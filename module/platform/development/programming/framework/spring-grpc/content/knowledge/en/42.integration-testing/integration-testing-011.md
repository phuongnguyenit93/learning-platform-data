# Avoiding Fixed Ports and Order-Dependent Tests

## Learning Objectives

After this lesson, you will be able to:

- Explain why fixed ports cause conflicts when running integration tests.
- Let the OS allocate a dynamic port for the gRPC server and retrieve it after binding succeeds.
- Create client channels after the Spring test context and gRPC server are ready.
- Distinguish dynamic ports from isolating data, state, and resources across tests.
- Write tests that are order-independent, do not rely on Thread.sleep, and avoid global state.
- Organize parallel test execution when servers, channels, and dependencies have clear lifecycles.
- Know when to use Spring context caching, @DirtiesContext, and JUnit resource locks.

## 1. Why Do Fixed Ports Make Tests Unstable?

A gRPC integration test requires the client to connect to the host and port where the server is listening. If all tests assume the server uses port 9090, tests can fail when another application uses that port, when another test has not stopped an old server, or when multiple application contexts start simultaneously.

Fixed ports also introduce environment dependencies: a developer machine may have the port free, while a CI agent or parallel job already occupies it. Failures often appear intermittently as bind failures, connection refused errors, or tests accidentally connecting to an older server.

With **SPRING_GRPC**, each integration test needs to connect to its application context's gRPC listener. The ports of the Spring Boot HTTP server, management endpoint, and gRPC server may differ. Using the web port by mistake fails to test gRPC transport.

## 2. Let the gRPC Server Bind a Dynamic Port Directly

gRPC Java accepts port 0 in ServerBuilder. The operating system selects an available port when the server binds:

~~~java
Server server = NettyServerBuilder.forPort(0)
    .addService(greeterService)
    .build()
    .start();

int actualPort = server.getPort();
~~~

Port 0 is merely an allocation request. Clients must use the getPort() value after startup succeeds. Never read 0 from configuration and use 0 to build a channel.

Do not open ServerSocket(0), read the port, and close the socket before the gRPC server binds. Another process can claim the port in the gap between those two operations. Let the gRPC server itself bind port 0 and publish the actual port after startup.

## 3. Lifecycle Diagram for Dynamic-Port Tests

~~~mermaid
flowchart TD
  A["Spring creates test context"] --> B["gRPC server binds port 0"]
  B --> C["Server starts successfully"]
  C --> D["Fixture publishes actual port"]
  D --> E["Test creates ManagedChannel"]
  E --> F["Test calls RPC and asserts"]
  F --> G["Test closes channel"]
  G --> H["Spring closes server when context ends"]
~~~

The key is ordering: the server must finish binding before the client channel is created. Tests should never guess when the server is ready with a fixed sleep interval.

## 4. Creating a Server Fixture with a Dynamic Port

When a test manages the server itself, you can create a Spring fixture with init/destroy methods:

~~~java
final class TestGrpcServer {
    private final List<BindableService> services;
    private volatile Server server;

    TestGrpcServer(List<BindableService> services) {
        this.services = List.copyOf(services);
    }

    synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }

        ServerBuilder<?> builder = NettyServerBuilder.forPort(0);
        services.forEach(builder::addService);

        try {
            server = builder.build().start();
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot start gRPC test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException(
                "gRPC test server is not running");
        }
        return current.getPort();
    }

    synchronized void stop() {
        Server current = server;
        server = null;
        if (current == null) {
            return;
        }

        current.shutdown();
        try {
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                current.shutdownNow();
                if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "gRPC test server did not terminate");
                }
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Register the fixture in test configuration:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class GrpcTestConfiguration {
    @Bean(initMethod = "start", destroyMethod = "stop")
    TestGrpcServer testGrpcServer(
            GreeterServiceImpl greeter,
            CatalogServiceImpl catalog) {
        return new TestGrpcServer(List.of(greeter, catalog));
    }
}
~~~

Spring starts the fixture after injecting service beans and calls stop when the context closes. The fixture binds a dynamic port, registers the services on the same server, and exposes the real port via port().

