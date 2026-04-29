import os
import uuid
from dotenv import load_dotenv

from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Game, User
from schemas import CreateGame, JoinGame, DrawCard, DiscardCard, KnockAction, GameState
from game import build_deck, shuffle_deck, deal, is_valid_meld, hand_deadwood, is_gin, find_best_melds, sort_hand
from auth import hash_password, verify_password, create_session, get_current_user_id, get_session_payload, \
    SESSION_COOKIE

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

    last_result = None
    if game.last_result:
        result = dict(game.last_result)
        if result.get("knocker") != player:
            last_result = {
                **result,
                "knocker_sets": result.get("opponent_sets", []),
                "knocker_deadwood": result.get("opponent_deadwood", []),
                "knocker_deadwood_value": result.get("opponent_deadwood_value", 0),
                "opponent_sets": result.get("knocker_sets", []),
                "opponent_deadwood": result.get("knocker_deadwood", []),
                "opponent_deadwood_value": result.get("knocker_deadwood_value", 0),
            }
        else:
            last_result = result

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
        last_result=last_result,
    )


def get_allowed_usernames():
    """This function returns the list of allowed usernames from the environment variable."""
    return [u.strip().lower() for u in os.getenv("ALLOWED_USERNAMES", "").split(",")]


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
    response.set_cookie(SESSION_COOKIE, create_session(user.id, user.session_version), httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return response


@app.post("/register")
def register(request: Request, username: str = Form(), password: str = Form(), db: Session = Depends(get_db)):
    """This endpoint creates a new user account if the username is on the allowed list."""
    if username.lower() not in get_allowed_usernames():
        return templates.TemplateResponse(request, "login.html", {"error": "registration_closed"})
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse(request, "login.html", {"error": "taken"})
    if len(password) < 6:
        return templates.TemplateResponse(request, "login.html", {"error": "password_too_short"})
    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    response = RedirectResponse("/board", status_code=302)
    response.set_cookie(SESSION_COOKIE, create_session(user.id, user.session_version), httponly=True, samesite="lax",
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
    payload = get_session_payload(request)
    user = db.query(User).filter(User.id == payload["id"]).first()
    if not user or user.session_version != payload["v"]:
        response = RedirectResponse("/login", status_code=302)
        response.delete_cookie(SESSION_COOKIE)
        return response
    return templates.TemplateResponse(request, "board.html", {"username": user.username})


# ── Account Routes ──

@app.get("/account")
def account_page(request: Request, db: Session = Depends(get_db)):
    """This endpoint serves the account settings page."""
    payload = get_session_payload(request)
    user = db.query(User).filter(User.id == payload["id"]).first()
    if not user or user.session_version != payload["v"]:
        response = RedirectResponse("/login", status_code=302)
        response.delete_cookie(SESSION_COOKIE)
        return response
    return templates.TemplateResponse(request, "account.html", {"username": user.username})


@app.post("/account/username")
def change_username(request: Request, new_username: str = Form(), db: Session = Depends(get_db)):
    """This endpoint updates the logged-in user's username if it is on the allowed list."""
    payload = get_session_payload(request)
    user = db.query(User).filter(User.id == payload["id"]).first()
    if not user or user.session_version != payload["v"]:
        return RedirectResponse("/login", status_code=302)
    if new_username.lower() not in get_allowed_usernames():
        return templates.TemplateResponse(request, "account.html", {
            "username": user.username,
            "username_error": "That username is not on the allowed list."
        })
    if db.query(User).filter(User.username == new_username).first():
        return templates.TemplateResponse(request, "account.html", {
            "username": user.username,
            "username_error": "That username is already taken."
        })
    user.username = new_username
    db.commit()
    return RedirectResponse("/account", status_code=302)


@app.post("/account/password")
def change_password(request: Request, current_password: str = Form(), new_password: str = Form(),
                    db: Session = Depends(get_db)):
    """This endpoint updates the logged-in user's password after verifying their current password."""
    payload = get_session_payload(request)
    user = db.query(User).filter(User.id == payload["id"]).first()
    if not user or user.session_version != payload["v"]:
        return RedirectResponse("/login", status_code=302)
    if not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse(request, "account.html", {
            "username": user.username,
            "password_error": "Current password is incorrect."
        })
    if len(new_password) < 6:
        return templates.TemplateResponse(request, "account.html", {
            "username": user.username,
            "password_error": "New password must be at least 6 characters."
        })
    user.password_hash = hash_password(new_password)
    db.commit()
    return templates.TemplateResponse(request, "account.html", {
        "username": user.username,
        "password_success": "Password updated successfully."
    })


@app.post("/account/logout-all")
def logout_all(request: Request, db: Session = Depends(get_db)):
    """This endpoint increments the session version, invalidating all existing sessions for this user."""
    payload = get_session_payload(request)
    user = db.query(User).filter(User.id == payload["id"]).first()
    if not user:
        return RedirectResponse("/login", status_code=302)
    user.session_version += 1
    db.commit()
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


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
        player1_hand=sort_hand(p1_hand),
        player2_hand=sort_hand(p2_hand),
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
        hand = sort_hand(list(hand) + [card])
        game.stock = stock
    elif body.source == "discard":
        if not game.discard_pile:
            raise HTTPException(status_code=400, detail="Discard pile is empty")
        discard = list(game.discard_pile)
        card = discard.pop()
        hand = sort_hand(list(hand) + [card])
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
    """This endpoint handles knocking — auto-detects best melds, calculates score, and stores result for both players."""
    get_current_user_id(request)
    game = get_game_or_404(game_id, db)
    if game.phase != "playing":
        raise HTTPException(status_code=400, detail="Game is not in playing phase")
    if game.current_turn != body.player:
        raise HTTPException(status_code=400, detail="Not your turn")
    if not game.drawn_this_turn:
        raise HTTPException(status_code=400, detail="You must draw before knocking")

    knocker = body.player
    opponent = "player2" if knocker == "player1" else "player1"
    knocker_hand = list(game.player1_hand if knocker == "player1" else game.player2_hand)
    opponent_hand = list(game.player2_hand if knocker == "player1" else game.player1_hand)

    best_melds, knocker_deadwood = find_best_melds(knocker_hand)

    if knocker_deadwood > 10:
        raise HTTPException(status_code=400,
                            detail=f"Your deadwood is {knocker_deadwood} — you need 10 or fewer to knock.")

    opponent_best_melds, opponent_deadwood = find_best_melds(opponent_hand)
    difference = opponent_deadwood - knocker_deadwood
    gin = knocker_deadwood == 0
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

    knocker_melded = {c for meld in best_melds for c in meld}
    knocker_deadwood_cards = [c for c in knocker_hand if c not in knocker_melded]
    opponent_melded = {c for meld in opponent_best_melds for c in meld}
    opponent_deadwood_cards = [c for c in opponent_hand if c not in opponent_melded]

    game.last_result = {
        "knocker": knocker,
        "points_scored": points,
        "gin": gin,
        "undercut": undercut,
        "winner": winner,
        "knocker_sets": best_melds,
        "knocker_deadwood": knocker_deadwood_cards,
        "knocker_deadwood_value": knocker_deadwood,
        "opponent_sets": opponent_best_melds,
        "opponent_deadwood": opponent_deadwood_cards,
        "opponent_deadwood_value": opponent_deadwood,
    }
    db.commit()
    db.refresh(game)

    return {
        "state": build_game_state(game, knocker),
        "points_scored": points,
        "gin": gin,
        "undercut": undercut,
        "winner": winner,
        "knocker_sets": best_melds,
        "knocker_deadwood": knocker_deadwood_cards,
        "opponent_sets": opponent_best_melds,
        "opponent_deadwood": opponent_deadwood_cards,
        "knocker_deadwood_value": knocker_deadwood,
        "opponent_deadwood_value": opponent_deadwood,
    }


@app.post("/games/{game_id}/new-hand")
def new_hand(game_id: str, request: Request, db: Session = Depends(get_db)):
    """This endpoint resets the cards for a new hand while preserving cumulative scores."""
    get_current_user_id(request)
    game = get_game_or_404(game_id, db)
    if game.phase not in ("scoring", "finished"):
        raise HTTPException(status_code=400, detail="Round is not over yet")
    if game.phase == "finished":
        raise HTTPException(status_code=400, detail="Game is already finished — start a new game")

    deck = shuffle_deck(build_deck())
    p1_hand, p2_hand, stock = deal(deck)
    discard_pile = [stock.pop()]

    game.player1_hand = sort_hand(p1_hand)
    game.player2_hand = sort_hand(p2_hand)
    game.stock = stock
    game.discard_pile = discard_pile
    game.current_turn = "player1"
    game.phase = "playing"
    game.knocked_by = None
    game.drawn_this_turn = False
    game.last_result = None

    db.commit()
    db.refresh(game)
    return {"state": build_game_state(game, "player1")}
