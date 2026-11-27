# Latency, Throughput, Locks, and Failed Transaction Metrics

An application using Neo4j may still return correct data while gradually slowing down: an API takes 2 seconds instead of 100 ms, write transactions wait on locks, or Java Driver retries inflate latency even though end users see no exceptions. To find the root cause, looking only at CPU or Bolt connection count is not enough. You must combine **latency**, **throughput**, **lock contention**, and **failed/rolled-back transactions**, and then correlate them with **actual Cypher queries**.

This lesson belongs to the **Monitoring** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module covers property graphs, nodes, relationships, Cypher, indexes, constraints, data import, the Java Driver, Spring Data Neo4j, and Neo4j operations. The four signal groups below connect application-layer performance to database query and transaction activity, showing whether to fix Cypher, relationship modeling, indexes, transaction duration, or resource configuration.

> **Version and environment note:** Examples reflect capabilities of Neo4j 5 and newer release families. **Neo4j Enterprise Edition** provides a rich metrics system (CSV/JMX/Prometheus/Graphite); Neo4j Community and Aura tiers differ in observability scope, export mechanisms, and privileges. Metric names, `SHOW TRANSACTIONS` columns, and log configurations can vary across versions. Before building dashboards, verify **actually exported metrics** and documentation for your exact running version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **application-perceived latency**, **Neo4j server execution latency**, lock wait time, and connection acquisition time.
2. Calculate queries/second and transactions/second properly from **counters**, never mistaking cumulative counter values for instantaneous rates.
3. Read `SHOW TRANSACTIONS` to spot long-running, lock-waiting, and heavily lock-holding transactions.
4. Distinguish **failed queries**, **rolled-back transactions**, **terminated transactions**, and **deadlocks**.
5. Combine query logs, metrics, `EXPLAIN`/`PROFILE`, and Java Driver/SDN instrumentation to investigate slow queries.
6. Design dashboards and alerts grounded in baselines, SLOs, Neo4j version capabilities, and workload characteristics.

## 2. Viewing Signals Across Three Distinct Layers

A `GET /orders/{id}` request may pass through:

~~~mermaid
flowchart LR
    U["Client / API"] --> A["Java Service / Spring Data Neo4j"]
    A --> P["Java Driver<br/>connection pool, retry, routing"]
    P --> B["Bolt / Neo4j Server"]
    B --> Q["Cypher planner + execution"]
    Q --> L["Graph store<br/>indexes, relationships, locks"]
    L --> Q --> B --> P --> A --> U
~~~

**User-perceived latency** can include web server queuing, Java logic, connection acquisition, DNS/TLS, networking, routing, retries, Cypher execution, Bolt streaming, and object mapping. Meanwhile, **Neo4j server query latency metrics** measure a specific server-side stage; they do not replace end-to-end API latency.

| Measurement Layer | What Is Commonly Measured? | When Is It Useful? |
|---|---|---|
| **Application / API** | Request latency, error rate, repository timing, retry count | Quantifying user impact and SLO compliance |
| **Driver / connectivity** | Connection acquisition wait, connection timeouts, retries, in-use connections | Distinguishing DB slowness from pool wait, network, or routing |
| **Neo4j Server** | Query latency, query success/failure, active/committed/rolled-back transactions, locks, CPU, heap, page cache | Pinpointing bottlenecks inside the database |

Never equate these three measurements merely because they share milliseconds as a unit.

## 3. Four Core Signal Groups

| Group | Operational Question | Metrics to Watch | Follow-Up Analysis |
|---|---|---|---|
| **Latency** | Are users experiencing slowness? Which queries are slow? | Endpoint/query p50, p95, p99; server execution histogram | Compare client vs. server, classify queries, `PROFILE` |
| **Throughput** | How many queries and transactions complete per second? | Queries/s, commits/s, writes/s, concurrent transactions | Compare against load and resource headroom |
| **Locks** | Which transactions are waiting on each other or holding locks long? | `waitTime`, `currentQueryWaitTime`, `activeLockCount`, active transaction count | Trace hot queries/resources, reduce contention |
| **Failed transactions** | Which transactions rolled back, were terminated, or deadlocked? | `rollbacks`, `rollbacks_write`, `terminated`, `rollbacks_deadlocked` if available, error codes | Classify errors, check retry/timeout/idempotency |

A **latency spike** may stem from lock contention, but it can equally stem from missing indexes, overly broad relationship expansions, heap/GC pressure, page-cache misses, or CPU saturation. Look at **correlations across metrics** instead of jumping to conclusions from one chart.

## 4. Latency: Measure at the Right Boundaries

### 4.1. Application Latency vs. Database Latency

Example of a request taking 260 ms total:

~~~text
Request /orders/O01         = 260 ms end-to-end (hypothetical example)
  Java and validation       = 25 ms
  Connection / routing      = 35 ms
  Neo4j query execution     = 100 ms
  Transfer + result mapping = 70 ms
  Other steps               = 30 ms
~~~

These are **illustrative numbers**, not measurements from a specific Neo4j deployment. They illustrate why a 100 ms server query can produce a 260 ms API call. In reality, phases can **overlap** as the driver streams records while the application processes them concurrently, so phase timings cannot always be summed linearly.

Name measurements clearly:

- `http.request.duration`: HTTP request completion time per endpoint from the application's view.
- `repository.operation.duration`: repository/service call duration until required results are processed.
- `driver.connection.acquire.duration`: wait time to acquire a connection from the pool, **when instrumented by the application**.
- `neo4j.query.execution.latency`: server execution duration as defined by the corresponding metric.

The first three names are **application-defined example metric names**, not mandatory built-in Neo4j Driver defaults. When instrumenting with Micrometer/OpenTelemetry, use the exact names and units emitted by your instrumentation library.

### 4.2. p50, p95, and p99 Are Not Averages

**Percentiles** describe latency distributions:

- **p50:** roughly half of requests complete at or below this mark; approximately the median.
- **p95:** roughly 95% of requests complete at or below this mark; the remaining 5% are slower.
- **p99:** focuses on the slowest tail, often critical for spotting erratic user experience.

Example (hypothetical data):

| Endpoint | p50 | p95 | p99 | Notes |
|---|---:|---:|---:|---|
| `GET /orders/{id}` | 25 ms | 95 ms | 320 ms | Slow tail worth inspecting |
| `POST /orders` | 50 ms | 180 ms | 1,200 ms | Likely affected by writes/locks/retries |
| `GET /recommendations` | 130 ms | 490 ms | 2,100 ms | Check traversal breadth and result size |

If figures are measured over different time windows or different request populations, comparisons are invalid. Always specify **measurement window**, unit, sample count, endpoint, and breakdown by success/failure.

**Never take an arithmetic average of per-machine p95s to compute system-wide p95.** To aggregate percentiles accurately, merge distributions/histograms or raw sample data using tooling-supported aggregation.

### 4.3. Neo4j Histograms and Interpretation Limits

In the Enterprise metric family published by Neo4j, query latency follows a logical form like:

~~~text
<prefix>.db.query.execution.latency.millis
~~~

This is a **histogram of execution times for successful queries** in milliseconds. Related metrics can include:

~~~text
<prefix>.db.query.execution.success
<prefix>.db.query.execution.failure
~~~

The last two are **counters**, unlike the latency histogram. Do not use **successful query** latency to conclude that failing queries aren't making users wait: timeouts or queries failing after long runs still hurt API latency without appearing fully in that success histogram.

**Query metrics** and **transaction metrics** also count different units: one transaction can execute multiple Cypher statements. With `CALL { ... } IN TRANSACTIONS`, one outer statement can spawn many inner sub-transactions. Never force "1 API call = 1 Cypher query = 1 transaction".

## 5. Throughput: Computing Rates from Counters

**Throughput** is completed work per unit time, such as `queries/s`, `transactions/s`, or `rows/s`. First clarify **succeeded** vs. **started**, **reads** vs. **writes**, and whether the counter covers an entire DBMS or a specific database.

| Quantity | Conceptual Calculation | Unit |
|---|---|---|
| Successful query throughput | `ΔsuccessfulQueries / Δseconds` | query/s |
| Failed query rate | `ΔfailedQueries / Δseconds` | failed query/s |
| All completed query rate | `(Δsuccess + Δfailure) / Δseconds` | query/s |
| Committed transaction throughput | `ΔcommittedTransactions / Δseconds` | committed tx/s |
| Committed writes throughput | `ΔcommittedWriteTransactions / Δseconds` | committed write tx/s |
| Rollback rate | `ΔrolledBackTransactions / Δseconds` | rolled-back tx/s |

`Δcounter = counter(t2) − counter(t1)` from the same source and active epoch; **never divide the current cumulative counter by one second**. Counters reset when a server restarts, a metrics exporter changes, or a database is recreated; in Prometheus, `rate(...)`/`increase(...)` handle counter resets within collection limits.

### Five-Minute Window Calculation Example

Suppose a system has one business database and counters are sampled over the **same 300-second window**:

| Counter | Window Start | Window End | Delta |
|---|---:|---:|---:|
| Query success | 120,000 | 121,800 | 1,800 |
| Query failure | 700 | 760 | 60 |
| Transaction started | 43,000 | 43,950 | 950 |
| Transaction committed | 42,000 | 42,900 | 900 |
| Transaction rolled back | 900 | 950 | 50 |

Calculations:

~~~text
Successful query throughput   = 1800 / 300         = 6.0 query/s
All completed query rate      = (1800 + 60) / 300  = 6.2 query/s
Query failure ratio           = 60 / (1800 + 60)   ≈ 3.23%
Committed tx throughput       = 900 / 300          = 3.0 tx/s
Rolled-back tx rate           = 50 / 300           ≈ 0.167 tx/s
Rollback fraction (reference) = 50 / (900 + 50)    ≈ 5.26%
~~~

**These are illustrative numbers, not measured production output.** In real systems, `started`, `committed`, and `rollbacks` may not balance exactly over a window boundary because transactions start before, finish after, or stay open. Nor does `query failures` always equal `rolled-back transactions`.

### Throughput Alone Does Not Prove Health

When throughput drops, there are at least two very different scenarios:

1. **Lower demand:** the API receives fewer requests, latency stays low, and errors do not rise.
2. **System bottleneck:** incoming request rate is high while **completed** requests/tx drop, and queues and latency climb.

To tell them apart, compare **application request arrival rate** against **completion rate**, concurrent transactions, pool waits, CPU, GC, and timed-out requests.

### Concurrency Is Not Throughput

`transaction.active` is a **gauge** of active transactions at the instant of sampling. It is not `transactions/s`. High concurrency may indicate long read queries, large imports, or contention; always check the latency distribution alongside it.

A helpful intuition for stable systems is **Little's Law**: average work in the system approximates `arrival rate × average time in system`, provided boundaries and conditions match. For example, 20 requests/s averaging 0.2 seconds corresponds to roughly 4 concurrent requests inside that boundary. Never apply this formula directly to active transaction counts when requests spend substantial time outside Neo4j.

## 6. Key Neo4j Metrics

Neo4j separates **global** DBMS metrics from **per-database** metrics. With the default prefix `neo4j` and an example database `orders`, a transaction metric takes the form:

~~~text
neo4j.database.orders.transaction.committed
~~~

The prefix is configurable via `server.metrics.prefix`; the Prometheus exporter **transforms names** (for example, dots become underscores with type suffixes). **Never hard-code** a Prometheus metric name without inspecting actual `/metrics` output first.

| Logical Metric in Docs | Type | Interpretation |
|---|---|---|
| `<prefix>.dbms.bolt.connections_running` | Gauge | Bolt connections actively executing Cypher and returning results |
| `<prefix>.db.query.execution.success` | Counter | Queries completed successfully |
| `<prefix>.db.query.execution.failure` | Counter | Queries that failed |
| `<prefix>.db.query.execution.latency.millis` | Histogram | Execution latency distribution of successful queries |
| `<prefix>.database.<db>.transaction.started` | Counter | Transactions started |
| `<prefix>.database.<db>.transaction.active` | Gauge | Currently active transactions |
| `<prefix>.database.<db>.transaction.active_read` | Gauge | Currently active read transactions |
| `<prefix>.database.<db>.transaction.active_write` | Gauge | Currently active write transactions |
| `<prefix>.database.<db>.transaction.committed` | Counter | Transactions committed |
| `<prefix>.database.<db>.transaction.committed_write` | Counter | Write transactions committed |
| `<prefix>.database.<db>.transaction.rollbacks` | Counter | Transactions rolled back |
| `<prefix>.database.<db>.transaction.rollbacks_write` | Counter | Write transactions rolled back |
| `<prefix>.database.<db>.transaction.terminated` | Counter | Transactions terminated |
| `<prefix>.database.<db>.transaction.peak_concurrent` | Counter/gauge peak per docs | Recorded peak concurrency; not current active count |

**The `transaction.rollbacks_deadlocked` metric** tracking transactions rolled back due to deadlocks **was only introduced in Neo4j 2026.01**. On older Neo4j 5.x deployments, this metric may **not exist**; rely on logs/deadlock error codes and version-appropriate metrics rather than assuming an empty chart means zero deadlocks.

Do not turn every metric into an "error assumption": rising `active` may reflect legitimate data imports; `rollbacks` may include intentional rollbacks; `terminated` may reflect manual admin intervention. **Always correlate with workload and context.**

## 7. Locks: Detecting Contention via Active Transactions

Neo4j uses locks to protect node/relationship updates. If two transactions attempt to update the same locked node concurrently, one transaction must **wait**. Lock waiting often surfaces as high latency even when the query performs no large scan.

### 7.1. Inspecting Transactions with Cypher

With an account authorized to inspect transactions:

~~~cypher
SHOW TRANSACTIONS
YIELD database, transactionId, username, status,
      elapsedTime, waitTime, activeLockCount,
      currentQuery, currentQueryWaitTime
RETURN database, transactionId, username, status,
       elapsedTime, waitTime, activeLockCount,
       currentQueryWaitTime, currentQuery
ORDER BY waitTime DESC
LIMIT 20;
~~~

Relevant fields:

| Field | Interpretation | Limitations |
|---|---|---|
| `transactionId` | Identifier of the observed transaction | Not a business key; do not use as a long-term ID |
| `username` | User running the transaction | Visibility depends on current user's privileges |
| `status` | Server-reported state at sampling time | Point-in-time snapshot; may change immediately after `SHOW` |
| `elapsedTime` | Total lifetime of the transaction | Covers multiple phases, not solely lock wait time |
| `waitTime` | **Cumulative time spent waiting for locks** in this transaction | Does not guarantee the transaction is **currently** blocked at inspection time |
| `currentQueryWaitTime` | Lock wait time of the current query, if any | May be `null` when no query is active |
| `activeLockCount` | Number of locks currently held by the transaction | **Many locks do not automatically mean** contention or blocking |
| `currentQuery` | Currently executing Cypher text | May contain sensitive data; requires proper privileges and logging rules |

Filter transactions with significant lock wait time **in the current snapshot**:

~~~cypher
SHOW TRANSACTIONS
YIELD database, transactionId, username, status,
      elapsedTime, waitTime, activeLockCount, currentQuery
WHERE database = 'neo4j'
  AND waitTime > duration({seconds: 1})
RETURN transactionId, username, status,
       elapsedTime, waitTime, activeLockCount, currentQuery
ORDER BY waitTime DESC;
~~~

This is an **observational read query**—it does not block or terminate transactions. `waitTime > 1s` means the transaction has accumulated over one second waiting on locks, **not necessarily that it is waiting right now**. To confirm active blocking at that instant, combine `status`, version-supported transaction details, repeated samples, and query logs.

### 7.2. Diagnosing Lock Contention with Multiple Signals

Suppose concurrent requests update the same `:Account {accountId:'A01'}`. One transaction holds the write lock while others wait:

~~~text
TX-1: update A01 ---- holds write lock ----- COMMIT
TX-2: update A01 .... waits for lock ....... update / COMMIT
TX-3: update A01 .... waits for lock ............... update / COMMIT
~~~

Signals supporting a contention hypothesis:

1. **Write API p95/p99 climbs** during the same window.
2. `SHOW TRANSACTIONS` shows multiple transactions with high `waitTime`/`currentQueryWaitTime`.
3. A long-lived transaction holds locks, active write transactions rise, or application backlogs build up.
4. Query logs reveal `SET`/`MERGE` statements colliding on the same business keys.
5. If deadlocks occur, logs, error codes, or `rollbacks_deadlocked` (where supported) increase.

**Never infer** that every transaction with a large `activeLockCount` is causing contention. A valid import transaction may hold many locks while zero other requests wait on them.

### 7.3. Effective Ways to Reduce Contention

- **Shorten transactions:** never make HTTP API calls, send emails, or run slow processing inside a lock-holding transaction.
- **Eliminate "hot nodes":** redesign patterns that increment/update a single super-popular node under heavy write concurrency.
- **Standardize lock ordering:** when updating multiple nodes, acquire/touch them in a consistent order to reduce deadlock risk.
- **Tune batch sizes:** massive import batches hold locks and memory for prolonged durations.
- **Avoid unbounded parallelism:** too many concurrent writers hitting the same lock set can degrade throughput and spike latency.
- **Optimize node lookup before updating:** use indexes and selective filters, while remembering that fast index lookup **does not eliminate** write contention on the same node.

## 8. Deadlocks and Failed Transactions: Don't Lump Everything into One Number

### 8.1. Different Termination Outcomes

| Outcome | Meaning | Is It Always an Error? |
|---|---|---|
| Query success | A Cypher statement executed successfully | Does not mean the entire transaction committed if later steps exist |
| Query failure | A Cypher statement failed | May cause the transaction to roll back |
| Transaction committed | Transaction finished with commit | May be read-only; does not imply nodes were created |
| Transaction rolled back | Transaction discarded uncommitted changes | May be due to error, cancellation, or intentional rollback |
| Transaction terminated | Transaction was forcefully stopped | Inspect reason: timeout, admin kill, policy cancellation, etc. |
| Deadlock detected | Cyclic lock wait/hold forced Neo4j to abort one transaction | Typically transient; requires proper retry handling |

When Neo4j detects a deadlock, a familiar error code is:

~~~text
Neo.TransientError.Transaction.DeadlockDetected
~~~

On newer drivers/servers, `GQLSTATUS`, cause chains, and classification metadata may also be present. Log **exception class, Neo4j code, GQLSTATUS (if present)**, and transaction/query IDs; never classify errors solely by `getMessage()` text.

### 8.2. Why Query Failures Do Not Equal Transaction Rollbacks

A single transaction can run multiple Cypher queries; one failed query can roll back the whole transaction. Conversely, an application can intentionally roll back a transaction **with zero query errors**. Furthermore:

- A transaction **started** in one window may **commit** in the next window.
- A single transaction can execute multiple **queries**.
- The Java Driver may **retry managed transactions**, so server-side attempts can exceed final API-level failures.
- With `CALL { ... } IN TRANSACTIONS`, many inner transactions may commit before the outer job hits an error.

Therefore, dashboards should display query failures, transaction rollbacks, and application error rates **separately**—never sum them together as "total errors".

### 8.3. Classifying Errors to Decide on Retries

| Error Group | Examples | Initial Handling |
|---|---|---|
| Invalid request | Cypher syntax, insufficient privileges, constraint violation | Fix query/role/data; do not retry verbatim |
| Transient error | Deadlock, leader switch, brief disconnect | Bounded retry when callback/idempotency is safe |
| Resource exhaustion | Transaction timeout, heap/GC pressure, disk full | Investigate root cause and cap retries |
| Intentional abort | Application cancellation, admin terminate | Separate from system failures; log reason |
| Uncertain commit | Connection dropped right as server committed | Check idempotency key before re-running writes |

When using `session.executeRead(...)` or `session.executeWrite(...)`, the driver automatically retries errors classified as transient within its configured retry budget. **Do not add unbounded API-layer retry loops** without accounting for existing driver retries. For writes, guard operations with **business keys/constraints** to avoid duplicate writes when commit outcomes are uncertain.

## 9. Exporting Metrics to Observability Systems

In **self-managed Neo4j Enterprise**, export channels can include CSV, JMX, Graphite, and Prometheus. For Prometheus, an example `neo4j.conf` configuration:

~~~properties
# Enterprise self-managed - illustrative localhost endpoint configuration.
server.metrics.prometheus.enabled=true
server.metrics.prometheus.endpoint=localhost:2004
~~~

After applying and restarting per version requirements, a Prometheus scraper can collect from authorized locations. **Never expose `0.0.0.0:2004` to the public Internet**; for remote scraping, use internal networks/tunnels/proxies with authentication, TLS, and firewall rules. Metrics endpoints can reveal operational state, load, and infrastructure metadata.

### Gauges, Counters, and Histograms Must Be Handled Differently

| Type | Examples | Proper Visualization |
|---|---|---|
| **Gauge** | Transaction `active`, Bolt `connections_running` | Plot raw values over time; check current level/peaks |
| **Counter** | `committed`, `rollbacks`, query `success`/`failure` | Compute `rate` or `increase` over windows; handle resets |
| **Histogram** | Query execution latency | Compute percentiles/quantiles matching histogram/exporter semantics |

Metric names in Neo4j docs use dots; Prometheus-exported names convert punctuation and append type suffixes. Before writing PromQL queries:

1. Inspect what metrics and types the endpoint actually emits.
2. Read the `HELP`/`TYPE` lines in the Prometheus payload.
3. Distinguish prefix, database name, server instance, and exporter-added labels.
4. Determine whether query rates are **server-wide** or per database/cluster; avoid double-counting across routing/replication layers.
5. Account for exporter/Neo4j upgrades or counter resets.

**Never aggregate per-instance quantiles using `avg`.** To compute system-wide p95, aggregate compatible histogram buckets or compute from underlying sample distributions.

## 10. Query Logs: Connecting Charts to Specific Cypher Queries

Metrics reveal **that a problem exists**, while query logs reveal **which query** is involved. On Neo4j versions supporting query logging, an illustrative `neo4j.conf` setup for testing:

~~~properties
# Log only queries finishing slower than threshold; tune per policy.
db.logs.query.enabled=INFO
db.logs.query.threshold=250ms
db.logs.query.parameter_logging_enabled=false
~~~

In many modern Neo4j versions, `INFO` logs completed queries exceeding the threshold, while `VERBOSE` can log both start and completion. **Never assume** every version shares the same defaults. To diagnose transactions left open long after a query finishes, documentation supports transaction lifecycle logging:

~~~properties
# Illustrative; enable selectively only when diagnosing.
db.logs.query.transaction.enabled=INFO
db.logs.query.transaction.threshold=1s
~~~

**Query logs are not transaction logs (WAL).** Transaction logs serve durability/recovery and record data mutations; query logs serve query/timing/error observability and are not a complete replica of every committed transaction.

### Fields Readable from Query Logs

Depending on format and version, logs can report query ID, transaction ID, database, user, elapsed time, planning time, CPU time, page hits/faults, wait time, success/failure status, and error codes. These fields help answer:

- Was time spent in **planning**, **execution**, **lock waiting**, or post-query idle wait before commit?
- Is a query **repeating excessively** (N+1) from Spring Data Neo4j?
- Is the same query template slow only for certain low-selectivity parameter sets?
- Did a p99 spike coincide with **rollbacks/deadlocks** or **index/schema changes**?

