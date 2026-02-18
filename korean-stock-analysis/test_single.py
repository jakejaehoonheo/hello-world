"""단일 종목 테스트 스크립트.

네트워크 없이 샘플 데이터로 분석 파이프라인을 검증합니다.
실제 환경에서는 pykrx로 실시간 데이터를 수집합니다.
"""

import logging
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

import technical_analysis
import signal_generator


TICKER = "005930"
NAME = "삼성전자"


def generate_sample_ohlcv(days: int = 120) -> pd.DataFrame:
    """삼성전자 실제 가격대 기반 샘플 OHLCV 데이터 생성.

    최근 실제 삼성전자 가격대(55,000~58,000원)를 참고하여
    현실적인 변동 패턴을 시뮬레이션합니다.
    """
    np.random.seed(42)
    dates = pd.bdate_range(end=datetime.now(), periods=days)

    # 기준가 55,000원에서 시작, 랜덤워크
    base_price = 55000
    returns = np.random.normal(0.0005, 0.015, days)
    # 최근 상승 추세 반영
    returns[-20:] += 0.002
    prices = base_price * np.cumprod(1 + returns)

    # OHLCV 생성
    close = prices
    high = close * (1 + np.abs(np.random.normal(0, 0.008, days)))
    low = close * (1 - np.abs(np.random.normal(0, 0.008, days)))
    open_ = close * (1 + np.random.normal(0, 0.005, days))
    volume = np.random.lognormal(mean=17.5, sigma=0.5, size=days).astype(int)
    # 최근 3일 거래량 급증
    volume[-3:] = (volume[-3:] * 2.5).astype(int)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
    return df


