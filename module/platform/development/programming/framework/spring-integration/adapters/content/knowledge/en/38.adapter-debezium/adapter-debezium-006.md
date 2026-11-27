# Schema Change Events in Debezium

## 1. When Table Structure Changes, What Does the CDC Pipeline Know?

Applications use **Spring Integration Adapters** to connect external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s. When syncing data from MySQL or PostgreSQL, Debezium captures changes from the transaction log and sends events over Kafka (or another event delivery mechanism) into a Spring Integration flow. Beyond **row data** changes such as inserts, updates, and deletes, the source table structure itself can also change:

~~~sql
ALTER TABLE sales.orders
    ADD COLUMN coupon_code VARCHAR(32) NULL;
~~~

After this statement, rows in `sales.orders` can carry an extra `coupon_code` attribute. A target application still using a DTO with only `id`, `status`, and `total` might:

- Ignore the new field if the converter/logic allows it.
- Fail to deserialize messages if schema checks are too strict.
- Omit persisting the new data even though Debezium captured the change.
- Misread records if a column is renamed, changes type, or is dropped before the downstream contract is updated.

For connectors that support it, a **schema change event** is a notification describing a source structure change, typically originating from DDL statements such as `CREATE TABLE`, `ALTER TABLE`, or `DROP TABLE`. It helps systems observe schema evolution and prepare downstream changes. However, **not every Debezium connector emits DDL notifications in the same way**.

**Lesson objective:** after this lesson, you will be able to distinguish schema change events from row change events, Kafka Connect schemas, and internal schema history; understand MySQL configuration/event examples; evaluate schema compatibility; and design safe handling branches when feeding events into Spring Integration.

## 2. Distinguishing Four Concepts Commonly Called "Schema"

| Concept | Core Content | Who Uses It? | Key Takeaway |
|---|---|---|---|
| **Schema change event** | Notification of a source structural change, e.g., DDL statement and table metadata | Monitoring, schema governance, orchestration pipelines | Emitted by connectors that support it; format is not uniform across all connectors |
| **Row change event** | Data event `c`, `u`, `d`, `r` with `before`, `after`, and `source` metadata | CDC processing services, data sinks, caches, search indexes | When table structure changes, `before`/`after` shape may change accordingly |
| **Kafka Connect record schema** | Field/type descriptor of a message used by converters when schemas are enabled | Converters, deserializers, Schema Registry (depending on config) | Data type metadata **is not the same** as a DDL event |
| **Internal schema history** | Historical schema state needed by some Debezium connectors to decode log records during recovery | The Debezium connector itself | Internal operational state; do not consume as a business topic |

For example, when adding `coupon_code`:

1. The database executes the DDL, altering the source schema.
2. A supporting Debezium connector updates its schema knowledge and may record it in **internal schema history**.
3. If the connector supports and enables schema change events, it can emit a separate DDL notification.
4. Subsequent **row change events** can carry `coupon_code` in `after`; the message schema may also change.

These steps serve distinct purposes. Do not expect that subscribing to a schema change topic will automatically update target tables or Java DTOs. Nor should the absence of a schema change topic be taken as proof that no DDL ran on the database.

### 2.1. Schema Change Event Differs from `op = "u"`

A row event `op = "u"` means **a row was updated**. An `ALTER TABLE` DDL changes **table structure**, not an `u` record for each existing row. Adding a column with a default may alter how values are observed, but you should not assume Debezium will emit an update event for every existing row.

### 2.2. Schema Change Event Differs from Schema Registry

A connector emitting DDL notifications can work with Kafka JSON Converter, Avro Converter, Protobuf Converter, or other formats. **Schema Registry** (when used) manages serialization schemas by subject/version; a Debezium schema change event describes a structural operation on the database. An `ALTER TABLE` may lead to a new schema version in the Registry when the converter registers the updated schema, but there is no strict one-to-one mapping. A Registry schema can also change due to event representation changes without any corresponding DDL.

## 3. Typical Flow of a MySQL Schema Change Event

With the **Debezium MySQL connector**, DDL statements are read from the binlog and used by the connector to maintain schema state. Depending on configuration, the connector can emit schema change events to a dedicated Kafka topic.

~~~mermaid
flowchart LR
    DB[(MySQL)] -->|DDL in binlog| DZ[Debezium MySQL connector]
    DZ -->|Updates internal history| HIST[(Internal schema history topic)]
    DZ -->|Schema change event| SC[(Schema change topic)]
    DZ -->|Data change events| ROW[(Row CDC topic)]
    SC --> SI1[Spring Integration<br/>schema monitoring flow]
    ROW --> SI2[Spring Integration<br/>row processing flow]
    SI1 --> AUDIT[(Audit / alert)]
    SI2 --> SINK[(Projection / target system)]
