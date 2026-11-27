# Comparing Behavior, SQL, and Performance Before and After Migration

When migrating an application from JPA/Hibernate to **Spring Data Relational JDBC**, performance comparisons cannot rely solely on the timing of a single repository method or the number of logged SQL statements. The two frameworks can generate different SQL, load objects differently, and execute writes differently. One change may reduce round-trips while increasing returned rows; another may cut object allocations while holding database connections longer inside transactions.

A meaningful comparison must answer three questions:

1. **Is behavior equivalent?** Business outcomes, transactions, locking, cascade/ownership, generated IDs, and error handling must preserve contracts.
2. **How did the SQL change?** Statement counts, query shapes, bind parameters, rows, joins, write statements, and execution plans.
3. **How did overall cost change?** Latency, throughput, database CPU/I/O, network payload, JVM allocation/GC, lock contention, and connection pool usage.

Establish a pre-migration baseline, run the identical post-migration workload under matching data and infrastructure conditions, and analyze each difference. Never conclude Spring Data JDBC is faster or slower purely because it emits fewer or more SQL statements.

## 1. Establish the Baseline Before Making Changes

Before altering the persistence implementation, record the current behavior of the JPA/Hibernate application. The baseline must represent realistic production workloads, not just a test with one tiny aggregate.

For each use case, record:

- Entry point and inputs.
- Number of aggregates/roots read or written.
- Average and tail child counts.
- To-one/to-many associations accessed.
- Fields actually returned to the caller.
- Transaction boundaries, propagation, and isolation.
- Whether optimistic or pessimistic locking is used.
- Concurrency level and use-case frequency.
- Expected business outcomes and side effects.
- SQL statements, masked bind types/values, and execution order.
- Latency, throughput, and database/JVM resources.

Example workloads:

| Use Case | Data Shape | Behavior to Preserve |
|---|---|---|
| View order details | 1 root, 0–30 lines | Complete root and lines, correct order |
| Order list page | 50 roots, customer name, and totals | 50 DTOs properly sorted/paged, without loading full aggregates |
| Update status | 1 root | Mutate business status only, keep other columns intact |
| Add order line | 1 root, 1 new child | Child linked to right root, accurate total |
| Delete order | 1 root, multiple owned rows | Delete/soft-delete per contract without deleting other aggregates |
| Search orders by customer | 1,000+ roots | Accurate filtering, sorting, and pagination |
| Batch import | 5,000 rows/chunk | No lost IDs, no duplicates, clear transaction boundaries |

Do not use one generic synthetic workload for every use case. A list screen, an aggregate update command, and a batch job have very different performance objectives.

## 2. Verify Business Equivalence Before Benchmarking

If business outcomes differ, performance measurements are no longer comparing the same work.

Check behaviors Hibernate may have supplied implicitly:

- Dirty checking and flush timing.
- Cascade persist/merge/remove and orphan removal.
- Lazy loading and fetch strategies.
- Identity map/persistence context.
- Optimistic locking and version increments.
- Entity callbacks/listeners and auditing.
- Generated IDs, sequences, and database defaults.
- Transaction rollbacks, isolation, and propagation.
- Null handling, converters, enums, and timestamp semantics.
- Collection ordering and pagination.
- Soft deletes, triggers, and FK actions.

In Spring Data JDBC, objects are not managed by a persistence context. Code must call `save` explicitly; owned entities persist with the aggregate; references to other aggregates do not cascade; there are no lazy proxies. Convert these differences into verification tests before measuring speed.

### Parity Table

| Behavior | JPA Baseline | Result to Verify in JDBC |
|---|---|---|
| Mutating a field | Dirty checking on managed entity | Persists only when `save` or explicit DML is called |
| Adding a child | Cascade/relationship mapping | Child belongs to aggregate and saves with root |
| Removing a child | `orphanRemoval` if configured | Owned collection update handles row properly |
| Reference to `Customer` | Association/lazy proxy | ID/`AggregateReference`, separate query when needed |
| Version | Optimistic lock on flush | `@Version` and failure on stale version |
| Callbacks | JPA lifecycle listener | Equivalent `EntityCallback`/lifecycle event |
| Read-only DTO | JPQL projection/entity graph | SQL projection/`RowMapper`/read model |
| Rollback | `EntityManager` and transaction manager | Repository/`JdbcTemplate` in shared transaction |

Never benchmark a JDBC path that skips business validation or auditing present in the JPA path and claim the lower latency as an improvement.

