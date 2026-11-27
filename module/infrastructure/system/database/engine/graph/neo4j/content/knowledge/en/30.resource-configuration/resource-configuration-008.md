# Validating Configuration Changes with Metrics Instead of Blindly Adding Resources in Neo4j

## 1. The Problem: Slow Queries Do Not Automatically Mean the Server Lacks RAM

Neo4j stores a **property graph** of nodes, relationships, and properties; applications use Cypher to traverse paths, locate related entities, aggregate results, and update the graph. Neo4j can run slowly for many reasons: a query traversing too many relationships, an undersized page cache, JVM garbage collection (GC) pauses, transactions waiting on locks, disk bottlenecks, or the Java Driver waiting for connections.

Suppose a supply-chain API returns suppliers per product. p95 response time climbs from 120 ms to 900 ms as order volume grows. Someone proposes:

> "Raise JVM heap from 8 GiB to 24 GiB, page cache from 12 GiB to 24 GiB, and Bolt thread pool to 800—that will make it fast."

This proposal **lacks evidence**. If Neo4j runs on a 32 GiB machine, allocating 24 GiB heap and 24 GiB page cache simultaneously is impossible once OS, native memory, and other processes are counted. And if the root cause is an `Expand(All)` producing millions of rows or transactions contending on a single lock, adding heap will not magically optimize the query.

**Principle of the "Resource Configuration" chapter: every change must start from a testable hypothesis with a baseline, output metrics, test conditions, acceptance thresholds, and a rollback plan.**

This lesson covers:

1. Distinguishing the **resource regions** used by Neo4j and the Java Driver.
2. Establishing a **baseline** and a representative metric suite.
3. Reading bottleneck signals across query plans, page cache, GC, CPU, I/O, transactions, and Bolt.
4. Designing experiments that change **one variable at a time**, comparing before and after properly.
5. Walking through evaluations of heap, page cache, transaction limits, and thread pools—including how to decide **not** to raise limits.
6. Applying the workflow across self-managed hosts, containers/Kubernetes, Neo4j Enterprise, and AuraDB.

> Setting names below follow current Neo4j 5.x/2025–2026 conventions. Verify via `SHOW SETTINGS` and documentation for your **exact version and edition**; never reuse Neo4j 4.x setting names in new configurations.

## 2. Distinguish Resources Before Optimizing

### 2.1. Memory Consumption Model

```text
Physical RAM or container memory limit
|
+-- Neo4j process (JVM)
|   |
|   +-- JVM heap
|   |   +-- Objects, query/transaction state
|   |   +-- Cypher runtime and aggregation/sorting
|   |   +-- GDS projected graphs (if Graph Data Science is installed)
|   |   +-- Query/plan caches and GC headroom
|   |
|   +-- Page cache (off-heap / outside Java heap)
|   |   +-- Data store and native indexes
|   |
|   +-- Native/direct memory
|       +-- Network buffers, metaspace, thread stacks, JVM overhead
|
+-- Operating system / filesystem / other processes
    +-- Kernel, container runtime, monitoring, agents, etc.
```

| Region | Settings or Monitoring | Purpose | Common Misconceptions |
| --- | --- | --- | --- |
| **JVM heap** | `server.memory.heap.initial_size`, `server.memory.heap.max_size`; JVM/GC metrics | Java objects, query/transaction state, certain plugins | Not total Neo4j RAM |
| **Neo4j page cache** | `server.memory.pagecache.size`, hit ratio, page faults | Caches graph data and native indexes to avoid disk reads | Not JVM heap; gives diminishing returns when hit ratio is already high |
| **Transaction memory** | `dbms.memory.transaction.total.max`, `db.memory.transaction.total.max`, `db.memory.transaction.max` | Caps memory consumed by transactions | Does not create extra RAM; overly low limits can abort queries |
| **Native/JVM overhead** | RSS, metaspace, direct buffers, thread stacks | Off-heap space required for Neo4j to run | Does not disappear when you shrink heap |
| **I/O and storage** | IOPS, throughput, latency, checkpoint duration, page faults | Data reads/writes, flushes, checkpoints, transaction logs | `DB Hits` do not equal physical disk reads |
| **CPU and threads** | Process/host CPU, run queue, Bolt thread pool | Cypher execution, concurrency, GC, planning | More threads do not create more CPU |
| **Java client** | Connection pool, request latency, heap, GC, wait time | Submits Cypher and consumes results | Growing the client pool does not speed up server query execution |

**View resources as a single coupled system.** Raising heap can shrink RAM available for page cache; raising query concurrency can push up CPU/GC and I/O together. Optimize **the entire request path**, never one metric in isolation while ignoring side effects.

### 2.2. Recommendation Tools Do Not Replace Benchmarks

On self-managed Neo4j, you can generate an initial suggestion:

```bash
bin/neo4j-admin server memory-recommendation --memory=32g
```

This command outputs a **heuristic** heap/page-cache split assuming a given RAM allocation for Neo4j. It has no full knowledge of degree distributions, query selectivity, p99 targets, transaction concurrency, or concurrent GDS jobs. Never treat its output as the final optimal configuration.

In Docker/Kubernetes, pass the **actual container/pod memory limit**, not host RAM. If a pod is limited to 16 GiB, never apply a recommendation computed for a 64 GiB host. If a Java app, monitoring agents, or multiple Neo4j instances share the machine, subtract their budgets first.

