# Distinguishing Unit Tests from Data-Access Integration Tests

## 1. Two Types of Tests Answer Two Different Questions

In a Spring Data Relational R2DBC application, testing needs to verify both business logic and how the application communicates with the database. These two goals are related, but they are not the same:

- **Unit tests** verify that a small piece of logic works correctly when its dependencies are controlled. For example, checking that OrderService calculates totals, rejects invalid orders, or coordinates repository calls in the right order.
- **Data-access integration tests** verify that the persistence components actually work together and with the database. For example, checking that a repository generates the right SQL, entities map to the right columns, converters work, constraints are enforced, and transactions roll back as expected.

A unit test can use Mockito to mock a repository. That test is useful for service logic, but it does not prove that SQL queries, mapping metadata, or the R2DBC driver work properly.

An integration test must go through the real data-access path: repository or DatabaseClient, R2DBC ConnectionFactory, driver, and database. It can catch errors that mocks cannot see, though it usually takes longer to run and requires test data management.

Neither type replaces the other. A balanced suite uses unit tests to check many logic branches quickly, and uses integration tests for behavior that depends on Spring Data, the R2DBC driver, or the database management system.

## 2. Testing Boundaries in an R2DBC Application

You can visualize the layers of an application like this:

~~~text
                 HTTP / Message entry point
                            |
                            v
                     Service / Use case
                    /                 \
                   v                   v
             Domain rules         Repository API
                                       |
                         +-------------+-------------+
                         |                           |
                         v                           v
                 Spring Data R2DBC             DatabaseClient
                 Repository / Template          SQL execution
                         |                           |
                         +-------------+-------------+
                                       |
                                       v
                              R2DBC ConnectionFactory
                                       |
                                       v
                                  R2DBC Driver
                                       |
                                       v
                                  Database
~~~

Unit tests usually focus on the service/domain layer and replace the repository with a mock or fake. Data-access integration tests go through the repository/template/DatabaseClient and a real database.

| Component to verify | Appropriate test type |
|---|---|
| Pure Java calculation rules | Unit test |
| Validation and business decisions | Unit test |
| Service handling repository empty/error properly | Unit test with mock publisher |
| Entity mapping and column names | Data-access integration test |
| Derived queries or query annotations | Data-access integration test |
| Template Criteria, Query, and Update | Data-access integration test |
| DatabaseClient SQL and bind parameters | Data-access integration test |
| Custom R2dbcConverter | Data-access integration test |
| Unique/foreign key/check constraints | Data-access integration test |
| Generated ID and version | Data-access integration test |
| Transaction rollback across multiple statements | Integration test with database |
| SQL dialect and production driver behavior | Integration test on the target database |
| Query plan and performance | Performance test in an appropriate environment |

A test that starts a Spring context is not necessarily a data-access integration test. If the repository is still mocked and there is no database, that test only verifies coordination logic among beans. Conversely, a test that does not start all of Spring Boot can still be an integration test if it uses the R2DBC driver and a real database to execute statements.

## 3. What Is a Unit Test?

A unit test checks a single unit of logic within a narrow scope. That unit can be a class, a service method, or a domain function. The goal is to test the behavior of the code you own without depending on whether a database, network, or external system is available.

Service example:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> register(RegisterCustomer command) {
        if (command.email() == null || command.email().isBlank()) {
            return Mono.error(
                    new IllegalArgumentException("Email is required")
            );
        }

        Customer customer = new Customer(
                null,
                command.name().trim(),
                command.email().trim().toLowerCase(Locale.ROOT),
                "ACTIVE"
        );

        return repository.save(customer);
    }
}
~~~

A unit test can mock CustomerRepository to check:

- Blank emails are rejected.
- Names are trimmed.
- Emails are normalized.
- The service calls save with the right entity.
- The result from the repository is emitted to the caller.
- Errors from the repository are propagated or translated according to the contract.

The test does not need to spin up H2 or PostgreSQL because the target is CustomerService's logic.

