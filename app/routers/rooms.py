from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from app.storage import load_comments, save_comment, now_iso

router = APIRouter(prefix="/rooms", tags=["rooms"])

class RoomsPostCommentRequest(BaseModel):
    comment: str
    nickname: str | None = None
    whisper: bool = False

@router.get("/{user_id}/page", response_class=HTMLResponse)
def get_page(user_id: str):
    return f"""
    <html>
        <body>
            <h1>{user_id}'s room</h1>
            <form id="form">
                <input name="nickname" placeholder="Nickname">
                <input name="comment" placeholder="Comment">
                <button type="submit">Send</button>
            </form>
            <div id="comments"></div>
            <script>
                const form = document.getElementById('form');
                const commentsDiv = document.getElementById('comments');
                async function fetchComments() {{
                    const res = await fetch(`/rooms/{user_id}/comments`);
                    const data = await res.json();
                    commentsDiv.innerHTML = data.items.map(c => `<p><b>${{c.nickname||"匿名"}}:</b> ${{c.text}}</p>`).join("");
                }}
                form.addEventListener('submit', async (e) => {{
                    e.preventDefault();
                    const formData = new FormData(form);
                    const body = {{
                        nickname: formData.get('nickname'),
                        comment: formData.get('comment'),
                        whisper: false
                    }};
                    await fetch(`/rooms/{user_id}/comments`, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(body)
                    }});
                    await fetchComments();
                    form.reset();
                }});
                fetchComments();
            </script>
        </body>
    </html>
    """

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
