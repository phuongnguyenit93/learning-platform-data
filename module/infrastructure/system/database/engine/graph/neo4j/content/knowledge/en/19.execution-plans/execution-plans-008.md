# Memory, Page Cache, and Differences Between Cold and Warm Runs

## 1. Why Can a Cypher Query Run Faster the Second Time?

Consider the same Neo4j query:

~~~cypher
MATCH (a:Article)
WHERE a.category = 'database'
RETURN count(a) AS total;
~~~

The first time, the query may have to read data or index pages from storage into memory. When run again, many needed pages are already in the **Neo4j page cache**, so data-access wait time can drop significantly. However, the difference between two runs **is not solely due to the page cache**: Neo4j also caches query plans, the JVM may optimize hot code, the OS has its own filesystem cache, and the client may incur connection setup time.

In the **Execution Plans** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, we learn to read `EXPLAIN` and `PROFILE` to distinguish:

- How much **logical work** the query is doing against the graph.
- How many page accesses **hit or miss the Neo4j page cache**.
- How much intermediate memory the operators allocate.
- Why a **cold run** measurement differs from a **warm run**.
- When you need to fix the model, indexes, or Cypher instead of adding RAM.

This lesson applies to queries on property graphs (nodes, relationships, and indexes) and is also useful when measuring performance via the **Neo4j Java Driver** or **Spring Data Neo4j**.

> **Conditions:** Cypher examples use Neo4j 5+ syntax. Column names, visibility, and `PROFILE` formatting may vary by version, edition, and runtime. Illustrative latency figures in the tables below **are not actual benchmark results**.

## 2. Neo4j Memory Map

Related memory regions serve different functions:

| Region | What It Stores | When Scarce or Troubled |
|---|---|---|
| **JVM heap** | Java objects, transaction state, and part of intermediate query memory; the query plan cache also consumes heap | Increased GC; complex sorts/aggregations can exceed transaction memory limits |
| **Neo4j page cache** | Pages from graph store files and certain on-disk indexes | Many *page cache misses*, forcing page reloads and raising I/O latency |
| **Native/off-heap memory** | Native allocations used by Neo4j or libraries, including off-heap structures | Pressure on system RAM even while `heap used` remains low |
| **OS memory / filesystem cache** | OS allocations, file pages, and structures outside the JVM heap | Can cause swapping or memory contention with Neo4j |
| **JVM code cache / JIT** | Compiled machine code and runtime metadata | Early runs incur extra startup/compilation overhead |
| **Application / Driver memory** | Connections, network buffers, DTOs, client-side result data | Client-observed latency can be high even when server processing is fast |

**The page cache is not the JVM heap.** Seeing a `Sort` use high `Memory (Bytes)` does not mean you should raise `server.memory.pagecache.size`. Conversely, having many page cache misses does not by itself prove heap is insufficient.

For specialized indexes such as **vector indexes**, part of working memory resides in OS/native memory rather than necessarily inside the Neo4j page cache. Estimating RAM needs solely from graph store size and page cache can therefore miss total memory requirements.

Common settings in Neo4j 5+:

~~~properties
# Illustrative configuration example, NOT a recommendation for all machines.
server.memory.heap.initial_size=4G
server.memory.heap.max_size=4G
server.memory.pagecache.size=8G
~~~

On a dedicated Neo4j machine, you must still leave RAM for the OS, native buffers, various index types, and other processes. **Do not set heap plus page cache equal to 100% of physical RAM.** Consult `neo4j-admin server memory-recommendation`, store/index file sizes, transaction load, and real observations before tuning values.

### What Does the Page Cache Hold?

Neo4j stores the graph and indexes in files. When the runtime needs to read records/properties or access an index, it works with data **pages**:

- **Hit:** the page is already in the Neo4j page cache and can be served without reloading.
- **Miss:** the page is not yet in the Neo4j page cache, so the system must fetch/load it from lower storage layers.
- **Eviction:** when cache capacity cannot hold all active pages, older pages may be evicted to make room for new ones.
- **Warmup:** mechanisms or traffic that bring frequently used pages back into the page cache.

A *miss* does not necessarily equal **one physical SSD read**: the OS may maintain its own cache; furthermore, asynchronous reads, prefetching, and page management vary by version and configuration.

## 3. Path from Cypher to the Page Cache

