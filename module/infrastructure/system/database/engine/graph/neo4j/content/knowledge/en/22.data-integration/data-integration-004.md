# Idempotency, Event Ordering, and Duplicate Event Handling

## 1. The Event Integration Problem with Neo4j

An order management system pushes events to a service updating a Neo4j graph. Whenever a product is sold, the service updates a counter on the `Product` node; when an order changes status, the service syncs properties on the `Order` node; when a customer is assigned a role, the service may create or modify a relationship.

In production, an event may be redelivered due to timeouts, consumer restarts, broker redelivery, or explicit application retries. At the same time, events for **the same entity** can arrive out of order because of multiple producers/workers, network delays, or replay workflows.

Suppose order `O100` has three events:

| Event | Order Version | Content | Consumer Arrival Time |
|---|---:|---|---|
| E-21 | 21 | `status = CREATED` | 09:00:03 |
| E-23 | 23 | `status = SHIPPED` | 09:00:04 |
| E-22 | 22 | `status = PAID` | 09:00:08 |

If the consumer updates `Order.status` in **arrival order** without checking the version, the final status becomes **PAID** even though the source already moved to **SHIPPED**. If the broker redelivers `E-22`, the duplicate event can keep corrupting the projection.

For **additive/cumulative** events, the risk is even clearer: processing the same `OrderLineAdded` event with `quantity = 2` twice increments `soldUnits` by **4** instead of **2**.

Three distinct concerns must be separated:

- **Idempotency:** reprocessing **the same logical operation** does not duplicate its business effect.
- **Event ordering:** an entity is updated according to the before–after dependency rules of its versions/events.
- **Duplicate delivery:** a message that has already been received and possibly committed is redelivered, or the same action is published multiple times.

This lesson belongs to the **Data Integration** chapter in Neo4j: the focus is on keeping nodes, relationships, properties, and projection state accurate when syncing from message brokers, CDC, or Java services. These principles apply to the Java Driver and Spring Data Neo4j; specific implementation details also depend on the broker and driver version.

## 2. At-Most-Once, At-Least-Once, and Effectively-Once Processing

### 2.1. Why Can an Event Arrive Multiple Times?

For example, a consumer receives an event, writes successfully to Neo4j, but **crashes before acknowledging processing (ack)** to the broker:

~~~text
Producer        Broker             Consumer             Neo4j
   |               |                   |                    |
   |--- E-100 ---->|                   |                    |
   |               |--- E-100 -------> |                    |
   |               |                   |--- commit -------> |
   |               |                   | <--- success ------|
   |               |                   X crash               |
   |               |                   |                    |
   |               |--- E-100 again -> |                    |
~~~

Because the broker did not receive an ack, it may redeliver E-100. A committed Neo4j transaction **does not mean** the broker knows it happened.

| Delivery Guarantee | General Behavior | Consumer Responsibility |
|---|---|---|
| At-most-once | May lose events, avoids redelivery | Suitable only when data loss is acceptable |
| At-least-once | Events are typically not lost with retries, but may arrive multiple times | Idempotent processing and progress tracking |
| Exactly-once within a specific scope | A platform may guarantee semantics within its own internal transactions | Check scope limits; do not assume Neo4j side effects are automatically once-only |

Even when a broker advertises a feature called **exactly-once**, the broker transaction and the Neo4j write transaction do not automatically merge into **a single distributed transaction**. The practical goal is an **exactly-once effect** for an operation with a stable identity key: each logical event mutates the graph **once**, even if the consumer receives it multiple times.

### 2.2. Specify What "Idempotency" Applies To

Two update patterns carry different semantics:

~~~cypher
// Assign an absolute state
MATCH (o:Order {orderId: $orderId})
SET o.status = 'PAID';
~~~

~~~cypher
// Accumulate a value
MATCH (p:Product {sku: $sku})
SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity;
~~~

When executed **repeatedly against the exact same database state**, assigning `status = 'PAID'` does not alter the value further; adding to `soldUnits` changes the value on every execution.

However, absolute state assignment is **not safe against late stale events**: once the status is already SHIPPED, processing a late PAID event reverts it to PAID. Therefore, **idempotency of a single assignment and correctness of an event sequence are two separate requirements**.

## 3. Designing an Event Contract with Identity and Version

Example payload published by an orders service:

~~~json
{
  "eventId": "orders-service:E-000123",
  "eventType": "OrderStatusChanged",
  "source": "orders-service",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "O100",
  "aggregateVersion": 23,
  "occurredAt": "2026-11-25T09:00:00Z",
  "payload": {
    "status": "SHIPPED"
  }
}
~~~

