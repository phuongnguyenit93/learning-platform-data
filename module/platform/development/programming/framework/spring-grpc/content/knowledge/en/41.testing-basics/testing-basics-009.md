# Testing server interceptors

A server interceptor is a processing layer placed before the service handler in the gRPC server call pipeline. It is commonly used to read metadata, authenticate callers, check permissions, attach principals or correlation IDs to gRPC Context, record telemetry, and standardize request rejection. Because an interceptor affects every RPC passing through it, tests must cover both allowed and rejected cases, as well as verify that the handler receives the expected context.

In Spring gRPC, interceptors can be registered at the server level or attached to individual services depending on configuration. Tests should distinguish two goals: testing interceptor logic with an in-process server, and verifying that Spring actually registers the interceptor bean on the starter-managed server. In-process tests do not verify TLS, HTTP/2 over sockets, ingress, or network policies.

## 1. Where do server interceptors sit in the call pipeline?

When a client calls an RPC, the server resolves the method and runs through interceptors before dispatching to the service handler:

```text
Client stub
    |
    | request + metadata
    v
gRPC server transport
    |
    v
Server interceptor(s)
    | authenticate / authorize
    | inspect metadata
    | attach Context
    v
Service handler
    |
    v
response messages or gRPC status
```

grpc-java defines ServerInterceptor with the interceptCall method. The interceptor receives the ServerCall, Metadata, and the next ServerCallHandler. It can:

- Let the call proceed via next.startCall(call, headers).
- Close the call with a status if credentials are invalid or the caller lacks permissions.
- Create a Context holding call data and propagate it down to the handler.
- Wrap the ServerCall or listener to observe headers, messages, close, and cancellation.

An interceptor does not replace business validation inside the service. It handles cross-cutting concerns applied at the RPC boundary; the service must still validate inputs and resource-level permissions as needed.

## 2. Lifecycle of interceptCall

A minimal interceptor has this shape:

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;

final class LoggingServerInterceptor implements ServerInterceptor {
    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String fullMethod =
            call.getMethodDescriptor().getFullMethodName();

        // Record method/correlation ID per logging policy.
        return next.startCall(call, headers);
    }
}
```

interceptCall runs when the server receives a call, before the listener processes request messages. The returned listener receives callbacks such as onMessage, onHalfClose, onCancel, onComplete, and onReady. For unary RPCs, the server normally receives one request via onMessage followed by onHalfClose before the handler finishes the call.

Never keep request-specific data in mutable fields of a singleton interceptor. Multiple RPCs can execute concurrently on the same instance; storing a principal or request ID in a field leaks data across callers. Use local variables per call or gRPC Context.

## 3. Metadata, authentication, and authorization

Metadata represents headers/trailers at the gRPC layer, commonly used to carry credentials, tenant IDs, request IDs, or tracing information. The interceptor must read metadata using defined keys:

```java
import io.grpc.Metadata;

