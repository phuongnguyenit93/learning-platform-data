# Idempotency on CDC Replay in Debezium and Spring Integration

## 1. The Problem: Does Receiving the Same Change Twice Corrupt Data?

In the **SPRING_INTEGRATION_ADAPTERS** module, systems exchange data via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s. A common architecture uses **Debezium** for *Change Data Capture* (CDC) from MySQL/PostgreSQL, publishing records to Kafka, after which a **Spring Integration Kafka inbound adapter** feeds them into a flow to update a reporting database, cache, search engine, or external service.

Suppose an order is updated to `PAID`. Debezium emits the event to Kafka, and Spring Integration reads it and writes to the target database. Immediately after writing, the application crashes **before committing the consumer offset**. Upon restart, the consumer can re-read that exact same Kafka record.

If the handler runs:

~~~text
SET orders.status = "PAID"
~~~

then applying it repeatedly usually produces the same result. However, if the handler runs:

~~~text
account.balance = account.balance + 200000
sendPaymentConfirmationEmail()
~~~

then the same event can **credit the balance twice** and **send two emails**. That is why CDC pipelines require **idempotency**: reprocessing a change produces no extra business effect beyond the intended outcome.

### Learning Outcomes

After this lesson, you will be able to:

1. Explain why CDC replays occur across Debezium, Kafka consumers, retries, and dead-letter redrives.
2. Distinguish *idempotent state updates*, *event-ID deduplication*, and *version/ordering enforcement*.
3. Choose appropriate identifiers for CDC row events, Debezium outbox events, and special records like snapshots or tombstones.
4. Implement an **inbox/processed-event table** alongside target updates in **the same database transaction**.
5. Design Spring Integration flows with properly timed acknowledgments, bounded retries, and reliable side effects.
6. Test crashes, replays, duplicates with new Kafka offsets, out-of-order arrivals, and deletes so projections stay accurate.

## 2. Defining Idempotency and Two Commonly Conflated Failures

An operation `f` is idempotent with respect to event `e` if applying `e` repeatedly to a state that has already processed `e` yields the same result as applying it once:

\[
f(f(s, e), e) = f(s, e)
\]

Status update example:

~~~sql
UPDATE reporting.orders
SET status = 'PAID'
WHERE id = 42;
~~~

Assuming no triggers or other side effects, this SQL statement yields the same **resulting state** whether run once or many times. By contrast, the following operations are typically **not idempotent**:

~~~sql
UPDATE reporting.accounts
SET balance = balance + 200000
WHERE id = 10;
~~~

~~~text
chargeCard(200000)
sendEmail("Payment received")
incrementMetric("completed_payment", 1)
~~~

Idempotency is not solely about avoiding **duplicates**; it must also address **stale events arriving late**. These are two distinct cases:

| Case | Example | Risk | Appropriate Mechanism |
|---|---|---|---|
| **Duplicate**: the same change is processed twice | `E1: PAID`, followed by `E1: PAID` again | Duplicate rows, double-counting, repeated notifications | Idempotent upsert, event IDs, and inbox/dedup |
| **Out-of-order / stale replay**: an older change arrives after a newer one | `E1: PAID`, `E2: SHIPPED`, then replay of `E1` | State regresses to `PAID` | Per-key ordering, reliable version/sequence checks, reconciliation |

**Deduplicating a single event ID does not replace business ordering.** Conversely, using an UPSERT alone for state idempotency is insufficient if an older record is applied after a newer one.

## 3. Why Can Debezium and Consumers Replay Events?

~~~mermaid
flowchart LR
    DB[(Source database)] --> LOG[Transaction log]
    LOG --> DZ[Debezium connector]
    DZ --> K[(Kafka CDC topic)]
    K --> IN[Spring Integration<br/>Kafka inbound adapter]
    IN --> CH[MessageChannel]
    CH --> H[Service activator]
    H --> DEST[(Target database)]
    DZ -. persists source offset .-> OS[(Connect offset store)]
    IN -. commits consumer offset .-> CG[(Consumer group)]
~~~

Three **independent** progress layers exist:

| Position | Purpose | When Not Durably Persisted |
|---|---|---|
| Debezium **source offset** | Lets connector resume reading the DB log from the right checkpoint | Connector may re-read and re-emit source change events |
| Kafka **topic-partition-offset** | Locates each record appended to a Kafka partition | A re-emitted source change becomes **a new Kafka record with a different offset** |
| Kafka **consumer group offset** | Tracks how far a consumer group has acknowledged | Consumer may re-read an already-processed Kafka record |

### 3.1. Debezium Source Replays

A possible sequence:

1. Kafka Connect has its source offset persisted at `P100`.
2. Debezium reads change `E101`, and Kafka writes the record at offset `500`.
3. The connector dies before the checkpoint for `E101` flushes.
4. The connector restarts from the saved state and emits `E101` again, now landing at Kafka offset `501`.

