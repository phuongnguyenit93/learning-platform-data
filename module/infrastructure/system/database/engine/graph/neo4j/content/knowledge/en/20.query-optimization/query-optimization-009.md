# Measuring Latency, Throughput, and Resource Usage Under Realistic Load in Neo4j

## Learning Objectives

After this lesson, you will be able to:

- Design performance measurements **representative of realistic workloads** for Neo4j-backed applications, rather than benchmarking a single Cypher query on an empty database.
- Distinguish **latency**, **throughput**, **concurrency**, error rates, and resource metrics; interpret p50, p95, and p99 accurately.
- Measure at both the **application/Java Driver side** and **Neo4j side**, isolating connection acquisition wait time, query execution time, and result consumption time.
- Combine `EXPLAIN`/`PROFILE` with CPU, heap, page cache, I/O, transaction, and connection pool metrics to pinpoint bottlenecks.
- Run repeatable experiments, identify saturation thresholds, and verify whether an optimization truly improves user experience.

This lesson belongs to the **Query Optimization** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. A property graph application typically looks up nodes by key, expands relationships, queries paths in Cypher, writes transactions via the **Neo4j Java Driver** or **Spring Data Neo4j**, and may run batch imports. These tasks create distinct load profiles. Properly evaluating performance requires measuring **system behavior under realistic query mixes and traffic**, not just checking whether a single query uses an index.

> Thresholds, sample figures, and load scales in this lesson illustrate measurement methodology only. Do not treat them as Neo4j benchmarks or speed guarantees for any specific environment. Metric names and observability features vary by Neo4j version, edition, self-managed setup, or managed service.

## 1. Define Exactly What You Are Measuring

Suppose the `GET /customers/{id}/orders` API looks up a `Customer` by `customerId`, traverses `PLACED` relationships, filters `Order` by timestamp, and returns up to the 20 most recent orders. The Cypher query might look like:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.createdAt >= datetime($fromTime)
RETURN o.orderId AS orderId, o.createdAt AS createdAt
ORDER BY createdAt DESC
LIMIT 20;
~~~

A business request from browser to API and Neo4j passes through multiple stages:

~~~mermaid
flowchart LR
    A["Client sends request"] --> B["API and queues"]
    B --> C["Driver acquires connection"]
    C --> D["Neo4j executes Cypher"]
    D --> E["Transfer and consume all results"]
    E --> F["API processes and returns response"]
~~~

Distinguish the measurement scopes:

| Scope | Start – End | What It Reflects |
| --- | --- | --- |
| **End-to-end API latency** | HTTP request received until response sent | What the user experiences; includes app logic, queuing, network |
| **Application-side Neo4j operation latency** | Right before opening session/running tx until results are consumed and session closed | Includes pool/driver, network, retries, execution, and data reading |
| **Database-side query duration** | Per Neo4j monitoring/logs | Database processing portion; does not replace app-side measurement |
| **Cypher `PROFILE`** | Runs the query and gathers operator metrics | `Rows`, `DB Hits`, scan/seek/expand steps for root-cause diagnosis |

**Key point:** A `PROFILE` with low `DB Hits` does not guarantee low HTTP p99. Users may still wait because the connection pool is exhausted, the server is saturated, large payloads cross the network, or the app serializes slowly. Conversely, you cannot blame Neo4j for every API latency spike.

## 2. Core Metrics: Latency, Throughput, Concurrency, and Errors

### 2.1. Latency: Never Measure Only the Average

**Latency** is the duration to complete **one** operation, typically in milliseconds (ms). A system with many fast requests and a few very slow ones can show a **great average yet a poor user experience**. Always report percentiles:

| Metric | Interpretation | When Useful |
| --- | --- | --- |
| `p50` (median) | 50% of measurements are at or below this value | Typical case |
| `p95` | 95% of measurements are at or below this value | Tail experienced by many users |
| `p99` | 99% of measurements are at or below this value | Tail latency under heavy load |
| `max` | Largest measurement observed | Spotting anomalies, though noisy |
| `average` | Arithmetic mean | Useful supplement, never a substitute for percentiles |

