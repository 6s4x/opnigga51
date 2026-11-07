FROM mcr.microsoft.com/playwright/python:v1.64.1-jammy

RUN apt-get update && apt-get install -y xvfb && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY railway_api/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY railway_api/ .

ENV PORT=8080
ENV DISPLAY=:99
EXPOSE 8080

CMD Xvfb :99 -screen 0 1280x800x24 -nolisten tcp & sleep 1 && python main.py