| Field | Purpose | Principle |
|---|---|---|
| `eventId` | Identify **one logical event** across retries/replays | Remains stable across redeliveries |
| `eventType` | Select graph mapping logic | Has per-type schema and validation |
| `source` | Identify namespace and trusted source | Used when events arrive from multiple systems |
| `schemaVersion` | Select payload decoder | Do not confuse with the Order's entity version |
| `aggregateId` | Identify the node/ordering stream to protect | Never use Neo4j internal IDs as foreign keys |
| `aggregateVersion` | Define mutation order **for an aggregate** | Incremented according to producer rules |
| `occurredAt` | Event timestamp metadata | Do not replace version for ordering arbitration |
| `payload` | Business data to apply | Distinguish snapshots from deltas |

**Do not confuse the two version types:** `schemaVersion` describes the **message format**, while `aggregateVersion` describes the **entity mutation order**.

### 3.1. Stable Event ID Across Retries

If a producer generates a **new UUID each time it retries the same operation**, consumers treat those messages as **different events**. Every deduplication technique based on `eventId` breaks down.

Assign the ID when creating the logical event, persist it durably, and keep it unchanged across retries. With an outbox pattern, the same outbox row must carry the same `eventId` every time the publisher retries sending it.

### 3.2. Within What Scope Is an ID Unique?

Two independent systems might both generate an `eventId` of `123`. Use a composite key:

~~~text
eventKey = source + ":" + eventId
~~~

For instance, `crm:123` and `orders:123` are two distinct events.

In multi-tenant systems, the namespace may also require `tenantId`. **The uniqueness scope of `eventKey` must match the ID generation contract**; never assume a short code is globally unique.

### 3.3. Payload Hash to Detect ID Collisions

The same `eventKey` carrying different content may indicate a producer bug, data corruption, or changed event semantics. Storing a **payloadHash** computed from a canonicalized representation of the payload helps distinguish:

- **Same `eventKey`, same `payloadHash`:** typically a legitimate redelivery.
- **Same `eventKey`, different `payloadHash`:** a conflict requiring alerts and investigation—never silently treat it as a safe duplicate.

Standardize canonicalization: JSON key ordering, numeric types, character encoding, and schema version can all affect the digest. In strict systems, direct comparison of key business fields may also be necessary.

## 4. Designing the Graph Model and Applied-Event Ledger

Two groups of nodes serve different purposes:

~~~text
(:Product {sku, soldUnits})
(:AppliedEvent {eventKey, source, eventId, payloadHash, appliedAt})
~~~

You can optionally add a traceability relationship:

~~~text
(:AppliedEvent)-[:APPLIED_TO]->(:Product)
~~~

The `Product` node holds business state; `AppliedEvent` is a **receipt/ledger** recording that an event has already taken effect on the Neo4j projection. This ledger can live in the same Neo4j database or in another system with suitable transactional support; this lesson uses the **same Neo4j transaction**.

Create uniqueness constraints for both the business key and `eventKey`:

~~~cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT applied_event_key_unique IF NOT EXISTS
FOR (e:AppliedEvent)
REQUIRE e.eventKey IS UNIQUE;
~~~

The two constraints serve distinct roles:

- `Product.sku` prevents creating two Product nodes with the same SKU.
- `AppliedEvent.eventKey` prevents **two transactions from committing two receipts for the same eventKey**.

Create the schema before concurrent event processing starts. If duplicate keys already exist, constraint creation fails and data must be cleaned first. Uniqueness constraints do not enforce that key properties are non-null, so inputs must still be validated.

### 4.1. Shortcomings of Using MERGE Alone

~~~cypher
MERGE (p:Product {sku: $sku})
SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity;
~~~

This query avoids creating duplicate Product nodes **when backed by a proper constraint**, yet does not stop **the same event from adding `soldUnits` a second time**. `MERGE` finds or creates the **Product node**, without tracking which events already added quantities.

Similarly, merely adding:

~~~cypher
MERGE (e:AppliedEvent {eventKey: $eventKey})
WITH e
MATCH (p:Product {sku: $sku})
SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity;
~~~

is still wrong: even when `MERGE` matches an existing receipt, the pipeline still executes `SET`. **`MERGE`ing a receipt does not automatically mean "execute subsequent steps only ON CREATE."**

## 5. Processing Deltas with Receipts and Constraints in One Transaction

Suppose a `ProductUnitsSold` event carries `sku` and a positive integer `quantity`. The Product node already exists; each event must increment `soldUnits` strictly once.

~~~cypher
MATCH (p:Product {sku: $sku})
CREATE (e:AppliedEvent {
    eventKey: $eventKey,
    source: $source,
    eventId: $eventId,
    payloadHash: $payloadHash,
    appliedAt: datetime()
})
SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity
CREATE (e)-[:APPLIED_TO]->(p)
RETURN p.sku AS sku, p.soldUnits AS soldUnits;
~~~

This query has three essential properties:

1. **`MATCH Product` first:** if the SKU is missing, zero rows proceed to `CREATE` the receipt. The application must detect 0-row results and handle missing reference data.
2. **`CREATE AppliedEvent`** attempts to insert a new receipt, guarded by the `AppliedEvent.eventKey` uniqueness constraint. The receipt, audit relationship, and `soldUnits` update happen in **the same transaction**.
3. For an already-committed `eventKey`, a subsequent `CREATE` violates the uniqueness constraint. The transaction fails and **commits no second increment**. The application inspects the existing receipt and classifies the delivery as a duplicate or a conflict.

