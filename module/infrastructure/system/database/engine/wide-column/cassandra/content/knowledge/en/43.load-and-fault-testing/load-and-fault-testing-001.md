# Designing Read/Write Workloads from Business Queries for Load and Distributed Fault Testing in Cassandra

## 1. Why Measuring "100,000 requests/second" Can Still Solve the Wrong Problem

Apache Cassandra is a distributed **wide-column** database. Data resides on replicas determined by the **partition key**, **replication factor (RF)**, and datacenter/rack topology; read/write outcomes depend on the **consistency level (CL)** and the state of each replica. Cassandra does not distribute the cost of all CQL statements equally. Two requests that each return a single row can differ drastically in the number of SSTables read, partition hotness, network hops, compaction impact, and coordinator work required.

Suppose a real e-commerce system has:

- 60% operations listing a customer's or tenant's latest orders for a given day.
- 20% fetching order details by order ID.
- 15% creating an order, writing to two tables that serve two different read patterns.
- 5% updating order status, also writing to two tables.

If a benchmark only runs `SELECT ... WHERE order_id = ?` across a few thousand cached keys and announces "100,000 QPS", it **fails to measure** the cost of listing long partitions, dual writes, concurrent updates, tombstones from TTLs, or hot partitions that appear during a sales campaign.

Conversely, a benchmark that only spams random `INSERT` statements fails to reflect read/write ratios or business query paths. When a node fails, an average result stating "still at 80% throughput" does not tell you **whether customers can actually read the orders they just created**.

**This lesson explains how to design workloads from business journeys down to CQL/Java**, collect explainable metrics, and establish safety boundaries before injecting distributed faults. The numbers in the examples are **hypothetical modeling assumptions**, not real benchmarks or recommended default settings for every cluster.

### Learning Outcomes

1. Translate application journeys/APIs into a **CQL query matrix** with realistic occurrence ratios.
2. Distinguish **logical business operations**, CQL statements, driver attempts, and replica-level work.
3. Design seed data and **hot/cold key distributions**, payloads, TTLs, deletes, and lifecycle states.
4. Define **offered load**, concurrency limits, open-loop/closed-loop models, and load test phases.
5. Measure p50/p95/p99 latencies, achieved throughput, error rates, data correctness, queuing/backpressure, and node health.
6. Use CQL, Java Driver 4.x, observability tools, and a fault matrix without equating a single benchmark to production SLOs.
7. Establish **stop** thresholds for load testing, especially before injecting node/network/disk failures.

> **Principle:** Start from **user actions → actual CQL statements → affected partitions/replicas → SLOs and data correctness**. Only then choose the load-generation tool.

## 2. Four Measurement Units That Must Not Be Mixed

| Level | Example | Unit | Common Misconception |
| --- | --- | --- | --- |
| Business operation | "Create an order" | operations/s | One operation may execute multiple CQL statements |
| CQL execution | `INSERT orders_by_id` | executions/s | One CQL statement may retry/speculate into multiple attempts |
| Driver attempt | Sent to coordinator, may retry | attempts/s | A timeout does not guarantee the mutation was not applied |
| Replica/internal work | Coordinator sends read/write to replicas | internal messages, CPU, I/O | Cannot simply multiply CQL rate × RF for all reads/writes |

When creating an order requires writing to two tables, a single "create order" operation can generate **at least two INSERT statements**. With retries, one HTTP operation may spawn additional attempts; with paging, opening a list once may fetch multiple pages.

Simple planning formula:

\[
R_{\text{CQL,offered}} \approx \sum_{i=1}^{n} R_{\text{business},i}
\times \overline{Q}_{i}
\]

Where:

- \(R_{\text{business},i}\): number of business operations/s of type \(i\).
- \(\overline{Q}_{i}\): average number of CQL executions per **single** business operation of type \(i\), including planned page fetches.
- Retries/speculative executions are excluded here; they must be measured separately.

**This is an input estimation formula, not a formula for measuring CPU/disk or replica message counts.** One statement can touch different numbers of SSTables, replicas, or token ranges; CL and RF affect the cost depending on the read/write path.

## 3. Building the Workload from a Business Journey Map

### Step 1 — List User or System Actions

An input table:

| Journey | API/worker | Core Behavior | Correctness Criteria |
| --- | --- | --- | --- |
| View list | `GET /tenants/{t}/orders?day=D` | `SELECT` a daily partition, with paging | Newest first, no cross-tenant leakage |
| View detail | `GET /orders/{id}` | `SELECT` by full partition key | Returns accurate status, no mixed orders |
| Create order | `POST /orders` | Two `INSERT`s into two query tables | No lost orders / no duplicate logical orders |
| Change status | Payment worker | Two `UPDATE`s by full keys | Status reflects valid state transitions |
| Expire/delete data | Retention job | TTL/delete per policy | No expired data retained, tombstones accounted for |

Not every API maps one-to-one to a single CQL statement. Any hidden queries in repositories, cache fallbacks, permission lookups, idempotency checks, or multi-day fan-outs must be included in the model.

### Step 2 — Specify Query Shape, Not Just API Name

For each action, document:

- CQL template/prepared statement and meaningful **bound variables**.
- Partition key and clustering predicates; whether `IN`, range scans, secondary indexes/SAI, or fan-out are used.
- Number of rows/bytes returned; page size, probability of fetching the next page.
- Read/write ratio, concurrency, and peak periods.
- CL, local DC, request timeout, retry/idempotency rules.
- Prerequisite actions that must occur beforehand (e.g., **create order then view detail**).
- Data conditions: live, freshly written, near-TTL expiration, tombstone-heavy, or updated.

### Step 3 — Group by Query Shape Instead of Taking a Single Average Ratio

Do not merge two fundamentally different `SELECT` patterns:

```text
READ_DETAIL:
  WHERE order_id=?
  1 partition, at most 1 row, small payload

READ_LIST:
  WHERE tenant_id=? AND order_day=?
  1 partition, many clustering rows
  1–3 pages, may touch multiple SSTables/tombstones
```

An overall average like "80% reads" hides critical differences. Dashboards must break down metrics by **query template** as well as hot/cold key cohorts, row size, DC, and CL.

## 4. Example of Load Mix Calculation and CQL Fan-Out

Assume **1,000 logical operations/s** at peak hour:

| Action | Share | Business ops/s | Modeled CQL executions/operation |
| --- | ---: | ---: | --- |
| READ_LIST | 60% | 600 | Average 1.4 page fetches |
| READ_DETAIL | 20% | 200 | 1 SELECT |
| CREATE_ORDER | 15% | 150 | 2 INSERTs |
| UPDATE_STATUS | 5% | 50 | 2 UPDATEs |
| **Total** | **100%** | **1,000** | Action-dependent |

Before retries, the offered CQL rate is approximately:

\[
600 \times 1.4 + 200 \times 1
+ 150 \times 2 + 50 \times 2 = 1440\ \text{CQL executions/s}
\]

Breakdown:

- Reads: \(840+200=1040\) CQL/s.
- Writes: \(300+100=400\) CQL/s.
- Read/write at business level: 80%/20%.
- Read/write at **CQL executions** level: approximately 72.2%/27.8%.

**Note:** the read/write ratio will shift when paged reads fetch more pages, dual writes undergo retries, or the application adds permission checks or transaction ledger writes. Therefore, never configure a generator simply as "80% read, 20% write" and conclude it represents the system.

### What About Retries?

Suppose the driver/gateway generates extra attempts due to timeouts; do **not** simply count every attempt as a successful business operation. Report separately:

```text
logical_operations_offered
logical_operations_completed_successfully
cql_executions_requested
driver_attempts
retries_and_speculations
unknown_write_outcomes
```

For counters, list appends, LWTs, and TTLs, blind retries can corrupt data. Never trade correctness to inflate the count of "successful requests".

## 5. Lab Schema: Two Tables for Two Business Read Paths

