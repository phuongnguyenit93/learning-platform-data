# Keeping Data Independent When Multiple Tests Share a Database

When multiple tests share a single database, data created by one test can alter the outcome of another test. A test may pass when run alone yet fail as part of the full suite due to stale records, incremented sequences, deleted data, or two tests modifying the same row. These failures are often hard to reproduce because outcomes depend on execution order, worker count, or leftover database state from prior runs.

In Spring Framework Testing, keeping data independent means every test starts with a deterministic input state and does not let its changes skew other tests. This goal can be achieved via transaction rollback, uniquely identified data, controlled setup and cleanup, dedicated schemas/databases, or a fresh database environment per suite.

No single technique fits every type of test. Synchronous repository tests typically leverage transaction rollback. Tests verifying commits, asynchronous work, or multiple connections may require dedicated databases and explicit cleanup. When running in parallel, both data and resources must be designed to avoid contention.

## 1. Why does sharing a database easily make tests interdependent?

Suppose two tests both operate on the `customer` table:

~~~java
@Test
void createsCustomer() {
    customerRepository.save(new Customer("ada@example.test"));
    assertEquals(1, customerRepository.count());
}

@Test
void startsWithNoCustomers() {
    assertEquals(0, customerRepository.count());
}
~~~

If the first test commits data, the second test may receive `1` instead of `0`. If the execution order is reversed, both might pass. The suite result therefore becomes unstable.

Common causes:

- **Leftover data from previous runs:** a test committed or failed to clean up completely.
- **Shared identifiers:** two tests create customers with the same fixed email or business code, triggering unique constraint errors.
- **Overly broad cleanup:** one test clears a table or truncates data that another test is using.
- **Sequences and auto-increment:** a test assumes IDs always start at a fixed value.
- **Transactions not covering all operations:** code runs on another thread, uses a separate transaction, or opens another connection.
- **Shared state across test workers:** concurrently running tests edit the same record or share the same schema.
- **Time-dependent data:** tests use the current date, timestamp, or expiration state that varies depending on when they run.

An independent test must produce the same result when run alone, run with the suite, run before or after any other test, and run repeatedly in a controlled environment.

## 2. Principles for designing test data

Before selecting tools, apply several foundational principles:

1. **Each test prepares its own required data.** Do not depend on another test having created a fixture.
2. **Use unique identifiers.** Test codes, emails, and business keys must not collide with other tests.
3. **Assert only on data within the test's scope.** Avoid assertions based on total row counts across the whole table if the database might hold other data.
4. **Clean up only the data created by the test.** Do not wipe an entire shared table.
5. **Know transaction boundaries.** Know which operations join the test transaction and which may commit separately.
6. **Control time and random data.** Use a controllable `Clock` or a fixed random seed when needed.
7. **Design for parallel execution.** Do not rely on a fixed execution order or a single fixed set of keys.

For example, instead of checking the total number of customers in the database:

~~~java
assertEquals(1, customerRepository.count());
~~~

you can check the exact record the test just created:

~~~java
Customer saved = customerRepository.save(
    new Customer("customer-test-42", "ada@example.test")
);

assertTrue(customerRepository.findById(saved.getId()).isPresent());
assertEquals(
    "ada@example.test",
    customerRepository.findById(saved.getId()).orElseThrow().getEmail()
);
~~~

Assertions keyed by the fixture's identifier are far less affected by unrelated data in the database.

## 3. Using transaction rollback for synchronous tests

For repository or service tests interacting with the database on the same thread, test transactions are a simple way to isolate changes. Spring TestContext supports test-managed transactions via `@Transactional`. By default, this transaction rolls back after each test method.

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesAndFindsCustomer() {
        Customer customer = new Customer(
            "customer-test-01",
            "ada@example.test"
        );

        Customer saved = customerRepository.save(customer);
        customerRepository.flush();

        Customer loaded = customerRepository.findById(saved.getId())
            .orElseThrow();

        assertEquals("ada@example.test", loaded.getEmail());
    }
}
~~~

With test slices such as `@DataJpaTest`, Spring Boot typically configures test transactions and default rollback. When using `@SpringBootTest` or plain Spring Framework configuration, a suitable `PlatformTransactionManager` and `@Transactional` on the class or method are required.

