# Event Sourcing: Replay, Snapshots, and Applicability

In many systems, databases store only the current state of an object: what status an order is in, how much balance an account holds, or until when a piece of equipment is held. This approach is efficient for current-state queries, but it does not by itself fully explain how state changed or which decisions produced the result unless history is recorded separately.

**Event sourcing** is a way of organizing data where business changes are stored as an ordered sequence of immutable events. Current state is derived by applying those events. As a result, the system can reconstruct state at a point in time, inspect history, build new projections, or fix read-data calculations by replaying events. In return, the design must handle ordering, versions, compatibility, snapshots, storage volume, privacy, and side effects during replay.

This lesson belongs to the **Consistency** chapter of the **Cloud Architecture** track. The content focuses on event stores, aggregates, replay, snapshots, and applicability in cloud systems. Decisions must balance business correctness, reliability, security, performance, cost, and operability.

After this lesson, you will be able to:

- Distinguish event sourcing, event-driven architecture, audit logs, and CRUD state storage.
- Model aggregates with ordered, versioned event streams.
- Design appends, concurrency control, idempotency, and event schemas.
- Reconstruct state via replay and build snapshots to reduce recovery time.
- Build or rebuild read projections without repeating side effects.
- Handle event schema evolution, sensitive data, retention, and migrations.
- Evaluate operational costs and risks to determine when event sourcing fits.

## 1. What is event sourcing?

In traditional CRUD models, a mutating operation directly updates the current record. For example, the pre-transaction balance is 1,000,000 VND, the customer pays 250,000 VND, and the system updates the balance to 750,000 VND. If only the final state is stored, current data does not self-explain which transactions took place.

In event sourcing, the system records events describing changes:

- `AccountOpened`
- `MoneyDeposited`
- `PaymentDebited`

Current state is constructed by applying events sequentially from the start of the stream. An event is not a SQL statement or a full row copy; it describes **a business fact that occurred**.

### 1.1. Event stream example

~~~text
Aggregate: Account-42

Version 1: AccountOpened(initialBalance = 1,000,000 VND)
Version 2: MoneyDeposited(amount = 100,000 VND)
Version 3: PaymentDebited(amount = 250,000 VND)

State after version 3:
  balance = 850,000 VND
~~~

From this stream, state can be reconstructed at version 1, 2, or 3. An event stream does not automatically guarantee correct arithmetic; event-application logic and invariants must be designed, tested, and version-managed.

~~~mermaid
flowchart LR
    C["Command"] --> D["Domain logic"]
    D --> E["Append event"]
    E --> S[("Event store")]
    S --> R["Replay / projection processor"]
    R --> ST["Current state / read model"]
    ST --> Q["Query API"]
~~~

Commands ask the system to perform an action. Domain logic validates business conditions and appends events if valid. The event store persists history; projection processors apply events to build read models. **Event sourcing does not mean every read must replay the entire stream**; systems typically use projections or snapshots for efficient querying and loading.

## 2. Distinguishing event sourcing from related concepts

| Concept | What is stored or organized | Purpose |
| --- | --- | --- |
| CRUD state storage | Current state of an entity/row | Reading and updating current state |
| Audit log | Trail of who did what, when, with metadata | Auditing and investigation |
| Event sourcing | Sequence of business events as primary data source | Reconstructing state and change history |
| Event-driven architecture | Components communicating or reacting via events/messages | Reducing coupling and async processing |
| Transaction log / WAL | Changes recorded at the database engine level | DB recovery, replication, and durability |
| Change Data Capture (CDC) | Extracting changes from database logs/tables | Syncing data to other systems |

A system can use event-driven architecture while still storing state with CRUD. For instance, an application updates a `Booking` table and then emits `BookingUpdated` via an outbox. That is event-driven integration, not yet event sourcing if the `Booking` table is the source of truth and the event is merely an integration message.

Conversely, an event-sourced aggregate stores the event stream as its state source and may emit domain/integration events to other consumers.

### 2.1. Audit logs do not replace an event store

Audit logs usually record actor, IP, timestamp, and action; they do not necessarily hold enough information to reconstruct state. Event sourcing requires events with business semantics and sufficient data to execute state transitions.

Do not take text logs or access logs and call them an event store. Observability logs typically lack stable contracts, per-aggregate ordering, or required durability.

## 3. Aggregates and event streams

In Domain-Driven Design, an **aggregate** is a business consistency boundary. The aggregate root controls changes that must protect shared invariants. In event sourcing, each aggregate typically has its own stream with a stable identifier and monotonically increasing versions.

