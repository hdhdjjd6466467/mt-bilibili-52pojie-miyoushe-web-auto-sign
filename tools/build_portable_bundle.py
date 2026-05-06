#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Iterable
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
SLUG = "mt-bilibili-52pojie-miyoushe-web-auto-sign"
NODE_VERSION = "22.22.2"
PYTHON_STANDALONE_TAG = "20260504"
PYTHON_VERSION = "3.13.13"


PLATFORMS = {
    "linux-x64": {
        "archive_ext": ".tar.gz",
        "python_url": f"https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_STANDALONE_TAG}/cpython-{PYTHON_VERSION}+{PYTHON_STANDALONE_TAG}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "node_url": f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz",
        "python_exec": "runtime/python/bin/python3",
        "node_exec": "runtime/node/bin/node",
        "npm_exec": "runtime/node/bin/npm",
        "family": "linux",
    },
    "linux-aarch64": {
        "archive_ext": ".tar.gz",
        "python_url": f"https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_STANDALONE_TAG}/cpython-{PYTHON_VERSION}+{PYTHON_STANDALONE_TAG}-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "node_url": f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-arm64.tar.xz",
        "python_exec": "runtime/python/bin/python3",
        "node_exec": "runtime/node/bin/node",
        "npm_exec": "runtime/node/bin/npm",
        "family": "linux",
    },
    "windows-x64": {
        "archive_ext": ".zip",
        "python_url": f"https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_STANDALONE_TAG}/cpython-{PYTHON_VERSION}+{PYTHON_STANDALONE_TAG}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
        "node_url": f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip",
        "python_exec": "runtime/python/python.exe",
        "node_exec": "runtime/node/node.exe",
        "npm_exec": "runtime/node/npm.cmd",
        "family": "windows",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--skip-test", action="store_true")
    return parser.parse_args()


def print_step(message: str) -> None:
    print(message, flush=True)


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, check=True)


def run_capture(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, text=True, capture_output=True, check=True)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "portable-builder"})
    with urllib.request.urlopen(req, timeout=600) as response, dest.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(dest_dir)
        return
    if archive_path.suffixes[-2:] == [".tar", ".gz"] or archive_path.suffixes[-2:] == [".tar", ".xz"]:
        with tarfile.open(archive_path, "r:*") as archive:
            archive.extractall(dest_dir)
        return
    raise ValueError(f"unsupported archive: {archive_path}")


def copy_project(target_dir: Path) -> None:
    ignore = shutil.ignore_patterns(
        ".git",
        ".venv",
        "data",
        "logs",
        "state",
        "dist",
        "runtime",
        "__pycache__",
        "*.pyc",
        "node_modules",
    )
    shutil.copytree(ROOT, target_dir, ignore=ignore, dirs_exist_ok=True)
    (target_dir / "data").mkdir(exist_ok=True)
    (target_dir / "logs").mkdir(exist_ok=True)
    (target_dir / "state").mkdir(exist_ok=True)
    shutil.rmtree(target_dir / "vendor" / "MihoyoBBSTools" / ".venv", ignore_errors=True)
    shutil.rmtree(target_dir / "vendor" / "52pojie-auto-sign" / "node_modules", ignore_errors=True)


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def install_python_packages(package_dir: Path, python_exe: Path) -> None:
    env = os.environ.copy()
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], cwd=package_dir, env=env)
    run([str(python_exe), "-m", "pip", "install", "-r", str(package_dir / "requirements.txt")], cwd=package_dir, env=env)
    run(
        [str(python_exe), "-m", "pip", "install", "-r", str(package_dir / "vendor" / "MihoyoBBSTools" / "requirements.txt")],
        cwd=package_dir,
        env=env,
    )


def install_node_packages(package_dir: Path, npm_exe: Path, node_exe: Path) -> None:
    vendor_dir = package_dir / "vendor" / "52pojie-auto-sign"
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(package_dir / "runtime" / "ms-playwright")
    env["PATH"] = str(node_exe.parent) + os.pathsep + env.get("PATH", "")
    run([str(npm_exe), "install", "--omit=dev"], cwd=vendor_dir, env=env)
    run([str(node_exe), str(vendor_dir / "node_modules" / "playwright" / "cli.js"), "install", "firefox"], cwd=vendor_dir, env=env)


def write_linux_launchers(package_dir: Path) -> None:
    files = {
        "start-web.sh": """#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
"$ROOT/bin/start-web"
echo
"$ROOT/bin/status-web" || true
echo
"$ROOT/bin/show-lan-url" || true
""",
        "status-web.sh": """#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/bin/status-web"
""",
        "stop-web.sh": """#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/bin/stop-web"
""",
        "run-dispatch.sh": """#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/bin/dispatch"
""",
        "show-lan-url.sh": """#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/bin/show-lan-url"
""",
        "README-START.txt": """MT管理器 / 哔哩哔哩 / 52破解 / 米游社 Web 自动签到管理平台

使用方式:
1. 解压压缩包
2. 进入目录
3. 运行 ./start-web.sh
4. 浏览器打开脚本输出的局域网地址
5. 首次访问进入 /setup 创建管理员账号和密码
""",
    }
    for name, content in files.items():
        path = package_dir / name
        path.write_text(content, encoding="utf-8")
        if path.suffix == ".sh":
            path.chmod(0o755)


