# Système de Compostage Numérique

Ce projet simule le processus de compostage organique mais avec des fichiers numériques. Il analyse les fichiers comme des matières organiques, calcule leur ratio carbone/azote, les organise en silos équilibrés, puis les "décompose" en créant un nouveau fichier binaire qui est une fusion transformée des originaux.

## Concept

Le compostage numérique transforme les fichiers à travers plusieurs phases :
1. **Analyse** : Extraction des métadonnées et caractéristiques des fichiers 
2. **Classification C/N** : Détermination si un fichier est plutôt "vert" (riche en azote) ou "brun" (riche en carbone)
3. **Organisation** : Répartition dans des silos pour équilibrer le ratio C/N global
4. **Transformation** : "Décomposition" des fichiers pour créer un compost numérique final

## Architecture du système

Le système utilise trois écrans différents et potentiellement une imprimante thermique :
- **Écran circulaire** : Affiche la phase actuelle et la progression
- **Écran HDMI principal** : Montre des visualisations détaillées du processus
- **Écran e-paper** : Présente les statistiques et informations clés
- **Imprimante thermique** : Peut imprimer une représentation du résultat final

## Installation

### Environnement virtuel

Le projet utilise un environnement virtuel Python isolé (`venv/`) avec
toutes ses dépendances. **Il faut l'activer avant chaque session** :

```bash
# Première fois uniquement : créer le venv et installer les dépendances
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ensuite, à chaque nouvelle session terminal :
source venv/bin/activate
```

Une fois le venv activé, `python` pointe vers l'interpréteur du venv et
toutes les dépendances sont disponibles. Pour quitter le venv :
`deactivate`.

> Astuce : si `python: command not found` apparaît, c'est que le venv
> n'est pas activé. Sur macOS, le système ne fournit que `python3` —
> jamais `python`.

### Configuration matérielle 

1. Connectez l'écran circulaire (via HDMI ou SPI)
2. Connectez l'écran HDMI principal 
3. Connectez l'écran e-paper (via SPI généralement)
4. Connectez l'imprimante thermique (si applicable)

## Utilisation

### Préparation

Placez les fichiers à "composter" dans le dossier `data/test/` ou spécifiez un autre dossier lors de l'exécution.

### Exécution

⚠️ Activer d'abord le venv : `source venv/bin/activate`

Pour lancer le programme complet :
```bash
python main.py --input data/test
```

Pour exécuter uniquement le processus sans interfaces graphiques :
```bash
python main.py --input data/test --skip-displays
```

Pour démarrer à une phase spécifique :
```bash
python main.py --input data/test --phase 3  # Commence à la création des silos
```

### Tests

```bash
pytest tests/
```

### Configuration

Les chemins, seuils C/N et paramètres du pipeline sont centralisés dans
[`config.toml`](config.toml) à la racine du projet. Modifier ce fichier
plutôt que le code.

## Structure du projet

```
data-compost/
├── data/                      # Données d'entrée et résultats
├── modules/                   # Modules de traitement
├── displays/                  # Modules d'affichage 
└── main.py                    # Script principal
```

## Phases détaillées

1. **Analyse des fichiers**
   - Analyse de tous les fichiers et leurs métadonnées
   - Classification initiale par type

2. **Calcul des ratios C/N**
   - Détermination des propriétés carbone/azote
   - Normalisation des ratios

3. **Création des silos**
   - Organisation des fichiers en groupes équilibrés
   - Optimisation du ratio C/N global

4. **Processus de compostage**
   - Transformation adaptée selon le type de fichier
   - Fusion progressive des données

5. **Visualisation finale**
   - Présentation du "compost numérique" résultant
   - Analyse visuelle et sonore du résultat

## Contribution

Ce projet est une œuvre artistique et technique explorant la matérialité des données numériques.
