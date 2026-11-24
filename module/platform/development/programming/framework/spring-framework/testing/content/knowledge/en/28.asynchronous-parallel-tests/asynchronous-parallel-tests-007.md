# TestContext Conditions Suitable for Parallel Execution

**Context:** Spring Framework Testing → Asynchronous and Parallel.

Running multiple tests simultaneously can shorten build times, but it is only safe when each test can execute without altering another test's outcome. With the Spring TestContext Framework, this condition must be considered at two layers: how JUnit schedules tests and how Spring shares an ApplicationContext across tests.

Spring can reuse one **ApplicationContext** across multiple test classes that have equivalent configurations. This reuse reduces startup cost, but it also means multiple tests can concurrently share singleton beans, mocks, clients, connection pools, or external resources. The context cache is managed to support concurrent access; that does not automatically make every bean and fixture inside the context safe when multiple threads operate on them simultaneously.

A test suite suitable for parallel execution needs isolated data, fixtures free from contended mutations, a stable context lifecycle, and properly synchronized asynchronous tasks. Tests that mutate shared state or close the context must be restricted from running concurrently.

## 1. Two different mechanisms: JUnit scheduling and Spring context management

JUnit decides which test runs on which thread and when. The Spring TestContext Framework provides the ApplicationContext, dependency injection, test-managed transactions, and listeners for the test lifecycle.

The two mechanisms cooperate but hold distinct responsibilities:

~~~text
JUnit Jupiter
  |
  +--> selects test class / test method
  |
  +--> schedules SAME_THREAD or CONCURRENT
  |
  v
Spring TestContext Framework
  |
  +--> creates or retrieves ApplicationContext from context cache
  |
  +--> injects beans and manages test lifecycle
  |
  v
Test method
  |
  +--> uses singleton beans / mocks / datasource
  |
  +--> operates on database / file / server / shared resource
~~~

Enabling parallel execution in JUnit only allows tests to run concurrently. It does not automatically:

- Create a separate ApplicationContext for each test.
- Create a separate database or roll back all changes outside a transaction.
- Make mocks and singleton beans thread-safe under concurrent operations.
- Wait for all threads or reactive pipelines to finish.
- Prevent one test from closing a context that another test is using.
- Isolate shared system properties, files, ports, or servers.

Therefore, before enabling parallel execution for a package or module, identify which resources are shared and who is allowed to mutate them.

## 2. How does JUnit Jupiter enable parallel execution?

### 2.1. Parallel execution is a JUnit configuration

JUnit Jupiter runs tests sequentially by default if parallel execution is not enabled. It can be enabled with a **junit-platform.properties** file on the test classpath:

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent

junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
~~~

Meaning:

- **parallel.enabled:** enables JUnit Jupiter's parallel scheduling mechanism.
- **mode.default:** sets the default mode for test nodes such as methods.
- **mode.classes.default:** sets the default mode for test classes.
- **config.strategy:** selects how parallelism is determined.
- **fixed.parallelism:** sets the target parallelism level for the fixed strategy.

The **concurrent** value allows a node to run concurrently when no constraint or resource lock prevents it. Do not treat the number 4 as an absolute number of threads that always exist; this is the scheduler's parallelism setting, while actual execution also depends on the environment and scheduling constraints.

These properties can be placed in a dedicated test configuration file instead of enabling them for the entire project right away. Starting with a package that has independent data makes resource-sharing issues easier to detect.

### 2.2. Configuring via annotations

Modes can be specified on a class or method:

~~~java
@Execution(ExecutionMode.CONCURRENT)
class IndependentControllerTests {

    @Test
    void firstScenario() {
        // Independent scenario.
    }

    @Test
    void secondScenario() {
        // Another independent scenario.
    }
}
~~~

Or force a class to run sequentially:

~~~java
@Execution(ExecutionMode.SAME_THREAD)
class TestsUsingSharedMutableFixture {

    @Test
    void updatesSharedFixture() {
        // Operates on shared state.
    }

    @Test
    void readsSharedFixture() {
        // Depends on previously established state.
    }
}
~~~

**SAME_THREAD** means the related nodes execute on the same thread according to JUnit's schedule. It does not automatically synchronize with another test class running concurrently. If multiple classes access the same resource, all involved classes must share a locking convention or be isolated at a broader scope.

### 2.3. Choosing an appropriate strategy