## 3. Start with Measurable Targets, Not Machine Sizes

### 3.1. Define SLOs and Comparison Scope

Example use case: endpoint `GET /suppliers/{id}/products`.

| Factor | Example Target | How to Verify |
| --- | --- | --- |
| **Correctness** | SKU list and ordering remain unchanged by tuning | Compare results, counts, and keys before and after |
| **p95 latency** | Under 250 ms at 100 requests/s | Measure end-to-end requests across multiple windows |
| **p99 latency** | Under 500 ms | Track tail latency, not just averages |
| **Throughput** | Sustains at least 100 requests/s | No climb in errors/timeouts at target load |
| **Error rate** | Under 0.1% across test runs | Track timeouts, transaction failures, pool errors |
| **Resources** | Zero OOMs, zero swap, GC/CPU/I/O within safe limits | JVM, host/container, query logs, metrics |
| **Stability** | Steady over sustained runs and peak load | Compare multiple windows, not a single request |

**Values like 250 ms, 500 ms, and 100 requests/s are illustrative self-defined SLOs**, not Neo4j standards. A 10-minute reporting job or overnight batch import has completely different targets from an interactive API.

### 3.2. Measuring p95, p99, and Throughput Correctly

- **p95 latency**: 95% of measured requests finish at or below this value; never replace p95 with an average.
- **p99 latency**: sensitive to GC pauses, queueing, lock contention, and traffic spikes.
- **Throughput**: number of **successfully completed** requests per second, not just requests sent.
- **Error rate**: fraction of failing requests; a configuration that responds faster only by returning more timeouts/503s is **not an improvement**.
- **Offered load** vs. **achieved throughput**: a load generator sending 200 req/s while the server completes 120 req/s indicates saturation/queueing, not 200 req/s throughput.

Collect CPU, memory, GC, and I/O during the **same time window**. Never compare off-peak p95 with peak-hour p95 and credit the difference to configuration changes.

## 4. Capturing a Baseline: Four Metric Layers

### 4.1. Java/Spring Application Layer

Record at minimum:

1. Request rate and end-to-end p50/p95/p99 of the endpoint.
2. Neo4j call duration alone, serialization/response time, and payload size.
3. Number of Neo4j queries per HTTP request (detecting **N+1** patterns).
4. Timeouts, retries, transaction failures, and connection acquisition wait times.
5. Application JVM heap/GC, especially when materializing large lists with `Result.list()`.

If a Spring Data Neo4j app hydrates an entire relationship-rich entity graph just to read two properties, fixing the **read query/DTO** can help far more than growing database heap.

### 4.2. Cypher Query Layer

Use `EXPLAIN` to inspect the plan **without executing**, and `PROFILE` to measure an **actually executed query**:

```cypher
EXPLAIN
MATCH (s:Supplier {supplierId: $supplierId})-[:SUPPLIES]->(p:Product)
WHERE p.active = true
RETURN p.sku AS sku, p.name AS name
ORDER BY sku
LIMIT $limit;
```

```cypher
PROFILE
MATCH (s:Supplier {supplierId: $supplierId})-[:SUPPLIES]->(p:Product)
WHERE p.active = true
RETURN p.sku AS sku, p.name AS name
ORDER BY sku
LIMIT $limit;
```

**Note:** this is an illustrative pattern for a graph with `Supplier`/`Product` labels and `SUPPLIES` relationships; running it requires matching data, parameters, and privileges. Operators to watch for:

| Plan Signal | Possible Interpretation | Investigation Direction |
| --- | --- | --- |
| `NodeByLabelScan` on a huge label | No selective entry point or planner deems scan cheaper | Check indexes/constraints, predicates, and cardinality |
| `Expand(All)` producing huge `Rows` | High fan-out from a `Supplier` node | Constrain type/direction, limit traversal scope, or redesign query |
| `Filter` discarding most rows after expand | Late filtering | Start from a more selective indexed anchor |
| `CartesianProduct` | Two candidate sets multiplied row-by-row | Check pattern for unintended disconnected branches |
| `Sort`/`EagerAggregation` on huge inputs | High CPU/heap cost | Consider indexes, pre-filtering, or read models |
| High `DB Hits` | Many storage engine operations | Do not equate directly to disk I/O; correlate with page faults |
| `Estimated Rows` far off from `Rows` | Cardinality estimates misrepresent data | Check data skew, stats, plan, and parameters |

**Never run `PROFILE` on write queries in production just to "preview": it actually executes `CREATE`/`MERGE`/`SET`/`DELETE`.** Use `EXPLAIN` or a controlled test environment.

### 4.3. Neo4j DBMS Layer

Where privileges and monitoring features permit, track:

| Group | Metrics / Signals | When Suspect |
| --- | --- | --- |
| Page cache | Hit ratio, usage ratio, page faults/s, evictions/s, bytes read | Sustained drop in hits with rising faults and disk I/O |
| JVM heap | Heap used/committed/max, GC time/pauses, allocation rate | High GC time, old-gen pressure, near OOM |
| Transactions | Active transactions, `estimatedUsedHeapMemory`, lock/wait time | Long transactions, lock waits, memory limits hit |
| Bolt | Connection/thread counts, pool utilization, rejected jobs | Worker exhaustion, long-held connections/transactions |
| CPU | CPU busy, run queue, CPU quota/throttling | CPU maxed out while throughput stalls |
| Storage | Disk utilization, IOPS, await, throughput, checkpoint duration | Rising I/O latency, checkpoints contending with writes |
| Reliability | Errors, timeouts, OOMs, restarts, transaction terminations | Spikes appearing after a config change |

