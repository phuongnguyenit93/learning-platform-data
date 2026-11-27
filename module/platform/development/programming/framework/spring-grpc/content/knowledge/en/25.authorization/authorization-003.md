# Authorization Interceptor

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of the **Authorization interceptor** in the server-side RPC processing pipeline.
- Distinguish the authentication interceptor from the authorization interceptor and identify the data each step is responsible for.
- Retrieve the verified principal from **io.grpc.Context**, identify the RPC by full method name, and evaluate policy.
- Properly reject calls using **PERMISSION_DENIED** or **UNAUTHENTICATED** without invoking the service implementation.
- Register interceptors in the correct order in grpc-java and Spring gRPC applications.
- Design deny-by-default policies, handle policy errors, audit decisions, and avoid information leakage.
- Distinguish method call permissions from resource, tenant, and per-message streaming RPC permissions.
- Test the interceptor to prove both the returned status and that the handler is not executed.

## 1. Where Does the Authorization Interceptor Sit?

In **SPRING_GRPC**, generated stubs allow clients to call RPC methods defined in Protocol Buffers. The server receives the request and routes it to the service implementation. Before the call reaches the handler, a **ServerInterceptor** can inspect shared cross-cutting conditions.

The authentication interceptor answers who the caller is by verifying tokens, certificates, or other credentials. After verification, it creates a trusted principal and places it into the gRPC Context. The authorization interceptor reads that principal, determines which method is being called, and decides whether to allow the call to proceed.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant A as Authentication interceptor
    participant Z as Authorization interceptor
    participant S as Service implementation
    C->>A: RPC + credential
    A->>A: Verify credential
    A->>Z: Principal in Context
    Z->>Z: Check policy by method
    alt Allowed
        Z->>S: next.startCall
        S-->>C: Response / status
    else Unauthenticated
        A-->>C: UNAUTHENTICATED
    else Insufficient permissions
        Z-->>C: PERMISSION_DENIED
    end
~~~

The authorization interceptor is an **enforcement point at the RPC boundary**. It can protect entire methods from unauthorized callers, but it does not replace business checks on individual orders, accounts, or tenants. A principal allowed to call GetOrder may still not be allowed to read a specific order.

## 2. Lifecycle of ServerInterceptor

grpc-java defines ServerInterceptor via the method:

~~~java
<ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
        ServerCall<ReqT, RespT> call,
        Metadata headers,
        ServerCallHandler<ReqT, RespT> next);
~~~

Every RPC arriving at a service registered with the interceptor passes through interceptCall. Three key parameters:

- **ServerCall** provides the method descriptor, attributes, response headers, trailers, status, and call-closing operations.
- **Metadata headers** contains the request metadata decoded by the gRPC runtime.
- **ServerCallHandler next** is the next step in the pipeline; typically it invokes the service implementation and returns a listener that receives request messages.

The authorization interceptor has two outcomes:

1. **Allow:** call next.startCall(call, headers) and return the listener provided by the next step.
2. **Deny:** close the call with an appropriate status, return an empty listener, and never call next.startCall.

Skeleton example:

~~~java
@Override
public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
        ServerCall<ReqT, RespT> call,
        Metadata headers,
        ServerCallHandler<ReqT, RespT> next) {

    AuthorizationDecision decision = authorize(call);

    if (!decision.allowed()) {
        call.close(
                Status.PERMISSION_DENIED.withDescription("Permission denied"),
                new Metadata());
        return new ServerCall.Listener<ReqT>() {};
    }

    return next.startCall(call, headers);
}
~~~

Do not call next first and check permissions afterward. Once next.startCall has run, the service implementation may already start processing the request; returning PERMISSION_DENIED later cannot undo side effects that already occurred.

The interceptor should also not invoke onMessage itself or synthesize business responses when denying. It terminates the RPC at the server boundary using status/trailers; the caller receives the result according to the gRPC protocol.

## 3. Principal Must Come from Verified Authentication

Authorization must never infer identity from arbitrary headers. A client may send metadata such as x-user, x-role, or x-permissions, but those values are not proof of authorization.

An immutable principal can contain the verified subject and permission set:

~~~java
package dev.example.security;

import java.util.Objects;
import java.util.Set;

