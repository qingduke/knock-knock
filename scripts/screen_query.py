# -*- coding: utf-8 -*-
"""查询当前屏幕情况（敲门时按需调用），输出 JSON 到 stdout。

字段：t 时间、foreground 前台窗口标题（可能为空）、idle_s 键鼠空闲秒数。

agent 将本次结果与 screen_state.json 中上次敲门的基线对比：
  窗口不变 + idle 继续增长 -> 用户可能不在电脑前
  窗口切换或 idle 明显回落 -> 用户可能刚回到电脑前
"""
import ctypes
import json
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def idle_seconds():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if user32.GetLastInputInfo(ctypes.byref(lii)):
        return round((kernel32.GetTickCount() - lii.dwTime) / 1000.0, 1)
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


print(
    json.dumps(
        {
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "foreground": foreground_title(),
            "idle_s": idle_seconds(),
        },
        ensure_ascii=False,
    )
)
