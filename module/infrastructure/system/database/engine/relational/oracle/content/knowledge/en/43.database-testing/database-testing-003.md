# Integration Testing with Real Oracle and Differences from H2

A Spring Boot application using JPA can run unit tests and some fast repository tests with H2. However, even with Oracle compatibility mode enabled, H2 does not become Oracle Database. The two DBMSs differ in SQL parser, data types, transactions, locking, sequences, functions, metadata, and JDBC behavior.

Therefore, a test suite running only on H2 can pass while the application still fails when running on real Oracle. Bugs that commonly appear only in Oracle environments include invalid SQL, `DATE`/`TIMESTAMP` differences, empty strings treated as `NULL`, incorrect sequences, incompatible DDL migrations, differing lock behavior, and schema privilege errors.

The right strategy is to use each test type for its specific goal:

- Unit tests verify business logic independently of the database.
- H2 tests can quickly verify a subset of repositories or simple flows if the SQL falls within the compatible subset.
- Integration tests against real Oracle verify SQL, JPA mappings, migrations, transactions, and driver behavior on the actual engine.
- End-to-end tests verify that the application and integrated components work together in a near-production environment.

## 1. Why doesn't H2 replace Oracle?

H2 is a relational database that runs inside the JVM, often convenient for testing because of fast startup and in-memory execution. H2 provides several syntax compatibility modes, including Oracle mode. This mode helps H2 understand some familiar syntax or behaviors, but it does not fully emulate Oracle SQL, PL/SQL, the optimizer, transaction engine, data dictionary, or JDBC driver.

Example:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:testdb;MODE=Oracle;DB_CLOSE_DELAY=-1
    username: sa
    password:
    driver-class-name: org.h2.Driver
~~~

`MODE=Oracle` can be useful for running simple tests quickly, but it does not prove a SQL statement will execute on Oracle. H2 still uses H2's engine and data types; compatibility mode only covers a subset of behavior.

### Example of risk

A repository might use syntax that H2 accepts:

~~~sql
SELECT *
  FROM orders
 LIMIT 10;
~~~

Oracle Database does not support `LIMIT` with this syntax. Standard pagination in modern Oracle typically uses `OFFSET ... FETCH`, or Hibernate generates SQL per the Oracle dialect:

~~~sql
SELECT *
  FROM orders
 ORDER BY order_id
 OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY;
~~~

If tests only run on H2, this bug may go undetected. Similarly, H2 may accept a type conversion that Oracle rejects, or vice versa.

## 2. Common differences between Oracle and H2

Do not build a syntax checklist and assume turning on Oracle mode handles everything. Differences can appear across many layers.

| Topic | Oracle Database | H2 / Oracle mode | Risk when testing only on H2 |
|---|---|---|---|
| Empty string | Empty string in `VARCHAR2` is treated as `NULL` | May distinguish empty string from `NULL` | Wrong validation, unique logic, and queries |
| Identifiers | Unquoted identifiers are normalized to uppercase | Rules and settings may differ | Wrong table/column/schema names |
| `DATE` | Stores date and time down to seconds | `DATE` usually represents date only | Wrong mapping and time predicates |
| `TIMESTAMP` | Has fractional seconds and timezone variants | Semantics differ by type and setting | Time drift, lost precision |
| `NUMBER` | Oracle-specific precision/scale | Different numeric implementation | Overflow or rounding errors |
| Sequences | `NEXTVAL`, cache, and Oracle semantics | Supports sequences but differs in details | ID errors or ordering assumptions |
| PL/SQL | Packages, procedures, triggers, cursors, exceptions | Does not fully implement PL/SQL | Migrations or stored code fail |
| Functions | `NVL`, `DECODE`, `LISTAGG`, `CONNECT BY`, ... | Only partially supported | Native queries fail |
| Pagination | `OFFSET/FETCH`, `ROWNUM`, analytic functions | Different SQL generation | Native queries or pagination break |
| Transactional DDL | DDL usually triggers implicit commit | Different DDL transaction handling | Rollback tests give false safety |
| Locking | Oracle row locks, `FOR UPDATE`, `SKIP LOCKED` | Different engine and scheduling | Deadlocks, timeouts, or race conditions |
| Metadata | Data dictionary, synonyms, schemas, grants | Different metadata model | Broken privilege and migration tests |
| LOBs | `CLOB`/`NCLOB`/`BLOB` and locator semantics | Different LOB implementation | Mapping or streaming errors |

The sections below explain the differences that directly affect Spring Data JPA.

## 3. Empty strings and NULL

In Oracle, a zero-length string is treated as `NULL` for character types such as `VARCHAR2`. This can make results differ from H2.

Example:

~~~sql
INSERT INTO customers(customer_code)
VALUES ('');
~~~

On Oracle, the value of `customer_code` is treated as `NULL`. A query:

~~~sql
SELECT *
  FROM customers
 WHERE customer_code = '';
~~~

