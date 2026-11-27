# H2: Testing Benefits and Differences From Real Databases

## 1. H2 in the Context of Spring Data Relational R2DBC

H2 is a relational database management system written in Java. It can run embedded inside the application process, storing data in memory or on disk, and provides SQL for creating tables, querying, updating, and deleting data. Because it starts quickly and needs no separate database server, H2 is commonly used in extended unit tests and integration tests for Spring applications.

With Spring Data R2DBC, H2 can be accessed through an R2DBC driver. Repositories, R2dbcEntityTemplate, and DatabaseClient still work through familiar Spring Data APIs. This enables testing many parts of an application without standing up PostgreSQL, MySQL, or another database server for every test run.

However, H2 is not a complete clone of a production database. Each database engine has its own SQL dialect, data types, constraint rules, transactions, locking, indexes, and query planner. A test passing on H2 only proves behavior within the H2 environment; it does not prove that SQL queries and mappings will work identically on PostgreSQL, MySQL, SQL Server, or Oracle.

The sound approach is to treat H2 as a fast testing database for general relational behavior, and then use the real production database engine for integration tests that must verify compatibility.

## 2. Why Is H2 Useful for Testing?

H2 offers several practical benefits:

- **Fast startup:** tests can create a fresh database without starting external containers or services.
- **Minimal environment dependencies:** developers and CI do not need a database server installed just to run basic test suites.
- **Isolated databases:** each test suite can use its own in-memory database to prevent leftover data from prior runs.
- **Testing relational SQL:** can verify CREATE TABLE, INSERT, SELECT, UPDATE, DELETE, constraints, and common SQL expressions.
- **Testing Spring Data mappings:** can verify entity metadata, @Table, @Column, @Id, converters, and repository queries in a more realistic environment than mocks.
- **Fast feedback:** mapping mistakes or simple query predicate bugs are caught early.
- **Easy fixtures:** tests can load schemas and sample data from scripts.

H2 is well-suited for checking questions like:

- Does the repository return the right entity by ID?
- Does Criteria build the expected filter predicates?
- Does insert persist properties and generated IDs under H2 configuration?
- Are DTOs mapped properly from standard queries?
- Does a unique constraint reject duplicate data in H2?
- Does a transaction roll back data when a write step fails in the H2 environment?

Questions involving production-specific syntax, concurrency, locking, or specialized data types require testing against the corresponding production database.

## 3. H2 Is Not a Complete Production Database Emulator

Suppose production uses PostgreSQL. An H2 test can run:

~~~sql
SELECT id, name
FROM customers
WHERE status = 'ACTIVE'
ORDER BY id
LIMIT 20;
~~~

This is standard SQL supported by many engines. But when the application uses PostgreSQL-specific features such as JSONB, array operators, ON CONFLICT, RETURNING, extensions, or engine-specific functions, H2 may not support that syntax or may have different semantics.

Even when H2 provides a similarly named feature, implementation details can differ. For instance, type casting, string comparison, timestamp handling, generated values, and transaction locks may not match production.

Therefore, distinguish clearly:

| Testing Goal | Is H2 Suitable? |
|---|---|
| Verifying basic entity mapping | Usually suitable |
| Verifying standard CRUD and repository queries | Usually suitable |
| Verifying simple relational constraints | Suitable within H2 semantics |
| Verifying dialect-specific production custom SQL | Insufficient |
| Verifying PostgreSQL JSONB, arrays, or custom functions | Insufficient |
| Verifying production locking/deadlocks/concurrency | Insufficient |
| Verifying production query plans and performance | Insufficient |
| Verifying migrations on the actual production engine | Insufficient |
| Verifying production R2DBC driver behavior | Insufficient |

H2 is a useful testing layer, but it should not be the sole evidence of production database compatibility.

## 4. Using H2 Through the R2DBC Driver

For Spring Data R2DBC to access H2, the project needs the corresponding R2DBC driver. The standard dependency is io.r2dbc:r2dbc-h2, with its version managed compatibly by Spring Boot dependency management or project configuration.

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'

    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

If using H2 exclusively via R2DBC, adding the H2 JDBC driver is not strictly necessary. The JDBC driver is only required when another component such as Flyway or Liquibase is configured to connect to H2 over JDBC.

Use an H2 R2DBC driver version compatible with your project's Spring Boot, Spring Data Relational, and R2DBC SPI versions. Avoid independently bumping one dependency beyond managed versions without verifying compatibility.