## 3. Capturing SQL from Hibernate and Spring Data JDBC

Capture SQL in both implementations using a comparable method. At minimum, record statements, ordering, timings, row counts, and operation types. When inspecting bind parameters, use controlled instrumentation with data masking.

### Hibernate SQL Logging

In Hibernate 6, you can enable:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

- `org.hibernate.SQL` logs SQL executed by Hibernate.
- `org.hibernate.orm.jdbc.bind` logs detailed parameter bindings.

Bind loggers can expose sensitive data. Enable only locally, in tests, or during controlled investigations; mask values before sharing.

Hibernate statistics can supply extra metrics such as entity loads/fetches, collection fetches, query executions, and cache hits. Enable statistics in measurement environments when needed; do not enable detailed stats in production by default without assessing overhead.

### Spring Data JDBC SQL Logging

Spring Data JDBC executes SQL via Spring JDBC. Enable:

~~~yaml
logging:
  level:
    org.springframework.jdbc: DEBUG
~~~

This logger reveals statements and execution order. For bind values, row counts, or exact timings, use `datasource-proxy`, P6Spy, or common JDBC instrumentation across both versions.

### Use the Same Capture Tool

A reliable comparison places datasource instrumentation at the same layer for both Hibernate and Spring Data JDBC. Record:

- Normalized SQL/fingerprint.
- Operation type: `SELECT`/`INSERT`/`UPDATE`/`DELETE`.
- Bind parameter types and masked/synthetic values.
- Query duration.
- Rows returned or update count.
- Connection/transaction/request correlation ID.
- Exceptions, `SQLState`, and vendor error codes.

Do not just copy text logs and count lines. Some logs emit separate lines for prepare, bind, and execute; some statements are batched. Count actual executions.

## 4. Normalize the Environment for Fair Comparisons

Baseline and candidate must run under equivalent conditions:

| Condition | What to Keep Stable |
|---|---|
| Database | Same engine and major/minor version |
| JDBC driver | Same version where possible |
| Schema | Same DDL, indexes, constraints, and triggers |
| Dataset | Same row counts, distribution, NULLs, and cardinality |
| Database statistics | `ANALYZE`/statistics in equivalent state |
| Hardware | CPU, RAM, disk, and network |
| Connection pool | Max pool size, min idle, timeouts |
| Transactions | Isolation, timeouts, and boundaries |
| Workload | Request mix, concurrency, and payloads |
| Cache state | Warm/cold cache clearly defined |
| JVM | JDK, heap, GC, container CPU/memory limits |
| Observability | Same instrumentation and sampling |

Do not run both benchmarks simultaneously against the same database if they compete for CPU, I/O, or locks. Run sequentially or on identical isolated instances.

### Datasets Must Have Realistic Distributions

Do not generate 100 orders with exactly 2 lines each. Simulate:

- Many roots with zero children.
- Roots with one child.
- Roots with average child counts.
- A few roots with very large collections.
- Skewed status/filter distributions.
- Hot keys updated concurrently by many requests.
- Duplicate timestamps.
- NULL/duplicate/legacy values if present in production.
- Enough volume for indexes and query plans to matter.

Skewed cardinality often yields drastically different query plans and JOIN behavior compared to uniform fixtures.

## 5. Measure Multiple Layers, Not Just Query Count

Minimum metrics:

| Metric | Meaning |
|---|---|
| Request latency p50 | Typical response time |
| p95/p99 latency | Tail latency and experience under load |
| Throughput | Requests/operations completed per second |
| Error rate | Rate of SQL errors, timeouts, conflicts, and rollbacks |
| SQL statement count | Number of statement executions |
| Total DB time | Total database processing time |
| Rows returned/updated | Actual data volume |
| Bytes transferred | Network and decoding cost |
| DB CPU/buffer reads | Query engine and I/O cost |
| JVM CPU | Application and mapping cost |
| Heap allocation/GC | Object graph materialization cost |
| Connection pool wait/active | Pressure on the connection pool |
| Lock wait/deadlocks | Contention across concurrent transactions |
| Batch size/round-trips | Batch write efficiency |

A single SQL statement can be slower than 10 well-indexed queries if it joins multiple collections and returns thousands of duplicate rows. Conversely, 100 tiny round-trips can incur heavy network latency even when each individual query is fast.

**Query count is an investigation signal, not the final verdict.**

## 6. Comparing the Aggregate Read Path

### JPA/Hibernate

