"""Outils pour la gestion des quiz de révision."""

from datetime import datetime

# Stockage en mémoire des résultats de quiz
_quiz_results: list[dict] = []


def generate_questions(topic: str, count: int = 3) -> dict:
    """Génère un template de session de quiz sur un sujet donné.

    Cette fonction initialise une session de quiz et retourne les instructions
    pour que l'agent LLM formule les questions adaptées au sujet.

    Args:
        topic: Le sujet sur lequel générer les questions (ex: "Python", "Maths").
        count: Le nombre de questions à poser (défaut: 3, max: 10).

    Returns:
        dict avec le sujet, le nombre de questions et les instructions de format.
    """
    count = max(1, min(int(count), 10))
    return {
        "status": "success",
        "topic": topic,
        "count": count,
        "instructions": (
            f"Génère exactement {count} questions sur '{topic}'. "
            "Pour chaque question, indique: la question, 3 options de réponse (A, B, C) "
            "et la bonne réponse. Pose les questions une par une à l'étudiant."
        ),
        "format": {
            "question": "Texte de la question",
            "options": {"A": "...", "B": "...", "C": "..."},
            "correct": "A ou B ou C",
        },
    }


def save_quiz_result(topic: str, score: int, total: int) -> dict:
    """Sauvegarde le résultat d'un quiz complété.

    Args:
        topic: Le sujet du quiz (ex: "Python").
        score: Le nombre de bonnes réponses obtenues.
        total: Le nombre total de questions posées.

    Returns:
        dict avec confirmation et statistiques du résultat sauvegardé.
    """
    try:
        score = int(score)
        total = int(total)
    except (ValueError, TypeError):
        return {"status": "error", "message": "Score et total doivent être des nombres."}

    if total <= 0:
        return {"status": "error", "message": "Le total de questions doit être > 0."}
    if score < 0 or score > total:
        return {"status": "error", "message": f"Score invalide: {score}/{total}."}

    percentage = round((score / total) * 100, 1)
    result = {
        "topic": topic,
        "score": score,
        "total": total,
        "percentage": percentage,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mention": _get_mention(percentage),
    }
    _quiz_results.append(result)

    return {
        "status": "success",
        "message": f"Résultat sauvegardé: {score}/{total} ({percentage}%)",
        "result": result,
    }


def get_all_quiz_results() -> list[dict]:
    """Retourne tous les résultats de quiz sauvegardés (usage interne)."""
    return _quiz_results


def _get_mention(percentage: float) -> str:
    """Retourne la mention en fonction du pourcentage."""
    if percentage >= 90:
        return "Excellent"
    elif percentage >= 75:
        return "Bien"
    elif percentage >= 60:
        return "Assez bien"
    elif percentage >= 50:
        return "Passable"
    else:
        return "Insuffisant"
