# Émargement Club — Render + PostgreSQL

L'application utilise PostgreSQL comme stockage persistant. Les fichiers CSV du dossier `data/` ne sont plus utilisés comme base de données.

## Déploiement Render

### Option 1 — Blueprint

1. Pousser le projet sur GitHub.
2. Dans Render, créer un **Blueprint** depuis le dépôt.
3. Render lit `render.yaml` et crée le Web Service ainsi que PostgreSQL.
4. Vérifier que `DATABASE_URL` est bien injectée dans le Web Service.

### Option 2 — services créés manuellement

Créer :

- une base PostgreSQL Render ;
- un Web Service Python ;
- la variable d'environnement `DATABASE_URL` avec l'Internal Database URL de PostgreSQL.

Build command :

```text
pip install -r requirements.txt
```

Start command :

```text
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Données

Au démarrage, l'application crée automatiquement les tables `adherents` et `presences` si elles n'existent pas.

L'émargement est enregistré dans PostgreSQL. Le blocage de doublon pendant 30 minutes est également vérifié côté serveur.

L'URL `/api/export/presences.csv` permet d'obtenir un export CSV à tout moment.

## Migration des anciens CSV

Les anciens `data/adherents.csv` et `data/presences.csv` sont conservés dans le dépôt comme archive, mais ne sont pas importés automatiquement afin d'éviter les doublons. Si nécessaire, ils peuvent être importés une seule fois dans PostgreSQL.
