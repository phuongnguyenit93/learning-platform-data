# Writing Integration Tests with Testcontainers and StepVerifier

Testing R2DBC repositories is only truly meaningful when behavior is verified against a real database and driver. Mocked repositories can check how a service invokes its collaborators, but they cannot catch dialect errors in SQL, broken UUID/JSON/timestamp mappings, schema constraint mismatches, or transactions that fail to roll back as expected.

Testcontainers spins up a real database inside a container for the duration of tests. Spring Boot connects to that container via dynamic configuration, while `StepVerifier` drives subscriptions and asserts reactive signals such as `onNext`, `onComplete`, and `onError`. Combining both tools lets tests verify the entire path from repository/service through the R2DBC driver to the database.

This lesson uses PostgreSQL as an example. The same principles apply to other databases whenever a matching container image and R2DBC driver exist. It covers container setup, Spring test contexts, schemas and migrations, verifying `Mono`/`Flux` signals, reactive transactions, fixtures and cleanup, concurrency, runtime control, and CI execution.

## 1. Why integration test against a real database?

Unit tests can verify mappers and pure Java domain logic. Repository integration tests must verify everything mocks cannot simulate:

- Does Spring Data–generated SQL actually execute on the target database?
- Do table names, column names, schemas, and data types match entity mappings?
- Does the R2DBC driver convert `UUID`, `BigDecimal`, enums, JSON, and timestamps accurately?
- Are generated IDs returned properly?
- Are `UNIQUE`, `FOREIGN KEY`, `NOT NULL`, and `CHECK` constraints enforced as expected?
- Do derived queries, `@Query`, `Criteria`, and `DatabaseClient` work with the real dialect?
- Do transactions commit and roll back across the reactive context?
- Does optimistic locking detect concurrent updates?

An H2-based test can be useful for portable queries, yet it does not prove PostgreSQL `JSONB`, enums, arrays, sequences, or PostgreSQL-specific syntax work. If production runs PostgreSQL, at least a core suite of integration tests should run against real PostgreSQL.

### Role of each tool

| Tool | Responsibility |
| --- | --- |
| Testcontainers | Creates and manages database container lifecycles. |
| JUnit 5 | Manages test lifecycle and assertions. |
| Spring Boot test | Boots the application context or test slice. |
| R2DBC driver | Connects the application to the database over reactive SPI. |
| StepVerifier | Subscribes and verifies `Mono`/`Flux` signals. |
| Flyway/Liquibase or `schema.sql` | Prepares the test schema. |

Testcontainers does not replace Spring Data R2DBC, and `StepVerifier` does not provision databases. Each tool handles a distinct part of integration testing.

## 2. Required dependencies

Example Gradle dependencies for Spring Boot, Reactor Test, and Testcontainers:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")

    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
}
~~~

Spring Boot's test starter provides JUnit Jupiter, AssertJ, and standard Spring testing utilities. Reactor Test supplies `StepVerifier`. Testcontainers provides the JUnit Jupiter and PostgreSQL modules.

Manage Testcontainers versions through your project's BOM or dependency management rather than declaring disconnected versions per module. Ensure versions align with your Java, Spring Boot, and Gradle versions.

If tests run Flyway over JDBC, add Flyway and the PostgreSQL JDBC driver to test runtime dependencies. The R2DBC driver and JDBC driver are separate dependencies:

- The R2DBC driver serves repositories and `DatabaseClient`.
- The JDBC driver serves Flyway/Liquibase when migration tools use JDBC.

Do not add JDBC just so Spring Data R2DBC can connect to the database.

## 3. Starting PostgreSQL with Testcontainers

Testcontainers provides `PostgreSQLContainer` to run PostgreSQL in Docker:

~~~java
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class DatabaseContainerTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void containerIsRunning() {
        assertTrue(POSTGRES.isRunning());
    }
}
~~~

Testcontainers pulls the image if absent locally, starts the container, waits until the database is ready, and then executes tests. When the test class finishes, the JUnit extension stops and removes the container according to its lifecycle.

Pin a concrete image tag instead of floating tags like `latest` so tests remain reproducible. Pick a PostgreSQL version close to production, especially when relying on specific data types or vendor features.

### Docker is a prerequisite

Testcontainers requires a Docker daemon or compatible container runtime. If Docker is not running, containers cannot start. That is a test environment failure, not a repository bug.

