# Testing blocking stubs

A blocking stub is a grpc-java client API for synchronous calls: the calling thread waits until it receives a response, receives an error status, or reaches the deadline. When testing Spring gRPC, blocking stubs are suitable for verifying unary RPCs and server-streaming RPCs sequentially with readable assertions. Tests must prove both business outcomes and synchronous behavior: correct responses, correct statuses, enforced deadlines, and released resources.

Generated blocking stubs are generated from the Protobuf service definition. They call the server over a ManagedChannel; therefore, an in-process channel can be used for fast tests without opening a TCP port. In-process tests still go through the gRPC call pipeline, though they do not verify TLS, HTTP/2 over sockets, ingress, or network policies.

## 1. How does a blocking stub work?

When calling a method on a blocking stub, the caller blocks until the RPC completes. For unary RPCs, the method returns a single response message. If the RPC ends with a status other than OK, grpc-java throws StatusRuntimeException. For server-streaming RPCs, the method returns an Iterator of responses; calling hasNext/next can wait for subsequent messages or stream completion.

```text
Test thread
    |
    | blockingStub.getOrder(request)
    v
ManagedChannel
    |
    v
gRPC server method
    |
    +---- onNext(response) + onCompleted()
    |
    v
Blocking stub returns response
    |
    v
JUnit assertions
```

Blocking stubs make tests linear, but the test thread must wait for network/call completion. Never use them on an event loop or a thread needed to handle other callbacks, to avoid deadlocks or thread-pool exhaustion.

## 2. Which RPCs have blocking stubs?

The generated Java API typically provides these stub types:

| Stub | Call style | Best suited for |
| --- | --- | --- |
| Blocking stub | Synchronous method returning response or iterator | Unary and server-streaming |
| Async stub | Receives results via StreamObserver callbacks | Unary and all streaming types |
| Future stub | Returns ListenableFuture for unary | Unary calls needing future composition |

Blocking stubs support unary and server-streaming RPCs. Client-streaming and bidirectional-streaming require sending multiple streamed requests; they are performed via async stubs with StreamObserver and have no corresponding methods in traditional blocking stubs.

Choose the stub matching the RPC contract. Do not force a client-streaming method into multiple unary calls if doing so alters semantics, ordering, or transaction boundaries.

## 3. Setting up an in-process server and channel

A test can generate a unique server name, register the service implementation, and connect a channel to that same name:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class GreeterBlockingStubTest {
    private Server server;
    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new GreeterService())
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow()
                .awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow()
                .awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

The server name must be fresh for each test to avoid connecting to the wrong fixture. Close the channel before the server and set finite timeouts for cleanup. If the server uses a test-created executor, shut down that executor during teardown after the server has stopped.

directExecutor() executes callbacks directly on the calling thread and is helpful for simple tests. It does not simulate production scheduling; tests covering executors, context propagation, or blocking handlers should use an appropriate executor with managed lifecycle.

## 4. Testing unary responses

Suppose the proto declares a unary method:

```proto
service Greeter {
  rpc SayHello(HelloRequest) returns (HelloReply);
}
```

The service returns a single response and completes:

```java
final class GreeterService extends GreeterGrpc.GreeterImplBase {
    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> observer) {
        HelloReply reply = HelloReply.newBuilder()
            .setMessage("Hello, " + request.getName())
            .build();
        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

The test calls the blocking stub and asserts response fields:

```java
@Test
void returnsGreeting() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("Mai")
        .build();

    HelloReply reply = stub.sayHello(request);

    assertEquals("Hello, Mai", reply.getMessage());
}
```

Do not just check that the method returns without throwing. Assertions should verify fields meaningful to the contract. If the service calls a repository or application service, check required side effects using an appropriate fake/mock or test database.

## 5. Testing error statuses

If the service rejects a request, the blocking stub throws StatusRuntimeException. Assert the status code to lock down the error contract:

```java
@Test
void rejectsBlankName() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName(" ")
        .build();

    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.sayHello(request));

    assertEquals(
        Status.Code.INVALID_ARGUMENT,
        error.getStatus().getCode());
}
```

Statuses that commonly need tests:

| Condition | Status |
| --- | --- |
| Invalid or missing request fields per validation | INVALID_ARGUMENT |
| Resource does not exist | NOT_FOUND |
| Missing or invalid credentials | UNAUTHENTICATED |
| Principal lacks permission | PERMISSION_DENIED |
| Dependency temporarily unavailable | UNAVAILABLE per error mapping |
| Call exceeds deadline | DEADLINE_EXCEEDED |

Assert descriptions or trailers only when they are part of the published contract. Avoid depending on internal exception messages because their wording can change without altering status semantics.

## 6. Setting deadlines on blocking calls

A blocking call should never wait indefinitely. Set a deadline on the stub:

```java
HelloReply reply = stub
    .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
    .sayHello(request);
