# Yu-Gi-Oh Custom Deck Drafter
Python app built ontop of PyQt for drafting custom decks with a custom rulset.

# Usage
1. Download the latest launcher from 'Releases`
2. Load the application. It will generate some folders on the first start for caching and autosave purposes.
3. Select 40 packs for the drafting stage. 
    1. Generally recommend that the card sets have more than 10 different cards within them. Otherwise the drafting process will occassionaly stop working as it will cause issues with the drafting ruleset.
    2. There are several options for this. Either filter the sets by right clicking the dropdown menu and pressing filter or randomising them by right clicking and selecting one of the randomisation options.
    3. If you have other people drafting at the same time you can also copy the selected packs and copy paste the set-list to them so they can paste it into their own drafter.
4. Press start and type in the desired deck name. This will launch the drafting dialog afterwards.
5. Press start to begin the drafting process. This will load and open the first booster pack beginning the drafting process. The drafting process goes as follows:
    1. You draft ~20 cards out of 10 boost packs. Usually 2 per pack unless overdrafted. *Some will allow you to pick more depending if the have relevant associated cards or summoning material, but will always go down to the curent drafting stage multiplied by 10 in the main deck*
    2. You discard down to 12 cards so that you have 10 * discard stage in the main deck and 2 * discard stage in the side deck. *Extra Deck Cards are not counted.*
    3. **Rinse and repeat until you have opened 40 packs and have 40 cards in your main deck, plus 8 more in the side deck.

6. At the end of the drafting process the application saves the deck in the default folder and a folder of your choice or the default "YGO Omega" imports folder in the **.ydk** format

## Notes
- Some cards will have dropdown menus available for adding assocciated cards to the selection, which will overdraw you depending on the selection.
- Most extra deck cards should have these menus available or a search function for finding relevant summoning material to be added.
- A card is picked if its highlighted in a red outline or if in the discard stage its also crossed out.

# API
This is the api that get used for retrieving set/card information/art:
[YGOPRODECK](https://ygoprodeck.com/api-guide/)

# License
The literal and graphical information presented in this application about Yu-Gi-Oh!, including card images,booster pack art and card text/information, is copyright 4K Media Inc, a subsidiary of Konami Digital Entertainment, Inc. This application is not produced by, endorsed by, supported by, or affiliated with 4k Media or Konami Digital Entertainment.

MIT. For everything else check `LICENSE` file for more info.
