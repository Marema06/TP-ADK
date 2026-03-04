"""
Assistant de Révision — Système multi-agents avec Google ADK.

Architecture:
  coordinator_agent (LlmAgent, root)
  ├── quiz_session_workflow  (SequentialAgent)
  │   ├── quiz_agent         (LlmAgent) — utilise evaluator_agent via AgentTool
  │   │   └── evaluator_agent (LlmAgent) — wrappé comme AgentTool
  │   └── progress_agent     (LlmAgent)
  └── preparation_workflow   (ParallelAgent)
      ├── flashcard_agent    (LlmAgent)
      └── tips_agent         (LlmAgent)

Callbacks utilisés (3 types différents parmi les 6 disponibles):
  - before_agent_callback  → log_agent_start (journalise le démarrage)
  - after_tool_callback    → log_tool_result (journalise les résultats d'outils)
  - before_tool_callback   → prevent_tool_loop (empêche les appels d'outils en double)
  - before_model_callback  → smart_router (routing déterministe du coordinateur)
"""

import logging
from typing import Any, Optional

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import AgentTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .tools.quiz_tools import generate_questions, save_quiz_result
from .tools.flashcard_tools import create_flashcard, list_flashcards
from .tools.progress_tools import get_progress_report, get_study_tips

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# Configuration du modèle
# ─────────────────────────────────────────
MODEL = "ollama/mistral"


# ═════════════════════════════════════════
# CALLBACKS (4 types différents sur les 6)
# ═════════════════════════════════════════

# --- Callback 1: before_agent_callback ---
def log_agent_start(callback_context: CallbackContext) -> Optional[types.Content]:
    """Callback déclenché AVANT chaque activation d'un agent.

    Journalise le démarrage d'un agent avec l'utilisateur courant.
    Retourne None pour laisser l'agent continuer normalement.
    """
    agent_name = callback_context.agent_name
    user_id = getattr(callback_context.session, "user_id", "inconnu")
    logger.info("[AVANT AGENT] '%s' demarre | utilisateur: %s", agent_name, user_id)
    print(f"[Agent demarre] {agent_name} | user: {user_id}")
    return None


# --- Callback 2: after_tool_callback ---
def log_tool_result(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict,
) -> Optional[dict]:
    """Callback déclenché APRÈS chaque appel d'outil réussi.

    Journalise le nom de l'outil et son statut de retour.
    Retourne None pour conserver le résultat original de l'outil.
    """
    status = tool_response.get("status", "?")
    logger.info("[APRES OUTIL] '%s' -> status: %s", tool.name, status)
    print(f"[Outil OK] {tool.name} -> {status}")
    return None


