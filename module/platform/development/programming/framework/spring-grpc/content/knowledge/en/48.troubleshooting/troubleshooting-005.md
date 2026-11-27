# UNAUTHENTICATED Due to Missing Metadata

In **SPRING_GRPC**, clients typically send authentication credentials in gRPC Metadata, most commonly the authorization header containing a Bearer access token. A server interceptor reads the header, verifies the token, and only allows the request to proceed when the credentials are valid. If metadata is not sent, uses the wrong key/format, or gets stripped in transit, the server can return UNAUTHENTICATED.

When troubleshooting this error, trace the entire path of the credential: the client's token provider, the mechanism attaching metadata to each RPC, the actual channel/stub invoked, the server interceptor, and any intermediary proxy/gateway. This guide focuses on missing authentication metadata errors in Spring gRPC, how to distinguish them from authorization errors, and how to test both missing and valid credential cases.

## 1. Authentication Metadata in gRPC

gRPC Metadata is a set of key-value pairs accompanying an RPC as HTTP/2 headers or trailers. Authentication metadata is normally sent in request headers:

```text
authorization: Bearer <access-token>
```

Metadata key names must be lowercase ASCII. Use the authorization key and Metadata.ASCII_STRING_MARSHALLER for text-based Bearer tokens:

```java
public final class GrpcAuthMetadata {

    private GrpcAuthMetadata() {
    }

    public static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);
}
```

The metadata key is part of the transport contract. Mistakes such as using a custom auth-token key while the server only reads authorization, using the wrong binary marshaller type, or failing to attach the header to the actual RPC can all cause the server to treat the credential as missing.

Do not send tokens inside the protobuf request body. Use authentication metadata and protect the connection with TLS so credentials cannot be read in transit.

## 2. Distinguish UNAUTHENTICATED from PERMISSION_DENIED

These two statuses represent two distinct stages:

| Status | Meaning | Example |
| --- | --- | --- |
| UNAUTHENTICATED | Server cannot verify the caller's identity | Missing token, invalid signature, expired, or malformed |
| PERMISSION_DENIED | Caller is authenticated but lacks permission for the action | Valid principal without the inventory:reserve permission |

If authentication metadata is missing, the server lacks credentials to verify identity and therefore typically returns UNAUTHENTICATED. Do not return PERMISSION_DENIED for this case because the client has not passed authentication yet.

Conversely, do not use UNAUTHENTICATED to mask all authorization failures. When the token is valid yet the principal is not allowed to invoke the method, return PERMISSION_DENIED. Keeping semantics consistent helps clients know when to log in/refresh credentials and when to request permissions.

## 3. Reasons Metadata Goes Missing

| Cause | Symptom | How to Check |
| --- | --- | --- |
| Client does not attach credentials | Every RPC from the client lacks the header | Check CallCredentials or client interceptor |
| Header attached to a different channel/stub | Some calls have the token, others do not | Inspect the exact stub used to make the call |
| Wrong metadata key | Client sends auth-token, server reads authorization | Standardize on a shared key |
| Wrong format | Header lacks the Bearer prefix | Verify format before calling |
| Token provider returns empty/expired | Error appears after refresh or when token cache expires | Inspect token lifecycle without logging token values |
| Server interceptor not registered | Service runs without the expected authentication step | Check interceptor registration |
| Proxy/gateway strips header | Client sends it properly yet server does not receive it | Check request header allowlist on the proxy |
| Downstream RPC lacks credentials | Inbound request has auth yet subsequent call lacks it | Configure separate credentials for downstream |

Do not conclude the server has a bug from the status alone. Confirm the client sent the metadata, the server interceptor ran, and the request reached the right backend before modifying authentication policy.

## 4. Attach Tokens on the Client Using CallCredentials

CallCredentials is suited for attaching credentials per RPC. It allows fetching a fresh token from a provider rather than holding a static token in channel metadata.

