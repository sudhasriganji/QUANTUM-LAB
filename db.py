import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client

from langchain_community.vectorstores import SupabaseVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.documents import Document


# ============================================================
# AI TUTOR - RAG BACKEND
# Multiple Users + Chat Restoration + RAG
# ============================================================

print("=" * 60)
print("                 AI TUTOR - RAG BACKEND")
print("=" * 60)


# ============================================================
# STEP 0: LOAD ENVIRONMENT VARIABLES
# ============================================================

env_path = Path(__file__).resolve().parent / ".env"

load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
)


# ============================================================
# CHECK ENVIRONMENT VARIABLES
# ============================================================

if not SUPABASE_URL:
    raise ValueError(
        f"SUPABASE_URL is missing from {env_path}"
    )

if not SUPABASE_KEY:
    raise ValueError(
        f"SUPABASE_SERVICE_KEY is missing from {env_path}"
    )

if not GEMINI_API_KEY:
    raise ValueError(
        f"GEMINI_API_KEY or GOOGLE_API_KEY is missing from {env_path}"
    )


# ============================================================
# STEP 1: CONNECT TO SUPABASE
# ============================================================

print("\nConnecting to Supabase...")

try:

    supabase: Client = create_client(
        SUPABASE_URL,
        SUPABASE_KEY
    )

    print("Supabase connected successfully.")

except Exception as e:

    print("\nSupabase connection failed:")
    print(str(e))

    raise


# ============================================================
# STEP 2: LOAD EMBEDDING MODEL
# ============================================================

print("\nLoading embedding model...")

try:

    embeddings = HuggingFaceEmbeddings(
        model_name="all-MiniLM-L6-v2"
    )

    print("Embedding model loaded successfully.")

except Exception as e:

    print("\nEmbedding model failed to load:")
    print(str(e))

    raise


# ============================================================
# STEP 3: INITIALIZE GEMINI
# ============================================================

print("\nInitializing Gemini...")

try:

    llm = ChatGoogleGenerativeAI(
        model="gemini-3.6-flash",
        google_api_key=GEMINI_API_KEY
    )

    print("Gemini initialized successfully.")

except Exception as e:

    print("\nGemini initialization failed:")
    print(str(e))

    raise


# ============================================================
# STEP 4: USER MANAGEMENT
# ============================================================

def get_or_create_user(
    email: str,
    role: str = "student"
) -> str:

    """
    Find an existing user using email.

    If the user doesn't exist, create one.

    Returns:
        user_id as string
    """

    try:

        response = (
            supabase
            .table("users")
            .select("user_id")
            .eq("email", email)
            .limit(1)
            .execute()
        )

    except Exception as e:

        raise RuntimeError(
            f"Failed to find user: {e}"
        )

    if response.data:

        return str(
            response.data[0]["user_id"]
        )


    # --------------------------------------------------------
    # CREATE USER
    # --------------------------------------------------------

    try:

        response = (
            supabase
            .table("users")
            .insert({
                "email": email,
                "role": role
            })
            .execute()
        )

    except Exception as e:

        raise RuntimeError(
            f"Failed to create user: {e}"
        )

    if not response.data:

        raise RuntimeError(
            "Failed to create user. No data returned."
        )

    return str(
        response.data[0]["user_id"]
    )


# ============================================================
# STEP 5: CREATE NEW CHAT SESSION
# ============================================================

def create_chat_session(
    user_id: str,
    title: str = "AI Tutor Session"
) -> str:

    """
    Create a new chat session for a specific user.

    Returns:
        session_id
    """

    try:

        response = (
            supabase
            .table("chat_sessions")
            .insert({
                "user_id": user_id,
                "title": title
            })
            .execute()
        )

    except Exception as e:

        raise RuntimeError(
            f"Failed to create chat session: {e}"
        )

    if not response.data:

        raise RuntimeError(
            "Failed to create chat session. "
            "No data returned."
        )

    return str(
        response.data[0]["session_id"]
    )


# ============================================================
# STEP 6: GET ALL CHATS FOR A USER
# ============================================================

