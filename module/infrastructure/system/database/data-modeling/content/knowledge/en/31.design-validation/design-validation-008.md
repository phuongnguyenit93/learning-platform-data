# Measuring Read Queries, Write Costs, and Storage Capacity on Representative Data

## 1. Validating Data Designs with Measurements, Not Gut Feelings

A data model can be right on **entities, relationships, and constraints** yet still fail a live system: the order detail page reads slowly, every update maintains too many indexes, or storage grows faster than budgeted. Conversely, a schema that appears join-heavy is not automatically slow if data, indexes, and real queries are well structured.

**Design validation through benchmarking** places competing options under **the same representative volume, distribution, and access patterns**, simultaneously measuring:

- **Reads:** client-side and database latency, throughput, rows/bytes scanned, I/O, index usage, and SLO violation rate.
- **Writes:** transactions/second, commit latency, index maintenance cost, WAL, lock contention, dead tuples, autovacuum, replication lag, and impact on reads.
- **Storage:** primary data, indexes, TOAST, WAL, derived tables, partitions, replicas, backups, and growth rate over time.
- **Correctness:** identical data must yield identical business results; never "optimize" by dropping rows, removing constraints, reading stale timestamps, or double-counting.
- **Operability:** cache dependency, tenant skew, late-arriving data, node failures, backfills, and recovery time.

The task is not "run `EXPLAIN` and pick the lowest estimated cost." You need a **workload model**, acceptance criteria, a reproducible dataset, clear instrumentation, and evidence-backed decisions.

### Running Example

A multi-tenant commerce platform stores **`Order`**, **`OrderLine`**, and **`PaymentMovement`**. The engineering team is weighing three options:

- **A — Normalized:** separate order and line tables with basic primary/foreign keys.
- **B — Normalized with read-path indexes:** adds composite/covering indexes tuned for primary read paths.
- **C — B plus daily summary rollups:** accelerates reporting queries while adding update costs and freshness lag.

These three options **compare fairly only** when sharing identical grain, monetary definitions, business statuses, source data, and consistency rules; if Option C serves data up to three minutes stale, that lag must lie within accepted requirements.

## 2. Lock Down Requirements with Workloads, Invariants, and Bounds

Before generating millions of test rows, write a target table:

| Group | Illustrative acceptance criterion *(example)* | Where to measure? |
| --- | --- | --- |
| Read order by ID (`Q1`) | P95 ≤ 80 ms at 300 req/s; P99 per separate SLO. | End-to-end from client, including header and lines. |
| Tenant recent orders list (`Q2`) | P95 ≤ 150 ms under baseline load; max 50 rows/page. | Client latency + SQL plan. |
| Daily sales summary report (`Q3`) | P95 ≤ 2,000 ms; max 5 min lag if using a mart. | Query, freshness, and reconciliation. |
| Create 3-line order (`W1`) | P95 commit ≤ 120 ms at 120 tx/s. | Client, DB transaction, WAL, and locks. |
| Status update (`W2`) | Preserves state machine; meets write target. | Correct transaction outcome and index update cost. |
| Storage | Primary + indexes fit approved Year-2 budget. | Measured physical bytes plus growth projection. |
| Correctness | No duplicate business keys, no inflated totals, no tenant leaks. | PK/FK/CHECK and reconciliation queries. |

**These thresholds are hypothetical prompt targets, not measured benchmark results or universal SLO recommendations.** In real projects, numbers come from UX targets, budgets, peak traffic ratios, and business agreements.

A workload is never just "80% read, 20% write"; define **request shapes**:

- `Q1`: read one order by `(tenant_id, order_id)` along with `1–N` lines.
- `Q2`: filter by tenant and time window, sort most recent first, take top page.
- `Q3`: aggregate by day and currency, potentially scanning millions of rows.
- `W1`: create an order and its lines in one transaction.
- `W2`: transition status when version preconditions match.
- `W3`: ingest payment movements idempotently, including duplicate and late callbacks.

If real traffic is 70% tenant-scoped queries while benchmarks run global scans, conclusions are worthless.

## 3. Representative Data Means Representative *Distribution*, Not Just Row Counts

A 100,000-row uniformly random dataset differs fundamentally from real data with giant enterprise customers, spiky promo days, and best-selling SKUs.

Hypothetical Year-2 production profile:

| Attribute | Test dataset target | Why it matters? |
| --- | --- | --- |
| Tenants | 200 tenants, with **2 large tenants** holding 35% of orders. | Tests hot tenants and index/shard skew. |
| Orders | 6 million `orders`. | Tests scale and planner statistics. |
| Order lines | 18 million `order_lines`; mostly 1–5 lines, some orders with dozens. | JOIN cardinality, fanout, caching. |
| Payment movements | 7.2 million; includes uncaptured, multi-capture, and partial refunds. | Grain accuracy and per-order indexing. |
| Time | 24 months; promo-day peaks far higher than normal days. | Partition pruning, temporal hotspots. |
| Statuses | `PLACED`, `CANCELLED`, `FULFILLED` unevenly distributed. | Predicate selectivity and update patterns. |
| Currencies | Multiple codes distributed by tenant/region. | Tests `GROUP BY`, prevents cross-currency summing. |
| Text sizes | Names/codes with realistic length distribution plus long outliers. | Heap/TOAST behavior, scan bytes, serialization. |
| Read heat | Recent windows read far more heavily than old history. | Page cache, index locality, warm vs. cold tiers. |

This is a **simulated scenario**, not production telemetry from a real company. Real values should come from sanitized business statistics and growth forecasts.

### Preserve Correlations Across Attributes

Independent uniform randomness makes "every tenant use every currency," "every status spread evenly across all years," or "every order contain exactly 3 lines," causing the planner and I/O to behave unrealistically.

A representative dataset preserves **meaningful correlations**:

- Large tenants generate more orders, concurrent updates, and payment callbacks.
- Promo days drive spikes in order lines, pending statuses, and reporting queries.
- Top-selling products recur across many orders.
- Recent orders see frequent reads and edits; older orders serve mostly reporting and audits.
- Payment callbacks may arrive late, replay, or record multiple movements per order.
- Region codes, currencies, and sources follow real contract distributions.

Altering distributions alters predicate selectivity — turning the exact same index from fast to counterproductive.

## 4. Production Copies, Statistical Synthesis, or Sampling: Which Is Trustworthy?

Three common approaches can be combined:

| Dataset method | Benefits | Limitations |
| --- | --- | --- |
| **Sanitized copy of real production data** | Preserves real skew, correlations, text sizes, and outliers. | Privacy risk; needs authorization, masking, and derived-data controls. |
| **Synthetic generation from aggregate stats** | Scales arbitrarily, reproducible, zero real PII. | Easily misses correlations and rare outliers affecting plans. |
| **Stratified sampling** by tenant, time, status, size | Preserves key cohorts inside a smaller footprint. | Small samples fail to reproduce RAM overflow, cache misses, and index depth. |