Examples:

- `Booking-1005` has its own stream for creation, hold, confirmation, and cancellation.
- `Account-42` has its own stream for deposits and debits.
- `Asset-21` has its own stream for equipment status and maintenance.

An event stream typically carries metadata:

| Field | Meaning |
| --- | --- |
| Aggregate ID | Identifier of the object or aggregate |
| Stream version | Position/version of the event in the stream |
| Event type | Type of business event |
| Payload | Data needed to apply the event |
| Event ID | Unique ID of the event |
| Occurred time | Business timestamp when it occurred |
| Recorded time | Timestamp when the event store persisted it |
| Correlation / causation ID | Links to the triggering request or causing event |
| Schema version | Version of the event structure |

An event store usually needs to support appending with an expected version or an equivalent concurrency mechanism to avoid overwriting concurrent logic.

### 3.1. Events represent facts that already happened

Event names should use past tense or signify completed facts: `BookingCreated`, `ReservationConfirmed`, `PaymentAuthorized`, `BookingCancelled`. Names like `CreateBooking` or `AuthorizePayment` are typically commands—requests to perform an action.

Payloads should describe meaningful changes, such as `PaymentAuthorized` with `amount`, `currency`, and `providerReference`, rather than a generic `BookingChanged` event carrying an opaque JSON blob.

## 4. Commands, business decisions, and appending events

Event sourcing does not skip command handling. When a command arrives, the aggregate reconstructs current state, checks invariants, and decides which events may be appended.

Example `CancelBooking` command:

1. Load stream `Booking-1005`.
2. Reconstruct current state from snapshot plus any newer events.
3. Verify the booking is in a cancellable state.
4. Check cancellation deadlines and caller permissions.
5. If valid, append `BookingCancelled`.
6. If invalid, return a business rejection; append no state-changing event.

~~~text
handle(CancelBooking(command)):
    state = loadAggregate(command.bookingId)

    if state.status is not CONFIRMED:
        reject("Booking cannot be cancelled")

    if now > state.cancellationDeadline:
        reject("Cancellation window expired")

    append(
        expectedVersion = state.version,
        event = BookingCancelled(
            bookingId = state.id,
            reason = command.reason
        )
    )
~~~

This is illustrative pseudocode. Real implementations must authenticate permissions, handle duplicate commands, and coordinate appending events with integration notifications per transactional design.

### 4.1. Invariants at the right boundary

If an invariant belongs to an aggregate, every command mutating that aggregate must be checked at that boundary. For instance, a cancelled booking must not be confirmed. Checking only at the API gateway or UI is insufficient because multiple clients, jobs, and consumers may invoke the domain.

If an invariant spans multiple aggregates or bounded contexts, a single event-store transaction may not solve it. You need a workflow/process manager, reservations, Sagas, or another coordination mechanism.

## 5. Event store: storage requirements

An event store persists streams and supports reading/appending with required semantics. You can use a purpose-built event store product or build carefully on top of a database/log. Having an `events` table alone does not automatically make a proper event store.

Properties to evaluate:

- **Append durability:** whether acknowledged events survive failures per commitment.
- **Per-stream ordering:** events within the same stream have a deterministic order.
- **Optimistic concurrency:** appends succeed only if the expected version still matches.
- **Read by stream:** loading events by aggregate ID and position/version.
- **Global subscription / catch-up:** reading new events to build projections if the architecture requires it.
- **Idempotent append or dedup:** handling client retries after timeouts.
- **Retention / archival:** retaining events per business/legal policies.
- **Backup / restore:** restoring the store and syncing checkpoints.
- **Security:** encryption, access control, auditing, and tenant isolation.

### 5.1. Example event table structure

~~~sql
CREATE TABLE event_stream (
    stream_id       VARCHAR(200) NOT NULL,
    version         BIGINT NOT NULL,
    event_id        VARCHAR(100) NOT NULL,
    event_type      VARCHAR(200) NOT NULL,
    schema_version  INTEGER NOT NULL,
    occurred_at     TIMESTAMP NOT NULL,
    recorded_at     TIMESTAMP NOT NULL,
    correlation_id  VARCHAR(100),
    payload         JSON NOT NULL,
    PRIMARY KEY (stream_id, version),
    UNIQUE (event_id)
);
~~~

This is a simplified schema for teaching purposes. Production databases may use partitioning, binary payloads, metadata columns, extra indexes, and different storage layouts. A relational table must also ensure proper append concurrency, indexing, transactions, and read performance.

## 6. Optimistic concurrency and concurrent writes

