FROM python:3.12.11

WORKDIR /License_counter

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY license_counter.py .
COPY config.yaml .
COPY folders.db .
COPY templates ./templates
COPY end ./end
COPY test ./test
COPY .env .

EXPOSE 3000
ENTRYPOINT ["python", "license_counter.py"]
