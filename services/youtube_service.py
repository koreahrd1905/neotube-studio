import os
import re
import json
import uuid
import threading
import logging
import requests
from typing import Dict, Any, Optional
import yt_dlp

logger = logging.getLogger(__name__)

# Global dictionary to hold background download progress in memory
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
    
    # Extract URL if surrounded by extra text
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
                "duration_formatted": "확인 완료",
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
        logger.error(f"Error in get_video_info: {e}")
        return {
            "success": False,
            "error": f"영상 정보를 불러올 수 없습니다: {str(e)}"
        }

def save_task_to_file(output_dir: str, task_id: str, data: dict):
    """Saves task status to disk for cross-worker multi-process synchronization."""
    DOWNLOAD_TASKS.setdefault(task_id, {}).update(data)
    try:
        tasks_dir = os.path.join(output_dir, '.tasks')
        os.makedirs(tasks_dir, exist_ok=True)
        fpath = os.path.join(tasks_dir, f"{task_id}.json")
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(DOWNLOAD_TASKS[task_id], f)
    except Exception as e:
        pass

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
    initial_data = {
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
    save_task_to_file(output_dir, task_id, initial_data)

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

            save_task_to_file(output_dir, task_id, {
                "status": "downloading",
                "progress": round(percent, 1),
                "speed": speed_str,
                "eta": eta_str,
                "total_bytes": total,
                "downloaded_bytes": downloaded,
            })
        elif d['status'] == 'finished':
            save_task_to_file(output_dir, task_id, {
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
            'socket_timeout': 30,
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
            # MP4 Video download (supports both regular and vertical shorts)
            if quality and quality != 'best' and quality.endswith('p'):
                res_num = quality.replace('p', '')
                format_spec = f'bestvideo[height<={res_num}]+bestaudio/bestvideo[width<={res_num}]+bestaudio/bestvideo+bestaudio/best'
            else:
                format_spec = 'bestvideo+bestaudio/best'

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
                sanitized_pattern = info.get('id', '')
                saved_file = None
                for fname in os.listdir(output_dir):
                    if sanitized_pattern in fname and fname.endswith(f".{ext}"):
                        saved_file = fname
                        break
                        
                if not saved_file:
                    saved_file = actual_filename

                save_task_to_file(output_dir, task_id, {
                    "status": "completed",
                    "progress": 100.0,
                    "filename": saved_file,
                    "title": title,
                    "thumbnail": info.get('thumbnail', ''),
                    "file_url": f"/api/files/downloads/{saved_file}"
                })
        except Exception as e:
            logger.error(f"Download task error: {e}")
            save_task_to_file(output_dir, task_id, {
                "status": "failed",
                "error": str(e)
            })

    t = threading.Thread(target=run_download, daemon=True)
    t.start()
    return task_id

def get_task_status(task_id: str, output_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    # Check in memory first
    if task_id in DOWNLOAD_TASKS and DOWNLOAD_TASKS[task_id].get("status") in ["downloading", "processing", "completed", "failed"]:
        return DOWNLOAD_TASKS[task_id]
        
    # Check file cache for multi-worker synchronization
    if not output_dir:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(base_dir, 'downloads')
        
    fpath = os.path.join(output_dir, '.tasks', f"{task_id}.json")
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                DOWNLOAD_TASKS[task_id] = data
                return data
        except Exception:
            pass
            
    return DOWNLOAD_TASKS.get(task_id)
