"""ygo_data.py

Classes & Functions for managing the YGOPRODECK API communication, modelling
card sets/cards and exporting to the .ydk format.

Classes:
    Enums: Various enumerations for card properties and filtering.
    DataModels: Various models for storing and transferring card models and
        sets.
    YugiObj: Main class for managing requesting, formatting and fomatting
        YuGiOh data.
    ExtraSearch: Class responsible for searching extra summoning materials and
        assocciations.

Usage:
    Instantiate YugiObj and load in and process card data as you need or
        randomise selections.

"""
import enum
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from random import choice, randint
from typing import Any, Final, NamedTuple, Optional, Generator, Iterable
from urllib.parse import quote
import re

import requests
import requests_cache

import pydantic_core._pydantic_core
import inflect

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QMessageBox

from yugioh_deck_drafter import util


class CardSetClass(enum.Enum):
    """Enumeration for filtering and selecting specfic types of card
    sets. Matched against the names of sets to allow for categorising."""
    BOOSTER_PACK = enum.auto()
    PROMOTIONAL = enum.auto()
    STARTER_DECK = enum.auto()
    TOURNAMENT = enum.auto()
    TIN = enum.auto()
    PARTICIPATION = enum.auto()
    SPECIAL_EDITION = enum.auto()
    EXCLUSIVE = enum.auto()
    PRIZE = enum.auto()
    MOVIE = enum.auto()
    MASTER_COLLECTION = enum.auto()
    STRUCTURE_DECK = enum.auto()
    DUELIST_PACK = enum.auto()
    CHAMPION_PACK = enum.auto()
    ANNIVERSARY = enum.auto()
    PREMIUM = enum.auto()
    DECK = enum.auto()
    DEMO = enum.auto()
    ADVENT_CALENDAR = enum.auto()
    COLLECTOR_BOX = enum.auto()
    COLLECTION = enum.auto()


class DeckType(enum.Enum):
    """Enumeration for the DeckType"""

    MAIN = enum.auto()
    EXTRA = enum.auto()
    SIDE = enum.auto()
    SEARCH = enum.auto()


class RaceType(enum.Enum):
    """Enumerations for card race values."""

    AQUA = enum.auto()
    BEAST = enum.auto()
    BEAST_WARRIOR = enum.auto()
    CREATOR_GOD = enum.auto()
    CYBERSE = enum.auto()
    DINOSAUR = enum.auto()
    DIVINE_BEAST = enum.auto()
    DRAGON = enum.auto()
    FAIRY = enum.auto()
    FIEND = enum.auto()
    FISH = enum.auto()
    INSECT = enum.auto()
    MACHINE = enum.auto()
    PLANT = enum.auto()
    PSYCHIC = enum.auto()
    PYRO = enum.auto()
    REPTILE = enum.auto()
    ROCK = enum.auto()
    SEA_SERPENT = enum.auto()
    SPELLCASTER = enum.auto()
    THUNDER = enum.auto()
    WARRIOR = enum.auto()
    WINGED_BEAST = enum.auto()
    WYRM = enum.auto()
    ZOMBIE = enum.auto()
    ILLUSION = enum.auto()  # not present on the api page
    # Spell/Trap Cards
    NORMAL = enum.auto()
    FIELD = enum.auto()
    EQUIP = enum.auto()
    CONTINUOUS = enum.auto()
    QUICK_PLAY = enum.auto()
    RITUAL = enum.auto()
    COUNTER = enum.auto()


class CardType(enum.Enum):
    """Card Type Enumerations"""
    MONSTER_CARD = enum.auto()
    EFFECT_MONSTER = enum.auto()
    FLIP_EFFECT_MONSTER = enum.auto()
    FLIP_TUNER_EFFECT_MONSTER = enum.auto()
    GEMINI_MONSTER = enum.auto()
    NORMAL_MONSTER = enum.auto()
    NORMAL_TUNER_MONSTER = enum.auto()
    PENDULUM_EFFECT_MONSTER = enum.auto()
    PENDULUM_EFFECT_RITUAL_MONSTER = enum.auto()
    PENDULUM_FLIP_EFFECT_MONSTER = enum.auto()
    PENDULUM_NORMAL_MONSTER = enum.auto()
    PENDULUM_TUNER_EFFECT_MONSTER = enum.auto()
    RITUAL_EFFECT_MONSTER = enum.auto()
    RITUAL_MONSTER = enum.auto()
    SPELL_CARD = enum.auto()
    SPIRIT_MONSTER = enum.auto()
    TOON_MONSTER = enum.auto()
    TRAP_CARD = enum.auto()
    TUNER_MONSTER = enum.auto()
    UNION_EFFECT_MONSTER = enum.auto()
    FUSION_MONSTER = enum.auto()
    LINK_MONSTER = enum.auto()
    PENDULUM_EFFECT_FUSION_MONSTER = enum.auto()
    SYNCHRO_MONSTER = enum.auto()
    SYNCHRO_PENDULUM_EFFECT_MONSTER = enum.auto()
    SYNCHRO_TUNER_MONSTER = enum.auto()
    XYZ_MONSTER = enum.auto()
    XYZ_PENDULUM_EFFECT_MONSTER = enum.auto()
    SKILL_CARD = enum.auto()
    TOKEN = enum.auto()
    EXTRA_MONSTER = enum.auto()  # Custom


