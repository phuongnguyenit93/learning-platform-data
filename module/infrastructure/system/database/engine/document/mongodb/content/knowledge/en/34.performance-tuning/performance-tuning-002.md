# Identifying Bottlenecks Across Application, Query, Storage, or Network in MongoDB

An API backed by MongoDB can be slow even when the MongoDB server is operating normally. Conversely, a query may run fast in `mongosh` while application responses still take several seconds. The root cause can lie in the **application**, **MongoDB query/execution engine**, **storage**, or **network**. These layers interact: a query scanning many documents can drive I/O; high I/O causes the application's connection pool to wait; application retries then amplify server load and make the incident worse.

This lesson belongs to the **Performance Tuning** chapter of the **Database Engine Document MongoDB** module and presents a repeatable diagnostic methodology: **measure where time is actually spent, form a hypothesis, gather evidence across layers, and change something only once the real bottleneck is known**.

Contents include:

1. Distinguishing latency, throughput, saturation, queueing, and tail latency.
2. Separating time spent in the application, MongoDB driver, server-side query execution, storage, and network.
3. Using tracing, metrics, logs, MongoDB `explain`, the profiler, and observability tools.
4. Interpreting specific signals such as connection checkout wait, COLLSCAN, sort spill, WiredTiger cache pressure, disk latency, replication lag, and network RTT.
5. Investigating misleading symptoms, especially fast queries with slow APIs or high database CPU where indexes are not the culprit.
6. Examples in `mongosh` and Java Sync Driver, troubleshooting workflows, exercises, and checklists.

**Key principle:** Do not optimize based on a single metric or just because a metric name looks unusual. Prove the causal link between the metric and the latency users experience. Commands that raise profiling levels, run heavy benchmarks, or alter production indexes or configurations must follow approved operational procedures; prioritize reading metrics first and testing changes in a suitable staging environment.

## 1. What Is a Bottleneck?

A **bottleneck** is the resource or stage that limits responsiveness when the system must process additional work. A bottleneck can be CPU, disk I/O, lock contention, network links, a connection pool, a thread pool, or a specific query.

For example:

~~~text
Client
  |
  v
API Gateway
  |
  v
Application
  |-- request queue
  |-- business logic
  |-- driver connection checkout
  |-- BSON serialization
  |
  v
Network
  |
  v
MongoDB
  |-- admission/scheduling
  |-- query planning/execution
  |-- cache
  |-- storage reads/writes
  |-- locks/transactions
  |
  v
Network response
  |
  v
Application mapping/JSON
  |
  v
Client
~~~

If MongoDB executes a query in 20 ms while connection pool checkout waits 900 ms, adding another index may not improve response time at all.

### 1.1. The Bottleneck Is Not Necessarily the Resource at Highest Utilization

80% server CPU may be perfectly acceptable if the system meets its SLOs and queues are not growing. Conversely, 20% CPU can still be accompanied by severe I/O wait or network timeouts.

### 1.2. A Bottleneck Can Shift

After adding an index, data read time may drop and the next bottleneck shifts to JSON serialization, network transfer, or an external service.

### 1.3. Distinguishing Symptoms from Root Causes

| Symptom | Possible Causes |
| --- | --- |
| API p95 increases | Queueing, GC, query, I/O, network, or downstream service |
| MongoDB CPU increases | Large scans, aggregations, high QPS, compression |
| High disk utilization | Cache misses, write volume, checkpoints, backups |
| Many connections | Pool scaling, leaks, connection churn, or many app instances |
| Request timeouts | Server overload, pool wait, network, retries, tight deadlines |
| Fast MongoDB explain | API may be slow in network, pool, app, or data mapping |
| High network bytes | Large docs, unbounded results, N+1, backups, replication |
| Write latency increases | Majority replication, journaling, locks, storage, or network |

Never pick a solution from a single symptom row alone.

## 2. Four Primary Diagnostic Layers

### 2.1. Application

Includes:

- Request queue and thread/event-loop scheduling.
- Connection pool checkout and connection establishment.
- Garbage collection and memory pressure.
- BSON/JSON serialization and deserialization.
- Object/ORM mapping and business logic.
- N+1 queries and excessive database round trips.
- Retries, timeouts, and circuit breakers.
- Thread pools for HTTP, background jobs, and the driver.
- CPU processing after receiving documents.

### 2.2. MongoDB Query

Includes:

- Filters without a suitable index.
- In-memory sorts not backed by an index.
- Aggregation pipelines scanning too much data.
- High documents/keys examined relative to returned.
- Expensive `$lookup`, `$unwind`, or `$group` stages.
- Plan selection and plan cache behavior.
- Shard scatter-gather.
- Long-running transactions, contention, and write conflicts.
- High-frequency small queries.

### 2.3. Storage and MongoDB Engine

Includes:

- Data/index working set larger than available cache.
- Frequent cache misses and disk reads.
- Disk IOPS, throughput, and latency.
- Dirty pages, checkpoints, and journal.
- Compression/decompression.
- Filesystem/snapshot/backup load.
- Oplog and replication disk writes.
- Data growth, fragmentation, or insufficient headroom.

### 2.4. Network

Includes:

- Client-server round-trip time (RTT).
- Cross-region routing.
- Bandwidth and packet loss.
- DNS/SRV resolution.
- TLS handshakes and connection churn.
- Load balancers, firewalls, NAT, and proxies.
- Large response payloads.
- Retransmits and transient disconnections.

Do not equate "requests to MongoDB are slow" with "MongoDB query execution is slow."

## 3. Foundational Metrics

### 3.1. Latency

The time from when an operation starts until it completes, such as API latency or database command latency.

### 3.2. Throughput

The number of requests/operations processed per unit of time:

~~~text
requests/second
queries/second
documents/second
bytes/second
~~~

### 3.3. Utilization

Resource usage levels: CPU, RAM, disk, network, connection pool.

### 3.4. Saturation

The degree to which a resource becomes saturated, manifested through queue depth, wait time, throttling, timeouts, admission control, or dropped requests.

### 3.5. Errors

Rates of timeouts, connection errors, write conflicts, retryable errors, rejected requests, and application failures.

### 3.6. Tail Latency

P50 is the median; P95 and P99 describe the tail of the distribution. For user-facing APIs, P95/P99 often matter far more than the average.

| Metric | Hypothetical Example | Interpretation |
| --- | --- | --- |
| p50 | 30 ms | Most requests are reasonably fast |
| p95 | 700 ms | 5% of requests are slower than this threshold |
| p99 | 2,200 ms | Severe slow tail |
| Error rate | 1.5% | A fraction of requests fail |
| QPS | 4,000 | Load may be higher than baseline |

All figures are illustrative only, not measurements from any specific system.

## 4. End-to-End Latency Budget

A request can be broken down into **non-overlapping** intervals in execution order:

~~~text
Total API latency
  |
  +-- HTTP queue / dispatch
  +-- Application logic before DB
  +-- Driver connection checkout
  +-- Connection establishment if needed
  +-- Network request transit
  +-- MongoDB scheduling/query execution/storage waits
  +-- Network response transit
  +-- Driver decode / result iteration
  +-- Application mapping/JSON rendering
  +-- Other dependencies / response sending
~~~

Approximately:

\[
T_{\mathrm{API}} \approx
T_{\mathrm{queue}}+
T_{\mathrm{app}}+
T_{\mathrm{pool}}+
T_{\mathrm{connect}}+
T_{\mathrm{wire}}+
T_{\mathrm{server}}+
T_{\mathrm{decode}}+
T_{\mathrm{response}}
\]

This is a simplified model for a sequential chain. With parallel calls, retries, multiple queries, or overlapping work, use tracing to identify the **critical path**; do not blindly sum overlapping spans.

### 4.1. Example: API Slow Due to Pool

~~~text
HTTP queue:                5 ms
Business logic:           20 ms
Pool checkout wait:      780 ms
DB command RTT:           35 ms
Serialization/response:   30 ms
Total:                   870 ms
~~~

Here the first area to investigate is **connection pool checkout wait**, not indexes.

### 4.2. Example: API Slow Due to Query

~~~text
HTTP queue:                5 ms
Business logic:           10 ms
Pool checkout wait:        2 ms
DB command RTT:         1,100 ms
Serialization/response:   25 ms
Total:                 1,142 ms
~~~

Determine whether high DB command RTT comes from server execution, a large response, or the network before picking a fix.

### 4.3. Do Not Subtract the Wrong Components

