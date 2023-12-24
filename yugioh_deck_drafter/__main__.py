"""__main__.py
Main Deck Builder Python Script
Handles launching the application, card-set selection and miscelanous tasks.

Classes:
    MainWindow: Main classes that launches when launching the program from
        main.
    PackFilterDialog: GUI Dialog for filtering packs.
    RandomPacks: Pack randomisation of Dialog, SubClass of PackFilterDialog.
    CheckableListWidget: Widget for selecting and filtering out unwanted set
        categories.

Functions:
    main: Main window handler and manager.
    excepthook: Application excepthook for managing and displaying exceptions
        and errors.
"""

import enum
import logging
import re
import sys
import traceback
from functools import partial
from pathlib import Path
from typing import Final, Optional

import pyperclip as clipboard
from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSlot
from PyQt6.QtGui import QAction, QCursor, QPixmapCache
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from yugioh_deck_drafter import util
from yugioh_deck_drafter.modules.deck_drafter import DraftingDialog
from yugioh_deck_drafter.modules.ygo_data import (
    CardSetClass,
    CardSetFilter,
    CardSetModel,
    DeckModel,
    YugiObj,
)


class MainWindow(QMainWindow):
    """Main Window Class managing Pack Selection and general utilities.

    Attributes:
        DEFAULT_PACK_COUNT (int): Default amount of packs when adding new ones
        PACK_MAX (int): Maximum amount of packs that are used for drafting
        OMEGA_PATH (Path): Path for direct imports of cards.
        DEFAULT_FILTER (CardSetFilter): For comparing default values with
            new filter objects.
        p_count (int): Count of packs in the selection.
        selected_packs(list): Models of packs that were selected.

    Args:
        debug (bool): For debugging purposes in the window.

    Methods:
        list_context_menu: Context menu method for the modifying the GUI card
            list.
        check_for_filter_dia: Checks for an existing filter dialog thats open.
        pack_list_context_menu: For manipulating the card_set dropdown menu.
        add_item: Adds an item thats supplied or selected on the dropdown menu.
        remove_item: Removes a card_set from the selection thats supplied if
            None just returns.
        retrieve_set_list_info: Collects a card_set based on its name.
        update_indi/update_pack_count: Update gui indicator values.
        start_drafting: Contains the drafting method that will run the dialog
            for drafting the deck.
        save_deck_dialog: Saves the supplied deck depending on the drafters
            input.
        reset_selection: Method for resetting GUI to the default state.
        randomise_packs: Runs the randomisation dialog/functions for create a
            random set list.
        filter_packs: Filters out packs based on the supplied filter criteria.
        add_packs_to_selection: Adds provided pack set to selection.
        copy_pack_selection/paste_pack_selection: Copies or pastes from/to the
            drafter.
        find_card_set: Looks for a set pack with the same selection.
    """

    DEFAULT_PACK_COUNT: Final[int] = 10
    PACK_MAX: Final[int] = 40
    OMEGA_PATH = Path(r"C:\Program Files (x86)\YGO Omega")
    DEFAULT_IMPORT = OMEGA_PATH / r"YGO Omega_Data\Files\Imports"

    DEFAULT_SAVE = Path("saves")

    DEFAULT_FILTER = CardSetFilter()

    def __init__(self, debug: bool = False):
        super().__init__()
        self.DEFAULT_SAVE.mkdir(parents=True, exist_ok=True)

        self.debug = debug
        self.yugi_pro = YugiObj()

        self.selected_packs: list[CardSetModel] = []
        self.p_count: int = 0

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.init_ui()

        self.pack_filter = self.DEFAULT_FILTER

        self.update_pack_count()
        self.filter_packs(True)

    def init_ui(self) -> None:
        """Intializes layouts and widgets for the UI."""
        self.main_layout = QVBoxLayout()
        self.main_widget.setLayout(self.main_layout)

        self.select_layout = QHBoxLayout()
        self.main_layout.addLayout(self.select_layout)

        CMP = Qt.ContextMenuPolicy.CustomContextMenu

        self.select_pack = QComboBox()
        self.select_layout.addWidget(self.select_pack, 3)
        self.select_pack.setContextMenuPolicy(CMP)
        (
            self.select_pack.customContextMenuRequested.connect(
                self.pack_list_context_menu
            )
        )

        self.select_layout.addStretch(1)

        QSP = QSizePolicy.Policy
        self.no_packs = QSlider()
        self.no_packs.setSizePolicy(QSP.Minimum, QSP.Preferred)
        self.no_packs.setSingleStep(5)
        self.no_packs.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.no_packs.setTickInterval(10)
        self.no_packs.setOrientation(Qt.Orientation.Horizontal)
        self.no_packs.setMinimum(5)
        self.no_packs.setValue(self.DEFAULT_PACK_COUNT)
        self.no_packs.setMaximum(self.PACK_MAX)
        self.select_layout.addWidget(self.no_packs, 1)
        self.no_packs.setContextMenuPolicy(CMP)
        (self.no_packs.customContextMenuRequested.connect(self.pack_list_context_menu))

        self.no_pack_indi = QSpinBox()
        self.no_pack_indi.setValue(self.DEFAULT_PACK_COUNT)
        self.no_pack_indi.setSingleStep(5)
        self.no_pack_indi.setMinimum(5)
        self.no_pack_indi.setMaximum(self.PACK_MAX)
        self.select_layout.addWidget(self.no_pack_indi, 1)
        self.no_pack_indi.setContextMenuPolicy(CMP)
        (
            self.no_pack_indi.customContextMenuRequested.connect(
                self.pack_list_context_menu
            )
        )

        self.sel_card_set_list = QListWidget()
        self.sel_card_set_list.setContextMenuPolicy(CMP)
        (
            self.sel_card_set_list.customContextMenuRequested.connect(
                self.list_context_menu
            )
        )
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

        The context menu provides an options for manipulating the QListWidget
            showing CardSet selections.
        Certain actions will be disabled if conditions meet to keep the ui more
            intuitive.
        """
        pos = QCursor().pos()

        menu = QMenu(self.sel_card_set_list)

        remove_item = QAction("Remove Pack")
        menu.addAction(remove_item)
        item_pos = self.sel_card_set_list.mapFromGlobal(pos)
        item = self.sel_card_set_list.itemAt(item_pos)
        item_exist = isinstance(item, QListWidgetItem)
        remove_item.setDisabled(not item_exist)
        remove_item.triggered.connect(lambda: self.remove_item(item))

        menu.addSeparator()

        random_packs = QAction("Randomise Packs")
        random_packs.setDisabled(self.check_for_filter_dia())
        menu.addAction(random_packs)
        random_packs.triggered.connect(self.randomize_packs)

        quick_random = QAction("Quick Randomise")
        quick_random.triggered.connect(lambda: self.randomize_packs(True))
        menu.addAction(quick_random)

        menu.addSeparator()

        pack_exist = not self.selected_packs

        copy_packs = QAction("Copy Packs")
        copy_packs.setDisabled(pack_exist)
        copy_packs.triggered.connect(self.copy_pack_selection)
        menu.addAction(copy_packs)

        paste_packs = QAction("Paste Packs")
        text = clipboard.paste()
        paste_packs.setDisabled(not isinstance(text, str) or text == "")
        paste_packs.triggered.connect(lambda: self.paste_pack_selection(text))
        menu.addAction(paste_packs)

        menu.addSeparator()

        clear_packs = QAction("Clear Packs")
        clear_packs.setDisabled(pack_exist)
        clear_packs.triggered.connect(self.reset_selection)
        menu.addAction(clear_packs)

        menu.exec(pos)

    def check_for_filter_dia(self) -> bool:
        """Function to check if the filter dialog is already running to prevent
        the user from opening another.

        Returns:
            bool: False if not open and true if open.
        """
        return any(isinstance(c, PackFilterDialog) for c in self.children())

    @pyqtSlot()
    def pack_list_context_menu(self):
        """Filtering and selection options for the set pack dropdown menu."""
        pos = QCursor().pos()
        menu = QMenu(self.select_pack)

        reset_dropdwn = QAction("Reset Dropdown")
        (reset_dropdwn.triggered.connect(lambda: self.select_pack.setCurrentIndex(-1)))
        reset_dropdwn.setDisabled(self.select_pack.currentIndex() == -1)
        menu.addAction(reset_dropdwn)

        menu.addSeparator()

        pack_filter = QAction("Filter Packs")
        pack_filter.setDisabled(self.check_for_filter_dia())
        pack_filter.triggered.connect(self.filter_packs)
        menu.addAction(pack_filter)

        reset_filter = QAction("Reset Filter")
        reset_filter.setDisabled(self.filter == self.DEFAULT_FILTER)
        reset_filter.triggered.connect(lambda: self.filter_packs(True))
        menu.addAction(reset_filter)

        menu.exec(pos)

    @pyqtSlot()
    def add_item(self, card_set: Optional[CardSetModel] = None) -> None:
        """This function retrieves the selected pack from the UI and adds it to
        the selection list while managing the associated indicators.

        Args:
            card_set (CardSetModel | None): If the user already know what the
                pack is going to be.
        """

        if isinstance(card_set, CardSetModel):
            label = card_set.set_name
            cnt = card_set.count
        else:
            index = self.select_pack.currentIndex()
            if index == -1:
                return

            label = self.select_pack.currentText()
            cnt = self.no_pack_indi.value()

            card_set = self.yugi_pro.card_sets[index]

            cnt = self.no_pack_indi.value()
            card_set.count = cnt

        item = QListWidgetItem(f"{cnt}x {label}")

        self.sel_card_set_list.addItem(item)
        self.selected_packs.append(card_set)

        self.update_pack_count()

    @pyqtSlot()
    def remove_item(self, item: QListWidgetItem | None) -> None:
        """Remove an item from the pack list based on the provided position.

        This function identifies the item in the pack list widget based on the
        given position.
        If no item is found at that position, it logs a debug message and
        exits.
        Upon successful identification, it removes the item from the list,
        updates the associated data, and refreshes the pack count.

        Args:
            item (QListWidgetItem) Pre-selected item to be removed from the
                QListWidget.
        """
        if item is None:
            return

        row = self.sel_card_set_list.row(item)
        removed_item = self.sel_card_set_list.takeItem(row)
        if removed_item is None:
            return

        label, cnt = self.retrieve_set_list_info(removed_item)

        for index, value in enumerate(self.selected_packs):
            if value.set_name == label and value.count == cnt:
                self.selected_packs.pop(index)
                break

        self.update_pack_count()

    def retrieve_set_list_info(self, item: QListWidgetItem | str) -> tuple[str, int]:
        """Reformats a string with a count and the name of the set back
          into a int and str.

          Args:
              item (QListWidgetItem | str): Item to be checked, either can
                  be a list item to be extracted or a ready string.

        10 ▎   ▎   ▎   self.DEFAULT_IMPORT.exists()                                      ┃
          Raises:
              ValueError: If the item is not a valid str it raises an
                  error.

          Returns:
              tuple[str, int]: Name of the pack and pack count in a tuple.
        """
        text = item
        if isinstance(text, QListWidgetItem):
            text = text.text()
        try:
            cnt, label = text.split("x ")
            return label, int(cnt)
        except ValueError as v:
            raise v

    def update_indi(self, value: int) -> None:
        """Updates pack count indicators depending on the values provided
        which determine how many packs get added at a time.

        Args:
            value (int): the updated value set by the widget.
        """
        with QSignalBlocker(self.no_packs) and QSignalBlocker(self.no_pack_indi):
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

        Checks if there are 40 packs selected first and asks for a Deck Name.
        Begins the drafting dialog if conditions are met which will stay in
            this func until the process is finished.
        """

        if self.p_count != self.PACK_MAX:
            msg = "Make sure you have {0} packs selected."
            QMessageBox.information(self, "Not Enough Packs", msg.format(self.PACK_MAX))
            return

        name_dia = QInputDialog(self)
        name_dia.setWindowTitle("Deck Name")
        name_dia.setLabelText("Choose a name for your deck.")
        name_dia.setModal(not self.debug)

        if self.debug:
            name_dia.show()
        else:
            name_dia.exec()
        deck_name = name_dia.textValue()

        logging.info("Opening Selection Dialog.")
        dialog = DraftingDialog(self, deck_name)
        if self.debug:
            dialog.show()

        elif dialog.exec():
            self.save_deck_dialog(dialog.deck)
        return

    def save_deck_dialog(self, deck: DeckModel) -> None:
        """Converts and saves the provided deck to path.

        Sanitizes the provided path(Path) first and then converts the deck to
        a str according to the .ydk format.

        Args:
            deck (DeckModel): Datamodel containing all the selected cards
                including the side/extra deck.
            path (Path): Path to where the YDK file will be saved.
        """
        deck_file = self.yugi_pro.to_ygodk_format(deck)

        deck_name = util.sanitize_file_path(deck.name)
        file_name = Path(f"{deck_name}.ydk")

        file_path = self.DEFAULT_SAVE

        default_path = file_path / file_name
        with default_path.open("w", encoding="utf-8") as file:
            file.write(deck_file)

        message_box = QMessageBox(
            QMessageBox.Icon.Question, "Save Location", "Where would you like to save?"
        )

        message_box.addButton("Default", QMessageBox.ButtonRole.ActionRole)
        cust_button = message_box.addButton(
            "Custom Location", QMessageBox.ButtonRole.ActionRole
        )
        import_button = None
        if self.DEFAULT_IMPORT.exists():
            import_button = message_box.addButton(
                "Imports Folder", QMessageBox.ButtonRole.ActionRole
            )

        message_box.exec()

        if message_box.clickedButton() == cust_button:
            file_dia = QFileDialog(self)
            file_dia.setDirectory(str(self.DEFAULT_SAVE))
            file_dia.setDefaultSuffix(".ygo")
            file_dia.setWindowTitle("Select a Folder")
            while True:
                if file_dia.exec():
                    if file_dia.directory().exists():
                        break

            file_dia.selectFile(deck.name + ".ygo")
            file_path = Path(str(file_dia.directory().path())) / file_name

        elif (
            self.DEFAULT_IMPORT.exists()
            and message_box.clickedButton() == import_button
        ):
            file_path = self.DEFAULT_IMPORT / file_name

        else:
            file_path = default_path

        try:
            with file_path.open("w", encoding="utf-8") as file:
                file.write(deck_file)
        except FileNotFoundError:
            return self.save_deck_dialog(deck)

        return QMessageBox.information(
            self,
            "File Saved",
            f"File was saved to {file_path}!",
            QMessageBox.StandardButton.Ok,
        )

    @pyqtSlot()
    def reset_selection(self) -> None:
        """Resets pack Selection to empty and clears out the rest of cache."""
        logging.info("Resetting app to defaults.")

        self.selected_packs = []
        self.sel_card_set_list.clear()
        self.filter = self.DEFAULT_FILTER
        self.select_pack.setCurrentIndex(-1)

    @pyqtSlot()
    def randomize_packs(self, quick: bool = False) -> None:
        """Launches a dialog for randomizing card_set picks.

        Args:
            quick (bool, optional): If enabled it will just randomise the cards
                with the current card_set filter and skip opening the dialog.
                Defaults to False.
        """
        dialog = RandomPacks(self, self.yugi_pro.card_sets.copy(), self.filter)

        if quick:
            dialog.randomise_packs()
            dialog.reject()
            dialog.deleteLater()
            return

        dialog.show()
        dialog.exec()
        return

    @pyqtSlot(bool)
    def filter_packs(self, reset: bool = False):
        """For filtering out unwanted packs from selection or resetting the
        current selection"""

        card_set = self.yugi_pro.card_sets.copy()

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
            packs = [item.set_name for item in card_set]
            self.select_pack.addItems(packs)

    @pyqtSlot()
    def copy_pack_selection(self) -> None:
        """Copies current pack selection into clipboard for sharing or saving."""
        logging.debug("Copying text to clipboard.")
        copied_text = ""
        count = self.sel_card_set_list.count()
        for i in range(count):
            item = self.sel_card_set_list.item(i)
            if item is None:
                continue
            text = item.text()
            if text == "":
                continue
            copied_text += text

            if i + 1 != count:
                copied_text += "\n"

        clipboard.copy(copied_text)

    @pyqtSlot(str)
    def paste_pack_selection(self, clip_data: str) -> None:
        """Pastes clipboard data into the list widget which displays selected
        packs.

        Args:
            clip_data (str): User clipboard as copied before with
                copy_pack_selection method.
        """
        logging.debug("Pasting packs in clipboard into QListWidget")
        self.reset_selection()
        patt = re.compile(r"[\r]")
        clip_data = re.sub(patt, "", clip_data)
        text = clip_data.split("\n")

        for t in text:
            try:
                label, cnt = self.retrieve_set_list_info(t)
            except ValueError:
                print("value")
                continue
            try:
                card_set = self.find_card_set(label)
            except KeyError:
                print("keyerror")
                continue

            card_set.count = cnt
            self.add_item(card_set)

    def find_card_set(self, label: str) -> CardSetModel:
        """Find a cardset from all the available cardsets and add return it.

        Args:
            label (str): Name of the target cardset.

        Raises:
            KeyError: If the card_set is not available or the
                name is invalid it returns a key erro.

        Returns:
            CardSetModel: CardSet with the same names as the
                target label.
        """
        for item in self.yugi_pro.card_sets:
            if item.set_name == label:
                return item

        raise KeyError(f"{label} does not exist in the file.")


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

    Methods:
        create_filter: Generates a filter based on the GUI values set by the
            drafter
        filter_cards: Filters out card sets based on the supplied filter.

    """

    def __init__(
        self,
        parent: MainWindow,
        card_set: list[CardSetModel],
        previous_filter: CardSetFilter,
    ) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Filter Sets")
        self.setModal(False)
        self.card_set = card_set

        self.main_layout = QVBoxLayout()

        self.form = QFormLayout()
        self.main_layout.addLayout(self.form)

        self.min_card_count = QSpinBox()
        self.min_card_count.setMinimum(3)
        self.min_card_count.setValue(previous_filter.card_count)
        (self.min_card_count.setToolTip("Minimum card threshold allowed inside a set."))
        self.form.addRow("Minimum Cards", self.min_card_count)

        self.max_date = QDateEdit()
        self.max_date.setDate(previous_filter.set_date)
        self.max_date.setToolTip("Filter out packs after this date.")
        self.form.addRow("Max Date", self.max_date)

        self.checkable_items = CheckableListWidget()
        self.checkable_items.add_items(CardSetClass, previous_filter.set_classes)
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
        """Generates a filter objects from the selected values in the dialog
        GUI.

        Returns:
            CardSetFilter: Set filter object filled in with GUI value choices.
        """
        checked_classes = self.checkable_items.checked_items_to_set()
        checked_enums = set()

        for item in checked_classes:
            enum_item = CardSetClass[item.replace(" ", "_")]
            checked_enums.add(enum_item)

        card_filter = CardSetFilter(
            self.min_card_count.value(), self.max_date.date().toPyDate(), checked_enums
        )
        return card_filter

    def filter_cards(self, pack_filter: CardSetFilter) -> list[CardSetModel]:
        """Filters out cards ouit of the base_set and return a new list.

        Args:
            pack_filter (CardSetFilter): Filter object create with classmethod
                create_filter()

        Returns:
            list[CardSetModel]: A list of Card Set as per filter.
        """
        filt_func = partial(
            self.parent().yugi_pro.filter_out_card_sets, set_filter=pack_filter
        )
        new_sets = filter(filt_func, self.card_set)

        return list(new_sets)

    def accept(self) -> None:
        """Overriden accept function in order to triger filtering the GUI."""
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

    Methods:
        randomise_packs: Randomises pack selection depending on the filter
            settings that are set.
    """

    def __init__(
        self,
        parent: MainWindow,
        card_set: list[CardSetModel],
        previous_filter: CardSetFilter,
    ) -> None:
        super().__init__(
            parent=parent, card_set=card_set, previous_filter=previous_filter
        )
        self.setModal(False)
        self.setWindowTitle("Randomise Sets")

        self.total_packs = QSpinBox()
        self.total_packs.setValue(40)
        self.total_packs.setMinimum(1)
        self.total_packs.setMaximum(40)
        self.total_packs.setSingleStep(1)
        (self.total_packs.setToolTip("Total packs to be added to the selection."))
        self.form.addRow("Total Packs", self.total_packs)

        self.pack_increments = QSpinBox()
        self.pack_increments.setValue(5)
        self.pack_increments.setMinimum(5)
        self.pack_increments.setMaximum(25)
        self.pack_increments.setSingleStep(1)
        self.form.addRow("Pack Increments", self.pack_increments)

        self.filter_button.setText("Randomise")
        self.filter_button.disconnect()
        self.filter_button.pressed.connect(self.randomise_packs)

    def randomise_packs(self) -> None:
        """Randomises packs and adds sets to the MainWindow card set list based
        on the values chosen in the GUI"""
        logging.info("Randomising Cards and adding to ListWidget.")

        new_filter = self.create_filter()
        card_set = self.filter_cards(new_filter)
        count_range = range(5, self.pack_increments.value())
        total_packs = self.total_packs.value()

        packs = self.parent().yugi_pro.select_random_packs(
            card_set, count_range, total_packs
        )

        self.parent().reset_selection()

        for pack in packs:
            self.parent().add_item(pack)