~~~mermaid
flowchart TD
    A["Java Driver / Browser sends Cypher"] --> B["Parse, plan, or reuse query plan cache"]
    B --> C["Runtime runs operators"]
    C --> D["Access record / property / index (DB Hits)"]
    D --> E{"Page present in Neo4j page cache?"}
    E -->|Hit| F["Use page already in RAM"]
    E -->|Miss| G["Load required page"]
    G --> H["OS filesystem cache or storage device"]
    H --> F
    F --> I["Compute / return results"]
~~~

This diagram illustrates a **conceptual** flow; `DB Hits` is a logical unit of storage-layer work, **not** the number of pages the OS must read. One database hit can trigger varying page-cache activity, and not every operator step touches the page cache.

Example of an index lookup:

~~~cypher
MATCH (u:User)
WHERE u.email = $email
RETURN u.name;
~~~

With an index on `:User(email)`, the plan can use `NodeIndexSeek`; without one, it may need a scan and filter. Whether data is hot or cold, index/scan selection still matters enormously: **caching lowers page-load cost, yet does not eliminate the logical work of a poor plan**.

## 4. Cold Runs and Warm Runs: Defining Terms Clearly

### 4.1. What Is “Cold”?

In page-cache terms, a **cold run** means most pages needed by the query **are not yet in the Neo4j page cache** at the start. On the first read, misses may be higher and I/O latency larger.

A **warm run** means most pages to be accessed **are already held in the page cache**. Subsequent runs typically have more hits, fewer misses, and lower page-loading cost.

These states describe the **warmth of the page working set needed by the query**, not just process uptime.

| Aspect | Cold Run Scenario | Warm Run Scenario |
|---|---|---|
| Needed pages in Neo4j page cache | Many pages absent | Most already present |
| Page cache misses | Can be high | Usually lower |
| Page cache hits | Ratio can be low | Ratio usually higher |
| Latency | Can suffer I/O wait | Can reduce I/O wait |
| `Rows` and query answer | Must match current data | Must match cold run if data/logic unchanged |
| `DB Hits` | Usually nearly equal under the same plan | Usually nearly equal under the same plan |
| Execution plan | Depends on schema, statistics, and planner | Does not necessarily change solely because cache warmed |

Do not claim “the first run is always slowest.” Another user may already have loaded those exact pages, or warmup may have run automatically. Conversely, the 10th run can still be slow if the working set exceeds cache size or concurrent tasks evict pages.

### 4.2. Cold Page Cache Differs from Cold Query Plan Cache

Neo4j has several independent optimization layers:

| Mechanism | What Does It Cache? | Does It Skip Query Execution? |
|---|---|---|
| **Neo4j page cache** | Data and index pages | No; merely helps the runtime access pages faster |
| **Query cache / plan cache** | Parse stages, logical plans, executable plans | No; skips part of planning cost, **still executes** the query |
| **OS filesystem cache** | OS-level file pages | No; can help Neo4j reload pages faster |
| **JVM JIT/code cache** | Optimized/compiled machine code | No; lowers repeated execution overhead in some cases |
| **Connection pool** | Ready network connections on the client | No; avoids connection/handshake setup overhead |

Changing one character in Cypher or changing parameter types can affect query-cache reuse; modifying index files or schema can also force replanning. Therefore, never compare “run 1” and “run 2” timings and declare **exact percentages** attributable to the page cache without supporting metrics.

### 4.3. Restarting Neo4j Does Not Guarantee a Clean “Cold Run”

After a restart, process memory resets, yet:

- The OS may still hold prior filesystem cache pages.
- Neo4j Enterprise supports **page cache warmup** based on usage profiles, depending on configuration.
- Other jobs or traffic may load pages before your test runs.
- Java services/drivers have their own startup and JIT costs.

Thus, restarting a test environment produces only a **near-cold condition**, not a guarantee that all data is read strictly from disk. Intentionally dropping OS caches or repeatedly restarting databases must not be done on production systems.

## 5. Reading EXPLAIN and PROFILE to See What Costs Resources

### EXPLAIN

~~~cypher
EXPLAIN
MATCH (p:Person)
WHERE p.age >= 30
RETURN p.name
ORDER BY p.name;
~~~

`EXPLAIN` builds the **projected plan** without running the query. It is useful for checking which operators are chosen, estimated row counts, and potential index usage, but it does not report actual runtime metrics such as page cache hits/misses.

