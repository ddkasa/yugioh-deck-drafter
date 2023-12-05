"""ygo_data.py

Classes & Functions for managing the YGOPRODECK API communication, modelling
card sets/cards and exporting to the .ydk format.

Usage:
    Instantiate YugiObj and load in and process card data as you need
        randomise selections..

"""

import enum
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from random import choice, randint
from typing import Any, Final, NamedTuple, Optional, Generator
from urllib.parse import quote
import re

import requests
import requests_cache

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


class AttributeType(enum.Enum):
    """Monster element type enumeration."""
    DARK = enum.auto()
    EARTH = enum.auto()
    FIRE = enum.auto()
    LIGHT = enum.auto()
    WATER = enum.auto()
    WIND = enum.auto()
    DIVINE = enum.auto()


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
    card_set: tuple['CardModel', ...] = field(default_factory=tuple)
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
    set_classes: set[CardSetClass]\
        = field(default_factory=lambda: {s for s in CardSetClass})


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
        RARITY_COLORS (defaultdict): For picking and displaying rarity borders.
    """

    CACHE = requests_cache.CachedSession(str(Path("cache/ygoprodeck.sqlite")),
                                         backend="sqlite",
                                         allowable_codes=[200])

    PROB: Final[defaultdict[str, float]] = defaultdict(
        lambda: 2.8571428571,
        {"Common": 80,
         "Rare": 16.6667,
         "Super Rare": 8.3334,
         "Ultra Rare": 4.3478260870,
         "Secret": 2.8571428571
         })

    RARITY_COLOURS: Final[defaultdict[str, Qt.GlobalColor]] = defaultdict(
        lambda: Qt.GlobalColor.magenta,
        {"Rare": Qt.GlobalColor.blue,
         "Super Rare": Qt.GlobalColor.lightGray,
         "Ultra Rare": Qt.GlobalColor.green,
         "Secret": Qt.GlobalColor.magenta
         })

    SIDE_DECK_TYPES: Final[set[CardType]] = {
        CardType.FUSION_MONSTER,
        CardType.LINK_MONSTER,
        CardType.PENDULUM_EFFECT_FUSION_MONSTER,
        CardType.SYNCHRO_MONSTER,
        CardType.SYNCHRO_PENDULUM_EFFECT_MONSTER,
        CardType.SYNCHRO_TUNER_MONSTER,
        CardType.XYZ_MONSTER,
        CardType.XYZ_PENDULUM_EFFECT_MONSTER
        }

    CARD_CLASS_NAMES = util.enum_to_list(CardSetClass)

    def __init__(self) -> None:
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
            QMessageBox.critical(None,
                                 "Critical",
                                 "Failed to Grab Card Sets. Retry Later")
            sys.exit()

        data = request.json()

        new_set = []
        for item in data:
            d = item.get("tcg_date")
            if d is None:
                continue
            new_date = datetime.strptime(d, '%Y-%m-%d').date()
            name = item["set_name"]
            set_class = self.infer_set_types(name)
            set_model = CardSetModel(set_name=name,
                                     set_code=item["set_code"],
                                     set_date=new_date,
                                     set_image=item.get("set_image"),
                                     set_class=set_class,
                                     card_count=item["num_of_cards"])
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
        request = self.CACHE.get(url, timeout=2)
        if request.status_code != 200:
            logging.critical("Failed to Archetype List. Exiting!")
            logging.critical("Status Code: %s", request.status_code)
            QMessageBox.critical(None, "Critical",
                                 "Failed to fetch remote Arche Types.\
                                  Retry Later")
            sys.exit()

        archetype = [i["archetype_name"] for i in request.json()]
        return tuple(archetype)

    def filter_out_card_sets(
        self,
        card_set: CardSetModel,
        set_filter: CardSetFilter
    ) -> bool:
        """Filters out card_sets based on the criteria.

        To be used with a filter function or a seperate loop.

        Args:
            card_set (CardSetModel): The card_set to check
            set_filter (CardSetFilter): Datamodel containing the info on what
                to check agaisnt.

        Returns:
            bool: If card set matches the count, date and set type it returns.
                true.
        """
        count_bool = card_set.card_count >= set_filter.card_count
        date_bool = card_set.set_date <= set_filter.set_date
        cls_bool = any(x in card_set.set_class for x in set_filter.set_classes)

        return count_bool and date_bool and cls_bool

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
        cards = self.convert_raw_to_card_model(card_set, data)

        return cards

    def convert_raw_to_card_model(
        self,
        card_set: CardSetModel | None,
        data: list[dict]
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
            QPixmap | None: _description_
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
        request = self.CACHE.get(url.format(subtype, card_arche),
                                 timeout=10)

        if request.status_code != 200:
            logging.warning("Failed to fetch card %s. Skipping!", subtype)
            logging.warning("Status Code: %s", request.status_code)
            return []

        return self.convert_raw_to_card_model(None, request.json()["data"])

    def grab_card(self, name: str) -> dict | None:
        """Collects card info for the given name(str).

        Args:
            name (str): Name of the card as provided from previous queries.

        Returns:
            dict | None: JSON data or nothing if the query fails.
        """

        name = quote(name.lower(), safe="/:?&")
        url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?name={name}"
        request = self.CACHE.get(url, timeout=10)

        if request.status_code != 200:
            logging.warning("Failed to grab %s. Skipping!", name)
            logging.warning("Status Code: %s", request.status_code)
            return None

        return request.json()["data"]

    def create_card(
        self,
        data: dict,
        set_data: CardSetModel | None
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

        card = CardModel(name=data["name"],
                         description=data["desc"],
                         card_id=data["id"],
                         card_type=type_enum,
                         raw_data=data,
                         attribute=attrib,
                         attack=data.get("atk"),
                         defense=data.get("def"),
                         level=data.get("level"),
                         rarity=rarity,
                         card_set=set_data)

        return card

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
            bool: checks if a card model variable in present in a class
                constant.
        """
        return card.card_type in self.SIDE_DECK_TYPES

    def find_extra_materials(
        self,
        card: CardModel
    ) -> tuple['ExtraMaterial', ...]:
        """Parses the given cards description in order to find the extra
        summoning materials.

        Args:
            card (CardModel): The information to be parsed.

        Returns:
            tuple: An array of extra materials.
        """
        search = ExtraSearch(self, card)
        material = search.find_extra_material()
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