The lab assumes datacenter `dc1` with **three replicas** to demonstrate `LOCAL_QUORUM` at RF3. If you only have a single node, adjust RF appropriately **for lab use only**; RF1 cannot simulate a 2/3 quorum or a single-replica failure.

```sql
CREATE KEYSPACE IF NOT EXISTS load_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS load_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    tenant_id text,
    order_day date,
    created_at timestamp,
    status text,
    total_cents bigint
);

CREATE TABLE IF NOT EXISTS load_lab.orders_by_tenant_day (
    tenant_id text,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    total_cents bigint,
    PRIMARY KEY ((tenant_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
```

**Purpose of each table:**

- `orders_by_id` serves `GET /orders/{id}`: partition key `order_id`.
- `orders_by_tenant_day` serves order listings for a tenant/day: partition key `(tenant_id, order_day)` and clustering by `created_at DESC, order_id ASC`.

This is **intentional denormalization**. One logical order is represented across two tables for two query shapes. To benchmark `CREATE_ORDER` properly, you must measure both writes, individual write failures, and the reconciliation mechanism if one table succeeded while the other did not. Never assume two `INSERT`s to **two different partitions** form an ACID transaction just because they reside in the same service.

### Query Templates Matching the Matrix

```sql
-- READ_DETAIL: single order_id, typically at most one row.
SELECT order_id, status, total_cents, tenant_id, order_day
FROM load_lab.orders_by_id
WHERE order_id = ?;

-- READ_LIST: exact composite partition key, ordered by clustering columns.
SELECT created_at, order_id, status, total_cents
FROM load_lab.orders_by_tenant_day
WHERE tenant_id = ? AND order_day = ?
LIMIT 100;

-- CREATE_ORDER — first write.
INSERT INTO load_lab.orders_by_id (
    order_id, tenant_id, order_day, created_at, status, total_cents
) VALUES (?, ?, ?, ?, ?, ?);

-- CREATE_ORDER — second write.
INSERT INTO load_lab.orders_by_tenant_day (
    tenant_id, order_day, created_at, order_id, status, total_cents
) VALUES (?, ?, ?, ?, ?, ?);

-- UPDATE_STATUS in the detail-read table.
UPDATE load_lab.orders_by_id
SET status = ?
WHERE order_id = ?;

-- UPDATE_STATUS in the list-read table:
-- must include the full partition + clustering key.
UPDATE load_lab.orders_by_tenant_day
SET status = ?
WHERE tenant_id = ? AND order_day = ?
  AND created_at = ? AND order_id = ?;
```

Keep the same logical `order_id`, `tenant_id`, `order_day`, and `created_at` when writing to both tables. If a retry generates a new `order_id`, the generator may accidentally duplicate data instead of simulating a true retry.

### Do Not Use `ALLOW FILTERING` to Simulate Business Queries

A query such as `SELECT * FROM orders_by_id WHERE status='PAID' ALLOW FILTERING` can scan large volumes of data and **does not represent** the ID-lookup endpoint. If the business requires querying orders by status, it needs its own dedicated table/index/query plan and **a separate workload row**.

## 6. Key Distribution: Hot Tenants, Hot Partitions, and the "Long Tail"

When a load generator selects keys, both extremes are wrong:

- **Uniform across all keys** when production has a few very hot tenants.
- **Only one key/partition** when production has millions of widely distributed tenants.

An illustrative distribution model only:

| Tenant Cohort | Share of Tenants | Share of Requests |
| --- | ---: | ---: |
| Top 1% "very hot" | 1% | 45% |
| Next tier | 9% | 35% |
| Remaining 90% | 90% | 20% |

This is a **hypothetical skew configuration**, not Zipf's law or real production data. Derive histograms/top-k safely from sanitized telemetry; never copy raw production tenant IDs into a lab environment.

### Distributions Must Be Measured at Multiple Levels

1. **Tenant:** request rate per tenant.
2. **Partition:** same tenant, but the current day and past days have different read densities.
3. **Clustering range:** users typically read the "latest 20 orders", rarely the entire history.
4. **Order ID:** an order currently undergoing payment processing may be read/refreshed repeatedly.
5. **Status:** `CREATED`/`PAID`/`CANCELLED` have different proportions.
6. **Data age:** new orders, old orders, orders near retention expiry, recently updated/deleted data.

### What Does Hotness Affect?

An overly hot partition key can overload the replica set owning it, even when total cluster QPS is modest. RF3 still places **only three replicas of that partition**; adding more nodes does not automatically spread a single hot partition across every node.

Reading a partition with millions of clustering rows can also cause read amplification, high SSTables/read, and tombstone scans. `setPageSize(20)` throttles the response, not turn a wide partition into a small one.

### Using Buckets or Shards?

If `(tenant_id, order_day)` grows too large, consider hourly buckets or deterministic sharding; however, listing queries may then require **fan-out + merge** across multiple partitions. The load model must account for the extra CQL statements and merge algorithm, rather than measuring only a single select on the old table.

## 7. Designing Representative Seed Data for Volume and Lifecycle

A benchmark with **10 rows and zero tombstones** on a freshly started node does not reflect a cluster retaining months of data.

Dimensions to plan:

| Data Dimension | Required Seed Pattern | Why |
| --- | --- | --- |
| Partition count | Sufficient tenants × buckets per distribution | Affects token distribution/caches |
| Rows/partition | Median, p95, p99, plus several hot partitions | Affects listing/range reads |
| Row size | Realistic small/medium/large payloads in bytes | Affects network, heap, compaction |
| Data age | Fresh and older data across multiple SSTables | Affects caches and read amplification |
| TTL | A subset of data with varying lifetimes | Generates expirations/tombstones |
| Delete/update | Business-realistic mutation rates | Alters SSTable density and GC pressure |
| Statuses | Multiple statuses with valid read/write transitions | Avoids meaningless single-status data |
| Hot/cold | Heavy reads on a few buckets, long tail on the rest | Measures cache behavior and replica imbalance |
| Compression/compaction | Policies matching the target environment | Governs disk space/write amplification |
| Multi-DC | Realistic data replication and routing when required | Validates per-DC latency and headroom |

### Estimating Storage Without Fabricating an Exact Number

For example, 2 million logical orders, each **written to two tables**, already yield around 4 million logical rows across both tables before accounting for TTLs, metadata, indexes, and tombstones. However, **never use `row count × payload bytes × RF` as an exact disk forecast**, because storage also includes:

- SSTable encoding, partition/clustering metadata, and compression.
- Indexes, Bloom filters, summaries, and memtables.
- Replication across DCs/racks.
- Compaction temporary disk overhead and write amplification.
- Tombstones, overwritten cells, and snapshots/backups.

Capacity planning must measure disk footprint after bulk load, after compaction stabilizes, and under ongoing writes/updates/TTLs. Remember to reserve **headroom for compaction and node recovery**—do not fill disks just to hit a target dataset size.

### Seeding Valid Identities and Read-After-Write Behavior

The generator should maintain a catalog of seeded `order_id` values so `READ_DETAIL` hits real data. If it generates a random UUID on every read, most queries simply return "not found", making the benchmark artificially easy and misleading.

A realistic 404 rate may exist, but it must be **intentionally modeled**—for instance, 2% detail lookup misses—not caused by broken key generation.

## 8. RF, CL, and DC: Each Workload Class Has Its Own Contract

With `NetworkTopologyStrategy` RF3 in `dc1`, a typical read/write behaves as follows:

| CL | Required Local Responses | Practical Meaning |
| --- | --- | --- |
| `LOCAL_ONE` | At least one local replica | Lower latency in some cases, but different freshness/guarantees |
| `LOCAL_QUORUM` | At least two of three local replicas | Commonly chosen to balance consistency and availability |
| `ALL` in one RF3 DC | All three replicas | A single failed replica can cause requests to fail CL |