# --- Callback 3: before_tool_callback ---
def prevent_tool_loop(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> Optional[dict]:
    """Callback déclenché AVANT chaque appel d'outil — empêche les boucles.

    Utilise le state partagé pour tracker les outils déjà appelés.
    Si un outil a déjà été appelé dans cette session, retourne un
    message d'arrêt au lieu de l'exécuter à nouveau.

    Retourne None pour laisser l'outil s'exécuter normalement,
    ou un dict pour court-circuiter l'appel (le dict devient la réponse).
    """
    called_key = f"_tool_called_{tool.name}"

    if tool_context.state.get(called_key):
        logger.info("[BLOQUE] Outil '%s' deja appele, bloqué.", tool.name)
        print(f"[BLOQUE] {tool.name} deja appele")
        return {
            "status": "already_called",
            "message": f"L'outil {tool.name} a deja ete appele. Reponds maintenant a l'utilisateur avec les resultats deja obtenus. N'appelle plus aucun outil.",
        }

    # Marquer comme appelé dans le state partagé
    tool_context.state[called_key] = True
    return None  # Laisser l'outil s'exécuter


# --- Callback 4: before_model_callback ---
def smart_router(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Callback déclenché AVANT chaque appel LLM du coordinateur.

    Analyse le message de l'utilisateur et route de façon déterministe:
    - Mots-clés quiz → transfer_to_agent(quiz_session_workflow) sans appel LLM
    - Mots-clés fiches → transfer_to_agent(preparation_workflow) sans appel LLM
    - Sinon → retire les outils du LLM pour qu'il réponde en texte pur

    Ceci résout le problème des petits LLMs locaux qui hallucinent des noms
    de fonctions quand ils ont accès à des outils.
    """
    # Extraire le dernier message utilisateur
    user_msg = ""
    if llm_request.contents:
        for content in reversed(llm_request.contents):
            if content.role == "user" and content.parts:
                for part in content.parts:
                    if hasattr(part, "text") and part.text:
                        user_msg = part.text.lower()
                        break
                if user_msg:
                    break

    # Routing par mots-clés → transfer_to_agent instantané (bypass LLM)
    if any(kw in user_msg for kw in ["quiz", "qcm", "question", "teste"]):
        print(f"[Router] '{user_msg[:40]}' -> quiz_session_workflow")
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(
                    name="transfer_to_agent",
                    args={"agent_name": "quiz_session_workflow"},
                ))],
            )
        )

    if any(kw in user_msg for kw in ["fiche", "flashcard", "conseil", "revision", "prepare"]):
        print(f"[Router] '{user_msg[:40]}' -> preparation_workflow")
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(
                    name="transfer_to_agent",
                    args={"agent_name": "preparation_workflow"},
                ))],
            )
        )

    # Pas de mot-clé → retirer les outils pour réponse texte pure
    if llm_request.config and llm_request.config.tools:
        llm_request.config.tools = []

    return None  # Le LLM répond en texte


# ═════════════════════════════════════════
# AGENTS (5 LlmAgents + 2 Workflow Agents)
# ═════════════════════════════════════════

# --- Agent 1: Évaluateur (wrappé comme AgentTool) ---
evaluator_agent = LlmAgent(
    name="evaluator_agent",
    model=MODEL,
    description="Evalue la reponse d'un etudiant a une question de quiz.",
    instruction="""Tu es un évaluateur de quiz. On te donne une question et la réponse de l'étudiant.
Dis si c'est correct ou non avec une courte explication en français (2 phrases max).""",
    output_key="evaluation_result",
    before_agent_callback=log_agent_start,
)

# --- Agent 2: Quiz (utilise evaluator via AgentTool) ---
quiz_agent = LlmAgent(
    name="quiz_agent",
    model=MODEL,
    description="Genere et anime un quiz interactif sur un sujet donne.",
    instruction="""Tu es un animateur de quiz en français.

1. Appelle generate_questions avec le sujet et count=2.
2. Formule 2 questions QCM avec options A, B, C. Présente-les TOUTES d'un coup.
3. Demande à l'utilisateur de répondre (ex: "1:A 2:C"). Puis STOP.

Quand l'utilisateur donne ses réponses:
1. Utilise evaluator_agent pour évaluer.
2. Appelle save_quiz_result avec le score.

NE RÉPONDS JAMAIS à la place de l'utilisateur. Attends sa réponse.""",
    tools=[
        generate_questions,
        save_quiz_result,
        AgentTool(agent=evaluator_agent),  # ← Mécanisme AgentTool (TP contrainte 5)
    ],
    output_key="quiz_result",
    before_agent_callback=log_agent_start,
    before_tool_callback=prevent_tool_loop,  # ← Anti-boucle
    after_tool_callback=log_tool_result,
)

# --- Agent 3: Fiches de révision ---
flashcard_agent = LlmAgent(
    name="flashcard_agent",
    model=MODEL,
    description="Cree des fiches de revision (flashcards) sur un sujet donne.",
    instruction="""Tu es un créateur de fiches de révision en français.

1. Appelle create_flashcard UNE SEULE FOIS avec le concept clé du sujet.
2. Réponds en texte pour présenter la fiche créée. STOP.""",
    tools=[create_flashcard, list_flashcards],
    output_key="flashcards_result",
    before_agent_callback=log_agent_start,
    before_tool_callback=prevent_tool_loop,  # ← Anti-boucle
    after_tool_callback=log_tool_result,
)

# --- Agent 4: Progression ---
progress_agent = LlmAgent(
    name="progress_agent",
    model=MODEL,
    description="Analyse et presente la progression de l'etudiant.",
    instruction="""Tu es un coach pédagogique en français.

Résultat du dernier quiz: {quiz_result}

1. Appelle get_progress_report UNE SEULE FOIS.
2. Résume les stats en 2 lignes et donne UN conseil. STOP.""",
    tools=[get_progress_report],
    output_key="progress_report",
    before_agent_callback=log_agent_start,
    before_tool_callback=prevent_tool_loop,  # ← Anti-boucle
)

# --- Agent 5: Conseils de révision ---
tips_agent = LlmAgent(
    name="tips_agent",
    model=MODEL,
    description="Fournit des conseils et methodes de revision pour un sujet.",
    instruction="""Tu es un expert en méthodes d'apprentissage.

1. Appelle get_study_tips UNE SEULE FOIS pour le sujet.
2. Présente le conseil principal et 2 méthodes en français. STOP.""",
    tools=[get_study_tips],
    output_key="tips_result",
    before_agent_callback=log_agent_start,
    before_tool_callback=prevent_tool_loop,  # ← Anti-boucle
    after_tool_callback=log_tool_result,
)

# ═════════════════════════════════════════
# WORKFLOW AGENTS (TP contrainte 3)
# ═════════════════════════════════════════

# SequentialAgent: Quiz → puis rapport de progression
quiz_session_workflow = SequentialAgent(
    name="quiz_session_workflow",
    description="Workflow sequentiel: quiz interactif puis rapport de progression.",
    sub_agents=[quiz_agent, progress_agent],
)

# ParallelAgent: Fiches + conseils en même temps
preparation_workflow = ParallelAgent(
    name="preparation_workflow",
    description="Workflow parallele: fiches de revision ET conseils simultanement.",
    sub_agents=[flashcard_agent, tips_agent],
)

# ═════════════════════════════════════════
# AGENT ROOT — Coordinateur
# ═════════════════════════════════════════
root_agent = LlmAgent(
    name="coordinator_agent",
    model=MODEL,
    description="Coordinateur principal qui route les demandes vers les agents specialises.",
    instruction="""Tu es un assistant de révision en français. Accueille l'étudiant et propose:
1. Quiz (dis "quiz sur [sujet]")
2. Fiches de révision + conseils (dis "fiches sur [sujet]")

Demande quel sujet l'intéresse.""",
    sub_agents=[
        quiz_session_workflow,   # transfer_to_agent → SequentialAgent (TP contrainte 5)
        preparation_workflow,    # transfer_to_agent → ParallelAgent
    ],
    before_agent_callback=log_agent_start,
    before_model_callback=smart_router,  # ← Routing Python (TP contrainte 6)
)
