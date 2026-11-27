# Limiting Compaction, Storage, and Replica Load Impact During Cassandra Data Migration

## 1. Why can schema migration overload a cluster even when every CQL query is valid?

Apache Cassandra is a distributed **wide-column** database that places partitions by **partition key** and maintains multiple replicas per replication strategy. Java applications query via CQL, choose consistency levels, and depend on SSTables, compaction, repair, streaming, and replica health.

When changing schemas—such as moving from an overly wide partition to monthly bucketed partitions—teams usually want to do three things:

1. Create a new table with a partition key aligned to queries.
2. **Backfill** historical data from the old table into the new table.
3. Switch applications to read/write the new table, then retire the old one.

If backfill runs at full blast, the cluster can hit a dangerous feedback loop:

~~~mermaid
flowchart TD
    A["Backfill reads source data"] --> B["Read I/O and network rise"]
    A --> C["Writes mutations to target table"]
    C --> D["Memtable flushes create more SSTables"]
    D --> E["Compaction backlog grows"]
    E --> F["Disk I/O and temp space rise"]
    F --> G["Replicas respond slowly"]
    G --> H["p99, timeouts, and retries rise"]
    H --> I["More request load hits replicas"]
    I --> F
    J["Concurrent repair, streaming, or backup"] --> F
~~~

**The problem is not just row count.** You must factor in replication factor, write amplification, temporary compaction files, Java driver concurrency, source read paths, and concurrent operational tasks.

This lesson belongs to the **Migration and Schema** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The goal is building a controlled migration process that avoids sacrificing performance, storage headroom, or correctness merely to shorten backfill duration.

## 2. Distinguishing metadata changes from real data movement

Not every schema change carries the same resource cost.

| Change type | Example | Expected data load | Notes |
|---|---|---|---|
| CQL-supported metadata change | Adding a regular column via `ALTER TABLE ... ADD` | Does not require immediately rewriting the entire table | Must check version, client compatibility, and semantics |
| Creating a new query-driven table | `CREATE TABLE ...` then backfill | Reads source and writes target at target RF | Can nearly double disk usage during transition |
| Changing partition/clustering keys | Moving to daily/monthly partitions | Typically requires new table and rewriting logical rows | Cassandra does not allow arbitrarily altering an existing table's primary key |
| Changing formats or data types | Normalizing timestamps, converting field types | May require parsing, transforming, and rewriting data | Cannot merely copy raw SSTables directly |
| Adding an index or materialized view | Creating a secondary access path | May require background index/view building | I/O cost and feature behavior vary by version |
| Changing replication factor | RF=2 to RF=3 | Changes replica count, requiring data sync workflow | Different problem from application table backfill |
| Cross-cluster/DC move | Changing data placement | May involve large streaming or import/export | Must account for topology, network, and token ranges |

**Never draft a blanket plan assuming "schema changes are cheap."** A metadata-only statement may be lightweight, whereas a migration involving a full-partition backfill is a large-scale read/write workload.

### 2.1. Business example: replacing an order lookup table

Old table:

~~~cql
CREATE KEYSPACE commerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE commerce.orders_by_customer_v1 (
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    amount decimal,
    status text,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

For customers with multi-year histories, **one `customer_id` partition** can grow huge. To bound read scope and SSTable merges by month, create a new table:

~~~cql
CREATE TABLE commerce.orders_by_customer_month_v2 (
    customer_id uuid,
    order_month date,
    created_at timestamp,
    order_id uuid,
    amount decimal,
    status text,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

In this example, `order_month` is the **first day of the month in UTC**, computed by the app from `created_at`. Each `(customer_id, order_month)` pair forms its own partition, letting the API fetch one month of orders instead of scanning multi-year partitions.

**Cassandra does not move data from v1 to v2 automatically** when `CREATE TABLE` completes. You must engineer the backfill, live-write synchronization, and read cutover.

### 2.2. Queries must be safe on both sides

~~~cql
-- Source: reading one customer's history.
SELECT created_at, order_id, amount, status
FROM commerce.orders_by_customer_v1
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

-- Target: reading one month for a customer.
SELECT created_at, order_id, amount, status
FROM commerce.orders_by_customer_month_v2
WHERE customer_id = 11111111-1111-1111-1111-111111111111
  AND order_month = '2026-11-01'
LIMIT 50;
~~~

Run the source query only **against a known customer/partition list or a controlled scan workflow**. If v1 holds massive partitions, even reading by exact partition key is expensive; enforce paging, read pacing, and per-partition sizing.

## 3. Three costs to forecast before running

### 3.1. Source read load

Backfill must read data from v1:

- Replica reads may merge memtables and multiple SSTables.
- Tombstones/TTLs force scanning more entries than live rows returned.
- Wide partitions require many pages and client-side buffering.
- Read consistency level affects participating replicas and latency.
- Parallelizing across partitions does not distribute load evenly across token ranges.

### 3.2. Target write load

Each mutation to v2 goes to multiple replicas per RF and placement:

- Replicas append to commit logs and insert into memtables.
- Memtables flush to SSTables periodically.
- Compaction rewrites SSTables according to the table's strategy.
- Hints, repairs, and background tasks handle lagging replicas.
- In multi-DC clusters, cross-DC traffic can be heavy even if workers connect to one local DC.

**RF=3 does not mean one mutation causes exactly three fixed disk I/Os.** It specifies replica count under the replication strategy; actual messages, ACKs, flushes, and compactions also depend on CL, routing, workload, and node state.

### 3.3. Temporary storage space

While both tables coexist, several consumers occupy disk:

- SSTables and snapshots of table v1.
- Growing SSTables of v2 during backfill.
- Compaction output SSTables **while old input SSTables remain pinned until safe release**.
- Commit logs, hints, temporary files, and streaming/repair artifacts.
- Organic growth from live traffic throughout the migration window.

Therefore, **never multiply logical data size by RF and call that peak disk usage**.

## 4. Capacity and headroom modeling

### 4.1. Preliminary budget formula

When one cluster holds both v1 and v2:

~~~text
Peak physical storage (estimate)
≈ physical_bytes(v1, still retained)
 + physical_bytes(v2 post-backfill)
 + temporary_bytes(compaction/streaming/flush)
 + snapshots/backups on the same filesystem
 + organic new data growth
 + operational safety margin
~~~

Pull variables from **per-node storage metrics**; this is not an exact formula for every compaction strategy. Physical SSTable size depends on compression, TTLs, tombstones, and physical overlap.

### 4.2. Cluster capacity example

Suppose we have **6 nodes** and these physical figures:

| Item | Cluster total | Per-node average if evenly spread |
|---|---:|---:|
| Old table SSTable data | 6.0 TiB | 1.00 TiB |
| New table SSTable data post-migration | 5.4 TiB | 0.90 TiB |
| Temporary compaction/flush/streaming peak (assumed) | 1.5 TiB | 0.25 TiB |
| **Total before snapshots and safety margin** | **12.9 TiB** | **2.15 TiB** |

If each node has only **2.5 TiB usable capacity**, an average of 2.15 TiB is already **86%** before snapshots and organic growth. That is risky here, especially when compaction needs extra scratch space.

If each node has **4 TiB usable**, headroom is healthier, yet **never declare safety from averages alone**. A hot node can hold much more data and hit disk limits ahead of peers.

**Figures in this table are hypothetical**, not Cassandra benchmarks. Substitute real measurements, checking per-node skew, snapshot hard links, and growth trends.

### 4.3. Accounting for replication factor

Suppose v2 holds **1 TiB of compressed single-replica data** and the keyspace has RF=3 in one DC:

~~~text
Estimated 3-replica storage
≈ 1 TiB × 3 = 3 TiB

This is only a rough physical baseline,
excluding compaction temp space, metadata,
commit logs, hints, snapshots, or skew.
~~~

If the keyspace sets RF=3 in **two** datacenters, total replicas per partition equal 6, so budget capacity per DC separately. Never count free space in DC1 to offset a nearly full volume in DC2.

### 4.4. Disk stop thresholds

Before starting migration, agree on warning and **hard-stop** thresholds based on free bytes or usable percentage on the **worst node**, not cluster averages.

Illustrative operational rule (**example only, not a universal recommendation**):

~~~text
If any target replica hits:
    free disk < 25% of usable capacity
    or disk write latency p99 breaches SLO
    or compaction backlog grows continuously for > 30 minutes
=> PAUSE backfill, investigate, stop sending load.
~~~

Validate numbers like 25% and 30 minutes against your baseline, compaction strategy, disk size, and organizational policy. Different clusters need different thresholds.

## 5. Compaction amplification: why writing 1 GiB causes > 1 GiB of I/O

### 5.1. Lifecycle of newly written data

~~~mermaid
flowchart LR
    A["Backfill mutation"] --> B["Commit log + memtable"]
    B --> C["Memtable flush: new SSTable"]
    C --> D["Compaction reads older SSTables"]
    D --> E["Compaction writes merged SSTables"]
    E --> F["Source SSTables reclaimed when safe"]
    G["TTL / DELETE / updates"] --> D
~~~

When backfill writes rows into v2, they do not immediately land in a single optimized final file. Data flushes and gets rewritten repeatedly across subsequent compactions.

**Write amplification** is the ratio of total storage bytes written over the original logical payload. It depends on:

- Compaction strategy and SSTable sizes.
- Write/backfill ordering and concurrent active partitions.
- Updates, deletes, and TTLs/tombstones.
- Compression, partition width, and ingest speed.
- Concurrent streaming, repair, and flush I/O.

### 5.2. STCS, LCS, and TWCS behave differently

| Strategy | When suitable | Migration risks |
|---|---|---|
| **STCS** (SizeTieredCompactionStrategy) | Write-heavy workloads; merges similar-sized SSTables | Large compactions require big disk headroom; reads may touch many SSTables |
| **LCS** (LeveledCompactionStrategy) | Controls read amplification on read-heavy workloads | Updates/backfill cause high write amplification and heavy background I/O |
| **TWCS** (TimeWindowCompactionStrategy) | Mostly immutable, TTL/time-series data matching time windows | Backfilling old data at current times or late updates breaks window/tombstone assumptions |

Never switch v2 to TWCS merely because the partition key includes `order_month`. If historical orders keep receiving status UPDATEs months later, time-window immutability assumptions break down. Evaluate mutation patterns, TTLs, late arrivals, and version-specific strategy behavior.

### 5.3. Observe compaction instead of raising concurrency blindly

~~~bash
# Active and pending compactions on a node.
nodetool compactionstats

# SSTable count, read/write metrics, and table-level statistics.
nodetool tablestats commerce.orders_by_customer_month_v2

# Per-table histograms if supported by version.
nodetool tablehistograms commerce orders_by_customer_month_v2
~~~

`Pending tasks` is neither bytes remaining nor an ETA. A queue of 100 tiny tasks behaves completely differently from 10 huge tasks. Watch progress, disk latency, compaction throughput (bytes/s), and actual SSTable counts.

**Never raise `concurrent_compactors` or compaction throughput to "catch up faster" when disks are already saturated.** More threads simply contend for the same I/O, worsening read p99 and temporary free space. Conversely, throttling too low lets v2 backlogs grow unboundedly. Test and prepare rollback for any tuning change.

## 6. Replica load: source reads and target writes do not always spread evenly

### 6.1. Token ranges and partition keys

Partition keys hash to tokens; replica placement selects owning nodes. A backfill job reading **all large customers** sequentially can hammer the few replicas holding those partitions even when cluster-wide CPU looks idle.

In v1, one partition holds years of a customer's orders. In v2, the same history splits into monthly partitions, **changing token placement and target replicas**. The node serving source reads is not necessarily the node taking v2 writes.

Thus, capping only the number of **JVM workers** is insufficient. Monitor:

- Read/write throughput per **node** and DC.
- Pending/active tasks across stages in `nodetool tpstats`.
- Free disk and disk latency on the **worst node**.
- Driver in-flight requests and retries.
- Hot partitions, wide partitions, and token skew.

### 6.2. CL changes ACK requirements, not the query model

With RF=3 in one DC:

- `ONE` requires an ACK from one replica for the operation.
- `LOCAL_QUORUM` requires ACKs from two replicas in that DC.
- `ALL` requires all replicas.

A `ONE` write **does not mean** the mutation is sent to only one replica without loading peers. CL controls when the coordinator returns success, while the coordinator still sends mutations to replicas per the replication strategy and handles hints/failures underneath.

Backfill **should not arbitrarily drop CL** for speed at the expense of correctness. Reading source at `ONE` risks seeing unconverged replica state, whereas `LOCAL_QUORUM` waits for more responses; choose according to migration design, replica health, and reconciliation.

### 6.3. Cross-datacenter load

With multi-DC `NetworkTopologyStrategy`:

- Mutations to v2 replicate across multiple DCs.
- WAN links and remote DC disks can become bottlenecks.
- `LOCAL_QUORUM` ACKs from the local DC **without proving a remote DC achieved quorum** at return time.
- `EACH_QUORUM` (for supported **writes**) requires quorum in every DC and suffers higher WAN/availability sensitivity.
- Repairs and streaming compete for cross-DC bandwidth during migration.

Budget capacity and throughput **per DC**, never only cluster-wide totals.

## 7. Designing migration flows that avoid load spikes

### 7.1. Standard roadmap: expand → backfill → verify → switch → contract

| Phase | Key actions | Risks to control | Advancement gate |
|---|---|---|---|
| **Expand** | Create v2, deploy code understanding v1/v2 | Schema agreement, app compatibility | v2 exists; old clients still work |
| **Capture writes** | Implement dual-write or CDC/event log/upstream replay | Missed or misordered writes across tables | Reliable handling of ongoing mutations |
| **Backfill** | Copy historical data by partition/range | Read/write/compaction/disk pressure | Throttles, checkpoints, and alerts active |
| **Verify** | Reconcile partitions, rows, values, invariants | Missed data, TTL/tombstone drift | Discrepancies below approved threshold |
| **Switch reads** | Shift API reads to v2 via feature flag/canary | Read p99, query logic, duplicate/missing rows | SLOs healthy; read rollback ready |
| **Contract** | Stop old path, then drop v1 when eligible | Losing rollback path and backups | Retention, restore test, and approval complete |

**Never assume v2 is complete before backfill finishes** merely because a few sample SELECTs return expected rows.

### 7.2. Why is dual-write not automatically an atomic transaction?

A service may write v1 then v2:

~~~text
Write v1  -> SUCCESS
Write v2  -> TIMEOUT
API       -> what to return? how to retry v2? can v1 roll back?
~~~

Cassandra does not provide arbitrary multi-table ACID transactions by issuing two consecutive `INSERT`s. Logged batches do not replace cross-table business transactions either; batch atomicity/visibility guarantees are not equivalent to snapshot isolation or general-purpose CAS.

Therefore you need:

- An explicit **source of truth** during the transition window.
- Idempotent writes or auditable deduplication.
- Durable events/outbox/CDC/mutation logs to replay misses where appropriate.
- Handling for **UPDATE, DELETE, and TTL** mutations—not just immutable INSERTs.
- Parallel reconciliation and a clearly fenced cutover moment.

### 7.3. Backfill colliding with concurrent updates

Suppose order O1 updates status from `CREATED` to `PAID` while the job copies an older snapshot:

~~~text
10:00  Backfill reads v1: O1.status = CREATED
10:01  Live writer writes v1 and v2: O1.status = PAID
10:02  Backfill writes v2: O1.status = CREATED
~~~

If backfill stamps a newer timestamp than the live writer, the stale value **overwrites the newer value** under Cassandra's timestamp reconciliation. That is a severe correctness bug even with zero timeouts.

Mitigations include:

- Replaying mutations from an ordered log with a clear barrier/cutover.
- Backfilling only immutable or frozen partitions.
- Controlled preservation of timestamps/TTLs where appropriate, accounting for tombstone resurrection guards.
- Logical versioning or CAS where business rules compare state.
- Post-backfill reconciliation and discrepancy repair.

**Never apply `USING TIMESTAMP` across every row as a blanket trick.** Clock skew, DELETE/TTL timestamps, and concurrent updates must be analyzed per data model. A plain `SELECT` also omits mutation metadata needed for exact replay.

## 8. Checkpoints, idempotency, and pause/resume capability

### 8.1. A safe job must be pausable

A well-designed backfill can:

1. Complete a small work unit.
2. Persist a checkpoint **only after the unit's writes are applied and verified per policy**.
3. Pause cleanly on alerts or quorum loss.
4. Resume from checkpoints without corrupting data.
5. Reconcile completed vs. remaining scope.

Checkpoints can cover small partitions, primary-key groups, or split token ranges. Never use **rows read** as proof that replicas persisted the data.

### 8.2. Per-partition checkpoints and mid-run failures

~~~text
Work item:
    customer_id = C123

Status:
    PENDING -> RUNNING -> VERIFIED -> COMPLETE

Mark COMPLETE only when:
    all rows in snapshot/replay scope are processed;
    all writes ACKed at target CL;
    required validation passed.

If worker dies:
    re-claim work item per lease/retry policy;
    replay unverified scope using idempotent operations.
~~~

The checkpoint store is a logical control plane; it does not have to live inside the target Cassandra cluster. If stored in Cassandra, handle concurrency and worker races via appropriate LWTs/leases.

**Rewriting the same primary key with identical values may be idempotent for final state**, yet still unsafe when rows carry TTLs, update timestamps, counters, DELETEs, or external side effects. Analyze semantics before enabling retries.

### 8.3. Pagination also needs sound checkpointing

Driver page size **limits rows per fetch**, not total rows returned by a query. Paging state is an opaque protocol token to continue a compatible query—never treat it as a permanent durable business checkpoint.

On worker restart:

- Re-read a small partition from the start if operations are idempotent and scope is bounded.
- For large scopes, store business cursors by clustering keys and cutoff rules where valid.
- Never carry old paging states across query-shape, schema, or version changes without verification.
- Account for new mutations arriving mid-scan; paging does not provide a table-wide transactional snapshot.

## 9. Rate limiting: worker count, in-flight, rate, and bytes must work together

### 9.1. Four practical limits

| Mechanism | What it caps | Why one limit alone is insufficient |
|---|---|---|
| **Worker count** | Parallel processes/threads | One worker can still spawn hundreds of async requests |
| **Max in-flight** | Pending Cassandra requests | Large rows can saturate bytes/s even at low concurrency |
| **Rate limit** | Mutations or reads per second | Fails to cap byte spikes when record sizes vary |
| **Bytes budget** | Bytes read/written per second or batch | Fails to prevent tiny queries from exhausting coordinator overhead |

Hypothetical starting values **for testing only, not universal defaults**:

~~~text
Per migration job:
    max_worker_count     = 4
    max_in_flight_writes = 16
    write_rate_limit     = 500 mutations/s
    read_rate_limit      = 100 partitions/s

Global stop:
    worst-node free disk below approved threshold;
    write p99 or timeouts breach SLO;
    compaction backlog grows unrecoverably.
~~~

Across multiple jobs or pods, **500 mutations/s per pod is not 500 mutations/s cluster-wide**. Enforce a shared budget or coordinator so autoscaling does not multiply migration load unexpectedly.

### 9.2. Prefer adaptive throttling

A useful control loop:

~~~mermaid
flowchart TD
    A["Start at low rate"] --> B["Run across an adequate measurement window"]
    B --> C{"p99/errors/disk/free space/compaction OK?"}
    C -->|Yes| D["Step rate up slightly within cap"]
    C -->|No| E["Throttle down or PAUSE"]
    D --> B
    E --> F["Investigate bottleneck"]
    F --> G{"Safe to resume?"}
    G -->|Yes| A
    G -->|No| H["Hold PAUSE, escalate/roll back"]
~~~

**Never use average CPU alone** as permission to raise rate. A node with bad SSTable counts and disk write p99 can saturate long before cluster-average CPU climbs.

## 10. Java Driver 4.x example: intentionally slow, bounded-memory backfill

The code below illustrates **one customer work item**, paging v1 and writing v2 sequentially. It intentionally favors **load bounding** over peak throughput; production requires a job scheduler, checkpoints, metrics, auth/TLS, and guards against overwriting newer mutations.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.UUID;

public final class ConservativeOrderBackfill {
    private final CqlSession session;
    private final PreparedStatement source;
    private final PreparedStatement target;

    public ConservativeOrderBackfill(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.source = session.prepare(
            "SELECT created_at, order_id, amount, status " +
            "FROM commerce.orders_by_customer_v1 " +
            "WHERE customer_id = ?"
        );
        this.target = session.prepare(
            "INSERT INTO commerce.orders_by_customer_month_v2 " +
            "(customer_id, order_month, created_at, order_id, amount, status) " +
            "VALUES (?, ?, ?, ?, ?, ?)"
        );
    }

    public long copyCustomer(UUID customerId) throws InterruptedException {
        BoundStatement read = source.bind(customerId)
            .setPageSize(100)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM);

        long written = 0;
        ResultSet rows = session.execute(read);

        for (Row row : rows) {
            Instant createdAt = row.getInstant("created_at");
            UUID orderId = row.getUuid("order_id");
            BigDecimal amount = row.getBigDecimal("amount");
            String status = row.getString("status");

            // UTC is the bucketing contract for this migration.
            LocalDate month = createdAt
                .atOffset(ZoneOffset.UTC)
                .toLocalDate()
                .withDayOfMonth(1);

            BoundStatement write = target
                .bind(customerId, month, createdAt,
                      orderId, amount, status)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);
            written++;

            // Illustrates ~50 writes/s cap for ONE thread,
            // not a cluster-wide quota or bytes/s limit.
            Thread.sleep(20);
        }

        return written; // Do not mark COMPLETE before reconciliation.
    }
}
~~~

