# Stubs in Tests

## 1. Objectives

In Spring gRPC, a generated stub is the client API produced from a Protobuf service. Tests use stubs to invoke RPCs and verify the behavior the client actually observes: responses, statuses, metadata, deadlines, and streaming. The right testing approach depends on the layer under test: the application service, the gateway/client adapter, or the full Spring gRPC server.

**Stubs in tests** means using generated gRPC stubs in a test environment to verify that the client calls the right method, serializes requests, receives and decodes responses, handles errors, and honors call options. A good test picks the right boundary:

- Unit tests for application services typically mock gateway interfaces.
- Tests for gateways and generated stubs can use an in-process gRPC server.
- Spring integration tests should start the server/client using the application's configuration.
- Deployment/transport tests should connect over TCP/TLS in an environment close to production.

After this lesson, you can:

- Create blocking, async, or future stubs in tests.
- Use `InProcessServerBuilder` and `InProcessChannelBuilder` for fast RPC tests.
- Write fake services by extending generated `ImplBase`.
- Verify responses, statuses, deadlines, metadata, and streaming.
- Manage server/channel lifecycles in JUnit.
- Distinguish in-process tests from Spring integration tests over a real transport.
- Avoid mocking generated stubs at the wrong layer.

## 2. Choosing the Right Test Type

Not every test needs to start a gRPC server. Choose the boundary based on what needs to be proven:

| Goal | Appropriate Test Type | What Is Verified |
|---|---|---|
| Application service coordinates multiple dependencies properly | Unit test, mock gateway interface | Business rules and orchestration |
| Gateway builds requests and maps responses/statuses properly | Generated stub calling an in-process fake service | RPC method, Protobuf marshalling, and mapping |
| Spring registers service/client beans properly | Spring application context test | Dependency injection, auto-configuration, and service registration |
| TLS, DNS, load balancing, proxies, or sockets | Integration test over TCP/TLS | Transport and connection configuration |
| Client/server version differences | Compatibility test with old/new artifacts | Wire contract and mixed-version behavior |

A unit test that mocks `CatalogClient` does not prove the generated stub calls the right full method path. Conversely, an in-process test does not need to re-verify every business rule of the application service. Each test layer should have a clear goal.

## 3. What Is the In-Process Transport?

gRPC Java provides an in-process transport so client and server communicate within the same JVM without opening a TCP socket. It still exercises generated stubs, service descriptors, the gRPC call lifecycle, and Protobuf marshallers. Therefore, it is an appropriate choice for fast, reliable RPC-boundary testing.

The two main builders:

- `InProcessServerBuilder`: creates a test server with a given name.
- `InProcessChannelBuilder`: creates a channel pointing to the server with the same name.

Test dependencies require `grpc-inprocess` on the same release line as the other gRPC Java libraries:

```kotlin
dependencies {
    testImplementation("io.grpc:grpc-inprocess:<grpc-version>")
}
```

Replace `<grpc-version>` with the version centrally managed in the project's BOM or dependency constraints. Do not introduce a version that differs from `grpc-api`, `grpc-stub`, and the other gRPC artifacts in use.

In-process tests do not verify TLS handshakes, certificates, DNS, load balancing, HTTP/2 proxies, or socket settings. Those aspects require tests over a real transport.

## 4. Building a Fake Service with Generated ImplBase

Suppose the contract defines a unary RPC:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (Product);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string name = 2;
}
```

The gRPC Java plugin generates `CatalogServiceGrpc.CatalogServiceImplBase`. Tests can extend this base class to create a fake service:

```java
final class FakeCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<Product> observer) {

        if ("missing".equals(request.getProductId())) {
            observer.onError(
                    Status.NOT_FOUND
                            .withDescription("product not found")
                            .asRuntimeException());
            return;
        }

        Product response = Product.newBuilder()
                .setProductId(request.getProductId())
                .setName("Keyboard")
                .build();

        observer.onNext(response);
        observer.onCompleted();
    }
}
```

A fake service can return fixed data, simulate errors, or record requests for test assertions. It should keep logic minimal and deterministic; do not copy the entire production implementation into tests.

## 5. Creating an In-Process Server and Channel in JUnit

JUnit 5 example creating a server before each test and closing resources afterward:

```java
class CatalogStubTest {

