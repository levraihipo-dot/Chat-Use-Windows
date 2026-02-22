import pytchat
import subprocess
import time
import queue
import threading
import traceback
import asyncio
import websockets
import json
from collections import deque

# ======================
# CONFIG
# ======================

VM_NAME = NOM DE LA VM"
VIDEO_ID = "ID DU CHAT YOUTUBE"
COMMAND_DELAY = 0.05

VOTE_REQUIRED = 2
VOTE_TIMEOUT = 30       # secondes avant annulation du vote
DEBUG_KEYS = True
WEBSOCKET_PORT = 8766

INACTIVITY_REVERT_DELAY = 15 * 60  # 15 minutes
SOLO_USER_WINDOW = 120              # 2 minutes

PRIVILEGED_USERS = [
    "levraihipo",
    "cameracxis",
    "S8m73l"
]

BLOCKED_WORDS = [
    "Nigger", "nigger", "Niggers", "niggers", "sreggiN", "sreggin",
    "jews", "Jews", "swej", "sweJ",
    "echo", "html", "lmth", "ohce",
    "Nagger", "nagger", "Naggers", "naggers",
    "sreggan", "sreggaN", "reggan", "reggaN",
]

KNOWN_COMMANDS = {
    "!type", "!send", "!key", "!combo", "!wait",
    "!startvm", "!revert", "!restartvm"
}

def is_known_command(cmd):
    for k in KNOWN_COMMANDS:
        if cmd == k or cmd.startswith(k + " "):
            return True
    return False

cmd_queue = queue.Queue()
cooldowns = {
    "!startvm": 30,
    "!revert": 120,
    "!restartvm": 120
}
last_exec = {}
ws_clients = set()
waiting_mode = False

# ======================
# ASYNCIO LOOP PARTAGEE
# ======================

ws_loop = asyncio.new_event_loop()

def run_ws_loop():
    asyncio.set_event_loop(ws_loop)
    ws_loop.run_forever()

threading.Thread(target=run_ws_loop, daemon=True).start()

def broadcast_sync(user, command):
    async def _send():
        clients = list(ws_clients)
        if not clients:
            return
        msg = json.dumps({"user": user, "command": command})
        print(f"[BROADCAST] -> {len(clients)} client(s): {user} | {command}")
        await asyncio.gather(
            *[client.send(msg) for client in clients],
            return_exceptions=True
        )
    asyncio.run_coroutine_threadsafe(_send(), ws_loop)

# ======================
# WEBSOCKET SERVER
# ======================

async def websocket_handler(websocket):
    ws_clients.add(websocket)
    print(f"[WEBSOCKET] Client connected (total: {len(ws_clients)})")
    # Envoie l etat initial au nouveau client : idle elapsed + waiting mode
    try:
        idle_elapsed = int(time.time() - last_message_time)
        init_msg = json.dumps({
            "user": "BOT",
            "command": f"INIT:idle={idle_elapsed}:waiting={1 if waiting_mode else 0}"
        })
        await websocket.send(init_msg)
    except Exception as e:
        print(f"[WEBSOCKET] Init send failed: {e}")
    try:
        await websocket.wait_closed()
    finally:
        ws_clients.discard(websocket)
        print(f"[WEBSOCKET] Client disconnected (total: {len(ws_clients)})")

async def start_ws_server():
    server = await websockets.serve(websocket_handler, "localhost", WEBSOCKET_PORT)
    print(f"[WEBSOCKET] Server started on ws://localhost:{WEBSOCKET_PORT}")
    await server.wait_closed()

future = asyncio.run_coroutine_threadsafe(start_ws_server(), ws_loop)
print("[WEBSOCKET] Server coroutine scheduled")
def _check_ws_error():
    time.sleep(3)
    if future.done() and future.exception():
        print(f"[WEBSOCKET ERROR] Server failed to start: {future.exception()}")
threading.Thread(target=_check_ws_error, daemon=True).start()

# ======================
# INACTIVITY TRACKER
# ======================

last_message_time = time.time()
recent_chatters = deque()

def record_message(user):
    global last_message_time, waiting_mode
    last_message_time = time.time()
    if waiting_mode:
        waiting_mode = False
        broadcast_sync("BOT", "STATUS:active")
    recent_chatters.append((last_message_time, user))
    cutoff = last_message_time - SOLO_USER_WINDOW
    while recent_chatters and recent_chatters[0][0] < cutoff:
        recent_chatters.popleft()

def is_solo_user():
    now = time.time()
    cutoff = now - SOLO_USER_WINDOW
    active = set(u for t, u in recent_chatters if t >= cutoff)
    return len(active) <= 1

def inactivity_watcher():
    global last_message_time, waiting_mode
    print(f"[INACTIVITY] Watcher started — auto-revert apres {INACTIVITY_REVERT_DELAY}s de silence")
    while True:
        time.sleep(10)
        idle = time.time() - last_message_time
        if idle >= INACTIVITY_REVERT_DELAY:
            print(f"[INACTIVITY] {int(idle)}s sans message — auto-revert!")
            last_message_time = time.time()
            waiting_mode = True
            cmd_queue.put("!revert")
            broadcast_sync("BOT", "!revert (inactivity)")
            broadcast_sync("BOT", "STATUS:waiting")

