# Do not use real networking for every unit test

## 1. Unit tests should verify logic, not spin up an entire network stack

In **SPRING_GRPC**, applications use Protocol Buffers as contracts, generated stubs to invoke RPCs, and service implementations inside the Spring ecosystem. At runtime, a real gRPC call travels through channels, HTTP/2, TCP, and possibly TLS, proxies, DNS, and many infrastructure components.

Not every test needs those components. Unit tests should run fast, in isolation, and repeatably; they focus on verifying a single unit of logic with controlled inputs and outputs. If every unit test opens sockets, boots a real server, connects to a database, or depends on a broker, the test suite becomes slow, environment-fragile, and hard to diagnose when failing.

That does not mean skipping transport testing. Choose the right level:

| Level | Scope | Appropriate execution approach |
|---|---|---|
| Domain/use-case unit test | Business rules, validation, mapping | Call classes directly; use fakes/mocks for dependencies |
| gRPC service test | Generated stubs, method descriptors, service adapters, status/observer | In-process gRPC transport |
| Component test | Spring wiring, interceptors, configuration, serialization | Spring test context and fake/local dependencies |
| Integration test | TCP, TLS, HTTP/2, database, broker, proxy | Real server on ephemeral port and containerized dependencies |
| End-to-end test | Cross-service flows in a near-production environment | Dedicated integration environment, small count |

The goal is to keep the majority of tests at levels that do not require real networking, while maintaining a small, targeted set of integration tests to verify critical infrastructure boundaries.

## 2. Testing use cases directly

Business rules should not depend on `ManagedChannel`, `StreamObserver`, or sockets. The service adapter receives a protobuf request, converts it into an application command/query, invokes the use case, and maps the result back to a protobuf response.

~~~text
gRPC client
    |
    v
Generated stub
    |
    v
gRPC service adapter
    |
    v
Application use case
    |
    +---- repository / external port
~~~

Use-case unit tests should call the use case directly and replace external dependencies with fakes or mocks. There is no need to stand up a gRPC server to test a rule like "reject order quantities less than 1".

Example:

~~~java
class CreateOrderUseCaseTest {
    private final OrderRepository repository =
            mock(OrderRepository.class);
    private final CreateOrderUseCase useCase =
            new CreateOrderUseCase(repository);

    @Test
    void rejectsNonPositiveQuantity() {
        CreateOrderCommand command =
                new CreateOrderCommand("customer-1", List.of(
                        new OrderLine("sku-1", 0)));

        assertThrows(
                InvalidOrderException.class,
                () -> useCase.execute(command));

        verifyNoInteractions(repository);
    }
}
~~~

This test verifies validation and guarantees the repository is not called when the command is invalid. It needs no port, channel, server, or broker. Other tests can use an in-memory fake repository if multiple business steps need verification.

## 3. Using fakes and mocks at the right boundary

A well-substituted dependency keeps tests focused on the unit under test:

- **Fake:** a simplified yet working implementation, such as an in-memory repository or fake clock.
- **Mock:** an object recording invocations to verify interactions, useful when ensuring a side effect did not occur.
- **Stub:** returns fixed results per call, used to steer execution branches.

Prefer fakes when a dependency needs realistic state and behavior. Use mocks for critical interactions such as "do not publish a message when validation fails". Avoid deeply mocking every method of generated stubs, channels, and the gRPC runtime; such tests tightly couple to implementation details rather than observable contracts.

Example fake repository:

~~~java
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}
~~~

This fake suits testing basic read/write logic. It does not verify SQL, transactions, isolation, or migrations; those belong to integration tests against a real database.

## 4. What is the in-process gRPC transport?

gRPC Java provides an **in-process** transport via `grpc-inprocess`. It lets you create a server and channel in the same JVM and invoke the service using generated stubs like a normal client, without opening TCP sockets or passing through a network interface.

In-process is useful for testing:

- Generated blocking, future, or async stubs calling the right service method.
- Service adapters mapping requests and responses accurately.
- gRPC statuses, metadata, and interceptors operating within a call.
- Unary and streaming RPCs obeying `onNext`, `onError`, and `onCompleted` rules.
- Clients receiving the expected errors when the service returns a status.
- Call-level deadlines and cancellation handled in transport tests.

