"""
用户认证模块（纯标准库实现，无第三方依赖）。

设计要点：
- 密码使用 pbkdf2_hmac（sha256 + 随机 salt）哈希存储
- 登录会话使用 HMAC-SHA256 签名的 token，存放在 HttpOnly Cookie 中
  （这样前端的 /final 下载与 /ws WebSocket 也能自动携带，无需额外的 Authorization 头）
- 用户数据持久化到 data/users.json（与项目数据同目录，保持「无数据库」设计）

权限：
- 普通用户 user：可以使用制作功能
- 管理员 admin：额外可添加 / 删除用户
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Optional

from . import config

logger = logging.getLogger("drama-studio.auth")

SESSION_COOKIE = "ds_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 天

# 会话签名密钥：优先取环境变量 SESSION_SECRET，否则用内置默认值（仅用于本地/演示）。
# 若需生产部署，请通过环境变量 SESSION_SECRET 设置一个随机长字符串。
SESSION_SECRET = os.environ.get("SESSION_SECRET") or "drama-studio-dev-secret-change-me"

USERS_FILE = config.DATA_DIR / "users.json"

DEFAULT_ADMIN = {
    "username": "admin",
    "password": "admin123",
    "role": "admin",
}


# ============ 密码哈希 ============
def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return salt.hex() + ":" + dk.hex()


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ============ 用户持久化 ============
def _load_users() -> list:
    if not USERS_FILE.exists():
        return []
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_users(users: list) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def _seed_admin() -> None:
    """首次运行时写入默认管理员账户（仅当不存在任何管理员时）。"""
    users = _load_users()
    if not any(u.get("role") == "admin" for u in users):
        users.append({
            "username": DEFAULT_ADMIN["username"],
            "password_hash": _hash_password(DEFAULT_ADMIN["password"]),
            "role": "admin",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        _save_users(users)


def ensure_admin_account() -> None:
    """
    启动时保证存在管理员账户，并支持通过环境变量 ADMIN_PASSWORD 重置密码。

    用法：启动时设置 ADMIN_PASSWORD=新密码 然后重启服务，
    即可把 admin 的密码强制改为「新密码」（解决忘记密码被锁死的问题）。
    """
    override = os.environ.get("ADMIN_PASSWORD")
    users = _load_users()
    admin = next((u for u in users if u.get("username") == DEFAULT_ADMIN["username"]), None)
    if admin:
        if override:
            admin["password_hash"] = _hash_password(override)
            _save_users(users)
            logger.info("admin 密码已由环境变量 ADMIN_PASSWORD 重置")
        return
    # 不存在管理员：创建（优先用 override，否则用默认 admin123）
    pw = override or DEFAULT_ADMIN["password"]
    users.append({
        "username": DEFAULT_ADMIN["username"],
        "password_hash": _hash_password(pw),
        "role": "admin",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    _save_users(users)


def set_password(username: str, password: str) -> None:
    """直接重置某用户的密码（不校验旧密码，供运维/命令行重置使用）。"""
    users = _load_users()
    for u in users:
        if u.get("username") == username:
            u["password_hash"] = _hash_password(password)
            _save_users(users)
            return
    raise ValueError("用户不存在")


# 模块导入时即保证存在默认管理员（并应用 ADMIN_PASSWORD 覆盖）
ensure_admin_account()


def authenticate(username: str, password: str) -> Optional[dict]:
    users = _load_users()
    for u in users:
        if u.get("username") == username:
            if _verify_password(password, u.get("password_hash", "")):
                return {"username": u["username"], "role": u["role"]}
            return None
    return None


def create_user(username: str, password: str, role: str = "user") -> dict:
    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    if role not in ("admin", "user"):
        raise ValueError("role 必须为 admin 或 user")
    users = _load_users()
    if any(u.get("username") == username for u in users):
        raise ValueError("用户名已存在")
    users.append({
        "username": username,
        "password_hash": _hash_password(password),
        "role": role,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    _save_users(users)
    return {"username": username, "role": role}


def delete_user(username: str) -> None:
    users = _load_users()
    target = next((u for u in users if u.get("username") == username), None)
    if not target:
        raise ValueError("用户不存在")
    if target.get("role") == "admin":
        admins = [u for u in users if u.get("role") == "admin"]
        if len(admins) <= 1:
            raise ValueError("不能删除最后一个管理员账户")
    users = [u for u in users if u.get("username") != username]
    _save_users(users)


def list_users() -> list:
    users = _load_users()
    return [{"username": u["username"], "role": u["role"], "created_at": u.get("created_at")}
            for u in users]


def get_user(username: str) -> Optional[dict]:
    users = _load_users()
    for u in users:
        if u.get("username") == username:
            return {"username": u["username"], "role": u["role"]}
    return None


# ============ 会话 token（HMAC 签名） ============
def _b64(s: str) -> str:
    import base64
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _unb64(s: str) -> str:
    import base64
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad).decode("utf-8")


def _sign(b64payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode("utf-8"),
                    b64payload.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def create_session_token(username: str) -> str:
    payload = _b64(f"{username}.{int(time.time())}")
    return f"{payload}.{_sign(payload)}"


def verify_session_token(token: Optional[str]) -> Optional[str]:
    if not token or "." not in token:
        return None
    b64payload, _, sig = token.partition(".")
    if not sig or not hmac.compare_digest(_sign(b64payload), sig):
        return None
    try:
        username, _ts = _unb64(b64payload).split(".", 1)
        return username
    except Exception:
        return None
