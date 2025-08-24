from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List

# 既存コードの上に追加
active_connections: Dict[str, List[WebSocket]] = {}

async def connect_ws(user_id: str, websocket: WebSocket):
    await websocket.accept()
    if user_id not in active_connections:
        active_connections[user_id] = []
    active_connections[user_id].append(websocket)

async def disconnect_ws(user_id: str, websocket: WebSocket):
    if user_id in active_connections:
        active_connections[user_id].remove(websocket)
        if not active_connections[user_id]:
            del active_connections[user_id]

async def broadcast(user_id: str, message: dict):
    if user_id in active_connections:
        for ws in active_connections[user_id]:
            await ws.send_json(message)

@router.websocket("/{user_id}/ws")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await connect_ws(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await broadcast(user_id, data)
    except WebSocketDisconnect:
        await disconnect_ws(user_id, websocket)