### 4.1. Configuring an In-Memory Database

An in-memory R2DBC H2 configuration looks like:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:h2:mem:///testdb
    username: sa
    password:
~~~

The exact URL and parameters for keeping the database alive depend on the R2DBC H2 driver version. Verify syntax against the documentation of the driver in use.

In-memory databases are tied to the database name and connection lifecycle. If the database closes when the last connection is released, tests can hit errors where the schema disappears between connection acquisitions. In some H2 configurations, an option is needed to keep the database alive throughout the test context lifecycle. Do not copy JDBC URL options into an R2DBC URL without checking how the R2DBC driver parses parameters.

### 4.2. Database Names and Isolation Scope

If multiple test contexts share the same in-memory database name inside the same JVM process, data may be shared depending on how the driver creates and retains databases. To keep tests independent, choose one of these approaches:

- Use a distinct database name per test suite.
- Clean up data and reset sequences in test setup.
- Close contexts/connections with an explicit lifecycle.
- Use dedicated database containers for tests needing the production engine.

Never let tests depend on execution order or leftover data from previous tests.

## 5. Initializing Schema and Test Data

SQL scripts can create the schema:

~~~text
src/test/resources/
├── schema.sql
└── data.sql
~~~

Example schema.sql:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(320) NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE UNIQUE INDEX uq_customers_email
    ON customers(email);
~~~

Example data.sql:

~~~sql
INSERT INTO customers (name, email, status)
VALUES
    ('An Nguyen', 'an@example.test', 'ACTIVE'),
    ('Binh Tran', 'binh@example.test', 'INACTIVE');
~~~

Spring Boot supports SQL script initialization for R2DBC. Common configuration:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
      data-locations: classpath:data.sql
~~~

In tests, scripts ensure each context starts with consistent schema and fixtures. Configure initialization to run in order before tests access repositories.

If your project uses Flyway or Liquibase for schema management, decide on a single source of schema creation. You can run the migration tool in tests to verify real migrations; avoid accidentally running both migrations and schema.sql on the same schema if both attempt to create the same tables.

## 6. Testing Entity Mapping With H2

Example entity:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        String email,
        String status
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);
}
~~~

Test:

~~~java
@DataR2dbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void shouldFindActiveCustomers() {
        StepVerifier.create(repository.findByStatus("ACTIVE"))
                .expectNextMatches(customer ->
                        customer.name().equals("An Nguyen"))
                .verifyComplete();
    }
}
~~~

This illustrates testing repositories and mapping via R2DBC. Real test setups must supply the H2 ConnectionFactory and matching schema fixtures. Depending on the Spring Boot version, test slice and SQL initialization setups can differ; do not assume annotations automatically select H2 unless classpath and database settings satisfy auto-configuration conditions.

This test can catch:

- Wrong table or column mapping names.
- Repository methods generating unexpected conditions.
- Incompatible entity property types.
- Fixtures missing required columns.
- Generated IDs or basic mappings failing in H2.

It does not prove that the same entity works identically with all production data types and the production driver.

## 7. Testing DatabaseClient and Explicit SQL

With DatabaseClient, H2 tests can verify portable SQL and row mapping:

~~~java
@Test
void shouldReadCustomerSummary() {
    Flux<CustomerSummary> result =
            databaseClient.sql("""
                    SELECT id, name, status
                    FROM customers
                    WHERE status = :status
                    ORDER BY id
                    """)
                .bind("status", "ACTIVE")
                .map((row, metadata) -> new CustomerSummary(
                        row.get("id", Long.class),
                        row.get("name", String.class),
                        row.get("status", String.class)
                ))
                .all();

    StepVerifier.create(result)
            .expectNextCount(1)
            .verifyComplete();
}
~~~

This is useful when SQL does not depend on engine-specific dialects. H2 helps catch common syntax errors, invalid aliases, misspelled column names, and basic type mapping mismatches.

If SQL uses ON CONFLICT, JSONB operators, PostgreSQL arrays, RETURNING, or custom functions, H2 tests may fail even when the PostgreSQL query is valid—or worse, pass in compatibility mode despite differing semantics. Verify those queries on the matching production database.

## 8. SQL Dialect Differences

Each database has its own dialect. H2 supports a broad set of SQL, yet it does not implement every syntax from other databases.

Areas prone to differences:

- Pagination and limit syntax.
- Upsert and conflict handling.
- Generated keys and RETURNING/OUTPUT.
- CTEs and recursive queries.
- Window functions.
- JSON operators and functions.
- Arrays, enums, and domain types.
- Sequences and identity columns.
- Date/time, string, and math functions.
- Locking clauses like FOR UPDATE.
- Index and partial index syntax.

PostgreSQL upsert example:

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES (:sku, :quantity)
ON CONFLICT (sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

An H2 equivalent might use H2's MERGE syntax:

~~~sql
MERGE INTO inventory (sku, quantity)
KEY (sku)
VALUES (:sku, :quantity);
~~~

Both statements express forms of key-based insert/update, but they should not be treated as completely equivalent. Semantics around multiple unique constraints, triggers, affected-row counts, concurrency, and generated values can differ.

If production uses PostgreSQL ON CONFLICT, test that statement on PostgreSQL rather than writing an alternative H2 query and assuming upsert has been verified.

## 9. Identifier and Table/Column Name Differences

Databases have their own rules for handling unquoted versus quoted identifiers.

For instance, PostgreSQL folds unquoted identifiers to lowercase; H2 has its own identifier normalization rules, typically displaying unquoted identifiers in uppercase in metadata. Quoted identifiers can handle case sensitivity differently.

This can expose bugs when:

- An entity uses @Column("createdAt") while the schema uses created_at.
- Raw SQL quotes column names with mismatched casing.
- A migration creates quoted table names.
- Metadata mappings and query column names are inconsistent.
- H2 tests pass while metadata queries or native SQL fail in production.

Adopt a consistent naming convention—usually unquoted snake_case for table and column names—and declare @Table/@Column explicitly when needed. For raw SQL, follow the target database's identifier rules and test on that engine.

## 10. Data Type Differences

Java and SQL types are mapped via R2DBC drivers and Spring Data converters. The same Java type can correspond to different SQL types across databases.

Types requiring attention:

| Data Category | Examples of Differences to Check |
|---|---|
| Boolean | How booleans are represented and converted |
| UUID | Native UUID type vs. string/binary |
| Timestamp | Timestamps with vs. without timezone |
| Decimal | Precision, scale, and rounding |
| JSON | JSON text, native JSON, or JSONB |
| Array | Array support and driver read/write behavior |
| Enum | Native enum vs. VARCHAR |
| Binary | BLOB/BYTEA and byte array mapping |
| Identity/sequence | How IDs are generated and returned |
| Large text | TEXT, CLOB, or length limits |

For example, PostgreSQL has native UUID and JSONB types. H2 supports several similar types, yet the Java types returned by the driver, function syntax, and semantics can differ. An H2 test cannot validate PostgreSQL JSONB mapping.

### 10.1. Timestamps and Timezones

Do not assume LocalDateTime, Instant, OffsetDateTime, and ZonedDateTime carry identical semantics across every database.

- LocalDateTime represents date and time without a timezone.
- Instant represents a point on the UTC timeline.
- OffsetDateTime carries a numeric offset.
- SQL timestamp-with-time-zone types vary in semantics across engines.

For example, PostgreSQL TIMESTAMPTZ normalizes instants per PostgreSQL semantics, while display depends on session timezone. H2 has its own timestamp-with-time-zone type. Tests should verify round-trip instants rather than merely comparing formatted strings.

If business logic needs an absolute instant, specify the Java type, SQL type, and serialization format explicitly. Do not let H2 tests running in a developer's default local timezone mask production bugs.

### 10.2. Decimals and Currency

For BigDecimal, declare precision and scale explicitly in the schema:

~~~sql
amount DECIMAL(19, 4) NOT NULL
~~~

Verify rounding, scale, and out-of-range values. H2 and production databases can differ in how they coerce or reject values whose scale exceeds the column definition. Java unit tests for arithmetic do not replace integration tests storing and reading decimals through the real driver.

## 11. Constraint and Data Integrity Differences

H2 supports primary keys, unique constraints, foreign keys, check constraints, and not-null constraints. Nevertheless, detailed semantics can differ from production databases.

Check:

- Unique constraints when one or more columns are NULL.
- Foreign keys with ON DELETE CASCADE/RESTRICT/SET NULL.
- Deferrable constraints if production relies on them.
- Check constraints and function expressions.
- Partial unique indexes.
- Constraint validation when added to populated tables.
- Constraint evaluation order within a transaction.
- Error details and SQLState returned by the driver.

Example:

~~~sql
CREATE TABLE customer_addresses (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    address_line VARCHAR(200) NOT NULL,
    CONSTRAINT fk_address_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
        ON DELETE CASCADE
);
~~~

H2 can verify foreign key relationships and cascades in tests. But if production relies on partial indexes or deferrable constraints, test on that engine because H2 may not support them or may behave differently.

Do not only assert that an operation throws an exception. If the application classifies errors by SQLState, vendor error code, or constraint name, test against the production driver.

## 12. Transaction and Isolation Differences

Transactions are one area where behavior must never be inferred from H2 to production.

Database engines can differ in:

- Supported isolation levels and their actual semantics.
- MVCC and snapshot visibility.
- Lock granularity.
- Row locks vs. table locks.
- Deadlock detection.
- Serialization failures.
- DDL transactions.
- Behavior when a transaction is cancelled or a connection drops.
- When constraints are checked.

For example, two transactions reading a quantity and then updating it can race differently depending on isolation and locking. A simple H2 test may never reproduce PostgreSQL/MySQL deadlocks or serialization failures under concurrent load.

If business logic depends on optimistic locking with @Version, pessimistic locking, SELECT ... FOR UPDATE, or specific isolation levels, test on the production database engine. Build real concurrency tests with multiple connections/transactions rather than sequential repository calls in one test.

## 13. Index and Query Planner Differences

H2 has its own query optimizer and index implementation. It may choose a completely different execution plan than PostgreSQL, MySQL, or SQL Server.

Therefore:

- A query running fast on H2 does not prove it will run fast in production.
- An index used by H2 does not prove production will use the same index.
- Estimated row counts and cost models differ.
- Statistics and statistics collection differ.
- Partial/covering indexes and expression indexes may not be supported identically.
- Join orders and join algorithms can differ.

Never use H2 to benchmark production database performance. Run EXPLAIN or equivalent tools on the actual engine with data sizes and distributions resembling production.

H2 remains useful for functionally verifying query logic. Performance evaluation requires a production-representative environment.

## 14. Collation and String Comparison Differences

Filtering and sorting strings depend on collation, case sensitivity, and accent handling.

Example:

~~~sql
SELECT id, name
FROM customers
WHERE name = :name
ORDER BY name;
~~~

H2 and production can differ when comparing An, AN, án, or accented strings. Using LOWER(name) provides partial normalization but still does not guarantee identical collations everywhere.

Verify:

- Case-sensitive comparisons.
- Accent-sensitive comparisons.
- Locale-specific sort ordering.
- LIKE and wildcards.
- LOWER/UPPER functions.
- Unique constraints on strings under collation.
- Expression indexes or explicit collations.

If business logic requires case-insensitive names or emails, define normalization rules and unique constraints explicitly on the production database. H2 tests can verify Java normalization code, but cannot prove production collation behavior.

## 15. Generated ID, Sequence, and RETURNING Differences

Spring Data R2DBC supports generated IDs via mapping metadata and dialects. Yet how databases generate and return IDs differs.

Some databases use identity columns; some use sequences; some support RETURNING, while others use different generated-key mechanisms or statements.

Example:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL
);
~~~

