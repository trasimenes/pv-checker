# Pierre & Vacances Image Checker - Documentation

## Structure d'un placeholder

Exemple d'une destination avec placeholder (pas d'image disponible) :
https://www.pierreetvacances.com/fr-fr/de_location-luni

```html
<section class="headband headband--boxed">
    <div class="headband-imgContainer">
        <picture>
            <source srcset="https://static.pierreetvacances.com/138.7.0/assets/images/default/1140x380.jpg" media="(max-width: 767px)">
            <img class="headband-img" src="https://static.pierreetvacances.com/138.7.0/assets/images/default/1368x456.jpg" alt="Visuel panoramique Luni" fetchpriority="high">
        </picture>
    </div>
    <div class="headband-wrapper container">
        <div class="headband-content">
            <h1 class="headband-title">Location Luni</h1>
            <div class="headband-destination">
                <a title="Italie" href="https://www.pierreetvacances.com/fr-fr/co_location-italie">Italie</a>
            </div>
        </div>
    </div>
</section>
```

### Indicateurs de placeholder :
- URL contient `/assets/images/default/`
- Classe `headband-img` avec source default
- Structure spécifique avec dimensions standard (1140x380.jpg, 1368x456.jpg)

## Structure des URLs Pierre & Vacances

### Patterns d'URLs par type de destination :

#### **Zones Touristiques** (`zt_`)
- **Pattern** : `https://www.pierreetvacances.com/fr-fr/zt_*`
- **Exemple** : `https://www.pierreetvacances.com/fr-fr/zt_location-majorque`
- **Description** : Pages de zones touristiques spécifiques (îles, régions touristiques)

#### **Géographique** (`ge_`)
- **Pattern** : `https://www.pierreetvacances.com/fr-fr/ge_*`
- **Exemple** : `https://www.pierreetvacances.com/fr-fr/ge_location-saint-paul`
- **Description** : Pages de pays et régions géographiques

#### **Résidences** (`fp_`)
- **Pattern** : `https://www.pierreetvacances.com/fr-fr/fp_[CODE]_*`
- **Exemple** : `https://www.pierreetvacances.com/fr-fr/fp_CWL_location-residence-la-petite-venise`
- **Description** : Pages de résidences individuelles spécifiques (CODE = identifiant unique de la résidence)

#### **Destinations** (`de_`)
- **Pattern** : `https://www.pierreetvacances.com/fr-fr/de_*`
- **Exemple** : `https://www.pierreetvacances.com/fr-fr/de_location-houlgate`
- **Description** : Pages de destinations par ville/localité

#### **Pays** (`co_`)
- **Pattern** : `https://www.pierreetvacances.com/fr-fr/co_*`
- **Exemple** : `https://www.pierreetvacances.com/fr-fr/co_location-france`
- **Description** : Pages de niveau pays

### Hiérarchie des destinations P&V :
```
Pays (co_) 
├── Zones Touristiques (zt_) - ex: Majorque, Andalousie
├── Régions Géographiques (ge_) - ex: Saint-Paul, Alsace
├── Destinations par ville (de_) - ex: Houlgate, Colmar
└── Résidences individuelles (fp_) - ex: La Petite Venise, Les Balcons de la Vanoise
```

## Nouvelles fonctionnalités

### URL Consolidator
- **Base de données SQLite** : Stockage des destinations avec pays, région, ville, type
- **Scraping complet** : Récupération automatique de toutes les destinations du catalogue P&V
- **Patterns complets** : Détection de tous les types d'URLs (`zt_`, `ge_`, `fp_`, `de_`, `co_`)
- **Gestion par pays** : Organisation des destinations par onglets de pays
- **Import/Export CSV** : Possibilité d'importer et exporter les destinations
- **Édition manuelle** : Ajout/modification/suppression de destinations

### Système de Snapshots
- **Versioning** : Historique complet des états du catalogue
- **Timeline** : Suivi de l'évolution dans le temps
- **Export snapshots** : Sauvegarde des versions en CSV
- **Création manuelle/auto** : Snapshots à la demande ou automatiques

### Vérification sélective
- **Toutes les destinations** : Vérification complète
- **Par pays** : Vérification limitée à un pays spécifique
- **Non vérifiées** : Seulement les destinations jamais vérifiées
- **Avec placeholders** : Seulement les destinations avec images par défaut

### Progress en temps réel
- **Callback system** : Mise à jour live du statut de scraping
- **7 étapes trackées** : Pages catalogue → Pays → Sitemaps → Dédoublonnage → Sauvegarde
- **Interface AJAX** : Barre de progression + texte de statut

## Architecture Base de Données (Nouveau - Janvier 2025)

### Migration complète vers base de données SQLite
- **TOUT en base** : Fini les fichiers JSON, toutes les données sont en base
- **Préservation historique** : Aucune donnée n'est jamais écrasée, tout est consolidé
- **Migration automatique** : Les anciens résultats JSON sont importés automatiquement une seule fois
- **Statistiques historiques** : Suivi complet de l'évolution dans le temps

### Table `verification_results`
- **Historique complet** : Chaque URL peut avoir plusieurs vérifications datées
- **Tags colorés** : Catégorie détectée (Pays, Région, Destination, Blog, etc.)
- **Optimisation intelligente** : Support du groupement par destination similaire
- **Statuts** : `pending`, `success`, `warning`, `error`
- **Données riches** : Images, placeholders, pays, catégories, dates

### Nouvelles API pour gestion historique
- `POST /api/verification/populate-missing` : Peuple toutes les URLs manquantes en base
- `GET /api/verification/stats` : Statistiques détaillées par statut/catégorie/pays
- `GET /api/verification/unverified` : Liste des destinations jamais vérifiées
- `GET /api/verification/history/<url>` : Historique complet d'une URL

### Système de vérification optimisé
- **Groupement intelligent** : "Saint-Anne" → vérifie une seule URL représentative
- **Population complète** : Toutes les URLs restent en base avec statut "pending"
- **Rate limiting adaptatif** : Ajustement automatique selon la réponse serveur
- **Conservation historique** : Les 1,536+ analyses existantes préservées

### Base de données methods
```python
# Gestion des résultats de vérification
db.save_verification_result(result)           # Sauvegarde sans écraser
db.get_all_verification_results()             # Dernier scan par URL
db.get_verification_history_for_url(url)      # Historique complet d'une URL
db.populate_missing_verification_urls()       # Peuple les URLs manquantes
db.get_unverified_destinations()              # URLs jamais vérifiées
db.get_verification_stats()                   # Stats complètes
```

## Commandes de test
- Lancer l'application : `python app.py`
- Installer les dépendances : `pip install -r requirements.txt`
- Accéder au consolidateur : `http://localhost:5000/consolidator`
- Statistiques historiques : `http://localhost:5000/api/verification/stats`