Driver command monitoring measures a stage that may **include server processing and network**, yet usually excludes waiting for a connection before sending the command. It may also exclude the application consuming the rest of the cursor after the initial command. Do not equate all driver metrics with server-only execution time.

## 5. Measure the Right Unit of Work

Before turning on diagnostic tools, identify:

- The slow endpoint or business transaction.
- Tenant, request type, and input data.
- Read/write operation and query shape.
- Timestamp, traffic level, and region.
- Deployment and driver versions.
- Indexes and query options.
- SLOs for latency, throughput, and errors.

### 5.1. Query Shape Matters

Two calls to the same API can have different conditions:

~~~javascript
db.orders.find({
  tenantId: "A",
  status: "paid"
});
~~~

and:

~~~javascript
db.orders.find({
  tenantId: "A",
  status: {
    $in: ["paid", "failed", "cancelled"]
  }
});
~~~

Index selectivity and returned document counts differ. Measuring only a favorable sample easily misses slow requests.

### 5.2. Segment the Data

Inspect p95 segmented by:

- Endpoint.
- Query shape.
- Small vs. large tenants.
- Region.
- MongoDB node/cluster.
- Payload bucket.
- Cache hit/miss.
- Read concern / write concern.
- Before vs. after deploy.

### 5.3. Record a Baseline

For example:

~~~text
Endpoint: GET /orders
Baseline p95: 120 ms
Current p95: 680 ms
QPS baseline/current: 500 / 520
MongoDB command p95: 45 / 60 ms
Pool checkout p95: 10 / 480 ms
App CPU baseline/current: 45% / 90%
~~~

These hypothetical numbers point toward application/connection pool saturation rather than server queries suddenly slowing down 6x.

## 6. Hypothesis-Driven Investigation Method

A controlled cycle:

1. **Confirm the symptom:** endpoint, timestamp, p95/p99, error rate.
2. **Narrow the scope:** one service, one tenant, one region, or the whole cluster?
3. **Measure across layers:** app/driver, MongoDB, storage, network.
4. **Form a hypothesis:** e.g., pool wait is high because many operations hold cursors open.
5. **Look for disconfirming evidence:** did server command time actually increase?
6. **Test one small, reversible change.**
7. **Measure before/after under comparable load.**
8. **Document the findings and next actions.**

### 6.1. Do Not Start by Changing Indexes

Adding indexes costs storage and write amplification, and it cannot fix DNS/TLS delays or thread pool blocking.

### 6.2. Do Not Change Multiple Variables at Once

If you increase pool size, alter indexes, and scale out instances simultaneously, it becomes very hard to know which change actually helped.

### 6.3. Use Testable Hypotheses

Good:

~~~text
"More than 70% of p95 is spent in connection checkout,
and in-use connections reach maxPoolSize."
~~~

Poor:

~~~text
"MongoDB seems slow, so scale up hardware."
~~~

## 7. Application-Side Observability

Key metrics:

- HTTP request duration by route.
- Active requests and request queue length.
- Thread pool utilization.
- Event-loop lag for async runtimes.
- Heap usage, allocations, and GC pauses.
- CPU per process/container.
- Connection pool in-use / available / pending checkout counts.
- Connection creation rate.
- MongoDB command duration and errors.
- Result cursor iteration duration.
- JSON serialization time and payload bytes.
- Retries and timeout counters.

### 7.1. Tracing by Request ID

A distributed trace should show:

~~~text
traceId: abc...
  HTTP GET /orders             650 ms
    auth middleware             15 ms
    business preparation         8 ms
    mongo pool checkout        480 ms
    find command round-trip     60 ms
    cursor getMore              30 ms
    json response               40 ms
~~~

Spans must carry timestamps so sequence and overlap are visible. Real instrumentation systems may place span boundaries differently.

### 7.2. Never Log Raw Query Values Containing PII

When capturing command events, queries may contain customer details, tokens, or confidential documents. Log command name, namespace, safe query shape, duration, `traceId`, and redacted errors.

## 8. Connection Pool — A Classic Application Bottleneck

MongoDB drivers maintain connection pools to servers. An operation must **check out** a connection before sending a command.

### 8.1. Pool Too Small or Connections Held Too Long

~~~text
Max pool connections: 100
Active connections:   100
Pending checkouts:    180
Checkout p95:         700 ms
Server command p95:    20 ms
~~~

The application waits even though each command executes quickly once sent.

### 8.2. Do Not Blindly Increase maxPoolSize

High pool wait can result from:

- Too many concurrent requests generated by the application.
- N+1 queries.
- Slow cursor consumption or unclosed cursors.
- Long-running transactions.
- Thread pools holding operations too long.
- Slow MongoDB server causing connections to stay occupied.
- Traffic spikes or retry storms.

Increasing pool size may simply shift the bottleneck from the app to MongoDB, driving up connections and CPU.

### 8.3. maxPoolSize vs. maxConnecting

- `maxPoolSize` caps the configured maximum pool size.
- `maxConnecting` caps how many connections a pool can establish concurrently, depending on driver/version.

A connection storm after restart may be bound by connection/TLS creation rate rather than maximum pool size alone.

### 8.4. Wait Queue Timeout

If checkout waits past the driver's deadline, the application can time out before ever sending a query to MongoDB. The server profiler will show no corresponding executed query.

### 8.5. Reuse a Single MongoClient

In the Java Sync Driver, you should normally create a shared `MongoClient` scoped to the application lifecycle. Creating a new client per HTTP request causes connection churn, DNS/TLS overhead, and server connection pressure.

## 9. Thread Pools, Event Loops, and Blocked Applications

### 9.1. Java Thread Pool Saturation

If the API uses a bounded thread pool and all threads are blocked on I/O, incoming requests queue up. High HTTP p95 can occur before the MongoDB driver is even called.

### 9.2. Synchronous Driver on an Async Path

Calling blocking operations on an event loop inappropriately stalls other requests. Choose the right execution model: offload blocking work to worker threads or use a reactive driver when the architecture requires it.

### 9.3. Garbage Collection

Long GC pauses freeze application processing, creating p99 spikes even when MongoDB shows no corresponding spike.

Signs:

- JVM GC pause logs.
- Heap near limit.
- High allocation rates.
- Heavy JSON/BSON object mapping.
- Sudden regressions after a deploy.

### 9.4. Application-Side CPU

Encryption, compression, in-memory aggregation, JSON serialization, regexes, or heavy data mapping can saturate CPU. An API with fast DB queries will still be slow if it converts tens of MB of BSON into JSON.

## 10. N+1 Queries and Excessive Round Trips

For example, fetching 100 bookings and then running a separate query for each customer:

~~~text
1 query loads 100 bookings
100 queries load customers
--------------------------
101 database round trips
~~~

If average RTT is 5 ms and queries run sequentially, network/command overhead alone becomes substantial.

### 10.1. Symptoms

- One HTTP request triggers dozens or hundreds of MongoDB commands.
- Each command is fast, yet total API latency is slow.
- Server QPS rises much faster than business request rate.
- Driver monitoring shows many `find`/`getMore` calls.

### 10.2. Conditional Solutions

- Batch lookups using `$in` with reasonable batch sizes.
- `$lookup` when schema, indexes, and plan are appropriate.
- Embed small data frequently read together.
- Controlled caching.
- Avoid fetching unnecessary fields.

Do not cram everything into an oversized document; balance BSON size limits, update patterns, and query cardinality.

## 11. Cursors and getMore

A `find` or `aggregate` query can return a cursor in batches:

~~~text
find -> first batch
     -> getMore
     -> getMore
     -> close cursor
~~~

### 11.1. Why Is the First Command Response Fast While the API Is Slow?

The application may need many `getMore` calls to consume all results. Measuring only the initial `find` command misses all subsequent round trips.

### 11.2. Batch Size

Batch size affects round-trip count and memory/buffering. Too small increases `getMore` calls; too large increases memory and payload size. Tune for the workload.

### 11.3. Bounding Result Counts

If the API only needs 20 records, apply `limit` and proper `projection` instead of reading tens of thousands of documents and slicing in Java.

### 11.4. Closing Cursors

Unclosed cursors or retained iterators consume resources. Use try-with-resources where appropriate and avoid materializing unbounded result sets.

## 12. Retries, Timeouts, and Retry Storms

### 12.1. Retries Improve Resilience at a Cost

If MongoDB or the network slows down, aggressive automatic retries multiply load and prolong outages.

### 12.2. Symptoms

- Attempts per request increase.
- Error rate rises before throughput does.
- MongoDB ops/sec climbs despite flat user traffic.
- Pool wait and server latency rise together.
- Timeouts cluster near the same deadline.

