# Verifying with Execution Metrics Rather Than Assuming an Index Suffices

> **Chapter:** Indexes  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — exploring Apache Cassandra's distributed architecture and wide-column model, query-driven table design, partition keys, read/write consistency levels, and operational tasks like compaction, repair, troubleshooting, and Java connectivity.

Successfully creating an index and running a `SELECT` are necessary conditions, yet **not sufficient** to prove a query will remain fast and stable in production. In Cassandra, an indexed query can still touch many nodes, read many partitions or SSTables, overload coordinators, and degrade at the latency tail. Conversely, in some workloads, filtering within a small partition is already fast enough without an index.

This lesson shows how to **hypothesize, measure, analyze, and decide** from real workloads rather than simply assuming "an index makes queries fast." Examples use **Apache Cassandra 5.0 Storage-Attached Indexing (SAI)**; on Cassandra 4.x or distributions lacking SAI support, verify capabilities and syntax before practicing. Do not equate SAI with legacy secondary indexes (2i): they have different storage structures and limitations.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish a **valid query**, an **index-backed query**, and a **query meeting performance targets**.
2. Design controlled benchmarks comparing unindexed filtering, SAI queries, and query-driven table designs.
3. Measure `p50/p95/p99` latency, throughput, errors, I/O pressure, write overhead, disk footprint, and stability under load.
4. Use `TRACING ON`, `nodetool tablehistograms`, `tablestats`, `proxyhistograms`, and application metrics/telemetry to pinpoint cost sources.
5. Decide based on **selectivity, partition count, data distribution, sorting requirements, SLOs, and operational impact**.

## 2. Three different questions: exists, used, or worth using?

| Question | How to verify | What remains unproven |
|---|---|---|
| **Is the index declared?** | Inspect schema via `DESCRIBE TABLE` and index build state | Index is ready across every replica; query takes the optimal path |
| **Does the query actually use the index?** | Check predicate support, tracing, and query execution stats | Latency or resource usage beats the baseline |
| **Does the index fit the workload?** | Benchmark with realistic data/distributions, target load, measuring reads **and writes** | Long-term stability if data or topology evolves |

Do not confuse two kinds of "counts":

- **Selectivity:** fraction of rows matching the filter. For instance, if `OPEN` accounts for 90%, filtering by status returns huge volumes; if `OPEN` is 1%, it returns far less. Selectivity is only one variable and does not predict latency alone.
- **Cardinality:** number of distinct values in a column. `status` has few values; `email` has many. With SAI, value distribution **across nodes and partitions** impacts performance; "higher cardinality is always better" is false.

In Cassandra, the **partition key** determines how data is grouped and placed, replication strategy determines partition replicas, and **consistency level (CL)** determines how many replicas must respond. An index does not eliminate network, disk, coordinator, CL, or pagination costs.

### 2.1. Why can SAI still be expensive?

SAI stores lookup structures attached to SSTables. When filtering on an indexed column, the engine narrows candidate rows/partitions and then fetches base data. Real cost depends on matching counts, scatter across nodes, and base-data read amplification:

- With a **full partition key**, the query already routes to the replica set of one specific partition; scanning a small partition can rival an index lookup.
- **Without a partition key**, an index query may coordinate across multiple token ranges/nodes. Even a tiny result set does not guarantee only one node participates in searching.
- When a predicate is common (e.g., most records have `OPEN`), the index returns a large candidate set, still paying for base-row reads, network transfer, and pagination.
- If data or indexes are actively building, flushing, compacting, or repairing, measurements diverge from steady state.
- Adding indexes adds write-path maintenance, disk footprint, and build/recovery duration; measure indirect effects on write latency too.

SAI can combine multiple predicates across SAI-indexed columns, yet improvements do not scale linearly with index count. Exact query capabilities, type limits, and syntax must be verified against your Cassandra version.

## 3. A verifiable problem: finding OPEN tickets in a tenant/month

