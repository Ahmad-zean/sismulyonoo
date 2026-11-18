import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from database import Base, engine, get_db, migrate_conversation_ownership
from models import ChatMessage, Conversation, User, utc_now
from Routers.User import get_current_user, router as user_router
from security import CSRF_COOKIE_NAME, new_csrf_token, require_header_csrf
from schema import ConversationRename, Message
from services import PASSWORD_RESET, get_request_user, verify_email_action_token

load_dotenv()

PLACEHOLDER_KEYS = {
    "your_api_key_here",
    "apikey",
    "changeme",
    "dummy",
    "test",
    "placeholder",
}

try:
    from groq import Groq
except ImportError:
    Groq = None


app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
Base.metadata.create_all(bind=engine)
migrate_conversation_ownership()
app.include_router(user_router)


def get_optional_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    return get_request_user(request, db)


def get_valid_api_key():
    raw_key = (
        os.environ.get("GROQ_API_KEY")
        or os.environ.get("SECRET_API_KEY")
        or ""
    ).strip()

    if not raw_key:
        return None
    if raw_key.lower() in {key.lower() for key in PLACEHOLDER_KEYS}:
        return None
    return raw_key


def get_client():
    api_key = get_valid_api_key()
    if not api_key or Groq is None:
        return None
    return Groq(api_key=api_key)


def get_available_model_name():
    preferred = os.environ.get("GROQ_MODEL", "").strip()
    if preferred:
        return preferred

    client = get_client()
    if client is None:
        return None

    try:
        models = client.models.list().data
        banned_keywords = [
            "whisper",
            "tts",
            "audio",
            "speech",
            "embedding",
            "playai",
            "transcription",
            "distil",
            "stt",
            "guard",
            "safeguard",
            "prompt-guard",
            "orpheus",
        ]

        preferred_order = [
            "qwen",
            "gpt-oss",
            "llama-3.3",
            "llama-3.1",
            "llama-3.2",
            "llama",
            "gemma",
            "mistral",
        ]

        choices = []
        for model in models:
            model_id = getattr(model, "id", "").strip()
            if not model_id:
                continue
            lower = model_id.lower()
            if any(keyword in lower for keyword in banned_keywords):
                continue
            if any(keyword in lower for keyword in ["qwen", "gpt", "llama", "gemma", "mistral"]):
                choices.append(model_id)

        for keyword in preferred_order:
            for model_id in choices:
                if keyword in model_id.lower():
                    return model_id

        if choices:
            return choices[0]

        return None
    except Exception:
        return None


def build_open_source_ai_response():
    return (
        "Chatbot ini menggunakan model AI berbasis open-weight/open-source melalui layanan Groq. "
        "Biasanya dipakai model Llama yang tersedia dari Groq. Jadi kalau ditanya soal AI open source "
        "yang dipakai, jawabannya adalah model Llama yang dijalankan via API key dari provider Groq."
    )


def is_open_source_question(message: str) -> bool:
    text = message.lower().strip()
    if not text:
        return False

    keywords = [
        "open source ai",
        "open-source ai",
        "ai open source",
        "model open source",
        "model yang dipakai",
        "ai yang dipakai",
        "menggunakan ai apa",
        "ai apa yang dipakai",
        "llama",
        "gemma",
        "mistral",
        "qwen",
    ]
    return any(keyword in text for keyword in keywords)


def get_bot_response(message: str, history: list[dict[str, str]] | None = None):
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    clean_message = message.strip()

    if is_open_source_question(clean_message):
        return build_open_source_ai_response()

    client = get_client()
    if client is None:
        return (
            "Maaf, API key Groq belum aktif atau belum diisi. "
            "Silakan set variabel lingkungan GROQ_API_KEY dengan key yang valid."
        )

    try:
        model_name = get_available_model_name()
        if not model_name:
            return (
                "API key Groq aktif, tetapi model yang tersedia untuk akun ini tidak dapat dipilih "
                "atau belum didukung. Silakan cek variabel GROQ_MODEL di environment Anda."
            )

        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                *(history or []),
                {"role": "user", "content": clean_message},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        return completion.choices[0].message.content
    except Exception as exc:
        return f"Maaf, terjadi kesalahan saat memproses pertanyaan Anda: {str(exc)}"


