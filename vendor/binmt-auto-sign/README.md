# bbs.binmt.cc 自动签到

这个目录里是 `bbs.binmt.cc` 的本地签到脚本。

## 运行

```bash
cd /root/binmt-auto-sign
python3 binmt_sign.py
```

## 配置

账号密码写在 `.env`：

```env
BINMT_USERNAME=
BINMT_PASSWORD=
```

## 当前签到逻辑

脚本会按这个顺序执行：

1. 打开 Discuz 登录页
2. 读取登录表单里的 `formhash` 和真实提交地址
3. 登录账号
4. 打开 `k_misign-sign.html`
5. 找到 `plugin.php?id=k_misign:sign&operation=qiandao...`
6. 发送签到请求
7. 重新读取签到页并判断结果

## 日志

运行日志会写到 `logs/signin.log`。

## 定时执行

如果你要每天自动跑一次，可以加到 `crontab`：

```cron
5 8 * * * cd /root/binmt-auto-sign && /usr/bin/python3 /root/binmt-auto-sign/binmt_sign.py >> /root/binmt-auto-sign/logs/cron.log 2>&1
```
