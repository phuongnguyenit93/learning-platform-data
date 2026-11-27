# Selecting Critical Queries by Latency, Frequency, and Resource Footprint in Apache Cassandra

> **Chapter:** Query Tuning  
> **Scope:** Selecting the right CQL queries to prioritize for optimization on an Apache Cassandra cluster using measurements from Java applications, Cassandra, and the operating system. Focuses on *latency*, *frequency*, and *resource footprint* per **query family**, combining business SLOs, replication/consistency, partition keys, tombstones, SSTables, tracing, and a before–after measurement runbook. Examples use Cassandra 4.1/5.0 and Java Driver 4.x; parameters and metrics must be verified against the running version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Build a **query family catalog** by business operation, CQL pattern, keyspace/table, and consistency level, rather than lumping all `SELECT` statements into a single group.
2. Distinguish **average latency, p95/p99, timeout rate, QPS frequency, request residence time, and CPU/I/O/memory/network cost**.
3. Select critical queries using a **SLO × frequency × resource cost × business impact** matrix, including infrequent queries that create cluster bottlenecks.
4. Use metrics from **Java Driver 4.x**, Cassandra `ClientRequest`/`Table`, `nodetool`, tracing, and sampling to gather evidence rather than guessing from a single number.
5. Recognize Cassandra query patterns prone to high cost: missing partition keys, `ALLOW FILTERING`, wide partitions, excessive tombstones, overlapping SSTables, large pages, index fan-out, and mismatched table models.
6. Write a runbook to select top queries, formulate improvement hypotheses, benchmark safely, and verify no regression in **data correctness, consistency, latency, and throughput**.
7. Practice with CQL/Java to collect quantitative evidence on a sample workload with well-defined query families.

A defining characteristic of **wide-column Cassandra**: data is modeled around query paths; the partition key controls distribution and replica access, while clustering columns control ordering within a partition. A seemingly simple CQL statement may read a small partition, scan many SSTables/tombstones, or fan out across many nodes. Therefore, **selecting the right workload to tune** is just as important as editing the CQL statement itself.

## 2. What Does a "Critical" Query Mean?

The query with the highest latency is not always the first one to optimize. A critical query is one where **improvement delivers significant value to users, cluster resources, or operational risk**.

Compare four illustrative scenarios:

| Query family | Frequency | Latency p95 | Target p95 | Characteristics | Priority question |
|---|---:|---:|---:|---|---|
| `order.getById` | 800 QPS | 12 ms | 40 ms | Reads a single small partition/key | High frequency but meets SLO; how much I/O is it consuming? |
| `order.listRecent` | 90 QPS | 240 ms | 150 ms | Reads multiple pages/rows | Both breaches SLO and may consume substantial resources |
| `order.searchStatus` | 4 QPS | 2,000 ms | 600 ms | Filtering / large range scan | Low QPS, yet each request can impose heavy load |
| `audit.exportNightly` | 0.05 QPS | 5,000 ms | 10,000 ms | Background job with its own window | Slow but within SLO; does it overlap with peak hours? |

These numbers are **hypothetical**, not a Cassandra benchmark. The conclusion might be: `order.listRecent` requires top priority due to direct user-experience impact; `order.searchStatus` needs early review because each scan is expensive despite low QPS; `order.getById` can wait if the cluster still has ample headroom; `audit.exportNightly` can be scheduled/rate-limited rather than urgently tuned.

### 2.1. Three Mandatory Axes

~~~text
                   SELECTING CRITICAL QUERY FAMILIES
                                |
            +-------------------+--------------------+
            |                   |                    |
         LATENCY             FREQUENCY           RESOURCE COST
       p50/p95/p99           QPS, burst          CPU / disk / memory
       timeout, SLO          peak window         rows/tombstones read
            |                   |                bytes / fan-out
            +-------------------+--------------------+
                                |
                   BUSINESS CRITICALITY / RISK
                   error budget, SLA, customers
                                |
                        TOP CANDIDATES
                                |
                     TRACE + VERIFY + TUNE
~~~

**Do not combine the three axes with a blind formula.** A payment query may require investigation even at very low QPS; conversely, a slow audit job that is rate-limited and runs overnight may not need immediate fixes. Use a prioritization order that is explainable and backed by measurement sources.

### 2.2. The Goal Is *Selection*, Not "Fixing Everything"

The deliverables of a query selection cycle should include:

1. A catalog of query families that actually generate traffic.
2. A prioritized list of the top 3–10 queries with measurement sources, time windows, SLOs, and estimated impact.
3. Cost hypotheses for each query and **how to verify them**.
4. A tuning/rollback experiment plan, owner, and success criteria.
5. Items **not selected**, along with reasons (already meets SLO, small dataset, negligible frequency, or excessive change risk).

Cassandra does not maintain an out-of-the-box "top slow queries" list for every statement: Cassandra exposes metrics per node/table/request type, whereas statistics **per CQL template** usually require instrumentation in the application, gateway, or bounded logging mechanisms.

## 3. Query Family: The Right Unit of Comparison

A query family groups executions that share the **same business intent and data access path**, while preserving distinctions that affect resource usage.

Consider two executions:

~~~sql
SELECT status, total
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, total
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-b'
  AND order_id = 22222222-2222-2222-2222-222222222222;
~~~

They can be tagged under **one query family** `order.getById` because they share the same statement/template, partition key structure, and shape. However, if `tenant-a` has a very large hot partition while `tenant-b` does not, you need an additional breakdown dimension such as **partition size tier, tenant tier, or token range** instead of letting averages hide tail latency.

### 3.1. Recommended Label Structure

| Metadata field | Example | Reason |
|---|---|---|
| `service` | `checkout-api` | Identifies owner and business criticality |
| `operation` / `query_family` | `order.listRecent` | Bounded-cardinality grouping |
| `cql_template_id` | `ord_recent_v2` | Detects shape changes across deployments |
| `keyspace.table` | `shop.orders_by_tenant_day` | Correlates with Cassandra table metrics |
| `access_pattern` | `single_partition_range` | Distinguishes point lookup, range, fan-out |
| `consistency_level` | `LOCAL_QUORUM` | Affects replica response count and latency |
| `datacenter` | `dc1` | Compares topology performance |
| `result_mode` | `first_page` / `all_pages` | Separates first-page timing from full consumption |
| `outcome` | `success` / `timeout` / `failure` | Avoids measuring only successful requests |

**Do not use raw CQL containing literals, `tenant_id`, `order_id`, email addresses, or bind values as Prometheus labels**: this causes cardinality explosion, risks exposing PII, and incurs high metric storage cost. For detailed traces, sensitive data must be masked or stored in accordance with security policies.

### 3.2. Do Not Group Different Workloads Just Because They Share a Table

~~~text
Table: orders_by_tenant_day
   |
   +-- order.getByPrimaryKey  (reads exactly one row)
   +-- order.listRecent       (slices 50 rows within one partition)
   +-- order.listAllDays      (multiple partitions, multiple pages)
   +-- order.deleteExpired    (many tombstones)

Same table, yet latency, QPS, rows scanned, fan-out, and SLOs differ.
~~~

A high `Table.ReadLatency` metric only tells you **that table has slow local reads**, not which query family is responsible. Accurate prioritization requires joining **application-side data (by query family)** with **server-side data (by node/table/replica)** and selective traces.

## 4. Axis One — Latency and User Experience

### 4.1. Measure p50, p95, and p99, Not Just Average

- **p50**: half of requests finish within this bound; represents typical experience.
- **p95/p99**: sensitive to the tail; usually aligned with latency SLOs for APIs.
- **Mean/average**: useful for certain aggregate load calculations, but can mask extreme slow requests.
- **Timeouts/Unavailables/Failures**: must be measured separately; timed-out queries must not be excluded when evaluating user experience.
- **Time to first page** and **time to all pages**: are two distinct quantities under Cassandra paging.

Example with the same p50 = 8 ms:

~~~text
Family A: p50=8ms, p95=18ms, p99=30ms
Family B: p50=8ms, p95=220ms, p99=900ms

=> Identical medians, yet Family B has severe tail latency.
   Check replicas, partition-size outliers, paging, GC,
   compaction, tombstones, and retries instead of looking only at average.
~~~

### 4.2. Every Latency Measurement Has a Boundary

| Measurement source | Scope | Includes / excludes |
|---|---|---|
| API/business operation | From when the app receives the request until it returns the response | May include auth, business logic, multiple queries, cache, serialization |
| Query family in Java service | From before `session.execute` until the measurement condition is met | Includes driver, network, coordinator, retries; depends on measuring first page vs all pages |
| Driver session `cql-requests` | Total CQL request time at the session level | Includes retries; by default aggregates all query families on the session |
| Driver node `cql-messages` | CQL messages sent to a single node | One client request may generate multiple messages due to retries/speculation |
| Cassandra `ClientRequest.Read.Latency` | Coordinator request latency by request type | Aggregates same-type requests on the node; not per CQL template |
| Cassandra `Table.ReadLatency` | Local read latency of a table on a node | Does not represent full Java request latency |
| CQL tracing | Events of a sampled request | Helps pinpoint expensive steps; limited by sampling, overhead, and coverage |

**Do not directly subtract server p99 from API p99 to infer network latency**: percentiles of different distributions **cannot be subtracted**, and the sampled requests or replicas may also differ. Correlate matching traces and timestamps when breaking down latency.

### 4.3. SLOs and Error Budgets Matter More Than the "Slowest Query"

Example:

~~~text
order.getById:       p95  12 ms / SLO  40 ms -> compliant
order.listRecent:    p95 240 ms / SLO 150 ms -> breached
order.searchStatus:  p95 2.0 s  / SLO 0.6 s -> breached
audit.exportNightly: p95 5.0 s  / SLO 10 s  -> compliant
~~~

The ratio `observed_latency / SLO` is a screening signal, **not a substitute for the fraction of requests breaching the threshold**. If an SLO specifies "99.9% of requests under 200 ms", measure **the percentage of requests under 200 ms**, rather than inferring solely from p95. When timeouts occur, `success p95` may look healthy while the user error budget is already exhausted.

## 5. Axis Two — Frequency, Bursts, and Fan-Out

### 5.1. Average QPS Does Not Describe Peak Hours

Collect at minimum:

- `requests_per_second` by query family in 1–5 minute windows.
- `peak QPS` during peak hours and batch/cron windows.
- Request counts by tenant tier/region/DC if **low-cardinality** tagging is available.
- Retries, speculative executions, and multi-node fan-out.
- Frequency shifts tied to deployments or feature flags.

Example:

| Family | Average QPS | Peak QPS | Characteristics |
|---|---:|---:|---|
| `order.getById` | 800 | 2,000 | Hot read path all day |
| `order.listRecent` | 90 | 400 | Spikes when history page is opened |
| `order.searchStatus` | 4 | 100 | Bursts during filtering/reconciliation batches |
| `audit.exportNightly` | 0.05 | 20 | Concentrated inside the job window |

Comparing by average QPS alone makes it easy to overlook `order.searchStatus`, even though it can drive steep disk/CPU spikes during bursts.

### 5.2. Logical Requests vs. Physical Requests

~~~text
                 1 API request
                      |
               1 query family
                      |
           Java Driver execute()
                      |
        1 coordinator attempt
         /                \
      Success        timeout / retry
                         |
                 coordinator attempt #2
                         |
                    replica reads
                      |
                  multiple SSTables
~~~

**Logical QPS** is how often the business layer invokes a family; **messages/attempts sent to nodes** can be higher due to retries/speculation, paging, or one request issuing multiple statements. Raising driver retries to mask latency can increase cluster load even when user traffic stays flat.

Estimating fan-out must follow the mechanics of each query type:

- A `LOCAL_QUORUM` read requires responses according to RF/DC; a coordinator may contact multiple replicas, involving digest/data responses.
- Queries spanning multiple partition keys (`IN` on the partition key, if used) may touch multiple token ranges.
- Pagination can trigger multiple CQL fetches when the client consumes the full result set.
- Index/filtering queries may scan extensive data or scatter across many nodes, depending on index type and predicates.

**Do not multiply QPS by RF mechanically and call it disk reads.** Replication, digests, speculative retries, caches, and coordinator/replica differences mean actual cost must be measured via tracing and metrics.

### 5.3. A Supporting Metric: Equivalent Concurrency

By the intuition of Little's Law, in a **stable system**:

\[
L \approx \lambda W
\]

where `L` is the number of requests **currently in the system**, `λ` is request throughput per second, and `W` is average residence time per request (seconds).

For example, if `order.listRecent` runs at 90 QPS with a mean latency of 100 ms, then `L ≈ 90 × 0.1 = 9` equivalent concurrent requests. This is useful for gauging **in-flight load/queueing**, but it is **not 9 CPU-seconds per second** and does not directly measure Cassandra disk reads.

Similarly, 800 QPS × 6 ms mean ≈ 4.8 concurrent requests. High concurrency in a family can consume connections or request slots, yet you still need to measure **actual resource cost** before drawing conclusions about CPU or disk.

## 6. Axis Three — Per-Execution Resource Cost and Total Consumption

Low latency does not automatically mean cheap. A query returning in 10 ms on an underutilized cluster can still consume heavy I/O and become a bottleneck at 10× traffic. Conversely, a request waiting on the network or a downstream service may show high latency while consuming **little** Cassandra CPU.

### 6.1. Defining "Per-Query Cost"

| Cost dimension | Recommended unit | Evidence source |
|---|---|---|
| Partitions accessed | partitions/attempt | CQL shape, routing key, trace |
| Rows/cells scanned vs. returned | scanned/returned ratio | Tracing and table metrics; app counts returned rows |
| Tombstones read | tombstones/read | `Table.TombstoneScannedHistogram`, warning logs, tracing |
| SSTables touched | SSTables/partition read | `Table.SSTablesPerReadHistogram` |
| Network data | bytes/request, bytes/s | Driver, coordinator/network metrics, estimated response size |
| Disk reads / I/O | bytes/s, IOPS, disk await | OS/node disk stats, traces, load tests |
| CPU/GC | CPU seconds or % CPU/node, GC pause | OS/JVM metrics; requires isolated workload for per-family attribution |
| Memory/queues | in-flight, paging buffers, heap/off-heap, pending tasks | Driver/JVM, request pools, memtables/caches |
| New rows/SSTables from writes | bytes written, flush/compaction backlog | `Table.WriteLatency`, `BytesFlushed`, compaction metrics |
| LWT/counters | Paxos messages, contention, retries | `ClientRequest.CASRead/CASWrite`, tracing, app retries |

**Key point:** Many metrics are **per-table/node** and do not directly report "CPU per CQL template." When multiple query families share the same table and disk concurrently, **you cannot attribute all table disk bytes to one family** without controlled experiments or further breakdown.

### 6.2. From Per-Request Cost to Total Load per Second

When you have a reasonably reliable measure of average response bytes per request:

\[
B_{\mathrm{response/sec}} \approx QPS \times \overline{B}_{\mathrm{response/request}}
\]

Example:

| Family | QPS | Avg response bytes | Estimated logical response load |
|---|---:|---:|---:|
| `order.getById` | 800 | 2 KiB | 1,600 KiB/s |
| `order.listRecent` | 90 | 200 KiB | 18,000 KiB/s |
| `order.searchStatus` | 4 | 20 KiB | 80 KiB/s |
| `audit.exportNightly` | 0.05 | 2 MiB | 0.1 MiB/s on average |

`order.listRecent` consumes more **response bandwidth** than `getById` despite lower QPS. Meanwhile, `searchStatus` may return only 20 KiB while scanning **hundreds of thousands of rows**. **Response bytes do not represent disk read bytes.**

Likewise, if sampling shows a query typically scans around 100,000 rows per call at 4 QPS, it may generate **400,000 rows scanned/sec** within the sampled scope. This is only a **proxy**; it does not equal CPU cycles or total replica reads without knowing the execution behavior and retries.

### 6.3. Instantaneous Footprint vs. Time-Averaged Footprint

For an infrequently executed report:

- **Daily average** may look low.
- **At execution time**, it may touch many token ranges and saturate nodes.
- **While running**, it creates CPU/disk spikes and occupies request queues needed by other queries.

Therefore, capture **peak-second/peak-minute impact**, especially for repair, bulk ingest, batch jobs, exports, and distributed analytical reads. For strict interactive SLO queries, check **p99 and error budget**, not just bytes/sec.

### 6.4. Write Costs Must Also Be Evaluated

Query tuning is not limited to `SELECT`. A single mutation can replicate to multiple replicas, write to commit log/memtable, and trigger compaction. With denormalized tables, one business operation may write to multiple tables.

Example:

~~~text
API placeOrder:
    INSERT orders_by_id
    INSERT orders_by_customer_day
    INSERT order_status_by_warehouse

One business event -> 3 query families / 3 tables
Each table has its own RF and replica I/O.
~~~

You cannot conclude "INSERT takes only 3 ms so it is cheap": evaluate **write QPS, mutation size, RF, commit log, flushes, pending compactions, SSTable count**, and whether retries generate duplicate mutations. For LWT, assess contention and Paxos rounds rather than a single successful `UPDATE`.

## 7. Collecting Metrics at the Right Layer: Application, Driver, and Cassandra

### 7.1. Data Source Matrix

| Source | What can it measure? | Blind spots |
|---|---|---|
| API gateway / service tracing | Business operation, error budget, request latency | May span multiple CQL queries and caches; does not isolate individual queries |
| App instrumentation **by query family** | Count, latency, timeouts, pages, returned rows, SLO tags | Does not directly observe SSTables/tombstones on replicas |
| Java Driver session metrics | `cql-requests`, `cql-client-timeouts`, connected-nodes | Aggregates all query families on the session by default |
| Java Driver node metrics | `cql-messages`, `pool.in-flight`, per-node network/timeouts | Messages do not equal one business request; retries inflate counts |
| Cassandra `ClientRequest` metrics | Coordinator Read/Write/CAS latency, failures, timeouts, unavailables | Grouped by request type/node, not by CQL template |
| Cassandra `Table` metrics | Local read/scan latency, SSTables-per-read, tombstones, disk/compaction | Grouped by table/node, does not know business owner |
| CQL tracing / sampling | Events of a single query and participating replicas | Overhead, sampling bias, does not cover full workload |
| Controlled Full Query Logging (FQL) | Actual query traffic for classification or replay | Sensitive data, storage volume, requires approval and strict limits |
| `nodetool` and OS/JVM | Node/table hotspots, compaction, disk/GC, thread queues | Cannot isolate per-family CPU when workloads share nodes |

**Do not use a single source in place of the whole matrix.** Capture the **query family identifier from the application** and correlate it by timestamp/DC/table with **server-side metrics** to narrow down the cause.

### 7.2. Key Cassandra Table Metrics

Common names in Apache Cassandra documentation:

~~~text
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=ReadLatency
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=CoordinatorReadLatency
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=RangeLatency
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=SSTablesPerReadHistogram
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=TombstoneScannedHistogram
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=LiveScannedHistogram
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=EstimatedPartitionSizeHistogram
org.apache.cassandra.metrics:type=Table,keyspace=shop,scope=orders_by_tenant_day,name=ReadTotalLatency
~~~

