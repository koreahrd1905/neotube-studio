import os
import re
import sys
import time
import subprocess
import threading
import logging
import requests

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(BASE_DIR, 'bin')
CLOUDFLARED_EXE = os.path.join(BIN_DIR, 'cloudflared.exe')
CLOUDFLARED_DOWNLOAD_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

class CloudflareTunnelManager:
    def __init__(self, port: int = 5050):
        self.port = port
        self.process = None
        self.public_url = None
        self.is_running = False
        self.is_downloading = False
        self.download_progress = 0
        self.status = "stopped" # stopped, downloading, starting, running, error
        self.error_msg = None

    def ensure_cloudflared_binary(self, progress_callback=None) -> bool:
        """Ensures cloudflared.exe exists, downloads if missing."""
        if os.path.exists(CLOUDFLARED_EXE) and os.path.getsize(CLOUDFLARED_EXE) > 10000000:
            return True

        os.makedirs(BIN_DIR, exist_ok=True)
        self.is_downloading = True
        self.status = "downloading"
        logger.info(f"Downloading Cloudflare Tunnel engine from {CLOUDFLARED_DOWNLOAD_URL} ...")

        try:
            r = requests.get(CLOUDFLARED_DOWNLOAD_URL, stream=True, timeout=30)
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            temp_path = CLOUDFLARED_EXE + ".tmp"

            with open(temp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            self.download_progress = round(percent, 1)
                            if progress_callback:
                                progress_callback(percent)

            if os.path.exists(CLOUDFLARED_EXE):
                os.remove(CLOUDFLARED_EXE)
            os.rename(temp_path, CLOUDFLARED_EXE)
            self.is_downloading = False
            logger.info("Cloudflare Tunnel binary downloaded successfully.")
            return True
        except Exception as e:
            self.is_downloading = False
            self.status = "error"
            self.error_msg = f"Failed to download cloudflared: {e}"
            logger.error(self.error_msg)
            return False

    def start_tunnel(self, async_mode: bool = True):
        """Starts Cloudflare quick tunnel to expose the local server globally with HTTPS."""
        if self.is_running and self.public_url:
            return self.public_url

        def _run():
            self.status = "starting"
            if not self.ensure_cloudflared_binary():
                return

            cmd = [CLOUDFLARED_EXE, "tunnel", "--url", f"http://127.0.0.1:{self.port}", "--no-autoupdate"]
            logger.info(f"Starting tunnel command: {' '.join(cmd)}")

            try:
                # Use CREATE_NO_WINDOW on Windows to prevent popups
                creation_flags = 0x08000000 if sys.platform == 'win32' else 0
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    creationflags=creation_flags
                )
                self.is_running = True

                url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
                
                for line in iter(self.process.stdout.readline, ''):
                    if not line:
                        break
                    match = url_pattern.search(line)
                    if match:
                        self.public_url = match.group(0)
                        self.status = "running"
                        logger.info(f"✨ [Cloudflare Tunnel Ready] Public URL: {self.public_url}")
                        break
                        
                # Keep reading to avoid buffer overflow
                for _ in iter(self.process.stdout.readline, ''):
                    if not self.is_running:
                        break
            except Exception as e:
                self.status = "error"
                self.error_msg = str(e)
                logger.error(f"Error in Cloudflare tunnel: {e}")

        if async_mode:
            t = threading.Thread(target=_run, daemon=True)
            t.start()
        else:
            _run()

    def get_public_url(self) -> str:
        return self.public_url

    def get_status_info(self) -> dict:
        return {
            "status": self.status,
            "public_url": self.public_url,
            "is_running": self.is_running,
            "download_progress": self.download_progress,
            "error": self.error_msg
        }

    def stop_tunnel(self):
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except Exception:
                pass
            self.process = None
        self.public_url = None
        self.status = "stopped"

# Global instance
tunnel_manager = CloudflareTunnelManager(port=5050)