The two Kafka records have **different offsets** yet represent **the exact same source business change**. Therefore, **deduplicating solely by Kafka topic/partition/offset cannot eliminate duplicates caused by source replays**.

### 3.2. Consumer Re-Reads the Same Kafka Record

Another scenario:

1. Spring Integration receives Kafka record at offset `500`.
2. The handler successfully writes to the target database.
3. The application stops before the consumer group commits the next offset.
4. Upon restart, the consumer re-reads Kafka record offset `500`.

Here, `(topic, partition, offset)` identifies **that exact Kafka record** within the topic/partition, but cannot distinguish it from a replay of the same source event written at a different Kafka offset.

### 3.3. Retries, Dead-Lettering, and Snapshots

Beyond crashes, records can be replayed by:

- **Retries** when a transformer, JDBC write, HTTP gateway, JMS/AMQP adapter, or outbound handler hits transient errors.
- **Kafka rebalances** when a member loses partition ownership while an async target write is still in flight.
- **DLT/DLQ redrives** when quarantined records are sent back into processing after a fix.
- **Initial/incremental snapshots** emitting row state via `op="r"`, which can reappear during re-snapshots or snapshot recovery.
- **Topology changes**: multiple consumer groups or pipelines writing to the same target, or routing/partitioning changes.

Not all of these represent "the same Kafka message". Clearly define whether the **target of deduplication** is a broker record, a source change event, or a business event.

## 4. Inspecting the Debezium Envelope Before Choosing a Deduplication Key

Illustrative CDC row event:

**Kafka record key**

~~~json
{"id": 42}
~~~

**Kafka record value** (abbreviated):

~~~json
{
  "before": {"id": 42, "status": "NEW"},
  "after": {"id": 42, "status": "PAID"},
  "source": {
    "connector": "mysql",
    "name": "shop-cdc",
    "db": "sales",
    "table": "orders",
    "file": "mysql-bin.000032",
    "pos": 18420,
    "row": 0,
    "snapshot": "false"
  },
  "op": "u",
  "ts_ms": 1763892000000
}
~~~

Fields and representations vary across Debezium connectors, versions, converters, and SMTs. This example is **not a mandatory structure** for every source.

| Field | Purpose | Can It Serve Alone as an Event ID? |
|---|---|---|
| Kafka key `{"id":42}` | Business record identifier | **No**: the same order can change many times |
| `op` | `r`/`c`/`u`/`d` and connector-specific ops | No |
| `before`, `after` | Pre/post row state for upserts/deletes | No: two separate changes can share identical payloads |
| `source.file/pos/row`, `lsn` | Source coordinates for tracing and recovery | **Not automatically** unique across all row events |
| `source.name`/`db`/`table` | Identifies source scope | Must be paired with an appropriate identity/sequence |
| `ts_ms` | Timestamp recorded by connector or source | No: can collide or suffer clock skew |
| `transaction` | Transaction and intra-tx ordering metadata if supported | Helpful, but structure and coverage vary |
| Kafka `topic/partition/offset` | Identifies broker record in a partition | Identifies a **Kafka record**, not a source event replayed at another offset |

### There Is No Universal Event ID for Every Debezium Row Event

For raw row CDC streams, Debezium supplies source metadata rather than **automatically guaranteeing** a globally unique, stable `eventId` field across all connectors, operations, and snapshots.

In MySQL, `file + pos` alone may lack enough granularity to distinguish multiple row events at the same log offset; in PostgreSQL, a single `lsn` may not distinguish every row change within one transaction. If you construct a composite key from `sourcePartition + log position + transaction order + table + key`, verify **the exact contract of your connector and version**, including during snapshots and primary-key updates.

When you need a **durable business event ID**, a **transactional outbox** with an explicit `event_id` column is far easier to control than stitching together database-specific log metadata.

## 5. Idempotency Strategies and When to Use Each

| Strategy | Suitable Input | Primary Guarantee | Limitations |
|---|---|---|---|
| **Idempotent UPSERT** | Row CDC representing current state | Replaying identical state creates no duplicate rows | Older events arriving late can overwrite newer state |
| **Idempotent DELETE** | `op="d"` with stable key | Repeated deletes cause no errors or extra side effects | Older updates replayed after delete can resurrect the row |
| **Inbox / processed-event table** | Events with stable, unique IDs | Applies each event ID once per consumer | Requires unique constraints, local transactions, and retention management |
| **Version/sequence gating** | Sources with reliable monotonic per-entity versions | Blocks stale events from overwriting newer state | Requires strict versioning rules and delete markers |
| **Transactional outbox at sink** | External side effects or forwarding to other systems | Persists state and outbound intent in one DB transaction | Needs a relay and idempotent downstream consumers |
| **Reconciliation** | Lacking reliable IDs/versions or lost logs | Restores accurate state from source | Resource-intensive; cannot reconstruct historical external side effects |

