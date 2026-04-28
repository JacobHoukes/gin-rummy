import os
import uuid
from dotenv import load_dotenv

from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Game, User
from schemas import CreateGame, JoinGame, DrawCard, DiscardCard, KnockAction, GameState
from game import build_deck, shuffle_deck, deal, is_valid_meld, hand_deadwood, is_gin
from auth import hash_password, verify_password, create_session, get_current_user_id, SESSION_COOKIE

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Helpers ──

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


# ── Auth Routes ──

@app.get("/")
def root(request: Request):
    """This endpoint redirects logged-in users to the game board and everyone else to the login page."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            from auth import decode_session
            decode_session(token)
            return RedirectResponse("/board", status_code=302)
        except Exception:
            pass
    return RedirectResponse("/login", status_code=302)


@app.get("/login")
def login_page(request: Request, error: str = None):
    """This endpoint serves the login and registration page."""
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
def login(request: Request, username: str = Form(), password: str = Form(), db: Session = Depends(get_db)):
    """This endpoint validates login credentials and sets a session cookie if correct."""
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password"})
    response = RedirectResponse("/board", status_code=302)
    response.set_cookie(SESSION_COOKIE, create_session(user.id), httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return response


@app.post("/register")
def register(request: Request, username: str = Form(), password: str = Form(), db: Session = Depends(get_db)):
    """This endpoint creates a new user account if the username is on the allowed list, and logs them in immediately."""
    allowed = [u.strip().lower() for u in os.getenv("ALLOWED_USERNAMES", "").split(",")]
    if username.lower() not in allowed:
        return templates.TemplateResponse(request, "login.html", {
            "error": "registration_closed"
        })
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse(request, "login.html", {"error": "taken"})
    if len(password) < 6:
        return templates.TemplateResponse(request, "login.html", {"error": "password_too_short"})
    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    response = RedirectResponse("/board", status_code=302)
    response.set_cookie(SESSION_COOKIE, create_session(user.id), httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return response


@app.get("/logout")
def logout():
    """This endpoint clears the session cookie and redirects to the login page."""
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/board")
def board(request: Request, db: Session = Depends(get_db)):
    """This endpoint serves the game board — only accessible to logged-in users."""
    user_id = get_current_user_id(request)
    user = db.query(User).filter(User.id == user_id).first()
    return templates.TemplateResponse(request, "board.html", {"username": user.username})


# ── Game Routes ──

@app.post("/games")
def create_game(body: CreateGame, request: Request, db: Session = Depends(get_db)):
    """This endpoint creates a new game for the logged-in user and returns the game ID and initial state."""
    user_id = get_current_user_id(request)
    deck = shuffle_deck(build_deck())
    p1_hand, p2_hand, stock = deal(deck)
    discard_pile = [stock.pop()]
    game = Game(
        id=str(uuid.uuid4())[:6],
        player1_id=user_id,
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
def join_game(game_id: str, body: JoinGame, request: Request, db: Session = Depends(get_db)):
    """This endpoint allows a logged-in user to join a waiting game using the game code."""
    user_id = get_current_user_id(request)
    game = get_game_or_404(game_id, db)
    if game.phase != "waiting":
        raise HTTPException(status_code=400, detail="Game already started")
    if game.player1_id == user_id:
        raise HTTPException(status_code=400, detail="You cannot join your own game")
    game.player2_id = user_id
    game.player2_name = body.player2_name
    game.phase = "playing"
    game.current_turn = "player1"
    db.commit()
    db.refresh(game)
    return {"state": build_game_state(game, "player2")}


@app.get("/games/{game_id}/state")
def get_state(game_id: str, player: str, request: Request, db: Session = Depends(get_db)):
    """This endpoint returns the current game state for the logged-in player."""
    get_current_user_id(request)
    game = get_game_or_404(game_id, db)
    return {"state": build_game_state(game, player)}


@app.post("/games/{game_id}/draw")
def draw_card(game_id: str, body: DrawCard, request: Request, db: Session = Depends(get_db)):
    """This endpoint handles a logged-in player drawing a card from either the stock or discard pile."""
    get_current_user_id(request)
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
def discard_card(game_id: str, body: DiscardCard, request: Request, db: Session = Depends(get_db)):
    """This endpoint handles a logged-in player discarding a card and passing the turn."""
    get_current_user_id(request)
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
def knock(game_id: str, body: KnockAction, request: Request, db: Session = Depends(get_db)):
    """This endpoint handles a logged-in player knocking, validates melds, and calculates the round score."""
    get_current_user_id(request)
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
