"""deck_drafter.py

Main GUI modules that manages information display and drafting rules.


Classes:
    AspectRatio: Basic NamedTuple for storing card aspect ratio.
    PackOpeningState: Main DataModel for storing drafting information and
        progression.
    DraftingDialog: Main class that manages the GUI and drafting progression.
        Everything else parents to this except the main window.
    CardButton: Button subclass for making cards interactive and visually
        useful.
    DeckViewer: Main widget for displaying the drafted deck and managing
        discard stages.
    DeckSlider/DeckWidget/CardLayout: For managing and displaying readble card
        layouts.
    CardSearch: GUI for searching for extra deck materials.

Usages:
    Instatiate DraftingDialog with the correct args and proceed from there
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Final, NamedTuple, Optional

import logging
import math
import random
import enum
from pathlib import Path
from dataclasses import dataclass, field
from functools import partial

from PyQt6.QtCore import (QMimeData, QPoint, QRect, QRectF, QSignalBlocker,
                          QSize, Qt, pyqtSignal, pyqtSlot)

from PyQt6.QtGui import (QBrush, QCursor, QDrag, QDragEnterEvent, QCloseEvent,
                         QDropEvent, QFont, QImage, QKeyEvent, QMouseEvent,
                         QPainter, QPaintEvent, QPen, QPixmap, QAction)

from PyQt6.QtWidgets import (QApplication, QCompleter, QDialog, QHBoxLayout,
                             QLabel, QLayout, QLayoutItem, QLineEdit, QMenu,
                             QMessageBox, QProgressBar, QPushButton,
                             QScrollArea, QSizePolicy, QWidget, QStackedWidget,
                             QStyle, QStyleOptionButton, QVBoxLayout,
                             QProgressDialog)

from yugioh_deck_drafter import util
from yugioh_deck_drafter.modules.ygo_data import (CardModel, CardSetModel,
                                                  DeckModel, DeckType,
                                                  CardType, ExtraMaterial,
                                                  DamageValues)

if TYPE_CHECKING:
    from yugioh_deck_drafter.__main__ import MainWindow


class AspectRatio(NamedTuple):
    """Aspect ratio for resizing widgets properly."""
    width: float = 1.0
    height: float = 1.0


@dataclass
class PackOpeningState:
    """Needed data for drafting decks with the Drafting Dialog.

    Attributes:
        opened_set_packs (int): Keeps track of how many pack bundles have been
            opened so far.
        total_packs (int): The total number of packs that have been opened so
            far.
        selection_per_pack (int): How many max selections the current pack has.
        selections_left (int): Counter for how many selections the drafter
            has left for the current pack. Must be 0 or less to proceed through
            the drafting process.
        discard_stage_cnt (int): How many discard stages have occured, mainly
            to trigger deck completion.
        selection (list): Where the current selections are stored and delegated
            from later on.
    """
    opened_set_packs: int = field(default=0)
    total_packs: int = field(default=0)
    selection_per_pack: int = field(default=0)
    selections_left: int = field(default=0)
    discard_stage_cnt: int = field(default=0)
    selections: list[CardButton | CardModel] = field(default_factory=list)


class DraftingDialog(QDialog):
    """Dialog for opening packs and managing drafting in general, as it has a
    core function that cycles and keep track of whats been added and removed in
    the meanwhile.

    Attributes:
        CARDS_PER_PACK (int): How many cards each pack contains.
        deck (DeckModel): Mostly for storing the selected card data and
            tranferring between widgets.
        drafting_model (DeckModel): Holds important drafting information for
            checking different stages of the drafting process.

    Args:
        parent (MainWindow): For retrieving, managing and finalzing the
            drafting data.
        deck_name (str): Name of deck set by the user used for save pathh name
            later on.
        flags (Optional[WindowType]): Mostly for debugging.
        SET_ART_SIZE (QSize): For having a consistent size for set art when
            loading.
    """
    SET_ART_SIZE: Final[QSize] = QSize(400, 708)
    CARDS_PER_PACK: Final[int] = 9

    def __init__(
        self,
        parent: MainWindow, deck_name: str,
        flags=Qt.WindowType.Dialog
    ) -> None:
        super().__init__(parent, flags)
        self.setModal(not parent.debug)

        self.setWindowTitle("Card Pack Opener")

        self.ygo_data = self.parent().yugi_pro

        self.deck = DeckModel(deck_name)
        self.drafting_model = PackOpeningState()
        self.setSizePolicy(QSizePolicy.Policy.Minimum,
                           QSizePolicy.Policy.Minimum)
        self.resize(self.minimumSize())

        self.init_ui()

    def init_ui(self) -> None:
        """Intializes layouts and widgets for the UI."""
        self.pack_filter = None

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(self.main_layout)
        self.view_widget = QStackedWidget()
        self.main_layout.addWidget(self.view_widget)

        self.drafting_widget = self.setup_drafting_widget()
        self.view_widget.addWidget(self.drafting_widget)

        self.loading_widget = self.setup_loading_widget()
        self.view_widget.addWidget(self.loading_widget)

    def setup_loading_widget(self) -> QWidget:
        """Lays outs widgets for displaying loading information to the user.

        Returns:
            QWidget: Return the main loading widget so it can be added to the
                dialog view widget.
        """
        self.loading_widget = QWidget()
        self.loading_layout = QHBoxLayout()

        QAF = Qt.AlignmentFlag

        self.set_layout = QVBoxLayout()

        self.set_art_widget = QLabel()
        self.set_art_widget.setSizePolicy(QSizePolicy.Policy.Minimum,
                                          QSizePolicy.Policy.Minimum)
        self.set_art_widget.setAlignment(QAF.AlignHCenter | QAF.AlignBottom)
        self.set_layout.addWidget(self.set_art_widget, 70)
        self.set_art_widget.setMaximumSize(self.SET_ART_SIZE)

        self.set_name_label = QLabel("Set")
        self.set_name_label.setObjectName("subtitle")
        self.set_name_label.setAlignment(QAF.AlignTop | QAF.AlignHCenter)
        self.set_layout.addWidget(self.set_name_label, 20)

        self.loading_layout.addLayout(self.set_layout, 30)

        self.progess_layout = QVBoxLayout()

        self.loading_label = QLabel("Loading")
        self.loading_label.setObjectName("subtitle")
        self.loading_label.setAlignment(QAF.AlignHCenter | QAF.AlignBottom)
        self.progess_layout.addWidget(self.loading_label, 50)

        self.loading_bar = QProgressBar()
        self.loading_bar.setAlignment(QAF.AlignCenter)
        self.loading_bar.setMinimum(0)
        self.loading_bar.setMaximum(9)
        self.loading_bar.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Preferred)
        self.progess_layout.addWidget(self.loading_bar, 50, QAF.AlignTop)

        self.loading_layout.addLayout(self.progess_layout, 70)

        self.loading_widget.setLayout(self.loading_layout)
        return self.loading_widget

    def setup_drafting_widget(self) -> QWidget:
        """Drafting widget where most of the card packs are usually opened.

        Returns:
            QWidget: Returns the drafting widget to be added to the view.
        """
        self.drafting_widget = QWidget()

        self.drafting_layout = QVBoxLayout()
        self.drafting_layout.addStretch(1)
        self.stretch = self.drafting_layout.itemAt(0)

        self.card_layout = CardLayout(parent=self.drafting_layout, rows=2)
        self.drafting_layout.addLayout(self.card_layout)

        self.card_buttons: list[CardButton] = []  # Contains the card widgets

        self.button_layout = QHBoxLayout()

        self.check_deck_button = QPushButton("View Deck")
        self.button_layout.addWidget(self.check_deck_button, 20)
        self.check_deck_button.pressed.connect(self.preview_deck)

        self.button_layout.addStretch(60)

        self.reset_selection = QPushButton("Reset Selection")
        self.button_layout.addWidget(self.reset_selection, 20)
        self.reset_selection.pressed.connect(self.clear_pack_selection)

        self.button_layout.addStretch(2)

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

        self.current_pack = QLabel("Current Pack: None")
        self.current_pack.setObjectName("indicator")
        self.button_layout.addWidget(self.current_pack, 20)

        self.button_layout.addStretch(60)

        self.next_button = QPushButton("Start")
        self.next_button.pressed.connect(self.sel_next_set)
        self.button_layout.addWidget(self.next_button, 20)

        self.drafting_layout.addLayout(self.button_layout)

        self.drafting_widget.setLayout(self.drafting_layout)

        return self.drafting_widget

    def sel_next_set(self) -> None:
        """MAIN Drafting Manager Method. Selects the next pack and also manages
        the drafting session in general.

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
        8. Finally opens the pack by calling open_pack().
        """

        if self.view_widget.currentWidget() == self.loading_widget:
            return

        if hasattr(self, "stretch"):
            self.drafting_layout.removeItem(self.stretch)
            self.setMinimumSize(self.size())

            del self.stretch

        if not self.proceed_set_check():
            return

        self.view_widget.setCurrentWidget(self.loading_widget)
        if self.drafting_model.selections:
            self.add_card_to_deck()

        if self.check_discard_stage():
            try:
                self.discard_stage()
            except ValueError:
                self.view_widget.setCurrentWidget(self.drafting_widget)
                return
            self.drafting_model.selections_left = 0

        self.next_button.setText("Next")

        if self.drafting_model.discard_stage_cnt == 4:
            logging.error("Selection complete!")
            msg_class = QMessageBox
            mbutton = msg_class.StandardButton
            ms_box = msg_class.information(
                self,
                "Deck Drafting Complete",
                "Would you like to preview the deck?",
                (mbutton.No | mbutton.Yes))

            if ms_box == mbutton.Yes:
                self.preview_deck()

            return self.accept()

        if self.card_buttons:
            self.clean_layout()

        sel_packs = self.parent().selected_packs

        set_data = sel_packs[self.drafting_model.opened_set_packs]
        self.load_set_art()

        self.drafting_model.total_packs += 1

        (self.packs_opened
         .setText(f"Pack No.: {self.drafting_model.total_packs}"))
        self.current_pack.setText(f"Current Pack: {set_data.set_name}")

        if not set_data.probabilities:
            card_data = self.ygo_data.get_card_set_info(set_data)
            set_data.card_set = tuple(card_data)
            probabilities = self.ygo_data.generate_weights(set_data.set_name,
                                                           card_data)
            set_data.probabilities = tuple(probabilities)

        if self.check_discard_stage():
            self.next_button.setText("Discard Stage")

        self.open_pack(set_data)
        set_data.count -= 1

        if set_data.count == 0:
            self.drafting_model.opened_set_packs += 1

    def proceed_set_check(self) -> bool:
        """Checks if the drafter can proceed to the next stage of drafting.

        This also double checks if there are enough cards to pick in the dialog
            in the first place.

        Returns:
            bool: True if all conditions are met else False.
        """
        if self.drafting_model.selections_left < 1:
            return True

        extra_card_types = 0
        duplicates = 0
        for card in self.card_buttons:
            mdl = card.card_model
            if self.ygo_data.check_extra_monster(mdl):
                extra_card_types += 1
            elif self.check_card_count(mdl) == 3:
                duplicates += 1
            elif card.isChecked():
                continue

        actual_selection = self.CARDS_PER_PACK
        actual_selection -= (extra_card_types + duplicates)

        if actual_selection < self.drafting_model.selections_left:
            return True

        text = "Select at least {0} more cards."
        text = text.format(self.drafting_model.selections_left)
        logging.info(text)
        QMessageBox.warning(self, "Select More Cards", text,
                            QMessageBox.StandardButton.Ok)
        return False

    def load_set_art(self) -> None:
        """Loads in set art from the server or local cache and resizes it
        to a visible size.
        """
        logging.debug("Loading Set Art into GUI")
        sel_packs = self.parent().selected_packs
        set_data = sel_packs[self.drafting_model.opened_set_packs]
        self.set_name_label.setText(set_data.set_name)
        set_art = self.parent().yugi_pro.get_set_art(set_data)
        if set_art is not None:
            set_art = set_art.scaled(self.SET_ART_SIZE.width() // 2,
                                     self.SET_ART_SIZE.height() // 2,
                                     Qt.AspectRatioMode.KeepAspectRatio)
            self.set_art_widget.setPixmap(set_art)

    def check_discard_stage(self) -> bool:
        """Checks if its time for a dicard stage or not. Return true if the
        condiions are met."""
        ten_div = self.drafting_model.total_packs % 10 == 0
        tot_pack = bool(self.drafting_model.total_packs)
        return ten_div and tot_pack

    def add_card_to_deck(self):
        """Adds cards to the deck from the picked cards in the current opended
        pack.
        """
        for cardbutton in list(self.drafting_model.selections):
            card = cardbutton
            if isinstance(card, CardButton):
                card = card.card_model

            if self.ygo_data.check_extra_monster(card):
                self.deck.extra.append(card)
                continue

            self.deck.main.append(card)

        self.update_counter_label()

    def clean_layout(self):
        """Cleans the pack Card Layout in order to add the open the next pack.

        *Might have to look a the function in the in order to determine
            if I am not having a issues with this approach.
        *Could also be combined with the adding cards function in order to
            make a smoother operation.
        """
        util.clean_layout(self.card_layout)

        for _ in range(len(self.drafting_model.selections)):
            card = self.drafting_model.selections.pop(0)
            if isinstance(card, CardModel):
                continue
            card.deleteLater()
            del card

        for _ in range(len(self.card_buttons)):
            card = self.card_buttons.pop(0)
            card.deleteLater()
            del card

        self.repaint()
        QApplication.processEvents()

    def filter_common(self, card: CardModel):
        """Filters out common rarity cards out of a set."""
        return card.rarity != "Common"

    def open_pack(self, set_data: CardSetModel) -> None:
        """ Opens a pack with probablities supplied and adds its to the layout.

        The last card get new probabilities as its atleast a rare.

        Args:
            set_data (YGOCardSet): Cards set which contains all the cards,
                probabilities and set info.
        """
        debug = f"Opening a pack from {set_data.set_name}.".center(60, "-")
        logging.debug(debug)

        self.drafting_model.selections_left += 2
        sel_left = self.drafting_model.selections_left
        self.drafting_model.selection_per_pack = sel_left
        logging.debug("%s Card Selection(s) Available.",
                      self.drafting_model.selection_per_pack)

        self.update_counter_label()

        for column in range(self.CARDS_PER_PACK):
            card_data = self.select_pack_card(set_data, column)

            self.loading_bar.setValue(column + 1)
            self.loading_label.setText(f"Loading: {card_data.name}")
            QApplication.processEvents()

            card = CardButton(card_data, self)

            if self.check_card_count(card_data) == 3:
                card.setDisabled(True)

            self.card_buttons.append(card)
            card.toggled.connect(partial(self.update_selection, card))
            self.card_layout.addWidget(card)

        self.repaint()
        self.view_widget.setCurrentWidget(self.drafting_widget)
        self.loading_bar.setValue(0)

    def select_pack_card(
        self,
        set_data: CardSetModel,
        pack_index: int
    ) -> CardModel:
        """Selects a random card based on the weights previously generated.

        Will select a rare or higher if its the 8 + 1 column, unless there are
            not enough rares in a set.

        Args:
            set_data (CardSetModel): The set to select the card from.
            pack_index (int): Current card being opened for checking when it
                100% should be a rare or above.

        Returns:
            CardModel: Select card model for display and information.
        """

        card_set = set_data.card_set
        prob = set_data.probabilities
        if pack_index == 8:
            rare_cards = list(filter(self.filter_common, card_set))
            rprob = self.ygo_data.generate_weights(set_data.set_name,
                                                   rare_cards,
                                                   extra=True)
            try:
                card_data = random.choices(rare_cards, weights=rprob, k=1)[0]
            except (IndexError, ValueError):
                return self.select_pack_card(set_data, pack_index=0)

        else:
            card_data = random.choices(card_set, weights=prob, k=1)[0]

        return card_data

    def parent(self) -> MainWindow:
        """Overriden function to remove the type alert."""
        return super().parent()  # type: ignore

    def update_selection(self, card: CardButton) -> None:
        """Check if there are any slections left and checks and for duplicate
        cards.

        Args:
            card (CardButton): Card that was changed and needs to be.
                Will be the first card that is checked.
        """
        logging.debug("Updating Selection")

        self.update_item_selection(card)

        for item in self.card_layout.widget_list():
            if item == card:
                continue
            self.update_item_selection(item)

    def update_item_selection(self, item: 'CardButton') -> None:
        """Updates the given item selection status.

        Args:
            item (CardButton): Item to be updated from the selection
        """
        with QSignalBlocker(item):
            item_in = item in self.drafting_model.selections
            fus_mon = self.ygo_data.check_extra_monster(item.card_model)

            if (item.isChecked()
               and not self.check_card_count(item.card_model) == 3
               and (self.drafting_model.selections_left > 0 or fus_mon)):

                if not item_in:
                    logging.debug("Adding card %s", item.accessibleName())
                    self.add_card_to_selection(item)

            elif not item.isChecked() and item_in:
                logging.debug("Removing card %s", item.accessibleName())
                self.remove_card_from_selection(item)

            elif not item_in and not fus_mon:
                item.setChecked(False)

            item.setDisabled((self.check_card_count(item.card_model) == 3
                             and not item.isChecked()) or item._assocc_added)

            self.update_counter_label()

        QApplication.processEvents()

    def add_card_to_selection(
        self,
        card_model: CardModel | CardButton
    ) -> None:
        """Adds a card to selection and decrements selections left in the
        current pack.

        Args:
            card_model (CardModel | CardButton): Target card to add to
                selection.
        """
        self.drafting_model.selections.append(card_model)

        if isinstance(card_model, CardButton):
            card_model = card_model.card_model

        if not self.ygo_data.check_extra_monster(card_model):
            self.drafting_model.selections_left -= 1

        self.update_counter_label()

    def remove_card_from_selection(
        self,
        card_model: CardModel | CardButton
    ) -> None:
        """Removes a card from selection and increments the selection if
        the card is not a extra deck monster.

        Args:
            card_model (CardModel | CardButton): Target card to remove.
        """
        index = self.drafting_model.selections.index(card_model)
        self.drafting_model.selections.pop(index)

        if isinstance(card_model, CardButton):
            card_model = card_model.card_model

        if not self.ygo_data.check_extra_monster(card_model):
            self.drafting_model.selections_left += 1

        self.update_counter_label()

    def update_counter_label(self):
        """Updates the card count indicator labels in the GUI."""

        self.selections_left_label()

        picked = len(self.deck.main) + len(self.deck.side)

        self.cards_picked.setText(f"Card Total: {picked}")

        tip = self.generate_breakdown_ttip(DeckType.MAIN).strip() + "\n"
        tip += f"Extra Deck: {len(self.deck.extra)}" + "\n"
        tip += self.generate_breakdown_ttip(DeckType.SIDE)

        self.cards_picked.setToolTip(tip.strip())

    def selections_left_label(self):
        """Selections left indicator updater and selection list tooltip.
        """
        remaining = f"Remaining Picks: {self.drafting_model.selections_left}"
        self.card_picks_left.setText(remaining)

        tooltip = "Selected Cards\n"
        for i, item in enumerate(self.drafting_model.selections):
            if isinstance(item, CardButton):
                item = item.card_model
            tooltip += f"{i + 1}. {item.name}"
            if i + 1 != len(self.drafting_model.selections):
                tooltip += "\n"

        self.card_picks_left.setToolTip(tooltip)

    def generate_breakdown_ttip(
        self,
        deck: DeckType | list,
    ) -> str:
        """Generates a breakdown for each type main card of each deck.

        Args:
            deck (DeckType | list): Deck/Deck Type to create a break down off.

        Returns:
            str: Breakdown seperated with newlines.
        """

        logging.debug("Generating Deck Breakdown")
        decks = {
            DeckType.MAIN: self.deck.main,
            DeckType.EXTRA: self.deck.extra,
            DeckType.SIDE: self.deck.side
        }
        sel_deck = decks[deck] if isinstance(deck, DeckType) else deck
        monster_total = self.count_card_type("Monster", sel_deck)
        spell_total = self.count_card_type("Spell", sel_deck)
        trap_total = self.count_card_type("Trap", sel_deck)

        space = " " * 6
        break_down = space + f"Monster: {monster_total}\n"
        break_down += space + f"Spell: {spell_total}\n"
        break_down += space + f"Trap: {trap_total}"

        if isinstance(deck, list):
            break_down = break_down.replace(space, "")
            return break_down.strip()

        tip = f"{deck.name.title()} Deck: {len(sel_deck)}\n"

        return str(tip + break_down).strip()

    def check_card_count(self, card: CardModel) -> int:
        """Checks the amount of the same card present in the deck.

        Args:
            card (YGOCard): Card Model to be checked for.

        Returns:
            int: The amount of cards present inside all the decks.
                 Between 0 and 3 usually.
        """
        count = 0

        def count_cards(card, deck) -> int:
            count = 0

            for item in deck:
                if item.name == card.name:
                    count += 1
            return count

        count += count_cards(card, self.deck.main)
        count += count_cards(card, self.deck.extra)
        count += count_cards(card, self.deck.side)

        for item in self.drafting_model.selections:
            if isinstance(item, CardButton):
                item = item.card_model
            if item.name == card.name:
                count += 1

        return count

    def discard_stage(self) -> None:
        """Calculates the amount to be discarded and starts the dialog.

        Raises:
            ValueError: Will raise a value error if the discard stage was
                unsucessful.
        """

        discard = self.drafting_model.total_packs
        discard += (self.drafting_model.total_packs // 5)
        dialog = DeckViewer(self, discard)

        dialog.setWindowTitle("Card Removal Stage")

        if self.parent().debug:
            dialog.show()
        else:
            confirmation = dialog.exec()
            if confirmation:
                self.deck = dialog.new_deck
                self.drafting_model.discard_stage_cnt += 1
            else:
                raise ValueError("Discard Not Successful")

            self.auto_save(self.drafting_model.discard_stage_cnt)

    def preview_deck(self):
        """Spawns the deck viewer for previewing the deck on demand."""

        deck = DeckViewer(self)
        deck.exec()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Key override to prevent the drafter from accidently quitting out of
        the window or misclicking.

        Args:
            event (QKeyEvent | None): Event object to take information from.
        """
        if event is None:
            return super().keyPressEvent(event)

        KEY = Qt.Key
        if (event.key() in {KEY.Key_Escape, KEY.Key_Space}):
            return

        return super().keyPressEvent(event)

    @pyqtSlot()
    def clear_pack_selection(self):
        """Resets current pack selection fully."""
        selection_count = len(self.drafting_model.selections)

        for _ in range(selection_count):
            item = self.drafting_model.selections.pop(-1)
            if isinstance(item, CardButton):
                with QSignalBlocker(item):
                    item.setChecked(False)
                    item.setDisabled(False)
                    item._assocc_added = False
                item = item.card_model

        sel_left = self.drafting_model.selection_per_pack
        self.drafting_model.selections_left = sel_left

        self.update_counter_label()

    def minimumSize(self) -> QSize:
        """Minimum size for the drafting for clearer reading.

        Returns:
            QSize: Minimum size of the window based on 1080p resolution.
        """
        return QSize(1344, 824)

    def closeEvent(self, event: QCloseEvent | None):
        """Overriden closeEvent to catch closing out the window as an
        accidental closing can lose a lot of progress.

        Args:
            event (QCloseEvent): event to be catched and declined/accepted.
        """
        if event is None:
            return
        close = QMessageBox.question(
            self,
            "Quit",
            "Are you sure want to quit the drafting process?",
            (QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes))

        if close == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

    def count_card_type(
        self,
        card_type: str,
        group: list[CardModel] | list[CardButton]
    ) -> int:
        """Counts the target card_type inside the container provided.

        Args:
            card_type (str): Target card type to check for. Is fuzzy as the
                method checks if the card_type is inside the models card_type.
            group (list[CardButton | CardModel]): Where the cards to check
                are located.

        Returns:
            int: Count of the card_type inside the card_model.
        """

        cnt = 0
        for mdl in group:
            if isinstance(mdl, CardButton):
                if mdl.isChecked():  # Exculdes discarded cards.
                    continue
                mdl = mdl.card_model
            if card_type.lower() in mdl.card_type.name.lower():
                cnt += 1

        return cnt

    def auto_save(self, stage: int) -> None:
        """Auto save method for saving the current deck after each stage of the
        game.

        Args:
            stage (int): Discard Stage for the name of the file.
        """
        logging.info("Autosaving Deck at discard stage %s", stage)
        autosave_location = self.parent().DEFAULT_SAVE / Path("autosave")
        autosave_location.mkdir(parents=True, exist_ok=True)

        data = self.ygo_data.to_ygodk_format(self.deck)
        deck_name = self.deck.name if self.deck.name != "" else "Deck"
        name = Path(f"{deck_name}_autosave_stage_{stage}.ydk".lower())
        path = autosave_location / name

        with path.open("w", encoding="utf-8") as autosave:
            autosave.write(data)


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
    ASPECT_RATIO = AspectRatio(0.650793651, 1.4756097561)

    def __init__(
        self,
        data: CardModel,
        parent: DraftingDialog,
        viewer: Optional['DeckViewer'] = None,
        sub_deck: Optional[DeckType] = None
    ) -> None:
        super().__init__(parent=parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.drafting_dialog = parent
        self._sub_deck = sub_deck

        self.viewer = viewer  # type: ignore
        self.card_model = data

        self.rarity_color = parent.ygo_data.RARITY_COLOURS[data.rarity]

        self.setAccessibleName(data.name)
        self.setAccessibleDescription(data.description)

        self._assocc_added = False

        self.construct_card_tooltip(data)

        self.setObjectName("card_button")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)

        QSP = QSizePolicy.Policy
        self.setSizePolicy(QSP.MinimumExpanding, QSP.MinimumExpanding)
        self.setCheckable(True)

        if sub_deck is None:
            self.assocc = self.filter_assocciated(data)

        self.image = parent.ygo_data.get_card_art(self.card_model)

    def construct_card_tooltip(self, data: CardModel) -> None:
        """Generates a tooltip out of the provided card model data.

        Args:
            data (CardModel): Card model data to be used to extract the info.
        """
        desc = util.new_line_text(data.description, 100)
        ttip = data.name
        if data.level:
            ttip += f" | Level: {data.level}"
        if data.attribute:
            ttip += f" | Attribute: {data.attribute.name.title()}"
        ttip += f"\n\n{desc}"
        if data.attack is not None:
            ttip += f"\n\nATK: {data.attack}  |  DEF: {data.defense}"
        self.setToolTip(ttip)

    def minimumSize(self) -> QSize:
        """Overriden minimum size of the widget in order to stay legible.

        Returns:
            QSize: item desribes the minimum size of the widget.
        """
        return self.BASE_SIZE

    def sizeHint(self) -> QSize:
        """Overriden size hint to return the minimum size at all times.

        Returns:
            QSize: Minimum size object.
        """
        return self.minimumSize()

    def filter_assocciated(
        self,
        card_model: CardModel
    ) -> tuple[ExtraMaterial, ...]:
        """Filters out asscciated cards for quick adding with the submenu.

        Also checks if the items in the card are actually accessible in the
        Ygoprodeck database.

        Returns:
            list: Assocciated Extra Summon Data.
        """
        assocc_data = self.parent().ygo_data.find_extra_materials(card_model)

        return assocc_data

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
            return

        option = QStyleOptionButton()
        option.initFrom(self)

        rect = event.rect()

        painter = QPainter(self)
        HINT = QPainter.RenderHint
        painter.setRenderHints(HINT.LosslessImageRendering)
        image = self.image.scaled(self.width(), self.height(),
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)

        if not self.isEnabled():
            image = image.toImage()
            grayscale = image.convertToFormat(QImage.Format.Format_Grayscale8)
            image = QPixmap.fromImage(grayscale)

        brush = QBrush(image)
        painter.setBrush(brush)

        pen_width = 7
        pen = QPen()
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)

        pen.setWidthF(pen_width)
        if self.isChecked():
            pen.setColor(Qt.GlobalColor.red)
            painter.setPen(pen)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            pen.setColor(Qt.GlobalColor.yellow)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        new_rect = self.rect_generator(rect, pen_width)
        painter.drawRect(new_rect)

        if self.card_model.rarity != "Common":
            painter.save()
            painter.setOpacity(0.8)
            cmp = QPainter.CompositionMode.CompositionMode_ColorDodge
            painter.setCompositionMode(cmp)
            pen.setColor(self.rarity_color)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            new_rect = self.rect_generator(rect, pen_width)
            painter.drawRect(new_rect)
            painter.restore()

        if not self.isChecked():
            return

        if isinstance(self.viewer, DeckViewer) and self.viewer.discard:
            rect = self.rect()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topRight())

        return

    def rect_generator(self, og_rect: QRect, pen_width: float) -> QRectF:
        """Generates a rectangle render adjusted to the pen size for proper
        positioning.

        Args:
            og_rect (QRect): Origin rectantle to take size and position from.
            pen_width (float): Pen size to adjust the rectangle with.

        Returns:
            QRectF: Adjusted rectangle which will fit the line centers
                properly.
        """
        pen_half = pen_width / 2
        new_rect = QRectF(og_rect.x() + pen_half,
                          og_rect.y() + pen_half,
                          og_rect.width() - pen_width,
                          og_rect.height() - pen_width)
        return new_rect

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
            _ = self.discard_stage_menu(menu)
        else:
            if self.parent().drafting_model.selections_left < 1:
                return

            _ = self.drafting_menu(menu)

        if menu.actions():
            menu.exec(pos)
            pass

        self.repaint()

    def drafting_menu(self, menu: QMenu) -> list[QAction]:
        """Menu that pop ups when drafting the deck.

        Args:
            menu (QMenu): Menu to add the additonal actions to.

        Returns:
            list: List of QAction to prevent garbage collection to remove them
                pre-emptively.
        """
        actions = []
        logging.debug("Assocc %s", self.assocc)
        if self.parent().ygo_data.check_extra_monster(self.card_model):
            self.fusion_menu(menu, actions)

        elif self.assocc:
            for item in self.assocc:
                for card in item.materials:
                    print(card)
                    if (card.subtype != "name"
                       or isinstance(card, DamageValues)):
                        continue
                    action = self.create_add_action(str(card.name))
                    util.action_to_list_men(action, actions, menu)

            self.add_all_assocc_action(actions, menu)

        return actions

    def add_all_assocc_action(
        self,
        actions: list[QAction],
        menu: QMenu
    ) -> None:
        """Action for adding all named cards to the selection.

        Args:
            actions (list): Container to add the action to.
            menu (QMenu): Menu to add the action to.
        """

        non_search = actions and any("Search" not in a.text() for a in actions)
        if (self.parent().drafting_model.selections_left > 1 and non_search):
            acc = QAction("Add all Assocciated")
            acc.triggered.connect(self.add_all_assocc)
            util.action_to_list_men(acc, actions, menu)

    def fusion_menu(self, menu: QMenu, action_container: list) -> None:
        """Creates fusion/extra deck monster menu actions.

        Args:
            menu (QMenu): Menu to add the actions to.
            action_container (list): Data structure for actions to keep the
                away from garbage collection.
        """

        for assocc in self.assocc:
            if not assocc.materials and assocc.count == -1:
                continue
            if assocc.materials and assocc.materials[0].subtype == "name":
                action = self.create_add_action(assocc.materials[0].name)
            else:
                action = self.search_menu(assocc)

            util.action_to_list_men(action, action_container, menu)

        self.add_all_assocc_action(action_container, menu)

    def create_add_action(self, name: str | enum.Enum) -> QAction:
        """Generates and connects a action for adding a card to the selection.

        Args:
            name (str | enum.Enum): Name of the card that will be added.

        Returns:
            QAction: Action to add to a menu.
        """
        if isinstance(name, enum.Enum):
            name = name.name.replace("_", " ").title()

        action = QAction("Add " + name.title())
        action.triggered.connect(lambda: self.add_assocc(name))
        return action

    def search_menu(
        self,
        data: ExtraMaterial,
    ) -> QAction:
        """Create an action for to search for a subtype of a card.

        Args:
           data (ExtraMaterial): The query information to use when searching
                for cards.
        """
        label = self.generate_action_labels(data)
        search_item = QAction(label)
        search_item.triggered.connect(lambda: self.search_dialog(data, label))

        return search_item

    def generate_action_labels(
        self,
        data: ExtraMaterial,
    ) -> str:
        """Generates a text label for menu actions.

        Args:
            data (ExtraMaterial): Data to parse to create the label
            action_type (str, optional): Type of label. For a search action or
                add action. Defaults to "Search".

        Returns:
            str: A formatted string for display purposes.
        """

        text = f"Search for {data.count} Monster(s) "
        if data.level != -1:
            text += f"level {data.level} "

        if not data.materials:
            return text + " Monster"

        start = "with"
        for item in data.materials:
            if isinstance(item, DamageValues):
                continue
            name = item.name
            if isinstance(name, enum.Enum):
                name = name.name.replace("_", " ")

            subtype = item.subtype.title().replace("_", " ")
            if item.polarity:
                t = f"{start} {subtype}: {name.title()} "
                start = "and"
            else:
                t = f"that are not a {subtype}: {name.title()} "

            text += t

        return text

    def discard_stage_menu(self, menu: QMenu) -> list[QAction]:
        """Menu that pop ups when in the discard stage of drafting.

        Args:
            menu (QMenu): Menu to add the additonal actions to.

        Returns:
            list: List of QAction to prevent garbage collection to remove them
                pre-emptively.
        """
        actions = []
        self.viewer: DeckViewer
        if self.isChecked():
            card_state = "Keep Card"
        else:
            card_state = "Discard Card"
        card_state_change = QAction(card_state)
        card_state_change.triggered.connect(self.toggle)
        util.action_to_list_men(card_state_change, actions, menu)

        mv_deck = self.viewer.mv_card

        if self.sub_deck == DeckType.MAIN:
            mv_side = f"Move {self.accessibleName()} to Side Deck"
            mv_to_side = QAction(mv_side)
            mv_to_side.triggered.connect(lambda: mv_deck(self, DeckType.SIDE))
            util.action_to_list_men(mv_to_side, actions, menu)

        elif self.sub_deck == DeckType.SIDE:
            mv_main = f"Move {self.accessibleName()} to Main Deck"
            mv_to_main = QAction(mv_main)
            mv_to_main.triggered.connect(lambda: mv_deck(self, DeckType.MAIN))
            util.action_to_list_men(mv_to_main, actions, menu)

        return actions

    def add_all_assocc(self) -> None:
        """Adds all assocciated cards present within the assocc instance
        variable.

        If the monster belongs in the extra deck a Polymerization gets added to
        the deck.
        """

        items = []
        for item in self.assocc:
            for sub_item in item.materials:
                if sub_item.subtype != "name":
                    continue
                items.append(sub_item.name)

        if self.parent().ygo_data.check_extra_monster(self.card_model):
            if (self.card_model.card_type
               in self.parent().ygo_data.TYPE_MATCH[CardType.FUSION_MONSTER]):
                poly = "Polymerization"
                items.append(poly)

        self.get_card(items)
        self.toggle_assocc()

    def add_assocc(self, card_name: str) -> None:
        """Adds a single assocciated card to the selected cards.

        Args:
            card_name (str): Which card to add to the deck as it will get
                searched by subsequent functions.
        """
        self.get_card(card_name)
        self.toggle_assocc()

    def toggle_assocc(self, toggl: bool = True) -> None:
        """Assocciation toggle for checking if the card should stay disabled.

        Args:
            toggl (bool): Turn the item on or off
        """
        self._assocc_added = toggl
        self.setChecked(toggl)
        self.setDisabled(toggl)

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
            logging.error("Card does not exist.")
            self.toggle_assocc(False)
            return

        logging.info("Adding %s to selection.", card_name)

        try:
            card_set = self.card_model.card_set
            c_mdl = self.parent().ygo_data.create_card(data[0], card_set)
        except KeyError:
            return

        self.add_card(c_mdl)

    def add_card(self, card: CardModel) -> None:
        """Adds a card to the deck list.

        If three of the same card exist inside the deck the card gets ignored.

        Args:
            card (YGOCard): Model of the card to be added.
        """
        if self.parent().check_card_count(card) == 3:
            logging.error("Three %s cards in deck.", card.name)
            return

        self.parent().add_card_to_selection(card)

    def parent(self) -> DraftingDialog:
        """Override to clear typing issues when calling this function."""
        return self.drafting_dialog  # type: ignore

    def search_dialog(
        self,
        data: ExtraMaterial,
        label: str,
    ) -> None:
        """Starts a search dialog with the instances target subtype.
        """

        dialog = CardSearch(self.card_model, data, self.parent(), label)

        if dialog.exec():
            for item in dialog.chosen_items:
                self.add_card(item)
            self.setChecked(True)
            self.setDisabled(True)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        """Movement function for when dragging cards between decks."""
        if event is None:
            return

        if self.sub_deck in (None, DeckType.EXTRA, DeckType.SEARCH):
            return

        if event.buttons() == Qt.MouseButton.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            drag.setMimeData(mime)

            pixmap = QPixmap(self.size())
            self.render(pixmap)
            drag.setPixmap(pixmap)

            drag.exec(Qt.DropAction.MoveAction)

    @property
    def sub_deck(self) -> DeckType | None:
        """Returns the sub_deck type of the given instance.

        Returns:
            DeckType | None: DeckType of the card instance if applicable.
        """
        return self._sub_deck

    @sub_deck.setter
    def sub_deck(self, sub_deck: DeckType | None) -> None:
        """Sets the sub deck of the given card.

        Args:
            sub_deck (DeckType | None): The decktype of the card model itself.
        """
        self._sub_deck = sub_deck


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
        discard (int): How many cards should be discounted.
            Used as a boolean to decide what type of viewer it is.
    """
    MAX_COLUMNS: Final[int] = 10

    def __init__(self, parent: DraftingDialog, discard: int = 0) -> None:
        super().__init__(parent)
        self.setModal(not parent.parent().debug)
        self.setWindowTitle("Deck Viewer")
        self.resize(1745, 860)  # Base on 1080 ratio

        self.discard = discard
        self.side_length = len(parent.deck.side) + 2

        self.main_layout = QVBoxLayout()

        self.main_deck_widget = DeckSlider(DeckType.MAIN, self)
        self.deck = self.main_deck_widget.main_layout
        self.main_layout.addWidget(self.main_deck_widget, 60)
        self.fill_deck(parent.deck.main, self.main_deck_widget)

        self.extra_deck_widget = DeckSlider(DeckType.EXTRA, self)
        self.extra = self.extra_deck_widget.main_layout
        self.main_layout.addWidget(self.extra_deck_widget, 20)
        self.fill_deck(parent.deck.extra, self.extra_deck_widget)

        self.side_deck_widget = DeckSlider(DeckType.SIDE, self)
        self.side = self.side_deck_widget.main_layout
        self.main_layout.addWidget(self.side_deck_widget, 20)
        self.fill_deck(parent.deck.side, self.side_deck_widget)

        self.interconnect_repaint(self.main_deck_widget)
        self.interconnect_repaint(self.side_deck_widget)

        self.button_layout = QHBoxLayout()

        if discard:
            self.removal_counter = QLabel()
            self.removal_counter.setObjectName("indicator")
            self.button_layout.addWidget(self.removal_counter, 5)

            self.side_counter = QLabel()
            self.side_counter.setObjectName("indicator")
            self.button_layout.addWidget(self.side_counter, 5)

            self.button_layout.addStretch(50)

        self.main_deck_count = QLabel()
        self.main_deck_count.setObjectName("indicator")
        self.button_layout.addWidget(self.main_deck_count, 5)

        self.extra_deck_count = QLabel()
        self.extra_deck_count.setObjectName("indicator")
        self.button_layout.addWidget(self.extra_deck_count, 5)

        self.side_deck_count = QLabel()
        self.side_deck_count.setObjectName("indicator")
        self.button_layout.addWidget(self.side_deck_count, 5)

        self.removal_count()

        self.button_layout.addStretch(55)

        self.accept_button = QPushButton("Accept")
        self.accept_button.pressed.connect(self.accept)
        self.button_layout.addWidget(self.accept_button, 5)

        self.main_layout.addLayout(self.button_layout)

        self.setLayout(self.main_layout)

    def interconnect_repaint(self, widget: DeckSlider) -> None:
        """This method interconnects Deck Widgets to repaint on drop events.

        Args:
            widget (DeckSlider): Widget to take the signal from.
        """
        (widget.main_widget.order_changed
         .connect(self.main_deck_widget.main_widget.repaint))
        (widget.main_widget.order_changed
         .connect(self.side_deck_widget.main_widget.repaint))

    def fill_deck(
        self,
        cards: list[CardModel],
        scroll_bar: 'DeckSlider',
        check: bool = False
    ) -> None:
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

        QSP = QSizePolicy.Policy
        row = 0
        column = 0
        while cards:
            if column % self.MAX_COLUMNS == 0 and column:
                row += 1
                column = 0

            card = cards.pop(0)

            card_button = CardButton(card, self.parent(), self,
                                     scroll_bar.deck_type)

            self.connect_scroll_bar(scroll_bar, card_button)

            if not self.discard:
                card_button.setCheckable(False)
            else:
                card_button.toggled.connect(self.removal_count)
                card_button.setChecked(check)

            card_button.setSizePolicy(QSP.Maximum, QSP.Maximum)

            layout.addWidget(card_button)  # type: ignore
            column += 1

    def connect_scroll_bar(
        self,
        scroll_bar: QScrollArea,
        card_button: CardButton
    ) -> None:
        """Connects scrolling signal to a repaint function of the cards in
        order to avoid render artifacting.

        Args:
            scroll_bar (QScrollArea): Scroll area to source the scrollbars
                from.
            card_button (CardButton): Cardbutton to repaint.
        """
        if isinstance(scroll_bar, QScrollArea):
            vscroll = scroll_bar.verticalScrollBar()
            if vscroll is not None:
                vscroll.valueChanged.connect(card_button.repaint)
            hscroll = scroll_bar.horizontalScrollBar()
            if hscroll is not None:
                hscroll.valueChanged.connect(card_button.repaint)

    def mv_card(self, card: CardButton, deck: DeckType) -> None:
        """Moves a card[CardButton] between the side and main deck.

           To be called from the card (CardButton):show_menu method itself
           and assigns itself for movement.

           Args:
                card (CardButton): The card to be moved.
                deck (CardButton): Which deck the card will be moved to.
        """

        if deck == DeckType.MAIN:
            self.main_deck_widget.main_layout.addWidget(card)

        elif deck == DeckType.SIDE:
            self.side_deck_widget.main_layout.addWidget(card)

        if self.discard:
            self.removal_count()

    def parent(self) -> DraftingDialog:
        """Overriden to avoid type hint issues."""
        return super().parent()  # type: ignore

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Overriden to prevent the user from accidently quitting the
           application if there are a lot of random keystrokes."""

        if event is None:
            return super().keyPressEvent(event)

        KEY = Qt.Key
        if (event.key() in {KEY.Key_Escape, KEY.Key_Space} and self.discard):
            return None

        return super().keyPressEvent(event)

    def count(self, target: Optional[DeckType] = None) -> int:
        """Returns the count of the deck picked > target[str] with the
           checked cards marked for removal as discarded.

            Args:
                target (str): If just checking for just one deck count this is
                    used to filter those out.

            Returns:
                int: Target count as an in value.
        """

        def cnt(layout: CardLayout):
            sub_count = 0
            widgets = layout.widget_list()
            for widget in widgets:
                if widget.isChecked():
                    continue
                sub_count += 1

            return sub_count

        count = 0
        if target in (None, DeckType.MAIN):
            count += cnt(self.main_deck_widget.main_layout)

        if target in (None, DeckType.SIDE):
            count += cnt(self.side_deck_widget.main_layout)

        return count

    @pyqtSlot()
    def removal_count(self) -> None:
        """Updates the counters for removal, main, side and extra deck."""
        if self.discard:
            discard_count = self.count() - self.discard
            self.removal_counter.setText(f"Remove: {discard_count}")
            side_count = abs(self.count(DeckType.SIDE) - self.side_length)
            self.side_counter.setText(f"Side: {side_count}")

        mcount = self.count(DeckType.MAIN)
        with QSignalBlocker(self.main_deck_count):
            self.main_deck_count.setText(f"Main Deck: {mcount}")
            widget_list = self.deck.widget_list()
            ttip = self.parent().generate_breakdown_ttip(widget_list)
            self.main_deck_count.setToolTip(ttip)

        extra = self.extra_deck_widget.main_layout.count()
        with QSignalBlocker(self.extra_deck_count):
            self.extra_deck_count.setText(f"Extra Deck: {extra}")
            widget_list = self.extra.widget_list()
            ttip = self.parent().generate_breakdown_ttip(widget_list)
            self.extra_deck_count.setToolTip(ttip)

        side = self.count(DeckType.SIDE)
        with QSignalBlocker(self.side_deck_count):
            self.side_deck_count.setText(f"Side Deck: {side}")
            widget_list = self.side.widget_list()
            ttip = self.parent().generate_breakdown_ttip(widget_list)
            self.side_deck_count.setToolTip(ttip)

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

        logging.debug("Deck Cards: %s",
                      self.main_deck_widget.main_layout.count())
        logging.debug("Extra Cards: %s",
                      self.extra_deck_widget.main_layout.count())
        logging.debug("Side Cards: %s",
                      self.side_deck_widget.main_layout.count())

        count = self.count()
        logging.debug("Actual Count: %s", count)

        if count != self.discard:
            cnt = count - self.discard
            operation, cnt = util.get_operation(cnt)

            QMessageBox.warning(self, f"{operation} More Cards",
                                f"{operation} {cnt} more card(s)",
                                QMessageBox.StandardButton.Ok)
            return

        elif self.count(DeckType.SIDE) != self.side_length:
            cnt = self.count(DeckType.SIDE) - self.side_length
            operation, cnt = util.get_operation(cnt)
            msg = f"{operation} {cnt} more card(s) to the Side Deck"

            if operation == "Remove":
                msg = f"{operation} {cnt} more card(s) from the Side Deck"

            QMessageBox.warning(self, "Adjust Side Deck", msg,
                                QMessageBox.StandardButton.Ok)
            return

        self.new_deck = DeckModel(self.parent().deck.name)

        main_deck_cards = self.main_deck_widget.main_layout.widget_list()
        filter_items(self.new_deck.main, main_deck_cards)
        extra_deck_cards = self.extra_deck_widget.main_layout.widget_list()
        filter_items(self.new_deck.extra, extra_deck_cards)
        side_deck_cards = self.side_deck_widget.main_layout.widget_list()
        filter_items(self.new_deck.side, side_deck_cards)

        return super().accept()


