# Evaluating Multi-Table Write Cost and Consistency Reconciliation

## Lesson Objectives

With query-driven design in Apache Cassandra, a single business entity may be stored across multiple tables to serve multiple read paths: lookup by ID, listing by customer, filtering by status, or reading chronologically. This **denormalization** typically reduces the number of partitions read, yet every create, update, or delete generates **multiple mutations**, extra data transfers, and the risk of tables falling out of sync.

This lesson belongs to the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It focuses on **evaluating multi-table write cost and consistency reconciliation** in Cassandra: from query contracts, CQL, replication, and consistency levels to network failures, tombstones, compaction, repair, and how a Java application maintains data projections.

After this lesson, you will be able to:

- Estimate **logical mutations**, bytes written, target partition counts, and replication impact when a domain workflow updates multiple projections.
- Weigh the gains of reduced **read fan-out** against increased **write amplification**, storage, and operational cost.
- Distinguish consistency **among replicas of one partition** from consistency **across business tables**; never confuse `LOCAL_QUORUM`, logged batches, LWTs, or repair with cross-table SQL transactions.
- Design a **source of truth**, revision/event IDs, projection update rules, and handling for duplicate writes, out-of-order arrivals, or partial failures.
- Build a **reconciliation** process with clear invariants, enumerable inputs, safe repair logic, and drift-detection metrics.
- Write illustrative CQL and Java code alongside failure test suites and operational criteria.

## 1. The Trade-Off: Simpler Reads, More Complex Writes

A multi-tenant e-commerce application has three requirements:

| ID | Read Behavior | Inputs the Caller Always Has | Desired Access Path |
| --- | --- | --- | --- |
| Q01 | Look up one order | `tenant_id`, `order_id` | One partition by ID |
| Q02 | List a customer's orders in a UTC month | `tenant_id`, `customer_id`, `month_bucket` | One partition, newest first |
| Q03 | List `PENDING` orders created on a day | `tenant_id`, `status`, `created_day` | One partition by status/day |

Assume Q02 and Q03 are both critical screens requiring low latency. With only an ID-keyed table, loading a list would require knowing many order IDs in advance. With only a customer-keyed table, Q03 does not know which customers have pending orders and must probe many partitions.

We can create **three tables for three query shapes**. Reads become simple, yet a new order must write to three places. When an order transitions from `PENDING` to `PAID`, a row must disappear from the old status partition and appear in the new status partition. If connectivity drops between operations, users may observe mismatched data.

That trade-off must be quantified:

```text
Fewer tables, fewer mutations
    -> may require reading many partitions and filtering/merging in the service

More query-driven projections
    -> read fewer partitions
    -> more mutations, storage, update complexity, and reconciliation
```

**Principle:** a projection table is worth adding only if the benefit of a **deterministic, bounded read path** outweighs the cost of **writing and maintaining business correctness** under real load.

## 2. CQL: Three Representations of the Same Order

The schemas below use text `tenant_id`, UUID `order_id/customer_id`, and buckets derived from **UTC order creation time**. They serve as self-contained examples for cost estimation and reconciliation.

### 2.1. Authoritative Lookup Table by ID

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    current_status text,
    total_amount decimal,
    updated_at timestamp,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

SELECT customer_id, created_at, current_status,
       total_amount, updated_at, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

In this example, the application treats `orders_by_id` as the **source state row that determines the current version**. `revision` is a business version assigned by the application/event pipeline; Cassandra **does not auto-increment** this field. The write mechanism must ensure older-version events cannot regress the source state backward.

### 2.2. List Projection by Customer/Month

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    current_status text,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, created_at, current_status, total_amount, revision
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

`month_bucket` follows `YYYY-MM` from `created_at` in UTC, e.g., `2026-11`. In this table, `current_status` is a regular data column that can be updated in place on the same row when status changes.

### 2.3. Queue Projection by Status/Creation Day

```sql
CREATE TABLE orders_by_status_day (
    tenant_id text,
    current_status text,
    created_day date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, current_status, created_day),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, customer_id, created_at, total_amount, revision
FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = 'PENDING'
  AND created_day = ?
LIMIT 50;
```

