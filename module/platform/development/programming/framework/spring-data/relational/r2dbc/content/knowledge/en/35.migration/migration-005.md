# Migrating Feature by Feature and Verifying Behavioral Equivalence

## 1. Why Migrate Feature by Feature?

Migrating database access from JDBC/JPA to Spring Data Relational R2DBC is not merely swapping repository types or changing blocking calls to `Mono`/`Flux`. The two models manage connections, transactions, mapping, concurrency, and data lifecycles differently.

A feature that runs reliably in production may depend on behaviors not explicitly recorded in design docs:

- Default sort order of a query.
- Handling of `null` values.
- When IDs are generated.
- How optimistic locking behaves.
- Which repositories a transaction spans.
- Whether side effects execute before or after commit.
- Decimal rounding rules and date/time conversions.
- Which exceptions are returned to clients.
- Whether an API call emits exactly one event.

If you migrate the entire application at once, whenever behavior changes it becomes hard to pinpoint whether the cause is mapping, SQL, transactions, the driver, or business logic.

A safer approach is migrating feature by feature, or by vertical slice. Each slice traverses every layer required to complete one use case, from API/service down to the database and related side effects. After each slice, the team verifies the new behavior against existing behavior before expanding scope.

For example, you might migrate viewing order details first, then order search, then order confirmation, and finally the payment flow. Each step has its own completion criteria and test evidence.

This approach helps:

- Narrow the blast radius of each deployment.
- Catch data and transaction discrepancies early.
- Preserve incremental release capability.
- Compare outputs between the old and new implementations.
- Determine precisely which features are ready to shift traffic.
- Reduce the risk of having to roll back the entire application.

## 2. What Does Behavioral Equivalence Mean?

Behavioral equivalence does not mean the new implementation must have the same classes, methods, or SQL as the old implementation. What must be preserved is the contract that users, integrated systems, and other features rely on.

For a data-access feature, examine at least the following dimensions:

| Dimension | What to Preserve or Intentionally Change |
|---|---|
| API contract | HTTP method, path, status, response schema, and error contract |
| Business rules | Validation conditions, state transitions, and business outcomes |
| Data mapping | Values read/written, nullability, precision, and data types |
| Query semantics | Filters, sorting, pagination, joins, counts, and result ordering |
| Transactions | Groups of operations committing/rolling back together |
| Concurrency | Behavior when multiple requests update data simultaneously |
| Side effects | Events, emails, payments, auditing, and emission timing |
| Security | Tenant scope, authorization, and permitted read data |
| Performance contract | Latency, throughput, pool usage, and resource limits |
| Failure behavior | Timeouts, retries, cancellation, and database errors |

Some internal differences are acceptable if they do not alter the external contract. For instance, the old implementation used a single join query while the new implementation uses two queries and merges the results. What must be confirmed is that data, access control, consistency, and performance still meet requirements.

Conversely, a subtle difference in nulls, result ordering, or transactions can alter business behavior even when the API still returns HTTP 200.

### 2.1. Distinguish Equivalence from Business Improvements

During migration, you may discover that legacy behavior is buggy or outdated. Do not silently change that behavior in the same technical migration step.

Classify behaviors:

- Behavior to preserve for compatibility.
- Old behavior that is buggy and needs fixing.
- Undefined behavior requiring a decision from the product/domain owner.
- New behavior intentionally redesigned.

If you migrate to R2DBC and change business rules simultaneously, test failures become ambiguous. Separate business changes into documented decisions with dedicated test suites.

## 3. Inventory Features Before Making Changes

Before writing R2DBC adapters, build an inventory of use cases accessing the database.

Example:

| Feature | Read/Write | Current Components | Key Risks | Planned Order |
|---|---|---|---|---|
| View order details | Read | JDBC/JPA repository | Mapping, relationships, and nulls | Low |
| Search orders | Read | Criteria/Specification | Filters, sorting, pagination | Medium |
| Create order | Write | JPA repository | IDs, transactions, and outbox | Medium |
| Update status | Write | JPA + service | Optimistic locking | High |
| Confirm order | Multi-write | Multiple repositories | Transaction boundary | High |
| Export report | Large read | JDBC streaming | Memory, cursors, and timeouts | High |
| Sync audit | Write + event | JDBC + broker | Retries and idempotency | High |

The inventory should also include less obvious access paths:

- Scheduled jobs.
- Batch imports/exports.
- Message consumers.
- Admin endpoints.
- Custom repository implementations.
- Stored procedures.
- Direct SQL.
- Startup tasks.
- Migration and maintenance scripts.

A use case may be invoked from multiple entry points. Migrating a service while forgetting a scheduled job or message consumer can leave two persistence models writing to the same table differently.

### 3.1. Document Each Feature's Dependencies

For each use case, record:

