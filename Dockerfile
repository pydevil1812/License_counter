FROM python:3.12.11

WORKDIR /License_counter

COPY License_counter/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY License_counter/license_counter.py .
COPY License_counter/config.yaml .
COPY License_counter/folders.db .
COPY License_counter/templates ./templates
COPY License_counter/license_count.yaml .
COPY end ./end
COPY test ./test
COPY .env .

EXPOSE 3000
ENTRYPOINT ["python", "license_counter.py"]
