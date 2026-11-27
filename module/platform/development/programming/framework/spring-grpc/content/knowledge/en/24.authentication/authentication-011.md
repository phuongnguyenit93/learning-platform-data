# Testing Requests Missing Credentials

In gRPC, credentials are typically sent via request metadata—for example, the `authorization` key containing a Bearer token. When a client calls a protected RPC without sending credentials, the server must reject the request at the authentication step and return **`UNAUTHENTICATED` (16)**. The test must confirm both the returned status and that the business handler was never executed.

In **SPRING_GRPC**, authentication is usually placed in a server interceptor or the starter's integrated security mechanism. Testing requests missing credentials helps catch bugs such as an unregistered interceptor, a service accidentally bypassing the interceptor, or a handler still running without a principal. This lesson focuses on requests without credentials; invalid credentials, expired tokens, and callers lacking permissions are separate cases requiring additional tests to ensure clear authentication/authorization boundaries.

## 1. Security expectations when credentials are missing

A protected RPC must make an authentication decision before business logic executes:

1. The client sends request metadata.
2. The server interceptor reads credentials from metadata.
3. If credentials are missing or blank, the interceptor closes the call with `UNAUTHENTICATED`.
4. The server does not invoke downstream interceptors or the application handler.
5. The client receives the status and can trigger login or credential acquisition per the application's flow.

For Bearer tokens, metadata typically looks like:

```text
authorization: Bearer <access-token>
```

Metadata key names are normalized to lowercase. Token values are sensitive data; never print tokens into logs, assertion messages, exception descriptions, or test reports.

## 2. Distinguishing missing credentials from other security errors

Do not collapse every security failure into a single status:

| Scenario | Typically appropriate status | Meaning |
| --- | --- | --- |
| No `authorization` metadata sent | `UNAUTHENTICATED` | Server received no identity to verify |
| Empty header value or missing Bearer credential per contract | `UNAUTHENTICATED` | No usable credential present |
| Token invalid signature, malformed, or expired | `UNAUTHENTICATED` | Credential was sent but could not be verified |
| Valid token lacking scope/role | `PERMISSION_DENIED` | Identity verified, caller lacks permission |
| Valid token with sufficient permissions | `OK` if operation succeeds | Both authentication and authorization pass |

A missing-credential test must prove the exact `UNAUTHENTICATED` status. If a test merely checks for any exception or asserts an empty response, it fails to prove the server enforces authentication properly.

## 3. Placing the credential check before the business handler

In gRPC Java, a `ServerInterceptor` can inspect metadata before passing the call to the handler. If credentials are missing, the interceptor calls `close` and skips `next.startCall`.

Minimal example interceptor:

```java
public final class RequireBearerCredentialInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
            "authorization",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        if (authorization == null || authorization.isBlank()) {
            call.close(
                Status.UNAUTHENTICATED
                    .withDescription("Missing authentication credentials"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
```

This example checks header presence to illustrate testing. In a real application, checking only for a non-blank header is not enough: the interceptor or authentication provider must verify the Bearer format, signature, issuer, audience, expiration, and required claims. Never turn an unverified token string into a principal.

The key point for the test is that the missing-credential branch closes the call before `next.startCall`. If the interceptor calls `next.startCall` before authenticating, the business handler or downstream interceptors may already have run.

## 4. Creating a fake service to detect whether the handler was invoked

Asserting only the status is not enough to prove the request was blocked before business logic. A fake service can use an `AtomicBoolean` to record whether the handler was called:

```java
public final class GreetingService
        extends GreeterGrpc.GreeterImplBase {

    private final AtomicBoolean handlerInvoked;

    public GreetingService(AtomicBoolean handlerInvoked) {
        this.handlerInvoked = handlerInvoked;
    }

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {
        handlerInvoked.set(true);
        responseObserver.onNext(
            HelloReply.newBuilder()
                .setMessage("Hello " + request.getName())
                .build());
        responseObserver.onCompleted();
    }
}
```

The classes `GreeterGrpc`, `HelloRequest`, and `HelloReply` are example types generated from a Protobuf service. In an actual module, replace them with your application's generated service and request/response types. The fake service does not need database access or external dependencies.

## 5. In-process integration test with JUnit 5

The in-process transport lets you spin up a gRPC server and client within the same JVM. Tests still flow through gRPC dispatch and interceptors without opening TCP ports or depending on an externally running server.

