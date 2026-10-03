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

# ---------- TREASURE HUNT CONFIG ----------
ROUND_DURATION = 30
BASE_POINTS = 100
HINT_COST = 30
FREEZE_DURATION = 5
STREAK_BONUS = 50
STREAK_THRESHOLD = 3

# ---------- MAFIA CONFIG ----------
MAFIA_ROLE_REVEAL_TIME = 6
MAFIA_NIGHT_TIME = 30
MAFIA_DAWN_TIME = 8
MAFIA_DISCUSSION_TIME = 60
MAFIA_VOTING_TIME = 30

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


# ==================== MODELS ====================
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


# ==================== ROOM CREATION ====================
@app.get("/")
def read_root():
    return {"message": "puArcade backend is running! 🎮"}

@app.post("/create-room")
def create_room(request: CreateRoomRequest):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    rooms[code] = {
        "game_type": request.game_type,
        "players": [],
        "connections": {},
        "host": request.host_name,
        "started": False,
        # Treasure Hunt state
        "progress": {},
        "current_clue_index": 0,
        "round_active": False,
        "round_winner": None,
        "answered_this_round": [],
        "round_started_at": 0,
        "round_task": None,
        "active_questions": [],
        # Mafia state
        "mafia_state": None,   # filled in when game starts
    }
    print(f"🏠 Room created: {code} | Host: {request.host_name} | Game: {request.game_type}")
    return {"room_code": code}


# ==================== UTILS ====================
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

async def send_to(room_code: str, player_name: str, message: dict):
    room = rooms.get(room_code)
    if not room: return
    ws = room["connections"].get(player_name)
    if not ws: return
    try:
        await ws.send_json(message)
    except Exception:
        pass

async def broadcast_players(room_code: str):
    room = rooms[room_code]
    await broadcast(room_code, {"type": "players", "players": room["players"]})

async def broadcast_scores(room_code: str):
    if room_code not in rooms: return
    room = rooms[room_code]
    scores = {
        name: {"score": d.get("score", 0), "streak": d.get("streak", 0)}
        for name, d in room["progress"].items()
    }
    await broadcast(room_code, {"type": "scores", "scores": scores})


# ==================== TREASURE HUNT LOGIC ====================
async def start_round(room_code: str):
    room = rooms.get(room_code)
    if not room: return

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
    room["round_task"] = asyncio.create_task(th_round_timeout(room_code, idx))

async def th_round_timeout(room_code: str, expected_idx: int):
    await asyncio.sleep(ROUND_DURATION)
    room = rooms.get(room_code)
    if not room: return
    if room["current_clue_index"] != expected_idx: return
    if room["round_winner"] is not None: return

    room["round_active"] = False
    correct = room["active_questions"][expected_idx]["answers"][0]
    for p in room["progress"]:
        room["progress"][p]["streak"] = 0
    await broadcast(room_code, {"type": "round_timeout", "answer": correct})
    await broadcast_scores(room_code)
    room["current_clue_index"] += 1
    await asyncio.sleep(3)
    await start_round(room_code)

async def th_advance_after_win(room_code, winner, points, answer, streak, streak_bonus):
    room = rooms.get(room_code)
    if not room: return
    await broadcast(room_code, {
        "type": "round_winner",
        "player": winner, "points": points, "answer": answer,
        "streak": streak, "streak_bonus": streak_bonus,
    })
    await broadcast_scores(room_code)
    room["current_clue_index"] += 1
    await asyncio.sleep(3)
    await start_round(room_code)

async def start_treasure_hunt(room_code: str):
    room = rooms.get(room_code)
    if not room: return
    if not questions_store:
        await broadcast(room_code, {"type": "error", "message": "No questions available"})
        return
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


# ==================== MAFIA LOGIC ====================
def assign_mafia_roles(players):
    """Assigns roles based on player count. Returns dict {player_name: role}."""
    n = len(players)
    names = [p["name"] for p in players]
    random.shuffle(names)

    # Role distribution based on count
    if n <= 4:
        saboteurs = 1
        investigators = 1
    elif n <= 7:
        saboteurs = 2
        investigators = 1
    elif n <= 10:
        saboteurs = 2
        investigators = 1
    else:
        saboteurs = 3
        investigators = 2

    roles = {}
    idx = 0
    for _ in range(saboteurs):
        roles[names[idx]] = "saboteur"
        idx += 1
    for _ in range(investigators):
        roles[names[idx]] = "investigator"
        idx += 1
    for name in names[idx:]:
        roles[name] = "student"

    return roles


