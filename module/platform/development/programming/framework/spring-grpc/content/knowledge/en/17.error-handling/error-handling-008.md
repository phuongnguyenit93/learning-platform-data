# Authorization errors and UNAUTHENTICATED, PERMISSION_DENIED

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers, generated Java code, and unary or streaming RPCs. This lesson focuses on two security errors at the API boundary: **failing to authenticate identity** and **an authenticated caller lacking permission to perform the operation**.

## 1. Distinguishing authentication and authorization

These two steps answer two different questions:

- **Authentication:** Who is the caller? The server checks credentials, signatures, expiration, and issuer to establish a trusted identity.
- **Authorization:** What is that identity allowed to do on which resource? The server checks roles, scopes, permissions, tenant, and relationship to the resource.

Accordingly, the two gRPC statuses have different meanings:

| Situation | Status | Meaning |
| --- | --- | --- |
| Missing required credentials | `UNAUTHENTICATED` | The server has not established a valid identity |
| Invalid signature, expired token, or invalid issuer | `UNAUTHENTICATED` | Credentials do not prove identity |
| Valid token but missing scope/role | `PERMISSION_DENIED` | Caller is authenticated but not allowed |
| Caller has read permission but not write permission | `PERMISSION_DENIED` for write operation | Permission depends on the action |
| Caller does not belong to an allowed tenant | Usually `PERMISSION_DENIED` | Identity is valid, but access scope is not appropriate |

For example: an employee has a valid token with only order-viewing permissions. When calling the delete-order RPC, the server returns `PERMISSION_DENIED`. If the token has expired, the server returns `UNAUTHENTICATED` before checking permissions on the order.

**Do not use the two statuses interchangeably.** Returning `UNAUTHENTICATED` for an authenticated user who lacks permission can cause the client to refresh tokens fruitlessly. Returning `PERMISSION_DENIED` for an expired token leaves the client unaware it needs to re-authenticate.

## 2. Credentials are typically sent via metadata

A client typically sends an access token in metadata:

```java
Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
                "authorization",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata headers = new Metadata();
headers.put(AUTHORIZATION, "Bearer " + accessToken);

CustomerServiceGrpc.CustomerServiceBlockingStub authenticatedStub =
        MetadataUtils.attachHeaders(blockingStub, headers);

Customer customer = authenticatedStub.getCustomer(request);
```

The `authorization` metadata is an application header, not a field inside the protobuf message. It is sent per RPC. Clients should not hard-code tokens or write tokens into logs. In production systems, credentials should be attached using call credentials or an interceptor aligned with the token lifecycle so tokens refresh automatically and are never shared across users.

### Protecting credentials in transit

An access token is a bearer credential: anyone holding the token can use it with its permissions. Therefore:

- Use TLS when sending credentials over the network; do not send bearer tokens over plaintext connections.
- Do not put tokens into protobuf payloads, status descriptions, trailers, or logs.
- Do not log all metadata headers in logging interceptors.
- Verify issuer, audience, signature, expiration, and allowed algorithms; do not merely decode the token and trust its claims.
- Do not treat a client-declared user ID or role in the request as an authenticated identity.

## 3. Authenticating on the server with an interceptor

Authentication should run early, before invoking the business handler. gRPC Java provides `ServerInterceptor` to read metadata and authenticate credentials for each RPC.

The example uses a `TokenAuthenticator` abstraction to verify the token. Signature verification details depend on the identity provider, but the result must be a server-trusted principal:

```java
public record AuthenticatedPrincipal(
        String subject,
        String tenantId,
        Set<String> authorities) {}

public interface TokenAuthenticator {
    AuthenticatedPrincipal authenticate(String bearerToken)
            throws InvalidCredentialException;
}
```

The interceptor extracts the bearer token, calls the authenticator, and stores the principal in the gRPC `Context`:

```java
import io.grpc.Context;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.grpc.Contexts;

public final class AuthenticationInterceptor implements ServerInterceptor {

    public static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final TokenAuthenticator authenticator;

    public AuthenticationInterceptor(TokenAuthenticator authenticator) {
        this.authenticator = authenticator;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        String token = authorization.substring("Bearer ".length()).trim();
        if (token.isEmpty()) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Invalid credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        try {
            AuthenticatedPrincipal principal =
                    authenticator.authenticate(token);
            Context context = Context.current()
                    .withValue(PRINCIPAL, principal);
            return Contexts.interceptCall(context, call, headers, next);
        } catch (InvalidCredentialException invalid) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Invalid credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }
    }
}
```

