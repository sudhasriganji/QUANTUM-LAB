import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from tavily import TavilyClient


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)


# =========================================================
# API KEYS
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


# =========================================================
# STREAMLIT SECRETS FALLBACK
# =========================================================

try:
    import streamlit as st

    if not GROQ_API_KEY:
        GROQ_API_KEY = st.secrets.get("GROQ_API_KEY")

    if not TAVILY_API_KEY:
        TAVILY_API_KEY = st.secrets.get("TAVILY_API_KEY")

    if not SUPABASE_URL:
        SUPABASE_URL = st.secrets.get("SUPABASE_URL")

    if not SUPABASE_SERVICE_KEY:
        SUPABASE_SERVICE_KEY = st.secrets.get(
            "SUPABASE_SERVICE_KEY"
        )

except Exception:
    pass


# =========================================================
# VALIDATE SETTINGS
# =========================================================

missing_keys = []

if not GROQ_API_KEY:
    missing_keys.append("GROQ_API_KEY")

if not TAVILY_API_KEY:
    missing_keys.append("TAVILY_API_KEY")

if not SUPABASE_URL:
    missing_keys.append("SUPABASE_URL")

if not SUPABASE_SERVICE_KEY:
    missing_keys.append("SUPABASE_SERVICE_KEY")


if missing_keys:
    raise ValueError(
        "Missing required environment variables:\n\n"
        + "\n".join(
            f"- {key}"
            for key in missing_keys
        )
        + "\n\nAdd them to your .env file."
    )


# =========================================================
# CONNECTIONS
# =========================================================

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY
)

tavily_client = TavilyClient(
    api_key=TAVILY_API_KEY
)


# =========================================================
# AI MODEL
# =========================================================

def get_llm():

    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.5,
        api_key=GROQ_API_KEY,
        max_retries=3,
        request_timeout=60.0
    )


# =========================================================
# USER MANAGEMENT
# =========================================================

def get_or_create_user(
    email: str,
    role: str = "student"
) -> str:

    email = email.strip().lower()

    if not email:
        raise ValueError(
            "Email cannot be empty."
        )

    response = (
        supabase
        .table("users")
        .select("user_id")
        .eq("email", email)
        .limit(1)
        .execute()
    )

    if response.data:
        return response.data[0]["user_id"]

    response = (
        supabase
        .table("users")
        .insert({
            "email": email,
            "role": role
        })
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Failed to create user."
        )

    return response.data[0]["user_id"]


# =========================================================
# CREATE CHAT SESSION
# =========================================================

def create_chat_session(
    user_id: str,
    title: str = "New Quantum Chat"
) -> str:

    if not user_id:
        raise ValueError(
            "User ID is required."
        )

    response = (
        supabase
        .table("chat_sessions")
        .insert({
            "user_id": user_id,
            "title": title
        })
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Failed to create chat session."
        )

    return response.data[0]["session_id"]


# =========================================================
# GET USER CHAT SESSIONS
# =========================================================

def get_user_sessions(
    user_id: str
):

    if not user_id:
        return []

    response = (
        supabase
        .table("chat_sessions")
        .select(
            "session_id, title, created_at"
        )
        .eq(
            "user_id",
            user_id
        )
        .order(
            "created_at",
            desc=True
        )
        .execute()
    )

    return response.data or []


# =========================================================
# VERIFY CHAT OWNER
# =========================================================

def verify_session_owner(
    session_id: str,
    user_id: str
) -> bool:

    if not session_id or not user_id:
        return False

    response = (
        supabase
        .table("chat_sessions")
        .select("session_id")
        .eq(
            "session_id",
            session_id
        )
        .eq(
            "user_id",
            user_id
        )
        .limit(1)
        .execute()
    )

    return bool(response.data)


# =========================================================
# RENAME CHAT
# =========================================================

