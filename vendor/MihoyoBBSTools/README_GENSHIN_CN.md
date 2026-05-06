# 原神自动签到最简配置

这个仓库已经被整理成“只跑原神国服签到”的模式。

## 已经完成的部分

- 已创建虚拟环境：`/root/MihoyoBBSTools/.venv`
- 已安装运行依赖
- 已生成最简配置：`/root/MihoyoBBSTools/config/config.yaml`
- 已关闭米游社社区任务
- 已关闭星铁、绝区零、崩坏系列、云游戏等其他模块
- 已保留国服原神签到

## 你还需要做的事

把米游社 Cookie 填到：

`/root/MihoyoBBSTools/config/config.yaml`

找到这一行：

```yaml
cookie: "PUT_MIHOYO_COOKIE_HERE"
```

替换成你的真实 Cookie。

## 运行

```bash
/root/MihoyoBBSTools/run_genshin.sh
```

## 获取 Cookie

推荐按仓库原 README 的方式抓：

1. 浏览器无痕模式登录米游社
2. 打开 `https://www.miyoushe.com/ys/`
3. F12 打开开发者工具
4. 在网络请求里筛选 `getUserGameUnreadCount`
5. 复制请求头里的整段 `Cookie`

## 说明

当前配置只做原神游戏签到，所以先不需要 `stoken`。
如果后面你还想开米游社社区任务，再补 `stoken / stuid / mid` 就行。
