from pydantic import BaseModel
from typing import Optional, Any

class CreateGame(BaseModel):
    """This schema validates the request body when a new game is created."""
    player1_name: str

class JoinGame(BaseModel):
    """This schema validates the request body when a second player joins."""
    player2_name: str

class DrawCard(BaseModel):
    """This schema validates the request body when a player draws a card."""
    player: str
    source: str

class DiscardCard(BaseModel):
    """This schema validates the request body when a player discards a card."""
    player: str
    card: str

class KnockAction(BaseModel):
    """This schema validates the request body when a player knocks."""
    player: str
    melds: list[list[str]]
    layoffs: list[str]

class GameState(BaseModel):
    """This schema defines the shape of the game state returned to the frontend."""
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
    last_result: Optional[Any]