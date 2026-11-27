# Preparing Sample Data and Isolating Test Data

Testing Spring Data Relational R2DBC is only reliable when the database starts from a known state and tests do not mutate data that other tests rely on. Seed data provides baseline records needed for testing; fixtures craft data tailored to each scenario; and isolation strategies ensure a test can run independently, repeatedly, and in parallel without order dependencies.

With R2DBC, test data must also be set up and cleaned up following reactive flows. A query returning a `Mono` or `Flux` only runs when subscribed to. If seed data runs on a detached subscription, the test may begin before data finishes writing. If a test holds a transaction or connection too long, another test may wait on the pool or observe an unexpected state.

This lesson explains how to prepare schemas and sample data, choose between SQL scripts and Java fixtures, use dedicated databases or Testcontainers, isolate data between tests, handle transaction rollbacks in reactive testing, run tests in parallel, and protect production data.

## 1. Seed Data, Fixtures, and Test Data Have Distinct Roles

These terms are often used closely together, yet each has a specific purpose:

- **Schema:** database structure including tables, columns, keys, constraints, indexes, and relationships.
- **Seed data:** initial dataset loaded to create a usable or testable environment.
- **Fixture:** data deliberately prepared for a specific test or test group.
- **Test database:** dedicated database for testing that can be recreated and wiped without affecting other data.
- **Test isolation:** preventing mutations in one test from affecting the outcome of another test.

For example, a test checking order lookup by customer may require:

1. One customer.
2. Two orders belonging to that customer.
3. One order belonging to a different customer to verify the filter condition.
4. Deterministic statuses and timestamps.

Fixtures should clearly express which data supports assertions. There is no need to load thousands of rows for a test verifying a simple query.

A good test environment has three traits:

- **Deterministic:** the same fixtures and code produce predictable results.
- **Repeatable:** running tests repeatedly does not accumulate data or alter outcomes.
- **Isolated:** tests do not depend on data created by other tests or execution order.

## 2. Separating the Test Database from Development and Production

Never share a production database with tests. Tests may insert, update, delete, truncate, or run migrations; a single misconfiguration could wipe real data.

Maintain separate configuration per environment:

~~~text
src/main/resources/
    application.yml
    application-dev.yml
    application-test.yml

src/test/resources/
    schema.sql
    data.sql
    application-test.yml
~~~

Example test configuration:

~~~yaml
spring:
  config:
    activate:
      on-profile: test

  r2dbc:
    url: r2dbc:postgresql://localhost:55432/orders_test
    username: test_user
    password: test_password

  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
      data-locations: classpath:data.sql
      continue-on-error: false
~~~

This example is for PostgreSQL and a Spring Boot version supporting R2DBC script initialization. Adjust URL, driver, and properties for your project's database and Boot version.

Do not place test URLs in default configuration if the application could launch under a production profile. Check active profiles and effective final configuration before running tests.

### 2.1. Using the Test Profile Safely

You can activate the test profile on a test class:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class CustomerRepositoryIntegrationTest {
}
~~~

A profile only selects configuration—it does not guarantee database isolation on its own. If `application-test.yml` accidentally points to a shared or production database, cleanup commands can still affect real data.

Apply additional safeguards:

- Use a dedicated database name like `orders_test`.
- Use a database user granted privileges only on the test database.
- Use containers or ephemeral databases.
- Never place production credentials in test configuration.
- Verify host, database name, and profile before running destructive setup.
- Never use a database dump containing production personal data as a fixture.

## 3. Preparing the Schema with SQL Scripts

Spring Boot can run initialization scripts when the application starts. With R2DBC, script initialization uses the R2DBC-compatible mechanism configured by Spring Boot.

Example `schema.sql`:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Schema scripts should create the exact elements required by the application:

- Tables and columns.
- Primary keys and foreign keys.
- Unique, not-null, and check constraints.
- Indexes required for queries.
- Sequences or ID generation structures if required by the database.
- Views or functions if tests depend on them.

Do not create minimal stripped-down tables just to make tests pass if production relies on critical constraints or indexes. Test schemas should mirror the schema managed by migrations.

### 3.1. Table Creation and Deletion Order

