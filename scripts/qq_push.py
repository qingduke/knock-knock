# -*- coding: utf-8 -*-
"""QQ 主动消息推送。

用法:
    python qq_push.py <消息文件路径>   # 文件为 UTF-8 文本

凭据来源（按优先级）:
    1. 环境变量 QQ_APP_ID / QQ_CLIENT_SECRET / QQ_USER_OPENID
    2. 同目录 .env 文件（QQ_APP_ID=..., QQ_CLIENT_SECRET=..., QQ_USER_OPENID=...）

注意:
    - 主动消息不要带 msg_id/event_id（那是被动回复专用，带了会 40034024）
    - Content-Type 必须带 charset=utf-8，否则中文乱码
    - 用户需在 QQ 客户端开启「允许主动发送」，否则返回 50015001
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def read_env(key: str) -> str:
    """环境变量优先，其次同目录 .env 文件。"""
    val = os.environ.get(key)
    if val:
        return val
    env_file = os.path.join(HERE, ".env")
    if os.path.exists(env_file):
        for line in open(env_file, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main() -> None:
    msg = open(sys.argv[1], encoding="utf-8").read().strip()
    app_id = read_env("QQ_APP_ID")
    secret = read_env("QQ_CLIENT_SECRET")
    openid = read_env("QQ_USER_OPENID")
    if not (app_id and secret and openid):
        print("CREDS_MISSING")
        sys.exit(1)

    token_req = urllib.request.Request(
        "https://bots.qq.com/app/getAppAccessToken",
        data=json.dumps({"appId": app_id, "clientSecret": secret}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    token = json.loads(urllib.request.urlopen(token_req, timeout=30).read().decode("utf-8")).get("access_token", "")
    if not token:
        print("TOKEN_FAILED")
        sys.exit(1)

    body = json.dumps({"content": msg, "msg_type": 0}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.sgroup.qq.com/v2/users/{openid}/messages",
        data=body,
        headers={
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    print(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))


if __name__ == "__main__":
    main()