### PROFILE

~~~cypher
PROFILE
MATCH (p:Person)
WHERE p.age >= 30
RETURN p.name
ORDER BY p.name;
~~~

`PROFILE` **actually runs** the query and adds execution metrics. If prefixed to a write statement, the write executes too; in lessons and benchmarks, use it only on **read-only** queries.

Important plan fields (when available):

| Field | Meaning | How to Interpret |
|---|---|---|
| `Estimated Rows` | Rows the planner estimated before execution | Large mismatch with `Rows` can cause suboptimal plan selection |
| `Rows` | Actual rows emitted by each operator | Helps spot row inflation from one-to-many relationships |
| `DB Hits` | Logical storage-layer access operations | Does not equal physical disk reads; lower generally means less work |
| `Page Cache Hits/Misses` | Page cache hits/misses | Shows warmth during that run; typically shown in **Enterprise Edition** |
| `Memory (Bytes)` | Tracked **heap peak** per operator | Not Neo4j page cache size; do not sum operator peaks to get total |
| `Time (ms)` | Time recorded for operator/pipeline | Fused operators share a pipeline timing metric |
| `Indexes Used` | Indexes used, when provided by the runtime | Distinguishes seek/scan plans; do not infer solely from operator names |
| Footer `total allocated memory` | Query memory peak recorded by the runtime | Does not equal the sum of all operators' `Memory (Bytes)` |

**Observability note:** `Page Cache Hits/Misses` in `PROFILE` plans are documented by Neo4j for **Enterprise Edition**; some operators or pipelines do not display them. Blank cells or a missing column **do not mean** Neo4j is not using the page cache. Check DBMS/database-level metrics via monitoring tools if the plan lacks sufficient detail.

In addition, when the runtime fuses multiple operators into a pipeline, `Time (ms)` can represent **the entire pipeline**. Do not blame a single operator as the bottleneck when multiple operators share that timing metric.

### Hit Ratio Formula

When both `hits` and `misses` are available for the same measurement scope:

\[
\text{Page cache hit ratio}
=\frac{\text{hits}}{\text{hits}+\text{misses}} \times 100\%
\]

Hypothetical example: `995 hits` and `5 misses` gives **99.5%**. If both are 0, the ratio is undefined; do not assume “100% optimal cache”.

## 6. Illustrative Table: Same DB Hits, Different Page Cache

The numbers below **only illustrate how to read**, not measured Neo4j outputs:

| Metric | Near-Cold Run | Warm Run |
|---|---:|---:|
| Rows at inspected operator | 1,000 | 1,000 |
| DB Hits | 4,000 | 4,000 |
| Page Cache Hits | 100 | 995 |
| Page Cache Misses | 900 | 5 |
| Hit ratio | 10.0% | 99.5% |
| Client latency (hypothetical) | 95 ms | 18 ms |

In this example, logical workload is virtually identical (`Rows` and `DB Hits` match), while page state differs. The proper interpretation is that **the page cache can contribute substantially to the latency difference**. You cannot deduce from this table alone that “77 ms is strictly disk I/O time” because OS cache, network, planning, scheduling, and other factors also apply.

If a warm run still shows very high `DB Hits`, inspect the query plan: an unnecessary scan or expand still burns CPU and resources even without reading pages from disk again.

## 7. Hands-On with Answers: Building an Isolated Dataset

Use an isolated practice database; never run cleanup in a database holding real data. The `QA008PerfDoc` label and `qa008_perf_segment` index name are dedicated to this lesson.

### Step 1 — Clean Up Prior Fixture If Present

~~~cypher
DROP INDEX qa008_perf_segment IF EXISTS;
~~~

~~~cypher
MATCH (d:QA008PerfDoc)
DETACH DELETE d;
~~~

### Step 2 — Create 10,000 Nodes with Deterministic Data

~~~cypher
UNWIND range(1, 10000) AS i
CREATE (:QA008PerfDoc {
  testId: i,
  segment: i % 100,
  score: i % 10,
  title: 'Test document ' + toString(i)
});
~~~

This is a small dataset **for learning to read execution plans**, not large enough to guarantee reliable cold/warm gaps on every configuration. Even `CREATE` itself warms many pages, so the first `PROFILE` right after this step is **not a true cold run**.

Verify answers:

~~~cypher
MATCH (d:QA008PerfDoc)
RETURN
  count(d) AS soNode,
  sum(d.score) AS tongDiem,
  count(DISTINCT d.segment) AS soSegment;
~~~

| soNode | tongDiem | soSegment |
|---:|---:|---:|
| 10,000 | 45,000 | 100 |

Explanation: `score` takes values 0–9, each appearing exactly 1,000 times; the sum is `(0+1+...+9) × 1,000 = 45,000`. `segment` takes values 0–99, with 100 nodes per group.

### Step 3 — Read the Scan Plan

~~~cypher
EXPLAIN
MATCH (d:QA008PerfDoc)
RETURN
  count(d.score) AS soNode,
  sum(d.score) AS tongDiem;
~~~

Then run:

~~~cypher
PROFILE
MATCH (d:QA008PerfDoc)
RETURN
  count(d.score) AS soNode,
  sum(d.score) AS tongDiem;
~~~

The answer stays the same: `soNode = 10000`, `tongDiem = 45000`.

Depending on runtime, you may see a label-scan operator, property reads, and an aggregation operator. Names such as `NodeByLabelScan` and `EagerAggregation` are merely **examples**; version, data layout, and planner optimizations can yield a different plan.

**Run the exact `PROFILE` query above three times**, capturing `Rows`, `DB Hits`, `Page Cache Hits/Misses`, and timing stats. Then analyze:

- If `DB Hits` stays stable while `misses` drop, pages are being retained better in cache.
- If `misses` stay high, the working set may exceed cache capacity or other tasks are competing for cache.
- If `misses` are near 0 from the first run, the fixture was already warm or all newly created data remained in RAM.
- If per-operator page cache metrics are unavailable, do not fabricate them; use system-level dashboard metrics or note that your edition/runtime does not expose them.

### Step 4 — Add an Index to Observe Logical Work Differences

Create a dedicated index on `segment`:

~~~cypher
CREATE RANGE INDEX qa008_perf_segment IF NOT EXISTS
FOR (d:QA008PerfDoc) ON (d.segment);
~~~

Check that the index is ready:

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
WHERE name = 'qa008_perf_segment'
RETURN name, type, state, labelsOrTypes, properties;
~~~

Test seeks only after the index is `ONLINE`.

~~~cypher
PROFILE
MATCH (d:QA008PerfDoc)
WHERE d.segment = 42
RETURN
  count(d) AS soNode,
  sum(d.score) AS tongDiem;
~~~

Answer: `soNode = 100`, `tongDiem = 200`. In the `segment = 42` group, every node has `score = 2` because `42 mod 10 = 2`.

The planner **may** pick `NodeIndexSeek` using the range index; however, on a small dataset, the planner sometimes chooses another strategy. Evaluate the actual plan returned rather than forcing the result to display a fixed operator name.

**Comparison purpose:** an index can reduce `DB Hits` by narrowing the nodes read; the page cache keeps the pages needed by the plan readily available in RAM. These are **two distinct optimization axes**. Do not compare the latency of the full-scan query in Step 3 directly against the `WHERE d.segment = 42` query because both the problem and record counts processed differ.

### Step 5 — Observing Intermediate Memory of Aggregation

~~~cypher
PROFILE
MATCH (d:QA008PerfDoc)
WITH d.segment AS segment, collect(d.testId) AS ids
RETURN segment, size(ids) AS members
ORDER BY members DESC, segment
LIMIT 5;
~~~

The data yields 100 groups of 100 elements each; because `members` values are tied, the result is groups `segment = 0, 1, 2, 3, 4`, each with `members = 100`.

The `ids` lists are constructed in query memory. Locate the aggregation/sort operators and `Memory (Bytes)` column if supported by the runtime, then separate the cost of **buffering intermediate data** from **loading pages from the page cache**. When only a count is needed, you can optimize by replacing `collect(d.testId)` and `size(ids)` with `count(d)`, avoiding materializing each `ids` list.

## 8. Building a Repeatable Cold/Warm Benchmark

To draw conclusions for production optimization, you need a rigorous measurement protocol.

### 8.1. Hold Confounding Variables Constant

