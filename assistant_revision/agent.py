"""
Assistant de Revision — Systeme multi-agents avec Google ADK.

Architecture:
  coordinator_agent (LlmAgent, root)
  ├── quiz_session_workflow    (SequentialAgent)
  │   ├── quiz_agent           (LlmAgent) — utilise evaluator_agent via AgentTool
  │   │   └── evaluator_agent  (LlmAgent) — wrappe comme AgentTool
  │   └── progress_agent       (LlmAgent)
  ├── preparation_workflow     (ParallelAgent)
  │   ├── flashcard_agent      (LlmAgent)
  │   └── tips_agent           (LlmAgent)
  └── flashcard_loop_workflow  (LoopAgent, max 2 iterations)
      ├── loop_flashcard_agent     (LlmAgent)
      └── flashcard_checker_agent  (LlmAgent)

Callbacks utilises (5 types differents parmi les 6 disponibles):
  - before_agent_callback  → log_agent_start (journalise le demarrage)
  - after_agent_callback   → log_agent_end (journalise la fin)
  - before_tool_callback   → prevent_tool_loop (empeche les appels d'outils en double)
  - after_tool_callback    → log_tool_result (journalise les resultats d'outils)
  - before_model_callback  → smart_router / strip_tools_after_use
"""

import logging
from typing import Any, Optional

from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
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
# Configuration du modele
# ─────────────────────────────────────────
MODEL = "ollama/mistral"


# ═════════════════════════════════════════
# CALLBACKS (5 types differents sur les 6)
# ═════════════════════════════════════════

# --- Callback 1: before_agent_callback ---
def log_agent_start(callback_context: CallbackContext) -> Optional[types.Content]:
    """Callback declenche AVANT chaque activation d'un agent.

    Journalise le demarrage d'un agent avec l'utilisateur courant.
    Retourne None pour laisser l'agent continuer normalement.
    """
    agent_name = callback_context.agent_name
    user_id = getattr(callback_context.session, "user_id", "inconnu")
    logger.info("[AVANT AGENT] '%s' demarre | utilisateur: %s", agent_name, user_id)
    print(f"[Agent demarre] {agent_name} | user: {user_id}")
    return None


# --- Callback 2: after_agent_callback ---
def log_agent_end(callback_context: CallbackContext) -> Optional[types.Content]:
    """Callback declenche APRES la fin d'un agent.

    Journalise la fin d'execution d'un agent.
    Retourne None pour laisser le resultat inchange.
    """
    agent_name = callback_context.agent_name
    logger.info("[APRES AGENT] '%s' a termine", agent_name)
    print(f"[Agent termine] {agent_name}")
    return None


# --- Callback 3: after_tool_callback ---
def log_tool_result(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict,
) -> Optional[dict]:
    """Callback declenche APRES chaque appel d'outil reussi.

    Journalise le nom de l'outil et son statut de retour.
    Retourne None pour conserver le resultat original de l'outil.
    """
    if isinstance(tool_response, dict):
        status = tool_response.get("status", "ok")
    else:
        status = "ok"
    logger.info("[APRES OUTIL] '%s' -> status: %s", tool.name, status)
    print(f"[Outil OK] {tool.name} -> {status}")
    return None


# --- Callback 4: before_tool_callback ---
def prevent_tool_loop(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> Optional[dict]:
    """Callback declenche AVANT chaque appel d'outil — empeche les boucles.

    Utilise le state partage pour tracker les outils deja appeles.
    Si un outil a deja ete appele dans cette session, retourne un
    message d'arret au lieu de l'executer a nouveau.

    Retourne None pour laisser l'outil s'executer normalement,
    ou un dict pour court-circuiter l'appel (le dict devient la reponse).
    """
    called_key = f"_tool_called_{tool.name}"

    if tool_context.state.get(called_key):
        logger.info("[BLOQUE] Outil '%s' deja appele, bloque.", tool.name)
        print(f"[BLOQUE] {tool.name} deja appele")
        return {
            "status": "deja_fait",
            "resultat": f"STOP. L'outil {tool.name} a deja ete execute avec succes. Tu as deja les resultats. Presente-les maintenant a l'utilisateur en texte. NE RAPPELLE AUCUN OUTIL.",
        }

    # Marquer comme appele dans le state partage
    tool_context.state[called_key] = True
    tool_context.state["_any_tool_called"] = True
    return None  # Laisser l'outil s'executer


# --- Callback 5: before_model_callback (coordinateur) ---
def smart_router(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Callback declenche AVANT chaque appel LLM du coordinateur.

    Analyse le message de l'utilisateur et route de facon deterministe:
    - Mots-cles quiz -> transfer_to_agent(quiz_session_workflow) sans appel LLM
    - Mots-cles fiches -> transfer_to_agent(flashcard_loop_workflow) sans appel LLM
    - Mots-cles revision -> transfer_to_agent(preparation_workflow) sans appel LLM
    - Sinon -> retire les outils du LLM pour qu'il reponde en texte pur

    Ceci resout le probleme des petits LLMs locaux qui hallucinent des noms
    de fonctions quand ils ont acces a des outils.
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

    # Routing par mots-cles -> transfer_to_agent instantane (bypass LLM)
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

    if any(kw in user_msg for kw in ["fiche", "flashcard", "carte"]):
        print(f"[Router] '{user_msg[:40]}' -> flashcard_loop_workflow")
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(
                    name="transfer_to_agent",
                    args={"agent_name": "flashcard_loop_workflow"},
                ))],
            )
        )

    if any(kw in user_msg for kw in ["conseil", "revision", "prepare", "methode"]):
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

    # Pas de mot-cle -> retirer les outils pour reponse texte pure
    if llm_request.config and llm_request.config.tools:
        llm_request.config.tools = []

    return None  # Le LLM repond en texte


