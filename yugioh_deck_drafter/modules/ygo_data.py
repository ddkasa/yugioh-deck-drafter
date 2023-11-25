"""ygo_data.py

Classes & Functions for managing the YGOPRODECK API communication, modelling
card sets/cards and exporting to the .ydk format.
"""

import sys
from typing import NamedTuple, Optional, Any, Final
import logging
from datetime import date, datetime
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote
from collections import defaultdict

import requests
import requests_cache

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QMessageBox

from yugioh_deck_drafter import util


@dataclass
class YGOCardSet:
    """Datamodel for a YGO Cardset

    Store base data for a card set and weights in addtional, while also
    carrying the list of weights for random choices.

    """
    set_name: str = field()
    set_code: str = field()
    data: date = field()
    card_count: int = field(default=1)
    count: int = field(default=1)
    card_set: tuple['YGOCard', ...] = field(default_factory=tuple)
    probabilities: tuple[int, ...] = field(default_factory=tuple)


class YGOCard(NamedTuple):
    """Datamodel for a YGO Card

    Some data is stored in the raw JSON[dict] format so that could be
    parsed more cleanly in the future
    """
    name: str = field()
    description: str = field()
    card_id: int = field()
    card_type: str = field()
    raw_data: dict[str, Any] = field()
    rarity: str = field(default="Common")
    card_set: Optional[YGOCardSet] = None


@dataclass
class DeckModel:
    """Datamodel for a complete YGO Deck"""
    name: str = field(default="Deck")
    main: list[YGOCard] = field(default_factory=lambda: [])
    extra: list[YGOCard] = field(default_factory=lambda: [])
    side: list[YGOCard] = field(default_factory=lambda: [])


