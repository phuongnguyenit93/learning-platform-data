# Building a Regression Test Suite for SQL, Mapping, Transactions, and Performance

When a Spring Data R2DBC application modifies an entity, repository, SQL query, converter, or publisher composition, a feature may still pass simple tests while failing on realistic data. A timestamp column may shift timezones, a join query may duplicate rows, a count query may miscount, a transaction may partially commit, or a subtle predicate change may cause the database to skip an index.

A *regression test suite* catches these regressions before release. For R2DBC, the suite must verify multiple layers: SQL actually executing on the target database, data mapping accurately into entities/projections, transactions and concurrency upholding their semantics, and performance remaining within defined budgets.

Do not check only that a method returns a `Mono` or `Flux` with a value. A reliable suite must verify final database state, constraints, error behavior, critical query counts, and performance metrics meaningful to the workload. At the same time, tests must be repeatable, use deterministic data, and run on a database/driver close to production.

## 1. Goals and Scope of the Regression Suite

Regression testing does not just verify new features. It verifies that previously promised behaviors stay intact after code or schema changes.

For Spring Data R2DBC, cover at least four categories:

| Category | Questions to Answer | Example Bugs Caught |
|---|---|---|
| SQL and query behavior | Do filtering, joins, sorting, paging, and aggregates return the right datasets? | Missing tenant predicate, wrong count, row-multiplying join |
| Entity/projection mapping | Are Java types, column names, nulls, generated values, and conversions accurate? | Precision loss, timezone shift, unmapped enum |
| Transactions and concurrency | Do commits, rollbacks, isolation, and optimistic locking preserve integrity? | Partial writes, lost updates, detached transaction context |
| Performance | Do query latency, throughput, pool metrics, and resources stay within thresholds? | N+1 queries, full table scans, acquire timeouts, memory spikes |

Beyond these four core groups, the suite can cover migration compatibility, cancellation, driver errors, retries, and observability if those behaviors are critical to the application.

### 1.1. Define the Contract Before Writing Tests

Each test should verify a clearly specified behavior:

- What are the inputs and initial database state?
- What must the query or business operation do?
- What values must the returned output contain?
- What final state must the database be in?
- Which errors are expected, if any?
- Are there time or resource limits?

Example contract for querying orders by tenant and status:

```text
Given:
  tenant A has 3 PAID orders, tenant B has 2 PAID orders
  tenant A's request filters by status PAID

When:
  calling searchOrders(tenantA, PAID, page=0, size=20)

Then:
  only tenant A's 3 orders are returned
  totalElements = 3
  results are stably sorted
  no rows from tenant B appear
```

This test verifies both content and total while confirming tenant isolation. Checking only `content.size() == 3` is insufficient if a buggy query could return three wrong rows.

### 1.2. Separate Tests by Layer

A practical testing strategy includes:

1. **Unit tests:** test pure Java logic, validation, mapping functions, and business rules without a database.
2. **Repository integration tests:** test SQL, mapping, and the driver against a real database.
3. **Transaction/concurrency integration tests:** test multi-statement flows, multiple connections, and contention scenarios.
4. **Performance regression tests:** measure queries and end-to-end flows on representative datasets.
5. **Migration compatibility tests:** test schemas post-migration and compatibility across relevant code versions.

Never use mocked repositories to claim SQL, transactions, or query plans are correct. Mocks only prove code calls the mock as stubbed.

## 2. Choosing a Production-Like Test Environment

SQL and transaction semantics depend on the database engine. A test passing on H2 does not prove the same query behaves identically on PostgreSQL, MySQL, SQL Server, or Oracle.

### 2.1. Use Testcontainers for Integration Tests

Testcontainers starts a real database inside a container and configures Spring R2DBC to connect to the dynamically mapped port.

Example PostgreSQL setup with JUnit 5:

```java
@Testcontainers
@DataR2dbcTest
@ActiveProfiles("test")
class OrderRepositoryTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4-alpine")
                    .withDatabaseName("store_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void configureR2dbc(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://" + postgres.getHost() + ":"
                        + postgres.getMappedPort(5432) + "/"
                        + postgres.getDatabaseName());
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository orderRepository;
}
```

Pin container image versions for reproducible results. Never use `latest` in a regression suite that needs stability. If your project supports multiple databases, run contract suites for each database/driver rather than letting one engine represent all.

### 2.2. Use Deterministic Schemas and Fixtures

Test schemas should be built by the project's chosen source of truth (migrations or SQL initialization). Fixtures should:

