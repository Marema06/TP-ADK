"""Outils pour la création et gestion des fiches de révision."""

# Stockage en mémoire des fiches
_flashcards: list[dict] = []
_card_counter: list[int] = [0]  # compteur mutable


def create_flashcard(front: str, back: str, category: str = "général") -> dict:
    """Crée et sauvegarde une fiche de révision (flashcard).

    Une flashcard est composée d'un recto (question/terme) et d'un verso
    (réponse/définition). Elle est classée par catégorie pour faciliter
    l'organisation de la révision.

    Args:
        front: Le recto de la fiche — question, terme ou concept à mémoriser.
        back: Le verso de la fiche — réponse, définition ou explication.
        category: La catégorie de la fiche (ex: "définitions", "formules",
                  "exemples", "dates"). Défaut: "général".

    Returns:
        dict avec la fiche créée et son identifiant unique.
    """
    if not front.strip() or not back.strip():
        return {
            "status": "error",
            "message": "Le recto et le verso ne peuvent pas être vides.",
        }

    _card_counter[0] += 1
    card = {
        "id": _card_counter[0],
        "front": front.strip(),
        "back": back.strip(),
        "category": category.strip().lower(),
    }
    _flashcards.append(card)

    return {
        "status": "success",
        "message": f"Fiche #{card['id']} créée dans la catégorie '{category}'.",
        "card": card,
        "total_cards": len(_flashcards),
    }


def list_flashcards(category: str | None = None) -> dict:
    """Liste les fiches de révision existantes, avec filtre optionnel par catégorie.

    Args:
        category: Si fourni, filtre les fiches de cette catégorie uniquement.
                  Si None, retourne toutes les fiches.

    Returns:
        dict avec la liste des fiches et les statistiques par catégorie.
    """
    if category:
        cards = [c for c in _flashcards if c["category"] == category.strip().lower()]
        filter_info = f"catégorie '{category}'"
    else:
        cards = list(_flashcards)
        filter_info = "toutes catégories"

    # Statistiques par catégorie
    categories: dict[str, int] = {}
    for card in _flashcards:
        categories[card["category"]] = categories.get(card["category"], 0) + 1

    return {
        "status": "success",
        "filter": filter_info,
        "count": len(cards),
        "flashcards": cards,
        "categories_summary": categories,
    }