The quorum formula is typically \(\lfloor RF/2\rfloor+1\); for RF3 that is 2. In multi-DC setups, `LOCAL_QUORUM` applies to the local DC, not the entire keyspace globally.

**Load tested at CL=ONE cannot substitute for load at CL=LOCAL_QUORUM.** Differences in tail latency, replica ACKs, and availability under failure can be substantial. Record CL, local DC, RF, and keyspace in all results.

### A "Read-After-Write Test" Also Needs a Contract

- Writing and reading the same key with the chosen CL—on which DC?
- Is there a time lag between the write and the read?
- Are there concurrent writers or clock skew?
- Is eventual visibility acceptable, or must the user immediately read the order they just created?
- Can two denormalized tables temporarily diverge after a partial failure?

If an `INSERT` on table A succeeds while table B times out, the business failure is **cross-table projection drift**, not necessarily a Cassandra replication failure. Add corresponding reconciliation checks rather than merely counting HTTP 200 responses.

## 9. Checking Mutation Semantics Before Enabling Retries

| Mutation | Risk on Retry | Workload Design Guidance |
| --- | --- | --- |
| Pure-read `SELECT` | Adds load, result may change if data is live | Bounded retries if idempotent |
| Upsert with same key and stable values | May overwrite concurrent writer if timestamp is newer | Use operation IDs and proper versioning/state transitions |
| `counter = counter + 1` | May double-count after a timeout | Do not auto-retry; track event IDs and reconcile |
| `list = list + [...]` | May append duplicates | Use item identity and an appropriate data model |
| `USING TTL` | Late retry can shift expiration time | Store absolute expiration if policy requires |
| `INSERT ... IF NOT EXISTS` | Retry may return `[applied]=false` even if the first attempt succeeded | Reconcile against operation ID and state |
| Dual-write to two tables | One table may succeed while the other fails | Track each write outcome and reconcile |

**Do not mark every statement `setIdempotent(true)` just to make the driver retry aggressively.** The driver does not understand money or inventory semantics. The workload generator must also reuse the same logical order ID when replaying an operation, rather than generating a fresh UUID and counting it as a success.

## 10. Offered Load, Achieved Throughput, and Concurrency

A test must report:

- **Offered load:** how many logical operations/s the generator intends to dispatch.
- **Admitted load:** how many operations actually pass the in-flight limiter.
- **Achieved throughput:** how many operations complete successfully per second.
- **Failures/unknown:** how many requests timed out, were rejected, failed, or have uncertain mutation outcomes.
- **Backlog/queue wait:** how many operations waited client-side before CQL dispatch.

If 1,000 ops/s are offered, but only 700 are admitted and 650 complete successfully, never report "650 ops/s, 0% errors" by **excluding the 300 rejected and 50 failed operations from the sample**.

### Little's Law: Clarifying the Relationship Between QPS and Latency

In steady state under the law's assumptions, average concurrency is approximately:

\[
L \approx \lambda W
\]

For example, at 1,000 ops/s offered and 80 ms average latency once stabilized, **around 80 operations** may be in-flight. If tail latency climbs to 500 ms or the server slows down, in-flight demand rises; this is not a hard ceiling.

**Do not** use this calculation to derive p99 or conclude that an 80-connection pool is sufficient. The driver uses multiplexing, requests involve multiple CQL calls, concurrent workloads exist, and variance matters; measure actual in-flight counts, queue depth, and deadlines.

### Open-Loop vs. Closed-Loop

| Model | What the Generator Does | Advantage | Interpretation Risk |
| --- | --- | --- | --- |
| **Closed-loop** | Each worker waits for completion before sending the next request | Simulates a fixed number of users with think time | When the server slows, offered load drops automatically, masking tail latency |
| **Open-loop** | Dispatches requests on a target schedule/rate independent of completion time | Measures ability to sustain offered QPS and overload | Must bound queues/in-flight and count shed requests |
| **Hybrid** | User/session flows + global rate/tenant quota | Models more realistic behavior | Must report both offered and completed to avoid ambiguous definitions |

In closed-loop mode, "100 users" does not mean "1000 QPS"; QPS depends on think time, requests per flow, and latency. In open-loop mode, when the server stalls, the dispatch schedule keeps advancing; you must **count due requests that could not be sent** to avoid hiding overload.

### Coordinated Omission

If a generator only records latency for requests that **were actually sent** and stops issuing new requests while the server stalls, percentiles can look artificially good. When evaluating overload, measure:

1. **End-to-end** latency starting from the time the logical operation was scheduled to fire.
2. Queueing/admission wait time.
3. Latency of driver/CQL requests actually dispatched.
4. Requests rejected or exceeding deadlines before dispatch.

Do not patch histograms by injecting synthetic "zeros" for missed requests. Choose a generator and metric definition aligned with your load model, document the calculation, and avoid claiming a p99 for a population that effectively dropped slow requests.

## 11. Designing Load Phases and Stop Thresholds

| Phase | Goal | Example in an Isolated Lab |
| --- | --- | --- |
| **Preflight** | Verify nodes/replicas/keyspace/CL, seed data, auth/TLS | Sample queries succeed, no abnormal repair/compaction before test |
| **Warm-up** | Stabilize JIT, driver pools, caches, memtables | Moderate load sufficient to observe initial transients |
| **Baseline** | Measure latency and errors at normal load | 30% of peak with the target workload mix |
| **Ramp** | Find where p99 begins degrading and saturation occurs | 50%, 70%, 90%, 100% of offered peak |
| **Steady-state peak** | Measure SLOs at expected peak | Sustain load until metrics stabilize |
| **Burst** | Evaluate bounded sudden spikes | Inject a short, approved high-load burst |
| **Soak** | Observe compaction, GC, tombstones, disk over time | Hold representative load long enough to see background effects |
| **Cool-down** | Observe backlog drain and return to baseline | Stop workload generation, inspect pending tasks |

Durations and percentages are **planning templates** that must be tuned to your workload and SLOs. Especially in Cassandra, a test lasting only a few minutes may not cycle through flushes, compactions, or TTLs, and thus cannot speak to long-term steady state.

### Stop Thresholds Must Be Agreed Before the Test

Example stop conditions:

- HTTP or CQL p99 breaches the contractual threshold continuously over a defined window.
- `Unavailable`/timeout errors exceed the test error budget.
- Free disk space drops below the **approved headroom** for compaction/streaming.
- Pending compactions/tasks or dropped messages grow continuously without recovering.
- A node enters an unexpected failure state outside the test scenario.
- Safety/correctness of dual writes, operation IDs, or authentication cannot be guaranteed.
- The generator hits CPU/GC saturation and can no longer emit the offered rate accurately.

Do not pick a universal disk/CPU percentage without knowing the compaction strategy, dataset, disks, and replica repair window. **An incomplete guardrail is still far better than defaulting to "push until the cluster dies".**

## 12. Metrics That Must Be Measured Together

| Layer | Metric | Used to Answer |
| --- | --- | --- |
| User/API | Logical success/error, HTTP p95/p99, deadlines | What experience do users see? |
| Load generator | Offered/admitted/completed/rejected, scheduling lag, CPU | Are we actually generating the intended load? |
| Java Driver | CQL latency, retries/attempts, in-flight, connection pool, local DC | Is the bottleneck in the driver or routing? |
| Query template | Separate `READ_LIST`/`READ_DETAIL`/`CREATE`/`UPDATE` latency/timeouts | Which query shape degrades first? |
| Cassandra node | Read/write latency, pending work, dropped messages | Are replicas or coordinators saturated? |
| Storage | SSTables/read, tombstones, compaction backlog, disk utilization | Is read/write amplification increasing? |
| JVM/OS | Heap/GC, CPU, network, disk latency, file descriptors | Is there an underlying resource bottleneck? |
| Consistency | RF/CL/DC, unavailable/timeouts, cross-table divergence | Are enough replicas responding with accurate data? |
| Correctness | Missing orders, duplicate logical IDs, status drift | Is the benchmark silently corrupting data? |