```

withDeadlineAfter() returns a new stub configured for the call; the underlying channel continues to be reused. When the deadline expires before the RPC completes, the blocking call fails with a StatusRuntimeException whose code is DEADLINE_EXCEEDED.

Deadline tests should use a service whose completion time is controllable, such as via a CountDownLatch or test scheduler. Avoid fixed Thread.sleep() calls because CI scheduling and load differ from development machines. The server handler must run on a different executor from the client thread waiting for the call; if directExecutor is used and the handler blocks on the call thread, the test may not observe the deadline as expected.

A good deadline test verifies:

- The client receives DEADLINE_EXCEEDED within a bounded duration.
- Server work receives a cancellation signal if the implementation supports cancellation.
- No late out-of-contract side effects occur after the caller times out.
- Latches, executors, channels, and servers are all released when the test finishes.

## 7. Testing server-streaming with blocking stubs

With server-streaming RPCs, a single request can produce multiple responses. The blocking stub returns an Iterator:

```proto
service Greeter {
  rpc SayHelloMany(HelloRequest) returns (stream HelloReply);
}
```

Example test:

```java
@Test
void receivesAllServerStreamMessages() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("Mai")
        .build();

    Iterator<HelloReply> replies = stub.sayHelloMany(request);
    List<String> messages = new ArrayList<>();

    while (replies.hasNext()) {
        messages.add(replies.next().getMessage());
    }

    assertEquals(
        List.of("Hello, Mai", "Welcome, Mai", "Goodbye, Mai"),
        messages);
}
```

hasNext() and next() are blocking operations: they wait for the next response. The iterator terminates when the server closes the stream; if the stream terminates with an error, the next read throws StatusRuntimeException. Tests should verify count, order, and response content, and include a deadline to avoid hanging if the server forgets to call onCompleted().

Do not use blocking iterators for client-streaming or bidi-streaming; those two styles require async stubs to stream requests and receive responses.

## 8. Metadata and interceptors in blocking stub tests

Blocking stubs still pass through client interceptors and server interceptors. You can verify metadata sent and read on the server, such as a request ID or tenant:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ClientInterceptors;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

Metadata headers = new Metadata();
Metadata.Key<String> requestIdKey = Metadata.Key.of(
    "x-request-id",
    Metadata.ASCII_STRING_MARSHALLER);
headers.put(requestIdKey, "test-123");

ClientInterceptor requestIdInterceptor = new ClientInterceptor() {
    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {
            @Override
            public void start(Listener<RespT> responseListener,
                              Metadata requestHeaders) {
                requestHeaders.merge(headers);
                super.start(responseListener, requestHeaders);
            }
        };
    }
};

Channel interceptedChannel =
    ClientInterceptors.intercept(channel, requestIdInterceptor);
GreeterGrpc.GreeterBlockingStub testStub =
    GreeterGrpc.newBlockingStub(interceptedChannel);

HelloReply reply = testStub.sayHello(request);
```

The client interceptor attaches metadata to each call before sending. The server side uses an interceptor to read headers, verify the principal, or put the request ID into gRPC Context. In tests, a server interceptor can capture received values for assertions.

Tests should verify that metadata reaches the right call and does not leak across requests. Never store tenant, principal, or request ID in mutable fields of singleton stubs/services. Credentials must be verified before granting access; the mere presence of a header does not prove a valid identity.

## 9. Reusing channels, stubs, and concurrency testing

ManagedChannel is a long-lived resource capable of serving many concurrent RPCs. Never create a new channel per method call. Generated stubs are immutable; you can reuse a stub or derive a newly configured instance via withDeadlineAfter(), withInterceptors(), or similar configuration methods.

For concurrency tests:

- Share a channel across workers rather than creating one channel per request.
- Use independent requests and verify each response corresponds to its request.
- Use a bounded-size executor and shut it down after the test.
- Set a deadline on every call so failures do not hold workers forever.
- Never call a blocking stub from an event-loop thread or an executor with too few threads to process both calls and dependent callbacks.