In CI, runners need access to a Docker socket or compatible container runtime. Never silently skip integration tests and report a green build as though they had run.

## 4. Configuring R2DBC with DynamicPropertySource

Container host ports are dynamically mapped. Never assume PostgreSQL is always listening on `localhost:5432`. Use `@DynamicPropertySource` to register connection properties once the container exposes its endpoint.

~~~java
@DataR2dbcTest
@Testcontainers
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class PersonRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void configureR2dbc(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.r2dbc.url",
            () -> "r2dbc:postgresql://"
                + POSTGRES.getHost()
                + ":"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", POSTGRES::getUsername);
        registry.add("spring.r2dbc.password", POSTGRES::getPassword);
    }

    @Autowired
    PersonRepository repository;
}
~~~

Key points:

- The URL uses scheme `r2dbc:postgresql`, not `jdbc:postgresql`.
- Host comes from `POSTGRES.getHost()`.
- Port comes from `getMappedPort(5432)`, never hardcoded to `5432`.
- Database name, username, and password come from the container.
- `Replace.NONE` prevents test database replacement from swapping the configured connection for an embedded database.

Exact annotations and packages must match your project's Spring Boot version. In some versions, test slices or auto-configuration may differ; use the APIs from your managed dependencies.

### Why not use the JDBC URL?

`PostgreSQLContainer` exposes `getJdbcUrl()`, but Spring Data R2DBC needs an R2DBC URL. Both URLs can point to the same container, yet they belong to two different SPIs and drivers.

## 5. Using @DataR2dbcTest or @SpringBootTest?

Pick the test context matching your scope.

| Annotation | Scope |
| --- | --- |
| `@DataR2dbcTest` | Repositories, mapping, `DatabaseClient`, `R2dbcEntityTemplate`, and the persistence slice. |
| `@SpringBootTest` | Full application context, service wiring, transaction config, migrations, and application beans. |
| `@WebFluxTest` | Controllers, routing, and HTTP serialization; services are typically mocked. |
| Pure unit test | Mappers, domain rules, and logic needing neither Spring nor a database. |

### Repository slice

`@DataR2dbcTest` boots only the persistence slice and usually starts faster than a full application context. Use it to verify derived queries, custom `@Query` methods, converters, generated IDs, and constraints.

### Full application context

`@SpringBootTest` fits when testing services coordinating multiple repositories, transaction manager configuration, automatic migrations, or full bean wiring. Booting the entire application solely to test one repository slows tests down and makes failures harder to diagnose.

### @SpringBootTest example

~~~java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrderServiceIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.r2dbc.url",
            () -> "r2dbc:postgresql://"
                + POSTGRES.getHost()
                + ":"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", POSTGRES::getUsername);
        registry.add("spring.r2dbc.password", POSTGRES::getPassword);
    }

    @Autowired
    OrderService orderService;
}
~~~

This example uses the same container while booting the full application context. If the application uses Flyway, also configure the separate JDBC URL as shown next.

## 6. Preparing the schema with migrations

The most reliable approach for integration tests is running the application's actual migrations. That verifies both that migrations build a valid schema and that current code works against it.

When running Flyway over JDBC, also register the JDBC URL from the same container:

~~~java
@DynamicPropertySource
static void configureDatabase(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.r2dbc.url",
        () -> "r2dbc:postgresql://"
            + POSTGRES.getHost()
            + ":"
            + POSTGRES.getMappedPort(5432)
            + "/"
            + POSTGRES.getDatabaseName()
    );
    registry.add("spring.r2dbc.username", POSTGRES::getUsername);
    registry.add("spring.r2dbc.password", POSTGRES::getPassword);

    registry.add("spring.flyway.url", POSTGRES::getJdbcUrl);
    registry.add("spring.flyway.user", POSTGRES::getUsername);
    registry.add("spring.flyway.password", POSTGRES::getPassword);
}
~~~

Test runtime dependencies must include Flyway and the PostgreSQL JDBC driver. Spring Boot runs Flyway during application context startup, before repositories are invoked. Exact auto-configuration behavior depends on Spring Boot version and datasource settings.

If using Liquibase, configure the JDBC URL and credentials under the corresponding Liquibase properties.

### Why share the same container?