class CheckableListWidget(QListWidget):
    """QListWidget subclass for allowing selectable filters with checkboxes.

    Methods:
        addItems: Overriden parent method in order to clean input and add
            checkboxes to the items.
        checked_items_to_list: Quick function for return checked items.
    """

    def add_items(
        self, items: set[str] | enum.EnumMeta, set_classes: set[CardSetClass]
    ) -> None:
        """Extra addItems method for quick adding Enums as a list ontop of
        strings

        Args:
            items (set[str  |  None] | enum.EnumMeta): A set of enumerations or
                strings for adding to the list
            set_classes (set[CardSetClass]): A list of enums previously checked
                by the user or defaults.
        """

        for item in items:
            if item is None:
                continue
            name = item
            if isinstance(name, enum.Enum):
                name = name.name.replace("_", " ").title()

            list_item = QListWidgetItem(name)  # type: ignore
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            check_state = Qt.CheckState.Unchecked
            if item in set_classes:
                check_state = Qt.CheckState.Checked

            list_item.setCheckState(check_state)
            self.addItem(list_item)

    def checked_items_to_set(self) -> set[str]:
        """Custom method for quickly collecting all checked items inside the
        list.

        Returns:
            set[str]: Items that were checked inside the widget.
        """
        check_items = set()
        for i in range(self.count()):
            item = self.item(i)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            check_items.add(item.text().upper())

        return check_items


