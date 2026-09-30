# knock-knock 敲门机器人

基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent) cron 机制构建的
QQ 主动问候小机器人：每小时随机敲 1~3 次门，观察你在做什么，然后以自然的方式
发一条 QQ 主动消息问候。

## 背景

个人助理长时间后台运行后，用户希望它不只是"被叫醒"，而是像朋友一样不定期
主动探个头。本项目的诉求：

- 敲门间隔随机（避免定时器感）
- 敲门内容自然（先观察前台窗口 + 活动状态簿，结合当前时间说话）
- 正在聊天时绝不插嘴（且跳过照计次数，不补敲）

## 架构

```
cron (every 10m)
  └─ monitor: knock_monitor.py        # 门控，输出 KNOCK / WAIT
       ├─ 小时计划：每小时随机 1~3 个敲门位（10 分钟粒度）
       ├─ 聊天避让：查 Hermes 会话库最近活动，3 分钟内视为聊天中 → 跳过但计数
       └─ 状态持久化：knock_state.json（跨重启保留计划）
  └─ agent 被 KNOCK 唤醒后：
       ├─ 查活动状态簿（activity_state.json）+ 当前时间
       ├─ 查前台窗口（PowerShell Get-Process MainWindowTitle）
       └─ 通过 qq_push.py 发送 QQ 主动消息
```

## 组件

| 文件 | 作用 |
|------|------|
| `scripts/qq_push.py` | QQ 主动消息推送（UTF-8 文件 → Python 直发） |
| `scripts/knock_monitor.py` | 敲门门控（小时计划 + 聊天避让 + 计数） |
| `scripts/bg3_download_monitor.py` | 一次性任务监控示例（Steam 下载完成检测） |

## 部署

1. 安装 Hermes Agent，注册 QQ 机器人（q.qq.com），获得 AppID / AppSecret
2. 填写 `.env`（参考 `.env.example`）：
   `QQ_APP_ID` / `QQ_CLIENT_SECRET` / `QQ_USER_OPENID`
3. **用户在 QQ 客户端对机器人开启「允许主动发送」**（必需，否则推送被拒）
4. 修改 `knock_monitor.py` 顶部的三个路径常量指向本机 Hermes 目录
5. 创建 cron 任务（agent 模式，monitor 指向 knock_monitor.py，
   schedule `every 10m`），prompt 要求 agent 在 KNOCK 时查状态簿/前台窗口后
   调用 `qq_push.py` 发消息

## 踩坑记录（都写进了代码注释）

1. **主动消息不要带 `msg_id`**：`msg_id`/`event_id` 是被动回复专用字段，
   主动消息带上会返回 `40034024 请求参数msg_id无效或越权`
2. **Content-Type 必须带 `charset=utf-8`**：缺了它中文变乱码
3. **用户端开关**：未开启「允许主动发送」时 API 返回误导性的 `50015001 系统繁忙`
4. **不要用 bash 传中文参数**：Windows 终端编码会破坏 UTF-8 字节流，
   消息走「UTF-8 文件 → Python 直读直发」最稳
5. **monitor 输出必须稳定**：Hermes monitor 靠输出哈希变化唤醒 agent，
   带时间戳/随机数的输出会导致每个 tick 都唤醒
6. **频控**：未认证机器人 5/qps & 30/qpm（bot 维度），每用户每日 1000 条

## License

MIT