Flyway builds the schema via JDBC, and repositories then access that schema via R2DBC. Both connections must target the exact same server, database, and schema. If migrations run against database A while R2DBC connects to database B, tests will fail with missing-table errors even though migration logs report success.

### Never alter migrations solely to pass a test

Integration tests should run real migrations. If a migration fails on a clean database, fix the migration or migration configuration properly. Never maintain a separate test schema diverging from production and treat test passes as validation of your migrations.

## 7. Preparing the schema with schema.sql when not using migrations

For small tests or modules without migrations yet, place `schema.sql` under `src/test/resources`:

~~~sql
CREATE TABLE people (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    first_name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE
);
~~~

Configure SQL initialization:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
~~~

With a container database, set `mode` explicitly so Spring executes the script when needed. Whether SQL initialization activates inside a test slice depends on your Spring Boot version and active auto-configuration.

`schema.sql` works well for small, stable test fixtures. Once the application uses Flyway or Liquibase, prefer running real migrations to avoid drift between test and production schemas.

## 8. Writing your first repository integration test

Assume a `Person` entity:

~~~java
@Table("people")
public record Person(
    @Id Long id,
    @Column("first_name") String firstName,
    String email
) {}
~~~

Repository:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    Mono<Person> findByEmail(String email);

    Flux<Person> findByFirstName(String firstName);
}
~~~

Test saving and reading back:

~~~java
@Test
void savesAndReadsPerson() {
    String email = UUID.randomUUID() + "@example.test";
    Person input = new Person(null, "Ada Lovelace", email);

    StepVerifier.create(
        repository.save(input)
            .flatMap(saved -> repository.findById(saved.id()))
    )
    .assertNext(found -> {
        assertNotNull(found.id());
        assertEquals("Ada Lovelace", found.firstName());
        assertEquals(email, found.email());
    })
    .verifyComplete();
}
~~~

This test verifies a realistic round trip:

1. Spring Data maps the entity to a row.
2. The R2DBC driver sends an `INSERT` to PostgreSQL.
3. The database generates the ID.
4. The repository emits the saved entity.
5. `findById` executes a `SELECT` by ID.
6. The driver maps the row back into an entity.
7. `StepVerifier` asserts the payload and completion signal.

Never mock the repository in this test. The entire goal is confirming the database, mapping, and driver cooperate properly.

## 9. Verifying Mono signals with StepVerifier

A `Mono` can emit at most one item, complete empty, or emit an error.

### Expecting one item

~~~java
StepVerifier.create(repository.findByEmail(email))
    .assertNext(person -> assertEquals(email, person.email()))
    .verifyComplete();
~~~

If the `Mono` is empty, `assertNext` is not called and `verifyComplete` fails the test because an element was expected.

### Expecting empty

~~~java
StepVerifier.create(repository.findByEmail("missing@example.test"))
    .verifyComplete();
~~~

This is the standard behavior of `findById`/`findByEmail` when no record matches. `Mono.empty()` is not an exception.

### Expecting an error

~~~java
StepVerifier.create(service.createOrder(invalidCommand))
    .expectError(InvalidOrderException.class)
    .verify();
~~~

Use `expectErrorMatches` when you also need to assert error codes or causes. Avoid coupling tightly to driver error messages, which can change across versions.

### Asserting a value followed by completion

~~~java
StepVerifier.create(repository.count())
    .expectNext(3L)
    .verifyComplete();
~~~

`StepVerifier` verifies both the emitted value and the completion signal. If the publisher emits extra items or errors afterward, `verifyComplete` catches it.

## 10. Verifying Flux signals with StepVerifier

A `Flux` can emit multiple items. Assert element counts, contents, and order—checking order only when ordering is part of the query contract.

~~~java
StepVerifier.create(repository.findByFirstName("Ada"))
    .expectNextMatches(person ->
        person.firstName().equals("Ada")
    )
    .expectNextMatches(person ->
        person.firstName().equals("Ada")
    )
    .verifyComplete();
~~~

This test assumes exactly two matching rows and deterministic ordering. Without an `ORDER BY`, databases do not guarantee return order.

### Asserting after collecting into a list

~~~java
StepVerifier.create(repository.findByFirstName("Ada").collectList())
    .assertNext(people -> {
        assertEquals(2, people.size());
        assertTrue(people.stream()
            .allMatch(person -> person.firstName().equals("Ada")));
    })
    .verifyComplete();
