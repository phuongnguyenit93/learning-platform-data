# Testing Repositories with @DataR2dbcTest

Spring Data R2DBC repositories return reactive types such as Mono and Flux. Therefore, repository testing needs to verify both the database statements and how the publisher emits data, completes, or signals errors. Spring Boot provides the @DataR2dbcTest annotation to create a test slice focused on R2DBC components without starting the entire application.

This test slice is well suited for testing repositories, entity mapping, derived queries, custom queries, DatabaseClient, and R2dbcEntityTemplate. It helps tests run faster than booting the full application context while still using real Spring Data R2DBC infrastructure.

A good repository test should verify database behavior: inserts and generated IDs, conditional queries, pagination/sorting, data type mapping, custom SQL, constraints, and transactions where appropriate. StepVerifier drives subscription and checks reactive signals. For database- or driver-dependent differences, Testcontainers lets you run the actual database engine in the test environment.

## 1. What Is @DataR2dbcTest Used For?

@DataR2dbcTest is a Spring Boot test slice for applications using Spring Data R2DBC. It loads only the configuration slice related to R2DBC and repositories rather than initializing web, security, messaging, or unrelated service components.

A test slice typically provides:

- R2DBC ConnectionFactory configuration.
- Spring Data R2DBC repository infrastructure.
- Entity mapping and related persistence components.
- Beans such as DatabaseClient or R2dbcEntityTemplate when auto-configured.
- Test database configuration depending on available classpath dependencies and settings.

Regular application components are not necessarily scanned as in a full application context. If a repository test needs custom converters, mapping configuration, or dedicated helper beans, import them explicitly with @Import or a nested @TestConfiguration.

### Scope of the Test Slice

| Component | Suitable inside @DataR2dbcTest? |
| --- | --- |
| ReactiveCrudRepository | Yes, this is the primary target. |
| Custom repository implementation | Yes, if discovered and configured within the slice. |
| DatabaseClient/R2dbcEntityTemplate | Yes, when the corresponding auto-configuration is active. |
| Entity mapping and custom converters | Yes, though custom configuration must be imported if not auto-detected. |
| Regular application services | Usually not component-scanned like a full app; import or mock only when genuinely needed. |
| WebFlux controllers and HTTP routing | Outside the scope of this slice. |
| Security filter chain, messaging, schedulers | Not automatically initialized as in the full application. |
| Flyway/Liquibase migrations | Do not assume they are always enabled in the slice; configure or run separately per test goal. |

If you need to test HTTP requests, validation, or controllers, use @WebFluxTest or @SpringBootTest with WebTestClient. If you need to test full service orchestration together with repositories and application configuration, use @SpringBootTest.

## 2. Creating Your First Repository Test

Suppose the application has a Person entity stored in the people table:

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

    Flux<Person> findByFirstName(String firstName);

    Mono<Person> findByEmail(String email);

    Mono<Boolean> existsByEmail(String email);
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@DataR2dbcTest
class PersonRepositoryTest {

    @Autowired
    PersonRepository repository;

    @Test
    void savesAndFindsPerson() {
        Person input = new Person(
            null,
            "Ada Lovelace",
            "ada-" + UUID.randomUUID() + "@example.test"
        );

        StepVerifier.create(
            repository.save(input)
                .flatMap(saved -> repository.findById(saved.id()))
        )
        .assertNext(found -> {
            assertNotNull(found.id());
            assertEquals("Ada Lovelace", found.firstName());
            assertTrue(found.email().startsWith("ada-"));
        })
        .verifyComplete();
    }
}
~~~

The example assumes the schema has been initialized and the database supports generated identity for the id column. The ID is null on insert; Spring Data/the driver receives the database-generated ID and returns the saved entity. Verify this behavior on your target database because ID generation strategies depend on the database, schema, and mapping.

Key points:

1. @DataR2dbcTest creates a test context for persistence.
2. Spring injects the real repository, not a mock.
3. repository.save returns a Mono and does not execute until subscribed to.
4. StepVerifier subscribes and inspects emitted elements.
5. findById runs after save completes thanks to flatMap.
6. verifyComplete confirms the publisher completes without further errors.

