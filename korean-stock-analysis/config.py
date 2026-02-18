"""설정 및 환경변수 관리."""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env 파일 로딩
load_dotenv(Path(__file__).parent / ".env")

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"
)

# Google Sheets 시트 이름
INPUT_SHEET_NAME = os.getenv("INPUT_SHEET_NAME", "INPUT")

# 분석 파라미터
LOOKBACK_DAYS = 120
MA_PERIODS = [5, 20, 60, 120]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
VOLUME_AVG_PERIOD = 20

# Claude API 모델
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# 시그널 임계값
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# 시그널 가중치 (총합 10점 만점으로 환산)
SIGNAL_WEIGHTS = {
    "rsi": 2.0,
    "macd": 2.0,
    "bollinger": 2.0,
    "ma60": 2.0,
    "volume": 2.0,
}
