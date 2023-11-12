from typing import Optional
from pathlib import Path

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