Official metrics—including CSV/JMX/Prometheus metrics—are documented by Neo4j for **Enterprise Edition**. Do not assume Community or Aura exposes identical endpoints, metric names, or config rights. On Community, you can still measure OS/JVM/app metrics and run `EXPLAIN`/`PROFILE` when authorized; on Aura, use the consoles and metrics exposed by your service tier.

**A high page-cache hit ratio is generally good**, and Neo4j docs cite ~98–100% as a reference zone for well-fitted workloads. Yet it is a **diagnostic indicator**, not proof that a query is optimal. A 99.9% cache hit ratio with huge `DB Hits`/`Rows` can still be slow.

### 4.4. OS / Container Layer

Beyond Neo4j memory, record:

- Allocated RAM, resident set size (RSS), swap activity, and OOM killer events.
- CPU cores/CPU quota, CPU throttling, load average or run queue.
- Disk read/write latency, IOPS, utilization, filesystem, and free space.
- Network RTT between the Java service and Neo4j, connection errors, and retransmissions if any.
- Other instances or non-Neo4j processes sharing the same host.

A host with 64 GiB RAM running a Neo4j container capped at 16 GiB can still hit a container OOM while the host reports plenty of free RAM.

## 5. Enabling Appropriate Observability and Checking Effective Configuration

### 5.1. Viewing Active Settings

On **self-managed Neo4j**, with appropriate privileges:

```cypher
SHOW SETTINGS
YIELD name, value, isDynamic
WHERE name IN [
  'server.memory.heap.initial_size',
  'server.memory.heap.max_size',
  'server.memory.pagecache.size',
  'dbms.memory.transaction.total.max',
  'server.bolt.thread_pool_max_size'
]
RETURN name, value, isDynamic
ORDER BY name;
```

`SHOW SETTINGS` reflects values on the **server executing the statement**; in a cluster, querying one member does not prove other members share identical settings. Per the current Operations Manual, this command is unavailable on Aura.

**Never log passwords or secrets in configuration reports.** Any setting touching endpoints or credentials must be handled as sensitive operational data.

### 5.2. Neo4j Enterprise: Using the Query Log for Investigation

In Enterprise with an approved change process, you can configure `neo4j.conf`:

```properties
# Example slow-query observation config, NOT a default preset.
db.logs.query.enabled=INFO
db.logs.query.threshold=200ms
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
```

Here `INFO` logs queries exceeding the threshold; `VERBOSE` logs query start and end regardless of threshold. Pick a threshold aligned with your SLOs and avoid logging sensitive data. Logging every query/plan on a high-throughput system can bloat logs and add overhead. Specifically, `db.logs.query.plan_description_enabled=true` carries extra cost and is **not suited to leaving enabled permanently**.

Query logs can report **elapsed time, planning time, waiting time, page hits/faults, and allocated bytes** depending on config and version. Analyze logs by **specific query** and time window; never blend distinct query plans into one aggregate summary.

### 5.3. Dynamic Settings Are Not Permanent Configuration

In Neo4j Enterprise, some settings have `isDynamic = true` and can be updated while the DBMS is running:

```cypher
// Illustrative only in environments authorized to modify settings:
CALL dbms.setConfigValue('db.logs.query.threshold', '200ms');
```

**Important caveats:**

- Only **dynamic** settings can be changed with this procedure; max heap and page cache size normally require a planned change/restart workflow.
- Runtime changes made via `dbms.setConfigValue` are **not persisted to `neo4j.conf`**. After a restart, values can revert to file settings.
- In a cluster, this applies **only to the connected member** and does not automatically propagate to other members.
- Persistent changes in config files/configuration management must be managed separately and synchronized across members.

Before and after every change, capture **actual active values** via `SHOW SETTINGS`, startup logs, and relevant admin tools.

## 6. Formulating a Hypothesis and Choosing One Meaningful Change

A well-formed hypothesis follows this structure:

> **If** we raise page cache by 4 GiB within the RAM budget **because** steady-state page faults remain high and disk read latency is elevated, **then** page faults/request and read p95 latency will drop, without degrading GC, RSS, or causing OOMs.

This differs from "add RAM to make it faster" because it states **pre-change evidence and falsification criteria**.

| Observed Symptom | Hypothesis | Change to Test | Expected Outcome and Stop Criteria |
| --- | --- | --- | --- |
| Heap near max, rising GC pauses, OOM/tx failures | Heap too small for live set | Raise heap within RAM budget | Fewer GC pauses/errors; no spike in page faults/OS swap |
| Sustained high page faults, low steady-state hit ratio, busy disk | Hot working set misses page cache | Controlled page cache increase | Lower faults and I/O latency; improved p95 |
| `SHOW TRANSACTIONS` shows huge transactions aborted | Query builds excessive state or per-tx limit too low | Optimize query/batch first; review tx limits second | Queries succeed stably with bounded memory |
| Server logs show Bolt thread pool exhaustion | Too many active transactions vs. pool | Shorten transactions, inspect pool before raising limit | Fewer rejections while CPU/GC stay safe |
| Driver connection acquisition timeout, server idle | Undersized client pool or session leak | Fix leaks; scale driver pool sensibly | Lower wait time, higher throughput without errors |
| Plan shows Cartesian product or huge fan-out | Low query selectivity | Fix Cypher, indexes, projections/DTOs | Fewer `Rows`, `DB Hits`, lower latency; RAM change may be unneeded |
| CPU quota at 100%, heap/page cache sufficient | CPU-bound or oversubscribed | Lower concurrency, tune queries, evaluate CPU | Better p95 or higher throughput within SLO |
| Checkpoint duration climbs with disk latency | Storage I/O contention | Inspect storage/write load and checkpoint policy | Stable checkpoints and commits without write-latency spikes |