def main():
    """Main Function for starting the card set picking and deck drafting
    process.

    Args:
        argv (list): For any arguments you want to pass from the command
            line.
    """
    app_name = "YU-GI-OH Deck Creator"

    sys.excepthook = excepthook

    FMT = "%(relativepath)s:%(lineno)s | %(levelname)s: %(message)s"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(FMT)

    handler.setFormatter(formatter)

    handler.addFilter(util.PackagePathFilter())
    logger.addHandler(handler)

    logging.info("Starting %s!", app_name)

    app = QApplication(sys.argv)
    app.setStyle("fusion")

    QPixmapCache.setCacheLimit(100000)

    main_window = MainWindow()
    main_window.setWindowTitle(app_name)

    stylesheet = Path("yugioh_deck_drafter/styles/style.qss")
    with stylesheet.open("r", encoding="utf-8") as file:
        style = file.read()

    main_window.setStyleSheet(style)
    main_window.show()

    sys.exit(app.exec())


def excepthook(type_, value, traceback_):
    """Exception hook and display.

    Excepthook with GUI error messages for the end user.

    Args:
        type_ (type): Type of the error.
        value (exception): Exception object of the error.
        traceback_ (traceback): Traceback object pointing the position at
            fault.
    """
    traceback_text = traceback.format_exception(type_, value, traceback_)
    traceback.print_exception(type_, value, traceback_)
    text = ""

    for t in traceback_text:
        text += "\n" + t

    msg = QMessageBox.critical(None, "Critical", text)
    if msg:
        pass

    sys.exit(1)


if __name__ == "__main__":
    main()
