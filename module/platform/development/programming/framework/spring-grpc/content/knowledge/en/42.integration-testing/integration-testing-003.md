# Testing Multiple Services on the Same Server

## Learning Objectives

After this lesson, you will be able to:

- Explain how a gRPC server registers and routes multiple services on the same endpoint.
- Declare multiple Protobuf services with distinct full names and implement them as Spring beans.
- Start a test server containing multiple BindableService instances.
- Create one ManagedChannel and multiple generated stubs to call each service.
- Verify service routing, independent status handling, interceptors, and shared state.
- Manage lifecycle, dynamic ports, and test isolation when multiple services run together.

## 1. Multiple Services Can Share One gRPC Server

A gRPC server is not required to register only one service. A server can expose multiple service definitions on the same host and port. Each service is identified by its full name in Protobuf, consisting of the package and service name; methods are routed by their full method name.

For example, the same server can provide:

- **demo.v1.GreetingService** to handle greetings.
- **demo.v1.CatalogService** to look up products.
- **demo.v1.OrderService** to manage orders.

The client creates a separate stub for each service but can share a single ManagedChannel because all services reside on the same endpoint. gRPC routes requests to the corresponding handler based on the method descriptor.

In **SPRING_GRPC**, service implementations are typically Spring beans so they can share repositories, configuration, interceptors, and business services. Integration tests need to verify that all expected services are registered on the same server and are callable over real transport.

## 2. Defining Services in Protobuf

Example of two independent services in the same package:

~~~proto
syntax = "proto3";

package demo.v1;

option java_package = "com.example.grpc.generated";
option java_multiple_files = true;

message GreetRequest {
  string name = 1;
}

message GreetReply {
  string message = 1;
}

message FindItemRequest {
  string item_id = 1;
}

message FindItemReply {
  string item_id = 1;
  string description = 2;
}

service GreetingService {
  rpc Greet(GreetRequest) returns (GreetReply);
}

service CatalogService {
  rpc FindItem(FindItemRequest) returns (FindItemReply);
}
~~~

Code generation produces separate base classes and stubs, such as **GreetingServiceGrpc** and **CatalogServiceGrpc**. The two services share a package but have distinct full service names, allowing the server to route each RPC accurately.

Do not arbitrarily rename packages or services between already-published clients and servers. The full service and method names are part of the RPC path; changing them prevents older clients from calling those methods.

## 3. Each Service Is a Separate BindableService

Generated server-side base classes implement BindableService. Each service implementation extends its corresponding base class:

~~~java
final class GreetingServiceImpl
        extends GreetingServiceGrpc.GreetingServiceImplBase {

    @Override
    public void greet(
            GreetRequest request,
            StreamObserver<GreetReply> responseObserver) {
        GreetReply reply = GreetReply.newBuilder()
            .setMessage("Hello, " + request.getName())
            .build();

        responseObserver.onNext(reply);
        responseObserver.onCompleted();
    }
}
~~~

The second service implements CatalogServiceGrpc.CatalogServiceImplBase:

~~~java
final class CatalogServiceImpl
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void findItem(
            FindItemRequest request,
            StreamObserver<FindItemReply> responseObserver) {
        if (!"item-1".equals(request.getItemId())) {
            responseObserver.onError(
                Status.NOT_FOUND
                    .withDescription("Item not found")
                    .asRuntimeException());
            return;
        }

        responseObserver.onNext(
            FindItemReply.newBuilder()
                .setItemId("item-1")
                .setDescription("Keyboard")
                .build());
        responseObserver.onCompleted();
    }
}
~~~

The two implementations are independent service handlers. Each method is responsible for emitting exactly one terminal event to the response observer for that call.

## 4. Registering Multiple Services on the Same Server

In plain gRPC Java, ServerBuilder accepts multiple addService(...) calls before build:

~~~java
Server server = ServerBuilder.forPort(0)
    .addService(greetingService)
    .addService(catalogService)
    .build()
    .start();
~~~

The server binds only one port while registering both services. When a client calls GreetingService/Greet, gRPC dispatches to GreetingServiceImpl; when it calls CatalogService/FindItem, the request is routed to CatalogServiceImpl.

In Spring, let component scanning or configuration create each implementation as a bean. If the starter automatically discovers and registers service beans, do not call addService again on a manual server. Keep a single server owner and one consistent registration mechanism.

## 5. A Test Fixture Containing Multiple Services

When not using a starter that auto-starts the server, you can create a Spring lifecycle-managed fixture that accepts a list of services:

~~~java
final class MultiServiceGrpcServer implements SmartLifecycle {
    private final List<BindableService> services;
    private volatile Server server;

    MultiServiceGrpcServer(List<BindableService> services) {
        this.services = List.copyOf(services);
    }

    @Override
    public synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }

        ServerBuilder<?> builder = ServerBuilder.forPort(0);
        services.forEach(builder::addService);

        try {
            server = builder.build().start();
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot start multi-service gRPC test server", ex);
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

The fixture binds port 0 so the OS allocates a dynamic port. port() only returns a value after the server has started. stop() shuts down the server gracefully, waits for a bounded timeout, and then forces shutdown if necessary.

This is a self-managed test server fixture. If the Spring gRPC starter already manages the server, register both service beans with that server and retrieve the port from the starter's API/test support. Do not combine auto-configuration with a second fixture containing the same services.

## 6. Registering Service Beans in the Spring Test Context

The test configuration can construct the server from two concrete service beans:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class MultiServiceGrpcTestConfiguration {
    @Bean
    MultiServiceGrpcServer multiServiceGrpcServer(
            GreetingServiceImpl greeting,
            CatalogServiceImpl catalog) {
        return new MultiServiceGrpcServer(
            List.of(greeting, catalog));
    }
}
~~~

In a real application, implementations are usually created by component scanning or production configuration. The test only needs to import the fixture configuration and let Spring inject the proper beans. Using concrete parameter types avoids ambiguity when the context contains multiple BindableService beans.

Do not register the same service definition twice. Services must have distinct full names; if two implementations compete for the same full service name, the server configuration becomes ambiguous and startup may fail.

## 7. One Channel, Multiple Stubs

After the Spring context has started the server, the test creates one channel to the server's port and then creates stubs for each service:

~~~java
@SpringBootTest
@Import(MultiServiceGrpcTestConfiguration.class)
class MultiServiceIntegrationTest {
    @Autowired
    MultiServiceGrpcServer grpcServer;

    private ManagedChannel channel;
    private GreetingServiceGrpc.GreetingServiceBlockingStub greetingStub;
    private CatalogServiceGrpc.CatalogServiceBlockingStub catalogStub;

    @BeforeEach
    void connect() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcServer.port())
            .usePlaintext()
            .build();

        greetingStub =
            GreetingServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);
        catalogStub =
            CatalogServiceGrpc.newBlockingStub(channel)
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

One ManagedChannel can serve multiple stubs and multiple concurrent RPCs. Stubs hold method/service descriptors; the channel manages the connection to the endpoint. There is no need to open a new channel for each service if they reside on the same server.

## 8. Verifying Both Services Over the Same Endpoint

Tests should call at least one method on each service:

~~~java
@Test
void routesCallsToBothServicesOnTheSameServer() {
    GreetReply greeting = greetingStub.greet(
        GreetRequest.newBuilder()
            .setName("An")
            .build());

    FindItemReply item = catalogStub.findItem(
        FindItemRequest.newBuilder()
            .setItemId("item-1")
            .build());

    assertEquals("Hello, An", greeting.getMessage());
    assertEquals("Keyboard", item.getDescription());
}
~~~

Such a test confirms that the client uses the same channel while requests are dispatched to the two respective service handlers. Only checking that the server started or the channel connected is not enough to prove that every service is registered.

Assertions should check meaningful business return data to catch cases where a stub points to the wrong service or an implementation was not injected with the right dependencies.

## 9. Errors in One Service Must Not Break Another Service

Each RPC has its own status. For example, Catalog can return NOT_FOUND while Greeting continues working:

~~~java
@Test
void failureInOneServiceDoesNotStopTheOtherService() {
    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> catalogStub.findItem(
            FindItemRequest.newBuilder()
                .setItemId("missing")
                .build()));

    assertEquals(Status.Code.NOT_FOUND,
        error.getStatus().getCode());

    GreetReply reply = greetingStub.greet(
        GreetRequest.newBuilder()
            .setName("Binh")
            .build());

    assertEquals("Hello, Binh", reply.getMessage());
}
~~~

A business error in one method does not automatically shut down the entire server. However, if one service exhausts a shared executor, heap, or connection pool, other services can still be affected. Load or fault-injection integration tests can verify these shared resource limits.

## 10. Interceptors and Metadata Across Multiple Services

A server can apply interceptors at the server or service scope depending on the API and starter in use. When multiple services exist, verify explicitly:

- Does authentication/authorization apply to every protected service?
- Is metadata such as trace ID and correlation ID read consistently?
- Do server-wide interceptors alter statuses or deadlines unexpectedly?
- Do public services and internal services require different policies?

Tests should call each service with both valid and invalid metadata to verify the policy. Do not assume that because one service is protected, another service automatically receives the same interceptor if the registration configuration does not guarantee it.

If the starter registers service beans automatically, check the interceptor attachment mechanism supported by the starter. Do not add interceptors by creating a second server just for tests.

## 11. Isolating State Between Services

Services on the same server may share dependencies like repositories, caches, or executors, but should not accidentally share per-request mutable state.

- Spring singleton service implementations must be safe when multiple RPCs execute concurrently.
- State for a call should live in objects scoped to that call.
- Greeting test data should not affect Catalog results unless that is an explicitly designed integration behavior.
- If multiple services write to the database, tests should use namespaced data or appropriate transaction/test fixtures.

Running two services on the same server does not mean they run sequentially. gRPC can process many calls concurrently; shared dependencies need proper concurrency semantics.

## 12. Testing Multiple Services Concurrently

In addition to sequential calls, verify that two services can handle concurrent calls over the same channel:

~~~java
CompletableFuture<GreetReply> greetingCall =
    CompletableFuture.supplyAsync(() ->
        greetingStub.greet(
            GreetRequest.newBuilder().setName("Concurrent").build()));

CompletableFuture<FindItemReply> catalogCall =
    CompletableFuture.supplyAsync(() ->
        catalogStub.findItem(
            FindItemRequest.newBuilder().setItemId("item-1").build()));

assertEquals("Hello, Concurrent", greetingCall.get(3, TimeUnit.SECONDS)
    .getMessage());
assertEquals("Keyboard", catalogCall.get(3, TimeUnit.SECONDS)
    .getDescription());
~~~

In real tests, use a bounded test executor and clean it up after execution. Set timeouts on both futures and RPCs so failures do not hang the suite. If services share state or resources, add tests confirming there are no race conditions or data leaks between the two methods.

## 13. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Starting one server per service | Multiple ports and a configuration that does not reflect the target topology | Register multiple BindableService beans on the same server. |
| Calling only one service in tests | Remaining services may not be registered | Call methods of each service over a real channel. |
| Creating a separate channel per stub | Unnecessary connections and threads | Share one channel for the same endpoint. |
| Registering duplicate service definitions | Ambiguous server registry or startup failure | Use unique full service names and a single registration owner. |
| Testing only successful service routing | Misses status handling, interceptors, and policies | Test both errors and metadata on every service. |
| Assuming one RPC error stops the server | Incorrect retry/health handling | Distinguish call status from server lifecycle. |
| Sharing unsynchronized mutable state | Race conditions across RPCs belonging to different services | Protect shared dependencies and isolate call state. |
| Combining auto-registration with manual addService | Duplicate registration or two servers | Choose a single server lifecycle/registration owner. |

## 14. Hands-On Exercise

Create a Spring gRPC server with two services:

1. Define GreetingService and CatalogService in Protobuf with distinct full service names.
2. Create two Spring bean implementations.
3. Register both on the same server, using a dynamic port in tests.
4. Create one ManagedChannel and two generated blocking stubs.
5. Call a successful method on each service and verify the responses.
6. Call Catalog with a nonexistent ID, assert NOT_FOUND, then call Greeting successfully on the same channel.
7. Call both services concurrently to verify shared dependencies and concurrency.
8. Verify interceptors/metadata apply properly to both services.

**Completion criteria:** both services are dispatched through the same server/port, the client shares one channel, each RPC's status is independent, and Spring properly manages the lifecycle of both the server and service beans.

## 15. Takeaways

- A gRPC server can register multiple BindableService implementations on the same endpoint.
- Full service names in Protobuf enable gRPC to route requests to the right service/method.
- Each service has its own generated base class and stub; multiple stubs can share one ManagedChannel.
- Integration tests must call each service through a real server to verify registration and routing.
- An error in one RPC does not automatically stop the server or other services.
- Verify interceptors, metadata, and authorization on each service.
- Spring singleton service beans and shared dependencies must be safe when multiple RPCs run concurrently.
- Keep a single owner for server lifecycle and registration; avoid duplicating auto-registration with a manual fixture.

Testing multiple services on the same server verifies realistic gRPC topology, service routing, independent status handling, and how Spring manages implementations sharing one endpoint.
