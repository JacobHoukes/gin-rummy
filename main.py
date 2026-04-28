import uuid
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Game
from schemas import CreateGame, JoinGame, DrawCard, DiscardCard, KnockAction, GameState
from game import build_deck, shuffle_deck, deal, card_value, is_valid_meld, hand_deadwood, is_gin

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_game_or_404(game_id: str, db: Session) -> Game:
    """This function fetches a game by ID from the database and raises a 404 error if it does not exist."""
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


def build_game_state(game: Game, player: str) -> GameState:
    """This function builds and returns a GameState for the requesting player, showing only their own hand."""
    hand = game.player1_hand if player == "player1" else game.player2_hand
    discard_top = game.discard_pile[-1] if game.discard_pile else None
    return GameState(
        game_id=game.id,
        player1_name=game.player1_name,
        player2_name=game.player2_name,
        current_turn=game.current_turn,
        phase=game.phase,
        player1_score=game.player1_score,
        player2_score=game.player2_score,
        your_hand=hand,
        discard_top=discard_top,
        stock_count=len(game.stock),
        drawn_this_turn=game.drawn_this_turn,
        knocked_by=game.knocked_by,
    )


@app.get("/")
def lobby(request: Request):
    """This endpoint serves the main game board HTML page via Jinja2."""
    return templates.TemplateResponse(request, "board.html")


@app.post("/games")
def create_game(body: CreateGame, db: Session = Depends(get_db)):
    """This endpoint creates a new game, deals the cards, and returns the game ID and initial state for player1."""
    deck = shuffle_deck(build_deck())
    p1_hand, p2_hand, stock = deal(deck)
    discard_pile = [stock.pop()]
    game = Game(
        id=str(uuid.uuid4())[:6],
        player1_name=body.player1_name,
        player1_hand=p1_hand,
        player2_hand=p2_hand,
        stock=stock,
        discard_pile=discard_pile,
        phase="waiting",
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return {"game_id": game.id, "state": build_game_state(game, "player1")}


@app.post("/games/{game_id}/join")
def join_game(game_id: str, body: JoinGame, db: Session = Depends(get_db)):
    """This endpoint allows player2 to join a waiting game using the game code, transitioning the game to playing phase."""
    game = get_game_or_404(game_id, db)
    if game.phase != "waiting":
        raise HTTPException(status_code=400, detail="Game already started")
    game.player2_name = body.player2_name
    game.phase = "playing"
    game.current_turn = "player1"
    db.commit()
    db.refresh(game)
    return {"state": build_game_state(game, "player2")}


@app.get("/games/{game_id}/state")
def get_state(game_id: str, player: str, db: Session = Depends(get_db)):
    """This endpoint returns the current game state for the given player — used by the frontend to poll for updates."""
    game = get_game_or_404(game_id, db)
    return {"state": build_game_state(game, player)}


@app.post("/games/{game_id}/draw")
def draw_card(game_id: str, body: DrawCard, db: Session = Depends(get_db)):
    """This endpoint handles a player drawing a card from either the stock pile or the discard pile."""
    game = get_game_or_404(game_id, db)
    if game.phase != "playing":
        raise HTTPException(status_code=400, detail="Game is not in playing phase")
    if game.current_turn != body.player:
        raise HTTPException(status_code=400, detail="Not your turn")
    if game.drawn_this_turn:
        raise HTTPException(status_code=400, detail="You already drew this turn")

    hand = game.player1_hand if body.player == "player1" else game.player2_hand

    if body.source == "stock":
        if not game.stock:
            raise HTTPException(status_code=400, detail="Stock is empty")
        stock = list(game.stock)
        card = stock.pop()
        hand = list(hand) + [card]
        game.stock = stock
    elif body.source == "discard":
        if not game.discard_pile:
            raise HTTPException(status_code=400, detail="Discard pile is empty")
        discard = list(game.discard_pile)
        card = discard.pop()
        hand = list(hand) + [card]
        game.discard_pile = discard
    else:
        raise HTTPException(status_code=400, detail="source must be 'stock' or 'discard'")

    if body.player == "player1":
        game.player1_hand = hand
    else:
        game.player2_hand = hand

    game.drawn_this_turn = True
    db.commit()
    db.refresh(game)
    return {"state": build_game_state(game, body.player)}


@app.post("/games/{game_id}/discard")
def discard_card(game_id: str, body: DiscardCard, db: Session = Depends(get_db)):
    """This endpoint handles a player discarding a card from their hand, then passes the turn to the opponent."""
    game = get_game_or_404(game_id, db)
    if game.phase != "playing":
        raise HTTPException(status_code=400, detail="Game is not in playing phase")
    if game.current_turn != body.player:
        raise HTTPException(status_code=400, detail="Not your turn")
    if not game.drawn_this_turn:
        raise HTTPException(status_code=400, detail="You must draw before discarding")

    hand = list(game.player1_hand if body.player == "player1" else game.player2_hand)

    if body.card not in hand:
        raise HTTPException(status_code=400, detail="Card not in your hand")

    hand.remove(body.card)
    game.discard_pile = list(game.discard_pile) + [body.card]

    if body.player == "player1":
        game.player1_hand = hand
        game.current_turn = "player2"
    else:
        game.player2_hand = hand
        game.current_turn = "player1"

    game.drawn_this_turn = False
    db.commit()
    db.refresh(game)
    return {"state": build_game_state(game, body.player)}


@app.post("/games/{game_id}/knock")
def knock(game_id: str, body: KnockAction, db: Session = Depends(get_db)):
    """This endpoint handles a player knocking, validates their melds, calculates scores, and determines the round winner."""
    game = get_game_or_404(game_id, db)
    if game.phase != "playing":
        raise HTTPException(status_code=400, detail="Game is not in playing phase")
    if game.current_turn != body.player:
        raise HTTPException(status_code=400, detail="Not your turn")
    if not game.drawn_this_turn:
        raise HTTPException(status_code=400, detail="You must draw before knocking")

    for meld in body.melds:
        if not is_valid_meld(meld):
            raise HTTPException(status_code=400, detail=f"Invalid meld: {meld}")

    knocker = body.player
    opponent = "player2" if knocker == "player1" else "player1"
    knocker_hand = list(game.player1_hand if knocker == "player1" else game.player2_hand)
    opponent_hand = list(game.player2_hand if knocker == "player1" else game.player1_hand)

    knocker_deadwood = hand_deadwood(knocker_hand, body.melds)
    if knocker_deadwood > 10:
        raise HTTPException(status_code=400, detail="Deadwood too high to knock")

    opponent_deadwood = hand_deadwood(opponent_hand, [])
    difference = opponent_deadwood - knocker_deadwood
    gin = is_gin(knocker_hand, body.melds)
    undercut = False

    if gin:
        points = difference + 25
        winner = knocker
    elif difference < 0:
        undercut = True
        points = abs(difference) + 25
        winner = opponent
    else:
        points = difference
        winner = knocker

    if winner == "player1":
        game.player1_score += points
    else:
        game.player2_score += points

    game.knocked_by = knocker
    game.phase = "finished" if max(game.player1_score, game.player2_score) >= 100 else "scoring"
    game.current_turn = None
    db.commit()
    db.refresh(game)
    return {
        "state": build_game_state(game, knocker),
        "points_scored": points,
        "gin": gin,
        "undercut": undercut,
        "winner": winner
    }