    private Server server;
    private ManagedChannel channel;
    private CatalogServiceGrpc.CatalogServiceBlockingStub blockingStub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new FakeCatalogService())
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        blockingStub = CatalogServiceGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            channel.awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow();
            server.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

A unique server name is generated for each test to avoid collisions when tests run in parallel. Both channel and server are resources that must be closed; do not leave threads or calls running after a test.

`directExecutor()` runs callbacks directly on the calling thread's executor, keeping tests simple and reducing scheduling nondeterminism. It does not fully simulate production concurrency. For race, cancellation, callback-thread, or backpressure tests, add tests using a separate executor and synchronize with latches.

## 6. Testing Unary Responses

Once the stub is created, the test invokes the RPC like a real client:

```java
@Test
void blockingStubReturnsProduct() {
    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId("product-42")
            .build();

    Product response = blockingStub.getProduct(request);

    assertEquals("product-42", response.getProductId());
    assertEquals("Keyboard", response.getName());
}
```

This test exercises the generated blocking stub, method descriptor, in-process channel, fake server implementation, and response observer. It is well suited for verifying request/response mapping of a gateway or generated client API.

If a test merely calls `FakeCatalogService.getProduct()` directly, it does not test the stub, marshalling, or gRPC call lifecycle. That is a unit test for the service implementation, which has its own value but does not replace stub tests.

## 7. Testing gRPC Statuses

A fake service can simulate business errors or transport statuses:

```java
@Test
void blockingStubPreservesNotFoundStatus() {
    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId("missing")
            .build();

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> blockingStub.getProduct(request));

    assertEquals(Status.Code.NOT_FOUND,
            error.getStatus().getCode());
}
```

Check status codes and metadata/trailers if they are part of the contract. Avoid over-relying on error descriptions, as description text may change or be normalized by a gateway layer.

For an application gateway, you can add tests verifying that `NOT_FOUND` is mapped to the appropriate business exception. Those tests should focus on mapping at the gateway/application boundary without repeating full Protobuf transport tests.

## 8. Testing Asynchronous and Future Stubs

### Asynchronous Stub

Async stubs use `StreamObserver`. Tests must wait for callbacks to finish using a latch with a timeout so the suite cannot hang:

```java
@Test
void asyncStubReturnsResponse() throws InterruptedException {
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<Product> result = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    var asyncStub = CatalogServiceGrpc.newStub(channel);
    asyncStub.getProduct(
            GetProductRequest.newBuilder()
                    .setProductId("product-42")
                    .build(),
            new StreamObserver<>() {
                @Override
                public void onNext(Product value) {
                    result.set(value);
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

    assertTrue(completed.await(2, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals("product-42", result.get().getProductId());
}
```

Do not use busy-wait loops or arbitrary sleeps. Latches let tests wait for the exact callback; timeouts ensure bounded failure if the callback never arrives.

### Future Stub

Future stubs suit unary RPCs:

```java
@Test
void futureStubCompletesWithProduct() throws Exception {
    var futureStub = CatalogServiceGrpc.newFutureStub(channel);

    ListenableFuture<Product> future = futureStub.getProduct(
            GetProductRequest.newBuilder()
                    .setProductId("product-42")
                    .build());

    Product response = future.get(2, TimeUnit.SECONDS);
    assertEquals("product-42", response.getProductId());
}
```

Use `get(timeout, unit)` instead of waiting indefinitely. When a test fails, the timeout indicates the call did not complete instead of hanging CI.

## 9. Testing Streaming Stubs

Generated asynchronous stubs support server-streaming, client-streaming, and bidirectional streaming. Tests should verify message count, ordering, completion, and error lifecycles.

Example fake server-streaming service:

```java
final class FakeInventoryService
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    @Override
    public void watchInventory(
            WatchInventoryRequest request,
            StreamObserver<InventoryUpdate> observer) {
        observer.onNext(update("product-1", 4));
        observer.onNext(update("product-2", 9));
        observer.onCompleted();
    }
}
```