- Use clear natural keys such as `ORD-TEST-001`.
- Use fixed timestamps when assertions depend on time.
- Insert parent records before child records.
- Retain production-equivalent constraints and indexes.
- Avoid assuming generated identity values always start at a specific number.

For example, look up an order by `orderCode` rather than `id = 1`. When testing generated IDs, verify only that an ID was generated and reads back the right row.

### 2.3. Representative Workload Data

A three-row table suffices for basic mapping tests, but not for evaluating paging or query plans. Performance regressions require datasets with:

- Size approaching realistic operational scale.
- Data distributions and predicate selectivity resembling production.
- Realistic ratios of nulls, statuses, and foreign keys.
- Enough one-to-many rows to expose join issues or N+1s.
- Edge cases such as empty, oversized, or duplicate values.

You do not need full production dumps in tests. Use synthetic data with similar distributions and zero real personal data.

## 3. Testing SQL and Query Behavior

SQL tests must verify datasets, ordering, and semantics—not merely that queries run without throwing exceptions.

### 3.1. Verify Predicates and Boundary Conditions

For each repository query, prepare rows that satisfy and fail each predicate. Example filtering by tenant, status, and time range:

```sql
SELECT id, order_code, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :from
  AND created_at < :to
ORDER BY created_at DESC, id DESC
```

Tests should verify:

- Rows belonging to other tenants are excluded.
- Rows with other statuses are excluded.
- The `from` boundary is inclusive.
- The `to` boundary is exclusive when using `<`.
- Equal timestamps sort deterministically by `id`.
- Empty datasets complete empty or return an empty page content list per contract.

For time ranges, using half-open intervals `[from, to)` helps stitch consecutive intervals without double-counting boundaries. If business rules specify another convention, tests must reflect that exact rule.

### 3.2. Verify Dynamic Filters

For optional filters, test every meaningful combination:

- Mandatory filters only.
- Each optional filter individually.
- Multiple filters combined.
- Empty or whitespace-only filter strings.
- `null` values meaning "omit filter."
- Cases explicitly querying for SQL `NULL`.

Do not test only the case where every filter is populated. Bugs commonly hide where query builders mis-join `AND`/`OR` clauses or mis-bind typed nulls.

### 3.3. Verify Joins and Cardinality

In one-to-many joins, a parent entity can appear across multiple SQL rows. Tests must distinguish:

- Queries returning distinct parent entities.
- Queries returning individual child lines.
- Queries returning aggregated projections.

For instance, an order has three line items. On an order-paginated screen, that order must appear once with `lineCount` equal to 3. If the count query runs `COUNT(*)` over the join, the total can become 3 instead of 1.

Seed fixtures containing:

- An order with zero lines if permitted.
- An order with one line.
- An order with multiple lines.
- Two orders for the same customer.
- Child rows belonging to another tenant if the schema is multi-tenant.

Test `LEFT JOIN`, `COUNT(child.id)`, `COUNT(DISTINCT parent.id)`, or `EXISTS` against exact semantics. Never compare only content row counts while ignoring projection field values.

### 3.4. Verify Paging and Sorting

For offset pagination:

- First page returns at most `size` rows.
- Subsequent pages do not duplicate rows in a static dataset.
- Last page returns the exact remaining count.
- Out-of-range pages return empty content.
- `totalElements` is not truncated by `LIMIT`/`OFFSET`.
- Sorting includes a unique tie-breaker.

For keyset pagination:

- Cursors include all sort fields.
- Rows with identical timestamps are neither skipped nor duplicated.
- Cursors are not reused after changing filters or sort order.
- Cursor conditions handle ascending/descending directions properly.

If dynamic sorting uses an allowlist, test every allowed field and confirm invalid fields are rejected before generating SQL.

### 3.5. Verify Count Queries Independently

Count queries must be tested as semantically separate queries. Critical cases:

- Count omits limit/offset.
- Count applies the exact same filters as the content query.
- One-to-many joins do not over-count logical entities.
- Aggregated queries count groups rather than raw source rows.
- `HAVING` clauses are preserved in counts via subqueries if needed.
- Empty results yield total equal to 0.

Even when content and count share a builder, integration tests remain essential because the final SQL often differs in joins, grouping, or bindings.

### 3.6. Verify SQL Injection Protection and Bind Parameters

Never test SQL injection merely by scanning SQL strings in source code. Invoke queries with inputs containing quotes, special characters, or SQL-like payloads and confirm they are treated strictly as data values without altering statement structure.