Suppose two requests both load `Booking-1005` at version 12. Request A confirms the booking; request B cancels it. If both append without checking versions, the stream could hold two contradictory events derived from the same old state.

**Expected version** allows a request to append only if the stream is still at the expected version.

~~~mermaid
sequenceDiagram
    participant A as Command A
    participant B as Command B
    participant S as Event Store

    A->>S: Load stream version 12
    B->>S: Load stream version 12
    A->>S: Append event, expectedVersion=12
    S-->>A: Success, new version 13
    B->>S: Append event, expectedVersion=12
    S-->>B: Conflict: actual version 13
    B->>B: Reload state and re-evaluate decision
~~~

On conflict, do not automatically re-append the old event. The command handler must reload the new state and re-evaluate preconditions; the operation may no longer be valid.

### 6.1. Scope of concurrency control

Stream versions protect writes to the same stream. They do not automatically protect cross-aggregate invariants, such as two bookings competing for the same asset when each booking has a separate stream. You need an aggregate/stream owning the reservation, unique constraints, or an appropriate coordination mechanism.

### 6.2. Idempotent commands and append retries

A client may time out after the event store committed but before receiving the response. On command retry, the system must know whether the request was already processed. Use a command ID / idempotency key and store command outcomes. Event IDs must also be unique.

Event deduplication is not the same as command deduplication: one command can validly emit multiple events, whereas retrying the same command should not recreate side effects.

## 7. Reconstructing state via replay

Replay is the process of reading events in order and applying them to an initial state.

~~~text
v1 AccountOpened(openingBalance=1,000,000)
v2 MoneyDeposited(amount=200,000)
v3 PaymentDebited(amount=350,000)
v4 MoneyDeposited(amount=50,000)
~~~

A reducer can apply:

~~~text
apply(state, AccountOpened):
    state.balance = openingBalance

apply(state, MoneyDeposited):
    state.balance += amount

apply(state, PaymentDebited):
    state.balance -= amount
~~~

After version 4:

\[
1,000,000 + 200,000 - 350,000 + 50,000 = 900,000\ \text{VND}
\]

A good reducer should be deterministic: the same initial state and same versioned event sequence must yield the exact same result. Avoid calling external APIs, reading current wall-clock time, or relying on environment-dependent configuration inside state-apply functions.

### 7.1. Replay differs from re-running commands

- A **Command** is a request that can be rejected, depending on permissions, current state, and business rules.
- **Replay** applies decisions already recorded in events to reconstruct state or projections.

Never replay by resubmitting every original command as if users were requesting them anew. Doing so could recalculate prices, re-trigger payments, or apply today's rules differently from historical decisions.

### 7.2. Determinism and external facts

Reducers should not recompute facts already decided externally if events can store those decided outcomes. For example, `RentalPriceQuoted` should record the finalized price and currency if history needs to reconstruct exact pricing at that time, rather than querying today's price table during replay.

If an event handler depends on exchange rates, tax rules, or holiday calendars, store the applied result or reference a reproducible policy version.

## 8. What is replay used for?

| Purpose | Input | Output | Notes |
| --- | --- | --- | --- |
| Reconstruct aggregate | Aggregate stream | Current state | Preserve order and event semantics |
| Build read projection | Events from checkpoint or stream start | New read table | Idempotent consumer, track checkpoints |
| Fix projection bugs | Replay into new projection version | Corrected read model | Do not overwrite serving projection before validation |
| Rebuild reports | Business events | Datasets / analytics | Data policies and metrics must be versioned |
| Investigation / audit | Event streams and metadata | Decision history | Enforce access controls |
| Consumer migration | Historical events into new schema/read model | New projection | Check compatibility and replay progress |

### 8.1. Do not replay side effects

If a projection consumer sends emails, calls payment providers, or sends SMS, replaying can repeat external effects. Separate:

- **State projector:** updates only read models that can be deleted and rebuilt.
- **Integration side-effect handler:** performs external actions, requires idempotency, and does not run automatically during projection rebuilds.
- **Operational replay:** an approved procedure with explicit mode, target, checkpoint, and bounds.

Separate projection builders from integration handlers. Never have one consumer both update read models and send emails if independent replay is needed.

## 9. What is a snapshot?

When a stream contains millions of events, reconstructing an aggregate by replaying from the first event on every command can be too slow. A **snapshot** stores a state representation at a specific version to reduce the number of events that must be read.

~~~text
Event stream:
v1 ... v5000

