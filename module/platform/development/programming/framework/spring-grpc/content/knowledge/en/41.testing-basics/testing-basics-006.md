# In-process channel for testing

An in-process channel is a ManagedChannel that connects a client stub to a test gRPC server in the same JVM by identifier name. It allows tests to call generated stubs through gRPC method dispatch without opening a TCP port, resolving DNS, or establishing sockets. Tests still go through the gRPC client/server APIs, without starting a real network transport.

In Spring gRPC, an in-process channel is useful for testing service implementations, request validation, responses, status mapping, interceptors, and deadlines at the call level. The focus is creating a channel pointing to the right server name, using the channel with generated stubs, and closing it properly in the lifecycle. To verify TLS, HTTP/2, proxies, sockets, or actual Spring starter wiring, integration tests over a real transport are still required.

## 1. How does an in-process channel connect to a test server?

A test generates a unique server name, registers the service implementation, starts the server, and creates a channel pointing to that exact name:

```text
JUnit test
   |
   | generate in-process server name
   v
InProcessServerBuilder
   | addService(...)
   | build().start()
   v
In-process gRPC server
   ^
   | InProcessChannelBuilder.forName(serverName)
   |
Generated client stub
   |
   | unary request
   v
Service implementation
   |
   | response or gRPC status
   v
Test assertions
```

The server and channel communicate via the in-process transport without sockets. The client still invokes the service through the generated stub and gRPC method dispatch, so tests can verify method paths, request/response types, statuses, and interceptors attached to the server.

A new server name must be created for each fixture/test so two tests do not accidentally connect to the wrong server. When the fixture finishes, close the channel and server so executors, callbacks, or resources are not retained across tests.

## 2. Preparing test dependencies

Add the in-process artifact with a version synchronized with the rest of the grpc-java libraries. Gradle Kotlin DSL example:

```kotlin
dependencies {
    testImplementation("io.grpc:grpc-inprocess:$grpcVersion")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
```

If the project manages versions with a gRPC BOM or version catalog, use that same version source instead of declaring a different grpc-inprocess version. Generated classes such as `GreeterGrpc`, `HelloRequest`, and `HelloReply` must be generated from proto during the application build.

Tests do not need to add TCP transport dependencies just to run an in-process server. If a test uses a Spring Boot test context, keep Spring test dependencies according to the project configuration.

## 3. Writing a small service implementation for testing

Example service with a unary method that takes a name and returns a greeting. Blank input is mapped to status `INVALID_ARGUMENT`:

```java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

final class GreeterService extends GreeterGrpc.GreeterImplBase {

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> observer) {

        String name = request.getName().trim();
        if (name.isEmpty()) {
            observer.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("name is required")
                    .asRuntimeException());
            return;
        }

        HelloReply reply = HelloReply.newBuilder()
            .setMessage("Hello, " + name)
            .build();
        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

For unary RPCs, the server sends exactly one response and completes the stream with `onCompleted()`. On error, the server calls `onError()` and sends no further responses. Never call both terminal branches for the same call.

In a real service, business logic should call injected application services/repositories. Unit tests for business rules can be tested separately; in-process tests verify the integration between the gRPC method and that logic.

## 4. Setting up the server/channel in JUnit 5

Use `@BeforeEach` to set up the server and channel, and `@AfterEach` to close them:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class GreeterServiceTest {
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

`directExecutor()` makes callbacks run directly on the calling thread in simple tests, making execution order easy to observe. It does not simulate production executors. If the application depends on asynchronous executors, context propagation, or scheduling, add tests with an appropriate executor.

Always close the channel first, then the server. Use a finite timeout on `awaitTermination` so tests do not hang indefinitely if shutdown fails. If test fixture initialization fails midway, cleanup still needs null checks as shown in the example.

## 5. Testing responses and request validation

Success tests should verify response content, not just that the call does not throw an exception:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

@Test
void returnsGreetingForValidName() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("Linh")
        .build();

    HelloReply reply = stub
        .withDeadlineAfter(1, TimeUnit.SECONDS)
        .sayHello(request);

    assertEquals("Hello, Linh", reply.getMessage());
}
```

