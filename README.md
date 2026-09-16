# GridSense

Το GridSense είναι ένα prototype σύστημα για smart power grid analytics και fault management, υλοποιημένο στο πλαίσιο του μαθήματος Advanced Data Management.

Η εφαρμογή συνδυάζει Cassandra, Neo4j, MongoDB, PostgreSQL και Redis πίσω από ένα FastAPI REST API.

## Απαιτήσεις

Για την εκτέλεση απαιτούνται:

- Docker
- Docker Compose
- Python 3.11+
- Git

## Ρύθμιση Περιβάλλοντος

Όλα τα passwords και connection parameters παρέχονται μέσω αρχείου `.env`.

Δημιούργησε το `.env` από το παρεχόμενο example:

```bash
cp .env.example .env
```

## Εκκίνηση

Κλωνοποίησε το repository:

```bash
git clone https://github.com/EfthymiosManolis/gridsense.git
cd gridsense
```

Δημιούργησε το `.env`:

```bash
cp .env.example .env
```

Εκκίνησε ολόκληρο το σύστημα:

```bash
docker compose up --build
```

Για εκτέλεση στο background:

```bash
docker compose up --build -d
```

Έλεγχος κατάστασης των containers:

```bash
docker compose ps
```

Το REST API είναι διαθέσιμο στο:

```text
http://localhost:8000
```

Το Swagger UI είναι διαθέσιμο στο:

```text
http://localhost:8000/docs
```

Έλεγχος λειτουργίας του API:

```bash
curl http://localhost:8000/health
```

## Services

| Service | Technology | Port | Purpose |
|---|---|---:|---|
| `api` | FastAPI / Python 3.11 | 8000 | REST API gateway και business logic |
| `timeseries-db` | Cassandra 4.1 | 9042 | Αποθήκευση sensor readings και relay events |
| `graph-db` | Neo4j 5 Community | 7474 / 7687 | Τοπολογία ηλεκτρικού δικτύου και graph traversals |
| `catalog-db` | MongoDB 7 | 27017 | Flexible equipment metadata |
| `billing-db` | PostgreSQL 15 | 5432 | Consumer accounts και billing records |
| `cache` | Redis 7 Alpine | 6379 | Dashboard cache και Pub/Sub fault alerts |

## Seed Data

Για την εκτέλεση των utility scripts δημιούργησε Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r scripts/requirements.txt
```

Η δημιουργία όλων των seed δεδομένων γίνεται με μία εντολή:

```bash
python scripts/seed.py
```

Το seed script είναι idempotent: η επανεκτέλεσή του δεν δημιουργεί duplicate seed records.

Το dataset περιλαμβάνει:

- 50.000 Cassandra sensor readings σε 20 διαφορετικά sensor IDs
- 10 Neo4j substations
- 40 Neo4j transformers
- 200 Neo4j smart meters και τις μεταξύ τους relationships
- 40 MongoDB equipment records σε 4 διαφορετικά equipment types
- 100 PostgreSQL consumer accounts με sample invoices

## Παραδείγματα API Calls

### Sensor Readings

Ανάκτηση των τελευταίων readings ενός sensor:

```bash
curl "http://localhost:8000/sensors/SENSOR01/readings?limit=10"
```

### Sensor Summary

Ανάκτηση του cached summary ενός sensor:

```bash
curl "http://localhost:8000/sensors/SENSOR01/summary"
```

### Fault Impact

Ανάκτηση των downstream nodes που επηρεάζονται από fault:

```bash
curl "http://localhost:8000/grid/fault-impact/GSP001?max_depth=6"
```

### Equipment Metadata

Ανάκτηση equipment metadata από MongoDB:

```bash
curl "http://localhost:8000/equipment/TR1"
```

### Billing Account

Ανάκτηση consumer billing account:

```bash
curl "http://localhost:8000/billing/account/PREM001"
```

## Benchmarks

Με ενεργό το Python virtual environment μπορούν να εκτελεστούν τα πειράματα του Part C.

### C.1 Cassandra

```bash
python scripts/benchmark_cassandra.py
```

### C.2 Neo4j

```bash
python scripts/benchmark_neo4j.py
```

Το benchmark δημιουργεί επίσης το αρχείο:

```text
c2_graph_traversal_latency.png
```

### C.3 Redis

```bash
python scripts/benchmark_redis.py
```

### C.4 MongoDB vs PostgreSQL

Αρχικά δημιουργούνται τα ίδια 30 equipment records και στις δύο βάσεις:

```bash
python scripts/seed_c4.py
```

Στη συνέχεια εκτελείται το benchmark:

```bash
python scripts/benchmark_c4.py
```

Τα αποτελέσματα και η ανάλυση των πειραμάτων παρουσιάζονται στο γραπτό report.

## Observability

Το API καταγράφει ανά endpoint:

- request count
- error count
- error rate
- p50 latency
- p95 latency
- p99 latency

Τα metrics είναι διαθέσιμα στο:

```bash
curl http://localhost:8000/metrics
```

## Τερματισμός

Τερματισμός των containers:

```bash
docker compose down
```

Τερματισμός και διαγραφή των persistent volumes:

```bash
docker compose down -v
```
