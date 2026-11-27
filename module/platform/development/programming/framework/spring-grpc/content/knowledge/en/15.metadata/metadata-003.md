# Authorization Metadata

In a microservice system using **Spring gRPC**, clients often must prove their identity or access permissions before the server processes a call. Data such as access tokens is transmitted via **request metadata**, most commonly the `authorization` header carrying a `Bearer <access-token>` value. This mechanism uses `grpc-java`'s metadata infrastructure, without needing to add tokens to every Protocol Buffers message.

The name "authorization metadata" can be misleading: **metadata only transports authentication or authorization credentials**. The presence of a header alone does not prove the caller has permission. The server must authenticate the credentials first, then check permissions for the specific method and resource.

After this lesson, you will be able to:

- Distinguish authentication and authorization in a gRPC call.
- Know how to use the ASCII metadata key `authorization` for bearer tokens, and when a different credential mechanism is needed.
- Attach authentication credentials on the client using `CallCredentials` or an interceptor.
- Validate metadata in a server interceptor, pass the authenticated identity through `io.grpc.Context`, and enforce authorization in the proper place.
- Return `UNAUTHENTICATED` or `PERMISSION_DENIED` in the right scenarios; test and protect tokens when using Spring gRPC, TLS, streaming, and inter-service calls.

## 1. Authentication and Authorization in gRPC

The two steps serve different purposes:

| Step | Question | Examples |
| --- | --- | --- |
| **Authentication** | Who is calling? Is there valid proof of identity? | Verifying JWT signature, expiration, issuer, and audience; or opaque token introspection |
| **Authorization** | Is the authenticated identity allowed to perform this action on this resource? | User A can only read their own orders; only the inventory service may update stock |

In an architecture using access tokens:

```text
Client                          gRPC Server                         Service
  |                                  |                                  |
  | -- request metadata -----------> |                                  |
  |    authorization: Bearer ...     |                                  |
  |    x-request-id: req-42          |                                  |
  |                                  |-- Verify token ----------------> |
  |                                  |   (server interceptor)           |
  |                                  |-- Attach authenticated identity -> |
  |                                  |                                  |-- Check permissions
  |                                  |                                  |   for method/resource
  | <----------- response/status --- | <--------------------------------|
```

Success flow:

1. The client obtains an access token from the established login or service identity mechanism.
2. The client places the token into `authorization` when starting the RPC.
3. The server interceptor receives request metadata, verifies the token, and creates a trusted identity context.
4. The service (or policy layer) checks permissions for the method and resource.
5. The server returns data if permitted; if failed, it returns the appropriate gRPC status.

**Example:** User `user-17`'s token is still valid and has the `orders:read` permission. The token is authenticated successfully, but if `user-17` requests an order belonging to `user-22`, the server must still deny it if the policy requires ownership. A valid token does not mean every action is valid.

## 2. What Type of Metadata Is the `authorization` Header?

`authorization` is an **ASCII metadata key**: its value is represented as a string, for example:

```text
authorization: Bearer eyJhbGciOi...
```

In `grpc-java`:

```java
import io.grpc.Metadata;

Metadata.Key<String> AUTHORIZATION =
    Metadata.Key.of(
        "authorization",
        Metadata.ASCII_STRING_MARSHALLER
    );

Metadata headers = new Metadata();
headers.put(AUTHORIZATION, "Bearer " + accessToken);
```

Here `accessToken` is a value **already obtained by the client through the application's security flow**. Do not put real tokens into source code, sample files, git, URLs, query strings, or logs. The snippet above only illustrates how to construct the header.

Some important rules:

| Rule | Practical meaning |
| --- | --- |
| Key is `authorization`, written in lowercase | Compatible with HTTP/2 header naming rules |
| Value carries `Bearer ` followed by the token | Server must parse and verify according to the agreed mechanism |
| Do not add `-bin` suffix for bearer tokens | Standard bearer tokens are ASCII strings, not raw binary metadata |
| Do not define custom keys starting with `grpc-` | This prefix is reserved for protocol metadata |
| Header belongs to the **RPC**, not Protobuf messages | Streaming RPCs do not require repeating the token on each message |
| Client-sent headers are not trusted by default | Server must validate the value and identity before granting access |

