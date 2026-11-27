# Adding Interceptors for Auth and Correlation ID

In this project, you will build a pair of interceptors so that every RPC passes through the same authentication and request-tracing rules. The server interceptor reads a Bearer token, verifies identity, generates or validates a correlation ID, and places both values into the gRPC `Context`. The client interceptor attaches the access token and correlation ID to outbound RPC metadata.

Expected outcome: requests with missing or invalid tokens are rejected with the appropriate gRPC status; services read the authenticated identity and correlation ID without manually parsing metadata; responses return the correlation ID so clients and operators can trace logs. This lesson uses a unary RPC for illustration, though the interceptors apply to both unary and streaming RPCs.

The Java examples use APIs available in Java 11+ and `grpc-java`. Use the same `grpc-java` version across runtime, stubs, and test dependencies.

## 1. Objectives and Processing Flow

After completing this lesson, you will be able to:

- Declare metadata keys following gRPC conventions.
- Write a server interceptor that verifies Bearer tokens and returns appropriate statuses on authentication failures.
- Attach the principal and correlation ID into **io.grpc.Context**.
- Write client interceptors that attach authentication credentials and correlation IDs to outbound RPCs.
- Register interceptors on the right server and channel in a Spring application.
- Test valid requests, missing tokens, invalid tokens, invalid correlation IDs, and downstream correlation ID propagation.

Expected flow:

~~~mermaid
sequenceDiagram
    participant C as gRPC Client
    participant CI as Client Interceptors
    participant SI as Server Interceptor
    participant S as Spring gRPC Service
    participant D as Downstream Service

    C->>CI: Call RPC
    CI->>CI: Attach Authorization and x-correlation-id
    CI->>SI: Metadata over HTTP/2
    SI->>SI: Validate correlation ID
    SI->>SI: Verify Bearer token
    alt Invalid token
        SI-->>C: UNAUTHENTICATED + correlation ID trailer
    else Valid token
        SI->>S: Attach principal and correlation ID to gRPC Context
        S->>D: Call downstream RPC
        Note over S,D: Client interceptor reads correlation ID from Context
        D-->>S: Response
        S-->>C: Response + correlation ID
    end
~~~

Clearly distinguish three concepts:

| Component | Role |
|---|---|
| Authentication | Verifies which identity the client represents |
| Authorization | Checks whether that identity has permission to invoke a specific operation |
| Correlation ID | Links logs and activities for the same request across multiple services |

The authentication interceptor owns authentication. Business permissions must still be enforced at the service or authorization layer. Correlation IDs are strictly for cross-referencing and must never be used as proof of identity.

## 2. Preparing the Contract and Metadata

Use a small unary RPC to test the interceptors. Create a Protocol Buffers file, e.g., **src/main/proto/order.proto**:

~~~proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.grpc";

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string status = 2;
}
~~~

Run the Protocol Buffers code generation task configured in your project. The remaining steps use the generated service base class and stubs produced by the plugin.

Metadata conventions for this lesson:

| Metadata key | Direction | Meaning |
|---|---|---|
| **authorization** | Client → Server | Bearer access token |
| **x-correlation-id** | Client → Server, Server → Client | Request correlation identifier |
| **traceparent**, **tracestate**, **baggage** | Per tracing config | OpenTelemetry trace context |

Metadata key names must be lowercase. Use **Metadata.ASCII_STRING_MARSHALLER** for text values. Never create custom keys starting with **grpc-**, as that prefix is reserved for the gRPC protocol.

The correlation ID in this example is limited to 64 ASCII characters consisting of letters, digits, dots, underscores, and hyphens. If the client omits it, the server generates a UUID. If the client sends an invalid value, the server returns **INVALID_ARGUMENT** while still generating a fresh ID to identify that rejection. Never put tokens, emails, usernames, or personal data into a correlation ID.

## 3. Creating Metadata and Request Context Classes

Create a class holding metadata keys shared between client and server:

~~~java
package com.example.orders.grpc;

import io.grpc.Metadata;

public final class GrpcMetadata {
    private GrpcMetadata() {}

    public static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> CORRELATION_ID =
            Metadata.Key.of(
                    "x-correlation-id",
                    Metadata.ASCII_STRING_MARSHALLER);
}
~~~

