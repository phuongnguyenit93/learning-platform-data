# Replay, Backfill, and Distinguishing Recovery Data from New Data

In **SPRING_BOOT_INTEGRATION**, a Spring Boot application can ingest data via HTTP clients, databases, caches, message brokers, and Spring Integration adapters. Integration flows typically run continuously, yet in practice consumers go down, message retention expires, a buggy release misprocesses records, or a summary table must be rebuilt. When that happens, **replay** or **backfill** is needed to recover data.

The challenge is not merely feeding old data back into the system. You must know **what the data describes, when it occurred, whether it was already applied, whether it is still valid, and whether reprocessing triggers side effects**. Treating a re-ingested historical event as a "brand-new order" can resend emails, distort today's revenue reports, overwrite newer state, or double-charge customers.

Lesson objectives:

- Distinguish **retry**, **replay**, **backfill**, **reprocess**, **reconciliation**, and **live** flows.
- Model **event identity**, **business time**, **data provenance**, and **recovery runs** as separate concepts.
- Design **idempotent** processing and enforce **version/order** checks when historical and live data interleave.
- Execute safe replay/backfill across Spring Boot, PostgreSQL, HTTP, brokers, and Spring Integration.
- Verify **completeness, consistency, and zero duplicate side effects** instead of merely counting messages read.

## 1. Scenario: losing a slice of data while the live stream keeps running

Suppose an **Order Projection** service consumes order-status events from a partner system to populate a fast lookup read table. The partner emits:

~~~text
10:00  order-42 / version=10 / CREATED
10:05  order-42 / version=11 / PAID
10:10  order-42 / version=12 / SHIPPED
10:15  order-42 / version=13 / DELIVERED
~~~

The consumer fails from 10:04 to 10:12. After recovering, it may receive **version=13** over the live stream while a backfill job fetches **version=11** and **version=12** from the historical API. If the updater applies messages in **arrival order**, the following can happen:

~~~mermaid
sequenceDiagram
    participant Source as Source system
    participant Live as Live consumer
    participant Backfill as Backfill worker
    participant DB as Order projection DB
    Source->>Live: DELIVERED (v13)
    Live->>DB: Save DELIVERED, version=13
    Source->>Backfill: History PAID (v11), SHIPPED (v12)
    Backfill->>DB: Try writing PAID (v11)
    Note over DB: Unconditional overwrite -> wrong!
    Backfill->>DB: Try writing SHIPPED (v12)
    Note over DB: Update only when incoming version is newer
~~~

The right requirement is **recovering missing history without regressing the latest state**. At the same time, a "new orders today" report must not double-count orders merely because they were loaded into the database today.

This example assumes the source assigns a **monotonically increasing version per orderId** for each state change. If the upstream lacks reliable versions or sequences, pick another strategy such as watermarked snapshots, CDC log positions, or reconciliation; **consumer receipt timestamps are insufficient to determine which record is newer**.

## 2. Related terms that are not the same

| Concept | Meaning | Example | Risk if confused |
| --- | --- | --- | --- |
| **Live ingestion** | Ingesting events emitted during normal operation | Consumer receives OrderPaid right after emission | Mistaking late messages for brand-new events |
| **Retry** | Re-attempting an unfinished or uncertain operation | HTTP timeout followed by resend with same idempotency key | Duplicate transactions or side effects |
| **Redelivery** | Broker re-delivering an unacked or failed delivery | RabbitMQ requeue after consumer crash | Double charging if consumer is not idempotent |
| **Replay** | Re-running **existing** events/records from durable history | Re-reading Kafka offsets or event archive to rebuild projection | Resending notifications and unintended side effects |
| **Backfill** | Filling missing data or loading historical data for a range | Fetching orders from partner API for 10:04–10:12 | Overwriting live updates or missing boundary records |
| **Reprocess** | Recomputing already-processed data after logic/contract changes | Recalculating VAT from source records after a bugfix | Changing business outcomes without auditing/versioning |
| **Reconciliation** | Comparing two sides to detect and resolve discrepancies | Cross-checking source order counts against projection | Mistaking "job succeeded" for "data is complete" |

**Replay** typically reads from a **durable event log**, whereas **backfill** may read from snapshots, paginated APIs, staging tables, or historical archives; naming conventions vary across organizations. What matters is knowing the **source of truth** and the **semantics of the data being read**.

When a broker retains messages only temporarily, wanting to replay does not mean old messages are still there. Without an event archive or historical API, you may be **unable to reconstruct** the past via consumer retries alone.

## 3. Distinguishing three kinds of time