**Never test a 1% sample and assume query latency scales linearly by 100×.** Once tables outgrow RAM, index tree depth rises, cache misses spike, and the planner switches JOIN strategies. For production capacity and performance decisions, test **near target scale** or calibrate projections across multiple scale points.

### Matrix of Representative Test Cases

Include:

- Largest tenant, median tenant, and tiny tenant.
- Recent 24-hour, 30-day, and full-history windows.
- Orders with 1 line, 5 lines, and 100 lines; orders with zero payments and orders with multiple refunds.
- Peak traffic bursts and normal baseline days.
- High-selectivity point keys and low-selectivity broad predicates.
- `NULL`s, rare enums, long product codes, and soft-deleted rows where policy permits.
- Updates contending on hot keys alongside uncontended distributed keys.

**Representative data must obey invariants.** Never generate 18 million lines pointing to non-existent orders and blame slowness on the relational model. Put corrupt-data cases in dedicated **negative tests**.

## 5. Identity, Grain, and Correctness Are the Foundation of Benchmarking

Assume:

- `orders` has grain **one order per `(tenant_id, order_id)`**.
- `order_lines` has grain **one line item per `(tenant_id, order_id, line_no)`**.
- `payment_movements` has grain **one provider-confirmed movement per `(tenant_id, movement_id)`**.

One `Order` can have 3 `OrderLine`s and 2 `PaymentMovement`s. Directly joining both child tables via `Order` produces 6 rows. Even with perfect indexes running in 20 ms, `SUM(line_net_minor)` or `SUM(amount_minor)` over that join is **business-wrong**.

**Measurement prerequisite:** every candidate option must return equivalent results under the same contract — never "win latency" by dropping rows, loosening tenant boundaries, or confusing `RefundRequested` with `RefundConfirmed`.

### Defining the Ground Truth (*Oracle*)

Maintain a suite of **golden fixtures** covering:

1. An order with no confirmed payments.
2. An order with multiple lines, multiple captures, and a partial refund.
3. An order cancelled after placement, handled per reporting policy.
4. Late-arriving data bucketed accurately by event date.
5. Another tenant reusing identical external codes within its allowed namespace.
6. A duplicate payment callback sharing the same transaction ID.

For each case, lock down **exact row counts, amounts, currencies, timestamps, and statuses** before comparing latencies. Correctness is a **gating criterion**: an inaccurate option is disqualified even if faster.

## 6. Normalized Baseline Schema in PostgreSQL

The schema below separates Order, Line, and Movement into distinct grains. The schema name `bench` highlights that this is a **benchmark test schema**, not a recommendation to run migrations straight onto production.

~~~sql
CREATE SCHEMA IF NOT EXISTS bench;

