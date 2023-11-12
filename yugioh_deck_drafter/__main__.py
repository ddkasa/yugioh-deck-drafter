import logging
import sys
from pathlib import Path
from typing import Optional, NamedTuple
from json import dumps
from pprint import pprint
from datetime import date, datetime
from collections import OrderedDict
from dataclasses import dataclass, field
import random

from itertools import groupby
from PyQt6 import QtGui

from PyQt6.QtCore import (QObject, Qt, QRectF, QPointF, QCoreApplication)
from PyQt6.QtWidgets import (QApplication, QLineEdit, QPushButton, QWidget,
                             QComboBox, QVBoxLayout, QListWidget, QSlider,
                             QHBoxLayout, QListWidgetItem, QDialog,
                             QGridLayout, QToolButton, QSizePolicy,
                             QMenu, QButtonGroup, QSpinBox)

from PyQt6.QtGui import (QIntValidator, QPixmapCache, QPixmap, QPainter,
                         QPaintEvent, QResizeEvent, QContextMenuEvent,
                         QCursor)

from yugioh_deck_drafter import util

import requests_cache
import requests

NAME = "YU-GI-OH Deck Creator"




@dataclass
class SelectedSet:
    set_name: str
    set_code: str
    data: date
    card_count: int = field(default=1)
    count: int = field(default=1)
    card_set: list = field(default_factory=lambda: [])
    probabilities: list = field(default_factory=lambda: [])


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

        request = self.CACHE.get(URL.format(card_arche))

        if request.status_code != 200:
            # Add a default image here in the future.
            logging.critical("Failed to fetch card image. Skipping!")
            logging.critical(request.status_code)
            return None

        return request.json()

    def to_ydk_format(self, cards: list):
        pass


class MainWindow(QWidget):

    def __init__(self, parent: QWidget | None, flags=Qt.WindowType.Widget):
        super(MainWindow, self).__init__(parent, flags)
        self.YU_GI = YugiObj()

        QPixmapCache.setCacheLimit(5000)

        self.setWindowTitle(NAME)
        self.selected_packs: dict[str, SelectedSet] = {}
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self.select_layout = QHBoxLayout()
        self.main_layout.addLayout(self.select_layout)

        self.select_pack = QComboBox()
        names = [item["set_name"] for item in self.YU_GI.card_set]
        self.select_pack.addItems(names)
        self.select_layout.addWidget(self.select_pack, 50)
        self.select_layout.addStretch(10)

        PACK_MAX = 40

        self.no_packs = QSlider()
        self.no_packs.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.no_packs.setTickInterval(10)
        self.no_packs.setOrientation(Qt.Orientation.Horizontal)
        self.no_packs.setMinimum(1)
        self.no_packs.setValue(1)
        self.no_packs.setMaximum(PACK_MAX)
        self.select_layout.addWidget(self.no_packs, 50)

        self.no_pack_indi = QSpinBox()
        self.no_pack_indi.setValue(1)
        self.no_pack_indi.setMinimum(1)
        self.no_pack_indi.setMaximum(PACK_MAX)
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
        self.no_pack_indi.valueChanged[int].connect(self.update_indi)
        self.start_button.pressed.connect(self.start_creating)

        self.show()

    def add_item(self):
        label = self.select_pack.currentText()
        if label in self.selected_packs:
            return

        index = self.select_pack.currentIndex()
        data = self.YU_GI.card_set[index]

        cnt = self.no_pack_indi.value()

        item = QListWidgetItem(f"{cnt}x {label}")
        self.list_widget.addItem(item)

        data = SelectedSet(label, data["set_code"], data["tcg_date"],
                           data["num_of_cards"], cnt)

        self.selected_packs[label] = data

    def update_indi(self, value: int):
        self.no_packs.blockSignals(True)
        self.no_packs.setValue(value)
        self.no_pack_indi.setValue(value)
        self.no_packs.blockSignals(False)

    def start_creating(self):
        if not self.selected_packs:
            logging.error("Select some sets to open.")
            return
        dialog = SelectioDialog(self)
        if dialog.exec() == 1:
            # Save the deck here
            pass

    def reset_selection(self):
        logging.info("Resetting app to defaults.")
        self.selected_packs = {}
        self.selected_cards = []
        self.selected_side = []

        self.list_widget.clear()