When foreign keys exist, create referenced parent tables first, then dependent child tables. When cleaning up data, delete child tables before parent tables unless using cascade.

Example:

~~~text
CREATE customer
      |
      v
CREATE purchase_order
      |
      v
INSERT customer
      |
      v
INSERT purchase_order
~~~

Cleanup order is usually reversed:

~~~text
DELETE purchase_order
      |
      v
DELETE customer
~~~

If the schema has many relationships, order statements according to the dependency graph. Do not add `ON DELETE CASCADE` solely for test cleanup convenience if production behavior does not want cascading deletes.

### 3.2. Do Not Let Scripts Continue on Unexpected Errors

Configuration:

~~~yaml
spring:
  sql:
    init:
      continue-on-error: false
~~~

halts startup when a script fails. Ignoring errors can let tests run against a partially initialized schema or seed dataset, causing confusing failures in later steps.

## 4. Loading Sample Data with data.sql

Example `data.sql`:

~~~sql
INSERT INTO customer (id, email, full_name)
VALUES
    (1001, 'an@example.test', 'Nguyen An'),
    (1002, 'binh@example.test', 'Tran Binh');

INSERT INTO purchase_order
    (id, customer_id, order_number, status, created_at)
VALUES
    (2001, 1001, 'ORD-TEST-001', 'OPEN', TIMESTAMP '2026-01-10 09:00:00'),
    (2002, 1001, 'ORD-TEST-002', 'CLOSED', TIMESTAMP '2026-01-11 10:00:00'),
    (2003, 1002, 'ORD-TEST-003', 'OPEN', TIMESTAMP '2026-01-12 11:00:00');
~~~

Seed data with fixed IDs and values makes tests easy to read and verify. Emails use a test-reserved domain such as `example.test` to avoid accidentally emailing real addresses.

A good seed dataset usually:

- Is small and easy to understand.
- Covers valid cases and statuses needed for testing.
- Respects foreign keys and unique constraints.
- Uses fixed timestamps independent of the current clock.
- Contains no real secrets, tokens, or personal data.
- Can be reloaded after resetting the database.

### 4.1. Seed Data vs. Per-Test Fixtures

`data.sql` suits baseline data shared across the test suite, such as lookup tables or reference settings. Per-test fixtures should be constructed in the test or a fixture factory to explicitly state the scenario's conditions.

If every test shares a large dataset in `data.sql`, tests easily become coupled to shared state. One test updating or deleting a row can break another test.

Do not use global seed data to replace dedicated per-test fixtures.

## 5. Spring Boot SQL Initialization Configuration

Common properties:

| Property | Purpose |
|---|---|
| `spring.sql.init.mode` | Selects when scripts run: `embedded`, `always`, or `never` |
| `spring.sql.init.schema-locations` | Locations of schema creation scripts |
| `spring.sql.init.data-locations` | Locations of data loading scripts |
| `spring.sql.init.platform` | Platform suffix for database-specific scripts |
| `spring.sql.init.continue-on-error` | Whether to continue when a script fails |
| `spring.sql.init.separator` | Statement delimiter if customization is needed |

Example:

~~~yaml
spring:
  sql:
    init:
      mode: always
      platform: postgresql
      schema-locations: classpath:schema-postgresql.sql
      data-locations: classpath:data-postgresql.sql
      continue-on-error: false
~~~

Verify property names and capabilities for your Spring Boot version. In particular, do not confuse script initialization with Flyway or Liquibase migrations.

### 5.1. When to Use embedded, always, and never Modes?

- `embedded`: runs scripts automatically in embedded database environments per Boot rules.
- `always`: runs scripts even against non-embedded databases.
- `never`: disables script initialization.

In tests using a PostgreSQL container, `always` is typically needed if Spring Boot should load `schema.sql` and `data.sql`. In production managed by a migration tool, you usually do not want simple initialization scripts running on every startup.

Never place `mode: always` in default configuration shared across all profiles if scripts contain `DROP`, `TRUNCATE`, or table-recreation statements. Scope it strictly to the test profile and verify the active configuration.

## 6. Using Migrations Instead of Maintaining a Separate Test Schema

