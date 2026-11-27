# Key, Value, and Envelope in Debezium

## 1. Why Must You Understand a CDC Message Contract?

In the **SPRING_INTEGRATION_ADAPTERS** module, external systems connect to Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s. For database sources, a common architecture uses **Debezium** to read transaction logs and emit CDC events to Kafka, while a **Spring Integration Kafka inbound adapter** receives them and forwards them to a transformer, router, or service activator.

When a message arrives, processing code must be able to answer:

- **Which record changed?** Usually found in the Kafka message **key**.
- **What changed, and what are the before/after values?** Found in the message **value**, typically an **envelope** containing `before`, `after`, `op`, and `source`.
- **Where did the change originate, and when was it recorded?** Read metadata in `source`, timestamps, and transaction info if present.
- **When should a record be deleted or skipped?** Distinguish CDC delete events from Kafka tombstones; account for snapshot state and SMTs.
- **Can it be processed repeatedly?** Rely on idempotency, ordering, source checkpoints, and consumer acknowledgments.

If you only decode `after` and discard all metadata, the application may sync inserted rows, yet mishandle DELETEs, confuse snapshot data with new transactions, or lose critical context during replays.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **Kafka record key**, **Kafka record value**, and **Debezium event envelope**.
2. Read `before`, `after`, `source`, `op`, `ts_ms`, and `transaction` fields in context.
3. Explain the difference between the logical envelope and Kafka Connect JSON Converter's `schema/payload` wrapper.
4. Properly handle `r/c/u/d`, tombstones, key changes, tables without primary keys, and SMT unwrapping.
5. Design message contracts, key mapping, idempotency, and deserialization error handling in Spring Integration.

## 2. Structure of a Kafka Record Emitted by Debezium

A Kafka record has separate components: **topic**, **partition**, **offset**, **timestamp**, **headers**, **key**, and **value**. Debezium constructs key/value according to the source connector contract; the Kafka broker assigns the record's offset within a partition.

~~~mermaid
flowchart LR
    DB[(Database<br/>transaction log)] --> DZ[Debezium<br/>source connector]
    DZ --> K[(Kafka topic)]
    K --> AD[Spring Integration<br/>Kafka inbound adapter]
    AD --> CH[MessageChannel]
    CH --> MAP[Transformer<br/>decode contract]
    MAP --> ROUTE{op / record type}
    ROUTE --> UPSERT[Upsert projection]
    ROUTE --> DEL[Delete / tombstone policy]
    ROUTE --> ERR[Error / retry policy]
~~~

For a `sales.orders` table with primary key `id = 42`, an update record can be visualized as:

~~~text
Kafka record
  topic:     orders-cdc.sales.orders
  partition: 1
  offset:    2058                 <- Kafka offset, not binlog position
  key:       {"id":42}            <- record identifier
  value:     {                    <- Debezium change-event envelope
               "before": {...},
               "after": {...},
               "source": {...},
               "op": "u",
               "ts_ms": 1763892000000
             }
  headers:   ...                  <- Kafka headers, configuration-dependent
~~~

The example above assumes the JSON converter **omits Kafka Connect schemas from the payload**. Actual shapes depend on the connector, version, converter, Single Message Transforms (SMTs), and configuration.

### Distinguishing Record and Envelope

| Component | Example | Where Does It Live? | What Is It Used For? |
|---|---|---|---|
| Kafka record key | `{"id":42}` | Kafka record key | Partitioning, grouping changes for the same entity, upserts |
| Kafka record value | JSON object or bytes | Kafka record value | Carries CDC content; may be null on tombstones |
| Debezium envelope | `before`, `after`, `source`, `op`… | Typically the logical content of value | Expresses change type and metadata |
| Kafka record offset | `2058` | Topic partition metadata | Tracking/committing Kafka consumption progress |
| Debezium source position | `file/pos`, `lsn`… | Typically in `value.source` and source offset | Tracking database transaction log position |
| Kafka headers | Headers per adapter/SMT | Metadata outside value | Carrying transport or pipeline-enriched info |

**Never equate** the Kafka message key with an `id` column when a table has a composite key; likewise, never equate a Kafka offset with a Debezium log position.

## 3. Key: Which Record Is Changing?

### 3.1. Default Keys Usually Come from the Primary Key