```java
import io.grpc.CallCredentials;
import io.grpc.Metadata;
import io.grpc.Status;

import java.util.concurrent.Executor;

public final class BearerTokenCredentials extends CallCredentials {

    private final AccessTokenProvider tokenProvider;

    public BearerTokenCredentials(AccessTokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public void applyRequestMetadata(
            RequestInfo requestInfo,
            Executor appExecutor,
            MetadataApplier applier) {

        appExecutor.execute(() -> {
            try {
                String token = tokenProvider.currentAccessToken();

                if (token == null || token.isBlank()) {
                    applier.fail(Status.UNAUTHENTICATED
                            .withDescription("Authentication credentials unavailable"));
                    return;
                }

                Metadata headers = new Metadata();
                headers.put(
                        GrpcAuthMetadata.AUTHORIZATION,
                        "Bearer " + token);

                applier.apply(headers);
            } catch (CredentialUnavailableException error) {
                applier.fail(Status.UNAVAILABLE
                        .withDescription("Credential provider unavailable"));
            } catch (RuntimeException error) {
                applier.fail(Status.UNAUTHENTICATED
                        .withDescription("Authentication credentials unavailable"));
            }
        });
    }
}
```

AccessTokenProvider should return a valid token from cache or refresh it according to your application's security mechanism. Do not perform arbitrary blocking network refreshes on the RPC calling thread; use an appropriate executor and timeout. If the token provider is temporarily unreachable, UNAVAILABLE reflects a dependency failure better than assuming the caller's token is invalid.

Attach credentials to the stub:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("inventory.internal:9090")
        .useTransportSecurity()
        .build();

CatalogServiceGrpc.CatalogServiceBlockingStub client =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withCallCredentials(
                        new BearerTokenCredentials(tokenProvider));