1. **Same data and schema:** do not create indexes, update statistics, import data, or write nodes/relationships between measurement runs. Indexes must be `ONLINE`.
2. **Same query and parameter types:** use parameterized queries with identical values/types to avoid plan-cache misses and selectivity shifts.
3. **Same environment:** Neo4j version, Cypher runtime, heap, page cache, CPU, RAM, storage, container limits, connection counts, and concurrency should remain stable.
4. **Same result consumption:** always consume the full result stream; never compare merely opening a cursor against awaiting all results.
5. **Measure both server and client:** capture `PROFILE`/metrics to diagnose causes, while measuring plain queries (without `PROFILE`) when reporting application latency because `PROFILE` carries instrumentation overhead.
6. **Record actual plans:** if operators or indexes used change, that is a separate experiment; analyze it independently rather than attributing the entire difference to page cache.

### 8.2. The “Near-Cold” Group

On a **dedicated test instance**, choose a controlled initial data-loading state. If using restarts, document that OS filesystem cache and page cache warmup may keep data partially warm. Recent Neo4j versions include `db.memory.pagecache.warmup.enable` in Enterprise Edition; restarts can automatically re-warm pages from usage profiles.

Run the read query **once**, saving latency and cache metrics near execution time. Collecting multiple near-cold samples requires restoring the initial condition for **each sample**; do not treat consecutive runs inside the same process as independent “cold” samples.

Never attempt to cool caches through disruptive operations in production. If you cannot isolate the environment and confirm a cold cache, label results as **“first observed run”** or **“after restart”**, rather than claiming “cold disk”.

### 8.3. The Warm Group

In the same test environment:

1. Run the same query several times to warm frequently accessed pages, the connection pool, and JIT.
2. Exclude warmup runs from steady-state measurements.
3. Run at least several dozen iterations (depending on goals), recording per-run latency along with **median**, **p95**, page hits/misses, DB Hits, GC, and I/O.
4. Add realistic **concurrent load** if the goal is production operation; single-user sequential latency often differs from concurrent transactional graph access.

Use median instead of reporting only “fastest run”; p95 exposes outliers caused by I/O, GC, or resource contention. Do not average cold and warm runs into one number because they answer two different questions.

### 8.4. Sample Recording Table

| run | Condition | Client Latency (ms) | DB Hits | PC Hits | PC Misses | Plan/Index |
|---|---|---:|---:|---:|---:|---|
| 1 | after restart | *(measure)* | *(measure)* | *(if available)* | *(if available)* | *(record)* |
| 2 | warmup | *(measure)* | *(measure)* | *(if available)* | *(if available)* | *(record)* |
| 3..N | steady-state | *(measure)* | *(measure)* | *(if available)* | *(if available)* | *(record)* |

Cells marked “*(measure)*” are collection requirements, **not assumed results**. If per-query metrics are unavailable, you can use database/DBMS-level metrics over an isolated time window and workload, without attributing whole-system metrics to one query in a multi-user environment.

## 9. Measuring Latency via the Neo4j Java Driver

In Java applications, the time from sending a query until **consuming all results** usually matters more than a single operator's duration. The minimal example below assumes `driver` is already initialized and connected, using database `neo4j`:

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

void benchmarkRead(Driver driver) {
    String cypher = """
        MATCH (d:QA008PerfDoc)
        WHERE d.segment = $segment
        RETURN count(d) AS soNode, sum(d.score) AS tongDiem
        """;

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        // Exclude driver creation time from query latency.
        long start = System.nanoTime();

        // consume() forces the driver to receive the entire result stream.
        session.run(cypher, Values.parameters("segment", 42))
               .consume();

        long millis = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - start
        );
        System.out.println("Elapsed ms = " + millis);
    }
}
~~~

For cleaner comparisons, invoke the query multiple times, discard warmup iterations, and record per-iteration latency instead of printing a single number. Keep database configuration, Java Driver version, connection pool, network, and concurrency stable.

In Spring Data Neo4j, you can measure similarly at the service/repository layer, though application timing may additionally include entity mapping, transaction interceptors, and Spring overhead. If the goal is analyzing the page cache, compare application latency with server-side metrics to pinpoint which layer introduces the gap.

## 10. Operational Metrics to Watch Alongside Execution Plans

`PROFILE` helps understand a single query. For production observability, watch multi-query metrics simultaneously:

| Metric | Question to Ask |
|---|---|
| Page cache **hit ratio** | Over the measurement window, what share of page requests were served from cache? |
| Page cache **usage ratio** | How much of cache capacity is currently utilized? |
| Page cache **hits / misses / page faults** | How do hit and page-load rates shift after deployments or load spikes? |
| Page cache **bytes read** | Are large data reads occurring from the storage layer? |
| Heap used / GC pause | Are queries slow due to memory allocation/GC rather than page loading? |
| Query duration, p95/p99 | Are users experiencing slowness even when cache hit ratio is high? |
| I/O latency, IOPS, CPU | Is the real bottleneck storage hardware or compute capacity? |
| Transaction memory / query memory | Are queries hitting large `Sort`, `EagerAggregation`, `Expand`, or memory-limit blocks? |

In Neo4j operational guidance, keeping hit ratio **above roughly 98%** is often a reference target for steady workloads; it is **not a rigid rule** for every query. A workload continuously scanning fresh data may incur many cache misses while still behaving normally; conversely, a high hit ratio does not guarantee low latency if CPU is saturated or Cypher generates too many intermediate rows.

`usage ratio = 100%` alongside falling hit ratio and rising I/O can suggest the working set no longer fits in the page cache. However, **high usage ratio alone** is normal for a cache making full use of RAM; combine multiple metrics before deciding to grow cache capacity.

### Checking Configuration via Cypher

Depending on permissions and Neo4j version, you can run:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'server.memory.heap.initial_size',
  'server.memory.heap.max_size',
  'server.memory.pagecache.size'
]
RETURN name, value
ORDER BY name;
~~~

If the account lacks permission to view settings or the system is managed by a cloud platform, inspect configuration/monitoring exposed by that platform. Pay special attention to **container or VM RAM limits**, not just the host's physical RAM total.

Neo4j documentation also provides a server memory estimation command:

~~~text
neo4j-admin server memory-recommendation
~~~

This is an **operating system CLI command**, not Cypher. Use it as a starting point and inspect store/index sizes; final tuning must still rely on your real workload.

## 11. Diagnostic Scenarios and Next Actions

| Observation | Plausible Explanation | Verification / Tuning Step |
|---|---|---|
| First run slow with many page cache misses; faster after a few runs | Needed pages warmed into cache | Keep query/index identical; compare DB Hits and hits/misses across runs |
| First run slow yet almost zero page cache misses | Unlikely to be page cache | Inspect plan cache, JIT, connection setup, GC, and client operations |
| Both cold and warm runs slow with very high DB Hits | Plan is likely doing redundant work | Inspect scans/expands, filters, cardinality; consider indexes or Cypher rewrites |
| High cache hit ratio yet `Sort` consumes high memory | Bottleneck in intermediate memory / CPU | Shrink rows to sort, tune filters, find matching index, avoid needless `collect()` |
| Page cache usage near 100%, misses and I/O climbing steadily | Working set likely exceeds cache | Check store/index sizes, concurrent load, available RAM; measure before growing cache |
| Query timing suddenly shifts right after adding an index | Planner replanned, index building, or new cache state | Wait for index `ONLINE`, capture plans, compare under identical conditions |
| `PROFILE` shows DB Hits but lacks Page Cache Hits/Misses | Edition/runtime does not emit those stats | Check DBMS-level metrics; do not conclude page cache is absent |
| Query via Java runs slower than Neo4j Browser | Differences in connections, serialization, result consumption, network | Time client/server phases and ensure identical result consumption |
| P95 rises under high load despite fast single runs | CPU/I/O contention, GC, tx memory, page cache eviction | Benchmark at realistic concurrency and watch system metrics |

**Special case:** a query like `MATCH (n) RETURN count(n)` can use the count store or similar optimizations, behaving very differently from reading properties across every node. To test store-access load, pick a query that actually reads properties or relationships, such as `sum(d.score)` in section 7's fixture. Never treat simple count queries as representative of all graph-traversal workloads.

## 12. Common Pitfalls in Performance Reasoning

**Pitfall 1 — “Higher DB Hits always means more disk reads.”**

`DB Hits` counts **logical access work** by the runtime against the storage layer. The same number of DB Hits can be served entirely from hot pages, resulting in far fewer actual disk reads.

**Pitfall 2 — “To make queries faster, just increase heap.”**

If queries are slow mainly due to page cache misses, increasing heap will not solve the issue and steals RAM from the page cache and OS. Conversely, if queries suffer from GC or heavy aggregation memory, increasing only the page cache can be futile.

**Pitfall 3 — “A restart produces a clean cold benchmark.”**

