from __future__ import annotations

from functools import wraps
import os
from typing import Any

from flask import Flask, flash, redirect, render_template, request, session, url_for

from . import config, runtime, store


config.ensure_directories()
store.init_db()

app = Flask(__name__, template_folder=str(config.TEMPLATE_DIR))
app.secret_key = config.get_flask_secret()


def _is_logged_in() -> bool:
    return bool(session.get("signadmin_logged_in"))


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not store.admin_is_configured():
            return redirect(url_for("setup_admin"))
        if not _is_logged_in():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapper


def _checkbox(name: str) -> bool:
    return request.form.get(name) == "on"


def _target_form_defaults() -> dict[str, Any]:
    return {
        "member_id": "",
        "site": "binmt",
        "display_name": "",
        "enabled": True,
        "schedule_enabled": True,
        "schedule_start": store.DEFAULTS.schedule_start,
        "schedule_end": store.DEFAULTS.schedule_end,
        "jitter_seconds": store.DEFAULTS.jitter_seconds,
        "notify_enabled": True,
        "config": {
            "watch_enabled": True,
            "share_enabled": True,
            "coin_enabled": True,
            "target_daily_coins": 5,
            "protected_coins": 0,
            "mihoyo_games": "genshin",
        },
        "secrets": {
            "username": "",
            "password": "",
            "static_cookie": "",
        },
    }


