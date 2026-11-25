FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8768

CMD ["python", "-m", "shenqi", "serve", "--host", "0.0.0.0"]