For tables with a primary key on supporting connectors, Debezium typically uses the primary key value(s) to construct the change event key.

Example:

~~~sql
CREATE TABLE sales.orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL
);
~~~

An event for order `id = 42` has the logical key:

~~~json
{"id": 42}
~~~

If `order_items` has a composite primary key (`order_id`, `line_no`), the key may be:

~~~json
{"order_id": 42, "line_no": 2}
~~~

**The key is not a copy of the entire row.** `status`, `customer_id`, or `quantity` do not automatically appear in the key unless configured. On supporting connectors, you can customize key columns with options such as `message.key.columns`; requirements, syntax, and side effects vary by connector.

### 3.2. Why Is the Kafka Key Important?

The Kafka producer typically uses the key to choose the target partition. When multiple changes for the **same stable key** land in the same partition and the producer preserves log order, Kafka preserves record ordering within that partition. This lets projections apply updates to the same record in order.

However:

- **There is no global ordering** across Kafka partitions.
- Changing partition counts, partitioner strategies, key serialization, or topic routing can alter record distribution; evaluate this whenever preserving order across migrations.
- A single source transaction can modify multiple tables/keys and produce multiple records across different topics/partitions.
- A multi-threaded/async Spring Integration consumer can reorder *application* of updates if concurrency is uncontrolled, even when Kafka delivered them in order.

Keys also matter for **compacted topics**. Kafka log compaction retains the latest record per key, not per field inside `after`. Using an unstable or null key that breaks entity semantics undermines state reconstruction.

### 3.3. What If a Table Has No Primary Key?

For tables lacking a primary key, the default key may be **null** or constructed from custom key settings depending on the connector. Common consequences:

1. Changes to a given row are difficult to identify consistently.
2. Compacted topics cannot reliably reconstruct per-row state from null keys.
3. Sink upserts/deletes cannot accurately target a row, especially if duplicate rows exist.
4. There is no guarantee that changes for the same entity land on the same partition.

If state synchronization is needed, prefer tables with a stable primary or business key, or design an explicit identity strategy verified against your connector.

### 3.4. When the Primary Key Changes

Changing a primary key is not a routine in-place update for a key-ordered stream. In Debezium connectors supporting this model, a key update can be represented as a **DELETE for the old key** followed by a **CREATE for the new key**; tombstones and headers carrying old/new keys may also appear depending on connector and config.

Example changing `id=42` to `id=420`:

~~~text
Record 1: key={"id":42},  value=op:"d", after:null
Record 2: key={"id":42},  value=null       (tombstone if enabled)
Record 3: key={"id":420}, value=op:"c", after:{"id":420,...}
~~~

This is an **illustrative model**, not a guarantee that every connector emits exactly three records or preserves cross-partition observation order. If a sink only UPSERTs the new key without deleting the old key, "ghost" records will remain.

## 4. Value and Envelope: How Did the Record Change?

In standard Debezium events, the **value** carries an envelope with these core fields:

| Field | Content | How It Is Used |
|---|---|---|
| `before` | Old row state, or null/partial depending on source and config | Comparison, auditing, delete/update handling |
| `after` | New row state; null on delete events | Projection upserts / initialization |
| `source` | Metadata such as connector, logical name, database/table, snapshot, log position, source timestamp | Tracing, source identification, diagnostics |
| `op` | Operation type: typically `r`, `c`, `u`, `d` | Routing processing by action |
| `ts_ms` / `ts_us` / `ts_ns` | Timestamp when connector processed/emitted the event (resolution depends on version) | Latency analysis, observability |
| `transaction` | Transaction metadata if configured/supported | Observing grouping and ordering within a transaction |

Some connectors/versions add extra fields or emit only a subset of the above. When present, `source.ts_ms` usually relates to when the change occurred at the source; envelope-level `ts_ms` is usually recorded by the connector. **Do not treat them as unique event IDs**, and account for clock skew.

### 4.1. Update Envelope Example

Suppose the application updates order 42 from `NEW` to `PAID`:

~~~sql
UPDATE sales.orders
SET status = 'PAID'
WHERE id = 42;
~~~

Illustrative key and value in **logical, abbreviated form**:

**Key**

~~~json
{"id": 42}
~~~

**Value**