Hypothetical example: p50 = 18 ms, p95 = 85 ms, and p99 = 270 ms. This indicates most requests are fast, while the tail takes significantly longer. Percentiles must be accompanied by **sample count**, measurement window, and request type.

**Never drop failed or timed-out requests from reports.** If you compute p99 only on successful requests and ignore 5% timeouts, the latency chart hides a severe outage. Report latency of successful requests alongside error counts, timeouts, and in-SLO completion rates.

### 2.2. Throughput: How Much Work Completes per Second?

Throughput measures the number of **completed** operations in a time interval:

\[
\text{Throughput (ops/s)}
=\frac{\text{Completed operations}}{\text{Measurement duration (seconds)}}
\]

For example, completing 12,000 requests in 120 seconds yields a throughput of **100 requests/s**. Across workloads, specify the unit clearly: **HTTP requests/s**, **Cypher queries/s**, **transactions/s**, **rows/s**, or **events/s**. One HTTP request may run multiple Cypher statements, so these units are not interchangeable.

Specifically distinguish:

- **Offered load:** intended request submission rate of the load generator.
- **Achieved throughput:** requests actually completed per second.
- **Timeouts/errors/retries:** failed or retried work; do not count every retry as a separate successful business transaction.

If the load generator sends 300 requests/s while the system completes only 190 requests/s, the system's throughput is not 300 requests/s.

### 2.3. Concurrency: How Many Operations Are In Flight?

**Concurrency** is the number of requests/transactions being processed simultaneously. It differs from throughput: adding more workers or connections does not automatically raise completed requests/s.

When a system is stable, drops no requests, and all metrics share the same scope, **Little's Law** gives an approximate relationship:

\[
L \approx \lambda W
\]

Here `L` is the average number of items in the system, `\lambda` is the completion rate (items/second), and `W` is the average time an item spends in the system (seconds). For instance, at 100 req/s and 0.05 s average duration, roughly 5 requests are concurrent **within the measured scope**. This is not a formula guaranteeing a server reaches a target rate, especially when load is unstable, queued, or saturated.

### 2.4. Specify Exact Definitions for Each Measurement

Before benchmarking, agree on:

1. What **one operation** means: an HTTP request, a managed transaction, or a single query?
2. Where the timer starts: before waiting for a connection or after acquiring one?
3. When the operation ends: after `run`, after `consume`/reading all records, or after sending the full HTTP response?
4. Are retries and timeouts included in latency?
5. Are reads routed to leader, follower, or multiple cluster instances? Are bookmarks used when causal read-after-write is required?

Without fixed definitions, two runs can easily show fake "improvements" merely from moving the stopwatch.

## 3. Building a Workload Representative of Business Traffic

Do not run `MATCH (n) RETURN count(n)` thousands of times and treat the numbers as your graph application's performance. Select a **query mix** grounded in logs and business data, for example:

| Workload Category | Assumed Share | Example | Pressure Profile |
| --- | ---: | --- | --- |
| **Key lookup** | 50% | Find `Customer` by `customerId` | Index seek, connections, cache |
| **Short traversal** | 25% | Customer → orders via `PLACED` | Branching factor, reading multiple nodes/relationships |
| **Multi-hop path** | 10% | `KNOWS*1..3` from a `Person` | Intermediate row explosion |
| **Transactional write** | 10% | Create/update `Order` and links | Write locks, tx log, constraints |
| **Batch import/sync** | 5% | `UNWIND` events with stable IDs | I/O, memory, transaction size |

These percentages are **illustrative only**. In real systems, derive distributions from telemetry or logs; separate online latency tests from long batch import jobs if they run on different schedules, and also test **concurrent** execution when they overlap operationally.

### Parameter Distributions Must Reflect Reality

Two queries running the same Cypher with different IDs can have vastly different costs:

- A customer with 2 orders vs. one with 500,000 orders both traverse `Customer` via `PLACED`, yet expand drastically different edge counts.
- A `Person` with 5 `KNOWS` edges vs. a celebrity with tens of thousands creates very different load.
- Querying the last 24 hours is usually far more selective than scanning an entire year.

