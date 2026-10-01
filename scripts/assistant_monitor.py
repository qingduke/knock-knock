# -*- coding: utf-8 -*-
"""玛修助手门控（cron monitor）——敲门 + 开机问候 二合一。

被 Hermes cron 以 monitor 模式调用。输出（稳定、无时间戳，靠输出哈希变化唤醒 agent）：
  BOOT  开机 30 分钟内且当天未问候 -> 开机问候（问候前重置屏幕基线）
  KNOCK 敲门计划到点且用户不在聊天 -> 敲门
  WAIT  其他情况

屏幕情况不在这里记录：由 agent 在 KNOCK 时按需查询（screen_query.py），
并与上一次敲门保存的基线（screen_state.json）对比。

设计要点:
    - BOOT 只在「当天还没问候过」时触发：一天开关机多次，只有每天第一次会问候，
      屏幕基线也只在这时重置（防止昨天的事延续到今天）
    - KNOCK 跳过也照计次数（不推迟、不补敲）
    - 聊天判定双重信号：active_agents > 0 或最近 10 分钟有消息
"""
import ctypes
import json
import os
import random
import sqlite3
import time

# ---- 按本机环境修改以下常量 ----
PROF = "/path/to/hermes/profile"             # Hermes profile 目录
KNOCK_STATE = PROF + "/knock_state.json"     # 敲门计划状态
BOOT_STATE = PROF + "/boot_greet_state.json"  # 开机问候状态（date=上次问候日期）
SCREEN_STATE = PROF + "/screen_state.json"   # 屏幕对比基线（KNOCK 时写入）
DB = PROF + "/state.db"                      # 会话数据库
GATEWAY_STATE = PROF + "/gateway_state.json"  # 网关状态（active_agents）
USER = "YOUR_USER_OPENID"                    # 用户 openid
CHAT_WINDOW = 600                            # 秒：最近 10 分钟有活动视为聊天中
BOOT_WINDOW = 1800                           # 秒：开机 30 分钟内

kernel32 = ctypes.windll.kernel32


def uptime_seconds():
    try:
        return kernel32.GetTickCount64() / 1000.0
    except Exception:
        return 1e9  # 拿不到就保持安静


def is_chatting(now_ts: float) -> bool:
    # 1) 有 agent 正在处理消息（包括长时间思考中）
    try:
        gs = json.load(open(GATEWAY_STATE, encoding="utf-8"))
        if gs.get("active_agents", 0) > 0:
            return True
    except Exception:
        pass
    # 2) 最近消息活动在窗口内
    try:
        db = sqlite3.connect(DB, timeout=3)
        row = db.execute(
            "SELECT MAX(last_activity_at) FROM sessions WHERE source='qqbot' AND user_id=?",
            (USER,),
        ).fetchone()
        db.close()
        if row and row[0] is not None and now_ts - row[0] < CHAT_WINDOW:
            return True
    except Exception:
        pass
    return False


def boot_check():
    if uptime_seconds() > BOOT_WINDOW:
        return None
    today = time.strftime("%Y-%m-%d")
    try:
        st = json.load(open(BOOT_STATE, encoding="utf-8"))
    except Exception:
        st = {}
    if st.get("date") == today:
        return None  # 今天已经问候过（一天多次开机只问候第一次）
    # 新的一天开始：重置屏幕对比基线，避免昨天的快照延续到今天
    try:
        os.remove(SCREEN_STATE)
    except Exception:
        pass
    return "BOOT"


def knock_check(now_ts: float):
    hour = time.strftime("%Y-%m-%dT%H")
    idx = int(time.strftime("%M")) // 10
    try:
        st = json.load(open(KNOCK_STATE, encoding="utf-8"))
    except Exception:
        st = {}
    if st.get("hour") != hour:
        n = random.randint(1, 3)
        st = {"hour": hour, "planned": sorted(random.sample(range(6), n)), "done": []}
    planned = st.get("planned", [])
    done = st.get("done", [])
    if idx in planned and idx not in done:
        done.append(idx)  # 跳过也照计次数
        st["done"] = done
        try:
            json.dump(st, open(KNOCK_STATE, "w", encoding="utf-8"))
        except Exception:
            pass
        if is_chatting(now_ts):
            return None  # 聊天中 -> 跳过但已计数
        return "KNOCK"
    return None


def main() -> None:
    sig = boot_check() or knock_check(time.time()) or "WAIT"
    print(sig)


if __name__ == "__main__":
    main()
