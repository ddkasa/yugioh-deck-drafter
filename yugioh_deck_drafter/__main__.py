import logging
import sys
from pathlib import Path
from typing import Optional, NamedTuple, Final
from json import dumps
from pprint import pprint
from datetime import date, datetime
from collections import OrderedDict
from dataclasses import dataclass, field
from urllib.parse import quote

from functools import partial, cache

import re
import random

from itertools import groupby
from PyQt6 import QtCore, QtGui

import requests_cache
import requests

from PyQt6.QtCore import (QObject, Qt, QRectF, QPointF, QCoreApplication)
from PyQt6.QtWidgets import (QApplication, QLineEdit, QPushButton, QWidget,
                             QComboBox, QVBoxLayout, QListWidget, QSlider,
                             QHBoxLayout, QListWidgetItem, QDialog,
                             QGridLayout, QToolButton, QSizePolicy,
                             QMenu, QButtonGroup, QSpinBox, QCompleter,
                             QScrollArea, QLabel)

from PyQt6.QtGui import (QIntValidator, QPixmapCache, QPixmap, QPainter,
                         QPaintEvent, QResizeEvent, QContextMenuEvent,
                         QCursor)



from yugioh_deck_drafter import util


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


class YGOCard(NamedTuple):
    name: str
    card_id: int
    card_type: str
    rarity: str = "Common"
    card_set: Optional[SelectedSet] = None



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

    def card_arche_types(self, card_arche: str,
                         subtype: str = "archetype") -> list | None:
        URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php?{0}={1}"

        request = self.CACHE.get(URL.format(subtype, card_arche))

        if request.status_code != 200:
            # Add a default image here in the future.
            logging.critical("Failed to fetch card arche_types. Skipping!")
            logging.critical(request.status_code)
            return None

        return request.json()["data"]

    def grab_card(self, name: str) -> dict:
        name = quote(name, safe="/:?&")
        URL = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?name={name}"

        request = self.CACHE.get(URL)

        if request.status_code != 200:
            # Add a default image here in the future.
            logging.critical(f"Failed to grab {name}. Skipping!")
            logging.critical(request.status_code)
            return None

        return request.json()["data"]

    def create_card(self, data: dict, set_data: SelectedSet | None) -> YGOCard:
        rarity = "Common"

        if isinstance(set_data, SelectedSet):
            card_sets = data["card_sets"]
            for card_set in card_sets:
                card_set_code = card_set["set_code"]
                if set_data.set_code in card_set_code:
                    rarity = card_set["set_rarity"]
                    break

        card = YGOCard(data["name"], data["id"], data["type"], rarity,
                       set_data)

        return card

    def to_ygodk_format(self,
                        main: list,
                        extra: list,
                        bonus: list,
                        path: Path) -> bool:
        return True


class MainWindow(QWidget):

    def __init__(self, parent: QWidget | None, flags=Qt.WindowType.Widget):
        super(MainWindow, self).__init__(parent, flags)
        self.YU_GI = YugiObj()

        QPixmapCache.setCacheLimit(200000)

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

        PACK_MAX: Final[int] = 40
        DEFAULT_PACK_COUNT: Final[int] = 10

        self.no_packs = QSlider()
        self.no_packs.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.no_packs.setTickInterval(10)
        self.no_packs.setOrientation(Qt.Orientation.Horizontal)
        self.no_packs.setMinimum(1)
        self.no_packs.setValue(DEFAULT_PACK_COUNT)
        self.no_packs.setMaximum(PACK_MAX)
        self.select_layout.addWidget(self.no_packs, 50)

        self.no_pack_indi = QSpinBox()
        self.no_pack_indi.setValue(DEFAULT_PACK_COUNT)
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
        dialog = SelectionDialog(self)
        if dialog.exec() == 1:
            # Save the deck here
            pass

    def reset_selection(self):
        logging.info("Resetting app to defaults.")
        self.selected_packs = {}
        self.selected_cards = []
        self.selected_side = []

        self.list_widget.clear()