Snapshot:
  aggregateId = Booking-1005
  atVersion   = 4800
  state       = { status: CONFIRMED, ... }

Load current state:
  load snapshot at version 4800
  apply events v4801 ... v5000
~~~

A snapshot is **data derived from the event stream**, not a source of truth replacing events. If a snapshot is lost or corrupted, the system must be able to rebuild from the event stream or a valid backup.

~~~mermaid
flowchart LR
    ES[("Event stream v1...vN")] --> RP["Replay events"]
    RP --> SNAP["Snapshot at version K"]
    SNAP --> LOAD["Load snapshot K"]
    ES --> TAIL["Read events K+1...N"]
    LOAD --> REDUCE["Apply tail events"]
    TAIL --> REDUCE
    REDUCE --> STATE["Current aggregate state"]
~~~

### 9.1. Snapshot cadence

You do not need to snapshot after every event. You can create snapshots based on new event count, elapsed time, stream size, measured replay cost, or meaningful business checkpoints.

Snapshotting too frequently increases writes and storage; snapshotting too rarely increases load latency. Measure p95 load time, event counts, snapshot build cost, state size, and command frequency.

### 9.2. Snapshots must include metadata

At minimum, include aggregate ID, stream version, snapshot schema/version, timestamp, state payload, and optionally a checksum/format version. On load, verify the snapshot belongs to the right stream and its version does not exceed the stream version. If a snapshot is unreadable or uses an unsupported schema, fall back to an older snapshot or full replay per policy.

A snapshot at version K must represent state **after applying up through event K**; thereafter apply only events K+1 onward.

## 10. Snapshots differ from projection checkpoints

Snapshots accelerate loading **aggregate state**. Projection checkpoints record a consumer's processed position in an event stream or log. Both may carry versions/offsets, yet they serve different purposes.

| Aspect | Aggregate snapshot | Projection checkpoint |
| --- | --- | --- |
| Purpose | Reduce events replayed to load an aggregate | Resume a consumer from its processed position |
| What is stored? | Aggregate state at a stream version | Processed offset / version / position |
| Used by | Command handler / aggregate loader | Projection consumer |
| Deletable? | Can be rebuilt from stream | Projection or checkpoint can be rebuilt safely |
| What to protect | Snapshot/schema/state integrity | Checkpoint never advances past committed data |

If a consumer updates a projection table yet persists its checkpoint before committing the transaction, a crash can skip uncommitted data. Updating the projection and checkpoint must be atomic or backed by detection and recovery mechanisms.

## 11. CQRS and read projections

Event streams are optimized for appending history and reconstructing aggregates, not necessarily for queries like finding all bookings for a customer or counting bookings by status. Systems typically build **read projections** from events.

- Write model validates commands and appends events.
- Projection consumers read events and update read databases.
- Query APIs read from read models tailored to UI screens.
- Projections can be eventually consistent and require lag monitoring.

~~~mermaid
flowchart TB
    CMD["Commands"] --> AGG["Aggregate / domain logic"]
    AGG --> ES[("Event store")]
    ES --> SUB["Event subscriptions"]
    SUB --> P1["Booking list projection"]
    SUB --> P2["Customer history projection"]
    SUB --> P3["Analytics projection"]
    P1 --> R1[("Query DB A")]
    P2 --> R2[("Query DB B")]
    P3 --> R3[("Warehouse")]
    API["Query API"] --> R1
    API --> R2
~~~

Read projections can be dropped and rebuilt from the stream if projector logic stays compatible and all required events remain retained. Never let users edit read models directly; business changes must flow through commands and the write model.

### 11.1. Projections can lag

After the event store appends an event but before the consumer processes it, queries can still return stale state. APIs can return projection version/`lastUpdated` or provide read-your-writes by waiting briefly for the checkpoint to reach the required version.

Do not assume transactions across the event store and all read DBs are atomic. If a command requires immediate read-model visibility, define an explicit consistency contract.

## 12. Event sourcing and transactional outbox

The event store is the source of state in event sourcing. If the system must publish events to external brokers/consumers, ensure event persistence and publication notifications do not diverge.

In CRUD architectures using relational DBs, a transactional outbox writes business changes and outbox records in the same transaction. In event sourcing, the event store may provide a reliable subscription/change feed, or an adapter tracks streams and checkpoints. The goal is avoiding silent gaps where an event committed yet the integration event vanished without detection.

### 12.1. Domain events and integration events

- **Domain event:** serves internal domain modeling and may contain domain-specific details.
- **Integration event:** a contract published outside the bounded context, requiring stability, versioning, and minimization of sensitive data.

