# Starting from Latency, Throughput, and Representative Queries in PostgreSQL

When a PostgreSQL system “runs slow,” the common reaction is to find a `SELECT` statement and add an index, rewrite a `JOIN`, or increase memory. However, **query optimization does not start with editing SQL**. It starts with understanding what work the system is actually performing, how fast it must serve users, and how much concurrent work it needs to handle.

A change might reduce the execution time of a single SQL statement from 50 ms to 5 ms, yet increase `INSERT` overhead, cause other requests to wait longer for locks, or fail to speed up the user-facing page because most of the time is spent in the network and application layer. Conversely, a 200 ms SQL query may be completely acceptable in an overnight batch report, yet unacceptable on an inventory-check endpoint that must serve thousands of requests per second.

Therefore, a PostgreSQL performance optimization effort should open with three questions:

1. **What is the latency goal?** How long can the user or calling API wait, where is it measured, and to what percentage of requests does it apply?
2. **What is the throughput goal?** How many queries, transactions, or business operations per second must the system handle, and under what concurrency and read–write ratio?
3. **What are the representative queries?** Which SQL patterns, parameter types, data distributions, and transactions actually make up the application's workload?

This lesson belongs to the **Query Optimization** chapter of the **Database Engine Relational PostgreSQL** module. You will build a repeatable measurement workflow using `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements`, `pgbench`, PostgreSQL statistics, and application telemetry to prioritize optimization in the right places.

## 1. “Faster” Is Not a Clear Enough Goal

Consider how different these two statements are:

> “The orders page is slow; we need to optimize PostgreSQL.”

> “During peak hours at 600 requests/second, the endpoint that lists the 20 most recent orders for a tenant must have a p95 under 120 ms and a p99 under 350 ms, with a minimum success rate of 99.9%; at the same time, it must not push order-creation p95 past 250 ms.”

The first statement leaves everything unspecified:

- Is latency measured from the browser, the gateway, or PostgreSQL?
- How many SQL statements does one request execute?
- Is current load 5 or 5,000 requests/second?
- Is it slow for all tenants or only very large tenants?
- Are timeouts included or dropped from the metrics?
- Is the “optimization” allowed to slow down the write path?

The second statement has **measurable goals**, including speed, load, and side-effect limits.

### From Problem to Testable Hypothesis

A good hypothesis looks like this:

> The recent-orders listing query currently scans and sorts too many rows per tenant. An index on `(tenant_id, status, created_at DESC, order_id DESC)` may reduce the number of blocks read and eliminate a sort step. We need to re-measure with both small and large tenants while also checking the cost of updating `status`.

A hypothesis should only be accepted when backed by evidence, not just because `Index Scan` appears in the query planner output.

## 2. Distinguishing Latency, Throughput, and Concurrency

These three concepts are related, but **not synonymous**:

| Concept | Question | Common Units |
| --- | --- | --- |
| **Latency** | How long does a single operation take to complete? | ms, seconds |
| **Throughput** | How many operations complete per unit of time? | requests/s, queries/s, transactions/s |
| **Concurrency** | How many operations coexist / are being processed or waiting at the same time? | concurrent requests/connections/transactions |

Illustrative example:

- An endpoint has a p95 latency of **180 ms**.
- During peak hours, it receives **400 requests/s**.
- Approximately **80 requests are in flight concurrently** at a given moment.

The three numbers describe different dimensions. A system can process many requests/second yet still exhibit high tail latency; another system can respond very quickly to an individual request at low load yet collapse when many requests arrive together.

### QPS, TPS, and RPS

- **RPS** (*requests per second*): typically measured at the API/gateway layer.
- **QPS** (*queries per second*): the number of SQL statements executed per second; clarify whether prepared statements, SELECTs, and DML are counted.
- **TPS** (*transactions per second*): the number of transactions completed per second; PostgreSQL and benchmark tools have different ways/sources of counting these statistics.

A single HTTP request may invoke **8 SQL queries** across **2 transactions**. Thus, 1,000 RPS does not automatically equal 1,000 QPS or 1,000 TPS.

**Always state the units, measurement boundaries, and load conditions** when reporting results.

## 3. At Which Layer Does Latency Occur?

A request to fetch an order list may pass through:

~~~mermaid
flowchart LR
    U["User"] --> G["Gateway / network"]
    G --> A["Application"]
    A --> P["Waiting for connection pool"]
    P --> D["PostgreSQL"]
    D --> R["Reading results / data transfer"]
    R --> S["Application processing and serialization"]
    S --> U
~~~

End-to-end request latency consists of multiple components:

\[
L_{\mathrm{request}} \approx
L_{\mathrm{network}}+
L_{\mathrm{gateway}}+
L_{\mathrm{pool}}+
L_{\mathrm{database}}+
L_{\mathrm{application}}+
L_{\mathrm{response}}
\]

This is a mental model for allocating time, not a guarantee that every component is strictly independent or that you can directly sum numbers from charts measured at different layers.

Illustrative example:

| Component | Time |
| --- | ---: |
| Gateway and network | 20 ms |
| Waiting for a connection from the pool | 65 ms |
| SQL on PostgreSQL | 8 ms |
| Reading results, processing, and serialization | 27 ms |
| **Total** | **120 ms** |

If SQL drops from 8 ms to 2 ms, the request may improve by only about 6 ms. In this case, index tuning does not address the primary cause, which is **waiting on the connection pool**.

**Do not use `EXPLAIN ANALYZE Execution Time` as the latency metric for an entire API.** It reflects only part of the server-side work and excludes client and network steps.

## 4. Average Latency Does Not Reflect Tail Experience

An API handles 100 requests:

- 95 requests return in 20 ms.
- 5 requests return in 3 seconds.

The average may not look terrible compared to some systems, yet 5 users still wait a very long time.

Commonly used percentiles:

| Metric | Meaning |
| --- | --- |
| **p50 / median** | Roughly 50% of measured values do not exceed this threshold |
| **p90** | Roughly 90% of measured values do not exceed this threshold |
| **p95** | Roughly 95% of measured values do not exceed this threshold |
| **p99** | Roughly 99% of measured values do not exceed this threshold |
| **max** | Maximum value observed in the sample |
| **mean** | Arithmetic average; can be skewed by a small number of very slow requests |

Percentiles must be accompanied by **the measurement window, sample size, error/timeout counts, and collection method**. With only 30 requests, a p99 figure is not stable enough to draw conclusions about tail latency at scale.

### Example SLO

> “Over a 1-hour window, at least 95% of successful `GET /orders` requests must complete under 150 ms; at the same time, the successful request rate must be at least 99.9%.”

Here we have defined both a latency criterion **and** an availability criterion. When computing percentiles, specify how failed/timed-out requests are handled so you do not accidentally produce a flattering report by dropping the worst requests.

### PostgreSQL Mean Differs from API p95

`pg_stat_statements.mean_exec_time` is an aggregate statistic of **SQL execution time**, and it does not give you HTTP request p95. For end-to-end p95/p99, use application tracing, gateway metrics, or sufficiently detailed client-side benchmarks.

## 5. SLI, SLO, and SLA Are Different

Three terms frequently encountered in performance optimization:

- **SLI — Service Level Indicator:** the measured metric, e.g., the fraction of requests with latency under 150 ms.
- **SLO — Service Level Objective:** the internal target for an SLI over a window, e.g., 95% of requests under 150 ms.
- **SLA — Service Level Agreement:** an external commitment, which may carry legal or commercial conditions/consequences.

An example SLI can be defined as:

\[
SLI_{\mathrm{latency}} =
\frac{\text{valid requests with latency }\leq150\ \mathrm{ms}}
{\text{total valid requests in window}}
\]

To use this formula, you must **define “valid request”**: does it include client cancellations, retries, timeouts, health checks, 5xx errors, and 4xx errors?

A good SLO requires:

1. Metric.
2. Measurement point.
3. Unit.
4. Endpoint/workflow scope.
5. Load conditions.
6. Time window.
7. Error/timeout accounting policy.

**Do not optimize a query toward a goal that is not measured where it is actually used.**

## 6. Throughput Goals Must Specify Load Conditions

A throughput number like 5,000 QPS says very little on its own. You need to know:

- How many connections are open?
- What is the read/write ratio?
- Does the query return one row or one million rows?
- Is the data in cache or on disk?
- Are transactions short or long?
- How many queries hit the same hot row?
- What are the error, timeout, and rollback rates?
- What are CPU, I/O, WAL, and replica lag levels?

A system achieving 5,000 QPS on `SELECT 1` proves nothing about handling 5,000 QPS of large reporting `JOIN`s and `UPDATE`s with triggers.

### Goodput Differs from Total Throughput

If clients aggressively retry on timeout, total received requests may go up while **successfully completed business operations** go down. Distinguish between:

- Requests attempted/s.
- Requests completed/s.
- Successful business operations/s (*goodput*).
- Failed/timeouts/s.
- Retries/s.