### 3.1. Unit Tests Do Not Test the Real Repository

When a repository is mocked, the call:

~~~java
when(repository.save(any(Customer.class)))
        .thenReturn(Mono.just(savedCustomer));
~~~

does not execute SQL. Mockito simply returns the publisher defined by the test. Therefore, the test cannot detect:

- Wrong table or column declarations.
- Query methods generating incorrect SQL.
- The database rejecting a data type.
- Missing unique constraints.
- Unregistered converters.
- An R2DBC driver not supporting a Java type.
- The transaction manager not participating in the operation.

This is not a flaw in Mockito. It is the intentional boundary of a unit test. You should not expect a mock to prove database behavior.

## 4. Writing Reactive Unit Tests with Mockito and StepVerifier

In R2DBC code, services typically return Mono or Flux. Unit tests should consume the publisher and verify signals using Reactor Test, typically StepVerifier.

Example:

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    @InjectMocks
    CustomerService service;

    @Test
    void shouldNormalizeEmailBeforeSaving() {
        RegisterCustomer command = new RegisterCustomer(
                "An Nguyen",
                "  AN@EXAMPLE.TEST "
        );

        Customer saved = new Customer(
                10L,
                "An Nguyen",
                "an@example.test",
                "ACTIVE"
        );

        when(repository.save(any(Customer.class)))
                .thenReturn(Mono.just(saved));

        StepVerifier.create(service.register(command))
                .expectNext(saved)
                .verifyComplete();

        ArgumentCaptor<Customer> captor =
                ArgumentCaptor.forClass(Customer.class);

        verify(repository).save(captor.capture());

        assertThat(captor.getValue().email())
                .isEqualTo("an@example.test");
        assertThat(captor.getValue().name())
                .isEqualTo("An Nguyen");
    }
}
~~~

This test verifies service behavior and the entity passed to the repository. It does not verify how the entity is stored in the database.

A few notes:

- You must subscribe to the publisher in the test, for example with StepVerifier, so the reactive pipeline executes.
- Use ArgumentCaptor to inspect the data passed to a dependency.
- Do not call subscribe() separately and immediately run assertions right after.
- Avoid arbitrary block() calls in production code. In tests, StepVerifier keeps reactive verification clear and bounded by timeouts.
- If a service has multiple dependent publishers, verify ordering and signals with appropriate operators/publishers.

### 4.1. Testing Validation Without Calling the Repository

~~~java
@Test
void shouldRejectBlankEmail() {
    RegisterCustomer command = new RegisterCustomer(
            "An Nguyen",
            " "
    );

    StepVerifier.create(service.register(command))
            .expectErrorMatches(error ->
                    error instanceof IllegalArgumentException
                    && error.getMessage().equals("Email is required"))
            .verify();

    verifyNoInteractions(repository);
}
~~~

This is a good unit test because it verifies that the service rejects the request before touching persistence.

### 4.2. Testing a Repository Returning Empty

~~~java
@Test
void shouldPreserveEmptyResult() {
    when(repository.findById(99L)).thenReturn(Mono.empty());

    StepVerifier.create(service.findById(99L))
            .verifyComplete();
}
~~~

If the service turns empty into a business error, check for that exact exception. Mock publishers let you quickly reproduce success, empty, and error branches that are hard to trigger deterministically with a database.

### 4.3. Testing Errors from a Repository

~~~java
@Test
void shouldPropagateRepositoryFailure() {
    RuntimeException databaseFailure =
            new RuntimeException("database unavailable");

    when(repository.findById(10L))
            .thenReturn(Mono.error(databaseFailure));

    StepVerifier.create(service.findById(10L))
            .expectErrorMatches(error -> error == databaseFailure)
            .verify();
}
~~~

If the service is responsible for translating technical errors into business errors, unit tests should verify that mapping. Verifying actual SQLState or vendor error codes belongs in integration tests on the corresponding driver/database.

## 5. Fakes, Stubs, and Mocks in Unit Tests

Test doubles can replace dependencies, but they serve different purposes:

- **Stub:** returns predefined data to exercise logic branches.
- **Mock:** both returns results and lets you verify calls, arguments, or interaction order.
- **Fake:** a simple implementation with realistic behavior that does not use a production database, such as an in-memory repository backed by a Map.

Fake repository example:

~~~java
class InMemoryCustomerRepository
        implements CustomerRepository {

    private final Map<Long, Customer> customers = new HashMap<>();
    private final AtomicLong ids = new AtomicLong();

    // Required methods implemented using in-memory data.
}
~~~

Fakes can be useful when many unit tests need consistent repository behavior. However, a fake must obey the contract the service relies on. A simple fake may not reproduce constraints, concurrency, or SQL semantics.

Avoid building an overly complex fake database in unit tests. If you need to test mapping, constraints, or queries, use an integration test with a database.

## 6. When Should You Not Mock a Repository?

Do not mock the repository in every test just because the application uses R2DBC.

If the goal is to test a repository method, query, mapping, or transaction, mocking the repository skips the very component you want to verify.

For example, this test has no value for proving that a query method works:

~~~java
when(repository.findByStatus("ACTIVE"))
        .thenReturn(Flux.just(customer));

StepVerifier.create(repository.findByStatus("ACTIVE"))
        .expectNext(customer)
        .verifyComplete();
~~~

It only verifies that the mock returns the value set up by the test. No SQL is executed.

For repository tests, inject the real Spring Data-created repository and use a database. Mocks are only appropriate when the repository is a dependency of the unit of logic under test.

## 7. What Is a Data-Access Integration Test?

A data-access integration test verifies that multiple persistence components work together. A typical test may involve:

1. Spring creating the repository or R2dbcEntityTemplate.
2. ConnectionFactory creating a connection via the R2DBC driver.
3. The driver sending SQL to the database.
4. The database executing queries and constraints.
5. Spring Data mapping rows into entities or DTOs.
6. The test verifying the results and data state.

Examples of what to verify:

- @Table and @Column map properly.
- @Id receives a generated value.
- Derived queries return the right rows.
- @Query uses bind parameters accurately.
- Template Criteria and Sort build appropriate conditions.
- Custom conversions work in both directions.
- Unique constraints reject duplicates.
- Transactions roll back multiple operations.
- Database-specific SQL runs on the right engine.

Integration tests are typically slower than unit tests because of startup, connection acquisition, SQL execution, and cleanup. However, they provide necessary proof for persistence-dependent behavior.

## 8. Testing Repositories with @DataR2dbcTest

Spring Boot provides @DataR2dbcTest to create a test slice focused on R2DBC components. A test slice typically limits the ApplicationContext to repository/persistence-related configuration, starting faster than a full application context.

Example:

~~~java
@DataR2dbcTest
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void shouldPersistAndReadCustomer() {
        Customer input = new Customer(
                null,
                "An Nguyen",
                "an@example.test",
                "ACTIVE"
        );

        StepVerifier.create(
                repository.save(input)
                        .flatMap(saved ->
                                repository.findById(saved.id())
                        )
        )
        .assertNext(found -> {
            assertThat(found.id()).isNotNull();
            assertThat(found.name()).isEqualTo("An Nguyen");
            assertThat(found.email()).isEqualTo("an@example.test");
        })
        .verifyComplete();
    }
}
~~~

This is an integration test because the real repository executes operations over R2DBC. The test configuration must provide a suitable ConnectionFactory and schema. Depending on the Spring Boot version and classpath dependencies, the test slice may pick an embedded database or require explicit URL/bean configuration.

Do not assume @DataR2dbcTest automatically creates a schema matching every entity. The schema may come from an initializer script, a migration tool, or dedicated test configuration.

### 8.1. When You Need Additional Beans in the Test Slice

A test slice does not load all application beans. If a repository needs custom converters, callbacks, or custom configuration, import the required configuration:

~~~java
@DataR2dbcTest
@Import(CustomerR2dbcConfiguration.class)
class CustomerRepositoryIntegrationTest {
    // Real repository and required persistence beans.
}
~~~

