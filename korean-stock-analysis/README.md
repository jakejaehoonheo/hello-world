# 한국 주식 자동 분석 대시보드

Google Sheets 기반 한국 주식 기술적 분석 자동화 도구입니다.
매일 자동으로 관심 종목의 기술적 분석, 매수/매도 시그널, AI 요약을 생성하여 Google Sheets에 기록합니다.

## 기능

- **데이터 수집**: pykrx를 통해 KRX 주식 데이터 (OHLCV, 시가총액, PER, PBR, 배당수익률) 수집
- **기술적 분석**: 이동평균선(5/20/60/120일), RSI, MACD, 볼린저밴드, 거래량 분석
- **시그널 판단**: 5단계 매수/매도 시그널 (강한매수 ~ 강한매도) + 10점 만점 종합점수
- **AI 분석**: Claude API를 활용한 3줄 요약 및 자연어 쿼리 응답
- **자동 기록**: Google Sheets에 날짜별 시트로 결과 자동 기록

## 프로젝트 구조

```
korean-stock-analysis/
├── config.py              # 설정 및 환경변수
├── data_collector.py      # 주식 데이터 수집
├── technical_analysis.py  # 기술적 분석 (MA, RSI, MACD, BB)
├── signal_generator.py    # 매수/매도 시그널 판단
├── ai_analyzer.py         # Claude API 연동
├── sheets_manager.py      # Google Sheets 읽기/쓰기
├── main.py                # 메인 실행 스크립트
├── requirements.txt
├── .env.example
└── README.md
```

## 설치 방법

### 1. Python 환경 설정

```bash
# Python 3.11+ 필요
python --version

# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 2. Google Sheets API 서비스 계정 설정

#### 2-1. Google Cloud 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 상단의 프로젝트 선택 드롭다운 → **새 프로젝트** 클릭
3. 프로젝트 이름 입력 (예: `stock-analysis`) → **만들기**

#### 2-2. Google Sheets API 활성화

1. 좌측 메뉴 → **API 및 서비스** → **라이브러리**
2. "Google Sheets API" 검색 → 클릭 → **사용** 버튼 클릭

#### 2-3. 서비스 계정 생성

1. 좌측 메뉴 → **API 및 서비스** → **사용자 인증 정보**
2. **+ 사용자 인증 정보 만들기** → **서비스 계정**
3. 서비스 계정 이름 입력 (예: `sheets-writer`) → **만들기 및 계속**
4. 역할: **편집자** 선택 → **완료**

#### 2-4. JSON 키 다운로드

1. 생성된 서비스 계정 클릭
2. **키** 탭 → **키 추가** → **새 키 만들기**
3. **JSON** 선택 → **만들기**
4. 다운로드된 JSON 파일을 프로젝트 폴더에 `service_account.json`으로 저장

#### 2-5. 스프레드시트에 서비스 계정 공유

1. Google Sheets에서 대시보드용 스프레드시트 생성
2. JSON 키 파일 내의 `client_email` 값 확인 (예: `sheets-writer@stock-analysis.iam.gserviceaccount.com`)
3. 스프레드시트 우측 상단 **공유** → 해당 이메일 주소를 **편집자** 권한으로 추가

### 3. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 편집하여 다음 값을 입력:

```
ANTHROPIC_API_KEY=sk-ant-your-api-key
GOOGLE_SHEET_ID=your-spreadsheet-id
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
```

- `GOOGLE_SHEET_ID`는 스프레드시트 URL에서 확인:
  `https://docs.google.com/spreadsheets/d/{여기가_ID}/edit`

### 4. INPUT 시트 준비

스프레드시트에 `INPUT`이라는 이름의 시트를 만들고, 다음과 같이 작성:

| A (종목코드) | B (종목명) | C (자연어 쿼리) | D (메모) |
|---|---|---|---|
| 005930 | 삼성전자 | 현재 매수 타이밍인가요? | |
| 000660 | SK하이닉스 | 52주 신고가 돌파 가능성은? | AI반도체 |
| 035720 | 카카오 | | |

