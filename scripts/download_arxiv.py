#!/usr/bin/env python3
"""
下载 arXiv 预印本 PDF（从 arxiv.org 免费直下）
arXiv 论文无 DOI，青梨AI无法下载，但 arXiv 提供免费 PDF。

用法：
  python scripts/download_arxiv.py <arxiv_id> [<arxiv_id> ...] [--output-dir <dir>]
  
示例：
  python scripts/download_arxiv.py 2607.25324 2605.14108 -o my_pdfs/
"""
import os
import sys
import time
import argparse

import requests


def download_arxiv(arxiv_id, output_dir, label=""):
    """Download a single arXiv paper PDF. Returns (filepath, error)"""
    filename = f"arxiv_{arxiv_id}.pdf"
    filepath = os.path.join(output_dir, filename)

    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        print(f"  SKIP (已存在): {label}")
        return filepath, None

    url = f"https://arxiv.org/pdf/{arxiv_id}"
    print(f"  URL: {url}")

    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        r.raise_for_status()
        if len(r.content) < 1000:
            return None, f"文件太小({len(r.content)} bytes)"
        with open(filepath, "wb") as f:
            f.write(r.content)
        print(f"  OK: {len(r.content)//1024} KB")
        return filepath, None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return None, f"arXiv 上不存在 {arxiv_id}"
        return None, str(e)
    except Exception as e:
        return None, str(e)


def main():
    parser = argparse.ArgumentParser(description="下载 arXiv 预印本 PDF")
    parser.add_argument("arxiv_ids", nargs="+", help="arXiv ID(s)，如 2607.25324")
    parser.add_argument("--output-dir", "-o", default="qingli_pdfs", help="PDF 输出目录（默认: qingli_pdfs）")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    success = 0
    fail = 0
    for i, aid in enumerate(args.arxiv_ids):
        print(f"[{i+1}/{len(args.arxiv_ids)}] arXiv: {aid}")
        result, err = download_arxiv(aid, args.output_dir)
        if err:
            print(f"  FAIL: {err}")
            fail += 1
        else:
            success += 1

        if i < len(args.arxiv_ids) - 1:
            time.sleep(3)

    print(f"\n完成: {success} 成功 / {fail} 失败")


if __name__ == "__main__":
    main()