async def start_mafia(room_code: str):
    room = rooms.get(room_code)
    if not room: return
    if len(room["players"]) < 4:
        await broadcast(room_code, {"type": "error", "message": "Need at least 4 players for Mafia"})
        return

    roles = assign_mafia_roles(room["players"])
    room["started"] = True
    room["mafia_state"] = {
        "phase": "role_reveal",
        "round": 1,
        "roles": roles,
        "alive": [p["name"] for p in room["players"]],
        "eliminated": [],          # list of {name, role, round, by}
        "night_actions": {},       # {player: action_data}
        "votes": {},               # {voter: target}
        "night_target": None,      # who the saboteurs chose
        "investigation_result": None,
        "phase_task": None,
        "last_eliminated": None,
    }

    # Send roles privately
    await broadcast(room_code, {"type": "mafia_game_started"})
    await asyncio.sleep(0.5)

    for p in room["players"]:
        role = roles[p["name"]]
        teammates = [n for n, r in roles.items() if r == role and n != p["name"]] if role == "saboteur" else []
        await send_to(room_code, p["name"], {
            "type": "your_role",
            "role": role,
            "teammates": teammates,
            "alive": room["mafia_state"]["alive"],
        })

    # Begin role reveal phase
    await broadcast(room_code, {
        "type": "mafia_phase",
        "phase": "role_reveal",
        "duration": MAFIA_ROLE_REVEAL_TIME,
        "round": 1,
    })
    room["mafia_state"]["phase_task"] = asyncio.create_task(
        mafia_phase_timer(room_code, "role_reveal", MAFIA_ROLE_REVEAL_TIME)
    )


async def mafia_phase_timer(room_code: str, expected_phase: str, duration: int):
    """Generic phase timer. Advances when time is up or phase changes."""
    await asyncio.sleep(duration)
    room = rooms.get(room_code)
    if not room or not room["mafia_state"]: return
    if room["mafia_state"]["phase"] != expected_phase: return
    await advance_mafia_phase(room_code)


