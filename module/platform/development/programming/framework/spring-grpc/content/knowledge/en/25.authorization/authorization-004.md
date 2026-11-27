# Tenant Isolation

## Learning Objectives

After this lesson, you will be able to:

- Explain tenant isolation and the risks when multiple tenants share a single gRPC service.
- Identify the tenant from verified identity and check whether the caller has permission to operate within that tenant.
- Prevent cross-tenant access at the service/domain, repository, and database layers.
- Safely propagate tenant context across gRPC interceptors, executors, and asynchronous tasks.
- Design caches, events, file storage, and streaming so tenant data is never mixed.
- Handle cases where administrators or workloads are allowed to access multiple tenants through explicit policy.
- Test tenant isolation using positive tests, negative tests, and concurrency tests.

## 1. Which Data Boundaries Does Tenant Isolation Protect?

In **SPRING_GRPC**, a service may serve multiple independent organizations, customers, or business units. Each unit is a **tenant**. Tenants may share the same process, database, gRPC endpoint, and infrastructure, yet one tenant's data and operations must be isolated from another's according to policy.

For example, the **OrderService/GetOrder** RPC may accept an order ID. If the server looks up the order by global ID alone, a caller belonging to tenant A could guess or know the ID of tenant B's order and read its data. This is a cross-tenant access bug even though the caller is authenticated and holds the **orders:read** permission.

Tenant isolation must protect multiple layers:

- **Identity:** which tenant is the caller operating under, and which tenants is the caller allowed to select?
- **RPC authorization:** is the caller allowed to invoke this method on this service?
- **Resource authorization:** does the requested resource belong to an allowed tenant or scope?
- **Persistence:** do data reads and writes always include a tenant predicate?
- **Infrastructure:** do caches, message brokers, object storage, search indexes, and logs preserve the same boundary?

~~~mermaid
flowchart TB
    A["gRPC request"] --> B["Authentication"]
    B --> C["Verified principal"]
    C --> D["Resolve and validate tenant"]
    D --> E["Method authorization"]
    E --> F["Tenant-scoped service"]
    F --> G["Repository query with tenant_id"]
    G --> H["Tenant data only"]
    D --> X["Reject invalid tenant"]
    E --> Y["Reject forbidden method"]
~~~

Successful authentication and method-call permission are not enough to access arbitrary resources. The tenant must be resolved and bound to every data operation.

## 2. Tenant Identity Must Come from a Trusted Source

A request may carry a tenant ID in the protobuf message or metadata. That value indicates which tenant the client wants to operate in; by itself, it does not prove the caller is allowed to access that tenant.

There are three common scenarios:

1. **One principal belongs to one tenant:** the tenant is determined from verified claims or internal identity mapping. The client does not need to select a tenant.
2. **One principal is a member of multiple tenants:** the client may send a selected tenant, but the server must verify that tenant is in the verified membership/entitlement list.
3. **Service-to-service workloads:** a workload's identity may be restricted to a single tenant or a group of tenants. Never assume internal workloads have access to all tenants by default.

Do not treat **x-tenant-id** or **tenant_id** in the request as the sole source of truth. If the architecture uses a header to choose a tenant, that header is only a **tenant selector**; the server must still verify the caller has the corresponding membership or permission.

Example immutable principal after authentication:

~~~java
package dev.example.security;

import java.util.Set;

