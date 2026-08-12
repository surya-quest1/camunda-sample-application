FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY northwind_workers ./northwind_workers
ENTRYPOINT ["python", "-m", "northwind_workers.main"]
