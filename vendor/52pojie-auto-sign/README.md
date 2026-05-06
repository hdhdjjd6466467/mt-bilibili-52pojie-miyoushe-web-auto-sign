# 52pojie 自动签到

这个项目用 Playwright 的 Firefox 内核执行 52pojie 每日任务签到。
手动排查默认建议有窗口模式，定时任务建议走无头模式。

## 当前结论

- 52pojie 当前的脚本化账号密码登录会被验证码拦住。
- 项目已经内置了账号密码登录兜底，但实际长期可用的方式应该是导入浏览器里已经登录好的 Cookie。
- 签到流程按 Discuz 任务页处理：
  - `home.php?mod=task&do=apply&id=2`
  - `home.php?mod=task&do=draw&id=2`

## 安装

```bash
cd /root/52pojie-auto-sign
npm install
```

## 配置

复制一份环境变量模板：

```bash
cp .env.example .env
```

推荐优先填写 `POJIE_COOKIE`。

```env
POJIE_USERNAME=
POJIE_PASSWORD=
POJIE_COOKIE=
POJIE_HEADLESS=false
POJIE_HUMAN_MODE=true
POJIE_KEEP_OPEN_MS=0
POJIE_SLOW_MO_MS=0
POJIE_TIMEZONE_ID=Asia/Shanghai
POJIE_VIEWPORT_WIDTH=1366
POJIE_VIEWPORT_HEIGHT=768
POJIE_RETRY_COUNT=3
POJIE_RETRY_SLEEP_SECONDS=120
```

说明：

- `POJIE_HEADLESS=false`：默认打开真实浏览器窗口
- `POJIE_HUMAN_MODE=true`：启用更像真人的停顿、慢速输入和轻微滚动
- `POJIE_KEEP_OPEN_MS`：运行结束后额外停留多久，方便你在 VNC 里观察或手动过验证
- `POJIE_SLOW_MO_MS`：每个 Playwright 动作额外减速多少毫秒
- `POJIE_TIMEZONE_ID`：浏览器上下文时区，默认 `Asia/Shanghai`
- `POJIE_VIEWPORT_WIDTH` / `POJIE_VIEWPORT_HEIGHT`：浏览器窗口尺寸
- `POJIE_RETRY_COUNT`：`cron` 模式最多重试几次
- `POJIE_RETRY_SLEEP_SECONDS`：重试之间等待几秒

## 导入 Cookie

1. 在你常用浏览器里先登录 `https://www.52pojie.cn/`
2. 打开开发者工具，找到请求头里的 `Cookie`
3. 复制整段 Cookie 字符串到 `.env` 里的 `POJIE_COOKIE`
4. 执行：

```bash
DISPLAY=:1 npm run import-cookie
```

成功后会把会话保存到 `.auth/storage-state.json`。

## 运行签到

```bash
DISPLAY=:1 npm run signin
```

如果你想固定用有窗口模式，也可以直接运行：

```bash
/root/52pojie-auto-sign/run-headed.sh
```

给 `cron` 跑的入口：

```bash
/root/52pojie-auto-sign/run-cron.sh
```

`run-cron.sh` 现在默认会走有窗口模式，并继承 `run-headed.sh` 的真人化参数。

脚本会按下面顺序处理：

1. 优先读取 `.auth/storage-state.json`
2. 如果没有已保存会话，尝试导入 `POJIE_COOKIE`
3. 如果还没有登录状态，再尝试使用账号密码登录
4. 登录后依次访问任务页、申请任务页、领奖页

运行日志会写到 `logs/signin.log`。

## 定时执行

当前这台机器实际时区还是 `UTC`。如果你要它在北京时间 `00:03` 执行，那么 `cron` 应该写成 `16:03 UTC`。

```bash
crontab -e
```

加入这一行：

```cron
3 16 * * * cd /root/52pojie-auto-sign && /root/52pojie-auto-sign/run-cron.sh >> /root/52pojie-auto-sign/logs/cron.log 2>&1
```

如果以后你把系统时区切成 `Asia/Shanghai`，同一个目标时间就该改回：

```cron
3 0 * * * cd /root/52pojie-auto-sign && /root/52pojie-auto-sign/run-cron.sh >> /root/52pojie-auto-sign/logs/cron.log 2>&1
```

## 排错

- `login_failed`: 通常表示站点验证码挡住了脚本化登录。
- `login_required`: 表示本地没有有效会话，也没有提供可用 Cookie。
- `waf_verification_required`: 表示已登录会话访问任务页时被站点 WAF 文本验证码拦截。
- `run-cron.sh` 会先检查 `python3`、`ddddocr`、`Pillow` 是否存在，再以有窗口模式做 3 次重试。
- 遇到 WAF 验证码时，脚本会优先使用 OCR 主候选；如果候选只存在大小写差异，会自动顺带尝试同组备选。
- 如果你要人工看浏览器过程，把 `POJIE_KEEP_OPEN_MS` 调大，比如 `60000`。
- 如果签到失效，先在浏览器重新登录一次，再更新 `POJIE_COOKIE` 并执行 `npm run import-cookie`。
