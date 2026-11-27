# Checking Authorization Before Business Actions

## Learning Objectives

After this lesson, you will be able to:

- Identify the authorization checkpoint in an RPC processing flow before executing side effects.
- Distinguish method-call permissions from permissions to act on a specific resource.
- Design the flow from authentication, principal, and policy decision to business action following the deny-by-default principle.
- Place authorization checks properly across the gRPC adapter, application service, and transaction.
- Prevent TOCTOU bugs when permissions depend on resource state that can change concurrently.
- Handle status codes, idempotency, auditing, async jobs, and streaming without bypassing authorization.
- Write tests proving that denied requests produce no side effects.

## 1. Why Check Permissions Before Business Actions?

In **SPRING_GRPC**, an RPC may read data, create orders, cancel orders, transfer funds, or change configuration. Successful authentication only tells you who the caller is; it does not prove the caller is allowed to perform a specific action.

**Checking authorization before business actions** means the server must verify all authorization conditions before performing any side effects of the use case. Side effects may include:

- Writing or updating data in a database.
- Emitting events, sending messages, or creating jobs.
- Calling payment, inventory, or external services.
- Generating export files, signed URLs, or new resources.
- Changing workflow state or sending notifications.

If permissions are checked after writing data or calling downstream services, returning **PERMISSION_DENIED** cannot undo the impact that already happened. A denied request must terminate before the business action starts.

Overview flow:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant I as Authentication / Authorization
    participant A as gRPC adapter
    participant U as Application use case
    participant P as Policy
    participant D as Database / downstream
    C->>I: RPC + credentials
    I->>I: Verify identity
    I->>A: Verified principal
    A->>U: Command + principal
    U->>P: Check method/resource permissions
    alt Allowed
        P-->>U: Allow
        U->>D: Business action in transaction
        D-->>U: Result
        U-->>C: Response
    else Denied
        P-->>U: Deny
        U-->>C: PERMISSION_DENIED
    end
~~~

Authorization must occur before the **side-effect boundary**. Some data reads to resolve the resource and policy may still be necessary; those reads must be tenant-scoped and must not expose unauthorized data.

## 2. Distinguishing Method Authorization from Resource Authorization

An authorization check may have two layers:

- **Method-level authorization:** may the principal invoke OrderService/CancelOrder?
- **Resource-level authorization:** may the principal cancel the exact order specified in the request?

For example, the **orders:cancel** permission allows a group of callers to request order cancellation. Yet the specific order may belong to another tenant, be owned by someone else, or already be in a non-cancelable state.

| Layer | Question | Example |
| --- | --- | --- |
| Authentication | Who is the caller? | service:order-operator is verified |
| Method authorization | Can the caller invoke this method? | Has orders:cancel |
| Resource authorization | Can the caller act on this resource? | Order belongs to an allowed tenant |
| Business invariant | Does the current state permit the action? | Order has not shipped yet |

Business invariants and authorization are related but distinct. A caller may be authorized to cancel an order, yet the order has already shipped; that is a business state error, typically represented by **FAILED_PRECONDITION**. Conversely, a caller lacking cancellation permission receives **PERMISSION_DENIED**.

## 3. Flow for Enforcing Permissions Before Side Effects

A data-mutating use case typically follows this sequence:

1. Verify credentials and construct the principal.
2. Check service/method call permissions.
3. Determine the tenant from the principal or validate the tenant selector.
4. Load the resource using a tenant-scoped query.
5. Evaluate permissions on the resource and relevant attributes.
6. Check business invariants.
7. Only after all conditions pass, perform the mutation.
8. Commit data and write outbox/events in the appropriate transaction.
9. Return the result and record the outcome.

Not every use case needs all nine steps. A read method may have no mutation; an operation independent of a specific resource can skip loading a resource. Never reverse the order so that side effects happen before authorization.

For resources outside the tenant, you may return **NOT_FOUND** to avoid disclosing whether the resource exists in another tenant. For resources within scope where the caller lacks permission, return **PERMISSION_DENIED**. Choose consistent semantics according to your threat model and API contract.

