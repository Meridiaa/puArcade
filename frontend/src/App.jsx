import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './App.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000';

const GAMES = [
  { id: 'Treasure Hunt', emoji: '🗺️', title: 'Campus Treasure Hunt', tagline: 'Race against friends — first to answer wins!' },
  { id: 'Mafia', emoji: '🕵️', title: 'Campus Mafia', tagline: 'Trust no one. Find the saboteur.' },
];

const REACTIONS = ['😂', '🔥', '😱', '👏', '💀', '🤔', '🎉', '❤️'];
const AVATARS = ['🐱', '🐼', '🦊', '🐸', '🐧', '🦄', '🐙', '🦖', '🐝', '🐢', '🦋', '🐨'];

// 🎵 Sound effects using Web Audio API (no files needed)
function playSound(type, enabled) {
  if (!enabled) return;
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const ctx = new AudioCtx();
    const now = ctx.currentTime;

    const beep = (freq, start, duration, vol = 0.15, wave = 'sine') => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = wave;
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(vol, now + start);
      gain.gain.exponentialRampToValueAtTime(0.001, now + start + duration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + start);
      osc.stop(now + start + duration);
    };

    if (type === 'correct') {
      beep(660, 0, 0.15);
      beep(880, 0.1, 0.25);
    } else if (type === 'wrong') {
      beep(200, 0, 0.2, 0.2, 'sawtooth');
    } else if (type === 'tick') {
      beep(1200, 0, 0.05, 0.08);
    } else if (type === 'win') {
      [523, 659, 784, 1047].forEach((f, i) => beep(f, i * 0.12, 0.3, 0.15));
    } else if (type === 'join') {
      beep(880, 0, 0.1, 0.1);
      beep(1175, 0.08, 0.15, 0.1);
    } else if (type === 'start') {
      [392, 523, 659, 784].forEach((f, i) => beep(f, i * 0.08, 0.2, 0.12));
    } else if (type === 'streak') {
      [659, 784, 988, 1319].forEach((f, i) => beep(f, i * 0.07, 0.25, 0.14));
    }
  } catch (e) { /* ignore */ }
}

