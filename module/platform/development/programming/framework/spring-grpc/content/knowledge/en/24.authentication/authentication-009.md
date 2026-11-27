# Distinguishing Authentication and Authorization

## 1. Two distinct security questions

In **Spring gRPC**, authentication and authorization often appear in the same request yet answer two separate questions:

- **Authentication:** who is the request coming from? The system verifies credentials to establish the identity of the calling user or service.
- **Authorization:** what is that identity allowed to do on which resource? The system evaluates permissions and policies before allowing the operation.

For example, a valid access token may authenticate the caller as an employee belonging to tenant-17. That does not mean this person is allowed to read every order in the tenant. Authorization must still check roles, method permissions, and access rights on the exact requested order.

An RPC should only enter business logic after the identity has been authenticated and the required permissions have been checked at the right scope.

## 2. Comparing authentication and authorization

| Criterion | Authentication | Authorization |
| --- | --- | --- |
| Question | Who is calling? | Which actions are permitted? |
| Input | Certificate, bearer token, API key, or other credential | Authenticated principal, permissions, resource, and policy |
| Output | Verified identity/principal or rejection | Allow or deny the operation |
| Timing | Usually at the start of the RPC, before business processing | At the method boundary and/or inside the service once the resource is known |
| Example | Verifying a JWT signature and token expiration | Checking whether the principal has orders:read permission on a specific order |
| gRPC status on failure | Typically UNAUTHENTICATED | Typically PERMISSION_DENIED |

The two steps are related but do not replace each other. A valid token does not automatically grant all permissions; even a user with the ADMIN role must still prove their identity before the system trusts that role.

## 3. Processing flow in Spring gRPC

~~~mermaid
sequenceDiagram
    participant C as gRPC Client
    participant T as TLS / mTLS
    participant A as Authentication interceptor
    participant Z as Authorization policy
    participant S as Spring gRPC service
    participant D as Database
    C->>T: RPC + credential metadata
    T->>T: Verify channel and certificate if using mTLS
    T->>A: Request passed transport security
    A->>A: Verify token / credential
    A->>Z: Authenticated principal
    Z->>Z: Check method permission
    Z->>S: Allow to proceed
    S->>D: Check resource permission and read data
    D-->>S: Result within permitted scope
    S-->>C: Response
~~~

TLS protects the transport channel; authentication establishes the principal; authorization decides whether the principal is allowed to execute the RPC and act on the resource.

For some methods, authorization in an interceptor can reject immediately based on method invocation permissions. For data-dependent permissions such as order ownership, the service must check after resolving the resource but before returning data or causing side effects.

## 4. Authentication: verifying identity

Common mechanisms in gRPC:

### 4.1. TLS and mutual TLS

- TLS authenticates the server to the client and provides encryption and integrity protection in transit.
- Mutual TLS (mTLS) requires the client to also present a certificate so the server can verify the workload/peer identity.
- A certificate can identify a service such as inventory-service, well suited for service-to-service authentication.

mTLS does not authenticate the end user acting through that service. A gateway may hold a valid certificate yet still require a delegated user token or identity to execute requests on the user's behalf.

### 4.2. Bearer token in gRPC metadata

Clients typically send an access token in metadata:

~~~text
authorization: Bearer <access-token>
~~~

The server must verify at least:

- Token signature using a trusted key.
- Issuer (iss) matching the issuing system.
- Audience (aud) matching the receiving service.
- Validity window (exp, and nbf if present).
- Subject (sub) and required claims having valid structure.
- Scopes/roles issued by a trusted source, not claims self-supplied by the client.

Do not merely decode a JWT and trust its payload. Decoding does not verify the signature. For opaque tokens, introspection or a verification mechanism through the authorization server is needed per system design.

### 4.3. API keys and other credentials

API keys can identify an application or integration client, yet they usually do not fully represent end users and should not replace an identity system with revocation, expiration, scopes, and auditing. If using API keys, store them securely, support rotation/revocation, and enforce clear permission boundaries.