H2 tests can confirm an ID is generated and populated on the returned entity. But if production uses custom PostgreSQL sequences, triggers, or default expressions, test on PostgreSQL.

Do not write generated-key SQL based on H2 assumptions and deploy it unchanged to another database. Check the production dialect and driver.

## 16. H2 Compatibility Modes Have Limits

H2 provides compatibility modes that adjust certain behaviors to mimic other databases, such as PostgreSQL or MySQL modes depending on version.

Compatibility modes can help run certain SQL statements or familiar constructs. However, they do not turn H2 into real PostgreSQL or MySQL.

They do not fully replicate:

- Internal storage engines.
- Query planners and statistics.
- Locking/MVCC implementations.
- All data types and operators.
- Extensions and built-in functions.
- Constraint semantics.
- Driver behavior.
- Replication and failover.
- Permission models.
- Migration edge cases.

Do not use compatibility modes as an excuse to skip testing on the production database. Treat them as a convenience for smoothing minor syntax differences, not an equivalence guarantee.

## 17. Differences Between H2 JDBC and H2 R2DBC

H2 provides both a JDBC driver and an R2DBC driver. Both talk to the same H2 database family, yet use different APIs and lifecycles.

- JDBC uses DataSource, Connection, PreparedStatement, and blocking APIs.
- R2DBC uses ConnectionFactory, Connection, Statement, and reactive Publishers.
- Spring Data R2DBC requires the R2DBC driver to create ConnectionFactory.
- Flyway or certain Liquibase setups typically require the JDBC driver to run migrations.

