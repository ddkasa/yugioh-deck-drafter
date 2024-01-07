"""Module for testing main functions of the app testing most of the process.

Tests most of the functions require for crafting a deck except search
    and more detailed assocciated card additions.
"""


from random import choice
from typing import Generator

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QInputDialog, QWidget
from pytestqt.qtbot import QtBot

from yugioh_deck_drafter import __main__ as main
from yugioh_deck_drafter.modules import deck_drafter, ygo_data


@pytest.fixture()
def main_window_fill() -> Generator:
    """Main window function that returns the main window with prefilled sets.

    Yields:
        MainWindow: Returns the widget with a bunch of sets prefilled.
    """
    main_window = main.MainWindow(debug=True)
    main_window.show()

    TEST_DATA = (
        "Legend of Blue Eyes White Dragon",
        "Pharaoh's Servant",
        "Spell Ruler",
        "Magic Ruler",
    )

    for item in TEST_DATA:
        main_window.select_pack.setCurrentText(item)

    yield main_window


def find_dialog(parent: QWidget, dialog: type) -> QWidget:
    """Looks for modal dialog that is parented to a widget.

    Args:
        parent (QWidget): Parent widget where the target widget type should
            be located.
        dialog (Type): Target Dialog type that should be attached to the
            widget.

    Returns:
        QDialog: If the widget is present and parented.

    Raises:
        AttributeError: If the target widget type is not present.
    """
    children = parent.children()
    for item in children:
        if isinstance(item, dialog):
            item: dialog
            return item
    else:
        raise AttributeError("No Dialog present in children.")


def test_main_win_functionality(
    main_window_fill: main.MainWindow, qtbot: QtBot
) -> None:
    """Tests if the main window was filled correctly with sets.

    Args:
        main_window_fill (MainWindow): Helper function to prefill the main
            window with sets.
        qtbot (QtBot): QtBot for managing the widget while testing.
    """
    main_window = main_window_fill
    main_window.show()

    qtbot.addWidget(main_window)

    assert main_window.sel_card_set_list.count() == 4


def test_dialog(main_window_fill: main.MainWindow, qtbot: QtBot) -> None:
    """Tests if the drafting dialog spawns if the conditions are met for it.

    Args:
        main_window_fill (MainWindow): Prefilled MainWindow ready for testing.
        qtbot (QtBot): QtBot Instance for testing the widget.
    """
    main_window = main_window_fill
    qtbot.addWidget(main_window)
    main_window.show()
    main_window.start_button.click()

    name_input: QInputDialog = find_dialog(main_window, QInputDialog)
    name_input.setTextValue("Test_Deck")
    name_input.accept()

    dia = find_dialog(main_window, main.DraftingDialog)

    assert isinstance(dia, main.DraftingDialog)


def test_card_picks(main_window_fill: main.MainWindow, qtbot: QtBot) -> None:
    """Tests the basic drafting process start to end.

    Misses out on more advanced functions like searching and adding assocciated
        cards.

    Generally will run through most of it smoothly, but need to be careful with
        this test and possible precache for it in the future as otherwise it
        might be rate limited.

    Args:
        main_window_fill (MainWindow): Pre-filled main for testing the drafting
            process with.
        qtbot (QtBot): For managing the widgets used for testing.
    """
    pack_count = 40

    main_window = main_window_fill
    main_window.show()

    main_window.start_button.click()

    name_input: QInputDialog = find_dialog(main_window, QInputDialog)

    name_input.setTextValue("Test_Deck")
    name_input.accept()

    dialog = find_dialog(main_window, deck_drafter.DraftingDialog)

    qtbot.addWidget(dialog)
    dialog.next_button.click()

    stages = pack_count // 40
    for stage in range(stages):
        for _ in range(10):
            while dialog.drafting_model.selections_left > 0:
                button = choice(dialog.card_buttons)
                if button.card_model.card_type == "Fusion Monster":
                    continue

                qtbot.addWidget(button)
                qtbot.mouseClick(button, Qt.MouseButton.RightButton, delay=10)

                qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

            dialog.next_button.click()

        discard_stage = find_dialog(dialog, deck_drafter.DeckViewer)

        qtbot.addWidget(discard_stage)

        main_deck_items = discard_stage.deck.widget_list()
        for _ in range(discard_stage.deck.count()):
            item = choice(main_deck_items)
            item.click()
            if discard_stage.removal_counter.text() == "Remove: 0":
                break

        move_cnt = 0
        for item in main_deck_items:
            if item.isChecked():
                continue

            discard_stage.mv_card(item, ygo_data.DeckType.SIDE)
            move_cnt += 1

            if move_cnt == 2:
                break

        qtbot.addWidget(discard_stage.accept_button)
        discard_stage.accept_button.click()

        dialog.deck = discard_stage.new_deck

        stage += 1
        assert len(dialog.deck.main) == 10 * stage
        assert len(dialog.deck.side) == 2 * stage

        discard_stage.accept()
