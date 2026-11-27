# Redesigning When Access Patterns Change

## Lesson Objectives

Apache Cassandra is typically designed **from the queries it must serve**: the partition key locates data across the distributed cluster, while clustering columns sort rows within a partition. Consequently, a schema that serves an application well today may fail when new screens arrive, customers grow larger, peak traffic shifts, or retention policies change.

A critical trait is that **you cannot alter an existing partition key with a few `ALTER TABLE` statements and expect historical data to automatically redistribute**. When access patterns genuinely change, you usually need a new query-driven table, data synchronization rules, backfill, reconciliation, and a controlled read-path cutover plan.

This lesson belongs to the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects partition keys, clustering, CQL, replication, read/write consistency, compaction, repair, partial failures, and how Java applications execute schema transitions.

After this lesson, you will be able to:

- Detect access-pattern shifts using a query inventory, frequency, p95/p99 latency, fan-out, and data distribution.
- Distinguish cases where adding a regular column or compatible index suffices from cases **requiring a new access path**.
- Design a **v2** table with new partition/clustering keys without overwriting or breaking the v1 read path.
- Coordinate live changes, backfill, revisions, deduplication, shadow reads, and data validation before shifting traffic.
- Handle key-changing state transitions, late events, TTLs, tombstones, mid-mutation failures, and rollbacks.
- Build a migration plan with stage gates, observability metrics, and resource caps.

## 1. A Good Schema Can Become an Unsuitable Schema

Suppose a multi-tenant order system initially only has the requirement:

> View the 50 most recent orders for a customer within a UTC month.

The original table was designed with partitioning by tenant/customer/month and clustering by creation time:

