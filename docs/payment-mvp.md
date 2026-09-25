# 收费 MVP · 兑换码模式 — 运营与规则

> 更新: 2026-09-25。当前形态: 个人收款码收款 + 兑换码解锁 AI 像素化。
> 个体户办下来后的升级路径见文末。

## 为什么是兑换码而不是支付 API

个人主体**无法**申请微信支付/支付宝商户号（需营业执照+备案域名），
所以 MVP 用人工发码：用户扫码付款（个人收款码）→ 你把码发给用户 →
用户在网页输入码 → 服务端校验并扣次。

## 规则（服务器强制执行）

- AI 像素化是唯一付费功能，免费转换不受影响
- 每张 AI 图纸消耗兑换码 1 次；`licenses.json` 记录 max_uses/uses/时间
- 服务端在 `/api/generate` 里强制校验 `license_code`，前端 localStorage 只做 UX
- 生成失败（API 超时/出错）不自动退码——当前版本的取舍，量大后再自动化退款

## 你的日常操作

### 发码

```bash
# 生成 1 个可用 1 次的码
curl -X POST http://127.0.0.1:8600/api/license/gen \
  -F admin_key=$PINDOU_ADMIN_KEY -F count=1 -F max_uses=1 -F note="微信昵称xxx"
# 返回 {"codes":["PD-XXXXXXXX"]} → 把码发给付款用户
```

也可一次生成一批（`-F count=20`），收到一笔款发一个码。

### 查询剩余

```bash
curl "http://127.0.0.1:8600/api/license/status?code=PD-XXXXXXXX"
```

### 收款码

收款码图片放到 `static/pay-qr.png`（微信或支付宝个人收款码，金额写在面板上）。
定价建议：AI 接口成本约 0.2–0.4 元/张（gpt-image-2 low 档），定价 ¥3–5/次有利润。

## .env 需要新增

```
PINDOU_ADMIN_KEY=<随机字符串，用于发码接口鉴权>
```

## 个体户办下来后的升级路径

1. 个体户执照 → 域名备案
2. 微信小程序（工具类目）+ 微信支付商户号
3. 小程序内直接 wx.requestPayment，兑换码逻辑退役或转为"次卡"
4. 图生图切到已备案的国产模型 API（通义万相/混元等），满足 AIGC 上架审核
