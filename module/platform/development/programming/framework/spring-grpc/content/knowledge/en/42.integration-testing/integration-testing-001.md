# Starting the gRPC Server in the Test Context

## Learning Objectives

After this lesson, you will be able to:

- Explain how Spring Test creates and manages an application context for an integration test.
- Start the gRPC server after service beans are ready and stop the server when the context closes.
- Use dynamic ports to avoid port conflicts between test runs.
- Create a ManagedChannel and stub to connect to the server running in the test context.
- Distinguish between testing over real TCP and in-process transport.
- Manage channels, server lifecycle, context caching, and test isolation in Spring Boot.

## 1. Why Start the Server in the Test Context?

Unit testing a service implementation can call the Java method directly, but that does not test the process of a gRPC call going through the server. An integration test needs to verify that the service was created properly by Spring, gRPC registered the service, the server opened a port, the client can connect, and the message passes through serialization, HTTP/2 transport, and status handling.

With **SPRING_GRPC**, the server needs access to Spring-managed dependencies such as repositories, business services, interceptors, and configuration. Starting the server in the Spring test context helps test those components together.

The goal is to let Spring manage the server lifecycle: when the context is refreshed, the server starts listening; when the context closes, the server stops and releases resources. The test only needs to create a client channel to the running server's port.

## 2. Spring Test Context Lifecycle

**@SpringBootTest** creates an application context close to the actual application configuration. Spring instantiates beans, injects dependencies, applies configuration, and completes refresh before running test methods.

If the gRPC server is registered as a lifecycle bean or managed by the starter itself, the server will start during context refresh. When Spring closes the context, the lifecycle bean receives the stop signal to shut down the server.

~~~mermaid
flowchart TD
  A["JUnit starts test class"] --> B["Spring creates ApplicationContext"]
  B --> C["Create service and dependency beans"]
  C --> D["Refresh context / start lifecycle"]
  D --> E["gRPC server binds port"]
  E --> F["Test creates channel and calls RPC"]
  F --> G["Test closes channel"]
  G --> H["Spring closes ApplicationContext"]
  H --> I["gRPC server shutdown"]
~~~

Do not manually start the server in every **@BeforeEach** if Spring already manages the server. That approach can create multiple servers, bind duplicate ports, or leave old servers running when the test ends.

## 3. Prefer Server Lifecycle Managed by the Starter

If the application uses a Spring gRPC starter with auto-configuration, let the starter register the services and start the server. In tests:

- Load the application context using **@SpringBootTest**.
- Configure the server to use a dynamic port using the property supported by that exact starter version.
- Retrieve the actual port from the test support mechanism or server lifecycle API provided by the starter.
- Create a **ManagedChannel** to that port.
- Let Spring shut down the server when the context is closed.

Property names, local port annotations, and server access APIs depend on the starter and version. For example, **spring.grpc.server.port** only applies to Spring gRPC versions that use that configuration namespace; other starters may use different names. Check the exact documentation of your project's dependency rather than copying a property from another starter.

Do not register an additional custom test server if auto-configuration has already started a server for the same service and port. A test context should only have one clear owner for the server under test.

## 4. Self-Managed Server Test Fixture Using Spring Lifecycle

When a project does not use a starter that auto-starts the server or needs an independent fixture, you can register the test server as a **SmartLifecycle** bean. Spring will call **start()** during refresh and **stop()** when the context closes.

Example fixture:

~~~java
import io.grpc.BindableService;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.springframework.context.SmartLifecycle;

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
            throw new IllegalStateException(
                "Cannot start test gRPC server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("gRPC server is not running");
        }
        return current.getPort();
    }

    @Override
    public synchronized void stop() {
        Server current = server;
        server = null;
        if (current == null) {
            return;
        }

        current.shutdown();
        try {
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                current.shutdownNow();
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public boolean isRunning() {
        Server current = server;
        return current != null && !current.isShutdown();
    }
}
~~~

**ServerBuilder.forPort(0)** asks the operating system to allocate an available port. After starting, **Server.getPort()** returns the actual port for the test client to connect to. **stop()** shuts down the server gracefully first, then falls back to **shutdownNow()** if the server does not terminate within the timeout.

This fixture is an option for test contexts that manage their own server. If the starter already manages the server, use the starter's lifecycle/port accessor instead of registering a second fixture.

## 5. Registering the Fixture in Test Configuration

Create a test configuration so Spring injects the service implementation and manages the fixture:

~~~java
import io.grpc.BindableService;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class GrpcTestServerConfiguration {
    @Bean
    TestGrpcServer testGrpcServer(BindableService greeterService) {
        return new TestGrpcServer(greeterService);
    }
}
~~~

In a real project, the bean type can be the concrete service class extending the generated **GreeterGrpc.GreeterImplBase**. Use the concrete type in the bean parameter if the context has multiple BindableService beans so Spring selects the right service. Ensure the service bean is created by component scanning or declared in the test configuration.

Do not use this test configuration at the same time as server auto-configuration binding the same service/port. Choose a single server management approach for the test.

## 6. Creating a Channel After the Server Starts

The test can inject the fixture and create the channel in **@BeforeEach**:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(GrpcTestServerConfiguration.class)
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
    void closeChannel() throws InterruptedException {
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

Spring finishes refreshing and starts **SmartLifecycle** before JUnit runs **@BeforeEach**, so **grpcServer.port()** is already available. Using **127.0.0.1** helps tests avoid IPv4/IPv6 resolution differences for **localhost** in some environments.

**usePlaintext()** is only suitable for local TCP fixtures without TLS enabled. If the test objective includes TLS, create the channel with a trust certificate and the corresponding security configuration; do not accidentally test plaintext and conclude that TLS works.

## 7. Calling RPCs and Verifying Real Results

A unary test can invoke the blocking stub:

~~~java
@Test
void invokesSpringManagedGreeter() {
    HelloReply reply = stub.sayHello(
        HelloRequest.newBuilder()
            .setName("Lan")
            .build());

    assertEquals("Hello, Lan", reply.getMessage());
}
~~~

This is an integration test over TCP: the request is serialized, transmitted over HTTP/2, dispatched by the server to the service bean, the response is serialized, and the client parses it back. It can be extended to test:

- Status codes when the service throws errors.
- Interceptors, metadata, and authentication.
- Deadlines and cancellation.
- Unary and streaming RPCs.
- TLS, compression, and message-size limit configurations.

Set a deadline for test RPCs so failures do not hang the suite indefinitely. Test deadlines should be long enough for slow CI environments while still shorter than the overall test suite timeout.

## 8. Managing Channel and Server Separately

Channels and servers have different owners:

| Component | Who creates it? | Who closes it? |
| --- | --- | --- |
| Spring application context | Spring Test | Spring Test closes it when evicted from cache or when tests finish per configuration. |
| Starter-managed gRPC server | Starter/Spring lifecycle | Starter/Spring lifecycle. |
| **TestGrpcServer** fixture | Spring test configuration | Spring invokes **SmartLifecycle.stop()**. |
| Client **ManagedChannel** | Test or test client bean | Test closes it after each test or after use. |
| Stub | Created from channel | No separate shutdown needed; stop using when channel closes. |

Do not call **server.shutdownNow()** directly from individual tests if the server belongs to the Spring context; doing so causes other tests sharing the context to encounter a dead server. Conversely, do not leave a client channel open across multiple tests if each test requires an independent connection state.

## 9. Dynamic Ports and Avoiding Test Conflicts

Do not hardcode a port like **9090** for integration tests running in parallel. Another test or local process may already be using that port.

With the gRPC Java fixture, bind port **0** and then read the assigned port from **Server.getPort()**. With a starter, configure a dynamic port using the version-supported property and retrieve the actual port via the corresponding test support.

Do not manually find a free port by opening **ServerSocket(0)**, reading the port, and closing the socket before gRPC binds. Another process can claim the port in the gap between the two operations. Let the gRPC server itself bind port 0 directly.

Each separate application context may have a different dynamic port. If Spring Test caches the context, the server may stay running and be shared across methods/classes using the same context configuration; tests must not arbitrarily stop that shared server.

## 10. Context Caching and Test Isolation

Spring Test typically caches application contexts to reduce suite execution time. This means:

- **@BeforeEach** and **@AfterEach** run for each test method.
- The server lifecycle bean usually lives with the context rather than starting/stopping for every method.
- Channels created by tests can be closed after each method.
- Mutable state in singleton services may persist across methods.

If a service holds business state, reset the state through an explicit fixture/test API or use a fresh context when truly necessary. **@DirtiesContext** forces Spring to evict the context from the cache and close lifecycle beans, but slows down the suite; only use it when a test leaves the context unusable.

For parallel test runs, ensure services do not share unsafe mutable state and test data has separate namespaces. Dynamic ports avoid bind conflicts but do not automatically guarantee test isolation for databases, caches, or singleton beans.

## 11. When to Use In-Process Transport?

An in-process server/channel can make tests faster and avoid opening sockets:

- Suitable for testing service dispatch, stubs, interceptors, or gRPC logic at a lightweight integration level.
- Does not test TCP sockets, port binding, HTTP/2 network paths, or TLS handshakes like a real TCP server.
- Should not be used as the sole proof that the production server configuration can start and accept network connections.

A practical strategy is to use in-process for many fast tests and keep a group of TCP integration tests to verify server lifecycle, port binding, transport, and TLS where needed. The two types of tests answer different questions.

## 12. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Manually starting server in every **@BeforeEach** | Multiple servers or thread/port leaks | Let Spring lifecycle manage the server per context. |
| Using a fixed port | Parallel tests or other processes occupy the port | Use port 0 and read the actual port. |
| Creating a second test server when starter already runs one | Duplicate port binding or inconsistent service registration | Keep only one server owner in the context. |
| Shutting down the server from individual test methods | Other tests sharing the context encounter a shutdown server | Let Spring shut down the server when the context closes. |
| Not closing **ManagedChannel** | Keeps threads and connections alive after tests | Shutdown the channel in teardown. |
| Using **usePlaintext()** to conclude TLS is working | Skips TLS handshake/certificate validation | Create a dedicated TLS test with test certificates. |
| Probing a free port beforehand and then binding | Race condition with other processes | Let the server bind port 0 directly. |
| Assuming context cache resets all state | Tests depend on execution order | Reset business state or use a separate context when needed. |
| Using only in-process tests | Fails to verify TCP/HTTP2 server startup | Add real TCP integration tests. |

## 13. Hands-On Exercise

Create an integration test for the **Greeter** service in Spring Boot:

1. Declare the service implementation as a Spring bean.
2. Load the application context using **@SpringBootTest**.
3. Choose either a starter-managed server lifecycle or a **SmartLifecycle** fixture; do not run both for the same server.
4. Bind a dynamic port and retrieve the actual port after the server starts.
5. Create a **ManagedChannel**, a blocking stub, and a deadline.
6. Call a unary RPC, asserting both the response and error status.
7. Close the channel after each test; verify the server stops when the context is closed.
8. Run two test contexts in parallel and verify there are no port collisions.

**Completion criteria:** the server starts with the test context, the client connects over the dynamic port, the channel is closed at the proper time, and the server is stopped by Spring when the context closes.

## 14. Takeaways

- **@SpringBootTest** creates the context; the server should be managed by starter lifecycle or a Spring lifecycle bean.
- Spring starts lifecycle beans after bean creation and stops them when the context closes.
- Use port **0** to let the OS allocate a port; read the actual port after the server starts.
- Do not create a second server fixture if the starter already manages the server in the same context.
- The client **ManagedChannel** is the test's responsibility and requires explicit shutdown.
- Context caching can keep the server alive across multiple test methods; do not shut down a shared server from individual tests.
- In-process transport is fast but does not replace TCP/HTTP2 or TLS tests.
- Use deadlines and test isolation to keep integration tests stable in CI.

Starting the gRPC server with the proper lifecycle in the Spring test context allows integration tests to verify bean wiring, service registration, and real transport while avoiding port, thread, and resource conflicts across runs.
