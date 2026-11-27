# Mapping Permission Failures to Status Codes

## Learning Objectives

After this lesson, you will be able to:

- Distinguish authentication errors, authorization denial decisions, and policy evaluation failures.
- Choose the appropriate gRPC status for each situation involving permissions, resource visibility, and business preconditions.
- Centralize mapping of application security exceptions to gRPC statuses in Spring gRPC.
- Return consistent errors from interceptors and service implementations without leaking policies, tokens, or sensitive data.
- Use structured error details when clients need stable error codes to handle.
- Distinguish retryable errors from permanent denials; never retry a write operation merely because the status is an error.
- Test statuses, trailers, error details, and verify that the business handler does not execute when denied.

## 1. Why Is Clear Mapping of Permission Failures Needed?

In **SPRING_GRPC**, authentication verifies who the caller is; authorization decides which services/methods or resources that principal may call or operate on. When a request fails, the client needs to know whether credentials were invalid, the caller lacked permissions, the resource was out of scope, or the system could not evaluate policy.

gRPC communicates RPC outcomes using a **status code**, optionally accompanied by a status description, trailers, or error details. If every security error becomes **UNKNOWN**, clients struggle to distinguish whether to re-authenticate, request permissions, or retry later. Conversely, if status messages are overly detailed, the server may disclose resource existence, internal permissions, or policy structure.

A good mapping simultaneously satisfies:

- **Correct semantics:** the status reflects the nature of the failure.
- **Stability:** clients can handle based on status codes rather than fragile description strings.
- **Safety:** never expose tokens, claims, policy rules, or tenant data.
- **Consistency:** the same error category maps identically across all RPCs.
- **Operability:** distinguish true denials from infrastructure failures preventing policy evaluation.

## 2. Distinguishing Authentication Failure from Permission Denial

The two primary statuses of the security flow are **UNAUTHENTICATED** and **PERMISSION_DENIED**.

| Situation | Status | Meaning |
| --- | --- | --- |
| Required credential not sent | **UNAUTHENTICATED** | Server could not verify the caller |
| Token has invalid signature, expired, wrong issuer or audience | **UNAUTHENTICATED** | Credential does not prove a valid identity |
| Invalid or unacceptable mTLS identity | **UNAUTHENTICATED** | Authentication did not succeed |
| Valid principal but missing method permission | **PERMISSION_DENIED** | Caller is authenticated, but policy denies |
| Principal not allowed to access tenant/resource | **PERMISSION_DENIED** or **NOT_FOUND** per concealment policy | Authorization decision evaluated and denied |
| Method has no rule in deny-by-default policy | **PERMISSION_DENIED** | No permission granted for that method |

Rule of thumb:

- **UNAUTHENTICATED:** the caller's identity has not been verified.
- **PERMISSION_DENIED:** the caller's identity is verified, but the caller is not permitted to perform the action.

Do not return **UNAUTHENTICATED** merely because the principal lacks a permission. Doing so misleads clients into thinking the token expired and may trigger continuous credential refreshes when the actual permission has simply not been granted.

Conversely, do not return **PERMISSION_DENIED** for a token with an invalid signature. The server cannot yet trust the principal declared in the token.

## 3. Mapping Authorization-Related Errors

Not every error near an authorization check is a permission denial. Distinguish policy decisions from data errors, business state errors, and infrastructure failures.

| Cause | Common appropriate status | Reason |
| --- | --- | --- |
| Missing/invalid credential | **UNAUTHENTICATED** | Caller is not authenticated |
| Missing permission or role grant | **PERMISSION_DENIED** | Policy evaluated and denied |
| Tenant not in verified membership | **PERMISSION_DENIED** | Caller has no rights in that tenant |
| Intentionally concealing out-of-scope resource | **NOT_FOUND** | Avoid revealing whether the resource exists |
| Resource exists but state disallows action | **FAILED_PRECONDITION** | Current business condition |
| Request contains malformed selector or parameter | **INVALID_ARGUMENT** | Invalid input, not yet a permission decision |
| Policy engine unreachable | **UNAVAILABLE** | System cannot render a decision |
| Policy evaluation exceeded deadline | **DEADLINE_EXCEEDED** | Call time budget expired |
| Caller canceled RPC during policy check | **CANCELLED** | Call was canceled |
| Quota/rate limit exceeded | **RESOURCE_EXHAUSTED** | Resource or traffic limit reached |
| Programming bug or broken internal invariant | **INTERNAL** | Server error, not a deny decision |

