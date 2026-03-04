"""
main.py — Runner programmatique de l'Assistant de Révision.

Usage:
    python main.py

Ce script instancie le Runner ADK avec InMemorySessionService
et lance une boucle interactive dans le terminal.
"""

import asyncio
import uuid

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from assistant_revision.agent import root_agent

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
APP_NAME = "assistant_revision"
USER_ID = "etudiant_01"


async def run_conversation():
    """Lance une session interactive avec l'assistant de révision."""

    # 1. Créer le service de sessions en mémoire
    session_service = InMemorySessionService()

    # 2. Créer une session unique pour cet utilisateur
    session_id = str(uuid.uuid4())
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
    )
    print(f"✅ Session créée: {session_id[:8]}...")

    # 3. Instancier le Runner avec l'agent root et le service de sessions
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    print("\n" + "=" * 60)
    print("📚 Assistant de Révision — Multi-Agents ADK")
    print("=" * 60)
    print("Tape 'exit' ou 'quit' pour quitter.\n")

    # 4. Boucle de conversation interactive
    while True:
        try:
            user_input = input("Toi: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nAu revoir!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Au revoir! Bonne révision! 🎓")
            break

        # Construire le message utilisateur au format ADK
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=user_input)],
        )

        # Envoyer au runner et collecter la réponse
        print("\nAssistant: ", end="", flush=True)
        final_response = ""

        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=user_message,
        ):
            # Extraire le texte des événements de réponse
            if event.is_final_response():
                if event.content and event.content.parts:
                    final_response = "".join(
                        p.text for p in event.content.parts if hasattr(p, "text") and p.text
                    )

        print(final_response if final_response else "[Pas de réponse]")
        print()


def main():
    """Point d'entrée principal."""
    asyncio.run(run_conversation())


if __name__ == "__main__":
    main()