Transaction rollback helps:

- Prevent records created during a test from persisting after the method finishes.
- Keep fixture setup and the test action inside the same transaction.
- Reduce the need to write cleanup for database operations joining the transaction.
- Allow the test to assert on data before the transaction rolls back.

However, rollback is not an absolute isolation layer for every operation. Check the actual boundaries of the database and application code.

### 3.1. Cases where rollback is not enough

Test rollback does not automatically undo:

- Operations committed inside a `REQUIRES_NEW` transaction.
- Writes performed via another thread not participating in the test's transaction.
- Writes to a datasource managed by a different transaction manager.
- Operations using an independent connection or manually managed transactions.
- Sending messages, calling HTTP services, or writing files outside the database.
- Data committed before the test started.

For example, a service method using `REQUIRES_NEW` can commit independently of the outer test transaction. If a test expects that data to disappear after rollback, that expectation is wrong. Dedicated cleanup or a dedicated test database/schema is needed.

### 3.2. Flush is not commit

With JPA, `save` may only update the persistence context while SQL is sent to the database upon flush. When testing unique constraints or foreign keys, call `flush` so errors surface immediately inside the test:

~~~java
repository.save(new Customer("same@example.test"));
repository.flush();

assertThrows(
    DataIntegrityViolationException.class,
    () -> {
        repository.save(new Customer("same@example.test"));
        repository.flush();
    }
);
~~~

Flushing synchronizes the persistence context with the database within the current transaction. It does not commit the transaction. Once the test finishes, the transaction can still roll back.

## 4. Creating data with unique identifiers

Transaction rollback is helpful, yet not every test runs inside a single transaction. To reduce conflicts, generate unique identifiers per test or per run.

You can use a UUID:

~~~java
String testRunId = UUID.randomUUID().toString();
String email = "customer-" + testRunId + "@example.test";

Customer customer = customerRepository.save(
    new Customer("customer-" + testRunId, email)
);
~~~

Or use the test name combined with a worker ID:

~~~java
String namespace = "it-" + workerId + "-" + testCaseId;
String orderNumber = namespace + "-order-01";
~~~

UUIDs work well when merely avoiding collisions. Structured namespaces are more useful when you need to locate and clean up data after tests. Both can be combined: a run ID identifies the entire run, while the test name identifies the data owner.

### 4.1. Do not assume auto-increment IDs start at 1

Do not write:

~~~java
assertEquals(1L, saved.getId());
~~~

The database may have incremented sequences from previous runs, rollbacks do not necessarily reset sequences, and insert order can vary under parallel execution. Obtain the ID from the saved entity or query by a test-created business key.

~~~java
Customer saved = customerRepository.save(customer);

assertNotNull(saved.getId());
assertTrue(customerRepository.existsById(saved.getId()));
~~~

If IDs are generated from a sequence, tests should verify existence and data relationships rather than relying on a fixed number.

### 4.2. Using builders or factories for fixtures

A factory helps create valid data and reduces repetitive setup:

~~~java
final class CustomerTestData {

    static Customer newCustomer(String namespace) {
        return new Customer(
            namespace,
            namespace + "@example.test",
            "Ada"
        );
    }
}
~~~

Test usage:

~~~java
String namespace = "customer-" + UUID.randomUUID();
Customer customer = CustomerTestData.newCustomer(namespace);

Customer saved = customerRepository.save(customer);

assertTrue(customerRepository.existsById(saved.getId()));
~~~

Factories should create meaningful, easily customizable data. Avoid building giant fixtures with many unnecessary associations, since changing one attribute could affect many tests.

## 5. Controlled data setup and cleanup

When rollback cannot be relied upon, tests need explicit data preparation and cleanup. A safe strategy is tracking the identifiers of records created by the test and deleting those exact records afterward.

~~~java
@SpringBootTest
class CustomerImportIntegrationTest {

    @Autowired
    private CustomerRepository customerRepository;

    private String testNamespace;

    @BeforeEach
    void setUp() {
        testNamespace = "import-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanUp() {
        customerRepository.deleteByTestNamespace(testNamespace);
    }

    @Test
    void importsCustomers() {
        // Import only records carrying testNamespace.
    }
}
~~~

