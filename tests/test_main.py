import pytest
from pytestqt.qtbot import QtBot
from random import choice

from PyQt6.QtCore import Qt

from PyQt6.QtWidgets import QInputDialog, QWidget, QApplication

from yugioh_deck_drafter import __main__ as main
from yugioh_deck_drafter.modules import deck_drafter


@pytest.fixture()
def main_window_fill():
    main_window = main.MainWindow(debug=True)
    main_window.show()

    TEST_DATA = ("Legend of Blue Eyes White Dragon", "Pharaoh's Servant",
                 "Spell Ruler", "Magic Ruler")

    for item in TEST_DATA:
        main_window.select_pack.setCurrentText(item)

    yield main_window


def find_dialog(parent: QWidget, dialog: type):
    children = parent.children()
    for item in children:
        if isinstance(item, dialog):
            item: dialog
            return item
    else:
        raise AttributeError("No Dialog present in children.")


def test_main_win_functionality(main_window_fill: main.MainWindow, qtbot):
    main_window = main_window_fill
    main_window.show()

    qtbot.addWidget(main_window)

    assert main_window.sel_card_set_list.count() == 4


def test_dialog(main_window_fill: main.MainWindow, qtbot):
    main_window = main_window_fill
    qtbot.addWidget(main_window)
    main_window.show()
    main_window.start_button.click()

    name_input: QInputDialog = find_dialog(main_window, QInputDialog)
    name_input.setTextValue("Test_Deck")
    name_input.accept()

    dia = find_dialog(main_window, main.DraftingDialog)

    assert isinstance(dia, main.DraftingDialog)


def test_card_picks(main_window_fill: main.MainWindow, qtbot: QtBot):
    pack_count = 40

    main_window = main_window_fill
    main_window.show()

    main_window.start_button.click()

    name_input: QInputDialog = find_dialog(main_window, QInputDialog)

    name_input.setTextValue("Test_Deck")
    name_input.accept()

    dialog = find_dialog(main_window, deck_drafter.DraftingDialog)

    qtbot.addWidget(dialog)
    dialog.show()
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

        for item in discard_stage.deck:
            item.click()
            if discard_stage.removal_counter.text() == "Remove: 0":
                break

        move_cnt = 0
        for item in discard_stage.deck:

            if item.isChecked():
                continue

            discard_stage.mv_card(item, "side")
            move_cnt += 1

            if move_cnt == 2:
                break

        qtbot.addWidget(discard_stage.accept_button)
        discard_stage.accept_button.click()

        dialog.deck = discard_stage.new_deck

        stage += 1
        assert len(dialog.deck.main) == 10 * stage
        assert len(dialog.deck.side) == 2 * stage

        discard_stage.close()