threading.Thread(target=inactivity_watcher, daemon=True).start()

# ======================
# VOTE SYSTEM
# ======================

# votes[cmd] = {"users": set(), "timer": threading.Timer|None, "start": float}
votes = {
    "!revert":    {"users": set(), "timer": None, "start": 0},
    "!restartvm": {"users": set(), "timer": None, "start": 0},
}

def cancel_vote(cmd):
    v = votes[cmd]
    if v["timer"]:
        v["timer"].cancel()
        v["timer"] = None
    if v["users"]:
        print(f"[VOTE] {cmd} expiré — annulé")
        broadcast_sync("BOT", f"VOTE_EXPIRED:{cmd}")
    v["users"].clear()
    v["start"] = 0

def execute_vote(cmd, user):
    """Exécute un vote accepté."""
    cancel_vote(cmd)  # annule le timer
    print(f"[VOTE] Accepté: {cmd}")
    cmd_queue.put(cmd)
    broadcast_sync(user, cmd)

def start_vote_timer(cmd):
    """Lance/remet le timer d'expiration du vote."""
    v = votes[cmd]
    if v["timer"]:
        v["timer"].cancel()
    t = threading.Timer(VOTE_TIMEOUT, cancel_vote, args=[cmd])
    t.daemon = True
    t.start()
    v["timer"] = t
    v["start"] = time.time()

# ======================
# SCANCODES
# ======================

SCANCODES = {
    "ctrl":  ["1d", "9d"],
    "shift": ["2a", "aa"],
    "alt":   ["38", "b8"],
    "win":   ["e0 5b", "e0 db"],
    "enter": ["1c", "9c"],
    "esc":   ["01", "81"],
    "tab":   ["0f", "8f"],
    "space": ["39", "b9"],
    "backspace": ["0e", "8e"],
    "del":   ["e0 53", "e0 d3"],
    "up":    ["e0 48", "e0 c8"],
    "down":  ["e0 50", "e0 d0"],
    "left":  ["e0 4b", "e0 cb"],
    "right": ["e0 4d", "e0 cd"],
}

for i in range(1, 13):
    SCANCODES[f"f{i}"] = [hex(0x3A + i)[2:], hex(0xBA + i)[2:]]

LETTER_SC = {
    "a":"1e","b":"30","c":"2e","d":"20","e":"12","f":"21","g":"22","h":"23",
    "i":"17","j":"24","k":"25","l":"26","m":"32","n":"31","o":"18","p":"19",
    "q":"10","r":"13","s":"1f","t":"14","u":"16","v":"2f","w":"11","x":"2d",
    "y":"15","z":"2c"
}
for l, c in LETTER_SC.items():
    SCANCODES[l] = [c, hex(int(c, 16) | 0x80)[2:]]

NUM_SC = {"1":"02","2":"03","3":"04","4":"05","5":"06","6":"07","7":"08","8":"09","9":"0a","0":"0b"}
for n, c in NUM_SC.items():
    SCANCODES[n] = [c, hex(int(c, 16) | 0x80)[2:]]

# ======================
# LOW LEVEL
# ======================