Read carefully:

- `ReadLatency` at the **replica/local table** differs from `CoordinatorReadLatency`.
- `RangeLatency` applies to range scans at the table scope; it does not mean every CQL query with a clustering range is accounted for as a cluster-wide scan.
- `SSTablesPerReadHistogram` measures the number of SSTables *actually accessed* per partition read, after Bloom filters, min-max timestamps, and indexes prune irrelevant SSTables.
- `TombstoneScannedHistogram` and `LiveScannedHistogram` reveal scan overhead that may not show up in response bytes.
- `EstimatedPartitionSizeHistogram` gives clues about **overly wide partitions**, though it does not replace per-key statistics.

JMX metric names and exporter labels can vary by version, especially for histograms. Verify your exporter so you do not mistake a **cumulative histogram since server start** for a 5-minute window histogram without proper delta/snapshot conversion.

### 7.3. ClientRequest and Node-Wide Signals

~~~text
org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Latency
org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Timeouts
org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Unavailables
org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Latency
org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Timeouts
org.apache.cassandra.metrics:type=ClientRequest,scope=CASWrite,name=Latency
~~~

Node-wide signals also include `ThreadPools.ReadStage.PendingTasks`, `MutationStage`, native transport, pending compactions, commit log, GC, and I/O. When multiple query families spike in p99 simultaneously, it may be a **shared resource bottleneck** (disk, CPU, GC, network, node down) rather than every CQL query suddenly having a bad data model.

### 7.4. Java Driver 4.x Metrics: Meaning and Configuration

Per Java Driver 4.17 documentation, metrics are **disabled by default** and enabled selectively:

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      connected-nodes,
      cql-requests,
      cql-client-timeouts
    ]
    node.enabled = [
      cql-messages,
      pool.open-connections,
      pool.in-flight
    ]
  }
}
~~~

To export metrics, integrate the appropriate reporter (Dropwizard, Micrometer, etc.) and configure histograms/timers per the driver and library documentation. `cql-requests` measures `session.execute()` duration at the request level **including retries**. `cql-messages` tracks individual messages sent to a node and can exceed logical request counts when retries or speculative execution occur.

**Note:** Enabling driver metrics **does not automatically add query family labels**. To select critical CQL queries, add timers/counters **at the repository/service layer** using stable query family names; never use raw SQL/CQL literals or bind parameters as labels.

### 7.5. Safe Collection Commands

~~~bash
nodetool status
nodetool tablestats shop.orders_by_tenant_day
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool gcstats
~~~

Do not treat these commands as a "check 100% of queries" script. `nodetool tablestats` reflects aggregates per **table on a node**; `tpstats` shows background queues; `netstats` shows streaming; all must be correlated with query families and timestamps.

If a node shows high `TombstoneScannedHistogram` while the application has 20 families reading that table, sample/trace the suspect families instead of blaming all tombstones on one query.

## 8. Candidate Selection Method: From Longlist to Shortlist

Use a **two-stage approach** instead of collapsing everything into one score from the start:

### Stage 1 — Mandatory Triage

| Track | Condition | Decision |
|---|---|---|
| **Urgent (P0)** | Timeouts/Unavailables above threshold, payment/checkout impact, cluster nearing outage | Prioritize immediately, even at low QPS |
| **SLO breach (P1)** | p95/p99 or under-threshold ratio violates SLO across multiple windows | Investigate promptly, prioritize by user impact |
| **Capacity risk (P1)** | High QPS × cost, hot tombstones/SSTables/scans/CPU, projected peak overload | Investigate promptly even if current latency looks healthy |
| **Planned improvement (P2)** | Meets SLO, stable resources; clear cost-saving potential | Schedule by benefit vs. effort |
| **Defer/monitor** | Infrequent workload, low impact, safely bounded, no bottleneck evidence | Keep on dashboard, no changes yet |

**Never let an average score bury a P0.** A query deleting the wrong data or timing out payment requests demands immediate action regardless of how its composite score compares to a reporting query.

### Stage 2 — Ranking Within the Same Track

Score each candidate on a 0–5 scale using a rubric defined **before inspecting results**, for instance:

- `S` — SLO/error budget severity: 0 comfortably met; 5 severe breach.
- `R` — per-request resource × peak traffic: 0 low; 5 heavy CPU/disk/tombstone pressure.
- `F` — frequency/blast reach: 0 very low; 5 high request share or multi-node bursts.
- `B` — business impact: 0 non-critical batch; 5 core user-facing request.

An illustrative internal formula:

\[
Priority = 0.35S + 0.30R + 0.20F + 0.15B
\]

This is a **discussion aid**, not a Cassandra algorithm, and cannot replace engineering judgment. Weights depend on SLOs, budget, and capacity goals. For P0 incidents, priority is already decided in Stage 1; never use a score to downgrade a P0.

Example with **hypothetical data having owners and measurement sources**:

| Query family | Track | S | R | F | B | Relative priority |
|---|---|---:|---:|---:|---:|---|
| `order.getById` | P2 | 0 | 2 | 5 | 5 | High frequency, not urgent |
| `order.listRecent` | P1 SLO | 4 | 4 | 3 | 4 | Top priority in SLO group |
| `order.searchStatus` | P1 capacity | 5 | 5 | 1 | 3 | Low QPS, very expensive scan |
| `audit.exportNightly` | Defer | 0 | 2 | 0 | 1 | Schedule window bounded, monitor |

The `R` score **must only be assigned after evidence** from traces, bytes/rows scanned, or resource metrics; if missing, mark "**unknown**" instead of setting 0 and letting a dangerous query drop in rank.

### 8.1. Quantifying Improvement Opportunity

For latency, record:

~~~text
Family: order.listRecent
Current: p95=240ms, error rate=0.7% during peak 18:00–19:00
Target:  p95<=150ms, error rate<=0.1%
Peak QPS: 400

If changing table model / limit / paging:
  Hypothesis: reduce rows scanned and page fetches.
  Measure: p95/p99, total pages, tombstones/read,
           read bytes/requests, disk I/O, CPU, and result correctness.
~~~

Do not claim "saving 90 ms × 400 QPS = 36 CPU-seconds per second." Wall-clock latency is not CPU time. Mean latency improvement × QPS can only represent **total request residence time reduction** under valid assumptions; CPU/disk must be measured separately.

### 8.2. Filtering by Confidence and Change Risk

In the backlog, add:

| Attribute | Purpose |
|---|---|
| Evidence confidence: high/medium/low | Prevents tuning when root cause is unconfirmed |
| Estimated effort | Changing `LIMIT` takes hours vs. creating a new table, backfilling, and dual-writing over weeks |
| Blast radius | How many tables, services, DCs, and historical records are affected |
| Reversibility | Whether a feature flag, dual-read, or safe rollback exists |
| Data correctness risk | Whether semantics, CL, ordering, paging, TTL, or consistency change |
| Owner and deadline | Clear accountability and target peak/load-test window |

An easy SQL/CQL tweak that breaks pagination or accuracy **is not a better choice** than investing in the proper schema. Still, picking **measured quick wins** can relieve pressure early while a redesign is underway.

## 9. Identifying Which Cassandra Queries Are Likely Resource-Heavy

Once you have a shortlist, inspect the **CQL shape** to form hypotheses. Cassandra is optimized for **query-driven data modeling**: querying a single partition with the right keys is usually far more predictable than forcing the cluster to filter or scan broad data.

### 9.1. Classification by Access Pattern

| Query shape | Pattern | Strengths / risks | Signals to measure |
|---|---|---|---|
| **Point lookup** | Full partition key + full clustering key | Usually predictable if partition is small | p99, SSTables-per-read, node hotspots |
| **In-partition slice** | Partition key + clustering range | Reads in clustering order; can still be very wide | Rows scanned, pages, response size, partition size |
| **Multi-partition** | Multiple partition keys or app-level fan-out | Touches multiple token ranges/replicas | Fan-out, server traffic, retries, coordinator latency |
| **Index/SAI query** | Index-backed predicate | Can work well, but selectivity and node count matter | Candidate rows, post-filtering, index SSTable pressure |
| **Filtering** | `ALLOW FILTERING` | Unpredictable performance; few returned rows can still scan heavily | Scanned/returned ratio, CPU/disk, timeouts |
| **Large partition lookup** | Valid partition key, too many rows | Hotspots, many tombstones, many SSTables | Partition-size histogram, tombstones/read, p99 |
| **LWT/CAS** | `IF NOT EXISTS` or `IF ...` | Multiple Paxos rounds, contention | CASRead/CASWrite latency, contention, failures |
| **Unbounded scan/export** | Broad `SELECT *`, many pages | Cost scales with dataset, impacts cluster | Pages, bytes, range scan latency, off-peak footprint |
| **Write-heavy/update/delete** | High mutation/tombstone rate | LSM write amplification, flush/compaction | Mutation size, commit log, pending compactions, tombstones |

**Having a partition key does not guarantee a fast query**: if a partition holds millions of clustering rows, accumulates many tombstones, or requires reading hundreds of pages, p99 can still be high.

### 9.2. Three CQL Patterns to Compare

**Pattern A — Reading an exact row:**

~~~sql
SELECT status, total
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

With `PRIMARY KEY ((tenant_id), order_id)`, a large tenant can still form a wide partition, though Cassandra can locate the row via the clustering key. When per-tenant data grows unbounded, add appropriate bucketing/partitioning instead of assuming point lookups are always cheap.

