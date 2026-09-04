/**
 * Audio Cutter & Waveform Engine
 */
class AudioCutterEngine {
    constructor() {
        this.audioElement = new Audio();
        this.audioContext = null;
        this.audioBuffer = null;
        this.peaks = [];
        this.duration = 0;
        this.startTime = 0;
        this.endTime = 0;
        this.isPlaying = false;
        this.isSelectionPlaying = false;
        this.currentFile = null;
        this.currentFolder = 'downloads';

        this.canvas = document.getElementById('waveformCanvas');
        this.ctx = this.canvas.getContext('2d');
        this.cursorEl = document.getElementById('waveformCursor');
        this.overlayEl = document.getElementById('selectionOverlay');

        this.initEventListeners();
    }

    initEventListeners() {
        // Audio Element updates
        this.audioElement.addEventListener('timeupdate', () => this.onTimeUpdate());
        this.audioElement.addEventListener('ended', () => this.onPlaybackEnded());

        // Play/Pause button
        document.getElementById('btnWavePlayPause').addEventListener('click', () => this.togglePlay());
        document.getElementById('btnWaveStop').addEventListener('click', () => this.stopPlay());
        document.getElementById('btnPlaySelection').addEventListener('click', () => this.playSelection());

        // Step buttons
        document.querySelectorAll('.btn-step').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const target = e.target.dataset.target;
                const delta = parseFloat(e.target.dataset.delta);
                if (target === 'start') {
                    this.setStartTime(Math.max(0, Math.min(this.startTime + delta, this.endTime - 0.1)));
                } else if (target === 'end') {
                    this.setEndTime(Math.min(this.duration, Math.max(this.endTime + delta, this.startTime + 0.1)));
                }
            });
        });

        // Set to current location buttons
        document.getElementById('btnSetStartCurrent').addEventListener('click', () => {
            this.setStartTime(Math.min(this.audioElement.currentTime, this.endTime - 0.1));
        });
        document.getElementById('btnSetEndCurrent').addEventListener('click', () => {
            this.setEndTime(Math.max(this.audioElement.currentTime, this.startTime + 0.1));
        });

        // Input manual change
        document.getElementById('inputStartTime').addEventListener('change', (e) => {
            const sec = this.parseTimeStr(e.target.value);
            this.setStartTime(Math.max(0, Math.min(sec, this.endTime - 0.1)));
        });
        document.getElementById('inputEndTime').addEventListener('change', (e) => {
            const sec = this.parseTimeStr(e.target.value);
            this.setEndTime(Math.min(this.duration, Math.max(sec, this.startTime + 0.1)));
        });

        // Canvas Click & Drag for selection
        let isDragging = false;
        let dragTarget = null; // 'start', 'end', or 'seek'

        // Helper for mouse and touch position
        const getEventPos = (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const clickX = clientX - rect.left;
            const ratio = Math.max(0, Math.min(clickX / rect.width, 1));
            return { clickX, ratio, rect };
        };

        const handleDragStart = (e) => {
            if (!this.duration) return;
            const { clickX, ratio, rect } = getEventPos(e);
            const clickTime = ratio * this.duration;

            const startRatio = this.startTime / this.duration;
            const endRatio = this.endTime / this.duration;
            const startX = startRatio * rect.width;
            const endX = endRatio * rect.width;

            if (Math.abs(clickX - startX) < 25) {
                dragTarget = 'start';
            } else if (Math.abs(clickX - endX) < 25) {
                dragTarget = 'end';
            } else {
                dragTarget = 'seek';
                this.audioElement.currentTime = clickTime;
                this.updateCursor(ratio);
            }
            isDragging = true;
        };

        const handleDragMove = (e) => {
            if (!isDragging || !this.duration) return;
            if (e.cancelable) e.preventDefault();
            const { ratio } = getEventPos(e);
            const time = ratio * this.duration;

            if (dragTarget === 'start') {
                this.setStartTime(Math.max(0, Math.min(time, this.endTime - 0.1)));
            } else if (dragTarget === 'end') {
                this.setEndTime(Math.min(this.duration, Math.max(time, this.startTime + 0.1)));
            } else if (dragTarget === 'seek') {
                this.audioElement.currentTime = time;
                this.updateCursor(ratio);
            }
        };

        const handleDragEnd = () => {
            isDragging = false;
            dragTarget = null;
        };

        // Mouse Events
        this.canvas.addEventListener('mousedown', handleDragStart);
        window.addEventListener('mousemove', handleDragMove);
        window.addEventListener('mouseup', handleDragEnd);

        // Touch Events for Mobile
        this.canvas.addEventListener('touchstart', handleDragStart, { passive: false });
        window.addEventListener('touchmove', handleDragMove, { passive: false });
        window.addEventListener('touchend', handleDragEnd);

        // Fade sliders
        const fadeIn = document.getElementById('sliderFadeIn');
        const fadeOut = document.getElementById('sliderFadeOut');
        fadeIn.addEventListener('input', () => {
            document.getElementById('fadeInVal').textContent = `${fadeIn.value}초`;
        });
        fadeOut.addEventListener('input', () => {
            document.getElementById('fadeOutVal').textContent = `${fadeOut.value}초`;
        });

        // Trim Action
        document.getElementById('btnExecuteTrim').addEventListener('click', () => this.executeTrim());
    }

    async loadMedia(fileUrl, filename, folder = 'downloads', metadata = null) {
        this.currentFile = filename;
        this.currentFolder = folder;
        this.audioElement.src = fileUrl;
        this.audioElement.load();

        document.getElementById('trimmerFileName').textContent = filename;
        document.getElementById('trimmerFileMeta').textContent = '로딩 및 파형 분석 중...';
        document.getElementById('trimmerWorkspace').style.display = 'block';
        document.getElementById('trimmerFileBar').style.display = 'flex';
        document.getElementById('trimResultBox').style.display = 'none';

        // Fetch arraybuffer and decode with Web Audio API for waveform
        try {
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }

            const response = await fetch(fileUrl);
            const arrayBuffer = await response.arrayBuffer();
            this.audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
            this.duration = this.audioBuffer.duration;
            this.calculatePeaks(this.audioBuffer);
            this.drawWaveform();
        } catch (err) {
            console.warn('Web Audio decoding fallback (simulating peaks):', err);
            // Fallback duration from audio element
            this.audioElement.onloadedmetadata = () => {
                this.duration = this.audioElement.duration || 60;
                this.generateSimulatedPeaks();
                this.drawWaveform();
            };
        }

        // Initialize start and end
        this.startTime = 0;
        this.endTime = this.duration || 60;
        this.setStartTime(0);
        this.setEndTime(this.endTime);
        this.updateTimeDisplay();
        
        if (metadata && metadata.duration) {
            this.duration = metadata.duration;
            this.endTime = metadata.duration;
            this.setEndTime(this.endTime);
        }

        document.getElementById('trimmerFileMeta').textContent = 
            `길이: ${this.formatTime(this.duration)} | 전체 시간: ${this.duration.toFixed(1)}초`;
    }

    calculatePeaks(audioBuffer) {
        const channelData = audioBuffer.getChannelData(0);
        const sampleCount = 200;
        const blockSize = Math.floor(channelData.length / sampleCount);
        this.peaks = [];

        for (let i = 0; i < sampleCount; i++) {
            let max = 0;
            const start = i * blockSize;
            for (let j = 0; j < blockSize; j += 10) {
                const val = Math.abs(channelData[start + j]);
                if (val > max) max = val;
            }
            this.peaks.push(Math.min(max * 1.5, 1.0));
        }
    }

    generateSimulatedPeaks() {
        this.peaks = [];
        for (let i = 0; i < 200; i++) {
            this.peaks.push(0.2 + 0.6 * Math.abs(Math.sin(i * 0.15) * Math.cos(i * 0.05)));
        }
    }

    drawWaveform() {
        const w = this.canvas.width;
        const h = this.canvas.height;
        const ctx = this.ctx;

        ctx.clearRect(0, 0, w, h);

        const barCount = this.peaks.length || 100;
        const barWidth = (w / barCount) * 0.7;
        const gap = (w / barCount) * 0.3;

        // Gradient for waveform
        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, '#6366f1');
        grad.addColorStop(0.5, '#ec4899');
        grad.addColorStop(1, '#6366f1');

        for (let i = 0; i < barCount; i++) {
            const peak = this.peaks[i] || 0.3;
            const barHeight = Math.max(peak * (h - 20), 4);
            const x = i * (barWidth + gap);
            const y = (h - barHeight) / 2;

            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.roundRect(x, y, barWidth, barHeight, 2);
            ctx.fill();
        }

        this.updateOverlay();
    }

    setStartTime(sec) {
        this.startTime = Math.max(0, parseFloat(sec));
        document.getElementById('inputStartTime').value = this.formatTime(this.startTime);
        this.updateTimeDisplay();
        this.updateOverlay();
    }

    setEndTime(sec) {
        this.endTime = Math.min(this.duration || 999999, parseFloat(sec));
        document.getElementById('inputEndTime').value = this.formatTime(this.endTime);
        this.updateTimeDisplay();
        this.updateOverlay();
    }

    updateTimeDisplay() {
        const dur = Math.max(0, this.endTime - this.startTime);
        document.getElementById('selectedDurationText').textContent = `${dur.toFixed(2)} 초`;
        document.getElementById('selectedRangeBadge').textContent = 
            `${this.formatTime(this.startTime)} ~ ${this.formatTime(this.endTime)}`;
    }

    updateOverlay() {
        if (!this.duration) return;
        const startPercent = (this.startTime / this.duration) * 100;
        const endPercent = (this.endTime / this.duration) * 100;
        const widthPercent = Math.max(0, endPercent - startPercent);

        this.overlayEl.style.left = `${startPercent}%`;
        this.overlayEl.style.width = `${widthPercent}%`;
    }

    updateCursor(ratio) {
        this.cursorEl.style.left = `${ratio * 100}%`;
    }

    onTimeUpdate() {
        const cur = this.audioElement.currentTime;
        const ratio = this.duration > 0 ? cur / this.duration : 0;
        this.updateCursor(ratio);

        document.getElementById('trimmerCurrentTime').textContent = this.formatTime(cur);
        document.getElementById('trimmerTotalDuration').textContent = this.formatTime(this.duration);

        if (this.isSelectionPlaying && cur >= this.endTime) {
            this.audioElement.currentTime = this.startTime;
        }
    }

    onPlaybackEnded() {
        this.isPlaying = false;
        this.isSelectionPlaying = false;
        document.getElementById('wavePlayIcon').className = 'fa-solid fa-play';
    }

    togglePlay() {
        if (this.isPlaying) {
            this.audioElement.pause();
            this.isPlaying = false;
            document.getElementById('wavePlayIcon').className = 'fa-solid fa-play';
        } else {
            this.audioElement.play();
            this.isPlaying = true;
            this.isSelectionPlaying = false;
            document.getElementById('wavePlayIcon').className = 'fa-solid fa-pause';
        }
    }

    stopPlay() {
        this.audioElement.pause();
        this.audioElement.currentTime = this.startTime;
        this.isPlaying = false;
        this.isSelectionPlaying = false;
        document.getElementById('wavePlayIcon').className = 'fa-solid fa-play';
    }

    playSelection() {
        this.audioElement.currentTime = this.startTime;
        this.audioElement.play();
        this.isPlaying = true;
        this.isSelectionPlaying = true;
        document.getElementById('wavePlayIcon').className = 'fa-solid fa-pause';
    }

    formatTime(sec) {
        if (isNaN(sec)) return "00:00.00";
        const m = Math.floor(sec / 60);
        const s = (sec % 60).toFixed(2);
        return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
    }

    parseTimeStr(str) {
        if (!str) return 0;
        const parts = str.split(':');
        if (parts.length === 1) return parseFloat(parts[0]) || 0;
        if (parts.length === 2) return (parseFloat(parts[0]) || 0) * 60 + (parseFloat(parts[1]) || 0);
        if (parts.length === 3) return (parseFloat(parts[0]) || 0) * 3600 + (parseFloat(parts[1]) || 0) * 60 + (parseFloat(parts[2]) || 0);
        return 0;
    }

    async executeTrim() {
        if (!this.currentFile) {
            window.showToast('편집할 파일을 먼저 선택해주세요.', 'error');
            return;
        }

        const outFormat = document.getElementById('trimOutputFormat').value;
        const fadeIn = parseFloat(document.getElementById('sliderFadeIn').value);
        const fadeOut = parseFloat(document.getElementById('sliderFadeOut').value);

        const btn = document.getElementById('btnExecuteTrim');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 오디오 자르는 중...';

        try {
            const resp = await fetch('/api/audio/trim', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: this.currentFile,
                    folder: this.currentFolder,
                    start_time: this.startTime,
                    end_time: this.endTime,
                    output_format: outFormat,
                    fade_in: fadeIn,
                    fade_out: fadeOut
                })
            });

            const data = await resp.json();
            if (data.success) {
                window.showToast('오디오 구간 자르기가 완료되었습니다!', 'success');
                const resultBox = document.getElementById('trimResultBox');
                resultBox.style.display = 'block';
                document.getElementById('trimmedResultFileName').textContent = data.output_filename;

                const player = document.getElementById('trimmedAudioPlayer');
                player.src = data.file_url;

                const downloadBtn = document.getElementById('btnDownloadTrimmed');
                downloadBtn.href = `${data.file_url}?download=1`;
                downloadBtn.setAttribute('download', data.output_filename);

                // Set send to converter button
                document.getElementById('btnSendTrimmedToConverter').onclick = () => {
                    window.appInstance.sendToConverter(data.output_filename, 'trimmed');
                };

                window.appInstance.fetchHistory();
                resultBox.scrollIntoView({ behavior: 'smooth' });
            } else {
                window.showToast(data.error || '자르기 작업 중 오류가 발생했습니다.', 'error');
            }
        } catch (err) {
            window.showToast(`서버 요청 실패: ${err.message}`, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-scissors"></i> 선택 구간 자르기 및 추출';
        }
    }
}
