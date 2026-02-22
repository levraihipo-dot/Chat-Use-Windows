# 🎮 YouTube Chat VM Controller — Setup Guide

Système de contrôle d'une machine virtuelle VirtualBox via le chat YouTube, avec overlay OBS en temps réel.

---

## 📦 Composants

| Fichier | Rôle |
|---|---|
| `bot.py` | Backend Python — écoute le chat YouTube, exécute les commandes sur la VM, diffuse via WebSocket |
| `overlay.html` | Frontend HTML — affiche les événements, votes, timer d'inactivité en overlay OBS |

---

## 🔧 Prérequis

### Python
```bash
pip install pytchat websockets
```

### VirtualBox
- VirtualBox installé avec `VBoxManage` accessible dans le PATH système
- Une VM créée avec un snapshot existant (utilisé par `!revert`)

### Vérifier VBoxManage dans le PATH
```bash
VBoxManage --version
```
Si la commande n'est pas trouvée, ajouter le dossier d'installation de VirtualBox au PATH (ex : `C:\Program Files\Oracle\VirtualBox` sur Windows).

---

## ⚙️ Configuration du bot (`bot.py`)

Ouvrir `bot.py` et modifier les variables en haut du fichier :

```python
VM_NAME   = "NOM DE LA VM"         # Nom exact de votre VM dans VirtualBox
VIDEO_ID  = "ID DU CHAT YOUTUBE"   # ID de la vidéo YouTube (ex: dQw4w9WgXcQ)
```

> L'ID YouTube se trouve dans l'URL du live : `youtube.com/watch?v=`**`XXXXXXXXXXXX`**

### Autres réglages disponibles

| Variable | Valeur par défaut | Description |
|---|---|---|
| `VOTE_REQUIRED` | `2` | Nombre de votes nécessaires pour `!revert` / `!restartvm` |
| `VOTE_TIMEOUT` | `30` s | Délai avant annulation d'un vote |
| `INACTIVITY_REVERT_DELAY` | `900` s (15 min) | Silence avant auto-revert |
| `SOLO_USER_WINDOW` | `120` s | Fenêtre pour détecter si un seul user est actif |
| `WEBSOCKET_PORT` | `8766` | Port du serveur WebSocket local |
| `PRIVILEGED_USERS` | liste | Usernames ayant des droits admin (vote direct) |
| `BLOCKED_WORDS` | liste | Mots filtrés — aucune commande ne s'exécutera |

---

## ▶️ Lancer le bot

```bash
python bot.py
```

Le bot va :
1. Se connecter au chat YouTube
2. Démarrer un serveur WebSocket sur `ws://localhost:8766`
3. Écouter et exécuter les commandes en temps réel

---

## 💬 Commandes disponibles dans le chat

| Commande | Description |
|---|---|
| `!startvm` | Démarre la VM |
| `!revert` | Éteint la VM, restaure le snapshot, redémarre (nécessite 2 votes) |
| `!restartvm` | Reset forcé de la VM (nécessite 2 votes) |
| `!type [texte]` | Envoie du texte au clavier de la VM |
| `!send [texte]` | Envoie du texte + Entrée |
| `!key [touche]` | Appuie sur une touche (ex: `!key enter`) |
| `!combo [touches]` | Combinaison de touches (ex: `!combo ctrl+alt+del`) |
| `!wait [secondes]` | Pause (max 60s) |

---

## 🖥️ Configuration OBS

### Version recommandée
**OBS 28** ou supérieure. La version 28 est recommandée si vous avez besoin de gérer plusieurs instances OBS simultanément (profils séparés, multi-scènes). Pour un usage simple, la dernière version stable convient.

