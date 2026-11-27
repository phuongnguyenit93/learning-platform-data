# Testing metadata and deadlines

Metadata and deadlines are two key parts of a gRPC call contract. Metadata carries call-accompanying information such as request IDs, tenants, or credentials; deadlines bound how long a caller waits for a result and propagate across downstream calls. Tests must verify that metadata actually reaches the server, is processed according to policy, and does not leak between calls; and that deadlines are preserved across stubs/interceptors, terminate with the right status, and trigger cancellation upon expiration.

In Spring gRPC, you can test this logic using generated stubs, an in-process server/channel, and interceptors. These tests verify the call pipeline inside the JVM. Spring context tests additionally verify whether channel/stub beans actually attach real interceptors; TCP/TLS integration tests verify metadata and deadlines across real transport, proxies, or service meshes.

## 1. Metadata and deadlines in an RPC

Metadata is a set of headers/trailers at the gRPC layer, separate from the Protobuf request message. It typically carries:

- A request ID or correlation ID to link logs/traces across services.
- Authorization tokens or credentials issued by a credential provider.
- A tenant or routing hint verified against policy.
- Trace context matching the system's observability standard.

A deadline represents the latest point in time the caller will accept a result. The client can set a deadline on the stub or call options; the server reads the deadline from gRPC Context and should stop work when the call is cancelled. Deadlines can propagate to downstream RPCs so the entire request chain adheres to the same time budget.

Metadata is not business payload, and a deadline is not a process-wide timeout. Each RPC has its own metadata and deadline; never store them in mutable fields shared across calls.

## 2. Defining metadata keys properly

grpc-java uses Metadata.Key with a matching marshaller:

```java
import io.grpc.Metadata;

static final Metadata.Key<String> REQUEST_ID =
    Metadata.Key.of(
        "x-request-id",
        Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<String> TENANT_ID =
    Metadata.Key.of(
        "x-tenant-id",
        Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<byte[]> SIGNATURE =
    Metadata.Key.of(
        "x-payload-signature-bin",
        Metadata.BINARY_BYTE_MARSHALLER);
```

Metadata key names must be lowercase. Binary keys carry the -bin suffix and use a binary marshaller; never use an ASCII marshaller to transmit byte arrays. Avoid headers reserved for gRPC transport or custom headers that could conflict with proxies.

Metadata can hold multiple values for the same key. If the contract requires a single value, explicitly define the behavior when the key already exists: preserve the caller-sent value, replace it with a gateway-generated value, or reject the request. Never accidentally append a second value and leave client/server to interpret it differently.

## 3. Attaching metadata with ClientInterceptor

A client interceptor is the right place to attach metadata shared across RPCs. The example below generates a request ID only when the caller has not supplied one:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.function.Supplier;

final class RequestMetadataInterceptor implements ClientInterceptor {
    private final Supplier<String> requestIdSupplier;
    private final Supplier<String> tenantSupplier;

    RequestMetadataInterceptor(
            Supplier<String> requestIdSupplier,
            Supplier<String> tenantSupplier) {
        this.requestIdSupplier = requestIdSupplier;
        this.tenantSupplier = tenantSupplier;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                if (headers.get(REQUEST_ID) == null) {
                    headers.put(REQUEST_ID, requestIdSupplier.get());
                }
                if (headers.get(TENANT_ID) == null) {
                    headers.put(TENANT_ID, tenantSupplier.get());
                }
                super.start(responseListener, headers);
            }
        };
    }
}
```

Suppliers are invoked per call to avoid reusing one fixed request ID for every request. If a request ID was already created by a trusted gateway, the interceptor can preserve it; if the caller lies outside the trust boundary, the gateway should verify or replace the ID per policy.

Never store Metadata or headers in fields of a singleton interceptor. Interceptors are typically used concurrently by many calls; per-call data must stay in local variables. Never log bearer tokens, signatures, or sensitive metadata either.

## 4. Testing metadata with an in-process server

To prove headers traveled through the client call pipeline to the server, attach a server interceptor that records the values:

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<String> receivedRequestId = new AtomicReference<>();
AtomicReference<String> receivedTenant = new AtomicReference<>();

ServerInterceptor captureMetadata = new ServerInterceptor() {
    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        receivedRequestId.set(headers.get(REQUEST_ID));
        receivedTenant.set(headers.get(TENANT_ID));
        return next.startCall(call, headers);
    }
};
```

Use this interceptor when registering the service definition on the in-process server, then call via the generated stub over a channel wrapped with RequestMetadataInterceptor. After the RPC completes, assertions on the test thread verify that the server received the expected request ID and tenant.

This is an in-JVM integration test: it verifies metadata actually traverses the client/server call pipeline, rather than merely calling the interceptor method directly. For multiple concurrent calls, replace AtomicReference with a queue or map keyed by request ID so results from one call do not overwrite another's.

## 5. Setting up the test fixture and calling the stub

A JUnit 5 fixture can generate a dedicated server name, register the service with the server interceptor, and create a channel with the client interceptor:

```java
String serverName = InProcessServerBuilder.generateName();

ServerServiceDefinition observedService =
    ServerInterceptors.intercept(
        new GreeterService().bindService(),
        captureMetadata);

Server server = InProcessServerBuilder.forName(serverName)
    .addService(observedService)
    .build()
    .start();

ManagedChannel baseChannel = InProcessChannelBuilder
    .forName(serverName)
    .build();

Channel interceptedChannel = ClientInterceptors.intercept(
    baseChannel,
    new RequestMetadataInterceptor(
        () -> "req-test-42",
        () -> "tenant-test"));

GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(interceptedChannel);
```

After invoking the RPC, verify the response and the metadata received by the server. Close the channel and then the server during teardown, with a finite shutdown timeout. Generate a fresh server name per test so fixtures do not connect to the wrong server.

This test needs no TCP port. It still verifies the generated stub, method dispatch, and interceptor chain. To test Spring auto-registering interceptor beans onto real channels, use a separate Spring context test.

## 6. Testing metadata generate, preserve, and replace

For request ID or tenant headers, lock down the policy with these cases:

| Metadata sent by caller | Policy | Outcome to verify |
| --- | --- | --- |
| No request ID | Generate | Server receives interceptor-generated ID |
| Valid request ID from trusted gateway | Preserve | Server receives the original ID |
| Invalid request ID | Reject or replace | Behavior clearly defined |
| Multiple values for single-valued key | Reject or pick clear policy | No implicit interpretation |
| Two concurrent calls | Generate per call | One call's ID never appears on the other |

To replace a header, clear old values with headers.removeAll(REQUEST_ID) before adding the new value. To preserve, add only when headers.get(REQUEST_ID) is null. If rejecting, the client interceptor can fail before sending the call; the server must still validate data from untrusted callers.

Never use a request ID as a credential. Nor does a tenant ID by itself prove the caller is allowed to access that tenant; the server must bind the tenant to the authenticated principal.

## 7. Setting deadlines on generated stubs

Blocking stubs support per-call deadlines:

```java
GreeterGrpc.GreeterBlockingStub boundedStub =
    stub.withDeadlineAfter(500, TimeUnit.MILLISECONDS);

HelloReply reply = boundedStub.sayHello(request);
```

withDeadlineAfter returns a newly configured stub without modifying the original stub. The deadline is computed at the moment withDeadlineAfter is called, so derive a bounded stub right before each RPC rather than keeping a stub with a finite deadline to reuse across many calls. gRPC represents deadlines as absolute points in time; as a deadline propagates across hops, elapsed time is not reset into a fresh full timeout.

Async stubs accept deadlines in the exact same way:

```java
GreeterGrpc.GreeterStub boundedAsyncStub =
    asyncStub.withDeadlineAfter(500, TimeUnit.MILLISECONDS);

boundedAsyncStub.sayHello(request, responseObserver);
```

When the deadline expires before the RPC finishes, the caller receives status DEADLINE_EXCEEDED. If the server finishes before the deadline, the caller receives the normal response. Set finite deadlines in tests so the suite does not wait forever if a handler hangs.

## 8. Deadlines propagated to server and downstream

The server can read the active deadline via gRPC Context:

```java
import io.grpc.Context;
import io.grpc.Deadline;

Deadline deadline = Context.current().getDeadline();
if (deadline != null && deadline.isExpired()) {
    // The call has exceeded its time budget.
}
```

Never invent a new timeout longer than the remaining deadline. When calling downstream services, propagate the remaining budget or matching deadline so the entire request chain completes on time. If a downstream does not support cancellation, the application needs appropriate timeouts and cleanup to prevent work from continuing after the caller gave up waiting.

A deadline differs from a connection configuration timeout. Connect timeout governs establishing a connection; an RPC deadline bounds the duration of a single call, including queueing, processing, and response. A connected channel does not guarantee an RPC finishes before its deadline.

## 9. Testing deadlines and cancellation in a controlled way

Avoid using Thread.sleep() to simulate a slow handler. Use a scheduler to delay the response and a cancellation listener to verify the server observes cancellation:

```java
import io.grpc.Context;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

final class DelayedGreeterService extends GreeterGrpc.GreeterImplBase {
    private final ScheduledExecutorService scheduler;
    private final CountDownLatch cancelled;

    DelayedGreeterService(
            ScheduledExecutorService scheduler,
            CountDownLatch cancelled) {
        this.scheduler = scheduler;
        this.cancelled = cancelled;
    }

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> observer) {
        ScheduledFuture<?> responseTask = scheduler.schedule(() -> {
            observer.onNext(HelloReply.newBuilder()
                .setMessage("Hello, " + request.getName())
                .build());
            observer.onCompleted();
        }, 2, TimeUnit.SECONDS);

        Context.current().addListener(context -> {
            responseTask.cancel(false);
            cancelled.countDown();
        }, Runnable::run);
    }
}
```

The test invokes the blocking stub with a deadline shorter than the scheduled response time:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> stub.withDeadlineAfter(100, TimeUnit.MILLISECONDS)
        .sayHello(request));