A historical event can be reprocessed long after it occurred. Never rely on a single `created_at = now()` column to represent every kind of time.

| Field | Meaning | Example |
| --- | --- | --- |
| **occurredAt / eventTime** | When the event **occurred in business terms** per the source | Partner confirmed payment at 10:05 |
| **sourceRecordedAt / sourcePosition** | When the source recorded it or its ordered log/CDC position | CDC LSN, event sequence 11 |
| **ingestedAt / observedAt** | When the integration system **received it this time** | Backfill ingested event at 14:00 |
| **processedAt** | When the handler committed the effect to the projection | 14:00:01 |
| **recoveryRunId** | Which replay/backfill run brought this record in | run-20261121-01 |

A PAID event that occurred at 10:05 and was backfilled at 14:00 is still a **10:05 PAID event**, not a new payment at 14:00. Therefore:

- **Business-time reporting** uses `eventTime` or effective date per contract.
- **Integration latency reporting** uses the delta between `ingestedAt` and `occurredAt` (accounting for possible source clock skew).
- **Recovery auditing** uses `recoveryRunId`, run timestamps, and recovery source provenance.
- **Update ordering** uses `sourceVersion`, sequence, or an order-guaranteed version source; **never rely solely on `ingestedAt` or `occurredAt`** when upstreams have lag or clock skew.

Specify timezones, UTC formatting, timestamp precision, and "accounting day" rules in the data contract. Sometimes an event is **recorded at 10:05 yet retroactively effective from 09:00**; model `effectiveAt` separately rather than conflating event time with effective time.

## 4. Event identity and ingestion-run identity are two separate things

**One source event** must retain a **stable identity** across live, replay, and backfill deliveries. Meanwhile, **each ingestion run/attempt** gets its own operational identifier.

~~~mermaid
flowchart LR
    E["Source event E-007, order-42, v11"] --> LIVE["LIVE receipt"]
    E --> REP1["REPLAY #1 receipt"]
    E --> BACK["BACKFILL #2 receipt"]
    LIVE --> ID["Same business event identity"]
    REP1 --> ID
    BACK --> ID
    ID --> APPLY["One rule-compliant business effect"]
~~~

Example event contract:

~~~json
{
  "eventId": "91fe41a3-4164-4b8f-84e5-c08b9d5abbd0",
  "sourceSystem": "partner-a",
  "aggregateType": "Order",
  "aggregateId": "order-42",
  "sourceVersion": 11,
  "eventType": "OrderStateChanged",
  "state": "PAID",
  "occurredAt": "2026-11-21T03:05:00Z",
  "schemaVersion": 1
}
~~~

Information about the **ingestion pass** lives in a separate envelope/metadata structure:

~~~json
{
  "ingestionMode": "BACKFILL",
  "recoveryRunId": "4c88bcf3-11a8-40b3-b0e1-e85e286cc009",
  "ingestedAt": "2026-11-21T07:00:00Z",
  "sourceSnapshotId": "partner-a-snapshot-20261121",
  "attempt": 2
}
~~~

**Never replace `eventId` or `occurredAt` with fresh values just because you re-ran ingestion.** If the source lacks an `eventId`:

1. Prefer an immutable source-promised key, such as **(sourceSystem, aggregateId, sourceVersion, eventType)** if the contract guarantees uniqueness per combination.
2. For snapshots, identify records by **sourceSystem + businessKey + revision/snapshot watermark**, not by load iteration.
3. Hashing canonical content is only a fallback with limits: two distinct valid events can share identical fields, and schema/format changes alter hashes. Understand the contract before choosing it.

**External operation idempotency keys** (such as a payment charge request) are a different identifier class. Bind them to **business intent**, not to retry attempts or `recoveryRunId`.

## 5. Recovery data does not mean new data

Downstream should clearly distinguish at least five processing outcomes:

| Processing status | Exact meaning | Example |
| --- | --- | --- |
| **FIRST_SEEN_LIVE** | First time the handler sees the event via the live stream | Newly placed order processed immediately |
| **FIRST_SEEN_RECOVERY** | Handler **sees it for the first time**, yet the event occurred in the past | PAID at 10:05, backfilled at 14:00 |
| **ALREADY_SEEN** | Event was already applied/recorded earlier | Replaying the exact same PAID event |
| **STALE_OR_SUPERSEDED** | Event unseen before, yet older version than current state | Replaying v11 when projection is already at v13 |
| **CONFLICT** | Two source records claim the same identity/version with conflicting content | Differing payload for order-42/v11 |