def write_windows_launchers(package_dir: Path) -> None:
    windows_dir = package_dir / "windows"
    windows_dir.mkdir(parents=True, exist_ok=True)

    env_block = r"""$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'runtime\python\python.exe'
$Node = Join-Path $Root 'runtime\node\node.exe'
$env:SIGNADMIN_PYTHON_BIN = $Python
$env:SIGNADMIN_NODE_BIN = $Node
$env:NODE_BIN = $Node
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Root 'runtime\ms-playwright'
"""

    ps_scripts = {
        "start-web.ps1": rf"""param([int]$Port = 18080)
$ErrorActionPreference = 'Stop'
{env_block}
$PidFile = Join-Path $Root 'state\web.pid'
$OutLog = Join-Path $Root 'logs\web.out.log'
$ErrLog = Join-Path $Root 'logs\web.err.log'
New-Item -ItemType Directory -Force (Join-Path $Root 'state') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Root 'logs') | Out-Null
if (Test-Path $PidFile) {{
  $ExistingPid = (Get-Content $PidFile -Raw).Trim()
  if ($ExistingPid) {{
    $Process = Get-Process -Id ([int]$ExistingPid) -ErrorAction SilentlyContinue
    if ($Process) {{
      Write-Host "auto-sign web already running pid=$ExistingPid"
      exit 0
    }}
  }}
  Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}}
$env:SIGNADMIN_PORT = [string]$Port
$Process = Start-Process -FilePath $Python -ArgumentList '-m','signadmin.web' -WorkingDirectory $Root -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -PassThru -WindowStyle Hidden
Set-Content -Path $PidFile -Value $Process.Id -NoNewline
Start-Sleep -Seconds 2
if (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue) {{
  Write-Host "auto-sign web started pid=$($Process.Id)"
}} else {{
  Write-Error "auto-sign web failed to start"
  exit 1
}}
""",
        "status-web.ps1": r"""$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root 'state\web.pid'
if (-not (Test-Path $PidFile)) {
  Write-Host 'stopped'
  exit 1
}
$Pid = (Get-Content $PidFile -Raw).Trim()
if ($Pid -and (Get-Process -Id ([int]$Pid) -ErrorAction SilentlyContinue)) {
  Write-Host "running pid=$Pid"
  exit 0
}
Write-Host 'stale pid file'
exit 1
""",
        "stop-web.ps1": r"""$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root 'state\web.pid'
if (-not (Test-Path $PidFile)) {
  Write-Host 'auto-sign web not running'
  exit 0
}
$Pid = (Get-Content $PidFile -Raw).Trim()
if ($Pid) {
  Stop-Process -Id ([int]$Pid) -Force
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host 'auto-sign web stopped'
""",
        "run-dispatch.ps1": rf"""$ErrorActionPreference = 'Stop'
{env_block}
& $Python -m signadmin.dispatch
""",
        "show-lan-url.ps1": r"""param([int]$Port = 18080)
$ErrorActionPreference = 'Stop'
$Entries = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {
  $_.IPAddress -ne '127.0.0.1' -and
  $_.IPAddress -notlike '169.254.*' -and
  $_.InterfaceAlias -notmatch 'Loopback'
} | Select-Object -ExpandProperty IPAddress -Unique
if ($Entries) {
  Write-Host '当前可在局域网打开的网址:'
  foreach ($Ip in $Entries) {
    Write-Host ("http://{0}:{1}/" -f $Ip, $Port)
  }
  exit 0
}
Write-Host '当前没有检测到可用的局域网 IPv4 地址。'
exit 1
""",
    }

    for name, content in ps_scripts.items():
        (windows_dir / name).write_text(content, encoding="utf-8")

    bat_files = {
        "start-web.bat": "@echo off\r\npowershell -ExecutionPolicy Bypass -File \"%~dp0windows\\start-web.ps1\" %*\r\nif errorlevel 1 exit /b %errorlevel%\r\npowershell -ExecutionPolicy Bypass -File \"%~dp0windows\\status-web.ps1\"\r\npowershell -ExecutionPolicy Bypass -File \"%~dp0windows\\show-lan-url.ps1\" %*\r\n",
        "status-web.bat": "@echo off\r\npowershell -ExecutionPolicy Bypass -File \"%~dp0windows\\status-web.ps1\"\r\n",
        "stop-web.bat": "@echo off\r\npowershell -ExecutionPolicy Bypass -File \"%~dp0windows\\stop-web.ps1\"\r\n",
        "run-dispatch.bat": "@echo off\r\npowershell -ExecutionPolicy Bypass -File \"%~dp0windows\\run-dispatch.ps1\" %*\r\n",
        "show-lan-url.bat": "@echo off\r\npowershell -ExecutionPolicy Bypass -File \"%~dp0windows\\show-lan-url.ps1\" %*\r\n",
        "README-START.txt": "MT管理器 / 哔哩哔哩 / 52破解 / 米游社 Web 自动签到管理平台\r\n\r\n使用方式:\r\n1. 解压压缩包\r\n2. 双击 start-web.bat\r\n3. 浏览器打开脚本输出的局域网地址\r\n4. 首次访问进入 /setup 创建管理员账号和密码\r\n",
    }

    for name, content in bat_files.items():
        (package_dir / name).write_text(content, encoding="utf-8", newline="")