Your test parameter set should include **hot keys, rare keys, high-degree nodes, zero-result queries, and time-varying inputs**. Never reuse one fixed ID for every request, or artificial caching will skew results.

### Graph Scale and Shape

Match not only total node count, but also:

- Relationship counts and *degree distribution*.
- Label proportions, relationship type ratios, and property selectivity.
- Property sizes, indexes/constraints, and percentage of newly written data.
- Hot/cold cache working sets and data growth over time.

A test graph with 10,000 uniformly distributed nodes will not simulate a production graph containing several **supernodes**. If you must use smaller sample data, document this limitation clearly in your conclusions.

## 4. Designing a Repeatable Load Test

### 4.1. Establish Conditions Before Measuring

Record **Neo4j version/edition**, database configuration, heap and page cache sizes, cluster topology, hardware, disk type, network, Java Driver version, connection pool limits, application instance count, index/constraint schema, and dataset size. Capture a **baseline** before changing any Cypher or settings.

Ensure indexes are ready:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

`ONLINE` means an index is built and ready, not that the query planner uses it. Index usage must be verified separately via `EXPLAIN`/`PROFILE`.

### 4.2. Warm-Up and Steady-State Measurement Window

A standard test sequence includes:

1. **Setup:** load data, verify business results, and ready connections.
2. **Warm-up:** run the mixed workload so JVM, driver, plan cache, page cache, and other components reach a representative state.
3. **Steady state:** measure over a window long enough to observe p95/p99, throughput, CPU, and GC. Pick duration based on precision needs rather than trusting a brief burst.
4. **Step-load testing:** ramp offered load across levels toward saturation; cap load to avoid unintended disruption.
5. **Teardown:** record versions, parameters, errors, charts, and verify data integrity after write operations.

**Cold cache** and **warm cache** are distinct scenarios. If users mostly query recently accessed data, warm cache is realistic. If batch jobs periodically scan most of the store after restarts, cold cache should also be measured. Never silently compare before/after across two different cache states.

### 4.3. Load Generation Models: Closed-Loop vs. Open-Loop

- **Closed-loop:** each worker waits for one request to finish before sending the next. When the server slows down, submission rate drops automatically, masking real-world backlog buildup.
- **Open-loop:** sends requests at a target rate independent of response time, exposing queuing, timeouts, and failure to keep up with offered load. The load generator must have sufficient capacity and log actual send rates.

In both models, never ramp concurrency while ignoring **timeouts, backlogs, or completion rate**. Once a system becomes unstable or overloaded, latency percentiles computed over completed requests no longer reflect total user experience.

## 5. Measuring Latency at the Java Driver and Spring Layers

### 5.1. Placing Timers at Business Operation Boundaries

The Java Driver example below measures fetching the 20 most recent orders; the timer covers opening the session, running the managed read transaction, and consuming all results. `System.nanoTime()` is suited for **elapsed intervals**, not wall-clock timestamps.

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public class OrderReadLatency {
    private static final String QUERY = """
        MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
        RETURN o.orderId AS orderId
        ORDER BY o.createdAt DESC
        LIMIT 20
        """;

    static long measureOnce(Driver driver, String customerId) {
        long started = System.nanoTime();
        try (Session session =
                     driver.session(SessionConfig.forDatabase("neo4j"))) {
            List<String> ids = session.executeRead(tx ->
                    tx.run(QUERY, Map.of("customerId", customerId))
                      .list(record -> record.get("orderId").asString()));

            // Results have been fully consumed before ending the timer.
            if (ids.size() > 20) {
                throw new IllegalStateException("Invalid result limit");
            }
        }
        return TimeUnit.NANOSECONDS.toMicros(
                System.nanoTime() - started);
    }

    public static void main(String[] args) {
        // Configuration example only: load credentials from secure storage.
        try (Driver driver = GraphDatabase.driver(
                "bolt://localhost:7687",
                AuthTokens.basic("neo4j", "password-from-config"))) {
            driver.verifyConnectivity();
            // For real benchmarks: warm up, run many representative IDs,
            // measure concurrently with a separate session per task.
            long micros = measureOnce(driver, "C-101");
            System.out.println("Elapsed (microseconds): " + micros);
        }
    }
}
~~~

