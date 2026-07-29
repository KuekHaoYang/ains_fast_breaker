import json
import time
import os
import sys
from playwright.sync_api import sync_playwright

# ================= 配置区 =================
DATA_FILE = 'books.json'
# =========================================

def countdown(seconds):
    """在控制台显示动态倒计时的辅助函数"""
    for i in range(seconds, 0, -1):
        minutes, secs = divmod(i, 60)
        print(f"\r⏳ 距离开始下一本还有: {minutes:02d}分{secs:02d}秒 ...", end="", flush=True)
        time.sleep(1)
    print("\r🚀 倒计时结束，开始下一本！" + " " * 30)

def wait_for_manual_login(target_url):
    """等待用户完成浏览器登录；非交互式运行时安全退出。"""
    print("\n" + "="*60)
    print(">>> 【步骤 1】: 请手动登录。")
    print(f">>> 【步骤 2】: 登录后，确保页面在：{target_url}")
    print(">>> 【步骤 3】: 回到这里按 [Enter] 开始...")
    print("="*60 + "\n")

    if not sys.stdin.isatty():
        print("当前运行环境没有交互式 stdin，无法接收 [Enter]。")
        print("已安全停止：没有登录确认时不会处理 books.json，避免产生无效提交。")
        print("请在真实终端中运行同一命令，并在完成网页登录后按 [Enter]。")
        return False

    try:
        input()
    except (EOFError, KeyboardInterrupt):
        print("\n已停止。")
        return False

    return True

def close_browser(browser):
    """关闭浏览器；忽略中断时 Playwright driver 已断开的关闭错误。"""
    try:
        browser.close()
    except Exception as e:
        print(f"关闭浏览器时出现非致命错误，已忽略: {e}")

def run():
    if not os.path.exists(DATA_FILE):
        print(f"错误：找不到 {DATA_FILE}")
        return

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        books = json.load(f)

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-infobars']
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("正在启动浏览器...")
        # 目标网址：直接进添加页
        target_url = "https://ains.moe.gov.my/record/add"
        
        try:
            page.goto(target_url)
        except:
            print("请手动输入网址...")

        # --- 登录环节 ---
        if not wait_for_manual_login(target_url):
            close_browser(browser)
            return

        for index, book in enumerate(books):
            print(f"\n[{index + 1}/{len(books)}] 正在输入: {book['tajuk']}...")

            try:
                # 0. 确保在添加页面
                if "record/add" not in page.url:
                    page.goto(target_url)
                    time.sleep(1.5)

                # 1. 点击 Buku/E-Buku
                try:
                    # 等待并点击
                    page.locator("text=Buku/E-Buku").click(timeout=3000)
                    
                    # 检查是否有 Seterusnya 按钮
                    next_btn = page.locator("button.btn-primary:has-text('Seterusnya')")
                    if next_btn.is_visible(timeout=1000):
                        next_btn.click()
                except: pass

                # =================================================
                # Page 1: Maklumat Buku (快速填写)
                # =================================================
                page.wait_for_selector("#title", timeout=5000)

                page.locator("#title").fill(book['tajuk'])
                page.locator("#typephysical").check() # Fizikal

                # Kategori
                cat_val = "nonFiction" if "Bukan" in book['kategori'] else "fiction"
                page.locator("select:has(option[value='fiction'])").select_option(value=cat_val)

                # 其他字段
                page.locator("#noOfPage").fill(str(book['muka_surat']))
                page.locator("#isbn").fill(book['isbn'])
                page.locator("#author").fill(book['penulis'])
                page.locator("#publisher").fill(book['penerbit'])
                page.locator("#publishedYear").fill(str(book['tahun']))

                # Bahasa
                page.locator("select:has(option[value='my'])").select_option(value="my")

                # Next
                page.locator("button.btn-primary:has-text('Seterusnya')").click()

                # =================================================
                # Page 2: Rumusan (快速填写)
                # =================================================
                page.wait_for_selector("#summary", timeout=5000)
                page.locator("#summary").fill(book['rumusan'])
                page.locator("#review").fill(book['pengajaran'])

                # 评分
                try:
                    stars = page.locator(".fa-star").all()
                    if len(stars) > 0:
                        stars[-1].click()
                except: pass

                page.locator("button.btn-primary:has-text('Seterusnya')").click()

                # =================================================
                # Page 3: Gambar (跳过)
                # =================================================
                page.wait_for_selector("button.btn-primary:has-text('Seterusnya')", timeout=5000)
                page.locator("button.btn-primary:has-text('Seterusnya')").click()

                # =================================================
                # Page 4: Semak & Hantar (快速提交)
                # =================================================
                print("   -> 点击 Hantar...")
                hantar_btn = page.locator("button.btn-primary", has_text="Hantar")
                hantar_btn.wait_for(state="visible", timeout=5000)
                hantar_btn.click()

                # =================================================
                # SweetAlert 弹窗确认
                # =================================================
                print("   -> 等待确认 (Pasti)...")
                confirm_button = page.locator("button.swal2-confirm")
                confirm_button.wait_for(state="visible", timeout=5000)
                time.sleep(0.3) # 小停顿确保动画完成
                confirm_button.click()
                print("   -> 已点击 Pasti，等待提交结果...")

                # =================================================
                # ★★★ 核心修复: 精准检测提交结果 ★★★
                # =================================================
                is_success = False
                try:
                    # 等待页面上出现 "Tahniah" 文本（成功弹窗的标志）。
                    # 设置 6 秒超时。如果 6 秒内没有出现 "Tahniah"（比如出现了重复警告/系统错误）
                    # 就会超时，代码会自动跳入 except 块，判定为未成功。
                    page.locator("text=Tahniah").wait_for(state="visible", timeout=6000)
                    print("   -> 🎉 提交成功！检测到 'Tahniah' 成功标志。")
                    is_success = True
                except Exception:
                    # 如果未检测到成功标志，尝试读取此时弹窗上的错误/重复提示信息
                    try:
                        err_text = page.locator(".swal2-html-container").inner_text(timeout=2000)
                        print(f"   -> ⚠️ 提交未成功。弹窗提示: {err_text.replace('\n', ' ')}")
                    except Exception:
                        print("   -> ⚠️ 未检测到成功标志 'Tahniah'，可能已被系统判定为重复录入或报错。")

                # =================================================
                # 处理页面跳转
                # =================================================
                print("   -> 跳转至等待页面...")
                page.goto(target_url)
                
                # 等待页面加载完成
                page.wait_for_selector("text=Buku/E-Buku", timeout=10000)
                
                # =================================================
                # 根据提交状态决定是否倒计时
                # =================================================
                if is_success:
                    if index < len(books) - 1:
                        print("   -> 确认为新纪录提交成功！开始安全等待间隔...")
                        countdown(0)  # 6分钟15秒 = 375秒
                    else:
                        print("   -> 最后一本书已录入完毕，无需等待。")
                else:
                    print("   -> 检测到重复录入或提交未成功，跳过倒计时，直接开始下一本！")

            except Exception as e:
                # 应对程序执行异常（如浏览器卡死、网络断开等）
                print(f"❌ 运行中发生错误: {e}")
                print("   -> 出现异常，跳过倒计时。正在重置页面...")
                try:
                    page.goto(target_url)
                    page.wait_for_selector("text=Buku/E-Buku", timeout=5000)
                    time.sleep(1.5)
                except:
                    pass

        print("\n所有任务完成！")
        close_browser(browser)

if __name__ == "__main__":
    run()
