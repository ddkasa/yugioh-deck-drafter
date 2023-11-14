import pytest

from yugioh_deck_drafter.__main__ import MainWindow


@pytest.fixture(scope="session")
def main_window_fill():
    main_window = MainWindow()
    main_window.show()

    TEST_DATA = ("Legend of Blue Eyes White Dragon", "Pharaoh's Servant",
                 "Spell Ruler", "Magic Ruler")

    for item in TEST_DATA:
        main_window.select_pack.setCurrentText(item)

    yield main_window
