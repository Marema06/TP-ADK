"""Outils pour le suivi de progression et les conseils de révision."""

from .quiz_tools import get_all_quiz_results


def get_progress_report() -> dict:
    """Génère un rapport complet de progression de l'étudiant.

    Analyse tous les résultats de quiz sauvegardés et produit des statistiques
    globales ainsi que des détails par sujet pour aider à identifier les points
    forts et les axes d'amélioration.

    Returns:
        dict contenant les statistiques globales, le détail par sujet
        et des recommandations basées sur les résultats.
    """
    results = get_all_quiz_results()

    if not results:
        return {
            "status": "no_data",
            "message": "Aucun quiz complété pour le moment. Lance un quiz pour voir ta progression!",
            "total_quizzes": 0,
        }

    total_quizzes = len(results)
    total_correct = sum(r["score"] for r in results)
    total_questions = sum(r["total"] for r in results)
    global_percentage = round((total_correct / total_questions) * 100, 1) if total_questions > 0 else 0

    # Statistiques par sujet
    by_topic: dict[str, dict] = {}
    for r in results:
        topic = r["topic"]
        if topic not in by_topic:
            by_topic[topic] = {"attempts": 0, "total_score": 0, "total_questions": 0}
        by_topic[topic]["attempts"] += 1
        by_topic[topic]["total_score"] += r["score"]
        by_topic[topic]["total_questions"] += r["total"]

    topics_summary = []
    weakest_topic = None
    weakest_pct = 100.0
    for topic, data in by_topic.items():
        pct = round((data["total_score"] / data["total_questions"]) * 100, 1)
        topics_summary.append({
            "topic": topic,
            "attempts": data["attempts"],
            "average_percentage": pct,
            "status": "Fort" if pct >= 70 else "À retravailler",
        })
        if pct < weakest_pct:
            weakest_pct = pct
            weakest_topic = topic

    recommendation = (
        f"Tu maîtrises bien les sujets étudiés! Continue comme ça."
        if global_percentage >= 75
        else f"Concentre-toi sur '{weakest_topic}' qui est ton point faible ({weakest_pct}%)."
    )

    return {
        "status": "success",
        "global_stats": {
            "total_quizzes": total_quizzes,
            "total_questions_answered": total_questions,
            "correct_answers": total_correct,
            "global_percentage": global_percentage,
            "overall_mention": _get_mention(global_percentage),
        },
        "by_topic": topics_summary,
        "recommendation": recommendation,
        "history": results[-5:],  # 5 derniers résultats
    }


def get_study_tips(topic: str) -> dict:
    """Retourne des conseils et stratégies de révision pour un sujet donné.

    Fournit des méthodes d'apprentissage adaptées, des ressources suggérées
    et un plan de révision structuré pour le sujet demandé.

    Args:
        topic: Le sujet pour lequel obtenir des conseils (ex: "Python", "Algèbre").

    Returns:
        dict avec des conseils personnalisés, méthodes et un plan de révision.
    """
    topic_lower = topic.lower()

    # Conseils génériques adaptés au type de sujet
    if any(kw in topic_lower for kw in ["math", "algèbre", "calcul", "physique", "stats"]):
        methods = [
            "Résous des exercices progressifs (du plus simple au plus complexe)",
            "Refais les exercices vus en cours sans regarder la correction",
            "Crée des fiches avec les formules clés et leurs conditions d'application",
            "Explique les concepts à voix haute comme si tu enseignais",
        ]
        tips = "Pour les matières formelles, la pratique régulière vaut mieux que les longues sessions."
    elif any(kw in topic_lower for kw in ["python", "code", "programmation", "algo", "javascript"]):
        methods = [
            "Code chaque concept vu en cours dans un mini-projet",
            "Résous des exercices sur des plateformes comme Codewars ou LeetCode",
            "Lit du code existant et essaie de le comprendre ligne par ligne",
            "Construis de petits projets qui utilisent les concepts étudiés",
        ]
        tips = "En programmation, écrire du code tous les jours est la clé du progrès."
    else:
        methods = [
            "Utilise la technique de Feynman: explique le sujet simplement",
            "Crée des cartes mentales pour visualiser les connexions entre concepts",
            "Fais des révisions espacées: reviens sur le sujet après 1 jour, 1 semaine, 1 mois",
            "Transforme les informations en questions et réponds-y régulièrement",
        ]
        tips = "La répétition espacée est la méthode la plus efficace pour la mémorisation long terme."

    plan = {
        "jour_1": f"Lis et comprends les concepts de base de '{topic}'",
        "jour_2": f"Crée des fiches de révision sur '{topic}'",
        "jour_3": f"Fais un quiz sur '{topic}' pour tester tes connaissances",
        "jour_7": f"Révision complète de '{topic}' et identification des lacunes",
        "jour_14": f"Quiz final sur '{topic}' pour consolider",
    }

    return {
        "status": "success",
        "topic": topic,
        "key_tip": tips,
        "recommended_methods": methods,
        "revision_plan": plan,
        "pomodoro_suggestion": "25 min de travail, 5 min de pause — répète 4 fois puis fais une longue pause.",
    }


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