### 12.3. Retries with Backoff and Jitter

Classify retryable errors, cap retry attempts, enforce overall deadlines, and ensure idempotency for writes. Never blindly retry non-idempotent operations.

### 12.4. Distinguishing Timeout Types

- HTTP request timeout.
- Connection checkout timeout.
- Connection establishment timeout.
- Socket read timeout.
- Server-side `maxTimeMS`.
- Transaction timeout.

All are called "timeout," yet each points to a different layer.

## 13. MongoDB Query Execution — Where to Start?

For a slow query, inspect:

1. Query shape and actual bind values.
2. Index inventory.
3. Explain plan.
4. Documents/keys examined.
5. Sort/aggregation stages.
6. Output count and payload size.
7. Corresponding server resource metrics.
8. Per-shard plans when sharded.

### 13.1. Explaining a Representative Query

~~~javascript
use rental

db.orders.find({
  tenantId: "tenant-a",
  status: "confirmed"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

### 13.2. explain Does Not Measure the Whole Application

Explain reveals server-side query planner/execution behavior. It excludes HTTP serialization, pool checkout, and full client-side network latency.

### 13.3. Load and Cache Affect Metrics

An explain on a small/cold staging dataset can differ from warm production. Document test conditions, query values, and data distribution.

## 14. Reading executionStats

Commonly useful fields:

- **nReturned**: number of documents returned at the corresponding stage.
- **totalDocsExamined**: documents examined.
- **totalKeysExamined**: index keys examined.
- **executionTimeMillis**: server execution time as measured by explain, not identical to client latency.
- **winningPlan** and stages: how the server executed the query.
- Stage-specific metrics such as sort spill/disk usage where supported by the version.

### 14.1. Inefficient Example

~~~text
nReturned         = 20
totalDocsExamined = 500000
totalKeysExamined = 0
winningPlan       = COLLSCAN
~~~

Reading 20 results while scanning 500,000 documents is likely to generate heavy load.

### 14.2. More Efficient Index Example

~~~text
nReturned         = 20
totalDocsExamined = 20
totalKeysExamined = 20
winningPlan       = IXSCAN + FETCH
~~~

Not every good query has an exact 1:1 ratio; ranges and selectivity can legitimately make `keysExamined` higher than `nReturned`.

### 14.3. Covered Queries

A query served entirely from an index can avoid `FETCH`ing documents when all queried and projected fields reside in the index under appropriate conditions. Consequently `totalDocsExamined` can be 0.

### 14.4. Do Not Compare Fields While Ignoring limit

A query with `limit 20` can stop after 20 matches; a query scanning all data to compute totals needs a different evaluation. Pick metrics according to query intent.

## 15. COLLSCAN Is Not Always Wrong

A collection scan can be reasonable when:

- The collection is very small.
- The query must read most of the data.
- No index is selective for the filter.
- The query is a batch/analytics job with a different SLA.
- Index lookup would be more expensive than a scan in that specific case.

### 15.1. When Is COLLSCAN Suspicious?

- On a large collection.
- High-frequency query.
- Returns few documents.
- CPU/disk rise alongside slow queries.
- Explain shows very high `totalDocsExamined`.

### 15.2. Do Not Index Every Single Filter

Too many indexes increase write cost, storage, and cache pressure. Design indexes around query patterns, compound predicates, sort/projection, and selectivity.

## 16. Suboptimal Indexes and Sorts

Example:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "confirmed"
}).sort({
  createdAt: -1
}).limit(20);
~~~

An index worth considering:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

**This is only a design example**, not a command to run immediately in production. Check query patterns, cardinality, write overhead, and `explain` before creating it.

### 16.1. ESR Heuristic

In many cases, ordering equality, sort, and range fields serves as a useful heuristic for compound indexes, though it is not an absolute rule for every query or data distribution.

### 16.2. Blocking Sort

If MongoDB cannot return documents in sorted order from an index, the `SORT` stage can consume memory/CPU and may spill to disk when supported by the operation and server settings.

### 16.3. Sorting Small Result Sets May Not Need a New Index

If the collection or pre-sort candidate set is small enough, adding an index may not justify its write and storage cost.

### 16.4. Verify After Changes

Compare docs examined, keys examined, latency/CPU under comparable load, and write throughput. Do not declare success merely because `IXSCAN` appears.

## 17. Aggregation Pipelines as a Bottleneck

A pipeline:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "confirmed"
    }
  },
  {
    $group: {
      _id: "$customerId",
      total: { $sum: "$amount" }
    }
  },
  {
    $sort: {
      total: -1
    }
  },
  {
    $limit: 20
  }
]);
~~~

### 17.1. Place $match Early When Valid

Shrink the candidate set before CPU/memory-heavy stages while preserving semantics and enabling planner optimizations.

### 17.2. $unwind Increases Cardinality

A document with 100 items becomes 100 intermediate records after `$unwind`. Across multiple stages, intermediate rows can be many times larger than the original collection.

### 17.3. $lookup

Can trigger many lookups or heavy reads in the foreign collection; ensure indexes exist on join keys and inspect `explain` for the actual execution path.

### 17.4. $group and $sort

Blocking stages can demand large amounts of memory or spill to disk. Check profiler/explain and resource metrics; never assume every aggregation streams.

### 17.5. allowDiskUse Is a Trade-Off

Allowing disk spill lets operations finish under memory limits, yet can shift the bottleneck to disk I/O. Do not treat it as a sole fix while ignoring pipeline design.

## 18. Query Planner and Plan Cache

MongoDB chooses plans based on query shape, indexes, data distribution, and engine/version. A previously fast plan can degrade as data changes.

### 18.1. Symptoms

- Specific query shapes suddenly slow down.
- Index inventory has not changed.
- Query values have widely varying selectivity.
- Explain/winning plan differs from baseline.
- Latency climbs after data growth or deploys.

### 18.2. Do Not Immediately Rely on Index Hints Long-Term

Hints can help test hypotheses, yet forcing a single plan may perform poorly for other query values. Identify the root cause and evaluate across representative workloads.

### 18.3. Query Plan Metrics Vary by Engine

Classic execution and Slot-Based Execution (SBE) produce different explain structures. Read stages according to your actual server version rather than writing parsers tied to one rigid JSON path.

## 19. Large Returned Payloads as a Bottleneck

A query can use the right index yet still return tens of MB of data:

~~~javascript
db.events.find({
  tenantId: "tenant-a"
});
~~~

If the API only needs ID and timestamp, use projection:

~~~javascript
db.events.find(
  {
    tenantId: "tenant-a"
  },
  {
    _id: 1,
    eventType: 1,
    createdAt: 1
  }
).limit(100);
~~~

### 19.1. A Good Index Does Not Replace Payload Reduction

The server can locate matching documents quickly yet still spend significant time reading, serializing, transmitting over the network, and parsing large fields requested by the client.

### 19.2. Pagination

Avoid unbounded responses. For large datasets, index-backed keyset pagination can outperform deep `skip`, depending on API semantics.

### 19.3. BSON Size Limit

The 16 MiB limit applies to a single BSON document, not to an entire API response. A multi-batch cursor can transfer far more bytes.

## 20. Slow Writes Are Not Caused Only by Indexes

A write passes through multiple stages:

~~~text
Application
    |
    v
Network
    |
    v
MongoDB write execution
    |
    +-- validation
    +-- document/index update
    +-- conflict/locking
    +-- journal/storage work
    +-- replication/acknowledgement policy
    |
    v
Acknowledgement to application
~~~

### 20.1. Index Overhead

Every insert/update may need to update multiple indexes. Adding indexes to speed up reads can increase write CPU and storage overhead.

### 20.2. Unique Constraints

Unique indexes enforce uniqueness checks; under high contention on a key/record, retries may occur.

### 20.3. Write Concern

Write concern determines when a write is acknowledged—for example, `w:1` vs. `majority`. Never weaken write concern solely to reduce latency at the expense of durability/consistency requirements.

### 20.4. Journal and fsync

Storage latency affects commits, checkpoints, and journaling depending on engine/settings. Inspect database and disk metrics, not just read query explains.

### 20.5. Replication Lag

If `majority` writes must wait for acknowledgements from enough members, secondary network/IO latency affects write latency. Monitor member health and lag across the topology.

## 21. Lock Contention and Transactions

MongoDB uses granular concurrency control; not every slow query is caused by a global lock.

### 21.1. When to Suspect Contention

- Many concurrent writes to the same record or key group.
- Rising write conflicts.
- Long-running transactions.
- Operations waiting on resources.
- Latency scaling up with concurrency while CPU/disk are not saturated.

