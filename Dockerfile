FROM python:3.11-slim

WORKDIR /app

COPY requirements-deploy.txt /app/requirements-deploy.txt
RUN pip install --no-cache-dir -r /app/requirements-deploy.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV PORT=5000

EXPOSE 5000

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120"]
