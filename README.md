# SignAdmin 多站签到中控台

SignAdmin 多站签到中控台是一套独立的 Web 自动签到管理平台，用来统一管理 MT 管理器论坛、哔哩哔哩、52 破解、米游社等多成员、多站点、多账号的自动签到任务。

它的定位不是替代单个签到脚本，而是把这些脚本统一纳入一套可视化后台里，解决下面这些问题：

- 多个人、多账号时怎么统一管理
- 每个站点的签到时间怎么错峰安排
- Cookie 型站点怎么做静态兜底和运行时续命
- 每次执行成功了什么、失败在哪里，怎么回看
- 企业微信推送怎么按账号独立控制

## 功能概览

- 多成员管理
- 多站点账号管理
- 独立时间窗口与随机抖动
- 手动执行与定时调度并存
- Cookie 续命浏览器会话
- 企业微信结果推送
- 运行记录与原始日志回看
- 局域网 Web 后台

## 下载成品版

如果你只是想直接下载并运行，不想自己手动装环境，优先使用 GitHub Releases 里的 Linux 便携版。

下载后：

```bash
tar -xzf mt-bilibili-52pojie-miyoushe-web-auto-sign-*.tar.gz
cd mt-bilibili-52pojie-miyoushe-web-auto-sign-*
./start-web.sh
```

启动后可直接运行：

- `./start-web.sh`
- `./status-web.sh`
- `./stop-web.sh`
- `./show-lan-url.sh`
- `./run-dispatch.sh`

## 当前支持站点

- MT 管理器论坛
- 米游社
- 哔哩哔哩
- 52 破解

## 项目结构

```text
mt-bilibili-52pojie-miyoushe-web-auto-sign/
├── bin/                    启动、调度、初始化、自检脚本
├── docs/                   部署与发布文档
├── signadmin/              Web 后台主程序
├── templates/              页面模板
├── vendor/                 各站点脚本
├── data/                   运行时数据库与密钥（不提交）
├── logs/                   运行日志（不提交）
└── state/                  运行状态与浏览器 profile（不提交）
```

## 源码部署

### 1. 克隆项目

```bash
git clone https://github.com/676743748/mt-bilibili-52pojie-miyoushe-web-auto-sign.git
cd mt-bilibili-52pojie-miyoushe-web-auto-sign
```

### 2. 初始化依赖

```bash
./bin/bootstrap
```

### 3. 启动 Web

```bash
./bin/start-web
./bin/status-web
```

### 4. 查看局域网地址

```bash
./bin/show-lan-url
```

### 5. 首次访问

浏览器打开：

```text
http://你的IP:18080/
```

首次会进入 `/setup`，由你自己创建管理员账号和密码。

## 常用命令

启动 Web：

```bash
./bin/start-web
```

停止 Web：

```bash
./bin/stop-web
```

查看状态：

```bash
./bin/status-web
```

执行一次调度：

```bash
./bin/dispatch
```

模板和路由自检：

```bash
./.venv/bin/python ./bin/smoke-test.py
```

查看局域网地址：

```bash
./bin/show-lan-url
```

## 定时调度

推荐每 5 分钟跑一次调度器：

```cron
*/5 * * * * cd /path/to/mt-bilibili-52pojie-miyoushe-web-auto-sign && ./bin/dispatch >> ./logs/dispatch.log 2>&1
```

调度器会根据每个账号自己的时间窗口、抖动秒数和当天执行记录，决定是否真正执行。

## 运行数据说明

以下目录属于运行时数据，不应提交到公开仓库：

- `data/`
- `logs/`
- `state/`
- `.venv/`

项目已提供 `.gitignore`。

## 文档

- 详细部署：[`docs/DEPLOY.md`](./docs/DEPLOY.md)
- 对外发布：[`docs/PUBLISH.md`](./docs/PUBLISH.md)

## 第三方组件

站点脚本位于 `vendor/` 目录。

如果你对外发布源码，请保留各第三方组件原有的许可证文件和必要声明，尤其是：

- `vendor/MihoyoBBSTools/LICENSE`

## 备注

这个项目默认面向局域网使用场景。

如果你需要：

- 固定公网入口
- 更严格的权限体系
- 多实例分发
- 更复杂的推送编排

建议在当前基础上继续做网关、反代、鉴权和消息层扩展，而不是把运行时数据直接暴露出去。
