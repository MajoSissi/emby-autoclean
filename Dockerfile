FROM python:3.11-alpine

WORKDIR /app

COPY app/* /app/
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
