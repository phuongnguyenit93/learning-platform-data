# Avoiding Context Restarts Just to Clean Up Business Data

Spring Test can reuse `ApplicationContext` instances across multiple test classes with equivalent configurations. This caching mechanism reduces execution time significantly, especially with `@SpringBootTest` having many beans, auto-configuration, and infrastructure connections. However, after a test, the database or cache may still contain data created by the test. When encountering leftover state, an easy impulse is to mark the context with `@DirtiesContext` so Spring closes the current context and creates a new one.

This is usually an overly broad cleanup approach. `ApplicationContext` manages beans and configuration; business data resides in databases, caches, message brokers, filesystems, or external services. Closing the context does not automatically delete that data. If the goal is merely to restore test data to its initial state, clean the actual data source using transaction rollbacks, SQL scripts, repositories, or appropriate cleanup APIs. Reserve `@DirtiesContext` for cases where the state of the context itself or shared beans was altered and cannot be safely restored.

## 1. Distinguishing the ApplicationContext Cache From Business Data

In a Spring test, multiple distinct layers of state can exist:

| Type of state | Example | Usually appropriate cleanup approach |
| --- | --- | --- |
| Spring `ApplicationContext` | Bean definitions, singleton beans, configuration, proxies, listeners | Keep the context if still valid; use `@DirtiesContext` when the context itself was altered unrecoverably |
| Database data | Customer, Order, Invoice, audit records | Transaction rollback, delete by test ID, SQL cleanup, or separate schema/database |
| Application cache | Values in Caffeine, Redis, or Spring Cache | Evict keys or clear test namespace |
| Sent messages and events | Messages in queues/topics, persisted events | Use separate queues/topics, separate consumer groups, or purge APIs for test environments |
| Files and object storage | Exported files, images, objects in buckets | Temporary directories, dedicated prefixes, or delete exact objects created by the test |
| External service state | Records in payment sandboxes, webhooks, or mock systems | Reset/cleanup APIs, unique IDs, or dedicated sandboxes |

The Spring Test context cache holds `ApplicationContext` instances with equivalent configurations so subsequent tests can reuse them. This cache is not a business data cache. When a context is closed, beans and resources attached to the context are destroyed per lifecycle; external databases, Redis, brokers, or other services retain their state unless a dedicated cleanup mechanism runs.

For example, a test creates an order in PostgreSQL and then calls `@DirtiesContext` after the method. Spring may close the context and remove it from the context cache, yet the row in `orders` still exists in the database. The next test loads a new context and still sees the old order. Therefore, a context restart does not address the true cause of leftover data.

## 2. The Cost of Marking a Context Dirty

`@DirtiesContext` instructs Spring Test to mark the current `ApplicationContext` as unusable and remove it from the cache according to the specified mode. When another test needs the same configuration, Spring must load a new context.

Restarting a context can entail:

- Scanning components, processing configuration classes, and creating bean definitions.
- Initializing datasources, connection pools, ORM, security filters, HTTP clients, and singleton beans.
- Running migrations, starting embedded servers, or opening connections to brokers if required by configuration.
- Reinitializing internal bean caches and context-bound resources.
- Increasing execution time and CPU, memory, socket, or connection consumption in the pipeline.

If one test class marks dirty after every method, multiple test classes may continuously reload the same context. A test suite that could have reused contexts becomes slower and less predictable.

Example:

```java
@SpringBootTest
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
class OrderServiceIntegrationTest {

    @Test
    void createsOrder() {
        // ...
    }

    @Test
    void cancelsOrder() {
        // ...
    }
}
```

In `AFTER_METHOD` mode, the context is marked dirty after each test method. If two tests merely insert or delete Order records, reloading the entire context is far too expensive and does not directly handle database data.

## 3. When Is `@DirtiesContext` Actually Appropriate?

`@DirtiesContext` is appropriate when a test alters the state of the `ApplicationContext` itself such that subsequent tests can no longer receive a trustworthy environment. For example:

- A test alters shared configuration or a singleton bean in a way that cannot be reset.
- A bean holds global state and has no API to return it to its initial state.
- A test modifies context structure or registers dynamic resources that lifecycle cannot restore.
- A test intentionally verifies behavior when a context is altered, closed, or must be created anew.

