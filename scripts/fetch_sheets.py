"""
구글 시트(웹에 게시한 CSV 주소) → data/원본/시트/*.csv 내려받기
--------------------------------------------------------------
쓰는 법:
  1) 구글 시트에서 [파일] → [공유] → [웹에 게시] → 형식을 'CSV'로 골라 주소를 복사합니다.
     주소는 .../pub?output=csv 또는 .../pub?gid=0&single=true&output=csv 모양입니다.
  2) 그 주소를 data/시트연동.json 에 적습니다.
  3) python3 scripts/fetch_sheets.py     ← 시트를 내려받습니다
  4) python3 scripts/build.py            ← 대시보드를 다시 만듭니다

연결만 먼저 확인하고 싶으면:
  python3 scripts/fetch_sheets.py --check      (파일을 저장하지 않고 열리는지만 봅니다)
하나만 받고 싶으면:
  python3 scripts/fetch_sheets.py --only 네이버정산

주의: '웹에 게시'와 '링크 공유'는 다릅니다.
      링크 공유만 켜 두면 로그인 화면(HTML)이 내려와서 이 스크립트가 오류로 잡아냅니다.
"""
import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "data" / "시트연동.json"
OUT = ROOT / "data" / "원본" / "시트"
TIMEOUT = 60

# 회사 프록시를 쓰는 환경에서도 인증서 검증을 끄지 않도록, 시스템 설정을 그대로 씁니다.
CTX = ssl.create_default_context()


def load_conf():
    if not CONF.exists():
        sys.exit(
            f"[오류] 설정 파일이 없습니다: {CONF}\n"
            "  data/시트연동.json 을 만들고 시트 주소를 적어 주세요.\n"
            "  형식은 scripts/fetch_sheets.py 맨 위 설명을 참고하세요."
        )
    try:
        conf = json.loads(CONF.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"[오류] {CONF.name} 을 읽지 못했습니다 (JSON 형식 오류): {e}")

    sheets = conf.get("시트")
    if not isinstance(sheets, list) or not sheets:
        sys.exit(f"[오류] {CONF.name} 의 '시트' 목록이 비어 있습니다.")

    for i, s in enumerate(sheets, 1):
        for key in ("이름", "주소", "저장"):
            if not s.get(key):
                sys.exit(f"[오류] {CONF.name} 의 {i}번째 시트에 '{key}' 가 없습니다.")
        if "/" in s["저장"] or "\\" in s["저장"]:
            sys.exit(f"[오류] '저장' 에는 파일 이름만 적어 주세요 (폴더 경로 X): {s['저장']}")
    return sheets


def fetch(url):
    """주소를 열어 (본문 bytes, 최종주소) 를 돌려줍니다. 실패하면 사람이 읽을 수 있는 오류를 냅니다."""
    req = urllib.request.Request(url, headers={"User-Agent": "allTogetherNow-dashboard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
            return r.read(), r.geturl()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError(
                f"구글이 접근을 거부했습니다 (HTTP {e.code}).\n"
                "      → 시트가 '웹에 게시' 되어 있는지 확인해 주세요. "
                "'링크가 있는 사람에게 공유'만으로는 안 됩니다."
            )
        if e.code == 404:
            raise RuntimeError(
                "주소를 찾을 수 없습니다 (HTTP 404).\n"
                "      → 게시를 중단했거나 주소를 잘못 붙여넣었을 수 있습니다."
            )
        raise RuntimeError(f"구글이 오류를 돌려줬습니다 (HTTP {e.code} {e.reason}).")
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "403" in reason or "CONNECT" in reason.upper():
            raise RuntimeError(
                "회사/작업환경 네트워크가 docs.google.com 을 막고 있습니다.\n"
                "      → 네트워크 정책에 docs.google.com 을 추가한 뒤, "
                "새 세션(새 대화)에서 다시 실행해 주세요.\n"
                "        정책은 세션이 시작될 때 한 번 정해져서, 실행 중인 세션에는 반영되지 않습니다."
            )
        raise RuntimeError(f"연결하지 못했습니다: {reason}")


def looks_like_html(body: bytes) -> bool:
    head = body[:400].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<head>" in head


def decode(body: bytes) -> str:
    """구글은 UTF-8로 줍니다. 혹시 모를 BOM만 떼어냅니다."""
    return body.decode("utf-8-sig", errors="replace")


def summarize(text: str):
    """행 수와 첫 줄(열 이름)을 돌려줍니다 — 받은 게 맞는지 눈으로 확인하기 위한 것."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = lines[0] if lines else ""
    if len(header) > 100:
        header = header[:100] + " …"
    return len(lines), header


def main():
    ap = argparse.ArgumentParser(description="구글 시트를 CSV로 내려받습니다.")
    ap.add_argument("--check", action="store_true", help="저장하지 않고 열리는지만 확인합니다.")
    ap.add_argument("--only", metavar="이름", help="설정에서 이 이름의 시트 하나만 받습니다.")
    args = ap.parse_args()

    sheets = load_conf()
    if args.only:
        sheets = [s for s in sheets if s["이름"] == args.only]
        if not sheets:
            sys.exit(f"[오류] '{args.only}' 라는 이름의 시트가 설정에 없습니다.")
    else:
        sheets = [s for s in sheets if s.get("사용", True)]
        if not sheets:
            sys.exit("[오류] '사용': true 인 시트가 하나도 없습니다.")

    if not args.check:
        OUT.mkdir(parents=True, exist_ok=True)

    ok, failed = [], []
    for s in sheets:
        name = s["이름"]
        print(f"· {name} … ", end="", flush=True)
        try:
            body, final = fetch(s["주소"])
        except RuntimeError as e:
            print("실패")
            print(f"    {e}")
            failed.append(name)
            continue

        if looks_like_html(body):
            print("실패")
            print("    CSV가 아니라 웹페이지(HTML)가 내려왔습니다.")
            print("    → 대개 시트가 '웹에 게시' 되어 있지 않아 로그인 화면이 온 경우입니다.")
            print(f"    → 최종 도착 주소: {final}")
            failed.append(name)
            continue

        text = decode(body)
        rows, header = summarize(text)
        if rows == 0:
            print("실패")
            print("    내용이 비어 있습니다. 시트에 데이터가 있는지, gid(탭 번호)가 맞는지 확인해 주세요.")
            failed.append(name)
            continue

        if args.check:
            print(f"열림 ({rows}줄)")
            print(f"    열: {header}")
        else:
            path = OUT / s["저장"]
            path.write_text(text, encoding="utf-8")
            print(f"저장 ({rows}줄) → data/원본/시트/{s['저장']}")
            print(f"    열: {header}")
        ok.append(name)

    print()
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[{when}] 성공 {len(ok)}건, 실패 {len(failed)}건")
    if failed:
        print("실패한 시트: " + ", ".join(failed))
        sys.exit(1)
    if not args.check:
        print("다음: python3 scripts/build.py 로 대시보드를 다시 만드세요.")


if __name__ == "__main__":
    main()
