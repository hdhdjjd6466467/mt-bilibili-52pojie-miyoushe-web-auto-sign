# SignAdmin 多站签到中控台部署说明

这份文档按“全新机器从零部署”来写，看完即可把项目跑起来。

## 1. 运行环境

- Linux
- Python 3.10 及以上
- Node.js 20 及以上
- npm
- `tesseract` 可选
  - 只影响 52 的验证码辅助识别
  - 没装也能运行，只是少一个 OCR 兜底

## 2. 获取项目

```bash
git clone https://github.com/676743748/mt-bilibili-52pojie-miyoushe-web-auto-sign.git
cd mt-bilibili-52pojie-miyoushe-web-auto-sign
```

## 3. 一键初始化

项目已经带了初始化脚本：

```bash
./bin/bootstrap
```

它会完成这些事情：

- 创建顶层 `.venv`
- 安装 Web 后台依赖
- 安装 52 的 Node 依赖和 Playwright Firefox
- 创建 `vendor/MihoyoBBSTools/.venv`
- 安装米游社脚本依赖

## 4. 启动 Web

前台启动：

```bash
./bin/web
```

后台启动：

```bash
./bin/start-web
./bin/status-web
```

停止：

```bash
./bin/stop-web
```

默认监听：

```text
0.0.0.0:18080
```

## 5. 找局域网访问地址

直接运行：

```bash
./bin/show-lan-url
```

如果当前连着局域网，它会直接输出可访问地址，例如：

```text
http://192.168.1.23:18080/
```

## 6. 首次初始化

浏览器打开：

```text
http://你的IP:18080/
```

首次访问会跳到 `/setup`，由你自己创建管理员账号和密码。

## 7. 添加签到对象

后台数据模型分两层：

- 成员
  - 用来承载“一个人 / 一组账号 / 一个主体”
- 站点账号
  - 成员下面的具体签到对象
  - 例如 MT、米游社、B 站、52

推荐顺序：

1. 先建成员
2. 再给成员挂站点账号
3. 配时间窗口、随机抖动和推送
4. 对 Cookie 型站点保留一份静态 Cookie 兜底
5. 用“打开会话”补运行时 Cookie

## 8. 定时调度

这个项目的定时执行入口是：

```bash
./bin/dispatch
```

推荐每 5 分钟跑一次：

```cron
*/5 * * * * cd /path/to/mt-bilibili-52pojie-miyoushe-web-auto-sign && ./bin/dispatch >> ./logs/dispatch.log 2>&1
```

说明：

- 调度器不会无脑全跑
- 它会按每个账号自己的时间窗口和抖动值判断是否到点
- 同一天已经执行过的账号不会重复执行

## 9. 开机自启

如果你想让 Web 在重启后自动起来，最简单有两种方案。

方案一：`@reboot`

```cron
@reboot cd /path/to/mt-bilibili-52pojie-miyoushe-web-auto-sign && ./bin/start-web >> ./logs/web-start.log 2>&1
```

方案二：systemd

示例：

```ini
[Unit]
Description=multi-site auto-sign web
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/mt-bilibili-52pojie-miyoushe-web-auto-sign
ExecStart=/path/to/mt-bilibili-52pojie-miyoushe-web-auto-sign/.venv/bin/python -m signadmin.web
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## 10. 站点依赖说明

### MT 管理器论坛

- 主要依赖账号密码
- 后台里填 `username` 和 `password`

### 米游社

- 使用 `vendor/MihoyoBBSTools`
- 后台里建议保留静态 Cookie 兜底
- 也可以用浏览器登录会话补运行时 Cookie

### 哔哩哔哩

- 后台里填完整 Cookie
- 支持观看、分享、投币开关
- 支持目标投币数和保留硬币数

### 52 破解

- 使用 `vendor/52pojie-auto-sign`
- 支持静态 Cookie 兜底
- 支持浏览器登录会话续命
- 支持 OCR 验证辅助
- 52 的 Python OCR 依赖默认走主项目 `.venv`

## 11. 数据目录

运行时会自动生成这些目录：

- `data/`
  - SQLite 数据库
  - 加密密钥
  - Flask secret
- `logs/`
  - Web 日志
  - 单次运行日志
  - 浏览器会话日志
- `state/`
  - 每个目标的运行时环境
  - Cookie 续命状态
  - 浏览器 profile

这些目录都不应该提交到公开仓库。

## 12. 发布前自检

模板和关键页面渲染检查：

```bash
./.venv/bin/python ./bin/smoke-test.py
```

检查局域网访问地址：

```bash
./bin/show-lan-url --verbose
```

## 13. 常见问题

### 访问不到 Web

- 确认 `./bin/status-web` 显示 `running`
- 确认端口 `18080` 没被防火墙拦
- 确认你访问的是当前机器所在网络的实际 IP

### 52 浏览器会话打不开

- 确认当前机器有可用的图形环境
- 没有桌面时，使用 VNC 或 Xvfb
- 确认 Playwright Firefox 已安装

### 米游社执行失败

- 确认 `vendor/MihoyoBBSTools/.venv` 已创建
- 确认 Cookie 仍有效
- 确认游戏列表填写格式正确，例如 `genshin,honkai_sr,zzz`

### 调度没有跑

- 先手动执行 `./bin/dispatch`
- 再检查你的 cron 是否生效
- 查看 `logs/dispatch.log`

## 14. 升级建议

升级时推荐只做三件事：

1. 先备份 `data/`
2. 再备份 `state/`
3. 然后替换代码并重新执行 `./bin/bootstrap`

只要 `data/` 和 `state/` 还在，后台账号配置和大部分运行态就还能接上。
