"""매수/매도 시그널 판단 모듈.

기술적 지표를 종합하여 5단계 시그널과 10점 만점 점수를 산출합니다.
"""

from __future__ import annotations

import config


# 시그널 레이블 정의
SIGNAL_LABELS = {
    "strong_buy": "🟢강한매수",
    "buy": "🔵매수고려",
    "neutral": "⚪중립",
    "sell": "🟡매도고려",
    "strong_sell": "🔴강한매도",
}


def _score_rsi(rsi: float | None) -> float:
    """RSI 기반 점수 (0~1). 1에 가까울수록 매수 시그널."""
    if rsi is None:
        return 0.5  # 데이터 없으면 중립
    if rsi <= config.RSI_OVERSOLD:
        return 1.0  # 과매도 → 매수 기회
    if rsi >= config.RSI_OVERBOUGHT:
        return 0.0  # 과매수 → 매도 시그널
    # 30~70 구간: 선형 보간 (50이 중립)
    return 1.0 - (rsi - config.RSI_OVERSOLD) / (
        config.RSI_OVERBOUGHT - config.RSI_OVERSOLD
    )


def _score_macd(macd_data: dict) -> float:
    """MACD 기반 점수 (0~1)."""
    score = 0.5  # 기본 중립

    if macd_data.get("golden_cross"):
        score = 1.0
    elif macd_data.get("dead_cross"):
        score = 0.0
    elif macd_data.get("direction") == "상승":
        score = 0.7
    elif macd_data.get("direction") == "하락":
        score = 0.3

    return score


def _score_bollinger(bb_data: dict) -> float:
    """볼린저밴드 기반 점수 (0~1)."""
    position = bb_data.get("position", "N/A")

    scores = {
        "하단이탈": 1.0,    # 과매도 반등 기대
        "하단근접": 0.8,
        "중앙아래": 0.6,
        "중앙위": 0.4,
        "상단근접": 0.2,
        "상단돌파": 0.0,    # 과매수
    }
    return scores.get(position, 0.5)


def _score_ma60(current_price: float, ma60: float | None) -> float:
    """60일 이동평균선 대비 가격 위치 점수 (0~1)."""
    if ma60 is None or ma60 == 0:
        return 0.5
    ratio = current_price / ma60
    if ratio >= 1.05:
        return 0.8  # 60일선 위 5% 이상 → 상승 추세
    if ratio >= 1.0:
        return 0.65
    if ratio >= 0.95:
        return 0.35
    return 0.2  # 60일선 아래 5% 이상 → 하락 추세


def _score_volume(volume_data: dict, is_bullish: bool) -> float:
    """거래량 기반 점수 (0~1)."""
    ratio = volume_data.get("volume_ratio", 0)
    is_surge = volume_data.get("is_surge", False)

    if not is_surge:
        return 0.5  # 평범한 거래량은 중립

    # 거래량 급증 시: 상승 동반이면 매수, 하락 동반이면 매도
    if is_bullish:
        return min(0.5 + ratio * 0.15, 1.0)
    return max(0.5 - ratio * 0.15, 0.0)


def generate_signal(
    analysis: dict, current_price: float, prev_price: float
) -> dict:
    """기술적 분석 결과를 종합하여 시그널을 생성합니다.

    Args:
        analysis: technical_analysis.run_full_analysis()의 결과
        current_price: 현재 종가
        prev_price: 전일 종가

    Returns:
        {"signal": str, "score": float, "details": dict}
    """
    is_bullish = current_price >= prev_price

    # 각 지표별 점수 계산
    scores = {
        "rsi": _score_rsi(analysis.get("rsi")),
        "macd": _score_macd(analysis.get("macd", {})),
        "bollinger": _score_bollinger(analysis.get("bollinger", {})),
        "ma60": _score_ma60(
            current_price,
            analysis.get("moving_averages", {}).get("ma60"),
        ),
        "volume": _score_volume(analysis.get("volume", {}), is_bullish),
    }

    # 가중 평균 계산
    weights = config.SIGNAL_WEIGHTS
    total_weight = sum(weights.values())
    weighted_sum = sum(scores[k] * weights[k] for k in scores)
    normalized_score = (weighted_sum / total_weight) * 10  # 0~10 점수

    # 5단계 시그널 판단
    if normalized_score >= 8.0:
        signal_key = "strong_buy"
    elif normalized_score >= 6.0:
        signal_key = "buy"
    elif normalized_score >= 4.0:
        signal_key = "neutral"
    elif normalized_score >= 2.0:
        signal_key = "sell"
    else:
        signal_key = "strong_sell"

    return {
        "signal": SIGNAL_LABELS[signal_key],
        "signal_key": signal_key,
        "score": round(normalized_score, 1),
        "details": scores,
    }
