"""Main Deck Builder Python Script"""


from typing import Final, Optional, Iterable
import logging
import sys
import traceback
from datetime import date
from pathlib import Path
from functools import partial
import enum

from PyQt6.QtCore import (Qt, pyqtSlot, QPoint, QSignalBlocker, QDate)

from PyQt6.QtWidgets import (QApplication, QPushButton, QWidget,
                             QComboBox, QVBoxLayout, QListWidget, QSlider,
                             QHBoxLayout, QListWidgetItem, QSpinBox, 
                             QLabel, QFileDialog, QMenu, QMessageBox,
                             QInputDialog, QDialog, QFormLayout, QDateEdit)

from PyQt6.QtGui import (QPixmapCache, QCursor, QStandardItemModel,
                         QAction)

from yugioh_deck_drafter import util
from yugioh_deck_drafter.modules.deck_drafter import DraftingDialog
from yugioh_deck_drafter.modules.ygo_data import (DeckModel, CardSetModel,
                                                  YugiObj, CardSetClass,
                                                  CardSetFilter)


class MainWindow(QWidget):
    """Main Window Class managing Pack Selection and general utilities.

    Attributes:


    Args:
        QWidget (_type_): _description_
    """

    DEFAULT_PACK_COUNT: Final[int] = 10
    PACK_MAX: Final[int] = 40
    OMEGA_PATH = Path(r"C:\Program Files (x86)\YGO Omega")
    DEFAULT_IMPORT = OMEGA_PATH / r"YGO Omega_Data\Files\Imports"

    DEFAULT_FILTER = CardSetFilter()

    def __init__(self, debug: bool = False):
        super().__init__()

        self.debug = debug
        self.yugi_pro = YugiObj()

        self.selected_packs: list[CardSetModel] = []
        self.p_count: int = 0
        self.init_ui()

        self.update_pack_count()
        self.filter_packs(True)

    def init_ui(self) -> None:
        """Intializes layouts and widgets for the UI."""
        self.pack_filter = None

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self.select_layout = QHBoxLayout()
        self.main_layout.addLayout(self.select_layout)

        CMP = Qt.ContextMenuPolicy.CustomContextMenu

        self.select_pack = QComboBox()
        self.select_layout.addWidget(self.select_pack, 50)
        self.select_pack.setContextMenuPolicy(CMP)
        (self.select_pack.customContextMenuRequested
         .connect(self.pack_list_context_menu))

        self.select_layout.addStretch(10)

        self.no_packs = QSlider()
        self.no_packs.setSingleStep(10)
        self.no_packs.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.no_packs.setTickInterval(10)
        self.no_packs.setOrientation(Qt.Orientation.Horizontal)
        self.no_packs.setMinimum(10)
        self.no_packs.setValue(self.DEFAULT_PACK_COUNT)
        self.no_packs.setMaximum(self.PACK_MAX)
        self.select_layout.addWidget(self.no_packs, 40)
        self.no_packs.setContextMenuPolicy(CMP)
        (self.no_packs.customContextMenuRequested
         .connect(self.pack_list_context_menu))

        self.no_pack_indi = QSpinBox()
        self.no_pack_indi.setValue(self.DEFAULT_PACK_COUNT)
        self.no_pack_indi.setSingleStep(5)
        self.no_pack_indi.setMinimum(5)
        self.no_pack_indi.setMaximum(self.PACK_MAX)
        self.select_layout.addWidget(self.no_pack_indi, 1)
        self.no_pack_indi.setContextMenuPolicy(CMP)
        (self.no_pack_indi.customContextMenuRequested
         .connect(self.pack_list_context_menu))

        self.sel_card_set_list = QListWidget()
        self.sel_card_set_list.setContextMenuPolicy(CMP)
        (self.sel_card_set_list.customContextMenuRequested
         .connect(self.list_context_menu))
        self.main_layout.addWidget(self.sel_card_set_list)

        self.button_layout = QHBoxLayout()

        self.start_button = QPushButton("START")
        self.button_layout.addWidget(self.start_button)

        self.button_layout.addStretch(20)

        self.pack_count = QLabel(f"Pack Count: {self.p_count}")
        self.pack_count.setObjectName("indicator")
        self.button_layout.addWidget(self.pack_count)

        self.button_layout.addStretch(20)

        self.reset_button = QPushButton("RESET")
        self.button_layout.addWidget(self.reset_button)
        self.reset_button.pressed.connect(self.reset_selection)

        self.main_layout.addLayout(self.button_layout)

        self.select_pack.currentIndexChanged.connect(self.add_item)
        self.no_packs.valueChanged[int].connect(self.update_indi)
        self.no_pack_indi.valueChanged[int].connect(self.update_indi)
        self.start_button.pressed.connect(self.start_drafting)

    @pyqtSlot()
    def list_context_menu(self):
        """Create and display a context menu for managing the pack list widget.

        This function generates a context menu when triggered at a specific
        position within the widget.
        The context menu provides an option to remove an item from the
        list, triggered by selecting 'Remove Item'.
        """
        pos = QCursor().pos()

        menu = QMenu(self.sel_card_set_list)

        remove_item = menu.addAction("Remove Item")
        if remove_item is not None:
            item_pos = self.sel_card_set_list.mapFromGlobal(pos)
            item = self.sel_card_set_list.itemAt(item_pos)
            remove_item.setDisabled(item is None)
            if item is not None:
                remove_item.triggered.connect(lambda: self.remove_item(item))

        random_packs = menu.addAction("Randomize Packs")
        if random_packs is not None:
            random_packs.triggered.connect(self.randomize_packs)

        menu.exec(pos)

    @pyqtSlot()
    def pack_list_context_menu(self):
        pos = QCursor().pos()
        menu = QMenu(self.sel_card_set_list)

        pack_filter = QAction("Filter Packs")
        pack_filter.triggered.connect(self.filter_packs)
        menu.addAction(pack_filter)

        reset_filter = QAction("Reset Filter")
        reset_filter.setDisabled(self.filter == self.DEFAULT_FILTER)
        reset_filter.triggered.connect(lambda: self.filter_packs(True))
        menu.addAction(reset_filter)

        menu.exec(pos)

    @pyqtSlot()
    def add_item(self) -> None:
        """
        This function retrieves the selected pack from the UI and adds it to
        the selection list while managing the associated indicators.
        """
        label = self.select_pack.currentText()
        if label in self.selected_packs:
            return

        index = self.select_pack.currentIndex()
        data = self.yugi_pro.card_set[index]

        cnt = self.no_pack_indi.value()

        item = QListWidgetItem(f"{cnt}x {label}")
        self.sel_card_set_list.addItem(item)

        data.count = cnt
        self.selected_packs.append(data)

        self.update_pack_count()


    @pyqtSlot()
    def remove_item(self, item: QListWidgetItem) -> None:
        """Remove an item from the pack list based on the provided position.

        This function identifies the item in the pack list widget based on the
        given position.
        If no item is found at that position, it logs a debug message and
        exits.
        Upon successful identification, it removes the item from the list,
        updates the associated data, and refreshes the pack count.

        Args:
            pos (QPoint): The position from which the item removal action is
            triggered.
        """
        row = self.sel_card_set_list.row(item)
        removed_item = self.sel_card_set_list.takeItem(row)
        if removed_item is None:
            return
        cnt, label = removed_item.text().split("x ")

        for index, value in enumerate(self.selected_packs):
            if value.set_name == label and value.count == cnt:
                self.selected_packs.pop(index)
                break

        self.update_pack_count()

    def update_indi(self, value: int) -> None:
        """Updates pack count indicators depending on the values provided
        which determine how many packs get added at a time.

        Args:
            value (int): the updated value set by the widget.
        """
        with (QSignalBlocker(self.no_packs)
             and QSignalBlocker(self.no_pack_indi)):
            self.no_packs.setValue(value)
            self.no_pack_indi.setValue(value)

    def update_pack_count(self) -> None:
        """Updates pack count of the selected packs when the values are
           changed.
        """
        self.p_count = 0
        for pack in self.selected_packs:
            self.p_count += pack.count

        self.pack_count.setText(f"Pack Count: {self.p_count}")

    @pyqtSlot()
    def start_drafting(self) -> None:
        """Starts the drafting process.

           Checks if there are 40 packs selected first and asks for a Deck
           Name.
           Begins the drafting dialog if conditions are met which will stay in
           this func until the process is finished.
        """

        if self.p_count != self.PACK_MAX:
            msg = "Make sure you have {0} packs selected."
            QMessageBox.information(self, "Not Enough Packs",
                                    msg.format(self.PACK_MAX))
            return

        name_dia = QInputDialog(self)
        name_dia.setWindowTitle("Deck Name")
        name_dia.setLabelText("Choose a name for your deck.")
        deck_name = name_dia.textValue()

        logging.info("Opening Selection Dialog.")
        dialog = DraftingDialog(self, deck_name)

        if dialog.exec():
            if self.DEFAULT_IMPORT.exists():
                path = self.DEFAULT_IMPORT
            else:
                file_dia = QFileDialog(self)
                file_dia.setWindowTitle("Select a Folder")
                while True:
                    if file_dia.exec():
                        if file_dia.directory().exists():
                            break

                path = Path(str(file_dia.directory()))

            self.save_deck_dialog(dialog.deck, path)

            QMessageBox.information(self, "File Saved",
                                    f"File was saved to {path}!",
                                    QMessageBox.StandardButton.Ok)
        return

    def save_deck_dialog(self, deck: DeckModel, path: Path) -> None:
        """Converts and saves the provided deck to path.

        Sanitizes the provided path(Path) first and then converts the deck to
        a str according to the .ydk format.

        Args:
            deck (DeckModel): Datamodel containing all the selected cards
                including the side/extra deck.
            path (Path): Path to where the YDK file will be saved.
        """
        deck_name = util.sanitize_file_path(deck.name)
        file_name = Path(f"{deck_name}.ydk")
        file_path = path / file_name
        deck_file = self.yugi_pro.to_ygodk_format(deck)

        with file_path.open("w", encoding="utf-8") as file:
            file.write(deck_file)

    @pyqtSlot()
    def reset_selection(self) -> None:
        """Resets pack Selection to empty and clears out the rest of cache."""
        logging.info("Resetting app to defaults.")

        self.selected_packs = []
        self.sel_card_set_list.clear()
        self.update_pack_count()

    @pyqtSlot()
    def randomize_packs(self) -> None:
        """Launches a dialog for randomizing card_set picks."""

        dialog = RandomPacks(self)
        dialog.show()

    @pyqtSlot(bool)
    def filter_packs(self, reset: bool = False):
        """For filtering out unwanted packs from selection or resetting the
        current selection"""

        card_set = self.yugi_pro.card_set.copy()

        if reset:
            self.filter = self.DEFAULT_FILTER
            self.add_packs_to_selection(card_set)
            return

        dialog = PackFilterDialog(self, card_set, self.filter)

        if dialog.exec():
            self.filter = dialog.filter
            new_sets = dialog.filter_cards(dialog.filter)
            self.add_packs_to_selection(new_sets)

    def add_packs_to_selection(self, card_set: list[CardSetModel]) -> None:
        """Clears and adds a new card set to the dropdown selection menu."""

        with QSignalBlocker(self.select_pack):
            self.select_pack.clear()
            self.current_card_set = card_set
            packs = [item.set_name for item in card_set]
            self.select_pack.addItems(packs)


