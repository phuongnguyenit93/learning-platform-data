# Reconciling State Between Source and Target Systems

## 1. Why is reconciliation needed when sync mechanisms already exist?

In a Spring Boot system integrating HTTP clients, databases, caches, message brokers, and Spring Integration adapters, data is regularly replicated or transformed from a **source system** to a **target system**. For example:

- An order service writes orders to its transactional database and emits **OrderChanged** events.
- A consumer updates the **order_projection** query table in a reporting service.
- A Redis cache holds order status summaries.
- An adapter makes HTTP calls to a shipping system to synchronize orders awaiting delivery.

Even when every component works normally, the two sides can drift due to queued events, unfinished retries, consumer failures, stale-message overwrites, buggy mappers, schema changes, or deletions never emitted as events.

**Reconciliation** is the process of gathering evidence from source and target, comparing them under a shared data contract and observation point, classifying discrepancies, and verifying or executing controlled remediation per policy.

Reconciliation is not simply running **COUNT(*)** on two tables. Two systems can match in row count while differing on an order, an amount, or a status. Conversely, one side having fewer rows for a few seconds may simply be normal sync lag.

### Learning objectives

After this lesson, learners can:

1. Identify the authoritative system and comparison contract for each data field.
2. Choose consistency checkpoints, business keys, versions/sequences, tombstones, and lag handling.
3. Detect **missing, extra, lagging, conflicting, and mismatched-content** records via SQL or paginated reconciliation.
4. Design Spring Boot jobs that are restartable, checkpoint-resumable, and audit-logged.
5. Choose between auto-repair, event replay, compensation, or manual investigation based on business risk.
6. Test and monitor to prove post-repair data matches the authoritative source.

This topic belongs to the **Consistency and Deduplication** section of the **SPRING_BOOT_INTEGRATION** module: eventual consistency and idempotency reduce drift, while reconciliation detects and resolves discrepancies that persist across transactions, retries, and recoveries.

## 2. Before comparing: define which state must be consistent

Suppose the source system stores an order:

~~~text
orderId       = 1042
sourceVersion = 18
status        = CONFIRMED
totalMinor    = 125000
deleted       = false
~~~

The target system may also store **updated_at**, **last_synced_at**, a normalized customer name, or display-only columns. Not every column must match. Define a **projection contract**: which fields must match the source, at which version, and under which transformations.

### 2.1. Choosing the authoritative source

**Source of truth** can be assigned per entity or per field:

| Data | Example authoritative source | Role of target system |
| --- | --- | --- |
| Order status and total amount | Order service | Stores read model for reporting and lookup. |
| Posted account balance | Ledger/payment service | Displays balance; never recomputes from potentially incomplete events. |
| Partner tracking number | Carrier API | Stores a copy for shipment tracking. |
| User permission groups | Directory/LDAP per org policy | TTL cache; never blindly authoritative for final access decisions. |
| Target-side editorial notes | Target system itself | Sync from source must never overwrite target-owned fields. |

If both sides are allowed to edit **the exact same field**, a simple "source wins" rule fails. You need clear ownership, conflict resolution rules, versioning, or an explicit business reconciliation workflow.

### 2.2. Identifying keys must be stable

Reconciliation requires a contracted unique key, such as **(tenantId, orderId)**. Never rely on row order, API page positions, or display names.

Separate three key types:

- **Business key:** identifies the entity, e.g., **(tenantId, orderId)**.
- **Event ID:** identifies a specific event emission to prevent reprocessing, e.g., **eventId=evt-9120**.
- **Source version/sequence:** reflects the entity's mutation order, e.g., **sourceVersion=18**.

Two events with distinct `eventId`s can apply to the same `orderId`; `eventId` does not replace version. When multiple tenants can share an `orderId`, include `tenantId` in keys across source, target, logs, and reconciliation.

### 2.3. Data representation contract

Canonicalize before comparing:

- **Monetary amounts:** use integer minor units paired with currency; never compare floating-point numbers.
- **Timestamps:** standardize timezone, precision, and timestamp semantics. **updated_at** generated independently by two machines is rarely a reliable version proxy.
- **Strings:** define rules for case sensitivity, whitespace, and Unicode normalization; normalize only when business rules allow.
- **Null/absent:** distinguish explicit `null`, omitted fields, empty strings, and defaults if they differ in contract meaning.
- **Collections:** clarify whether lists are ordered or unordered sets; never hash arbitrary JSON when two systems serialize differently.
- **Deletions:** emit delete events or versioned **tombstones** so targets never resurrect deleted records upon replaying older events.