Email example:

```java
String input = "x' OR '1'='1";

StepVerifier.create(customerRepository.findByEmail(input))
        .verifyComplete();
```

Tests should verify the query does not return all customers. Column names, table names, and sort directions must come from allowlists because identifiers cannot be bound as parameter values.

### 3.7. Verify Empty Lists and Parameter Limits

`IN (:ids)` queries behave subtly when lists are empty or huge. Define the contract for empty lists: return empty, omit predicate, or raise validation error. Never let an empty list accidentally return all records.

For large lists, check database/driver bind-parameter limits. Chunk into batches or use database-native array/table parameters where supported.

## 4. Testing Entity and Projection Mapping

Mapping regressions easily go undetected if tests inspect only a few String fields. Verify every data type, nullability, column name, and database-generated value.

### 4.1. Round-Trip Insert and Read

For each key entity, test:

1. Construct an entity with valid values.
2. Save via repository.
3. Read back by ID or natural key.
4. Compare all fields that must be preserved.
5. Verify database-generated values or auditing metadata if present.

```java
@Test
void savesAndReadsCustomer() {
    CustomerEntity draft = new CustomerEntity(
            null, "an@example.test", "An Nguyen");

    StepVerifier.create(customerRepository.save(draft)
            .flatMap(saved -> customerRepository.findById(saved.id())))
            .assertNext(found -> {
                assertThat(found.id()).isNotNull();
                assertThat(found.email()).isEqualTo("an@example.test");
                assertThat(found.displayName()).isEqualTo("An Nguyen");
            })
            .verifyComplete();
}
```

With records/immutable entities, always use the instance emitted by `save`; never assume the input instance is mutated in place.

### 4.2. Verify Numeric Types and Precision

For `BigDecimal`, test:

- Negative, zero, and positive values.
- Precision/scale at schema boundaries.
- Values with many decimal places.
- Whether out-of-scale values are rejected or rounded by database rules.
- `null` if the column is nullable.

Never route currency through `double` in tests or mappers. Compare `BigDecimal` according to business semantics: `compareTo` if only numeric value matters, or `equals` when scale is part of the contract.

### 4.3. Verify Temporal Types and Timezones

For `Instant`, `OffsetDateTime`, `LocalDateTime`, or other temporal types, test timestamps with non-UTC offsets and confirm round-trips preserve the exact instant per schema conventions.

Verify storage precision supported by the database. Some databases truncate timestamps to microseconds or milliseconds; tests should assert at actual supported precision rather than assuming nanoseconds always survive.

Test timestamps around DST transitions if the application uses regional local times. `LocalDateTime` carries no timezone and therefore needs explicit conversion rules.

### 4.4. Verify Nulls and Defaults

Test separately:

- Omitting a column so the database applies `DEFAULT`.
- Binding an explicit `NULL`.
- `NOT NULL` columns rejecting `null`.
- Generated/read-only columns being read back without being written from the entity.
- `@InsertOnlyProperty` not being overwritten on update.
- `@Transient` being excluded from persistence.

Never assume Java `null` automatically omits a column from an `INSERT`. Inspect actual generated SQL or database state to confirm semantics.

### 4.5. Verify UUID, Enum, JSON, Array, and Binary Types

If the application uses specialized types, write round-trip tests covering edge cases for each:

- Native UUID vs. text representation.
- Enum labels, unknown values, and `null`.
- Nested JSON objects, Unicode, arrays, and null properties.
- SQL arrays with empty or null elements if supported.
- Empty and large binary payloads.

Verify both Spring Data custom converters and driver codecs against a real database. A converter working in repositories does not guarantee manual bindings via `DatabaseClient` use the exact same conversion path.

### 4.6. Verify Projections and Aliases

For queries returning DTOs/projections, verify SQL aliases match property names or mapping functions:

```sql
SELECT c.display_name AS customer_name,
       COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.display_name
```

Test nulls produced by `LEFT JOIN`, numeric types returned by `COUNT`, and customers with zero orders. A wrong alias can cause fields to map as `null` or fail only at runtime.

## 5. Testing Auditing and Optimistic Locking

If entities use `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate`, `@LastModifiedDate`, or `@Version`, add regression tests for insert/update lifecycles.

### 5.1. Auditing

With `@EnableR2dbcAuditing` and `ReactiveAuditorAware`, verify:

- Insert sets creator and created date.
- Update preserves original creator and created date.
- Update modifies last modifier and modified date.
- Anonymous or background jobs follow defined policy.
- Immutable entities returned by `save` carry updated metadata.

Inject a fixed `Clock` so timestamp assertions do not depend on wall-clock timing.

### 5.2. Optimistic Locking

With `@Version`, verify:

- Insert initializes version.
- Successful update increments version.
- Two instances reading the same version: only the first write succeeds; the second throws an optimistic locking exception.
- Custom SQL/bulk updates enforce their own version predicates if required.

Concurrency tests must run against a real database and ensure both entities are read before the first write commits. Mocking the exception does not prove the SQL contains a version predicate.

## 6. Testing Transactions and Data Integrity

A transaction regression test must inspect final database state, not merely assert that a method emits an error.

### 6.1. Verify Commits

Create a multi-write business flow inside one transaction; after the publisher completes successfully, read back from a separate transaction/connection to verify changes committed.

For example, placing an order may:

1. Deduct or reserve inventory.
2. Create the order.
3. Create order lines.
4. Record a payment intent or related status.

Tests must confirm all changes persisted with valid foreign key links.

### 6.2. Verify Rollback on Step Failure

Suppose inventory reservation succeeds, but order creation violates a constraint. When all steps share a transaction, inventory must roll back.

```java
@Transactional
public Mono<OrderEntity> placeOrder(OrderCommand command) {
    return inventoryRepository.reserve(command.items())
            .then(orderRepository.save(toOrder(command)))
            .flatMap(order -> orderLineRepository.saveAll(
                    toLines(order, command.items())).then(Mono.just(order)));
}
```

Integration tests should deliberately fail a later step and then read back inventory/orders in an independent transaction to confirm zero partial writes.

Never swallow errors inside a transaction with `onErrorResume` if business rules require rollback. Converting an error into normal completion inside the transaction boundary prevents the transaction manager from seeing the error signal to roll back.

### 6.3. Verify Isolation and Concurrency

For isolation-sensitive flows, open two independent transactions and interleave reads/writes. Test for anomalies the system must prevent:

- Lost updates.
- Double booking or overselling.
- Duplicate inserts.
- Dirty reads if database/isolation permits them.
- Proper handling of serialization failures or deadlocks.

Never run two concurrent queries on the same transaction connection if the driver forbids concurrent statements. Use two separate transactions/connections to simulate two independent requests.

### 6.4. Verify Transaction Context in Reactor

R2DBC operations must stay within the same reactive pipeline so the transaction manager propagates context. Never call `subscribe()` or `block()` internally and detach work from the transaction.

Tests should confirm nested writes roll back together on failure, and operations launched on independent subscriptions do not accidentally join the active transaction.

### 6.5. Verify Cancellation

When requests cancel or clients disconnect, verify how queries/transactions behave. Check whether connections return to the pool, uncommitted transactions roll back, and no unintended background writes continue.

Cancellation behavior depends on the driver and database; never assume canceling a subscription immediately halts server-side execution. For critical writes, design explicit idempotency and operation states.

## 7. Testing Generated SQL and Query Plans

Asserting exact SQL strings is often brittle because aliases, column ordering, or identifier quoting can change across framework versions. Instead, test behavior and essential query properties.

### 7.1. When to Assert SQL Text

SQL text assertions are useful when:

- The query is critical custom SQL.
- You must guarantee a tenant predicate or optimistic version predicate is present.
- You must verify `LIMIT`/`OFFSET`, `ORDER BY`, or cursor conditions.
- A framework upgrade could alter critical syntax.

Keep assertions structural rather than locking tests to whitespace or irrelevant aliases. Even better, execute the query against a database and assert results to prove semantics.

### 7.2. Capturing SQL in Tests

Enable appropriate driver/framework logging or use proxy/observability instrumentation to observe queries. Avoid logging sensitive bind values in CI or production. When asserting query counts, use instrumentation/spies at the proper layer and separate main queries from fixture/health-check queries.

### 7.3. EXPLAIN and EXPLAIN ANALYZE

In PostgreSQL, `EXPLAIN` shows the estimated plan; `EXPLAIN ANALYZE` executes the query and reports actual metrics. Other databases offer equivalent syntax and tools.

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_code, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

When inspecting plans, watch for:

- Whether sequential scan vs. index scan fits selectivity.
- Whether estimated rows diverge sharply from actual rows.
- Whether join strategies produce huge intermediate row sets.
- Expensive sorts or disk spills.
- Changes in buffer reads and execution time.
- Whether index column order matches predicates and sorting.