Bearer is an *authentication scheme*. The server should check the scheme case-insensitively according to HTTP authentication rules, while rejecting malformed or empty content. The application needs a clear policy if multiple `authorization` values are received for the same RPC; avoid arbitrarily picking one of them.

### When Is Binary Metadata Needed?

Some systems transmit custom byte-formatted proof of identity, such as a short binary proof defined by both endpoints. In that case, its key **must** end with `-bin` and `Metadata.BINARY_BYTE_MARSHALLER` can be used. However, switching from ASCII to binary **does not inherently increase security**: the library still transports metadata over headers/trailers, and Base64 encoding on the wire is merely a byte representation.

For HTTP-convention bearer access tokens, use ASCII `authorization`. Do not Base64-encode a token yourself and send it under a `-bin` key just to "make it safer".

## 3. Metadata and Transport-Layer Security Mechanisms

Bearer-style access tokens have a key property: **anyone possessing a valid token can attempt to use the privileges it represents**. Therefore, protecting the transport channel and processing environment is essential.

- **TLS:** Use a TLS channel for RPCs over a network. TLS protects metadata and messages across the hops covered by TLS; in architectures with a TLS-terminating proxy, also evaluate the hop from the proxy to the service.
- **mTLS:** Mutually authenticates the identities of connected endpoints, commonly used between services. mTLS and user tokens answer different questions and can be combined; do not assume mTLS proves an end user is authorized to read an order.
- **Token audience and scopes:** Only accept tokens issued for the right API/service, still within their validity period, and having appropriate permissions.
- **Logging and monitoring:** Do not log `authorization` or tokens in logs, trace attributes, error messages, or metric labels. You may log request IDs or standardized, permitted identifiers.
- **Proxy/gateway:** Clearly define which component authenticates, which component may add or strip headers, and whether downstream servers still need to verify credentials or receive an attested identity from a trusted proxy.

Metadata is not a standalone end-to-end encryption mechanism. Do not treat "having `authorization`" or "token in binary metadata" as sufficient to secure a call.

## 4. Client: Attaching a Token Using an Interceptor

To demonstrate basic `Metadata` handling, a client can attach a set of headers to a stub using `MetadataUtils.newAttachHeadersInterceptor(...)`:

```java
import io.grpc.Channel;
import io.grpc.Metadata;
import io.grpc.stub.MetadataUtils;
import java.util.concurrent.TimeUnit;

// Retrieve token from the application's credentials management mechanism.
String token = tokenProvider.getAccessToken();

Metadata.Key<String> authorizationKey =
    Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

Metadata fixedHeaders = new Metadata();
fixedHeaders.put(authorizationKey, "Bearer " + token);

OrderServiceGrpc.OrderServiceBlockingStub stub =
    OrderServiceGrpc.newBlockingStub(channel)
        .withInterceptors(
            MetadataUtils.newAttachHeadersInterceptor(fixedHeaders))
        .withDeadlineAfter(3, TimeUnit.SECONDS);

// stub.getOrder(...) will send authorization in the request headers.
```

`OrderServiceGrpc`, `channel`, and `tokenProvider` are assumed to exist in the application; service and RPC method names depend on the `.proto` contract. `withDeadlineAfter(...)` sets the deadline via the gRPC API, without manually adding `grpc-timeout`.

Attaching fixed headers is useful for minimal examples, tests, or tokens whose lifetime is managed when creating the stub. **Limitation:** if the token expires while the stub/interceptor continues using the old value, subsequent RPCs may be rejected. In real environments, prepare a mechanism to refresh or supply credentials per call.

## 5. Client: Using `CallCredentials` When Tokens Change

`io.grpc.CallCredentials` lets the client supply authentication metadata at the moment gRPC applies credentials to a call. It fits when tokens are dynamically issued or rotated. This separates token retrieval from the stub's message-handling logic.

Below is an example credentials class taking a `Supplier<String>` to fetch the current token. Fetching a token may involve I/O; `appExecutor` is provided by gRPC for credential-related work to avoid blocking transport threads:

```java
import io.grpc.CallCredentials;
import io.grpc.Metadata;
import io.grpc.Status;
import java.util.concurrent.Executor;
import java.util.function.Supplier;

public final class BearerCallCredentials extends CallCredentials {
    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    private final Supplier<String> tokenSupplier;

    public BearerCallCredentials(Supplier<String> tokenSupplier) {
        this.tokenSupplier = tokenSupplier;
    }

    @Override
    public void applyRequestMetadata(
            RequestInfo requestInfo,
            Executor appExecutor,
            MetadataApplier applier) {
        try {
            appExecutor.execute(() -> {
                try {
                    String token = tokenSupplier.get();
                    if (token == null || token.isBlank()) {
                        applier.fail(
                            Status.UNAUTHENTICATED.withDescription(
                                "Access token unavailable"));
                        return;
                    }

                    Metadata metadata = new Metadata();
                    metadata.put(AUTHORIZATION, "Bearer " + token);
                    applier.apply(metadata);
                } catch (Exception ex) {
                    // Do not include tokens or secret contents in errors.
                    applier.fail(
                        Status.UNAUTHENTICATED.withDescription(
                            "Unable to obtain access token"));
                }
            });
        } catch (RuntimeException ex) {
            applier.fail(
                Status.UNAUTHENTICATED.withDescription(
                    "Credential execution unavailable"));
        }
    }

    @Override
    public void thisUsesUnstableApi() {
        // Compatibility method for grpc-java versions that require it.
    }
}
```

Attaching it to a stub with `withCallCredentials(...)`:

```java
OrderServiceGrpc.OrderServiceBlockingStub authenticatedStub =
    OrderServiceGrpc.newBlockingStub(channel)
        .withCallCredentials(
            new BearerCallCredentials(tokenProvider::getAccessToken));
```

**Limitations of the example:** `tokenProvider` represents an application-implemented token issuance/refresh component. In production, it must manage expiration, synchronize refreshes, and avoid bottlenecks when many RPCs start simultaneously. Do not make a new login request for every single call just because `CallCredentials` is used. If your environment uses an official credentials library from an identity provider, prefer existing adapters and check compatibility with your `grpc-java` version.

With Spring gRPC, stubs/channels are typically created or configured through Spring. Attaching credentials to a stub still uses `grpc-java` APIs; apply it at the client initialization/configuration point matching the Spring gRPC version in use. If credentials depend on individual user identities, avoid attaching User A's token to a singleton stub shared with User B.

## 6. Server: Validating Tokens in a `ServerInterceptor`

On the server, a `ServerInterceptor` can read `authorization` before executing the service. The example below handles three common issues: missing header, multiple headers with the same name, and invalid token. To avoid coupling to a specific JWT provider, actual verification logic is abstracted behind `TokenVerifier`.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;

public final class AccessTokenServerInterceptor implements ServerInterceptor {
    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> SUBJECT =
        Context.key("authenticated-subject");

    private final TokenVerifier verifier;

    public AccessTokenServerInterceptor(TokenVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Iterable<String> values = headers.getAll(AUTHORIZATION);
        if (values == null) {
            return reject(call);
        }
        Iterator<String> it = values.iterator();
        if (!it.hasNext()) {
            return reject(call);
        }
        String value = it.next();
        if (it.hasNext()) { // Reject multiple competing credentials.
            return reject(call);
        }

        if (value == null || !value.regionMatches(
                true, 0, "Bearer ", 0, 7)) {
            return reject(call);
        }
        String token = value.substring(7);
        if (token.isBlank() || token.length() > 4096) {
            return reject(call);
        }

        try {
            String subject = verifier.verify(token);
            if (subject == null || subject.isBlank()) {
                return reject(call);
            }

            Context authenticatedContext =
                Context.current().withValue(SUBJECT, subject);
            return Contexts.interceptCall(
                authenticatedContext, call, headers, next);
        } catch (InvalidTokenException ex) {
            return reject(call);
        }
    }

