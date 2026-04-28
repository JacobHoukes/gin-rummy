import random
from itertools import product

SUITS = ["H", "D", "C", "S"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


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
    """This function checks whether a list of cards forms a valid run: 3 or more consecutive cards of the same suit."""
    if len(cards) < 3:
        return False
    suits = [c[-1] for c in cards]
    if len(set(suits)) != 1:
        return False
    rank_order = {r: i for i, r in enumerate(RANKS)}
    indices = sorted([rank_order[c[:-1]] for c in cards])
    return indices == list(range(indices[0], indices[0] + len(indices)))


def is_valid_meld(cards):
    """This function returns True if the given list of cards forms either a valid set or a valid run."""
    return is_valid_set(cards) or is_valid_run(cards)


def deal(deck):
    """This function deals 10 cards to each player from the top of the deck and returns (player1_hand, player2_hand, remaining_stock)."""
    p1 = deck[:10]
    p2 = deck[10:20]
    stock = deck[20:]
    return p1, p2, stock


def can_knock(hand, melds):
    """This function returns True if the deadwood value of the hand is 10 or fewer, meaning the player is allowed to knock."""
    return hand_deadwood(hand, melds) <= 10


def is_gin(hand, melds):
    """This function returns True if the player has zero deadwood, meaning they have Gin."""
    return hand_deadwood(hand, melds) == 0