Only import the components you need to test. If the goal is to verify full-application wiring, migrations, or service transaction boundaries, you can use @SpringBootTest.

### 8.2. Testing Repositories Without Starting an HTTP Server

A repository-access test usually does not need a WebServer. @DataR2dbcTest avoids initializing controllers, security filters, schedulers, and unrelated beans. As a result, the test stays focused on persistence and gives faster feedback than a full context.

If you need to test controllers, serialization, security, and repositories together in a single request, that is a broader application-level integration test.

## 9. Testing SQL and Mapping Through DatabaseClient

When using DatabaseClient, integration tests should send real SQL and check row mapping:

~~~java
@DataR2dbcTest
class CustomerQueryIntegrationTest {

    @Autowired
    DatabaseClient databaseClient;

    @Test
    void shouldMapSummaryFromSql() {
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
                .expectNextMatches(summary ->
                        summary.name().equals("An Nguyen"))
                .verifyComplete();
    }
}
~~~

This test verifies that the database understands the SQL, named parameters are bound, columns are returned, and the map callback builds the DTO properly.

For raw SQL, use a matching test schema and bind all data values. Do not concatenate input directly into SQL strings. If a query depends on a production dialect feature such as PostgreSQL ON CONFLICT, JSONB, or RETURNING, run the test on PostgreSQL rather than rewriting the query into a different syntax and assuming the same behavior is verified.

## 10. Testing Entity Mapping and Converters

Mapping is the responsibility of Spring Data R2DBC and the driver, so it requires integration testing.

Entity example:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        @Column("display_name") String name,
        @Column("email_address") String email,
        String status
) {}
~~~

Schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(320) NOT NULL,
    status VARCHAR(30) NOT NULL
);
~~~

An integration test that inserts and reads back can catch mismatches between properties and columns.

For custom value objects, test both the writing converter and the reading converter:

~~~java
public record EmailAddress(String value) {}
~~~

~~~java
@WritingConverter
class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

~~~java
@ReadingConverter
class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

A unit test can invoke a converter directly to verify its transformation. However, only an integration test confirms that Spring Data registered and uses the converter in the read/write pipeline.

If production uses native types like UUID, JSONB, or enums, run tests against the production database and driver because H2 may represent those types differently.

## 11. Testing Constraints and Database Errors

A unit test with a mock can simulate a repository emitting DuplicateKeyException, but it does not prove the database actually has a unique constraint.

An integration test should create two records with duplicate business keys:

~~~java
@Test
void shouldRejectDuplicateEmail() {
    Customer first = new Customer(
            null, "An", "an@example.test", "ACTIVE"
    );

    Customer duplicate = new Customer(
            null, "Another", "an@example.test", "ACTIVE"
    );

    StepVerifier.create(
            repository.save(first)
                    .then(repository.save(duplicate))
    )
    .expectError()
    .verify();
}
~~~

The test requires a unique constraint in the schema. If a test only checks for a generic exception, it verifies that the operation failed, though not necessarily for the right reason. You can inspect the exception chain, SQLState, or constraint name when the application relies on that error classification. Vendor error codes should be tested against the production database.

Constraints should be tested individually:

- Primary key.
- Unique constraint.
- Not-null.
- Check constraint.
- Foreign key.
- Delete/update referential behavior.

Do not assume H2 and the production database handle NULL, collation, or deferred constraints identically.

## 12. Testing Transactions and Rollback

A unit test can verify that a service chains publishers correctly, but it cannot prove the database rolls back multiple statements in a transaction.

An integration test needs a real transaction manager and must execute at least two database operations within the same boundary. For example:

~~~java
@Transactional
public Mono<Order> createOrderThenFail(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(savedOrder ->
                    orderLineRepository.saveAll(toLines(savedOrder.id(), command))
                            .then(Mono.error(
                                    new IllegalStateException("force rollback")
                            ))
            );
}
~~~

