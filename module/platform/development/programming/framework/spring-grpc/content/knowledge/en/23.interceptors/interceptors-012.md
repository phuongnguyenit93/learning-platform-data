# Testing Interceptor Success and Failure Paths

Interceptors sit on the path of every RPC, so a small bug can affect many services or clients simultaneously. Tests must prove both paths: valid requests proceed to the handler with the right metadata/context; invalid requests are blocked with the appropriate gRPC status and do not execute business logic.

In Spring gRPC, interceptors must be tested at three levels: interceptor logic, behavior across the gRPC channel/server, and verifying Spring actually attaches the interceptor at the intended scope. This lesson focuses on testing success, authentication/authorization failures, statuses, metadata, ordering, concurrency, and the limits of in-process tests.

## 1. Defining the contract to test

Before writing tests, clearly specify what the interceptor is responsible for and what must hold true when calls succeed or fail:

| Scenario | Expected behavior |
| --- | --- |
| Valid credential | Interceptor authenticates, puts principal in gRPC `Context`, and calls `next.startCall(...)` |
| Missing credential | Closes call with `UNAUTHENTICATED`; handler does not run |
| Invalid/expired credential | Closes call with `UNAUTHENTICATED`; does not leak secret details |
| Valid principal lacking permission | Returns `PERMISSION_DENIED`; handler does not run |
| Malformed metadata | Returns appropriate client error, typically `INVALID_ARGUMENT` if it is an input data error |
| Auth dependency failure | Maps to specified status; never leaks arbitrary exceptions over the wire |
| Successful call | Correct response; metrics/tracing/audit recorded once |
| Streaming call | Context and cleanup maintained across the entire stream lifecycle |

Do not merely assert that the interceptor was invoked. A valuable test verifies observable outcomes: status, response, metadata/context received by the handler, allowed side effects, and that the handler never ran when a request was rejected.

## 2. Splitting tests across layers

A balanced strategy usually has three layers:

1. **Policy unit tests:** test authentication, authorization, metadata parsing, and exception mapping logic using fake/mock dependencies.
2. **In-process gRPC tests:** spin up a server and channel in the same process to verify the interceptor is attached, calls traverse the chain, and status and Context propagate accurately.
3. **Transport integration tests:** use real TCP/TLS when verifying certificates, HTTP/2, proxies, networking, metadata through gateways, or environment-configured channels.

Unit tests run fast and pinpoint logic branches. In-process tests verify gRPC behavior without opening network ports. Transport tests are slower but necessary for issues in-process transport does not simulate, especially TLS and proxies.

Do not mock away the entire gRPC pipeline and conclude the interceptor works. Conversely, do not boot the full production topology just to verify an `UNAUTHENTICATED` branch.

## 3. Testing a server interceptor with an in-process server

The example below uses an API key for illustration. The interceptor validates the key, puts the principal into `Context`, and rejects the call if the key is missing or invalid:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Map;

final class ApiKeyInterceptor implements ServerInterceptor {
    static final Metadata.Key<String> API_KEY =
        Metadata.Key.of("x-api-key", Metadata.ASCII_STRING_MARSHALLER);
    static final Context.Key<String> CALLER = Context.key("caller");

    private final Map<String, String> principalsByKey;

