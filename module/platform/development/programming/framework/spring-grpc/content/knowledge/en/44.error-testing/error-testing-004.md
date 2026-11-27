# Testing UNAUTHENTICATED

In gRPC, **UNAUTHENTICATED** indicates that the server could not verify the caller's identity. With Spring gRPC, this error typically occurs when a request lacks credentials, has a malformed bearer token, an invalid signature, an expired token, or an unacceptable issuer/audience. Tests must prove that the server rejects the call before the service handler performs any business logic.

Distinguish UNAUTHENTICATED from PERMISSION_DENIED: in the first case the caller does not yet have a verified identity; in the second case the caller is authenticated but lacks permission to perform the action. This lesson uses the GetMyProfile RPC, an authentication interceptor, gRPC Context, and a generated blocking stub to test credential branches.

## 1. Authentication Precedes Authorization

The security processing flow usually follows this order:

1. The client sends credentials over TLS, typically in the authorization metadata.
2. The server interceptor verifies the credentials: signature, issuer, audience, expiry, and required claims.
3. If valid, the interceptor creates a trusted principal and attaches it to the gRPC Context.
4. The service handler reads the principal from the context.
5. The authorization policy checks permissions on the method/resource.
6. Only when authorized does the service access data or perform side effects.

| Situation | Appropriate Status |
| --- | --- |
| Missing bearer token | UNAUTHENTICATED |
| Authorization header has wrong scheme or empty token | UNAUTHENTICATED |
| Token has invalid signature, is expired, or has wrong issuer/audience | UNAUTHENTICATED |
| Valid token but lacks permission to read resource | PERMISSION_DENIED |
| Valid token and authorized, but resource does not exist | NOT_FOUND |
| Valid token, but identity provider is temporarily unavailable | UNAVAILABLE or corresponding infrastructure error |

Do not arbitrarily turn identity provider errors into UNAUTHENTICATED. Invalid credentials are an identity error; an identity provider timeout is an availability error, which may require retries according to policy and deadline.

## 2. Put the Verified Principal into the gRPC Context

The principal must be built from the result of credential verification, not by taking subject or role directly from client-supplied headers.

~~~java
import java.util.Set;

public record AuthenticatedPrincipal(
    String subject,
    String tenantId,
    Set<String> authorities) {}
~~~

Declare a shared context key between the interceptor and the service:

~~~java
import io.grpc.Context;

public final class PrincipalContext {
    public static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
        Context.key("authenticated-principal");

    private PrincipalContext() {}
}
~~~

Verifier is an application abstraction; the production implementation is responsible for checking signatures, issuer, audience, expiration, and claims per policy:

~~~java
public interface TokenVerifier {
    AuthenticatedPrincipal verify(String token)
        throws InvalidTokenException, IdentityProviderUnavailableException;
}
~~~

Do not log tokens or full sensitive claims. If using JWT, do not just decode the payload and trust its contents; you must verify the signature and required claims. If using token introspection from an identity provider, set explicit timeouts and deadlines.

## 3. Server Interceptor Rejects Invalid Credentials