Suppose a customer support application stores multi-tenant tickets. A screen needs tickets with `status = 'OPEN'` in the current month for a tenant. We compare **three storage/query options** over identical logical data:

| Option | Model | Experimental question |
|---|---|---|
| A — Base table, no index | `tickets_plain` partitioned by tenant and month; filters `status` | Is intra-partition scanning actually too expensive? |
| B — Base table with SAI | `tickets_sai` with the same primary key; indexes `status` | How much cost does SAI save, and under which distributions? |
| C — Query-driven table | `tickets_by_status` puts `status` into the partition key | Does keyed lookup outweigh maintaining an extra table? |

This is a **comparative experiment**. When measuring, load identical data into A, B, and C, holding RF/CL and filter semantics constant. Option C also supports chronological sorting via clustering keys, which is a **separate functional capability**; never lump "50 newest tickets" and "any 50 tickets" into the same latency comparison column.

### 3.1. Creating the lab keyspace

The examples below require **Cassandra 5.0 with SAI support**, `cqlsh`, and schema creation permissions. Use an isolated test cluster. `dc1` and RF = 3 apply only if your cluster actually has a `dc1` datacenter with at least three nodes; adjust according to `nodetool status` before running.

~~~sql
CREATE KEYSPACE IF NOT EXISTS index_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;
~~~

Before benchmarking, verify an existing keyspace actually carries the expected config: `IF NOT EXISTS` **does not update** an older schema. RF should match your lab topology and stay identical across options.

### 3.2. A — Table without an index

~~~sql
CREATE TABLE IF NOT EXISTS index_lab.tickets_plain (
    tenant_id uuid,
    month_bucket int,
    ticket_id uuid,
    status text,
    updated_at timestamp,
    subject text,
    PRIMARY KEY ((tenant_id, month_bucket), ticket_id)
);
~~~

The partition key `tenant_id + month_bucket` avoids stuffing a tenant's entire history into one partition. Still, an extra-large tenant can create an overly wide monthly partition; measure size distributions and evaluate smaller buckets if needed.

Without an index on `status`, filtering on it typically requires `ALLOW FILTERING`:

~~~sql
SELECT ticket_id, status, updated_at, subject
FROM index_lab.tickets_plain
WHERE tenant_id = 5bd928ad-a5aa-4eb9-8c12-bfda73571a70
  AND month_bucket = 202611
  AND status = 'OPEN'
ALLOW FILTERING;
~~~

**Use this only as a lab baseline**, on bounded, monitored datasets. `ALLOW FILTERING` permits filtering that can read far more rows than it returns; it is not a production data-modeling fix.

### 3.3. B — Same primary key, adding SAI

~~~sql
CREATE TABLE IF NOT EXISTS index_lab.tickets_sai (
    tenant_id uuid,
    month_bucket int,
    ticket_id uuid,
    status text,
    updated_at timestamp,
    subject text,
    PRIMARY KEY ((tenant_id, month_bucket), ticket_id)
);

CREATE INDEX IF NOT EXISTS tickets_status_sai_idx
ON index_lab.tickets_sai (status)
USING 'sai';
~~~

This is SAI syntax in Apache Cassandra 5.0. Run benchmarks only after all relevant replicas **finish building the index** and readiness is verified via your version's tools/metrics. Cassandra can build indexes asynchronously over existing data; seeing `CREATE INDEX` succeed does not prove readiness.

~~~sql
SELECT ticket_id, status, updated_at, subject
FROM index_lab.tickets_sai
WHERE tenant_id = 5bd928ad-a5aa-4eb9-8c12-bfda73571a70
  AND month_bucket = 202611
  AND status = 'OPEN';
~~~

Here the application supplies the full partition key plus an SAI-indexed predicate. Measure whether SAI delivers meaningful gains over scanning the same partition, especially as the `OPEN` ratio varies.

### 3.4. C — Query-driven table

