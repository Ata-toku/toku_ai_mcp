FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY server.py .
COPY tools/ tools/

EXPOSE 8000

CMD ["python", "server.py"]
