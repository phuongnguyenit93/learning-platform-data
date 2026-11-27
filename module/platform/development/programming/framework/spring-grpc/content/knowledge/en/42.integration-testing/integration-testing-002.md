# Connecting Test Clients to a Dynamic Port

## Learning Objectives

After this lesson, you will be able to:

- Explain why integration tests should use a dynamic port instead of hardcoding a port.
- Retrieve the actual port after the gRPC server has bound successfully.
- Create a **ManagedChannel** and stub pointing to the server address in the Spring test context.
- Set deadlines for RPCs and close the channel according to the test lifecycle.
- Distinguish the Spring Boot HTTP server port from the gRPC server port.
- Organize parallel tests, context caching, and TLS without environment dependencies.

## 1. Why Do Test Clients Need a Dynamic Port?

An integration test over TCP requires the client to know the address and port on which the gRPC server is listening. If all tests use a fixed port like **9090**, tests can fail when another process is using that port, when multiple tests run in parallel, or when two application contexts start at the same time.

The solution is to let the operating system allocate an available port when the server binds. With gRPC Java, pass **0** to **ServerBuilder.forPort(0)**. After the server starts successfully, read the actual port using **Server.getPort()** and then create the client channel to that port.

In **SPRING_GRPC**, the server is usually started alongside the Spring test context so that service implementations, interceptors, and dependencies are injected just like in the real application. The test client must connect to that exact context's gRPC listener. The Spring Boot web server port, if present, is a different listener and cannot be used in place of the gRPC port.

## 2. Connection Flow

~~~mermaid
flowchart TD
  A["Spring creates test ApplicationContext"] --> B["gRPC server starts with port 0"]
  B --> C["Server binds successfully"]
  C --> D["Read actual port"]
  D --> E["Create ManagedChannel to 127.0.0.1:port"]
  E --> F["Create stub and set deadline"]
  F --> G["Call RPC and verify result"]
  G --> H["Shutdown channel"]
  H --> I["Spring closes context and server"]
~~~

Order matters: create the channel only after the server has finished binding. Do not read the port before **start()** and do not guess the port from configuration. If the server is managed by Spring, obtain the port from the server's bean or lifecycle accessor after context refresh completes.

## 3. Binding Port 0 and Reading the Actual Port

With a self-managed gRPC Java server fixture:

~~~java
Server server = ServerBuilder.forPort(0)
    .addService(greeterService)
    .build()
    .start();

int actualPort = server.getPort();
~~~

**0** is a request to allocate a dynamic port, not the port the client will use. **getPort()** is only meaningful after the server starts successfully. If the server fails to bind, startup must fail and the test context should not proceed to create a channel.

If the Spring gRPC starter starts the server automatically, enable dynamic ports using the configuration supported by that exact starter/version and obtain the actual port through its test support API or server lifecycle bean. Do not assume all starters use the same property. Also do not assume **@LocalServerPort** returns the gRPC port; that annotation is typically tied to the Spring Boot web server.

Do not open **ServerSocket(0)**, read the port, and close the socket before the gRPC server binds. Another process can claim the port between those two operations. Let the gRPC server itself bind port 0.

## 4. Exposing the Port from a Server Fixture to Tests

A Spring fixture can expose the port after the server has started:

~~~java
final class TestGrpcServer implements SmartLifecycle {
    private final BindableService service;
    private volatile Server server;

    TestGrpcServer(BindableService service) {
        this.service = service;
    }

    @Override
    public synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }
        try {
            server = ServerBuilder.forPort(0)
                .addService(service)
                .build()
                .start();
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot start gRPC test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("gRPC test server is not running");
        }
        return current.getPort();
    }

    @Override
    public synchronized void stop() {
        Server current = server;
        server = null;
        if (current != null) {
            current.shutdown();
        }
    }

    @Override
    public boolean isRunning() {
        return server != null && !server.isShutdown();
    }
}
~~~

This is a minimal fixture to illustrate publishing the port. In real tests, **stop()** should wait on **awaitTermination** for a bounded duration and then call **shutdownNow()** if needed, while preserving the interrupt status if the thread is interrupted.

Register the fixture with **@TestConfiguration** and let Spring inject the service bean. If the starter already owns the server, do not create a second fixture: expose the port from the starter-managed server. Each context should have one clear server owner.

## 5. Creating a ManagedChannel to the Dynamic Port

Once the context has refreshed and the server is running, the test can inject the port provider and create the channel:

~~~java
@SpringBootTest
class GreeterIntegrationTest {
    @Autowired
    TestGrpcServer grpcServer;

    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void connectClient() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcServer.port())
            .usePlaintext()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
    }
}
~~~

**@BeforeEach** runs after Spring has created and refreshed the context, so the lifecycle bean has already been started. Using **127.0.0.1** helps avoid certain differences in resolving **localhost** to IPv4 or IPv6 across CI machines.

**usePlaintext()** is only meant for local TCP tests when the server does not have TLS enabled. If the test verifies TLS, the channel must be configured with the appropriate trust certificate and transport security.

## 6. Creating a Stub and Calling RPCs

Stubs are created from the channel. A blocking stub is suitable for simple unary tests:

~~~java
@Test
void connectsToTheDynamicallyBoundServer() {
    HelloReply reply = stub.sayHello(
        HelloRequest.newBuilder()
            .setName("Mai")
            .build());

    assertEquals("Hello, Mai", reply.getMessage());
}
~~~

For streaming RPCs, use an async stub and an observer:

~~~java
List<PriceUpdate> received = new CopyOnWriteArrayList<>();
CountDownLatch completed = new CountDownLatch(1);

GreeterGrpc.GreeterStub asyncStub =
    GreeterGrpc.newStub(channel)
        .withDeadlineAfter(3, TimeUnit.SECONDS);

asyncStub.watchPrices(
    SubscribeRequest.getDefaultInstance(),
    new StreamObserver<>() {
        @Override
        public void onNext(PriceUpdate update) {
            received.add(update);
        }

        @Override
        public void onError(Throwable error) {
            completed.countDown();
        }

        @Override
        public void onCompleted() {
            completed.countDown();
        }
    });

assertTrue(completed.await(4, TimeUnit.SECONDS));
~~~

This example illustrates waiting for a terminal callback; real tests should capture any received error separately to assert status, count, and message ordering. The latch timeout should be slightly longer than the RPC deadline so the test has time to observe the call result.

## 7. Deadlines Prevent Tests from Hanging

Every RPC in an integration test should have a finite deadline:

~~~java
GreeterGrpc.GreeterBlockingStub boundedStub =
    GreeterGrpc.newBlockingStub(channel)
        .withDeadlineAfter(2, TimeUnit.SECONDS);
~~~

If the server fails to start, the client cannot connect, or a handler hangs, the deadline ensures the call terminates instead of holding up the test suite indefinitely. Choose a duration suitable for CI; deadlines that are too short can cause flaky tests on heavily loaded machines.

An RPC deadline does not replace wait timeouts in the test framework. For async streaming, you need both a deadline for the call and a timeout for the test's **CountDownLatch**/future.

## 8. Closing the Channel at the Right Lifecycle Stage

The client channel is a resource owned by the test, not the server fixture. Close the channel after each test method:

~~~java
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
~~~

**shutdown()** initiates a graceful close; **awaitTermination()** waits for calls/channel to finish within the timeout. Only use **shutdownNow()** when termination does not complete in time. Do not close a shared channel while another RPC is still in flight.

Because the server belongs to the Spring context, Spring or the starter closes the server when the context is closed. Do not call **server.shutdownNow()** from individual test methods if the server is shared via context caching; doing so causes subsequent tests to connect to a stopped server.

## 9. Why Not Use the Spring Boot Web Port?

An application can simultaneously open:

- An HTTP server for REST/Actuator.
- A gRPC server for HTTP/2 gRPC.
- A management server or other auxiliary listeners.

**@LocalServerPort** typically provides the web server port, not the gRPC server port. Using the wrong port can cause handshake/protocol errors or connect to the HTTP application instead of gRPC.

Retrieve the port from the actual gRPC server bean or the starter's test support. If the starter does not expose the port directly, create a test-only abstraction to read the server address after lifecycle startup, rather than inferring it from the web port.

## 10. Dynamic Ports with Context Caching and Parallel Tests

Spring Test can cache the application context across multiple methods or classes with the same configuration. In that case, the server typically continues running with the context; each test only creates and closes its own channel.

Guidelines:

- Do not assume a new port is allocated for each **@Test**; the port is tied to the server/context lifecycle.
- Do not close the server from **@AfterEach** if the server belongs to a shared context.
- If there are two independent contexts, each context can bind its own dynamic port.
- Parallel tests still require state and service data isolation; dynamic ports only prevent socket conflicts.
- Do not share an already-shutdown channel across tests.