- Which controllers or message handlers call it.
- Which services orchestrate the business logic.
- Which repositories, templates, or `DatabaseClient` instances are used.
- Which tables and schemas are involved.
- The current transaction manager.
- Events or side effects generated.
- Other features depending on its output data.
- Existing API contract tests.

A dependency map clarifies whether a slice is truly independent.

### 3.2. Choose a Small Initial Slice

Start with a feature that:

- Has a clear contract.
- Has few side effects.
- Touches few tables.
- Is easy to seed with fixtures.
- Is easy to verify data correctness for.
- Can shift traffic independently.
- Has a rollback path to the old implementation.

A detail-read query is not necessarily the best first slice if it depends on heavy lazy loading or data assembled from many sources. Choose based on real complexity, not just CRUD labels.

## 4. Characterization Tests: Capturing Current Behavior

Before replacing an implementation, write tests describing the behavior of the running system. These are commonly called characterization tests or golden-master style tests.

The goal is to record actual behavior produced by the legacy implementation, including undocumented details.

For example, for order search, record:

- When `status` is omitted, what is the default filter?
- Is `keyword` trimmed or kept with whitespace?
- Is search case-sensitive or case-insensitive?
- When start date equals end date, what is returned?
- What field is used for default sorting?
- How are two rows with identical timestamps ordered?
- How are page sizes of 0 or negative numbers handled?
- Does no matches return an empty list or an error?
- Does total count apply the exact same filters as the list?
- Which tenants are allowed to see the data?

Tests must not check only a happy-path fixture. Include boundary data to uncover hidden rules.

### 4.1. Example Test of Current Contract

~~~java
@Test
void searchShouldUseStableDefaultOrdering() {
    SearchRequest request = new SearchRequest(
        null,
        0,
        20,
        null,
        null
    );

    StepVerifier.create(legacyOrderService.search(request))
        .assertNext(page -> {
            assertThat(page.items())
                .extracting(OrderSummary::id)
                .containsExactly(103L, 102L, 101L);

            assertThat(page.totalElements()).isEqualTo(3);
        })
        .verifyComplete();
}
~~~

This example assumes the legacy service is wrapped in an appropriate test API. In real projects, the legacy implementation may return synchronous types; write tests matching its current API without forcing it reactive merely to write characterization tests.

### 4.2. Store Reproducible Fixtures and Expected Outputs

Fixtures should include:
- Normal records.
- Null data.
- Boundary values.
- Two rows with identical sort values.
- Data belonging to another tenant.
- Soft-deleted records if the application uses soft deletes.
- Data with varying versions.
- Invalid business states.

Never use the production database as a test source. Use reproducible synthetic schemas and datasets.

### 4.3. Do Not Freeze Security Bugs

If characterization tests reveal that the legacy implementation leaks data from another tenant, do not treat that as behavior to preserve. Record it as a security bug and address it via an approved fix. Equivalence never means replicating vulnerabilities.

## 5. Designing Boundaries to Swap Implementations

A helpful approach is keeping the application contract stable while swapping the persistence adapter underneath.

Example:

~~~java
public interface OrderReader {
    Mono<OrderDetails> findDetails(long orderId, TenantId tenantId);
}
~~~

Current implementation:

~~~java
@Repository
public class JdbcOrderReader implements OrderReader {
    // Current JDBC/JPA implementation
}
~~~

New implementation:

~~~java
@Repository
public class R2dbcOrderReader implements OrderReader {
    // R2DBC implementation
}
~~~

Service depends on the abstraction:

~~~java
@Service
public class OrderQueryService {

    private final OrderReader orderReader;

    public OrderQueryService(OrderReader orderReader) {
        this.orderReader = orderReader;
    }

    public Mono<OrderDetails> details(
            long orderId,
            TenantId tenantId) {
        return orderReader.findDetails(orderId, tenantId);
    }
}
~~~

This is one example of an adapter boundary. Not every application needs a new interface for every repository. Introduce boundaries where they make swapping implementations, testing, or managing multiple persistence sources clearer.

If the old implementation is blocking, do not pretend it is non-blocking simply by changing its return type to `Mono`. When temporarily invoking JDBC in WebFlux, isolate blocking work on an appropriate scheduler and mark it as transitional.

## 6. Migrating by Vertical Slice

A slice should complete an entire use case flow rather than migrating one technical layer across the whole system at once.

Example slice for viewing order details:

~~~text
HTTP GET /orders/{id}
        |
        v
OrderController
        |
        v
OrderQueryService
        |
        v
OrderReader
        |
        v
R2dbcOrderReader
        |
        v
R2dbcEntityTemplate / DatabaseClient
        |
        v
Orders database
~~~

An order-write slice may also involve a transaction manager and outbox:

~~~text
HTTP POST /orders
        |
        v
OrderCommandService
        |
        v
