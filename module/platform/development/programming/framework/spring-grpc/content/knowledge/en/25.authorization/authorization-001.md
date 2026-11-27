# Service and Method Call Authorization

## Learning Objectives

After this lesson, you will be able to:

- Distinguish identity verification (**authentication**) from call permission decisions (**authorization**) in gRPC.
- Identify an RPC by its full name **package.Service/Method** and use it as a policy key.
- Design permissions at two scopes: service and method, following the default-deny principle.
- Enforce policies on the server side using **ServerInterceptor**, principal, and **io.grpc.Context**.
- Distinguish **UNAUTHENTICATED** from **PERMISSION_DENIED**, while never trusting client-declared metadata as permissions.
- Handle authorization for streaming, resources/tenants, and special methods such as health/reflection.
- Test allow, deny, and unauthenticated cases in Spring gRPC.

## 1. Where Does Authorization Sit in a gRPC Call?

In **SPRING_GRPC**, Protocol Buffers defines the services and methods that clients can invoke. Generated stubs help clients call those methods, but the fact that a method is declared and visible to a client **does not mean every caller is allowed to use it**.

**Authorization** is the decision of whether an authenticated principal is permitted to call a service/method. For example:

- The **OrderService** service is only for workloads with access to the orders domain.
- The **GetOrder** method requires permission to read orders.
- The **CancelOrder** method requires permission to cancel orders.
- An administrative method may require a separate permission, even if it resides in the same service.

Typical flow:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant A as Authentication interceptor
    participant Z as Authorization interceptor
    participant S as Service implementation
    C->>A: RPC + credentials
    A->>A: Verify token / certificate
    A->>Z: Verified principal in Context
    Z->>Z: Check service and method policy
    alt Allowed
        Z->>S: Forward RPC
        S-->>C: Response + status
    else Insufficient permissions
        Z-->>C: PERMISSION_DENIED
    else Unauthenticated
        A-->>C: UNAUTHENTICATED
    end
~~~

Authorization is typically checked on the server because the client is controlled by the caller. A client may hide buttons or omit methods from the UI, but that only improves user experience; it does not protect the API.

## 2. Authentication vs. Authorization

These two steps have different goals:

| Step | Question | Example outcome |
| --- | --- | --- |
| **Authentication** | Who is the caller? | Principal **service:billing-worker** verified |
| **Authorization** | Is that principal allowed to call this method? | Has **orders:read**, allowed to call **OrderService/GetOrder** |

Authentication may verify a JWT, OAuth2 access token, mTLS certificate, or other credential. After verifying signature/issuer/audience/expiry and required claims, the authentication layer produces a trusted principal.

Authorization uses that principal together with policy to make a decision. Never extract **user-role**, **permissions**, or **tenant** from arbitrary metadata and treat it as proof of authorization. Metadata is caller-supplied data; it is only trustworthy if verified or set by a trusted component over a protected channel.

gRPC typically uses the following statuses:

- **UNAUTHENTICATED**: missing credential, invalid/expired credential, or identity cannot be verified.
- **PERMISSION_DENIED**: identity is verified, but policy does not allow calling the service/method or performing the operation.
- **INVALID_ARGUMENT**: invalid request; do not use this code to indicate missing permissions.
- **NOT_FOUND**: resource does not exist or is intentionally hidden per security policy; choose consistently to avoid information leakage.

Do not include tokens, certificate details, internal policies, or sensitive reasons in the status description. Clients only need a stable status code to handle; the server records diagnostic details in security logs.

## 3. Identifying Services and Methods in gRPC

The full method name is the natural key for applying policy:

~~~text
demo.orders.v1.OrderService/GetOrder
demo.orders.v1.OrderService/WatchOrder
demo.orders.v1.OrderService/CancelOrder
demo.admin.v1.AdminService/DisableAccount
~~~

In grpc-java, this name can be obtained from:

~~~java
String fullMethodName =
        call.getMethodDescriptor().getFullMethodName();
~~~

The **fullMethodName** value has the form **package.Service/Method**, without a leading slash. The HTTP/2 **:path** typically has the form **/package.Service/Method**. Use the descriptor API to obtain the method name, avoiding manual parsing of URL, authority, or path strings from metadata.

Policies should use full, stable names. When changing a package, service, or method in proto, the RPC name may change; policies and tests must be updated alongside the contract change.

