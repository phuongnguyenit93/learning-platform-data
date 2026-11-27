# Data Synchronization During Parallel Run

## 1. Context and Goals

When migrating or modernizing an application to the cloud, it is rarely possible to shut down the entire legacy system, copy data once, and switch on the new system without impacting users. A **parallel run / coexistence** phase is usually required: the legacy system continues handling business operations while the new system is seeded with data, tested, and gradually receives traffic.

For example, an e-commerce platform is migrating from a monolith using a data center database to an order service deployed in the cloud. For weeks, new orders and status updates continue occurring in the legacy system; the new system must read fresh enough data to test, reconcile, and eventually take over. Copying all data once at the start leaves the two sides out of sync immediately after the very next write.

A sound synchronization design must simultaneously satisfy five architectural requirement groups:

- **Reliability:** zero lost records, no double-applying a change in ways that cause side effects, and a recovery path on link drops.
- **Security:** data transmitted and stored under least privilege, proper encryption, and controls over sensitive data in logs and test environments.
- **Scalability:** ingestion and change processing keep pace with write throughput, including peak hours.
- **Cost:** controlling parallel-run infrastructure, data transfer, log retention, and staging storage costs.
- **Operations:** visibility into lag, drift, error locations, cutover criteria, and rollback capability.

After this lesson, learners can select an appropriate sync model, design a *snapshot + change data capture* pipeline, define reconciliation criteria, establish *cutover/rollback* conditions, and evaluate choices through a **Well-Architected** lens.

## 2. Understanding “Synchronization” During Parallel Run

### 2.1. Distinguishing Key Concepts

| Concept | Meaning | Design Question to Answer |
| --- | --- | --- |
| *Initial load / snapshot* | Loading baseline data state from source to target. | Consistent snapshot at which exact point? |
| *Change data capture* (CDC) | Capturing changes generated after or during the initial load, typically from transaction logs. | How do you avoid gaps between the snapshot and CDC? |
| *Replication* | Continuous change copying; may operate at database, table, or event level. | What are the direction, lag, and change-application semantics? |
| *Dual write* | One business operation attempting to write to two systems. | What happens if only one side succeeds? |
| *Shadow read / shadow traffic* | Sending read traffic or test requests to the new system without using its output for business decisions. | How do you compare results safely without side effects? |
| *Cutover* | Transferring primary processing or write authority to the new system. | Which mechanism guards the authority handoff point? |
| *Rollback / failback* | Returning processing authority to the old system after cutover. | Can newly written data return completely to the old system? |

**Synchronization does not mean two databases are identical at every instant.** With asynchronous pipelines, the target may lag the source by several seconds—or longer during incidents. Predefine acceptable lag, which data demands strong consistency, and which system is permitted to accept writes.

### 2.2. Data Ownership Boundaries Come First

In most migrations, the easiest model to control is **one authoritative write source per entity or business domain at any point in time** (*single write authority*). For example:

- Before cutover, the legacy system owns order creation and status changes; the new system receives a read-only replica.
- During canary, write authority may shift for a clearly partitioned tenant group or data domain; each individual order still has **one** write owner.
- After cutover, the new system owns writes; legacy write paths are blocked or routed to the new system.

If both systems are allowed to write the same entity, the architecture must resolve conflicts, ordering, logical locks, and reconciliation rules. Turning on bidirectional replication alone does not create consistency.

**Note:** ownership can differ across data domains. For instance, orders may have moved to the new system while reference customer data remains managed by the legacy system via API or a synced replica.

## 3. Synchronization Models and Trade-Offs

| Model | When Appropriate | Strengths | Risks and Limits |
| --- | --- | --- | --- |
| One-way DB replication / CDC | Migrating databases or building read replicas; clear single writer. | Minimal app code changes; captures insert/update/delete via logs. | Sync lag; relies on logs, access permissions, and schema/type compatibility. |
| Periodic snapshot or batch ETL | Infrequently changing reference data, reports tolerating lag. | Simple operations, easy transformations. | Large freshness gaps; poorly suited to near-real-time transactions. |
| Business events via outbox | Incremental service extraction; broadcasting meaningful business changes. | Reduces DB schema coupling; supports multiple consumers. | Must manage event schemas, replay, idempotency, and outbox lifecycle. |
| API-based sync | Source disallows transaction log reads or exposes only business interfaces. | Preserves source access rules and authorization. | Rate limits, pagination, versioning/ETags, hard to capture every update/delete. |
| Direct app-level dual write | Narrow cases where neither events nor CDC are feasible. | Updates both close to request time. | Split-brain when one fails; hard rollback; rarely recommended as default. |
| Bidirectional / active-active sync | Explicit business requirement for multiple independent write sites. | Can remove single-writer dependency. | Conflicts, update loops, network partitions, cross-region ordering, high complexity. |