Do not broadcast raw internal payloads to every consumer. An integration adapter can map and filter domain events into public contracts.

## 13. Event schema evolution

Event stores retain long-term history, so event schemas outlive individual application deployments. Renaming fields, changing types, or altering semantics can break historical event replay.

Strategies:

1. **Additive changes:** add optional fields with sensible defaults.
2. **Upcasting:** transform old-version events into new representations on read without necessarily rewriting historical records.
3. **Versioned event types:** introduce a new type/version when semantics change significantly.
4. **Transformation / rewrite:** perform only with justification, integrity checks, backups, and full audits.

~~~text
v1 BookingCreated:
    bookingId, customerId

v2 BookingCreated:
    bookingId, customerId, currency

Upcaster:
    if event schema is v1:
        currency = default determined by historical policy
        return v2 representation
~~~

Defaults for historical events must have a sound basis. If `currency` cannot be inferred safely, do not invent arbitrary values; use versioned reference data or preserve v1 semantics in the reducer.

### 13.1. Avoid applying current configuration to history

Replaying last year's events with today's tax rates or pricing policies can yield different outcomes from the original decisions. Events should capture finalized values or reference reproducible policy versions. For sensitive data, avoid storing excessive personal information permanently in payloads.

## 14. Sensitive data, privacy, and retention

Event sourcing creates high-value history, yet makes editing/deleting data harder. If append-only events are retained long-term, personal-data deletion requests can conflict with payloads containing identifying information.

Design upfront for:

- **Data minimization:** events store only data needed to preserve business meaning.
- **References instead of payloads:** store reference IDs pointing to mutable/deletable profiles when suitable; the trade-off is that replay requires versioned reference data or snapshots.
- **Encryption / tokenization:** encrypt or tokenize sensitive fields with clear key lifecycles.
- **Separate PII store:** isolate identifying data from the event stream to handle erasure rights properly.
- **Retention policies:** classify events by retention obligation and purpose; do not retain indefinitely by default.
- **Access control / audit:** read access to raw events is often more sensitive than read-model access; restrict replay/export queries.
- **Backups and archives:** backups, archives, and replicas must also obey data policies.

You cannot always wipe an event cleanly from an append-only log without affecting integrity or retention obligations. Crypto-erasure, PII separation, tombstones, or special legal/control workflows may be required depending on applicable policies and regulations. Such decisions require confirmation from authorized specialists.

## 15. Event sourcing in distributed systems and consistency

Event sourcing does not automatically create distributed transactions across multiple aggregates or services. Appending an event to stream A does not atomically commit stream B and service C's database.

When use cases span multiple aggregates, use process managers/Sagas, reservations, compensation, eventual consistency, idempotent consumers, and reconciliation.

For example, a Booking is created before Inventory confirms the hold. State may be `PENDING_RESERVATION`; upon `ReservationAccepted`, the workflow moves to `PENDING_PAYMENT`. Never record `CONFIRMED` merely because the initial command was received.

### 15.1. Intermediate states are part of the model

Event sourcing often makes multi-state lifecycles explicit. Still, avoid inventing excessive statuses that do not reflect business rules. Every transition needs conditions, an owner, and error/timeout handling.

## 16. Performance, partitioning, and hot streams

Each aggregate typically has one ordered stream. If a single aggregate receives heavy write traffic, its stream can become a hot stream because every append must coordinate versions.

Performance questions:

- Are too many events hitting a single aggregate?
- Can aggregates be split along invariant boundaries while staying true to the domain?
- Does partitioning by stream/tenant/aggregate ID distribute load evenly?
- Do query projections need dedicated indexes?
- Are payloads overly large or duplicating excessive data?
- Can replay be bounded by time/version or use snapshots?
- Do subscriptions suffer consumer lag or checkpoint contention?

Never split an aggregate purely to boost throughput if doing so breaks invariants. If a single account sees thousands of transactions per second, a specialized ledger/partition design may be needed rather than a single stream.

## 17. Snapshots, archiving, and retention

Long-lived event-sourced systems need policies for aged events, snapshots, and backups.

| Component | Management approach | Risks to control |
| --- | --- | --- |
| Hot events | Low-latency store, frequent appends/reads | Storage cost, indexing, and backups |
| Infrequently accessed historical events | Archive/object storage or colder tiers | Higher restore/replay latency |
| Snapshots | Created by threshold; versioned and schema-tagged | Corrupted or incompatible snapshots |
| Current projections | Databases optimized for queries | Rebuildable, though time-consuming |
| Checkpoints | Durably persist consumer position | Faulty checkpoints drop or duplicate data |
| Event store backups | Backups/replication per RPO/RTO | Restores must verify ordering and integrity |