In real projects, schemas are normally managed via Flyway or Liquibase. Tests should verify the application works with the exact schema created by the same migrations production uses.

Example Flyway structure:

~~~text
src/main/resources/db/migration/
    V1__create_customer.sql
    V2__create_purchase_order.sql
    V3__add_order_status_index.sql
~~~

Each migration adds or updates schema versions. The test database starts fresh and runs all migrations to confirm migrations can apply from scratch.

Traditionally, Flyway and Liquibase use JDBC to manage migrations. If the runtime application uses only R2DBC, you may need to add a JDBC driver and migration datasource. These are two distinct connection paths:

~~~text
Application queries
      |
      v
R2DBC driver
      |
      v
Database

Schema migrations
      |
      v
JDBC migration connection
      |
      v
Same database
~~~

Do not assume Flyway will use R2DBC simply because the application defines `spring.r2dbc.*`.

### 6.1. Choosing One Primary Schema Source

Avoid having `schema.sql`, Hibernate DDL auto, and Flyway/Liquibase modify the schema in inconsistent ways.

A common setup:

- The migration tool is the source of truth for the schema.
- Tests run migrations on an empty database.
- Test fixtures only insert data rather than recreating table structures.
- Production runs the same migrations via the deployment workflow.

If using script initialization for an exercise or small application, keep that script consistent across environments and do not run another schema-creating tool concurrently.

## 7. Creating Java Fixtures Per Test

For tests needing varied data, Java fixture factories express intent much better than a massive SQL file.

Simple builder example:

~~~java
public final class CustomerFixtures {

    private CustomerFixtures() {
    }

    public static Customer customer(String email, String name) {
        Customer customer = new Customer();
        customer.setEmail(email);
        customer.setFullName(name);
        return customer;
    }

    public static Customer defaultCustomer() {
        return customer("fixture@example.test", "Fixture Customer");
    }
}
~~~

Fixture factories should provide sensible defaults while allowing tests to override key fields.

Example:

~~~java
@Test
void findsOrdersForCustomer() {
    Customer customer = CustomerFixtures.customer(
            "orders@example.test",
            "Order Test Customer");

    Mono<List<PurchaseOrder>> scenario =
            customerRepository.save(customer)
                    .flatMap(saved ->
                            orderRepository.saveAll(List.of(
                                    OrderFixtures.openOrder(saved.getId()),
                                    OrderFixtures.closedOrder(saved.getId())))
                                    .collectList());

    StepVerifier.create(scenario)
            .assertNext(orders ->
                    assertThat(orders).hasSize(2))
            .verifyComplete();
}
~~~

This example chains customer and order creation inside the same reactive chain. The test does not begin assertions until fixture setup completes.

Fixture factories should avoid hiding too much behavior. When a test verifies a specific state, keep that value visible right in the test.

### 7.1. Using Unique Data Across Tests

If tests run in parallel or share a database, static fixtures like `fixture@example.test` can trigger duplicate key errors.

You can use a unique ID/namespace per test:

~~~java
String email = "customer-" + UUID.randomUUID() + "@example.test";
~~~

Use random values only for fields not tied to fixed assertions, or capture them for assertions. Avoid random timestamps or random business states if they make tests hard to reproduce.

Another option is giving each test its own database/schema so fixed data can be used without collisions.

## 8. Cleaning Up Data After Each Test

Test data must be deleted or the database reset so the next test starts from a known state.

Common strategies:

| Strategy | When Appropriate | Limitations |
|---|---|---|
| Transaction rollback | All test operations run within one transaction | Reactive test transactions need proper setup; independent commits are not rolled back |
| DELETE by fixture/test ID | Test creates a deterministic set of records | Must delete in proper FK order |
| TRUNCATE tables | Dedicated test database where all data can be wiped | Can affect parallel tests sharing the database |
| Fresh database/container | Need strong isolation and clean schema | Higher startup overhead |
| Separate schema | Multiple test suites share one server | Requires managing search paths, privileges, and cleanup |

Example cleanup with SQL:

~~~java
Mono<Void> cleanDatabase() {
    return databaseClient.sql("DELETE FROM purchase_order")
            .then()
            .then(databaseClient.sql("DELETE FROM customer").then());
}
~~~

