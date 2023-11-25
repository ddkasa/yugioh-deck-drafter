from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Final, Literal

import random
import re
import logging
from functools import partial

from PyQt6.QtCore import (
    Qt,
    QSize,
    pyqtSlot,
    pyqtSignal,
    QRectF,
    QRect,
    QSignalBlocker,
    QMimeData
    )

from PyQt6.QtGui import (
    QResizeEvent,
    QDropEvent,
    QDragEnterEvent,
    QPainter,
    QPaintEvent,
    QFont,
    QKeyEvent,
    QBrush,
    QPen,
    QPixmap,
    QImage,
    QCursor,
    QDrag,
    QMouseEvent
)

from PyQt6.QtWidgets import (
    QWidget,
    QDialog,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QApplication,
    QStyleOptionButton,
    QStyle,
    QMenu,
    QSpacerItem,
    
)

from yugioh_deck_drafter.modules.ygo_data import YGOCard, YGOCardSet, DeckModel
from yugioh_deck_drafter import util

if TYPE_CHECKING:
    from yugioh_deck_drafter.__main__ import MainWindow


class DraftingDialog(QDialog):
    """Dialog for opening packs and managing drafting in general, as it has a
       core function that cycles and keep track of whats been added and
       removed in the meanwhile.

    Attributes:
        W/H (int): Base size for the dialog itself.
        CARDS_PER_PACK (int): How many cards each pack contains.
        main/extra/side deck (list): Mostly for storing the selected card data.
        selection_per_pack (int): Counter for how many selections the drafter
            has left for the current pack. Must be 0 or less to proceed through
            the drafting process.
        opened_set_packs (int): Keeps track of how many pack bundles have been
            opened so far.
        total_packs (int): The total number of packs that have been opened so
            far.
        discard_stage_cnt (int): How many discard stages have occured, mainly
            to trigger deck completion.

    Args:
        parent (MainWindow): For retrieving, managing and finalzing the
            drafting data.
        deck_name (str): Name of deck set by the user used for save pathh name
            later on.
        flags (Optional[WindowType]): Mostly for debugging.

    """
    W, H = 1344, 824  # Base on 1080 screen resolution
    CARDS_PER_PACK: Final[int] = 9

    def __init__(self, parent: MainWindow, deck_name: str,
                 flags=Qt.WindowType.Dialog):
        super().__init__(parent, flags)
        self.setWindowTitle("Card Pack Opener")

        self.deck_name = deck_name

        self.main_deck: list[YGOCard] = []
        self.extra_deck: list[YGOCard] = []
        self.side_deck: list[YGOCard] = []

        self.opened_set_packs = 0
        self.total_packs = 0
        self.selection_per_pack = 0
        self.discard_stage_cnt = 0

        self.setMinimumSize(self.W, self.H)

        self.ygo_data = parent.yugi_pro_connect

        self.main_layout = QVBoxLayout()
        self.main_layout.addStretch(1)
        self.stretch = self.main_layout.itemAt(0)

        self.card_layout = QGridLayout()
        self.card_layout.setAlignment(Qt.AlignmentFlag.AlignAbsolute)
        self.main_layout.addLayout(self.card_layout)

        self.card_buttons: list[CardButton] = []  # Contains the card widgets

        self.button_layout = QHBoxLayout()

        self.check_deck_button = QPushButton("View Deck")
        self.button_layout.addWidget(self.check_deck_button)
        self.check_deck_button.pressed.connect(self.check_deck)

        self.button_layout.addStretch(60)

        self.card_picks_left = QLabel()
        self.card_picks_left.setObjectName("indicator")
        self.button_layout.addWidget(self.card_picks_left, 20)

        self.button_layout.addStretch(2)

        self.cards_picked = QLabel()
        self.cards_picked.setObjectName("indicator")
        self.button_layout.addWidget(self.cards_picked, 20)

        self.update_counter_label()

        self.button_layout.addStretch(2)

        self.packs_opened = QLabel("Pack No.: 0")
        self.packs_opened.setObjectName("indicator")
        self.button_layout.addWidget(self.packs_opened, 20)

        self.button_layout.addStretch(2)

        self.current_pack = QLabel("Current Pack: ")
        self.current_pack.setObjectName("indicator")
        self.button_layout.addWidget(self.current_pack, 20)

        self.button_layout.addStretch(60)

        self.next_button = QPushButton("Start")
        self.next_button.pressed.connect(self.sel_next_set)
        self.button_layout.addWidget(self.next_button)

        self.picked_cards: list[CardButton] = []

        self.main_layout.addLayout(self.button_layout)

        self.setLayout(self.main_layout)

        self.sel_next_set()

    def sel_next_set(self):
        """Selects the next pack and also manages the drafting session in
        general.

        1. Will check if there have been enough enough cards selected.
        1a. Returns back to the selection with a warning popup.
        2b. Otherwise it will add the selected cards to the deck.
        3. Check if its a discard stage and trigger the dialog for that if the
           pack count is divisable by 10.
        4. Checks everytime if there have been 4 discard stages and ask the
           user if they want to preview the deck and continue on to save the
           deck.
        5. Removes the current cards from the layout.
        6. Selects the next pack and decrements the count.
        7. Generates the probabilities for the base cards in the set.
        8. Finally opens the pack by calling open_pack()
        """

        if hasattr(self, "stretch"):
            self.main_layout.removeItem(self.stretch)
            del self.stretch

        if self.selection_per_pack > 0:
            text = f"Select at least {self.selection_per_pack} more cards."
            logging.error(text)
            QMessageBox.warning(self, "Select More Cards", text,
                                QMessageBox.StandardButton.Ok)
            return

        if self.picked_cards:
            self.add_card_to_deck()

        if self.total_packs % 10 == 0 and self.total_packs:
            self.discard_stage()
            self.selection_per_pack = 0

        self.next_button.setText("Next")

        if self.discard_stage_cnt == 4:
            logging.error("Selection complete!")
            msg_class = QMessageBox
            mbutton = msg_class.StandardButton
            ms_box = msg_class.information(
                self,
                "Deck Drafting Complete",
                "Would you like to preview the deck?",
                (mbutton.No | mbutton.Yes))

            if ms_box == mbutton.Yes:
                self.check_deck()

            self.accept()

        if self.card_buttons:
            self.clean_layout()

        sel_packs = self.parent().selected_packs

        next_key = list(sel_packs.keys())[self.opened_set_packs]
        set_data = sel_packs[next_key]

        self.total_packs += 1
        self.packs_opened.setText(f"Pack No.: {self.total_packs}")
        self.current_pack.setText("Current Pack: %s" % set_data.set_name)

        if not set_data.probabilities:
            card_data = self.ygo_data.get_card_set_info(set_data)
            set_data.card_set = card_data
            probabilities = self.generate_weights(next_key, card_data)
            set_data.probabilities = tuple(probabilities)

        if self.total_packs % 10 == 0 and self.total_packs != 0:
            self.next_button.setText("Discard Stage")

        self.open_pack(set_data.card_set, set_data.probabilities, set_data)
        set_data.count -= 1

        if set_data.count == 0:
            self.opened_set_packs += 1

    def add_card_to_deck(self):
        for cardbutton in list(self.picked_cards):
            self.card_layout.removeWidget(cardbutton)

            card = cardbutton.card_model
            cardbutton.deleteLater()

            if self.ygo_data.check_extra_monster(card):
                self.extra_deck.append(card)
                continue

            self.main_deck.append(card)

        self.update_counter_label()

    def generate_weights(self, card_set_name: str, data: list[YGOCard],
                         extra: bool = False) -> tuple[int, ...]:
        """
        >>> Generate a list of integers depeding on the weight denoting the
            index of an item inside the set cards.
        >>> The Extra[bool] value is if you want to skip the common cards in
            order to weight the last card in a pack.
        """

        PROB = {
            "Common": 80,
            "Rare": 16.6667,
            "Super Rare": 8.3334,
            "Ultra Rare": 4.3478260870,
            "Secret": 2.8571428571,
        }

        probabilities = []

        for card_model in data:
            card = card_model.raw_data
            card_sets = card["card_sets"]
            for card_set in card_sets:
                if card_set["set_name"] != card_set_name:
                    continue

                rarity_name = card_set["set_rarity"]
                if rarity_name == "Common" and extra:
                    break

                card["set_rarity"] = rarity_name

                rarity = round(PROB.get(rarity_name, 2.8571428571))
                probabilities.append(rarity)
                break

        return tuple(probabilities)

    def clean_layout(self):
        """
        >>> Cleans the pack Card Layout in order to add the open the next pack.
        >>> *Might have to look a the function in the in order to determine
            if I am not having a issues with this approach.
        >>> *Could also be combined with the adding cards function in order to
            make a smoother operation.
        """
        util.clean_layout(self.card_layout)

        for _ in range(len(self.picked_cards)):
            card = self.picked_cards.pop(0)
            card.deleteLater()
            del card

        for _ in range(len(self.card_buttons)):
            card = self.card_buttons.pop(0)
            card.deleteLater()
            del card

        self.repaint()
        QApplication.processEvents()

    def filter_common(self, card: YGOCard):
        return card.rarity != "Common"

    def open_pack(self,
                  card_set: list[YGOCard],
                  probablities: tuple[int, ...],
                  set_data: YGOCardSet):
        """
        >>> Opens a pack with probablities supplied and adds its to the layout.
        >>> The last card get new probabilities as its atleast a rare.
        >>> *refactor this in the future too make probability calculations
            easier.
        """

        (logging
         .debug(f"Opening a pack from {set_data.set_name}.".center(60, "-")))

        self.selection_per_pack += 2
        logging.debug(f"{self.selection_per_pack} Cards Plus Available.")
        self.update_counter_label()

        row = 0
        for column in range(self.CARDS_PER_PACK):
            if column == 8:
                rare_cards = list(filter(self.filter_common, card_set))
                prob = self.generate_weights(set_data.set_name, rare_cards,
                                             extra=True)
                card_data = random.choices(rare_cards, weights=prob, k=1)
            else:
                card_data = random.choices(card_set, weights=probablities, k=1)

            row = 0
            if column % 2 != 0:
                QApplication.processEvents()
                row = 1
                column -= 1

            card = CardButton(card_data[0], self)

            self.card_buttons.append(card)
            card.toggled.connect(self.update_selection)
            self.card_layout.addWidget(card, row, column, 1, 1)

        self.repaint()

    def parent(self) -> MainWindow:
        return super().parent()  # type: ignore

    def accept(self):
        self.deck = DeckModel(self.deck_name, self.main_deck,
                              self.extra_deck, self.side_deck)

        return super().accept()

    def update_selection(self):
        logging.debug("Updating Selection")

        for item in list(self.card_buttons):
            item.blockSignals(True)

            item_in = item in self.picked_cards

            fus_monster = self.ygo_data.check_extra_monster(item.card_model)
            three = self.check_dup_card_count(item.card_model) == 3

            if (item.isChecked()
               and not three
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
        picked = len(self.main_deck) + len(self.side_deck)
        self.cards_picked.setText(f"Deck Total: {picked}")
        tip = f"Main Deck: {len(self.main_deck)}\n"
        tip += f"Extra Deck: {len(self.extra_deck)}\n"
        tip += f"Side Deck: {len(self.side_deck)}"
        self.cards_picked.setToolTip(tip)

    def check_dup_card_count(self, card: YGOCard) -> int:
        count = 0

        def count_cards(card, deck) -> int:
            count = 0
            for item in deck:
                if item.name == card.name:
                    count += 1
            return count

        count += count_cards(card, self.main_deck)
        count += count_cards(card, self.extra_deck)
        count += count_cards(card, self.side_deck)

        for item in self.picked_cards:
            if item.accessibleName() == card.name:
                count += 1

        return count

    def discard_stage(self):
        """Calculates the amount to be discarded and starts the dialog."""

        discard = self.total_packs + (self.total_packs // 5)
        dialog = DeckViewer(self, discard)

        dialog.setWindowTitle("Card Removal Stage")

        if dialog.exec():
            self.main_deck = dialog.new_deck
            self.extra_deck = dialog.new_extra
            self.side_deck = dialog.new_side

            self.discard_stage_cnt += 1

    def check_deck(self):
        deck = DeckViewer(self)
        deck.exec()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return super().keyPressEvent(event)
        KEY = Qt.Key
        if (event.key() in {KEY.Key_Escape, KEY.Key_Space}):
            return

        return super().keyPressEvent(event)

    def resizeEvent(self, event: QResizeEvent | None):
        QApplication.processEvents()
        return super().resizeEvent(event)


class CardButton(QPushButton):
    """Card class used for displaying, deleting and containg cards.

        Has some functions to search and locate assocciated cards aswell.
        Future refactor might include moving some functions out and refining
        the paint event.

        Attributes:
            BASE_SIZE (QSize): Minimum size of the card for readibility.
            ASPECT_RATION (float): Ratio of the card that allows for smooth
                scaling.
            card_model (YGOCard): Holds all the metadata of the card itself.
            image (QPixmap): Holds the cover art inside an image.

        Args:
            data (YGOCard): Card data itself with the set_data prefilled.
            parent (DraftingDialog): Dialog where the drafting is being done
                for accessing additonal information.
            viwer (DeckViewer): Optional argument if slotting it into a
                DeckViewer dialog, which enables different functionality
                in terms of menu and draggability.

    """
    BASE_SIZE = QSize(164, 242)
    ASPECT_RATIO: Final[float] = 1.4756097561  # Height to Width

    def __init__(self, data: YGOCard, parent: DraftingDialog,
                 viewer: Optional['DeckViewer'] = None) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if isinstance(viewer, DeckViewer):
            self.setAcceptDrops(True)

        self.viewer = viewer  # type: ignore
        self.card_model = data

        self.setAccessibleName(data.name)
        self.setAccessibleDescription(data.description)

        self.setBaseSize(self.BASE_SIZE)
        desc = util.new_line_text(data.description, 100)

        self.setToolTip(data.name + "\n" + desc)
        self.setObjectName("card_button")

        QSP = QSizePolicy.Policy

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)

        self.setSizePolicy(QSP.Expanding, QSP.Expanding)
        self.setCheckable(True)

        self.assocc = self.filter_assocciated()

        self.image = parent.ygo_data.get_card_art(self.card_model)

    def minimumSize(self) -> QSize:
        """Overriden minimum size of the card widget in order to stay legible

        Returns:
            A QSize item desribes the minimum size of the widget.
        """
        return self.BASE_SIZE

    def sizeHint(self) -> QSize:
        """Size Hint to keep the the card widget in proportion.

        Returns:
            QSize: Based on the proportions set by the constant ASPECT_RATIO.
        """
        width = self.minimumSize().width()
        size = QSize(width, self.heightForWidth(width))
        return size

    def heightForWidth(self, width: int) -> int:
        """Return a height for the widget depending on the width."""
        return round(width * self.ASPECT_RATIO)

    def filter_assocciated(self) -> set:
        """Filters out asscciated cards for quick adding with the submenu.

        Returns:
            set: Names of the cards assocciated with this instance.
                 *At the moment it will return anything that matches, but in
                 reality it should check if cards exists in order to avoid
                 confusion.
        """
        pattern = re.compile(r'(?<!\\)"(.*?[^\\])"')
        matches = re.findall(pattern, self.accessibleDescription())
        return set(matches)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        """Overriden PaintEvent for painting the card art and additonal
           effects.

           Override the drawing/painting process completely unless the image
           is missing.

        Args:
            event (QPaintEvent | None): PaintEvent called from the gui loop or
                somewhere else.
        """
        if event is None or self.image is None:
            return super().paintEvent(event)

        option = QStyleOptionButton()
        option.initFrom(self)

        rect = event.rect()
        # height = rect.height()

        painter = QPainter(self)
        HINT = QPainter.RenderHint
        painter.setRenderHints(HINT.LosslessImageRendering |
                               HINT.Antialiasing)
        image = self.image.scaled(self.width(), self.height(),
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)

        if not self.isEnabled():
            image = image.toImage()
            grayscale = image.convertToFormat(QImage.Format.Format_Grayscale8)
            image = QPixmap.fromImage(grayscale)

        brush = QBrush(image)
        painter.setBrush(brush)

        # RADIUS = 10

        PEN_WIDTH = 5
        assert PEN_WIDTH % 2 != 0
        PEN_HALF = PEN_WIDTH / 2
        new_rect = QRectF(rect.x(), rect.y() + PEN_HALF,
                          image.width(), image.height())
        if self.isChecked():
            PEN_WIDTH *= 1.25
            pen = QPen(Qt.GlobalColor.red)
            pen.setWidthF(PEN_WIDTH)
            painter.setPen(pen)

        elif option.state & QStyle.StateFlag.State_MouseOver:
            pen = QPen(Qt.GlobalColor.yellow)
            pen.setWidth(PEN_WIDTH)
            painter.setPen(pen)
        elif self.card_model.rarity != "Common":
            painter.setOpacity(0.8)
            pen = QPen(Qt.GlobalColor.darkMagenta)
            pen.setCosmetic(True)
            pen.setWidth(PEN_WIDTH)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        painter.drawRect(new_rect)
        painter.setOpacity(1)

        if not self.isChecked():
            return
        if isinstance(self.viewer, DeckViewer) and self.viewer.discard:
            rect = self.rect()
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topRight())

    def show_menu(self) -> None:
        """Submenu event which spawn a dropdown menu at the cursor location.

        Create a varied menu depending if its inside the DraftingDialog
          or the deckviewer

        DraftingDialog:
            Adding Assocciated Cards/Fusion Material
        DeckViewer:
            If its not a discard stage there is no menu, otherwise movement or
            deletion buttons.

        """
        pos = QCursor().pos()
        menu = QMenu(self)

        if isinstance(self.viewer, DeckViewer):
            if not self.viewer.discard:
                return
            self.discard_stage_menu(menu)
        else:
            if self.parent().selection_per_pack < 1:
                return

            self.drafting_menu(menu)

        menu.exec(pos)

    def drafting_menu(self, menu: QMenu) -> None:
        """Menu that pop ups when drafting the deck."""
        if self.card_model.card_type == "Fusion Monster":
            poly = "Polymerization"

            if self.parent().selection_per_pack > 1:
                fusion = menu.addAction("Add All Fusion Parts")
                fusion.triggered.connect(self.add_all_assocc)  # type: ignore

            poly_add = menu.addAction("Add Polymerization")
            (poly_add.triggered  # type: ignore
             .connect(lambda: self.add_assocc(poly)))

            for item in self.assocc:
                acc = menu.addAction(f"Add {item}")
                (acc.triggered  # type: ignore
                 .connect(partial(self.add_assocc, item)))

        else:
            for item in self.assocc:
                acc = menu.addAction(f"Add {item}")
                (acc.triggered  # type: ignore
                 .connect(partial(self.add_assocc, item)))
            if self.assocc:
                acc = menu.addAction("Add all Assocciated")
                acc.triggered.connect(self.add_all_assocc)  # type: ignore
            else:
                return

    def discard_stage_menu(self, menu: QMenu) -> None:
        """Menu that pop ups when in the discard stage of drafting."""

        self.viewer: DeckViewer
        if self.isChecked():
            card_state = "Keep Card"
        else:
            card_state = "Discard Card"
        card_state_change = menu.addAction(card_state)
        if card_state_change is not None:
            card_state_change.triggered.connect(self.toggle)

        mv_deck = self.viewer.mv_card

        if self in self.viewer.deck:
            mv_main = f"Move {self.accessibleName()} to Side Deck"
            mv_to_side = menu.addAction(mv_main)
            (mv_to_side.triggered  # type: ignore
             .connect(lambda: mv_deck(self, "side")))

        elif self in self.viewer.side:
            mv_main = f"Move {self.accessibleName()} to Main Deck"
            mv_to_mn = menu.addAction(mv_main)
            (mv_to_mn.triggered  # type: ignore
             .connect(lambda: mv_deck(self, "main")))

    def add_all_assocc(self) -> None:
        """Adds all assocciated cards present within the assocc instance
           variable.

           If the monster belongs in the extra deck a Polymerization gets
           added to the deck.
        """
        self.setChecked(True)
        self.setDisabled(True)

        items = list(self.assocc)
        if self.parent().ygo_data.check_extra_monster(self.card_model):
            # Need to confirm this as different extra deck monster might need
            # different material
            poly = "Polymerization"
            items.append(poly)

        self.get_card(self.assocc)

    def add_assocc(self, card_name: str) -> None:
        """Adds a single assocciated card to the selected cards.

        Args:
            card_name (str): Which card to add to the deck as it will get
                searched by subsequent functions.
        """
        self.setChecked(True)
        self.setDisabled(True)
        self.get_card(card_name)

    def get_card(self, card_name: str | list | set) -> None:
        """Collects a card with the help of a YGO data model object.

        Args:
            card_name (str | list | set): Card Name which can be multiple cards
                if inside in an Iterable.

        Raises:
            FileNotFoundError: If there is no card found inside the YGOProDeck
                database.
        """

        if isinstance(card_name, (list, set)):
            for item in card_name:
                self.get_card(item)
            return

        data = self.parent().ygo_data.grab_card(card_name)
        if data is None:
            raise FileNotFoundError("Card does not exist.")
        logging.info(f"Adding {card_name} to selection.")

        try:
            card_set = self.card_model.card_set
            c_mdl = self.parent().ygo_data.create_card(data[0], card_set)
        except KeyError:
            return

        self.add_card(c_mdl)

    def add_card(self, card: YGOCard) -> None:
        """Adds a card to the deck list.

        If three of the same card exist inside the deck the card gets ignored.

        Args:
            card (YGOCard): Model of the card to be added.
        """
        if self.parent().check_dup_card_count(card) == 3:
            logging.error(f"Three {card.name} cards in deck.")
            return

        self.parent().main_deck.append(card)
        if card.card_type != "Fusion Monster":
            self.parent().selection_per_pack -= 1
        self.parent().update_counter_label()

    def parent(self) -> DraftingDialog:
        """Override to clear typing issues when calling this function."""
        return super().parent()  # type: ignore

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Movement function for when dragging cards between decks."""
        if self.viewer is None:
            return
        if event.buttons() == Qt.MouseButton.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            drag.setMimeData(mime)

            pixmap = QPixmap(self.size())
            self.render(pixmap)
            drag.setPixmap(pixmap)

            drag.exec(Qt.DropAction.MoveAction)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        """Resize event to set the minimum size of an object."""
        self.setMinimumSize(self.sizeHint())
        return super().resizeEvent(event)


class DeckViewer(QDialog):
    """Deck viewer window for previewing and managing the deck through the
       drafting phases.

    Attributes:
        side/extra/deck (list): Existing cards that are generated by the fill
            deck classmethod.
        discard (int): How many cards are to be discarded.
            *Used as a boolean check whether its just a viewer or interactive
             stage as well.
        side_length (int): How many cards belong in the side deck.
            *Calculated from existing length of the side deck.
        MAX_COLUMNS: (int): The amount of columns to be used when displaying
            cards

    Args:
        parent (DraftingDialog): Parent where the deck is/was being drafting.
        discard (int): How many cards should be discounted
    """

    MAX_COLUMNS: Final[int] = 10

    def __init__(self, parent: DraftingDialog, discard: int = 0):
        super().__init__(parent)

        self.setWindowTitle("Deck Viewer")
        self.resize(1745, 860)  # Base on 1080 ratio

        self.discard = discard
        self.side_length = len(parent.side_deck) + 2

        self.deck: list[CardButton] = []
        self.extra: list[CardButton] = []
        self.side: list[CardButton] = []

        self.main_layout = QVBoxLayout()

        self.deck_area = DeckSlider("Main Deck", self)
        self.main_layout.addWidget(self.deck_area, 60)
        self.fill_deck(parent.main_deck, self.deck, self.deck_area)

        self.extra_deck_widget = DeckSlider("Extra Deck", self)
        self.main_layout.addWidget(self.extra_deck_widget, 20)
        self.fill_deck(parent.extra_deck, self.extra, self.extra_deck_widget)

        self.side_deck_widget = DeckSlider("Side Deck", self)
        self.main_layout.addWidget(self.side_deck_widget, 20)
        self.fill_deck(parent.side_deck, self.side, self.side_deck_widget)

        self.button_layout = QHBoxLayout()

        if discard:
            self.removal_counter = QLabel()
            self.removal_counter.setObjectName("indicator")
            self.button_layout.addWidget(self.removal_counter)

        self.main_deck_count = QLabel()
        self.main_deck_count.setObjectName("indicator")
        self.button_layout.addWidget(self.main_deck_count)

        self.extra_deck_count = QLabel()
        self.extra_deck_count.setObjectName("indicator")
        self.button_layout.addWidget(self.extra_deck_count)

        self.side_deck_count = QLabel()
        self.side_deck_count.setObjectName("indicator")
        self.button_layout.addWidget(self.side_deck_count)

        self.removal_count()

        self.button_layout.addStretch(50)

        self.accept_button = QPushButton("Accept")
        self.accept_button.pressed.connect(self.accept)
        self.button_layout.addWidget(self.accept_button)

        self.main_layout.addLayout(self.button_layout)

        self.setLayout(self.main_layout)

    def fill_deck(self, cards: list[YGOCard], container: list,
                  scroll_bar: 'DeckSlider', check: bool = False) -> None:
        """Fills the deck preview with the list of given list[YGOCards].

            Also checks if an item has been previously checked as the func
                is used for moving cards between main and side decks as well.

            Args:
                cards (list): The list of cards to be added to the layout
                container (list): Where to put the Card Widgets for storage.
                scrollbar (QScrollView): What widget the cards will be added to
                    *Will extract the scrollvbars and layout from the widget.
                check (bool): If moving whether to recheck the QPushButton.
        """

        layout = scroll_bar.main_layout
        cards = cards.copy()
        if isinstance(layout, QHBoxLayout):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if isinstance(item, QSpacerItem):
                    layout.removeItem(item)

        QSP = QSizePolicy.Policy
        QAF = Qt.AlignmentFlag
        row = 0
        column = 0
        while cards:
            if column % self.MAX_COLUMNS == 0 and column:
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

            if isinstance(scroll_bar, QScrollArea):
                vscroll = scroll_bar.verticalScrollBar()
                if vscroll is not None:
                    vscroll.valueChanged.connect(card_button.repaint)
                hscroll = scroll_bar.horizontalScrollBar()
                if hscroll is not None:
                    hscroll.valueChanged.connect(card_button.repaint)

            if not self.discard:
                card_button.setCheckable(False)
            else:
                card_button.toggled.connect(self.removal_count)
                card_button.setChecked(check)

            card_button.setSizePolicy(QSP.Fixed, QSP.Fixed)
            container.append(card_button)
            if isinstance(layout, QHBoxLayout):
                layout.addWidget(card_button)
                continue

            layout.addWidget(card_button, row, column,
                             QAF.AlignJustify)  # type: ignore
            column += 1

        if isinstance(layout, QHBoxLayout):
            layout.insertStretch(-1, 1)

    def mv_card(self, card: CardButton, deck: Literal["main", "side"]):
        """Moves a card[CardButton] between the side and main deck.

           To be called from the card (CardButton):show_menu method itself
           and assigns itself for movement.

           Args:
                card (CardButton): The card to be moved.
                deck (CardButton): Which deck the card will be moved to.
        """
        card.deleteLater()

        if deck == "main":
            side_idx = self.side.index(card)
            item = self.side.pop(side_idx)

            self.fill_deck([item.card_model], self.deck, self.deck_area,
                           card.isChecked())

        elif deck == "side":
            main_idx = self.deck.index(card)
            item = self.deck.pop(main_idx)
            self.fill_deck([item.card_model], self.side, self.side_deck_widget,
                           card.isChecked())

        if self.discard:
            self.removal_count()

    def parent(self) -> DraftingDialog:
        """Overriden to avoid type hint issues."""
        return super().parent()  # type: ignore

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Overriden to prevent the user from accidently quitting the
           application if there are a lot of problems."""

        if event is None:
            return super().keyPressEvent(event)

        KEY = Qt.Key
        if (event.key() in {KEY.Key_Escape, KEY.Key_Space} and self.discard):
            return

        return super().keyPressEvent(event)

    def count(self, target: Literal["both", "main", "side"] = "both") -> int:
        """Returns the count of the deck picked > target[str] with the
           checked cards marked for removal as discarded.

            Args:
                target (str): If just checking for just one deck count this is
                    used to filter those out.

            Returns:
                int: Target count as an in value.
        """

        def cnt(deck: list[CardButton]):
            sub_count = 0
            for item in deck:
                if not item.isChecked():
                    sub_count += 1

            return sub_count

        count = 0
        if target in {"both", "main"}:
            count += cnt(self.deck)

        if target in {"both", "side"}:
            count += cnt(self.side)

        return count

    @pyqtSlot()
    def removal_count(self) -> None:
        """Updates the counters for removal, main, side and extra deck."""
        if self.discard:
            discardcount = self.count() - self.discard
            self.removal_counter.setText(f"Remove: {discardcount}")

        mcount = self.count("main")
        with QSignalBlocker(self.main_deck_count):
            self.main_deck_count.setText("Main Deck: %s" % mcount)

        extra = len(self.extra)
        with QSignalBlocker(self.extra_deck_count):
            self.extra_deck_count.setText("Extra Deck: %s" % extra)

        side = self.count("side")
        with QSignalBlocker(self.side_deck_count):
            self.side_deck_count.setText("Side Deck: %s" % side)

    def accept(self) -> None:
        """Overriden accept function to check if there are the right amount of
           cards in each deck and validate the entries.

           Will check if Main & Side deck counts are at the right numbers
            according instance.discard and instance.side_length.
        """
        if not self.discard:
            self.deleteLater()
            return self.hide()

        def filter_items(container: list, source: list[CardButton]):
            for item in list(source):
                if not item.isChecked():
                    container.append(item.card_model)
                    continue
                item.deleteLater()

        logging.debug("Deck Cards: %s", len(self.deck))
        logging.debug("Extra Cards: %s", len(self.extra))
        logging.debug("Side Cards: %s", len(self.side))
        count = self.count()
        logging.debug("Actual Count: %s", count)

        if count != self.discard:
            cnt = count - self.discard
            operation, cnt = util.get_operation(cnt)

            QMessageBox.warning(self, f"{operation} More Cards",
                                f"{operation} {cnt} more card(s)",
                                QMessageBox.StandardButton.Ok)
            return

        elif self.count("side") != self.side_length:
            cnt = self.count("side") - self.side_length
            operation, cnt = util.get_operation(cnt)
            msg = f"{operation} {cnt} more card(s) to the Side Deck"
            if operation == "Remove":
                msg = f"{operation} {cnt} more card(s) from the Side Deck"
            QMessageBox.warning(self, "Adjust Side Deck", msg,
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
    """Widget for sliding the deck around inside the deck viewer window.

    Attributes:
        main_widget (DeckDragWidget | DeckWidget): For displaying and laying
            out the cards.
        main_layout (QLayout): Where the card widgets will be slotted into.

    Args:
        deck_type (str): What kind of deck it is for labeling.
        parent (DeckViewer): The window this widget will displayed on.
    """

    def __init__(self,
                 deck_type: Literal["Main Deck", "Side Deck", "Extra Deck"],
                 parent: DeckViewer) -> None:
        super().__init__(parent)

        QAF = Qt.AlignmentFlag
        SBP = Qt.ScrollBarPolicy
        self.setHorizontalScrollBarPolicy(SBP.ScrollBarAsNeeded)

        if deck_type != "Main Deck":
            self.main_widget = DeckDragWidget(deck_type, self)
            self.main_layout = self.main_widget.main_layout

            self.setWidgetResizable(True)
            self.setVerticalScrollBarPolicy(SBP.ScrollBarAlwaysOff)
        else:
            self.setVerticalScrollBarPolicy(SBP.ScrollBarAlwaysOn)
            self.main_widget = DeckWidget(deck_type, self)
            self.main_layout = QGridLayout(self)
            self.main_layout.setAlignment(QAF.AlignTop | QAF.AlignLeft)
            self.main_widget.setLayout(self.main_layout)
            self.setWidgetResizable(True)

        self.setWidget(self.main_widget)

        vscroll = self.verticalScrollBar()
        if vscroll is not None:
            vscroll.valueChanged.connect(self.main_widget.repaint)
        hscroll = self.horizontalScrollBar()
        if hscroll is not None:
            hscroll.valueChanged.connect(self.main_widget.repaint)


class DeckWidget(QWidget):
    """Basic Deck Widget for attaching to a scrolling.

    Reimplements the QSizePolicy and repaints the background with the
    decktype.
    Layout management happens within a child or parent class of this class.

    Args:
        deck_type (str): Type of Deck {Side/Extra/Main} for label purposes.
        parent (DeckSlider): to access and manage the layout within the
                             DeckViewer and allow scrolling the layout
    """

    def __init__(self, deck_type: str, parent: DeckSlider):
        super().__init__(parent)
        self.scroll_area = parent
        self.name = deck_type
        QSP = QSizePolicy.Policy

        self.setSizePolicy(QSP.Minimum, QSP.Minimum)

    def paintEvent(self, event: QPaintEvent | None):
        """Draws the basic paint event of the widget.

        Extended with a QPainter in order to draw the deck name on the
        center of the viewport background adjusting for scrolled distance.

        Args:
            event (QPaintEvent | None): Builtin QWidget paint event to refresh
                                        and find out which area needs rerender.
        """
        super().paintEvent(event)
        if event is None:
            return

        viewport = self.scroll_area.viewport()
        if viewport is None:
            return

        pos = viewport.pos()

        vscroll = self.scroll_area.verticalScrollBar()
        if vscroll is not None:
            pos.setY(pos.y() + vscroll.value())
        hscroll = self.scroll_area.horizontalScrollBar()
        if hscroll is not None:
            pos.setX(pos.x() + hscroll.value())

        new_rect = QRect(pos, event.rect().size())

        painter = QPainter(self)

        font = QFont()
        font.setItalic(True)
        font.setPixelSize(36)
        painter.setFont(font)

        painter.setOpacity(0.1)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(new_rect, (Qt.TextFlag.TextWordWrap
                         | Qt.AlignmentFlag.AlignCenter),
                         self.name)


class DeckDragWidget(DeckWidget):
    """Widget for visually managing dragging cards around the layouts.

    Not fully implemented with to enable dragging cards at the moment.

    Args:
        deck_type (str): Type of deck {Side/Extra/Main} for label purposes.
        parent (DeckSlider): To access and manage the layout within the
                             DeckViewer and allow scrolling the layout
        orientation (Qt.Orientation): For choosing which directions the cards
                                      slide.
    """

    orderChanged = pyqtSignal()

    def __init__(self, deck_type: str, parent: DeckSlider,
                 orientation=Qt.Orientation.Horizontal):
        super(DeckDragWidget, self).__init__(deck_type, parent)
        self.name = deck_type
        self.setAcceptDrops(True)
        self.orientation = orientation

        self.main_layout = QHBoxLayout()
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.setLayout(self.main_layout)

    def add_drag_widget(self, card: CardButton):
        """Adds a card to the layout.

        Args:
            card (CardButton): Card widget to be added to the layout.
        """
        self.main_layout.addWidget(card)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Event Manager for a widget dragged around the layout."""
        event.accept()

    def dropEvent(self, event: QDropEvent | None):
        """Checks for a drop event and the position in order to choose where
           to put the widget.

        Args:
            event (QDropEvent): Event produced by the widget getting dragged
                                around.
        """

        if event is None:
            return
        pos = event.position()

        for n in range(self.main_layout.count()):
            item = self.main_layout.itemAt(n)

            widget = util.check_item_validation(item)
            if widget is None:
                continue

            if self.orientation == Qt.Orientation.Vertical:
                drop_here = pos.y() < widget.y() + widget.size().height() // 2
            else:
                drop_here = pos.x() < widget.x() + widget.size().width() // 2

            if drop_here:
                self.main_layout.insertWidget(n - 1, widget)
                self.orderChanged.emit()
                break

        event.accept()

    @pyqtSlot(int)
    def delete_widget(self, widget: CardButton):
        """Removes the widget provided form the layout.

        Removes a widget and notifies sends out a signal about the order
        changing.

        Args:
            widget (CardButton): Widget to be removed from its layout.
        """
        widget.deleteLater()
        widget.setParent(None)  # type: ignore
        self.orderChanged.emit()