**Fix sources of waste before scaling resources**: one elevated metric does not prove causality; articulate *why* the chosen parameter directly addresses the measured bottleneck.

## 7. Designing a Conclusive A/B Experiment

### 7.1. Variables to Hold Constant

Between **A (baseline)** and **B (candidate)**, hold constant:

1. Neo4j/JDK/Driver versions, schema, indexes, graph size, and database count.
2. Cypher queries, parameter distributions, read/write mix, and response sizes.
3. Virtual users, request patterns, concurrency, and arrival rates.
4. Hardware, container limits, network, disks, and cluster topology.
5. Identical warmup and measurement windows, long enough to capture GC/checkpoints.
6. No ad-hoc import or GDS jobs running during only one phase.
7. **Change only one target variable**, or if coupled variables must move together, document it explicitly as a **combined configuration** and do not attribute gains to a single parameter.

Test conditions must mirror production: if production has extreme degree skew or deep path queries, a 100-node toy dataset will mislead you.

### 7.2. Three Measurement Phases

```text
Baseline A (stable)
  |
  +-- Warm-up --> measure multiple uniform windows --> save plans, metrics, errors
  |
  v
Change exactly 1 setting with planned restart (if required)
  |
  +-- Verify setting active --> re-warm --> measure identical workload
  |
  v
Candidate B
  |
  +-- Compare p95/p99, throughput, errors, GC, page faults, RSS, I/O
  |
  +-- Meets criteria? --Yes--> keep config + continue monitoring
                        |
                        +-- No --> rollback + re-verify
```

Measure across **multiple runs/windows**, since any single run can be skewed by GC, filesystem cache, load generator hiccups, or network jitter. Where possible, run multiple A–B or A–B–A cycles in staging to avoid mistaking restart/warmup effects for setting improvements.

**Never run destructive load tests against production.** If a production canary is unavoidable, cap request volume, assign an active observer, and prepare explicit abort thresholds and rollback steps.

### 7.3. Designing a Representative Load Mix

For example, split requests into:
- **70%**: look up customer/product nodes via index and return a small page.
- **20%**: traverse 1–2 customer relationship hops, returning a lean DTO.
- **8%**: aggregate revenue over a time range.
- **2%**: write orders via transaction/`MERGE`.

**These weights are illustrative only.** For real systems, derive distributions from telemetry and query logs; include peak bursts, high-degree nodes, miss queries, concurrent writes, and slow clients.

To verify correctness, keep the same data snapshot or build an equivalent one. For write workloads, each test pass mutates the graph and can bias subsequent runs; restore a clean snapshot or use standardized idempotency/data-reset rules.

## 8. Experiment 1: Does Increasing JVM Heap Actually Help?

### 8.1. A Hypothesis Backed by GC Data

Suppose the baseline shows:
- Heap usage hugging its ceiling during peak hours.
- Long GC pauses coinciding with p99 latency spikes.
- No severe I/O bottlenecks or plan regressions.

That is valid evidence to **consider** raising heap, though still insufficient to pick an exact GiB figure: inspect live-set size, allocation rate, transaction memory, and total RAM.

Common self-managed settings:

```properties
# Example only when host/container has sufficient RAM.
server.memory.heap.initial_size=10G
server.memory.heap.max_size=10G
```

Neo4j recommends setting initial and max heap equal to avoid unwanted pauses when resizing the heap. **Never raise `max_size` past the RAM remaining after page cache, native memory, and the OS.**

### 8.2. Why Increasing Heap Might Not Solve the Problem

- **GC is not the bottleneck:** if total GC time is tiny, changing heap size rarely helps.
- **Memory leaks or huge result sets:** a larger heap merely delays the failure.
- **Starving the page cache:** raising heap by shrinking page cache can increase page faults.
- **Longer GC pauses or JVM overhead:** a very large heap does not guarantee better p99.
- **Lock-waiting transactions:** adding heap cannot fix lock contention.

After the change, measure **GC time/pause distribution, post-GC heap occupancy, p95/p99, page faults, RSS, and throughput**. If GC improves yet latency stays flat, the bottleneck lies elsewhere—stop raising heap endlessly.

## 9. Experiment 2: Does Page Cache Need Raising, or Is the Query Reading Too Much?

### 9.1. Reading Hit Ratio Alongside Page Faults and Working Set

The Neo4j page cache holds graph store and native index pages. To analyze it:

- **`hit_ratio`**: fraction of page lookups satisfied from cache.
- **`usage_ratio`**: fraction of allocated cache currently populated.
- **`page_faults`**: cumulative page faults; always compute the **rate over time**.
- **`bytes_read`** and disk read latency: reveal actual physical read demand.

