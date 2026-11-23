"""Entry point: ``python app.py`` or ``uvicorn app:app``.

Serves the REST/WebSocket API and the static mission-control dashboard.
"""

from __future__ import annotations

import os

import uvicorn

from audit.api import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
