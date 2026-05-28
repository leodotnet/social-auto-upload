# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from playwright.async_api import Playwright, async_playwright

from conf import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
from utils.files_times import get_absolute_path
from utils.log import logger as default_logger

# 创建 YouTube 专用日志记录器
youtube_logger = default_logger

_NAV_TIMEOUT_MS = 120_000


def _copy_chrome_profile(user_data_dir: str, profile_directory: str | None) -> str:
    """Copy a Chrome profile into a temporary user data dir for automation."""
    source_root = Path(user_data_dir)
    profile_name = profile_directory or "Default"
    temp_root = Path(tempfile.mkdtemp(prefix="sau_youtube_chrome_"))

    local_state = source_root / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, temp_root / "Local State")

    def ignore_profile_files(_directory, names):
        ignored = {
            "SingletonCookie",
            "SingletonLock",
            "SingletonSocket",
            "Crashpad",
            "BrowserMetrics",
            "GrShaderCache",
            "GraphiteDawnCache",
            "ShaderCache",
        }
        return {name for name in names if name in ignored or name.endswith("-journal")}

    shutil.copytree(
        source_root / profile_name,
        temp_root / profile_name,
        ignore=ignore_profile_files,
        dirs_exist_ok=True,
    )
    return str(temp_root)


async def _launch_chromium(
    playwright,
    *,
    headless: bool,
    user_data_dir: str | None = None,
    profile_directory: str | None = None,
):
    """Launch Chromium browser/context for YouTube.

    Returns:
        tuple[browser, context]
    """
    path = (LOCAL_CHROME_PATH or "").strip()
    kwargs = {"headless": headless}
    if path:
        kwargs["executable_path"] = path
    temp_user_data_dir = None
    if user_data_dir:
        temp_user_data_dir = _copy_chrome_profile(user_data_dir, profile_directory)
        persistent_args = []
        if profile_directory:
            persistent_args.append(f"--profile-directory={profile_directory}")
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=temp_user_data_dir,
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            args=persistent_args,
            **kwargs,
        )
        return context.browser, context, temp_user_data_dir
    browser = await playwright.chromium.launch(**kwargs)
    context = await browser.new_context(
        locale="en-US",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    return browser, context, temp_user_data_dir


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


async def cookie_auth(account_file):
    """Verify if saved YouTube cookie is still valid."""
    async with async_playwright() as playwright:
        browser, context, temp_user_data_dir = await _launch_chromium(playwright, headless=LOCAL_CHROME_HEADLESS)
        try:
            await context.close()
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            page = await context.new_page()
            
            await page.goto(
                "https://studio.youtube.com/",
                wait_until="domcontentloaded",
                timeout=_NAV_TIMEOUT_MS,
            )
            await page.wait_for_timeout(2000)
            
            try:
                # 检查是否已登录（看是否能访问到 Studio 的主要元素）
                await page.wait_for_selector(
                    'yt-icon-button[aria-label*="Create"], button[aria-label*="Create"]',
                    timeout=5000
                )
                youtube_logger.success("[+] YouTube cookie valid")
                return True
            except Exception:
                youtube_logger.error("[+] YouTube cookie expired or invalid")
                return False
        finally:
            await browser.close()
            if temp_user_data_dir:
                shutil.rmtree(temp_user_data_dir, ignore_errors=True)


async def youtube_setup(
    account_file,
    handle=False,
    use_local_profile: bool = False,
    profile_directory: str | None = None,
):
    """Setup YouTube authentication flow."""
    account_file = get_absolute_path(account_file, "youtube_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        youtube_logger.info('[+] YouTube cookie not found or expired. Opening browser for login...')
        await get_youtube_cookie(
            account_file,
            use_local_profile=use_local_profile,
            profile_directory=profile_directory,
        )
    return True


async def get_youtube_cookie(
    account_file,
    use_local_profile: bool = False,
    profile_directory: str | None = None,
):
    """Interactive YouTube login flow using Playwright."""
    async with async_playwright() as playwright:
        browser, context, temp_user_data_dir = await _launch_chromium(
            playwright,
            headless=LOCAL_CHROME_HEADLESS,
            user_data_dir=_get_chrome_user_data_dir() if use_local_profile else None,
            profile_directory=profile_directory if use_local_profile else None,
        )
        try:
            context = await set_init_script(context)
            page = await context.new_page()
            
            try:
                await page.goto(
                    "https://studio.youtube.com/",
                    wait_until="domcontentloaded",
                    timeout=_NAV_TIMEOUT_MS,
                )
            except Exception as exc:
                youtube_logger.warning(
                    f"Opening YouTube Studio timeout or interrupted ({exc!s}). "
                    "You can manually login in the browser window, then press Enter to save cookie."
                )
            
            if sys.stdin.isatty():
                youtube_logger.info(
                    "Browser opened at YouTube Studio. Please complete login (or confirm already logged in), "
                    "then return to this terminal and press Enter to save cookie."
                )
                await asyncio.to_thread(input, "Press Enter after login to save cookie … ")
            else:
                youtube_logger.warning(
                    "Non-interactive terminal detected. Using Playwright pause; click Resume in Inspector."
                )
                await page.pause()
            
            os.makedirs(os.path.dirname(account_file) or ".", exist_ok=True)
            await context.storage_state(path=account_file)
            youtube_logger.success(f"[+] Cookie saved to {account_file}")
        finally:
            await browser.close()
            if temp_user_data_dir:
                shutil.rmtree(temp_user_data_dir, ignore_errors=True)


class YoutubeVideo:
    """YouTube video uploader using Playwright."""
    
    def __init__(self, title: str, file_path: str, tags: list[str], 
                 publish_date: datetime | int, account_file: str,
                 description: str = "", thumbnail_path: str | None = None,
                 privacy: str = "PUBLIC"):
        self.title = title
        self.file_path = file_path
        self.description = description
        self.tags = tags
        self.publish_date = publish_date
        self.thumbnail_path = thumbnail_path
        self.account_file = account_file
        self.privacy = privacy  # PRIVATE, UNLISTED, PUBLIC
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
    
    async def _dismiss_popups(self, page):
        """Dismiss common YouTube Studio popups."""
        try:
            cancel_dialog = page.locator('ytcp-confirmation-dialog:has-text("Cancel upload")')
            if await cancel_dialog.count():
                keep_editing = page.locator(
                    'ytcp-confirmation-dialog button:has-text("Continue editing"), '
                    'ytcp-confirmation-dialog button:has-text("Keep editing")'
                ).first
                if await keep_editing.count():
                    await keep_editing.click(timeout=2000)
                    await page.wait_for_timeout(500)

            safe_buttons = await page.locator(
                'button:has-text("Got it"), '
                'button:has-text("Not now"), '
                'button:has-text("No thanks"), '
                'button:has-text("以后再说"), '
                'button:has-text("知道了")'
            ).all()
            for btn in safe_buttons[:3]:
                try:
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
        except Exception:
            pass
    
    async def upload_video_file(self, page):
        """Upload video file to YouTube."""
        youtube_logger.info(f"[+] Uploading video: {self.title}")
        
        try:
            create_button = page.locator(
                'yt-icon-button[aria-label*="Create"], '
                'button[aria-label*="Create"], '
                'yt-icon-button[aria-label*="创建"], '
                'button[aria-label*="创建"]'
            ).first
            await create_button.click(timeout=30000)
            await page.wait_for_timeout(1000)
            
            upload_button = page.locator(
                'yt-formatted-string:has-text("Upload video"), '
                'tp-yt-paper-item:has-text("Upload video"), '
                'yt-formatted-string:has-text("上传视频"), '
                'tp-yt-paper-item:has-text("上传视频")'
            ).first
            await upload_button.click(timeout=30000)

            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files(self.file_path, timeout=30000)
            
            youtube_logger.info(f"[+] Video file uploaded: {Path(self.file_path).name}")
            
        except Exception as e:
            youtube_logger.error(f"[-] Failed to upload video file: {str(e)}")
            raise
    
    async def fill_metadata(self, page):
        """Fill in video metadata (title, description, tags)."""
        try:
            youtube_logger.info("[+] Filling metadata...")

            await page.wait_for_selector('ytcp-video-metadata-editor', timeout=120000)

            title_input = page.locator(
                'ytcp-social-suggestions-textbox[aria-label*="Title"] #textbox, '
                'ytcp-social-suggestions-textbox[aria-label*="标题"] #textbox, '
                '#title-textarea #textbox'
            ).first
            await title_input.click(timeout=30000)
            await page.keyboard.press("Meta+A")
            await page.keyboard.type(self.title)
            youtube_logger.info(f"  [-] Title set: {self.title}")
            
            await page.wait_for_timeout(500)
            
            if self.description:
                desc_input = page.locator(
                    'ytcp-social-suggestions-textbox[aria-label*="Description"] #textbox, '
                    'ytcp-social-suggestions-textbox[aria-label*="说明"] #textbox, '
                    '#description-textarea #textbox'
                ).first
                await desc_input.click(timeout=30000)
                await page.keyboard.press("Meta+A")
                await page.keyboard.type(self.description)
                youtube_logger.info(f"  [-] Description set ({len(self.description)} chars)")
            
            await page.wait_for_timeout(500)
            
            # 添加标签
            if self.tags:
                tags_input = page.locator('input[aria-label*="Tag"]').first
                for tag in self.tags:
                    await tags_input.click()
                    await tags_input.fill(tag)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(200)
                youtube_logger.info(f"  [-] Tags added: {', '.join(self.tags)}")
            
        except Exception as e:
            youtube_logger.error(f"[-] Failed to fill metadata: {str(e)}")
            raise

    async def set_audience(self, page):
        """Select the standard 'not made for kids' audience option."""
        try:
            not_for_kids = page.locator(
                'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"], '
                'tp-yt-paper-radio-button:has-text("No, it")'
            ).first
            await not_for_kids.click(timeout=30000)
            youtube_logger.info("  [-] Audience set: not made for kids")
        except Exception as e:
            youtube_logger.warning(f"[-] Could not set audience: {str(e)}")

    async def advance_to_visibility(self, page):
        """Move through YouTube Studio's Details, Video elements, and Checks steps."""
        for index in range(3):
            next_button = page.locator(
                'ytcp-button#next-button:not([disabled]), '
                'ytcp-button:has-text("Next"):not([disabled]), '
                'ytcp-button:has-text("下一步"):not([disabled])'
            ).first
            await next_button.click(timeout=180000)
            youtube_logger.info(f"  [-] Advanced upload wizard step {index + 1}")
            await page.wait_for_timeout(1000)
    
    async def set_privacy(self, page):
        """Set video privacy level."""
        try:
            youtube_logger.info(f"[+] Setting privacy to: {self.privacy}")

            privacy_selector = page.locator(
                'tp-yt-paper-radio-button[name="PRIVATE"], '
                'tp-yt-paper-radio-button:has-text("Private"), '
                'tp-yt-paper-radio-button:has-text("私享")'
            ).first
            if self.privacy == "PUBLIC":
                privacy_selector = page.locator(
                    'tp-yt-paper-radio-button[name="PUBLIC"], '
                    'tp-yt-paper-radio-button:has-text("Public"), '
                    'tp-yt-paper-radio-button:has-text("公开")'
                ).first
            elif self.privacy == "UNLISTED":
                privacy_selector = page.locator(
                    'tp-yt-paper-radio-button[name="UNLISTED"], '
                    'tp-yt-paper-radio-button:has-text("Unlisted"), '
                    'tp-yt-paper-radio-button:has-text("不公开列出")'
                ).first
            
            await privacy_selector.click(timeout=30000)
            await page.wait_for_timeout(500)
            youtube_logger.info(f"  [-] Privacy set to {self.privacy}")
            
        except Exception as e:
            youtube_logger.warning(f"[-] Could not set privacy: {str(e)}")
    
    async def set_scheduled_time(self, page, publish_date: datetime):
        """Schedule video publish time."""
        try:
            youtube_logger.info(f"[+] Scheduling for: {publish_date}")
            
            # 点击"Scheduled"选项（如果存在）
            schedule_button = page.locator('yt-formatted-string:has-text("Schedule")').first
            await schedule_button.click()
            await page.wait_for_timeout(500)
            
            # 填写日期和时间
            date_input = page.locator('input[type="date"]').first
            time_input = page.locator('input[type="time"]').first
            
            if date_input:
                date_str = publish_date.strftime("%Y-%m-%d")
                await date_input.fill(date_str)
            
            if time_input:
                time_str = publish_date.strftime("%H:%M")
                await time_input.fill(time_str)
            
            youtube_logger.info(f"  [-] Schedule set")
            
        except Exception as e:
            youtube_logger.warning(f"[-] Could not set schedule: {str(e)}")
    
    async def publish(self, page):
        """Publish the video."""
        try:
            youtube_logger.info("[+] Publishing video...")

            publish_button = page.locator(
                'ytcp-button#done-button:not([disabled]), '
                'ytcp-button:has-text("Save"):not([disabled]), '
                'ytcp-button:has-text("Publish"):not([disabled]), '
                'ytcp-button:has-text("保存"):not([disabled]), '
                'ytcp-button:has-text("发布"):not([disabled])'
            ).first
            await publish_button.click(timeout=180000)
            
            # 等待发布完成
            await page.wait_for_timeout(3000)
            
            youtube_logger.success("[+] Video published successfully!")
            
        except Exception as e:
            youtube_logger.error(f"[-] Failed to publish: {str(e)}")
            raise
    
    async def upload(self, playwright: Playwright) -> None:
        """Main upload workflow."""
        browser, context, temp_user_data_dir = await _launch_chromium(
            playwright,
            headless=self.headless,
            user_data_dir=None  # Use saved cookies
        )
        
        try:
            await context.close()
            context = await browser.new_context(storage_state=self.account_file)
            page = await context.new_page()
            
            await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded")
            
            # 上传视频
            await self.upload_video_file(page)
            await page.wait_for_timeout(2000)
            
            # 消除弹窗
            await self._dismiss_popups(page)
            
            # 填写元数据
            await self.fill_metadata(page)
            await page.wait_for_timeout(1000)

            await self.set_audience(page)
            await self.advance_to_visibility(page)
            
            # 设置隐私
            await self.set_privacy(page)
            
            # 如果需要定时发布
            if isinstance(self.publish_date, datetime) and self.publish_date > datetime.now():
                await self.set_scheduled_time(page, self.publish_date)
            
            # 发布
            await self.publish(page)
            
            # 保存 cookie
            await context.storage_state(path=self.account_file)
            youtube_logger.info('[+] Cookie updated!')
            
            await page.wait_for_timeout(2000)
            
        finally:
            await browser.close()
            if temp_user_data_dir:
                shutil.rmtree(temp_user_data_dir, ignore_errors=True)
    
    async def main(self):
        """Run the upload workflow."""
        async with async_playwright() as playwright:
            await self.upload(playwright)
