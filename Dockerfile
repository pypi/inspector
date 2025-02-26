# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.11.8-slim-bullseye

# Allow statements and log messages to immediately appear in the logs
ENV PYTHONUNBUFFERED True

# Don't create .pyc files
ENV PYTHONDONTWRITEBYTECODE True

# Put our application on the PYTHONPATH
ENV PYTHONPATH /app

# Define whether we're building a production or a development image. This will
# generally be used to control whether or not we install our development and
# test dependencies.
ARG DEVEL=no

# Install System level requirements, this is done before everything else
# because these are rarely ever going to change.
RUN set -x \
    && apt-get update \
    && apt-get install -y \
    git cmake g++ \
    #        $(if [ "$DEVEL" = "yes" ]; then echo 'bash postgresql-client'; fi) \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy local code to the container image.
WORKDIR /app
# Copy in requirements files
COPY ./requirements ./requirements

# Install production dependencies.
RUN pip install \
    -r requirements/main.txt \
    -r requirements/deploy.txt

# Install development dependencies
RUN if [ "$DEVEL" = "yes" ]; then pip install -r requirements/lint.txt; fi
RUN if [ "$DEVEL" = "yes" ]; then pip install -r requirements/tests.txt; fi

# Copy in everything else
COPY . .
