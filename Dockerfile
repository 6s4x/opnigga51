FROM mcr.microsoft.com/playwright/python:v1.64.1-jammy

WORKDIR /app

COPY railway_api/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY railway_api/ .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "main.py"]