A repository find may load the root first. When code accesses lazy collections, Hibernate can issue extra `SELECT`s:

~~~sql
SELECT id, customer_id, status, created_at
FROM purchase_order
WHERE id = ?;

SELECT id, order_id, product_id, quantity
FROM order_line
WHERE order_id = ?;
~~~

When loading multiple roots and iterating over collections, N+1 queries can occur:

~~~text
1 query fetching purchase_order
N queries fetching order_line for each order_id
~~~

JPA can reduce queries with fetch joins, entity graphs, or batch fetching. Yet fetch-joining multiple collections can multiply row counts and produce duplicate root rows requiring deduplication.

### Spring Data JDBC

Spring Data JDBC loads aggregates per mapping. Default loading may issue a root query plus queries for owned collections. There are no lazy proxies; collections are resolved during aggregate loading.

Single Query Loading (introduced in Spring Data Relational 3.2) can load aggregates in a single query when mappings, dialects, and repository methods qualify. The feature currently remains experimental with limitations; it does not apply to all derived/`@Query` methods or all aggregates.

### How to Compare Properly

- Use identical IDs/filters and identical aggregate shapes.
- Compare statement counts, rows, bytes, and total DB time.
- Check whether the aggregate has nested collections, references, or embedded mappings.
- Measure object allocations and GC when materializing many children.
- Inspect real SQL rather than just checking the Single Query Loading flag.
- Compare against your tuned JPA fetch plan, not an intentionally unoptimized N+1 JPA path.

If a use case only needs a summary, never benchmark full JDBC aggregate loading against a JPA projection or vice versa. Both paths must return identical data with identical semantics.

## 7. Comparing Projections and Read Models

A list page may only need order ID, status, customer name, and total amount. JPA can use DTO projections/JPQL. Spring Data JDBC can use `@Query` with a custom `RowMapper` or a repository fragment with `NamedParameterJdbcTemplate`.

The SQL may look like:

~~~sql
SELECT
    po.id,
    po.status,
    c.name AS customer_name,
    COUNT(line.id) AS line_count,
    COALESCE(SUM(line.quantity * line.unit_price), 0) AS total_amount
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
LEFT JOIN order_line line ON line.order_id = po.id
WHERE po.status = :status
GROUP BY po.id, po.status, c.name
ORDER BY po.created_at DESC, po.id DESC;
~~~

Measure:

- Columns actually `SELECT`ed.
- Rows returned.
- CPU for `JOIN`/`GROUP BY`.
- Indexes used.
- DTO mapping allocations.
- Count queries and pagination.
- Whether collections are accidentally loaded through aggregate mapping.

Projections can bring large gains if the application previously loaded full entity graphs just to display a few fields. However, that is a read-model redesign, not an apples-to-apples comparison of two persistence frameworks on the same operation.

## 8. Comparing JOINs and Collection Cardinality

To-one JOINs generally do not multiply root rows when FKs and unique constraints are sound. To-many JOINs produce one row per child. Joining two independent collections multiplies row counts.

For example, an order has 5 lines, 3 payments, and 4 shipments. Joining all three collections can produce up to 5 × 3 × 4 = 60 rows for a single root.

~~~mermaid
flowchart TD
    A["One PurchaseOrder"] --> B["5 OrderLines"]
    A --> C["3 Payments"]
    A --> D["4 Shipments"]
    B --> E["JOIN three collections"]
    C --> E
    D --> E
    E --> F["Up to 60 rows"]
~~~

When comparing JPA fetch joins against JDBC SQL, measure:

- Result rows after JOIN.
- Repeated root/child columns.
- Bytes transferred.
- CPU and memory spent deduplicating.
- `ResultSet` mapping time.
- Whether `COUNT`/`SUM` values are inflated.

You can aggregate each collection inside a subquery/CTE and join the one-row-per-root results, or run separate indexed queries. Do not force every collection into one JOIN just to chase a low query count.

## 9. Comparing the Write Path: Dirty Checking vs. Aggregate Save

This is usually where the two frameworks diverge most visibly.

### JPA Dirty Checking

When an entity is managed and only one field changes, Hibernate can often emit an `UPDATE` covering just changed columns, depending on dynamic update settings:

~~~sql
UPDATE purchase_order
SET status = ?
WHERE id = ?;
~~~

When the entity is versioned, SQL adds a version predicate and increments the version.

### Spring Data JDBC Save

