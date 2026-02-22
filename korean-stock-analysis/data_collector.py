"""주식 데이터 수집 모듈.

pykrx를 주 데이터 소스로 사용하고, yfinance를 보조로 활용합니다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock as pykrx_stock

import config

logger = logging.getLogger(__name__)


def _format_date(dt: datetime) -> str:
    """pykrx 형식의 날짜 문자열 반환 (YYYYMMDD)."""
    return dt.strftime("%Y%m%d")


def get_ohlcv(ticker: str, days: int = config.LOOKBACK_DAYS) -> pd.DataFrame:
    """종목의 최근 N일 OHLCV 데이터를 가져옵니다.

    Args:
        ticker: 종목코드 (예: "005930")
        days: 조회 기간 (영업일 기준이 아닌 캘린더일 기준)

    Returns:
        날짜 인덱스의 OHLCV DataFrame.
        컬럼: open, high, low, close, volume
    """
    end_date = datetime.now()
    # 영업일 확보를 위해 여유분 추가
    start_date = end_date - timedelta(days=int(days * 1.8))

    try:
        df = pykrx_stock.get_market_ohlcv_by_date(
            _format_date(start_date),
            _format_date(end_date),
            ticker,
        )
        if df.empty:
            logger.warning("pykrx에서 %s 데이터를 가져올 수 없습니다.", ticker)
            return pd.DataFrame()

        df.columns = [c.lower() for c in df.columns]
        # pykrx 컬럼명 매핑 (시가/고가/저가/종가/거래량)
        rename_map = {
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
        }
        df = df.rename(columns=rename_map)

        # 필요한 컬럼만 유지
        required = ["open", "high", "low", "close", "volume"]
        available = [c for c in required if c in df.columns]
        df = df[available]

        # 최근 days 영업일만 유지
        df = df.tail(days)
        return df

    except Exception:
        logger.exception("pykrx OHLCV 조회 실패 (종목: %s)", ticker)
        return pd.DataFrame()


def _recent_trading_range() -> tuple[str, str]:
    """주말/공휴일을 고려하여 최근 거래일을 포함하는 조회 범위를 반환합니다.

    Returns:
        (start_date, end_date) YYYYMMDD 형식
    """
    today = datetime.now()
    # 최근 10일 범위를 조회하면 주말·공휴일과 무관하게 거래일 데이터를 얻을 수 있음
    start = today - timedelta(days=10)
    return _format_date(start), _format_date(today)


def get_fundamental(ticker: str) -> dict:
    """종목의 펀더멘털 데이터 (PER, PBR, 배당수익률, 시가총액)를 가져옵니다.

    Returns:
        {"per": float, "pbr": float, "dividend_yield": float, "market_cap": int}
    """
    start, end = _recent_trading_range()
    result = {"per": None, "pbr": None, "dividend_yield": None, "market_cap": None}

    try:
        fund_df = pykrx_stock.get_market_fundamental_by_date(
            start, end, ticker
        )
        if not fund_df.empty:
            row = fund_df.iloc[-1]
            rename = {"PER": "per", "PBR": "pbr", "DIV": "dividend_yield"}
            for orig, key in rename.items():
                if orig in fund_df.columns:
                    result[key] = float(row[orig]) if pd.notna(row[orig]) else None
    except Exception:
        logger.exception("펀더멘털 조회 실패 (종목: %s)", ticker)

    try:
        cap_df = pykrx_stock.get_market_cap_by_date(start, end, ticker)
        if not cap_df.empty:
            cap_col = "시가총액" if "시가총액" in cap_df.columns else (
                cap_df.columns[0] if len(cap_df.columns) > 0 else None
            )
            if cap_col:
                result["market_cap"] = int(cap_df.iloc[-1][cap_col])
    except Exception:
        logger.exception("시가총액 조회 실패 (종목: %s)", ticker)

    return result


def get_market_index(index_ticker: str = "1001") -> dict | None:
    """시장 지수 정보를 가져옵니다.

    Args:
        index_ticker: "1001" (코스피), "2001" (코스닥)

    Returns:
        {"name": str, "close": float, "change_pct": float} 또는 None
    """
    today = datetime.now()
    start = today - timedelta(days=7)

    try:
        df = pykrx_stock.get_index_ohlcv_by_date(
            _format_date(start), _format_date(today), index_ticker
        )
        if df.empty or len(df) < 2:
            return None

        close_col = "종가" if "종가" in df.columns else df.columns[0]
        latest = float(df[close_col].iloc[-1])
        prev = float(df[close_col].iloc[-2])
        change_pct = ((latest - prev) / prev) * 100 if prev != 0 else 0

        index_names = {"1001": "코스피", "2001": "코스닥"}
        return {
            "name": index_names.get(index_ticker, index_ticker),
            "close": latest,
            "change_pct": round(change_pct, 2),
        }
    except Exception:
        logger.exception("지수 조회 실패 (%s)", index_ticker)
        return None


def get_current_price_info(ticker: str, ohlcv: pd.DataFrame) -> dict:
    """현재가와 전일 대비 변동률을 계산합니다.

    Args:
        ticker: 종목코드
        ohlcv: OHLCV DataFrame

    Returns:
        {"current_price": float, "change_pct": float}
    """
    if ohlcv.empty or len(ohlcv) < 2:
        return {"current_price": 0, "change_pct": 0}

    current = float(ohlcv["close"].iloc[-1])
    prev = float(ohlcv["close"].iloc[-2])
    change_pct = ((current - prev) / prev) * 100 if prev != 0 else 0

    return {
        "current_price": current,
        "change_pct": round(change_pct, 2),
    }
