from sqlalchemy import Column, String, Integer, JSON, Boolean, ForeignKey
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    session_version = Column(Integer, default=0, nullable=False)


class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True)
    player1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    player2_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    player1_name = Column(String, nullable=False)
    player2_name = Column(String, nullable=True)
    player1_hand = Column(JSON, default=list)
    player2_hand = Column(JSON, default=list)
    stock = Column(JSON, default=list)
    discard_pile = Column(JSON, default=list)
    current_turn = Column(String, nullable=True)
    phase = Column(String, default="waiting")
    player1_score = Column(Integer, default=0)
    player2_score = Column(Integer, default=0)
    knocked_by = Column(String, nullable=True)
    drawn_this_turn = Column(Boolean, default=False)
    last_result = Column(JSON, nullable=True)