**Guarantee scope:** this pattern holds if every worker updating `soldUnits` from events goes through the same receipt/constraint mechanism with a stable `eventKey`. There is no guarantee if another worker bypasses the rule and increments directly.

### 5.1. Why Use CREATE Receipt Instead of MERGE Here?

`CREATE` forces the transaction to prove `eventKey` **has not been used yet** via the uniqueness constraint. If the key already exists, the write fails and rolls back. This creates an explicit **deduplication gate**.

If choosing `MERGE` on the receipt instead of `CREATE`, you must reliably detect whether the receipt was created in this transaction so that **business mutations run strictly in the creation branch**. Never simply put an accumulative `SET` after `MERGE` and assume idempotency.

### 5.2. Two Workers Receive the Same Event Concurrently

~~~text
Consumer A              Neo4j                Consumer B
    |                       |                      |
    |-- CREATE E-100 ------>|<------ CREATE E-100--|
    |                       |                      |
    |     one transaction commits                  |
    |     the other transaction cannot commit      |
    |     duplicate receipt eventKey               |
~~~

Depending on timing and transaction mechanics, one worker may wait or receive a constraint/transaction error. The crucial **invariant** is that the constraint prevents **two receipts with the same `eventKey` from committing**. Because the receipt and business update share a transaction, a duplicate event cannot be applied twice by this handler.

Upon catching an error, **do not assume every constraint violation is a duplicate**. Another constraint might have been violated. Verify the error code, `eventKey`, and the committed receipt's payload.

### 5.3. Handling Transaction Outcomes

| Outcome | Meaning and Handling |
|---|---|
| One `RETURN` row, transaction committed | Event applied; safe to ack broker |
| Product not found | Zero rows processed; report data error or wait for entity per rules |
| `eventKey` uniqueness violation with matching `payloadHash` | Event already applied previously; do not re-apply, treat delivery as complete |
| `eventKey` duplicate with differing `payloadHash` | Producer/data conflict; alert and do not ack as normal success until resolved |
| Transient/deadlock error | Retry the **entire transaction** with bounded backoff |
| Unknown commit status after disconnect | Query receipt in a fresh session/transaction before deciding to retry |

Distinguish **"DB commit succeeded"** from **"client received success response."** A network drop right after commit leaves the client unsure of the outcome; the receipt provides the proof to check.

## 6. Other Idempotency Techniques

The receipt pattern is a general solution for delta events needing exact application counts. Depending on data semantics, complementary techniques exist.

| Technique | Suitable Scenario | Limitation |
|---|---|---|
| `MERGE` node on stable key | Creating/updating identifiable entities | Does not prevent double-counting delta increments |
| `MERGE` relationship between identified nodes | Creating business links | Must consider concurrency and single-relationship invariants |
| Receipt with `eventKey` and uniqueness constraint | Every event must apply strictly once | Storage cost, requires retention policy |
| Absolute snapshot assignment with version guard | Syncing latest state | `SET` alone does not fix out-of-order arrivals |
| Idempotency key per **business command** | Producer may emit multiple distinct event IDs for one user action | Requires explicit `operationId` contract |
| Serialization by aggregate key | Prevents two workers from processing one entity's history simultaneously | Requires rebalance, timeout, and replay management |

### 6.1. Duplicate Messages vs. Duplicate Business Actions

Suppose a client sends a "create order" command twice due to a timeout. The producer might emit **two different `eventId`s** even though this was **one user request**. An `eventId`-based receipt treats them as two valid events.

If the business requires creating strictly one order per click of "Place Order," the API/producer also needs an **operationId** or **requestId** stable across request retries. This ID can become a unique entity key or producer-side ledger entry. A consumer deduplicating deliveries cannot infer that two different `eventId`s represent the same command.

## 7. Event Ordering: Late Events and Aggregate Versions

### 7.1. Use Per-Entity Versions, Not Arrival Time

Suppose Order O100 has the sequence:

~~~text
version=21  CREATED
version=22  PAID
version=23  SHIPPED
~~~

The current projection state might store:

~~~text
(:Order {
  orderId: 'O100',
  status: 'SHIPPED',
  lastAppliedVersion: 23
})
~~~

A consumer receiving **version=22** again must not revert the status from SHIPPED back to PAID. Version validation must happen at apply time.

One message having a later `occurredAt` than another **does not always mean** it is a newer logical version: server clocks drift, network delays vary, and producers differ. An authoritative `aggregateVersion` or sequence issued by the source is far more reliable for ordering **within an aggregate's scope**.

### 7.2. Two Event Types, Two Ordering Policies

**Full-state / snapshot event:**