Do not call subscribe manually in the test and then assert against shared variables. StepVerifier keeps subscription and assertions in the same test pipeline.

## 3. StepVerifier and How to Verify Mono/Flux

Reactor Test provides StepVerifier to verify onNext, onComplete, and onError signals in sequence. This is the right way to verify reactive behavior without blocking in production code.

### Verifying a Mono with One Element

~~~java
StepVerifier.create(repository.findById(id))
    .assertNext(person -> {
        assertEquals(id, person.id());
        assertEquals("Ada Lovelace", person.firstName());
    })
    .verifyComplete();
~~~

If the repository does not find the ID, the Mono completes empty. When the test expects an element, use expectNext or assertNext so the test fails if no data is returned.

### Verifying an Empty Mono

~~~java
StepVerifier.create(repository.findByEmail("missing@example.test"))
    .verifyComplete();
~~~

For methods returning Mono<Person>, not found is normally represented as Mono.empty. Do not confuse this case with a database error.

### Verifying a Flux with Multiple Elements

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

The test above assumes exactly two matching records. If ordering is not guaranteed by the query, do not rely on element emission order. Add ORDER BY or use collectList and inspect the set of values if ordering is not part of the repository contract.

### Verifying Element Count

~~~java
StepVerifier.create(repository.findByFirstName("Ada"))
    .expectNextCount(2)
    .verifyComplete();
~~~

expectNextCount only verifies the count, not the contents. Use assertNext when fields need inspection.

### Verifying Errors

~~~java
StepVerifier.create(repository.save(personWithInvalidData))
    .expectError()
    .verify();
~~~

When you need to verify the error type, use expectError(Class) or expectErrorMatches. Specific exception types may depend on Spring exception translation and the R2DBC driver. For constraint errors, verify against the real driver/database rather than assuming all vendors return the same class.

## 4. Initializing Schema for Repository Tests

Repositories require tables and columns matching entities. There are several ways to initialize schema:

- Using schema.sql in test resources.
- Using Flyway/Liquibase migrations.
- Using dedicated scripts for Testcontainers.
- Creating schema in test setup via DatabaseClient when direct control is needed.

Example schema.sql for the people table:

~~~sql
CREATE TABLE people (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    first_name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE
);
~~~

Place the file at:

~~~text
src/test/resources/schema.sql
~~~

Spring Boot has SQL initialization support for R2DBC. You can configure tests to run scripts:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
~~~

Property names and initialization timing depend on the Spring Boot version and how the test slice is configured. With embedded databases, the default mode may only initialize schema in appropriate cases. With external databases or Testcontainers, configure mode explicitly if using schema.sql.

If the test suite runs in parallel on the same database, avoid having multiple tests DROP/CREATE tables concurrently. Create the schema once per container/context and use independent test data.

### Sample Data

You can use data.sql to load fixed seed data:

~~~sql
INSERT INTO people (first_name, email)
VALUES ('Ada Lovelace', 'ada@example.test');

INSERT INTO people (first_name, email)
VALUES ('Grace Hopper', 'grace@example.test');
~~~

Fixed seed data helps query tests that expect deterministic results. For tests that may run repeatedly or in parallel, use unique emails/IDs to avoid data collisions across runs.

Do not rely on insert order to infer SELECT order. If a test requires ordering, the query must have ORDER BY.

## 5. Embedded Databases vs. Real Databases

@DataR2dbcTest can use an embedded R2DBC database if the corresponding driver and dependency are on the test classpath, or use a database configured in the test environment. Embedded databases are fast to run and easy to set up.

However, different databases differ in:

- SQL syntax and functions.
- Data types such as UUID, JSON, enums, and timestamps.
- Generated identities/sequences.
- Constraints and error codes.
- Transaction isolation, locking, and savepoints.
- Collation, case sensitivity, and string comparison rules.
- Handling of LIMIT/OFFSET, RETURNING, and upserts.

A query that runs on H2 is not guaranteed to behave the same on PostgreSQL or MySQL. Embedded databases suit simple repository tests, basic mapping, and portable queries. For vendor-specific SQL or critical production features, test against the same database type as the real environment.

### Do Not Swap Databases Just to Make Tests Easier