Example of a singleton bean with mutable configuration only serving a legacy scenario:

```java
@Component
class RuntimeFeatureRegistry {

    private final Map<String, Boolean> flags = new ConcurrentHashMap<>();

    void replaceAll(Map<String, Boolean> newFlags) {
        flags.clear();
        flags.putAll(newFlags);
    }

    boolean isEnabled(String name) {
        return flags.getOrDefault(name, false);
    }
}
```

If a test alters the shared registry and has no reliable way to restore state, a new context may be needed. However, if the bean has an explicit reset method or state can be saved and restored, reset the bean in the fixture so the context continues to be reused.

Do not use `@DirtiesContext` merely because:

- A test inserted or updated data in the database.
- A cache key holds a test-created value.
- A message was sent to a test queue.
- A mock has invocation history or stubbing needing reset.
- A test file was created in a temporary directory.

Those types of state have direct cleanup methods and typically do not require closing the context.

## 4. Using Transaction Rollback to Isolate Database Data

For integration tests running synchronously within the same transaction, `@Transactional` is one of the simplest ways to prevent data leakage between tests. Spring Test typically opens a transaction before the test method and rolls it back after the method completes.

```java
@SpringBootTest
@Transactional
class OrderRepositoryIntegrationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrder() {
        Order order = repository.save(new Order("customer-42"));

        assertTrue(repository.findById(order.getId()).isPresent());
    }
}
```

Database changes within the test transaction are rolled back by default. The context can stay in the cache for the next test; data in the transaction is reverted without reinitializing all beans.

`@Rollback` can be used to make the policy explicit:

```java
@Test
@Rollback(true)
void createsTemporaryOrder() {
    // Changes are rolled back after the test
}
```

If an intentional commit is needed, you can use `@Commit` or `@Rollback(false)`, though keep in mind committed data needs separate cleanup if tests share a database.

### Limitations of Test Transactions

Rollback only covers changes participating in the Spring-managed transaction. It does not automatically undo:

- HTTP requests sent to a payment service or external API.
- Sent emails, published messages, or messages received by a message broker.
- File writes, object storage writes, or Redis changes if those operations do not participate in the same transaction.
- Code running on another thread such as `@Async` tasks by default.
- Independent transactions opened with `REQUIRES_NEW` propagation that committed.
- Changes written by another process or test to a shared database.

Therefore, do not assume `@Transactional` guarantees all business state is cleaned. Identify whether each side effect lies inside or outside the transaction and choose cleanup accordingly.

## 5. Cleaning Up Data by Test-Specific IDs or Keys

When rollback cannot be used, create uniquely identified data so the test can delete the exact portion it owns. For example, each test uses a unique customer ID or correlation key:

```java
@SpringBootTest
class OrderApiIntegrationTest {

    @Autowired
    OrderRepository orderRepository;

    private final String customerId = "test-customer-order-api";

    @BeforeEach
    void prepare() {
        orderRepository.deleteByCustomerId(customerId);
    }

    @AfterEach
    void cleanUp() {
        orderRepository.deleteByCustomerId(customerId);
    }

    @Test
    void createsOrderForCustomer() {
        // Send request creating an order for the test's customerId
    }
}
```

Deleting before the test prevents the test from depending on data left behind from an earlier run. Deleting after the test keeps the environment clean for subsequent tests. Cleanup should be idempotent: calling it multiple times remains safe and does not fail when records are already gone.

In systems with foreign key relationships, delete in dependency order. For example, delete `order_items` before `orders` if the database does not cascade as configured. You can use a cleanup method on a repository or a test-support service to group deletions in the right order.

If tests run in parallel, a fixed ID like `test-customer-order-api` could be used by two concurrent runs. In that case, generate a unique namespace per test invocation, such as a UUID or test run ID, and pass that ID through all related records and requests.

## 6. Using `@Sql` to Prepare and Clean Up Data

`@Sql` allows running SQL scripts at test phases. This is a helpful option when prepared data spans multiple tables or needs a specific fixture.

```java
@SpringBootTest
@Sql(
    scripts = "/sql/orders/insert-test-orders.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/orders/delete-test-orders.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
class OrderSearchIntegrationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void findsOrdersForTestCustomer() {
        assertFalse(repository.findByCustomerId("test-customer-89").isEmpty());
    }
}
```