Never enable logging of all parameters/literals recklessly, because Cypher parameters may carry emails, tokens, and customer data. Beyond `parameter_logging_enabled=false`, newer versions provide literal/error obfuscation options; still enforce strict log read access and retention limits. Never write connection-string credentials into dashboards.

## 11. Timing from the Java Driver and Spring Data Neo4j

Server metrics do not replace timing **real repository calls**. A simple example measuring an entire read operation with `executeRead`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderMonitor {
    private final Driver driver;

    public OrderMonitor(Driver driver) {
        this.driver = driver;
    }

    public List<String> findOrderIds(String customerId) {
        long startedAt = System.nanoTime();
        boolean success = false;
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {

            List<String> ids = session.executeRead(tx -> tx.run("""
                    MATCH (c:Customer {customerId: $customerId})
                          -[:PLACED]->(o:Order)
                    RETURN o.orderId AS id
                    ORDER BY id
                    """, Map.of("customerId", customerId))
                    .list(record -> record.get("id").asString()));

            success = true;
            return ids;
        } finally {
            long elapsedNanos = System.nanoTime() - startedAt;
            long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
            // Replace with Micrometer/OTel in a real application:
            System.out.printf("operation=findOrderIds,success=%s,elapsedMs=%d%n",
                    success, elapsedMillis);
        }
    }
}
~~~

This example **illustrates** timer placement, not a production monitoring system. In production, replace `System.out.printf` with cardinality-safe metrics and structured logging; never use `customerId` directly as a metric label (it explodes cardinality and risks PII leakage).

Important notes:

1. `startedAt` starts before opening the session, so elapsed time **includes** connection acquisition, transaction management, query execution, full record consumption, and session closure.
2. `executeRead` is a **managed transaction**, so driver retries inside the callback raise **single-request latency** even when the call ultimately succeeds.
3. `.list(...)` consumes all returned records inside the callback; calling `tx.run(...)` without draining `Result` mismeasures the expected scope.
4. When using Spring Data Neo4j, instrument around **real service/repository methods** and log SDN-generated queries so secondary queries, relationship mapping, or extra transactions aren't missed.
5. Configure appropriate timeouts and retry budgets; **client timeout**, connection timeout, and **transaction timeout** are distinct mechanisms.

### Combining Traces and Errors

Production instrumentation should record **operation**, service name, database name, read/write category, and **success/failure status**, optionally with exception class and Neo4j error code. Never turn arbitrary `queryText` or `customerId` values into time-series labels; for query-level details, rely on protected traces/logs linked by correlation IDs.

With Micrometer/Prometheus, choose histogram buckets aligned with SLOs. When investigating **which specific query** was slow, well-sampled logs/traces work far better than minting separate time series for every distinct Cypher string.

## 12. Finding the Root of a p99 Spike: An Ordered Process

Suppose `POST /orders` p99 rises from ~180 ms to over 1,000 ms for 15 minutes. To analyze:

1. **Confirm impact:** p50/p95/p99 charts, request arrival/completion rates, failed request counts, and affected endpoints.
2. **Correlate database and instance events:** was there a leader switch, deploy, index migration, large import, or cluster scaling at that exact time?
3. **Check load levels:** successful/failed queries/s, committed write tx/s, active read/write tx, Bolt connections, CPU, heap, GC, and page-cache hit ratio.
4. **Look for lock waits:** run `SHOW TRANSACTIONS` during the slowdown, checking `waitTime`, `currentQueryWaitTime`, `status`, and `activeLockCount`.
5. **Classify errors:** watch query failures, transaction rollbacks/terminations, deadlock codes, and service errors. Never assume all rollbacks are deadlocks.
6. **Capture the real query:** from query logs/traces, note the Cypher statement, sanitized parameters, database, and application version.
7. **Analyze the plan:** run `EXPLAIN`, and `PROFILE` on a representative dataset copy to examine `Rows`, `DB Hits`, `Sort`, relationship expansions, and indexes. `PROFILE` **executes the query**, so never run it recklessly on writes in production.
8. **Form a testable hypothesis:** e.g., an import batch is holding locks on `:Order`, or a traversal is expanding too many relationships and multiplying rows.
9. **Change one variable at a time:** shrink batch size, stabilize lock order, add an appropriate index, or rewrite the query, then re-measure under comparable load.
10. **Verify correctness:** after tuning, outputs must still return the exact expected nodes, relationships, totals, ordering, and row counts.

### Hypothesis Discrimination Table

| Concurrent Observations | Hypothesis to Check | Verification Step |
|---|---|---|
| Latency up, `waitTime` up, many write tx | Lock contention | `SHOW TRANSACTIONS`, query logs, and update patterns |
| Latency up, `DB Hits` and `Rows` up, low lock wait | Suboptimal query plan or high cardinality | `PROFILE`, indexes, 1-to-many relationships |
| API latency up while server query latency is flat | Pool wait, network, mapping, retries, external service | Java Driver/SDN traces and metrics |
| Rollbacks up alongside deadlock errors | Deadlocks / concurrent writes | Error codes, lock ordering, transaction size |
| Throughput down, CPU/GC up, page-cache misses up | Resource saturation | Heap, GC, page cache, disk, and workload metrics |
| `transaction.active` up with zero errors | Long queries, imports, or high request volume | Cross-check throughput, latency, transaction snapshot |

