"""종목 추천 스크리너.

매직포뮬러(조엘 그린블라트) + 배당 분석(제랄딘 와이스)을 조합하여
전체 시장에서 매력적인 종목을 자동 발굴합니다.

선별 기준:
1. 이익수익률(EY) 상위 — PER이 낮아 싸게 살 수 있는 종목
2. 자본수익률(ROE) 상위 — 자본 효율이 높은 종목
3. 배당수익률 상위 — 현금 흐름이 좋고 배당을 주는 종목
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock as pykrx_stock

logger = logging.getLogger(__name__)


def _find_trading_date() -> str:
    """최근 거래일을 YYYYMMDD 형식으로 반환합니다."""
    today = datetime.now()
    for i in range(7):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y%m%d")
        try:
            tickers = pykrx_stock.get_market_ticker_list(date_str, market="KOSPI")
            if tickers:
                return date_str
        except Exception:
            continue
    return today.strftime("%Y%m%d")


def _fetch_all_fundamentals(date_str: str) -> pd.DataFrame:
    """KOSPI + KOSDAQ 전 종목 펀더멘털을 한 번에 조회합니다."""
    frames = []
    for market in ("KOSPI", "KOSDAQ"):
        try:
            df = pykrx_stock.get_market_fundamental(date_str, market=market)
            if not df.empty:
                df["market"] = market
                frames.append(df)
        except Exception:
            logger.exception("전종목 펀더멘털 조회 실패: %s", market)
        time.sleep(0.5)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames)


def _fetch_all_market_caps(date_str: str) -> pd.Series:
    """KOSPI + KOSDAQ 전 종목 시가총액을 조회합니다."""
    frames = []
    for market in ("KOSPI", "KOSDAQ"):
        try:
            df = pykrx_stock.get_market_cap(date_str, market=market)
            if not df.empty and "시가총액" in df.columns:
                frames.append(df["시가총액"])
        except Exception:
            logger.exception("전종목 시가총액 조회 실패: %s", market)
        time.sleep(0.5)

    if not frames:
        return pd.Series(dtype=float)
    return pd.concat(frames)


def screen_stocks(
    exclude_tickers: list[str] | None = None,
    top_n: int = 3,
) -> list[dict]:
    """매직포뮬러 + 배당 기준으로 상위 종목을 추천합니다.

    전체 흐름:
    1. 전 종목 펀더멘털(PER, PBR, DIV) + 시가총액 일괄 조회
    2. 필터링 (수익성 있고, 배당 있고, 시총 일정 이상)
    3. 매직포뮬러 점수 + 배당 점수 합산
    4. 상위 N개 종목 반환

    Args:
        exclude_tickers: 이미 분석한 종목코드 (제외)
        top_n: 추천 종목 수 (기본 3)

    Returns:
        [{"ticker": str, "name": str, "query": str, "reason": str}, ...]
    """
    exclude = set(exclude_tickers or [])

    logger.info("추천 종목 스크리닝 시작...")
    date_str = _find_trading_date()
    logger.info("기준일: %s", date_str)

    # 1. 전 종목 펀더멘털 + 시가총액 조회
    fund = _fetch_all_fundamentals(date_str)
    if fund.empty:
        logger.warning("펀더멘털 데이터 조회 실패, 추천 중단")
        return []

    caps = _fetch_all_market_caps(date_str)

    # 시가총액 병합
    if not caps.empty:
        fund["시가총액"] = caps
    else:
        fund["시가총액"] = 0

    # 2. 필터링
    # 이미 분석한 종목 제외
    fund = fund[~fund.index.isin(exclude)]

    # 기본 필터: 수익성 + 배당 + 적정 밸류에이션
    fund = fund[
        (fund["PER"] > 2) & (fund["PER"] < 30)     # 적정 PER 범위
        & (fund["PBR"] > 0.2) & (fund["PBR"] < 10) # 적정 PBR 범위
        & (fund["DIV"] >= 1.0)                       # 배당 1% 이상
        & (fund["시가총액"] >= 300_000_000_000)       # 시총 3000억 이상
    ]

    if fund.empty:
        logger.warning("필터 조건을 만족하는 종목이 없습니다.")
        return []

    logger.info("필터 통과 종목: %d개", len(fund))

    # 3. 점수 계산
    # 이익수익률 (Earnings Yield) = 1/PER × 100
    fund["EY"] = (1.0 / fund["PER"]) * 100
    # 자본수익률 (ROE) ≈ PBR/PER × 100
    fund["ROE"] = (fund["PBR"] / fund["PER"]) * 100

    # 각 지표를 0~5점으로 환산
    fund["ey_score"] = (fund["EY"] / 20.0 * 5.0).clip(0, 5)
    fund["roe_score"] = (fund["ROE"] / 25.0 * 5.0).clip(0, 5)
    fund["div_score"] = (fund["DIV"] / 5.0 * 5.0).clip(0, 5)

    # 종합점수 = 매직포뮬러(EY + ROE) + 배당
    fund["composite"] = fund["ey_score"] + fund["roe_score"] + fund["div_score"]

    # 4. 정렬 및 상위 추출
    fund = fund.sort_values("composite", ascending=False)

    results = []
    for ticker in fund.head(top_n * 3).index:
        if len(results) >= top_n:
            break
        try:
            name = pykrx_stock.get_market_ticker_name(ticker)
            if not name:
                continue

            row = fund.loc[ticker]
            ey = row["EY"]
            roe = row["ROE"]
            div_yield = row["DIV"]
            cap_billions = row["시가총액"] / 100_000_000  # 억원

            reason_parts = []
            if ey >= 10:
                reason_parts.append(f"EY {ey:.1f}%")
            elif ey >= 5:
                reason_parts.append(f"EY {ey:.1f}%")
            if roe >= 15:
                reason_parts.append(f"ROE {roe:.1f}%")
            elif roe >= 10:
                reason_parts.append(f"ROE {roe:.1f}%")
            if div_yield >= 3:
                reason_parts.append(f"배당 {div_yield:.1f}%")
            elif div_yield >= 1:
                reason_parts.append(f"배당 {div_yield:.1f}%")

            reason = " / ".join(reason_parts)
            reason += f" (시총 {cap_billions:,.0f}억)"

            results.append({
                "ticker": ticker,
                "name": name,
                "query": "",
                "reason": reason,
            })

            logger.info(
                "추천 #%d: %s(%s) — %s | 종합 %.1f점",
                len(results), name, ticker, reason, row["composite"],
            )
        except Exception:
            logger.exception("종목 정보 조회 실패: %s", ticker)

    logger.info("추천 종목 스크리닝 완료: %d개 선정", len(results))
    return results