```text
page_faults_per_sec ≈
  (counter at t2 - counter at t1) / (t2 - t1, seconds)

page_faults_per_request ≈
  fault delta in window / completed requests in window
```

A large cumulative counter after days of uptime **does not mean cache is currently insufficient**. After a restart, cold cache or warmup creates fault spikes; compare **steady state after warm-up**.

### 9.2. Page Cache Change Example

```properties
# Baseline A — example:
server.memory.pagecache.size=8G
```

```properties
# Candidate B — only when RAM budget allows:
server.memory.pagecache.size=12G
```

Hold heap, data, load, storage, and queries constant if possible. Check:

- Do faults/s and faults/request drop consistently?
- Do p95/p99 latencies improve under the **same offered load**?
- Do disk I/O wait and bytes read drop?
- Does the host swap/OOM, or does JVM RSS jump unexpectedly?

**If hit ratio is already 99.9%, page faults are near zero, and `PROFILE` shows millions of DB Hits from an overly broad query**, raising page cache is not the first step. Fix the Cypher query, indexes, or traversal bounds.

### 9.3. Working Set Differs from Total Database Size

The page cache does not need to hold the entire store for strong performance. If a graph is 500 GiB on disk while 95% of requests touch a 30 GiB "hot" subset, aim to fit the **actively accessed working set** with modest buffer—do not blindly buy 500 GiB of RAM.

Conversely, if almost the whole graph is read randomly, the working set approaches full store size and storage latency becomes critical. Size for the use case, not just raw disk footprint.

## 10. Experiment 3: Transaction Memory Limits and OOM Errors

### 10.1. Three Settings with Different Scopes

| Setting | Scope | Effect |
| --- | --- | --- |
| `dbms.memory.transaction.total.max` | Total transaction memory across the DBMS | Global cap protecting the server |
| `db.memory.transaction.total.max` | Transaction memory within one database | Prevents one database from monopolizing memory |
| `db.memory.transaction.max` | One single transaction | Bounds an oversized query/transaction |

These limits are not "bonus RAM." When breached, Neo4j can **terminate the transaction** to protect the server. Never "fix" this by setting all limits to 0 (unlimited) in production.

### 10.2. Finding the Offending Transaction

In environments with permissions:

```cypher
SHOW TRANSACTIONS;
```

Depending on version and privileges, you can inspect `estimatedUsedHeapMemory`, `currentQueryAllocatedBytes`, wait times, and running queries. Neo4j also provides:

```cypher
CALL dbms.listPools();
```

Transaction memory figures are **estimates** and can differ from exact heap bytes or count conservatively when structures are shared. Never conclude "the database needs 8 more GiB" from a single transaction memory limit error alone.

### 10.3. Resize the Transaction First

Suppose an importer runs:

```cypher
// Can create an oversized transaction if $rows holds a million records:
UNWIND $rows AS row
MERGE (n:Product {sku: row.sku})
SET n.name = row.name;
```

Instead of raising limits indefinitely, split into batches, back the `MERGE` key with an index/uniqueness constraint, and use controlled retries. For batched `LOAD CSV`, run `CALL { ... } IN TRANSACTIONS` in an **implicit transaction**—never wrap it inside a Java Driver managed transaction.

If you still need a higher limit for an already-optimized workload, measure memory/transaction, concurrent transactions, GC, OOMs, and terminations before and after. Raising a per-transaction limit when 100 transactions scale up together can push **total heap past capacity**.

## 11. Experiment 4: Bolt Thread Pool vs. Java Driver Connection Pool

### 11.1. Two Pools on Opposite Sides

```text
Java/Spring Service                           Neo4j Server
   |                                                |
Driver connection pool  -- Bolt connections --> Bolt thread pool
   |                                                |
Session / tx lifecycle                      Cypher runtime / locks / I/O
```

| Symptom | Where the Bottleneck May Be | Checks Before Expanding the Pool |
| --- | --- | --- |
| Java reports connection acquisition timeout | Driver pool exhausted or session leak | Open sessions, tx duration, pool settings, retries, load |
| Neo4j logs Bolt thread pool exhaustion/rejected jobs | Bolt server thread pool | Active transactions, leaked transactions, workers, and CPU |
| Pool has free capacity yet p95 rises | Queries/locks/CPU/I/O rather than pool | `PROFILE`, wait times, GC, CPU, I/O |
| Raising concurrency lowers throughput | Contention/oversubscription | Inspect locks, CPU saturation, page cache, disk |
| Many idle connections | High connection count with low work | Do not raise thread pool just because connections are idle |

Server-side Neo4j settings:

```properties
# Example Bolt server pool controls; not an optimal default:
server.bolt.thread_pool_min_size=5
server.bolt.thread_pool_max_size=100
server.bolt.thread_pool_keep_alive=10m
```

Neo4j documentation notes that **Bolt pool defaults fit most workloads**. Active explicit/implicit transactions occupy worker threads per server mechanics; **close transactions promptly and cleanly** before increasing thread counts.

The Java Driver maintains its own connection pool with options like max pool size and acquisition timeout. Reuse **a single shared `Driver`**, keep sessions short-lived per operation, consume results, and close sessions. **Never create a new Driver per HTTP request.**

### 11.2. Enlarging Pools Can Make Things Worse

