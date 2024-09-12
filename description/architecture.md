# Architecture du projet Data-Compost

Ce document décrit l'architecture du projet **Data-Compost** et la manière dont les différents composants interagissent.

## Structure des dossiers

- `data/` : Contient les ensembles de données (dossier `train/` et `test/` pour les phases d'entraînement et de test).
- `src/` : Code source du projet, organisé en modules indépendants.
    - `modules/` : Contient les principaux modules (analyse, segmentation, transformation, etc.).
    - `utils/` : Fonctions utilitaires réutilisables.
    - `main.py` : Point d'entrée du projet pour exécuter les différents modules.
- `front/` : Code de l'interface utilisateur.
- `description/` : Documentation détaillée du projet.
- `ressources/` : Ressources externes (images, données, modèles).
- `notebooks/` : Notebooks Jupyter pour l'exploration et les tests.
- `requirements.txt` : Liste des dépendances Python.
- `package.json` : Fichier des dépendances front-end.

## Interaction entre les modules

Les modules communiquent via des interfaces bien définies. Par exemple :

- Le module `analyse` extrait les métadonnées et passe les résultats au module `segmentation`.
- Le module `segmentation` regroupe les fichiers en silos virtuels, qui sont ensuite être transformés par le module `transformation`.
- Le module `visualisation` prend les résultats finaux pour les afficher dans l'interface utilisateur.

## Flux de travail global

1. Extraction des métadonnées et analyse initiale.
2. Segmentation des fichiers en fonction de leur contenu.
3. Transformation créative des fichiers.
4. Interprétation et génération de contenu.
5. Visualisation et export des résultats.
