# -*- coding: utf-8 -*-
import re
from datetime import datetime

from playwright.async_api import Playwright, async_playwright
import asyncio
import os
import sys

from conf import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS
from uploader.tk_uploader.tk_config import Tk_Locator
from utils.base_social_media import set_init_script
from utils.files_times import get_absolute_path
from utils.log import tiktok_logger

_NAV_TIMEOUT_MS = 120_000
# TikTok Studio 会持续请求，几乎等不到 networkidle；用 domcontentloaded + 短等待即可做登录态探测


def _launch_chromium(playwright, *, headless: bool, user_data_dir: str | None = None):
    path = (LOCAL_CHROME_PATH or "").strip()
    kwargs = {"headless": headless}
    if path:
        kwargs["executable_path"] = path
    if user_data_dir:
        kwargs["args"] = [f"--user-data-dir={user_data_dir}"]
    return playwright.chromium.launch(**kwargs)


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await _launch_chromium(playwright, headless=LOCAL_CHROME_HEADLESS)
        try:
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto(
                "https://www.tiktok.com/tiktokstudio/upload?lang=en",
                wait_until="domcontentloaded",
                timeout=_NAV_TIMEOUT_MS,
            )
            await page.wait_for_timeout(3000)
            try:
                select_elements = await page.query_selector_all("select")
                for element in select_elements:
                    class_name = await element.get_attribute("class")
                    if class_name and re.match(r"tiktok-.*-SelectFormContainer.*", class_name):
                        tiktok_logger.error("[+] cookie expired")
                        return False
                tiktok_logger.success("[+] cookie valid")
                return True
            except Exception:
                tiktok_logger.success("[+] cookie valid")
                return True
        finally:
            await browser.close()