The snippet illustrates deleting the child table before the parent table. Specific APIs may need adjustment depending on the `DatabaseClient` version; `rowsUpdated()` can be used if you want to check deleted row counts.

Do not delete data by a shared email if multiple tests might create the same email. Use the specific test's ID or namespace for accurate cleanup.

### 8.1. Cleanup Must Be Awaited

Do not do this:

~~~java
@AfterEach
void cleanup() {
    databaseClient.sql("DELETE FROM customer")
            .fetch()
            .rowsUpdated()
            .subscribe();
}
~~~

`subscribe()` launches a detached execution stream. JUnit can start the next test before DELETE finishes.

Instead, use a test lifecycle mechanism supporting reactive completion, or chain cleanup onto the test's publisher. In synchronous JUnit `@AfterEach`, the method does not automatically await a returned `Mono`; never assume returning `Mono<Void>` from a lifecycle method causes JUnit to subscribe.

You can write a test helper returning `Mono<Void>` and chain cleanup at the end of the test publisher, or use an appropriate extension. If blocking is strictly necessary in test infrastructure, do so deliberately at the test boundary—never introduce blocking into reactive application code.

## 9. Isolation with Dedicated Databases and Testcontainers

Testcontainers enables running a real database inside a container for the test lifecycle. This lets tests exercise the real engine and driver instead of relying solely on H2 or mocks.

PostgreSQL container example:

~~~java
@Testcontainers
@DataR2dbcTest
@ActiveProfiles("test")
class CustomerRepositoryTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void configureR2dbc(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://"
                        + postgres.getHost()
                        + ":"
                        + postgres.getMappedPort(5432)
                        + "/"
                        + postgres.getDatabaseName());

        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }
}
~~~

This is an illustrative template; test slice annotations, Testcontainers dependencies, and drivers must match your project's Spring Boot/Spring Data versions. If a test needs the full application context, use `@SpringBootTest` instead of `@DataR2dbcTest`.

Containers supply a real database, yet they do not automatically wipe data between tests if the container is shared. You still need data resets or separate databases/schemas per test.

### 9.1. Container Per Class or Per Test?

- **One container for the whole test suite:** faster startup, but tests share the database and require strict cleanup.
- **One container per class:** isolates classes, with higher startup overhead.
- **One container per test:** strong isolation, but can be very slow in large suites.
- **Separate database/schema inside a shared container:** balances speed and isolation when schema creation/deletion is managed carefully.

When using a shared static container, do not let tests update the same row or truncate the same table concurrently. Parallel tests must use distinct namespaces/databases/schemas or disable parallel execution for tests sharing state.

### 9.2. An R2DBC Connection Is Not a JDBC URL

`PostgreSQLContainer.getJdbcUrl()` returns a JDBC URL like `jdbc:postgresql://...`. R2DBC requires a driver-scheme URL, such as `r2dbc:postgresql://...`.

Never assign a JDBC URL to `spring.r2dbc.url`. Likewise, a Testcontainers JDBC URL used for migrations does not automatically substitute for the runtime R2DBC URL.

## 10. Using @DataR2dbcTest and @SpringBootTest

`@DataR2dbcTest` is suited when testing only repositories, mapping, and required R2DBC configuration. It narrows the application context to persistence components and may configure test transactions/databases depending on the Boot version.

`@SpringBootTest` is suited when tests need services, security, transaction configuration, converters, or broader application context beans.

| Annotation | Scope |
|---|---|
| `@DataR2dbcTest` | Focuses on repositories and persistence |
| `@SpringBootTest` | Initializes the full application context |
| `@Testcontainers` | Manages containers in tests |
| `@ActiveProfiles("test")` | Activates test configuration |
| `@DynamicPropertySource` | Registers dynamic properties from containers |

Do not use `@SpringBootTest` for every repository test if a slice test suffices. A full context boots more slowly and may pull in unrelated services.

Also do not assume `@DataR2dbcTest` automatically loads the right scripts or resets data. Verify initializer settings and explicit cleanup strategies.

## 11. Transaction Rollback in Reactive Tests

