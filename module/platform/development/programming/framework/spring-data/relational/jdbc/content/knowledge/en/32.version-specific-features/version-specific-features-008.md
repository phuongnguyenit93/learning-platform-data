# Designing Regression Tests When Upgrading Spring Data or Drivers

Upgrading Spring Data JDBC or a JDBC driver can alter persistence behavior even when business code remains unchanged. The framework may change how aggregates are mapped, how lifecycle callbacks fire, how transactions are managed, or how metadata is interpreted; the driver may change how data types are bound or read, how generated keys are retrieved, or how timestamps, exceptions, and batch statements are handled. An application may still compile and start cleanly yet write wrong data, read different types, fail to roll back as expected, or degrade in performance after an upgrade.

Regression testing for an upgrade must answer a concrete question: **which contracts that the application relies on must continue holding true on the new framework, driver, and database versions?** This lesson covers scoping the upgrade, establishing a baseline, designing integration tests, checking database/driver compatibility, evaluating transactions and migrations, and executing a controlled staged upgrade.

## 1. Distinguishing Components That Can Be Upgraded

A Spring Data JDBC application typically involves multiple versioned layers:

| Component | Role | Risk when changed |
| --- | --- | --- |
| Spring Boot | Manages dependencies and auto-configuration if the project uses Boot. | Changes BOM, default configs, auto-configured beans, and managed framework versions. |
| Spring Data JDBC | Aggregate mapping, repositories, callbacks, auditing, and SQL persistence. | Changes APIs, mapping, lifecycle behavior, query generation, or optimistic locking. |
| Spring Data Relational / Commons | Shared mapping infrastructure and abstractions. | Changes metadata, converters, repository infrastructure, or callback contracts. |
| Spring Framework | Transactions, bean lifecycle, proxies, and JDBC support. | Changes transaction interception, exception translation, and resource management. |
| JDBC driver | Bridge between Java and the database. | Changes type mapping, parameter binding, generated keys, metadata, timeouts, and SQL errors. |
| Database server | Executes SQL and manages transactions/storage. | Changes dialect, optimizer, constraints, isolation, precision, or SQL behavior. |
| Connection pool | Manages physical connections. | Changes validation, timeouts, leak detection, session state, and connection lifecycle. |
| Migration tool | Applies schema/data migrations. | Changes migration execution, transaction support, checksums, or ordering. |

Do not treat a dependency upgrade as a single isolated change if multiple components change versions together. If an application upgrades Spring Boot, Spring Data JDBC, the JDBC driver, and the database server simultaneously, a failing test cannot easily pinpoint which layer caused it.

### Define the Exact Scope of Change

Before modifying dependencies, record:

- Current and target versions of Spring Boot/Spring Data.
- The Spring Framework version selected by dependency management.
- Current and target JDBC driver versions.
- Production database engine and server version.
- Connection pool, migration tool, and Java runtime.
- Custom converters, custom dialects, repository fragments, and hand-written SQL.
- DataSource, transaction manager, timezone, schema, and pool configurations.

If using Spring Boot, prefer upgrading via Boot's compatible dependency management/BOM. Do not force an individual Spring Data module to a version outside Boot's managed set without verifying the compatibility matrix. For non-Boot applications, manage Spring Data/Framework module versions according to published compatible sets.

## 2. Identifying Contracts to Protect

You do not need to write tests for every internal framework implementation detail. List the behaviors your application depends on, then test them through public APIs and observable outcomes.

A useful inventory:

| Area | Contract to preserve |
| --- | --- |
| Aggregate mapping | Root and children are inserted, loaded, updated, and deleted with accurate structure. |
| ID generation | Generated IDs are returned accurately after insert. |
| Type conversion | Enums, UUIDs, decimals, date/time, JSON, or custom types round-trip accurately. |
| Null/defaults | Nulls, database defaults, and primitives/wrappers are handled properly. |
| Optimistic locking | Version increments properly; stale updates are detected. |
| Transactions | Multiple statements commit or roll back together per the use case. |
| Repository queries | Derived queries, `@Query`, pagination, sorting, and custom SQL return accurate results. |
| Lifecycle/auditing | Callbacks, events, and audit fields appear per application contract. |
| Database constraints | Unique, foreign key, check, and generated columns remain respected. |
| Driver behavior | Parameter binding, `ResultSet` mapping, generated keys, metadata, and exception translation work properly. |
| Migrations | Older databases migrate to the new schema and the application can still read/write. |
| Performance | Key queries do not introduce N+1 issues or regress beyond acceptable thresholds. |

