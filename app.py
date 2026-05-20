import os
import asyncio
import logging
import sys

# Suppress harmless Windows ProactorEventLoop ConnectionResetError
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

import gradio as gr

from config import Config
from ui.app_ui import build_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Silence the specific asyncio ConnectionResetError on Windows
if sys.platform == "win32":
    import ctypes
    try:
        # Suppress WinError 10054 logs from asyncio proactor
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass


class _SuppressConnectionReset(logging.Filter):
    def filter(self, record):
        return "ConnectionResetError" not in record.getMessage() and "[WinError 10054]" not in record.getMessage()


logging.getLogger("asyncio").addFilter(_SuppressConnectionReset())


def main():
    config = Config()
    config.ensure_dirs()

    app = build_app(config)
    app.queue(max_size=1)
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True,
    )


if __name__ == "__main__":
    main()