# --- Callback 6: before_model_callback (agents enfants) ---
def strip_tools_after_use(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Retire les outils du LLM apres le premier appel d'outil reussi.

    Verifie dans le state si un outil a deja ete appele (via _any_tool_called).
    Si oui, retire tous les outils pour forcer une reponse en texte.
    Ceci empeche Mistral d'halluciner des noms d'outils inexistants.
    """
    any_tool_called = callback_context.state.get("_any_tool_called", False)
    if any_tool_called and llm_request.config and llm_request.config.tools:
        print(f"[StripTools] {callback_context.agent_name}: outils retires, reponse texte forcee")
        llm_request.config.tools = []
    return None


# ═════════════════════════════════════════
# AGENTS (8 LlmAgents + 3 Workflow Agents)
# ═════════════════════════════════════════

# --- Agent 1: Evaluateur (wrappe comme AgentTool) ---
evaluator_agent = LlmAgent(
    name="evaluator_agent",
    model=MODEL,
    description="Evalue la reponse d'un etudiant a une question de quiz.",
    instruction="""Tu es un evaluateur de quiz. On te donne une question et la reponse de l'etudiant.
Dis si c'est correct ou non avec une courte explication en francais (2 phrases max).""",
    output_key="evaluation_result",
    before_agent_callback=log_agent_start,
    after_agent_callback=log_agent_end,
)

# --- Agent 2: Quiz (utilise evaluator via AgentTool) ---
quiz_agent = LlmAgent(
    name="quiz_agent",
    model=MODEL,
    description="Genere et anime un quiz interactif sur un sujet donne.",
    instruction="""Tu es un animateur de quiz en francais.

ETAPE 1: Appelle generate_questions UNE SEULE FOIS avec le sujet et count=2.
ETAPE 2: Avec le resultat obtenu, formule 2 questions QCM avec options A, B, C.
ETAPE 3: Presente les questions a l'utilisateur et demande ses reponses. STOP.

IMPORTANT: N'appelle generate_questions qu'UNE SEULE FOIS. Apres avoir recu le resultat, ecris les questions en TEXTE. Ne rappelle AUCUN outil.

Quand l'utilisateur donne ses reponses plus tard:
1. Utilise evaluator_agent pour evaluer.
2. Appelle save_quiz_result avec le score.""",
    tools=[
        generate_questions,
        save_quiz_result,
        AgentTool(agent=evaluator_agent),  # Mecanisme AgentTool (TP contrainte 5)
    ],
    output_key="quiz_result",
    before_agent_callback=log_agent_start,
    before_model_callback=strip_tools_after_use,  # Force texte apres 1er outil
    before_tool_callback=prevent_tool_loop,  # Anti-boucle
    after_tool_callback=log_tool_result,
)

# --- Agent 3: Fiches de revision ---
flashcard_agent = LlmAgent(
    name="flashcard_agent",
    model=MODEL,
    description="Cree des fiches de revision (flashcards) sur un sujet donne.",
    instruction="""Tu es un createur de fiches de revision en francais.

1. Appelle create_flashcard UNE SEULE FOIS avec le concept cle du sujet.
2. Reponds en texte pour presenter la fiche creee. STOP.""",
    tools=[create_flashcard, list_flashcards],
    output_key="flashcards_result",
    before_agent_callback=log_agent_start,
    before_model_callback=strip_tools_after_use,  # Force texte apres 1er outil
    before_tool_callback=prevent_tool_loop,  # Anti-boucle
    after_tool_callback=log_tool_result,
)