**Pattern B — Reading history by day bucket:**

~~~sql
SELECT event_time, event_id, status
FROM shop.orders_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND order_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
LIMIT 50;
~~~

If the partition key is `(tenant_id, order_day)` and the clustering key starts with `event_time`, this is a single-partition range query. Adding a time bucket bounds partition size, though you must consider **users querying across multiple days**, where the application must read across buckets and merge results.

**Pattern C — Filtering status without a matching key:**

~~~sql
-- DO NOT run on large/production tables just to "test latency".
SELECT tenant_id, event_time, event_id
FROM shop.orders_by_tenant_day
WHERE status = 'PAID'
ALLOW FILTERING;
~~~

This is an **anti-pattern if the table lacks an appropriate index/access path**. `ALLOW FILTERING` permits the server to perform costly filtering; it does not turn the query into an efficient lookup. A query returning 5 rows may still inspect massive amounts of data. Solutions include a **query-specific table** (e.g., `orders_by_status_day`), a benchmarked index, or offloading analytics to a dedicated engine; never assume "adding SAI fixes every search."

### 9.3. `LIMIT` Is Not Proof of Optimization

`LIMIT 50` usually caps the **number of returned rows**, not the number of cells or SSTables read. For example:

- A partition with many tombstones must skip deleted entries before finding 50 live rows.
- Filtering may inspect many rows to yield 50 matches.
- Multiple partitions may be accessed and merged according to filtering/ordering rules.
- A `LIMIT 50` request can still have a large response if each row contains large collections or blobs.

Measure `rows_scanned / rows_returned`, tombstones/read, and response bytes instead of relying on `LIMIT`.

### 9.4. Reducing Returned Columns vs. Reducing Rows Read

~~~sql
-- Version 1: many columns, may fetch large payloads.
SELECT *
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

-- Version 2: returns only columns needed by the API.
SELECT status, total
FROM shop.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Projection can reduce response bytes, serialization, network traffic, and client heap. However, it does not guarantee a proportional drop in SSTables touched. **Measure both network and read path**, especially when wide rows or tombstones are the real culprit.

### 9.5. Hot Partitions and Skew Distort Aggregates

~~~text
Average family latency: 20ms
  tenant-small: p95=12ms
  tenant-medium: p95=30ms
  tenant-large: p95=600ms

Average Table.ReadLatency may still look reasonable
while one tenant tier severely breaches SLO.
~~~

To detect skew, tag with a low-cardinality **size bucket** or **tenant tier**. Never create labels per tenant ID. Use traces, metadata, and `EstimatedPartitionSizeHistogram` to inspect partition outliers, token-range distribution, and hotspot nodes. In multi-datacenter workloads, measure `LOCAL_QUORUM` and coordinator placement separately.

## 10. Deep-Diving a Candidate with Tracing and Server Evidence

Once the shortlist is set, use **one representative query** (or a few outliers) to pinpoint abnormal cost. Never enable full tracing for all production traffic.

### 10.1. Tracing Practice in cqlsh

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, status
FROM shop.orders_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND order_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
LIMIT 50;

TRACING OFF;
~~~

**How to read a trace:**

1. Which coordinator received the query? Are local DC and CL as expected?
2. Which replicas responded, and were there retries or speculative attempts?
3. How is time split across coordinator, waiting on replicas, SSTable reads, merge/reconciliation, and returning results?
4. Were many rows/cells read and discarded, or are there tombstone warnings or index/filter indicators?
5. Is the query slow on one partition or across multiple partitions? Does it correlate with specific token ranges or hot nodes?

A trace **is not an RDBMS EXPLAIN plan**. Cassandra has no universal SQL-style `EXPLAIN ANALYZE` for every CQL query. Tracing records execution events for that specific request; it adds overhead, varies in detail by version, and a single fast trace does not rule out peak-hour outliers.

### 10.2. Partial Traffic Tracing and FQL

Apache Cassandra provides `system_traces` and probabilistic tracing tools (such as `nodetool settraceprobability` on supported versions). **Use only with approval** because every trace writes metadata and adds load; even a small probability at high QPS can generate heavy trace volume.

Since Cassandra 4.0, **Full Query Logging (FQL)** can capture query traffic for analysis/replay; `nodetool enablefullquerylog` supports queue/disk limits. FQL differs from **tracing**: FQL logs queries, not how many tombstones each request scanned. Before enabling FQL in production, verify:

- Log volume, rotation, queue memory, I/O impact, and retention period.
- Access permissions for sensitive data in statements/bound values, encryption, and retention policies.
- Whether needed query forms can be captured without exposing PII.
- Run only within a **controlled window**, limited in node/scope, with a defined disable plan.

**Prefer application-level query family metrics** for continuous long-term frequency and latency tracking; use FQL/tracing when investigating **actual query shapes** or outliers that aggregate metrics cannot explain.

### 10.3. Combining Tracing with Table Stats

~~~bash
nodetool tablestats shop.orders_by_tenant_day
nodetool tpstats
nodetool compactionstats
~~~

| Observation | Reasonable interpretation |
|---|---|
| Trace shows multiple replica/page reads | Possible query fan-out or multi-page fetch |
| High `TombstoneScannedHistogram` + warnings | Scanning deleted data; check TTL, DELETE, compaction/repair |
| High `SSTablesPerReadHistogram` | Read amplification; inspect compaction backlog/strategy |
| Skewed `EstimatedPartitionSizeHistogram` | Some partitions are overly wide, driving tail latency |
| Rising `Compaction.PendingTasks` and disk await | Shared bottleneck; do not rush to rewrite CQL blaming a bad query |
| Rising `ClientRequest.Read.Timeouts` while app QPS is flat | Check node availability, overload, GC, consistency, and retries |
| Rising `RangeLatency` after bulk load | Scan/range queries may be hitting SSTable/compaction pressure |

**A single table may serve multiple query families**, so use traces and/or controlled experiments for attribution. When reads slow down because the entire node is saturated with compaction, tweaking a query's `WHERE` clause will not fix the physical bottleneck.

### 10.4. Separating Application vs. Server Causes

| Symptom | Verification path |
|---|---|
| High API p99 while Java CQL p99 is healthy | Cache, downstream calls, serialization, web server queues |
| High Java CQL p99 while Cassandra coordinator p99 is healthy | Network, client pool, throttling, retries, timeouts, pagination |
| High coordinator p99, low local table p99 | Waiting on replicas/quorum/network/queues or fan-out |
| High local table read p99 and high SSTables-per-read | Storage read amplification, compaction, disk |
| High local table read p99 and high tombstones/read | TTL/DELETE patterns, clustering range/partition design |
| A few nodes have higher p99 than others | Hotspots, token skew, disk/GC, topology, repair |

Never treat a single row in this table as definitive proof. Require the **same time window, same DC, same CL, same query family**, and repeatability across samples.

## 11. Common Pitfalls That Distort Prioritization

### 11.1. Comparing Different Time Windows

Comparing `getById` p99 at 2:00 AM against `listRecent` p99 at 7:00 PM is invalid. Collect at minimum:

- A business peak window with comparable load.
- A steady-state window after cluster caches have warmed.
- Batch/maintenance windows when workloads share resources.
- Before/after deployments, schema changes, bootstraps, or repairs.

### 11.2. Counting Only Successes

If a family has a 20% timeout rate, p95 over only the 80% successful requests may actually **drop** because the worst requests were excluded. Always count failures, timeouts, and requests exceeding deadlines; when durations are cut off at timeout, explicitly note **censored data**.

### 11.3. Single-Page Latency vs. Full Query Latency

The Java Driver uses paging: calling `execute()` may return only the **first page**; iterating through `ResultSet` or fetching further pages issues additional page requests. If an API needs to display 5,000 rows, timing only `execute()` **misses the cost of reading the rest**.

Conversely, if an API only needs the first 50 rows, do not fetch everything just to time it. Suffix family names with `firstPage`/`allPages` and record page size and rows consumed/returned; account for driver prefetching when counting actual page fetches.

### 11.4. Changing the Table Model Without Changing Template/Version

After a redesign, the same method `getRecentOrders` may query a different table or use a new time bucket. Reusing the `query_family` label without tracking `cql_template_id`/release mixes before and after data and leads to false conclusions.

### 11.5. Percentiles Are Not Additive

- Do not take a simple average of p95 across 10 pods and call it service-wide p95.
- Do not sum p99 across stages and call it end-to-end p99.
- Merge **appropriate histograms/distributions** or aggregate raw observations with proper weighting.
- If a rare family has only 10 requests in a window, p99 is essentially the max; report **sample count** and confidence.

### 11.6. Resource Cost May Originate from Other Requests

A query executing during heavy compaction or repair can exhibit high latency without being the root cause of I/O load. In experiments, keep total workload constant and avoid changing batch jobs, RF, compaction throttling, or node topology simultaneously if you want clean attribution.

## 12. Runbook for Selecting Top Queries in an Operational Cycle

A repeatable workflow that can run **weekly**, after major releases, or whenever the cluster breaches capacity/SLO thresholds.

### 12.1. Step 0 — Define Goals and Scope

Example goal: "Bring order API p99 below 250 ms and return peak CPU/disk to safe headroom, **without lowering CL or breaking result ordering**."

Confirm:

- Cluster, datacenter, Cassandra version, RF, keyspaces/tables.
- List of Java services, releases/feature flags, time windows (peak/steady/batch).
- SLOs for each business operation and error budgets.
- Target headroom for CPU, disk, network, heap/GC.
- Representative datasets/tenant tiers, plus privacy and audit requirements.

Do not promote a query to the top list just because Team A says it feels "slow" without observation window, sample count, and execution conditions.

