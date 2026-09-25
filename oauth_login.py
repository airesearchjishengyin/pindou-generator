"""图豆 OAuth 登录 (Google / Microsoft) — 标准 OIDC 授权码流程, 零重依赖。
凭据全部走 .env:
  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
  MS_CLIENT_ID / MS_CLIENT_SECRET
未配置的提供商在前端自动隐藏。回调地址:
  {base}/auth/google/callback   {base}/auth/microsoft/callback
base 从请求推断 (支持 CF Tunnel 公网域名)。
"""
import os
import base64
import hashlib
import secrets
import urllib.parse
import urllib.request
import json as _json

# ---------- 提供商配置 ----------
PROVIDERS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile",
    },
    "microsoft": {
        # tenants=common: 个人账号 + 组织账号都能登录
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2/token",
        "scope": "openid email profile",
    },
}


def configured() -> list:
    out = []
    if os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
        out.append("google")
    if os.environ.get("MS_CLIENT_ID") and os.environ.get("MS_CLIENT_SECRET"):
        out.append("microsoft")
    return out


def _client_creds(provider: str):
    if provider == "google":
        return os.environ["GOOGLE_CLIENT_ID"], os.environ["GOOGLE_CLIENT_SECRET"]
    return os.environ["MS_CLIENT_ID"], os.environ["MS_CLIENT_SECRET"]


def make_state() -> str:
    return secrets.token_urlsafe(24)


def auth_redirect(provider: str, base_url: str, state: str) -> str:
    cid, _ = _client_creds(provider)
    p = PROVIDERS[provider]
    q = urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": f"{base_url}/auth/{provider}/callback",
        "response_type": "code",
        "scope": p["scope"],
        "state": state,
        "prompt": "select_account",          # 多账号用户每次可选号
    })
    return f"{p['auth_url']}?{q}"


def exchange_code(provider: str, base_url: str, code: str) -> dict:
    """用授权码换 id_token 并解出 email/name。失败抛 RuntimeError。"""
    cid, secret = _client_creds(provider)
    p = PROVIDERS[provider]
    body = urllib.parse.urlencode({
        "client_id": cid,
        "client_secret": secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": f"{base_url}/auth/{provider}/callback",
    }).encode()
    req = urllib.request.Request(p["token_url"], data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            tok = _json.load(resp)
    except Exception as e:
        raise RuntimeError(f"token 交换失败: {e}")
    id_token = tok.get("id_token", "")
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload))
    except Exception as e:
        raise RuntimeError(f"id_token 解析失败: {e}")
    email = claims.get("email")
    if not email:
        raise RuntimeError("该账号未返回邮箱, 无法登录")
    return {"email": email, "name": claims.get("name", ""),
            "provider_uid": claims.get("sub", "")}
