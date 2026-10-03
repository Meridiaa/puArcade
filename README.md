# 🎮 puArcade

A real-time multiplayer campus arcade — where your university becomes the game board!

## ✨ Features
- 🗺️ **Campus Treasure Hunt** — Race to solve riddles, first to answer wins
- ⚡ **Power-ups**: Hint, Freeze, Mystery Box
- 💬 **Live reactions** — Emoji reactions float across everyone's screens
- 🔐 **Admin panel** — Owner-only question manager (password protected)
- ⏱ **Timed rounds** with speed bonuses
- 🏆 **Live scoreboard** with medals

## 🧰 Tech Stack
- **Frontend:** React + Vite + CSS
- **Backend:** Python + FastAPI + WebSockets
- **Real-time:** Native WebSocket protocol

## 🚀 Run Locally

### Backend
\`\`\`bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install fastapi "uvicorn[standard]"
python -m uvicorn main:app --reload
\`\`\`

### Frontend
\`\`\`bash
cd frontend
npm install
npm run dev
\`\`\`

## 🔐 Admin Access
- Visit `http://localhost:5173/#admin`
- Default password: `puarcade-admin` (change in `backend/main.py`)

## 👤 Author
Built by **Prachi** — [GitHub](https://github.com/Meridiaa)