~~~

`collectList` works well when test result sets are small and you want collection-level assertions. Avoid this pattern for huge production streams without memory bounds.

### Verifying explicit ordering

When a repository method includes `ORDER BY`:

~~~java
StepVerifier.create(repository.findByFirstNameOrderByEmailAsc("Ada"))
    .expectNextMatches(person -> person.email().startsWith("a-"))
    .expectNextMatches(person -> person.email().startsWith("b-"))
    .verifyComplete();
~~~

Seed test fixtures with distinct sort values so ordering assertions are unambiguous.

## 11. Testing derived queries and custom SQL

Integration tests should confirm queries execute cleanly on the target database vendor.

Derived query:

~~~java
Flux<Person> findByFirstNameOrderByEmailAsc(String firstName);
~~~

Custom query:

~~~java
@Query("""
    SELECT id, first_name, email
    FROM people
    WHERE LOWER(first_name) = LOWER(:name)
    ORDER BY id
    """)
Flux<Person> searchByNameIgnoreCase(String name);
~~~

Tests should verify:

- Bind parameters are passed properly.
- Column names and aliases match mappings.
- Functions and operators are supported by the database.
- Results map to the expected Java types.
- Empty results and multi-row results match expected semantics.
- Sorting is deterministic.

For PostgreSQL-specific queries using `JSONB` operators, arrays, or `RETURNING`, run tests on a PostgreSQL container rather than H2 alone.

## 12. Testing constraints and database errors

Testcontainers lets you test real database constraints.

Suppose `email` has a `UNIQUE` constraint. Testing duplicates:

~~~java
@Test
void rejectsDuplicateEmail() {
    String email = UUID.randomUUID() + "@example.test";

    Person first = new Person(null, "First", email);
    Person duplicate = new Person(null, "Second", email);

    StepVerifier.create(
        repository.save(first)
            .then(repository.save(duplicate))
    )
    .expectError()
    .verify();
}
~~~

This verifies that the second write emits an error. When asserting a specific exception type, inspect the translated exception and SQLSTATE returned by your Spring exception translator and driver version.

Constraints that warrant integration tests:

- `UNIQUE`: rejects duplicate business keys.
- `NOT NULL`: rejects missing required data.
- `FOREIGN KEY`: blocks dangling references.
- `CHECK`: enforces quantity, price, or status bounds.
- `PRIMARY KEY`: enforces entity identity.

Never assume every database vendor raises the exact same exception class or message for the same constraint.

## 13. Testing generated IDs and database defaults

When IDs are database-generated, verify the returned entity carries a valid ID:

~~~java
StepVerifier.create(repository.save(new Person(null, "Grace", email)))
    .assertNext(saved -> assertNotNull(saved.id()))
    .verifyComplete();
~~~

If the table defines default timestamps or triggers, read the row back to confirm the database populated the expected values.

Never assert solely on the input object, since the input instance may retain its `null` ID or `null` timestamp. Inspect the entity emitted by `save` and/or read back from the database according to driver semantics.

Generated values and `RETURNING` behavior depend on the database and driver. Test with the same engine and a version close to production.

## 14. Testing transaction rollbacks with TransactionalOperator

Reactive transactions attach to the Reactor Context and subscription. Never assume they behave like JDBC thread-bound transactions.

Inject a `TransactionalOperator` backed by the same `R2dbcTransactionManager` as the repository:

~~~java
@Test
void rollsBackWriteWhenPublisherFails() {
    String email = UUID.randomUUID() + "@example.test";
    Person person = new Person(null, "Rollback", email);

    Mono<Person> work = repository.save(person)
        .flatMap(saved ->
            Mono.<Person>error(new IllegalStateException("force rollback"))
        );

    StepVerifier.create(transactionalOperator.transactional(work))
        .expectError(IllegalStateException.class)
        .verify();

    StepVerifier.create(repository.findByEmail(email))
        .verifyComplete();
}
~~~

The test executes an `INSERT` and then emits an error inside the same transaction. `TransactionalOperator` rolls back; after the publisher terminates, a new query confirms the row does not exist.

For this test to be valid:

- `TransactionalOperator` uses the repository's `ConnectionFactory`.
- Repository operations are subscribed inside the transaction-wrapped publisher.
- The error propagates past the transaction boundary to trigger rollback.
- The database supports transactions for the operation under test.
- The verification query runs after the transaction rollback completes.

### Never call subscribe inside a transaction

Do not write:

~~~java
transactionalOperator.transactional(repository.save(person)).subscribe();
return Mono.empty();
~~~

A detached subscription runs outside the lifecycle controlled by the test. Always pass the publisher to `StepVerifier` or return it to the caller.

### Be cautious with @Transactional on test methods

Do not assume `@Transactional` on a test method behaves identically to JDBC tests. Test-managed reactive transaction support depends on Spring Test version and the transaction manager type. With reactive flows, explicitly wrapping with `TransactionalOperator` makes clear which publisher participates in the transaction.

## 15. Testing service use cases with multiple writes

Integration tests can verify services coordinating multiple repositories in a single transaction.

Example use case creating an order and order lines:

~~~java
@Test
void createsOrderAndLinesAtomically() {
    CreateOrderCommand command = sampleCommand();

    StepVerifier.create(orderService.create(command))
        .assertNext(order -> {
            assertNotNull(order.id());
            assertEquals(2, order.lines().size());
        })
        .verifyComplete();

    StepVerifier.create(orderRepository.findById(command.expectedId()))
        .expectNextCount(1)
        .verifyComplete();
}
~~~

Adapt this illustration to how IDs are generated and what your service returns. Tests should read back the related tables to confirm both root and child rows persisted.

A companion rollback test can force the payment write step to fail after inserting the order, then verify neither the order nor the payment persisted when both share the transaction.

Never check only the returned DTO. Read back from the database to verify committed state.

## 16. Managing fixtures and data isolation between tests

Integration tests sharing a container or Spring context can observe data left by earlier tests. Without isolation, outcomes depend on execution order and parallel tests fail.

Best practices:

- Generate unique UUIDs or business keys per test.
- Create fixtures inside each test rather than depending on another test's data.
- Delete test data by test key rather than running table-wide `DELETE`s during parallel runs.
- Delete child tables before parent tables when foreign keys require it.
- Wait for cleanup publishers to finish before ending the test.
- Never share mutable fixture objects across tests.
- Keep explicit `ORDER BY` clauses whenever assertions depend on ordering.

Example generating a unique email:

~~~java
String email = "person-" + UUID.randomUUID() + "@example.test";
~~~

This avoids collisions across repeated or parallel test runs.

### Reactive cleanup

You can use `DatabaseClient` with `StepVerifier` in `@AfterEach`:

~~~java
@AfterEach
void cleanUp() {
    StepVerifier.create(
        databaseClient.sql("DELETE FROM people")
            .fetch()
            .rowsUpdated()
    )
    .expectNextMatches(rows -> rows >= 0)
    .verifyComplete();
}
~~~

`rowsUpdated` emits the affected row count; `expectNextMatches` asserts that count. Never use `expectNextCount` to check the row count, because `expectNextCount` counts emitted `onNext` signals instead.

In parallel suites, a table-wide `DELETE` can wipe out data belonging to another running test. Delete by unique test key or isolate each test worker in its own schema or database.

### Cleanup with foreign keys

If `order_lines` references `orders`, delete children before parents or use `TRUNCATE ... CASCADE` strictly in an isolated test database. Never run destructive cleanup commands on shared databases.

## 17. Container lifecycle and Spring context caching

This is a common pitfall when pairing Testcontainers with the Spring TestContext framework.

The JUnit Testcontainers extension manages containers annotated with `@Container`. A static `@Container` typically starts for a test class and stops when that class completes. Spring, however, caches application contexts across test classes. If a cached context is reused after its container stopped, subsequent test classes hold a `ConnectionFactory` pointing to a dead container.

Two common lifecycle setups exist:

### Per-class container

~~~java
@Testcontainers
@SpringBootTest
class PersonRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // DynamicPropertySource and tests
}
~~~

This is simple when a class owns its own context or no later class reuses the cached context after the container stops. When multiple classes share a cached context, manage the lifecycle carefully.

### Shared singleton container

You can define a base class or test support helper that keeps one container alive for the entire test JVM:

~~~java
abstract class PostgresIntegrationTest {

    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    static {
        POSTGRES.start();
    }

