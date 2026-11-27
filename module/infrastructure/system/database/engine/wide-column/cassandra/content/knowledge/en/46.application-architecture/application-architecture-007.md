# Streaming Data to Search or Analytics with Observable Sync Progress

## 1. The Problem: One Data Source, Multiple Read Patterns

Apache Cassandra fits high-throughput writes distributed across nodes and reads with known partition keys. A Cassandra table is typically designed **around queries**: selecting partition keys and clustering columns so the application reads the exact partition directly, avoiding full-table scans or arbitrary filtering. This is an advantage for transactional APIs, yet does not automatically satisfy:

- **Search:** full-text lookup, relevance ranking, multi-attribute filtering, or autocomplete.
- **Analytics:** cross-customer aggregations, historical comparisons, metric computations, and ad-hoc queries over large datasets.

For instance, an order service stores orders in Cassandra and reads them by `(tenant_id, order_id)`. Meanwhile, support staff want to search orders by keyword, status, or shipping address, and analysts want daily revenue by region. Continually adding Cassandra tables for every filter combination or running cluster-wide scan queries quickly drives up operational complexity and read cost.

The standard solution is keeping **Cassandra as the business data source** while syncing projections to systems tailored to each query pattern:

| Need | Example Target System | Data Model at Target |
| --- | --- | --- |
| Text search, filtering, sorting | OpenSearch/Elasticsearch | One document per entity; index only searchable fields |
| Reporting, BI, aggregations | ClickHouse, data warehouse, or data lake | Event/fact tables, dimension tables, or current-state snapshots |
| Transactional lookup by ID | Cassandra | Tables keyed by partition key and predetermined business queries |

**Syncing does not mean every system returns the exact same result at every instant.** Acceptable lag (freshness), change-forwarding mechanics, drift-handling rules, progress state, and recovery workflows must all be explicitly designed.

### Completion Criteria to Agree On Upfront

A pipeline is operationally sound when it can answer five questions:

1. **What is being synced?** Source tables, tenant scope, schema versions, event types, and exportable fields.
2. **How far has sync progressed?** Which historical data has been scanned, which stream positions have been processed, and what the target has genuinely acknowledged.
3. **How stale is recent data?** End-to-end latency and acceptable thresholds per target system.
4. **Is re-running after failures safe?** Whether idempotency, stale-version guards, and durable checkpoints exist.
5. **How are dropped records detected?** Whether reconciliation, alerting, replay, and rebuild mechanisms exist.

## 2. Reference Architecture

~~~mermaid
flowchart LR
    APP["Java Application"] --> CAS[("Cassandra: business data")]
    CAS -->|"Historical read by token range"| BF["Checkpointed backfill"]
    CAS -->|"CDC from commit log"| CDC["CDC connector / agent"]
    CDC --> BUS[("Durable event stream")]
    BF --> NORM["Normalize events and versions"]
    BUS --> NORM
    NORM --> SEARCH["Search consumer"]
    NORM --> ANALYTICS["Analytics consumer"]
    SEARCH --> OS[("Search index")]
    ANALYTICS --> WH[("Analytics store")]
    SEARCH --> CS[("Search checkpoint")]
    ANALYTICS --> CA[("Analytics checkpoint")]
    CS --> MON["Track lag, errors, progress"]
    CA --> MON
~~~

Here **backfill** loads pre-existing data; **Change Data Capture (CDC)** forwards subsequent updates. A durable event stream, such as a Kafka topic, decouples Cassandra write throughput from each target system's ingestion capacity. Each consumer maintains its own checkpoint: search having caught up does not prove the analytics store has caught up.

The diagram shows a **logical architecture**. Cassandra CDC reads changes from the commit log mechanism through a connector/agent suited to the version and runtime environment; it is not an auto-created CDC topic triggered by flipping a table flag alone. If an organization adopts an event-first source-of-truth model, the application can write to a durable event log first, with multiple consumers building Cassandra, the search index, and the analytics store in parallel. That model requires redesigning write paths and data ownership.