Here `created_day` means **UTC order creation date**, not the date the order moved to `PENDING`. Because `current_status` is in the partition key, status changes cannot update a regular column in place: you must **delete the row from the old status key and insert a row under the new key**.

All three tables allow a critical query to read **one logical partition** when the caller supplies the full key. However, the status/day table can grow oversized or hot when a tenant has many orders in a single status. CQL validity is **not yet** SLA validation.

## 3. Counting Mutations on the Write Path

Before optimizing, distinguish three quantities:

- **Logical mutation:** a write/delete operation requested by the application on one table/partition, such as one `INSERT` or `DELETE`.
- **Replica application:** Cassandra distributes each mutation to replicas per keyspace strategy/replication factor; do not equate one logical mutation with one physical disk write.
- **Actual I/O:** commit log, memtable, SSTables, compaction, retries, tombstones, network, and internal steps. This cost must be measured rather than deduced solely from CQL statement counts.

### 3.1. Creating a New Order

With the three tables in Section 2:

```sql
INSERT INTO orders_by_id (
    tenant_id, order_id, customer_id, created_at,
    current_status, total_amount, updated_at, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, month_bucket, created_at,
    order_id, current_status, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_status_day (
    tenant_id, current_status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

That is **at least three logical mutations** for one order-creation event considering only these three projections. If there is also a durable event log, audit table, external-reference lookup, or index, operation count and storage grow further.

### 3.2. Transitioning an Order's Status

Suppose an order created on Nov 21 is `PENDING`, and then transitions to `PAID`. A straightforward model performs:

1. Update `orders_by_id` with `current_status = PAID` and the new revision.
2. Update `orders_by_customer_month` with the new status/revision.
3. `DELETE` the old row in `orders_by_status_day` under `PENDING`.
4. `INSERT` the new row in `orders_by_status_day` under `PAID`.

```sql
-- 1. Business logic has accepted the order status transition.
UPDATE orders_by_id
SET current_status = ?, updated_at = ?, revision = ?
WHERE tenant_id = ? AND order_id = ?;

-- 2. Update regular columns in the customer/month table.
UPDATE orders_by_customer_month
SET current_status = ?, revision = ?
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;

-- 3. Delete the row from the old status partition.
DELETE FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;