class SelectionDialog(QDialog):

    def __init__(self, parent: MainWindow, flags=Qt.WindowType.Dialog):
        super(SelectionDialog, self).__init__(parent, flags)

        self.setWindowTitle("Card Selector")

        self.main_deck = []
        self.extra_deck = []
        self.side_deck = []

        self.opened_packs = 0

        self.selection_per_pack = 0

        p_size = QApplication.primaryScreen().availableGeometry()

        self.setMinimumSize(p_size.width() // 2, p_size.height() // 2)

        self.button_size = p_size.width() // 12

        self.sets = {}
        self.data_requests = parent.YU_GI

        self.main_layout = QVBoxLayout()

        self.card_layout = QGridLayout()
        self.card_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.addLayout(self.card_layout)

        self.card_buttons: list[CardButton] = []  # Contains the card widgets.

        self.button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.pressed.connect(self.reject)
        self.button_layout.addWidget(self.cancel_button)

        self.button_layout.addStretch(40)

        self.card_picks_left = QLabel("0")
        self.button_layout.addWidget(self.card_picks_left)

        self.button_layout.addStretch(20)

        self.cards_picked = QLabel("0")
        self.button_layout.addWidget(self.cards_picked)

        self.button_layout.addStretch(40)

        self.accept_button = QPushButton("Next")
        self.accept_button.pressed.connect(self.sel_next_set)
        self.button_layout.addWidget(self.accept_button)

        self.button_layout.addStretch(20)

        self.accept_button = QPushButton("Accept")
        self.accept_button.pressed.connect(self.accept)
        self.button_layout.addWidget(self.accept_button)

        self.picked_cards: list[CardButton] = []

        self.main_layout.addLayout(self.button_layout)

        self.setLayout(self.main_layout)

        self.sel_next_set()

    def sel_next_set(self):
        if self.selection_per_pack > 0:
            logging.error("Select at least 2 cards to open the next pack.")
            return

        if self.picked_cards:
            self.add_card_to_deck()

        sel_packs = self.parent().selected_packs
        if len(self.parent().selected_packs) == self.opened_packs:
            logging.error("Selection complete!")
            return

        self.clean_layout()

        next_key = list(sel_packs.keys())[self.opened_packs]
        set_data = sel_packs[next_key]
        if set_data.count == 0:
            self.opened_packs += 1
            return self.sel_next_set()

        if not set_data.probabilities:
            card_data = self.data_requests.get_card_set_info(next_key)
            set_data.card_set = card_data
            probabilities = self.generate_probab(next_key, card_data)
            set_data.probabilities = probabilities

        self.open_pack(set_data.card_set, set_data.probabilities, set_data)

        set_data.count -= 1

    def add_card_to_deck(self):
        for cardbutton in self.picked_cards:
            card = cardbutton.card_model

            if self.check_fusion_monster(card):
                self.extra_deck.append(card)

            self.main_deck.append(card)

        self.update_counter_label()

    def generate_probab(self, card_set_name: str, data: list,
                        extra: bool = False) -> list:
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
                if rarity_name == "Common" and extra:
                    break

                card["set_rarity"] = rarity_name

                rarity = round(PROB.get(rarity_name, 2.8571428571) * 10)

                for _ in range(rarity):
                    probabilities.append(index)
                break

        return probabilities

    def clean_layout(self):
        for i in range(self.card_layout.count()):
            item = self.card_layout.itemAt(i)
            if item is None:
                continue

            widget: CardButton = item.widget()  # type: ignore
            if widget is None:
                continue
            widget.deleteLater()
            try:
                idx = self.picked_cards.index(widget)
                self.picked_cards.pop(idx)
            except ValueError:
                pass
            try:
                idx = self.card_buttons.index(widget)
                self.card_buttons.pop(idx)
            except ValueError:
                pass

            widget.setParent(None)

        self.picked_cards = []
        self.card_buttons = []

    def open_pack(self,
                  card_set: list,
                  probablities: list,
                  set_data: SelectedSet):
        (logging.debug(f"Opening a pack from {set_data.set_name}."
                       .center(60,"-")))



        self.selection_per_pack += 2
        logging.debug(f"{self.selection_per_pack} Cards Plus Available.")
        self.update_counter_label()

        CARD_PER_PACK = 9

        row = 0        
        for column in range(CARD_PER_PACK):
            print(column)
            if column == 8:
                prob = self.generate_probab(set_data.set_name, card_set,
                                            extra=True)
                random_int = random.randint(0, len(prob) - 1)
                pick = prob[random_int]
            else:
                random_int = random.randint(0, len(probablities) - 1)
                pick = probablities[random_int]

            row = 0
            if column % 2 != 0:
                row = 1
                column -= 1

            card_data = card_set[pick]
            card = CardButton(card_data, set_data, self)

            self.card_buttons.append(card)
            card.toggled.connect(self.update_selection)
            self.card_layout.addWidget(card, row, column, 1, 1)

    def parent(self) -> MainWindow:
        return super().parent()  # type: ignore

    def accept(self):
        self.parent().reset_selection()
        return super().accept()

    def update_selection(self):
        logging.debug("Updating Selection")

        for item in self.card_buttons:
            item.blockSignals(True)
            item_in = item in self.picked_cards

            fus_monster = self.check_fusion_monster(item.card_model)

            print(item_in, item.accessibleName())

            if item.isChecked() and (self.selection_per_pack > 0 or fus_monster):
                if not item_in:
                    print(f"adding card {item.accessibleName()}")
                    self.picked_cards.append(item)
                    if not fus_monster:
                        self.selection_per_pack -= 1

            elif not item.isChecked() and item_in:
                print(f"removing card {item.accessibleName()}")
                index = self.picked_cards.index(item)
                self.picked_cards.pop(index)
                if not fus_monster:
                    self.selection_per_pack += 1

            elif not item_in and not fus_monster:
                item.setChecked(False)

            self.update_counter_label()

            item.blockSignals(False)

    def update_counter_label(self):
        remaining = f"Remaining Picks: {self.selection_per_pack}"
        self.card_picks_left.setText(remaining)
        picked = len(self.main_deck)
        self.cards_picked.setText(f"Card Total: {picked}")

    def check_fusion_monster(self, card: YGOCard) -> bool:
        return card.card_type == "Fusion Monster"
    
    


class CardButton(QToolButton):
    def __init__(self, data: dict, card_set: Optional[SelectedSet],
                 parent: SelectionDialog):
        super(CardButton, self).__init__(parent)

        self.card_set = card_set
        self.card_model = parent.data_requests.create_card(data, card_set)
        self.data = data

        self.card_id = data["id"]
        name = data["name"]
        desc = data["desc"]

        self.setAccessibleDescription(desc)

        desc = util.new_line_text(desc, 100)
        self.setAccessibleName(name)
        self.setToolTip(name + "\n" + desc)
        self.setObjectName("card_button")

        QSP = QSizePolicy.Policy

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)

        self.setSizePolicy(QSP.MinimumExpanding, QSP.MinimumExpanding)
        self.setCheckable(True)

        self.assocc = set(self.filter_assocciated())

        self.image = parent.data_requests.get_card_art(self.card_id)

    def filter_assocciated(self) -> list:
        pattern = r'(?<!\\)"(.*?[^\\])"'
        matches = re.findall(pattern, self.accessibleDescription())

        return matches

    def paintEvent(self, event: QPaintEvent | None):
        if event is None:
            return super().paintEvent(event)
        rect = event.rect()
        height = rect.height()

        tform_mode = Qt.TransformationMode
        image = self.image.scaledToHeight(height,
                                          tform_mode.SmoothTransformation)

        self.setMaximumWidth(image.width())

        painter = QPainter(self)
        HINT = QPainter.RenderHint
        painter.setRenderHints(HINT.LosslessImageRendering | HINT.Antialiasing)

        pt = QPointF(rect.x(), rect.y())
        new_rect = QRectF(rect.x(), rect.y(), image.width(), image.height())

        painter.drawPixmap(pt, image, new_rect)

        super().paintEvent(event)

    def show_menu(self):
        if self.parent().selection_per_pack < 1:
            return

        pos = QCursor().pos()
        menu = QMenu(self)

        # race = self.data['race']
        # race_type = menu.addAction(f"Search for {race}")
        # (race_type.triggered  # type: ignore
        #  .connect(lambda: self.search_type(race, "race")))
        # attribute = self.data.get("attribute")
        # if attribute is not None:
        #     attribute_type = menu.addAction(f"Search for {attribute}.")
        #     (attribute_type.triggered  # type: ignore
        #      .connect(lambda: self.search_type(attribute, "attribute")))

        # # archetype = self.data.get("archetype")
        # # if archetype is not None:
        # #     type_action = menu.addAction(f"Search for {archetype}.")
        # #     (type_action.triggered  # type: ignore
        # #      .connect(lambda: self.search_type(archetype)))

        if self.data["type"] == "Fusion Monster":
            poly = menu.addAction("Add Polymerization")
            (poly.triggered  # type: ignore
             .connect(lambda: self.get_card("Polymerization")))

            fusion = menu.addAction("Add Fusion Parts")
            (fusion.triggered  # type: ignore
             .connect(lambda: self.get_card(self.assocc)))

        else:
            for item in self.assocc:
                acc = menu.addAction(f"Add {item}")
                (acc.triggered  # type: ignore
                 .connect(partial(self.get_card, item)))
            if self.assocc:
                acc = menu.addAction("Add all Assocciated")
                (acc.triggered  # type: ignore
                 .connect(lambda: self.get_card(self.assocc)))
            else:
                return

        menu.exec(pos)

    def get_card(self, card_name: str | list | set):

        if isinstance(card_name, (list, set)):
            for item in card_name:
                self.get_card(item)
            return

        data = self.parent().data_requests.grab_card(card_name)
        if data is None:
            return
        logging.info(f"Adding {card_name} to selection.")

        c_mdl = self.parent().data_requests.create_card(data[0], self.card_set)

        self.add_card(c_mdl)

    def add_card(self, card: YGOCard):
        self.parent().main_deck.append(card)
        if card.card_type != "Fusion Monster":
            self.parent().selection_per_pack -= 1
        self.parent().update_counter_label()

    # def search_type(self, attribute: str, subtype: str = "archetype"):
    #     dialog = SearchDialog(attribute, subtype, self.parent())

    #     if dialog.exec() == 1:
    #         self.add_card(dialog.selected_item)

    def parent(self) -> SelectionDialog:
        return super().parent()  # type: ignore

    # def resizeEvent(self, event: QResizeEvent | None) -> None:
    #     size = self.parent().size()
    #     width = size.width() // 10
    #     height = size.height() // 10

    #     self.resize(width, height)

    #     return super().resizeEvent(event)