static final Metadata.Key<String> AUTHORIZATION =
    Metadata.Key.of(
        "authorization",
        Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<String> REQUEST_ID =
    Metadata.Key.of(
        "x-request-id",
        Metadata.ASCII_STRING_MARSHALLER);
```

Basic authentication workflow:

1. Read authorization metadata.
2. Verify the token/certificate using a trusted verifier.
3. Construct the principal from verification results; never trust arbitrary roles from caller-supplied headers.
4. If credentials are missing or invalid, close with UNAUTHENTICATED.
5. If the identity is valid but lacks permissions, close with PERMISSION_DENIED.
6. If permitted, attach the principal to Context and let the call proceed.

Authentication identifies who the caller is; authorization determines what the caller can do. Never treat header presence as proof of a valid identity. Never log bearer tokens, private keys, or sensitive metadata.

## 4. Propagating the principal via gRPC Context

Context is gRPC's mechanism for passing call-scoped data across callbacks and thread boundaries without global mutable fields. Example interceptor that verifies a bearer token and attaches the principal:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

final class AuthServerInterceptor implements ServerInterceptor {
    static final Context.Key<String> PRINCIPAL =
        Context.key("authenticated-principal");

    private final TokenVerifier verifier;

    AuthServerInterceptor(TokenVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        String principal = verifier.verify(authorization);
        if (principal == null) {
            call.close(
                Status.UNAUTHENTICATED
                    .withDescription("missing or invalid credentials"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context context = Context.current()
            .withValue(PRINCIPAL, principal);
        return Contexts.interceptCall(
            context, call, headers, next);
    }
}
```

TokenVerifier is an application abstraction that must verify signatures, expiration, issuer/audience, and required claims. The example above simplifies checks to highlight the interceptor; production code must distinguish invalid credentials from verifier failures or temporarily unavailable identity providers according to policy.

Contexts.interceptCall ensures the Context stays attached during call processing and listener callbacks. Handlers can read the principal via AuthServerInterceptor.PRINCIPAL.get(). Never pass principals via static mutable variables or fields of a singleton service.

## 5. Allowing or rejecting calls with statuses

When rejecting a call, the interceptor must close the ServerCall and not invoke next.startCall. Example:

```java
if (!authorizationPolicy.canReadOrders(principal)) {
    call.close(
        Status.PERMISSION_DENIED
            .withDescription("caller cannot read orders"),
        new Metadata());
    return new ServerCall.Listener<>() {};
}

return next.startCall(call, headers);
```

Commonly used statuses:

| Scenario | Status |
| --- | --- |
| Missing, invalid, or expired credentials | UNAUTHENTICATED |
| Valid identity lacking permission | PERMISSION_DENIED |
| Malformed request/validation failure | INVALID_ARGUMENT |
| Resource does not exist | NOT_FOUND |
| Dependency temporarily unavailable | UNAVAILABLE per contract |

Do not return INTERNAL for every auth failure. Do not return UNAUTHENTICATED when the caller is authenticated but lacks a role; distinguishing statuses properly helps clients handle errors and helps telemetry classify incidents.

After calling call.close, do not proceed to call next or send responses. An empty listener is returned to satisfy the interceptCall contract; do not use it to perform business work.

## 6. Applying policies by full method name

An interceptor can enforce different policies per method. Use the full method name from MethodDescriptor:

```java
String method = call.getMethodDescriptor().getFullMethodName();

if (method.equals("acme.orders.v1.OrderService/GetOrder")) {
    if (!policy.canReadOrders(principal)) {
        call.close(Status.PERMISSION_DENIED, new Metadata());
        return new ServerCall.Listener<>() {};
    }
}

if (method.equals("acme.orders.v1.OrderService/CancelOrder")) {
    if (!policy.canCancelOrders(principal)) {
        call.close(Status.PERMISSION_DENIED, new Metadata());
        return new ServerCall.Listener<>() {};
    }
}

return next.startCall(call, headers);
```

The method name consists of proto package + service + method, not the Java package or Spring bean name. Extract policy rules into an authorization component that can be unit tested separately, rather than writing a long conditional chain inside the interceptor.

Deny administrative or sensitive methods by default if no rule exists. Public RPCs like health probes may need controlled exceptions, but never disable authentication for the entire server just to make probes work.

## 7. Ordering multiple interceptors

A server may use multiple interceptors for authentication, authorization, tracing, logging, and metrics. They are nested as a wrapper chain; an outer interceptor can short-circuit the call before inner interceptors run.

An example logical ordering that usually makes sense:

1. Correlation/tracing: generate or validate request IDs.
2. Authentication: verify credentials and build the principal.
3. Authorization: check permissions on the method/resource.
4. Metrics/logging: record method, outcome, and duration per policy.
5. Service handler: execute business logic.

Actual registration order depends on the helper APIs and how the starter constructs the interceptor chain. Never infer ordering solely from bean declaration order in the application context. Write tests using spies/counters to verify actual ordering, especially when one interceptor depends on Context populated by another.

If authorization runs before authentication, the principal may not exist yet. If logging records metadata before redaction, credentials may be leaked. Testing order is part of security testing, not merely a configuration detail.

## 8. Building an in-process server with a server interceptor

The in-process transport allows testing interceptors through generated stubs without opening a TCP port:

```java
String serverName = InProcessServerBuilder.generateName();

ServerServiceDefinition securedService =
    ServerInterceptors.intercept(
        new GreeterService().bindService(),
        new AuthServerInterceptor(testTokenVerifier));

Server server = InProcessServerBuilder.forName(serverName)
    .directExecutor()
    .addService(securedService)
    .build()
    .start();

ManagedChannel channel = InProcessChannelBuilder
    .forName(serverName)
    .directExecutor()
    .build();

GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(channel);
```

ServerInterceptors.intercept wraps the ServiceDefinition with the specified interceptor. This tests the interceptor implementation and service dispatch. If you need to verify global interceptors or server customizers registered by the Spring starter, boot a Spring context using application configuration instead of manually wrapping the service in a test fixture.

Generate a new server name per fixture. Close the channel before the server in teardown and set a finite shutdown timeout so the test suite cannot hang.

## 9. Testing metadata and Context when permitted

Test clients can attach authorization metadata using a ClientInterceptor:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ClientInterceptors;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

ClientInterceptor authHeader = new ClientInterceptor() {
    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata requestHeaders) {
                requestHeaders.put(
                    AUTHORIZATION, "Bearer test-token");
                super.start(responseListener, requestHeaders);
            }
        };
    }
};

Channel authenticatedChannel =
    ClientInterceptors.intercept(channel, authHeader);
GreeterGrpc.GreeterBlockingStub authenticatedStub =
    GreeterGrpc.newBlockingStub(authenticatedChannel);

HelloReply reply = authenticatedStub.sayHello(request);
```

In tests, TokenVerifier can accept a predefined fake token and return a test principal. The service handler reads AuthServerInterceptor.PRINCIPAL.get() and stores the value in an AtomicReference for test assertions after the RPC completes.

Example handler recording the principal from Context for test verification:

```java
final class GreeterService extends GreeterGrpc.GreeterImplBase {
    private final AtomicReference<String> observedPrincipal;