CREATE TABLE bench.orders (
    tenant_id           UUID NOT NULL,
    order_id            UUID NOT NULL,
    customer_id         UUID NOT NULL,
    placed_at           TIMESTAMPTZ NOT NULL,
    order_status        VARCHAR(24) NOT NULL
                        CHECK (order_status IN
                            ('PLACED', 'CANCELLED', 'FULFILLED')),
    booked_total_minor  BIGINT NOT NULL
                        CHECK (booked_total_minor >= 0),
    currency_code       CHAR(3) NOT NULL,
    row_version         BIGINT NOT NULL DEFAULT 1
                        CHECK (row_version > 0),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE bench.order_lines (
    tenant_id           UUID NOT NULL,
    order_id            UUID NOT NULL,
    line_no             INTEGER NOT NULL CHECK (line_no > 0),
    product_id          UUID NOT NULL,
    quantity            NUMERIC(18,3) NOT NULL CHECK (quantity > 0),
    line_net_minor      BIGINT NOT NULL CHECK (line_net_minor >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES bench.orders (tenant_id, order_id)
);

CREATE TABLE bench.payment_movements (
    tenant_id           UUID NOT NULL,
    movement_id         UUID NOT NULL,
    order_id            UUID NOT NULL,
    provider_name       VARCHAR(60) NOT NULL,
    provider_reference  VARCHAR(120) NOT NULL,
    movement_type       VARCHAR(12) NOT NULL
                        CHECK (movement_type IN ('CAPTURE', 'REFUND')),
    amount_minor        BIGINT NOT NULL CHECK (amount_minor > 0),
    currency_code       CHAR(3) NOT NULL,
    confirmed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, movement_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES bench.orders (tenant_id, order_id),
    UNIQUE (tenant_id, provider_name, provider_reference)
);
~~~

**Scope limitations of this example:**

- `booked_total_minor` represents the booked value at placement under test policy; it **differs from net cash**. If shipping fees, taxes, or order-level discounts exist outside lines, never assume line sums equal order totals.
- Payment movements are written only once confirmed by an authoritative source. If provider references are not unique per `tenant + provider`, include merchant/account namespace in the `UNIQUE` key.
- `row_version` supports optimistic concurrency on `Order`, yet does not enforce the full state machine unless the application validates transitions.
- Composite FKs enforce tenant scope within the same DB; `customer_id` and `product_id` may reference external services.
- This is a baseline schema to compare indexing, denormalization, and partitioning — not a full accounting or retention model.

### After Bulk Loading Test Data

Planner statistics must reflect the loaded dataset:

~~~sql
-- Run in test environment after bulk load.
ANALYZE bench.orders;
ANALYZE bench.order_lines;
ANALYZE bench.payment_movements;
~~~

Stale statistics cause `EXPLAIN` to pick wrong plans — an error of **measurement setup**, not necessarily the data model. Record PostgreSQL version, storage class, statistics state, and configuration before comparing runs.

## 7. Building a Read Query Catalog: Never Benchmark One Isolated `SELECT`

A read workload should list query shapes, frequencies, result sizes, filters, and freshness expectations.

| ID | Query | Key inputs | Potential bottlenecks |
| --- | --- | --- | --- |
| **`Q1`** | Read one Order and its Lines by PK. | Tenant, Order ID, line count. | N+1 queries, network round-trips, wide rows. |
| **`Q2`** | 50 most recent orders per tenant. | Hot/cold tenant, date window, cursor. | Large sorts, missing indexes, deep `OFFSET`. |
| **`Q3`** | Booked sales by day and currency. | 1 day / 30 days / 2 years. | Large scans, JOIN/aggregate, temp spill, cache eviction. |
| **`Q4`** | Confirmed captures/refunds for one Order. | Movement count, provider, currency. | Wrong-grain joins, missing order index. |
| **`Q5`** | Top-selling products in period. | Date filter, product groups, many tenants. | High-cardinality `GROUP BY`, hot keys, shuffles. |
| **`Q6`** | Look up a customer's latest orders. | Tenant, `customer_id`, time range. | Secondary index on customer, skew. |

Measure both **common cases and tail cases**: giant tenants, hundred-line orders, empty date ranges, and orders with many payment callbacks. Never average `Q1` and `Q3` into one "mean database latency"; their targets are completely different.

### `Q1` — Order Detail

~~~sql
SELECT tenant_id, order_id, customer_id,
       placed_at, order_status, booked_total_minor, currency_code
FROM bench.orders
WHERE tenant_id = :tenant_id AND order_id = :order_id;

SELECT line_no, product_id, quantity, line_net_minor
FROM bench.order_lines
WHERE tenant_id = :tenant_id AND order_id = :order_id
ORDER BY line_no;
~~~

This is **two queries** inside one request. End-to-end latency includes both plus serialization/connection overhead. If you need a consistent snapshot across header and lines during concurrent writes, choose appropriate isolation/session policies; two `SELECT`s under `READ COMMITTED` can observe two different snapshots.

### `Q2` — Most Recent Orders Page

~~~sql
SELECT order_id, placed_at, order_status,
       booked_total_minor, currency_code
FROM bench.orders
WHERE tenant_id = :tenant_id
  AND placed_at >= :from_at
ORDER BY placed_at DESC, order_id DESC
LIMIT 50;
~~~

The sort key includes `order_id` as a deterministic tie-breaker when multiple orders share a timestamp. For deep pagination, benchmark **keyset pagination** using `(placed_at, order_id)` instead of large `OFFSET`s.

### `Q3` — Daily Booked Line Value

~~~sql
SELECT (o.placed_at AT TIME ZONE 'UTC')::date AS day_utc,
       o.currency_code,
       SUM(l.line_net_minor) AS booked_line_minor
FROM bench.orders o
JOIN bench.order_lines l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
WHERE o.tenant_id = :tenant_id
  AND o.placed_at >= :from_at
  AND o.placed_at <  :to_at
GROUP BY (o.placed_at AT TIME ZONE 'UTC')::date, o.currency_code
ORDER BY day_utc, o.currency_code;
~~~

This example deliberately buckets by **UTC date** via `AT TIME ZONE 'UTC'`; if reporting uses a **local business date**, substitute the approved time zone/cutoff and keep that rule identical across all options. This sums **line values**, which does not automatically equal Order `booked_total_minor` if order-level fees/taxes exist, nor is it net cash. For a fair `Q3` comparison, every option must evaluate this exact same definition, tenant scope, calendar, and currency.

Placeholders like `:tenant_id` and `:from_at` are **illustrative bind parameters** for an application or benchmark driver; they are not runnable literal SQL variables in all PostgreSQL consoles.

## 8. Plan Analysis: How to Read `EXPLAIN (ANALYZE, BUFFERS)`

Example plan check for `Q2`:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT order_id, placed_at, order_status,
       booked_total_minor, currency_code
FROM bench.orders
WHERE tenant_id = :tenant_id
  AND placed_at >= :from_at
ORDER BY placed_at DESC, order_id DESC
LIMIT 50;
~~~

**Do not look only at "Execution Time."** Record:

| Observation | Question to answer |
| --- | --- |
| `Seq Scan` / `Index Scan` / `Bitmap Scan` | How much data did the plan touch, and why did it choose that path? |
| `actual rows` and `loops` | Are nodes executing repeatedly, suffering N+1 or JOIN fanout? |
| `estimated rows` vs. `actual rows` | Are statistics misestimating selectivity or skew? |
| `Rows Removed by Filter` | How many rows were read only to be discarded? |
| `Sort Method`, `Memory`, `Disk` | Did `ORDER BY`/`GROUP BY` spill to disk? |
| `shared hit/read` | Were pages served from PostgreSQL shared buffers or read from OS/storage? |
| `temp read/written` | Did hash joins, sorts, or aggregates spill temporary files? |
| `Planning Time`, `Execution Time` | How much time went to planning vs. execution? |
| `Settings` | Did non-default planner settings differ between runs? |

In PostgreSQL, `BUFFERS shared hit` tracks **PostgreSQL's shared buffer cache**, while `shared read` may still come from the OS page cache rather than physical disk I/O. Proving physical disk I/O requires OS/storage metrics and controlled cache conditions.

**`EXPLAIN ANALYZE` actually executes the SQL statement.** For `INSERT`/`UPDATE`/`DELETE` or functions with side effects, run only in test environments with controlled transactions and external effects. Even after SQL rollback, sequences, non-DB trigger side effects, or external logs may not revert. Never run it in production just to "peek at a plan."

### Server Execution Time Differs from User-Perceived Latency

`EXPLAIN ANALYZE` timings reflect engine execution (plus instrumentation overhead). They omit network round-trips, connection-pool queueing, JSON encoding/decoding, application mapping, and downstream service calls.

Use two instrumentation layers:

- **Query plan instrumentation:** explains *why* a SQL query is slow.
- **Workload driver / client tracing:** tells *whether users meet SLOs* under concurrent load.

Never substitute a single idle `EXPLAIN` snapshot for concurrent load testing.

## 9. Comparing Indexes: Read Gains Cost Writes and Storage

For `Q2`, Option B may add:

~~~sql
CREATE INDEX ix_orders_tenant_recent
ON bench.orders (tenant_id, placed_at DESC, order_id DESC)
INCLUDE (order_status, booked_total_minor, currency_code);
~~~

This index supports tenant filtering plus recency ordering and can reduce heap fetches on some workloads. Still, **index-only scan** effectiveness depends on **the visibility map** and row visibility checks; heavily updated tables may still require heap fetches.

### What to Measure Before and After Adding an Index?

| Expected benefit | Cost to measure |
| --- | --- |
| Less sorting/scanning on `Q2`. | Index bytes, WAL, and CPU during `INSERT`. |
| Faster top-50 order fetch. | Updates to `order_status` must maintain the `INCLUDE` index. |
| Better tail latency. | Cache pressure: larger indexes leave less RAM for hot pages. |
| Fewer heap fetches when clean. | Vacuum / visibility map overhead affecting index-only scans. |

**No index is free.** If `order_status` updates frequently and sits in `INCLUDE`, updates may lose PostgreSQL HOT-update eligibility, causing extra index/heap writes and WAL amplification. An alternative omitting `order_status` from `INCLUDE` touches the heap more on reads yet writes more lightly.

Never benchmark only `Q2` and declare B superior to A. Run **the full mixed read/write workload**, especially updates touching indexed columns, and measure storage too.

### BRIN, B-Tree, and Other Options

- **B-tree** suits selective lookups, ordering, and ranges on matching keys.
- **BRIN** stays compact on physically time-correlated append data; it is lossy, requires re-checking rows, and can perform poorly for small tenants scattered across pages.
- **Partition pruning** reduces scanned child tables, yet does not replace per-partition index design.
- **Materialized summaries** speed up heavy `Q3` reads at the cost of pipelines, lag, corrections, and extra storage.

Choose via **real workload measurement**, not heuristics like "big tables must use BRIN" or "every FK needs an index."

## 10. Measure Latency by Distribution, Never by Mean Alone

"Average latency 40 ms" can hide 5% of requests taking several seconds. Track at least:

- **`P50`**: median request latency.
- **`P95` and `P99`**: tail behavior driving user frustration, timeouts, and saturation.
- **SLO violation rate** per query shape and tenant tier.
- **Throughput**: requests/sec and transactions/sec achieved while staying within latency targets.
- **Errors, timeouts, retries**: never drop failed requests to make latency charts look prettier.
- **Result size** and rows scanned: distinguish fast queries from queries returning fewer rows.

### Designing Concurrent Load

| Driver model | Best suited for | Risks |
| --- | --- | --- |
| **Closed-loop:** `N` clients send the next request only after the previous finishes. | Testing app concurrency with fixed clients. | Slowdowns throttle send rate, masking true arrival load. |
| **Open-loop / arrival-rate:** sends at a target arrival schedule. | Testing SLAs under latency-independent arrival rates. | Saturation builds unbounded queues; set safety caps and record failures. |
| **Burst / peak:** concentrates traffic in a window. | Testing promo drops, thundering herds, connection limits. | Does not replace steady-state tests; report exact burst shape. |

Guard against **coordinated omission**: if a driver waits for a slow response before scheduling the next request and records only completed requests, wait queues disappear from metrics. Under arrival-rate testing, log from the *intended start time* and track queued, timed-out, and incomplete requests.

### Never Average Percentiles

Averaging per-minute P95 values does not equal the run's true P95. Store **high-resolution histograms or raw samples** per query shape and concurrency level to compute percentiles over the full sample set. Always report request counts, duration, error counts, and percentile calculation method.

## 11. Warm vs. Cold Cache and Planner Statistics Can Flip Conclusions

Two runs of identical SQL can produce vastly different numbers because:

- Most pages already sit in PostgreSQL shared buffers or the OS page cache.
- An index was just built, `ANALYZE` just ran, or vacuum just cleaned dead tuples.
- The first run incurred JIT / plan caching while the second ran warm.
- Autovacuum or a checkpoint fired during one run and not the other.
- Hot tenants were queried repeatedly in the second run.
- Connection pools, prepared statements, and parallel query settings differed.

Report two distinct modes explicitly:

1. **Warm-cache / steady-state:** run sufficient warmup before measuring a steady window; represents normal steady traffic.
2. **Cold-ish / cache-pressured:** exercise datasets exceeding RAM, post-restart states, or wide historical scans; execute safely in test environments without recklessly flushing OS caches on shared hosts.

Never claim "cold cache" unless cache state, storage, and host conditions are verified. Aim for **reproducibility**, not strict-sounding labels.

### Standardizing the Comparison Environment

Keep constant: DB version, CPU/RAM/storage, pool config, autovacuum, WAL durability, planner settings, dataset/seed, query parameters, and read/write mix. If one option uses async commits while another waits for durable flush, you are comparing **different durability guarantees**, not faster schemas.

## 12. Write Benchmarks: Orders and Lines Must Commit Atomically

Single-order creation transaction in PostgreSQL:

~~~sql
BEGIN;

INSERT INTO bench.orders (
    tenant_id, order_id, customer_id,
    placed_at, order_status, booked_total_minor,
    currency_code
) VALUES (
    :tenant_id, :order_id, :customer_id,
    :placed_at, 'PLACED', :booked_total_minor,
    :currency_code
);

INSERT INTO bench.order_lines (
    tenant_id, order_id, line_no,
    product_id, quantity, line_net_minor
)
VALUES
    (:tenant_id, :order_id, 1,
     :product_1, :quantity_1, :line_amount_1),
    (:tenant_id, :order_id, 2,
     :product_2, :quantity_2, :line_amount_2);

COMMIT;
~~~

This illustrates two lines; workload `W1` should vary from 1 to hundreds of lines matching real distributions. Tests must assert order totals, currency, FKs, and invariants before counting throughput. Transactions failing `UNIQUE`/FK checks must not count as successful orders.

### Writes Are More Than `INSERT`s

| Write pattern | Load to simulate | Physical cost |
| --- | --- | --- |
| **`INSERT` order + lines** | Multi-PK/FK, multi-row, single commit. | Heap pages, PK/secondary indexes, WAL, commit flush. |
| **`UPDATE` status** | In-flight orders with optimistic locking. | New MVCC tuple, index maintenance, dead tuples. |
| **`INSERT` payment movement** | Idempotency, unique provider ref, duplicate callbacks. | Uniqueness checks, lock contention on collisions. |
| **`DELETE` / soft delete** | Policy retention or lifecycle expiry. | Bloat, dead index entries, vacuum, filter selectivity. |
| **Bulk load / backfill** | Historical batch ingestion. | WAL spikes, checkpoints, replica lag, stats/index upkeep. |
| **Concurrent hot-key update** | Contention on shared stock/counters/keys. | Lock waits, serialization failures/retries, throughput caps. |

When comparing schemas, **keep identical commit durability and business constraints**. Dropping FKs or unique constraints to speed up write benchmarks invalidates the comparison if production requires them.

## 13. Modeling `UPDATE`, MVCC, HOT, and Bloat in PostgreSQL

PostgreSQL uses MVCC: an `UPDATE` normally writes a new tuple version while the old version awaits visibility/vacuum cleanup. Update cost is therefore far more than "overwriting 10 bytes of status."

Lost-update guard using `row_version`:

~~~sql
UPDATE bench.orders
SET order_status = :new_status,
    row_version = row_version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND row_version = :expected_version
  AND order_status = :expected_status
RETURNING row_version;
~~~

Returning **0 rows** indicates a version conflict, mismatched status, or missing order; the application must classify and handle retries or investigations. This statement guards conditional updates, **not the entire state machine** by itself.

### HOT Updates and Indexes

HOT (Heap-Only Tuple) updates reduce index maintenance when PostgreSQL's conditions hold—chiefly that no indexed column changes and free space exists on the same heap page. Adding `order_status` to an `INCLUDE` index can disqualify status updates from HOT updates.

When comparing Option A and Option B:

- Measure the HOT-update ratio under identical `W2` workload.
- Measure WAL bytes and dead-tuple accumulation rate.
- Measure lock waits, transaction duration, and autovacuum load.
- Measure storage after a write cycle **long enough** to surface bloat, not just right after bulk load.

**Never disable autovacuum to "stabilize" benchmarks and extrapolate to production.** If fixing settings for a narrow micro-experiment, explicitly flag reduced representativeness.

## 14. Measuring Write Cost via WAL, Stats, and End-to-End Latency

PostgreSQL exposes observability counters, though many are **cumulative** rather than per-query. Measure via before/after snapshots across controlled intervals with background noise isolated.

~~~sql
-- Example columns from pg_stat_user_tables.
SELECT relname,
       n_tup_ins, n_tup_upd, n_tup_del,
       n_tup_hot_upd, n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'bench'
ORDER BY relname;
~~~

`n_dead_tup` is an **estimate** at stats update time, not an exact live count; `n_tup_ins/upd/del` reflect observed operations and may lag slightly. Never compare raw cumulative numbers across runs without taking deltas or resetting in isolated test environments.

~~~sql
-- Available on PostgreSQL versions supporting pg_stat_wal.
SELECT wal_records, wal_fpi, wal_bytes
FROM pg_stat_wal;
~~~

`wal_bytes` measures **instance-wide WAL generated during the window**, not final compressed/retained disk bytes, and mixes all concurrent DB activity unless isolated. Record start/end deltas and watch background tasks. For replicated setups, measure replica lag and catch-up recovery when read replicas are required.

### Complete Write Measurement Scorecard

| Metric | Unit | Meaning |
| --- | --- | --- |
| Successful transactions | tx/s | Throughput of **committed** business writes. |
| Commit P50/P95/P99 | ms | Client-observed transaction completion latency. |
| Abort/conflict/retry rate | % / count | Cost of contention and idempotency collisions. |
| WAL bytes per committed order | bytes/order | Log cost per unit of work (delta on isolated run). |
| CPU and disk write bandwidth | CPU%, MiB/s | Hardware resource bottlenecks. |
| Lock wait | ms, count | Contention on shared rows/locks. |
| Dead tuples / vacuum work | estimate, duration | Long-term cost of `UPDATE`/`DELETE`. |
| Index bytes growth | MiB/GiB | Write amplification from extra indexes. |
| Replica freshness | ms/s | How far read replicas lag under write load. |

Never equate `INSERT ... RETURNING` completion with **durable commit** in `W1` when multi-statement transactions are used. Pre-commit timings omit actual user wait until `COMMIT` returns.

## 15. Actual Storage: Heap, Indexes, TOAST, and Total Footprint

Row counts or CSV sizes do not predict database storage. Beyond payload bytes, PostgreSQL adds tuple headers, page framing, visibility metadata, indexes, TOAST out-of-line storage, free space, and update/vacuum bloat.

~~~sql
SELECT
    'bench.orders' AS relation_name,
    pg_size_pretty(
        pg_relation_size('bench.orders'::regclass)
    ) AS main_fork,
    pg_size_pretty(
        pg_table_size('bench.orders'::regclass)
    ) AS table_including_toast,
    pg_size_pretty(
        pg_indexes_size('bench.orders'::regclass)
    ) AS indexes,
    pg_size_pretty(
        pg_total_relation_size('bench.orders'::regclass)
    ) AS total_relation;
~~~

These functions differ in scope:

- `pg_relation_size` (default main fork): main relation fork only, not full table cost.
- `pg_table_size`: table heap plus associated TOAST and internal forks, excluding indexes.
- `pg_indexes_size`: all indexes attached to the relation.
- `pg_total_relation_size`: table + TOAST + indexes for that relation.

When comparing A/B/C, sum **every table in the design**: orders, lines, movements, secondary indexes, rollup tables, materialized views, and design-required read replicas.

### Tracking Index Footprint Share

~~~sql
SELECT c.relname,
       pg_size_pretty(pg_table_size(c.oid)) AS table_bytes,
       pg_size_pretty(pg_indexes_size(c.oid)) AS index_bytes,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_bytes
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'bench'
  AND c.relkind IN ('r', 'm')
ORDER BY pg_total_relation_size(c.oid) DESC;
~~~

This identifies which objects bloat storage, though it cannot judge whether an index is worth keeping — pair it with **query frequency, latency, and write cost**.

### Storage Over Time

Measure at least three checkpoints:

1. **Right after bulk load** and `ANALYZE`.
2. **After steady-state writes/updates/deletes** with representative transactions and normal maintenance running.
3. **After retention/archival/rebuild or vacuum** following real operational procedures.

For partitioned tables, calling `pg_total_relation_size` on the **partitioned parent** may exclude child partitions. Sum across all leaf partitions plus attached indexes and rollups — never report a parent table's "few KB" header as total dataset size.

## 16. Capacity Forecasting: Data, Indexes, WAL, Replicas, and Backups Have Separate Budgets

A storage validation report needs explicit formulas, such as:

~~~text
Data + Indexes at 24 months
    ≈ current_physical_bytes
      + measured_monthly_growth_bytes × 24
      + safety_margin_for_skew_and_bloat

Operational capacity
    = primary_data_and_indexes
      + headroom_for_maintenance_and_migration
      + retained_WAL_and_temp_working_space
      + separately_budgeted_replica_and_backup_storage
~~~

Never apply a universal "indexes = 20% of table size" rule of thumb. Measure **bytes/row per entity and per index** at representative scale, factoring in row volume, text length, update churn, retention, and compression.

Budget separately for:

| Component | How to estimate | Do not forget |
| --- | --- | --- |
| **Primary heap/index** | Measured bytes after substantial load. | Bloat, TOAST, FSM/VM, workload-specific indexes. |
| **WAL** | WAL bytes/tx × volume + retention policy. | Peak traffic spikes, replication/archive backlogs. |
| **Replicas** | Replica count × corresponding footprint. | Costs storage and network, not just CPU. |
| **Backups/snapshots** | Full/incremental per retention & churn rate. | Multi-version retention, restore test space. |
| **Temp files** | Large-query sort/hash spills. | Concurrent `Q3` peaks and heavy reporting. |
| **Materialized aggregates** | Mart size + indexes + refresh staging. | Rebuild time and dual-buffer swap cost. |
| **Migration headroom** | Spare space for online copies/index builds. | Expand–contract holds two structures concurrently. |
| **Retention/erasure** | Purge/archive schedules and legal holds. | Source deletes don't automatically purge downstream copies. |

**Distinguish storage capacity from storage throughput.** Two schemas may both consume `1 TiB`, yet one generates twice the WAL/index writes and misses IOPS and latency SLOs.

## 17. Testing Partitioning and Distribution Without Breaking Constraints

Monthly partitioning can shrink scans for `Q3` and simplify retention drops. Every strategy brings trade-offs:

- **Range on `placed_at`:** date/month queries prune cleanly; point lookups by `order_id` without a date may scan every partition.
- **Hash on `tenant_id`:** scopes tenant data where supported; giant tenants remain hotspots.
- **Multi-DB sharding:** adds routing overhead, cross-shard JOIN limits, distributed constraints/transactions, coordination, and failover complexity.
- **Single-DB declarative partitions:** transactions across partitions remain within **one database**, avoiding cross-cluster 2PC.

### The PK/UNIQUE Trap on PostgreSQL Partitioned Tables

With declarative partitioning, PostgreSQL requires every `PRIMARY KEY`/`UNIQUE` on a partitioned parent to include all partition-key columns. For a table partitioned by `placed_at`:

~~~sql
CREATE TABLE bench.orders_by_month (
    tenant_id    UUID NOT NULL,
    order_id     UUID NOT NULL,
    placed_at    TIMESTAMPTZ NOT NULL,
    status       VARCHAR(24) NOT NULL,
    PRIMARY KEY (tenant_id, placed_at, order_id)
) PARTITION BY RANGE (placed_at);
~~~

This PK **does not enforce** `(tenant_id, order_id)` uniqueness across different months. If `order_id` is an immutable per-tenant business key, you need a separate ID registry, routing, global uniqueness owner, or a different partition key. **Never relax business uniqueness just to make a partition benchmark pass.**

### What to Measure When Testing Partitions?

| Query/operation | Metrics |
| --- | --- |
| `Q2` one tenant, 30 days | Partitions touched, planning/startup time, P95. |
| `Q3` 1 month vs. 24 months | Partition pruning, rows/bytes scanned, temp spill. |
| `Q1` lookup by Order ID | Cross-partition fanout vs. directory lookup. |
| `W1` new orders | Hot partition contention, lock/index writes, WAL. |
| Historical backfill | Writes hitting old partitions, maintenance, replica lag. |
| Retention | Partition archive/drop speed and downstream obligations. |

In distributed SQL/MPP systems, also measure **shuffled network bytes, coordinator waits, and tail latency**. Global queries are governed by the slowest shard; single-node PostgreSQL partition results **do not extrapolate** directly to multi-node sharding.

## 18. Recording Benchmark Conditions for Reproducibility

A minimal benchmark report needs an **experiment contract**, not just timing tables.

~~~yaml
benchmark_id: order-model-2026-11
purpose: compare-index-and-summary
environment:
  database_engine: PostgreSQL
  version: "record exact version used"
  cpu_ram_storage: "record exact hardware spec"
  config_hash: "tracked configuration hash"
dataset:
  generation_version: v3
  seed: "fixed seed in test generator"
  orders: 6000000
  order_lines: 18000000
  payment_movements: 7200000
  skew_profile: "2 large tenants hold 35% of orders"
workload:
  read_write_mix: "per measured request distribution"
  warmup: "record warmup window"
  measurement_window: "record measurement window"
  arrival_rate_and_concurrency: "record actual load"
  consistency: "same guarantees across alternatives"
acceptance:
  read_p95_ms: "per query ID"
  write_commit_p95_ms: "per transaction ID"
  correctness: "golden fixtures + reconciliation"
  storage_budget: "primary/index/WAL/backup budgeted separately"
~~~

This is a **metadata template**, not a runnable config for a specific harness. Fill in actual measured values or approved targets before publishing — never leave placeholders looking like real results.

### Repeatable Validation Flow

~~~mermaid
flowchart LR
    SRC["Source stats + business requirements"] --> DATA["Representative dataset, seed, and skew"]
    SRC --> WORK["Workload + SLOs + correctness oracle"]
    DATA --> A["Options A / B / C in identical environment"]
    WORK --> A
    A --> MEASURE["Reads, writes, storage, latency, errors"]
    MEASURE --> VERIFY{"Business results and SLOs pass?"}
    VERIFY -->|No| REVISE["Adjust model or workload"]
    REVISE --> A
    VERIFY -->|Yes| ADR["ADR: choice, trade-offs, re-evaluation triggers"]
~~~

The flowchart highlights **correctness as a mandatory gate**. Latency metrics are invalid if an option returns wrong monetary figures or drops rows.

### Rules for Fair A/B/C Comparisons

1. Identical dataset snapshot/seed, tenant skew, and distributions.
2. Identical request shapes, parameter mixes, payloads, and result row counts.
3. Identical CPU/RAM/disk, DB version, WAL durability, pools, and connection counts.
4. Identical warmup, measurement duration, steady-state conditions, and maintenance policies.
5. **Interleave or repeat runs** to reduce temporal and caching drift.
6. Measure reads **concurrently with writes**, never solely reads-then-writes if production is mixed.
7. Validate correctness **before and after every run**; disqualify wrong runs from latency rankings.
8. Report variance/confidence across runs; never pick a winner over a few milliseconds of noise.

## 19. PostgreSQL Observability Queries for Investigation

Beyond `EXPLAIN`, diagnostic views help pinpoint costs:

### `pg_stat_statements` (When Enabled)

~~~sql
-- Requires extension and config; not always enabled by default.
SELECT queryid, calls, rows,
       mean_exec_time, total_exec_time,
       shared_blks_hit, shared_blks_read,
       temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

This spots query families consuming total execution time, yet `mean_exec_time` is not client P95, `calls` accumulates over time, and statements are normalized/grouped by the extension. Take start/end delta snapshots and filter to the target query families. Never reset production stats just for a test.

### Inspecting Current Wait States

~~~sql
SELECT wait_event_type, wait_event, COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

This is a **point-in-time snapshot**, not cumulative lock wait duration. For full test analysis, sample over time or use tracing/monitoring metrics.

### `EXPLAIN WAL` on Supporting PostgreSQL Versions

~~~sql
-- Run only in test environments on controlled DML!
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE bench.orders
SET order_status = 'FULFILLED',
    row_version = row_version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND order_status = 'PLACED';
~~~

This observes **one test update** and **executes the `UPDATE`**. Never run it directly on live production data. To inspect plans without executing writes, run `EXPLAIN` without `ANALYZE`, keeping in mind runtime metrics won't appear.

**General rule:** the DBMS supplies execution plans, resource counters, and statistics; load drivers supply end-to-end latency and throughput; business reconciliation supplies correctness. All three belong in the decision report.

## 20. Illustrative Comparison of Three Options (Hypothetical Figures)

The table below presents **illustrative fabricated numbers to demonstrate interpretation**, not executed benchmark results or claims about real PostgreSQL performance.

| Metric (identical load) | A: Basic PKs | B: Added `Q2` index | C: B + daily summary |
| --- | ---: | ---: | ---: |
| `Q1` detail read P95 | 35 ms | 37 ms | 38 ms |
| `Q2` recent list P95 | 620 ms | 90 ms | 92 ms |
| `Q3` 30-day report P95 | 2,400 ms | 2,200 ms | 180 ms |
| `W1` order create commit P95 | 45 ms | 61 ms | 74 ms |
| `W2` status update P95 | 28 ms | 46 ms | 49 ms |
| Sustainable write throughput before SLO breach | 3,200 tx/s | 2,800 tx/s | 2,500 tx/s |
| Primary data + indexes + summary | 820 GiB | 1,050 GiB | 1,140 GiB |
| `Q3` freshness | Direct query | Direct query | Up to 3 min lag assumed |

Interpretation:

- **A** writes lightly and saves storage, yet `Q2` misses the 150 ms P95 target.
- **B** cuts `Q2` latency sharply, paying index/WAL/update overhead and extra storage; `Q3` still misses target.
- **C** meets `Q3` P95 ≤ 2,000 ms **only if 3-minute staleness and correction/rebuild workflows are acceptable**. Never treat C as real-time if the business demands zero-lag figures.
- If required write throughput exceeds 2,500 tx/s, C fails write capacity despite fast reads.
- If the storage cap for this dataset is 1,000 GiB, B and C exceed budget and need further optimization or budget revision rather than picking blindly on `Q2`.

**A sensible hybrid decision:** keep B for OLTP while offloading `Q3` to a warehouse or dedicated read replica with explicit contracts and watermarks, preventing synchronous summary updates from slowing `W1`/`W2`. Benchmark the new architecture too — costs do not vanish, they **move to pipelines, separate storage, and async freshness**.

### Weighted Scores Do Not Override Hard Thresholds

Never compute `"score = 0.4 × read + 0.3 × write + 0.3 × storage"` when an option **violates invariants** or hard SLOs. Eliminate failing/unsafe options first, then analyze Pareto trade-offs across latency, throughput, cost, and operational complexity.

## 21. Validating Data and Reports After Optimization

Every physical change must preserve semantics. Verification examples:

~~~sql
-- Zero orphan order lines (normally guarded by FK).
SELECT l.tenant_id, l.order_id, l.line_no
FROM bench.order_lines l
LEFT JOIN bench.orders o
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
WHERE o.order_id IS NULL;

-- No duplicate payment movements at the same grain.
SELECT tenant_id, movement_id, COUNT(*) AS n
FROM bench.payment_movements
GROUP BY tenant_id, movement_id
HAVING COUNT(*) > 1;

-- Capture and refund totals by currency.
SELECT tenant_id, currency_code,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE 0 END) AS captured_minor,
       SUM(CASE WHEN movement_type = 'REFUND'
                THEN amount_minor ELSE 0 END) AS refunded_minor
FROM bench.payment_movements
GROUP BY tenant_id, currency_code;
~~~

The first two queries return empty inside a constrained DB; they remain essential when exporting to marts, staging tables, or shards lacking identical constraints.

### Golden Fixtures and Checksums

Beyond row counts, verify:

- Business-key sets and row counts by tenant and day.
- `booked_total_minor` vs. `line_net_minor` sums under their distinct definitions, documenting any legitimate delta.
- `CAPTURE` and `REFUND` sums by currency and confirmation cutoff.
- Orders with multiple payment movements, customers with zero payments, and cancelled orders.
- Missing-reference rates and outcomes for late arrivals, corrections, and soft deletes.
- Consistent metric-rule versions and data cutoffs across compared outputs.

Checksums are meaningful only when defining **exact canonicalization and matching row sets**. Two matching totals do not prove individual rows match; +100 on one row and −100 on another cancel out. For critical data, compare per key/record or partitioned canonical hashes.

## 22. Sustainable Benchmarking: Soak, Burst, and Failure Testing

A design can meet SLOs for 10 minutes and degrade after a full day due to bloat, checkpoints, WAL backlogs, or queue buildup. Distinguish:

| Test type | Scenario | What to evaluate |
| --- | --- | --- |
| **Baseline** | Normal steady load, warm cache. | Latency/throughput and plan stability. |
| **Peak/burst** | Promo spikes or callback storms. | Queues, P99, pool exhaustion, hot tenants. |
| **Soak test** | Hours of mixed reads/writes. | Bloat, autovacuum, disk growth, memory/lag leaks. |
| **Cold / cache pressure** | Restart or wide historical scans. | RAM dependency, disk I/O, warm-up recovery time. |
| **Backfill / retention** | History loads, index builds, partition drops/archives. | WAL spikes, locks, replica lag, storage headroom. |
| **Failure / recovery** | Lagging replica, network timeouts, process restarts. | Idempotency, failover, consistency, zero data loss. |
| **Scale sensitivity** | `1×`, `2×`, `4×` data/load. | Query plan inflection points and capacity cliffs. |

Never inject destructive faults in production for benchmarking. Failover and corruption drills require isolated environments, backups/runbooks, and strict permissions.

### Measuring Tail Latency Under Concurrent Load

Reports must state exact concurrency and arrival rates. A `Q2` query taking 10 ms on an idle server can spike dramatically when 100 `W2` workers update `Order` rows during checkpoints. Never cite an idle "10 ms" figure in place of realistic workload P95.

## 23. Decision-Ready Benchmark Report Template

Structured report sections:

1. **Goal:** decision among A/B/C, mandatory workloads, and SLOs.
2. **Environment:** DB version, hardware, storage, config, dataset/seed, cache state, replication, run order.
3. **Dataset:** row counts per table, skew/hot tenants, time spread, lines/order, status/`NULL` ratios, PII sanitization policy.
4. **Options:** DDL/indexes/partitions/denormalizations and preserved invariants.
5. **Methodology:** load driver, warmup, duration, concurrency/arrival rate, retries/errors, percentiles, stat snapshots.
6. **Correctness:** golden fixtures, key reconciliation, amount/currency/time checks, late/correction cases.
7. **Read results:** `Q1..Qn` P50/P95/P99, throughput, plans, rows/buffers/bytes, cache hit rate, timeouts.
8. **Write results:** commit latency, tx success rate, WAL/tx, HOT/bloat, locks, replica lag.
9. **Storage:** heap/index/TOAST/summary, WAL/backups/headroom, period forecasts.
10. **Risks:** schema evolution, retention, hot shards, unsharded queries, rebuild complexity.
11. **Decision:** chosen option, deployment prerequisites, why alternatives were rejected.
12. **Re-evaluation triggers:** data/traffic thresholds, SLO changes, new query shapes, or metric drift.

**Never report only "B is 7× faster than A."** State *which query*, at what load, on which dataset, preserving which business results, at what resource cost, and within what boundaries.

## 24. Common Validation Mistakes

| Mistake | Why conclusion is wrong? | Remedy |
| --- | --- | --- |
| Generating 100K uniform rows and extrapolating to 100M. | Cache, planner plans, and skew differ completely. | Test multiple scales with representative distributions. |
| Querying only one small tenant. | Misses hot tenants and long tails. | Weighted workloads across tenant cohorts. |
| Benchmarking `SELECT`s without concurrent updates. | Misses index write amplification, HOT loss, bloat. | Mixed read/write and soak tests. |
| Reading `EXPLAIN cost` as milliseconds. | Cost is an optimizer model unit, not wall time. | `EXPLAIN ANALYZE` + client latency. |
| Declaring SLO pass from a single P50 mean. | Ignores P95/P99 tails and timeouts. | Histograms, percentiles, request/error counts. |
| Counting only successful requests. | Hides retries, timeouts, and queue collapses. | Report failure rates and incomplete requests. |
| Comparing runs with mismatched warm caches. | Cache and maintenance noise skew timings. | Identical warmup and interleaved multi-runs. |
| Comparing schemas with unequal constraints. | Faster option may skip invariant checks. | Enforce identical contracts, PK/FK/unique, correctness gates. |
| `SUM` after joining two 1:N facts. | Doubles monetary values while running fast. | Verify grain; pre-aggregate before joining. |
| Estimating storage from CSV size. | Ignores indexes, TOAST, WAL, bloat, replicas. | Measure physical bytes and full operational footprint. |
| Treating `pg_stat` counters as single-query metrics. | Counters are cumulative and include background work. | Delta snapshots in isolated test runs. |
| Disabling autovacuum for cleaner graphs. | Hides long-term update and bloat costs. | Production-like maintenance and soak runs. |
| Reading stale replicas as immediately consistent. | Violates freshness and source cutoffs. | Define watermark/lag SLAs and reconcile. |
| Benchmarking materialized marts while hiding refresh lag. | Compares incompatible consistency tiers. | State freshness SLAs and refresh costs explicitly. |
| Testing on unauthorized copies containing real PII. | Security and compliance violation. | Verified synthetic/masked data under least privilege. |
| Adding an index for one niche query. | Slows majority write workload or bloats RAM. | Pareto analysis across frequency, cost, and SLOs. |

## 25. Practice Exercise: Evaluating a Ticketing Platform Design

**Context:** a ticketing platform serves 150 tenants and many live events. One `booking` has multiple `ticket_line`s; one `payment_attempt` can produce multiple capture/refund movements. Major ticket drops push 1% of tenants to 45% of load. Users look up bookings by ID, view the 50 most recent bookings, and operations monitors hourly ticket sales. Cancellations and refunds arrive late.

### Tasks

1. **Choose grain and keys:** specify `booking`, `ticket_line`, `payment_movement`; authoritative sources for seat holds and payment outcomes; tenant-scoped unique/FK keys.
2. **Build a data profile:** table of tenant counts, bookings, lines/booking, skew, time spread, status ratios, and movements — separating simulated targets from real stats.
3. **Define SLOs:** P95/P99 targets for booking lookup, recent list, hourly report, and booking transaction; specify concurrency, arrival rates, and error budgets.
4. **Propose three options:** A baseline normalized, B indexed on `(tenant_id, placed_at)`, C = B plus materialized hourly rollups. Define rollup ownership and freshness.
5. **Define query workload:** at least four query shapes and three transaction types, including hot/cold tenants and extreme line counts.
6. **Write SQL:** test schema with PK/FK/CHECK; booking lookup; recent list with tie-breaker; hourly ticket totals free of payment-join fanout.
7. **`EXPLAIN`:** list fields to capture from `EXPLAIN (ANALYZE, BUFFERS)` to diagnose sorts, join fanout, misestimates, and temp spills.
8. **Mixed read/write:** design an open-loop load scenario at 100, 300, 600 req/s plus burst tests; explain coordinated omission.
9. **Index cost:** measure shifts in read P95, WAL/tx, HOT updates, lock waits, and index bytes.
10. **Storage:** use `pg_table_size`, `pg_indexes_size`, and `pg_total_relation_size`; forecast 12–24 months including WAL, replicas, backups, and headroom.
11. **Partitioning:** evaluate monthly partitions; analyze PK/UNIQUE when business key is `(tenant_id, booking_id)` and queries omit the month.
12. **Correctness:** golden fixtures for a 3-line booking, 2 captures, 1 refund; prove JOINs do not inflate money; test currency and duplicate callbacks.
13. **Freshness:** reconcile hourly rollups against transaction sources at identical watermarks; handle late cancellations/refunds and restatement.
14. **Durability:** design soak tests, cold-ish cache pressure, hot tenants, autovacuum, replica failover, and online index rebuilds.
15. **Report:** build an A/B/C comparison table with P50/P95/P99, throughput, WAL/booking, storage, correctness, and confidence level.
16. **ADR:** choose the option meeting mandatory constraints, detailing trade-offs, re-evaluation triggers, and unverified limits.

### Self-Assessment Rubric

| Criterion | Passing evidence |
| --- | --- |
| **Representative data** | Includes scale, skew, correlations, hot/cold tiers, outliers, and sources/seeds. |
| **Clear workload** | Query shapes, frequencies, result sizes, transaction semantics, and concurrency. |
| **Proper read metrics** | Client P95/P99 + `EXPLAIN`/Buffers/plans, not just server averages. |
| **Proper write metrics** | Success/abort/retry rates, commit latency, WAL, locks, HOT, and bloat. |
| **Complete storage** | Heap, indexes, TOAST/summaries, WAL, replicas, backups, headroom. |
| **Correctness** | Zero fact multiplication, no mixed currencies, no dropped PK/FKs for speed. |
| **Fair comparison** | Identical data/engine/config/semantics, identical load, stated freshness. |
| **Operability** | Covers soak/peak/failure, lag, and recovery procedures. |
| **Decision** | Eliminates options breaking SLOs/correctness; explains Pareto trade-offs. |

**Conclusion:** validating a data model requires measuring **on structurally representative data and workloads**, not merely inserting many rows or timing one lucky query. Reads must be judged by latency distributions, plans, and I/O; writes must account for transactions, indexes, WAL, locks, bloat, and durability; storage must include data, indexes, history, and replicas. Above all, compared options must share identical **grain, keys, measure definitions, consistency contracts, and business correctness**. Only with documented measurement conditions, verified outputs, and explicit trade-off analysis is a relational, document, distributed, or analytical design ready for production.
