from pymongo import MongoClient
from cassandra.cluster import Cluster
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import asyncio
import asyncpg
from neo4j import GraphDatabase
from pathlib import Path
from dotenv import load_dotenv
import os
import zlib
from redis import Redis


load_dotenv(
    Path(__file__).resolve().parents[1] / ".env"
)


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set"
        )

    return value


MONGO_URI = require_env("SCRIPT_MONGO_URI")

def seed_mongo():
    client = MongoClient(MONGO_URI)
    database = client["gridsense"]
    collection = database["equipment"]

    equipment_records = []

    for i in range(1, 41):
        if i <= 10:
            equipment_records.append({
                "asset_id": f"TR{i}",
                "equipment_type": "Transformer",
                "name": f"Transformer {i}",
                "status": "active",
                "location": f"Substation {(i - 1) // 2 + 1}",
                "specifications": {
                    "capacity_kva": 500 + ((i % 6) * 100),
                    "voltage": "110/20 kV",
                },
            })

        elif i <= 20:
            number = i - 10

            equipment_records.append({
                "asset_id": f"SW{number}",
                "equipment_type": "Switch",
                "name": f"Switch {number}",
                "status": "active",
                "location": f"Substation {((number - 1) % 10) + 1}",
                "specifications": {
                    "switch_type": "breaker",
                    "rated_current": 630,
                },
            })

        elif i <= 30:
            number = i - 20

            equipment_records.append({
                "asset_id": f"SEN{number}",
                "equipment_type": "Sensor",
                "name": f"Grid Sensor {number}",
                "status": "active",
                "specifications": {
                    "measurement": [
                        "voltage",
                        "current",
                        "power",
                    ],
                },
            })

        else:
            number = i - 30

            equipment_records.append({
                "asset_id": f"REL{number}",
                "equipment_type": "Relay",
                "name": f"Protection Relay {number}",
                "status": "active",
                "location": f"Feeder {((number - 1) % 5) + 1}",
                "protection_settings": {
                    "trip_current_a": 800 + (number * 10),
                    "curve": "inverse",
                    "auto_reclose": True,
                },
            })

    collection.delete_many({})

    collection.insert_many(equipment_records)

    client.close()

    print(
        f"MongoDB seed completed: "
        f"{len(equipment_records)} equipment records."
    )

CASSANDRA_HOST = require_env("SCRIPT_CASSANDRA_HOST")
CASSANDRA_PORT = int(require_env("SCRIPT_CASSANDRA_PORT"))

def seed_cassandra():
    cluster = Cluster([CASSANDRA_HOST], port=CASSANDRA_PORT)
    session = cluster.connect("gridsense")

    # Clear synthetic seed data so the script can be run again
    # without creating duplicate seed records.
    session.execute("TRUNCATE sensor_readings")
    session.execute("TRUNCATE regional_readings")

    sensor_query = """
    INSERT INTO sensor_readings
    (
        sensor_id,
        date_bucket,
        reading_time,
        region_id,
        metric_type,
        value,
        unit,
        quality_flag
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    regional_query = """
    INSERT INTO regional_readings
    (
        region_id,
        date_bucket,
        shard,
        reading_time,
        sensor_id,
        metric_type,
        value,
        unit,
        quality_flag
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    sensor_prepared = session.prepare(sensor_query)
    regional_prepared = session.prepare(regional_query)

    # 20 sensors * 2500 readings = 50,000 readings
    start_time = datetime.now(timezone.utc) - timedelta(minutes=2499)

    metric_types = [
        ("voltage", "V"),
        ("current", "A"),
        ("power_factor", ""),
        ("temp", "C"),
    ]

    total_readings = 0

    for sensor_number in range(1, 21):
        sensor_id = f"SENSOR{sensor_number:02d}"
        region_id = f"REGION{((sensor_number - 1) % 4) + 1:02d}"

        shard = zlib.crc32(sensor_id.encode("utf-8")) % 16

        for reading_number in range(2500):
            reading_time = start_time + timedelta(minutes=reading_number)

            metric_type, unit = metric_types[
                reading_number % len(metric_types)
            ]

            if metric_type == "voltage":
                value = 230.0 + sensor_number * 0.1

            elif metric_type == "current":
                value = 5.0 + (reading_number % 10) * 0.1

            elif metric_type == "power_factor":
                value = 0.90 + (sensor_number % 8) * 0.01

            else:
                value = 25.0 + (sensor_number % 10) * 0.5

            if reading_number % 500 == 0:
                quality_flag = 2
            elif reading_number % 100 == 0:
                quality_flag = 1
            else:
                quality_flag = 0

            session.execute(
                sensor_prepared,
                (
                    sensor_id,
                    reading_time.date(),
                    reading_time,
                    region_id,
                    metric_type,
                    value,
                    unit,
                    quality_flag,
                ),
            )

            session.execute(
                regional_prepared,
                (
                    region_id,
                    reading_time.date(),
                    shard,
                    reading_time,
                    sensor_id,
                    metric_type,
                    value,
                    unit,
                    quality_flag,
                ),
            )

            total_readings += 1

    cluster.shutdown()
    redis_client = Redis(
        host=require_env("SCRIPT_REDIS_HOST"),
        port=int(require_env("SCRIPT_REDIS_PORT")),
        decode_responses=True,
    )
    redis_client.sadd("sensor_regions", "REGION01", "REGION02", "REGION03", "REGION04")
    redis_client.close()

    print(
        f"Cassandra seed completed: "
        f"{total_readings:,} sensor readings inserted."
    )

NEO4J_URI = require_env("SCRIPT_NEO4J_URI")
NEO4J_USER = require_env("NEO4J_USER")
NEO4J_PASSWORD = require_env("NEO4J_PASSWORD")


def seed_neo4j():
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )

    seed_file = (
        Path(__file__).resolve().parents[1]
        / "neo4j"
        / "import"
        / "seed.cypher"
    )

    script = seed_file.read_text()

    statements = [
        statement.strip()
        for statement in script.split(";")
        if statement.strip()
    ]

    try:
        with driver.session(database="neo4j") as session:
            for statement in statements:
                session.run(statement).consume()
    finally:
        driver.close()

    print(
        f"Neo4j seed completed: "
        f"{len(statements)} Cypher statements executed."
    )