You do not need every strategy simultaneously. For simple **state projections**, idempotent upserts + per-key sequential processing may suffice within clear boundaries. For **payments, emails, or ledger entries**, use stable event IDs with an inbox or outbox.

## 6. Case 1: Row CDC for Building a State Projection

Suppose source table `sales.orders` has columns `id`, `status`, and `version`. The source application increments `version` on every order status change, following a **strictly monotonic per-`id` rule**.

~~~text
order=42, version=7, status=NEW
order=42, version=8, status=PAID
order=42, version=9, status=SHIPPED
~~~

If only final state matters, you can use `(id, version)` to reject stale updates. This is a **source-managed business version**, not an arbitrary comparison of timestamps or Kafka offsets.

### 6.1. Version-Guarded SQL UPSERT

PostgreSQL projection table:

~~~sql
CREATE TABLE reporting.orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(32),
    last_version BIGINT NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

UPSERT:

~~~sql
INSERT INTO reporting.orders AS current_row
    (id, status, last_version, is_deleted)
VALUES
    (42, 'PAID', 8, FALSE)
ON CONFLICT (id) DO UPDATE
SET status = EXCLUDED.status,
    last_version = EXCLUDED.last_version,
    is_deleted = EXCLUDED.is_deleted
WHERE current_row.last_version < EXCLUDED.last_version;
~~~

If `version=9, status=SHIPPED` is already stored, replaying `version=8` leaves the row untouched. Receiving `version=8` twice is also blocked from redundant updates by the `<` predicate.

**Mandatory condition:** the source must genuinely increment `version` for **every relevant change**, never resetting it across migrations or row recreations, and each entity needs a stable key. If two messages share the same version with different payloads, that is a **contract violation** to flag and investigate, never silently resolved by arrival time.

### 6.2. DELETEs and Stale Events Resurrecting Records

If you only run `DELETE FROM reporting.orders WHERE id = 42`, replaying an older update afterward can **re-insert** the row. With source versions and versioned delete events, persist a **delete marker**:

~~~sql
INSERT INTO reporting.orders AS current_row
    (id, status, last_version, is_deleted)
VALUES
    (42, NULL, 10, TRUE)
ON CONFLICT (id) DO UPDATE
SET status = EXCLUDED.status,
    last_version = EXCLUDED.last_version,
    is_deleted = EXCLUDED.is_deleted
WHERE current_row.last_version < EXCLUDED.last_version;
~~~

Once version 10 marks the row deleted, replaying version 8 or 9 cannot resurrect the order. **Distinguish raw CDC deletes from versioned business delete events**: in many sources, `after=null` and `before` do not automatically contain a new "delete version". If the source lacks a reliable delete version, preserve per-key ordering or add an explicit business/outbox contract; **never treat `before.version` as a new delete version** unless the source guarantees that contract.

### 6.3. Snapshots Can Reintroduce Older State

Snapshot `op="r"` events can reappear during re-snapshots or incremental snapshots. Instead of treating `r` as "create a new order", treat it as **state synchronization**. If using versions, ensure snapshot rows share the same version space as streaming events.

Without business versions, maintain ordering at the Debezium/consumer layer, rely on the connector's snapshot/chunk collision mechanisms, and design reconciliation so stale snapshot reads cannot overwrite newer updates. Snapshots **do not guarantee** a unique business event ID per record.

## 7. Case 2: Inbox with Event IDs from a Transactional Outbox

When the source produces **business events** like `OrderPaid` instead of exposing raw row updates, it can insert into an **outbox table in the same transaction** that updates the order:

~~~sql
BEGIN;

UPDATE sales.orders
SET status = 'PAID'
WHERE id = 42;

INSERT INTO sales.outbox_events
    (id, aggregatetype, aggregateid, type, payload)
VALUES (
    'bc7042bc-56fb-498c-b7be-df6b0f35008f',
    'orders',
    '42',
    'OrderPaid',
    '{"orderId":42,"status":"PAID","version":8}'::jsonb
);

COMMIT;
~~~

*The SQL above uses PostgreSQL types as an example; create the tables, constraints, and transactions appropriately before running.* Debezium's Outbox Event Router SMT can promote `id` to the **event ID in Kafka headers** and `aggregateid` to the Kafka key; verify your actual SMT and converter configuration. **The event ID is generated once inside the source transaction** and remains identical across Debezium/Kafka replays.

### 7.1. Durable Inbox in the Target Database

When Spring Integration applies events into the `reporting` database, record **processed markers** in an inbox table:

~~~sql
CREATE TABLE reporting.processed_cdc_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

The composite key `(consumer_name, event_id)` lets multiple independent applications or flows track the same event under separate policies. `event_id` must be unique per the source contract; Kafka offsets **cannot substitute** for this ID.

