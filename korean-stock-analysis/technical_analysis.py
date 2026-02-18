"""기술적 분석 모듈.

이동평균선, RSI, MACD, 볼린저밴드, 거래량 분석을 수행합니다.
"""

import logging

import pandas as pd
import ta

import config

logger = logging.getLogger(__name__)


def calculate_moving_averages(df: pd.DataFrame) -> dict:
    """이동평균선을 계산합니다.

    Returns:
        {"ma5": float, "ma20": float, "ma60": float, "ma120": float,
         "golden_cross": bool, "dead_cross": bool}
    """
    result = {}
    close = df["close"]

    for period in config.MA_PERIODS:
        col_name = f"ma{period}"
        if len(close) >= period:
            ma = close.rolling(window=period).mean()
            result[col_name] = round(float(ma.iloc[-1]), 2) if pd.notna(ma.iloc[-1]) else None
        else:
            result[col_name] = None

    # 골든크로스/데드크로스 (5일선과 20일선 기준)
    result["golden_cross"] = False
    result["dead_cross"] = False

    if len(close) >= 21:
        ma5 = close.rolling(window=5).mean()
        ma20 = close.rolling(window=20).mean()
        if pd.notna(ma5.iloc[-1]) and pd.notna(ma20.iloc[-1]):
            if pd.notna(ma5.iloc[-2]) and pd.notna(ma20.iloc[-2]):
                prev_diff = ma5.iloc[-2] - ma20.iloc[-2]
                curr_diff = ma5.iloc[-1] - ma20.iloc[-1]
                if prev_diff <= 0 and curr_diff > 0:
                    result["golden_cross"] = True
                elif prev_diff >= 0 and curr_diff < 0:
                    result["dead_cross"] = True

    return result


def calculate_rsi(df: pd.DataFrame, period: int = config.RSI_PERIOD) -> float | None:
    """RSI(상대강도지수)를 계산합니다."""
    if len(df) < period + 1:
        return None
    try:
        rsi = ta.momentum.RSIIndicator(df["close"], window=period)
        val = rsi.rsi().iloc[-1]
        return round(float(val), 2) if pd.notna(val) else None
    except Exception:
        logger.exception("RSI 계산 실패")
        return None


def calculate_macd(
    df: pd.DataFrame,
    fast: int = config.MACD_FAST,
    slow: int = config.MACD_SLOW,
    signal: int = config.MACD_SIGNAL,
) -> dict:
    """MACD를 계산합니다.

    Returns:
        {"macd": float, "signal": float, "histogram": float,
         "direction": str ("상승"/"하락"/"N/A"),
         "golden_cross": bool, "dead_cross": bool}
    """
    result = {
        "macd": None,
        "signal": None,
        "histogram": None,
        "direction": "N/A",
        "golden_cross": False,
        "dead_cross": False,
    }

    if len(df) < slow + signal:
        return result

    try:
        macd_ind = ta.trend.MACD(
            df["close"], window_fast=fast, window_slow=slow, window_sign=signal
        )
        macd_line = macd_ind.macd()
        signal_line = macd_ind.macd_signal()
        hist = macd_ind.macd_diff()

        if pd.notna(macd_line.iloc[-1]):
            result["macd"] = round(float(macd_line.iloc[-1]), 2)
        if pd.notna(signal_line.iloc[-1]):
            result["signal"] = round(float(signal_line.iloc[-1]), 2)
        if pd.notna(hist.iloc[-1]):
            result["histogram"] = round(float(hist.iloc[-1]), 2)

        # MACD 방향 판단
        if len(hist) >= 2 and pd.notna(hist.iloc[-1]) and pd.notna(hist.iloc[-2]):
            result["direction"] = "상승" if hist.iloc[-1] > hist.iloc[-2] else "하락"

        # MACD 골든/데드크로스
        if len(macd_line) >= 2 and len(signal_line) >= 2:
            prev_diff = macd_line.iloc[-2] - signal_line.iloc[-2]
            curr_diff = macd_line.iloc[-1] - signal_line.iloc[-1]
            if pd.notna(prev_diff) and pd.notna(curr_diff):
                if prev_diff <= 0 and curr_diff > 0:
                    result["golden_cross"] = True
                elif prev_diff >= 0 and curr_diff < 0:
                    result["dead_cross"] = True

    except Exception:
        logger.exception("MACD 계산 실패")

    return result


