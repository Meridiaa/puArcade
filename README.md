# 🎮 puArcade

A real-time multiplayer campus arcade with two full game modes.

🔗 **[Live Demo](https://puarcade-frontend.onrender.com)**

## 🎯 Game Modes

### 🗺️ Campus Treasure Hunt
Race against friends to solve riddles. First correct answer wins the round.
- ⚡ Power-ups: Hint, Freeze, Mystery Box
- 🔥 Streak system with bonus points
- ⏱ Timed rounds with speed bonuses

### 🕵️ Campus Mafia
Social deduction at its finest. Trust no one.
- 🎭 Secret roles (Saboteur, Investigator, Student)
- 🌙 Night actions (eliminate, investigate)
- 💬 Live discussion chat
- 🗳️ Anonymous voting with live tally
- 🏆 Win conditions: Students vs Saboteurs

## ✨ Cross-game features
- 🎭 Emoji avatar picker
- 🔊 Procedural sound effects (no files!)
- 💬 Floating emoji reactions
- 🎨 Kawaii UI with animated gradients, cursor glow, and confetti
- 🔐 Owner-only admin panel for question management

## 🧰 Tech Stack
**Frontend** — React + Vite, WebSocket client, custom CSS
**Backend** — Python + FastAPI, WebSockets via `uvicorn[standard]`, in-memory game state
**Deployment** — Render (Static Site + Web Service)

## 🚀 Run Locally

### Backend
\`\`\`bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1     # Windows
pip install -r requirements.txt
python -m uvicorn main:app --reload
\`\`\`

### Frontend (new terminal)
\`\`\`bash
cd frontend
npm install
npm run dev
\`\`\`

Visit `http://localhost:5173`.

## 🔐 Admin Access
Add your own Treasure Hunt questions at `http://localhost:5173/#admin`.
Password set via `ADMIN_PASSWORD` env var (default: `puarcade-admin`).

## 👤 Author
**Prachi** — [GitHub](https://github.com/Meridiaa)