    private static <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call) {
        call.close(
            Status.UNAUTHENTICATED.withDescription(
                "Missing or invalid credentials"),
            new Metadata());
        return new ServerCall.Listener<ReqT>() {};
    }

    public interface TokenVerifier {
        String verify(String token) throws InvalidTokenException;
    }

    public static final class InvalidTokenException extends Exception {
        public InvalidTokenException(String message) {
            super(message);
        }
    }
}
```

In this example:

- `AUTHORIZATION` has type `String` so it uses the ASCII marshaller.
- `getAll` detects duplicate headers, instead of reading only the last value with `get`.
- `TokenVerifier` must validate the token using a trusted library or security component. Never compare tokens against hardcoded strings in a real application.
- `Contexts.interceptCall(...)` passes the authenticated `subject` into the call's `io.grpc.Context` for downstream processing.
- `4096` is an **illustrative application limit**, not a fixed gRPC limit.
- The error message returned to the client is kept generic, revealing neither the token, discovered identity, signature details, nor internal validation reasons.

### What Must `TokenVerifier` Check?

For **JWTs**, the verifier typically needs to verify the signature with a trusted key, allowed algorithms, `issuer`, `audience`, `exp`/`nbf`, and other conditions per policy. Never simply Base64-decode the JWT payload and trust the claims. Verification keys and key rotation must follow a secure process. For **opaque tokens**, an introspection or token status query mechanism against the trusted issuer is required, along with timeout and network error handling.

For verification infrastructure failures (e.g., unreachable introspection service), the application needs a **fail-closed** policy and an appropriate status code for dependency failures, typically `UNAVAILABLE`; do not treat every backend failure as a forged token. The interceptor example above only illustrates the path for tokens determined to be invalid; infrastructure error handling policies must be added according to your environment.

## 7. Passing Identity via `Context` and Enforcing Authorization

Once authentication succeeds, the server knows the `subject`. However, **permissions on a resource** also depend on the method, role/scope, tenant, and specific data.

In the RPC implementation, you can read:

```java
String subject = AccessTokenServerInterceptor.SUBJECT.get();
```

Then the policy layer checks permissions, for example with this illustrative logic:

```java
// Illustrative snippet inside getOrder(request, responseObserver).
String subject = AccessTokenServerInterceptor.SUBJECT.get();
if (subject == null) {
    responseObserver.onError(
        Status.UNAUTHENTICATED
            .withDescription("Authentication required")
            .asRuntimeException());
    return;
}

if (!orderAccessPolicy.canRead(subject, request.getOrderId())) {
    responseObserver.onError(
        Status.PERMISSION_DENIED
            .withDescription("Access denied")
            .asRuntimeException());
    return;
}