In JDBC/imperative tests, `@Transactional` on a test is commonly used to roll back data after each test. With R2DBC, transactions are reactive and propagate through Reactor Context. Do not mechanically carry over assumptions from JDBC.

Verify your Spring Test version and how test methods execute to see whether reactive transactions are supported. A test method returning a `Mono` does not mean JUnit automatically subscribes and awaits it; many tests must use `StepVerifier` to subscribe to and verify the publisher.

### 11.1. Attaching a Transaction to a Publisher

You can use `TransactionalOperator` in tests to control transaction boundaries:

~~~java
Mono<Void> scenario =
        transactionalOperator.transactional(
                customerRepository.save(customer)
                        .flatMap(saved ->
                                orderRepository.save(
                                        OrderFixtures.openOrder(saved.getId())))
                        .then());
~~~

The publisher subscribed via `StepVerifier` executes within the transaction context created by the operator.

If the test must verify data is committed and visible from another connection, do not mark it rollback-only. Let the transaction complete normally, then read it back with an independent operation.

### 11.2. Explicit Rollback with rollback-only

To test temporary data and roll back upon completion, use `execute`:

~~~java
Flux<Long> temporaryInsert =
        transactionalOperator.execute(status ->
                customerRepository.save(customer)
                        .map(Customer::getId)
                        .doOnNext(id -> status.setRollbackOnly()));
~~~

Once the publisher completes, the transaction rolls back. This snippet illustrates marking rollback-only; in an actual test, wait for `StepVerifier` to finish, then verify from another transaction that the record no longer exists.

This only works when repositories participate in the same reactive transaction context. A separately `subscribe()`d publisher or an operation on a different connection factory may sit outside that transaction.

### 11.3. Not Every Change Is Rolled Back

The following may not be undone alongside the test transaction:

- Detached subscribed publishers.
- Operations using a different `ConnectionFactory` or transaction manager.
- Statements committed independently via `REQUIRES_NEW`.
- HTTP calls, emails, published messages, or file writes.
- Databases/drivers with distinct DDL or sequence semantics.

Sequences/identities can keep incrementing after a rollback. Never write tests assuming the next ID always equals a fixed number after rollback.

## 12. Verifying Seed Data Consistency and Fixture Ordering

Fixtures with foreign keys must be created in dependency order:

~~~java
Mono<Customer> customerMono =
        customerRepository.save(CustomerFixtures.defaultCustomer());

Mono<PurchaseOrder> orderMono =
        customerMono.flatMap(customer ->
                orderRepository.save(
                        OrderFixtures.openOrder(customer.getId())));
~~~

When a test needs multiple related rows, use `flatMap` or `then` to chain steps. Never call `subscribe()` on individual repository operations and assume insert ordering.

When creating multiple independent rows, use `saveAll` or `Flux.concat` if order matters. Use `flatMap` for concurrent inserts only when they have no interdependencies and the driver/database handles the workload.

If a test verifies display ordering, set explicit timestamps and sort keys. Never rely on implicit database return order for queries lacking `ORDER BY`.

## 13. Avoiding Reliance on Auto-Generated IDs

A common mistake is inserting fixture records and assuming IDs will always be 1, 2, 3. Sequences can keep advancing across test runs, rollbacks, or differing container lifecycles.

Instead:

- Capture the saved entity and use the ID returned by the database.
- Use a unique natural key if the test needs to query back later.
- Do not rely on sequence resets unless the test explicitly tests sequences.
- If fixed IDs are required, declare explicit IDs in the fixture and ensure the schema permits it.

Example:

~~~java
customerRepository.save(customer)
        .flatMap(saved ->
                orderRepository.findByCustomerId(saved.getId())
                        .collectList());
~~~

Do not use `SELECT MAX(id)` to infer the just-inserted ID. Under concurrent requests, another transaction could allocate a higher ID.

## 14. Isolating Data When Running Tests in Parallel

Parallel tests can expose dependencies hidden during sequential runs:

- Two tests inserting the same fixed email.
- One test truncating a table while another test reads it.
- One test updating a row's status while another asserts on it.
- Test cleanup deleting another test's fixtures.
- A connection pool too small, causing tests to block waiting on each other.
- Shared containers running migrations concurrently.