Select tests from real business workflows and data shapes your application persists. For instance, if an aggregate has a child collection, a test should prove updating the root does not accidentally drop children. If audit timestamps are stored as `Instant`, tests must confirm round-tripping at the column's precision.

## 3. Separating the Baseline from the Target Version

The baseline is the observed behavior on the currently stable version combination. The target is the new dependency combination to verify. Use the same test fixtures and the same database engine/version for comparison.

```text
Baseline:
  Application commit: <known-good commit>
  Spring Data JDBC:    <current version>
  JDBC driver:         <current version>
  Database:            <engine and version>
  Java runtime:        <current version>

Target:
  Application commit: <upgrade branch>
  Spring Data JDBC:    <target version>
  JDBC driver:         <target version>
  Database:            <same engine/version for first comparison>
  Java runtime:        <same runtime unless Java is also upgraded>
```

When upgrading the database server around the same time, first compare the new framework/driver on the existing database version if compatibility permits. Then run a separate matrix for the new database server. This separation isolates framework, driver, and database engine regressions.

### Keep Fixtures Deterministic

- Include data with nulls, Unicode, boundary values, decimals, timestamps, and child collections.
- Fix the clock and timezone for time-related tests.
- Do not rely on row ordering if a query omits `ORDER BY`.
- Use explicit IDs when checking relationships; if IDs are database-generated, assert on returned values rather than assuming a sequence starts at a fixed number.
- Create a fresh schema per test suite or reset the database deterministically.
- Never use production data containing personal information; create synthetic fixtures mirroring real data shapes.

A baseline does not require storing a full snapshot of the production database. Store test results, version logs, migration versions, key query plans, and performance metrics for comparison.

## 4. Designing Tests by Layer

A strong regression suite combines small tests, integration tests, and operational checks. Each layer answers a different question.

| Layer | Verifies | Can detect |
| --- | --- | --- |
| Unit test | Domain rules, pure converters, routing policies. | Changes in application logic or type handling. |
| Repository integration test | Mapping, generated keys, queries, and aggregate lifecycle. | Changes in framework/driver/database interaction. |
| Transaction integration test | Commit, rollback, isolation, and optimistic locking. | Changes in transaction/resource behavior. |
| Migration test | Upgrading schema from an older version and reading/writing with new code. | Schema incompatibility and data loss. |
| Contract/API test | JSON, timestamps, enums, and error contracts. | Changes in data types exposed externally. |
| Performance test | Query count, latency, throughput, and pool behavior. | N+1 regressions, plan regressions, and resource contention. |
| Staging/canary | Real connections, credentials, network, pools, and observability. | Environmental discrepancies impossible to simulate in unit tests. |

`@DataJdbcTest` is useful for repository slice tests. However, it does not prove the full application is wired properly. Transaction, security, custom configuration, migration, and datasource routing tests require an appropriate context or full integration tests.

## 5. Using the Real Database Engine in Integration Tests

H2 or other in-memory databases are helpful for fast feedback, but they do not always mimic the production dialect. SQL syntax, generated keys, type conversion, locking, JSON, arrays, timestamps, sequences, and constraint behaviors can differ.

If production uses PostgreSQL, MySQL, or SQL Server, run core integration tests on the same engine and a production-compatible version. Testcontainers is a solid option for running real databases in CI pipelines; pin image tags to explicit versions instead of floating tags.