When comparing via **content hashes**, both sides must apply the **exact same canonicalization** over the exact same business fields. Hashing does not resolve mismatched contracts, versions, or unclear authority.

## 3. Distinguishing real drift from sync lag

In an **eventually consistent** system, at the same wall-clock instant, the target can legitimately lag behind the source:

~~~mermaid
sequenceDiagram
    participant S as Source DB
    participant O as Outbox/Broker
    participant D as Target DB
    participant R as Reconciliation job
    S->>S: Commit order 1042 version 18
    S->>O: Publish OrderChanged v18
    R->>S: Read source v18
    R->>D: Read target v17
    Note over R: Temporary lag; check backlog/watermark
    O->>D: Consumer applies v18
    R->>D: Re-check -> MATCH
~~~

If a reconciliation job immediately triggers repairs whenever **v17 ≠ v18**, it creates unnecessary load and races healthy consumers.

Define a **consistency window** or **grace period** aligned with the flow's SLA and inspect progress evidence:

- **Watermark/offset:** how far consumers have safely processed in the source stream.
- **Per-entity version:** latest version applied at the target per entity.
- **Discrepancy age:** how long the mismatch has persisted since source mutation and emission/receipt.
- **Backlog/DLQ:** whether events remain queued, retrying, or quarantined.

**Never assume** source and target timestamps are directly comparable when clocks, timezones, or definitions differ. Prefer system-generated monotonic sequences/offsets and traces from committed events.

### 3.1. Capture points must be comparable

Taking a source snapshot at **T1** and reading the target at **T2** without accounting for mutations between T1 and T2 yields false positives. Three strategies:

| Strategy | Usage | Conditions/limitations |
| --- | --- | --- |
| **Frozen or consistent snapshot** | Use DB/read-replica snapshots or exports at a fixed point. | Understand snapshot boundaries and production load; two separate DBs rarely share one transactional snapshot. |
| **Stream watermark** | Pick a source point, wait for consumers to apply up to it, then compare. | Requires tracking per-partition offsets and handling late events; a bogus global watermark hides gaps. |
| **Per-entity version comparison** | Read `sourceVersion` on both sides, separating target lag from same-version content mismatches. | If records mutate mid-scan, re-read/verify or stage snapshots; version semantics must be explicit. |

Across multiple partitions, a **committed consumer offset** does not prove all downstream side effects committed; ACKs/offsets must follow durable processing. Nor is a source sequence globally contiguous if it increments only **per entity**.

### 3.2. Result classification matrix

| Comparison status | Possible meaning | Initial decision |
| --- | --- | --- |
| **MATCH** | Same key, same version, contracted fields equal. | Record success. |
| **SOURCE_ONLY** | Source has entry; target lacks it. | Check backlog, snapshot scope, and grace period; may need projection creation. |
| **DEST_ONLY** | Target has entry; source lacks it in capture scope. | Check tombstones, tenant filters, retention, and newly created data; never delete immediately. |
| **DEST_BEHIND** | Target `sourceVersion` is lower than source. | Often sync lag; past SLA, investigate lost/stuck events. |
| **DEST_AHEAD** | Target `sourceVersion` exceeds source snapshot. | May be newer live data or wrong source; re-read at consistent checkpoint first. |
| **CONTENT_MISMATCH** | Same version, differing business values. | Likely buggy mapping, out-of-band edit, or data corruption; conditional investigate/repair. |
| **INCOMPARABLE** | Missing version, incompatible mapping, multi-writer ambiguity, or incomplete snapshot. | Halt auto-repair; gather more evidence. |

**DEST_ONLY** can also happen when the source API filters out deleted records while the target retains tombstones. Define deletion semantics before flagging this as an error.

## 4. Forms of reconciliation

### 4.1. Full reconciliation

Scans the entire dataset in scope, comparing by stable keys. Suited for daily/weekly checks, post-incident audits, post-mapper deploys, or proving zero dropped events.