-- 4. Insert the row into the new status partition.
INSERT INTO orders_by_status_day (
    tenant_id, current_status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

**Four logical mutations** is the count for **this illustrative scenario**, excluding event-log writes, idempotency checks, retries, conditional operations, or extra tables.

The `UPDATE orders_by_id` statement above **does not enforce version-concurrency control on its own**. It only illustrates a mutation after the system has validated the new revision; if multiple writers can operate concurrently, you need CAS/LWT or an appropriate serialized writer (covered later).

### 3.3. A Simple Estimation Model

Let:

```text
C = new orders per second
U = status-transition events per second
Pcreate = logical mutations per order creation
Pupdate = logical mutations per status transition

logical_mutations_per_second ≈ C × Pcreate + U × Pupdate
```

Suppose **800 new orders/second** and **200 status transitions/second**:

```text
Pcreate = 3
Pupdate = 4
logical mutations/s = 800 × 3 + 200 × 4
                    = 2,400 + 800
                    = 3,200
```

With a keyspace replication factor `RF = 3` and assuming every mutation applies to three replicas, a high-level estimate is **3,200 × 3 = 9,600 replica-level mutation applications per second**. This multiplication **illustrates target load**, **not** exact disk I/O, network packets, or physical writes: replica placement, consistency, retries, batchlogs, topology, and compaction change actual cost.

If `Pcreate` rises from 3 to 6 because three more projections are added, the minimum increase is `800 × 3 = 2,400 logical mutations/second` on order creation alone, before even counting updates. Therefore, every new projection needs a **read-path justification** and benchmark results.

### 3.4. Estimating Storage and Write Amplification

Suppose the three representations of one order have average raw payload sizes:

| Representation | Raw Data/Order (Assumed) | Role |
| --- | ---: | --- |
| `orders_by_id` | 500 B | Detail/summary |
| `orders_by_customer_month` | 180 B | Customer list |
| `orders_by_status_day` | 160 B | Status queue |
| **Total** | **840 B** | Excludes replication/overhead |

Compared with 500 B in a single table, raw data across three representations increases by about `840 / 500 = 1.68` times. **This is not the real disk multiplier**: primary key sizes, metadata, compression, tombstones, memtables/SSTables, partition indexes, and replication must all be measured.

For status-changing rows, `DELETE` generates tombstones and `INSERT` writes new rows; frequent `status` churn can drive **actual bytes written and transient storage usage** up much faster than live-row size alone predicts.

## 4. What Do Reads Gain When Accepting Multiple Tables?

Do not count write mutations while forgetting the **read amplification** of having no projection.

| Criterion | Customer/Month Table Only | Plus Status/Day Table |
| --- | --- | --- |
| Q02: customer/month | Direct single partition | Still direct on customer/month table |
| Q03: tenant-wide, status/day | Unknown which customers hold data; risks probing many partitions | Known `(tenant, status, day)` partition key |
| Filtering `PENDING` | May require app-side data filtering | `PENDING` is part of the partition key |
| Sorting list | Merge/sort across many streams | Pre-clustered by `created_at DESC` in partition |
| Write load | Fewer mutations | Extra mutations and tombstones on status transitions |
| Other risk | High, unpredictable fan-out latency | Status partition can become too hot |

Suppose a tenant has **50,000 customers**. If the queue query must probe a large fraction of those customers, read pressure looks drastically different from querying a status partition directly. Conversely, if status/day accumulates millions of rows or churns extremely fast, the projection itself can become a hotspot.

When a `(tenant_id, current_status, created_day)` partition becomes too hot, add `shard_id` to the partition key using a stable hash of `order_id`. Queue reads then fan out across **N known shards** and merge results. That trades **unbounded or huge fan-out** for **bounded fan-out**, at the cost of extra pagination complexity and shard-rule versioning.

Decisions to add projections or shards must be based on **QPS, p95/p99, skew, bytes/partition, transition frequency, tombstones, storage cost, and target consistency**, not merely because CQL executes.

## 5. Three Consistency Layers Not to Confuse

### 5.1. Consistency Among Replicas of the Same Partition

Cassandra distributes a partition's data to replicas per keyspace configuration. An operation's consistency level (e.g., `ONE`, `LOCAL_QUORUM` in an appropriate topology) defines replica acknowledgment for reads/writes.

Picking the right consistency level supports read-your-writes requirements on **the same data** given a suitable replication factor. It cannot conjure a mutation that **was never sent** to a projection table.

### 5.2. Business Consistency Across Projection Tables

If `orders_by_id` is already `PAID` while the consumer has not yet updated `orders_by_status_day`, querying the status table may still return the `PENDING` row or miss the `PAID` row. This is **projection lag or a dropped mutation**, not a matter of choosing `LOCAL_QUORUM` on the status query.

A product spec must clarify:

- Which table needs **read-your-writes** and immediately after which command?
- How far behind the source may secondary lists lag?
- Is it acceptable for an order to appear temporarily in both queues?
- How should the API behave when the source updated but projections have not yet converged?

Never claim "eventual consistency" is a complete solution without **durable event emission, retries, and reconciliation**: if a mutation is permanently lost, the system will never converge by waiting.

### 5.3. Consistency When Reading Multiple Partitions or Tables

Even when individual queries use strong consistency levels, two `SELECT` calls at two instants across two partitions do not automatically form a **shared transactional snapshot**. Data can change between reads. Multi-bucket pagination likewise does not guarantee an immutable snapshot under concurrent writes/deletes.

Distinguish the goals clearly:

| Goal | Approach to Consider |
| --- | --- |
| Read authoritative status of one order | Read `orders_by_id` per consistency contract |
| Lists may lag by a few seconds | Async projections + lag SLO and monitoring |
| Avoid applying a transition twice | Idempotency key/sequence and source transition control |
| Audit events must not be lost | Durable event log and tested recovery workflow |
| Multi-table state must match after convergence | Invariants, reconciliation, and replay/rebuild capability |

## 6. How Far Do Logged Batches, LWTs, and Timestamps Go?

### 6.1. CQL `BATCH` Is Not a Cross-Table SQL Transaction

`BEGIN BATCH ... APPLY BATCH` groups mutations. A **logged batch** supports atomicity in the sense that accepted mutations can be replayed during failure recovery so they are eventually all applied, yet it **does not provide cross-partition isolation like SQL**: readers can observe updates in some tables/partitions while others are still pending.

Do not use multi-partition batches as a default throughput optimization. With many partitions, batchlogs and coordinators bear extra load. Nor does a batch check whether "revision 11 is overwriting revision 12."

### 6.2. LWT/CAS for Conditional Control on Source State

When the domain must ensure an order transitions only from a known revision, you can use a **lightweight transaction** on the `orders_by_id` row:

```sql
-- Assumes source row exists and expectedRevision is known to the caller.
UPDATE orders_by_id
SET current_status = ?,
    updated_at = ?,
    revision = ?
WHERE tenant_id = ?
  AND order_id = ?
IF revision = ?;
```

The application must check `[applied]`, handle contention, and verify `nextRevision` is a valid business version. Cassandra does not infer from setting `revision = 13` that 13 legitimately follows 12. LWTs add round-trips and coordination overhead, so use them only when the consistency contract requires them.

**An LWT on one source row does not turn mutations to the customer/month and status/day tables into an isolated cross-partition transaction.** Only **accepted** transitions enter the projection synchronization pipeline.

### 6.3. Do Not Treat Write Timestamps as Business Revisions

Cassandra resolves regular cell conflicts by write timestamp; an earlier business event arriving later at the server can still overwrite newer data if the pipeline updates unconditionally.

Do not use client/server wall clocks as business sequence numbers without explicit control. `USING TIMESTAMP` likewise does not provide transactions, deduplication, or transition validation; combining it with `DELETE`/tombstones requires extra care.

## 7. Failure Matrix: Why Projections Can Drift

| Scenario | Symptom | Handling |
| --- | --- | --- |
| Source succeeds, customer/month fails | Order detail is newer than customer list | Retry/replay mutation from accepted revision |
| Source is `PAID`, deleting `PENDING` fails | Order lingers in PENDING queue | Retry delete using **old key**, reconcile extra rows |
| `PENDING` deleted, inserting `PAID` fails | Order temporarily missing from all queues | Retry insert of new row, reconcile missing rows |
| Timeout after Cassandra applied write | Caller unsure if write succeeded or failed | Use stable ID/revision, safe retries, and re-check |
| Event delivered twice | Projection reprocesses or refreshes TTLs | Dedupe/sequence, idempotent mutations, clear retention |
| Revision 12 arrives before revision 11 | Risk of regressing status backward | Order per order ID, enforce revision at source |
| Consumer crashes after updating one projection | One table new, another stale | Durable log, proper checkpointing, replay |
| `customer_id` or `created_at` changes | Old row remains in old partition/bucket | Track old/new keys, delete/write via migration flow |
| Projection has shorter TTL than source | List row disappears before order detail | Align retention policies or define separate lifecycles |
| Node/replica temporarily unreachable | Replica may need repair | Manage replication/CL and repair; **do not confuse** with projection sync |

A naive "rewrite all tables anytime" retry is not always safe. If revision 11 failed, revision 12 completed, and later retrying revision 11 runs unchecked, it could **re-create the stale `PENDING` row**. Combine **processing order, idempotency, and reconciliation**, not merely "at-least-once" delivery.

## 8. Defining Source of Truth and Invariants Before Reconciling

**Reconciliation** compares projections against trusted state, identifies missing/extra/stale entries, and repairs them safely. You cannot build correct reconciliation without first answering "what is the truth?"

In this example, choose:

- `orders_by_id` holds the latest **revision-accepted** state.
- A **durable event source** records accepted transitions, including `event_id`, `revision`, `old_status`, `new_status`, tenant/order IDs, customer, `created_at`, and processing time. This source supports replaying transitions and knowing which old keys to delete. It can be any purpose-built event stream/durable log; this lesson does not assume a single technology.
- The two list tables are **projections** rebuildable from verified source metadata.

### 8.1. Illustrative Invariants

For an order whose source state is `PAID`, revision 12, `customer_id = C`, and `created_at = T`:

| Code | Invariant After Projections Converge |
| --- | --- |
| I1 | `orders_by_id` row reflects accepted status `PAID` and revision 12 |
| I2 | Row `(tenant, C, month(T), T, orderId)` in `orders_by_customer_month` exists with matching status/revision |
| I3 | Row `(tenant, PAID, day(T), T, orderId)` in `orders_by_status_day` exists with matching revision |
| I4 | Old status/day rows for this order under **prior statuses** no longer exist after convergence |
| I5 | Projections within retention policy are queryable; expired entries follow the retention contract |

I4 does not mean Cassandra offers a cheap "find order ID across all status/day partitions" lookup. To know which old keys to check, the system relies on **the event log, change manifests, or domain-known status sets**. Avoid full-table scans per order.

### 8.2. Reconciliation Must Not Overwrite Newer Data

Suppose a reconciliation job reads the source at revision 12 and prepares to patch a projection. Meanwhile, the source advances to revision 13. If the slow job writes revision 12 data after the revision 13 mutation, the **repair job itself** corrupts the table.

Enforce at least one control mechanism:

- Sequential processing / logical locking per `(tenant_id, order_id)` shared by projection mutations and repair.
- Reliable snapshot/version watermarks, re-reading source state before applying fixes under contention.
- Revision checks/mutation models strong enough to **ignore stale repairs**; never assume storing a `revision` column in a row automatically blocks stale writes.

Without this safeguard, reconciliation can worsen consistency.

## 9. An Operational Reconciliation Workflow

A practical workflow splits into **near-real-time reconciliation** and **periodic batch reconciliation**.

### 9.1. Discovering Entities to Check

Never start by running `SELECT * FROM orders_by_id` to scan all of Cassandra on the request path. Cassandra is optimized for partition-key lookups, not unbounded online scans.

Build a **bounded list of IDs to reconcile** from:

1. Accepted events in the durable log over a time window.
2. Failed or timed-out mutations in retry/dead-letter queues.
3. IDs flagged by business checks or user reports.
4. Batches of IDs intentionally tracked in a maintenance job manifest/input.

Cap batch size, QPS, runtime, and checkpoint progress; never let a reconciliation job compete uncontrollably with production queries.

### 9.2. Comparing by Full Primary Keys

For each `(tenant_id, order_id)`:

1. Read the `orders_by_id` source row and its current revision.
2. Compute `month_bucket` and `created_day` from the source's **UTC `created_at`**.
3. Read the customer/month row using its **full partition and clustering key**.
4. Read the status/day row for the **current status**.
5. From the event log/manifest, identify **previously held** statuses/buckets and check for orphan rows to delete.
6. Compare ID, status, revision, and any projection attributes governed by sync contracts.

Example CQL checking a specific row in the customer/month table:

```sql
SELECT current_status, total_amount, revision
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;
```

And a status row:

```sql
SELECT revision, total_amount
FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;
```

The key is **knowing the full keys to check**, never adding `ALLOW FILTERING` to hunt for an order ID across all partitions.

### 9.3. Classifying Discrepancies

| Type | Example | Desired Action |
| --- | --- | --- |
| `MISSING` | Source is `PAID` but PAID row is absent in status/day | Recreate row at the right key |
| `STALE` | Customer/month still shows `PENDING` rev 11 while source is `PAID` rev 12 | Update projection columns per valid revision |
| `ORPHAN` | Old PENDING row still exists after transition to PAID | Delete row at confirmed old key |
| `MISMATCH` | Total amount in projection differs from source | Verify authoritative source and patch allowed fields |
| `EXPIRED_EXPECTED` | Projection expired via TTL per policy | Do not resurrect expired data |
| `IN_FLIGHT` | Recent mutation still within lag SLO | Observe and wait within allowed lag window before alerting |

Distinguishing `IN_FLIGHT` from real failures stops the job from thrashing projections that are updating normally. However, waiting too long hides real errors; define lag SLOs and classify by event age.

### 9.4. Controlled Repair

Conceptual algorithm:

```text
for each orderKey in boundedManifest:
    source = readOrdersById(orderKey)
    if source absent:
        apply deletion/retention policy; do not assume every absence is error
        continue

    expectedCustomerKey = keyFrom(source.customerId, source.createdAt)
    expectedStatusKey = keyFrom(source.status, source.createdAt)
    oldStatusKeys = lookupKnownHistoricalKeysFromDurableEvents(orderKey)

    observed = readExpectedProjectionRowsAndKnownOldKeys(...)
    discrepancies = compare(source.revision, source.fields, observed)

    if discrepancies:
        verify source is still current / acquire per-order sequencing
        repair missing/stale expected rows
        remove known orphan rows using exact old primary keys
        verify or enqueue a new bounded verification pass

    record outcome and advance checkpoint only after safe handling
```

If an error occurs mid-run, the job must resume without corrupting data. Never delete old rows without verifying source state or confirming the old key is genuinely obsolete. Never force every projection to share one TTL if their lifecycles were designed separately.

### 9.5. Reconciliation Metrics and Alerting

Track at least:

| Metric | Meaning |
| --- | --- |
| `projection_lag_seconds` per table | Age of source changes not yet reflected in projection |
| Retry / dead-letter mutation count | Indicator of delivery failures or non-recoverable errors |
| `missing/stale/orphan/mismatch` over time | Breakdown of drift causes |
| Entities checked and checkpoint progress | Whether the job is advancing and covering enough data |
| Repair success rate and retry counts | Measures reconciliation effectiveness and impact |
| p95/p99 read/write latency | Tracks the ongoing cost of denormalization |
| Largest partition, tombstones scanned | Detects degradation in status or history tables |
| Oldest backlog age | Detects unconverged events breaching committed SLAs |

Alert thresholds must align with product SLAs and real measurements; there is no universal lag or partition-size threshold for every Cassandra cluster.

## 10. Java: Calling the Right Projection and Handling Updates

Example using **DataStax Java Driver 4.x** for a consumer receiving **accepted transitions**. This assumes upstream guarantees per-order revision ordering and retains durable events for retries/reconciliation; without those guarantees, this snippet is **unsafe** against out-of-order events.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.UUID;

public final class OrderProjectionWriter {
    private final CqlSession session;
    private final PreparedStatement updateCustomer;
    private final PreparedStatement deleteOldStatus;
    private final PreparedStatement insertNewStatus;

    public OrderProjectionWriter(CqlSession session) {
        this.session = session;
        this.updateCustomer = session.prepare(
            "UPDATE orders_by_customer_month " +
            "SET current_status = ?, revision = ? " +
            "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ? " +
            "AND created_at = ? AND order_id = ?"
        );
        this.deleteOldStatus = session.prepare(
            "DELETE FROM orders_by_status_day " +
            "WHERE tenant_id = ? AND current_status = ? AND created_day = ? " +
            "AND created_at = ? AND order_id = ?"
        );
        this.insertNewStatus = session.prepare(
            "INSERT INTO orders_by_status_day (" +
            "tenant_id, current_status, created_day, created_at, " +
            "order_id, customer_id, total_amount, revision) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        );
    }

    // Call only with accepted source transitions processed in order.
    // On failure, retain the durable event for retry/reconciliation.
    public void projectStatusChange(
        String tenantId, UUID orderId, UUID customerId,
        Instant createdAt, String oldStatus, String newStatus,
        BigDecimal totalAmount, long revision
    ) {
        String month = YearMonth.from(
            createdAt.atZone(ZoneOffset.UTC)
        ).toString();
        LocalDate day = createdAt.atZone(ZoneOffset.UTC).toLocalDate();

        session.execute(updateCustomer.bind(
            newStatus, revision, tenantId, customerId, month,
            createdAt, orderId
        ));
        session.execute(deleteOldStatus.bind(
            tenantId, oldStatus, day, createdAt, orderId
        ));
        session.execute(insertNewStatus.bind(
            tenantId, newStatus, day, createdAt, orderId,
            customerId, totalAmount, revision
        ));
    }
}
```

The code shows **only projection mutations**; accepting the new state in `orders_by_id` and writing the durable log happen in another layer. These `session.execute` calls do not form a cross-table transaction: if the second statement succeeds and the third fails, the status projection is temporarily incomplete.

For production operation, add:

1. **Checkpoint only after safe completion:** never mark an event permanently processed while a projection is missing.
2. **Per-order ordering:** never let a retry of revision 11 apply after revision 12; if ordering is not guaranteed, check source/revision and repair safely.
3. **Ambiguous timeouts:** Cassandra may have applied the write while the client lost the ACK; retries must be safe and not create rows under different keys.
4. **Consistency level:** choose per topology and SLA; never assume one mutation's CL synchronizes multiple tables.
5. **Tenant authorization:** having tenant in the partition key does not grant access automatically; the API must still enforce authorization.
6. **Observability:** instrument each mutation step and route failed events to a retryable queue.

`CqlSession` should be managed over the application lifecycle, not created per update. `Instant` maps to CQL `timestamp`, `LocalDate` to `date`, `UUID` to `uuid`, and `BigDecimal` to `decimal`. Bucketing must consistently use UTC across writes, reads, and reconciliation.

### 10.1. Why Not Just Wrap It in a `BATCH` in Java?

A logged batch helps replay all mutations after a crash under batch semantics, yet it does not solve **out-of-order revisions**, provide cross-partition snapshots, or replace an event log and reconciliation. Frequent updates across many partitions can also overload coordinators and batchlogs; benchmark before choosing.

When projections are maintained by asynchronous consumers, the sound flow is typically: **accepted transition → durable event → update projections → verify/checkpoint progress → retry/reconcile when needed**, rather than "fire writes at three tables and hope they stay equal."

## 11. Tombstones, TTL, Compaction, and Repair

### 11.1. Hidden Cost When Status Is Part of the Key

Every `PENDING → PAID` transition creates at least one tombstone for the old status row before compaction purges old data when eligible. A queue with heavy status churn can read many tombstones even when `LIMIT 50` returns only 50 live rows.

Monitor tombstones scanned, SSTables-per-read, write latency, and partition hotness; never assume a status table stays cheap merely because queries target a single partition.

### 11.2. Differing TTLs Across Projections

The ID table may need to retain state for the entire order lifecycle, while list tables have shorter retention policies. If a projection expires via TTL before reconciliation runs, the repair job must not blindly recreate old rows without checking **retention policy**. Conversely, if the source is deleted without cleaning secondary tables, stale entries can linger in status lists.

TTL applies to written cell values and can generate tombstones; replays/updates can alter cell expiration. Lock down retention windows, deletion behavior, and GDPR/compliance handling in the business layer when required.

### 11.3. Compaction and Repair Do Not Fix Projection Logic Bugs

Compaction organizes SSTables and purges expired data/tombstones when eligible; it will not create a `PAID` row the application never wrote. Repair synchronizes replicas via Cassandra's anti-entropy mechanisms; it does not know an order lingers in `PENDING` because a consumer missed a `DELETE`.

Never shrink `gc_grace_seconds` arbitrarily to purge tombstones faster; deletion safety depends on replica health, repair schedules, and operational policy. For projection tables with TTLs and frequent deletes, monitor both **tombstone load** and **expiration correctness**.

## 12. Fault Testing and Decision Checklist

### 12.1. Minimum Test Scenarios

| Scenario | Invariant to Observe After Convergence |
| --- | --- |
| Normal order creation | Source row, customer/month row, status/day row all present |
| Transition `PENDING → PAID` | Source/customer share revision; PAID present, PENDING absent |
| Old-status delete times out | Retry/reconciliation removes old row; no lasting orphan |
| New-status insert fails | Retry restores missing row |
| Rapid transitions rev 11/12/13 | Final state reflects latest version; old replay cannot regress |
| Consumer restarts mid-batch | No lost events; accurate checkpoint and recovery |
| Tenant with huge PENDING partition | Meets p95/p99 targets or triggers sharding plan |
| Projection expires before source | Obeys retention; reconciliation does not violate policy |
| Node/replica temporarily down | Handled by CL/repair; not confused with business sync bug |
| Reconciliation runs concurrently with transitions | Job never overwrites newer state after a transition |

### 12.2. Design Checklist

| Question | Acceptance Criterion |
| --- | --- |
| Which query shape does the projection serve? | Query ID, inputs, partition key, sort, and SLA documented |
| Are mutations counted? | Create/update/delete paths mapped, including delete+insert on key change |
| Are costs forecast? | Read/write QPS, bytes, RF/topology, tombstones, peak partition |
| What is the source of truth? | Single place/process governing accepted revision and state |
| Is there a durable event log? | Replayable after failures without losing transitions |
| Are mutation retries safe? | Stable IDs, ordering control, and idempotency tested |
| Is sync lag defined? | Projection lag SLO and stale-read behavior explicit |
| Are reconciliation inputs bounded? | Durable log, manifest, or bounded enumerable key list |
| Are invariants and repair safe? | Detects missing/stale/orphan; blocks stale revision repairs |
| Are replica repair and reconciliation separated? | Distinct runbooks for node faults vs. business drift |
| Benchmarked on extreme data? | p95/p99, largest partition rows/bytes, tombstones, write throughput |

## 13. Practice Exercise

A Java support-ticket system wants to serve three APIs:

```text
R1. Look up a ticket by (tenant_id, ticket_id).
R2. List a requester's 20 most recent tickets in a month.
R3. List OPEN tickets created on a day for a tenant, newest first.
```

Each ticket has `ticket_id`, `requester_id`, `created_at`, `status`, `priority`, and `revision`. The ID table is the source of truth; the other two tables are projections.

**Tasks:**

1. Propose partition keys and clustering keys for all three tables; explain why R3 should not scan across all requester/month partitions.
2. Count the minimum logical mutations if a new ticket writes all three tables, and one `OPEN → RESOLVED` transition updates two tables, deletes the OPEN row, and inserts the RESOLVED row.
3. Suppose load is **300 new tickets/second** and **100 status transitions/second**. Compute logical mutations per second with `Pcreate = 3`, `Pupdate = 4`, excluding event logs and retries.
4. With `RF = 3`, compute the rough high-level estimate of replica-level mutation applications by simple multiplication; explain why that is not actual disk I/O.
5. List three discrepancies that can occur if failure strikes after deleting OPEN but before inserting RESOLVED; propose detection and repair steps.
6. A reconciliation job reads revision 8 while the source advances to revision 9. What condition must the job enforce before patching projections so it does not reinstate version 8 data?
7. Explain why `LOCAL_QUORUM` or a logged batch does not replace event-ordering management and business reconciliation.

**Reference guidance:** R1 keys by `(tenant_id, ticket_id)`; R2 keys by `(tenant_id, requester_id, month_bucket)` with clustering `created_at DESC, ticket_id DESC`; R3 keys by `(tenant_id, status, created_day)` with similar clustering, and `created_day` must consistently derive from creation time if the requirement says "created on that day." Calculation in Question 3: `300 × 3 + 100 × 4 = 1,300 logical mutations/second`; with `RF = 3`, high-level estimate is `3,900 replica-level applications/second`. Count extra if log/dedupe tables or retries exist. After deleting OPEN before inserting RESOLVED, source and requester tables have changed while the status list lacks a row; reconciliation by revision and full keys must restore RESOLVED without resurrecting stale OPEN. The reconciliation job must verify the latest revision or execute under per-ticket serialization before writing.

## Conclusion

Adding projection tables in Cassandra is a trade-off that **exchanges write cost for efficient read paths**. Evaluation goes beyond counting `INSERT`s or duplicated bytes: include key transitions, tombstones, retries, replication, sync lag, and the operational cost of keeping state accurate. Consistency levels, LWTs, batches, compaction, and repair solve distinct problems; none turns multiple projections into a cross-table transaction. For reliable denormalization, establish **a source of truth, revisions, durable events, invariants, reconciliation, and load measurements** before committing SLAs on read paths.
