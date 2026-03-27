##########################################################################
#   Script: Telegram Media Uploader
#   Author: @BetterCallShiv
#   Features: 
#       - Auto detects & uploads videos from local folder to Telegram.
#       - Creates random 10 images preview album for each video.
#       - Upload media with custom thumbnail and filename as caption.
#   How to Use:
#       1. Install Python packages: pip install pyrogram tgcrypto
#       2. Ensure ffmpeg is installed and added to your system PATH.
#       3. Add your API_ID, API_HASH and BOT_TOKEN in the config section.
#       4. Create a folder named "uploads" in the same dir where the script is.
#       5. Place your .mp4, .mkv or .mov files inside the "uploads" folder.
#       6. Run the script.
#       7. Go to your bot on Telegram and send /process to start the uploading.
##########################################################################

import asyncio
import logging
import os
import time
import json
import random
from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto
from pyrogram.errors import FloodWait
import sys
sys.stdout.reconfigure(encoding='utf-8')

# ================= CONFIG =================
API_ID = ""
API_HASH = ""
BOT_TOKEN = ""
USER_SESSION = "user"
BOT_SESSION = "bot"
LOCAL_DIR = "uploads"
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("BCS-Uploader")
app = Client(BOT_SESSION, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
app.is_processing = False 



def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024


async def get_video_metadata(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "v:0", file_path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        data = json.loads(stdout.decode())
        stream = data["streams"][0]
        duration = int(float(stream.get("duration", 0))) if stream.get("duration") else None
        width = int(stream.get("width", 0)) if stream.get("width") else None
        height = int(stream.get("height", 0)) if stream.get("height") else None
        return duration, width, height
    except Exception as e:
        LOG.warning(f"Metadata error for {file_path}: {e}")
        return None, None, None


async def generate_thumbnail(video_path, duration):
    output = f"{video_path}_thumb.jpg"
    target_time = int(duration * 0.15) if duration else 15
    try:
        cmd = [
            "ffmpeg", "-ss", str(target_time), "-i", video_path,
            "-vframes", "1", "-vf", "scale=320:-1",
            "-q:v", "5", "-y", output
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await process.communicate()
        if os.path.exists(output):
            if os.path.getsize(output) > 200 * 1024:
                os.remove(output)
                return None
            return output
        return None
    except Exception as e:
        LOG.warning(f"Thumbnail error: {e}")
        return None


async def generate_preview_screenshots(video_path, duration, num_screenshots=10):
    if not duration or duration < 10:
        return []
    timestamps = random.sample(range(1, int(duration) - 1), min(num_screenshots, int(duration) - 2))
    timestamps.sort()
    screenshots = []
    for i, ts in enumerate(timestamps):
        output = f"{video_path}_preview_{i}.jpg"
        cmd = [
            "ffmpeg", "-ss", str(ts), "-i", video_path,
            "-vframes", "1", "-q:v", "5", "-y", output
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await process.communicate()
        if os.path.exists(output):
            screenshots.append(output)
    return screenshots


async def progress_callback(current, total, status_message, start_time, state):
    now = time.time()
    if now - state["last_update"] < 3:
        return
    state["last_update"] = now
    percent = (current / total) * 100 if total else 0
    elapsed = now - start_time
    speed = current / elapsed if elapsed > 0 else 0
    text = (
        f"📤 **Uploading Video...**\n"
        f"**File:** `{state['filename']}`\n"
        f"**Progress:** {percent:.1f}%\n"
        f"**Size:** {format_size(current)} / {format_size(total)}\n"
        f"**Speed:** {format_size(speed)}/s"
    )
    try:
        await status_message.edit_text(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass


async def upload_file(client, file_path, chat_id, status_message, index, total_files):
    if not os.path.exists(file_path):
        return False
    duration, width, height = await get_video_metadata(file_path)
    name = os.path.splitext(os.path.basename(file_path))[0]
    name = " ".join(name.replace("_", " ").split())
    await status_message.edit_text(f"📸 Generating {name} previews...")
    screenshots = await generate_preview_screenshots(file_path, duration)
    if screenshots:
        await status_message.edit_text(f"🖼 Uploading previews for {name}...")
        media_group = []
        for i, shot in enumerate(screenshots):
            if i == 0:
                media_group.append(InputMediaPhoto(media=shot, caption=f"**{name}**"))
            else:
                media_group.append(InputMediaPhoto(media=shot))
        try:
            await client.send_media_group(chat_id=chat_id, media=media_group)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await client.send_media_group(chat_id=chat_id, media=media_group)
        except Exception as e:
            LOG.error(f"Failed to send media group: {e}")
        finally:
            for shot in screenshots:
                if os.path.exists(shot):
                    os.remove(shot)
    await status_message.edit_text(f"⚙️ Preparing video file...")
    thumb = await generate_thumbnail(file_path, duration)
    start_time = time.time()
    state = {"last_update": 0, "filename": name}
    try:
        await client.send_video(
            chat_id=chat_id,
            video=file_path,
            duration=duration,
            width=width,
            height=height,
            thumb=thumb,
            caption=f"**{name}**",
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(status_message, start_time, state)
        )
        return True
    except FloodWait as e:
        LOG.warning(f"Floodwait: Sleeping for {e.value}s")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        LOG.error(f"Upload failed for {file_path}: {e}")
        return False
    finally:
        if thumb and os.path.exists(thumb):
            os.remove(thumb)


async def process_files(client, message):
    if app.is_processing:
        await message.reply("⚠️ A process is already running.")
        return
    app.is_processing = True
    status_msg = await message.reply("🔍 Scanning local directory for files...")
    files = []
    for root, _, f in os.walk(LOCAL_DIR):
        for file in f:
            if file.lower().endswith((".mp4", ".mkv", ".mov")):
                files.append(os.path.join(root, file))
    total = len(files)
    if total == 0:
        await status_msg.edit_text("❌ No supported video files found in the directory.")
        app.is_processing = False
        return
    uploaded = 0
    for i, file in enumerate(files, start=1):
        success = await upload_file(client, file, message.chat.id, status_msg, i, total)
        if success:
            uploaded += 1
        await asyncio.sleep(3)
    await status_msg.edit_text(f"✅ **Process Complete!**\nSuccessfully uploaded {uploaded} out of {total} files.")
    app.is_processing = False


@app.on_message(filters.command("start"))
async def cmd_start(client, message):
    await message.reply("🤖 Bot ready. Drop files in your local directory and use /process to begin.")

@app.on_message(filters.command("process"))
async def cmd_process(client, message):
    asyncio.create_task(process_files(client, message))

# ================= MAIN =================
if __name__ == "__main__":
    print("Bot running...")
    app.run()
