from pathlib import Path
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

# ルーター読み込み
from app.routers import rooms

app = FastAPI()

# ルーター登録
app.include_router(rooms.router)

# テンプレート設定
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 動作確認用
@app.get("/")
def root():
    return {"message": "FastAPI is running!"}