### 10.1. What does this code solve?

- Reuses `PreparedStatement`s for source and target.
- `WHERE customer_id = ?` avoids blind scans; each work item targets an explicit partition.
- `setPageSize(100)` bounds rows buffered per page, though it **does not** make a huge partition cheap.
- Iterating streams one row at a time instead of calling `ResultSet.all()` into memory.
- **Sequential** writes ensure at most one write in flight per worker.
- The 20 ms sleep illustrates single-worker pacing; replace with a **shared rate limiter** across multiple workers/pods.
- Writing the same primary key updates rows; pair with guards against overwriting newer live state and real TTL/timestamp preservation.

### 10.2. What does this code not solve?

- No CDC/replay or barrier protecting concurrent UPDATEs/DELETEs.
- No pre-check for oversized customer partitions before scanning.
- No checkpoints, cancellation, or cross-worker backpressure.
- No distinct handling for uncertain timeouts; exceptions simply propagate.
- No total bytes/s cap, concurrent-partition cap, or cluster-wide CPU/GC budget.
- No verification that target counts/values match source scope.
- Does not preserve source write timestamps or TTLs; **never run as a general correctness-preserving migration** where updates, TTLs, or deletes occur.

Add those safeguards **before** production use.

### 10.3. Async Driver: never spawn unbounded futures

