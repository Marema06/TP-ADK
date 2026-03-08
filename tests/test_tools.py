"""Tests unitaires pour les outils de l'assistant de revision."""

import pytest


# ═══════════════════════════════════════════
# TESTS: quiz_tools
# ═══════════════════════════════════════════

class TestGenerateQuestions:
    """Tests pour l'outil generate_questions."""

    def test_generation_basique(self):
        from assistant_revision.tools.quiz_tools import generate_questions
        result = generate_questions("Python", 3)
        assert result["status"] == "success"
        assert result["topic"] == "Python"
        assert result["count"] == 3

    def test_count_par_defaut(self):
        from assistant_revision.tools.quiz_tools import generate_questions
        result = generate_questions("Maths")
        assert result["count"] == 3  # valeur par defaut

    def test_count_string_converti_en_int(self):
        """Mistral passe parfois count comme string."""
        from assistant_revision.tools.quiz_tools import generate_questions
        result = generate_questions("Python", "5")
        assert result["count"] == 5
        assert result["status"] == "success"

    def test_count_limite_a_10(self):
        from assistant_revision.tools.quiz_tools import generate_questions
        result = generate_questions("Python", 50)
        assert result["count"] == 10

    def test_count_minimum_1(self):
        from assistant_revision.tools.quiz_tools import generate_questions
        result = generate_questions("Python", -5)
        assert result["count"] == 1

    def test_format_retourne(self):
        from assistant_revision.tools.quiz_tools import generate_questions
        result = generate_questions("Python", 2)
        assert "format" in result
        assert "question" in result["format"]
        assert "options" in result["format"]
        assert "correct" in result["format"]


class TestSaveQuizResult:
    """Tests pour l'outil save_quiz_result."""

    def test_sauvegarde_reussie(self):
        from assistant_revision.tools.quiz_tools import save_quiz_result
        result = save_quiz_result("Python", 2, 3)
        assert result["status"] == "success"
        assert result["result"]["percentage"] == 66.7

    def test_score_string_converti(self):
        """Mistral passe parfois score/total comme strings."""
        from assistant_revision.tools.quiz_tools import save_quiz_result
        result = save_quiz_result("Maths", "3", "5")
        assert result["status"] == "success"
        assert result["result"]["score"] == 3
        assert result["result"]["total"] == 5

    def test_total_zero_erreur(self):
        from assistant_revision.tools.quiz_tools import save_quiz_result
        result = save_quiz_result("Python", 0, 0)
        assert result["status"] == "error"

    def test_score_negatif_erreur(self):
        from assistant_revision.tools.quiz_tools import save_quiz_result
        result = save_quiz_result("Python", -1, 3)
        assert result["status"] == "error"

    def test_score_superieur_total_erreur(self):
        from assistant_revision.tools.quiz_tools import save_quiz_result
        result = save_quiz_result("Python", 5, 3)
        assert result["status"] == "error"

    def test_mention_excellent(self):
        from assistant_revision.tools.quiz_tools import save_quiz_result
        result = save_quiz_result("Python", 10, 10)
        assert result["result"]["mention"] == "Excellent"

    def test_mention_insuffisant(self):
        from assistant_revision.tools.quiz_tools import save_quiz_result
        result = save_quiz_result("Python", 1, 10)
        assert result["result"]["mention"] == "Insuffisant"


# ═══════════════════════════════════════════
# TESTS: flashcard_tools
# ═══════════════════════════════════════════

class TestCreateFlashcard:
    """Tests pour l'outil create_flashcard."""

    def test_creation_reussie(self):
        from assistant_revision.tools.flashcard_tools import create_flashcard
        result = create_flashcard("Qu'est-ce qu'une liste?", "Structure de donnees ordonnee", "python")
        assert result["status"] == "success"
        assert result["card"]["front"] == "Qu'est-ce qu'une liste?"
        assert result["card"]["category"] == "python"

    def test_categorie_par_defaut(self):
        from assistant_revision.tools.flashcard_tools import create_flashcard
        result = create_flashcard("Question", "Reponse")
        assert result["card"]["category"] == "général"

    def test_recto_vide_erreur(self):
        from assistant_revision.tools.flashcard_tools import create_flashcard
        result = create_flashcard("", "Reponse")
        assert result["status"] == "error"

    def test_verso_vide_erreur(self):
        from assistant_revision.tools.flashcard_tools import create_flashcard
        result = create_flashcard("Question", "   ")
        assert result["status"] == "error"

    def test_id_incremente(self):
        from assistant_revision.tools.flashcard_tools import create_flashcard
        r1 = create_flashcard("Q1", "R1")
        r2 = create_flashcard("Q2", "R2")
        assert r2["card"]["id"] > r1["card"]["id"]


class TestListFlashcards:
    """Tests pour l'outil list_flashcards."""

    def test_liste_toutes(self):
        from assistant_revision.tools.flashcard_tools import list_flashcards
        result = list_flashcards()
        assert result["status"] == "success"
        assert result["count"] >= 0

    def test_filtre_categorie(self):
        from assistant_revision.tools.flashcard_tools import create_flashcard, list_flashcards
        create_flashcard("Test", "Test", "filtrage")
        result = list_flashcards("filtrage")
        assert result["status"] == "success"
        assert all(c["category"] == "filtrage" for c in result["flashcards"])


# ═══════════════════════════════════════════
# TESTS: progress_tools
# ═══════════════════════════════════════════

class TestGetProgressReport:
    """Tests pour l'outil get_progress_report."""

    def test_rapport_sans_donnees(self):
        from assistant_revision.tools import progress_tools
        # Vider les resultats pour ce test
        from assistant_revision.tools.quiz_tools import _quiz_results
        original = _quiz_results.copy()
        _quiz_results.clear()

        result = progress_tools.get_progress_report()
        assert result["status"] == "no_data"
        assert result["total_quizzes"] == 0

        # Restaurer
        _quiz_results.extend(original)

    def test_rapport_avec_donnees(self):
        from assistant_revision.tools.quiz_tools import save_quiz_result
        from assistant_revision.tools.progress_tools import get_progress_report
        save_quiz_result("TestSujet", 3, 5)
        result = get_progress_report()
        assert result["status"] == "success"
        assert result["global_stats"]["total_quizzes"] >= 1
        assert "by_topic" in result
        assert "recommendation" in result


class TestGetStudyTips:
    """Tests pour l'outil get_study_tips."""

    def test_tips_programmation(self):
        from assistant_revision.tools.progress_tools import get_study_tips
        result = get_study_tips("Python")
        assert result["status"] == "success"
        assert result["topic"] == "Python"
        assert len(result["recommended_methods"]) == 4
        assert "revision_plan" in result

    def test_tips_maths(self):
        from assistant_revision.tools.progress_tools import get_study_tips
        result = get_study_tips("Mathematiques")
        assert result["status"] == "success"
        assert any("exercice" in m.lower() for m in result["recommended_methods"])

    def test_tips_sujet_general(self):
        from assistant_revision.tools.progress_tools import get_study_tips
        result = get_study_tips("Histoire")
        assert result["status"] == "success"
        assert any("feynman" in m.lower() for m in result["recommended_methods"])

    def test_plan_revision_present(self):
        from assistant_revision.tools.progress_tools import get_study_tips
        result = get_study_tips("Biologie")
        assert "jour_1" in result["revision_plan"]
        assert "jour_14" in result["revision_plan"]

    def test_pomodoro_present(self):
        from assistant_revision.tools.progress_tools import get_study_tips
        result = get_study_tips("Chimie")
        assert "pomodoro_suggestion" in result