This snippet measures a **single illustrative call**, not a statistically valid benchmark harness. Realistic testing needs many samples, controlled concurrent requests, post-window percentile calculation, and error tracking. Avoid printing to console per request inside timed sections, as logging I/O distorts numbers.

**Transaction note:** the `executeRead` callback may retry on transient errors recognized by the driver. Timing outside the callback captures total latency including retries; timing **inside** measures individual attempts. Both are useful and answer different questions.

Under concurrent load, share the **Driver** (designed to be shared) while creating a **separate Session per thread/request**; never share one Session across concurrent tasks. Pool sizes and cluster connections should fit the workload, though oversizing pools can worsen resource contention inside Neo4j.

### 5.2. Instrumenting Spring Data Neo4j

In Spring Boot applications using Spring Data Neo4j, monitor simultaneously:

- **HTTP server latency** and API error response rates.
- **Service method duration** per use case: key lookup, path finding, order creation.
- **Neo4j operation duration** (via instrumentation/metrics supported by your framework and driver versions).
- **Connection pool pending/acquired**, retries, and timeouts where exposed by your libraries and observability setup.

Micrometer/Actuator are commonly used to export metrics, though **metric names, tags, and automatic Neo4j instrumentation depend on version**; verify actual metric names before building dashboards. Avoid putting `customerId`, `orderId`, or raw Cypher containing personal data into **metric tags**, as high cardinality inflates memory and risks data exposure. Use stable tags such as `operation=read_customer_orders`, `result=success|error`, or `workload=graph_traversal`.

## 6. Observing Database-Side Resources in Neo4j

Queries getting slower under load are not necessarily caused by poor planner choices. Sometimes the planner picks the right index, yet the database saturates CPU, cache, or I/O. Collect resource metrics **aligned on the same timeline** as latency/throughput charts:

| Group | What to Observe | Diagnostic Signal |
| --- | --- | --- |
| **CPU** | Neo4j process CPU, host CPU, per-core load | Sustained high CPU paired with rising p95 and flat throughput |
| **Heap & GC** | Heap utilization, GC frequency/pause duration, JVM pools | Frequent GC pauses spike tail latency |
| **Page cache** | Size, hits/misses, page faults or related I/O | Misses or page faults climb once working set exceeds cache |
| **Disk / transaction log** | I/O throughput, I/O latency, log writes, checkpoints | Heavy write/import transactions turn I/O into the bottleneck |
| **Queries / transactions** | Active transactions, wait times, slow queries, errors | Lock contention, queuing, and abnormally slow queries |
| **Network / Bolt / driver pool** | In-use/waiting connections, network throughput, timeouts | Clients waiting on pool acquisition or large payload transfers |
| **Cluster** | Per-member load, read routing, replication/sync status where available | Skewed load, read-after-write lag, or replication wait |

Depending on deployment, use Neo4j-supported metrics, admin dashboards, host/container monitoring, query logs, and application telemetry. Do not assume every Neo4j version or Aura tier exposes identical metrics, log settings, or Prometheus/JMX endpoints. In production, enabling query logging or detailed tracing requires weighing **overhead**, sampling, and masking sensitive parameters.

### Page Cache and Heap Are Not the Same

**Heap** serves Java objects and JVM operations; **page cache** backs Neo4j's on-disk store access. Increasing heap does not fix an undersized page cache by itself. Meanwhile, over-allocating RAM across heap + page cache + OS and other processes can trigger out-of-memory failures.

When evaluating page cache, inspect hit/miss rates and I/O **by workload**. A high hit ratio does not prove a query is efficient if it still reads millions of unnecessary records in cache; missing indexes and excessive relationship fan-out still waste work.

### Higher Latency Does Not Automatically Mean Insufficient CPU

Suppose server CPU is only 40%, yet p99 surges. Possible causes include:

- Application connection pool is too small, leaving requests **waiting for a connection**.
- Write transactions hold locks that block other queries.
- Disk latency or I/O contention spikes before CPU saturates.
- Large payloads travel over a slow or congested network.
- A few requests hit extreme supernodes, dragging down the tail.

Correlate metrics **from the exact same time window** before scaling hardware or tweaking database settings.

## 7. Using EXPLAIN and PROFILE to Explain Metrics

Once realistic load testing flags a slow **operation**, take representative queries and inputs to inspect their plans:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = $status
RETURN o.orderId
LIMIT 20;
~~~

`EXPLAIN` builds the plan **without executing** the query. It reveals whether the database intends to use:

- `NodeUniqueIndexSeek` or `NodeIndexSeek` on `Customer.customerId` when schema matches;
- `NodeByLabelScan` / `AllNodesScan` when reading broadly;
- `Expand(All)` to traverse `PLACED` relationships;
- `Filter`, `Sort`, `Distinct`, or other operators downstream.

Where safe, run `PROFILE` to measure actual execution work:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = $status
RETURN o.orderId
LIMIT 20;
~~~

`PROFILE` **actually executes the query**, including writes and deletes; avoid running `PROFILE` carelessly in production. It adds instrumentation overhead, so **do not use PROFILE execution time as your primary benchmark latency**. Its purpose is showing **Rows, Estimated Rows, DB Hits, and operators** to explain why a workload is slow.

| Observed in PROFILE | Hypothesis | Next Step |
| --- | --- | --- |
| `AllNodesScan` reading nearly all nodes | Missing label or selective predicate | Add proper business predicates, consider suitable indexes |
| Large `NodeByLabelScan`, `Filter` keeps few rows | Filtered property needs an index | Check selectivity and property index |
| `NodeIndexSeek` yields 1 node, `Expand(All)` yields millions | High-degree node, massive relationship fan-out | Change starting point, adjust model/filter early, bound scope |
| `Sort` processes huge rows before `LIMIT` | Sorting large intermediate set | Filter/limit earlier or leverage a matching index |
| `CartesianProduct` over two large sets | Missing connection between patterns | Link patterns via appropriate relationship/predicates |

A query with an index seek **can still be slow** if it subsequently fans out across too many relationships. Conversely, a scan on a small set can be optimal. Never optimize solely to turn `Scan` into `Seek`.

## 8. Step-Load Analysis and Saturation Points

Rather than testing a single load level, hold data and query mix constant and measure across stepped offered-load levels. The table below is entirely **hypothetical**:

| Offered Load (req/s) | Completed (req/s) | Successful p95 (ms) | Successful p99 (ms) | Errors/Timeouts | Neo4j CPU |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 50 | 32 | 58 | 0% | 18% |
| 100 | 100 | 46 | 93 | 0% | 35% |
| 180 | 176 | 105 | 240 | 0.4% | 71% |
| 250 | 191 | 410 | 1,250 | 7% | 94% |
| 320 | 190 | 1,100 | 3,800 | 19% | 97% |

Interpretation: throughput scales nearly linearly at low load, then barely increases from 180 to 250 req/s despite much higher submission rates. Meanwhile, p95/p99, error rates, and CPU surge: the system is **approaching or past saturation**. Adding more worker threads here mostly increases wait times and failed requests.

To pinpoint the **true bottleneck**, you need supporting data: pool waits, queues, detailed CPU, GC, disk, and slow queries. An illustrative summary table **is not enough** to conclude whether to add CPU or fix an index.

### Setting Thresholds by SLO

Suppose an internal SLO requires:

- Completing **at least 99.9%** of valid requests during the measurement window;
- Order-read p95 **below 150 ms**;
- Sustaining **150 requests/s** under the target business query mix;
- Without degrading critical write throughput or pushing lock waits above acceptable bounds.

These targets must be agreed upon with product and stakeholders, not treated as "Neo4j's default SLO." Acceptable capacity is the load meeting **latency + throughput + errors + resource headroom** together, not raw maximum requests/s.

## 9. Pitfalls That Skew Benchmarks

### Pitfall 1: Using Only One Customer or Parameter