## 13. Designing Useful Dashboards and Alerts

Dashboards should clearly separate **each database**, **each server/cluster member**, and **each workload type**. Suggested layout:

| Panel | Data | Why Needed |
|---|---|---|
| API latency p50/p95/p99 | Per endpoint/service, rolling window | Measures direct user impact |
| API requests/s & error ratio | Success/failure counts | Separates low demand from saturation |
| Server query latency histogram | Successful query execution | Spots slowdowns inside Neo4j |
| Query success/failure rate | `db.query.execution.*` counters | Isolates query errors from API errors |
| Transaction commit/rollback rate | Per-database counters | Reveals transaction volume and rollbacks |
| Active read/write transactions | Per-database gauges | Tracks concurrency |
| Lock-waiting transactions | Periodic/event `SHOW TRANSACTIONS` | Diagnoses point-in-time contention |
| Deadlock events | Error codes or version-supported metrics | Alerts on hard write contention |
| CPU/heap/GC/page-cache | System/DBMS metrics | Rules out or confirms resource bottlenecks |
| Bolt/pool utilization | DBMS Bolt + application pools | Detects connectivity pressure |

### Set Alert Thresholds by SLO, Not Arbitrary Numbers

**Hypothetical example:** a read API has an SLO of p95 under 200 ms; if p95 breaches that mark across multiple consecutive windows while error rate rises, trigger a higher-severity alert. For rollbacks, baseline rates in an import pipeline differ from interactive OLTP traffic, so "`rollbacks > 0`" is rarely a good default alert.

Choose alerts based on:

- **SLOs** and user impact, not isolated CPU or counter spikes.
- **Baselines per workload class** (read-heavy, write-heavy, batch import).
- **Sufficiently long windows** to filter noise while remaining responsive.
- **Absolute + ratio thresholds**, e.g., failure ratio spiking only when traffic volume is significant.
- **Correlated signals**, such as high p95 latency **and** rising queue/lock waits.
- **Clear ownership/runbook** stating who responds and what to check first.

Never alert on percentiles computed from a window with too few requests; one or two slow requests can skew p95 unrepresentatively.

## 14. Hands-On Observation on a Small Graph

To avoid generating load or locks on a live system, test on a **dedicated Neo4j instance**. Initialize mock order nodes:

~~~cypher
CREATE CONSTRAINT mon_order_id_unique IF NOT EXISTS
FOR (o:MonOrder)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
UNWIND range(1, 100) AS n
MERGE (o:MonOrder {orderId: 'MON-' + toString(n)})
SET o.customerId = 'C' + toString(n % 10),
    o.totalAmount = 100000 + n * 1000,
    o.createdAt = date('2026-01-01') + duration({days: n % 30});
~~~

For this sample dataset, here is a **read query** benchmark—not a deliberate deadlock test:

~~~cypher
MATCH (o:MonOrder)
WHERE o.customerId = $customerId
RETURN o.orderId AS orderId,
       o.totalAmount AS amount,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId ASC
LIMIT 10;
~~~

In Neo4j Browser, set the parameter with `:param customerId => 'C1'`. To view the plan:

~~~cypher
PROFILE
MATCH (o:MonOrder)
WHERE o.customerId = $customerId
RETURN o.orderId AS orderId,
       o.totalAmount AS amount,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId ASC
LIMIT 10;
~~~

Inspect `Rows`, `DB Hits`, `Sort`/`Top`, and actual returned rows before assuming optimizations. You can test an appropriate index, **strictly on the practice database**:

~~~cypher
CREATE RANGE INDEX mon_order_customer_created IF NOT EXISTS
FOR (o:MonOrder)
ON (o.customerId, o.createdAt);
~~~

Wait for the index to reach `ONLINE`, re-run the same query/parameter, and compare results and plans. With only 100 nodes, the planner **may still skip the index** because scanning a tiny set can be cheaper; the lesson is to read real measurements rather than forcing a plan change.

### Controlled Lock Contention Simulation

To observe `waitTime` climbing, coordinate **two concurrent write transactions** on **the same test node** across two separate sessions in an isolated environment:

~~~cypher
// Run once; never reuse labels/IDs from real data.
MERGE (a:MonAccount {accountId: 'A01'})
SET a.balance = 1000;
~~~