Error tests check the status code and important side effects:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.Status;
import io.grpc.StatusRuntimeException;

@Test
void rejectsBlankName() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("   ")
        .build();

    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.sayHello(request));

    assertEquals(
        Status.Code.INVALID_ARGUMENT,
        error.getStatus().getCode());
}
```

Do not assert the entire description if it is not part of the public contract. Prioritize status codes, response fields, and necessary side effects. If the handler calls a repository, use an appropriate fake/mock or test database to verify data is only written when the request is valid.

## 6. Testing interceptors and Context

An in-process server can register services via `ServerInterceptors.intercept(...)` to verify that interceptors run before the handler:

```java
ServerServiceDefinition intercepted =
    ServerInterceptors.intercept(
        new GreeterService().bindService(),
        new RequestIdServerInterceptor());

server = InProcessServerBuilder.forName(serverName)
    .directExecutor()
    .addService(intercepted)
    .build()
    .start();
```

An interceptor test should verify:

- Inbound metadata is read correctly.
- The principal or request ID is placed into the gRPC Context.
- The handler receives the expected context value.
- Invalid requests are rejected before the business handler runs.
- The interceptor does not alter responses/statuses outside the contract.

If the interceptor is a Spring bean, the standalone test above only checks the interceptor implementation and service wrapping. A separate Spring integration test is needed to verify the bean is injected and registered on the starter-managed server.

## 7. Deadlines, cancellation, and status

Client stubs allow setting a deadline per call:

```java
HelloReply reply = stub
    .withDeadlineAfter(200, TimeUnit.MILLISECONDS)
    .sayHello(request);
