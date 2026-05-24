"""
auto_post.py — 多媒体文件自动上传与文案填充
接管本地浏览器，完成 Taobao / 小红书 的内容发布准备

用法:
  python auto_post.py --image <path> --copy <path> --platform taobao
  python auto_post.py --image <path> --copy <path> --platform xiaohongshu
  python auto_post.py --image <path> --copy <path> --platform all

前置条件:
  1. 已关闭所有 Chrome，用以下命令启动:
     /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
  2. 在打开的浏览器中完成目标平台的扫码登录
  3. 保持浏览器窗口打开，不要关闭
"""

import argparse
import json
import os
import time
import sys
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser


# ── 平台配置 ──────────────────────────────────────────────────────────────

PLATFORMS = {
    "taobao": {
        "name": "淘宝",
        "url": "https://seller.taobao.com/",
        "upload_selector": "input[type=file]",
        "description_selector": "#description",
    },
    "xiaohongshu": {
        "name": "小红书",
        "url": "https://creator.xiaohongshu.com/publish/publish",
        "upload_selector": "input[type=file]",
        "description_selector": ".ql-editor",
    },
}


# ── 工具函数 ──────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"  ℹ️  {msg}")


def success(msg: str):
    print(f"  ✅ {msg}")


def warn(msg: str):
    print(f"  ⚠️  {msg}")


def wait_and_click(page: Page, selector: str, timeout: int = 15000):
    """等待元素出现后点击"""
    page.wait_for_selector(selector, timeout=timeout)
    page.click(selector)
    time.sleep(1)


def wait_and_fill(page: Page, selector: str, text: str, timeout: int = 15000):
    """等待元素出现后填写文本"""
    page.wait_for_selector(selector, timeout=timeout)
    page.fill(selector, text)
    time.sleep(0.5)


# ── 浏览器连接 ─────────────────────────────────────────────────────────────

def connect_browser(port: int = 9222) -> Browser:
    """连接到已经以 debug 模式启动的本地 Chrome"""
    # 绕过系统代理（Chrome DevTools 端口走代理会 502）
    old_http = os.environ.pop("http_proxy", None)
    old_https = os.environ.pop("https_proxy", None)
    old_no_proxy = os.environ.get("no_proxy", "")
    os.environ["no_proxy"] = "127.0.0.1,localhost" + ("," + old_no_proxy if old_no_proxy else "")
    try:
        browser = sync_playwright().start().chromium.connect_over_cdp(
            f"http://127.0.0.1:{port}"
        )
        log(f"已连接到本地 Chrome (端口 {port})")
        return browser
    except Exception as e:
        print(f"❌ 无法连接到 Chrome。请确保已用以下命令启动 Chrome：")
        print()
        print(f"   /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port={port} --user-data-dir=/tmp/chrome-debug-profile")
        print()
        sys.exit(1)
    finally:
        if old_http:
            os.environ["http_proxy"] = old_http
        if old_https:
            os.environ["https_proxy"] = old_https


# ── 图片上传 ───────────────────────────────────────────────────────────────

def upload_image(page: Page, image_path: str, file_input_selector: str):
    """上传图片到当前页面的文件输入框"""
    image_path = os.path.abspath(image_path)
    if not os.path.exists(image_path):
        print(f"❌ 图片不存在: {image_path}")
        return False

    # 尝试多种常见文件上传选择器
    selectors = [
        file_input_selector,
        "input[type=file]",
        ".upload-input input[type=file]",
        "[role=button] input[type=file]",
    ]

    for sel in selectors:
        try:
            input_el = page.query_selector(sel)
            if input_el:
                input_el.set_input_files(image_path)
                success(f"图片已上传: {os.path.basename(image_path)}")
                return True
        except Exception:
            continue

    warn("未找到文件上传控件，可能需要手动上传")
    return False


# ── 平台发布逻辑 ───────────────────────────────────────────────────────────

def publish_taobao(page: Page, image_path: str, copy_text: str):
    """淘宝卖家中心 — 发布商品（填充 + 上传，不提交）"""
    log("进入淘宝卖家中心…")
    page.goto(PLATFORMS["taobao"]["url"], wait_until="domcontentloaded")
    time.sleep(3)

    # 检测登录状态
    if "login" in page.url.lower() or "passport" in page.url.lower():
        warn("检测到未登录状态，请在浏览器中完成淘宝扫码登录")
        log("等待登录（60s 超时）…")
        try:
            page.wait_for_url(
                lambda url: "login" not in url.lower() and "passport" not in url.lower(),
                timeout=60000,
            )
        except Exception:
            warn("登录超时，请手动刷新页面后重试")
            return

    success("已进入淘宝卖家中心")

    # 尝试点击"发布商品"
    try:
        publish_links = page.get_by_text("发布商品")
        if publish_links.count() > 0:
            publish_links.first.click()
            time.sleep(3)
            success("已进入发布商品页面")
        else:
            log("未找到「发布商品」按钮，停留在当前页面继续")
    except Exception:
        warn("进入发布商品页面失败，建议手动导航")

    # 上传图片（不会自动提交）
    upload_image(page, image_path, PLATFORMS["taobao"]["upload_selector"])

    # 填写描述（不会自动提交）
    log("尝试填写商品描述…")
    try:
        textareas = page.query_selector_all("textarea, [contenteditable=true], .desc-editor")
        if textareas:
            # 只填写第一个富文本框，截取前 500 字避免超限
            truncated = copy_text[:500]
            textareas[0].fill(truncated)
            success("商品描述已填入（前500字）")
        else:
            warn("未找到描述输入框，请手动粘贴文案")
    except Exception as e:
        warn(f"填写描述时出错: {e}")

    print()
    print("  ─────────────────────────────────────")
    print("  📝 淘宝操作完成。请核对信息后手动提交。")
    print("  ─────────────────────────────────────")


