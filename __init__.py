# -----------------------------------------------------------------------------
# Role: Exports the save file block package API.
# File Name: __init__.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-11-16
# -----------------------------------------------------------------------------

from .block import SaveFileBlock, SaveFileBlockError

__all__ = ["SaveFileBlock", "SaveFileBlockError"]