Preparation script:

```sql
INSERT INTO customers (id, name)
VALUES ('test-customer-89', 'Test Customer');

INSERT INTO orders (id, customer_id, status)
VALUES ('test-order-89', 'test-customer-89', 'PENDING');
```

Cleanup script:

```sql
DELETE FROM order_items WHERE order_id = 'test-order-89';
DELETE FROM orders WHERE id = 'test-order-89';
DELETE FROM customers WHERE id = 'test-customer-89';
```

The IDs in the example must be reserved exclusively for that test. If tests can run in parallel or multiple workers share the database, generate unique IDs per run or use separate databases/schemas.

### Transaction Mode of `@Sql`

`@SqlConfig` lets you adjust the transaction mode. In the default inferred mode, Spring attempts to use an active transaction if present, or creates an appropriate transaction when needed. `ISOLATED` requires the script to run in a separate transaction and commit independently.

Example configuration:

```java
@Sql(
    scripts = "/sql/cleanup-test-data.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED)
)
```

Only use an isolated transaction when necessary, because it can commit cleanup even if the test transaction rolls back. Understand your project's listener order and transaction manager clearly, especially when preparation and cleanup scripts execute in different transactions.

## 7. Using Repositories or Test-Support Services for Cleanup

If cleanup requires business rules or deleting multiple aggregates, you can create a test-support component. It can use real repositories in the integration context:

```java
@TestComponent
class OrderTestDataCleaner {

    private final OrderRepository orders;
    private final OrderItemRepository items;

    OrderTestDataCleaner(
            OrderRepository orders,
            OrderItemRepository items) {
        this.orders = orders;
        this.items = items;
    }

    @Transactional
    void deleteOrdersForCustomer(String customerId) {
        items.deleteByCustomerId(customerId);
        orders.deleteByCustomerId(customerId);
    }
}
```

Tests can call the cleaner in `@BeforeEach` and `@AfterEach`:

```java
@SpringBootTest
class OrderWorkflowIntegrationTest {

    @Autowired
    OrderTestDataCleaner cleaner;

    @BeforeEach
    void cleanBefore() {
        cleaner.deleteOrdersForCustomer("test-customer-135");
    }

    @AfterEach
    void cleanAfter() {
        cleaner.deleteOrdersForCustomer("test-customer-135");
    }
}
```

`@TestComponent` is a stereotype for test-support components in Spring Boot; if the project does not use Spring Boot, you can register this class in test configuration using `@Bean`. Place the cleaner in the test source set so it is never accidentally packaged into the production application.

If the cleanup method is called inside a rolled-back test transaction, understand transaction propagation. If cleanup must commit independently to delete pre-existing test data, a separate transaction or `ISOLATED` script may be needed. Do not simply add `@Transactional` without knowing which transaction will commit.

## 8. Clearing Application Caches Instead of Restarting the Context

Spring Cache and internal bean caches are application state. If a test leaves stale data in a cache, evict the exact keys or clear the test-dedicated cache region.

Example using `CacheManager`:

```java
@SpringBootTest
class ProductCacheIntegrationTest {

    @Autowired
    CacheManager cacheManager;

    @AfterEach
    void clearProductCache() {
        Cache cache = cacheManager.getCache("products");
        if (cache != null) {
            cache.clear();
        }
    }
}
```

If only one key needs removal:

```java
cache.evict(productId);
```

In distributed caches like Redis, consider using a dedicated prefix/namespace for tests. Avoid flushing the entire shared Redis if other tests or services are using it. For parallel tests, each test should use unique keys or isolated caches so cleanup does not delete another test's data.

If a cache is a mutable field inside a singleton bean with no reset API, you can add a semantically meaningful clear/refresh method or design a controllable cache abstraction. Only use `@DirtiesContext` when bean state cannot be safely restored that way.

## 9. Cleaning Up Message Brokers and Sent Events

Database transaction rollback does not delete messages published to Kafka, RabbitMQ, or another broker. If tests use a real broker or Testcontainers, design separate data regions:

- Use topics or queues dedicated to the test class or test run.
- Use separate consumer groups to avoid interference from other tests' offsets.
- Include the test run ID in message keys or payloads to locate and verify the test's messages.
- Delete queues/topics or purge messages according to broker capabilities in an isolated test environment.
- Wait for consumers to process using conditions with timeouts, not arbitrary `Thread.sleep()` calls.