class SelectioDialog(QDialog):

    def __init__(self, parent: MainWindow, flags=Qt.WindowType.Dialog):
        super(SelectioDialog, self).__init__(parent, flags)

        self.main_deck = {}
        self.extra_deck = {}
        self.side_deck = {}

        self.opened_packs = 0

        p_size = QApplication.primaryScreen().availableGeometry()

        self.setMinimumSize(p_size.width() // 2, p_size.height() // 2)

        self.button_size = p_size.width() // 12

        self.setWindowTitle("Card Selector")

        self.sets = {}
        self.data_requests = parent.YU_GI

        self.main_layout = QVBoxLayout()

        self.card_layout = QGridLayout()
        self.main_layout.addLayout(self.card_layout)

        self.cards = []  # Contains the card widgets.

        self.button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.pressed.connect(self.reject)
        self.button_layout.addWidget(self.cancel_button)

        self.button_layout.addStretch(80)

        self.accept_button = QPushButton("Next")
        self.accept_button.pressed.connect(self.sel_next_set)
        self.button_layout.addWidget(self.accept_button)

        self.button_layout.addStretch(20)

        self.accept_button = QPushButton("Accept")
        self.accept_button.pressed.connect(self.accept)
        self.button_layout.addWidget(self.accept_button)

        self.main_layout.addLayout(self.button_layout)

        self.setLayout(self.main_layout)

        self.sel_next_set()

    def sel_next_set(self):
        sel_packs = self.parent().selected_packs
        if len(self.parent().selected_packs) == self.opened_packs:
            logging.error("Selection complete!")
            return

        next_key = list(sel_packs.keys())[self.opened_packs]
        data = sel_packs[next_key]
        if data.count == 0:
            self.opened_packs += 1
            return self.sel_next_set()

        if not data.probabilities:
            card_data = self.data_requests.get_card_set_info(next_key)
            data.card_set = card_data
            probabilities = self.generate_probab(next_key, card_data)
            data.probabilities = probabilities

        self.open_pack(data.card_set, data.probabilities)

        data.count -= 1

    def generate_probab(self, card_set_name: str, data: list) -> list:
        PROB = {
            "Common": 80,
            "Rare": 16.6667,
            "Super Rare": 8.3334,
            "Ultra Rare": 4.3478260870,
            "Secret": 2.8571428571,
        }

        probabilities = []

        for index, card in enumerate(data):
            card_sets = card["card_sets"]
            for card_set in card_sets:
                if card_set["set_name"] != card_set_name:
                    continue
                rarity_name = card_set["set_rarity"]
                rarity = round(PROB.get(rarity_name, 2.8571428571) * 10)

                for _ in range(rarity):
                    probabilities.append(index)

        return probabilities

    def open_pack(self, card_set: list, probablities: list):

        CARD_PER_PACK = 9
        
        cards_set = QButtonGroup()
        cards_set.buttonToggled.connect(self.update_selection)

        row = 0
        for column in range(CARD_PER_PACK):
            row = 0
            if column % 2 != 0:
                row = 2
                column -= 1

            random_int = random.randint(0, len(probablities) - 1)
            pick = probablities[random_int]
            item = card_set[pick]
            card = CardButton(item, self)

            self.cards.append(card)
            cards_set.addButton(card)
            self.card_layout.addWidget(card, row, column, 1, 2)

    def update_selection(self):
        pass

    def parent(self) -> MainWindow:
        return super().parent()  # type: ignore

    def accept(self):
        self.parent().reset_selection()
        return super().accept()


class CardButton(QToolButton):
    def __init__(self, data: dict, parent: SelectioDialog):
        super(CardButton, self).__init__(parent)
        self.data = data

        card_id = data["id"]
        name = data["name"]
        desc = data["desc"]

        self.setAccessibleDescription(desc)

        desc = util.new_line_text(desc, 100)

        self.setAccessibleName(name)
        self.setToolTip(desc)
        self.setObjectName("card_button")

        style_sheet = "background: transparent;"
        QSP = QSizePolicy.Policy

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)

        self.setStyleSheet(style_sheet)
        self.setSizePolicy(QSP.Preferred,
                           QSP.Preferred)
        self.setCheckable(True)

        self.image = parent.data_requests.get_card_art(card_id)

    def paintEvent(self, event: QPaintEvent | None):
        if event is None:
            return
        rect = event.rect()
        height = rect.height()

        transform_mode = Qt.TransformationMode
        image = self.image.scaledToHeight(height,
                                          transform_mode.SmoothTransformation)
        self.setMaximumWidth(image.width())

        painter = QPainter(self)
        HINT = QPainter.RenderHint
        painter.setRenderHints(HINT.LosslessImageRendering | HINT.Antialiasing)

        pt = QPointF(rect.x(), rect.y())
        new_rect = QRectF(rect.x(), rect.y(), image.width(), image.height())

        painter.drawPixmap(pt, image, new_rect)

        return super().paintEvent(event)

    def show_menu(self):
        pos = QCursor().pos()
        menu = QMenu(self)

        menu.addSection(self.accessibleName())
        archetype = self.data.get("archetype")

        if archetype is not None:
            type_action = menu.addAction(archetype)

        menu.exec(pos)

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