### 12.2. Step 1 — Build the Longlist from Application Metrics

Create one row per **query family**:

~~~text
Query family          Request/s  p50  p95  p99  error rate  SLO   Owner
order.getById           800      5    12   27   0.01%     40ms  checkout
order.listRecent         90     45   240  570   0.70%    150ms  order-api
order.searchStatus        4    650  2000 4100   2.00%    600ms  ops-ui
audit.exportNightly    0.05   1500  5000 8400   0.00%  10000ms  audit
~~~

**These are hypothetical numbers.** If metrics lack family labels, add instrumentation before drawing conclusions; controlled short-term traffic sampling can seed an initial longlist, provided sampling bias is documented.

### 12.3. Step 2 — Correlate Tables and Resource Hotspots

For the tables accessed by the longlist:

~~~bash
nodetool tablestats shop.orders_by_tenant_day
nodetool tablestats shop.orders_by_id
nodetool tpstats
nodetool compactionstats
nodetool status
~~~

Collect `ReadLatency`/`CoordinatorReadLatency`, `SSTablesPerReadHistogram`, `TombstoneScannedHistogram`, partition sizes, disk I/O, GC, and CPU **per node**. Note the timestamp when metrics began climbing and which query families rose together.

**Distinguish correlation from attribution**:

- "Family `listRecent` p99 rose alongside `SSTablesPerRead` on the table" is a **hypothesis**.
- "Tracing `listRecent` confirmed reading many SSTables and tombstones, and the fix reduced those exact metrics" is **stronger evidence**.

### 12.4. Step 3 — Apply Mandatory Flags and Rank

1. Families causing critical errors or SLO breaches go into P0/P1 first.
2. High-QPS or bursty families with heavy footprints go into P1 capacity.
3. Remaining families can use priority scoring and effort estimates.
4. Queries lacking metrics can be marked "**investigate**", rather than defaulting to low priority.
5. Separate "investigate now" from "deploy schema change now": a P1 query may require deeper measurement before picking a solution.

### 12.5. Step 4 — Trace a Few Candidates First, Not Everything

Pick at most the top few families to stay focused. For each family:

~~~text
Family: order.listRecent
Hypothesis:
  Query reads too many rows to return 50 display rows.
Evidence:
  Peak p95=240ms >150ms; QPS=90; 4 pages/request;
  high table tombstones/read p95; traces on large tenants.
Proposed action:
  Check bucket/day, time range, page size, and row limits.
Expected impact:
  Reduce rows scanned and pages, improving p95/p99.
Non-negotiable:
  Must not omit events inside the time range and
  must not alter pagination ordering semantics.
~~~

Avoid "tuning by rumor" such as "add indexes to all columns" or "increase thread pools" before identifying the bottleneck.

### 12.6. Step 5 — Test One Change Under Control

Design a repeatable A/B or load test:

- Keep request mix, peak QPS, data size, hot keys, CL, page size, and cache warmup equivalent.
- Do not bundle schema changes with RF changes, JVM memory tuning, compaction strategy changes, and unrelated deploys when isolating cause and effect.
- Measure **success + timeout**, latency histograms, CPU/disk, tombstones, SSTables-per-read, and returned rows.
- Verify **business correctness**, especially when adding buckets/denormalization or altering ordering.
- Prepare rollback/feature flags or an evaluated dual-read/dual-write plan.

### 12.7. Step 6 — Verify in Limited Production

Roll out via canary, compare the same time window/tier against baseline, and ramp traffic gradually. If p99 drops while CPU/disk rises and impacts other families, inspect **cluster-wide health**, not just one service dashboard.

A change fails verification if:

- Latency improved by **lowering CL** in violation of application consistency requirements.
- Returned rows dropped because **required data was omitted** or ordering/paging broke.
- Timeouts disappeared because **real errors were swallowed**, exceptions ignored, or timeouts inflated indefinitely.
- One node grew hotter or disk saturated despite a nicer cluster-wide mean latency.

### 12.8. Step 7 — Publish Results and Revisit the Longlist

~~~text
QUERY TUNING REVIEW — period 2026-W47, hypothetical metrics

1. P1 listRecent:
   Owner: order-api
   Before: p95=240ms, peak=400QPS, 4 pages/request
   After:  p95=120ms, peak=400QPS, 1 page/request
   Data correctness: PASS
   Resource effect: CPU/disk did not increase; tombstone scans dropped

2. P1 searchStatus:
   Owner: ops-ui
   Investigation: ALLOW FILTERING, multiple partitions
   Action: design query-driven table, validate backfill/dual-write
   Status: EXPERIMENT; not yet deployed to production

3. P2 getById:
   800 QPS, p95=12ms below SLO=40ms
   Status: MONITOR; do not prioritize ahead of the two P1s
~~~

Every cycle should update both **top queries** and **items intentionally deferred with rationale**. If data growth or a new feature pushes a family from 4 to 100 QPS, re-rank immediately.

## 13. Dashboards and Tracing: Displaying Data Without Misleading Operators

### 13.1. Minimum Dashboard Panels

| Panel | Labels | Purpose |
|---|---|---|
| QPS by query family | service/family/release/DC | Identify hot families and bursts |
| p50/p95/p99 by family | service/family/DC/CL | Detect SLO breaches and tail latency |
| Error/timeout rate | family/error class | Avoid measuring only successful requests |
| In-flight requests and driver pool | service/instance/DC/node | Inspect client queues and retry spikes |
| Response bytes/rows/pages | family/result_mode | Separate payload size from paging |
| Cassandra ClientRequest | node/DC/Read/Write/CAS | Distinguish coordinator-wide latency and errors |
| Table ReadLatency, SSTablesPerRead, tombstones | node/table | Pinpoint table hotspots and read amplification |
| Compaction/flush/commit log | node/table | Assess shared bottlenecks |
| Disk/CPU/GC/network | node/disk/DC | Separate query inefficiency from infrastructure issues |
| Change markers | release/schema/RF/topology/repair | Correlate regressions with operational changes |

**Never use partition key, tenant, user, or SQL text as metric labels.** To investigate outliers, use controlled **trace IDs** in your logging/tracing backend instead of turning IDs into time-series labels.

### 13.2. Illustrative PromQL Examples

Because exporter metric names vary, the snippets below are **not copy-paste runnable commands**. Assume the app uses Micrometer exposing histogram buckets `app_cql_family_duration_seconds_bucket` and counter `app_cql_family_requests_total`:

~~~promql
# p95 per family over a 5-minute window, only if the histogram
# is exported under this exact bucket metric name.
histogram_quantile(
  0.95,
  sum by (le, service, query_family) (
    rate(app_cql_family_duration_seconds_bucket[5m])
  )
)
~~~

~~~promql
# Request QPS per family; adjust metric names to match your system.
sum by (service, query_family) (
  rate(app_cql_family_requests_total[5m])
)
~~~

~~~promql
# Logical error rate; denominator must include failures.
sum by (service, query_family) (
  rate(app_cql_family_requests_total{outcome!="success"}[5m])
)
/
clamp_min(
  sum by (service, query_family) (
    rate(app_cql_family_requests_total[5m])
  ),
  1e-9
)
~~~

**Caveat:** `histogram_quantile` requires well-chosen histogram buckets and sufficient sample counts; client metrics sometimes emit summaries or timers without compatible buckets. Check your exporter format before pasting queries. For Prometheus classic histograms, compute quantiles from summed buckets rather than averaging per-JVM p99 values.

### 13.3. Three-Window Metric Framework

~~~text
Window A — Last 5 minutes:
  detect incidents and spikes

Window B — 1-hour peak:
  verify capacity demand during peak traffic

Window C — 7 to 14 days:
  evaluate data growth trends, seasonality,
  and select queries for long-term optimization
~~~

Record version/release markers and exclude abnormal maintenance windows when isolating **inefficient query shapes**. However, if maintenance consistently collides with peak traffic, it remains a **real operational risk** requiring prioritization.

## 14. Deciding "Tune the Query or Fix Another Layer?"

Not every SLO breach requires rewriting CQL:

| Evidence | Priority direction |
|---|---|
| Scanning too many rows/tombstones relative to results | Redesign partition/clustering access, TTL/delete strategy, or query-specific table |
| Many pages and wide payloads | Limit actually needed results, projection, page size, and UI contract |
| Query fans out across many partitions due to bad model | Design table/partition key around access pattern |
| Low-selectivity SAI/index query | Tighten predicates, benchmark index vs. denormalized table, account for fan-out |
| Rising LWT contention | Reduce single-key contention, redesign workflow, or split hot partitions |
| All families on a node show rising p99 + disk await | Investigate disk/compaction/repair/capacity before blaming one CQL query |
| Driver pool exhausted and retries rising | Inspect connection pool, concurrency, timeouts, idempotency |
| App JSON/serialization is very slow | Fix the application layer instead of futile Cassandra tuning |
| Nightly job collides with peak but can be shifted | Reschedule/rate-limit instead of redesigning a rare query |
| App repeatedly reads the same key excessively | Consider caching with proper TTL/invalidation rather than blindly |

**Core selection principle:** Every candidate needs a **falsifiable hypothesis**. If reducing rows scanned does not improve p99, investigate network/pools/GC rather than declaring query tuning successful using unrelated numbers.

## 15. CQL Lab: Comparing Three Query Patterns on the Same Data

**Lab goal:** Create a small query-driven table, run three query families with different shapes, enable selective tracing, and build an evidence table. This exercise **does not require heavy load**; with only a few rows, latency and cost are tiny, so never extrapolate benchmarks to production datasets.

