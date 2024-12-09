FROM python:3.11.1-slim
WORKDIR /orders
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
COPY . .