JUnit supports strategies such as dynamic, fixed, and custom. With the fixed strategy, the parallelism count is explicitly set in configuration. With the dynamic strategy, JUnit calculates the parallelism level based on configuration and the number of processors detected by the runtime.

Choose a strategy based on:

- CPU and RAM resources of the CI runner.
- The number of ApplicationContexts that need to initialize concurrently.
- The load capacity of the test database.
- The number of containers or mock servers that can run simultaneously.
- Network wait times and limits of test services.

Many Spring tests initialize heavy contexts, databases, and embedded servers. Setting parallelism too high can slow down builds due to contention over CPU, memory, connection pools, or I/O.

## 3. TestContext cache and shared ApplicationContext

### 3.1. Why can multiple test classes use the same context?

The Spring TestContext Framework stores ApplicationContexts in a static cache per JVM process. When a test class needs a context whose configuration matches an already created context, Spring can retrieve that context instead of initializing it from scratch.

The cache key is formed from test configuration attributes such as:

- Context configuration classes and locations.
- Context initializers.
- Active profiles.
- Test property sources.
- Context customizers.
- Bean overrides or mock bean declarations.
- Parent context and other related attributes.

Two classes with the same effective configuration can share a single ApplicationContext. Therefore, having separate test class instances does not mean the beans injected into them are separate.

### 3.2. Context cache supports concurrent access, but beans still hold state

Spring manages the cache so multiple tests can look up and obtain contexts during parallel execution. However, singleton beans inside the context remain the exact same objects used by multiple tests.

Example:

~~~java
@Component
class RequestCounter {

    private int count;

    void increment() {
        count++;
    }

    int currentValue() {
        return count;
    }
}
~~~

If multiple tests call increment and currentValue on this singleton simultaneously, the result depends on thread interleaving. The fact that JUnit creates a separate test instance per method does not change that.

Stateless, immutable, or thread-safe beans are generally better suited for sharing. Beans containing mutable state, writable caches, counters, lists used as fixtures, or mocks with changing stubbing need special examination.

### 3.3. Do not use the context cache as a test isolation mechanism

The context cache optimizes startup cost, not data boundaries. Do not assume each test will receive a fresh context or that bean state will be reset after each method.

If one test modifies bean state, registers a listener, alters runtime configuration, or writes to shared memory, another test can observe that change. Reset state safely, create a separate context, or avoid running the related tests concurrently.

## 4. Conditions on test state and test instances

### 4.1. Default test instance lifecycle

JUnit Jupiter defaults to **PER_METHOD**: creating a new test class instance for each test method.

~~~java
class OrderServiceTests {

    private int invocationCount;

    @Test
    void firstTest() {
        invocationCount++;
    }

    @Test
    void secondTest() {
        invocationCount++;
    }
}
~~~

With PER_METHOD, the two methods have separate instances so instance fields are not shared between them. However, static fields, singleton beans, databases, files, and resources outside the test instance can still be shared.

### 4.2. PER_CLASS requires care when running concurrently

With **@TestInstance(PER_CLASS)**, JUnit uses a single instance for the entire test class:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.CONCURRENT)
class SharedTestInstance {

    private final List<String> observed = new ArrayList<>();

    @Test
    void firstTest() {
        observed.add("first");
    }

    @Test
    void secondTest() {
        observed.add("second");
    }
}
~~~

The example above has a race condition because ArrayList is not designed for concurrent writes. Aside from collections, other mutable fields and lifecycle callbacks can also be accessed concurrently.

When using PER_CLASS, ensure:

- Shared fields are immutable or thread-safe.
- Test methods do not depend on ordering.
- @BeforeAll and @AfterAll do not create or destroy fixtures while other methods are still using them.
- Setup/cleanup operations do not overwrite each other's state.

If a shared test instance is unnecessary, keeping the default PER_METHOD is usually simpler. Even so, PER_METHOD does not solve shared singleton beans or shared databases.

### 4.3. Do not rely on test ordering

Parallel execution means execution order is no longer a reliable synchronization mechanism. One test must not require another test to run beforehand to create data or establish state.

Do not use @Order as a way to guarantee sequentiality when nodes are marked concurrent. If two steps truly belong to a single scenario, place them in the same test method or build independent fixtures for each test.

## 5. Conditions on shared beans and mocks

### 5.1. Singleton beans must be safe for concurrent access

