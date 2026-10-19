# Budget Libre — V2

Application web auto-hébergeable de budget à base zéro, inspirée des principes d’enveloppes budgétaires sans reproduire l’interface ni le code d’un produit tiers.

## Fonctions incluses

- Budget mensuel **Assigné / Activité / Disponible**, avec report des soldes et montant **Prêt à répartir**.
- Groupes, catégories, nature de dépense et types d’épargne.
- Comptes bancaires, épargne, espèces, prêts et cartes de crédit.
- Transactions, compensées/approuvées, recherche, filtres mensuels, transferts créés en double écriture.
- Transactions fractionnées prises en charge au niveau de l’API (le formulaire permet aujourd’hui une saisie par ligne pour rester rapide sur mobile).
- Import OFX/QFX, contrôle FITID puis contrôle date/montant/bénéficiaire, application de règles de catégorisation.
- Cibles configurables par menu : enveloppe à renflouer, mise de côté et épargne de projet; rythme hebdomadaire, aux deux semaines, mensuel ou annuel, date/jour requis et recommandation d’allocation calculée selon le solde restant.
- Profils budgétaires isolés : chaque profil possède ses comptes, catégories, budget, transactions et rapports. Un profil est créé avec une structure de départ indépendante.
- Rapprochement de compte et calcul d’écart.
- Rapports de dépenses, revenus, moyenne mensuelle, flux de trésorerie et patrimoine.
- Sauvegarde/restauration SQLite et PWA installable.

## Démarrage avec Docker (recommandé)

```bash
docker compose up -d --build
```

Ouvrez ensuite `http://localhost:8000`.

Vos données sont dans `./data/budget.db`; faites des copies régulières ou utilisez le bouton **Télécharger la sauvegarde** de l’interface. Pour mettre l’application à jour :

```bash
docker compose up -d --build
```

## Démarrage sans Docker

Python 3.12 ou plus récent est recommandé.

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows PowerShell
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Sous macOS/Linux, activez l’environnement avec `source .venv/bin/activate`.

## Utilisation rapide

1. Créez vos comptes et saisissez les soldes d’ouverture.
2. Adaptez les groupes et catégories puis ajoutez des cibles depuis la page Budget.
3. Importez votre OFX dans **Règles & import**; définissez des règles pour les prochains imports.
4. Affectez les entrées d’argent aux catégories afin de ramener « Prêt à répartir » à zéro.
5. Enregistrez les dépenses et rapprochez chaque compte à la réception d’un relevé.

## Notes de sécurité

Cette version est conçue pour un usage personnel ou familial sur un serveur de confiance. Elle ne propose pas encore d’authentification multi-utilisateur : placez-la derrière un proxy HTTPS avec authentification si elle est exposée à Internet. Conservez les sauvegardes dans un emplacement protégé.
