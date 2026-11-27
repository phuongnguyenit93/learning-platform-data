# Minimal Reproduction Workflow Using SQL Logs and Integration Tests

When a Spring Data JDBC query behaves unexpectedly, the root cause can originate across many layers: property names in derived queries, dialect-generated SQL, parameter binding, ResultSet mapping, aggregate relationships, transactions, schema migrations, or the JDBC driver. Looking at the final exception alone is rarely enough to pinpoint the failing layer.

A reliable reproduction should capture:

1. **Environment details:** versions of Spring Data JDBC, Spring Framework/Spring Boot, JDBC driver, database, and dialect.
2. **Actual SQL:** executed statements, statement ordering, and parameter values needed to reproduce.
3. **Minimal data:** only the table rows necessary to trigger the failure.
4. **Transaction context:** which method opens the transaction, isolation level, rollback/commit state, and preceding operations.
5. **Integration test:** an isolated test running on the matching database engine that asserts both the failure and expected outcome.

The goal is to distill an elusive application bug into a small, repeatable test case. While the test fails, it serves as proof of the broken query, mapping, or transaction; once fixed, it becomes a regression test preventing the bug from returning.

## 1. Define the Exact Symptom Before Enabling Logs

Before changing logging configuration, record the exact observable behavior:

- Which repository method was invoked?
- Which inputs/parameters trigger the failure?
- Does it fail for all data or only specific records?
- Does it occur on SELECT, INSERT, UPDATE, or DELETE?
- Is the exception a Spring DataAccessException, MappingException, OptimisticLockingFailureException, or SQLException?
- Does it fail immediately on statement execution or only at commit?
- Is there an active transaction or autocommit?
- Are there differences between local, CI, and production?

Insufficiently specific description:

> Repository query fails.

Reproducible description:

> Calling findByStatusAndCreatedAtAfter("PAID", 2026-01-01T00:00) on PostgreSQL returns SQLState 42703 because the SQL references column createdAt. The error started appearing after migration V18; H2 tests still pass.

The second description narrows down the method, inputs, database, SQLState, and schema change timing.

## 2. Collect Versions and Database Metadata

Identical code can emit different SQL or bind types across dialects and drivers. Record at minimum:

| Information | Example |
|---|---|
| Spring Boot | Active version |
| Spring Framework | Version resolved by dependency management |
| Spring Data Relational/JDBC | Actual version |
| JDBC driver | PostgreSQL/MySQL/SQL Server driver and version |
| Database product | PostgreSQL, MySQL, Oracle, SQL Server... |
| Database version | Major/minor version |
| Dialect | JdbcDialect resolved by Spring Data JDBC |
| Schema version | Latest applied Flyway/Liquibase migration |
| Transaction isolation | READ_COMMITTED, REPEATABLE_READ... |
| Connection pool | HikariCP or other pool |
| SQL mode/collation/timezone | Whenever relevant to the failure |

Do not record only the JDBC URL. A URL may route through a proxy or different endpoint; verify the actual database product and version the connection reaches.

### Reading metadata via JdbcTemplate

~~~java
@Component
public class DatabaseDiagnostics {

    private final JdbcTemplate jdbcTemplate;

    public DatabaseDiagnostics(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void logMetadata() {
        jdbcTemplate.execute((ConnectionCallback<Void>) connection -> {
            DatabaseMetaData metadata = connection.getMetaData();

            log.info("Database product: {}", metadata.getDatabaseProductName());
            log.info("Database version: {}", metadata.getDatabaseProductVersion());
            log.info("JDBC driver: {}", metadata.getDriverName());
            log.info("JDBC driver version: {}", metadata.getDriverVersion());

            return null;
        });
    }
}
~~~

This is diagnostic code. Never log passwords, tokens, or full JDBC URLs if they contain credentials. Log only necessary metadata.

You can inject JdbcDialect to verify which dialect Spring Data JDBC selected:

~~~java
@Component
public class DialectDiagnostics {