Flow for **one event**:

~~~mermaid
sequenceDiagram
    participant K as Kafka CDC / outbox topic
    participant SI as Spring Integration handler
    participant DB as Reporting database
    K->>SI: eventId=E42
    SI->>DB: BEGIN
    SI->>DB: INSERT inbox(E42) ON CONFLICT DO NOTHING
    alt New ID
        DB-->>SI: inserted = 1
        SI->>DB: Update projection
        SI->>DB: COMMIT inbox + projection
    else Existing ID
        DB-->>SI: inserted = 0
        SI->>DB: COMMIT without altering projection
    end
    SI->>SI: ACK/commit consumer per container policy
    Note over SI,DB: If DB transaction rolls back, both inbox and projection roll back
~~~

The critical rule is **writing the inbox and updating the projection in the same database transaction**. Recording completion in a separate database or committing the inbox before business updates means a crash between the two can leave the inbox claiming "DONE" while the projection was never updated.

### 7.2. Illustrative Java Example with Spring JDBC

The model below assumes the consumer extracted a **stable event ID** from Kafka headers/outbox contract and a **per-`orderId` monotonic version** from the payload. It **cannot be used verbatim on raw Debezium envelopes** because row CDC lacks a built-in `eventId`.

~~~java
import java.util.UUID;

public record OrderStateEvent(
        UUID eventId,
        long orderId,
        long version,
        String status,
        boolean deleted) {
}
~~~

Transactional handler on the target database:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {
    private static final String CONSUMER_NAME = "order-reporting-projection";
    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderStateEvent event) {
        int inserted = jdbc.update("""
                INSERT INTO reporting.processed_cdc_events
                    (consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """, CONSUMER_NAME, event.eventId());

        if (inserted == 0) {
            // This event ID was already processed and committed previously.
            return;
        }

        jdbc.update("""
                INSERT INTO reporting.orders AS current_row
                    (id, status, last_version, is_deleted)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE
                SET status = EXCLUDED.status,
                    last_version = EXCLUDED.last_version,
                    is_deleted = EXCLUDED.is_deleted
                WHERE current_row.last_version < EXCLUDED.last_version
                """,
                event.orderId(),
                event.deleted() ? null : event.status(),
                event.version(),
                event.deleted());
    }
}
~~~

**Scope of this example:**

- Uses PostgreSQL `INSERT ... ON CONFLICT`, Spring JDBC, and Java text blocks; both tables must exist with the illustrated schemas.
- `@Transactional` must be enabled with a **transaction manager bound to the same `DataSource`** and invoked through a Spring proxy; never self-invoke internally expecting the annotation to take effect.
- If the inbox insert succeeds but the projection write throws, **both statements roll back**. Subsequent retries can reprocess cleanly.
- If the inbox already contains `eventId`, the method returns normally without extra side effects.
- Combining `eventId` + `version` solves two distinct problems: **duplicate deliveries of the same event** and **stale events arriving late**. If a source lacks reliable versions, omit version gating and enforce ordering/reconciliation differently.
- This example omits payload validation, event-name checks, signatures, version bounds, and business rules; add validation, error handling, and metrics in production.
- If the same `eventId` arrives with a **different payload**, raise a contract error instead of silently ignoring it; optionally store a payload checksum alongside the inbox row.

### 7.3. Why Is a Unique Constraint Mandatory?

An application may run multiple instances, or two workers may process the same event concurrently during retries/rebalances. Code like:

~~~text
if (!exists(eventId)) {
    applyBusinessChange();
    insertProcessed(eventId);
}
~~~

is **unsafe under concurrency**: both workers can observe `!exists` and both execute the side effect. `PRIMARY KEY (consumer_name, event_id)` paired with `INSERT ... ON CONFLICT DO NOTHING` delegates synchronization to **the database**, inside the same transaction as the business mutation, giving far stronger guarantees than an in-JVM `HashSet` or local lock.

## 8. When No Stable Event ID Exists: Choosing a Practical Strategy

Raw Debezium CDC on `orders` does not inherently contain `eventId`. Available options:

1. **State synchronization:** use idempotent upserts/deletes by primary key; never trigger side effects from snapshot events, and preserve ordering.
2. **Source-maintained version column:** compare per-entity versions inside the target transaction and retain delete markers.
3. **Derive event identity from source metadata:** only after verifying exact behavior for your connector/version, snapshot handling, and multi-row transactions; document the ID's exact scope.
4. **Unique business events needed:** emit from a transactional outbox with an event ID generated by the source application.
5. **No reliable ID/version/ordering available:** enforce sequential processing, block order-breaking redrives, or reconcile from source state; never claim duplicates are solved by an arbitrary hash.

### Why Isn't Hashing the Entire Payload an Event ID?

