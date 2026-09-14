from fastapi import APIRouter, HTTPException
from api.models.mongo import Equipment
from api.db.mongo import get_mongo_database


router = APIRouter(prefix="/equipment", tags=["Equipment"])


@router.get("/{asset_id}")
async def get_equipment(asset_id: str):
    database = get_mongo_database()

    equipment = await database.equipment.find_one(
        {"asset_id": asset_id},
        {"_id": 0}
    )

    if equipment is None:
        raise HTTPException(
            status_code=404,
            detail="Equipment not found"
        )

    return equipment


@router.post("")
async def create_equipment(equipment: dict):
    database = get_mongo_database()

    asset_id = equipment.get("asset_id")

    if not asset_id:
        raise HTTPException(
            status_code=400,
            detail="asset_id is required"
        )

    existing = await database.equipment.find_one(
        {"asset_id": asset_id}
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Equipment with this asset_id already exists"
        )

    await database.equipment.insert_one(equipment)

    return {
        "message": "Equipment created successfully",
        "asset_id": asset_id
    }


@router.patch("/{asset_id}")
async def update_equipment(
    asset_id: str,
    equipment: dict
):
    database = get_mongo_database()

    if not equipment:
        raise HTTPException(
            status_code=400,
            detail="No fields provided for update"
        )

    result = await database.equipment.update_one(
        {"asset_id": asset_id},
        {"$set": equipment}
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Equipment not found"
        )

    return {
        "message": "Equipment updated successfully",
        "asset_id": asset_id
    }