In session A, open an explicit transaction, update `A01`, and **hold the transaction uncommitted** for a brief controlled window; in session B, start another transaction and attempt to update `A01`. Session B will wait on the lock. In a third authorized monitoring session, run `SHOW TRANSACTIONS` and inspect `waitTime`/`currentQueryWaitTime`.

Do not write long `sleep` calls in real transactions and never run production writes to demonstrate lock contention. Afterward, **commit or rollback both transactions**, close the sessions, and verify the resulting balance matches your chosen outcome. Avoid inducing actual deadlocks when you only need to observe lock wait time.

## 15. Comprehension Exercises

### Exercise 1 — Computing queries/s and Rollback Rate

Over 60 seconds, `query.success` rises from 5,000 to 5,900; `query.failure` rises from 200 to 230. Over the same window, `transaction.committed` rises by 450 and `transaction.rollbacks` rises by 30. Calculate:

1. Completed queries per second.
2. Query failure ratio.
3. Committed transactions/s and rolled-back transactions/s.
4. Can you conclude those 30 rollbacks are the exact same 30 failed queries?

**Reference answer:** `(900+30)/60 = 15.5 queries/s`; `30/930 ≈ 3.23%`; `450/60 = 7.5 committed tx/s`; `30/60 = 0.5 rolled-back tx/s`. You cannot conclude the 30 rollbacks correspond 1-to-1 to the 30 failed queries without per-transaction correlation data.

### Exercise 2 — Why Is API p99 High While Server Queries Look Normal?

API p99 climbs from 120 ms to 1,000 ms, yet the server-side query execution histogram barely moves. Name at least four things to inspect.

**Reference answer:** connection pool wait time, network/TLS/routing delays, driver retry counts, Java mapping/result consumption time, HTTP server queuing, and downstream services. Trace individual requests rather than assuming Neo4j needs another index.

### Exercise 3 — Reading Lock Wait Properly

One transaction shows `activeLockCount = 300`, `waitTime = 0s`; another shows `activeLockCount = 2`, `waitTime = 8s`. Which transaction is definitely blocking others?

**Answer:** Insufficient evidence to conclude. The second transaction has **accumulated** 8 seconds waiting on locks, yet may no longer be waiting. The first holds many locks, yet may not be blocking anyone. Check `status`, related transactions, query logs, and multiple snapshots.

### Exercise 4 — Query Errors vs. Rollbacks

An application uses `session.executeWrite`; on a deadlock, the driver retries and the request eventually succeeds. The API dashboard shows 0 errors, yet the transaction rollback metric rises. Is this a contradiction?

**Answer:** No. Failed attempts on the server roll back before the driver retries and succeeds, so the API layer sees only the final outcome. Track **server rollbacks/errors** separately from **post-retry request failures**.

### Exercise 5 — Choosing the Right Remediation

When `POST /orders` slows down, `waitTime` rises, active write transactions rise, and query logs show many operations updating a single total-revenue node, what should you change first?

**Suggested answer:** Address the **hot node** design, shorten transactions, reduce conflicting write concurrency, decouple/batch aggregation updates, and standardize write lock ordering. Adding an index alone will not resolve multiple transactions writing to the same node.

### Exercise 6 — Histogram Pitfalls

A team computes cluster-wide p95 by taking `avg(p95_instance_1, p95_instance_2)`. Why is this wrong?

**Answer:** Percentiles of distributions do not combine linearly; each instance handles different request counts and distinct latency distributions. Merge compatible histogram buckets or raw sample distributions using identical time/sample definitions before calculating quantiles.

## 16. Official Documentation for Reference

- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/)
- [Metrics reference: query execution and transaction metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Expose metrics: Prometheus/CSV/JMX/Graphite](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/expose/)
- [Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Concurrent data access and deadlocks](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Logging and query log](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
- [Cypher query tuning with EXPLAIN/PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)

The `current` documentation pages update with each release. When operating older Neo4j versions—especially Neo4j 5.x—**verify exact metric names, supported fields, Enterprise features, configuration keys, and Prometheus export behavior** before deploying dashboards or automation.

## 17. Key Takeaways

- **Latency is multi-layered:** API p95/p99, driver/pool waits, server query latency, and lock waits are not the same measurement.
- **Throughput is a rate over time**, calculated from counter deltas/rates; `active transactions` is a concurrency gauge, not transactions/s.
- **`SHOW TRANSACTIONS` provides a lock-state snapshot:** `waitTime` is cumulative time spent waiting on locks; `activeLockCount` alone does not prove blocking.
- **Query failures, transaction rollbacks, terminations, and deadlocks are distinct concepts**; driver retries can hide transient errors from the API while still leaving server-side events.
- **Combine metrics, query logs, Java Driver/SDN instrumentation, and `PROFILE`** to diagnose root causes rather than guessing from a single chart.
- **Alert on SLOs and workload baselines**, while protecting metrics endpoints, query logs, and sensitive parameters during observation.
