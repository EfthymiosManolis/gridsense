from pymongo import MongoClient
from cassandra.cluster import Cluster
from datetime import datetime, timedelta, timezone
import asyncio
import asyncpg
from neo4j import GraphDatabase
from pathlib import Path
from dotenv import dotenv_values
import os

ENV = dotenv_values(Path(__file__).resolve().parents[1] / ".env")

MONGO_URI = os.getenv("MONGO_URI","mongodb://127.0.0.1:27017/gridsense")

def seed_mongo():
    client = MongoClient(MONGO_URI)
    database = client["gridsense"]
    collection = database["equipment"]

    equipment_records = []

    for i in range(1, 41):
        if i <= 15:
            equipment_records.append({
                "asset_id": f"TR{i}",
                "equipment_type": "Transformer",
                "name": f"Transformer {i}",
                "status": "active",
                "location": f"Substation {(i - 1) // 4 + 1}",
                "specifications": {
                    "capacity_kva": 500 + ((i % 6) * 100),
                    "voltage": "110/20 kV"
                }
            })

        elif i <= 30:
            equipment_records.append({
                "asset_id": f"SW{i - 15}",
                "equipment_type": "Switch",
                "name": f"Switch {(i - 15)}",
                "status": "active",
                "location": f"Substation {((i - 16) % 10) + 1}",
                "specifications": {
                    "switch_type": "breaker",
                    "rated_current": 630
                }
            })

        else:
            equipment_records.append({
                "asset_id": f"SEN{i - 30}",
                "equipment_type": "Sensor",
                "name": f"Grid Sensor {i - 30}",
                "status": "active",
                "specifications": {
                    "measurement": ["voltage", "current", "power"]
                }
            })

    for record in equipment_records:
        collection.update_one(
            {"asset_id": record["asset_id"]},
            {"$set": record},
            upsert=True
        )

    client.close()

    print(f"MongoDB seed completed: {len(equipment_records)} equipment records.")

CASSANDRA_HOST = os.getenv("CASSANDRA_HOST", "127.0.0.1")
CASSANDRA_PORT = int(os.getenv("CASSANDRA_PORT", "9042"))


def seed_cassandra():
    cluster = Cluster([CASSANDRA_HOST], port=CASSANDRA_PORT)
    session = cluster.connect("gridsense")

    # Clear synthetic seed data so the script can be run again
    # without creating duplicate seed records.
    session.execute("TRUNCATE sensor_readings")
    session.execute("TRUNCATE dashboard_readings")

    sensor_query = """
    INSERT INTO sensor_readings
    (
        sensor_id,
        reading_time,
        metric_type,
        value,
        unit,
        quality_flag
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """

    dashboard_query = """
    INSERT INTO dashboard_readings
    (
        bucket_minute,
        shard,
        reading_time,
        sensor_id,
        metric_type,
        value,
        unit,
        quality_flag
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    sensor_prepared = session.prepare(sensor_query)
    dashboard_prepared = session.prepare(dashboard_query)

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

        # Spread dashboard writes across 16 partitions per minute
        shard = (sensor_number - 1) % 16

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
                    reading_time,
                    metric_type,
                    value,
                    unit,
                    quality_flag,
                ),
            )

            bucket_minute = reading_time.replace(
                second=0,
                microsecond=0
            )

            session.execute(
                dashboard_prepared,
                (
                    bucket_minute,
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

    print(
        f"Cassandra seed completed: "
        f"{total_readings:,} sensor readings inserted."
    )



NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or ENV.get("NEO4J_PASSWORD") or "neo4jpassword"


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

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER") or ENV.get("POSTGRES_USER") or "gridsense"
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD") or ENV.get("POSTGRES_PASSWORD") or "postgrespassword"
POSTGRES_DB = os.getenv("POSTGRES_DB") or ENV.get("POSTGRES_DB") or "gridsense"


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
                    DO UPDATE SET
                        customer_name = EXCLUDED.customer_name,
                        address = EXCLUDED.address,
                        account_status = EXCLUDED.account_status,
                        balance = EXCLUDED.balance
                    """,
                    premise_id,
                    f"Customer {i}",
                    f"Sample Address {i}",
                    "active",
                    float((i * 7) % 150),
                )

                description = "Sample monthly electricity invoice"
                due_date = datetime(2026, 10, 31, tzinfo=timezone.utc)
                amount = float(40 + (i % 60))

                exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM invoices
                        WHERE premise_id = $1
                          AND due_date = $2
                          AND description = $3
                    )
                    """,
                    premise_id,
                    due_date,
                    description,
                )

                if not exists:
                    await connection.execute(
                        """
                        INSERT INTO invoices
                            (
                                premise_id,
                                amount,
                                due_date,
                                description
                            )
                        VALUES ($1, $2, $3, $4)
                        """,
                        premise_id,
                        amount,
                        due_date,
                        description,
                    )

    finally:
        await connection.close()

    print("PostgreSQL seed completed: 100 consumer accounts with sample invoices.")


if __name__ == "__main__":
    seed_cassandra()
    seed_mongo()
    seed_neo4j()
    asyncio.run(seed_postgres())