Do not advertise a benchmark TPS increase if most of those transactions are ignored errors or `ON CONFLICT DO NOTHING` on duplicate data.

## 7. Concurrency and Little's Law

A useful intuition from queueing theory is **Little's Law**:

\[
N=\lambda\times W
\]

In steady state and with a consistently defined system boundary:

- `N`: average number of items simultaneously in the system.
- `\lambda`: steady-state arrival/completion rate.
- `W`: average time an item spends in the system.

For example: if a system steadily completes **200 requests/s** with an average request duration of **0.25 seconds**, then on average there are about:

\[
N=200\times0{,}25=50
\]

requests in flight within the measured boundary.

**Do not infer that “50 concurrent requests” means you need exactly 50 PostgreSQL connections.** A request may wait at a gateway/queue, perform CPU work, or call external services without holding a DB connection. Conversely, a single request may open multiple queries or connections depending on architecture.

### As Load Increases, Latency Does Not Necessarily Grow Linearly

When the server still has spare capacity, increasing the request rate can raise throughput while latency changes little. Near saturation, queues build up, tail latency spikes rapidly, and timeouts appear.

~~~text
Throughput
   ^
   |                 ________ near saturation
   |              __/
   |           __/
   |        __/
   |     __/
   |  __/
   +--------------------------> Offered load

Latency p95/p99 can rise sharply near the saturation region.
~~~

Therefore, you must measure latency at the **target load level**, not just run a single query on an idle server.

## 8. A Faster Query Does Not Always Improve TPS

Suppose query A drops from 15 ms to 3 ms. If the transaction also spends:

- 90 ms calling an external service.
- 35 ms waiting on locks.
- 20 ms writing WAL / committing.
- 12 ms in application processing.

then total transaction time shrinks by only a small fraction.

In another situation, A is a query consuming 80% of PostgreSQL CPU and executed 20,000 times/second. Reducing A's CPU usage can significantly increase overall throughput.

Therefore, evaluate:

1. How much **total resource and total time** does the query consume?
2. Is the query on the **critical path** of an important request?
3. Are there other bottlenecks?
4. If the optimization succeeds, does the bottleneck migrate elsewhere?
5. Do end-to-end SLOs actually improve?

Do not treat every millisecond in every query as having equal business value.

## 9. What Is a Representative Query?

A **representative query** is not just a concise SQL snippet that resembles a real query. It is an execution pattern defined by:

- SQL shape: `WHERE`, `JOIN`, `ORDER BY`, `LIMIT`, aggregates, subqueries, etc.
- Parameter types and concrete values.
- Typical parameter distribution and worst-case values.
- Current row counts and data distribution.
- Isolation and transaction boundaries.
- Invocation method: literals, bind parameters, or server-side prepared statements.
- Frequency, concurrent client count, and share of the workload.
- Number of rows / payload size returned to the application.
- SLO of the workflow the query serves.

Two statements sharing the exact same template:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 20;
~~~

where one call passes `$1 = 1` (a tenant with 5 million orders) and another passes `$1 = 99` (a tenant with 500 orders) can produce very different plans and costs.

**One template does not equal one measurement that represents all parameter values.**

## 10. Grouping a Workload into Query Classes

In an e-commerce system, you can classify queries as:

| Class | Workload | What Matters |
| --- | --- | --- |
| **Point lookup** | Look up order by PK | Very high selectivity, index lookup |
| **Top-N listing** | 20 most recent orders by tenant/status | Filtering, ordering, limit, pagination |
| **Detail + JOIN** | Order + customer + items | Join cardinality, N+1, data transfer |
| **Aggregation** | Daily revenue totals | Rows read, grouping, memory/temp I/O |
| **Insert path** | Create order and items | Unique/FK/index maintenance, WAL |
| **State transition** | Pending → paid | Row locks, indexed columns, contention |
| **Maintenance** | Delete/archive old data | Batch size, WAL, vacuum, locks |

Picking only easy-to-optimize queries such as point lookups creates an unrepresentative benchmark suite. You must include **resource-heavy queries** and **write statements** that may pay the cost of new indexes.

## 11. Frequency and Cost Must Be Viewed Together

Suppose you collect:

| Query | Calls/min | Mean SQL time | Total SQL time/min (illustrative) |
| --- | ---: | ---: | ---: |
| Q1 — List orders | 30,000 | 8 ms | 240,000 ms |
| Q2 — Order detail | 10,000 | 4 ms | 40,000 ms |
| Q3 — Report | 10 | 500 ms | 5,000 ms |
| Q4 — Update status | 6,000 | 12 ms | 72,000 ms |

These figures only illustrate prioritization, not actual measured numbers.

Q3 is slowest **per invocation**, but Q1 consumes the largest total SQL execution time. Q4 also matters because it is on the write path. If Q3 is an executive report that must finish before a strict deadline, it can still merit priority despite its small total time.

### A Prioritization Model

Consider all of the following together:

- Frequency.
- p95/p99 and SLOs.
- Total CPU/I/O.
- Business impact.
- Error/timeout risk.
- Cost to fix and deploy.
- Impact on other workloads.

Do not simply sort queries by `mean_exec_time DESC`.

## 12. Uniform Synthetic Data Can Mislead the Query Planner

Suppose production has 10 tenants:

- Tenant 1 accounts for **60% of all orders**.
- The remaining nine tenants split the other 40%.

If you generate uniformly distributed seed data, each tenant gets 10% of orders; the planner sees a completely different distribution.

Factors your test data should reflect:

| Factor | Why It Matters |
| --- | --- |
| Row counts, table/index size | Affects seq scan vs index scan |
| Tenant skew | Different parameters have different selectivity |
| Common vs rare statuses | An index may help `failed` but not `pending` |
| NULL distribution | `IS NULL` predicates / partial indexes |
| Correlation with heap order | Range scans, BRIN, random I/O |
| Row width | Cache/heap pages and data transfer |
| Column update frequency | HOT, WAL, and index maintenance |
| Bloat/visibility map | Index-only scans and heap fetches |
| Time/periodicity | Monthly, daily, hourly peaks, recent data |
| Foreign keys and triggers | Runtime cost paid during DML |

You do not need an exact copy of sensitive values to benchmark; you can generate synthetic data based on **measured and permitted distributions**.

## 13. Setting Up a Repeatable PostgreSQL Lab

All examples use the `perf_goal_lab` schema inside a **practice-only database**.

**Warning:** the script starts with `DROP SCHEMA IF EXISTS ... CASCADE`, which deletes all objects in that schema. Never run it on production or in a schema containing data you need to keep.

Simulated dataset:

- 6,000 customers distributed across 10 tenants.
- 240,000 orders, with tenant 1 accounting for about 60%.
- 480,000 order line items, two lines per order.
- Uneven status distribution, including a rare group.
- Creation timestamps spanning multiple days.
- Mandatory indexes from primary/foreign keys, with candidate indexes added later.

### 13.1. Create Schema and Tables

~~~sql
-- RUN ONLY IN LAB DATABASE.
DROP SCHEMA IF EXISTS perf_goal_lab CASCADE;
CREATE SCHEMA perf_goal_lab;

CREATE TABLE perf_goal_lab.customers (
    tenant_id integer NOT NULL,
    customer_id integer NOT NULL,
    display_name text NOT NULL,
    email text NOT NULL,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, email)
);

CREATE TABLE perf_goal_lab.orders (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_id integer NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'failed')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    total_amount numeric(12,2) NOT NULL CHECK (total_amount >= 0),
    note text,
    payload text NOT NULL,

    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES perf_goal_lab.customers(tenant_id, customer_id)
);

CREATE TABLE perf_goal_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES perf_goal_lab.orders(order_id),
    line_no smallint NOT NULL CHECK (line_no IN (1,2)),
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Indexes already created by constraints:

- `orders(order_id)`: primary key.
- `customers(tenant_id, customer_id)`: primary key.
- `customers(tenant_id, email)`: unique.
- `order_items(order_id, line_no)`: primary key.

**PostgreSQL does not automatically create indexes on all FK columns on the child table.** We will measure the benefit of a new index on `orders(tenant_id,status,created_at,order_id)` without removing the constraint-backing indexes.

### 13.2. Load 6,000 Customers

~~~sql
INSERT INTO perf_goal_lab.customers (
    tenant_id, customer_id, display_name, email
)
SELECT
    CASE
        WHEN g <= 3000 THEN 1
        ELSE 2 + ((g - 3001) % 9)
    END,
    g,
    'Customer ' || g,
    'customer' || g || '@example.test'
FROM generate_series(1, 6000) AS s(g);
~~~

Tenant 1 has 3,000 customers. The remaining nine tenants have roughly 333–334 customers each.

### 13.3. Load 240,000 Orders with Tenant Skew

