# 주식 스크리닝 자동화 시스템

매직 포뮬라(Joel Greenblatt)와 와이스 배당 분석(Geraldine Weiss) 두 가지 방법론으로
한국(KOSPI/KOSDAQ) 및 미국(NYSE/NASDAQ) 주식을 자동 스크리닝하여
결과를 Google Sheets에 날짜별로 저장하는 Python 프로그램입니다.

## 기능

- **매직 포뮬라**: 이익수익률(Earnings Yield)과 투자자본수익률(ROC) 기반 종합 랭킹
- **와이스 배당 분석**: 역사적 배당수익률 채널과 블루칩 품질 점수 기반 매수 신호
- **교집합 분석**: 두 방법론 모두에서 긍정 신호인 종목 추출
- **Google Sheets 자동 저장**: 날짜별 시트로 결과 기록
- **CSV 백업**: 로컬 CSV 파일 자동 저장

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. Google Service Account 설정

Google Sheets에 결과를 저장하려면 Service Account를 설정해야 합니다.

#### 2-1. Google Cloud Console에서 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 새 프로젝트 생성 (또는 기존 프로젝트 선택)

#### 2-2. API 활성화

1. **APIs & Services** → **Library** 이동
2. **Google Sheets API** 검색 후 활성화
3. **Google Drive API** 검색 후 활성화

#### 2-3. Service Account 생성

1. **APIs & Services** → **Credentials** 이동
2. **Create Credentials** → **Service Account** 선택
3. 이름 입력 (예: `stock-screener`) → **Create**
4. Role은 생략 가능 → **Continue** → **Done**

#### 2-4. JSON 키 다운로드

1. 생성된 Service Account 클릭
2. **Keys** 탭 → **Add Key** → **Create new key**
3. **JSON** 선택 → **Create**
4. 다운로드된 파일을 프로젝트 루트에 `credentials.json`으로 저장

#### 2-5. 스프레드시트 공유

자동 생성된 스프레드시트를 사용하려면, Service Account 이메일
(예: `stock-screener@project-id.iam.gserviceaccount.com`)에
**편집자** 권한을 부여하세요. 또는 프로그램이 자동 생성하는 경우
Drive API 권한으로 자동 처리됩니다.

### 3. 환경 변수 (선택)

`.env` 파일을 생성하여 파라미터를 조정할 수 있습니다:

```env
# 시가총액 최소 기준
KR_MIN_MARKET_CAP=50000000000   # 500억 원
US_MIN_MARKET_CAP=500000000     # $500M

# 매직 포뮬라
MF_TOP_N=50                     # 상위 추출 수

# 와이스 배당
WEISS_BUY_THRESHOLD=0.8         # 매수 신호 임계값
BLUECHIP_MIN_SCORE=4            # 블루칩 최소 점수
MIN_DIVIDEND_YEARS=5            # 배당 이력 최소 연수

# 데이터 수집
MAX_WORKERS=5                   # 병렬 workers 수

# Google Sheets
GOOGLE_CREDENTIALS_FILE=credentials.json
```

## 사용법

```bash
# 전체 실행 (한국 + 미국, 매직 포뮬라 + 와이스)
python main.py

# 한국 시장만
python main.py --market kr

# 미국 시장만
python main.py --market us

# 매직 포뮬라만
python main.py --screener mf

# 와이스 배당 분석만
python main.py --screener weiss

# Google Sheets 저장 없이 콘솔/CSV만 출력
python main.py --dry-run

# 상세 로그 출력
python main.py --verbose
```

## 프로젝트 구조

```
├── main.py                  # 메인 실행 스크립트
├── config.py                # 설정 파라미터
├── data_collector.py        # 데이터 수집 (yfinance, pykrx, FDR)
├── sheets_writer.py         # Google Sheets 저장
├── screeners/
│   ├── __init__.py
│   ├── magic_formula.py     # 매직 포뮬라 스크리너
│   └── weiss_dividend.py    # 와이스 배당 분석 스크리너
├── output/                  # CSV 결과 저장 디렉토리
├── requirements.txt
├── .env                     # 환경 변수 (git 제외)
├── credentials.json         # Google 인증 (git 제외)
└── README.md
```

## 데이터 소스

| 시장 | 우선 소스 | 보완 소스 |
|------|-----------|-----------|
| 한국 (KOSPI/KOSDAQ) | pykrx, FinanceDataReader | yfinance |
| 미국 (S&P 500) | yfinance | FinanceDataReader |

## 주의사항

- yfinance의 한국 주식 재무 데이터는 불완전할 수 있으므로 pykrx/FDR를 우선 활용합니다.
- API rate limit을 고려하여 병렬 수집은 기본 5개 worker로 제한됩니다.
- Google Sheets API 일일 쓰기 할당량(60 req/min)을 고려해 batch_update를 사용합니다.
- `credentials.json` 파일은 절대 git에 커밋하지 마세요.