Pros: catches missing records where no event ever existed to announce them. Cons: heavy I/O, runtime, and bandwidth; requires pagination, snapshots/watermarks, throttling, and crash-resumability.

**Never use OFFSET/LIMIT on live mutating tables without a snapshot** when accuracy matters. Use stable keyset pagination or a fixed snapshot to reduce skipped/duplicated rows:

~~~sql
SELECT order_id, source_version, status, total_minor, deleted
FROM orders
WHERE order_id > :lastOrderId
ORDER BY order_id
LIMIT :batchSize;
~~~

This illustrates scanning a dataset **fixed at a checkpoint**; if rows change mid-scan, keyset ensures deterministic cursoring rather than a point-in-time snapshot by itself. For composite keys, use DBMS-supported tuple comparisons or multi-part cursors.

### 4.2. Incremental reconciliation

Examines only records changed since a reliable checkpoint, such as:

- Source CDC/transaction logs.
- Outbox tables with sequences and publish statuses.
- Change-feed APIs providing cursors + versions.
- **updated_at** records if the contract guarantees monotonic precision and captures all changes.

Incremental scans run fast yet can miss **deletes without tombstones**, out-of-band DB changes outside CDC, expired retention events, or bad cursors. Production systems often combine **frequent incremental + periodic full reconciliation**.

Never use **`updated_at > lastRunTime`** alone when commit visibility, timestamp precision, and ties across rows are unhandled—you can drop rows updated on the exact boundary. Use a `(updated_at, id)` cursor with an overlap window and deduplication when no stronger sequence exists, still accounting for clock skew and late commits.

### 4.3. Hash, aggregate, or domain-level reconciliation

To save bandwidth, first compare **COUNT**, monetary sums, min/max versions, or per-partition hashes. These only detect or localize discrepancies:

- Equal counts do not prove matching keys or contents.
- Equal sums can mask two offsetting errors.
- Hashes require identical canonicalization, scopes, and versions.
- Financial reconciliation must follow double-entry/ledger rules, not just projection table snapshots.

When a partition flags an anomaly, run a **row-level diff** by key and version. Never overwrite blindly based on hashes without understanding the difference.

## 5. Example: reconciling an order projection

Suppose **Order Service** owns order status and totals, while **Reporting Service** maintains a read model:

~~~text
Source (Order Service)                 Target (Reporting Service)
order_id  version  status  total       order_id  version  status  total
101       5        PAID     50000      101       5        PAID     50000
102       7        SHIPPED 120000      102       6        PAID    120000
103       3        NEW      30000      (missing)
104       9        PAID     90000      104       9        NEW      90000
                                      105       2        PAID     70000
~~~

Assuming both sets are normalized and captured compatibly:

- **101:** MATCH.
- **102:** DEST_BEHIND; inspect lag or v7 event.
- **103:** SOURCE_ONLY; inspect creation event delivery.
- **104:** CONTENT_MISMATCH at same version; suspect buggy mapping or out-of-band edit.
- **105:** DEST_ONLY; investigate why source lacks the record or tombstone.

### 5.1. Normalizing data into two staging snapshots

When source and target live in separate databases, **you cannot JOIN them directly just because both run Spring Boot**. The job must read via authorized APIs/connections and stage into a controlled store, or compare by streaming keys in the application tier.

PostgreSQL staging example for a reconciliation run:

~~~sql
CREATE TABLE recon_source_snapshot (
    run_id         UUID NOT NULL,
    order_id       BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    status         VARCHAR(32) NOT NULL,
    total_minor    BIGINT NOT NULL,
    deleted        BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, order_id)
);

CREATE TABLE recon_target_snapshot (
    run_id         UUID NOT NULL,
    order_id       BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    status         VARCHAR(32) NOT NULL,
    total_minor    BIGINT NOT NULL,
    deleted        BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, order_id)
);
~~~

**run_id** identifies one scan and enables reproducibility. Staged data must tie to **source watermark, scope, mapping version, and capture time** in the run's metadata. Never share one `run_id` across two incompatible capture points and treat every difference as a bug.

The model uses a **tombstone** (`deleted=true` with incrementing `source_version`) for deleted rows. Absence from a source API that hides deleted rows is insufficient proof of deletion.

### 5.2. Discrepancy classification query

