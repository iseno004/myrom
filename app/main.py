from pathlib import Path
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import rooms

app = FastAPI()

# ルーター登録
app.include_router(rooms.router)

# テンプレート設定
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 静的ファイルの配信 (/static でアクセス可能にする)
STATIC_DIR = Path(__file__).parent / "static"
(STATIC_DIR / "avatars").mkdir(parents=True, exist_ok=True)   # ← 追加：必ず作る
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")  # ← str() 推奨

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "FastAPI is running!"}