// Passed authentication and authorization: proceed to fetch data and onNext/onCompleted.
```

`orderAccessPolicy` is an application authorization component that must be implemented and tested separately. Policies may combine scopes, roles, and **resource ownership**. Having `orders:read` does not automatically grant access to view all orders. Do not use client-declared `x-user-id`, `x-role`, or `x-tenant-id` as trusted permission sources; if such values are used, a trusted component must first authenticate and map them to a principal.

`io.grpc.Context` attaches context per call. If code offloads work to another executor/thread, context must be propagated via gRPC's mechanisms; otherwise `SUBJECT.get()` may no longer hold the expected value. In applications using Spring Security, gRPC's `Context` and `SecurityContextHolder` are two separate mechanisms. Only use Spring Security annotations or policies once proper identity bridging and context integration are in place; do not assume a plain interceptor automatically activates full Spring method security.

## 8. Distinguishing `UNAUTHENTICATED` and `PERMISSION_DENIED`

gRPC uses `io.grpc.Status` to express outcomes; the library transports status in trailers when finishing the RPC. Two access-related codes are easily misused:

| Scenario | Suggested gRPC status | Reason |
| --- | --- | --- |
| No token sent when the method requires authentication | `UNAUTHENTICATED` | No proof of identity provided |
| Expired token, invalid signature, wrong audience | `UNAUTHENTICATED` | Submitted credentials could not be authenticated |
| Sending two `authorization` headers violating policy | `UNAUTHENTICATED` | Credentials are not accepted |
| Valid identity but missing scope to write data | `PERMISSION_DENIED` | Caller is known, but lacks permission |
| Valid user accessing a resource they do not own | `PERMISSION_DENIED` or `NOT_FOUND` per resource-hiding policy | Choose consistently to avoid leaking data existence |
| Token verification depends on another service that is down | `UNAVAILABLE` or appropriate operational status | Infrastructure error differs from a proven invalid token |

In some APIs, the server may return `NOT_FOUND` instead of `PERMISSION_DENIED` to avoid revealing a resource's existence. This is a security and API UX decision that must remain consistent with the system's access policy.

Do not attempt to modify `grpc-status` using `Metadata.put`. End calls using `Status` or `StatusRuntimeException`. Errors sent back to the client should avoid including sensitive details, even in custom response trailers.

## 9. Integrating with Spring gRPC

Spring gRPC runs on top of `grpc-java`, so the `Metadata`, `ServerInterceptor`, `CallCredentials`, and `Status` APIs are used at the appropriate integration layer.

A typical organizational flow:

1. **Client configuration:** configure secure channels, token acquisition, and attaching `CallCredentials` to the stubs used.
2. **Server configuration:** register authentication interceptors across the scope of services needing protection.
3. **Principal mapping:** after authentication, place trusted identity info into the context used during RPC processing.
4. **Authorization policy:** enforce permissions by method, scope, and resource at the service or policy layer.
5. **Observability:** log only request IDs, gRPC status codes, and necessary non-sensitive information.

Example bean creating an interceptor:

```java
import io.grpc.ServerInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RpcSecurityConfiguration {

    @Bean
    ServerInterceptor accessTokenServerInterceptor(
            AccessTokenServerInterceptor.TokenVerifier tokenVerifier) {
        return new AccessTokenServerInterceptor(tokenVerifier);
    }
}
```

The bean above shows how to provide the interceptor's dependency using Spring. **Whether an interceptor bean is automatically applied to the server or how interceptor ordering is chosen depends on your Spring gRPC/starter version and configuration.** Register it according to your project's mechanism, then test a real RPC to confirm the interceptor executes. When having multiple authentication mechanisms or public RPCs (health checks, reflection per policy), clearly define the protection scope; do not accidentally leave a sensitive endpoint outside the interceptor chain.

Do not confuse "Spring gRPC" with a third-party starter that has similar annotations and configuration but different APIs. Keeping authentication minimally coupled to starter specifics makes testing and upgrades easier.

## 10. Token Expiration, Retries, Deadlines, and Streaming

### Token Lifecycle

Access tokens usually have an expiration time. The client should have a token management component capable of:

- Obtaining tokens from a trusted source and storing them securely per application policy.
- Refreshing when needed, while controlling concurrent refresh requests.
- Distinguishing user tokens from service-level tokens.
- Handling `UNAUTHENTICATED` responses via an appropriate authentication flow, avoiding infinite loops with an expired token.

Do not store shared tokens in global static variables if the application serves multiple identities. Do not let multiple users share a singleton stub holding one user's fixed bearer token.

### Retries and Deadlines

gRPC may retry certain cases depending on configuration and RPC nature. Authentication credentials must be applied properly to each attempt, and token refresh operations must be bounded. Do not blindly retry all `UNAUTHENTICATED` or `PERMISSION_DENIED` calls; these are typically errors requiring fixed credentials/permissions, not transient failures suitable for immediate retry.

Clients set deadlines via `withDeadlineAfter(...)` or `withDeadline(...)`. If obtaining a token is slow, the call may also exceed its deadline before completing. Ensure token acquisition has an appropriate timeout and never blocks gRPC executors or queues indefinitely.

### Streaming RPCs

For server streaming, client streaming, and bidirectional streaming, authentication metadata is sent when **initiating an RPC stream**. A new token does not automatically arrive on every message. If a token expires during a long-lived stream, server policies regarding session lifetime, token revocation, and stream duration must be clearly designed. Do not assume `authorization` is updated mid-stream via a message.

### Calling Downstream Services

When service A calls service B, do not automatically forward the user's raw token to every downstream service. A token may be bound to a specific `audience`, scope, or delegation policy. Depending on architecture, A may use a service identity, token exchange, or an on-behalf-of mechanism supported by the identity system. B must validate credentials intended specifically for **B**.

## 11. Testing Authorization Metadata

Combine unit tests for the verifier/policy with integration tests using real gRPC client/server instances. `InProcessServerBuilder` and `InProcessChannelBuilder` are useful for verifying interceptor logic without opening network ports; testing TLS, proxies, mTLS, and header size limit behavior requires an actual network environment.

| Test case | Input data | Expected result |
| --- | --- | --- |
| Missing header | Omit `authorization` | `UNAUTHENTICATED` |
| Wrong scheme | `authorization: Basic ...` when API only supports Bearer | `UNAUTHENTICATED` |
| Empty or malformed token | `authorization: Bearer ` | `UNAUTHENTICATED` |
| Duplicate header | Two `authorization` values | Rejected per illustrative policy |
| Expired token | JWT past `exp` | `UNAUTHENTICATED` |
| Invalid signature or wrong audience | Invalid simulated credentials | `UNAUTHENTICATED` |
| Valid token, missing scope | Valid identity calling restricted action | `PERMISSION_DENIED` |
| Valid token, sufficient permissions | Identity and resource match policy | RPC succeeds |
| Accessing another user's resource | User A requests User B's resource | Denied or hidden per policy |
| Two users in the same client process | Stubs/credentials separated by identity | Never sends one user's token for another |
| Network error to verifier | Introspection service unresponsive | Fail closed; appropriate operational status, no access granted |
| Logs/traces | Header containing test token | Token does not appear in logs, traces, or error trailers |
| Streaming | Token at stream initiation time | Interceptor authenticates when RPC opens; authorization enforced consistently per policy |

Example testing key creation and duplicate header detection with JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Metadata;
import java.util.Iterator;
import org.junit.jupiter.api.Test;

class AuthorizationMetadataTest {
    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    @Test
    void detectsRepeatedAuthorizationValues() {
        Metadata headers = new Metadata();
        headers.put(AUTHORIZATION, "Bearer token-A");
        headers.put(AUTHORIZATION, "Bearer token-B");

        Iterator<String> values = headers.getAll(AUTHORIZATION).iterator();
        assertTrue(values.hasNext());
        assertEquals("Bearer token-A", values.next());
        assertTrue(values.hasNext());
        assertEquals("Bearer token-B", values.next());
        assertFalse(values.hasNext());
    }
}
```

