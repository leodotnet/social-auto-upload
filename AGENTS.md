## Project Overview

This project, `social-auto-upload`, is a powerful automation tool designed to help content creators and operators efficiently publish video content to multiple domestic and international mainstream social media platforms in one click. The project implements video upload, scheduled release and other functions for platforms such as `Douyin`, `Bilibili`, `Xiaohongshu`, `Kuaishou`, `WeChat Channel`, `Baijiahao` and `TikTok`.

The project consists of a Python backend and a Vue.js frontend.

**Backend:**

*   Framework: Flask
*   Core Functionality:
    *   Handles file uploads and management.
    *   Interacts with a SQLite database to store information about files and user accounts.
    *   Uses `playwright` for browser automation to interact with social media platforms.
    *   Provides a RESTful API for the frontend to consume.
    *   Uses Server-Sent Events (SSE) for real-time communication with the frontend during the login process.

**Frontend:**

*   Framework: Vue.js
*   Build Tool: Vite
*   UI Library: Element Plus
*   State Management: Pinia
*   Routing: Vue Router
*   Core Functionality:
    *   Provides a web interface for managing social media accounts, video files, and publishing videos.
    *   Communicates with the backend via a RESTful API.

**Command-line Interface:**

The project also provides a command-line interface (CLI) for users who prefer to work from the terminal. For new Douyin CLI work, prefer the `sau douyin ...` entrypoint over legacy example scripts.

*   `login`: To log in to the Douyin uploader account.
*   `check`: To verify whether the saved Douyin cookie is still valid.
*   `upload`: To upload one video file with explicit metadata flags.

## Building and Running

### Backend

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Install Playwright browser drivers:**
    ```bash
    playwright install chromium
    ```

3.  **Initialize the database:**
    ```bash
    python db/createTable.py
    ```

4.  **Run the backend server:**
    ```bash
    python sau_backend.py
    ```
    The backend server will start on `http://localhost:5409`.

### Frontend

1.  **Navigate to the frontend directory:**
    ```bash
    cd sau_frontend
    ```

2.  **Install dependencies:**
    ```bash
    npm install
    ```

3.  **Run the development server:**
    ```bash
    npm run dev
    ```
    The frontend development server will start on `http://localhost:5173`.

### Command-line Interface

To use the CLI, you can run the `cli_main.py` script with the appropriate arguments.

**Login:**

```bash
sau douyin login --account <account_name>
```

**Check:**

```bash
sau douyin check --account <account_name>
```

**Upload:**

```bash
sau douyin upload --account <account_name> --file <video_file> --title <title> [--tags tag1,tag2] [--schedule YYYY-MM-DD HH:MM]
```

**Install bundled skill:**

```bash
sau skill install
```

## OpenClaw Publishing Runbook

Use the project virtual environment from the repository root:

```bash
./.venv/bin/python sau_cli.py <platform> <action> ...
```

Always run `check` before uploading. If `check` returns `invalid`, run the platform `login` command first and verify again.

### Current Accounts

*   TikTok: `sgreport`
    *   Cookie file: `cookies/tiktok_sgreport.json`
*   YouTube: `demo`
    *   Cookie file: `cookies/youtube_demo.json`
    *   Channel: `狮城播报`
    *   Upload default visibility: `PUBLIC`
*   Douyin: `2207157066`
    *   Cookie file: `cookies/douyin_2207157066.json`
*   Weixin Channels / 视频号: `sphVOjCNLD2SQq6`
    *   Cookie file: `cookies/tencent_sphVOjCNLD2SQq6.json`
    *   视频号名称: `狮城播报`
    *   视频号ID: `sphVOjCNLD2SQq6`
    *   Status shown in UI: `申请认证`

### TikTok

```bash
./.venv/bin/python sau_cli.py tiktok check --account sgreport
```

```bash
./.venv/bin/python sau_cli.py tiktok login --account sgreport
```

```bash
./.venv/bin/python sau_cli.py tiktok upload-video \
  --account sgreport \
  --file "/absolute/path/to/video.mp4" \
  --title "Video title" \
  --desc "Video description"
```

TikTok stores the title and description together as the caption. If using a local Chrome profile for login, prefer the explicit login flow and then re-run `check`.

### YouTube

```bash
./.venv/bin/python sau_cli.py youtube check --account demo
```

```bash
./.venv/bin/python sau_cli.py youtube login --account demo --use-local-profile --profile-directory Default
```

```bash
./.venv/bin/python sau_cli.py youtube upload-video \
  --account demo \
  --file "/absolute/path/to/video.mp4" \
  --title "Video title" \
  --desc "Video description"
```

YouTube uploads default to `PUBLIC`. Use `--privacy PRIVATE` or `--privacy UNLISTED` only when explicitly requested.

If Google blocks automated login with `This browser or app may not be secure`, open normal Chrome first and sign in manually:

```bash
open -na "Google Chrome" --args --profile-directory=Default https://studio.youtube.com
```

After normal Chrome is logged in, extract/save the YouTube cookie using the project login flow or the existing cookie export helper workflow in `uploader/youtube_uploader/main.py`, then re-run `check`.

### Douyin

```bash
./.venv/bin/python sau_cli.py douyin check --account 2207157066
```

```bash
./.venv/bin/python sau_cli.py douyin login --account 2207157066 --headed
```

```bash
./.venv/bin/python sau_cli.py douyin upload-video \
  --account 2207157066 \
  --file "/absolute/path/to/video.mp4" \
  --title "Video title" \
  --desc "Video description"
```

For new Douyin CLI work, use `sau_cli.py douyin ...` or the installed `sau douyin ...` entrypoint rather than legacy example scripts.

### Weixin Channels / 视频号

```bash
./.venv/bin/python sau_cli.py tencent check --account sphVOjCNLD2SQq6
```

```bash
./.venv/bin/python sau_cli.py tencent login --account sphVOjCNLD2SQq6
```

The video-channel login flow opens Playwright Inspector. Complete QR/login confirmation in the browser, then click `Resume` / `继续` in the Inspector so the cookie can be saved.

```bash
./.venv/bin/python sau_cli.py tencent upload-video \
  --account sphVOjCNLD2SQq6 \
  --file "/absolute/path/to/video.mp4" \
  --title "Video title" \
  --desc "Video description"
```

Use `--draft` only when the user asks to save as draft. Without `--draft`, the command publishes directly.

## Development Conventions

*   The backend code is located in the root directory and the `myUtils` and `uploader` directories.
*   The frontend code is located in the `sau_frontend` directory.
*   The project uses a SQLite database for data storage. The database file is located at `db/database.db`.
*   The `conf.example.py` file should be copied to `conf.py` and configured with the appropriate settings.
*   The `requirements.txt` file lists the Python dependencies.
*   The `package.json` file in the `sau_frontend` directory lists the frontend dependencies.
