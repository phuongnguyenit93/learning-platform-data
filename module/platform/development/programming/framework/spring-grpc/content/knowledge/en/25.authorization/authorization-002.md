# Role, Scope, and Permission

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **role**, **scope**, and **permission** in a gRPC authorization model.
- Understand that a role describes a subject's capability group, a scope limits the permissions granted to an access token, and a permission represents a specific action.
- Read roles/scopes from verified credentials and convert them into a trusted principal.
- Design least-privilege policies for services and methods in Spring gRPC.
- Combine roles with scopes according to clear rules, defaulting to deny when claims or policies are missing.
- Enforce permissions using **ServerInterceptor** and **io.grpc.Context**.
- Distinguish method call permissions from tenant/resource permissions, test allow/deny cases, and audit decisions.

## 1. Three Concepts Answering Three Different Questions

In **SPRING_GRPC**, authentication verifies who the caller is; authorization decides what the caller is allowed to do. Role, scope, and permission are three concepts that frequently appear in authorization, but they are not synonymous and should not be used interchangeably.

| Concept | Question | Example |
| --- | --- | --- |
| **Role** | Which capability group does the subject belong to? | order-reader, order-operator, support-agent |
| **Scope** | Which API scope is the access token allowed to access? | orders.read, orders.cancel |
| **Permission** | Which specific action is allowed? | orders:read, orders:cancel |

You can visualize the conversion flow as follows:

~~~mermaid
flowchart LR
    A["Verified credential"]
    B["Subject's roles"]
    C["Access token's scopes"]
    D["Permission catalog / policy"]
    E["Effective permissions"]
    F["Service + method policy"]
    G["Allow or deny"]
    A --> B
    A --> C
    B --> D
    C --> D
    D --> E
    E --> F --> G
~~~

- **Role** typically groups related permissions together to manage subjects conveniently.
- **Scope** typically limits the permissions of an access token for a specific resource server/API, especially in OAuth 2.0.
- **Permission** is the unit that policy checks when deciding whether to allow an action.

For example, the **order-operator** role may be mapped to read and cancel order permissions. However, if the current access token only has the **orders.read** scope, then the token only allows the read portion. Scope limits the permissions usable in this call, even when the subject's role is broader.

## 2. Role: Subject's Capability Group

A role is a label describing a group of capabilities or responsibilities assigned to a user, service account, or workload. For example:

- **order-reader**: reads order information.
- **order-operator**: processes and cancels orders according to workflow.
- **support-agent**: looks up information to support customers.
- **system-admin**: performs certain administrative operations.

Roles simplify administration: instead of assigning dozens of permissions directly to each subject, the system assigns one or more roles and maps roles to permissions.

However, a role name does not grant permissions by itself. The server must have a policy defining which permissions that role grants, on which services/methods, and under what conditions. Do not write logic like **admin = allow all**, because it bypasses API scope, tenant boundaries, token scopes, and the principle of least privilege.

Roles may be issued by an identity provider or managed internally. Role claims have different names and structures across providers; some systems use **roles**, **groups**, or namespaced nested claims. Normalize claims at the authentication step into a unified principal model, rather than having each interceptor read raw claims on its own.

## 3. Scope: Boundary of an Access Token

In OAuth 2.0, a scope is a string representing the access range granted by the authorization server to a client. The resource server uses scopes to check whether the token has permission to call the corresponding API.

Example token with scopes:

~~~text
scope = "orders.read orders.summary"
~~~

This token may be allowed to read orders and view summaries, but does not have the **orders.cancel** scope. Even if the subject has the **order-operator** role, the current token should not be used to cancel orders if the policy requires the corresponding scope.

Points to remember:

- Scope is typically issued to an **access token**, not as a long-lived user role.
- Scope reflects the permissions negotiated between the client/resource server during token issuance.
- The claim name may be **scope**, **scp**, or an identity-provider-specific structure; read according to the issuer's contract.
- Scopes must be constrained by audience/resource server; a token issued for another API is not automatically valid for this gRPC service.
- Missing required scopes must be handled according to an explicit policy, typically deny.

Scope does not replace per-resource permission checks. **orders.read** may allow calling **GetOrder**, but it does not by itself indicate which tenant's orders the caller may read.

## 4. Permission: Specific Action Checked by Policy

A permission describes a controllable action, typically in the form **resource:action**:

~~~text
orders:read
orders:cancel
orders:watch
accounts:disable
reports:export
~~~

A permission should have stable meaning within the domain. Do not tie permission names directly to role names, because roles are groupings that may change; permissions describe actions performed by the service.