For typical OLTP migrations, **consistent snapshot + one-way CDC + single write owner** is usually a solid starting point. When extracting microservices, a *transactional outbox* propagates business changes without writing directly to the target database in the same request.

### Why Direct Dual Write Breaks Easily

Suppose an API writes an order to A and then to B:

1. Write to A succeeds, B times out. The client does not know whether B saved it.
2. API retries; B may receive duplicate commands, and A may trigger extra side effects.
3. Without a distributed transaction across both systems, “succeeds in both” is not guaranteed by two sequential calls.

A safer alternative is **writing business data and an outbox record in the same transaction on the owning system**, then letting an event publisher forward it. Target consumers process idempotently. An outbox ensures the event record commits alongside source data, yet **does not guarantee exactly-once delivery across every layer**: networks and brokers can still deliver duplicates.

## 4. Reference Architecture: Snapshot Combined with CDC

~~~mermaid
flowchart LR
    U[User / API] --> R[Traffic router]
    R -->|Before cutover: writes| O[Legacy application]
    O --> DB1[(Source DB)]
    DB1 -->|Consistent snapshot| L[Initial load pipeline]
    DB1 -->|Transaction log / CDC| C[Change pipeline]
    L --> A[Transform & idempotent apply]
    C --> A
    A --> DB2[(Target DB in cloud)]
    DB1 --> V[Reconcile at consistency point]
    DB2 --> V
    R -.->|Shadow read / controlled canary| N[New application]
    N --> DB2
    C --> M[Metrics, alerts, DLQ]
    A --> M
    V --> M
~~~

In this diagram, primary writes still go through the legacy system until cutover. The data pipeline consists of two paths that **must coordinate via a determinable change position**:

1. **Prepare source:** inventory tables, primary keys, relationships, transaction logs, deletion behavior, permissions, volume, and write rate; anchor the CDC start point to the snapshot.
2. **Capture consistent snapshot:** extract baseline data using a snapshot transaction or equivalent consistency guarantee. For large datasets, chunk by stable keys; never assume separate independent queries read a single point in time.
3. **Record change position:** capture LSN, binlog position, resume token, or platform cursor. Anchoring depends on the engine; never rely solely on wall-clock timestamps as proof every change was read.
4. **Load target:** map data types, keys, and constraints; support safe retries without overwriting newer event states.
5. **Replay changes:** apply all inserts/updates/deletes from the chosen position, including changes that occurred while the snapshot ran; deduplicate and preserve appropriate ordering.
6. **Catch up with source:** monitor backlog and end-to-end lag until steady; begin reconciliation and shadow reads.

Two common implementations are: (a) a CDC tool offering integrated snapshot + streaming with coordinated checkpoints, or (b) a custom pipeline combining a consistent snapshot with tightly managed watermarks. If custom-built, prove zero *gaps* between phases and ensure older events cannot overwrite newer state.

### Separating Data Migration from Model Changes

When the new system uses a different schema, build an explicit transformation layer:

- Convert types, time zones, monetary precision, encodings, nullability, and identifiers.
- Normalize data before enforcing new constraints; report invalid values rather than silently dropping rows.
- Version mappings/schemas because both apps may deploy new releases during parallel run.
- Use **expand → migrate → contract**: expand schema so old and new code both understand it, migrate and verify, and drop legacy fields only when zero consumers depend on them.

For instance, an old string status column might split into a canonical status code and an updated timestamp on target. Byte-for-byte table comparison is then insufficient; compare according to **equivalent business rules**.

## 5. Ensuring Correctness of Every Change