~~~

Suppose:

- `topic.prefix = shop-cdc`;
- database `sales`, table `orders`;
- the MySQL connector writes row data to a topic like `shop-cdc.sales.orders`;
- the connector emits schema notifications to the topic named after the logical server/topic prefix `shop-cdc`;
- internal schema history uses a **different** topic, e.g., `schemahistory.shop-cdc`.

Exact topic names depend on the connector, routing config, version, and any Single Message Transforms (SMTs) in use. The topics above represent **one typical MySQL setup**, not a universal rule for PostgreSQL, SQL Server, Oracle, or every sink.

### 3.1. Reference Configuration

The fields below are an **excerpt** of Debezium MySQL configuration on Kafka Connect; connection details, credentials, source privileges, and other required properties are omitted:

~~~json
{
  "name": "orders-mysql-cdc",
  "config": {
    "connector.class": "io.debezium.connector.mysql.MySqlConnector",
    "topic.prefix": "shop-cdc",
    "database.include.list": "sales",
    "table.include.list": "sales.orders",
    "include.schema.changes": "true",
    "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
    "schema.history.internal.kafka.topic": "schemahistory.shop-cdc"
  }
}
~~~

The two groups of properties have distinct roles:

| Property | Role |
|---|---|
| `include.schema.changes` | On supporting connectors, controls emitting **schema change notifications to Kafka** |
| `schema.history.internal.kafka.bootstrap.servers`, `schema.history.internal.kafka.topic` | Specifies where the connector stores its **internal schema history** |

In the MySQL connector, setting `include.schema.changes=false` typically disables only the **schema change notification topic**; Debezium must still track schemas to decode row events accurately and still requires internal schema history storage. **Never delete the internal schema history topic to silence DDL notifications.** That is connector recovery state; losing it can break restarts or force a recovery procedure.

The example property names match Debezium MySQL versions using the `schema.history.internal.*` prefix. Verify documentation for your exact version; older Debezium releases used different property names.

### 3.2. Illustrative DDL and Event

A DBA executes:

~~~sql
ALTER TABLE sales.orders
    ADD COLUMN coupon_code VARCHAR(32) NULL;
~~~

A schema change event **abbreviated to explain structure** might look like this (actual `table` fields and metadata are richer depending on connector/converter/version):

~~~json
{
  "source": {
    "connector": "mysql",
    "name": "shop-cdc",
    "db": "sales"
  },
  "ts_ms": 1763892000000,
  "databaseName": "sales",
  "schemaName": null,
  "ddl": "ALTER TABLE sales.orders ADD COLUMN coupon_code VARCHAR(32) NULL",
  "tableChanges": [
    {
      "type": "ALTER",
      "id": "sales.orders",
      "table": {
        "columns": [
          { "name": "id", "typeName": "BIGINT" },
          { "name": "status", "typeName": "VARCHAR" },
          { "name": "coupon_code", "typeName": "VARCHAR" }
        ]
      }
    }
  ]
}
~~~

This is **illustrative JSON with omitted fields**, not a verbatim fixture compatible with every converter. In real notifications:

- `source` provides metadata identifying the database, connector, and log position per source.
- `databaseName` and `schemaName` indicate catalog/schema scope when supplied by the connector.
- `ddl` provides the source DDL statement when available; never rely solely on regex SQL parsing to handle all DDL variants.
- `tableChanges` describes structured table changes, including `type` such as `CREATE`, `ALTER`, `DROP`, table identifiers, and column/key metadata.
- `ts_ms` is normally the timestamp recorded by the connector for the event; do not use timestamps to replace source log positions or as unique keys.

If the Kafka Connect JSON Converter enables `schemas.enable=true`, the record will have outer `schema` and `payload` wrappers. With Avro/Protobuf or SMTs, the format delivered to handlers can look completely different from the JSON above. **Inspect actual messages from your system before writing deserializers.**

## 4. How Does DDL Lead to Structural Changes in Row Events?

Suppose `sales.orders` initially is:

~~~sql
CREATE TABLE sales.orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    total DECIMAL(12, 2) NOT NULL
);
~~~

An order creation (row CDC) event before the DDL might contain:

~~~json
{
  "before": null,
  "after": { "id": 501, "status": "NEW", "total": "150.00" },
  "op": "c"
}
~~~

After `ALTER TABLE ... ADD COLUMN coupon_code ...`, a newly inserted record might contain:

~~~json
{
  "before": null,
  "after": {
    "id": 502,
    "status": "NEW",
    "total": "240.00",
    "coupon_code": "SAVE10"
  },
  "op": "c"
}
~~~

These two JSON snippets only illustrate the difference in **field sets**. Decimal values may be represented by converters as strings, binary, numbers, or logical types depending on configuration. Receiving a separate schema change event **does not replace** handling the updated schema on the row topic.

### 4.1. Timeline

~~~mermaid
sequenceDiagram
    participant DB as MySQL
    participant DZ as Debezium
    participant SC as Schema topic
    participant ROW as Row topic
    participant SI as Spring Integration
    DB->>DZ: DDL adding coupon_code column
    DZ->>DZ: Update structure + schema history
    DZ->>SC: Schema change event ALTER
    DB->>DZ: INSERT row with coupon_code
    DZ->>ROW: Row event op=c with new schema
    SC-->>SI: Metadata stream receives event
    ROW-->>SI: Data stream receives event
    Note over SC,ROW: Separate topics/partitions: no global observation order
~~~

Even though the DDL occurred **before** the INSERT in the source transaction log, the two Kafka topics can have independent partitions and consumers. **Never assume** Spring Integration will finish processing the schema change event before receiving row events with the new schema. Applications should support multiple schema versions or use verified coordination rather than hoping cross-topic arrival order suffices.

### 4.2. When One DDL Includes Multiple Changes

A single `ALTER TABLE` can add, drop, rename, or alter types on multiple columns; a `RENAME TABLE` can affect multiple tables. Sink parsers should therefore never assume `tableChanges` always has exactly one element. Furthermore, some connectors provide only partial metadata and may not reproduce the exact original SQL uniformly.

## 5. Schema Change Event Support Depends on the Connector

Do not mechanically apply MySQL's model to every database source:

| Source | Behavior to Understand |
|---|---|
| **Debezium MySQL** | Parses DDL from the binlog, maintains schema history, and can emit schema change events to Kafka when configured |
| **Debezium PostgreSQL** | Logical decoding/`pgoutput` streams data changes; **do not expect a MySQL-style DDL notification topic**. Schema changes appear in subsequent row event schemas; capturing DDL requires additional solutions |
| **Debezium SQL Server / Oracle** | Schema extraction and DDL capabilities differ from MySQL; verify documentation and configuration for your connector/version |
| **Debezium Engine / Debezium Server** | Message delivery, offset storage, and notification output depend on version, connector, and sink; a separate Kafka schema topic is not automatic |

**Verify before designing:** whether your running connector emits DDL notifications, which topic/channel carries them, what payload format is used, whether database/table filtering applies, and how schema history is stored. If PostgreSQL requires full DDL auditing, you may need database event triggers or external schema auditing per database capabilities and policies.

## 6. Classifying Schema Evolution and Consumer Impact

Not all DDL changes carry the same risk. Compatibility also depends on message encoding, Java mappings, schema registry, API contracts, and business logic.

| Example DDL | Typical Consequence for CDC Consumers | Mitigation |
|---|---|---|
| `ADD COLUMN coupon_code VARCHAR(32) NULL` | New messages include optional field; old messages lack it | Allow missing/null fields; deploy compatible consumer before using new field |
| `ADD COLUMN priority INT NOT NULL DEFAULT 0` | New field appears; default semantics need verification | Verify converter/default values and sync target model |
| `DROP COLUMN legacy_code` | Consumers reading old field may fail or see null/missing | Remove dependencies before dropping; explicit contract versioning |
| `RENAME COLUMN status TO order_status` | Contract renames field rather than updating values | Run transition period supporting both old and new names if needed |
| `MODIFY total DECIMAL(12,2) -> DECIMAL(18,4)` | Precision/scale or serialization type changes | Test mapping, target DB, validators, and monetary calculations |
| `ALTER PRIMARY KEY` | Kafka/message key may change; sink mapping/dedup impacted | Plan key migration; verify upserts, deletes, and partitioning |
| `DROP TABLE` / `RENAME TABLE` | Topics, filters, routing, projections may no longer match | Update routing, target data lifecycle, and connector config |

### 6.1. Expand–Migrate–Contract

For continuously running systems, a safer workflow is:

1. **Expand:** add new columns compatibly; deploy converters/DTOs capable of understanding both old and new events.
2. **Migrate:** update writers/readers, validate topics, and update projections or backfill as needed.
3. **Contract:** drop old columns/fields only after all affected consumers have upgraded and in-flight backlog has drained.

For instance, to rename `status` to `order_status`, add `order_status` first, move producers and consumers through a dual-field phase, and remove `status` last. The compatibility window must account for Kafka retention, retry topics, pending batches, and replay windows.

### 6.2. Distinguishing Schema Compatibility from Data Compatibility

A change accepted by Schema Registry under `BACKWARD` or `FULL` compatibility (if used) **is not necessarily** business-safe. For example, changing the meaning of `total` from VND to thousands of VND can preserve the decimal type while breaking downstream calculations. Conversely, a handler using a flexible map might parse new JSON cleanly while silently ignoring a business-critical field.

Evaluate all four dimensions:

- **Wire compatibility:** can the consumer deserialize the message?
- **Structural compatibility:** do fields, types, nullability, and keys remain valid?
- **Semantic compatibility:** did units, meanings, or calculation rules change?
- **Operational compatibility:** do reprocessing, retries, snapshots, routing, and historical events remain safe?

## 7. Designing Two Spring Integration Branches: Metadata and Data

When using Kafka as an intermediary, a manageable design separates inbound adapters for the **schema topic** and **row topics**, feeding two `MessageChannel`s with distinct contracts:

~~~text
MySQL -- Debezium --> Kafka: shop-cdc
                         |
                         +--> schemaChangeInboundAdapter
                         |      -> schemaChangeChannel
                         |      -> validate metadata
                         |      -> audit / alert / compatibility check
                         |
                         +--> row CDC topics: shop-cdc.sales.orders
                                -> rowChangeInboundAdapter
                                -> rowChangesChannel
                                -> transformer
                                -> service activator / projection writer
~~~

In **SPRING_INTEGRATION_ADAPTERS**, inbound adapters receive messages and send them onto a `MessageChannel`; transformers normalize message contracts, filters drop out-of-scope events, routers direct traffic, service activators run business logic, and error channels/DLQs handle failures as designed.

| Branch | Input | Appropriate Work | What Not to Do |
|---|---|---|---|
| `schemaChangeChannel` | DDL notifications | Write audits, alert on breaking changes, open tickets, check compatibility, trigger approved migration workflows | Automatically execute every received SQL DDL on the target database |
| `rowChangesChannel` | `before/after` + `op` | Upserts, deletes, cache/search/projection updates, emitting filtered business events | Assume every event has fixed fields or trigger side effects straight from snapshots/replays |

**Never automatically run `ddl` strings extracted from events against the target database.** Source DDL may be incompatible with target dialect, permissions, topology, or migration policies; schema synchronization requires explicit migration planning, ordering, and rollback capability.

### 7.1. Example Handler Observing Schema Change Events

Assume the adapter receives from the schema topic, the deserializer produces a JSON `String` payload, and the converter may emit either the raw object or a `payload` wrapper. Illustrative Java handling **metadata** (instead of executing DDL):

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class SchemaChangeObserver {
    private final ObjectMapper mapper = new ObjectMapper();

    @ServiceActivator(inputChannel = "schemaChangeChannel")
    public void observe(Message<String> message) throws Exception {
        JsonNode root = mapper.readTree(message.getPayload());
        JsonNode body = root.hasNonNull("payload")
                ? root.get("payload")
                : root;

        String database = body.path("databaseName").asText("");
        String ddl = body.path("ddl").asText("");
        JsonNode changes = body.path("tableChanges");

        if (!changes.isArray()) {
            throw new IllegalArgumentException("Missing tableChanges");
        }

        for (JsonNode change : changes) {
            String type = change.path("type").asText("");
            String tableId = change.path("id").asText("");
            // Replace with audit service, metrics, or compatibility check.
            // Do not execute ddl directly on the target database.
            System.out.printf("DDL event: db=%s table=%s type=%s%n",
                    database, tableId, type);
        }
    }
}
~~~

This is an **abbreviated example for learning how to read events**, omitting Kafka inbound adapter configuration, error handling, audit log security, and real converters. In production, you may need to:

- Handle nulls and `byte[]`, `GenericRecord`, JSON tree, or POJO payloads depending on the deserializer.
- Validate events that lack `tableChanges` or have connector/version-specific shapes rather than always throwing.
- Attach correlation metadata (source partition/offset, Kafka topic/partition/offset, connector, table) to audits for investigation and deduplication.
- Define retries/DLQs and ack rules so audit entries are not lost when a handler fails.
- Avoid logging full SQL DDL statements if they contain sensitive literals or expose internal system structure.

### 7.2. Why Prepare for New Events Before Deploying DDL?

Example Java consumer decoding Kafka messages into a DTO:

~~~java
// Illustrative DTO used before the schema changed.
public record OrderChange(Long id, String status, java.math.BigDecimal total) {}
~~~

If new data adds `coupon_code`, that same DTO may keep working or fail depending on object mapper settings and schema handling. You cannot tell from the `record` definition alone. The safe approach is testing with **both pre-DDL and post-DDL events**, including historical events replayed from Kafka.

During schema changes—especially dropping or renaming columns—schema versioning or compatible mapping is far more reliable than treating a DDL notification as a signal that "from now on every message uses the new schema"; partitions and consumers may still hold unprocessed older messages.

## 8. Offsets, Schema History, Ordering, and Recoverability

Schema changes complicate CDC recovery because the connector needs not only the log position, but also **which schema applies to each segment of the log being read**.

### 8.1. Internal Schema History Enables Log Replay

Example:

1. At log position `P10`, `orders` has 3 columns.
2. At `P20`, a DDL adds column `coupon_code`.
3. At `P30`, an INSERT writes data using the 4-column schema.
4. Debezium crashes after `P30`, while the durable offset is still at `P15`.

When restarting from `P15`, the connector must accurately decode records both before and after `P20`. In connectors with internal schema history like MySQL, that history enables reconstructing the proper schema during log replay. **Never edit or replace the internal schema history topic with DDL events meant for monitoring.**

Flushing source offsets and schema history have their own lifecycles; database/log retention settings and schema history durability both govern whether resumption succeeds.

### 8.2. Replaying Schema Change Events

A DDL event sent successfully before source offsets were flushed can be replayed after a restart depending on the connector's mechanism and guarantees. Audit pipelines should therefore record events idempotently whenever possible, using a key built from **source identity, log position, and relevant event metadata**. A timestamp or raw SQL text alone is not a reliable unique key across all DBMSs.

### 8.3. Do Not Infer Synchronization from Receiving a Notification

A schema-topic consumer receiving `ALTER TABLE` does not prove row-topic consumers have finished reading all old-schema records or started seeing the new schema. Likewise, the Kafka consumer group offset on the schema topic does not reflect projection update progress. Track separately:

- Source offset and Debezium connector status.
- Durability and availability of schema history.
- Kafka lag and deserialization errors per consumer group/topic.
- Schema versions actually supported by transformers, handlers, and target databases.
- Status of related database migrations.

## 9. Real-World Errors and How to Handle Them

| Symptom | Possible Cause | Verification Step |
|---|---|---|
| `ALTER TABLE` ran, but schema topic has no event | Connector doesn't emit notifications, feature disabled, DB/table filter, wrong topic, or DDL not captured | Verify connector type, `include.schema.changes`, logs, and actual topics |
| Row topic has new field, but schema topic has no notification | Connector reflects schema only via row events, or notification topic disabled/skipped | Inspect row message converter/schema and connector capabilities |
| Consumer fails decoding after DDL | DTO/Schema Registry/mapping rejects new field or type | Compare pre/post-DDL messages, converter settings, compatibility rules |
| Target data is missing the new column | Transformer/projection mapping not updated | Check mappings, target table, and backfill plan |
| Debezium fails to start after losing internal history | Connector cannot reconstruct old schema to read needed offset/log | Check error logs, supported snapshot/recovery options, backups, and schema history |
| Schema event audited twice | Retry, unflushed source offset, or uncommitted consumer offset | Add idempotency and store Kafka/source metadata |
| Data events arrive before migration completes | No global ordering across topics; staggered deployment | Deploy compatible consumers first; enforce migration controls and rollback plans |
| Primary key change duplicates target records | Deduplication/partitioning/routing tied to old key | Check key encoding, upserts/deletes, and key transition handling |

**Operational rule:** never proactively delete offsets or internal schema history to "sync quickly" after a schema error. Losing history can prevent the connector from decoding older logs or force a resnapshot. Always verify recovery options before intervening.

## 10. End-to-End Scenario: Adding a Column to an Orders System

Suppose MySQL `sales.orders` streams CDC via Debezium. Spring Integration reads `shop-cdc.sales.orders` and updates `reporting.orders`. The product team asks to add a promo code column `coupon_code`.