def _build_dashboard_stats(members: list[dict[str, Any]], targets: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    active_members = sum(1 for item in members if item.get("enabled"))
    active_targets = sum(1 for item in targets if item.get("enabled"))
    scheduled_targets = sum(1 for item in targets if item.get("enabled") and item.get("schedule_enabled"))
    notify_targets = sum(1 for item in targets if item.get("notify_enabled"))
    success_runs = sum(1 for item in runs if int(item.get("exit_code") or 0) == 0)
    failed_runs = len(runs) - success_runs
    success_rate = int(round((success_runs / len(runs)) * 100)) if runs else 0

    site_cards: list[dict[str, Any]] = []
    for site_key in config.SITE_ORDER:
        site_def = runtime.SITE_DEFS.get(site_key)
        if not site_def:
            continue
        matched = [item for item in targets if item.get("site") == site_key]
        if not matched:
            continue
        site_cards.append(
            {
                "site": site_key,
                "label": str(site_def["label"]),
                "count": len(matched),
                "active_count": sum(1 for item in matched if item.get("enabled")),
                "scheduled_count": sum(1 for item in matched if item.get("enabled") and item.get("schedule_enabled")),
            }
        )

    return {
        "member_total": len(members),
        "member_active": active_members,
        "target_total": len(targets),
        "target_active": active_targets,
        "target_scheduled": scheduled_targets,
        "target_notify": notify_targets,
        "run_success": success_runs,
        "run_failed": failed_runs,
        "run_success_rate": success_rate,
        "site_cards": site_cards,
    }


def _dashboard_filters(
    members: list[dict[str, Any]], targets: list[dict[str, Any]], runs: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    selected_site = request.args.get("site", "").strip()
    if selected_site not in runtime.SITE_DEFS:
        selected_site = ""

    selected_member_raw = request.args.get("member_id", "").strip()
    selected_member_id: int | None = None
    if selected_member_raw:
        try:
            selected_member_id = int(selected_member_raw)
        except ValueError:
            selected_member_raw = ""
            selected_member_id = None

    selected_run_status = request.args.get("run_status", "").strip().lower()
    if selected_run_status not in {"", "success", "failed"}:
        selected_run_status = ""

    notify_only = request.args.get("notify_only", "").strip().lower() in {"1", "true", "on", "yes"}

    filtered_targets = list(targets)
    filtered_runs = list(runs)

    if selected_site:
        filtered_targets = [item for item in filtered_targets if item.get("site") == selected_site]
        filtered_runs = [item for item in filtered_runs if item.get("site") == selected_site]

    if selected_member_id is not None:
        filtered_targets = [item for item in filtered_targets if int(item.get("member_id") or 0) == selected_member_id]
        member_target_ids = {int(item["id"]) for item in filtered_targets}
        filtered_runs = [item for item in filtered_runs if int(item.get("target_id") or 0) in member_target_ids]

    if notify_only:
        filtered_targets = [item for item in filtered_targets if item.get("notify_enabled")]
        target_ids = {int(item["id"]) for item in filtered_targets}
        filtered_runs = [item for item in filtered_runs if int(item.get("target_id") or 0) in target_ids]

    if selected_run_status == "success":
        filtered_runs = [item for item in filtered_runs if int(item.get("exit_code") or 0) == 0]
    elif selected_run_status == "failed":
        filtered_runs = [item for item in filtered_runs if int(item.get("exit_code") or 0) != 0]

    member_name = ""
    if selected_member_id is not None:
        member_name = next((str(item.get("name") or "") for item in members if int(item.get("id") or 0) == selected_member_id), "")

    filters = {
        "site": selected_site,
        "member_id": str(selected_member_id) if selected_member_id is not None else "",
        "member_name": member_name,
        "run_status": selected_run_status,
        "notify_only": notify_only,
        "has_filters": bool(selected_site or selected_member_id is not None or selected_run_status or notify_only),
    }
    return filters, filtered_targets, filtered_runs


@app.context_processor
def inject_globals():
    settings = store.get_settings()
    return {
        "app_title": settings.get("app_title", store.DEFAULT_APP_TITLE),
        "site_defs": runtime.SITE_DEFS,
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if not store.admin_is_configured():
        return redirect(url_for("setup_admin"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if store.verify_admin_credentials(username, password):
            session["signadmin_logged_in"] = True
            session["signadmin_username"] = username
            flash("登录成功。", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("管理员账号或密码不正确。", "error")
    return render_template("login.html")


@app.route("/setup", methods=["GET", "POST"])
def setup_admin():
    if store.admin_is_configured():
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not username:
            flash("管理员账号不能为空。", "error")
        elif len(password) < 6:
            flash("管理员密码至少 6 位。", "error")
        elif password != confirm_password:
            flash("两次输入的密码不一致。", "error")
        else:
            store.setup_admin(username, password)
            flash("管理员已创建，请登录。", "success")
            return redirect(url_for("login"))
    return render_template("setup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    members = store.list_members()
    targets = store.list_targets()
    runs = store.list_recent_runs(limit=30)
    filters, filtered_targets, filtered_runs = _dashboard_filters(members, targets, runs)
    return render_template(
        "dashboard.html",
        members=members,
        targets=filtered_targets,
        runs=filtered_runs,
        stats=_build_dashboard_stats(members, targets, runs),
        filters=filters,
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_view():
    current = store.get_settings()
    if request.method == "POST":
        store.update_settings(
            {
                "app_title": request.form.get("app_title", store.DEFAULT_APP_TITLE).strip() or store.DEFAULT_APP_TITLE,
                "wecom_webhook_url": request.form.get("wecom_webhook_url", "").strip(),
            }
        )
        username = request.form.get("admin_username", "").strip()
        password = request.form.get("new_password", "").strip()
        if username or password:
            store.update_admin_account(username=username or None, password=password or None)
        flash("设置已保存。", "success")
        return redirect(url_for("settings_view"))
    return render_template("settings.html", settings=current)


@app.route("/members/new", methods=["GET", "POST"])
@app.route("/members/<int:member_id>/edit", methods=["GET", "POST"])
@login_required
def member_form(member_id: int | None = None):
    member = store.get_member(member_id) if member_id else None
    if request.method == "POST":
        saved_id = store.save_member(
            member_id,
            name=request.form.get("name", ""),
            remark=request.form.get("remark", ""),
            enabled=_checkbox("enabled"),
        )
        flash("成员已保存。", "success")
        return redirect(url_for("target_form", member_id=saved_id))
    return render_template("member_form.html", member=member)


@app.post("/members/<int:member_id>/delete")
@login_required
def delete_member(member_id: int):
    member = store.get_member(member_id)
    if not member:
        flash("成员不存在。", "error")
        return redirect(url_for("dashboard"))

    target_ids = store.list_target_ids_for_member(member_id)
    for target_id in target_ids:
        runtime.purge_target_artifacts(target_id, store.list_run_log_paths_for_target(target_id))

    if store.delete_member(member_id):
        flash(f"成员已删除：{member['name']}。", "success")
    else:
        flash("成员删除失败。", "error")
    return redirect(url_for("dashboard"))


@app.route("/targets/new", methods=["GET", "POST"])
@app.route("/targets/<int:target_id>/edit", methods=["GET", "POST"])
@login_required
def target_form(target_id: int | None = None):
    target = store.get_target(target_id) if target_id else _target_form_defaults()
    if request.method == "POST":
        config_data = {
            "watch_enabled": _checkbox("watch_enabled"),
            "share_enabled": _checkbox("share_enabled"),
            "coin_enabled": _checkbox("coin_enabled"),
            "target_daily_coins": int(request.form.get("target_daily_coins", "5") or 5),
            "protected_coins": int(request.form.get("protected_coins", "0") or 0),
            "mihoyo_games": request.form.get("mihoyo_games", "genshin").strip() or "genshin",
        }
        secrets_data = {
            "username": request.form.get("username", "").strip(),
            "password": request.form.get("password", "").strip(),
            "static_cookie": request.form.get("static_cookie", "").strip(),
        }
        saved_id = store.save_target(
            target_id,
            member_id=int(request.form.get("member_id", "0")),
            site=request.form.get("site", "binmt").strip(),
            display_name=request.form.get("display_name", "").strip() or runtime.site_label(request.form.get("site", "")),
            enabled=_checkbox("enabled"),
            schedule_enabled=_checkbox("schedule_enabled"),
            schedule_start=request.form.get("schedule_start", store.DEFAULTS.schedule_start).strip(),
            schedule_end=request.form.get("schedule_end", store.DEFAULTS.schedule_end).strip(),
            jitter_seconds=int(request.form.get("jitter_seconds", str(store.DEFAULTS.jitter_seconds)) or 0),
            notify_enabled=_checkbox("notify_enabled"),
            config_data=config_data,
            secrets_data=secrets_data,
        )
        flash("站点账号已保存。", "success")
        return redirect(url_for("target_form", target_id=saved_id))

    members = store.list_members()
    if not target_id and request.args.get("member_id"):
        target["member_id"] = request.args.get("member_id")
    return render_template("target_form.html", target=target, members=members)


@app.post("/targets/<int:target_id>/delete")
@login_required
def delete_target(target_id: int):
    target = store.get_target(target_id)
    if not target:
        flash("站点账号不存在。", "error")
        return redirect(url_for("dashboard"))

    runtime.purge_target_artifacts(target_id, store.list_run_log_paths_for_target(target_id))
    if store.delete_target(target_id):
        flash(f"站点账号已删除：{target['display_name']}。", "success")
    else:
        flash("站点账号删除失败。", "error")
    return redirect(url_for("dashboard"))


@app.post("/targets/<int:target_id>/run")
@login_required
def run_target_now(target_id: int):
    target = store.get_target(target_id)
    if not target:
        flash("目标不存在。", "error")
        return redirect(url_for("dashboard"))
    result = runtime.run_target(target, trigger_type="manual")
    run_id = store.create_run(**result)
    settings = store.get_settings()
    if target["notify_enabled"] and settings.get("wecom_webhook_url"):
        try:
            runtime.send_wecom(
                settings["wecom_webhook_url"],
                runtime.build_notification_text(target, result["summary"]),
            )
        except Exception as exc:  # noqa: BLE001
            flash(f"企业微信推送失败: {exc}", "error")
    flash(f"执行完成: {result['summary']}", "success" if result["exit_code"] == 0 else "error")
    return redirect(url_for("run_detail", run_id=run_id))


@app.post("/targets/<int:target_id>/open-session")
@login_required
def open_session(target_id: int):
    target = store.get_target(target_id)
    if not target:
        flash("目标不存在。", "error")
        return redirect(url_for("dashboard"))
    result = runtime.open_browser_session(target)
    if result.get("ok"):
        flash(f"已启动浏览器会话，PID={result['pid']}。日志: {result['log_path']}", "success")
    else:
        flash(str(result.get("message") or "无法打开浏览器会话。"), "error")
    return redirect(url_for("target_form", target_id=target_id))


@app.route("/runs/<int:run_id>")
@login_required
def run_detail(run_id: int):
    run = store.get_run(run_id)
    if not run:
        flash("运行记录不存在。", "error")
        return redirect(url_for("dashboard"))
    log_text = store.read_log(run["log_path"])
    return render_template("run_detail.html", run=run, log_text=log_text)


def main() -> int:
    from waitress import serve

    host = os.environ.get("SIGNADMIN_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port_text = os.environ.get("SIGNADMIN_PORT", "18080").strip() or "18080"
    port = int(port_text)
    serve(app, host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