~~~json
{
  "eventId": "E-23",
  "aggregateId": "O100",
  "aggregateVersion": 23,
  "payload": {
    "status": "SHIPPED",
    "totalInCents": 360000,
    "currency": "VND"
  }
}
~~~

Full snapshots may allow **advancing to a higher version** and skipping older snapshots, provided the producer guarantees version N contains all required state and skipped intermediate versions carry no separate side effects.

**Delta event:**

~~~json
{
  "eventId": "E-23",
  "aggregateId": "O100",
  "aggregateVersion": 23,
  "payload": {
    "addedAmountInCents": 120000
  }
}
~~~

A delta describes **only one change**. Skipping version=22 and applying version=23 leaves the projection missing part of the total. For deltas requiring full sequence processing, you cannot simply keep the highest version.

**Key rule:** "higher version" alone is not enough to decide whether intermediate messages can be skipped. The decision depends on **full snapshot** vs. **history-dependent delta** semantics.

### 7.3. Version Decision Matrix

Suppose an aggregate's projection has `lastAppliedVersion = 21` and the producer issues **contiguous** versions for all events this projection consumes.

| Incoming Event | Condition | Handling for Sequential Deltas |
|---|---|---|
| `version = 22` | Exact next version | Check receipt, apply, and advance checkpoint to 22 |
| `version = 21` | Old or redelivered | Do not re-apply delta; verify `eventId`/payload |
| `version = 20` | Very old | Safely ignore or audit against history |
| `version = 23` | Gap missing version 22 | Hold pending, fetch/replay version 22; do not add prematurely |
| `version = 22` with different `eventId` than recorded | Version conflict | Investigate; do not apply arbitrarily |

This matrix holds **only** when the source sequence is contiguous for the event subset consumed by the projection. If a producer shares one counter across multiple event types while the consumer subscribes to only a subset, use a different checkpointing scheme; never assume every missing integer indicates a lost message.

### 7.4. Broker Ordering Does Not Guarantee Neo4j Commit Order

If a broker partitions by aggregate key, messages for a single key arrive in order within the same partition. However:

- A consumer may process multiple records in the same partition concurrently.
- One record may fail and retry later, allowing a subsequent record to commit first.
- Rebalances or multiple concurrent pipelines can interleave schedules differently.
- Backfill/replay jobs may bypass normal broker streams.

Therefore, **partitioning by aggregate key** reduces out-of-order risk, while target-side version checks and transactional writes must still be explicitly engineered.

## 8. Tracking Processing State per Aggregate

One way to represent checkpoints:

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
MATCH (o:Order {orderId: $orderId})
RETURN o.lastAppliedVersion AS lastAppliedVersion,
       o.status AS currentStatus;
~~~

When receiving an event, the handler must decide whether it can be applied. Logically:

~~~text
receive event E
  |
  v
validate schema, key, version, payload
  |
  +-- eventKey already applied --> compare payload --> duplicate or conflict
  |
  +-- version < current version --> stale --> safely ignore
  |
  +-- version = next --> apply + receipt + checkpoint in same transaction
  |
  +-- version > next --> pending/replay missing gap
~~~

**Concurrency note:** reading `lastAppliedVersion`, comparing in Java, and then running a separate `SET` query **does not form an atomic compare-and-swap**. Two workers can simultaneously read the old version and both conclude their event is valid.

For pipelines enforcing strict sequential versions, combine **per-aggregate serialization** with Neo4j locking/coordination mechanisms, or a conditional update pattern verified under contention. Simply writing `MATCH ... WHERE o.lastAppliedVersion = $expectedVersion SET ...` should not be assumed sufficient across all concurrent schedules: the predicate may be evaluated before the transaction acquires the necessary write lock.

When implementing write-lock coordination, ensure you **re-read state after acquiring the lock**, then place the state update, receipt, and checkpoint inside **the same transaction**. Auto-locking details and Cypher clause behavior depend on Neo4j versions, so test concurrency under your target runtime version.

### 8.1. Never Advance Checkpoints Ahead of Data

A broken design:

~~~text
1. write lastAppliedVersion = 23
2. commit
3. update Order.status = SHIPPED
4. commit
~~~

If the process crashes between steps 2 and 3, a retry sees checkpoint 23 and may skip the event even though the status was never updated.

Commit **receipt + business mutation + `lastAppliedVersion`** as a single **atomic transaction unit**. If the transaction rolls back, none of the three effects are persisted.

### 8.2. One Event Updating Multiple Nodes and Relationships

For example, `OrderConfirmed` updates the `Order` node and creates `(Customer)-[:PLACED]->(Order)`. If the event requires all-or-nothing atomicity:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (o:Order {orderId: $orderId})
CREATE (e:AppliedEvent {
    eventKey: $eventKey,
    payloadHash: $payloadHash,
    appliedAt: datetime()
})
SET o.status = 'CONFIRMED'
MERGE (c)-[:PLACED]->(o)
CREATE (e)-[:APPLIED_TO]->(o)
RETURN o.orderId AS orderId;
~~~

