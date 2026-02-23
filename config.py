"""
Stock Screening Automation - Configuration
Adjustable parameters for Magic Formula and Weiss Dividend Analysis.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Market Cap Minimums ──────────────────────────────────────────────
KR_MIN_MARKET_CAP = int(os.getenv("KR_MIN_MARKET_CAP", 50_000_000_000))       # 500억 원
US_MIN_MARKET_CAP = int(os.getenv("US_MIN_MARKET_CAP", 500_000_000))           # $500M

# ── Magic Formula ────────────────────────────────────────────────────
MF_TOP_N = int(os.getenv("MF_TOP_N", 50))                                     # 상위 추출 수

# ── Weiss Dividend Analysis ──────────────────────────────────────────
WEISS_BUY_THRESHOLD = float(os.getenv("WEISS_BUY_THRESHOLD", 0.8))            # 매수 신호 임계값
WEISS_REVIEW_THRESHOLD = float(os.getenv("WEISS_REVIEW_THRESHOLD", 0.6))      # 매수 검토 임계값
BLUECHIP_MIN_SCORE = int(os.getenv("BLUECHIP_MIN_SCORE", 4))                  # 블루칩 최소 점수
MIN_DIVIDEND_YEARS = int(os.getenv("MIN_DIVIDEND_YEARS", 5))                  # 배당 이력 최소 연수

# ── Data Collection ──────────────────────────────────────────────────
MAX_WORKERS = int(os.getenv("MAX_WORKERS", 5))                                # 병렬 수집 workers
API_RETRY_COUNT = int(os.getenv("API_RETRY_COUNT", 3))                        # API 재시도 횟수
HISTORY_YEARS = int(os.getenv("HISTORY_YEARS", 12))                           # 배당/EPS 이력 연수

# ── Excluded Sectors ─────────────────────────────────────────────────
# 매직 포뮬라에서 제외할 업종 (Greenblatt 원칙)
KR_EXCLUDED_SECTORS = {
    "은행", "보험", "증권", "금융업", "금융", "기타금융",
    "유틸리티", "전기가스업", "전기·가스업",
}

US_EXCLUDED_SECTORS = {
    "Financial Services", "Banks", "Insurance", "Capital Markets",
    "Diversified Financial Services", "Consumer Finance",
    "Utilities", "Regulated Electric", "Gas Utilities",
    "Independent Power Producers", "Multi-Utilities",
}

# ── Google Sheets ────────────────────────────────────────────────────
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_NAME_TEMPLATE = "주식 스크리닝 결과 - {year}"

# ── Output ───────────────────────────────────────────────────────────
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