class PackFilterDialog(QDialog):
    """Filter dialog for filtering out packs from the selection Dropdown.

    Filters out based on total cards in a pack, pack release date and pack
    type.

    Attributes:
        min_count (int): Minimum amount of cards in a card set.
        max_date (date): Maximum date to filter out the card set with.
        pack_types (list): What type of card sets to include in the selection.

    Args:
        parent (parent): Widget to parent the dialog to and access additonal
            information.

    """

    def __init__(self, parent: MainWindow, card_set: list[CardSetModel],
                 previous_filter: CardSetFilter) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Filter Sets")
        self.setModal(False)
        self.card_set = card_set

        self.main_layout = QVBoxLayout()

        self.form = QFormLayout()
        self.main_layout.addLayout(self.form)

        self.min_card_count = QSpinBox()
        self.min_card_count.setMinimum(1)
        self.min_card_count.setValue(previous_filter.card_count)
        (self.min_card_count
         .setToolTip("Minimum card threshold allowed inside a set."))
        self.form.addRow("Minimum Cards", self.min_card_count)

        self.max_date = QDateEdit()
        self.max_date.setDate(previous_filter.set_date)
        self.max_date.setToolTip("Filter out packs after this date.")
        self.form.addRow("Max Date", self.max_date)

        self.checkable_items = CheckableListWidget()
        self.checkable_items.addItems(CardSetClass,
                                      previous_filter.set_classes)
        self.form.addRow("Card Sets", self.checkable_items)

        self.button_layout = QHBoxLayout()

        self.close_button = QPushButton("Close")
        self.close_button.pressed.connect(self.close)
        self.button_layout.addWidget(self.close_button)

        self.button_layout.addStretch(20)

        self.filter_button = QPushButton("Filter Sets")
        self.filter_button.pressed.connect(self.accept)
        self.button_layout.addWidget(self.filter_button)

        self.main_layout.addLayout(self.button_layout)

        self.setLayout(self.main_layout)

    def create_filter(self) -> CardSetFilter:
        checked_classes = self.checkable_items.checked_items_to_set()
        checked_enums = set()

        for item in checked_classes:
            enum_item = CardSetClass[item.replace(" ", "_")]
            checked_enums.add(enum_item)

        card_filter = CardSetFilter(self.min_card_count.value(),
                                    self.max_date.date().toPyDate(),
                                    checked_enums)
        return card_filter

    def filter_cards(self, pack_filter: CardSetFilter) -> list[CardSetModel]:
        filt_func = partial(self.parent().yugi_pro.filter_out_card_sets,
                            set_filter=pack_filter)
        new_sets = filter(filt_func, self.card_set)

        return list(new_sets)

    def accept(self) -> None:
        self.filter = self.create_filter()
        return super().accept()

    def parent(self) -> MainWindow:
        """Overriden method to avoid type hint issues."""
        return super().parent()  # type: ignore