The unit test above only demonstrates `Metadata` behavior in Java. To verify the interceptor actually rejects duplicate headers, call an RPC through a server with the interceptor registered and check the gRPC status. Never use strings like `token-A`/`token-B` as real credentials.

## 12. Practical Scenario: Protecting an Order Lookup RPC

Suppose you build `OrderService.GetOrder` with Spring gRPC. Logged-in users obtain an access token; only the order owner or staff with appropriate permissions may view its details.

**Requirements:**

1. The client uses TLS, obtains a token from `tokenProvider`, and attaches it to request metadata `authorization`.
2. The server interceptor accepts only a single bearer credential, validates format, and passes the token to a trusted verifier.
3. The verifier returns the authenticated identity. If the token is invalid/expired, return `UNAUTHENTICATED`.
4. The service checks the `orders:read` permission, tenant, and ownership of `order_id`. If unauthorized, return `PERMISSION_DENIED` or `NOT_FOUND` per policy.
5. Request/response Protobuf messages carry only business data; logs record only request IDs, status, and non-sensitive fields.
6. Separately test expired tokens, missing scopes, cross-tenant access, two concurrent users, and streaming calls if supported by the API.

**Self-check questions:**

- Why does the presence of an `authorization` header not prove the client is allowed to call `GetOrder`?
- When should `UNAUTHENTICATED` be used versus `PERMISSION_DENIED`?
- Why must `audience` be verified, and why shouldn't raw tokens be forwarded to every downstream service?
- Which limitation of a fixed-token interceptor does `CallCredentials` help solve?
- Why is `io.grpc.Context` not inherently the same as Spring Security's `SecurityContextHolder`?
- Is a bearer token in binary metadata more secure than an ASCII token?

**Key takeaway:** `authorization` is a common ASCII metadata header for transmitting bearer tokens in a gRPC call. The client is responsible for sending valid credentials and protecting the transport channel; the server is responsible for verifying credentials, establishing a trusted identity, and enforcing method/resource authorization. In Spring gRPC, `CallCredentials`, `ServerInterceptor`, `Context`, TLS, and `Status` work together to implement this flow cleanly and testably.
