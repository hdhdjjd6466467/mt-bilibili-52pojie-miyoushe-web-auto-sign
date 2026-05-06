#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from datetime import datetime, timezone


ROOT = Path(os.getenv("BINMT_BASE_DIR") or Path(__file__).resolve().parent).resolve()
ENV_PATH = ROOT / ".env"
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "signin.log"

LOGIN_URL = "https://bbs.binmt.cc/member.php?mod=logging&action=login"
SIGN_PAGE_URL = "https://bbs.binmt.cc/k_misign-sign.html"
USER_AGENT = "Mozilla/5.0"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def append_log(payload: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        now = datetime.now(timezone.utc).isoformat()
        handle.write(f"{now} {json.dumps(payload, ensure_ascii=False)}\n")


def opener_with_cookies():
    cookie_jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def http_get(opener, url: str, referer: str | None = None) -> str:
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    return opener.open(request, timeout=20).read().decode("utf-8", "ignore")


def http_post(opener, url: str, data: dict, referer: str | None = None) -> str:
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    payload = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(url, data=payload, headers=headers)
    return opener.open(request, timeout=20).read().decode("utf-8", "ignore")


def parse_login_form(html: str) -> tuple[str, str]:
    formhashes = re.findall(r'name="formhash" value="([^"]+)"', html)
    actions = re.findall(r'<form[^>]+name="login"[^>]+action="([^"]+)"', html)
    if not formhashes or not actions:
        raise RuntimeError("Failed to parse the login form.")
    return formhashes[-1], actions[0].replace("&amp;", "&")


def login(opener, username: str, password: str) -> dict:
    login_page = http_get(opener, LOGIN_URL)
    formhash, action = parse_login_form(login_page)
    login_action_url = urllib.parse.urljoin("https://bbs.binmt.cc/", action)

    login_response = http_post(
        opener,
        login_action_url,
        {
            "formhash": formhash,
            "referer": "https://bbs.binmt.cc/./",
            "loginfield": "username",
            "username": username,
            "password": password,
            "questionid": "0",
            "answer": "",
            "cookietime": "2592000",
            "loginsubmit": "true",
        },
        referer=LOGIN_URL,
    )

    sign_page = http_get(opener, SIGN_PAGE_URL)
    logged_in = username in sign_page or "退出" in sign_page

    return {
        "ok": logged_in,
        "formhash": formhash,
        "login_action_url": login_action_url,
        "login_response_snippet": login_response[:600],
        "sign_page": sign_page,
    }


def parse_sign_url(sign_page: str) -> str | None:
    match = re.search(
        r'href="(plugin\.php\?id=k_misign:sign&operation=qiandao&formhash=[0-9a-f]+&format=empty)"',
        sign_page,
    )
    if not match:
        return None
    return urllib.parse.urljoin("https://bbs.binmt.cc/", match.group(1))


def summarize_sign_page(sign_page: str, sign_body: str = "") -> tuple[str, str]:
    combined = f"{sign_body}\n{sign_page}"

    if "您的签到排名：" in sign_page:
        ranking = re.search(r"您的签到排名：([0-9]+)", sign_page)
        rank_text = ranking.group(1) if ranking else ""
        message = f"今日已签到，排名 {rank_text}" if rank_text else "今日已签到"
        return "success", message

    if "您今天还没有签到" in sign_page:
        return "not_signed", "页面显示今天还没有签到"

    if "您需要先登录" in combined or "登录" in sign_body and "密码" in sign_body:
        return "login_required", "签到前需要重新登录"

    return "unknown", "未识别的签到结果"


def run() -> int:
    load_env_file(ENV_PATH)

    username = os.environ.get("BINMT_USERNAME", "").strip()
    password = os.environ.get("BINMT_PASSWORD", "").strip()
    if not username or not password:
        result = {
            "ok": False,
            "status": "missing_credentials",
            "message": "Set BINMT_USERNAME and BINMT_PASSWORD in .env first.",
        }
        append_log(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    opener = opener_with_cookies()
    login_result = login(opener, username, password)
    if not login_result["ok"]:
        result = {
            "ok": False,
            "status": "login_failed",
            "message": "Login did not reach the signed-in state.",
            "login_response_snippet": login_result["login_response_snippet"],
        }
        append_log(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    sign_page = login_result["sign_page"]
    sign_url = parse_sign_url(sign_page)
    if not sign_url:
        status, message = summarize_sign_page(sign_page)
        result = {
            "ok": status == "success",
            "status": "already_done" if status == "success" else status,
            "message": message,
        }
        append_log(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    sign_body = http_get(opener, sign_url, referer=SIGN_PAGE_URL)
    refreshed_sign_page = http_get(opener, SIGN_PAGE_URL)
    status, message = summarize_sign_page(refreshed_sign_page, sign_body)

    result = {
        "ok": status == "success",
        "status": status,
        "message": message,
        "sign_url": sign_url,
        "response_snippet": sign_body[:300],
    }
    append_log(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(run())