**FIRST_SEEN_RECOVERY is not a "new order" in business reports.** Whether an order is "new" is governed by **event time, identity, and state rules**, not when the row first appeared in the destination database.

If the system emits downstream events from the projection, separate clearly:

- **Business events**: real source events keeping original identity and `eventTime`.
- **Processing/audit events**: operational notices that recovery occurred, such as `BackfillCompleted`; these are new operational events with their own eventIds, never fake new `OrderCreated` events.
- **Derived events**: genuinely new computed events permitted by business rules. Define explicit rules before emitting externally.

Never automatically resend welcome emails, push notifications, payment charges, or fulfillment orders merely because historical events were re-read. For downstream systems needing data reconstruction, provide an **explicit replay contract**, since projection consumers can replay safely while side-effect-producing consumers cannot.

## 6. Two lines of defense: inbox against duplicates and versions against regression

**Deduplication** and **ordering** prevent two distinct failure classes:

- **Inbox/dedup:** the same **eventId** delivered multiple times is never applied more than once.
- **Version guard:** two events with **different IDs** for the same aggregate arrive out of order; an older event cannot overwrite newer state.

With an inbox alone, an unseen `version=11` arriving after `version=13` still looks "new" and can regress state. With version checks alone, two conflicting payloads sharing a version might be silently skipped without leaving an investigation trail.

### 6.1. Illustrative PostgreSQL schema

~~~sql
-- Shared inbox for projection consumers, preventing reprocessing the same event ID.
CREATE TABLE processed_source_event (
    consumer_name    varchar(80)  NOT NULL,
    source_system    varchar(80)  NOT NULL,
    event_id         uuid         NOT NULL,
    aggregate_id     varchar(120) NOT NULL,
    source_version   bigint       NOT NULL,
    first_seen_mode  varchar(16)  NOT NULL,
    first_seen_at    timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, source_system, event_id),
    CONSTRAINT processed_event_mode_check
        CHECK (first_seen_mode IN ('LIVE', 'REPLAY', 'BACKFILL'))
);

-- Projection holding the LATEST state of each order.
CREATE TABLE order_state_projection (
    source_system        varchar(80)  NOT NULL,
    order_id             varchar(120) NOT NULL,
    source_version       bigint       NOT NULL,
    state                varchar(40)  NOT NULL,
    state_occurred_at    timestamptz  NOT NULL,
    last_applied_event_id uuid        NOT NULL,
    updated_at           timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (source_system, order_id)
);

-- Tracks a recovery run; NEVER masquerades as a new order.
CREATE TABLE recovery_run (
    id                  uuid PRIMARY KEY,
    mode                varchar(16) NOT NULL,
    source_system       varchar(80) NOT NULL,
    scope_description   text NOT NULL,
    source_watermark    text,
    state               varchar(20) NOT NULL,
    started_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    CHECK (mode IN ('REPLAY', 'BACKFILL')),
    CHECK (state IN ('PLANNED','RUNNING','PAUSED','FAILED','COMPLETED'))
);
~~~

In production, add indexes, retention, per-record error tracking, and a **source identity contract**. `processed_source_event` can grow rapidly; never purge deduplication history before replay/redelivery windows close or without an alternative idempotency mechanism.

### 6.2. Transactional apply with version checks

Assume the source guarantees **increasing `sourceVersion` per `orderId`**, and each newer version supersedes older state without requiring all intermediate versions to compute current state. The handler below illustrates updating the projection:

~~~java
public record OrderStateChanged(
        UUID eventId, String sourceSystem, String orderId,
        long sourceVersion, String state, Instant occurredAt,
        int schemaVersion) {}

public enum IngestionMode { LIVE, REPLAY, BACKFILL }

public enum ApplyResult { APPLIED, ALREADY_SEEN, STALE }
~~~

~~~java
@Service
public class OrderProjectionUpdater {
    private final JdbcTemplate jdbc;