```sql
CREATE TABLE orders_by_customer_month_v1 (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

v1 query:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month_v1
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

In this query, the caller supplies the full partition key. Cassandra routes to the replica set holding the target partition and takes the top rows in clustering order. This is a sound choice for the **initial access pattern**.

Months later, product adds an operations screen:

> View the 50 **currently `PENDING`** orders created on **UTC day X**, across the **entire tenant**, newest first.

The new query knows only `tenant_id`, `status`, and `created_day`. It **does not know `customer_id`** for each order. Trying to reuse v1 forces the application to fetch a huge list of customers, query many partitions, and filter/sort in Java. Cassandra does not inherently provide an efficient `JOIN` or global `ORDER BY` across all partitions like a scan-capable SQL database.

The v1 schema is **not wrong**; it simply serves a different query contract. The new requirement requires adding a new access path to the architecture.

## 2. Detecting Shifts with Data Rather Than Gut Feel

Not every UI change or traffic increase requires a schema redesign. First, document the **differences between before and after workloads**.

| Aspect | Before Change | After Change | Design Implication |
| --- | --- | --- | --- |
| Keys caller has | Tenant, customer, month | Tenant, status, day | Missing the old table's routing key |
| Ordering | `created_at DESC` for one customer | `created_at DESC` across tenant/status/day | Wants a different time slice |
| Scope | One customer/month partition | Many customers in a tenant | Fan-out could be massive |
| Frequency | Customer screen read often | PENDING queue also read often | New query warrants its own access path |
| Write load | Mostly inserting orders | Orders change status multiple times | Status projection needs delete/insert on key changes |
| Freshness | Customer list can lag slightly | Queue must reflect changes within clear SLO | Must design projection sync |

### 2.1. Query-Shape Tracker

Example:

| ID | Query | Mandatory Inputs | Illustrative Target | Current Solution |
| --- | --- | --- | --- | --- |
| Q01 | Look up order by ID | Tenant, order ID | Single row, low latency | Table `orders_by_id` |
| Q02 | Customer's orders in a month | Tenant, customer ID, month | 50 rows, newest first | Table v1 |
| Q03 | PENDING orders by creation day | Tenant, status, day | 50 rows, low p95 | **No suitable read path yet** |
| Q04 | Customer's orders across 2 months | Tenant, customer ID, month range | Can be slower than Q02 | Bounded fan-out across 2 buckets |
| Q05 | Search keywords, price, optional status | Tenant and dynamic filters | Flexible sort | Likely needs search engine |

The "50 rows" and SLO numbers here are **illustrative assumptions**, not Cassandra defaults.

### 2.2. Metrics Used to Decide Whether Redesign Is Necessary

- **Read path:** requests/s per query shape, average/peak partitions per request, returned bytes/rows vs. intermediate bytes/rows read, p50/p95/p99 latency, timeouts.
- **Write path:** mutations/s, update/delete ratios, number of projection tables, write latency, retries, single-partition hotspots.
- **Storage:** largest partition size, rows/partition, SSTables per read, tombstones scanned, compaction backlog, disk usage.
- **Data/tenants:** largest tenant, order distribution by status, skew across keys, retention, and growth rate.
- **Correctness:** projection lag, missing/extra/stale record rates, source revisions, and unprocessed event backlogs.

A tenant with 10 customers behaves nothing like a tenant with 100,000 customers. Decisions based only on fast queries over tiny sample datasets easily miss fan-out and hot partitions at production scale.

## 3. Which Changes Call for Which Approaches?

| Type of Change | Example | Approach to Evaluate |
| --- | --- | --- |
| Add a display column | Add `delivery_note` to order details | Can add a regular column and update writers/readers |
| Add filter within bounded scope | Filter severity inside one small partition | Evaluate bounded filter, compatible index, or projection |
| Change query partition key | Read by tenant/status instead of customer/month | **New query-driven table**, plus backfill |
| Change primary sort order | Sort by payment time instead of creation time | New table/projection aligned to that axis |
| Old partition grows too big/hot | One device/day hits millions of events | Finer bucket or sharding, then migrate |
| Retention changes | Keep events 90 days instead of 30 | Assess old TTL impact, capacity, and backfill |
| Queries become ad-hoc search | Full-text, multi-filters, relevance | Evaluate search/analytics rather than endless tables |
| Add datacenter / increase RF | New operational region | Plan replication/placement/consistency and cluster capacity; may not alter data model |

Do not turn every new feature into a new Cassandra table. If fan-out spans only two known buckets and traffic is rare, reading two partitions and merging can be preferable. Conversely, if Q03 is a heavily polled queue, scanning the whole tenant even for few returned rows will blow past SLAs.

### 3.1. When `ALTER TABLE` Suffices—and When It Does Not

Adding a **regular column** is a very different schema change from changing a primary key:

```sql
-- Example if the application needs to store an extra display column.
ALTER TABLE orders_by_customer_month_v1
ADD delivery_note text;
```

However, adding a column **creates no new index and changes no partition placement**. The following does not magically become an efficient query simply because `delivery_note` exists:

```sql
-- Illustrates an intent LACKING a key-aligned read path:
-- SELECT ... FROM orders_by_customer_month_v1
-- WHERE delivery_note = ? AND tenant_id = ?;
```

More importantly, **you cannot directly `ALTER` the partition key or clustering key of a populated table like an ordinary column**. For access-key changes, create a v2 table with the right primary key, migrate data with verification, and switch read paths; never try to mutate v1 "in place" expecting Cassandra to reshuffle existing rows.

## 4. Designing the v2 Table for the New Access Pattern

For Q03, a candidate is:

```sql
CREATE TABLE orders_by_status_created_day_v2 (
    tenant_id text,
    status text,
    created_day date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, status, created_day),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

New query:

```sql
SELECT created_at, order_id, customer_id, total_amount, revision
FROM orders_by_status_created_day_v2
WHERE tenant_id = ?
  AND status = ?
  AND created_day = ?
LIMIT 50;
```

This creates **one partition** per tenant, status, and creation day; clustering supports reading newest first by `created_at`, using `order_id` to break ties within the same millisecond. No prior lookup of customer IDs and no `ALLOW FILTERING` are needed.

### 4.1. Bucket Definitions Must Be Unambiguous

`created_day` here is the **UTC date of `created_at`**, not the date the order entered its current status. If an order was created on Nov 21 and moved `PENDING → PAID` on Nov 22, the new `PAID` row still belongs to the **Nov 21 creation-day** partition.

If the domain actually wants "orders **that became PAID on Nov 22**," a different query path must key off `status_changed_at` or a status-event table—never reuse the creation-day bucket while ignoring the semantic mismatch.

Temporal fields must be normalized consistently across all producers and consumers. `LocalDate` in Java carries no timezone, so when deriving it from `Instant createdAt`, convert to **UTC** first.

### 4.2. Size the New Costs Before Adopting v2

| Dimension | v1 Customer/Month | v2 Status/Creation Day |
| --- | --- | --- |
| Primary read path | One customer and one month | One tenant, one status, one day |
| Per new order | Written to v1 | Also written to v2 |
| On status transition | Update regular column `status` | Delete old status key, insert new status key |
| Risk of huge partition | Customer with huge monthly volume | Large tenant with a common status on one day |
| Multi-bucket reads | Multiple months | Multiple days or shards |
| Business consistency | Needs clear status source | Needs projection sync and stale/orphan detection |