Two distinct updates can yield **the exact same `after` state**—for example, `PAID → NEW → PAID`, or updating an uncaptured column. The hash of `after` would collide despite representing two separate events. Conversely, the same source event serialized across two converter or schema versions can produce different bytes. Payload hashes help detect tampering or drift, but **do not automatically represent business identity**.

### Why Can't `updated_at` Replace Version?

Timestamps can collide, have insufficient resolution, suffer timezone/clock skew, or be updated manually. If a source enforces strictly monotonic per-entity timestamps, they may work within proven bounds, but most systems should prefer an **integer sequence/version** incremented in the same transaction.

## 9. Spring Integration: Where Does the ACK Boundary Sit?

Reference flow:

~~~text
Debezium -> Kafka CDC/outbox topic
    -> Kafka message-driven inbound adapter
    -> cdcInboundChannel (DirectChannel)
    -> deserialize/normalize contract
    -> validate key, event ID, version, op
    -> @Transactional OrderProjectionService.apply(...)
    -> once DB transaction has committed
    -> acknowledge Kafka record per listener container ack mode
~~~

**Core principle:** if the handler throws and the transaction rolls back, the adapter/container must receive the error to retry or invoke recovery per policy; never acknowledge consumption merely because the message entered memory.

| Component | Relationship to Idempotency |
|---|---|
| `DirectChannel` | Synchronous flow on caller thread; straightforward to ensure DB commits before the listener pulls the next record |
| `ExecutorChannel` or `QueueChannel` | Async handoff can return before DB commit; requires custom durability, ack protocol, and ordering |
| Service activator / transformer | Never swallow exceptions and report success if business data was not durably written |
| Spring Kafka listener container | Manages retries, acks, offsets, and DLTs depending on mode; wire the handler onto the adapter's actual container |
| `errorChannel` | Carries `ErrorMessage` for Spring Integration failures; does not automatically ensure DLT storage in Kafka |
| Outbound adapter / gateway | HTTP/JMS/AMQP calls can succeed and then time out; retries require receiver-side deduplication |

### 9.1. Manual Ack vs. Auto Ack

In Spring Integration Kafka, how acknowledgment is obtained and when offsets commit depend on the **listener mode, ack mode, and adapter/container version**. Not every `Message<?>` carries a fixed ACK header callable with a one-liner.

Logical flow:

~~~text
onMessage(record):
    try:
        event = decodeAndValidate(record)
        projectionService.apply(event)  # transaction must commit cleanly
        acknowledgeAccordingToContainerPolicy(record)
    catch error:
        propagateToContainerOrDurableRecovery(record, error)
        # Do not acknowledge record as successfully processed
~~~

When using auto/batch commits, verify what "handler finished" means; `@Transactional` completing only guarantees the **DataSource transaction**, not an atomic distributed transaction binding Kafka consumer offsets to database commits.

### 9.2. Do Not Rely on Kafka Exactly-Once for Target Databases

Kafka transactions can coordinate **produced Kafka records** and **committed Kafka offsets** atomically within Kafka. However, a Kafka transaction does not span JDBC writes, HTTP calls, emails, or external systems.

In a Kafka → Spring Integration → SQL pipeline, target-database idempotency remains mandatory even if Kafka-side exactly-once options are enabled. A failure between DB commit and Kafka commit still causes replays; an **inbox in the same DB transaction** turns replays into business no-ops.

## 10. Side Effects Outside the Database: Email, HTTP, JMS, and AMQP

If a handler both updates a projection and calls a payment API, sends an email, or publishes to a third-party queue, those two actions **do not share a single transaction**.

Hazardous sequence:

~~~text
1. DB: markOrderPaid()       -> succeeds
2. HTTP: sendInvoiceEmail()  -> server receives and sends email
3. Connection drops before response arrives
4. Consumer retries the whole flow
5. sendInvoiceEmail() executes a 2nd time
~~~

Even when `sendInvoiceEmail()` times out, you cannot assume the external service never processed it. For APIs that support it, pass a stable **idempotency key** (such as the source-controlled event ID) so the receiver caches and deduplicates by that key.

### 10.1. Transactional Outbox in the Target System

Another pattern is **recording outbound intent in the same DB transaction as the inbox and projection**:

~~~mermaid
flowchart LR
    K[(Kafka CDC topic)] --> SI[Spring Integration handler]
    SI --> TX[(Single DB transaction<br/>inbox + projection + outbound outbox)]
    TX --> RELAY[Outbox relay / publisher]
    RELAY --> Q[(Kafka / JMS / AMQP)]
    Q --> CON[Downstream consumer<br/>idempotent]
    CON --> EXT[Email / HTTP / payment service]
~~~

Suppose inside the transaction applying `OrderPaid`:

~~~sql
BEGIN;

