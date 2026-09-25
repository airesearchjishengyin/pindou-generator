# 账户系统 · 登录 / 余额 / 充值

> 2026-09-25 上线。 SQLite 单文件 (`accounts.db`, 已 gitignore), 无外部依赖。

## 用户侧

- 登录方式: Google / Microsoft (OAuth, 拿邮箱即可), 未配置的自动隐藏
- 新用户注册送 ¥0.9 (够生成 1 次)
- AI 像素化 ¥0.9/次, 从余额扣; 余额不足返回 402 提示充值
- 未登录用户仍可用兑换码 (老路径不变)
- 登录态: HMAC 签名 Cookie 30 天 (`pd_session`, httponly)

## 充值优惠规则 (自动)

每 20 元送 3 元 + 余数每 10 元送 1 元:
充10→11 / 充20→23 / 充30→34 / 充50→57 / 充100→115

## 你的操作 (收款入账)

用户转账后 (扫码付到你的微信/支付宝), 用管理接口入账:

```bash
curl -X POST https://pindou.macagents.org/api/admin/recharge \
  -H "x-admin-key: $PINDOU_ADMIN_KEY" \
  -F email=用户邮箱 -F amount_yuan=20 -F ref=微信转账单号
```

系统自动加赠并记账。查账: `sqlite3 accounts.db "SELECT * FROM ledger WHERE email='...'"`

## OAuth 凭据配置 (一次, 免费)

1. Google: console.cloud.google.com → 新建项目 → OAuth 同意屏幕 (External) →
   凭据 → OAuth 客户端 ID (Web) → 授权回调 URI 填
   `https://pindou.macagents.org/auth/google/callback`
   → 把 Client ID/Secret 填进 `.env`
2. Microsoft: portal.azure.com → Microsoft Entra ID → 应用注册 → 新建
   → 支持的账户类型选 "任何组织目录中的账户和个人 Microsoft 账户"
   → 重定向 URI 填 `https://pindou.macagents.org/auth/microsoft/callback`
   → 客户端密码 → 填 `.env` (MS_CLIENT_ID / MS_CLIENT_SECRET)
3. 重启服务: `launchctl kickstart -k gui/$UID/org.pindou.server`

⚠️ 国内用户 Google 登录可能打不开 (被墙), 微软登录国内可用; 两者的兜底是兑换码模式。
