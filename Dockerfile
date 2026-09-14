FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1

RUN pip install --upgrade pip

WORKDIR /code
COPY requirements.txt /code
RUN pip install --no-cache-dir -r requirements.txt

COPY . /code/