does not mean finding an empty string the way many other DBMSs interpret it. Comparing against `NULL` requires `IS NULL`.

In Java, an empty string and `null` are two distinct values. If the application sends an empty string down to Oracle, the database may store `NULL`, causing data read back to differ from the original object.

Explicitly test:

- Forms submitting an empty string.
- Forms leaving fields blank.
- Strings containing only spaces.
- `NULL` in unique keys or composite keys.
- Predicates using `=`, `IS NULL`, `NVL`, or `COALESCE`.

Do not automatically trim strings if business rules require preserving spaces. Define the normalization policy at the application layer.

## 4. Identifiers, schemas, and case sensitivity

Oracle normalizes unquoted identifiers to uppercase:

~~~sql
CREATE TABLE order_items (
  item_id NUMBER
);
~~~

The actual names stored are `ORDER_ITEMS` and `ITEM_ID`. If an identifier is created with double quotes:

~~~sql
CREATE TABLE "orderItems" (
  "itemId" NUMBER
);
~~~

then it must be referenced with the exact spelling and case using double quotes in all corresponding SQL statements.

In JPA applications, avoid creating quoted mixed-case table/column names without a clear reason. Mappings can vary across Hibernate dialects, naming strategies, and databases.

### Schema is not the same as database

In Oracle, a schema is tied to the user owning the objects. When connecting as user `APP_RUNTIME`, the default schema is usually `APP_RUNTIME`, though the user can be granted privileges to read objects in another schema.

Differences to test:

- `CURRENT_SCHEMA` and the login user are not the same concept.
- Synonyms can mask real schema names.
- Object privileges and system privileges differ.
- A query that works under a DBA account may fail under an application account.
- Object names may resolve differently when `CURRENT_SCHEMA` changes.

Integration tests should run under a user similar to the production application, not solely `SYSTEM` or `SYS`.

## 5. DATE, TIMESTAMP, and timezones

This is one of the most common sources of bugs when moving from H2 to Oracle.

### Oracle DATE includes time

Oracle `DATE` stores year, month, day, hour, minute, and second. It does not store fractional seconds or timezone. H2 `DATE` normally represents only the date portion. Consequently, an Oracle `DATE` column mapped to Java `LocalDate` can truncate the time component if the actual schema stores hours/minutes/seconds.

If an Oracle `DATE` column stores full timestamps to the second, consider an appropriate mapping like `LocalDateTime` and verify Hibernate/JDBC mapping. If the column only holds business dates, normalize data to midnight and use `LocalDate` under a clear convention.

### TIMESTAMP and timezone types

Oracle provides:

- `TIMESTAMP`: date and time with fractional seconds, without timezone.
- `TIMESTAMP WITH TIME ZONE`: includes timezone offset/region.
- `TIMESTAMP WITH LOCAL TIME ZONE`: normalized to the database timezone and displayed in the session timezone.

