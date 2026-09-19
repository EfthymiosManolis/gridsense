# GridSense

Το GridSense είναι ένα prototype σύστημα smart power grid analytics και fault management, υλοποιημένο στο πλαίσιο του μαθήματος Advanced Data Management.

Η εφαρμογή συνδυάζει Cassandra, Neo4j, MongoDB, PostgreSQL και Redis πίσω από ένα FastAPI REST API.

## Αρχιτεκτονική

| Ρόλος | Τεχνολογία | Χρήση |
| --- | --- | --- |
| Time-series δεδομένα | Cassandra 4.1 | Sensor readings και relay events |
| Τοπολογία δικτύου | Neo4j 5 Community | Graph traversals και fault propagation |
| Equipment metadata | MongoDB 7 | Ευέλικτα και ετερογενή metadata |
| Billing | PostgreSQL 15 | Consumer accounts και ACID invoices |
| Cache και alerts | Redis 7 | Cached summaries, Streams και Pub/Sub |
| REST API | FastAPI / Python 3.11 | Πρόσβαση στις υπηρεσίες μέσω HTTP |

## Απαιτήσεις

Για την εκτέλεση απαιτούνται:

- Docker
- Docker Compose
- Git

Για τα προαιρετικά host-side scripts και benchmarks απαιτείται επιπλέον Python 3.11+.

## Ρύθμιση περιβάλλοντος

Το GridSense χρησιμοποιεί αρχείο `.env` για τα credentials και τις ρυθμίσεις σύνδεσης των υπηρεσιών.

Δημιούργησε το τοπικό `.env` από το template:

```bash
cp .env.example .env
```

Το `.env` αγνοείται από το Git και δεν πρέπει να γίνεται commit.

Οι βασικές μεταβλητές περιλαμβάνουν:

- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`

Το ίδιο `.env` χρησιμοποιείται από το Docker Compose και από τα host-side utility και benchmark scripts.

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

Το Docker Compose περιμένει να γίνουν healthy οι βάσεις, δημιουργεί το Cassandra schema, εκτελεί αυτόματα το seed και στη συνέχεια ξεκινά το API.

Έλεγχος της κατάστασης όλων των containers:

```bash
docker compose ps -a
```

Τα `cassandra-init` και `seed` είναι one-shot initialization services. Η κατάσταση `Exited (0)` σημαίνει ότι ολοκληρώθηκαν επιτυχώς.

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
curl -sS -w '\nHTTP %{http_code}\n' \
  http://localhost:8000/health
```

Αναμένεται `HTTP 200`.

## Services

### Κύριες υπηρεσίες

| Service | Technology | Port | Purpose |
| --- | --- | ---: | --- |
| `api` | FastAPI / Python 3.11 | 8000 | REST API gateway και business logic |
| `timeseries-db` | Cassandra 4.1 | 9042 | Sensor readings και relay events |
| `graph-db` | Neo4j 5 Community | 7474 / 7687 | Τοπολογία δικτύου και graph traversals |
| `catalog-db` | MongoDB 7 | 27017 | Equipment metadata |
| `billing-db` | PostgreSQL 15 | 5432 | Consumer accounts και billing records |
| `cache` | Redis 7 Alpine | 6379 | Cache, Redis Streams και Pub/Sub alerts |

### Υπηρεσίες αρχικοποίησης

| Service | Purpose |
| --- | --- |
| `cassandra-init` | Εκτελεί το `cql/init.cql` μετά την εκκίνηση της Cassandra |
| `seed` | Εισάγει αυτόματα τα αρχικά δοκιμαστικά δεδομένα πριν ξεκινήσει το API |

Τα δεδομένα των βάσεων διατηρούνται σε Docker persistent volumes.

## Αυτόματη αρχικοποίηση και Seed Data

Σε καθαρή εγκατάσταση:

1. Το `cassandra-init` δημιουργεί το Cassandra keyspace και τους πίνακες.
2. Το PostgreSQL εκτελεί το `postgres/init.sql`.
3. Η υπηρεσία `seed` εισάγει τα αρχικά δεδομένα.
4. Το API ξεκινά μόνο αφού ολοκληρωθεί επιτυχώς το seed.