In-process does not verify TCP, DNS, TLS handshakes, certificates, ALPN, proxies, HTTP/2 wire behavior, or firewalls. It is an in-JVM gRPC transport test, not proof that a server deployed over a network works.

## 5. Adding the in-process dependency for tests

Use the `grpc-inprocess` version matching the rest of your gRPC Java modules. If the project manages dependencies with a gRPC BOM, let the BOM choose the version rather than specifying a standalone version that might drift from the runtime.

Gradle example:

~~~kotlin
dependencies {
    testImplementation("io.grpc:grpc-inprocess")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-junit-jupiter")
}
~~~

If the project uses Spring Boot dependency management or a version catalog, declare dependencies using that existing mechanism. Never pull `grpc-inprocess` into production runtime just because tests need it; it is a test-scoped dependency.

## 6. Setting up an in-process server and channel

The test fixture creates a dedicated server name, registers the service implementation, starts the in-process server, and builds a channel with the same name:

~~~java
class OrdersGrpcServiceTest {
    private Server server;
    private ManagedChannel channel;
    private OrdersGrpc.OrdersBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrdersGrpcService(
                        new InMemoryOrderRepository()))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        stub = OrdersGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(5, TimeUnit.SECONDS);
        server.awaitTermination(5, TimeUnit.SECONDS);
    }

    @Test
    void returnsOrderThroughGeneratedStub() {
        GetOrderReply reply = stub.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build());

        assertEquals("order-42", reply.getOrderId());
    }
}
~~~

Imports and generated classes depend on the package declared in `.proto` files. The example assumes an `Orders` service with a `GetOrder` RPC and a server implementation named `OrdersGrpcService`.

`InProcessServerBuilder.generateName()` prevents name collisions between parallel tests. The server and channel must be shut down after each test to avoid leaking resources or causing other tests to hit the wrong service. In real tests, if `channel` or `server` could be uninitialized when setup fails, check for null before shutting down during cleanup.

## 7. Meaning and limits of directExecutor

`directExecutor()` runs callbacks immediately on the calling thread instead of dispatching to another executor. It keeps tests simple, reduces scheduling nondeterminism, and suits many synchronous service tests.

However, a direct executor does not fully simulate production server concurrency. It can expose different reentrancy or callback ordering compared to real executors; never use it as proof of thread safety, absence of race conditions, throughput, or fairness. For cancellation tests, async callbacks, or executor-dependent code, configure a dedicated executor and synchronize tests with latches/futures instead of sleep.

Never use `Thread.sleep()` to wait for callbacks. Wait with `CountDownLatch`, `CompletableFuture`, or assertions with bounded timeouts so tests have clear termination conditions.

## 8. Checking gRPC statuses and errors without opening ports

Service adapters should translate domain errors into meaningful gRPC statuses. In-process stubs let you check statuses without networking:

~~~java
@Test
void mapsMissingOrderToNotFound() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("missing")
                            .build()));

    assertEquals(Status.Code.NOT_FOUND, error.getStatus().getCode());
}
~~~

This test verifies client-observable behavior: the RPC terminates with `NOT_FOUND`. It does not need to inspect a specific internal repository exception if that exception is an implementation detail.

For metadata, send headers via `MetadataUtils`/stub interceptors and verify that the server interceptor passes the principal or correlation context into the handler properly. Test missing, malformed, and invalid metadata cases as well.

## 9. Testing unary and streaming RPCs

Unary RPCs return one response and complete. Server streaming can return multiple responses before completing. The in-process transport helps verify the contract and terminal signals:

~~~java
@Test
void serverStreamingEmitsAllItemsThenCompletes() {
    List<OrderUpdate> updates = new ArrayList<>();
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();

    stub.watchOrder(
            WatchOrderRequest.newBuilder()
                    .setOrderId("order-42")
                    .build(),
            new StreamObserver<>() {
                @Override
                public void onNext(OrderUpdate value) {
                    updates.add(value);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    completed.countDown();
                }

                @Override
                public void onCompleted() {
                    completed.countDown();
                }
            });

    assertTrue(await(completed, 2, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(3, updates.size());
}
~~~

This is a condensed example; the `await` helper should translate interrupts into an appropriate test failure and never swallow errors. If callbacks can run concurrently, use a thread-safe collection or synchronize access. Tests must verify the server emits only one terminal signal and never calls `onNext` after `onError`/`onCompleted`.

For client streaming or bidirectional streaming, tests send requests sequentially through `StreamObserver`, verifying multi-message handling, backpressure/application flow, and terminal signals. In-process verifies the API flow, though it does not measure frame sizes, TCP buffering, or real HTTP/2 flow control.

## 10. Testing interceptors and metadata at the gRPC boundary

Interceptors are part of the runtime contract and can be tested with an in-process server. Cases worth checking:

- Valid metadata is read accurately.
- Missing or malformed metadata returns the expected status.
- Authentication interceptors create the right principal and never leak tokens in logs.
- Correlation IDs are placed into `io.grpc.Context`.
- Server interceptors forward to the handler exactly once.
- Exceptions in interceptors map to gRPC statuses.
- Client interceptors attach headers once per call.

Do not test only a parser helper if your goal is verifying the interceptor is attached to the server. An in-process test calling the generated stub against a server registered with the interceptor catches cases where the interceptor is missing from the chain.

## 11. Testing deadlines and cancellation

The in-process transport is well suited for checking call-level gRPC behavior:

~~~java
@Test
void clientDeadlineIsObservedByServer() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> slowStub.withDeadlineAfter(20, TimeUnit.MILLISECONDS)
                    .getOrder(request));

    assertEquals(Status.Code.DEADLINE_EXCEEDED,
            error.getStatus().getCode());
}
~~~

Tests need a controllable slow service test double and deterministic cleanup. Never use long sleeps to force timeouts; use a controllable latch or future to reproduce slow server responses.

RPC cancellation does not automatically roll back databases or retract published messages. Use-case unit tests must separately verify business cancellation policies; integration tests must check behavior once side effects have committed. In-process tests only verify that cancellation propagates across the call and the handler reacts as coded.

## 12. Testing downstream gRPC clients with an in-process server

If a use case calls another gRPC service, you can stand up an in-process server for the downstream service to test adapter/client integration without opening TCP:

~~~text
Test subject
    |
    v
Generated downstream stub
    |
    v
InProcessChannel
    |
    v
InProcessServer
    |
    v
Fake downstream service
~~~

The fake downstream service can return success, `UNAVAILABLE`, `NOT_FOUND`, or controlled slow responses. The test subject must map statuses and results properly. This verifies usage of generated stubs, deadlines, metadata, and error mapping through the gRPC API.

There is no need to mock every method of a generated stub. A real fake service over the in-process transport usually verifies more contract behavior while depending less on stub internals.

## 13. When is real networking still required?

Some behaviors cannot be proven by the in-process transport:

| Behavior | Why integration testing is needed |
|---|---|
| TCP bind, port conflicts, firewalls, routing | In-process does not open sockets |
| DNS and service discovery | No real hostname resolution step |
| TLS, certificates, SNI, mTLS | No TLS handshake is performed |
| ALPN and HTTP/2 negotiation | Does not test negotiation over the network |
| Proxies, ingress, service mesh | Calls do not traverse these components |
| Network interruption, packet loss, connection resets | Does not fully simulate network failures |
| Message broker delivery/ack/redelivery | Requires a real or containerized broker |
| Database transactions/locking/migrations | Fake repositories lack database semantics |
| Load, throughput, and resource usage | In-process direct executor does not represent production transport |

Maintain a small, well-scoped set of integration tests using ephemeral ports (such as port `0` if supported by the server builder), test certificates, and containerized brokers/databases when needed. Do not try to turn every unit test into an integration test just to make it "more real".

## 14. Distinguishing in-process tests, mock servers, and embedded servers

These techniques serve different purposes:

| Technique | Strengths | Limitations |
|---|---|---|
| Calling use cases directly | Fast, isolates business logic | Does not test the gRPC adapter |
| Mock/fake dependencies | Controls external errors and outputs | Does not prove real dependency implementations |
| gRPC in-process server | Tests stubs, services, statuses, metadata without TCP | Does not test TLS/HTTP2/networking |
| Real server on ephemeral port | Tests real sockets and transport | Slower, requires cleanup and avoiding port conflicts |
| Testcontainers | Tests real databases/brokers in isolated environments | Slower and requires Docker/runtime |

Do not confuse an in-process server with an embedded network server. In-process is not a Netty server bound to loopback; it is a separate transport built into gRPC Java.

