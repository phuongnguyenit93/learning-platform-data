# Testing Auth Metadata

## Learning Objectives

After this lesson, you will be able to:

- Explain how metadata is sent alongside a gRPC call and distinguish metadata from the Protobuf payload.
- Define metadata keys following naming and marshaller rules.
- Test server-side authentication using **ServerInterceptor**.
- Send bearer tokens from the client using **ClientInterceptor**.
- Verify **UNAUTHENTICATED** status for missing/invalid credentials and distinguish it from **PERMISSION_DENIED**.
- Integrate interceptors into a Spring gRPC server without unintentionally creating an extra server.
- Test both success and failure paths and ensure credentials are protected with TLS.

## 1. Where Does Auth Metadata Live in a gRPC Call?

gRPC metadata is a set of key-value pairs accompanying a call, transmitted over HTTP/2 headers/trailers. Metadata typically carries control or contextual information such as bearer tokens, trace IDs, tenant IDs, and correlation IDs. The business data of the request and response remains inside the Protobuf message.

In **SPRING_GRPC**, authentication is usually performed in an interceptor before the request reaches the service method. The interceptor reads the metadata, verifies the credentials, and decides whether to allow the call to proceed or terminate it with a status. This allows multiple services to enforce the same policy and avoids repeating authentication logic in every method.

Metadata does not encrypt data by itself. A bearer token sent in metadata still requires TLS to protect it in transit. A test using plaintext loopback can verify the interceptor and status handling, but it does not prove that credentials are protected over the network; TLS must be tested separately.

## 2. Metadata Key Naming Rules

Metadata keys use lowercase names by gRPC convention. Keys carrying ASCII strings use **Metadata.ASCII_STRING_MARSHALLER**; keys carrying binary data have the **-bin** suffix and use the corresponding binary marshaller.

Example defining an authorization key:

~~~java
final class AuthMetadata {
    static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
            "authorization",
            Metadata.ASCII_STRING_MARSHALLER);

    private AuthMetadata() {}
}
~~~

Do not use the reserved **grpc-** prefix for application metadata. Avoid placing large payloads in metadata because headers have size limits and metadata is processed on every call. Tokens, tenant IDs, or trace IDs should be concise and well-formatted.

## 3. ServerInterceptor Checking Bearer Tokens

A **ServerInterceptor** runs before the service handler. If credentials are invalid, the interceptor closes the call with **UNAUTHENTICATED** and does not call **next.startCall**, so the business method is never executed.

The example below uses a fixed token solely to illustrate the test:

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

final class AuthServerInterceptor implements ServerInterceptor {
    private final TokenVerifier tokenVerifier;

    AuthServerInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AuthMetadata.AUTHORIZATION);
        if (authorization == null
                || !authorization.startsWith("Bearer ")) {
            call.close(
                Status.UNAUTHENTICATED
                    .withDescription("Authentication required"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        String token = authorization.substring("Bearer ".length());
        if (!tokenVerifier.isValid(token)) {
            call.close(
                Status.UNAUTHENTICATED
                    .withDescription("Invalid credentials"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

**TokenVerifier** represents the component that verifies token signature, issuer, audience, expiry, and claims. Do not rely on simple string equality checks for tokens in production. Never log tokens or expose tokens/internal verification details in status descriptions.

**UNAUTHENTICATED** means the caller has not been authenticated or provided invalid credentials. If the caller is authenticated but lacks permission to perform an action, use **PERMISSION_DENIED**.

## 4. ClientInterceptor Attaching Metadata to Calls

The client can attach authorization metadata using a **ClientInterceptor**. The interceptor receives the call's own **Metadata** and adds the bearer token before the call is sent:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

final class BearerTokenClientInterceptor implements ClientInterceptor {
    private final String token;

    BearerTokenClientInterceptor(String token) {
        this.token = token;
    }

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
                    Listener<RespT> responseListener,
                    Metadata headers) {
                headers.put(
                    AuthMetadata.AUTHORIZATION,
                    "Bearer " + token);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

In a real application, tokens should come from a credential provider with an appropriate lifecycle, such as a token refresh mechanism or **CallCredentials**, rather than being hardcoded in a stub. The interceptor above is just a small test fixture to demonstrate sending metadata on every call.

Do not share a single global mutable **Metadata** instance across multiple calls. Create or attach headers on each call's own metadata to avoid leaking tokens across requests, especially when multiple tenants or users share a channel.

## 5. Registering Interceptors on the Spring gRPC Server

Two cases must be distinguished:

- If the Spring gRPC starter starts the server and registers service beans automatically, configure the server interceptor via the extension point of the exact starter/version in use.
- If the test owns the server itself, you can register the interceptor directly on **NettyServerBuilder**.

Example of a self-managed test server fixture:

~~~java
final class AuthTestGrpcServer implements SmartLifecycle {
    private final BindableService service;
    private final ServerInterceptor authInterceptor;
    private volatile Server server;

    AuthTestGrpcServer(
            BindableService service,
            ServerInterceptor authInterceptor) {
        this.service = service;
        this.authInterceptor = authInterceptor;
    }

    @Override
    public synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }

        try {
            NettyServerBuilder builder = NettyServerBuilder.forPort(0);
            builder.intercept(authInterceptor);
            builder.addService(service);
            server = builder.build().start();
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot start authenticated gRPC test server", ex);
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

The fixture binds port **0** so the OS allocates a dynamic port. Spring manages **SmartLifecycle**: the server starts with the context and stops when the context closes. If the starter already manages the server, do not create a second fixture for the same service; instead, test the interceptor on the starter's server via the official registration configuration.

## 6. Registering Test Beans and Creating the Client Channel

The test configuration creates the service, token verifier, interceptor, and server fixture:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class AuthGrpcTestConfiguration {
    @Bean
    TokenVerifier tokenVerifier() {
        return token -> "integration-test-token".equals(token);
    }

    @Bean
    AuthServerInterceptor authServerInterceptor(TokenVerifier verifier) {
        return new AuthServerInterceptor(verifier);
    }

    @Bean
    AuthTestGrpcServer authTestGrpcServer(
            GreeterServiceImpl greeter,
            AuthServerInterceptor interceptor) {
        return new AuthTestGrpcServer(greeter, interceptor);
    }
}
~~~

**GreeterServiceImpl** is an illustrative service bean; replace it with the implementation extending your project's generated base class. If the production starter already starts the server, the test configuration should apply the interceptor bean on that server rather than importing **AuthTestGrpcServer**.

The test creates a channel after Spring refreshes the context:

~~~java
@SpringBootTest
@Import(AuthGrpcTestConfiguration.class)
class AuthMetadataIntegrationTest {
    @Autowired
    AuthTestGrpcServer grpcServer;

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

Plaintext here is strictly for loopback testing to focus on interceptor logic. In real environments, bearer tokens must be transmitted over TLS; never deploy metadata authentication over untrusted plaintext connections.

## 7. Testing Missing Metadata and Invalid Tokens

A stub without the interceptor sends calls without authorization metadata. The server must terminate the call with **UNAUTHENTICATED**:

~~~java
@Test
void rejectsCallWithoutAuthorizationMetadata() {
    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.sayHello(
            HelloRequest.newBuilder().setName("Mai").build()));

    assertEquals(
        Status.Code.UNAUTHENTICATED,
        Status.fromThrowable(error).getCode());
}
~~~

You can create a stub attached with an invalid token:

~~~java
Channel invalidAuthChannel = ClientInterceptors.intercept(
    channel,
    new BearerTokenClientInterceptor("wrong-token"));

GreeterGrpc.GreeterBlockingStub invalidStub =
    GreeterGrpc.newBlockingStub(invalidAuthChannel)
        .withDeadlineAfter(2, TimeUnit.SECONDS);

StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> invalidStub.sayHello(
        HelloRequest.newBuilder().setName("Mai").build()));

assertEquals(Status.Code.UNAUTHENTICATED,
    Status.fromThrowable(error).getCode());
~~~

Tests should also verify that the service method is not invoked when the interceptor rejects a call, such as by using a spy or counter. This proves authentication is enforced before the business handler rather than just checking that the client received some error.

## 8. Testing Valid Tokens

Attach the client interceptor with a valid test token and call the same server:

~~~java
@Test
void acceptsValidBearerMetadata() {
    Channel authenticatedChannel = ClientInterceptors.intercept(
        channel,
        new BearerTokenClientInterceptor("integration-test-token"));

    GreeterGrpc.GreeterBlockingStub authenticatedStub =
        GreeterGrpc.newBlockingStub(authenticatedChannel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);

    HelloReply reply = authenticatedStub.sayHello(
        HelloRequest.newBuilder().setName("Mai").build());

    assertEquals("Hello, Mai", reply.getMessage());
}
~~~

The underlying channel remains the resource that needs closing; **ClientInterceptors.intercept** creates a channel wrapper, not an independent physical connection requiring separate shutdown. Do not close the channel while another RPC is still using it.

If the interceptor authenticates successfully and attaches a principal to the gRPC **Context**, the service can read the identity from the context. In that case, include tests verifying that the right principal reaches the handler, not just a generic response check.

## 9. Distinguishing Authentication and Authorization

The two security decisions produce different statuses:

| Scenario | Status | Meaning |
| --- | --- | --- |
| Missing token | **UNAUTHENTICATED** | Caller has not proven its identity. |
| Bad signature, expired, or invalid issuer token | **UNAUTHENTICATED** | Credentials are not accepted. |
| Valid token but missing scope/role | **PERMISSION_DENIED** | Caller is authenticated but lacks sufficient permissions. |
| Resource does not exist | **NOT_FOUND** | Business/resource error, not an authentication error. |

Do not return **UNAUTHENTICATED** for all authorization errors. This distinction helps clients know whether they need to re-authenticate/refresh credentials or request different permissions.

An authorization test should use a valid token that lacks permissions and verify **PERMISSION_DENIED**. Do not use an invalid token to simulate a missing role, because the two scenarios occur at different stages.

## 10. Metadata for Tracing and Tenant Context

Beyond authorization, integration tests can check context-specific metadata:

- **x-request-id**: correlates logs across client, interceptor, and service.
- **traceparent** or trace metadata per the tracing stack in use.
- **x-tenant-id**: routes or selects a tenant after authentication.

A tenant ID sent by a client does not prove on its own that the caller belongs to that tenant. The server must cross-check the tenant in the token/principal against the tenant metadata before accessing data. Never trust self-reported client metadata if it affects access rights.

Tests should send a matching tenant, a tenant that mismatches the principal, and missing metadata. Verify that the interceptor/service rejects mismatches before accessing another tenant's data.

## 11. Metadata Security Considerations

- Use TLS to protect bearer tokens in transit.
- Never log authorization headers or tokens in application logs, tracing attributes, or exception messages.
- Never place tokens in Protobuf payloads, URLs, or query strings.
- Do not share mutable metadata objects across calls.
- Limit metadata sizes and reject malformed values.
- Verify token signature, issuer, audience, expiry, and algorithm per policy.
- Do not trust self-declared tenant/role metadata unless bound to an authenticated principal.
- Use short-lived test credentials, and never store production secrets in test resources.

Metadata is an RPC header, not an inherently secure secret container. TLS, credential verification, and logging policies must all be verified independently.

## 12. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Uppercase metadata keys or wrong marshaller | Keys are not processed as expected | Use lowercase names and the matching marshaller type. |
| Placing tokens in Protobuf payloads | Mixes auth with business data | Use authorization metadata. |
| Sending bearer tokens over untrusted plaintext | Credentials can be intercepted in transit | Enable TLS and test TLS separately. |
| Testing only valid tokens | Misses rejection paths | Test missing, invalid, and expired tokens. |
| Returning **PERMISSION_DENIED** for invalid tokens | Client cannot distinguish authn from authz | Use **UNAUTHENTICATED** for invalid credentials. |
| Trusting client-supplied tenant IDs | Potential cross-tenant data access | Cross-check against the authenticated principal. |
| Logging all metadata | Leaks tokens or sensitive data | Redact authorization and sensitive metadata. |
| Checking status without verifying handler did not run | Errors could originate from the business method | Use a spy/counter to confirm the interceptor blocked before the handler. |
| Registering interceptors differently in tests than in production | Tests do not reflect real configuration | Test the actual starter extension point deployed. |

## 13. Auth Metadata Testing Matrix

A baseline integration test suite should include:

1. Missing authorization metadata: **UNAUTHENTICATED**.
2. Wrong or expired bearer token: **UNAUTHENTICATED**.
3. Valid token: RPC succeeds.
4. Valid token lacking role/scope: **PERMISSION_DENIED**.
5. Tenant metadata mismatching principal: rejected before data access.
6. Authorization metadata is not written to logs.
7. Multiple concurrent calls with different tokens/tenants do not leak metadata across calls.
8. TLS test confirms credentials travel over an encrypted connection.

Set deadlines on every RPC and close channels after tests. When using Spring context caching, let Spring manage the server; tests only close channels they create.

## 14. Hands-On Exercise

Create an integration test for the **Greeter** service with authentication metadata:

1. Define the **authorization** key with **ASCII_STRING_MARSHALLER**.
2. Create an **AuthServerInterceptor** that verifies bearer tokens before calling the service handler.
3. Register the interceptor on the Spring gRPC server via the starter's extension point or a self-managed server test fixture.
4. Create a client interceptor that attaches the bearer token on each call.
5. Test missing and invalid tokens to verify **UNAUTHENTICATED**.
6. Test a valid token to verify the RPC succeeds.
7. Add a case with a valid token lacking scope to verify **PERMISSION_DENIED**.
8. Confirm the service handler does not execute when authentication fails.
9. Verify metadata is not logged and channels/servers follow proper lifecycle shutdown.

**Completion criteria:** tests prove metadata is transmitted accurately, the server interceptor blocks unauthenticated requests, statuses distinguish authn/authz, and credentials do not leak across calls.

## 15. Takeaways

- gRPC metadata carries call context over HTTP/2 headers/trailers; business payloads remain in Protobuf.
- Use lowercase metadata keys and appropriate marshallers; binary keys use the **-bin** suffix.
- Server interceptors authenticate before the service handler and can terminate calls with **UNAUTHENTICATED**.
- Client interceptors or **CallCredentials** attach per-call credentials.
- **UNAUTHENTICATED** indicates missing/invalid identity or credentials; **PERMISSION_DENIED** indicates an authenticated caller lacking permissions.
- Metadata does not encrypt itself; bearer tokens require TLS over untrusted connections.
- Never log tokens, trust unverified tenant metadata, or share mutable metadata across calls.
- Integration tests must cover success, missing/invalid tokens, insufficient permissions, isolation, and TLS.

Testing auth metadata with server interceptors and client credentials ensures Spring gRPC services authenticate requests prior to business logic, return consistent statuses, and keep credentials isolated across concurrent RPCs.
