from pydantic import BaseModel
from typing import Optional


class CreateGame(BaseModel):
    """This schema validates the request body when a new game is created — only the host's name is required."""
    player1_name: str


class JoinGame(BaseModel):
    """This schema validates the request body when a second player joins an existing game using the game code."""
    player2_name: str


class DrawCard(BaseModel):
    """This schema validates the request body when a player draws a card, specifying whether they draw from the stock or discard pile."""
    player: str  # "player1" or "player2"
    source: str  # "stock" or "discard"


class DiscardCard(BaseModel):
    """This schema validates the request body when a player discards a card from their hand."""
    player: str
    card: str  # e.g. "10H"


class KnockAction(BaseModel):
    """This schema validates the request body when a player knocks, including the melds they are declaring and any layoffs on the opponent's melds."""
    player: str
    melds: list[list[str]]  # e.g. [["AH", "AS", "AD"], ["3C", "4C", "5C"]]
    layoffs: list[str]  # cards the opponent lays off onto knocker's melds


class GameState(BaseModel):
    """This schema defines the shape of the game state returned to the frontend after every action."""
    game_id: str
    player1_name: str
    player2_name: Optional[str]
    current_turn: Optional[str]
    phase: str
    player1_score: int
    player2_score: int
    your_hand: list[str]
    discard_top: Optional[str]
    stock_count: int
    drawn_this_turn: bool
    knocked_by: Optional[str]