~~~sql
INSERT INTO perf_goal_lab.orders (
    order_id, tenant_id, customer_id, status,
    created_at, updated_at, total_amount, note, payload
)
SELECT
    g::bigint,
    t.tenant_id,
    CASE
        WHEN t.tenant_id = 1 THEN 1 + (g % 3000)
        ELSE 3001 + (t.tenant_id - 2) + 9 * (g % 333)
    END,
    CASE
        WHEN (g * 17) % 101 = 0 THEN 'failed'
        WHEN (g * 17) % 101 < 21 THEN 'paid'
        ELSE 'pending'
    END,
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '30 seconds',
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '30 seconds',
    (20 + (g % 300))::numeric(12,2),
    CASE
        WHEN g % 50 = 0 THEN 'Manual review'
        ELSE NULL
    END,
    repeat('x', 100)
FROM generate_series(1, 240000) AS s(g)
CROSS JOIN LATERAL (
    VALUES (
        CASE
            WHEN g % 10 < 6 THEN 1
            ELSE 2 + (g % 9)
        END
    )
) AS t(tenant_id);
~~~

This generation logic is intentional:

- `g % 10 < 6` gives roughly 60% of orders to tenant 1.
- Other tenants share the remainder.
- Status assignment uses modulo 101 instead of modulo 5/10 to avoid correlating status too directly with tenant.
- `created_at` ordering aligns closely with insertion order, helping illustrate correlation.
- `payload` is 100 characters wide so the table is not overly tiny.

### 13.4. Load Two Line Items per Order

~~~sql
INSERT INTO perf_goal_lab.order_items (
    order_id, line_no, product_code, quantity, unit_price
)
SELECT
    o.order_id,
    line_no::smallint,
    CASE line_no
        WHEN 1 THEN 'SKU-A'
        ELSE 'SKU-B'
    END,
    1,
    CASE line_no
        WHEN 1 THEN 10 + (o.order_id % 100)
        ELSE 10 + ((o.order_id % 300) / 100) * 100
    END::numeric(12,2)
FROM perf_goal_lab.orders AS o
CROSS JOIN generate_series(1, 2) AS s(line_no);
~~~

Because `quantity = 1` and the two `unit_price` values are constructed from the tens and hundreds components of `order_id % 300`, the sum of the two lines matches `total_amount = 20 + (order_id % 300)` under this seed.

### 13.5. Update Statistics

~~~sql
ANALYZE perf_goal_lab.customers;
ANALYZE perf_goal_lab.orders;
ANALYZE perf_goal_lab.order_items;
~~~

`ANALYZE` gives the planner statistics on row counts, distributions, and selectivity. In a rigorous benchmark, keep statistics equivalent between the baseline and the candidate approach.

### 13.6. Verify Dataset

~~~sql
SELECT
    COUNT(*) AS orders_count,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_count,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_count
FROM perf_goal_lab.orders;

SELECT tenant_id, COUNT(*) AS orders_count
FROM perf_goal_lab.orders
GROUP BY tenant_id
ORDER BY orders_count DESC, tenant_id;

SELECT COUNT(*) AS items_count
FROM perf_goal_lab.order_items;
~~~

Expected:

- `orders_count = 240000`.
- `items_count = 480000`.
- Tenant 1 has around `144000` orders.
- `failed` is roughly 1%, `paid` roughly 20%, and the rest `pending`.

Exact counts for the modulo categories should be taken from verification queries rather than assumed from approximate percentages.

## 14. Selecting Representative Queries for the Lab

Do not measure only a single `SELECT` that favors an index. The query suite needs multiple access patterns plus write paths.

### Q1 — List the 20 Most Recent Pending Orders for a Small Tenant

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

This is a **top-N listing** API: filter by tenant/status and return a few rows in newest-first order.

### Q2 — Same API for a Very Large Tenant

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Same template, vastly different candidate row count. This is an example of **parameter skew** that cannot be ignored.

### Q3 — Order Details and Line Items

~~~sql
SELECT
    o.order_id,
    o.status,
    o.total_amount,
    c.display_name,
    i.line_no,
    i.product_code,
    i.quantity,
    i.unit_price
FROM perf_goal_lab.orders AS o
JOIN perf_goal_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
JOIN perf_goal_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.tenant_id = 7
  AND o.order_id = 123456
ORDER BY i.line_no;
~~~

This query illustrates reading a single order via its primary key and joining to related tables. If order 123456 belongs to a different tenant, the query returns 0 rows—a test case that preserves **tenant-isolation semantics**.

When measuring Q3 throughput, do not pick a fixed ID belonging to another tenant and benchmark thousands of 0-row lookups. Use valid `(tenant_id, order_id)` pairs from a parameter set.

### Q4 — Revenue Aggregation over a Fixed Time Range

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM perf_goal_lab.orders
WHERE status = 'paid'
  AND created_at >= timestamptz '2026-02-01 00:00:00+00'
  AND created_at <  timestamptz '2026-03-01 00:00:00+00'
GROUP BY tenant_id
ORDER BY paid_amount DESC;
~~~

This is an aggregate query that reads many more rows. It may favor a scan/parallel aggregate or another plan depending on statistics.

**Do not replace the fixed bounds with `now() - interval '7 days'` when the seed lies in the past**: running the lab at the current date would make the query return 0 rows, rendering the measurement unrepresentative.

### W1 — Conditional State Transition

~~~sql
BEGIN;

UPDATE perf_goal_lab.orders
SET
    status = 'paid',
    updated_at = clock_timestamp()
WHERE order_id BETWEEN 50001 AND 50500
  AND status = 'pending'
RETURNING order_id;

ROLLBACK;
~~~

The example uses rollback to preserve the lab state. When benchmarking real write workloads, use a disposable database and committed transactions matching production, not a permanent rollback-only scenario.

### W2 — INSERT New Order

An order-creation path must maintain primary keys, foreign keys, candidate indexes, and WAL. Measuring only Q1/Q2 without W2 misses the extra write overhead introduced by additional indexes.

The write benchmark section below describes a collision-free ID allocation strategy using valid data.

## 15. Weighting the Representative Workload

An example peak-hour traffic mix:

| Group | App Transaction Share | Illustrative SLO |
| --- | ---: | --- |
| Q1 — small-tenant top-N | 35% | API p95 under 150 ms |
| Q2 — large-tenant top-N | 10% | API p95 under 250 ms |
| Q3 — order detail | 25% | API p95 under 120 ms |
| Q4 — reporting | 5% | 99% under 5 seconds |
| W1 — status transition | 15% | p95 under 200 ms |
| W2 — create order | 10% | p95 under 250 ms |

These figures are **purely hypothetical requirements for this lesson**, not recommended SLOs for every system.

Why record the weights?

An index serving Q1/Q2—which together account for 45% of requests—may be a better investment than an index serving only Q4 at 5%, even if Q4 is slower per execution. Still, Q4 might be a business-critical workflow with its own dedicated SLO.

### Do Not Directly Add Group p95s

If Q1 p95 = 80 ms and Q2 p95 = 300 ms, the overall workload p95 is **not** 35%×80 + 10%×300 plus the other groups. The composite percentile must be calculated from the **latency distribution across all requests in the mix** or via an appropriate histogram aggregation.

Weighted averages apply to the **mean**, not as a substitute for percentiles.

## 16. Baseline: Measure Before Editing SQL or Creating Indexes

Before creating the `(tenant_id,status,created_at,order_id)` index:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT
    order_id,
    created_at,
    total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Repeat for Q2 and Q4. Record at least:

- Query text and parameters.
- PostgreSQL major version.
- Total row counts and table/index sizes.
- Plan nodes: `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, `Sort`, `Limit`, etc.
- `actual rows`, `Rows Removed by Filter`, and estimates.
- `Buffers: shared hit/read`, plus local/temp if present.
- `Execution Time`.
- Cache state, concurrency, and number of runs.

### Why `TIMING OFF`?

`TIMING OFF` reduces the per-node timing overhead while `EXPLAIN ANALYZE` still executes the query and reports total execution time. When you need to pinpoint which specific node is slow, run a diagnostic check with timing enabled.

**Do not assume a fixed plan from the lesson.** The planner chooses plans based on cost, statistics, version, configuration, cache, row counts, and actual data distribution.

## 17. Reading a Plan: `Index Cond` vs `Filter`

A plan might show:

~~~text
Index Cond: (tenant_id = 7)
Filter: (status = 'pending')
Rows Removed by Filter: ...
~~~

This indicates the index only narrows down rows by tenant, while `status` is applied as a filter after fetching candidate rows.

With a properly ordered multi-column index:

~~~text
Index Cond: ((tenant_id = 7) AND (status = 'pending'))
~~~

PostgreSQL can jump directly to the matching index slice, scan in `(created_at DESC, order_id DESC)` order, and stop after 20 rows without sorting the entire set.

### Seeing `Index Scan` Does Not Mean It Is Optimized

Ask:

1. Did buffer accesses decrease?
2. Did rows read / discarded by Filter decrease?
3. Did it eliminate sorting a large set?
4. Did p95 improve under realistic load?
5. Did INSERT/UPDATE paths slow down?

Switching a query from a 4.0 ms Seq Scan to a 3.8 ms Index Scan is rarely worth adding a large index.

## 18. Test One Index Change and Re-Measure

Candidate for Q1/Q2:

~~~sql
CREATE INDEX idx_perf_orders_tenant_status_latest
ON perf_goal_lab.orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);

ANALYZE perf_goal_lab.orders;
~~~

Re-measure with the exact same SQL and parameters:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Do the same for tenant 1.

### Expected Mechanism

When the leading columns use equality predicates, the B-tree index can supply the sort order on the trailing columns. With `LIMIT 20`, PostgreSQL can stop once enough rows are retrieved rather than scanning and sorting thousands or hundreds of thousands of rows.

### Must Also Measure Non-Target Queries

After creating the index, run Q3, Q4, W1, and W2 as well.

- Q3 will likely continue using the primary keys of `orders` and `order_items`.
- Q4 will likely continue using a Seq Scan because it reads and aggregates a large number of rows.
- W1 may incur extra work when updating `status`, which is an indexed key column.
- W2 must insert an entry into the additional index.

**An index that speeds up Q1/Q2 while degrading W1/W2 is a trade-off, not an automatic failure or automatic win.**

## 19. How Should a Before/After Report Table Look?

Example with **hypothetical figures**:

| Metric | Baseline | With Index |
| --- | ---: | ---: |
| Q1 p95 SQL (ms) | 45 | 5 |
| Q2 p95 SQL (ms) | 120 | 8 |
| Q3 p95 SQL (ms) | 9 | 9 |
| Q4 p95 SQL (ms) | 180 | 178 |
| W1 UPDATE p95 (ms) | 14 | 17 |
| W2 INSERT p95 (ms) | 8 | 10 |
| Write TPS at 16 clients | 2,800 | 2,650 |
| Additional index storage | 0 | 20 MB |

**This illustrates how to record results, not actual benchmark numbers.** Replace with real measurements, including variance and test configuration.

### Latency Reduction Formula

\[
\text{Latency reduction rate} =
\frac{L_{\mathrm{before}}-L_{\mathrm{after}}}
{L_{\mathrm{before}}}\times100\%
\]

For example, Q1 going from 45 ms down to 5 ms is about an 88.9% reduction. You should not write “88.9% throughput increase” because throughput has a different denominator and mechanism.

### Throughput Gain Formula

\[
\text{Throughput gain rate} =
\frac{X_{\mathrm{after}}-X_{\mathrm{before}}}
{X_{\mathrm{before}}}\times100\%
\]

If throughput drops from 2,800 to 2,650 TPS, that is a **decrease** of about 5.36%, even though the target read queries improved.

## 20. Query Latency and Transaction Latency Differ

An order-creation transaction might execute:

~~~text
BEGIN
  INSERT orders
  INSERT order_items
  UPDATE inventory
  INSERT outbox
COMMIT
~~~

Even if each of the four individual SQL statements takes 3 ms, the transaction does **not necessarily** take 12 ms. It also includes:

- Lock waits.
- Connection / network round trips.
- Trigger / FK checks.
- WAL flush at commit according to configuration.
- Application compute time between statements.
- Serialization/retry on contention.

An index change might slow `INSERT orders` by 1 ms while shaving 20 ms off a `SELECT` in another transaction. To evaluate the system, measure **individual SQL, transactions, and API workflows**.

### Measure Across the Same Boundary

When comparing baseline and candidate:

- If baseline uses API p95, candidate must also use API p95.
- If baseline uses server execution time, candidate must measure the same way.
- If the benchmark runs committed transactions, do not compare against a run that only executes SELECTs or ROLLBACKs.
- Do not mix client-recorded latency with server `Execution Time` and attribute the difference to an index.

## 21. Reading Real Statistics from `pg_stat_statements`

`pg_stat_statements` is an extension that aggregates call counts and execution times for SQL statements observed by PostgreSQL.

### Prerequisites

Typically it must be configured in `shared_preload_libraries` with a server restart before use. Once preloaded, a user with appropriate privileges creates the extension in the database:

~~~sql
-- Run only if the environment has configured the extension and permits it.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

**Do not modify configuration or restart production just for a practice exercise.** If the extension is not available, use application tracing, logs, and EXPLAIN to gather evidence first.

### Query Top SQL by Total Execution Time

~~~sql
SELECT
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    round(stddev_exec_time::numeric, 2) AS stddev_exec_ms,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 180) AS query_template
FROM pg_stat_statements
WHERE dbid = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Column names match many modern PostgreSQL versions; verify against your extension version. Visibility of query text and statistics for other users may be restricted.

### Interpretation

- `calls`: number of recorded invocations.
- `total_exec_time`: cumulative server execution time for the query template.
- `mean_exec_time`: mean execution time.
- `stddev_exec_time`: spread/variance of execution time.
- `rows`: total rows reported in the statistics.
- `shared_blks_hit/read`: cumulative buffer activity.

`pg_stat_statements` **does not by itself give full p95/p99 per API request**. It can also merge tenant 1 and tenant 7 under the same query template, letting the mean hide parameter skew.

## 22. Selecting Queries by Total Cost Rather Than the Single Slowest Query

Example:

~~~text
Q1: mean 2 ms × 100,000 calls = 200,000 ms total
Q2: mean 200 ms × 100 calls = 20,000 ms total
~~~

Q2 is **100× slower per call**, yet Q1 consumes **10× more total execution time** during the observation window.

When prioritizing, consider:

- Does Q1 consume high CPU/I/O and run very frequently?
- Does Q2 have a dedicated deadline, represent a critical operation, or hold locks?
- Is a slower query on the critical path of a user-facing request?
- Does optimizing Q1 impact the write path?
- Is an ORM generating N+1 queries that cause one endpoint to emit hundreds of small SQL statements?

**Do not blindly optimize the slowest query in the logs** without knowing its frequency and impact.

## 23. N+1 Queries: A Request Can Be Slow Even When Every SQL Query Is Fast

Suppose an API loads 100 orders:

~~~text
SELECT * FROM orders WHERE tenant_id = ? LIMIT 100;
Then loop 100 times:
  SELECT * FROM order_items WHERE order_id = ?;
~~~

Each child query takes only 1 ms, yet 100 round trips can make the API noticeably slow.

Measure:

- Number of SQL statements per request.
- Total DB time per request.
- Network/connection wait time.
- Number of rows returned.
- Whether queries can be batched or replaced with an appropriate JOIN/aggregation.

An index on `order_items(order_id)` helps each child query, but **reducing 101 queries down to 1–2 queries** can yield a far larger gain. However, a one-to-many JOIN can duplicate header columns, so inspect result size and fetch patterns.

**Query optimization starts with the workflow**, not just a single SQL statement.

## 24. Skewed Data and Most-Common-Values Statistics

The lab dataset is heavily skewed toward tenant 1. Inspect:

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    correlation,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'perf_goal_lab'
  AND tablename = 'orders'
  AND attname IN (
      'tenant_id',
      'status',
      'created_at',
      'customer_id'
  )
ORDER BY attname;
~~~

Key fields:

- `n_distinct`: estimated number of distinct values.
- `most_common_vals` and `most_common_freqs`: most common values and their corresponding frequencies.
- `correlation`: statistical correlation between value ordering and physical heap ordering.
- `null_frac`: fraction of NULL values.

Knowing only that there are 10 tenants is not enough to estimate tenant 1's row count accurately. Most-common values and skew heavily influence the planner.

### When Statistics Are Stale or Inaccurate

After bulk-inserting millions of rows, run `ANALYZE` to refresh stats. If multiple columns are strongly correlated, consider extended statistics to improve estimates.

~~~sql
CREATE STATISTICS st_orders_tenant_status (
    dependencies,
    mcv
)
ON tenant_id, status
FROM perf_goal_lab.orders;

ANALYZE perf_goal_lab.orders;
~~~

Extended statistics help the planner understand certain multi-column relationships; they **do not create access paths like an index does**. Measure plans and estimates before and after to verify they help.

## 25. Prepared Statements: Literal Queries Can Differ from Application Behavior

JDBC applications commonly use bind parameters:

~~~sql
WHERE tenant_id = $1
  AND status = $2
~~~

PostgreSQL may choose a **custom plan** tailored to specific parameter values or a **generic plan** reused across executions, depending on plan caching rules and cost.

Test in the lab:

~~~sql
PREPARE latest_orders(integer, text) AS
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE latest_orders(7, 'pending');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE latest_orders(1, 'pending');

DEALLOCATE latest_orders;
~~~

Two tenant parameters may receive different plans in custom-plan mode, whereas a generic plan does not always reflect per-value skew.

### Testing Generic and Custom Plans Deliberately

On versions supporting `plan_cache_mode`:

~~~sql
SET plan_cache_mode = force_custom_plan;

PREPARE p(integer, text) AS
SELECT order_id, created_at
FROM perf_goal_lab.orders
WHERE tenant_id = $1 AND status = $2
ORDER BY created_at DESC
LIMIT 20;

EXPLAIN EXECUTE p(1, 'pending');
EXPLAIN EXECUTE p(7, 'pending');

SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE p(1, 'pending');
EXPLAIN EXECUTE p(7, 'pending');

DEALLOCATE p;
RESET plan_cache_mode;
~~~

This is a **diagnostic test**, not advice to force custom or generic plans instance-wide. When benchmarking, match the application's actual protocol.

### Why Parameter Data Types Matter Too

If a column is `integer` but the application binds text and casts improperly, the resulting expression can differ from your literal SQL test. Inspect the SQL generated by your ORM/JDBC driver, including bind types and casts, rather than guessing from handwritten queries.

## 26. Throughput Under Concurrency: Don't Measure Only Single-Query SQL

To find out how many requests PostgreSQL handles under load, you need a tool that issues concurrent requests matching the workload model.

`pgbench` is a convenient choice for PostgreSQL benchmarking with custom scripts. It simulates multiple clients, threads, the prepared protocol, and weighted transaction mixes.

### Preparing Read-Only Scripts

Create sample file `latest-small.sql` on the benchmark host:

~~~text
\set tenant_id random(2, 10)
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = :tenant_id
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

File `latest-hot.sql`:

~~~text
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Run against the lab database:

~~~bash
pgbench -n -c 12 -j 4 -T 120 -P 10 -M prepared \
  -f latest-small.sql@7 \
  -f latest-hot.sql@3 \
  "postgresql://bench_user@localhost:5432/benchmark_db"
~~~

Options:

| Option | Meaning |
| --- | --- |
| `-n` | Skip the built-in benchmark initialization vacuum step |
| `-c 12` | 12 concurrent client connections |
| `-j 4` | 4 worker threads |
| `-T 120` | Run for roughly 120 seconds |
| `-P 10` | Print progress roughly every 10 seconds |
| `-M prepared` | Prepared protocol |
| `-f script@weight` | Relative weight among scripts |
| URI | Connect only to the dedicated benchmark database |

**Do not run high-load benchmarks on production.** Before running, verify hostname, database, permissions, and resources according to your organization's procedures.

### Why Include the Large Tenant?

Using only `random(2,10)` excludes tenant 1 entirely. In a system where 60% of data belongs to a large tenant, the benchmark would paint an overly optimistic picture.

The 7:3 ratio in the example is hypothetical. In practice, derive weights from real telemetry.

## 27. Fixed-Load Testing vs Saturation Testing

These answer two distinct questions.

### A. At the Target Load, What Is the Latency?

Use a controlled offered load, e.g., 250 transactions/s if supported by the environment:

~~~bash
pgbench -n -c 12 -j 4 -T 120 -R 250 \
  -M prepared -P 10 \
  -f latest-small.sql@7 \
  -f latest-hot.sql@3 \
  "postgresql://bench_user@localhost:5432/benchmark_db"
~~~

`-R` sets a target rate using `pgbench`'s rate-limiting mechanism. When the server falls behind, transactions accumulate schedule lag and some may be skipped/delayed depending on configuration; inspect actual throughput, latency, and accompanying stats.

**What to compare:** At the same offered load, are p95/p99 and error rates better before vs after?

### B. Where Is Maximum Capacity?

Gradually increase clients/rate to locate the throughput saturation region and the inflection point where latency spikes.

**What to compare:** Does the candidate increase peak goodput while staying within SLO? Raising attempted requests while increasing failures is not a useful improvement.

### Closed-Loop vs Open-Loop

A benchmark where “the client sends the next request only after the previous one finishes” automatically throttles offered load when the system slows down. That causes **coordinated omission** in some tail-latency measurement approaches.

When evaluating SLOs under a fixed arrival rate, run a test whose offered load is independent of response time and accounts for delayed/dropped requests. Document the load-generator model instead of comparing percentiles across two different benchmark modes.

## 28. Measuring p95/p99 Requires Suitable Latency Data

`pgbench` reports summary TPS and latency, and to analyze per-transaction tail distributions you can enable logging:

~~~bash
pgbench -n -c 12 -j 4 -T 120 -l \
  -M prepared \
  -f latest-small.sql@7 \
  -f latest-hot.sql@3 \
  "postgresql://bench_user@localhost:5432/benchmark_db"
~~~

Log files can grow very large. Content and format depend on version and options; protect sensitive data and avoid excessive logging that distorts the benchmark itself.

For application APIs, prefer latency histograms and distributed traces from your existing monitoring tools to measure end-to-end latency. Combine client-side benchmark metrics with server-side EXPLAIN to explain root causes.

### Do Not Mechanically Derive p95 from Mean and Standard Deviation

Latency distributions are rarely normal; they have long tails caused by lock waits, I/O, GC, checkpoints, or traffic bursts. Mean and stddev are not enough to compute accurate p95/p99 across arbitrary workloads.

## 29. Check Lock Waits Before Rushing to Add Indexes

An `UPDATE` statement may take 2 seconds **not because it lacks an index**, but because it is waiting for another transaction holding a row lock.

From a connection permitted to inspect activity:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    pg_blocking_pids(pid) AS blockers,
    left(query, 180) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;
~~~

If `wait_event_type = 'Lock'` and blocking PIDs are present, investigate why:

- Is a transaction staying open too long?
- Are two workers updating the same hot row?
- Is a DDL migration holding a table-level lock?
- Are FKs/triggers causing waits?
- Is there a deadlock/retry storm?
- Is an oversized connection pool amplifying contention?

An index can **shorten the row-lookup step** before locking, but it cannot eliminate all lock conflicts.

### Do Not Confuse CPU Time with Wait Time

A query taking 2 seconds of execution time mostly waiting on a lock calls for a very different fix than one burning 2 seconds of CPU sorting or aggregating. Measure wait events and blocked queries to choose the right direction.

## 30. Check I/O and Memory Before “Increasing `work_mem`”

An aggregate may be slow because sorts or hashes are spilling to temporary files:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    tenant_id,
    status,
    SUM(total_amount)
FROM perf_goal_lab.orders
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
~~~

The plan can reveal:

- `Sort Method` and memory or disk space used.
- `HashAggregate`/`GroupAggregate`.
- `temp read/write`.
- `Buffers`.
- Per-node timing when timing is enabled.

If a node spills due to data volume, `work_mem` can play a role. However, **do not raise `work_mem` server-wide indiscriminately**: a single query can allocate memory across multiple operators, and many queries run concurrently.

Similarly, an I/O-heavy query may need a plan/index/partition change, or an inspection of cache and disk throughput before tweaking SQL.

## 31. Optimize in System Priority Order

A pragmatic sequence:

1. **Confirm the exact SLO and measurement point.**
2. **Inspect telemetry:** which APIs/workloads violate SLOs or consume the most resources?
3. **Break down wait time** (pool, lock, I/O, network) vs execution time.
4. **Collect representative query templates and parameters.**
5. **Read plans and estimated vs actual rows.**
6. **Check existing indexes and statistics.**
7. **Formulate a single optimization hypothesis.**
8. **Measure baseline, apply change, re-measure.**
9. **Measure the full read–write mix at the same offered load.**
10. **Deploy only when benefit outweighs cost, with rollback and monitoring ready.**

Do not jump straight to step 7 before knowing where the workload is actually bottlenecked.

## 32. An Index Good for Reads Can Have Side Effects on Writes

Candidate index:

~~~sql
CREATE INDEX idx_perf_orders_tenant_status_latest
ON perf_goal_lab.orders (
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

may accelerate Q1/Q2. However, the statement:

~~~sql
UPDATE perf_goal_lab.orders
SET status = 'paid'
WHERE order_id = 10001
  AND status = 'pending';
~~~

modifies `status`—a column included in the index. PostgreSQL may have to maintain the index entry, write additional WAL, and lose opportunities for **HOT updates**.

Therefore, measure:

- W1 UPDATE p95/p99.
- W2 INSERT throughput.
- `n_tup_upd`, `n_tup_hot_upd`.
- WAL bytes during the same test window.
- Index size.
- CPU/I/O and replica lag if applicable.

### HOT Ratio

In `pg_stat_user_tables`:

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_hot_upd,
    n_tup_del,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'perf_goal_lab';
~~~

Reference HOT ratio:

\[
\text{HOT ratio} =
\frac{\text{HOT updates}}{\text{total updates}}
\]

Use **deltas of the counters before and after a benchmark window**, not long-lived cumulative ratios, to isolate the effect of a single change.

### Do Not Assume Every Index Slows Every UPDATE Equally

Actual cost depends on which columns change, HOT eligibility, page fill, caching, existing index count, row count, and concurrency. Measure instead of applying a fixed multiplier.

## 33. `EXPLAIN ANALYZE` on DML Must Be Handled Safely

To inspect an update plan in the lab:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL, TIMING OFF)
UPDATE perf_goal_lab.orders
SET
    status = 'paid',
    updated_at = clock_timestamp()
WHERE order_id BETWEEN 50001 AND 50500
  AND status = 'pending';

ROLLBACK;
~~~

**`EXPLAIN ANALYZE` actually executes the DML.** `BEGIN ... ROLLBACK` preserves the lab's logical data, yet it still generates WAL, dead tuple versions, and cleanup work. Do not rely on an always-rollback test and claim you have measured production's true commit and vacuum cost.

The `WAL` option in `EXPLAIN` is supported starting in PostgreSQL 13. On older servers, use version-appropriate options or other observation tools.

## 34. Measuring WAL and Storage in Write Tests

If your PostgreSQL version supports it:

~~~sql
-- PostgreSQL 14+, instance-level metrics.
SELECT
    wal_records,
    wal_fpi,
    wal_bytes
FROM pg_stat_wal;
~~~

Take the delta before and after the workload while accounting for background activity in other databases. `pg_stat_wal` provides **instance-wide statistics** and does not automatically separate WAL per query or schema on a busy cluster.

Storage size:

~~~sql
SELECT
    pg_size_pretty(
        pg_table_size('perf_goal_lab.orders'::regclass)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('perf_goal_lab.orders'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('perf_goal_lab.orders'::regclass)
    ) AS total_size;
~~~

An index that speeds up an API while occupying several GB may still be worthwhile; a tiny 10 MB index can still be undesirable if it imposes a frequent write-path tax with no clear benefit.

## 35. Read Benchmarks Must Match How the Application Reads

The application may use:

- JDBC `PreparedStatement`.
- An ORM generating `SELECT`s with `LIMIT/OFFSET`.
- Keyset pagination on `(created_at, order_id)`.
- A list query followed by per-row detail queries.
- The same query template with different parameter types.
- A connection pool with statement caching.

A benchmark running only literal SQL in `psql` can yield different plans.

### Offset Pagination vs Keyset

For a recent-orders listing:

~~~sql
SELECT order_id, created_at
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
OFFSET 10000
LIMIT 20;
~~~

PostgreSQL still has to walk past many rows in order to skip 10,000 rows. A matching index speeds up lookup and ordering, but it does not make deep offsets free.

If the API supports cursor/keyset pagination:

~~~sql
SELECT order_id, created_at
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
  AND (created_at, order_id)
      < (
          timestamptz '2026-03-01 00:00:00+00',
          175000::bigint
        )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

The tuple comparison matches the sort order; cursor values must come from the **last row of the previous page** in a real workflow. Arbitrary timestamps/IDs in examples only illustrate syntax, not an issued cursor.

### Compare Business Semantics Too

Keyset pagination reduces work for deep pagination, but differs in random page jumping, handling concurrent inserts/deletes, and cursor stability. Do not optimize performance by breaking the API contract without considering users.

## 36. Don't Benchmark Top-N Only with Small Tenants

An index:

~~~sql
(tenant_id, status, created_at DESC, order_id DESC)
~~~

can return the 20 newest orders very quickly for both small and large tenants. Yet other queries without `LIMIT` or using `ORDER BY total_amount` may behave completely differently.

Your test parameter suite should cover:

1. High-volume tenant.
2. Low-volume tenant.
3. Common `pending` status.
4. Rare `failed` status.
5. Short date range.
6. Long date range.
7. 0-row result.
8. 1-row result.
9. Very large result.
10. Recent data / start of history.
11. Small `LIMIT` query.
12. Aggregate query without `LIMIT`.

You do not need to test infinitely many parameter values; choose **classes with distinct cost characteristics** and weight them by real telemetry.

## 37. Assumptions About Indexes and Selectivity

Suppose there is a single-column index on `status`:

~~~sql
CREATE INDEX idx_perf_orders_status
ON perf_goal_lab.orders(status);
~~~

The query:

~~~sql
SELECT COUNT(*)
FROM perf_goal_lab.orders
WHERE status = 'pending';
~~~

must process roughly 79% of the rows in the lab. The planner may choose Seq Scan / Parallel Seq Scan on cost grounds even though the index exists.

On the exact same index, `status = 'failed'` matches only about 1% of rows and may benefit differently. Even so, there is no universal selectivity threshold below which PostgreSQL is forced to pick an index.

**Representative queries must include both common and rare values**, not just samples that favor the optimizer's hypothesis.

## 38. A Change Can Shift the Bottleneck

Before the index, Q1 spent most of its CPU filtering and sorting. With the index, Q1 is fast, yet system throughput still fails to climb because:

- The connection pool is capped.
- API serialization saturates CPU.
- WAL flush becomes the write-path bottleneck.
- A hot inventory row causes lock contention.
- Read replicas fall behind with lag.
- Network saturates from returning too much data.

This is **bottleneck migration**: resolving one limit exposes the next limit.

Therefore, after each optimization step:

1. Re-measure end-to-end.
2. Observe which component now dominates time.
3. Check whether SLOs are met.
4. Stop optimizing once goals are met and further changes aren't worth the cost.
5. Do not keep adding indexes just because one more query could become a few microseconds faster.

## 39. When to Tune the Query First vs When Architecture Must Change

A slow query can often be resolved via:

- An appropriate index.
- Rewriting filter predicates so they do not block index usage.
- Joining on proper keys and avoiding Cartesian products.
- Eliminating N+1 queries.
- Pagination and reducing returned columns.
- Refreshing `ANALYZE` / adding extended statistics.
- Batching DML operations.
- Adjusting transactions to reduce lock waits.

However, some problems call for broader solutions:

- Dashboards summing billions of rows every time a user opens the page → consider summary/aggregate tables, materialized views, or an appropriate pipeline.
- Massive historical datasets queried by time ranges → consider partitioning or BRIN depending on data layout.
- Read demand exceeding single-node capacity → consider caching or read replicas along with consistency guarantees.
- Write workloads exceeding WAL/storage capacity → optimize batching, schema, or storage/architecture.

**Do not jump to complex architecture before measuring the bottleneck; equally, do not try to fix a fundamental workload limit with a single index.**

## 40. Designing a Fair A/B Test

Minimum procedure:

~~~text
1. Build dataset D with consistent statistics.
2. Baseline A: mandatory indexes + workload W.
3. Warm up A, measure A across multiple runs.
4. Restore to state D.
5. Candidate B: add only the candidate index.
6. Equivalent warm-up for B, measure B with the same W.
7. Compare latency, throughput, buffers, WAL, HOT, size.
8. If cache or time drift is suspected, alternate A/B runs.
~~~

### Biases to Avoid

- A runs on cold cache, B runs on warm cache.
- A has 240,000 rows, B has 500,000 rows after INSERTs.
- A uses tenant 1, B uses tenant 7.
- A uses a prepared generic plan, B uses literals.
- A runs with 1 concurrent client, B runs with 16.
- A has a fresh `ANALYZE`, B does not.
- A runs alongside autovacuum, B runs on an idle host.
- A is read-only, B includes writes.
- A commits, B rolls back.
- B accumulates multiple new indexes instead of testing one candidate.

These discrepancies make it impossible to separate **the effect of the index** from **the effect of the test conditions**.

## 41. Why Repeating a Test Isn't Enough If Data Doesn't Match Production

Suppose a benchmark runs 100 iterations with very low standard deviation, yet:

- The table has only 10,000 rows.
- The entire table fits in RAM.
- There are no concurrent writers.
- There is no tenant skew.
- There are no long transactions.
- There is no index bloat.
- The query always returns one row.

The results can be highly **consistent** yet still **unrepresentative** of production with tens of millions of orders and hundreds of concurrent workers.

Two distinct properties:

- **Repeatability:** re-running under the same conditions produces similar results.
- **Representativeness:** the simulated conditions reflect the actual system being tuned.

A sound measurement needs both. Precisely measuring an irrelevant workload will not lead to good decisions.

## 42. Measure Committed Workloads Rather Than Only Rollbacks

In lab examples, `BEGIN ... ROLLBACK` helps you practice SQL without permanently altering the seed data. However, production write benchmarks must account for:

- Commit WAL and durability settings.
- Table and index growth.
- Dead tuple accumulation after UPDATE/DELETE.
- Autovacuum activity.
- Lock contention.
- Visibility map changes.
- Replica replay.

A rollback-only benchmark **does not fully simulate** these conditions.

Use a **cloned/disposable database**, load the same initial dataset, run real committed transactions there, and reset before testing the next candidate.

**Never apply this approach directly to a production database.**

## 43. Multi-Layer Measurement Checklist

| Layer | Tool | What You Get |
| --- | --- | --- |
| Browser / client | Browser/app telemetry | True user-perceived latency |
| Gateway/API | Tracing, request histograms | RPS, p50/p95/p99, errors/timeouts |
| Connection pool | Pool metrics | Wait time, active/idle connections, queue |
| Aggregated SQL | `pg_stat_statements` | Calls, total/mean exec time, blocks |
| SQL plan | `EXPLAIN (ANALYZE, BUFFERS)` | Operators, rows, buffer accesses |
| PostgreSQL activity | `pg_stat_activity` | Wait events, transaction age, blockers |
| Tables/indexes | `pg_stat_user_tables/indexes` | DML/HOT/scan statistics |
| WAL | `pg_stat_wal` by version | Instance-level WAL records/bytes |
| Host | OS monitoring | CPU, memory, disk IOPS/latency |
| Replica | Replication monitoring | Lag, replay health |
| Load generation | `pgbench`/load testing | Offered load, TPS, client latency |

Not every system needs every tool. Pick data sources to **answer a specific hypothesis** rather than opening dozens of dashboards without knowing what to look for.

## 44. Monitoring Long-Running and `idle in transaction` Sessions

A single query can slow down due to the impact of another transaction:

~~~sql
SELECT
    pid,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 120) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Transactions holding snapshots or locks for long periods can:

- Force other writers to wait.
- Retain old row versions, impeding vacuum.
- Increase bloat over time.
- Cause index-only scans to incur more heap fetches.

If you spot `idle in transaction`, investigate its owner/caller and expected duration; never terminate PIDs in production without understanding the consequences.

**Query optimization also includes transaction management**, not just adding indexes.

## 45. Measuring Periodic Jobs and Rare Paths

A representative workload must cover:

- Peak hours.
- Nightly batch runs.
- Beginning/end-of-month reports.
- Large data imports.
- Cleanup/retention jobs.
- Retry storms when downstream services fail.
- Queries from the largest tenant.
- Operational queries that must run fast during incidents.

An index showing `idx_scan = 0` after one day is not necessarily useless if it supports month-end jobs or enforces a UNIQUE/PRIMARY KEY constraint. Do not drop indexes based on too short an observation window.

## 46. A Query Optimization Report Template

A handoff-ready report should document:

| Section | Information |
| --- | --- |
| **Goal** | Endpoint/workflow, p95/p99, RPS/TPS, errors/timeouts |
| **Scope** | Measurement window, peak/normal, tenants, data |
| **Environment** | PostgreSQL version, CPU, RAM, disk, config, replicas |
| **Representative queries** | SQL templates, bind types, parameters, and weights |
| **Baseline** | API/SQL latency, plans, buffers, locks, TPS |
| **Hypothesis** | Why the change is expected to help |
| **Candidate** | Specific DDL or query change |
| **Methodology** | Warm-up, iterations, offered load, concurrency, reset |
| **Read results** | p50/p95/p99, rows, buffers, sorts |
| **Write results** | W1/W2 latency, throughput, WAL, HOT |
| **Trade-offs** | Index size, vacuum, replica lag, cost |
| **Decision** | Keep/revise/discard, rationale, and risks |
| **Rollout** | DDL plan, monitoring, rollback thresholds |

Transparency matters more than pretty charts. If the data is insufficient to conclude, explicitly state **what is missing** and what extra measurements are needed.

## 47. Example of a Conditional Decision

Suppose after a representative benchmark, you observe these illustrative results:

- Q1/Q2 p95 drops sharply and meets the SLO.
- Q3 is essentially unchanged.
- Q4 does not improve.
- W1 p95 increases by 10%.
- W2 TPS decreases by 3%.
- The index adds 80 MB of storage.
- Replica lag stays within threshold.
- Load of 600 requests/s is sustained with error rate within SLO.

If the system's write-cost budget allows **no more than a 15% p95 increase**, storage has plenty of headroom, and Q1/Q2 are on the critical path, the index may be worth deploying.

If W1 is actually a payment flow requiring ultra-low p99, a 10% p95 increase is not yet proof of safety. You must measure p99, errors, lock waits, and peak load.

**A good decision follows pre-defined goals and constraints**, rather than picking whichever option has the most “green” metrics.

## 48. Common Mistakes

### 48.1. Optimizing Before Defining SLOs

Without knowing the target, it is easy to waste time tuning a query that is already fast enough.

### 48.2. Looking Only at Average Latency

The mean can hide terrible p99 or timed-out requests.

### 48.3. Treating a Single SQL's Execution Time as API Latency

Ignores pool, network, application logic, and other SQL statements.

### 48.4. Testing Only Under Low Load

A query taking 5 ms with zero concurrency does not guarantee good p95 at 600 RPS.

### 48.5. Confusing RPS, QPS, and TPS

A single request may execute multiple statements and transactions.

### 48.6. Testing Favorable Queries Instead of Representative Ones

Picking a small tenant and a key guaranteed to hit an index while skipping large tenants and aggregates.

### 48.7. Generating Uniform Seed Data When Production Is Heavily Skewed

The real planner and workload behavior may be completely different.

### 48.8. Ignoring Write Ratio

An index great for Q1 can slow down W1/W2.

### 48.9. Taking a Weighted Average of Group p95s

The percentile of a combined workload cannot be computed by linearly combining individual percentiles.

### 48.10. Computing p95 from Mean and Stddev Without Justification

Latency distributions usually have long tails; measure the actual distribution.

### 48.11. Dropping Errors/Timeouts from Reports

Counting only successful requests makes p95 look artificially good while the system is overloaded.

### 48.12. Having No Baseline

You cannot prove what an index changed without before-state numbers.

### 48.13. Running `EXPLAIN` Once Under Different Cache States

Results can be skewed by caching or background activity.

### 48.14. Assuming `shared read` Always Means Physical Disk Read

Blocks read into `shared_buffers` may come from the OS page cache.

### 48.15. Testing Literal Queries When the App Uses Prepared Statements

Custom/generic plans and bind types can behave differently.

### 48.16. Ignoring Lock Waits

A query slowed by blocking does not necessarily need an index.

### 48.17. Raising `work_mem` Server-Wide to Fix One Sort

Concurrent queries can end up consuming huge amounts of memory.

### 48.18. Adding Multiple Indexes at Once

You cannot isolate the individual impact of each candidate.

### 48.19. Benchmarking Only with Rolled-Back Transactions

Fails to simulate real commits, WAL, and bloat/vacuum lifecycles.

### 48.20. Treating `EXPLAIN ANALYZE UPDATE` in Production as a Dry Run

`ANALYZE` actually executes the DML and produces real effects.

### 48.21. Benchmarking Throughput Only, Ignoring p95/p99 and Error Rate

Higher TPS accompanied by worse tail latency and retries can hurt user experience.

### 48.22. Seeing `idx_scan=0` and Dropping the Index

Forgets constraints, infrequent jobs, and short observation windows.

### 48.23. Omitting PostgreSQL Version and Config

Makes results hard to reproduce; planner and feature differences matter.

### 48.24. Not Verifying Business Correctness

A fast benchmark where every INSERT hits `ON CONFLICT DO NOTHING` is not a win.

### 48.25. Not Measuring After Deployment

Staging can differ from production in cache, data distribution, peak load, and replication.

### 48.26. Failing to Stop Once Goals Are Met

Further tuning can add risk and cost for negligible value.

## 49. Practice Exercises with Answers

Use the `perf_goal_lab` schema from section 13. Statements with DML side effects are wrapped in `BEGIN ... ROLLBACK` when used solely for illustration. Index-creation statements apply to the lab database and should take existing indexes into account to avoid duplicates.

### Exercise 1. Distinguishing Vague vs Measurable Goals

**Question:** What is missing from “The database needs to be faster”?

**Answer:** It lacks the target endpoint/workload, latency measurement point, p95/p99 targets, throughput and concurrency levels, load conditions, measurement window, error rate, and write/storage impact limits.

### Exercise 2. RPS and QPS

An API receives 500 requests/s, and each request executes an average of 4 SQL statements.

**Answer:** If all requests complete and each executes an average of 4 statements, that is roughly **2,000 SQL executions/s**. Do not infer TPS without knowing transaction boundaries.

### Exercise 3. Little's Law

A system steadily completes 200 requests/s with a mean response time of 250 ms.

**Answer:** The average number of requests inside the measured boundary is roughly `200 × 0.25 = 50`. Do not infer that exactly 50 DB connections are required.

### Exercise 4. Distinguishing Mean and p99

**Question:** Why does a 20 ms mean not guarantee every user waits under 100 ms?

**Answer:** A small number of requests can take several seconds while the mean stays low. You must inspect percentiles, errors, and timeouts.

### Exercise 5. From API SLO to SQL Target

API p95 must be under 150 ms, and SQL accounts for only 8 ms inside a 120 ms request.

**Answer:** Cutting SQL from 8 ms to 2 ms will not fix pool/network overhead that dominates the request; break down time per layer to target the real bottleneck.

### Exercise 6. Recording Q1 Baseline

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 7 AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

**Answer:** Record the plan, actual/estimated rows, buffers, sort nodes, and execution time before creating an index; never fill in unmeasured timings.

### Exercise 7. Tenant Skew

**Question:** Why is testing only tenant 7 insufficient?

**Answer:** Tenant 1 owns roughly 60% of orders, so queries with the same template have vastly different candidate row counts and selectivity. You must test large tenants too.

### Exercise 8. Proposing a Top-N Index

~~~sql
CREATE INDEX idx_exercise_latest
ON perf_goal_lab.orders(
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

**Answer:** Matches equality filters on tenant/status and the top-N sort order. If an equivalent `idx_perf_orders_tenant_status_latest` already exists, do not keep both indexes outside testing.

### Exercise 9. Why Not Conclude from `Index Scan` Alone?

**Answer:** You must inspect buffers, rows, sorts, latency under load, write overhead, and storage; a plan using an Index Scan can still be worse overall.

### Exercise 10. Which Query Processes Many Rows?

Compare Q1 (`LIMIT 20`) with Q4 (monthly revenue aggregation).

**Answer:** Q4 must read and group many rows; a top-N index does not automatically speed it up, and a Seq Scan may be the sensible plan.

### Exercise 11. Calculating Latency Reduction Percentage

Q1 p95 drops from 120 ms to 30 ms.

**Answer:** A reduction of `(120-30)/120 = 75%`.

### Exercise 12. Calculating Throughput Gain

Write TPS increases from 2,000 to 2,200.

**Answer:** A gain of `(2200-2000)/2000 = 10%` if measured on the same workload and under the same conditions.

### Exercise 13. Why Not Compute a Weighted Sum of Group p95s?

**Answer:** The percentile of a mixed workload depends on the full distribution of all requests, not a linear combination of subgroup percentiles. Calculate it from the combined raw samples or an appropriate histogram.

### Exercise 14. How to Spot High-Frequency Queries

**Answer:** Inspect `pg_stat_statements.calls`, `total_exec_time`, and application telemetry; a query with a tiny mean execution time called millions of times can still be a top priority.

### Exercise 15. Testing Parameterized Queries

~~~sql
PREPARE p(integer, text) AS
SELECT order_id
FROM perf_goal_lab.orders
WHERE tenant_id=$1 AND status=$2
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

EXPLAIN EXECUTE p(1, 'pending');
EXPLAIN EXECUTE p(7, 'pending');
DEALLOCATE p;
~~~

**Answer:** Lets you inspect plans in a form closer to application prepared statements; still check custom/generic plan behavior and the real wire protocol.

### Exercise 16. Distinguishing Lock Waits from CPU Work

**Answer:** `pg_stat_activity.wait_event_type='Lock'`, `pg_blocking_pids`, and transaction age help identify lock waits; do not automatically assume a missing index.

### Exercise 17. Why Does `EXPLAIN ANALYZE UPDATE` Need Rollback in the Lab?

**Answer:** Because `ANALYZE` actually executes the UPDATE. Rolling back prevents persisting business changes while still incurring tuple/WAL work; it is not a true committed write benchmark.

### Exercise 18. Explaining `shared hit/read`

**Answer:** `hit` indicates blocks already found in `shared_buffers`; `read` indicates blocks fetched into `shared_buffers`, which may come from the OS page cache rather than physical disk.

### Exercise 19. Evaluating a Read/Write Trade-Off

An index cuts Q1 p95 by 80% but increases UPDATE p95 by 25%.

**Answer:** You cannot decide based on Q1 alone. Weigh against the UPDATE SLO, Q1/W1 traffic share, write TPS, WAL, storage, tail latency, and business priorities.

### Exercise 20. When Are Longer / Multi-Run Benchmarks Needed?

**Answer:** When evaluating p95/p99, saturation, cache behavior, checkpoint/autovacuum effects, or time-varying workloads. A run lasting only a few seconds is rarely representative.

### Exercise 21. Why Measure APIs Instead of Just SQL?

**Answer:** SQL is only one piece of a request; network, connection pooling, serialization, N+1 patterns, and downstream service calls can dominate end-to-end latency.

### Exercise 22. Is a Query Returning 0 Rows a Good Benchmark?

**Answer:** Only if 0-row lookups occur at that frequency in reality. If production normally returns rows while the benchmark always misses, the results are overly optimistic.

### Exercise 23. Why Is 1,000 RPS of All Errors Not a Win?

**Answer:** Total throughput does not measure business success. You need goodput, error rates, timeouts, and actually committed transactions.

### Exercise 24. When Do You Stop Optimizing?

**Answer:** When SLOs and throughput targets are met under representative load, write and storage costs are within bounds, and further improvements do not justify the risk or cost.

## 50. Checklist for Starting a PostgreSQL Optimization Task

- [ ] Identify the endpoint/workflow or query to improve.
- [ ] Specify the latency measurement point: client, API, transaction, or SQL.
- [ ] Set p95/p99 SLOs, load conditions, and measurement window.
- [ ] Define throughput (RPS/QPS/TPS) and goodput.
- [ ] Record error rate, timeout, and retry policies.
- [ ] Gather query templates from telemetry.
- [ ] Include point lookup, top-N, JOIN, aggregate, INSERT, and UPDATE classes.
- [ ] Identify tenant skew, common/rare statuses, and result sizes.
- [ ] Match application SQL, bind types, and prepared plans.
- [ ] Prepare representative data rather than overly small tables.
- [ ] Measure baseline before creating indexes or rewriting SQL.
- [ ] Use `EXPLAIN (ANALYZE, BUFFERS)` in a safe environment.
- [ ] Inspect estimated/actual rows, Index Cond, Filter, Sort, and Heap Fetches.
- [ ] Check lock waits, pool waits, CPU, and I/O.
- [ ] Change only one primary variable per A/B round.
- [ ] Keep warm-up, run counts, and concurrency equivalent.
- [ ] Measure p50/p95/p99, TPS, and errors at the target offered load.
- [ ] Also measure write latency, WAL, HOT, index size, and replica lag if applicable.
- [ ] Never run heavy load benchmarks or destructive DML on production.
- [ ] Clearly distinguish hypothetical numbers from actually measured data.
- [ ] Prepare a rollback/migration plan and post-rollout monitoring.
- [ ] Conclude only when benefits outweigh trade-offs and satisfy SLOs.

## 51. Official PostgreSQL Documentation

When applying these techniques to real systems, verify against the **exact major version of PostgreSQL and `pgbench`** you are running:

- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — how to read plans, row estimates, scans, and costs.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — `ANALYZE`, `BUFFERS`, `WAL`, and DML caveats.
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html) — histograms, most-common values, extended stats.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query call counts and execution time statistics.
- [pgbench](https://www.postgresql.org/docs/current/pgbench.html) — custom scripts, weights, concurrency, rate limiting, and logging.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_activity`, `pg_stat_user_tables`, `pg_stat_wal`, `pg_stat_progress_create_index`.
- [Indexes](https://www.postgresql.org/docs/current/indexes.html) — role and cost of indexes.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html) — B-tree, GIN, GiST, BRIN, and access methods.
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html) — composite key order and predicate optimization.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples, autovacuum, and plan impact.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — MVCC, snapshots, and concurrency.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock waits, deadlocks, and transaction coordination.
- [PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html) — generic and custom plans.