The constraint on `AppliedEvent.eventKey` blocks duplicate event application; graph changes share one transaction. This assumes endpoints already exist and the pipeline enforces a matching version policy. `MERGE` on the relationship expresses the link, yet uniqueness constraints on Customer/Order **do not enforce a single-relationship invariant per endpoint pair** under uncoordinated concurrent writes.

## 9. Handling Out-of-Order Events by Business Semantics

### 9.1. Waiting for Missing Messages (Reorder Buffer)

For sequential deltas, when currently at version 21 and version 23 arrives:

1. Persist event 23 in a **pending inbox** or durable buffer.
2. Fetch or replay event 22 from the broker/source.
3. Apply event 22 and event 23 in order.
4. Clear the pending entry once target state and checkpoint are confirmed.

Never hold event 23 only in RAM where a crash would lose track of it. Pending storage needs retention limits, retries, and alerts when gaps persist too long.

### 9.2. Latest Snapshot Recovering Missing Gaps

If events are **full snapshots** containing complete state, the projection can jump from version 21 to version 23 without applying version 22 when all of these hold:

- The source confirms snapshot 23 represents complete valid state.
- Version 22 has no distinct side effects that must execute individually.
- Version updates are guarded so late event 22 cannot overwrite later.
- Audit/reconciliation rules allow skipping intermediate transitions.

Never apply this casually to monetary balances, delta inventories, event counters, or processes requiring full audit trails.

### 9.3. Conflicting Multiple Sources

If CRM and Sales both update `Customer.name`, each source may maintain its own version sequence. You cannot directly compare `CRM version 12` with `Sales version 40` and conclude 40 is newer in business terms.

Define clear rules:

- Which source holds **ownership** of each property?
- Should `crmName` and `displayName` be separated to preserve both views?
- Is only the authoritative source allowed to mutate shared state?
- When merging is required, do you use source priority, per-source version vectors, or explicit domain logic?

`occurredAt` does not resolve multi-source conflicts either. Choosing an authoritative source per field is usually far easier to verify than "highest timestamp wins" under distributed clocks.

## 10. Duplicate Events in LOAD CSV, JSON, and CDC

### 10.1. Batch Loading with UNWIND

A JSON batch may contain multiple messages where an `eventKey` appears more than once. This statement:

~~~cypher
UNWIND $events AS ev
MATCH (p:Product {sku: ev.sku})
SET p.soldUnits = coalesce(p.soldUnits, 0) + ev.quantity;
~~~

is **not idempotent**. If an event appears twice in the array or the entire batch is retried, quantities are added again.

Each event must undergo identity and receipt checks; process events individually in separate transactions or design batches with explicit deduplication gates. When using `CREATE AppliedEvent` with a uniqueness constraint inside **one multi-event transaction**, a single duplicate event can **roll back the whole batch**. This is an engineering trade-off based on throughput goals and error isolation needs.

### 10.2. CDC and Ordering from Relational Sources

In Change Data Capture (CDC), metadata typically includes:

- Changed record ID or source log position.
- Table name and row primary key.
- Operation type: INSERT/UPDATE/DELETE.
- Offset, LSN, or log coordinates specific to the source engine.
- Change timestamp and before/after row images.

An **offset** or log position enables resume/replay; **`eventKey`** can be derived from stable CDC record keys and an appropriate namespace. Never assume raw numeric offsets are globally unique across all partitions, databases, or epochs; verify the connector contract.

For state transitions, the `after` payload can act as a snapshot of a single row. However, assembling state across multiple tables/aggregates may still require multiple events and ordering constraints; a snapshot of **one SQL row** is not necessarily a full snapshot of the **entire graph projection**.

### 10.3. Scheduled Imports That Replay Records

With nightly CSV snapshots, `MERGE`ing nodes by key prevents duplicate nodes, yet relationships and cumulative metrics must be handled deliberately. For instance, total revenue should be **recomputed from uniquely identified source records**, or overwritten via versioned snapshots; never add a CSV's daily/running total onto the same node every night if the CSV repeats cumulative figures.

A relational or CSV source lacking event IDs needs a deterministic **idempotency key** built from meaningful operational identifiers (e.g., transaction line ID + event type + version), while clarifying whether a "data replay" represents the same logical event.

## 11. Java Driver: Receipts and Updates in Managed Transactions

