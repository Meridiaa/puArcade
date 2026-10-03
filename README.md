# 🎮 puArcade

A real-time multiplayer campus arcade — where your university becomes the game board!

🔗 **[Live Demo](https://puarcade-frontend.onrender.com)** ← replace with your URL

## ✨ Features

- 🗺️ **Campus Treasure Hunt** — Race against friends to solve riddles. First correct answer wins.
- ⚡ **Power-ups** — Hint (reveals first letter), Freeze (locks a player for 5s), Mystery Box (gamble for points)
- 💬 **Live reactions** — Emoji reactions float across everyone's screen in real-time
- ⏱ **Timed rounds** — 30-second countdown with speed bonuses
- 🏆 **Live scoreboard** — Updates instantly for all players, with medals at the end
- 🔐 **Admin panel** — Owner-only question manager (password protected)
- 🎨 **Kawaii UI** — Pastel gradients, floating emojis, cursor glow, confetti

## 🧰 Tech Stack

**Frontend**
- React + Vite
- CSS3 animations
- WebSocket client

**Backend**
- Python + FastAPI
- WebSocket server (via `uvicorn[standard]`)
- In-memory room/state management
- JSON-based question persistence

**Deployment**
- Frontend: Render Static Site
- Backend: Render Web Service

## 🚀 Run Locally

### 1. Clone the repo
\`\`\`bash
git clone https://github.com/Meridiaa/puArcade.git
cd puArcade
\`\`\`

### 2. Setup backend
\`\`\`bash
cd backend
python -m venv venv

# Activate (Windows)
.\venv\Scripts\Activate.ps1
# Activate (Mac/Linux)
source venv/bin/activate

pip install -r requirements.txt
python -m uvicorn main:app --reload
\`\`\`
Backend runs at `http://127.0.0.1:8000`

### 3. Setup frontend
\`\`\`bash
cd frontend
npm install
npm run dev
\`\`\`
Frontend runs at `http://localhost:5173`

## 🔐 Admin Access

Add questions to the game pool by visiting:
\`\`\`
http://localhost:5173/#admin
\`\`\`

Default password is set via the `ADMIN_PASSWORD` environment variable. Change it in `backend/main.py` for local use.

## 🎮 How to Play

1. One player **Hosts a Game** and shares the 6-digit room code
2. Friends **Join a Game** with that code
3. Host clicks **Start Game**
4. Everyone sees the same clue and races to type the correct answer
5. Fastest player earns the points (speed bonus included!)
6. Use power-ups strategically — they're once-per-game
7. After all clues, final scoreboard shows the winner 🏆

## 📌 Notes

- Backend runs on Render's free tier — first request after inactivity may take 30-60 seconds to wake up
- Game state is held in memory; restarting the backend clears active rooms
- Questions persist via `questions.json` in the backend folder

## 👤 Author

**Prachi** — [GitHub](https://github.com/Meridiaa)

---

*Built from scratch with zero prior coding experience. If you liked it, drop a ⭐!*