Spring Data JDBC does not dirty-check objects. Repository `save` is invoked explicitly and persists the aggregate per mapping. The root may be updated while owned collections may execute multiple statements to synchronize child state.

An illustrative shape might include:

~~~sql
UPDATE purchase_order
SET customer_id = ?, status = ?, created_at = ?, version = ?
WHERE id = ? AND version = ?;

DELETE FROM order_line
WHERE order_id = ?;

INSERT INTO order_line (...);
INSERT INTO order_line (...);
~~~

This shape is illustrative, not a fixed SQL guarantee across all versions and mappings. Capture the real SQL generated by your application.

### What to Measure on the Write Path

- Count of `INSERT`/`UPDATE`/`DELETE` statements.
- Rows affected.
- Whether child rows are deleted and re-inserted.
- How many times triggers/audit events fire.
- Whether generated IDs change.
- Whether FK and unique constraints cause write failures.
- Lock duration and transaction duration.
- Version increments and optimistic conflict rates.
- WAL/log/CDC volume.
- Overall latency and throughput under concurrent writes.

If an aggregate has hundreds of children and only one root field changes, the child write strategy can dominate costs. Examine aggregate size, write frequency, and boundaries before drawing conclusions.

## 10. Comparing Batch and Bulk Operations

Hibernate supports JDBC batching for certain inserts/updates/deletes; effectiveness depends on mapping, ID generation, flush mode, batch size, and driver. Spring Data JDBC also runs JDBC operations and may offer batching paths depending on API and version, though you must not assume both frameworks batch statements identically.

Measure:

- Actual round-trips.
- Statements per batch.
- Batch size.
- Generated key retrieval.
- Transaction size and rollback cost.
- Lock duration.
- Memory used to hold aggregates/batches.
- Throughput as chunk size grows.

Larger batches cut round-trips yet hold connections/locks longer and increase rollback cost. Smaller chunks reduce per-transaction duration while altering atomicity: committed chunks do not roll back if a later chunk fails.

Never benchmark batching by stripping validation or callbacks from one version while keeping them in the other. Keep identical semantics or document differences explicitly.

## 11. Transactions, Locking, and Concurrency

Both frameworks can execute different SQL even when using identical `@Transactional` annotations.

Compare:

- Effective transaction boundaries.
- Isolation levels.
- Connections held.
- Lock modes and lock acquisition order.
- Time from lock acquisition to commit.
- Deadlocks and lock timeouts.
- Optimistic locking failures.
- Retry behavior.
- Transaction rollback rates.

JPA can defer SQL until flush; Spring Data JDBC runs statements when repository/template methods are called. This can shift when constraint errors surface even though the transaction ultimately rolls back in both cases.

When multiple requests update the same aggregate concurrently, measure throughput and conflict rates. Spring Data JDBC uses `@Version` for optimistic locking; if a direct SQL write path skips incrementing version properly, the comparison is no longer equivalent.

Never benchmark single-threaded only. A design that looks fast at concurrency 1 can degrade sharply at concurrency 32 due to lock contention or connection pool saturation.

## 12. Analyzing SQL Execution Plans Before and After

For slow queries, capture execution plans on the same database with representative parameters.

PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Compare:

- Estimated rows vs. actual rows.
- Sequential scans vs. index scans.
- Join order and join algorithms.
- Sorts and memory/disk spills.
- Buffer hits and reads.
- Rows removed by filters.
- Total execution time.
- Index selectivity and statistics.

`EXPLAIN ANALYZE` executes the query for real. Be careful with write statements; run only safe `SELECT`s or wrap writes in rolled-back transactions on test databases. In production, use controlled observation methods.

If SQL shape changed, compare both the query plan and the payload size. A new query may pick a better index yet return more data; total application latency can still rise due to mapping overhead.

## 13. Designing Repeatable Benchmarks

A sound benchmark must be defined upfront:

### Workload

- Production-representative read/write ratio.
- Use-case request mix.
- Page sizes and offset/deep pagination.
- Aggregate size distribution.
- Concurrency and think time.
- Hot-key ratio.
- Payload and response sizes.

### Running the Benchmark

1. Start database and application with identical resource limits.
2. Load identical datasets or restore the exact same snapshot.
3. Apply version-matched migrations/schemas.
4. Warm up JVM, connection pool, and query plans/caches.
5. Run a sufficiently long steady-state window.
6. Record latency percentiles, throughput, error rates, and resource usage.
7. Reset database/state before the next run if write workloads mutate data.
8. Repeat runs and report variance.
9. Run at both low and high concurrency.
10. Save SQL traces and query plans for key operations.