Never require every query to use an index. For small tables or low-selectivity predicates returning most rows, sequential scan can be optimal. Regression tests should watch plans and costs on realistic data rather than blindly asserting specific plan node names.

### 7.4. Query Plans Change with Statistics and Data

Query plans depend on statistics, parameter distributions, database versions, caches, and system load. A different plan does not always mean a regression. Compare actual rows, buffers, execution times, and workload context. After loading large fixtures, update statistics as required by the database before measuring.

## 8. Designing Performance Regression Tests

Performance tests must answer a focused question: did this change slow down queries or business flows past an acceptable threshold?

### 8.1. Choose Appropriate Metrics

| Metric | Meaning | When Useful |
|---|---|---|
| Throughput | Requests/queries completed per second | Comparing overall processing capacity |
| p50 latency | Median request duration | Assessing typical experience |
| p95/p99 latency | Tail latency | Catching slow queries or pool contention |
| Error rate | Percentage of failures/timeouts | Detecting overload or driver errors |
| Connection acquire latency | Time spent waiting for a connection | Separating pool bottlenecks from slow queries |
| Active/pending connections | Pool utilization and wait queue | Evaluating concurrency and pool sizing |
| Rows scanned/returned | Work performed by the database | Catching over-fetching queries |
| CPU, I/O, buffer reads | Database cost | Catching expensive plans or workloads |
| Allocation/heap | Application cost | Catching excessive in-memory materialization |

Never measure only average latency. A query with good average latency can still have spiking p99 that causes API timeouts under load.

### 8.2. Establish a Baseline

Before changing queries or mapping, run a standard workload on the same database version, dataset, pool configuration, and comparable resources. Record:

- Commit/build version.
- Database and driver versions.
- Row counts and data distributions.
- Query parameters and request mix.
- Pool size and concurrency.
- Warm-up duration and measurement duration.
- Throughput, latency percentiles, error rate, and database metrics.

A baseline is only meaningful under comparable conditions. Comparing a local laptop run against a shared CI runner rarely proves a regression.

### 8.3. Warm-Up and Repeated Runs

JIT compilation, pool warm-up, prepared statement caches, and database buffer caches make initial requests slower. Separate warm-up from measurement. Run multiple iterations and examine medians or distributions rather than relying on a single measurement.

Do not flush caches between requests if production runs with warm caches; conversely, if production sees frequent cold starts, build a dedicated cold-start scenario.

### 8.4. Control Concurrency and Load

Performance tests should reflect realistic load profiles:

- Concurrent request count.
- Read/write ratio.
- Page/batch sizes.
- Cache hit rate if applicable.
- Queries involving joins/aggregates.
- Transactions holding connections longer.

Never use unbounded `flatMap` in tests and blame the driver for slow database execution. Distinguish test-harness concurrency, reactive pipeline concurrency, and pool limits.

### 8.5. Set Meaningful Regression Thresholds

Example criteria:

- p95 increases by no more than 15% over baseline in the same environment.
- Error rate remains within defined limits.
- Queries do not scan far more rows than returned results require.
- Pending connections do not grow continuously under target load.
- Throughput does not drop beyond acceptable bounds.

Base thresholds on SLOs and environment noise rather than copying arbitrary defaults. For noisy benchmarks, use repeated runs, confidence intervals, or distribution comparisons.

## 9. Detecting N+1 and Abnormal Query Counts

A small service change can accidentally turn a single join query into per-row follow-up queries.

Example:

```java
return orderRepository.findAllByStatus("PAID")
        .flatMap(order -> customerRepository.findById(order.customerId())
                .map(customer -> OrderView.from(order, customer)));
```

With 100 orders, the code may run one orders query and roughly 100 customer queries. That is the N+1 pattern.

Regression tests can check query counts against a fixed fixture scenario:

- For a join/projection query, query count remains at the expected constant.
- Increasing orders from 10 to 100 does not increase queries linearly unintentionally.
- With batch lookups, query count scales with batches rather than individual entities.

Exclude setup queries, transaction metadata, and health checks from query counts. Collect counts via datasource/driver instrumentation or test query logs. Avoid brittle assertions on an exact total if valid framework changes add a benign query; define a query budget per use case.

## 10. Testing Connection Pools and Resource Usage

A query may be fast in isolation yet time out under concurrent traffic because the pool saturates.

Regression suites or performance tests should observe:

- Active/allocated connections.
- Idle connections.
- Pending acquires.
- Acquire latency and timeout counts.
- Connection creation time.
- Duration transactions hold connections.
- Maximum connections relative to database budget.

Load scenarios should confirm:

1. The pool never allocates beyond `max-size`.
2. Completed or canceled queries return connections cleanly.
3. Load exceeding pool capacity follows configured timeouts/backpressure.
4. Pending acquires do not grow unboundedly.
5. Long transactions do not starve normal traffic of connections.

Never bump `max-size` just to make a test pass. If database CPU, I/O, or locks are saturated, a larger pool can make p99 worse.

## 11. Testing with StepVerifier

`StepVerifier` from `reactor-test` subscribes to publishers and asserts signals in order.

### 11.1. Verifying a Successful Mono

```java
StepVerifier.create(customerRepository.findByEmail("an@example.test"))
        .assertNext(customer -> {
            assertThat(customer.email()).isEqualTo("an@example.test");
        })
        .verifyComplete();
```

### 11.2. Verifying Flux and Element Counts

```java
StepVerifier.create(orderRepository.findByStatus("PAID"))
        .expectNextCount(2)
        .verifyComplete();
```

If ordering is part of the contract, assert each element in order rather than only `expectNextCount`.

### 11.3. Verifying Errors

```java
StepVerifier.create(orderService.updateWithStaleVersion(command))
        .expectError(OptimisticLockingFailureException.class)
        .verify();
```

Assert both the exception type and post-error database state. When exceptions wrap into domain exceptions, confirm the cause is preserved if required for diagnostics.

### 11.4. Verifying Timeouts and Cancellation

`StepVerifier` accepts a verification timeout so tests never hang indefinitely. For cancellation, use `thenCancel()` and subsequently verify via instrumentation or an independent query that resources and transactions were cleaned up.

Test timeouts act as suite guardrails; they do not prove production query timeouts are configured correctly.

### 11.5. Never Call subscribe in Tests to Skip Assertions

Calling `.subscribe()` and letting the test method return allows the test to finish before the publisher completes, missing asynchronous failures. Use `StepVerifier` or compose publishers into a single scenario that the test awaits and asserts.

## 12. Organizing Test Suites and Naming Tests

Group tests by behavior and layer:

```text
src/test/java/
  .../repository/
    CustomerRepositorySqlTest.java
    OrderRepositoryPagingTest.java
    OrderProjectionMappingTest.java
  .../transaction/
    OrderTransactionIntegrationTest.java
    OptimisticLockingIntegrationTest.java
  .../performance/
    OrderSearchPerformanceTest.java
  .../migration/
    SchemaMigrationCompatibilityTest.java
```

You do not have to mirror this exact directory layout. What matters is clear test names describing behavior, fixtures, and environments. Performance tests can live in a separate source set or pipeline stage so they do not slow down routine unit test runs.

### 12.1. Staging Tests in CI

A pipeline can split runs into stages:

| Stage | Contents | When Run |
|---|---|---|
| Fast tests | Unit tests, validation, pure Java mapping functions | Every commit |
| Database integration | Repository SQL, mapping, constraints | Every PR or main commit |
| Transaction suite | Rollback, isolation, optimistic locking | Key PRs or nightly depending on cost |
| Migration suite | Empty database and upgrades from older schemas | Every PR touching schemas |
| Performance suite | Baselines, query plans, load profiles | Nightly, pre-release, or when critical queries change |

Do not defer critical SQL tests until after merge if a query change is high risk. Frequency should reflect execution cost and feature criticality.

### 12.2. Isolating Parallel Tests

When multiple tests share one database, avoid full-table `TRUNCATE` while other tests run. Use separate containers/databases/schemas, unique fixture keys, or disable parallelism for suites doing global cleanup.

Every test must know who owns its data and how cleanup works. Never share natural keys across tests running concurrently on the same schema.

## 13. Testing Migrations and Schema Compatibility

Entity or query changes often accompany migrations. The regression suite should verify:

- All migrations execute cleanly from an empty database.
- New migrations upgrade the prior schema version cleanly.
- Legacy data backfills accurately.
- Old code continues running on expanded schemas during rolling deployments if required.
- New code runs properly after the expand phase.
- Contract migrations run only after no consumers depend on old structures.

For breaking migrations, use expand-and-contract and test intermediate phases rather than only the final state. Testing only new code against the final schema fails to catch old instances breaking mid-rollout.

## 14. SQL Query Plans and Performance Baselines in CI

CI performance tests must balance stability with regression sensitivity.