### 17.1. Snapshots do not replace backups

A snapshot is derived state at version K. It does not protect the full event stream against accidental deletion, corruption, or compromise. The event store needs its own backup/replication and restore drills; projections also need verified rebuild or recovery procedures.

### 17.2. Replay after archiving

If old events move to archive storage, aggregate loaders can read a snapshot and fetch only recent hot events. However, rebuilding projections from scratch still requires full history or a trusted baseline. Archiving plans must define retrieval paths, integrity checks, restores, and egress costs.

## 18. Testing event-sourced systems

Testing must cover reducers, command decisions, concurrency, replay, schema evolution, and side effects.

- **Reducer tests:** known event sequences produce expected state.
- **Command tests:** current state plus command yields expected events or business rejections.
- **Invariant tests:** invalid transitions are rejected.
- **Concurrency tests:** concurrent appends with the same expected version allow only one to succeed.
- **Replay tests:** rebuilding state/projections matches the authoritative baseline.
- **Snapshot tests:** loading snapshot K and applying events K+1...N equals full replay.
- **Schema compatibility tests:** historical event versions can be read by current reducers/upcasters.
- **Duplicate / reordering tests:** consumers handle duplicates, late events, or sequence gaps per contract.
- **Failure / recovery tests:** crashes after append, before publish, mid-projection update, and before checkpoint.
- **Privacy / security tests:** stream read permissions, masking, retention, and deletion/isolation comply with policy.

### 18.1. Property-based and invariant tests

Example for accounts: balance must never drop below the allowed limit; replaying any valid stream must preserve this invariant. Random command/event sequences can uncover unanticipated transition combinations. Tests must clearly define which events are valid, rather than expecting reducers to silently patch invalid events.

## 19. Practical example: rental order lifecycle

Suppose an equipment-rental platform must preserve booking-decision history to explain why an order was confirmed, cancelled, or refunded.

### 19.1. Sample stream

~~~text
Booking-1005
v1 BookingCreated(customerId, itemId, startAt, endAt)
v2 ReservationAccepted(reservationId, expiresAt)
v3 PaymentAuthorized(paymentReference, amount, currency)
v4 BookingConfirmed(confirmedAt)
v5 CancellationRequested(reason, requestedAt)
v6 BookingCancelled(cancelledAt)
v7 RefundRequested(refundId, amount)
v8 RefundCompleted(refundId, providerReference)
~~~

This sequence is illustrative. Some systems use a separate aggregate for Payment/Refund rather than packing every domain into the Booking stream.

### 19.2. How is state constructed?

- `BookingCreated` initializes state.
- `ReservationAccepted` marks the asset held.
- `PaymentAuthorized` records reference and authorized amount.
- `BookingConfirmed` transitions the order to confirmed.
- `CancellationRequested` records the cancellation request without yet confirming cancellation.
- `BookingCancelled` confirms the transition completed.
- Refund events describe the refund progression.

The key distinction is request vs. outcome. `RefundRequested` does not mean funds have been refunded. The system needs outcome events like `RefundCompleted` or `RefundFailed`.

### 19.3. Snapshots and query projections

After version 100 of a Booking stream, the system can store a snapshot containing confirmed booking state, reference info, and version 100. A query projection might store one row for the order-list screen. Snapshots speed up aggregate loading for command handlers; projections speed up list queries. The two serve different goals and can use different schemas.

### 19.4. Replaying to fix a projection

Suppose an old projection miscalculated rental days due to a timezone bug. Procedure:

1. Fix the projector and add boundary date/time tests.
2. Create a new projection version or table without immediately deleting the serving table.
3. Replay events from the appropriate checkpoint or stream start.
4. Compare record counts, states, totals, and checksums with independent verification.
5. Verify lag and edge cases, then switch queries to the new projection.
6. Retain a rollback path for a defined period and retire the old projection once stable.

Projection replay must never resend confirmation emails, charge payments, or issue refunds. Side-effect consumers run only on live streams with dedicated idempotency.

## 20. When is event sourcing a good fit?

Event sourcing is valuable when **change history is a core part of the data**, requiring state reconstruction or building multiple read views from the same business events.

Conditions that favor event sourcing:

1. **Deep auditing:** need to explain who/what created state and the decision trail.
2. **Critical business history:** finance, ledgers, contracts, bookings, or multi-state workflows.
3. **Temporal reconstruction:** need to reconstruct state at a specific point in time or version.
4. **Multiple projections:** one history feeding read models, reports, and integrations.
5. **Genuine replay value:** needing to rebuild projections, fix read logic, or migrate schemas.
6. **Clear business rules:** aggregate boundaries and event semantics can be cleanly modeled.
7. **Capable operations team:** tooling exists for event stores, replay, backups, schemas, and observability.

An organization can use event sourcing for select domains like ledgers/bookings while keeping CRUD for profiles, catalogs, or configs that rarely need full history. It does not need to apply system-wide.

## 21. When should you avoid it?

Event sourcing is usually not worth it for simple data where only current state matters, or when the organization lacks the operational maturity to manage long-term event histories.

Warning signs:

- **Simple CRUD:** slowly changing catalogs with no need for historical reconstruction.
- **No strong replay/audit need:** current state plus a proper audit log suffices.
- **Team cannot manage schema evolution:** event formats live for years while consumers change constantly.
- **Unclear business processes:** event types and aggregate boundaries churn continuously, driving migration overhead.
- **Deletion requirements conflict with retention:** no design yet for PII isolation, crypto-erasure, or legal holds.
- **Extreme volume on a hot single aggregate:** requires specialized architectures to preserve ordering and throughput.
- **Ad-hoc querying is the primary need:** event streams do not replace database queries or read models.
- **Cost and complexity exceed benefit:** event stores, projections, snapshots, replay tooling, and on-call burden are too heavy.

Do not adopt event sourcing solely to get an audit trail. A reliable audit log with immutability controls and proper storage can satisfy that requirement at lower cost.

## 22. Architectural trade-offs

| Criterion | Benefits | Costs / risks |
| --- | --- | --- |
| Business history | Reconstruction, auditing, and state explainability | Data grows over time; requires retention policies |
| Replay | Rebuild projections, test new logic on history | Resource-intensive; must suppress side effects |
| Snapshots | Reduce events loaded per command | Adds versioning logic, storage, and validation |
| CQRS | Read models tailored per use case | Eventual consistency and projection sync |
| Schema evolution | Long-term history preservation | Requires upcasters, compatibility, and tests |
| Concurrency | Expected version protects single streams | Conflicts and retries under high contention |
| Security / privacy | Clear audits and history controls | Long-lived PII in events and broad read sensitivity |
| Operations | Recover/rebuild read models from streams | Complex replay tooling, backups, and incident response |
| Cost | Decoupled writes/reads and multiple projections | Event storage, replication, indexing, compute, and archiving |

Choose the right level:

- CRUD with audit metadata when only current state and who edited it are needed.
- CRUD + transactional outbox when reliable integration event emission is needed.
- Bounded event log when only specific change types must be recorded for audit.
- Full event sourcing when events are the source of truth and replay/state reconstruction carries clear business value.

These are not mandatory maturity tiers. Choose the simplest approach that meets measurable requirements.

## 23. Safe adoption roadmap

1. **Choose a bounded context:** start with a domain where history matters and boundaries/owners are clear.
2. **Define aggregates and invariants:** specify stream IDs, concurrency scope, and valid transitions.
3. **Define event contracts:** names, schemas, metadata, versions, and minimal payloads.
4. **Select the event store:** verify durability, expected-version checks, subscriptions, backups, retention, and security.
5. **Write reducers and command handlers:** ensure deterministic apply logic and business rejections.
6. **Design projections:** query models, checkpoints, idempotency, and rebuild strategies.
7. **Design snapshots:** measure stream length/load time, schemas, and fallbacks.
8. **Design side effects:** isolate integration handlers, outbox/subscriptions, deduplication, and compensation.
9. **Define privacy / retention:** PII handling, encryption, legal holds, and archiving.
10. **Establish observability:** stream versions, append conflicts, projection lag, replay progress, and storage growth.
11. **Drill recovery:** restore the event store, rebuild projections, and load aggregates from snapshots.
12. **Review the decision:** continue, expand, or narrow scope based on TCO and realized value.