The example assumes the table has a `test_namespace` column and the repository provides a matching delete method. A namespace column does not necessarily belong in the production schema; projects can use an appropriate business key or dedicated fixture table.

Cleanup should have these properties:

- Deletes only data belonging to the current test.
- Can run multiple times without error.
- Deletes in an order that respects foreign keys.
- Executes even when assertions fail.
- Never deletes data created by other tests or other users.

JUnit Jupiter runs `@AfterEach` after each test method, even if a test assertion fails. However, if the JVM exits abruptly or the process is killed, cleanup callbacks are not guaranteed to run. Therefore, namespaced data and run-ID-based cleanup remain valuable.

### 5.1. Deleting in relationship order

If tables have parent-child relationships, cleanup must respect foreign keys:

~~~sql
DELETE FROM order_item
WHERE order_id IN (
    SELECT id FROM orders WHERE test_namespace = :namespace
);

DELETE FROM orders
WHERE test_namespace = :namespace;
~~~

Delete child records before parent records if the database has no appropriate cascade configured. Wrap cleanup in a transaction if you want all delete operations to succeed or roll back together.

### 5.2. Avoid truncating shared tables

Truncating entire tables can be fast yet dangerous when multiple tests or workers share a database. It can:

- Delete fixtures that another test currently needs.
- Cause concurrently running tests to fail randomly.
- Reset identities/sequences differently across databases.
- Be blocked by foreign keys or require elevated privileges.

Only truncate when tests have a dedicated database or schema, or when the entire suite is guaranteed to run exclusively against that database.

## 6. Using @Sql to prepare and clean up data

Spring Test supports `@Sql` to run SQL scripts at various points in the test lifecycle. This approach works well when fixtures span multiple tables, need clear relational data, or when setup/cleanup should live in readable, manageable SQL files.

Example:

~~~java
@SpringBootTest
@Sql(
    scripts = "/sql/customer-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/cleanup-customer-test-data.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
class CustomerQueryIntegrationTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsActiveCustomer() {
        Customer customer = customerRepository
            .findByEmail("active-customer@example.test")
            .orElseThrow();

        assertTrue(customer.isActive());
    }
}
~~~

The setup script can insert required fixtures; the cleanup script deletes the exact test fixture. Files are placed in `src/test/resources/sql` so they are found on the classpath.

### 6.1. Choosing the execution phase

`@Sql` supports these phases:

| Phase | Timing |
|---|---|
| BEFORE_TEST_METHOD | Before each test method |
| AFTER_TEST_METHOD | After each test method |
| BEFORE_TEST_CLASS | Before the test class |
| AFTER_TEST_CLASS | After the test class |

Class-level phases are available starting from the supporting Spring Framework versions; check your project version's API if using them. For fixtures refreshed per test, `BEFORE_TEST_METHOD` and `AFTER_TEST_METHOD` are common choices.

### 6.2. Transaction mode of @Sql

`@SqlConfig` has a `transactionMode` attribute to specify how scripts run in transactions:

- **INFERRED:** Spring infers the transaction from an active transaction or available transaction manager. This is the default mode.
- **ISOLATED:** the script runs in its own transaction, committed independently upon completion.

Example:

~~~java
@Sql(
    scripts = "/sql/seed-customer.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    ),
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
~~~

Use `ISOLATED` when setup must commit so tests see data from another transaction or when scripts need their own transaction boundaries. Because setup data commits independently, test transaction rollback will not delete that fixture automatically. A cleanup script or dedicated namespace is needed to clean up data.

If setup and test both join the test transaction, `INFERRED` usually helps roll back both script-created data and method operations. Verify the exact transaction manager and datasource the script uses.

### 6.3. Using namespaces in SQL scripts

Do not insert the same fixed email into a shared database if tests may run concurrently. You can use a dedicated fixture code passed through an appropriate parameterization mechanism, or create data via repositories/factories before running SQL. If scripts do not support dynamic variables in the way the project needs, use static fixture tables only in a suite-dedicated database.

When fixtures are fixed and only one suite runs exclusively, clearly named data like `active-customer-fixture` may suffice. When multiple workers share a database, distinguish data by worker or run ID.

## 7. Using dedicated databases or schemas per suite

A strong isolation method is provisioning a separate database or schema for each test run. Suites then share neither tables nor data.

Options:

| Strategy | Isolation scope | Pros | Cost |
|---|---|---|---|
| Dedicated database per suite | Entire suite | Clear isolation, easy cleanup | Startup resource overhead |
| Dedicated schema per suite | Tables and sequences | Faster when database supports schemas | Requires schema/search-path config |
| Dedicated database per worker | Tests within a worker | Supports parallel execution | Managing multiple databases |
| Single shared database, per-test namespace | By data group | Lightweight, easy infrastructure sharing | Needs cleanup and collision avoidance |
| Transaction rollback | Per transaction/thread | Fast, minimal cleanup | Does not cover all operations |

Dedicated schemas can be selected via JDBC URL configuration, schema search paths, or connection properties depending on the database. Ensure Flyway/Liquibase and ORM create schemas in the right namespace.

If workers share a database server with separate schemas, each worker can run migrations and cleanup independently. Do not let multiple workers concurrently run migrations or drop a shared schema without synchronization.

## 8. Using Testcontainers to create fresh database environments

Testcontainers can launch databases in containers for integration tests. A dedicated container or database keeps tests independent of local databases or a shared instance from earlier runs.

PostgreSQL example:

~~~java
@Testcontainers
@SpringBootTest
class CustomerDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

The example requires Testcontainers dependencies matching the project version and container lifecycle configuration aligned with the test framework. `@DynamicPropertySource` supplies the generated URL, username, and password to the Spring `Environment` before the `ApplicationContext` is created.

Sharing one container across a class saves time, yet methods must still remain data-independent. A fresh container does not automatically give each method an empty database if methods commit data.

Isolation can be increased by:

- Using transaction rollback for synchronous tests.
- Creating dedicated schemas/databases per worker.
- Using dedicated namespaces for fixtures and cleanup.
- Starting a fresh container for suites or test groups needing a clean environment.

There is no need to launch a container per method when transactions and fixtures already isolate adequately. Balance isolation level, startup time, and resource cost.

## 9. Running parallel tests on a shared database

When JUnit or a build tool runs tests in parallel, two tests can access the database simultaneously. Having each method in its own transaction does not prevent conflicts if they modify the same record or the same unique key.

Example of two tests updating the same row:

~~~java
@Test
void enablesFeature() {
    settingsRepository.updateEnabled("checkout", true);
}

@Test
void disablesFeature() {
    settingsRepository.updateEnabled("checkout", false);
}
~~~

The final outcome depends on commit order. If a test checks the final value of the same record, parallel execution can make assertions flaky.

### 9.1. Each test owns its own data

Prefer creating separate records per test instead of editing one shared fixture. Use UUIDs, worker IDs, or test namespaces in business keys.

~~~java
String key = "feature-" + UUID.randomUUID();
settingsRepository.save(new FeatureSetting(key, false));

settingsRepository.updateEnabled(key, true);
assertTrue(settingsRepository.findByKey(key).orElseThrow().isEnabled());
~~~

### 9.2. Synchronizing when a resource truly must be shared

If tests must operate on the same resource, you can:

- Disable parallel execution for that test group.
- Use JUnit `@ResourceLock` to lock logical resources within the same JVM.
- Use database-level locks if synchronization across multiple processes is needed.
- Split databases/schemas by worker.

`ResourceLock` example:

~~~java
@ResourceLock(
    value = "shared-reference-data",
    mode = ResourceAccessMode.READ_WRITE
)
class ReferenceDataIntegrationTest {
    // Tests in this class access shared data.
}
~~~

`ResourceLock` coordinates tests within the corresponding JUnit execution scope. It does not lock a database across separate Gradle processes, different JVMs, or separate CI jobs. Across multiple processes, database-layer locking or resource separation is needed.

### 9.3. Do not use @Order to fix data dependencies

Setting test execution order can mask issues without making data independent. If test B only passes after test A because A created a fixture, test B cannot run alone and breaks easily when ordering changes.

Each test must prepare its own fixture or use an immutable fixture created before the suite that tests never mutate.

## 10. Managing reference data and immutable fixtures

Some tables contain reference data such as countries, currencies, order statuses, or categories. Tests can safely share reading this data if it is created once and never modified.

Reference data can be created by migrations or suite-level setup scripts:

~~~sql
INSERT INTO currency(code, display_name)
VALUES ('VND', 'Vietnamese Dong')
ON CONFLICT (code) DO NOTHING;
~~~

Upsert syntax varies by database. Use scripts matching the database engine running the tests.

Rules for shared fixtures:

- Data is read-only across tests.
- No test updates or deletes shared fixtures.
- If a test needs a variant, create a copy with its own key.
- Setup configuration must run before tests needing the fixture start.
- Do not depend on leftover data from previous runs; scripts must be safely repeatable or the database freshly created.

If reference fixtures evolve with business rules, version test data or generate it from controlled migrations/fixtures instead of copying data straight from production.

## 11. Controlling time and auto-generated data

Time-dependent data easily causes failures when tests run across midnight, across timezones, or during daylight saving transitions. For example, a test checking order expiration using `LocalDate.now()` may behave differently on another day.

Instead of calling system time directly in business logic, inject a `Clock`:

~~~java
@Service
class SubscriptionService {

    private final Clock clock;

    SubscriptionService(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(Instant.now(clock));
    }
}
~~~

Tests use a fixed clock:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

With stable time, expiration data and date-based queries can be tested repeatedly. For random IDs, use a fixed seed if tests need to reproduce an exact dataset; if only avoiding collisions, UUID is a suitable choice.

## 12. Safe cleanup when tests fail

Cleanup should be designed to run regardless of whether assertions pass or fail. With JUnit Jupiter, you can store a namespace or generated ID in `@BeforeEach` and delete it in `@AfterEach`.

~~~java
class OrderImportTest {

    private String namespace;

    @BeforeEach
    void prepareNamespace() {
        namespace = "order-import-" + UUID.randomUUID();
    }

    @AfterEach
    void removeImportedData() {
        orderItemRepository.deleteByNamespace(namespace);
        orderRepository.deleteByNamespace(namespace);
    }
}
~~~

To prevent cleanup errors from masking the original failure:

- Cleanup must be able to run when no data exists.
- Use delete by namespace rather than full-table queries.
- Clean child tables before parent tables.
- Log cleanup errors if needed while preserving the test's original exception.
- If cleanup needs its own transaction, declare boundaries explicitly.

When tests use a suite-dedicated database, the entire database/schema can be cleaned up at the end of the suite. This is simpler because no other test owns data in that namespace.

## 13. Common mistakes

### 13.1. Using fixed data in a shared database

Fixed emails or order codes can persist from prior runs or be duplicated by parallel tests. Use a unique namespace per test or clean fixtures with proper scope.

### 13.2. Assuming rollback deletes everything

Rollback only affects operations participating in the corresponding transaction. Check `REQUIRES_NEW`, async threads, other datasources, and independent commits.

### 13.3. Full-table cleanup

Unconditional `TRUNCATE` or `DELETE` can destroy another test's data. Only run those operations on suite-dedicated databases/schemas.

### 13.4. Asserting on total row counts

Full-table counts are affected by other fixtures and tests. Check by ID or namespace created by the test.

### 13.5. Depending on execution order

A test that relies on another test instead of creating its own fixture will fail when run alone or in parallel. Put setup inside the test itself or its test helpers.

### 13.6. Relying on fixed auto-increment IDs

Sequences may not reset on rollback and may increment due to other tests. Read the ID from the insert result rather than hard-coding values.

### 13.7. Cleanup running inside a rolled-back transaction

If cleanup runs inside the test transaction and that transaction rolls back, the cleanup operation can also roll back. Determine which transaction cleanup should join and use the right transaction mode.

### 13.8. Using mutable shared fixtures

One test updating a shared fixture can impact other tests. Treat shared reference data as immutable or create an isolated copy.

### 13.9. Running in parallel while locking only within one JVM

`ResourceLock` does not synchronize across multiple JVMs or CI jobs. Use separate schemas/databases or database-level locks when multiple processes exist.

### 13.10. Leaving stale data after abrupt process termination

`@AfterEach` does not run if the JVM is killed. Namespaces keyed by run ID help identify and clean up leftover data under a separate policy.

## 14. Choosing strategies by test type

| Test type | Usually suitable strategy |
|---|---|
| Synchronous repository test | `@DataJpaTest` or `@JdbcTest` with default rollback |
| Service integration test using one datasource | `@Transactional` if you want all test operations rolled back |
| Testing actual service commits | Do not wrap the test in an outer transaction; use dedicated data and cleanup |
| Test using `REQUIRES_NEW` | Dedicated namespace or post-commit cleanup |
| Asynchronous test | Await completion, use dedicated data, and explicit cleanup |
| Multi-datasource test | Specify transaction manager; isolate each datasource or use appropriate distributed transactions |
| Parallel tests | Dedicated keys, dedicated schemas/databases, or unique namespaces |
| Migration/schema verification test | Fresh database or schema per suite |
| API test via embedded server | Dedicated database per suite, clear fixtures, and cleanup |

A sound strategy can combine multiple layers: a fresh database per suite, transaction rollback per method, dedicated namespaces for committed data, and cleanup for non-transactional resources.

## 15. Pattern for organizing repository tests with isolated data

The example below uses a namespace so the test does not depend on total rows in the table:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmail() {
        String namespace = UUID.randomUUID().toString();
        String email = "customer-" + namespace + "@example.test";

        Customer customer = new Customer(namespace, email, "Ada");
        customerRepository.saveAndFlush(customer);

        Optional<Customer> found = customerRepository.findByEmail(email);

        assertTrue(found.isPresent());
        assertEquals(namespace, found.orElseThrow().getExternalId());
    }
}
~~~