~~~sql
CREATE TABLE IF NOT EXISTS index_lab.tickets_by_status (
    tenant_id uuid,
    status text,
    month_bucket int,
    updated_at timestamp,
    ticket_id uuid,
    subject text,
    PRIMARY KEY ((tenant_id, status, month_bucket), updated_at, ticket_id)
) WITH CLUSTERING ORDER BY (updated_at DESC, ticket_id ASC);
~~~

Now retrieving all `OPEN` tickets for a tenant in a month is served directly by the **partition key**, with no secondary index:

~~~sql
SELECT ticket_id, status, updated_at, subject
FROM index_lab.tickets_by_status
WHERE tenant_id = 5bd928ad-a5aa-4eb9-8c12-bfda73571a70
  AND status = 'OPEN'
  AND month_bucket = 202611;
~~~

If the functional requirement is the **50 most recently updated tickets**, table C has matching clustering keys:

~~~sql
SELECT ticket_id, status, updated_at, subject
FROM index_lab.tickets_by_status
WHERE tenant_id = 5bd928ad-a5aa-4eb9-8c12-bfda73571a70
  AND status = 'OPEN'
  AND month_bucket = 202611
LIMIT 50;
~~~

Options A and B **lack** this `updated_at DESC` ordering guarantee. Therefore, to fairly compare an ordered feature, redesign the baseline to meet the same semantics or explicitly document that A/B cannot satisfy ordering. Never fetch 50 arbitrary rows from SAI and call them "the 50 newest rows."

**Trade-off:** to maintain C when a ticket transitions `OPEN → CLOSED` or when `updated_at` changes, the application must delete from the old key and insert at the new key. With A/B, updating `status` does not force the application to move rows across status partitions, though B still pays SAI maintenance costs. Model C therefore requires consistent update workflows, retries/idempotency, and stale-record handling; app-level dual-writes do not automatically get linearizable multi-table transactions.

### 3.5. Writing consistent data across all three options

Example single ticket to verify schemas and query results. Keys and values across all three `INSERT` statements must represent **the exact same logical ticket**:

~~~sql
INSERT INTO index_lab.tickets_plain
    (tenant_id, month_bucket, ticket_id, status, updated_at, subject)
VALUES (
    5bd928ad-a5aa-4eb9-8c12-bfda73571a70,
    202611,
    f8ba776b-eb1a-4b94-8d2d-6d5460dbad1d,
    'OPEN',
    '2026-11-21T08:15:00Z',
    'Verify access limit'
);

INSERT INTO index_lab.tickets_sai
    (tenant_id, month_bucket, ticket_id, status, updated_at, subject)
VALUES (
    5bd928ad-a5aa-4eb9-8c12-bfda73571a70,
    202611,
    f8ba776b-eb1a-4b94-8d2d-6d5460dbad1d,
    'OPEN',
    '2026-11-21T08:15:00Z',
    'Verify access limit'
);

INSERT INTO index_lab.tickets_by_status
    (tenant_id, status, month_bucket, updated_at, ticket_id, subject)
VALUES (
    5bd928ad-a5aa-4eb9-8c12-bfda73571a70,
    'OPEN',
    202611,
    '2026-11-21T08:15:00Z',
    f8ba776b-eb1a-4b94-8d2d-6d5460dbad1d,
    'Verify access limit'
);
~~~

One row verifies syntax only—it **does not make a meaningful benchmark**. Generate/load production-representative data: tens to hundreds of thousands of partitions, large tenant/month buckets, many small tenants, skewed status ratios, updated/deleted records, and data flushed/compacted naturally. Record the loader tool, seed, total dataset size, index build state, Cassandra version, and topology in the experiment log.

## 4. Designing benchmarks to answer the right question

### 4.1. Hypothesis and success criteria

Example initial hypothesis:

> For tenant/months with many tickets and a low `OPEN` ratio, Option B will reduce p95/p99 versus unindexed filtering; when the `OPEN` ratio is high, gains may be small or negative. Option C generally excels for tenant/status/month queries—especially when time ordering is required—but must account for extra table maintenance and status-transition writes.

