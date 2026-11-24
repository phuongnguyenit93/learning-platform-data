# Test transactions do not automatically wrap HTTP requests on server threads

A Spring test can be annotated with `@Transactional` and rolled back after running. This is very convenient when testing repositories, services, or controllers using `MockMvc`. However, if a test sends an HTTP request through a live running server, the transaction opened by Spring Test for the test method normally **does not cover the transaction handled on the server thread**.

The difference lies in the execution boundary. Spring's test transaction is bound to the thread executing the test. When using `@SpringBootTest(webEnvironment = RANDOM_PORT)` and sending a request over HTTP to an embedded server, the server handles the request on a different thread. Services on the server side can open and commit their own transactions. When the test method finishes, Spring rolls back the test thread's transaction; operations committed on the server thread remain in the database.

Therefore, clearly distinguish testing requests in the same process/thread from testing over real HTTP. Choose transaction and cleanup strategies according to how the request is executed, rather than assuming every change triggered by a test rolls back with the test method's transaction.

## 1. What is a test-managed transaction?

The Spring TestContext Framework can manage a transaction for a test method when the test is annotated with `@Transactional` and an appropriate `PlatformTransactionManager` exists. `TransactionalTestExecutionListener` starts the transaction before the test method runs and ends it according to the rollback/commit policy.

Example:

```java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrder() {
        Order order = repository.save(new Order("customer-42"));

        assertTrue(repository.findById(order.getId()).isPresent());
    }
}
```

By default, a test-managed transaction is rolled back after the method. Because repository operations join that transaction, test-created data is not committed to the database.

`@Rollback` can make the behavior explicit:

```java
@Test
@Rollback(true)
void createsTemporaryOrder() {
    // The test's transaction is rolled back after the method.
}
```

Or you can request a commit with `@Commit` or `@Rollback(false)`. These annotations control the test-managed transaction. They do not turn an HTTP request's transaction on another thread into a child transaction of the test.

## 2. Test transactions are bound to the executing thread

With Spring's common imperative transaction managers, transaction resources and transaction state are bound to the current thread. When a service method with `@Transactional(propagation = REQUIRED)` is called on the same thread, it usually joins the active transaction.

If a call happens on another thread, that thread does not automatically inherit the test thread's transaction. It will use its own transaction if appropriate transaction configuration exists, or execute according to the semantics of the repository/connection it uses.

```text
Test thread
    |
    +-- Spring Test opens transaction T1
    |
    +-- calls a synchronous method on the same thread
    |       |
    |       +-- REQUIRED service can join T1
    |
    +-- test finishes -> rolls back T1

Server thread
    |
    +-- receives HTTP request
    |
    +-- service opens transaction T2
    |
    +-- writes data and commits T2
    |
    +-- response returns to client

Rolling back T1 does not roll back T2.
```

This is the core reason `@Transactional` on a test method does not automatically clean up data created by a real HTTP request.

## 3. `MockMvc` and HTTP requests to a real server differ

Two ways of testing endpoints may look similar at the API level yet differ in how requests execute.

| Testing approach | How the request is processed | Can test-managed transaction cover it? |
| --- | --- | --- |
| Calling service/repository directly in test | On test thread | Yes, if the call joins the current transaction |
| `MockMvc` with synchronous Spring MVC | Servlet pipeline executes inside the test call, usually on test thread | Usually yes, if services use propagation that joins the current transaction |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` and `TestRestTemplate` | Request goes over socket to embedded server; server handles on separate thread | No; server uses its own transaction |
| `@SpringBootTest(webEnvironment = DEFINED_PORT)` and HTTP client | Request goes to running server on separate thread | No; server uses its own transaction |
| Async request or work offloaded to executor | Portion of work runs on another thread/task | Does not automatically join the test thread's transaction |

### `MockMvc`: synchronous request on the same thread

With Spring MVC Test, `MockMvc.perform(...)` invokes the MVC pipeline in the test process without opening a socket to a real server. In typical synchronous cases, the request is processed on the thread calling `perform()`. If a test-managed transaction is active on that thread, database operations of services with `REQUIRED` propagation can join the same transaction.

Example:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class OrderMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository orders;

    @Test
    void createsOrderThroughMvcPipeline() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":"customer-42", "items":[{"sku":"BOOK-1","quantity":1}]}
                    """))
            .andExpect(status().isCreated());

        assertTrue(orders.existsByCustomerId("customer-42"));
    }
}
```