-- 1. Insert inbox row by event ID with unique constraint.
-- 2. If event ID is new: update projection.
-- 3. If event ID is new: insert a row into outbound_outbox
--    with a stable business event ID / idempotency key.

COMMIT;
~~~

The relay may retry sending outbox rows, so **downstream receivers must still be idempotent**; a transactional outbox bridges the gap between **DB commit** and **publish intent**, without magically making external HTTP/email calls exactly-once if the external provider lacks support.

### 10.2. When Consumers Perform Cumulative Additions

For a business event `PaymentCaptured(amount=200000)`, never directly run:

~~~sql
UPDATE reporting.accounts
SET balance = balance + 200000
WHERE id = 10;
~~~

on every callback invocation. Ensure the credit executes only when **claiming a new stable event ID** inside the same transaction. For ledger systems, enforce `UNIQUE (payment_event_id)` on ledger entries and derive balances from valid entries; this is far easier to audit and reconcile than mutating a running total directly.

## 11. Ordering, DLTs, and Replay: Idempotency Can Still Break

Suppose:

~~~text
Kafka P1 offset 100: E1 -> order 42 = PAID
Kafka P1 offset 101: E2 -> order 42 = SHIPPED

E1 fails -> routed to DLT
E2 succeeds -> projection = SHIPPED
Later, E1 is redriven -> projection may regress to PAID
~~~

If the handler only performs a keyed UPSERT, replaying `E1` creates no extra row yet **overwrites newer state with older state**. That is an **ordering** failure rather than a duplicate failure.

Safeguards:

- **Preserve per-key/partition order:** stable Kafka keys, stable partitioners, and handlers that never scatter same-key events across uncoordinated async workers.
- **Reject stale events:** use monotonically increasing source versions checked and updated atomically in the database.
- **Control DLT redrives:** before replaying, check whether newer events have already been applied; repair via reconciliation instead of writing stale state.
- **Retain delete markers:** stale updates replayed later must never resurrect an entity deleted at a higher version.
- **Account for rebalances:** old workers must not overwrite state after partition ownership moves; manage in-flight tasks, fencing, and versions.

Kafka preserves order **within one topic-partition**, with no global order across partitions or topics. Adding partitions, changing key serializers, swapping partitioners, or rerouting can move an entity to a different partition, invalidating prior assumptions.

## 12. Delete Events and Kafka Tombstones

A Debezium DELETE normally emits an envelope with `op="d"` and `after=null`; the connector may also emit a Kafka tombstone with an **actual null value**:

~~~text
DELETE:
  key   = {"id":42}
  value = {"op":"d","before":{"id":42,...},"after":null,...}

TOMBSTONE:
  key   = {"id":42}
  value = null
~~~

The **Delete event** indicates the source row was deleted. The **Tombstone** serves key deletion in compacted Kafka topics; it is not an `op="d"` envelope and must not be executed as a second business deletion command.

In Spring Integration Kafka, deserializers/converters may represent null values using a sentinel like `KafkaNull`. Detect tombstones **before parsing JSON**, matching your exact adapter/API version.

Idempotency edge cases to test:

1. DELETE received twice: repeated delete is safe and does not trigger duplicate cancellation workflows.
2. Tombstone following DELETE: does not trigger a second refund command.
3. Stale update replayed **after** DELETE: requires ordering/versioning or reconciliation, especially if physical deletion erased version history.
4. Primary key change: connector may emit a delete on the old key and a create on the new key across two different partitions; handle per connector contract.

## 13. Errors, Retries, and Redrives Must Align with Deduplication Strategy

A pipeline can use Spring Kafka's `DefaultErrorHandler`/`DeadLetterPublishingRecoverer` or an equivalent error channel/adapter to route bad records to a DLT. However, **routing to a DLT does not mean the application applied the business change**.

| Situation | Recommended Handling |
|---|---|
| Target DB times out writing inbox/projection | Roll back transaction; retry with backoff; same event ID processes safely |
| DB commits, but Kafka ACK fails | Consumer re-reads; inbox unique constraint detects already-processed event ID |
| DLT holds a record older than current state | Check version/ordering; never replay blindly; reconcile if needed |
| Consumer sends email then times out | Receiver must support idempotency keys, or use an outbound outbox/dedup |
| Old Debezium source offset replays event at a new Kafka offset | Deduplicate by source event ID, or use idempotent state + ordering; Kafka offset is insufficient |
| Schema changed while older payloads replay | Consumers must support old/new contracts or versioned migrations/converters |
| Source logs purged; connector cannot resume | Inbox/DLT alone cannot fix this; run resnapshot and reconciliation |
| Table lacks a primary key | No stable identity for simple upserts/deletes; fix source key design |

### Inbox Retention

Purging `processed_cdc_events` markers too early allows a delayed redrive of an old event to be **processed again as brand new**. Inbox retention must cover Kafka retention, DLT retention, downtime windows, snapshot/replay cycles, and business archival rules.