When switching to `executeAsync()`, a common mistake is:

~~~java
// ANTI-PATTERN: spawns unbounded in-flight requests.
for (BackfillRow row : millionsOfRows) {
    session.executeAsync(buildWrite(row));
}
~~~

`buildWrite` and `BackfillRow` are placeholders. This loop neither awaits completion nor bounds concurrency nor handles failures.

Right pattern:

~~~text
Semaphore permits = MAX_IN_FLIGHT (e.g., 16)

for each source row:
    acquire permit (or wait for downstream readiness)
    send asynchronous write
    on completion:
        record outcome and latency
        release permit
    on error:
        apply bounded retry/stop policy

Checkpoint only after all required writes
for the work item are ACKed and verified.
~~~

Never perform blocking I/O inside driver callback threads. If delegating to a custom executor, bound its queue too; **a semaphore works only if acquired before submitting**.

## 11. Timeouts, retries, and backoff: keep the cluster healthy instead of piling on load

### 11.1. A timeout does not mean every replica failed to write

A write timeout can happen **after mutations reached some replicas**, falling short of required ACKs before the deadline. Uncontrolled retries amplify duplicate work and load.

Therefore:

1. Distinguish **unavailable**, **write timeout**, **read timeout**, **overload**, and data/schema errors.
2. Retry only semantically safe operations within bounded attempt caps.
3. Use **exponential backoff with jitter** and overall deadlines.
4. Throttle or pause when timeouts climb instead of inflating request timeouts to hide symptoms.
5. Reconcile outcomes whenever timeouts leave mutation persistence ambiguous.

