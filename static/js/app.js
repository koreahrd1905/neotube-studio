/**
 * Media Studio Main Frontend Application
 */

// Toast notification helper
window.showToast = function(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-circle-check';
    if (type === 'error') icon = 'fa-triangle-exclamation';

    toast.innerHTML = `<i class="fa-solid ${icon}"></i><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
};

class MediaStudioApp {
    constructor() {
        this.currentDownloadTaskId = null;
        this.pollInterval = null;
        this.selectedFormat = 'mp3';
        this.currentVideoResolutions = [];

        // Trimmer Engine instance
        this.audioCutter = new AudioCutterEngine();

        // Converter state
        this.converterCurrentFile = null;
        this.converterCurrentFolder = 'downloads';
        this.converterTargetFormat = 'wmv';

        // PWA & Mobile Connect state
        this.deferredPrompt = null;
        this.initPWA();
        this.initMobileConnect();
        this.initTabs();
        this.initDownloader();
        this.initUploaders();
        this.initConverter();
        this.initHistory();
        this.fetchHistory();
    }

    // PWA Service Worker & Install Prompt
    initPWA() {
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js')
                .then(reg => console.log('PWA ServiceWorker registered with scope:', reg.scope))
                .catch(err => console.log('PWA ServiceWorker registration failed:', err));
        }

        const banner = document.getElementById('pwaInstallBanner');
        const btnInstall = document.getElementById('btnPwaInstall');
        const btnClose = document.getElementById('btnClosePwaBanner');

        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            if (banner) banner.style.display = 'flex';
        });

        if (btnInstall) {
            btnInstall.addEventListener('click', async () => {
                if (this.deferredPrompt) {
                    this.deferredPrompt.prompt();
                    const choice = await this.deferredPrompt.userChoice;
                    if (choice.outcome === 'accepted') {
                        window.showToast('앱 설치가 진행됩니다!', 'success');
                    }
                    this.deferredPrompt = null;
                    if (banner) banner.style.display = 'none';
                } else {
                    // Fallback to mobile connect modal
                    document.getElementById('btnOpenMobileConnect').click();
                }
            });
        }

        if (btnClose) {
            btnClose.addEventListener('click', () => {
                if (banner) banner.style.display = 'none';
            });
        }
    }

    // Mobile Connect & QR Code Modal
    initMobileConnect() {
        const btnOpen = document.getElementById('btnOpenMobileConnect');
        const btnClose = document.getElementById('btnCloseMobile');
        const modal = document.getElementById('mobileModal');
        const qrImg = document.getElementById('mobileQrImg');
        const qrSpinner = document.getElementById('qrLoadingSpinner');
        const urlInput = document.getElementById('mobileUrlText');
        const urlLabel = document.getElementById('mobileUrlLabel');
        const networkTag = document.getElementById('networkTag');
        const btnCopy = document.getElementById('btnCopyMobileUrl');
        const btnModeGlobal = document.getElementById('btnModeGlobal');
        const btnModeLocal = document.getElementById('btnModeLocal');
        const btnModeTermux = document.getElementById('btnModeTermux');
        const standardQrSection = document.getElementById('standardQrSection');
        const termuxGuideSection = document.getElementById('termuxGuideSection');

        let mobileData = null;
        let currentMode = 'global'; // 'global', 'local', or 'termux'

        const updateModalUI = () => {
            btnModeGlobal.classList.remove('active');
            btnModeLocal.classList.remove('active');
            if (btnModeTermux) btnModeTermux.classList.remove('active');

            if (currentMode === 'termux') {
                if (btnModeTermux) btnModeTermux.classList.add('active');
                if (standardQrSection) standardQrSection.style.display = 'none';
                if (termuxGuideSection) termuxGuideSection.style.display = 'block';
                return;
            }

            if (standardQrSection) standardQrSection.style.display = 'flex';
            if (termuxGuideSection) termuxGuideSection.style.display = 'none';

            if (!mobileData) return;

            if (currentMode === 'global') {
                btnModeGlobal.classList.add('active');
                urlLabel.textContent = '🌐 외부 어디서나 접속 주소 (HTTPS):';
                networkTag.textContent = 'LTE/5G/외부 가능';
                networkTag.style.background = 'rgba(236, 72, 153, 0.2)';
                networkTag.style.color = 'var(--secondary)';

                if (mobileData.global_url && mobileData.global_qr) {
                    qrImg.src = mobileData.global_qr;
                    qrImg.style.display = 'block';
                    qrSpinner.style.display = 'none';
                    urlInput.value = mobileData.global_url;
                } else {
                    qrImg.style.display = 'none';
                    qrSpinner.style.display = 'block';
                    urlInput.value = 'Cloudflare 글로벌 보안 터널 생성 중...';
                    setTimeout(fetchMobileInfo, 2000);
                }
            } else if (currentMode === 'local') {
                btnModeLocal.classList.add('active');
                urlLabel.textContent = '🏠 같은 Wi-Fi 공유기 접속 주소:';
                networkTag.textContent = '로컬 Wi-Fi';
                networkTag.style.background = 'rgba(6, 182, 212, 0.2)';
                networkTag.style.color = 'var(--accent)';

                qrImg.src = mobileData.local_qr;
                qrImg.style.display = 'block';
                qrSpinner.style.display = 'none';
                urlInput.value = mobileData.local_url;
            }
        };

        const termuxApkQrImg = document.getElementById('termuxApkQrImg');
        const zipDownloadQrImg = document.getElementById('zipDownloadQrImg');
        const btnDirectZip = document.getElementById('btnDirectZipDownload');
        const btnCopyTermuxCmd = document.getElementById('btnCopyTermuxCmd');
        const termuxCmdText = document.getElementById('termuxCmdText');

        const fetchMobileInfo = async () => {
            try {
                const resp = await fetch('/api/mobile-info');
                const data = await resp.json();
                if (data.success) {
                    mobileData = data;
                    if (termuxApkQrImg && data.termux_apk_qr) {
                        termuxApkQrImg.src = data.termux_apk_qr;
                    }
                    if (zipDownloadQrImg && data.zip_download_qr) {
                        zipDownloadQrImg.src = data.zip_download_qr;
                    }
                    if (btnDirectZip && data.zip_download_url) {
                        btnDirectZip.href = data.zip_download_url;
                    }
                    updateModalUI();
                }
            } catch (err) {
                console.error('Failed to load mobile info:', err);
            }
        };

        if (btnOpen) {
            btnOpen.addEventListener('click', () => {
                modal.style.display = 'flex';
                fetchMobileInfo();
            });
        }

        btnModeGlobal.addEventListener('click', () => {
            currentMode = 'global';
            updateModalUI();
        });

        btnModeLocal.addEventListener('click', () => {
            currentMode = 'local';
            updateModalUI();
        });

        if (btnModeTermux) {
            btnModeTermux.addEventListener('click', () => {
                currentMode = 'termux';
                updateModalUI();
            });
        }

        if (btnCopyTermuxCmd && termuxCmdText) {
            btnCopyTermuxCmd.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(termuxCmdText.textContent);
                    window.showToast('Termux 설치 명령어가 복사되었습니다!', 'success');
                } catch (e) {
                    window.showToast('명령어를 복사했습니다.', 'success');
                }
            });
        }

        btnCloseModal(btnClose, modal);

        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.style.display = 'none';
        });

        if (btnCopy) {
            btnCopy.addEventListener('click', async () => {
                if (urlInput.value && !urlInput.value.includes('생성 중')) {
                    try {
                        await navigator.clipboard.writeText(urlInput.value);
                        window.showToast('휴대폰 접속 주소가 복사되었습니다!', 'success');
                    } catch (e) {
                        urlInput.select();
                        document.execCommand('copy');
                        window.showToast('휴대폰 접속 주소가 복사되었습니다!', 'success');
                    }
                }
            });
        }
    }

    // Tab Navigation
    initTabs() {
        const tabBtns = document.querySelectorAll('.tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const target = btn.dataset.tab;
                this.switchTab(target);
            });
        });
    }

    switchTab(tabId) {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        const targetBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
        const targetContent = document.getElementById(tabId);

        if (targetBtn && targetContent) {
            targetBtn.classList.add('active');
            targetContent.classList.add('active');
        }
    }

    // 1. YouTube Downloader Module
    initDownloader() {
        const urlInput = document.getElementById('ytUrlInput');
        const btnFetch = document.getElementById('btnFetchInfo');
        const btnClear = document.getElementById('btnClearUrl');
        const btnPaste = document.getElementById('btnPasteUrl');
        const btnStartDownload = document.getElementById('btnStartDownload');

        // URL input actions
        btnClear.addEventListener('click', () => {
            urlInput.value = '';
            urlInput.focus();
        });

        btnPaste.addEventListener('click', async () => {
            try {
                const text = await navigator.clipboard.readText();
                urlInput.value = text;
                this.fetchVideoInfo(text);
            } catch (e) {
                window.showToast('클립보드 권한이 필요합니다.', 'error');
            }
        });

        btnFetch.addEventListener('click', () => {
            const url = urlInput.value.trim();
            if (!url) {
                window.showToast('유튜브 URL을 입력해주세요.', 'error');
                return;
            }
            this.fetchVideoInfo(url);
        });

        urlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                btnFetch.click();
            }
        });

        // Format Toggle (MP3 vs MP4)
        document.querySelectorAll('.format-toggle .toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.format-toggle .toggle-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.selectedFormat = btn.dataset.format;
                this.updateQualityOptions();
            });
        });

        // Start Download Button
        btnStartDownload.addEventListener('click', () => this.startDownload());
    }

    async fetchVideoInfo(url) {
        const btnFetch = document.getElementById('btnFetchInfo');
        btnFetch.disabled = true;
        btnFetch.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 분석 중...';

        try {
            const resp = await fetch('/api/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            const data = await resp.json();

            if (data.success) {
                document.getElementById('videoPreviewCard').style.display = 'block';
                document.getElementById('videoThumb').src = data.thumbnail || '';
                document.getElementById('videoDuration').textContent = data.duration_formatted || '00:00';
                document.getElementById('videoTitle').textContent = data.title;
                document.getElementById('videoUploader').innerHTML = 
                    `<i class="fa-solid fa-user-check"></i> ${data.uploader}`;

                this.currentVideoResolutions = data.resolutions || [];
                this.updateQualityOptions();

                document.getElementById('downloadCompleteCard').style.display = 'none';
                document.getElementById('downloadProgressContainer').style.display = 'none';
                window.showToast('영상 정보를 성공적으로 불러왔습니다!', 'success');
            } else {
                window.showToast(data.error || '영상 정보를 불러오지 못했습니다.', 'error');
            }
        } catch (err) {
            window.showToast(`네트워크 오류: ${err.message}`, 'error');
        } finally {
            btnFetch.disabled = false;
            btnFetch.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> 정보 조회';
        }
    }

    updateQualityOptions() {
        const select = document.getElementById('downloadQualitySelect');
        select.innerHTML = '';

        if (this.selectedFormat === 'mp3') {
            select.innerHTML = `
                <option value="320k">최고음질 (320 kbps MP3 - 권장)</option>
                <option value="192k">표준음질 (192 kbps MP3)</option>
                <option value="128k">일반음질 (128 kbps MP3)</option>
            `;
        } else {
            // MP4 options
            select.innerHTML = `<option value="best">최고화질 (Best Available MP4)</option>`;
            if (this.currentVideoResolutions && this.currentVideoResolutions.length > 0) {
                this.currentVideoResolutions.forEach(res => {
                    const opt = document.createElement('option');
                    opt.value = res;
                    opt.textContent = `${res} 고화질 MP4`;
                    select.appendChild(opt);
                });
            } else {
                select.innerHTML += `
                    <option value="1080p">1080p FHD MP4</option>
                    <option value="720p">720p HD MP4</option>
                    <option value="480p">480p SD MP4</option>
                `;
            }
        }
    }

    async startDownload() {
        const url = document.getElementById('ytUrlInput').value.trim();
        const quality = document.getElementById('downloadQualitySelect').value;

        if (!url) {
            window.showToast('유튜브 URL을 입력해주세요.', 'error');
            return;
        }

        const btn = document.getElementById('btnStartDownload');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 작업 요청 중...';

        try {
            const resp = await fetch('/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: url,
                    format_type: this.selectedFormat,
                    quality: quality
                })
            });

            const data = await resp.json();
            if (data.success) {
                this.currentDownloadTaskId = data.task_id;
                document.getElementById('downloadProgressContainer').style.display = 'block';
                document.getElementById('downloadCompleteCard').style.display = 'none';
                this.startProgressPolling();
            } else {
                window.showToast(data.error || '다운로드 요청 실패', 'error');
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> 지금 다운로드 시작';
            }
        } catch (err) {
            window.showToast(`다운로드 오류: ${err.message}`, 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i> 지금 다운로드 시작';
        }
    }

    startProgressPolling() {
        if (this.pollInterval) clearInterval(this.pollInterval);

        this.pollInterval = setInterval(async () => {
            if (!this.currentDownloadTaskId) {
                clearInterval(this.pollInterval);
                return;
            }

            try {
                const resp = await fetch(`/api/download/status/${this.currentDownloadTaskId}`);
                const data = await resp.json();

                if (!data.success || !data.task) return;

                const task = data.task;
                const progressFill = document.getElementById('downloadProgressFill');
                const progressPercent = document.getElementById('downloadPercent');
                const statusText = document.getElementById('downloadStatusText');
                const speedText = document.getElementById('downloadSpeed');
                const etaText = document.getElementById('downloadEta');

                progressFill.style.width = `${task.progress}%`;
                progressPercent.textContent = `${task.progress}%`;

                if (task.status === 'downloading') {
                    statusText.innerHTML = `<i class="fa-solid fa-arrow-down"></i> 다운로드 중...`;
                    speedText.innerHTML = `<i class="fa-solid fa-gauge-high"></i> 속도: ${task.speed}`;
                    etaText.innerHTML = `<i class="fa-solid fa-hourglass-half"></i> 남은 시간: ${task.eta}`;
                } else if (task.status === 'processing') {
                    statusText.innerHTML = `<i class="fa-solid fa-gear fa-spin"></i> 고음질 인코딩 및 변환 중...`;
                    speedText.innerHTML = `<i class="fa-solid fa-gauge-high"></i> FFmpeg 처리 중`;
                    etaText.innerHTML = `<i class="fa-solid fa-hourglass-half"></i> 마무리 단계`;
                } else if (task.status === 'completed') {
                    clearInterval(this.pollInterval);
                    this.onDownloadComplete(task);
                } else if (task.status === 'failed') {
                    clearInterval(this.pollInterval);
                    window.showToast(`다운로드 실패: ${task.error || '오류 발생'}`, 'error');
                    statusText.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> 실패`;
                    document.getElementById('btnStartDownload').disabled = false;
                    document.getElementById('btnStartDownload').innerHTML = 
                        '<i class="fa-solid fa-cloud-arrow-down"></i> 지금 다운로드 시작';
                }
            } catch (err) {
                console.error('Polling error:', err);
            }
        }, 1000);
    }

    onDownloadComplete(task) {
        document.getElementById('btnStartDownload').disabled = false;
        document.getElementById('btnStartDownload').innerHTML = 
            '<i class="fa-solid fa-cloud-arrow-down"></i> 지금 다운로드 시작';

        window.showToast('🎉 다운로드 및 변환이 완료되었습니다!', 'success');

        const completeCard = document.getElementById('downloadCompleteCard');
        completeCard.style.display = 'block';
        document.getElementById('completedFileName').textContent = task.filename;

        // Render player
        const playerBox = document.getElementById('completedPlayerBox');
        if (task.format_type === 'mp3') {
            playerBox.innerHTML = `
                <audio controls autoplay style="width: 100%;">
                    <source src="${task.file_url}" type="audio/mp3">
                </audio>
            `;
        } else {
            playerBox.innerHTML = `
                <video controls autoplay style="width: 100%; max-height: 380px; border-radius: 12px; background: #000;">
                    <source src="${task.file_url}" type="video/mp4">
                </video>
            `;
        }

        // Direct download link
        const directBtn = document.getElementById('btnDirectDownload');
        directBtn.href = `${task.file_url}?download=1`;
        directBtn.setAttribute('download', task.filename);

        // Send to Trimmer Action
        document.getElementById('btnSendToTrimmer').onclick = () => {
            this.sendToTrimmer(task.filename, 'downloads');
        };

        // Send to Converter Action
        document.getElementById('btnSendToConverter').onclick = () => {
            this.sendToConverter(task.filename, 'downloads');
        };

        this.fetchHistory();
        completeCard.scrollIntoView({ behavior: 'smooth' });
    }

    // 2. Drag & Drop and Uploaders
    initUploaders() {
        // Trimmer Dropzone
        const trimmerDropzone = document.getElementById('trimmerDropzone');
        const trimmerInput = document.getElementById('trimmerFileInput');

        this.setupDropzone(trimmerDropzone, trimmerInput, (file) => {
            this.uploadFile(file, (data) => {
                this.audioCutter.loadMedia(data.file_url, data.filename, 'uploads', data.info);
                this.fetchHistory();
            });
        });

        document.getElementById('btnChangeTrimmerFile').addEventListener('click', () => {
            trimmerInput.click();
        });

        // Converter Dropzone
        const converterDropzone = document.getElementById('converterDropzone');
        const converterInput = document.getElementById('converterFileInput');

        this.setupDropzone(converterDropzone, converterInput, (file) => {
            this.uploadFile(file, (data) => {
                this.loadConverterMedia(data.filename, 'uploads', data.info);
                this.fetchHistory();
            });
        });

        document.getElementById('btnChangeConverterFile').addEventListener('click', () => {
            converterInput.click();
        });
    }

    setupDropzone(zone, input, onFileReady) {
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                onFileReady(e.dataTransfer.files[0]);
            }
        });
        input.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                onFileReady(e.target.files[0]);
            }
        });
    }

    async uploadFile(file, callback) {
        const formData = new FormData();
        formData.append('file', file);

        window.showToast(`'${file.name}' 업로드 중...`, 'info');

        try {
            const resp = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await resp.json();

            if (data.success) {
                window.showToast('파일 업로드가 완료되었습니다.', 'success');
                if (callback) callback(data);
            } else {
                window.showToast(data.error || '업로드 실패', 'error');
            }
        } catch (err) {
            window.showToast(`업로드 에러: ${err.message}`, 'error');
        }
    }

    // 3. Video Converter Module
    initConverter() {
        // Target format button group
        document.querySelectorAll('#targetFormatBtnGroup .format-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#targetFormatBtnGroup .format-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.converterTargetFormat = btn.dataset.target;
            });
        });

        document.getElementById('btnExecuteConvert').addEventListener('click', () => this.executeConvert());
    }

    loadConverterMedia(filename, folder = 'downloads', info = null) {
        this.converterCurrentFile = filename;
        this.converterCurrentFolder = folder;

        const ext = filename.split('.').pop().toUpperCase();
        document.getElementById('sourceFormatBadge').textContent = ext;
        document.getElementById('converterFileName').textContent = filename;
        
        let metaStr = `포맷: ${ext}`;
        if (info) {
            if (info.video && info.video.width) {
                metaStr += ` | 해상도: ${info.video.width}x${info.video.height}`;
            }
            if (info.duration_formatted) {
                metaStr += ` | 길이: ${info.duration_formatted}`;
            }
            if (info.size_formatted) {
                metaStr += ` | 용량: ${info.size_formatted}`;
            }
        }

        document.getElementById('converterFileMeta').textContent = metaStr;
        document.getElementById('converterFileBar').style.display = 'flex';
        document.getElementById('converterWorkspace').style.display = 'block';
        document.getElementById('convertResultBox').style.display = 'none';

        // Set default recommended target format
        const targetBtns = document.querySelectorAll('#targetFormatBtnGroup .format-btn');
        targetBtns.forEach(b => b.classList.remove('active'));

        if (ext === 'MP4') {
            const wmvBtn = document.querySelector('#targetFormatBtnGroup .format-btn[data-target="wmv"]');
            if (wmvBtn) {
                wmvBtn.classList.add('active');
                this.converterTargetFormat = 'wmv';
            }
        } else if (ext === 'WMV' || ext === 'AVI') {
            const mp4Btn = document.querySelector('#targetFormatBtnGroup .format-btn[data-target="mp4"]');
            if (mp4Btn) {
                mp4Btn.classList.add('active');
                this.converterTargetFormat = 'mp4';
            }
        } else {
            targetBtns[0].classList.add('active');
            this.converterTargetFormat = targetBtns[0].dataset.target;
        }
    }

    async executeConvert() {
        if (!this.converterCurrentFile) {
            window.showToast('변환할 동영상 파일을 먼저 선택해주세요.', 'error');
            return;
        }

        const resolution = document.getElementById('converterResolutionSelect').value;
        const quality = document.getElementById('converterQualitySelect').value;
        const btn = document.getElementById('btnExecuteConvert');
        const progressBox = document.getElementById('convertProgressBox');
        const resultBox = document.getElementById('convertResultBox');

        btn.disabled = true;
        progressBox.style.display = 'block';
        resultBox.style.display = 'none';

        try {
            const resp = await fetch('/api/video/convert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: this.converterCurrentFile,
                    folder: this.converterCurrentFolder,
                    target_format: this.converterTargetFormat,
                    resolution: resolution,
                    quality: quality
                })
            });

            const data = await resp.json();
            if (data.success) {
                window.showToast('동영상 포맷 변환이 완료되었습니다!', 'success');
                progressBox.style.display = 'none';
                resultBox.style.display = 'block';

                document.getElementById('convertedResultFileName').textContent = data.output_filename;
                document.getElementById('convertedResultSize').textContent = 
                    `용량: ${data.info.size_formatted || '-- MB'}`;

                // Preview player
                const previewBox = document.getElementById('convertedVideoPreviewBox');
                const isAudio = data.target_format === 'mp3';
                if (isAudio) {
                    previewBox.innerHTML = `
                        <audio controls autoplay style="width: 100%;">
                            <source src="${data.file_url}" type="audio/mp3">
                        </audio>
                    `;
                } else {
                    previewBox.innerHTML = `
                        <video controls autoplay style="width: 100%; max-height: 400px; border-radius: 12px; background: #000;">
                            <source src="${data.file_url}">
                        </video>
                    `;
                }

                // Download Link
                const downloadBtn = document.getElementById('btnDownloadConverted');
                downloadBtn.href = `${data.file_url}?download=1`;
                downloadBtn.setAttribute('download', data.output_filename);

                // Send converted to trimmer
                document.getElementById('btnSendConvertedToTrimmer').onclick = () => {
                    this.sendToTrimmer(data.output_filename, 'converted');
                };

                this.fetchHistory();
                resultBox.scrollIntoView({ behavior: 'smooth' });
            } else {
                progressBox.style.display = 'none';
                window.showToast(data.error || '변환 중 오류가 발생했습니다.', 'error');
            }
        } catch (err) {
            progressBox.style.display = 'none';
            window.showToast(`변환 실패: ${err.message}`, 'error');
        } finally {
            btn.disabled = false;
        }
    }

    // Cross Module Workflow Navigation
    sendToTrimmer(filename, folder) {
        this.switchTab('tab-trimmer');
        const fileUrl = `/api/files/${folder}/${filename}`;
        this.audioCutter.loadMedia(fileUrl, filename, folder);
        window.showToast(`'${filename}' 파일을 오디오 편집기로 불러왔습니다.`, 'info');
    }

    sendToConverter(filename, folder) {
        this.switchTab('tab-converter');
        fetch('/api/media/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename, folder })
        })
        .then(r => r.json())
        .then(data => {
            this.loadConverterMedia(filename, folder, data.info);
            window.showToast(`'${filename}' 파일을 동영상 변환기로 불러왔습니다.`, 'info');
        });
    }

    // 4. History Storage Modal
    initHistory() {
        const btnOpen = document.getElementById('btnOpenHistory');
        const btnClose = document.getElementById('btnCloseHistory');
        const modal = document.getElementById('historyModal');

        btnOpen.addEventListener('click', () => {
            this.fetchHistory();
            modal.style.display = 'flex';
        });
        btnCloseModal(btnClose, modal);

        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.style.display = 'none';
        });
    }

    async fetchHistory() {
        try {
            const resp = await fetch('/api/history');
            const data = await resp.json();

            if (!data.success) return;

            const files = data.files || [];
            document.getElementById('historyCountBadge').textContent = files.length;

            const list = document.getElementById('historyListContainer');
            if (files.length === 0) {
                list.innerHTML = `<p style="text-align: center; color: var(--text-dim); padding: 30px;">저장된 작업 내역이 없습니다.</p>`;
                return;
            }

            list.innerHTML = files.map(f => {
                const badgeClass = `badge-${f.folder}`;
                return `
                    <div class="history-item">
                        <div class="history-meta-left">
                            <span class="history-type-badge ${badgeClass}">${f.category}</span>
                            <div style="min-width: 0;">
                                <div class="history-name" title="${f.filename}">${f.filename}</div>
                                <div class="history-sub">${f.size_formatted} &bull; ${f.created_at}</div>
                            </div>
                        </div>
                        <div class="history-actions">
                            <a href="${f.file_url}?download=1" download="${f.filename}" class="btn-icon" title="다운로드">
                                <i class="fa-solid fa-download"></i>
                            </a>
                            <button class="btn-icon" title="오디오 자르기로 보내기" onclick="window.appInstance.sendToTrimmer('${f.filename}', '${f.folder}')">
                                <i class="fa-solid fa-scissors"></i>
                            </button>
                            <button class="btn-icon" title="포맷 변환기로 보내기" onclick="window.appInstance.sendToConverter('${f.filename}', '${f.folder}')">
                                <i class="fa-solid fa-arrows-rotate"></i>
                            </button>
                            <button class="btn-icon" title="삭제" onclick="window.appInstance.deleteFile('${f.filename}', '${f.folder}')">
                                <i class="fa-regular fa-trash-can" style="color: var(--danger);"></i>
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (err) {
            console.error('Failed to fetch history:', err);
        }
    }

    async deleteFile(filename, folder) {
        if (!confirm(`'${filename}' 파일을 삭제하시겠습니까?`)) return;

        try {
            const resp = await fetch('/api/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename, folder })
            });
            const data = await resp.json();
            if (data.success) {
                window.showToast('파일이 삭제되었습니다.', 'info');
                this.fetchHistory();
            } else {
                window.showToast(data.error || '삭제 실패', 'error');
            }
        } catch (err) {
            window.showToast(`삭제 에러: ${err.message}`, 'error');
        }
    }
}

function btnCloseModal(btn, modal) {
    btn.addEventListener('click', () => modal.style.display = 'none');
}

// Global initialization
window.addEventListener('DOMContentLoaded', () => {
    window.appInstance = new MediaStudioApp();
});
