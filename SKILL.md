---
name: qingli-pdf-downloader
description: 青梨AI科研服务平台 PDF 自动下载器。通过 DOI 自动提交、轮询、下载论文 PDF。支持：扫码登录（微信）、JWT token 管理、API 逆向调用、CDN 直链下载。触发词：青梨、qingli、青梨下载、qingli.ai、通过DOI下载论文、青梨AI下载。每个用户需要自己的青梨账号和 qingli_auth.json。
agent_created: true
---

# 青梨AI PDF 自动下载器

通过青梨AI科研服务平台 (`https://qingli.newacademic.net/`) 的逆向 API，根据 DOI 自动获取论文 PDF。

## 适用场景

- 用户需要从青梨平台根据 DOI 下载论文 PDF
- 用户需要批量下载论文（循环调用）
- 登录态过期需要重新扫码
- 首次使用需要设置青梨账号绑定

## 前置依赖

### Node.js 环境
```bash
npm install playwright
npx playwright install chromium
```

### Python 环境
```bash
pip install requests
```

## 使用流程

### 首次使用：扫码登录

每个用户（bogo、爱人、学生）需要用自己的青梨账号扫码一次：

1. 检查当前目录是否已有 `qingli_auth.json`。如果有，先检查 token 过期时间。
2. 运行 `scripts/qingli_login.js`：
   ```bash
   node scripts/qingli_login.js
   ```
3. 浏览器窗口弹出后，用微信扫码登录青梨AI。
4. 脚本自动检测登录成功，保存 `qingli_auth.json` 到当前目录。
5. 登录态（JWT token）有效期 30 天。

### 下载 PDF

```bash
python scripts/qingli_downloader.py <DOI>
```

示例：
```bash
python scripts/qingli_downloader.py 10.1016/j.artmed.2025.103345
```

脚本执行流程：
1. 读取 `qingli_auth.json` 中的 JWT token，检查过期时间
2. 提交 DOI 到青梨系统
3. 每 5 秒轮询处理状态（最长 60 秒）
4. 获取 PDF CDN 直链并下载
5. 保存到 `qingli_pdfs/` 目录

### Token 过期处理

- `qingli_downloader.py` 会自动检查 token 剩余天数
- 剩余 < 3 天时打印红色警告
- 过期后需重新运行 `qingli_login.js` 扫码

### 批量下载（推荐）

使用 `scripts/batch_download.py` 批量下载，支持断点续传和失败重试：

```bash
python scripts/batch_download.py <paper_list.json> [--output-dir <dir>]
```

**核心特性：**
- ✅ 断点续传：自动跳过已下载的 PDF（检查文件大小 > 1KB）
- ✅ 失败记录：写入 `<output_dir>/download_failures.json`，增量保存不丢数据
- ✅ 重试友好：失败后再次运行相同命令，只下缺失的
- ✅ 进度显示：实时 ETA 预估

**JSON 输入格式（二选一）：**
```json
// 格式1：简单列表
[{"doi": "10.xxx/yyy", "title": "...", "journal": "..."}]

// 格式2：带分类（自动合并 tier1 + tier2）
{"tier1_papers": [...], "tier2_papers": [...]}
```

**可选参数：**
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--output-dir` / `-o` | `qingli_pdfs` | PDF 输出目录 |
| `--auth-file` | `qingli_auth.json` | 认证文件路径 |
| `--interval` | `2` | 篇间间隔秒数 |
| `--max-wait` | `150` | 单篇轮询最长秒数 |

**重试失败项：**
失败记录保存在 `<output_dir>/download_failures.json`，再次运行相同命令即可自动重试。

### arXiv 预印本下载

arXiv 论文无 DOI（青梨不支持），用 `scripts/download_arxiv.py` 直接下载：

```bash
python scripts/download_arxiv.py <arxiv_id> [<arxiv_id> ...] --output-dir <dir>
```

示例：
```bash
python scripts/download_arxiv.py 2607.25324 2605.14108 -o qingli_pdfs/
```

## 技术原理

详见 `references/qingli_api.md`，核心 API 链路：

1. `POST /api/user/consultation/` — 提交 DOI
2. `POST /api/literature/new_get_user_demand/` — 轮询获取 PDF CDN 直链（`down_url` 字段）
3. `GET {down_url}` — 直接下载 PDF

## 多用户共享

此 skill 设计为多用户共享：
- `qingli_auth.json` 是每个用户的独立文件，不随 skill 分发
- 每个用户需要运行自己的 `qingli_login.js` 生成自己的 `qingli_auth.json`
- 不同用户的 token 互不干扰
- 脚本文件（`qingli_login.js`、`qingli_downloader.py`）通用，无需修改

## 注意事项

- 青梨对同一 DOI 的重复提交会自动合并，不会重复处理
- PDF 处理时间通常 10-30 秒
- 部分论文青梨无馆藏，`down_url` 为空
- `qingli_auth.json` 包含 JWT token，不要分享给他人

## 常见问题（排错）

### 1. `FileNotFoundError: qingli_auth.json`
`batch_download.py` 的 `--auth-file` 默认值是**相对当前工作目录**的 `qingli_auth.json`，不是脚本目录。
→ 必须显式传绝对路径：
```bash
python scripts/batch_download.py papers.json -o out/ --auth-file "C:/Users/bogolyx/.dsh/skills/qingli-pdf-downloader/scripts/qingli_auth.json"
```

### 2. `{"error_code": 400, "msg": "该账号已在其他设备登录"}`
同一个账号在别处（微信小程序 / 另一台机器）登录，会顶掉网页版 JWT。
→ 重新运行 `node qingli_login.js` 即可恢复；浏览器 profile 里通常还留着微信会话，无需再次扫码，启动后会自动跳转主页并把新 token 写回 `scripts/qingli_auth.json`。
→ 恢复后可把新 auth 文件同步到自己的备份位置（例如 `E:/ghb/keyan/paper/2026 papers/qingli_auth.json`）。

### 3. `ModuleNotFoundError: No module named 'requests'`
WorkBuddy 的托管 python（`versions/3.13.12`）可能没有 `requests`。
→ 用带 requests 的 venv 解释器运行脚本：
```
C:/Users/bogolyx/.dsh/toolchain/binaries/python/envs/default/Scripts/python.exe scripts/batch_download.py ...
```

### 4. token 有效期
登录态约 30 天。提交前先用一次单篇 `POST /api/user/consultation/` 探活，比直接跑批量更省时间。
