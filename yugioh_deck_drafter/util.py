import logging
from typing import Optional
from pathlib import Path
from json import JSONEncoder
from datetime import date

from PyQt6.QtGui import QPixmap, QPixmapCache


def get_or_insert(pixmap_path: str | Path, format: str = ".jpg",
                  data: Optional[bytes] = None) -> QPixmap:
    if isinstance(pixmap_path, Path):
        pixmap_path = str(pixmap_path)
    cached_pixmap = QPixmapCache.find(pixmap_path)
    if cached_pixmap is None:
        if isinstance(data, bytes):
            pixmap = QPixmap()
            pixmap.loadFromData(data, format)
        else:
            pixmap = QPixmap(pixmap_path)
        QPixmapCache.insert(pixmap_path, pixmap)
        return pixmap
    return cached_pixmap


def new_line_text(text: str, max_line_length: int) -> str:
    logging.debug(f"{max_line_length}, {text}, {len(text)}")
    if "\n" in text:
        return text

    name_processed = ""
    for i, t in enumerate(text):
        if i % max_line_length == 0 and i != 0:
            last_space = name_processed.rfind(" ")
            if last_space == -1:
                name_processed += "-\n"
            else:
                name_processed = (name_processed[:last_space] + "\n"
                                + name_processed[last_space+1:])
        name_processed += t
    return name_processed


class DateSerializer(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)