async def tiktok_setup(account_file, handle=False, use_local_profile: bool = False):
    account_file = get_absolute_path(account_file, "tk_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        tiktok_logger.info('[+] cookie file is not existed or expired. Now open the browser auto. Please login with your way(gmail phone, whatever, the cookie file will generated after login')
        await get_tiktok_cookie(account_file, use_local_profile=use_local_profile)
    return True


def _get_chrome_user_data_dir() -> str | None:
    """Get the default Chrome user data directory for current OS."""
    import platform
    system = platform.system()
    home = os.path.expanduser("~")
    
    if system == "Darwin":  # macOS
        return os.path.join(home, "Library", "Application Support", "Google", "Chrome")
    elif system == "Windows":
        return os.path.join(home, "AppData", "Local", "Google", "Chrome", "User Data")
    elif system == "Linux":
        return os.path.join(home, ".config", "google-chrome")
    return None


async def get_tiktok_cookie(account_file, use_local_profile: bool = False):
    async with async_playwright() as playwright:
        browser = await _launch_chromium(
            playwright,
            headless=LOCAL_CHROME_HEADLESS,
            user_data_dir=_get_chrome_user_data_dir() if use_local_profile else None,
        )
        try:
            context = await browser.new_context(
                locale="en-GB",
                extra_http_headers={"Accept-Language": "en-GB,en;q=0.9"},
            )
            context = await set_init_script(context)
            page = await context.new_page()
            try:
                await page.goto(
                    "https://www.tiktok.com/login?lang=en",
                    wait_until="domcontentloaded",
                    timeout=_NAV_TIMEOUT_MS,
                )
            except Exception as exc:
                tiktok_logger.warning(
                    f"打开登录页超时或中断（{exc!s}）。若浏览器里已能操作，可直接登录后在终端按回车保存 cookie。"
                )
            if sys.stdin.isatty():
                tiktok_logger.info(
                    "已在浏览器中打开登录页。请在窗口中完成登录（或确认已登录），"
                    "然后回到此终端按回车，将保存 cookie 并关闭浏览器。"
                )
                await asyncio.to_thread(input, "登录完成后按 Enter 保存 cookie … ")
            else:
                tiktok_logger.warning(
                    "非交互式终端无法按回车保存；已改用 Playwright 暂停，请在 Inspector 中点击 Resume。"
                )
                await page.pause()
            os.makedirs(os.path.dirname(account_file) or ".", exist_ok=True)
            await context.storage_state(path=account_file)
        finally:
            await browser.close()


class TiktokVideo(object):
    def __init__(self, title, file_path, tags, publish_date, account_file, thumbnail_path=None):
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.thumbnail_path = thumbnail_path
        self.account_file = account_file
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
        self.locator_base = None

    async def set_schedule_time(self, page, publish_date):
        schedule_input_element = self.locator_base.get_by_label('Schedule')
        await schedule_input_element.wait_for(state='visible')  # 确保按钮可见

        await schedule_input_element.click(force=True)
        if await self.locator_base.locator('div.TUXButton-content >> text=Allow').count():
            await self.locator_base.locator('div.TUXButton-content >> text=Allow').click()

        scheduled_picker = self.locator_base.locator('div.scheduled-picker')
        await scheduled_picker.locator('div.TUXInputBox').nth(1).click()

        calendar_month = await self.locator_base.locator(
            'div.calendar-wrapper span.month-title').inner_text()

        n_calendar_month = datetime.strptime(calendar_month, '%B').month

        schedule_month = publish_date.month

        if n_calendar_month != schedule_month:
            if n_calendar_month < schedule_month:
                arrow = self.locator_base.locator('div.calendar-wrapper span.arrow').nth(-1)
            else:
                arrow = self.locator_base.locator('div.calendar-wrapper span.arrow').nth(0)
            await arrow.click()

        # day set
        valid_days_locator = self.locator_base.locator(
            'div.calendar-wrapper span.day.valid')
        valid_days = await valid_days_locator.count()
        for i in range(valid_days):
            day_element = valid_days_locator.nth(i)
            text = await day_element.inner_text()
            if text.strip() == str(publish_date.day):
                await day_element.click()
                break
        # time set
        await scheduled_picker.locator('div.TUXInputBox').nth(0).click()

        hour_str = publish_date.strftime("%H")
        correct_minute = int(publish_date.minute / 5)
        minute_str = f"{correct_minute:02d}"

        hour_selector = f"span.tiktok-timepicker-left:has-text('{hour_str}')"
        minute_selector = f"span.tiktok-timepicker-right:has-text('{minute_str}')"

        # pick hour first
        await page.wait_for_timeout(1000)  # 等待500毫秒
        await self.locator_base.locator(hour_selector).click()
        # click time button again
        await page.wait_for_timeout(1000)  # 等待500毫秒
        # pick minutes after
        await self.locator_base.locator(minute_selector).click()

        # click title to remove the focus.
        # await self.locator_base.locator("h1:has-text('Upload video')").click()

    async def handle_upload_error(self, page):
        tiktok_logger.info("video upload error retrying.")
        select_file_button = self.locator_base.locator('button[aria-label="Select file"]')
        async with page.expect_file_chooser() as fc_info:
            await select_file_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(self.file_path)

    async def upload(self, playwright: Playwright) -> None:
        browser = await playwright.chromium.launch(headless=self.headless, executable_path=self.local_executable_path)
        context = await browser.new_context(storage_state=f"{self.account_file}")
        # context = await set_init_script(context)
        page = await context.new_page()

        # change language to eng first
        await self.change_language(page)
        await page.goto("https://www.tiktok.com/tiktokstudio/upload")
        tiktok_logger.info(f"[+] Uploading video (title length {len(self.title)} chars)")

        await page.wait_for_url("https://www.tiktok.com/tiktokstudio/upload", timeout=10000)

        # 页面可能是 iframe、旧版 upload-container，或仅渲染「Select video」；任一出现即视为可继续
        try:
            await page.wait_for_selector(
                'iframe[data-tt="Upload_index_iframe"], div.upload-container, '
                'button:has-text("Select video")',
                timeout=30000,
            )
            tiktok_logger.info("  [-] Upload UI ready (iframe, upload container, or Select video).")
        except Exception:
            tiktok_logger.warning(
                "  [-] Upload shell selectors not seen within 30s; continuing in case UI is slow or DOM changed."
            )

        await self.choose_base_locator(page)

        upload_button = self.locator_base.locator(
            'button:has-text("Select video"):visible')
        await upload_button.wait_for(state='visible')  # 确保按钮可见

        async with page.expect_file_chooser() as fc_info:
            await upload_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(self.file_path)

        await page.wait_for_timeout(2000)
        await self._dismiss_studio_popups(page)
        await self.add_title_tags(page)
        # detect upload status
        await self.detect_upload_status(page)
        if self.thumbnail_path:
            tiktok_logger.info(f'[+] Uploading thumbnail file {self.title}.png')
            await self.upload_thumbnails(page)

        if self.publish_date != 0:
            await self.set_schedule_time(page, self.publish_date)

        await self.click_publish(page)
        tiktok_logger.success(f"video_id: {await self.get_last_video_id(page)}")

        await context.storage_state(path=f"{self.account_file}")  # save cookie
        tiktok_logger.info('  [-] update cookie！')
        await asyncio.sleep(2)  # close delay for look the video status
        # close all
        await context.close()
        await browser.close()

    async def _dismiss_studio_popups(self, page) -> None:
        """Close onboarding (react-joyride), TUX modals and floating hints that block the caption editor."""
        tiktok_logger.info("  [-] Dismissing TikTok Studio overlays (tour / modals / tooltips)…")
        for _ in range(4):
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(200)

        for label in (
            "Got it",
            "OK",
            "Continue",
            "Skip",
            "Dismiss",
            "I understand",
            "Not now",
            "Maybe later",
            "Allow",
            "Next",
        ):
            try:
                btn = page.get_by_role("button", name=re.compile(rf"^{re.escape(label)}$", re.I))
                if await btn.count():
                    await btn.first.click(timeout=2500)
                    await page.wait_for_timeout(400)
            except Exception:
                pass

        try:
            await page.evaluate(
                """() => {
                    document.getElementById('react-joyride-portal')?.remove();
                    document.querySelectorAll('.react-joyride__overlay').forEach((e) => e.remove());
                }"""
            )
        except Exception:
            pass

        for _ in range(2):
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(200)

    async def _dismiss_publish_blockers(self, page) -> None:
        """Dismiss TUX dialogs that cover the Post / Post Now button (floating-ui portal)."""
        for _ in range(3):
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(150)

        overlay = page.locator('div.TUXModal-overlay[data-transition-status="open"]')
        if await overlay.count():
            for pattern in (
                r"Post Now",
                r"^Post$",
                r"Publish",
                r"OK",
                r"Got it",
                r"Continue",
                r"Confirm",
            ):
                try:
                    btn = overlay.get_by_role("button", name=re.compile(pattern, re.I))
                    if await btn.count():
                        await btn.first.click(timeout=4000)
                        await page.wait_for_timeout(500)
                        return
                except Exception:
                    pass
            try:
                primary = overlay.locator("button.Button__root--type-primary").first
                if await primary.count():
                    await primary.click(timeout=4000)
                    await page.wait_for_timeout(500)
            except Exception:
                pass

    async def _neutralize_open_tux_overlays(self, page) -> None:
        """Last resort: let clicks reach the Post button (does not remove DOM, only pointer-events)."""
        try:
            await page.evaluate(
                """() => {
                    document.querySelectorAll(
                        'div.TUXModal-overlay[data-transition-status="open"]'
                    ).forEach((el) => {
                        el.style.setProperty('pointer-events', 'none');
                    });
                }"""
            )
        except Exception:
            pass

    async def add_title_tags(self, page):
        await self._dismiss_studio_popups(page)

        editor_locator = self.locator_base.locator("div.public-DraftEditor-content")
        await editor_locator.wait_for(state="visible", timeout=20000)

        try:
            await editor_locator.focus(timeout=8000)
        except Exception:
            pass

        try:
            await editor_locator.click(timeout=8000)
        except Exception:
            tiktok_logger.info("  [-] Caption editor click intercepted; using force=True")
            await editor_locator.click(force=True, timeout=15000)

        await page.keyboard.press("End")

        await page.keyboard.press("Control+A")

        await page.keyboard.press("Delete")

        await page.keyboard.press("End")

        await page.wait_for_timeout(1000)  # 等待1秒

        await page.keyboard.insert_text(self.title)
        await page.wait_for_timeout(1000)  # 等待1秒
        await page.keyboard.press("End")

        await page.keyboard.press("Enter")

        # tag part
        for index, tag in enumerate(self.tags, start=1):
            tiktok_logger.info("Setting the %s tag" % index)
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)  # 等待1秒
            await page.keyboard.insert_text("#" + tag + " ")
            await page.keyboard.press("Space")
            await page.wait_for_timeout(1000)  # 等待1秒

            await page.keyboard.press("Backspace")
            await page.keyboard.press("End")

    async def upload_thumbnails(self, page):
        await self.locator_base.locator(".cover-container").click()
        await self.locator_base.locator(".cover-edit-container >> text=Upload cover").click()
        async with page.expect_file_chooser() as fc_info:
            await self.locator_base.locator(".upload-image-upload-area").click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(self.thumbnail_path)
        await self.locator_base.locator('div.cover-edit-panel:not(.hide-panel)').get_by_role(
            "button", name="Confirm").click()
        await page.wait_for_timeout(3000)  # wait 3s, fix it later

    async def change_language(self, page):
        # set the language to english
        await page.goto("https://www.tiktok.com")
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_selector('[data-e2e="nav-more-menu"]')
        # 已经设置为英文, 省略这个步骤
        if await page.locator('[data-e2e="nav-more-menu"]').text_content() == "More":
            return

        await page.locator('[data-e2e="nav-more-menu"]').click()
        await page.locator('[data-e2e="language-select"]').click()
        await page.locator('#creator-tools-selection-menu-header >> text=English (US)').click()

    async def click_publish(self, page):
        last_err: Exception | None = None
        for attempt in range(60):
            try:
                await self._dismiss_studio_popups(page)
                await self._dismiss_publish_blockers(page)

                if attempt >= 12 and attempt % 6 == 0:
                    await self._neutralize_open_tux_overlays(page)

                candidates = [
                    self.locator_base.locator('[data-e2e="post_video_button"]'),
                    self.locator_base.get_by_role("button", name=re.compile(r"Post Now", re.I)),
                    self.locator_base.locator("div.button-group button").filter(
                        has_text=re.compile(r"Post", re.I)
                    ),
                    self.locator_base.locator("div.button-group button").first,
                ]
                clicked = False
                for loc in candidates:
                    if await loc.count():
                        await loc.first.click(force=True, timeout=20000)
                        clicked = True
                        break
                if not clicked:
                    await asyncio.sleep(0.5)
                    continue

                await page.wait_for_url(
                    "https://www.tiktok.com/tiktokstudio/content",
                    timeout=10000,
                )
                tiktok_logger.success("  [-] video published success")
                return
            except Exception as e:
                last_err = e
                if attempt % 5 == 0:
                    tiktok_logger.info(f"  [-] video publishing (attempt {attempt + 1})")
                await asyncio.sleep(0.5)

        raise RuntimeError(f"TikTok publish failed after retries: {last_err}")

    async def get_last_video_id(self, page):
        await page.wait_for_selector('div[data-tt="components_PostTable_Container"]')
        video_list_locator = self.locator_base.locator('div[data-tt="components_PostTable_Container"] div[data-tt="components_PostInfoCell_Container"] a')
        if await video_list_locator.count():
            first_video_obj = await video_list_locator.nth(0).get_attribute('href')
            video_id = re.search(r'video/(\d+)', first_video_obj).group(1) if first_video_obj else None
            return video_id


    async def detect_upload_status(self, page):
        while True:
            try:
                # if await self.locator_base.locator('div.btn-post > button').get_attribute("disabled") is None:
                if await self.locator_base.locator(
                        'div.button-group > button >> text=Post').get_attribute("disabled") is None:
                    tiktok_logger.info("  [-]video uploaded.")
                    break
                else:
                    tiktok_logger.info("  [-] video uploading...")
                    await asyncio.sleep(2)
                    if await self.locator_base.locator(
                            'button[aria-label="Select file"]').count():
                        tiktok_logger.info("  [-] found some error while uploading now retry...")
                        await self.handle_upload_error(page)
            except:
                tiktok_logger.info("  [-] video uploading...")
                await asyncio.sleep(2)

    async def choose_base_locator(self, page):
        # await page.wait_for_selector('div.upload-container')
        if await page.locator('iframe[data-tt="Upload_index_iframe"]').count():
            self.locator_base = page.frame_locator(Tk_Locator.tk_iframe)
        else:
            self.locator_base = page.locator(Tk_Locator.default) 

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
