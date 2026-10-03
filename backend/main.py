from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List
from datetime import datetime
import asyncio
import random
import string
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rooms: Dict[str, dict] = {}

ROUND_DURATION = 30
BASE_POINTS = 100
HINT_COST = 30
FREEZE_DURATION = 5
STREAK_BONUS = 50
STREAK_THRESHOLD = 3
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "puarcade-admin")
QUESTIONS_FILE = "questions.json"

DEFAULT_QUESTIONS = [
    {"id": "q1", "clue": "I hold thousands of stories, but none of them are mine. Where am I? 📚", "answers": ["library", "lib"]},
    {"id": "q2", "clue": "Experiments happen here, and mysteries get solved. Where am I? 🧪", "answers": ["lab", "laboratory", "lab block"]},
    {"id": "q3", "clue": "Where victories are celebrated and games are won. Where am I? 🏆", "answers": ["ground", "sports ground", "field", "playground"]},
    {"id": "q4", "clue": "Food, friends, and laughter live here. Where am I? ☕", "answers": ["canteen", "cafeteria", "mess"]},
    {"id": "q5", "clue": "The final clue awaits where wisdom is shared with hundreds. Where am I? 🎓", "answers": ["auditorium", "auditorium hall", "hall"]},
]


def load_questions():
    if os.path.exists(QUESTIONS_FILE):
        try:
            with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load questions: {e}")
    return DEFAULT_QUESTIONS.copy()