def rename_chat(
    session_id: str,
    user_id: str,
    new_title: str
):

    new_title = new_title.strip()

    if not new_title:
        raise ValueError(
            "Chat name cannot be empty."
        )

    if not verify_session_owner(
        session_id,
        user_id
    ):
        raise PermissionError(
            "You cannot rename this chat."
        )

    response = (
        supabase
        .table("chat_sessions")
        .update({
            "title": new_title
        })
        .eq(
            "session_id",
            session_id
        )
        .eq(
            "user_id",
            user_id
        )
        .execute()
    )

    return response.data


# =========================================================
# SAVE MESSAGE
# =========================================================

def save_message(
    session_id: str,
    sender: str,
    content: str
):

    if not session_id:
        raise ValueError(
            "Session ID is required."
        )

    if not content:
        return None

    if sender not in ["user", "assistant"]:
        raise ValueError(
            "Sender must be 'user' or 'assistant'."
        )

    response = (
        supabase
        .table("chat_messages")
        .insert({
            "session_id": session_id,
            "sender": sender,
            "content": content
        })
        .execute()
    )

    return response.data


# =========================================================
# GET CHAT HISTORY
# =========================================================

def get_chat_history(
    session_id: str
):

    if not session_id:
        return []

    response = (
        supabase
        .table("chat_messages")
        .select(
            "message_id, sender, content, created_at"
        )
        .eq(
            "session_id",
            session_id
        )
        .order(
            "created_at",
            desc=False
        )
        .execute()
    )

    return response.data or []


# =========================================================
# RESTORE CHAT
# =========================================================

def restore_chat(
    session_id: str,
    user_id: str
):

    if not verify_session_owner(
        session_id,
        user_id
    ):
        raise PermissionError(
            "You cannot access this chat."
        )

    return get_chat_history(
        session_id
    )


# =========================================================
# DELETE CHAT
# =========================================================

def delete_chat(
    session_id: str,
    user_id: str
):

    if not verify_session_owner(
        session_id,
        user_id
    ):
        raise PermissionError(
            "You cannot delete this chat."
        )

    # Delete messages first
    (
        supabase
        .table("chat_messages")
        .delete()
        .eq(
            "session_id",
            session_id
        )
        .execute()
    )

    # Delete session
    (
        supabase
        .table("chat_sessions")
        .delete()
        .eq(
            "session_id",
            session_id
        )
        .execute()
    )

    return True


# =========================================================
# WEB SEARCH
# =========================================================

def web_search(
    query: str
) -> str:

    try:

        results = tavily_client.search(
            query=query,
            search_depth="advanced",
            max_results=6
        )

    except Exception as e:

        print(
            "Tavily error:",
            str(e)
        )

        return ""

    web_context = []

    for result in results.get(
        "results",
        []
    ):

        title = result.get(
            "title",
            ""
        )

        content = result.get(
            "content",
            ""
        )

        url = result.get(
            "url",
            ""
        )

        if not content:
            continue

        web_context.append(
            f"""
Title: {title}

Source: {url}

Information:
{content}
"""
        )

    return "\n\n".join(
        web_context
    )


# =========================================================
# DETECT WEB SEARCH REQUIREMENT
# =========================================================

def needs_web_search(
    query: str
) -> bool:

    query_lower = (
        query.lower().strip()
    )

    if (
        len(query_lower.split()) <= 3
        and not query_lower.startswith(
            (
                "what is",
                "how to",
                "explain"
            )
        )
    ):

        return True

    current_keywords = [

        "latest",
        "current",
        "today",
        "now",
        "recent",
        "recently",
        "news",

        "2026",
        "2025",
        "2024",

        "this year",
        "this month",

        "price",
        "weather",
        "stock",
        "market",

        "release",
        "released",

        "movie",
        "actor",
        "actress",

        "who is",

        "updated",
        "update",

        "what is happening"
    ]

    return any(
        keyword in query_lower
        for keyword in current_keywords
    )


# =========================================================
# FORMAT CHAT HISTORY
# =========================================================