These types are not strictly equivalent to `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, or `Instant`.

DDL example:

~~~sql
CREATE TABLE event_log (
  event_id NUMBER PRIMARY KEY,
  created_at TIMESTAMP(6) NOT NULL,
  occurred_at TIMESTAMP(6) WITH TIME ZONE
);
~~~

Illustrative Java mapping:

~~~java
@Entity
public class EventLog {
    @Id
    private Long eventId;

    private LocalDateTime createdAt;

    private OffsetDateTime occurredAt;
}
~~~

Exact mapping depends on the Hibernate version, Oracle JDBC driver, and column type. Test both insert and read-back paths with integration tests.

### NLS and implicit conversion

Do not rely on implicit conversion via `NLS_DATE_FORMAT` or `NLS_TIMESTAMP_FORMAT`. Avoid SQL like:

~~~sql
WHERE created_at = '14-11-2026'
~~~

Bind typed parameters from JDBC/JPA or use explicitly formatted literals:

~~~sql
WHERE created_at >= DATE '2026-11-14'
~~~

For timestamps, use bind parameters or `TO_TIMESTAMP` with an explicit format mask. Tests should run under different session NLS settings to detect dependencies on default configurations.

## 6. NUMBER, precision, and scale

Oracle `NUMBER(p,s)` has explicit precision and scale. Example:

~~~sql
CREATE TABLE payment (
  payment_id NUMBER(18,0) PRIMARY KEY,
  amount     NUMBER(12,2) NOT NULL
);
~~~

Java mappings typically use `Long` for integers within range and `BigDecimal` for currency or numbers requiring precision. Avoid `double` for monetary values because floating-point arithmetic can introduce rounding errors.

Example:

~~~java
@Column(name = "AMOUNT", precision = 12, scale = 2)
private BigDecimal amount;
~~~

Test:

- Maximum and minimum valid values.
- Values with extra decimal digits.
- Rounding and scale when persisting.
- Negative values if allowed by business rules.
- Values exceeding precision.
- Nullability.

Do not just inspect the entity after setting fields. Persist, flush, clear the persistence context, and read back from Oracle to verify the actual stored value.

## 7. Sequences, identity, and ID generation strategies

Oracle supports sequences:

~~~sql
CREATE SEQUENCE order_seq
  START WITH 1
  INCREMENT BY 1
  CACHE 100;
~~~

Fetching a value:

~~~sql
SELECT order_seq.NEXTVAL
  FROM dual;
~~~

Hibernate can use a sequence generator:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_seq_gen"
)
@SequenceGenerator(
    name = "order_seq_gen",
    sequenceName = "ORDER_SEQ",
    allocationSize = 1
)
private Long id;
~~~

`allocationSize` must align with how Hibernate allocates IDs and the sequence's increment according to the generator strategy. If mismatched, you may encounter unexpected ID jumps or mapping/sequence increment errors depending on the Hibernate version and configuration.

Oracle sequences do not guarantee contiguous IDs:

- Rollbacks do not return sequence values.
- Caching can drop unused values upon instance restart.
- RAC can issue sequence values across multiple instances.
- Sequences guarantee issued values, not transaction commit order.

Tests should not assert gap-free consecutive IDs. Verify ID existence, uniqueness, and proper mapping.

### Identity columns

Modern Oracle versions support identity columns:

~~~sql
CREATE TABLE audit_event (
  event_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  event_type VARCHAR2(50) NOT NULL
);
~~~

Identity support and Hibernate SQL generation depend on the Oracle version, dialect, and JDBC driver. If the production schema uses sequences, do not let H2 tests auto-generate identity columns and assume production migrations are verified.

## 8. Oracle-specific SQL and native queries

JPA JPQL is more portable than native SQL, yet mappings and Hibernate-generated SQL still require verification. Native queries are coupled directly to the engine.

Common Oracle syntax/functions include:

- `DUAL`.
- `NVL`, `DECODE`.
- `LISTAGG`.
- `CONNECT BY`.
- `ROWNUM`.
- `ROW_NUMBER() OVER (...)`.
- `MERGE`.
- `REGEXP_LIKE`.
- `SYS_GUID()`.
- `SYSTIMESTAMP`.
- JSON operators/functions depending on version.

Hierarchical query example:

~~~sql
SELECT employee_id,
       manager_id,
       LEVEL AS hierarchy_level
  FROM employees
 START WITH manager_id IS NULL
 CONNECT BY PRIOR employee_id = manager_id;
~~~

H2 Oracle mode is not guaranteed to fully support Oracle hierarchical queries, packages, optimizer hints, or version-specific functions. These queries must be tested on real Oracle.

### Pagination

Native SQL using `ROWNUM`, `OFFSET/FETCH`, or analytic functions follows distinct rules. When using Spring Data `Pageable`, let the Hibernate Oracle dialect generate SQL whenever possible, then inspect both the generated SQL and actual Oracle results.

Never write a native query with `LIMIT` and expect Oracle to understand it.

### MERGE and concurrent updates

Oracle `MERGE` is very useful for upserts, but behavior when multiple transactions concurrently insert/update the same key must be tested. H2 may have different semantics or lock scheduling.

If upserts are a critical path, run concurrency tests on Oracle with real unique constraints and define how duplicate keys/retries are handled.

## 9. PL/SQL, packages, triggers, and stored procedures

Real-world Oracle applications may use:

- PL/SQL packages.
- Stored procedures/functions.
- Triggers.
- Sequences and triggers for ID generation.
- Scheduler jobs.
- Synonyms.
- Database links.
- Virtual columns.
- Function-based indexes.
- Partitioned tables.

H2 does not implement PL/SQL like Oracle. An H2 test cannot verify package compilation, trigger execution, or procedure exception handling as Oracle does.

Procedure example:

~~~sql
CREATE OR REPLACE PROCEDURE close_order(
  p_order_id IN NUMBER
) AS
BEGIN
  UPDATE orders
     SET status = 'CLOSED'
   WHERE order_id = p_order_id;
END;
/
~~~

Integration tests should invoke procedures via JDBC or `EntityManager` on real Oracle, then verify data state and any returned Oracle errors.

### Checking invalid objects

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
  FROM all_objects
 WHERE status = 'INVALID'
 ORDER BY owner, object_type, object_name;
~~~

Migration tests should verify that packages, views, triggers, and procedures compile cleanly. Do not merely verify that Flyway/Liquibase reports migration completion.

## 10. Transactions and DDL: a crucial difference

Oracle DDL statements such as `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, and `CREATE INDEX` generally trigger implicit commits before and after the DDL. Consequently, DDL is not rolled back like DML within a normal transaction.

Example:

~~~sql
BEGIN
  INSERT INTO test_log(id) VALUES (1);
  CREATE TABLE sample_table(id NUMBER);
  ROLLBACK;
END;
~~~

Do not expect the insert before the DDL to roll back like a pure DML transaction. Oracle DDL can commit the preceding transaction state before executing the DDL.

