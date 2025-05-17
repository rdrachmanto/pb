FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY .env .

EXPOSE 8081

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8081"]
