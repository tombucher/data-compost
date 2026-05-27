# Structure des fichiers du projet

```
data-compost/
├── data/                       # Données et résultats
│   ├── test/                   # Dossier de test contenant des fichiers à composter
│   └── output/                 # Résultats générés
│       ├── silos/              # Organisation des fichiers en silos
│       └── composted/          # Fichiers transformés et résultat final
├── modules/                    # Modules principaux du système
│   ├── __init__.py             # Rend le dossier un package Python
│   ├── analyze.py              # Analyse des fichiers et extraction des métadonnées
│   ├── calculate_cn.py         # Calcul des ratios carbone/azote
│   ├── create_silos.py         # Organisation des fichiers en silos équilibrés
│   ├── transformation.py       # Processus de "compostage" des fichiers
│   ├── compost_info_display.py # Affichage des informations sur l'écran e-paper
│   ├── file_analysis_visualization.py # Visualisation pour l'analyse des fichiers
│   └── visualize_bin.py        # Visualisation du fichier binaire final
├── displays/                   # Modules d'affichage pour les différents écrans
│   ├── __init__.py             # Rend le dossier un package Python
│   ├── circular_display.py     # Affichage pour l'écran circulaire
│   ├── hdmi_display.py         # Affichage pour l'écran HDMI principal
│   ├── epaper_display.py       # Affichage amélioré pour l'écran e-paper
│   └── multiscreen_coordinator.py  # Coordinateur central du système multiécran
├── main.py                     # Script principal
├── project_structure.md        # Documentation du projet
└── readme.md                   # Documentation du projet

```

# Installation des dépendances

Pour faire fonctionner le système, vous aurez besoin d'installer les dépendances suivantes :

```bash
pip install pygame numpy tqdm pylint PyPDF2 python-docx nltk langdetect torch torchvision transformers opencv-python-headless
```

# Configuration des écrans

1. **Écran circulaire** : Connectez l'écran circulaire via HDMI ou SPI selon votre modèle.
2. **Écran HDMI principal** : Connectez-le sur le port HDMI principal.
3. **Écran e-paper** : Connectez-le via SPI ou selon les spécifications du fabricant.
4. **Imprimante thermique** : Connectez-la via USB ou port série selon votre modèle.

# Exécution du programme

Pour lancer le programme avec tous les écrans :

```bash
python main.py --input data/test
```

Pour exécuter uniquement le processus de compostage sans les affichages :

```bash
python main.py --input data/test --skip-displays
```

Pour démarrer à une phase spécifique :

```bash
python main.py --input data/test --phase 3  # Commence à la phase de création des silos
```

# Phases du processus

1. **Analyse des fichiers** : Analyse de tous les fichiers pour extraire les métadonnées.
2. **Calcul C/N** : Calcul des ratios carbone/azote pour chaque fichier.
3. **Création des silos** : Organisation des fichiers en groupes équilibrés.
4. **Compostage** : Transformation des fichiers selon leur type.
5. **Visualisation** : Présentation du "compost numérique" résultant.

# Création de dossiers nécessaires

Si vous débutez le projet, assurez-vous de créer les dossiers suivants :

```bash
mkdir -p data/test data/output/silos data/output/composted displays modules
touch modules/__init__.py displays/__init__.py
```

Placez quelques fichiers de test dans le dossier `data/test` pour démarrer le processus.
