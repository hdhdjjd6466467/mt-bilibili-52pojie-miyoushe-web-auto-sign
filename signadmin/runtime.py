from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib import request as urlrequest

from . import config


SITE_DEFS: dict[str, dict[str, Any]] = {
    "binmt": {
        "label": "MT管理器论坛",
        "kind": "password",
        "cooldown_seconds": 5,
    },
    "mihoyo": {
        "label": "米游社",
        "kind": "cookie",
        "sync_target": "mihoyo",
        "runtime_flag": "MIHOYO_USE_RUNTIME_COOKIE",
        "cooldown_seconds": 10,
    },
    "bilibili": {
        "label": "哔哩哔哩",
        "kind": "cookie",
        "sync_target": "bilibili",
        "runtime_flag": "BILIBILI_USE_RUNTIME_COOKIE",
        "cooldown_seconds": 12,
    },
    "52pojie": {
        "label": "52破解",
        "kind": "cookie",
        "sync_target": "52pojie",
        "runtime_flag": "POJIE_USE_RUNTIME_COOKIE",
        "cooldown_seconds": 30,
    },
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
CONTROL_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")


def site_label(site: str) -> str:
    return str(SITE_DEFS.get(site, {}).get("label") or site)


def target_root(target_id: int) -> Path:
    return config.TARGET_STATE_DIR / f"target-{target_id}"


def ensure_target_dirs(target_id: int) -> dict[str, Path]:
    root = target_root(target_id)
    paths = {
        "root": root,
        "logs": root / "logs",
        "config": root / "config",
        "profile": root / "profile",
        "inspect": root / "logs" / "inspect",
    }
    for value in paths.values():
        value.mkdir(parents=True, exist_ok=True)
    return paths


def _clean_text(text: str) -> str:
    text = ANSI_RE.sub("", text or "")
    text = CONTROL_RE.sub("", text)
    return text.replace("\r", "\n")


def _clip(text: str, limit: int = 180) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _env_quote(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _games_from_config(config_data: dict[str, Any]) -> list[str]:
    raw = str(config_data.get("mihoyo_games", "genshin")).strip()
    if not raw:
        raw = "genshin"
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or ["genshin"]


def prepare_target_state(target: dict[str, Any]) -> dict[str, Path]:
    paths = ensure_target_dirs(int(target["id"]))
    site = str(target["site"])
    secrets = target.get("secrets") or {}
    cfg = target.get("config") or {}

    if site == "binmt":
        env_text = (
            f'BINMT_USERNAME="{_env_quote(secrets.get("username", ""))}"\n'
            f'BINMT_PASSWORD="{_env_quote(secrets.get("password", ""))}"\n'
        )
        _write_text(paths["root"] / ".env", env_text)

    elif site == "bilibili":
        env_text = (
            f'BILIBILI_COOKIE="{_env_quote(secrets.get("static_cookie", ""))}"\n'
            f'BILIBILI_WATCH_ENABLED="{1 if cfg.get("watch_enabled", True) else 0}"\n'
            f'BILIBILI_SHARE_ENABLED="{1 if cfg.get("share_enabled", True) else 0}"\n'
            f'BILIBILI_COIN_ENABLED="{1 if cfg.get("coin_enabled", True) else 0}"\n'
            f'BILIBILI_TARGET_DAILY_COINS="{int(cfg.get("target_daily_coins", 5))}"\n'
            f'BILIBILI_PROTECTED_COINS="{int(cfg.get("protected_coins", 0))}"\n'
        )
        _write_text(paths["root"] / ".env", env_text)

    elif site == "52pojie":
        env_lines = [
            f'POJIE_COOKIE="{_env_quote(secrets.get("static_cookie", ""))}"',
            f'POJIE_USERNAME="{_env_quote(secrets.get("username", ""))}"',
            f'POJIE_PASSWORD="{_env_quote(secrets.get("password", ""))}"',
            'POJIE_HEADLESS="true"',
            'POJIE_HUMAN_MODE="true"',
            'POJIE_RETRY_COUNT="1"',
            'POJIE_RETRY_SLEEP_SECONDS="60"',
            'POJIE_TIMEZONE_ID="Asia/Shanghai"',
            'POJIE_SLOW_MO_MS="90"',
        ]
        _write_text(paths["root"] / ".env", "\n".join(env_lines) + "\n")

    elif site == "mihoyo":
        games = set(_games_from_config(cfg))
        enabled = lambda key: "true" if key in games else "false"
        yaml_text = f"""enable: true
version: 15
push: ""
account:
  cookie: "{_env_quote(secrets.get("static_cookie", ""))}"
  stuid: ""
  stoken: ""
  mid: ""
device:
  name: "Xiaomi MI 6"
  model: "Mi 6"
  id: ""
  fp: ""
mihoyobbs:
  enable: false
  checkin: false
  checkin_list: [5, 2]
  read: false
  like: false
  cancel_like: false
  share: false
games:
  cn:
    enable: true
    useragent: "Mozilla/5.0 (Linux; Android 12; Unspecified Device) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/103.0.5060.129 Mobile Safari/537.36"
    retries: 3
    genshin: {{checkin: {enabled("genshin")}, black_list: []}}
    honkai2: {{checkin: {enabled("honkai2")}, black_list: []}}
    honkai3rd: {{checkin: {enabled("honkai3rd")}, black_list: []}}
    tears_of_themis: {{checkin: {enabled("tears_of_themis")}, black_list: []}}
    honkai_sr: {{checkin: {enabled("honkai_sr")}, black_list: []}}
    zzz: {{checkin: {enabled("zzz")}, black_list: []}}
  os:
    enable: false
    cookie: ""
    lang: "zh-cn"
    genshin: {{checkin: false, black_list: []}}
    honkai3rd: {{checkin: false, black_list: []}}
    tears_of_themis: {{checkin: false, black_list: []}}
    honkai_sr: {{checkin: false, black_list: []}}
    zzz: {{checkin: false, black_list: []}}
cloud_games:
  cn:
    enable: false
    genshin: {{enable: false, token: ""}}
    zzz: {{enable: false, token: ""}}
  os:
    enable: false
    lang: "zh-cn"
    genshin: {{enable: false, token: ""}}
competition:
  enable: false
  genius_invokation:
    enable: false
    account: []
    checkin: false
    weekly: false
web_activity:
  enable: false
  activities: []
"""
        _write_text(paths["config"] / "config.yaml", yaml_text)

    return paths


def _cookie_sync_env(target: dict[str, Any], paths: dict[str, Path]) -> dict[str, str]:
    env = os.environ.copy()
    site = str(target["site"])
    if site == "52pojie":
        env.update(
            {
                "POJIE_PROFILE_DIR": str(paths["profile"]),
                "POJIE_RUNTIME_PATH": str(paths["root"] / ".env.runtime"),
                "POJIE_STATIC_PATH": str(paths["root"] / ".env"),
            }
        )
    elif site == "bilibili":
        env.update(
            {
                "BILIBILI_PROFILE_DIR": str(paths["profile"]),
                "BILIBILI_RUNTIME_PATH": str(paths["root"] / ".env.runtime"),
                "BILIBILI_STATIC_PATH": str(paths["root"] / ".env"),
            }
        )
    elif site == "mihoyo":
        env.update(
            {
                "MIHOYO_PROFILE_DIR": str(paths["profile"]),
                "MIHOYO_RUNTIME_PATH": str(paths["config"] / "runtime.yaml"),
                "MIHOYO_STATIC_PATH": str(paths["config"] / "config.yaml"),
            }
        )
    return env


def _ensure_xvfb(display: str = ":1") -> str:
    resolved = str(display or "").strip() or ":1"
    if shutil.which("Xvfb") is None:
        return resolved
    probe = subprocess.run(
        ["pgrep", "-f", f"Xvfb {resolved}"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if probe.returncode == 0 and (probe.stdout or "").strip():
        return resolved
    subprocess.Popen(
        ["Xvfb", resolved, "-screen", "0", "1280x860x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(1)
    return resolved


def sync_cookie_runtime(target: dict[str, Any], paths: dict[str, Path]) -> tuple[bool, str]:
    site = str(target["site"])
    site_def = SITE_DEFS.get(site, {})
    sync_target = site_def.get("sync_target")
    if not sync_target:
        return False, ""

    env = _cookie_sync_env(target, paths)
    cmd = [
        "node",
        str(config.VENDOR_52 / "scripts" / "browser-cookie-sync.mjs"),
        "sync",
        str(sync_target),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output


def open_browser_session(target: dict[str, Any]) -> dict[str, Any]:
    site = str(target["site"])
    if site not in {"52pojie", "bilibili", "mihoyo"}:
        return {"ok": False, "message": "这个站点不需要浏览器登录会话。"}

    paths = prepare_target_state(target)
    env = _cookie_sync_env(target, paths)
    env["DISPLAY"] = _ensure_xvfb(env.get("DISPLAY") or ":1")
    cmd = [
        "node",
        str(config.VENDOR_52 / "scripts" / "browser-cookie-sync.mjs"),
        "open",
        str(SITE_DEFS[site]["sync_target"]),
    ]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = config.SESSION_LOG_DIR / f"target-{target['id']}-{stamp}.log"
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    return {"ok": True, "pid": process.pid, "log_path": str(log_path)}


def purge_target_artifacts(target_id: int, run_log_paths: list[str] | None = None) -> None:
    root = target_root(target_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)

    for path_text in run_log_paths or []:
        path = Path(path_text)
        try:
            if path.exists():
                path.unlink()
        except Exception:
            continue

    for session_log in config.SESSION_LOG_DIR.glob(f"target-{target_id}-*.log"):
        try:
            session_log.unlink()
        except Exception:
            continue


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    results: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        try:
            parsed, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        if isinstance(parsed, dict):
            results.append(parsed)
        index = end
    return results


def _last_matching(items: list[dict[str, Any]], predicate) -> dict[str, Any] | None:
    for item in reversed(items):
        try:
            if predicate(item):
                return item
        except Exception:
            continue
    return None


def summarize_output(site: str, output: str, exit_code: int) -> str:
    text = _clean_text(output)
    objects = _extract_json_objects(text)

    if site == "binmt":
        obj = _last_matching(objects, lambda item: isinstance(item.get("message"), str))
        if obj:
            return _clip(str(obj.get("message") or "").strip())
        return "签到成功" if exit_code == 0 else f"签到失败(exit={exit_code})"

    if site == "bilibili":
        obj = _last_matching(objects, lambda item: "actions" in item or "error" in item or "warnings" in item)
        if not obj:
            return "签到成功" if exit_code == 0 else f"签到失败(exit={exit_code})"
        if obj.get("ok") is False and obj.get("error"):
            return _clip(f"失败: {obj['error']}")
        user = str(obj.get("user") or "").strip()
        actions = [str(item).strip() for item in obj.get("actions") or [] if str(item).strip()]
        detail = "；".join(actions) if actions else ("签到成功" if exit_code == 0 else "执行失败")
        if user:
            detail = f"{user}: {detail}"
        return _clip(detail)

    if site == "mihoyo":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        details: list[str] = []
        current_game = ""
        current_status = "签到成功"
        for line in lines:
            game_match = re.search(r"正在进行「(.+?)」签到", line)
            if game_match:
                current_game = game_match.group(1).strip()
                current_status = "签到成功"
                continue
            if "今天已经签到过了" in line:
                current_status = "今日已签到"
                continue
            if "签到成功" in line:
                current_status = "签到成功"
                continue
            reward_match = re.search(r"今天获得的奖励是[「\"]?(.+?)[」\"]?\s*$", line)
            if reward_match:
                reward = reward_match.group(1).replace("「", "").replace("」", "").strip()
                reward = re.sub(r"(?<=[0-9A-Za-z\u4e00-\u9fff])x(\d+)$", r" x\1", reward)
                details.append(f"{current_game}: {current_status}，奖励 {reward}" if current_game else f"{current_status}，奖励 {reward}")
        if details:
            unique_details: list[str] = []
            for item in details:
                if item not in unique_details:
                    unique_details.append(item)
            return _clip("；".join(unique_details))
        return "签到成功" if exit_code == 0 else f"签到失败(exit={exit_code})"

    if site == "52pojie":
        obj = _last_matching(
            objects,
            lambda item: isinstance(item.get("status"), str) and ("visited" in item or "usernameText" in item or "error" in item),
        )
        if not obj:
            return "签到成功" if exit_code == 0 else f"签到失败(exit={exit_code})"
        status = str(obj.get("status") or "")
        username = str(obj.get("usernameText") or "").strip()
        if status == "success":
            detail = "签到成功"
        elif status == "already_done":
            detail = "今日已签到"
        elif status == "login_required":
            detail = "需要重新登录"
        elif status in {"waf_verification_required", "js_challenge_page"}:
            detail = "触发验证，需要人工处理"
        elif status == "error":
            detail = f"失败: {obj.get('error') or '未知错误'}"
        else:
            detail = status or ("签到成功" if exit_code == 0 else "执行失败")
        reward = ""
        visited = obj.get("visited") or []
        if isinstance(visited, list):
            joined = "\n".join(
                str(((item.get("info") or {}).get("bodySnippet")) or "")
                for item in visited
                if isinstance(item, dict)
            )
            match = re.search(r"积分\s*吾爱币\s*(\d+)\s*CB", joined)
            if match and status in {"success", "already_done"}:
                reward = f"奖励 {match.group(1)}CB"
        parts = [detail]
        if reward:
            parts.append(reward)
        message = "，".join(parts)
        if username and status in {"success", "already_done"}:
            message = f"{username}: {message}"
        return _clip(message)

    return "签到成功" if exit_code == 0 else f"签到失败(exit={exit_code})"


def build_notification_text(target: dict[str, Any], summary: str) -> str:
    member_name = str(target.get("member_name") or "")
    display_name = str(target.get("display_name") or "")
    return f"[{site_label(str(target['site']))}][{member_name}] {display_name}: {summary}"


def send_wecom(webhook_url: str, content: str) -> tuple[bool, str]:
    webhook = webhook_url.strip()
    if not webhook or not content.strip():
        return False, "missing webhook or content"
    payload = json.dumps(
        {
            "msgtype": "text",
            "text": {
                "content": content,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urlrequest.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=20) as response:
        body = response.read().decode("utf-8", "replace")
    return True, body


def run_target(target: dict[str, Any], trigger_type: str = "manual") -> dict[str, Any]:
    target_id = int(target["id"])
    site = str(target["site"])
    paths = prepare_target_state(target)
    started_at = config.now_iso()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = config.RUN_LOG_DIR / f"target-{target_id}-{stamp}.log"
    output_parts: list[str] = []

    runtime_used = False
    if SITE_DEFS.get(site, {}).get("kind") == "cookie":
        sync_ok, sync_output = sync_cookie_runtime(target, paths)
        if sync_output:
            output_parts.append(sync_output)
        runtime_used = sync_ok

    env = os.environ.copy()
    cmd: list[str]

    if site == "binmt":
        env["BINMT_BASE_DIR"] = str(paths["root"])
        cmd = [sys.executable, str(config.VENDOR_BINMT / "binmt_sign.py")]
    elif site == "bilibili":
        env["BILIBILI_BASE_DIR"] = str(paths["root"])
        env["BILIBILI_USE_RUNTIME_COOKIE"] = "1" if runtime_used else "0"
        cmd = [sys.executable, str(config.VENDOR_BILIBILI / "bilibili_sign.py")]
    elif site == "mihoyo":
        env["MIHOYO_CODE_ROOT"] = str(config.VENDOR_MIHOYO)
        env["MIHOYO_VENV_PYTHON"] = str(config.VENDOR_MIHOYO / ".venv" / "bin" / "python")
        env["AutoMihoyoBBS_config_path"] = str(paths["config"])
        env["MIHOYO_USE_RUNTIME_COOKIE"] = "1" if runtime_used else "0"
        cmd = [str(config.VENDOR_MIHOYO / "run_genshin.sh")]
    elif site == "52pojie":
        env["POJIE_CODE_ROOT"] = str(config.VENDOR_52)
        env["POJIE_PROJECT_ROOT"] = str(paths["root"])
        env["POJIE_USE_RUNTIME_COOKIE"] = "1" if runtime_used else "0"
        env["POJIE_PYTHON_BIN"] = sys.executable
        env["POJIE_HEADLESS"] = "true"
        env["POJIE_HUMAN_MODE"] = "true"
        cmd = [str(config.VENDOR_52 / "run-cron.sh")]
    else:
        raise ValueError(f"unsupported site: {site}")

    completed = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=900, check=False)
    output_parts.append((completed.stdout or "") + (completed.stderr or ""))
    exit_code = int(completed.returncode)

    if exit_code != 0 and runtime_used and SITE_DEFS.get(site, {}).get("runtime_flag"):
        fallback_env = env.copy()
        fallback_env[str(SITE_DEFS[site]["runtime_flag"])] = "0"
        fallback_output = "\n[auto-sign-web] runtime failed, fallback to static cookie\n"
        completed = subprocess.run(cmd, capture_output=True, text=True, env=fallback_env, timeout=900, check=False)
        fallback_output += (completed.stdout or "") + (completed.stderr or "")
        output_parts.append(fallback_output)
        exit_code = int(completed.returncode)

    output_text = "\n".join(part for part in output_parts if part)
    _write_text(log_path, output_text)
    finished_at = config.now_iso()
    summary = summarize_output(site, output_text, exit_code)
    return {
        "target_id": target_id,
        "trigger_type": trigger_type,
        "status": "success" if exit_code == 0 else "failed",
        "exit_code": exit_code,
        "summary": summary,
        "log_path": str(log_path),
        "started_at": started_at,
        "finished_at": finished_at,
        "output_text": output_text,
    }


def cooldown_seconds(site: str) -> int:
    return int(SITE_DEFS.get(site, {}).get("cooldown_seconds", 5))