function App() {
  const [screen, setScreen] = useState('home');
  const [isHost, setIsHost] = useState(false);
  const [gameType, setGameType] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [avatar, setAvatar] = useState('🐱');
  const [roomCode, setRoomCode] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [players, setPlayers] = useState([]);
  const [scores, setScores] = useState({});
  const [currentClue, setCurrentClue] = useState(null);
  const [clueNumber, setClueNumber] = useState(0);
  const [totalClues, setTotalClues] = useState(0);
  const [timeLeft, setTimeLeft] = useState(0);
  const [answer, setAnswer] = useState('');
  const [feedback, setFeedback] = useState('');
  const [roundWinner, setRoundWinner] = useState(null);
  const [roundTimeout, setRoundTimeout] = useState(null);
  const [gameOver, setGameOver] = useState(null);
  const [myLastPoints, setMyLastPoints] = useState(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [cursor, setCursor] = useState({ x: -200, y: -200 });
  const [confetti, setConfetti] = useState([]);
  const [floatingEmojis, setFloatingEmojis] = useState([]);
  const [soundOn, setSoundOn] = useState(true);
  const [myStreak, setMyStreak] = useState(0);

  const [myPowerUps, setMyPowerUps] = useState({ hint_used: false, freeze_used: false, mystery_used: false });
  const [hintLetter, setHintLetter] = useState(null);
  const [frozenUntil, setFrozenUntil] = useState(0);
  const [showFreezePicker, setShowFreezePicker] = useState(false);
  const [mysteryResult, setMysteryResult] = useState(null);

  const [adminPassword, setAdminPassword] = useState('');
  const [adminUnlocked, setAdminUnlocked] = useState(false);
  const [questions, setQuestions] = useState([]);
  const [editingQ, setEditingQ] = useState(null);
  const [newClue, setNewClue] = useState('');
  const [newAnswers, setNewAnswers] = useState('');

  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const lastTickRef = useRef(0);

  const [bubbles] = useState(() =>
    Array.from({ length: 14 }, (_, i) => ({
      id: i,
      emoji: ['⭐', '💖', '🌸', '✨', '🎀', '🍬', '🎮', '🕹️', '💫', '🌈', '☁️', '🎯', '🍭', '🎪'][i],
      left: Math.random() * 100,
      delay: Math.random() * 15,
      duration: 12 + Math.random() * 12,
      size: 1.4 + Math.random() * 1.8,
    }))
  );

  useEffect(() => {
    const move = (e) => setCursor({ x: e.clientX, y: e.clientY });
    window.addEventListener('mousemove', move);
    return () => window.removeEventListener('mousemove', move);
  }, []);

  useEffect(() => {
    if (window.location.hash === '#admin') setScreen('adminLogin');
  }, []);

  useEffect(() => {
    if (!roomCode || !playerName) return;
    if (['home', 'selectGame', 'enterName', 'joinRoom'].includes(screen)) return;

    const ws = new WebSocket(`${WS_URL}/ws/${roomCode}/${encodeURIComponent(playerName)}?avatar=${encodeURIComponent(avatar)}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      console.log('📨', data);

      if (data.type === 'players') {
        setPlayers(data.players);
      }
      if (data.type === 'scores') {
        setScores(data.scores);
      }
      if (data.type === 'game_started') {
        setScreen('game');
        setGameOver(null); setRoundWinner(null); setRoundTimeout(null);
        setMyPowerUps({ hint_used: false, freeze_used: false, mystery_used: false });
        setHintLetter(null); setFrozenUntil(0); setMysteryResult(null);
        setMyStreak(0);
        shootConfetti();
        playSound('start', soundOn);
      }
      if (data.type === 'round_start') {
        setCurrentClue(data.clue);
        setClueNumber(data.clue_number);
        setTotalClues(data.total_clues);
        setTimeLeft(data.duration);
        setRoundWinner(null); setRoundTimeout(null);
        setMyLastPoints(null); setFeedback(''); setAnswer('');
        setHintLetter(null); setMysteryResult(null);
      }
      if (data.type === 'you_won') {
        setFeedback('you_won');
        setMyLastPoints(data.points);
        setMyStreak(data.streak || 0);
        shootConfetti();
        playSound(data.streak_bonus > 0 ? 'streak' : 'correct', soundOn);
      }
      if (data.type === 'round_winner') {
        setRoundWinner({
          player: data.player, points: data.points, answer: data.answer,
          streak: data.streak, streak_bonus: data.streak_bonus,
        });
        setTimeLeft(0);
      }
      if (data.type === 'round_timeout') {
        setRoundTimeout({ answer: data.answer });
        setTimeLeft(0);
        playSound('wrong', soundOn);
      }
      if (data.type === 'wrong') {
        if (data.reason === 'bad_answer') {
          setFeedback('wrong');
          playSound('wrong', soundOn);
          setTimeout(() => setFeedback(''), 800);
        } else if (data.reason === 'too_late' || data.reason === 'already_won') {
          setFeedback('too_late'); setTimeout(() => setFeedback(''), 1500);
        } else if (data.reason === 'already_answered') {
          setFeedback('already_answered'); setTimeout(() => setFeedback(''), 1200);
        } else if (data.reason === 'frozen') {
          setFeedback('frozen'); setTimeout(() => setFeedback(''), 1200);
        }
      }
      if (data.type === 'hint_revealed') {
        setHintLetter(data.letter);
        setMyPowerUps(p => ({ ...p, hint_used: true }));
      }
      if (data.type === 'player_frozen') {
        if (data.target === playerName) setFrozenUntil(Date.now() + data.duration * 1000);
        const id = Date.now() + Math.random();
        setFloatingEmojis(prev => [...prev, { id, emoji: '❄️', player: `${data.by} froze ${data.target}`, left: 30 + Math.random() * 40 }]);
        setTimeout(() => setFloatingEmojis(prev => prev.filter(e => e.id !== id)), 3000);
      }
      if (data.type === 'mystery_result') {
        setMysteryResult(data);
        setMyPowerUps(p => ({ ...p, mystery_used: true }));
        if (data.outcome === 'win') {
          shootConfetti();
          playSound('correct', soundOn);
        } else {
          playSound('wrong', soundOn);
        }
      }
      if (data.type === 'game_over') {
        setGameOver({ scores: data.scores, winner: data.winner });
        shootConfetti(); shootConfetti();
        playSound('win', soundOn);
      }
      if (data.type === 'reaction') {
        const id = Date.now() + Math.random();
        setFloatingEmojis(prev => [...prev, { id, emoji: data.emoji, player: data.player, left: 20 + Math.random() * 60 }]);
        setTimeout(() => setFloatingEmojis(prev => prev.filter(e => e.id !== id)), 3000);
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [roomCode, playerName, avatar, soundOn]);

  useEffect(() => {
    if (timeLeft <= 0 || roundWinner || roundTimeout) return;
    timerRef.current = setTimeout(() => setTimeLeft(t => Math.max(0, t - 1)), 1000);
    if (timeLeft <= 10 && timeLeft !== lastTickRef.current) {
      lastTickRef.current = timeLeft;
      playSound('tick', soundOn);
    }
    return () => clearTimeout(timerRef.current);
  }, [timeLeft, roundWinner, roundTimeout, soundOn]);

  const [isFrozen, setIsFrozen] = useState(false);
  useEffect(() => {
    if (frozenUntil === 0) { setIsFrozen(false); return; }
    const check = () => {
      if (Date.now() < frozenUntil) setIsFrozen(true);
      else { setIsFrozen(false); setFrozenUntil(0); }
    };
    check();
    const iv = setInterval(check, 200);
    return () => clearInterval(iv);
  }, [frozenUntil]);

  const shootConfetti = () => {
    const pieces = Array.from({ length: 40 }, (_, i) => ({
      id: i + Math.random(),
      left: Math.random() * 100,
      delay: Math.random() * 0.5,
      duration: 1.8 + Math.random() * 1.2,
      emoji: ['🎉', '✨', '⭐', '💖', '🌸', '🎊', '💫', '🍭'][Math.floor(Math.random() * 8)],
    }));
    setConfetti(prev => [...prev, ...pieces]);
    setTimeout(() => setConfetti(prev => prev.slice(pieces.length)), 3500);
  };

  const resetAll = () => {
    if (wsRef.current) wsRef.current.close();
    setScreen('home'); setIsHost(false); setGameType('');
    setPlayerName(''); setRoomCode(''); setJoinCode('');
    setPlayers([]); setScores({}); setCurrentClue(null);
    setAnswer(''); setFeedback(''); setGameOver(null);
    setRoundWinner(null); setRoundTimeout(null);
    setError(''); setCopied(false);
    setMyPowerUps({ hint_used: false, freeze_used: false, mystery_used: false });
    setHintLetter(null); setFrozenUntil(0); setMysteryResult(null);
    setMyStreak(0);
  };

  const handleHostEnterLobby = async () => {
    if (!playerName.trim()) { setError("Don't forget your name! ✏️"); return; }
    setError('');
    try {
      const res = await axios.post(`${API_URL}/create-room`, { game_type: gameType, host_name: playerName });
      setRoomCode(res.data.room_code);
      setScreen('lobby');
      shootConfetti();
    } catch (err) {
      console.error(err);
      setError('Backend is sleeping 😴 — is it running?');
    }
  };

  const handleJoinLobby = () => {
    if (!playerName.trim()) { setError("We need your name! ✏️"); return; }
    if (joinCode.length !== 6) { setError('Room code must be 6 characters 🔑'); return; }
    setError('');
    setRoomCode(joinCode.toUpperCase());
    setScreen('lobby');
  };

  const copyCode = () => {
    navigator.clipboard.writeText(roomCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const startGame = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'start_game' }));
    }
  };

  const submitAnswer = (e) => {
    e.preventDefault();
    if (!answer.trim() || !wsRef.current || isFrozen) return;
    wsRef.current.send(JSON.stringify({ type: 'submit_answer', answer }));
    setAnswer('');
  };

  const sendReaction = (emoji) => {
    if (!wsRef.current) return;
    wsRef.current.send(JSON.stringify({ type: 'reaction', emoji }));
  };

  const useHint = () => {
    if (myPowerUps.hint_used || !wsRef.current) return;
    wsRef.current.send(JSON.stringify({ type: 'use_hint' }));
  };

  const useFreeze = (target) => {
    if (myPowerUps.freeze_used || !wsRef.current) return;
    wsRef.current.send(JSON.stringify({ type: 'use_freeze', target }));
    setShowFreezePicker(false);
    setMyPowerUps(p => ({ ...p, freeze_used: true }));
  };

  const useMystery = () => {
    if (myPowerUps.mystery_used || !wsRef.current) return;
    wsRef.current.send(JSON.stringify({ type: 'use_mystery' }));
  };

  const tryAdminLogin = async () => {
    try {
      await axios.post(`${API_URL}/admin/login`, { password: adminPassword });
      setAdminUnlocked(true);
      setScreen('adminPanel');
      loadQuestions();
    } catch (err) {
      setError('❌ Wrong password');
      setTimeout(() => setError(''), 2000);
    }
  };

  const loadQuestions = async () => {
    try {
      const res = await axios.get(`${API_URL}/admin/questions`);
      setQuestions(res.data.questions);
    } catch (err) { console.error(err); }
  };

  const saveQuestion = async () => {
    const answersArr = newAnswers.split(',').map(s => s.trim()).filter(Boolean);
    if (!newClue.trim() || answersArr.length === 0) {
      setError('Clue and at least 1 answer required');
      setTimeout(() => setError(''), 2000);
      return;
    }
    try {
      if (editingQ) {
        await axios.put(`${API_URL}/admin/questions/${editingQ.id}`, { clue: newClue, answers: answersArr });
      } else {
        await axios.post(`${API_URL}/admin/questions`, { clue: newClue, answers: answersArr });
      }
      setNewClue(''); setNewAnswers(''); setEditingQ(null);
      loadQuestions();
    } catch (err) { console.error(err); }
  };

  const deleteQuestion = async (id) => {
    await axios.delete(`${API_URL}/admin/questions/${id}`);
    loadQuestions();
  };

  const startEdit = (q) => {
    setEditingQ(q);
    setNewClue(q.clue);
    setNewAnswers(q.answers.join(', '));
  };

  const timerPercent = timeLeft > 0 ? (timeLeft / 30) * 100 : 0;
  const isUrgent = timeLeft <= 10 && timeLeft > 0;

  return (
    <div className="stage">
      <div className="cursor-glow" style={{ left: cursor.x, top: cursor.y }} />

      <div className="bubble-field">
        {bubbles.map(b => (
          <span key={b.id} className="bubble"
            style={{ left: `${b.left}%`, animationDelay: `${b.delay}s`, animationDuration: `${b.duration}s`, fontSize: `${b.size}rem` }}>
            {b.emoji}
          </span>
        ))}
      </div>

      {confetti.length > 0 && (
        <div className="confetti-field">
          {confetti.map(c => (
            <span key={c.id} className="confetti"
              style={{ left: `${c.left}%`, animationDelay: `${c.delay}s`, animationDuration: `${c.duration}s` }}>
              {c.emoji}
            </span>
          ))}
        </div>
      )}

      {floatingEmojis.length > 0 && (
        <div className="emoji-float-field">
          {floatingEmojis.map(e => (
            <span key={e.id} className="floating-emoji" style={{ left: `${e.left}%` }}>
              {e.emoji}
              <small>{e.player}</small>
            </span>
          ))}
        </div>
      )}

      <div className="cabinet">
        <div className="cabinet-glass" />
        <div className="mascot">👾</div>

        <button className="sound-toggle" onClick={() => setSoundOn(s => !s)} title={soundOn ? 'mute' : 'unmute'}>
          {soundOn ? '🔊' : '🔇'}
        </button>

        {screen === 'home' && (
          <div className="screen-content pop-in">
            <button className="admin-peek" onClick={() => setScreen('adminLogin')} title="owner access">⚙️</button>
            <h1 className="hero-title">
              <span className="word">welcome</span>
              <span className="word accent">to the</span>
              <span className="word big">arcade 🎮</span>
            </h1>
            <p className="hero-sub">Pick your game. Grab your crew.<br />Campus is your playground.</p>
            <div className="big-buttons">
              <button className="arcade-btn pink" onClick={() => { setIsHost(true); setScreen('selectGame'); }}>
                <span className="btn-emoji">🚀</span>
                <span className="btn-text"><strong>Host a Game</strong><small>you're the boss</small></span>
              </button>
              <button className="arcade-btn mint" onClick={() => { setIsHost(false); setScreen('selectGame'); }}>
                <span className="btn-emoji">🔑</span>
                <span className="btn-text"><strong>Join a Game</strong><small>got a code?</small></span>
              </button>
            </div>
          </div>
        )}

        {screen === 'selectGame' && (
          <div className="screen-content pop-in">
            <button className="back-link" onClick={resetAll}>← back</button>
            <h2 className="step-title">choose your adventure</h2>
            <div className="game-grid">
              {GAMES.map(g => (
                <button key={g.id} className={`game-card ${g.id === 'Mafia' ? 'dark' : ''}`}
                  onClick={() => { setGameType(g.id); setScreen(isHost ? 'enterName' : 'joinRoom'); }}>
                  <span className="game-emoji">{g.emoji}</span>
                  <strong>{g.title}</strong>
                  <small>{g.tagline}</small>
                </button>
              ))}
            </div>
          </div>
        )}

        {screen === 'enterName' && (
          <div className="screen-content pop-in">
            <button className="back-link" onClick={resetAll}>← back</button>
            <div className="pill">{gameType}</div>
            <h2 className="step-title">pick your character</h2>
            <div className="avatar-grid">
              {AVATARS.map(a => (
                <button key={a}
                  className={`avatar-btn ${avatar === a ? 'selected' : ''}`}
                  onClick={() => setAvatar(a)}>
                  {a}
                </button>
              ))}
            </div>
            <h2 className="step-title">what should we call you?</h2>
            <input className="fun-input" placeholder="your name..." maxLength={15}
              value={playerName} onChange={e => setPlayerName(e.target.value)} />
            <button className="arcade-btn pink full" onClick={handleHostEnterLobby}>
              <span className="btn-emoji">🎉</span>
              <span className="btn-text"><strong>Create the Room</strong><small>let's go!</small></span>
            </button>
            {error && <p className="error-bubble">{error}</p>}
          </div>
        )}

        {screen === 'joinRoom' && (
          <div className="screen-content pop-in">
            <button className="back-link" onClick={resetAll}>← back</button>
            <div className="pill">{gameType}</div>
            <h2 className="step-title">room code, please!</h2>
            <input className="fun-input code" placeholder="ABC123" maxLength={6}
              value={joinCode} onChange={e => setJoinCode(e.target.value.toUpperCase())} />
            <h2 className="step-title">pick your character</h2>
            <div className="avatar-grid">
              {AVATARS.map(a => (
                <button key={a}
                  className={`avatar-btn ${avatar === a ? 'selected' : ''}`}
                  onClick={() => setAvatar(a)}>
                  {a}
                </button>
              ))}
            </div>
            <h2 className="step-title">and your name?</h2>
            <input className="fun-input" placeholder="your name..." maxLength={15}
              value={playerName} onChange={e => setPlayerName(e.target.value)} />
            <button className="arcade-btn mint full" onClick={handleJoinLobby}>
              <span className="btn-emoji">✨</span>
              <span className="btn-text"><strong>Sneak In</strong><small>ready to play</small></span>
            </button>
            {error && <p className="error-bubble">{error}</p>}
          </div>
        )}

        {screen === 'lobby' && (
          <div className="screen-content pop-in">
            <div className="pill">{gameType}</div>
            <div className="ticket">
              <span className="ticket-label">ROOM CODE</span>
              <span className="ticket-code">{roomCode}</span>
              <button className="copy-chip" onClick={copyCode}>
                {copied ? '✅ copied!' : '📋 tap to copy'}
              </button>
            </div>
            <div className="players-section">
              <h3 className="players-header">players <span className="count-badge">{players.length}</span></h3>
              <div className="players-grid">
                {players.length === 0 && <p className="loading-dots">connecting...</p>}
                {players.map(p => (
                  <div key={p.name} className={`player-bubble ${p.name === playerName ? 'me' : ''}`}>
                    <span className="player-avatar">{p.avatar}</span>
                    <span className="player-name">{p.name}</span>
                  </div>
                ))}
              </div>
            </div>
            {isHost ? (
              <button className="arcade-btn sunset full" onClick={startGame}>
                <span className="btn-emoji">🎬</span>
                <span className="btn-text"><strong>Start Game</strong><small>everyone ready?</small></span>
              </button>
            ) : (
              <p className="waiting-msg">💤 waiting for the host to hit start...</p>
            )}
            <button className="ghost-btn" onClick={resetAll}>leave room</button>
          </div>
        )}

        {screen === 'game' && !gameOver && (
          <div className="screen-content pop-in">
            <div className="clue-header">
              <span className="pill">🎯 clue {clueNumber} / {totalClues}</span>
              {myStreak >= 2 && <span className="streak-chip">🔥 {myStreak}x</span>}
              {timeLeft > 0 && <span className={`timer-chip ${isUrgent ? 'urgent' : ''}`}>⏱ {timeLeft}s</span>}
            </div>

            {timeLeft > 0 && (
              <div className="timer-bar-wrap">
                <div className={`timer-bar ${isUrgent ? 'urgent' : ''}`} style={{ width: `${timerPercent}%` }} />
              </div>
            )}

            <div className={`clue-card ${roundWinner ? 'correct' : ''} ${roundTimeout ? 'wrong' : ''}`}>
              <div className="clue-emoji">🔎</div>
              <p className="clue-text">{currentClue}</p>
              {hintLetter && <div className="hint-badge">💡 starts with "<strong>{hintLetter}</strong>"</div>}
            </div>

            {!roundWinner && !roundTimeout && (
              <form className="answer-form" onSubmit={submitAnswer}>
                <input
                  className={`fun-input ${feedback === 'wrong' ? 'shake' : ''} ${isFrozen ? 'frozen' : ''}`}
                  placeholder={isFrozen ? '❄️ frozen! waiting...' : 'type your answer...'}
                  value={answer}
                  onChange={e => setAnswer(e.target.value)}
                  autoFocus
                  disabled={timeLeft <= 0 || isFrozen}
                />
                <button type="submit" className="arcade-btn mint full" disabled={timeLeft <= 0 || isFrozen}>
                  <span className="btn-emoji">⚡</span>
                  <span className="btn-text"><strong>Answer!</strong><small>be fast</small></span>
                </button>
              </form>
            )}

            {feedback === 'you_won' && myLastPoints && (
              <div className="round-result win">
                <span className="result-emoji">🏆</span>
                <div>
                  <strong>YOU GOT IT!</strong>
                  <small>+{myLastPoints} points ⚡ {myStreak >= 3 && `· 🔥 ${myStreak}x streak!`}</small>
                </div>
              </div>
            )}
            {feedback === 'wrong' && <p className="feedback bad">❌ Nope, try again!</p>}
            {feedback === 'too_late' && <p className="feedback bad">😢 Too slow — someone else got it!</p>}
            {feedback === 'already_answered' && <p className="feedback bad">🤐 You already guessed this round</p>}
            {feedback === 'frozen' && <p className="feedback bad">❄️ You're frozen!</p>}

            {mysteryResult && (
              <div className={`round-result ${mysteryResult.outcome === 'win' ? 'win' : 'timeout'}`}>
                <span className="result-emoji">🎁</span>
                <div>
                  <strong>{mysteryResult.outcome === 'win' ? 'JACKPOT!' : 'Ouch!'}</strong>
                  <small>{mysteryResult.points > 0 ? '+' : ''}{mysteryResult.points} points</small>
                </div>
              </div>
            )}

            {roundWinner && (
              <div className="round-result">
                <span className="result-emoji">🎉</span>
                <div>
                  <strong>{roundWinner.player} got it!</strong>
                  <small>
                    "{roundWinner.answer}" · +{roundWinner.points} pts
                    {roundWinner.streak_bonus > 0 && ` · 🔥 ${roundWinner.streak}x streak +${roundWinner.streak_bonus}`}
                  </small>
                </div>
              </div>
            )}
            {roundTimeout && (
              <div className="round-result timeout">
                <span className="result-emoji">⏰</span>
                <div>
                  <strong>Time's up!</strong>
                  <small>Answer was "{roundTimeout.answer}"</small>
                </div>
              </div>
            )}

            <div className="powerups-bar">
              <button className={`powerup-btn ${myPowerUps.hint_used ? 'used' : ''}`} onClick={useHint} disabled={myPowerUps.hint_used}>
                <span>⚡</span>
                <small>{myPowerUps.hint_used ? 'used' : 'hint'}</small>
              </button>
              <button className={`powerup-btn ${myPowerUps.freeze_used ? 'used' : ''}`}
                onClick={() => setShowFreezePicker(true)} disabled={myPowerUps.freeze_used}>
                <span>❄️</span>
                <small>{myPowerUps.freeze_used ? 'used' : 'freeze'}</small>
              </button>
              <button className={`powerup-btn ${myPowerUps.mystery_used ? 'used' : ''}`} onClick={useMystery} disabled={myPowerUps.mystery_used}>
                <span>🎁</span>
                <small>{myPowerUps.mystery_used ? 'used' : 'mystery'}</small>
              </button>
            </div>

            <div className="mini-scoreboard">
              <h4>🏆 live scores</h4>
              {Object.entries(scores).sort((a, b) => b[1].score - a[1].score).map(([name, data], i) => (
                <div key={name} className={`score-row ${name === playerName ? 'me' : ''}`}>
                  <span>
                    {i === 0 && data.score > 0 ? '👑' : (name === playerName ? '⭐' : '👤')} {name}
                    {data.streak >= 2 && <span className="streak-inline"> 🔥{data.streak}</span>}
                  </span>
                  <span className="score-val">{data.score}</span>
                </div>
              ))}
            </div>

            <div className="reactions-bar">
              {REACTIONS.map(r => (
                <button key={r} className="reaction-btn" onClick={() => sendReaction(r)}>{r}</button>
              ))}
            </div>
          </div>
        )}

        {gameOver && (
          <div className="screen-content pop-in won-screen">
            <div className="trophy">🏆</div>
            <h2 className="won-title">
              {gameOver.winner === playerName ? 'You win!' : `${gameOver.winner} wins!`}
            </h2>
            <p className="won-sub">That was intense. Final scores:</p>
            <div className="final-scoreboard">
              {Object.entries(gameOver.scores).sort((a, b) => b[1] - a[1]).map(([name, score], i) => (
                <div key={name} className={`final-row ${name === playerName ? 'me' : ''}`}>
                  <span className="rank">{['🥇', '🥈', '🥉'][i] || `#${i + 1}`}</span>
                  <span className="fname">{name}</span>
                  <span className="fscore">{score}</span>
                </div>
              ))}
            </div>
            <button className="arcade-btn pink full" onClick={resetAll} style={{ marginTop: '1rem' }}>
              <span className="btn-emoji">🎮</span>
              <span className="btn-text"><strong>Back to Home</strong><small>play again</small></span>
            </button>
          </div>
        )}

        {showFreezePicker && (
          <div className="modal-overlay" onClick={() => setShowFreezePicker(false)}>
            <div className="modal-box pop-in" onClick={e => e.stopPropagation()}>
              <h3>❄️ Freeze who?</h3>
              <p className="modal-sub">They can't type for 5 seconds!</p>
              <div className="target-list">
                {players.filter(p => p.name !== playerName).map(p => (
                  <button key={p.name} className="target-chip" onClick={() => useFreeze(p.name)}>
                    {p.avatar} {p.name}
                  </button>
                ))}
                {players.filter(p => p.name !== playerName).length === 0 && (
                  <p className="waiting-msg">no one else to freeze 🥲</p>
                )}
              </div>
              <button className="ghost-btn" onClick={() => setShowFreezePicker(false)}>cancel</button>
            </div>
          </div>
        )}

        {screen === 'adminLogin' && (
          <div className="screen-content pop-in">
            <button className="back-link" onClick={resetAll}>← back</button>
            <div className="admin-badge">🔐 OWNER ACCESS</div>
            <h2 className="step-title">enter admin password</h2>
            <input className="fun-input" type="password" placeholder="password..."
              value={adminPassword} onChange={e => setAdminPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && tryAdminLogin()} />
            <button className="arcade-btn pink full" onClick={tryAdminLogin}>
              <span className="btn-emoji">🔓</span>
              <span className="btn-text"><strong>Unlock</strong><small>only you</small></span>
            </button>
            {error && <p className="error-bubble">{error}</p>}
          </div>
        )}

        {screen === 'adminPanel' && adminUnlocked && (
          <div className="screen-content pop-in admin-panel">
            <div className="admin-badge">🔐 OWNER MODE</div>
            <h2 className="step-title">question manager</h2>
            <p className="modal-sub">{questions.length} questions stored</p>

            <div className="admin-form">
              <textarea
                className="fun-input admin-textarea"
                placeholder="Enter the clue/riddle..."
                value={newClue}
                onChange={e => setNewClue(e.target.value)}
                rows={2}
              />
              <input className="fun-input" placeholder="answers, comma-separated (e.g., library, lib)"
                value={newAnswers} onChange={e => setNewAnswers(e.target.value)} />
              <div className="admin-btn-row">
                <button className="arcade-btn pink" onClick={saveQuestion} style={{ flex: 1 }}>
                  <span className="btn-emoji">{editingQ ? '💾' : '➕'}</span>
                  <span className="btn-text"><strong>{editingQ ? 'Update' : 'Add'}</strong></span>
                </button>
                {editingQ && (
                  <button className="arcade-btn secondary" onClick={() => { setEditingQ(null); setNewClue(''); setNewAnswers(''); }}>
                    <span className="btn-emoji">✖</span>
                    <span className="btn-text"><strong>Cancel</strong></span>
                  </button>
                )}
              </div>
            </div>

            <div className="admin-list">
              {questions.map((q, i) => (
                <div key={q.id} className="admin-q-card">
                  <div className="admin-q-header">
                    <strong>#{i + 1}</strong>
                    <div className="admin-q-actions">
                      <button onClick={() => startEdit(q)} title="edit">✏️</button>
                      <button onClick={() => deleteQuestion(q.id)} title="delete">🗑️</button>
                    </div>
                  </div>
                  <p className="admin-q-clue">{q.clue}</p>
                  <small className="admin-q-answers">✅ {q.answers.join(', ')}</small>
                </div>
              ))}
            </div>

            <button className="ghost-btn" onClick={resetAll}>← exit admin</button>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;