public record GrpcPrincipal(
        String subject,
        Set<String> permissions) {

    public GrpcPrincipal {
        Objects.requireNonNull(subject, "subject");
        if (subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        permissions = Set.copyOf(permissions);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

Use a shared Context key between authentication and authorization:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

After verifying credentials, the authentication interceptor puts the principal into Context:

~~~java
Context context = Context.current().withValue(
        GrpcSecurityContext.PRINCIPAL,
        verifiedPrincipal);

return Contexts.interceptCall(context, call, headers, next);
~~~

The authorization interceptor reads the same key via:

~~~java
GrpcPrincipal principal = GrpcSecurityContext.PRINCIPAL.get();
~~~

It is critical that both interceptors use **the exact same Context.Key instance**. Creating two separate keys even with the same string name still produces two distinct keys; authorization will not be able to read the principal set by authentication.

Context binds data to RPC processing and is propagated by grpc-java across callbacks via the runtime mechanism. If the service offloads work to a custom executor, propagate Context to the task using APIs like Context.wrap or an equivalent mechanism. Do not assume custom ThreadLocals automatically propagate to another thread.

## 4. Identifying Methods and Evaluating Policy

The method being invoked can be retrieved directly from the descriptor:

~~~java
String fullMethodName =
        call.getMethodDescriptor().getFullMethodName();
~~~

The full name has the form:

~~~text
demo.orders.v1.OrderService/GetOrder
demo.orders.v1.OrderService/CancelOrder
demo.accounts.v1.AccountService/DisableAccount
~~~

Do not manually parse URLs, hostnames, or metadata to determine the method. Using MethodDescriptor keeps the policy tied to the actual gRPC contract.

A simple policy maps methods to required permissions:

~~~java
package dev.example.security;

import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class GrpcAuthorizationPolicy {

    private final Map<String, Set<String>> requiredPermissions = Map.of(
            "demo.orders.v1.OrderService/GetOrder",
            Set.of("orders:read"),
            "demo.orders.v1.OrderService/WatchOrder",
            Set.of("orders:read", "orders:watch"),
            "demo.orders.v1.OrderService/CancelOrder",
            Set.of("orders:cancel"),
            "demo.accounts.v1.AccountService/DisableAccount",
            Set.of("accounts:disable"));

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        Set<String> required =
                requiredPermissions.get(fullMethodName);

        // Methods without a policy are always denied.
        return required != null
                && principal.permissions().containsAll(required);
    }
}
~~~

This policy uses deny-by-default: undeclared methods are not allowed. Do not use a rule like "if no policy is found, allow," because newly added proto methods could accidentally open up to every caller.

For larger systems, policies may come from versioned configuration, a database, or a policy engine. Regardless of the source, explicitly define caching, invalidation, auditing, and behavior when the policy store is unreachable. If permissions cannot be evaluated reliably, failing closed is usually safer than allowing automatically.

## 5. Implementing the Authorization Interceptor

The following example uses the principal from Context and a policy keyed by full method name:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import org.springframework.stereotype.Component;

@Component
public final class AuthorizationServerInterceptor
        implements ServerInterceptor {

    private final GrpcAuthorizationPolicy policy;
    private final AuthorizationAudit audit;

    public AuthorizationServerInterceptor(
            GrpcAuthorizationPolicy policy,
            AuthorizationAudit audit) {
        this.policy = policy;
        this.audit = audit;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method =
                call.getMethodDescriptor().getFullMethodName();

        GrpcPrincipal principal =
                GrpcSecurityContext.PRINCIPAL.get();

        if (principal == null) {
            audit.record(null, method, false, "missing_principal");
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        boolean allowed = policy.allows(principal, method);

        audit.record(
                principal.subject(),
                method,
                allowed,
                allowed ? "allowed" : "permission_denied");

        if (!allowed) {
            call.close(
                    Status.PERMISSION_DENIED
                            .withDescription("Permission denied"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

The example assumes the authentication interceptor ran earlier and set the principal. If the principal is absent, the interceptor returns **UNAUTHENTICATED**; this case usually indicates that the authentication interceptor was not applied, credentials were invalid, or Context was not propagated properly.

If the principal is verified but lacks permissions, return **PERMISSION_DENIED**. Do not include internal permission names, policy rules, tokens, or credential details in the response description. The caller only needs a stable status; the server can record the specific reason in a controlled audit log.

**AuthorizationAudit** should be an abstraction for recording allow/deny events. Real implementations must be thread-safe, avoid blocking callbacks with slow I/O, and avoid logging tokens or full metadata. If auditing must be durable before allowing sensitive operations, explicitly design the durability and latency requirements rather than defaulting to synchronous logging.

## 6. Authentication Must Run Before Authorization

Authorization relies on the principal created by authentication, so interceptor ordering is part of correctness and security.

~~~text
Incoming RPC
    |
    v
Authentication interceptor
    |  verify credential
    |  set GrpcSecurityContext.PRINCIPAL
    v
Authorization interceptor
    |  read principal
    |  check method policy
    +---- deny --> close(PERMISSION_DENIED)
    |
    v
Service implementation
~~~

With grpc-java, interceptors can be registered around a service using ServerInterceptors. Example:

~~~java
ServerServiceDefinition securedService =
        ServerInterceptors.interceptForward(
                orderEndpoint,
                authenticationInterceptor,
                authorizationInterceptor);

serverBuilder.addService(securedService);
~~~

This code illustrates the desired order: authentication establishes Context first, and authorization reads Context afterward. Exact execution order must be verified against the registration API in use and the grpc-java/starter version; write integration tests to prove the principal is present at the authorization interceptor.

In the Spring gRPC starter, register interceptors through the extension point or bean registration supported by the starter version. Do not create a manual server on the same port if the starter already owns the server. Also avoid registering the same interceptor twice, as audits and metrics could be recorded in duplicate.

## 7. Choosing the Status and Closing the Call Properly

The authorization interceptor typically needs to distinguish these cases:

| Situation | Status | Meaning |
| --- | --- | --- |
| No principal or unverified credential | **UNAUTHENTICATED** | Server has not identified the caller |
| Principal verified but lacks permissions | **PERMISSION_DENIED** | Caller has an identity, but policy denies the action |
| Policy has no rule for method | **PERMISSION_DENIED** | Deny-by-default |
| Policy store unavailable | Usually fail-closed; status depends on infrastructure error and contract | Must not default to allow |
| Malformed request | **INVALID_ARGUMENT** | Request data error, not a permission error |

When denying, call ServerCall.close with status and trailers, then return an empty listener. Do not call next.startCall. Do not call close multiple times; avoid emitting a second terminal status once the call has already ended.

If the policy service encounters an infrastructure error, you may choose **UNAVAILABLE** or **INTERNAL** depending on the operational contract, but never convert a policy error into allow. Distinguishing a policy denial from an inability to evaluate policy helps clients and monitoring systems respond properly.

## 8. Method Permissions vs. Resource Permissions

The authorization interceptor is suited for service/method-level permissions, such as whether a principal may call GetOrder or CancelOrder. It does not automatically know whether the caller has permission to access a specific order.

For example, a principal has the orders:read permission, yet the request contains an orderId belonging to another tenant. The service/domain layer needs to check:

- whether the order exists and belongs to the principal's verified tenant;
- whether the caller has ownership or is assigned to handle it;
- whether the business state allows the operation;
- whether the response should hide resource existence to prevent ID enumeration.

Do not trust client-supplied tenantId or ownerId as proof of permission. Cross-check the request against the principal or trusted policy data. You can use the authorization interceptor for coarse-grained policy, then let the service perform resource authorization with actual data.

## 9. Authorization for Streaming RPCs

The interceptor evaluates method permissions when the RPC opens. For client-streaming or bidirectional streaming, multiple messages can arrive later and each message may reference different resources.

For example:

- WatchOrder requires orders:read and orders:watch permissions when opening the stream.
- If WatchOrder tracks multiple orderIds, each order must still pass tenant/ownership checks.
- UploadEvents requires the events:write permission, yet each event must still be checked for schema, tenant, and state.
- When permissions are revoked while a long-lived stream is running, an explicit policy is needed for revalidation or cancellation.

Do not assume a single method check at stream open permits every subsequent message. If rapid permission revocation is required, consider bounding stream duration, revalidating periodically, or canceling subscriptions when identity/policy changes. When denying mid-stream, the service must terminate the stream with an appropriate status and clean up resources.

## 10. Common Implementation Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every call is UNAUTHENTICATED | Authentication not registered or different Context keys | Share the Context key and check ordering |
| Valid user still gets PERMISSION_DENIED | Policy uses wrong full method name or missing mapping | Log method name, check catalog, and test |
| New method is automatically callable | Default-allow policy | Deny-by-default and require mapping for new methods |
| Handler still runs despite audit logging deny | Interceptor calls next before checking or still calls next after deny | Close the call and return an empty listener |
| Audit logs twice | Interceptor registered twice or auditing in multiple layers | Check registration and event definitions |
| Permissions leak across two RPCs | Principal stored in a shared mutable field | Store principal in Context per call |
| Streaming accesses another tenant | Only checked method at stream open | Check resources per message |
| Policy store fails but calls are allowed | Fallback to allow on error | Fail-closed and monitor policy errors |
| Client sees internal permission details | Status description contains policy/claims | Generic response; details in audit logs |

When debugging, check step by step: are credentials verified; does the authentication interceptor set the right Context key; can authorization read the principal; does the full method name match the policy; is the decision enforced before next.startCall; is the status sent back to the client properly.

## 11. Testing the Authorization Interceptor

Tests must verify both the RPC result and server-side side effects. Asserting PERMISSION_DENIED alone is insufficient if the handler still runs before the call closes.

| Scenario | Expected Status | Handler |
| --- | --- | --- |
| No principal | UNAUTHENTICATED | Not executed |
| Principal lacks permission | PERMISSION_DENIED | Not executed |
| Method has no policy | PERMISSION_DENIED | Not executed |
| Principal has sufficient permissions | OK or business status | Executed |
| Policy store fails | Fail-closed per contract | Not executed |
| Has method permission but resource is wrong tenant | Appropriate domain/security status | May enter handler, but resource operation is blocked |

Use an in-process gRPC test to call through the generated stub, register authentication and authorization interceptors as in production, and verify:

1. Authentication creates the principal using the shared Context key.
2. Authorization reads the right principal within the same RPC.
3. Methods without a policy are denied.
4. When denied, a mock/flag confirms the service implementation is not called.
5. When allowed, the handler runs and returns a normal response.
6. Two concurrent RPCs with different principals do not accidentally share context.
7. Streaming is denied properly at open or during resource checks in message processing.

In-process tests do not verify TLS, proxies, or credential validation over the network. If identity comes from JWT/mTLS or a gateway, add integration tests over real transport to verify the full authentication and authorization chain.

## 12. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Create an immutable GrpcPrincipal containing the verified subject and permissions.
2. Create GrpcSecurityContext with a shared Context key for authentication and authorization.
3. Create a mock authentication interceptor in tests that sets the principal into Context using Contexts.interceptCall.
4. Write GrpcAuthorizationPolicy mapping full method names to required permissions; methods without rules must be denied.
5. Write AuthorizationServerInterceptor returning UNAUTHENTICATED when missing a principal and PERMISSION_DENIED when lacking permissions.
6. Register authentication before authorization using the appropriate server API and verify ordering in an integration test.
7. Place a mock/flag in the service implementation to prove the handler does not run when denied.
8. Add resource/tenant checks in the service and test streaming with multiple resource IDs.

### Self-Check Questions

**1. What is the responsibility of the authorization interceptor?**  
Read the verified principal, determine the full method name, evaluate policy, and block the RPC before the service implementation runs if the caller lacks permissions.

**2. Why must authentication run before authorization?**  
Authorization needs a trusted principal. If authentication has not verified credentials or populated Context, the interceptor has no basis to decide permissions.

**3. Why must both interceptors use the exact same Context.Key instance?**  
A Context key is an identity-based object. Creating two different keys even with the same name does not make them reference the same value.

**4. When should UNAUTHENTICATED vs. PERMISSION_DENIED be returned?**  
UNAUTHENTICATED when the caller has not been verified; PERMISSION_DENIED when the principal is verified but policy denies access.

**5. Why must methods without a policy be denied?**  
Deny-by-default prevents new methods added to proto from accidentally becoming public APIs.

**6. Can an interceptor be used to check ownership of individual orders?**  
An interceptor can check general method permissions; ownership requires resource data and is therefore usually checked in the service/domain layer.

**7. Is a single authorization check when opening a stream enough?**  
It is only enough for method-call permission. If messages reference multiple resources or permissions may be revoked, per-message/periodic checks or stream cancellation are needed.

**8. What test proves the interceptor actually protects the service?**  
A test calling through the gRPC runtime that asserts the status and simultaneously verifies the handler is not invoked when the decision is deny.

## Summary

The **authorization interceptor** is the policy enforcement layer at the gRPC server boundary. Authentication verifies credentials and places the principal into a shared **io.grpc.Context**; authorization reads the principal, retrieves the full method name, and checks permissions following the deny-by-default principle. When the principal is missing, return **UNAUTHENTICATED**; when the principal lacks permissions, return **PERMISSION_DENIED** and do not call next.startCall. Register interceptors in the right order in Spring gRPC, keep policies fail-closed, audit safely, and test both status and whether the handler runs. Method permissions still need to be combined with resource/tenant authorization at the service/domain layer, especially for streaming RPCs.
