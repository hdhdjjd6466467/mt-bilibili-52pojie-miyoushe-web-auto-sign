# B 站自动签到

这个目录放的是 B 站主站“每日任务”脚本，不是老式单按钮签到。

当前脚本支持：

- Cookie 登录校验
- 检查每日任务状态
- 自动观看视频
- 自动分享视频
- 自动投币

## 文件

- `bilibili_sign.py`：主脚本
- `.env.example`：配置模板

## 使用

1. 复制 `.env.example` 为 `.env`
2. 把完整 B 站浏览器 Cookie 填进 `BILIBILI_COOKIE`
3. 运行：

```bash
cd /root/bilibili-auto-sign
python3 bilibili_sign.py --status-only
python3 bilibili_sign.py
```

## Cookie 建议

至少要有：

- `SESSDATA`
- `bili_jct`
- `DedeUserID`

最好直接给完整浏览器 Cookie，因为分享接口缺少 `buvid3` 时可能偶发失败。