class AttributeType(enum.Enum):
    """Monster element type enumeration."""
    DARK = enum.auto()
    EARTH = enum.auto()
    FIRE = enum.auto()
    LIGHT = enum.auto()
    WATER = enum.auto()
    WIND = enum.auto()
    DIVINE = enum.auto()


class CollectionType(enum.Enum):
    """Enumerations for the type of collection."""
    OCG = enum.auto()
    TCG = enum.auto()


@dataclass
class CardSetModel:
    """Datamodel for a YGO Cardset

    Store base data for a card set and weights in addtional, while also
    carrying the list of weights for random choices.

    """
    set_name: str = field()
    set_code: str = field()
    set_date: date = field()
    set_image: Optional[str] = field(default=None)
    set_class: set[CardSetClass] = field(default_factory=set)
    card_count: int = field(default=1)
    count: int = field(default=1)
    card_set: tuple["CardModel", ...] = field(default_factory=tuple)
    probabilities: tuple[int, ...] = field(default_factory=tuple)


class CardModel(NamedTuple):
    """Datamodel for a YGO Card

    Some data is stored in the raw JSON[dict] format so that could be
    parsed more cleanly in the future
    """

    name: str
    description: str
    card_id: int
    card_type: CardType
    raw_data: dict[str, Any]
    attribute: Optional[AttributeType] = None
    attack: Optional[int] = None
    defense: Optional[int] = None
    level: Optional[int] = None
    rarity: str = "Common"
    card_set: Optional[CardSetModel] = None

    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        setattr(self, item, value)


@dataclass
class DeckModel:
    """Datamodel for a complete YGO Deck"""

    name: str = field(default="Deck")
    main: list[CardModel] = field(default_factory=lambda: [])
    extra: list[CardModel] = field(default_factory=lambda: [])
    side: list[CardModel] = field(default_factory=lambda: [])


@dataclass(frozen=True, unsafe_hash=True)
class CardSetFilter:
    """Filter object for filtering out specfic types of card sets for
    selection.
    """

    card_count: int = field(default=3)
    set_date: date = field(default_factory=date.today)
    set_classes: set[CardSetClass] = field(
        default_factory=lambda: {s for s in CardSetClass}
    )