Create context keys so the service can read information verified by the interceptor:

~~~java
package com.example.orders.grpc;

import io.grpc.Context;

public final class GrpcRequestContext {
    private GrpcRequestContext() {}

    public static final Context.Key<AuthenticatedUser> AUTHENTICATED_USER =
            Context.key("authenticated-user");

    public static final Context.Key<String> CORRELATION_ID =
            Context.key("correlation-id");
}
~~~

**io.grpc.Context** binds data to RPC execution and is managed by `grpc-java` across callbacks. It is not an application-managed **ThreadLocal**. When offloading work to another executor, propagate the context explicitly; otherwise values may disappear on the worker thread.

Create a minimal principal for the application:

~~~java
package com.example.orders.grpc;

import java.util.Set;

public final class AuthenticatedUser {
    private final String subject;
    private final Set<String> authorities;

    public AuthenticatedUser(String subject, Set<String> authorities) {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        this.subject = subject;
        this.authorities = Set.copyOf(authorities);
    }

    public String getSubject() {
        return subject;
    }

    public boolean hasAuthority(String authority) {
        return authorities.contains(authority);
    }

    public Set<String> getAuthorities() {
        return authorities;
    }
}
~~~

The principal retains only the attributes needed for authorization and auditing. Never store raw access tokens inside gRPC `Context`, logs, or the principal object.

## 4. Defining the Token Verification Port

Never manually decode a JWT and treat its payload as trustworthy. Always verify signatures and required claims using a security library approved by your project.

Decouple verification from the interceptor via an interface:

~~~java
package com.example.orders.security;

import com.example.orders.grpc.AuthenticatedUser;

public interface TokenVerifier {
    AuthenticatedUser verify(String token)
            throws InvalidTokenException,
                   AuthenticationUnavailableException;
}
~~~

The two exceptions can be declared minimally as follows:

~~~java
package com.example.orders.security;

public final class InvalidTokenException extends Exception {
    public InvalidTokenException(String message) {
        super(message);
    }
}
~~~

~~~java
package com.example.orders.security;