    public DialectDiagnostics(JdbcDialect dialect) {
        log.info("Spring Data JDBC dialect: {}", dialect.getName());
    }
}
~~~

## 3. Enable Spring JDBC SQL Logging

Spring Data JDBC relies on Spring JDBC infrastructure to execute statements. Therefore, to inspect executed SQL, enable logging for the Spring JDBC package.

In application.yaml:

~~~yaml
logging:
  level:
    org.springframework.jdbc: DEBUG
~~~

Or in application.properties:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

Spring Data JDBC documentation recommends setting DEBUG on org.springframework.jdbc to inspect statements executed by NamedParameterJdbcTemplate/JdbcTemplate. Spring Data JDBC itself logs very little SQL directly; statement execution lives in Spring JDBC.

Once enabled, examine log entries around the failing request or test. Record:

- SQL statements.
- Ordering of SELECT/INSERT/UPDATE/DELETE.
- How many times the same query executes.
- Which statement immediately precedes the exception.
- Transaction begin/commit/rollback events if transaction logging is enabled.

### When bind parameter values are needed

SQL logs do not always display full parameter values. When you need exact bound values:

- Use datasource-proxy or P6Spy in local/test environments.
- Or instrument the JDBC layer to capture statements and parameters in a controlled manner.
- If enabling verbose binding loggers, turn them on only during investigation and sanitize output before sharing.

Never place personal data, access tokens, passwords, sensitive emails, or confidential payloads in logs. Mask values or substitute dummy fixtures preserving the offending data types and lengths.

Configuration for datasource-proxy/P6Spy must match your dependencies and application version; never install extra logging tools in production solely to diagnose a short-lived bug without evaluating overhead and data exposure risks.

## 4. Read SQL Logs Sequentially, Not Just the Final Statement

Loading a single aggregate can trigger multiple statements. For example:

~~~text
1. SELECT purchase_order WHERE id = ?
2. SELECT order_line WHERE order_id = ?
3. SELECT line_note WHERE order_line_id IN (...)
~~~

If the third statement fails, the initial root SELECT may be completely fine. Pinpoint whether the issue lies in:

- Incorrectly generated SQL.
- Wrong parameter bind type or value.
- Table/column names mismatching the schema.
- A collection query generated from unexpected mapping metadata.
- Database constraints or permissions.
- ResultSet failing to map into constructors/properties.
- A transaction already marked rollback-only earlier.

Number statements chronologically and correlate them with a request or test ID to verify they belong to the same execution.

### Distinguishing SQL errors from mapping errors

| Symptom | Layer to inspect |
|---|---|
| SQLSyntaxErrorException, undefined column/table | SQL, schema, dialect, naming strategy |
| ConstraintViolationException/DataIntegrityViolationException | Data, FK, unique/check constraints |
| ConversionFailedException/MappingException | JDBC types, converters, constructor/property mappings |
| IncorrectResultSizeDataAccessException | Method expects single result, yet SQL returns multiple rows |
| EmptyResultDataAccessException | Caller requires one row, yet no rows returned |
| OptimisticLockingFailureException | Stale version or update/delete no longer matches |
| TransactionSystemException on commit | Error triggered during commit/rollback |
| QueryTimeoutException | Query/statement timeout or slow database |

Do not jump straight to patching the final exception message. Locate the first SQL statement or operation that introduced the broken state.

## 5. Run the SQL Independently Against the Database

Once you have the SQL and parameters, turn them into a standalone statement you can run in a database client.

Example from logs:

~~~sql
SELECT id, status, created_at
FROM purchase_order
WHERE status = ?
  AND created_at > ?
ORDER BY created_at DESC, id DESC;
~~~

Bound parameters:

~~~text
1 = "PAID" (VARCHAR)
2 = 2026-01-01T00:00:00 (TIMESTAMP)
~~~

Running standalone:

~~~sql
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'PAID'
  AND created_at > TIMESTAMP '2026-01-01 00:00:00'
ORDER BY created_at DESC, id DESC;
~~~

Match all conditions accurately:

- Database engine/version.
- Schema and search_path.
- User/permissions.
- Parameter types (VARCHAR, BIGINT, TIMESTAMP, UUID...).
- Timezone and collation where relevant.
- Transaction isolation if concurrency is involved.
- Corresponding fixture data.

If the SQL fails standalone, investigate the SQL, schema, or database. If the SQL succeeds standalone yet fails in Spring Data JDBC, focus on bind types, mapping, transaction context, connection/session state, or query ordering.

Never copy sensitive parameters from production logs into tickets or test fixtures. Construct synthetic data sharing the same types and edge-case characteristics.

## 6. Shrink the Dataset for a Minimal Reproduction

A minimal reproduction should contain at least:

- One relevant entity/aggregate root.
- Only the tables truly required by the query.
- Just enough fixture rows to trigger the failure.
- One repository method or service method.
- One self-contained test reproducing the bug.
- Necessary schema/migrations.
- Explicit dependency and database versions.

For example, if loading an order with a collection fails:

~~~text
purchase_order
  id = 100
  status = PAID

order_line
  id = 1, order_id = 100
  id = 2, order_id = 100
~~~

There is no need to import millions of production rows when two child rows reproduce the issue. However, if the failure only happens with duplicates, NULLs, Unicode strings, timezone-aware timestamps, or specific cardinalities, the fixture must preserve that condition.

### Preserve the triggering condition

When trimming down data, do not accidentally strip out:

- Nullable columns or NULL values.
- Duplicate business keys.
- A root with 0 children vs. a root with multiple children.
- Column names colliding with SQL reserved words.
- UUID/JSON/array/vendor-specific types.
- Decimal precision/scale.
- Timestamps with timezones/offsets.
- Stale versions or concurrent updates.
- Open transactions and repository call ordering.

A minimal reproduction does not mean the fewest rows at all costs; it means the smallest dataset that still triggers the bug reliably.

## 7. Create an Integration Test with @DataJdbcTest

@DataJdbcTest is suited for testing Spring Data JDBC repositories and mappings. In Spring Boot, this test slice configures DataSource, JdbcTemplate, Spring Data JDBC repositories, and test transactions. By default, tests roll back upon completion.

Example:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryReproductionTest {

    @Autowired PurchaseOrderRepository repository;
    @Autowired JdbcTemplate jdbcTemplate;

    @BeforeEach
    void setUp() {
        jdbcTemplate.update("""
                INSERT INTO purchase_order(id, customer_id, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                100L,
                10L,
                "PAID",
                Timestamp.valueOf("2026-01-10 09:00:00")
        );
    }

    @Test
    void reproducesTheUnexpectedResult() {
        List<PurchaseOrder> result = repository.findByStatus("PAID");

        assertThat(result)
                .extracting(PurchaseOrder::getId)
                .containsExactly(100L);
    }
}
~~~

This test illustrates isolating a repository query. If the bug depends on migrations/schemas, let the test run migrations or supply matching schema SQL. If it depends on custom converters or RowMappers, import the relevant configuration using @Import.

### Load only what the test needs

Test slices exclude web servers, controllers, and unrelated beans. If the bug lives strictly in repository mapping, there is no need to boot the full application context.

Use @SpringBootTest when reproduction requires:

- Application services and transaction proxies.
- Multiple collaborating repositories.
- Custom application configuration not loaded by the slice.
- Transaction manager or multi-DataSource wiring.
- A use case spanning multiple layers.

Do not mock repositories or JdbcTemplate to reproduce real SQL failures. Mocks are useful for unit-testing logic, but they never exercise SQL syntax, JDBC binding, database constraints, dialects, or ResultSet mapping.

## 8. Reproducing Transaction and Rollback Bugs

If a failure involves multiple operations needing to commit or roll back together, invoke the Spring service through its proxy and verify database state after the transaction finishes.

Service:

~~~java
@Service
public class OrderWorkflow {

    private final PurchaseOrderRepository repository;
    private final JdbcTemplate jdbcTemplate;

    public OrderWorkflow(
            PurchaseOrderRepository repository,
            JdbcTemplate jdbcTemplate) {
        this.repository = repository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void createOrderThenFail(PurchaseOrder order) {
        PurchaseOrder saved = repository.save(order);

        jdbcTemplate.update("""
                INSERT INTO order_audit(order_id, event_type)
                VALUES (?, ?)
                """,
                saved.getId(),
                "CREATED"
        );

        throw new IllegalStateException("Reproduction failure");
    }
}
~~~

Integration test:

~~~java
@SpringBootTest
class OrderWorkflowTransactionReproductionTest {

    @Autowired OrderWorkflow workflow;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackAllWritesAfterFailure() {
        assertThatThrownBy(() ->
                workflow.createOrderThenFail(
                        new PurchaseOrder(10L, "DRAFT", LocalDateTime.now())
                )
        ).isInstanceOf(IllegalStateException.class);

        Integer orderCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM purchase_order WHERE customer_id = ?",
                Integer.class,
                10L
        );

        Integer auditCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM order_audit WHERE event_type = ?",
                Integer.class,
                "CREATED"
        );

        assertThat(orderCount).isZero();
        assertThat(auditCount).isZero();
    }
}
~~~

This illustrative test needs matching schemas, constructors, and fixtures. Crucially, the test itself does not open an outer transaction that hides the service's commit/rollback outcome. Invoke the service bean through the Spring proxy so the service transaction finishes before assertions inspect the database.

If the test method itself carries @Transactional, assertions may run inside an outer test transaction; manage test transactions explicitly when verifying actual commit/rollback behavior.

## 9. Use Testcontainers When Failures Depend on Database or Driver

H2 is not a drop-in substitute for PostgreSQL, MySQL, SQL Server, or Oracle. Engines differ in:

- SQL syntax and dialects.
- Generated keys, identity columns, and sequences.
- UUID, JSON, array, and timestamp binding.
- Case sensitivity and identifier quoting.
- Unique, FK, and check constraints.
- Locking, isolation, and transaction semantics.
- Window functions and execution plans.

When a bug reproduces only on the production database, use Testcontainers to run the matching engine and JDBC driver in integration tests.

PostgreSQL example:

~~~java
@Testcontainers
@SpringBootTest
class PurchaseOrderPostgresReproductionTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("sales")
                    .withUsername("app")
                    .withPassword("secret");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add(
                "spring.datasource.driver-class-name",
                postgres::getDriverClassName
        );
    }
}
~~~

Apply the application's schema/migrations to the container before running tests. If the bug depends on database version, pin the container image to the matching major/minor version; avoid floating tags when seeking stable reproductions.

Testcontainers lets you test against a real database in automation, but it will not synthesize production-like data automatically. Fixtures must still include the triggering conditions.

## 10. Analyzing Execution Plans for Slow Queries

When a query is functionally correct yet slow, capture the execution plan on the same database with representative parameters.

PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Inspect:

- Estimated rows vs. actual rows.
- Sequential scans vs. index scans.
- Join order and join algorithms.
- Whether sorts spill to disk.
- Buffer hits and reads.
- Time spent per plan node.
- How many rows filters discard.

EXPLAIN ANALYZE actually executes the query. Be careful with write statements; wrap them in rolled-back transactions or restrict analysis to SELECT statements as appropriate. In production, analyze plans conservatively with appropriate privileges.

If a query is slow only for certain parameters, compare selectivity and plans against fast parameters. Do not add an index blindly just because one query is slow; evaluate predicates, sort order, and write workload first.

## 11. Recording the Exception Chain and SQLState

Spring JDBC translates SQLException into the DataAccessException hierarchy. The outermost exception indicates the Spring-level failure category; the SQLException cause provides SQLState and vendor error codes.

When logging errors, record:

- Outermost exception class.
- Cause chain.
- SQLState if available.
- Vendor error code.
- Repository/service method.
- Request/test ID.
- Database product/version and driver version.
- Transaction boundary and rollback status.

Example service/logging handling:

~~~java
try {
    repository.findByStatus("PAID");
} catch (DataAccessException ex) {
    log.error("Database operation failed", ex);
    throw ex;
}
~~~

Do not catch DataAccessException and return an empty list or default value if doing so hides data errors. Preserve the exception and sufficient investigative context.

If failures occur only at commit time, inspect exceptions from the transaction manager as well. Some deadlock or serialization errors are reported by the database at transaction end rather than on the first statement.

## 12. Verifying Mappings and Schema

If standalone SQL succeeds yet repository mapping fails, compare the ResultSet against entity metadata:

- Do column names match @Column/NamingStrategy?
- Does the entity constructor accept all required columns?
- Does the returned JDBC type have a matching converter?
- Do embedded properties have the expected alias prefixes?
- Do collections have matching FK and key columns?
- Does the version property have a matching column and valid value?
- Does custom SQL return all columns expected by the default RowMapper?

For @Query returning an aggregate root, columns used in the constructor must be present. Properties populated via fields, setters, or withers remain unset if omitted from the query. For one-to-one/embedded properties, aliases must follow mapping rules; collection entities are loaded via separate queries.

If using a custom RowMapper or ResultSetExtractor, unit-test the mapper with a sample ResultSet if possible, then run integration tests to confirm the JDBC driver returns the expected types.

## 13. Keeping Logs Safe and Shareable

SQL logs may contain user or business data. Before sharing logs with others:

- Mask emails, phones, addresses, tokens, passwords, and personal data.
- Replace production IDs with synthetic IDs while keeping relationships intact.
- Never share JDBC URLs containing credentials.
- Strip internal connection details that are not needed.
- Retain SQLState, vendor codes, table/column names, and data types needed for diagnosis.
- Retain timestamps/offsets when timezones are implicated.
- Explicitly note which parameters were masked or replaced with fixtures.

Do not leave TRACE logging or parameter value logging enabled long-term in production without log protection policies.

## 14. Minimal Reproduction Report Template

When packaging a reproduction for another team or an issue report, use this structure:

~~~text
Title:
One-sentence summary of the incorrect behavior.

Environment:
- Spring Boot:
- Spring Framework:
- Spring Data Relational:
- JDBC driver:
- Database product/version:
- Dialect:
- Schema migration:
- Transaction isolation:

Expected:
The expected correct outcome.

Actual:
The actual outcome or exception.

Repository/service method:
Method name and minimal inputs.

SQL:
Actual logged statements.

Parameters:
Names, masked dummy values, and JDBC types.

Fixture:
DDL and minimal rows to reproduce.

Transaction:
Present/absent, boundary, commit/rollback.

Reproduction:
Command to run the single integration test.

Failure:
Assertion/exception and SQLState/vendor code.

Notes:
Differences between local and production databases.
~~~

A good reproduction does not require the entire application source code. It only needs the schema, fixture, dependency/database versions, SQL, and a single runnable test that exhibits the same bug.

## 15. End-to-End Reproduction Workflow

1. **Record symptoms:** method, inputs, exception, and timing.
2. **Capture environment:** framework, driver, database version, dialect, schema migration, and isolation.
3. **Enable SQL logging:** set org.springframework.jdbc=DEBUG; add datasource-proxy/P6Spy in tests if bind values or query counts are needed.
4. **Correlate entries:** tag request/test IDs and number statements in sequence.
5. **Classify the error:** SQL, binding, mapping, constraint, transaction, concurrency, or performance.
6. **Minimize fixtures:** keep the exact data, types, and relationships that trigger the bug.
7. **Run standalone SQL:** matching database, schema, parameter types, and transaction semantics.
8. **Write an integration test:** use @DataJdbcTest for repositories or @SpringBootTest for services/transactions.
9. **Use a real database if needed:** Testcontainers with the matching engine/driver/version.
10. **Keep the regression test:** assert the exact outcome or exception so the bug stays fixed.
11. **Document the report:** environment, SQL, masked parameters, fixture, test command, and expected/actual results.

### Quick Decision Table

| Symptom | First investigation step |
|---|---|
| SQL syntax/column/table error | Enable SQL logs, inspect DDL/dialect, and run SQL standalone |
| Empty or wrong row results | Capture parameters, fixture, and WHERE predicates |
| Mapping/conversion error | Compare ResultSet columns/types against entity/RowMapper |
| FK/unique/check failure | Reproduce with minimal fixture and record vendor error code |
| Optimistic locking failure | Record ID/version and update transaction ordering |
| Unexpected rollback behavior | Write service integration test and verify transaction manager/DataSource |
| Abnormal query count | Instrument statement counts and locate N+1 queries |
| Slow query | Check EXPLAIN/ANALYZE, rows, indexes, buffers, and parameter selectivity |
| Fails only on production DB | Run Testcontainers with the exact engine/driver/version |

**Core takeaway:** reproduce bugs by capturing real SQL and environment details, shrinking data while keeping triggering conditions intact, and locking down behavior with an integration test. SQL logs reveal what the framework actually executed; standalone SQL separates database bugs from Spring mapping/transaction bugs; Testcontainers validates behavior on the real engine. Always mask sensitive data and keep reproductions small, deterministic, and repeatable.

## Official References

- [Spring Data Relational — Getting Started: Logging](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html): logging SQL via Spring JDBC and the org.springframework.jdbc logger.
- [Spring Framework — JDBC Core Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JdbcTemplate, exception handling, and SQL logging.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): configuring logging.level per package/logger.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): @DataJdbcTest, @SpringBootTest, and test slices.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): running PostgreSQL in integration tests.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): analyzing execution plans and query performance.
