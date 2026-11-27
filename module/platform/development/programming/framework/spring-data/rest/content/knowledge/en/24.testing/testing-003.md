# Preparing Independent Test Data and Cleaning State Between Test Cases

## Goal

Each test case must prepare the data it owns, verify that exact slice of data, and finish without leaving side effects for subsequent cases. A test must be able to run standalone, run as part of the full suite, and remain independent of execution order.

This is especially critical with Spring Data REST: the framework exports Spring Data repositories as REST resources through Spring MVC. Leftover data can alter collection results, search results, pagination, count checks, or cause duplicate key errors when other tests run.

## 1. Choosing the Right Test Type

- **Unit test:** tests pure logic; replaces repositories or external services with mocks. No need to create database records.
- **Repository test:** for JPA, use `@DataJpaTest` to focus on entity mappings, queries, and repositories. Spring Boot configures repositories and an embedded database if present on the classpath; tests run inside a transaction by default and roll back after each method.
- **Spring Data REST integration test:** when you need to verify exported repositories, URLs, HAL/JSON, query methods, status codes, or HTTP writes, load the real application context with `@SpringBootTest` and use `@AutoConfigureMockMvc`. The default configuration is a mock web environment and does not start a real server.
- **Live-server test:** only use `webEnvironment = RANDOM_PORT` when you need to verify HTTP through a real server, ports, filters, or network-dependent behavior. You must have a separate cleanup plan because client requests and server processing run on different threads and transactions.

`@WebMvcTest` is suitable when testing only selected MVC controllers. It does not automatically load all repositories and Spring Data REST export configurations; use the full application context when the goal is to verify repository-generated resources.

## 2. Creating Independent Fixtures per Test

A good fixture has the following characteristics:

1. Create a new entity every time a factory/builder is called; do not reuse a mutable entity or static collection across multiple tests.
2. Create only the records the test needs. Do not rely on data seeded by other tests or assume the table is empty.
3. Use unique business keys per run, especially for email, username, order code, or slug. You can combine a recognizable prefix with a UUID.
4. Keep data small enough and accurately descriptive of the condition under test. When testing a search endpoint, query by the fixture's unique key instead of asserting the total record count of the entire table.
5. If there are relationships, create all required dependent records and keep references to IDs returned by the repository for accurate cleanup.

Example factory creating a new fixture:

```java
static Customer newCustomerFixture() {
    Customer customer = new Customer();
    customer.setName("Ada");
    customer.setEmail("sdr-" + UUID.randomUUID() + "@example.test");
    return customer;
}
```

Do not store an already-created `Customer` in a `static final` variable and share it across tests. A factory can be static, but each invocation must return a new object and fresh identifying data.

For simple data, create fixtures in `@BeforeEach` or directly inside the test method. Use `@BeforeEach` when multiple tests in the same class need the same initial data structure; use dedicated helpers when each test needs a different state. Avoid `@BeforeAll` for creating shared mutable data across the entire class.

## 3. Preferring Rollback for Tests Running in the Same Transaction

Spring TestContext supports test-managed transactions when the application context has a `PlatformTransactionManager` and the test is annotated with `@Transactional`. The test transaction is rolled back by default after the test finishes. Operations inside Spring-managed transactions normally join this transaction when using appropriate propagation, such as `REQUIRED`.

With JPA repository tests, `@DataJpaTest` enables transactions and rollback by default. There is no need to add `repository.deleteAll()` in `@AfterEach` just to clean up records inside that transaction: the delete statement is also inside the transaction and will roll back with the test.

For Spring Data REST endpoints executed via MockMvc, you can use the following configuration for backends that support transactions (such as JPA):

```java
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class CustomerRestIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    CustomerRepository customers;

    @Test
    void searchReturnsThisTestsCustomer() throws Exception {
        Customer customer = newCustomerFixture();
        customers.save(customer);

        mvc.perform(get("/customers/search/findByEmail")
                .param("email", customer.getEmail())
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.email").value(customer.getEmail()));
    }
}
```