### 11.2. Never treat counter increments as idempotent backfill

~~~cql
-- Do not use as a blind backfill retry mechanism:
UPDATE commerce.some_counters
SET counter_value = counter_value + 1
WHERE counter_id = 11111111-1111-1111-1111-111111111111;
~~~

Counter increments are not idempotent like rewriting the same primary key and values. For counter tables, design dedicated migration logic to establish logical totals without double-counting.

### 11.3. Avoid multi-partition logged batches

A giant `BEGIN BATCH` packing thousands of mutations across many partitions **is not a bulk import tool**. It creates batchlog pressure, oversized payloads, network/disk spikes, and timeouts.

If multiple rows share one partition and require bounded batching, check version semantics and benchmark. For distributed backfills, **throttled single prepared writes** or dedicated bulk tools are far more effective.

## 12. Snapshot space, backups, and when to drop the old table

During migration, keeping v1 is usually a **rollback prerequisite**. Yet dropping v1 too early and holding snapshots too long both carry risk.

### 12.1. Snapshots can pin old SSTables even after DROP

Cassandra snapshots typically create hard links to SSTable components. Files continue consuming disk until corresponding snapshots/hard links are cleared per policy. Thus:

- Disk usage does not necessarily fall immediately after `TRUNCATE` or `DROP` while snapshots pin SSTables.
- Reported sizes of snapshot and data directories may overlap on physical blocks due to hard links; know your disk-usage tooling.
- `nodetool clearsnapshot` deletes snapshots needed for rollback/restore; **never run it just to "free space" without approval**.
- Store off-node backups independently for disk/cluster recovery rather than relying solely on local snapshots on the same volume.

### 12.2. When to drop v1

Preconditions before retiring the old table:

- v2 data reconciled across partitions/token ranges and business invariants.
- Read traffic shifted and stable long enough to surface edge cases.
- Post-snapshot/backfill mutations captured, replayed, and reconciled.
- Zero remaining code or jobs reading v1.
- Restorable backups verified and retention approved.
- Sufficient disk/compaction headroom for safe cleanup.

**Never use `DROP TABLE` lightly or rush cleanup.** Once v1 is removed, reverting reads disappears or becomes costly; govern it via explicit change management.

## 13. Metrics and nodetool for monitoring migration impact

### 13.1. Three-layer dashboard

| Layer | Metrics to watch | What it reveals |
|---|---|---|
| **Application** | API read/write p50/p95/p99, timeouts, unavailables, retry rates, QPS | Whether migration degrades user SLOs |
| **Migration job** | Rows read/written, bytes/s, partitions/s, in-flight, checkpoint lag, error rates | Job speed, progress, and backlog |
| **Cluster/node** | Free disk/latency, compaction backlog, SSTables/read, commit log, flush queues, network, CPU/GC | Replica bottlenecks and background debt |

Never look solely at rows migrated/s. A fast job that spikes API timeouts **fails operational goals**.

### 13.2. Status inspection commands

~~~bash
# Replica status and DC/rack layout.
nodetool status

# Thread pools, pending queues, and dropped messages.
nodetool tpstats

# Active and pending compactions.
nodetool compactionstats

# Table-level storage and latency.
nodetool tablestats commerce.orders_by_customer_month_v2

# Per-table histograms if supported by version.
nodetool tablehistograms commerce orders_by_customer_month_v2

# SSTable streaming for repair/bootstrap/relocation (if active).
nodetool netstats

# Node overview, disk, and heap stats.
nodetool info
~~~

`netstats` does not display ordinary CQL backfill requests as SSTable streaming sessions. An empty `netstats` **can still accompany heavy read/write traffic** from Java backfill jobs. Watch node/network metrics and driver telemetry to see it.

### 13.3. Time-series snapshot example

~~~text
UTC          Job writes/s    Compaction pending   Worst-node free   API p99
09:00             100                 10              38%           80 ms
09:20             500                 45              34%          110 ms
09:40           1,000                130              27%          420 ms
09:45         PAUSED                 135              26%          500 ms
10:15               0                 70              26%          120 ms
~~~

This is **hypothetical data** illustrating how ramping load builds pressure and pausing lets the cluster drain backlogs. It **cannot prove causality alone**; inspect disk latency, traffic mix, compaction throughput, and concurrent events.

### 13.4. Watch the worst node; never hide capacity behind averages

If five nodes have 40% free disk and one node has 5%, **average free space** still looks comfortable—yet the 5% node can fail compaction long before peers suffer.

Alert on **minimum free bytes/percentage**, replica health, node roles, and growth rates. Never average per-node p99s into a fake cluster p99; use proper histogram aggregation.

## 14. Runbook: backfill drives up pending compactions and write p99

**Scenario:** the team enabled v1→v2 migration at 1,000 mutations/s. Within 40 minutes, pending compactions surge, one node drops to 18% free disk, and write p99 jumps from 40 ms to 700 ms.

### Step 1 — Assess impact

Record timestamps, job version, feature flags, CL, source/target tables, read/write QPS, timeouts, disk headroom, RF, and DC. Prioritize identifying **which user APIs** are breaching SLOs.

### Step 2 — Halt ramp-up, then pause if thresholds tripped

Use the job's built-in pause rather than killing processes mid-unit without checkpoints. If hard-stop thresholds trigger or disks near capacity, **pause immediately per runbook** while preserving manifests and checkpoints.

### Step 3 — Locate the bottleneck

- `compactionstats`: do pending tasks and throughput improve once paused?
- `tpstats`: do mutation/flush/read queues drain?
- Disk telemetry: write/read latency, free bytes, cloud volume throttling.
- `tablestats`: SSTables per read and v2 size.
- `netstats`: are repairs/bootstraps competing for I/O?
- Client: did retries multiply?

### Step 4 — Shed controllable competing load

Within authorized change schedules, pause or throttle other imports, non-urgent repairs/streaming, or overlapping batch jobs. **Never disable compaction long-term**, delete SSTables or commit logs, or drop CL to "fix" timeouts.

### Step 5 — Resume at a safer rate

Once backlogs drain and disk/latency stabilize, resume from checkpoints at a lower rate and step up gradually. Keep stop conditions active and watch live user traffic.

### Step 6 — Post-incident review

Log peak pending tasks, minimum free bytes, p99/timeouts, completed work items, safe sustainable rate, and capacity-planning gaps. Feed these numbers into future migrations rather than judging success only by final completion.

## 15. Runbook: v2 has missing rows or stale status

**Scenario:** backfill reports complete, yet v2 APIs miss new orders or show `CREATED` instead of `PAID`.

1. **Halt full read cutover** and keep v1 authoritative per plan.
2. Compare primary keys, business versions, and timestamps between v1 and v2 on sample partitions and affected windows.
3. Check source reads for incomplete paging, skipped timeouts, or premature checkpoints.
4. Check dual-write failures, CDC/event replay lag, and replica propagation delays.
5. Hunt for backfill writing newer timestamps over live mutations.
6. Check TTLs and DELETE/tombstones: rows may have legitimately expired or been deleted.
7. Fix reconciliation/replay logic and rerun small work units safely.
8. Switch reads only after invariants and scope verify cleanly.

