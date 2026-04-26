#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import discord
import requests
import re
import asyncio
import subprocess
import zipfile
import time
import os
from pathlib import Path

# =========================
# CONFIG
# =========================

DISCORD_BOT_TOKEN = "MTQyMjAxNjAwNTM2MTg5NzU2NQ.Gj5rTa.p88gUs75KdGnU7DRpxTLmOk0GPN8tasiRYcBHg"
SOURCE_CHANNEL_ID = 1474250311739637836
UPLOAD_CHANNEL_ID = 1495212529201320008

# The ONLY working directory (must already exist)
WORK_DIR = Path(r"G:\My Drive\videoposting")

# FFmpeg folder (auto-installed here)
FFMPEG_DIR = WORK_DIR / "ffmpeg"
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"

# REAL persona path
PERSONA_PATH = Path(r"C:\Users\Billy\OneDrive\videoposting\persona.mp4")

# =========================
# LOGGING
# =========================

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# =========================
# FFmpeg AUTO-INSTALL
# =========================

def ensure_ffmpeg():
    if FFMPEG_EXE.exists():
        return str(FFMPEG_EXE)

    log("⬇️ FFmpeg missing — downloading now...")

    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = FFMPEG_DIR / "ffmpeg.zip"

    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    r = requests.get(url, stream=True)
    with open(zip_path, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            f.write(chunk)

    log("📦 Extracting FFmpeg...")

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(FFMPEG_DIR)

    zip_path.unlink()

    for f in FFMPEG_DIR.rglob("ffmpeg.exe"):
        FFMPEG_EXE.write_bytes(f.read_bytes())
        break

    log("✅ FFmpeg installed successfully")
    return str(FFMPEG_EXE)

FFMPEG_PATH = ensure_ffmpeg()

# =========================
# HELPERS
# =========================

def extract_video_url(content):
    match = re.search(r"https://video\.twimg\.com/\S+?\.mp4", content)
    return match.group(0).rstrip(")") if match else None

def clean_caption(text):
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^\w\s\-\.\,\!']", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:120] if text else "video"

# =========================
# PROCESS VIDEO
# =========================

def process_video(input_path: Path, caption: str):
    safe_name = clean_caption(caption)

    # FULL video saved to Google Drive
    full_output = WORK_DIR / f"{safe_name}.mp4"

    # TEMPORARY 15-second version for Discord (will be deleted)
    discord_output = WORK_DIR / f"{safe_name}_15s.mp4"

    log(f"🎬 Processing FULL video as: {safe_name}.mp4")
    log(f"🎬 Creating 15s Discord version as: {safe_name}_15s.mp4")

    # -------------------------
    # FULL VIDEO (persona)
    # -------------------------
    if PERSONA_PATH.exists():
        log("🎭 Persona detected — applying PIP overlay")

        full_cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", str(input_path),
            "-stream_loop", "-1",
            "-i", str(PERSONA_PATH),

            "-filter_complex",
            (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,boxblur=18[bg];"
                "[0:v]scale=980:-2,setsar=1[main];"
                "[bg][main]overlay=(W-w)/2:(H-h)/2[tmp];"
                "[1:v]scale=220:-2[pip];"
                "[tmp][pip]overlay=25:25[outv]"
            ),

            "-map", "[outv]",
            "-map", "0:a?",
            "-af", "loudnorm",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-c:a", "aac",
            "-shortest",
            str(full_output)
        ]
    else:
        log("⚠️ Persona NOT found — exporting clean vertical video")

        full_cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", str(input_path),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-af", "loudnorm",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-crf", "23",
            "-preset", "ultrafast",
            str(full_output)
        ]

    subprocess.run(full_cmd, capture_output=True, text=True)

    # -------------------------
    # DISCORD 15-SECOND VERSION + LIKE POP
    # -------------------------

    discord_cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(full_output),

        # LIKE POP overlay (FFmpeg-generated)
        "-filter_complex",
        (
            "color=white@0.0:s=300x300:d=0.5[base];"
            "drawbox=50:50:200:200:white@1:t=fill[thumb];"
            "[base][thumb]overlay=0:0:enable='between(t,3,3.5)'[like];"
            "[0:v][like]overlay=(W-w)/2:(H-h)/2"
        ),

        "-t", "15",  # ⭐ FORCE MAX 15 SECONDS
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "ultrafast",
        "-crf", "23",
        str(discord_output)
    ]

    subprocess.run(discord_cmd, capture_output=True, text=True)

    return full_output, discord_output

# =========================
# DOWNLOAD + PROCESS + UPLOAD
# =========================

async def handle_video(url, caption, upload_channel):
    try:
        log(f"⬇️ Downloading: {url}")

        temp_path = WORK_DIR / f"temp_{time.strftime('%Y%m%d_%H%M%S')}.mp4"

        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()

        with open(temp_path, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)

        log("✅ Download complete")

        full_path, discord_path = process_video(temp_path, caption)

        # Upload ONLY the 15-second version
        log("📤 Uploading 15-second version to Discord...")
        await upload_channel.send(
            content=f"**{clean_caption(caption)}**",
            file=discord.File(str(discord_path))
        )
        log("✅ Discord upload complete")

        # DELETE ONLY TEMP FILES
        if temp_path.exists():
            os.remove(temp_path)

        if discord_path.exists():
            os.remove(discord_path)

        # KEEP ONLY full_path in Google Drive

    except Exception as e:
        log(f"❌ ERROR: {e}")

# =========================
# DISCORD BOT
# =========================

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    log(f"✅ Logged in as {client.user}")

    source_channel = client.get_channel(SOURCE_CHANNEL_ID)
    upload_channel = client.get_channel(UPLOAD_CHANNEL_ID)

    found = False

    async for message in source_channel.history(limit=None, oldest_first=False):
        url = extract_video_url(message.content or "")
        if url:
            log(f"🎯 Video found in message {message.id}")
            asyncio.create_task(handle_video(url, message.content, upload_channel))
            found = True
            break

    if not found:
        log("⚠️ No video found in entire channel history")

    while True:
        await asyncio.sleep(60)

client.run(DISCORD_BOT_TOKEN)