The test transaction rolls back after the method by default. Unique namespaces remain valuable because they prevent conflicts with fixtures or concurrent tests while focusing assertions on the test's own record.

## 16. Pattern for organizing tests requiring commit and cleanup

If a test must verify an independently committed transaction, it cannot rely on test transaction rollback to clean up that data. Use a namespace and scoped cleanup:

~~~java
@SpringBootTest
class CommittedImportTest {

    @Autowired
    private ImportService importService;

    @Autowired
    private ImportRepository importRepository;

    private String namespace;

    @BeforeEach
    void createNamespace() {
        namespace = "import-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanCommittedRows() {
        importRepository.deleteByNamespace(namespace);
    }

    @Test
    void commitsImportedRows() {
        importService.importBatch(namespace, sampleRows());

        assertTrue(importRepository.existsByNamespace(namespace));
    }
}
~~~

The example assumes the import service commits in its own transaction and the repository provides namespace-based query/delete methods. If cleanup must commit independently to actually delete data, configure cleanup's transaction explicitly. Never let cleanup accidentally join a transaction that will later roll back.

## 17. Workflow for designing independent data

When writing a new test sharing a database, determine:

1. Does the test run inside a test-managed transaction?
2. Do all operations use the same transaction manager and datasource?
3. Is there async code, `REQUIRES_NEW`, or independent commits?
4. What fixtures does the test need, and can they be created independently?
5. Do identifiers collide with other tests or stale data?
6. Do assertions verify the exact data created by the test?
7. Is cleanup scoped by namespace and respectful of foreign key relationships?
8. Can the test run alone, repeatedly, and in parallel?
9. Is a dedicated database/schema needed for the suite or worker?
10. If the process terminates abruptly, can leftover data be identified for cleanup?

A simple convention for a test suite can be:

- Use a dedicated database/schema per suite.
- Use `@Transactional` rollback for synchronous repository tests.
- Use UUIDs or run IDs for data that must commit.
- Use `@Sql` or factories to create clear fixtures.
- Clean up by namespace; never truncate shared databases.
- Disable parallel execution or use dedicated schemas when tests must mutate the same resource.

## Conclusion

Keeping data independent when multiple tests share a database requires each test to create its own input state, own distinct identifiers, and clean up only its own data. Transaction rollback is an effective choice for synchronous tests, but it does not cover independent commits, asynchronous threads, or other datasources. For those cases, use namespaces, controlled cleanup, `@Sql`, dedicated databases/schemas, or Testcontainers. When also designed for parallel execution and order independence, the test suite becomes far more stable across developer machines and CI.
