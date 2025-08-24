from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, List
from app.storage import load_comments, save_comment, now_iso

router = APIRouter(prefix="/rooms", tags=["rooms"])

# WebSocket接続プール
active_connections: Dict[str, List[WebSocket]] = {}

async def _ws_connect(user_id: str, websocket: WebSocket):
    await websocket.accept()
    active_connections.setdefault(user_id, []).append(websocket)

async def _ws_disconnect(user_id: str, websocket: WebSocket):
    conns = active_connections.get(user_id, [])
    if websocket in conns:
        conns.remove(websocket)
    if not conns and user_id in active_connections:
        del active_connections[user_id]

async def _broadcast(user_id: str, payload: dict):
    for ws in active_connections.get(user_id, []):
        await ws.send_json(payload)

class RoomsPostCommentRequest(BaseModel):
    comment: str
    nickname: str | None = None
    whisper: bool = False

# HTMLテンプレ（__USER__ を置換）
_HTML = """
<html>
  <head>
    <meta charset="utf-8" />
    <title>__USER__'s room</title>
    <style>
      body{ font-family: system-ui, sans-serif; max-width:760px; margin:24px auto; }
      h1{ margin-bottom:8px; }
      .status{ font-size:12px; color:#666; }
      #avatarWrap{ margin:12px 0; }
      #avatar{ width:200px; height:200px; object-fit:contain; }
      .tag{ font-size:10px; padding:2px 6px; border-radius:6px; background:#eee; margin-left:6px; }
    </style>
  </head>
  <body>
    <h1>__USER__'s room <span id="wsState" class="status">(connecting...)</span></h1>

    <div id="avatarWrap">
      <img id="avatar" src="/static/avatars/active.png" alt="avatar">
      <div class="status">presence: <span id="presenceText" class="tag">active</span></div>
    </div>

    <form id="form">
      <input name="nickname" placeholder="Nickname" />
      <input name="comment" placeholder="Comment" style="width:300px;" />
      <label><input type="checkbox" name="whisper" /> whisper</label>
      <button type="submit">Send</button>
    </form>

    <h3>Comments</h3>
    <div id="comments"></div>

    <script>
      const userId = "__USER__";
      const commentsDiv = document.getElementById('comments');
      const form = document.getElementById('form');
      const presenceText = document.getElementById('presenceText');
      const wsState = document.getElementById('wsState');
      const avatar = document.getElementById('avatar');

      const avatarImgs = {
        active: "/static/avatars/active.png",
        idle: "/static/avatars/idle.png",
        sleep: "/static/avatars/sleep.png"
      };

      // 履歴取得
      async function fetchComments(){
        const res = await fetch("/rooms/__USER__/comments");
        const data = await res.json();
        commentsDiv.innerHTML = "";
        for(const c of data.items){
          const who = c.nickname || "匿名";
          const tag = c.whisper ? '<span class="tag">whisper</span>' : '';
          const p = document.createElement("p");
          p.innerHTML = `<b>${who}:</b> ${c.text} ${tag}`;
          commentsDiv.appendChild(p);
        }
      }

      // WS接続
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${scheme}://${location.host}/rooms/__USER__/ws`);
      ws.addEventListener("open", ()=> wsState.textContent="(online)");
      ws.addEventListener("close", ()=> wsState.textContent="(offline)");

      ws.addEventListener("message", (ev)=>{
        const msg = JSON.parse(ev.data);
        if(msg.type==="comment"){
          const p = document.createElement("p");
          const who = msg.nickname || "匿名";
          const tag = msg.whisper ? '<span class="tag">whisper</span>' : '';
          p.innerHTML = `<b>${who}:</b> ${msg.text} ${tag}`;
          commentsDiv.appendChild(p);
          p.scrollIntoView({block:"end"});
        }else if(msg.type==="presence"){
          setPresence(msg.status);
        }
      });

      // presence送信
      let lastActivity = Date.now();
      const bump = ()=> lastActivity = Date.now();
      document.addEventListener("mousemove", bump);
      document.addEventListener("keydown", bump);

      setInterval(()=>{
        const now = Date.now();
        let status = "active";
        if(now - lastActivity > 1800000) status = "sleep";
        else if(now - lastActivity > 180000) status = "idle";
        ws.send(JSON.stringify({ type:"presence", status }));
        setPresence(status);
      }, 5000);

      function setPresence(status){
        presenceText.textContent = status;
        avatar.src = avatarImgs[status] || avatarImgs["active"];
      }

      fetchComments();
    </script>
  </body>
</html>
"""

@router.get("/{user_id}/page", response_class=HTMLResponse)
def get_page(user_id: str):
    return HTMLResponse(_HTML.replace("__USER__", user_id))

@router.get("/{user_id}/comments")
def get_comments(user_id: str):
    return {"items": load_comments(user_id)}

@router.post("/{user_id}/comments")
def post_comment(user_id: str, body: RoomsPostCommentRequest):
    text = (body.comment or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="comment required")
    item = {
        "id": now_iso(),
        "user_id": user_id,
        "nickname": body.nickname,
        "whisper": body.whisper,
        "text": text,
        "created_at": now_iso(),
    }
    return save_comment(user_id, item)

@router.websocket("/{user_id}/ws")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await _ws_connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            t = data.get("type")
            if t == "comment":
                text = (data.get("text") or "").strip()
                if not text: continue
                item = {
                    "id": now_iso(),
                    "user_id": user_id,
                    "nickname": data.get("nickname"),
                    "whisper": bool(data.get("whisper", False)),
                    "text": text,
                    "created_at": now_iso(),
                }
                save_comment(user_id, item)
                await _broadcast(user_id, {"type":"comment", **item})
            elif t == "presence":
                status = data.get("status") or "active"
                await _broadcast(user_id, {"type":"presence","status":status,"at":now_iso()})
    except WebSocketDisconnect:
        await _ws_disconnect(user_id, websocket)
        