def main():
    ohlcv = generate_sample_ohlcv()

    print("=" * 60)
    print(f"  한국 주식 분석 테스트: {NAME} ({TICKER})")
    print(f"  실행: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  (샘플 데이터 사용 - 네트워크 없는 환경)")
    print("=" * 60)

    # 현재가 정보
    current_price = float(ohlcv["close"].iloc[-1])
    prev_price = float(ohlcv["close"].iloc[-2])
    change_pct = ((current_price - prev_price) / prev_price) * 100

    print(f"\n[ 가격 정보 ]")
    print(f"  현재가:    {current_price:>10,.0f}원")
    print(f"  전일대비:  {change_pct:>+10.2f}%")
    print(f"  데이터:    {len(ohlcv)}일 ({ohlcv.index[0].date()} ~ {ohlcv.index[-1].date()})")

    print(f"\n  최근 5일 종가:")
    for date, row in ohlcv.tail(5).iterrows():
        print(f"    {date.date()}: {row['close']:>10,.0f}원  (거래량: {row['volume']:>12,})")

    # 기술적 분석 실행
    print(f"\n{'=' * 60}")
    print("[ 기술적 분석 ]")
    print("=" * 60)
    analysis = technical_analysis.run_full_analysis(ohlcv)

    # 이동평균선
    ma = analysis["moving_averages"]
    print(f"\n  이동평균선:")
    for p in [5, 20, 60, 120]:
        val = ma.get(f"ma{p}")
        if val:
            diff = ((current_price - val) / val) * 100
            marker = "▲" if current_price > val else "▼"
            print(f"    MA{p:>3}: {val:>10,.0f}원  {marker} 현재가 {diff:+.1f}%")
        else:
            print(f"    MA{p:>3}: N/A")
    print(f"    골든크로스(5일/20일): {'⭐ 발생!' if ma['golden_cross'] else '없음'}")
    print(f"    데드크로스(5일/20일): {'⚠️  발생!' if ma['dead_cross'] else '없음'}")

    # RSI
    rsi = analysis["rsi"]
    rsi_bar = "█" * int(rsi / 5) + "░" * (20 - int(rsi / 5)) if rsi else ""
    rsi_status = "(과매도)" if rsi and rsi < 30 else "(과매수)" if rsi and rsi > 70 else "(중립)"
    print(f"\n  RSI(14): {rsi} {rsi_status}")
    if rsi:
        print(f"    [{'=' * int(rsi / 5)}{'·' * (20 - int(rsi / 5))}] 0 ← 과매도 | 과매수 → 100")

    # MACD
    macd = analysis["macd"]
    print(f"\n  MACD:")
    print(f"    MACD선:    {macd['macd']:>10}")
    print(f"    시그널선:  {macd['signal']:>10}")
    print(f"    히스토그램: {macd['histogram']:>10}")
    print(f"    방향: {macd['direction']}")
    if macd["golden_cross"]:
        print(f"    ⭐ MACD 골든크로스 발생!")
    if macd["dead_cross"]:
        print(f"    ⚠️  MACD 데드크로스 발생!")

    # 볼린저밴드
    bb = analysis["bollinger"]
    print(f"\n  볼린저밴드(20일, 2σ):")
    if bb["upper"]:
        print(f"    상단: {bb['upper']:>10,.0f}원")
        print(f"    중앙: {bb['middle']:>10,.0f}원")
        print(f"    하단: {bb['lower']:>10,.0f}원")
        print(f"    현재 위치: {bb['position']}")
        print(f"    %B: {bb['pct_b']} (0=하단, 0.5=중앙, 1=상단)")

    # 거래량
    vol = analysis["volume"]
    print(f"\n  거래량 분석:")
    print(f"    당일 거래량:  {vol['current_volume']:>12,}")
    print(f"    20일 평균:    {vol['avg_volume']:>12,.0f}")
    print(f"    비율: {vol['volume_ratio']}배 {'🔥 급증!' if vol['is_surge'] else ''}")

    # 시그널 판단
    print(f"\n{'=' * 60}")
    print("[ 매수/매도 시그널 판단 ]")
    print("=" * 60)
    signal = signal_generator.generate_signal(analysis, current_price, prev_price)

    print(f"\n  ┌─────────────────────────────────────┐")
    print(f"  │  종합 판정:  {signal['signal']:<16}        │")
    print(f"  │  종합 점수:  {signal['score']}/10                  │")
    print(f"  └─────────────────────────────────────┘")

    print(f"\n  세부 점수 (0.0=강한매도 ← 0.5=중립 → 1.0=강한매수):")
    labels = {
        "rsi": "RSI      ",
        "macd": "MACD     ",
        "bollinger": "볼린저밴드",
        "ma60": "60일이평선",
        "volume": "거래량   ",
    }
    for k, v in signal["details"].items():
        bar_len = int(v * 30)
        bar = "▓" * bar_len + "░" * (30 - bar_len)
        print(f"    {labels.get(k, k)}: [{bar}] {v:.2f}")

    # 최종 요약 (AI 요약 대신 규칙 기반 요약)
    print(f"\n{'=' * 60}")
    print("[ 분석 요약 ]")
    print("=" * 60)
    print(f"  종목: {NAME} ({TICKER})")
    print(f"  현재가: {current_price:,.0f}원 ({change_pct:+.2f}%)")
    print(f"  시그널: {signal['signal']} (점수: {signal['score']}/10)")

    summaries = []
    if rsi and rsi < 30:
        summaries.append("RSI 과매도 구간 → 반등 가능성")
    elif rsi and rsi > 70:
        summaries.append("RSI 과매수 구간 → 조정 주의")
    if macd["golden_cross"]:
        summaries.append("MACD 골든크로스 발생")
    if macd["dead_cross"]:
        summaries.append("MACD 데드크로스 발생")
    if vol["is_surge"]:
        summaries.append(f"거래량 {vol['volume_ratio']}배 급증")
    if ma.get("ma60") and current_price > ma["ma60"]:
        summaries.append("60일선 위 → 상승 추세")
    elif ma.get("ma60"):
        summaries.append("60일선 아래 → 하락 추세")

    for s in summaries:
        print(f"  • {s}")

    print(f"\n{'=' * 60}")
    print("  테스트 완료! 모든 분석 모듈이 정상 동작합니다.")
    print("  실제 환경에서는 pykrx로 실시간 데이터를 수집합니다.")
    print("=" * 60)


if __name__ == "__main__":
    main()