If a test checks an R2DBC repository, use the H2 R2DBC driver. Using H2 JDBC for schema setup does not prove the R2DBC repository itself is being tested; verify that both drivers see the exact same database/schema when sharing an in-memory database.

When combining Flyway JDBC and R2DBC H2, configure both URLs to target the same H2 database and keep the database alive long enough for both connections to access it. Exact URL syntax and lifecycle flags depend on the driver. If you only need basic repository tests, initializing the schema with the R2DBC SQL initializer avoids adding a JDBC path.

## 18. H2 Tests Do Not Validate Production Migrations

A migration may be valid on PostgreSQL yet fail on H2 due to syntax or data type differences. The reverse can also occur: a migration runs on H2 yet is rejected in production.

For example, migrations may use:

- JSONB.
- CREATE INDEX CONCURRENTLY.
- Partial indexes with WHERE.
- ALTER TYPE.
- Sequences or extensions.
- Engine-specific functions/procedures.
- Dialect-specific generated column syntax.
- Database-specific lock or transaction behavior.

If migrations target PostgreSQL, run migrations against PostgreSQL in tests. Never rewrite a production migration into a separate H2 script and treat that as testing the same migration.

When migrations must support multiple databases, maintain separate changelogs or migration locations per engine. Test every variant on its corresponding database and guard against drift between migration sets.

## 19. Using Testcontainers to Test Real Databases

Testcontainers spins up real databases inside containers during test execution. For example, if production uses PostgreSQL, you can run a matching PostgreSQL container version.

Test dependencies:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

A test can start the container and supply the R2DBC URL dynamically:

~~~java
@Testcontainers
@SpringBootTest
class CustomerPostgresIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://" +
                postgres.getHost() + ":" +
                postgres.getFirstMappedPort() + "/" +
                postgres.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }
}
~~~

This is an illustrative configuration; use the exact container APIs and R2DBC URL matching your Testcontainers and driver versions. If using Flyway, also provide the JDBC URL, username, and password pointing to the same container so migrations run before tests.

Testcontainers requires Docker or a compatible container runtime. If CI lacks a container runtime, provision a managed test database service matching production versions and settings.

### 19.1. When to Use H2 vs. Testcontainers

| Test Type | H2 | Testcontainers With Production DB |
|---|---|---|
| Standard repository CRUD | Good, fast | Good, though slower startup |
| Simple entity mapping | Suitable | Verifies production driver |
| Pure portable SQL | Often suitable | Recommended for critical queries |
| Dialect-specific SQL | Insufficient | Required |
| Production migrations | Insufficient | Required |
| JSON/array/vendor types | Insufficient | Required |
| Locking and concurrency | Insufficient for conclusions | Required |
| Query plans/performance | Not representative | Closer to reality; still needs realistic data |
| Production driver error handling | Insufficient | Required |

## 20. A Multi-Tiered Testing Strategy

You do not have to pick exclusively H2 or Testcontainers for every test. Organize tests in layers:

~~~text
                 Unit tests
             Domain / service logic
                      |
                      v
              H2 R2DBC tests
        Mapping / CRUD / standard SQL
                      |
                      v
          Testcontainers integration
        Production dialect / driver /
          migrations / transactions
                      |
                      v
          Staging / production-like
        Load / concurrency / operations
~~~

### Tier 1: Unit Tests

Mock dependencies or test pure domain logic to verify:

- Business rules.
- Validation.
- Service-layer DTO mapping.
- Error handling.
- Publisher orchestration decisions.

Unit tests do not need a database when persistence is not under test.

### Tier 2: H2 R2DBC Tests

Use H2 for fast checks of:

- Standard repository queries.
- Entity mapping.
- CRUD operations.
- Simple constraints.
- Basic transaction rollback.
- Row mapping for portable SQL.

### Tier 3: Production Database Integration Tests

Use Testcontainers or a matching test database engine to verify:

- SQL dialect behavior.
- Migrations.
- Vendor-specific types.
- Generated IDs and sequences.
- Transaction isolation.
- Locking and concurrency.
- Custom converters with the real driver.
- Constraints and error codes.
- Queries requiring specific indexes or execution plans.