Το dataset περιλαμβάνει:

- 50.000 Cassandra sensor readings σε 20 διαφορετικά sensor IDs
- 10 Neo4j substations
- 40 Neo4j transformers
- 200 Neo4j smart meters και τις μεταξύ τους relationships
- 40 MongoDB equipment records σε 4 διαφορετικά equipment types
- 100 PostgreSQL consumer accounts με sample invoices

Αν υπάρχουν ήδη sensor readings, το αυτόματο bootstrap seed παραλείπει την επανεισαγωγή τους ώστε να διατηρηθούν τα υπάρχοντα δεδομένα.

Για προαιρετική χειροκίνητη εκτέλεση του seed:

```bash
python scripts/seed.py
```

Η χειροκίνητη εκτέλεση επαναδημιουργεί τα συνθετικά Cassandra sensor και regional readings. Δεν πρέπει να χρησιμοποιείται πάνω σε πραγματικά δεδομένα που πρέπει να διατηρηθούν.

Το seed script είναι idempotent ως προς τα seed records και η επανεκτέλεσή του δεν δημιουργεί duplicate logical records.

Ένα υπάρχον Cassandra volume διατηρεί το προηγούμενο schema. Το `CREATE TABLE IF NOT EXISTS` δεν μεταβάλλει αυτόματα τη δομή ενός ήδη υπάρχοντος πίνακα.

## Data Models

### Cassandra

Το `sensor_readings` εξυπηρετεί αναζητήσεις με βάση έναν sensor και ένα χρονικό διάστημα.

```text
Partition key:
(sensor_id, date_bucket)

Clustering columns:
reading_time, metric_type
```

Το `date_bucket` είναι ημερομηνία UTC και περιορίζει το μέγεθος κάθε partition.

Τα readings έχουν TTL 90 ημερών:

```text
default_time_to_live = 7776000
```

Το `regional_readings` εξυπηρετεί το cross-network dashboard query pattern.

```text
Partition key:
(region_id, date_bucket, shard)
```

Το `shard` κατανέμει τις εγγραφές μιας περιοχής σε περισσότερα partitions και περιορίζει τα hot partitions.

Το `relay_events` αποθηκεύει τη χρονική ακολουθία των relay operations με `TIMEUUID`, ώστε τα events κάθε feeder να διατηρούνται σε αιτιακή σειρά.

### Neo4j

Η βασική τοπολογία του δικτύου είναι:

```text
GridSupplyPoint
    └── FEEDS
        Substation
            └── SUPPLIES
                Transformer
                    └── CONNECTS_TO
                        SmartMeter
```

Τα βασικά ID properties είναι:

| Node label | ID property |
| --- | --- |
| `GridSupplyPoint` | `gsp_id` |
| `Substation` | `substation_id` |
| `Transformer` | `asset_id` |
| `SmartMeter` | `meter_id` |

Τα βασικά relationship types είναι:

- `FEEDS`
- `SUPPLIES`
- `CONNECTS_TO`

Το fault-impact traversal είναι bounded. Το `max_depth` πρέπει να είναι από 1 έως 10 και έχει προεπιλεγμένη τιμή 6.

## REST API Endpoints

| Method | Endpoint | Backend |
| --- | --- | --- |
| `POST` | `/sensors/readings` | Cassandra |
| `GET` | `/sensors/{sensor_id}/readings` | Cassandra |
| `GET` | `/sensors/{sensor_id}/summary` | Redis / Cassandra |
| `GET` | `/grid/fault-impact/{node_id}` | Neo4j |
| `GET` | `/grid/restore-paths/{node_id}` | Neo4j |
| `POST` | `/grid/nodes` | Neo4j |
| `POST` | `/grid/relationships` | Neo4j |
| `GET` | `/equipment/{asset_id}` | MongoDB |
| `POST` | `/equipment` | MongoDB |
| `PATCH` | `/equipment/{asset_id}` | MongoDB |
| `GET` | `/billing/account/{premise_id}` | PostgreSQL |
| `POST` | `/billing/invoice` | PostgreSQL |
| `GET` | `/alerts/active` | Redis |
| `POST` | `/alerts/publish` | Redis |

