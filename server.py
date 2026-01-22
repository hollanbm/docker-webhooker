import os
from sys import stdout
from types import SimpleNamespace
from typing import Optional

import docker
from docker.errors import APIError, NotFound
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

logger_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)
logger.remove()
logger.add(stdout, format=logger_format)

app = FastAPI()

_webhook_token_env = os.environ.get("WEBHOOK_TOKEN")
if _webhook_token_env is None:
    logger.error("WEBHOOK_TOKEN not set")
    raise RuntimeError("WEBHOOK_TOKEN not set")
WEBHOOK_TOKEN: str = _webhook_token_env

_container_env = os.environ.get("CONTAINER_NAME")
if _container_env is None:
    logger.error("CONTAINER_NAME not set")
    raise RuntimeError("CONTAINER_NAME not set")
CONTAINER: str = _container_env


def check_token(token_qs: Optional[str], token_hdr: Optional[str]) -> None:
    if token_qs == WEBHOOK_TOKEN:
        logger.debug("WEBHOOK_TOKEN match")
        return

    if token_hdr == WEBHOOK_TOKEN:
        logger.debug("WEBHOOK_TOKEN match")
        return

    logger.warning("invalid webhook token")
    raise HTTPException(status_code=401, detail="invalid token")


def start_container() -> SimpleNamespace:
    client = docker.from_env()
    result = SimpleNamespace(returncode=0, stdout="", stderr="")

    try:
        try:
            container = client.containers.get(CONTAINER)
        except NotFound:
            result.returncode = 1
            result.stderr = f"container for service '{CONTAINER}' not found"
            logger.warning(result.stderr)
            return result

        container.reload()
        if container.status != "running":
            container.start()
            container.reload()
            result.stdout = (
                f"started container '{container.name}' ({container.short_id}); "
                f"status={container.status}"
            )
            logger.info(result.stdout)
        else:
            result.stdout = f"container '{container.name}' already running"
            logger.info(result.stdout)
    except APIError as exc:
        result.returncode = 1
        result.stderr = str(exc)
        logger.error(str(exc))
    except Exception as exc:  # catch-all to keep HTTP response predictable
        result.returncode = 1
        result.stderr = str(exc)
        logger.error(str(exc))
    finally:
        client.close()

    return result


@app.get("/health")
def healthz():
    return {"ok": True}


@app.post("/start_container")
async def webhook(
    request: Request,
    token: Optional[str] = None,  # ?token=...
    x_webhook_token: Optional[str] = Header(default=None),
):
    check_token(token, x_webhook_token)

    res = start_container()

    ok = res.returncode == 0
    return JSONResponse(
        status_code=200 if ok else 500,
        content={
            "ok": ok,
            "container": CONTAINER,
            "stdout": (res.stdout or "")[-4000:],
            "stderr": (res.stderr or "")[-4000:],
        },
    )