class YugiObj:
    """Object for managing requests from YGOPRODECK, creating Models and
    generating cardmodels themselves.

    Will immediatly request card_set data in order to grab the information
    for the main window.

    Attributes:
        card_set (list): Data of all the card_sets available.
        arche_types (tuple): List of archetypes for querying at a later point.
        CACHE (CachedSession): Cache for most of the requests except images
            which get managed more manually.
        TYPE_MATCH (dict[enum, set]): For filtering out different subsets of
            cards.
        PROB (defaultdict): probablities for each type of card rarity.
        RARITY_COLORS (defaultdict): For picking and displaying rarity borders.
        CARD_CLASS_NAMES (list): Pre-formatted list of card classes.
        collection_type (CollectionType): Type of collection the cards belong.
            to. Defaults to None

    Methods:
        get_card_set: Gets a list of all card_sets for selection and filtering.
            Called on instantiation.
        get_arche_type_list: Collects a list of arch_types.
            Called on instantiation.
        filter_out_card_sets: Filters out card_sets with a user set
            filter_object.
        complex_search: Search Ygoprodeck with a more complex query. Mostly
            meant for extra deck types.
        infer_set_types: Creates set classes based on a card sets name.
        get_card_set_info: Requests card_set info from the YGOprodeck.
        convert_raw_to_model: Converts or generates a json object into a
            CardModel.
        get_card_art: Collects card_art from Ygoprodeck or from local cache
            and slots them into a QPixmap.
        get_set_art: Collects the set art from Ygoprodeck or local if avaiable.
        grab_arche_type_cards: Collects cards based on a singular type.
        grab_card: Collects a single card based on its name.
        create_card: Generates a card based on provided JSON data.
        to_ygodk_format: Converts a DeckModel to a exportable file format.
        check_extra_monster: Checks if a card belongs in the extra deck.
        find_extra_materials: Calls another object for searching for extra
            material requirements.
        generate_weights: Generates weights based on a set of cards and
            their rarities.
        select_random_packs: Selects random packs based on a bunch of supplied
            criteria.
    """

    CACHE = requests_cache.CachedSession(
        str(Path("cache/ygoprodeck.sqlite")),
        backend="sqlite",
        allowable_codes=[200]
    )

    PROB: Final[defaultdict[str, float]] = defaultdict(
        lambda: 2.8571428571,
        {
            "Common": 80,
            "Rare": 16.6667,
            "Super Rare": 8.3334,
            "Ultra Rare": 4.3478260870,
            "Secret": 2.8571428571,
        },
    )

    RARITY_COLOURS: Final[defaultdict[str, Qt.GlobalColor]] = defaultdict(
        lambda: Qt.GlobalColor.magenta,
        {
            "Rare": Qt.GlobalColor.blue,
            "Super Rare": Qt.GlobalColor.lightGray,
            "Ultra Rare": Qt.GlobalColor.green,
            "Secret": Qt.GlobalColor.magenta,
        },
    )

    TYPE_MATCH = {
        CardType.MONSTER_CARD: {
            CardType.MONSTER_CARD,
            CardType.EFFECT_MONSTER,
            CardType.FLIP_EFFECT_MONSTER,
            CardType.FLIP_TUNER_EFFECT_MONSTER,
            CardType.GEMINI_MONSTER,
            CardType.NORMAL_MONSTER,
            CardType.NORMAL_TUNER_MONSTER,
            CardType.PENDULUM_EFFECT_FUSION_MONSTER,
            CardType.PENDULUM_EFFECT_RITUAL_MONSTER,
            CardType.PENDULUM_FLIP_EFFECT_MONSTER,
            CardType.PENDULUM_EFFECT_FUSION_MONSTER,
            CardType.RITUAL_EFFECT_MONSTER,
            CardType.RITUAL_MONSTER,
            CardType.SPIRIT_MONSTER,
            CardType.TOON_MONSTER,
            CardType.TUNER_MONSTER,
            CardType.UNION_EFFECT_MONSTER,
            CardType.FUSION_MONSTER,
            CardType.LINK_MONSTER,
            CardType.SYNCHRO_MONSTER,
            CardType.SYNCHRO_PENDULUM_EFFECT_MONSTER,
            CardType.SYNCHRO_TUNER_MONSTER,
            CardType.XYZ_MONSTER,
            CardType.XYZ_PENDULUM_EFFECT_MONSTER,
            CardType.EXTRA_MONSTER
        },
        DeckType.EXTRA: {
            CardType.FUSION_MONSTER,
            CardType.LINK_MONSTER,
            CardType.PENDULUM_EFFECT_FUSION_MONSTER,
            CardType.SYNCHRO_MONSTER,
            CardType.SYNCHRO_PENDULUM_EFFECT_MONSTER,
            CardType.SYNCHRO_TUNER_MONSTER,
            CardType.XYZ_MONSTER,
            CardType.XYZ_PENDULUM_EFFECT_MONSTER,
        }
    }
    CARD_CLASS_NAMES = util.enum_to_list(CardSetClass)

    def __init__(
        self,
        collection_type: Optional[CollectionType] = None
    ) -> None:
        self._collection_type = collection_type
        self.card_sets = self.get_card_set()
        self.arche_types = self.get_arche_type_list()

    def get_card_set(self) -> list[CardSetModel]:
        """Collects all card sets for selection.

        Filters out any Card Sets with less than 10 cards in them.
        """
        url = r"https://db.ygoprodeck.com/api/v7/cardsets.php"
        request = self.CACHE.get(url, timeout=20)
        if request.status_code != 200:
            logging.critical("Failed to fetch Card Sets. Exiting!")
            logging.critical("Status Code: %s", request.status_code)
            QMessageBox.critical(
                None, "Critical", "Failed to Grab Card Sets. Retry Later"
            )
            sys.exit()

        data = request.json()

        new_set = []
        for item in data:
            d = item.get("tcg_date")
            if d is None:
                continue
            new_date = datetime.strptime(d, "%Y-%m-%d").date()
            name = item["set_name"]
            set_class = self.infer_set_types(name)
            set_model = CardSetModel(
                set_name=name,
                set_code=item["set_code"],
                set_date=new_date,
                set_image=item.get("set_image"),
                set_class=set_class,
                card_count=item["num_of_cards"],
            )
            new_set.append(set_model)

        new_set.sort(key=lambda x: x.set_name)

        return new_set

    def get_arche_type_list(self) -> tuple[str, ...]:
        """Grabs an archetype list from ygoprodeck and cleans the data
        structure.

        Returns:
            tuple[str]: An array of strings denoting each card archetype.
        """
        url = "https://db.ygoprodeck.com/api/v7/archetypes.php"
        request = self.CACHE.get(url, timeout=20)
        if request.status_code != 200:
            logging.critical("Failed to Archetype List. Exiting!")
            logging.critical("Status Code: %s", request.status_code)
            QMessageBox.critical(
                None,
                "Critical",
                "Failed to fetch remote Arche Types.\
                                  Retry Later",
            )
            sys.exit()

        archetype = [i["archetype_name"].upper() for i in request.json()]
        return tuple(archetype)

    def filter_out_card_sets(
        self, card_set: CardSetModel, set_filter: CardSetFilter
    ) -> bool:
        """Filters out card_sets based on the criteria provided.

        To be used with a filter function or a seperate loop.

        Args:
            card_set (CardSetModel): The card_set to check
            set_filter (CardSetFilter): Datamodel containing the info on what
                to check against.

        Returns:
            bool: If card set matches the count, date and set type it returns.
                true.
        """
        count_bool = card_set.card_count >= set_filter.card_count
        date_bool = card_set.set_date <= set_filter.set_date
        cls_bool = any(x in card_set.set_class for x in set_filter.set_classes)

        return count_bool and date_bool and cls_bool

    def complex_search(
        self,
        material: "ExtraMaterial",
        card_type: CardType | DeckType = CardType.MONSTER_CARD
    ) -> list[CardModel]:
        """Search method for looking niche types of cards.

        Args:
            material (ExtraMaterial): Data model of information for searching
                ygoprodeck.
            card_type (CardType): Overall type of card to filter in.
                Defaults to CardType.MONSTER_CARD

        Returns:
            list[CardModel]: List of cards fomatted into a datamodel.
        """
        PROP_MATCH = {
            "card_type": "type"
        }

        base_url = "https://db.ygoprodeck.com/api/v7/cardinfo.php?"

        if material.level != -1:
            base_url += "level={comparison}{level}"
            base_url = base_url.format(
                comparison=material.comparison, level=material.level
            )
        for item in material.materials:
            if isinstance(item, DamageValues):
                continue
            if not item.polarity or item.subtype == "name":
                continue
            if base_url[-1] != "?":
                base_url += "&"
            name = item.name
            if isinstance(name, enum.Enum):
                name = re.sub(r'([\-\_])', " ", name.name.lower())

            sub_type = PROP_MATCH.get(item.subtype, item.subtype)
            base_url += f"{sub_type}={name}"

        logging.debug("Requesting complex query with url %s", base_url)
        request = self.CACHE.get(base_url, timeout=20)

        if request.status_code != 200:
            logging.critical("Failed to Archetype List. Exiting!")
            logging.critical("Status Code: %s", request.status_code)
            QMessageBox.critical(
                None,
                "Critical",
                "Failed to fetch remote Complex Query. "\
                f"Retry Later. \nURL: {base_url}",
            )
            return []

        data = self.convert_raw_to_card_model(None, request.json()["data"])

        self.filter_cards(material, data, card_type)

        return data

    def infer_set_types(self, set_name: str) -> set[CardSetClass]:
        """Parses the name of a card set and generates set classes for
        filtering purposes later on.

        Args:
            set_name (str): To filter out various sets in the collection.
        """
        set_classes: set[CardSetClass] = set()
        for set_class in self.CARD_CLASS_NAMES:
            if set_class in set_name.lower():
                sclass = CardSetClass[set_class.upper().replace(" ", "_")]
                set_classes.add(sclass)
        if not set_classes:
            set_classes.add(CardSetClass.BOOSTER_PACK)

        return set_classes

    def get_card_set_info(self, card_set: CardSetModel) -> list[CardModel]:
        """Returns the cards contained within the given card set."""
        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php?cardset={0}"
        request = self.CACHE.get(url.format(card_set.set_name), timeout=20)

        data = request.json()
        if request.status_code != 200 or not isinstance(data, dict):
            logging.critical("Failed to fetch Card Sets. Exiting!")
            logging.critical("Status Code: %s", request.status_code)
            QMessageBox.critical(
                None, "Critical", "Failed to Grab Card Sets. Retry Later"
            )
            sys.exit()

        data = data["data"]
        cards = self.convert_raw_to_card_model(card_set, data)

        return cards

    def convert_raw_to_card_model(
        self,
        card_set: CardSetModel | None,
        data: list[dict],
    ) -> list[CardModel]:
        """Converts raw json response data into usable card models.

        Args:
            card_set (CardSetModel | None): Card set for defining rarity.
                *Note might have to use derive the card set from available data
                in the future.
            data (list[dict]): Raw json data for conversion

        Returns:
            list[CardModel]: A list of card data converted into card models.
        """
        cards = []
        for card_data in data:
            card = self.create_card(card_data, card_set)
            cards.append(card)

        return cards

    def filter_cards(
        self,
        search_material: 'ExtraMaterial',
        cards: list[CardModel],
        subtype: CardType | DeckType
    ) -> None:
        """Filters out cards based on the supplied arguments.

        Args:
            search_material (ExtraMaterial): Material data structure for
                specific targeted search material.
            cards (list[CardModel]): The list of cards to filter out.
            subtype (CardType): A general list of subtypes to keep.
        """
        stype_list = self.TYPE_MATCH.get(
            subtype,
            self.TYPE_MATCH[CardType.MONSTER_CARD])

        for item in search_material.materials:
            if isinstance(item, DamageValues) or item.polarity:
                continue
            for card in list(cards):

                if (card[item.subtype] == item.name
                   or card.card_type not in stype_list):
                    idx = cards.index(card)
                    cards.pop(idx)

    def get_card_art(self, card: CardModel) -> QPixmap | None:
        """Collects and stores card art for the given piece.

        Will return a default image here if neede

        Args:
            card (YGOCard): Card data for grabbing the card art.

        Returns:
            QPixmap | None: Image in a pixmap format ready to displayed on the
                PyQt GUI.
        """
        image_store = Path("assets/images/card_art")
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

    def get_set_art(self, set_model: CardSetModel) -> QPixmap | None:
        """Collects set art from YGOPRODECK for the set_model provided.

        Args:
            set_model (CardSetModel): Set model where the set_code will be
                taken from.

        Returns:
            QPixmap | None: Converted pixmap if it exists, otherwise nothing.
        """
        image_store = Path(r"assets/images/set_art")
        image_store.mkdir(parents=True, exist_ok=True)
        set_code = set_model.set_code
        image_path = image_store / str(str(set_code) + ".jpg")

        if image_path.exists():
            return util.get_or_insert(image_path)

        url = "https://images.ygoprodeck.com/images/sets/{0}.jpg"
        request = requests.get(url.format(set_code), timeout=10)
        if request.status_code != 200:
            # Add a default image here in the future.
            logging.error("Failed to fetch card image. Using Default")
            logging.error("Status Code: %s", request.status_code)
            return

        data = request.content
        with image_path.open("wb") as image_file:
            image_file.write(data)

        image = util.get_or_insert(image_path, data=data)

        return image

    def grab_arche_type_cards(
        self,
        card_arche: enum.Enum | str,
        subtype: str = "archetype"
    ) -> list[CardModel]:
        """Filters out cards with the specfied subtype.

        Queries YGOPRODECK for specified subtype(str) with archetype included.

        Args:
            card_arche (str): Actual name of the type of the subtype.
            subtype (str, optional): Subtype of the Card.
                                     Defaults to "archetype".

        Returns:
            list | None: Either returns None if the query is bad or converted
                json data retrieved.
        """
        if isinstance(card_arche, enum.Enum):
            card_arche = util.clean_enum_name(card_arche)  # type: ignore

        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php?{0}={1}"
        request = self.CACHE.get(url.format(subtype, card_arche), timeout=10)

        if request.status_code != 200:
            logging.warning("Failed to fetch card %s. Skipping!", subtype)
            logging.warning("Status Code: %s", request.status_code)
            return []

        return self.convert_raw_to_card_model(None, request.json()["data"])

    def grab_card(self, name: str, fuzzy: bool = False) -> dict | None:
        """Collects card info for the given name(str).

        Args:
            name (str): Name of the card as provided from previous queries.
            fuzzy (bool): Toggle for enabling fuzzy search with this method.
                Defaults to False.

        Returns:
            dict | None: JSON data or nothing if the query fails.
        """
        n = "name"
        if fuzzy:
            n = "fname"

        name = quote(name.lower(), safe="/:?&")
        url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?{n}={name}"
        request = self.CACHE.get(url, timeout=10)

        if request.status_code != 200:
            logging.warning("Failed to grab %s. Skipping!", name)
            logging.warning("Status Code: %s", request.status_code)
            return

        return request.json()["data"]

    def create_card(
        self,
        data: dict,
        set_data: Optional[CardSetModel] = None
    ) -> CardModel:
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

        if isinstance(set_data, CardSetModel):
            card_sets = data["card_sets"]
            for card_set in card_sets:
                card_set_code = card_set["set_code"]
                if set_data.set_code in card_set_code:
                    rarity = card_set["set_rarity"]
                    break

        type_enum = CardType[data["type"].upper().replace(" ", "_")]
        attrib = data.get("attribute")
        if attrib is not None:
            attrib = attrib.upper().replace(" ", "_")
            attrib = AttributeType[attrib]

        card = CardModel(
            name=data["name"],
            description=self.filter_card_description(data),
            card_id=data["id"],
            card_type=type_enum,
            raw_data=data,
            attribute=attrib,
            attack=data.get("atk"),
            defense=data.get("def"),
            level=data.get("level"),
            rarity=rarity,
            card_set=set_data,
        )

        return card

    def filter_card_description(self, data: dict) -> str:
        """Filters out the correct card description if multiple are present.

        Args:
            data (dict): Raw json data with the descriptions strings.

        Returns:
            str: Correct description text.
        """
        desc = data.get("monster_desc")
        if desc is not None:
            return desc.replace("Rank", "Level")

        return data.get("desc", "").replace("Rank", "Level")

    def to_ygodk_format(self, deck: DeckModel) -> str:
        """Generates and formats a .ydk file format from the provided deck.

        Args:
            deck (DeckModel): Model of the deck containing the selected cards.

        Returns:
            str: File in a str newline concated str.
        """

        def create_text(data: list[CardModel]) -> str:
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

    def check_extra_monster(self, card: CardModel) -> bool:
        """Checks if a card belongs in the side deck.

        Args:
            card (CardModel): Card to be Checked

        Returns:
            bool: Checks if a card model variable in present in a class
                constant.
        """
        return card.card_type in self.TYPE_MATCH[DeckType.EXTRA]

    def find_extra_materials(
        self,
        card: CardModel
    ) -> tuple["ExtraMaterial", ...]:
        """Parses the given cards description in order to find the extra
        summoning materials.

        Args:
            card (CardModel): The information to be parsed.

        Returns:
            tuple: An array of extra materials.
        """
        search = ExtraSearch(self, card)
        material = search.parse_description()

        return material

    def generate_weights(
        self,
        card_set_name: str,
        data: list[CardModel],
        extra: bool = False
    ) -> tuple[int, ...]:
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

    def select_random_packs(
        self,
        pack_set: list[CardSetModel],
        count_range: range,
        max_packs: int = 40
    ) -> list[CardSetModel]:
        """Selects random packs based on the supplied criteria.
        Args:
            pack_set (list[CardSetModel]): Collection of card_sets to select
                from.
            count_range (range): Minimum and Maximum amount of cards per
                selection. Might be limited by numbers of cards in a set or
                how cards have already been added.
            max_packs (int, optional): Total amount of packs to be selected.
                Defaults to 40.

        Returns:
            list[CardSetModel]: Randomised list of card sets based on the
                parameters.
        """
        pack_counter = 0
        packs_to_add = []

        while pack_counter < max_packs:
            chosen_pack = choice(pack_set)
            total_pack = randint(count_range.start, count_range.stop)
            if chosen_pack.card_count < 10:
                total_pack = 1

            chosen_pack.count = min(max_packs - pack_counter, total_pack)
            packs_to_add.append(chosen_pack)
            pack_counter += chosen_pack.count

        return packs_to_add

    @property
    def collection_type(self) -> None | CollectionType:
        return self._collection_type

    @collection_type.setter
    def collection_type(self, ctype: Optional[CollectionType] = None) -> None:
        self._collection_type = ctype