    ApiKeyInterceptor(Map<String, String> principalsByKey) {
        this.principalsByKey = Map.copyOf(principalsByKey);
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String principal = principalsByKey.get(headers.get(API_KEY));
        if (principal == null) {
            call.close(
                Status.UNAUTHENTICATED.withDescription("Invalid credentials"),
                new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context =
            Context.current().withValue(CALLER, principal);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

In production, replace the illustrative map with an injected `Authenticator`. Do not log API keys or include keys in error responses. If the authentication service throws an exception, the interceptor should catch and map known exceptions to statuses; unexpected errors should be safely logged and mapped to `INTERNAL` or a status defined by the application's error policy.

A test service can read the principal from Context to prove the interceptor propagated the identity:

```java
final class OrdersTestService
        extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> observer) {
        String caller = ApiKeyInterceptor.CALLER.get();
        GetOrderResponse response = GetOrderResponse.newBuilder()
            .setOrderId(request.getOrderId())
            .setStatus("served-for-" + caller)
            .build();
        observer.onNext(response);
        observer.onCompleted();
    }
}
```

This service is strictly for testing. In real applications, handlers use the authenticated principal to enforce business authorization rather than concatenating identity into the response.

## 4. Testing success, missing key, and invalid key

`InProcessServerBuilder` and `InProcessChannelBuilder` let you start a server/channel without TCP ports. The following test checks both the success and rejection paths:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.*;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.ServerServiceDefinition;
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ApiKeyInterceptorTest {
    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        ServerServiceDefinition service =
            ServerInterceptors.intercept(
                new OrdersTestService().bindService(),
                new ApiKeyInterceptor(Map.of("test-key", "alice")));

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(service)
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void validKeyReachesHandlerWithAuthenticatedContext() {
        GetOrderResponse response = stubWithKey("test-key").getOrder(
            GetOrderRequest.newBuilder().setOrderId("ORD-1").build());

        assertEquals("served-for-alice", response.getStatus());
    }

    @Test
    void missingKeyIsRejectedBeforeHandler() {
        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> OrderServiceGrpc.newBlockingStub(channel).getOrder(
                GetOrderRequest.newBuilder().setOrderId("ORD-1").build()));

        assertEquals(Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
    }

    @Test
    void invalidKeyIsRejected() {
        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stubWithKey("wrong-key").getOrder(
                GetOrderRequest.newBuilder().setOrderId("ORD-1").build()));

        assertEquals(Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
    }

    private OrderServiceGrpc.OrderServiceBlockingStub stubWithKey(
            String apiKey) {
        ClientInterceptor addKey = new ClientInterceptor() {
            @Override
            public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
                    MethodDescriptor<ReqT, RespT> method,
                    CallOptions callOptions,
                    Channel next) {
                return new ForwardingClientCall
                        .SimpleForwardingClientCall<ReqT, RespT>(
                            next.newCall(method, callOptions)) {
                    @Override
                    public void start(
                            Listener<RespT> listener,
                            Metadata headers) {
                        headers.put(ApiKeyInterceptor.API_KEY, apiKey);
                        super.start(listener, headers);
                    }
                };
            }
        };

        Channel wrapped = ClientInterceptors.intercept(channel, addKey);
        return OrderServiceGrpc.newBlockingStub(wrapped);
    }
}
```

This test assumes generated types `OrderServiceGrpc`, `GetOrderRequest`, and `GetOrderResponse` from the application's proto files. `grpc-inprocess` and JUnit 5 must be in test dependencies. The test uses `directExecutor()` to simplify execution; if your interceptor relies on schedulers or asynchronous callbacks, add tests with an appropriate executor.

The three tests above verify:

- A valid key passes through the interceptor and the handler reads the principal from Context.
- A missing key is rejected with `UNAUTHENTICATED`.
- An invalid key is also rejected before the handler executes business logic.

Add an `AtomicInteger` in the test service to assert the handler is not invoked in the two failure cases. Asserting status alone can miss cases where an interceptor called the handler before closing the call.

## 5. Testing authorization and status mapping

Authentication and authorization are separate decisions. A caller may authenticate successfully yet lack permission to invoke a method.

| Condition | Typical status | Recommended assertion |
| --- | --- | --- |
| Missing credential | `UNAUTHENTICATED` | Handler does not run |
| Invalid/expired credential | `UNAUTHENTICATED` | No internal reason or token leaked |
| Valid principal, missing role/scope | `PERMISSION_DENIED` | Authentication succeeded, policy rejected |
| Required metadata malformed | `INVALID_ARGUMENT` | Stable error description, no sensitive data |
| Auth dependency temporarily unavailable | Usually `UNAVAILABLE` per contract | Do not turn infra failures into credential errors |
| Unexpected error | `INTERNAL` or agreed generic mapping | Log includes correlation ID, response omits stack trace |

Authorization tests should define at least two principals: one authorized and one unauthorized. Call the same method with both principals; verify the authorized caller succeeds, the unauthorized caller receives `PERMISSION_DENIED`, and the service handler does not run for the rejected call.

Avoid asserting exact full error descriptions if wording can change or if they might vary. Focus on status codes, published error metadata, and critical side effects.

## 6. Testing client interceptors and metadata

A client interceptor may add trace context, tenant headers, or credentials. Tests must confirm the headers reach the intended server and never leak to other calls.

A simple test can have the test server record header values into an `AtomicReference`, call a stub over the client-interceptor-wrapped channel, and assert the received value. Include both stubs: one using the channel wrapper and one using the raw channel. Only the wrapper stub should attach the dedicated metadata.

Cases to check:

- Header is added exactly once.
- Pre-existing caller headers follow the chosen merge/override rules.
- Sensitive metadata does not appear in logs.
- One call's tenant/user does not leak to subsequent calls.
- Refreshed credentials pick up the new value on the next call.
- The client interceptor does not mutate a shared `Metadata` object concurrently across calls.

For binary metadata, use a key with an appropriate binary marshaller instead of `ASCII_STRING_MARSHALLER`. Test key names, data types, and header size limits if your application specifies them.

## 7. Testing ordering and composition

When multiple interceptors are composed, tests must verify the actual order required by the application:

- Authentication must establish the principal before authorization reads it.
- Trace context must be present when metrics/auditing record the call.
- Error-handling interceptors must observe the right final status.
- Service-specific interceptors run only on the wrapped service.
- Global interceptors are not registered a second time at service scope unintentionally.

Do not just assert declaration order in configuration. Attach test interceptors that record `before` and `after` events into a thread-safe recorder list, execute RPCs, and compare the event trace against the expected contract. Wrapper/callback ordering can depend on composition style and grpc-java version; tests lock down the project's actual behavior.

A helpful test runs two services on the same server: service A wrapped with dedicated authorization, service B with global tracing only. Call both and verify the dedicated interceptor runs only for A.

## 8. Exceptions, cancellation, streaming, and concurrency

Interceptors must be tested beyond the happy-path unary call:

- **Exceptions during authentication:** known exceptions map to statuses; unexpected exceptions do not leak stack traces.
- **Client cancellation:** metrics/context/resource cleanup runs; the call is not recorded as a success.
- **Deadline exceeded:** interceptor records `DEADLINE_EXCEEDED` and holds no resources after call completion.
- **Server streaming:** context remains active across message callbacks; cleanup runs on complete/error/cancel.
- **Client streaming/bidi streaming:** do not assume the request ends right after `interceptCall`; verify listener lifecycle and callbacks.
- **Concurrent calls:** concurrent RPCs never share principal, tenant, trace ID, or mutable request state.

For streaming, test sending multiple messages and completing normally, then test mid-stream cancellation and failure. Verify cleanup runs only once. For concurrency, issue multiple calls with different principals/tenants and confirm each call's response/audit carries the right identity.

Singleton interceptors in Spring are typically executed concurrently across multiple threads. Concurrency tests expose mutable fields holding request state, shared `Metadata` instances, or non-thread-safe caches.

## 9. Testing Spring wiring

An interceptor bean existing in ApplicationContext does not prove it is attached to the server/channel. Spring integration tests must verify:

1. The context constructs the interceptor bean and injects the right dependencies.
2. The Spring gRPC starter's server customizer or extension point actually registers the interceptor.
3. Service-specific wrappers apply to the right service.
4. Client channels/stubs managed by the starter receive the right client interceptors.
5. No duplicate interceptors occur from combining auto-configuration with manual registration.
6. Context shutdown closes servers/channels and resources held by interceptors.

You can use `@SpringBootTest` with a dynamic port or an appropriate test slice/context. Make real RPCs through managed stub beans to verify behavior; calling `ApplicationContext.getBean(...)` alone is insufficient.

Starter configuration APIs can vary across versions. Run tests against the exact configuration used in production instead of assembling a standalone `ServerBuilder` and assuming the starter wires it identically.

## 10. When are real transport tests needed?

In-process tests are great for verifying interceptor chains, statuses, Context, and metadata in gRPC calls. They do not fully test:

- TLS handshakes, certificate chains, SANs, and client certificates.
- HTTP/2 through ingress, gateways, or service meshes.
- Headers stripped or normalized by proxies.
- DNS, socket timeouts, and network interruptions.
- Header sizes/flow control over real transport.

For interceptors involved in authentication or metadata across proxies, include at least one integration test over real TCP/TLS in a test environment. Certificate mismatch tests must fail; never fix a failing test by disabling hostname verification or switching to plaintext.

## 11. Recommended test matrix

| Category | Core test case | Pass condition |
| --- | --- | --- |
| Server success | Valid credential, handler returns response | Correct response and principal |
| Server failure | Missing/invalid credential | `UNAUTHENTICATED`, handler does not run |
| Authorization | Principal lacks permission | `PERMISSION_DENIED`, no side effects |
| Error mapping | Auth dependency timeout/exception | Status matches contract, no internal leaks |
| Client metadata | Client interceptor adds header | Server receives expected header |
| Scope | Global vs. service-specific | Applies only to in-scope services/methods |
| Composition | Multiple interceptors | Execution order and counts match expectations |
| Context | Multiple concurrent principals | No identity leakage across calls |
| Streaming | Complete, error, cancellation | Listener and cleanup follow lifecycle |
| Spring wiring | Spring-managed stub/server | Interceptor genuinely participates in RPCs |
| Transport | TLS/proxy/network | Behavior matches real configuration |
| Lifecycle | Context/server/channel shutdown | No leaked schedulers, watches, or resources |

Not every test needs to boot the full system. Choose the smallest test layer that proves the contract, then add targeted integration tests for Spring and transport boundaries.

## 12. Practice exercise

`OrderService` uses a server interceptor to validate API keys, place the principal into gRPC `Context`, and check the `orders:cancel` permission for the `CancelOrder` method. A client interceptor attaches trace IDs and tenant IDs. Recently a bug occurred: requests missing a key still generated a successful audit record, and tenants from two concurrent requests occasionally mixed.

**Requirements:**

1. Write unit tests for the authenticator: valid key, invalid key, expired key, and auth dependency unavailable.
2. Write an in-process integration test proving valid requests receive the right principal in Context.
3. Verify requests with a missing/invalid key return `UNAUTHENTICATED` and neither invoke the handler nor record a successful audit.
4. Verify a valid principal lacking `orders:cancel` receives `PERMISSION_DENIED`.
5. Verify the client interceptor sends trace/tenant metadata and tenants do not leak between two concurrent calls.
6. Verify the order authentication → authorization → audit/metrics and confirm no interceptor runs twice.
7. Add tests for streaming cancellation and Spring wiring; use real TLS transport for certificate/proxy checks if the application includes those boundaries.

**Self-check questions:**

- Why must interceptor tests assert both status and whether the handler was called?
- How does `UNAUTHENTICATED` differ from `PERMISSION_DENIED`?
- What can in-process tests verify, and what can they not?
- How do you prove a principal was propagated through gRPC `Context`?
- Why must a client interceptor create per-call metadata?
- Which test detects a duplicated interceptor registration?
- How does streaming cancellation affect cleanup and metrics?
- Why must Spring integration tests make RPCs through Spring-managed stubs?

**Takeaway:** Interceptor testing must cover both success and rejection paths, checking statuses, metadata, Context, handler side effects, and execution order. Use unit tests for policies, in-process tests for gRPC chains, Spring integration tests for wiring, and transport tests for TLS/proxy/network behavior. For singleton interceptors, always test concurrency and streaming lifecycles to prevent data leaks between calls.