`/current/` links to the current version's docs on the PostgreSQL website. For servers or tools on another version, consult that version's documentation before using new measurement options.

## 52. Summary

**PostgreSQL query optimization must begin with goals and workload, not with indexes or SQL syntax.**

Key principles:

1. **Define latency by measurement point and percentile.** The mean or a single `EXPLAIN` execution time does not represent end-to-end p95/p99.
2. **State throughput under concrete load conditions.** QPS, TPS, RPS, goodput, and concurrency are not a single number.
3. **Select queries that represent the real workload.** Include SQL templates, skewed parameters, realistic data distributions, JOINs/aggregates, and write operations.
4. **Start with a baseline.** Without pre-change measurements, you cannot prove a new index's effectiveness.
5. **Use EXPLAIN, statistics, and load tests as complementary evidence.** Each tool observes only one part of the system.
6. **Measure read–write trade-offs at the same offered load.** An index helping top-N while raising W1/W2 WAL or latency may or may not be worthwhile depending on SLOs.
7. **Decide and deploy in a controlled manner.** Document test methodology, keep rollback options ready, and re-measure in production against the exact SLOs you defined.

The closing question of an optimization pass is not “Did PostgreSQL use the index?”, but **“Does the system serve the real workload at the committed latency, throughput, success rate, and operational cost?”** Only when you can answer that with measured data does optimization truly deliver value.
