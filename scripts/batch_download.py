#!/usr/bin/env python3
"""
批量下载论文 PDF（断点续传 + 失败重试）
适用场景：已有论文 JSON 列表（含 DOI），批量调用青梨 AI 下载。

用法：
  python scripts/batch_download.py <paper_list.json> [--output-dir <dir>]
  
JSON 格式：
  [{"doi": "10.xxx/yyy", "title": "...", "journal": "...", "tier": "tier1"}, ...]
  
  或带分类的格式（会自动合并 tier1_papers + tier2_papers）：
  {"tier1_papers": [...], "tier2_papers": [...]}

特性：
  - 断点续传：跳过已下载文件（检查文件大小 > 1KB）
  - 失败记录：写入 <output_dir>/download_failures.json 便于重试
  - 增量保存：每篇失败实时记录，中断后不丢数据
"""
import json
import os
import sys
import time
import argparse

import requests

# ---- Parse Args ----
parser = argparse.ArgumentParser(description="批量下载论文 PDF（青梨AI）")
parser.add_argument("json_file", help="论文列表 JSON 文件路径")
parser.add_argument("--output-dir", "-o", default="qingli_pdfs", help="PDF 输出目录（默认: qingli_pdfs）")
parser.add_argument("--auth-file", default="qingli_auth.json", help="青梨认证文件路径（默认: qingli_auth.json）")
parser.add_argument("--interval", type=int, default=2, help="提交间隔秒数（默认: 2）")
parser.add_argument("--max-wait", type=int, default=150, help="单篇轮询最长等待秒数（默认: 150）")
args = parser.parse_args()

BASE_API = "https://xcx.newacademic.net/api"

# ---- Load Papers ----
with open(args.json_file, "r", encoding="utf-8") as f:
    paper_data = json.load(f)

if isinstance(paper_data, dict) and "tier1_papers" in paper_data:
    all_papers = paper_data["tier1_papers"] + paper_data.get("tier2_papers", [])
else:
    all_papers = paper_data if isinstance(paper_data, list) else [paper_data]

os.makedirs(args.output_dir, exist_ok=True)
OUTPUT_DIR = args.output_dir
FAIL_LOG = os.path.join(args.output_dir, "download_failures.json")

# Build todo list: skip existing
todo = []
skipped_existing = 0
skipped_no_doi = 0

for i, p in enumerate(all_papers):
    doi = (p.get("doi", "") or "").strip()
    if not doi.startswith("10."):
        skipped_no_doi += 1
        continue
    filename = f"{doi.replace('/', '_').replace(':', '_')}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        skipped_existing += 1
        continue
    todo.append((i, p, doi, filename, filepath))

print(f"总论文: {len(all_papers)}")
print(f"无DOI跳过: {skipped_no_doi}")
print(f"已下载跳过: {skipped_existing}")
print(f"待下载: {len(todo)}")
print()

# ---- Auth ----
with open(args.auth_file, encoding="utf-8") as f:
    auth = json.load(f)

token = newtoken = user_code = None
org_code = "OJSYSOJS001"
for origin in auth.get("origins", []):
    if origin.get("origin") == "https://qingli.newacademic.net":
        for item in origin.get("localStorage", []):
            if item["name"] == "token":
                token = item["value"]
            elif item["name"] == "new_token":
                newtoken = item["value"]
            elif item["name"] == "email":
                user_code = item["value"]

if not token:
    print("未找到 token，请先运行 node scripts/qingli_login.js 扫码登录")
    sys.exit(1)

print(f"已加载登录态 (用户: {user_code[:25]}...)")
print()

# ---- Load previous failures ----
failures = []
if os.path.exists(FAIL_LOG):
    with open(FAIL_LOG, "r", encoding="utf-8") as f:
        failures = json.load(f)
    print(f"历史失败记录: {len(failures)} 篇")
    print()