This directly impacts tests:

- `@Transactional` tests will not undo any DDL executed.
- Migrations creating tables/indexes may persist even after a test rolls back.
- `@Sql` scripts containing DDL can leave state behind for subsequent tests.
- Cleanup via `TRUNCATE` is also DDL and triggers an implicit commit.

For integration tests, use an isolated database/schema and migrations that can run repeatably on a fresh database. DML tests can roll back via transactions; DDL must be managed via migrations or dedicated cleanup.

## 11. Isolation, locking, and concurrency

Oracle defaults to `READ COMMITTED` with statement-level read consistency. Each query sees a consistent snapshot as of the moment the statement began, rather than a fixed snapshot for the entire transaction as some might expect from other DBMSs.

Scenarios to test on Oracle:

- Two transactions updating the same row.
- `SELECT ... FOR UPDATE`.
- `NOWAIT` and `WAIT n`.
- `SKIP LOCKED`.
- Unique constraints when two transactions insert the same key.
- Deadlocks across tables acquired in different lock orders.
- Transactions reading while another transaction updates.
- `SERIALIZABLE` isolation if used by the application.

Example:

~~~sql
SELECT order_id,
       status
  FROM orders
 WHERE order_id = :order_id
 FOR UPDATE WAIT 5;
~~~

H2 may produce different results regarding blocking timing, lock timeouts, deadlocks, and error codes. If the application processes queues using `FOR UPDATE SKIP LOCKED`, it must be tested on Oracle.

### Do not test with only one connection

A sequential repository test will not uncover race conditions. For critical write paths, use multiple real threads/connections, barriers/latches to coordinate execution, and assert final state on Oracle.

Do not use `Thread.sleep()` as the primary synchronization mechanism in concurrency tests. Use latches, barriers, or deterministic synchronization mechanisms for reliable tests.

## 12. LOB, JSON, and specialized data types

Oracle has specific types and handling behavior:

- `CLOB` and `NCLOB`.
- `BLOB`.
- `BFILE`.
- `RAW` and `LONG RAW` in legacy systems.
- `XMLTYPE` depending on version/option.
- Native `JSON` or JSON stored as text depending on release.
- `INTERVAL`.
- `TIMESTAMP WITH TIME ZONE`.

Hibernate/JDBC mappings must be tested with realistic data:

- Are large LOBs streamed or materialized entirely into memory?
- Are Unicode and national character sets preserved intact?
- Do JSON constraints/functions compile?
- Are `BLOB`s read/written with exact byte sizes?
- Does the JDBC driver return the expected Java types?

H2 may support similar types, but it does not prove locator behavior, streaming, conversion, or performance match Oracle.

## 13. Schema migrations: Flyway or Liquibase

If the production schema is built with Flyway or Liquibase, Oracle integration tests must execute those exact migrations.

Flyway example:

~~~yaml
spring:
  flyway:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
~~~

With this approach:

1. The test database starts in a clean state.
2. Flyway runs the migrations.
3. Hibernate validates entity mappings against the generated schema.
4. Tests execute repositories/services against real Oracle.
5. Test data is rolled back or cleaned up according to a dedicated strategy.

Do not use `ddl-auto: create-drop` as a substitute for production migrations when the goal is verifying migrations. Hibernate DDL can generate a schema that differs from Flyway/Liquibase scripts.

### Do not let test and production migrations drift

Migrations must be version-controlled and executed identically across CI/staging/production. Do not maintain a separate H2 schema with simplified DDL and treat it as proof that Oracle migrations are valid.

If a project maintains separate migrations per database, create a test suite for each dialect/engine. If only Oracle is supported, make Oracle the standard engine for integration tests.

## 14. Configuring Spring Boot tests to use real Oracle

You can run integration tests against a dedicated test Oracle database, such as an ephemeral container database or a dedicated provisioned test database.

Test configuration example:

~~~yaml
spring:
  datasource:
    url: ${ORACLE_TEST_JDBC_URL}
    username: ${ORACLE_TEST_USERNAME}
    password: ${ORACLE_TEST_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
  jpa:
    hibernate:
      ddl-auto: validate
    open-in-view: false
  flyway:
    enabled: true
~~~

The values above are placeholders supplied from CI secrets or secure local configuration. Never write real passwords into repositories, test logs, or committed YAML files. In real configurations, use Spring's property placeholder/environment binding mechanisms.

### Preventing Spring from replacing the DataSource with H2

`@DataJpaTest` may automatically configure an embedded database if H2 is on the classpath. When testing against real Oracle, disable this replacement behavior:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class OrderRepositoryOracleTest {
    // Repository tests use the configured Oracle DataSource.
}
~~~

Without `Replace.NONE`, tests might silently run against H2 even when the test profile declares Oracle. Verify the JDBC URL in the test context or startup logs.

### Integration tests with Spring Boot

~~~java
@SpringBootTest
@ActiveProfiles("oracle-test")
class OrderServiceOracleIT {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void persistsOrderUsingOracleSchema() {
        Long id = orderService.createOrder("ORD-1001");

        Order stored = orderRepository.findById(id)
            .orElseThrow();

        assertThat(stored.getOrderCode()).isEqualTo("ORD-1001");
    }
}
~~~

This test verifies the service/repository against the Oracle `DataSource` configured by the profile. Ensure the profile does not fall back to H2 when environment variables are missing.

## 15. Using Testcontainers to run Oracle in CI

Testcontainers can spin up a database container within the test lifecycle, giving each CI run a more independent environment. For Oracle, select an authorized Oracle Database image, an appropriate version, and a compatible Testcontainers module.

A common option for testing is an Oracle XE image or Oracle Database Free image. The image, version, environment variables, license/terms, and feature limits must be verified from the image/provider and Oracle documentation before use. XE/Free have edition limits and do not fully substitute for Enterprise Edition production.

### Illustrative dependencies

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>oracle-xe</artifactId>
    <scope>test</scope>
</dependency>
~~~

Versions are managed by a Testcontainers BOM compatible with the project's JDK and Spring Boot versions. Artifacts/modules and container classes can change across Testcontainers releases; check the documentation for the version in use before copying code.

### Test template with OracleContainer

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.OracleContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OracleDatabaseIntegrationTest {

    @Container
    static final OracleContainer ORACLE =
        new OracleContainer("gvenzl/oracle-xe:21-slim-faststart");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", ORACLE::getJdbcUrl);
        registry.add("spring.datasource.username", ORACLE::getUsername);
        registry.add("spring.datasource.password", ORACLE::getPassword);
    }

    @Test
    void applicationConnectsToOracle() {
        // Execute repository/service assertions against Oracle.
    }
}
~~~

This is an illustrative template based on the `OracleContainer` API typically provided by the Testcontainers Oracle XE module and corresponding image. Pin the image tag and Testcontainers version, and check classes/APIs against actual dependencies. Do not use the `latest` tag in CI because the engine can change without any source code changes.

If the CI environment prohibits Docker-in-Docker or lacks a Docker socket, use a dedicated provisioned Oracle test database and pass URLs/credentials via secrets.

### Testcontainers and schemas

Once the container is ready:

1. Create the application user/schema.
2. Create tablespaces or configure quotas if required by migrations.
3. Run Flyway/Liquibase.
4. Execute tests.
5. Destroy the container after tests.

A fresh container isolates the database across pipelines, but it does not automatically make parallel tests safe if multiple test classes share the same container/schema.

## 16. Using Oracle Free/XE and edition limits

Oracle XE or Oracle Database Free can be helpful for running local and CI integration tests at low or zero cost under product terms. However:

- Resource and feature limits apply by edition.
- Several Enterprise or HA options are unavailable.
- RAC/FAN/FCF behavior cannot be validated with a single standalone XE instance.
- Partitioning, advanced security, Data Guard, or other features may lack parity with production.
- Storage, memory, character set, and parameter configurations may differ.

If production uses Enterprise Edition with RAC, Oracle Free/XE tests still validate basic SQL, migrations, JPA mappings, and JDBC behavior, but they do not prove RAC failover or all production options.

For edition-specific features, test on an environment where the corresponding features are licensed and configured.

## 17. Separate test profiles and avoiding H2 fallback

Separate configurations clearly:

- `application.yml`: default environment-agnostic settings.
- `application-test.yml`: H2 if used for simple unit/repository tests.
- `application-oracle-test.yml`: Oracle test database.

Example:

~~~yaml
spring:
  datasource:
    url: ${ORACLE_TEST_JDBC_URL}
    username: ${ORACLE_TEST_USERNAME}
    password: ${ORACLE_TEST_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
~~~

Activate the profile:

~~~java
@ActiveProfiles("oracle-test")
~~~

Add guards so Oracle tests fail explicitly when URL/credentials are missing rather than silently falling back to H2. An integration test labeled Oracle that accidentally runs on H2 creates a false sense of security.

You can assert the database product in a test:

~~~java
@Autowired
DataSource dataSource;

@Test
void testUsesOracleDatabase() throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        String product =
            connection.getMetaData().getDatabaseProductName();

        assertThat(product).containsIgnoringCase("Oracle");
    }
}
~~~

This is a simple guard to confirm that the test is running against the right engine.

## 18. Testing repositories on real Oracle

A repository test should verify both SQL and mapping:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@ActiveProfiles("oracle-test")
class CustomerRepositoryOracleTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerByNormalizedCode() {
        Customer customer = new Customer();
        customer.setCustomerCode("CUS-001");
        customer.setCustomerName("Acme");
        repository.saveAndFlush(customer);

        Optional<Customer> found =
            repository.findByCustomerCode("CUS-001");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().getCustomerName())
            .isEqualTo("Acme");
    }
}
~~~

