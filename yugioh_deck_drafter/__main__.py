import logging
import sys
from pathlib import Path
from typing import Optional, NamedTuple, Final, Any, Literal
from json import dumps
from pprint import pprint
from datetime import date, datetime
from collections import OrderedDict
from dataclasses import dataclass, field
from urllib.parse import quote

from functools import partial, cache

import re
import random
from PyQt6 import QtGui

import requests_cache
import requests

from PyQt6.QtCore import (Qt, QRectF, pyqtSignal, pyqtSlot, QMimeData, QSize)

from PyQt6.QtWidgets import (QApplication, QLineEdit, QPushButton, QWidget,
                             QComboBox, QVBoxLayout, QListWidget, QSlider,
                             QHBoxLayout, QListWidgetItem, QDialog,
                             QGridLayout, QToolButton, QSizePolicy,
                             QMenu, QButtonGroup, QSpinBox, QCompleter,
                             QScrollArea, QLabel, QStyle, QLayout,
                             QStyleOptionButton, QMessageBox)

from PyQt6.QtGui import (QPen, QPixmapCache, QPixmap, QPainter,
                         QPaintEvent, QResizeEvent, QContextMenuEvent,
                         QCursor, QBrush, QDragEnterEvent, QDropEvent,
                         QMouseEvent, QDrag, QKeyEvent)



from yugioh_deck_drafter import util


NAME = "YU-GI-OH Deck Creator"


@dataclass
class SelectedSet:
    set_name: str
    set_code: str
    data: date
    card_count: int = field(default=1)
    count: int = field(default=1)
    card_set: list['YGOCard'] = field(default_factory=lambda: [])
    probabilities: list = field(default_factory=lambda: [])