public final class AuthenticationUnavailableException extends Exception {
    public AuthenticationUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

These two exceptions represent distinct failure modes:

- **InvalidTokenException**: token is missing, has an invalid signature, is expired, has a mismatched issuer/audience, or is otherwise rejected.
- **AuthenticationUnavailableException**: the verification system is temporarily unavailable, e.g., an introspection service or key store outage.

A **TokenVerifier** implementation should:

- Accept only explicitly permitted signing algorithms; never trust the algorithm declared in the token header.
- Validate signature, issuer, audience, expiration, and not-before claims.
- Support key rotation and public key caching per policy.
- Return a normalized subject and set of authorities.
- Never log tokens or leak verification details to the client.

When verifying JWTs with local public keys, checks typically run quickly inside the interceptor. If a remote verification service must be called, never let unbounded network calls block gRPC processing threads. Use an asynchronous auth architecture or bounded cache with timeouts, circuit breakers, and clear failure policies.

## 5. Writing the Server Interceptor

Create a helper to validate and generate correlation IDs:

~~~java
package com.example.orders.grpc;

import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIds {
    private static final Pattern VALID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    private CorrelationIds() {}

    public static boolean isValid(String value) {
        return value != null && VALID.matcher(value).matches();
    }

    public static String newId() {
        return UUID.randomUUID().toString();
    }
}
~~~

Next, create **AuthCorrelationServerInterceptor**. This interceptor authenticates before invoking the handler. On success, it wraps **ServerCall** to include the correlation ID in response headers when the service explicitly sends headers, and in trailers when the RPC closes. That ensures both successful and failed responses can be correlated.

~~~java
package com.example.orders.grpc;

import com.example.orders.security.TokenVerifier;
import com.example.orders.security.InvalidTokenException;
import com.example.orders.security.AuthenticationUnavailableException;
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class AuthCorrelationServerInterceptor
        implements ServerInterceptor {

    private final TokenVerifier tokenVerifier;

    public AuthCorrelationServerInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String incomingId = headers.get(GrpcMetadata.CORRELATION_ID);
        String correlationId =
                incomingId == null ? CorrelationIds.newId() : incomingId;

        if (!CorrelationIds.isValid(correlationId)) {
            return reject(
                    call,
                    Status.INVALID_ARGUMENT.withDescription(
                            "Invalid x-correlation-id"),
                    CorrelationIds.newId());
        }

        String token = extractBearerToken(
                headers.get(GrpcMetadata.AUTHORIZATION));

        if (token == null) {
            return reject(
                    call,
                    Status.UNAUTHENTICATED.withDescription(
                            "Missing or invalid bearer credentials"),
                    correlationId);
        }

        AuthenticatedUser user;
        try {
            user = tokenVerifier.verify(token);
        } catch (InvalidTokenException exception) {
            return reject(
                    call,
                    Status.UNAUTHENTICATED.withDescription(
                            "Invalid bearer credentials"),
                    correlationId);
        } catch (AuthenticationUnavailableException exception) {
            return reject(
                    call,
                    Status.UNAVAILABLE.withDescription(
                            "Authentication service unavailable"),
                    correlationId);
        } catch (RuntimeException exception) {
            // Log the exception after scrubbing sensitive data before returning the error.
            return reject(
                    call,
                    Status.INTERNAL.withDescription(
                            "Authentication failed"),
                    correlationId);
        }

        if (user == null) {
            return reject(
                    call,
                    Status.UNAUTHENTICATED.withDescription(
                            "Invalid bearer credentials"),
                    correlationId);
        }

        ServerCall<ReqT, RespT> responseCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {

            @Override
            public void sendHeaders(Metadata responseHeaders) {
                addCorrelationId(responseHeaders, correlationId);
                super.sendHeaders(responseHeaders);
            }

            @Override
            public void close(Status status, Metadata trailers) {
                addCorrelationId(trailers, correlationId);
                super.close(status, trailers);
            }
        };

        Context requestContext = Context.current()
                .withValue(
                        GrpcRequestContext.AUTHENTICATED_USER,
                        user)
                .withValue(
                        GrpcRequestContext.CORRELATION_ID,
                        correlationId);

        return Contexts.interceptCall(
                requestContext,
                responseCall,
                headers,
                next);
    }

    private static String extractBearerToken(String authorization) {
        if (authorization == null
                || !authorization.regionMatches(
                        true, 0, "Bearer ", 0, 7)) {
            return null;
        }

        String token = authorization.substring(7).trim();
        if (token.isEmpty() || token.chars().anyMatch(Character::isWhitespace)) {
            return null;
        }
        return token;
    }

    private static void addCorrelationId(
            Metadata metadata,
            String correlationId) {
        metadata.discardAll(GrpcMetadata.CORRELATION_ID);
        metadata.put(GrpcMetadata.CORRELATION_ID, correlationId);
    }

    private static <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call,
            Status status,
            String correlationId) {

        Metadata trailers = new Metadata();
        trailers.put(GrpcMetadata.CORRELATION_ID, correlationId);
        call.close(status, trailers);

        return new ServerCall.Listener<ReqT>() {};
    }
}
~~~

Key points in the interceptor:

1. Metadata is read once at the RPC boundary. Services never manually parse the `Authorization` header.
2. **TokenVerifier** decides whether the token is valid. Invalid tokens return **UNAUTHENTICATED**; transient verification outages return **UNAVAILABLE**.
3. **Contexts.interceptCall(...)** binds the principal and correlation ID to the context throughout handler invocation and listener callbacks.
4. **ServerCall** is wrapped to inject the correlation ID into response metadata. When the RPC finishes, the ID is included in trailers even if the service never sent explicit headers.
5. When rejecting a request, the interceptor closes the call and returns an empty listener. The business service is never invoked.

If any public RPC does not require a token, maintain an explicit allowlist by full method name and test it thoroughly. Never assume a method is public simply because `Authorization` metadata is missing. All other methods must require authentication by default.

## 6. Reading the Principal and Correlation ID in the Service

Implement the service from its generated base class. The service reads values from the gRPC `Context` and performs business authorization:

~~~java
package com.example.orders.service;

