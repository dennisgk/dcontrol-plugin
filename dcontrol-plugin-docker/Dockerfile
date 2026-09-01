FROM python:3.12-slim

WORKDIR /app
COPY dcontrol-plugin-py/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY dcontrol-plugin-py/ ./

EXPOSE 8000
CMD ["python", "-m", "app"]