### 14.1. Avoid Overly Tight Thresholds

Query times fluctuate with shared CPU, disk, cache, container runtime, and CI load. Overly tight thresholds make suites flaky. Pick thresholds wide enough to absorb minor noise while still catching real regressions.

### 14.2. Separate Benchmarks from Correctness Tests

Correctness tests should be deterministic, exact, and run frequently. Benchmarks can run less often in controlled environments, archiving results across builds for trend comparison.

Never turn a 20 ms latency assertion into a hard gate on shared CI runners if runner variance exceeds the difference you want to detect.

### 14.3. Archive Results with Metadata

Every benchmark report should record:

- Git commit/build ID.
- Database/driver/framework versions.
- Dataset size and seed.
- Hardware/container limits.
- Pool size and concurrency.
- Warm-up and measurement durations.
- Throughput, p50/p95/p99, error rate.
- Query plans or plan summaries where appropriate.

Without metadata, comparing two latency numbers can lead to false conclusions.

### 14.4. Use Query Plans as Supporting Evidence

Saving plans for critical queries helps spot dropped indexes or changed join orders. However, plans vary with statistics and server versions; avoid brittle raw-text diffs. Focus on actual rows, buffers, sort spills, and major cost shifts.

## 15. Example: Regression Suite for an Order Search Query

Suppose an order search use case has:

- Required tenant.
- Optional status and date range.
- Customer name via join.
- Line count and total amount.
- Sort by newest creation time.
- Offset pagination and total count.

A test suite may include:

| Test | Data / Condition | Key Assertions |
|---|---|---|
| Tenant isolation | Two tenants with orders of the same status | Never returns orders from the other tenant |
| Optional filters | Status/time present or omitted | Exact matching subset for each combination |
| Join cardinality | Orders with 0, 1, and many lines | Each order appears exactly once |
| Aggregate mapping | `quantity × unit_price` | `totalAmount` has right type and value |
| Paging | Multiple orders with identical timestamps | No skips/duplicates in static dataset; stable ID tie-breaker |
| Count | One-to-many join | Total counts logical orders, not line items |
| Empty result | No orders match filters | Empty content, total equal to 0 |
| SQL injection | Input containing SQL syntax | Query structure remains unaltered |
| Query budget | Larger dataset | Zero N+1 queries |
| Performance | Target load | p95/p99 and acquire latency within limits |

Verify both response DTOs and database state when mutations happen. For read-only queries, verifying the result set and query budget may suffice.

## 16. Example: Regression Suite for an Order Placement Transaction

An order placement use case reserves inventory, inserts an order, and inserts order lines inside one transaction. Critical tests:

1. **Happy path:** all operations commit and foreign keys link accurately.
2. **Constraint failure:** an invalid order line rolls back the entire transaction.
3. **Insufficient inventory:** no order is created if inventory reservation fails.
4. **Concurrent requests:** two concurrent requests cannot oversell inventory.
5. **Optimistic conflict:** updating with a stale version fails predictably.
6. **Cancellation:** canceling before commit leaves no partial data per contract.
7. **Retry:** only transient failures retry without creating duplicate orders.

Specifically for double booking/overselling, coordinate two competing transactions against a real database. Sequential tests cannot detect race conditions.

## 17. Triaging Regression Results

When a test fails, classify the cause instead of blindly updating assertions to make the suite green.

| Symptom | Area to Investigate |
|---|---|
| Wrong result set | Predicates, tenant scope, joins, null semantics |
| Wrong ordering | `ORDER BY`, tie-breakers, collation, cursors |
| Wrong total | Count query, distinct, group by, having |
| Null or wrong mapped type | Aliases, converters, driver codecs, schema types |
| Timestamp skew | Timezone, precision, session settings |
| Incomplete rollback | Transaction boundaries, nested subscriptions, error recovery |
| Lost update | `@Version`, update predicates, isolation |
| Load test timeouts | Pool acquires, query latency, lock waits, concurrency |
| Degraded query plan | Indexes, statistics, predicates, cardinality estimates |
| N+1 | Fan-out in `flatMap`, lazy follow-up queries, projections |

If a new test uncovers a bug that predated the current change, track it as a separate defect and scope the fix. Never delete a test merely because it exposed broken legacy behavior.

## 18. Common Mistakes When Building a Regression Suite

### Testing Repositories Only with Mocks

Mocks do not execute SQL and do not verify mapping, constraints, dialects, or drivers. Use mocks for unit tests, paired with integration tests against a real database.