Reactive transaction
        |
        +-- OrderRepository.save(...)
        |
        +-- OutboxRepository.save(...)
        |
        v
COMMIT
~~~

Each slice should have:
1. A contract and acceptance criteria.
2. R2DBC mapping and queries.
3. Transaction boundaries if writes occur.
4. Equivalence tests.
5. Performance and resource measurements.
6. A traffic-shifting plan.
7. An implementation rollback plan.

### 6.1. Migrate Reads Before Writes When Appropriate

Some systems can start with read-only use cases because they avoid dual-write risks and write side effects.

However, read paths still require checking:
- Tenant scope.
- Cross-query consistency.
- Sorting and pagination.
- Locking or snapshot semantics if required.
- Query latency.
- Result size.

Never assume read operations are risk-free.

### 6.2. Never Split a Single Transaction Mid-Migration

If a use case updates two tables atomically, do not migrate only the first repository to R2DBC while keeping the second on JDBC and expect a single shared transaction.

`R2dbcTransactionManager` manages the R2DBC `ConnectionFactory`. The JDBC transaction manager manages the JDBC `DataSource`. Two separate managers do not automatically form one ACID transaction.

Migrate all writes within the same transaction boundary together in one slice, or design an outbox/saga coordination flow if the two resources must stay separate.

## 7. Key Differences When Moving from JDBC/JPA to R2DBC

### 7.1. Blocking vs. Non-Blocking

JDBC is a blocking API. Calling a query usually makes the thread wait for results. R2DBC is a reactive API: operations are represented as `Publisher`s and results emit when subscribed.

JDBC example:

~~~java
Order order = jdbcTemplate.queryForObject(
    "SELECT id, status FROM orders WHERE id = ?",
    mapper,
    orderId
);
~~~

R2DBC example:

~~~java
Mono<Order> order = orderRepository.findById(orderId);
~~~

Do not just change the return type. Review:
- Threading.
- Subscription lifecycle.
- Error propagation.
- Cancellation.
- Backpressure.
- Transaction context.
- Whether downstream APIs are blocking.

Never call `block()` on the event loop to keep code feeling sequential like JDBC.

### 7.2. JPA Persistence Context Has No Direct Copy

JPA `EntityManager` has a persistence context, dirty checking, lazy loading, and cascade semantics. Spring Data Relational R2DBC does not provide a JPA-like persistence context.

In R2DBC:
- Modifying an object in memory is not automatically flushed merely because a transaction is open.
- You must explicitly call repository `save` or a write operation.
- There is no JPA-style proxy lazy loading.
- Entity relationships are not loaded automatically under the same model.
- Cascade persistence must not be assumed as in JPA.
- Queries and aggregate boundaries must be designed more explicitly.

For example, in JPA, code can mutate a managed entity and commit so dirty checking persists it. With R2DBC, explicitly call `save`:

~~~java
return orderRepository.findById(orderId)
    .flatMap(order -> {
        order.setStatus("CONFIRMED");
        return orderRepository.save(order);
    });
~~~

### 7.3. Generated IDs and Database-Generated Values

JPA has many ID generation strategies and lifecycle callbacks. R2DBC relies on database/driver generated-value capabilities and mapping strategies.

Verify:
- Whether IDs are generated on insert.
- Whether returned entities contain the ID.
- How versions are updated.
- Whether database default values are read back.
- Whether triggers or generated columns are returned via `RETURNING`/driver support.

Do not assume the input entity passed to `save` is mutated in place like the old implementation. Use the entity emitted by the repository and test actual database/driver behavior.

### 7.4. Mapping and Conversion

Verify every data type:
- Decimal precision and scale.
- `LocalDate`, `LocalDateTime`, `Instant`, and timezones.
- Booleans.
- Enums.
- UUIDs.
- JSON or database-specific types.
- Binary data.
- Nulls and defaults.
- Table/column names, quoting, and schemas.

A mapping may run without throwing errors while silently rounding decimals or shifting timezones. Tests should assert values read back from the database, not just objects before `save`.

### 7.5. Queries and Pagination

JPA Specifications, Criteria API, native queries, and Spring Data repository methods do not always map one-to-one to R2DBC.

Verify:
- Generated SQL.
- Driver-specific bind markers.
- Null semantics.
- Case sensitivity.
- Collation.
- `LIKE` and wildcard escaping.
- `ORDER BY` and null ordering.
- `LIMIT`/`OFFSET`.
- Count queries.
- Joins and projections.

When rewriting queries, test with boundary data to verify semantics rather than comparing SQL strings alone.

### 7.6. Transactions and Propagation

JDBC/JPA typically uses thread-bound transactions. R2DBC reactive transactions propagate via Reactor Context.