def publish_xiaohongshu(page: Page, image_path: str, copy_text: str):
    """小红书创作者平台 — 发布笔记（填充 + 上传，不提交）"""
    log("进入小红书创作者平台…")
    page.goto(PLATFORMS["xiaohongshu"]["url"], wait_until="domcontentloaded")
    time.sleep(3)

    # 检测登录状态
    if "login" in page.url.lower():
        warn("检测到未登录状态，请在浏览器中完成小红书扫码登录")
        log("等待登录（60s 超时）…")
        try:
            page.wait_for_url(
                lambda url: "login" not in url.lower(),
                timeout=60000,
            )
        except Exception:
            warn("登录超时，请手动刷新页面后重试")
            return

    success("已进入小红书发布页")

    # 切换到「上传图文」模式（页面默认在视频模式）
    log("切换到图文模式…")
    page.evaluate("""
        (() => {
            const spans = document.querySelectorAll('span.title');
            for (const s of spans) {
                if (s.textContent.includes('上传图文')) {
                    s.click();
                    return;
                }
            }
        })();
    """)
    time.sleep(2)

    # 上传图片
    upload_image(page, image_path, PLATFORMS["xiaohongshu"]["upload_selector"])

    # 等编辑器出现（上传后需等待渲染）
    log("等待笔记编辑器出现…")
    editor = None
    for wait in range(20):
        time.sleep(1)
        editor = page.query_selector("[contenteditable=true]")
        if editor:
            break
        # 也检查 role=textbox
        editor = page.query_selector("[role=textbox]")
        if editor:
            break

    if editor:
        log("填写笔记正文…")
        editor.fill(copy_text)
        success("笔记正文已填入")
    else:
        warn("未找到正文编辑器，请手动粘贴文案")

    # 填写标题
    log("尝试填写标题…")
    title_input = page.query_selector("input[placeholder*='标题'], input[placeholder*='title'], [class*=title] input")
    if not title_input:
        # 小红书可能用 div 做标题输入
        title_input = page.query_selector("div[class*='title'] [contenteditable=true], div[class*='Title'] [contenteditable=true]")
    if title_input:
        title = copy_text.strip().split("\n")[0][:30]
        title_input.fill(title)
        success(f"标题已填入: {title}")
    else:
        warn("未找到标题输入框，请手动填写")

    print()
    print("  ─────────────────────────────────────")
    print("  📝 小红书操作完成。请核对信息后手动发布。")
    print("  ─────────────────────────────────────")


# ── 主入口 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="自动上传图片并填充文案到电商/社交平台")
    parser.add_argument("--image", required=True, help="图片文件路径")
    parser.add_argument("--copy", help="文案文件路径，不传则从 stdin 读取")
    parser.add_argument(
        "--platform",
        required=True,
        choices=["taobao", "xiaohongshu", "all"],
        help="目标平台",
    )
    parser.add_argument("--port", type=int, default=9222, help="Chrome debug 端口 (默认 9222)")
    args = parser.parse_args()

    # 读取文案
    copy_text = ""
    if args.copy:
        with open(args.copy, "r", encoding="utf-8") as f:
            copy_text = f.read()
    else:
        print("📝 请粘贴文案内容 (Ctrl+D 结束):")
        copy_text = sys.stdin.read()

    if not copy_text.strip():
        print("❌ 文案不能为空")
        sys.exit(1)

    # 连接浏览器
    browser = connect_browser(args.port)

    try:
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()

        if args.platform in ("taobao", "all"):
            print(f"\n{'='*50}")
            print("  🎯 平台: 淘宝")
            print(f"{'='*50}")
            publish_taobao(page, args.image, copy_text)

        if args.platform in ("xiaohongshu", "all"):
            print(f"\n{'='*50}")
            print("  🎯 平台: 小红书")
            print(f"{'='*50}")
            publish_xiaohongshu(page, args.image, copy_text)

    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
    except Exception as e:
        print(f"\n❌ 脚本出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        browser.close()
        print("\n👋 浏览器连接已关闭")


if __name__ == "__main__":
    main()