**Environment:** Single-node Apache Cassandra 4.1 or 5.0 lab, `cqlsh`, and `nodetool` read access. Using `SimpleStrategy` RF=1 is only for single-node learning; multi-DC production requires `NetworkTopologyStrategy` and appropriate RF.

### Step 1 — Create Keyspace and Time-Bucketed Table

~~~sql
CREATE KEYSPACE IF NOT EXISTS query_priority_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS query_priority_lab.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    status text,
    payload text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Design notes:

- **Partition key**: `(tenant_id, day)` — one tenant on one day.
- **Clustering key**: `(event_time, event_id)` — ordered time-range queries with a unique tie-breaker.
- `status` is a **regular column**, not an efficient lookup key on its own; filtering by `status` inside a partition may require scanning.
- No joins, and no arbitrary `ORDER BY` on non-clustering columns.

### Step 2 — Load Small Sample Data

~~~sql
INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
  11111111-1111-1111-1111-111111111111, 'NEW', 'created');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:05:00Z',
  22222222-2222-2222-2222-222222222222, 'PAID', 'payment accepted');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:10:00Z',
  33333333-3333-3333-3333-333333333333, 'PAID', 'confirmed');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:15:00Z',
  44444444-4444-4444-4444-444444444444, 'CANCELLED', 'cancelled');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-b', '2026-11-21', '2026-11-21T08:30:00Z',
  55555555-5555-5555-5555-555555555555, 'PAID', 'confirmed');

INSERT INTO query_priority_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T18:00:00Z',
  66666666-6666-6666-6666-666666666666, 'PAID', 'previous day');
~~~

Keep the lab small to inspect query shapes; **do not** load millions of rows in production just to prove `ALLOW FILTERING` can be slow. If the lab was run previously, repeated `INSERT`s overwrite the same primary keys; when measuring latency, distinguish cold/warm cache and initial table creation.

### Step 3 — Family A: Exact Single-Row Read by Full Key

~~~sql
CONSISTENCY ONE;
TRACING ON;

SELECT status, payload
FROM query_priority_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND event_time = '2026-11-21T08:05:00Z'
  AND event_id = 22222222-2222-2222-2222-222222222222;

TRACING OFF;
~~~

Label this `events.getExact`. This is a predictable point access: full partition key and full clustering key. Inspect the printed trace: coordinator, replica, timings, and operations performed. Do not treat a single run as p99.

### Step 4 — Family B: In-Partition Slice

~~~sql
TRACING ON;

SELECT event_time, event_id, status
FROM query_priority_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
LIMIT 3;

TRACING OFF;
~~~

Label this `events.listByHour`. Because `event_time` is clustered `DESC` inside the partition, Cassandra can seek and return the matching range. Changing `LIMIT` or the time bounds alters rows read/returned and page counts; on a tiny dataset, latency differences are negligible.

### Step 5 — Family C: In-Partition Filtering (Lab Only)

~~~sql
-- Only use when the table is known to be very small and filtering is permitted.
TRACING ON;

SELECT event_time, event_id, status
FROM query_priority_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND status = 'PAID'
ALLOW FILTERING;

TRACING OFF;
~~~

Label this `events.filterPaidWithinDay`. If the cluster enables a guardrail blocking `ALLOW FILTERING`, the statement may be rejected; that is **not a lab failure**—note the guardrail instead of disabling protections in production.

This query **still specifies the partition key**, so the example demonstrates **in-partition filtering**, not an unbounded cluster-wide scan. Does the partition span multiple days? No: partitions are bucketed by day. However, if a tenant/day has millions of events, it can **still** scan huge numbers of rows to return just a few `PAID` rows. That is why you must track `scanned/returned ratio` as traffic grows.

### Step 6 — Inspect Table, SSTables, and Tombstones

~~~bash
nodetool tablestats query_priority_lab.events_by_tenant_day
nodetool compactionstats
nodetool tpstats
~~~

From metrics/JMX, inspect `ReadLatency`, `SSTablesPerReadHistogram`, `TombstoneScannedHistogram`, and `LiveScannedHistogram` if an exporter is available.

**Limitation of this lab:** Too few rows exist to differentiate I/O pressure, disk/CPU load, or meaningful p99. To benchmark properly, move to a **dedicated staging environment** loaded with representative partition sizes, TTL/DELETE rates, traffic mix, key skew, and RF. **Never** conclude "Family C is faster than A" because one `cqlsh` run took 2 ms while A took 3 ms.

### Step 7 — Observe Pagination

~~~sql
PAGING 2;

SELECT event_time, event_id, status
FROM query_priority_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

PAGING ON;
~~~

`PAGING 2` sets the page size for **cqlsh** during this session; it does not change your Java application's page size. When an API consumes all pages, measure page count and total completion time; if an API only needs the top 3 rows, do not fetch everything and discard the rest.

### Step 8 — Fill in the Ranking Table from Your Own Measurements

| Attribute | A — getExact | B — listByHour | C — filterPaidWithinDay |
|---|---|---|---|
| SLO defined? | Fill in | Fill in | Fill in |
| Actual QPS in application? | Needs instrumentation | Needs instrumentation | Needs instrumentation |
| p95/p99 under representative load? | Needs load test | Needs load test | Needs load test |
| Partition scope | Single partition | Single partition | Single partition |
| Expected rows examined | One exact key | One range | Potentially many rows to filter |
| Page/response bytes | Measure | Measure | Measure |
| Tombstones/read, SSTables/read | Measure | Measure | Measure |
| Priority? | Based on 3 axes | Based on 3 axes | Based on 3 axes |

**Correct takeaway from the lab:** Shape C can be expensive on large partitions, **yet you cannot assign a real-world priority** until you measure QPS, latency, and resource cost under a representative workload. The exercise teaches **evidence-based decision-making**, not gut-feeling rankings.

### Step 9 — Sketching a Model If Family C Proves Critical

If the business frequently needs "PAID events for a tenant on a day", consider a dedicated query table:

~~~sql
-- Illustrative schema only; design dual-write/backfill/TTL and
-- data correctness checks before real deployment.
CREATE TABLE IF NOT EXISTS query_priority_lab.events_by_status_day (
    tenant_id text,
    day date,
    status text,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, day, status), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

SELECT event_time, event_id, payload
FROM query_priority_lab.events_by_status_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND status = 'PAID'
LIMIT 50;
~~~

This schema only proves the **access path**; it contains no data because rows do not automatically migrate from the old table. Production readiness requires:

- Controlled backfill of historical data.
- Reliable dual-write/CDC/outbox or synchronization pipeline.
- Handling **status transitions**: deleting the old-status entry and writing the new-status entry.
- Designing TTL/DELETE, repair, retries, and idempotency across both tables.
- Reconciliation against the source of truth to ensure the derived table has no missing or stale rows.

Only accept the write amplification and denormalization cost if **frequency × SLO × resource savings** of query C justifies it.

## 16. Java Driver 4.x: Measuring Query Families Directly in the Application

Driver 4.x exposes aggregate metrics at the session and node levels, but to **rank individual query families**, the practical approach is instrumenting at the repository/service layer with stable operation names. The example below uses **Java 17 + DataStax Java Driver 4.x + Micrometer Core**, where `MeterRegistry` is supplied via DI. This is illustrative code—do not create a new Cassandra session or `MeterRegistry` per request.

### 16.1. Repository with Two Distinct Query Families

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

public final class EventRepository {
    public record EventSummary(
            Instant eventTime, UUID eventId, String status) {}

    private final CqlSession session;
    private final MeterRegistry metrics;
    private final PreparedStatement getExact;
    private final PreparedStatement listByHour;

    public EventRepository(CqlSession session, MeterRegistry metrics) {
        this.session = session;
        this.metrics = metrics;

        this.getExact = session.prepare(
            "SELECT event_time, event_id, status " +
            "FROM query_priority_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND day = ? " +
            "AND event_time = ? AND event_id = ?");

        this.listByHour = session.prepare(
            "SELECT event_time, event_id, status " +
            "FROM query_priority_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 50");
    }

    public EventSummary getExact(
            String tenantId, LocalDate day,
            Instant eventTime, UUID eventId) {
        return observe("events.getExact", () -> {
            BoundStatement query = getExact.bind(
                    tenantId, day, eventTime, eventId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE);

            Row row = session.execute(query).one();
            return row == null ? null : convert(row);
        });
    }

    public List<EventSummary> listByHour(
            String tenantId, LocalDate day,
            Instant startInclusive, Instant endExclusive) {
        return observe("events.listByHour", () -> {
            BoundStatement query = listByHour.bind(
                    tenantId, day, startInclusive, endExclusive)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(50);

            ResultSet result = session.execute(query);
            List<EventSummary> events = new ArrayList<>();
            for (Row row : result) {
                events.add(convert(row));
            }
            return events;
        });
    }

    private static EventSummary convert(Row row) {
        return new EventSummary(
            row.getInstant("event_time"),
            row.getUuid("event_id"),
            row.getString("status"));
    }

    private <T> T observe(String family, Supplier<T> operation) {
        // "family" only accepts STATIC values from code, never tenantId.
        long started = System.nanoTime();
        boolean success = false;
        try {
            T answer = operation.get();
            success = true;
            return answer;
        } finally {
            String outcome = success ? "success" : "failure";
            long elapsed = System.nanoTime() - started;

            Timer.builder("app.cql.family.duration")
                .tag("service", "query-lab")
                .tag("query_family", family)
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(metrics)
                .record(elapsed, TimeUnit.NANOSECONDS);

            Counter.builder("app.cql.family.requests")
                .tag("service", "query-lab")
                .tag("query_family", family)
                .tag("outcome", outcome)
                .register(metrics)
                .increment();
        }
    }
}
~~~