def get_user_sessions(user_id: str):

    response = (
        supabase
        .table("chat_sessions")
        .select(
            "session_id, title, created_at"
        )
        .eq("user_id", user_id)
        .order(
            "created_at",
            desc=True
        )
        .execute()
    )

    return response.data or []


# ============================================================
# STEP 7: SAVE MESSAGE
# ============================================================

def save_message(
    session_id: str,
    sender: str,
    content: str
):

    """
    Save one message.

    sender:
        user
        assistant
    """

    if not content:

        return []

    try:

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

    except Exception as e:

        raise RuntimeError(
            f"Failed to save message: {e}"
        )

    return response.data or []


# ============================================================
# STEP 8: GET CHAT HISTORY
# ============================================================

def get_chat_history(
    session_id: str
):

    """
    Restore all messages for a chat session.
    """

    try:

        response = (
            supabase
            .table("chat_messages")
            .select(
                "message_id, sender, content, created_at"
            )
            .eq("session_id", session_id)
            .order(
                "created_at",
                desc=False
            )
            .execute()
        )

    except Exception as e:

        raise RuntimeError(
            f"Failed to retrieve chat history: {e}"
        )

    return response.data or []


# ============================================================
# STEP 9: VERIFY CHAT BELONGS TO USER
# ============================================================

