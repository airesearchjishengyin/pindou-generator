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

## 微信收款自动到账（调研结论 2026-09）

**结论: 个人收款码没有官方自动到账 API, 别碰第三方"免签支付"。**

| 方案 | 原理 | 风险 |
|---|---|---|
| 微信官方商户 API | 有自动回调 | 需营业执照 (即个体户, 回到正轨) |
| 免签支付 (V免签/码支付/XPay等) | 监听手机通知栏/无障碍服务抓到账推送 | 第三方平台经手订单信息, 有"二清"合规风险; 微信 2022 年 3 月起明令个人收款码不得用于经营, 风控会封码 |
| 云监控变体 | 同上, 交给云端监听 | 同上 + 订单数据过第三方服务器 |

微信 2021 年央行 259 号文后, **个人静态收款码被明确禁止用于经营性收款**,
免签方案等于踩线跑, 小量可侥幸, 量起来必被风控 (封码/限制收款)。

**现实路径**: 兑换码人工发码 (现状) → 个体户执照下来 → 立刻申请微信商户号 →
Native 扫码支付自动回调, 那时才真正做到"不用手动更新余额"。
在个体户办下来之前, 手动入账就一条 curl 命令 (见上节), 日单量 < 20 完全可接受。
