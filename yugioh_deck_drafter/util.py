"""util.py

Utility module for fuctions that are used all over the application

Functions:
    get_or_insert: For collection images from cache or inserting them into
        cache.
    new_line_text: Creates a string that fits into a N line length.
    clean_layout: Removes all widgets from a layout and deletes thems.
    check_item_validation: For looping through layouts and skipping empty
        items.
    get_operation: Most for showing for displaying warning information in the
        GUI.
    round_down_int: Rounds down to the closest given (Nth) multiple.
    sanitize_file_path: For sanitizing save_names if the deck names or off.
    action_to_list: For adding an action to a menu and storing them in
        container.
    clean_enum_name: For filtering and saving enums as useable strings.
    enum_to_list: Converts a enum object into a list for easier matching.

Classes:
    DataSerializer: For serializing and saving JSON files for quicker
        debugging.
    PackagePathFilter: Custom fitler for debugging and logging purposes.

"""

import logging
from typing import Optional
from pathlib import Path
from json import JSONEncoder
from datetime import date
import sys
import re
import unicodedata
import enum
from functools import cache
import os
import math

from PyQt6.QtGui import QPixmap, QPixmapCache, QAction

from PyQt6.QtWidgets import QLayout, QLayoutItem, QWidget, QMenu


def get_or_insert(pixmap_path: str | Path, format: str = ".jpg",
                  data: Optional[bytes] = None) -> QPixmap:
    """Manages loading and cache operations for QPixmaps.

    Args:
        pixmap_path (str | Path): Path of the image being loaded or where to
            save to.
        format (str, optional): Format of the images being loaded.\
            Defaults to ".jpg".
        data (Optional[bytes], optional): Data if an image is being loaded
            from a GET requesta. Defaults to None.

    Returns:
        QPixmap: A pointer to an image that has been saved and loaded into
            cache.
    """
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
    """Generate a new string with target line length.

    Args:
        text (str): String to be transformed into multiline.
        max_line_length (int): What the maximum characters a line should
            contain.

    Returns:
        str: Transformed multiline string.
    """
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


def clean_layout(layout: QLayout):
    """Removes and deletes widgets from the supplied layout.

    Args:
        layout (QLayout): Any type of Qt Layout with widgets inserted.
    """
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = check_item_validation(item)
        if widget is None:
            continue
        widget.deleteLater()
        widget.setParent(None)


def check_item_validation(item: QLayoutItem | None) -> QWidget | None:
    """Simple helper function for dealing with layouts.

    Args:
        item (QLayoutItem | None): The item to be checked.

    Returns:
        QWidget | None: Either return None or the widget if it exists.
    """
    if item is None:
        return
    widget = item.widget()
    if widget is None:
        return
    return widget


def get_operation(number: int) -> tuple[str, int]:
    """Gets an operation in readable format for GUI usage and turns the value
    supplied into an absolute

    Args:
        number (int): Number to derive the operation from.

    Returns:
        tuple[str, int]: Operation and absolute number (int) in a tuple.
    """
    operation = "Remove"
    if number < 0:
        operation = "Add"
        number *= -1

    return operation, number


def round_down_int(value: int, multiple: int = 10) -> int:
    """Rounds down a value[integer] to the closest multiple[int]"""
    return math.floor(value / multiple) * multiple


def sanitize_file_path(name: str, max_len=255) -> Path:
    """Sanitizing a file path for easier saving purposes at the end of the
    drafting process.

    Args:
        name (str): String to tb ereformated and cleaned.
        max_len (int, optional): Maximum length of the file name.
            Defaults to 255.

    Returns:
        Path: A file path ready to be used for saving.
    """
    name = name.replace("[", "-").replace("]", "-")
    sanitized_name = re.sub(r'[\\/:"*?<>|]', '', name)
    sanitized_name = unicodedata.normalize('NFC', sanitized_name)
    sanitized_name = sanitized_name[:max_len]
    return Path(sanitized_name)


class DateSerializer(JSONEncoder):
    """Helper subclass for easier debugging of received API structures."""
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def action_to_list_men(
    action: QAction,
    container: list,
    menu: QMenu
) -> None:
    """Helper function to add a action to a menu + array in order to
    not lose it to scope.

    Args:
        action (QAction): Precreated action to be added.
        container (list): Container to store the action in.
        menu (QMenu): Menu to add the action to.
        """
    menu.addAction(action)
    container.append(action)


def clean_enum_name(en_name: enum.Enum) -> str:
    """Converts an enum value into a formatted name for querying.

    Args:
        name (EnumMeta): Enum member to take the name from.

    Returns:
        str: Sanitized name for fetching card info.
    """
    conv = en_name.name.lower().replace("_", " ")

    return conv


@cache
def enum_to_list(e_class: enum.EnumMeta) -> list[str]:
    """Convert an enum class into a general list of enum string names.

    Args:
        e_class (enum.EnumMeta): Enumeration to convert to a list

    Returns:
        list[str]: Converted list of enum names.
    """
    data = [s.name.replace("_", " ").lower() for s in e_class]  # type: ignore
    return data


class PackagePathFilter(logging.Filter):
    def filter(self, record):
        pathname = record.pathname
        record.relativepath = None
        abs_sys_paths = map(os.path.abspath, sys.path)
        for path in sorted(abs_sys_paths, key=len, reverse=True):  # longer paths first
            if not path.endswith(os.sep):
                path += os.sep
            if pathname.startswith(path):
                record.relativepath = os.path.relpath(pathname, path)
                break
        return True


if __name__ == "__main__":
    pass