class CardSearch(QDialog):
    """Dialog for search for different subtypes of a card when the card desc
    doesn't have a description itself.

    Attributes:
        data (CardModel): Container for data that matched query with the
            info given.

    Args:
        card (CardModel): DataModel for the card the assocciations belong to.
        extra_material (ExtraMaterial): Query setting for finding suitable
            cards.
        parent (DraftingDialog): For searching capability and checking
            duplicates.
    """

    def __init__(
        self,
        card: CardModel,
        extra_material: ExtraMaterial,
        parent: DraftingDialog,
        label: str
    ) -> None:
        super().__init__(parent)
        self.card = card
        self.extra_mats = extra_material

        self.setWindowTitle(label.replace("_", " "))
        self.setMinimumSize(960, 540)

        self.data = parent.ygo_data.complex_search(extra_material)

        if not self.data:
            self.reject()

        self.main_layout = QVBoxLayout()

        self.top_bar = QHBoxLayout()
        self.main_layout.addLayout(self.top_bar)

        self.search_box = QLineEdit()
        self.search_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.search_box.setPlaceholderText("Search")
        self.top_bar.addWidget(self.search_box, 80)

        self.matches_box = QLabel(f"Matches: {len(self.data)} card(s)")
        self.matches_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.matches_box.setObjectName("indicator")
        self.top_bar.addWidget(self.matches_box, 20)

        self.scroll_widget = DeckSlider(None, self)
        self.main_layout.addWidget(self.scroll_widget)

        self.button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.pressed.connect(self.reject)
        self.button_layout.addWidget(self.cancel_button)

        self.button_layout.addStretch(20)

        self.add_more_button = QPushButton("Load More Cards")
        self.button_layout.addWidget(self.add_more_button)
        self.add_more_button.pressed.connect(self.load_more_cards)

        self.button_layout.addStretch(10)

        self.pick_text = "{count} pick(s) left"
        self.picks = QLabel(self.pick_text.format(count=self.extra_mats.count))
        self.picks.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picks.setObjectName("indicator")
        self.button_layout.addWidget(self.picks)

        self.button_layout.addStretch(10)

        self.accept_button = QPushButton("Accept")
        self.accept_button.pressed.connect(self.accept)
        self.button_layout.addWidget(self.accept_button)

        self.main_layout.addLayout(self.button_layout)

        self.fill_search()

        self.setLayout(self.main_layout)

        self.load_more_cards()

    def load_more_cards(self):
        """Loads the next set of maximum 20 cards.
        """
        self.data: list
        max_files = min(20, len(self.data))
        progress_dialog = QProgressDialog("Loading Cards", None, 0, max_files,
                                          self.parent())
        progress_dialog.show()
        label = "Loading Cards {card_name}"
        for i in range(20):
            progress_dialog.setValue(i)
            QApplication.processEvents()

            if not self.data:
                self.add_more_button.setDisabled(True)
                progress_dialog.setValue(max_files)
                break

            bttn = self.load_cardbutton()
            lab = label.format(card_name=bttn.accessibleName())
            progress_dialog.setLabelText(lab)

        progress_dialog.close()
        progress_dialog.deleteLater()

    def load_cardbutton(
        self,
        index: int = 0,
        check: bool = False
    ) -> CardButton:
        """Loads the next single card from the saved data.

        Args:
            index (int, optional): Index of the card to us. Defaults to 0.
            check (bool, optional): Checks the card if its True.
                Defaults to False.

        Returns:
            CardButton: For scrolling the view to the item.
        """
        CMP = Qt.ContextMenuPolicy
        card_button = CardButton(self.data.pop(index),
                                 self.parent(),
                                 sub_deck=DeckType.SEARCH)
        card_button.setContextMenuPolicy(CMP.NoContextMenu)
        card_button.setChecked(check)
        card_button.toggled.connect(self.check_picks)
        self.scroll_widget.main_layout.addWidget(card_button)

        return card_button

    @pyqtSlot(int)
    def card_pick_setter(self, picked: int = 0) -> None:
        """Slot for setting the cards picked indicator.

        Args:
            picked (int, optional): Total cards picked so far.
                Defaults to 0.
        """
        txt = self.pick_text.format(count=self.extra_mats.count - picked)
        self.picks.setText(txt)

    def parent(self) -> DraftingDialog:
        """Overriden parent function to avoid typing issues.

        Returns:
            DraftingDialog: Returns the parent of the widget.
        """
        return super().parent()  # type: ignore

    def fill_search(self) -> None:
        """Pre-cached the search values which matched to the name of the
        searched subtype.
        """

        if not isinstance(self.data, list):
            return self.reject()

        names = [card.name for card in self.data]

        completer = QCompleter(names)
        completer.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)

        self.search_box.setCompleter(completer)
        (self.search_box.editingFinished
         .connect(lambda: self.highlight_search(self.search_box.text())))

    def highlight_search(self, name: str) -> None:
        """Hightlights the item searched for inside the search box and toggls
        the button to the checked state.

        Args:
            name (str): Name of the card to highlight.
        """
        for i, item in enumerate(self.scroll_widget.main_layout.widget_list()):
            if item.accessibleName() == name:
                item.setChecked(True)
                return

        for i, item in enumerate(self.data):
            if item.name == name:
                item = self.load_cardbutton(i, True)
                sbar = self.scroll_widget.horizontalScrollBar()
                sbar.setValue(sbar.maximum() + item.width())  # type: ignore
                break

    def check_picks(self) -> list[CardModel]:
        """Checks which cards are picked and adds them to a list while updating
        the pick indicator.

        Returns:
            list[CardModel]: A list of picked cards.
        """
        picked_cards: list[CardModel] = []
        for item in self.scroll_widget.main_layout.widget_list():
            if item.isChecked():
                if len(picked_cards) > self.extra_mats.count:
                    with QSignalBlocker(item):
                        item.setChecked(False)
                        continue
                picked_cards.append(item.card_model)

        self.card_pick_setter(len(picked_cards))

        return picked_cards

    def accept(self) -> None:
        """Overriden except method in order to highlight and return the correct
        card model.
        """

        self.chosen_items = self.check_picks()
        if not self.chosen_items:
            QMessageBox.warning(
                self,
                "Select more cards.",
                "Select at least one card.")
            return
        elif len(self.chosen_items) > self.extra_mats.count:
            QMessageBox.warning(
                self,
                "Too Many Cards",
                f"Maximum {len(self.chosen_items)} Allowed")
            return

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

    def __init__(
        self,
        deck_type: DeckType | None,
        parent: DeckViewer | CardSearch,
    ) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)

        self.deck_type = deck_type
        QSP = QSizePolicy.Policy
        SBP = Qt.ScrollBarPolicy
        self.setHorizontalScrollBarPolicy(SBP.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(SBP.ScrollBarAlwaysOff)

        self.main_widget = DeckWidget(deck_type, self)

        if isinstance(parent, DeckViewer):
            self.main_widget.order_changed.connect(parent.removal_count)

        if deck_type == DeckType.MAIN:
            self.setVerticalScrollBarPolicy(SBP.ScrollBarAlwaysOn)
            self.main_widget.setSizePolicy(QSP.Preferred, QSP.Expanding)
        else:
            self.setHorizontalScrollBarPolicy(SBP.ScrollBarAlwaysOn)
            self.main_widget.setSizePolicy(QSP.MinimumExpanding, QSP.Expanding)

        self.main_layout = self.main_widget.main_layout

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

    Args:
        deck_type (str): Type of Deck {Side/Extra/Main} for label purposes.
        parent (DeckSlider): to access and manage the layout within the
                             DeckViewer and allow scrolling the layout
        main_layout (CardLayout): Varied card layout depending on the deck
            type.
    """
    order_changed = pyqtSignal()

    def __init__(self, deck_type: DeckType | None, parent: DeckSlider):
        super().__init__(parent)

        self.scroll_area = parent
        self.deck_type = deck_type

        if isinstance(deck_type, DeckType):
            self.name = deck_type.name.title() + " Deck"

        if (deck_type != DeckType.EXTRA
           and not isinstance(parent.parent(), CardSearch)):
            self.setAcceptDrops(True)

        if deck_type == DeckType.MAIN:
            self.main_layout = CardLayout(parent=self, scroll=(True, False))
        else:
            self.main_layout = CardLayout(rows=1, parent=self,
                                          scroll=(False, True))
        self.setLayout(self.main_layout)

    def paintEvent(self, event: QPaintEvent | None):
        """Draws the basic paint event of the widget.

        Extended with a QPainter in order to draw the deck name on the
        center of the viewport background adjusting for scrolled distance.

        Args:
            event (QPaintEvent | None): Builtin QWidget paint event to refresh
                                        and find out which area needs rerender.
        """
        super().paintEvent(event)
        if event is None or self.deck_type is None:
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
                         | Qt.AlignmentFlag.AlignCenter), self.name)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Event Manager for a widget dragged around the layout."""
        event.acceptProposedAction()

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
        button = event.source()

        if button not in self.main_layout.widget_list():
            self.main_layout.addWidget(button)  # type: ignore

        for n in range(self.main_layout.count()):
            item = self.main_layout.itemAt(n)
            if item is None:
                continue

            widget = util.check_item_validation(item)
            if widget is None:
                continue

            drop_here_x = pos.x() > widget.x() + widget.size().width() // 2
            drop_here_y = pos.y() > widget.y() + widget.size().height() // 2

            if drop_here_x or drop_here_y:
                widget = self.main_layout.takeAt(n)
                self.main_layout.insert_item(widget, n)
                break

        self.order_changed.emit()
        event.accept()


class CardLayout(QLayout):
    """Layout for displaying cards in a proper aspect ration and taking up size
    correctly.

    Spacing determines the contents margins of the layocustom layout with drag
    and drop between layouts pyqt6t.

    Attributes | Args:
        rows (int): Total rows to be displayed when showing added items. If at
            default (-1) it will uses the column count to determine row count.
        columns (int): Total columns for the layout. Defaults to 10.
        v_scroll, h_scroll (bool): Check if its okay to expanding in either
            direction. Will prioritize vertical scrolling if both values are
            true. Defaults to False.
        aspect_ratio (NamedTuple): Original aspect ratio from the cards used
            for sizing up the layout items
        card_items (list): Where the layout items are stored.
    """

    def __init__(
        self,
        parent: DeckWidget | QVBoxLayout,
        rows: int = -1,
        columns: int = 10,
        scroll: tuple[bool, bool] = (False, False),
    ) -> None:
        super().__init__()

        self._parent = parent
        self._rows = rows
        self._columns = max(columns, 1)
        self.v_scroll, self.h_scroll = scroll
        self.scrolling = self.v_scroll or self.h_scroll
        self._aspect_ratio = CardButton.ASPECT_RATIO
        self._card_items: list[QLayoutItem] = []

        marg = self.spacing()
        self.setContentsMargins(marg, marg, marg, marg)

    def addItem(self, cards: QLayoutItem | None) -> None:
        """Overriden abstract method for adding item to the list.

        Args:
            cards (QLayoutItem | None): Item to be added to the item_list.
        """
        if cards is None:
            return
        self._card_items.append(cards)

    def parent(self) -> DeckWidget | QVBoxLayout:
        """Returns the parent for extracting extra information.

        Returns:
            DeckWidget | QVBoxLayout: Parent of the layout
        """
        return self._parent

    def sizeHint(self) -> QSize:
        """Overrided abstract SizeHint method for keeping to size of the layout
        for minimum items in the cards.

        Returns:
            QSize: Minimum size of the layout.
        """

        width = 0
        height = 0
        spacing = self.spacing()

        for item in self._card_items:
            item_size_hint = item.widget().rect()  # type: ignore
            if self.h_scroll or width == 0 or not self.scrolling:
                width += item_size_hint.width() + spacing
            if self.v_scroll or height == 0 or not self.scrolling:
                height += item_size_hint.height() + spacing

        width += spacing
        height += spacing

        return QSize(width, height)

    def itemAt(self, index: int) -> QLayoutItem | None:
        """Overriden abstract method in order to select items in the layout.
        """
        try:
            return self._card_items[index]
        except IndexError:
            return

    def takeAt(self, index: int) -> QLayoutItem | None:
        """Overriden abstract method in order to remove items from the layout.
        """
        try:
            return self._card_items.pop(index)
        except IndexError:
            return

    def count(self) -> int:
        """For checking the size of the layout and managing sizes.

        Returns:
            int: How many items that have been added to the layout.
        """
        return len(self._card_items)

    def minimumSize(self) -> QSize:
        """Minimum Size of the layout based on the SizeHint which should be
        reimplemented in the future."""
        return self.sizeHint()

    def heightForWidth(self, width: int) -> int:
        """Returns the height in ratio of the given width.

        Args:
            width (int): Width of the current item.

        Returns:
            int: Height of the item scaled on the preset ratio.
        """
        return math.ceil(width * self._aspect_ratio.height)

    def widthForHeight(self, height: int) -> int:
        """Width of the item based on the height on the height of the item.

        Args:
            height (int): Height of the current item.

        Returns:
            int: Width of the item scaled on the preset ratio.
        """
        return math.ceil(height * self._aspect_ratio.width)

    def setGeometry(self, rect: QRect) -> None:
        """Main function of the layout which determines the sizing, direction
        and positioning of each layout item.

        *Will need a refactor in the future in order to be more flexible with a
            refactor of the sizhint and minimum size functions.
        *Also will need a refactor in order to clean the function a bit more.

        Args:
            rect (QRect): Size of the layout where to disperse the items on.
        """
        if not self.count():
            return super().setGeometry(rect)

        spacing = self.spacing()
        ver_spacing, hor_spacing, width, height = self.sizing(rect, spacing)

        size = QSize(width, height)
        pt = QPoint(spacing, spacing)

        for i, item in enumerate(self._card_items):
            if i % self.columns() == 0 and i:
                pt.setX(spacing)
                pt.setY(pt.y() + height + ver_spacing)
            item.setGeometry(QRect(pt, size))
            pt.setX(pt.x() + width + hor_spacing)

    def sizing(
        self,
        rect: QRect,
        spacing: int
    ) -> tuple[int, int, int, int]:
        """This calculates the sizing for the layout iself and spaces it out
        accordingly.

        *Will need a refactor in the future as the calculations.

        Args:
            rect (QRect): Area to take the size of the widget from.
            spacing (int): How much of a gap you need to add betwe

        Returns:
            tuple[int, int, int, int]: _description_
        """
        card_size = CardButton.BASE_SIZE
        full_height = rect.height()
        full_width = rect.width()

        ver_spacing = spacing
        hor_spacing = spacing

        if self.v_scroll:
            width = full_width // self.columns()
            width -= spacing * 2
            height = self.heightForWidth(width)

        elif self.h_scroll:
            height = full_height - spacing * 2
            width = self.widthForHeight(height)
            height = self.heightForWidth(width)

        else:
            full_height -= (spacing * 2)
            full_width -= (spacing * 2)
            height = full_height // self.rows()
            width = self.widthForHeight(height)
            height = self.heightForWidth(width)

            try:
                ver_spacing = (full_height % height) // self.rows()
                hor_spacing = (full_width % width) // self.columns()
            except ZeroDivisionError:
                pass

        width = max(width, card_size.width())
        height = max(height, card_size.height())

        return ver_spacing, hor_spacing, width, height

    def columns(self) -> int:
        """Returns a total amount of columns depening on what the row attribute
        was set at.

        Returns:
            int: Either a set amount of columns or the row implementation of
                the widget.
        """
        if self._rows < 1:
            return self._columns
        return math.ceil(self.count() / self.rows())

    def rows(self) -> int:
        """Total amount of rows inside the layout depedning on if they are set
        to 0.

        Returns:
            int: Row count depening on the preset rows or columns inside the
                layout.
        """
        if self._rows > 0:
            return self._rows
        return math.ceil(self.count() / self._columns)

    def insert_item(self, item: QLayoutItem | None, index: int):
        """Moves an item to the given index.

        Args:
            index (int): Index to move the item to.
        """
        if item is None:
            return
        self._card_items.insert(index, item)

    def widget_list(self) -> list[CardButton]:
        """Returns a list of widgets added to the layout converted from layout
        items.

        Returns:
            list[CardButton]: A list of CardButton to iterate over.
        """
        data = []
        for item in self._card_items:
            widget = item.widget()
            data.append(widget)

        return data


if __name__ == "__main__":
    pass