### 21.2. Long-Running Transactions

They hold resources, increase cache pressure, and cause write conflicts. Keep transaction scope short and avoid external API calls inside transactions when unnecessary.

### 21.3. Safe Transaction Retries

Classify transient transaction errors and retry per driver guidance, while ensuring idempotency for any external side effects.

### 21.4. Observing Lock Metrics

`serverStatus` and `currentOp` expose lock/wait signals depending on version. Do not conclude "high locks" from a single cumulative counter without time intervals, operation mix, and baseline comparison.

## 22. MongoDB Profiler and Slow Operations

To find real slow queries, use the profiler or Atlas query insights/real-time metrics depending on deployment capabilities.

### 22.1. Checking Profiling Status

~~~javascript
db.getProfilingStatus();
~~~

### 22.2. system.profile

When profiling is enabled and recording data, inspect:

~~~javascript
db.system.profile.find(
  {},
  {
    ts: 1,
    ns: 1,
    op: 1,
    millis: 1,
    planSummary: 1,
    keysExamined: 1,
    docsExamined: 1
  }
).sort({
  ts: -1
}).limit(20);
~~~

Field names and availability depend on version and operation type.

### 22.3. Be Careful Enabling the Profiler

The following example is **only for authorized environments**—do not run it casually on production:

~~~javascript
db.setProfilingLevel(1, {
  slowms: 100
});
~~~

Profiling adds overhead, may store sensitive query details, and behaves differently across deployments, especially managed services. Consider thresholds, sampling, retention, and permissions.

### 22.4. Slow Logs Do Not Capture Every Slow Request

An HTTP request can be slow due to pool wait or network delay before the command is ever sent. Finding no slow query in the profiler does not prove the app is not slowed by database-related resource waits.

## 23. currentOp: Inspecting Active Operations

With appropriate privileges, run:

~~~javascript
db.currentOp();
~~~

Or aggregate on `admin` using `$currentOp` depending on deployment and permissions.

### 23.1. currentOp Is a Snapshot

It reflects operations currently in progress at the moment of inspection, not a complete history of finished requests.

### 23.2. Useful Questions

- Are there long-running operations?
- Are many operations running the same query shape?
- Are cursors/`getMore` holding resources?
- Are there lock waits or long transactions?
- Is an aggregation performing a massive scan?

### 23.3. Be Careful with Sensitive Data

`currentOp` output can expose command/filter values. Restrict privileges, sanitize logs/screenshots, and never retain raw customer queries indiscriminately.

### 23.4. Do Not Kill Operations Arbitrarily

Terminating operations with `killOp` can abort valid work or trigger application retries. Use it only under approved incident procedures when truly necessary.

## 24. serverStatus and MongoDB Metrics

Example:

~~~javascript
db.serverStatus();
~~~

The output contains multiple metric groups:

- `opcounters`.
- `connections`.
- Network bytes/requests.
- WiredTiger cache/transactions.
- `globalLock`/locks.
- Operation-related metrics.
- Memory/process/replication depending on configuration.

### 24.1. serverStatus Is Diagnostic Data, Not a Fixed Per-Field API

Field structures depend on MongoDB version, storage engine, and topology. Do not build dashboards rigidly tied to one static JSON example.

### 24.2. Counters Are Not Rates

A metric incrementing since process startup is not QPS. Compute the delta over a time interval:

\[
rate \approx
\frac{counter(t_2)-counter(t_1)}
{t_2-t_1}
\]

### 24.3. Inspect Per Node

Primary and secondaries carry different workloads. Looking only at cluster-level averages can hide a single bottlenecked node.

### 24.4. Atlas Metrics

When using Atlas, cluster/process charts for operation execution, disk IOPS/latency, connections, CPU, cache, and network are helpful; exact names and capabilities vary by version and tier.

## 25. Storage Engine and Working Set

MongoDB typically uses WiredTiger. Queries may read data/indexes from cache or require disk access.

### 25.1. Working Set

The portion of data and indexes actively accessed by the workload. If the working set exceeds available cache, the system must continuously fault pages in from disk.

### 25.2. Signs of Cache Pressure

- Heavy cache eviction activity.
- Rising disk reads / cache misses.
- Increasing disk read latency.
- Query p95 climbing as queried data/range grows.
- CPU may stay well below 100%.

### 25.3. Do Not Look at Cache Hit Ratio Alone

Some analytical workloads intentionally scan large volumes; cache misses are not automatically a bug requiring more RAM. Evaluate working set, query design, and storage throughput together.

### 25.4. Compression and CPU

Compression reduces disk/network bytes at the cost of CPU. If a system is CPU-bound, compression/decompression may contribute to load.

## 26. WiredTiger Cache and Eviction

Key charts can include:

- Bytes currently in cache.
- Dirty bytes.
- Pages read into cache.
- Pages written/evicted.
- Eviction activity.
- Cache pressure metrics.

Exact field names change by version; consult documentation for your exact release.

### 26.1. Is a Full Cache Always a Bottleneck?

A cache is designed to use RAM aggressively. **High cache utilization alone is not an incident.** Check eviction latency, pages read, disk I/O, and query tail latency.

### 26.2. Eviction Adds Latency

When dirty pages or cache pressure grow large, application threads may bear eviction/write costs per engine behavior. Diagnose using time-series metrics correlated with workload.

### 26.3. Do Not Resize Cache Blindly

The OS, filesystem cache, and other processes also need memory. Changing cache size can trigger swapping/OOM or shift bottlenecks; test changes under controlled conditions.

## 27. Disk IOPS, Throughput, and Latency

Three distinct metrics:

- **IOPS:** I/O operations per second.
- **Throughput:** bytes per second.
- **Latency:** time each I/O waits to complete.

### 27.1. High IOPS Does Not Automatically Mean Disk Saturation

If the disk serves those IOPS at low latency without queueing, high utilization may still be healthy.

### 27.2. Signs of a Storage Bottleneck

- Sharp rise in read/write latency.
- Growing disk queue depth.
- IOPS hitting provisioned limits.
- I/O throttling or depleted burst credits.
- Query latency rising concurrently.
- Cache misses or checkpoints coinciding in time.
- Relatively low server CPU while throughput stops scaling.

### 27.3. Storage Tier and Burst Credits

In cloud environments, disk performance can depend on volume capacity, provisioned IOPS, and burst behavior. When burst credits run out, latency spikes even at constant workload.

### 27.4. Distinguishing Bandwidth from IOPS

Many random small reads are typically IOPS-bound; file scans and large sequential operations can be throughput-bound.

## 28. Checkpoints, Journal, and Background I/O

Not all disk activity originates from user queries.

Other sources:

- WiredTiger checkpoints.
- Journaling.
- Index builds.
- TTL deletes.
- Backups/snapshots.
- Compaction/maintenance.
- Oplog writes and replication.
- Data migration/rebalancing.

### 28.1. Periodic Slowdowns

If p95 spikes periodically while QPS stays steady, inspect checkpoints, backups, scheduled jobs, or TTL sweeps.

### 28.2. Do Not Disable Backups Just Because Latency Rises

Backups are essential for recovery requirements. If they cause contention, adjust scheduling, resource provisioning, or backup strategy rather than disabling them uncontrollably.

### 28.3. Index Builds Compete for I/O

Building a large index in production can spike CPU and disk usage. Plan and monitor according to version and data size to protect SLAs.

## 29. Storage Capacity and Fragmentation

When a disk approaches full capacity:

- Write failures or lack of headroom.
- Compaction or index builds cannot run due to lack of space.
- Restore/migration becomes difficult.
- Filesystem performance degrades.
- Autoscaling cannot react fast enough.

### 29.1. dataSize Differs from storageSize

MongoDB `dataSize`, `storageSize`, `indexSize`, and filesystem usage are distinct metrics. Never extrapolate total disk usage from a single collection metric.

### 29.2. Adding Disk Alone Does Not Fix Query Design

If a query always scans millions of records, faster or larger disks may temporarily lower latency without solving the root cause.

### 29.3. Data Growth Changes the Working Set

An index that worked yesterday may still be logically valid, yet the growing working set now exceeds cache. Track growth alongside access patterns.

## 30. Replication and Secondary Bottlenecks

A replica set has a primary handling writes and secondaries receiving and replaying the oplog.

### 30.1. Majority Write Latency

If a secondary needed for majority acknowledgement has slow disk or network, write acknowledgements slow down even when primary CPU is low.

### 30.2. Secondary Reads

