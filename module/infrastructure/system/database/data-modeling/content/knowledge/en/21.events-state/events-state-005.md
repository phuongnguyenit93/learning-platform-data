# Stream Identity, Version Ordering, and Concurrent Updates

## 1. Why Are These Three Decisions the Foundation of Event Modeling?

A system can store `OrderPlaced`, `OrderPaid`, `OrderCancelled`, and `OrderShipped` events completely and still produce the wrong state if it does not know **which stream an event belongs to**, **which event came first in that stream**, and **in what order two concurrent requests are accepted**.

For example, two staff members open order `ORD-842` at the same time while the order is in `READY`:

- Staff member A submits `CancelOrder` because the customer changed their mind.
- Staff member B submits `ConfirmShipment` because the parcel was just handed over.

Both see the stale state and may believe their action is valid. If the system simply reads state and appends events without version control, it risks recording both `OrderCancelled` and `OrderShipped` in an invalid progression.

To design data properly, separate three layers:

| Question | Mechanism | Effect |
| --- | --- | --- |
| **Which entity owns the data?** | Stream identity. | Defines history boundaries and applicable invariants. |
| **Which progression has been accepted?** | Per-stream incrementing version/sequence. | Enables ordered replay and detects missing/duplicate events. |
| **Who gets to write next under contention?** | Expected version, locking, or suitable transaction. | Prevents logical overwrites and decisions based on stale state. |

These three layers tie directly to translating business rules into **aggregates, primary keys, unique constraints, indexes, and transactions**. They are especially critical for event sourcing, though many of the same principles apply to state + audit logs, document versioning, and change-synchronization models.

## 2. Stream Identity: Every Event Must Belong to the Right Business Boundary

An **event stream** is the sequence of accepted events belonging to an entity or aggregate in a deterministic logical order. A common choice for stream key is the tuple:

~~~text
stream_key = (tenant_id, aggregate_type, aggregate_id)
~~~

Examples:

~~~text
(tenant-hcm, Order, ORD-842)      -> order stream
(tenant-hcm, Payment, PAY-590)    -> payment stream
(tenant-dn,  Order, ORD-842)      -> different order, if IDs are only unique within a tenant
~~~

The identifier `ORD-842` is **not sufficient on its own** when multiple aggregate types share an ID format or multiple tenants have colliding IDs. If the entire system uses globally unique UUIDs and only one aggregate type exists, a simpler key may be valid; still, document the convention explicitly instead of leaving readers to guess from column names.

### Stream vs. Event, Command, and Correlation

| Identifier | Represents | Scope/meaning |
| --- | --- | --- |
| `stream_key` | Entity owning the event history. | Used for grouping, enforcing invariants, and replay. |
| `event_id` | **A single recorded event**. | Usually unique across the event store; used for tracing and event deduplication. |
| `stream_version` | Position of an event inside one stream. | Unique per stream; not a system-wide sequence number. |
| `command_id` / `idempotency_key` | A processing intent that may be retried. | Deduplication scope is defined per caller/tenant/operation. |
| `correlation_id` | A multi-step workflow. | May link across streams, services, and messages. |
| `causation_id` | Action/message that directly caused the event. | Aids root-cause tracing; does not define global ordering. |
| `schema_version` | Structural version of the **event type**. | Does not increment with the number of events in the stream. |

One command may produce **0, 1, or multiple events**. One event may be redelivered to many consumers. One correlation may link hundreds of events across many streams. Therefore, never arbitrarily substitute `command_id`, `event_id`, or `correlation_id` for `stream_key`.

### Choosing Aggregate Boundaries From Invariants

If the rule is “an order cannot be both cancelled and confirmed as shipped”, approving those two actions must be serialized **within the same invariant-checking boundary**. An `Order` stream may fit well.

If an order consists of multiple parcels, each with an independent shipping schedule, you may need a `Shipment` stream per parcel. In that case, do not assume an `Order` stream key automatically protects invariants across multiple `Shipment`s; design cross-stream coordination or adjust data boundaries.

**Principle:** choose aggregates and streams first from consistency rules, and only then decide tables, documents, partitions, and indexes. Organizing streams as “one stream for all events in the system” creates write hotspots and blurs business boundaries; making streams too granular forces mandatory invariants across multiple transactions.