JUnit 5 example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MissingCredentialGrpcTest {

    private Server server;
    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;
    private AtomicBoolean handlerInvoked;

    @BeforeEach
    void setUp() throws IOException {
        handlerInvoked = new AtomicBoolean(false);
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                new GreetingService(handlerInvoked),
                new RequireBearerCredentialInterceptor()))
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
            channel.shutdownNow();
            channel.awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow();
            server.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void requestWithoutAuthorizationMetadataIsRejected() {
        HelloRequest request = HelloRequest.newBuilder()
            .setName("Alice")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.sayHello(request));

        assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
        assertFalse(handlerInvoked.get());
    }
}
```

The stub in the test must not have a metadata interceptor or `CallCredentials` attached, because the goal is to send a request without credentials. If a test fixture shares a channel configured with default credentials, the test might accidentally send a token and no longer test the missing-credential case.

### 5.1. What is the test proving?

Two critical assertions:

- `Status.Code.UNAUTHENTICATED`: the server returns the right status for a request without credentials.
- `handlerInvoked == false`: the interceptor blocked the request before the business handler ran.

If the status is right yet the handler was still invoked, the implementation may have executed side effects before rejecting, or the test may be observing the wrong handler. For write operations, add assertions that repositories/downstream mocks were not called and no records/events were created.

## 6. Registering interceptors in Spring gRPC

The in-process test above registers the interceptor directly on the service. Spring applications typically register interceptors via annotations, beans, or configuration mechanisms provided by the starter. Exact annotation names and interceptor ordering depend on the specific Spring gRPC library.

When testing a Spring application, verify that:

- The interceptor is discovered by Spring and attached to the right gRPC server.
- Every service requiring protection passes through the authentication interceptor.
- No sensitive endpoint is registered alongside while bypassing the protection layer.
- Authentication runs before interceptors/application components that require the principal.
- Requests missing credentials are blocked before the handler executes.

A unit test on the interceptor does not prove Spring registered it. Therefore, maintain at least one integration test that boots the application context and invokes the RPC through the channel the application actually provides.

## 7. Integration testing through the Spring application context

An application-level integration test can use `@SpringBootTest` to start the server, obtain the test-configured port/channel, and invoke an RPC without metadata. Illustrative structure:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ProtectedGrpcApplicationTest {

    @Test
    void protectedMethodRejectsCallWithoutCredential(
            @Autowired GreeterGrpc.GreeterBlockingStub unauthenticatedStub) {

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> unauthenticatedStub.sayHello(
                HelloRequest.newBuilder().setName("Alice").build()));

        assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
    }
}
```

This is an illustrative structure, not a built-in stub bean present in every Spring gRPC starter. Your project's test fixture needs to create a channel/stub targeting the test server and inject or supply that stub. What matters is keeping the test channel free of automatic credential attachment.

If the application uses a random port, the test should retrieve the port published by the test server rather than hardcoding a shared port. Close channels/servers in lifecycle hooks to prevent thread and port leaks across tests.

## 8. Test matrix for requests with missing or unusable credentials

A test case focused on a missing header belongs in a suite of negative authentication tests:

| Case | Expectation |
| --- | --- |
| No `authorization` metadata sent | `UNAUTHENTICATED`; handler does not run |
| Empty header sent | `UNAUTHENTICATED`; handler does not run |
| Value not matching the Bearer scheme | `UNAUTHENTICATED`; handler does not run |
| Malformed Bearer token | `UNAUTHENTICATED`; handler does not run |
| Bearer token invalid signature/issuer/audience | `UNAUTHENTICATED`; handler does not run |
| Expired token | `UNAUTHENTICATED`; handler does not run |
| Valid token missing scope | `PERMISSION_DENIED` |
| Valid token with sufficient permissions | Handler runs; status reflects business outcome |

Do not lump all of these cases into a single test. When each cause has its own test, a failure pinpoints the exact authentication or authorization layer that broke.

## 9. Ensuring the request sends no metadata

In gRPC Java, metadata is attached to a call by interceptors or `CallCredentials`. To be sure the test sends no credentials:

- Build the stub from a channel without client-side metadata interceptors.
- Do not use `CallCredentials` in missing-credential tests.
- Do not reuse a stub already configured with a Bearer token from another test.
- When using a shared test fixture, create a separate channel for the unauthenticated group.
- You may record on the server side that the authorization key was absent, without logging credential values.

A separate test may check an empty header, yet do not treat an empty header as equivalent to every malformed credential. The contract should specify how the parser handles schemes, whitespace, and multiple metadata values.

## 10. Status assertions and error details

Blocking client stubs typically throw `StatusRuntimeException` when an RPC terminates with a non-`OK` status. Tests should assert the status code first:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> stub.sayHello(request));

