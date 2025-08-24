from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, List
from app.storage import load_comments, save_comment, now_iso

router = APIRouter(prefix="/rooms", tags=["rooms"])

# --- WebSocket接続管理 ---
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

# --- REST: 既存のPOST用スキーマ ---
class RoomsPostCommentRequest(BaseModel):
    comment: str
    nickname: str | None = None
    whisper: bool = False

# --- ページ（ここにWebSocketクライアントJSを内蔵） ---
@router.get("/{user_id}/page", response_class=HTMLResponse)
def get_page(user_id: str):
    # 注意: f-string内で {user_id} だけを使い、JSの ${} は使わない
    return f"""
    <html>
        <head>
            <meta charset="utf-8" />
            <title>{user_id}'s room</title>
            <style>
              body {{ font-family: sans-serif; max-width: 680px; margin: 24px auto; }}
              #comments p {{ margin: 6px 0; }}
              .status {{ font-size: 12px; color: #666; }}
              .tag {{ font-size: 10px; padding: 2px 6px; border-radius: 6px; background: #eee; margin-left: 6px; }}
            </style>
        </head>
        <body>
            <h1>{user_id}'s room <span id="wsState" class="status">(connecting...)</span></h1>

            <form id="form">
                <input name="nickname" placeholder="Nickname" style="width: 140px;">
                <input name="comment" placeholder="Comment" style="width: 360px;">
                <label style="margin-left:8px;"><input type="checkbox" name="whisper"> whisper</label>
                <button type="submit">Send</button>
            </form>

            <div style="margin-top:8px;">
              <span class="status">presence: </span>
              <span id="presenceText" class="tag">unknown</span>
            </div>

            <h3>Comments</h3>
            <div id="comments"></div>

            <script>
                const userId = "{user_id}";
                const commentsDiv = document.getElementById('comments');
                const form = document.getElementById('form');
                const presenceText = document.getElementById('presenceText');
                const wsState = document.getElementById('wsState');

                // 初回はRESTで履歴を取得
                async function fetchComments() {{
                    const res = await fetch("/rooms/{user_id}/comments");
                    const data = await res.json();
                    commentsDiv.innerHTML = "";
                    for (const c of data.items) {{
                        const p = document.createElement("p");
                        const who = c.nickname || "匿名";
                        const tag = c.whisper ? '<span class="tag">whisper</span>' : '';
                        p.innerHTML = `<b>${{who}}:</b> ${{c.text}} ${tag}`;
                        commentsDiv.appendChild(p);
                    }}
                }}

                // WebSocket接続（http/https判定でws/wssを出し分け）
                const scheme = location.protocol === "https:" ? "wss" : "ws";
                const ws = new WebSocket(`${{scheme}}://${{location.host}}/rooms/{user_id}/ws`);

                ws.addEventListener("open", () => {{
                    wsState.textContent = "(online)";
                }});
                ws.addEventListener("close", () => {{
                    wsState.textContent = "(offline)";
                }});

                ws.addEventListener("message", (event) => {{
                    const msg = JSON.parse(event.data);
                    if (msg.type === "comment") {{
                        const p = document.createElement("p");
                        const who = msg.nickname || "匿名";
                        const tag = msg.whisper ? '<span class="tag">whisper</span>' : '';
                        p.innerHTML = `<b>${{who}}:</b> ${{msg.text}} ${tag}`;
                        commentsDiv.appendChild(p);
                        // 最新が見えるようスクロール
                        p.scrollIntoView({{ block: "end" }});
                    }} else if (msg.type === "presence") {{
                        presenceText.textContent = msg.status;
                    }}
                }});

                // 入力送信 → WSで即時配信（保存もサーバ側で行う）
                form.addEventListener('submit', (e) => {{
                    e.preventDefault();
                    const fd = new FormData(form);
                    const nickname = fd.get('nickname') || "";
                    const text = (fd.get('comment') || "").trim();
                    const whisper = !!fd.get('whisper');
                    if (!text) return;
                    ws.send(JSON.stringify({{
                        type: "comment",
                        nickname,
                        text,
                        whisper
                    }}));
                    form.reset();
                }});

                // presence（アクティビティ）送信
                let lastActivity = Date.now();
                function bump() {{ lastActivity = Date.now(); }}
                document.addEventListener("mousemove", bump);
                document.addEventListener("keydown", bump);

                setInterval(() => {{
                    const now = Date.now();
                    let status = "active";
                    if (now - lastActivity > 1800000) status = "sleep";   // 30分
                    else if (now - lastActivity > 180000) status = "idle"; // 3分
                    ws.send(JSON.stringify({{ type: "presence", status }}));
                }}, 5000);

                // 初期ロード
                fetchComments();
            </script>
        </body>
    </html>
    """

# --- コメント取得（既存） ---
@router.get("/{user_id}/comments")
def get_comments(user_id: str):
    return {"items": load_comments(user_id)}

# --- コメントPOST（既存RESTも残す。WSでも保存するので任意） ---
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

# --- WebSocketエンドポイント ---
@router.websocket("/{user_id}/ws")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await _ws_connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "comment":
                text = (data.get("text") or "").strip()
                if not text:
                    # 空は無視
                    continue
                item = {
                    "id": now_iso(),
                    "user_id": user_id,
                    "nickname": data.get("nickname"),
                    "whisper": bool(data.get("whisper", False)),
                    "text": text,
                    "created_at": now_iso(),
                }
                # 保存
                save_comment(user_id, item)
                # 全員へ配信
                await _broadcast(user_id, {
                    "type": "comment",
                    **item
                })

            elif msg_type == "presence":
                status = data.get("status") or "active"
                await _broadcast(user_id, {
                    "type": "presence",
                    "status": status,
                    "at": now_iso()
                })

            else:
                # 未知タイプは無視
                pass

    except WebSocketDisconnect:
        await _ws_disconnect(user_id, websocket)