This is an example of the authentication boundary; register the interceptor with the server/service according to the Spring gRPC configuration for the version in use. Do not write tokens or detailed authentication library exceptions to logs/descriptions. Expired tokens, invalid signatures, wrong issuers, or malformed tokens all map to `UNAUTHENTICATED`.

### Principal in Context

gRPC's `Context` binds the principal to the RPC lifecycle. Handlers can retrieve the identity verified by the interceptor:

```java
AuthenticatedPrincipal principal =
        AuthenticationInterceptor.PRINCIPAL.get();

if (principal == null) {
    // The RPC did not pass through the authentication interceptor as expected.
    throw new IllegalStateException("Authenticated principal missing");
}
```

Do not store the principal in a mutable field of a singleton Spring service. Multiple RPCs run concurrently; `Context` scopes identity data to the call instead of sharing it across requests. When offloading work to a separate executor, propagate/wrap the `Context` properly or pass the principal explicitly.

## 4. Authorization checks permissions on actions and resources

Once a principal is established, the application service or authorization component decides whether the caller has permission to perform the action. Do not check only a coarse role when permissions depend on tenant, resource owner, or business state.

Example policy:

```java
public interface TransferAuthorization {
    boolean canRead(
            AuthenticatedPrincipal principal,
            String transferId);

    boolean canCancel(
            AuthenticatedPrincipal principal,
            String transferId);
}
```

The service adapter uses the authenticated principal and returns `PERMISSION_DENIED` when the policy denies access:

```java
@GrpcService
public class TransferGrpcService
        extends TransferServiceGrpc.TransferServiceImplBase {

    private final TransferApplicationService applicationService;
    private final TransferAuthorization authorization;

    public TransferGrpcService(
            TransferApplicationService applicationService,
            TransferAuthorization authorization) {
        this.applicationService = applicationService;
        this.authorization = authorization;
    }

    @Override
    public void cancelTransfer(
            CancelTransferRequest request,
            StreamObserver<TransferResponse> responseObserver) {

        AuthenticatedPrincipal principal =
                AuthenticationInterceptor.PRINCIPAL.get();

        if (principal == null) {
            responseObserver.onError(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required")
                            .asRuntimeException());
            return;
        }

        if (!authorization.canCancel(principal, request.getTransferId())) {
            responseObserver.onError(
                    Status.PERMISSION_DENIED
                            .withDescription("Operation is not permitted")
                            .asRuntimeException());
            return;
        }

        try {
            Transfer transfer = applicationService.cancel(
                    principal.tenantId(), request.getTransferId());
            responseObserver.onNext(toProto(transfer));
            responseObserver.onCompleted();
        } catch (TransferNotFoundException missing) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Transfer not found")
                            .asRuntimeException());
        }
    }
}
```

This example illustrates checking permissions in the adapter. For complex business rules, place the policy in an application/domain authorization service to avoid duplicating logic across transports. The application service must still constrain tenant/owner in queries or updates; do not rely solely on an earlier check if a race condition is possible.

### Preventing cross-tenant access

Do not treat `tenant_id` from the protobuf request as the sole source of truth. Take the tenant from the authenticated principal, then scope the query:

```java
repository.findByIdAndTenantId(
        transferId,
        principal.tenantId());
```

If the API needs to avoid revealing whether a resource exists in another tenant, it can return `NOT_FOUND` instead of `PERMISSION_DENIED` under an anti-enumeration policy. That decision must be consistent and documented in the API contract; do not accidentally disclose resource existence through status or description.

## 5. Status on the client: refresh credentials or stop?

Clients should classify based on the status code:

| Status | Client reaction |
| --- | --- |
| `UNAUTHENTICATED` | Check session, refresh credentials per policy, and retry with a limit |
| `PERMISSION_DENIED` | Stop the operation; do not retry with the same credentials and request |
| `NOT_FOUND` | Show not found or refresh the list |
| `UNAVAILABLE` | Retry with backoff if the operation is safe |
| `DEADLINE_EXCEEDED` | Verify outcome before retrying if the RPC has side effects |

Do not auto-refresh tokens infinitely. A sound client strategy:

1. Send the RPC using the current credentials.
2. If `UNAUTHENTICATED` is received, ask the token provider to refresh once.
3. If the refresh succeeds, resend the RPC with the new credentials and a bounded attempt count.
4. If it is still `UNAUTHENTICATED`, prompt the user to sign in again or stop.
5. If `PERMISSION_DENIED` is received, do not refresh the token to try bypassing the policy; display the required permission or terminate the operation.

For write RPCs, a retry after refresh still requires an idempotency key if the first attempt could have caused side effects before the status was returned.

## 6. Testing authentication and authorization

These two test suites must be independent because they verify two different gates:

| Test case | Credentials | Permission | Expected |
| --- | --- | --- | --- |
| Missing authorization metadata | None | Undetermined | `UNAUTHENTICATED` |
| Invalid/expired token | Invalid | Undetermined | `UNAUTHENTICATED` |
| Valid token | Missing cancel permission | Insufficient | `PERMISSION_DENIED` |
| Valid token | Has cancel permission | Sufficient | RPC succeeds if business rules allow |
| Valid token in tenant A | Tenant B resource | Out of scope | Status per tenant policy, usually `PERMISSION_DENIED` or `NOT_FOUND` |

Example unit test for the policy:

```java
class TransferAuthorizationTest {

    private final TransferAuthorization authorization =
            new DefaultTransferAuthorization();

    @Test
    void viewerCannotCancelTransfer() {
        var viewer = new AuthenticatedPrincipal(
                "user-1", "tenant-A", Set.of("TRANSFER_READ"));

        assertFalse(authorization.canCancel(viewer, "transfer-9"));
    }

    @Test
    void operatorWithCancelPermissionCanCancel() {
        var operator = new AuthenticatedPrincipal(
                "user-2", "tenant-A",
                Set.of("TRANSFER_READ", "TRANSFER_CANCEL"));

        assertTrue(authorization.canCancel(operator, "transfer-9"));
    }
}
```

Integration tests via in-process gRPC should verify both the interceptor and actual statuses:

- No metadata sent: business handler is not called and client receives `UNAUTHENTICATED`.
- Fake or expired token: handler is not called and client receives `UNAUTHENTICATED`.
- Valid token lacking permission: authenticator succeeds, policy denies, and client receives `PERMISSION_DENIED`.
- Valid token with sufficient permission: handler runs with a Context containing the right principal.
- Mismatched tenant: repository returns no cross-tenant data.

Tests should not only mock `AuthenticationInterceptor.PRINCIPAL` when the goal is to test the interceptor; include integration tests sending metadata over the channel to verify credentials are processed at the right boundary.

## 7. Common implementation mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning `PERMISSION_DENIED` for expired token | Client does not know it must re-authenticate | Use `UNAUTHENTICATED` |
| Returning `UNAUTHENTICATED` when user lacks permission | Client refreshes tokens in vain | Use `PERMISSION_DENIED` |
| Trusting user/role/tenant in protobuf request | Caller can impersonate | Extract principal from verified credentials |
| Checking role only, ignoring resource/tenant | Cross-tenant data access | Enforce policy by action and resource |
| Logging all metadata | Tokens may be leaked | Redact authorization and credentials |
| Using Context like a global variable | Identities can mix across RPCs | Scope Context per call, do not store in mutable fields |
| Infinite retries on `UNAUTHENTICATED` | Refresh or request loops | Cap to one refresh and bounded retries |
| Treating TLS as a substitute for authorization | Connected users can still access unauthorized resources | TLS protects transport; policy must still check permissions |

## 8. Self-practice

1. A token has a valid signature but is expired. Why does the server return `UNAUTHENTICATED`, not `PERMISSION_DENIED`?
2. A signed-in user has read-only permission. Design the server status and client reaction when the user calls a delete-resource RPC.
3. Why must the tenant ID come from the authenticated principal instead of trusting a field in the protobuf request?
4. Write a test proving the interceptor rejects requests without a bearer token before calling the handler.
5. If a client receives `UNAUTHENTICATED` after a transaction-creating RPC, what must be ensured before refreshing the token and resending?

**Remember:** `UNAUTHENTICATED` means the server could not verify identity from credentials; `PERMISSION_DENIED` means the identity is valid but lacks permission. Authenticate credentials in an interceptor, attach the principal to the per-RPC `Context`, enforce permissions by action/resource/tenant, and never trust client-declared identity. TLS protects credentials in transit; authorization must still be enforced on the server.
