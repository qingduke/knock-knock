# -*- coding: utf-8 -*-
"""敲门门控脚本（cron monitor）——聊天避让修复版。

被 Hermes cron 以 monitor 模式调用：输出 KNOCK 唤醒 agent 敲门，
输出 WAIT 保持静默。输出必须稳定（monitor 靠输出哈希变化检测唤醒）。

设计:
    - 每小时随机计划 1~3 个敲门时刻（10 分钟粒度，保证至少一次）
    - 到点但用户正在聊天时跳过，且照样消耗计划次数（不推迟、不补敲）
    - 状态存 STATE 文件，跨 gateway 重启不丢

聊天判定（双重信号，修复"agent 长时间思考被误判为对话结束"问题）:
    1. gateway_state.json 的 active_agents > 0 —— 有 agent 正在处理消息
    2. 会话库最近 10 分钟内有消息活动
"""
import json
import os
import random
import sqlite3
import time

# 零配置：profile 根目录 = 本脚本所在 scripts/ 的上一级；
# 用户 openid 从 profile 根目录 .env 读取（QQ_USER_OPENID=...）
PROF = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(PROF, "knock_state.json")
DB = os.path.join(PROF, "state.db")
GATEWAY_STATE = os.path.join(PROF, "gateway_state.json")
CHAT_WINDOW = 600  # 秒：最近 10 分钟有活动视为聊天中


def _load_env():
    """从 profile 根目录 .env 读取键值（不覆盖已存在的环境变量）。"""
    env_path = os.path.join(PROF, ".env")
    if not os.path.exists(env_path):
        return
    try:
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


def _user():
    _load_env()
    return os.environ.get("QQ_USER_OPENID", "")


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
            (_user(),),
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
