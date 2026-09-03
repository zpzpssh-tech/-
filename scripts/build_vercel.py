"""
베르셀(Vercel) 배포용 폴더 만들기
--------------------------------
dashboard/index.html 을 비밀번호로 잠긴 형태로 site/ 폴더에 담습니다.

실행:  python3 scripts/build_vercel.py     (scripts/build.py 를 먼저 돌린 뒤에)

[왜 이렇게 하나요]
  베르셀 무료 플랜은 '운영 주소'를 잠글 수 없습니다.
  (잠금 기능은 미리보기 주소에만 걸리고, 운영 주소는 공개로 남습니다.
   운영 주소를 잠그려면 Pro 월 $20, 비밀번호 기능은 그보다 더 비쌉니다.)

  이 대시보드에는 매출·원가·마진이 들어 있어서 공개되면 안 됩니다.
  그래서 대시보드를 그냥 파일로 두지 않고, 비밀번호를 확인하는 작은 프로그램
  안에 넣습니다. 주소로 들어오면 먼저 아이디·비밀번호를 묻고,
  맞아야만 대시보드를 내보냅니다. 이러면 무료 플랜에서도 확실히 잠깁니다.

  대시보드 내용을 프로그램 안에 통째로 넣는 이유는, 파일로 따로 두면
  베르셀이 그 파일을 비밀번호 없이 그냥 내줘 버리기 때문입니다.

[비밀번호 정하기]
  베르셀 프로젝트 설정 → Environment Variables 에서 정합니다.
    DASHBOARD_USER      아이디   (안 정하면 admin)
    DASHBOARD_PASSWORD  비밀번호 (필수. 안 정하면 사이트가 열리지 않습니다)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dashboard" / "index.html"
SITE = ROOT / "site"

HANDLER = '''// 이 파일은 scripts/build_vercel.py 가 만듭니다. 직접 고치지 마세요.
// 고칠 일이 있으면 scripts/build_vercel.py 를 고치고 다시 돌리세요.
//
// 하는 일: 주소로 들어온 사람에게 아이디·비밀번호를 묻고, 맞으면 대시보드를 보여줍니다.
const crypto = require("crypto");

const HTML = %(html)s;

const BUILT_AT = %(built)s;

// 아이디/비밀번호가 맞는지 봅니다.
// 글자를 하나씩 비교하면 걸리는 시간으로 비밀번호를 알아낼 수 있어서,
// 길이에 상관없이 같은 시간이 걸리는 방식(timingSafeEqual)을 씁니다.
function same(a, b) {
  const x = crypto.createHash("sha256").update(String(a)).digest();
  const y = crypto.createHash("sha256").update(String(b)).digest();
  return crypto.timingSafeEqual(x, y);
}

function page(title, body) {
  return '<!doctype html><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>' + title + '</title>' +
    '<style>body{margin:0;min-height:100vh;display:grid;place-items:center;' +
    'background:#f7f3ec;color:#3d3630;font-family:system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;' +
    'line-height:1.7}main{max-width:30rem;padding:2rem;text-align:center}' +
    'h1{font-size:1.25rem;margin:0 0 .75rem}p{margin:.4rem 0;color:#6b6058;font-size:.95rem}' +
    'code{background:#ece5da;padding:.15em .4em;border-radius:4px;font-size:.9em}</style>' +
    '<main>' + body + '</main>';
}

module.exports = (req, res) => {
  // 검색엔진이 절대 수집하지 못하게 합니다.
  res.setHeader("X-Robots-Tag", "noindex, nofollow, noarchive, nosnippet");
  res.setHeader("Referrer-Policy", "no-referrer");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader("X-Content-Type-Options", "nosniff");

  if (req.url === "/robots.txt") {
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    return res.status(200).send("User-agent: *\\nDisallow: /\\n");
  }

  const user = process.env.DASHBOARD_USER || "admin";
  const pass = process.env.DASHBOARD_PASSWORD;

  // 비밀번호를 안 정했으면 아무것도 보여주지 않습니다.
  // (실수로 재무 자료가 공개되는 것보다, 안 열리는 게 낫습니다.)
  if (!pass) {
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    return res.status(500).send(page("설정이 필요합니다",
      "<h1>비밀번호가 정해지지 않았습니다</h1>" +
      "<p>베르셀 프로젝트 설정 → <b>Settings → Environment Variables</b> 에서" +
      " <code>DASHBOARD_PASSWORD</code> 를 정한 뒤, <b>Redeploy</b> 를 눌러 주세요.</p>" +
      "<p>안전을 위해 비밀번호가 없으면 대시보드를 내보내지 않습니다.</p>"));
  }

  const head = req.headers.authorization || "";
  if (head.startsWith("Basic ")) {
    const raw = Buffer.from(head.slice(6), "base64").toString("utf8");
    const cut = raw.indexOf(":");
    if (cut !== -1 && same(raw.slice(0, cut), user) && same(raw.slice(cut + 1), pass)) {
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      res.setHeader("Cache-Control", "private, no-store");
      return res.status(200).send(HTML);
    }
  }

  // HTTP 헤더 값에는 영문만 들어갑니다. 한글을 넣으면 서버가 오류를 냅니다.
  res.setHeader("WWW-Authenticate", 'Basic realm="Dashboard", charset="UTF-8"');
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  return res.status(401).send(page("로그인이 필요합니다",
    "<h1>올투게더나우 손익 대시보드</h1>" +
    "<p>아이디와 비밀번호를 넣어 주세요.</p>" +
    "<p>창이 안 뜨면 새로고침해 주세요.</p>" +
    "<p style=\\"margin-top:1.5rem;font-size:.85rem;opacity:.7\\">자료 기준 " + BUILT_AT + "</p>"));
};
'''

VERCEL_JSON = {
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "rewrites": [{"source": "/(.*)", "destination": "/api/index"}],
}


def main():
    if not SRC.exists():
        sys.exit(f"[오류] {SRC} 가 없습니다.\n"
                 "  python3 scripts/build.py 를 먼저 돌려 주세요.")

    html = SRC.read_text(encoding="utf-8")
    built = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")

    api = SITE / "api"
    api.mkdir(parents=True, exist_ok=True)

    # 대시보드를 자바스크립트 글자로 안전하게 집어넣습니다.
    # json.dumps 를 쓰면 따옴표·줄바꿈·역슬래시가 알아서 처리됩니다.
    (api / "index.js").write_text(
        HANDLER % {"html": json.dumps(html), "built": json.dumps(built)},
        encoding="utf-8",
    )
    (SITE / "vercel.json").write_text(
        json.dumps(VERCEL_JSON, indent=2) + "\n", encoding="utf-8"
    )
    # 이 폴더에는 정적 파일을 두지 않습니다.
    # 두면 베르셀이 비밀번호를 묻지 않고 그냥 내보냅니다.
    (SITE / "README.md").write_text(
        "# 베르셀 배포용 폴더 (자동 생성)\n\n"
        "`scripts/build_vercel.py` 가 만듭니다. 직접 고치지 마세요.\n\n"
        "여기에 HTML·이미지 같은 파일을 두면 안 됩니다. "
        "베르셀이 비밀번호를 묻지 않고 그대로 내보내기 때문입니다.\n"
        "대시보드는 `api/index.js` 안에 들어 있고, 비밀번호가 맞아야만 나옵니다.\n\n"
        "배포 방법은 `docs/베르셀배포.md` 를 보세요.\n",
        encoding="utf-8",
    )

    kb = len((api / "index.js").read_text(encoding="utf-8")) / 1024
    print(f"베르셀 배포용 폴더 생성 완료 → site/")
    print(f"  site/api/index.js   {kb:,.0f} KB (대시보드가 이 안에 들어 있습니다)")
    print(f"  site/vercel.json    모든 주소를 위 프로그램으로 보냅니다")
    print()
    print("다음: docs/베르셀배포.md 를 따라 베르셀에 올리세요.")
    print("      Root Directory 를 site 로, DASHBOARD_PASSWORD 를 꼭 정하세요.")


if __name__ == "__main__":
    main()
