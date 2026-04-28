from sqlalchemy import Column, String, Integer, JSON, Boolean
from database import Base


class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True)  # random game code, e.g. "abc123"
    player1_name = Column(String, nullable=False)
    player2_name = Column(String, nullable=True)  # None until someone joins
    player1_hand = Column(JSON, default=list)  # list of card strings, e.g. ["AH", "10S"]
    player2_hand = Column(JSON, default=list)
    stock = Column(JSON, default=list)  # remaining draw pile
    discard_pile = Column(JSON, default=list)  # face-up discard stack
    current_turn = Column(String, nullable=True)  # "player1" or "player2"
    phase = Column(String, default="waiting")  # waiting → playing → scoring → finished
    player1_score = Column(Integer, default=0)
    player2_score = Column(Integer, default=0)
    knocked_by = Column(String, nullable=True)  # who knocked this hand
    drawn_this_turn = Column(Boolean, default=False)  # has current player drawn yet?