### Percentiles and Sample Counts

Never average per-node p99 values to produce a cluster-wide p99. When using histograms, merge **compatible histograms/samples** with matching labels, time windows, and sample counts; averaged percentiles are statistically invalid.

If a query group only has a few dozen samples per minute, its p99 will be very noisy. Report:

- Request count in the window.
- p50, p95, p99 (and p99.9 if sample count is sufficient).
- Timeout/rejection/error counts **alongside** percentiles.
- Percentiles by DC, CL, hot/cold cohort, and row-size class.

**Never filter out timeouts and report only the p99 of fast responses.** Timeouts must be accounted for in the SLO experience according to a published rule; success-only percentiles can serve as a secondary metric, never a replacement for error rates.

## 13. Choosing the Right Tool Instead of Letting the Tool Dictate the Workload

| Tool / Approach | When to Use | Limitations to Remember |
| --- | --- | --- |
| `cassandra-stress` | Exploring CQL/driver/cluster capacity for tool-supported workloads | Default workloads are usually **not** your business journeys |
| NoSQLBench or equivalent workload framework | Modeling multiple queries/parameters and workload phases | Must verify plugins, syntax, version, and key distributions |
| YCSB and standard benchmark workloads | Comparing repeatable read/write patterns | Standard workload distributions and semantics may differ from your app |
| Custom Java Driver 4.x generator | Need exact prepared CQL, CL, paging behavior, hot keys, order lifecycle | Must build instrumentation, load limits, rate scheduler, and safety guards |
| k6/Gatling/JMeter via HTTP API | Measuring auth, Spring Boot, service logic, and CQL end-to-end | Cannot isolate Cassandra cost without per-layer instrumentation |
| Sanitized synthetic traffic replay | Reproducing realistic rates/mixes/bursts | Must not copy PII/secrets; replay still depends on underlying data state |

If using `cassandra-stress`, CLI flags, custom user profiles, throttling, and metrics **vary by the version bundled with your distribution**; read the help output of the pinned version in your lab. Never copy a command from another version's docs and assume it measures the right workload.

### Use at Least Two Perspectives

**A — CQL-level test:** Java Driver or a tool sending prepared statements directly to Cassandra, isolating routing, RF/CL, disk, compaction, and query costs.

**B — API-level test:** going through the HTTP controller, auth, validation, caching, multiple CQL calls, serialization, and downstream calls to reveal true user SLOs.

Do not compare **1,000 API requests/s** with **1,000 CQL/s** as equivalent quantities. Record the number of CQL statements per API operation and total attempts.

## 14. Java Driver 4.x: Bounded Asynchronous Load Generator

The following example uses Java 17 and Java Driver 4.x to demonstrate **a single JVM generating load at a 60/20/15/5 ratio**, without blocking callbacks or unbounded concurrency. It includes:

- `ScheduledExecutorService` dispatching logical operations at a nominal rate.
- `Semaphore` bounding the number of in-flight operations.
- `PreparedStatement` matching the query shapes from section 5.
- `CompletionStage`/`thenCompose` chaining the two writes of one business operation **without calling `join()`**.
- A pre-seeded `OrderKey` list that can **repeat elements by weight** to simulate hot keys.
- Counters for offered, rejected, acknowledged, errors, and total duration.

