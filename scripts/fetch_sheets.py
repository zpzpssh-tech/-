"""
구글 시트(웹에 게시한 주소) → data/원본/시트/*.csv 내려받기
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
시트에 어떤 탭(월별 시트)이 있는지만 보고 싶으면:
  python3 scripts/fetch_sheets.py --tabs

주의: '웹에 게시'와 '링크 공유'는 다릅니다.
      링크 공유만 켜 두면 로그인 화면(HTML)이 내려와서 이 스크립트가 오류로 잡아냅니다.

[받는 방법이 두 가지인 이유]
  구글의 CSV 주소(pub?output=csv)는 "파일은 저쪽에서 받아가라"며
  googleusercontent.com 이라는 다른 서버로 넘깁니다.
  회사/작업 환경에 따라 docs.google.com 은 열려 있어도 그 다른 서버는 막혀 있을 수 있습니다.
  그래서 CSV가 막히면 같은 시트의 '웹표(pubhtml)' 주소를 받아서 표를 CSV로 바꿉니다.
  웹표는 docs.google.com 이 직접 내려주기 때문에 이 경우에도 잘 받아집니다.
  내용은 같고, 받는 길만 다릅니다.
"""
import argparse
import csv
import io
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "data" / "시트연동.json"
OUT = ROOT / "data" / "원본" / "시트"
TIMEOUT = 120

# 회사 프록시를 쓰는 환경에서도 인증서 검증을 끄지 않도록, 시스템 설정을 그대로 씁니다.
CTX = ssl.create_default_context()


class Blocked(RuntimeError):
    """주소 자체는 맞는데 네트워크가 막아서 못 받은 경우 (웹표로 우회해 볼 수 있습니다)."""


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
        tabs = s.get("탭")
        if tabs is not None and not (tabs == "전체" or isinstance(tabs, list)):
            sys.exit(
                f"[오류] {CONF.name} 의 '{s['이름']}' 의 '탭' 은 "
                '"전체" 또는 ["2026/09월", ...] 형태여야 합니다.'
            )
    return sheets


# ---------------------------------------------------------------- 주소 다루기

def pub_base(url: str) -> str:
    """게시 주소에서 '.../pub' 앞부분만 잘라냅니다. 여기에 /pub, /pubhtml 을 붙여 씁니다."""
    m = re.match(r"(https://docs\.google\.com/spreadsheets/d/(?:e/)?[^/]+)/pub", url)
    if not m:
        raise RuntimeError(
            "주소 모양이 '웹에 게시' 주소가 아닙니다.\n"
            "      → .../pub?output=csv 처럼 중간에 /pub 이 들어간 주소여야 합니다.\n"
            "      → 구글 시트에서 [파일]→[공유]→[웹에 게시] 로 다시 만들어 주세요."
        )
    return m.group(1)


def with_gid(url: str, gid) -> str:
    """주소에 gid(탭 번호)를 붙입니다. 이미 있으면 바꿉니다."""
    if gid is None:
        return url
    if "gid=" in url:
        return re.sub(r"gid=\d+", f"gid={gid}", url)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}gid={gid}&single=true"


def safe_name(text: str) -> str:
    """탭 이름을 파일 이름으로 쓸 수 있게 다듬습니다. 예) 2026/09월 → 2026-09월"""
    return re.sub(r"[\\/:*?\"<>|]+", "-", text).strip().strip(".") or "이름없음"


# ---------------------------------------------------------------- 내려받기

def get(url: str):
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
        if "403" in reason or "CONNECT" in reason.upper() or "tunnel" in reason.lower():
            raise Blocked(f"네트워크가 이 주소를 막았습니다: {reason}")
        raise RuntimeError(f"연결하지 못했습니다: {reason}")


def looks_like_html(body: bytes) -> bool:
    head = body[:400].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<head>" in head


def decode(body: bytes) -> str:
    """구글은 UTF-8로 줍니다. 혹시 모를 BOM만 떼어냅니다."""
    return body.decode("utf-8-sig", errors="replace")


# ---------------------------------------------------------------- 웹표(HTML) → CSV