~~~json
{
  "before": {
    "id": 42,
    "customer_id": 8001,
    "status": "NEW"
  },
  "after": {
    "id": 42,
    "customer_id": 8001,
    "status": "PAID"
  },
  "source": {
    "version": "example",
    "connector": "mysql",
    "name": "orders-cdc",
    "db": "sales",
    "table": "orders",
    "file": "mysql-bin.000008",
    "pos": 12034,
    "row": 0,
    "snapshot": "false"
  },
  "op": "u",
  "ts_ms": 1763892000000,
  "transaction": null
}
~~~

The numbers, timestamps, filename, and metadata above are strictly illustrative. `version` is a placeholder reminding you that `source` metadata varies by version; never use `"example"` as a real config value. On PostgreSQL, `source` normally includes `lsn` instead of binlog `file/pos`.

### 4.2. Meaning of `op`

| `op` | Name | Typical `before` / `after` Shape | Common Handling |
|---|---|---|---|
| `r` | Read | `before=null`, `after` holds current row | Upsert read state from snapshot |
| `c` | Create | `before=null`, `after` holds new row | Insert or idempotent upsert |
| `u` | Update | May have `before`; `after` is the new row | Upsert / version comparison per business rules |
| `d` | Delete | `after=null`; `before` depends on source capabilities | Delete or soft-delete by key |

Within specific scopes, some connectors emit additional operations such as **TRUNCATE** (e.g., `op="t"`) or special messages. Heartbeats, transaction metadata, and schema notifications can also arrive on topics/records with separate contracts. **Handlers supporting only `r/c/u/d` need an explicit policy** for unrecognized events instead of treating everything as an INSERT by default.

### 4.3. `before` Is Not Always Complete

Never assume `before` on an UPDATE always contains every column. Depending on the database, connector, log/replica identity settings, and operation:

- `before` may contain the full old row, only key columns, or null;
- `after` generally reflects the new data reconstructible by the connector, though uncaptured or specially encoded columns still require attention;
- On PostgreSQL, **REPLICA IDENTITY** determines how much old-row data is emitted in logical replication;
- On some sources, large columns, sensitive types, or column filters can result in placeholders or partial values.

If business logic needs **pre-change values**, verify the source configuration and actual event payloads. Never subtract `before` from `after` without confirming both faithfully represent the required state.

## 5. Lifecycle: INSERT, UPDATE, DELETE, and Snapshot

Suppose a table only has `id` and `status`. The same key `{"id":42}` may go through:

~~~mermaid
sequenceDiagram
    participant DB as Database
    participant D as Debezium
    participant K as Kafka
    participant SI as Spring Integration
    DB->>D: INSERT id=42, NEW
    D->>K: key=42, op=c, after=NEW
    K->>SI: UPSERT (NEW)
    DB->>D: UPDATE id=42, PAID
    D->>K: key=42, op=u, before=NEW, after=PAID
    K->>SI: UPSERT (PAID)
    DB->>D: DELETE id=42
    D->>K: key=42, op=d, after=null
    K->>SI: DELETE (42)
    opt Tombstone enabled
        D->>K: key=42, value=null
        K->>SI: Apply tombstone policy
    end
~~~

If Debezium starts with an **initial snapshot**, a pre-existing row is typically emitted as `op="r"`. Therefore:

- `op="r"` does not mean a user just created a new order;
- updating a reporting projection from `r` is usually appropriate, whereas sending a "new order created" email on `r` can be disastrous;
- as snapshot transitions to streaming, final correctness depends on proper message application, ordering, and synchronization.

## 6. Delete Event Differs from a Kafka Tombstone

This is the most critical distinction when handling null values.

A **Delete event** is a CDC change event whose **value is still an envelope** with `op="d"` and `after=null`. It means "the row was deleted from the source table".

A **Tombstone** is a **separate Kafka record with the same key and a Kafka-level null value**. On a compacted topic, a tombstone signals that the latest value for that key has been removed, allowing compaction to purge prior records according to Kafka's retention policies.

~~~text
DELETE record:
  key:   {"id":42}
  value: {"before":{"id":42,...},"after":null,"op":"d",...}

TOMBSTONE record (if emitted by connector/config):
  key:   {"id":42}
  value: null
~~~