**Important:** This code is a baseline skeleton only. It does **not** yet record p99 histograms, scheduling lag, per-attempt retries, outstanding partial writes, per-DC metrics, or correctness verification. Do not claim it is a production benchmark framework simply because it uses a `Semaphore`.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class BusinessWorkloadGenerator implements AutoCloseable {
    public record OrderKey(
        UUID orderId, String tenantId, LocalDate day,
        Instant createdAt) {}

    private enum Kind {
        READ_LIST, READ_DETAIL, CREATE_ORDER, UPDATE_STATUS
    }

    private final CqlSession session;
    private final List<OrderKey> weightedSeedKeys;
    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();
    private final Semaphore inFlight = new Semaphore(128);

    private final PreparedStatement readList;
    private final PreparedStatement readDetail;
    private final PreparedStatement insertById;
    private final PreparedStatement insertByDay;
    private final PreparedStatement statusById;
    private final PreparedStatement statusByDay;

    private final LongAdder offered = new LongAdder();
    private final LongAdder rejected = new LongAdder();
    private final LongAdder acknowledged = new LongAdder();
    private final LongAdder errors = new LongAdder();
    private final LongAdder totalDurationNanos = new LongAdder();
    private volatile ScheduledFuture<?> scheduled;

    public BusinessWorkloadGenerator(
            CqlSession session, List<OrderKey> weightedSeedKeys) {
        if (weightedSeedKeys == null || weightedSeedKeys.isEmpty()) {
            throw new IllegalArgumentException("Seed keys required");
        }
        this.session = session;
        this.weightedSeedKeys = List.copyOf(weightedSeedKeys);

        readList = session.prepare(
            "SELECT created_at, order_id, status, total_cents " +
            "FROM load_lab.orders_by_tenant_day " +
            "WHERE tenant_id=? AND order_day=? LIMIT 100");

        readDetail = session.prepare(
            "SELECT order_id, status, total_cents " +
            "FROM load_lab.orders_by_id WHERE order_id=?");

        insertById = session.prepare(
            "INSERT INTO load_lab.orders_by_id " +
            "(order_id, tenant_id, order_day, created_at, " +
            "status, total_cents) VALUES (?, ?, ?, ?, ?, ?)");

        insertByDay = session.prepare(
            "INSERT INTO load_lab.orders_by_tenant_day " +
            "(tenant_id, order_day, created_at, order_id, " +
            "status, total_cents) VALUES (?, ?, ?, ?, ?, ?)");

        statusById = session.prepare(
            "UPDATE load_lab.orders_by_id " +
            "SET status=? WHERE order_id=?");

        statusByDay = session.prepare(
            "UPDATE load_lab.orders_by_tenant_day " +
            "SET status=? WHERE tenant_id=? AND order_day=? " +
            "AND created_at=? AND order_id=?");
    }

    // Example: 200 nominal operations/s; do not use an extremely high RPS
    // with a single scheduler thread and assume scheduling is accurate.
    public void start(int targetRps) {
        if (targetRps < 1 || targetRps > 5_000) {
            throw new IllegalArgumentException("Rate outside lab range");
        }
        if (scheduled != null) {
            throw new IllegalStateException("Already started");
        }
        long periodNanos = TimeUnit.SECONDS.toNanos(1)
            / targetRps;
        scheduled = scheduler.scheduleAtFixedRate(
            this::dispatchOne, 0, periodNanos, TimeUnit.NANOSECONDS);
    }

    private void dispatchOne() {
        offered.increment();
        if (!inFlight.tryAcquire()) {
            rejected.increment();
            return;
        }

        long started = System.nanoTime();
        try {
            int draw = ThreadLocalRandom.current().nextInt(100);
            Kind kind = draw < 60 ? Kind.READ_LIST
                : draw < 80 ? Kind.READ_DETAIL
                : draw < 95 ? Kind.CREATE_ORDER
                : Kind.UPDATE_STATUS;

            OrderKey key = weightedSeedKeys.get(
                ThreadLocalRandom.current().nextInt(
                    weightedSeedKeys.size()));

            // Completion callback is O(1) only: no JDBC/HTTP/sleep.
            execute(kind, key).whenComplete((unused, error) -> {
                totalDurationNanos.add(
                    System.nanoTime() - started);
                if (error == null) {
                    acknowledged.increment();
                } else {
                    errors.increment();
                    // Classify timeout/partial-write separately in the service.
                    // Do not auto-retry mutations here.
                }
                inFlight.release();
            });
        } catch (RuntimeException failure) {
            errors.increment();
            totalDurationNanos.add(
                System.nanoTime() - started);
            inFlight.release();
        }
    }

    private CompletionStage<AsyncResultSet> execute(
            Kind kind, OrderKey seed) {
        switch (kind) {
            case READ_LIST: {
                BoundStatement stmt = readList.bind(
                        seed.tenantId(), seed.day())
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setPageSize(20)
                    .setIdempotent(true);
                return session.executeAsync(stmt)
                    .thenCompose(first -> {
                        // Fetch 1 additional page on ~40% of requests
                        // ONLY when more pages actually exist.
                        boolean next = ThreadLocalRandom.current()
                            .nextInt(10) < 4;
                        if (next && first.hasMorePages()) {
                            return first.fetchNextPage();
                        }
                        return CompletableFuture.completedFuture(first);
                    });
            }
            case READ_DETAIL: {
                BoundStatement stmt = readDetail.bind(seed.orderId())
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(true);
                return session.executeAsync(stmt);
            }
            case CREATE_ORDER: {
                // Generate the ID once for this logical operation.
                // Date bucket must follow the published business timezone.
                Instant now = Instant.now()
                    .truncatedTo(ChronoUnit.MILLIS);
                LocalDate businessDay = now.atZone(
                    ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();
                OrderKey fresh = new OrderKey(
                    UUID.randomUUID(), seed.tenantId(), businessDay, now);
                BoundStatement first = insertById.bind(
                        fresh.orderId(), fresh.tenantId(), fresh.day(),
                        fresh.createdAt(), "CREATED", 125_000L)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(false);
                BoundStatement second = insertByDay.bind(
                        fresh.tenantId(), fresh.day(), fresh.createdAt(),
                        fresh.orderId(), "CREATED", 125_000L)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(false);

                // These are two independent writes, not a transaction.
                return session.executeAsync(first)
                    .thenCompose(ignore -> session.executeAsync(second));
            }
            case UPDATE_STATUS: {
                BoundStatement first = statusById.bind(
                        "PAID", seed.orderId())
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(false);
                BoundStatement second = statusByDay.bind(
                        "PAID", seed.tenantId(), seed.day(),
                        seed.createdAt(), seed.orderId())
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(false);
                return session.executeAsync(first)
                    .thenCompose(ignore -> session.executeAsync(second));
            }
            default:
                throw new IllegalArgumentException("Unknown workload");
        }
    }

    // Snapshot for debugging only; real measurement needs per-kind histograms.
    public String snapshot() {
        return "offered=" + offered.sum()
            + ", rejected=" + rejected.sum()
            + ", acknowledged=" + acknowledged.sum()
            + ", errors=" + errors.sum()
            + ", totalDurationNanos=" + totalDurationNanos.sum()
            + ", inFlight=" + (128 - inFlight.availablePermits());
    }

    @Override
    public void close() {
        ScheduledFuture<?> job = scheduled;
        if (job != null) {
            job.cancel(false);
        }
        scheduler.shutdown();
        // CqlSession is owned by the caller and must be closed outside the runner.
        // In-flight CompletionStages may still complete after this call.
    }
}
```

### Using It in a Controlled Test

```java
// session: a CqlSession configured with the proper local DC/auth/TLS.
// seedKeys: list of OrderKey instances that actually exist and were seeded.
BusinessWorkloadGenerator generator =
    new BusinessWorkloadGenerator(session, seedKeys);
generator.start(200);  // Hypothetical rate for lab use.

// A test controller manages phase duration and guardrails,
// reads metrics, and closes the generator when the phase finishes.
// Never call Thread.sleep() inside a driver callback.
```

The code above is an **orchestration snippet**: `session` and `seedKeys` are provided by the test bootstrap. It does not close the session, stop itself after a duration, or inject faults. A real harness requires a test controller that advances phases, stops on guardrails, drains in-flight work, records histograms, and verifies data correctness.

### Important Limitations of the Skeleton

1. **Scheduling:** `scheduleAtFixedRate` does not guarantee an exact 200 requests/s when the JVM pauses or the scheduler lags; catch-up bursts may occur. Measure **intended send time, actual dispatch time, and scheduling lag** rather than dividing `offered` by wall-clock time.
2. **Skew:** `weightedSeedKeys` allows repeating elements to increase selection probability, but the real distribution must come from telemetry. Never assume a uniform sampler is "production-like".
3. **Read-after-write:** `CREATE_ORDER` creates a new ID and computes the day bucket in the illustrative business timezone `Asia/Ho_Chi_Minh`, without adding it back to the seed pool. To model "create → view detail", use a **stateful workflow** or a queue of successfully created / UNKNOWN IDs needing verification. Align on the actual environment's business timezone instead of defaulting to the JVM timezone.
4. **Partial writes:** If `insertById` succeeds and `insertByDay` fails, the failed future **does not roll back the first table**. Track each stage and reconcile by `order_id`; this snippet has no ledger yet.
5. **Update realism:** `UPDATE_STATUS` picks a seed key and sets `PAID` without modeling a state machine or payment contention. Add preconditions, transition distributions, and concurrent writers matching real workloads.
6. **Latency:** `totalDurationNanos` only accumulates total time across all admitted logical operations; it provides neither p99 nor per-kind CQL latency. In practice, use histograms/Micrometer with sample counts, labels, and deadlines.
7. **Retries:** `setIdempotent(false)` informs the driver's retry policy that the mutation is not declared idempotent; HTTP/jobs/gateways or external code may still replay the logical operation.
8. **Backpressure:** `Semaphore` caps in-flight operations at 128, but it is not a request queue; calls that fail to acquire a permit must be counted as **shed/rejected offered load**.
9. **Pacing:** Firing 5,000 scheduled callbacks/s from a single JVM may not be appropriate; for high load, distribute generators, synchronize phases, and prevent the load generator itself from saturating.
10. **Resources:** In benchmarks, do not log every row/UUID, do not retain millions of futures in memory, do not call `join()` inside callbacks, and monitor generator CPU/GC to avoid becoming client-bound.

### Do Not Count "SUCCESS" Just Because a Stage Did Not Throw an Exception

For `READ_DETAIL`, a stage succeeding with zero rows returned could be a **valid 404 or a seed distribution bug**. For `READ_LIST`, a page can be empty even while more pages remain. For dual writes, the second stage succeeding does not prove external systems like a payment gateway completed. **Classify success by the business contract, not merely by transport ACKs.**

## 15. Richer Instrumentation for the Generator: Per-Operation and Per-Query

The generator above should be instrumented across two event streams:

```text
BUSINESS_OP_STARTED
  op=CREATE_ORDER
  logicalOperationId=...
  scheduledAt=...

CQL_ATTEMPT
  queryTemplate=insertOrdersById
  cl=LOCAL_QUORUM
  attempt=1
  latency=...

CQL_ATTEMPT
  queryTemplate=insertOrdersByTenantDay
  cl=LOCAL_QUORUM
  attempt=1
  latency=...

BUSINESS_OP_FINISHED
  status=CONFIRMED / UNKNOWN / PARTIAL / CONFLICT
  endToEndDuration=...
```

**Do not log full UUIDs, customer IDs, PII, or secrets on every request.** Event identifiers needed for reconciliation can be stored in a **protected, TTL-bounded test store**, while metrics should aggregate by query template, CL, DC, tenant cohort (hot/warm/cold), and status.

### Measuring the Cost of Paged Reads

If `READ_LIST` fetches an average of 1.4 pages/operation, measure in practice:

- Pages per `READ_LIST`.
- Requested page size and actual rows returned per page.
- Payload bytes/page, tombstone warnings, and per-page retries/failures.
- Wait time after the first page (UI think time) if the API fetches subsequent pages on user scroll/action.
- Cases where the user opens the list once and never paginates further.

Do not let a Java request automatically fetch **the entire ResultSet** and label the result "one page". With Java Driver 4.x, synchronous `ResultSet` iteration can auto-fetch subsequent pages; `AsyncResultSet.currentPage()` cleanly isolates the current page.

### Measuring Read/Write Mix Across Time Windows

A daily average 60/20/15/5 ratio can conceal sharp bursts:

```text
08:00–09:00: heavy READ_LIST, READ_DETAIL
12:00–12:05: order campaign → CREATE_ORDER burst
20:00–20:30: payment confirmation workers → UPDATE_STATUS surge
00:00–02:00: retention jobs, compaction, backups
```

This schedule is **illustrative**. Obtain burst ratios and durations from real telemetry and model distinct phases, rather than smoothing all request types uniformly and erasing business peaks.

## 16. Measuring Data Correctness: High Throughput Without Losing Orders

An order-creation test must retain **expected state** for verification. Counting "completed" `INSERT`s is insufficient when writes hit two tables or undergo retries.

| Invariant | Verification Method | Common Failure Found |
| --- | --- | --- |
| Single unique logical `order_id` | Compare event/operation ledger with `orders_by_id` | Duplicates caused by generating a new ID on retry |
| Both tables reflect the same order | Read both by known key | Partial write, write B timed out |
| Status never regresses illegally | Compare transition version/event log | Retried older status overwrote newer state |
| `READ_DETAIL` matches tenant/ID | Verify against seeded key and tenant authorization | CQL bind/mapping bug or stale data |
| `READ_LIST` stays within partition | Verify `tenant_id`, `order_day`, and clustering order | Wrong key selection or buggy fan-out merger |
| No excessive misses | Measure 404 rate against designed distribution | Generator picks nonexistent random UUIDs |
| Expiration follows policy | Compare `expires_at` with TTL/retention | TTL replay drifts expiration |
| Post-fault recovery | Reconcile `UNKNOWN`/`PARTIAL` entries | Test stops while corrupted/incomplete data remains |

### Reconciliation Work Should Not Run on the Generator's Hot Path

If the generator executes three extra verification `SELECT`s after every `INSERT`, the workload **no longer matches the original matrix**. There are two valid approaches, which must be stated explicitly:

1. **Validation workload is part of the product:** include verification reads in the query mix ratios.
2. **Independent test harness audit:** sample or run after the load phase, keeping reconciliation queries separate from business throughput.

When a timeout occurs, the mutation outcome may be **UNKNOWN**; never mark the order "failed" and generate a new ID. Keep the ID immutable in the ledger, re-read at an appropriate CL, and classify as `CONFIRMED`, `PARTIAL`, `CONFLICT`, or `UNKNOWN` according to agreed rules.

### Should `COUNT(*)` Be Used to Verify All Orders?

Do not run full-table `SELECT COUNT(*)` continuously under load to "count successful writes". Counting can scan numerous partitions/SSTables and distort the workload. Use **a manifest/ledger of IDs and key-based reads** for sampled or post-test reconciliation; if an exact count of finalized data is needed, design a separate export/snapshot job.

## 17. Fault Testing Must Complement, Not Replace, the Load Model

Once a baseline is established on a healthy cluster, you can introduce **a single controlled fault** during a representative load phase to test what real users care about: whether requests still meet SLOs, data remains accurate, and the system recovers without triggering a retry storm.

Scenario matrix:

| Fault Tested in Lab/Staging | Workload to Maintain | Expectations / What to Observe |
| --- | --- | --- |
| One replica/node Down in an RF3 DC | Mix of READ_LIST, READ_DETAIL, writes | `LOCAL_QUORUM` can still succeed with two healthy local replicas; p99 may rise |
| Coordinator killed after receiving request | CREATE_ORDER + READ_DETAIL | Write outcome may be UNKNOWN; application must reconcile |
| Elevated network latency to one node | Reads and writes at target CL | Tail latency, coordinator routing, timeouts/retries |
| WAN link disruption | Multi-DC reads/writes per contract | Local `LOCAL_QUORUM` vs. cross-DC convergence |
| Compaction backlog / disk I/O pressure | Paged reads and writes | SSTables/read, pending tasks, write latency, disk headroom |
| One load generator JVM overloaded | Keep server fault-free | Distinguish client artifacts from Cassandra failures |
| Controlled Cassandra node restart | Known peak workload | Connection recovery, in-flight failures, post-restart latency |
| Sudden spike on a hot tenant/partition | Dedicated hot-key profile | Replica imbalance, per-cohort p99, throttling |

**This is a scenario plan, not instructions for breaking production infrastructure.** Node, network, or disk faults may only be injected in approved environments with explicit control and rollback/fail-safe procedures. Never trigger `disk full`, network partitions, multi-replica kills, or forced compaction on a cluster serving real users.

### Separating Failure Modes

- **Graceful drain/shutdown** differs from **process kill**; write paths, ACKs, and recovery differ.
- **Node Down** differs from **network partition**: a node may still process mutations while unreachable to clients.
- **Replica failure** differs from **coordinator failure**: client routing and outcome knowledge differ.
- **One DC losing WAN** differs from **losing local quorum**.
- **Slow server** differs from **blocked driver callbacks** in the Java application.

Running a single "stop node" command and calling it "we tested all distributed failures" is an overbroad conclusion.

## 18. Runbook: Testing One Replica Down Under Business Load

**Assumptions for an approved fault-testing lab/staging cluster only:**

- One datacenter `dc1` with RF3 for the measured tables.
- Three replicas actually placed across proper racks/failure domains per lab design.
- Java Driver configured with the correct local DC and using `LOCAL_QUORUM`.
- Representative seed data present, generator driving a stable business workload mix.
- Authorization to stop/start a node and an approved **rollback plan**.

### Before Fault Injection

1. Capture topology/baseline from nodes: `nodetool status`, tables, RF/CL/DC/rack.
2. Verify authentication/TLS, application health, retry policy, and idempotency.
3. Confirm an appropriate backup/snapshot/restore policy; **do not** assume fault tests cannot lose data.
4. Set maximum offered RPS, duration, in-flight limits, and disk headroom.
5. Arm guardrails/alerts: p99, timeouts, unavailable errors, pending tasks, dropped messages, and correctness.
6. Ensure **a healthy quorum-capable replica set** before testing; if the baseline is already degraded, **do not inject additional faults**.
7. Synchronize clocks and phase markers across clients, generators, Cassandra nodes, and metrics.

**Read-only** observation commands on a lab node:

```bash
nodetool status
nodetool describecluster
nodetool tpstats
nodetool compactionstats
nodetool tablestats load_lab.orders_by_id
nodetool tablestats load_lab.orders_by_tenant_day
nodetool tablehistograms load_lab orders_by_tenant_day
```

`nodetool` reports node-local status/metrics; it does not directly measure HTTP latency or the Java generator's task queue. Combine it with driver/app metrics and OS/disk telemetry.

### During the Fault Phase

1. Record timestamp `T_fault_start` and **inject only one approved fault** on a specific node/network path.
2. Keep the workload mix and offered rate identical to baseline if guardrails allow; avoid changing two variables simultaneously.
3. Measure p95/p99 separately for `READ_LIST`/`READ_DETAIL`/`CREATE_ORDER`/`UPDATE_STATUS`, not just an overall average.
4. Track additional driver attempts/retries, read/write timeouts, and application rejections.
5. Watch the specific hot partitions owned by the failed replica, not only aggregate cluster traffic.
6. Log all `UNKNOWN`/`PARTIAL` writes for reconciliation; never blindly retry counters/lists/LWTs.
7. **Halt fault injection/load** if any guardrail is breached or out-of-scope errors appear.

With RF3/`LOCAL_QUORUM`, if one replica is Down while **the other two local replicas remain healthy and reachable**, many requests can still achieve quorum. This is **not a guarantee** that throughput/latency will stay unchanged or that every partition is healthy; client routing, coordinators, and load on the remaining two replicas still determine the outcome.

### After Node Recovery

1. Restore the node/network per the operational runbook without introducing further disruptive actions.
2. Re-verify node state and CQL request reachability.
3. Monitor streaming/hints/repair debt, compaction, and backlogs according to your Cassandra version/topology.
4. Continue observing until latency, error rates, disk usage, and pending tasks **return within acceptable thresholds**, not merely when `nodetool status` shows `UN`.
5. Reconcile logical orders across both tables, all `UNKNOWN`/`PARTIAL` operations, and status anomalies.
6. Compare pre-fault baseline, during-fault, and post-recovery phases under the **same workload distribution**.
7. Archive reports, PII-scrubbed artifacts, and go/no-go decisions for subsequent tests.

Do not use `nodetool repair` or `major compaction` as an unplanned "reset button". Repair and compaction consume substantial resources, must align with cluster state, and cannot distinguish valid from invalid business writes.

## 19. Separating Java Application Bugs from Cassandra Failures

A test showing "Cassandra is slow" may actually be client-constrained:

| Symptom | Primary Hypothesis | Verification |
| --- | --- | --- |
| Generator CPU 100%, Cassandra CPU low | Client cannot generate load fast enough / serialization overhead | Check scheduling lag, payload bytes, client GC |
| Driver I/O threads show `join/get/sleep` | Blocking callback | Thread dump, refactor to `thenCompose`/bounded executor |
| Local semaphore rejections spike | Client hit in-flight limit | Compare offered vs. admitted, not just completed |
| HTTP p99 degrades, CQL p99 stays healthy | Service auth/JSON/other dependency | Per-stage tracing, Spring Boot CPU/GC |
| CQL `READ_LIST` p99 spikes, `READ_DETAIL` stays flat | Wide/hot partition, SSTables/tombstones | Cohort hot/cold split, selective `tablehistograms`/tracing |
| CQL `CREATE` p99 rises during compaction backlog | Disk/write amplification | `compactionstats`, disk I/O, memtable/flush stats |
| `Unavailable` spikes when a node goes Down | Insufficient RF/CL/quorum or routing issue | Verify replica placement, DC, CL |
| Timeouts rise but writes appear afterward | Insufficient/delayed ACKs, UNKNOWN outcome | Reconcile; do not treat timeout as rollback |
| One DC reads staler data than another | WAN/convergence, CL, and routing | Measure per-DC, maintain consistent contracts |

### Do Not "Fix a Benchmark" by Weakening Consistency

If `LOCAL_QUORUM` is the API's contract, lowering it to `ONE` to boost throughput may yield an **interesting comparison**, but it is **not an equivalent optimization for correctness**. In the report, label it as a **different CL scenario** and explicitly document the semantic change; never blend both results into one baseline curve.

### Do Not Let the Load Generator Trigger a Retry Storm

Limited driver retries can be valid for idempotent `SELECT`s, but:

- Actual requests reaching Cassandra can exceed offered logical operations.
- Post-timeout attempts can worsen an already overloaded cluster.
- Speculative executions also consume resources and are only safe for proven-idempotent statements.
- Counter increments, list appends, TTL replays, and LWT timeouts require separate policies.

A throughput chart without retry counts **can hide the true cost** of serving users.

## 20. Comparable and Reproducible Benchmark Report Template

A standard report should begin with the **test conditions**:

```yaml
# Report metadata template only, NOT a tool configuration file.
scenario_id: business-mix-peak-rf3-lq
environment: isolated-staging
workload_version: orders-v3
data_model_version: orders-two-tables-v2
generator_instances: 2
offered_logical_ops_per_second: 1000
business_mix:
  READ_LIST: 60
  READ_DETAIL: 20
  CREATE_ORDER: 15
  UPDATE_STATUS: 5
read_list_mean_pages_target: 1.4
partition_distribution: sampled-hot-warm-cold
replication: "NetworkTopologyStrategy dc1=3"
consistency: LOCAL_QUORUM
local_dc: dc1
retry_policy: "record actual configured policy/version"
fault: "none; baseline"
measurement_window: "steady-state phase, exact timestamps"
```

When faults are tested, include `fault_type`, `fault_target`, `T_fault_start`, `T_fault_end`, recovery duration, and triggered guardrails. Never copy host IPs, secrets, or sensitive tenant IDs into widely distributed reports.

### Example Results Table — Hypothetical Numbers, Not Measurements

| Metric | Example Baseline | Example One Replica Down | Example Post-Recovery |
| --- | ---: | ---: | ---: |
| Offered logical ops/s | 1,000 | 1,000 | 1,000 |
| Admitted logical ops/s | 995 | 940 | 992 |
| Completed successful ops/s | 991 | 900 | 987 |
| Rejected ops/s | 5 | 60 | 8 |
| Errors/unknown ops/s | 4 | 40 | 5 |
| READ_LIST p99 (ms) | 85 | 180 | 95 |
| CREATE_ORDER p99 (ms) | 120 | 300 | 135 |
| Driver attempts/logical op | 1.02 | 1.17 | 1.03 |
| Correctness violations | 0 verified | Needs UNKNOWN reconciliation | 0 after reconciliation |

**All numbers in this table are illustrative.** The "correctness violations = 0" entry is valid only after a verification pass with sufficient coverage; if un-reconciled `UNKNOWN` entries remain, record **"undetermined"**—never fill in 0 by default.

### An Acceptable Report Conclusion

> "Under workload mix X, seed dataset Y, RF3/LOCAL_QUORUM in DC1, when fault Z occurred, READ_LIST p99 breached the SLO for N minutes; achieved throughput dropped while errors and retries rose. After recovery, compaction backlog and p99 returned within thresholds after M minutes. Uncertain write outcomes were reconciled by operation ID with coverage K."

Variables X/Y/Z/N/M/K must be replaced with **measured values from recorded sources**; never extrapolate from a few samples to claim that all other nodes, DCs, or query paths behave identically.

## 21. Common Mistakes When Designing Read/Write Workloads

### 21.1. Counting HTTP Requests While Forgetting CQL Fan-Out

One `POST /orders` writes to two tables, and one `GET /orders` may fetch two pages. One API operation does not equal one CQL execution.

### 21.2. Using Only Uniform Random Keys

Production has hot tenants; uniform random keys spread load evenly and make benchmarks look better than reality. Preserve hot/warm/cold tiers and partition sizes.

### 21.3. Using Only a Single Hot Key

The test can turn into a contention experiment on just a few replicas rather than representing the cluster. Hotness needs a defined share alongside a cold long tail.

### 21.4. Every `READ_DETAIL` Misses

The generator creates fresh UUIDs instead of picking seeded orders; empty queries return abnormally fast. Enforce deliberate hit/miss ratios.

### 21.5. Every Row Is Small, Fresh, and Tombstone-Free

Testing an overly clean dataset produces cache and SSTable behavior unlike production systems carrying TTLs, deletes, and compactions. Seed data must reflect realistic age and write/update lifecycles.

### 21.6. Closed-Loop Drops Offered Load When the Server Slows

When the server stalls, user threads block and request rate drops automatically; p99 then fails to reflect unserved demand. Measure offered/scheduled rates and queue wait, not just completed ops.

### 21.7. Unbounded Concurrency to Find "Max QPS"

When too many requests queue up, both the client and Cassandra can hit OOM or retry storms. Use controlled rate ramps and bounded in-flight concurrency with guardrails.

### 21.8. Treating Timeouts as Failed Writes and Retrying Blindly

A mutation may have been applied even though the client never received an ACK. With dual writes, a timeout between the two tables creates a `PARTIAL` state; reconcile by logical ID.

### 21.9. Reporting Only Average Latency

`READ_LIST` p99 can be many times higher than `READ_DETAIL`; an overall average hides user tail experience. Break down by query template and cohort.

### 21.10. Comparing Benchmarks with Different RF/CL/Datasets as Equivalent

RF1, `ONE`, and 10 GB of clean data are not the same problem as RF3, `LOCAL_QUORUM`, and terabytes of data with TTLs and tombstones. Normalize test conditions or explicitly state differences.

### 21.11. Running Fault Tests Against an Already Unhealthy Baseline

If the cluster already has pending compaction, low disk headroom, or a Down replica, injecting another fault can cause unexpected quorum loss. Stop and fix the baseline first.

### 21.12. Treating `UN` as Full Recovery

A node showing Up may still carry repair debt, pending compactions, unconverged data, or unstabilized Java connection pools. Measure the recovery window and data correctness too.

## 22. Case Exercises and Guided Answers

### Scenario A — Calculating CQL Rate from API Rate

A system handles 1,000 business operations/s: 60% READ_LIST (1.4 pages/op), 20% READ_DETAIL (1 CQL), 15% CREATE (2 writes), 5% UPDATE (2 writes). Excluding retries, estimate the CQL rate.

**Answer:** \(600×1.4+200+150×2+50×2=1440\) CQL/s, comprising roughly 1,040 read CQL/s and 400 write CQL/s. This is an **average** estimate and does not apply uniformly across every peak window.

### Scenario B — 50,000 QPS on an ID Lookup Table

A team proves `orders_by_id` reaches 50,000 QPS when every read hits cache. Is the tenant/day listing frontend safe?

**Answer:** No conclusion can be drawn. `READ_LIST` accesses different partitions and clustering keys, has different payload sizes, requires paging, and can hit multiple SSTables/tombstones. That query shape must be benchmarked directly.

### Scenario C — RF3 with One Replica Down

In an RF3 DC, one node goes Down. How many local replicas does `LOCAL_QUORUM` still require? Can unchanged p99 be guaranteed?

**Answer:** Two local replicas are required. Many partitions can still be served if two local replicas remain healthy; **unchanged p99 cannot be guaranteed**, because the remaining nodes absorb shifted load and routing.

### Scenario D — 0.5 ms Detail Reads Mostly Returning Empty

The generator calls `UUID.randomUUID()` for every read. Read latency looks fantastic.

**Answer:** Non-representative workload. Seed valid keys, control the hit/miss distribution, and verify correctness.

### Scenario E — Order Creation Succeeds on One Table Only

`INSERT orders_by_id` returns OK, while `INSERT orders_by_tenant_day` times out. The Java service logs "FAILED" and generates a different order ID on HTTP retry.

**Answer:** The second table's outcome is uncertain while the first table already succeeded. Keep `order_id`/operation ID immutable, mark `PARTIAL/UNKNOWN`, reconcile, and complete the projection instead of duplicating the order.

### Scenario F — A 5-Minute Peak

The 60/20/15/5 mix is measured over a full day; during a flash sale, `CREATE_ORDER` surges for 5 minutes and payment workers follow afterward.

**Answer:** Design separate **phases** and burst profiles grounded in telemetry; never average a 24-hour workload flat and claim peak was tested.

### Scenario G — Offered 1,000, Completed 650

The generator rejects 300 due to the semaphore, 50 fail, and 650 succeed. Is reporting "650 ops/s with 0% error rate" accurate?

**Answer:** No. Separate offered, admitted, acknowledged, errors, and rejected counts and report the denominator. In this example, 35% of offered operations did not complete successfully.

### Scenario H — Better Benchmark After Lowering CL

After switching from `LOCAL_QUORUM` to `ONE`, latency drops by 40%. Can the new chart be used to claim "we optimized the same workload"?

**Answer:** That is a **different consistency scenario**. It can be compared for trade-off analysis, but it is not semantically equivalent. Keep RF/CL/DC explicit in the report.

### Scenario I — Generator CPU Hits 100%

Driver queues remain small, Cassandra node CPU is only 25%, and offered is 2,000 while measured throughput is ~900 ops/s.

**Answer:** Measure generator scheduling lag, GC, CPU, and queues. The bottleneck is likely client-side; distribute generators or optimize serialization before blaming Cassandra.

### Scenario J — Increasing TTL to Reduce Disk Pressure

The team finds tombstones slowing down `READ_LIST` and wants to increase TTL from 1 day to 90 days without checking retention policies, then re-run the benchmark.

**Answer:** Never alter data semantics just to make a benchmark look better. Align TTL, compaction, and partition design with business requirements, measure with realistic data age and cleanup, and then decide.

### Scenario K — Node Returns to `UN` After Fault

After a restart, `nodetool status` reports `UN`, so the team stops measuring and declares the cluster recovered.

**Answer:** Also verify that latency/errors return to baseline, pending repairs/compactions drain, driver connections recover, data converges, and all `UNKNOWN` operations are reconciled.

### Scenario L — Averaging Group p99s

`READ_DETAIL` has p99 = 20 ms; `READ_LIST` has p99 = 200 ms. The team averages them to 110 ms and calls it the application p99.

**Answer:** Statistically invalid. The percentile of a combined dataset is not the mean of subgroup percentiles. Aggregate proper histograms/samples and report each query type separately.

## 23. Checklist Before Concluding a Load Test Represents the Business

**Data and Queries**

- [ ] Real list of business journeys and query templates; not just a generic `SELECT`/`INSERT`.
- [ ] Measured CQL executions per business operation, including paged reads and dual writes.
- [ ] Queries match partition/clustering keys; `ALLOW FILTERING` is not enabled to mask bad queries.
- [ ] Seed data covers sufficient partitions, rows/partition, payload bytes, hot/cold skew, and data age.
- [ ] Realistic read hit/miss ratios and create/read/update/delete state machine transitions.
- [ ] TTL/delete/tombstone/compaction patterns included whenever the real system uses them.
- [ ] Immutable operation IDs and a reconciliation path for multi-table writes.

**Load Generation Design**

- [ ] Report offered, admitted, acknowledged, rejected, errors, and actual driver attempts.
- [ ] Distinguish open-loop, closed-loop, think time, scheduling lag, and coordinated omission.
- [ ] Bounded concurrency/rate/backpressure; never buffer unbounded futures/rows in memory.
- [ ] Reuse `CqlSession`, prepared statements, and non-blocking async callbacks.
- [ ] Preserve query ratios across normal, peak, burst, and soak phases.
- [ ] Load generator is not the bottleneck; generator CPU/GC/queue metrics are captured.
- [ ] Request deadlines, retry budgets, speculative executions, and idempotency verified.

**Cassandra and Distributed System**

- [ ] Document Cassandra version/distribution, DC/rack topology, RF, CL, and driver/JDK versions.
- [ ] Local DC and client routing verified; CL is not lowered to hide timeouts.
- [ ] Monitor read/write latency, p95/p99, dropped messages, pending tasks, SSTables/read, disk/GC.
- [ ] Adequate disk/memory/CPU headroom reserved for compaction and node recovery.
- [ ] Do not extrapolate RF3/multi-DC failure behavior from RF1 tests.
- [ ] Stable baseline established before fault injection with a clear blast-radius limit.
- [ ] Never inject multi-replica/network/disk faults on production or unapproved clusters.

**SLOs, Correctness, and Recovery**

- [ ] p99 measured per query template/cohort with sample counts and time windows published.
- [ ] Timeouts/rejections/`UNKNOWN` outcomes are not excluded from SLO reporting.
- [ ] Verified against missing orders, duplicate logical IDs, and projection drift.
- [ ] Explicit fault/recovery timestamps and load-stop guardrails recorded.
- [ ] Recovery validated via throughput, latency, backlog, and correctness—not just `UN`.
- [ ] Report separates assumptions, measured results, and environment limitations.
- [ ] Scenario is reproducible from workload version, seed profile, RF/CL, timings, and configs.

**Remember:** A Cassandra load test is valuable only when it reflects **the actual CQL statements emitted by the business**, with realistic partition distributions, read/write mixes, page fetches, dual writes, RF/CL, and data that has undergone updates, TTLs, and compactions. Measure **offered load and rejected requests** alongside throughput, p99, and correctness; only then layer in controlled fault testing. The goal is not chasing a flattering QPS number, but knowing **how far the system preserves SLOs and data correctness under load and distributed failures**.