The Java example below executes an event incrementing `quantity` on Product using **one Cypher statement inside a managed write transaction**. It assumes the schema has the two uniqueness constraints from Section 4 and inputs have been validated.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ProductEventWriter {
    private final Driver driver;

    public ProductEventWriter(Driver driver) {
        this.driver = driver;
    }

    public long applySoldUnits(
            String eventKey, String source, String eventId,
            String payloadHash, String sku, long quantity) {

        if (eventKey == null || eventKey.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid event input");
        }

        String cypher = """
            MATCH (p:Product {sku: $sku})
            CREATE (e:AppliedEvent {
                eventKey: $eventKey,
                source: $source,
                eventId: $eventId,
                payloadHash: $payloadHash,
                appliedAt: datetime()
            })
            SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity
            RETURN p.soldUnits AS soldUnits
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx -> {
                var result = tx.run(cypher, Map.of(
                    "eventKey", eventKey,
                    "source", source,
                    "eventId", eventId,
                    "payloadHash", payloadHash,
                    "sku", sku,
                    "quantity", quantity
                ));
                if (!result.hasNext()) {
                    throw new IllegalStateException(
                        "Product was not found: " + sku
                    );
                }
                return result.single().get("soldUnits").asLong();
            });
        }
    }
}
~~~

This snippet shows only the **fresh-application branch**. When the event was already processed earlier, the uniqueness constraint raises a write error; the caller must catch **the appropriate exception type**, open a new read session/transaction to inspect the receipt, and compare `payloadHash`. If key and payload match, return "already processed" to the broker without incrementing `soldUnits` again. If the key matches with a differing payload, raise a conflict alert.

Never catch all exceptions and treat them as duplicates: network drops, timeouts, lock errors, schema issues, or invalid data require distinct handling. Verify exact exception error codes and driver auto-retryable error classes for your Neo4j and Java Driver versions.

### 11.1. Why Must the Callback Be Retry-Safe?

`session.executeWrite(...)` may re-invoke the callback when encountering transient errors classified as retryable by the driver. If the callback executes only idempotent Neo4j write statements, retries are straightforward to reason about.

**Never send emails, invoke payment gateways, or publish external side-effecting events inside the callback** without an outbox/idempotency guarantee. The callback may execute multiple times; rolling back a Neo4j transaction does not undo an already-dispatched HTTP request.

### 11.2. Ack the Broker Only After Confirming Database Results

A semantically safe processing flow:

~~~text
Receive event from broker
    |
Validate schema, ID, version
    |
Begin Neo4j managed transaction
    |
Create receipt / update graph / checkpoint
    |
Commit succeeded?
    |-- Yes --> ack/commit broker position
    |
    |-- Unknown --> check receipt; may retry
    |
    |-- Clear error --> classify retry / pending / conflict / DLQ
~~~

Acking **before committing Neo4j** allows a consumer crash post-ack to lose the update. Committing Neo4j before acking and then crashing causes the broker to redeliver, which the receipt safely detects so the update is not applied twice.

This is application-level coordination; it does not turn Neo4j and the broker into a single distributed transaction.

### 11.3. With Spring Data Neo4j

In a Spring application, a service can use `@Transactional` with a properly configured transaction manager to group graph updates and receipt writes within one Neo4j transaction. Repository `save(...)` or `Neo4jClient` does not prevent duplicate events without an event ID/receipt and uniqueness constraint.

When mixing SQL, brokers, and Neo4j, distinguish which transaction manager governs which resource. Never assume a single `@Transactional` annotation guarantees atomic commits across independent systems.

## 12. Retries, Poison Events, and Dead-Letter Queues

Classify failures before deciding whether to retry.

| Category | Example | Recommended Handling |
|---|---|---|
| Retryable/transient | Lock contention, deadlock, temporary overload | Bounded retries with backoff, track attempt counts |
| Confirmed duplicate | Receipt matches `eventKey` and `payloadHash` | Ack without re-applying |
| Data conflict | Same `eventKey` with differing payload, version conflict | Quarantine, alert, investigate |
| Schema/missing key error | Missing `aggregateId`, invalid quantity | Quarantine/DLQ, do not retry infinitely |
| Missing dependency | Relationship references uncreated Product | Hold pending per policy or query source to recover |
| Version gap | Received event 23 before 22 | Buffer/replay 22 with expiration timeout |
| Uncertain commit state | Timeout after DB may have committed | Read receipt first, then decide |
| Permanent business error | Event violates state transition rules | Report data error, do not blindly retry |

**Bounded retries** stop a single broken message from starving an entire worker. When routing an event to a DLQ, preserve enough metadata for safe diagnosis and replay: `eventKey`, `aggregateId`, version, source details, error category, retry count, and payload subject to security policies.

Never "fix" a DLQ by arbitrarily deleting receipts or resetting versions. Replays must obey the exact same keys, constraints, and ordering rules as the primary stream.

## 13. Receipt Retention and Storage Cost

Creating an `AppliedEvent` node per applied event can grow node counts rapidly. Decide **how long to retain receipts** based on the broker's replay window and audit requirements.

For instance, purging receipts after 7 days while a backfill job replays 30-day-old events leaves the system with no record that those events already ran. For delta events, they would be applied a second time.

Options include:

- Retaining receipts across the **entire valid replay window**, including backfills.
- Relying on versioned checkpoints guarded by business logic when versions can block stale replays.
- Archiving long-term receipts in another store capable of consistent lookups by `eventKey`.
- Using clean-slate rebuild/re-import rules into a separate namespace or database without mixing with prior applied state.

Never blindly purge receipts merely because old records are rarely read. Factor node, index, and relationship overhead into capacity and retention planning.

## 14. Observability and Verification Queries in Neo4j

### 14.1. Inspecting a Stored Receipt

~~~cypher
MATCH (e:AppliedEvent {eventKey: $eventKey})
RETURN e.eventKey AS eventKey,
       e.eventId AS eventId,
       e.source AS source,
       e.payloadHash AS payloadHash,
       e.appliedAt AS appliedAt;
~~~

The returned data distinguishes true duplicates from ID collision errors. Applications should bind parameters instead of concatenating raw event strings.

### 14.2. Counting Receipts by ID

~~~cypher
MATCH (e:AppliedEvent {eventKey: $eventKey})
RETURN count(e) AS receiptCount;
~~~

With proper constraints and an existing receipt, `receiptCount = 1`; `0` means no receipt exists yet for that key in the checked database. Without a constraint, multiple duplicate receipts can appear and break deduplication.

### 14.3. Finding Order Nodes Missing a Checkpoint

~~~cypher
MATCH (o:Order)
WHERE o.lastAppliedVersion IS NULL
RETURN o.orderId AS orderId,
       o.status AS status
LIMIT 50;
~~~

This supports migration and monitoring checks. A missing version may be valid for an Order initialized outside the event stream; understand how the projection was seeded before labeling records as corrupt.

### 14.4. Tracing Events Applied to a Node

When storing `APPLIED_TO`:

~~~cypher
MATCH (e:AppliedEvent)-[:APPLIED_TO]->(p:Product {sku: $sku})
RETURN e.eventKey AS eventKey,
       e.appliedAt AS appliedAt
ORDER BY appliedAt DESC
LIMIT 20;
~~~

This query supports auditing when audit edges are retained. In very high-throughput pipelines, audit edges also increase write amplification; weigh traceability benefits against storage and graph mutation costs.

### 14.5. Operational Metrics to Monitor

| Metric | Helps Detect |
|---|---|
| Events received vs. newly applied | Abnormal drops or elevated error rates |
| Duplicate rate by source/aggregate | Excessive producer retries or broker redeliveries |
| Conflicting `eventKey` rate | Unstable upstream ID generation or corrupt data |
| Out-of-order / gap count | Ordering violations or dropped messages |
| Age of oldest pending event | An aggregate stalled waiting on a missing version |
| Retries, deadlocks, transaction timeouts | Write contention and Neo4j load issues |
| Consumer lag, DLQ depth | Backlogs of unprocessed events |
| Receipt count and index size | Retention and ledger storage growth |
| Projection drift vs. source | Logic bugs invisible to retry counts alone |

Monitor both **correctness** and **throughput**. A fast pipeline that skips missing versions causes silent long-term data corruption.

## 15. Concurrency and Failure-Recovery Testing

Run the following scenarios on an **isolated test database** sharing the exact schema/constraints of production.

| Scenario | Test Action | Expected Outcome |
|---|---|---|
| Single event delivery | E100 adds 2 units | `soldUnits` increases by 2, 1 receipt created |
| Redelivery of same `eventKey`/payload | E100 delivered a second time | No extra increment; classified as duplicate |
| Two workers handle E100 simultaneously | Compete to create same receipt | Only one mutation commits |
| Same key with altered payload | E100 adds 3 instead of 2 | Conflict detected, does not add 3 |
| Disconnect right after commit | Client receives no response | Query receipt to confirm event was applied |
| Snapshot event v23 before v22 | SHIPPED arrives before PAID | v22 does not overwrite newer state |
| Delta event v23 before v22 | Missing delta v22 | v23 held pending or v22 replayed |
| Crash after DB commit, before broker ack | Broker redelivers | Receipt blocks re-application |
| Crash before DB commit | Transaction rolls back | Retry applies cleanly once |
| Missing endpoint node | Event references unknown SKU | No fake receipt recorded; dependency handled |
| Replay after receipt expiration | Old message returns | Obeys retention/version policy; no double effect |
| Two different sources update a property | CRM/Sales hold distinct versions | Source ownership rules enforced |

### 15.1. Testing with Reconcilable Counters

In a test dataset, initialize a Product with `soldUnits = 0` and prepare 100 distinct events, each incrementing by 1. Shuffle deliveries randomly, dispatch across multiple workers, and inject retries and crashes.

If **all 100 distinct valid events commit strictly once**, the final count must be **100**, even though total broker deliveries exceed 100. Receipt count across those `eventKey`s must equal 100.

To confirm correctness, never verify only the sum: **over-counting and under-counting errors can cancel each other out**. Reconcile every `eventKey`, application count, and version invariant.

### 15.2. Avoid Touching Production Data During Tests

The constraint, receipt, and mutation examples in this lesson are **real write operations**. Execute them in an authorized test database with dedicated sample event keys and SKUs, then clean up per procedure. Never run data-mutating commands in production just to observe behavior.

## 16. Common Misconceptions

**"MERGE is enough to handle duplicate events."** `MERGE` on a node key avoids duplicate nodes, yet a trailing cumulative `SET` still adds on every delivery.

**"Broker exactly-once automatically covers Neo4j."** Broker guarantees have specific scopes; writing to Neo4j is an external side effect requiring receipts or an equivalent mechanism.

**"Any higher-version event can skip intermediate versions."** Only true in certain full-snapshot models. Cumulative deltas typically require complete history.

**"Just sort by `occurredAt`."** Distributed clocks, network latency, and multiple producers mean timestamps may not reflect business order.

**"Two transactions checking version in `WHERE` before `SET` act as atomic compare-and-swap."** You cannot assume that without understanding lock acquisition timing; design and verify concurrency guards explicitly.

**"Every uniqueness error means an event was already processed."** Another constraint may have failed, or the same `eventKey` may carry a different payload. Inspect the receipt and related data.

**"Commit the checkpoint first and update the graph second."** Crashing in between leaves a record marked processed whose update never happened.

**"Ack immediately upon receiving an event for faster safe throughput."** Acking before commit loses events if the consumer crashes.

**"Delete receipts after 24 hours regardless of replays."** If events older than the retention window can return, the system can apply them twice.

**"All duplicates should endlessly throw errors."** Confirmed duplicates are normal under at-least-once delivery. Consumers should ack them cleanly so queues do not stall.

## 17. Applied Exercises

### Exercise 1 — Preventing Double Counting

A `StockReceived` event has `eventKey = inventory:E8` and `quantity = 5`. The broker delivers it twice. The application runs:

~~~cypher
MERGE (p:Product {sku: 'P7'})
SET p.stock = coalesce(p.stock, 0) + 5;
~~~

**Question:** Why can stock increase by 10, and what must be added?

**Answer:** `MERGE` only matches/creates the Product node; both executions still run `SET` and add 5 twice. You need a stable `eventKey`, a uniqueness-constrained receipt updated in the same transaction as stock, and duplicate handling.

### Exercise 2 — Same-ID Conflict

Two messages share `eventKey = orders:E9`, but the first payload has `status = PAID` and the second has `status = CANCELLED`.

**Question:** Should the second delivery be treated as a successful duplicate?

**Answer:** No, if the payloads differ beyond agreed normalization rules. Compare hashes/business fields and investigate the ID collision.

### Exercise 3 — Version Gap

The projection has `lastAppliedVersion = 41` and receives delta version 43.

**Question:** Should it apply immediately since 43 is newer?

**Answer:** No, if each delta depends on version 42 having been applied. Hold event 43 pending and fetch/replay version 42; skip versions only when semantics and source policies explicitly permit it.

### Exercise 4 — Late Stale Snapshot

The Order projection has version 50 and status SHIPPED. The consumer receives snapshot version 49 with status PAID.

**Question:** How should this be handled?

**Answer:** Prevent the stale snapshot from overwriting version 50. Validate the event against the same source/aggregate version rules and classify it as stale or duplicate.

### Exercise 5 — Crash After Commit

The consumer commits to Neo4j but crashes before acking Kafka. Kafka redelivers the same `eventKey`.

**Question:** What should the consumer do?

**Answer:** Using the receipt/constraint, confirm the `eventKey` and payload were already applied; ack the redelivered message without re-applying the delta.

### Exercise 6 — Two Version Types

An event carries `schemaVersion = 3` and `aggregateVersion = 17`.

**Question:** Which number selects the JSON decoder, and which checks node mutation order?

**Answer:** `schemaVersion` selects the decoder; `aggregateVersion` represents the logical order of the aggregate per the source contract.

### Exercise 7 — Receipt Retention

The broker retains messages for 7 days, while a quarterly backfill job replays 90-day-old events. Receipts are retained for only 14 days.

**Question:** What is the risk?

**Answer:** The backfill can redeliver already-applied deltas whose receipts were purged. Extend retention or use an equivalent safe checkpoint/rebuild mechanism covering the backfill window.

## 18. Key Takeaways

In event-driven Neo4j integration, **idempotency** must bind to **a stably identified event or business operation**; `MERGE`ing a node does not stop double-applying cumulative updates. A practical pattern is storing a **uniqueness-constrained receipt**, creating that receipt and updating nodes/relationships/properties **within the same transaction**. If a commit succeeds before the broker receives an ack, redelivered messages can still be verified without duplicating effects.

**Event ordering** must be solved using per-aggregate versions/sequences alongside **snapshot** vs. **delta** semantics. Late arrivals, version gaps, multiple producers, retries, and replays all require explicit policies. Combining keys, constraints, Java Driver managed transactions, post-commit acks, pending/DLQ handling, retention policies, and source reconciliation keeps the graph business-accurate even when distributed systems deliver events **duplicated, delayed, or out of order**.
