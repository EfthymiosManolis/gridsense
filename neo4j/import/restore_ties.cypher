// Demo backup supply for MTR1..MTR5 via TR5/SUB2 when TR1/SUB1 fails.
// Closed/open state is never reset when this script is repeated.
MATCH (backup:Transformer {asset_id: 'TR5'})
UNWIND range(1, 5) AS i
MATCH (meter:SmartMeter {meter_id: 'MTR' + toString(i)})
MERGE (backup)-[tie:CONNECTS_TO {tie_id: 'BACKUP_TR5_MTR' + toString(i)}]->(meter)
ON CREATE SET tie.is_open = true, tie.switchable = true, tie.available = true;
