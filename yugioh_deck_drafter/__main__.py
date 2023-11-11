import logging
import sys
from pathlib import Path
import typing
import json
from pprint import pprint
from datetime import date, datetime
from collections import OrderedDict
from PyQt6 import QtCore
# import random


from PyQt6.QtCore import (
    Qt
)
from PyQt6.QtWidgets import (QApplication, QLineEdit, QPushButton, QWidget,
                             QComboBox, QVBoxLayout, QListWidget, QSlider,
                             QHBoxLayout, QListWidgetItem, QDialog,
                             QGridLayout)

from PyQt6.QtGui import (QIntValidator)

import requests_cache

NAME = "YU-GI-OH Deck Creator"


class YugiObj:

    def __init__(self) -> None:
        self.CACHE = requests_cache.CachedSession("cache\\decks.sqlite",
                                                  backend="sqlite")
        self.card_set = self.get_card_set()

    def get_card_set(self) -> list:
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
        INFO = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?cardset={card_set}"
        request = self.CACHE.get(INFO)
        if request.status_code != 200:
            logging.critical("Failed to fetch Card Sets. Exiting!")
            logging.critical(request.status_code)
            sys.exit()
        return request.json()

    def get_cards(self, card_set: int) -> list:
        CARD_SET = "https://db.ygoprodeck.com/api/v7/cardinfo.php?banlist=tcg&level=4&sort=name"
        data = []
        return


class MainWindow(QWidget):

    def __init__(self, parent: QWidget | None, flags=Qt.WindowType.Widget):
        super(MainWindow, self).__init__(parent, flags)
        self.YU_GI = YugiObj()

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
        dialog = SelectioDialog(self)
        if dialog.exec() == 1:
            # Save the deck here
            pass

    def reset_selection(self):
        logging.info("Resetting app to defaults.")

        self.selected_cards = []
        self.selected_side = []

        self.list_widget.clear()


class SelectioDialog(QDialog):

    def __init__(self, parent: MainWindow, flags=Qt.WindowType.Dialog):
        super(SelectioDialog, self).__init__(parent, flags)
        self.setWindowTitle("Card Selector")

        self.deck = parent.selected_sets
        self.data_requests = parent.YU_GI

        self.main_layout = QVBoxLayout()

        self.card_layout = QGridLayout()

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
        print(card_set)
        data = self.data_requests.get_card_set_info(card_set_name)
        # card_set[1]["set_code"]
        pprint(data)


def main():
    FMT = "%(levelname)s | %(module)s\\%(funcName)s:%(lineno)d -> %(message)s"

    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=FMT)
    logging.info(f"Starting {NAME}!")

    app = QApplication(sys.argv)
    main_window = MainWindow(None)
    main_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":

    main()