import com.example.orders.grpc.AuthenticatedUser;
import com.example.orders.grpc.GrpcRequestContext;
import com.example.orders.grpc.OrderServiceGrpc;
import com.example.orders.grpc.GetOrderRequest;
import com.example.orders.grpc.GetOrderResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        AuthenticatedUser user =
                GrpcRequestContext.AUTHENTICATED_USER.get();

        String correlationId =
                GrpcRequestContext.CORRELATION_ID.get();

        if (user == null) {
            responseObserver.onError(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required")
                            .asRuntimeException());
            return;
        }

        if (!user.hasAuthority("orders:read")) {
            responseObserver.onError(
                    Status.PERMISSION_DENIED
                            .withDescription("Insufficient permission")
                            .asRuntimeException());
            return;
        }

        // Emit structured logs with subject and correlationId.
        // Do not log access tokens or sensitive request data.

        GetOrderResponse response = GetOrderResponse.newBuilder()
                .setOrderId(request.getOrderId())
                .setStatus("ACCEPTED")
                .build();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
~~~

In a real project, replace the sample response with results from your business service. You can move permission checks into a dedicated authorization service or interceptor if many RPCs share a common policy. Authentication and authorization should return distinct statuses: an unverified identity is **UNAUTHENTICATED**, while a verified identity lacking permissions is **PERMISSION_DENIED**.

## 7. Adding Client Interceptors

The client needs to send access tokens from the application's token source. Never hardcode tokens in source code and never mint tokens inside an interceptor.

Create an abstraction for retrieving access tokens:

~~~java
package com.example.orders.security;

public interface AccessTokenProvider {
    String getAccessToken();
}
~~~

Client interceptor attaching the Bearer token:

~~~java
package com.example.orders.grpc;

import com.example.orders.security.AccessTokenProvider;
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

public final class BearerTokenClientInterceptor
        implements ClientInterceptor {

    private final AccessTokenProvider tokenProvider;

    public BearerTokenClientInterceptor(
            AccessTokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {

            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {

                String token = tokenProvider.getAccessToken();
                headers.discardAll(GrpcMetadata.AUTHORIZATION);

                if (token != null && !token.isBlank()) {
                    headers.put(
                            GrpcMetadata.AUTHORIZATION,
                            "Bearer " + token);
                }

                super.start(listener, headers);
            }
        };
    }
}
~~~

If no token can be retrieved, the example still initiates the RPC and the server returns **UNAUTHENTICATED**. In a production application, you can fail fast on the client to surface an earlier error. **AccessTokenProvider** should integrate with OAuth2 or your application's token-issuing system, including refresh and token expiration handling.

Create a client interceptor for the correlation ID:

~~~java
package com.example.orders.grpc;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

public final class CorrelationIdClientInterceptor
        implements ClientInterceptor {

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {

            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {

                String correlationId =
                        GrpcRequestContext.CORRELATION_ID.get();

                if (correlationId == null) {
                    correlationId =
                            headers.get(GrpcMetadata.CORRELATION_ID);
                }

                if (!CorrelationIds.isValid(correlationId)) {
                    correlationId = CorrelationIds.newId();
                }

                headers.discardAll(GrpcMetadata.CORRELATION_ID);
                headers.put(
                        GrpcMetadata.CORRELATION_ID,
                        correlationId);

                super.start(listener, headers);
            }
        };
    }
}
~~~

The precedence order is: the correlation ID currently in gRPC `Context`, then metadata supplied by the caller, and finally a newly generated UUID. Thus, when service A handles a request and calls service B, the outbound channel's client interceptor automatically reuses the ID that the server interceptor placed in `Context`.

If a client needs to preserve the same ID across multiple independent RPCs, generate the ID at the business request boundary and bind it to `Context` for the scope of those calls:

~~~java
String correlationId = CorrelationIds.newId();

io.grpc.Context.current()
        .withValue(
                GrpcRequestContext.CORRELATION_ID,
                correlationId)
        .run(() -> {
            orderStub.getOrder(request);
            // Subsequent RPCs within the same scope will reuse the ID.
        });
~~~

For tasks offloaded to another executor, wrap tasks with **Context.current().wrap(...)** or use **Context.currentContextExecutor(executor)**. Never assume context automatically propagates across every **CompletableFuture**, **@Async**, or scheduler.