```

withCallCredentials returns a new stub. Make sure to use the exact stub with credentials attached when calling RPCs; if you keep the old stub and call through it, metadata will not be added.

CallCredentials APIs may vary slightly across grpc-java versions. Use the same library version as the Spring gRPC runtime and check the API signatures in your build dependencies.

## 5. Client Interceptors and Static Metadata

A client interceptor can also attach metadata:

```java
public final class StaticAuthInterceptor
        implements ClientInterceptor {

    private final String token;

    public StaticAuthInterceptor(String token) {
        this.token = token;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {
                headers.put(
                        GrpcAuthMetadata.AUTHORIZATION,
                        "Bearer " + token);
                super.start(listener, headers);
            }
        };
    }
}
```

This approach can be useful for integration tests or fixed credentials in internal environments. For short-lived access tokens, multi-user scenarios, or tokens requiring refresh, do not hold a token in an interceptor field long-term: the token can expire and multiple callers could accidentally share credentials. Prefer CallCredentials or an appropriate security integration mechanism.

Do not log token values when debugging interceptors. Only log whether metadata was attached and the necessary RPC method; redact all authorization values completely.

## 6. Server Interceptor Verifying a Bearer Token

The server interceptor reads metadata before invoking the service implementation. The example below uses a TokenVerifier to verify signature, issuer, audience, and expiry; verification details depend on your identity provider system.

```java
public final class AuthenticationInterceptor
        implements ServerInterceptor {

    public static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private final TokenVerifier tokenVerifier;

    public AuthenticationInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization =
                headers.get(GrpcAuthMetadata.AUTHORIZATION);

        if (authorization == null
                || !authorization.startsWith("Bearer ")
                || authorization.length() <= "Bearer ".length()) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        String token = authorization.substring("Bearer ".length());

        try {
            AuthenticatedPrincipal principal =
                    tokenVerifier.verify(token);

            Context context = Context.current()
                    .withValue(PRINCIPAL, principal);

            return Contexts.interceptCall(
                    context, call, headers, next);
        } catch (InvalidCredentialException error) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Invalid authentication credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }
    }
}
```

The interceptor only calls next after verification succeeds. When metadata is missing or credentials are invalid, the call is closed with status UNAUTHENTICATED; the service implementation is never executed.

Principal should be an immutable object containing only necessary claims. Do not store the raw token in Context, and do not include tokens in exceptions or logs. Application use cases should receive the verified principal/actor through an application context or explicit parameter, rather than depending directly on gRPC APIs.

## 7. Register the Interceptor in Spring gRPC

Having the right interceptor class without registering it on the server means authentication will not run. With Spring gRPC, use the server interceptor registration mechanism supported by your project's dependency version.

Check:

- AuthenticationInterceptor is created as a Spring bean.
- The bean is registered globally or per service according to policy.
- The interceptor applies to the right gRPC server and port.
- No profile/condition excludes the interceptor in the running environment.
- The authentication interceptor runs before adapter logic that needs the principal.
- No other configuration accidentally replaces or skips the interceptor.

If only protecting a group of services, register within that scope and test each service/method. If all RPCs require authentication, use a global policy and exclude only health/reflection endpoints per explicit rules. Do not leave a sensitive service unprotected simply because it sits outside component scan.

Annotation names/interceptor registration mechanisms may differ across Spring gRPC lines and starters. Look up your application's exact dependency version; do not copy annotations from another starter without verifying.

## 8. TLS Protects Credentials in Transit

A Bearer token is a credential that can be reused until it expires or is revoked. Therefore, sending tokens over plaintext transport can expose caller identity.

Production clients should configure TLS:

- Use useTransportSecurity or the corresponding TLS configuration.
- Verify the server certificate and hostname.
- Use appropriate CA trust; do not disable certificate validation to "fix" authentication errors.
- With mTLS, manage client certificates/keys separately and define clearly how certificate identity combines with Bearer tokens.
- Do not put tokens in URLs, logs, protobuf payloads, or exception messages.

TLS protects data in transit; it does not replace token validation or authorization. The server must still verify issuer, signature, audience, expiry, and claims according to policy.

## 9. Metadata When Calling Downstream Services

Inbound metadata is not automatically propagated to an outbound gRPC call. If a service receives an authenticated request and then calls another service, decide explicitly which identity is used downstream:

1. **Service identity**: downstream authenticates the current service itself using the workload's credentials.
2. **Delegated user identity**: the service forwards caller identity via a designed token exchange/delegation mechanism.
3. **On-behalf-of token**: the identity provider issues a new token with audience and scope tailored to the downstream service.

Do not blindly copy all inbound metadata to downstream calls. A raw token may not match the audience, scope, or trust boundary. Do not forward authorization if downstream requires its own service identity. Each downstream client must attach credentials matching its policy and endpoint.

If the server interceptor places the principal in gRPC Context, that Context is only in-process state. When calling downstream, the adapter/client must explicitly translate permitted information into new credentials or metadata.

## 10. Test the Server Interceptor When Metadata Is Missing

You can test the server interceptor over the in-process transport. Create a simple service and protect it with the interceptor:

```java
ServerServiceDefinition protectedService =
        ServerInterceptors.intercept(
                new CatalogGrpcService(getItemUseCase, mapper),
                authenticationInterceptor);

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(protectedService)
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

try {
    CatalogServiceGrpc.CatalogServiceBlockingStub client =
            CatalogServiceGrpc.newBlockingStub(channel);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> client.getItem(
                    GetItemRequest.newBuilder()
                            .setItemId("item-42")
                            .build()));

    assertEquals(
            Status.Code.UNAUTHENTICATED,
            Status.fromThrowable(error).getCode());
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(2, TimeUnit.SECONDS);
    server.awaitTermination(2, TimeUnit.SECONDS);
}
```

This test proves that when the client does not attach metadata, the interceptor blocks the call before the service. You can add an assertion that getItemUseCase was not invoked to confirm the request never reached the application layer.

## 11. Test Valid Credentials and Invalid Tokens

A positive test uses mock valid credentials:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub authenticatedClient =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withCallCredentials(
                        new TestBearerCredentials("valid-test-token"));

GetItemReply reply = authenticatedClient.getItem(
        GetItemRequest.newBuilder()
                .setItemId("item-42")
                .build());

assertEquals("item-42", reply.getItemId());
verify(tokenVerifier).verify("valid-test-token");
```

TestBearerCredentials can be a small CallCredentials implementation that only attaches the test token to authorization. Do not use production tokens in tests.

Add negative cases:

- Missing header → UNAUTHENTICATED.
- Header missing Bearer prefix or empty token → UNAUTHENTICATED.
- Expired/bad-signature/wrong-issuer token → UNAUTHENTICATED.
- Valid token lacking scope/role → PERMISSION_DENIED.
- Token provider temporarily unreachable → status reflects dependency error, typically UNAVAILABLE.

Verify that the verifier is not called when the header is missing or malformed. With a valid token lacking permissions, the authentication interceptor can place the principal into Context; the authorization policy in an interceptor/use case will return PERMISSION_DENIED.

## 12. Troubleshooting Sequence When Receiving UNAUTHENTICATED

Follow this sequence to isolate where metadata is missing:

1. Confirm the RPC calls the right channel and endpoint.
2. Check whether the actual client stub has CallCredentials or an interceptor attached.
3. Confirm the token provider returns a non-empty, valid token without logging the token.
4. Check that the metadata key is authorization and the format is Bearer <token>.
5. Confirm the interceptor is registered on the right server/service.
6. Check whether the server receives the header using safe instrumentation that only logs present/absent status.
7. If passing through a proxy/gateway, check request header allowlists and authorization forwarding policies.
8. Verify token issuer, audience, signature, expiry, and clock skew.
9. If the error occurs downstream, check whether the outbound client has its own credentials attached.
10. Run in-process tests for missing token, valid token, and invalid token to verify expected behavior.

Do not log token values or dump full metadata to diagnose. Use request ID, RPC method, status code, and an authorization_present flag to trace.

## 13. Common Mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Using key auth-token in client while server reads authorization | Server treats credentials as missing | Use a unified metadata key |
| Attaching credentials to a different stub | Actual RPC lacks the header | Call using the stub returned by withCallCredentials |
| Holding a static token long-term | Token expires while interceptor keeps sending the old token | Use token provider and CallCredentials per RPC |
| Interceptor not registered | Expected authentication step never runs | Check server registration and startup config |
| Wrong Bearer prefix | Server cannot parse credentials | Standardize the format |
| Proxy strips authorization | Client sends it yet server never receives it | Configure controlled header allowlist/forwarding |
| Forwarding raw token downstream | Wrong audience or crosses trust boundary | Use service identity or token exchange |
| Logging token values | Leaks reusable credentials | Completely redact header values |
| Returning PERMISSION_DENIED when token is missing | Client receives wrong semantics | Return UNAUTHENTICATED |
| Disabling TLS for quick testing | Credentials may be exposed on the network | Use test tokens and TLS test configuration |

## 14. Practice Exercises

1. Declare Metadata.Key<String> for authorization with an ASCII marshaller.
2. Write BearerTokenCredentials attaching tokens per RPC.
3. Create a ServerInterceptor that checks the Bearer prefix and verifies the token.
4. Place the authenticated principal in gRPC Context without storing the raw token.
5. Register the interceptor in the Spring gRPC server and verify the bean is created.
6. Write an in-process test with no metadata and assert UNAUTHENTICATED.
7. Write a positive test with a valid token and verify the use case is invoked.
8. Write tests for invalid/expired tokens and for a valid principal lacking permissions returning PERMISSION_DENIED.
9. Check downstream calls using service credentials or delegated tokens per policy.
10. Verify TLS is enabled and logs contain no authorization values.

### Remember

**UNAUTHENTICATED due to missing metadata usually lies along the credential path between client and server.** Check CallCredentials/interceptors, the exact stub, the authorization key, Bearer format, server interceptor registration, and proxy forwarding. Distinguish missing/invalid credentials from a valid principal lacking permissions; protect tokens with TLS, never log secrets, and verify with in-process tests for both negative and positive paths.

## References

- [gRPC — Authentication](https://grpc.io/docs/guides/auth/)
- [gRPC — Metadata](https://grpc.io/docs/guides/metadata/)
- [gRPC Java — CallCredentials](https://grpc.github.io/grpc-java/javadoc/io/grpc/CallCredentials.html)
- [gRPC Java — ServerInterceptor](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerInterceptor.html)
- [gRPC Java — Metadata](https://grpc.github.io/grpc-java/javadoc/io/grpc/Metadata.html)
- [Spring gRPC — Server](https://docs.spring.io/spring-grpc/reference/server.html)
