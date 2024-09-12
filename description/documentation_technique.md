# Documentation Technique du projet Data-Compost

Ce document présente les détails techniques du projet, notamment les algorithmes utilisés, les configurations, et les processus de déploiement.

## Algorithmes utilisés

### Module d'analyse

- **Extraction des métadonnées** : Utilisation de bibliothèques comme `exifread` pour les images, `eyed3` pour les fichiers audio, etc.
- **Classification des fichiers** : Un modèle de machine learning supervisé basé sur une approche de classification binaire est utilisé pour distinguer les fichiers en fonction de leur contenu.
- **Calcul du rapport carbone/azote** : Algorithme basé sur la taille des fichiers et la fréquence de modification pour évaluer le rapport.

### Module de segmentation

- **Clustering** : Utilisation de K-means ou DBSCAN pour regrouper les fichiers en fonction de leur contenu sémantique.
- **Segmentation sémantique** : Techniques de vision par ordinateur appliquées aux images et vidéos pour une identification précise des objets.

## Dépendances et Configuration

Le projet utilise plusieurs dépendances :

- **Python 3.12.5** : Langage principal pour le back-end.
- **Scikit-learn** : Pour les modèles de machine learning.
- **OpenCV** : Pour la manipulation d'images et vidéos.

Les dépendances sont spécifiées dans les fichiers suivants :
- `requirements.txt` pour les dépendances Python.
- `package.json` pour les dépendances front-end.

### Fichiers de configuration

- `.env` : Contient les variables d'environnement sensibles (clés API, configuration du serveur).
- `config.py` : Fichier de configuration pour définir les chemins d'accès, les paramètres des modules, etc.

## API (si applicable)

L'API expose les modules sous forme de services REST :

- `GET /analyze` : Lance l'analyse des fichiers.
- `POST /segment` : Segmente les fichiers envoyés dans le corps de la requête.
- `GET /transform` : Transforme les fichiers selon des paramètres prédéfinis.

## Déploiement

Le projet peut être déployé localement ou sur un service cloud. Voici un exemple de déploiement local :

1. **Cloner le dépôt** : `git clone https://github.com/tombucher/data-compost.git`
2. **Installer les dépendances** : `pip install -r requirements.txt`
3. **Lancer l'application** : `python src/main.py`

### Déploiement dans le cloud

Pour un déploiement cloud, des solutions comme AWS, Google Cloud, ou Heroku peuvent être utilisées. Le fichier `Procfile` (si applicable) contient les instructions de démarrage pour ces environnements.

## Tests

- **Tests unitaires** : Les tests unitaires sont exécutés via `pytest` et se trouvent dans le dossier `tests/`.
- **Tests d'intégration** : Des tests d'intégration assurent la bonne interaction entre les modules.
- **CI/CD** : Un pipeline CI/CD est mis en place via GitHub Actions pour automatiser les tests et le déploiement.
