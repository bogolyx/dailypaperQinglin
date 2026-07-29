# 青梨AI 科研服务平台 — API 逆向文档

## 概述

青梨AI (`https://qingli.newacademic.net/`) 是高校/科研机构常用的文献获取平台。
通过微信扫码登录后，可提交 DOI 获取论文 PDF。

## 认证机制

- **登录方式**: 网页版微信扫码（`POST /api/user/mini_qrcode/` 获取二维码）
- **Token 存储**: JWT 格式，存放在 localStorage (`token` 和 `new_token`)
- **Token 有效期**: 30 天（通过 `exp` 字段确认）
- **用户标识**: localStorage `email` 字段（实际是用户唯一 ID，非邮箱）

## API 端点

### 1. 提交文献需求

```
POST https://xcx.newacademic.net/api/user/consultation/
Headers:
  token: <JWT>
  newtoken: <JWT>
  Content-Type: application/json
Body:
{
  "type": 2,
  "text": "10.1016/j.artmed.2025.103345",   // DOI
  "organ_code": "OJSYSOJS001",              // 机构代码
  "force_type": 2,
  "is_artificial": 0,
  "force_submint": false
}
Response: {"error_code": 0, "msg": "提交成功"}
```

### 2. 查询资源需求列表

```
POST https://xcx.newacademic.net/api/literature/new_get_user_demand/?uc=<user_code>
Headers:
  token: <JWT>
  newtoken: <JWT>
  Content-Type: application/json
Body:
{
  "page": 1,
  "size": 20,
  "sort_by": "time_desc",
  "con_type": ["all"],
  "status": ["all"],
  "start_date": "2026-07-29",
  "end_date": "2026-07-29",
  "content": "",
  "read": 0,
  "source": 0
}
Response: 包含 data.data 数组，每条记录含:
  - content: 提交的 DOI
  - status: 处理状态
  - down_url: [PDF CDN 直链数组]
  - result_info: { title, doi, ... }
```

### 3. PDF 下载

`down_url` 是 CDN 直链（如 `https://*.myqcloud.com/*.pdf`），
直接 GET 即可下载，无需额外认证。

## 工作流程

```
扫码登录 → 获取 JWT token
    ↓
POST /consultation/ → 提交 DOI
    ↓
轮询 POST /new_get_user_demand/（每 5 秒，最长 60 秒）
    ↓
获取 down_url[0] → CDN 下载 PDF
```

## Token 过期处理

- `load_auth()` 自动检查 `exp` 字段
- 剩余 < 3 天时打印警告
- 过期后需重新运行 `qingli_login.js` 扫码

## 已知限制

- 每个 DOI 只能提交一次（重复提交会被系统合并）
- 处理时间通常 10-30 秒
- 部分论文青梨找不到（无馆藏），此时 `down_url` 为空
