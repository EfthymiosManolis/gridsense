# GridSense

Το GridSense είναι ένα prototype σύστημα για smart power grid analytics και fault management, υλοποιημένο στο πλαίσιο του μαθήματος Advanced Data Management.

Η εφαρμογή συνδυάζει Cassandra, Neo4j, MongoDB, PostgreSQL και Redis πίσω από ένα FastAPI REST API.

## Απαιτήσεις

Για την εκτέλεση απαιτούνται:

- Docker
- Docker Compose
- Git

Για τα προαιρετικά host-side scripts απαιτείται επιπλέον Python 3.11+.

## Ρύθμιση Περιβάλλοντος

Δεν απαιτείται αρχείο `.env` για την εκκίνηση. Το Docker Compose δημιουργεί
αυτόματα τυχαίους κωδικούς για Neo4j και PostgreSQL στο τοπικό volume
`secrets_data` κατά την πρώτη εκκίνηση. Οι κωδικοί διατηρούνται στις επόμενες
εκκινήσεις και δεν αποθηκεύονται στο Git. Το `.env.example` αφορά μόνο τα
προαιρετικά scripts που εκτελούνται από το host.

## Εκκίνηση

Κλωνοποίησε το repository:

```bash
git clone https://github.com/EfthymiosManolis/gridsense.git
cd gridsense
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
| `secrets-init` | Alpine | — | Δημιουργεί και διατηρεί τοπικούς κωδικούς κατά την πρώτη εκκίνηση |
| `seed` | Python 3.11 | — | Γεμίζει αυτόματα τις άδειες βάσεις με δοκιμαστικά δεδομένα πριν ξεκινήσει το API |
| `api` | FastAPI / Python 3.11 | 8000 | REST API gateway και business logic |
| `timeseries-db` | Cassandra 4.1 | 9042 | `sensor_readings`, `relay_events` και ημερήσια sharded `regional_readings` |
| `graph-db` | Neo4j 5 Community | 7474 / 7687 | Τοπολογία ηλεκτρικού δικτύου και graph traversals |
| `catalog-db` | MongoDB 7 | 27017 | Flexible equipment metadata |
| `billing-db` | PostgreSQL 15 | 5432 | Consumer accounts και billing records |
| `cache` | Redis 7 Alpine | 6379 | Dashboard cache, Redis Stream για fault updates και Pub/Sub ειδοποιήσεις |

## Seed Data

Το `sensor_readings` έχει partition key `(sensor_id, date_bucket)` και το
`regional_readings` έχει `(region_id, date_bucket, shard)`. Και στις δύο
περιπτώσεις το `date_bucket` είναι ημερομηνία UTC. Ο τρίτος πίνακας είναι το
`relay_events`. Κάθε νέα μέτρηση API χρειάζεται `region_id`.

Σε καθαρή εγκατάσταση οι τρεις πίνακες δημιουργούνται αυτόματα από το
`cql/init.cql`. Η υπηρεσία `seed` εκτελεί το `seed.py` πριν ξεκινήσει το API,
οπότε το `docker compose up --build` παρέχει και τα δοκιμαστικά δεδομένα.
Αν υπάρχουν ήδη sensor readings, το αυτόματο seed παραλείπεται για να
διατηρηθούν τα υπάρχοντα δεδομένα. Η χειροκίνητη εκτέλεση του `seed.py`
καθαρίζει τους πίνακες συνθετικών sensor/regional δεδομένων πριν τους
ξαναγεμίσει· μην την κάνεις πάνω σε δεδομένα που θέλεις να διατηρήσεις.

Ένα παλιό persistent Cassandra volume κρατά το προηγούμενο schema και δεν
αναβαθμίζεται αυτόματα από το `CREATE TABLE IF NOT EXISTS`.

Για τα προαιρετικά utility scripts που εκτελούνται από το host, δημιούργησε
`.env` από το `.env.example` και βάλε τους κωδικούς της τρέχουσας εγκατάστασης.
Μπορείς να τους διαβάσεις με:

```bash
docker compose exec -T graph-db cat /secrets/neo4j_password
docker compose exec -T billing-db cat /secrets/postgres_password
```

Το `.env` αγνοείται από το Git. Οι τιμές `change_me_*` στο `.env.example`
είναι placeholders και δεν είναι οι κωδικοί της εγκατάστασης.

Για την εκτέλεση των utility scripts δημιούργησε Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r scripts/requirements.txt
```

Για προαιρετική χειροκίνητη επαναδημιουργία των seed δεδομένων χρησιμοποίησε:

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

### Network Recent Readings

Το endpoint επιστρέφει έως 200 εγγραφές ανά σελίδα από το τελευταίο λεπτό.
Χρησιμοποίησε την ίδια τιμή `as_of` για διαδοχικές σελίδες:

```bash
curl "http://localhost:8000/sensors/network/recent?limit=100&offset=0"
```

Η απάντηση περιλαμβάνει `as_of`, `has_more` και `readings`. Το μέγιστο offset
είναι 1.000, ώστε ένα αίτημα dashboard να μη διαβάζει απεριόριστα δεδομένα.
Οι διαθέσιμες περιοχές καταγράφονται στο Redis κατά την εισαγωγή μετρήσεων.
Για μία περιοχή διατίθεται και το
`GET /sensors/regions/{region_id}/recent`.

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

Κάθε fault alert γράφεται πρώτα στο Redis Stream `fault_alert_events`.
Ένας worker ενημερώνει τον αντίστοιχο κόμβο Neo4j και επιβεβαιώνει το event
μόνο μετά την επιτυχή ενημέρωση. Σε προσωρινή αποτυχία Neo4j το event μένει
σε εκκρεμότητα για επανάληψη. Το Pub/Sub εξυπηρετεί μόνο τη ζωντανή
ειδοποίηση. Άγνωστα node IDs μεταφέρονται στο `fault_alerts_dead_letter`.
Η δοκιμαστική εγκατάσταση έχει έναν Neo4j κόμβο και δεν δοκιμάζει εκλογή leader.

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