## 8. Registering Interceptors in a Spring Application

To let Spring manage dependencies, declare the interceptors as beans:

~~~java
@Configuration
public class GrpcInterceptorConfiguration {

    @Bean
    AuthCorrelationServerInterceptor authCorrelationServerInterceptor(
            TokenVerifier tokenVerifier) {
        return new AuthCorrelationServerInterceptor(tokenVerifier);
    }

    @Bean
    BearerTokenClientInterceptor bearerTokenClientInterceptor(
            AccessTokenProvider tokenProvider) {
        return new BearerTokenClientInterceptor(tokenProvider);
    }

    @Bean
    CorrelationIdClientInterceptor correlationIdClientInterceptor() {
        return new CorrelationIdClientInterceptor();
    }
}
~~~

Creating beans only places them in the Spring container; verify that your starter actually registers the interceptors onto the gRPC server or channel. Registration mechanisms vary across versions and starters. Use the global server interceptor hook or server builder customizer provided by your project's version, and verify the interceptors appear in the service call chain.

At the raw `grpc-java` level, server interceptor registration looks like:

~~~java
serverBuilder.addService(
        ServerInterceptors.intercept(
                orderGrpcService,
                authCorrelationServerInterceptor));
~~~

And attaching client interceptors to a channel:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress(host, port)
        .useTransportSecurity()
        .intercept(
                bearerTokenClientInterceptor,
                correlationIdClientInterceptor)
        .build();
~~~

In a Spring application, let the starter create and manage the server/channel by wiring these beans through the starter's extension points rather than building an extra channel outside Spring's lifecycle. Verify TLS configuration on production channels; only use plaintext in controlled local test environments.

## 9. Integration Testing with In-Process gRPC

Use an in-process server/channel to test interceptors without opening network ports. The **grpc-inprocess** test dependency must match the `grpc-java` version used by your other gRPC dependencies.

Start the test server:

~~~java
String serverName = InProcessServerBuilder.generateName();

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(
                ServerInterceptors.intercept(
                        testOrderService,
                        authCorrelationServerInterceptor))
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();
~~~

Use a fake **TokenVerifier** in tests: accept a known test token and reject other values. Never use production JWTs or real secrets in unit tests.

Example fake verifier:

~~~java
TokenVerifier testTokenVerifier = token -> {
    if (!"test-token".equals(token)) {
        throw new InvalidTokenException("invalid test token");
    }
    return new AuthenticatedUser(
            "test-user",
            Set.of("orders:read"));
};
~~~

You can attach test metadata to a stub using **MetadataUtils.newAttachHeadersInterceptor(...)**:

~~~java
Metadata requestHeaders = new Metadata();
requestHeaders.put(
        GrpcMetadata.AUTHORIZATION,
        "Bearer test-token");
requestHeaders.put(
        GrpcMetadata.CORRELATION_ID,
        "test-order-001");

OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel)
                .withInterceptors(
                        MetadataUtils.newAttachHeadersInterceptor(
                                requestHeaders));
~~~

Create a test service that captures the principal and correlation ID from **GrpcRequestContext** into an **AtomicReference**. After the call, assert the captured values match the sent metadata. Add a client interceptor that captures response trailers to verify **x-correlation-id** is returned even when the RPC fails.

Your test suite should cover at least these cases:

| Case | Expected Result |
|---|---|
| Valid token and valid correlation ID | Service is invoked; Context holds the expected principal and ID |
| Missing Authorization | **UNAUTHENTICATED**; service is not invoked |
| Invalid or expired token | **UNAUTHENTICATED**; service is not invoked |
| Token verifier temporarily unavailable | **UNAVAILABLE** |
| Valid principal missing required authority | **PERMISSION_DENIED** |
| Correlation ID omitted | Server generates a UUID and returns it in response trailers |
| Correlation ID contains disallowed characters | **INVALID_ARGUMENT**, with a fresh ID in trailers |
| Service calls a downstream RPC | Client interceptor forwards the correlation ID from Context |
| Client opens a streaming RPC | Interceptor still authenticates and attaches the ID across the RPC |

Example status assertion:

~~~java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> unauthenticatedStub.getOrder(request));

assertEquals(
        Status.Code.UNAUTHENTICATED,
        error.getStatus().getCode());
~~~

Shut down the channel and server after each test or inside **@AfterEach** to avoid leaking threads and resources. In-process tests verify interceptor logic, metadata, and statuses; they do not test TLS, proxies, or HTTP/2 limits over the network. Those require dedicated integration tests using production-like transport configuration.

## 10. Troubleshooting Common Errors

**Server always returns UNAUTHENTICATED**

- Verify the client interceptor is attached to the stub's channel.
- Verify the **authorization** key name and **Bearer <token>** format.
- Verify the token provider returns an unexpired token.
- Verify **TokenVerifier** checks the expected issuer, audience, signature, and expiration.
- Confirm the server interceptor is actually registered on the service being called.

**Service cannot read the principal or correlation ID**

- Check that the interceptor invokes **Contexts.interceptCall(...)** with the new context.
- Check that the service reads the exact same shared context keys.
- If the error only happens in async tasks, check context propagation across executors.
- Do not read values from a custom `ThreadLocal` assuming it behaves like gRPC `Context`.

**Correlation ID changes between services**

- Check that the client interceptor prioritizes the active `Context` over caller-supplied metadata.
- Confirm the server interceptor writes the correlation ID into `Context` before the handler runs.
- Check that executors preserve context when the service invokes downstream calls.
- Distinguish request correlation IDs from OpenTelemetry trace IDs. When tracing is enabled, let the propagator manage **traceparent** and span context.

**Interceptors are Spring beans but never execute**

- Verify the interceptor registration extension point for the starter in use.
- Check that the right server, service definition, and channel are created by Spring.
- Add an integration test invoking via a real stub to prove the interceptor runs; checking bean existence alone is not enough.

## 11. Security and Operations

- Use TLS for client/server connections; consider mTLS when workload identity must be verified at the transport layer.
- Never trust user IDs, roles, or tenant IDs self-asserted by the client in metadata. The principal must come from a verified token or equivalent trusted source.
- Never log `Authorization` headers, tokens, secrets, or sensitive payloads.
- Do not forward the caller's raw token blindly to downstream services without an explicit delegation policy. Use service identities or token exchange per your security architecture.
- Use **UNAUTHENTICATED** for unverified identities, **PERMISSION_DENIED** for verified identities lacking permissions, **INVALID_ARGUMENT** for malformed correlation IDs, and **UNAVAILABLE** when the verification service is temporarily down.
- Never expose internal details like JWT signature failure reasons, key names, or auth provider internals to clients.
- Enforce length and character-set limits on correlation IDs; never use them as high-cardinality metric labels.
- Correlation IDs do not replace distributed tracing. When using OpenTelemetry, continue injecting/extracting trace context via the appropriate instrumentation or propagator.

Log fields should include the RPC method, status code, normalized subject, and correlation ID. Log subjects only when permitted by data policy. Use the correlation ID to locate all logs for a request across services; use trace IDs and span IDs to analyze parent-child relationships and per-operation timing.

## 12. Project Completion Criteria

- [ ] Metadata keys **authorization** and **x-correlation-id** are declared once and shared.
- [ ] Token verifier validates signatures/claims per policy and never logs tokens.
- [ ] Server interceptor rejects missing or invalid tokens with **UNAUTHENTICATED**.
- [ ] Transient verification outages map to **UNAVAILABLE**.
- [ ] Verified principal and correlation ID are placed into gRPC `Context`.
- [ ] Service enforces business permissions and never parses `Authorization` metadata directly.
- [ ] Server returns the correlation ID in response metadata or trailers.
- [ ] Client interceptors attach the Bearer token and propagate the correlation ID.
- [ ] Interceptors are registered on the right Spring gRPC server and channel.
- [ ] Tests cover valid tokens, bad tokens, missing permissions, missing/bad correlation IDs, and downstream propagation.
- [ ] TLS, safe logging, and separation between correlation IDs and trace context are verified.

When all criteria are met, every RPC is protected by a single authentication boundary, services receive verified identities via `Context`, and correlation IDs flow across calls to support incident investigation.