Example of a namespaced topic name:

```java
String topic = "orders-test-" + testRunId;
```

Do not purge a shared topic while other tests are running. Message cleanup must be limited to resources owned by the test. If a test only needs to verify that a use case emits an event, a unit test can mock the outbound port; dedicated integration tests need the real broker.

## 10. Cleaning Up Files and Resources Outside the Context

Beans can create files or objects in storage. Closing `ApplicationContext` does not mean every created file is deleted.

For the filesystem, use JUnit's temporary directory:

```java
class ReportExportTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void exportsReportToTemporaryDirectory() throws IOException {
        Path output = temporaryDirectory.resolve("report.pdf");

        // Call exporter writing to output

        assertTrue(Files.exists(output));
    }
}
```

JUnit manages the temporary directory lifecycle and cleans it up after the test per configuration. For object storage, use a dedicated bucket or prefix for tests and delete exact objects after completion. For sandbox services, use cleanup APIs or separate fixtures if supported by the provider.

If cleanup lives in `@AfterEach`, make the operation re-runnable and handle the case where the resource was not created yet. For multi-step flows that might fail mid-way, record resource IDs immediately upon creation so cleanup can find them even if the test fails before the final assertion.

## 11. Using Dedicated Data per Test to Support Parallel Execution

Accurate cleanup starts with accurate data ownership. One test should not delete data another test is using. This is critical when JUnit runs in parallel, CI runs multiple workers, or multiple pipelines share a database.

A simple approach is generating a test run ID:

```java
class TestRunIds {
    static String newId() {
        return "test-" + UUID.randomUUID();
    }
}
```

In each test, use that ID for customers, orders, cache keys, or message correlations. Cleanup only deletes records whose ID belongs to the current test.

If the database supports separate schemas, you can create a schema per test run and configure the datasource to point to that schema. For some database engines, a separate database per suite or worker provides even stronger isolation. The exact choice depends on initialization overhead and how migrations are managed.

Avoid overly broad cleanup statements such as:

```sql
DELETE FROM orders;
TRUNCATE TABLE customers CASCADE;
```

These statements can delete another test's data or shared environment data. Only use full-table truncation in a database/schema completely isolated for tests and when no concurrent tests share that resource.

## 12. Using `@BeforeEach` and `@AfterEach` Responsibly

`@BeforeEach` and `@AfterEach` are suitable for setup/cleanup tied to individual test methods. Keep each hook small and clear:

```java
@BeforeEach
void prepareFixture() {
    cleaner.removeByTestRunId(testRunId);
    fixture = fixtureFactory.createFor(testRunId);
}

@AfterEach
void cleanFixture() {
    cleaner.removeByTestRunId(testRunId);
}
```

Cleanup should:

- Delete only data owned by the test.
- Be safe when data does not exist yet or was already deleted.
- Still run after assertion failures.
- Not depend on test execution order.
- Not delete data belonging to another worker or pipeline.
- Have reasonable timeouts if calling external services.

If setup creates multiple resources in different steps, register cleanup right after each successful creation step. This prevents resource leaks when a subsequent step fails. For simple resources, `try/finally` or resource management APIs may be more suitable.

## 13. How Are the Context Cache and `@DirtiesContext` Related?

Spring Test uses the context cache to reuse contexts with equivalent configurations. `@DirtiesContext` marks a context for eviction from the cache. The annotation's modes determine when the context is evicted, such as after a method or after a class.