class SearchDialog(QDialog):

    def __init__(self, attribute: str, subtype: str, parent: SelectionDialog):
        super(SearchDialog, self).__init__(parent)

        self.data = parent.data_requests.card_arche_types(attribute, subtype)
        if self.data is None:
            return self.reject()

        p_size = QApplication.primaryScreen().availableGeometry()

        self.setMinimumSize(p_size.width() // 2, p_size.height() // 2)

        self.main_layout = QVBoxLayout()

        self.search_box = QLineEdit()
        self.main_layout.addWidget(self.search_box)

        self.scroll_widget = QScrollArea()
        self.card_widget = QWidget()
        self.scroll_widget.setWidget(self.card_widget)
        self.scroll_widget.setWidgetResizable(True)

        self.main_layout.addWidget(self.scroll_widget)

        self.card_layout = QHBoxLayout()
        self.card_widget.setLayout(self.card_layout)

        self.card_buttons: list[CardButton] = []
        self.card_button_group = QButtonGroup()
        self.card_button_group.setExclusive(True)

        CMP = Qt.ContextMenuPolicy

        for i, item in enumerate(self.data):
            card_button = CardButton(item, None, parent)
            card_button.setContextMenuPolicy(CMP.NoContextMenu)
            self.card_buttons.append(card_button)
            self.card_button_group.addButton(card_button)
            self.card_layout.addWidget(card_button)

        self.button_layout = QHBoxLayout()
        self.canceL_button = QPushButton("Cancel")
        self.canceL_button.pressed.connect(self.reject)
        self.button_layout.addWidget(self.canceL_button)

        self.button_layout.addStretch(20)

        self.accept_button = QPushButton("Accept")
        self.accept_button.pressed.connect(self.accept)
        self.button_layout.addWidget(self.accept_button)

        self.main_layout.addLayout(self.button_layout)

        self.fill_search()

        self.setLayout(self.main_layout)

    def fill_search(self):
        if not isinstance(self.data, list):
            return self.reject()

        names = [card["name"] for card in self.data]

        completer = QCompleter(names)
        completer.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)

        self.search_box.setCompleter(completer)
        self.search_box.editingFinished.connect(lambda: self.highlight_search)

    def highlight_search(self):
        name = self.search_box.text()
        for item in self.card_buttons:
            if item.accessibleName() == name:
                item.setChecked(True)
                return

    def accept(self) -> None:
        for item in self.card_buttons:
            if item.isChecked():
                self.selected_item = item.card_model
        else:
            self.selected_item = self.card_buttons[0]

        return super().accept()


def main():
    FMT = "%(levelname)s | %(module)s\\%(funcName)s:%(lineno)d -> %(message)s"

    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=FMT)
    logging.info(f"Starting {NAME}!")

    app = QApplication(sys.argv)
    # app.setStyle('Fusion')
    main_window = MainWindow(None)
    with open(r"yugioh_deck_drafter\style\stylesheet.qss", "r") as style:
        main_window.setStyleSheet(style.read())

    main_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
