FROM python:3.9

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y curl \
    && curl -sSL https://install.python-poetry.org \
    | python3 - --git https://github.com/python-poetry/poetry.git@master
WORKDIR /app
COPY pyproject.toml poetry.lock /app
RUN poetry install --no-dev
COPY . /app