Measure orders/tenant/day, distribution across statuses, and transition rates. If `PENDING` accumulates millions of orders for one tenant in a day, a v2 partition can become a hotspot even though Q03 reads only one partition.

### 4.3. What If v2 Creates a Hot Partition?

Consider adding `shard_id`, deterministically computed from `order_id`, to the partition key:

```sql
CREATE TABLE orders_by_status_created_day_sharded_v2 (
    tenant_id text,
    status text,
    created_day date,
    shard_id int,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, status, created_day, shard_id),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

With 16 shards, writers use a consistent versioned hash function to compute `shard_id` from `order_id`. Q03 must read **up to 16 partitions**, merge by `(created_at DESC, order_id DESC)`, and track per-shard pagination cursors.

Sharding **reduces per-partition load** at the cost of higher fan-out and complexity. Never pick a shard count by guesswork; measure the largest dataset and balance write throughput against read SLOs. Without an actual hotspot, an unsharded v2 table is simpler.

## 5. Never Switch Reads Before Building the New Write Path

Cassandra does not automatically know that rows in v1, the ID table, and v2 represent the same order. Adding v2 requires defining the **source of truth**, change propagation, and error repair.

In this example, an ID lookup row can serve as the application's accepted current state:

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
```

This is an **illustrative architectural assumption**—Cassandra does not automatically enforce single-writer source semantics. The application must govern who assigns `revision`, which transitions are legal, how concurrent updates resolve, and how accepted events are replayed.

### 5.1. On Order Creation

A newly created order writes three representations:

```sql
INSERT INTO orders_by_id (
    tenant_id, order_id, customer_id, created_at,
    current_status, total_amount, updated_at, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_customer_month_v1 (
    tenant_id, customer_id, month_bucket, created_at,
    order_id, status, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_status_created_day_v2 (
    tenant_id, status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

`month_bucket` and `created_day` must be derived from **the exact same accepted UTC `created_at`**, never from "current wall-clock time" inside each consumer. If an operation fails partway through, tables can diverge until retries or reconciliation run.

### 5.2. On Order Status Transition

For an accepted `PENDING → PAID` transition from the source:

1. Persist the new status/revision in the source under concurrency rules.
2. Update `status` and `revision` in v1 since `status` is a regular column there.
3. **Delete the v2 row** in partition `(tenant,PENDING,created_day)` using its full primary key.
4. **Insert the v2 row** in partition `(tenant,PAID,created_day)` using its full primary key.

The two v2 mutations:

```sql
DELETE FROM orders_by_status_created_day_v2
WHERE tenant_id = ?
  AND status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;