class YGOCard(NamedTuple):
    name: str
    description: str
    card_id: int
    card_type: str
    raw_data: dict[str, Any]
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

    def get_card_set_info(self, card_set: SelectedSet) -> list[YGOCard]:
        """Returns the cards contained with in the given card set."""
        URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php?cardset={0}"
        request = self.CACHE.get(URL.format(card_set.set_name))
        data = request.json()
        if request.status_code != 200 or not isinstance(data, dict):
            logging.critical("Failed to fetch Card Sets. Exiting!")
            logging.critical(request.status_code)
            sys.exit()

        data = data["data"]
        cards = []

        for card_data in data:
            card = self.create_card(card_data, card_set)
            cards.append(card)

        return cards

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

    def grab_card(self, name: str) -> dict | None:
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

        card = YGOCard(data["name"], data["desc"], data["id"], data["type"],
                       data, rarity, set_data)

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

        self.discard_stage_cnt = 0

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
            text = f"Select at least {self.selection_per_pack} more cards."
            logging.error(text)
            QMessageBox.warning(self, "Select More Cards", text,
                                QMessageBox.StandardButton.Ok)
            return

        if self.picked_cards:
            self.add_card_to_deck()

        main_deck_len = len(self.main_deck)
        if (any(main_deck_len >= x for x in {20, 30, 40, 50})
           and self.discard_stage_cnt < 4):
            self.discard_stage()

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
            card_data = self.data_requests.get_card_set_info(set_data)
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
                continue

            self.main_deck.append(card)

        self.update_counter_label()

    def generate_probab(self, card_set_name: str, data: list[YGOCard],
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
            card = card.raw_data
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
        util.clean_layout(self.card_layout)

        self.picked_cards = []
        self.card_buttons = []

    def open_pack(self,
                  card_set: list,
                  probablities: list,
                  set_data: SelectedSet):
        (logging
         .debug(f"Opening a pack from {set_data.set_name}.".center(60,"-")))

        self.selection_per_pack += 2
        logging.debug(f"{self.selection_per_pack} Cards Plus Available.")
        self.update_counter_label()

        CARD_PER_PACK = 9

        row = 0        
        for column in range(CARD_PER_PACK):
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
            card = CardButton(card_data, self)

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

            if (item.isChecked()
               and (self.selection_per_pack > 0 or fus_monster)):
                if not item_in:
                    logging.debug(f"Adding card {item.accessibleName()}")
                    self.picked_cards.append(item)
                    if not fus_monster:
                        self.selection_per_pack -= 1

            elif not item.isChecked() and item_in:
                logging.debug(f"Removing card {item.accessibleName()}")
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

    def discard_stage(self):
        dialog = DeckViewer(self, discard=10)

        dialog.setWindowTitle("Card Removal Stage")

        if dialog.exec() == 1:
            pass

        self.discard_stage_cnt += 1


class CardButton(QToolButton):
    base_size = QSize(164, 242)

    def __init__(self, data: YGOCard, parent: SelectionDialog,
                 viewer: Optional['DeckViewer'] = None):
        super(CardButton, self).__init__()
        self.ASPECT_RATIO: Final[float] = 0.6776859504

        self.viewer = viewer

        self.setBaseSize(self.base_size)
        self.setMinimumSize(round(self.base_size.width() * self.ASPECT_RATIO),
                            round(self.base_size.height() * self.ASPECT_RATIO))

        self.card_set = data.card_set
        self.card_model = data
        self.card_id = data.card_id

        self.setAccessibleName(data.name)
        self.setAccessibleDescription(data.description)

        desc = util.new_line_text(data.description, 100)

        self.heightForWidth(False)

        self.setToolTip(data.name + "\n" + desc)
        self.setObjectName("card_button")

        QSP = QSizePolicy.Policy

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)

        self.setSizePolicy(QSP.Expanding, QSP.Preferred)
        self.setCheckable(True)

        self.assocc = self.filter_assocciated()

        self.image = parent.data_requests.get_card_art(self.card_id)

    def filter_assocciated(self) -> set:
        pattern = r'(?<!\\)"(.*?[^\\])"'
        matches = re.findall(pattern, self.accessibleDescription())

        return set(matches)

    def paintEvent(self, event: QPaintEvent | None):
        if event is None:
            return super().paintEvent(event)

        option = QStyleOptionButton()
        option.initFrom(self)

        rect = event.rect()
        # height = rect.height()

        painter = QPainter(self)
        HINT = QPainter.RenderHint
        painter.setRenderHints(HINT.LosslessImageRendering |
                               HINT.Antialiasing)

        tform_mode = Qt.TransformationMode
        image = self.image.scaledToHeight(self.height(),
                                          tform_mode.SmoothTransformation)

        brush = QBrush(image)
        painter.setBrush(brush)

        # RADIUS = 10

        PEN_WIDTH = 6
        PEN_HALF = PEN_WIDTH / 2
        new_rect = QRectF(rect.x() + (PEN_HALF / 2), rect.y() + (PEN_HALF / 2),
                          image.width() - PEN_HALF, image.height() - PEN_HALF)
        if self.isChecked():
            PEN_WIDTH *= 1.25
            pen = QPen(Qt.GlobalColor.red)
            pen.setWidthF(PEN_WIDTH)
            painter.setPen(pen)

        elif option.state & QStyle.StateFlag.State_MouseOver:
            pen = QPen(Qt.GlobalColor.yellow)
            pen.setWidth(PEN_WIDTH)
            painter.setPen(pen)

        painter.drawRect(new_rect)

        if not self.isChecked():
            return
        if isinstance(self.viewer, DeckViewer) and self.viewer.discard:
            painter.drawLine(rect.topLeft().toPointF(),
                             new_rect.bottomRight())
            painter.drawLine(rect.bottomLeft().toPointF(),
                             new_rect.topRight())

    def show_menu(self):
        parent = self.parent()

        pos = QCursor().pos()
        menu = QMenu(self)

        if isinstance(self.viewer, DeckViewer):
            mv_deck = self.viewer.mv_card

            if self in self.viewer.deck:
                mv_main = f"Move {self.accessibleName()} to Side Deck"
                move_to_main = menu.addAction(mv_main)
                move_to_main.triggered.connect(lambda: mv_deck(self, "side"))

            elif self in self.viewer.side:
                mv_main = f"{self.accessibleName()} to Main Deck"
                move_to_main = menu.addAction(mv_main)
                move_to_main.triggered.connect(lambda: mv_deck(self, "main"))

            return menu.exec(pos)


        if self.parent().selection_per_pack < 1:
            return

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

        if self.card_model.card_type == "Fusion Monster":
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

        c_mdl = self.parent().data_requests.create_card(data[0],
                                                        self.card_set)

        self.add_card(c_mdl)

    def add_card(self, card: YGOCard):
        self.parent().main_deck.append(card)
        if card.card_type != "Fusion Monster":
            self.parent().selection_per_pack -= 1
        self.parent().update_counter_label()

    def parent(self) -> SelectionDialog:
        return super().parent()  # type: ignore

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            drag.setMimeData(mime)

            pixmap = QPixmap(self.size())
            self.render(pixmap)
            drag.setPixmap(pixmap)

            drag.exec(Qt.DropAction.MoveAction)

    def resizeEvent(self, event: QResizeEvent | None) -> None:

        return super().resizeEvent(event)