A bean can be injected into multiple test classes through the same context. If a bean holds mutable state, determine:

- Is the state protected by synchronization or concurrency primitives?
- Can one test reset state while another test is reading it?
- Are there shared caches or collections?
- Are there schedulers, executors, or background callbacks?
- Is runtime configuration modified during tests?

For real business beans, thread safety is an application property and must be designed properly. Do not add arbitrary synchronization just to make tests pass; first determine whether that concurrent behavior matches production expectations.

### 5.2. @MockitoBean and @MockitoSpyBean can be shared via context

When using **@MockitoBean** or **@MockitoSpyBean**, the mock/spy is registered in the ApplicationContext. If multiple tests share the context, they can operate on the same mock instance.

These two annotations were added in Spring Framework 6.2. For projects using older versions, the mock bean mechanism may come from Spring Boot Test; the same principle regarding mock state shared across a context still applies.

Example:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderControllerTests {

    @MockitoBean
    CatalogGateway catalogGateway;

    @Test
    void returnsAvailableOrder() {
        given(catalogGateway.findAvailability("SKU-1"))
                .willReturn(new ProductAvailability("SKU-1", true));

        // Send request and assert response.
    }
}
~~~

If one test is stubbing the mock while another test invokes or changes expectations on the same mock, results can depend on execution scheduling. Having a separate test instance per test method does not create a separate mock bean if the context is reused.

How to handle:

- Do not run tests concurrently if they share mocks with mutable stubbing or verification.
- Separate contexts when tests require different mock configurations.
- Use immutable fakes or per-test dependencies where appropriate.
- Organize tests into groups so mutable mocks are not shared across concurrent methods.

Do not assume calling reset(mock) in @BeforeEach is safe. One test could be using the mock while another test resets it.

### 5.3. Mockito mocks are not arbitrary shared fixtures

Mockito supports standard usage scenarios, but concurrently stubbing, resetting, verifying, and invoking the same mock can cause races or nondeterministic assertions. In particular, mock beans in the context cache live longer than a single test method.

If tests need different stubbing, isolating dependencies or contexts is an essential condition. Locking entire test classes can be a temporary measure, provided every test accessing that mock obeys the same resource lock.

## 6. @DirtiesContext and ApplicationContext lifecycle

### 6.1. What does @DirtiesContext do?

**@DirtiesContext** marks the ApplicationContext as altered and needing eviction from the context cache. Spring closes that context during eviction processing so a subsequent request can create a fresh context.

The annotation can be used at the method or class level with different modes, such as after method or after class.

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class TestsThatChangeApplicationContext {
    // Test alters context configuration state.
}
~~~

It is useful when a test genuinely corrupts or modifies the context in a way that cannot be safely restored via normal cleanup. Do not use @DirtiesContext as a default reset command after every test because context startup costs can be very large.

### 6.2. Why is @DirtiesContext dangerous in parallel tests?

Suppose two test classes share a context:

~~~text
Test A ------------------------>
          using ApplicationContext
Test B --------->
          marks @DirtiesContext
          Spring evicts and closes context
Test A ------------------------>
          may continue using a closed context
~~~

One test may be using a bean, connection pool, or embedded server while another test requests the context to be closed. This produces intermittent errors such as destroyed beans, closed connections, or servers no longer running.

Tests using @DirtiesContext are not good candidates for running concurrently with other tests sharing the same context. Run them sequentially or isolate the class so no other test executes concurrently within the same JUnit engine.

Example:

~~~java
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class TestsThatCloseSharedContext {
    // Tests needing to modify or close the context.
}
~~~

**@Isolated** is a JUnit Jupiter annotation requiring that class to run in isolation from other tests in the same test plan. It does not coordinate other JVMs or external processes accessing the same resources.

@Isolated has been available since JUnit Jupiter 5.11. If a project uses an older JUnit version, configure sequential execution in the build or split tests into a separate task; @Execution(SAME_THREAD) only restricts nodes within its applied scope and does not isolate the class from all other classes.

If possible, design tests to clean up state without closing the context. When @DirtiesContext is unavoidable, also check other classes sharing the same cache key.

### 6.3. Do not use @DirtiesContext to solve every race

If two tests write to the same database row, closing the context does not automatically resolve the data conflict. If two tests both modify a system property, creating a new context still does not isolate JVM-wide state.

Choose the measure matching the conflicting resource:

- Mutable bean state: controlled reset or separate context.
- Database data: transaction or separate schema/records.
- Global property: resource lock or avoid mutation.
- HTTP mock server: dedicated server/queue.
- Context lifecycle: serialize tests that close the context.

## 7. Conditions on databases and transactions

### 7.1. Test-managed transactions are usually thread-bound

Spring TestContext supports test-managed transactions via **@Transactional** and TransactionalTestExecutionListener. Transactions start and end with the test lifecycle, typically rolling back after the test unless configured otherwise.

~~~java
@Transactional
@SpringJUnitConfig(DataTestConfig.class)
class CustomerRepositoryTests {

    @Test
    void savesCustomer() {
        // Operations inside the test transaction.
    }
}
~~~

When two test methods run on two different threads, each test has its own transaction. That separates transactions, but it does not automatically create a separate database or schema per test.

If two tests write the same unique key, update the same record, or depend on data ordering, they can still collide.

### 7.2. Rollback does not replace data isolation

Transaction rollback works well for database operations inside the same test-managed transaction. However, the following scenarios can fall outside rollback scope:

- Another thread performs data writes.
- An @Async task or executor opens its own transaction.
- An HTTP call to an external service produces side effects.
- The test uses @Commit or @Rollback(false).
- Another transaction reads/writes the same data.
- Data created by scripts or fixtures outside the current transaction.

Do not assume everything happening in a test automatically rolls back simply because the method has @Transactional.

### 7.3. Creating separate data for each test

A safe parallel test should use non-colliding keys or data identifiers.

For example, instead of every test using the same email:

~~~java
String email = "parallel-test-" + UUID.randomUUID() + "@example.test";
~~~

For large databases, isolation can use:

- A dedicated database or schema per worker.
- A dedicated tenant or namespace.
- A unique ID per test.
- Cleanup by owner/test identifier.
- A dedicated database container per test group if cost permits.

Data must be created and deleted using a mechanism safe for concurrent execution. A cleanup like **DELETE FROM customer** can wipe out data another test just created; delete by the ID or namespace owned by the test.

### 7.4. @Sql and cleanup scripts

**@Sql** can execute scripts before or after tests. If multiple tests run against the same database and execute scripts that clear entire tables or insert fixed keys, they can contend.

Dangerous example:

~~~sql
DELETE FROM customer;
INSERT INTO customer(id, email) VALUES (1, 'test@example.test');
~~~

Two concurrently running tests can delete each other's data or violate unique constraints. Use scripts that only touch data belonging to that test, or move tests using global scripts into a sequential group.

### 7.5. Asynchronous tests do not automatically run inside the test's transaction

Spring's test-managed transaction is bound to the test execution thread. If a test launches work on another thread—such as via @Async, CompletableFuture, or an executor—that work does not automatically join the test thread's transaction.

~~~java
@Test
@Transactional
void startsAsyncWork() {
    service.startAsyncUpdate();

    // Do not assume the worker thread runs inside this transaction.
}
~~~

Tests must wait for the work to complete using an explicit synchronization mechanism and assert data after the worker commits. Do not end the test or roll back the transaction before the background task finishes if the task still relies on test data.

For reactive transactions, the transaction context follows propagation rules via Reactor Context; do not apply imperative ThreadLocal transaction assumptions to every reactive pipeline. Use reactive transaction APIs and test according to the application's actual execution model.

## 8. Conditions on HTTP servers, clients, and mock servers

### 8.1. MockRestServiceServer holds expectation state

MockRestServiceServer stores queued expectations and responses for the bound client. If multiple tests share one server instance, they can concurrently add expectations, send requests, or call verify/reset.

This easily causes errors when expectations are ordered or the server is shared through a singleton bean. For parallel tests, prefer creating a separate MockRestServiceServer and client per test or per isolated fixture.

Do not share a static MockRestServiceServer with a mutable queue across concurrent tests without synchronization and a clear request-distinguishing mechanism.

### 8.2. MockWebServer and WireMock need separate lifecycles

MockWebServer maintains a request/response queue and a listening port. If multiple tests share one instance, responses can be consumed prematurely by another test or RecordedRequests can be read by the wrong test.

Recommendations:

- Create a dedicated server per test or fixture with clear ownership.
- Use dynamic ports.
- Close the server during teardown.
- Do not share mutable response queues across concurrent tests.
- Wait for requests with finite timeouts.
- Do not share one static server across multiple tests without a request partitioning mechanism.