Suppose server CPU is already nearly saturated, and the app raises max client pool size from 100 to 1,000. Letting 900 more concurrent requests in can cause:
- More context switching.
- More transactions holding objects/locks and heap.
- Higher GC and page cache pressure.
- Worse p99 and more timeouts.
- **No gain in completed throughput** despite more open connections.

Only expand a pool after proving **the pool is the bottleneck** and the server still has headroom for extra load. Step up in small increments, measuring peak concurrency and actual throughput—never pick "bigger is better" defaults.

## 12. Experiment 5: CPU, I/O, Checkpoints, and Storage

### 12.1. CPU-Bound Signs

When process/host CPU or container CPU quota saturates, throughput plateaus while requests queue up:

- Determine whether CPU is spent in Cypher, GC, Java runtime, or another process.
- Check query plans for costly sorts, aggregations, path searches, or expression evaluation.
- Reduce fan-out/`Rows` first; evaluate indexes and read models.
- Cap concurrency to prevent CPU thrashing; **more threads do not raise a CPU quota**.
- Increase CPU only after measuring gains from cheaper query/config fixes.

### 12.2. I/O-Bound Signs

When page faults and disk read latency climb together, check:
- Does the working set exceed page cache?
- Is storage hitting throughput/IOPS limits?
- Are reads sequential or random, and is hot data staying cached?
- Are checkpoints, index rebuilds, backups, imports, or GDS projections overlapping?

Under heavy write throughput, watch **checkpoint duration**, flushes, and transaction logs. If checkpoint duration approaches the interval between checkpoints, storage may be the bottleneck. Only tune settings such as `db.checkpoint.iops.limit` or `server.memory.pagecache.flush.buffer.*` once you know your storage budget and version docs; raising the IOPS limit carelessly can **degrade commit latency**.

### 12.3. DB Hits Are Not Physical I/O

`DB Hits` in `PROFILE` measure storage-engine operations, not physical SSD reads. A query with 50,000 DB Hits can run quickly if pages are in the page cache, yet 50,000 hits can also signal unnecessary broad traversal. Always read **Rows + DB Hits + page faults + latency** in context.

## 13. Evaluation Scenario: Add RAM or Fix the Query?

Consider a **purely hypothetical** dataset for analytical practice—not a Neo4j benchmark:

| Metric | Baseline A | B: Page Cache 8 → 12 GiB | C: Keep Cache, Fix Query |
| --- | ---: | ---: | ---: |
| p95 latency | 900 ms | 860 ms | 190 ms |
| p99 latency | 1,900 ms | 1,870 ms | 380 ms |
| Achieved throughput | 95 req/s | 98 req/s | 130 req/s |
| `DB Hits` on primary query | 75,000 | 75,000 | 2,200 |
| Page-cache hit ratio | 99.2% | 99.4% | 99.4% |
| Page faults/request | 0.5 | 0.4 | 0.1 |
| Error rate | 0.1% | 0.1% | 0.05% |

Comparison conditions: identical data snapshot, identical load generator, and equivalent offered load/measurement conditions. If `achieved throughput` rises in phase C, verify **the test actually pushed sufficient load** so you distinguish higher server capacity from lower requested load.

**Interpretation:**

- The original page cache was already effective, so adding 4 GiB yields marginal benefit.
- Query B still incurs 75,000 DB Hits because the traversal shape is unchanged.
- Query C cuts DB Hits/Rows by starting from an indexed key and bounding traversal, slashing p95.
- The sensible choice is to **keep the query fix** rather than rushing to add RAM to every node, then verify under heavier load.

**Avoid hasty conclusions:** B and C are two **fundamentally different changes**; to isolate each contribution, measure against the same baseline rather than changing both query and page cache at once and crediting a single factor.

## 14. Java Driver: Capturing Segmented Latency

Java Driver 6.x example, given an application-wide `Driver driver`, measuring **duration of returning a short result list**:

```java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

record ProductView(String sku, String name) {}

static List<ProductView> loadProducts(
        Driver driver, String supplierId, int requestedLimit) {
    int limit = Math.max(1, Math.min(requestedLimit, 50));

    String cypher = """
        MATCH (s:Supplier {supplierId: $id})-[:SUPPLIES]->(p:Product)
        WHERE p.active = true
        RETURN p.sku AS sku, p.name AS name
        ORDER BY sku
        LIMIT $limit
        """;

    long started = System.nanoTime();

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        List<ProductView> result = session.executeRead(tx ->
            tx.run(cypher, Map.of("id", supplierId, "limit", limit))
              .list(r -> new ProductView(
                  r.get("sku").asString(),
                  r.get("name").asString()
              ))
        );

        long durationMs = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started
        );

        System.out.printf("neo4j_read_ms=%d, count=%d%n",
            durationMs, result.size());

        return result;
    }
}
```

This is a **client-side wall-clock measurement of the Neo4j call** covering session checkout, transaction execution, transport, and mapping—not server Cypher time alone. In production, use a metrics library/tracing with histograms instead of `System.out` per request, and record timings **even on exceptions** via `try/finally` or instrumentation. Never log sensitive supplier IDs or arbitrary record payloads.

When comparing sync, async, and reactive APIs, keep **identical Cypher, data, and equivalent result consumption**. Reactive offers backpressure without reducing DB Hits; async does not help when the bottleneck is a query plan or transaction lock.

## 15. Configuration in Docker, Kubernetes, Clusters, and AuraDB

### 15.1. Containers: Budget from the Effective Limit

