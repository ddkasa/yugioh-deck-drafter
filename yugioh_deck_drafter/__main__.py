import logging
import sys
from pathlib import Path
from typing import Optional
import json
from pprint import pprint
from datetime import date, datetime
from collections import OrderedDict
from PyQt6 import QtCore, QtGui
# import random


from PyQt6.QtCore import (Qt, QRectF, QPointF, QCoreApplication)
from PyQt6.QtWidgets import (QApplication, QLineEdit, QPushButton, QWidget,
                             QComboBox, QVBoxLayout, QListWidget, QSlider,
                             QHBoxLayout, QListWidgetItem, QDialog,
                             QGridLayout, QToolButton, QSizePolicy)

from PyQt6.QtGui import (QIntValidator, QPixmapCache, QPixmap, QPainter,
                         QPaintEvent, QResizeEvent)

from yugioh_deck_drafter import util

import requests_cache
import requests

NAME = "YU-GI-OH Deck Creator"


class YugiObj:

    def __init__(self) -> None:
        self.CACHE = requests_cache.CachedSession("cache\\decks.sqlite",
                                                  backend="sqlite")
        self.card_set = self.get_card_set()

    def get_card_set(self) -> list:
        """Collects all card sets for selection."""
        CARD_SET = r"https://db.ygoprodeck.com/api/v7/cardsets.php"
        request = self.CACHE.get(CARD_SET)
        if request.status_code != 200:
            logging.critical("Failed to fetch Card Sets. Exiting!")
            sys.exit()
        data = request.json()

        new_set = []
        for item in data:
            d = item.get("tcg_date")
            if d is None:
                continue
            item["tcg_date"] = datetime.strptime(d, '%Y-%m-%d').date()
            new_set.append(item)

        new_set.sort(key=lambda x: x["tcg_date"])
        return new_set

    def get_card_set_info(self, card_set: str) -> list:
        """Returns the cards contained with in the given card set."""
        URL = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?cardset={card_set}"
        request = self.CACHE.get(URL)
        data = request.json()
        if request.status_code != 200 or not isinstance(data, dict):
            logging.critical("Failed to fetch Card Sets. Exiting!")
            logging.critical(request.status_code)
            sys.exit()

        return data["data"]

    def get_card_art(self, card_art_id: int) -> QPixmap:
        """Collects and stores card art for the given piece."""
        image_store = Path(r"data\images\card_art")
        image_path = image_store / str(str(card_art_id) + ".jpg")

        if image_path.exists():
            return util.get_or_insert(image_path)

        URL = f"https://images.ygoprodeck.com/images/cards/{card_art_id}.jpg"
        request = requests.get(URL)
        if request.status_code != 200:
            # Add a default image here in the future.
            logging.critical("Failed to fetch card image. Skipping!")
            logging.critical(request.status_code)
            sys.exit()

        data = request.content
        with image_path.open("wb") as image_file:
            image_file.write(data)

        image = util.get_or_insert(image_path, data=data)

        return image

    def card_arche_types(self, card_arche: str) -> list | None:
        URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php?archetype={}"

        request = self.CACHE.get(URL.format(int))

        if request.status_code != 200:
            # Add a default image here in the future.
            logging.critical("Failed to fetch card image. Skipping!")
            logging.critical(request.status_code)
            return None

        return request.json()


class MainWindow(QWidget):

    def __init__(self, parent: QWidget | None, flags=Qt.WindowType.Widget):
        super(MainWindow, self).__init__(parent, flags)
        self.YU_GI = YugiObj()

        QPixmapCache.setCacheLimit(5000)

        self.setWindowTitle(NAME)
        self.selected_sets = {}
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self.selected_cards = []
        self.side_deck = {}

        self.select_layout = QHBoxLayout()
        self.main_layout.addLayout(self.select_layout)

        self.select_pack = QComboBox()
        names = [item["set_name"] for item in self.YU_GI.card_set]
        self.select_pack.addItems(names)
        self.select_layout.addWidget(self.select_pack, 50)
        self.select_layout.addStretch(10)

        self.no_packs = QSlider()
        self.no_packs.setTickPosition(QSlider.TickPosition.NoTicks)
        self.no_packs.setTickInterval(5)
        self.no_packs.setOrientation(Qt.Orientation.Horizontal)
        self.no_packs.setMinimum(1)
        self.no_packs.setMaximum(40)
        self.select_layout.addWidget(self.no_packs, 50)

        self.no_pack_indi = QLineEdit("0")
        self.no_pack_indi.setValidator(QIntValidator())
        self.select_layout.addWidget(self.no_pack_indi, 1)

        self.list_widget = QListWidget()
        self.main_layout.addWidget(self.list_widget)

        self.button_layout = QHBoxLayout()
        self.start_button = QPushButton("START")
        self.button_layout.addWidget(self.start_button)
        self.button_layout.addStretch(20)
        self.reset_button = QPushButton("RESET")
        self.button_layout.addWidget(self.reset_button)
        self.reset_button.pressed.connect(self.reset_selection)

        self.main_layout.addLayout(self.button_layout)

        self.select_pack.currentIndexChanged.connect(self.add_item)
        self.no_packs.valueChanged[int].connect(self.update_indi)
        self.no_pack_indi.textChanged[str].connect(self.update_indi)
        self.start_button.pressed.connect(self.start_creating)

        self.show()

    def add_item(self):
        label = self.select_pack.currentText()
        index = self.select_pack.currentIndex()
        cnt = max(int(self.no_pack_indi.text()), 1)

        item = QListWidgetItem(f"{cnt}x {label}")
        self.list_widget.addItem(item)

        self.selected_sets[label] = (cnt, self.YU_GI.card_set[index])

    def update_indi(self, value: int | str):
        if isinstance(value, int):
            self.no_pack_indi.setText(str(value))
            return
        self.no_packs.setValue(int(value))

    def start_creating(self):
        if not self.selected_sets:
            logging.error("Select some sets to open.")
            return
        dialog = SelectioDialog(self)
        if dialog.exec() == 1:
            # Save the deck here
            pass

    def reset_selection(self):
        logging.info("Resetting app to defaults.")
        self.selected_sets = {}
        self.selected_cards = []
        self.selected_side = []

        self.list_widget.clear()