Solutions:

1. Each test uses a unique namespace for natural keys and cleans up by that namespace.
2. Separate databases or schemas per test class/suite.
3. Use isolated databases/containers when strong isolation is needed.
4. Disable parallel execution for test groups that must share state.
5. Never truncate the entire database in `@AfterEach` if other tests might be running concurrently.
6. Size connection pools and timeouts appropriately for test suite concurrency.

Test names or random IDs work well as namespaces. Keep the namespace in a test variable for accurate cleanup.

## 15. Are H2 or Embedded Databases Sufficient?

Embedded databases can make tests fast, but they cannot replace integration tests with the production database when the application depends on specific dialects or behaviors.

Differences can arise in:

- SQL syntax.
- Data types and precision.
- Identity/sequence behavior.
- Constraints and constraint names.
- Transaction isolation.
- Locking and `SELECT FOR UPDATE`.
- JSON, arrays, enums, or vendor-specific types.
- Aliases, quoting, and case sensitivity.
- DDL transaction semantics.
- R2DBC drivers and mapping converters.

H2 can be used for simple logic tests if SQL and schemas are compatible. Still, maintain integration tests using the exact database/driver production uses to verify real behavior.

Testcontainers runs the real engine in automated environments. Startup costs are higher, yet it eliminates drift between test and production.

## 16. Sample Data for Each Test Category

Not every test needs the same kind of data.

| Test Category | Data to Prepare |
|---|---|
| Derived queries | Several rows matching and not matching filter values |
| Unique constraints | An existing row and a row with a duplicate key |
| Foreign keys | A valid parent row and a nonexistent parent ID |
| Pagination | Multiple rows with distinct sort keys plus tied values |
| Null mapping | A row with a nullable column set to SQL NULL |
| Optimistic locking | Two reads at the same version followed by competing updates |
| Transaction rollback | Pre-transaction data and an intentionally failing operation |
| Auditing | Security context with distinct auditors across insert/update |
| Joins/projections | Related rows plus missing child rows for optional joins |
| Aggregate queries | Data with known counts/totals for exact assertions |

Fixtures should expose boundary conditions. For example, pagination tests need two rows sharing the same `created_at` to confirm `id` acts as a tie-breaker. Foreign key tests need both existing and nonexistent parent cases.

## 17. Reset Schema or Only Reset Data?

These two actions differ:

- **Reset data:** deletes or reloads rows while keeping the schema intact.
- **Reset schema:** drops database structures, then recreates tables, constraints, indexes, and data.

Resetting data is usually enough per test. Resetting the schema fits testing migrations from an empty state or when each test suite gets its own database.

Do not reset the schema after every test unnecessarily. DDL can be slow, acquire locks, and carry varying transaction semantics across databases.

When testing migrations, provision a fresh database, run migrations from scratch, and verify both schema and data. Do not run `schema.sql` in place of migrations if the goal is to test migrations.

## 18. Protecting Real Data and Sensitive Information

Never copy a production database directly into a test environment without proper anonymization and approval workflows.

Test data should use:

- Fake names and emails.
- Test-reserved phone numbers.
- Fake addresses.
- Tokens/secrets without real access capabilities.
- Synthetic payment values.
- IDs and order numbers distinct from real environments.

Never commit production passwords, credentialed connection strings, or dumps containing PII to the repository.

If production-like data distributions are needed for benchmarks, use synthetic data or controlled anonymization pipelines. Never use raw dumps in CI.

## 19. Common Mistakes When Preparing Test Data