After collecting **both consistent snapshots per contract**, run:

~~~sql
WITH s AS (
    SELECT order_id, source_version, status, total_minor, deleted
    FROM recon_source_snapshot
    WHERE run_id = :runId
),
d AS (
    SELECT order_id, source_version, status, total_minor, deleted
    FROM recon_target_snapshot
    WHERE run_id = :runId
)
SELECT
    COALESCE(s.order_id, d.order_id) AS order_id,
    s.source_version AS expected_version,
    d.source_version AS actual_version,
    CASE
        WHEN s.order_id IS NULL THEN 'DEST_ONLY'
        WHEN d.order_id IS NULL THEN 'SOURCE_ONLY'
        WHEN d.source_version < s.source_version THEN 'DEST_BEHIND'
        WHEN d.source_version > s.source_version THEN 'DEST_AHEAD'
        WHEN s.status IS DISTINCT FROM d.status
          OR s.total_minor IS DISTINCT FROM d.total_minor
          OR s.deleted IS DISTINCT FROM d.deleted
        THEN 'CONTENT_MISMATCH'
        ELSE 'MATCH'
    END AS outcome
FROM s
FULL OUTER JOIN d
    ON s.order_id = d.order_id
ORDER BY order_id;
~~~

Both CTEs **s** and **d** filter `run_id` prior to joining. Filtering **`s.run_id = :runId AND d.run_id = :runId`** inside a trailing `WHERE` clause after `FULL OUTER JOIN` would accidentally drop one-sided rows.

PostgreSQL's **IS DISTINCT FROM** compares safely with NULLs so missing values are never overlooked. For other databases, use an equivalent null-safe comparison.

These SQL rows are **technical discrepancy candidates**. Before issuing repairs, evaluate age, watermarks, retention/tombstones, consumer lag, and authoritative-source rules.

### 5.3. Recording reconciliation history for auditing

Each run should record at minimum:

| Field | Meaning |
| --- | --- |
| **run_id, job_version** | Run identifier and algorithm/contract version. |
| **scope, source_watermark** | Tenant/partition/key scope and source checkpoint. |
| **started_at, completed_at, status** | Timestamps and status; distinguish RUNNING/PARTIAL/COMPLETED/FAILED. |
| **last_key, batch_number** | Resume checkpoint for large scans. |
| **counts_by_outcome** | Counts of MATCH, SOURCE_ONLY, DEST_ONLY, LAGGING, MISMATCH, INCOMPARABLE. |
| **finding_id, order_id, versions** | Per-mismatch evidence with minimized/hashed sensitive fields. |
| **repair_action, result, verified_at** | Repair decision, outcome, read-back verification, and approver if required. |

Never mark a `PARTIAL` scan as completed simply because the scanned subset all matched. An incomplete scan cannot certify full-system consistency.

## 6. Designing Spring Boot and Spring Integration jobs

A clean architecture can include:

~~~mermaid
flowchart LR
    A[Scheduler / Spring Integration poller] --> B[Reconciliation coordinator]
    B --> C[Source API / JDBC]
    B --> D[Target API / JDBC]
    C --> E[Normalize + compare by business key]
    D --> E
    E --> F[(Run + finding store)]
    F --> G{Repair policy}
    G -->|Safe, automatic| H[Idempotent repair / replay]
    G -->|Ambiguous, high-risk| I[Quarantine + investigation]
    H --> J[Read-back verification]
    I --> J
~~~

**Schedulers**, **`@Scheduled`**, or Spring Integration pollers merely trigger execution. Correctness stems from the data and rules underneath, not the trigger choice.

### 6.1. Resumable paginated collection

The job reads a fixed scope:

1. Create `run_id` with metadata: source watermark, scope, and contract version.
2. Fetch a source batch via stable keyset/cursor. Fetch target state for those keys, or collect an independent target snapshot to detect **DEST_ONLY** as well.
3. Canonicalize records; compare version and content per contract.
4. Persist findings and checkpoint durably; advance checkpoint only after batch findings commit.
5. Continue from cursor; finish only after scanning the full scope with zero gaps.
6. Re-check findings after the grace period and act per repair policy.