A client test can collect the messages:

```java
CountDownLatch completed = new CountDownLatch(1);
List<InventoryUpdate> updates =
        new CopyOnWriteArrayList<>();
AtomicReference<Throwable> failure = new AtomicReference<>();

asyncStub.watchInventory(request, new StreamObserver<>() {
    @Override
    public void onNext(InventoryUpdate value) {
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

assertTrue(completed.await(2, TimeUnit.SECONDS));
assertNull(failure.get());
assertEquals(2, updates.size());
```

For client-streaming or bidirectional streaming, tests should verify that the request observer is closed with `onCompleted()`, the server returns the expected response, and errors on either side propagate according to contract. Do not send further messages after a terminal signal. When testing flow control/backpressure, use real executors and enough messages to exercise the behavior rather than relying solely on `directExecutor()`.

## 10. Testing Deadlines and Cancellation

Deadlines are call options, so tests should set deadlines on derived stubs:

```java
var shortDeadlineStub = blockingStub.withDeadlineAfter(
        50, TimeUnit.MILLISECONDS);
```

The fake service can wait on a latch or perform controlled-duration work to test deadlines. Use safe timeout margins and avoid relying on very short `Thread.sleep()` intervals, as CI scheduling can jitter.

What to verify:

- Calls exceeding the deadline return `DEADLINE_EXCEEDED`.
- Client cancellation is observed by the server if the handler monitors cancellation.
- Server work can stop or avoid side effects when the call has been cancelled.
- Retries do not fire automatically if the call has side effects not protected by idempotency.

In-process transport is suitable for testing deadline/cancellation logic, while socket timeouts, proxy timeouts, and network interruptions require a real transport.

## 11. Testing Metadata and Interceptors

Metadata is per-RPC data. You can use a client interceptor to attach headers and a server interceptor/fake service to verify the server receives the expected values.

Example key declaration:

```java
static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
                "x-request-id",
                Metadata.ASCII_STRING_MARSHALLER);
```

In the test, create fresh metadata for the call:

```java
Metadata headers = new Metadata();
headers.put(REQUEST_ID, "test-request-17");

var callStub = blockingStub.withInterceptors(
        MetadataUtils.newAttachHeadersInterceptor(headers));
```

The fake service or server interceptor can read the header and store the value into an `AtomicReference` for assertion. Never share a mutable `Metadata` across concurrent tests or calls.

Interceptor tests should verify:

- Headers are attached with the exact key and value.
- The interceptor does not overwrite another call's metadata.
- Tracing/metrics are recorded only once.
- Tokens or sensitive data are not logged.
- Response headers/trailers are read properly on the client when required by the API.

## 12. Test the Generated Stub or Mock the Stub?

A generated stub is a transport API. Mocking stubs directly can be useful in some unit tests, but it usually fails to verify serialization, method paths, interceptors, or status mapping. Some generated stub classes are `final`, so mockability also depends on Mockito/mock-maker configuration.

Practical rule of thumb:

- Application service: prefer depending on a gateway interface and mocking the gateway in unit tests.
- Gateway: use the real generated stub against an in-process server to verify requests/responses and errors.
- Server implementation: test business logic separately; add RPC tests to verify observers/statuses.
- Spring configuration: test bean wiring and service registration with an application context test.
- Transport/security: use separate TCP/TLS tests.

If you need to mock a stub to isolate a tiny branch, keep that test at the unit level and do not treat it as proof that the gRPC client works end to end.

## 13. Spring Integration Tests

In-process tests do not prove that Spring registered the right service beans or created client channels according to application configuration. A Spring integration test should:

1. Start the application context with the real gRPC server configuration.
2. Use a random port or the test-port mechanism supported by the Spring gRPC starter.
3. Obtain the endpoint/port from the context instead of hard-coding a shared port.
4. Create generated stubs via a test channel or inject configured client beans.
5. Invoke RPCs against the Spring-managed server.
6. Verify service registration, interceptors, security, and exception mapping.
7. Close the test channel and context according to lifecycle.

Annotation names, properties to enable random ports, and ways to retrieve the port depend on the Spring gRPC starter/version. Use the test support provided by the starter in your project; do not assume all starters share identical annotations or properties.

