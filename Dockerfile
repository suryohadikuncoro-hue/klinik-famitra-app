# Image untuk Hugging Face Spaces (Docker SDK).
# Space berjalan sebagai user non-root UID 1000 dan mengekspos SATU port: app_port 7860.
FROM python:3.14-slim

RUN useradd -m -u 1000 user

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /home/user/app

# Salin file proyek, lalu sinkronkan dependensi
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev && chown -R user:user /home/user/app

ENV PATH="/home/user/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    HOME=/home/user

USER user

EXPOSE 7860

CMD ["sh", "-c", "exec uvicorn klinik_famitra_app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