class RandomPacks(PackFilterDialog):
    """Randomizes and pick random packs with certain constraints selected which
    filter through all the sets.

    Attributes:
        pack_increments (int): How many packs per random set to add.
        total_packs (int): How many packs to add in total.

    Args:
        parent (parent): Widget to parent the dialog to and access additonal
            information.
    """
    def __init__(self, parent: MainWindow, card_set: list[CardSetModel],
                 previous_filter: CardSetFilter) -> None:
        super().__init__(parent=parent, card_set=card_set,
                         previous_filter=previous_filter)
        self.setWindowTitle("Randomise Sets")

        self.total_packs = QSpinBox()
        self.total_packs.setValue(5)
        self.total_packs.setMinimum(5)
        self.total_packs.setMaximum(20)
        self.total_packs.setSingleStep(5)
        (self.total_packs
         .setToolTip("Total packs to be added to the selection."))
        self.form.addRow("Min Increments", self.total_packs)

        self.pack_increments = QSpinBox()
        self.pack_increments.setValue(5)
        self.pack_increments.setMinimum(5)
        self.pack_increments.setMaximum(40)
        self.pack_increments.setSingleStep(5)
        self.form.addRow("Pack Count", self.pack_increments)

        self.filter_button.setText("Randomise")
        self.filter_button.disconnect()
        self.filter_button.pressed.connect(self.randomise_packs)

    def randomise_packs(self) -> None:
        """Randomises packs and adds sets to the MainWindow card set list based
        on the values chosen in the GUI"""
        self.parent().yugi_pro.card_set

        new_filter = self.create_filter()
        card_set = self.filter_cards(new_filter)
        
        


