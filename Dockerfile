FROM python:3.14-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Salin file proyek, lalu sinkronkan dependensi
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

# Render mengirim PORT lewat env; hormati nilai itu (default 8000 untuk lokal).
CMD ["sh", "-c", "exec uvicorn klinik_famitra_app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