## 4. Placing Authorization in the Right Layer in Spring gRPC

Responsibilities should be divided cleanly:

| Layer | Responsibility |
| --- | --- |
| **Authentication ServerInterceptor** | Verify credentials, create a trusted principal, and place it into io.grpc.Context |
| **Authorization ServerInterceptor** | Check coarse-grained service/method permissions before the handler runs |
| **gRPC adapter** | Convert protobuf requests to commands, extract the principal, and invoke the use case |
| **Application service/use case** | Check resource permissions and orchestrate the business action |
| **Domain model** | Protect business invariants and valid state transitions |
| **Repository/database** | Scope data by tenant and support safe updates |

Interceptors fit policies shared across an entire method. For example, blocking every caller missing orders:cancel before the CancelOrder handler runs. However, interceptors should not hold all resource-level permission logic because request payloads, domain state, and related data are usually handled properly only in the application/domain layer.

A method can pass through both layers: the interceptor checks general permissions, and the use case checks ownership/tenant on the resource. Do not treat either layer as a complete replacement for the other.

## 5. Principal and Context: Permission Data Must Be Trusted

The principal must be built from verified credentials. Never take client-sent user_id, role, permissions, or tenant_id and treat them as identity.

Minimal principal example:

~~~java
package dev.example.security;

import java.util.Set;