Verify:
- `R2dbcTransactionManager` is selected properly.
- The transactional service method returns the publisher.
- No manual `subscribe()` inside services.
- No `block()` calls.
- All repositories share the corresponding `ConnectionFactory`.
- Errors reach the transaction boundary to trigger rollback.
- External side effects are not mistakenly assumed to roll back.

### 7.7. Locking and Optimistic Concurrency

If JPA uses `@Version`, Spring Data Relational R2DBC also supports optimistic locking via `@Version` on the corresponding entity-mapping path. However, direct SQL or custom updates are not automatically guarded by `@Version`.

Verify:
- Initial version value.
- Version after insert/update.
- Exception thrown on stale update.
- Retry behavior.
- Version predicates in custom SQL if needed.
- Whether writers outside Spring Data uphold the same invariant.

### 7.8. Callbacks and Auditing

Spring Data Relational entity callbacks are scoped to the mapping lifecycle. Do not assume they replace every JPA entity listener or run for direct SQL via `DatabaseClient`.

Cross-check each rule:
- `createdAt`/`updatedAt`.
- `createdBy`/`modifiedBy`.
- Pre-mapping field normalization.
- Transient values after loading.
- Audit events.
- Callback execution order and side effects.

If a rule must apply across all write paths, enforce it in service/domain policies or database constraints/mechanisms rather than relying solely on callbacks.

## 8. Verifying Queries and Data Outputs

### 8.1. Compare Against the Same Data Snapshot

To compare the old and new implementations, both must read the same data state or equivalent fixtures.

Options:
- Seed two identical test databases.
- Reset the database between runs.
- Run both queries against a shared database if they are strictly read-only with no side effects.
- Use snapshots or transaction isolation appropriate for the test goal.

If data changes between runs, output differences may not come from the implementation.

### 8.2. Normalize Outputs Before Comparing

Do not blindly serialize and compare objects if responses contain unstable fields such as:
- Current timestamps.
- Random IDs.
- Unspecified collection ordering.
- Trace IDs.
- Environment-generated values.

Normalize non-contract fields while preserving business-meaningful differences such as:
- Amount.
- Currency.
- Status.
- Tenant.
- Owner.
- Version when version is part of the contract.
- Record counts.
- Ordering when the API guarantees ordering.

### 8.3. Compare Ordered Query Results

If the API defines a sort contract, compare lists in exact order. If ordering is unspecified, compare sets by stable keys and document that contract.

Never use `HashSet` to compare when order is part of the behavior.

### 8.4. Compare Database State After Writes

For write use cases:
1. Run the command against the old implementation's database fixture.
2. Run the equivalent command against the R2DBC fixture.
3. Read back all affected tables.
4. Normalize non-contract technical fields.
5. Compare final state, audit records, and outbox rows.
6. Verify the count of side effects emitted.

Identical responses do not prove identical persistence. An implementation could return the right response while missing a secondary table or version update.

## 9. Shared Contract Tests for Both Implementations

When you have an abstraction such as `OrderReader`, you can write contract tests that run the exact same suite against both the JDBC adapter and the R2DBC adapter.

Example structure:

~~~java
abstract class OrderReaderContractTest {

    protected abstract OrderReader orderReader();

    protected abstract void resetAndSeed();

    @BeforeEach
    void setUp() {
        resetAndSeed();
    }

    @Test
    void shouldReturnOrderWithinTenant() {
        StepVerifier.create(
                orderReader().findDetails(1001L, TenantId.of("tenant-a"))
            )
            .assertNext(details -> {
                assertThat(details.id()).isEqualTo(1001L);
                assertThat(details.tenantId().value())
                    .isEqualTo("tenant-a");
            })
            .verifyComplete();
    }

    @Test
    void shouldNotExposeAnotherTenantOrder() {
        StepVerifier.create(
                orderReader().findDetails(2002L, TenantId.of("tenant-a"))
            )
            .verifyComplete();
    }
}
~~~

One subclass configures the JDBC adapter; another configures the R2DBC adapter. For synchronous JDBC implementations, a separate synchronous contract interface or appropriate test adapter can be used rather than forcing both implementations into an artificial reactive abstraction.

Contract tests should focus on observable outcomes. Dedicated tests for transactions, pools, and cancellation are still necessary because the two technologies have different lifecycles.

## 10. Verifying Transaction Equivalence

For multi-table write use cases, prove that changes requiring atomicity are genuinely atomic.

Example order creation flow:
- Insert order.
- Insert order items.
- Deduct inventory.
- Write outbox event.

The success test confirms all data is present. The failure test deliberately fails the final step and reads back the database to confirm earlier steps rolled back.

With R2DBC:

~~~java
@Test
void shouldRollbackAllWritesWhenOutboxFails() {
    StepVerifier.create(orderService.create(commandThatFailsOutbox))
        .expectError()
        .verify();

    StepVerifier.create(orderRepository.findByBusinessKey(command.key()))
        .verifyComplete();

    StepVerifier.create(inventoryRepository.findById(productId))
        .assertNext(inventory ->
            assertThat(inventory.getAvailable()).isEqualTo(10)
        )
        .verifyComplete();
}
~~~

Adapt this example to your repository return types and fixtures. Tests must inspect state after the service publisher terminates, avoiding an outer test transaction that masks the service's own commit/rollback behavior.

### 10.1. Verify the Correct Transaction Manager Source

While JDBC and R2DBC coexist during transition, confirm each use case uses the right transaction manager.

A JDBC `@Transactional` does not manage R2DBC operations. An `R2dbcTransactionManager` does not manage JDBC connections.

Never mark migration successful merely because a service test passed; verify data is written using the intended resource and transaction boundary.

### 10.2. Off-Database Side Effects

If a use case emits events, sends emails, or calls payment gateways:
- Identify when side effects occur.
- Verify invocation count.
- Verify retries and idempotency.
- Never assume a database rollback undoes external systems.
- Use an outbox when recording an event must be atomic with local data.

Side-effect behavior is part of the business contract.

## 11. Shadow Reads and Output Comparison

For some read features, you can serve responses from the old implementation while executing the new implementation in shadow mode to compare results.

Conceptual flow:

~~~text
                Read request
                    |
                    v
              Read service
                    |
          +---------+---------+
          |                   |
          v                   v
      JDBC reader         R2DBC reader
          |                   |
          v                   v
      Old result          New result
          |                   |
          v                   v
       Response           Compare/log
          |
          v
       Client
~~~

Shadow reads are suitable only when the new query has no side effects. Consider:
- Doubling database read load.
- Data changing between the two reads.
- Whether both share the same transaction snapshot.
- Ensuring shadow failures never break the primary response.
- Avoiding logging sensitive data during comparisons.
- Sampling the percentage of shadowed requests.
- Tracking discrepancies by field and query type.

If both queries run against the same database at slightly different times, outputs may differ because data mutated in between. Use fixtures/snapshots in tests or shadow only queries with suitable semantics.

Never shadow writes by executing both JDBC and R2DBC implementations in production. That can create duplicate records, emit duplicate events, or double-deduct inventory.

## 12. Avoiding Dual-Writes When Migrating Write Paths

During migration, a tempting idea is writing with both JDBC and R2DBC concurrently to compare results.

That is a dual-write and is usually dangerous without a consistency protocol:
- JDBC commits while R2DBC fails.
- R2DBC commits while JDBC fails.
- One side retries and creates duplicates.
- Both sides increment versions differently.
- Side effects fire twice.
- No single transaction spans both resources.

To validate a new write path, prefer:
- Testing against dedicated database fixtures.
- Replaying anonymized traffic copies.
- Running migration rehearsals in staging.
- Routing a subset of requests to the new implementation via feature flags.
- Comparing state when only a single implementation writes data.

If there is a mandatory reason to write to multiple stores, design outbox, CDC, or reconciliation workflows with explicit idempotency and ownership. Never use two independent `save` calls as a migration strategy.

## 13. Shifting Traffic with Feature Flags or Routing

Once a slice is verified, shift traffic incrementally:

1. Disable the new implementation by default.
2. Enable it in test/staging environments.
3. Enable for a small tenant group or small percentage if supported.
4. Monitor error rates, latency, pool metrics, and data discrepancies.
5. Increase percentage across checkpoints.
6. Cut over 100% of traffic once criteria are met.
7. Retain rollback capability for a defined window.

Example routing abstraction:

~~~java
@Service
public class OrderReaderRouter implements OrderReader {

    private final OrderReader jdbcReader;
    private final OrderReader r2dbcReader;
    private final MigrationFlags flags;

    public OrderReaderRouter(
            JdbcOrderReader jdbcReader,
            R2dbcOrderReader r2dbcReader,
            MigrationFlags flags) {
        this.jdbcReader = jdbcReader;
        this.r2dbcReader = r2dbcReader;
        this.flags = flags;
    }

    @Override
    public Mono<OrderDetails> findDetails(
            long orderId,
            TenantId tenantId) {

        if (flags.useR2dbcOrderReader()) {
            return r2dbcReader.findDetails(orderId, tenantId);
        }

        return jdbcReader.findDetails(orderId, tenantId);
    }
}
~~~

This example assumes both readers share a contract returning `Mono`. If the JDBC implementation is blocking, isolate it on a blocking scheduler during transition; never execute it directly on the WebFlux event loop.

Feature flags should have:
- An owner.
- A safe default value.
- Audit logging of flag changes if required.
- Fast toggle-off capability.
- No permanent migration branches left behind.
- A target date or criterion for flag removal.

## 14. Acceptance Criteria for Each Slice