The authentication interceptor inspects metadata before dispatching to the service:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class BearerAuthenticationInterceptor
        implements ServerInterceptor {

    public static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
            "authorization",
            Metadata.ASCII_STRING_MARSHALLER);

    private final TokenVerifier tokenVerifier;

    public BearerAuthenticationInterceptor(
            TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        if (authorization == null
                || !authorization.startsWith("Bearer ")) {
            return reject(call, "valid bearer credential is required");
        }

        String token = authorization.substring("Bearer ".length()).trim();
        if (token.isEmpty()) {
            return reject(call, "valid bearer credential is required");
        }

        final AuthenticatedPrincipal principal;
        try {
            principal = tokenVerifier.verify(token);
        } catch (InvalidTokenException ex) {
            return reject(call, "credential is invalid or expired");
        } catch (IdentityProviderUnavailableException ex) {
            call.close(
                Status.UNAVAILABLE.withDescription(
                    "identity provider is temporarily unavailable"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context context = Context.current().withValue(
            PrincipalContext.PRINCIPAL, principal);
        return Contexts.interceptCall(context, call, headers, next);
    }

    private <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call,
            String description) {
        call.close(
            Status.UNAUTHENTICATED.withDescription(description),
            new Metadata());
        return new ServerCall.Listener<>() {};
    }
}
~~~

The interceptor does not call next.startCall(...) when credentials are invalid, so the service handler is not executed. The error description does not reveal what is wrong with the token, which signature failed, or whether the user exists.

If the verifier makes a network call to an identity provider, do not block transport/event-loop threads inside the interceptor. Use an asynchronous authentication mechanism suited to the server integration, or verify tokens locally using cached keys. When the provider fails, return the corresponding availability status rather than pretending the caller sent invalid credentials.

## 4. Service Reads Only the Verified Principal

Example service reading the caller's profile:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public class ProfileGrpcService
        extends ProfileServiceGrpc.ProfileServiceImplBase {

    @Override
    public void getMyProfile(
            GetMyProfileRequest request,
            StreamObserver<GetMyProfileResponse> responseObserver) {

        AuthenticatedPrincipal principal =
            PrincipalContext.PRINCIPAL.get();
        if (principal == null) {
            responseObserver.onError(
                Status.UNAUTHENTICATED
                    .withDescription("authentication is required")
                    .asRuntimeException());
            return;
        }

        responseObserver.onNext(GetMyProfileResponse.newBuilder()
            .setSubject(principal.subject())
            .setTenantId(principal.tenantId())
            .build());
        responseObserver.onCompleted();
    }
}
~~~

In a Spring application, the service typically receives dependencies via constructor injection. The interceptor must be registered on the server before calls reach the service. Merely declaring an interceptor as a Spring bean does not guarantee the starter automatically applies it; use the server interceptor registration/customizer mechanism of the starter version in use.

## 5. Test Using an In-Process gRPC Server

In-process transport runs both server and client in the same JVM. It is well-suited for testing status mapping and proving the authentication interceptor blocks requests before the service handler. Interceptor/credential tests here do not verify TLS or production JWT signatures; those require dedicated integration tests.

Test client interceptor that adds a bearer token:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

final class TestBearerTokenClientInterceptor
        implements ClientInterceptor {

    private final String token;

    TestBearerTokenClientInterceptor(String token) {
        this.token = token;
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
                headers.put(
                    BearerAuthenticationInterceptor.AUTHORIZATION,
                    "Bearer " + token);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

JUnit 5 test for missing, invalid, and valid tokens:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ProfileAuthenticationTest {

    private Server server;
    private ManagedChannel channel;
    private AtomicInteger handlerCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        handlerCalls = new AtomicInteger();

        TokenVerifier verifier = token -> {
            if ("valid-token".equals(token)) {
                return new AuthenticatedPrincipal(
                    "user-42", "tenant-a", Set.of("PROFILE_READ"));
            }
            throw new InvalidTokenException();
        };

        ProfileGrpcService service = new ProfileGrpcService() {
            @Override
            public void getMyProfile(
                    GetMyProfileRequest request,
                    StreamObserver<GetMyProfileResponse> observer) {
                handlerCalls.incrementAndGet();
                super.getMyProfile(request, observer);
            }
        };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                service,
                new BearerAuthenticationInterceptor(verifier)))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void missingTokenReturnsUnauthenticatedBeforeHandler() {
        var stub = ProfileServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getMyProfile(GetMyProfileRequest.getDefaultInstance()));

        assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
        assertEquals(0, handlerCalls.get());
    }

    @Test
    void invalidTokenReturnsUnauthenticatedBeforeHandler() {
        var authenticatedChannel = ClientInterceptors.intercept(
            channel,
            new TestBearerTokenClientInterceptor("invalid-token"));
        var stub = ProfileServiceGrpc.newBlockingStub(authenticatedChannel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getMyProfile(GetMyProfileRequest.getDefaultInstance()));

        assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
        assertEquals(0, handlerCalls.get());
    }

    @Test
    void validTokenReachesHandlerWithVerifiedPrincipal() {
        var authenticatedChannel = ClientInterceptors.intercept(
            channel,
            new TestBearerTokenClientInterceptor("valid-token"));
        var stub = ProfileServiceGrpc.newBlockingStub(authenticatedChannel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);

        GetMyProfileResponse response =
            stub.getMyProfile(GetMyProfileRequest.getDefaultInstance());

        assertEquals("user-42", response.getSubject());
        assertEquals("tenant-a", response.getTenantId());
        assertEquals(1, handlerCalls.get());
    }
}
~~~

The test assumes InvalidTokenException, IdentityProviderUnavailableException, TokenVerifier, generated Protobuf classes, and the service base are declared as in the previous examples. You can use a spy/mock instead of subclassing the service if the service implementation is kept final. directExecutor() is only suitable for short, non-blocking handlers; use a dedicated executor if tests simulate I/O.

## 6. Key Assertions

An UNAUTHENTICATED test should verify:

1. **Status code:** the caller receives the exact Status.Code.UNAUTHENTICATED.
2. **Handler does not run:** a counter or mock verification shows the service was not called.
3. **No side effects:** repositories, downstream services, and event publishers are not called.
4. **Credentials are not leaked:** descriptions/logs do not contain tokens or sensitive verification details.
5. **Valid credentials still work:** a success test proves the interceptor does not reject all requests.

Simply asserting that an exception was thrown is not enough. If the service handler still runs after authentication fails, data access or side effects may have already occurred before the error was returned.

## 7. Distinguish Authentication Failures from Authorization Failures

Once the token is verified, authorization decides permissions on the resource:

| Credential | Permission | Result |
| --- | --- | --- |
| Missing/invalid/expired | Cannot be evaluated yet | UNAUTHENTICATED |
| Valid | No permission | PERMISSION_DENIED |
| Valid | Authorized, missing resource | NOT_FOUND |
| Valid | Authorized, valid resource | Success |

Do not include UNAUTHENTICATED in a general retry policy. The caller needs to obtain fresh credentials or fix identity configuration. Retrying the same expired token will not make it valid.

If the identity provider is temporarily unavailable, distinguish this error from an invalid token. You can return UNAVAILABLE and retry within limits if sufficient deadline remains; do not mark every caller's token as invalid just because the verifier is experiencing an outage.

## 8. Metadata Security and TLS

Bearer tokens are typically transmitted in the authorization metadata key. Metadata does not encrypt data on its own; only send credentials over TLS with verified certificates/hostnames. Do not use plaintext or trust-all just to make tests pass.

Principles:

- Only accept the specified scheme, such as Bearer.
- Verify signature, issuer, audience, expiry, and required claims.
- Do not trust client-supplied x-user-id, x-role, or tenant-id as the principal.
- Do not log tokens, authorization headers, or secrets in logs/tracing.
- Do not return details such as user non-existence or which byte of a signature failed to the caller.
- Limit metadata size and credential verification time.

If using mTLS, certificates can provide workload identity at the transport layer. The application still needs to map that identity to a principal and policy; a successful TLS handshake alone does not mean the caller has business permissions.

## 9. Integrating the Authentication Interceptor in Spring

You can manage the verifier and interceptor as Spring beans:

~~~java
@Configuration
public class GrpcAuthenticationConfiguration {

    @Bean
    BearerAuthenticationInterceptor bearerAuthenticationInterceptor(
            TokenVerifier tokenVerifier) {
        return new BearerAuthenticationInterceptor(tokenVerifier);
    }
}
~~~

This bean must be registered on the gRPC server using the corresponding extension point of the starter in use. Some starters provide a server interceptor customizer or interceptor list; the API and execution order vary by version. Verify that the authentication interceptor runs before the service handler and before business interceptors that require the principal.

In Spring integration tests, boot the application context and call the server over an actual channel to prove the interceptor is attached. In-process unit tests only verify interceptor/service logic when the test manually wires them together.

## 10. Recommended Test Matrix

| Scenario | Expected Status | Handler |
| --- | --- | --- |
| Missing authorization header | UNAUTHENTICATED | Does not run |
| Wrong scheme or empty token | UNAUTHENTICATED | Does not run |
| Token with invalid signature/expired | UNAUTHENTICATED | Does not run |
| Valid token | Success or proceeds to authorization | Runs |
| Valid token but missing permission | PERMISSION_DENIED | Runs up to authorization, does not run forbidden logic |
| Identity provider timeout | UNAVAILABLE or designated infrastructure status | Does not run business logic |
| Forged token in secondary metadata | Cannot elevate principal | Follows real credential |

Testing production authentication should include TLS, a real verifier or test identity provider, issuer/audience/expiry checks, and interceptor registration. Do not use a fake verifier to claim JWT signature verification or TLS configuration has been tested.

## 11. Takeaways and Self-Check

**Testing UNAUTHENTICATED** must prove that missing or invalid credentials are rejected before the service handler, the returned status is exact, and there are no side effects. Use a server interceptor to verify bearer tokens, attach the verified principal to the gRPC Context, and test with an in-process server and generated blocking stub. Add Spring integration tests for actual wiring and TLS/identity provider behavior per the deployment environment.

Self-check:

1. Why does UNAUTHENTICATED differ from PERMISSION_DENIED?
2. Which claims must be verified when using JWT?
3. Why must you not derive the principal from arbitrary metadata sent by the client?
4. How do you prove the service handler does not run when a token is missing?
5. Why should an identity provider timeout not be mapped to an invalid token?
6. Which parts of production authentication can an in-process test not prove?

Testing authentication properly ensures Spring gRPC passes only requests with verified identities into the service, keeps authorization separate, and prevents business access when credentials are invalid.
