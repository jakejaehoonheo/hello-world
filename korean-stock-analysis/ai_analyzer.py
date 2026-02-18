"""Claude API 연동 모듈.

종목 분석 요약과 자연어 쿼리 응답을 처리합니다.
"""

import json
import logging

import anthropic

import config

logger = logging.getLogger(__name__)


def _get_client() -> anthropic.Anthropic:
    """Anthropic 클라이언트를 생성합니다."""
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _format_analysis_context(
    ticker: str,
    name: str,
    price_info: dict,
    fundamental: dict,
    analysis: dict,
    signal: dict,
) -> str:
    """분석 데이터를 Claude에 전달할 컨텍스트 문자열로 변환합니다."""
    ma = analysis.get("moving_averages", {})
    macd = analysis.get("macd", {})
    bb = analysis.get("bollinger", {})
    vol = analysis.get("volume", {})

    return f"""## 종목 정보
- 종목코드: {ticker}
- 종목명: {name}
- 현재가: {price_info.get('current_price', 'N/A'):,}원
- 전일대비: {price_info.get('change_pct', 'N/A')}%

## 펀더멘털
- PER: {fundamental.get('per', 'N/A')}
- PBR: {fundamental.get('pbr', 'N/A')}
- 배당수익률: {fundamental.get('dividend_yield', 'N/A')}%
- 시가총액: {fundamental.get('market_cap', 'N/A')}

## 기술적 분석
- 이동평균선: 5일={ma.get('ma5')}, 20일={ma.get('ma20')}, 60일={ma.get('ma60')}, 120일={ma.get('ma120')}
- 골든크로스: {ma.get('golden_cross')}, 데드크로스: {ma.get('dead_cross')}
- RSI(14): {analysis.get('rsi', 'N/A')}
- MACD: {macd.get('macd')}, 시그널: {macd.get('signal')}, 히스토그램: {macd.get('histogram')}
- MACD 방향: {macd.get('direction')}, 골든크로스: {macd.get('golden_cross')}, 데드크로스: {macd.get('dead_cross')}
- 볼린저밴드: 상단={bb.get('upper')}, 중앙={bb.get('middle')}, 하단={bb.get('lower')}
- 볼린저밴드 위치: {bb.get('position')}, %B={bb.get('pct_b')}
- 거래량: {vol.get('current_volume'):,}, 20일 평균: {vol.get('avg_volume', 0):,.0f}
- 거래량 비율: {vol.get('volume_ratio')}배, 급증여부: {vol.get('is_surge')}

## 종합 시그널
- 판정: {signal.get('signal')}
- 종합점수: {signal.get('score')}/10
- 세부점수: {json.dumps(signal.get('details', {}), ensure_ascii=False)}
"""


def get_ai_summary(
    ticker: str,
    name: str,
    price_info: dict,
    fundamental: dict,
    analysis: dict,
    signal: dict,
) -> str:
    """Claude API를 사용하여 종목 분석 3줄 요약을 생성합니다.

    Returns:
        한국어 3줄 요약 문자열
    """
    context = _format_analysis_context(
        ticker, name, price_info, fundamental, analysis, signal
    )

    try:
        client = _get_client()
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": f"""다음 한국 주식 종목의 기술적 분석 데이터를 바탕으로,
개인 투자자가 이해하기 쉬운 한국어 3줄 요약을 작성해주세요.

요약 규칙:
1. 첫 줄: 현재 추세 판단 (상승/하락/횡보 + 핵심 근거)
2. 둘째 줄: 주요 기술적 시그널 요약
3. 셋째 줄: 단기 전망 및 주의사항

각 줄은 50자 이내로 간결하게 작성하세요. 줄 구분은 " | "로 해주세요.

{context}""",
                }
            ],
        )
        return response.content[0].text.strip()
    except Exception:
        logger.exception("AI 요약 생성 실패 (종목: %s)", ticker)
        return "AI 분석 요약 생성 실패"


def answer_query(
    query: str,
    ticker: str,
    name: str,
    price_info: dict,
    fundamental: dict,
    analysis: dict,
    signal: dict,
) -> str:
    """사용자의 자연어 쿼리에 대해 Claude API로 답변합니다.

    Args:
        query: 사용자의 자연어 질문 (INPUT 시트 C열)
        ticker, name, ...: 해당 종목의 분석 데이터

    Returns:
        한국어 답변 문자열
    """
    context = _format_analysis_context(
        ticker, name, price_info, fundamental, analysis, signal
    )

    # 시장 전반 질문인지 확인
    market_keywords = [
        "시장", "코스피", "코스닥", "공포", "탐욕", "전체", "지수",
        "fear", "greed", "market",
    ]
    is_market_query = any(kw in query.lower() for kw in market_keywords)

    system_prompt = """당신은 한국 주식 시장 분석 전문가입니다.
개인 투자자의 질문에 데이터 기반으로 명확하고 간결하게 답변하세요.
답변은 한국어로, 200자 이내로 작성하세요.
투자 판단은 사용자의 몫임을 항상 유의하세요."""

    user_message = f"""질문: {query}

"""
    if is_market_query:
        user_message += """이 질문은 시장 전반에 대한 것입니다.
현재 보유한 종목 데이터를 기반으로 답변하되,
시장 전체에 대한 정보는 제한적임을 알려주세요.

"""
    user_message += f"""참고할 종목 데이터:
{context}"""

    try:
        client = _get_client()
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    except Exception:
        logger.exception("쿼리 답변 실패 (종목: %s, 쿼리: %s)", ticker, query)
        return f"질문 '{query}'에 대한 답변 생성 실패"