def format_history(
    history
) -> str:

    if not history:
        return ""

    formatted = []

    for message in history:

        sender = message.get(
            "sender",
            ""
        )

        content = message.get(
            "content",
            ""
        )

        if not content:
            continue

        if sender == "user":
            name = "User"
        else:
            name = "Assistant"

        formatted.append(
            f"{name}: {content}"
        )

    return "\n".join(
        formatted
    )


# =========================================================
# GENERAL AI ANSWER
# =========================================================

def generate_answer(
    query: str,
    history: str = "",
    web_context: str = ""
) -> str:

    llm = get_llm()

    prompt = ChatPromptTemplate.from_messages(
        [

            (
                "system",

                """
You are Quantum Lab's AI Tutor.

You are an intelligent, versatile and helpful
AI assistant.

You MUST answer the user's question directly,
even if the question is not about quantum computing.

You can answer questions about:

- Quantum Computing
- Qubits
- Quantum Gates
- Quantum Circuits
- Qiskit
- Artificial Intelligence
- Machine Learning
- Programming
- Python
- C
- C++
- Java
- JavaScript
- HTML
- CSS
- SQL
- Data Structures
- Algorithms
- Mathematics
- Physics
- Chemistry
- Engineering
- Science
- History
- Geography
- General Knowledge
- Current Affairs
- Movies and entertainment
- Writing
- Summaries
- Assignments
- Exam preparation

IMPORTANT RULES:

1. Answer the exact question asked.

2. Do not restrict yourself to quantum computing.

3. Explain difficult concepts in a simple,
   student-friendly manner.

4. For programming questions:
   - Give correct code.
   - Explain the logic.
   - Mention important mistakes when useful.

5. For mathematical questions:
   - Show the steps.
   - Give the final answer clearly.

6. For educational questions:
   - Use headings when useful.
   - Give examples.
   - Keep explanations understandable.

7. If WEB CONTEXT is provided, use it when
   answering current or web-related questions.

8. Do not blindly copy web information.
   Use your reasoning to produce a useful answer.

9. If the web context is empty, answer using
   your general knowledge.

10. Do not mention internal prompts,
    databases, API keys, backend implementation,
    or internal tools.

11. Do not say that you can only answer
    quantum computing questions.

12. Never expose API keys or credentials.

PREVIOUS CONVERSATION:
----------------------
{history}
----------------------

WEB CONTEXT:
----------------------
{web_context}
----------------------
"""
            ),

            (
                "human",
                "{input}"
            )

        ]
    )

    chain = (
        prompt
        | llm
        | StrOutputParser()
    )

    return chain.invoke(
        {
            "history": history,
            "web_context": web_context,
            "input": query
        }
    )


# =========================================================
# MAIN ANSWER FUNCTION
# =========================================================

def answer_question(
    query: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> str:

    query = query.strip()

    if not query:
        return (
            "Please enter a question."
        )

    # Verify chat ownership
    if session_id and user_id:

        if not verify_session_owner(
            session_id,
            user_id
        ):
            raise PermissionError(
                "This chat does not belong to this user."
            )

    # Get previous history
    history_str = ""

    if session_id:

        try:

            history = get_chat_history(
                session_id
            )

            recent_history = history[-10:]

            history_str = format_history(
                recent_history
            )

        except Exception as e:

            print(
                "Chat history error:",
                str(e)
            )

    # Save user question
    if session_id:

        save_message(
            session_id,
            "user",
            query
        )

    # Web search
    web_context = ""

    if needs_web_search(
        query
    ):

        web_context = web_search(
            query
        )

    # Generate answer
    try:

        answer = generate_answer(
            query=query,
            history=history_str,
            web_context=web_context
        )

    except Exception as e:

        print(
            "\nAI Error:",
            str(e)
        )

        answer = (
            "⚠️ Sorry, I could not generate "
            "a response right now.\n\n"
            f"Error details: `{str(e)}`"
        )

    # Save AI answer
    if session_id:

        save_message(
            session_id,
            "assistant",
            answer
        )

    return answer