In synchronous scenarios, the test transaction normally covers persistence operations and rolls back after the test. The test still runs through Spring MVC mappings, filters, and controllers, though it does not test TCP, port binding, or the full behavior of a server receiving live requests.

Do not treat this as a guarantee for every `MockMvc` request. If the controller starts async processing, invokes `@Async`, spawns threads itself, or uses independent transaction propagation, that work may not join the test transaction. When using async `MockMvc`, verify the transaction and completion timing of background processing.

## 4. `RANDOM_PORT`: test transactions and server transactions are separate

`@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` launches a web server on a random port. The test uses an HTTP client such as `TestRestTemplate`, `RestClient`, `WebClient`, or a configured `WebTestClient` to call the server over the network.

Example:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository orders;

    @Test
    void createsOrderThroughRealHttpServer() {
        ResponseEntity<OrderResponse> response = http.postForEntity(
            "/orders",
            new CreateOrderRequest("customer-42"),
            OrderResponse.class
        );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertTrue(orders.existsById(response.getBody().id()));
    }
}
```

In this example, the `@Transactional` annotation opens a transaction for the test method. However, the request is handled on a thread of the embedded server. If `OrderService` opens a transaction and commits while processing the request, data is committed in the server-side transaction. Rolling back at the end of the test only reverts the test thread's transaction, not the server-side transaction.

Therefore, the example above can leave an order in the database after the test finishes, even though the class has `@Transactional`. This is a key difference between synchronous `MockMvc` and HTTP requests to a real server.

## 5. `@Rollback` and `@Commit` do not control server-side transactions

The following annotations control the transaction managed by Spring Test:

```java
@Transactional
@Rollback
@Test
void testRequest() {
    // ...
}
```

Or:

```java
@Transactional
@Commit
@Test
void testRequest() {
    // ...
}
```

For tests calling a server over real HTTP:

- `@Rollback` rolls back the test thread's transaction if one exists.
- `@Commit` commits the test thread's transaction if one exists.
- `@Rollback(false)` likewise requests the test transaction to commit.
- Neither annotation automatically binds the test's transaction to a request running on a server thread.

If the server request already committed, `@Rollback` on the test cannot revert that data. If the server transaction failed and rolled back, `@Commit` on the test likewise cannot make the server transaction commit again.

Do not add `@Transactional` to a real HTTP test solely to "automatically roll back all data." It creates a false sense of safety and can even hold an unnecessary connection while the server needs another connection.

## 6. Why can the server commit before the HTTP response returns?

In a synchronous Spring MVC request, a service can run inside a transaction:

```java
@Service
class OrderService {

    @Transactional
    public OrderId create(CreateOrderCommand command) {
        Order order = Order.create(command);
        repository.save(order);
        return order.getId();
    }
}
```

When the transactional method completes normally, the transaction interceptor can commit before request processing finishes sending the response. Thus, by the time the HTTP client receives a successful response, server-side data has usually already been committed.

This depends on the actual transaction boundary. If the controller returns an asynchronous result, offloads work to an executor, or merely enqueues a message for later processing, the response may return before business work finishes. In that case, the test must wait for completion with a bounded timeout instead of assuming the response means all side effects are done.

## 7. Cleaning up committed data using a test-specific key

For HTTP tests running against a real server, a common pattern is creating data with a unique identifier and deleting that exact data after the test.

Example using a test run ID:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderTestDataCleaner cleaner;

    private String testRunId;

    @BeforeEach
    void setUp() {
        testRunId = "http-test-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanUp() {
        cleaner.deleteByTestRunId(testRunId);
    }

    @Test
    void createsOrderThroughHttp() {
        CreateOrderRequest request = new CreateOrderRequest(
            "customer-42",
            testRunId
        );

        ResponseEntity<OrderResponse> response = http.postForEntity(
            "/orders", request, OrderResponse.class
        );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
    }
}
```

The cleanup service is a separate Spring bean:

```java
@Service
class OrderTestDataCleaner {

    private final OrderItemRepository items;
    private final OrderRepository orders;

    OrderTestDataCleaner(
            OrderItemRepository items,
            OrderRepository orders) {
        this.items = items;
        this.orders = orders;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void deleteByTestRunId(String testRunId) {
        items.deleteByTestRunId(testRunId);
        orders.deleteByTestRunId(testRunId);
    }
}
```

