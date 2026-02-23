"""Google Sheets 읽기/쓰기 모듈.

INPUT 시트에서 종목 목록을 읽고, 날짜별 OUTPUT 시트에 결과를 기록합니다.
"""

import logging
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_service():
    """Google Sheets API 서비스 객체를 생성합니다."""
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def read_input_sheet() -> list[dict]:
    """INPUT 시트에서 종목 목록을 읽어옵니다.

    Returns:
        [{"ticker": str, "name": str, "query": str}, ...]
    """
    service = _get_service()
    sheet = service.spreadsheets()

    # A~D열 읽기
    range_name = f"{config.INPUT_SHEET_NAME}!A2:D"
    result = (
        sheet.values()
        .get(spreadsheetId=config.GOOGLE_SHEET_ID, range=range_name)
        .execute()
    )
    rows = result.get("values", [])

    stocks = []
    for row in rows:
        if not row or not row[0].strip():
            continue

        ticker = row[0].strip().zfill(6)
        name = row[1].strip() if len(row) > 1 else ""
        query = row[2].strip() if len(row) > 2 else ""

        stocks.append({"ticker": ticker, "name": name, "query": query})

    logger.info("INPUT 시트에서 %d개 종목을 읽었습니다.", len(stocks))
    return stocks


def _get_or_create_output_sheet(service, date_str: str) -> str:
    """날짜 기반 OUTPUT 시트를 생성하거나 기존 시트를 반환합니다.

    Args:
        service: Sheets API 서비스 객체
        date_str: "20260217" 형식의 날짜 문자열

    Returns:
        시트 이름 (예: "20260217")
    """
    spreadsheet = (
        service.spreadsheets()
        .get(spreadsheetId=config.GOOGLE_SHEET_ID)
        .execute()
    )

    existing_sheets = [
        s["properties"]["title"] for s in spreadsheet.get("sheets", [])
    ]

    if date_str in existing_sheets:
        # 기존 시트 클리어
        sheet_id = None
        for s in spreadsheet.get("sheets", []):
            if s["properties"]["title"] == date_str:
                sheet_id = s["properties"]["sheetId"]
                break

        if sheet_id is not None:
            service.spreadsheets().batchUpdate(
                spreadsheetId=config.GOOGLE_SHEET_ID,
                body={
                    "requests": [
                        {
                            "updateCells": {
                                "range": {"sheetId": sheet_id},
                                "fields": "userEnteredValue",
                            }
                        }
                    ]
                },
            ).execute()
        logger.info("기존 시트 '%s'를 클리어했습니다.", date_str)
    else:
        # 새 시트 생성
        service.spreadsheets().batchUpdate(
            spreadsheetId=config.GOOGLE_SHEET_ID,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {"title": date_str}
                        }
                    }
                ]
            },
        ).execute()
        logger.info("새 시트 '%s'를 생성했습니다.", date_str)

    return date_str


def write_output(results: list[dict], market_summary: str) -> None:
    """분석 결과를 날짜별 OUTPUT 시트에 기록합니다.

    Args:
        results: 종목별 분석 결과 리스트
        market_summary: 시장 전체 요약 문자열
    """
    service = _get_service()
    date_str = datetime.now().strftime("%Y%m%d")
    sheet_name = _get_or_create_output_sheet(service, date_str)

    # 데이터 구성
    rows = []

    # 1행: 실행 시각 + 시장 요약
    execution_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
    rows.append([f"실행: {execution_time} | {market_summary}"])
    rows.append([])  # 빈 행

    # 3행: 헤더
    headers = [
        "종목코드",
        "종목명",
        "현재가",
        "전일대비%",
        "시그널",
        "RSI",
        "MACD방향",
        "볼밴위치",
        "거래량비율",
        "종합점수(10점)",
        "이익수익률(%)",
        "이익수익률등급",
        "자본수익률ROE(%)",
        "ROE등급",
        "매직포뮬러점수",
        "매직포뮬러등급",
        "배당수익률(%)",
        "배당수익률범위",
        "배당수익률위치(%)",
        "배당신호",
        "배당등급",
        "AI분석요약",
        "자연어쿼리답변",
    ]
    rows.append(headers)

    # 4행~: 종목 데이터
    for r in results:
        ey = r.get("earnings_yield")
        roe = r.get("roe")
        ms = r.get("magic_score")
        cy = r.get("current_yield")
        yh = r.get("yield_high")
        yl = r.get("yield_low")
        yp = r.get("yield_position")
        row = [
            r.get("ticker", ""),
            r.get("name", ""),
            f"{r.get('current_price', 0):,.0f}",
            f"{r.get('change_pct', 0):+.2f}%",
            r.get("signal", "⚪중립"),
            str(r.get("rsi", "N/A")),
            r.get("macd_direction", "N/A"),
            r.get("bb_position", "N/A"),
            f"{r.get('volume_ratio', 0):.2f}배",
            f"{r.get('score', 5.0):.1f}",
            f"{ey:.2f}" if ey is not None else "N/A",
            r.get("ey_grade", "N/A"),
            f"{roe:.2f}" if roe is not None else "N/A",
            r.get("roe_grade", "N/A"),
            f"{ms:.1f}" if ms is not None else "N/A",
            r.get("magic_grade", "N/A"),
            f"{cy:.2f}" if cy is not None else "N/A",
            f"{yl:.2f}~{yh:.2f}" if (yl is not None and yh is not None) else "N/A",
            f"{yp:.1f}" if yp is not None else "N/A",
            r.get("dividend_signal", "N/A"),
            r.get("dividend_grade", "N/A"),
            r.get("ai_summary", ""),
            r.get("query_answer", ""),
        ]
        rows.append(row)

    # 시트에 기록
    range_name = f"{sheet_name}!A1"
    service.spreadsheets().values().update(
        spreadsheetId=config.GOOGLE_SHEET_ID,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()

    logger.info(
        "시트 '%s'에 %d개 종목 결과를 기록했습니다.",
        sheet_name,
        len(results),
    )

    # 서식 적용 (헤더 볼드, 열 너비 조정)
    _apply_formatting(service, sheet_name, len(results))


def _apply_formatting(service, sheet_name: str, num_rows: int) -> None:
    """출력 시트에 기본 서식을 적용합니다."""
    try:
        spreadsheet = (
            service.spreadsheets()
            .get(spreadsheetId=config.GOOGLE_SHEET_ID)
            .execute()
        )
        sheet_id = None
        for s in spreadsheet.get("sheets", []):
            if s["properties"]["title"] == sheet_name:
                sheet_id = s["properties"]["sheetId"]
                break

        if sheet_id is None:
            return

        requests = [
            # 1행(시장 요약) 볼드
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True, "fontSize": 11}
                        }
                    },
                    "fields": "userEnteredFormat.textFormat",
                }
            },
            # 3행(헤더) 볼드 + 배경색
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 2,
                        "endRowIndex": 3,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.95,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            },
            # 열 너비 자동 조정
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 23,
                    }
                }
            },
        ]

        service.spreadsheets().batchUpdate(
            spreadsheetId=config.GOOGLE_SHEET_ID,
            body={"requests": requests},
        ).execute()

    except Exception:
        logger.exception("서식 적용 실패")