### Why Not Dual-Write Directly from Java?

A pattern of "write to Cassandra, then call the indexing API" leaves a failure gap: a crash between the two writes causes Cassandra and search to diverge. Reversing the order merely flips which side risks missing updates; retries can also create duplicate records. Cassandra also provides no ACID transactions spanning Cassandra and a search engine.

More reliable options include: controlled, well-operated CDC; a durable event log as the source of truth; or an application outbox that persists events alongside business changes **within actual storage transaction limits**. Never assume two writes to two Cassandra partitions or two distinct systems form an atomic transaction.

## 3. Preparing Source Data and Event Contracts

Suppose the API fetches orders by tenant and ID:

~~~sql
CREATE TABLE orders_by_id (
    tenant_id uuid,
    order_id uuid,
    customer_id uuid,
    status text,
    total_amount decimal,
    updated_at timestamp,
    change_version bigint,
    is_deleted boolean,
    PRIMARY KEY ((tenant_id, order_id))
) WITH cdc = true;
~~~

Each order is a partition. Business lookups use the full partition key:

~~~sql
SELECT order_id, customer_id, status, total_amount, updated_at
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

This is an **illustrative schema**, not the sole design for every order system. Partition key selection must account for traffic, partition size, tenant isolation strategy, and real queries. Enabling **cdc = true** on the table is only part of the setup; the cluster must also support and configure CDC, disk headroom, reader agents, backlog monitoring, and procedures for handling CDC write blocks.

Define an intermediate event contract:

~~~json
{
  "event_id": "a1b2c3-example",
  "entity_type": "order",
  "entity_key": "tenant-17/order-932",
  "operation": "UPSERT",
  "version": 104,
  "occurred_at": "2026-11-21T08:20:00Z",
  "source_position": {
    "stream": "order-changes",
    "partition": 3,
    "offset": 18720
  },
  "payload": {
    "tenant_id": "tenant-17",
    "order_id": "order-932",
    "status": "PAID",
    "total_amount": "125000.00"
  }
}
~~~

The JSON IDs and values are illustrative; production applications should use UUID/CQL-compatible formats. The contract must specify:

- **entity_key:** a stable key across all systems; in multi-tenant setups, always include `tenant_id` to prevent cross-tenant document overwrites.
- **operation:** `UPSERT`, `DELETE`, and any other needed change types.
- **version:** monotonically increasing **per entity**, produced by a reliable source write mechanism. Application-clock `updated_at` is not automatically a safe version when concurrent writers exist.
- **event_id:** identifier for deduplication and tracing.
- **source_position:** stream position for checkpointing/replay. Offsets are comparable only within **the same partition**, not as global sequence numbers.
- **schema_version** (if applicable): supports payload format evolution while older consumers can still distinguish versions.

CDC may carry **column mutations** rather than full row images after every update. The connector or normalization layer must know how to assemble current state, re-read from Cassandra when appropriate, or emit domain events containing full projection attributes. When re-reading from the source, account for another update occurring between event receipt and row read.

**Versions must be guaranteed by design**, such as a single writer per entity, per-entity serialization before stream emission, or conditional/LWT version updates in Cassandra where throughput and latency allow. Never infer exact ordering from wall-clock timestamps or offsets across distinct CDC agents.

## 4. Choosing How to Extract Changes from Cassandra

| Approach | When Suitable | What Must Be Solved |
| --- | --- | --- |
| Commit-log CDC | Need to capture mutations already hitting Cassandra with minimal changes to application write paths | Version-compatible connector deployment; duplicates, partial updates, deletes/TTLs, backlog, retention, and recovery |
| Event log as source of truth | Deliberately redesigning write paths; multiple consumers need the same event history | Event writing and ordering, building Cassandra projections, idempotency, and pre-existing data handling |
| Application-managed outbox | Application owns business logic and has a reliable outbox write boundary | Proving atomicity matches storage and partition rules; relay, retries, and outbox cleanup |
| Periodic scans | Small workloads tolerating high lag without a change stream | High scan resource cost; hard to detect deletes/TTLs; requires full reconciliation |

