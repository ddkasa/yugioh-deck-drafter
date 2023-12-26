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

import logging
import random
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final

from PyQt6.QtCore import QSignalBlocker, QSize, Qt, pyqtSlot
from PyQt6.QtGui import QCloseEvent, QKeyEvent
from PyQt6.QtWidgets import (QApplication, QCompleter, QDialog, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QProgressBar,
                             QProgressDialog, QPushButton, QSizePolicy,
                             QStackedWidget, QVBoxLayout, QWidget)

from yugioh_deck_drafter import util
from yugioh_deck_drafter.modules.base_widgets import (CardButton, CardLayout,
                                                      DeckSlider, DeckViewer)
from yugioh_deck_drafter.modules.ygo_data import (CardModel, CardSetModel,
                                                  DeckModel, DeckType,
                                                  ExtraMaterial, YugiObj)

if TYPE_CHECKING:
    from yugioh_deck_drafter.__main__ import MainWindow


@dataclass
class PackOpeningState:
    """Needed data for drafting decks with the Drafting Dialog.

    Attributes:
        opened_set_packs (int): Keeps track of how many pack bundles have been
            opened so far.
        total_packs (int): The total number of packs that have been opened so
            far.
        selections_per_pack (int): How many max selections the current pack has.
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
    selections_per_pack: int = field(default=0)
    selections_left: int = field(default=0)
    discard_stage_cnt: int = field(default=0)
    selections: list[CardButton | CardModel] = field(default_factory=list)


class DraftingDialog(QDialog):  # pylint: ignore[too-many-pulbic-methods]
    """Dialog for opening packs and managing drafting in general, as it has a
    core function that cycles and keep track of whats been added and removed in
    the meanwhile.

    Attributes:
        CARDS_PER_PACK (int): How many cards each pack contains.
        deck (DeckModel): Mostly for storing the selected card data and
            tranferring between widgets.
        drafting_model (DeckModel): Holds important drafting information for
            checking different stages of the drafting process.
        SET_ART_SIZE (QSize): For having a consistent size for set art when
            loading.

    Args:
        parent (MainWindow): For retrieving, managing and finalzing the
            drafting data.
        deck_name (str): Name of deck set by the user used for save pathh name
            later on.
        flags (Optional[WindowType]): Mostly for debugging and testing the
            class.
    """

    SET_ART_SIZE: Final[QSize] = QSize(400, 708)
    CARDS_PER_PACK: Final[int] = 9

    def __init__(
        self,
        parent: MainWindow,
        deck_name: str,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self.setModal(not parent.debug)

        self.setWindowTitle("Card Pack Opener")

        self.ygo_data: YugiObj = self.parent().yugi_pro

        self.deck: DeckModel = DeckModel(deck_name)
        self.drafting_model: PackOpeningState = PackOpeningState()
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
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
        self.set_art_widget.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
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
        self.loading_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
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
        1a. Returns back to the selection with a warnisave
        5. Removes the current cards from the layout.
        6. Selects the next pack and decrements the count.
        7. Generates the probabilities for the base cards in the set.
        8. Finally opens the pack by calling open_pack().
        """

        if self.view_widget.currentWidget() == self.loading_widget:
            return None

        if hasattr(self, "stretch"):
            self.drafting_layout.removeItem(self.stretch)
            self.setMinimumSize(self.size())

            del self.stretch

        if not self.proceed_set_check():
            return None

        self.view_widget.setCurrentWidget(self.loading_widget)
        if self.drafting_model.selections:
            self.add_card_to_deck()

        if self.check_discard_stage():
            try:
                self.discard_stage()
            except ValueError:
                self.view_widget.setCurrentWidget(self.drafting_widget)
                return None
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
                (mbutton.No | mbutton.Yes),
            )

            if ms_box == mbutton.Yes:
                self.preview_deck()

            return self.accept()

        if self.card_buttons:
            self.clean_layout()

        sel_packs = self.parent().selected_packs

        set_data = sel_packs[self.drafting_model.opened_set_packs]
        self.load_set_art()

        self.drafting_model.total_packs += 1

        (self.packs_opened.setText(f"Pack No.: {self.drafting_model.total_packs}"))
        self.current_pack.setText(f"Current Pack: {set_data.set_name}")

        if not set_data.probabilities:
            card_data = self.ygo_data.get_card_set_info(set_data)
            set_data.card_set = tuple(card_data)
            probabilities = self.ygo_data.generate_weights(set_data.set_name, card_data)
            set_data.probabilities = tuple(probabilities)

        if self.check_discard_stage():
            self.next_button.setText("Discard Stage")

        self.open_pack(set_data)
        set_data.count -= 1

        if set_data.count == 0:
            self.drafting_model.opened_set_packs += 1

        return None

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
        actual_selection -= extra_card_types + duplicates

        if actual_selection < self.drafting_model.selections_left:
            return True

        text = "Select at least {0} more cards."
        text = text.format(self.drafting_model.selections_left)
        logging.info(text)
        QMessageBox.warning(
            self, "Select More Cards", text, QMessageBox.StandardButton.Ok
        )
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
            set_art = set_art.scaled(
                self.SET_ART_SIZE.width() // 2,
                self.SET_ART_SIZE.height() // 2,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
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
        """Opens a pack with probablities supplied and adds its to the layout.

        The last card get new probabilities as its atleast a rare.

        Args:
            set_data (YGOCardSet): Cards set which contains all the cards,
                probabilities and set info.
        """
        debug = f"Opening a pack from {set_data.set_name}.".center(60, "-")
        logging.debug(debug)

        self.drafting_model.selections_left += 2
        sel_left = self.drafting_model.selections_left
        self.drafting_model.selections_per_pack = sel_left
        logging.debug(
            "%s Card Selection(s) Available.", self.drafting_model.selections_per_pack
        )

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

    def select_pack_card(self, set_data: CardSetModel, pack_index: int) -> CardModel:
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
            rprob = self.ygo_data.generate_weights(
                set_data.set_name, rare_cards, extra=True
            )
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

    def update_item_selection(self, item: CardButton) -> None:
        """Updates the given item selection status.

        Args:
            item (CardButton): Item to be updated from the selection
        """
        with QSignalBlocker(item):
            item_in = item in self.drafting_model.selections
            fus_mon = self.ygo_data.check_extra_monster(item.card_model)

            if (
                item.isChecked()
                and not self.check_card_count(item.card_model) == 3
                and (self.drafting_model.selections_left > 0 or fus_mon)
            ):
                if not item_in:
                    logging.debug("Adding card %s", item.accessibleName())
                    self.add_card_to_selection(item)

            elif not item.isChecked() and item_in:
                logging.debug("Removing card %s", item.accessibleName())
                self.remove_card_from_selection(item)

            elif not item_in and not fus_mon:
                item.setChecked(False)

            item.setDisabled(
                (self.check_card_count(item.card_model) == 3
                and not item.isChecked())
                or item.assocc_added
            )

            self.update_counter_label()

        QApplication.processEvents()

    def add_card_to_selection(self, card_model: CardModel | CardButton) -> bool:
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

        return True

    def remove_card_from_selection(self, card_model: CardModel | CardButton) -> None:
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
        """Selections left indicator updater and selection list tooltip."""
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
            DeckType.SIDE: self.deck.side,
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
        discard += self.drafting_model.total_packs // 5
        dialog = DeckViewer(self, discard)

        dialog.setWindowTitle("Card Removal Stage")

        if self.parent().debug:
            dialog.show()
        else:
            confirmation = dialog.exec()
            if confirmation:
                self.deck: DeckModel = dialog.new_deck
                self.drafting_model.discard_stage_cnt += 1
            else:
                raise ValueError("Discard Not Successful")

            self.auto_save(self.drafting_model.discard_stage_cnt)

    def preview_deck(self):
        """Spawns the deck viewer for previewing the deck on demand."""

        deck = DeckViewer(self)
        deck.exec()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Key override to prevent the drafter from accidently quitting out of
        the window or misclicking.

        Args:
            event (QKeyEvent | None): Event object to take information from.
        """
        if event is None:
            return super().keyPressEvent(event)

        KEY = Qt.Key
        if event.key() in {KEY.Key_Escape, KEY.Key_Space}:
            return None

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
                    item.assocc_added = False

                item = item.card_model

        sel_left = self.drafting_model.selections_per_pack
        self.drafting_model.selections_left = sel_left

        self.update_counter_label()

    def minimumSize(self) -> QSize:
        """Minimum size for the drafting for clearer reading.

        Returns:
            QSize: Minimum size of the window based on 1080p resolution.
        """
        return QSize(1344, 824)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
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
            (QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes),
        )

        if close == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

        return

    def count_card_type(
        self, card_type: str, group: list[CardModel] | list[CardButton]
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
        label: str,
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

        self.scroll_widget = DeckSlider(None, self)  # type: ignore
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
        """Loads the next set of maximum 20 cards."""

        max_files = min(20, len(self.data))
        progress_dialog = QProgressDialog(
            "Loading Cards", None, 0, max_files, self.parent()
        )
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

    def load_cardbutton(self, index: int = 0, check: bool = False) -> CardButton:
        """Loads the next single card from the saved data.

        Args:
            index (int, optional): Index of the card to us. Defaults to 0.
            check (bool, optional): Checks the card if its True.
                Defaults to False.

        Returns:
            CardButton: For scrolling the view to the item.
        """
        CMP = Qt.ContextMenuPolicy
        card_button = CardButton(
            self.data.pop(index), self.parent(), sub_deck=DeckType.SEARCH
        )
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
        (
            self.search_box.editingFinished.connect(
                lambda: self.highlight_search(self.search_box.text())
            )
        )

        return None

    def highlight_search(self, name: str) -> None:
        """Hightlights the item searched for inside the search box and toggls
        the button to the checked state.

        Args:
            name (str): Name of the card to highlight.
        """
        for i, button in enumerate(self.scroll_widget.main_layout.widget_list()):
            if button.accessibleName() == name:
                button.setChecked(True)
                return

        for i, item in enumerate(self.data):
            if item.name == name:
                new_button = self.load_cardbutton(i, True)
                sbar = self.scroll_widget.horizontalScrollBar()
                sbar.setValue(sbar.maximum() + new_button.width())  # type: ignore
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
            QMessageBox.warning(self, "Select more cards.", "Select at least one card.")
            return
        elif len(self.chosen_items) > self.extra_mats.count:
            QMessageBox.warning(
                self, "Too Many Cards", f"Maximum {len(self.chosen_items)} Allowed"
            )
            return

        return super().accept()


if __name__ == "__main__":
    pass