### 5.1. Idempotency, Ordering, and Transactions

CDC/brokers are usually designed for *at-least-once* delivery: the same event can be replayed after a consumer crash, timeout, or checkpoint failure. The target must handle duplicates safely.

Each change should carry an event ID, entity ID, appropriate version or sequence, operation type, and stream position. A consumer can apply logic such as:

~~~text
receive change(event_id, entity_id, entity_version, operation, payload, stream_position)

BEGIN TRANSACTION on target system
  if event_id has already been processed:
      skip data mutation
  else:
      read stored version of entity_id (including tombstone if deleted)
      if entity_version is newer than stored version:
          if operation = DELETE: write tombstone with new version
          if operation = UPSERT: apply payload and new version
      mark event_id as processed
  update checkpoint only for contiguous, partition-accurate stream segment
COMMIT
~~~

This is **pseudocode**, not a ready-made library. Critically, business data, deduplication markers, and checkpoints (if stored in the same store/transaction) must remain consistent. If checkpoints live in another system, design safe crash recovery and reprocessing. Versions must increase monotonically **per entity**; never compare sequences across independent partitions or sources.

Test scenarios to verify:

- **Duplicate events:** receiving the same event twice leaves state unchanged on the second pass.
- **Out-of-order delivery:** UPDATE version 8 arrives before version 7; version 7 must not overwrite version 8.
- **Delete then recreate:** physical deletion without versions/tombstones lets a late UPDATE resurrect deleted records.
- **Multi-table single transaction:** a source transaction modifies order and order_item; target must not expose half-applied state if business reads require atomicity.
- **External side effects:** emails, payments, and inventory adjustments must never fire merely because historical events are replayed.

### 5.2. Choosing Consistency Levels by Business Need

| Data / Operation | Consistency Typically Required | Recommended Design |
| --- | --- | --- |
| Order placement, payment capture, inventory holds | Must decide on authoritative state; avoid two sites committing conflicting transactions. | Route writes through one owner; cross-service flows use explicit API/transaction orchestration or sagas with compensation. |
| Order search, operational dashboards | Can tolerate a few seconds of lag per SLO. | CDC replica, lag metrics, display data-freshness timestamp. |
| Product catalog, low-churn config | Can tolerate longer lag depending on risk. | CDC or periodic versioned sync. |
| Accounting reports, revenue reconciliation | Requires completeness and repeatability at cutoff points. | Watermarks, snapshots, or accounting period windows; verify totals and detail rows. |

Never use an asynchronous replica as the decision source for critical transactions if business rules require reading the latest committed state from the write owner.

### 5.3. Resolving Conflicts If Bidirectional Writes Are Unavoidable

Before accepting a bidirectional architecture, define: who owns each field; conflict-detection keys; duplicate or echo-loop suppression; detection window; and who adjudicates unresolvable conflicts. Common policies include:

- **Partitioned write ownership:** tenant/aggregate A writes only in region 1, B only in region 2 — preferred when feasible.
- **Conditional versioning:** updates succeed only when version/ETag matches.
- **Business-rule reconciliation:** e.g., payment status comes from the authoritative ledger; never merge arbitrary fields blindly.
- **Last-write-wins:** simple, yet prone to silent lost updates under clock skew or concurrent writes; unsuitable as a default for financial data.

If you cannot prove conflict-handling rules, return to a single write owner and route commands through it.

## 6. Latency, Throughput Capacity, and Failure Points

Sync latency is more than broker queue time. A useful measurement spans from source transaction **commit** until the change is applied and readable on target. Track median, p95/p99, and maximum lag per table/partition.

Suppose the source averages 200 changes/sec and the pipeline sustains 500 changes/sec. After a 10-minute outage, the backlog reaches roughly **120,000 changes**. While the source keeps writing 200 changes/sec, net catch-up capacity is 500 − 200 = **300 changes/sec**, requiring around **400 seconds** to drain the backlog if rates stay steady with no other bottlenecks. When processing capacity is less than or equal to the generation rate, the backlog never drains on its own.

Common bottlenecks include insufficient transaction log retention, unstable hybrid links, CPU-heavy schema transforms, throttled target writes, tables lacking primary keys, and skewed partitions. Adding consumers does not always help if ordering per key must be preserved or target throughput is capped.