### Key Limitations of CDC

1. CDC is tied to each Cassandra node's commit log. Collecting from multiple replicas/nodes can produce duplicate events and reordered observations; the connector needs a normalization strategy.
2. CDC buffers and disk space are finite. If the reader pipeline falls behind, depending on version/configuration, CDC pressure can affect write availability on CDC-enabled tables. Set early alerts, retention budgets, and disconnect playbooks.
3. **TTL expiration does not mean a `DELETE` event is emitted at expiration time.** A TTL-bearing value can expire silently without a new mutation at expiry time. If targets require timely deletion, include expiration timestamps in documents for target-side handling, emit business expiry events, or run periodic reconciliation/cleanup.
4. A `DELETE` command generates tombstones; consumers must translate them into deletes/hides at the target. Account for cell-, row-, and partition-level deletes if the schema permits them, not just `INSERT`/`UPDATE`.
5. CDC does not replace backups, snapshots, or an infinite historical log. Recovery procedures must know the exact replay retention window and fall back to re-initialization if exceeded.

## 5. Combining Historical Backfill with the Change Stream

This is the easiest step to get wrong. If you scan existing rows and **only then** start CDC, updates or deletes occurring during the scan may disappear from the target.

A safer rollout procedure:

1. **Start CDC capture** and ensure durable event storage. Record the set of starting positions per stream/partition. Verify event retention easily covers the entire backfill plus incident headroom.
2. **Split backfill into token ranges** and throttle concurrency, page size, and read rate. Cassandra is optimized for partition-key lookups; scanning across many token ranges still consumes heavy I/O/CPU and can impact production traffic.
3. **Emit each row as a versioned UPSERT**, feeding it through the same consumer idempotency logic or a dedicated backfill flow with agreed rules for merging with live events.
4. **Persist backfill checkpoints only after target acknowledgment**; store ranges and safe resume keys/positions, allowing overlap re-reads of the trailing range after restarts.
5. **Replay and apply CDC backlog**, preserving per-entity order and skipping events older than the already-applied version. Never let an older snapshot overwrite a newer version.
6. **Reconcile coverage and counts**, transitioning to "caught up" only after every range completes and every CDC partition has passed the target watermark captured for that check.

~~~mermaid
sequenceDiagram
    participant S as Cassandra
    participant B as Backfill
    participant E as CDC/Event log
    participant T as Search/Analytics
    Note over E: Start retaining events at position C0
    S-->>E: version 12: update order X
    S-->>B: Scan order X (version 11 or 12)
    B->>T: UPSERT X from backfill
    E->>T: UPSERT X version 12
    Note over T: Keep highest version only
    S-->>E: version 13: delete order X
    E->>T: DELETE X version 13
    Note over T: Retain delete marker/version to prevent resurrection
~~~

**Do not assume backfill is a point-in-time consistent snapshot.** A standard Cassandra scan can observe different points in time across partitions. Versioning and reconciliation resolve interleaved changes; without trustworthy versions, stronger cutover/stream-merging mechanisms or locked/verified rebuild workflows are required.

Paging-state scan checkpoints should only be used if driver lifecycle and recovery limits are thoroughly understood. For long-running jobs, treat small token ranges as work units and checkpoint completed ranges or last applied keys; after failures, re-scanning unconfirmed segments is safe thanks to consumer idempotency.

### When a Full Index Rebuild Is Required

Build a **new index version**, backfill historical data, catch up on live changes, verify counts/samples, and then switch query aliases to the new index. Never drop the old index before verification. Analytics stores can use staging partitions/tables similarly, depending on engine atomic-swap capabilities.

## 6. Preventing Duplicates, Out-of-Order Writes, and Erroneous Deletes

