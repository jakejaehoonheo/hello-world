"""'배당은 거짓말하지 않는다' (Dividends Don't Lie) 배당 분석 모듈.

제랄딘 와이스(Geraldine Weiss)의 핵심 원리:
배당수익률의 역사적 범위 내 현재 위치를 통해
주가의 저평가/고평가 여부를 판단합니다.

- 배당수익률이 역사적 고점 근처 → 주가 저평가 (매수 구간)
- 배당수익률이 역사적 저점 근처 → 주가 고평가 (매도 구간)

원서 기준 핵심 신호:
1. 배당수익률이 역사적 고점 부근이면 매수 (주가가 싸다)
2. 배당수익률이 역사적 저점 부근이면 매도 (주가가 비싸다)
3. 꾸준히 배당을 지급하는 기업만 분석 대상
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def analyze_dividend_signal(
    current_yield: float | None,
    historical_yields: list[float],
) -> dict:
    """배당수익률 기반 가치 평가 분석.

    Args:
        current_yield: 현재 배당수익률 (%)
        historical_yields: 과거 배당수익률 리스트 (0보다 큰 값만)

    Returns:
        {
            "current_yield": float|None,
            "yield_high": float|None,      # 역사적 고점
            "yield_low": float|None,       # 역사적 저점
            "yield_avg": float|None,       # 역사적 평균
            "yield_position": float|None,  # 0~100 (0=고평가, 100=저평가)
            "dividend_signal": str,        # 저평가매수구간/적정가/고평가매도구간/무배당/데이터부족
            "dividend_grade": str,         # 등급
        }
    """
    result = {
        "current_yield": current_yield,
        "yield_high": None,
        "yield_low": None,
        "yield_avg": None,
        "yield_position": None,
        "dividend_signal": "N/A",
        "dividend_grade": "N/A",
    }

    # 배당 없는 종목
    if current_yield is None or current_yield <= 0:
        result["dividend_signal"] = "무배당"
        result["dividend_grade"] = "—"
        return result

    # 역사적 데이터 부족 (최소 6개월)
    if len(historical_yields) < 6:
        result["dividend_signal"] = "데이터부족"
        result["dividend_grade"] = "—"
        return result

    yield_high = max(historical_yields)
    yield_low = min(historical_yields)
    yield_avg = sum(historical_yields) / len(historical_yields)

    result["yield_high"] = round(yield_high, 2)
    result["yield_low"] = round(yield_low, 2)
    result["yield_avg"] = round(yield_avg, 2)

    # 배당수익률 위치 계산
    # 100 = 역사적 고점 (주가 저평가) → 매수 신호
    # 0   = 역사적 저점 (주가 고평가) → 매도 신호
    if yield_high == yield_low:
        position = 50.0
    else:
        position = ((current_yield - yield_low) / (yield_high - yield_low)) * 100
        position = max(0.0, min(100.0, position))

    result["yield_position"] = round(position, 1)

    # 와이스 방법론에 따른 신호 판단
    if position >= 80:
        result["dividend_signal"] = "저평가 매수구간"
        result["dividend_grade"] = "★★★★★"
    elif position >= 60:
        result["dividend_signal"] = "저평가 근접"
        result["dividend_grade"] = "★★★★"
    elif position >= 40:
        result["dividend_signal"] = "적정가"
        result["dividend_grade"] = "★★★"
    elif position >= 20:
        result["dividend_signal"] = "고평가 근접"
        result["dividend_grade"] = "★★"
    else:
        result["dividend_signal"] = "고평가 매도구간"
        result["dividend_grade"] = "★"

    return result
