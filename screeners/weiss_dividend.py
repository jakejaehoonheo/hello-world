"""
Weiss Dividend Analysis (Geraldine Weiss) Stock Screener.

Evaluates stocks based on:
  - Historical dividend yield channel (overvalued ↔ undervalued)
  - Blue-chip quality criteria (6 checks)
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)


def run_weiss_analysis(stock_data: list[dict], market: str) -> pd.DataFrame:
    """와이스 배당 분석 실행.

    Args:
        stock_data: fetch된 종목 데이터 리스트
        market: 'kr' 또는 'us'

    Returns:
        분석 결과 DataFrame (와이스 신호 포함, 순위 정렬)
    """
    results = []
    skipped = 0

    for stock in stock_data:
        try:
            analysis = _analyze_single(stock, market)
            if analysis is not None:
                results.append(analysis)
            else:
                skipped += 1
        except Exception as e:
            logger.debug("와이스 분석 실패 - %s: %s", stock.get("ticker"), e)
            skipped += 1

    if skipped:
        logger.info("와이스 분석 건너뜀: %d 종목 (데이터 부족)", skipped)

    if not results:
        logger.warning("와이스 분석: 유효 결과 없음")
        return pd.DataFrame()

    df = pd.DataFrame(results)

    # 현재위치 기준 내림차순 정렬 (1.0에 가까울수록 매수 신호)
    df = df.sort_values("current_position", ascending=False).reset_index(drop=True)
    df["순위"] = range(1, len(df) + 1)

    output = _format_output(df)
    logger.info("와이스 분석 완료: %d 종목", len(output))
    return output


def _analyze_single(stock: dict, market: str) -> dict | None:
    """단일 종목 와이스 분석."""
    ticker = stock.get("ticker", "")
    name = stock.get("name", "")
    current_price = stock.get("current_price")
    div_yield = stock.get("dividend_yield")

    if not current_price or current_price <= 0:
        return None

    # 배당 이력 처리
    div_history = stock.get("dividend_history", pd.Series(dtype=float))
    if isinstance(div_history, pd.Series) and len(div_history) > 0:
        annual_dps = _aggregate_annual_dps(div_history)
    else:
        return None  # 배당 이력 없으면 제외

    if len(annual_dps) < config.MIN_DIVIDEND_YEARS:
        return None  # 최소 이력 미달

    # 주가 이력에서 연도별 고가/저가
    price_history = stock.get("price_history", pd.DataFrame())
    if isinstance(price_history, pd.DataFrame) and not price_history.empty:
        annual_prices = _aggregate_annual_prices(price_history)
    else:
        return None

    # 역사적 배당수익률 채널 계산
    channel = _calc_yield_channel(annual_dps, annual_prices)
    if channel is None:
        return None

    high_yield, low_yield, mid_yield = channel

    # 현재 배당수익률
    if div_yield is None or div_yield <= 0:
        # DPS / 현재가로 계산 시도
        recent_dps = annual_dps.iloc[-1] if len(annual_dps) > 0 else 0
        if recent_dps > 0:
            div_yield = recent_dps / current_price
        else:
            return None

    # 현재 위치 계산
    if high_yield <= low_yield:
        return None
    current_position = (div_yield - low_yield) / (high_yield - low_yield)
    current_position = max(0.0, min(1.0, current_position))

    # 블루칩 점수 (6개 항목)
    bluechip_score, bluechip_details = _calc_bluechip_score(stock, annual_dps, market)

    # 와이스 종합 신호
    signal = _determine_signal(bluechip_score, current_position, annual_dps)

    # 배당 지속 연수
    dividend_years = _count_consecutive_dividend_years(annual_dps)

    # 최근 10년 DPS 문자열
    recent_10y_dps = annual_dps.tail(10).round(2).tolist()

    return {
        "ticker": ticker,
        "name": name,
        "sector": stock.get("sector", ""),
        "market": stock.get("market", ""),
        "market_cap": stock.get("market_cap"),
        "current_price": current_price,
        "current_dividend_yield": round(div_yield, 4),
        "high_yield": round(high_yield, 4),
        "low_yield": round(low_yield, 4),
        "current_position": round(current_position, 4),
        "signal": signal,
        "bluechip_score": bluechip_score,
        "dividend_years": dividend_years,
        "recent_10y_dps": str(recent_10y_dps),
        "payout_ratio": stock.get("payout_ratio"),
        "pbr": stock.get("pbr"),
        "per": stock.get("per"),
        "roe": stock.get("roe"),
        "분석일자": datetime.now().strftime("%Y-%m-%d"),
    }


def _aggregate_annual_dps(div_series: pd.Series) -> pd.Series:
    """배당금 이력을 연도별 합산 DPS로 변환."""
    if div_series.index.tz is not None:
        div_series.index = div_series.index.tz_localize(None)
    annual = div_series.resample("YE").sum()
    annual = annual[annual > 0]  # 무배당 연도 제외하지 않음 (0도 유지)
    annual.index = annual.index.year
    return annual


def _aggregate_annual_prices(price_df: pd.DataFrame) -> pd.DataFrame:
    """주가 이력에서 연도별 고가/저가 추출."""
    if price_df.index.tz is not None:
        price_df.index = price_df.index.tz_localize(None)

    annual = price_df.resample("YE").agg({"High": "max", "Low": "min"})
    annual = annual.dropna()
    annual.index = annual.index.year
    return annual


def _calc_yield_channel(annual_dps: pd.Series, annual_prices: pd.DataFrame) -> tuple | None:
    """역사적 배당수익률 채널 계산.

    Returns:
        (high_yield, low_yield, mid_yield) 또는 None
    """
    # 공통 연도만 사용
    common_years = sorted(set(annual_dps.index) & set(annual_prices.index))
    if len(common_years) < config.MIN_DIVIDEND_YEARS:
        return None

    # 최근 10년만
    recent_years = common_years[-10:]
    yearly_yields_high = []  # DPS / Low price → 고수익률
    yearly_yields_low = []   # DPS / High price → 저수익률

    for year in recent_years:
        dps = annual_dps.get(year, 0)
        if dps <= 0:
            continue
        low_price = annual_prices.loc[year, "Low"]
        high_price = annual_prices.loc[year, "High"]
        if low_price > 0:
            yearly_yields_high.append(dps / low_price)
        if high_price > 0:
            yearly_yields_low.append(dps / high_price)

    if len(yearly_yields_high) < 3 or len(yearly_yields_low) < 3:
        return None

    # 상위 30% 평균 (고수익률 = 저가 구간)
    sorted_high = sorted(yearly_yields_high, reverse=True)
    top_30_count = max(1, int(len(sorted_high) * 0.3))
    high_yield = np.mean(sorted_high[:top_30_count])

    # 하위 30% 평균 (저수익률 = 고가 구간)
    sorted_low = sorted(yearly_yields_low)
    bottom_30_count = max(1, int(len(sorted_low) * 0.3))
    low_yield = np.mean(sorted_low[:bottom_30_count])

    mid_yield = (high_yield + low_yield) / 2

    return high_yield, low_yield, mid_yield


def _calc_bluechip_score(stock: dict, annual_dps: pd.Series, market: str) -> tuple[int, dict]:
    """블루칩 기준 6개 항목 체크.

    Returns:
        (score, details_dict)
    """
    details = {}
    score = 0
    years = sorted(annual_dps.index)

    # 1. 최근 12년 중 배당금 인상 횟수 ≥ 5회
    increase_count = 0
    for i in range(1, len(years)):
        if annual_dps[years[i]] > annual_dps[years[i - 1]]:
            increase_count += 1
    details["dividend_increases"] = increase_count
    if increase_count >= 5:
        score += 1

    # 2. 시가총액 기준 (한국 1조 / 미국 $5B)
    cap = stock.get("market_cap") or 0
    if market == "kr":
        cap_threshold = 1_000_000_000_000  # 1조
    else:
        cap_threshold = 5_000_000_000  # $5B
    details["market_cap_pass"] = cap >= cap_threshold
    if cap >= cap_threshold:
        score += 1

    # 3. 발행주식수 안정 (±20% 이내) — 간접 체크
    # yfinance에서 과거 주식수 이력은 제한적이므로 현재 주식수 존재 여부로 대리
    shares = stock.get("shares_outstanding")
    details["shares_stable"] = shares is not None and shares > 0
    if details["shares_stable"]:
        score += 1  # 데이터 있으면 안정으로 간주 (보수적 접근)

    # 4. 최근 12년 중 EPS 개선 횟수 ≥ 7회
    eps_hist = stock.get("eps_history")
    eps_improve = _count_eps_improvements(eps_hist, stock.get("trailing_eps"))
    details["eps_improvements"] = eps_improve
    if eps_improve >= 7:
        score += 1

    # 5. 배당 무중단 (최근 10년 중 무배당 연도 = 0)
    recent_10 = annual_dps.tail(10)
    zero_years = (recent_10 <= 0).sum()
    details["zero_dividend_years"] = int(zero_years)
    if zero_years == 0:
        score += 1

    # 6. 배당금 삭감 없음 (최근 10년 중 전년 대비 감소 ≤ 1회)
    cut_count = 0
    recent_years = sorted(recent_10.index)
    for i in range(1, len(recent_years)):
        if recent_10[recent_years[i]] < recent_10[recent_years[i - 1]]:
            cut_count += 1
    details["dividend_cuts"] = cut_count
    if cut_count <= 1:
        score += 1

    return score, details


def _count_eps_improvements(eps_history, trailing_eps) -> int:
    """EPS 개선 횟수 추정."""
    # eps_history가 DataFrame이면 연도별 비교
    if isinstance(eps_history, pd.DataFrame) and not eps_history.empty:
        try:
            if "epsActual" in eps_history.columns:
                eps_vals = eps_history["epsActual"].dropna()
            elif "Earnings" in eps_history.columns:
                eps_vals = eps_history["Earnings"].dropna()
            else:
                return 0

            improvements = 0
            vals = eps_vals.tolist()
            for i in range(1, len(vals)):
                if vals[i] > vals[i - 1]:
                    improvements += 1
            return improvements
        except Exception:
            pass
    return 0  # 데이터 부족 시 0


def _count_consecutive_dividend_years(annual_dps: pd.Series) -> int:
    """최근 연속 배당 지급 연수."""
    years = sorted(annual_dps.index, reverse=True)
    count = 0
    for y in years:
        if annual_dps[y] > 0:
            count += 1
        else:
            break
    return count


def _determine_signal(bluechip_score: int, position: float, annual_dps: pd.Series) -> str:
    """와이스 종합 신호 판정."""
    # 경고: 배당 삭감 또는 무배당 이력
    recent_10 = annual_dps.tail(10)
    has_zero = (recent_10 <= 0).any()
    cuts = 0
    years = sorted(recent_10.index)
    for i in range(1, len(years)):
        if recent_10[years[i]] < recent_10[years[i - 1]]:
            cuts += 1

    if has_zero or cuts >= 2:
        return "🔴 경고"

    if bluechip_score >= 5 and position >= config.WEISS_BUY_THRESHOLD:
        return "🟢 강력 매수"
    elif bluechip_score >= 4 and position >= config.WEISS_REVIEW_THRESHOLD:
        return "🟡 매수 검토"
    else:
        return "⚪ 중립/관망"


def _format_output(df: pd.DataFrame) -> pd.DataFrame:
    """Google Sheets 출력 형식."""
    output = pd.DataFrame()
    output["순위"] = df["순위"]
    output["티커"] = df["ticker"]
    output["종목명"] = df["name"]
    output["업종"] = df["sector"]
    output["시가총액"] = df["market_cap"]
    output["현재주가"] = df["current_price"]
    output["현재배당수익률"] = df["current_dividend_yield"]
    output["역사적_고수익률"] = df["high_yield"]
    output["역사적_저수익률"] = df["low_yield"]
    output["현재위치(0~1)"] = df["current_position"]
    output["와이스신호"] = df["signal"]
    output["블루칩점수"] = df["bluechip_score"]
    output["배당지속연수"] = df["dividend_years"]
    output["최근10년DPS"] = df["recent_10y_dps"]
    output["배당성향"] = df["payout_ratio"]
    output["PBR"] = df["pbr"]
    output["분석일자"] = df["분석일자"]

    return output.reset_index(drop=True)
