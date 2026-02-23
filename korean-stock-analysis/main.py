"""메인 오케스트레이터.

전체 분석 파이프라인을 실행합니다:
1. Google Sheets INPUT 시트에서 종목 목록 읽기
2. 각 종목별 데이터 수집 + 기술적 분석 + 시그널 판단
3. Claude API로 AI 요약 및 자연어 쿼리 응답
4. 결과를 날짜별 OUTPUT 시트에 기록
"""

import logging
import sys
import time
from datetime import datetime

import config
import data_collector
import technical_analysis
import signal_generator
import magic_formula
import dividend_analysis
import ai_analyzer
import sheets_manager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def get_market_summary() -> str:
    """시장 전체 요약 문자열을 생성합니다."""
    parts = []

    # 코스피
    kospi = data_collector.get_market_index("1001")
    if kospi:
        parts.append(
            f"코스피 {kospi['close']:,.2f} ({kospi['change_pct']:+.2f}%)"
        )

    # 코스닥
    kosdaq = data_collector.get_market_index("2001")
    if kosdaq:
        parts.append(
            f"코스닥 {kosdaq['close']:,.2f} ({kosdaq['change_pct']:+.2f}%)"
        )

    return " | ".join(parts) if parts else "시장 지수 조회 실패"


def analyze_stock(stock: dict) -> dict:
    """단일 종목에 대한 전체 분석을 수행합니다.

    Args:
        stock: {"ticker": str, "name": str, "query": str}

    Returns:
        OUTPUT 시트에 기록할 결과 딕셔너리
    """
    ticker = stock["ticker"]
    name = stock["name"]
    query = stock["query"]

    logger.info("분석 시작: %s (%s)", name, ticker)

    # 1. 데이터 수집
    ohlcv = data_collector.get_ohlcv(ticker)
    if ohlcv.empty:
        logger.warning("OHLCV 데이터 없음, 스킵: %s", ticker)
        return {
            "ticker": ticker,
            "name": name,
            "current_price": 0,
            "change_pct": 0,
            "signal": "⚪중립",
            "rsi": "N/A",
            "macd_direction": "N/A",
            "bb_position": "N/A",
            "volume_ratio": 0,
            "score": 5.0,
            "ai_summary": "데이터 조회 실패",
            "query_answer": "",
        }

    fundamental = data_collector.get_fundamental(ticker)
    price_info = data_collector.get_current_price_info(ticker, ohlcv)

    # 2. 기술적 분석
    analysis = technical_analysis.run_full_analysis(ohlcv)

    # 3. 시그널 생성
    current_price = price_info["current_price"]
    prev_price = float(ohlcv["close"].iloc[-2]) if len(ohlcv) >= 2 else current_price
    signal = signal_generator.generate_signal(analysis, current_price, prev_price)

    # 3.5. 매직포뮬러 분석
    mf = magic_formula.calculate_magic_formula(fundamental)

    # 3.6. 배당 분석 (배당은 거짓말하지 않는다)
    hist_yields = data_collector.get_historical_dividend_yields(ticker)
    div = dividend_analysis.analyze_dividend_signal(
        fundamental.get("dividend_yield"), hist_yields
    )

    # 4. AI 분석 요약
    ai_summary = ai_analyzer.get_ai_summary(
        ticker, name, price_info, fundamental, analysis, signal, mf, div
    )

    # 5. 자연어 쿼리 처리
    query_answer = ""
    if query:
        query_answer = ai_analyzer.answer_query(
            query, ticker, name, price_info, fundamental, analysis, signal, mf, div
        )

    result = {
        "ticker": ticker,
        "name": name,
        "current_price": price_info["current_price"],
        "change_pct": price_info["change_pct"],
        "signal": signal["signal"],
        "rsi": analysis.get("rsi", "N/A"),
        "macd_direction": analysis.get("macd", {}).get("direction", "N/A"),
        "bb_position": analysis.get("bollinger", {}).get("position", "N/A"),
        "volume_ratio": analysis.get("volume", {}).get("volume_ratio", 0),
        "score": signal["score"],
        "earnings_yield": mf.get("earnings_yield"),
        "ey_grade": mf.get("ey_grade", "N/A"),
        "roe": mf.get("roe"),
        "roe_grade": mf.get("roe_grade", "N/A"),
        "magic_score": mf.get("magic_score"),
        "magic_grade": mf.get("magic_grade", "N/A"),
        "current_yield": div.get("current_yield"),
        "yield_high": div.get("yield_high"),
        "yield_low": div.get("yield_low"),
        "yield_avg": div.get("yield_avg"),
        "yield_position": div.get("yield_position"),
        "dividend_signal": div.get("dividend_signal", "N/A"),
        "dividend_grade": div.get("dividend_grade", "N/A"),
        "ai_summary": ai_summary,
        "query_answer": query_answer,
    }

    logger.info(
        "분석 완료: %s → %s (점수: %s/10)",
        name,
        signal["signal"],
        signal["score"],
    )
    return result


def main():
    """메인 실행 함수."""
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("한국 주식 분석 시작: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    # 환경변수 검증
    if not config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        sys.exit(1)
    if not config.GOOGLE_SHEET_ID:
        logger.error("GOOGLE_SHEET_ID가 설정되지 않았습니다.")
        sys.exit(1)

    # 1. INPUT 시트에서 종목 목록 읽기
    try:
        stocks = sheets_manager.read_input_sheet()
    except Exception:
        logger.exception("INPUT 시트 읽기 실패")
        sys.exit(1)

    if not stocks:
        logger.warning("분석할 종목이 없습니다. INPUT 시트를 확인하세요.")
        sys.exit(0)

    logger.info("총 %d개 종목 분석 예정", len(stocks))

    # 2. 시장 요약 수집
    market_summary = get_market_summary()
    logger.info("시장 요약: %s", market_summary)

    # 3. 종목별 분석 실행
    results = []
    for i, stock in enumerate(stocks, 1):
        logger.info("[%d/%d] %s (%s)", i, len(stocks), stock["name"], stock["ticker"])
        try:
            result = analyze_stock(stock)
            results.append(result)
        except Exception:
            logger.exception("종목 분석 실패: %s", stock["ticker"])
            results.append(
                {
                    "ticker": stock["ticker"],
                    "name": stock["name"],
                    "current_price": 0,
                    "change_pct": 0,
                    "signal": "⚪중립",
                    "rsi": "N/A",
                    "macd_direction": "N/A",
                    "bb_position": "N/A",
                    "volume_ratio": 0,
                    "score": 5.0,
                    "ai_summary": "분석 실패",
                    "query_answer": "",
                }
            )

        # pykrx 요청 간 딜레이 (rate limit 방지)
        if i < len(stocks):
            time.sleep(1)

    # 4. 결과를 Google Sheets에 기록
    try:
        sheets_manager.write_output(results, market_summary)
        logger.info("Google Sheets 기록 완료")
    except Exception:
        logger.exception("Google Sheets 기록 실패")
        # 결과를 콘솔에 출력 (백업)
        logger.info("=== 분석 결과 (콘솔 백업) ===")
        for r in results:
            logger.info(
                "%s(%s): %s 점수=%s RSI=%s",
                r["name"],
                r["ticker"],
                r["signal"],
                r["score"],
                r["rsi"],
            )

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("분석 완료. 총 소요시간: %.1f초", elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
