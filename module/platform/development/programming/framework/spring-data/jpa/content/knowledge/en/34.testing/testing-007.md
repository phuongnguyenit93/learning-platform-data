# Differences Between H2 and Production DBMSs and the Risk of Misleading Results

H2 is a lightweight Java database commonly used in Spring Data JPA tests because it starts quickly and can run in memory. However, a green test on H2 only proves the tested behavior in an H2 environment. It does not prove by itself that SQL statements, data types, transactions, concurrent locking, migrations, or performance will behave identically on PostgreSQL, MySQL, Oracle, or the deployed DBMS.

Risk arises when tests rely on H2 instead of a real database while the application depends on production-specific database behavior. H2 may accept SQL that the target database rejects, interpret data types differently, sort nulls differently, or fail to reproduce locks and isolation levels. The result is passing tests followed by failures after deployment.

The right approach is to use H2 for fast, clearly scoped tests while running critical integration tests on the exact same database engine and version as the deployment environment.

## 1. What Is H2 and Why Is It Used in Testing?

H2 is a relational database written in Java that can run embedded or in server mode. With Spring Boot, a common configuration is an in-memory database:

~~~properties
spring.datasource.url=jdbc:h2:mem:jpa-test
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
~~~

When using the URL `jdbc:h2:mem:jpa-test`, the database typically lives in JVM memory and is accessed across connections sharing that database name. When the database closes upon the last connection closing, data can disappear. Depending on configuration and how tests open connections, creating a fresh database or keeping it across connections can affect results.

H2 is useful because:

- It avoids installing a separate database server for each test run.
- It starts fast, making schema and test data creation easy.
- It fits many repository tests, entity mappings, relationships, and relatively portable JPQL queries.
- It integrates smoothly with `@DataJpaTest` and Spring Boot auto-configuration.

Yet H2 is its own database engine with its own SQL parser, data types, optimizer, transaction manager, and behaviors. Supporting syntax resembling another DBMS does not turn it into that DBMS.

## 2. Compatibility Mode Does Not Turn H2 Into PostgreSQL or MySQL

H2 offers syntax compatibility modes, for example:

~~~properties
spring.datasource.url=jdbc:h2:mem:jpa-test;MODE=PostgreSQL
~~~

Or:

~~~properties
spring.datasource.url=jdbc:h2:mem:jpa-test;MODE=MySQL
~~~

Compatibility modes help H2 accept or interpret certain syntax styles of the selected database. Support depends on the H2 version and does not cover the full semantics of the target DBMS.

For instance, `MODE=PostgreSQL` does not provide all PostgreSQL extensions, operators, data types, planner behavior, locking, isolation semantics, and catalog rules. Likewise, `MODE=MySQL` does not replicate all MySQL SQL modes, collations, InnoDB engine semantics, index behaviors, or MySQL-specific quirks.

Modes can reduce minor syntax friction in fast tests, but mode results must not be treated as proof of production equivalence. If a feature depends on PostgreSQL JSONB, `->>` operators, `ON CONFLICT`, extensions, or MySQL-specific functions, test it on the real engine.

## 3. Differences in SQL Dialects and Native Queries

Hibernate uses a dialect to translate parts of ORM operations into database-appropriate SQL. When tests run on H2, Hibernate emits SQL using the H2 dialect; when production runs PostgreSQL or MySQL, SQL is generated using the corresponding dialect.

JPQL is generally more portable than native SQL because it queries Java entities and properties rather than table names, column names, and database-specific syntax. Nevertheless, JPQL is still translated by the provider into SQL for the active engine. A JPQL query may work on H2 while hitting function, type, or translation differences on another database.

Native queries bind even more tightly to the database:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Query(value = """
        select *
          from product
         where lower(name) like lower(concat('%', :keyword, '%'))
        """, nativeQuery = true)
    List<Product> searchByName(@Param("keyword") String keyword);
}
~~~

This example uses relatively common syntax, yet you should not generalize that all native queries are portable. Common differences include:

- String, date/time, JSON, math, and type-casting functions.
- Pagination syntax, result limits, and window expressions.
- Upserts, returning clauses, conflict handling, and CTEs.
- Identifier quoting rules, schemas, table names, and column names.
- Row-locking syntax, hints, and stored procedures.
- Companion count queries for paginated native queries.

A native query running on H2 only proves H2's parser and engine accept it. If production uses vendor-specific SQL, run that exact query against a production-compatible database in integration tests.

## 4. Differences in Data Types and Comparison Rules

Java-to-SQL mappings are not always identical across engines. The same entity can be mapped by Hibernate to different column types depending on dialect and database version.

Areas prone to divergence:

| Data Category | Risk to Verify |
|---|---|
| Boolean | Database may store as `BOOLEAN`, `BIT`, numeric, or custom conventions |
| UUID | Storage as native UUID vs. string/binary may differ |
| Timestamp | Fractional second precision, timezones, and local/UTC conversion may differ |
| Numeric/Decimal | Precision, scale, rounding, and overflow |
| String | Length limits, Unicode, collation, and case-sensitive comparison |
| JSON | `JSON` vs. `JSONB`, validation, operators, and indexing depend on engine |
| Array/Enum | Native types and mapping behavior depend on database/provider |
| BLOB/CLOB | Drivers, streaming, size limits, and storage mechanisms |

For example, H2 may accept a column type or implicit conversion that the target database handles differently. A test checking only a simple save-and-read value can miss precision, timezone, encoding, or length limit bugs.

### Case Sensitivity, Collation, and Diacritics

String comparison rules depend on collation and database configuration. A query searching for `"admin"` can yield different matches against `"Admin"` across engines or collations. Accent-sensitive/insensitive comparisons, Unicode characters, and locale sorting can also vary.

Do not use H2 search or sort results to claim production produces the same order. If business logic relies on collation, configure and test with the real collation on the target database.

### NULLs and Sort Ordering

`NULL` ordering in `ORDER BY` can differ across engines or between default syntax and explicit clauses. A page sorted by date can order differently when multiple rows contain null values.

If business logic needs deterministic ordering, explicitly specify null ordering using portable JPA capabilities or an expression verified on the target engine. Also include a unique tie-breaker key in `ORDER BY` when paginating so tied rows do not shift positions across queries.

## 5. DDL, Constraints, Sequences, and Schema Generation

Spring Boot can let Hibernate generate test schemas via `ddl-auto=create` or `create-drop`. While convenient for mapping tests, Hibernate-generated schemas do not necessarily match schemas built by production migrations.

Differences to watch:

- Column types and lengths inferred from annotations.
- Index, constraint, and sequence names.
- Identity/auto-increment syntax and ID generation strategies.
- Unique constraints, foreign keys, check constraints, and violation behavior.
- Schemas, catalogs, quoted identifiers, and case-folding rules.
- Default values, generated columns, triggers, and stored procedures.

If production uses Flyway or Liquibase, a test running only `ddl-auto=create-drop` does not confirm production migrations will succeed on the target database. Migrations may contain vendor-specific DDL, custom index clauses, functions, or extensions unsupported by H2.

For migration tests, run migrations on the exact target database engine and version. Once migrations finish, inspect the schema and run representative read/write operations.

### Primary Key Generation Strategies

`GenerationType.IDENTITY`, sequences, and table generators behave differently. H2 can follow a different ID generation path than PostgreSQL or MySQL. A passing insert test on H2 does not prove production uses the right sequence, has sequence permissions, or matches allocation settings.

Verify:

- Whether `@GeneratedValue` and `@SequenceGenerator` annotations match the production schema.
- Sequence names, increments, and allocation sizes.
- ID values after insert and after `EntityManager` flush.
- Whether bulk data imports or concurrent inserts cause key collisions.

## 6. Transactions, Isolation, and Concurrent Locking

Transactions are one of the easiest places for H2 to create a false sense of security. Two engines can differ in MVCC implementation, lock granularity, lock acquisition timing, deadlock detection, timeouts, and concurrent transaction handling.

Features that must be tested on the target database when relied upon:

- `SELECT ... FOR UPDATE` and row-locking variants.
- Optimistic locking with `@Version`.
- Pessimistic locking via `@Lock`.
- Isolation levels such as `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`.
- Deadlocks, lock timeouts, and retries.
- Unique constraints when two transactions insert the same value concurrently.
- Concurrent updates and lost updates.
- `SKIP LOCKED` or `NOWAIT` if used by the application.

H2 supports some transaction and locking mechanisms, but detailed behavior does not mirror production engines. A single-threaded sequential test cannot prove code is safe under concurrent requests.

For example, checking inventory by reading quantity and then updating it can pass single-threaded tests while still overselling when two transactions run concurrently. Build integration tests with two independent transactions, synchronize read/write timing, and verify outcomes on a real database.

## 7. H2 and Risks for Pagination, Queries, and the Optimizer

H2 and production databases have different optimizers, statistics, index selection, and execution plans. A query running fast over a few dozen rows in H2 can crawl on a production table with millions of rows.

Risks include:

- N+1 queries masked by tiny test datasets.
- Indexes not used as anticipated.
- Query plans changing under different data distributions.
- Pagination lacking deterministic ordering.
- Native queries using engine-specific pagination syntax.
- Count queries not matching the data query.
- Joins, distinct, group by, and fetch strategies producing different plans.

H2 tests can check basic logical outputs, but do not replace inspecting `EXPLAIN` or `EXPLAIN ANALYZE` on a production-like engine and dataset. Never extrapolate production execution times from H2 timings.

## 8. Which Database Might @DataJpaTest Actually Be Using?

`@DataJpaTest` builds a JPA-focused test slice: entities, repositories, and related configuration. Spring Boot typically configures test transactions and rolls back after each test. When an embedded database like H2 is on the classpath, Spring Boot can automatically swap the configured datasource for the embedded database per auto-configuration policy.

This can mislead developers into thinking tests run against PostgreSQL or MySQL when they are actually running on H2.

Example repository test:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository productRepository;

    @Test
    void findsActiveProducts() {
        Product product = new Product("Keyboard", true);
        productRepository.save(product);

        List<Product> result = productRepository.findByActiveTrue();

        assertThat(result).contains(product);
    }
}
~~~

This test is helpful for checking basic repository behavior. Yet if it runs on H2, it does not verify native SQL, migrations, locking, or production data types.

If you want `@DataJpaTest` to use a datasource supplied by Testcontainers or an external test database configuration, disable embedded database replacement:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryPostgresTest {
    // Datasource configured to point at a PostgreSQL test instance
}
~~~

With `@SpringBootTest`, the application usually loads fuller datasource configuration and does not share the same datasource-replacement default as the JPA test slice. Whichever annotation you use, confirm the actual JDBC URL, driver, and engine before drawing conclusions.

### Test Transaction Rollback Can Also Mask Bugs

JPA slice tests normally run inside a transaction and roll back afterward. This is convenient for data isolation, yet can hide behaviors that only happen on commit:

- Constraints or write errors caught at flush/commit time.
- Transaction synchronization and after-commit callbacks.
- Nested or multi-transaction behavior.
- Data visibility from another connection after commit.

When verifying commits, flush explicitly and use appropriately designed transaction tests, or run service operations in separate transactions and inspect data from another transaction/connection. Do not merely check entities still sitting in the persistence context, as that does not guarantee database commit.

## 9. Testing on a Real Database With Testcontainers

Testcontainers spins up a real database inside a container for tests. For applications deploying on PostgreSQL, tests can run a PostgreSQL container matching the production major version and configuration.

Example with Spring Boot 3.1+ using `@ServiceConnection`:

~~~java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private ProductRepository productRepository;

    @Test
    void persistsAndQueriesOnPostgres() {
        Product product = new Product("Keyboard", true);
        productRepository.saveAndFlush(product);

        assertThat(productRepository.findByActiveTrue())
                .extracting(Product::getName)
                .contains("Keyboard");
    }
}
~~~

This is a test configuration example assuming the project declares the required test dependencies: Testcontainers JUnit Jupiter, PostgreSQL module, PostgreSQL JDBC driver, and Spring Boot Testcontainers. Manage dependency versions via your project's Spring Boot dependency management or Testcontainers BOM.