### Using a Different Database Engine Than Production

SQL behavior, data types, and transaction semantics vary across engines. Use Testcontainers or integration databases matching the production engine.

### Tiny, Unrepresentative Fixtures

A handful of rows hides full table scans, N+1s, and large-dataset paging bugs. Build dedicated performance datasets whose distributions mirror real workloads.

### Asserting Only Return Values

A method can return the right response while writing wrong data or committing partially. Re-read database state to verify final state on write use cases.

### Measuring Only Average Latency

Averages hide tail latency. Track p95/p99, error rates, and acquire latency.

### Overly Rigid Query Plan Assertions

Plans can legitimately change with statistics or server versions. Check cost and key characteristics rather than asserting exact full plan text.

### Wrapping Every Test in Transaction Rollback

Some tests must observe real commits, multiple connections, or concurrency. Wrapping the entire scenario in a test transaction distorts the behavior under test.

### Running Full-Table Cleanups in Parallel

Concurrent tests can lose fixtures or observe mid-run mutations. Isolate databases/schemas or use test-specific fixture keys.

### Calling subscribe to Finish Tests Early

Tests can exit before publishers finish and silently drop errors. Use `StepVerifier` or compose publishers properly.

### Neglecting Generated Values and Null Semantics

IDs, defaults, computed columns, timestamps, and explicit nulls frequently depend on database/driver specifics. Add dedicated integration tests.

### Failing to Store Baselines and Benchmark Environments

Latency numbers without metadata cannot be compared reliably. Record versions, datasets, pool settings, concurrency, and runner specs.

## 19. Workflow for Building the Regression Suite

1. List the most critical persistence queries and use cases.
2. Document contracts for predicates, joins, sorting, paging, aggregates, and counts.
3. Identify entities/projections and every data type needing verification.
4. Define transaction boundaries, rollback rules, isolation, and concurrency invariants.
5. Select production-matching database/driver versions and pin test environments.
6. Create schemas via migrations/SQL initialization and deterministic fixtures.
7. Write repository integration tests using `StepVerifier`.
8. Write mapping round-trip tests for types, nulls, defaults, and generated values.
9. Write multi-connection transaction/concurrency tests where required.
10. Assert query counts to catch N+1s and abnormal query budgets.
11. Capture query plans for critical SQL on representative datasets.
12. Record performance baselines and set thresholds aligned with SLOs and noise.
13. Separate fast tests, integration, migration, and performance stages in CI.
14. Isolate fixtures during parallel execution and ensure cleanup after both success and failure.
15. Archive results with environment metadata and triage regressions on failure.

## 20. Pre-Release Regression Checklist

- [ ] SQL filters, joins, sorting, paging, and aggregates are tested on the target database.
- [ ] Tenant predicates and authorization scopes are tested with multi-tenant fixtures.
- [ ] Count queries accurately count logical entities or groups.
- [ ] Nulls, empty collections, explicit nulls, and database defaults have dedicated tests.
- [ ] Generated IDs, generated columns, and trigger values are verified.
- [ ] Decimal precision, temporal timezones, and custom types have round-trip tests.
- [ ] Projection aliases and nullable join results are verified.
- [ ] Zero N+1s exceed defined query budgets.
- [ ] Transaction commits and rollbacks are verified by reading back final database state.
- [ ] Concurrency tests cover lost updates, overselling, or key invariants.
- [ ] Reactive pipelines contain no nested subscriptions detaching transactions/context.
- [ ] Cancellation and connection cleanup are tested where required.
- [ ] Query plans and indexes for critical queries have been reviewed.
- [ ] Performance baselines include dataset, version, pool, and concurrency metadata.
- [ ] p95/p99, throughput, error rate, and acquire latency remain within thresholds.
- [ ] Testcontainers/database images and dependency versions are pinned.
- [ ] Fixtures are deterministic and tests can re-run independently.
- [ ] Parallel tests share no destructive cleanups or conflicting fixture keys.
- [ ] Migrations from empty schemas and prior schema versions are verified.
- [ ] CI archives test/benchmark results with enough detail for comparison and investigation.

A strong R2DBC regression suite must prove both correctness and operational readiness. Testing SQL and mapping against a real database catches mismatches across entities, drivers, and schemas; testing transactions and concurrency verifies integrity under failures and parallel requests; and performance baselines plus query plans catch cost regressions. With deterministic fixtures, pinned environments, and metadata-rich results, the suite becomes a reliable safety net before every persistence release.