`REQUIRES_NEW` ensures the cleaner runs in its own transaction when another transaction is active on the calling thread. If the test class has no test-managed transaction, a normal `REQUIRED` transaction may suffice; `REQUIRES_NEW` is useful when wanting cleanup to commit independently of any outer transaction.

The cleaner must be invoked through a Spring bean proxy for propagation to apply. Placing an `@Transactional` method on the test class itself or using self-invocation within the same bean does not create an equivalent proxy boundary. In the example, the test injects `OrderTestDataCleaner` and invokes a public method on the Spring-managed bean.

## 8. Why use a unique ID instead of deleting the entire table?

HTTP tests can run in parallel with other tests or another CI worker. If cleanup executes a command that deletes the entire table, it can wipe out data belonging to another running test.

Avoid broad cleanup such as:

```sql
DELETE FROM orders;
TRUNCATE TABLE orders CASCADE;
```

on a database shared across tests.

Instead:

- Generate a unique UUID or test run ID per test method.
- Include that ID in the request or metadata of created data.
- Store references from child records so they can be cleaned up by the same ID.
- Delete only the records created by the current test.
- Make cleanup operations idempotent so calling them multiple times remains safe.

If you cannot put a test run ID into the domain model, you can use a metadata field, correlation ID, dedicated test tenant, or separate schema. The key is that the test has a way to accurately identify the data belonging to it.

## 9. Cleanup with `@Sql` and transaction mode

`@Sql` can run scripts after a test method to delete data. For real HTTP tests, note that the cleanup script must actually commit; if it joins a test-managed transaction that rolls back, the deletions may not be persisted.

Example:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Sql(
    scripts = "/sql/cleanup-http-test-data.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED)
)
class OrderHttpIntegrationTest {
    // ...
}
```

`ISOLATED` requires the script to run in its own transaction and commit independently. Use this setting when the script needs to delete data committed by the server and must not roll back with another transaction.

The script still needs to delete by the test's unique ID. If the script uses a fixed ID while multiple tests run in parallel, it can accidentally delete another test's data. For dynamic IDs, use an appropriate script/parameter generation mechanism or a cleanup bean to pass parameters safely.

## 10. Using a separate database or schema for HTTP tests

When tests involve many tables, multiple request flows, and parallel execution, a separate database/schema can provide better isolation than row-by-row cleanup.

Options include:

| Organization | Benefit | Cost/consideration |
| --- | --- | --- |
| Transaction rollback | Fast for operations in the same transaction | Does not cover server threads or out-of-transaction side effects |
| Cleanup by test run ID | Works with a shared database | Requires managing IDs and deletion order |
| `@Sql` cleanup | Clear, reusable scripts | Requires managing transaction mode and test IDs |
| Separate schema | Separates data across suites/workers | Requires creating schemas and running migrations |
| Separate database/container | High isolation, close to production | Resource- and time-intensive startup |

Testcontainers helps spin up databases for testing, yet if multiple tests write to the same container and schema, data is still shared. A container does not automatically give each test its own transaction or roll back server-side requests.

## 11. Do not use `@DirtiesContext` to roll back HTTP requests

`@DirtiesContext` marks an `ApplicationContext` for removal from the context cache. It does not delete committed database records, remove messages from a broker, undo HTTP requests, or restore external service state.

For example, a create-order request committed to PostgreSQL. After the test, Spring closes the context because of `@DirtiesContext`; the database still holds the order. The new context creates a new datasource yet reads the same database, so the old order remains.

Only use `@DirtiesContext` when a test mutates the context itself or a singleton bean in an unrecoverable way. Business data must be cleaned up via transactions, repositories, SQL scripts, or isolated test resources.

## 12. Async requests and background work

A request may return `202 Accepted` or another response before the business task completes. Example:

```java
@PostMapping("/reports")
ResponseEntity<Void> createReport(@RequestBody ReportRequest request) {
    reportService.schedule(request);
    return ResponseEntity.accepted().build();
}
```

If `schedule()` dispatches work to `@Async`, an executor, or a message broker, transactions and cleanup timing become even further separated from the test thread. The test should not call cleanup immediately upon receiving `202` if a worker may still write data afterward.

Wait for the business completion condition with a timeout:

```java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertTrue(reportRepository.existsByTestRunId(testRunId))
    );