class ExtraSubMaterial(NamedTuple):
    """Type of extra deck summoning material."""
    name: str | enum.Enum
    subtype: str
    polarity: bool = True

    def __hash__(self) -> int:
        return hash(str(self.name) + self.subtype)

    def __eq__(self, other: 'ExtraSubMaterial'):
        return hash(self) == hash(other)


class DamageValues(NamedTuple):
    """Data structure for holding required def & attack values."""
    subtype: str = "damage"
    comparison: str = ""
    attack: int = -1
    defense: int = -1


@dataclass()
class ExtraMaterial:
    """Extra Material Info for Special Summons Types."""
    level: int = field(default=-1)
    comparison: str = field(default="")
    count: int = field(default=1)
    materials: list[ExtraSubMaterial | DamageValues]\
        = field(default_factory=list)

    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        setattr(self, item, value)


class ExtraSearch:
    """Extra Search Object for finding extra deck special summon materials.

    Args:
        parent (YugiObj): For searching and retrieving card information.
        card_model (CardModel): For search information and context parsing.

    Methods:
        parse_description: Main method which runs the description parsing
            process
        split_description: Splits a returns description parts according to
            the main seperator(+).
        find_extra_material: Builds the actual core data structure for the
            search information
        find_monster_cap: Finds monster cards and types for searching.
        create_sub_material: Generate a sub data structure for searching.
        find_level: Finds a min/max level if there is one present in the
            description.
        find_count: Finds the minimum count of monster required for the extra
            special summon.
        check_subtype: Searches for a matching subtype of a card property.
        find_comparison: Searches for a comparison element inside the cards
            description.

    Attributes:
        parse_types: List of accepted side deck types.
        ENGINE: For simplifying plurals when checking for card type.
    """
    COMPARISONS: dict[str, str] = {
        "or more": "gte",
        "or higher": "gte",
        "or lower": "lte",
        "or less": "lte",
    }

    ENGINE = inflect.engine()

    def __init__(self, parent: YugiObj, card_model: CardModel) -> None:
        self.parent = parent
        self.card_model = card_model

        self.parse_types = parent.TYPE_MATCH[DeckType.EXTRA].copy()

    def parse_description(self) -> tuple[ExtraMaterial, ...]:
        """Base Method that runs the entire search."""
        if self.card_model.card_type not in self.parse_types:
            return tuple([self.filter_assocciated()])

        if "\n" in self.card_model.description:
            desc = self.card_model.description.split("\n")[0].replace("\r", "")
        else:
            desc = self.card_model.description.split("/")[0]

        data: list[ExtraMaterial] = []
        for part in self.split_description(desc):
            mat = self.find_extra_material(part)
            data.append(mat)

        # Change for description with a ´comma' or 'including'
        if data[-1].count == 0 and data[0].count > 1:
            data[0].count -= 1
            data[-1].count += 1
            data[-1].materials.extend(data[0].materials)

        for item in data:
            item.count = max(item.count, 1)

        return tuple(data)

    def filter_assocciated(self) -> ExtraMaterial:
        """Filters out assocciated cards for quick adding with the submenu.

        Function for basic filtering of items in a description.

        Returns:
            ExtraMaterial: Data model of the extra material defining what the
                drafter can add.
        """
        pattern = re.compile(r'(?<!\\)"(.*?[^\\])"')
        matches = re.findall(pattern, self.card_model.description)

        filt_matches = ExtraMaterial()
        for item in matches:
            data = self.parent.grab_card(item)
            # Might want to use the data here instead of the name to avoid some
            # unnecessary processing the future.
            if data is None or item == self.card_model.name:
                continue
            filt_matches.count += 1
            model = ExtraSubMaterial(item, "name")
            filt_matches.materials.append(model)

        return filt_matches

    def split_description(self, desc: str) -> Generator[str, None, None]:
        """Split description apart according to each seperate chunk and return
        part by part.

        Args:
            desc (str): Whole description preprocessed and cut off from the
                previous end.

        Yields:
            str: Each seperated part of the description.
        """
        start = 0
        patt = re.compile(r"((,)?(including ))|( \+ )|(?<=\")( , )(?:\")")
        for m in re.finditer(patt, desc):
            chunk = desc[start:m.span()[0]]
            yield chunk
            start = m.span()[1]

        yield desc[start:len(desc)]

    def find_extra_material(self, desc: str) -> ExtraMaterial:
        """Create the final extra material data structure which the search
        dialog uses.

        Args:
            desc (str): Part of the description to parse through.

        Returns:
            ExtraMaterial: Data for finding the extra material.
        """
        extra_mat = ExtraMaterial()
        extra_mat.count = self.find_count(desc)
        self.req_level = self.find_level(desc)
        extra_mat.level = self.req_level
        extra_mat.comparison = self.find_comparison(desc)

        if "special summon" in desc.lower():
            if '\"Mask Change\"' in desc:
                monster_cap = [ExtraSubMaterial("mask change", "name")]
            elif '\"NEX\"' in desc:
                monster_cap = [ExtraSubMaterial("nex", "name")]
            elif '\"The Claw of Hermos\"' in desc:
                monster_cap = [ExtraSubMaterial("the claw of hermos", "name")]
            extra_mat.count = 1
        elif self.card_model.name == "Phantasmal Lord Ultimitl Bishbaalkin":
            extra_mat.level = 8
            extra_mat.count = 2
            extra_mat.comparison = "gte"
        else:
            monster_cap = self.find_monster_cap(desc)

        if "monster_cap" in locals():
            extra_mat.materials = monster_cap  # type: ignore

        attrib = self.find_stat_cap(desc)
        if attrib.attack != -1 or attrib.defense != -1:
            extra_mat.materials.append(attrib)  # type: ignore

        if not extra_mat.count:
            for item in extra_mat.materials:
                if item.subtype == "name":
                    extra_mat.count += 1

        return extra_mat

    def find_monster_cap(self, text: str) -> list[ExtraSubMaterial]:
        """Parses the given card description for card types.

        1. Checks for archetypes/names within quotations.
        2. Checks monster types with monster followups.
        3. Checks for monster types with a '-type' suffix.
        4. Checks monsters with count former count prefixes.
        5. Lastly checks negative items to remove other items.

        Args:
            text (str): Chunk of description to be parsed.

        Returns:
            list[str]: A set with all the types with the none elements removed.
        """
        logging.debug("Look for monsters in \"%s\"", text)
        data: set[ExtraSubMaterial] = set()
        checked_words = set()

        text = text.lower().replace("on the field", "")
        text = re.sub(r"\+", "", text)

        arche_patt = r'(?<=")([a-z0-9]{1}[a-z0-9- #\,\'\.]+[a-z0-9α]{1})(?:")'
        archetype_match = re.findall(arche_patt, text, re.I)
        checked_words.update(archetype_match)
        data.update(self.create_sub_material(
            archetype_match,
            last_check=True,
            fuzzy=True))

        monster_type_capture = r"(?<!non-)([a-z-]+)(?:(monster)(s?))"
        monster_match = re.findall(monster_type_capture, text, re.I)
        checked_words.update(monster_match)
        data.update(self.create_sub_material(monster_match))

        sub_type_capture = r"([a-z]+)(?:-type){1}"
        sub_type_match = re.findall(sub_type_capture, text, re.I)
        checked_words.update(sub_type_match)
        data.update(self.create_sub_material(sub_type_match))

        counted_type_capture = r"(?<=[1-9]).*?(?=\s\d|$)"
        counted_match = re.findall(counted_type_capture, text, re.I)
        checked_words.update(counted_match)
        data.update(self.create_sub_material(counted_match))

        negative_capture = r"(?<=non-)([a-z]{4,})"
        negative_match = re.findall(negative_capture, text, re.I)
        checked_words.update(negative_match)
        data.update(self.create_sub_material(negative_match, False))

        re_data = data.copy()
        logging.debug("Regex found %s", re_data)
        for item in data:
            if item.subtype == "name":
                return list(data)

        # Need a cleaner solution here in the future, as edge cases are making
        # it super overcomplicated
        for word in text.split():
            if word in checked_words or '"' in word:
                continue

            word = re.sub(r"[\(\)\,\"]", "", word)
            if word == "winged" and word + " beast" in text:
                word = "winged beast"
            elif word == "sea" and word + " serpent" in text:
                word = "sea serpent"

            sub_mat = self.create_sub_material([word], last_check=False)
            data.update(sub_mat)

        logging.debug("Brute Force Found %s", data.difference(re_data))

        return list(data)

    def create_sub_material(
        self,
        data: Iterable,
        polarity: bool = True,
        last_check: bool = True,
        fuzzy: bool = False
    ) -> list[ExtraSubMaterial]:
        """Creates sub material NamedTuples.

        Args:
            data (Iterable): Data to parse through
            polarity (bool, optional): If its a removing or adding item.
                Defaults to True.
            last_check (bool): For toggling on and off name searches.
                Defaults to True.
            fuzzy (bool): For toggling on and off fuzzy searches.
                Defaults to False

        Returns:
            list[ExtraSubMaterial]: Parsed items in a list.
        """
        sub_mats = []

        for item in data:
            if item == self.card_model.name.lower():
                continue
            try:
                subtype, pitem = self.check_subtype(item, last_check, fuzzy)
            except KeyError as k:
                logging.info("%s | %s: item", k, item)
                if " " in item:
                    mat = self.create_sub_material(
                        item.split(), polarity, last_check, fuzzy)
                    sub_mats.extend(mat)
                continue

            checked_polarity = self.polarity_test(item, polarity)
            material = ExtraSubMaterial(pitem, subtype, checked_polarity)
            sub_mats.append(material)

        return sub_mats

    def polarity_test(self, text: str, previous: bool) -> bool:
        """Tests if the item is a negative search or positive search.

        Args:
            text (str): Description of the card that is being queried.
            previous (bool): Current assumed polarity of the item.

        Returns:
            bool: If its a negative item it will be detected as False.
        """
        whole_desc = re.sub('\"', '', self.card_model.description).lower()

        if "except " + text in whole_desc:
            return False

        return previous

    def find_level(self, text: str) -> int:
        """Finds a level in the description if present.

        Args:
            text (str): Pretrimmed description for the regex search.

        Returns:
            int: Level in int format. If not found it will be a -1.
        """
        level_search = re.findall(r"(?<=Level )(1[0-3] |[0-9] )", text)
        if not level_search:
            return -1

        level = int(level_search[0])

        return level

    def find_stat_cap(self, text: str) -> DamageValues:
        """Parses the description and finds the values for attack and defense
        properties.

        Args:
            text (str): Part of description to be parsed for stats ATK/DEF.

        Returns:
            DamageValues: Filled in values with the required statistics.
                Most values will default to -1 if none existant.
        """
        logging.debug("Checking \"%s\" for attribute values.", text)
        label_pattern = re.compile(r"ATK|DEF")
        labels = re.findall(label_pattern, text)

        if not labels:
            return DamageValues()

        amount_pattern = re.compile(r"(?=(?<=with.)*(\d{4,}).*)")
        values = re.findall(amount_pattern, text)

        data = defaultdict(lambda: -1,
                           map(lambda key, val: (key, val), labels, values))

        comp = self.find_comparison(text, "Stat")

        dvalues = DamageValues(
            comparison=comp,
            attack=data["ATK"],
            defense=data["DEF"])

        return dvalues

    def find_count(self, text: str) -> int:
        """Finds the minimum count of monsters required to summon the extra
        monster.

        Args:
            text (str): Description of the card pre-trimmed/processed.

        Returns:
            int: Total number of extra monsters. Defaults to 1.
        """
        text = text.replace("+", "")

        if text[0].isdigit():
            return int(text[0])
        patt = re.compile(r"(?<!\()(?<!Level )(?<![1-9])([1-9] ){1}(?![#\)])")
        count_search = re.findall(patt, text)
        if count_search is None:
            return 1

        count = sum(map(int, count_search))

        return count

    def check_subtype(
        self,
        target: str,
        last_check: bool = True,
        fuzzy: bool = True
    ) -> tuple[str, enum.Enum | str]:
        """Checks Enums and other type lists and returns a subtype if it
        matches.

        Args:
            target (str): Name of the type to look for inside the subypes.
            last_check (bool): For toggling on and off name searches.
                Defaults to True.
            fuzzy (bool): For toggling on and off fuzzy searches.
                Defaults to True

        Returns:
            str: The name of the sub type for further use.

        Raises:
            KeyError: If no sub type is found.
        """
        og_target = re.sub(r"\"", "", target)
        target = og_target
        try:
            singular = self.ENGINE.singular_noun(target)
        except pydantic_core._pydantic_core.ValidationError:
            raise KeyError(f"{target} not found in any subtype.")

        if isinstance(singular, str):
            target = singular

        if target.upper() in self.parent.arche_types:
            return "archetype", target

        if target == "d/d/d":
            return "archetype",  "d/d"
        if target == "flip":
            target += " effect"

        ETL = util.enum_to_list
        clean_target = target.lower().removesuffix("-type").replace("-", " ")

        if clean_target in ETL(AttributeType):
            return "attribute", AttributeType[clean_target.upper()]
        elif clean_target in ETL(RaceType):
            return "race", RaceType[clean_target.upper().replace(" ", "_")]
        elif clean_target + " monster" in ETL(CardType):
            clean_target = clean_target + " monster"
            return "card_type", CardType[clean_target.upper().replace(" ", "_")]

        if last_check:
            # Should change this to query local items in the future as it calls
            # the API to much.
            data = self.parent.grab_card(og_target.lower())
            if data is not None:
                return "name", og_target

        if fuzzy:
            data = self.parent.grab_card(og_target.lower(), True)
            if data is not None:
                return "fname", og_target

        logging.error("Card: %s", self.card_model.name)
        raise KeyError(f"{target} not found in any subtype.")

    def find_comparison(self, desc: str, element: str = "Level") -> str:
        """Match a comparison for limiters on card count and levels.

        Args:
            desc (str): Part of description to be parsed.
            elment (element): Which property does the comparison belong to.
                Defaults to Level.

        Returns:
            str: Symbol for matching the correct range over Extra Material.
        """

        for k, v in self.COMPARISONS.items():
            if f"Level {self.req_level} " + k in desc:
                return v
            elif element != "Level" and k in desc:
                return v

        return ""