## Δοκιμαστική λειτουργία των B.7 endpoints

Οι παρακάτω εντολές χρησιμοποιήθηκαν για τον έλεγχο των mandatory endpoints.

Εκτέλεσέ τες με τη σειρά στο ίδιο Bash terminal. Το μοναδικό `B7_RUN_ID` επιτρέπει την επανάληψη των δοκιμών χωρίς σύγκρουση με παλιότερα test records.

### Προετοιμασία

```bash
BASE_URL="http://localhost:8000"
B7_RUN_ID="$(date -u +%Y%m%d%H%M%S)_${RANDOM}"

B7_SENSOR="B7_SENSOR_${B7_RUN_ID}"
B7_REGION="B7_TEST_REGION"
B7_METER="B7_METER_${B7_RUN_ID}"
B7_EQUIPMENT="B7_EQ_${B7_RUN_ID}"
B7_INVOICE="B7_INVOICE_${B7_RUN_ID}"
B7_ALERT="B7_ALERT_${B7_RUN_ID}"
```

### 1. Εισαγωγή sensor reading

```bash
B7_READING_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

curl -sS -w '\nHTTP %{http_code}\n' \
  -X POST "$BASE_URL/sensors/readings" \
  -H "Content-Type: application/json" \
  -d "{
    \"sensor_id\": \"$B7_SENSOR\",
    \"region_id\": \"$B7_REGION\",
    \"reading_time\": \"$B7_READING_TIME\",
    \"metric_type\": \"voltage\",
    \"value\": 231.5,
    \"unit\": \"V\",
    \"quality_flag\": 0
  }"
```

Αναμένεται `HTTP 200` και `"inserted": 1`.

### 2. Ανάκτηση sensor readings

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/sensors/$B7_SENSOR/readings?limit=10"
```

Η απάντηση πρέπει να περιλαμβάνει τη μέτρηση με `value: 231.5`.

### 3. Ανάκτηση cached sensor summary

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/sensors/$B7_SENSOR/summary"
```

Επανάληψη του ίδιου αιτήματος:

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/sensors/$B7_SENSOR/summary"
```

Αναμένεται `HTTP 200` και στις δύο κλήσεις. Η αναλυτική μέτρηση cache hit και cache miss πραγματοποιείται στο benchmark C.3.

### 4. Fault impact

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/grid/fault-impact/GSP001?max_depth=6"
```

Αναμένεται `HTTP 200` και λίστα `affected_nodes`.

Έλεγχος validation του `max_depth`:

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/grid/fault-impact/GSP001?max_depth=11"
```

Αναμένεται `HTTP 400`.

Έλεγχος ανύπαρκτου κόμβου:

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/grid/fault-impact/B7_NONEXISTENT_NODE?max_depth=6"
```

Αναμένεται `HTTP 404`.

### 5. Restore paths

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/grid/restore-paths/MTR1"
```

Αναμένεται `HTTP 200` και διαδρομή που περιλαμβάνει το `MTR1`.

### 6. Δημιουργία Neo4j node

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  -X POST "$BASE_URL/grid/nodes" \
  -H "Content-Type: application/json" \
  -d "{
    \"node_id\": \"$B7_METER\",
    \"node_type\": \"SmartMeter\",
    \"name\": \"B7 Test Meter\",
    \"properties\": {
      \"meter_id\": \"$B7_METER\"
    }
  }"
```

Αναμένεται `HTTP 200`.

### 7. Δημιουργία Neo4j relationship

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  -X POST "$BASE_URL/grid/relationships" \
  -H "Content-Type: application/json" \
  -d "{
    \"from_node\": \"TR1\",
    \"to_node\": \"$B7_METER\",
    \"relationship_type\": \"CONNECTS_TO\",
    \"properties\": {
      \"test\": true
    }
  }"