WireMock also holds mapping state and a request journal. Resetting mappings or the journal while another test uses the server can produce nondeterministic results.

### 8.3. Embedded servers and random ports

Tests using Spring Boot random port or test servers can share the same ApplicationContext and server instance when the context is cached. This is not automatically wrong: multiple tests can call the same server if endpoints are stateless and data is isolated.

However, pay attention to:

- Tests must not assume a fixed port.
- Do not stop the server while another test is using the context.
- Do not modify global server configuration while other requests are running.
- Data and request state must be separated between tests.
- Tests calling endpoints that reset the entire application must be serialized or use a dedicated instance.

### 8.4. Do not share fixed ports or temp files

Tests starting HTTP servers, brokers, or file services on fixed ports can collide when running concurrently. Use dynamically allocated ports and pass the actual address to clients.

Similarly, do not write from multiple tests to the same temporary file or fixed-name directory. Use test-specific directories, UUIDs, or JUnit's temporary directory mechanism.

## 9. Conditions on system properties and JVM-wide state

Some state does not belong to ApplicationContext yet is shared across all tests in the same JVM:

- System properties.
- Default Locale and TimeZone.
- System.out/System.err.
- Static singletons or caches.
- Default security provider.
- Shutdown hooks and JVM-wide registries.
- Shared temporary files and directories.

Example:

~~~java
@Test
void changesSystemProperty() {
    System.setProperty("feature.mode", "test");
}
~~~

If another test reads or writes the same property concurrently, results depend on timing. Save the previous value, restore it in finally/teardown, and use a resource lock to prevent tests within the same JUnit engine from accessing it concurrently.

JUnit Jupiter supports **@ResourceLock**:

~~~java
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE
)
class TestsChangingSystemProperties {

    @Test
    void changesPropertyForThisScenario() {
        // Modifies system property.
    }
}
~~~

Custom resource names can be used for shared resources:

~~~java
@ResourceLock(
        value = "shared-test-database",
        mode = ResourceAccessMode.READ_WRITE
)
class TestsUsingGlobalDatabaseReset {
    // Tests needing exclusive access to the shared database.
}
~~~

Every test that may access the same resource must share the lock name and compatible access mode. Resource locks only coordinate within the JUnit test plan of the same engine. They do not lock other processes, other JVM forks, external running applications, or users operating on the database.

If a resource can be created per test, isolating the resource is usually simpler and scales better than locking an entire group of tests.

## 10. Conditions on @DynamicPropertySource and context configuration

### 10.1. Dynamic property values must remain stable over the context lifecycle

**@DynamicPropertySource** is commonly used to register URLs, ports, or credentials from test resources such as Testcontainers.

~~~java
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

These values are used when Spring creates the ApplicationContext. If the context is cached, the datasource may continue holding the URL and connections to the container created during that initialization.

Do not change values returned by a dynamic property source while a context is being shared. If two test classes need different endpoints, use different context keys or create distinct test configurations.

### 10.2. Shared Testcontainers and shared data

A static container shared across a test class or test suite can reduce startup time. However, the database inside the container remains a shared resource.

Decide:

- Does each test use its own schema or share a schema?
- Does the data have unique keys?
- Does cleanup delete only the data created by that test?
- Could the container be stopped while another test is still using it?
- Do tests run across multiple JVM forks?

A static container in one JVM is not automatically shared with another JVM fork. Each fork might start its own container or connect to a shared external database; both cases must be configured explicitly.

### 10.3. Context customizers and cache keys

Configurations such as active profiles, property sources, bean overrides, or context customizers can alter the cache key. Two seemingly similar test classes with differing configurations can create two separate contexts; conversely, two classes with identical effective configurations can share a context.

Do not rely on class names to guess whether contexts are separate or shared. Inspect the effective test configuration and injected components. When a test needs completely isolated state, establish an explicit configuration boundary rather than merely renaming the test class.

## 11. Asynchronous tasks and synchronization in tests

### 11.1. Do not let a test finish while background work is still running

A test launching @Async tasks, executors, or reactive pipelines must wait for completion before finishing:

~~~java
@Test
void waitsForAsyncResult() {
    CompletableFuture<String> future = service.fetchAsync();

    String value = future.orTimeout(5, TimeUnit.SECONDS).join();

    assertThat(value).isEqualTo("completed");
}
~~~

