#!/usr/bin/env python3
"""
青梨AI 自动下载器
根据 DOI 自动提交、轮询、获取 PDF 直链并下载

用法:
    python qingli_downloader.py <DOI>
    python qingli_downloader.py 10.1016/j.artmed.2025.103345

环境要求:
    pip install requests

前置条件:
    - 必须先运行 node qingli_login.js 扫码登录，生成 qingli_auth.json
    - qingli_auth.json 与脚本放在同一目录
"""
import json
import os
import sys
import time

import requests

# --- 配置 ---
AUTH_FILE = os.path.join(os.path.dirname(__file__), "qingli_auth.json")
OUTPUT_DIR = os.path.join(os.getcwd(), "qingli_pdfs")
BASE_API = "https://xcx.newacademic.net/api"


def load_auth():
    """从 Playwright auth state 读取 token 和用户信息"""
    if not os.path.exists(AUTH_FILE):
        raise RuntimeError(
            f"未找到 {AUTH_FILE}，请先运行:\n"
            f"    node qingli_login.js"
        )

    with open(AUTH_FILE, encoding="utf-8") as f:
        auth = json.load(f)

    token = None
    newtoken = None
    user_code = None
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
                elif item["name"] == "org_ode":
                    org_code = item["value"]

    if not token:
        raise RuntimeError("未找到 token，请先运行 node qingli_login.js 扫码登录")

    # Check token expiration
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            import base64
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            if "exp" in data:
                remaining = (data["exp"] - time.time()) / 86400
                if remaining < 3:
                    print(f"\n⚠️  WARNING: token 将在 {remaining:.1f} 天后过期，请重新扫码登录!\n")
                print(f"Token 剩余有效天数: {remaining:.0f} 天")
    except Exception:
        pass

    return token, newtoken, user_code, org_code


def api_call(method, endpoint, token, newtoken, user_code=None, payload=None):
    """通用 API 调用"""
    url = f"{BASE_API}{endpoint}"
    if user_code:
        url += f"?uc={user_code}"

    headers = {
        "token": token,
        "newtoken": newtoken,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://qingli.newacademic.net/",
    }

    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload)
    else:
        data = ""

    if method.upper() == "GET":
        r = requests.get(url, headers=headers, timeout=30)
    else:
        r = requests.post(url, headers=headers, data=data, timeout=30)

    r.raise_for_status()
    return r.json()


def submit_doi(token, newtoken, doi, org_code):
    """提交 DOI 到青梨系统"""
    print(f"[1/4] 提交 DOI: {doi}")
    payload = {
        "type": 2,
        "text": doi,
        "organ_code": org_code,
        "force_type": 2,
        "is_artificial": 0,
        "force_submint": False,
    }
    data = api_call("POST", "/user/consultation/", token, newtoken, payload=payload)
    if data.get("error_code") == 0:
        print(f"      提交成功")
        return True
    else:
        print(f"      提交失败: {data}")
        return False


def get_demands(token, newtoken, user_code):
    """获取用户资源需求列表"""
    today = time.strftime("%Y-%m-%d")
    payload = {
        "page": 1,
        "size": 20,
        "sort_by": "time_desc",
        "con_type": ["all"],
        "status": ["all"],
        "start_date": today,
        "end_date": today,
        "content": "",
        "read": 0,
        "source": 0,
    }
    return api_call("POST", "/literature/new_get_user_demand/", token, newtoken, user_code, payload)


def find_demand_by_doi(demands, doi):
    """在需求列表中查找匹配的 DOI"""
    for d in demands:
        content = d.get("content", "") + d.get("original", "") + d.get("message", "")
        result_doi = d.get("result_info", {}).get("doi", "")
        if doi in content or doi == result_doi:
            return d
    return None


def download_pdf(url, doi):
    """从 CDN 下载 PDF"""
    print(f"[4/4] 下载 PDF...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()

    if len(r.content) < 1000:
        print(f"      文件太小 ({len(r.content)} bytes)，可能不是 PDF")
        return None

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    filename = f"{doi.replace('/', '_').replace(':', '_')}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(r.content)

    size_mb = len(r.content) / (1024 * 1024)
    print(f"      已保存: {filepath} ({size_mb:.1f} MB)")
    return filepath


def main():
    if len(sys.argv) < 2:
        print("用法: python qingli_downloader.py <DOI>")
        print("例:   python qingli_downloader.py 10.1016/j.artmed.2025.103345")
        sys.exit(1)

    doi = sys.argv[1].strip()

    # Load auth
    token, newtoken, user_code, org_code = load_auth()
    print(f"已加载登录态 (用户: {user_code[:25]}...)")

    # Step 1: Submit DOI
    if not submit_doi(token, newtoken, doi, org_code):
        print("提交失败，退出")
        sys.exit(1)

    # Step 2: Poll for completion
    print("[2/4] 轮询处理状态...")
    target_demand = None
    # 2026-10-13 实测：服务端生成 PDF 需要约 3–6 分钟（create_time→complete_time 相差 335 秒）。
    # 原来只等 60 秒，会误报“处理完成但未返回 PDF 链接”，看着像没有馆藏。
    max_wait = 900
    interval = 15

    for i in range(0, max_wait, interval):
        time.sleep(interval)
        data = get_demands(token, newtoken, user_code)
        if data.get("error_code") != 0:
            print(f"      查询失败: {data.get('msg')}")
            continue

        demands = data.get("data", {}).get("data", [])
        target_demand = find_demand_by_doi(demands, doi)

        if target_demand:
            status = target_demand.get("status")
            down_urls = target_demand.get("down_url", [])
            title = target_demand.get("result_info", {}).get("title", "")
            print(f"      找到记录: {title[:60]}")

            if down_urls:
                print(f"      PDF 已就绪！")
                break
            else:
                print(f"      还在处理中... ({i+interval}s)")
        else:
            print(f"      未找到记录，继续等待... ({i+interval}s)")

    if not target_demand:
        print("轮询超时，未找到该 DOI 的记录")
        sys.exit(1)

    down_urls = target_demand.get("down_url", [])
    if not down_urls:
        print("处理完成但未返回 PDF 链接")
        sys.exit(1)

    pdf_url = down_urls[0]
    print(f"[3/4] PDF 链接: {pdf_url[:80]}...")

    # Step 4: Download
    filepath = download_pdf(pdf_url, doi)
    if filepath:
        title = target_demand.get("result_info", {}).get("title", "")
        print(f"\n完成！")
        print(f"  标题: {title}")
        print(f"  文件: {filepath}")
    else:
        print("\n下载失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
