import io
import base64
import json
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")  # 讓 matplotlib 可以在沒有螢幕的伺服器上畫圖

from django.shortcuts import render

def home(request):

    return render(request, "core/index.html")

def k_chart(request):
    """
    K 線圖頁面：抓約 5 年日線資料給前端 Plotly 畫圖。
    使用者只輸入 2330，程式會依序嘗試 2330.TW、2330.TWO。
    也支援 AAPL 這種美股代號。
    """
    raw_code = request.GET.get("code", "2330").strip()
    error = None
    used_symbol = None
    records = []

    # 準備 candidate symbol
    candidates = []
    code_upper = raw_code.upper()

    if "." in code_upper:
        candidates.append(code_upper)
    else:
        # 台股：先試上市，再試上櫃
        candidates.append(f"{code_upper}.TW")
        candidates.append(f"{code_upper}.TWO")

    df = None

    for sym in candidates:
        try:
            tmp = yf.download(
                sym,
                period="5y",      # 抓約五年
                interval="1d",
                auto_adjust=False,
                progress=False,
            )
        except Exception:
            continue

        if tmp is None or tmp.empty:
            continue

        # 若是 MultiIndex 欄位，攤平成單層
        if isinstance(tmp.columns, pd.MultiIndex):
            tmp = tmp.xs(sym, level=1, axis=1)

        needed = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in tmp.columns for c in needed):
            continue

        tmp = tmp[needed].apply(pd.to_numeric, errors="coerce").dropna()
        if tmp.empty:
            continue

        df = tmp
        used_symbol = sym
        break

    company_name = None
    last_close = None
    last_change = None
    last_change_pct = None
    last_date_str = None

    if df is None:
        error = f"找不到 {raw_code}（已嘗試：{', '.join(candidates)}）的價格資料"
    else:
        # 把 index 轉成欄位 Date 方便轉 JSON
        df = df.reset_index()  # 有 Date 欄
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        for _, row in df.iterrows():
            records.append(
                {
                    "date": row["Date"],
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                }
            )

        # 取最後一筆做「收盤價＋漲跌」
        last_row = df.iloc[-1]
        last_close = float(last_row["Close"])
        last_date_str = last_row["Date"]

        if len(df) >= 2:
            prev_close = float(df.iloc[-2]["Close"])
            last_change = last_close - prev_close
            if prev_close != 0:
                last_change_pct = last_change / prev_close * 100

        # 嘗試抓公司名稱（失敗就算了）
        company_name = raw_code
        if used_symbol:
            try:
                tkr = yf.Ticker(used_symbol)
                info = getattr(tkr, "get_info", tkr.info)()
                company_name = (
                    info.get("shortName")
                    or info.get("longName")
                    or company_name
                )
            except Exception:
                pass

    context = {
        "raw_code": raw_code,
        "symbol": used_symbol or raw_code,
        "error": error,
        "ohlc_json": json.dumps(records, ensure_ascii=False),
        "company_name": company_name,
        "last_close": last_close,
        "last_change": last_change,
        "last_change_pct": last_change_pct,
        "last_date": last_date_str,
    }
    return render(request, "core/k_chart.html", context)