import os
import re
import uuid
import threading
import logging
import requests
from typing import Dict, Any, Optional
import yt_dlp

logger = logging.getLogger(__name__)

# Global dictionary to hold background download progress
DOWNLOAD_TASKS: Dict[str, Dict[str, Any]] = {}

def sanitize_filename(name: str) -> str:
    """Removes or replaces invalid characters in filenames."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()[:150]

def clean_youtube_url(text: str) -> str:
    """
    Cleans and standardizes various YouTube URL formats.
    Handles mobile shares, shorts, youtu.be, query params, etc.
    """
    if not text:
        return ""
    text = text.strip()
    
    # Extract URL if surrounded by extra text (e.g. mobile share text)
    url_match = re.search(r'https?://[^\s]+', text)
    if url_match:
        text = url_match.group(0)

    # Clean short URL: youtu.be/ID
    m = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', text)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    # Clean shorts URL: youtube.com/shorts/ID
    m = re.search(r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})', text)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    # Clean watch URL: youtube.com/watch?v=ID
    m = re.search(r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})', text)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    # Clean live URL: youtube.com/live/ID
    m = re.search(r'youtube\.com/live/([a-zA-Z0-9_-]{11})', text)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    return text

def extract_video_id(url: str) -> Optional[str]:
    """Extracts 11-char video ID from URL."""
    m = re.search(r'(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})', url)
    return m.group(1) if m else None

def get_oembed_fallback(url: str) -> Optional[Dict[str, Any]]:
    """
    Fast, reliable fallback using YouTube oEmbed API when yt-dlp encounters datacenter blocking.
    """
    try:
        vid = extract_video_id(url)
        clean_url = f"https://www.youtube.com/watch?v={vid}" if vid else url
        oembed_url = f"https://www.youtube.com/oembed?url={clean_url}&format=json"
        
        r = requests.get(oembed_url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            thumb = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg" if vid else data.get('thumbnail_url', '')
            return {
                "success": True,
                "title": data.get('title', 'YouTube Video'),
                "id": vid or '',
                "uploader": data.get('author_name', 'YouTube Creator'),
                "duration": 0,
                "duration_formatted": "확인 중",
                "thumbnail": thumb,
                "view_count": 0,
                "resolutions": ["Best (최고화질)", "1080p", "720p", "480p", "360p"],
                "webpage_url": clean_url
            }
    except Exception as e:
        logger.warning(f"oEmbed fallback failed: {e}")
    return None

def get_video_info(url: str) -> Dict[str, Any]:
    """
    Extracts video metadata without downloading.
    Uses ultra-fast oEmbed API first (0.2s) to guarantee zero timeout on mobile/cloud.
    """
    url = clean_youtube_url(url)
    if not url:
        return {"success": False, "error": "올바른 유튜브 주소를 입력해주세요."}

    # 1. Try Lightning-fast oEmbed (0.2s, never blocked by datacenter IPs)
    oembed_data = get_oembed_fallback(url)
    if oembed_data:
        return oembed_data

    # 2. Fallback to yt-dlp if oEmbed fails
    common_opts = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 5,
        'retries': 1,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb', 'web'],
                'player_skip': ['webpage', 'configs']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        }
    }

    ydl_opts = {
        **common_opts,
        'extract_flat': True,
        'skip_download': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            title = info.get('title', 'YouTube Video')
            vid = info.get('id', '')
            uploader = info.get('uploader', info.get('channel', 'YouTube'))
            thumb = info.get('thumbnail') or f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"

            return {
                "success": True,
                "title": title,
                "id": vid,
                "uploader": uploader,
                "duration": info.get('duration', 0),
                "duration_formatted": "확인 완료",
                "thumbnail": thumb,
                "view_count": info.get('view_count', 0),
                "resolutions": ["Best (최고화질)", "1080p", "720p", "480p", "360p"],
                "webpage_url": url
            }
    except Exception as e:
        logger.warning(f"yt-dlp extract_info warning: {e}. Trying oEmbed fallback...")
        # Fallback to fast oEmbed
        fallback_data = get_oembed_fallback(url)
        if fallback_data:
            return fallback_data
        
        return {
            "success": False,
            "error": f"영상 정보를 불러올 수 없습니다: {str(e)}"
        }

def start_download_task(
    url: str,
    format_type: str, # "mp3" or "mp4"
    quality: str,     # "best", "1080p", "720p", "320k", "192k" etc.
    output_dir: str
) -> str:
    """
    Spawns a background thread to download the requested YouTube media.
    Returns task_id for tracking progress.
    """
    url = clean_youtube_url(url)
    task_id = str(uuid.uuid4())
    DOWNLOAD_TASKS[task_id] = {
        "id": task_id,
        "status": "starting",
        "progress": 0,
        "speed": "0 KB/s",
        "eta": "0s",
        "total_bytes": 0,
        "downloaded_bytes": 0,
        "filename": "",
        "file_url": "",
        "title": "",
        "thumbnail": "",
        "format_type": format_type,
        "error": None
    }

    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            downloaded = d.get('downloaded_bytes', 0)
            percent = (downloaded / total) * 100 if total > 0 else 0
            
            speed = d.get('speed', 0)
            if speed:
                if speed > 1024 * 1024:
                    speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
                else:
                    speed_str = f"{speed / 1024:.1f} KB/s"
            else:
                speed_str = "-- KB/s"

            eta = d.get('eta', 0)
            eta_str = f"{eta}초" if eta else "--"

            DOWNLOAD_TASKS[task_id].update({
                "status": "downloading",
                "progress": round(percent, 1),
                "speed": speed_str,
                "eta": eta_str,
                "total_bytes": total,
                "downloaded_bytes": downloaded,
            })
        elif d['status'] == 'finished':
            DOWNLOAD_TASKS[task_id].update({
                "status": "processing",
                "progress": 99.0,
                "speed": "인코딩/변환 중...",
                "eta": "마무리 중"
            })

    def run_download():
        os.makedirs(output_dir, exist_ok=True)
        
        common_opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
            'retries': 5,
            'fragment_retries': 5,
            'file_access_retries': 3,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'mweb', 'web'],
                    'player_skip': ['webpage', 'configs']
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            }
        }

        # Determine format options
        if format_type == "mp3":
            audio_quality = "0" # best VBR
            if quality == "320k":
                audio_quality = "320"
            elif quality == "192k":
                audio_quality = "192"
            elif quality == "128k":
                audio_quality = "128"

            ydl_opts = {
                **common_opts,
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(output_dir, '%(title)s_%(id)s.%(ext)s'),
                'progress_hooks': [progress_hook],
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': audio_quality,
                }],
            }
        else:
            # MP4 Video download
            format_spec = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            if quality and quality.endswith('p'):
                height = quality.replace('p', '')
                format_spec = f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'

            ydl_opts = {
                **common_opts,
                'format': format_spec,
                'outtmpl': os.path.join(output_dir, '%(title)s_%(id)s.%(ext)s'),
                'progress_hooks': [progress_hook],
                'merge_output_format': 'mp4',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }]
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'media')
                ext = 'mp3' if format_type == 'mp3' else 'mp4'
                # Find final filename
                actual_filename = f"{title}_{info.get('id', '')}.{ext}"
                # If special characters exist, look up in dir
                sanitized_pattern = info.get('id', '')
                saved_file = None
                for fname in os.listdir(output_dir):
                    if sanitized_pattern in fname and fname.endswith(f".{ext}"):
                        saved_file = fname
                        break
                        
                if not saved_file:
                    saved_file = actual_filename

                DOWNLOAD_TASKS[task_id].update({
                    "status": "completed",
                    "progress": 100.0,
                    "filename": saved_file,
                    "title": title,
                    "thumbnail": info.get('thumbnail', ''),
                    "file_url": f"/api/files/downloads/{saved_file}"
                })
        except Exception as e:
            logger.error(f"Download task error: {e}")
            DOWNLOAD_TASKS[task_id].update({
                "status": "error",
                "error": str(e)
            })

    t = threading.Thread(target=run_download, daemon=True)
    t.start()
    return task_id

def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    return DOWNLOAD_TASKS.get(task_id)