If production uses PostgreSQL and a repository has queries relying on JSONB, arrays, RETURNING, or PostgreSQL-specific operators, H2 cannot prove the query works properly. H2 tests may still be useful for general logic, but you need PostgreSQL integration tests to verify real behavior.

## 6. Using Testcontainers with PostgreSQL

Testcontainers runs a real database in a container during tests. This lets you test the R2DBC driver, SQL dialect, data types, and constraints matching the target environment.

Illustrative Gradle dependencies:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

The project needs the R2DBC PostgreSQL driver on the runtime/test runtime classpath per its dependency configuration. Testcontainers versions should be managed consistently through a BOM or project dependency management.

Test class:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataR2dbcTest
@Testcontainers
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class PersonRepositoryPostgresTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void r2dbcProperties(DynamicPropertyRegistry registry) {
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

    @Test
    void persistsPersonInPostgres() {
        String email = UUID.randomUUID() + "@example.test";
        Person input = new Person(null, "Grace Hopper", email);

        StepVerifier.create(repository.save(input))
            .assertNext(saved -> {
                assertNotNull(saved.id());
                assertEquals(email, saved.email());
            })
            .verifyComplete();
    }
}
~~~

The example uses a PostgreSQL 16 image for illustration. Choose an image tag compatible with production and project test policy. The AutoConfigureTestDatabase annotation with Replace.NONE instructs Spring Boot not to replace the configured connection with an embedded test database; verify exact package/API for your Spring Boot version.

### Why Is @DynamicPropertySource Needed?

Container ports are typically mapped dynamically on the host. Do not hard-code localhost:5432. DynamicPropertySource registers the URL, username, and password once the container provides its actual endpoint.

The R2DBC URL has the form r2dbc:postgresql://host:port/database. PostgreSQLContainer usually exposes a JDBC URL, but R2DBC tests need a URL using the R2DBC driver scheme. Both URLs must point to the same container/database.

### Docker and CI Environments

Testcontainers requires a Docker daemon or compatible container runtime. If developer/CI machines lack Docker, tests may not run. You can:

- Configure CI runners with Docker support.
- Run container test groups in a separate integration pipeline.
- Use an embedded database for fast tests and Testcontainers for tests needing the real vendor.
- Use @Testcontainers(disabledWithoutDocker = true) when supported by your Testcontainers version and the project wants to skip tests without Docker.

Do not silently skip all integration tests in production CI. Pipelines should clearly report which tests ran and which were skipped.

## 7. Keep the Test Slice Small and Import Needed Configuration

@DataR2dbcTest does not perform full component scanning like @SpringBootTest. This is intentional to keep tests focused and fast.

If you need custom converters or mapping configuration, import them explicitly:

~~~java
@DataR2dbcTest
@Import(ProductR2dbcConfiguration.class)
class ProductRepositoryTest {
    // repository tests
}
~~~

If configuration is only used for tests, you can declare a nested @TestConfiguration:

~~~java
@DataR2dbcTest
class ProductRepositoryTest {

    @TestConfiguration
    static class TestConfig {
        // Test-only beans
    }
}
~~~

Do not pull all services, controllers, and external clients into the slice when the target is only repositories. If you need service beans to test larger flows, consider @SpringBootTest or import only the exact collaborators needed.

### Custom Conversions

If entities have custom types, special enum mappings, or custom converters, repository tests need the same conversion configuration as the application. If the test context does not scan that configuration automatically, use @Import.

Example domain data type:

~~~java
public record Money(BigDecimal amount, String currency) {}
~~~

If Money is stored in a NUMERIC or VARCHAR column according to custom conventions, reading and writing converters are needed. Tests should verify both directions:

1. Save an entity containing Money.
2. Read the entity back.
3. Compare amount and currency.
4. Check the database value if the converter uses a custom representation.

Do not test converters solely via unit tests; repository integration tests confirm the converter is actually registered in the mapping infrastructure.

## 8. Testing Derived Query Methods

Spring Data can generate queries from method names. Repository tests should verify that methods query the expected dataset:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    Flux<Person> findByFirstName(String firstName);

    Mono<Person> findByEmail(String email);

    Flux<Person> findByFirstNameOrderByEmailAsc(String firstName);
}
~~~

Test:

~~~java
@Test
void findsPeopleByFirstName() {
    String first = "Ada-" + UUID.randomUUID();

    Person firstPerson = new Person(null, first, "a-" + UUID.randomUUID() + "@example.test");
    Person secondPerson = new Person(null, first, "b-" + UUID.randomUUID() + "@example.test");

    StepVerifier.create(
        repository.saveAll(List.of(firstPerson, secondPerson))
            .thenMany(repository.findByFirstNameOrderByEmailAsc(first))
    )
    .assertNext(person -> assertTrue(person.email().startsWith("a-")))
    .assertNext(person -> assertTrue(person.email().startsWith("b-")))
    .verifyComplete();
}
~~~

Using a unique prefix prevents the test from being affected by data from other tests. Queries with OrderBy in the method name create an explicit order; without sorting, do not assert emission order.

For repository methods returning Mono<Person> on queries that could match multiple rows, understand query semantics and unique constraints. If multiple rows match, the result may error due to more results than expected. Use Flux for multi-row relationships or enforce uniqueness in the database.

## 9. Testing Custom Queries with @Query

For declared queries, tests must run against a database to confirm SQL validity and accurate mapping.

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    @Query("""
        SELECT id, first_name, email
        FROM people
        WHERE LOWER(first_name) = LOWER(:name)
        ORDER BY id
        """)
    Flux<Person> searchByNameIgnoreCase(String name);
}
~~~

Test:

~~~java
@Test
void executesCustomQueryAndMapsRows() {
    String name = "Ada-" + UUID.randomUUID();

    Person input = new Person(null, name, "ada-" + UUID.randomUUID() + "@example.test");

    StepVerifier.create(
        repository.save(input)
            .thenMany(repository.searchByNameIgnoreCase(name.toUpperCase(Locale.ROOT)))
    )
    .assertNext(found -> assertEquals(name, found.firstName()))
    .verifyComplete();
}
~~~

This test verifies:

- Named parameters are bound.
- The LOWER function is supported by the database.
- Column names and aliases match the entity.
- Rows are mapped into Person.
- The query emits the expected result.

Text block syntax and named parameters are supported according to the Spring Data R2DBC version. If SQL uses vendor-specific functions or operators, run tests against the production database.

### Testing Queries Returning Projections

If a query selects only a subset of columns, use an appropriate projection instead of mapping into a full entity:

~~~java
public record PersonSummary(Long id, String firstName) {}
~~~

Query:

~~~java
@Query("""
    SELECT id, first_name
    FROM people
    WHERE id = :id
    """)
Mono<PersonSummary> findSummaryById(Long id);
~~~

Tests should verify that aliases/columns map properly. Do not rely on SELECT * for projections because schema changes can cause queries and mappings to drift out of sync.

## 10. Testing DatabaseClient and R2dbcEntityTemplate

Not all persistence code goes through repository interfaces. Custom repositories may use DatabaseClient or R2dbcEntityTemplate.

You can inject these components inside @DataR2dbcTest:

~~~java
@DataR2dbcTest
class ProductTemplateTest {

    @Autowired
    R2dbcEntityTemplate template;

    @Test
    void insertsAndReadsProduct() {
        ProductEntity product = sampleProduct();

        StepVerifier.create(
            template.insert(ProductEntity.class)
                .using(product)
                .flatMap(saved ->
                    template.select(ProductEntity.class)
                        .matching(query(where("id").is(saved.id())))
                        .one()
                )
        )
        .assertNext(found -> assertEquals(product.name(), found.name()))
        .verifyComplete();
    }
}
~~~

The example illustrates the template API; import Criteria/Query and adjust ID generation to match your entity/schema.

With DatabaseClient:

~~~java
@Autowired
DatabaseClient databaseClient;

@Test
void executesParameterizedSql() {
    String email = UUID.randomUUID() + "@example.test";

    StepVerifier.create(
        databaseClient.sql("""
            SELECT COUNT(*)
            FROM people
            WHERE email = :email
            """)
            .bind("email", email)
            .map((row, metadata) -> row.get(0, Long.class))
            .one()
    )
    .expectNext(0L)
    .verifyComplete();
}
~~~

