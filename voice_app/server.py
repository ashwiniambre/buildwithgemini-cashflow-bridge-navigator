import os
import uuid
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Ensure environment variables are loaded before ADK imports
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent import get_firestore_client, root_agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

app = FastAPI(title="Cashflow Bridge Voice Navigator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    session_service=session_service,
    app_name="cashflow_bridge_voice",
)
sessions: Dict[str, Any] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    user_id = "voice_navigator_user"
    session_id = req.session_id

    if not session_id or session_id not in sessions:
        session = await session_service.create_session(
            user_id=user_id, app_name="cashflow_bridge_voice"
        )
        session_id = session.id
        sessions[session_id] = session

    user_msg = types.Content(
        role="user", parts=[types.Part.from_text(text=req.message)]
    )

    tool_calls_executed = []
    reply_text_parts = []

    async for event in runner.run_async(
        new_message=user_msg,
        user_id=user_id,
        session_id=session_id,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    reply_text_parts.append(part.text)
                if hasattr(part, "function_call") and part.function_call:
                    tool_calls_executed.append({
                        "name": part.function_call.name,
                        "args": getattr(part.function_call, "args", {}),
                    })

    full_reply = "".join(reply_text_parts).strip()

    return {
        "session_id": session_id,
        "response": full_reply,
        "tool_calls": tool_calls_executed,
    }


@app.get("/api/bills")
def get_bills():
    try:
        db = get_firestore_client()
        docs = db.collection("pending_bills").stream()
        bills = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            bills.append(d)
        bills.sort(key=lambda x: str(x.get("due_date", "")))
        return {"bills": bills}
    except Exception as e:
        return {"error": str(e), "bills": []}


static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(static_dir, "index.html"))
