import os
import asyncio
import json
import asyncpg
from pymongo import MongoClient


MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://127.0.0.1:27017/gridsense",
)

POSTGRES_HOST = os.getenv(
    "POSTGRES_HOST",
    "127.0.0.1",
)

POSTGRES_PORT = int(
    os.getenv("POSTGRES_PORT", "5432")
)

POSTGRES_USER = os.getenv(
    "POSTGRES_USER",
    "gridsense",
)

POSTGRES_PASSWORD = os.getenv(
    "POSTGRES_PASSWORD",
    "postgrespassword",
)

POSTGRES_DB = os.getenv(
    "POSTGRES_DB",
    "gridsense",
)

MONGO_COLLECTION = "equipment_c4"
POSTGRES_TABLE = "equipment_c4"
RECORD_COUNT = 30

def build_equipment_records():
    records = []

    equipment_types = [
        "SmartMeter",
        "Transformer",
        "Relay",
    ]

    manufacturers = [
        "ABB",
        "Siemens",
        "Schneider",
    ]

    for index in range(1, RECORD_COUNT + 1):
        equipment_type = equipment_types[
            (index - 1) % len(equipment_types)
        ]

        manufacturer = manufacturers[
            (index - 1) % len(manufacturers)
        ]

        if index % 2 == 0:
            firmware_version = (
                f"3.{index % 5}.{index % 10}"
            )
        else:
            firmware_version = (
                f"2.{index % 5}.{index % 10}"
            )

        if equipment_type == "SmartMeter":
            if index % 4 == 1:
                rated_voltage = 230
            else:
                rated_voltage = 240

        elif equipment_type == "Transformer":
            rated_voltage = 11000

        else:
            rated_voltage = 400

        record = {
            "asset_id": f"C4_EQ_{index:03d}",
            "type": equipment_type,
            "name": f"C4 Equipment {index}",
            "rated_voltage": rated_voltage,
            "metadata": {
                "firmware_version": firmware_version,
                "manufacturer": manufacturer,
            },
        }

        records.append(record)

    return records

def seed_mongodb(records):
    client = MongoClient(MONGO_URI)

    try:
        database = client.get_default_database()
        collection = database[MONGO_COLLECTION]

        collection.delete_many({})

        collection.insert_many(records)

        collection.create_index(
            "asset_id",
            unique=True,
        )

        count = collection.count_documents({})

        print(
            f"MongoDB C.4 seed complete: "
            f"{count} records"
        )

    finally:
        client.close()

async def seed_postgresql(records):
    connection = await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
    )

    try:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS equipment_c4 (
                asset_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                rated_voltage INTEGER NOT NULL,
                metadata JSONB NOT NULL
            )
        """)

        await connection.execute(
            "TRUNCATE TABLE equipment_c4"
        )

        rows = [
            (
                record["asset_id"],
                record["type"],
                record["name"],
                record["rated_voltage"],
                json.dumps(record["metadata"]),
            )
            for record in records
        ]

        await connection.executemany("""
            INSERT INTO equipment_c4 (
                asset_id,
                type,
                name,
                rated_voltage,
                metadata
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5::jsonb
            )
        """, rows)

        count = await connection.fetchval(
            "SELECT COUNT(*) FROM equipment_c4"
        )

        print(
            f"PostgreSQL C.4 seed complete: "
            f"{count} records"
        )

    finally:
        await connection.close()


async def main():
    records = build_equipment_records()

    seed_mongodb(records)

    await seed_postgresql(records)


if __name__ == "__main__":
    asyncio.run(main())