`saveAndFlush()` forces Hibernate to send SQL to the database immediately during the test, catching constraint/type/SQL errors earlier than calling `save()` alone. However, tests should read back after flushing and clearing the persistence context to avoid merely retrieving the entity still cached in the persistence context.

Example:

~~~java
repository.saveAndFlush(customer);
entityManager.clear();

Customer stored = repository.findById(customer.getId())
    .orElseThrow();
~~~

When testing a native query, call the exact repository method containing the native SQL against Oracle; do not swap in an alternative query meant only for H2.

## 19. Testing DDL migrations

Migrations should run on real Oracle from a clean database state. Example:

~~~text
V1__create_customer.sql
V2__add_customer_status.sql
V3__create_customer_search_index.sql
~~~

Tests should verify:

- Migrations run in the right order.
- Objects are created in the right schema.
- Data types, precision, and scale are accurate.
- Constraints and indexes are created.
- Sequences/identities match entity mappings.
- Views, triggers, and packages compile.
- Migrations can upgrade from the previous schema version.
- Failed migrations produce clear logs and do not leave the database in an ambiguous state.

With Oracle, implicit DDL commits make rollback behavior differ from H2. If a migration fails partway through, do not assume all prior DDL was rolled back. Flyway/Liquibase have their own tracking and behavior; inspect migration state and establish a recovery procedure.

Do not modify migrations already applied to shared environments. Create a new migration to fix the schema.

## 20. Test data and cleanup

Test data must be reproducible and independent of test execution order.

Common approaches:

- `@Sql` to load fixture data.
- Java builders/factories to construct entities.
- Flyway migrations creating only schemas and immutable reference data.
- Transaction rollback for tests performing only DML changes.
- Deleting data by test run ID or dedicated schema.
- Creating dedicated schemas/containers per worker during parallel execution.

### Transaction rollback

`@DataJpaTest` typically runs inside a transaction and rolls back after each test. This works well for DML, but it does not undo Oracle DDL. Sequence values are also not reverted when a transaction rolls back.

Do not assert that sequences always start at 1 or have no gaps. If tests depend on fixed IDs, seed data with explicit IDs in fixtures or query the generated ID.

### TRUNCATE is not transactional cleanup

Oracle `TRUNCATE TABLE` is DDL and triggers an implicit commit. Do not use `TRUNCATE` inside a test transaction expecting rollback to restore the data.

If using cleanup scripts:

- Run them against an isolated schema/database.
- Account for foreign key dependencies.
- Execute them outside test transactions or per a clear lifecycle.
- Never point test cleanup at production.

## 21. Testing transaction rollback and propagation

Test these scenarios on real Oracle:

- Runtime exceptions triggering rollback.
- Checked exceptions per configured rollback rules.
- `REQUIRES_NEW` committing independently.
- `NESTED` if the transaction manager/driver supports the semantics properly.
- Constraint violations.
- Deadlocks or lock timeouts.
- Transactions updating multiple tables.

Example:

~~~java
@Test
void rollsBackOrderWhenAuditInsertFails() {
    assertThatThrownBy(() ->
        orderService.createOrderWithAudit("ORD-ROLLBACK")
    ).isInstanceOf(RuntimeException.class);

    assertThat(orderRepository.existsByOrderCode("ORD-ROLLBACK"))
        .isFalse();
}
~~~

The test method itself may be executing inside the test framework's transaction. When a service uses different propagation modes, understand which transaction is committed/rolled back and inspect data using an independent connection/context when necessary.

A test that only asserts an exception does not prove data was rolled back. Read back from the database after the transaction ends.

## 22. Testing locking and race conditions

If the application involves reservations, payments, inventory allocation, or queue processing, test concurrency against real Oracle.

Locking SQL example:

~~~sql
SELECT inventory_id,
       available_quantity
  FROM inventory
 WHERE inventory_id = :id
 FOR UPDATE;
~~~

Tests should create two independent transactions:

1. Transaction A locks the row.
2. Transaction B attempts to update the same row.
3. Verify B waits, times out, or receives an error per configuration.
4. A commits/rolls back.
5. Verify B proceeds or fails per expected behavior.

Never share the same `EntityManager` or `Connection` across two threads. Each transaction requires its own resources.

With `SKIP LOCKED` tests, verify two workers never claim the same record. With unique constraints, verify one of two competing inserts is rejected or retried according to rules.

## 23. Testing native SQL and Hibernate dialect

The Hibernate dialect governs SQL generated for pagination, sequences, identity, locking, and certain functions. Hibernate/Spring Boot versions can change dialect classes and SQL generation.

In modern Hibernate, the Oracle dialect is typically auto-detected from JDBC metadata. If explicit declaration is needed, use the dialect matching the active Hibernate version rather than copying legacy classes like `Oracle12cDialect` if the current version has changed.

Verify:

- SQL pagination.
- Sequence generation.
- `SELECT FOR UPDATE`.
- Bulk updates/deletes.
- `RETURNING` or generated keys if used by the application.
- Native queries with hints.
- Oracle-specific functions and operators.

Enable SQL logging in tests when investigating:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Bind logging can expose sensitive data. Enable it only temporarily in test environments and never write credentials/PII to CI logs.

## 24. Testing realistic privileges

Testing with a DBA user can mask privilege errors. Create application schemas/users and integration accounts mirroring production:

- The application runtime user holds only necessary privileges.
- The migration user holds DDL privileges per a dedicated process.
- The application runtime user does not need table creation privileges if migrations run under a separate user.
- Read-only integration users can only read required views.
- Never use `SYS`, `SYSTEM`, or the `DBA` role for normal application tests.

A common setup:

| User | Role |
|---|---|
| `APP_OWNER` | Owns tables, sequences, views, and packages |
| `APP_MIGRATOR` | Runs migrations during deployment windows |
| `APP_RUNTIME` | Holds DML/EXECUTE privileges required by the application |
| `APP_TEST_READER` | Reads views/APIs for integration test verification |

Depending on deployment style, owner and runtime users may be combined, but tests should reflect the actual production model to catch privilege failures.

## 25. Checking character sets and Unicode

H2 and Oracle can differ in encoding, collation, and string comparison. Oracle databases have both a database character set and a national character set. Check:

~~~sql
SELECT parameter,
       value
  FROM nls_database_parameters
 WHERE parameter IN (
   'NLS_CHARACTERSET',
   'NLS_NCHAR_CHARACTERSET'
 );
~~~

Test with:

- Vietnamese diacritics.
- Unicode combining characters.
- Emojis if supported by the system.
- Characters outside the Basic Multilingual Plane.
- Strings near column length limits.
- Case-insensitive comparisons if required by business logic.

Do not assume `VARCHAR2` and `NVARCHAR2` have identical byte/character limits or identical semantics. Choose column types based on the database character set and data requirements.

## 26. Testing datetimes and NLS session settings

Oracle sessions can have varying NLS settings. Tests running solely under a default session may miss implicit conversion bugs.

Inspect session settings:

~~~sql
SELECT parameter,
       value
  FROM nls_session_parameters
 ORDER BY parameter;
~~~

Scenarios to test:

- Different date formats.
- Different decimal separators.
- Session timezone differing from database timezone.
- Daylight saving transitions.
- Timestamps with fractional seconds.
- `TIMESTAMP WITH LOCAL TIME ZONE` read across two different session timezones.

Prefer typed bind parameters over converting dates/numbers into strings and concatenating them into SQL.

## 27. Performance testing and resource limits

Functional integration tests with Oracle Free/XE validate correctness, but they do not represent production performance. Editions, CPU, memory, storage, concurrency, and database settings differ.

Performance tests should use a near-production environment:

- Same major Oracle version and compatible patch level.
- Same storage type or equivalent I/O characteristics.
- Same connection pool and JDBC driver.
- Sanitized/masked data with realistic distribution and volume.
- Concurrency and think time close to real workloads.
- Separate warm-up and measurement phases.

Do not benchmark on a single container and extrapolate optimal connection counts for production RAC.

## 28. CI pipeline for Oracle integration tests

A typical pipeline:

~~~text
Compile
  |
  v
Unit tests
  |
  v
Build application
  |
  v
Start disposable Oracle
  |
  v
Create application schema
  |
  v
Run Flyway/Liquibase migrations
  |
  v
Run Oracle integration tests
  |
  v
Collect logs and test reports
  |
  v
Destroy disposable database
~~~

Principles:

- Pin Oracle image tags and dependency versions.
- Never use the `latest` tag.
- Wait for the database to actually be ready, not just container running state.
- Use appropriate healthchecks or wait strategies.
- Give each CI run an isolated database/schema.
- Never use unmasked production data.
- Preserve startup logs, migration logs, and Oracle alert logs on test failure.
- Limit concurrent Oracle jobs according to CI runner resources.
- Clean up containers/volumes after job completion.

If Oracle startup takes too long, you can reuse a service container within a single CI job or use a managed test database. In return, enforce data cleanup and isolation across pipelines.

## 29. Test layering in a Spring Boot project

You do not need to run the entire test suite on Oracle if tests only check pure Java logic. A sound structure:

| Test group | Tools | Objective |
|---|---|---|
| Unit | JUnit, Mockito | Business logic, validation, pure mappings |
| Web slice | `@WebMvcTest` | Controllers, serialization, HTTP contracts |
| Fast repository slice | H2 if queries are portable | Basic tests, fast feedback |
| Oracle repository | Oracle Testcontainers/test DB | SQL, mappings, constraints, sequences, and dialect |
| Service integration | Oracle + Spring context | Transactions, JPA, JDBC, and migrations |
| End-to-end | Integration environment | Service wiring, queues, APIs, and workflows |
| Performance/concurrency | Near-production Oracle | Throughput, locks, pools, query plans |