def archive_package(package_dir: Path, archive_path: Path, family: str) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(package_dir.rglob("*")):
                archive.write(file_path, package_dir.name / file_path.relative_to(package_dir))
        return
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(package_dir, arcname=package_dir.name)


def extract_for_test(archive_path: Path, dest_dir: Path) -> Path:
    ensure_clean_dir(dest_dir)
    extract_archive(archive_path, dest_dir)
    children = [item for item in dest_dir.iterdir() if item.is_dir()]
    if len(children) != 1:
        raise RuntimeError(f"unexpected archive layout: {children}")
    return children[0]


def wait_for_setup(port: int, timeout_seconds: int = 60) -> None:
    import urllib.request

    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/setup", timeout=5) as response:
                body = response.read().decode("utf-8", "replace")
            if response.status == 200 and ("管理员" in body or "/setup" in body):
                return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"setup page did not become ready: {last_error}")


def test_package(extracted_dir: Path, platform_key: str) -> None:
    port = 18082 if platform_key != "linux-aarch64" else 18083
    env = os.environ.copy()
    env["SIGNADMIN_PORT"] = str(port)

    if PLATFORMS[platform_key]["family"] == "windows":
        subprocess.run(["cmd", "/c", "start-web.bat"], cwd=str(extracted_dir), env=env, check=True)
        try:
            wait_for_setup(port)
        finally:
            subprocess.run(["cmd", "/c", "stop-web.bat"], cwd=str(extracted_dir), env=env, check=False)
        return

    subprocess.run(["bash", "start-web.sh"], cwd=str(extracted_dir), env=env, check=True)
    try:
        wait_for_setup(port)
    finally:
        subprocess.run(["bash", "stop-web.sh"], cwd=str(extracted_dir), env=env, check=False)


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def move_single_child(parent: Path, expected_name: str) -> Path:
    child = parent / expected_name
    if child.exists():
        return child
    entries = [item for item in parent.iterdir() if item.is_dir()]
    if len(entries) != 1:
        raise RuntimeError(f"unable to resolve extracted directory under {parent}")
    return entries[0]


def build_package(platform_key: str, version: str, skip_test: bool) -> tuple[Path, Path]:
    cfg = PLATFORMS[platform_key]
    package_name = f"{SLUG}-{version}-{platform_key}"
    package_dir = DIST_DIR / package_name
    archive_path = DIST_DIR / f"{package_name}{cfg['archive_ext']}"
    checksum_path = DIST_DIR / f"{package_name}{cfg['archive_ext']}.sha256"

    ensure_clean_dir(package_dir)
    print_step(f"[1/7] stage project: {package_name}")
    copy_project(package_dir)

    runtime_dir = package_dir / "runtime"
    ensure_clean_dir(runtime_dir)

    with tempfile.TemporaryDirectory(prefix="portable-builder-") as temp_dir_text:
        temp_dir = Path(temp_dir_text)

        print_step("[2/7] download portable python")
        python_archive = temp_dir / Path(cfg["python_url"]).name
        download(cfg["python_url"], python_archive)
        extract_archive(python_archive, runtime_dir)

        print_step("[3/7] download node runtime")
        node_archive = temp_dir / Path(cfg["node_url"]).name
        download(cfg["node_url"], node_archive)
        node_extract_dir = temp_dir / "node-extract"
        extract_archive(node_archive, node_extract_dir)
        extracted_node_dir = move_single_child(node_extract_dir, "node")
        shutil.move(str(extracted_node_dir), str(runtime_dir / "node"))

    python_exe = package_dir / cfg["python_exec"]
    node_exe = package_dir / cfg["node_exec"]
    npm_exe = package_dir / cfg["npm_exec"]

    print_step("[4/7] install python packages")
    install_python_packages(package_dir, python_exe)

    print_step("[5/7] install node packages and firefox")
    install_node_packages(package_dir, npm_exe, node_exe)

    print_step("[6/7] write launchers")
    if cfg["family"] == "windows":
        write_windows_launchers(package_dir)
    else:
        write_linux_launchers(package_dir)

    print_step("[7/7] create archive")
    if archive_path.exists():
        archive_path.unlink()
    archive_package(package_dir, archive_path, cfg["family"])
    checksum_path.write_text(f"{sha256_file(archive_path)}  {archive_path.name}\n", encoding="utf-8")

    if not skip_test:
        print_step("[test] extract and verify startup")
        with tempfile.TemporaryDirectory(prefix="portable-test-") as test_dir_text:
            extracted_dir = extract_for_test(archive_path, Path(test_dir_text))
            test_package(extracted_dir, platform_key)

    print(archive_path)
    print(checksum_path)
    return archive_path, checksum_path


def main() -> int:
    args = parse_args()
    build_package(args.platform, args.version, args.skip_test)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