## 15. Organizing tests in a Spring project

A clean structure can organize tests by package or source set:

~~~text
src/test/java/
  .../domain/
    CreateOrderUseCaseTest.java
  .../application/
    SubmitOrderHandlerTest.java
  .../grpc/
    OrdersGrpcServiceTest.java
    CorrelationInterceptorTest.java
  .../integration/
    OrdersGrpcTcpIntegrationTest.java
    OrdersGrpcTlsIntegrationTest.java
    OrderMessagingIntegrationTest.java
~~~

Domain/application unit tests do not need `@SpringBootTest`. Booting the entire Spring context for a pure Java class slows down tests and blurs wiring errors with logic errors.

For components requiring dependency-injection checks, use Spring test slices or a minimal context where appropriate. Use `@SpringBootTest` only when the goal is genuinely verifying full-application wiring or an integration path. Never start an embedded server on a fixed port across parallel tests.

If the Spring gRPC starter provides dedicated test support in your project version, use it to create test servers/channels. Otherwise, gRPC Java's in-process builders are a clear option; avoid assuming every starter shares the same test annotations or auto-configuration.

## 16. Managing lifecycle and test stability

Tests without real networking can still leak resources if channels and servers are not cleaned up:

- Create servers/channels per fixture or test class with clear scope.
- Shut down channels and servers in `@AfterEach`/`@AfterAll`.
- Do not share mutable service state across parallel tests unless thread-safe.
- Use unique in-process server names.
- Avoid sleep; synchronize with futures/latches.
- Bound timeouts so failing tests do not hang the suite.
- Ensure test-created executors or schedulers do not keep running after tests finish.

For tests using `directExecutor`, re-verify concurrency-sensitive flows with a real executor in a separate test. A test passing on a direct executor does not prove code is race-free in production.

## 17. Example testing strategy for an RPC

Suppose `GetOrder` takes `orderId`, authenticates the caller, reads a repository, and returns a protobuf response:

| Question to verify | Appropriate level | How to test |
|---|---|---|
| Is blank `orderId` rejected? | Use-case/validator unit test | Call directly and assert exception |
| Does the repository return the right order? | Use-case unit test | In-memory fake |
| Does the adapter map the order to protobuf properly? | In-process gRPC test | Generated stub calls service |
| Does a missing order return `NOT_FOUND`? | In-process gRPC test | Assert gRPC status code |
| Does the interceptor block callers without a token? | In-process gRPC test | Call through server with interceptor |
| Do the bound port and TLS certificate work? | Integration test | Real server and TLS client |
| Does the Kubernetes Service route to pods? | Environment test | Probe from pod/client inside cluster |

One RPC can have tests across multiple layers, but each test should answer one specific question. Never repeat the entire network matrix in every business test.

## 18. Common mistakes

| Bad practice | Consequence | Better approach |
|---|---|---|
| Starting a TCP server for every unit test | Slow tests, port and environment dependencies | Call use cases directly or use in-process |
| Over-mocking generated stubs | Tests couple to implementation and miss gRPC semantics | Use an in-process fake service when testing RPCs |
| Using in-process tests to conclude TLS works | No TLS handshake happens | Create a dedicated TLS integration test |
| Using fake repositories to conclude transactions work | Fakes do not simulate isolation/locking | Verify with database integration tests |
| Using `Thread.sleep()` to wait for callbacks | Flaky and slows down the suite | Use latches/futures with timeouts |
| Not shutting down channels/servers | Leaks executors and affects other tests | Clean up explicitly in lifecycle hooks |
| Running all tests with `@SpringBootTest` | Slow startup and hard-to-localize failures | Pick unit, slice, in-process, or integration per goal |
| Using `directExecutor` to test concurrency | Does not represent production scheduling | Test concurrency separately with proper executors |
| Running integration tests on fixed ports | Collisions during parallel runs | Use ephemeral ports and discover the bound port |

**Remember:** Do not use real networking for every unit test. Call domain/use-case classes directly to test logic; use fakes/mocks at dependency boundaries; use gRPC in-process servers/channels to test generated stubs, service adapters, statuses, metadata, and streaming without opening TCP. Keep a small integration test suite for TCP, TLS, HTTP/2, proxies, databases, and brokers—behaviors that in-process cannot verify.