Example illustrating Neo4j settings in Docker:

```yaml
services:
  neo4j:
    image: neo4j:2026.10
    environment:
      NEO4J_server_memory_heap_initial__size: "6G"
      NEO4J_server_memory_heap_max__size: "6G"
      NEO4J_server_memory_pagecache_size: "6G"
    mem_limit: 16g
```

**This is syntax illustration only**, not a complete production Docker Compose file (omitting volumes, authentication, backups, network security, etc.). In Neo4j Docker, dots in setting names map to single underscores and original underscores map to double underscores. Verify that your exact image tag exists and uses the matching setting format.

With a 16 GiB limit, heap + page cache = 12 GiB here, leaving roughly 4 GiB for native memory, OS/container processes, and headroom. **Do not assume 4 GiB is always enough**; measure RSS and test real workloads, especially with high thread counts, GDS, or custom plugins.

Kubernetes adds **CPU throttling, OOMKilled, pod eviction, request/limit shifts, and persistent volume latency**. Compare metrics before/after per pod and remember restarts cool the page cache.

### 15.2. Clusters: Do Not Inspect Only One Server

In a cluster, check:
- Whether all members have matching **effective configs and memory**.
- Which members receive read traffic, and whether leader/writer load differs.
- Page cache, GC, CPU, and I/O **per member**, instead of looking only at cluster averages.
- Whether restarts/rolling changes impact availability, cache warmup, or routing/rebalancing.
- Dynamic changes on one member do not auto-propagate to other members.

If one replica has worse p99 due to a slow disk, adding RAM to another member will not fix requests routed to the slow replica.

### 15.3. AuraDB: Optimizing Within Managed Service Boundaries

On AuraDB, users **do not edit `neo4j.conf` or run `neo4j-admin` as on self-hosted instances**. Available metrics, observability rights, and instance-size/scaling options depend on your service tier.

Recommended workflow:
1. Measure requests/Cypher and use Aura-provided metrics.
2. Fix query plans, indexes, batching, and Java Driver pool usage first.
3. Once resource limits are proven, evaluate upgrading tier/instance size.
4. Compare before and after under identical workloads, factoring in cost and service-policy rollback options.

Never hand an Aura user commands to change `server.memory.pagecache.size` or run `dbms.setConfigValue` as if they had self-hosted controls.

## 16. Auditable Operations and Rollback Workflow

Before any resource change, write a brief change record:

| Field | Example |
| --- | --- |
| Change ID | `neo4j-perf-2026-11-25-01` |
| Problem | Order-read p95 rose above 600 ms at 100 req/s |
| Baseline | Query X, p95, p99, errors, `Rows`/`DB Hits`, GC, page faults, disk |
| Hypothesis | Steady-state page faults/request remain elevated |
| Single variable changed | `server.memory.pagecache.size`: 8G → 12G |
| Scope | One staging member, identical data/load; canary next if approved |
| Pass criteria | Significant p95 drop, no error increase, stable GC/RSS |
| Stop criteria | OOM, swap, rising p99/errors, no expected gain |
| Rollback | Restore 8G, planned restart, verify setting, warm up, and re-measure |
| Outcome | Keep/revert decision with rationale and measurements |

**Rollback is more than reverting one config line.** If a setting requires a restart, rolling back may also require a restart—impacting cache warmup and availability. For clusters, define rolling order, stabilization intervals, and recovery steps. For index or query changes, plan carefully to preserve data and business correctness.

Never compare **one minute after a restart** against a system running for days; caches, JIT, GC, and workload are not comparable. Always annotate restarts, failovers, deployments, and imports on monitoring dashboards.

## 17. Common Misconceptions That Lead to Bad Tuning

| Misconception | Correct Understanding |
| --- | --- |
| "If Neo4j is slow, just raise the heap." | Raise heap only when heap/GC/transaction metrics prove heap is the bottleneck |
| "On 32 GiB RAM, 24G heap + 24G page cache is fine." | The sum exceeds RAM before even counting native/OS and memory limits |
| "A 99% page cache hit ratio proves the query is fast." | Queries can still suffer high `DB Hits`, CPU, sorts, or locks |
| "A huge page faults counter means cache is starving right now." | Check the rate over time; restarts/warmups spike counters |
| "`DB Hits` equals SSD reads." | It counts logical storage-engine operations, distinct from page faults/I/O |
| "`PROFILE` does not modify the graph." | `PROFILE` executes the query, including write queries |
| "Raising `db.memory.transaction.max` creates more memory." | It only raises the cap; concurrent transactions can still trigger OOM |
| "Using `--memory=32g` from memrec is fully optimal." | It is a starting heuristic that must be tested against real workloads |
| "Client pool size equal to user count is good." | Oversized pools worsen contention and p99 |
| "Many Bolt connections means not enough Bolt threads." | Idle connections differ from active transactions; check rejections/worker utilization |
| "Adding CPU makes full scans have good indexes." | Query plans and indexes must be fixed directly |
| "`SHOW SETTINGS` on one cluster member represents all." | Settings reflect only the executing member |
| "Edited dynamic settings survive restarts." | Runtime changes do not persist to config files automatically |
| "Lower p50 with higher p99/errors is still a win." | Changes must satisfy SLOs and system stability |
| "One benchmark run is enough." | Multiple windows, warmup, and representative data/load are required |
| "On Aura you can edit `neo4j.conf` too." | Tunability depends on the managed service; no self-hosted config file access |
| "Adding resources without changing queries always speeds things up." | Unselective queries can burn extra resources with negligible improvement |

