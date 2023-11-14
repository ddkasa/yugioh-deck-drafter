import pytest

from PyQt6.QtCore import Qt

from yugioh_deck_drafter import __main__ as main


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

    dia = main_window.start_creating()

    assert isinstance(dia, main.SelectionDialog)


def test_card_picks(main_window_fill: main.MainWindow, qtbot):
    main_window = main_window_fill
    main_window.show()

    dialog = main.SelectionDialog(main_window, Qt.WindowType.Widget)
    qtbot.addWidget(dialog)
    dialog.show()

    PACK_COUNT = 10
    for _ in range(PACK_COUNT):
        b_clicks = 0

        for button in dialog.card_buttons:

            if button.card_model.card_type == "Fusion Monster":
                continue
            button.toggle()
            b_clicks += 1

            if b_clicks == 2:
                break

        # qtbot.addWidget(dialog.accept_button)
        dialog.next_button.click()

    print(dialog.children())

    main_deck_len = len(dialog.main_deck)


    assert main_deck_len == PACK_COUNT * 2 - 8