```

Only after confirming the work completed should the test clean up data. Use Awaitility or an equivalent synchronization mechanism; avoid fixed `Thread.sleep()` since processing time depends on machine load and infrastructure state.

If cleanup must run even when the test times out or an assertion fails, capture the test run ID as soon as the request is sent and put cleanup in `@AfterEach`. For tasks that might outlive the test, add cancellation or verify the worker has stopped before deleting fixtures.

## 13. `REQUIRES_NEW` and independent transactions

Even when using `MockMvc` on the same test thread, transaction rollback does not cover every operation. A service may declare:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAuditEvent(AuditEvent event) {
    auditRepository.save(event);
}
```

`REQUIRES_NEW` suspends the current transaction, opens a new transaction, and can commit independently. When the test's outer transaction rolls back, the audit record committed in the independent transaction still remains.

Other cases that can escape the test transaction:

- `@Transactional(propagation = NOT_SUPPORTED)` runs the method without a current transaction.
- Code running in `@Async` or a separate executor.
- Transactions started through a different datasource or transaction manager.
- Side effects sent to external systems.
- A service opening its own connection or transaction that does not participate in the test's transaction manager.

When a test leaves data behind despite using `@Transactional`, inspect propagation, threads, datasources, and transaction managers before concluding Spring Test failed to roll back properly.

## 14. Risk of connection pool exhaustion when tests hold transactions

A real HTTP test might open a transaction on the test thread and then send a request to the server. If the test transaction holds a connection from the pool while the server thread needs another connection, a small pool can be exhausted.

A scenario that can occur:

1. The test thread starts a transaction and holds a connection.
2. The test sends an HTTP request to the server.
3. The server thread handles the request and needs a connection to write to the database.
4. No connections remain available in the pool; the server must wait.
5. The test thread waits for the HTTP response; the server thread waits for a connection.

With a pool size of just one connection, this scenario can cause timeouts or application-level deadlocks. Increasing pool size can mask symptoms without fixing the misguided rollback attempt. If a test calls a real server, usually avoid opening an unnecessary test-managed transaction on the client thread.

## 15. How to verify data after an HTTP request

After the server returns a response, the test can read data using a repository. However, if the test method holds its own transaction, visibility of the server's commit also depends on the database's isolation level and snapshots.

With `READ COMMITTED` isolation, a new query can typically see server transactions committed earlier. With isolation like `REPEATABLE READ`, the test transaction may keep seeing an older snapshot. Additionally, the persistence context may hold stale entities in the first-level cache.

To verify committed state:

- Avoid opening a test transaction unless needed.
- Read through a new transaction after the request completes.
- If needed, use `EntityManager.clear()` to avoid reading entities still managed in the persistence context.
- Use a repository/transaction template with clear boundaries.
- Wait for background tasks to complete if the endpoint returns a response before writing data.

Do not use an assertion on an object sitting in the persistence context as the sole proof that the server request committed data to the database.

## 16. A testing strategy for each type of goal

| Goal | Appropriate testing approach | Data strategy |
| --- | --- | --- |
| Service rules | Call service directly with mock/fake dependencies | Test transaction rollback if real database is needed |
| MVC mapping, validation, exception handlers | `MockMvc` with test transaction for synchronous processing | Rollback usually fits if all writes join the test transaction |
| HTTP communication over sockets, port binding, real server | `RANDOM_PORT` or `DEFINED_PORT` with HTTP client | Do not rely on test thread rollback; clean up committed data |
| Async endpoints or background jobs | HTTP test plus awaiting completion condition | Clean up after worker completes, using unique IDs |
| Real transaction propagation/commit | Integration test with clear transaction boundaries | Re-read from a new transaction and clean up independently |
| Contracts with external services | Mock server or sandbox | Use isolated resources/IDs and cleanup APIs if available |

You do not need a real HTTP server for every controller test. If the goal is only mappings and responses, `MockMvc` is usually faster. Reserve `RANDOM_PORT` for things that can only be verified with a real server and HTTP client.

## 17. Complete example: HTTP test without a test-managed transaction