class DeckViewer(QDialog):

    def __init__(self, parent: SelectionDialog, discard: int = 0):
        super(DeckViewer, self).__init__(parent)
        self.discard = discard
        self.deck: list[CardButton] = []
        self.extra: list[CardButton] = []
        self.side: list[CardButton] = []

        self.main_layout = QVBoxLayout()
        self.deck_area = QScrollArea()
        # self.deck_area.ensurePolished()
        # self.deck_area.setWidgetResizable(True)
        # self.deck_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self.deck_area_widget = QWidget()
        self.deck_layout = QGridLayout()
        self.deck_area_widget.setLayout(self.deck_layout)

        self.fill_deck(parent.main_deck, self.deck_layout, self.deck)

        self.deck_area.setWidget(self.deck_area_widget)

        self.main_layout.addWidget(self.deck_area, 60)

        self.extra_deck_widget = DeckSlider(self)
        self.main_layout.addWidget(self.extra_deck_widget, 20)

        self.fill_deck(parent.extra_deck,
                       self.extra_deck_widget.main_widget.blayout,
                       self.extra)

        self.side_deck_widget = DeckSlider(self)
        self.main_layout.addWidget(self.side_deck_widget, 20)

        self.fill_deck(parent.extra_deck,
                       self.extra_deck_widget.main_widget.blayout,
                       self.extra)

        self.button_layout = QHBoxLayout()

        if not discard:
            self.cancel_button = QPushButton()
            self.cancel_button.pressed.connect(self.reject)
            self.button_layout.addWidget(self.cancel_button)

        self.button_layout.addStretch(50)

        self.accept_button = QPushButton("Accept")
        self.accept_button.pressed.connect(self.accept)
        self.button_layout.addWidget(self.accept_button)

        self.setLayout(self.main_layout)

    def fill_deck(self, cards: list, layout: QLayout, container: list,
                  check: bool = False):
        # util.clean_layout(layout)

        MAX_COLUMNS: Final[int] = 10

        QSP = QSizePolicy.Policy
        row = 0
        column = 0
        while cards:
            # print(cards)
            # if not cards:
            #     break
            if column % MAX_COLUMNS == 0 and column:
                row += 1
                column = 0

            if isinstance(layout, QGridLayout):
                item = layout.itemAtPosition(row, column)
                if item is not None:
                    if item.widget() is not None:
                        column += 1
                        continue

            card = cards.pop(0)

            card_button = CardButton(card, self.parent(), self)
            card_button.setChecked(check)

            card_button.setSizePolicy(QSP.MinimumExpanding,
                                      QSP.MinimumExpanding)  
            card_button.acceptDrops()
            container.append(card_button)
            if isinstance(layout, QHBoxLayout):
                layout.addWidget(card_button,
                                 alignment=Qt.AlignmentFlag.AlignLeft)
                continue
            layout.addWidget(card_button, row, column, 1, 1)

    def mv_card(self, card: CardButton, deck: Literal["main", "side"]):
        if deck == "main":
            side_idx = self.side.index(card)
            item = self.side.pop(side_idx)

            self.side_deck_widget.main_widget.blayout.removeWidget(card)
            card.setParent(None)

            self.deck.append(card)
            self.fill_deck([item.card_model], self.deck_layout, self.deck,
                           card.isChecked())
            return

        main_idx = self.deck.index(card)
        item = self.deck.pop(main_idx)

        self.deck_layout.removeWidget(card)
        card.setParent(None)

        self.side.append(card)
        self.fill_deck([item.card_model], self.side_deck_widget.main_layout,
                       self.side, card.isChecked())

    def parent(self) -> SelectionDialog:
        return super().parent()  # type: ignore

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return super().keyPressEvent(event)

        if (event.key() == Qt.Key.Key_Escape and self.discard):
            return

        return super().keyPressEvent(event)

    def count(self) -> int:
        return len(self.deck) + len(self.side)

    def allowed_count(self) -> int:
        allowed_count = len(self.deck) + (len(self.deck) // 5)
        return allowed_count

    def accept(self):

        def filter_items(container: list, source: list[CardButton]):
            for item in source:
                if not item.isChecked():
                    container.append(item.card_model)

        if self.count() != self.allowed_count():
            cnt = self.allowed_count() - self.count()
            QMessageBox.warning(self, "Remove More Cards",
                                f"Remove {cnt} more card(s)",
                                QMessageBox.StandardButton.Ok)
            return

        self.new_deck = []
        self.new_extra = []
        self.new_side = []

        filter_items(self.new_deck, self.deck)
        filter_items(self.new_extra, self.extra)
        filter_items(self.new_side, self.side)

        return super().accept()


class DeckSlider(QScrollArea):

    def __init__(self, parent: DeckViewer) -> None:
        super().__init__(parent)

        self.setWidgetResizable(True)

        self.main_widget = DragWidget(Qt.Orientation.Horizontal)

        self.main_layout = self.main_widget.blayout

        self.setWidget(self.main_widget)


class DragWidget(QWidget):
    orderChanged = pyqtSignal()

    def __init__(self, orientation=Qt.Orientation.Vertical):
        super().__init__()
        # self.setAcceptDrops(True)
        self.orientation = orientation

        QSP = QSizePolicy.Policy
        # self.setSizePolicy(QSP.Preferred, QSP.Preferred)

        if self.orientation == Qt.Orientation.Vertical:
            self.blayout = QVBoxLayout()
        else:
            self.blayout = QHBoxLayout()

        self.setLayout(self.blayout)

    def add_drag_widget(self, card: CardButton):
        self.blayout.addWidget(card)

    def dragEnterEvent(self, event: QDragEnterEvent):
        event.accept()

    def dropEvent(self, event: QDropEvent):
        """Checks for a drop event and the position in order to choose where
           to put the widget."""
        pos = event.position()
        widget: CardButton = event.source()  # type: ignore

        for n in range(self.blayout.count()):
            w = self.blayout.itemAt(n).widget()
            if self.orientation == Qt.Orientation.Vertical:
                drop_here = pos.y() < w.y() + w.size().height() // 2
            else:
                drop_here = pos.x() < w.x() + w.size().width() // 2

            if drop_here:
                self.blayout.insertWidget(n - 1, widget)
                self.orderChanged.emit()
                break

        event.accept()

    @pyqtSlot(int)
    def delete_widget(self, widget: CardButton):
        widget.setParent(None)  # type: ignore
        self.orderChanged.emit()


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
