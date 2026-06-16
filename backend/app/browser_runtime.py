from __future__ import annotations

import asyncio
import sys


def ensure_browser_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    proactor_policy = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if proactor_policy is None:
        return
    current = asyncio.get_event_loop_policy()
    if not isinstance(current, proactor_policy):
        asyncio.set_event_loop_policy(proactor_policy())