Index-based mapping can depend on the driver and metadata; in real queries, prefer explicit aliases and reading by column name where appropriate. Tests should also check which Java type the driver returns; COUNT may map to Long or another numeric type depending on the driver.

## 11. Testing Sorting and Pagination

Repository tests should verify page boundaries and sorting if repositories expose Pageable/Sort or custom pagination.

Example:

~~~java
Flux<Person> findByFirstName(String firstName, Sort sort);
~~~

Invocation:

~~~java
repository.findByFirstName(
    "Ada",
    Sort.by(Sort.Direction.ASC, "email")
);
~~~

If a custom repository uses Pageable, tests should verify:

- Offsets are calculated correctly.
- Page size limits the number of elements.
- Sorting includes a stable tie-breaker when primary values match.
- Count queries (if present) count the matching dataset accurately.
- The last page and out-of-range pages are handled properly.

Do not check only element counts. Create test data with duplicate sort values to verify tie-breakers. If a database query lacks a stable ORDER BY, tests can fail intermittently even when data does not change.

## 12. Testing Constraints and Exception Translation

Database tests are the right place to verify that UNIQUE, NOT NULL, FOREIGN KEY, and CHECK constraints are enforced.

Example where email has a unique constraint:

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

This test verifies that the second operation emits an error. If you want to assert the exception type, use the exception returned by Spring/the driver in your specific version and database. You can inspect the cause chain or SQLSTATE to classify integrity violations.

Do not assume every database returns the same exception class or message. Assertions on message text break easily when upgrading driver/database versions.

### Transactions After Constraint Errors

Some databases mark a transaction as aborted/unusable after a statement error until rollback. Therefore, if a test runs multiple statements in the same transaction, operations after the error may fail even if the initial error was caught.

Check your database's transaction semantics. For simple constraint tests, isolate the failing write in its own test/transaction or use appropriate cleanup.

## 13. Managing Data Between Tests

Repository tests may share a database or application context. If data is not isolated, tests become order-dependent and can fail when run in parallel.

Some approaches:

- Use a UUID or unique value for email/code per test.
- Create data through the repository inside the test itself.
- Use separate schemas/databases per suite or worker when parallel execution is needed.
- Delete data using reactive DatabaseClient and wait for cleanup to complete.
- Initialize schema once rather than DROP/CREATE before every method if unnecessary.
- Never rely on data created by another test.

Example reactive cleanup in a test:

~~~java
@AfterEach
void cleanUp() {
    StepVerifier.create(
        databaseClient.sql("DELETE FROM people")
            .fetch()
            .rowsUpdated()
    )
    .expectNextMatches(rowsUpdated -> rowsUpdated >= 0)
    .verifyComplete();
}
~~~

rowsUpdated emits the count of affected rows; expectNextMatches inspects that value, whereas expectNextCount only counts onNext signals. In parallel suites, a full-table DELETE can wipe another test's data. In that case, use unique test keys and delete by key.

### Do Not Clean Up Asynchronously and Exit the Test

Do not call subscribe inside @AfterEach and let the test finish immediately. Cleanup may not finish before the next test starts. Use StepVerifier or an explicit synchronous wait in test lifecycle hooks to await cleanup.

## 14. Transactions in @DataR2dbcTest

Transactions in R2DBC are reactive and tied to subscription/Reactor Context. This differs from JDBC transactions bound to a thread-bound connection.

When using transactions in repository tests:

- Determine whether the test context configures a ReactiveTransactionManager.
- Check whether your Spring Boot/Spring Test version supports reactive transactional test semantics in the way you use it.
- Publishers must be subscribed to within the proper transaction context to join the same transaction.
- A detached subscription will not participate in the managed transaction.
- Do not open a transaction and call subscribe independently in test setup.

Do not assume @Transactional on a test method always works identically to JDBC tests. Verify the behavior of your Spring Boot version and reactive transaction test support. For tests needing explicit commit/rollback control, use TransactionalOperator in the test or call a real transactional service and inspect database state after the publisher completes.

Example using TransactionalOperator to test rollback:

~~~java
@Test
void rollsBackRepositoryWriteWhenPublisherFails() {
    Person person = new Person(
        null,
        "Rollback",
        UUID.randomUUID() + "@example.test"
    );

    Mono<Person> work = repository.save(person)
        .flatMap(saved ->
            Mono.<Person>error(new IllegalStateException("force rollback"))
        );

    StepVerifier.create(transactionalOperator.transactional(work))
        .expectError(IllegalStateException.class)
        .verify();

    StepVerifier.create(repository.findByEmail(person.email()))
        .verifyComplete();
}
~~~

The example assumes transactionalOperator uses the same ConnectionFactory as the repository and the test database supports transactions. The test subscribes to the transaction and queries after the transaction has rolled back.

If the slice's transaction manager is not auto-injected in a given version, import R2dbcTransactionManager configuration or create TransactionalOperator in test configuration.

## 15. Testing Custom Repository Fragments

Custom repository fragments often hold complex queries or DatabaseClient logic. The test slice can still test the fragment through the repository bean if the implementation is discovered by naming convention.

Example interface:

~~~java
public interface PersonSearchRepository {
    Flux<Person> searchByPrefix(String prefix);
}
~~~

Main repository:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long>,
                PersonSearchRepository {
}
~~~

Implementation following naming convention:

~~~java
public class PersonSearchRepositoryImpl
        implements PersonSearchRepository {

    private final DatabaseClient databaseClient;

    public PersonSearchRepositoryImpl(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Flux<Person> searchByPrefix(String prefix) {
        return databaseClient.sql("""
                SELECT id, first_name, email
                FROM people
                WHERE first_name LIKE :prefix
                ORDER BY id
                """)
            .bind("prefix", prefix + "%")
            .map((row, metadata) -> new Person(
                row.get("id", Long.class),
                row.get("first_name", String.class),
                row.get("email", String.class)
            ))
            .all();
    }
}
~~~

Test through the repository:

~~~java
StepVerifier.create(repository.searchByPrefix("Ada"))
    .expectNextMatches(person ->
        person.firstName().startsWith("Ada")
    )
    .verifyComplete();
~~~

If the fragment implementation needs custom configuration beans absent from the slice, import the needed configuration. Do not widen component scanning to the entire application just to find one implementation.

## 16. Testing Optimistic Locking and Version Fields

If an entity uses @Version for optimistic locking, repository tests should verify that version increments on update and conflicts when updating with a stale version.

Illustrative entity:

~~~java
@Table("inventory")
public record InventoryItem(
    @Id Long id,
    String sku,
    Integer quantity,
    @Version Long version
) {}
~~~

A test can:

1. Insert the entity and read the initial version.
2. Update the entity with the current version.
3. Verify the version incremented.
4. Attempt another update using the object with the stale version.
5. Verify Spring Data emits an appropriate optimistic locking error.

Exact exception names and details depend on the Spring Data R2DBC version. Verify with tests against a real database rather than checking version fields on mocked objects.

## 17. Testing Custom Converters and Data Types

Types such as JSON, enums, UUID, Instant, OffsetDateTime, or value objects can depend on drivers and custom converters.

Tests should cover the round trip:

~~~text
Java value
   |
Write converter
   |
Database column
   |
Read converter
   |
Java value
~~~

Example with an enum:

~~~java
public enum PersonStatus {
    ACTIVE,
    SUSPENDED
}
~~~

Check:

- Enum values are written using the right representation (name, code, or native enum).
- Read values convert back into the expected enum.
- Legacy values or values removed from the enum are handled intentionally.
- Casing and null semantics are consistent.

For JSON columns, test with a database supporting JSON types if production relies on JSON operators/indexes. A JSON string stored in a VARCHAR in H2 does not prove PostgreSQL JSONB mapping works.

## 18. @DataR2dbcTest or @SpringBootTest?

Choose the annotation based on the scope to verify:

| Need | Appropriate annotation |
| --- | --- |
| Repositories, mapping, custom SQL | @DataR2dbcTest |
| R2dbcEntityTemplate/DatabaseClient | @DataR2dbcTest |
| Custom converters in persistence slice | @DataR2dbcTest + @Import |
| Service coordinating multiple repositories | @SpringBootTest or service test with appropriate collaborators |
| WebFlux controllers and HTTP serialization | @WebFluxTest |
| Full application wiring, migrations, and R2DBC | @SpringBootTest |
| End-to-end with real database | @SpringBootTest + Testcontainers |

@DataR2dbcTest keeps tests fast, narrow in scope, and low in dependencies. However, if a test needs to check full-application auto-configuration, Flyway/Liquibase, security, or HTTP routing, a slice test is not enough.

Do not use @SpringBootTest for every repository test if the full context is not needed; startup time and complexity will grow.

## 19. Diagnosing Common Issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Repository bean not found | Repository scanning not enabled or package outside configuration | Check packages and slice configuration |
| No ConnectionFactory | Missing R2DBC driver or wrong URL/credentials | Check dependencies and spring.r2dbc.* |
| Test mistakenly uses embedded DB | Test database replacement is enabled | Use Replace.NONE when configured database is needed |
| Table does not exist | Schema script/migration did not run or wrong schema | Configure SQL init/migration and check schema |
| Query passes on H2 but fails in production | Different dialect or data types | Add Testcontainers for the production database |
| StepVerifier emits no data | Data not inserted or wrong query filter | Chain save with then/flatMap and check bind values |
| Test depends on execution order | Shared data or missing ORDER BY | Use unique data and explicit sorting |
| Test hangs | Publisher never completes, timeout, or blocking in reactive flow | Check queries, subscriptions, and use verify(Duration) |
| Constraint test receives unexpected exception | Different driver/translator | Inspect cause chain, SQLSTATE, and vendor behavior |
| Custom converter does not run | Converter configuration not imported into slice | Use @Import or test configuration |
| Cleanup incomplete | Detached subscribe or not awaiting publisher | Use StepVerifier in test lifecycle |
| Transaction test does not roll back | Reactive context not shared or test transaction support differs by version | Use TransactionalOperator and verify after completion |

### Setting Timeouts for Reactive Tests

You can set a timeout on verify:

~~~java
StepVerifier.create(repository.findAll())
    .expectNextCount(3)
    .verifyComplete(Duration.ofSeconds(5));
~~~

Timeouts make tests fail instead of hanging indefinitely. Do not set timeouts so low that slow CI or container startup is mistaken for a query failure.

## 20. Best Practices When Building a Repository Test Suite

- Use @DataR2dbcTest for persistence-focused tests.
- Use real repositories instead of mocks when verifying SQL and mapping.
- Use StepVerifier to check Mono/Flux signals.
- Create clear schemas and manage test schemas consistently.
- Use embedded databases for portable queries, Testcontainers for vendor-specific behavior.
- Use unique data so tests can run repeatedly and in parallel.
- Do not rely on result order if the query has no ORDER BY.
- Import needed custom converters/configurations rather than booting the whole app.
- Verify constraints, generated IDs, versions, pagination, and data types.
- Do not subscribe manually in test setup/cleanup and finish the test before the publisher completes.
- Separate repository slices from service, web, and end-to-end tests.
- Record database vendor, driver, and version in CI to aid reproduction.

## 21. Workflow for Writing a @DataR2dbcTest

When adding tests for a new repository, follow this sequence:

1. **Define scope:** testing repositories/queries/mapping or also services/web?
2. **Choose database:** embedded for portable behavior; Testcontainers for production database.
3. **Declare slice:** use @DataR2dbcTest and configure replacement if using a real database.
4. **Prepare schema:** schema.sql, migrations, or an appropriate setup script.
5. **Inject repository:** use the real Spring bean.
6. **Create test data:** use distinct IDs/codes/emails per test.
7. **Subscribe and assert:** use StepVerifier for Mono/Flux.
8. **Check boundaries:** empty results, duplicates, nulls, generated IDs, and mapping.
9. **Manage transactions/cleanup:** verify reactive context and await cleanup completion.
10. **Run in CI:** ensure Docker or a test database is ready when using Testcontainers.

@DataR2dbcTest lets you test repositories in a small Spring context focused on reactive persistence. Combining real repositories, clearly managed schemas, StepVerifier, and an appropriate database uncovers SQL, mapping, constraint, and driver bugs that mocks cannot reveal. Use Testcontainers when you need to verify production database behavior, while keeping tests independent via isolated data and proper reactive subscription/cleanup management.