A tombstone is not the JSON string `"null"`, not the object `{"after":null}`, and does not carry `op="d"` to inspect.

### 6.1. Avoiding Double-Delete Processing

If a handler receives `d` and deletes the projection row, the subsequent tombstone can be:

- safely skipped in a controlled way because the projection is already gone;
- used as a cache-eviction signal;
- routed to a dedicated policy branch for compacted topics.

Only trigger extra side effects when business intent is explicit. Repeated deletes must be idempotent, especially under message replay.

### 6.2. Note When Using the Spring Integration Kafka Inbound Adapter

A null Kafka value may be represented by the deserializer/adapter using a **sentinel object** such as `KafkaNull` or another mechanism depending on version and configuration, because Spring `Message` generally disallows plain Java null payloads. Therefore, do not write only `if (payload == null)` assuming it catches all tombstones. Check your Kafka adapter and converter contract for how tombstones are surfaced in Spring Integration.

Some SMTs can **drop tombstones**, **rewrite deletes into flagged records**, or reshape envelopes. If downstream never sees `d` events as expected, check whether any SMTs are active in the pipeline.

## 7. Envelope vs. JSON Converter's `schema/payload` Wrapper

A common misconception is that every Debezium Kafka JSON value has a top-level `before` field. That is only true when the converter/pipeline produces flat JSON.

With Kafka Connect **JsonConverter** and `schemas.enable=false`, the logical data appears directly:

~~~json
{
  "before": null,
  "after": {"id": 42, "status": "NEW"},
  "source": {"connector": "mysql", "db": "sales", "table": "orders"},
  "op": "c",
  "ts_ms": 1763892000000
}
~~~

With `schemas.enable=true`, `JsonConverter` adds an outer wrapper:

~~~json
{
  "schema": {
    "type": "struct",
    "name": "orders-cdc.sales.orders.Envelope",
    "fields": [
      {"type": "struct", "field": "before", "optional": true},
      {"type": "struct", "field": "after", "optional": true},
      {"type": "struct", "field": "source", "optional": false},
      {"type": "string", "field": "op", "optional": false}
    ]
  },
  "payload": {
    "before": null,
    "after": {"id": 42, "status": "NEW"},
    "source": {"connector": "mysql", "db": "sales", "table": "orders"},
    "op": "c",
    "ts_ms": 1763892000000
  }
}
~~~

This is an **abbreviated example, not a complete valid Connect schema to copy verbatim**: in practice, the schemas of `before`, `after`, and `source` declare nested fields and exact types. The key can also carry its own `schema/payload` pair if `key.converter.schemas.enable=true`.

| Wire Format | What the Consumer Must Understand |
|---|---|
| JSON converter, schemas disabled | Read the envelope directly from the decoded JSON value |
| JSON converter, schemas enabled | Read the envelope inside `payload`, optionally validating against `schema` |
| Avro / Protobuf / JSON Schema + registry | Use matching converter/deserializer; do not expect raw JSON text bytes |
| Debezium unwrap SMT | Value may contain only row state + appended metadata; `before/after/op` may no longer exist at original paths |
| Tombstone | Null Kafka value; no JSON envelope |

A **Kafka Connect schema** describes serialization structure. It is **different** from a DDL schema change event and **different** from the internal schema history used by some connectors to decode transaction logs.

## 8. Single Message Transform: When the Envelope Is Unwrapped

Debezium provides the **ExtractNewRecordState** SMT (often called *unwrap*), used when downstream systems want only the "row state" rather than the full envelope.

**Before unwrap:**

~~~json
{
  "before": {"id": 42, "status": "NEW"},
  "after": {"id": 42, "status": "PAID"},
  "op": "u",
  "source": {"db": "sales", "table": "orders"}
}
~~~

**After unwrap (illustrative when keeping new row state):**

~~~json
{"id": 42, "status": "PAID"}
~~~

The benefit is simpler sink logic for upsert-only consumers. The trade-off is that **before/op/source disappear from the value by default** unless configured to preserve or inject metadata. Consequences:

- You cannot infer a DELETE merely from the absence of `after` if the SMT drops delete events;
- pre-update values are unavailable for comparison unless stored elsewhere;
- snapshot, delete, and tombstone handling must match the SMT configuration;
- auditing systems may still need the original envelope on a separate branch;
- you can optionally append metadata such as operation or source fields via SMT options (version-dependent).

