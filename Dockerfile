FROM python:3.11-slim

# Install ffmpeg and system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy project files
COPY . .

# Generate PWA icons if missing
RUN python generate_icons.py

ENV PORT=5050
EXPOSE 5050

# Run with Gunicorn WSGI server (1 worker, 8 threads for shared background task memory)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5050} --workers 1 --threads 8 --timeout 300 app:app"]