### Tier 4: Staging/Performance Tests

Use production-like data and settings to test load, connection pools, query plans, latency, replication, and database failure modes.

H2 does not replace these subsequent tiers.

## 21. Limitations of Testing Transactions on H2

H2 can verify a simple transaction flow: insert an entity, emit an error, and confirm the data rolled back.

Example:

~~~java
@Transactional
public Mono<Customer> createThenFail(Customer customer) {
    return customerRepository.save(customer)
            .flatMap(saved ->
                    Mono.error(new IllegalStateException("force rollback"))
            );
}
~~~

Test:

~~~java
StepVerifier.create(service.createThenFail(customer))
        .expectError(IllegalStateException.class)
        .verify();

StepVerifier.create(customerRepository.count())
        .expectNext(0L)
        .verifyComplete();
~~~

This test verifies transaction flow under the current H2 configuration. It does not prove every rollback, cancellation, lock, or isolation case matches PostgreSQL/MySQL.

If the system depends on SELECT FOR UPDATE, optimistic locking, transaction propagation, or specific isolation levels, write integration tests on the production engine. Build real concurrency tests using multiple connections/transactions rather than sequential calls in a single test.

## 22. Testing Repositories and Queries With H2 Independently of Test Order

A good test prepares its own data and never depends on execution order.

Example:

~~~java
@BeforeEach
void setUp() {
    // Delete old test data and create fixtures for the current test.
}
~~~

In reactive tests, setup must be subscribed to and complete before assertions start. Use reactive setup patterns compatible with your test framework, or place setup directly inside the test pipeline:

~~~java
Mono<Void> arrange = customerRepository.deleteAll()
        .thenMany(Flux.just(
                new Customer(null, "An", "an@example.test", "ACTIVE"),
                new Customer(null, "Binh", "binh@example.test", "INACTIVE")
        ))
        .thenMany(customerRepository.saveAll(
                Flux.just(
                        new Customer(null, "An", "an@example.test", "ACTIVE"),
                        new Customer(null, "Binh", "binh@example.test", "INACTIVE")
                )
        ))
        .then();

StepVerifier.create(
        arrange.thenMany(customerRepository.findByStatus("ACTIVE"))
)
.expectNextMatches(customer -> customer.name().equals("An"))
.verifyComplete();
~~~

Adjust this illustration to your actual repository and entity APIs; never call subscribe() inside setup and then run assertions before data seeding completes.

If an entire suite shares one in-memory database, parallel tests can wipe out each other's data. Use separate databases per context/suite or disable parallel execution for tests sharing a schema without proper isolation.

## 23. H2 and Spring Boot Test Slices

@DataR2dbcTest lets you focus on repositories and R2DBC configuration without bootstrapping the entire application. The test slice typically loads only required persistence beans and can use test database settings.

Example:

~~~java
@DataR2dbcTest
@Import(CustomerRepositoryConfiguration.class)
class CustomerRepositoryTest {
    // Inject repository and verify queries.
}
~~~

Exact configuration depends on Spring Boot version, classpath dependencies, and how the project declares ConnectionFactory. If H2 is not auto-selected or needs explicit settings, declare spring.r2dbc.url in src/test/resources/application.yml or via test properties.

For tests needing full services, transaction managers, migrations, or security contexts, @SpringBootTest fits better at the cost of slower startup.

Do not assume a test slice verifies production migrations. If the slice skips Flyway/Liquibase, the schema may come from schema.sql and bypass real migrations.

## 24. Testing Custom Conversions and Data Types

Spring Data R2DBC supports custom converters for domain types. H2 is handy for verifying converters over common SQL types, though production driver tests remain necessary for specialized types.

Example domain value object:

~~~java
public record EmailAddress(String value) {}
~~~

Writing converter:

~~~java
@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

H2 tests can confirm String round-tripping. However, if production stores EmailAddress in a native type or the production driver returns a different Java type, converters may need adjustments. Test converters against the exact production SQL type and R2DBC driver.

## 25. Never Use H2 to Benchmark Production

A query may run in a few milliseconds on H2 yet run much slower on a production database. That is not necessarily due to application code; storage engines, networking, connection pools, indexes, statistics, and concurrency all differ.

Do not:

- Compare H2 latency against PostgreSQL to claim production queries are fast.
- Rely on H2 execution plans to design production indexes.
- Estimate production R2DBC throughput from in-memory H2.
- Use H2 to test pool saturation or network timeouts.
- Use H2 as evidence of real database scalability.

