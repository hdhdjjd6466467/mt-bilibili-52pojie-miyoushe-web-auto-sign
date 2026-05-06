# 对外发布说明

这份文档只处理“怎么把当前项目整理成公开仓库”。

## 1. 不要公开的内容

以下目录属于运行时数据，不能进公开仓库：

- `data/`
- `logs/`
- `state/`
- `.venv/`
- `vendor/52pojie-auto-sign/node_modules/`
- `vendor/52pojie-auto-sign/.auth/`

项目根目录已经提供 `.gitignore`，新建仓库后这些内容默认会被忽略。

## 2. 先做本地检查

模板渲染：

```bash
./.venv/bin/python ./bin/smoke-test.py
```

Web 启动：

```bash
./bin/start-web
./bin/status-web
```

调度器检查：

```bash
./bin/dispatch
```

## 3. 发布前建议

建议先确认以下几点：

- README 已改成你希望对外展示的内容
- 仓库名、项目名、页面标题已经统一
- 运行中的真实账号和 Cookie 没有落在仓库文件里
- `data/` 没有被误提交
- `logs/` 没有被误提交

## 4. 第三方组件

这个项目内部包含多个站点脚本目录，尤其是：

- `vendor/MihoyoBBSTools`
- `vendor/52pojie-auto-sign`
- `vendor/bilibili-auto-sign`
- `vendor/binmt-auto-sign`

需要注意：

- `vendor/MihoyoBBSTools` 已自带上游 `LICENSE`
- 这个许可证文件不能删
- `node_modules` 不建议提交，公开仓库里保留 `package.json` 和 `package-lock.json` 即可

## 5. 推荐发布流程

```bash
git init
git add .
git status
git commit -m "init: publish multi-site auto-sign web"
```

在 `git add .` 之后，重点再看一遍：

- 有没有把 `data/` 加进去
- 有没有把 `logs/` 加进去
- 有没有把 `state/` 加进去
- 有没有把你本机的 `.venv/` 加进去

## 6. 关于协议

如果你要把它作为标准开源项目公开，发布前最好补一个顶层 `LICENSE`。

仓库里已经放了一个可直接使用的顶层协议文件：

```text
LICENSE
```
当前版本已经按 GitHub 账号 `676743748` 填好了版权声明。

## 7. 对外说明建议

如果你准备让别人直接部署，仓库首页最少要保证这些信息清楚：

- 它是做什么的
- 支持哪些站点
- 依赖什么环境
- 怎么初始化
- 怎么启动 Web
- 怎么配置 cron
- 运行数据放在哪里

这几个点在 `README.md` 和 `docs/DEPLOY.md` 里都已经补齐了。
