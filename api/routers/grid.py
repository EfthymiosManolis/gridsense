from fastapi import APIRouter, HTTPException
from api.models.graph import GridNode, GridRelationship, FaultImpactResponse
from api.db.neo4j import get_neo4j_driver


router = APIRouter(prefix="/grid", tags=["Grid"])


@router.get("/fault-impact/{node_id}", response_model=FaultImpactResponse)
async def fault_impact(
    node_id: str,
    max_depth: int = 6
):
    if max_depth > 10:
        raise HTTPException(
            status_code=400,
            detail="max_depth cannot exceed 10 to protect query performance"
        )

    if max_depth < 1:
        raise HTTPException(
            status_code=400,
            detail="max_depth must be at least 1"
        )

    driver = await get_neo4j_driver()

    cypher = """
    MATCH (origin)
    WHERE origin.node_id = $node_id
       OR origin.gsp_id = $node_id
       OR origin.substation_id = $node_id
       OR origin.asset_id = $node_id
       OR origin.meter_id = $node_id

    MATCH path = (origin)-[:FEEDS|SUPPLIES|CONNECTS_TO*1..10]->(downstream)
    WHERE length(path) <= $max_depth
      AND all(r IN relationships(path) WHERE NOT coalesce(r.is_open, false)
              AND coalesce(r.available, true))

    WITH downstream, min(length(path)) AS depth

    RETURN
        coalesce(
            downstream.node_id,
            downstream.substation_id,
            downstream.asset_id,
            downstream.meter_id
        ) AS node_id,
        labels(downstream)[0] AS node_type,
        coalesce(
            downstream.name,
            downstream.node_id,
            downstream.substation_id,
            downstream.asset_id,
            downstream.meter_id
        ) AS name,
        depth

    ORDER BY depth
    """

    async with driver.session(database="neo4j") as session:
        result = await session.run(
            cypher,
            node_id=node_id,
            max_depth=max_depth
        )

        records = await result.data()

    if not records:
        check_query = """
        MATCH (n)
        WHERE n.node_id = $node_id
           OR n.gsp_id = $node_id
           OR n.substation_id = $node_id
           OR n.asset_id = $node_id
           OR n.meter_id = $node_id
        RETURN count(n) > 0 AS exists
        """

        async with driver.session(database="neo4j") as session:
            check_result = await session.run(
                check_query,
                node_id=node_id
            )

            check_record = await check_result.single()

        if not check_record["exists"]:
            raise HTTPException(
                status_code=404,
                detail=f"Node '{node_id}' not found in topology graph"
            )

    affected = [
        {
            "node_id": record["node_id"],
            "node_type": record["node_type"],
            "name": record["name"],
            "depth": record["depth"]
        }
        for record in records
    ]

    return FaultImpactResponse(
        origin_id=node_id,
        affected_nodes=affected,
        total_affected=len(affected)
    )