public record TenantPrincipal(
        String subject,
        Set<String> allowedTenantIds,
        Set<String> permissions) {

    public TenantPrincipal {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        allowedTenantIds = Set.copyOf(allowedTenantIds);
        permissions = Set.copyOf(permissions);
    }

    public boolean canAccessTenant(String tenantId) {
        return allowedTenantIds.contains(tenantId);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

allowedTenantIds must be populated from verified credentials or a trusted membership lookup. When the number of tenants is large, you do not necessarily have to embed the entire list in a token; you can use a verified selected tenant, a membership service, or a policy engine. Either way, the server must have trustworthy evidence before executing queries.

## 3. Putting Tenant Context into gRPC Context

The authentication interceptor verifies credentials and places the principal into **io.grpc.Context**. Subsequent interceptors or handlers can read the principal per RPC.

Declare a shared key:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class TenantSecurityContext {

    public static final Context.Key<TenantPrincipal> PRINCIPAL =
            Context.key("tenant-principal");

    private TenantSecurityContext() {}
}
~~~

Once credentials are valid, the authentication layer can attach the principal:

~~~java
Context context = Context.current().withValue(
        TenantSecurityContext.PRINCIPAL,
        verifiedPrincipal);

return Contexts.interceptCall(context, call, headers, next);
~~~

In a handler or service, retrieve the principal from the exact same key:

~~~java
TenantPrincipal principal =
        TenantSecurityContext.PRINCIPAL.get();

if (principal == null) {
    throw Status.UNAUTHENTICATED
            .withDescription("Authentication required")
            .asRuntimeException();
}
~~~

Use the exact same Context.Key instance across the entire pipeline. Creating two different keys even with the same string name will not make them share values.

### 3.1. Resolving the Tenant per Request

If the principal has only one tenant, the service can use that tenant as the operation scope. If the principal belongs to multiple tenants, the request may select a tenant, but the server must verify membership before using it:

~~~java
package dev.example.security;

import io.grpc.Status;
import org.springframework.stereotype.Component;

@Component
public class TenantAccess {

    public String requireTenant(
            TenantPrincipal principal,
            String requestedTenantId) {

        if (principal == null) {
            throw Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException();
        }

        if (requestedTenantId == null
                || requestedTenantId.isBlank()
                || !principal.canAccessTenant(requestedTenantId)) {
            throw Status.PERMISSION_DENIED
                    .withDescription("Tenant access denied")
                    .asRuntimeException();
        }

        return requestedTenantId;
    }
}
~~~

This snippet assumes membership has already been loaded into the principal. If a membership service must be queried, set deadlines, use caching with TTL/invalidation, and handle errors fail-closed. Never fall back to a default tenant when the tenant selector is missing or invalid.

For APIs that allow only a single tenant per principal, do not accept a requested tenant ID from the client; using the verified tenant directly reduces error surface.

## 4. Enforcing Tenant Boundaries in Services and Repositories

An authorization interceptor can check general method permissions, yet it typically cannot read resource IDs inside the protobuf request before service processing. Therefore, checking a resource's tenant must reside in the service/domain and data access layers.

Suppose the orders table has a tenant_id column. The repository should require both tenant and resource ID:

~~~java
package dev.example.orders.persistence;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, String> {

    Optional<OrderEntity> findByTenantIdAndId(
            String tenantId,
            String id);
}
~~~

The service obtains the tenant from the verified principal, then runs a query with a tenant predicate:

~~~java
package dev.example.orders.service;

import dev.example.orders.persistence.OrderEntity;
import dev.example.orders.persistence.OrderRepository;
import dev.example.security.TenantPrincipal;
import io.grpc.Status;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderEntity getOrder(
            TenantPrincipal principal,
            String orderId) {

        String tenantId = requireTenant(principal);

        return repository.findByTenantIdAndId(tenantId, orderId)
                .orElseThrow(() -> Status.NOT_FOUND
                        .withDescription("Order not found")
                        .asRuntimeException());
    }

    private String requireTenant(TenantPrincipal principal) {
        if (principal == null) {
            throw Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException();
        }
        if (principal.allowedTenantIds().size() != 1) {
            throw Status.PERMISSION_DENIED
                    .withDescription("Tenant selection required")
                    .asRuntimeException();
        }
        return principal.allowedTenantIds().iterator().next();
    }
}
~~~

The service example above illustrates a single-tenant-per-principal model. For multi-tenant principals, resolve the selected tenant using **TenantAccess.requireTenant(...)** before calling the repository.

Avoid querying by ID first and comparing the tenant in Java afterward:

~~~java
// Do not use as the primary protection boundary:
OrderEntity order = repository.findById(orderId).orElseThrow();
if (!order.getTenantId().equals(tenantId)) {
    throw new AccessDeniedException("Denied");
}
~~~

Queries without a tenant constraint can bring sensitive data into memory, caches, or logs before the check occurs. Placing the tenant predicate directly in the query restricts the data fetched. Depending on anti-enumeration policy, returning **NOT_FOUND** for a resource that does not exist in the current tenant can avoid disclosing that the resource exists in another tenant; choose statuses consistent with your security contract.

## 5. Protecting Write Operations and Data Constraints

The tenant predicate must apply to reads, updates, and deletes alike. For updates, the tenant condition must be part of the statement or query condition:

~~~sql
UPDATE orders
SET status = :new_status
WHERE tenant_id = :tenant_id
  AND id = :order_id;
~~~

If the updated row count is 0, the resource does not exist in that tenant or cannot be updated under the current condition. Do not execute updates solely by ID.

Database-level safeguards:

- Set **tenant_id NOT NULL** on tenant-owned tables.
- Create composite indexes such as **(tenant_id, id)** to support scoped queries.
- Use tenant-scoped unique constraints, such as **(tenant_id, external_order_number)**, if order numbers only need to be unique within a tenant.
- Configure foreign keys/relationships to prevent records in tenant A from referencing records in tenant B.
- Consider Row-Level Security (RLS) if the database supports it and the application can set tenant context safely within transactions.

When using PostgreSQL RLS with session variables, set the tenant inside the exact transaction and ensure connection pools do not retain the previous request's context. Use transaction-local settings, reset safely, and test connection reuse. RLS is an additional defense-in-depth layer; the application must still verify tenant and permissions.

## 6. Tenant Isolation in Caches, Search, and Object Storage

Tenant boundaries do not stop at the database. A properly scoped query can still leak data if cache keys or storage paths omit the tenant.

| Component | Isolation rule |
| --- | --- |
| **Cache** | Include tenant in the key, e.g. tenant:{tenantId}:order:{orderId} |
| **Search index** | Enforce mandatory tenant filter on every query; do not rely solely on client-sent filters |
| **Object storage** | Verify tenant before creating/reading objects; use tenant-scoped namespaces/paths |
| **Idempotency key** | Scope keys by tenant and operation so different tenants do not collide |
| **Distributed lock** | Include tenant in the lock name if the operation belongs to a tenant |
| **Export/report** | Check tenant before generating files and when downloading files |
| **Metrics/logs** | Minimize tenant data; do not put high-cardinality tenant IDs into metric labels |

Example cache key:

~~~java
String cacheKey =
        "tenant:" + tenantId + ":order:" + orderId;
~~~

If the cache uses only the order ID, one tenant could receive a result cached by another tenant when IDs are not globally unique or when cache namespaces are shared. Tenant must be part of data identity at every layer.

For object storage, do not let clients pick arbitrary paths. The server verifies permissions and constructs keys by tenant and resource, while also checking permissions at download time. Signed URLs must also have short lifetimes, specific object scope, and only be issued after authorization.

## 7. Tenant Context Across Async Processing and Message Brokers

gRPC Context can be propagated across grpc-java callbacks, but it does not automatically propagate across arbitrary executors, thread pools, or message brokers.

When offloading work to a separate executor, wrap the task with Context:

~~~java
Context current = Context.current();

executor.execute(current.wrap(() -> {
    TenantPrincipal principal =
            TenantSecurityContext.PRINCIPAL.get();

    processTenantWork(principal);
}));
~~~

When publishing events, the tenant must be attached to the event envelope according to a controlled internal schema:

~~~json
{
  "eventId": "evt-123",
  "tenantId": "tenant-a",
  "eventType": "OrderCreated",
  "aggregateId": "order-42"
}
~~~

Consumers should not trust a tenant field merely because it appears in the payload. Authenticate the producer/channel, verify the tenant matches the workload and event subscription, and then use that tenant to scope all queries. Even if broker topics are separated by tenant, verify publish/consume permissions and prevent tenant A from publishing forged events carrying tenant B.

Outboxes, retry queues, dead-letter queues, and scheduled jobs must also preserve tenant context. If tenant context is lost on retry, tasks could run under a default tenant or the wrong tenant.

## 8. Tenant Isolation for Streaming RPCs

A streaming RPC can be long-lived and process many messages. Checking the tenant when opening the stream is only sufficient when the entire stream is bound to a single tenant and every message obeys that binding.

- Resolve the tenant from the principal or a verified tenant selector when opening the stream.
- If messages contain resource IDs, query resources with a tenant predicate on every message.
- Do not let clients switch tenants mid-stream unless the contract explicitly supports it.
- When a stream serves multiple tenants, require an explicit multi-tenant policy and verify each tenant/resource.
- When permissions or memberships are revoked, decide whether to revalidate periodically or terminate the stream.
- Clean up subscriptions, buffers, and workers when the client cancels or authorization is denied.

For example, server-streaming **WatchOrder** should create subscriptions keyed by **(tenantId, orderId)**, not order ID alone. If a stream receives commands for multiple orders, each command must have its tenant verified before executing side effects.

Flow control and cancellation also relate to isolation: one tenant must not monopolize all buffers or workers of other tenants. Apply per-tenant quotas, concurrent stream limits, and fairness to prevent noisy neighbors.

## 9. Multi-Tenant Access and Cross-Tenant Administration

Some actors have legitimate needs to access multiple tenants, such as support agents, operators, or administrative systems. This is a privileged capability and requires explicit policy.

- The principal must hold a dedicated permission such as **tenants:support** or **tenants:admin**.
- Target tenants must still be selected and verified against membership/assignment.
- Every cross-tenant operation must be audited with subject, target tenant, method, resource, and reason.
- Restrict allowed methods; support permission to read data does not implicitly include exporting or modifying data.
- Consider requiring step-up authentication or approval for sensitive operations.
- Never use a tenant wildcard or default tenant as a way to bypass checks.

For service-to-service calls, a workload may be granted an explicit list of tenants or permission to handle a group of tenants. Scope must be limited by purpose and audience; a valid certificate only verifies workload identity, and does not automatically grant access to all tenants.

## 10. Common Issues and Diagnostics

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Tenant A user reads tenant B order | Query uses only resource ID | Require tenant predicate in repository |
| Request with another tenant is still processed | Client-supplied tenant ID or header trusted | Verify membership against verified principal |
| Cache returns another tenant's data | Cache key omits tenant | Namespace keys by tenant and resource |
| Cross-tenant update/delete | Statement filters only by ID | Include tenant in WHERE clause and check affected rows |
| Search returns mixed-tenant results | Missing mandatory tenant filter | Apply server-side filter on every query |
| Async task runs under wrong tenant | Context not propagated to executor | Use Context.wrap or verified event envelope |
| Tenant B event processed as tenant A | Consumer trusts tenant in payload | Verify producer and scope tenant before processing |
| Streaming reads out-of-tenant resources | Only checked tenant at stream open | Check each resource/message |
| Connection pool retains old tenant | DB session variable not reset | Use transaction-local context and test connection reuse |
| Support agent has overly broad access | Cross-tenant permission unrestricted by method | Separate permissions, scopes, approvals, and auditing |

When investigating, trace the tenant from verified credentials through Context, tenant resolver, service, repository queries, and cache/storage keys. Do not just check whether the request sent the right tenant ID; prove the server bound that tenant to the principal across every data layer.

## 11. Testing Tenant Isolation

Tests must prove tenant A cannot read, modify, delete, search, or receive events belonging to tenant B. Core tests include:

| Test | Expectation |
| --- | --- |
| Principal A reads order A | Succeeds |
| Principal A reads order B using valid ID | Returns no data from B |
| Principal A sends tenant selector B without membership | PERMISSION_DENIED |
| Multi-tenant principal selects an allowed tenant | Succeeds per policy |
| Principal missing tenant identity | Rejected; no fallback to default tenant |
| Update/delete using another tenant's ID | Zero rows affected |
| Cache same resource ID across two tenants | Two distinct keys and isolated results |
| Search query omits tenant filter from client | Server still enforces tenant filter |
| Tenant B event arrives at consumer allowed only for A | Rejected or quarantined |
| Tenant A stream sends resource B | Message rejected, stream cleaned up properly |
| Two concurrent requests for different tenants | No Context, response, or cache mixing |
| DB connection is reused | No leftover tenant setting from previous transaction |

Use test data with identical resource IDs in two tenants when the schema permits; this catches false assumptions that IDs are globally unique. For databases, verify SQL/repository behavior and affected rows directly. For caches, brokers, and storage, test keys/namespaces explicitly. Add integration tests through the gRPC runtime to confirm interceptors, Context, and services work together properly.

## 12. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Create **TenantPrincipal** containing subject, allowed tenant IDs, and verified permissions.
2. Create a shared gRPC Context key and attach the principal in the authentication interceptor.
3. Write **TenantAccess** to validate the tenant selector against the principal's membership.
4. Create repository method **findByTenantIdAndId** and avoid single-ID lookups for tenant-owned resources.
5. Add tenant predicates to updates/deletes and composite uniqueness for tenant-scoped data.
6. Include tenant ID in cache keys, object storage keys, and event envelopes; verify on the consumer side.
7. For **WatchOrder**, check tenant per resource and clean up on cancellation/denial.
8. Write integration tests for cross-tenant reads/writes, cache collisions, async context, and concurrent calls.

### Self-Check Questions

**1. Does a tenant ID in the request prove the caller belongs to that tenant?**  
No. It is only a tenant selector. The server must verify the caller has membership or permission for that tenant.

**2. Why must repositories accept both tenant ID and resource ID?**  
To restrict data directly in the query, avoiding fetching another tenant's resource before checking it in Java.

**3. Is an authorization interceptor alone enough to protect tenants?**  
Not completely. The interceptor checks general method permissions; resources/tenants must be enforced in the service and data access layers.

**4. Why must tenant be included in cache keys?**  
So an identical resource key or ID never causes one tenant's data to be served to another tenant.

**5. What must be watched when using database RLS with connection pools?**  
Tenant settings must be transaction-scoped and safely reset; never allow reused connections to carry stale tenant context.

**6. Is a single tenant check when opening a streaming RPC enough?**  
Only if the stream is bound to a single tenant and every message respects that binding. If messages reference other resources, per-message checks are required.

**7. Can a support agent access all tenants?**  
Only when policy explicitly grants cross-tenant permissions, restricts methods/resources, and audits every operation.

**8. How do you prove tenant A cannot read tenant B's data?**  
Invoke the same RPC with principal A and resource ID B, verify no data is returned, no side effects occur, and all caches/queries are tenant-scoped.

## Summary

**Tenant isolation** ensures callers only operate on data belonging to tenants permitted by their verified identity. In Spring gRPC, authentication creates the principal and Context; a tenant selector from a request may only be used after verifying membership. Services/repositories must include the tenant in all read/write queries, while caches, search, object storage, events, and streaming must uphold the same boundary. Method-call permissions do not replace resource authorization. Cross-tenant cases require dedicated permissions, restrictions, and auditing. Cross-tenant, concurrency, and connection-reuse tests help uncover leak paths that single-RPC tests miss.
