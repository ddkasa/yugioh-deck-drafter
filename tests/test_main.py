import pytest
from PyQt6.QtCore import Qt

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


def test_main_win_functionality(main_window_fill: main.MainWindow, qtbot):
    main_window = main_window_fill
    main_window.show()

    qtbot.addWidget(main_window)

    assert main_window.list_widget.count() == 4


def test_dialog(main_window_fill: main.MainWindow, qtbot):
    main_window = main_window_fill
    main_window.show()

    start_button = main_window.start_button

    qtbot.addWidget(start_button)

    dia = main_window.start_drafting()

    assert isinstance(dia, main.DraftingDialog)


def test_card_picks(main_window_fill: main.MainWindow, qtbot):
    pack_count = 40

    def find_dialog(children: list):
        for item in children:
            if isinstance(item, deck_drafter.DeckViewer):
                return item
        else:
            raise ValueError("No DeckViewer dialog present in children.")

    main_window = main_window_fill
    main_window.show()

    dialog = main.DraftingDialog(main_window, "test_deck",
                                 Qt.WindowType.Widget)
    qtbot.addWidget(dialog)
    dialog.show()

    stages = pack_count // 40
    for stage in range(stages):
        for i in range(10):
            b_clicks = 0
            for button in dialog.card_buttons:

                if button.card_model.card_type == "Fusion Monster":
                    continue
                button.toggle()
                b_clicks += 1

                if dialog.selection_per_pack <= 0:
                    break

            dialog.next_button.click()

        discard_stage: deck_drafter.DeckViewer = find_dialog(dialog.children())

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
