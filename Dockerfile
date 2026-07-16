FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .
RUN pip install --upgrade pip && pip install --no-cache-dir .

RUN useradd --create-home --shell /usr/sbin/nologin mcp

COPY --chown=mcp:mcp server.py .
COPY --chown=mcp:mcp tools/ tools/
COPY --chown=mcp:mcp knowledge/ knowledge/
COPY --chown=mcp:mcp scripts/ scripts/

USER mcp

EXPOSE 8000

CMD ["python", "server.py"]