If **checkpoint saves before findings** and the process dies, records may be skipped. If findings save before the checkpoint, the batch reruns; enforce unique constraints like `(run_id, order_id)` and idempotent upserts so nothing duplicates.

Never hold a single JDBC transaction open across thousands of HTTP calls. Keep finding/checkpoint batch transactions short with isolated retries. Never assume `@Transactional` on a Spring Boot service coordinates source DB, HTTP, and broker together.

### 6.2. Separating detection from remediation

Reconciliation can start in **detect-only** mode. Findings should be re-verified before executing repairs because source or target may have changed since the scan:

~~~text
DETECTED -> CONFIRMED -> APPROVED -> APPLYING -> VERIFIED
                          |                |
                          v                v
                       DEFERRED         FAILED/RETRY
~~~

Each finding records the observed expected and actual versions. Repairs must re-read and enforce **compare-and-set** so a repair never overwrites a newer target record.

### 6.3. Target upsert example that never overwrites newer versions

In PostgreSQL, the target table stores the applied source version:

~~~sql
CREATE TABLE order_projection (
    order_id       BIGINT PRIMARY KEY,
    source_version BIGINT NOT NULL,
    status         VARCHAR(32) NOT NULL,
    total_minor    BIGINT NOT NULL,
    deleted        BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Applying a verified source repair:

~~~sql
INSERT INTO order_projection
    (order_id, source_version, status, total_minor, deleted)
VALUES
    (:orderId, :sourceVersion, :status, :totalMinor, :deleted)
ON CONFLICT (order_id) DO UPDATE
SET source_version = EXCLUDED.source_version,
    status = EXCLUDED.status,
    total_minor = EXCLUDED.total_minor,
    deleted = EXCLUDED.deleted
WHERE order_projection.source_version < EXCLUDED.source_version;
~~~

`source_version < EXCLUDED.source_version` allows advancing stale rows without ever regressing newer ones. On same-version differing content, this statement leaves the row untouched; classify it as `CONTENT_MISMATCH` for investigation, or apply a dedicated remediation guarded by expected version and authoritative source evidence. Blindly using `>=` to overwrite the same version masks mapping bugs.

Tombstones carry versions too: applying a delete at version 20 sets `deleted=true` and `source_version=20`. Replaying an update at version 19 cannot resurrect the record.

### 6.4. Example discrepancy-detection and conditional-repair service

Illustrative Java core decision logic, assuming `SourceGateway` returns state at the requested checkpoint and `TargetRepository` runs the version-guarded SQL above:

~~~java
record OrderState(
        long orderId,
        long sourceVersion,
        String status,
        long totalMinor,
        boolean deleted) {}

enum Outcome {
    MATCH, DEST_BEHIND, DEST_AHEAD,
    SOURCE_ONLY, CONTENT_MISMATCH, INCOMPARABLE
}

@Service
class OrderReconciliationService {
    private final SourceGateway source;
    private final TargetRepository target;

    OrderReconciliationService(SourceGateway source,
                               TargetRepository target) {
        this.source = source;
        this.target = target;
    }

    Outcome compare(long orderId, long watermark) {
        // Gateway returns only valid snapshot/watermarked data
        // including tombstones; nulls must be classified explicitly.
        OrderState expected = source.findAt(orderId, watermark);
        OrderState actual = target.find(orderId);

        if (expected == null) {
            return Outcome.INCOMPARABLE;
        }
        if (actual == null) {
            return Outcome.SOURCE_ONLY;
        }
        if (actual.sourceVersion() < expected.sourceVersion()) {
            return Outcome.DEST_BEHIND;
        }
        if (actual.sourceVersion() > expected.sourceVersion()) {
            return Outcome.DEST_AHEAD;
        }

        boolean samePayload =
                actual.deleted() == expected.deleted()
                && actual.totalMinor() == expected.totalMinor()
                && actual.status().equals(expected.status());

        return samePayload
                ? Outcome.MATCH
                : Outcome.CONTENT_MISMATCH;
    }
}
~~~

`SourceGateway` and `TargetRepository` are application abstractions, not built-in Spring classes; implement them with HTTP clients, `JdbcTemplate`, or adapters. This example focuses on **comparison rules** without repair execution or full-range `DEST_ONLY` detection (which requires scanning the target set too).

In real systems, preserve `tenantId`, distinguish HTTP/DB errors from absent records, reject invalid nulls, and read consistently at a checkpoint. A single lookup by `orderId` does not guarantee a stable snapshot while live events continue arriving.

For `DEST_BEHIND` past SLA with verified source data, a worker can apply a version-guarded upsert and then **read back** from the target to confirm state. If 0 rows updated, another consumer/worker may have applied an equal or newer version concurrently; read back and reclassify instead of falsely reporting repaired.

## 7. Repairing discrepancies: prioritize evidence and idempotency

Not every finding should be "fixed" by copying the source row over the target.

| Outcome | Action after verification | When manual intervention is needed |
| --- | --- | --- |
| **DEST_BEHIND** within SLA | Wait for consumer, monitor backlog, and re-read. | Lag breaches SLA, DLQ, or event passed retention. |
| **DEST_BEHIND** past SLA | Replay events in version order or upsert projection from authoritative source. | Target has local edits, irreversible side effects, or lacks source version. |
| **SOURCE_ONLY** | Check creation event and scope; create projection via idempotent upsert if eligible. | Unclear whether pending or intentionally filtered by permissions. |
| **DEST_ONLY** | Check tombstones, deletion logs, scope, and retention; mark deleted via authoritative version if proven. | Cannot prove source deleted it; avoid hard-deleting immediately. |
| **CONTENT_MISMATCH** same version | Inspect mappers, schemas, normalization, and commit evidence; repair with expected-version guard once confirmed. | Financial records, multi-writer ambiguity, suspected app logic bug. |
| **DEST_AHEAD/INCOMPARABLE** | Re-read with matching checkpoint and contract; defer. | Ownership conflict, missing metadata, or indeterminate truth. |

### 7.1. Replay events or rebuild the projection?

**Replay** works when event logs are durable, retention suffices, ordering/versioning exists, and consumers are idempotent. To rebuild an entire read model, populate a new projection table from a source snapshot and catch up on delta events before switching read traffic.

**Rebuilds** must never drop a live production projection before the replacement is verified. Use snapshot + CDC/outbox catch-up, reconcile counts/keys/versions, then switch reads cleanly.

If current source state has moved past an older event's point in time, replaying non-idempotent delta events may not reconstruct intermediate steps cleanly. Events like **"add 10 points"** need strict `eventId` deduplication and ordering; where contracts permit, syncing final-state snapshots for read models is simpler to repair.

### 7.2. Avoiding race conditions during repair

Suppose the job sees target at version 6 and source at version 7. Before repair writes, the live consumer advances the target to version 8. An unconditional `UPDATE` would overwrite version 8 back to version 7.

Therefore:

- Guard writes with `sourceVersion` or DB compare-and-set.
- When fixing same-version content mismatches, check **expected old state/hash** and write an audit entry.
- Never treat an HTTP 200 as proof the target matches; read back or confirm commit evidence.
- Every repair command carries an **idempotency key**, finding/run ID, and trace/correlation ID.
- Enforce rate limits, batching, backoff, and a **kill switch** to halt repairs if mismatch rates spike abnormally.

### 7.3. When repairs trigger external side effects

Updating a projection or cache is repeatable; calling **refund**, creating a shipment, sending an email, or posting a ledger entry creates real-world effects. Never "replay everything" as if side effects were freely reversible. Inspect third-party state first, use idempotency keys, or follow approved compensating workflows.

For sensitive data and financial reporting, enforce **quarantine + human approval** before remediating. Every repair must record before/after evidence, actor/system, and how to recover if a repair itself was wrong.

## 8. Relationship to retries, deduplication, outboxes, and transactions

Reconciliation complements upstream consistency mechanisms:

**Idempotent consumers.** Events can redeliver after broker failures. Persist `(consumerName, eventId)` or an equivalent business constraint inside the same DB transaction as business updates. This blocks duplicate processing, yet cannot prove no event was ever missed.

**Transactional outbox.** The source database updates business state and records publish intent in one transaction. Relays publish with retries, typically yielding **at-least-once** delivery. Reconciliation catches events stuck in the outbox or projections that diverged from the source.

**Inboxes and checkpoints.** Persist incoming payloads/processed markers before ACKing when contracts require. Checkpoints/offsets must reflect committed work, not merely read positions. Reconciliation can verify whether accepted `eventId`s actually finished processing.

**JTA/XA.** Can coordinate atomic commits across genuine XA-enlisted resources, yet does not cover arbitrary HTTP/cache side effects nor prevent business bugs, bad mappers, or out-of-band edits. Reconciliation remains valuable.

**Caches.** Caches drift from databases due to TTLs, missed invalidations, or races. Enforce **database authoritative** rules, cache versioning/TTLs, and refresh logic; minor cache drift may be acceptable without per-entry reconciliation if eventual invalidation suffices.

**Spring Integration flows.** HTTP inbound adapters, JDBC outbound adapters, message channels, pollers, and aggregators introduce varied transaction boundaries and staging buffers. Reconciliation orchestration must know where durable work lives and where restarts can retry or duplicate.

~~~mermaid
flowchart TD
    A[(Source DB)] --> B[(Outbox)]
    B --> C[(Broker)]
    C --> D[Idempotent consumer]
    D --> E[(Target DB)]
    A --> F[Reconciliation]
    E --> F
    C --> G[Backlog / DLQ metrics]
    G --> F
    F --> H{Finding}
    H -->|Normal lag| I[Monitor / re-read]
    H -->|Confirmed drift| J[Conditional repair]
    H -->|Ambiguous| K[Investigate]
    J --> E
~~~

An important operational rule: **repairs must never create a "secret" backdoor bypassing invariants and audits**. Route fixes through the same domain service or a guarded data-access boundary with equivalent version checks and logging.

## 9. Testing reconciliation and recovery

Tests should use realistic databases, brokers, or stubs matching production flows, with deterministic `eventId`s and versions. Mocking only comparison functions misses checkpoint bugs, unique constraint issues, and commit-order races.

| Scenario | Expected outcome |
| --- | --- |
| Same key, version, and payload on both sides | MATCH; zero repairs issued. |
| Equal row counts with one swapped key | Detects SOURCE_ONLY and DEST_ONLY; not fooled by COUNT. |
| Target v7, source v8, consumer has active backlog | DEST_BEHIND within grace period; no premature repair. |
| Target v7, source v8, backlog empty and drift past SLA | Verified finding; version-guarded repair/replay; readback confirms. |
| Target v8 differs in status from source v8 | CONTENT_MISMATCH; no uncontrolled overwrite. |
| Job repairing v8 while target advances to v9 | Guard blocks overwriting v9; job re-reads and reclassifies. |
| Source deletes via tombstone v10, stale v9 update replays | Target remains `deleted=true`, version 10. |
| Two jobs run same scope or crash between findings and checkpoint | No duplicate findings/repairs; job resumes without skipping batches. |
| Source API errors, times out, or returns partial page | Run marked PARTIAL/FAILED; missing pages never treated as deleted. |
| Old events dropped from stream due to retention | Incremental misses them; full reconciliation catches drift. |
| Mapping bugs in currency, timezone, nulls, or multi-value fields | Caught pre/post canonicalization; never masked by inconsistent hashes. |
| Multiple tenants sharing `orderId` or multiple partitions | Matched by full scoped key; per-partition watermarks kept separate. |
| Repair writes DB successfully then response times out | Retry with same idempotency key causes no duplicate mutation; readback confirms. |

### Fault injection for jobs

1. Seed source and target datasets covering **MATCH, SOURCE_ONLY, DEST_ONLY, BEHIND, AHEAD, CONTENT_MISMATCH**, including tombstones.
2. Run a partial scan, kill the process after saving findings yet before updating the checkpoint; restart and verify zero skipped or duplicated batches.
3. Stop after repair commits yet before marking **VERIFIED**; rerun and verify idempotency.
4. Have live consumers mutate target rows concurrently to trigger races and verify compare-and-set.
5. Take down the broker/source API, trigger timeouts and DLQs, then recover; confirm `PARTIAL` runs stay distinct from completed runs.
6. Re-reconcile all keys at a consistent watermark once streams catch up.

Never test only happy paths on frozen data: the hardest bugs happen when source, target, and repair jobs run concurrently.

## 10. Monitoring reconciliation in production

Metrics to track:

| Metric | Meaning |
| --- | --- |
| **last_successful_full_reconcile_at** | Most recent full scan completing the full scope and checkpoint. |
| **reconcile_duration / scanned_keys** | Runtime, scanned record count, and progress. |
| **mismatch_count_by_type** | Breakdown across missing, extra, behind, ahead, content mismatch. |
| **mismatch_age / stale_version_lag** | Age and severity of drift; separates brief lag from persistent bugs. |
| **repair_attempt / repair_success / repair_failure** | Effectiveness and risk of repair actions. |
| **unverified_repairs** | Repairs issued that have not yet passed read-back verification. |
| **source_api_errors / target_db_errors** | Reliability of data collection steps. |
| **broker_backlog / consumer_lag / DLQ** | Operational context behind drift. |
| **run_partial / checkpoint_age** | Stalled jobs unable to complete their scope. |

Tag each finding with `runId, tenantId, businessKey, sourceVersion, targetVersion, source watermark, correlationId, classification`. Avoid logging full payloads with personal data or secrets; store minimal fingerprints/evidence under appropriate access controls.

Alert on **mismatch age**, anomalous counts, error rates relative to scanned totals, and business thresholds; alerting on instantaneous **COUNT differences** floods teams with noise in eventually consistent systems.

### Example SLO and intervention policy

A read model might set an SLO of **99.9% of orders synced within 5 minutes** of source commit. This is purely an illustrative threshold; real numbers depend on business criticality and system capacity.

- Within 5 minutes, log `DEST_BEHIND` without auto-repairing.
- Past threshold, inspect consumer lag, outbox, DLQ, and version progression.
- If mismatches persist or spike sharply, pause risky auto-repairs and investigate.
- Once repaired, measure **time to VERIFIED**, not just when the update call was sent.

## 11. Runbook when two systems diverge

1. **Scope it:** entity, tenant, business key, authoritative source, data contract, and current versions.
2. **Capture evidence:** source/target snapshots or watermarks, consumer offsets, outbox, DLQ, logs, and change timestamps.
3. **Classify:** missing, extra, behind, ahead, same-version mismatch, incomparable; check grace periods and lag.
4. **Find root cause:** lost/stuck events, missed retries, premature checkpoint/ACK, buggy schema mapper, out-of-band edits, missing deletion tombstones, or API errors.
5. **Choose remediation:** wait for catch-up, idempotent replay, backfill/projection rebuild, CAS-guarded repair, or manual investigation when authority is ambiguous.
6. **Execute boundedly:** run in batches with rate limits, audit logs, circuit/kill switches, race monitoring, and checkpoints.
7. **Verify:** re-read both sides under the same contract/checkpoint, verify keys and versions, and mark `VERIFIED` once invariants hold.
8. **Prevent recurrence:** fix outbox/consumer/filter/checkpoint bugs, add fault-injection tests, and tune SLOs/monitoring.

### Mistakes to avoid

- Comparing only row counts or totals and concluding both systems agree.
- Reading two snapshots from different timestamps without accounting for watermarks and sync lag.
- Using `updated_at` across multiple servers as an absolute sequence.
- Immediately deleting `DEST_ONLY` rows without verifying source deletions, retention, scope, and tombstones.
- Overwriting higher versions with lower versions due to missing compare-and-set predicates.
- Using `eventId` as the entity key or treating one `eventId` as an order's entire history.
- Committing checkpoints before persisting reconciliation findings, skipping data after a crash.
- Running parallel repair jobs without locks/guards and audit trails.
- Treating HTTP 200, publish ACKs, or single DB commits as proof both sides now match.
- Replaying external financial/shipping side effects without idempotency or compensation controls.

## 12. Key takeaways

**State reconciliation is an independent verification loop for eventual consistency.** A sound design identifies **who owns the data**, **which keys/versions/contracts define equality**, **whether source and target checkpoints align**, and **whether drift exceeded allowed lag**. Jobs can then detect missing, extra, lagging, or mismatched records without mistaking normal in-flight sync for corruption.

Reconciliation finishes only when findings are durably traced, repaired via **idempotent and conditional operations**, and **verified via read-back** against the target. Combining periodic reconciliation with outbox/inbox, idempotent consumers, durable checkpoints, DLQs, and integration observability helps Spring Boot recover even from discrepancies that individual retries or local transactions cannot resolve alone.