Example mapping:

| Role | Granted permissions |
| --- | --- |
| **order-reader** | orders:read, orders:watch |
| **order-operator** | orders:read, orders:watch, orders:cancel |
| **support-agent** | orders:read, customers:read |

Scopes are mapped to the same permission vocabulary:

| OAuth scope | Corresponding permission |
| --- | --- |
| **orders.read** | orders:read |
| **orders.watch** | orders:watch |
| **orders.cancel** | orders:cancel |
| **customers.read** | customers:read |

This mapping is the resource server's policy, not an automatic OAuth or gRPC rule. Name them clearly and version them when semantics change so clients, authorization servers, and services do not interpret them differently.

## 5. Safely Combining Roles and Scopes

There is no single way to combine roles/scopes that fits every system. What matters is that the policy clearly states what roles and scopes represent. For OAuth access tokens, a common safe model is:

1. Roles determine the permissions a subject may be granted based on responsibility.
2. Scopes determine the permissions the current token is allowed to use at the resource server.
3. Effective permissions are the intersection of both permission sets.
4. Method policy requires the corresponding effective permissions; lacking either a role grant or a scope grant results in denial.

Example:

~~~text
Role: order-operator
  -> orders:read
  -> orders:watch
  -> orders:cancel

Token scopes:
  -> orders.read
  -> orders.watch

Effective permissions:
  -> orders:read
  -> orders:watch

Result:
  GetOrder    -> allow
  WatchOrder  -> allow
  CancelOrder -> deny (token missing orders.cancel)
~~~

Intersection allows the token to restrict the subject's effective permissions. If a system uses roles as the sole permission source or does not use OAuth scopes, design a dedicated policy mode and state it explicitly. Never silently treat a missing scope as unrestricted, or combine roles and scopes with OR so that a narrow token still exercises broad role permissions.

### 5.1. Immutable Principal After Authentication

After verifying credentials, normalize the required information into a principal:

~~~java
package dev.example.security;

import java.util.Set;

public record GrpcPrincipal(
        String subject,
        Set<String> roles,
        Set<String> scopes,
        String tenantId) {

    public GrpcPrincipal {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        roles = Set.copyOf(roles);
        scopes = Set.copyOf(scopes);
    }
}
~~~

Declare a shared Context key so authentication and authorization read the exact same principal:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

The principal contains only verified and normalized data. **roles** and **scopes** must not be copied directly from a caller-declared custom metadata header. **tenantId**, if present, must also come from a verified claim/identity or a trusted policy store, not from a request field by default.

### 5.2. Verifying the Token Before Reading Roles and Scopes

The authentication layer must check credentials before creating a principal. For JWTs, typical steps include:

- Verify the signature with the appropriate key and allowed algorithm.
- Verify **iss** matches a trusted issuer.
- Verify **aud** contains this resource server/API.
- Verify **exp**, **nbf**, and time-based conditions.
- Verify token type and claims according to the issuer's contract.
- Normalize roles/scopes into defined strings; reject malformed claim types or structures.

Do not decode a JWT and trust the payload without verifying the signature. Do not treat a token ID or role claim as a permission simply because the claim name looks trustworthy. Once the token is valid, the authentication interceptor can attach the principal to **io.grpc.Context** for the authorization layer to use.

Core snippet to attach the verified principal to the shared Context key:

~~~java
Context context = Context.current().withValue(
        GrpcSecurityContext.PRINCIPAL,
        principal);

return Contexts.interceptCall(context, call, headers, next);
~~~

## 6. Building a Permission Catalog and Method Policy

The example below maps roles and scopes to permissions, then takes the intersection. Methods are identified by their full name **package.Service/Method**.

~~~java
package dev.example.security;

import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

@Component
public class GrpcPermissionPolicy {

    private final Map<String, Set<String>> roleGrants = Map.of(
            "order-reader",
            Set.of("orders:read", "orders:watch"),
            "order-operator",
            Set.of("orders:read", "orders:watch", "orders:cancel"));

    private final Map<String, Set<String>> scopeGrants = Map.of(
            "orders.read", Set.of("orders:read"),
            "orders.watch", Set.of("orders:watch"),
            "orders.cancel", Set.of("orders:cancel"));

    private final Map<String, Set<String>> methodRequirements = Map.of(
            "demo.orders.v1.OrderService/GetOrder",
            Set.of("orders:read"),
            "demo.orders.v1.OrderService/WatchOrder",
            Set.of("orders:read", "orders:watch"),
            "demo.orders.v1.OrderService/CancelOrder",
            Set.of("orders:read", "orders:cancel"));

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        Set<String> rolePermissions =
                expand(principal.roles(), roleGrants);
        Set<String> tokenPermissions =
                expand(principal.scopes(), scopeGrants);