Never draw conclusions from a short single run. Benchmarks require warm-up and steady-state windows; report results alongside exact environment details and software versions.

### Suitable Tools

- JMeter, Gatling, or k6 for HTTP/load workloads.
- Micrometer/Actuator and tracing for request/transaction latency.
- `datasource-proxy`/P6Spy for SQL execution and bind inspection.
- Hibernate Statistics for entity/query/cache metrics.
- Database monitoring and `EXPLAIN` for execution plans.
- JFR/profilers for CPU, allocations, and GC.
- Connection pool metrics for active, idle, and pending threads.

JMH fits pure-JVM microbenchmarks such as converters or mapping functions, yet does not replace integration/load tests for database round-trips and transactions.

## 14. Reading Results Through an Example

Suppose a benchmark runs the same use case returning 50 order summaries:

| Metric | JPA Baseline | JDBC Candidate |
|---|---|---|
| Request p50 | 45 ms | 32 ms |
| Request p95 | 110 ms | 96 ms |
| SQL statements | 151 | 1 |
| Rows returned | 500 | 50 |
| DB CPU/request | 8 ms | 11 ms |
| JVM allocation/request | 2.4 MB | 0.8 MB |

These numbers merely illustrate how to analyze metrics, not guaranteed framework outcomes.

Interpretation:

- JDBC cut statement counts and rows via an aggregated projection query.
- Database CPU ticked up slightly due to `GROUP BY`, while network payload and JVM allocations dropped.
- p50/p95 improved under this workload.
- Concurrency and query plans still require validation before broad rollout.

Another outcome could go the opposite way: a large SQL JOIN returning 20,000 rows spikes database CPU. In that case, fewer statements did not mean better performance.

## 15. Regression Checks and Data Correctness

Benchmarks must pair with regression tests. For every use case, assert:

- Matching counts of aggregates or result DTOs.
- Matching IDs and business values.
- Matching collection order where order is part of the contract.
- Matching filter, sort, and page semantics.
- Matching generated IDs and default values.
- Matching transaction rollback behavior.
- Matching optimistic lock guarantees.
- No duplicate or orphan rows created.
- No extra side effects through triggers/callbacks.
- No lost audit/version/timestamp fields.

For write paths, compare before-and-after database state via queries or snapshots. Never assert only the returned object, since in-memory objects can look right while unintended side effects occurred in the database.

## 16. Shadow Reads and Canary Rollouts

To compare against production-like traffic, you can deploy controlled shadow reads:

1. Primary requests continue using the old implementation.
2. A secondary read executes concurrently against an appropriate snapshot or replica.
3. Compare results across selected business fields.
4. Record latency and SQL metrics for the new implementation.
5. Mask sensitive fields in diffs.
6. Prevent the shadow path from writing data or triggering side effects.
7. Cap traffic percentage to avoid unexpected database load.

Shadow reads must enforce concurrency limits and timeouts. Never run two heavy queries per request if doing so risks overloading the database.

Once parity stabilizes, canary a small group of use cases or tenants. Monitor error rates, latency, DB CPU, lock waits, pool saturation, and data discrepancies. Expand scope gradually as metrics stabilize.

## 17. Deciding to Keep, Optimize, or Roll Back

There is no single threshold valid for every application. Decide based on SLOs and risk tolerance:

- Keep the change if parity holds, latency/throughput meet SLOs, and resources stay within bounds.
- Tune queries/indexes if the bottleneck is query plan or payload size.
- Refine aggregate boundaries if saving large aggregates generates excessive writes.
- Use projections for read models if materializing unnecessary object graphs.
- Use Single Query Loading when aggregates, dialects, and methods qualify and measurements prove a win.
- Roll back or revert cutover if data mismatches, constraint errors, deadlocks, tail latency, or pool saturation exceed limits.

Before rollout, plan how to revert to the old implementation, maintain schema compatibility, and handle data written by the new version. Never roll back code if a new schema already broke the old code's contract; migrations must be backward-compatible.

## 18. Common Comparison Mistakes

