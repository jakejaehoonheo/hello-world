"""
Stock Screening Automation - Data Collector
Collects stock universe and financial data for Korean and US markets.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from tqdm import tqdm

import config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Stock Universe Loaders
# ═══════════════════════════════════════════════════════════════════════

def get_kr_stock_list() -> pd.DataFrame:
    """한국 주식 유니버스 (KOSPI/KOSDAQ 시가총액 상위 종목) 로드.
    pykrx 우선, 실패 시 FinanceDataReader 사용.
    Returns DataFrame with columns: [ticker, name, market].
    """
    try:
        return _get_kr_stocks_pykrx()
    except Exception as e:
        logger.warning("pykrx 로드 실패, FinanceDataReader로 대체: %s", e)
    try:
        return _get_kr_stocks_fdr()
    except Exception as e:
        logger.error("한국 종목 리스트 로드 실패: %s", e)
        return pd.DataFrame(columns=["ticker", "name", "market"])


def _get_kr_stocks_pykrx() -> pd.DataFrame:
    from pykrx import stock as pykrx_stock

    today = datetime.now().strftime("%Y%m%d")
    rows = []
    for market_name, market_code in [("KOSPI", "STK"), ("KOSDAQ", "KSQ")]:
        tickers = pykrx_stock.get_market_ticker_list(today, market=market_code)
        for t in tickers:
            name = pykrx_stock.get_market_ticker_name(t)
            rows.append({"ticker": t, "name": name, "market": market_name})
    df = pd.DataFrame(rows)
    logger.info("pykrx: %d 종목 로드", len(df))
    return df


def _get_kr_stocks_fdr() -> pd.DataFrame:
    import FinanceDataReader as fdr

    rows = []
    for market_name in ["KOSPI", "KOSDAQ"]:
        listing = fdr.StockListing(market_name)
        for _, row in listing.iterrows():
            code = str(row.get("Code", row.get("Symbol", ""))).zfill(6)
            name = row.get("Name", "")
            rows.append({"ticker": code, "name": name, "market": market_name})
    df = pd.DataFrame(rows)
    logger.info("FDR: %d 종목 로드", len(df))
    return df


def get_us_stock_list() -> pd.DataFrame:
    """S&P 500 구성 종목을 Wikipedia에서 파싱.
    Returns DataFrame with columns: [ticker, name, sector, market].
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", {"id": "constituents"})
        df = pd.read_html(str(table))[0]
        result = pd.DataFrame({
            "ticker": df["Symbol"].str.replace(".", "-", regex=False),
            "name": df["Security"],
            "sector": df["GICS Sector"],
            "market": "US",
        })
        logger.info("S&P 500: %d 종목 로드", len(result))
        return result
    except Exception as e:
        logger.error("S&P 500 목록 로드 실패: %s", e)
        return pd.DataFrame(columns=["ticker", "name", "sector", "market"])


# ═══════════════════════════════════════════════════════════════════════
#  Financial Data Fetchers
# ═══════════════════════════════════════════════════════════════════════

def _yf_ticker_suffix(ticker: str, market: str) -> str:
    """한국 종목에 yfinance suffix 추가."""
    if market == "KOSPI":
        return f"{ticker}.KS"
    elif market == "KOSDAQ":
        return f"{ticker}.KQ"
    return ticker


def fetch_single_stock_data(ticker: str, name: str, market: str) -> dict | None:
    """단일 종목의 재무/시세 데이터를 수집하여 dict로 반환."""
    is_kr = market in ("KOSPI", "KOSDAQ")
    yf_ticker = _yf_ticker_suffix(ticker, market)

    for attempt in range(config.API_RETRY_COUNT):
        try:
            data = _collect_from_yfinance(yf_ticker, ticker, name, market)
            if is_kr:
                data = _supplement_kr_data(data, ticker, market)
            return data
        except Exception as e:
            if attempt < config.API_RETRY_COUNT - 1:
                time.sleep(1 * (attempt + 1))
                logger.debug("재시도 %d/%d: %s (%s)", attempt + 2, config.API_RETRY_COUNT, ticker, e)
            else:
                logger.warning("데이터 수집 실패 - %s (%s): %s", ticker, name, e)
                return None
    return None