class CheckableListWidget(QListWidget):
    """QListWidget subclass for allowing selectable filters with checkboxes.

    Methods:
        addItems: Overriden parent method in order to clean input and add
            checkboxes to the items.
        checked_items_to_list: Quick function for return checked items.
    """

    def __init__(self) -> None:
        super().__init__()

    def addItems(self, items: set[str | None] | enum.EnumMeta,
                 set_classes: set[CardSetClass]) -> None:

        for item in items:
            if item is None:
                continue
            name = item
            if isinstance(name, enum.Enum):
                name = name.name

            list_item = QListWidgetItem(name)  # type: ignore
            list_item.setFlags(list_item.flags() |
                               Qt.ItemFlag.ItemIsUserCheckable)

            check_state = Qt.CheckState.Unchecked
            if item in set_classes:
                check_state = Qt.CheckState.Checked

            list_item.setCheckState(check_state)
            self.addItem(list_item)

    def checked_items_to_set(self) -> set[str]:
        check_items = set()
        for i in range(self.count()):
            item = self.item(i)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            check_items.add(item.text())

        return check_items


def main(argv: list):
    """
       Main Function for starting the card set picking and deck drafting
       process.
    """
    NAME = "YU-GI-OH Deck Creator"

    logging.info("Starting %s!", NAME)

    app = QApplication(argv)
    app.setStyle("Fusion")

    QPixmapCache.setCacheLimit(100000)

    main_window = MainWindow()
    main_window.setWindowTitle(NAME)

    style = """
        QScrollArea {
            border: 1px solid gray;
            border-radius: 2px;
            }
        QLabel#indicator {
            color: white;
            border: 1px solid gray;
            border-radius: 2px;
            }
        """

    main_window.setStyleSheet(style)
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    def excepthook(type_, value, traceback_):
        """Exception hook and display."""
        traceback.print_exception(type_, value, traceback_)
        sys.exit(1)

    sys.excepthook = excepthook

    fmt = "%(levelname)s | %(module)s\\%(funcName)s:%(lineno)d -> %(message)s"
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=fmt)
    main(sys.argv)