def api_get(endpoint, token, newtoken, user_code=None):
    url = f"{BASE_API}{endpoint}"
    if user_code:
        url += f"?uc={user_code}"
    headers = {
        "token": token, "newtoken": newtoken,
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://qingli.newacademic.net/",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(endpoint, token, newtoken, payload, user_code=None):
    url = f"{BASE_API}{endpoint}"
    if user_code:
        url += f"?uc={user_code}"
    headers = {
        "token": token, "newtoken": newtoken,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://qingli.newacademic.net/",
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json()


def submit_and_wait(doi, token, newtoken, user_code, max_wait):
    """Submit DOI and poll for PDF link. Returns (pdf_url, title) or (None, error_msg)"""
    # Step 1: submit
    payload = {
        "type": 2, "text": doi, "organ_code": org_code,
        "force_type": 2, "is_artificial": 0, "force_submint": False,
    }
    data = api_post("/user/consultation/", token, newtoken, payload)
    if data.get("error_code") != 0:
        return None, f"提交失败: {data.get('msg', data)}"

    # Step 2: poll
    today = time.strftime("%Y-%m-%d")
    poll_payload = {
        "page": 1, "size": 20, "sort_by": "time_desc",
        "con_type": ["all"], "status": ["all"],
        "start_date": today, "end_date": today,
        "content": "", "read": 0, "source": 0,
    }

    target_demand = None
    interval = 5

    for elapsed in range(0, max_wait, interval):
        if elapsed > 0:
            time.sleep(interval)
        data = api_post("/literature/new_get_user_demand/", token, newtoken, poll_payload, user_code)
        if data.get("error_code") != 0:
            continue

        demands = data.get("data", {}).get("data", [])
        for d in demands:
            content = d.get("content", "") + d.get("original", "") + d.get("message", "")
            result_doi = d.get("result_info", {}).get("doi", "")
            if doi in content or doi == result_doi:
                target_demand = d
                break

        if target_demand:
            down_urls = target_demand.get("down_url", [])
            if down_urls:
                title = target_demand.get("result_info", {}).get("title", "")
                return down_urls[0], title
            status = target_demand.get("status")
            if status == 3:
                return None, f"处理失败(status=3): {target_demand.get('message','')}"

    return None, f"轮询超时({max_wait}s)"


def download_pdf(url, filepath):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()
    if len(r.content) < 1000:
        return None, f"文件太小({len(r.content)} bytes)"
    with open(filepath, "wb") as f:
        f.write(r.content)
    return filepath, None


# ---- Main Loop ----
new_failures = []
success_count = 0
fail_count = 0
start_time = time.time()

for idx, (paper_idx, paper, doi, filename, filepath) in enumerate(todo):
    title_cn = paper.get("title", "")[:70]
    journal = paper.get("journal", "?")
    tier = paper.get("tier", "?")
    
    elapsed = time.time() - start_time
    eta = (elapsed / max(idx, 1)) * (len(todo) - idx) if idx > 0 else 0
    
    print(f"[{idx+1}/{len(todo)}] [{journal}|{tier}] {title_cn}")
    print(f"    DOI: {doi}")
    
    try:
        pdf_url, info = submit_and_wait(doi, token, newtoken, user_code, args.max_wait)
        if pdf_url is None:
            print(f"    FAIL: {info}")
            new_failures.append({"index": paper_idx, "doi": doi, "title": paper.get("title",""),
                                 "journal": journal, "error": info})
            fail_count += 1
        else:
            result, err = download_pdf(pdf_url, filepath)
            if result:
                size_mb = os.path.getsize(filepath) / 1024 / 1024
                print(f"    OK: {size_mb:.1f} MB | ETA: {eta/60:.0f}min")
                success_count += 1
            else:
                print(f"    DOWNLOAD FAIL: {err}")
                new_failures.append({"index": paper_idx, "doi": doi, "title": paper.get("title",""),
                                     "journal": journal, "error": f"下载失败: {err}"})
                fail_count += 1
    except Exception as e:
        print(f"    ERROR: {e}")
        new_failures.append({"index": paper_idx, "doi": doi, "title": paper.get("title",""),
                             "journal": journal, "error": str(e)})
        fail_count += 1
    
    # Save failures incrementally
    if new_failures:
        all_failures = failures + new_failures
        with open(FAIL_LOG, "w", encoding="utf-8") as f:
            json.dump(all_failures, f, ensure_ascii=False, indent=2)
    
    # Rate limit
    if idx < len(todo) - 1:
        time.sleep(args.interval)

# ---- Summary ----
elapsed_min = (time.time() - start_time) / 60
print()
print("=" * 60)
print(f"批量下载完成！")
print(f"  成功: {success_count}")
print(f"  失败: {fail_count}")
print(f"  耗时: {elapsed_min:.1f} 分钟")
if new_failures:
    print(f"  失败记录: {FAIL_LOG}")
    print(f"  重试命令: python scripts/batch_download.py {args.json_file} -o {args.output_dir}")
print("=" * 60)

sys.exit(0 if fail_count == 0 else 1)