## 3. Version Ordering: What Is Guaranteed and What Is Not?

Suppose the event store has recorded these events for `ORD-842`:

| stream_version | event_type | Meaning |
| ---: | --- | --- |
| 1 | `OrderPlaced` | Order was created. |
| 2 | `PaymentCaptured` | Payment was successfully captured. |
| 3 | `OrderPrepared` | Goods were prepared. |
| 4 | `OrderReadyForShipment` | Ready for handover. |
| 5 | `OrderCancelled` | Order was validly cancelled. |

A simple convention starts a new stream at **version 0** (no events yet); the first event carries version 1. Each appended event increments version by 1. If a valid command emits three events, it occupies three consecutive versions. Define the rule clearly and enforce it consistently across the system.

Meanings to keep separate:

- **`stream_version`:** accepted business order **within the stream**. It is the primary axis for aggregate replay and gap detection.
- **`schema_version`:** payload version number of `event_type`, e.g., `PaymentCaptured.v2`. A stream at version 87 can still hold events with schema version 1.
- **`occurred_at`:** when the occurrence happened per an authoritative source; may be earlier than a previously recorded event due to late arrival.
- **`recorded_at`:** when the event was persisted into the store; do not use in place of version for concurrency control.
- **Global offset, transaction log position, or broker offset:** position within a specific storage engine/log/partition. Does not implicitly represent commit order or causality across all streams and services.

**Never simply `ORDER BY occurred_at` to replay an aggregate.** Two events can share the same timestamp; source clocks can drift; notification of an older occurrence can be processed late. Apply order is the order committed by the event store within the stream, while business timestamps serve analytics and separate interpretation.

### Why Must Versions Have No Gaps in a Complete Stream?

If a stream contains `1, 2, 4` and lacks `3`, a projection cannot tell whether event 3 was lost, has not arrived yet, or was deleted. In systems using contiguous versions, the event store must **write version and event atomically**, never committing `current_version = 4` while version 3 is absent.

Gaps can appear in a **global sequence** generated by a database sequence due to rollbacks or distributed allocation, which does not mean an event was lost; do not apply the per-stream “no gaps” rule to every system-wide ID.

## 4. Concurrent Updates: Lost Updates at the Business Level

Suppose an order stream is at version 4, status `READY`. Two commands arrive almost simultaneously:

~~~text
T0: Order ORD-842 is at version 4, status=READY

A reads version 4                 B reads version 4
A validates CancelOrder           B validates ConfirmShipment
A tries to append OrderCancelled  B tries to append OrderShipped
~~~

If both append based on their stale reads without a version check on write, the system could:

- Write two events with the same `stream_version = 5`, making replay ambiguous.
- Auto-number them 5 and 6 while still treating both commands as valid against version 4 state; the resulting history violates business rules.
- Persist events while a projection only partially applies them, causing state to diverge from log truth.

**Optimistic concurrency control (OCC)** resolves contention using **expected version**: the command declares “I made this decision based on stream version 4”. The append succeeds only if the current version is still 4 at the **moment checked atomically with the write**.

A valid progression:

| Step | A: CancelOrder | B: ConfirmShipment |
| --- | --- | --- |
| Initial read | Based on version 4 | Based on version 4 |
| Append | Succeeds: writes `OrderCancelled` version 5 | Fails: expected 4, actual 5 |
| Next step | Returns cancelled outcome | Reloads state at version 5, re-evaluates conditions; in this example must reject shipment |
| History | Contiguous versions 1 to 5 | No rule-violating `OrderShipped` event added |

If B wins the append first and rules forbid cancellation after handover, A is rejected in the reverse scenario. The system does not guarantee a specific actor wins; it guarantees **each command is accepted only against the latest state at the serialization point**.

### Expected Version Differs From Idempotency

Two **different** commands sharing the same expected version require concurrency control. One **identical retried** command requires recognizing that the request was already processed. If a client times out right after a successful commit and retries, the stream version has already advanced, and merely returning “version conflict” leaves the client unsure whether its original request succeeded. Store an idempotency receipt or a unique business key that can be reconciled.

## 5. PostgreSQL Schema: Stream Locking and Non-Duplicate Version Constraints

