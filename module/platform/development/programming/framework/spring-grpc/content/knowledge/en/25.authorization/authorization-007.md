# Never Rely on Client-Supplied Method Names

## Learning Objectives

After this lesson, you will be able to:

- Explain why a method name declared by the client in metadata or request body is not a trustworthy basis for authorization.
- Distinguish the RPC path chosen by the client from the method descriptor dispatched by the server.
- Obtain the method name from the server-side MethodDescriptor and use the full method name for policy evaluation.
- Design exact, deny-by-default allowlists without relying on prefixes or similar method names.
- Combine method authorization with verified principals, tenants, and resource policies.
- Understand the impact of gateway/path rewrites and how to protect the backend.
- Test method name spoofing, unauthorized method calls, and non-existent methods.

## 1. Why Never Trust Client-Declared Method Names?

In **SPRING_GRPC**, clients invoke services through generated stubs. An RPC is identified by the service and method in the Protocol Buffers contract, such as OrderService/GetOrder. The server needs to know the actual method being executed to enforce authorization.

A common design mistake is letting the client send extra metadata or a request field such as:

~~~text
x-method-name: demo.orders.v1.OrderService/GetOrder
~~~

And then having the server use that value to decide permissions. The client can replace it with an allowed method name, even while the actual RPC invokes an administrative method:

~~~text
Actual RPC: demo.admin.v1.AdminService/DisableAccount
Claimed metadata: demo.orders.v1.OrderService/GetOrder
~~~

If authorization trusts that metadata, the server might allow an administrative operation based on a forged method name. A client-declared method name is untrusted data, just like any other input.

**Principle:** authorization must rely on the method descriptor dispatched by the server, never on a method name inside custom metadata, protobuf request bodies, query parameters, or caller-controlled headers.

## 2. Client Chooses RPC Path; Server Determines Executed Method

Distinguish these two concepts:

- The client indeed chooses the RPC via the HTTP/2 path, typically formatted as /package.Service/Method. This is part of the routing protocol; the client is allowed to request a method it knows.
- The server receives the path, looks up the registered service/method, and dispatches to the corresponding method. When the service's interceptor is called, ServerCall provides the MethodDescriptor representing the method selected by the server.

Thus, it is not that the server ignores the RPC path. The path is a routing input, whereas authorization uses the server-side descriptor after dispatch.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as HTTP/2 transport
    participant R as Server dispatch
    participant I as Authorization interceptor
    participant S as Service handler
    C->>T: POST + :path /demo.admin.v1.AdminService/DisableAccount
    T->>R: Resolve registered service and method
    R->>I: ServerCall + MethodDescriptor
    I->>I: Read server-side full method name
    alt Policy allows
        I->>S: next.startCall
        S-->>C: Response
    else Policy denies
        I-->>C: PERMISSION_DENIED
    end
~~~

Generated stubs help client code follow the contract, but they are not a security boundary. A caller can use a raw gRPC client or craft an HTTP/2 request targeting a different path. The server must still authenticate and check permissions for the actual method.

## 3. Getting the Full Method Name from the Server-Side Descriptor

In grpc-java, ServerCall provides the MethodDescriptor:

~~~java
String fullMethodName =
        call.getMethodDescriptor().getFullMethodName();
~~~

The full method name has the exact form:

~~~text
demo.orders.v1.OrderService/GetOrder
demo.orders.v1.OrderService/CancelOrder
demo.admin.v1.AdminService/DisableAccount
~~~

This is the proper value to match against policy. There is no need to manually split URLs or read a custom header to determine the method.

You can use generated descriptors to avoid repeating method name strings in policies:

~~~java
String getOrderMethod =
        OrderServiceGrpc.getGetOrderMethod().getFullMethodName();

String cancelOrderMethod =
        OrderServiceGrpc.getCancelOrderMethod().getFullMethodName();
~~~

Generated descriptors reflect method names in the contract compiled on the server. When package/service/method names change, policies and tests must be updated alongside the contract change.

## 4. Using Exact Allowlists and Deny-by-Default

Policies should match full method names exactly. Avoid prefix, suffix, or substring checks:

~~~java
// Unsafe: any method with this prefix could slip through.
if (fullMethodName.startsWith("demo.orders.v1.OrderService/")) {
    return true;
}
~~~

If a service contains both read methods and administrative methods, a service prefix cannot express permission differences. A new method added to the service could also be opened accidentally.

Example exact policy:

~~~java
package dev.example.security;

import dev.example.orders.v1.OrderServiceGrpc;
import dev.example.admin.v1.AdminServiceGrpc;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class GrpcMethodPolicy {

    private final Map<String, String> requiredPermissions = Map.of(
            OrderServiceGrpc.getGetOrderMethod().getFullMethodName(),
            "orders:read",
            OrderServiceGrpc.getCancelOrderMethod().getFullMethodName(),
            "orders:cancel",
            AdminServiceGrpc.getDisableAccountMethod().getFullMethodName(),
            "accounts:disable");

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        String permission = requiredPermissions.get(fullMethodName);

        // Undeclared methods or missing permissions are always denied.
        return permission != null
                && principal.hasPermission(permission);
    }
}
~~~