If the application configures read preference to secondaries, tail latency can differ across members. One overloaded secondary can slow down a subset of requests.

### 30.3. Replication Lag

Growing lag can stem from write throughput, network delays, or secondary disk/CPU saturation. Isolate the cause via per-member metrics.

### 30.4. Do Not Downgrade majority Just to Lower p95

Read/write concern are durability and consistency choices. Changing them for performance requires approval against business requirements.

## 31. Sharded Clusters and Routing

MongoDB sharding introduces:

~~~text
Application
    |
    v
mongos
    |
    +--> shard A
    +--> shard B
    +--> shard C
~~~

### 31.1. Targeted Queries vs. Scatter-Gather

If the filter includes an appropriate shard key, `mongos` can route to fewer shards. Queries lacking the shard key may broadcast across many shards.

### 31.2. Symptoms

- Many shards involved in a simple query.
- Latency equals or exceeds the slowest shard.
- High network bytes between routers and shards.
- One shard develops a hotspot.
- Migrations or balancing add I/O/network load.

### 31.3. Explain Through mongos

Run `explain` via the same router endpoint the application uses to observe target shards and execution, rather than checking only one shard directly.

### 31.4. Do Not Shard to Fix a Missing Index

Sharding adds operational complexity and potential network fan-out. First verify index/query design and the true bottleneck.

## 32. Network RTT and Geographic Distance

Latency between the application and MongoDB can be dominated by physical distance and network routing.

### 32.1. Round-Trip Count Example

Suppose RTT is roughly 70 ms and an API executes 15 sequential database commands:

\[
15 \times 70\ \mathrm{ms}=1050\ \mathrm{ms}
\]

This excludes server processing and payload transfer. This illustrates **N+1 / round-trip amplification**.

### 32.2. Co-Locating Services Near the Database

If a workload issues many database calls, placing the application in the same region or close in network topology to MongoDB typically lowers RTT—balanced against availability, compliance, and cross-region DR.

### 32.3. Do Not Equate Ping RTT with MongoDB Command Time

ICMP may be blocked or routed/prioritized differently from TCP. Use application-to-database measurements, TCP/TLS monitoring, and driver command spans to verify.

### 32.4. Cross-Region Writes

Majority acknowledgements or cross-region replicas can add latency depending on topology and write concern; do not assume all writes are always bound by the farthest replica.

## 33. Bandwidth, Packet Loss, and Retransmits

### 33.1. Large Payloads

A query returning 30 MB of data can be slow even if MongoDB locates documents rapidly, especially over bandwidth-constrained links.

### 33.2. Packet Loss

Loss and TCP retransmits make tail latency erratic. Symptoms include p99 spikes, timeouts, and reduced effective throughput.

### 33.3. Network Saturation

Outbound bytes or NIC utilization hitting limits causes queueing; inspect network metrics on app servers, routers, and database nodes.

### 33.4. Compression

Wire compression reduces bandwidth usage at the cost of CPU and requires mutual configuration/driver support. Do not toggle compression blindly before knowing whether the workload is CPU-bound or bandwidth-bound.

## 34. DNS, TLS, and Connection Establishment

A request can be slow **before a command is even sent**:

~~~text
DNS/SRV lookup
    |
    v
TCP connect
    |
    v
TLS handshake
    |
    v
Authentication
    |
    v
Connection ready
    |
    v
MongoDB command
~~~

### 34.1. Connection Churn

Creating a `MongoClient` per request repeatedly pays this entire cost. Reusing `MongoClient` lets the pool retain connections per driver policy.

### 34.2. SRV Records and DNS

`mongodb+srv` connection strings perform DNS lookups. DNS failures or slow resolvers can delay connections, though you should not conclude this from a single `nslookup`.

### 34.3. TLS Certificates

Hostname/CA mismatches or expired certificates cause errors. Inspect exact exceptions; never disable certificate validation to "speed things up."

### 34.4. Load Balancer / NAT Idle Timeouts

A proxy closing idle connections can trigger reconnects or transient errors, especially after low-traffic periods. Check middlebox timeouts and driver connection lifecycle settings.

## 35. Separating Network Latency from Server Latency

One approach is comparing:

- API latency.
- Driver checkout time.
- Driver command duration.
- MongoDB server observed operation duration.
- Response bytes.
- RTT/loss metrics.

Hypothetical example:

~~~text
API p95:                 850 ms
Pool checkout p95:         5 ms
Driver command p95:      800 ms
MongoDB server op p95:    35 ms
Response bytes:        120 KiB
Network RTT:            70 ms
~~~

A large discrepancy calls for investigating network/wire, connection behavior, cursor iteration, instrumentation differences, and server timing semantics rather than immediately declaring "network failure."

### 35.1. Compare the Same Operation

An aggregate p95 across all command events and a profiler p95 for a different query shape cannot simply be subtracted to claim `network = difference`.

### 35.2. Correlation IDs

Link requests, commands, traces, timestamps, and query shapes. Without correlation, comparing aggregates is only suggestive.

### 35.3. Time Zones and Clock Synchronization

Cross-system timestamps require UTC and clock synchronization to align incident windows. Measuring durations within a single process is usually more reliable than subtracting timestamps from two unsynchronized clocks.

## 36. Quick Decision Matrix

| Prominent Evidence | Layer to Investigate First | Further Verification Needed |
| --- | --- | --- |
| High API p95, low DB command p95, high pool wait | Application/pool | Active pool, concurrency, cursors |
| Growing API queue before calling DB | Application | Threads, CPU, GC |
| Very high totalDocsExamined, small nReturned | Query | Indexes/filters/selectivity |
| Sort spill, high aggregation memory | Query/storage | Pipeline, spills, disk metrics |
| Disk read latency and cache misses rise together | Storage | Working set, I/O limits |
| Write p95 rises alongside secondary lag | Replication/storage/network | Member metrics, write concern |
| Fast server ops, high driver command duration | Network/wire/result handling | RTT, bytes, `getMore` |
| p99 rises right after app deploy | Application/driver | Connection lifecycle, code changes |
| One tenant slower than others | Query/data skew | Cardinality, shard placement |
| Reads speed up after index, writes slow down | Index/write path | Index maintenance, write metrics |
| Slowdowns align strictly with backup schedule | Storage/background | IOPS, checkpoints, schedule |
| Continuous MongoClient creation | Application/network | TLS/DNS/connect rate |

This is a **triage priority table**, not a guaranteed diagnosis.

## 37. Java Sync Driver: Reusing MongoClient

A connection provider pattern:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoProvider {

    private final MongoClient client;

    public MongoProvider(String uri) {
        ConnectionString connectionString =
                new ConnectionString(uri);

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                connectionString
                        )
                        .build();

        this.client = MongoClients.create(settings);
    }

    public MongoClient client() {
        return client;
    }

    public void close() {
        client.close();
    }
}
~~~

### 37.1. Lifecycle

Initialize at application startup, inject/reuse the client, and close at shutdown. Do not instantiate a new client inside each HTTP handler.

### 37.2. Configuration

Pool, timeout, `readPreference`, `readConcern`/`writeConcern`, and TLS options must match workload requirements. Do not copy an oversized `maxPoolSize` across every service.

### 37.3. Never Log URIs Containing Passwords

Use a secret manager or environment variables. If diagnostics must print host/cluster info, redact usernames and passwords.

## 38. Java Sync Driver: Command Monitoring

`CommandListener` lets you observe duration and errors of database commands actually sent by the client.

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;

import java.util.concurrent.TimeUnit;

public class MongoCommandMetrics {

    public static MongoClient create(String uri) {
        CommandListener listener = new CommandListener() {

            @Override
            public void commandStarted(
                    CommandStartedEvent event
            ) {
                System.out.println(
                        "Mongo command started: "
                        + event.getCommandName()
                );
            }

            @Override
            public void commandSucceeded(
                    CommandSucceededEvent event
            ) {
                long ms = event.getElapsedTime(
                        TimeUnit.MILLISECONDS
                );

                System.out.println(
                        event.getCommandName()
                        + " succeeded in " + ms + " ms"
                );
            }

            @Override
            public void commandFailed(
                    CommandFailedEvent event
            ) {
                long ms = event.getElapsedTime(
                        TimeUnit.MILLISECONDS
                );

                System.out.println(
                        event.getCommandName()
                        + " failed in " + ms + " ms"
                );
            }
        };

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                new ConnectionString(uri)
                        )
                        .addCommandListener(listener)
                        .build();

        return MongoClients.create(settings);
    }
}
~~~

### 38.1. Emit Metrics Instead of System.out in Production