Detailed explanation:

1. `PreparedStatement`s are prepared **once** in the constructor, not re-prepared on every request.
2. Both methods use **static query family labels**, never UUIDs or tenant IDs, to prevent label cardinality explosion.
3. `getExact` reads a single row; `listByHour` iterates the full result set, bounded by `LIMIT 50` in CQL. The timer covers iterating through the result rather than stopping right when `execute()` returns the first page.
4. `Timer` records **wall-clock elapsed time** via `System.nanoTime()`. It does not measure Cassandra CPU/disk; correlate it with table/OS metrics.
5. The `outcome` tag ensures failed requests are not excluded from distributions. In production, split **timeout/unavailable/validation failure** into a bounded set of categories instead of only success/failure.
6. `Timer.builder(...).register(metrics)` works for a demo; in production, **cache pre-registered `Timer`/`Counter` instances** for fixed query families to avoid lookup/allocation overhead per request.

**Lab code note:** Uses `CL=ONE` because `query_priority_lab` has RF=1. Production must use `LOCAL_QUORUM` or the level suited to RF/DC and consistency guarantees; **never copy `CL=ONE` into sensitive business paths**.

### 16.2. Usage in Application Code

~~~java
// Inside a method that already holds CqlSession and MeterRegistry.
EventRepository repo = new EventRepository(session, meterRegistry);

EventRepository.EventSummary exact = repo.getExact(
    "tenant-a",
    LocalDate.parse("2026-11-21"),
    Instant.parse("2026-11-21T08:05:00Z"),
    UUID.fromString("22222222-2222-2222-2222-222222222222"));

List<EventRepository.EventSummary> recent = repo.listByHour(
    "tenant-a",
    LocalDate.parse("2026-11-21"),
    Instant.parse("2026-11-21T08:00:00Z"),
    Instant.parse("2026-11-21T09:00:00Z"));
~~~

Results can be exported to your monitoring stack via the configured `MeterRegistry`. With a Prometheus exporter, verify whether actual histogram buckets are emitted before querying with `histogram_quantile`.

### 16.3. Single Call Measurement vs. Full Workflow Measurement

If an API invokes:

~~~text
GET /orders/{id}
    |
    +-- events.getExact  (CQL family A)
    +-- orderPayments.getById (CQL family B)
    +-- fraudService.verify (HTTP)
    +-- JSON serialization
~~~

A timer wrapping `events.getExact` only measures **part A**. High API p99 might come from `fraudService.verify`. Looking only at server `Table.ReadLatency` and tuning A could optimize the wrong component.

You should capture:

- An **end-to-end** API span/timer.
- Nested spans/timers for each **query family** and downstream call.
- Driver session/node metrics to verify network/retry time.
- Server JMX metrics to see replica/table pressure.

With asynchronous driver APIs, measure from submission until the future completes or the target pages are consumed; do not stop the timer right after `executeAsync()`, as the request has usually not completed yet.

### 16.4. Recording Rows, Pages, and Response Size

In `listByHour`, you can additionally record:

- `returned_rows = events.size()`.
- Additional page fetch counts if implementing custom async paging; remember the driver may prefetch.
- Estimated response size if a serialization layer measures bytes.
- `page_size`/`LIMIT`/`CL` as static metadata or a controlled set of buckets.

Do not treat `events.size()` as server-side "rows scanned": Cassandra may scan many rows/tombstones to return that small count. Combine with traces and table metrics when inferring I/O cost.

## 17. Three Case Studies in Selecting the Right Query

### 17.1. Case A — Poor p99 with Low QPS

~~~text
Family: customer.searchStatus
Normal QPS = 3; peak=80; p99=4.2s; SLO=600ms
Rows returned ≈ 15; trace shows scanning huge numbers of rows
Several runs at 18:00 spike disk await across 3 nodes
~~~

**Decision:** Warranted as P1 capacity/SLO despite normally low QPS. Inspect filtering, index selectivity, partition access, and batch timing. A query-specific table or offloading search to a dedicated engine may be far better than raising timeouts.

**Trap:** Looking only at average QPS, missing the 80 QPS peak, and vastly underestimating capacity impact.

### 17.2. Case B — Very High QPS While Meeting SLO

~~~text
Family: order.getById
800 QPS average, peak=2000; p95=12ms; SLO=40ms
Point lookup by primary key, response≈2KiB
Node disk/CPU and p99 are stable with headroom remaining
~~~

**Decision:** Keep on the dashboard and project growth; do not prioritize ahead of P1 queries. If a 3× QPS surge is forecasted against tight headroom, promote it to capacity optimization even while latency looks good.

**Trap:** Treating 800 QPS as an automatic mandate to tune, spending engineering effort without improving user experience or real capacity.

### 17.3. Case C — Multiple Queries Slow Simultaneously Due to Node Overload

~~~text
During peak:
  getById p99:       30 -> 300 ms
  listRecent p99:   200 -> 900 ms
  searchStatus p99:   2 ->   8 s

Simultaneously:
  Disk await on node N3 spikes.
  Pending compactions and repair streaming surge.
  GC pauses also increase.
~~~

**Decision:** Open an incident for the shared bottleneck first. Temporarily defer repairs/batches per runbook and analyze capacity. Only after the cluster stabilizes can you separate which query families are **inherently** expensive.

**Trap:** Editing three CQL queries simultaneously and claiming success when repair finishes on its own, even though CQL edits were not what restored performance.

### 17.4. Case D — Better Latency at Worse Resource Cost

A candidate `listRecent` was changed from two small queries into one very broad query. Mean latency may drop due to fewer round trips, but the server scans more rows, increasing tombstone reads and disk I/O.

**Decision:** Accept only if **SLO, throughput headroom, resource footprint, and correctness** all pass. In Cassandra, fewer requests **do not automatically** reduce total resource usage.

### 17.5. Case E — Fewer Reads at High Write Amplification

A status-lookup query was tuned by adding an `orders_by_status` table. Read latency improved, but every status transition now requires `DELETE` old entry + `INSERT` new entry; TTLs and repairs on the secondary table add extra workload.

**Decision:** Weigh **query frequency × saved cost** against **write traffic × number of derived tables**, operational complexity, and data drift risk. Deploy only with reliable synchronization and data verification tests.

## 18. Evaluating Tuning Results: Beyond "The Query Got Faster"

### 18.1. Four Validation Gates

| Gate | Question | Pass condition |
|---|---|---|
| **A — Correctness** | Are data, ordering, paging, TTL, and consistency still right? | Verified against expected data and business tests |
| **B — Latency/SLO** | Did p95/p99 and failure rate improve during peak? | Meets SLO in the same window with sufficient samples |
| **C — Resource** | Did CPU/disk/network/memory and scans/SSTables/tombstones drop or preserve headroom? | Cost was not shifted excessively to other nodes/tables |
| **D — Operability** | Are rollback, owner, and post-deploy monitoring in place? | Capable of detecting regressions or backfill/dual-write failures |

### 18.2. Hypothetical Experiment Results

| Metric `order.listRecent` | Before | After | Interpretation |
|---|---:|---:|---|
| Peak QPS | 400 | 400 | Equivalent traffic |
| p95 | 240 ms | 120 ms | Meets 150 ms SLO |
| p99 | 570 ms | 240 ms | Improved tail |
| Timeout rate | 0.7% | 0.1% | Includes all failures |
| Pages/request | 4 | 1 | Fewer fetches with equivalent semantics |
| Rows returned | 50 | 50 | Results not truncated |
| Tombstones scanned p95 | 300 | 30 | Assumes fewer shadowed entries traversed |
| Disk read p99 on hot node | 35 ms | 18 ms | Resource improved; still verify peer nodes |

This is an **illustrative table**, not a guarantee that changing `LIMIT` achieves these numbers. In practice, measure across multiple sufficiently sampled windows, check data skew, and ensure no concurrent cluster changes confound conclusions.

### 18.3. What If Only Two of Four Gates Pass?

- A fails: **do not deploy**, regardless of p99 gains.
- B fails: revisit hypothesis and trace remaining bottlenecks.
- C fails: evaluate capacity risk; latency may have dropped by consuming excessive resources.
- D fails: not ready for broad rollout; add canary/rollback/monitoring first.

For **critical** query families, correctness and safe rollback must be **non-negotiable**.

## 19. Misconceptions That Lead to Picking the Wrong Query