Never default to full-table `SELECT COUNT(*)` for comparison, as it triggers costly full scans. Use token/partition sampling, key-identity checks, logical checksums, or controlled reconciliation jobs.

## 16. Testing rollout and rollback

### 16.1. Small-scope canary

A strong canary:

- Selects representative customers/partitions: small, wide, and update-heavy.
- Estimates expected rows/bytes and deadlines beforehand.
- Enables verified dual-write/capture.
- Backfills at a very low rate while measuring load on touched nodes.
- Compares v1/v2 data and API responses against business invariants.
- Scales incrementally—never jumping from 1% to 100% without verified disk headroom.

**Never canary only tiny partitions**: they hide wide-partition risks, compaction debt, and outliers.

### 16.2. Distinguish read rollback from schema rollback

| What must revert | Typical safe action | Risk |
|---|---|---|
| v2 API slow/incorrect | Switch reads back to v1 if v1 stayed current | Must prove v1 still holds all updates |
| Backfill overloads cluster | Pause and lower rate | Needs checkpoints/idempotency on resume |
| Dual-write failing | Disable/roll back code per runbook; replay gaps | v1/v2 data may have diverged |
| v2 schema flawed | Keep v1; create revised v2 and migrate cleanly | Never arbitrarily mutate v2 primary keys in place |
| Need to reclaim disk | Retire v1 **after passing all gates** | May lose rollback path; snapshots still pin space |

Write rollback plans **before running migration**, not after disks fill up.

### 16.3. Stagger resource pressure across phases

A production plan can separate phases:

~~~text
Phase 1: Create schema, deploy v1/v2-aware code
Phase 2: Capture new mutations, canary reads/dual-write
Phase 3: Throttled historical backfill by slice
Phase 4: Reconciliation and targeted repair off-peak
Phase 5: Canary -> full read cutover per SLOs
Phase 6: Retain v1 through retention/rollback window
Phase 7: Retire v1/snapshots per change and backup policy
~~~

Avoid running large backfills, topology changes, cluster-wide repairs, major compactions, and backups concurrently without a capacity plan. Yet **never defer critical repairs indefinitely** just for migration speed; coordinate data-safety schedules per policy.

## 17. Common mistakes

| Claim / action | Problem | Alternative |
|---|---|---|
| "Cassandra copies data when creating v2." | Creating a table never backfills v1 | Build a dedicated migration job |
| "RF=3 writes cost like one copy." | Replica fan-out and storage amplification | Budget RF, DCs, and physical bytes |
| "20% average free disk is plenty." | Node skew, compaction temp space, snapshots | Check worst node and leave headroom |
| "More backfill workers always runs faster." | Saturation, retries, and pending queues spike | Cap rate, in-flight, and bytes budgets |
| "Pending compactions high? Add threads." | Disks may already be saturated | Measure disk I/O and backlog trends |
| "Page size 100 caps query at 100 rows." | Paging does not cap total rows returned | Use scoped work items, LIMIT, and stop guards |
| "Re-inserting is always idempotent." | TTLs, timestamps, UPDATEs/DELETEs, side effects | Analyze write and replay semantics |
| "Multi-partition logged batches speed imports." | Batchlog/message overhead and timeouts | Use throttled single prepared writes or bulk tools |
| "`LOCAL_QUORUM` success means every DC has it." | Quorum applies only to local DC | Track cross-DC replication and CL needs |
| "Job read N rows so N rows are written." | Timeouts, premature checkpoints, dupes, skips | Verify logical contents and outcomes |
| "Drop v1 right after shifting reads." | Loses rollback path and unverified data | Keep through retention + restore test |
| "`netstats` empty means zero migration traffic." | CQL backfill is not SSTable streaming | Check driver, node network, and write metrics |
| "Disable compaction forever during backfill." | Unbounded SSTables, disk pressure, read amplification | Balance throughput and I/O per runbook |
| "Lower CL to cut p99 for free." | Changes consistency/correctness guarantees | Separate performance tuning from data guarantees |

## 18. Exercises with answers

### Q1 — Calculating storage peak

Cluster has 6 TiB v1 SSTables, estimated 5.4 TiB v2, and 1.5 TiB temporary peak. Total before snapshots, logs, and safety margin?

**Answer:** `6 + 5.4 + 1.5 = 12.9 TiB`. Across six balanced nodes, ~2.15 TiB/node; still inspect the worst node.

### Q2 — How does RF affect sizing?

v2 equals 1 TiB single-replica volume with RF=3. Is 1 TiB cluster-wide sufficient?

**Answer:** No. Baseline is ~3 TiB physical before compaction temp space, commit logs, snapshots, and skew.

### Q3 — Does LIMIT replace backpressure?

A job uses `LIMIT 500` per partition and page size 100, running 1,000 customers concurrently. Is it safe?

**Answer:** Not necessarily. Individual queries are bounded, yet aggregate in-flight, bytes/s, and replica hotspots can still overload the cluster; cap workers, rate, concurrency, and monitor nodes.

### Q4 — Rising pending compactions

`compactionstats` shows pending climbing rapidly while disk write p99 spikes. Raise compaction concurrency immediately?

**Answer:** No. If disks are saturated, higher concurrency worsens contention. Throttle backfill first and observe drain and capacity before tuning.

### Q5 — Dual-write timeout

v1 succeeded, v2 timed out. Can you conclude v2 definitely wrote nothing?

