"""Main Deck Builder Python Script"""
from typing import Final
import logging
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import (Qt, pyqtSlot, QPoint, qFatal, QSignalBlocker)

from PyQt6.QtWidgets import (QApplication, QPushButton, QWidget,
                             QComboBox, QVBoxLayout, QListWidget, QSlider,
                             QHBoxLayout, QListWidgetItem, QSpinBox, 
                             QLabel, QFileDialog, QMenu, QMessageBox,
                             QInputDialog)

from PyQt6.QtGui import (QPixmapCache, QCursor)

from yugioh_deck_drafter import util
from yugioh_deck_drafter.modules.deck_drafter import DraftingDialog
from yugioh_deck_drafter.modules.ygo_data import (
    DeckModel,
    YGOCardSet,
    YugiObj
    )


class MainWindow(QWidget):
    """Main Window Class managing Pack Selection and general utilities."""

    DEFAULT_PACK_COUNT: Final[int] = 10
    PACK_MAX: Final[int] = 40
    OMEGA_PATH = Path(r"C:\Program Files (x86)\YGO Omega")
    DEFAULT_IMPORT = OMEGA_PATH / r"YGO Omega_Data\Files\Imports"

    def __init__(self, debug: bool = False):
        super().__init__()

        self.debug = debug
        self.yugi_pro_connect = YugiObj()

        self.selected_packs: dict[str, YGOCardSet] = {}
        self.p_count: int = 0

        self.init_ui()
        self.update_pack_count()
        self.show()

    def init_ui(self) -> None:
        """Intializes layouts and widgets for the UI."""
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self.select_layout = QHBoxLayout()
        self.main_layout.addLayout(self.select_layout)

        self.select_pack = QComboBox()
        names = [item["set_name"] for item in self.yugi_pro_connect.card_set]

        self.select_pack.addItems(names)
        self.select_layout.addWidget(self.select_pack, 50)
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

        self.no_pack_indi = QSpinBox()
        self.no_pack_indi.setValue(self.DEFAULT_PACK_COUNT)
        self.no_pack_indi.setSingleStep(5)
        self.no_pack_indi.setMinimum(5)
        self.no_pack_indi.setMaximum(self.PACK_MAX)
        self.select_layout.addWidget(self.no_pack_indi, 1)

        self.list_widget = QListWidget()
        (self.list_widget
         .setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu))
        (self.list_widget.customContextMenuRequested
         .connect(self.list_context_menu))
        self.main_layout.addWidget(self.list_widget)

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
        
        TEST_DATA = ("Legend of Blue Eyes White Dragon", "Pharaoh's Servant",
                 "Spell Ruler", "Magic Ruler")

        for item in TEST_DATA:
            self.select_pack.setCurrentText(item)

    @pyqtSlot()
    def list_context_menu(self):
        """Create and display a context menu for managing the pack list widget.

        This function generates a context menu when triggered at a specific
        position within the widget.
        The context menu provides an option to remove an item from the
        list, triggered by selecting 'Remove Item'.
        """
        pos = QCursor().pos()

        menu = QMenu(self.list_widget)

        remove_item = menu.addAction("Remove Item")
        (remove_item.triggered  # type: ignore
         .connect(lambda: self.remove_item(pos)))

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
        data = self.yugi_pro_connect.card_set[index]

        cnt = self.no_pack_indi.value()

        item = QListWidgetItem(f"{cnt}x {label}")
        self.list_widget.addItem(item)

        data = YGOCardSet(label, data["set_code"], data["tcg_date"],
                          data["num_of_cards"], cnt)

        self.selected_packs[label] = data

        self.update_pack_count()

    @pyqtSlot()
    def remove_item(self, pos: QPoint) -> None:
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
        pos = self.list_widget.mapFromGlobal(pos)
        item = self.list_widget.itemAt(pos)
        if item is None:
            logging.debug("Bad index for pack removal.")
            return
        row = self.list_widget.row(item)
        removed_item = self.list_widget.takeItem(row)
        if removed_item is None:
            return
        label = removed_item.text().split("x ")[-1]
        self.selected_packs.pop(label)

        del removed_item

        self.update_pack_count()

    def update_indi(self, value: int):
        """Updates pack count indicators depending on the values provided
        which determine how many packs get added at a time.

        Args:
            value (int): the updated value set by the widget.
        """
        with (QSignalBlocker(self.no_packs)
             and QSignalBlocker(self.no_pack_indi)):
            self.no_packs.setValue(value)
            self.no_pack_indi.setValue(value)

    def update_pack_count(self):
        """Updates pack count of the selected packs when the values are
           changed.
        """
        self.p_count = 0
        for pack in self.selected_packs.values():
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

            self.save__deck_dialog(dialog.deck, path)

            QMessageBox.information(self, "File Saved",
                                    f"File was saved to {path}!",
                                    QMessageBox.StandardButton.Ok)
        return

    def save__deck_dialog(self, deck: DeckModel, path: Path) -> None:
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
        deck_file = self.yugi_pro_connect.to_ygodk_format(deck)

        with file_path.open("w", encoding="utf-8") as file:
            file.write(deck_file)

    @pyqtSlot()
    def reset_selection(self) -> None:
        """Resets pack Selection to empty and clears out the rest of cache."""
        logging.info("Resetting app to defaults.")

        self.selected_packs = {}
        self.list_widget.clear()
        self.update_pack_count()

    @pyqtSlot()
    def randomize_packs(self):
        """Launches a dialog for randomizing card_set picks."""


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
        qFatal(traceback_)
        sys.exit(1)

    sys.excepthook = excepthook

    fmt = "%(levelname)s | %(module)s\\%(funcName)s:%(lineno)d -> %(message)s"
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=fmt)
    main(sys.argv)
