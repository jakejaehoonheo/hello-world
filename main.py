#!/usr/bin/env python3
"""
Stock Screening Automation
매직 포뮬라(Joel Greenblatt) + 와이스 배당 분석(Geraldine Weiss)
한국(KOSPI/KOSDAQ) 및 미국(NYSE/NASDAQ) 주식 자동 스크리닝

Usage:
    python main.py                    # 전체 실행 (한국 + 미국)
    python main.py --market kr        # 한국만
    python main.py --market us        # 미국만
    python main.py --screener mf      # 매직 포뮬라만
    python main.py --screener weiss   # 와이스만
    python main.py --dry-run          # 시트 저장 없이 콘솔 출력만
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import pandas as pd

import config
from data_collector import collect_all_data, get_kr_stock_list, get_us_stock_list
from screeners.magic_formula import run_magic_formula
from screeners.weiss_dividend import run_weiss_analysis
from sheets_writer import save_results

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args():
    parser = argparse.ArgumentParser(description="주식 스크리닝 자동화 시스템")
    parser.add_argument(
        "--market",
        choices=["kr", "us", "all"],
        default="all",
        help="분석 시장 (기본: all)",
    )
    parser.add_argument(
        "--screener",
        choices=["mf", "weiss", "all"],
        default="all",
        help="스크리너 선택 (기본: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Google Sheets 저장 없이 콘솔 출력만",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 로그 출력",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(args.verbose)
    logger.info("=" * 60)
    logger.info("주식 스크리닝 자동화 시작")
    logger.info("시장: %s | 스크리너: %s | dry-run: %s", args.market, args.screener, args.dry_run)
    logger.info("=" * 60)

    today_str = datetime.now().strftime("%Y%m%d")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # 결과 저장 변수
    mf_kr = mf_us = weiss_kr = weiss_us = None

    # ── 한국 시장 ────────────────────────────────────────────────
    if args.market in ("kr", "all"):
        logger.info("── 한국 시장 데이터 수집 시작 ──")
        kr_stocks = get_kr_stock_list()
        if not kr_stocks.empty:
            kr_data = collect_all_data(kr_stocks)
            logger.info("한국 종목 데이터 수집 완료: %d개", len(kr_data))

            if args.screener in ("mf", "all"):
                logger.info("매직 포뮬라 (한국) 분석 시작...")
                mf_kr = run_magic_formula(kr_data, "kr")
                _print_summary("매직 포뮬라 (한국)", mf_kr)

            if args.screener in ("weiss", "all"):
                logger.info("와이스 배당 (한국) 분석 시작...")
                weiss_kr = run_weiss_analysis(kr_data, "kr")
                _print_summary("와이스 배당 (한국)", weiss_kr)
        else:
            logger.warning("한국 종목 리스트 로드 실패")

    # ── 미국 시장 ────────────────────────────────────────────────
    if args.market in ("us", "all"):
        logger.info("── 미국 시장 데이터 수집 시작 ──")
        us_stocks = get_us_stock_list()
        if not us_stocks.empty:
            us_data = collect_all_data(us_stocks)
            logger.info("미국 종목 데이터 수집 완료: %d개", len(us_data))

            if args.screener in ("mf", "all"):
                logger.info("매직 포뮬라 (미국) 분석 시작...")
                mf_us = run_magic_formula(us_data, "us")
                _print_summary("매직 포뮬라 (미국)", mf_us)

            if args.screener in ("weiss", "all"):
                logger.info("와이스 배당 (미국) 분석 시작...")
                weiss_us = run_weiss_analysis(us_data, "us")
                _print_summary("와이스 배당 (미국)", weiss_us)
        else:
            logger.warning("미국 종목 리스트 로드 실패")

    # ── 요약 (교집합) ────────────────────────────────────────────
    summary = _build_summary(mf_kr, mf_us, weiss_kr, weiss_us)
    if summary is not None and not summary.empty:
        _print_summary("교집합 요약", summary)

    # ── CSV 저장 ─────────────────────────────────────────────────
    _save_csv(mf_kr, f"MF_한국_{today_str}", today_str)
    _save_csv(mf_us, f"MF_미국_{today_str}", today_str)
    _save_csv(weiss_kr, f"Weiss_한국_{today_str}", today_str)
    _save_csv(weiss_us, f"Weiss_미국_{today_str}", today_str)
    _save_csv(summary, f"요약_{today_str}", today_str)

    # ── Google Sheets 저장 ───────────────────────────────────────
    if not args.dry_run:
        try:
            save_results(
                mf_kr=mf_kr,
                mf_us=mf_us,
                weiss_kr=weiss_kr,
                weiss_us=weiss_us,
                summary=summary,
            )
        except FileNotFoundError as e:
            logger.warning("Google Sheets 저장 건너뜀: %s", e)
        except Exception as e:
            logger.error("Google Sheets 저장 실패: %s", e)
    else:
        logger.info("dry-run 모드: Google Sheets 저장 건너뜀")

    logger.info("=" * 60)
    logger.info("스크리닝 완료!")
    logger.info("=" * 60)


def _build_summary(
    mf_kr: pd.DataFrame | None,
    mf_us: pd.DataFrame | None,
    weiss_kr: pd.DataFrame | None,
    weiss_us: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """매직 포뮬라와 와이스 분석의 교집합 종목 추출."""
    mf_tickers = set()
    weiss_data = {}

    # 매직 포뮬라 상위 종목 티커 수집
    for mf_df in [mf_kr, mf_us]:
        if mf_df is not None and not mf_df.empty:
            mf_tickers.update(mf_df["티커"].tolist())

    # 와이스 긍정 신호 종목
    for weiss_df, market_label in [(weiss_kr, "KR"), (weiss_us, "US")]:
        if weiss_df is not None and not weiss_df.empty:
            positive = weiss_df[weiss_df["와이스신호"].isin(["🟢 강력 매수", "🟡 매수 검토"])]
            for _, row in positive.iterrows():
                weiss_data[row["티커"]] = {
                    "market_label": market_label,
                    "signal": row["와이스신호"],
                    "position": row.get("현재위치(0~1)", ""),
                    "bluechip": row.get("블루칩점수", ""),
                    "div_yield": row.get("현재배당수익률", ""),
                }

    # 교집합
    overlap = mf_tickers & set(weiss_data.keys())
    if not overlap:
        logger.info("두 방법론 교집합 종목 없음")
        return None

    rows = []
    all_dfs = {"kr": (mf_kr, weiss_kr), "us": (mf_us, weiss_us)}

    for ticker in overlap:
        w = weiss_data[ticker]
        row = {"티커": ticker, "시장": w["market_label"]}

        # 매직 포뮬라 데이터
        for mf_df in [mf_kr, mf_us]:
            if mf_df is not None and not mf_df.empty:
                match = mf_df[mf_df["티커"] == ticker]
                if not match.empty:
                    m = match.iloc[0]
                    row["종목명"] = m.get("종목명", "")
                    row["매직포뮬라_순위"] = m.get("순위", "")
                    row["현재주가"] = m.get("현재주가", "")
                    row["PER"] = m.get("PER", "")
                    row["PBR"] = m.get("PBR", "")
                    break

        # 와이스 데이터
        row["와이스_신호"] = w["signal"]
        row["와이스_위치"] = w["position"]
        row["블루칩점수"] = w["bluechip"]
        row["배당수익률"] = w["div_yield"]

        # ROE 추가 (와이스 시트에서)
        for weiss_df in [weiss_kr, weiss_us]:
            if weiss_df is not None and not weiss_df.empty:
                wmatch = weiss_df[weiss_df["티커"] == ticker]
                if not wmatch.empty:
                    row["ROE"] = wmatch.iloc[0].get("ROE", "")
                    break

        row["종합메모"] = f"MF+Weiss 교집합 ({w['signal']})"
        row["분석일자"] = datetime.now().strftime("%Y-%m-%d")
        rows.append(row)

    summary = pd.DataFrame(rows)

    # 컬럼 순서 정리
    col_order = [
        "티커", "종목명", "시장", "매직포뮬라_순위", "와이스_신호", "와이스_위치",
        "블루칩점수", "현재주가", "PER", "PBR", "ROE", "배당수익률", "종합메모", "분석일자",
    ]
    for c in col_order:
        if c not in summary.columns:
            summary[c] = ""
    summary = summary[col_order]

    return summary


def _print_summary(title: str, df: pd.DataFrame | None):
    """콘솔에 결과 요약 출력."""
    if df is None or df.empty:
        logger.info("[%s] 결과 없음", title)
        return

    logger.info("─" * 50)
    logger.info("[%s] 상위 10 종목:", title)
    display_cols = [c for c in df.columns if c not in ("분석일자",)]
    print(df[display_cols].head(10).to_string(index=False))
    logger.info("총 %d 종목", len(df))


def _save_csv(df: pd.DataFrame | None, name: str, date_str: str):
    """DataFrame을 CSV 파일로 저장."""
    if df is None or df.empty:
        return
    filepath = os.path.join(config.OUTPUT_DIR, f"{name}.csv")
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    logger.info("CSV 저장: %s", filepath)


if __name__ == "__main__":
    main()