These statuses carry distinct semantics. For instance, **FAILED_PRECONDITION** should not replace **PERMISSION_DENIED** just because both prevent the business action from running. **RESOURCE_EXHAUSTED** fits quota/rate limits; it is not a generic status for callers lacking permissions.

### 3.1. Resource Concealment: When to Use NOT_FOUND?

Some APIs prefer not to disclose whether a resource exists in another tenant. For example, a tenant A caller requests GetOrder with an order ID belonging to tenant B. Returning **PERMISSION_DENIED** might confirm the order exists. An API can choose to return **NOT_FOUND**, the same as when a resource does not exist.

This is a security design choice, not a mandatory rule for all systems. Apply it consistently across read, update, delete, and related lookup APIs. If the contract needs to distinguish "resource does not exist" from "caller lacks permission," use **PERMISSION_DENIED** and accept the corresponding information disclosure.

Whichever approach you choose, the repository must still scope queries by tenant. Never run an unscoped global query and rely on returning **NOT_FOUND** to mask a data access bug.

### 3.2. Policy Deny vs. Policy Unavailable

Do not conflate these two situations:

- **Deny:** the policy engine returned an explicit result that the principal lacks permissions. Return **PERMISSION_DENIED**.
- **Indeterminate/unavailable:** the policy engine timed out, lost connectivity, or failed to evaluate. Never assume allow; fail closed and return an infrastructure status such as **UNAVAILABLE** or **DEADLINE_EXCEEDED**.

Clients may retry transient infrastructure errors within appropriate deadlines and retry policies. Clients should not indefinitely retry a **PERMISSION_DENIED** decision, because resending the same credentials under the same policy will not usually grant permissions.

## 4. Designing Internal Exceptions Before Mapping Statuses

The application should represent errors in business/security terms, then translate them to gRPC statuses at the boundary. This keeps the domain independent of gRPC description strings and prevents each service from picking different statuses.

Example categorized exceptions:

~~~java
package dev.example.security;

public final class AuthorizationDeniedException
        extends RuntimeException {

    public AuthorizationDeniedException() {
        super("Authorization denied");
    }
}
~~~

~~~java
package dev.example.security;

public final class AuthenticationRequiredException
        extends RuntimeException {

    public AuthenticationRequiredException() {
        super("Authentication required");
    }
}
~~~

~~~java
package dev.example.security;

public final class AuthorizationDependencyException
        extends RuntimeException {

    public AuthorizationDependencyException(Throwable cause) {
        super("Authorization dependency unavailable", cause);
    }
}
~~~

Internal exceptions may carry causes for logging and tracing. Never serialize stack traces, tokens, or policy objects into client responses.

If the application already has standard exception types, reuse them instead of creating a parallel exception hierarchy. The goal is to classify causes once and map consistently.

## 5. Centralizing Mapping to gRPC Status

A centralized mapper ensures gRPC adapters and interceptors use identical semantics:

~~~java
package dev.example.grpc;

import dev.example.security.AuthenticationRequiredException;
import dev.example.security.AuthorizationDeniedException;
import dev.example.security.AuthorizationDependencyException;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class GrpcStatusMapper {

    public StatusRuntimeException map(Throwable error) {
        if (error instanceof AuthenticationRequiredException) {
            return Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException();
        }

        if (error instanceof AuthorizationDeniedException) {
            return Status.PERMISSION_DENIED
                    .withDescription("Permission denied")
                    .asRuntimeException();
        }

        if (error instanceof AuthorizationDependencyException) {
            return Status.UNAVAILABLE
                    .withDescription("Authorization service unavailable")
                    .asRuntimeException();
        }

        if (error instanceof StatusRuntimeException grpcError) {
            return grpcError;
        }

        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }
}
~~~

