import json
from django.shortcuts import render


def home(request):
    return render(request, "core/index.html")


def k_chart(request):
    """
    K 線圖頁面：抓約 3 年日線資料給前端 Plotly 畫圖。
    使用者只輸入 2330，程式會依序嘗試 2330.TW、2330.TWO。
    也支援 AAPL 這種美股代號。
    """
    # 🔹 把 heavy 的東西搬進來（只在用到這個 view 時載入）
    import pandas as pd
    import yfinance as yf

    raw_code = request.GET.get("code", "2330").strip()
    error = None
    used_symbol = None
    records = []

    candidates = []
    code_upper = raw_code.upper()

    if "." in code_upper:
        candidates.append(code_upper)
    else:
        candidates.append(f"{code_upper}.TW")
        candidates.append(f"{code_upper}.TWO")

    df = None

    for sym in candidates:
        try:
            tmp = yf.download(
                sym,
                period="3y",      # ⬅ 我先改成 3 年就好，比 5 年更省資源
                interval="1d",
                auto_adjust=False,
                progress=False,
            )
        except Exception:
            continue

        if tmp is None or tmp.empty:
            continue

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
        df = df.reset_index()
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

        last_row = df.iloc[-1]
        last_close = float(last_row["Close"])
        last_date_str = last_row["Date"]

        if len(df) >= 2:
            prev_close = float(df.iloc[-2]["Close"])
            last_change = last_close - prev_close
            if prev_close != 0:
                last_change_pct = last_change / prev_close * 100

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

def fundamental(request):
    import yfinance as yf
    import pandas as pd

    raw_code = request.GET.get("code", "2330").strip()
    code_upper = raw_code.upper()

    # 嘗試各種 symbol（台股 / 美股）
    candidates = []
    if "." in code_upper:
        candidates.append(code_upper)
    else:
        candidates.append(f"{code_upper}.TW")
        candidates.append(f"{code_upper}.TWO")
        candidates.append(code_upper)  # 萬一是美股代號

    tkr = None
    used_symbol = None

    for sym in candidates:
        try:
            tmp = yf.Ticker(sym)
            # 試著抓一下 info，沒炸就當作可用
            info_test = getattr(tmp, "get_info", lambda: tmp.info)()
            if info_test:  # 有拿到東西就用這個 symbol
                tkr = tmp
                used_symbol = sym
                break
        except Exception:
            continue

    # 完全找不到 symbol → 回報錯誤頁面
    if tkr is None:
        context = {
            "raw_code": raw_code,
            "symbol": raw_code,
            "error": f"找不到 {raw_code} 的公司資訊（已嘗試：{', '.join(candidates)}）",
            "company_name": None,
            "income_q": None,
            "bs_q": None,
            "cf_q": None,
        }
        return render(request, "core/fundamental.html", context)

    # -------- 基本公司資料 --------
    try:
        info = getattr(tkr, "get_info", lambda: tkr.info)() or {}
    except Exception:
        info = {}

    company_name = (
        info.get("longName")
        or info.get("shortName")
        or raw_code
    )
    sector = info.get("sector")
    industry = info.get("industry")
    country = info.get("country")
    currency = info.get("currency")
    market_cap = info.get("marketCap")
    trailing_pe = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    dividend_yield = info.get("dividendYield")
    beta = info.get("beta")

    # -------- DataFrame -> table 給 template --------
    def df_to_table(df, max_rows=6, max_cols=8, transpose=True):
        """
        回傳：
        {
          "columns": [...],
          "rows": [
            {"period": "2024-09-30", "cells": [...]},
            ...
          ]
        }
        """
        if df is None or len(df) == 0:
            return None

        df = df.copy()
        if transpose:
            df = df.T

        df = df.iloc[:max_rows, :max_cols]

        # index 變成期間字串
        if hasattr(df.index, "strftime"):
            periods = df.index.strftime("%Y-%m-%d").tolist()
        else:
            periods = df.index.map(str).tolist()

        columns = [str(c) for c in df.columns]

        rows = []
        for idx, period in zip(df.index, periods):
            row_vals = []
            for c in df.columns:
                v = df.at[idx, c]
                try:
                    if pd.isna(v):
                        v = None
                except Exception:
                    pass
                row_vals.append(v)
            rows.append({"period": period, "cells": row_vals})

        return {"columns": columns, "rows": rows}

    # -------- 三張季報 --------
    try:
        inc_q = df_to_table(tkr.quarterly_income_stmt)
    except Exception:
        inc_q = None

    try:
        bs_q = df_to_table(tkr.quarterly_balance_sheet)
    except Exception:
        bs_q = None

    try:
        cf_q = df_to_table(tkr.quarterly_cashflow)
    except Exception:
        cf_q = None

    # -------- 組 context 並一定要 return render --------
    context = {
        "raw_code": raw_code,
        "symbol": used_symbol or raw_code,
        "error": None,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "country": country,
        "currency": currency,
        "market_cap": market_cap,
        "trailing_pe": trailing_pe,
        "forward_pe": forward_pe,
        "dividend_yield": dividend_yield,
        "beta": beta,
        "income_q": inc_q,
        "bs_q": bs_q,
        "cf_q": cf_q,
    }

    return render(request, "core/fundamental.html", context)