This approach applies when the test owns the server. If the Spring gRPC starter starts the server automatically, use the starter's dynamic port configuration and API/test support to read the actual port. Do not create a second server for the same services just to obtain a separate port.

## 5. Getting the Right gRPC Port in Spring Tests

The test creates the channel after the Spring context finishes refreshing:

~~~java
@SpringBootTest
@Import(GrpcTestConfiguration.class)
class GreeterIntegrationTest {
    @Autowired
    TestGrpcServer grpcServer;

    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void connect() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcServer.port())
            .usePlaintext()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void closeClient() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

The port accessor in the example belongs to the fixture. If the starter manages the server, replace it with the accessor provided by the starter; never assume @LocalServerPort is the gRPC port since that annotation typically represents the web server port.

The channel is created after the fixture starts. A finite deadline ensures the test terminates clearly if the server is not ready or a handler hangs. Test-created channels should be closed in teardown.

## 6. Dynamic Ports Do Not Mean a New Port per Test Method

Spring Test can cache ApplicationContext for reuse across multiple test classes with compatible configurations. When the gRPC server is a bean in that context, the server may continue running on the same dynamic port for the lifetime of the context.

This is normal:

- The port is allocated when the server fixture starts.
- Test methods sharing the context can reuse the same port.
- Each test method can still create its own channel and close it afterwards.
- When the context closes, Spring stops the server; a new context may receive a different port.

Do not write assertions expecting the port to change after every test method. The purpose of dynamic ports is to prevent collisions between active listeners, not to force constant server restarts.

If a test requires completely isolated server state, create a dedicated context/fixture or perform controlled state resets. Do not rely on port changes as a substitute for test isolation.

## 7. Why Do Tests Become Order-Dependent?

A test is order-dependent when it only passes if another test ran beforehand to create data, reset counters, or mutate shared state. Common culprits include:

- Database records left over from an earlier test.
- Spring singleton services holding mutable state or caches.
- Unreset static fields, global counters, or singleton test fixtures.
- HealthStatusManager still set to NOT_SERVING from an earlier test.
- One test closing a shared channel/server that subsequent tests still need.
- Tests relying on ID generation order, wall-clock time, or random data.
- Async tests finishing before callbacks or background workers complete.

Running a single test in isolation often misses these issues. A test may pass alone yet fail when running the full suite or when JUnit executes tests in parallel.

## 8. Every Test Must Prepare Its Own Required Data

Tests should create their own input data and never assume records were created by another test:

~~~java
@Test
void createsAndReadsItsOwnOrder() {
    String testId = UUID.randomUUID().toString();
    String orderId = "it-" + testId;

    CreateOrderReply created = orderStub.createOrder(
        CreateOrderRequest.newBuilder()
            .setOrderId(orderId)
            .setCustomerId("customer-" + testId)
            .build());

    assertEquals(orderId, created.getOrderId());

    OrderReply loaded = orderStub.getOrder(
        GetOrderRequest.newBuilder()
            .setOrderId(orderId)
            .build());

    assertEquals(orderId, loaded.getOrderId());
}
~~~

Unique IDs keep concurrent tests from overwriting each other's data. Created data should be deleted or namespaced per test run so it does not accumulate in shared databases.

Do not use fixed data like order-1 across all tests if the database is shared between test methods or CI jobs. If a fixed ID is part of the test contract, use an isolated database/schema or a controlled reset fixture.

## 9. Cleaning Up Data Without Relying on Test Transactions

In Spring integration tests, do not assume @Transactional on the test method will roll back changes made by a gRPC service. RPCs can run on server threads in different transactions than the transaction bound to the test thread. A test's transaction does not automatically span TCP calls.

Reliable ways to isolate data:

- Use a dedicated database/schema/container per test suite or test class.
- Create records with unique namespaces or test IDs.
- Call explicit cleanup APIs in @AfterEach or fixture teardown.
- Manage transactions at the service/repository layer along proper business boundaries.
- Reset caches/test state via test-only APIs.

When using Testcontainers or external services, manage container lifecycles and endpoints separately. Testcontainers can assign dynamic host ports; retrieve the mapped port from the container rather than hardcoding a host port.