def verify_session_owner(
    session_id: str,
    user_id: str
) -> bool:

    """
    Security check.

    Makes sure a user cannot access
    another user's chat session.
    """

    try:

        response = (
            supabase
            .table("chat_sessions")
            .select("session_id")
            .eq("session_id", session_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

    except Exception as e:

        print(
            f"\nSession ownership check failed: {e}"
        )

        return False

    return bool(response.data)


# ============================================================
# STEP 10: GET VECTOR STORE
# ============================================================

def get_vectorstore():

    """
    Connect to the existing pgvector knowledge base.

    Table:
        document_chunks

    RPC:
        match_documents
    """

    return SupabaseVectorStore(
        client=supabase,
        embedding=embeddings,
        table_name="document_chunks",
        query_name="match_documents"
    )


# ============================================================
# STEP 11: TEST VECTOR DATABASE
# ============================================================

def test_vector_database():

    """
    Test whether the pgvector table and
    match_documents function are working.
    """

    print("\nTesting pgvector knowledge base...")

    try:

        vectorstore = get_vectorstore()

        results = vectorstore.similarity_search(
            "Pythagorean Theorem",
            k=2
        )

        if results:

            print(
                f"Vector search successful. "
                f"Found {len(results)} document(s)."
            )

            for i, doc in enumerate(
                results,
                start=1
            ):

                print(
                    f"\nDocument {i}:"
                )

                print(
                    doc.page_content[:200]
                )

            return True

        print(
            "Vector database is connected, "
            "but no documents were found."
        )

        return False

    except Exception as e:

        print(
            "\nVector database test failed:"
        )

        print(str(e))

        return False


# ============================================================
# STEP 12: SEED KNOWLEDGE BASE
# ============================================================

def seed_knowledge_base():

    """
    Add sample documents to the vector database.

    Run this only when you need to add documents.
    """

    docs = [

        Document(
            page_content=(
                "Pythagorean Theorem: "
                "In a right-angled triangle, "
                "a² + b² = c², "
                "where c is the hypotenuse."
            ),
            metadata={
                "subject": "Math",
                "grade": 8
            }
        ),

        Document(
            page_content=(
                "Newton's First Law of Motion: "
                "An object remains at rest or in uniform motion "
                "unless acted upon by a net external force. "
                "This law is also called the Law of Inertia."
            ),
            metadata={
                "subject": "Physics",
                "grade": 9
            }
        ),

        Document(
            page_content=(
                "Quick Sort is a sorting algorithm. "
                "Its average time complexity is O(n log n), "
                "while its worst-case time complexity is O(n²)."
            ),
            metadata={
                "subject": "Data Structures"
            }
        )
    ]


    try:

        SupabaseVectorStore.from_documents(
            docs,
            embeddings,
            client=supabase,
            table_name="document_chunks",
            query_name="match_documents"
        )

        print(
            "Knowledge base seeded successfully!"
        )

    except Exception as e:

        print(
            "\nKnowledge base seeding failed:"
        )

        print(str(e))

        raise


# ============================================================
# STEP 13: EXTRACT GEMINI RESPONSE
# ============================================================

def extract_response_text(
    response
) -> str:

    """
    Convert Gemini response into plain text.
    """

    content = response.content

    if isinstance(content, str):

        return content.strip()


    if isinstance(content, list):

        text_parts = []

        for item in content:

            if isinstance(item, dict):

                if item.get("type") == "text":

                    text_parts.append(
                        item.get("text", "")
                    )

                elif "text" in item:

                    text_parts.append(
                        str(item["text"])
                    )

            elif isinstance(item, str):

                text_parts.append(item)


        return "\n".join(
            text_parts
        ).strip()


    return str(content).strip()


# ============================================================
# STEP 14: AI TUTOR RAG
# ============================================================

def ask_ai_tutor(
    session_id: str,
    query: str,
    user_id: str | None = None
) -> str:

    """
    Main AI Tutor pipeline.

    1. Verify user ownership
    2. Save user question
    3. Search knowledge base
    4. Get chat history
    5. Generate Gemini response
    6. Save AI response
    7. Return answer
    """

    if not query or not query.strip():

        return (
            "Please enter a question."
        )


    query = query.strip()


    # ========================================================
    # SECURITY CHECK
    # ========================================================

    if user_id is not None:

        if not verify_session_owner(
            session_id,
            user_id
        ):

            raise PermissionError(
                "This chat does not belong to this user."
            )


    # ========================================================
    # SAVE USER QUESTION
    # ========================================================

    save_message(
        session_id,
        "user",
        query
    )


    # ========================================================
    # VECTOR SEARCH
    # ========================================================

    context = (
        "No relevant information was found "
        "in the knowledge base."
    )

    try:

        vectorstore = get_vectorstore()

        retrieved_docs = (
            vectorstore.similarity_search(
                query,
                k=2
            )
        )


        if retrieved_docs:

            context = "\n\n".join(
                doc.page_content
                for doc in retrieved_docs
            )

    except Exception as e:

        print(
            "\nVector Search Error:"
        )

        print(str(e))

        print(
            "Continuing with Gemini general knowledge."
        )


    # ========================================================
    # GET PREVIOUS CHAT HISTORY
    # ========================================================

    history = get_chat_history(
        session_id
    )

    # Last 6 messages
    recent_history = history[-6:]


    if recent_history:

        history_str = "\n".join(
            f"{message['sender']}: "
            f"{message['content']}"
            for message in recent_history
        )

    else:

        history_str = (
            "No previous conversation."
        )


    # ========================================================
    # CREATE PROMPT
    # ========================================================

    prompt = f"""
You are an AI Tutor.

Help students understand academic concepts
clearly, accurately, and step-by-step.

Use the Context as the primary source when relevant.

Use the Chat History to understand follow-up questions.

If the Context does not contain enough information,
you may use your general knowledge.

Keep explanations student-friendly.

For mathematics:
- Explain formulas clearly.
- Show the steps.
- Give examples when useful.

For physics:
- Explain concepts simply.
- Give everyday examples when useful.
- Explain important formulas.

For programming:
- Explain concepts step-by-step.
- Give code only when requested.
- Keep code beginner-friendly.

Do not mention:
- RAG
- embeddings
- vector database
- Supabase
- internal implementation

to the student.

============================================================
CONTEXT
============================================================

{context}

============================================================
CHAT HISTORY
============================================================

{history_str}

============================================================
STUDENT QUESTION
============================================================

{query}

============================================================
ANSWER
============================================================
"""


    # ========================================================
    # CALL GEMINI
    # ========================================================

    try:

        response = llm.invoke(
            prompt
        )

        answer = extract_response_text(
            response
        )


        if not answer:

            answer = (
                "I could not generate an answer. "
                "Please try again."
            )


    except Exception as e:

        print(
            "\nGemini API Error:"
        )

        print(str(e))

        answer = (
            "Sorry, I could not generate a response "
            "right now. Please try again."
        )


    # ========================================================
    # SAVE AI RESPONSE
    # ========================================================

    try:

        save_message(
            session_id,
            "assistant",
            answer
        )

    except Exception as e:

        print(
            "\nWarning: AI response could not be saved:"
        )

        print(str(e))


    return answer


# ============================================================
# STEP 15: RESTORE CHAT
# ============================================================

def restore_chat(
    session_id: str,
    user_id: str | None = None
):

    """
    Restore a previous chat.

    Optional user_id is used to verify ownership.
    """

    if user_id is not None:

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


# ============================================================
# STEP 16: DELETE CHAT
# ============================================================

def delete_chat(
    session_id: str,
    user_id: str
):

    """
    Delete a chat only if it belongs to the user.
    """

    if not verify_session_owner(
        session_id,
        user_id
    ):

        raise PermissionError(
            "You cannot delete this chat."
        )


    try:

        # Delete messages first
        supabase.table(
            "chat_messages"
        ).delete().eq(
            "session_id",
            session_id
        ).execute()


        # Delete session
        supabase.table(
            "chat_sessions"
        ).delete().eq(
            "session_id",
            session_id
        ).execute()


    except Exception as e:

        raise RuntimeError(
            f"Failed to delete chat: {e}"
        )


    return True


# ============================================================
# STEP 17: TEST BACKEND
# ============================================================

if __name__ == "__main__":

    print("\n")

    print("=" * 60)
    print("                  AI TUTOR TEST")
    print("=" * 60)


    # ========================================================
    # CREATE / RETRIEVE TEST USER
    # ========================================================

    try:

        user_id = get_or_create_user(
            email="student1@example.com",
            role="student"
        )

        print(
            f"\nUser ID: {user_id}"
        )

    except Exception as e:

        print(
            "\nUser operation failed:"
        )

        print(str(e))

        raise


    # ========================================================
    # DISPLAY PREVIOUS CHATS
    # ========================================================

    try:

        sessions = get_user_sessions(
            user_id
        )

        print(
            "\nPrevious Chat Sessions:"
        )


        if sessions:

            for session in sessions:

                print(
                    f"- {session['session_id']} | "
                    f"{session['title']} | "
                    f"{session['created_at']}"
                )

        else:

            print(
                "No previous chats found."
            )

    except Exception as e:

        print(
            "\nCould not load previous chats:"
        )

        print(str(e))

        raise


    # ========================================================
    # CREATE NEW CHAT
    # ========================================================

    try:

        session_id = create_chat_session(
            user_id=user_id,
            title="Physics & Math Prep"
        )

        print(
            f"\nNew Chat Session ID: {session_id}"
        )

    except Exception as e:

        print(
            "\nChat session creation failed:"
        )

        print(str(e))

        raise


    # ========================================================
    # TEST VECTOR DATABASE
    # ========================================================

    print("\n")

    vector_ok = test_vector_database()


    # ========================================================
    # TEST QUESTION 1
    # ========================================================

    q1 = "What is the Pythagorean Theorem?"

    print(
        "\n" + "=" * 60
    )

    print(
        f"User: {q1}"
    )

    print(
        "-" * 60
    )


    answer1 = ask_ai_tutor(
        session_id=session_id,
        query=q1,
        user_id=user_id
    )


    print(
        "AI:"
    )

    print(
        answer1
    )


    # ========================================================
    # TEST QUESTION 2
    # ========================================================

    q2 = "What about Newton's First Law?"

    print(
        "\n" + "=" * 60
    )

    print(
        f"User: {q2}"
    )

    print(
        "-" * 60
    )


    answer2 = ask_ai_tutor(
        session_id=session_id,
        query=q2,
        user_id=user_id
    )


    print(
        "AI:"
    )

    print(
        answer2
    )


    # ========================================================
    # RESTORE CHAT
    # ========================================================

    print(
        "\n" + "=" * 60
    )

    print(
        "                  RESTORED CHAT"
    )

    print(
        "=" * 60
    )


    restored_history = restore_chat(
        session_id=session_id,
        user_id=user_id
    )


    for message in restored_history:

        print(
            f"{message['sender']}: "
            f"{message['content']}"
        )


    # ========================================================
    # COMPLETED
    # ========================================================

    print(
        "\n" + "=" * 60
    )

    print(
        "                 AI TUTOR TEST COMPLETED"
    )

    print(
        "=" * 60
    )