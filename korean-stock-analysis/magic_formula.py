"""조엘 그린블라트 매직포뮬러 분석 모듈.

『주식시장을 이기는 작은 책』에서 소개된 두 가지 핵심 지표:
1. 이익수익률 (Earnings Yield) ≈ 1/PER — 투입 가격 대비 벌어들이는 이익
2. 자본수익률 (ROC/ROE) ≈ PBR/PER — 투입 자본 대비 벌어들이는 이익

매직포뮬러는 본래 전체 종목을 두 지표로 각각 순위 매긴 뒤
합산 순위가 높은 종목에 투자하는 전략입니다.
여기서는 개별 종목의 지표값을 등급으로 환산하여 제공합니다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _grade(value: float | None, thresholds: list[tuple[float, str]]) -> str:
    """값을 임계값 리스트와 비교하여 등급을 반환합니다.

    Args:
        value: 평가할 값
        thresholds: [(임계값, 등급), ...] 내림차순 정렬
    """
    if value is None:
        return "N/A"
    for threshold, grade in thresholds:
        if value >= threshold:
            return grade
    return thresholds[-1][1]


def calculate_magic_formula(fundamental: dict) -> dict:
    """매직포뮬러 지표를 계산합니다.

    Args:
        fundamental: {"per": float|None, "pbr": float|None, ...}

    Returns:
        {
            "earnings_yield": float|None,    # 이익수익률 (%)
            "ey_grade": str,                 # 이익수익률 등급
            "roe": float|None,               # 자본수익률 (%)
            "roe_grade": str,                # 자본수익률 등급
            "magic_score": float,            # 매직포뮬러 종합점수 (0~10)
            "magic_grade": str,              # 종합 등급
        }
    """
    per = fundamental.get("per")
    pbr = fundamental.get("pbr")

    result = {
        "earnings_yield": None,
        "ey_grade": "N/A",
        "roe": None,
        "roe_grade": "N/A",
        "magic_score": None,
        "magic_grade": "N/A",
    }

    # --- 이익수익률 (Earnings Yield = 1/PER × 100) ---
    if per is not None and per > 0:
        ey = (1.0 / per) * 100
        result["earnings_yield"] = round(ey, 2)
        result["ey_grade"] = _grade(ey, [
            (20.0, "★★★★★"),   # PER < 5
            (10.0, "★★★★"),    # PER 5~10
            (6.67, "★★★"),     # PER 10~15
            (4.0, "★★"),       # PER 15~25
            (0.0, "★"),        # PER > 25
        ])
    elif per is not None and per < 0:
        # 적자 기업
        result["earnings_yield"] = 0.0
        result["ey_grade"] = "적자"

    # --- 자본수익률 (ROE ≈ PBR/PER × 100) ---
    if per is not None and per > 0 and pbr is not None and pbr > 0:
        roe = (pbr / per) * 100
        result["roe"] = round(roe, 2)
        result["roe_grade"] = _grade(roe, [
            (20.0, "★★★★★"),   # ROE ≥ 20%
            (15.0, "★★★★"),    # ROE 15~20%
            (10.0, "★★★"),     # ROE 10~15%
            (5.0, "★★"),       # ROE 5~10%
            (0.0, "★"),        # ROE < 5%
        ])
    elif per is not None and per < 0:
        result["roe"] = 0.0
        result["roe_grade"] = "적자"

    # --- 매직포뮬러 종합점수 (0~10) ---
    ey = result["earnings_yield"]
    roe = result["roe"]

    if ey is not None and roe is not None and ey > 0 and roe > 0:
        # 이익수익률 점수 (0~5): EY 20%→5점, 0%→0점
        ey_score = min(ey / 20.0 * 5.0, 5.0)
        # 자본수익률 점수 (0~5): ROE 25%→5점, 0%→0점
        roe_score = min(roe / 25.0 * 5.0, 5.0)
        magic_score = round(ey_score + roe_score, 1)
        result["magic_score"] = magic_score

        result["magic_grade"] = _grade(magic_score, [
            (8.0, "매우 우수"),
            (6.0, "우수"),
            (4.0, "보통"),
            (2.0, "미흡"),
            (0.0, "부진"),
        ])
    elif ey is not None and ey <= 0:
        result["magic_score"] = 0.0
        result["magic_grade"] = "적자 기업"

    return result
