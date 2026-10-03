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

# 零配置：profile 根目录 = 本脚本所在 scripts/ 的上一级；
# 用户 openid 从 profile 根目录 .env 读取（QQ_USER_OPENID=...）
PROF = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOCK_STATE = os.path.join(PROF, "knock_state.json")
BOOT_STATE = os.path.join(PROF, "boot_greet_state.json")
SCREEN_STATE = os.path.join(PROF, "screen_state.json")
IDLE_STATE = os.path.join(PROF, "idle_state.json")
EVENTS = os.path.join(PROF, "events.json")
DB = os.path.join(PROF, "state.db")
GATEWAY_STATE = os.path.join(PROF, "gateway_state.json")
CHAT_WINDOW = 600   # 秒：最近 10 分钟有活动视为聊天中
BOOT_WINDOW = 1800  # 秒：开机 30 分钟内
LEAVE_IDLE_S = 600  # 秒：键鼠无操作 10 分钟 -> 进入「无操作」状态
RETURN_IDLE_S = 60  # 秒：idle 回落到 1 分钟内 -> 恢复操作

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32


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


def idle_seconds():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if user32.GetLastInputInfo(ctypes.byref(lii)):
        return (kernel32.GetTickCount() - lii.dwTime) / 1000.0
    return -1.0


def foreground_title():
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


def _append_event(kind, idle, fg):
    try:
        ev = json.load(open(EVENTS, encoding="utf-8"))
    except Exception:
        ev = []
    ev.append(
        {
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "kind": kind,
            "idle_s": round(idle, 1),
            "foreground": fg,
        }
    )
    try:
        json.dump(ev[-10:], open(EVENTS, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def idle_event_check():
    """屏幕观察事件检测（纯规则，零 AI）。

    键鼠无操作超阈值 -> 持续输出 LEAVE（可能离开，也可能在用手机）；
    idle 回落 -> 输出一次 RETURN。事件写入 events.json 供 agent 语义化。
    输出稳定：离开期间一直 LEAVE，不会重复唤醒 agent。
    """
    try:
        st = json.load(open(IDLE_STATE, encoding="utf-8"))
    except Exception:
        st = {"state": "in"}
    idle = idle_seconds()
    if idle < 0:
        return None  # 拿不到数据就保持安静
    state = st.get("state", "in")
    if state == "in" and idle > LEAVE_IDLE_S:
        st = {"state": "out", "since": time.strftime("%Y-%m-%dT%H:%M:%S")}
        try:
            json.dump(st, open(IDLE_STATE, "w", encoding="utf-8"))
        except Exception:
            pass
        _append_event("leave", idle, foreground_title())
        return "LEAVE"
    if state == "out" and idle < RETURN_IDLE_S:
        st = {"state": "in"}
        try:
            json.dump(st, open(IDLE_STATE, "w", encoding="utf-8"))
        except Exception:
            pass
        _append_event("return", idle, foreground_title())
        return "RETURN"
    if state == "out":
        return None  # 持续无操作：转换时已发过 LEAVE 信号，此后让位，不再阻塞 KNOCK
    return None


def _gateway_uptime():
    """gateway 主进程已运行秒数 ≈ 本次开机的时长。

    不能用系统 GetTickCount 判断开机：Windows「快速启动」的混合关机/恢复
    不会重置内核计时，用户每天关机开机却显示几十天 uptime。
    gateway 由开机自启的计划任务拉起，每次开机都是新进程；gateway_state.json
    里记录了 gateway 的 pid，用该进程的创建时间作为「本次开机」的时间点。
    """
    try:
        gs = json.load(open(GATEWAY_STATE, encoding="utf-8"))
        pid = gs.get("pid")
        if not pid:
            return 1e9
        import psutil

        try:
            return max(0.0, time.time() - psutil.Process(pid).create_time())
        except Exception:
            return 1e9
    except Exception:
        pass
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
            (_user(),),
        ).fetchone()
        db.close()
        if row and row[0] is not None and now_ts - row[0] < CHAT_WINDOW:
            return True
    except Exception:
        pass
    return False


def boot_check():
    if _gateway_uptime() > BOOT_WINDOW:
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
    lt = time.localtime()
    hour = time.strftime("%Y-%m-%dT%H")
    minute = lt.tm_min
    try:
        st = json.load(open(KNOCK_STATE, encoding="utf-8"))
    except Exception:
        st = {}
    if st.get("hour") != hour:
        # 新的一小时：抽两次签——先抽次数（1~3），再抽具体分钟。
        # 约束：同小时内两两间隔 >=10 分钟；且与上一小时最后一次计划
        # 至少间隔 10 分钟（跨小时边界也生效）。
        n = random.randint(1, 3)
        lo = 2
        prev_last = st.get("last_planned")
        if prev_last is not None:
            lo = max(2, (prev_last + 10) % 60)
        pool = list(range(lo, 60))
        chosen = []
        for _ in range(n):
            if not pool:
                break
            x = random.choice(pool)
            chosen.append(x)
            pool = [m for m in pool if abs(m - x) >= 10]
        planned = sorted(chosen)
        st = {
            "hour": hour,
            "planned": planned,
            "done": [],
            "last_planned": planned[-1] if planned else prev_last,
        }
        try:
            json.dump(st, open(KNOCK_STATE, "w", encoding="utf-8"))
        except Exception:
            pass
    planned = st.get("planned", [])
    done = st.get("done", [])
    if minute in planned and minute not in done:
        done.append(minute)  # 到点即消耗（聊天中跳过也不补敲）
        st["done"] = done
        try:
            json.dump(st, open(KNOCK_STATE, "w", encoding="utf-8"))
        except Exception:
            pass
        if is_chatting(now_ts):
            return None  # 聊天中 -> 跳过
        return "KNOCK"
    return None


def main() -> None:
    sig = boot_check() or idle_event_check() or knock_check(time.time()) or "WAIT"
    print(sig)


if __name__ == "__main__":
    main()