    @DynamicPropertySource
    static void configureR2dbc(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.r2dbc.url",
            () -> "r2dbc:postgresql://"
                + POSTGRES.getHost()
                + ":"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", POSTGRES::getUsername);
        registry.add("spring.r2dbc.password", POSTGRES::getPassword);
    }
}
~~~

Test classes extending the base class share the container. It starts statically once and Testcontainers' shutdown cleanup stops it when the JVM exits. With this pattern, do not also annotate the same container with JUnit's `@Container`.

### Choosing a lifecycle for your suite

- Single isolated test class: static `@Container` is straightforward.
- Multiple classes sharing a Spring context: a singleton or Spring-managed container prevents contexts from pointing at stopped containers.
- Parallel test runs: isolate test data and schemas, not just container lifecycles.
- Multi-fork CI runs: each JVM fork may spin up its own container; weigh startup time and resource limits.

Never allow a Spring context to outlive the database container it connects to.

## 18. Testing optimistic locking and concurrency

A real database is essential to verify behavior under competing operations.

For an entity with `@Version`:

~~~java
@Table("inventory")
public record InventoryItem(
    @Id UUID id,
    String sku,
    Integer quantity,
    @Version Long version
) {}
~~~

A test can:

1. Insert an inventory item.
2. Read the entity with its current version.
3. Update it using that version.
4. Attempt to save a stale copy carrying the old version.
5. Verify the stale write emits an optimistic locking error.

Exact exception types and implementation details depend on your Spring Data version. Test on your target database to confirm.

### Two concurrent updates

You can trigger two competing operations with `Mono.when` or `Flux.merge`, designing the test so assertions do not depend on arbitrary thread scheduling. Use barriers/latches or coordinated service hooks when reproducing race conditions reliably.

Never assert that one specific operation always wins unless the database guarantees that order. Assert the final invariants: no lost updates outside policy, version incremented properly, and stale operations rejected.

## 19. Testing timeouts and connection failures

Integration tests can hang if a query stalls or a container stops. Always pass a timeout to `StepVerifier`:

~~~java
StepVerifier.create(repository.findAll())
    .expectNextCount(3)
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

Set timeouts generous enough for CI environments and container cold starts. Setting timeouts too tight causes flaky tests.

Distinguish clearly between:

- Container failed to start.
- `ConnectionFactory` failed to connect.
- Query hung.
- Publisher emitted a SQL error.
- Assertion failed due to unexpected data.

Each failure mode requires different diagnostics. Test logs should preserve exception causes and SQLSTATEs without printing passwords or URLs containing credentials.

## 20. Testcontainers and WebFlux end-to-end

To test HTTP endpoints alongside a real database, use `@SpringBootTest` with `RANDOM_PORT` and `WebTestClient`:

~~~java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ProductApiIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.r2dbc.url",
            () -> "r2dbc:postgresql://"
                + POSTGRES.getHost()
                + ":"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", POSTGRES::getUsername);
        registry.add("spring.r2dbc.password", POSTGRES::getPassword);
    }

    @Autowired
    WebTestClient webTestClient;

    @Test
    void createsAndReadsProduct() {
        webTestClient.post()
            .uri("/api/products")
            .bodyValue(sampleRequest())
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.id").exists();
    }
}
~~~

`WebTestClient` exercises the HTTP boundary. `StepVerifier` is suited for testing service and repository publishers directly. You do not need `StepVerifier` for every HTTP test; pick the tool matching the boundary under test.

If an endpoint writes data and the test reads it back over HTTP, that is a broader end-to-end integration test than a repository test. Keep end-to-end tests focused in count because they boot more components and run slower.

## 21. Testing custom converters and vendor-specific data types

When entities use `UUID`, JSON, enums, or timestamps, run round-trip tests against a real database:

1. Construct an entity with representative values.
2. Save via the repository.
3. Read back by ID or business key.
4. Compare mapped Java values.
5. When needed, query the raw column directly to verify database representation.

For PostgreSQL `JSONB`, H2 cannot validate `JSONB` operators or converters. Use a PostgreSQL container to test saving, reading, and querying JSON fields.

For timestamps, verify `Instant`/`OffsetDateTime` and timezone semantics. Avoid comparing formatted display strings alone, as drivers may normalize precision or timezone offsets per column type.