- A열, B열: 필수
- C열: 선택 (비어있으면 자연어 쿼리 스킵)
- D열: 메모 (스크립트 무시)
- 1행은 헤더로 사용 (2행부터 데이터)

## 실행

```bash
cd korean-stock-analysis
python main.py
```

실행 시 `20260218` 형식의 날짜 시트가 자동 생성되며, 분석 결과가 기록됩니다.

## 자동 실행 설정

### 옵션 A: 로컬 cron job (Linux/Mac)

```bash
# crontab 편집
crontab -e

# 매일 오전 7시(KST) 실행 (서버가 UTC인 경우 22:00 UTC = 07:00 KST)
0 22 * * * cd /path/to/korean-stock-analysis && /path/to/venv/bin/python main.py >> /path/to/cron.log 2>&1

# 또는 KST 타임존 서버인 경우
0 7 * * * cd /path/to/korean-stock-analysis && /path/to/venv/bin/python main.py >> /path/to/cron.log 2>&1
```

경로를 실제 설치 경로로 변경하세요.

### 옵션 B: Google Cloud Scheduler + Cloud Run

#### B-1. Dockerfile 생성

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

#### B-2. Cloud Run 배포

```bash
# Google Cloud CLI 설치 후
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 컨테이너 빌드 및 배포
gcloud run deploy stock-analysis \
  --source . \
  --region asia-northeast3 \
  --no-allow-unauthenticated \
  --set-env-vars "ANTHROPIC_API_KEY=sk-ant-xxx,GOOGLE_SHEET_ID=xxx" \
  --memory 512Mi \
  --timeout 300
```

#### B-3. Cloud Scheduler 설정

```bash
# 서비스 계정 생성 (Cloud Run 호출용)
gcloud iam service-accounts create scheduler-invoker

# 권한 부여
gcloud run services add-iam-policy-binding stock-analysis \
  --region asia-northeast3 \
  --member="serviceAccount:scheduler-invoker@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# 스케줄러 생성 (매일 오전 7시 KST)
gcloud scheduler jobs create http stock-analysis-daily \
  --schedule="0 7 * * *" \
  --time-zone="Asia/Seoul" \
  --uri="https://stock-analysis-xxx.run.app" \
  --http-method=GET \
  --oidc-service-account-email="scheduler-invoker@YOUR_PROJECT_ID.iam.gserviceaccount.com"
```

## 출력 형식

매일 실행 시 `YYYYMMDD` 형식의 시트가 생성됩니다:

**1행**: 실행 시각 + 코스피/코스닥 지수 요약

**3행 (헤더)**:
| 종목코드 | 종목명 | 현재가 | 전일대비% | 시그널 | RSI | MACD방향 | 볼밴위치 | 거래량비율 | 종합점수(10점) | AI분석요약 | 자연어쿼리답변 |

**시그널 범례**:
- 🟢강한매수: 종합점수 8.0 이상
- 🔵매수고려: 종합점수 6.0~7.9
- ⚪중립: 종합점수 4.0~5.9
- 🟡매도고려: 종합점수 2.0~3.9
- 🔴강한매도: 종합점수 2.0 미만

## 종합점수 산출 방식

5개 기술적 지표를 각 2점씩, 총 10점 만점으로 가중 평균:

| 지표 | 가중치 | 매수 시그널 | 매도 시그널 |
|---|---|---|---|
| RSI | 2점 | RSI < 30 (과매도) | RSI > 70 (과매수) |
| MACD | 2점 | 골든크로스, 상승 방향 | 데드크로스, 하락 방향 |
| 볼린저밴드 | 2점 | 하단 이탈/근접 | 상단 돌파/근접 |
| 60일 이평선 | 2점 | 가격 > 60일선 | 가격 < 60일선 |
| 거래량 | 2점 | 급증 + 상승 동반 | 급증 + 하락 동반 |