One way to implement event sourcing in PostgreSQL uses **two tables**: one tracking each stream's current position and one storing events. Here, a tenant can have multiple aggregate types; the primary key spans all three components.

~~~sql
CREATE TABLE event_stream (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0),
    PRIMARY KEY (tenant_id, aggregate_type, aggregate_id)
);

CREATE TABLE domain_event (
    event_id         UUID PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    stream_version   BIGINT NOT NULL CHECK (stream_version > 0),
    event_type       VARCHAR(100) NOT NULL,
    schema_version   SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at      TIMESTAMPTZ NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    command_id       UUID,
    correlation_id   UUID,
    causation_id     UUID,
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream
        (tenant_id, aggregate_type, aggregate_id),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, stream_version)
);

CREATE INDEX ix_domain_event_type_time
    ON domain_event (event_type, occurred_at);
~~~

What is guaranteed and what is not:

- **Primary key on `event_stream`:** no two rows manage the same stream.
- **`UNIQUE(tenant_id, aggregate_type, aggregate_id, stream_version)`:** no two committed events occupy the same position in a stream. This constraint creates an index suitable for reading a stream in version order.
- **`PRIMARY KEY(event_id)`:** distinguishes individual events; this identifier does not replace uniqueness on stream + version.
- **`FOREIGN KEY`:** every event must reference an existing stream.
- **`CHECK(jsonb_typeof(payload) = 'object')`:** checks only payload shape; does not validate field types and constraints for `OrderCancelled` or `PaymentCaptured`.
- **Consistency between `current_version` and the event sequence:** requires a **transactional workflow** to protect; merely declaring a counter column does not force every writer to append matching events.
- **Secondary index on type/time:** useful only when actually querying by `event_type` and time range. Verify workload before adding indexes to avoid extra write cost.

Appending should be funneled through a controlled service/repository or procedure with proper write privileges. If multiple components can `UPDATE event_stream` independently of `INSERT domain_event`, the `current_version` invariant can still break. Add access controls, triggers, or write-layer constraint checks as reliability demands.

### Example: Reading a Stream in Exact Order

~~~sql
SELECT stream_version, event_id, event_type,
       schema_version, occurred_at, payload
FROM domain_event
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Order'
  AND aggregate_id = :order_id
ORDER BY stream_version;
~~~

The illustrative statement uses `:tenant_id` and `:order_id` parameters passed by the application; executing directly in a SQL client requires appropriate parameter-binding syntax.

## 6. Conditional Append Inside a Transaction

The easiest pattern to reason about is locking the **stream row** inside a transaction, loading the latest state, validating the command, and writing the event alongside the next version.

~~~text
BEGIN;

-- If the stream is new, create the version=0 row using an operation
-- protected by PRIMARY KEY and aggregate initialization rules.
INSERT INTO event_stream (
    tenant_id, aggregate_type, aggregate_id, current_version
)
VALUES (:tenant_id, 'Order', :order_id, 0)
ON CONFLICT DO NOTHING;

-- Lock the target stream; concurrent writers to the same stream wait.
SELECT current_version
FROM event_stream
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Order'
  AND aggregate_id = :order_id
FOR UPDATE;

-- Application verifies current_version == expected_version,
-- loads valid events/snapshot, and evaluates business rules.
-- If invalid: ROLLBACK, append no event.

-- Assuming current_version = :expected_version:
INSERT INTO domain_event (
    event_id, tenant_id, aggregate_type, aggregate_id,
    stream_version, event_type, schema_version, occurred_at, payload
)
VALUES (
    :event_id, :tenant_id, 'Order', :order_id,
    :expected_version + 1, 'OrderCancelled', 1, :occurred_at, :payload
);

UPDATE event_stream
SET current_version = :expected_version + 1
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Order'
  AND aggregate_id = :order_id;

COMMIT;
~~~

This is **illustrative SQL combined with application steps**, not a standalone script runnable without variables and validation logic. Key points:

1. **Lock before making the final decision.** Reading state outside a transaction, waiting for a lock, and failing to re-check is how decisions get made on stale data.
2. Compare expected version against the **locked** version. If they differ, abort or reload state and re-evaluate the command.
3. `INSERT domain_event` and `UPDATE event_stream` must be in the same transaction; failure in either rolls back the entire unit.
4. For commands producing multiple events, allocate a **contiguous range** `expected + 1` through `expected + N`, then set `current_version = expected + N` in the same transaction.
5. For a new stream, only a valid initialization command may create initial history; `INSERT ... ON CONFLICT DO NOTHING` does not replace business validation. Two competing initialization commands still require version or state conflict handling.

A **compare-and-swap** variant:

~~~sql
UPDATE event_stream
SET current_version = current_version + 1
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Order'
  AND aggregate_id = :order_id
  AND current_version = :expected_version
RETURNING current_version;
~~~

If no row is returned, either the version changed or the stream does not exist. If exactly one row returns, the application receives the new version to insert the event **within the same transaction**; if the insert fails, roll back so the counter does not advance alone. Checking invariants against the latest state remains mandatory. Never conclude a command is valid solely because the `UPDATE` succeeded.

### Pessimistic Locking or OCC?

| Approach | Advantages | Trade-offs |
| --- | --- | --- |
| **`SELECT ... FOR UPDATE`** | Serializes operations on a stream inside the DB; easy to reason about the state-check point. | Writers block on the lock; “hot” streams cause contention, so transactions must stay short. |
| **OCC via expected version** | Allows computing before writing; makes conflicts explicit. | Under high contention can cause frequent retries; must re-validate invariants on fresh state. |
| **Serializable transactions** | Can protect complex multi-row rules when properly designed. | Can hit serialization failures requiring full transaction retry; does not replace idempotency. |

Even with pessimistic locking, **expected version** remains useful when commands originate from UIs displaying older state: the system can inform the user that the order changed rather than silently applying the request against an unseen version.

## 7. Idempotency When Commands Are Retried

Concurrent updates and duplicate submissions are distinct scenarios. On real networks, a client may time out after an event already committed and automatically resend the same request. Without idempotency, the second request could create a second event or fail with a version mismatch even though the first succeeded.

A practical design keeps a **command receipt** scoped to request identity:

~~~sql
CREATE TABLE command_receipt (
    tenant_id        UUID NOT NULL,
    caller_id        VARCHAR(100) NOT NULL,
    idempotency_key  VARCHAR(160) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    result           JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, caller_id, idempotency_key)
);
~~~

Processing flow:

1. Look up the receipt by the scoped key. If present and `request_hash` matches, return the committed result; if the key matches but payload differs, return a conflict error.
2. If absent, process the command and check the version. Save events, `current_version`, and the receipt **in the same transaction**, ensuring all commit or none commit.
3. Two concurrent requests with the same key must be coordinated via the `PRIMARY KEY` constraint, locking, or equivalent ownership acquisition. After the winning transaction commits, the losing request reads the receipt and returns the original outcome; if the winning transaction rolls back, processing can proceed.
4. If a command emits multiple events, the receipt binds to **one command** rather than forcing `command_id` to be unique per event row. IDs and the version range of created events can be stored inside `result`.

`request_hash` must be computed from a canonical representation of meaningful payload content (and operation scope) so the same key is never misused for two different commands. Receipt retention windows should align with real retry windows and business requirements; for financial transactions, an independent business uniqueness key may also be required.

**Consumer-side deduplication is a separate concern:** brokers may deliver messages multiple times. Consumers must use `event_id` or `stream_key + stream_version` to prevent double-crediting balances, double-counting attempts, or sending duplicate notifications even when the originating command was written once.

## 8. Reading, Replay, and Projections When Events Arrive Late or Out of Order

The state reconstruction function for a stream should be **deterministic**:

~~~text
state = initial_state
for event in load_events(stream_key, order_by=stream_version):
    state = apply(state, upcast_if_needed(event))
return state
~~~

`apply` must not call external APIs, read current wall-clock time, send notifications, or query live fee schedules to make new decisions. If a value affects state, the event or an immutable versioned reference must allow reproducing the exact same outcome.

A projector tracking `last_applied_version` can follow these rules:

~~~text
incoming_version <= last_applied_version:
    ignore already-applied event or verify consistency

incoming_version == last_applied_version + 1:
    apply event
    update state and last_applied_version in the same transaction

incoming_version > last_applied_version + 1:
    one or more versions missing
    pause this stream and fetch missing events