Never shift traffic solely because code compiles or unit tests pass.

Each slice should have quantitative, verifiable criteria:

| Category | Example Criteria |
|---|---|
| Correctness | Responses and database state match the contract |
| Security | Tenant scope and authorization are preserved |
| Queries | Filters, sorting, nulls, and pagination are equivalent |
| Transactions | Rollback/commit behave properly across all error branches |
| Concurrency | Versions/constraints protect concurrent updates |
| Side effects | Events and outbox rows are not duplicated |
| Reliability | Timeouts/cancellations do not leak connections |
| Performance | p95/p99 and throughput meet SLOs |
| Capacity | Pool, database sessions, and memory stay within budget |
| Operations | Metrics, logs, and alerts suffice for diagnostics |
| Rollback | Can revert to the old implementation under defined conditions |

Specific thresholds must come from your system's SLOs and baseline. Do not copy generic numbers across all features.

### 14.1. Correctness Gate

Examples:
- All contract tests pass.
- Boundary tests for nulls, sorting, and pagination pass.
- Zero unexplained data discrepancies.
- Transaction rollback tests pass.
- Optimistic locking and idempotency tests pass if required by the use case.

### 14.2. Performance Gate

Compare on equivalent workloads:
- Throughput.
- p50/p95/p99 latency.
- CPU and heap usage.
- Acquired/pending connections.
- Database query latency.
- System-wide connection count.
- Error and timeout rates.

R2DBC does not guarantee faster execution than JDBC on every workload. If most time is spent in queries or the database, changing the access API will not speed up queries by itself. The migration goal may be concurrency scalability or end-to-end reactivity; measure against that actual goal.

### 14.3. Operational Gate

Confirm:
- Dashboards exist for pools and queries.
- Error logs include sufficient context without exposing sensitive data.
- Tracing covers critical use cases.
- Alerts cover acquire timeouts, query timeouts, and error rates.
- Rollback runbooks exist.
- An owner is assigned to monitor the rollout window.

## 15. Rollback Plan

Rolling back is not as simple as flipping a feature flag back to the old implementation. Verify backward compatibility across schema, data, and side effects.

Before cutting over a slice, determine:
- Can the legacy JDBC implementation still read and write the new schema?
- Are schema migrations additive and backward-compatible?
- Are there new required columns that legacy code does not populate?
- Does newly written data use formats legacy code cannot parse?
- Can legacy consumers process newly emitted events?
- Can new workers be stopped without losing outbox events?
- Is reverse backfill or reconciliation needed before reverting?

### 15.1. Prefer Expand-Contract Schemas

Typical sequence:

1. Expand: add new columns/tables/indexes in a way that keeps legacy code working.
2. Deploy code capable of understanding both old and new schemas if needed.
3. Cut over the feature to R2DBC.
4. Monitor and complete backfill.
5. Contract: drop old schema structures only after no legacy code depends on them.

Do not drop or rename columns in the same release that switches adapters if rollback still relies on legacy code.

### 15.2. Once Data Has Been Written by the New Implementation

If the new implementation writes data with different semantics, reverting to the old implementation may be unsafe. Check:
- Do new columns have valid default values?
- Does `version` share the same semantics?
- Can old consumers process new events?
- Does any data need reverse conversion?
- Were any irreversible external actions triggered?

Rollback readiness must rest on data compatibility, not just the ability to restart an old binary.

## 16. Monitoring and Comparing After Cutover

During the early phase after cutover, monitor the migrated slice specifically:

- Request rate.
- Error rate by exception type.
- p95/p99 latency.
- Query duration.
- Acquire wait and pending pool count.
- Transaction duration.
- Optimistic locking conflicts.
- Rows returned and response bytes.
- Outbox lag and retry count.
- Data discrepancies if cross-checking.

Compare against the pre-migration baseline over matching time windows and equivalent workloads. Shifts in traffic or data volume can skew naive comparisons.

When an incident occurs:
1. Identify which slice is affected.
2. Inspect metrics and traces.
3. Determine whether the root cause is bad data, timeouts, pool saturation, or transactions.
4. Decide whether to toggle off the flag or continue investigating.
5. Preserve logs and state needed for reproduction.
6. Resume rollout only once the cause is understood and resolved.

Do not rely on a single application-wide aggregate metric to declare a new slice healthy. Tag metrics by use case/implementation with bounded cardinality.

## 17. Example Migration Plan for an Order Search Feature

Suppose an existing order search API uses JPA Specifications.

### Step 1: Record the Contract

Request:
- Optional `keyword`.
- Optional `status`.
- Date range.
- `page` and `size`.
- Sort field and direction.

Response:
- List of `OrderSummary`.
- Total elements.
- Current page.
- Page size.