def send_scancode(sc):
    subprocess.run(
        ["VBoxManage", "controlvm", VM_NAME, "keyboardputscancode"] + sc.split(),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def press_key(key):
    key = key.lower()
    if key not in SCANCODES:
        if DEBUG_KEYS: print(f"[KEY DEBUG] Unknown key: {key}")
        return
    if DEBUG_KEYS: print(f"[KEY DEBUG] Key pressed: {key}")
    send_scancode(SCANCODES[key][0])
    send_scancode(SCANCODES[key][1])

def combo(keys):
    if DEBUG_KEYS: print(f"[KEY DEBUG] Combo: {' + '.join(keys)}")
    presses, releases = [], []
    for k in keys:
        if k in SCANCODES:
            presses.append(SCANCODES[k][0])
            releases.insert(0, SCANCODES[k][1])
        elif DEBUG_KEYS:
            print(f"[KEY DEBUG] Unknown combo key: {k}")
    for p in presses: send_scancode(p)
    for r in releases: send_scancode(r)

# ======================
# COMMAND HANDLER
# ======================

def handle(command):
    if DEBUG_KEYS: print(f"[CMD DEBUG] Executing: {command}")

    if command.startswith("!type "):
        subprocess.run(["VBoxManage", "controlvm", VM_NAME, "keyboardputstring", command[6:]])
    elif command.startswith("!send "):
        subprocess.run(["VBoxManage", "controlvm", VM_NAME, "keyboardputstring", command[6:]])
        press_key("enter")
    elif command.startswith("!key "):
        press_key(command[5:])
    elif command.startswith("!combo "):
        combo(command[7:].split("+"))
    elif command.startswith("!wait "):
        try:
            time.sleep(min(float(command[6:]), 60))
        except Exception as e:
            if DEBUG_KEYS: print(f"[CMD DEBUG] Invalid wait: {e}")
    elif command == "!startvm":
        subprocess.run(["VBoxManage", "startvm", VM_NAME, "--type", "gui"])
    elif command == "!revert":
        print("[REVERT] Powering off...")
        subprocess.run(["VBoxManage", "controlvm", VM_NAME, "poweroff"])
        time.sleep(4)
        print("[REVERT] Restoring snapshot...")
        subprocess.run(["VBoxManage", "snapshot", VM_NAME, "restorecurrent"])
        time.sleep(3)
        print("[REVERT] Starting VM...")
        subprocess.run(["VBoxManage", "startvm", VM_NAME, "--type", "gui"])
    elif command == "!restartvm":
        print("[RESTART] VM reset")
        subprocess.run(["VBoxManage", "controlvm", VM_NAME, "reset"])

# ======================
# EXECUTOR
# ======================

def executor():
    while True:
        try:
            cmd = cmd_queue.get()
            now = time.time()
            if cmd in cooldowns:
                time_left = cooldowns[cmd] - (now - last_exec.get(cmd, 0))
                if time_left > 0:
                    print(f"[COOLDOWN] {cmd} cooldown: {int(time_left)}s restant")
                    cmd_queue.task_done()
                    continue
                last_exec[cmd] = now
            handle(cmd)
            time.sleep(COMMAND_DELAY)
            cmd_queue.task_done()
        except Exception as e:
            print(f"[EXECUTOR ERROR] {e}")
            traceback.print_exc()
            cmd_queue.task_done()

threading.Thread(target=executor, daemon=True).start()

# ======================
# YOUTUBE CHAT
# ======================

print("[DEBUG] Listening for chat commands...")

while True:
    try:
        chat = pytchat.create(video_id=VIDEO_ID)
        print("[DEBUG] Chat connected")

        while chat.is_alive():
            items = chat.get().sync_items()

            if not items:
                time.sleep(1)
                continue

            for c in items:
                user = c.author.name
                msg = c.message.strip().lower()
                is_privileged = (user in PRIVILEGED_USERS
                                 or c.author.isChatOwner
                                 or c.author.isChatModerator)

                if any(word in msg for word in BLOCKED_WORDS):
                    print(f"[BLOCKED] @{user}")
                    continue

                record_message(user)

                # ── Commandes avec vote (revert / restartvm) ──
                if msg in votes:
                    v = votes[msg]

                    if is_privileged:
                        # Admin = compte comme 2 votes → valide direct
                        # On passe visuellement par le système : 1 puis 2 pips
                        print(f"[PRIVILEGED] @{user} -> {msg} (admin, validation directe)")
                        v["users"].add(user)
                        broadcast_sync(user, f"VOTE:{msg}:1:{VOTE_TIMEOUT}")
                        time.sleep(0.3)  # petit délai pour que l'overlay affiche le pip 1
                        execute_vote(msg, user)
                        continue

                    if is_solo_user():
                        print(f"[SOLO] @{user} -> {msg} (seul dans le chat)")
                        v["users"].add(user)
                        broadcast_sync(user, f"VOTE:{msg}:1:{VOTE_TIMEOUT}")
                        time.sleep(0.3)
                        execute_vote(msg, user)
                        continue

                    if user in v["users"]:
                        print(f"[VOTE] @{user} a déjà voté pour {msg}")
                        continue

                    v["users"].add(user)
                    count = len(v["users"])
                    print(f"[VOTE] {msg} : {count}/{VOTE_REQUIRED}")

                    if count == 1:
                        # Premier vote → démarre le timer
                        start_vote_timer(msg)
                        broadcast_sync(user, f"VOTE:{msg}:{count}:{VOTE_TIMEOUT}")
                    else:
                        # Deuxième vote → exécute
                        remaining = max(0, int(VOTE_TIMEOUT - (time.time() - v["start"])))
                        broadcast_sync(user, f"VOTE:{msg}:{count}:{remaining}")
                        time.sleep(0.2)
                        execute_vote(msg, user)
                    continue

                # ── Commandes normales ──
                # Extrait uniquement les commandes connues
                known_cmds = []
                if "!" in msg:
                    candidates = [f"!{p.strip()}" for p in msg.split("!") if p.strip() and p.strip()[0].isalpha()]
                    known_cmds = [cmd for cmd in candidates if is_known_command(cmd)]

                if known_cmds:
                    for cmd in known_cmds:
                        print(f"[COMMAND] @{user} -> {cmd}")
                        cmd_queue.put(cmd)
                        broadcast_sync(user, cmd)
                else:
                    # Pas de commande connue → message de chat normal
                    print(f"[CHAT] @{user} -> {c.message.strip()}")
                    broadcast_sync(user, f"CHAT:{c.message.strip()}")

    except Exception as e:
        print(f"[CHAT ERROR] {e}")
        print("[CHAT DEBUG] Reconnection dans 5s...")
        time.sleep(5)