def _collect_from_yfinance(yf_ticker: str, raw_ticker: str, name: str, market: str) -> dict:
    """yfinance에서 종목 데이터 수집."""
    tk = yf.Ticker(yf_ticker)
    info = tk.info or {}

    # 기본 정보
    data = {
        "ticker": raw_ticker,
        "yf_ticker": yf_ticker,
        "name": name,
        "market": market,
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "currency": info.get("currency", "KRW" if market in ("KOSPI", "KOSDAQ") else "USD"),
    }

    # 매직 포뮬라용 데이터
    data["ebit"] = info.get("ebitda")  # EBITDA를 기본으로, 아래서 보정
    operating_income = info.get("operatingIncome")
    if operating_income is not None:
        data["ebit"] = operating_income

    data["enterprise_value"] = info.get("enterpriseValue")
    data["total_assets"] = info.get("totalAssets")
    data["total_debt"] = info.get("totalDebt")
    data["total_cash"] = info.get("totalCash")
    data["current_assets"] = None
    data["current_liabilities"] = None
    data["intangible_assets"] = None

    # 재무제표에서 상세 데이터 추출
    try:
        bs = tk.balance_sheet
        if bs is not None and not bs.empty:
            latest = bs.iloc[:, 0]
            data["total_assets"] = data["total_assets"] or _safe_get(latest, "Total Assets")
            data["current_assets"] = _safe_get(latest, "Current Assets")
            data["current_liabilities"] = _safe_get(latest, "Current Liabilities")
            data["intangible_assets"] = (
                _safe_get(latest, "Intangible Assets")
                or _safe_get(latest, "Goodwill And Other Intangible Assets")
            )
    except Exception:
        pass

    try:
        inc = tk.income_stmt
        if inc is not None and not inc.empty:
            # TTM EBIT: 가장 최근 연간 영업이익 사용 (분기 합산이 불가능한 경우)
            ebit_val = _safe_get(inc.iloc[:, 0], "EBIT") or _safe_get(inc.iloc[:, 0], "Operating Income")
            if ebit_val is not None:
                data["ebit"] = ebit_val
    except Exception:
        pass

    # TTM EBIT from quarterly data
    try:
        q_inc = tk.quarterly_income_stmt
        if q_inc is not None and not q_inc.empty:
            ebit_row = None
            for label in ["EBIT", "Operating Income"]:
                if label in q_inc.index:
                    ebit_row = q_inc.loc[label]
                    break
            if ebit_row is not None:
                recent_4q = ebit_row.dropna().head(4)
                if len(recent_4q) == 4:
                    data["ebit"] = recent_4q.sum()
    except Exception:
        pass

    # 밸류에이션 지표
    data["per"] = info.get("trailingPE") or info.get("forwardPE")
    data["pbr"] = info.get("priceToBook")
    data["roe"] = info.get("returnOnEquity")
    data["operating_margin"] = info.get("operatingMargins")
    data["debt_ratio"] = None
    if data.get("total_debt") and data.get("total_assets"):
        try:
            data["debt_ratio"] = data["total_debt"] / data["total_assets"]
        except (ZeroDivisionError, TypeError):
            pass

    # 배당 데이터
    data["dividend_yield"] = info.get("dividendYield")
    data["dividend_rate"] = info.get("dividendRate")
    data["payout_ratio"] = info.get("payoutRatio")
    data["trailing_eps"] = info.get("trailingEps")

    # 배당 이력 (최근 12년)
    try:
        hist_divs = tk.dividends
        if hist_divs is not None and len(hist_divs) > 0:
            data["dividend_history"] = hist_divs
        else:
            data["dividend_history"] = pd.Series(dtype=float)
    except Exception:
        data["dividend_history"] = pd.Series(dtype=float)

    # 주가 이력 (최근 12년, 연도별 고가/저가)
    try:
        price_hist = tk.history(period=f"{config.HISTORY_YEARS}y")
        if price_hist is not None and not price_hist.empty:
            data["price_history"] = price_hist
        else:
            data["price_history"] = pd.DataFrame()
    except Exception:
        data["price_history"] = pd.DataFrame()

    # EPS 이력
    try:
        earnings = tk.earnings_history
        if earnings is not None and not earnings.empty:
            data["eps_history"] = earnings
        else:
            data["eps_history"] = pd.DataFrame()
    except Exception:
        data["eps_history"] = pd.DataFrame()

    # 발행주식수
    data["shares_outstanding"] = info.get("sharesOutstanding")

    return data


def _supplement_kr_data(data: dict, ticker: str, market: str) -> dict:
    """한국 주식의 경우 pykrx/FDR로 데이터 보완."""
    try:
        from pykrx import stock as pykrx_stock

        today = datetime.now().strftime("%Y%m%d")

        # 시가총액 보완
        if not data.get("market_cap"):
            try:
                cap_df = pykrx_stock.get_market_cap(today, today, ticker)
                if not cap_df.empty:
                    data["market_cap"] = cap_df.iloc[0].get("시가총액")
            except Exception:
                pass

        # 기본 재무 데이터 보완
        try:
            fundamental = pykrx_stock.get_market_fundamental(today, today, ticker)
            if not fundamental.empty:
                row = fundamental.iloc[0]
                if not data.get("per"):
                    data["per"] = row.get("PER") if row.get("PER") and row.get("PER") > 0 else None
                if not data.get("pbr"):
                    data["pbr"] = row.get("PBR") if row.get("PBR") and row.get("PBR") > 0 else None
                if not data.get("dividend_yield"):
                    dy = row.get("DIV")
                    if dy and dy > 0:
                        data["dividend_yield"] = dy / 100.0
        except Exception:
            pass

    except ImportError:
        logger.debug("pykrx를 사용할 수 없어 한국 데이터 보완 생략")

    return data


def _safe_get(series, key):
    """pandas Series에서 안전하게 값 추출."""
    try:
        val = series.get(key)
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            return val
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════
#  Batch Collection (Parallel)
# ═══════════════════════════════════════════════════════════════════════

def collect_all_data(stock_list: pd.DataFrame) -> list[dict]:
    """종목 리스트에 대해 병렬로 데이터를 수집."""
    results = []
    failed = []

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        futures = {}
        for _, row in stock_list.iterrows():
            ticker = row["ticker"]
            name = row.get("name", "")
            market = row.get("market", "")
            future = executor.submit(fetch_single_stock_data, ticker, name, market)
            futures[future] = (ticker, name)

        for future in tqdm(as_completed(futures), total=len(futures), desc="데이터 수집"):
            ticker, name = futures[future]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
                else:
                    failed.append(ticker)
            except Exception as e:
                logger.warning("예외 발생 - %s: %s", ticker, e)
                failed.append(ticker)

    if failed:
        logger.info("데이터 수집 실패 종목 %d개: %s", len(failed), failed[:20])

    logger.info("총 %d개 종목 데이터 수집 완료", len(results))
    return results