async def advance_mafia_phase(room_code: str):
    """Move to the next phase in the Mafia game loop."""
    room = rooms.get(room_code)
    if not room or not room["mafia_state"]: return
    state = room["mafia_state"]

    # Cancel previous timer
    if state.get("phase_task"):
        state["phase_task"].cancel()
        state["phase_task"] = None

    current = state["phase"]

    if current == "role_reveal":
        # → Night
        state["phase"] = "night"
        state["night_actions"] = {}
        state["night_target"] = None
        state["investigation_result"] = None

        # Send night action prompts per role
        for name in state["alive"]:
            role = state["roles"][name]
            if role == "saboteur":
                targets = [n for n in state["alive"] if state["roles"][n] != "saboteur"]
                await send_to(room_code, name, {
                    "type": "mafia_prompt",
                    "phase": "night",
                    "role": "saboteur",
                    "targets": targets,
                })
            elif role == "investigator":
                targets = [n for n in state["alive"] if n != name]
                await send_to(room_code, name, {
                    "type": "mafia_prompt",
                    "phase": "night",
                    "role": "investigator",
                    "targets": targets,
                })
            else:
                await send_to(room_code, name, {
                    "type": "mafia_prompt",
                    "phase": "night",
                    "role": "student",
                })

        await broadcast(room_code, {
            "type": "mafia_phase",
            "phase": "night",
            "duration": MAFIA_NIGHT_TIME,
            "round": state["round"],
        })
        state["phase_task"] = asyncio.create_task(
            mafia_phase_timer(room_code, "night", MAFIA_NIGHT_TIME)
        )

    elif current == "night":
        # Resolve night → Dawn
        # Saboteur consensus: most-voted target (ties broken randomly)
        target_votes = {}
        investigation = None
        for actor, action in state["night_actions"].items():
            if action["type"] == "kill":
                target_votes[action["target"]] = target_votes.get(action["target"], 0) + 1
            elif action["type"] == "investigate":
                investigation = {"by": actor, "target": action["target"]}

        state["night_target"] = None
        if target_votes:
            max_votes = max(target_votes.values())
            top = [t for t, v in target_votes.items() if v == max_votes]
            state["night_target"] = random.choice(top)

        # Send investigation result privately
        if investigation:
            target_role = state["roles"][investigation["target"]]
            is_sus = target_role == "saboteur"
            await send_to(room_code, investigation["by"], {
                "type": "investigation_result",
                "target": investigation["target"],
                "is_saboteur": is_sus,
            })

        # Eliminate target if any
        killed = None
        if state["night_target"] and state["night_target"] in state["alive"]:
            killed = state["night_target"]
            state["alive"].remove(killed)
            state["eliminated"].append({
                "name": killed,
                "role": state["roles"][killed],
                "round": state["round"],
                "by": "saboteur",
            })
            state["last_eliminated"] = killed
        else:
            state["last_eliminated"] = None

        state["phase"] = "dawn"
        await broadcast(room_code, {
            "type": "mafia_dawn",
            "killed": killed,
            "killed_role": state["roles"][killed] if killed else None,
            "alive": state["alive"],
            "eliminated": state["eliminated"],
        })

        # Check win condition
        if check_mafia_win(room_code):
            return

        await broadcast(room_code, {
            "type": "mafia_phase",
            "phase": "dawn",
            "duration": MAFIA_DAWN_TIME,
            "round": state["round"],
        })
        state["phase_task"] = asyncio.create_task(
            mafia_phase_timer(room_code, "dawn", MAFIA_DAWN_TIME)
        )

    elif current == "dawn":
        # → Discussion
        state["phase"] = "discussion"
        state["votes"] = {}
        await broadcast(room_code, {
            "type": "mafia_phase",
            "phase": "discussion",
            "duration": MAFIA_DISCUSSION_TIME,
            "round": state["round"],
            "alive": state["alive"],
        })
        state["phase_task"] = asyncio.create_task(
            mafia_phase_timer(room_code, "discussion", MAFIA_DISCUSSION_TIME)
        )

    elif current == "discussion":
        # → Voting
        state["phase"] = "voting"
        state["votes"] = {}
        await broadcast(room_code, {
            "type": "mafia_phase",
            "phase": "voting",
            "duration": MAFIA_VOTING_TIME,
            "round": state["round"],
            "alive": state["alive"],
        })
        state["phase_task"] = asyncio.create_task(
            mafia_phase_timer(room_code, "voting", MAFIA_VOTING_TIME)
        )

    elif current == "voting":
        # Resolve vote
        vote_counts = {}
        for voter, target in state["votes"].items():
            if voter in state["alive"] and target in state["alive"]:
                vote_counts[target] = vote_counts.get(target, 0) + 1

        eliminated_by_vote = None
        if vote_counts:
            max_v = max(vote_counts.values())
            top = [t for t, v in vote_counts.items() if v == max_v]
            if len(top) == 1:
                eliminated_by_vote = top[0]
            else:
                # Tie → no elimination (or random pick — choose no elimination for fairness)
                eliminated_by_vote = None

        if eliminated_by_vote and eliminated_by_vote in state["alive"]:
            state["alive"].remove(eliminated_by_vote)
            state["eliminated"].append({
                "name": eliminated_by_vote,
                "role": state["roles"][eliminated_by_vote],
                "round": state["round"],
                "by": "vote",
            })

        await broadcast(room_code, {
            "type": "mafia_vote_result",
            "eliminated": eliminated_by_vote,
            "eliminated_role": state["roles"][eliminated_by_vote] if eliminated_by_vote else None,
            "vote_counts": vote_counts,
            "alive": state["alive"],
            "eliminated_all": state["eliminated"],
        })

        # Check win condition
        if check_mafia_win(room_code):
            return

        # → Next round's Night
        state["round"] += 1
        state["phase"] = "night"
        state["night_actions"] = {}
        state["night_target"] = None
        state["investigation_result"] = None

        for name in state["alive"]:
            role = state["roles"][name]
            if role == "saboteur":
                targets = [n for n in state["alive"] if state["roles"][n] != "saboteur"]
                await send_to(room_code, name, {
                    "type": "mafia_prompt",
                    "phase": "night",
                    "role": "saboteur",
                    "targets": targets,
                })
            elif role == "investigator":
                targets = [n for n in state["alive"] if n != name]
                await send_to(room_code, name, {
                    "type": "mafia_prompt",
                    "phase": "night",
                    "role": "investigator",
                    "targets": targets,
                })
            else:
                await send_to(room_code, name, {
                    "type": "mafia_prompt",
                    "phase": "night",
                    "role": "student",
                })

        await broadcast(room_code, {
            "type": "mafia_phase",
            "phase": "night",
            "duration": MAFIA_NIGHT_TIME,
            "round": state["round"],
        })
        state["phase_task"] = asyncio.create_task(
            mafia_phase_timer(room_code, "night", MAFIA_NIGHT_TIME)
        )