## 24. Common design mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Treating event sourcing like message publishing | Brokers lack sufficient history/semantics to rebuild state | Establish the event store as source of truth |
| Making events full row snapshots on every update | Bloated payloads and obscured business intent | Record events describing meaningful changes |
| Skipping expected-version checks | Concurrent commands create conflicting transitions | Stream-level optimistic concurrency |
| Calling APIs or reading current time in reducers | Replay yields inconsistent results | Keep apply logic deterministic; store needed facts |
| Replaying handlers that trigger side effects | Duplicate emails/payments | Separate projectors from integration side-effect consumers |
| Snapshots without version metadata | Misaligned or skipped events | Persist `atVersion` and apply only subsequent events |
| Treating snapshots as backups | Historical events lost if the store fails | Back up / replicate the event store separately |
| Breaking replay with schema changes | Old consumers fail to read history | Versioning, upcasting, and compatibility tests |
| Unthrottled replay during peak hours | Overloads DB and impacts production | Rate-limit replays and target separate projections |
| Overly hot single stream | High conflicts and latency | Revisit aggregate boundaries and invariants |
| Events storing PII without retention | Hard to fulfill erasure requests; larger breach blast radius | Data minimization, tokenization, retention |
| Persisting projection checkpoints before data | Skips events on restart | Atomic updates or recovery protocols |
| Using the event log as a query database | Difficult and slow queries | Use appropriate CQRS / read projections |
| Adopting event sourcing solely for auditing | Operational costs outweigh benefits | Compare against audit logs / CRUD + outbox |

## 25. Architecture verification and acceptance

An event-sourced system must prove its ability to write, read, replay, and recover.

- [ ] Events are the source of truth for chosen aggregates; CRUD/event-sourcing boundaries are clear.
- [ ] Aggregate IDs and event stream versions follow consistent rules.
- [ ] Appends enforce expected-version concurrency and idempotent command retries.
- [ ] Events include schema version, event ID, correlation, and data needed for reconstruction.
- [ ] Reducers are deterministic and covered by invariant tests.
- [ ] Replaying state and projections never repeats side effects.
- [ ] Snapshots record `atVersion`, schema version, validation, and fallbacks.
- [ ] Projection checkpoints never advance past committed data.
- [ ] Schema evolution/upcasting handles historical events.
- [ ] PII, retention, archiving, encryption, and stream read permissions are designed.
- [ ] The event store has backups/restores and has been drilled.
- [ ] Metrics track append conflicts, stream lengths, projection lag, replay progress, and storage growth.
- [ ] Replay throttling and runbooks exist for projection/DLQ errors.
- [ ] Benefits have been compared against CRUD, audit logs, and outbox.

## 26. Well-Architected assessment

| Perspective | Design questions |
| --- | --- |
| **Reliability** | Are acknowledged appends durable? Is the event store backed up? Can snapshots be rebuilt? Do replays and projections have recoverable checkpoints? |
| **Security** | Who can read streams? Do payloads hold PII/secrets? Are retention, key lifecycles, legal holds, and audits managed? |
| **Performance Efficiency** | Are stream lengths, append latency, replay duration, and projection lag within SLOs? Is snapshot cadence appropriate? |
| **Cost Optimization** | Are event storage, replication, indexing, archiving, snapshots, and replay compute forecasted? |
| **Operational Excellence** | Are there tools to inspect streams, monitor versions/conflicts, rebuild projections, roll back consumers, and drill recovery? |

## 27. Practice exercise

An internal financial platform manages expense accounts. Requirements: every balance change must be explainable; balances must be reconstructible at any month-end; department reports update within a few minutes; some user info must be deletable or separable per retention policy. Traffic includes several summary accounts receiving high transaction volumes.

Propose:

1. Should event sourcing apply to the entire system or only the ledger/account domain? Explain.
2. Design aggregates, event types, and metadata to preserve balance-change history.
3. How do you handle two concurrent transactions on the same account?
4. Under what conditions should snapshots be created, and what version metadata must be stored?
5. How do you build department reporting projections and rebuild them when logic changes?
6. Which events might carry PII, and what data should be tokenized or referenced externally?
7. How must the replay procedure prevent resending notifications, triggering payments, or applying side effects?
8. How would you set SLOs, retention, backups, and recovery tests?
9. What signals indicate the event store or a single aggregate stream is becoming a bottleneck?

A sound approach might use event sourcing for the ledger, isolate personal profiles into a separate datastore with its own lifecycle, use projections for reports, use snapshots to speed aggregate loading, and manage concurrency per account. Explicit policies must cover PII, backups, replay, and hot accounts; simply adding consumers will not help if all writes contend on one stream.

**Key takeaway:** event sourcing makes business-change history the primary data source; replay reconstructs state or projections; snapshots reduce the volume of events read while remaining derived data. The pattern is valuable when history, explainability, and reconstruction genuinely matter and the organization can manage schemas, privacy, storage, concurrency, and recovery. If only current state or simple auditing is needed, CRUD paired with audit logs/outboxes is usually easier to operate.
