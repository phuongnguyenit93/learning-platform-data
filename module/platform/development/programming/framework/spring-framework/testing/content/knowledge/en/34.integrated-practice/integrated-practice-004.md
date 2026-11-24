# Testing a Real Repository with SQL and Data Constraints

A repository is the boundary between application logic and the database. A unit test using a mock repository can verify that a service calls the right method, but it does not prove that the SQL executes properly, entity mappings are accurate, transactions work, or the database enforces data constraints.

When testing a real repository, tests need to run against a database engine and schema whose behavior closely matches the application environment. The test performs save, query, update, and delete operations through the real repository, then verifies the results processed by the database. For requirements depending on SQL or a specific dialect, use the same database type as production, typically via Testcontainers.

## 1. How Does a Real Repository Differ from a Mock Repository?

A mock repository only simulates results declared by the test. It does not execute SQL and does not check the database:

```java
given(customerRepository.findByEmail("mai@example.test"))
    .willReturn(Optional.of(customer));
```

A mock-based snippet may be appropriate when testing a service, yet it does not prove:

- Derived queries or `@Query` generate valid SQL.
- Mappings between entities and database columns are accurate.
- Joins, sorting, pagination, and native queries work with the real dialect.
- Unique, foreign key, check constraints, and `NOT NULL` are enforced by the database.
- Transactions commit and roll back as designed.
- Migrations create a schema compatible with the current code.

A repository integration test uses the minimal Spring context needed along with a real database. It tests the contract across the repository, ORM/JDBC layer, SQL, and schema.

## 2. Choosing the Appropriate Test Slice

Spring Boot provides test slices to load only the necessary infrastructure:

| Annotation | Configured Components | Use Case |
|---|---|---|
| `@DataJpaTest` | JPA repositories, entity scanning, `EntityManager`, and JPA infrastructure | Testing Spring Data JPA repositories and ORM mappings |
| `@DataJdbcTest` | Spring Data JDBC repositories and related JDBC infrastructure | Testing repositories using Spring Data JDBC |
| `@JdbcTest` | `DataSource`, `JdbcTemplate`, and transaction support | Testing DAO/JDBC code or direct SQL statements |
| `@SpringBootTest` | Broader application context, depending on configuration | Testing repositories together with services, transactions, or integrated app config |

Test slices typically run in a transaction and roll back after each test method. This is a fast way to keep the database clean, though you still need to watch out for operations that commit independently or run from another thread.

Example JPA repository:

```java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
```

With plain JDBC, you can inject `JdbcTemplate` into a DAO and use `@JdbcTest`. If the DAO is an application-defined component, use `@Import(CustomerJdbcRepository.class)` to include it in the test slice.

## 3. Using the Same Database Type as Production

An embedded database like H2 can run fast, but it does not guarantee full compatibility with PostgreSQL, MySQL, SQL Server, or Oracle. SQL syntax, data types, collations, sequences, JSON support, locking, and constraint behavior can all differ.

If the production application runs PostgreSQL, prefer running repository tests on PostgreSQL. Testcontainers starts the database in a container and supplies connection details to the Spring test context.

With Spring Boot 3.1 and later, `@ServiceConnection` can automatically supply connection details from the container. Example Gradle dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    runtimeOnly 'org.postgresql:postgresql'
}
```

To let Boot manage aligned versions, use Spring Boot dependency management or the project's BOM.

Example JPA slice test with PostgreSQL:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=validate")
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class CustomerRepositoryTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private CustomerRepository customerRepository;
}
```

`@AutoConfigureTestDatabase(replace = NONE)` tells Spring Boot not to replace the container database with an embedded database. `@ServiceConnection` supplies JDBC connection details from the container. `@DataJpaTest` loads the repositories and JPA infrastructure needed for the test.

With Spring Boot versions older than 3.1, you can use `@DynamicPropertySource` to register the URL, username, and password from the container:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

When using `@DynamicPropertySource`, remember to import `DynamicPropertyRegistry` and `DynamicPropertySource` from `org.springframework.test.context`. The container must be started before Spring creates the datasource.

## 4. Testing Schemas Created by Migrations

In production, schemas are commonly managed by Flyway or Liquibase. If tests merely let Hibernate auto-generate tables from entities, they may miss migration errors or discrepancies between the test schema and production schema.

A production-like testing approach is:

1. Start a database using the same engine as production.
2. Run the application's real migrations.
3. Set Hibernate to `validate` mode to check entity mappings against the existing schema.
4. Execute repository operations and verify the results.

Example Flyway migration creating customer and order tables:

```sql
CREATE TABLE customer (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    CONSTRAINT uk_customer_email UNIQUE (email),
    CONSTRAINT ck_customer_email_not_blank
        CHECK (length(trim(email)) > 0)
);

CREATE TABLE purchase_order (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    CONSTRAINT uk_purchase_order_number UNIQUE (order_number),
    CONSTRAINT ck_purchase_order_amount CHECK (amount >= 0),
    CONSTRAINT fk_purchase_order_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
```

Place the migration file according to Flyway conventions, e.g., `src/main/resources/db/migration/V1__create_customer_and_order.sql`. When the test context starts, Boot auto-configures Flyway if the dependency and migration configuration are present in the application. `spring.jpa.hibernate.ddl-auto=validate` catches mappings incompatible with the migrated schema.

Do not enable `ddl-auto=create` or `create-drop` in migration tests if the goal is to verify production DDL. If Hibernate recreates the tables itself, the test may not run against the schema produced by migrations.

## 5. Verifying Database Writes and Reads

A basic repository test should prove that data was written to the database and can be queried back. With JPA, `save(...)` may only place the entity into the persistence context; SQL might not run immediately. `flush()` forces Hibernate to synchronize pending changes to the database.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@Autowired
private CustomerRepository customerRepository;

@Autowired
private TestEntityManager entityManager;

@Test
void savesAndReloadsCustomer() {
    String email = "customer-" + UUID.randomUUID() + "@example.test";

    Customer saved = customerRepository.save(new Customer(email, "Mai"));

    entityManager.flush();
    entityManager.clear();

    Customer reloaded = customerRepository.findById(saved.getId())
        .orElseThrow();

    assertThat(reloaded.getEmail()).isEqualTo(email);
    assertThat(reloaded.getDisplayName()).isEqualTo("Mai");
}
```

`flush()` forces the SQL insert/update to be sent to the database. `clear()` detaches entities from the persistence context; the next query must read the data back instead of merely returning the managed in-memory object. This helps the test avoid only asserting in-memory state.

When using Spring Data JDBC or plain JDBC, repository operations generally execute SQL immediately upon invocation; there is no JPA persistence context to flush/clear. Write assertions matching the semantics of the technology in use.

## 6. Testing Derived Queries, @Query, and Native SQL

Repository methods can have queries generated by Spring Data from method names or declared with `@Query`. Tests should verify filter conditions and actual data, especially for joins, sorting, paging, and dialect-dependent SQL expressions.

Example derived queries:

```java
Optional<Customer> findByEmail(String email);

List<Customer> findByDisplayNameContainingIgnoreCaseOrderByDisplayNameAsc(
    String keyword
);
```

Example JPQL and native queries:

```java
@Query("select c from Customer c where lower(c.email) = lower(:email)")
Optional<Customer> findByEmailCaseInsensitive(String email);

@Query(value = "select count(*) from customer where email like :pattern",
       nativeQuery = true)