In distributed systems, **at-least-once** is the practical norm: consumers reprocess events on timeouts, crashes before offset commit, or replays. Therefore, sinks must be idempotent.

For each entity, apply this logical rule:

~~~text
handle(event):
    key = event.entity_key
    current = sink_state.get(key)

    if current exists and event.version < current.version:
        return ACK_OLD_EVENT
    if current exists and event.version == current.version:
        if same_semantic_event(current, event):
            return ACK_DUPLICATE
        return CONFLICT_REQUIRES_INVESTIGATION

    if event.operation == DELETE:
        persist_tombstone(key, event.version)
        remove_or_hide_document(key)
    else:
        upsert_projection(key, event.payload, event.version)

    return ACK_AFTER_DURABLE_SINK_SUCCESS
~~~

This is **correctness pseudocode**, not a built-in transaction across every search engine. Version checks and state writes must be atomic enough that two concurrent consumers/workers cannot let an older event overwrite a newer one. Use the sink's conditional version control or a transactional state store alongside the pipeline. Under concurrent writers, separate "read version then write" logic is insufficient.

Pay special attention to `DELETE`: some search engines retain tombstones/versions for deleted documents only briefly. Replaying a very old `UPSERT` after the delete marker expires risks "resurrecting" the document. For strict correctness, persist **durable delete versions** in the projection/state store, or model deleted records as versioned hidden documents until old events can no longer be replayed.

Partitioning Kafka by `entity_key` typically preserves per-entity ordering **within an already-serialized producer stream**. It does not automatically fix multiple CDC replicas emitting out-of-order mutations prior to Kafka ingestion. Version guards and conflict checks remain essential.

## 7. Defining Verifiable Sync Progress

Showing "100% processed" based solely on scanned row count is insufficient. A pipeline has at least **two distinct progress dimensions**: how far historical backfill has progressed and how far the change stream has been applied. Each target system tracks its own progress.

### 7.1. What Should a Checkpoint Contain?

A progress tracking record can store:

~~~json
{
  "pipeline": "orders-to-search",
  "target": "search-v4",
  "phase": "CATCHING_UP",
  "backfill": {
    "completed_ranges": 238,
    "total_ranges": 256,
    "active_range": "range-239",
    "last_durable_key": "opaque-resume-key"
  },
  "stream": {
    "topic": "order-changes",
    "partition": 3,
    "committed_offset": 18720,
    "observed_head_offset": 18960
  },
  "last_sink_ack_at": "2026-11-21T08:20:10Z",
  "error_count": 0
}
~~~

This example shows **a single partition**. Production deployments must track offsets/checkpoints across **all partitions and all token ranges** in the job scope, along with job version, snapshot/cutover markers, and target type. No single Kafka offset represents whole-topic progress; even less does one offset cover multiple CDC agents or Cassandra nodes.

States should be explicitly defined:

| State | Verifiable Condition |
| --- | --- |
| INITIALIZING | Connector, mapping/schema, credentials, and CDC start positions are prepared |
| BACKFILLING | Token ranges remain unacknowledged at the sink |
| CATCHING_UP | Backfill complete; draining CDC backlog toward target watermark |
| LIVE | Backfill complete and lag stays within SLO over an observation window |
| DEGRADED | Pipeline is running, but lag, errors, or retry rates exceed thresholds |
| BLOCKED | Missing event source, retention expired, schema/credential error, or sink unavailable |
| REBUILDING | Building a new projection; cannot yet declare it ready to serve |

### 7.2. Rules for Recording Completion

**Advance checkpoints only after the sink acknowledges that the corresponding operations succeeded durably per the sink's contract.** If a 100-document bulk request has 2 rejected documents, never commit an offset past those 2 documents and call it done. Retry, record granular progress, and route to DLQ as needed while preserving accurate replay capability.

Kafka consumer example:

~~~text
poll records from partition P
validate and transform each record
apply to target using idempotent writes
verify each item/bulk result (including partial failures)
persist target-specific checkpoint / commit only safe offset
on crash: replay from last safe offset
~~~