The example assumes the repository is exported by Spring Data REST, has a `findByEmail(String email)` query method, the entity has an `email` field, and the collection resource is `/customers`. Default resource names are derived from the entity name; `@RepositoryRestResource`, base path, or other configurations can change the URL. Search resources only appear when the repository exposes the corresponding query method.

In the test above, the fixture is saved via the repository and the endpoint is invoked in a mock web environment. With synchronous MVC handling and standard transaction propagation, database operations participate in the test transaction; data is rolled back after the method. Do not apply this assumption to async tasks, separate threads, `REQUIRES_NEW` transactions, or backends that do not support transactions in that way.

## 4. Using `@Sql` When Explicit Fixtures or Cleanup Are Needed

For relational databases, `@Sql` allows running scripts before or after a test method. By default, scripts run before the test. Set `executionPhase = AFTER_TEST_METHOD` to run a cleanup script after the test.

The following example is for situations where data must be committed so a real server or another process can see it:

```java
import static org.springframework.test.context.jdbc.Sql.ExecutionPhase.AFTER_TEST_METHOD;
import static org.springframework.test.context.jdbc.Sql.TransactionMode.ISOLATED;

@Test
@Sql(
    scripts = "/sql/customer-fixture.sql",
    config = @SqlConfig(transactionMode = ISOLATED)
)
@Sql(
    scripts = "/sql/customer-cleanup.sql",
    config = @SqlConfig(transactionMode = ISOLATED),
    executionPhase = AFTER_TEST_METHOD
)
void liveEndpointReadsCommittedFixture() {
    // Call endpoint and verify committed data.
}
```

- Place scripts on the test classpath, e.g. `src/test/resources/sql/`.
- Fixture scripts should create data with a test-specific marker; cleanup scripts should only delete rows carrying that marker.
- Use `ISOLATED` when you need a separate transaction committed independently from the test transaction. Cleanup scripts also need an isolated transaction if data was committed elsewhere.
- Delete child records before parent records when foreign keys exist, unless the schema configures appropriate cascades.
- `@Sql` declared on a method overrides class-level declarations by default. Check these rules if sharing scripts at the class level alongside method-specific fixtures.

If both the test and scripts participate in the same test-managed transaction, default rollback is usually sufficient and no separate delete script is needed. Only add independent cleanup when data genuinely escapes the test's transaction rollback.

## 5. Cleaning Up State Outside the Database

Database rollback does not automatically reset all state. Identify which resources a test may modify and clean up those exact resources:

- **Caches or singleton beans:** reset entries/keys created by the test; do not use a cache shared with real data.
- **Message brokers or events:** use test-specific queues/topics, inspect and drain messages emitted by the test; wait for consumers to finish before asserting state.
- **Temporary files or directories:** use test-specific directories and delete them in `@AfterEach` or via `@TempDir`.
- **Mocks and spies:** create/reset per test lifecycle; do not retain shared invocations or mutable mock state unintentionally.
- **Open resources:** close streams, clients, sockets, and executors created by the test.

JUnit Jupiter creates a new test instance for each test method by default (`PER_METHOD`). This isolates fields on the test object, but does not automatically clear databases, static fields, singleton beans, or external services. If `@TestInstance(PER_CLASS)` is enabled, the same test instance is reused for the entire class; you must reset mutable fields in `@BeforeEach` or `@AfterEach`.

`@DirtiesContext` marks the Spring `ApplicationContext` as modified or corrupted so the framework closes and recreates the context when needed. Use this annotation when a test mutates context state, such as a singleton bean that cannot be safely reset. This is not a default cleanup mechanism for individual rows in an external database; you still have to clean up data in the database, broker, or filesystem accordingly. Reloading the context is also time-consuming and can impact parallel tests.

## 6. Avoiding Conflicts During Parallel Execution

If multiple tests access the same database, broker, or filesystem, global cleanup can delete data belonging to another running test. To minimize conflicts:

- Use a UUID or unique namespace for each test invocation.
- Delete by ID or marker belonging to that test; avoid `deleteAll()` on shared repositories.
- Use a dedicated database/schema/container for test groups requiring strong state isolation.
- Do not depend on test order or data created by other tests.
- If a shared resource cannot be isolated, do not run that test group in parallel.
- Do not use `@DirtiesContext` as a fix for race conditions; fix the shared state or exclude the test from parallel execution.

Spring TestContext warns that tests modifying shared system state such as databases, message brokers, or filesystems can fail flakily when run in parallel. Design fixtures and cleanup before enabling parallel execution.

## 7. Execution Workflow for a Spring Data REST Test

1. Identify the exported repository, collection path, query methods, and actual base path.
2. Choose the test type: repository slice, MockMvc with full context, or live server.
3. Create an isolated fixture with unique keys and only the necessary relationships.
4. Exercise behavior via the repository or REST endpoint; check status, representation, data, and required relationships.
5. Choose the right teardown mechanism: transaction rollback; or marker-based cleanup via `@Sql`/repository; while also resetting non-database state.
6. Confirm the test's data no longer exists after cleanup if the test uses commits or a live server.
7. Run the test individually, then run the entire test suite. If parallel execution is enabled, re-run the related group to detect conflicts.

Command to run a single test class (substitute the class name and use the wrapper present in the project):

```bash
./mvnw -Dtest=CustomerRestIntegrationTest test
./gradlew test --tests '*CustomerRestIntegrationTest'
```

On Windows you can use `mvnw.cmd -Dtest=CustomerRestIntegrationTest test` or `gradlew.bat test --tests '*CustomerRestIntegrationTest'`.

## 8. Diagnosing Common Failures

| Symptom | Common cause | How to resolve |
|---|---|---|
| Test passes alone but fails when running the full suite | Stale data, static state, singleton beans, or order dependency | Create fresh fixtures per method; look up data by marker; reset shared state |
| Unique constraint violation | Multiple tests share the same email, username, or business key | Generate unique keys; clean up the exact created records |
| REST collection returns more rows than expected | Test inspects the entire collection in a shared database | Query by unique ID/marker; assert only the slice of data owned by the test |
| POST over RANDOM_PORT leaves data behind despite `@Transactional` on test | Request is processed on a separate server thread and transaction | Clean up after test using `@Sql` with `ISOLATED`/`AFTER_TEST_METHOD`, or use fixture IDs and delete explicitly |
| Cleanup fails due to foreign key constraint | Deleting parent before child | Delete in dependency order or use designed cascades |
| Cleanup script does not run | `@Sql` runs before tests by default or method annotation overrides class annotation | Check `executionPhase`, classpath location, and merge/override rules |
| Data does not roll back | No suitable transaction manager, test lacks `@Transactional`, uses `REQUIRES_NEW`, async/other thread, or test configured to commit | Check transaction manager/propagation; use independent cleanup for committed parts |
| Parallel tests pass and fail intermittently | Multiple tests concurrently mutate database, queue, cache, or files | Separate namespaces/resources or disable parallelism for groups that cannot be isolated |

When diagnosing, log fixture IDs/markers and query those exact records. Avoid running full-table delete commands on a shared database.

## Official Documentation

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): how repositories are exported, collection/item/search resources, and HTTP methods.
- [Spring Data REST — Getting started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): configuring Spring Data REST in Spring Boot.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, mock web environment, `@AutoConfigureMockMvc`, live server, and transaction boundaries.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/): test slices, including `@DataJpaTest`.
- [Spring Framework — Transaction management in TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions, rollback, and lifecycle hooks.
- [Spring Framework — Executing SQL scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): `@Sql`, execution phases, and transaction modes.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing Spring MVC with mock requests/responses.
- [Spring Framework — Context caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): reusing ApplicationContext and when reloading the context is needed.
- [Spring Framework — Parallel test execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): limitations and risks when running tests in parallel.
- [JUnit Jupiter User Guide — Test instance lifecycle](https://docs.junit.org/current/user-guide/#writing-tests-test-instance-lifecycle): `PER_METHOD` and `PER_CLASS` lifecycles.
