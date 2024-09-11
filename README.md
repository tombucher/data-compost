# data-compost

## Description

**data-compost** est un projet qui vise à traiter et transformer des fichiers numériques à travers un processus appelé "compostage numérique". Il utilise des techniques de segmentation, d'analyse, de transformation, et de visualisation pour donner un nouvel aspect aux données tout en générant des métadonnées pour le suivi.

## Fonctionnalités principales

- **Analyse des fichiers** : Extraction de métadonnées, classification des fichiers, détection de la qualité, calcul du rapport carbone/azote.
- **Segmentation** : Clustering basé sur le contenu, création de silos virtuels, et distribution des fichiers dans ces silos.
- **Transformation** : Altération et fusion des fichiers, génération de compost numérique avec des métadonnées de transformation.
- **Interprétation** : Génération de narratifs, extraction de caractéristiques, analyse sentimentale.
- **Visualisation** : Interface utilisateur permettant de suivre et visualiser le compostage numérique.

## Architecture du projet

```bash
data-compost/
├── data/
│   ├── train/
│   └── test/
├── src/
│   ├── modules/
│   │   ├── analysis.py
│   │   ├── segmentation.py
│   │   ├── transformation.py
│   ├── utils/
│   └── main.py
├── front/
│   ├── index.html
│   ├── styles.css
│   └── scripts.js
├── description/
│   └── README.md
├── ressources/
│   └── images/
├── notebooks/
│   └── data_exploration.ipynb
├── requirements.txt
└── README.md

```
## Installation

1. Clonez ce dépôt :

    ```bash
    git clone https://github.com/tombucher/data-compost.git
    cd data-compost
    ```

2. Créez un environnement virtuel et activez-le :

    ```bash
    python -m venv venv
    source venv/bin/activate  # Pour macOS/Linux
    venv\Scripts\activate  # Pour Windows
    ```

3. Installez les dépendances Python :

    ```bash
    pip install -r requirements.txt
    ```

4. Pour le front-end (si applicable), installez les dépendances Node.js :

    ```bash
    npm install
    ```

## Utilisation

1. **Analyse des fichiers** : Utilisez le module d’analyse pour extraire des métadonnées et classer les fichiers.

    ```bash
    python src/modules/analysis.py
    ```

2. **Segmentation** : Segmentez les fichiers selon leur contenu.

    ```bash
    python src/modules/segmentation.py
    ```

3. **Transformation des fichiers** : Transformez les fichiers en compost numérique.

    ```bash
    python src/modules/transformation.py
    ```

4. **Lancement du front-end** : Démarrez l’interface utilisateur.

    ```bash
    npm start
    ```

## Contribuer

Les contributions sont les bienvenues ! Si vous avez des idées d’amélioration ou souhaitez signaler des problèmes, ouvrez une issue ou un pull request.
