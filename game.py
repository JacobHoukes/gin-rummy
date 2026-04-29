import random
from itertools import product, combinations

SUITS = ["H", "D", "C", "S"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUIT_ORDER = {"H": 0, "D": 1, "C": 2, "S": 3}


def build_deck():
    """This function builds and returns a full 52-card deck as a list of strings (e.g. 'AH', '10S')."""
    return [f"{rank}{suit}" for rank, suit in product(RANKS, SUITS)]


def shuffle_deck(deck):
    """This function shuffles the given deck in place and returns it."""
    random.shuffle(deck)
    return deck


def card_value(card):
    """This function returns the point value of a card: 1 for Ace, 10 for face cards, face value for number cards."""
    rank = card[:-1]
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 1
    return int(rank)


def card_rank_index(card):
    """This function returns the rank index (0-12) of a card for sorting and run detection."""
    return RANKS.index(card[:-1])


def card_suit(card):
    """This function returns the suit character of a card."""
    return card[-1]


def sort_hand(hand):
    """This function sorts a hand by suit then by rank index."""
    return sorted(hand, key=lambda c: (SUIT_ORDER[card_suit(c)], card_rank_index(c)))


def hand_deadwood(hand, melds):
    """This function calculates and returns the total deadwood value of a hand — the sum of card values not covered by any meld."""
    melded_cards = {card for meld in melds for card in meld}
    return sum(card_value(c) for c in hand if c not in melded_cards)


def is_valid_set(cards):
    """This function checks whether a list of cards forms a valid set: 3 or 4 cards of the same rank."""
    if len(cards) < 3 or len(cards) > 4:
        return False
    ranks = [c[:-1] for c in cards]
    return len(set(ranks)) == 1


def is_valid_run(cards):
    """This function checks whether a list of cards forms a valid run: 3 or more consecutive cards of the same suit. Aces are low only."""
    if len(cards) < 3:
        return False
    suits = [card_suit(c) for c in cards]
    if len(set(suits)) != 1:
        return False
    indices = sorted([card_rank_index(c) for c in cards])
    return indices == list(range(indices[0], indices[0] + len(indices)))


def is_valid_meld(cards):
    """This function returns True if the given list of cards forms either a valid set or a valid run."""
    return is_valid_set(cards) or is_valid_run(cards)


def find_all_melds(hand):
    """This function finds all possible valid melds (sets and runs) within a hand."""
    melds = []

    by_rank = {}
    for card in hand:
        rank = card[:-1]
        by_rank.setdefault(rank, []).append(card)

    for rank, cards in by_rank.items():
        if len(cards) >= 3:
            for size in range(3, len(cards) + 1):
                for combo in combinations(cards, size):
                    melds.append(list(combo))

    by_suit = {}
    for card in hand:
        suit = card_suit(card)
        by_suit.setdefault(suit, []).append(card)

    for suit, cards in by_suit.items():
        sorted_cards = sorted(cards, key=card_rank_index)
        for i in range(len(sorted_cards)):
            for j in range(i + 3, len(sorted_cards) + 1):
                subset = sorted_cards[i:j]
                indices = [card_rank_index(c) for c in subset]
                if indices == list(range(indices[0], indices[0] + len(indices))):
                    melds.append(subset)

    return melds


def find_best_melds(hand):
    """This function finds the optimal combination of melds that minimizes deadwood in the given hand."""
    all_melds = find_all_melds(hand)
    best_melds = []
    best_deadwood = hand_deadwood(hand, [])

    def search(remaining_cards, current_melds, available_melds):
        nonlocal best_melds, best_deadwood
        current_deadwood = sum(card_value(c) for c in remaining_cards)
        if current_deadwood < best_deadwood:
            best_deadwood = current_deadwood
            best_melds = list(current_melds)
        for i, meld in enumerate(available_melds):
            meld_set = set(meld)
            if meld_set.issubset(set(remaining_cards)):
                new_remaining = [c for c in remaining_cards if c not in meld_set]
                search(new_remaining, current_melds + [meld], available_melds[i + 1:])

    search(list(hand), [], all_melds)
    return best_melds, best_deadwood


def deal(deck):
    """This function deals 10 cards to each player from the top of the deck and returns (player1_hand, player2_hand, remaining_stock)."""
    p1 = deck[:10]
    p2 = deck[10:20]
    stock = deck[20:]
    return p1, p2, stock


def can_knock(hand, melds):
    """This function returns True if the deadwood value of the hand is 10 or fewer."""
    return hand_deadwood(hand, melds) <= 10


def is_gin(hand, melds):
    """This function returns True if the player has zero deadwood."""
    return hand_deadwood(hand, melds) == 0