def seed_restore_ties():
    """Add only demo backup ties, without rerunning destructive data seeding."""
    path = Path(__file__).resolve().parents[1] / 'neo4j/import/restore_ties.cypher'
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        with driver.session(database="neo4j") as session:
            session.run(path.read_text()).consume()


POSTGRES_HOST = require_env("SCRIPT_POSTGRES_HOST")
POSTGRES_PORT = int(require_env("SCRIPT_POSTGRES_PORT"))
POSTGRES_USER = require_env("POSTGRES_USER")
POSTGRES_PASSWORD = require_env("POSTGRES_PASSWORD")
POSTGRES_DB = require_env("POSTGRES_DB")

async def seed_postgres():
    connection = await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
    )

    try:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(714032601)")
            schema = Path(__file__).resolve().parents[1] / 'api/db/billing_schema.sql'
            await connection.execute(schema.read_text())
            for i in range(1, 101):
                premise_id = f"PREM{i:03d}"

                await connection.execute(
                    """
                    INSERT INTO consumer_accounts
                        (
                            premise_id,
                            customer_name,
                            address,
                            account_status,
                            balance
                        )
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (premise_id)
                    DO NOTHING
                    """,
                    premise_id,
                    f"Customer {i}",
                    f"Sample Address {i}",
                    "active",
                    Decimal('0.00'),
                )

                # Do not guess the periods or balances of historical invoices.
                if await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM invoices WHERE premise_id=$1 AND billing_period IS NULL)",
                    premise_id,
                ):
                    continue
                amount = Decimal(40 + (i % 60))
                invoice_id = await connection.fetchval(
                    """INSERT INTO invoices
                           (premise_id, amount, billing_period, due_date, description)
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT (premise_id, billing_period) DO NOTHING
                       RETURNING invoice_id""",
                    premise_id, amount, date(2026, 10, 1),
                    datetime(2026, 10, 31, tzinfo=timezone.utc),
                    "Sample monthly electricity invoice",
                )
                if invoice_id is not None:
                    await connection.execute(
                        "UPDATE consumer_accounts SET balance=balance+$2 WHERE premise_id=$1",
                        premise_id, amount,
                    )

    finally:
        await connection.close()

    print("PostgreSQL seed completed: 100 consumer accounts with sample invoices.")


def sensor_data_exists() -> bool:
    cluster = Cluster([CASSANDRA_HOST], port=CASSANDRA_PORT)
    try:
        session = cluster.connect("gridsense")
        return session.execute(
            "SELECT sensor_id FROM sensor_readings LIMIT 1"
        ).one() is not None
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    if os.getenv("BOOTSTRAP_ONLY") == "1" and sensor_data_exists():
        seed_restore_ties()
        print("Existing sensor data found; automatic seed skipped.")
        raise SystemExit(0)

    seed_cassandra()
    seed_mongo()
    seed_neo4j()
    seed_restore_ties()
    asyncio.run(seed_postgres())
