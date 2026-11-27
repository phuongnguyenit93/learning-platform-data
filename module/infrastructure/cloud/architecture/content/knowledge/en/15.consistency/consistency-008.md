# CQRS and Separating Read Models from Write Models

## Learning objectives

A cloud system frequently has to process write commands carrying complex business rules while serving high volumes of queries with very different data shapes. Search screens, transaction lists, dashboards, and reports often require joins, filtering, sorting, or aggregations; meanwhile, the write path must protect invariants, handle contention, and commit data accurately.

**CQRS (Command Query Responsibility Segregation)** is the principle of separating the responsibility for handling commands that mutate state from the responsibility for querying state. CQRS can be applied within a single application and a single database. At a deeper level of separation, read models can be built independently, updated asynchronously, and deployed on separate infrastructure.

This lesson belongs to the **Consistency** chapter, focusing on dividing commands/queries, designing write/read models, synchronizing projections, managing consistency lag, and evaluating operational costs. It is a useful architectural option for certain workloads, while introducing extra state and synchronization pipelines to manage.

After this lesson, you will be able to:

- Distinguish commands from queries by their effect on state.
- Identify when a shared read/write model becomes a bottleneck and when CQRS only adds unnecessary complexity.
- Design write models that protect business invariants and read models optimized for query needs.
- Choose how to update projections via transactions, outbox/events, CDC, or polling.
- Handle eventual consistency, projection lag, duplicate events, ordering, replay, and rebuilds.
- Design read-your-writes, version checks, polling, and user experience when read data has not yet updated.
- Evaluate databases, caches, queues, networking, security, observability, TCO, and resilience in the cloud.
- Build quality scenarios and decide when to apply CQRS using Well-Architected principles.

## 1. The problem: one data model serving two workload profiles

Suppose a room-booking platform manages bookings, customers, rooms, pricing, and payments. A create-booking command must:

1. Verify the booker's identity and permissions.
2. Verify the room is available for the requested time range.
3. Calculate pricing per policy at the time of transaction.
4. Ensure no conflicting booking exists.
5. Persist the booking and related state consistently.
6. Emit events to send notifications and update downstream systems.

This is the **write** path with business invariants. A minor discrepancy can cause double-booking or miscalculate charges.

An admin screen may need total bookings by day, status, and branch; booking details combining guest, room, and payment info; a list of pending bookings with many filters; or revenue statistics by campaign. This is the **read** path, whose data shapes differ from the aggregates used to protect write invariants.

CQRS asks: should one model serve both writes and reads, or should two models be structured to fit each purpose?

~~~mermaid
flowchart LR
    CLIENT["Client / UI"] --> CMD["Command"]
    CMD --> WRITE["Write model"]
    WRITE --> WDB[("Write database")]
    WDB --> EVT["Event / Outbox"]
    EVT --> PROJECT["Projection handler"]
    PROJECT --> RDB[("Read model")]
    CLIENT --> QUERY["Query"]
    QUERY --> READ["Query handler"]
    READ --> RDB
~~~

The diagram illustrates CQRS with separated read/write models and asynchronous projection updates. CQRS does not require two databases; the core is **separating responsibilities and processing models**, while storage boundaries are a separate decision.

## 2. How do commands and queries differ?

### 2.1. Command: a request to change state

A command expresses intent to perform a business action, such as `CreateBooking`, `ConfirmBooking`, `CancelBooking`, `ChangeRoomPrice`, `CapturePayment`, or `ReserveInventory`.

A command handler typically checks:

- Does the caller have permission to perform the action?
- Is the input data valid?
- Is the aggregate in a state that permits the transition?
- Do business invariants still hold at commit time?
- Does the change conflict with concurrent commands?
- Will client retries produce duplicate side effects?

The command handler coordinates state transitions. The result is usually success/failure along with the ID, version, or status the caller needs to know what was confirmed.

### 2.2. Query: reading data without mutating business state

A query retrieves data for display, analysis, or decision support, such as `GetBookingDetails`, `SearchBookings`, `GetRevenueByDay`, or `FindPaymentsPendingReconciliation`.

Queries should avoid mutating business state. A query may emit technical telemetry or populate cache entries, but it should never silently confirm a booking or charge money. Query handlers optimize for access patterns: projections, joins, indexes, search engines, caches, pagination, or aggregated views.

### 2.3. Identification rules

| Question | Command | Query |
| --- | --- | --- |
| Intentionally mutates business state? | Yes | No |
| Enforces write business invariants? | Yes | No |
| Can return data? | Yes, usually ID/version/result | Yes, the requested data |
| Can retries cause side effects? | Yes, needs idempotency/concurrency control | Usually not, though still incurs load cost |
| Can data be optimized separately? | Write model | Read model |
| Example | Cancel booking | Check whether booking is cancelled |

