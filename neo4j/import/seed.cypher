CREATE CONSTRAINT substation_id_unique IF NOT EXISTS
FOR (s:Substation)
REQUIRE s.substation_id IS UNIQUE;

CREATE CONSTRAINT transformer_asset_id_unique IF NOT EXISTS
FOR (t:Transformer)
REQUIRE t.asset_id IS UNIQUE;

CREATE CONSTRAINT smartmeter_meter_id_unique IF NOT EXISTS
FOR (m:SmartMeter)
REQUIRE m.meter_id IS UNIQUE;

CREATE CONSTRAINT gsp_id_unique IF NOT EXISTS
FOR (g:GridSupplyPoint)
REQUIRE g.gsp_id IS UNIQUE;


MERGE (g:GridSupplyPoint {gsp_id: 'GSP001'})
SET g.name = 'Main Grid Supply Point';


UNWIND range(1, 10) AS i
MERGE (s:Substation {substation_id: 'SUB' + toString(i)})
SET s.name = 'Substation ' + toString(i),
    s.voltage_level = 110;


UNWIND range(1, 40) AS i
MERGE (t:Transformer {asset_id: 'TR' + toString(i)})
SET t.name = 'Transformer ' + toString(i),
    t.capacity_kva = 500 + ((i % 6) * 100);


UNWIND range(1, 200) AS i
MERGE (m:SmartMeter {meter_id: 'MTR' + toString(i)})
SET m.premise_id = 'PREM' + toString(i);

MATCH (g:GridSupplyPoint {gsp_id: 'GSP001'})
MATCH (s:Substation)
WITH g, s, toInteger(substring(s.substation_id, 3)) AS sub_num
MERGE (g)-[r:FEEDS]->(s)
SET r.feeder_id = 'F_' + toString(sub_num),
    r.voltage_kV = 110,
    r.length_km = 1.0 + (sub_num * 0.2);


MATCH (s:Substation)
MATCH (t:Transformer)
WHERE toInteger(substring(t.asset_id, 2)) >=
      ((toInteger(substring(s.substation_id, 3)) - 1) * 4) + 1
  AND toInteger(substring(t.asset_id, 2)) <=
      toInteger(substring(s.substation_id, 3)) * 4
WITH s, t, toInteger(substring(t.asset_id, 2)) AS transformer_num
MERGE (s)-[r:SUPPLIES]->(t)
SET r.cable_id = 'CB_' + toString(transformer_num),
    r.distance_m = 200 + (transformer_num * 10);


MATCH (t:Transformer)
MATCH (m:SmartMeter)
WHERE toInteger(substring(m.meter_id, 3)) >=
      ((toInteger(substring(t.asset_id, 2)) - 1) * 5) + 1
  AND toInteger(substring(m.meter_id, 3)) <=
      toInteger(substring(t.asset_id, 2)) * 5
MERGE (t)-[:CONNECTS_TO]->(m);
