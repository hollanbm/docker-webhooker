ARG UV_VERSION=0.9.24

FROM ghcr.io/astral-sh/uv:${UV_VERSION}-debian AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Update system packages
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# https://docs.astral.sh/uv/reference/environment/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_PREFERENCE=only-managed \
    UV_NO_DEV=1 UV_NO_EDITABLE=1 UV_FROZEN=1

# Configure the Python install directory for use when copying between stages
ENV UV_PYTHON_INSTALL_DIR=/python

WORKDIR /app
# Install dependencies first for better caching
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-install-project

# Copy the rest of the app in
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync

# chainguard secure distroless base image
FROM cgr.dev/chainguard/wolfi-base:latest AS runtime

# Grab python from the builder
COPY --from=builder --chown=python:python /python /python

WORKDIR /app

# Copy the application from the builder
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app server.py /app/server.py


# activate venv
ENV PATH="/app/.venv/bin:$PATH"

# start the FastAPI webhook server
ENTRYPOINT ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