def save_questions(qs):
    try:
        with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(qs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Could not save: {e}")


questions_store = load_questions()
print(f"📚 Loaded {len(questions_store)} questions")


class CreateRoomRequest(BaseModel):
    game_type: str
    host_name: str


class AdminLogin(BaseModel):
    password: str


class Question(BaseModel):
    clue: str
    answers: List[str]


# ==================== ADMIN ====================

@app.post("/admin/login")
def admin_login(req: AdminLogin):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Wrong password")
    return {"success": True}


@app.get("/admin/questions")
def get_questions():
    return {"questions": questions_store}


@app.post("/admin/questions")
def add_question(q: Question):
    new_q = {
        "id": f"q{int(datetime.now().timestamp() * 1000)}",
        "clue": q.clue,
        "answers": [a.strip().lower() for a in q.answers if a.strip()],
    }
    questions_store.append(new_q)
    save_questions(questions_store)
    return {"success": True, "question": new_q}


@app.put("/admin/questions/{qid}")
def update_question(qid: str, q: Question):
    for i, existing in enumerate(questions_store):
        if existing["id"] == qid:
            questions_store[i] = {
                "id": qid,
                "clue": q.clue,
                "answers": [a.strip().lower() for a in q.answers if a.strip()],
            }
            save_questions(questions_store)
            return {"success": True}
    raise HTTPException(status_code=404, detail="Question not found")


@app.delete("/admin/questions/{qid}")
def delete_question(qid: str):
    global questions_store
    questions_store = [q for q in questions_store if q["id"] != qid]
    save_questions(questions_store)
    return {"success": True}


@app.post("/admin/reset")
def reset_questions():
    global questions_store
    questions_store = DEFAULT_QUESTIONS.copy()
    save_questions(questions_store)
    return {"success": True}


# ==================== GAME ====================

@app.get("/")
def read_root():
    return {"message": "puArcade backend is running! 🎮"}


@app.post("/create-room")
def create_room(request: CreateRoomRequest):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    rooms[code] = {
        "game_type": request.game_type,
        "players": [],  # will store {name, avatar}
        "connections": {},
        "host": request.host_name,
        "started": False,
        "progress": {},
        "current_clue_index": 0,
        "round_active": False,
        "round_winner": None,
        "answered_this_round": [],
        "round_started_at": 0,
        "round_task": None,
        "active_questions": [],
    }
    print(f"🏠 Room created: {code} | Host: {request.host_name}")
    return {"room_code": code}


def get_player(room, name):
    for p in room["players"]:
        if p["name"] == name:
            return p
    return None


async def broadcast(room_code: str, message: dict):
    if room_code not in rooms:
        return
    dead = []
    for name, ws in rooms[room_code]["connections"].items():
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(name)
    for name in dead:
        rooms[room_code]["connections"].pop(name, None)


async def broadcast_players(room_code: str):
    room = rooms[room_code]
    await broadcast(room_code, {"type": "players", "players": room["players"]})


async def broadcast_scores(room_code: str):
    if room_code not in rooms:
        return
    room = rooms[room_code]
    scores = {
        name: {"score": d["score"], "streak": d.get("streak", 0)}
        for name, d in room["progress"].items()
    }
    await broadcast(room_code, {"type": "scores", "scores": scores})


async def start_round(room_code: str):
    room = rooms.get(room_code)
    if not room:
        return

    idx = room["current_clue_index"]
    qs = room["active_questions"]

    if idx >= len(qs):
        scores = {name: d["score"] for name, d in room["progress"].items()}
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner = sorted_scores[0][0] if sorted_scores else None
        await broadcast(room_code, {"type": "game_over", "scores": scores, "winner": winner})
        return

    room["round_active"] = True
    room["round_winner"] = None
    room["answered_this_round"] = []
    room["round_started_at"] = datetime.now().timestamp()

    for p in room["progress"]:
        room["progress"][p]["hint_letter"] = None

    await broadcast(room_code, {
        "type": "round_start",
        "clue": qs[idx]["clue"],
        "clue_number": idx + 1,
        "total_clues": len(qs),
        "duration": ROUND_DURATION,
    })

    if room["round_task"]:
        room["round_task"].cancel()
    room["round_task"] = asyncio.create_task(round_timeout(room_code, idx))


async def round_timeout(room_code: str, expected_idx: int):
    await asyncio.sleep(ROUND_DURATION)
    room = rooms.get(room_code)
    if not room: return
    if room["current_clue_index"] != expected_idx: return
    if room["round_winner"] is not None: return

    room["round_active"] = False
    correct = room["active_questions"][expected_idx]["answers"][0]
    # Reset everyone's streak when nobody answered
    for p in room["progress"]:
        room["progress"][p]["streak"] = 0
    await broadcast(room_code, {"type": "round_timeout", "answer": correct})
    await broadcast_scores(room_code)
    room["current_clue_index"] += 1
    await asyncio.sleep(3)
    await start_round(room_code)


async def advance_after_win(room_code: str, winner: str, points: int, answer: str, streak: int, streak_bonus: int):
    room = rooms.get(room_code)
    if not room: return
    await broadcast(room_code, {
        "type": "round_winner",
        "player": winner,
        "points": points,
        "answer": answer,
        "streak": streak,
        "streak_bonus": streak_bonus,
    })
    await broadcast_scores(room_code)
    room["current_clue_index"] += 1
    await asyncio.sleep(3)
    await start_round(room_code)


@app.websocket("/ws/{room_code}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, player_name: str, avatar: str = "👤"):
    await websocket.accept()
    print(f"🔌 {player_name} ({avatar}) connected to {room_code}")

    if room_code not in rooms:
        rooms[room_code] = {
            "game_type": "unknown", "players": [], "connections": {}, "host": None,
            "started": False, "progress": {}, "current_clue_index": 0,
            "round_active": False, "round_winner": None, "answered_this_round": [],
            "round_started_at": 0, "round_task": None, "active_questions": [],
        }

    room = rooms[room_code]

    # Add or update player
    existing = get_player(room, player_name)
    if existing:
        existing["avatar"] = avatar
    else:
        room["players"].append({"name": player_name, "avatar": avatar})

    room["connections"][player_name] = websocket

    if player_name not in room["progress"]:
        room["progress"][player_name] = {
            "score": 0,
            "frozen_until": 0,
            "hint_used": False,
            "freeze_used": False,
            "mystery_used": False,
            "hint_letter": None,
            "streak": 0,
        }

    await broadcast_players(room_code)
    await broadcast_scores(room_code)

    if room["started"] and room["round_active"]:
        idx = room["current_clue_index"]
        if idx < len(room["active_questions"]):
            elapsed = datetime.now().timestamp() - room["round_started_at"]
            remaining = max(0, ROUND_DURATION - int(elapsed))
            await websocket.send_json({
                "type": "round_start",
                "clue": room["active_questions"][idx]["clue"],
                "clue_number": idx + 1,
                "total_clues": len(room["active_questions"]),
                "duration": remaining,
            })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            room = rooms[room_code]
            print(f"📨 [{room_code}] {player_name}: {msg_type}")

            if msg_type == "start_game":
                if player_name != room["host"]: continue
                if not questions_store:
                    await websocket.send_json({"type": "error", "message": "No questions available"})
                    continue
                room["started"] = True
                room["current_clue_index"] = 0
                room["active_questions"] = [dict(q) for q in questions_store]
                random.shuffle(room["active_questions"])
                for p in room["players"]:
                    room["progress"][p["name"]] = {
                        "score": 0, "frozen_until": 0,
                        "hint_used": False, "freeze_used": False, "mystery_used": False,
                        "hint_letter": None, "streak": 0,
                    }
                await broadcast(room_code, {"type": "game_started"})
                await broadcast_scores(room_code)
                await asyncio.sleep(1)
                await start_round(room_code)

            elif msg_type == "submit_answer":
                if not room["round_active"]:
                    await websocket.send_json({"type": "wrong", "reason": "round_not_active"})
                    continue
                p = room["progress"].get(player_name)
                if p and p["frozen_until"] > datetime.now().timestamp():
                    await websocket.send_json({"type": "wrong", "reason": "frozen"})
                    continue
                if room["round_winner"] is not None:
                    await websocket.send_json({"type": "wrong", "reason": "already_won"})
                    continue
                if player_name in room["answered_this_round"]:
                    await websocket.send_json({"type": "wrong", "reason": "already_answered"})
                    continue

                answer = data.get("answer", "").strip().lower()
                idx = room["current_clue_index"]
                correct_answers = room["active_questions"][idx]["answers"]

                if answer in correct_answers:
                    elapsed = datetime.now().timestamp() - room["round_started_at"]
                    time_bonus = max(0, int((ROUND_DURATION - elapsed) * 3))
                    base_win_points = BASE_POINTS + time_bonus

                    # Streak logic
                    p["streak"] = p.get("streak", 0) + 1
                    streak_bonus = STREAK_BONUS if p["streak"] >= STREAK_THRESHOLD else 0
                    total_points = base_win_points + streak_bonus
                    p["score"] += total_points

                    # Reset others' streaks
                    for other_name, other_p in room["progress"].items():
                        if other_name != player_name:
                            other_p["streak"] = 0

                    room["round_winner"] = player_name
                    room["round_active"] = False

                    if room["round_task"]:
                        room["round_task"].cancel()
                        room["round_task"] = None

                    await websocket.send_json({
                        "type": "you_won",
                        "points": total_points,
                        "time_bonus": time_bonus,
                        "streak": p["streak"],
                        "streak_bonus": streak_bonus,
                    })
                    asyncio.create_task(advance_after_win(
                        room_code, player_name, total_points, correct_answers[0],
                        p["streak"], streak_bonus
                    ))
                else:
                    room["answered_this_round"].append(player_name)
                    await websocket.send_json({"type": "wrong", "reason": "bad_answer"})

            elif msg_type == "use_hint":
                p = room["progress"].get(player_name)
                if not p or p["hint_used"]: continue
                if not room["round_active"]: continue
                idx = room["current_clue_index"]
                if idx >= len(room["active_questions"]): continue
                first_answer = room["active_questions"][idx]["answers"][0]
                first_letter = first_answer[0].upper()
                p["hint_used"] = True
                p["hint_letter"] = first_letter
                p["score"] = max(0, p["score"] - HINT_COST)
                await websocket.send_json({"type": "hint_revealed", "letter": first_letter, "cost": HINT_COST})
                await broadcast_scores(room_code)
                await broadcast(room_code, {
                    "type": "reaction", "emoji": "⚡",
                    "player": f"{player_name} used a hint"
                })

            elif msg_type == "use_freeze":
                target = data.get("target")
                p = room["progress"].get(player_name)
                if not p or p["freeze_used"]: continue
                if not room["round_active"]: continue
                if not target or target not in room["progress"]: continue
                if target == player_name: continue
                p["freeze_used"] = True
                room["progress"][target]["frozen_until"] = datetime.now().timestamp() + FREEZE_DURATION
                await broadcast(room_code, {
                    "type": "player_frozen",
                    "target": target, "by": player_name,
                    "duration": FREEZE_DURATION,
                })

            elif msg_type == "use_mystery":
                p = room["progress"].get(player_name)
                if not p or p["mystery_used"]: continue
                if not room["round_active"]: continue
                p["mystery_used"] = True
                roll = random.random()
                if roll < 0.5:
                    bonus = 200
                    p["score"] += bonus
                    result = {"outcome": "win", "points": bonus}
                else:
                    penalty = 50
                    p["score"] = max(0, p["score"] - penalty)
                    result = {"outcome": "lose", "points": -penalty}
                await websocket.send_json({"type": "mystery_result", **result})
                await broadcast_scores(room_code)
                await broadcast(room_code, {
                    "type": "reaction",
                    "emoji": "🎁" if result["outcome"] == "win" else "💀",
                    "player": f"{player_name} opened a mystery box"
                })

            elif msg_type == "reaction":
                await broadcast(room_code, {
                    "type": "reaction",
                    "emoji": data.get("emoji", "😂"),
                    "player": player_name,
                })

    except WebSocketDisconnect:
        print(f"🔌 {player_name} disconnected")
        room = rooms.get(room_code)
        if room:
            room["connections"].pop(player_name, None)
            room["players"] = [p for p in room["players"] if p["name"] != player_name]
            await broadcast_players(room_code)