If a project relies heavily on native queries or PL/SQL, the proportion of Oracle tests must be large enough to cover engine-dependent components. H2 can still serve as fast feedback for portable parts.

## 30. Common errors when migrating tests from H2 to Oracle

| Error | Possible cause | How to investigate |
|---|---|---|
| `ORA-00904` invalid identifier | Column name, case, alias, or SQL dialect | Inspect generated SQL, check data dictionary |
| `ORA-00933` SQL command not properly ended | Invalid Oracle SQL syntax | Look for `LIMIT`, quoting, or engine-specific syntax |
| `ORA-00942` table or view does not exist | Wrong schema, missing grant, object not created | Check user, schema, synonyms, and migrations |
| `ORA-01400` cannot insert `NULL` | Entity missing value or empty string became `NULL` | Check mapping, validation, and data |
| `ORA-00001` unique constraint violated | Duplicate sequence/ID or data | Check generator, seed, and constraints |
| `ORA-02291` parent key not found | Missing parent row or insert order | Check fixtures, cascades, and FKs |
| `ORA-02292` child record found | Deleting parent while child exists | Check cleanup order and cascades |
| `ORA-01861` literal does not match format string | Date string/implicit conversion | Use bind parameters or explicit formats |
| `ORA-01555` snapshot too old | Insufficient undo for long queries/exports | Check undo retention and transaction duration |
| `ORA-00054` resource busy | Lock/DDL contention | Check transactions, lock timeouts, and parallel tests |

Do not fix errors by relaxing privileges or dropping constraints before understanding the root cause. A passing H2 test is not proof that the Oracle schema is correct.

## 31. Example of inspecting generated SQL and Oracle results

When a repository query fails:

1. Enable Hibernate SQL logging in the test profile.
2. Record bind types/values in a safe test environment.
3. Run the corresponding SQL directly against test Oracle.
4. Verify current schema, service, NLS, and privileges.
5. Inspect the execution plan if the query runs but is slow.
6. Fix the query or mapping at the proper layer.
7. Retain the Oracle integration test to prevent regressions.

Never replace an Oracle query with an H2-only query inside the same test method. If both engines are needed, split test contracts by profile and explicitly document what is portable versus database-specific.

## 32. Oracle integration testing checklist

### Environment

- [ ] Verified JDBC URL points to the right Oracle service/PDB.
- [ ] Tests do not silently fall back to H2.
- [ ] Oracle image/database version pinned.
- [ ] Dedicated test schema/user used.
- [ ] No unmasked production data used.
- [ ] Database product/version logged when tests start.

### Schema and migrations

- [ ] Flyway/Liquibase migrations run on Oracle.
- [ ] `ddl-auto=validate` used when migrations are the schema source of truth.
- [ ] Data types, precision, scale, and nullability verified.
- [ ] Sequences/identities and allocation sizes verified.
- [ ] Indexes, constraints, triggers, views, and PL/SQL verified.
- [ ] Migration failure/recovery behavior verified.

### Repositories and transactions

- [ ] Native SQL and pagination tested.
- [ ] Empty string/`NULL` behavior tested.
- [ ] `DATE`/`TIMESTAMP`/timezone handling tested.
- [ ] LOB/Unicode/`NUMBER` tested where applicable.
- [ ] Rollback, propagation, and constraint errors tested.
- [ ] Locking/concurrency tested for critical business flows.
- [ ] Tested with a runtime user holding production-like privileges.

### CI and operations

- [ ] Waited for Oracle readiness before running migrations.
- [ ] Databases/schemas isolated across pipelines.
- [ ] Migration, Hibernate, and Oracle logs collected on failure.
- [ ] Containers/volumes cleaned up per lifecycle.
- [ ] Functional tests separated from performance tests.
- [ ] XE/Free not treated as proof for RAC or production options.

## 33. Conclusion

H2 with Oracle mode is helpful for fast feedback, but it only emulates a subset of syntax and behavior. Oracle differs significantly in empty strings/`NULL`, identifiers, `DATE`/`TIMESTAMP`, `NUMBER`, sequences, PL/SQL, native SQL, implicit DDL commits, transaction isolation, and locking. These differences can let H2 tests pass while the application fails in production.

For Spring Boot/JPA, keep unit tests fast, use H2 for portable SQL, and add integration tests on real Oracle for migrations, repositories, native queries, transactions, sequences, privileges, and concurrency. Oracle Testcontainers or an isolated test database can provide repeatable environments; pin versions, run proper Flyway/Liquibase migrations, and prevent H2 fallbacks. Use Oracle Free/XE for core engine checks, but test RAC, Active Data Guard, or production-specific options on matching environments.

When tests fail, inspect generated SQL, bind types, schemas, services, NLS settings, privileges, and Oracle error codes. The goal is to prove the application works on the actual engine production runs, not merely on a syntactically similar database.
