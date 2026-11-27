# In-process gRPC server

**Chapter:** Testing basics  
**Scope:** Spring gRPC (SPRING_GRPC) using Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs. This lesson focuses on testing services with an in-process gRPC server: standing up a server and channel in the same JVM, calling the service via generated stubs, and verifying requests, responses, statuses, metadata, and streaming lifecycles without opening a TCP port.

## 1. What is an in-process server used to test?

Unit tests that call a service implementation method directly only verify the Java logic inside the handler. They skip an important part of gRPC: the generated client stub, method descriptors, call lifecycle, interceptor chain, and runtime dispatch of RPCs to the right service method.

The in-process transport lets you stand up a gRPC server and channel inside the same process. The client still calls the generated stub just like a real application, and the server still registers the generated service implementation. As a result, tests can verify:

- The generated stub invokes the right service method.
- Requests and responses travel through the gRPC call path.
- Unary and streaming RPCs complete with the proper lifecycle.
- gRPC statuses return the expected codes.
- Client/server interceptors are applied.
- Metadata and deadlines are propagated across the call.
- Cancellation and errors are observed on the client/server sides.

In-process tests run fast without fixed ports or sockets. They are well suited for testing adapters/services and runtime gRPC wiring.

## 2. In-process tests do not replace transport integration tests

The in-process transport does not open a TCP socket and does not run the Netty HTTP/2 transport used in production. Therefore, these tests do not prove:

- TLS handshakes, certificate chains, or hostname verification.
- Real HTTP/2 framing, flow control, and network backpressure.
- Netty event loops, channel pipelines, or socket timeouts.
- Infrastructure load balancing, DNS/service discovery, or retry behavior.
- Firewalls, proxies, ingress, or network policies.

Combine the test layers:

| Layer | Purpose |
| --- | --- |
| Unit test | Verify validators, mappers, and application logic |
| In-process gRPC test | Verify generated stubs, service registration, interceptors, statuses, and call lifecycle |
| Transport integration test | Verify Netty/TCP, TLS, HTTP/2, and real server configuration |
| End-to-end test | Verify flows across services in a near-production environment |

Never conclude that TLS or HTTP/2 works simply because a generated stub succeeds over an in-process channel.

## 3. Required dependencies

In the test source set, include the grpc-inprocess artifact matching your module's gRPC Java runtime version. Gradle example:

~~~kotlin
dependencies {
    testImplementation("io.grpc:grpc-inprocess")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
~~~

If the module uses a gRPC BOM or dependency platform, let the BOM manage the versions of grpc-inprocess, grpc-stub, grpc-core, and related artifacts. Avoid pinning separate versions manually, which can cause runtime and test transport mismatches.

Generated protobuf classes and generated gRPC stubs still come from the project's existing protobuf plugin/source set. Do not duplicate message classes in tests.

## 4. Setting up a minimal server and channel

Two main builders:

- InProcessServerBuilder.forName(serverName): creates a server bound to an internal name.
- InProcessChannelBuilder.forName(serverName): creates a client channel connecting to the server with the same name.

Generate a unique server name per test using InProcessServerBuilder.generateName() to prevent collisions between parallel tests.

~~~java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class OrderGrpcServiceTest {

    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void startServer() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new TestOrderGrpcService())
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void stopServer() throws Exception {
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
~~~

This example uses directExecutor() so callbacks execute directly on the calling thread, keeping synchronous tests simpler. This is fine for basic logic tests; it does not simulate production executor scheduling and concurrency. For tests involving cancellation, races, async callbacks, or thread isolation, use a dedicated executor and synchronize with latches/futures.

Always shut down the channel and server in teardown even when assertions fail. Never share the same server name across concurrent tests.

## 5. Registering a real service implementation

The generated service base is generated from the .proto file. The service implementation extends the base class and is registered on the server:

Suppose the service contract also declares the following streaming methods:

~~~proto
service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
  rpc WatchOrder(WatchOrderRequest) returns (stream OrderEvent);
  rpc UploadOrder(stream UploadChunk) returns (UploadSummary);
  rpc ControlOrder(stream OrderCommand) returns (stream OrderCommand);
}

message GetOrderRequest { string order_id = 1; }
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_CREATED = 1;
}
message GetOrderResponse {
  string order_id = 1;
  OrderStatus status = 2;
}
message WatchOrderRequest { string order_id = 1; }
message OrderEvent { string event_type = 1; }
message UploadChunk {
  int32 sequence = 1;
  string payload = 2;
}
message UploadSummary { int32 accepted_count = 1; }
message OrderCommand { string action = 1; }
~~~

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.ArrayList;
import java.util.List;