For TLS, configure test certificates and trust stores mirroring the production setup while using dedicated test certificates. In-process channels do not perform TLS handshakes and cannot replace these tests.

## 14. Test Isolation and Resource Management

gRPC tests become flaky easily if channels/servers stay alive after tests or multiple tests share the same server name or port.

Checklist:

- Use `InProcessServerBuilder.generateName()` for every server fixture.
- Each test or test class has clear ownership of its server/channel.
- Always shut down channels and servers in `@AfterEach`/`@AfterAll`.
- Wait for termination with a finite timeout.
- Do not share mutable observers, metadata, or request builders across tests.
- Do not use fixed ports when tests run in parallel.
- Do not depend on test execution order.
- Use deterministic fixture data and avoid unnecessary external service calls.

If using a JUnit extension or shared test fixture, ensure cleanup still runs even when assertions or setup fail. Avoid letting an exception during setup leave a newly created channel unclosed.

## 15. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Tests call the service directly, yet stubs fail | Tests bypass generated stubs/channels | Add in-process RPC tests |
| CI hangs on async callbacks | Waiting without timeouts or observer never terminates | Use latches/futures with timeouts |
| Tests pass, yet Spring does not register the service | Only using a fake in-process server | Add a Spring application context test |
| Tests pass, yet production TLS fails | In-process transport has no TLS | Test over TCP/TLS with test certificates |
| Parallel tests collide on server name | Using a fixed in-process server name | Generate a unique name per fixture |
| Channels/threads leak after tests | Missing shutdown or missing awaitTermination | Clean up servers/channels in lifecycle hooks |
| Mocking the stub fails | Generated stub is final or unmockable API | Mock a gateway interface or use a fake server |
| Wrong method path goes undetected | Only testing mappers or mocking stubs | Call the generated stub against a server fixture |
| Metadata leaks across tests | Sharing mutable Metadata | Create separate metadata per call |
| Deadline tests are flaky | Relying on tiny sleeps or direct executors | Use latches, safe timeout margins, and appropriate executors |

## 16. Hands-On Exercise

**Scenario:** `CatalogGateway` uses a blocking stub to call `GetProduct`; another client uses an async stub for `WatchInventory`. The Spring application must verify responses, NOT_FOUND errors, deadlines, and request ID metadata.

Complete the following:

1. Add the `grpc-inprocess` test dependency matching the gRPC Java runtime release line.
2. Write a fake `CatalogServiceImplBase` returning a product or `NOT_FOUND` based on product ID.
3. Set up an in-process server and channel with a unique name in JUnit 5.
4. Create a blocking stub and test request/response over a real RPC.
5. Test that `StatusRuntimeException` preserves `NOT_FOUND`.
6. Create an async stub, collecting multiple inventory updates with an observer and a timed latch.
7. Attach `x-request-id` via a client interceptor and verify the server receives the right metadata.
8. Use a derived stub with a short deadline; verify `DEADLINE_EXCEEDED` using a fake service with controlled wait behavior.
9. Shut down the channel/server and await termination after each test.
10. Add a Spring integration test against an application-context-managed server; if TLS is used, test separately over TCP/TLS.

**Completion criteria:** tests use real generated stubs; fake services behave deterministically; responses/statuses/metadata/deadlines are verified; async tests cannot hang; resources are closed; in-process tests are clearly separated from Spring/transport integration tests.

## 17. Takeaways

Test generated stubs by invoking real RPCs against a fake service rather than only calling implementations directly or mocking every transport layer. `InProcessServerBuilder` and `InProcessChannelBuilder` let you verify generated stubs, Protobuf marshalling, method routing, statuses, metadata, and streaming without opening TCP sockets. Use JUnit lifecycle hooks to generate unique server names and always shut down channels and servers. Async/future tests must always have timeouts. In-process tests do not verify Spring bean registration, TLS, DNS, or load balancing; complement them with Spring application context and TCP/TLS integration tests for those boundaries. At the application layer, mock gateway interfaces to test orchestration; at the gateway layer, use real stubs to test gRPC behavior.