# --- Agent 4: Progression ---
progress_agent = LlmAgent(
    name="progress_agent",
    model=MODEL,
    description="Analyse et presente la progression de l'etudiant.",
    instruction="""Tu es un coach pedagogique en francais.

Resultat du dernier quiz: {quiz_result}

Tu as UN SEUL outil disponible. Son nom EXACT est: get_progress_report
N'invente AUCUN autre nom d'outil. N'utilise PAS present_progress_report ni aucun autre nom.

1. Appelle get_progress_report() UNE SEULE FOIS (sans arguments).
2. Resume les stats en 2 lignes et donne UN conseil. STOP.""",
    tools=[get_progress_report],
    output_key="progress_report",
    before_agent_callback=log_agent_start,
    before_model_callback=strip_tools_after_use,  # Force texte apres 1er outil
    before_tool_callback=prevent_tool_loop,  # Anti-boucle
    after_tool_callback=log_tool_result,
)

# --- Agent 5: Conseils de revision ---
tips_agent = LlmAgent(
    name="tips_agent",
    model=MODEL,
    description="Fournit des conseils et methodes de revision pour un sujet.",
    instruction="""Tu es un expert en methodes d'apprentissage.

1. Appelle get_study_tips UNE SEULE FOIS pour le sujet.
2. Presente le conseil principal et 2 methodes en francais. STOP.""",
    tools=[get_study_tips],
    output_key="tips_result",
    before_agent_callback=log_agent_start,
    before_model_callback=strip_tools_after_use,  # Force texte apres 1er outil
    before_tool_callback=prevent_tool_loop,  # Anti-boucle
    after_tool_callback=log_tool_result,
)

# --- Agent 6: Createur de fiches pour le LoopAgent (distinct de flashcard_agent) ---
loop_flashcard_agent = LlmAgent(
    name="loop_flashcard_agent",
    model=MODEL,
    description="Cree une fiche de revision dans le cadre du workflow en boucle.",
    instruction="""Tu es un createur de fiches de revision en francais.

1. Appelle create_flashcard UNE SEULE FOIS avec le concept cle du sujet.
2. Reponds en texte pour presenter la fiche creee. STOP.""",
    tools=[create_flashcard],
    output_key="flashcards_result",
    before_agent_callback=log_agent_start,
    after_agent_callback=log_agent_end,
    before_model_callback=strip_tools_after_use,
    before_tool_callback=prevent_tool_loop,
    after_tool_callback=log_tool_result,
)

# --- Agent 7: Verificateur de fiches (pour le LoopAgent) ---
flashcard_checker_agent = LlmAgent(
    name="flashcard_checker_agent",
    model=MODEL,
    description="Verifie la qualite d'une fiche de revision et suggere une amelioration.",
    instruction="""Tu es un verificateur de fiches de revision en francais.

Fiche creee: {flashcards_result}

Evalue la fiche en 2 lignes: est-elle claire et complete?
Si oui, dis "La fiche est bonne." et STOP.
Si non, suggere UNE amelioration concrete.""",
    output_key="checker_result",
    before_agent_callback=log_agent_start,
    after_agent_callback=log_agent_end,
)

# --- Agent 8: coordinator_agent (root) --- defini plus bas


# ═════════════════════════════════════════
# WORKFLOW AGENTS (TP contrainte 3)
# ═════════════════════════════════════════

# SequentialAgent: Quiz puis rapport de progression
quiz_session_workflow = SequentialAgent(
    name="quiz_session_workflow",
    description="Workflow sequentiel: quiz interactif puis rapport de progression.",
    sub_agents=[quiz_agent, progress_agent],
)

# ParallelAgent: Fiches + conseils en meme temps
preparation_workflow = ParallelAgent(
    name="preparation_workflow",
    description="Workflow parallele: fiches de revision ET conseils simultanement.",
    sub_agents=[flashcard_agent, tips_agent],
)

# LoopAgent: Cree une fiche puis la verifie (max 2 iterations)
flashcard_loop_workflow = LoopAgent(
    name="flashcard_loop_workflow",
    description="Workflow en boucle: cree une fiche puis verifie sa qualite (max 2 tours).",
    sub_agents=[loop_flashcard_agent, flashcard_checker_agent],
    max_iterations=2,
)

# ═════════════════════════════════════════
# AGENT ROOT — Coordinateur
# ═════════════════════════════════════════
root_agent = LlmAgent(
    name="coordinator_agent",
    model=MODEL,
    description="Coordinateur principal qui route les demandes vers les agents specialises.",
    instruction="""Tu es un assistant de revision en francais. Accueille l'etudiant et propose:
1. Quiz (dis "quiz sur [sujet]")
2. Fiches de revision (dis "fiche sur [sujet]")
3. Conseils de revision (dis "conseils sur [sujet]")

Demande quel sujet l'interesse.""",
    sub_agents=[
        quiz_session_workflow,      # transfer_to_agent -> SequentialAgent (TP contrainte 5)
        preparation_workflow,       # transfer_to_agent -> ParallelAgent
        flashcard_loop_workflow,    # transfer_to_agent -> LoopAgent
    ],
    before_agent_callback=log_agent_start,
    after_agent_callback=log_agent_end,
    before_model_callback=smart_router,  # Routing Python (TP contrainte 6)
)