This example uses a finite timeout to avoid hanging tests. In real applications, pick a waiting approach suited to the API and handle exceptions from the future so the test reports the true root cause.

If a test ends before background work finishes, teardown may close the context, delete data, or stop containers while the worker is still accessing them.

### 11.2. With Reactor, subscribe and verify signals

Do not merely construct a Mono or Flux and assume it has executed. Use StepVerifier or a bounded subscription mechanism:

~~~java
StepVerifier.create(service.fetchEvents())
        .expectNextMatches(event -> event.type().equals("CREATED"))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

When a test cancels a stream, verify that upstream resources and work are released as designed. For long-lived streams, cancellation is an important part of the test lifecycle.

### 11.3. Do not use Thread.sleep for synchronization

~~~java
@Test
void waitsForBackgroundWork() throws InterruptedException {
    service.startAsync();
    Thread.sleep(1000);
    // Check state.
}
~~~

This approach does not guarantee the worker finished after one second and slows down the test even when work finishes early. Use Future, CountDownLatch, Awaitility, or StepVerifier to wait for a concrete condition with a finite timeout.

When using latches or shared signals, each test needs its own instance. Do not reuse a static latch across concurrent tests.

## 12. Resource locks and how to isolate tests

### 12.1. When to use @ResourceLock?

Use a resource lock when multiple tests must access a clearly named resource that cannot easily be created separately:

- System properties.
- A shared configuration file.
- A global test database requiring resets.
- A singleton fixture with mutable state.
- A shared mock server with mutable queues or mappings.

Example:

~~~java
@ResourceLock(
        value = "catalog-wiremock",
        mode = ResourceAccessMode.READ_WRITE
)
class CatalogWireMockTests {
    // Configures or resets shared WireMock.
}
~~~

Other tests accessing that same WireMock must also declare the same resource name. If a class omits the lock declaration, JUnit cannot automatically know which resource that class uses.

### 12.2. READ and READ_WRITE

**READ** allows tests to read a resource concurrently when no writer holds the lock. **READ_WRITE** requires exclusive access to read/write or mutate the resource.

Use READ only when tests genuinely do not modify shared state. A GET request can still alter a server-side request journal, cache, counter, or audit log; examine actual state rather than relying solely on the HTTP method.

### 12.3. @Isolated for tests that must run alone

If a class performs operations with broad impact on global state or closes widely shared resources, **@Isolated** can ensure that class does not run concurrently with other tests in the same JUnit test plan.

~~~java
@Isolated
class GlobalEnvironmentTests {

    @Test
    void changesGlobalLocale() {
        // Changes JVM-wide locale and restores after test.
    }
}
~~~

@Isolated is a broad measure. Use it when resources are hard to model with resource locks or when the test modifies shared environment state on a large scale. It does not synchronize across multiple processes/JVMs or external services.

### 12.4. Prefer per-test fixtures over global locks

If each test has its own database schema, mock server, temp directory, and test data, tests can run concurrently without waiting on each other.

Locks are useful for resources that must be shared. However, overly broad locking can cause parallel execution to add scheduler overhead without speeding up runs. Fixture isolation generally scales much better.

## 13. Build-tool parallelism and lock limitations

### 13.1. JUnit threads and JVM forks are two distinct levels

A build can run tests in parallel in two ways:

- Multiple test threads within the same JVM managed by JUnit Jupiter.
- Multiple JVM forks launched by the build tool.

JUnit's context cache and resource locks exist only within the scope of their respective JVM/test engine. Two JVM forks do not share each other's context cache or locks.

If two forks share an external database, file, port, or WireMock server, JUnit `@ResourceLock` inside each fork cannot prevent conflicts between them.

### 13.2. Gradle

Gradle can run multiple test processes using maxParallelForks:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()

    maxParallelForks = 2
}
~~~

This setting controls the number of forked processes for the Test task. It is distinct from JUnit Jupiter's parallel execution properties. Both can be combined, but total concurrency must be accounted for when databases and containers have resource limits.

If you only want to try parallel execution inside a single JVM, start with JUnit configuration and keep maxParallelForks at 1. Only increase fork counts after verifying data, fixtures, and contexts, if needed.

### 13.3. Maven Surefire

