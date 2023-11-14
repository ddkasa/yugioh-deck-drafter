import pytest

from yugioh_deck_drafter.__main__ import MainWindow, SelectionDialog


def test_main_win_functionality(main_window_fill: MainWindow, qtbot):
    main_window = main_window_fill
    main_window.show()

    qtbot.addWidget(main_window)

    assert main_window.list_widget.count() == 4


def test_dialog(main_window_fill: MainWindow, qtbot):
    main_window = main_window_fill
    main_window.show()

    start_button = main_window.start_button

    qtbot.addWidget(start_button)

    start_button.click()
    assert main_window.children()[-1] == SelectionDialog