If pruning the inbox is necessary, pair it with an alternative safeguard: snapshot/reconciliation, carefully sized TTLs, per-entity version watermarks, or strict replay-window limits. For financial side effects, transaction identities often must be kept long-term per accounting/payment rules.

### Failures After Commit

Avoid calling an external system **after DB commit inside the same handler** and throwing an exception back as if everything can roll back. An already-committed DB transaction will not auto-rollback when SMTP/HTTP times out. Decouple external side effects via an outbound outbox or receiver-side idempotency keys.

## 14. Testing Along the Failure Timeline

To truly verify idempotency, assert **database state** and **external side effects**, not just that the Kafka consumer offset advanced.

| Test Case | Failure Injection Point | Expected Outcome |
|---|---|---|
| 1. Duplicate Kafka record | Redeliver exact `(topic,partition,offset)` | Projection and side effects remain unchanged |
| 2. Duplicate Debezium source | Same source event at a **new** Kafka offset | No duplicate business mutation thanks to event ID/state idempotency |
| 3. Crash before DB commit | Inbox/projection transaction uncommitted | No partial effects; retry succeeds cleanly |
| 4. Crash after DB commit, before ACK | Target persisted, consumer offset uncommitted | Retry redelivers; inbox turns it into a no-op |
| 5. Parallel duplicate | Two workers receive the same `eventId` simultaneously | Unique constraint protects; only one transaction applies |
| 6. Out-of-order | `version=9` arrives before `version=8` | State remains at version 9; no regression |
| 7. Delete then update replay | Delete version 10, stale update version 8 | Deleted entity is not resurrected |
| 8. Snapshot/re-snapshot | `op="r"` received again | Syncs state only; fires no "created" notifications |
| 9. DLT redrive | Older event arrives after newer state committed | Does not overwrite newer data; redrive outcome audited |
| 10. HTTP/email timeout after success | Downstream succeeded, response lost | Idempotency key or outbound outbox prevents double side effect |
| 11. Schema change | Pre- and post-DDL events coexist | Handler handles both contracts per policy |
| 12. Purged source logs | Cannot re-read missed log window | Alerts fire and reconciliation/resnapshot runs; inbox does not claim to fix it |

### 14.1. Rehearsing a Crash Mid-Transaction

With an inbox transaction:

~~~text
BEGIN
  INSERT processed_cdc_events(event_id = E42) -> succeeds
  UPDATE reporting.orders                 -> throws exception
ROLLBACK
~~~

After rollback, the inbox **does not contain `E42`** and the projection is untouched; retrying `E42` runs safely.

If `INSERT processed_cdc_events` ran in its own separate transaction and committed first, a retry would think `E42` was already processed and **skip the UPDATE that never succeeded**. That is a critical design flaw.

### 14.2. Metrics Worth Observing

- Count of **duplicate event IDs** caught by the unique constraint, broken down by source/consumer.
- Kafka CDC rate, per-partition consumer lag, and retry/rebalance counts.
- Count of stale events rejected by version gating.
- Processing latency, rollbacks, database deadlocks, and commit failures.
- DLQ/DLT volume, oldest record age, redrive counts, and unreconciled records.
- Drift between source database and projection in row counts, keys, and business states.
- External email/payment/API side-effect counts per event ID to catch duplicate executions.

Never treat `duplicate_count = 0` alone as proof of safety. Zero duplicates can happen simply because the consumer **dropped records** or lacked event IDs. Always pair metrics with business data reconciliation.

## 15. End-to-End Scenario: Order Paid and Invoice Sent

A MySQL source stores orders and a transactional outbox. Debezium emits `OrderPaid(eventId=E42, orderId=42, version=8)` to Kafka. Spring Integration receives it, updates a projection, and triggers an invoice email request.

**Recommended design:**

1. Source producer writes the `orders` change and outbox `E42` in the same transaction.
2. Debezium's Outbox Event Router emits the event with key `orderId` and stable ID `E42` (typically in a header with default SMT settings).
3. Spring Integration's inbound adapter receives the record, validates event ID, key, and version, and passes it over a `DirectChannel` into a transactional handler.
4. The handler inserts inbox `E42`, updates the projection if the version is newer, and writes an **outbound outbox** row requesting invoice delivery—all inside **one database transaction**.
5. After the DB transaction commits, the consumer acknowledges the record per listener container policy.
6. A relay sends invoice requests from the outbound outbox; the invoice sender deduplicates on `E42` or a stable invoice request key.
7. If a crash occurs at any stage, retries may happen without creating multiple invoices or payments for the same business event.

If `OrderPaid` is redriven after `OrderShipped`, version gating prevents the projection from regressing, while the inbox prevents resending the invoice for `E42`. Two layers of defense solve **two distinct problems**.

### A Business Edge Case to Clarify