The example prints to console for API clarity. Production should export histograms/counters via a telemetry framework with sampling and without blocking hot paths.

### 38.2. Never Log Raw Commands

Command documents can hold query values, auth data, or PII. Record only safe fields like command name, namespace, and elapsed time.

### 38.3. Command Time Is Not the Entire HTTP Request

Command duration does not include pool checkout, business logic, or JSON serialization. Combine with application-level traces.

### 38.4. Multi-Batch Cursors

If a response requires `getMore`, the command listener observes multiple commands; API latency reflects the full critical path rather than just one `find` command duration.

## 39. Java Sync Driver: Application-Level Timing

Example separating database call and result consumption:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class OrderReadExample {

    public static List<Document> loadRecentOrders(
            MongoCollection<Document> collection,
            String tenantId
    ) {
        long start = System.nanoTime();

        List<Document> result =
                collection.find(
                        new Document("tenantId", tenantId)
                ).limit(100).into(new ArrayList<>());

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start
        );

        System.out.println(
                "DB find + cursor iteration: "
                + elapsedMs + " ms"
        );

        return result;
    }
}
~~~

### 39.1. Measure Cursor Iteration Properly

`find()` typically returns an `Iterable`; actual execution and fetching occur during iteration. Measuring from cursor creation through `.into(...)` captures application-level time for the full result set.

### 39.2. Combine with Driver Spans

If the application-level DB block takes 500 ms while the sum of command durations is low, investigate pool wait, iteration, transformation, or scheduling—do not assume MongoDB execution took 500 ms.

### 39.3. Benchmark with System.nanoTime

Use a monotonic clock for in-process durations instead of subtracting wall-clock timestamps from two machines that may have clock skew.

## 40. ConnectionPoolListener and Useful Events

The MongoDB Java driver supports connection pool monitoring. Relevant event types include:

~~~text
ConnectionCheckOutStarted
ConnectionCheckedOut
ConnectionCheckOutFailed
ConnectionCheckedIn
ConnectionCreated
ConnectionReady
ConnectionClosed
ConnectionPoolCleared
~~~

Exact Java class and listener method names depend on driver version; check the corresponding API docs.

### 40.1. Checkout Histogram

Measure from `checkOutStarted` to `checkedOut` or `failed` per checkout event to obtain p50/p95/p99 pool wait times.

### 40.2. Pool Sizing Applies Per Server Address

A `MongoClient` can maintain pools to multiple servers. Do not sum them all and interpret the total against a single `maxPoolSize` limit.

### 40.3. Command Monitoring Complements Pool Monitoring

If an operation waits for a connection before sending a command, `commandStarted` has not fired yet. That is a major reason both are needed.

## 41. MongoDB Profiler: Selective Slow Queries

First check status:

~~~javascript
db.getProfilingStatus();
~~~

Once data is available and read access is granted:

~~~javascript
db.system.profile.find(
  {},
  {
    ts: 1,
    ns: 1,
    op: 1,
    millis: 1,
    planSummary: 1,
    keysExamined: 1,
    docsExamined: 1
  }
).sort({
  ts: -1
}).limit(20);
~~~

Only in authorized environments, changing profiling level looks like:

~~~javascript
db.setProfilingLevel(1, {
  slowms: 100
});
~~~

### 41.1. Overhead and PII Warning

The profiler can store sensitive command details and add overhead. Managed services have their own monitoring mechanisms, and not every deployment allows identical profiler adjustments.

### 41.2. Do Not Inspect Only a Single Slow Operation

One 5-second operation running once per day may matter far less than an 80 ms query running 100,000 times per minute. Consider `latency × frequency × business criticality`.

## 42. MongoDB Explain: Index Comparison Example

Query:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "confirmed"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

Suppose initially:

~~~text
COLLSCAN
nReturned = 20
totalDocsExamined = 450000
executionTimeMillis = 850
~~~

After **evaluating and testing** a suitable compound index in an authorized environment:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

Hypothetical result:

~~~text
IXSCAN + FETCH
nReturned = 20
totalDocsExamined = 20
totalKeysExamined = 20
executionTimeMillis = 8
~~~

### 42.1. Not a Real-World Measurement

These numbers illustrate logic: fewer examined records generally reduce CPU and I/O. Real results must be measured on your system's actual data and traffic.

### 42.2. Check Write Costs

A new index adds storage and write maintenance overhead. Evaluate both read and write SLOs before keeping it.

## 43. Supporting OS and Cloud Metrics

At the host/VM/container layer, monitor:

- CPU utilization and load.
- Container CPU throttling.
- Memory / RSS / page faults.
- Disk read/write IOPS.
- Disk latency and queue length.
- Filesystem free space.
- Network throughput / errors / retransmits.
- TCP connections.
- Process restarts / OOM kills.

### 43.1. Container CPU Throttling

Container CPU limits can raise latency even when host CPU is unsaturated. Check cgroup/container metrics on your deployment platform.

### 43.2. Swap and Memory Pressure

If a host starts swapping, query latency can spike without any application code change. Do not watch only JVM heap or MongoDB cache while ignoring OS memory.

### 43.3. Disk Burst Credits

In cloud environments, disk throttling can kick in after sustained load; slowdowns do not always appear immediately when traffic rises.

### 43.4. Do Not Measure One Node and Generalize to the Cluster

In a replica set or sharded cluster, a single shard or secondary may have isolated slow I/O. Dashboards must allow per-node breakdown.

## 44. Load Testing to Identify Saturation

Run load tests **in an authorized environment**, stepping up load gradually:

~~~text
100 RPS
  |
  v
200 RPS
  |
  v
400 RPS
  |
  v
600 RPS
~~~

Observe actual throughput, p50/p95/p99 latency, errors, queue depth, CPU, disk, connections, and network.

### 44.1. Saturation Curve

~~~text
Load increases -> throughput increases nearly linearly
Load continues to increase -> throughput begins to flatten
Load increases further -> latency/queue/errors rise rapidly
~~~

When throughput stops climbing while latency rises, you have typically hit a resource limit or throttling mechanism.

### 44.2. Generate Realistic Load

Include production-like read/write mix, document sizes, tenant skew, concurrency, batch sizes, and cache behavior. A local loop firing the same tiny query does not represent production.

### 44.3. Protect Infrastructure

Never use load tests to "probe" a struggling production cluster without approval and strict risk bounds.

## 45. Little's Law and Queueing

A useful relationship for relatively steady systems:

\[
L = \lambda W
\]

Where:

- L is the average number of work items in the system.
- \(\lambda\) is throughput (items/second).
- W is the average time an item spends in the system.

### 45.1. Example

If throughput = 200 requests/s and average latency = 0.2 s:

\[
L = 200 \times 0.2 = 40
\]

On average, roughly 40 requests are in the system.

### 45.2. Diagnostic Application

If throughput stops increasing while waiting requests climb, W must be rising or the system has left steady state. Queue growth signals saturation.

### 45.3. Do Not Apply Little's Law to an Arbitrary Snapshot

The law holds under steady-state assumptions and consistent measurement boundaries. Do not multiply p95 latency by average arrival rate and call it exact L.

## 46. Case Study A — Application Slow Due to Pool

**Hypothetical symptoms:**

~~~text
API p95:             950 ms
MongoDB command p95:  25 ms
Pool checkout p95:   790 ms
DB CPU:               35%
Disk latency:         low
~~~

### 46.1. Hypothesis

Connections are being held too long or concurrent operations exceed pool/application capacity.

### 46.2. Verification Steps

- Active/in-use connections.
- Pending checkout queue.
- Long-running cursors/transactions.
- Number of `MongoClient` instances created.
- Thread pool utilization and retry counts.
- Post-deploy load spikes.

### 46.3. Remediation Options Depending on Findings

- Reuse `MongoClient`.
- Close cursors properly.
- Eliminate N+1 queries.
- Enforce concurrency limits / backpressure.
- Tune pool size with benchmarking while watching server impact.

**Don't:** create random indexes or upgrade disk IOPS without evidence.

## 47. Case Study B — Query Scanning the Collection

**Hypothetical symptoms:**

~~~text
API p95:               2.0 s
MongoDB command p95:   1.8 s
Server CPU:             95%
Disk latency:           normal
Explain: COLLSCAN
Docs examined:          900000
Docs returned:          15
~~~

### 47.1. Hypothesis

The query lacks a suitable index/filter, causing a CPU-intensive scan.

### 47.2. Verification Steps

- Query shape and selectivity.
- Required sort/projection.
- Current indexes.
- Explain on representative values.
- Execution frequency and write overhead.