def calculate_bollinger_bands(
    df: pd.DataFrame,
    period: int = config.BB_PERIOD,
    std_dev: int = config.BB_STD,
) -> dict:
    """볼린저밴드를 계산합니다.

    Returns:
        {"upper": float, "middle": float, "lower": float,
         "position": str ("상단돌파"/"상단근접"/"중앙위"/"중앙아래"/"하단근접"/"하단이탈"),
         "pct_b": float (0~1 범위, 0=하단, 1=상단)}
    """
    result = {
        "upper": None,
        "middle": None,
        "lower": None,
        "position": "N/A",
        "pct_b": None,
    }

    if len(df) < period:
        return result

    try:
        bb = ta.volatility.BollingerBands(
            df["close"], window=period, window_dev=std_dev
        )
        upper = bb.bollinger_hband().iloc[-1]
        middle = bb.bollinger_mavg().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        pct_b = bb.bollinger_pband().iloc[-1]

        if pd.notna(upper):
            result["upper"] = round(float(upper), 2)
        if pd.notna(middle):
            result["middle"] = round(float(middle), 2)
        if pd.notna(lower):
            result["lower"] = round(float(lower), 2)
        if pd.notna(pct_b):
            result["pct_b"] = round(float(pct_b), 4)

        # 위치 판단
        current_price = float(df["close"].iloc[-1])
        if pd.notna(upper) and pd.notna(lower):
            band_width = upper - lower
            if band_width > 0:
                if current_price > upper:
                    result["position"] = "상단돌파"
                elif current_price > upper - band_width * 0.1:
                    result["position"] = "상단근접"
                elif current_price > middle:
                    result["position"] = "중앙위"
                elif current_price > lower + band_width * 0.1:
                    result["position"] = "중앙아래"
                elif current_price > lower:
                    result["position"] = "하단근접"
                else:
                    result["position"] = "하단이탈"

    except Exception:
        logger.exception("볼린저밴드 계산 실패")

    return result


def calculate_volume_analysis(
    df: pd.DataFrame, avg_period: int = config.VOLUME_AVG_PERIOD
) -> dict:
    """거래량 분석을 수행합니다.

    Returns:
        {"current_volume": int, "avg_volume": float,
         "volume_ratio": float, "is_surge": bool}
    """
    result = {
        "current_volume": 0,
        "avg_volume": 0,
        "volume_ratio": 0,
        "is_surge": False,
    }

    if len(df) < avg_period + 1 or "volume" not in df.columns:
        return result

    try:
        current_vol = float(df["volume"].iloc[-1])
        avg_vol = float(df["volume"].iloc[-(avg_period + 1) : -1].mean())

        result["current_volume"] = int(current_vol)
        result["avg_volume"] = round(avg_vol, 0)
        result["volume_ratio"] = (
            round(current_vol / avg_vol, 2) if avg_vol > 0 else 0
        )
        result["is_surge"] = result["volume_ratio"] >= 2.0

    except Exception:
        logger.exception("거래량 분석 실패")

    return result


def run_full_analysis(df: pd.DataFrame) -> dict:
    """종목에 대한 전체 기술적 분석을 실행합니다.

    Returns:
        모든 기술적 지표를 포함한 딕셔너리
    """
    return {
        "moving_averages": calculate_moving_averages(df),
        "rsi": calculate_rsi(df),
        "macd": calculate_macd(df),
        "bollinger": calculate_bollinger_bands(df),
        "volume": calculate_volume_analysis(df),
    }
