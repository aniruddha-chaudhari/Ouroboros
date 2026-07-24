FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && opentelemetry-bootstrap -a install
COPY app ./app
COPY run.sh .
RUN chmod +x run.sh
EXPOSE 8000
CMD ["./run.sh"]
