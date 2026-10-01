# knock-knock 玛修助手

基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent) cron 机制构建的
QQ 主动问候小机器人：**开机问候 + 随机敲门 + 屏幕状态推测**三件事，
一个统一的任务完成。

## 功能

- **开机问候**：电脑开机 30 分钟内（且当天未问候过），主动发一条 QQ 消息，
  附今日天气与近期日程提醒
- **随机敲门**：每小时随机敲 1~3 次门，结合"屏幕观察"与"活动状态簿"推测
  用户当前状态，说合适的话
- **屏幕状态推测**：敲门时查询前台窗口 + 键鼠空闲时长，与上一次敲门的基线
  对比：窗口不变且空闲持续增长 → 人不在电脑前（留言式问候）；
  窗口切换或空闲回落 → 刚回到电脑前（欢迎回来式问候）

## 架构

```
cron「玛修助手」(every 10m)
  └─ monitor: assistant_monitor.py      # 门控，输出 BOOT / KNOCK / WAIT
       ├─ BOOT：开机 30 分钟内 + 当天未问候
       │        → 问候前先重置屏幕基线（新的一天，昨天的观察作废）
       ├─ KNOCK：小时随机计划到点 + 用户不在聊天
       │        （聊天判定：active_agents > 0 或最近 10 分钟有消息）
       └─ 状态：knock_state.json / boot_greet_state.json / screen_state.json
  └─ agent 被唤醒后：
       ├─ BOOT → 查天气 + 日程簿 → qq_push.py 发开机问候 → 记录问候日期
       └─ KNOCK → screen_query.py 查屏幕 → 与基线对比 → 推测状态
                → qq_push.py 发敲门 → 写入新基线
```

## 组件

| 文件 | 作用 |
|------|------|
| `scripts/qq_push.py` | QQ 主动消息推送（UTF-8 文件 → Python 直发） |
| `scripts/assistant_monitor.py` | 二合一门控（开机问候 + 敲门 + 基线重置） |
| `scripts/knock_monitor.py` | 敲门门控单功能版（早期版本，聊天避让修复版） |
| `scripts/screen_query.py` | 屏幕查询（前台窗口 + 键鼠空闲秒数，JSON 输出） |
| `scripts/bg3_download_monitor.py` | 一次性任务监控示例（Steam 下载完成检测） |

## 部署

1. 安装 Hermes Agent，注册 QQ 机器人（q.qq.com），获得 AppID / AppSecret
2. 填写 `.env`（参考 `.env.example`）：
   `QQ_APP_ID` / `QQ_CLIENT_SECRET` / `QQ_USER_OPENID`
3. **用户在 QQ 客户端对机器人开启「允许主动发送」**（必需，否则推送被拒）
4. 把脚本放进 Hermes profile 的 `scripts/` 目录——路径自动推导，**零代码配置**；
   在 profile 的 `.env` 中配置 `QQ_USER_OPENID=你的用户openid`
5. 创建 cron 任务（agent 模式，monitor 指向 assistant_monitor.py，
   schedule `every 10m`），prompt 里写明 BOOT / KNOCK / WAIT 三种分支的行为
6. 准备 `schedule.json`（日程簿）与 `activity_state.json`（活动状态簿），
   供 agent 读取

## 踩坑记录

1. **主动消息不要带 `msg_id`**：`msg_id`/`event_id` 是被动回复专用字段，
   主动消息带上会返回 `40034024 请求参数msg_id无效或越权`
2. **Content-Type 必须带 `charset=utf-8`**：缺了它中文变乱码
3. **用户端开关**：未开启「允许主动发送」时 API 返回误导性的 `50015001 系统繁忙`
4. **不要用 bash 传中文参数**：Windows 终端编码会破坏 UTF-8 字节流，
   消息走「UTF-8 文件 → Python 直读直发」最稳
5. **monitor 输出必须稳定**：Hermes monitor 靠输出哈希变化唤醒 agent，
   带时间戳/随机数的输出会导致每个 tick 都唤醒
6. **聊天避让要防"长时间思考"**：只按消息时间戳判定会在 agent 思考
   （超过窗口）时误判为"对话结束"。修复：双重信号——`active_agents > 0`
   视为聊天中 + 活动窗口放宽到 10 分钟
7. **屏幕基线要日清**：开机问候（每天第一次）时重置屏幕对比基线，
   否则昨天的快照会延续到今天；且重置绑定"当天未问候"而非"每次开机"，
   一天开关机多次不会反复重置
8. **前台账面获取在后台进程可能为空**：monitor/agent 运行在后台进程时
   `GetForegroundWindow` 可能拿不到标题，此时以键鼠空闲时长为准
9. **频控**：未认证机器人 5/qps & 30/qpm（bot 维度），每用户每日 1000 条
10. **「快速启动」让开机检测失灵**：Windows 快速启动的关机是混合关机，
    GetTickCount / LastBootUpTime 不会随每天的开机重置（用户天天关机，
    uptime 却显示几十天）。判断「刚开机」要用 gateway 进程的创建时间——
    gateway 每次开机都由计划任务重新拉起，进程创建时间≈本次开机时间

## License

MIT