Benchmarks must run on the matching engine/version and production-like configuration, using representative data, connection counts, and concurrency. H2 is only suited for fast functional checks.

## 26. Common Pitfalls When Substituting H2 for Production Databases

| Symptom | Possible Cause | Fix |
|---|---|---|
| Query passes on H2 but fails in production | Different dialect syntax or functions | Run query on production DB via Testcontainers |
| Migration passes on H2 but fails in production | Engine-specific DDL, types, or indexes | Test migrations on the target engine |
| Tests cannot find tables in a fresh context | In-memory database closed or URL targets another DB | Check DB name, lifecycle flags, and ConnectionFactory |
| H2 test passes but timestamps shift | Timezone/precision differences | Use explicit temporal types and test on production driver |
| Unique constraint behaves differently | Different NULL/collation/constraint semantics | Verify unique rules on production DB |
| Tests miss JSONB bugs | H2 does not replicate production types/operators | Use PostgreSQL Testcontainers |
| Tests pass but production deadlocks | Different locking/concurrency engine | Write concurrency tests on the real DB |
| SQL mapping fails due to column names | Different identifier folding/quoting | Standardize naming and test native SQL on target engine |
| H2 compatibility mode still rejects SQL | Mode does not implement full dialect | Do not treat compatibility mode as an emulator |
| Generated IDs behave differently in production | Identity/sequence/RETURNING differences | Test generated values with the real driver |
| Production query plan skips index | Different planner/statistics | Run EXPLAIN on a production-like database |
| Test passes standalone but fails in suite | Shared database state or parallel execution | Isolate databases and fixtures |
| Flyway does not run on H2 R2DBC | Missing JDBC driver/config | Supply JDBC driver and JDBC URL if migrations use JDBC |

## 27. Process for Deciding Between H2 and a Real Database

Before picking H2 for a group of tests, evaluate:

1. Is the test checking domain logic, mapping, or SQL dialect?
2. Does the query use production-specific syntax or data types?
3. Do migrations contain engine-specific DDL, functions, or indexes?
4. Does the test depend on transaction isolation, locking, or concurrency?
5. Do we need to verify the production R2DBC driver?
6. Do we need to verify generated keys, sequences, or RETURNING?
7. Is the H2 database isolated per test context?
8. Is the schema created from migrations or separate scripts?
9. Can tests run in parallel without sharing data?
10. Does a Testcontainers suite cover production-specific behaviors?

Choose H2 when the test goal stays within common relational SQL and fast feedback is the priority. Choose the production database via Testcontainers when verifying dialects, drivers, migrations, types, transactions, or concurrency.

## 28. A Practical Test Structure

A project can organize tests as:

~~~text
src/test/
├── java/
│   └── com/example/
│       ├── unit/
│       │   └── CustomerServiceTest.java
│       ├── h2/
│       │   └── CustomerRepositoryH2Test.java
│       └── postgres/
│           ├── CustomerRepositoryPostgresTest.java
│           └── FlywayMigrationTest.java
└── resources/
    ├── application-h2-test.yml
    └── db/
        └── test-data.sql
~~~

One categorization:

- Unit tests needing no database.
- Fast H2 tests for basic repository CRUD and mapping.
- PostgreSQL Testcontainers tests for native queries, migrations, types, and transactions.
- Staging tests for load, concurrency, and operations.

Package and profile names are just suggestions. Use Gradle test tasks or JUnit tags to run separate groups in CI, while ensuring production database tests are never skipped in release pipelines.

## 29. Conclusion

H2 is a valuable option for testing Spring Data R2DBC because it runs fast, stays isolated, and needs no external server. Over its R2DBC driver, tests can verify repositories, entity mapping, CRUD, Criteria, standard SQL, basic constraints, and simple transaction flows.

Its limits stem from differences across database engines. SQL dialects, identifiers, data types, timezones, decimals, constraints, collations, generated IDs, transaction isolation, locking, query planners, and migrations can all differ from production databases. H2 compatibility modes adjust only part of the behavior and do not turn H2 into a replica of PostgreSQL, MySQL, or other engines.

Use H2 to speed up feedback on general relational checks. For native queries, migrations, specialized types, concurrency, locking, and driver behavior, run Testcontainers or a test database matching production type and version. Combining both layers keeps daily development fast while providing reliable compatibility evidence before release.