~~~

Even though the event store persists sequentially, **message transport** can arrive late, duplicated, or out of order due to partitioning, network glitches, and retries. Never rely solely on message arrival order. Nor treat an event with an older `occurred_at` as an older version: `occurred_at` and `stream_version` answer two different questions.

Example read-model table:

~~~sql
CREATE TABLE order_current (
    tenant_id            UUID NOT NULL,
    order_id             VARCHAR(100) NOT NULL,
    order_status         VARCHAR(30) NOT NULL,
    last_applied_version BIGINT NOT NULL DEFAULT 0
                         CHECK (last_applied_version >= 0),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);
~~~

When processing `version = 6`, updating `order_status` and advancing `last_applied_version` to 6 must commit atomically. If a projector crashes after updating state but before persisting the checkpoint, the same message could be reapplied and corrupt non-idempotent accumulations. Consumer storage needs constraints or transactions guarding against that case.

### Snapshots Are Optimization Checkpoints, Not Replacement Sources of Truth

If a stream has tens of thousands of events, a snapshot at version `N` enables replaying from `N + 1`. A snapshot must record `stream_key`, `stream_version`, snapshot schema version, and be built from a consistent event sequence. When a command needs latest state, stale snapshots must be caught up with all subsequent events. Corrupted snapshots can be deleted and rebuilt from the event store—a guarantee that breaks if historical events cannot be replayed.

## 9. Consistency Boundaries: One Stream Does Not Solve Every Conflict

Locking `Order` protects rules belonging to one order. However, some invariants span beyond a single stream:

- **Inventory:** two different orders both reserve the last remaining item. Locking each `Order` separately does not protect total `available_stock`; a consistency point for `InventoryItem`, reservation, or source constraint is required.
- **Event seating:** two different bookings must not claim the same seat. A lock/unique constraint on `event_id + seat_id` or a seat-allocation aggregate is needed; per-`Booking` version alone is insufficient.
- **Wallet balance:** two debit commands from two operations must not push the balance negative. A `Wallet` ledger/aggregate or appropriate transaction control on the same source may be required.
- **Multi-service workflows:** confirmed payment without warehouse confirmation must not be interpreted as a fully completed order. Distinct meaningful events per source, orchestration, and compensation where needed are required.

Never replace cross-stream invariants with “the broker delivers in order”. Message ordering does not turn updates across two databases into an atomic transaction. For multi-row local transactions, use locks, unique constraints, and suitable isolation levels; for distributed services, use stateful workflows, idempotency, and reconciliation.

### Hot Streams and Write Bottlenecks

A stream receiving high command rates per second (such as “one stream for all users”) creates heavy contention because all writers must serialize. Before splitting a stream, re-examine invariants: can you shard by account, order, instrument, or inventory location? When splitting, define the consistency policy for cross-boundary rules. Never split merely for throughput if doing so breaks business invariant protection.

## 10. Physical Design and Operations by Query Characteristics

Choosing a database engine does not change the semantics of stream identity and version; it changes how constraints are implemented:

| Storage model | Representation | What to verify |
| --- | --- | --- |
| **Relational** | Event table + stream/version locks + transactions; separate read-model tables. | Unique constraints, locks, transactions, indexes, partitioning, and replay plans. |
| **Document** | Aggregate document holding version and event array, or events as separate documents. | Document size limits, atomic conditional updates, distributed ordering, indexing. |
| **Graph** | Causal links and entity/event relationships as nodes/edges. | Usually an analytical view for relationship exploration; needs separate source-of-truth and commit rules. |
| **Analytical store** | Cleansed event tables, time-series columns, and partition keys. | Ingestion lag, late-arriving data, deduplication, and metric definitions. |

In PostgreSQL, `UNIQUE(tenant_id, aggregate_type, aggregate_id, stream_version)` simultaneously supports stream lookups and ordering. Add indexes only when queries justify them: too many indexes slow down every append. If partitioning the event store by time or tenant, check how **global uniqueness** is enforced under the DBMS's partitioning rules; partitioned tables may require unique indexes to include the partition key, affecting `event_id`/version constraints. Never treat adding partitioning as a purely performance-only change.