INSERT INTO orders_by_status_created_day_v2 (
    tenant_id, status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

`status` in the `DELETE` is the **old status**, and in the `INSERT` is the **new status**. A status change literally **moves the row across partition keys**. Deletes generate tombstones, increasing compaction work and read overhead under heavy status churn.

These mutations **do not form a cross-table/cross-partition SQL transaction**. APIs may observe partial state during propagation. Define projection lag SLOs and recovery procedures when an operation fails.

## 6. Revisions, Event Ordering, and Durable Change Sources

Simply writing v1 and v2 in parallel and assuming they stay consistent is risky. Consider:

```text
Order O-1, revision 11: PENDING
Order O-1, revision 12: PAID

Consumer processes rev 12 first:
  deletes PENDING, inserts PAID in v2.

Later a retry of rev 11 arrives late:
  if written unconditionally, it can recreate PENDING
  or regress status in source/v1 back to the old version.
```

Merely having a `revision` column in each row **does not prevent** Cassandra from accepting stale mutations. Standard cell values obey write-timestamp conflict resolution; revision is business metadata that must be **checked and enforced by explicit logic**.

A sound design can combine:

- **A single source deciding transitions:** only accepted changes are emitted to projections.
- **Per-order monotonically increasing revision/sequence:** identifies latest state, detects retries, and handles contention.
- **Stable event IDs:** the same transition reuses the same `event_id` on replay.
- **Durable change stream:** event log/outbox/CDC with clear contracts, checkpoints, and replayability after consumer crashes.
- **Per-order serialized processing** or strong version checks when updating projections; never let an old-revision backfill job overwrite a newer live revision.
- **Periodic reconciliation:** detects missing, stale, or orphan rows and repairs them from the source.

### 6.1. What Does LWT Control?

If the source row holds `revision`, the application can use a lightweight transaction (LWT/CAS) on **that single source row** when conditional control is needed:

```sql
-- Illustrated for an existing source row.
UPDATE orders_by_id
SET current_status = ?,
    updated_at = ?,
    revision = ?
WHERE tenant_id = ?
  AND order_id = ?
IF revision = ?;
```

The caller must inspect `[applied]`, verify `nextRevision` is valid, and handle contention. LWTs add coordination cost; do not use them by default when unnecessary. **An LWT on the source table does not automatically create an isolated transaction across v1/v2 partitions.**

### 6.2. Logged Batches Do Not Replace a Pipeline

A logged batch helps ensure mutations in the batch are eventually applied after failure recovery per batch semantics, yet it **does not provide cross-partition read isolation like a relational transaction** and does not check old vs. new revisions. Multi-partition batches can also overload coordinators and batchlogs; never use them as a throughput hack or a substitute for durable events and reconciliation.

Replication factor and consistency levels such as `LOCAL_QUORUM` (in a matching topology) govern **how many replicas acknowledge each mutation**. If an event was never sent to v2 by the consumer, raising the consistency level on v2 reads will not materialize missing rows.

## 7. Multi-Phase Migration Plan

A safe migration plan ensures **v1 continues serving existing queries** while v2 is built and populated. Using a separate `v2` table name makes parallel deployment, validation, and rollback far simpler than modifying data in place.

| Phase | Tasks | Exit Criteria |
| --- | --- | --- |
| P0. Measure & lock contracts | Document query shapes, SLOs, load, largest datasets | Problem to solve is unambiguous |
| P1. Design v2 | Lock partition/clustering, TTL, buckets, sharding, schema | Valid CQL tests and acceptable load model |
| P2. Secure live changes | Build durable event source, v2 writer/consumer, retries | Zero dropped accepted mutations |
| P3. Backfill | Load historical data in checkpointed batches without breaking live data | Clear coverage and watermarks |
| P4. Reconcile & shadow-read | Compare against source; measure drift and latency | Invariants hold within SLO |
| P5. Canary & traffic shift | Enable v2 for small user/tenant slice, then ramp up | Error/latency/correctness KPIs pass |
| P6. Stability soak | Keep v1 and rollback path intact for defined soak window | No drift, lag, or abnormal cost |
| P7. Retire v1 | Stop old writers after consumers leave; archive/delete per policy | Approved cleanup and recovery plan |

Never skip P2 to run P3 first: if backfill takes hours while new orders keep arriving, v2 will miss changes emitted during that window unless you capture and replay them.

### 7.1. Keep Migration State Explicit

Example operational states for **the new Q03 read path**:

```text
SCHEMA_CREATED
  -> LIVE_SYNC_ENABLED
  -> BACKFILL_RUNNING
  -> RECONCILED
  -> SHADOW_READ
  -> CANARY
  -> V2_PRIMARY_READ
  -> V1_RETIRE_ELIGIBLE
```

These are **workflow states**, not mandatory CQL tables. Track rollout state per tenant or chosen scope alongside timestamps, owners, metrics, and rollback triggers. Multi-tenant systems can canary per tenant, but **never** enable v2 for a tenant that has not completed backfill and reconciliation.

## 8. Backfilling Without Overwriting Newer Data

Backfilling populates v2 for data that existed before v2 began receiving live traffic. The hard part is that source data keeps mutating concurrently.

### 8.1. Choose an Enumerable Source

In this example, `orders_by_id` supports looking up one order given `(tenant_id, order_id)`, yet the table itself **does not offer a cheap API to list all order IDs of a tenant**. Therefore, backfill needs an enumerable source designed for it: a durable event log with full history, a controlled maintenance export/snapshot/manifest, or an existing ETL dataset.

Never run `SELECT * FROM orders_by_id` on production APIs expecting a cheap tenant scan. For large datasets, scanning/exporting needs dedicated tooling, scheduling, and throttling so live transactional traffic is unaffected.

### 8.2. The In-Flight Change Window

Example timeline:

```text
10:00:00  Begin writing live changes to durable log.
10:00:10  Lock backfill checkpoint/watermark.
10:00:20  Load historical records via bounded manifests.
10:05:00  An order being backfilled transitions PENDING -> PAID.
10:10:00  Live consumer writes PAID rev 20 to v2.
10:11:00  Backfill worker still holds snapshot PENDING rev 18.
```

If the backfill worker writes PENDING rev 18 to v2 at 10:11, it can **recreate the stale status row** after the consumer already applied rev 20. Simply storing `revision=18` in the old row does not stop this on its own.

You need an **order-provable protocol**, such as:

1. Capture durable changes starting early enough to cover the checkpoint.
2. Load the snapshot with a well-defined watermark.
3. Replay post-watermark changes **per order** in sequence, deduplicating by event ID/revision.
4. Ensure backfill workers and live consumers never write an older version to status keys already updated by a newer version.
5. Reconcile final state against the live source before permitting production reads.

Depending on architecture, use **per-order serialized queues**, barrier/cutover watermarks, single-executor ownership per order, or post-snapshot writer handoff. An inconsistent snapshot paired with watermark-less replay leaves data gaps; verify the mechanism under realistic conditions.

### 8.3. Why `COUNT(*)` Alone Is Insufficient

Suppose v2 matches the source's total order count, yet is missing order A and has an extra order B. Matching totals do not prove data correctness. Compare:

- Expected `(tenant, order_id)` key sets per manifest.
- `status`, `customer_id`, `created_at`, `revision`, and display values.
- New partition keys correctly computed in UTC.
- Old status rows properly deleted on status transitions.
- Records inside vs. past retention per policy.

Reconciliation should use bounded ID batches and query by **full primary key**, never full-table scans on user request paths.

### 8.4. Retention During Backfill

If a v2 table stores history with TTL, never rewrite all historical rows with a fresh full TTL and accidentally **extend retention**. For example, with 30-day retention from `event_time`: a 28-day-old event has roughly 2 days left; already-expired events follow expired-data policy rather than getting a fresh 30-day lease.

If v2 holds current order state, its retention may differ from event history; lock down each table's lifecycle separately. Tables with heavy TTLs/deletes generate tombstones and compaction load. Backfill can also drive heavy write/SSTable bursts, so throttle QPS and reserve disk headroom.

## 9. Reconcile by Invariants, Not Intuition

In this scenario, `orders_by_id` is the authoritative accepted state, while v1/v2 are projections. For an order `O`, post-convergence invariants can be:

| ID | Invariant |
| --- | --- |
| I1 | `orders_by_id` holds current status and revision per business source |
| I2 | v1 holds O's customer/month row and regular columns `status/revision` match source |
| I3 | v2 holds O's row in partition `(tenant,current_status,created_day)` with matching revision |
| I4 | Rows in **prior status** partitions for O no longer exist after convergence |
| I5 | Rows past retention are not resurrected by backfill/repair jobs against policy |

To check I4, v2 cannot cheaply look up `order_id` across every status/day partition. You need **`old_status`** from durable events, manifests, or intentionally recorded historical key sets.

### 9.1. CQL to Verify One v2 Row by Full Key

```sql
SELECT customer_id, total_amount, revision
FROM orders_by_status_created_day_v2
WHERE tenant_id = ?
  AND status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;
```

Against source:

```sql
SELECT customer_id, created_at, current_status,
       total_amount, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

The reconciliation job must derive `created_day` from UTC `created_at` and use the accepted current status. When v2 shows a lower revision than source, never blindly fire an old mutation: confirm the source is still current and write under serialization/version control. If the source advances to a newer revision mid-job, an unguarded job can corrupt state without barriers or contention checks.

### 9.2. Classifying and Fixing Discrepancies

| Type | Symptom | Action |
| --- | --- | --- |
| `MISSING` | Source is PAID, v2 lacks PAID row | Recreate row with exact key and current version |
| `STALE` | v2 has PAID with older revision and stale fields | Update from latest source; avoid regressing |
| `ORPHAN` | v2 still has PENDING after source became PAID | Verify old key from event log and delete |
| `DUPLICATE_LOGICAL` | Same order appears under multiple statuses from replay | Use source/manifest to keep active row and prune old |
| `IN_FLIGHT` | Event just accepted; within sync SLO | Wait within allowed lag window and monitor |
| `EXPIRED_EXPECTED` | Missing due to legitimate TTL expiration | Do not resurrect against retention policy |

**Cassandra repair** synchronizes replicas across nodes; it has no idea the application forgot to delete a PENDING row in another table. Business reconciliation is a separate layer requiring safe retries and idempotent re-runs.

## 10. Shadow Reads, Canary Rollouts, and Read Cutover

Even after backfill and reconciliation, validate on bounded live traffic before full cutover.

### 10.1. Purposeful Shadow Reads

For Q03, **v1 has no equivalent read path** for direct per-request comparison. Never fire thousands of v1 scans just to "cross-check." Instead:

- Execute Q03 against v2 **without returning those results to users** during the shadow phase.
- Sample returned IDs and read `orders_by_id` to verify status, customer, creation time, and revision.
- Cross-check expected key lists from manifests/event logs for target tenants/days.
- Measure latency, partition counts, returned row counts, stale/missing rates, and v2 resource usage.

If a query shape is supported by both v1 and v2, you can compare results after normalizing sort order, limits, and freshness—but **never assume** equivalence when partition keys or bucket semantics differ.

### 10.2. Canary with Stop Criteria

Example workflow:

1. Enable Q03 reads from v2 for internal tenants or a fully verified tenant cohort.
2. Cap concurrency, page size, and query duration; enable p95/p99 and timeout alerts.
3. Monitor mismatch rates, v2 lag, tombstones, and hot nodes.
4. If thresholds breach, **disable the v2 read path** via config/feature flag; never fall back to scanning v1 across the whole tenant.
5. Once metrics remain stable over the agreed soak window, expand tenant percentage.

For existing queries Q01/Q02, keep using the tables already serving them well until you have a separate reason and migration plan. Adding v2 for Q03 **does not require dropping v1 right away**.

### 10.3. Metrics to Watch During Cutover

| Group | Metrics |
| --- | --- |
| API experience | p50/p95/p99, timeouts, error rate, actual page sizes |
| Freshness | Projection lag, oldest unapplied event age, backlog, dead-letters |
| Data correctness | Missing/stale/orphan rates, revision mismatches, reconciliation pass rate |
| Cassandra load | Read/write QPS per table, tombstones scanned, hot partitions, SSTables per read |
| Storage | Disk used, compaction backlog, headroom for repair/streaming/backfill |
| Rollout | % tenants on v2, reconciled tenants, rate-limited requests |

Evaluate the **hottest node** and **largest tenant**, not only cluster averages. A single large tenant's status/day partition can slow down specific replicas even while the broader cluster looks underutilized.

## 11. Java: Separating Old and New Read Paths with Explicit Contracts

Example using **DataStax Java Driver 4.x**. The application retains the old customer/month query and adds the new status/day query. A service-layer router or feature flag enables Q03 only after a tenant finishes backfill/reconciliation; this code does not automatically enable v2 for every tenant.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.UUID;

public final class MigratingOrderQueries {
    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement customerMonthV1;
    private final PreparedStatement statusDayV2;

    public MigratingOrderQueries(CqlSession session) {
        this.session = session;
        this.byId = session.prepare(
            "SELECT customer_id, created_at, current_status, total_amount, revision " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.customerMonthV1 = session.prepare(
            "SELECT order_id, created_at, status, total_amount, revision " +
            "FROM orders_by_customer_month_v1 " +
            "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ? " +
            "LIMIT 50"
        );
        this.statusDayV2 = session.prepare(
            "SELECT order_id, created_at, customer_id, total_amount, revision " +
            "FROM orders_by_status_created_day_v2 " +
            "WHERE tenant_id = ? AND status = ? AND created_day = ? " +
            "LIMIT 50"
        );
    }

    public Row getById(String tenantId, UUID orderId) {
        return session.execute(byId.bind(tenantId, orderId)).one();
    }

    public ResultSet customerOrders(
        String tenantId, UUID customerId, YearMonth utcMonth
    ) {
        return session.execute(
            customerMonthV1.bind(tenantId, customerId, utcMonth.toString())
        );
    }

    // Call once the tenant is enabled for v2 reads in the rollout workflow.
    public ResultSet ordersByStatusForCreatedDay(
        String tenantId, String status, LocalDate utcCreatedDay
    ) {
        BoundStatement bound = statusDayV2.bind(
            tenantId, status, utcCreatedDay
        ).setPageSize(50);
        return session.execute(bound);
    }

    public static LocalDate createdDayUtc(Instant createdAt) {
        return createdAt.atZone(ZoneOffset.UTC).toLocalDate();
    }
}
```

Bounds to enforce beyond the snippet:

- `tenantId` must come from an authenticated/authorized context, never trusting a client-supplied value. Shadow reads and reconciliation must also enforce tenant scope.
- `YearMonth` carries no timezone; derive it only from UTC-converted `Instant`s. `LocalDate` maps to CQL `date`, `Instant` to `timestamp`, and `UUID` to `uuid`.
- `LIMIT 50` is the **total row cap** of the CQL query. `setPageSize(50)` sets driver page size—it will not yield endless new pages if the query itself is capped at 50 rows.
- To support "load more" beyond a single preview page, use a CQL statement **without hardcoded `LIMIT 50`**, paired with opaque paging state tied to the query shape and bound values. Never reuse cursors across different tenants, statuses, or dates.
- Synchronous `ResultSet` iteration can fetch additional pages automatically; an endpoint returning one page must bound consumption.
- The Q03 API **must not** fall back to scanning v1 when v2 is unavailable: temporarily disable the feature, restrict tenants, or return a product-approved degraded response.

### 11.1. Sizing Bytes and Load Limits in Java

When enabling v2, the Java service needs explicit caps: valid statuses, dates within retention, page size, and concurrency. Conceptual logic:

```text
authorize(tenant, user)
validate(status, createdDay)
assert rolloutState(tenant) >= RECONCILED
assert request.pageSize <= configuredMax
execute v2 prepared query
record: latency, returnedRows, tenant, status, createdDay, projectionLag
```

These checks are the service's responsibility, not enforced merely by defining a partition key. For multi-day requests, use bounded fan-out and merging; single-day queries do not automatically create global ordering.

## 12. Rollback and Cleaning Up the Old Table

Rollback must be designed **before canarying**:

- If Q03 misbehaves, disable Q03/v2 for affected tenants; **never break v1** simply because v2 underperforms.
- If v2 writers fail, preserve durable events and apply backpressure/retries; pause v2 consumers if needed, without deleting the source of truth.
- If backfill data is found corrupt, clean/rebuild **v2 per plan**, avoiding destructive edits to v1.
- If v1 writes were stopped and you later want to roll back Q02, you need a **v1 catch-up plan** before returning old traffic; a table that stopped receiving updates cannot serve accurate reads merely by flipping a feature flag.

### 12.1. When Can v1 Be Retired?

Consider retirement only after:

1. Confirming every query shape depending on v1 has a replacement path or was intentionally deprecated.
2. Auditing all clients/services, export jobs, dashboards, and consumers to confirm none still read v1.
3. Soak/rollback window has elapsed, and data retention/backup approvals are signed off.
4. Stopping v1 writers cleanly, monitoring errors, and proving zero legitimate traffic remains.
5. Planning deletion with appropriate disk, compaction, and snapshot headroom.

Never treat `DROP TABLE` as universally risk-free or instantaneous disk reclamation. Execute it under cluster backup, access-control, replication, and operational procedures.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Changing screens without measuring query shapes | Useless tables or missed primary queries | Inventory + frequency/SLO/fan-out first |
| Trying to `ALTER` v1's partition key | No automatic re-keying of existing data | Create v2 and migrate with verification |
| Creating v2 and switching reads immediately | Missing pre-cutover historical data | Backfill, reconcile, shadow/canary |
| Backfilling during live updates without watermarks | Stale rows overwrite newer state or events drop | Durable log, checkpoints/barriers, per-key ordering |
| Storing `revision` column without enforcing checks | Stale retries can still write bad rows | Proper sequencer/CAS and reconciliation |
| Writing new status while forgetting to delete old status | Order appears in two queues | Store old key and delete with full primary key |
| Using `LOCAL_QUORUM` to fix stale v2 projections | Replicas never received the missing mutation | Monitor projection lag and retry pipeline |
| Treating logged batches as SQL transactions | Readers observe partial updates | Understand atomicity/isolation limits |
| Keying v2 by tenant/status/day without sizing big tenants | Hot partitions and latency spikes | Benchmark max partition; bucket/shard if needed |
| Backfilling TTL tables with full fresh TTL | Extends retention on old data | Compute remaining TTL per contract |
| Shadow-reading by scanning thousands of v1 partitions | Spikes production load | Compare against source/manifest on bounded samples |
| Canarying without a rollback path | Incidents hit all tenants | Feature flags, stop criteria, keep old path healthy |
| Dropping v1 before auditing consumers | Breaks legacy APIs with hard recovery | Inventory, freeze writes/reads, retire in phases |
| Expecting repair to fix missing projection logic | v2 still lacks app-omitted mutations | Business-level reconciliation |

## 14. Checklist for Completing a Redesign

| Question | Passing Evidence |
| --- | --- |
| Why change the schema? | New query shape or metrics proving old schema fails SLA |
| Are old patterns still needed? | All v1 APIs/consumers inventoried with continued support plan |
| Does v2 have the right keys? | CQL uses full partition key and clustering for sort/ranges |
| Are there hot partitions? | Tested largest tenant/device, bytes/rows, p95/p99, peak writes |
| What is the new write cost? | Create/update/delete mutation counts, RF, indexes, tombstones, headroom |
| Is there a source of truth? | Clear rules governing accepted revisions and transitions |
| Are changes durable? | Log/CDC/outbox with replay, checkpoints, and deduplication |
| Can backfill resume safely on failure? | Small batches, quotas, watermarks, idempotency, no stale overwrites |
| Are reconciliation invariants defined? | Checks source, v1, v2, and old status keys via manifests |
| Are TTL policies accurate? | Expired data not resurrected past policy; compaction sized |
| Do shadow/canary tests measure enough? | Latency, lag, drift, hotspots, timeouts, and stop thresholds |
| Is rollback viable? | Feature flags and intact data paths upon reverting |
| Is v1 cleanup planned? | Consumer audit, retention, backups, and ops sign-off |

## 15. Practice Exercise

A Java service logs parcel scan history in Cassandra. Initially APIs only asked for "the 50 most recent scans of a parcel on a UTC day," yielding:

```sql
CREATE TABLE parcel_scans_by_parcel_day_v1 (
    tenant_id text,
    parcel_id uuid,
    day_bucket date,
    scanned_at timestamp,
    scan_id uuid,
    location_id uuid,
    scan_status text,
    PRIMARY KEY ((tenant_id, parcel_id, day_bucket),
                 scanned_at, scan_id)
) WITH CLUSTERING ORDER BY (scanned_at DESC, scan_id DESC);
```

Six months later, operations adds:

- **R1:** The 100 most recent scans at **one location in a UTC hour**, across all parcels.
- **R2:** Continue reading single-parcel/day history from v1.
- **R3:** A very hot scanner emits 80 events/second, and the busiest location handles huge parcel volume.
- **R4:** Events can arrive one day late; data is retained 14 days from `scanned_at`.
- **R5:** The new API must roll out gradually without impacting legacy screens.

**Tasks:**

1. Explain why v1 cannot directly serve R1 despite containing `location_id`, and why `LIMIT 100` does not solve a missing partition key.
2. Propose a v2 table name and partition/clustering keys for `(tenant, location, hour_bucket)`; write CQL `CREATE TABLE` and `SELECT` for R1.
3. For a massive location, when are shorter buckets or shards needed? With 8 shards, how must readers change?
4. Define how to compute UTC `hour_bucket` from `scanned_at` and remaining TTL when an event arrives one day late.
5. Outline at least **seven steps** to migrate from v1 to v2: live changes, backfill source, watermarks, replay, shadow reads, canary, rollback, and reconciliation.
6. If event revision 5 was already written to v2 and a backfill job writes revision 4, what is the risk? Does having a `revision` column prevent the bug automatically?
7. Name three invariants to verify v2 against the event source, and two metrics used to decide whether traffic can shift.

**Reference guidance:** R1 needs a read path by location/hour, e.g., `PRIMARY KEY ((tenant_id, location_id, hour_bucket), scanned_at, scan_id)` with descending clustering. v1 by parcel/day remains for R2. For hot locations, measure largest partition and peak writes before considering a fixed shard count; reading all shards requires merging by `scanned_at DESC, scan_id DESC`. Bucket by UTC `scanned_at`, with 14-day event-time retention leaving roughly **13 days of TTL** on a one-day-late event. Migration needs an enumerable event source, durable live sync, checkpoints/watermarks, bounded backfill, stale-revision protection, key/value reconciliation, and per-tenant/location shadow and canary phases. A `revision` column alone does not block out-of-order updates; consumers/workers must enforce explicit versioning rules.

## Conclusion

In Cassandra, an access-pattern shift is a signal to **re-evaluate partition routing and clustering order**, not merely tune a `SELECT`. When old keys cannot serve new requirements, the safe path is **designing a query-driven v2 table, maintaining durable change streams, running controlled backfills, reconciling, and cutting over reads in stages**. Throughout, preserve legacy queries, handle TTLs, out-of-order events, hot partitions, and partial failures cleanly. A successful redesign means not just executable v2 CQL, but accurate converged data, measured SLAs under real load, and a clear rollback path.