get_bot_respone = get_bot_response

@app.exception_handler(StarletteHTTPException)
def http_error_page(request: Request, exc: StarletteHTTPException):
    if request.url.path == "/chat" or request.url.path.startswith("/api/"):
        return JSONResponse(
            content={"detail": exc.detail},
            status_code=exc.status_code,
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {"title": "Error", "status_code": exc.status_code, "detail": exc.detail},
        status_code=exc.status_code,
    )


@app.get("/")
async def home(request: Request):
    response = templates.TemplateResponse(
        request,
        "index.html",
        {"request": request},
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=new_csrf_token(),
        httponly=False,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )
    return response


@app.get("/reset-password/{token}")
def reset_password_page(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    token_valid = verify_email_action_token(token, PASSWORD_RESET, db) is not None
    response = templates.TemplateResponse(
        request,
        "reset_password.html",
        {"token": token, "token_valid": token_valid},
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.post("/chat")
async def chat(
    payload: Message,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
    _: None = Depends(require_header_csrf),
):
    try:
        clean_message = payload.message.strip()
        if user is None:
            if payload.conversation_id:
                raise HTTPException(status_code=401, detail="Silakan masuk untuk membuka riwayat.")
            history = [
                {"role": turn.role, "content": turn.content}
                for turn in payload.history
            ]
            reply = get_bot_response(clean_message, history=history) or ""
            return JSONResponse(content={"response": reply, "conversation_id": None})

        conversation = None
        if payload.conversation_id:
            conversation = db.scalar(
                select(Conversation).where(
                    Conversation.id == payload.conversation_id,
                    Conversation.user_id == user.id,
                )
            )
            if conversation is None:
                raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan.")

        history = [
            {"role": message.role, "content": message.content}
            for message in conversation.messages
        ] if conversation is not None else []
        reply = get_bot_response(clean_message, history=history) or ""
        if conversation is None:
            conversation = Conversation(
                user_id=user.id,
                title=clean_message[:120] or "Percakapan baru",
            )
            db.add(conversation)
            db.flush()

        conversation.updated_at = utc_now()
        db.add_all(
            [
                ChatMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content=clean_message,
                ),
                ChatMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=reply,
                ),
            ]
        )
        db.commit()
        return JSONResponse(
            content={
                "response": reply,
                "conversation_id": conversation.id,
            }
        )
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
):
    if user is None:
        return []

    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
    ).all()
    return [
        {
            "id": conversation.id,
            "title": conversation.title,
            "updated_at": conversation.updated_at.isoformat(),
        }
        for conversation in conversations
    ]


def get_owned_conversation(
    conversation_id: str,
    user: User,
    db: Session,
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan.")
    return conversation


@app.get("/api/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = get_owned_conversation(conversation_id, user, db)

    return {
        "id": conversation.id,
        "title": conversation.title,
        "messages": [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            for message in conversation.messages
        ],
    }


@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    payload: ConversationRename,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_header_csrf),
):
    conversation = get_owned_conversation(conversation_id, user, db)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Judul percakapan tidak boleh kosong.")

    conversation.title = title
    conversation.updated_at = utc_now()
    db.commit()
    return {"id": conversation.id, "title": conversation.title}


@app.delete(
    "/api/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_header_csrf),
) -> None:
    conversation = get_owned_conversation(conversation_id, user, db)
    db.delete(conversation)
    db.commit()


@app.get("/help")
def help(request: Request):
    return templates.TemplateResponse(request, "help.html", {"request": request})