Custom converters must be imported into test slices if not auto-configured:

~~~java
@DataR2dbcTest
@Import(ProductR2dbcConfiguration.class)
class ProductMappingIntegrationTest {
    // Tests
}
~~~

Verify that converters are actually registered in the mapping context rather than only invoking converter classes directly in unit tests.

## 22. Running integration tests in CI

CI environments must ensure:

- A Docker daemon or compatible container runtime is available.
- Runners can pull images or images are pre-cached.
- Image tags are pinned.
- Test timeouts accommodate cold container starts.
- Testcontainers cleanup leaves no orphaned containers or resource leaks.
- Database ports are allocated dynamically to avoid collisions.
- Secrets are never printed in build logs.
- Integration tests are clearly separated from unit tests.
- Parallel tests never share unsafe mutable data.

You can split out a dedicated Gradle integration test task when suites grow long. Exact source set/task configuration depends on your build structure; never copy arbitrary task names without checking `build.gradle`.

### When Docker is unavailable

You can use build profiles to run unit tests without Docker and run integration tests on a separate Docker-enabled job. If using Testcontainers' `disabledWithoutDocker`, monitor skipped tests closely. Release pipelines should verify the integration suite actually ran against the target database.

Never swap Testcontainers for mocks and treat coverage as equivalent.

## 23. Common pitfalls

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Docker connection error | Docker daemon stopped or runner lacks permissions. | Start Docker or grant container runtime access in CI. |
| Connection refused | Container not ready or wrong URL/port. | Use Testcontainers mapped ports and readiness waits. |
| Table not found | Schema/migrations did not run or wrong DB/schema. | Check migrations, SQL init, and R2DBC URL. |
| Flyway runs but R2DBC reports missing tables | JDBC and R2DBC point to different DBs/schemas. | Point both URLs to the same container endpoint. |
| Test slice missing repository bean | Incorrect package scan or slice configuration. | Check base packages and repository configuration. |
| Embedded database used unexpectedly | Test database replacement is enabled. | Set `Replace.NONE` when targeting a real container. |
| Later test class fails to connect | Cached Spring context outlived per-class container. | Use a shared container lifecycle or isolate contexts. |
| Flaky test failures | Shared data or missing `ORDER BY`. | Use unique fixtures and deterministic sorting. |
| Rollback does not happen | Publisher runs outside reactive transaction context. | Wrap with `TransactionalOperator` and verify via `StepVerifier`. |
| Exception assertion fails | Driver/DB emits a different exception than expected. | Inspect cause chain, SQLSTATE, and vendor behavior. |
| Test hangs | Publisher never completes or timeout is missing. | Pass `verify(Duration)` and inspect connection/query. |
| Parallel tests delete each other's data | Table-wide `DELETE` cleanup. | Clean up by test key or isolate schemas/databases. |

## 24. Workflow for building integration tests

When adding integration tests for an R2DBC repository or service, follow this order:

1. **Choose the scope:** repository slice, full context, or HTTP end-to-end.
2. **Choose the database:** match your production vendor and version closely.
3. **Add dependencies:** R2DBC driver, Reactor Test, and Testcontainers modules.
4. **Start the container:** pin the image tag and configure readiness checks.
5. **Register dynamic properties:** configure R2DBC URL, username, and password via `@DynamicPropertySource`.
6. **Prepare the schema:** run real migrations or an appropriate schema script.
7. **Create isolated fixtures:** generate unique UUIDs or business keys per test.
8. **Drive the publisher:** use `StepVerifier` to assert `onNext`/`onComplete`/`onError`.
9. **Verify database state:** read back persisted data, constraints, generated values, and mappings.
10. **Verify transactions:** use `TransactionalOperator` for rollbacks and reactive context tests.
11. **Manage lifecycles:** ensure containers never shut down before the Spring contexts using them.
12. **Run in CI:** confirm Docker availability, timeouts, cleanup, and actual test execution.

Testcontainers provides a reproducible real database, while `StepVerifier` asserts reactive publisher signals accurately. Configuring R2DBC against dynamic container endpoints, applying real migrations/schemas, and testing through real repositories catches dialect, mapping, constraint, transaction, and concurrency bugs that mocks miss. Keep fixtures isolated, align container and Spring context lifecycles, and run the suite in Docker-enabled CI for reliable, trustworthy results.