## 5. Authorization: evaluating permissions

After authentication, the server has a trusted principal. Authorization uses that principal to decide:

- Is the principal allowed to invoke this RPC?
- Is the principal allowed to operate on the specified tenant or resource?
- Is the action read, create, update, delete, or approve?
- Does permission depend on resource state, ownership, or business conditions?

Three common ways to structure policies:

| Model | Example | Best suited for |
| --- | --- | --- |
| Role-based access control (RBAC) | ORDER_ADMIN is allowed to manage orders | Permissions relatively stable by role |
| Scope/permission-based | orders:read, orders:write | APIs/services with explicit operational permissions |
| Attribute/resource-based (ABAC) | Only the order creator or regional manager may read it | Permissions depending on principal, resource, and context |

Real-world applications often combine models. For example, the orders:read scope permits calling the read operation, and then ABAC checks whether the principal is allowed to read orders in the specific tenant and assigned region.

## 6. Distinguishing UNAUTHENTICATED and PERMISSION_DENIED

Both statuses must be used consistently:

| Scenario | Typical status | Meaning |
| --- | --- | --- |
| Missing required bearer token | UNAUTHENTICATED | Identity has not been established |
| Token invalid signature, expired, or wrong audience | UNAUTHENTICATED | Credentials invalid for the service |
| Untrusted client certificate | TLS handshake error or transport rejection | Peer identity could not be established |
| Valid token missing required scope | PERMISSION_DENIED | Authenticated but insufficient permissions |
| Principal does not own resource | PERMISSION_DENIED or NOT_FOUND per anti-enumeration policy | Valid identity but forbidden from access |
| Principal authorized | OK if processing succeeds | Authorization permitted |

NOT_FOUND is sometimes returned instead of PERMISSION_DENIED to avoid leaking whether a resource exists. This is an API/security policy choice that must be standardized; do not vary statuses arbitrarily across equivalent methods.

Do not return UNAUTHENTICATED for every security error. When credentials are valid but lack permissions, PERMISSION_DENIED helps clients and telemetry distinguish the true cause.

## 7. Placing authentication in a ServerInterceptor

A server interceptor is the right place to verify credentials uniformly across many RPCs. When the token is valid, construct a principal and place it in gRPC Context so the service and subsequent interceptors can read it.