final class TestOrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {
        if (request.getOrderId().equals("missing")) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Order not found")
                            .asRuntimeException());
            return;
        }

        responseObserver.onNext(
                GetOrderResponse.newBuilder()
                        .setOrderId(request.getOrderId())
                        .setStatus(OrderStatus.ORDER_STATUS_CREATED)
                        .build());
        responseObserver.onCompleted();
    }

    @Override
    public void watchOrder(
            WatchOrderRequest request,
            StreamObserver<OrderEvent> responseObserver) {
        responseObserver.onNext(OrderEvent.newBuilder()
                .setEventType("ACCEPTED")
                .build());
        responseObserver.onNext(OrderEvent.newBuilder()
                .setEventType("PACKED")
                .build());
        responseObserver.onCompleted();
    }

    @Override
    public StreamObserver<UploadChunk> uploadOrder(
            StreamObserver<UploadSummary> responseObserver) {
        List<UploadChunk> chunks = new ArrayList<>();
        return new StreamObserver<>() {
            @Override
            public void onNext(UploadChunk chunk) {
                chunks.add(chunk);
            }

            @Override
            public void onError(Throwable error) {
                chunks.clear();
            }

            @Override
            public void onCompleted() {
                responseObserver.onNext(
                        UploadSummary.newBuilder()
                                .setAcceptedCount(chunks.size())
                                .build());
                responseObserver.onCompleted();
            }
        };
    }

    @Override
    public StreamObserver<OrderCommand> controlOrder(
            StreamObserver<OrderCommand> responseObserver) {
        return new StreamObserver<>() {
            @Override
            public void onNext(OrderCommand command) {
                responseObserver.onNext(command);
            }

            @Override
            public void onError(Throwable error) {
                responseObserver.onError(error);
            }

            @Override
            public void onCompleted() {
                responseObserver.onCompleted();
            }
        };
    }
}
~~~

This is a simple test service for illustration. In real adapter tests, you can register the production service implementation itself and mock the application use case behind it. That keeps validators, mappers, the adapter, and generated stubs real; only the application dependency is replaced with a mock.

## 6. Calling the generated blocking stub

After setting up the channel, create the generated stub just like a production client:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel);

GetOrderResponse response = stub.getOrder(
        GetOrderRequest.newBuilder()
                .setOrderId("order-42")
                .build());

assertEquals("order-42", response.getOrderId());
assertEquals(
        OrderStatus.ORDER_STATUS_CREATED,
        response.getStatus());
~~~

Blocking stubs suit unary RPCs in tests because the call either returns a response or throws StatusRuntimeException. Do not call the service method directly; the goal is to test the path through the generated stub and gRPC runtime.

## 7. Checking unary responses and error statuses

Tests can verify both success and error branches:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.Iterator;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

@Test
void returnsResponseForExistingOrder() {
    OrderServiceGrpc.OrderServiceBlockingStub stub =
            OrderServiceGrpc.newBlockingStub(channel);

    GetOrderResponse response = stub.getOrder(
            GetOrderRequest.newBuilder()
                    .setOrderId("order-42")
                    .build());

    assertEquals("order-42", response.getOrderId());
}

@Test
void exposesNotFoundStatusForMissingOrder() {
    OrderServiceGrpc.OrderServiceBlockingStub stub =
            OrderServiceGrpc.newBlockingStub(channel);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("missing")
                            .build()));

    assertEquals(
            Status.Code.NOT_FOUND,
            Status.fromThrowable(error).getCode());
}
~~~

On the client side, the status code is a more stable contract than the exception message. If the API uses rich error details such as google.rpc.BadRequest, unpack the detail and verify field violations in a dedicated test. Do not depend on error description strings if they are not part of the public contract.

## 8. Using asynchronous stubs and controlling callbacks

Async stubs take a StreamObserver to deliver results. Tests should use a latch and atomic references to await callbacks with a timeout:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