assertEquals(
    Status.Code.DEADLINE_EXCEEDED,
    error.getStatus().getCode());
assertTrue(cancelled.await(1, TimeUnit.SECONDS));
```

This example requires running the server handler on an appropriate executor and managing the scheduler in the fixture. If directExecutor is used alongside a blocking handler, client timers/calls may not be tested as intended. In this example, the handler returns quickly after scheduling the response; the cancellation listener cancels the scheduled task so no late response is sent.

Tests should verify both the client-side status and server-side cancellation. Asserting DEADLINE_EXCEEDED alone does not prove the server stopped working; scheduled tasks or downstream operations could keep running and consuming resources.

## 10. Combining metadata and deadlines in the same test

A production RPC typically needs request ID, tenant, credentials, and a deadline together. Integration tests should verify:

1. The client interceptor generates or preserves the request ID per policy.
2. Tenant/credential metadata is sent properly and validated by the server before use.
3. The server handler receives the expected principal/context.
4. Stub deadlines are not dropped by client interceptors.
5. When the deadline expires, the client receives DEADLINE_EXCEEDED.
6. The server receives cancellation and halts cancellable tasks.
7. Tokens or sensitive metadata are never written to logs.

Interceptors must call next.newCall(method, callOptions) with the exact CallOptions received. Creating a call with default CallOptions drops the stub's deadline. Testing deadlines over an intercepted channel catches this bug.

## 11. Spring client wiring and transport boundaries

In Spring gRPC, client channels are typically created via beans or the starter's client factory. To test wiring:

- Boot a Spring test context using production-like client configuration.
- Verify that the actual channel/stub is created with the client interceptor.
- Call an RPC against a test server and inspect metadata on the server side.
- Set a deadline on the stub and verify status when the handler is slow.
- Close the channel when the context stops if the application owns the channel lifecycle.

Never assume every bean implementing ClientInterceptor is automatically attached to every channel. Registration mechanisms depend on the starter version and how channels are created. Context tests must invoke the exact stub/channel used by the application service.

In-process tests do not verify HTTP/2 over sockets, TLS/mTLS, certificates, proxies, ingress, service meshes, or metadata limits enforced by gateways. If the system runs through these components, add TCP/TLS integration tests at the corresponding network boundary.

## 12. Test matrix and practice exercise

| Group | Test case | PASS condition |
| --- | --- | --- |
| Metadata generate | Caller sends no request ID | Server receives new ID |
| Metadata preserve | Caller sends trusted ID | Server receives exact ID |
| Metadata replace/reject | Header violates policy | Behavior matches contract |
| Tenant | Tenant metadata mismatches principal | Server rejects per policy |
| Concurrency | Multiple calls with different IDs | No leaked metadata |
| Deadline success | Handler responds before deadline | Receives response |
| Deadline exceeded | Handler responds after deadline | Client receives DEADLINE_EXCEEDED |
| Cancellation | Deadline/caller cancels | Server halts cancellable tasks |
| CallOptions | Stub with deadline via interceptor | Deadline remains enforced |
| Error path | Server returns status/trailers | Client receives original needed status |
| Spring wiring | Stub bean uses configured channel | Interceptor actually executes |
| Transport | TCP/TLS/proxy | Metadata and deadlines work over real network |

**Exercise:** OrderClient.GetOrder requires x-request-id, x-tenant-id, and a bearer token; the default deadline is 700 ms, while the search use case allows only 250 ms. A gateway already generates request IDs for some internal callers.

1. Write a client interceptor that creates a request ID if missing and preserves IDs from trusted gateways.
2. Send tenant and authorization metadata; verify the server does not trust the tenant header if the principal is unauthorized.
3. Write an in-process test to capture metadata on the server side.
4. Verify a stub with a 250 ms deadline retains that deadline across the interceptor.
5. Build a delayed handler with a scheduler and test DEADLINE_EXCEEDED plus server cancellation.
6. Run multiple concurrent calls to detect request ID/tenant leaks.
7. Write a Spring context test for the channel/stub bean and TCP/TLS tests for production transport.

**Self-check questions:**

- How does metadata differ from a Protobuf request message?
- When should you use an ASCII metadata key versus a -bin key?
- Why is a request ID not a credential?
- At what stage should a client interceptor attach metadata?
- Why must CallOptions be forwarded intact when creating ClientCall?
- How does a deadline differ from a connect timeout?
- Where does the server read the deadline from?
- Why should deadline-exceeded tests also check server-side cancellation?
- How do you test that metadata actually reaches the server instead of testing the interceptor in isolation?
- What must be verified using Spring context and TCP/TLS integration tests?

**Remember:** Testing metadata must verify generate/preserve/replace, tenant and credential enforcement per policy, and that headers actually reach the server. Testing deadlines must verify both the DEADLINE_EXCEEDED status and server-side cancellation and cleanup. Preserve CallOptions across interceptors, use in-process tests for the call pipeline, Spring context tests for client wiring, and TCP/TLS tests for real transport.