        // Token scope restricts the permissions that roles can grant.
        rolePermissions.retainAll(tokenPermissions);

        Set<String> required =
                methodRequirements.get(fullMethodName);

        // Undeclared method policies are always denied.
        return required != null && rolePermissions.containsAll(required);
    }

    private Set<String> expand(
            Set<String> grants,
            Map<String, Set<String>> catalog) {

        return grants.stream()
                .map(catalog::get)
                .filter(permissions -> permissions != null)
                .flatMap(Set::stream)
                .collect(Collectors.toCollection(HashSet::new));
    }
}
~~~

In this example, **CancelOrder** requires both **orders:read** and **orders:cancel**; the token must have both corresponding scopes and the role must grant both permissions. An unmapped role or scope contributes no permissions. Methods absent from **methodRequirements** are denied.

Real-world policies may come from configuration, a database, or a policy engine. Control caching, updates, auditing, and behavior when the policy source fails. If policy cannot be evaluated, failing closed is usually safer than allowing automatically.

## 7. Enforcing Policy in ServerInterceptor

The authentication interceptor verifies the token and puts the principal into Context. The authorization interceptor reads the principal, retrieves the full method name, and checks permissions:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import static dev.example.security.GrpcSecurityContext.PRINCIPAL;

public final class RoleScopeAuthorizationInterceptor
        implements ServerInterceptor {

    private final GrpcPermissionPolicy policy;

    public RoleScopeAuthorizationInterceptor(
            GrpcPermissionPolicy policy) {
        this.policy = policy;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        GrpcPrincipal principal = PRINCIPAL.get();

        if (principal == null) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        String method =
                call.getMethodDescriptor().getFullMethodName();

        if (!policy.allows(principal, method)) {
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

The authentication interceptor must attach the principal using the exact **GrpcSecurityContext.PRINCIPAL**; the authorization interceptor reads the same key to retrieve the principal for the right RPC.

When no principal is present, return **UNAUTHENTICATED**. When the principal is authenticated but effective permissions do not satisfy the method policy, return **PERMISSION_DENIED**. Do not call **next.startCall(...)** after denying; if forwarded anyway, the service implementation still runs and the policy fails to protect the RPC.

Register interceptors in order so authentication runs before authorization. With the Spring gRPC starter, use the extension point of the version in use; verify the actual execution order with integration tests.

## 8. Method Permissions vs. Tenant and Resource Permissions

Roles/scopes/permissions usually determine whether a caller may invoke a type of method. They do not automatically prove the caller has rights to every resource specified in the request.

For example, **orders:read** allows calling **GetOrder**, yet the service must still check:

- Does the order belong to the principal's tenant?
- Does the subject have an ownership relationship or support assignment for this order?
- Is the order in a state that permits the operation?
- Is there a rule to hide resource existence to prevent ID enumeration?

Do not trust **tenant_id** or **owner_id** sent by the client as proof of permission. Cross-check the request against the verified tenant/relationship or trusted policy data. This is resource-level/domain authorization and should take place in the service/domain layer.

## 9. Roles, Scopes, and Permissions with Streaming RPCs

The authorization interceptor checks method permissions when the stream opens. However, a stream can carry multiple messages and multiple resource IDs.

For example:

- **WatchOrder** may require **orders:read** and **orders:watch** when opening the stream.
- If the stream watches multiple orders, each **order_id** still needs tenant/ownership verification.
- **UploadEvents** may require **events:write**; each event must still be checked for validity and data scope.
- When permissions are revoked while a long-lived stream is running, the system needs a clear policy: enforce only at stream open or revalidate periodically/per message.

If immediate revocation is required, checking only at stream open may not be enough. Consider limiting stream duration, periodic revalidation, or mechanisms to cancel subscriptions when identity/policy changes. When denying mid-stream, terminate with an appropriate status and clean up resources.

## 10. Least Privilege, Role Sprawl, and Policy Operations

Common design mistakes:

- **Overly broad roles:** admin is used to avoid designing granular permissions.
- **Duplicate roles:** many nearly identical roles, making auditing difficult.
- **Overly broad scopes:** a token has orders.* even though it only needs to read one method.
- **UI-coupled permissions:** permissions named after buttons/screens instead of domain actions.
- **Default-allow policy:** new methods automatically open to all principals.
- **Untrusted claim sources:** roles/scopes read from self-declared headers or unverified JWTs.
- **Caches without invalidation:** revoked permissions remain active for too long.

Organize roles by responsibility groups, scopes by API/resource server, and permissions by domain actions. Review mappings periodically, bound token/cache lifetimes appropriately for the risk level, and audit both role changes and allow/deny decisions.

Metrics should use method, status, and decision labels with controlled cardinality. Do not put subject ID, token, tenant ID, or request ID into metric labels. Logs may store principal ID and correlation ID per security policy, but must redact credentials and sensitive payloads.

## 11. Testing Roles, Scopes, and Permissions

Tests should verify both the computed permissions and whether the handler is invoked.

| Role | Token scope | Method | Result |
| --- | --- | --- | --- |
| order-reader | orders.read | GetOrder | Allow |
| order-reader | orders.cancel | CancelOrder | Deny: role lacks permission |
| order-operator | orders.read | CancelOrder | Deny: token lacks cancel scope |
| order-operator | orders.read orders.cancel | CancelOrder | Allow |
| No role | orders.read | GetOrder | Deny |
| order-operator | No scope | GetOrder | Deny |
| order-operator | orders.read | Undeclared method | Deny |
| order-operator | orders.read | GetOrder for another tenant | Domain layer deny |

Required test groups:

1. Tokens with invalid signature, issuer, audience, or expiration do not create a principal.
2. Valid role with missing scope limits effective permissions.
3. Valid scope without role grant is still denied by the intersection policy.
4. New method without mapping is denied.
5. Authentication runs before authorization; the handler is not called when denied.
6. Tenant/resource authorization is verified independently from method permissions.
7. Streaming checks method permissions on open and per-message resources when needed.
8. Audit records decisions without leaking tokens or sensitive metadata.

An in-process test can use a mock authenticator to create a principal with specific roles/scopes, call the generated stub, and assert the status. Place a mock/flag on the service implementation to verify the handler does not run when denied. For real JWT/mTLS setups, add tests over real transport to verify identity is established properly.

## 12. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Define **OrderService** with **GetOrder**, **WatchOrder**, and **CancelOrder**.
2. Create an immutable principal containing verified subject, roles, scopes, and tenant.
3. Build a permission catalog mapping **order-reader** and **order-operator** to order permissions.
4. Map scopes **orders.read**, **orders.watch**, and **orders.cancel** to their corresponding permissions.
5. Write a policy that computes effective permissions as the intersection of role grants and token scope grants.
6. Enforce method policy via ServerInterceptor; undeclared methods must be denied.
7. Add a domain check to prevent reading/canceling orders belonging to another tenant.
8. Write tests for broad role with narrow scope, broad scope with insufficient role, invalid token, new method, and streaming resource checks.

### Self-Check Questions

**1. How does a role differ from a permission?**  
A role groups a subject's capabilities; a permission describes a specific action that policy can check.

**2. What does scope usually represent in OAuth 2.0?**  
The access range granted to an access token for a client/resource server, rather than a user's long-lived role.

**3. Why can scope restrict a role?**  
A role may grant broad capabilities, while the current token is only granted part of that range. Taking the intersection prevents the token from exceeding its granted permissions.

**4. Should an admin role be treated as allow-all for every method?**  
Not by default. Permissions, services/methods, and additional conditions must be explicitly mapped; broad privileges must be constrained and audited.

**5. Does the orders:read permission allow reading every order?**  
No. It may allow calling the read method; tenant, ownership, and resource policies must still be checked.

**6. How should a new method without a policy be handled?**  
Deny-by-default until role/scope/permission mappings are declared and tested.

**7. Can scopes be checked only once when opening a streaming RPC?**  
Scopes may suffice for method-call permission, but each resource in messages still needs checking if the stream accesses multiple tenants/resources.

**8. What if the scope claim is absent from a token?**  
Follow the issuer's contract and published policy. Do not treat a missing scope as unrestricted; in a scope-required model, deny it.

## Summary

**Roles** group a subject's capabilities; **scopes** limit the range granted to an access token; **permissions** represent specific actions checked by the server. In Spring gRPC, authentication must verify credentials and normalize roles/scopes into a principal before authorization runs. Policy can map roles and scopes to permissions and take their intersection to bound effective permissions; services/methods without rules must be denied. Method permissions still need to be paired with tenant, ownership, and resource state checks in the domain layer, especially for streaming. Clear mapping design, deny-by-default, auditing, and testing combinations of roles/scopes help avoid granting broader access than the token or actual need allows.
