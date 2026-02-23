"""
Stock Screening Automation - Google Sheets Writer
Saves screening results to Google Sheets with date-based worksheets.
"""

import logging
import os
from datetime import datetime

import gspread
import numpy as np
import pandas as pd
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client() -> gspread.Client:
    """Google Service Account 인증 후 gspread 클라이언트 반환."""
    creds_file = config.GOOGLE_CREDENTIALS_FILE
    if not os.path.exists(creds_file):
        raise FileNotFoundError(
            f"Google credentials 파일을 찾을 수 없습니다: {creds_file}\n"
            "README.md의 Google Service Account 설정 가이드를 참조하세요."
        )

    credentials = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    return gspread.authorize(credentials)


def get_or_create_spreadsheet(client: gspread.Client, year: int = None) -> gspread.Spreadsheet:
    """스프레드시트를 찾거나 없으면 자동 생성."""
    if year is None:
        year = datetime.now().year

    name = config.SPREADSHEET_NAME_TEMPLATE.format(year=year)

    try:
        spreadsheet = client.open(name)
        logger.info("기존 스프레드시트 열기: %s", name)
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(name)
        logger.info("새 스프레드시트 생성: %s", name)
        # 기본 Sheet1 삭제하지 않음 (첫 시트로 사용 가능)

    return spreadsheet


def save_results(
    mf_kr: pd.DataFrame | None = None,
    mf_us: pd.DataFrame | None = None,
    weiss_kr: pd.DataFrame | None = None,
    weiss_us: pd.DataFrame | None = None,
    summary: pd.DataFrame | None = None,
):
    """모든 결과를 Google Sheets에 저장."""
    client = get_gspread_client()
    spreadsheet = get_or_create_spreadsheet(client)
    today = datetime.now().strftime("%Y%m%d")

    sheets_to_write = []
    if mf_kr is not None and not mf_kr.empty:
        sheets_to_write.append((f"MF_한국_{today}", mf_kr))
    if mf_us is not None and not mf_us.empty:
        sheets_to_write.append((f"MF_미국_{today}", mf_us))
    if weiss_kr is not None and not weiss_kr.empty:
        sheets_to_write.append((f"Weiss_한국_{today}", weiss_kr))
    if weiss_us is not None and not weiss_us.empty:
        sheets_to_write.append((f"Weiss_미국_{today}", weiss_us))
    if summary is not None and not summary.empty:
        sheets_to_write.append((f"요약_{today}", summary))

    for sheet_name, df in sheets_to_write:
        _write_sheet(spreadsheet, sheet_name, df)

    logger.info("Google Sheets 저장 완료: %d개 시트", len(sheets_to_write))


def _write_sheet(spreadsheet: gspread.Spreadsheet, sheet_name: str, df: pd.DataFrame):
    """단일 시트에 DataFrame 저장 (batch_update 사용)."""
    # 시트 생성 또는 가져오기
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
        logger.debug("기존 시트 초기화: %s", sheet_name)
    except gspread.WorksheetNotFound:
        rows_needed = len(df) + 1  # 헤더 포함
        cols_needed = len(df.columns)
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=max(rows_needed, 100),
            cols=max(cols_needed, 20),
        )
        logger.debug("새 시트 생성: %s", sheet_name)

    # DataFrame → 2D 리스트 변환
    df_clean = _clean_for_sheets(df)
    header = df_clean.columns.tolist()
    values = df_clean.values.tolist()
    all_data = [header] + values

    # batch_update로 한 번에 쓰기 (API 할당량 절약)
    worksheet.update(all_data, value_input_option="USER_ENTERED")
    logger.info("시트 저장: %s (%d행)", sheet_name, len(values))


def _clean_for_sheets(df: pd.DataFrame) -> pd.DataFrame:
    """Google Sheets에 쓰기 위해 DataFrame 정리."""
    df = df.copy()

    for col in df.columns:
        # NaN/None → 빈 문자열
        df[col] = df[col].fillna("")

        # numpy 타입 → Python native 변환
        df[col] = df[col].apply(_to_native)

    return df


def _to_native(val):
    """numpy/pandas 타입을 Python native 타입으로 변환."""
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        if np.isnan(val) or np.isinf(val):
            return ""
        return float(val)
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    return val