Checking specific exception types before general fallbacks preserves exact semantics. In practice, add mappings for domain exceptions such as resource not found, failed precondition, quota exceeded, and cancellation; do not turn every RuntimeException into **PERMISSION_DENIED**.

Never return **error.getMessage()** arbitrarily to clients. Internal messages can contain SQL, permission names, tenant IDs, token fragments, or personal data. Use brief, stable public descriptions; log original exceptions on the server with redaction.

## 6. Mapping at the gRPC Boundary in Spring

There are two common places to translate exceptions into statuses:

- **ServerInterceptor:** suited for common RPC boundary failures such as missing principal, policy denial, or authentication errors.
- **gRPC adapter / exception handler:** suited for exceptions thrown inside application services when checking resources, state, or business rules.

Do not pass the same error through multiple mapping layers in ways that overwrite statuses or duplicate logs. Choose one owner for final mapping and ensure service exceptions become gRPC statuses before crossing the server boundary.

Adapter example:

~~~java
public GetOrderResponse getOrder(
        GetOrderRequest request) {

    try {
        GrpcPrincipal principal = requirePrincipal();

        return useCase.getOrder(
                principal,
                request.getOrderId());

    } catch (RuntimeException error) {
        throw statusMapper.map(error);
    }
}
~~~

This is a simplified example. A real adapter should catch the expected exception categories; unexpected exceptions must be logged on the server and mapped to **INTERNAL**, rather than masking all failures as a security status.

If your project's Spring gRPC starter provides exception advice/handlers, register the mapper via the extension point for that exact starter version. Do not assume all starters share identical annotations or handler ordering. Regardless of where it is wired, test the observed status through the generated stub.

## 7. Returning Statuses from the Authorization ServerInterceptor

When policy is evaluated directly in the interceptor, close the call with the appropriate status:

~~~java
if (principal == null) {
    call.close(
            Status.UNAUTHENTICATED
                    .withDescription("Authentication required"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}

if (!policy.allows(principal, fullMethodName)) {
    call.close(
            Status.PERMISSION_DENIED
                    .withDescription("Permission denied"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}
~~~

In the deny branch, do not call **next.startCall(...)**; the service implementation must not run. If the policy dependency is unavailable, close the call with **UNAVAILABLE** and a generic description. Do not convert a dependency error into **PERMISSION_DENIED**, because clients and operators need to distinguish "caller lacks permission" from "server could not evaluate permission."

If the authorization interceptor calls a policy engine asynchronously, coordinate deadlines and cancellation. When the caller cancels the call, avoid continuing costly work where safely interruptible; when the deadline expires, never allow simply because the policy check has not returned.

## 8. Structured Error Details and Trailers

Status codes suffice for most control flow. When clients need additional structured information, protobuf error details in **google.rpc.Status** and **Any** can be used if supported by the client/server ecosystem.

Common detail types:

| Detail type | Purpose |
| --- | --- |
| **ErrorInfo** | Stable error reason codes and controlled metadata |
| **RetryInfo** | Suggested wait duration before retrying |
| **ResourceInfo** | Resource type/name description when disclosure is permitted |
| **BadRequest** | Invalid input field details |
| **Help** | Links to vetted help documentation |

An example of a stable error code could be **AUTHORIZATION_DENIED**. Clients should rely on the status code and published reason code, not parse free-text descriptions like "Permission denied for orders:cancel".

Never include the following in error details/trailers:

- Access tokens, refresh tokens, private keys, or credentials.
- Full lists of the principal's roles/permissions.
- Policy expressions, internal rules, or security group names.
- Sensitive resource IDs/tenant IDs if the API conceals existence.
- Stack traces, SQL, or internal topology details.

Error details also traverse the network and may be logged by proxies/clients. Only include information the caller is allowed to know.

## 9. Retries, Token Refresh, and Client Behavior

Clients should handle statuses according to their semantics:

| Status | Typical appropriate client behavior |
| --- | --- |
| **UNAUTHENTICATED** | May refresh/reacquire credentials once via a supported flow; avoid infinite loops |
| **PERMISSION_DENIED** | Surface permission error or trigger access request workflow; do not retry repeatedly |
| **NOT_FOUND** | Treat as resource absent within the disclosed scope |
| **FAILED_PRECONDITION** | Require state or data changes before calling again |
| **UNAVAILABLE** | May perform bounded retries with backoff/jitter if operation is safe and deadline permits |
| **DEADLINE_EXCEEDED** | Review timeouts; do not assume the server operation did not occur |
| **RESOURCE_EXHAUSTED** | Respect quotas/rate limits and RetryInfo if returned |
| **CANCELLED** | Stop work tied to the call; do not trigger unintended retries |

**UNAUTHENTICATED** does not guarantee a token refresh will fix every error; tokens may be revoked or the client may lack permission for a new scope. **PERMISSION_DENIED** usually requires entitlement/policy changes, not resending the same request.

For RPCs with side effects, timeout or connection loss statuses do not prove the server did not commit. Retries require idempotency keys and safe method semantics. Never automatically retry CancelOrder, payments, or mutations merely because the client did not receive a response.

## 10. Status Mapping in Resource and Tenant Scenarios

Resource authorization often requires choosing between **PERMISSION_DENIED** and **NOT_FOUND** based on information disclosure policy:

- Use **PERMISSION_DENIED** when the API discloses that the resource exists but the caller lacks permission.
- Use **NOT_FOUND** when concealing resources outside the tenant/scope.
- Use **NOT_FOUND** when the resource does not exist within the verified tenant.
- Use **FAILED_PRECONDITION** when the caller has permission and the resource is in scope, but its current state disallows the action.

Crucially, status codes must never substitute for tenant-scoped queries. Repositories still need the tenant ID condition directly in the query. Do not load another tenant's resource and merely swap the status to **NOT_FOUND**; data may already enter caches, memory, or logs.

For cross-tenant administrators, if policy grants access, responses can use normal statuses, yet the operation must be audited by principal, target tenant, and method. Never let status mapping inadvertently become a permission-granting mechanism.

## 11. Auditing and Observability

A security decision must be observable without leaking secrets. Record:

- Full gRPC method name.
- Normalized principal ID or pseudonymous identifier per policy.
- Decision: allow, deny, or indeterminate.
- Stable reason category such as **missing_permission**, **wrong_tenant**, **policy_unavailable**.
- Final gRPC status and correlation/trace ID.
- Policy version if decisions must be investigated at a point in time.

Separate the **authorization decision** from the **transport outcome**. One call may be denied with **PERMISSION_DENIED**; another call may fail to evaluate policy due to **UNAVAILABLE**. Lumping both into a single "authorization failed" counter makes it hard for operators to spot policy dependency outages.

Never use high-cardinality user IDs, tokens, request IDs, or tenant IDs as metric labels. Logs must redact credentials and sensitive payloads. Public status descriptions never replace internal audit logs.

## 12. Common Mapping Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning **UNKNOWN** for all security errors | Client cannot tell authn from authz | Map **UNAUTHENTICATED** and **PERMISSION_DENIED** explicitly |
| Returning **UNAUTHENTICATED** for missing permission | Client refreshes token despite valid token | Use **PERMISSION_DENIED** |
| Returning **PERMISSION_DENIED** on policy engine timeout | Masks infrastructure outage as a denial | Fail closed with **UNAVAILABLE** or **DEADLINE_EXCEEDED** |
| Allowing when policy engine errors | Bypasses authorization | Fail closed, execute no action |
| Using **FAILED_PRECONDITION** for all denials | Wrong semantics and incorrect client handling | Reserve for unsuitable business state |
| Returning internal error messages | Leaks policy, SQL, or sensitive data | Generic descriptions, details in logs |
| Parsing descriptions on the client | Breaks when wording/language changes | Rely on status and stable reason codes |
| Retrying every error status | Useless retries on denials or duplicate side effects | Retry based on status, idempotency, and deadline |
| Returning NOT_FOUND without tenant-scoped query | Resource can still leak via side channels | Tenant predicate in repository/database |

## 13. Testing Status Mapping

Tests must go through the gRPC runtime to verify the status the client actually receives, not just check that a mapper returns an enum in a unit test.

| Scenario | Expected status | Handler/business action |
| --- | --- | --- |
| Missing credential | **UNAUTHENTICATED** | Not executed |
| Invalid token | **UNAUTHENTICATED** | Not executed |
| Principal lacks permission | **PERMISSION_DENIED** | Not executed |
| Method without policy | **PERMISSION_DENIED** | Not executed |
| Concealed out-of-tenant resource | **NOT_FOUND** per contract | No side effects |
| Resource in non-cancelable state | **FAILED_PRECONDITION** | No mutation |
| Policy service unavailable | **UNAVAILABLE** | Not executed |
| Policy check exceeded deadline | **DEADLINE_EXCEEDED** | Must not fall back to allow |
| Caller cancels | **CANCELLED** | Stop cancelable work |
| Quota exceeded | **RESOURCE_EXHAUSTED** | Do not execute limited action |

Tests should cover:

1. Unit tests for the exception-to-status mapper.
2. In-process integration tests through the generated stub and real interceptors.
3. Asserting status codes and reason codes without depending on free-text descriptions.
4. Verifying the handler is not invoked on authentication/authorization denial.
5. Verifying policy dependency errors do not allow business actions to run.
6. Verifying error details contain no tokens, permission catalogs, or sensitive tenant info.
7. Verifying clients do not infinitely retry **PERMISSION_DENIED**.
8. Verifying mutations use idempotency when retrying after timeout/connection loss.

## 14. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Define dedicated exceptions for authentication required, authorization denied, and policy dependency unavailable.
2. Create **GrpcStatusMapper** to map exceptions to gRPC statuses.
3. Configure the authentication interceptor to return **UNAUTHENTICATED** when credentials are invalid.
4. Configure the authorization interceptor to return **PERMISSION_DENIED** when the principal lacks permission and do not call **next.startCall**.
5. In the use case, distinguish out-of-tenant resources from invalid business state; map to **NOT_FOUND** or **FAILED_PRECONDITION** per contract.
6. Simulate a policy engine timeout and verify the server fails closed with an infrastructure status.
7. Add a stable error detail reason code without disclosing policies/credentials.
8. Write integration tests for every status in the table and confirm denials produce no side effects.

### Self-Check Questions

**1. When should UNAUTHENTICATED be used?**  
When the server cannot verify the caller's identity, such as missing or invalid credentials.

**2. When should PERMISSION_DENIED be used?**  
When the principal is verified, yet policy denies permission to call the method or act on the resource.

**3. Is an unreachable policy engine a permission denial?**  
No. The server could not evaluate policy; fail closed and return an infrastructure error such as **UNAVAILABLE** or **DEADLINE_EXCEEDED**.

**4. When can NOT_FOUND be returned instead of PERMISSION_DENIED?**  
When the API intentionally conceals the existence of out-of-scope resources, applied consistently while still tenant-scoping queries.

**5. Why should FAILED_PRECONDITION not be used for all permission errors?**  
Because this status represents that the current state does not satisfy conditions for executing the operation; it differs from an authorization denial.

**6. Should a client retry PERMISSION_DENIED?**  
Usually no. Entitlements or policy must change; resending the same credentials typically will not change the decision.

**7. Can raw exception messages be returned to the client?**  
No. Internal messages may contain policies, tokens, SQL, or sensitive data. Use generic descriptions and protected audit logs.

**8. How do you verify mapping works at runtime?**  
Call through the generated stub, assert status/trailers, and verify handlers/side effects do not run on authorization denial.

## Summary

Mapping permission failures to gRPC statuses requires distinguishing **unauthenticated** (**UNAUTHENTICATED**), **authenticated but denied** (**PERMISSION_DENIED**), and **unable to evaluate policy** (**UNAVAILABLE** or **DEADLINE_EXCEEDED**). **NOT_FOUND** can be used to conceal out-of-scope resources; **FAILED_PRECONDITION** is reserved for unsuitable business state. In Spring gRPC, standardize exceptions and mapping at the server boundary, avoid leaking policy details in descriptions/trailers, and only retry infrastructure errors when operations are safe. Integration tests must verify both the status received by the client and that business handlers do not execute or cause side effects on authorization denial.