### 47.3. Experiment

Evaluate a suitable compound index in an authorized environment, measuring docs examined, CPU, p95, and write latency.

### 47.4. Do Not Watch CPU Alone

High CPU is a possible consequence of a scan, but `explain` is needed to confirm the actual plan.

## 48. Case Study C — Storage/Cache Pressure

**Hypothetical symptoms:**

~~~text
Query p95:               1.2 s
Docs examined:           200
Server CPU:              40%
Disk read latency p95:   90 ms
Cache misses:            increased
IO queue depth:          high
Working set:             larger than effective cache
~~~

### 48.1. Hypothesis

The query must read many pages from disk due to working set/caching behavior, or the disk has hit IOPS/throughput limits.

### 48.2. Verification Steps

- WiredTiger cache and eviction trends.
- Disk read/write IOPS and latency.
- Filesystem free space.
- Backup/checkpoint/index build timing.
- Data/index growth.
- Read pattern per query.

### 48.3. Remediation Directions

- Optimize queries to touch less data.
- Use projections/covered indexes where beneficial.
- Evaluate RAM/cache/storage tier sizing for the workload.
- Schedule/throttle background I/O.
- Review scaling architecture.

**Don't:** blindly increase `maxPoolSize`, since checkout waits may simply be a symptom of slow I/O.

## 49. Case Study D — Network / Cross-Region

**Hypothetical symptoms:**

~~~text
API p95:                820 ms
Pool checkout p95:       5 ms
Server operation p95:   12 ms
Driver command p95:    150 ms
API DB calls:            5 sequential calls
RTT:                    70 ms
Network loss:            occasional
~~~

### 49.1. Hypothesis

Multiple sequential round trips and a distant/unstable network consume substantial time.

### 49.2. Verification Steps

- Service and database regions.
- Routing path, TCP/TLS metrics.
- Payload sizes.
- Number of sequential commands.
- DNS/connection churn.
- Differences between driver and server timing.

### 49.3. Remediation Directions

- Eliminate N+1 calls.
- Batch operations.
- Co-locate service and database when appropriate.
- Reuse connections.
- Optimize payload/projection.
- Investigate packet loss and routing.

Do not sum separate p95 latencies into an absolute total; measure the critical path with tracing.

## 50. Case Study E — Writes Slow Due to Replication

**Hypothetical symptoms:**

~~~text
Read p95:                  40 ms
Majority write p95:       700 ms
Primary CPU:               45%
Secondary disk latency:  high
Replication lag:         growing
~~~

### 50.1. Hypothesis

One or more secondaries are I/O- or network-bound, delaying replication and majority acknowledgements.

### 50.2. Checks

- Replica member health.
- Lag per member.
- Effective write concern.
- Secondary disk/CPU/network.
- Oplog behavior.
- Secondary read load and backups.

### 50.3. Remediation

Fix the constrained member, storage, network, or sizing; do not weaken write concern just to hide latency if the application requires majority durability.

## 51. Case Study F — N+1 Queries After Deploy

**Hypothetical symptoms:**

~~~text
Before deploy: 3 Mongo commands / HTTP request
After deploy:  120 Mongo commands / HTTP request
Each command p50: 4 ms
API p95: 900 ms
MongoDB QPS increased 30x
~~~

### 51.1. Hypothesis

A code change switched from batch fetching to querying each related entity individually.

### 51.2. Verification Steps

- Distributed traces.
- Driver commands per request.
- Query shapes.
- ORM/mapping code.
- Latency vs. request payload cardinality.

### 51.3. Solution

Batch lookups or adjust the data model/query path, then measure API latency and QPS. Increasing the connection pool only masks the symptom.

## 52. Case Study G — Slow API Despite Fast Explain

**Hypothetical symptoms:**

~~~text
MongoDB explain execution:     5 ms
Driver first find command:    12 ms
Cursor total read:           500 ms
JSON response:               300 ms
API total:                  850 ms
Response payload:            18 MB
~~~

### 52.1. Hypothesis

The issue lies in returned data volume, `getMore`, mapping/serialization, and network transfer—not filters or indexes.

### 52.2. Verification Steps

- Number of documents returned.
- Projection.
- Batch size / `getMore` count.
- Payload bytes.
- JSON serialization timings.
- Client bandwidth.
- Pagination semantics.

### 52.3. Remediation Directions

Apply limits/pagination, projections, streaming where suitable, controlled compression, and avoid building massive JSON payloads in memory.

## 53. Practical Incident Triage Workflow

A runbook table:

| Step | Action | Evidence |
| --- | --- | --- |
| 1 | Confirm p95/p99/errors and timeframe | Dashboards/traces |
| 2 | Identify route/query/tenant/region | Request metadata |
| 3 | Compare app wait / driver command / server time | Trace spans |
| 4 | Inspect pool/threads/GC/retries | App metrics |
| 5 | Inspect slow operations/explain | MongoDB metrics |
| 6 | Inspect CPU/cache/disk/replication | Server/cloud metrics |
| 7 | Inspect RTT/packet loss/payload/TLS | Network metrics |
| 8 | Choose one hypothesis and experiment | Hypothesis note |
| 9 | Test a reversible change | Change record |
| 10 | Measure before/after at comparable load | SLO comparison |
| 11 | Document root cause and corrective actions | Incident report |

### 53.1. Use Synchronized Time Windows

Do not compare app p95 from 09:00–09:10 with server disk IOPS from 10:00–10:10. Time alignment is the bare minimum requirement.

### 53.2. Distinguish Correlation from Causation

Disk latency and API latency rising together is a clue, but confirm whether the queries actually read from disk, check load levels, and rule out other factors.

### 53.3. Monitor After Remediation

A change can improve p50 while worsening p99 or write throughput. Watch all relevant SLOs and resource budgets.

## 54. Anti-Patterns to Avoid

| Bad Practice | Why It Is Wrong |
| --- | --- |
| API is slow -> immediately create an index | Bottleneck may be pool/network/app |
| Cache usage is high -> add RAM | High cache usage is often normal |
| Many connections -> raise `maxPoolSize` | May overload the server further |
| Using only `mongosh` explain for API latency | Omits app/pool/network/serialization |
| Watching only average latency | Hides p95/p99 spikes |
| Subtracting p95s from different sets | Does not measure the same critical path |
| Leaving high-level profiling on long in prod | Overhead and PII exposure |
| Running unbounded load tests | Causes real outages |
| Weakening write concern to improve p95 | Alters durability semantics |
| Disabling TLS to "go faster" | Security risk |
| Lowering `maxTimeMS` arbitrarily | Turns slowness into errors without fixing root cause |
| Treating every `COLLSCAN` as a bug | Scans can be appropriate |
| Creating too many indexes | Increases storage/write overhead |
| Ignoring query shape / tenant skew | Unrepresentative evaluation |
| Not measuring `getMore` | Misses most cursor time |
| Creating a `MongoClient` per request | DNS/TLS/connection churn |
| Unlimited retries | Retry storms |
| Ignoring secondary metrics | Misses replication bottlenecks |
| Treating `serverStatus` counters as rates | Wrong units |
| Ignoring disk burst credits | Misses throttling |
| Measuring only one node/shard | Hides hotspots |
| Changing multiple variables at once | Cannot isolate root cause |
| No rollback plan | Hard to recover from bad tuning |

## 55. Exercises: Classifying Bottlenecks

### Exercise 1 — Pool Wait

HTTP p95 = 900 ms, checkout wait p95 = 750 ms, DB command p95 = 20 ms. Which layer should be investigated first? Which metrics confirm it?

### Exercise 2 — Query Scan

Explain shows `nReturned=10`, `totalDocsExamined=800000`, `COLLSCAN`, high CPU. Outline steps to design and validate an index.

### Exercise 3 — Storage

P95 rises alongside disk read latency and cache misses, yet server CPU is 30%. Why might adding CPU instances fail to help?

### Exercise 4 — Network

Application is in region A, database in region B, RTT is 80 ms, and one request executes 12 sequential commands. Estimate the minimum RTT component in an ideal model and suggest ways to reduce it.

### Exercise 5 — Large Payload

Explain takes 6 ms, yet the API returns 25 MB and takes 1 second. Propose how to measure cursor/`getMore`, serialization, and network time.

## 56. Exercises: MongoDB Queries

### Exercise 6 — Filter + Sort

Given a `find` query filtering by `tenantId`/`status`, sorting by `createdAt` descending, `limit 20`. Propose a compound index and explain when the index would not help.