assertEquals(Status.Code.UNAUTHENTICATED, error.getStatus().getCode());
```

Do not assert solely on a message like "Missing authentication credentials", as phrasing or localization can change without altering the contract. If the API uses rich error details, you can assert stable detail types/reasons, yet never require the server to echo tokens, sensitive claims, or internal verification diagnostics.

Client-facing messages should be short and generic, such as "Request requires valid credentials". Server logs can record the method, reason code, trace ID, and authentication outcome without logging raw tokens.

## 11. Preventing tests from introducing security holes

Test fixtures must follow the same credential protection rules as production:

- Never commit real access tokens, private keys, or environment secrets.
- Use fake tokens or test-only signing keys.
- Never dump full metadata on assertion failures.
- Never embed tokens into test names, test display names, or CI artifacts.
- Never disable authentication globally just to make testing business handlers convenient.
- If a test bypasses an interceptor, isolate that bypass to a dedicated test fixture and never run production with that configuration.

A missing-credential test does not even need to know what a valid secret looks like. It only needs to send a request without authorization metadata and verify that the server rejects it properly.

## 12. TLS and the scope of in-process tests

The in-process transport tests gRPC dispatch and interceptors, yet it does not test the TLS handshake, certificate validation, or mTLS. Therefore:

- Use in-process tests to verify status codes and interceptor ordering.
- Use integration tests with a TLS transport to verify server certificates and client trust configuration.
- If the system requires mTLS, test missing client certificates separately at the transport handshake layer.
- Distinguish client certificates at the TLS layer from Bearer credentials in application metadata.

TLS protects the channel and verifies the server (or client in mTLS); it does not automatically replace application-layer authorization rules. A request with valid TLS can still be missing a required Bearer token per the RPC contract.

## 13. Common testing mistakes

| Mistake | Consequence | Better approach |
| --- | --- | --- |
| Asserting only that an exception was thrown | Fails to prove the right status | Assert `UNAUTHENTICATED` |
| Not checking the handler | Request may still have executed business logic | Use a spy/flag and assert the handler was not called |
| Stub attaches a default token automatically | Test no longer exercises missing credentials | Use a channel/stub without metadata credentials |
| Unit-testing only the interceptor | Misses Spring wiring/registration errors | Add an integration test through the application context |
| Using `PERMISSION_DENIED` for absent credentials | Conflates authentication with authorization | Return `UNAUTHENTICATED` |
| Asserting exact grpc-message text | Brittle tests when wording changes | Assert status code and structured details |
| Logging full request metadata | Can leak tokens | Log only safe keys/reasons, redact credentials |
| Using in-process tests to claim TLS is configured | Never tests handshake or certificates | Maintain dedicated TLS/mTLS transport tests |

## 14. Checklist for completing missing-credential tests

Before considering authentication tests complete, verify:

1. **Right RPC protected:** the test targets a method requiring authentication.
2. **No real credentials:** the stub has no metadata interceptor or `CallCredentials` attached.
3. **Server interceptor registered:** the test traverses the actual pipeline in use.
4. **Exact status:** the response is `UNAUTHENTICATED` (16).
5. **Handler skipped:** no business side effects or downstream invocations occur.
6. **Authentication separated from authorization:** valid token lacking permissions is tested separately with `PERMISSION_DENIED`.
7. **Safe messages:** no leaked tokens, claims, keys, or verification internals.
8. **Spring wiring verified:** an integration test boots the application context if Spring registers the interceptor.
9. **Transport security tested separately:** in-process tests do not substitute for TLS/mTLS tests.
10. **Independent tests:** no reliance on execution order or channels carrying credentials from prior tests.

## 15. Key takeaway

A request calling a protected RPC without sending credentials must be rejected with `UNAUTHENTICATED` (16) before the business handler runs. A solid test proves both things at once: the returned status is accurate and the handler was never invoked. In-process gRPC tests verify dispatch and interceptors; Spring application context integration tests verify real registration wiring. TLS/mTLS requires separate testing because the in-process transport performs no handshake.

In Spring gRPC, place authentication in an interceptor or security integration registered consistently across protected services. Never confuse missing/invalid credentials with an authenticated caller lacking permission (`PERMISSION_DENIED`). Keep tokens out of logs and test output, assert status codes rather than fragile messages, and check side effects via spies or repository assertions. These checks ensure unauthenticated requests can never reach business logic.

### References

- [gRPC – Authentication](https://grpc.io/docs/guides/auth/)
- [gRPC Java – Interceptors](https://grpc.io/docs/languages/java/interceptors/)
- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [JUnit 5 – User guide](https://junit.org/junit5/docs/current/user-guide/)
- [Spring Security – Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html)