This map uses exact keys. Not finding a method means the policy grants no permission. If a method requires multiple permissions, the policy can map to Set<String> and require the principal to hold all of them.

For public methods like health checks, declare specific exceptions by exact service/method and network boundary. Do not open an entire service just so a health probe works.

## 5. Authorization Interceptor Uses Only the Server Method Descriptor

The interceptor needs a principal verified by authentication. Authentication and authorization share one Context key:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

The authentication interceptor verifies credentials and puts the principal into Context. The authorization interceptor gets the method name from ServerCall:

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

The interceptor never reads a metadata key such as x-method-name. It uses the descriptor provided by server dispatch, then checks permissions on the verified principal.

If there is no principal, return UNAUTHENTICATED. If the principal exists but lacks permission for the actual method, return PERMISSION_DENIED. The deny branch closes the call and returns an empty listener; do not call next.startCall, because the service handler must not run when policy denies.

### 5.1. Registering Interceptors in the Right Order

With grpc-java, wrap the service definition so authentication runs before authorization:

~~~java
ServerServiceDefinition securedOrders =
        ServerInterceptors.interceptForward(
                orderService,
                authenticationInterceptor,
                methodAuthorizationInterceptor);

serverBuilder.addService(securedOrders);
~~~

In the Spring gRPC starter, register interceptors via the extension point/bean registration supported by your version; do not manually create a second server if the starter already manages the server. Test the actual execution order to ensure the principal is populated before authorization reads Context.

## 6. Metadata and Request Fields Remain Untrusted Input

Clients can send many kinds of data:

- Custom metadata such as x-method-name, x-role, or x-permissions.
- Request fields such as operation, action, commandType, or method.
- Query/route parameters forwarded by a gateway.
- Trace baggage or correlation metadata.

These fields may be useful for business logic, logging, or tracing, but must never replace the method descriptor when identifying the executing RPC.

If a request body contains an action field, that field may describe an **internal business action** inside a generic RPC, such as ExecuteCommand. In that case, the server must check the action against domain policy and resource state. Never treat the action field as the gRPC method name or allow it to override method authorization.

Similarly, never use client-sent x-role/x-permissions as a principal. Permissions must come from verified credentials or a trusted policy engine.

## 7. Gateways and Path Rewrites

In real deployments, gRPC traffic may pass through an ingress, reverse proxy, or service mesh. A gateway may select clusters or rewrite paths per configuration.

Ensure that:

- The gateway only routes to permitted backends/services.
- The backend still authenticates workloads/clients per the trust model, such as mTLS or tokens.
- Backend authorization uses the MethodDescriptor actually dispatched by the backend.
- No route rewrite allows a public path to accidentally invoke a privileged method.
- Policies and route configs are reviewed together whenever services/methods change.
- Gateway-added headers are never treated as identity unless the backend authenticates the gateway and controls header origin.

If a gateway rewrites a path from a public route to an internal method, the server-side descriptor reflects the internal method invoked. Backend authorization must check that method against the actual principal. If the backend only trusts a public route name passed by the gateway via metadata, that configuration could be spoofed if requests arrive via another path.

## 8. Non-Existent Methods vs. Unauthorized Methods

Two cases must be distinguished:

- **Method exists but principal lacks permission:** the server dispatches to the registered method, and the authorization interceptor can return PERMISSION_DENIED.
- **Method is not registered on the server:** the transport/server typically finds no matching service/method and returns UNIMPLEMENTED; service interceptors may not run because there is no corresponding handler.

Therefore, do not rely on the authorization interceptor to handle every non-existent path. Monitor UNIMPLEMENTED errors at the transport/gateway layer if you want to detect clients calling wrong methods or probing APIs.

Never turn a non-existent method into allow simply because metadata claims a valid method. Never dispatch manually based on a method name inside the request body.

## 9. Keeping Policies Consistent When Contracts Change

Full method names depend on package, service, and method in proto. These changes can alter policy keys:

- Changing package, e.g. demo.orders.v1 to demo.orders.v2.
- Renaming a service or moving a method to another service.
- Renaming a method.
- Adding a new method.
- Splitting a generic method into methods with separate permissions.

When changing contracts:

1. Regenerate code and determine the new full method name from the generated descriptor.
2. Update exact policy mappings.
3. Decide permissions for new methods; deny by default if no rule exists yet.
4. Update gateway routes and service registrations.
5. Run allow/deny tests for old and new methods.
6. Check logs/metrics to detect callers still using old method names.

Do not use prefix matching to avoid updating policies. Having to declare new methods explicitly is a control that prevents API changes from inadvertently opening permissions.

## 10. Auditing Without Trusting Claimed Method Names

Audit logs should record the actual method from the server descriptor:

~~~java
String method =
        call.getMethodDescriptor().getFullMethodName();

audit.record(
        principal.subject(),
        method,
        decision.allowed(),
        decision.reasonCode());
~~~

Do not use client-sent x-method-name as the primary method field in audits. If you need to record the caller's claimed value to investigate spoofing attempts, log it separately under a name like claimedMethod, mark it untrusted, and never use it for policy decisions.

Useful audit fields include normalized principal ID, server-side full method name, decision, reason code, verified tenant, correlation ID, and policy version. Never log tokens, private keys, or full metadata.

Metrics should group by method/status/decision with controlled cardinality. Never use claimed method, user ID, or request ID as high-cardinality metric labels.

## 11. Testing Client Method-Name Spoofing

Tests must call through the real gRPC runtime or an in-process server with production interceptors. Two critical scenarios:

| Actual RPC | Forged metadata | Expected result |
| --- | --- | --- |
| OrderService/GetOrder | AdminService/DisableAccount | Policy evaluates GetOrder |
| AdminService/DisableAccount | OrderService/GetOrder | Policy evaluates DisableAccount and denies if lacking permission |
| Unregistered method | Valid method in metadata | Server does not dispatch by metadata; typically returns UNIMPLEMENTED |
| Valid method without policy | Another method name in request body | Deny-by-default for the actual method |

Example creating forged metadata on the client:

~~~java
Metadata.Key<String> claimedMethodKey =
        Metadata.Key.of(
                "x-method-name",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata forged = new Metadata();
forged.put(
        claimedMethodKey,
        "demo.orders.v1.OrderService/GetOrder");
~~~

Attach this metadata using a client interceptor or CallCredentials in tests, then call the generated stub for the administrative method. The server must still take the full method name from the ServerCall descriptor and return PERMISSION_DENIED if the principal lacks administrative permissions.

Add tests for:

1. Calling a read method with metadata claiming an administrative method; decision still uses the read method.
2. Calling an administrative method with metadata claiming a read method; decision still uses the administrative method.
3. Sending forged x-role/x-permissions; principal in Context remains unchanged.
4. New method without policy is denied.
5. Handler is not invoked when interceptor denies.
6. Gateway path rewrites are tested so the backend enforces policy for the final dispatched method.
7. Non-existent methods are observed as routing/UNIMPLEMENTED errors, never granted access by metadata.

## 12. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Create OrderService with GetOrder and CancelOrder; create AdminService with DisableAccount.
2. Create a principal verified by the authentication interceptor and stored in a shared gRPC Context key.
3. Build an exact-match policy using generated MethodDescriptor full method names.
4. Create AuthorizationServerInterceptor retrieving the method from call.getMethodDescriptor().getFullMethodName().
5. Send custom metadata x-method-name with an allowed method name while calling an administrative RPC; verify the server still denies.
6. Call a read RPC with metadata claiming an administrative method name; verify policy evaluates the actual read method.
7. Add a new method without a mapping and verify deny-by-default.
8. Test through a gateway with routing/rewrites and verify backend authorization uses the descriptor of the actual method.

### Self-Check Questions

**1. Why not use x-method-name from the client for authorization?**  
Because the client controls metadata and can declare an allowed method while invoking a different privileged method.

**2. Does the client choose the method using the HTTP/2 path?**  
Yes. The path is a protocol routing input; the server dispatches it to a registered method. Authorization must use the server-side descriptor after dispatch.

**3. Which API reliably retrieves the full method name in ServerInterceptor?**  
call.getMethodDescriptor().getFullMethodName().

**4. Is a generated stub a security mechanism?**  
No. Callers can use raw gRPC clients or HTTP/2 requests; the server must still enforce authorization.

**5. Why is exact match safer than startsWith?**  
Prefixes can accidentally allow new or administrative methods within the same service. Exact mapping requires each method to be granted explicitly.

**6. Does a non-existent method always pass through AuthorizationServerInterceptor?**  
Not necessarily. If the server cannot dispatch a service/method, the transport typically returns UNIMPLEMENTED before service interceptors run.

**7. Do gateway path rewrites affect authorization?**  
The backend must authorize the final method descriptor it dispatches, never trusting a route name declared by the client or gateway in metadata.

**8. Which method should audits record?**  
Record the full method name from the server-side descriptor; if logging the caller's claimed name for investigation, mark it clearly as untrusted.

## Summary

Never use a client-declared method name in metadata or request bodies as a basis for authorization. Clients select an RPC path to request a method, yet the server dispatches the path to a registered service/method and supplies the MethodDescriptor to interceptors. In Spring gRPC, retrieve the full method name via the ServerCall descriptor, match exact policies, and deny by default. Principals must originate from verified authentication; forged metadata must never alter identity or permissions. When gateway rewrites exist, the backend still checks the actual dispatched method. Tests should spoof method names, call privileged methods, and prove both policy and auditing always use the server-side descriptor.