def check_mafia_win(room_code: str) -> bool:
    """Check win conditions; if game over, broadcast result and return True."""
    room = rooms.get(room_code)
    if not room or not room["mafia_state"]: return False
    state = room["mafia_state"]

    saboteurs_alive = [n for n in state["alive"] if state["roles"][n] == "saboteur"]
    students_alive = [n for n in state["alive"] if state["roles"][n] != "saboteur"]

    winner = None
    if not saboteurs_alive:
        winner = "students"
    elif len(saboteurs_alive) >= len(students_alive):
        winner = "saboteurs"

    if winner:
        state["phase"] = "game_over"
        if state.get("phase_task"):
            state["phase_task"].cancel()
            state["phase_task"] = None

        # Send the full role reveal at game over
        asyncio.create_task(broadcast(room_code, {
            "type": "mafia_game_over",
            "winner": winner,
            "roles": state["roles"],
            "eliminated": state["eliminated"],
            "alive": state["alive"],
        }))
        return True
    return False


# ==================== WEBSOCKET ====================
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
            "mafia_state": None,
        }

    room = rooms[room_code]

    existing = get_player(room, player_name)
    if existing:
        existing["avatar"] = avatar
    else:
        room["players"].append({"name": player_name, "avatar": avatar})

    room["connections"][player_name] = websocket
    if player_name not in room["progress"]:
        room["progress"][player_name] = {
            "score": 0, "frozen_until": 0,
            "hint_used": False, "freeze_used": False, "mystery_used": False,
            "hint_letter": None, "streak": 0,
        }

    await broadcast_players(room_code)
    await broadcast_scores(room_code)

    # Late join: resync state
    if room["game_type"] == "Mafia" and room.get("mafia_state"):
        state = room["mafia_state"]
        # Send role to late joiner (if they're in the game)
        if player_name in state["roles"]:
            role = state["roles"][player_name]
            teammates = [n for n, r in state["roles"].items() if r == role and n != player_name] if role == "saboteur" else []
            await send_to(room_code, player_name, {
                "type": "your_role",
                "role": role,
                "teammates": teammates,
                "alive": state["alive"],
            })
        await send_to(room_code, player_name, {
            "type": "mafia_phase",
            "phase": state["phase"],
            "duration": 5,
            "round": state["round"],
            "alive": state["alive"],
        })
    elif room["game_type"] == "Treasure Hunt" and room["started"] and room["round_active"]:
        idx = room["current_clue_index"]
        if idx < len(room["active_questions"]):
            elapsed = datetime.now().timestamp() - room["round_started_at"]
            remaining = max(0, ROUND_DURATION - int(elapsed))
            await send_to(room_code, player_name, {
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

            # ============ COMMON ============
            if msg_type == "start_game":
                if player_name != room["host"]: continue
                if room["game_type"] == "Mafia":
                    await start_mafia(room_code)
                else:
                    await start_treasure_hunt(room_code)

            elif msg_type == "reaction":
                await broadcast(room_code, {
                    "type": "reaction",
                    "emoji": data.get("emoji", "😂"),
                    "player": player_name,
                })

            # ============ TREASURE HUNT ============
            elif msg_type == "submit_answer" and room["game_type"] == "Treasure Hunt":
                if not room["round_active"]:
                    await send_to(room_code, player_name, {"type": "wrong", "reason": "round_not_active"})
                    continue
                p = room["progress"].get(player_name)
                if p and p["frozen_until"] > datetime.now().timestamp():
                    await send_to(room_code, player_name, {"type": "wrong", "reason": "frozen"})
                    continue
                if room["round_winner"] is not None:
                    await send_to(room_code, player_name, {"type": "wrong", "reason": "already_won"})
                    continue
                if player_name in room["answered_this_round"]:
                    await send_to(room_code, player_name, {"type": "wrong", "reason": "already_answered"})
                    continue

                answer = data.get("answer", "").strip().lower()
                idx = room["current_clue_index"]
                correct_answers = room["active_questions"][idx]["answers"]

                if answer in correct_answers:
                    elapsed = datetime.now().timestamp() - room["round_started_at"]
                    time_bonus = max(0, int((ROUND_DURATION - elapsed) * 3))
                    base_win_points = BASE_POINTS + time_bonus
                    p["streak"] = p.get("streak", 0) + 1
                    streak_bonus = STREAK_BONUS if p["streak"] >= STREAK_THRESHOLD else 0
                    total_points = base_win_points + streak_bonus
                    p["score"] += total_points

                    for other_name, other_p in room["progress"].items():
                        if other_name != player_name:
                            other_p["streak"] = 0

                    room["round_winner"] = player_name
                    room["round_active"] = False
                    if room["round_task"]:
                        room["round_task"].cancel()
                        room["round_task"] = None

                    await send_to(room_code, player_name, {
                        "type": "you_won",
                        "points": total_points,
                        "time_bonus": time_bonus,
                        "streak": p["streak"],
                        "streak_bonus": streak_bonus,
                    })
                    asyncio.create_task(th_advance_after_win(
                        room_code, player_name, total_points, correct_answers[0],
                        p["streak"], streak_bonus
                    ))
                else:
                    room["answered_this_round"].append(player_name)
                    await send_to(room_code, player_name, {"type": "wrong", "reason": "bad_answer"})

            elif msg_type == "use_hint" and room["game_type"] == "Treasure Hunt":
                p = room["progress"].get(player_name)
                if not p or p["hint_used"]: continue
                if not room["round_active"]: continue
                idx = room["current_clue_index"]
                if idx >= len(room["active_questions"]): continue
                first_letter = room["active_questions"][idx]["answers"][0][0].upper()
                p["hint_used"] = True
                p["hint_letter"] = first_letter
                p["score"] = max(0, p["score"] - HINT_COST)
                await send_to(room_code, player_name, {"type": "hint_revealed", "letter": first_letter, "cost": HINT_COST})
                await broadcast_scores(room_code)

            elif msg_type == "use_freeze" and room["game_type"] == "Treasure Hunt":
                target = data.get("target")
                p = room["progress"].get(player_name)
                if not p or p["freeze_used"]: continue
                if not room["round_active"]: continue
                if not target or target not in room["progress"]: continue
                if target == player_name: continue
                p["freeze_used"] = True
                room["progress"][target]["frozen_until"] = datetime.now().timestamp() + FREEZE_DURATION
                await broadcast(room_code, {
                    "type": "player_frozen", "target": target, "by": player_name, "duration": FREEZE_DURATION,
                })

            elif msg_type == "use_mystery" and room["game_type"] == "Treasure Hunt":
                p = room["progress"].get(player_name)
                if not p or p["mystery_used"]: continue
                if not room["round_active"]: continue
                p["mystery_used"] = True
                if random.random() < 0.5:
                    p["score"] += 200
                    result = {"outcome": "win", "points": 200}
                else:
                    p["score"] = max(0, p["score"] - 50)
                    result = {"outcome": "lose", "points": -50}
                await send_to(room_code, player_name, {"type": "mystery_result", **result})
                await broadcast_scores(room_code)

            # ============ MAFIA ============
            elif msg_type == "mafia_night_action" and room["game_type"] == "Mafia":
                state = room.get("mafia_state")
                if not state or state["phase"] != "night": continue
                if player_name not in state["alive"]: continue

                role = state["roles"].get(player_name)
                target = data.get("target")
                if not target or target not in state["alive"]: continue

                if role == "saboteur" and state["roles"][target] != "saboteur":
                    state["night_actions"][player_name] = {"type": "kill", "target": target}
                    await send_to(room_code, player_name, {"type": "night_action_ack", "action": "kill"})
                elif role == "investigator" and target != player_name:
                    state["night_actions"][player_name] = {"type": "investigate", "target": target}
                    await send_to(room_code, player_name, {"type": "night_action_ack", "action": "investigate"})

            elif msg_type == "mafia_chat" and room["game_type"] == "Mafia":
                state = room.get("mafia_state")
                if not state: continue
                # Only alive players during discussion / voting can chat
                if player_name not in state["alive"]: continue
                if state["phase"] not in ("discussion", "voting"): continue
                text = (data.get("text") or "").strip()[:200]
                if not text: continue
                await broadcast(room_code, {
                    "type": "mafia_chat",
                    "player": player_name,
                    "text": text,
                })

            elif msg_type == "mafia_vote" and room["game_type"] == "Mafia":
                state = room.get("mafia_state")
                if not state or state["phase"] != "voting": continue
                if player_name not in state["alive"]: continue
                target = data.get("target")
                if not target or target not in state["alive"]: continue
                if target == player_name: continue
                state["votes"][player_name] = target
                await broadcast(room_code, {
                    "type": "mafia_vote_cast",
                    "voter": player_name,
                    "target": target,
                })

            elif msg_type == "mafia_skip_vote" and room["game_type"] == "Mafia":
                state = room.get("mafia_state")
                if not state or state["phase"] != "voting": continue
                if player_name not in state["alive"]: continue
                state["votes"][player_name] = "__skip__"
                await broadcast(room_code, {
                    "type": "mafia_vote_cast",
                    "voter": player_name,
                    "target": "__skip__",
                })

    except WebSocketDisconnect:
        print(f"🔌 {player_name} disconnected")
        room = rooms.get(room_code)
        if room:
            room["connections"].pop(player_name, None)
            await broadcast_players(room_code)