## 4. Combining Service-Level and Method-Level Permissions

Service-level permissions restrict the API domain a principal can access. Method-level permissions restrict specific actions within a service.

Example policy:

| Service / method | Required permission |
| --- | --- |
| **OrderService** | **orders:access** |
| **OrderService/GetOrder** | **orders:read** |
| **OrderService/WatchOrder** | **orders:read** |
| **OrderService/CancelOrder** | **orders:cancel** |
| **AdminService** | **admin:access** |
| **AdminService/DisableAccount** | **accounts:disable** |

To call **OrderService/GetOrder**, the principal needs both **orders:access** and **orders:read**. This combination creates a coarse-grained policy layer for the service and a fine-grained permission layer for the method.

Some systems may choose a policy where methods inherit service permissions if the method has no specific rule. Whichever approach is chosen, inheritance semantics must be clearly specified and **undeclared methods must be denied by default**. A new method should never be accidentally allowed simply because it was added to the proto.

### 4.1. Immutable Principal Model

After authentication, store the verified subject and permission set in an immutable object:

~~~java
package dev.example.security;

import java.util.Objects;
import java.util.Set;

public record GrpcPrincipal(
        String subject,
        Set<String> permissions) {

    public GrpcPrincipal {
        Objects.requireNonNull(subject, "subject");
        permissions = Set.copyOf(permissions);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

The permission set must come from a trusted source such as verified claims, a policy engine, or a service identity registry. Never build a principal by copying a client-sent **x-permissions** header.

### 4.2. Policy by Full Name

A simple policy can require both service and method permissions:

~~~java
package dev.example.security;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class GrpcMethodPolicy {

    private final Map<String, String> servicePermissions = Map.of(
            "demo.orders.v1.OrderService", "orders:access",
            "demo.admin.v1.AdminService", "admin:access");

    private final Map<String, String> methodPermissions = Map.of(
            "demo.orders.v1.OrderService/GetOrder", "orders:read",
            "demo.orders.v1.OrderService/WatchOrder", "orders:read",
            "demo.orders.v1.OrderService/CancelOrder", "orders:cancel",
            "demo.admin.v1.AdminService/DisableAccount",
                    "accounts:disable");

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        int separator = fullMethodName.indexOf('/');
        if (separator <= 0 || separator == fullMethodName.length() - 1) {
            return false;
        }

        String serviceName = fullMethodName.substring(0, separator);
        String servicePermission = servicePermissions.get(serviceName);
        String methodPermission = methodPermissions.get(fullMethodName);

        // Missing service or method rule means deny.
        return servicePermission != null
                && methodPermission != null
                && principal.hasPermission(servicePermission)
                && principal.hasPermission(methodPermission);
    }
}
~~~

The example uses a static map to illustrate the mechanism. Production systems may load policies from controlled configuration or a policy engine, but must define how updates, caching, auditing, and failures are handled when the policy source is unavailable. If a policy cannot be determined, do not allow by default.

## 5. Putting the Principal into Context After Authentication

**io.grpc.Context** carries data associated with an RPC across grpc-java callbacks. The authentication interceptor verifies credentials and attaches the principal to the Context. The authorization interceptor reads that principal.

Declare a shared context key:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

An authentication interceptor can look like:

~~~java
package dev.example.security;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Optional;

public final class AuthenticationServerInterceptor
        implements ServerInterceptor {

    private final CredentialAuthenticator authenticator;

    public AuthenticationServerInterceptor(
            CredentialAuthenticator authenticator) {
        this.authenticator = authenticator;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Optional<GrpcPrincipal> authenticated =
                authenticator.authenticate(headers);

        if (authenticated.isEmpty()) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context = Context.current().withValue(
                GrpcSecurityContext.PRINCIPAL,
                authenticated.get());

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

**CredentialAuthenticator** is an application abstraction for verifying tokens/certificates; it must not treat metadata as a principal before checking credentials. The example omits token verification algorithms because library choices, issuers, and trust configurations depend on the system.

If a handler offloads work to a separate executor, propagate the Context to that thread using APIs such as **Context.wrap(...)**. Do not rely on custom ThreadLocals or assume asynchronous tasks automatically inherit the principal.

## 6. Enforcing Permissions in ServerInterceptor

The authorization interceptor checks the principal and method before forwarding to the service implementation:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class MethodAuthorizationInterceptor
        implements ServerInterceptor {

    private final GrpcMethodPolicy policy;

    public MethodAuthorizationInterceptor(GrpcMethodPolicy policy) {
        this.policy = policy;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        GrpcPrincipal principal =
                GrpcSecurityContext.PRINCIPAL.get();

        if (principal == null) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        String fullMethodName =
                call.getMethodDescriptor().getFullMethodName();

        if (!policy.allows(principal, fullMethodName)) {
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

If denied, the interceptor closes the call and returns an empty listener; the service implementation is not called. Do not merely log and still call **next.startCall(...)**, because then authorization is not actually enforced.

Authentication must run before authorization so that Context already holds the principal. When registering multiple interceptors, verify the nesting/wrapping order of the server API or starter being used and write integration tests to ensure the principal is present at the authorization interceptor.

### 6.1. Registration in a Spring Application

In direct grpc-java configuration, interceptors are attached to the service definition before registering with the server. Conceptual wiring example:

~~~java
@Bean
ServerServiceDefinition securedOrderService(
        OrderEndpoint endpoint,
        AuthenticationServerInterceptor authentication,
        MethodAuthorizationInterceptor authorization) {

    return ServerInterceptors.interceptForward(
            endpoint,
            authentication,
            authorization);
}
~~~

This wiring illustrates the desired order: authentication creates the principal in Context first, and authorization reads the principal afterward. When using the Spring gRPC starter, register interceptors via the extension point/bean registration of the exact starter version; do not manually create an additional server if the starter already manages the server. Verify ordering with tests rather than relying on assumptions about configuration order.

## 7. Service/Method Permissions Do Not Replace Resource Permissions

Method call permissions only answer whether the caller is allowed to invoke a type of operation. They do not necessarily indicate whether the caller may operate on **every resource** specified in the request.

For example, **orders:read** allows calling **GetOrder**, but the service must still verify that the caller has permission to read the specific **order_id** within the corresponding tenant. Similarly, permission to call **CancelOrder** does not automatically allow canceling every order.

Checks at the service/domain layer are needed when permissions depend on:

- **Resource ownership:** users only view or modify their own resources.
- **Tenant boundary:** workloads only access data belonging to their granted tenant.
- **Relationship/attribute:** permissions depend on order status, organization role, or resource attributes.
- **Business state:** orders can only be canceled before shipping or settlement.

Do not use **tenant_id** sent in the request as proof of tenant. Cross-check it against the verified tenant/relationship in the principal or policy store. This prevents an otherwise valid caller from changing an ID to access another tenant's data.

## 8. Authorization with Streaming RPCs

For unary RPCs, an interceptor can make an authorization decision before the handler processes the request. For client-streaming and bidirectional streaming, the interceptor still only sees the method when the call opens; subsequent messages may carry many different resource IDs.

Therefore:

- Check service/method call permissions as soon as the stream opens.
- Check each message or each resource at the business layer if the stream can operate on multiple resources.
- Terminate the stream with an appropriate status when an unauthorized message is detected.
- Clean up subscriptions, buffers, and background work when a call is canceled or denied.
- Do not assume a single authorization check at stream open grants access to every resource sent later.

For example, **WatchOrder** may be allowed at the method level, but each **order_id** must be checked for tenant/ownership before registering a subscription.

## 9. Special Methods: Health, Reflection, and Internal APIs

Some methods do not belong to business services yet can still be invoked over the network:

- **gRPC health** is often needed for load balancers/orchestrators to check the service.
- **Reflection** helps tools discover service descriptors, but can expose the API surface.
- **Admin/internal methods** can alter system state or read sensitive information.

Do not create a blanket exception such as "all methods without a policy are allowed." Explicitly declare which methods are public, which are restricted to internal workloads, and which require administrative permissions. If the health endpoint needs unauthenticated access within an internal network, restrict it via listener/network policy or a dedicated policy; do not open all business services under the same exception.

Reflection is not an authorization mechanism. Hiding a service from reflection does not prevent a client that knows the method name from calling it directly.

## 10. Auditing, Policy Caching, and Safety Principles

Authorization is a security decision and therefore needs observability without leaking data:

- Record **principal ID**, full method name, allow/deny decision, and correlation ID according to log policy.
- Do not log tokens, private keys, full metadata, or sensitive payloads.
- Use stable statuses; avoid describing internal policy details in responses.
- Use deny-by-default for new methods or unreadable policies.
- If caching permissions, define TTL, invalidation, and revocation windows.
- Keep policy changes under an audit trail, review, and rollback process.
- Metrics should use method/status/decision labels with controlled cardinality; do not use user IDs as labels.

Long-lived caches can allow revoked permissions to remain usable. For sensitive permissions, use short caches or online policy checks depending on latency and fault-tolerance requirements. If the policy service fails, failing closed is usually safer than automatically allowing.

## 11. Testing Authorization

Decisions should be tested through the gRPC runtime to confirm the interceptor actually blocks calls before the handler.

| Case | Expected result |
| --- | --- |
| No principal | **UNAUTHENTICATED** |
| Principal lacks service permission | **PERMISSION_DENIED** |
| Has service permission but lacks method permission | **PERMISSION_DENIED** |
| Has both permissions | Handler is invoked, RPC can succeed |
| New method without policy | **PERMISSION_DENIED** |
| Fake metadata **x-role: admin** while principal lacks permission | **PERMISSION_DENIED** |
| Has method permission but does not own resource | Domain/service rejects the resource operation |
| Streaming message contains out-of-tenant resource | Stream is rejected/terminated per policy |
| Health/reflection method | Accessible only per explicitly published rule |

An in-process test should use a mock principal injected by a test authenticator, then call through the generated stub and verify the status. Also place a flag or mock on the service implementation to assert that the handler is **not invoked** when the interceptor denies the call. Add tests over real transport if authorization depends on mTLS, a gateway, or identity forwarded by a proxy.

## 12. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Define **OrderService** with **GetOrder**, **WatchOrder**, and **CancelOrder**.
2. Create **GrpcPrincipal** containing only the verified subject and permissions.
3. Create a policy requiring **orders:access** at the service level; **orders:read** for GetOrder/WatchOrder and **orders:cancel** for CancelOrder.
4. Put the principal into **io.grpc.Context** in the authentication interceptor.
5. Add **MethodAuthorizationInterceptor** that reads **getFullMethodName()** and denies methods without a policy.
6. Write in-process tests for missing principal, missing service permission, missing method permission, sufficient permissions, and undeclared method.
7. Add ownership/tenant checks in the domain service for **order_id**, even when the principal has **orders:read**.
8. Inspect logs/audits and verify no tokens or sensitive data appear in statuses/metadata.

### Self-Check Questions

**1. How does authentication differ from authorization?**  
Authentication verifies who the caller is; authorization decides which services/methods or resources that principal may call or operate on.

**2. Why must authorization be enforced on the server?**  
Clients can be modified or bypass the UI. Only the server is a trusted boundary to decide whether to execute an RPC.

**3. What format does getFullMethodName() return?**  
The **package.Service/Method** format, suitable as a policy key for gRPC methods.

**4. When should UNAUTHENTICATED vs. PERMISSION_DENIED be returned?**  
UNAUTHENTICATED when identity cannot be verified; PERMISSION_DENIED when the principal is verified but lacks permission.

**5. Why are both service-level and method-level permissions needed?**  
Service-level limits the API domain; method-level limits specific actions within that domain.

**6. How should a new method without a policy be handled?**  
Deny by default until a policy is declared and tested.

**7. Can permissions be checked only once for all streaming messages?**  
That is only sufficient for method-call permission. If each message targets a different resource/tenant, permissions must be checked at the business layer for each resource.

**8. Why should x-role: admin from the client not be trusted?**  
It is caller-declared metadata and proves neither identity nor permissions. A principal must be built from verified credentials.

## Summary

**Service- and method-level authorization** controls which callers are allowed to invoke each RPC. The server verifies identity first, places a trusted principal into **io.grpc.Context**, and then uses a **ServerInterceptor** to match the full method name against service-level and method-level policies. Missing principals return **UNAUTHENTICATED**; principals lacking permissions or methods without rules return **PERMISSION_DENIED** under the deny-by-default principle. For permissions depending on tenant, ownership, or resource state, the service/domain must still check specific data, including in streaming. Testing both allow/deny decisions and whether the handler is actually blocked ensures the policy properly protects the Spring gRPC API surface.
