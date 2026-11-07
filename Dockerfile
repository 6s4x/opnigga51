FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

WORKDIR /app

COPY railway_api/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY railway_api/ .

ENV PORT=8000
EXPOSE 8000

CMD ["python", "main.py"]
