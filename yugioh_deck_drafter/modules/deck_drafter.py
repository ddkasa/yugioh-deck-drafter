from __future__ import annotations

import logging
import math
import random
import re
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, Optional

from PyQt6.QtCore import (QMimeData, QPoint, QRect, QRectF, QSignalBlocker,
                          QSize, Qt, pyqtSignal, pyqtSlot)
from PyQt6.QtGui import (QBrush, QCursor, QDrag, QDragEnterEvent, QCloseEvent,
                         QDropEvent, QFont, QImage, QKeyEvent, QMouseEvent,
                         QPainter, QPaintEvent, QPen, QPixmap)
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCompleter, QDialog,
                             QHBoxLayout, QLabel, QLayout, QLayoutItem,
                             QLineEdit, QMenu, QMessageBox, QProgressBar,
                             QPushButton, QScrollArea, QSizePolicy, QWidget,
                             QStackedWidget, QStyle, QStyleOptionButton,
                             QVBoxLayout)

from yugioh_deck_drafter import util
from yugioh_deck_drafter.modules.ygo_data import (CardModel, CardSetModel,
                                                  DeckModel)

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
       core function that cycles and keep track of whats been added and
       removed in the meanwhile.

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

    def __init__(self, parent: MainWindow, deck_name: str,
                 flags=Qt.WindowType.Dialog):
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

        self.card_layout = CardLayout(2)
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

        self.current_pack = QLabel("Current Pack: ")
        self.current_pack.setObjectName("indicator")
        self.button_layout.addWidget(self.current_pack, 20)

        self.button_layout.addStretch(60)

        self.next_button = QPushButton("Start")
        self.next_button.pressed.connect(self.sel_next_set)
        self.button_layout.addWidget(self.next_button, 20)

        self.drafting_layout.addLayout(self.button_layout)

        self.drafting_widget.setLayout(self.drafting_layout)

        return self.drafting_widget

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
        8. Finally opens the pack by calling open_pack().
        """

        if self.view_widget.currentWidget() == self.loading_widget:
            return

        if hasattr(self, "stretch"):
            self.drafting_layout.removeItem(self.stretch)
            self.setMinimumSize(self.size())

            del self.stretch

        if self.drafting_model.selections_left > 0:
            text = "Select at least {0} more cards."
            text = text.format(self.drafting_model.selections_left)
            logging.error(text)
            QMessageBox.warning(self, "Select More Cards", text,
                                QMessageBox.StandardButton.Ok)
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

            self.card_buttons.append(card)
            card.toggled.connect(self.update_selection)
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

    def update_selection(self):
        """Check if there are any slections left and checks and for duplicate
        cards.

        Removes the selections if there are three of more of the card present
        in the deck.
        """
        logging.debug("Updating Selection")

        for item in list(self.card_buttons):
            item.blockSignals(True)

            item_in = item in self.drafting_model.selections
            three = self.check_card_count(item.card_model) == 3
            fus_monster = self.ygo_data.check_extra_monster(item.card_model)

            if (item.isChecked()
               and not three
               and (self.drafting_model.selections_left > 0 or fus_monster)):
                if not item_in:
                    logging.debug("Adding card %s", item.accessibleName())
                    self.add_card_to_selection(item)

            elif not item.isChecked() and item_in:
                logging.debug("Removing card %s", item.accessibleName())
                self.remove_card_from_selection(item)

            elif not item_in and not fus_monster:
                item.setChecked(False)

            self.update_counter_label()
            item.blockSignals(False)

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

        remaining = f"Remaining Picks: {self.drafting_model.selections_left}"
        self.card_picks_left.setText(remaining)
        picked = len(self.deck.main) + len(self.deck.side)

        self.cards_picked.setText(f"Card Total: {picked}")
        tip = f"Main Deck: {len(self.deck.main)}\n"
        tip += f"Extra Deck: {len(self.deck.extra)}\n"
        tip += f"Side Deck: {len(self.deck.side)}"
        self.cards_picked.setToolTip(tip)

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

    def discard_stage(self):
        """Calculates the amount to be discarded and starts the dialog."""

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

    def preview_deck(self):
        """Spawns the deck viewer for previewing the deck on demand."""
        deck = DeckViewer(self)
        deck.exec()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Key override to prevent the drafter from accidently quitting out of
        the window or misclicking.
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
            (QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Yes)
            )
        if close == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()


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
        viewer: Optional['DeckViewer'] = None
    ) -> None:
        super().__init__(parent=parent)

        self.drafting_dialog = parent

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if isinstance(viewer, DeckViewer):
            self.setAcceptDrops(True)

        self.viewer = viewer  # type: ignore
        self.card_model = data

        self.rarity_color = parent.ygo_data.RARITY_COLOURS[data.rarity]

        self.setAccessibleName(data.name)
        self.setAccessibleDescription(data.description)

        self.setBaseSize(self.BASE_SIZE)
        desc = util.new_line_text(data.description, 100)

        ttip = data.name
        if data.level:
            ttip += f" | Level: {data.level}"
        if data.attribute:
            ttip += f" | Attribute: {data.attribute}"
        ttip += f"\n\n{desc}"
        if data.attack is not None:
            ttip += f"\n\nATK: {data.attack}  |  DEF: {data.defense}"
        self.setToolTip(ttip)

        self.setObjectName("card_button")

        QSP = QSizePolicy.Policy

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)

        self.setSizePolicy(QSP.MinimumExpanding, QSP.MinimumExpanding)
        self.setCheckable(True)

        self.assocc = self.filter_assocciated()

        self.image = parent.ygo_data.get_card_art(self.card_model)

    def minimumSize(self) -> QSize:
        """Overriden minimum size of the widget in order to stay legible.

        Returns:
            QSize: item desribes the minimum size of the widget.
        """
        return self.BASE_SIZE

    def sizeHint(self) -> QSize:
        return self.minimumSize()

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

        filt_matches = set()
        for item in matches:
            data = self.parent().ygo_data.grab_card(item)
            if data is None:
                continue
            filt_matches.add(item)

        return filt_matches

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
            return None

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
        if self.isChecked():
            pen.setColor(Qt.GlobalColor.red)
            pen.setWidthF(pen_width)
            painter.setPen(pen)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            pen.setColor(Qt.GlobalColor.yellow)
            pen.setWidth(pen_width)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)

        new_rect = self.rect_generator(rect, pen_width)
        painter.drawRect(new_rect)

        if self.card_model.rarity != "Common":
            painter.save()
            new_rect = self.rect_generator(rect, pen_width)
            cmp = QPainter.CompositionMode.CompositionMode_ColorDodge
            painter.setCompositionMode(cmp)
            pen.setColor(self.rarity_color)
            pen.setWidthF(pen_width)
            painter.setPen(pen)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(new_rect)
            painter.restore()

        if not self.isChecked():
            return None
        if isinstance(self.viewer, DeckViewer) and self.viewer.discard:
            rect = self.rect()
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topRight())
        return None

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
            self.discard_stage_menu(menu)
        else:
            if self.parent().drafting_model.selections_left < 1:
                return

            self.drafting_menu(menu)

        menu.exec(pos)

    def drafting_menu(self, menu: QMenu) -> None:
        """Menu that pop ups when drafting the deck.

        Args:
            menu (QMenu): Menu to add the additonal actions to.
        """
        if self.card_model.card_type == "Fusion Monster":
            poly = "Polymerization"

            if self.parent().drafting_model.selections_left > 1:
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
        """Menu that pop ups when in the discard stage of drafting.

        Args:
            menu (QMenu): Menu to add the additonal actions to.
        """

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
            if self.card_model.card_type == "Fusion Monster":
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
            logging.error("Card does not exist.")
            self.setChecked(False)
            self.setDisabled(False)
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

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        """Movement function for when dragging cards between decks."""
        if event is None:
            return

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

        self.deck: list[CardButton] = []
        self.extra: list[CardButton] = []
        self.side: list[CardButton] = []

        self.main_layout = QVBoxLayout()

        self.deck_area = DeckSlider("Main Deck", self)
        self.main_layout.addWidget(self.deck_area, 60)
        self.fill_deck(parent.deck.main, self.deck, self.deck_area)

        self.extra_deck_widget = DeckSlider("Extra Deck", self)
        self.main_layout.addWidget(self.extra_deck_widget, 20)
        self.fill_deck(parent.deck.extra, self.extra, self.extra_deck_widget)

        self.side_deck_widget = DeckSlider("Side Deck", self)
        self.main_layout.addWidget(self.side_deck_widget, 20)
        self.fill_deck(parent.deck.side, self.side, self.side_deck_widget)

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

    def fill_deck(self, cards: list[CardModel], container: list,
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

        QSP = QSizePolicy.Policy
        QAF = Qt.AlignmentFlag
        row = 0
        column = 0
        while cards:
            if column % self.MAX_COLUMNS == 0 and column:
                row += 1
                column = 0


            card = cards.pop(0)

            card_button = CardButton(card, self.parent(), self)

            self.connect_scroll_bar(scroll_bar, card_button)

            if not self.discard:
                card_button.setCheckable(False)
            else:
                card_button.toggled.connect(self.removal_count)
                card_button.setChecked(check)

            card_button.setSizePolicy(QSP.Maximum, QSP.Maximum)
            container.append(card_button)

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
            return None

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
            self.main_deck_count.setText(f"Main Deck: {mcount}")

        extra = len(self.extra)
        with QSignalBlocker(self.extra_deck_count):
            self.extra_deck_count.setText(f"Extra Deck: {extra}")

        side = self.count("side")
        with QSignalBlocker(self.side_deck_count):
            self.side_deck_count.setText(f"Side Deck: {side}")

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

        self.new_deck = DeckModel(self.parent().deck.name)

        filter_items(self.new_deck.main, self.deck)
        filter_items(self.new_deck.extra, self.extra)
        filter_items(self.new_deck.side, self.side)

        return super().accept()


class CardSearch(QDialog):
    """Dialog for search for different subtypes of a card when the card desc
    doesn't have a description itself.

    Args:
        attribute (str): The name of the subtype to search for.
        subtype (subtype): What subtype to look for in the database.
        parent (DraftingDialog): For searching capability and checking
            duplicates.
    """

    def __init__(
        self,
        attribute: str,
        subtype: str,
        parent: DraftingDialog
    ) -> None:
        super().__init__(parent)

        self.setMinimumSize(960, 540)

        self.total_cards = 1

        self.data = parent.ygo_data.card_arche_types(attribute, subtype)

        if not isinstance(self.data, list):
            self.reject()
            return

        self.main_layout = QVBoxLayout()

        self.search_box = QLineEdit()
        self.main_layout.addWidget(self.search_box)

        self.scroll_widget = DeckSlider(subtype + " Search", self)

        self.card_buttons: list[CardButton] = []
        self.card_button_group = QButtonGroup()
        self.card_button_group.setExclusive(True)

        CMP = Qt.ContextMenuPolicy

        for item in self.data:
            card_button = CardButton(item, parent, None)
            card_button.setContextMenuPolicy(CMP.NoContextMenu)
            self.card_buttons.append(card_button)
            self.card_button_group.addButton(card_button)
            self.scroll_widget.main_layout.addWidget(card_button)

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

    def fill_search(self) -> None:
        """Pre-cached the search values which matched to the name of the
        searched subtype.
        """

        if not isinstance(self.data, list):
            return self.reject()

        names = [card["name"] for card in self.data]

        completer = QCompleter(names)
        completer.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)

        self.search_box.setCompleter(completer)
        self.search_box.editingFinished.connect(lambda: self.highlight_search)

    def highlight_search(self):
        """Hightlights the item searched for inside the search box and toggls
        the button to the checked state.
        """
        name = self.search_box.text()
        for item in self.card_buttons:
            if item.accessibleName() == name:
                item.setChecked(True)
                return

    def accept(self) -> None:
        """Overriden except method in order to highlight and return the correct
        card model.
        """
        for item in self.card_buttons:
            if item.isChecked():
                self.selected_item = item.card_model
                break
        else:
            self.selected_item = self.card_buttons[0].card_model

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
                 deck_type: str,
                 parent: DeckViewer | CardSearch) -> None:
        super().__init__(parent)

        QSP = QSizePolicy.Policy
        SBP = Qt.ScrollBarPolicy
        self.setHorizontalScrollBarPolicy(SBP.ScrollBarAlwaysOff)

        if deck_type != "Main Deck":
            self.main_widget = DeckDragWidget(deck_type, self)
            self.main_layout = self.main_widget.main_layout

            self.setVerticalScrollBarPolicy(SBP.ScrollBarAlwaysOff)
            self.main_widget.setSizePolicy(QSP.Preferred, QSP.Ignored)
        else:
            self.setVerticalScrollBarPolicy(SBP.ScrollBarAlwaysOn)
            self.main_widget = DeckWidget(deck_type, self)
            self.main_layout = CardLayout(parent=self.main_widget,
                                          scroll=(True, False))
            self.main_widget.setLayout(self.main_layout)
            self.main_widget.setSizePolicy(QSP.Fixed, QSP.Preferred)

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
    # """

    def __init__(self, deck_type: str, parent: DeckSlider):
        super().__init__(parent)
        self.scroll_area = parent
        self.name = deck_type

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
    """

    orderChanged = pyqtSignal()

    def __init__(self, deck_type: str, parent: DeckSlider):
        super(DeckDragWidget, self).__init__(deck_type, parent)
        self.name = deck_type
        self.setAcceptDrops(True)

        self.main_layout = CardLayout(rows=1,
                                      parent=self,
                                      scroll=(False, True))
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


class CardLayout(QLayout):
    """Layout for displaying cards in a proper aspect ration and taking up size
    correctly.
    
    Spacing determines the contents margins of the layout.

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
        rows: int = -1,
        columns: int = 10,
        scroll: tuple[bool, bool] = (False, False),
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._rows = rows
        self._columns = max(columns, 1)
        self.v_scroll, self.h_scroll = scroll
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

    def sizeHint(self) -> QSize:
        """Overrided abstract SizeHint method for keeping to size of the layout
        for minimum item sin the cards.

        Returns:
            QSize: Minimum size of the layout.
        """
        # This might need overhaul in the future in order to be more flexible.
        card_size = CardButton.BASE_SIZE
        width = (card_size.width() + self.spacing()) * self.columns()
        height = (card_size.height() + self.spacing()) * self.rows()
        size_hint = QSize(width, height)
        return size_hint

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

        full_height = rect.height()
        full_width = rect.width()

        ver_spacing = spacing
        hor_spacing = spacing

        if self.v_scroll:
            width = full_width // self.columns()
            width -= spacing
            height = self.heightForWidth(width)
        elif self.h_scroll:
            height = full_height
            height -= spacing
            width = self.widthForHeight(height)
        else:
            full_height -= (spacing * 2)
            full_width -= (spacing * 2)
            height = full_height // self.rows()
            width = self.widthForHeight(height)
            height = self.heightForWidth(width)

            if self._rows > 0:
                ver_spacing = (full_height % height) // self.rows()
                hor_spacing = (full_width % width) // self.columns()

        size = QSize(width, height)
        pt = QPoint(spacing, spacing)

        for i, item in enumerate(self._card_items):
            if i % self.columns() == 0 and i:
                pt.setX(spacing)
                pt.setY(pt.y() + height + ver_spacing)
            item.setGeometry(QRect(pt, size))
            pt.setX(pt.x() + width + hor_spacing)

        self.update()

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