```

A deadline test needs a test service that can delay its response using a controllable latch or scheduler. Avoid arbitrary sleeps because CI scheduling jitter can make tests flaky. Verify that the client receives DEADLINE_EXCEEDED and that the service stops work if the implementation supports cancellation.

Statuses that typically warrant dedicated tests:

| Scenario | Status to verify |
| --- | --- |
| Invalid or missing request data | INVALID_ARGUMENT |
| Resource does not exist | NOT_FOUND |
| Unauthenticated caller | UNAUTHENTICATED |
| Caller lacks permission | PERMISSION_DENIED |
| Dependency temporarily unavailable | UNAVAILABLE per contract |
| Deadline expired | DEADLINE_EXCEEDED |
| Unexpected error | INTERNAL or defined mapping |

Statuses must be stable and semantically appropriate. Never turn every exception into INTERNAL if the application can map known business errors to specific statuses.

## 8. Testing isolation and concurrency

Each test should have its own server name and fixture. Do not share a mutable service singleton across multiple tests if it stores request state. If a fake dependency must be shared, reset its state before each test and avoid running tests in parallel against the same fixture.

For stateless services, you can execute multiple concurrent calls with an executor and assert each response matches its request. If a handler stores the principal, tenant, or correlation ID in a mutable field, concurrency tests can catch data leaking from one call to another.

Never store request data in fields of a singleton service. Use local variables in the handler or gRPC Context for per-call data. If you need to verify how many times a handler was invoked, use a thread-safe counter like AtomicInteger.

## 9. In-process tests do not replace TCP/TLS integration tests

The in-process transport enables fast testing of gRPC dispatch and lifecycle, but does not fully verify components that depend on real transport:

| Suitable for in-process tests | Requires transport integration tests |
| --- | --- |
| Request/response and status mapping | TCP sockets, port binding, and DNS |
| Method dispatch and service registration in fixtures | HTTP/2 negotiation and framing over the network |
| Interceptors, metadata, and Context on the call path | TLS handshakes, certificate chains, and hostname verification |
| Deadlines/cancellation in gRPC logic | Proxies, ingress, service mesh, and load balancers |
| Many fast, isolated logic tests | Network timeouts, connection resets, and reconnects |

The in-process transport does not prove byte serialization, TLS, HTTP/2, or proxies behave like production. If the goal is verifying wire compatibility, message sizes, certificates, or routing, invoke the server over a real transport.

## 10. Testing Spring gRPC wiring

A test creating its own InProcessServerBuilder does not prove Spring registered the service bean properly. To test Spring wiring:

1. Use a test context with the same starter/configuration the application deploys.
2. Register service implementations and interceptors as in production.
3. Obtain channels/stubs from the application's client configuration or connect to the test port opened by the Spring server.
4. Invoke a unary RPC and verify response/status.
5. Verify interceptors, dependency injection, and shutdown lifecycle.

Property names and extension points for selecting an in-process transport or dynamic port depend on the Spring gRPC starter version. Never copy a property unsupported by the current starter; use the existing test configuration in the application and verify the actual endpoint the context starts.

Keep in-process tests for service behavior and Spring context tests for wiring. An end-to-end test over TCP/TLS should cover boundaries that in-process cannot check.

## 11. Unary RPC test matrix

| Group | Test case | PASS condition |
| --- | --- | --- |
| Success | Valid request | Exact response fields |
| Validation | Blank/malformed field | Status INVALID_ARGUMENT |
| Business error | Resource does not exist | Status NOT_FOUND |
| Authentication | Missing/invalid credentials | Status UNAUTHENTICATED |
| Authorization | Principal lacks permission | Status PERMISSION_DENIED |
| Dependency | Backend unavailable | Status per error mapping |
| Deadline | Response exceeds deadline | Client receives DEADLINE_EXCEEDED |
| Interceptor | Metadata/Context propagated | Handler receives expected context |
| Cancellation | Client cancels call | Work stops or cleans up per contract |
| Concurrency | Multiple concurrent calls | No state leaked across requests |
| Lifecycle | Test finishes | Channel/server shut down |
| Spring wiring | Service bean registered | RPC succeeds through Spring-managed server |

Not every test needs a real server. Pick the transport matching the question to verify, keep tests small, and focus on one contract at a time.

## 12. Practice exercise

GreeterService.SayHello receives HelloRequest and returns HelloReply. The service requires a non-empty name, an interceptor attaches a request ID to Context, and the client sets a 200 ms deadline. A recent bug caused failing requests to still call the repository, and the test suite occasionally hangs after finishing.

**Requirements:**

1. Create an in-process server/channel fixture with a unique server name per test.
2. Write a success test verifying the exact response.
3. Write a validation test verifying INVALID_ARGUMENT and that the repository is not called.
4. Verify the interceptor passes the request ID via Context to the handler.
5. Write a deadline/cancellation test using a controllable latch or scheduler.
6. Run multiple concurrent calls and verify no request ID leaks across calls.
7. Close the channel and server during cleanup with a finite timeout.
8. Add a Spring integration test to verify service/interceptor beans are registered on the starter-managed server.
9. Add TCP/TLS tests if certificates, HTTP/2, or ingress need verification.

**Self-check questions:**

- Why does an in-process server not need a TCP port?
- When should you use directExecutor(), and what are its limitations?
- Why must a new server name be created for each test?
- In what order must a unary server call onNext() and onCompleted()?
- Why should error tests check both status codes and side effects?
- How do you verify that an interceptor puts a principal/request ID into Context?
- Why should fixed sleeps not be used to test deadlines?
- Which transport properties cannot be verified by in-process tests?
- Why is a Spring integration test needed in addition to custom-built fixtures?

**Remember:** An in-process channel connects generated stubs to a test server by identifier name, enabling unary RPC testing without a network port. Create a unique server name, build a channel pointing to that exact name, verify responses, validation, statuses, interceptors, Context, and call lifecycle; always close the channel and server after tests. Use Spring integration tests to verify wiring, and TCP/TLS tests to verify HTTP/2, certificates, proxies, and network behavior.