**Capacity planning** should cover peak write rates, backfill volume, event sizes, retries, log retention windows, replay capability, site-to-site links, and target capacity. Throttling and retries need backoff/jitter; malformed events must be quarantined into a *dead-letter queue* (DLQ) or error queue with a repair-and-replay workflow, never silently dropped.

### Metrics and Alerts to Instrument

| Signal | Operational Meaning | Action When Threshold Breached |
| --- | --- | --- |
| Source commit → target applied lag | Actual data freshness. | Inspect queues, network, consumers, target DB; pause cutover. |
| Backlog / oldest event age | Ability to catch up under load spikes. | Scale the actual bottleneck, throttle backfill, rebalance partitions. |
| Failed events, retries, DLQ | Data may not have been applied. | Triage, remediate, controlled replay; reconcile impacted slice. |
| CDC position and remaining log retention | Risk of losing replay window. | Intervene before logs purge; keep resnapshot plan ready. |
| Count / checksum / business invariant drift | Possible missing, duplicate, or mis-transformed records. | Scope by watermark, tenant, key; reconcile in detail. |
| New app latency and error rates | User impact during new-route traffic tests. | Scale down canary or revert read traffic to old source. |

Alert thresholds must derive from **business SLOs** and tested recovery capabilities, not fixed guesses applied everywhere. **RPO** describes maximum acceptable data loss during an incident; **RTO** describes recovery time. CDC lag is vital for assessing RPO, yet lag alone cannot guarantee RPO if logs are purged or changes are skipped.

## 7. Reconciliation: Proving Data Is Complete and Accurate

A “running” pipeline does not prove target data is accurate. Reconciliation should combine:

1. **Completeness:** counts by table, tenant, status, and time; no missing or unexpected keys.
2. **Content accuracy:** compare key fields, normalized hashes, monetary sums, item quantities, foreign keys, nulls, and time zones.
3. **Business accuracy:** order total = sum of line items after tax/discounts; paid orders have valid payment references; statuses never move backward in workflow.
4. **Point-in-time alignment:** compare both sides at the **same watermark/data point** or after confirming target caught up to the locked point; avoid calling normal in-flight writes “drift.”
5. **Auditability:** store watermark, scope, mapping rule version, results, error samples, and verifier sign-off.

For example, after blocking writes for a test cohort and confirming CDC applied up to watermark W, you can compare:

~~~sql
-- Run equivalent logic on both source and target over the SAME locked scope.
-- This is an illustrative sample: adjust column names, timezone, and currency precision.
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount_minor_unit) AS amount_minor_unit
FROM orders
WHERE tenant_id = :tenant_id
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
~~~

Use minor currency units (e.g., cents) or exact decimals; never compare money using floating point. Matching totals can still mask offsetting errors across two records, so verify by key and run full or targeted sampling on high-risk slices. For huge datasets, partition by stable key ranges and compare normalized row hashes to isolate mismatched segments, then diff row by row.

**Never diff two freely mutating tables and treat instantaneous deltas as errors.** Always record the observation watermark, lag, and comparison scope.

## 8. Implementation Process from Pilot to Cutover

### Phase A — Discovery and Acceptance Criteria

Inventory data and dependency flows: which tables are transactional vs. derived, who writes, who reads, and which operations cause side effects. Record row counts, write rates over time, retention requirements, sensitive data classifications, network links, legal constraints, and allowed maintenance windows.

Set measurable criteria before picking tools. A **hypothetical** example for an ordering system:

- CDC p95 lag ≤ 5 seconds during normal operation; alert if > 30 seconds continuously for 5 minutes.
- 100% of transactions up to the cutover watermark applied and reconciled on target before granting write authority; zero unresolved error events.
- Zero monetary total variance in reconciliation window; every key or status mismatch investigated.
- Expected route-switch duration ≤ 10 minutes; 15-minute recovery path available **if** data rollback path is verified.

These thresholds only illustrate how criteria are written; real numbers depend on load, SLOs, business tolerance, and test results.

### Phase B — Build Pipeline and Initial Load