This is a **hypothesis to measure**, not a proven fact. Before running, define product SLOs—for instance, read p99 under **100 ms** at **300 requests/sec** under a specific load profile, along with error thresholds and acceptable write-latency impact. These SLO figures are **experimental design examples**, not empirical Cassandra benchmarks.

To conclude soundly, compare both **user-facing metrics** and system costs. An option that is 10 ms faster at p50 yet causes timeouts or spikes read/write p99 under concurrency still fails the SLO.

### 4.2. Data and workload matrix

Never benchmark one query repeatedly against a single key. Minimum suggested matrix:

| Test axis | Test levels | Purpose |
|---|---|---|
| Rows per tenant/month | 100; 10,000; 100,000 | Test cost across large partitions |
| `OPEN` percentage | 1%; 25%; 90% | Contrast high- vs. low-selectivity filtering |
| Tenant distribution | Many small tenants plus a few massive tenants | Test skew and hot partitions |
| Concurrent clients | 1; 10; 50 (tuned to environment) | Observe tail latency and fan-out |
| Workload mix | Read-only; mixed read/write; `status` updates; deletes | Measure maintenance costs of indexes and table C |
| Cache state | Cold/warm **explicitly recorded**, never mixed arbitrarily | Avoid misattributing cache hits |
| Result size | 20; 100; full results via paging | Measure `LIMIT` and network effects |

**Hold constant** during comparison: node count, rack/DC layout, replication factor, CL, driver, prepared statements, page size, logical dataset, load rate, hardware, codec/compaction strategy, node repair state, and query profile. Run multiple independent trials after warm-up during steady background state; alternate A/B/C run order across trials to reduce cache or compaction bias.

Never run repair, major compaction, or add/remove nodes mid-benchmark unless that is the variable under study. If heavy background compaction or GC spikes occur, tag that measurement window for separate analysis.

### 4.3. Verify data and semantic correctness before timing

For queries fetching **all** matching tickets, verify:

1. All three tables hold the exact same logical ticket set for the target tenant and month, with zero missing or duplicate `ticket_id`s.
2. Standardize projected columns, filters, CL, and pagination; consume every page to count actual returned rows.
3. Read equivalent result batches. Never let A/B return arbitrary rows while C returns the 50 newest rows and compare p99 as if they were identical workloads.
4. For read-only measurements, finish syncing table C / building index B before timing. For write-to-read visibility tests, explicitly include **propagation lag** in scope and check CL consistency.
5. Verify zero failed queries, timeouts, or skipped final pages. A "fast" run missing rows is a functional failure.

In Java applications, driver prepared statements and paging mirror real production behavior. When benchmarking full result retrieval, stop the timer only after **consuming the entire `ResultSet`**, because `execute()` may return before fetching all pages.

## 5. Collecting metrics directly from Cassandra

### 5.1. Tracing: understanding a query's execution path