If a test runs multiple blocking calls with only a single thread handling both callers and server handlers, artificial starvation/deadlock can occur. Configure separate executors for client workers and server handlers when testing concurrency.

## 10. Blocking stubs in Spring applications

In Spring applications, channels and stubs are typically configured as beans or created from a shared client factory. Tests can inject configured stubs to verify how the application uses the client, keeping these distinctions in mind:

- Service client logic tests using a test-built in-process channel.
- Spring context tests verifying beans, interceptors, credentials, and default deadlines are configured properly.
- TCP/TLS integration tests verifying targets, resolvers, certificates, HTTP/2, and networking.

Never call a blocking stub on a reactive event loop. If the service layer uses WebFlux/Reactor, offload blocking calls to boundedElastic or a bounded executor; prefer async stubs when the flow needs end-to-end non-blocking execution. With Spring MVC, remember each blocking call occupies a request thread for the duration of the wait.

## 11. Boundaries that require testing beyond in-process tests

| Verified by in-process blocking stub tests | Requires network integration tests |
| --- | --- |
| Unary responses and statuses | DNS, TCP sockets, and port mapping |
| Server-streaming iterator and message order | HTTP/2 negotiation, proxies, and ingress |
| Deadlines/cancellation in the gRPC call pipeline | TLS/mTLS handshakes and hostname verification |
| Client/server interceptors and metadata | Load balancers, service mesh, and network policies |
| Stub configuration and service method paths | Certificate rotation, reconnects, and connection failures |

The in-process transport does not test TLS or real byte transport. If the goal is verifying that the Spring gRPC server started by the starter exposes the right port, use a Spring Boot integration test with a real server or dynamic port. Never conclude production wiring is correct solely from a custom fixture built with InProcessServerBuilder.

## 12. Test matrix and practice exercise

| Group | Test case | PASS condition |
| --- | --- | --- |
| Unary success | Valid request | Blocking stub returns expected response |
| Validation | Invalid request | Status INVALID_ARGUMENT |
| Business error | Resource does not exist | Status NOT_FOUND |
| Authentication | Missing/invalid credentials | Status UNAUTHENTICATED |
| Authorization | Principal lacks permission | Status PERMISSION_DENIED |
| Deadline | Server fails to finish in time | Client receives DEADLINE_EXCEEDED |
| Server streaming | Multiple responses | Iterator yields in order and completes |
| Metadata | Request ID/tenant | Server receives the call's metadata |
| Concurrency | Multiple workers calling concurrently | No leaked request state |
| Cleanup | Test finishes | Channel/server/executor closed |
| Spring wiring | Stub bean configured | Interceptors/credentials/deadline correct |
| Transport | TLS/HTTP2/ingress | Real connection operates per config |

**Exercise:** OrderClient uses a generated OrderServiceBlockingStub to call GetOrder. The method requires a bearer token, has a 250 ms deadline, and returns NOT_FOUND when the order does not exist. A server-streaming method ListOrderEvents returns events in order.

1. Set up an in-process server/channel and create a blocking stub for testing.
2. Write a successful GetOrder test and verify all important fields.
3. Write a missing-order test verifying status NOT_FOUND.
4. Attach authorization metadata via an interceptor and verify requests without a token are rejected.
5. Test the 250 ms deadline using a service with controllable completion timing.
6. Use the Iterator to verify ListOrderEvents ordering and stream errors if any.
7. Run multiple concurrent blocking calls with a bounded executor and individual deadlines.
8. Write a Spring context test for the stub bean, then add TCP/TLS tests for transport.

**Self-check questions:**

- At what point does a blocking stub block the calling thread?
- How do blocking stubs support unary and server-streaming RPCs?
- Why do client-streaming and bidi-streaming use async stubs?
- When an RPC returns an error status, what exception type does a blocking stub throw?
- How does withDeadlineAfter() affect subsequent calls?
- Why can a server-streaming Iterator block on hasNext()?
- Why should you not create a ManagedChannel for every call?
- Can metadata and interceptors be tested using an in-process channel?
- Which properties require TCP/TLS integration tests?
- Why should blocking stubs not be called on a reactive event loop?

**Remember:** Test blocking stubs by invoking the generated synchronous API over a channel to a test server and checking responses, statuses, deadlines, or server-stream iterators. Reuse channels, set finite deadlines, and close resources after tests. In-process tests verify call behavior; Spring context tests verify bean wiring; TCP/TLS tests verify real transport and networking.
