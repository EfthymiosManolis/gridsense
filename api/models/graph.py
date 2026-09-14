from pydantic import BaseModel
from typing import Optional


class GridNode(BaseModel):
    node_id: str
    node_type: str
    name: Optional[str] = None
    properties: dict = {}


class GridRelationship(BaseModel):
    from_node: str
    to_node: str
    relationship_type: str
    properties: dict = {}


class AffectedNode(BaseModel):
    node_id: str
    node_type: str
    name: str
    depth: int


class FaultImpactResponse(BaseModel):
    origin_id: str
    affected_nodes: list[AffectedNode]
    total_affected: int
