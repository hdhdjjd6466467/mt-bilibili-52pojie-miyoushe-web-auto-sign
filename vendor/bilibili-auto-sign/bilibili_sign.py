#!/usr/bin/env python3
import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT_DIR = Path(os.getenv("BILIBILI_BASE_DIR") or Path(__file__).resolve().parent).resolve()
ENV_PATH = ROOT_DIR / ".env"
RUNTIME_ENV_PATH = ROOT_DIR / ".env.runtime"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


class BiliApiError(RuntimeError):
    pass


def load_env_file(path: Path, override: bool = False) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ) and len(value) >= 2:
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value


def env_runtime_enabled() -> bool:
    value = os.getenv("BILIBILI_USE_RUNTIME_COOKIE")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off"}


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def parse_cookie_string(cookie_str: str) -> dict[str, str]:
    cookie_map: dict[str, str] = {}
    for item in cookie_str.split(";"):
        chunk = item.strip()
        if not chunk or "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        cookie_map[key.strip()] = value.strip()
    return cookie_map


class BiliClient:
    def __init__(self, cookie_str: str, user_agent: str) -> None:
        self.cookie_str = cookie_str.strip().strip(";")
        self.cookie_map = parse_cookie_string(self.cookie_str)
        self.user_agent = user_agent

    def required_cookie(self, name: str) -> str:
        value = self.cookie_map.get(name, "")
        if not value:
            raise BiliApiError(f"缺少必要 Cookie: {name}")
        return value

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        request_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Cookie": self.cookie_str,
        }
        if headers:
            request_headers.update(headers)

        body = None
        if data is not None:
            encoded = urllib.parse.urlencode(data).encode("utf-8")
            body = encoded
            request_headers.setdefault(
                "Content-Type", "application/x-www-form-urlencoded; charset=UTF-8"
            )

        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            raise BiliApiError(f"HTTP {exc.code} {url}: {body[:300]}") from exc
        except urllib.error.URLError as exc:
            raise BiliApiError(f"请求失败 {url}: {exc}") from exc

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise BiliApiError(f"返回不是 JSON: {url}: {payload[:200]}") from exc

    @staticmethod
    def _expect_ok(payload: dict, action: str):
        code = payload.get("code", -1)
        if code != 0:
            message = payload.get("message") or payload.get("msg") or "未知错误"
            raise BiliApiError(f"{action}失败: code={code}, message={message}")
        if "data" in payload:
            return payload["data"]
        return None

    def login_info(self) -> dict:
        payload = self._request_json(
            "GET",
            "https://api.bilibili.com/x/web-interface/nav",
            headers={
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
            },
        )
        return self._expect_ok(payload, "Cookie 登录校验")

    def daily_reward_info(self) -> dict:
        payload = self._request_json(
            "GET",
            "https://api.bilibili.com/x/member/web/exp/reward",
            headers={
                "Referer": "https://account.bilibili.com/account/home",
                "Origin": "https://account.bilibili.com",
            },
        )
        return self._expect_ok(payload, "获取每日任务状态")

    def today_coin_exp(self) -> int:
        payload = self._request_json(
            "GET",
            "https://api.bilibili.com/x/web-interface/coin/today/exp",
            headers={
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
            },
        )
        data = self._expect_ok(payload, "获取今日投币经验")
        return int(data)

    def coin_balance(self) -> float:
        payload = self._request_json(
            "GET",
            "https://account.bilibili.com/site/getCoin",
            headers={"Referer": "https://account.bilibili.com/account/coin"},
        )
        data = self._expect_ok(payload, "获取硬币余额")
        return float(data.get("money") or 0)

    def get_ranking_video(self) -> dict:
        payload = self._request_json(
            "GET",
            "https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all",
            headers={
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
                "dnt": "1",
            },
        )
        data = self._expect_ok(payload, "获取排行榜视频")
        video_list = data.get("list") or []
        if not video_list:
            raise BiliApiError("排行榜视频为空")
        return random.choice(video_list)

    def video_detail(self, aid: int | str) -> dict:
        aid_str = str(aid)
        payload = self._request_json(
            "GET",
            f"https://api.bilibili.com/x/web-interface/view?aid={urllib.parse.quote(aid_str)}",
            headers={
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
            },
        )
        return self._expect_ok(payload, "获取视频详情")

    def donated_coin_count(self, aid: int | str) -> int:
        aid_str = str(aid)
        payload = self._request_json(
            "GET",
            f"https://api.bilibili.com/x/web-interface/archive/coins?aid={urllib.parse.quote(aid_str)}",
            headers={"Referer": "https://www.bilibili.com/"},
        )
        data = self._expect_ok(payload, "获取视频已投币数量")
        return int(data.get("multiply") or 0)

    def open_or_watch_video(
        self,
        *,
        aid: int,
        bvid: str,
        cid: int,
        mid: int,
        played_time: int,
        realtime: int,
        start_ts: int,
    ) -> None:
        csrf = self.required_cookie("bili_jct")
        query = urllib.parse.urlencode({"aid": aid, "played_time": played_time})
        payload = self._request_json(
            "POST",
            f"https://api.bilibili.com/x/click-interface/web/heartbeat?{query}",
            data={
                "aid": aid,
                "cid": cid,
                "bvid": bvid,
                "mid": mid,
                "csrf": csrf,
                "played_time": played_time,
                "real_played_time": realtime,
                "realtime": realtime,
                "start_ts": start_ts,
                "type": 3,
                "dt": 2,
                "play_type": 3,
            },
            headers={
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        self._expect_ok(payload, "上报视频观看进度")

    def share_video(self, aid: int) -> None:
        csrf = self.required_cookie("bili_jct")
        payload = self._request_json(
            "POST",
            "https://api.bilibili.com/x/web-interface/share/add",
            data={
                "aid": aid,
                "csrf": csrf,
                "eab_x": "1",
                "ramval": str(random.randint(3, 20)),
                "source": "web_normal",
                "ga": "1",
            },
            headers={
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
            },
        )
        self._expect_ok(payload, "分享视频")

    def add_coin(self, *, aid: int, bvid: str, like: bool) -> None:
        csrf = self.required_cookie("bili_jct")
        payload = self._request_json(
            "POST",
            "https://api.bilibili.com/x/web-interface/coin/add",
            data={
                "aid": aid,
                "multiply": 1,
                "select_like": 1 if like else 0,
                "cross_domain": "true",
                "csrf": csrf,
                "eab_x": "2",
                "ramval": "3",
                "source": "web_normal",
                "ga": "1",
            },
            headers={
                "Referer": f"https://www.bilibili.com/video/{bvid}/",
                "Origin": "https://www.bilibili.com",
            },
        )
        self._expect_ok(payload, "视频投币")


def pick_video_detail(client: BiliClient, max_attempts: int = 8) -> dict:
    last_error = None
    for _ in range(max_attempts):
        try:
            ranking_video = client.get_ranking_video()
            return client.video_detail(ranking_video["aid"])
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if last_error is None:
        raise BiliApiError("未能获取可用视频")
    raise BiliApiError(f"未能获取可用视频: {last_error}")


def bool_status(value: object) -> bool:
    return bool(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="B 站主站每日任务脚本")
    parser.add_argument("--status-only", action="store_true", help="只检查状态，不执行任务")
    args = parser.parse_args()

    load_env_file(ENV_PATH)
    if env_runtime_enabled():
        load_env_file(RUNTIME_ENV_PATH, override=True)

    cookie_str = os.getenv("BILIBILI_COOKIE", "").strip()
    if not cookie_str:
        print("未配置 BILIBILI_COOKIE，请先在 .env 中填入完整浏览器 Cookie。", file=sys.stderr)
        return 2

    client = BiliClient(cookie_str, os.getenv("BILIBILI_USER_AGENT", DEFAULT_USER_AGENT))

    for key in ("SESSDATA", "bili_jct", "DedeUserID"):
        client.required_cookie(key)

    watch_enabled = env_bool("BILIBILI_ENABLE_WATCH", True)
    share_enabled = env_bool("BILIBILI_ENABLE_SHARE", True)
    coin_enabled = env_bool("BILIBILI_ENABLE_COIN", True)
    like_on_coin = env_bool("BILIBILI_LIKE_ON_COIN", True)
    target_daily_coins = max(0, env_int("BILIBILI_TARGET_DAILY_COINS", 5))
    protected_coins = max(0, env_int("BILIBILI_PROTECTED_COINS", 5))

    user_info = client.login_info()
    daily_info = client.daily_reward_info()
    today_coin_exp = client.today_coin_exp()

    mid = int(user_info.get("mid") or client.required_cookie("DedeUserID"))
    level_info = user_info.get("level_info") or {}
    username = user_info.get("uname") or f"uid:{mid}"

    summary: dict[str, object] = {
        "ok": True,
        "user": username,
        "mid": mid,
        "level": level_info.get("current_level"),
        "login_done": bool_status(daily_info.get("login")),
        "watch_done": bool_status(daily_info.get("watch")),
        "share_done": bool_status(daily_info.get("share")),
        "coin_exp_today": today_coin_exp,
        "actions": [],
        "warnings": [],
    }

    if "buvid3" not in client.cookie_map and share_enabled:
        summary["warnings"].append(
            "Cookie 中缺少 buvid3，分享接口可能偶发 403。最好导出完整浏览器 Cookie。"
        )

    if args.status_only:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    need_watch = watch_enabled and not bool_status(daily_info.get("watch"))
    need_share = share_enabled and not bool_status(daily_info.get("share"))

    selected_video = None
    if need_watch or need_share:
        selected_video = pick_video_detail(client)
        summary["video"] = {
            "aid": selected_video.get("aid"),
            "bvid": selected_video.get("bvid"),
            "title": selected_video.get("title"),
        }

    if need_watch and selected_video:
        aid = int(selected_video["aid"])
        bvid = str(selected_video["bvid"])
        cid = int(selected_video.get("cid") or (selected_video.get("pages") or [{}])[0].get("cid"))
        duration = int(selected_video.get("duration") or 15)
        watch_seconds = max(1, min(duration, 15))
        played_time = random.randint(1, watch_seconds)
        start_ts = int(time.time())

        client.open_or_watch_video(
            aid=aid,
            bvid=bvid,
            cid=cid,
            mid=mid,
            played_time=0,
            realtime=0,
            start_ts=start_ts,
        )
        client.open_or_watch_video(
            aid=aid,
            bvid=bvid,
            cid=cid,
            mid=mid,
            played_time=played_time,
            realtime=played_time,
            start_ts=start_ts,
        )
        summary["actions"].append(f"观看视频成功: {selected_video.get('title')} ({played_time}s)")
        summary["watch_done"] = True

    if need_share and selected_video:
        if not need_watch:
            aid = int(selected_video["aid"])
            bvid = str(selected_video["bvid"])
            cid = int(selected_video.get("cid") or (selected_video.get("pages") or [{}])[0].get("cid"))
            client.open_or_watch_video(
                aid=aid,
                bvid=bvid,
                cid=cid,
                mid=mid,
                played_time=0,
                realtime=0,
                start_ts=int(time.time()),
            )
        client.share_video(int(selected_video["aid"]))
        summary["actions"].append(f"分享视频成功: {selected_video.get('title')}")
        summary["share_done"] = True

    coins_added = 0
    if coin_enabled and target_daily_coins > 0:
        current_coin_count = today_coin_exp // 10
        need_coin_count = max(0, target_daily_coins - current_coin_count)
        if need_coin_count > 0:
            balance = client.coin_balance()
            summary["coin_balance_before"] = balance
            allowed = max(0, int(balance) - protected_coins)
            need_coin_count = min(need_coin_count, allowed)

            tried_aids: set[int] = set()
            attempts = max(need_coin_count * 5, 5)
            for _ in range(attempts):
                if coins_added >= need_coin_count:
                    break

                video = pick_video_detail(client)
                aid = int(video["aid"])
                if aid in tried_aids:
                    continue
                tried_aids.add(aid)

                owner = video.get("owner") or {}
                owner_mid = int(owner.get("mid") or 0)
                if owner_mid == mid:
                    continue

                current_donated = client.donated_coin_count(aid)
                limit = 2 if int(video.get("copyright") or 0) == 1 else 1
                if current_donated >= limit:
                    continue

                client.add_coin(aid=aid, bvid=str(video["bvid"]), like=like_on_coin)
                coins_added += 1
                summary["actions"].append(f"投币成功: {video.get('title')}")

            summary["coin_added"] = coins_added
            summary["coin_exp_today_after"] = today_coin_exp + (coins_added * 10)

    if not summary["actions"]:
        summary["actions"].append("今日无需执行任务，或当前配置已全部完成")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BiliApiError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"ok": False, "error": f"未处理异常: {type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)
