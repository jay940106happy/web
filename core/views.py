import json
from django.shortcuts import render


def home(request):
    return render(request, "core/index.html")


def home(request):
    return render(request, "core/index.html")


def k_chart(request):
    """
    個股 K 線 + 財報分析頁面
    - 上方：3 年日 K + 成交量（ECharts 畫）
    - 下方：公司資訊 / 財務比率 / 財報趨勢圖（同一頁互動切換）
    """
    # 只在需要時才載入 heavy 套件
    import pandas as pd
    import numpy as np
    import yfinance as yf

    raw_code = request.GET.get("code", "2330").strip()
    error = None
    used_symbol = None
    records = []

    # ------------ 1. 解析股票代號（台股 / 美股） ------------
    candidates = []
    code_upper = raw_code.upper()

    if "." in code_upper:
        candidates.append(code_upper)
    else:
        # 台股上市 / 上櫃
        candidates.append(f"{code_upper}.TW")
        candidates.append(f"{code_upper}.TWO")
        # 萬一本來就是美股代號
        candidates.append(code_upper)

    df = None

    for sym in candidates:
        try:
            tmp = yf.download(
                sym,
                period="3y",
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

    # 這兩個是我們要丟給前端的「財報 payload」
    fund_info = {}      # 靜態＋比率
    fund_series = {}    # 時間序列圖用

    # ------------ 小工具：從 yfinance DataFrame 抽出時間序列 ------------
    def build_series(df_src, row_candidates, max_points=12,
                     ratio_denominator=None, as_percent=False):
        """
        df_src: yfinance 的 quarterly_income_stmt / quarterly_balance_sheet...
                index = 科目名稱, columns = 各期日期
        row_candidates: 可能的 row 名稱 list（因為不同市場有時候名字略不同）
        ratio_denominator: 若要算比率，分母 row 的候選名稱 list
        回傳: [{"period": "2024-09-30", "value": 12345}, ...] 或 None
        """
        if df_src is None or df_src.empty:
            return None

        df = df_src.copy()

        # 找分子那列
        numerator = None
        for name in row_candidates:
            if name in df.index:
                numerator = df.loc[name]
                break
        if numerator is None:
            return None

        series = numerator.dropna()

        # 若要算比率 → 再找分母
        if ratio_denominator:
            denominator = None
            for name in ratio_denominator:
                if name in df.index:
                    denominator = df.loc[name]
                    break
            if denominator is None:
                return None

            denominator = denominator[series.index]
            with np.errstate(divide="ignore", invalid="ignore"):
                series = series / denominator
            if as_percent:
                series = series * 100

        # 轉成 list[dict]
        series = series.sort_index().iloc[-max_points:]

        out = []
        for idx, v in series.items():
            if hasattr(idx, "strftime"):
                period = idx.strftime("%Y-%m-%d")
            else:
                period = str(idx)

            try:
                v = float(v)
            except Exception:
                continue
            if not np.isfinite(v):
                continue

            out.append({"period": period, "value": v})

        return out or None

    # ------------ 2. 沒抓到股價 → 回傳錯誤頁 ------------
    if df is None:
        context = {
            "raw_code": raw_code,
            "symbol": raw_code,
            "error": f"找不到 {raw_code}（已嘗試：{', '.join(candidates)}）的價格資料",
            "ohlc_json": "[]",
            "company_name": None,
            "last_close": None,
            "last_change": None,
            "last_change_pct": None,
            "last_date": None,
            "fund_info": {},
            "fundamentals_json": "{}",
        }
        return render(request, "core/k_chart.html", context)

    # ------------ 3. 整理 K 線資料 ------------
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

    # ------------ 4. 用 yfinance.Ticker 抓公司資訊＋財報 ------------
    if used_symbol:
        try:
            tkr = yf.Ticker(used_symbol)
        except Exception:
            tkr = None
        else:
            # ----- 4-1. 公司基本資料 / 估值 / 比率 -----
            try:
                info = getattr(tkr, "get_info", lambda: tkr.info)() or {}
            except Exception:
                info = {}
            company_name = (
                info.get("shortName")
                or info.get("longName")
                or company_name
            )

            def pct(x):
                return float(x) * 100 if x not in (None, "None") else None

            fund_info = {
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "country": info.get("country"),
                "employees": info.get("fullTimeEmployees"),
                "marketCap": info.get("marketCap"),
                "currency": info.get("currency"),
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "pegRatio": info.get("pegRatio"),
                "priceToBook": info.get("priceToBook"),
                "dividendYieldPct": pct(info.get("dividendYield")),
                "payoutRatio": info.get("payoutRatio"),
                "beta": info.get("beta"),
                "profitMarginsPct": pct(info.get("profitMargins")),
                "operatingMarginsPct": pct(info.get("operatingMargins")),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "debtToEquity": info.get("debtToEquity"),
            }

            # ----- 4-2. 三大財報：季損益 / 資產負債 / 現金流 -----
            try:
                inc_q_df = tkr.quarterly_income_stmt
            except Exception:
                inc_q_df = None

            try:
                bs_q_df = tkr.quarterly_balance_sheet
            except Exception:
                bs_q_df = None

            try:
                cf_q_df = tkr.quarterly_cashflow
            except Exception:
                cf_q_df = None

            # ----- 4-3. 主要科目時間序列（圖表用） -----
            revenue = build_series(
                inc_q_df,
                ["Total Revenue", "TotalRevenue", "Revenue"],
                max_points=12,
            )
            op_income = build_series(
                inc_q_df,
                ["Operating Income", "OperatingIncome"],
                max_points=12,
            )
            net_income = build_series(
                inc_q_df,
                [
                    "Net Income",
                    "Net Income Common Stockholders",
                    "NetIncome",
                ],
                max_points=12,
            )
            gross_margin = build_series(
                inc_q_df,
                ["Gross Profit", "GrossProfit"],
                max_points=12,
                ratio_denominator=["Total Revenue", "TotalRevenue", "Revenue"],
                as_percent=True,
            )
            op_margin = build_series(
                inc_q_df,
                ["Operating Income", "OperatingIncome"],
                max_points=12,
                ratio_denominator=["Total Revenue", "TotalRevenue", "Revenue"],
                as_percent=True,
            )
            net_margin = build_series(
                inc_q_df,
                [
                    "Net Income",
                    "Net Income Common Stockholders",
                    "NetIncome",
                ],
                max_points=12,
                ratio_denominator=["Total Revenue", "TotalRevenue", "Revenue"],
                as_percent=True,
            )

            op_cf = build_series(
                cf_q_df,
                [
                    "Total Cash From Operating Activities",
                    "Operating Cash Flow",
                    "NetCashProvidedByUsedInOperatingActivities",
                ],
                max_points=12,
            )

            total_assets = build_series(
                bs_q_df,
                ["Total Assets"],
                max_points=12,
            )
            total_liab = build_series(
                bs_q_df,
                [
                    "Total Liabilities Net Minority Interest",
                    "Total Liab",
                ],
                max_points=12,
            )

            fund_series = {
                "revenue": revenue,
                "operatingIncome": op_income,
                "netIncome": net_income,
                "grossMargin": gross_margin,
                "operatingMargin": op_margin,
                "netMargin": net_margin,
                "operatingCashFlow": op_cf,
                "totalAssets": total_assets,
                "totalLiabilities": total_liab,
            }

    fundamentals_payload = {
        "info": fund_info,
        "series": fund_series,
    }

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
        "fund_info": fund_info,
        "fundamentals_json": json.dumps(
            fundamentals_payload, ensure_ascii=False
        ),
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