Kafka Connect config snippet merely showing **where the SMT is applied**, not a full configuration:

~~~properties
transforms=unwrap
transforms.unwrap.type=io.debezium.transforms.ExtractNewRecordState
~~~

Delete/tombstone options and added metadata fields have changed across Debezium versions; check the documentation for your deployed version, especially when configuring tombstone retention or delete rewriting.

**Design rule:** explicitly decide whether the Spring Integration consumer receives a **raw envelope**, a **wrapped `payload` envelope**, or an **unwrapped row**. Never write a single transformer guessing among all three without an explicit identification contract.

## 9. Source Metadata and Transactions: Tracing Where a Change Came From

The `source` field typically describes:

| Info Group | Example Fields | How It Is Used |
|---|---|---|
| Source identity | `connector`, `name` | Identify connector type and logical source |
| Data scope | `db`, `schema`, `table`, `collection` | Routing, auditing, validation |
| Log position | MySQL `file`/`pos`/`row`/`gtid`, PostgreSQL `lsn` | Incident investigation, connector-level resumption |
| Snapshot | `snapshot` | Distinguish snapshot reads from streaming events |
| Timing | `source.ts_ms` when present, envelope `ts_ms` | Track relative lag and clock skew |
| Transaction | `transaction.id`, `total_order`, `data_collection_order` when present | Correlate and order events within a transaction |

Some connectors emit dedicated transaction metadata when enabled (e.g., `provide.transaction.metadata` on supporting connectors). Metadata availability, field types, and cross-table transaction correlation must be verified for your exact version.

### Source Offset Differs from Position Metadata Inside an Event

Debezium manages a **source offset** representing the safe checkpoint persisted in the offset store; it can combine multiple fields including snapshot state or intra-transaction positions. `value.source.pos` or `value.source.lsn` is useful per-event metadata, **not the complete checkpoint state that you can manually overwrite**.

When an event is published to Kafka before the source offset flushes, Debezium can replay it on restart. Conversely, Spring Integration maintains its own **consumer group offset** and can re-read a Kafka record if uncommitted.

Therefore, when designing downstream deduplication, do not assume every event has a globally unique key in `ts_ms` or `lsn`. You may need source identity, table, record key, intra-transaction ordering metadata, and connector delivery semantics; many applications simply need an idempotent upsert guarded by a valid record version.

## 10. Mapping a Debezium Record to a Spring Integration Message

When using the **Spring Integration Kafka inbound adapter**, a Kafka record becomes a Spring `Message<?>`. The adapter, deserializer, and message converter determine the payload and header types.

| Kafka / Debezium | Possible Spring Integration Representation | Role |
|---|---|---|
| Kafka record value | `Message.payload`: bytes, String, JSON tree, POJO, Avro… | Data processed by transformers |
| Kafka record key | Received-key header or converter-mapped field | Business identity, partition key |
| Topic / partition / offset | Kafka metadata headers per adapter/version | Debugging, observability, retry/ack |
| Debezium `op`, `before`, `after` | Fields in payload when envelope is intact | Identify insert/update/delete |
| Debezium `source` | Fields in payload when envelope is intact | Tracing and routing |
| Null Kafka record value | Null sentinel / adapter tombstone representation | Deletion/compaction policy |

**Note:** Kafka headers, Spring Message headers, the record key, and Debezium `value.source` are distinct layers. Some converters or SMTs promote metadata from value into headers; in those cases, mapping must follow that exact configuration.

### 10.1. Recommended Processing Flow

~~~text
Kafka Debezium topic
    -> messageDrivenChannelAdapter
    -> cdcRawChannel
    -> deserialize + normalize envelope/unwrap/tombstone
    -> validate key, op, before, after, source
    -> route:
         r/c/u    -> upsert service activator
         d        -> delete service activator
         tombstone-> compacted-topic handling
         unknown  -> error channel / quarantine
    -> update projection inside transaction
    -> acknowledge/commit Kafka offset per safe policy
~~~

This is a **logical flow**, not a complete Java DSL configuration. Each adapter mode has distinct ack, retry, transaction, and error policies; passing a message through an async `MessageChannel` does not mean the target database transaction has committed.