long countByEmailPattern(@Param("pattern") String pattern);
```

Tests should create data with clearly distinguishable outcomes:

```java
@Test
void findsCustomersByCaseInsensitiveEmail() {
    String email = "Mai-" + UUID.randomUUID() + "@example.test";
    customerRepository.saveAndFlush(new Customer(email, "Mai"));

    Customer found = customerRepository
        .findByEmailCaseInsensitive(email.toUpperCase(Locale.ROOT))
        .orElseThrow();

    assertThat(found.getEmail()).isEqualTo(email);
}
```

For native SQL, running on the real database engine catches incompatible syntax, table/column names, data types, and functions. When queries use pagination, check page contents, total record count, and ordering; test data should include enough records to distinguish between pages.

## 7. Testing Unique Constraints

Unique constraints must be enforced by the database. Testing only an application-layer validator does not prove the real schema has the constraint.

Suppose `customer.email` has constraint `uk_customer_email`. A test can save the first record and then attempt to save a duplicate email:

```java
import org.springframework.dao.DataIntegrityViolationException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void databaseRejectsDuplicateCustomerEmail() {
    String email = "unique-" + UUID.randomUUID() + "@example.test";

    customerRepository.saveAndFlush(new Customer(email, "First"));

    assertThatThrownBy(() ->
        customerRepository.saveAndFlush(new Customer(email, "Duplicate"))
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

`saveAndFlush(...)` forces the second insert to execute immediately so the test observes the constraint error inside the method. Calling only `save(...)` might defer the exception until transaction flush or commit, causing the test to miss it at the assertion point.

With `@DataJpaTest`, each test method usually runs in a transaction rolled back at the end. After a constraint violation on flush, the current transaction may be in a rollback-only state; do not continue using that transaction for further queries. Let the test finish so Spring rolls back the transaction.

## 8. Testing Foreign Keys and Check Constraints

Foreign keys ensure child records reference an existing parent record. Check constraints ensure values satisfy a SQL expression. These are rules at the database layer, so tests should verify that the database rejects invalid data.

Example using `JdbcTemplate` to intentionally insert an order pointing to a non-existent customer:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Autowired
private JdbcTemplate jdbcTemplate;

@Test
void databaseRejectsOrderWithMissingCustomer() {
    String orderNumber = "PO-" + UUID.randomUUID();

    assertThatThrownBy(() -> jdbcTemplate.update("""
        INSERT INTO purchase_order(customer_id, order_number, amount)
        VALUES (?, ?, ?)
        """, -999L, orderNumber, new BigDecimal("25.00")))
        .isInstanceOf(DataIntegrityViolationException.class);
}
```

Similarly, a test can try inserting a negative `amount` to verify `ck_purchase_order_amount` works. Using direct SQL here separates database constraint errors from entity validation or pre-save checks.

Not every constraint needs to be tested with direct JDBC. For constraints exercised through repository saves, use the repository if the goal is to verify the full application path. Use direct JDBC when you want to prove the database itself rejects the data regardless of the ORM or validation layer.

## 9. SQL Fixtures with @Sql

Spring Test supports `@Sql` to run scripts before or after a test method. This is useful when a test needs a clear SQL dataset or needs to verify queries against a structured fixture.

Example script `src/test/resources/sql/customer-fixture.sql`:

```sql
INSERT INTO customer (email, display_name)
VALUES ('fixture-398@example.test', 'Fixture Customer');
```

Registering the script:

```java
import org.springframework.test.context.jdbc.Sql;

@Test
@Sql("/sql/customer-fixture.sql")
void findsFixtureCustomer() {
    Customer found = customerRepository
        .findByEmail("fixture-398@example.test")
        .orElseThrow();

    assertThat(found.getDisplayName()).isEqualTo("Fixture Customer");
}
```

With `@DataJpaTest`'s default transactional tests, a `BEFORE_TEST_METHOD` script normally runs inside the test transaction and the data is rolled back after the method. If the test is non-transactional or the script is configured to run in an independent transaction, design cleanup accordingly.

You can specify the phase explicitly:

```java
@Sql(
    scripts = "/sql/customer-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
```

If using a fixture with fixed IDs or unique keys, do not run that same fixture concurrently on a shared database if transactions can see each other and conflict on data. For parallel tests, prefer data with unique identifiers or separate databases/schemas. Avoid cleanup scripts like `DELETE FROM customer` on a database being used by other tests.

## 10. Transactions, Flushing, and Rollback in Repository Tests

`@DataJpaTest`, `@DataJdbcTest`, and `@JdbcTest` are typically configured to run each test method in a transaction and roll back on completion. This keeps tests independent without manually cleaning up every record.

However, rollback does not replace understanding transaction boundaries:

- JPA may defer SQL until flush or commit. Use `flush()` to surface constraint and SQL errors in the test.
- Managed entities may be returned from the persistence context. Use `clear()` when you need to verify data is re-read from the database.
- `REQUIRES_NEW` may commit a transaction independently of the test's transaction.
- Requests sent to a `RANDOM_PORT` server run on separate server threads, outside the test method's transaction.
- `@Async` tasks, schedulers, or message consumers also do not automatically join the test's transaction.
- Data written by external processes is not rolled back by the test transaction.

If a test needs to verify that data committed and is visible to another transaction, design a dedicated test for that transaction boundary. You can use `@Commit` or `TestTransaction.flagForCommit()` when a commit is genuinely needed, but ensure explicit cleanup and avoid sharing fixed data.

## 11. Direct JDBC Testing

For repositories using `JdbcTemplate`, `@JdbcTest` creates a lean slice containing `DataSource`, `JdbcTemplate`, and transaction support. You can import the real DAO:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
@Import(CustomerJdbcRepository.class)
class CustomerJdbcRepositoryTests {

    @Autowired
    private CustomerJdbcRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void queriesCustomerUsingSql() {
        jdbcTemplate.update("""
            INSERT INTO customer(email, display_name)
            VALUES (?, ?)
            """, "jdbc-398@example.test", "JDBC Customer");

        Customer customer = repository.findByEmail("jdbc-398@example.test");

        assertThat(customer.displayName()).isEqualTo("JDBC Customer");
    }
}
```

If you need a container database instead of an embedded database, combine `@AutoConfigureTestDatabase(replace = NONE)` and connection details from Testcontainers as in the JPA example. `@JdbcTest` tests SQL code executed via JDBC; it does not auto-scan all components like `@SpringBootTest`.

For Spring Data JDBC repositories, use `@DataJdbcTest` to load repositories and corresponding mappings. If custom converters or additional configuration are needed, bring them into the test slice with `@Import`.

## 12. Testing Database-Dependent Queries and Constraints

Some behaviors cannot be reliably simulated with an embedded database or mocks:

- JSON/JSONB operators and indexes in PostgreSQL.
- Collation, case sensitivity, and database-specific string comparison.
- `TIMESTAMP WITH TIME ZONE`, numeric precision, and rounding behavior.
- Sequences, identity generation, and locking semantics.
- `ON DELETE CASCADE`, deferred constraints, or partial unique indexes.
- Native SQL, CTEs, window functions, and vendor-specific database functions.

For these cases, run tests on the same database type and a version close to production. Let real migrations create the schema, then verify results through the repository or JDBC. Do not write tests assuming a different database behaves identically just because both support SQL.

## 13. Data Isolation and Parallel Test Execution

When multiple repository tests share a single database container, a dedicated container does not automatically isolate each test's data. Each test still needs independent data:

- Use UUIDs or test run IDs for emails, order numbers, and unique keys.
- Delete only records belonging to the current test.
- Avoid truncating shared tables while other tests are running.
- Use a separate schema/database if a test requires destructive resets or migrations.
- Use static fixtures only when the database/schema is isolated or fixtures cannot conflict.
- Do not share mutable singleton state across concurrently running tests.

If a build runs multiple JVMs or CI jobs pointing to the same database, UUIDs in test data prevent identifier collisions but do not protect schema-wide reset operations. When needed, create a dedicated database or schema per build/test run.

## 14. Common Mistakes

| Symptom | Cause to Check |
|---|---|
| Test passes on H2 but fails on the production database | Differences in dialect, data types, native SQL, collation, or constraints |
| Unique constraint only fails when the test ends | SQL was not flushed at the assertion point; use `saveAndFlush()` or `entityManager.flush()` |
| Test reads stale data after an update | Entity is still in the persistence context; call `clear()` and re-read |
| Flyway/Liquibase migrations do not run | Missing dependency, wrong migration location, or test slice does not load migration config |
| Hibernate creates tables itself so migration errors never appear | Test is using `ddl-auto=create/create-drop`; use real migrations and `validate` |
| Test container is still replaced by an embedded database | Missing `@AutoConfigureTestDatabase(replace = NONE)` |
| Foreign key test fails at the ORM layer before hitting the database | Entity relationships or cascades intercept before SQL runs; use JDBC to verify the DB constraint if that is the goal |
| Parallel tests collide on unique keys | Fixed fixtures or identifiers are shared |
| `@Transactional` does not roll back data created by an API call | Request runs on a separate server thread or commits an independent transaction |
| SQL cleanup script deletes another test's data | Cleanup script is not scoped by identifier or namespace |

When debugging, determine which layer the error originates from: repository mapping, SQL execution, database constraint, migration, transaction, or test fixture. Enabling SQL logging or bind parameter logging during investigation can reveal the actual statements; avoid leaving detailed sensitive logging enabled in environments with real data.

## 15. Process for Building a Repository Integration Test

1. Choose the right slice: `@DataJpaTest`, `@DataJdbcTest`, `@JdbcTest`, or `@SpringBootTest`.
2. Use the same database type as production when tests depend on dialect or specific constraints.
3. Start the database with Testcontainers and prevent Boot from substituting an embedded database.
4. Run real migrations and use Hibernate `validate` if the application uses JPA.
5. Create test-specific data or use SQL fixtures in an isolated database/schema.
6. Call the real repository to verify queries, mappings, and results.
7. Use `flush()` to force SQL execution; use `clear()` when you need to re-read from the database.
8. Verify unique, foreign key, check, and `NOT NULL` constraints at the database layer.
9. Understand transaction rollback and handle cleanup for operations that commit or run on other threads/processes.
10. Keep tests independent under parallel execution and verify migrations and SQL on a production-like database.

A reliable repository test must prove that the real SQL and real schema together uphold the data contract. Use test slices to keep the context lean, the same database type as production to verify the dialect, real migrations to validate the schema, and `flush()` to force constraints to execute right at the point under test. That way, tests catch bugs that mock repositories or embedded databases cannot reveal.