class SelectioDialog(QDialog):

    def __init__(self, parent: MainWindow, flags=Qt.WindowType.Dialog):
        super(SelectioDialog, self).__init__(parent, flags)

        p_size = QApplication.primaryScreen().availableGeometry()

        self.setMinimumSize(p_size.width() // 2, p_size.height() // 2)

        self.button_size = p_size.width() // 12

        self.setWindowTitle("Card Selector")

        self.deck = parent.selected_sets
        self.data_requests = parent.YU_GI

        self.main_layout = QVBoxLayout()

        self.card_layout = QGridLayout()
        self.main_layout.addLayout(self.card_layout)

        self.button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.pressed.connect(self.reject)
        self.button_layout.addWidget(self.cancel_button)

        self.button_layout.addStretch(80)

        self.accept_button = QPushButton("Accept")
        self.accept_button.pressed.connect(self.accept)
        self.button_layout.addWidget(self.accept_button)

        self.main_layout.addLayout(self.button_layout)

        self.setLayout(self.main_layout)

        test_set_key = list(self.deck.keys())[0]
        self.open_pack(test_set_key, self.deck[test_set_key])

    def open_pack(self, card_set_name: str, card_set: tuple):
        data = self.data_requests.get_card_set_info(card_set_name)
        CARD_PER_PACK = 9
        self.cards = []

        test_path = Path(r"data\set_data.json")

        # with test_path.open("w") as file:
        #     d = json.dumps(data)
        #     file.write(d)

        row = 0
        for column, item in enumerate(data):
            row = 0
            # if column + 1 == CARD_PER_PACK:
            #     row = 1
            if column % 2 != 0:
                row = 2
                column -= 1

            card_id = item["id"]
            name = item["name"]
            desc = item["desc"]

            pix = self.data_requests.get_card_art(card_id)

            card = CardButton(self, pix)

            card.setAccessibleName(name)
            card.setToolTip(desc)

            self.cards.append(card)

            # if column + 1 == CARD_PER_PACK:
            #     self.card_layout.addWidget(card, row, column, 1, 2)
            #     break

            self.card_layout.addWidget(card, row, column, 1, 2)

            if column > 9:
                break


class CardButton(QToolButton):
    def __init__(self, parent: SelectioDialog, image: QPixmap):
        super(CardButton, self).__init__(parent)
        # self.setMinimumWidth(parent.button_size)
        self.setObjectName("card_button")

        style_sheet = "background: transparent;"
        QSP = QSizePolicy.Policy

        self.setStyleSheet(style_sheet)
        self.setSizePolicy(QSP.MinimumExpanding, QSP.MinimumExpanding)
        self.setCheckable(True)

        self.image = image

    def paintEvent(self, event: QPaintEvent | None):
        if event is None:
            return

        CARD_RATIO = 1.4575645756
        rect = event.rect()

        height = rect.height()
        width = height - (height * CARD_RATIO)

        image = self.image.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)

        painter = QPainter(self)
        HINT = QPainter.RenderHint
        painter.setRenderHints(HINT.LosslessImageRendering | HINT.Antialiasing)

        pt = QPointF(rect.x(), rect.y())
        new_rect = QRectF(rect.x(), rect.y(), image.width(), image.height())

        painter.drawPixmap(pt, image, new_rect)

        return super().paintEvent(event)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        self.repaint()
        return super().resizeEvent(event)


def main():
    FMT = "%(levelname)s | %(module)s\\%(funcName)s:%(lineno)d -> %(message)s"

    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=FMT)
    logging.info(f"Starting {NAME}!")

    app = QApplication(sys.argv)
    main_window = MainWindow(None)
    with open(r"yugioh_deck_drafter\style\stylesheet.qss", "r") as style:
        main_window.setStyleSheet(style.read())

    main_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":

    main()