If the source can emit **two distinct `OrderPaid` events for the same `orderId`** (for example, split installment payments), never deduplicate solely by `orderId`: doing so would drop valid payments. Each payment needs its own **payment capture/transaction** identity, while `orderId` can remain the partition key to preserve per-order ordering.

## 16. Practice Exercises

### Exercise 1 — Distinguishing Duplicate from Stale

A projection stores `orders.id=42, version=9, status=SHIPPED`. The consumer receives:

~~~text
A: eventId=E8, orderId=42, version=8, status=PAID
B: eventId=E9, orderId=42, version=9, status=SHIPPED
C: eventId=E9, orderId=42, version=9, status=SHIPPED
~~~

Identify which record is stale, which is a duplicate assuming B was already processed, and why `WHERE id=42` alone is insufficient.

### Exercise 2 — Commit Point

Two designs:

**A**

~~~text
INSERT inbox -> COMMIT
UPDATE projection -> COMMIT
ACK Kafka
~~~

**B**

~~~text
BEGIN
INSERT inbox
UPDATE projection
COMMIT
ACK Kafka
~~~

Which design is safer against a crash between the two SQL statements? Explain what happens if `UPDATE` fails.

### Exercise 3 — Duplicate Email Sent

A handler uses an inbox transaction and stores `OrderPaid` once, yet calls an email service after DB commit. The email service actually sends the email, but the response times out so the job retries. Propose how to prevent sending the invoice twice.

### Exercise 4 — Choosing a Deduplication Key

A system sees two CDC records with the same business key `orders.id=42` from two separate transactions: one updates `status=PAID`, the other `status=SHIPPED`. Should `orders.id` be used as the inbox key? If not, how do you record both changes?

<details>
<summary>Solution Hints</summary>

1. A is stale (`version=8`), B is the version 9 event, and C is a duplicate of B by `eventId=E9`. An unversioned UPSERT would regress the status back to `PAID` when applying A.
2. B is safer: inbox and projection commit or roll back atomically. In A, crashing after the inbox commit but before the projection update makes retries assume the event was already handled.
3. Use an outbound outbox where each email request carries a stable idempotency key; the email worker/provider deduplicates by that key and retains the result durably. If the provider lacks deduplication support, add delivery-status checks and account for integration limits.
4. No. `orderId` identifies the entity, not **each change**. You need a unique event ID from a transactional outbox or a verified source event identity, while keeping `orderId` as the partition/upsert key.

</details>

## 17. Implementation Checklist

- [ ] Clarify whether you must protect **projection state**, **transaction ledgers**, **email/API side effects**, or all three.
- [ ] Understand the distinct roles of Debezium source offsets, Kafka topic offsets, and consumer group offsets.
- [ ] Establish a **stable event ID** when event deduplication is needed; never assume raw Debezium row events include a global event ID.
- [ ] Distinguish entity key, event ID, version/order, and Kafka topic-partition-offset.
- [ ] For an inbox, enforce a unique constraint and mutate target state **in the same DB transaction**.
- [ ] For UPSERTs, verify replayed old events cannot overwrite newer state using reliable versions or strict ordering.
- [ ] For DELETEs, account for delete markers, primary-key changes, and Kafka tombstones.
- [ ] For snapshot `op="r"`, never fire inappropriate creation side effects.
- [ ] Design Spring Integration channels and handlers so ACK/commit happens only after safe target persistence.
- [ ] When using async channels, build durable handoffs and separate checkpointing before ACKing.
- [ ] Configure retries, DLT/redrive, idempotency keys for HTTP/JMS/AMQP/email, and an outbound outbox where needed.
- [ ] Align retention across the inbox, Kafka topics, DLTs, and allowed replay windows.
- [ ] Test duplicate Kafka records, source replays at new Kafka offsets, crashes before/after DB commits, and stale events.
- [ ] Reconcile source vs. target data and monitor duplicate/stale/retry/DLT metrics.

## 18. References

- [Debezium Frequently Asked Questions](https://debezium.io/documentation/faq/): explains source and consumer replays after crashes and why consumers must tolerate duplicates.
- [Debezium Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): outbox structure, event IDs, aggregate keys, and topic routing.
- [Spring Integration — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): message-driven adapters, listener configuration, retry/recovery, and `MessageChannel`s.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): scope of Kafka transactions across consume–process–produce and offset commits.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): coordinating Kafka transactions with Spring transaction management and database transactions.

**Key Takeaway:** Debezium and Kafka consumers can replay changes after crashes, timeouts, or retries. **State idempotency**, **event-ID deduplication**, and **version/order enforcement** mitigate different risks. In Spring Integration, place transaction boundaries around the actual business persistence, commit offsets only after durable completion, and protect external side effects as well. Only then will receiving the same CDC event multiple times avoid duplicating data or business impacts.