@Test
void asyncStubCompletesUnaryCall() throws Exception {
    OrderServiceGrpc.OrderServiceStub stub =
            OrderServiceGrpc.newStub(channel);
    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<GetOrderResponse> response =
            new AtomicReference<>();
    AtomicReference<Throwable> failure =
            new AtomicReference<>();

    stub.getOrder(
            GetOrderRequest.newBuilder()
                    .setOrderId("order-async")
                    .build(),
            new StreamObserver<>() {
                @Override
                public void onNext(GetOrderResponse value) {
                    response.set(value);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    terminal.countDown();
                }

                @Override
                public void onCompleted() {
                    terminal.countDown();
                }
            });

    assertTrue(terminal.await(5, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals("order-async", response.get().getOrderId());
}
~~~

Do not use Thread.sleep() to guess when callbacks complete. A timeout on await makes tests fail clearly instead of hanging indefinitely. If callbacks can deliver multiple responses, use a thread-safe collection or synchronization when recording them.

## 9. Testing server-streaming RPCs

For server-streaming, the generated blocking stub typically returns an Iterator<Response>. Tests can consume the entire stream and assert ordering:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.ArrayList;
import java.util.List;
import java.util.Iterator;
import org.junit.jupiter.api.Test;

@Test
void receivesServerStreamInOrder() {
    OrderServiceGrpc.OrderServiceBlockingStub stub =
            OrderServiceGrpc.newBlockingStub(channel);

    Iterator<OrderEvent> events = stub.watchOrder(
            WatchOrderRequest.newBuilder()
                    .setOrderId("order-42")
                    .build());

    List<OrderEvent> received = new ArrayList<>();
    events.forEachRemaining(received::add);

    assertEquals(2, received.size());
    assertEquals("ACCEPTED", received.get(0).getEventType());
    assertEquals("PACKED", received.get(1).getEventType());
}
~~~

When the iterator finishes normally, the stream has completed. If the server terminates with an error, iterating may throw StatusRuntimeException; tests should assert the status code just like unary tests.

## 10. Testing client-streaming RPCs

For client-streaming, the async stub returns an inbound StreamObserver<Request>. The client sends multiple messages and calls onCompleted(); the server returns one final response:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

@Test
void uploadsMultipleChunksAndReceivesSummary() throws Exception {
    OrderServiceGrpc.OrderServiceStub stub =
            OrderServiceGrpc.newStub(channel);
    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<UploadSummary> summary = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<UploadChunk> requestObserver = stub.uploadOrder(
            new StreamObserver<>() {
                @Override
                public void onNext(UploadSummary value) {
                    summary.set(value);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    terminal.countDown();
                }

                @Override
                public void onCompleted() {
                    terminal.countDown();
                }
            });

    requestObserver.onNext(UploadChunk.newBuilder()
            .setSequence(1)
            .setPayload("first")
            .build());
    requestObserver.onNext(UploadChunk.newBuilder()
            .setSequence(2)
            .setPayload("second")
            .build());
    requestObserver.onCompleted();

    assertTrue(terminal.await(5, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(2, summary.get().getAcceptedCount());
}
~~~

Do not call onCompleted() before sending all requests. After a terminal signal, do not send more onNext() calls. If a test needs to verify client cancellation, call cancel on the call handle or abort the stream through the appropriate mechanism instead of sending messages after completion.

## 11. Testing bidirectional streaming

For bidirectional streaming, the client sends and receives messages independently within the same RPC. Tests should drive the request flow, await responses based on conditions, and terminate the lifecycle properly:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

@Test
void exchangesMessagesInBidirectionalStream() throws Exception {
    OrderServiceGrpc.OrderServiceStub stub =
            OrderServiceGrpc.newStub(channel);
    CountDownLatch terminal = new CountDownLatch(1);
    List<OrderCommand> responses =
            new CopyOnWriteArrayList<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<OrderCommand> requests = stub.controlOrder(
            new StreamObserver<>() {
                @Override
                public void onNext(OrderCommand value) {
                    responses.add(value);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    terminal.countDown();
                }

                @Override
                public void onCompleted() {
                    terminal.countDown();
                }
            });

    requests.onNext(OrderCommand.newBuilder()
            .setAction("PAUSE")
            .build());
    requests.onNext(OrderCommand.newBuilder()
            .setAction("RESUME")
            .build());
    requests.onCompleted();

    assertTrue(terminal.await(5, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(2, responses.size());
}
~~~

This example assumes the server returns one response per command and completes when the client closes the request direction. If the protocol allows the server to keep emitting after the client finishes sending, tests should drive response termination according to the service's semantics.

## 12. Testing metadata with interceptors

In-process channels support client interceptors and server interceptors. You can verify metadata sent across a call without opening sockets:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Channel;
import io.grpc.ClientInterceptor;
import io.grpc.ClientInterceptors;
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.MetadataUtils;
import java.util.concurrent.atomic.AtomicReference;

private static final Metadata.Key<String> TENANT_KEY =
        Metadata.Key.of(
                "x-tenant-id",
                Metadata.ASCII_STRING_MARSHALLER);
private static final Context.Key<String> TENANT_CONTEXT_KEY =
        Context.key("tenant-id");

final class TenantCaptureInterceptor implements ServerInterceptor {
    private final AtomicReference<String> capturedTenant =
            new AtomicReference<>();

    String capturedTenant() {
        return capturedTenant.get();
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        String tenant = headers.get(TENANT_KEY);
        capturedTenant.set(tenant);
        Context context = Context.current()
                .withValue(TENANT_CONTEXT_KEY, tenant);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Registering the interceptor on the server builder:

~~~java
TenantCaptureInterceptor tenantCapture = new TenantCaptureInterceptor();
server = InProcessServerBuilder.forName(serverName)
        .directExecutor()
        .intercept(tenantCapture)
        .addService(service)
        .build()
        .start();
~~~

The client can attach metadata through a client interceptor:

In the same fixture, use the exact tenantCapture instance registered on the server builder and the channel connected to that server:

~~~java
Metadata headers = new Metadata();
headers.put(TENANT_KEY, "tenant-test");

ClientInterceptor tenantHeader = MetadataUtils
        .newAttachHeadersInterceptor(headers);
Channel tenantChannel = ClientInterceptors.intercept(
        channel,
        tenantHeader);
OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(tenantChannel);

stub.getOrder(GetOrderRequest.newBuilder()
        .setOrderId("order-42")
        .build());
assertEquals("tenant-test", tenantCapture.capturedTenant());
~~~

Tests can verify that the service reads the tenant context or that the interceptor records the expected header. Metadata is just input data; never treat a client-supplied tenant ID as proof of authorization. Production code must authenticate the caller and enforce tenant access via security policies.

## 13. Deadlines and cancellation

Deadlines are attached to stubs using withDeadlineAfter. For stable tests, use a service fixture that schedules a response past the deadline instead of relying on Thread.sleep():

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

final class DelayedOrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase
        implements AutoCloseable {

    private final ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> observer) {
        scheduler.schedule(() -> {
            observer.onNext(GetOrderResponse.newBuilder()
                    .setOrderId(request.getOrderId())
                    .build());
            observer.onCompleted();
        }, 5, TimeUnit.SECONDS);
    }

    @Override
    public void close() {
        scheduler.shutdownNow();
    }
}

@Test
void deadlineExpiresBeforeScheduledResponse() throws Exception {
    String name = InProcessServerBuilder.generateName();
    DelayedOrderGrpcService delayedService =
            new DelayedOrderGrpcService();
    Server delayedServer = InProcessServerBuilder.forName(name)
            .addService(delayedService)
            .build()
            .start();
    ManagedChannel delayedChannel =
            InProcessChannelBuilder.forName(name).build();

    try {
        OrderServiceGrpc.OrderServiceBlockingStub stub =
                OrderServiceGrpc.newBlockingStub(delayedChannel)
                        .withDeadlineAfter(1, TimeUnit.SECONDS);
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getOrder(GetOrderRequest.newBuilder()
                        .setOrderId("slow-order")
                        .build()));

        assertEquals(
                Status.Code.DEADLINE_EXCEEDED,
                Status.fromThrowable(error).getCode());
    } finally {
        delayedChannel.shutdownNow();
        delayedServer.shutdownNow();
        delayedService.close();
    }
}
~~~

The fixture schedules the response five seconds out while the client sets a one-second deadline. The test does not wait for the late response; teardown cancels the scheduler after asserting the status. Still, leave enough margin for CI scheduling jitter and close the channel/server/scheduler on every path.

Deadlines/cancellations cancel the RPC on the client side, but they do not automatically interrupt every blocking operation in application code. Handlers and downstream clients must propagate cancellation/deadlines, check cancellation where appropriate, and release resources. Tests should verify that the server stops emitting responses after terminal cancellation.

## 14. Using a Spring service bean in an in-process server

In a Spring gRPC application, the service implementation is usually a Spring bean registered via annotations or a starter. You can retrieve the Spring-initialized bean and register it with the in-process server:

~~~java
OrderGrpcService service =
        applicationContext.getBean(OrderGrpcService.class);

Server server = InProcessServerBuilder.forName(serverName)
        .directExecutor()
        .addService(service)
        .build()
        .start();
~~~

This tests the real adapter together with its Spring-injected dependencies. Configure the test context so it does not accidentally start an extra network gRPC server if the goal is solely an in-process test; the mechanism for disabling server auto-configuration depends on your starter and project version.

If the test does not require Spring wiring, instantiate the service directly via its constructor and pass a mocked application use case. That approach is usually faster and makes failures easier to localize. Use a Spring context when bean wiring itself is part of what is being tested.

## 15. Interceptor chains and registration order

An in-process server/channel can register multiple interceptors. This is useful for testing:

- Authentication/authorization interceptors rejecting calls before reaching the handler.
- Tracing interceptors creating spans and propagating context.
- Logging/metrics interceptors recording statuses and latency.
- Metadata interceptors copying call metadata into gRPC Context.

Interceptor order can affect what downstream interceptors observe. Tests should mirror the application's chain configuration and verify critical behavior; never infer production ordering from a test builder configured differently.

Never include secrets or raw authorization metadata in assertion outputs or logs. For auth tests, use dummy tokens and assert statuses like UNAUTHENTICATED or PERMISSION_DENIED.

## 16. Executors and test determinism

directExecutor() runs callbacks directly on the thread making the call, which suits simple tests and reduces nondeterminism. However, it can hide:

- Races between callbacks and cancellation.
- Bugs from sharing mutable state across threads.
- Deadlocks caused by code accidentally blocking an event/callback thread.
- Errors propagating gRPC/OpenTelemetry/Security context across executors.

For concurrency-related behavior, drop directExecutor() and use an explicit executor or runtime defaults. Synchronize tests using CountDownLatch, CompletableFuture, or bounded-timeout conditions. Never busy-wait in a loop and never use Thread.sleep() as your primary synchronization mechanism.

## 17. Cleanup and resource management

Every test must close:

- ManagedChannel: stop accepting new calls, cancel remaining calls if the test needs fast shutdown, and await termination.
- Server: shut down the server and await termination.
- Custom executors created by the test: shut down and await termination.
- Open schedulers/futures or streams: cancel/close them so no threads outlive the test.

In teardown, use try/finally or JUnit @AfterEach to clean up even if assertions fail. Do not share a channel across tests if tests mutate interceptors, deadlines, or stream state.

## 18. In-process gRPC server test matrix

| Scenario | What to verify |
| --- | --- |
| Unary success | Generated blocking stub receives expected response |
| Unary error | Client receives expected gRPC status code |
| Async unary | Callback completes within timeout with no error |
| Server streaming | Receives all messages in order and terminal event |
| Client streaming | Sends multiple requests, receives summary after completion |
| Bidirectional streaming | Bidirectional exchange per protocol |
| Metadata | Client interceptor sends header, server interceptor reads it |
| Deadline | Call exceeding budget receives DEADLINE_EXCEEDED |
| Cancellation | Call terminates cleanly, no responses emitted after cancel |
| Authentication | Interceptor returns UNAUTHENTICATED/PERMISSION_DENIED |
| Spring wiring | Real service bean is registered and callable |
| Cleanup | Channel/server/executor terminate with no leaked threads |

Not every service has all four RPC types. Select cases matching the actual contract and test each risky behavior.

## 19. Common mistakes

- **Using a fixed port:** parallel tests can collide; use a generated server name.
- **Forgetting to shut down channel/server:** leaves threads behind and hangs the test suite.
- **Mocking the generated stub:** bypasses the gRPC runtime; create a real stub from the in-process channel.
- **Calling the service method directly and calling it an in-process test:** does not go through the stub/channel.
- **Using directExecutor for every test:** hides concurrency issues.
- **Using sleep to wait for callbacks:** creates flaky tests; use latches/futures with timeouts.
- **Concluding TLS works:** the in-process transport does not perform TLS handshakes.
- **Not checking status codes:** tests see only that the call failed without verifying the error contract.
- **Not terminating streaming observers:** tests hang or leak resources.
- **Trusting client-sent tenant metadata:** metadata does not replace authorization.

## 20. Self-practice

1. Why is an in-process server more useful than calling service methods directly when testing generated stubs?
2. What problem does InProcessServerBuilder.generateName() solve?
3. Why does directExecutor() work for simple tests yet fail to fully represent production concurrency?
4. Design a test verifying that server-streaming receives all messages and finishes cleanly.
5. How do you verify that a client interceptor sends metadata that a server interceptor can read?
6. Does an in-process test prove that TLS and HTTP/2 framing work? Why or why not?
7. When using a real Spring bean in an in-process server, what should you watch out for with starter auto-configuration?

**Remember:** An in-process gRPC server lets you invoke generated stubs against a server and channel in the same JVM to test service registration, unary/streaming lifecycles, statuses, metadata, interceptors, deadlines, and cancellation without opening a TCP port. Use unique server names, clean up channels and servers thoroughly, and use directExecutor only where appropriate. Add separate transport integration tests for Netty, HTTP/2, TLS, and network behavior.