**Preparation**

1. Confirm the MySQL connector emits schema change events and has durable internal schema history.
2. Check the converter and row event schema; use sample events to verify handlers accept the new field.
3. Expand `reporting.orders` and update the projection handler knowing the new field may be null/absent in older events.
4. Deploy the compatible consumer and test replaying older events **before** executing the DDL.

**Source Schema Change**

~~~sql
ALTER TABLE sales.orders
    ADD COLUMN coupon_code VARCHAR(32) NULL;
~~~

**Verification**

- Observe the schema change notification if supported and enabled; verify `tableChanges` reflects the expected table and column.
- Create a new order with `coupon_code`, check the row event carries the field, and confirm the handler writes it to the projection.
- Confirm older events lacking `coupon_code` still deserialize cleanly on replay.
- Monitor converter errors, DLQ, consumer lag, and target row counts.
- Mark migration complete after reconciliation; never treat receiving a single DDL notification as proof the entire rollout is finished.

**If rollback is required:** roll back the application version compatibly first; running `DROP COLUMN` for a "quick undo" risks losing data and triggers yet another schema change. Handle database rollbacks according to your migration plan.

## 11. Practice Exercises

### Exercise 1 — Event Classification

You receive two messages:

**Message A**

~~~json
{
  "ddl": "ALTER TABLE sales.orders ADD COLUMN coupon_code VARCHAR(32)",
  "tableChanges": [{ "type": "ALTER", "id": "sales.orders" }]
}
~~~

**Message B**

~~~json
{
  "before": { "id": 42, "status": "NEW" },
  "after": { "id": 42, "status": "PAID" },
  "op": "u"
}
~~~

Determine which message belongs to the metadata branch and which belongs to the projection update branch; why shouldn't A be sent to the same service activator handling `op`?

### Exercise 2 — Breaking Change

The database team wants to run:

~~~sql
ALTER TABLE sales.orders DROP COLUMN status;
~~~

Why can this break consumers even if the schema change event is emitted successfully? Propose the proper sequence for code deployment, migration, and verification.

### Exercise 3 — Missing Schema Topic in PostgreSQL

A team uses Debezium PostgreSQL with `pgoutput` and sees new fields in row events after a DDL, but sees no MySQL-style DDL Kafka topic. Explain why they should not conclude the connector missed row changes, and how schema tracking should be handled.

<details>
<summary>Answer Hints</summary>

1. Message A is a **schema change notification** and belongs in an audit/compatibility flow; B is a **row update event** handled in the projection flow. A has no `before/after/op` row CDC semantics.
2. Consumers still reading `status` will fail or lose business data; deploy compatible consumer changes first, backfill/transform data as needed, check older messages still in Kafka, and only then drop the old column.
3. PostgreSQL logical decoding does not provide a DDL notification mechanism equivalent to MySQL in the standard model. Rely on row event schemas, migration processes, and separate database DDL auditing if needed; verify exact capabilities for your connector/version.

</details>

## 12. Schema Evolution Design and Operations Checklist

- [ ] Verify whether the connector/version supports schema change events, which topic/channel is used, and the actual payload structure.
- [ ] Clearly distinguish DDL notifications, row events, Kafka Connect schemas, and Debezium internal schema history.
- [ ] Separate Spring Integration `schemaChangeChannel` and `rowChangesChannel` with appropriate message contracts, retries, and DLQs.
- [ ] Never auto-execute `ddl` on the target database merely because a notification arrived.
- [ ] Check compatibility for fields, types, nullability, keys, semantics, and existing historical event schemas.
- [ ] Design consumers to tolerate duplicate notifications, cross-topic ordering differences, and restarts.
- [ ] Maintain source offsets, internal schema history, and transaction logs under verified durability/retention policies.
- [ ] Monitor deserialization errors, event/schema versions, consumer lag, audits, and target data reconciliation.
- [ ] Follow expand–migrate–contract for renames, column drops, or key changes.
- [ ] Include test scenarios for pre/post-DDL replay and recovery when the connector cannot read historical schemas.

**Key Takeaway:** *Schema change events* announce changes to **source data structure**; *row change events* transmit changes to **record values**. In the Spring Integration Adapters module, the metadata branch helps detect and coordinate contract changes, while the data branch keeps updating target systems via `MessageChannel`s. A reliable CDC pipeline addresses schema evolution, message contracts, log/offset recovery, and consumer compatibility together.