@dataclass()
class ExtraMaterial:
    """Extra Material Info for Special Summons Types."""
    count: int = field(default=1)
    comparison: str = field(default="==")
    count: int = field(default=1)
    cardtype: Optional[CardType] = field(default=None)
    archetype: Optional[str] = field(default=None)
    element: Optional[AttributeType] = field(default=None)
    race: Optional[RaceType] = field(default=None)

    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        setattr(self, item, value)


class ExtraSearch:

    def __init__(self, parent: YugiObj, card_model: CardModel) -> None:
        self.parent = parent
        self.card_model = card_model

    def parse_description(self) -> tuple[ExtraMaterial, ...]:
        """Base Method that runs the entire search.
        """
        desc = self.card_model.description.split("\n")[0].replace("\r", "")
        data = []
        for part in self.split_description(desc):
            mat = self.find_extra_material(part)
            data.append(mat)

        return tuple(data)

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
        for m in re.finditer(r"( \+ )", desc):
            chunk = desc[start:m.span()[0]]
            yield chunk
            start = m.span()[1]

        yield desc[start:len(desc)]

    def find_extra_material(self, desc: str) -> ExtraMaterial:
        extra_mat = ExtraMaterial()

        return extra_mat

    def find_monster_cap(self, text: str) -> set[str]:
        """Parses the given text for types and returns a set.

        Args:
            text (str): Chunk of description to be parsed.

        Returns:
            set[str]: A set with all the types with the none elements removed.
        """
        data = set()

        archetype_capture = r'(?<="|\')(.*?[A-Za-z-])(?:"|\')'
        data.update(re.findall(archetype_capture, text))

        monster_type_capture = r'(?<!non-)([a-zA-Z-]+)(?: monster)'
        data.update(re.findall(monster_type_capture, text))

        negative_capture = r'(?<=non-)([A-Za-z]{4,})'
        data.difference_update(re.findall(negative_capture, text))

        return data

    def find_level(self, text: str) -> int:
        """Finds a level in the description if present.

        Args:
            text (str): Pretrimmed description for the regex search.

        Returns:
            int: Level in int format. If not found it will be a -1.
        """
        level = -1

        level_search = re.match(r'(?<=Level )([1-9])', text)
        if level_search is None:
            return -1

        level = int(level_search.group(0))

        return level

    def find_count(self, text: str) -> int:
        """Finds the minimum count of monsters required to summon the extra
        monster.

        Args:
            text (str): Description of the card pre-trimmed/processed.

        Returns:
            int: Total number of extra monsters. Defaults to 1.
        """
        count_search = re.findall(r'(?<!Level )([1-9]){1,}', text)
        if count_search is None:
            return 1

        count = sum(map(int, count_search))

        return count

    def check_subtype(self, target: str) -> tuple[str, enum.Enum | str]:
        """Checks Enums and other type lists and returns a subtype if it
        matches.

        Args:
            target (str): Name of the type to look for inside the subypes.

        Returns:
            str: The name of the sub type for further use.

        Raises:
            KeyError: If no sub type is found.
        """

        if target in self.parent.arche_types:
            return "archetype", target

        ETL = util.enum_to_list
        target.upper().replace(" ", "_")
        if target in ETL(AttributeType):
            return "attribute", AttributeType[target]
        elif target in ETL(RaceType):
            return "race", RaceType[target]
        elif target in ETL(CardType):
            return "cardtype", CardType[target]
        else:
            data = self.parent.grab_card(target)
            if data is None:
                raise KeyError(f"{target} not found in any subtype.")
        return "name", target