HTTP methods do not replace understanding actual behavior. `GET` should never trigger payments or mutate state merely for convenience. Commands generally use `POST`/`PUT`/`PATCH`/`DELETE` per API semantics, while queries generally use `GET`.

## 3. What CQRS is and what it is not

### 3.1. CQRS separates responsibility, not necessarily infrastructure

At a simple level, an application keeps a single database while organizing command handlers and query handlers independently:

~~~mermaid
flowchart TB
    API["API layer"] --> C["Command handler"]
    API --> Q["Query handler"]
    C --> W[("Shared database")]
    Q --> R["Read queries"]
    R --> W
~~~

The same database serves both writes and reads, yet code paths, validation, and query models are separated. This reduces coupling in application code without needing distributed synchronization.

### 3.2. CQRS with separate read models

At a deeper level of separation, commands update the write database; events or CDC update read databases:

~~~mermaid
flowchart TB
    CMD["Command API"] --> CH["Command handler"]
    CH --> WDB[("Write DB")]
    WDB --> OUTBOX["Outbox / CDC"]
    OUTBOX --> BROKER[("Event stream / broker")]
    BROKER --> P1["Projection: booking list"]
    BROKER --> P2["Projection: dashboard"]
    P1 --> RDB1[("Read store A")]
    P2 --> RDB2[("Analytics store")]
    Q1["Query API"] --> RDB1
    Q2["Dashboard API"] --> RDB2
~~~

Read models can reside in a relational database, search engine, cache, document store, key-value store, or warehouse depending on requirements. Separate read stores allow read optimization without distorting the write model, but introduce eventual consistency and synchronization operations.

### 3.3. CQRS does not mean microservices or event sourcing

| Concept | Question it answers |
| --- | --- |
| CQRS | How do we separate command-handling and query-handling responsibilities? |
| Microservices | How are business capabilities split into independently deployable services? |
| Event-driven architecture | How do components react and communicate via events? |
| Event sourcing | How is current state represented by a sequence of events? |
| Read replica | How do we replicate data to scale read load? |
| Materialized view | How do we precompute query results for fast reads? |

You can use CQRS without event sourcing. The write model can still store current state in relational tables and emit events via an outbox. You can use microservices without CQRS. You can add read replicas while keeping the same query model. These techniques can work together, but none replaces the definition of another.

## 4. Write model: protecting business rules and invariants

The write model is designed around valid state transitions. For bookings, an aggregate may contain reservation status, dates, customer, room, locked-in price, and version.

Example invariants:

- A booking can be confirmed only while `Pending`.
- A booking cannot transition to `Confirmed` after being `Cancelled`.
- No two `Confirmed` bookings may conflict on the same room/time range.
- Total amount at confirmation must follow valid pricing policy.
- A payment capture carries a unique business key for the corresponding payment attempt.

The write model can combine domain objects, services, transactions, and database constraints. Do not rely solely on the UI or prior query checks, since state can change between read and write.

### 4.1. Illustrative command handler in Java

~~~java
public record ConfirmBookingCommand(
    UUID bookingId,
    UUID callerId,
    String idempotencyKey
) {}

public record CommandResult(
    UUID aggregateId,
    long version,
    String status
) {}

public final class ConfirmBookingHandler {
    private final BookingRepository bookings;
    private final AuthorizationService authorization;

    public ConfirmBookingHandler(
        BookingRepository bookings,
        AuthorizationService authorization
    ) {
        this.bookings = bookings;
        this.authorization = authorization;
    }

    public CommandResult handle(ConfirmBookingCommand command) {
        authorization.requireCanConfirm(
            command.callerId(), command.bookingId()
        );

        Booking booking = bookings.findForUpdate(command.bookingId())
            .orElseThrow(BookingNotFoundException::new);

        booking.confirm();
        bookings.save(booking);

        return new CommandResult(
            booking.id(), booking.version(), booking.status().name()
        );
    }
}
~~~

This is a conceptual example. Real applications must define transaction boundaries, handle idempotency keys, enforce optimistic/pessimistic concurrency, and derive caller identity from an authenticated server security context rather than trusting an arbitrary client-supplied `callerId`.

### 4.2. Concurrency and invariants on the write side

Two concurrent requests can both read "room available" before either commits. Measures that may need to work together include:

- Unique/exclusion constraints or overlap-protection mechanisms in the database.
- Optimistic locking with versions.
- Pessimistic locks on aggregates or contended resources.
- Conditional updates checking availability conditions.
- Appropriate transaction isolation and conflict retries.
- Idempotency keys to prevent duplicate commands from client retries.

CQRS does not automatically solve race conditions. The write model must protect invariants at the commit point; read models may lag and must never replace authoritative write checks.

## 5. Read model: optimizing for query needs

A read model is a data structure prepared to answer one or more queries efficiently. It may aggregate or denormalize data from multiple sources.