## 18. Checklist Before Approving Resource Increases

1. **Define the incident:** which endpoint/query/job is slow, since when, and which SLO is violated?
2. **Classify the load:** reads/writes, deep traversals, batch imports, GDS, concurrency, data skew.
3. **Record baseline:** p50/p95/p99, throughput, errors, pool wait, GC, page cache, CPU, I/O.
4. **Verify queries:** `EXPLAIN`/`PROFILE`, indexes/constraints, fan-out, `Rows`, `DB Hits`, result sizes.
5. **Identify limits:** host/container RAM, heap, page cache, native, transactions, CPU quota, storage.
6. **Formulate hypothesis:** "setting X improves metric Y via mechanism Z."
7. **Check mutability:** version, edition, dynamic vs. static setting, privileges, and downtime impact.
8. **Prepare controls:** same data, parameters, concurrency, warmup, window length, and client.
9. **Test one change:** record before/after values and target member/pod/instance scope.
10. **Evaluate holistically:** latency/throughput, errors, correctness, GC, RSS, faults, CPU, I/O, cost.
11. **Rollback if needed:** have a revert plan ready and verify metrics after rollback.
12. **Archive evidence:** charts, sanitized logs, query plans, configs, conclusion, and owner.

## 19. Self-Check Exercises

1. A machine has 32 GiB RAM, 8 GiB heap, 16 GiB page cache, and the rest for OS/native. Someone proposes raising heap to 24 GiB while keeping 16 GiB cache. Identify the flaw and design a verification plan.
2. p95 climbs while page-cache hit ratio is 99.9% and page faults/s are near 0. `PROFILE` shows `Expand(All)` producing 1 million `Rows` from one customer. Would you prioritize changing settings or fixing Cypher? Why?
3. A JVM shows GC pauses climbing right as p99 spikes, while page cache hit ratio stays healthy. Draft a hypothesis and test plan for moving heap 8G → 10G, naming metrics and rollback criteria.
4. A giant import transaction is terminated by `db.memory.transaction.max`. Compare raising the limit against batching and indexing the `MERGE` key.
5. 100 Java Driver connections exist, yet only 10 transactions are active and zero Bolt rejections occur. Should you raise `server.bolt.thread_pool_max_size`? What else should you inspect?
6. Sketch an A–B–A pipeline for a page cache change, explaining how to handle cold caches after each restart to avoid false conclusions.
7. In a Neo4j Enterprise cluster, you call `dbms.setConfigValue(...)` on one member. Why must you also check the remaining members and config files?
8. You observe the page faults counter climb from 8,000 to 11,000 over 60 seconds while 1,500 requests complete. Compute faults/s and faults/request, and explain the limits of relying on those two numbers alone.
9. Build a 6-metric matrix comparing the impact of raising CPU quota versus indexing `MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)`.
10. A workload gains 15% throughput after enlarging the pool, yet p99 doubles and error rate rises. Should you deploy it? Relate your answer to the defined SLOs.

## 20. Key Takeaways

- **Adding resources is an engineering hypothesis to be tested**, not a default reflex when queries slow down.
- **Neo4j heap, page cache, transaction memory, Bolt pool, CPU, and storage** are distinct resources that can compete with one another.
- **Measure baseline first**: p95/p99, throughput, errors, `EXPLAIN`/`PROFILE`, GC, page faults, I/O, and client pools.
- **`DB Hits` is not disk I/O**; a high page-cache hit ratio does not prove a good query plan. Inspect cardinality/fan-out alongside latency.
- **One change per experiment**, with matched workload/data/parameters, proper warmup, and runs long enough to capture GC, checkpoints, and peak load.
- **Inspect effective configuration values**, static vs. dynamic behavior, edition/tier, and member/pod scope; dynamic runtime changes do not auto-save to files.
- **Decide from multi-dimensional results**: correct queries, SLO-compliant latency and throughput, no error spikes, sustainable resources, and reasonable cost.
- **When a change fails or adds risk, roll back cleanly** and investigate another hypothesis rather than blindly "adding a bit more."

### Official References

- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
- [Neo4j Operations Manual — Get initial memory recommendations](https://neo4j.com/docs/operations-manual/current/configuration/neo4j-admin-memrec/)
- [Neo4j Operations Manual — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/)
- [Neo4j Operations Manual — Show configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/show-settings/)
- [Neo4j Operations Manual — Update dynamic settings](https://neo4j.com/docs/operations-manual/current/configuration/dynamic-settings/)
- [Neo4j Operations Manual — Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/)
- [Neo4j Operations Manual — Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Neo4j Operations Manual — Logging and query log](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual — Bolt thread pool configuration](https://neo4j.com/docs/operations-manual/current/performance/bolt-thread-pool-configuration/)
- [Neo4j Operations Manual — Garbage collector tuning](https://neo4j.com/docs/operations-manual/current/performance/gc-tuning/)
- [Neo4j Operations Manual — Disks, RAM and other tips](https://neo4j.com/docs/operations-manual/current/performance/disks-ram-and-other-tips/)
- [Neo4j Operations Manual — Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Neo4j Operations Manual — Docker-specific configuration settings](https://neo4j.com/docs/operations-manual/current/docker/ref-settings/)
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