Example that should only be used when a test genuinely alters the context:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutableSingletonConfigurationTest {

    @Autowired
    RuntimeFeatureRegistry registry;

    @Test
    void replacesGlobalFeatureConfiguration() {
        registry.replaceAll(Map.of("new-flow", true));
    }
}
```

If `RuntimeFeatureRegistry` can be restored in `@AfterEach`, prefer restoring it to keep the context. If not, `AFTER_CLASS` usually limits reload counts better than marking dirty after every method, provided tests in the class can safely share context state.

Remember that the annotation can be placed at the class or method level and has multiple modes. Choose the smallest scope that meets the need. Do not attach `@DirtiesContext` to a large base test class if only one subclass test mutates a singleton; doing so can force a host of other tests to reload contexts.

## 14. Distinguishing Application Caches From the TestContext Cache

Two types of caches are commonly confused:

| Cache | What it stores | How to clean it |
| --- | --- | --- |
| Spring TestContext cache | `ApplicationContext` instances created from test configurations | Let Spring reuse them; use `@DirtiesContext` when a context is no longer valid |
| Application cache | Business results, read data, sessions, or cached objects | Evict keys, clear namespace, TTL, or reset cache bean |

For example, `@Cacheable("products")` stores `findProduct()` results in the application cache. `@DirtiesContext` may destroy the cache manager bean if the cache manager lives in the context, yet if Redis is an external service, the Redis data remains. When the new context creates a cache manager and reconnects to Redis, old keys can still be read.

Therefore, call `Cache.evict()` or `Cache.clear()` on the right cache manager, or use a dedicated namespace for tests. Only when the cache manager configuration or a singleton bean is corrupted and unrecoverable does the context need refreshing.

## 15. When to Use Separate Databases/Schemas or Testcontainers

If many tests depend on complex data or run in parallel, separate databases are usually more reliable than sharing one database and manually deleting entire tables.

Common options:

| Organization approach | Advantage | Considerations |
| --- | --- | --- |
| Transaction rollback | Fast, minimal cleanup code | Does not cover side effects outside the transaction, other threads, or `REQUIRES_NEW` |
| Delete by test ID | Flexible, works with a shared database | Must manage unique keys and deletion order |
| SQL scripts | Explicit fixtures, suits multiple tables | Scripts are coupled to schema and require transaction mode management |
| Separate schema/database | Strong isolation, supports parallel execution | Costs creation, migration, and cleanup time |
| Dedicated Testcontainers per suite/worker | Production-like environment, reduces data sharing | Container resources require lifecycle management and concurrency limits |

Testcontainers does not automatically solve isolation if every test writes to the same database container and shares tables. You still need transactions, unique IDs, separate schemas, or separate databases depending on requirements.

## 16. Avoid Resetting the Context Just to Reset Mockito Mocks

In Spring tests, mock/spy beans can be reset using Spring Test's built-in mechanism or the corresponding annotation for your Spring Boot/Spring Framework version. If a mock retains invocation history or stubbing from an earlier test, use the appropriate reset policy.

Example with Spring Framework 6.2 and `@MockitoBean`:

```java
@SpringBootTest
class OrderNotificationIntegrationTest {

    @MockitoBean
    NotificationGateway notificationGateway;

    @Test
    void sendsNotificationAfterOrderIsCreated() {
        // ...
        verify(notificationGateway).send(any());
    }
}
```

The `@MockitoBean` annotation has lifecycle-based reset options in supported versions. With older Spring Boot versions, projects may use `@MockBean` and its corresponding reset mechanism. Choose an explicit reset policy and avoid using `@DirtiesContext` just to clear mock invocation history.

Resetting a mock does not undo side effects of a real adapter. If a test sent real HTTP requests or wrote to a real database, resetting mocks has no effect on external data.

## 17. Cleanup When a Test Fails Mid-Way

A test might create a customer successfully, create an order successfully, and then fail when calling payment. If cleanup relies only on variables assigned after the entire flow, resources created before the failure may be left behind.

Record IDs immediately after creating resources:

```java
class OrderWorkflowTest {

    private final Set<String> createdOrderIds = new HashSet<>();

    @AfterEach
    void cleanUp() {
        for (String orderId : createdOrderIds) {
            orderCleaner.deleteById(orderId);
        }
        createdOrderIds.clear();
    }