class YugiObj:
    """Object for managing requests from YGOPRODECK, creating Models and
       generating cardmodels themselves.

    Will immediatly request card_set data in order to grab the information
    for the main window.

    Attributes:
        card_set (list): Data of all the card_sets available.
        CACHE (CachedSession): Cache for most of the requests except images
            which get managed more manually.
        SIDE_DECK_TYPES (set): For filtering out extra deck monsters and
            arche types.
        PROB (defaultdict): probablities for each type of card rarity.
    """

    CACHE = requests_cache.CachedSession("cache\\ygoprodeck.sqlite",
                                         backend="sqlite")
    PROB: Final[defaultdict[str, float]] = defaultdict(
        lambda: 2.8571428571,
        {"Common": 80,
         "Rare": 16.6667,
         "Super Rare": 8.3334,
         "Ultra Rare": 4.3478260870,
         "Secret": 2.8571428571
         })

    SIDE_DECK_TYPES: Final[set[str]] = {"Fusion Monster", "Synchro Monster",
                                        "Pendulum Monster", "XC Monster"}

    def __init__(self) -> None:
        self.card_set = self.get_card_set()

    def get_card_set(self) -> list:
        """Collects all card sets for selection.

        Filters out any Card Sets with less than 10 cards in them.
        """
        url = r"https://db.ygoprodeck.com/api/v7/cardsets.php"
        request = self.CACHE.get(url, timeout=20)
        if request.status_code != 200:
            logging.critical("Failed to fetch Card Sets. Exiting!")
            logging.critical("Status Code: %s", request.status_code)
            QMessageBox.critical(None,
                                 "Critical",
                                 "Failed to Grab Card Sets. Retry Later")
            sys.exit()

        data = request.json()

        new_set = []
        for item in data:
            if item["num_of_cards"] < 10:
                continue
            d = item.get("tcg_date")
            if d is None:
                continue
            item["tcg_date"] = datetime.strptime(d, '%Y-%m-%d').date()
            new_set.append(item)

        new_set.sort(key=lambda x: x["set_name"])
        return new_set

    def get_card_set_info(self, card_set: YGOCardSet) -> list[YGOCard]:
        """Returns the cards contained within the given card set."""
        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php?cardset={0}"
        request = self.CACHE.get(url.format(card_set.set_name),
                                 timeout=20)
        data = request.json()
        if request.status_code != 200 or not isinstance(data, dict):
            logging.critical("Failed to fetch Card Sets. Exiting!")
            logging.critical("Status Code: %s", request.status_code)
            QMessageBox.critical(None, "Critical",
                                 "Failed to Grab Card Sets. Retry Later")
            sys.exit()

        data = data["data"]
        cards = []

        for card_data in data:
            card = self.create_card(card_data, card_set)
            cards.append(card)

        return cards

    def get_card_art(self, card: YGOCard) -> QPixmap | None:
        """Collects and stores card art for the given piece.

        Will return a default image here if neede

        Args:
            card (YGOCard): Card data for grabbing the card art.

        Returns:
            QPixmap | None: Image in a pixmap format ready to displayed on the
                QT GUI.
        """
        image_store = Path(r"assets\images\card_art")
        image_store.mkdir(parents=True, exist_ok=True)

        card_art_id = card.card_id
        image_path = image_store / str(str(card_art_id) + ".jpg")

        if image_path.exists():
            return util.get_or_insert(image_path)

        url = f"https://images.ygoprodeck.com/images/cards/{card_art_id}.jpg"
        request = requests.get(url, timeout=10)
        if request.status_code != 200:
            # Add a default image here in the future.
            logging.error("Failed to fetch card image. Using Default")
            logging.error("Status Code: %s", request.status_code)
            return None

        data = request.content
        with image_path.open("wb") as image_file:
            image_file.write(data)

        image = util.get_or_insert(image_path, data=data)

        return image

    def card_arche_types(self, card_arche: str,
                         subtype: str = "archetype") -> list | None:
        """Filters out cards with the specfied subtype

        Queries YGOPRODECK for specified subtype(str) with archetype included.

        Args:
            card_arche (str): Actual name of the type of the subtype.
            subtype (str, optional): Subtype of the Card.
                                     Defaults to "archetype".

        Returns:
            list | None: Either returns None if the query is bad or JSON data
                         retrieved.
        """
        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php?{0}={1}"

        request = self.CACHE.get(url.format(subtype, card_arche),
                                 timeout=10)

        if request.status_code != 200:
            logging.warning(f"Failed to fetch card {subtype}. Skipping!")
            logging.warning("Status Code: %s", request.status_code)
            return

        return request.json()["data"]

    def grab_card(self, name: str) -> dict | None:
        """Collects card info for the given name(str).

        Args:
            name (str): Name of the card as provided from previous queries.

        Returns:
            dict | None: JSON data or nothing if the query fails.
        """

        name = quote(name, safe="/:?&")
        url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?name={name}"
        request = self.CACHE.get(url, timeout=10)

        if request.status_code != 200:
            logging.warning("Failed to grab %s. Skipping!", name)
            logging.warning("Status Code: %s", request.status_code)
            return

        return request.json()["data"]

    def create_card(self, data: dict, set_data: YGOCardSet | None) -> YGOCard:
        """Create a card datamodel from given JSON Data.

        Creates a cardmodel which uses the first rarity data found which
        matches to the CardSet Name.

        Args:
            data (dict): JSON data retrieved from a previous query.
            set_data (YGOCardSet | None): SetData which is used to determine
                                          the rarity.

        Returns:
            YGOCard: Generated model from the card data that was received.
        """

        # Rarity will have to be adjusted and tweaked here as I am not 100%
        # if it selects the correct value as there multiple values for the same
        # set included in the json data.
        rarity = "Common"

        if isinstance(set_data, YGOCardSet):
            card_sets = data["card_sets"]
            for card_set in card_sets:
                card_set_code = card_set["set_code"]
                if set_data.set_code in card_set_code:
                    rarity = card_set["set_rarity"]
                    break

        card = YGOCard(data["name"], data["desc"], data["id"], data["type"],
                       data, rarity, set_data)

        return card

    def to_ygodk_format(self, deck: DeckModel) -> str:
        """Generates and formats a .ydk file format from the provided deck.

        Args:
            deck (DeckModel): Model of the deck containing the selected cards.

        Returns:
            str: File in a str newline concated str.
        """
        def create_text(data: list[YGOCard]) -> str:
            cards = [str(item.card_id) for item in data]
            mn_text = "\n".join(cards)
            return mn_text

        main_ids = create_text(deck.main)
        extra_ids = create_text(deck.extra)
        side_ids = create_text(deck.side)

        text = "#main\n"
        text += main_ids + "\n"
        text += "#extra\n"
        text += extra_ids + "\n"
        text += "!side\n"
        text += side_ids + "\n"

        return text

    def check_extra_monster(self, card: YGOCard) -> bool:
        """Checks if a card belongs in the side deck.

        Args:
            card (YGOCard): Card to be Checked

        Returns:
            bool: checks if a card model variable in present in a class
                constant.
        """
        return card.card_type in self.SIDE_DECK_TYPES

    def generate_weights(self, card_set_name: str, data: list[YGOCard],
                         extra: bool = False) -> tuple[int, ...]:
        """Generate a list of integers depeding on the weight denoting the
        index of an item inside the set cards.

        Basic weight generator for probablities in the card set.

        Args:
            cards_set_name (str): In order to grab the corrrect rarity for the
                card.
            data (list): the cards required in the probablity set.
            extra (bool): value is if you want to skip the common cards in
                order to weight the last card in a pack.
        """

        probabilities = []

        for card_model in data:
            card = card_model.raw_data
            card_sets = card["card_sets"]
            for card_set in card_sets:
                if card_set["set_name"] != card_set_name:
                    continue

                rarity_name = card_set["set_rarity"]
                if rarity_name == "Common" and extra:
                    break

                card["set_rarity"] = rarity_name

                rarity = round(self.PROB[rarity_name])
                probabilities.append(rarity)
                break

        return tuple(probabilities)
