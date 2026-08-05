# AI Müsahibə Platforması — çərçivəsiz Python backend (http.server) + PyMySQL
FROM python:3.12-slim

# Loglar dərhal görünsün (kubectl logs / docker logs)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Asılılıqlar koddan əvvəl — Docker layer keşi effektiv işləsin
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tətbiq kodu (.dockerignore həssas faylları kənarlaşdırır)
COPY . .

EXPOSE 5000

# Konfiqurasiya işə salınanda verilir:
#   docker:     docker run --env-file .env -p 5000:5000 <image>
#   kubernetes: Secret `/app/.env` kimi mount olunur (bax k8s/musahibe.yaml)
CMD ["python3", "app.py"]