## 10. Do Not Use Test Ordering to Mask Leaked State

JUnit allows specifying test order, but @TestMethodOrder should not be used to patch a test that depends on another test. If test B only passes after test A, either test B fails to set up its own data or test A fails to clean up its state.

Only use explicit ordering when order itself is the behavior under test, such as an intentional multi-step state machine scenario. For independent integration tests, each test must set up its own preconditions and clean up data it owns.

A helpful check is running test classes individually, running the full suite, reversing order, or enabling random ordering in the test environment. If results change with execution order, find the shared state instead of adding an ordering annotation.

## 11. Avoiding Shared Mutable State in Spring Singletons

Spring service beans are usually singletons. That works well for stateless or thread-safe dependencies, but easily creates test interdependencies if an implementation stores per-request state in fields:

~~~java
// Unsafe if this field represents per-RPC data.
@Service
final class GreeterServiceImpl extends GreeterGrpc.GreeterImplBase {
    private String lastRequestName;
}
~~~

Per-call data should live in local variables or call-scoped context objects. If a shared cache is required, define clear eviction/reset and concurrency semantics. Never let a test mutate singleton state without restoring it before finishing.

For tests that must modify health statuses, interceptor policies, or server-wide config, consider an isolated context. When a server is shared through context caching, one test must not temporarily alter server-wide state while other tests are running.

## 12. Running Tests Safely in Parallel

Dynamic ports eliminate one source of socket conflicts, but do not automatically make tests thread-safe in parallel. Verify separately that:

- Each test owns its own channel or uses a shared channel with a clear lifecycle.
- Shared servers are not shut down or reset by individual test methods.
- Test data uses isolated IDs or schemas.
- Mutable singleton state is synchronized or not shared.
- Files, queues, counters, and temporary directories do not share names.
- Health state or server-wide configuration is not mutated mid-call by another test.

Enable @Execution(CONCURRENT) only after test independence and resource ownership are clear. If a test genuinely requires exclusive access to a shared resource, use JUnit @ResourceLock or run that test sequentially. Resource locks are intentional synchronization, not a substitute for cleanup.

## 13. Waiting for Readiness with Signals, Not Sleep

After the server binds a port, a service might still not be ready because dependencies are still connecting or data has not finished loading. Never use Thread.sleep(1000) hoping the server is ready.

Instead:

- Wait for Spring context refresh and server lifecycle startup to complete.
- Use health Check/Watch if the application exposes the health service.
- Wait on a readiness condition or latch published by the fixture.
- Set RPC deadlines and finite timeouts on wait operations.
- If readiness fails, fail with details on port, server state, and relevant dependencies.

Readiness must reflect the ability to handle RPCs. An open socket alone does not mean the service is ready.

## 14. @DynamicPropertySource and Context-Allocated Ports

@DynamicPropertySource is suited for injecting endpoints created before ApplicationContext startup into Spring configuration, such as mapped ports from Testcontainers or an auxiliary service started outside the context.

If the gRPC server itself is created inside ApplicationContext, @DynamicPropertySource runs before the server bean is instantiated. Thus you cannot read the port from that bean inside this callback. For in-context servers, inject a port accessor and create the channel after context refresh, such as in @BeforeEach.

If the starter accepts port 0 configuration, configure it using the property for your exact starter/version and read the actual port via its test support API. The configured value 0 is not an endpoint clients can connect to.

## 15. When to Use @DirtiesContext?

@DirtiesContext tells Spring to evict the context from the cache and close its lifecycle beans. This is useful when a test mutates configuration or state that cannot be safely reset, or when verifying context/server shutdown directly.

Do not use @DirtiesContext solely to close a test-created channel; close the channel directly. Putting the annotation on every test method slows down the suite because Spring must repeatedly restart the context and server.

If the server fixture is a Spring-managed bean, let the destroy method/SmartLifecycle stop the server when the context closes. Do not call stop in @AfterEach if the context may be reused.