### 10.2. State-Oriented Handler Pseudocode

~~~text
onKafkaMessage(record):
    identity = decodeKey(record.key)

    if isTombstone(record.value):
        handleTombstone(identity)
        acknowledgeWhenSafe()
        return

    envelope = decodeEnvelopeOrRecognizedUnwrappedContract(record.value)
    validateKnownSource(envelope.source, record.topic)

    switch envelope.op:
      case "r":
      case "c":
      case "u":
        assert envelope.after != null
        transaction:
            upsertProjection(identity, envelope.after)
            recordIdempotencyStateIfNeeded(...)
        break

      case "d":
        transaction:
            deleteProjectionIdempotently(identity)
            recordIdempotencyStateIfNeeded(...)
        break

      default:
        routeToErrorChannelWithContext(...)
        return

    acknowledgeWhenSafe()
~~~

If the pipeline unwraps envelopes and drops `op`, handlers cannot `switch envelope.op`; you need a separate contract with retained metadata or row-state + delete rules. When strict per-version ordering is required, `upsertProjection` must also reject stale updates replayed after newer ones using a reliable source version comparison.

### 10.3. Java Example: Extracting the Envelope from JSON Converter Output

Assume the payload **has already been deserialized to a JSON `String`**, not raw Avro/Protobuf bytes. The snippet below illustrates envelope inspection; it is not a full tombstone handler or connector configuration:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class DebeziumEnvelopeRouter {
    private final ObjectMapper mapper = new ObjectMapper();

    @ServiceActivator(inputChannel = "cdcRawChannel")
    public void handle(Message<String> message) throws Exception {
        JsonNode outer = mapper.readTree(message.getPayload());
        JsonNode envelope = outer.hasNonNull("payload")
                ? outer.get("payload") : outer;
        String operation = envelope.path("op").asText("");
        JsonNode after = envelope.path("after");

        switch (operation) {
            case "r", "c", "u" -> {
                if (after.isMissingNode() || after.isNull()) {
                    throw new IllegalArgumentException("Missing after for " + operation);
                }
                // Pass to an idempotent upsert service using the key from Kafka metadata.
            }
            case "d" -> {
                // Delete using the Kafka key, not after (since after = null).
            }
            default -> throw new IllegalArgumentException(
                    "Unsupported Debezium operation: " + operation);
        }
    }
}
~~~

This snippet uses **Java 17+**. Production use still requires inbound adapter configuration, `KafkaNull`/tombstone handling before JSON parsing, key and converter normalization, transaction/ack/retry wiring, observability, and an error channel. It also rejects unwrapped payloads because that contract lacks `op`. Route unrecognized formats to explicit errors and a DLQ.

## 11. Idempotency, Checkpoints, and Key/Value Mapping Pitfalls

| Situation | Risk | Handling Principle |
|---|---|---|
| Debezium replays after restart | Same change emitted to Kafka multiple times | Idempotent upsert/delete; deduplicate side effects |
| Kafka consumer retries record | Same record processed again | Commit only after target persistence succeeds |
| `op="r"` from snapshot | Treating an old order as newly placed | Use `r` to populate state; never fire "new order" business actions |
| Incomplete `before` | Wrong delta calculation | Rely on `after` or a verified source contract |
| Null or changing key | Updating wrong projection row, broken compaction | Use a stable key; handle key migrations explicitly |
| Kafka tombstone | JSON parse failure or double delete | Detect null/sentinel before parsing; handle idempotently |
| Unwrap SMT strips `op` | Cannot distinguish delete/update/snapshot | Preserve needed metadata or disallow incompatible config |
| Schema evolution adds/renames fields | Rigid DTO fails deserialization | Converters and models support both old and new events |
| Multiple partitions / concurrent handlers | Newer update overwritten by older one | Enforce per-key concurrency and version/order checks |
| Consumer commits before DB transaction | Projection loses event after crash | Commit target transaction safely before ack/commit per design |

**End-to-end exactly-once is not automatic** just because Debezium reads an ordered log. To prevent duplicate side effects, applications combine transactional outboxes, idempotency keys, unique constraints, version checks, or coordinated transactions.

### A Practical Upsert Strategy