Illustrative example with an application TokenVerifier:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class AuthenticationInterceptor
        implements ServerInterceptor {

    static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final TokenVerifier tokenVerifier;

    public AuthenticationInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        if (authorization == null
                || !authorization.startsWith("Bearer ")
                || authorization.length() <= "Bearer ".length()) {
            call.close(Status.UNAUTHENTICATED
                    .withDescription("Missing or invalid credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        AuthenticatedPrincipal principal;
        try {
            String token = authorization.substring("Bearer ".length());
            principal = tokenVerifier.verify(token);
        } catch (InvalidCredentialException error) {
            call.close(Status.UNAUTHENTICATED
                    .withDescription("Missing or invalid credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context authenticated = Context.current()
                .withValue(PRINCIPAL, principal);
        return Contexts.interceptCall(
                authenticated, call, headers, next);
    }
}
~~~

TokenVerifier must verify signature/issuer/audience/expiry or perform introspection depending on the token type. AuthenticatedPrincipal is an application data type holding the verified subject, tenant, and permissions; never take these fields directly from the request body.

The interceptor should never log tokens or return internal details such as signature mismatches to the caller. Internal logs may record a safe categorized reason containing no credentials.

## 8. Authorization at the method boundary

For permissions applying to an entire RPC, a subsequent interceptor can enforce policy based on the full method name:

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class MethodAuthorizationInterceptor
        implements ServerInterceptor {

    private final MethodPermissionPolicy policy;
    private final AuthorizationService authorization;

    public MethodAuthorizationInterceptor(
            MethodPermissionPolicy policy,
            AuthorizationService authorization) {
        this.policy = policy;
        this.authorization = authorization;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        AuthenticatedPrincipal principal =
                AuthenticationInterceptor.PRINCIPAL.get();
        String method = call.getMethodDescriptor().getFullMethodName();
        Permission required = policy.requiredPermission(method);

        if (principal == null
                || required == null
                || !authorization.hasPermission(principal, required)) {
            call.close(Status.PERMISSION_DENIED
                    .withDescription("Permission denied"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

Register the authentication interceptor before the method authorization interceptor so the principal is already present in Context when the policy runs. Exact interceptor ordering can depend on how the server/Spring gRPC is configured; verify the actual chain in your version.

Policies should fail closed: every protected method must have an explicit permission mapping. If a method lacks a mapping, deny it rather than allowing by default. Public RPCs should be explicitly declared in a dedicated policy.

Not all permissions can be checked in an interceptor. A method interceptor knows the RPC name, yet usually does not know the order ID, owner, or business state inside the request message. Those permissions must be enforced inside the application service.

## 9. Resource-level authorization in the service

For instance, a caller holds the orders:read scope, yet may only read orders belonging to their own tenant or assigned region. The service must obtain the principal from Context and query resources within the permitted scope:

~~~java
import io.grpc.Status;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final AuthorizationService authorization;

    public OrderApplicationService(
            OrderRepository orders,
            AuthorizationService authorization) {
        this.orders = orders;
        this.authorization = authorization;
    }

    @Transactional(readOnly = true)
    public Order getOrder(String orderId) {
        AuthenticatedPrincipal principal =
                AuthenticationInterceptor.PRINCIPAL.get();
        if (principal == null) {
            throw Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException();
        }

        authorization.requirePermission(principal, "orders:read");

        Order order = orders.findByIdAndTenantId(
                        orderId, principal.tenantId())
                .orElseThrow(() -> Status.NOT_FOUND
                        .withDescription("Order not found")
                        .asRuntimeException());

        authorization.requireCanReadOrder(principal, order);
        return order;
    }
}
~~~

findByIdAndTenantId() scopes the query to the authenticated tenant rather than trusting a client-supplied tenant_id. If a user legitimately has cross-tenant access by business rule, the policy must verify that relationship explicitly.

Permission checks should occur within the same transaction or conditional query to reduce races between checking permissions and accessing the resource. For write operations, check permissions before side effects and consider embedding authorization predicates directly in update/delete statements.

## 10. Attaching credentials from the client

Clients should use gRPC's credential mechanism such as CallCredentials to attach bearer tokens per call. Tokens should be fetched from a secure credential source, refreshed upon expiry, and never hardcoded in source code.

Example usage of an application-provided CallCredentials implementation:

~~~java
import java.util.concurrent.TimeUnit;
import com.example.catalog.v1.CatalogServiceGrpc;
import com.example.catalog.v1.GetItemRequest;
import com.example.catalog.v1.GetItemResponse;

CatalogServiceGrpc.CatalogServiceBlockingStub authenticatedStub =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withCallCredentials(
                        new BearerTokenCallCredentials(tokenProvider));

GetItemResponse response = authenticatedStub
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .getItem(request);
~~~

BearerTokenCallCredentials and tokenProvider are application components; the implementation must build authorization metadata for the call, handle refresh/errors, and avoid sharing unsafe mutable token state across concurrent requests.

Do not pass tokens in Protobuf requests, query strings, or logs. Metadata is also sensitive data: configure tracing/proxies/logging not to record the authorization header. Always use TLS when sending bearer tokens over a network.

## 11. Combining mTLS and tokens

In service-to-service communication, both mTLS and bearer tokens can be used together:

| Layer | Verified identity | Purpose |
| --- | --- | --- |
| mTLS | Workload/service peer via client certificate | Confirms the service connecting to the server is a trusted workload |
| Bearer token | User or service principal per issuer/audience | Identifies the caller subject and scopes of the request |
| Authorization policy | Principal + method + resource | Decides what the request is permitted to do |

For example, a gateway holds a valid certificate to connect to order-service while forwarding the user's access token. Order service verifies both the peer identity under its trust policy and the user token, then checks whether the user is permitted to read the specific order.

If the gateway calls a service on a user's behalf using a service token, a trustworthy delegation/token-exchange mechanism is needed to carry actor and subject. Do not trust arbitrary headers such as x-user-id if external clients could set them directly.

## 12. Testing authentication and authorization

Two test groups should be separated to prove each layer works properly:

| Scenario | Expected result |
| --- | --- |
| No token sent | UNAUTHENTICATED; service method does not run |
| Token invalid signature/expired/wrong audience | UNAUTHENTICATED |
| Valid token, sufficient scope, valid resource | RPC succeeds |
| Valid token lacking method permission | PERMISSION_DENIED |
| Valid token, right scope, wrong tenant | Rejected by resource policy |
| Principal is not owner of order | Rejected or NOT_FOUND per contract |
| Untrusted mTLS certificate | TLS handshake rejected before RPC |
| Token expires between calls | New call rejected; refresh credential per flow |
| Client sends a different tenant_id | Server still uses the tenant from the authenticated principal |
| Wrong interceptor chain order | Test catches missing principal when authorization runs |

Beyond status codes, verify side effects: rejected requests must not read out-of-scope data, write to the database, or emit events. Use dedicated test certificates/tokens for tests; never put production credentials into fixtures.

## 13. Common mistakes

1. **Treating a valid token as permission to do everything.** Authentication does not replace authorization.
2. **Treating mTLS as end-user identity.** Certificates usually identify a workload/peer.
3. **Checking roles only at the gateway.** Services must still protect their own resources and side effects.
4. **Trusting tenant/user IDs from the request body or arbitrary metadata.** Obtain the principal from verified credentials.
5. **Returning UNAUTHENTICATED for all permission errors.** Valid credentials lacking permission should use PERMISSION_DENIED.
6. **Checking permissions only by method.** Resource/ownership permissions may need enforcement inside the service.
7. **Decoding JWTs without verifying signature and audience.** A payload alone does not prove identity.
8. **Putting bearer tokens into logs or traces.** Risks exposing credentials.
9. **Failing to test interceptor ordering.** Authorization might execute before the principal is populated.
10. **Assuming cancellation or transport errors undo committed side effects.** Authentication/authorization do not replace idempotency and transaction design.

## 14. Practice exercise

For orders.v1.OrderService/GetOrder:

1. Design a bearer token containing iss, aud, sub, exp, tenant, and scope.
2. Write an authentication interceptor that verifies the token and places the principal into gRPC Context.
3. Write a method authorization policy requiring orders:read.
4. In the application service, query orders by the principal's tenant and enforce ownership/resource policies.
5. Configure TLS; try mTLS to verify the client workload separately from the user token.
6. Write tests for missing/invalid/expired tokens, missing scope, wrong tenant, and authorized access.
7. Verify rejected requests produce no side effects and logs contain no tokens.

**Completion criteria:** the learner can explain that authentication establishes identity while authorization decides permissions; configure credentials/interceptors, distinguish UNAUTHENTICATED from PERMISSION_DENIED, enforce method and resource permissions, and test both TLS/mTLS and bearer tokens.

### References

- [gRPC Authentication](https://grpc.io/docs/guides/auth/): TLS, tokens, and authentication mechanisms in gRPC.
- [gRPC Metadata](https://grpc.io/docs/guides/metadata/): passing credentials and metadata in RPCs.
- [gRPC Java ServerInterceptor API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerInterceptor.html): handling authentication/authorization at the server boundary.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): distinguishing UNAUTHENTICATED and PERMISSION_DENIED.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): principals, authentication, and authorization in Spring.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): integrating gRPC clients/servers in Spring.
