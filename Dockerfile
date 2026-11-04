FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOTEL_WEB_API_HOST=0.0.0.0
WORKDIR /app
COPY administrador/requirements-api.txt ./requirements-api.txt
RUN pip install --no-cache-dir -r requirements-api.txt
COPY administrador/hotel_admin/ ./hotel_admin/
RUN useradd --create-home hotel && mkdir -p /app/storage/room_photos && chown -R hotel:hotel /app
USER hotel
CMD ["python", "-m", "hotel_admin.web_api"]