| Mistake | Why Conclusions Are Wrong | Right Approach |
|---|---|---|
| Counting SQL statements only | One query can return far more rows than several small queries | Measure rows, bytes, DB time, and latency |
| Comparing JPA N+1 to JDBC Single Query Loading | Baseline was not comparably tuned | Optimize both to best-known configurations |
| Comparing full aggregates to DTOs | Both sides perform different amounts of work | Keep identical result shapes and semantics |
| Benchmarking only one tiny aggregate | Misses production cardinality | Use realistic data distributions |
| Running H2 benchmarks to predict PostgreSQL | Dialects, drivers, and plans differ | Use a production-compatible database |
| Skipping JVM/database warm-up | Results distorted by startup/cold caches | Define warm-up and steady-state windows |
| Measuring only p50 | Ignores tail latency | Measure p50/p95/p99 and error rates |
| Ignoring write side effects | Triggers/audits/child rows can dominate costs | Capture SQL and compare database state |
| Ignoring concurrency | Misses lock and pool bottlenecks | Load test at representative concurrency |
| Raising pool size to mask slow queries | Can overload the database further | Optimize queries/transactions and monitor pools |
| Skipping version/callback checks | Faster only because correctness was dropped | Regression-test behavior before benchmarking |
| Running two benchmarks concurrently | Both versions compete for resources | Run sequentially or on equivalent isolated instances |

## 19. Before-and-After Comparison Procedure

1. **Select use cases:** prioritize high-volume or high-risk read/write paths.
2. **Record baseline semantics:** inputs, outputs, side effects, transactions, and locking.
3. **Capture JPA SQL:** statements, bind types, rows, durations, and query plans.
4. **Build representative workloads:** datasets, cardinality, skew, concurrency, and page sizes.
5. **Implement JDBC migration:** preserve contracts, schema, and business behavior.
6. **Capture JDBC SQL:** use the exact same instrumentation and database environment.
7. **Compare query shapes:** JOINs, collection loading, write statements, batching, and pagination.
8. **Run correctness tests:** result parity, constraints, versions, rollbacks, and data diffs.
9. **Run benchmarks:** warm-up, steady-state, p50/p95/p99, throughput, CPU, rows/bytes, and JVM metrics.
10. **Analyze execution plans:** identify scan, join, sort, index, and lock bottlenecks.
11. **Optimize selectively:** projections, indexes, query shapes, aggregate boundaries, or batch sizes.
12. **Canary and monitor:** shadow reads/read-only first, then enable write paths in stages.
13. **Decide:** keep, optimize further, or roll back based on SLOs and data correctness.

### Quick Decision Table

| Post-Migration Signal | Investigation Direction |
|---|---|
| SQL count dropped yet latency rose | Rows/bytes, JOIN cardinality, DB CPU, and mapping |
| Read path cut allocations | Verify DTO includes all needed data and keeps validation |
| Write path increased `DELETE`/`INSERT`s | Owned collection save strategy, triggers, FKs, and aggregate size |
| Good p50 yet bad p99 | Lock waits, pool waits, GC, query skew, and hot keys |
| DB CPU dropped yet JVM CPU rose | `ResultSet`/object mapping, conversions, and app-side aggregation |
| N+1 disappeared | Inspect payload and query plan; do not stop at query count |
| Optimistic conflicts increased | Version handling, stale objects, and write concurrency |
| Tests pass yet production is slow | Differences in dataset/cardinality, indexes, plans, hardware, and concurrency |
| JPA/JDBC yield different outputs | Transaction timing, callbacks, defaults, nulls, sorting, and lifecycles |
| Rollout causes data discrepancies | Halt expansion, identify writer/schema/version, and recover per plan |

**Key takeaway:** compare before and after migration using identical business logic, data, and environments. Capture SQL from both Hibernate and Spring Data JDBC, then measure query counts alongside rows/bytes, latency percentiles, throughput, database resources, JVM allocations, locks, and connection pools. Prove correctness before benchmarking, optimize around measured bottlenecks, and roll out in stages with a rollback path.

## Official References

- [Spring Data Relational — Persisting Entities and Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): aggregate loading, update behavior, and Single Query Loading.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): derived queries, `@Query`, `RowMapper`, `ResultSetExtractor`, and pagination.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction boundaries and repository/service behavior.
- [Hibernate ORM User Guide — Statistics](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): Hibernate statistics, SQL, fetching, and persistence context.
- [Hibernate ORM — Logging](https://docs.jboss.org/hibernate/orm/current/logging/logging.html): SQL and JDBC bind logging categories.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logger configuration and levels.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): execution plans, actual rows, and query costs.
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): database activity and resource monitoring.
- [Testcontainers — Database Modules](https://java.testcontainers.org/modules/databases/): integration testing against real database engines.
