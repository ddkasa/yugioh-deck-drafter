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


class MainWindow(QWidget):

    def __init__(self,
                 parent: QWidget | None,
                 flags=Qt.WindowType.Widget) -> None:
        super().__init__(parent, flags)
        self.YU_GI = YugiObj()

        self.setWindowTitle(NAME)
        self.selected_sets = {}
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self.select_layout = QHBoxLayout()
        self.main_layout.addLayout(self.select_layout)

        self.select_pack = QComboBox()
        names = [item["set_name"] for item in self.YU_GI.card_set]
        self.select_pack.addItems(names)
        self.select_layout.addWidget(self.select_pack, 50)
        self.select_layout.addStretch(10)

        self.no_packs = QSlider()
        self.no_packs.setTickPosition(QSlider.TickPosition.TicksBothSides)
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

        self.start_button = QPushButton("START")
        self.main_layout.addWidget(self.start_button)
        self.select_pack.currentIndexChanged.connect(self.add_item)
        self.no_packs.valueChanged[int].connect(self.update_indi)
        self.show()

    def add_item(self):
        label = self.select_pack.currentText()
        cnt = self.no_packs.value()
        item = QListWidgetItem(f"{cnt}x {label}")
        self.list_widget.addItem(item)

    def update_indi(self, value: int):
        self.no_pack_indi.setText(str(value))

    def start_creating(self):
        dialog = SelectioDialog(self)
        if dialog.exec() == 1:
            # Save the deck here
            pass


class SelectioDialog(QDialog):

    def __init__(self, parent: MainWindow, flags=Qt.WindowType.Dialog):
        super().__init__(parent, flags)

        self.main_layout = QVBoxLayout()
        self.card_layout = QGridLayout()
        self.setLayout(self.main_layout)



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