Repeating the same `customerId` exploits a tiny cached working set and misses high-degree nodes. Use a wide set of IDs with representative hot/cold distributions, including non-matching queries.

### Pitfall 2: Timing Only Until `run()` Returns

Driver APIs may return a result handle before all records are transferred and consumed. Too-short timers miss network streaming and result materialization. Measure until all **needed results are consumed**.

### Pitfall 3: Changing Workload Mix Between Runs

If one run has 90% simple lookups and another has 30% multi-hop path queries, results are incomparable. Keep query ratios, data, parameters, duration, and environment identical.

### Pitfall 4: Saturating the Load Generator Itself

CPU, network, or thread pools on the load generator can become the bottleneck. Log actual offered load, client queuing, and generator overhead. If the generator fails to hit target send rates, do not blame Neo4j for the ceiling.

### Pitfall 5: Reporting Only Successful Requests

When slow requests time out, remaining completed requests are artificially faster, making p95 look better than reality. Report **latency alongside error rates, timeouts, retries, and incomplete requests**.

### Pitfall 6: Averaging p95 Values Across Time Windows

You cannot average per-minute p95 values and call it the overall p95. Percentiles must be computed from the **combined sample distribution** or properly mergeable histograms under uniform filters.

### Pitfall 7: Optimizing Reads While Ignoring Write Impact

Adding indexes can speed up lookups while adding work to `CREATE`/`SET`/`DELETE`. Re-measure write throughput, batch import duration, storage footprint, and tail latency under mixed read/write load.

### Pitfall 8: Treating PROFILE Output as the Final Benchmark

`PROFILE` helps analyze plans, but introduces overhead and does not simulate multi-threaded transactions, pooling, networking, API serialization, or realistic mixes. Use **application-level benchmarks** as your primary metric and `PROFILE` to explain them.

## 10. Evidence-Based Optimization and Re-Measurement Loop

Follow an iterative workflow:

~~~mermaid
flowchart TD
    A["Select operation and SLO"] --> B["Measure baseline under realistic workload"]
    B --> C["Isolate p95/p99, errors, and resources"]
    C --> D["EXPLAIN/PROFILE suspect queries"]
    D --> E["Change only one group of factors"]
    E --> F["Re-run same workload and data"]
    F --> G{"Are SLO and resources better?"}
    G -->|Yes| H["Record results and roll out with controls"]
    G -->|No| C
~~~

Candidate changes include:

- **Cypher:** add labels/types, filter on keys early, reduce traversed paths, return only needed fields, eliminate accidental `CartesianProduct`s.
- **Schema:** add range indexes or uniqueness constraints matching actual predicates; avoid unbounded indexing.
- **Data model:** rework queries starting from high-degree nodes, cut unnecessary fan-out, or add supporting relationships/properties for critical queries where justified.
- **Application:** share Driver instances, close Sessions properly, consume results carefully, tune pool/timeout settings to load, and batch writes safely while preserving transaction semantics.
- **Operations:** check CPU, page cache, heap, GC, disk, network, and workload scheduling before upgrading hardware.

Test **one group of changes at a time** or isolate effects cleanly. Always report **trade-offs**: new indexes consume storage, rewritten queries risk semantic differences, large batches lengthen transactions, and oversized pools increase contention.

### Before/After Comparison Template

| Metric | Before Optimization | After Optimization | Interpretation Rule |
| --- | --- | --- | --- |
| p50/p95/p99 of **same operation** | Record | Record | Did tail latency improve? |
| Completed throughput at same offered load | Record | Record | Are more operations finishing? |
| Errors/timeouts/retries | Record | Record | Are we trading reliability for speed? |
| CPU, GC, page cache, disk, network | Record | Record | Did the bottleneck merely shift elsewhere? |
| `Rows` and `DB Hits` on suspect plans | Record | Record | Is the query reading less wasted data? |
| Business data correctness | Test | Test | Output must preserve exact semantics |

Never declare a lower p95 from a **lower-load** run an optimization. Compare fairly at fixed offered load and query mix, then compare maximum sustainable SLO capacity.

## 11. Practice Exercise: Evaluating an Order Query