A clean structure is letting the server manage production transactions while the test manages data through a dedicated cleaner:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository orders;

    @Autowired
    OrderTestDataCleaner cleaner;

    private String testRunId;

    @BeforeEach
    void setUp() {
        testRunId = "http-" + UUID.randomUUID();
    }

    @AfterEach
    void tearDown() {
        cleaner.deleteByTestRunId(testRunId);
    }

    @Test
    void persistsOrderCreatedByHttpRequest() {
        ResponseEntity<OrderResponse> response = http.postForEntity(
            "/orders",
            new CreateOrderRequest("customer-42", testRunId),
            OrderResponse.class
        );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());

        assertTrue(orders.existsByTestRunId(testRunId));
    }
}
```

Here there is no `@Transactional` on the test class. The server processes the request and commits according to the application's transaction boundary. When the synchronous response returns, the test verifies the data and then `@AfterEach` calls the cleaner to delete the exact records belonging to the test run.

If the request is asynchronous, replace the immediate assertion with a bounded wait condition. The cleaner must run after the work has completed or been safely cancelled.

## 18. Example using `MockMvc` when rollback is desired

If the goal is testing the MVC pipeline and wanting data to roll back automatically, you can use `MockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class OrderMvcTransactionTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository orders;

    @Test
    void createsOrderWithinTestTransaction() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":"customer-42", "testRunId":"mvc-test-1"}
                    """))
            .andExpect(status().isCreated());

        assertTrue(orders.existsByTestRunId("mvc-test-1"));
    }
}
```

With synchronous requests, a service transaction with `REQUIRED` propagation can join the test transaction. Spring rolls back when the test finishes. If the controller uses async processing, the service uses `REQUIRES_NEW`, or code switches to another thread, dedicated cleanup is required just like a real HTTP test.

## 19. Common mistakes

- **Putting `@Transactional` on a `RANDOM_PORT` test and expecting database rollback:** requests are processed on a server thread with an independent server transaction.
- **Confusing `MockMvc` with real HTTP:** `MockMvc` does not open a socket to an embedded server; thread/transaction semantics usually differ.
- **Assuming `@Rollback` rolls back every transaction:** the annotation only controls the test-managed transaction.
- **Assuming `@Commit` makes the server transaction commit:** server transactions already have their own lifecycle.
- **Using `@DirtiesContext` to delete request data:** context restarts do not delete committed data in databases or external services.
- **Whole-table cleanup:** parallel tests can delete each other's data.
- **Cleanup inside a transaction that will roll back:** delete statements may not commit if they join the test transaction.
- **Overlooking `REQUIRES_NEW`:** independent transactions can commit even when the outer transaction rolls back.
- **Overlooking async:** a `202` response does not mean the worker finished; cleaning up too early can let the worker write data afterward.
- **Holding a test transaction while waiting on the server:** can hold a connection and exhaust the pool.
- **Reading from a stale persistence context:** tests may miss newly committed server data due to caching or snapshot isolation.

## 20. Workflow for choosing transactions and cleanup

When writing a test that sends HTTP requests, determine in order:

1. **Where is the request executed?** Synchronous `MockMvc` on the test thread, or a real server via `RANDOM_PORT`/`DEFINED_PORT`?
2. **Is there thread switching or async?** Check `@Async`, executors, async MVC/WebFlux, and message consumers.
3. **Which transactions are active?** Inspect `@Transactional`, propagation, transaction managers, and datasources.
4. **Does the test need rollback or commit verification?** Do not add `@Transactional` unless it serves a clear purpose.
5. **How is server-side data identified?** Use UUIDs, test run IDs, tenants, or separate schemas.
6. **Which transaction does cleanup run in?** Use a cleaner bean with an appropriate transaction or an `ISOLATED` SQL script when an independent commit is needed.
7. **Do tests run in parallel?** Avoid fixed IDs and broad delete commands.
8. **Has the request finished completely?** For async, wait for a completion condition with a timeout before cleaning up.
9. **Can data be verified from a new transaction?** Avoid relying on stale snapshots or persistence contexts.

Test transactions are an effective isolation tool when operations execute within the same transaction boundary. For HTTP requests to a real server, transactions are opened on server threads and can commit independently; rolling back on the test thread cannot undo them. Use `MockMvc` when testing synchronous MVC alongside a test transaction, and use unique IDs, committing cleanup, or dedicated databases/schemas for tests requiring a real HTTP server. Understanding this boundary ensures tests both reflect production behavior and prevent business data from leaking between runs.