Suppose the `reporting.orders` projection needs only the **latest state** per `id`; the handler can use a SQL UPSERT (PostgreSQL syntax shown):

~~~sql
INSERT INTO reporting.orders (id, status)
VALUES (42, 'PAID')
ON CONFLICT (id)
DO UPDATE SET status = EXCLUDED.status;
~~~

This UPSERT is safe when receiving the **same state** repeatedly, but does not by itself prevent an **older** event arriving late from overwriting a newer state. With parallel consumers or replays overlapping newer data, add reliable version/ordering guards or enforce sequential per-key processing.

## 12. Practice Exercise: Reading Three Records and Deducing the Outcome

A compacted Kafka topic stores events for `sales.orders`. Assume the contract is a standard Debezium envelope (unwrapped disabled), keys come from `orders.id`, and the consumer processes per-key order accurately.

**Record A**

~~~text
key:   {"id":7}
value: {"before":null,
        "after":{"id":7,"status":"NEW"},
        "op":"r",
        "source":{"snapshot":"true"}}
~~~

**Record B**

~~~text
key:   {"id":7}
value: {"before":{"id":7,"status":"NEW"},
        "after":{"id":7,"status":"SHIPPED"},
        "op":"u",
        "source":{"snapshot":"false"}}
~~~

**Record C**

~~~text
key:   {"id":7}
value: {"before":{"id":7,"status":"SHIPPED"},
        "after":null,
        "op":"d"}
~~~

After C, the connector may also emit record **D** with the same key and Kafka value **null**.

**Questions:**

1. What does `op="r"` in A indicate? Should you send a "new order created" email?
2. After processing A and B, what is the projection state for `id=7`?
3. Why must processing C extract `id` from the key or `before`, not `after.id`?
4. How does D differ from C, and what role does D play on a compacted topic?
5. If `ExtractNewRecordState` is enabled, what missing info would prevent `switch(op)` from working?
6. If B is replayed after C has already been processed and persisted, how do you avoid resurrecting the deleted record?

<details>
<summary>Answer Hints</summary>

1. A is a snapshot read. Use it to initialize/upsert the projection; it does not mean the order was just created when the message arrived.
2. B is an update: the projection stores `id=7, status=SHIPPED`.
3. A delete envelope has `after=null`; the Kafka key is the stable identifier for the deleted record.
4. D has a null Kafka value with no envelope or `op`; it lets Kafka log compaction purge the deleted key according to broker retention settings.
5. After unwrapping, `op`/`before`/`source` may be stripped from the value; you must retain the needed metadata or update the handler contract.
6. Enforce per-key ordering with reliable version/metadata checks or durable deduplication/tombstone markers rather than an unconditional UPSERT. Both source and consumer replays must be accounted for.

</details>

## 13. Pre-Deployment Key/Value Normalization Checklist

- [ ] Identify the exact **connector, version, converter, and SMTs** for the topic in use.
- [ ] Capture sample real records: Kafka key, value, headers, topic, partition, offset, and JSON/Avro/Protobuf wire format.
- [ ] Confirm whether keys come from primary keys or configured columns; handle composite keys and keyless tables.
- [ ] Determine whether consumers receive raw envelopes, `schema/payload` wrappers, or unwrapped rows.
- [ ] Handle `r/c/u/d`, policies for other operations, snapshots, and transaction metadata if enabled.
- [ ] Handle `after=null` delete events separately from null-value Kafka tombstones.
- [ ] Never assume `before`, `source.ts_ms`, or `transaction` are always complete.
- [ ] Verify support for schema evolution, added/missing fields, and serialization type changes.
- [ ] Ensure Kafka keys/partitions and parallel processing align with per-entity ordering requirements.
- [ ] Commit Kafka consumer offsets only after target processing succeeds per your adapter's mechanics.
- [ ] Design idempotency, error channel/DLQ, retries, and replay capability from Kafka or the source.
- [ ] Test insert → update → delete → tombstone, mid-processing restarts, and primary-key updates.

**Key Takeaway:** the **key** tells you *which record* an event targets; the **value** carries *what changed*; and Debezium's **envelope** explains *how the change occurred, from which source, and under what context*. In Spring Integration, a clean translation contract between Kafka records and `MessageChannel`s is the foundation for accurate routing, proper delete handling, and safe recovery under replay.
