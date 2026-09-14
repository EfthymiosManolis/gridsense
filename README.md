## Απαιτήσεις
Για την εκτέλεση απαιτούνται:

- Docker
- Docker Compose
- Python 3.11+
- Git

## Εκτέλεση

1. Κλωνοποίηση του repository:

```bash
git clone https://github.com/EfthymiosManolis/gridsense.git 
cd gridsense
```

2. Δημιουργία του αρχείου `.env`:

```bash
cp .env.example .env
```

3. Εκκίνηση όλων των services:

```bash
docker compose up --build -d
```

4. Έλεγχος ότι τα containers εκτελούνται:

```bash
docker compose ps
```

5. Δημιουργία και ενεργοποίηση Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r scripts/requirements.txt
```

6. Δημιουργία των seed δεδομένων:

```bash
python scripts/seed.py
```

7. Έλεγχος του API:

```bash
curl http://localhost:8000/health
```

Το API είναι διαθέσιμο στο:

```text
http://localhost:8000
```

και το Swagger UI στο:

```text
http://localhost:8000/docs
```

## Services

- **FastAPI** — REST API της εφαρμογής, port `8000`
- **Cassandra** — αποθήκευση sensor readings, port `9042`
- **Neo4j** — τοπολογία ηλεκτρικού δικτύου, ports `7474` και `7687`
- **MongoDB** — metadata εξοπλισμού, port `27017`
- **PostgreSQL** — billing δεδομένα, port `5432`
- **Redis** — caching και alerts, port `6379`

## Παραδείγματα API Calls

Ανάκτηση sensor readings:

```bash
curl "http://localhost:8000/sensors/SENSOR01/readings?limit=10"
```

Fault impact στο ηλεκτρικό δίκτυο:

```bash
curl "http://localhost:8000/grid/fault-impact/GSP001"
```

Ανάκτηση equipment:

```bash
curl "http://localhost:8000/equipment/TR1"
```

Ανάκτηση billing account:

```bash
curl "http://localhost:8000/billing/account/PREM001"
```

## Τερματισμός

```bash
docker compose down
```