Téléchargement : [obsproject.com](https://obsproject.com)

---

### 1. Capture de la fenêtre VirtualBox

Dans OBS, ajouter une source **"Capture de fenêtre"** (Window Capture) :

- **Méthode** : Sélectionner la fenêtre par **nom/titre exact** (et non par type d'application)
- **Titre de fenêtre** : correspond au nom de votre VM tel qu'il apparaît dans la barre de titre VirtualBox, généralement de la forme :
  ```
  NOM_DE_LA_VM [En ligne] - Oracle VM VirtualBox
  ```
  ⚠️ Choisir cette fenêtre dans la liste déroulante, ne pas sélectionner le processus `VirtualBox` en général.
- **Audio** : Cocher **"Capturer l'audio de la fenêtre"** (Window Audio Capture / Application Audio Capture) pour que le son de la VM soit capturé. Cette option est disponible nativement depuis OBS 28+.

---

### 2. Texte d'instruction en arrière-plan (sous la VM)

Ajouter une source **"Texte (GDI+)"** ou **"Texte (FreeType 2)"** placée **en dessous** de la capture VirtualBox dans l'ordre des sources :

**Contenu du texte :**
```
To start the VM: !startvm
If reverting, do nothing
```

**Suggestions de style :**
- Police : `Consolas` ou `Courier New`, taille 22–28
- Couleur : blanc ou gris clair `#CCCCCC`
- Fond semi-transparent recommandé pour la lisibilité

---

### 3. Texte d'instruction au-dessus de la VM

Ajouter une seconde source **"Texte"** placée **au-dessus** de la capture VirtualBox dans l'ordre des sources :

**Contenu du texte :**
```
If broken or crashed:
Requires 2 people
!restartvm — restart the VM
!revert — revert to snapshot
```

**Suggestions de style :**
- Police : `Consolas`, taille 20–24
- Couleur : jaune `#FFDD57` ou orange `#FF9900` pour attirer l'attention
- Fond semi-transparent noir `rgba(0,0,0,0.6)` recommandé

---

### 4. Overlay HTML (`overlay.html`)

L'overlay doit être ajouté **en dernier dans l'ordre des sources** (tout en haut de la pile) pour qu'il apparaisse par-dessus tout le reste.

**Étapes :**

1. Dans OBS, cliquer **"+" → "Navigateur"** (Browser Source)
2. Cocher **"Fichier local"**
3. Cliquer **"Parcourir"** et sélectionner votre fichier `overlay.html`
4. Régler les dimensions :
   - **Largeur** : `380`
   - **Hauteur** : `600` (ajuster selon votre mise en page)
5. Décocher **"Actualiser le navigateur quand la scène devient active"** pour éviter les rechargements intempestifs
6. Cocher **"Arrière-plan transparent"** pour que le fond noir des cartes soit le seul fond visible (pas de rectangle blanc autour)
7. Positionner l'overlay dans un coin de l'écran (recommandé : coin supérieur droit ou gauche)

> ⚠️ Le navigateur OBS se connecte automatiquement au WebSocket sur `ws://localhost:8766`. Le bot Python doit être démarré **avant** que la scène OBS ne soit active, sinon l'overlay tentera de se reconnecter toutes les 3 secondes (comportement normal).

---

### Ordre des sources dans la scène OBS (de bas en haut)

```
┌─────────────────────────────────┐
│  [5] Overlay HTML               │  ← au-dessus de tout
│  [4] Texte instructions haut    │
│  [3] Capture VirtualBox         │
│  [2] Texte instructions bas     │
│  [1] Fond / fond de scène       │
└─────────────────────────────────┘
```

---

## 🔁 Ordre de démarrage recommandé

1. Démarrer **VirtualBox** et la VM (ou laisser le chat envoyer `!startvm`)
2. Lancer **`python bot.py`** dans un terminal
3. Vérifier dans le terminal que le message `[WEBSOCKET] Server started on ws://localhost:8766` apparaît
4. Ouvrir **OBS** et démarrer le stream

---

## 🐛 Dépannage

| Problème | Solution |
|---|---|
| `VBoxManage: command not found` | Ajouter VirtualBox au PATH système |
| L'overlay ne se connecte pas | Vérifier que `bot.py` tourne et que le port 8766 est libre |
| Le chat ne se connecte pas | Vérifier l'`VIDEO_ID` et que le live est en cours |
| La VM ne répond pas aux touches | Vérifier que `VM_NAME` correspond exactement au nom dans VirtualBox |
| OBS ne capture pas le son de la VM | Utiliser OBS 28+ et activer "Application Audio Capture" sur la source fenêtre |
