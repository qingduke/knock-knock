# -*- coding: utf-8 -*-
"""一次性任务监控示例：Steam 游戏下载完成检测。

被 Hermes cron 以 monitor 模式调用：输出 StateFlags 值，
安装完成（StateFlags=4）时输出变化，唤醒 agent 发提醒。
"""
import os
import re

# Steam 安装目录下的 appmanifest 文件，appid 为游戏 ID
ACF = "/path/to/steam/steamapps/appmanifest_1086940.acf"


def main() -> None:
    if os.path.exists(ACF):
        txt = open(ACF, encoding="utf-8", errors="ignore").read()
        m = re.search(r'"StateFlags"\s+"(\d+)"', txt)
        print("STATEFLAGS=" + (m.group(1) if m else "?"))
    else:
        print("STATEFLAGS=missing")


if __name__ == "__main__":
    main()