JUnit example with PostgreSQL Testcontainers (configure dependencies and properties for your project's Spring Boot/Testcontainers version):

```java
@Testcontainers
@DataJdbcTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class PurchaseOrderRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name",
            postgres::getDriverClassName);
    }

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void savesAndLoadsAggregate() {
        // Test the aggregate contract against real PostgreSQL.
    }
}
```

This example only illustrates structure; ensure schema migrations run in the test context and Testcontainers dependencies match your Java, JUnit, and Spring Boot versions. Pin both the database image and the JDBC driver version for reproducible results.
## 6. Testing Aggregate Mapping and Child Relationships

Spring Data JDBC manages aggregates via their roots. An upgrade must ensure persisted and reloaded objects preserve relationships, collection ordering, nullability, and foreign keys.

Example aggregate:

```java
@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    @Version Long version,
    String reference,
    String status,
    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    List<OrderLine> lines
) {}

public record OrderLine(
    Long productId,
    int quantity,
    BigDecimal unitPrice
) {}
```

A regression test should verify insert, load, update, and delete against the domain contract:

```java
@Test
void persistsRootAndChildRowsAcrossLifecycle() {
    PurchaseOrder draft = new PurchaseOrder(
        null,
        null,
        "PO-REG-001",
        "CREATED",
        List.of(
            new OrderLine(101L, 2, new BigDecimal("12.50")),
            new OrderLine(202L, 1, new BigDecimal("99.00"))
        )
    );

    PurchaseOrder saved = orders.save(draft);

    assertThat(saved.id()).isNotNull();

    PurchaseOrder loaded = orders.findById(saved.id()).orElseThrow();

    assertThat(loaded.reference()).isEqualTo("PO-REG-001");
    assertThat(loaded.lines()).containsExactly(
        new OrderLine(101L, 2, new BigDecimal("12.50")),
        new OrderLine(202L, 1, new BigDecimal("99.00"))
    );
}
```

This is an illustrative contract test. Adjust ID types, constructors, mappings, and repositories to match your domain. If child order has no business meaning, compare sets of values rather than relying on an unguaranteed order.

### Verify Updates Do Not Accidentally Drop Children

After the initial save, modify a root attribute and save again. Reload and confirm the child collection matches the updated aggregate state. Also verify deleting one child removes only that child without accidentally deleting the root or sibling children.

Cases to include:

- Aggregate with no children.
- Aggregate with one child and multiple children.
- Child with nullable fields.
- Empty collection after update.
- Reordered collection when order is persisted via a key column.
- Foreign key constraint from child to root.
- Deleting the root and checking child rows per mapping semantics.

Do not assert only on the object returned directly from `save`. Reload from the database via a fresh repository call to confirm the persisted state.
## 7. Checking Generated IDs and Optimistic Locking

Driver upgrades can affect how JDBC returns generated keys or identity/sequence column metadata. For aggregates with database-generated IDs, verify:

- ID after insert is non-null and has the expected type.
- Reloading by the returned ID retrieves the right aggregate.
- Batch inserts or `saveAll` (if used) populate IDs for each element in the expected order/contract.
- Sequences/identities are not unintentionally reset by migrations.
- Rolled-back inserts do not leave the application holding state assuming the row committed.

Example:

```java
@Test
void generatedIdentifierCanBeUsedToReloadAggregate() {
    PurchaseOrder saved = orders.save(newOrder("PO-REG-002"));

    assertThat(saved.id()).isPositive();
    assertThat(orders.findById(saved.id()))
        .isPresent()
        .get()
        .extracting(PurchaseOrder::reference)
        .isEqualTo("PO-REG-002");
}
```

If IDs are application-generated UUIDs, test UUID generation and mapping rules separately. Do not apply generated-key assumptions to every ID type.

### Optimistic Locking with `@Version`

With `@Version`, the framework tracks versions to detect updates based on stale aggregates:

```java
@Test
void staleAggregateCannotOverwriteNewerVersion() {
    PurchaseOrder firstRead =
        orders.findById(orderId).orElseThrow();

    PurchaseOrder secondRead =
        orders.findById(orderId).orElseThrow();

    orders.save(firstRead.withStatus("CONFIRMED"));

    assertThatThrownBy(() ->
        orders.save(secondRead.withStatus("CANCELLED"))
    ).isInstanceOf(OptimisticLockingFailureException.class);
}
```

This test needs appropriate transaction/fixture boundaries so the two reads represent two independent snapshots. Exact exception subclasses and aggregate update helpers depend on your Spring Data version; what matters is proving stale writes are rejected rather than silently overwriting newer changes.

If the application runs custom SQL updates against the same table, add tests verifying custom updates also check and increment the version. Hand-written SQL can bypass default optimistic locking.

## 8. Testing Custom Converters and Type Mapping

A new driver can alter the Java type returned by `ResultSet.getObject(...)`, how `PreparedStatement` parameters are bound, or column metadata. This is especially noticeable for UUIDs, JSON, enums, arrays, decimals, binary data, date/time types, and database-specific types.

If your application has a custom type like `Money`, use explicit converters:

```java
@WritingConverter
public class MoneyWritingConverter
        implements Converter<Money, BigDecimal> {

    @Override
    public BigDecimal convert(Money source) {
        return source.amount();
    }
}

@ReadingConverter
public class MoneyReadingConverter
        implements Converter<BigDecimal, Money> {

    @Override
    public Money convert(BigDecimal source) {
        return new Money(source);
    }
}
```

Register converters via `JdbcCustomConversions` configuration appropriate for your Spring Data version. Then test round-tripping against a real database:

```java
@Test
void customMoneyTypeRoundTripsThroughDatabase() {
    Invoice invoice = invoices.save(
        new Invoice(null, new Money(new BigDecimal("1234.56")))
    );

    Invoice loaded = invoices.findById(invoice.id()).orElseThrow();

    assertThat(loaded.total())
        .isEqualTo(new Money(new BigDecimal("1234.56")));
}
```

Edge values should include zero, negative numbers if permitted, varying scales, large values near column precision limits, and null if the field is nullable. For monetary values, test scale/rounding as well; ensure the JDBC driver or database does not silently round in violation of domain rules.

### Types Worth Testing Explicitly

| Type | Regression cases to include |
| --- | --- |
| UUID | Read/write, binding in `WHERE`, null, and binary/text storage per schema. |
| Enum | Stored enum name, behavior on legacy/unknown values. |
| `BigDecimal` | Precision, scale, rounding, and boundary values. |
| `Instant`/`OffsetDateTime` | UTC, offsets, precision, and session timezone. |
| Boolean | True/false, null, and database defaults. |
| JSON/JSONB | Serialization, query operators, and mapping back to domain objects. |
| SQL array | Empty array, multiple elements, null, and ordering. |
| BLOB/CLOB | Large payloads, stream lifecycle, and encoding. |
| Custom value object | Read/write converters, null, and compatibility with existing data. |

Not every application uses all of these types. Add test cases matching your actual schema and APIs.

## 9. Checking Nulls, Defaults, and Metadata

Driver changes can expose wrong assumptions about SQL NULLs, primitive mappings, default expressions, or column metadata.

Verify:

- Nullable columns read back as null in wrapper/reference types.
- `NOT NULL` columns do not receive null when an aggregate leaves a field uninitialized.
- Database defaults apply when columns are omitted from INSERT per mapping rules.
- Generated/default timestamps are not overwritten by application-bound nulls.
- Column labels/aliases in custom queries match `RowMapper` expectations.
- Code does not make brittle assumptions about precision, scale, column type, or generated key metadata.

With custom SQL, avoid `SELECT *` if mapping depends on ambiguous column names. Explicit column lists and aliases help tests catch schema changes early.

## 10. Testing Repository Queries and Custom SQL

Derived queries, `@Query`, and custom repositories can be affected by query generation, SQL dialects, or driver behavior.

A test suite should verify:

- Derived queries by ID, status, foreign key, and null conditions.
- `IN` with empty, single-element, and multi-element collections.
- `LIKE`/case sensitivity/escaping if business logic depends on it.
- Stable sorting with a tie-breaker.
- Pagination: page contents and count queries.
- `@Query` with named parameters and projections.
- Custom SQL joins, aggregate functions, CTEs, or database-specific syntax.
- Conditional updates/deletes and affected row counts.
- Batch operations if the application uses batching.
- Error behavior on unique/foreign key/check constraint violations.

Example pagination test with deterministic ordering:

```java
@Test
void paginationHasStableOrderingAndCorrectTotal() {
    PageRequest page = PageRequest.of(
        0, 2, Sort.by(Sort.Order.asc("createdAt"),
                      Sort.Order.asc("id"))
    );

    Page<PurchaseOrder> result = orders.findByStatus("CREATED", page);

    assertThat(result.getTotalElements()).isEqualTo(5);
    assertThat(result.getContent()).hasSize(2);
}
```

Fixtures should include multiple rows sharing the same `createdAt` to exercise the `id` tie-breaker. Never assert stable ordering if the query has no `ORDER BY`.
## 11. Testing Transactions, Rollback, and Isolation

A driver upgrade can affect how connections handle autocommit, savepoints, isolation, timeouts, or exceptions. Spring's transaction abstraction hides many details, yet applications still need to verify commit/rollback contracts.

### Verifying Multi-Operation Rollback

Suppose a use case saves an aggregate and then writes an audit record. If writing the audit fails, both changes must roll back when sharing the datasource and transaction manager:

```java
@Test
void auditFailureRollsBackOrderUpdate() {
    String originalStatus = orders.findById(orderId)
        .orElseThrow()
        .status();

    assertThatThrownBy(() ->
        workflow.confirmWithAuditFailure(orderId, actorId)
    ).isInstanceOf(DataAccessException.class);

    PurchaseOrder reloaded = orders.findById(orderId).orElseThrow();

    assertThat(reloaded.status()).isEqualTo(originalStatus);
    assertThat(audits.existsFor(orderId, "CONFIRMED")).isFalse();
}
```

The audit error must happen after the aggregate update. Reloading must observe state from a new transaction after the business transaction finishes. If the test framework wraps the test method in a transaction, manage test transactions explicitly (e.g., via `TransactionTemplate` or a full integration test) so you do not accidentally inspect uncommitted state inside the active transaction.

### Transaction Behaviors to Protect

- `@Transactional` on services spans repository calls.
- Runtime exceptions roll back under the default policy.
- Checked exceptions roll back when matching `rollbackFor` is configured.
- Swallowed exceptions inside a method do not cause tests to assume automatic rollback.
- Nested `REQUIRED` participates in the active transaction.
- `REQUIRES_NEW` commits independently as designed.
- Savepoints/nested transactions if used by the application and supported by the database/driver.
- Isolation levels and locking per concurrency requirements.
- Timeouts, cancellation, and connection release when queries fail.

Do not assume every database supports the same isolation levels, savepoints, or transaction features. Run tests on the real engine and driver used in production.

## 12. Testing Exception Translation and Database Errors

Spring JDBC translates `SQLException` into the `DataAccessException` hierarchy. A new driver can change `SQLState`, vendor error codes, or messages. That can affect exception translation and application logic if code couples too tightly to error messages.

Verify:

- Unique constraint violations map to the error category the application handles.
- Foreign key/check constraint violations are not misclassified as connectivity failures.
- Deadlock/serialization failures are classified appropriately for retries or error responses.
- Connection timeouts and query timeouts are distinguished.
- Connection resets/network failures do not mask uncertain write outcomes.
- Error mapping to external APIs preserves stable status/error codes per application contracts.

Prefer checking exception types and stable error codes (`SQLState`/vendor code) rather than matching full driver messages, because messages can change across versions or locales.

Example integration check for unique constraints:

```java
@Test
void duplicateBusinessKeyIsRejected() {
    orders.save(orderWithReference("PO-UNIQUE-01"));

    assertThatThrownBy(() ->
        orders.save(orderWithReference("PO-UNIQUE-01"))
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

If the application translates this into `DuplicateOrderReferenceException`, test the service/API boundary to verify that mapping too. Never let controllers depend on verbatim PostgreSQL/MySQL/SQL Server error strings.

## 13. Testing Auditing and Lifecycle Callbacks

Spring Data upgrades can affect when or how callbacks and auditing execute. If your application depends on these hooks, test the persisted database state:

- `@CreatedDate` is populated on insert.
- `@LastModifiedDate` updates according to configuration.
- `@CreatedBy` and `@LastModifiedBy` capture the right actor.
- `BeforeConvertCallback` transforms the instance used for persistence as contracted.
- `AfterSaveEvent` is not mistaken for transaction commit.
- Domain events are published only along persistence paths the application actually uses.
- Custom SQL/bulk operations are audited separately if they bypass the lifecycle pipeline.

Use a fixed clock for timestamp tests:

```java
@TestConfiguration
static class FixedClockConfiguration {

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2026-11-13T02:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Reload the row after saving to verify the database stored the audit value. Do not check only the input object or emitted event.

## 14. Testing Connections, Pools, and Driver Behavior

Some bugs appear only when connections are borrowed/returned from a pool or under concurrent load. Verify:

- Connections return to the pool after both success and exceptions.
- Connection leak detection reports no leaks under normal test workloads.
- Validation queries or `Connection.isValid(...)` work with the new driver.
- Connection lifetime, idle timeout, and max lifetime do not unexpectedly abort active queries.
- Session state such as timezone, schema/`search_path`, isolation, and role is reset or managed explicitly.
- Prepared statement caches do not break across schema changes.
- Batch inserts/updates return update counts matching the semantics your application relies on.
- Fetch size/streaming results do not hold connections open longer than expected.
- LOBs/streams are closed properly and never read after returning the connection to the pool.
- TLS, certificate validation, and authentication plugins are compatible with the new driver.

If using a routing `DataSource`, test tenant/primary/replica routing with real physical connections. A unit test on `determineCurrentLookupKey()` will not catch a repository accidentally using a different datasource or acquiring a physical connection before the routing context is initialized.
## 15. Testing Migrations from the Running Schema

Framework/driver upgrades often coincide with schema changes. Test migrations independently from creating a fresh database from the latest schema.

A migration regression test should:

1. Initialize the database at the nearest production schema version.
2. Seed a fixture dataset representing legacy data.
3. Run all pending migrations in exact order.
4. Confirm the new schema version is recorded.
5. Verify legacy data is neither lost nor unexpectedly altered.
6. Run repository reads/writes using the new application version.
7. Verify constraints, indexes, defaults, sequences, and views after migration.

Creating an empty database from the latest schema fails to catch errors when upgrading data from an older schema. Keep a sanitized fixture/schema snapshot or a seed script reflecting older data structures.

### Checking Expand-and-Contract for Rolling Deployments

When deploying multiple instances, old and new versions may run concurrently during rollout. Migrations should remain compatible with both during the transition:

- **Expand:** add new columns/tables/indexes so the old version keeps working.
- Deploy new code capable of reading/writing the new structure while remaining compatible with old code where needed.
- Backfill data in batches and verify outcomes.
- Switch traffic/behavior to the new structure.
- **Contract:** drop old columns/tables only after no running instance or job depends on them.

For example, when renaming `customer_name` to `display_name`, do not drop the old column in the same migration before running code switches to the new column. Add the new column, dual-write or backfill per your chosen strategy, deploy compatible code, and drop the old column in a later release.

Not all migrations support full transactions. Some databases have non-transactional DDL or locking constraints. Test migrations on the target engine and observe execution time, locks, log volume, and recovery behavior on failure.

## 16. Checking Data Compatibility After Migration

Beyond migration completion, verify data invariants:

- Before/after row counts across critical tables.
- No orphan child rows.
- Valid foreign key and unique constraints.
- Proper migration of null/default values.
- No precision loss in decimals.
- Timestamps preserve exact instants or local time rules.
- Legacy enum/string codes remain interpretable.
- Sequences/identities continue generating IDs without colliding with existing data.
- Indexes and views exist with intended definitions.
- Per-tenant or per-partition row counts remain as expected.

Example orphan check:

```sql
SELECT line.order_id
FROM order_line line
LEFT JOIN purchase_order po ON po.id = line.order_id
WHERE po.id IS NULL;
```

This query must return zero rows if the model requires every line to belong to an existing order. In shared-schema multi-tenancy, joins and constraints must include the tenant key if IDs are unique only per tenant.

If a migration transforms data, check aggregate totals before and after as well. Sums by currency, counts by status, or min/max timestamps can catch subtle corruption that row counts alone miss.

## 17. Performance and Query Plan Testing

An upgrade may preserve functional results while increasing query counts, altering generated SQL, or degrading driver/pool behavior. Pick a representative workload:

- Loading aggregate roots with child collections.
- Saving aggregates with many children.
- Common derived queries and pagination.
- Custom SQL joins/reports.
- Batch inserts/updates, if used.
- Queries binding large collections.
- Long-running transactions holding connections.
- Concurrent workload through the connection pool.

Track:

| Metric | Meaning |
| --- | --- |
| Query count | Detects N+1 queries or increased SQL statement counts. |
| Latency p50/p95/p99 | Identifies median and tail latency regressions. |
| Throughput | Requests/transactions processed per second. |
| Connection acquisition time | Detects pool exhaustion or connection wait spikes. |
| Active/idle connections | Reflects load and pool sizing. |
| Lock wait/deadlocks | Detects concurrency or transaction duration shifts. |
| Rows examined / query plan | Identifies unused indexes or plan shifts. |
| Allocation/heap/CPU | Detects higher mapping or serialization overhead. |

Compare on the same dataset, database version, hardware/container limits, pool settings, and concurrency. Do not compare a small local run against a production benchmark and declare a regression.

Query plans can shift due to statistics, database versions, or data distributions rather than Spring Data itself. Capture plans for critical queries before and after upgrading; when a plan changes, inspect indexes, bind parameter types, cardinality estimates, and statistics.

### Setting Regression Thresholds

Do not apply a single latency threshold across all queries. Define SLOs per use case and specify maximum acceptable degradation. A 20% p95 increase that stays well within SLO and adds negligible resource cost leads to a different decision than p99 breaching SLO or pool saturation.

Run multiple iterations and report medians/percentiles; exclude startup, warm-up, and cold-cache effects when comparing.

## 18. Building a Version Test Matrix

You do not need to test every theoretically possible combination. Select vendor-supported combinations sufficient to isolate changes.

Example matrix:

| Run | Spring Data/Boot | JDBC driver | Database | Goal |
| --- | --- | --- | --- | --- |
| Baseline | Current | Current | Current | Confirm baseline tests and behavior. |
| Framework only | Target | Current | Unchanged | Isolate framework changes. |
| Driver only | Current | Target | Unchanged | Isolate driver changes. |
| Combined target | Target | Target | Unchanged | Verify intended deployment combination. |
| Database target | Target | Compatible target | Target | Verify database server upgrade separately. |

If a combination falls outside the vendor compatibility matrix, do not treat it as proof of support. Boot/Framework may need upgrading together due to dependency management constraints.

### Inspecting the Dependency Tree

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-data-jdbc \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency <jdbc-driver-artifact> \
  --configuration runtimeClasspath
```

With Maven:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-jdbc
mvn dependency:tree -Dincludes=<driver-group-id>:<driver-artifact-id>
```

Verify runtime actually uses the intended driver version rather than checking only the declared version. Transitive dependencies may select a different version via conflict resolution or BOMs.

## 19. Controlled Upgrade and Release Process

A practical process can be organized into stages:

1. **Inventory:** record dependencies, database, driver, Java runtime, schema, and custom integrations.
2. **Baseline:** run the current test suite against a production-like database/driver; save results and performance metrics.
3. **Isolated upgrades:** upgrade framework and driver in steps that separate root causes; keep the database fixed on the initial pass if possible.
4. **Compile and static checks:** address API deprecations/removals, dependency conflicts, and changed configuration.
5. **Repository integration:** run aggregate, converter, query, generated key, and lifecycle tests.
6. **Transaction/error tests:** run rollback, locking, exception translation, and pool tests.
7. **Migration tests:** upgrade a database from the old schema with representative data fixtures.
8. **Performance tests:** compare query counts, latency, pool metrics, and query plans.
9. **Staging:** run in a production-like setup including TLS, secrets, networking, and database permissions.
10. **Canary:** route a fraction of traffic, monitoring error rates, latency, pool health, deadlocks, and data correctness.
11. **Rollout:** expand traffic once signals stay within defined thresholds.
12. **Rollback/forward fix:** execute the pre-prepared schema- and dependency-compatible recovery plan.

Never treat compile success or application startup success as sufficient. Many mapping and SQL errors surface only during actual database operations.
## 20. Preparing Rollback and Backward Compatibility

Rolling back an application after a dependency upgrade is not always safe. If a migration dropped columns or changed data semantics, the old application version may fail to read the new schema.

Before deploying, determine:

- Can we revert to the old binary/dependencies without restoring the database?
- Is the migration compatible with both old and new code during rolling deployment?
- Are there any irreversible data transformations?
- Does the new driver write formats readable by the old driver?
- Were enums, JSON shapes, timestamp precisions, or encodings altered?
- Can new features be toggled off via feature flags without rolling back the schema?
- If a forward fix is needed, is a safe follow-up migration ready?

### Do Not Assume Dependency Downgrades Reverse Written Data

For instance, the new version writes a new enum value to the database. If rolling back to the old version fails to recognize that value, old code may crash reading those rows. Likewise, changing JSON structures or timestamp precision can cause old code to misinterpret written data.

When rapid application rollback is required, preserve backward-compatible data formats during the transition window. Start writing new formats only once all running instances can read them, or use versioned payloads and an appropriate migration strategy.

Dependency rollback and schema rollback are two separate plans. An already executed migration may require a forward migration rather than an automated downgrade.

## 21. Ordering the CI Pipeline for Upgrades

A pipeline can progress from fast checks to slow checks:

1. Resolve dependencies and verify dependency convergence.
2. Compile main/test sources and check for API deprecations/removals.
3. Run domain/converter unit tests.
4. Start the exact target database container engine/version.
5. Apply migrations from the previous schema.
6. Run repository integration tests.
7. Run transaction, locking, and lifecycle tests.
8. Run custom SQL and driver type tests.
9. Run API/contract tests.
10. Run performance smoke tests on critical queries.
11. Archive test reports, dependency trees, database versions, and driver metadata.

You do not need to run long benchmarks on every pull request if cost is high. Run core regression tests on every change, and run extended concurrency/performance workloads nightly or on release candidates. Before releasing, however, require results from the full mandatory suite.

### Record Environment Metadata in Test Reports

Each run should record:

- Application commit.
- Java runtime version.
- Spring Boot, Spring Framework, and Spring Data JDBC versions.
- JDBC driver name/version.
- Database product/version.
- Connection pool name/version and key settings.
- Migration/schema version.
- JVM timezone and database session timezone.
- Test suite, duration, and results.

When a test fails only in CI or staging, this metadata distinguishes environmental differences from real regressions.

## 22. Monitoring After Upgrading

After canary and rollout, monitor signals that may indicate persistence defects:

| Signal | What to watch for |
| --- | --- |
| Error rate by `SQLState`/vendor code | Spikes in constraint, syntax, connection, or serialization errors. |
| Repository/service exception rate | Unusual increases in `DataAccessException` or optimistic locking failures. |
| Query latency p95/p99 | Slower queries or tail latency spikes. |
| Connection pool pending/active | Pool exhaustion, rising acquisition times, or leaks. |
| Deadlocks/lock waits | Shifts in transaction duration or lock ordering. |
| Generated ID / sequence metrics | Anomalous IDs or duplicate key errors. |
| Migration status | Instances running against inconsistent schema versions. |
| Data invariants | Orphan rows, unexpected nulls, wrong counts/aggregate totals. |
| Replica lag | Read replicas lagging and impacting read-your-writes. |

Do not log full parameters containing sensitive information just to debug a driver. Prefer `SQLState`, operation name, query identifier, correlation ID, and sanitized metadata.

You can add a canary check reading/writing a technical record in a dedicated schema, but do not let health checks continuously write into business tables or generate substantial load. Health checks must also verify the proper datasource route if using multi-tenant or primary/replica routing.

## 23. Example Checklist for an Upgrade

A release checklist can record concrete evidence instead of merely ticking “tested”:

| Item | Evidence to retain |
| --- | --- |
| Dependency alignment | Dependency tree/runtime driver version. |
| Database compatibility | Database image/version and repository suite results. |
| Aggregate mapping | Test report for insert/load/update/delete of root + children. |
| Type mapping | Round-trip tests for all types actually in use. |
| Transactions | Commit/rollback, optimistic locking, and isolation tests. |
| Query behavior | Derived queries, `@Query`, custom SQL, count, and pagination tests. |
| Lifecycle/auditing | Callbacks, events, created/modified timestamps, and actor tests. |
| Migration | Upgrade test from old schema with fixtures; data invariant report. |
| Performance | Baseline/target query counts, latency, pool metrics, and query plans. |
| Rollback | Rehearsed old-binary rollback or forward-fix scenario. |
| Staging/canary | Error rate, `SQLState`, latency, pool health, and data invariants. |

Mark an item complete only when backed by traceable test reports, logs, or artifacts. If a database/driver variant is absent from the test environment, state that gap explicitly instead of extrapolating from another engine.

## 24. Self-Check Questions

- Why does successful compilation not prove a new Spring Data JDBC and driver version are compatible with the application?
- Which components can change during a persistence upgrade?
- Why separate baseline, framework-only, driver-only, and combined target runs?
- When should a real database engine be used instead of H2?
- Which tests protect aggregate roots and child collections?
- Why do generated IDs and optimistic locking need integration tests?
- Which data types and metadata can a driver upgrade affect?
- Why verify SQL NULLs, defaults, and column aliases?
- How do you prove multiple repository operations roll back together?
- Why avoid depending on verbatim `SQLException` messages?
- How do you verify auditing and lifecycle callbacks after an upgrade?
- Why must migration tests start from an older schema populated with data?
- How does expand-and-contract make rolling deployments safer?
- Which metrics can reveal performance regressions?
- When might rolling back an old binary be incompatible with the new schema/data?
- What evidence should be retained in a release report?

Regression testing when upgrading Spring Data or a JDBC driver must rest on the persistence contracts your application actually uses. Isolate framework, driver, and database changes to pinpoint root causes; run integration tests against the real database engine; verify aggregates, generated IDs, converters, queries, transactions, lifecycles, and migrations; then compare performance and monitor canary rollouts. Prepare application rollback alongside schema compatibility upfront, because dependency downgrades do not automatically revert written data.