Operational observability metrics should include: version conflict rate, lock-wait latency, command retry counts, idempotency hit rate, projection lag per stream/partition, missing-event gaps detected by consumers, replay duration, and mismatch rates between projections and canonical replays.

### Access Control and Data Protection

Event logs typically retain long-term history. Putting `tenant_id` in keys and filters does not guarantee tenant isolation if application queries can omit the filter. Enforce authorization at both application and database layers; for strict isolation requirements, use row-level security or physical separation.

Minimize personal data in payloads; consider referencing a separate PII store managing erasure/anonymization and storing only facts needed for replay. The append-only principle does not override retention limits, lawful rectification/erasure rights, or security policies.

## 11. Common Implementation Mistakes

| Mistake | Failure scenario | Fix |
| --- | --- | --- |
| Using timestamps as versions | Two events share the same timestamp or arrive late. | Dedicated logical sequence per stream. |
| Using `MAX(stream_version)+1` outside a transaction | Two writers read the same max version concurrently. | Stream locking or expected-version CAS inside a transaction. |
| Enforcing unique version while validating commands against stale state | A command is forced onto a later version even though rules no longer hold. | Reload state and re-evaluate invariants on conflict. |
| Using `event_id` instead of a command idempotency key | Retries generate new event IDs and record the same action again. | Command-level deduplication receipts/business keys. |
| Using `schema_version` as `stream_version` | Cannot determine event order. | Schema version and stream version are two separate columns. |
| Updating `current_version` outside the append transaction | Counter points to a nonexistent event. | Write both counter and event atomically. |
| Trusting broker delivery order blindly | Consumer receives version 8 before version 7. | Per-stream checkpoints, gap detection, and missing-event fetch. |
| Checking write-time invariants against an async read model | Projection lag causes accepting stale preconditions. | Validate against the source of truth at a valid serialization point. |
| Locking only individual orders to protect shared stock | Two orders reserve the same last unit. | Inventory/reservation boundary and shared constraint. |
| Applying side effects on every retry | Notifications or refunds execute twice. | Outbox, idempotent consumers, and provider business keys. |

## 12. Exercise: From Ticketing Requirements to Keys and Transactions

**Scenario:** an event ticketing platform has 200 seats. Users can hold seats, pay, cancel, and switch seats. Two devices belonging to the same customer can send hold commands concurrently; the payment service can send duplicate callbacks. The system must inspect every change in a booking's history and prevent two users from holding the same seat.

Complete the following:

1. **Stream identity:** propose `stream_key` designs for `Booking` and `SeatInventory` (or an alternative model). State which fields require `tenant_id`, `event_id`, `booking_id`, and `seat_id`.
2. **Versioning:** write a 5-event progression for a booking starting at version 1; distinguish `stream_version` from `schema_version`.
3. **Concurrency:** two `ReserveSeat` commands both rely on version 8 of the same inventory/seat. Describe expected outcomes when one succeeds and the other conflicts.
4. **Constraints:** design a lock/unique constraint so the same seat cannot be held by two active bookings simultaneously. Explain why a naive unique constraint solely on `seat_id` blocks re-reserving a seat after cancellation; propose a current-reservations table or suitable rule.
5. **Idempotency:** when a payment callback resends the same `provider_payment_id`, prove history records only one confirmed capture; describe how to handle two simultaneous callbacks.
6. **Projections:** define a read-model structure for the booking UI and the rule using `last_applied_version` when version 11 arrives before version 10.
7. **Boundaries:** identify which invariants live inside one stream and which require another consistency boundary or cross-service coordination.

**Verification criteria:**

- Each stream has contiguous versions with no two committed events sharing a version.
- Two competing commands cannot both be accepted based on stale state.
- Retried commands never create duplicate business events or monetary charges.
- Version-ordered replay is deterministic; projections detect duplicates and gaps.
- Seat/inventory checks cannot “leak” because locks only guard per-booking state.
- Physical schema accurately expresses key scope and supports real queries.

**Design conclusion:** `stream_key` tells you which entity owns the history; `stream_version` tells you the order of accepted changes; transactions with expected-version/locking ensure only one process appends the next valid step. These three mechanisms are reliable only when paired with **business invariants, idempotency, and consistency boundaries** defined clearly from the initial requirements.
