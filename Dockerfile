# lightweight python base (not playwright image — we install manually)
FROM python:3.11-slim

# install system deps that chromium needs
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcb1 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxshmfence1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy and install python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# force playwright to install browsers HERE (not in some random cache)
ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright
RUN playwright install chromium

# copy project files
COPY backend/ ./backend/
COPY frontend/ ./frontend/

EXPOSE 8000

# keep the env var set at runtime too
ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright

# run from backend dir so ../frontend resolves
CMD ["sh", "-c", "cd backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]