In `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
TRACING ON
~~~

Run **each SELECT from section 3 one by one**, then disable tracing:

~~~text
TRACING OFF
~~~

`LOCAL_QUORUM` fits when RF and DC are configured appropriately; if a lab has only one replica, choose a valid CL for that environment and keep it identical across A/B/C.

For each trace, record:

| Trace signal | Question to answer |
|---|---|
| Total duration recorded by Cassandra | Which query spends the most cluster-side time? |
| Coordinator/replica activity | How many nodes participate? Is there distributed network chatter? |
| Index lookup, partition/SSTable read, filtering stages (version-dependent) | Is time spent in index lookups or base-data reads? |
| I/O waits, messaging, retries (if shown) | Are there disk, network, or coordinator bottlenecks? |
| Returned rows and paging timing | Is cost proportional to processed data volume? |

Trace event names vary by version and query type, so read the **actual event sequence** rather than grepping for one fixed string to prove index usage.

**Tracing limits:** tracing adds overhead, persists trace rows, and fits **targeted sample queries**—never enable it broadly across full load tests. Server-side trace duration does not equal client end-to-end latency, which also includes connection pooling, serialization/deserialization, page fetches, and network hops.

### 5.2. Histograms and table stats

Commands on a Cassandra node:

~~~bash
nodetool tablehistograms index_lab tickets_plain
nodetool tablehistograms index_lab tickets_sai
nodetool tablehistograms index_lab tickets_by_status
~~~

Depending on version, `tablehistograms` reports local read/write latency percentiles, SSTables read per query, partition sizes, and cell counts. Cross-reference with client metrics; these histograms are typically **cumulative per table/node** and affected by other workloads unless the lab is isolated.

~~~bash
nodetool tablestats index_lab.tickets_plain
nodetool tablestats index_lab.tickets_sai
nodetool tablestats index_lab.tickets_by_status
nodetool proxyhistograms
~~~

`tablestats` tracks per-table disk space, read/write counts, SSTables, and storage state. `proxyhistograms` reflects coordinator latency across **all requests**, not a single `SELECT`, so isolate load and interpret per measurement window. To measure SAI disk/JMX costs, check the SAI metrics supported in your **exact running version**; never deduce exact index size solely from total table size stats.

These are **read-only inspection commands** that do not modify data. In production, rely on existing observability pipelines rather than introducing extra load.

### 5.3. Metrics to capture in the same time window

| Category | Useful metrics | Why needed |
|---|---|---|
| Application experience | p50, p95, p99, and max **end-to-end latency**; timeout/error rates | Determines SLO compliance |
| Traffic | Successful/failed QPS; active clients; in-flight requests; pages/rows returned | Ensures equal work comparisons |
| Coordinator | Coordinator latency, pending/blocked tasks, internode network traffic | Detects fan-out and service bottlenecks |
| Replica/table | Local read latency, SSTables per read, partition size, disk reads, heap/GC | Pinpoints root causes of differences |
| Write cost | p95/p99 write latency, write throughput, compaction backlog, index builds | Prevents optimizing reads at the expense of writes |
| Resources | CPU, memory/GC, disk IOPS/bandwidth, network, disk footprint | Assesses scalability and operational cost |

Tag every run with variant (A/B/C), dataset, `OPEN` ratio, concurrency, CL, and version. One "before/after" metrics screenshot cannot separate index effects from shifts in load, caching, and compaction.

## 6. Measuring from Java: observing true user wait time

Example with **DataStax/Apache Cassandra Java Driver 4.x** on a connected `CqlSession`. Preparing the statement for Option B:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement prepared = session.prepare(
    "SELECT ticket_id, status, updated_at, subject " +
    "FROM index_lab.tickets_sai " +
    "WHERE tenant_id = ? AND month_bucket = ? AND status = ?");

UUID tenant = UUID.fromString("5bd928ad-a5aa-4eb9-8c12-bfda73571a70");
BoundStatement statement = prepared.bind(tenant, 202611, "OPEN")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(500);

long started = System.nanoTime();
ResultSet rows = session.execute(statement);
int returnedRows = 0;
for (Row row : rows) {
    returnedRows++;
    // Read required column contents as in real workloads; avoid printing every row.
    row.getUuid("ticket_id");
}
long elapsedNs = System.nanoTime() - started;
double latencyMs = elapsedNs / 1_000_000.0;
~~~

Measure across **many iterations and keys**, reusing the prepared statement and session; record `latencyMs`, `returnedRows`, errors/timeouts, and dataset tags to build distributions. Never draw performance conclusions from a single `System.nanoTime()` call. In serious benchmarks, feed measurements into histograms supporting concurrency and realistic mixed read/write ratios.

If the product workload reads only the first page, measure **first-page latency** with realistic paging; if users scroll to the end, measure the full page sequence. Those two timings are not interchangeable.

## 7. Experimental results table template

Record actual numbers from your system; **never fill in example numbers as if they were real benchmark results**.

| Variant | Tenant/month | % OPEN | QPS | p50 (ms) | p95 (ms) | p99 (ms) | Timeout % | Rows returned | Notes |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| A — filter, no index | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _trace, SSTables, CPU_ |
| B — SAI | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _index build, fan-out_ |
| C — query-driven table | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _dual-write cost_ |

Include a separate **write workload** table under the same load (read:write ratio, status transition pattern, write p95/p99, errors, disk footprint) and save sample traces. If Option C adds tables, total cost must cover **all tables/writes** maintained per ticket—not just lookup table C's size.

For a reviewer to verify results, the report should state:

- **Parameters:** Cassandra/Java driver versions, node count/CPU/RAM/disk, RF, CL, compaction strategy, schema/index options.
- **Data:** total rows/partitions, per-tenant distribution, `OPEN` ratio, data age, TTL/tombstones if any, data seed.
- **Load:** QPS, concurrency, client pool, read/write mix, page size, run order, warm-up, sample duration.
- **Evidence:** percentile/error tables, node/table metrics, representative traces, and row-count/key reconciliation results.
- **Decision:** which options meet SLOs, write/storage trade-offs, and triggers for re-benchmarking.

## 8. Interpreting results and choosing a design

### 8.1. Possible conclusions (must be confirmed with numbers)

**Case 1 — small partitions, most rows match the filter.** A can be as fast as or faster than B because scanning a small partition is cheap and the index eliminates few rows. Keeping an index here may simply add write/disk cost. Do not extrapolate this to large partitions or other workloads.

**Case 2 — large partitions, few rows match the filter.** B can reduce work substantially compared to A. If p95/p99 meets SLOs and index maintenance costs are acceptable, B fits well—especially when applications filter across varied attributes.

**Case 3 — frequent query asking for "newest tickets by tenant and status."** C delivers direct partition-key routing and clustering order. When read speed is critical and the app accepts multi-table synchronization, C is usually a strong candidate for serious benchmarking.

**Case 4 — queries lacking a partition key with results scattered cluster-wide.** Even with an index, network fan-out, coordinator load, and tail latency can dominate. Revisit query requirements, add a meaningful business partition key, or design a dedicated table instead of merely adding indexes.

Never decide by p50 alone. Watch **p99 at target load, errors/timeouts, and resilience as data grows**. A benchmark with a few hundred rows or one node does not represent a multi-replica production cluster with real networking and compaction.

### 8.2. Common mistakes and fixes

| Mistake | Why it misleads | Fix |
|---|---|---|
| "CREATE INDEX succeeded so it's optimized" | Does not prove build finished, query uses it, or SLOs pass | Check build status, tracing, and benchmarks |
| Comparing A on large data vs. B on small data | Different processing volumes | Load and reconcile identical datasets |
| Benchmarking only `LIMIT 10` | Masks multi-page cost or misleads on sorting | Test all result sizes and real semantics |
| Timing only inside `cqlsh` | Mixes rendering, network, coordinator, and client overhead | Measure driver end-to-end; use tracing to explain |
| Benchmarking while building indexes or repairing | Shifting background load skews metrics | Use a steady window; log background tasks |
| Querying one hot key repeatedly | Caching/partition skew fakes great numbers | Vary tenants and partition sizes |
| Using `ALLOW FILTERING` long-term | May scan huge volumes for few returned rows | Use only as controlled baseline; prefer SAI or query tables |
| Measuring reads while ignoring writes | Extra indexes and tables cost writes and disk | Benchmark mixed workloads and status updates |
| Comparing `ONE` against `QUORUM` | Different replica responses skew latency | Hold CL fixed and document consistency |
| Looking at p50 and ignoring p99 | Users still hit tail latency and timeouts | Set SLOs on percentiles, errors, and target load |

## 9. Decision workflow before accepting an index

~~~mermaid
flowchart TD
    A["Define real queries and SLOs"] --> B["Inspect partition key, CL, row counts, distribution"]
    B --> C{"Does query already use a fitting partition key?"}
    C -->|Yes| D["Benchmark unindexed PK read path"]
    C -->|No| E["Evaluate SAI and query-driven table"]
    D --> F["Create SAI variant in lab"]
    E --> F
    F --> G["Reconcile results, await index build, warm up"]
    G --> H["Measure read/write, p95/p99, errors, node metrics"]
    H --> I{"Meets SLOs at acceptable cost?"}
    I -->|Yes| J["Record metrics, pick option, set monitoring alerts"]
    I -->|No| K["Adjust keys/table, index, paging, or query contract"]
    K --> G
~~~

**Acceptance criteria** should include:

1. **Correctness:** results match expectations across partitions, pages, and updates; never trade missing rows for lower latency.
2. **SLO compliance:** p95/p99 and error rates meet targets at projected traffic with headroom for data growth.
3. **Acceptable cost:** CPU, I/O, network, write latency, compaction/index builds, and disk footprint stay within budget.
4. **Operability:** observable index health, documented build/rebuild/repair handling, and version-safe schema rollout/rollback.
5. **Scalability:** when tenants grow or status ratios shift, re-measure on updated data matrices instead of trusting stale benchmarks forever.

Once an index is deployed, maintain workload dashboards tracking p95/p99, timeouts, read/write throughput, compaction backlog, and index size. Whenever schema, RF, CL, drivers, or query shapes change, **re-run** relevant benchmarks.

## 10. Practice exercises

**Exercise 1 — Why does the same index diverge dramatically?** Two tenants have the same monthly ticket count. Tenant A has 1% `OPEN`; tenant B has 90% `OPEN`. Predict which variables shift between querying A and B, define at least three metrics to verify your prediction, and explain why one ratio alone is inconclusive.

**Exercise 2 — Auditing benchmark fairness.** A benchmark reports SAI fetched 20 rows in 4 ms while a query-driven table fetched the 50 newest tickets in 7 ms. Can you conclude the index is faster? Identify at least two non-equivalent factors (`LIMIT`/ordering semantics, returned volume, CL, cache, or concurrency) and redesign the experiment.

**Exercise 3 — Reading traces.** Capture traces for the same `tenant_id`/`month_bucket` across varying status ratios, comparing client latency, local read latency, SSTables per read, and participating replicas. If the index shows low trace duration yet high client p99, propose driver, network, and paging causes.

**Exercise 4 — Finalizing a rollout choice.** Given an SLO of p99 ≤ 100 ms at 300 QPS (hypothetical target), build an A/B/C results table and choose an option covering read latency, write latency, disk footprint, and status-transition update cost. Wherever measurements are missing, write "insufficient evidence" instead of inventing numbers.

### Lab submission checklist

- [ ] Three schemas, identical logical data, and enough records to produce meaningful differences.
- [ ] Cassandra version recorded; SAI used only where supported by the environment.
- [ ] Queries A/B/C use identical predicates and reconciled results.
- [ ] Matrix covering status distributions, partition sizes, and concurrency.
- [ ] Recorded p50/p95/p99, errors, QPS, row counts, CL, and mixed read/write workloads.
- [ ] At least one sample trace per variant plus corresponding `nodetool`/JMX metrics.
- [ ] Notes on index/table maintenance cost and an evidence-backed SLO conclusion.

## References

1. Apache Cassandra — [Working with Storage-Attached Indexing (SAI)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-working-with.html): `CREATE INDEX ... USING 'sai'` syntax and querying.
2. Apache Cassandra — [SAI FAQ](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-faq.html): impact of cardinality, partitions, and query scope.
3. Apache Cassandra — [When to use a secondary index](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-when-to-use.html): when to choose an index vs. alternative data models.
4. Apache Cassandra — [Use Nodetool](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html): `tablehistograms`, `proxyhistograms`, and latency investigation.
5. Apache Cassandra — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): table metrics, latency, histograms, and JMX.
