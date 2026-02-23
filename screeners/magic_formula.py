"""
Magic Formula (Joel Greenblatt) Stock Screener.

Ranks stocks by:
  1. Earnings Yield = EBIT / EV  (higher = more undervalued)
  2. Return on Capital = EBIT / (Net Working Capital + Net Tangible Assets)  (higher = better quality)
Combined rank (lower = better) determines the final Magic Formula ranking.
"""

import logging

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)


def run_magic_formula(stock_data: list[dict], market: str) -> pd.DataFrame:
    """매직 포뮬라 스크리닝 실행.

    Args:
        stock_data: fetch된 종목 데이터 리스트
        market: 'kr' 또는 'us'

    Returns:
        상위 N개 종목의 DataFrame (순위 포함)
    """
    df = pd.DataFrame(stock_data)
    if df.empty:
        logger.warning("매직 포뮬라: 입력 데이터 없음")
        return pd.DataFrame()

    initial_count = len(df)
    logger.info("매직 포뮬라 시작: %d 종목 (%s)", initial_count, market)

    # ── 필터링 ────────────────────────────────────────────────────
    df = _apply_filters(df, market)
    logger.info("필터 후: %d → %d 종목", initial_count, len(df))

    if df.empty:
        logger.warning("필터 후 종목 없음")
        return pd.DataFrame()

    # ── 계산 ──────────────────────────────────────────────────────
    df = _calculate_metrics(df)

    # 유효 데이터만 (EBIT, EV 양수)
    df = df[(df["ebit"] > 0) & (df["ev_calc"] > 0)].copy()
    if df.empty:
        logger.warning("유효 EBIT/EV 종목 없음")
        return pd.DataFrame()

    # ── 랭킹 ──────────────────────────────────────────────────────
    df = _rank_stocks(df)

    # 상위 N개 추출
    top = df.head(config.MF_TOP_N).copy()
    top["분석일자"] = pd.Timestamp.now().strftime("%Y-%m-%d")

    # 출력 컬럼 정리
    result = _format_output(top)
    logger.info("매직 포뮬라 완료: 상위 %d 종목 추출", len(result))
    return result


def _apply_filters(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """그린블라트 원칙에 따른 필터링."""
    # 업종 제외 (금융, 유틸리티)
    if market == "kr":
        excluded = config.KR_EXCLUDED_SECTORS
        min_cap = config.KR_MIN_MARKET_CAP
    else:
        excluded = config.US_EXCLUDED_SECTORS
        min_cap = config.US_MIN_MARKET_CAP

    if "sector" in df.columns:
        mask_sector = ~df["sector"].fillna("").isin(excluded)
        # 한국: industry 컬럼도 확인
        if "industry" in df.columns:
            mask_industry = ~df["industry"].fillna("").isin(excluded)
            mask_sector = mask_sector & mask_industry
        df = df[mask_sector]

    # 시가총액 필터
    df = df[df["market_cap"].notna() & (df["market_cap"] >= min_cap)]

    # EBIT > 0
    df = df[df["ebit"].notna() & (df["ebit"] > 0)]

    return df.copy()


def _calculate_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """이익수익률과 ROC 계산."""
    # EV 계산: 시가총액 + 총부채 - 현금
    df["ev_calc"] = df.apply(_calc_ev, axis=1)

    # 이익수익률 = EBIT / EV
    df["earnings_yield"] = df.apply(
        lambda r: r["ebit"] / r["ev_calc"] if r["ev_calc"] and r["ev_calc"] > 0 else np.nan,
        axis=1,
    )

    # 순운전자본 = 유동자산 - 유동부채
    df["net_working_capital"] = df.apply(
        lambda r: _sub(r.get("current_assets"), r.get("current_liabilities")),
        axis=1,
    )

    # 순유형자산 = 총자산 - 무형자산 - 현금 - (유동부채 as proxy for 비이자발생부채)
    df["net_tangible_assets"] = df.apply(
        lambda r: _calc_nta(r),
        axis=1,
    )

    # 투자자본 = 순운전자본 + 순유형자산
    df["invested_capital"] = df["net_working_capital"].fillna(0) + df["net_tangible_assets"].fillna(0)

    # ROC = EBIT / 투자자본
    df["roc"] = df.apply(
        lambda r: r["ebit"] / r["invested_capital"]
        if r.get("invested_capital") and r["invested_capital"] > 0
        else np.nan,
        axis=1,
    )

    return df


def _calc_ev(row) -> float | None:
    """기업가치(EV) 계산. yfinance의 enterpriseValue가 있으면 우선 사용."""
    ev = row.get("enterprise_value")
    if ev and ev > 0:
        return ev
    mc = row.get("market_cap")
    debt = row.get("total_debt") or 0
    cash = row.get("total_cash") or 0
    if mc:
        return mc + debt - cash
    return None


def _calc_nta(row) -> float | None:
    """순유형자산 계산."""
    ta = row.get("total_assets")
    if not ta:
        return None
    intangibles = row.get("intangible_assets") or 0
    cash = row.get("total_cash") or 0
    cl = row.get("current_liabilities") or 0  # 비이자발생부채 대리지표
    return ta - intangibles - cash - cl


def _sub(a, b) -> float | None:
    if a is not None and b is not None:
        return a - b
    return None


def _rank_stocks(df: pd.DataFrame) -> pd.DataFrame:
    """이익수익률과 ROC 기준으로 종합 순위 산출."""
    # 이익수익률: 높을수록 좋음 → ascending=False
    df["earnings_yield_rank"] = df["earnings_yield"].rank(ascending=False, method="min", na_option="bottom")

    # ROC: 높을수록 좋음 → ascending=False
    df["roc_rank"] = df["roc"].rank(ascending=False, method="min", na_option="bottom")

    # 종합 순위 = 두 순위 합산 (낮을수록 우수)
    df["combined_rank"] = df["earnings_yield_rank"] + df["roc_rank"]
    df = df.sort_values("combined_rank").reset_index(drop=True)
    df["final_rank"] = range(1, len(df) + 1)

    return df


def _format_output(df: pd.DataFrame) -> pd.DataFrame:
    """Google Sheets 출력 형식에 맞게 컬럼 정리."""
    output = pd.DataFrame()
    output["순위"] = df["final_rank"]
    output["티커"] = df["ticker"]
    output["종목명"] = df["name"]
    output["업종"] = df["sector"].fillna("") + " / " + df["industry"].fillna("")
    output["시가총액"] = df["market_cap"]
    output["현재주가"] = df["current_price"]
    output["EBIT"] = df["ebit"]
    output["EV"] = df["ev_calc"]
    output["이익수익률"] = df["earnings_yield"].round(4)
    output["ROC"] = df["roc"].round(4)
    output["이익수익률_순위"] = df["earnings_yield_rank"].astype(int)
    output["ROC_순위"] = df["roc_rank"].astype(int)
    output["종합순위"] = df["combined_rank"].astype(int)
    output["PER"] = df["per"]
    output["PBR"] = df["pbr"]
    output["영업이익률"] = df.get("operating_margin")
    output["부채비율"] = df.get("debt_ratio")
    output["분석일자"] = df["분석일자"]

    return output.reset_index(drop=True)
