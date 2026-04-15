FROM python:3.11-slim

WORKDIR /app

# install python deps first (cached layer)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# install chromium + all its system dependencies (runs as root in Docker = no permission issues)
ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers
RUN playwright install --with-deps chromium

# copy project
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# keep browser path set at runtime
ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers

EXPOSE 8000

CMD ["sh", "-c", "cd backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]