**Answer:** No. Some replicas may have applied the mutation before the client missed ACKs; use controlled retries, idempotency, reconciliation, and source-of-truth rules.

### Q6 — Backfill overwrites newer data

A live writer sets O1 to `PAID`, then backfill writes stale `CREATED` with a newer timestamp. How does this break?

**Answer:** Cassandra picks the backfill's higher timestamp, reverting status to `CREATED`. Enforce replay barriers, timestamp policies, versioning, or race guards.

### Q7 — Empty `netstats`

`netstats` shows zero streams while replica disk/network spikes during a Java backfill. Is this contradictory?

**Answer:** No. CQL client backfill generates read/write traffic rather than SSTable streaming sessions reported by `netstats`.

### Q8 — Verifying completion

A job writes 20 million rows and reports done; several v2 queries return valid data. Safe to drop v1?

**Answer:** No. Verify all work items, logical keys/values, concurrent mutations, TTL/DELETEs, and business invariants, then keep a rollback window and restorable backups.

### Q9 — Compaction strategy

Orders keep receiving status updates months after creation. Default v2 to TWCS just because it partitions by month?

**Answer:** No. TWCS fits workloads with matching TTLs/windows and minimal late mutations; prolonged updates violate window assumptions. Evaluate strategy against real workloads.

### Q10 — Dropping CL for speed

Workers hit `LOCAL_QUORUM` timeouts on slow replicas. Is switching to `ONE` just a speed optimization?

**Answer:** No. It alters read/write consistency guarantees and stale-replica exposure. Diagnose bottlenecks rather than weakening CL to hide them.

### Q11 — Premature checkpoint

A work item reads 10,000 rows, writes 9,000, and marks COMPLETE before the remaining 1,000 ACK. What is the risk?

**Answer:** On resume, those 1,000 uncertain rows are skipped. Persist checkpoints only after writes are ACKed and verified per policy.

### Q12 — Snapshots holding disk

After dropping v1, filesystem usage barely drops. What should you inspect?

**Answer:** Snapshots/hard links, backups/staging, pending compactions, and version-specific file reclamation. Never delete snapshots while still needed for rollback/restore.

## 19. Pre-, during-, and post-migration checklists

### Before migration

~~~text
[ ] v1/v2 schemas, partition keys, clustering keys, query shapes documented
[ ] RF/topology/DCs, read/write consistency levels confirmed
[ ] Source-of-truth inventory and dual-write/CDC/replay design ready
[ ] Idempotency, UPDATE/DELETE/TTL, and timestamp-conflict policies defined
[ ] Physical v1/v2 sizes, temp space, and snapshots budgeted
[ ] Per-node disk headroom, compaction strategy, SSTables/read checked
[ ] Worker, in-flight, rate/bytes quotas and stop conditions set
[ ] Baseline QPS, p50/p95/p99, timeouts, free disk, and compactions recorded
[ ] Checkpoints/leases, resume, and rollback rehearsed in staging
[ ] Operational access, change window, on-call, and backup/restore plans approved
~~~

### During migration

~~~text
[ ] Monitor worst node, not just cluster averages
[ ] Track job rows/s, bytes/s, errors, retries, and checkpoint lag
[ ] Monitor client SLOs and Cassandra read/write p99 simultaneously
[ ] Watch tpstats pending/dropped and compactionstats progress/backlog
[ ] Watch free disk/latency, flushes/commit logs, and other streaming/repairs
[ ] Throttle or pause when approved thresholds trip
[ ] Run random and per-token/partition reconciliation each wave
[ ] Never stack unbudgeted storage or topology changes mid-run
~~~

### After migration

~~~text
[ ] v2 satisfies query patterns and SLOs across canary and full traffic
[ ] Data and invariants verified, including concurrent mutations
[ ] Backfill/replay lag converged to acceptable levels
[ ] Compaction backlog, disk headroom, GC, and errors back to baseline
[ ] Restorable backups and rollback path retained long enough
[ ] v1/snapshots retired only after approval and retention checks
[ ] Document safe rates, real resource cost, duration, and lessons learned
~~~

## 20. Summary

Safe Cassandra data migration requires watching **six budgets simultaneously**:

1. **Compaction budget:** backfill generates new SSTables and write amplification; track pending tasks, SSTables per read, and disk I/O before increasing throughput.
2. **Storage budget:** hold v1 and v2 simultaneously plus compaction temp space, commit logs, snapshots, and headroom sized for the **most constrained node**.
3. **Replica/load budget:** every read/write hits multiple nodes by token, RF, CL, and DC; cap workers, in-flight, rate, and bytes/s across the full fleet.
4. **Correctness budget:** dual-write is not atomic; UPDATE/DELETE, TTLs, timestamps, concurrent writes, and retries can corrupt state even in fast runs.
5. **Observability budget:** monitor application, job, and cluster together; `tpstats`, `compactionstats`, `tablestats`, and `netstats` complement but never replace p99/error telemetry.
6. **Rollback budget:** keep v1, backups, checkpoints, and feature flags viable until v2 is thoroughly proven.

The deciding question is never "how many million rows per hour can we push?", but **"what pace preserves live user SLOs, leaves compaction headroom, avoids hotspotting any replica, and keeps business state accurate across pauses and restarts?"** A successful migration can **throttle down, pause, resume, and roll back cleanly**, backed by evidence of both data integrity and cluster health.