    GreeterService(AtomicReference<String> observedPrincipal) {
        this.observedPrincipal = observedPrincipal;
    }

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> observer) {
        observedPrincipal.set(AuthServerInterceptor.PRINCIPAL.get());
        observer.onNext(HelloReply.newBuilder()
            .setMessage("Hello, " + request.getName())
            .build());
        observer.onCompleted();
    }
}
```

After calling via authenticatedStub, assertions on the test thread can verify that observedPrincipal matches the principal returned by the test verifier. Using AtomicReference here represents observation state in a test fixture; never turn it into a shared identity field in a production service.

Tests should verify:

- The header is sent with the expected key/value.
- The verifier receives the credential and returns the expected principal.
- The handler sees the principal via Context.
- Two calls with different principals do not leak data across one another.
- Tokens do not appear in logs.

Never use production tokens in tests. Test credentials should be dummy data and test verifiers must behave deterministically.

## 10. Testing rejections and verifying the handler is not invoked

When metadata is missing or the token is invalid, tests must verify both the status and that the service handler did not run:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> GreeterGrpc.newBlockingStub(channel).sayHello(request));

assertEquals(
    Status.Code.UNAUTHENTICATED,
    error.getStatus().getCode());
assertEquals(0, handlerInvocationCount.get());
```

For a valid identity lacking permissions, expect PERMISSION_DENIED. Use an AtomicInteger in a service test double to count handler invocations; post-call assertions verify that the interceptor blocked the request before dispatch.

Do not check only the status. An interceptor might accidentally call next.startCall and then close the call; testing handler invocations catches business code running even when the client receives an error. Likewise, authorization tests should use both authorized and unauthorized principals to verify both branches.

## 11. Spring wiring and integration test boundaries

In-process tests with ServerInterceptors.intercept verify interceptor logic, but do not prove the Spring gRPC starter registered the interceptor bean correctly. To verify wiring:

1. Create a Spring test context using the project's starter and application configuration.
2. Register services, authentication verifiers, and interceptors as in production.
3. Start the Spring-managed server on a test port or dynamic port.
4. Invoke RPCs with a stub over a channel connected to that server.
5. Check allow/deny behavior, Context propagation, interceptor ordering, and shutdown lifecycle.

The extension point for registering global/server interceptors depends on the starter version. Use the mechanism supported by your project's version; never assume every starter automatically registers every bean implementing ServerInterceptor.

TCP/TLS integration tests are required when verifying certificates, HTTP/2, ingress, service meshes, proxies, or metadata over real transport. The in-process transport does not test those boundaries.

## 12. Test matrix and practice exercise

| Group | Test case | PASS condition |
| --- | --- | --- |
| Authentication | Valid token | Call reaches handler and Context holds principal |
| Missing credential | No authorization metadata | UNAUTHENTICATED, handler does not run |
| Invalid credential | Wrong/expired token | UNAUTHENTICATED |
| Authorization | Principal lacks permission | PERMISSION_DENIED, handler does not run |
| Method policy | GetOrder and CancelOrder | Each method enforces the right permission |
| Context | Two calls with different principals | No principal leaked across calls |
| Metadata | Request ID and credential | Correct keys read, secrets not logged |
| Interceptor order | Multiple interceptors | Actual order matches design |
| Error path | Verifier/dependency failure | Status mapping follows policy |
| Concurrency | Multiple concurrent calls | No shared mutable state for calls |
| Spring wiring | Starter-managed server | Interceptor bean actually registered |
| Transport | TCP/TLS | Certificates, HTTP/2, and proxy work |

**Exercise:** OrderService has GetOrder restricted to role ORDER_READ and CancelOrder restricted to role ORDER_ADMIN. Every call requires a bearer token, a request ID, and an audit record; health probes follow a separate policy.

1. Write AuthServerInterceptor to verify tokens and attach the principal to Context.
2. Write an authorization policy by full method name for GetOrder and CancelOrder.
3. Use an in-process server to test valid tokens, missing tokens, invalid tokens, and insufficient roles.
4. Verify the handler does not run when the interceptor rejects a call.
5. Send two concurrent calls with different principals and check Context isolation.
6. Verify the order of tracing, authentication, authorization, and logging interceptors.
7. Write a Spring context test verifying the starter registers the interceptor bean.
8. Add TCP/TLS tests to verify metadata and identity over real transport.

**Self-check questions:**

- At what stage of a gRPC call does ServerInterceptor execute?
- Why should principals not be stored in mutable fields of an interceptor?
- How does authentication differ from authorization?
- When rejecting a call, why must you close ServerCall and not call next?
- What does Contexts.interceptCall ensure for callbacks?
- Which components make up a full method name?
- Why should you test handler invocation counts alongside status codes?
- How can interceptor order affect authentication and logging?
- What aspects of Spring/TCP/TLS integration cannot be verified by in-process tests?

**Remember:** Testing server interceptors must cover both permitted and rejected calls. Verify metadata, token verifiers, principals in Context, method-specific permissions, statuses, and whether the handler ran. Use an in-process server to test the call pipeline, Spring context tests to verify interceptor wiring, and TCP/TLS integration tests to verify production transport.