    public OrderProjectionUpdater(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ApplyResult apply(OrderStateChanged event, IngestionMode mode) {
        if (event.schemaVersion() != 1 || event.sourceVersion() < 0) {
            throw new IllegalArgumentException("Unsupported event contract");
        }

        int inserted = jdbc.update("""
                INSERT INTO processed_source_event
                    (consumer_name, source_system, event_id,
                     aggregate_id, source_version, first_seen_mode)
                VALUES ('order-projection', ?, ?, ?, ?, ?)
                ON CONFLICT (consumer_name, source_system, event_id)
                DO NOTHING
                """,
                event.sourceSystem(), event.eventId(),
                event.orderId(), event.sourceVersion(), mode.name());

        if (inserted == 0) {
            return ApplyResult.ALREADY_SEEN;
        }

        int changed = jdbc.update("""
                INSERT INTO order_state_projection
                    (source_system, order_id, source_version, state,
                     state_occurred_at, last_applied_event_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (source_system, order_id)
                DO UPDATE SET
                    source_version = EXCLUDED.source_version,
                    state = EXCLUDED.state,
                    state_occurred_at = EXCLUDED.state_occurred_at,
                    last_applied_event_id = EXCLUDED.last_applied_event_id,
                    updated_at = now()
                WHERE order_state_projection.source_version
                    < EXCLUDED.source_version
                """,
                event.sourceSystem(), event.orderId(),
                event.sourceVersion(), event.state(),
                Timestamp.from(event.occurredAt()), event.eventId());

        if (changed == 0) {
            // Current state is already at or ahead of sourceVersion.
            // Detect "same version, different payload" conflicts separately
            // per source contract; see Section 6.3.
            return ApplyResult.STALE;
        }
        return ApplyResult.APPLIED;
    }
}
~~~

**Conditions for correctness:** both inbox insert and projection upsert use the **same PostgreSQL DataSource and transaction manager**. Invoke the method through a Spring proxy so `@Transactional` applies, avoiding self-invocation. On rollback, both the dedup marker and projection must roll back; never mark processed when business work fails to commit.

`ON CONFLICT ... DO UPDATE ... WHERE source_version < EXCLUDED.source_version` is an atomic conditional DB update preventing regression under concurrent threads/instances. This implements **last version wins**, not **last arrival wins**. Version determines order, not consumer receipt time.

When `changed == 0`, it is not always an error: `v11` arriving after `v13` is expected. Yet `v11` with conflicting payload against an already applied `v11` is a contract error needing investigation, never silently ignored as stale.

### 6.3. Same version with different data

If each aggregate/version may have only one source state, store a **canonicalized payload hash** or immutable source event record keyed by **(sourceSystem, aggregateId, sourceVersion)**. When a message arrives with a different `eventId` yet the same `sourceVersion`:

1. If content matches per contract, treat as a **duplicate alias**; audit and skip.
2. If payload conflicts, route to a **quarantine/conflict queue**, alert, and reconcile with the source.
3. If the source permits historical corrections, **never** overwrite blindly by arrival time; use an explicit **sourceRevision/correctionId** or bitemporal policy.

To enforce this strictly, add a `source_event_version` table with a unique key and content hash, written inside the same transaction as the inbox/projection. The handler in Section 6.2 demonstrates only a baseline version guard; it **does not implement full conflict detection** and must not blindly skip conflicting messages by `sourceVersion` alone.

## 7. Choosing write semantics by data type: snapshot, event, or ledger

No single **upsert** pattern fits every problem.

| Source data shape | Replay/backfill handling | What to avoid |
| --- | --- | --- |
| **Current-state snapshot** | Upsert by business key and `sourceRevision`/version, checking tombstones | Old snapshot overwriting live state |
| **Superseding state events** | Keep history if needed; update latest projection when version rises | Picking state by receipt timestamp |
| **Additive events** (payments, loyalty points, stock adjustments) | Store each fact by `eventId` then aggregate; apply each fact at most once | Double-counting amounts during replay |
| **Ordered workflow events** (sagas, state machines) | Process sequentially by key, buffer pending when predecessor missing; detect gaps | Skipping intermediate versions when business needs every step |
| **Deleted records** | Honor delete events/tombstones and revisions | Backfilling an old snapshot and "resurrecting" deleted rows |
| **Retroactive corrections** | Explicit correction/revision with audit and deterministic recomputation | Treating retroactive fixes as new orders |

For example, a **current status projection** can skip `v11` and `v12` if `v13` is applied **and `v13` carries all required state**. By contrast, in a **financial ledger** summing transactions, skipping two old events loses money: store each immutable fact with a unique key, then recompute totals or apply unseen facts. **Never copy a latest-state version guard onto an additive ledger.**

When a source lacks reliable versions, fetch a **watermarked snapshot** and stitch subsequent changes via CDC, or buffer live events until the snapshot finishes. Verify snapshot consistency and **gap detection**; simply "sorting by `occurredAt`" does not yield reliable order under clock skew and delayed emissions.

## 8. Replay and backfill while the live stream keeps running

Both streams may write to the same projection. When halting the entire system is infeasible, use a **coordinated live + recovery** strategy.

~~~mermaid
flowchart TD
    SOURCE["Event source"] --> LIVE["Live consumer"]
    ARCHIVE["Archive / historical API / CDC"] --> REC["Replay/Backfill worker"]
    LIVE --> VALIDATE["Validate schema and source identity"]
    REC --> VALIDATE
    VALIDATE --> TX["Shared idempotent handler with version guard"]
    TX --> PROJ[("Projection DB")]
    TX --> AUDIT[("Recovery audit / metrics")]
    PROJ --> CHECK["Reconciliation before closing run"]
~~~

### 8.1. Strategy A: parallel ingestion with conditional updates

For **latest-state** projections where upstream supplies monotonic versions, both live and backfill can call **the same handler** with:

- Unique keys on `eventId`/source identity to stop duplicate processing.
- Conditional SQL updating the projection **only if incoming version is higher**.
- Separate metrics/counts for seen, applied, stale, and conflicting events.
- Zero non-idempotent side effects during recovery.

Advantage: live traffic never stops. Limitation: **does not guarantee executing every intermediate transition in order**, so it suits only domains permitting latest-state semantics.

### 8.2. Strategy B: watermarked snapshot + change stream

When rebuilding large tables or when the source provides CDC:

1. Pick a source **watermark W** (meaningful LSN, offset, sequence, or snapshot token) and capture a consistent snapshot at W.
2. While loading the snapshot, durably buffer or retain changes with **sourcePosition > W**.
3. Load the snapshot into a fresh/staging table or version-guarded projection.
4. Apply post-W changes in required key/order until caught up to the current high watermark.
5. Verify data and then **cut over** read pointers, API-serving tables, or projection versions cleanly.

Never assume `updatedSince=...` or paginated HTTP scans form a consistent snapshot. Partners mutate/delete rows mid-scan, causing **missed** or **duplicated** records. If an API lacks snapshots/CDC, use overlap windows, deduplication, reconciliation, and document consistency limits.

### 8.3. Strategy C: buffer and drain in order

For workflows requiring **every event in order** (not just final state), pause or buffer live updates per aggregate, backfill missing ranges by `sourceVersion`, and release buffers sequentially once gaps close. Track:

- **lastContiguousVersion** applied, distinct from **highestSeenVersion**.
- Missing versions and maximum wait thresholds.
- Memory/queue bounds on pending events.
- Operational workflow when the source can no longer supply a lost version.

If a gap is unrecoverable, never bump `lastContiguousVersion` and pretend data is complete; escalate an incident for exception handling or business reconciliation.

## 9. Detecting and scoping the backfill range

Safe backfills begin by defining the **exact missing scope** and a **reliable recovery source**.

Suppose the source emits time-ordered events and the consumer was down during 10:04–10:12:

~~~text
Suspected gap:  [10:04, 10:12)
Fetch window:   [10:02, 10:14)  -- overlap avoids missing boundary events
Stable ID:      eventId / sourceVersion
Cutoff/snapshot: watermark at recovery start
~~~

Overlap windows help only when the handler deduplicates cleanly. With paginated APIs, check how **cursors** behave under concurrent updates and deletes; `OFFSET/LIMIT` paging on mutating data rarely scans completely. Prefer **cursor/snapshot tokens** or **keyset pagination** on immutable keys/versions whenever supported.

A recovery plan should record:

| Recovery run field | Role |
| --- | --- |
| `runId` and operator/ticket | Audit: who or what job ran it |
| `sourceSystem` + entity/tenant/filter | Scopes impact and protects unrelated data |
| `mode` and source/schema version | Separates replay, backfill, and intentional reprocess |
| `from`/`to` or source offset/LSN | Bounds scope and enables resuming |
| High watermark/snapshot token | Target verification milestone |
| `dryRun`, `batchSize`, `rateLimit` | Controls load and previews impact before writing |
| Counts by outcome | Exposes applied, duplicate, stale, conflict, rejected |
| Checkpoint and retry policy | Resumes the same run without duplicating data |

Restrict operators from running unbounded "beginning of history to now" jobs. Enforce RBAC, date-range caps, mandatory dry-runs, quotas, and alerts when recovery creates heavy load.

## 10. Step-by-step safe recovery procedure

### Step 1. Verify source of truth and contract

Determine which system is authoritative for final values. Multiple sources may exist, requiring clear **precedence and conflict-resolution rules**—never pick "whichever arrived last" blindly. Verify `schemaVersion`, permissions, timezones, `sourceVersion`, delete/correction semantics, and historical retention limits.

### Step 2. Record scope and source watermark

Create a `recovery_run = PLANNED` record storing source/range/cutoff, selected code/rule version, trace, and operator. If the source supports snapshots, save the token so crashes can resume the exact same scope. Otherwise document assumptions and design overlap/reconciliation.

### Step 3. Dry-run and impact assessment

Sample-read or scan metadata to count **candidates**, age distribution, event types, schemas, affected keys, and projected changes. Compare against source totals, estimate DB/HTTP/broker load, and review side-effect risks. A **dry-run** must never create processed markers or trigger side effects; write preview audits to an isolated area if needed.

### Step 4. Execute bounded batches through the same validation logic as live

Transition the run to `RUNNING`; read history page/batch by batch, validate, and pass through the **same domain handler** as live traffic. The handler persists idempotency markers and projections in one DB transaction. Enforce concurrency and rate limits, HTTP timeouts, exponential backoff, DLQ/quarantine, and source load protection.

On crash restart, resume from the **recovery run's cursor/checkpoint**, yet **never rely on checkpoints as the sole deduplication guard**. Keep DB unique keys and version guards active.

### Step 5. Data-level reconciliation

Never declare "recovered" merely because the job threw zero exceptions. Compare:

- **Expected source** event/record counts in scope against received identities and validly rejected records.
- Business keys, versions, tombstones, monetary totals, and contracted statuses.
- Remaining **gaps**, conflicts, schema errors, and records lacking recoverable sources.
- Source high watermark vs. consumer watermark to verify recovery caught up.

### Step 6. Close the run and publish operational status

Mark `COMPLETED` only when reconciliation criteria pass; use `PARTIAL`/`FAILED` if unresolved discrepancies remain (extend the Section 6 schema's CHECK constraint if using `PARTIAL`). Retain counts of applied, duplicate, stale, conflict, rejected, and covered ranges. If needed, emit `RecoveryRunCompleted` as a **new operational event**, never fabricating old business events.

## 11. Spring Boot and Spring Integration: wiring replay/backfill

A practical architecture can look like:

~~~text
Live:       RabbitMQ/Kafka adapter --> validate --> handler --> PostgreSQL
Backfill:   HTTP polling / Batch  --> validate --> handler --> PostgreSQL
Replay:     Event archive reader  --> validate --> handler --> PostgreSQL
                                                   |
                                                   +--> metrics/audit
                                                   +--> optional outbox
~~~

**Principle:** ingestion sources have distinct adapters while **sharing the same business event contract and idempotent handler**. Only tracing/operational metadata like `ingestionMode` and `recoveryRunId` differ.

### 11.1. HTTP clients and paginated history

A recovery HTTP adapter needs:

- APIs supporting **watermark** filters or stable cursors, plus snapshot tokens if offered.
- Per-request timeouts, backoff retries, rate limiting, HTTP 429/503 handling, and contract validation.
- Pre-DB validation, schema evolution handling, and support for **deleted/corrected** records.
- Persisting the cursor **after the batch commits durably**; advancing the cursor before business commits risks skipping records on crashes.

Spring Batch `ItemReader/ItemProcessor/ItemWriter` works well for batch scans, using `JobParameters` for `recoveryRunId`, source watermark, and scope, while `ExecutionContext` holds only technical checkpoints. Keep critical business outcomes and recovery audits in domain/audit tables, as Spring Batch metadata does not replace reconciliation.

### 11.2. Message brokers: replay boundaries

| Broker/mechanism | Historical replay | Notes |
| --- | --- | --- |
| **Kafka topic with sufficient retention** | Consumer groups can seek/read from retained offsets or timestamps | Offsets are not business event IDs; guard commits and side effects |
| **Standard RabbitMQ classic/quorum queue** | Redelivers unacked messages; acked/deleted messages are gone | Needs a dedicated archive/outbox/event store to replay consumed history |
| **RabbitMQ Streams** | Supports retained logs and offset-based reading | Depends on stream type, retention, and client/protocol used |
| **Database outbox / CDC / event archive** | Serves as a replay source while data remains | Preserve original event ID/sequence, schema, and retention |

**Redelivery is not historical replay.** A standard RabbitMQ queue is not a permanent event store, and Spring Integration's **AMQP inbound adapter** cannot re-read acked messages beyond what the broker and history storage retain.

When replaying across a new broker, keep **event identity** in versioned payloads/headers and avoid using deliveryTags, delivery timestamps, or new offsets as business deduplication keys.

### 11.3. Spring Integration adapters and transactions

Flows can distinguish ingestion paths via internal headers like `ingestionMode`, while keeping `sourceSystem/eventId/sourceVersion` mandatory in the contract. Transformers must never accidentally strip or mutate those fields. Over networks, propagate only transport-appropriate headers or embed them inside a well-defined envelope.

`@Transactional` on a JDBC handler protects only DB writes on its transaction manager. It **does not roll back** HTTP calls, Kafka publishes, or RabbitMQ acks. If the projection commits and the consumer dies before acking, the broker redelivers and the **inbox** handles idempotency. If DB updates must emit new events, write to a **Transactional Outbox** in the same DB transaction and publish with confirmations/retries rather than dual-writing directly.

**Caches** like Redis belong purely as optimization/fast-read layers invalidated or refreshed post-DB-commit. Never treat a cache key like "eventId seen" as the sole duplicate guard when losing cache entries would double business effects.

## 12. Avoiding unintended side effects during recovery

Consumers do more than update projections; they may send emails, call payment gateways, award/deduct points, trigger shipments, or notify downstream services. This is where replays are most hazardous.

| Handler | On live events | On replay/backfill events |
| --- | --- | --- |
| **Build projections** | Update by identity/version | Safe to reapply if idempotent |
| **Compute transaction ledgers** | Record fact once by transactionId | Insert only missing facts; reconcile totals |
| **Send emails/SMS** | Per business policy | Never auto-resend; replay only with explicit product requirement |
| **Charge/refund payments** | API with business idempotency key | Never call blindly; query status and reuse original key |
| **Emit downstream integration events** | Via outbox or guaranteed mechanism | Decide whether downstreams need rebuild; prevent duplicate sends |
| **Update caches** | Invalidate/refresh from DB | Rebuild to latest state; never regress |

**Never write a naive rule like "if mode=BACKFILL then skip all side effects"** and assume consistency. A genuinely lost event may **actually need** to trigger a missing business action. Base decisions on **idempotency and the actual state of the target effect**:

1. Did the side effect already happen? Check business keys, outbox/inbox, ledgers, or status lookup APIs.
2. If it never happened, is executing it late still valid? Sending a delivery notice three weeks later may make no sense.
3. If it must execute, reuse the **original idempotency key** and record completion durably.
4. If automated execution is disallowed, route to **manual review/quarantine** or a discrepancy report.

`"recovery mode"` is therefore part of orchestration and auditing context—never a single toggle deciding business truth.

## 13. Failure and recovery matrix

| Failure scenario | What can go wrong | Design safeguard |
| --- | --- | --- |
| Crash after projection commit, before broker ack | Broker redelivers event | Inbox deduplicates; ack only after commit |
| Crash after processing a page, before saving cursor | Page gets re-read | Dedup/business keys; cursor is a progress optimization |
| Cursor saved before DB commit | Uncommitted records can be skipped permanently | Commit data before cursor or in same transaction; reconcile |
| Backfill v11 arrives after live v13 | Projection regresses on blind update | Conditional update guarded by `sourceVersion` |
| Two differing payloads share a version | Conflicting source data | Conflict detection, quarantine, verify with source of truth |
| Deleted record resurrected by old snapshot | Ghost record reappears | Tombstones + revisions; honor deletes |
| Replay additive event into balance | Money credited twice | Ledger keyed by event/transaction ID; skip if applied |
| Schema changed between history and present | Deserialization or calculation fails | Versioned schemas, explicit transforms, quarantine unsupported |
| Source API mutates mid-pagination | Missed or duplicated records | Stable snapshot tokens/cursors, overlap, reconciliation |
| Broker/event archive expired retention | Replay source unavailable | Accept limit; recover from source snapshot/DB if available, report gaps |
| New consumer runs replay and live together | Races and load spikes | Shared idempotent handler, bounded concurrency, backpressure |
| Old event triggers payment/email | Irreversible duplicate side effects | Business idempotency, effect state tracking, recovery workflow |

**Proof of successful recovery** is valid **data invariants**, not HTTP 200s, `Job COMPLETED`, empty queues, or zero exceptions.

## 14. Observability, metrics, and reconciliation

Track metrics by **run, source, and `ingestionMode`**:

| Metric group | Examples |
| --- | --- |
| Volume | candidates, fetched, validated, applied, duplicate, stale, conflict, rejected |
| Progress | currentCursor, sourceHighWatermark, processedHighWatermark, gapCount |
| Latency | processingLag = `ingestedAt − occurredAt`; runDuration, pageFetchLatency |
| Quality | missingKeys, mismatchedVersions, staleSnapshotCount, auditDiscrepancies |
| Resources | DB lock waits, tx rollbacks, HTTP 429/5xx, queue depth, thread pool saturation |
| External effects | outbox backlog, sideEffectAlreadyDone, manuallyReviewed, compensations |

In logs/traces, attach `recoveryRunId, eventId, aggregateId, sourceVersion, attempt` to trace individual records. In Prometheus metrics, avoid putting arbitrary `eventId`/`runId` in high-cardinality labels; label by `source`, `mode`, `result`, and error category while keeping IDs in logs, traces, and audit DBs.

Reconciliation should perform **independent verification**:

- Compare **distinct source event identities**, not raw receipt counts (which include retries).
- Compare state/totals by business key against the source at a defined watermark.
- Check version completeness/gaps against domain rules.
- Cross-check critical effects such as ledger entries, charges, and required emails.
- Produce a clear sign-off record listing discrepancies and the accountable owner.

If unrecoverable gaps remain due to expired source retention, report **incomplete** and escalate to snapshot/manual reconciliation—never mark `COMPLETED` merely because the worker read everything left.

## 15. Testing commonly missed scenarios

In Spring Boot, use real PostgreSQL via **Testcontainers**, HTTP stubs via **MockWebServer/WireMock**, and real brokers in integration tests when verifying acks, offsets, and retries. Key test cases:

1. **Repeating the same event ID:** feed event v11 three times under LIVE, REPLAY, and BACKFILL modes; only one idempotent effect is recorded.
2. **Out-of-order arrival:** apply v13 then v11/v12; projection stays at v13 and `DELIVERED`.
3. **Two-instance race:** concurrently apply v12 and v13; unique keys and conditional SQL preserve the highest version.
4. **Rollback:** inject an error inside the transaction after inserting the inbox; both inbox and projection roll back so retries can run.
5. **Same version, differing payload:** detected as a conflict rather than silently skipped.
6. **Additive ledger:** replay an event with the same `transactionId`; total balance does not increment twice.
7. **Tombstone:** source deletes order at v14; backfilling an older v12 snapshot does not resurrect the deleted order.
8. **Mid-page crash:** process 50 records and kill before saving cursor; restart finishes accurately with zero duplicates.
9. **Backfill during live traffic:** interleave live events with historical ones; verify correctness by `sourceVersion` and load limits.
10. **Retention/missing source:** v12 absent from archive; `recovery_run` reports a gap rather than claiming completeness.
11. **Schema migration:** replay an old `schemaVersion` event against new code; transform or quarantine per policy.
12. **Side effects:** replaying `OrderCreated` never resends completed emails or payment charges; missing ones execute via approved idempotent workflows.

### Illustrative acceptance criteria

For `order-42` with four events v10–v13, when live already updated the projection to **v13/DELIVERED** before recovery delivers v11/v12:

- Final projection keeps **v13/DELIVERED**.
- Historical events preserve original identities and original `occurredAt`; **zero new business `OrderCreated` events appear at backfill runtime**.
- Inbox/audit clearly records what was seen, what applied, and why old events were stale.
- Retrying or crashing and rerunning the same scope **never doubles transactions, notifications, or ledger entries**.
- Recovery closes only once source reconciliation passes and gaps/exceptions meet predefined criteria.

## 16. Safe replay/backfill implementation checklist

- [ ] **Reliable historical source** exists with adequate retention and clear scope/watermarks.
- [ ] **`eventTime`, `ingestedAt`, and `processedAt`** are kept distinct; old records never masquerade as new business events.
- [ ] **Stable event/business identities** stay separate from `recoveryRunId`.
- [ ] **Inbox/dedup** and **version/order checks** match the data semantics (state, ledger, workflow).
- [ ] Tombstones, corrections, `schemaVersion`, and event conflicts follow explicit contracts.
- [ ] Policies cover **concurrent live + recovery**, rate limits, backpressure, retries, and checkpoints.
- [ ] HTTP, email, payment, cache, and broker side effects have dedicated idempotency or recovery rules.
- [ ] Dry-runs, audit trails, per-run states, quarantine, and post-load **reconciliation** are in place.
- [ ] Tests cover crashes, duplicates, out-of-order arrivals, races, gaps, deleted records, and old schema replays.

**Principle to remember:** **Replay and backfill restore facts that already existed in history; re-ingestion time never turns them into brand-new business events.** To recover safely, preserve **source identity and business timestamps**, apply only valid changes per **versions and domain rules**, guard external side effects, and prove completeness through **data reconciliation**.
