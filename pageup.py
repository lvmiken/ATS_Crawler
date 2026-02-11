import asyncio
import re
import pandas as pd
from playwright.async_api import async_playwright

async def scrape_rpi_jobs_structured():
    async with async_playwright() as p:
        # 1. 启动浏览器 (关闭无头模式，方便你观察是否有弹窗)
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.set_default_navigation_timeout(60000)

        print("🚀 正在启动 RPI 职位抓取引擎...")
        
        try:
            # 访问页面，使用较轻量级的等待
            await page.goto("https://careers.rpi.edu/cw/en-us/listing/", wait_until="domcontentloaded")
            
            print("⏳ 正在检测职位列表...")
            # 修改点：只要元素在 HTML 里就行 (state='attached')，不强制要求它在屏幕上完全可见
            try:
                await page.wait_for_selector(".job-link", state="attached", timeout=15000)
            except:
                print("⚠️ 自动等待超时，但尝试强制解析页面...")
        except Exception as e:
            print(f"❌ 导航出错: {e}")
            await browser.close()
            return

        # 检查并尝试关闭可能存在的 Cookie 弹窗（PageUp 常见干扰项）
        # 如果你运行后看到页面有弹窗，程序会自动尝试点击它
        cookie_btn = page.locator("button:has-text('Accept'), #consent_prompt_submit")
        if await cookie_btn.is_visible():
            await cookie_btn.click()
            print("🍪 已关闭 Cookie 弹窗")

        # --- 2. 处理“More Jobs”加载 ---
        print("📑 正在展开所有职位列表...")
        while True:
            # 强制向下滚动
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            
            more_jobs_btn = page.locator("a.load-more-jobs")
            if await more_jobs_btn.count() > 0 and await more_jobs_btn.is_visible():
                print("🖱️ 点击加载更多...")
                try:
                    await more_jobs_btn.click()
                    await asyncio.sleep(2) 
                except:
                    break
            else:
                break

        # --- 3. 获取列表链接 ---
        job_elements = page.locator(".job-link")
        total_count = await job_elements.count()
        
        if total_count == 0:
            print("❌ 依然没有找到职位。请检查浏览器窗口是否被反爬验证拦截。")
            await browser.close()
            return

        print(f"✅ 成功找到 {total_count} 个职位。开始深度结构化解析...")

        # 预存 URL
        job_urls = []
        for i in range(total_count):
            el = job_elements.nth(i)
            href = await el.get_attribute("href")
            title = await el.inner_text()
            job_urls.append({"title": title.strip(), "url": "https://careers.rpi.edu" + href})

        # --- 4. 详情页解析逻辑 ---
        final_results = []
        for i, item in enumerate(job_urls):
            print(f"🔍 [{i+1}/{total_count}] 正在解析: {item['title']}")
            try:
                await page.goto(item['url'], wait_until="domcontentloaded")
                # 详情页同样使用 state="attached"
                await page.wait_for_selector("#job-content", state="attached", timeout=10000)
                
                full_text = await page.inner_text("#job-content")
                
                # 结构化字段提取
                job_no = re.search(r'Job no:\s*(\d+)', full_text)
                work_type = re.search(r'Work type:\s*([^\n]+)', full_text)
                location = re.search(r'Location:\s*([^\n]+)', full_text)
                salary = re.search(r'(?:Expected hiring range|Rate of Pay Range|Starting Salary/Rate|Salary Range/Rate):\s*([^\n]+)', full_text, re.IGNORECASE)
                adv_date = re.search(r'Advertised:\s*(\d+\s\w+\s\d{4})', full_text)
                
                qual_match = re.search(r'Minimum Qualifications\n\n(.*?)(?:\n\n\n\n|\n\nPreferred|\n\nMinimum Knowledge)', full_text, re.DOTALL)
                quals = qual_match.group(1).strip() if qual_match else "见详情"

                final_results.append({
                    "职位名称": item['title'],
                    "职位编号": job_no.group(1) if job_no else "N/A",
                    "工作类型": work_type.group(1).strip() if work_type else "N/A",
                    "薪资/待遇": salary.group(1).strip() if salary else "未标明",
                    "地点": location.group(1).strip() if location else "N/A",
                    "发布日期": adv_date.group(1) if adv_date else "N/A",
                    "任职要求简述": quals[:400].replace('\t', ''),
                    "链接": item['url']
                })
            except Exception as e:
                print(f"⚠️ 跳过职位 {item['title']}")
                continue

        # --- 5. 导出 Excel ---
        if final_results:
            df = pd.DataFrame(final_results)
            output_name = "RPI_Jobs_Final_Report.xlsx"
            df.to_excel(output_name, index=False)
            print(f"\n✨ 抓取圆满完成！文件已保存: {output_name}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_rpi_jobs_structured())