`@ServiceConnection` supplies container connection details to Spring Boot automatically. On older Spring Boot versions or without service connections, configure the datasource using `@DynamicPropertySource`.

Benefits of this approach:

- Tests run on real PostgreSQL, bringing parser, dialect, data types, and many transaction behaviors much closer to production.
- Real migrations can run at Spring startup.
- Vendor-specific native queries and functions are exercised.
- Realistic concurrency and constraint tests can be written.
- Database containers can be freshly provisioned per suite or managed per CI configuration.

Containers can still differ from production if versions, extensions, collations, timezones, server settings, or data volumes differ. Match critical versions and settings, not just the engine name.

## 10. Building a Layered Test Strategy

Not every test needs to run against a real database. You can layer tests by cost and database dependency:

| Test Type | Appropriate Database | Goal |
|---|---|---|
| Service unit tests | Mocks/fakes where appropriate | Database-independent business rules |
| Fast repository tests | H2 or real database | Mappings and portable queries |
| Native query tests | Production-compatible database | Verify engine-specific syntax and results |
| Migration tests | Production-compatible database | Prove migrations execute cleanly |
| Transaction/locking tests | Production-compatible database | Verify commits, rollbacks, and contention |
| Performance tests | Production-like database | Measure execution plans and real timings |

A practical CI pipeline might run:

1. Fast unit tests on every change.
2. H2 JPA tests for mappings and portable queries if speed provides value.
3. Testcontainers integration tests for native queries, migrations, locking, and critical transactions.
4. A dedicated performance/regression suite on an environment resembling production.

If container overhead is acceptable, you can run all repository integration tests on the real database and reduce reliance on H2. This choice depends on CI budgets and how heavily the application uses database-specific features.

## 11. Checklist for Investigating When H2 Passes but Production Fails

When a test passes on H2 but fails in production, inspect in order:

1. Which engine did the test actually use? Check JDBC URL, driver, Spring profile, and datasource startup logs.
2. Which dialect is Hibernate using? Confirm whether the auto-detected or configured dialect fits the real database.
3. Is the failing query JPQL, a derived query, Criteria, or native SQL?
4. Are there differences in data types, precision, timezones, collations, or null ordering?
5. Was the test schema generated by Hibernate or by Flyway/Liquibase migrations?
6. Are sequences, identities, triggers, extensions, or engine-specific functions involved?
7. Do any tests depend on isolation levels, row locks, deadlocks, or concurrency?
8. Did tests roll back before committing, or only read entities from the persistence context?
9. Was test data large and diverse enough to expose pagination, index, or query plan issues?
10. Does an integration test on the exact engine/version reproduce the bug?

Once the discrepancy is found, add a regression test running on a production-compatible database to prevent recurrence. H2 tests can stay if they still deliver fast feedback on portable behaviors.

## 12. Assumptions That Commonly Produce Misleading Results

| Assumption | Reality |
|---|---|
| H2 in PostgreSQL mode equals PostgreSQL | Mode only covers partial syntax differences; the engine is still H2 |
| Passing repository tests prove production native SQL is valid | Queries must run on the target database |
| `ddl-auto=create-drop` proves production migrations work | Flyway/Liquibase must run on the target engine |
| Rolled-back transaction tests prove commits succeed | Commit paths must be tested explicitly |
| Single-threaded tests prove locking is safe | Concurrent transaction tests are required |
| Fast H2 execution means fast production queries | Optimizers, indexes, and data sizes differ |
| Mapping one entity proves all data types are right | Precision, timezones, collations, and native types must be tested |

## Conclusion

H2 is a great tool for quickly testing portable JPA behaviors, but it is no substitute for the production database. Compatibility modes only smooth over partial syntax differences. SQL dialects, data types, schema migrations, collations, transactions, locking, and query planners can still diverge significantly.

Confirm clearly which engine your tests run against, keep H2 for appropriate checks, and use Testcontainers or integration environments with the matching database/version for native queries, migrations, concurrency, and commit-critical behaviors. Reliable QA outcomes must reflect the real engine the application runs on in deployment.