Document current implementation behavior for:
- Null/blank `keyword`.
- Start/end dates.
- Default sort.
- Excessively large page size.
- Other tenants.
- Empty results.

### Step 2: Build the R2DBC Query

Use DTOs and allowlists for filters/sorting. Choose `DatabaseClient` or `R2dbcEntityTemplate` based on complexity. Bind all values and apply `LIMIT`/`OFFSET` in the database.

~~~java
public Flux<OrderSummary> search(
        SearchCriteria criteria,
        TenantId tenantId,
        int page,
        int size) {

    int limit = validateSize(size);
    long offset = Math.multiplyExact((long) page, limit);

    return databaseClient.sql("""
            SELECT id, status, created_at
            FROM orders
            WHERE tenant_id = :tenantId
              AND (:status IS NULL OR status = :status)
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """)
        .bind("tenantId", tenantId.value())
        .bind("status", criteria.status())
        .bind("limit", limit)
        .bind("offset", offset)
        .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("status", String.class),
            row.get("created_at", LocalDateTime.class)
        ))
        .all();
}
~~~

This SQL illustrates the concept. Null binding and nullable parameter syntax must be verified with your specific driver and database. In some cases, conditionally building predicates outperforms nullable SQL expressions by allowing better index usage.

### Step 3: Verify the Count Query

If the response includes total elements, the count query must enforce the same tenant and filter predicates:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status;
~~~

Never omit the tenant predicate from the count query. Otherwise, `totalElements` can leak record counts from other tenants even when the list is filtered properly.

### Step 4: Run Contract Tests Against Both Adapters

Use identical fixtures and confirm:
- Same set of orders.
- Same order sequence.
- Same total count.
- Same date and null handling.
- No cross-tenant reads.
- Accurate page size and offset.

### Step 5: Measure Performance

Run workloads with default and maximum page sizes. Compare:
- p95/p99 latency.
- Query plans.
- Rows scanned/returned.
- Connection acquire wait.
- Database CPU.

### Step 6: Shift Traffic

Enable R2DBC in staging, then for a small tenant group or small traffic percentage. Monitor discrepancies and error rates. Once gates pass, ramp to 100%.

### Step 7: Remove Old Code After Stabilization

Remove the JPA adapter and related dependencies only when:
- No entry points still call it.
- Jobs and consumers have migrated.
- The rollback window has closed.
- The schema no longer needs compatibility with the old implementation.
- Dashboards confirm zero traffic hits the legacy path.

## 18. Common Mistakes During Migration

| Mistake or Misconception | Consequence | Fix |
|---|---|---|
| Rewriting the whole app at once | Hard to isolate causes of regressions | Migrate by vertical slice |
| Checking only that code compiles | Runtime behavior may diverge | Characterization and contract tests |
| Treating `Mono` as a new return wrapper for JDBC | Blocking still holds threads | Move truly to R2DBC or isolate blocking during transition |
| Expecting JPA dirty checking in R2DBC | Object mutations are not saved | Call `save` or explicit write operations |
| Assuming JPA-like lazy loading/cascades | Missing data or missing writes | Design explicit queries and aggregate boundaries |
| Ignoring generated IDs/default values | Wrong responses or related data | Verify returned values after insert |
| Comparing only API responses | Secondary/outbox tables may miss writes | Read back all related database state |
| Using one transaction manager for JDBC and R2DBC | Operations fall outside intended transaction | Match managers to resources; never assume cross-resource atomicity |
| Running both write implementations to compare | Duplicate writes/events or data drift | Use fixtures/replay and cut over with one single writer |
| Unbounded shadow reads | Doubles database load | Sample and cap shadow traffic |
| Comparing two queries across mutating data | False discrepancy alerts | Use snapshots/fixtures or account for timing |
| Migrating queries while dropping tenant filters | Cross-tenant data exposure | Write authorization contract tests for every query |
| Keeping legacy code too long after cutover | Two persistence paths hard to maintain | Set criteria and dates for removing old adapters |
| Rolling back code after breaking schema changes | Old version fails to run | Use expand-contract and data rollback plans |
| Measuring only throughput | Misses tail latency, pool waits, and errors | Measure p95/p99, resources, and correctness together |

## 19. Vertical Slice Implementation Checklist

Before starting:
- Identify the use case and all entry points.
- List repositories, tables, transactions, and side effects.
- Document the API contract.
- Write characterization tests.
- Define acceptance and rollback criteria.

During implementation:
- Build the R2DBC adapter.
- Verify mapping, queries, and null semantics.
- Verify transaction manager and `ConnectionFactory`.
- Keep blocking work off the event loop.
- Preserve tenant authorization.
- Bound query size, rows, and timeouts.
- Account for side effects and idempotency.