A booking-list screen may require booking ID, status, check-in/check-out dates, guest name, room, branch, total amount, and payment status. In the write model, these fields might live across multiple aggregates/tables. The read model can store them in one document or projection table to avoid joins and speed up searches.

### 5.1. Illustrative projection

~~~sql
CREATE TABLE booking_read_model (
    booking_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    customer_name VARCHAR(200),
    room_name VARCHAR(200),
    branch_id UUID,
    booking_status VARCHAR(30) NOT NULL,
    payment_status VARCHAR(30),
    check_in DATE,
    check_out DATE,
    total_amount DECIMAL(18,2),
    source_version BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

This table is an example, not a mandatory schema. A read model should store only fields needed by queries, respecting permissions and data classification. Do not copy PII or sensitive payment details if the screen does not need them.

### 5.2. Multiple read models for multiple access patterns

| Read model | Optimized query | Storage options to consider |
| --- | --- | --- |
| Booking detail | Single booking by ID with related fields | Document / relational projection |
| Booking search | Filtering, sorting, full-text, pagination | Search index |
| Daily dashboard | Grouping, aggregates, trends | OLAP / warehouse / materialized aggregates |
| Available room lookup | Fast lookup by date/location | Key-value / cache or projection |
| Customer history | Transaction list for one customer | Partitioned relational / document view |

You do not need a separate database for every query. A read model can simply be a schema or materialized view in the same database, depending on scale and independence needs.

### 5.3. Intentional denormalization

Read models often store pre-joined or pre-aggregated data. This makes queries simpler and faster, but data is duplicated. When a guest's name changes, every projection containing that name may need updating; when asynchronous, stale names can appear temporarily.

Decide which fields are point-in-time snapshots (e.g., name on an issued invoice), which should always reflect the latest value, which projections tolerate eventual consistency, and which events source changes emit to update each view.

## 6. CQRS and consistency: read models usually update asynchronously

When the write database and read database are separate stores, a write transaction cannot commit both simultaneously by default. The typical flow is:

1. Command updates the write database.
2. Same transaction writes an outbox event.
3. Relay/event connector emits the event.
4. Projection handler consumes the event.
5. Read model is updated.
6. Subsequent queries read the new state.

Between step 1 and step 5, users may read old data. This is **eventual consistency**: if no new updates occur and normal processing continues, the read model eventually reflects the source state.

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as Command API
    participant W as Write DB
    participant O as Outbox / Broker
    participant P as Projection worker
    participant R as Read DB
    participant Q as Query API
    U->>C: Confirm booking
    C->>W: Commit booking + outbox
    W-->>C: Commit success, version 12
    C-->>U: Confirmed, version 12
    U->>Q: Refresh booking list
    Q->>R: Read projection
    R-->>Q: May still be version 11
    O->>P: Deliver event version 12
    P->>R: Apply projection
    Q->>R: Read again
    R-->>Q: Version 12
~~~

Define the user experience when a query returns an older version. You can display "updating"; for actions requiring exact state, queries must check the write model or use a read-your-writes token.

## 7. Strategies for synchronizing read models

### 7.1. Synchronous update in the same database

When write and read models live in the same relational database, the command handler can update both within the same transaction or use triggers/materialized views depending on design.

**Advantages:** strong consistency within the transaction boundary, simplifies read-after-write.

**Limitations:** both models still share CPU, I/O, locks, and connections; heavy projections can lengthen transactions and slow writes. This is useful for starting CQRS with code-level separation.

### 7.2. Transactional outbox

The write transaction records both business state and an event in the outbox. A relay reads and publishes the event; projection consumers update read stores. The outbox eliminates the gap between committing business data and recording emission intent.

If the relay publishes successfully but crashes before marking the event sent, the event may be redelivered. Projection consumers must be idempotent by `eventId`/version or use safe upserts.

### 7.3. Change Data Capture (CDC)

CDC reads the write database's transaction log or change stream to emit change events. Clarify:

- Which changes are business events vs. purely technical updates?
- Is all information needed for the projection present, or are extra lookups required?
- How do schema migrations affect the connector?
- How are lag, offsets, retention, and recovery managed?
- Are deletes represented by tombstones or explicit events?
- From what point can replay occur, and is source data still retained?

CDC captures row changes; it does not automatically turn every row mutation into a well-designed domain event. Define clear contracts for consumers.

### 7.4. Polling or scheduled refresh

A periodic job queries changes since the prior watermark and updates the read model. This fits workloads that do not require near-real-time updates.

Risks include polling lag, missing late-arriving records, faulty watermarks, extra query load on the write database, and overlapping runs. Use stable timestamps/sequences, durable checkpoints, overlap windows, and idempotent upserts.

### 7.5. Comparing options

| Option | Update latency | Complexity | Best suited when |
| --- | --- | --- | --- |
| Same DB transaction | Nearly immediate on commit | Low to medium | Same DB, read models are lightweight |
| Outbox + broker | Near real-time with some lag | Medium to high | Separate stores and reliable event emission needed |
| CDC | Typically near real-time | High, requires connector/ops | Many tables/change sources needing log capture |
| Polling / batch refresh | Per schedule | Low initially | Reporting data tolerates delay |
| Full rebuild | Depends on rebuild time | Resource-intensive | Recreating projections, migrations, or recovery |

Do not choose solely by nominal latency. Test throughput, duplicates, ordering, recovery, schema evolution, and operational cost.

## 8. Projection handlers: idempotency, ordering, and versions

A projection handler transforms events into read-model state. It must tolerate duplicate, delayed, out-of-order, and replayed events.

### 8.1. Idempotent projection

A straightforward approach stores the aggregate's `source_version`. Apply updates only when the incoming version is newer than the stored version.

~~~sql
INSERT INTO booking_read_model (
    booking_id, booking_status, source_version, updated_at
)
VALUES (
    :booking_id, :status, :version, CURRENT_TIMESTAMP
)
ON CONFLICT (booking_id)
DO UPDATE SET
    booking_status = EXCLUDED.booking_status,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
WHERE booking_read_model.source_version < EXCLUDED.source_version;
~~~

Syntax resembles PostgreSQL. In production, handle same-version different-payload anomalies, validate events, and update all projection columns per contract.

If the projection performs additive aggregations like incrementing total bookings, upserting by a single aggregate's version may not suffice. Record processed event IDs, use transactions, or design projections that can be recomputed from source data.

### 8.2. Ordering and version gaps

Suppose a projection currently holds booking version 8 and receives event version 7. It can safely ignore the stale event. If it holds version 6 and receives version 8, event version 7 is missing. Depending on the business, wait briefly for the missing event, reload aggregate state from the authoritative source, rebuild the aggregate's projection, or quarantine the event and alert.

Do not blindly apply version 8 if skipping version 7 drops a critical state transition.

### 8.3. Event schema evolution

Projection consumers may outlive producer versions or deploy independently. Maintain schema versions and compatibility rules:

- Add optional fields with sensible defaults.
- Never change the meaning of an existing field without versioning.
- Never remove fields still required by active older consumers.
- Maintain producer/consumer contract tests.
- Plan historical event replay when upgrading projections.
- When changing a read model, run the new projection version in parallel and switch query traffic after verification.

## 9. Read-your-writes and user experience

An eventually consistent system can cause a user who just confirmed a booking to still see `Pending` in the list. That is not necessarily a source-data bug, yet without clear UX, users may click confirm again or contact support.

Strategies:

**Return clear command state:** return `bookingId`, `version`, and committed status in the command response. The UI can display the command outcome directly instead of waiting for the read projection.

**Read-your-writes routing:** immediately after a command, queries can read from the write database or authoritative status endpoint for a short window.

**Version token:** the client passes `minimumVersion` in the query; the read service waits briefly for the projection to reach that version or reports that it is not ready yet.

**Polling:** the client polls projection state with backoff and limits; avoid tight polling loops that overload servers.

**Push updates:** the server pushes updates via WebSocket/SSE once the projection updates, if UX demands it.

**Optimistic UI:** the UI renders the expected post-command state while marking it pending until confirmed.

### 9.1. Never turn queries into write-decision authorities

Read models can lag. If a client sees a room available in a projection and sends a reserve command, the write handler must still verify the write model and invariants. "The query just said it was available" does not grant reservation rights.

### 9.2. Consistency levels by use case

| Use case | Desired consistency | Possible strategy |
| --- | --- | --- |
| Booking confirmation | Return confirmed only after write commit | Write model is authoritative |
| Booking list after confirmation | Brief lag allowed if UX indicates it | Read-your-writes / version token |
| Revenue reports | Periodic delay acceptable | Batch projection, watermark |
| Available room counts | Must not oversell | Check and reserve on write side |
| Payment details | May need near-latest state | Query authoritative source or versioned projection |
| Executive dashboard | A few minutes acceptable | Dedicated aggregate / read store |

Do not apply one consistency policy to every query. Tie requirements to the consequence of reading stale data.

## 10. Rebuilding, backfilling, and migrating read models

Read models are derived data; you must be able to rebuild or repair them when projection logic changes.

### 10.1. Rebuilding from event logs

If events are retained long enough under stable schemas/contracts, you can build a new projection by replaying events from the beginning or a checkpoint. Account for event retention, rebuild duration, production impact, isolating live traffic from replay, suppressing external side effects, validating the new projection, and rollback capability.

### 10.2. Backfilling from the write database

If event history is insufficient, read a current snapshot from the write database to build the projection. Use a snapshot or watermark so changes occurring during backfill are not lost.

Reference workflow:

1. Establish a consistent data marker or snapshot.
2. Backfill by key range/partition.
3. Concurrently capture changes occurring after the watermark.
4. Apply remaining changes in proper order.
5. Compare record counts, aggregate totals, and sample records.
6. Run shadow queries to compare outputs.
7. Shift traffic to the new read model.
8. Retain rollback capability until stability is confirmed.

### 10.3. Blue/green projections

You can build `booking_read_v2` alongside `booking_read_v1`. The projection worker populates v2; once v2 shows low lag and passes data checks, the query service shifts traffic gradually. Keep v1 for a rollback window.

Never delete the old projection immediately after cutover. Account for indexes, storage, quotas, and retention; during dual-build, databases and workers carry higher load.

## 11. Does CQRS require event sourcing?

**No.** CQRS only requires separating command and query responsibilities. The write model can use standard CRUD/relational state and a transactional outbox.

Event sourcing stores immutable events as the source of truth to reconstruct aggregate state. It helps when full state-change audit history and domain event replay are required, but demands event evolution, snapshots, projections, ordering, and operating an event store.

| Characteristic | CQRS with state-based write model | CQRS combined with event sourcing |
| --- | --- | --- |
| Source of truth | Current state in DB | Sequence of immutable events |
| Writes | Update/insert/delete transactions | Append valid events |
| Rebuilding read models | From snapshots/CDC/outbox or current state | Can replay event history |
| Auditing | Requires separate history if needed | Event history is natural |
| Complexity | Lower in many CRUD apps | Higher: versioning, snapshots, projections |
| Querying state | Read from write model or projection | Fold events or projection |
| Best fit | Systems needing moderate separation | Event-centric domains where audit/replay is a major need |

Do not adopt event sourcing simply because you chose CQRS. Confirm that history, audit, and replay benefits outweigh the added cost and learning curve.

## 12. Databases and cloud infrastructure for CQRS

### 12.1. Same database, separate schemas

An application can use one relational database where command handlers update business tables and query handlers read views, materialized views, or separate projection tables.

Advantages: simple transactions and consistency; easy to start; fewer operational components.

Limitations: reads and writes still compete for CPU, I/O, locks, and connections; heavy read workloads can degrade transactions. Separate indexes, workload isolation, query budgets, and pools are needed.

### 12.2. Write primary and read replicas

One primary handles writes while replicas serve queries. This is read scaling, not strictly CQRS. Replicas usually update asynchronously, so queries can read stale data.

Monitor replication lag, manage read-after-write, plan failover, and ensure replicas handle query load. If query shapes differ substantially, dedicated read projections may fit better than raw replicas.

### 12.3. Separate write store and read store

You can use a relational database for transactions, a search engine for search, a warehouse for analytics, or a cache/document database for detail views. Manage:

- Network hops and egress/cross-zone costs.
- Duplicated data and deletion policies.
- Encryption, IAM, and tenant isolation per store.
- Backup/restore and rebuilds.
- Credentials, connection pools, and quotas.
- Data residency, retention, and audits.

Separate read stores enable independent scaling but add dependencies and failure modes. If a read projection fails, can write commands continue? That depends on event durability, backlog capacity, and business requirements.

### 12.4. Degraded mode

If the read store is down while the write database remains healthy, commands can continue writing and the outbox accumulates events; queries can return errors or fall back to the authoritative source under load limits. If the broker is down, the outbox retains events for later relay; monitor backlog and capacity.

Never allow unbounded backlogs. Enforce retention, storage capacity limits, throttling, and alerts before the outbox fills the write database.

## 13. Security and access control across both models

Separating reads and writes must never create a security bypass.

- Command handlers authenticate callers and authorize every action.
- Query handlers verify per-object permissions and tenant scope; read models are not public data.
- Projections copy only fields needed into the read store.
- Events/outbox may hold PII or payment metadata; apply encryption, retention, and access controls.
- Projection workers' service identities should only read allowed topics/schemas and write to the intended read store.
- Tenant ID must be derived/validated from a trusted source, never trusted blindly from client inputs.
- Audit critical commands, permission changes, replays, and data-affecting rebuilds.
- When deleting personal data, propagate deletions to read models, caches, search indexes, warehouses, and archives per policy.

A common bug is enforcing strict authorization on the command side while the query side fetches projections by ID without tenant checks, letting users read another tenant's data. Enforce authorization at every query boundary.

## 14. Performance, caching, and consistency costs

### 14.1. Separating reads and writes can reduce contention

When dashboards run continuous reads, a dedicated read database or warehouse relieves pressure on the write primary. However, projection lag, event backlogs, storage, and networking raise costs.

CQRS can also spawn many query services/handlers; if a read model does not match access patterns, the system adds extra layers while still needing joins or multi-service calls.

### 14.2. What role does caching play?

Caching optimizes the read path; it is not synonymous with a read model. You can cache query results or projections, but you must design invalidation and TTLs. If a cache updates slower than the read store, consistency lag gains another layer.

Cache-aside, write-through, and event-driven invalidation carry distinct trade-offs. For sensitive permissions or payment data, long TTLs can display stale state dangerously. Cached queries must never become the decision source for critical commands.

### 14.3. Estimating lag and backlog

Suppose a system emits an average of 500 events/second, and the projection worker processes 650 events/second during normal operation. If the worker stops for 2 minutes:

~~~text
Accumulated backlog = 500 events/s × 120 s
                    = 60,000 events
~~~

Once the worker resumes, net catch-up capacity above incoming events is:

~~~text
650 - 500 = 150 events/s
~~~

Time to drain the backlog, assuming steady arrival and processing rates:

~~~text
60,000 / 150 = 400 seconds ≈ 6 minutes 40 seconds
~~~

This example ignores bursts, retries, uneven processing times, and read-store throttling. If the worker only matches the arrival rate, the backlog never drains. Provision sufficient headroom and test recovery times, not just steady-state throughput.

### 14.4. Cost per query and business operation

~~~text
Cost per successful command
  = (Write compute + write DB + event/outbox + network + operations)
    / Number of successful commands

Cost per query
  = (Read compute + read store + cache + network + observability)
    / Number of successful queries
~~~

With separate stores in CQRS, costs include duplicate storage, brokers, projection compute, additional logs/tracing, and backups. Compare against current read-query costs on the primary, including impacts on write performance and primary scaling.

## 15. Observing and operating CQRS

Do not monitor command APIs and query APIs in isolation. Track the entire chain from write commit to read projection.

| Group | Metrics | Question |
| --- | --- | --- |
| Command | Success/failure, conflicts, validation errors, p95/p99 latency | Are writes accurate and timely? |
| Write store | Transaction duration, lock waits, connections, replication | Is the authoritative source overloaded? |
| Event / outbox | Pending count, oldest unpublished age, publish failures | Are changes being emitted? |
| Broker | Throughput, lag, redeliveries, DLQ, partition skew | Where are events waiting or failing? |
| Projection | Processing duration, failures, version gaps, duplicates ignored | Is the read model keeping up with the source? |
| Read store | Query latency, index/cache hits, storage, throttling | Do queries meet SLOs? |
| Consistency | Projection lag, source version vs. read version | How stale is read data? |
| Business | Command completion, query correctness, reconciliation mismatches | Are users receiving accurate results? |
| Cost | Cost per command/query, storage, broker, egress | Is separating models worth the cost? |

### 15.1. Traces and correlation

Attach `commandId`, `aggregateId`, `eventId`, `correlationId`, and `sourceVersion` across boundaries. Traces can link Command API, Write DB, outbox relay, broker, projection worker, and Read Store. Never embed personal data in span attributes.

Correlation IDs trace journeys; `sourceVersion` shows how caught up a projection is.

### 15.2. Impact-based alerts

- Oldest unpublished outbox event exceeds threshold.
- Projection lag breaches SLO.
- Read-model version gap persists.
- DLQ count spikes abnormally.
- Read store throttling or query p99 exceeds target.
- Command conflicts spike due to concurrency.
- Zero projection updates while write events continue rising.
- Reconciliation mismatch between write and read models.
- Outbox/broker storage approaching capacity.

Every alert needs an owner, dashboard, and runbook. Do not alert on a single duplicate event if consumers deduplicate safely; however, rising duplicate rates can signal misconfigured ACKs/visibility timeouts or producer retries.

## 16. Illustrative SLOs and quality scenarios

Thresholds are learning examples, not universal standards. Define exact measurement points, windows, workloads, and business consequences.

| ID | Scenario | Expected response | Illustrative measure |
| --- | --- | --- | --- |
| QA-CQRS-01 | User confirms booking | Write model commits invariant; response returns written version | 99.9% of valid commands confirmed within p95 500 ms |
| QA-CQRS-02 | Projection worker operates normally | Read model converges toward source version | 99% of events applied within 10 seconds |
| QA-CQRS-03 | Worker stops 2 minutes then recovers | Backlog drains without dropping or misapplying events | Lag below 10 seconds within 8 minutes; zero business key discrepancies |
| QA-CQRS-04 | Client reads right after command | Supports read-your-writes or indicates pending status | Read returns minimum version or reports projection still updating |
| QA-CQRS-05 | Consumer receives duplicate/out-of-order events | Deduplication/version checks protect projection | Zero state regressions; event gaps detected |
| QA-CQRS-06 | Read store fails | Commands continue if durability/backlog suffice; queries degrade gracefully | Command SLO holds during test window; backlog stays within capacity |
| QA-CQRS-07 | Tenant A queries Tenant B data | Denied and audited | 100% of unauthorized attempts blocked in test suite |
| QA-CQRS-08 | Rebuild new projection version | New projection matches source before traffic cutover | Counts, totals, and sample records pass reconciliation |

Projection-lag SLOs differ from command API SLOs. Commands can finish fast while projections lag by minutes. If the business needs near-real-time updates, measure and set explicit targets for it.

## 17. Case study: CQRS booking platform

### 17.1. Context

A booking platform receives far higher search and booking-list read traffic than write traffic. During promotions, internal dashboards run heavy aggregate queries that drive up CPU and lock contention on the write database.

Hypothetical requirements:

- Booking confirmation commands must prevent room double-booking.
- Booking list tolerates brief lag if an update indicator is shown.
- Revenue dashboard tolerates up to a few minutes of delay.
- Search queries need flexible filtering/sorting.
- Tenant data must stay isolated.
- Read models must be rebuildable after schema changes.

### 17.2. Design

**Write side:** Spring Boot Command API and relational primary. Booking aggregate, constraints, and transactions protect invariants. Outbox rows are written in the same transaction.

**Event transport:** Relay emits booking, payment, and cancellation events. The broker persists events per durability policy; consumers handle at-least-once delivery.

**Read side:**
- Booking detail/list projection in a relational read store.
- Search projection in a search engine.
- Revenue aggregates in an analytical store.
- Query handlers enforce tenant scope, pagination, and version/lag checks.

~~~mermaid
flowchart TB
    U["Web / Admin"] --> CMD["Command API"]
    CMD --> W["Write model"]
    W --> WDB[("Relational primary")]
    WDB --> O[("Outbox")]
    O --> B[("Event broker")]
    B --> P1["Booking projection"]
    B --> P2["Search projection"]
    B --> P3["Revenue projection"]
    P1 --> R1[("Read relational store")]
    P2 --> R2[("Search store")]
    P3 --> R3[("Analytics store")]
    U --> Q1["Booking query API"]
    U --> Q2["Search query API"]
    U --> Q3["Dashboard query API"]
    Q1 --> R1
    Q2 --> R2
    Q3 --> R3
~~~

### 17.3. Behavior right after booking confirmation

Command API commits the booking and outbox; returns `bookingId`, `Confirmed`, and version 12. The UI displays confirmation from the command result. The booking list may still be at version 11, so the query API accepts `minimumVersion` 12 or the UI shows an updating indicator. Once the projection reaches version 12, data displays normally.

The revenue dashboard can update within a few minutes; more critical payment detail screens can read from a strongly consistent source or display a reconciling status.

### 17.4. Incidents and recovery

Suppose the search projection worker stops for 4 minutes. Write commands continue if the outbox/broker have adequate capacity and durability. Search data becomes staler; the UI can display the last-updated timestamp or degrade features. When the worker resumes, the backlog drains and version checks prevent old events from overwriting newer state.

If the read store suffers a prolonged outage, never let an unbounded backlog fill the write source. Enforce retention limits, alerts, pause non-critical workloads, or scale capacity safely. Search index rebuilds run separately, reconcile, and only then receive cutover traffic.

### 17.5. Benefits and costs

Benefits: search/dashboard queries scale independently, the write model stays focused on invariants, and each read model is tailored to its access pattern.

Costs: event transport, projection workers, multiple datastores, schema versioning, eventual consistency, reconciliation, backups, and operational on-call load. At small scale, these costs can outweigh benefits; try optimizing queries, indexes, and read replicas before splitting deeply.

## 18. When should and shouldn't you use CQRS?

| Signal | Decision to consider |
| --- | --- |
| Reads and writes have markedly different access patterns | Separating query handlers/models may help |
| Dashboards/analytics overload the write primary | Dedicated read projections or analytical store |
| Read queries require complex joins/aggregations/search | Materialized read models / search projections |
| Need to scale reads and writes independently | CQRS with separate read stores if TCO fits |
| Multiple projections serve diverse consumers | Event-driven projections may fit |
| Simple CRUD with similar read/write patterns | One model is likely simpler |
| Team lacks capacity to operate brokers/CDC | Start with single-DB CQRS or hold off splitting |
| Data requires immediate consistency on every query | Asynchronous read stores may not fit |
| Authoritative source and ownership are undefined | Do not split into multiple stores yet |
| Multiple systems write directly to the same data | Clarify ownership before building projections |

CQRS is not the default for every CRUD application. Adopt it for a specific measurable problem, not because the architecture looks modern.

## 19. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking CQRS requires two databases | Unnecessary infrastructure | Separate command/query in code first |
| Using read models to enforce write invariants | Stale reads cause bad writes or overbooking | Check and commit invariants on the write side |
| Treating queries and commands as differing only by HTTP verb | Business logic remains tangled | Classify by effect on state |
| Not measuring projection lag | Users see stale data with no visibility | Lag SLIs, versions, and dashboards |
| Non-idempotent projections | Duplicate events inflate numbers | Inboxes, business keys, versions, and upserts |
| Ignoring out-of-order events | Projection state regresses | Aggregate versions and gap handling |
| Outbox without cleanup | Unbounded table growth, slow queries | Retention/archiving with audits |
| Unthrottled projection rebuilds | Overloads DB/broker/read store | Throttle, snapshot, shadow build |
| Copying all PII to read stores | Increases data risk and deletion cost | Data minimization and deletion propagation |
| Not reconciling source vs. read model | Silent drift persists undetected | Counts, totals, versions, and reconciliation |
| Adopting event sourcing just because of CQRS | Complexity outweighs benefit | Evaluate event-history needs separately |
| Splitting too early | Extra services, queues, and runbooks | Start from real bottlenecks and SLOs |

## 20. Practice exercise

A ticketing platform handles 50,000 search queries per minute during ticket drops and 500 booking commands per minute. Each ticket can be sold only once; the revenue dashboard can lag by up to 2 minutes; a user's ticket list must reflect newly placed orders within 5 seconds. The system currently uses one relational database.

Complete the following:

1. Identify commands and queries across searching, holding tickets, confirming payment, cancelling tickets, and viewing history.
2. Sketch the write model enforcing the invariant "one ticket has at most one valid owner."
3. Design at least two read models for search and dashboards; explain why their data shapes differ.
4. Choose how to emit events from the write model and explain how outbox/CDC fits.
5. Design a projection handler with idempotency, version checks, and out-of-order event handling.
6. Propose a read-your-writes mechanism so the ticket list updates within 5 seconds.
7. Define degraded modes when the read database or broker goes down.
8. Propose metrics for command latency, query latency, projection lag, outbox age, duplicate rate, and reconciliation.
9. Calculate backlog and recovery time if 20,000 events accumulate and the worker processes 300 events/s while 200 new events/s continue arriving.
10. Build a TCO comparison against optimizing queries/indexes/read replicas on a single database.
11. Write an ADR stating CQRS adoption criteria, residual risks, and review triggers.

**Self-assessment hints:** A solid solution specifies the authoritative source, write-side invariants, read models, update mechanisms, allowable lag, recovery approach, and measurable evidence. Drawing two databases without explaining synchronization is not a complete CQRS design.

## 21. Pre-production checklist for CQRS

- [ ] Commands and queries are distinguished by state mutation impact.
- [ ] Write model has an authoritative source and enforces invariants in transactions.
- [ ] Query handlers have clear access patterns, schemas, and indexes.
- [ ] Read models store only necessary data and enforce tenant authorization.
- [ ] Reliable change-emission exists: same-DB transaction, outbox, CDC, or checkpointed polling.
- [ ] Projections are idempotent with version/order policies and gap handling.
- [ ] Consistency expectations are defined per query.
- [ ] Read-your-writes or pending-state UI is provided where appropriate.
- [ ] Rebuild/backfill, shadow validation, and projection rollback plans exist.
- [ ] Deletion propagation covers caches, search, warehouses, and archives.
- [ ] Metrics cover projection lag, outbox age, DLQs, version gaps, and reconciliation.
- [ ] Capacity/retention exists for backlogs when consumers or read stores fail.
- [ ] TCO includes brokers, compute, read stores, network, backups, observability, and operations.
- [ ] Duplicates, out-of-order events, crashes, lag, failovers, and rebuilds have been tested.
- [ ] ADR states benefits, limitations, and triggers to retire or revisit CQRS.

## 22. Well-Architected assessment

| Pillar | Questions when designing CQRS |
| --- | --- |
| **Operational Excellence** | Can projections, rebuilds, replays, schema migrations, and reconciliation be operated with clear runbooks? |
| **Security** | Are command/query authorization, tenant isolation, event protection, and deletion propagation complete? |
| **Reliability** | Are write state and events recorded reliably; do projections tolerate duplicates, lag, and recover cleanly? |
| **Performance Efficiency** | Do reads/writes scale independently at real bottlenecks; do lag, p95/p99, and connections meet SLOs? |
| **Cost Optimization** | Does reduced primary load offset read stores, brokers, workers, storage, and operational effort? |
| **Sustainability** | Do we avoid unnecessary data duplication, repeated rebuilds, and idle read-store resources? |

**Conclusion:** CQRS separates the responsibility for mutating state from querying state, enabling the write model to protect invariants while read models optimize for specific access patterns. When the two models live in separate stores synchronized via events, the system must manage projection lag, duplicates, ordering, replay, and reconciliation. Apply CQRS when read/write differences are distinct enough to justify synchronization and operational costs; start from logical boundaries, define the authoritative source, and measure end-to-end quality in the Well-Architected spirit.
