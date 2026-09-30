# -*- coding: utf-8 -*-
"""敲门门控脚本（cron monitor）。

被 Hermes cron 以 monitor 模式调用：输出 KNOCK 唤醒 agent 敲门，
输出 WAIT 保持静默。输出必须稳定（monitor 靠输出哈希变化检测唤醒）。

设计:
    - 每小时随机计划 1~3 个敲门时刻（10 分钟粒度，保证至少一次）
    - 到点但用户正在聊天时跳过，且照样消耗计划次数（不推迟、不补敲）
    - 状态存 STATE 文件，跨 gateway 重启不丢
"""
import json
import os
import random
import sqlite3
import time

# ---- 按本机环境修改以下三个路径/常量 ----
STATE = "/path/to/knock_state.json"          # 敲门计划状态文件
DB = "/path/to/hermes/state.db"              # Hermes 会话数据库（判断聊天活跃）
USER_OPENID = "YOUR_USER_OPENID"             # 被敲门用户的 openid
CHAT_WINDOW = 180                            # 秒：最近 3 分钟有消息视为聊天中


def is_chatting(now_ts: float) -> bool:
    try:
        db = sqlite3.connect("file:" + DB.replace("\\", "/") + "?mode=ro", uri=True, timeout=3)
        row = db.execute(
            "SELECT MAX(last_activity_at) FROM sessions WHERE source='qqbot' AND user_id=?",
            (USER_OPENID,),
        ).fetchone()
        db.close()
        if row and row[0] is not None and now_ts - row[0] < CHAT_WINDOW:
            return True
    except Exception:
        pass
    return False


def main() -> None:
    now = time.localtime()
    hour_key = "%04d-%02d-%02dT%02d" % (now.tm_year, now.tm_mon, now.tm_mday, now.tm_hour)
    idx = now.tm_min // 10  # 0..5

    st = {"hour": "", "planned": [], "done": []}
    if os.path.exists(STATE):
        try:
            st = json.load(open(STATE, encoding="utf-8"))
        except Exception:
            st = {"hour": "", "planned": [], "done": []}

    if st.get("hour") != hour_key:
        n = random.randint(1, 3)
        st = {"hour": hour_key, "planned": sorted(random.sample(range(6), n)), "done": []}

    if idx in st["planned"] and idx not in st["done"]:
        st["done"].append(idx)  # 无论是否跳过都消耗计划位
        json.dump(st, open(STATE, "w", encoding="utf-8"))
        print("WAIT" if is_chatting(time.time()) else "KNOCK")
    else:
        json.dump(st, open(STATE, "w", encoding="utf-8"))
        print("WAIT")


if __name__ == "__main__":
    main()