Configure encrypted links, dedicated credentials, read-only log privileges on source, and least-privilege write permissions on target; protect secrets in a vault. Start snapshot/CDC with an aligned anchor point, throttling bulk loads to avoid starving source production. Test stops, restarts, link drops, duplicates, schema drift, and deletes. Ensure source logs are retained until consumers read them and checkpoints persist durably.

### Phase C — Observed Parallel Run

Keep the legacy system owning writes while the new system ingests data. Run shadow reads and compare business logic using side-effect-free requests. Enable canary reads for isolated cohorts (e.g., internal staff or select tenants), while routing all write commands consistently to the owner. Monitor lag, errors, cost, source/target load, and reconciliation across multiple load cycles, including peaks.

### Phase D — Lock Write Authority and Cut Over

A controlled cutover typically includes:

1. Verify *go/no-go* criteria: stable mappings, reconciliation passing, lag within bounds, monitoring and on-call staff ready.
2. Place a **write fence** at the legacy app or command gateway, pausing or queuing writes for the target scope; lock final change watermark W. Goal: zero uncontrolled writes reaching the old owner.
3. Wait for stream application through W, confirm zero unhandled error events, and reconcile critical data at W. Never rely solely on “lag = 0” without verifying watermark, errors, and ordering.
4. Switch write authority, API routes, secrets/permissions, and app configuration to the new system; open writes on the new owner. Ensure the fence blocks the legacy system from accepting writes for that scope.
5. Run controlled real-transaction smoke tests, check read-your-writes on the new owner, and closely watch app errors, data metrics, and performance.

Some architectures minimize write pauses via command queues, tenant partitioning, or dedicated leader-handoff mechanisms, yet **zero downtime / zero data loss** must be proven through testing—never assumed merely from using CDC.

### Phase E — Stabilization, Rollback, and Closure

Before cutover, explicitly decide **rollback triggers** and how post-cutover writes will be handled. Two distinct situations exist:

- **No writes yet on the new system:** routing back to legacy is relatively straightforward provided the fence/watermark did not drop queued commands.
- **Writes already occurred on the new system:** routing back without reverse sync loses or forks new transactions. This requires tested reverse sync, controlled command replay, or a *roll-forward* fix on the new system. Never call flipping DNS back a safe data rollback.

Keep the legacy source in protected/read-only mode per policy during stabilization; tear down pipelines and parallel infrastructure only after the observation window closes, reconciliation completes, archival/audit, backups, recovery drills, and consumer migrations are confirmed.

## 9. Typical Failures and Remedies

| Incident | Symptom | Design / Operational Action |
| --- | --- | --- |
| Long-running snapshot while source mutates | Old rows overwrite new updates or changes go missing. | Anchor snapshot with CDC position, versioning, and ordered application. |
| Hybrid link down for hours | Backlog grows, lag breaches SLO. | Exponential backoff retries, adequate log retention, catch-up headroom; plan resnapshot if logs expire. |
| Unexpected source schema change | Consumer parse errors, DLQ spikes. | Versioned schema contracts, pre-deploy compatibility checks, pause-and-replay runbook. |
| Deletes not propagated | Target retains deleted records. | Enable delete capture, tombstones/versions, enforce retention and PII deletion policies. |
| Duplicate events after restart | Double counts, re-triggered side effects. | Inbox/dedup, idempotent upserts, suppress side effects during replay. |
| Target reads half a transaction | Order exists without order_item rows. | Preserve transaction boundaries or publish read models only once the aggregate completes. |
| Users still write to legacy post-cutover | Data forks into two diverging branches. | Enforce write fence at execution layer, audit all entry points and DB grants; do not rely solely on DNS. |
| Rollback after new writes occurred | New transactions missing on legacy. | Tested reverse replication/replay or roll forward; always reconcile before switching authority. |

Test suites should cover duplicate events, out-of-order delivery, network drops, crashes before/after commit, schema changes, deletes, peak load, and aborted cutovers. One successful initial-load demo does not prove recoverability.

## 10. Well-Architected Design Review