Before shifting traffic:
- Contract tests pass.
- Integration tests against target database/driver pass.
- Transaction rollback tests pass.
- Concurrency tests pass if concurrent updates apply.
- Performance tests meet SLOs.
- Metrics and alerts are in place.
- Schema is compatible with the rollback plan.
- Feature flags/routing have been tested.

After cutover:
- Monitor errors, latency, and data discrepancies.
- Confirm zero unexpected traffic hits the old adapter.
- Monitor pool and database capacity.
- Honor the planned rollback window.
- Remove old code and flags once criteria are satisfied.

## 20. Self-Check Exercises

### Exercise 1: Choosing the First Slice

A system has order details, order search, order creation, and order confirmation features. Which feature should go first?

Hint: Pick a use case with a clear contract, minimal side effects, and easy verification. There is no single fixed answer; examine dependencies and ability to shift traffic independently.

### Exercise 2: Characterization Tests

Why test the legacy implementation before replacing it?

Hint: To capture undocumented actual behavior, create a baseline for the new implementation, and prevent unintended contract changes.

### Exercise 3: JPA Dirty Checking

JPA code mutates an entity field and commits without calling `save`. Can this pattern stay unchanged when migrating to R2DBC?

Hint: Do not assume so. R2DBC has no JPA-style persistence context/dirty checking; explicitly invoke a `save` or write operation.

### Exercise 4: Blocking APIs

A JDBC service changes its method signatures to `Mono` while still calling `jdbcTemplate` directly inside. Has it become non-blocking?

Hint: No. JDBC remains blocking. During transition, isolate on an appropriate scheduler and track as technical debt; the end goal is R2DBC or an appropriate architecture.

### Exercise 5: Transaction Boundaries

A use case updates order and inventory in one transaction. Can you migrate just the order repository to R2DBC while keeping the inventory repository on JDBC and use one `@Transactional` for atomicity?

Hint: No. Two transaction managers govern separate resources; migrate the entire boundary together or design a different coordination mechanism.

### Exercise 6: Shadow Writes

Should you run both JDBC and R2DBC writes in production to compare outputs?

Hint: Never perform ad-hoc dual-writes. Use fixtures/replay or route to a single writer via feature flags.

### Exercise 7: Shadow Reads

Two implementations query the same table, but results differ because data changed between the two queries. How do you verify fairly?

Hint: Use fixtures/snapshots or consistent reads appropriate to the test; account for timing rather than treating every discrepancy as a mapping bug.

### Exercise 8: Generated IDs

After an insert, a service needs the ID to create an outbox event. Where should the ID come from?

Hint: Use the entity emitted by the `save` publisher and verify the driver/database returns generated values as expected.

### Exercise 9: Rollback

After cutover, R2DBC code writes to a newly added column. Why might re-enabling old JDBC code be unsafe?

Hint: Schema or data may not be backward-compatible. Expand-contract and verifying old code against new data are required.

### Exercise 10: Completion Criteria

Unit tests pass and the application compiles. Is it ready to shift 100% of traffic?

Hint: Not yet. You need contract/integration tests, transaction/concurrency tests, performance verification, security checks, metrics, and rollback readiness.

## 21. Key Takeaways

- Migrating feature by feature via vertical slices bounds scope and simplifies verification.
- Behavioral equivalence spans API, business rules, mapping, queries, transactions, concurrency, side effects, security, and performance.
- Inventory every entry point and dependency, including jobs, consumers, and direct SQL.
- Write characterization tests before replacing implementations.
- Keep application contracts stable and swap persistence adapters underneath where appropriate.
- Blocking JDBC does not become non-blocking just by wrapping it in `Mono`.
- R2DBC lacks JPA's persistence context, dirty checking, lazy loading, and cascade semantics.
- Verify generated IDs, default values, versions, nulls, decimals, timezones, and query semantics.
- R2DBC transactions use Reactor Context and `R2dbcTransactionManager`; do not assume JDBC transactions cover them.
- Migrate all operations sharing a transaction boundary within the same slice, or design outbox/saga coordination.
- Compare both API responses and resulting database state and side effects.
- Contract tests can be shared across adapters when the abstraction reflects the true contract.
- Shadow reads help compare read paths, provided load is bounded and snapshots are controlled.
- Avoid uncoordinated dual-writes in production.
- Use feature flags/canaries and quantitative acceptance gates when shifting traffic.
- Prepare expand-contract schemas and rollback plans before cutover.
- Evaluate correctness, p95/p99, pool metrics, database health, and error rates together.
- Remove old implementations only after confirming zero traffic and closing the rollback window.

Migrating to Spring Data Relational R2DBC is a series of verifiable changes, not a one-shot library swap. Each feature needs a clear contract, tests capturing legacy behavior, a new implementation, and evidence that data, transactions, security, and performance still meet requirements. Migrating by vertical slices, shifting traffic incrementally, and keeping rollbacks compatible keeps the transition firmly under control.