public record GrpcPrincipal(
        String subject,
        String tenantId,
        Set<String> permissions) {

    public GrpcPrincipal {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        permissions = Set.copyOf(permissions);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

Declare a shared Context key:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

After authentication verifies the token/certificate, the interceptor attaches the principal:

~~~java
Context context = Context.current().withValue(
        GrpcSecurityContext.PRINCIPAL,
        verifiedPrincipal);

return Contexts.interceptCall(context, call, headers, next);
~~~

The adapter or application boundary can read the principal from the exact same key. If work is offloaded to a custom executor, propagate Context using APIs like Context.wrap or pass the principal/actor explicitly. Do not rely on custom ThreadLocals.

## 6. Example: Checking Permissions Before Canceling an Order

Suppose CancelOrder is a unary RPC. The interceptor already checked the orders:cancel method permission; the use case still needs to verify that the order belongs to the principal's tenant and is in a cancelable state.

~~~java
package dev.example.orders.application;

import dev.example.orders.persistence.OrderEntity;
import dev.example.orders.persistence.OrderRepository;
import dev.example.security.GrpcPrincipal;
import io.grpc.Status;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CancelOrderUseCase {

    private final OrderRepository orders;
    private final OrderResourceAuthorization authorization;
    private final OrderEventOutbox outbox;

    public CancelOrderUseCase(
            OrderRepository orders,
            OrderResourceAuthorization authorization,
            OrderEventOutbox outbox) {
        this.orders = orders;
        this.authorization = authorization;
        this.outbox = outbox;
    }

    @Transactional
    public CancelOrderResult execute(
            GrpcPrincipal principal,
            String orderId) {

        if (!principal.hasPermission("orders:cancel")) {
            throw Status.PERMISSION_DENIED
                    .withDescription("Permission denied")
                    .asRuntimeException();
        }

        OrderEntity order = orders
                .findByTenantIdAndIdForUpdate(
                        principal.tenantId(), orderId)
                .orElseThrow(() -> Status.NOT_FOUND
                        .withDescription("Order not found")
                        .asRuntimeException());

        authorization.requireCanCancel(principal, order);

        if (!order.isCancelable()) {
            throw Status.FAILED_PRECONDITION
                    .withDescription("Order cannot be cancelled")
                    .asRuntimeException();
        }

        // Business action begins only after permission and invariant checks.
        order.cancel();

        outbox.append(OrderCancelledEvent.from(order, principal.subject()));

        return CancelOrderResult.from(order);
    }
}
~~~

This example assumes the repository provides a tenant-scoped query with appropriate locking; OrderResourceAuthorization evaluates ownership/relationships; outbox writes the event in the same transaction. In real projects, the application service can throw dedicated domain exceptions and map them to gRPC statuses in an adapter/interceptor. Using io.grpc.Status directly in the use case is a simple choice for the example, not a mandatory architectural requirement.

The key point is never calling order.cancel() or outbox.append(...) before requireCanCancel. findByTenantIdAndIdForUpdate scopes data by tenant and keeps resource state stable within the transaction via database locking.

## 7. Avoiding TOCTOU Between Permission Checks and Business Actions

**TOCTOU** (time-of-check to time-of-use) occurs when the checked condition changes before the action uses that condition.

Example:

1. The server reads an order in PENDING state.
2. Policy allows the principal to cancel the order when it belongs to their tenant and has not shipped.
3. Another concurrent transaction transitions the order to SHIPPED.
4. The first request proceeds to cancel the order based on the stale state.

An accurate check at the start is insufficient if resource state changes before the mutation commits. Solutions depend on data and concurrency levels:

- Use transactions and pessimistic locks (SELECT ... FOR UPDATE) when locking the resource across check and mutation is needed.
- Use optimistic locking/versioning to detect whether the resource changed.
- Use conditional update statements including tenant, state, and version in the WHERE clause.
- For policies depending on mutable membership/relationships, define consistency levels and decision validity windows.

Conditional update example:

~~~sql
UPDATE orders
SET status = 'CANCELLED',
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :order_id
  AND status = 'PENDING'
  AND version = :expected_version;
~~~

If affected rows equals 0, the state or version changed, the resource does not belong to the tenant, or the condition is no longer met. Re-read in an appropriate transaction and return a result per contract; do not assume the update succeeded just because prior authorization allowed it.

For permissions purely based on the principal and policies immutable during the call, TOCTOU may be less complex. For permissions based on concurrently changing resource state, memberships, or quotas, explicit atomicity must be designed.

## 8. Authorization Before External Side Effects

Database writes are not the only business actions. A use case may call a payment provider, publish an event, or send an email. These side effects cannot be undone merely by rolling back a database transaction.

Safe sequence:

- Verify principal, permissions, and tenant before calling downstream services.
- Load the resource by tenant and check resource permissions.
- Check business state.
- Write data changes and outbox events in the same transaction if using a transactional outbox.
- A worker publishes the event after commit; the worker verifies service identity and tenant context before further processing.
- For direct downstream calls, consider sagas/compensation and idempotency; never issue commands before authorization.

Do not send emails, create payment intents, or publish events before checking permissions. If an external authorization service is unavailable, do not execute the business action on an assumption of allow.

## 9. Idempotency and Retries Must Not Bypass Authorization

gRPC clients or gateways may retry. Applications may also resend the same command when no response was received. An idempotency key prevents repeating side effects, but it does not replace authorization.

Order to enforce:

1. Authenticate the caller and determine the tenant.
2. Check that the caller has permission to invoke the operation and access the resource.
3. Scope the idempotency key within tenant/operation.
4. If a prior result exists, return it only if the current caller is still permitted to view that result.
5. Otherwise, execute the action once and store the result/idempotency record in the appropriate transaction.

Scope idempotency keys by tenant and operation type, e.g. (tenant_id, operation, key). Do not use a global client-supplied key without binding it to the tenant; two tenants must never collide or read each other's results.

A caller might have been authorized when creating the command but had permissions revoked before a retry. Policy must decide whether to re-check permissions on result replay; for sensitive data, always verify read permission when returning the response.

## 10. Async Jobs and Permissions at Execution Time

An RPC may simply create a job for later processing. Authorization before enqueuing is necessary, yet the worker running later may execute at a time when permissions have changed.

Clearly decide which model the job follows:

- **Delegated user action:** the job continues acting on behalf of the user. Store actor, tenant, operation, and minimal authorization context; the worker re-evaluates policy at execution time if permission revocation must take effect.
- **Service-owned operation:** the job becomes the service's responsibility once a valid command is accepted. The worker uses its own service identity with minimal permissions while preserving the command's tenant/resource scope.
- **Approved workflow:** operations requiring approval. The job executes only after a valid, active approval decision exists.

Do not store raw access tokens in queues for arbitrary reuse. Pass identity/references and tenant context in a protected internal schema; verify the producer and worker permissions. If the policy service fails at execution time, fail closed and keep the job in an appropriate retry/dead-letter state rather than executing the action.

## 11. Streaming: Check Before Opening and Before Each Action

With server-streaming, client-streaming, or bidirectional streaming, a single RPC can contain many messages and remain open for a long time.

- Check method call permissions before creating subscriptions or starting processing.
- For each message carrying a resource ID, check tenant/ownership before the corresponding side effect.
- Do not allow messages to change tenants arbitrarily if the contract does not support multi-tenant streams.
- When permissions are revoked, explicitly specify revalidation, duration limits, or cancellation.
- Terminate the stream and clean up buffers/subscriptions when a message is denied.
- Apply quotas/fairness so one tenant cannot monopolize another tenant's resources.

For example, UploadEvents may be allowed at the method level, yet each event must still verify it belongs to the principal's tenant before writing or emitting downstream. A single authorization check at stream open does not automatically authorize all subsequent operations.

## 12. Status Codes and Authorization Error Handling

Choose status codes to accurately reflect the error type:

| Situation | Commonly used gRPC status |
| --- | --- |
| Missing/invalid credential or no principal created | UNAUTHENTICATED |
| Principal verified but lacks permission | PERMISSION_DENIED |
| Resource does not exist in allowed tenant | NOT_FOUND |
| Resource exists but state disallows action | FAILED_PRECONDITION |
| Version/state conflict during mutation | ABORTED |
| Policy dependency cannot evaluate due to infrastructure error | UNAVAILABLE or infrastructure status per contract |

Never turn a policy dependency failure into allow. Also do not confuse "policy denied" with "policy service unresponsive": the first is an authorization decision, while the second is an infrastructure failure that may require controlled retries.

Status descriptions returned to clients should be brief and avoid exposing internal permissions, claims, tenant memberships, or sensitive resource details. Record detailed reasons in controlled audit logs.

## 13. Auditing and Observability

An authorization decision needs enough trace information for investigation without leaking secrets. You can log:

- Normalized subject/principal ID.
- Tenant ID per logging policy.
- Full method name and resource type/ID, redacted or pseudonymized when needed.
- Allow/deny decision and policy version.
- Correlation/trace ID, timestamp, and business action outcome.
- Categorized reason such as missing_permission, wrong_tenant, resource_state_denied.

Separate the **authorization decision** from the **business outcome**. A request may be allowed yet fail its business action due to state or a dependency; conversely, a denied request must produce zero mutations. Metrics should group by method, status, decision, and policy version with controlled cardinality; avoid putting user IDs, tokens, or request IDs into labels.

Auditing must not block interceptors with slow I/O. For actions requiring durable audits, specify whether the audit record commits with the business transaction or is published via an outbox. Never let an audit write failure accidentally turn a deny into an allow.

## 14. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Data changed yet client receives PERMISSION_DENIED | Permission checked after mutation | Move enforcement before side effects |
| Payment called before discovering missing permission | Downstream call placed before authorization | Verify method/resource before any external action |
| Caller has permission yet acts on wrong tenant | Only method checked, resource not scoped | Tenant-scoped queries and resource authorization |
| Permissions valid yet action used stale state | TOCTOU | Transactions, locks, versions, or conditional updates |
| Retry replays result to caller who lost permissions | Idempotency replay before authorization | Reauthorize before returning result |
| Async job runs with overly broad permissions | Worker uses shared service identity | Minimal service identity, tenant scope, and revalidation |
| Stream keeps acting after permission revocation | Only authorized at stream open | Revalidation/cancellation per policy |
| Policy dependency fails yet action runs | Fallback to allow | Fail-closed, no side effects when decision is indeterminate |
| Audit says deny yet database committed | Audit/decision and transaction out of sync | Make decision before action, record outcome via transaction/outbox |

## 15. Testing: Deny Must Mean Zero Side Effects

An authorization test should not merely assert status. It must prove no data changes, no events, and no downstream calls occur when a request is denied.

| Scenario | Expectation |
| --- | --- |
| Missing credential | UNAUTHENTICATED; use case does not run |
| Missing method permission | PERMISSION_DENIED; no unnecessary reads/mutations |
| Wrong tenant | Returns no data; no mutation |
| Has permission but caller does not own resource | NOT_FOUND or PERMISSION_DENIED per contract; no side effects |
| Has permission but invalid business state | FAILED_PRECONDITION; no mutation |
| Policy service unavailable | Fail-closed; no downstream calls |
| Two competing mutations | One mutation matches version/state; no invariant violation |
| Retry with same idempotency key | Single side effect; replayed result still passes authorization |
| Permission revoked before async execution | Worker obeys revalidation policy; never uses expired stale permissions |
| Streaming message accesses another tenant's resource | Message rejected; no side effects for that resource |

Useful testing techniques:

1. Use a mock/spy repository to confirm save/update is not called on deny.
2. Use mock downstream clients to confirm payment/event/email calls are not made.
3. Inspect database state before and after a denied request.
4. Verify the outbox has no events when authorization fails.
5. Run concurrency tests to catch TOCTOU and optimistic-lock conflicts.
6. Call through the generated stub and real interceptors in in-process or transport integration tests.
7. Check logs/audits as well to ensure no tokens or sensitive payloads are recorded.

## 16. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Create a CancelOrder unary RPC and a principal containing verified subject, tenant, and permissions.
2. Add an interceptor checking the orders:cancel permission before invoking the handler.
3. In the use case, query the order by tenant and ID, then check ownership/relationships.
4. Check cancelable state before calling order.cancel().
5. Use transactions/locks or optimistic versioning to prevent state changes between check and mutation.
6. Write the outbox event in the same transaction; verify no event is created when authorization denies.
7. Add a tenant/operation-scoped idempotency key and check authorization before replaying results.
8. Write tests for missing permission, wrong tenant, invalid state, policy unavailable, retries, and concurrent mutations.

### Self-Check Questions

**1. Why must authorization be checked before business actions?**  
Because side effects that already happened cannot be undone merely by returning PERMISSION_DENIED.

**2. Is method permission enough to cancel an order?**  
No. You must check tenant, ownership/relationships, and the business state of the specific order.

**3. Can a resource be loaded before authorization?**  
Loading may be needed to evaluate resource policy, but it must use a tenant-scoped query and avoid exposing data. Never mutate before authorization completes.

**4. What is TOCTOU?**  
A condition changing between time of check and time of use; mitigated with transactions, locks, versioning, or conditional updates.

**5. Does an idempotency key replace authorization?**  
No. You must authorize before executing or replaying results, and scope the key by tenant/operation.

**6. Does an async worker need to re-check permissions?**  
It depends on the delegated action model and revocation policy. Clarify whether the worker acts for the user or the service, preserve tenant scope, and revalidate when needed.

**7. If the policy service does not respond, may the action proceed?**  
No. If permissions cannot be evaluated, fail closed and produce no side effects.

**8. Which test proves authorization is placed correctly?**  
Assert the status from the gRPC client while confirming the database is unchanged, the outbox is empty, and downstream mocks are not called on deny.

## Summary

In Spring gRPC, authorization must be enforced before a use case executes side effects. Authentication creates a trusted principal; interceptors check method permissions; application services check tenant and resource permissions; the domain protects invariants; transactions/databases ensure mutations do not rely on stale state. Idempotency, async jobs, and streaming must preserve this exact order of checking permissions before actions. When policy cannot be evaluated, fail closed and perform no business actions. Tests must prove denied requests write no data, emit no events, and make no downstream calls.