The OS has a filesystem cache, Neo4j has page cache warmup, and other traffic may touch pages. Call a run cold only when cache state is genuinely controlled and documented.

**Pitfall 4 — “PROFILE tells the exact latency the API will experience.”**

`PROFILE` adds observation overhead and runs on the database server, whereas an API call also includes network transit, serialization, entity mapping, and result consumption. Use both profiling and real end-to-end latency when evaluating production systems.

**Pitfall 5 — “Fast warm runs mean the Cypher query is optimal.”**

The page cache masks part of the I/O cost of a bad plan. On larger datasets, shifting working sets, or cold starts, unnecessary scans and expansions will surface again.

**Pitfall 6 — “Summing every operator's Memory (Bytes) column gives the required heap.”**

Those figures are **per-operator memory peaks**, which can occur at different moments; their sum does not reflect concurrent peak demand. Check the query footer and transaction/heap metrics to size capacity accurately.

## 13. Exercises with Answers

### Exercise 1 — Calculating Cache Hit Ratio

A run records `Page Cache Hits = 1,800` and `Misses = 200`. What is the hit ratio?

**Answer:** `1,800 / (1,800 + 200) × 100% = 90%`. This applies only to the scope and window of that measurement.

### Exercise 2 — Distinguishing Logical vs. I/O Optimization

Two runs of the same Cypher on the same data both show `DB Hits = 12,000`, yet misses are `850` on run 1 and `12` on run 2. What explains this?

**Answer:** logical work was nearly identical; pages loaded into the page cache on the first run required fewer loads on the second. Check `Rows`/plan and other factors before attributing the entire latency difference to disk.

### Exercise 3 — Verifying the Fixture

With the 10,000 nodes from section 7, the query:

~~~cypher
MATCH (d:QA008PerfDoc)
WHERE d.segment = 42
RETURN count(d) AS n, sum(d.score) AS s;
~~~

What is the exact result?

**Answer:** `n = 100` and `s = 200`. The result must remain exact regardless of scan vs. index seek and hot vs. cold cache.

### Exercise 4 — Diagnosing Memory Pressure

A query calling `collect()` on millions of elements spikes query memory and triggers heavy GC, yet hit ratio is nearly 100%. Should you prioritize growing the page cache or reviewing the query?

**Answer:** prioritize shrinking intermediate data (`collect`, `Sort`, `Expand`, `EagerAggregation`) and checking transaction memory and heap limits. A high hit ratio indicates the root cause lies outside the page cache.

### Exercise 5 — Designing a Fair Experiment

Group A runs the query right after creating an index; Group B runs after 20 warmup iterations. Can you conclude the difference is entirely due to the page cache?

**Answer:** no. Creating an index can change the execution plan and invalidate the query plan cache; early runs may also incur planning/JIT overhead. Fix the schema first, wait for the index to go `ONLINE`, record the plan, control page cache state, and separate the cohorts.

## 14. Cleaning Up the Practice Dataset

In the same practice database used in section 7:

~~~cypher
DROP INDEX qa008_perf_segment IF EXISTS;
~~~

~~~cypher
MATCH (d:QA008PerfDoc)
DETACH DELETE d;
~~~

Verify:

~~~cypher
MATCH (d:QA008PerfDoc)
RETURN count(d) AS remaining;
~~~

Expected result: `remaining = 0`.

## 15. Official References and Takeaways

- [Neo4j Cypher Manual — Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): meanings of `EXPLAIN`, `PROFILE`, `DB Hits`, `Memory (Bytes)`, and page cache metrics.
- [Neo4j Cypher Manual — Query caches](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/caching/): plan cache layers, parameter types, and schema-change effects.
- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/): splitting heap, native/OS memory, and page cache; configuration sizing.
- [Neo4j Operations Manual — Disks, RAM and other tips](https://neo4j.com/docs/operations-manual/current/performance/disks-ram-and-other-tips/): page cache warmup and I/O impacts.
- [Neo4j Operations Manual — Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/): page cache, JVM, and transaction metrics.
- [Neo4j Operations Manual — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/): exact setting names and version support.

When tuning Neo4j, inspect both **the execution plan** and **runtime memory state** together. A plan that performs little logical work keeps performance predictable; a page cache sized for the working set lowers data-loading costs. Only controlled measurements, consistent answers, and a clear cold/warm distinction let you verify which change genuinely improves application behavior.