**Context:** A graph has `Customer`, `Order`, `PLACED` relationships, and an API listing a customer's 20 most recent orders. The goal is meeting your team's SLO when 20% of customers have far more orders than typical.

**Step 1 — Inspect query and schema.** Prepare a parameter set containing low-order customers, high-order customers, and non-existent IDs. Check indexes:

~~~cypher
SHOW INDEXES
YIELD name, entityType, labelsOrTypes, properties, state
RETURN name, entityType, labelsOrTypes, properties, state;
~~~

Then run:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

**Step 2 — Predict cost.** If one customer has 500,000 orders, ask whether `LIMIT 20` automatically stops `Expand(All)` from traversing many edges or `Sort` from processing many results. Answer: **not guaranteed**; it depends on the plan and access order. Verify via measurements.

**Step 3 — Generate load.** Run at three offered-load levels, e.g., 30/80/150 req/s. Warm up first, then measure over several minutes to collect enough samples for p95/p99; report errors and incomplete requests.

**Step 4 — Observe Neo4j concurrently.** Collect CPU, GC, page cache, disk, transactions, and connection pool metrics (where available) on the same timeline. Note what happens when p99 climbs.

**Step 5 — Diagnose.** Use `PROFILE` on the **read-only** query with several representative customers. Check `Expand(All)` rows, rows entering `Sort`, and DB Hits. Do not substitute `PROFILE` duration for benchmark latency.

**Step 6 — Test one improvement.** For instance, add a business-valid date predicate, bound the traversal range, or consider starting from `Order` if an index and constraint identify the customer properly. Any rewrite must return the **exact expected order list**.

**Step 7 — Re-measure the exact same workload.** Compare p50/p95/p99, throughput, errors, and resource usage; explain why a change might help low-order customers while behaving differently for high-degree customers.

### Self-Check Questions

1. **Is a better p95 alongside timeouts rising from 0% to 8% an improvement?** No—you must evaluate reliability and include failed requests.
2. **Adding 50 connections left throughput flat while p99 rose. Why?** The server may already be saturated, experiencing higher contention or altered queuing; inspect pools and resources before scaling connections further.
3. **`NodeIndexSeek` appears—is the query guaranteed to be fast?** No. `Expand(All)`, `Sort`, or returning huge payloads may dominate cost.
4. **Can you directly compare p99 across two runs with very different durations and sample sizes?** Only with extreme caution; check stability and sample adequacy while keeping the workload identical.
5. **Why monitor both the application and the database?** To separate delays from Java Driver/pooling/network/API from delays in Cypher execution, caching, or Neo4j resources.

## 12. Performance Testing Implementation Checklist

- [ ] Clearly define **operation**, timer boundaries, SLOs, timeouts, and retry accounting.
- [ ] Select representative data across labels, types, properties, relationship degrees, and hot/cold parameters.
- [ ] Build a realistic read/write/traversal/import mix and arrival rate; test concurrent workloads where they overlap.
- [ ] Run controlled warm-up, steady-state measurement, and identical environment between baseline and optimization.
- [ ] Collect **p50/p95/p99, completed throughput, offered load, concurrency, errors, and timeouts**.
- [ ] Correlate CPU, heap/GC, page cache, disk, network, transactions, and connection pools over the same window.
- [ ] Use `EXPLAIN` for plan inspection and scoped `PROFILE` for `Rows`, `DB Hits`, and scan/index/expand analysis.
- [ ] Document versions, schema, configuration, load generator setup, and environment limitations.
- [ ] Verify Cypher/index changes preserve business correctness and leave no unintended side effects during write benchmarks.
- [ ] Compare results at **equal load**, then determine saturation points and SLO-compliant capacity.

**Conclusion:** Measuring Neo4j query optimization properly combines **end-to-end latency**, **achieved throughput**, **error rates**, **resource utilization**, and **execution plans** under a representative workload. A query that runs fast in isolation does not prove the system performs well when concurrent requests, transactions, and graph paths compete for resources. Use consistent before/after measurements to isolate bottlenecks, prove optimization gains, and make informed operational tuning decisions.