@router.get("/restore-paths/{node_id}")
async def restore_paths(node_id: str):
    """Propose healthy topology paths that need a normally open tie closed.

    These are candidates for operator review, not electrical feasibility checks
    or commands to operate switches. A physically faulted target is excluded.
    """
    driver = await get_neo4j_driver()
    async with driver.session(database="neo4j") as session:
        result = await session.run(
            """MATCH (n)
               WHERE n.node_id=$node_id OR n.gsp_id=$node_id
                  OR n.substation_id=$node_id OR n.asset_id=$node_id
                  OR n.meter_id=$node_id
               RETURN elementId(n) AS id LIMIT 2""", node_id=node_id)
        targets = await result.data()
        if not targets:
            raise HTTPException(status_code=404, detail="Topology node not found")
        if len(targets) > 1:
            raise HTTPException(status_code=409, detail="Ambiguous topology node ID")
        result = await session.run(
            """MATCH path = (source:GridSupplyPoint)
                     -[:FEEDS|SUPPLIES|CONNECTS_TO*1..10]->(target)
               WHERE elementId(target) = $target_id
                 AND all(n IN nodes(path) WHERE coalesce(n.available, true)
                         AND NOT coalesce(n.fault_alert_active, false))
                 AND all(r IN relationships(path) WHERE coalesce(r.available, true)
                         AND NOT coalesce(r.fault_alert_active, false)
                         AND (NOT coalesce(r.is_open, false) OR coalesce(r.switchable, false)))
                 AND any(r IN relationships(path) WHERE coalesce(r.is_open, false))
                 AND all(n IN nodes(path) WHERE single(m IN nodes(path) WHERE m = n))
               WITH path,
                    [n IN nodes(path) | coalesce(n.node_id, n.gsp_id,
                       n.substation_id, n.asset_id, n.meter_id)] AS ids
               WHERE all(id IN ids WHERE id IS NOT NULL)
               RETURN ids AS restore_path,
                      [r IN relationships(path) WHERE coalesce(r.is_open, false) |
                        {from_node: coalesce(startNode(r).node_id, startNode(r).gsp_id,
                            startNode(r).substation_id, startNode(r).asset_id, startNode(r).meter_id),
                         to_node: coalesce(endNode(r).node_id, endNode(r).gsp_id,
                            endNode(r).substation_id, endNode(r).asset_id, endNode(r).meter_id),
                         relationship_id: elementId(r), action: 'close'}] AS required_switches
               ORDER BY length(path), ids LIMIT 50""",
            target_id=targets[0]['id'],
        )
        candidates = await result.data()
    return {
        "node_id": node_id,
        "restore_paths": [item['restore_path'] for item in candidates],
        "candidates": candidates,
        "requires_operator_validation": True,
    }


@router.post("/nodes")
async def create_node(node: GridNode):
    allowed_node_types = {
        "GridSupplyPoint",
        "Substation",
        "Transformer",
        "SmartMeter",
    }

    if node.node_type not in allowed_node_types:
        raise HTTPException(
            status_code=400,
            detail=(
                "node_type must be one of: "
                "GridSupplyPoint, Substation, "
                "Transformer, SmartMeter"
            ),
        )

    driver = await get_neo4j_driver()

    label = node.node_type

    query = f"""
    CREATE (n:{label} {{
        node_id: $node_id,
        node_type: $node_type,
        name: $name
    }})
    SET n += $properties
    RETURN n
    """

    async with driver.session(database="neo4j") as session:
        result = await session.run(
            query,
            node_id=node.node_id,
            node_type=node.node_type,
            name=node.name,
            properties=node.properties,
        )

        record = await result.single()

    return {
        "message": "Grid node created successfully",
        "node_id": record["n"]["node_id"],
    }

@router.post("/relationships")
async def create_relationship(relationship: GridRelationship):
    allowed_relationship_types = {
        "FEEDS",
        "SUPPLIES",
        "CONNECTS_TO",
    }

    if relationship.relationship_type not in allowed_relationship_types:
        raise HTTPException(
            status_code=400,
            detail=(
                "relationship_type must be one of: "
                "FEEDS, SUPPLIES, CONNECTS_TO"
            ),
        )

    driver = await get_neo4j_driver()

    relationship_type = relationship.relationship_type

    query = f"""
    MATCH (source), (target)
    WHERE (
        source.node_id = $from_node
        OR source.gsp_id = $from_node
        OR source.substation_id = $from_node
        OR source.asset_id = $from_node
        OR source.meter_id = $from_node
    )
    AND (
        target.node_id = $to_node
        OR target.gsp_id = $to_node
        OR target.substation_id = $to_node
        OR target.asset_id = $to_node
        OR target.meter_id = $to_node
    )

    CREATE (source)-[r:{relationship_type}]->(target)
    SET r += $properties

    RETURN
        type(r) AS relationship_type,
        $from_node AS from_node,
        $to_node AS to_node
    """

    async with driver.session(database="neo4j") as session:
        result = await session.run(
            query,
            from_node=relationship.from_node,
            to_node=relationship.to_node,
            properties=relationship.properties,
        )

        record = await result.single()

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Source or target node not found",
        )

    return {
        "message": "Grid relationship created successfully",
        "from_node": record["from_node"],
        "to_node": record["to_node"],
        "relationship_type": record["relationship_type"],
    }