def test_assocciated_cards() -> None:
    """Testing function for assccoiated card parsing. Requires a json import to
    function
    """
    ygo_data = YugiObj()

    # sys.exit()
    data = Path("cache/all_cards.json")
    with data.open("r", encoding="utf-8") as file:
        d = json.loads(file.read())

    checked_extra = Path("cache/checked_cards.json")
    with checked_extra.open("r") as file:
        check_cards = json.loads(file.read())

    checked_desc = set()

    cnt = 0
    for index, card in enumerate(d):
        model = ygo_data.create_card(card, None)
        if model is None or not ygo_data.check_extra_monster(model):
            continue
        cnt += 1
        print(model.name.center(60, "-"))
        desc = model.description.split("\n")[0]
        if check_cards.get(model.name) or desc in checked_desc:
            checked_desc.add(desc)
            continue
        for i in ygo_data.find_extra_materials(model):
            print(i)
        print(len(d) - index, "left")
        print("Does the extra breakdown make sense?")
        print(desc)
        correct = input("(Enter)-Yes | (Anything)-No > ")
        if correct == "":
            check_cards[model.name] = True
        else:
            check_cards[model.name] = False
        checked_desc.add(desc)

        with checked_extra.open("w") as file:
            file.write(json.dumps(check_cards))


if __name__ == "__main__":

    fmt = "%(levelname)s | .\\yugioh_deck_drafter"
    fmt += "\\%(module)s.py:%(lineno)d -> %(message)s"
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=fmt)
    import json

    test_assocciated_cards()