    @Test
    void createsOrderAndHandlesPaymentFailure() {
        String orderId = orderFixture.createOrder();
        createdOrderIds.add(orderId);

        // Continue to payment step which may throw an error
    }
}
```

This is an illustrative pattern; a fixture factory can return a resource-managing object providing `close()` for automatic cleanup. If using JUnit `@TestInstance(PER_CLASS)` or sharing a test instance, ensure the ID set is reset between methods and is not accessed concurrently in an unsafe manner.

For external resources, cleanup may fail due to network or temporary service outages. Log the resource ID and cleanup error so it can be investigated or handled by a dedicated test-data cleanup job. Never silently swallow cleanup failures if they can pollute a shared environment.

## 18. How to Verify That Contexts Are Still Being Reused

If you suspect tests are reinitializing contexts too often, inspect Spring Test logs or context cache statistics. Spring Test provides debug/trace logs for context loading and can log cache statistics when appropriate logging is enabled.

Example log configuration in `application-test.properties` or test logging configuration:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Cache info shows whether contexts are hitting or missing and whether they are being reloaded. Use this logging during diagnostics; there is no need to keep overly verbose trace levels in every pipeline if it bloats logs.

You can track context initialization time and test execution time separately. If every test method causes a context reload, search for `@DirtiesContext`, differing context configurations, or custom listeners dirtying the context. If the context remains cached yet data is left behind, fix cleanup in the corresponding database/cache/broker.

## 19. Example of Organizing a Test Suite Without Context Restarts

A suite can share a context and clean up data by test run ID:

```java
@SpringBootTest
class OrderWorkflowIntegrationTest {

    @Autowired
    OrderRepository orders;

    @Autowired
    OrderItemRepository items;

    private String testRunId;

    @BeforeEach
    void setUp() {
        testRunId = "order-test-" + UUID.randomUUID();
    }

    @AfterEach
    void tearDown() {
        items.deleteByTestRunId(testRunId);
        orders.deleteByTestRunId(testRunId);
    }

    @Test
    void createsOrderForCurrentTestRun() {
        Order order = new Order(testRunId, "customer-42");
        orders.save(order);

        assertTrue(orders.existsByTestRunId(testRunId));
    }
}
```

Each method has its own data; cleanup deletes the exact data of that method. The context can still be reused across methods and classes with equivalent configurations.

If repository cleanup is invoked through a transaction, ensure the transaction commits so data is actually deleted. If the test method has an outer transaction and cleanup joins the same transaction, cleanup may roll back along with the test; in that case adjust transaction management or run cleanup outside the test transaction.

## 20. Common Mistakes When Cleaning Up Test Data

- **Using `@DirtiesContext` to delete database records:** the context reloads while external data still remains.
- **Assuming closing the context clears Redis or brokers:** services outside the context keep their state.
- **Using rollback for all side effects:** emails, messages, HTTP, and other threads do not automatically roll back with the database.
- **Deleting entire tables in a shared database:** parallel tests can lose each other's data.
- **Running cleanup only after passing tests:** mid-way failures leave behind data or resources.
- **Non-idempotent cleanup:** a second cleanup run fails because data was already deleted.
- **Ignoring foreign key order:** cleanup fails because child tables still reference parent tables.
- **Sharing fixed IDs across tests:** tests running in parallel overwrite or delete each other's data.
- **Confusing TestContext cache with application cache:** context restarts while Redis keys still exist.
- **Using `@DirtiesContext` too broadly on a base class:** unrelated tests must load new contexts.
- **Failing to check cleanup transactions:** delete statements join the test transaction and get rolled back.

## 21. Workflow for Choosing the Right Cleanup Approach

When a test leaves state behind, identify the source of that state first:

1. **Database:** if operations stay within the test transaction, use rollback; if commits or multiple transactions are needed, delete by ID or use SQL cleanup.
2. **Cache:** evict keys or clear the test's dedicated namespace.
3. **Message broker:** use dedicated queues/topics/consumer groups and clean up the test's exact data region.
4. **Filesystem/object storage:** use temporary directories or dedicated prefixes and delete the exact resources.
5. **External services:** use sandboxes, unique IDs, and supported cleanup APIs.
6. **Singleton beans/context state:** reset beans or restore configuration; only use `@DirtiesContext` when safe recovery is not possible.
7. **Parallel execution:** assign a separate namespace to each test run, worker, or suite.
8. **Verify effectiveness:** inspect data after cleanup and check context cache logs when needed to confirm tests do not create new contexts just for business data.

A good cleanup strategy keeps tests independent, repeatable, and parallel-friendly. `ApplicationContext` should be retained when configuration and beans remain valid; business data should be cleaned in the exact place it is stored. By keeping these two lifecycles separate, Spring Test can leverage the context cache, the test suite runs faster, and errors from leftover data are resolved at their true source.
