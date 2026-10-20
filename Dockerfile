# ResearchAI web (Railway). Bağlam: depo kökü (researchai-mcp + researchai-web).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    RESEARCHAI_DATA=/data
WORKDIR /srv
COPY researchai-mcp/pyproject.toml researchai-mcp/README.md researchai-mcp/
COPY researchai-mcp/src researchai-mcp/src
RUN pip install ./researchai-mcp
COPY researchai-web/pyproject.toml researchai-web/
COPY researchai-web/app researchai-web/app
RUN pip install ./researchai-web
WORKDIR /srv/researchai-web
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host :: --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