If checkpoints and the sink live in two different systems, crashing in between can cause events to be reprocessed. Idempotency and version guards are what make replay safe. Advancing a checkpoint before sink confirmation risks **unrecoverable data loss**.

Some search engines return an index-write ACK before documents become searchable due to refresh intervals. Therefore, measure **search-visible latency** with verification queries; never equate write ACK with "visible to users."

### 7.3. Interpreting Lag Metrics Correctly

| Metric | Meaning | Notes |
| --- | --- | --- |
| Backfill coverage | Completed token ranges / total ranges | Range percentage does not equal row percentage; ranges may be uneven |
| Stream offset lag | Head offset − committed offset per partition | Aggregate via max/sum meaningfully; never compare raw offsets across partitions |
| End-to-end freshness | Time data becomes readable at target − source mutation time | Use synchronized clocks; account for clock skew and late events |
| Last successful apply | Most recent sink write acknowledgment | If upstream produces no events, an older timestamp alone does not prove pipeline failure |
| Retry/DLQ count | Records hitting transient/permanent errors | Non-zero DLQ may mean data sync is incomplete |
| Reconciliation mismatch | Count of divergent keys/records in sample or scope check | Supplements offset checks |
| CDC disk/backlog | Pressure on agents, queues, disk, and retention | Detects event-loss risk before replay windows expire |

On dashboards, publish concrete evaluation statements: "Backfill 256/256 ranges; all 12 stream partitions applied at least through head captured at 10:00:00 UTC; p95 freshness 8s; 0 pending DLQ records." This is a scoped, timestamped claim, unlike a vague "synchronized" label.

## 8. Two Target Systems, Two Projection Styles

### 8.1. Search Index

A document can contain business keys, filter attributes, searchable text, version, and deletion state. Document IDs should be deterministically derived, e.g., from `(tenant_id, order_id)`. Consumers update by that ID using version guards so older records cannot overwrite newer ones.

Mapping design must decide upfront:

- Which fields need full-text analysis vs. keyword type for exact filtering and aggregations.
- Vietnamese tokenization, stemming, diacritic/character normalization, and search relevance testing.
- Mapping/index version evolution policies, aliases, and cutover timing to new indexes.
- Which sensitive fields **must not** be indexed; tenant authorization enforcement at query time.

APIs can read search results to obtain matching IDs, then fetch authoritative business records from Cassandra when high accuracy or final authorization checks are required. This also limits the impact of slightly stale search documents, though it adds reads and requires guarding against N+1 queries.

### 8.2. Analytics Store

Clearly choose **target table semantics**:

- **Current-state table:** one current row per order, maintained with versioned UPSERTs and deletes as needed.
- **Event fact table:** each status transition is an independent event with an `event_id` for deduplication; answers "when did orders change state."
- **Daily/hourly aggregate:** summary tables derived from facts; requires update/recompute rules for late-arriving events.

Do not mix the two concepts: syncing only current snapshots of Cassandra rows cannot reconstruct **historical transitions** from before CDC was enabled. For daily reports, define the business timezone, closing cutoffs, and late-arrival/retraction handling.

Search and analytics pipelines can stay independent in throughput, mappings, offsets, and recovery procedures. One slow target should never force the other target to drop events.

## 9. Cassandra Consistency vs. Projection Freshness

Cassandra replicates data across replicas according to replication factor and read/write consistency policies. Java applications often pick a level such as `LOCAL_QUORUM` to balance latency, availability, and read-your-writes within one datacenter; exact guarantees depend on replication factor, topology, and failure conditions.

However, **`LOCAL_QUORUM` in Cassandra does not turn a search engine into a transactionally synchronous replica**. After an API returns success, there are still downstream stages: mutation captured by CDC, queued event delivery, consumer apply, search index refresh, and query cache expiration.

Explicitly document user-facing consistency expectations:

| Action | Reference Handling |
| --- | --- |
| Order detail screen immediately after save | Read Cassandra by ID; do not require waiting for search |
| List filters / search | Accept eventual consistency with an SLO, e.g., p95 change visibility within 10s |
| "Find newly created order right now" button | Use returned ID to read Cassandra, or provide an explicit wait/read-your-writes mechanism |
| End-of-day reports | Capture source cutoff, wait for pipeline to pass cutoff, reconcile, then publish |

SLO figures in the table are **examples only**; measure them against your real infrastructure and workload. In multi-datacenter deployments, clarify which DC/replicas supply CDC and the consistency boundary for cross-region replication.

## 10. Incident Handling and Recovery

| Scenario | Symptom | Safe Recovery |
| --- | --- | --- |
| Consumer crashes mid-batch | Offsets stop advancing, retries rise | Restart from durable checkpoint; deduplicate/version-guard on replay |
| Search engine overloaded / 429 | Lag climbs, bulk partial failures | Retry with backoff and rate limits; never commit past failed records |
| Schema-incompatible event | Poison message, DLQ grows | Quarantine event, alert, fix parser/mapping, then replay; never silently mark done |
| CDC agent falls behind retention | Offset/segment range no longer readable | Mark BLOCKED, identify missing window, and run source rebuild/reconciliation |
| Backfill interrupted | Incomplete token ranges remain | Re-scan unfinished ranges, apply version guards, and continue retained CDC |
| Unreflected `DELETE` or TTL | "Ghost" documents, reconciliation drift | Emit business delete events, check TTL via `expire_at` or periodic reconciliation cleanup |
| Sink receives out-of-order events | Version regressions/conflicts | Ignore older events or investigate version producer; avoid wall-clock last-write-wins |
| Mapping/schema change | Index write errors, new fields unsearchable | Use schema contracts, new index versions, and verified cutover procedures |

When an incident occurs, establish **the last retained source position, the last applied sink position, the timestamp of the first error, and affected entities**. Never purge queues, skip offsets, or "force green" alerts without a data-recovery plan.

### Periodic Reconciliation

Even when offsets are caught up, validate data directly. Partition checks by tenant, time bucket, or token range; compare active row counts, normalized checksums, and sampled keys/versions against sinks. Simple total counts are insufficient because two errors can cancel each other out. Include deleted and TTL-expired data; fix a clear comparison cutoff to avoid false positives from concurrent writes.

For search, run canary queries against known IDs/terms after index refreshes. For analytics, verify standard aggregations on closed days and late-adjusted records. Mismatches must trigger key/range repairs or rebuilds with auditable logs.

## 11. Connecting from Java Applications and Responsibility Boundaries

Java applications can use a cluster-compatible DataStax/Apache Cassandra Java Driver to run CQL via prepared statements, set appropriate consistency levels, and configure timeouts/retries. Business responsibility includes ensuring source records carry required keys, versions, and attributes; **never entrust sync correctness to a fire-and-forget second HTTP call**.

A conceptual example:

~~~java
PreparedStatement selectOrder = session.prepare(
    "SELECT status, total_amount, change_version " +
    "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?");