### Exercise 7 — Aggregation Spill

A `$group`/`$sort` spills to disk. Compare placing `$match` early, reducing cardinality, tuning indexes, and using `allowDiskUse`.

### Exercise 8 — $lookup

An aggregation joining `customers` by `customerId` is slow. How do you check foreign indexes, cardinality, and explain?

### Exercise 9 — Sharding

A query on a sharded collection without the shard key causes scatter-gather. How do you identify this using `explain` via `mongos`?

### Exercise 10 — Covered Query

A query has `docsExamined=0` and `keysExamined=100`. What does this indicate? Is it guaranteed to be fast end-to-end?

## 57. Exercises: Application and Driver

### Exercise 11 — MongoClient Lifecycle

In a Java API, each request creates a new `MongoClient`. What are the consequences for connections, TLS, DNS, and latency? Design a proper lifecycle.

### Exercise 12 — Command Events

Write a `CommandListener` that logs `commandName`, duration, and success/failure without logging raw queries containing PII.

### Exercise 13 — Pool Events

Design a histogram for checkout wait, distinguishing checkout timeout from server `maxTimeMS` timeout.

### Exercise 14 — Cursors

A `find` returns 10,000 documents across multiple batches. Why is measuring only the initial `find` command duration insufficient?

### Exercise 15 — GC

API p99 spikes after a deploy, heap allocations and GC pauses increase, while the MongoDB profiler shows no change. How do you confirm the root cause?

### Exercise 16 — N+1

An endpoint issues 1 `find` + 100 per-customer queries. Propose batching/`$lookup`/schema changes and compare round trips.

## 58. Exercises: Storage, Replication, and Network

### Exercise 17 — Majority Writes

Read p95 is normal, majority write p95 increases, and secondary disk latency is high. How do you investigate the topology?

### Exercise 18 — Disk IOPS

IOPS hits the provisioned limit, disk queue grows, and latency rises. Contrast upgrading the storage tier with optimizing query patterns.

### Exercise 19 — Backup Contention

Latency spikes only during backup windows. What metrics and safe mitigations should be considered?

### Exercise 20 — DNS/TLS

Requests are slow right after app restarts, connections created/sec spike, and TLS handshakes are slow. What should you investigate before adding indexes?

### Exercise 21 — Container Throttling

Host CPU is 50%, yet the container experiences CPU throttling. Why can the app be slow despite low database CPU?

### Exercise 22 — Packet Loss

MongoDB server operations are fast while client p99 is very high and network retransmits increase. How do you gather correlated evidence on the same trace?

## 59. Exercises: Measurement and Decision-Making

### Exercise 23 — Latency Budget

A request consists of queue=10ms, logic=20ms, pool=300ms, command=40ms, serialization=30ms. What is the approximate total if sequential? When does simple addition not apply?

### Exercise 24 — Little's Law

Throughput is 250 requests/s, average latency is 0.2s. Estimate the average number of requests in the system. What assumptions apply?

### Exercise 25 — Before/After SLOs

After adding an index, API p95 drops 20% while write p99 jumps 300%. Should you accept the change? What additional data do you need?

### Exercise 26 — Causal Experiment

Design an experiment distinguishing query scan latency from network latency, ensuring only one variable changes with a rollback plan.

### Exercise 27 — Incident Timeline

App p95 spikes at 09:10; Atlas disk latency rises starting at 09:30. Can you conclude disk caused the initial issue? Why is aligning time windows essential?

### Exercise 28 — Metric Mismatch

Profiler query p95 is 30 ms and driver command p95 is 200 ms, but they cover different query shapes. Why can you not conclude network = 170 ms?

### Exercise 29 — Retry Amplification

Traffic is 300 RPS, and each request retries 2 times on average upon errors. How does database QPS change if every attempt sends a command? Design backoff and caps.

### Exercise 30 — Runbook

Draft a runbook categorizing application queue, pool, explain, cache/disk, replication, and network, including required evidence and stop conditions.

## 60. Performance Diagnostics Checklist

### Problem Definition

1. Confirmed affected endpoint, SLO, and incident timeframe.
2. Collected p50/p95/p99, throughput, and error rate.
3. Segmented by tenant/query/region and payload.
4. Established a pre-incident or pre-deploy baseline.
5. Have correlation IDs/traces linking app to database.
6. Not logging secrets or PII.

### Application

7. Measured HTTP queue and thread/event-loop delay.
8. Measured CPU, heap, GC pauses, and throttling.
9. Measured `MongoClient` / pool checkout wait.
10. Checked connection churn and DNS/TLS overhead.
11. Checked N+1 queries, retries, and timeouts.
12. Measured cursor/`getMore` and result mapping.
13. Measured response serialization and payload bytes.

### MongoDB Queries

14. Inspected query shape/plan with `explain`.
15. Compared `nReturned`/`docsExamined`/`keysExamined`.
16. Checked sort, `$lookup`, `$group`, `$unwind`, and spills.
17. Verified index definitions, field order, partial filters, and collation.
18. Considered plan cache and selectivity variance.
19. Checked query frequency, not only single slow queries.
20. Checked write concern, transactions, and contention.
21. For sharding, checked `mongos` targeting.

### Storage/Cluster

22. Checked WiredTiger cache, eviction, and data growth.
23. Checked disk IOPS, throughput, latency, queue/burst credits.
24. Checked checkpoint/backup/index-build timing.
25. Checked filesystem capacity and headroom.
26. Checked primary/secondary CPU, disk, and replication lag.
27. Distinguished per-node metrics from cluster averages.

### Network

28. Verified app/database regions and routing path.
29. Measured RTT, packet loss, and retransmits.
30. Checked bandwidth and response payloads.
31. Checked DNS, TLS, proxies, NAT, and reconnect behavior.
32. Did not rely on ICMP ping as sole evidence.

### Remediation and Verification

33. Every change has a hypothesis and expected outcome.
34. Operating within an authorized test environment and boundaries.
35. Have a rollback plan.
36. Avoid changing multiple variables at once unless necessary.
37. Measure before/after on a representative workload.
38. Evaluate read/write latency, throughput, errors, and cost together.
39. Record root cause with supporting evidence and conclusion limits.
40. Set up monitoring/alerts to catch regressions.

## 61. Sample Investigation Report Template

~~~yaml
incidentId: PERF-2026-11-14-01
affectedEndpoint: GET /orders
environment: example-staging
startUtc: "2026-11-14T09:10:00Z"
symptom:
  apiP95Ms: 850
  baselineApiP95Ms: 120
  qps: 500
observations:
  poolCheckoutP95Ms: 600
  driverCommandP95Ms: 60
  mongoQueryPlan: IXSCAN
  docsExamined: 25
  serverCpuPct: 40
  diskLatencyMs: 3
  networkRttMs: 5
hypothesis:
  description: "App pool saturated by too many concurrent reads"
  confidence: "needs verification"
experiment:
  change: "Reduce per-request N+1 operations on staging"
  successMetric: "pool checkout wait and API p95 drop"
rollback: "Restore old request path"
result: "PENDING"
owner: "service-team"
~~~

Sample figures do not describe a real environment. A good report separates **observations**, **hypotheses**, **experiments**, and **conclusions**.

## 62. Conclusion

Diagnosing slow MongoDB performance should not begin with "Which index should I create?" but rather **"Where is time actually being spent, under what load, and what evidence links the root cause to the symptom?"**.

- If HTTP p95 is high while MongoDB commands are fast, inspect application queues, connection pools, N+1 calls, cursors, GC, and serialization.
- If server query time is high and `explain` shows heavy scanning, evaluate filters, indexes, sorts, and aggregations.
- If latency rises with disk wait and cache misses, inspect WiredTiger working set, storage IOPS/throughput, checkpoints, and background workloads.
- If driver time exceeds server time for the same request, examine network RTT, connection establishment, result payloads, `getMore`, and measurement boundary differences.
- If writes are slow, do not overlook replication, write concern, transaction conflicts, and secondary disk/network health.
- If a sharded cluster suffers scatter-gather or hotspots, examine routing and shard keys before simply scaling up hardware.

**A bottleneck is confirmed when there is solid evidence of queueing, saturation, or excessive work at a specific layer; an optimization is only validated when it improves real SLOs without unacceptable regressions in correctness, durability, or another resource layer.**

## References

- [MongoDB Manual — Analyze Query Performance](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — db.currentOp](https://www.mongodb.com/docs/manual/reference/method/db.currentOp/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — WiredTiger](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — Replication](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Atlas — Monitor Cluster Metrics](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/)