```

Αναμένεται `HTTP 200`.

Επιβεβαίωση της σύνδεσης:

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/grid/fault-impact/TR1?max_depth=1"
```

Ο νέος smart meter πρέπει να εμφανίζεται στην απόκριση.

### 8. Ανάκτηση equipment

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/equipment/TR1"
```

Αναμένεται `HTTP 200` και τα metadata του `TR1`.

### 9. Δημιουργία equipment

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  -X POST "$BASE_URL/equipment" \
  -H "Content-Type: application/json" \
  -d "{
    \"asset_id\": \"$B7_EQUIPMENT\",
    \"equipment_type\": \"Sensor\",
    \"name\": \"B7 Test Equipment\",
    \"status\": \"active\",
    \"specifications\": {
      \"measurement\": [\"voltage\"]
    }
  }"
```

Αναμένεται `HTTP 200`.

Επιβεβαίωση αποθήκευσης:

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/equipment/$B7_EQUIPMENT"
```

### 10. Ενημέρωση equipment

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  -X PATCH "$BASE_URL/equipment/$B7_EQUIPMENT" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "maintenance",
    "test_note": "B7 patch test"
  }'
```

Αναμένεται `HTTP 200`.

Επιβεβαίωση ενημέρωσης:

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/equipment/$B7_EQUIPMENT"
```

Η εγγραφή πρέπει να περιλαμβάνει `"status": "maintenance"`.

### 11. Ανάκτηση billing account

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/billing/account/PREM001"
```

Αναμένεται `HTTP 200`.

### 12. Δημιουργία invoice

```bash
B7_DUE_DATE="$(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)"

curl -sS -w '\nHTTP %{http_code}\n' \
  -X POST "$BASE_URL/billing/invoice" \
  -H "Content-Type: application/json" \
  -d "{
    \"premise_id\": \"PREM001\",
    \"amount\": 12.34,
    \"due_date\": \"$B7_DUE_DATE\",
    \"description\": \"$B7_INVOICE\"
  }"
```

Αναμένεται `HTTP 200`.

Ανάκτησε ξανά τον λογαριασμό:

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/billing/account/PREM001"
```

### 13. Δημοσίευση alert

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  -X POST "$BASE_URL/alerts/publish" \
  -H "Content-Type: application/json" \
  -d "{
    \"severity\": \"warning\",
    \"message\": \"$B7_ALERT\",
    \"node_id\": \"$B7_METER\"
  }"
```

Αναμένεται `HTTP 200`.

### 14. Ανάκτηση ενεργών alerts

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  "$BASE_URL/alerts/active"
```

Αναμένεται `HTTP 200` και alert με `message` ίσο με την τιμή του `B7_ALERT`.

Οι παραπάνω POST και PATCH δοκιμές δημιουργούν records με prefix `B7_`. Τα μοναδικά IDs αποτρέπουν συγκρούσεις σε επόμενη εκτέλεση.

## Επιπλέον API endpoints

Ανάκτηση πρόσφατων readings ολόκληρου του δικτύου:

```bash
curl -sS \
  "$BASE_URL/sensors/network/recent?limit=100&offset=0"
```

Η απάντηση περιλαμβάνει:

- `as_of`
- `has_more`
- `readings`

Για διαδοχικές σελίδες πρέπει να χρησιμοποιείται η ίδια τιμή `as_of`. Το μέγιστο offset είναι 1.000.

Ανάκτηση πρόσφατων readings συγκεκριμένης περιοχής:

```bash
curl -sS \
  "$BASE_URL/sensors/regions/B7_TEST_REGION/recent"
```

## Benchmarks — Part C

Δημιούργησε Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r scripts/requirements.txt
```

### C.1 — Cassandra consistency levels

```bash
python scripts/benchmark_cassandra.py
```

Το benchmark μετρά sustained write throughput και p50/p95 latency για:

- `ONE`
- `LOCAL_QUORUM`
- `ALL`