class TableParser(HTMLParser):
    """구글 웹표(pubhtml)에서 표 한 개를 읽어 줄 목록으로 만듭니다.

    구글 표는 왼쪽 줄번호 칸(1, 2, 3…)을 <th> 로, 실제 값을 <td> 로 내보냅니다.
    그래서 <td> 만 모으면 시트에 보이는 값 그대로가 됩니다.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None
        self._span = 1
        self._depth = 0   # 셀 안에 <div>, <a> 같은 게 있어도 흔들리지 않게

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []
            self._span = int(dict(attrs).get("colspan") or 1)
            self._depth = 0
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")
        elif self._cell is not None:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            text = "".join(self._cell).strip()
            self._row.append(text)
            # 병합된 칸은 빈 칸으로 자리를 채워 열이 밀리지 않게 합니다.
            self._row.extend([""] * (self._span - 1))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(c.strip() for c in self._row):
                self.rows.append(self._row)
            self._row = None
        elif self._cell is not None and self._depth > 0:
            self._depth -= 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def html_table_to_csv(html_text: str) -> str:
    p = TableParser()
    p.feed(html_text)
    rows = p.rows
    if not rows:
        raise RuntimeError("웹표에서 표를 찾지 못했습니다. 시트가 비어 있는지 확인해 주세요.")
    # 줄마다 칸 수가 다를 수 있어 가장 긴 줄에 맞춰 채웁니다.
    width = max(len(r) for r in rows)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for r in rows:
        w.writerow(r + [""] * (width - len(r)))
    return buf.getvalue()


TAB_RE = re.compile(r'name:\s*"((?:[^"\\]|\\.)*)".*?gid:\s*"(\d+)"', re.S)


def list_tabs(base: str):
    """게시된 시트에 어떤 탭이 있는지 [(이름, gid), …] 로 돌려줍니다."""
    body, _ = get(f"{base}/pubhtml")
    text = decode(body)
    tabs = []
    seen = set()
    for name, gid in TAB_RE.findall(text):
        # 자바스크립트 문자열이라 \/ 나 \x3d 같은 표기가 섞여 있습니다.
        name = name.replace("\\/", "/").replace('\\"', '"').replace("\\\\", "\\")
        name = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), name)
        if gid not in seen:
            seen.add(gid)
            tabs.append((name, gid))
    return tabs


def fetch_tab(base: str, url: str, gid):
    """탭 하나를 CSV 글자로 돌려줍니다. (본문, 받은 방법) 을 함께 줍니다."""
    try:
        body, final = get(with_gid(url, gid))
        if looks_like_html(body):
            raise Blocked("CSV 대신 웹페이지가 내려왔습니다.")
        return decode(body), "CSV"
    except Blocked:
        pass  # 아래에서 웹표로 다시 시도합니다.

    # 웹표 주소는 gid(탭 번호)를 꼭 요구합니다(없으면 구글이 400을 냅니다).
    # 설정에 탭을 안 적었으면 주소에 붙은 gid를, 그것도 없으면 첫 번째 탭을 씁니다.
    if gid is None:
        m = re.search(r"gid=(\d+)", url)
        if m:
            gid = m.group(1)
        else:
            tabs = list_tabs(base)
            if not tabs:
                raise RuntimeError("탭 목록을 읽지 못해 웹표로 받을 수 없습니다.")
            gid = tabs[0][1]

    body, final = get(f"{base}/pubhtml/sheet?headers=false&gid={gid}")
    if not looks_like_html(body):
        raise RuntimeError(f"웹표 주소에서 예상 밖의 내용이 왔습니다: {final}")
    return html_table_to_csv(decode(body)), "웹표"


def summarize(text: str):
    """행 수와 첫 줄(열 이름)을 돌려줍니다 — 받은 게 맞는지 눈으로 확인하기 위한 것."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = lines[0] if lines else ""
    if len(header) > 100:
        header = header[:100] + " …"
    return len(lines), header


# ---------------------------------------------------------------- 본체

def targets(sheet):
    """이 시트에서 받아야 할 [(붙일이름, gid, 저장파일명), …] 목록을 만듭니다."""
    name, save = sheet["이름"], sheet["저장"]
    want = sheet.get("탭")
    if want is None:
        return [(name, None, save)]

    base = pub_base(sheet["주소"])
    tabs = list_tabs(base)
    if not tabs:
        raise RuntimeError("탭 목록을 읽지 못했습니다. 시트가 '웹에 게시' 되어 있는지 확인해 주세요.")
    if isinstance(want, list):
        have = {n for n, _ in tabs}
        missing = [w for w in want if w not in have]
        if missing:
            raise RuntimeError(
                f"이런 이름의 탭이 없습니다: {', '.join(missing)}\n"
                f"      → 이 시트에 있는 탭: {', '.join(n for n, _ in tabs)}"
            )
        tabs = [(n, g) for n, g in tabs if n in want]

    stem = save[:-4] if save.lower().endswith(".csv") else save
    return [(f"{name}/{n}", g, f"{stem}_{safe_name(n)}.csv") for n, g in tabs]


def main():
    ap = argparse.ArgumentParser(description="구글 시트를 CSV로 내려받습니다.")
    ap.add_argument("--check", action="store_true", help="저장하지 않고 열리는지만 확인합니다.")
    ap.add_argument("--only", metavar="이름", help="설정에서 이 이름의 시트 하나만 받습니다.")
    ap.add_argument("--tabs", action="store_true", help="시트에 어떤 탭이 있는지만 보여 줍니다.")
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

    if args.tabs:
        for s in sheets:
            print(f"[{s['이름']}]")
            try:
                for n, g in list_tabs(pub_base(s["주소"])):
                    print(f"  · {n}   (gid={g})")
            except RuntimeError as e:
                print(f"  실패: {e}")
        return

    if not args.check:
        OUT.mkdir(parents=True, exist_ok=True)

    ok, failed = [], []
    for s in sheets:
        try:
            jobs = targets(s)
        except RuntimeError as e:
            print(f"· {s['이름']} … 실패")
            print(f"    {e}")
            failed.append(s["이름"])
            continue

        base = pub_base(s["주소"])
        for label, gid, save in jobs:
            print(f"· {label} … ", end="", flush=True)
            try:
                text, how = fetch_tab(base, s["주소"], gid)
            except (RuntimeError, Blocked) as e:
                print("실패")
                print(f"    {e}")
                failed.append(label)
                continue

            rows, header = summarize(text)
            if rows == 0:
                print("실패")
                print("    내용이 비어 있습니다. 시트에 데이터가 있는지 확인해 주세요.")
                failed.append(label)
                continue

            if args.check:
                print(f"열림 ({rows}줄, {how})")
            else:
                (OUT / save).write_text(text, encoding="utf-8")
                print(f"저장 ({rows}줄, {how}) → data/원본/시트/{save}")
            print(f"    열: {header}")
            ok.append(label)

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