## 16. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using a fixed port for all tests | Bind collisions when running suites in parallel | Bind the server to port 0 and read the actual port. |
| Opening ServerSocket to probe a port then closing it | Race condition before gRPC server binds | Let the gRPC server bind port 0 directly. |
| Treating @LocalServerPort as the gRPC port | Client connects to the wrong web listener | Read the port from the gRPC server/starter accessor. |
| Expecting the port to change after every method | Broken assertions when Spring caches the context | Understand ports are tied to server/context lifecycle. |
| Sharing test IDs and data | Tests overwrite or read stale data | Namespace data per test or run. |
| Relying on @Transactional to roll back RPCs over TCP | Server changes may still commit | Clean up via service/database fixtures. |
| Using @TestMethodOrder to hide dependencies | Tests fail standalone or when reordered | Have each test set up its own preconditions. |
| Resetting server/shared singletons in @AfterEach | Breaks concurrently running tests | Isolate contexts or synchronize resources. |
| Enabling concurrent execution too early | Races in state, DB, and fixtures | Verify ownership and isolation first. |
| Using Thread.sleep to wait for readiness | Flaky and slow tests | Use health/readiness signals and timeouts. |
| Overusing @DirtiesContext | Suite constantly restarts contexts | Close test-owned resources directly. |

## 17. Independence Testing Matrix

A stable integration test suite should be verified along these dimensions:

1. **Port**: two server fixtures concurrently bind dynamic ports without collision.
2. **Context cache**: multiple tests sharing a context can call the server; each test closes its own channel.
3. **Data isolation**: tests create isolated records and never read data created by other tests.
4. **Order independence**: every test passes when run standalone and when suite order is reversed.
5. **Parallel execution**: concurrent tests do not mutate the same state or database records.
6. **Readiness**: clients call only after server/service readiness, with clear timeouts.
7. **Failure cleanup**: tests failing mid-setup still close channels and temporary data.
8. **Server lifecycle**: Spring/starter stops the server when the context closes, not after each method sharing a context.

Dynamic ports only solve listener conflicts. Data isolation, shared state, readiness, and lifecycles must all be verified separately before concluding tests are order-independent.

## 18. Hands-On Exercise

Reorganize integration tests for Greeting and Catalog services:

1. Remove all fixed ports; configure the server to bind port 0 or use the starter's dynamic port support.
2. Expose the actual port after server startup and create the channel in @BeforeEach.
3. Close the channel in @AfterEach; let Spring manage the server if the context is cached.
4. Generate unique customer/order IDs per test instead of fixed records.
5. Clean up test data in teardown or use isolated schemas/containers.
6. Remove dependencies on @TestMethodOrder and Thread.sleep.
7. Run each test standalone, run the full suite, and enable parallel execution for the isolated group.
8. Use @ResourceLock or dedicated contexts for tests that must mutate server-wide state.
9. Verify tests failing mid-setup still clean up channels and data.

**Completion criteria:** no hardcoded ports, every test prepares its own data, channels have independent lifecycles, the server follows the Spring lifecycle, and results remain identical regardless of test order or supported parallel execution modes.

## 19. Takeaways

- Bind the gRPC server to port 0 and read the actual port after startup.
- Never probe ports by opening and closing a ServerSocket prior to server binding.
- Dynamic ports prevent listener conflicts but do not automatically isolate data or state.
- Spring context caching can retain the server and port across multiple test methods; do not expect the port to change per method.
- Create channels scoped to the test and close test-owned channels.
- Every test creates its own preconditions, uses unique IDs, and cleans up data it created.
- Do not rely on @Transactional to roll back side effects of RPCs running on separate server threads.
- Avoid @TestMethodOrder, Thread.sleep, and mutable singleton state that make tests order-dependent.
- Run in parallel only once servers, channels, databases, and shared state have clear ownership and isolation.
- Use readiness signals and timeouts instead of guessing startup times.
- Let Spring/starter stop the server when the context closes; use @DirtiesContext only when evicting the context from cache is truly required.

Avoiding fixed ports and order-dependent tests keeps Spring gRPC integration tests reliable on both developer machines and CI, enables safe parallel execution, and produces consistent results regardless of test order.