BoundStatement query = selectOrder.bind(tenantId, orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

Row row = session.execute(query).one();
~~~

The code above is **a direct Cassandra partition-key read**, not a complete CDC consumer. Session lifecycle must be managed at the application layer; select libraries, imports, and specific APIs for your actual driver version. If monotonically increasing `change_version` is needed across multiple writers, use an appropriate serialization/CAS mechanism, accept Paxos/LWT cost, and handle version contention; never treat system clock timestamps as a total order.

Separate responsibilities clearly: the service owns the business model and source data; the CDC/stream platform owns event delivery and retention; search and analytics consumers each own their projections, idempotency, and **separate** checkpoints; operations owns alerting, reconciliation, and rebuild playbooks.

## 12. End-to-End Progression Example from Write to Query

Suppose order X is created at version 41, transitions to `PAID` at version 42, and is canceled at version 43:

| Time | Cassandra | Stream Received | Valid Search State |
| --- | --- | --- | --- |
| T0 | X = NEW, v41 | UPSERT v41 | X = NEW, v41 |
| T1 | X = PAID, v42 | UPSERT v42 | X = PAID, v42 |
| T2 | X deleted/canceled, v43 | DELETE v43 | X hidden/deleted, v43 stored |
| T3 | No change | Replay UPSERT v41 | Still hidden/deleted, v43 |

If an old backfill sends X = NEW v41 after T2, the version guard must reject it. If v42 arrives before v41, the target keeps v42. If two events share the same version with different payloads, that is a **contract conflict** requiring investigation, not a safe duplicate.

Example progress report at 10:00 UTC:

~~~text
Pipeline: orders-to-search
Backfill: 256/256 ranges applied
CDC: 12/12 partitions applied through captured 09:59:55 head
Worst consumer lag: 250 records (partition 7)
p95 end-to-end freshness: 7.2 seconds
Failed records awaiting replay: 0
State: LIVE (SLO <= 15 seconds)
~~~

The `LIVE` state is valid here because the defined SLO criteria are met, **not because search data is instantaneously synchronized**. When a user requires data exact as of 10:00:00, the system must capture a new watermark and wait for all partitions to pass it; otherwise, publish the latest guaranteed timestamp.

## 13. Pre-Production Test Scenarios

1. **Backfill with concurrent writes:** update a row multiple times and delete it mid-scan; the target must converge to the latest valid version.
2. **Replay and duplicates:** replay the same `event_id`/offset after sink ACK; document/fact counts must not inflate and versions must not regress.
3. **Out-of-order delivery:** deliver v12 before v11, then `DELETE` v13 ahead of an older `UPSERT`; data must never resurrect.
4. **Crash between sink write and checkpoint commit:** restart loses zero records, even if reprocessed.
5. **Bulk partial failure:** reject part of a batch; offsets must advance only past safely processed items.
6. **CDC data gap or expired retention:** pipeline transitions to `BLOCKED`, with a verified rebuild and coverage check procedure.
7. **TTL/deletes:** verify expired/deleted documents disappear within the defined SLO.
8. **High load:** measure scan pressure on Cassandra, CDC disk usage, offset lag, refresh/search latency, and sink throughput.
9. **Reconciliation:** intentionally corrupt or drop a document and verify the reconciliation job detects and repairs it.
10. **Tenancy and authorization:** never export restricted sensitive fields or allow tenant A's queries to see tenant B's data.

Passing criteria must be quantified per system: time to detect incidents, max catch-up time, p95/p99 latency, error rate, max pipeline downtime before CDC retention expires, and allowable variance at report close.

## 14. Pre-Implementation Design Checklist

Before building, answer all of the following:

- Which Cassandra table is the source of truth? Do partition keys support token-range historical backfill without overloading the cluster?
- Do events originate from CDC, event-first logs, or an outbox? Who owns data retention when sinks are down?
- Do events include stable keys, monotonically increasing per-entity versions, `DELETE`/TTL info, and schema versions?
- Are deduplication, out-of-order handling, and tombstone/version retention defined so replays cannot resurrect data?
- Does backfill start only after CDC retains changes reliably? Are retention and per-range/partition checkpoints sufficient?
- Do checkpoints advance only after sink ACK? Are bulk partial errors, DLQs, and replays handled cleanly?
- Do dashboards separate **backfill coverage**, **stream progress**, **freshness**, **search visibility**, and **reconciliation**?
- Are separate SLOs defined for search and analytics, along with watermark-based reporting and safe rebuild playbooks?

**Core principle:** with Cassandra, tables are designed around transactional queries; search engines and analytics stores are projections serving different read patterns. Architectural quality depends on reliable change transport, idempotent application, target-acknowledged progress tracking, and detecting/recovering any remaining discrepancies.