| Mistake | Consequence | Resolution |
|---|---|---|
| Sharing production database | Could alter or wipe real data | Use separate databases, limited users, and containers |
| Using test profile without checking URL | Profile may point to the wrong database | Verify host/database before running setup |
| Oversized global seed data | Tests couple to shared state | Keep baseline small; create per-scenario fixtures |
| Inserting fixtures via detached subscription | Tests start before seeding finishes | Chain publishers and await via StepVerifier |
| Cleanup calling subscribe() in @AfterEach | Next test starts before cleanup finishes | Compose cleanup or use proper reactive test lifecycle |
| Deleting parent tables before child tables | Foreign key violations | Clean up in dependency order |
| Asserting fixed sequence IDs | Tests fail as sequences increment | Use save-returned IDs or natural keys |
| Assuming rollback resets sequences | IDs can still increment after rollback | Never depend on sequence values |
| Running parallel tests on shared data | Duplicates, cross-cleanup, or flaky results | Dedicated namespaces, databases, or schemas |
| Treating H2 as proof of prod compatibility | Dialect and driver gaps go unnoticed | Run integration tests with real database |
| Running schema.sql alongside Flyway | Two schema sources can diverge | Choose one authoritative schema source |
| Ignoring script initialization errors | Tests run on missing or broken schemas | Keep continue-on-error=false |
| Using un-anonymized production data | Leaks PII and secrets | Use synthetic/anonymized data |
| Assuming @DirtiesContext wipes the DB | Context reloads while DB data remains | Implement dedicated DB cleanup/reset |
| Assuming @Transactional auto-rolls back all R2DBC ops | Other subscriptions or connections commit independently | Manage reactive transaction context and verify post-test DB state |

## 20. Workflow for Building a Reliable Test Database

A practical workflow:

1. Select an isolated test database, ideally a container or ephemeral instance.
2. Activate test configuration explicitly and verify URL, database name, and user.
3. Choose one authoritative schema source: migration tool or SQL initialization.
4. Create schemas and constraints matching the target environment.
5. Load minimal seed data solely for baseline lookup records.
6. Create per-test fixtures inside reactive chains.
7. Use database-returned IDs or deterministic natural keys.
8. Choose a cleanup strategy: controlled rollback, DELETE by fixture, or database reset.
9. If tests run in parallel, use isolated namespaces, schemas, or databases, or limit parallelism.
10. Ensure cleanup operations finish before the next test starts.
11. Run integration tests against the real database/driver, not embedded databases alone.
12. Ensure tests cannot connect to or write to production.

A repository test can be structured as:

~~~java
@Test
void findsOnlyOpenOrdersForCustomer() {
    Mono<List<PurchaseOrder>> scenario =
            customerRepository.save(
                            CustomerFixtures.defaultCustomer())
                    .flatMap(customer ->
                            orderRepository.saveAll(List.of(
                                            OrderFixtures.openOrder(customer.getId()),
                                            OrderFixtures.closedOrder(customer.getId())))
                                    .thenMany(orderRepository
                                            .findByCustomerIdAndStatus(
                                                    customer.getId(),
                                                    OrderStatus.OPEN))
                                    .collectList());

    StepVerifier.create(scenario)
            .assertNext(orders -> {
                assertThat(orders).hasSize(1);
                assertThat(orders.get(0).getStatus())
                        .isEqualTo(OrderStatus.OPEN);
            })
            .verifyComplete();
}
~~~

This example creates data, queries, and asserts within a single publisher chain. In a test suite sharing a database, cleanup or per-test namespaces are still needed after the test completes.

## 21. Key Takeaways

- Schema, seed data, and fixtures are three distinct parts of the test environment.
- Test data must be deterministic, repeatable, and isolated.
- Always use a dedicated database; never point scripts or cleanup at production.
- Spring Boot can load schema/data scripts for R2DBC using version-appropriate SQL initialization settings.
- Use migrations as the primary schema source if the project manages schemas via Flyway or Liquibase.
- Keep shared seed data minimal; per-test fixtures should clearly express each scenario.
- In reactive tests, chain publishers to await seeding; never subscribe in a detached stream.
- Cleanup must be awaited; synchronous `@AfterEach` does not automatically await a returned Mono.
- Transaction rollback isolates only operations genuinely participating in the same reactive transaction.
- Never assume sequences/identities reset after rollback.
- Parallel tests need dedicated namespaces, schemas, or databases to avoid collisions.
- H2 does not replace integration tests using the actual production database and R2DBC driver.
- `@DirtiesContext` does not wipe database contents.
- Use synthetic or anonymized data; never commit production dumps, credentials, or PII.
- Test schemas, constraints, cleanup, transactions, and concurrency in a production-like environment.