| Misconception | Why it is wrong | Right approach |
|---|---|---|
| "The query with the highest p99 is always top priority." | It could be a rare background job well within its SLO | Consider SLO, frequency, peak bursts, and business criticality |
| "The highest-QPS query must be fixed first." | A point lookup may be cheap with plenty of headroom | Measure per-request cost and total footprint |
| "Total wall-clock ms × QPS = CPU seconds." | Latency includes waiting on network/I/O/quorum/queues | Separate concurrency proxy from actual CPU/disk |
| "`Table.ReadLatency` tells which CQL query is slow." | Metric is per table/node, mixing multiple query families | Instrument families in Java and trace candidates |
| "Java Driver `cql-requests` tags by CQL template automatically." | Session metrics aggregate requests | Create timers at repository/service level with fixed family labels |
| "One 2 ms `cqlsh` run beating 3 ms is proof." | Caching, warmup, sampling, and load vary | Benchmark across many samples with identical workload and data |
| "Returning 10 rows means only 10 rows were read." | Filtering/tombstones can scan many rows | Measure scanned/returned, tombstones, SSTables-per-read |
| "`LIMIT 50` always caps cost to 50 rows." | Must still skip tombstones or apply filters | Check traces/metrics; do not infer from `LIMIT` |
| "`ALLOW FILTERING` is the fix for missing indexes." | Can scan huge ranges with unpredictable latency | Design query-driven tables or benchmarked indexes |
| "A valid partition key guarantees a fast query." | Hot/wide partitions or TTLs can still be costly | Check partition size, clustering range, and skew |
| "Average pod p99 values to get service-wide p99." | Percentiles do not combine linearly | Merge histograms/raw samples statistically |
| "Tag metrics with SQL text and tenant ID." | High cardinality and data leakage risk | Label by family/template/version and bounded dimensions |
| "Measuring successful requests is enough." | Dropping timeouts makes tail latency look artificially good | Count failures/timeouts and track SLA violations |
| "Retries eliminated timeouts, so the query is tuned." | Retries add physical attempts and mask root errors | Measure retry cost, idempotency, in-flight load, server pressure |
| "Adding another read table only has upsides." | Write amplification, backfill, derived-table consistency | Weigh system-wide read/write cost and correctness |
| "All queries slowed down, so tune every `WHERE` clause." | Could be disk, GC, compaction, or a down node | Investigate shared bottlenecks first |
| "Raising the timeout means meeting the SLO." | SLOs govern actual latency/error budget, not configured timeouts | Use percentiles, threshold compliance, and error budgets |
| "Once the top 3 are picked, the ranking stays fixed." | Datasets, traffic, features, and topology evolve | Review periodically and after major changes |

## 20. Quick Checklist for Admitting Candidates to the Tuning Backlog

### 20.1. Before Promoting to Top Candidates

- [ ] CQL pattern/operation has a stable **query family** and clear owner.
- [ ] Keyspace/table, partition key, clustering key, CL, and local DC are documented.
- [ ] Request counts and QPS for **both average and peak hours** in the same period are known.
- [ ] p50/p95/p99, timeout/failure rates, and matching SLOs are recorded.
- [ ] Time-to-first-page is distinguished from time-to-all-pages.
- [ ] Response bytes/rows and associated server resources are estimated.
- [ ] Table/node hotspots, compaction, tombstones, and disk/GC were checked if suspect.
- [ ] Sample sizes are sufficient; p99 values across different groups were not averaged.
- [ ] No sensitive raw values, bind data, or tenant IDs appear in metric labels.
- [ ] P0/P1 (SLO/capacity) items are separated from P2 (planned optimization).
- [ ] A root-cause hypothesis exists that is **testable via tracing/experiments**.
- [ ] A plan exists to measure effectiveness and side effects on other query families.

### 20.2. Before Deploying an Optimization

- [ ] Compared on a representative workload for QPS, peak, partition size, tombstones, and page size.
- [ ] Correctness tests exist verifying returned row count/content, ordering, TTL, and paging.
- [ ] RF/CL requirements were reviewed; consistency was not silently weakened for prettier latency.
- [ ] Owner, canary, rollback, and data migration plan exist if adding a new table.
- [ ] Write amplification, backfill, and dual-write costs were assessed for schema changes.
- [ ] Latency, timeouts, node/disk/CPU, and resource footprint were measured before and after.
- [ ] No incidents caused by running `ALLOW FILTERING` on massive production datasets just to "benchmark."
- [ ] No unbounded full tracing/FQL or logging sensitive bind values.
- [ ] A follow-up review trigger is set for future QPS or data-size growth.

## 21. Self-Assessment Questions

**Q1.** `A` runs at 2,000 QPS with p95 = 10 ms (SLO 50 ms). `B` runs at 50 QPS with p95 = 350 ms (SLO 150 ms). Which query should be investigated first?  
**Guidance:** B is breaching its SLO; A still merits capacity tracking due to high QPS, but does not automatically outrank B.

**Q2.** `getOrder` reads 2 KiB/request at 1,000 QPS. `listOrders` reads 200 KiB/request at 100 QPS. Which generates more response bytes/s?  
**Guidance:** `getOrder` ≈ 2,000 KiB/s; `listOrders` ≈ 20,000 KiB/s. Response bytes still do not represent disk reads.

**Q3.** A query runs at 4 QPS, scanning ~100,000 rows per call while returning only 10. Can it be ignored because QPS is low?  
**Guidance:** No; peak bursts and scanned/returned ratio are huge, making it a clear capacity risk.

**Q4.** Why can't 800 QPS × 6 ms mean latency be called 4.8 CPU-seconds per second?  
**Guidance:** That is equivalent concurrency based on residence time, which includes waiting on network, replicas, and disk—not CPU time.

**Q5.** Both Cassandra `Table.ReadLatency` and Java Driver `cql-requests` increased. Can you pinpoint the specific query family yet?  
**Guidance:** Not yet. You need template/family instrumentation or sampling/tracing.

**Q6.** One client fetches only the first page while another service reads all 20 pages. Should their p99 values be combined simply because they use the same CQL?  
**Guidance:** No. Separate result modes, page sizes, and actual pages consumed.

**Q7.** A query returns 5 rows using `ALLOW FILTERING`. Does that mean only 5 rows were read?  
**Guidance:** No; Cassandra may scan many rows, partitions, and tombstones while filtering.

**Q8.** Why should `tenant_id` never be used as a Prometheus label?  
**Guidance:** High cardinality, metric storage cost, and data-exposure risk; use query families and bounded buckets.

**Q9.** Some nodes show high p99 while others are low. Should you average per-node p99 to report cluster-wide p99?  
**Guidance:** No; merge raw histograms/distributions properly and investigate node hotspots.

**Q10.** Query p95 spikes while the whole cluster is running repair and disk await is climbing. Should you immediately rewrite the schema?  
**Guidance:** Not yet; investigate the shared bottleneck first and re-evaluate once background load is controlled.

**Q11.** When creating `events_by_status_day`, what else is needed beyond `CREATE TABLE` so queries return complete data?  
**Guidance:** Backfill, dual-write/CDC, deleting old-status entries on transitions, retries/idempotency, and data reconciliation.

**Q12.** When testing a new query, p95 drops 40% while returned rows fall from 50 to 30 for the same filter. Can you declare success?  
**Guidance:** No if semantics require 50 rows; the correctness gate fails.

**Q13.** Query A runs at 0.01 QPS with p99 = 10 s, yet the background job SLO is 20 s and does not touch peak hours. Must it be P1?  
**Guidance:** No. It can be deferred, though you should still watch for resource spikes and operational risk.

**Q14.** Why doesn't a clean `nodetool tablestats` guarantee that every query family on that table meets its SLO?  
**Guidance:** Per-node/table aggregates can hide outliers, multi-page consumption, client retries, and tenant skew.

**Q15.** Why can driver `cql-messages` exceed `cql-requests`?  
**Guidance:** Retries, speculative execution, and physical attempts to nodes—one application request does not equal one message.

**Q16.** A query lowers p99 while driving up `PendingCompactions` and disk usage across all replicas. What should be evaluated?  
**Guidance:** The resource gate, write amplification, total workload, and headroom; a rollback or adjustment may be required.

## 22. Summary

~~~text
                API / JAVA SERVICE REQUESTS
                           |
                   Tag QUERY FAMILY
                           |
             +-------------+-------------+
             |             |             |
          LATENCY       FREQUENCY      RESOURCE
          p95/p99       QPS / burst    rows/pages/tombstones
          SLO/failure   in-flight      CPU/disk/bytes/fan-out
             |             |             |
             +-------------+-------------+
                           |
                   BUSINESS CRITICALITY
                           |
                      Triage P0/P1/P2
                           |
                   Shortlist with owner
                           |
                Trace + server metrics
                           |
                   Testable hypothesis
                           |
              Test 1 change + A/B measure
                           |
           +---------------+---------------+
           |               |               |
        CORRECTNESS      LATENCY         CAPACITY
           |               |               |
           +---------------+---------------+
                           |
                 Canary / rollback / review
~~~

**Most important principle:** A critical query is neither simply the **slowest** query nor simply the **most frequent** query. In Cassandra, combine **latency/SLO, frequency/peak, and actual replica/table/node resource cost**, then prioritize by business impact and change safety. A CQL query with `LIMIT 50` can still scan massive tombstones, whereas an 800 QPS point lookup can remain completely efficient. **Measure the right query family → pick evidence-backed candidates → verify root cause → evaluate cluster-wide impact** is the sustainable tuning workflow.

## References

- [Apache Cassandra — Introduction to Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — query-driven modeling, partition keys, and limiting the number of partitions read.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `SELECT`, `LIMIT`, `PER PARTITION LIMIT`, `ALLOW FILTERING`, clustering ranges, and query restrictions.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — `Table.ReadLatency`, `CoordinatorReadLatency`, `SSTablesPerReadHistogram`, tombstone metrics, and `ClientRequest` metrics.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — `TRACING ON/OFF`, `PAGING`, and interactive commands.
- [Apache Cassandra — Full Query Logging](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/fqllogging.html) — bounded CQL traffic capture for analysis and replay.
- [Apache Cassandra — nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html) — SSTable, read/write, and tombstone statistics per table.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — impact of DELETE/TTL on the read path and compaction.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — session/node metrics, enabling, and scope.
- [DataStax Java Driver 4.17 — Configuration Reference](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/) — `cql-requests`, `cql-messages`, timeouts, histograms, and configuration.
- [DataStax Java Driver 4.17 — Prepared Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — bind metadata, routing keys, and query-driven optimization.
- [DataStax Java Driver 4.17 — Speculative Query Execution](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/speculative_execution/) — tail latency, extra load risks, and interaction with retries.