If a test leaves the context unusable, **@DirtiesContext** can tell Spring to evict the context from the cache and close lifecycle beans. Only use it when necessary because restarting the context slows down the suite.

## 11. When to Use DynamicPropertySource?

**@DynamicPropertySource** is useful when a port or endpoint is created outside the Spring context, such as Testcontainers starting an auxiliary service before the context needs to read the property.

For a gRPC server created inside the Spring context itself, you cannot read the port from the server bean inside **@DynamicPropertySource** before the context instantiates that bean. In this case, inject the port provider and create the channel after refresh, such as in **@BeforeEach**.

If the starter requires a port via a property, you can configure the value **0** before the context starts; afterwards, you still need an API/accessor to retrieve the actual bound port. A configured property value of **0** is not an address a client can connect to.

## 12. TCP Tests, In-Process Tests, and TLS

| Test type | What it verifies | What it does not prove |
| --- | --- | --- |
| **In-process** | Service dispatch, stubs, some interceptors, and gRPC logic | TCP sockets, port binding, network HTTP/2, and TLS handshake. |
| **TCP with dynamic port** | Server startup, binding, channel connection, and real HTTP/2 transport | TLS if the test is using plaintext. |
| **TCP with TLS** | Certificates, trust chain, hostname verification, and handshake | Does not automatically verify all production configs if test certs/trust differ. |

Do not use in-process tests as the sole proof that a production server can open a port and accept network connections. A small set of TCP tests with dynamic ports helps verify the actual transport path.

When testing TLS, use a test certificate with a matching hostname/SAN and configure the channel to trust that certificate. Do not disable certificate verification to make a test pass; doing so skips the exact behavior under test.

## 13. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using a fixed port | Conflicts during parallel tests or when port is busy | Bind port 0 and retrieve the actual port. |
| Connecting before server starts | Connection refused or flaky tests | Create the channel after context refresh/lifecycle start. |
| Using **@LocalServerPort** for gRPC | Connects to the wrong web listener | Get the port from the gRPC server/starter accessor. |
| Reading port from configuration **0** | Client tries to connect to port 0 | Read the bound port from the server after startup. |
| Opening and closing **ServerSocket** to probe a port | Race condition claiming the port before gRPC binds | Let the server bind port 0 directly. |
| Not shutting down the channel | Thread/connection leaks and hanging suite | Close the channel in teardown. |
| Stopping the server in every **@AfterEach** | Breaks the server shared via context cache | Let Spring lifecycle stop the server. |
| Using plaintext to conclude TLS works | Skips certificate/handshake verification | Write dedicated TCP TLS tests. |
| Testing only in-process | Misses bind/transport errors | Add TCP integration tests. |

## 14. Hands-On Exercise

Create an integration test for the **Greeter** service:

1. Have Spring start the gRPC server on a dynamic port (**0**) or use the starter's port accessor.
2. After context refresh, retrieve the actual port from the server lifecycle bean.
3. Create a **ManagedChannel** to **127.0.0.1** and that port.
4. Create a blocking stub with a deadline and call a unary RPC.
5. Create an async stub to test a server-streaming RPC, waiting for the terminal callback with a timed latch.
6. Close the channel in teardown; let Spring stop the server when the context ends.
7. Run tests in parallel and verify there are no port collisions.
8. Add a TLS test if the application deploys gRPC over TLS.

**Completion criteria:** the test client connects to the right gRPC listener using the actual port, RPCs have deadlines, the channel is closed at the right time, and the server continues to follow the Spring context lifecycle.

## 15. Takeaways

- Use port **0** so the OS allocates a port for the gRPC server; read the actual port after the server starts.
- Create **ManagedChannel** after the Spring context refreshes and the server has bound.
- Retrieve the port from the gRPC server or starter test support; **@LocalServerPort** is typically the web port.
- Create stubs from the channel and set a deadline for every RPC.
- The test owns the client channel and must shut it down; Spring or the starter owns the server lifecycle.
- Context caching can keep the server alive across multiple test methods; do not stop a shared server from per-method teardown.
- **@DynamicPropertySource** fits endpoints created before the context; servers created inside the context need a port accessor after refresh.
- In-process tests do not replace TCP/HTTP2 tests; TLS requires dedicated test certificates and trust configuration.

Connecting test clients to a dynamic port keeps Spring gRPC integration tests independent of fixed ports, ensures stability during parallel runs, and verifies both server lifecycle and real transport.