| Dimension | Review Questions for Parallel Run |
| --- | --- |
| **Operational Excellence** | Are there lag, backlog, and reconciliation dashboards, alerts, replay/cutover runbooks, and named owners per data source? |
| **Reliability** | On link loss or consumer restart, can processing resume cleanly from checkpoints? Are log retention and write fences tested? |
| **Security** | Are links TLS-encrypted, data encrypted at rest, credentials rotated, audit logs scrubbed of PII, and read/write grants separated? |
| **Performance Efficiency** | Does the pipeline handle peak write rates, catch-up bursts, IOPS/CPU/network limits, and partition skew? |
| **Cost Optimization** | Are dual-run compute, cross-region egress, extended log retention, streams/queues, reconciliation, and temporary resources tracked with an end date? |
| **Sustainability** | Are unnecessary replays/backfills avoided, resources right-sized, and temporary infrastructure removed upon completion? |

Additionally, sensitive data requires reviewing role-based access, storage locations, backups, retention periods, deletion mandates, and cross-border regulations applicable to the organization. Sync pipelines can inadvertently replicate sensitive data into non-production environments if not governed upfront.

## 11. Design Exercise: Migrating an Order System

**Prompt.** A legacy system processes orders in a data center. The new cloud system splits the schema into `order` and `order_item`. Average churn is 200 changes/sec, peaking at 700 changes/sec. The legacy system must stay online for three weeks. Operations wants to pilot order lookup from the new system before shifting writes. Payment records must never be double-counted; the hybrid link drops occasionally.

**Reference Approach:**

1. Designate legacy as the order write owner until cutover; forbid the new system from writing payment status out of replayed data. Choose one-way CDC and versioned mappings for the target schema.
2. Load a consistent snapshot and replay CDC from the aligned anchor; verify order keys, line items, currency conversions, and deletes. Consumers apply changes keyed by order ID to preserve order, backed by an idempotency store/key.
3. Size for **700 changes/sec peak** plus post-outage catch-up headroom; test sustained link drops, verify log retention, and alert well before the replay window expires.
4. Run shadow reads; compare statuses, monetary totals, and line-item counts at watermarks. For canary reads, surface or handle lag per UX needs; operations requiring strong consistency query the owner.
5. At cutover, fence legacy writes, lock watermark, wait for full application, reconcile, then switch owner. Prepare a verified roll-forward or reverse-sync strategy for any transactions created after authority handoff.

**Self-Check Questions:**

1. If consumers process 600 changes/sec while source load is 700 changes/sec, what happens to the backlog?
2. Why are matching row counts between two tables insufficient to prove migration success?
3. If CDC reports zero lag yet the DLQ contains errors, is it safe to cut over?
4. Once users have created new orders in the cloud, can you safely roll back just by pointing DNS back to legacy?
5. If reference data can lag 10 minutes while payment confirmation requires immediate state, how do you split ownership and read/write paths?

**Answer Hints:** (1) backlog grows by roughly 100 changes/sec while those rates persist; (2) content, business invariants, and point-in-time watermarks must also reconcile; (3) no, remediate and replay failed events first; (4) no, newly written data must be preserved or handled via roll-forward; (5) reference data can read a lagging replica, while payment commands must route through the authoritative system with business-level deduplication.

## 12. Pre-Cutover Checklist

- [ ] Write owner and data scope defined, with an enforceable write fence.
- [ ] Snapshot and CDC anchored consistently; replay tested across outages and restarts.
- [ ] Inserts, updates, deletes, schema changes, duplicates, and out-of-order events handled or explicitly bounded.
- [ ] Backlog, lag, DLQ, and stream position monitored/alerted; capacity meets peak load.
- [ ] Reconciliation at a common watermark meets agreed criteria; zero uninvestigated critical data errors.
- [ ] Link security, access controls, logging, sensitive data handling, and parallel-run costs verified.
- [ ] Cutover runbook covers write fencing, watermark locking, verification, authority handoff, smoke tests, and abort conditions.
- [ ] Rollback/roll-forward plan handles **every post-cutover write**; rehearsed with test data.
- [ ] Accountable owners, acceptance evidence, legacy retention window, and resource teardown plan established.

The crux of parallel-run synchronization is **governing write authority, change positions, and reconciliation evidence**. CDC tools move the bytes, while the architecture must prove zero lost or misapplied data, preserved business consistency, and the ability to cut over or recover under tested conditions.