Maven Surefire can also fork multiple JVMs or configure parallel execution per provider. JUnit Platform properties still govern parallel execution within each JVM when using JUnit Jupiter.

Check both Surefire/Failsafe and JUnit configurations. A resource lock is not a shared locking mechanism across multiple forks.

### 13.4. Calculating overall concurrency

If there are 2 JVM forks and each JVM allows 4 tests to run concurrently, the system may have to serve more simultaneous tests than looking at a single parallelism property suggests.

Account for:

- Number of forked processes.
- JUnit parallelism within each process.
- Contexts initialized concurrently.
- Connection pools and database connection limits.
- Number of containers, servers, and ports.
- CPU/RAM of the CI runner.

Increase concurrency incrementally and measure actual duration instead of assuming more threads always mean faster builds.

## 14. Cases that should run sequentially

A test or test group should run sequentially when it has any of the following characteristics:

- Uses @DirtiesContext and may share a context with other tests.
- Mutates shared singleton beans or mock beans.
- Calls reset on a shared mock server or WireMock server.
- Uses fixed database data and whole-table cleanup.
- Modifies system properties, locale, timezone, or JVM-wide state.
- Depends on ordering between test methods.
- Uses fixed ports, files, or directories.
- Stops containers, embedded servers, or executors used by other tests.
- Launches async tasks whose teardown does not wait for completion.
- Writes to the same file or external resource without isolation.

You can use @Execution(SAME_THREAD), @ResourceLock, or @Isolated depending on scope. If conflicts span JVM forks or external processes, isolate resources at the system level or reduce forks; JUnit annotations are not sufficient.

## 15. Matrix for assessing parallel readiness

| Condition | Suitable | Needs prior handling |
|---|---|---|
| Test is order-independent and uses dedicated data | Yes | — |
| Shared beans are stateless/immutable or thread-safe | Yes | — |
| Each test has its own mock server and client | Yes | — |
| Multiple tests write to the same table with fixed IDs | — | Create dedicated data or lock |
| Same context and same @MockitoBean stubbed differently | — | Separate contexts or serialize |
| Test closes context with @DirtiesContext | — | Isolate or run sequentially with related contexts |
| Modifies system properties | — | Resource lock or @Isolated |
| Uses a single WireMock instance with mapping resets | — | Dedicated server or shared lock |
| Async work completes and is awaited before teardown | Yes | — |
| Async work keeps running after test finishes | — | Add synchronization and cleanup |
| Test relies on method ordering | — | Rewrite as independent scenarios or sequential |
| Multiple JVMs operate on one out-of-process database | — | Isolate database/schema or inter-process lock |

A test should only be marked concurrent after the states and resources it uses have been identified. When unsure whether a bean or fixture is shared, treat it as shared until proven otherwise.

## 16. Example configuration of a safer test group

### 16.1. JUnit configuration

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
~~~

This configuration allows classes to run concurrently while keeping child nodes within a class on the same thread by default. Method-level concurrent mode can be enabled on specific classes once test methods are confirmed independent.

### 16.2. Class with dedicated data and without closing context

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@Execution(ExecutionMode.CONCURRENT)
class IndependentOrderTests {

    @Autowired
    OrderService orderService;

    @Test
    void handlesFirstOrder() {
        String id = "test-" + UUID.randomUUID();

        // Data belongs exclusively to this scenario.
        orderService.createOrder(id);
    }

    @Test
    void handlesSecondOrder() {
        String id = "test-" + UUID.randomUUID();

        // Does not reuse another test's ID or cleanup.
        orderService.createOrder(id);
    }
}
~~~

This example illustrates data independence. The OrderService bean is shared via the context, so it and its singleton dependencies must be designed thread-safely. If the service writes to a database, the schema must allow both tests to operate simultaneously and cleanup must target individual IDs.

### 16.3. Class requiring exclusive access to a global resource

~~~java
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE
)
@Execution(ExecutionMode.SAME_THREAD)
class SystemPropertyTests {

    private String previousValue;

    @BeforeEach
    void rememberProperty() {
        previousValue = System.getProperty("feature.mode");
    }

    @AfterEach
    void restoreProperty() {
        if (previousValue == null) {
            System.clearProperty("feature.mode");
        } else {
            System.setProperty("feature.mode", previousValue);
        }
    }

    @Test
    void changesFeatureMode() {
        System.setProperty("feature.mode", "test");
        assertThat(System.getProperty("feature.mode")).isEqualTo("test");
    }
}
~~~