The test can verify that the publisher emits an error, then query the data again in an operation outside the finished transaction to ensure both Order and OrderLine rolled back.

Keep in mind:

- The service method must be invoked through a Spring proxy if relying on annotations.
- The entire publisher must be returned and subscribed to.
- Repositories must use the same ConnectionFactory/transaction manager.
- Do not call subscribe() separately inside the service.
- Do not swallow errors before the transaction interceptor sees them.
- The test should not accidentally open an outer transaction that masks commit/rollback results.

With H2, basic rollback tests can be useful. For isolation, locking, deadlocks, cancellation, or concurrent updates, test on the production engine.

## 13. Service Unit Tests and Repository Integration Tests Complement Each Other

An order-placement use case can be tested at two layers.

**OrderService unit tests:**

- Invalid input values are rejected.
- The service creates Order with the proper initial status.
- The service calls the repository to save Order.
- Order's ID is used when creating OrderLine items.
- Errors from the OrderLine repository are propagated properly.
- The final result is mapped to OrderResponse.

The repositories are mocked, so tests run fast and can cover many error branches.

**OrderRepository/OrderLineRepository integration tests:**

- Entity mapping is accurate.
- Generated IDs are returned.
- OrderLine foreign keys point to a valid Order.
- Quantity constraints are enforced.
- Queries finding orders by customer return the right data.
- A transaction saving Order and OrderLine rolls back together.

There is no need to repeat every business branch in integration tests. Integration tests should focus on persistence contracts and a few critical end-to-end flows.

## 14. H2 and Testcontainers: Choosing a Database for Integration Tests

Integration tests need a database, though not every test needs the same kind of database.

### 14.1. H2 for General Relational Testing

H2 can be suitable for fast checks of:

- Basic CRUD.
- Entity mapping.
- Common repository derived queries.
- Portable SQL.
- Simple constraints.
- Some basic transaction flows.

The advantages are fast startup and no need for a database server. However, H2 has its own dialect, data types, collation, transactions, locking, and query planner.

Passing an H2 test does not prove that PostgreSQL or MySQL will behave the same way.

### 14.2. Testcontainers for Production Databases

If production uses PostgreSQL, use a PostgreSQL container for tests that need to verify:

- SQL dialect.
- JSONB, arrays, enums, and native types.
- ON CONFLICT and RETURNING.
- Migrations.
- Generated values and sequences.
- Locking, isolation, and concurrency.
- Constraints/error codes.
- Production R2DBC driver behavior.

Example:

~~~java
@Testcontainers
@DataR2dbcTest
class CustomerPostgresRepositoryTest {

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

This is a conceptual configuration example; it requires Testcontainers dependencies, the R2DBC PostgreSQL driver, and corresponding schema setup. If the test needs Flyway, also configure the JDBC URL/user/password pointing to the same container and ensure migrations run before the test.

### 14.3. Do Not Use H2 to Benchmark Production

H2's query plans and performance do not represent the production database. Benchmarks need an engine, version, schema, indexes, data, and configuration close to production. H2 primarily helps verify functional logic quickly.

## 15. Testing Migrations Is a Separate Responsibility

Testing repositories against schema.sql does not verify that production migrations run properly. schema.sql might have been written differently from migrations, or a migration might contain dialect-specific syntax.

Migration integration tests should:

1. Start an empty database.
2. Run Flyway or Liquibase over JDBC if the tool uses JDBC.
3. Verify migration history.
4. Access the newly created schema through R2DBC.
5. Run several key repository operations.
6. Test upgrades from a previous schema version if needed.

In an R2DBC application, Flyway using JDBC does not mean repository tests are using JDBC. Migration and runtime are two separate connection paths. Tests should verify that both point to the same database/schema.

When a test only checks CRUD with schema.sql, make it clear that it is a persistence test on a schema fixture, not a migration test.

## 16. @DataR2dbcTest or @SpringBootTest?

| Criterion | @DataR2dbcTest | @SpringBootTest |
|---|---|---|
| Scope | Persistence slice | Broad or full application context |
| Real repository | Yes | Yes if configured by the application |
| Real database | Configurable | Configurable |
| Controller/security | Usually not loaded | Can be loaded |
| Services and full-app wiring | Only when imported | Yes |
| Migrations | Depends on auto-configuration/imports/config | Well-suited for testing full-app startup and migrations |
| Startup time | Usually faster | Usually slower |
| Use case | Repositories, mapping, converters, queries | Multi-bean integration flows and startup/migrations |

Do not use @SpringBootTest for every repository test when a small slice is sufficient. Equally, do not force full-application tests into @DataR2dbcTest when the goal includes controllers, security, migration ordering, or broad configuration.

Choose the annotation based on the scope of behavior to verify, not out of habit.

## 17. Testing Reactive Code Does Not Mean Mocking Every Publisher

StepVerifier works with publishers from mocks as well as publishers from real databases.

In unit tests, publishers are usually stubbed:

~~~java
when(repository.findById(10L))
        .thenReturn(Mono.just(customer));
~~~

In integration tests, the publisher comes from a real repository:

~~~java
StepVerifier.create(repository.findById(10L))
        .expectNextMatches(customer ->
                customer.id().equals(10L))
        .verifyComplete();
~~~

StepVerifier verifies Reactive Streams signals such as:

- onNext and emitted values.
- complete.
- error and error type.
- Element order.
- Element count.
- Timeouts or cancellation in properly coordinated tests.

StepVerifier does not determine whether a test is unit or integration. That depends on the publisher source and which real components are included in the test.

## 18. Testing Cancellation, Backpressure, and Concurrency

These are important reactive pipeline behaviors, though not every application needs to test them at every layer.

**Unit tests** can verify that a service composes publishers and handles cancellation/errors according to its code contract. You can use TestPublisher or PublisherProbe to control sources and verify subscriptions.

**Integration tests** need a real database when you want to verify whether cancellation properly frees result streams/connections or whether concurrency produces the expected database behavior.

Examples of scenarios requiring tests on the production database:

- Multiple requests updating the same row.
- Optimistic locking with @Version.
- Pessimistic locking or SELECT FOR UPDATE.
- Deadlocks and transaction retries.
- Transaction isolation.
- Cancelling a subscription while Flux is reading many rows.
- Pool saturation under multiple concurrent streams.

Do not infer PostgreSQL locking from H2. You need multiple real connections/transactions and coordinated test data to reproduce race conditions.

## 19. Test Isolation and Data Management

Integration tests can mutate a shared database. Without data isolation, tests that depend on execution order or run in parallel can fail intermittently.

Some strategies:

- Dedicated database/schema per test suite.
- Dedicated container for test groups needing strong isolation.
- Create data with unique keys per test.
- Clean up fixtures after tests using fully consumed publishers.
- Reset the schema when tests require a completely fresh initial state.
- Avoid running tests in parallel on the same schema if tests perform whole-table cleanup.

Example of preparing data right inside the pipeline:

~~~java
Mono<Void> arrange = repository.deleteAll()
        .then(repository.save(
                new Customer(null, "An", "an@example.test", "ACTIVE")
        ))
        .then();

StepVerifier.create(
        arrange.thenMany(repository.findByStatus("ACTIVE"))
)
.expectNextMatches(customer ->
        customer.email().equals("an@example.test"))
.verifyComplete();
~~~

This snippet simplifies the fixture; with multiple rows, you can use saveAll. What matters is that setup completes before assertions run.

Avoid calling subscribe() during setup and immediately running assertions because the write operation may not have finished yet. In reactive tests, chain setup and action into a single publisher or use a lifecycle mechanism that properly awaits completion.

### 19.1. Transaction Tests and Cleanup

Do not assume every R2DBC test slice automatically rolls back data after each test. Check the semantics of your Spring Boot/Spring Test version and how transactions are configured. If automatic rollback is not active, clean up data proactively or use an isolated database.

With reactive transactions, context propagates via Reactor Context. Do not assume an imperative ThreadLocal-bound test transaction automatically wraps a reactive publisher. If a transaction boundary is required, configure a ReactiveTransactionManager and explicitly verify how the test executes.

### 19.2. Do Not Use an Uncontrolled Shared In-Memory Database

If multiple test contexts share the same H2 in-memory database name, they may share the database depending on the URL and connection lifecycle. When running in parallel, one test can delete another test's data.

Name databases distinctly per suite/context, use separate containers, or control parallel execution. Do not rely on test ordering to leave leftover data behind.

## 20. Testing Errors at the Right Layer

Errors can originate in the service, mapping, driver, or database. Test them at the responsible layer:

| Error | Where to test? |
|---|---|
| Blank email accepted | Service/domain unit test |
| Service fails to turn empty into NotFound | Service unit test |
| Service calls save with wrong entity | Unit test with captor |
| @Column maps to wrong column name | Repository integration test |
| Query annotation has syntax error | Integration test with database |
| Null bound with wrong type | Integration test with driver |
| Unique constraint does not work | Database integration test |
| Converter not registered | Spring Data mapping integration test |
| R2DBC driver returns unexpected type | Production driver integration test |
| Transaction does not roll back | Integration test with transaction manager |
| Wrong SQLState/vendor error code | Integration test on target database |
| Slow query or missing index usage | Performance test on production-like database |

A unit test can construct a fake exception to test service mapping, but it should not claim that the fake exception accurately reflects a vendor exception. Integration tests verify the real errors emitted by the database/driver.

## 21. Avoid Common Anti-Patterns

- **Mocking the repository and calling it a repository integration test:** no SQL is executed.
- **Using H2 to verify PostgreSQL-specific SQL:** dialects and semantics are not fully equivalent.
- **Only having integration tests and skipping unit tests:** many small logic branches become slow to run and hard to diagnose.
- **Only having unit tests and never testing the database:** mapping, queries, and constraints can be broken while the suite stays green.
- **Calling subscribe() inside services or test setup:** creates an execution flow detached from the publisher under test.
- **Using block() in production reactive code:** can block the event loop and break composition.
- **Sharing a database across parallel tests without isolation:** causes order-dependent failures.
- **Relying on schema.sql without testing migrations:** production migrations may fail.
- **Asserting too tightly on generated SQL when only checking results:** tests become brittle when implementation changes without changing behavior.
- **Not testing native queries against the production database:** bugs only surface during real deployment.
- **Running Testcontainers for every unit test:** sacrifices the speed and narrow scope of unit tests.
- **Benchmarking performance with in-memory H2:** results do not represent the production engine.

## 22. Organizing a Test Suite by Layer

A practical structure might look like:

~~~text
src/test/
├── java/
│   └── com/example/
│       ├── unit/
│       │   ├── CustomerServiceTest.java
│       │   └── OrderServiceTest.java
│       ├── r2dbc/
│       │   ├── CustomerRepositoryTest.java
│       │   └── CustomerMappingTest.java
│       └── postgres/
│           ├── CustomerPostgresQueryTest.java
│           ├── OrderTransactionTest.java
│           └── FlywayMigrationTest.java
└── resources/
    └── db/
        └── test-data.sql
~~~

Package names are only suggestions. You can organize by module or domain instead of by test type.

A CI execution strategy:

1. Run unit tests frequently during development.
2. Run H2 R2DBC tests for common repository/mapping checks if the project uses H2.
3. Run Testcontainers tests for production-specific dialects, migrations, types, and transactions.
4. Run concurrency/performance groups separately as needed.
5. Do not skip production database tests in the release pipeline.

If CI duration is a concern, categorize tests with JUnit tags or Gradle test tasks. Keep grouping transparent; critical tests must not be accidentally excluded from release gates.

## 23. Example Testing Strategy for One Use Case

Suppose a customer creation use case normalizes email, saves the customer, and writes an audit record.

### CustomerService Unit Tests

Mock the repository and audit service to verify:

- Email is normalized.
- Invalid email is rejected.
- Repository is called exactly once.
- Audit service is called only when saving succeeds.
- Save errors are propagated properly.
- Returned result contains the ID from the repository.

### Repository Integration Tests

Use a real R2DBC database to verify:

- Customer is inserted.
- ID is generated and returned.
- Email is stored in the right column.
- Unique constraint rejects duplicate emails.
- Query finding customer by email works.
- Converters are used.

### Transaction Integration Tests

If customer and audit row must be atomic:

- Call the real transactional service.
- Force the audit step to fail in a controlled way.
- Verify the customer is not committed when full rollback is required.
- Verify the error is emitted properly.
- Check via a query after the transaction has ended.

### Production Database Tests

If using PostgreSQL-specific SQL or JSONB:

- Start PostgreSQL with Testcontainers.
- Run real migrations.
- Execute native SQL statements.
- Check mapping and constraints on PostgreSQL.

One use case may require multiple small tests across different layers. Each test should have one clear goal, avoiding one massive test that checks validation, HTTP, SQL, transactions, messaging, and responses all at once and makes failures hard to pinpoint.

## 24. Measuring Speed and Reliability of the Test Suite

A good test suite must be fast enough to run frequently and realistic enough to catch important bugs.

Track:

- Unit test duration.
- Spring context startup time.
- Database/container startup time.
- Number of flaky tests.
- Retry rate for tests.
- Cleanup duration.
- Number of tests sharing a database.
- Coverage of critical queries/mappings/transactions.

If multiple tests share a @SpringBootTest, Spring Test context caching can reduce startup costs. However, do not use context sharing as an excuse to share database state across tests.

Optimize the suite by setting clear boundaries, reusing containers/contexts in a controlled way, and starting only the components needed. Do not drop important integration tests just to shorten CI time.

## 25. Checklist for Choosing a Test Type

Before writing a test, determine:

1. Is the test verifying service/domain logic or persistence behavior?
2. Does real SQL need to be executed?
3. Do entity mapping or converters need verification?
4. Does the database need to enforce constraints?
5. Does it depend on a SQL dialect or vendor type?
6. Do transactions, locking, or concurrency need verification?
7. Should the repository be a mock or a real repository in this test?
8. Is H2 sufficient for common queries, or is Testcontainers with the production DB needed?
9. Does the schema come from fixtures or real migrations?
10. Does the test isolate data and support parallel execution?
11. Is the publisher consumed with StepVerifier or another explicit mechanism?
12. Does the test verify observable behavior rather than implementation details?

Rules of thumb:

- **Unit test:** mock/fake dependencies; focus on logic, input/output, errors, and reactive orchestration.
- **Data-access integration test:** real repository/template/DatabaseClient, R2DBC driver, and database; focus on SQL, mapping, constraints, and transactions.
- **Production database integration test:** target engine/driver; focus on dialect, migrations, types, locking, and concurrency.
- **Performance test:** production-like environment with representative data and load.

## 26. Conclusion

Unit tests and data-access integration tests have different boundaries. Unit tests isolate a single unit of logic, typically replacing repositories with mocks or fakes to quickly verify business branches and how a service handles Mono/Flux. They do not execute SQL and do not prove Spring Data mapping or database behavior.

Data-access integration tests go through the repository, R2dbcEntityTemplate or DatabaseClient, ConnectionFactory, R2DBC driver, and database. They verify queries, entity mapping, converters, generated IDs, constraints, transactions, and engine-dependent behavior. @DataR2dbcTest suits many persistence slice tests; @SpringBootTest fits when full-app wiring or startup/migrations are needed. H2 can help verify common relational behavior, while Testcontainers with the production database is necessary for dialect-specific SQL, migrations, types, locking, and concurrency.

An effective suite uses unit tests to check many logic branches at high speed and integration tests to verify real persistence contracts. Choose tests based on the behavior you need to prove, consume publishers explicitly, isolate data, and keep a group of tests running against the real production database in your release pipeline.