Το development environment χρησιμοποιεί single-node Cassandra με replication factor 1. Τα αποτελέσματα δεν αντιπροσωπεύουν πλήρες production cluster με RF=3.

### C.2 — Neo4j traversal depth

```bash
python scripts/benchmark_neo4j.py
```

Το benchmark μετρά το end-to-end HTTP latency του:

```text
/grid/fault-impact/{node_id}
```

για διαφορετικά traversal depths και καταγράφει median και p95 latency.

Δημιουργείται επίσης το διάγραμμα:

```text
c2_graph_traversal_latency.png
```

Το seeded graph έχει λίγες εκατοντάδες nodes και τα αποτελέσματα δεν γενικεύονται αυτόματα σε production topology 26.000 nodes.

### C.3 — Redis cache effectiveness

```bash
python scripts/benchmark_redis.py
```

Το benchmark στέλνει requests στο:

```text
/sensors/SENSOR01/summary
```

και συγκρίνει warm-cache και cold-cache συμπεριφορά με TTL 30 δευτερολέπτων.

Καταγράφονται:

- p50 latency
- p95 latency
- p99 latency
- cache hit rate

Χρησιμοποιείται σταθερό sensor ID ώστε το cache key να παραμένει ελεγχόμενη μεταβλητή.

### C.4 — MongoDB vs PostgreSQL JSONB

Δημιούργησε τα ίδια 30 equipment records και στις δύο βάσεις:

```bash
python scripts/seed_c4.py
```

Εκτέλεσε το benchmark:

```bash
python scripts/benchmark_c4.py
```

Το benchmark συγκρίνει τις ίδιες queries σε MongoDB και PostgreSQL JSONB και υπολογίζει τον μέσο χρόνο 10 measured runs ανά query.

Το μικρό synthetic dataset δεν επαρκεί για γενικό συμπέρασμα υπεροχής ενός DBMS.

Τα πλήρη αποτελέσματα, η μεθοδολογία, οι controlled variables, τα confounds και η ερμηνεία των πειραμάτων παρουσιάζονται στο γραπτό report.

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

Κάθε fault alert γράφεται πρώτα στο Redis Stream:

```text
fault_alert_events
```

Ένας worker ενημερώνει τον αντίστοιχο Neo4j node και επιβεβαιώνει το event μόνο μετά την επιτυχή ενημέρωση.

Σε προσωρινή αποτυχία του Neo4j, το event παραμένει σε εκκρεμότητα για επανάληψη. Άγνωστα node IDs μεταφέρονται στο:

```text
fault_alerts_dead_letter
```

Το Redis Pub/Sub χρησιμοποιείται για τη ζωντανή ειδοποίηση και όχι ως durable event store.

Η development εγκατάσταση χρησιμοποιεί έναν Neo4j node και δεν προσομοιώνει leader election.

## Δομή repository

```text
gridsense/
├── api/
│   ├── main.py
│   ├── fault_worker.py
│   ├── routers/
│   │   ├── sensors.py
│   │   ├── grid.py
│   │   ├── equipment.py
│   │   ├── billing.py
│   │   └── alerts.py
│   ├── models/
│   ├── db/
│   ├── Dockerfile
│   └── requirements.txt
├── cql/
│   └── init.cql
├── neo4j/
│   └── import/
├── postgres/
│   └── init.sql
├── scripts/
│   ├── seed.py
│   ├── benchmark_cassandra.py
│   ├── benchmark_neo4j.py
│   ├── benchmark_redis.py
│   ├── seed_c4.py
│   ├── benchmark_c4.py
│   └── requirements.txt
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

## Τερματισμός

Τερματισμός των containers:

```bash
docker compose down
```

Τερματισμός και πλήρης διαγραφή των persistent volumes:

```bash
docker compose down -v
```

Η δεύτερη εντολή διαγράφει όλα τα τοπικά δεδομένα Cassandra, Neo4j, MongoDB, PostgreSQL και Redis. Στην επόμενη εκκίνηση το schema και τα seed δεδομένα δημιουργούνται ξανά από την αρχή.