The resource lock must be declared by every test accessing system properties in the same test plan. Saving and restoring the previous value avoids leaking state to subsequent tests.

### 16.4. Class that dirties the context

~~~java
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTests {

    @Test
    void changesContextManagedState() {
        // Scenario that genuinely needs to evict context from cache.
    }
}
~~~

This class runs separately from other tests in the same JUnit test plan, and the context is marked for eviction after the class. If another process uses the same database or external resource outside the JVM, a separate isolation mechanism is still required.

## 17. How to roll out parallel execution safely in phases

Do not enable concurrency for all tests in a large project at once and simply patch random failures as they appear. Roll it out step by step:

### Step 1: Classify resources

List what tests use:

- ApplicationContext and singleton beans.
- MockitoBean/MockitoSpyBean.
- Databases, transactions, schemas, and SQL scripts.
- MockRestServiceServer, MockWebServer, WireMock.
- Embedded servers, containers, and ports.
- System properties, static state, files, and temp directories.
- Executors, schedulers, and reactive streams.

Document clearly which resources are created per test and which are shared.

### Step 2: Run an independent group of tests in parallel

Start with unit tests or adapter tests that have isolated fixtures. Use low JUnit parallelism to uncover race conditions and resource contention.

Do not pick tests just because they already run fast; choose based on actual isolation level.

### Step 3: Isolate tests with shared state

Create dedicated database records, schemas, or mock servers. Eliminate global cleanups. If tests must reset singletons or contexts, place that group under a resource lock or run sequentially.

### Step 4: Verify async and context lifecycles

Ensure futures, executor tasks, and Flux streams complete or are cancelled before teardown. Do not let @DirtiesContext, container shutdown, or database cleanup occur while other tests are still using them.

### Step 5: Increase concurrency under control

Raise parallelism in steps and measure:

- Build duration.
- Number of flaky failures.
- Context startup times.
- RAM/CPU usage.
- Database connection usage.
- Number of concurrent containers and servers.

If speed does not improve or nondeterministic failures increase, lower concurrency and find the real bottleneck.

## 18. Signs that tests are not yet safe for parallel execution

Common symptoms:

- Tests pass individually but fail when running the whole suite.
- Unique constraint errors appear intermittently.
- One test receives another test's response from a mock server.
- Mockito verification reports unexpected invocations.
- Beans are closed or the context refreshes mid-request.
- Ports are already in use or servers fail to start.
- Tests observe data from another scenario.
- Async tasks write data after cleanup has already run.
- Failures disappear when adding Thread.sleep.
- Outcomes vary with test order or fork count.

These are usually signs of shared mutable state, unisolated data, or unsynchronized resource lifecycles. Do not fix them by adding sleeps or retrying tests; pinpoint the exact shared resource and establish clear ownership.

## 19. Practical principles

1. Distinguish JUnit's parallel scheduler from Spring TestContext's context cache.
2. Only enable CONCURRENT for tests that are order-independent and free of state contention.
3. Assume singleton beans in the context cache can be shared across multiple tests.
4. Prefer stateless, immutable beans and per-test fixtures.
5. Watch out for PER_CLASS because multiple methods can share the same test instance.
6. Avoid running tests concurrently when they alter or close the same ApplicationContext with @DirtiesContext.
7. Do not concurrently stub, reset, or verify the same shared @MockitoBean.
8. Partition database data per test and avoid global cleanups.
9. Remember that test-managed transactions do not automatically cover other threads or external services.
10. Use dedicated MockRestServiceServer, MockWebServer, and WireMock instances per test, or lock shared resources.
11. Use @ResourceLock for JVM-wide state within the same JUnit engine; use @Isolated for tests that must run alone.
12. Do not treat JUnit resource locks as cross-process or cross-JVM locks.
13. Wait for async tasks and cancel reactive streams before teardown.
14. Use dynamic ports and separate temporary directories.
15. Increase concurrency in phases and monitor both stability and performance.

The Spring TestContext Framework can reuse an ApplicationContext while JUnit runs multiple tests concurrently. The decisive condition is that tests must be independent in data, bean state, mocks, and resource lifecycles. When a context or fixture holds mutable state, isolate or synchronize it explicitly. Only once those conditions are guaranteed will parallel execution cut test time while keeping results stable.

