# Enforcing Record-Level Access Control and Tenant Boundaries

In a Spring Data R2DBC application, authenticating the user only answers the question "who is sending the request?". The application must also determine what that user is allowed to do with the specific record being requested. A logged-in user can still try changing an ID in the URL to read, modify, or delete someone else's data. If a repository queries solely by ID without restricting tenant, owner, or sharing permissions, the API becomes vulnerable to Broken Object Level Authorization (IDOR/BOLA).

**Record-level access control must be enforced on every data read and write path.** The tenant and principal must come from the authenticated context and then be included in query predicates or reinforced by database policies. Never rely on a `tenant_id`, `owner_id`, or `role` sent by the client in the request body.

Spring Data R2DBC provides reactive query execution and transactions, but does not automatically apply authorization to every repository method. Applications must enforce data boundaries end-to-end across Spring Security, tenant context, services, repositories, and the database. This lesson focuses on record-level authorization and tenant isolation for reading, creating, updating, deleting, querying relationships, and asynchronous processing.

## 1. Distinguishing Authentication, Authorization, and Tenant Isolation

These three concepts are related but answer different questions:

| Concept | Question | Example |
| --- | --- | --- |
| Authentication | Who is making the request? | User with subject `user-42` |
| Authorization | Is that user allowed to perform this action? | Holds `ORDER_READ` permission |
| Tenant isolation | Within which data scope may the request operate? | Only tenant `20`'s data |

Record-level authorization adds one more question: does the user have rights on this exact record? For example, two users both belong to tenant 20, yet only the creator or a shared collaborator may edit a private document.

A request can pass authentication and still need to be rejected because:

- The user does not belong to the requested tenant.
- The user belongs to the tenant but lacks permission for the action.
- The user has general permission but does not own the record.
- The record is shared with a different group that does not include the current user.
- The record is locked, archived, or in a state that forbids modification.

Never collapse all of these conditions into a single role check.

## 2. IDOR/BOLA: Why Checking Login Alone Is Not Enough

Suppose an API exposes the endpoint:

~~~http
GET /api/orders/481
~~~

The controller calls:

~~~java
return orderRepository.findById(481L);
~~~

If ID 481 belongs to another tenant or another user, the repository will still return the data. Requiring authentication on the endpoint only proves the caller logged in; it does not prove the caller has rights to read order 481.

A common attack flow:

1. User A logs in legitimately and reads their own order 481.
2. User A changes the ID to 482 in the URL or request body.
3. The server queries by ID without checking tenant/owner/ACL.
4. The server returns data belonging to User B or another tenant.

This is an object-level authorization flaw. Whether the ID is sequential, a UUID, or a hard-to-guess string, ID substitution must still be defended against. Unpredictable UUIDs do not replace authorization.

### 2.1. Never treat hard-to-guess IDs as access control

UUIDs reduce sequential ID enumeration, yet IDs can still leak through logs, shared links, events, emails, or browser history. Any ID supplied by a client must undergo server-side permission checks.

### 2.2. Never enforce permissions solely in the UI

Hiding an Edit button or omitting a Delete link only improves user experience. An attacker can still send direct HTTP requests via curl, Postman, or scripts. Final enforcement must reside in the backend and database.

## 3. Building Tenant Context from a Trusted Identity

A tenant ID in a header, path, or body is merely what the client requests—not proof that the caller is allowed to access that tenant.

Safe flow:

~~~text
HTTP request
    |
    v
Authenticate principal
    |
    v
Resolve requested tenant
    |
    v
Verify principal membership and tenant status
    |
    v
Build trusted request context
    |
    v
Authorize action and record
    |
    v
Execute tenant-scoped R2DBC query
~~~

For example, a user belongs to tenant 10 and tenant 20. A request selecting tenant 20 is accepted only after the server verifies an active membership and confirms the user is permitted to act in that tenant.

### 3.1. Tenant context must never come straight from the payload

Avoid:

~~~java
public Mono<Order> create(CreateOrderRequest request) {
    Order order = new Order();
    order.setTenantId(request.tenantId());
    order.setCustomerId(request.customerId());
    return orderRepository.save(order);
}
~~~

A client can alter `tenantId` in JSON to create data inside another tenant.

Instead, obtain the verified tenant from the context:

~~~java
public Mono<Order> create(CreateOrderRequest request) {
    return tenantContext.currentTenantId()
            .flatMap(tenantId -> {
                Order order = Order.newOrder(
                        tenantId,
                        request.customerId(),
                        request.totalAmount());
                return orderRepository.save(order);
            });
}
~~~

If an endpoint lets an administrator select a target tenant, that is a separate administrative use case. The server must check cross-tenant permissions, audit the actor and source/target tenants, and scope the operation tightly.

### 3.2. Verifying membership on the server

A simple model uses a membership table:

~~~sql
CREATE TABLE tenant_memberships (
    tenant_id BIGINT NOT NULL,
    user_id VARCHAR(120) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);
~~~

Before building the tenant context, the service verifies membership:

~~~java
public Mono<TenantContextData> resolveTenant(
        String userId,
        Long requestedTenantId) {

    return membershipRepository
            .findActiveMembership(userId, requestedTenantId)
            .switchIfEmpty(Mono.error(new TenantAccessDeniedException()))
            .map(membership -> new TenantContextData(
                    requestedTenantId,
                    userId,
                    membership.role()));
}
~~~

Do not cache memberships indefinitely. When a user's access is revoked, a stale cache can keep permitting access. If you cache memberships, define TTL, invalidation, and behavior when the authority source is unavailable.

## 4. Propagating Principal and Tenant in a Reactive Pipeline

WebFlux and Reactor can switch threads during execution. Never rely on `ThreadLocal` to hold the current tenant or user. Reactor `Context` travels with the subscription and is suited for passing context data through reactive pipelines.

### 4.1. Minimal tenant context

~~~java
public record RequestTenant(
        Long tenantId,
        String userId
) {
}

public final class TenantContext {

    public static final String KEY = "requestTenant";

    private TenantContext() {
    }

    public static Mono<RequestTenant> current() {
        return Mono.deferContextual(context -> {
            if (!context.hasKey(KEY)) {
                return Mono.error(new IllegalStateException(
                        "Trusted tenant context is missing"));
            }
            return Mono.just(context.get(KEY));
        });
    }
}
~~~

Once authentication and membership checks complete, a filter or service boundary can write the verified object into the Reactor `Context`:

~~~java
return chain.filter(exchange)
        .contextWrite(context -> context.put(
                TenantContext.KEY,
                trustedTenant));
~~~

This outlines where context propagation occurs; your `WebFilter` implementation must ensure the tenant is resolved before the business pipeline executes. Never copy a `trustedTenant` from a header while skipping membership authorization.

### 4.2. Reactive Security Context

With Spring Security WebFlux, you can obtain the principal via `ReactiveSecurityContextHolder`:

~~~java
public Mono<String> currentUserId() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
}
~~~

In production applications, map the principal into a stable identity type carrying verified user ID, tenant memberships, and permissions. Never use mutable display names or emails as authorization keys.

### 4.3. Context is not the sole authorization mechanism

Reactor `Context` propagates verified identity between steps. It does not automatically ensure queries include a tenant predicate. Repositories must still include `tenantId` in SQL, or the database must enforce policies based on transaction context.

## 5. Designing Schemas to Preserve Tenant Boundaries

In a shared schema, tenant-scoped tables should include `tenant_id`. Keys and relationships must prevent cross-tenant references.

Example:

~~~sql
CREATE TABLE customers (
    id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(160) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_customers_tenant_id UNIQUE (tenant_id, id)
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    owner_user_id VARCHAR(120) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer_same_tenant
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, id)
);
~~~

A composite foreign key over `(tenant_id, customer_id)` stops an order in tenant A from referencing a customer in tenant B, even if application code passes the wrong ID.

### 5.1. Tenant-scoped unique constraints

If order numbers only need to be unique within a tenant:

~~~sql
CREATE UNIQUE INDEX uk_orders_tenant_number
ON orders (tenant_id, order_number);
~~~

Use global unique constraints only when uniqueness must hold system-wide, such as globally unique emails. Uniqueness rules should reflect business semantics rather than making every field globally unique by default.

### 5.2. Indexes supporting authorization predicates

If queries commonly filter by tenant and owner:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = :tenantId
  AND owner_user_id = :userId
  AND id = :orderId;
~~~

An appropriate index might be:

~~~sql
CREATE INDEX ix_orders_tenant_owner_id
ON orders (tenant_id, owner_user_id, id);
~~~

Index column order should match actual queries and execution plans. With ACL tables, create indexes for both resource-centric and principal-centric lookups.

## 6. Every Read Query Must Carry an Access Scope

Do not expose generic repository `findById` methods to tenant-scoped flows where services might accidentally call them without checking the tenant.

Repository:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Mono<Order> findByIdAndTenantId(Long id, Long tenantId);

    Mono<Order> findByIdAndTenantIdAndOwnerUserId(
            Long id,
            Long tenantId,
            String ownerUserId);

    Flux<Order> findAllByTenantIdAndOwnerUserId(
            Long tenantId,
            String ownerUserId);
}
~~~

Service:

~~~java
public Mono<Order> findOwnedOrder(Long orderId) {
    return TenantContext.current()
            .flatMap(context -> orderRepository
                    .findByIdAndTenantIdAndOwnerUserId(
                            orderId,
                            context.tenantId(),
                            context.userId()));
}
~~~

The query returns empty if no row matches every condition. The controller can return `404` so it does not disclose whether a record exists in another tenant.

### 6.1. Never load a record globally and check ownership afterward

Avoid:

~~~java
return orderRepository.findById(orderId)
        .flatMap(order -> {
            if (!order.getOwnerUserId().equals(currentUserId)) {
                return Mono.error(new AccessDeniedException("Forbidden"));
            }
            return Mono.just(order);
        });
~~~

This snippet loads the entity before checking permissions. If the entity holds sensitive fields, logging, tracing, callbacks, or intermediate mapping steps can accidentally process data the caller is not allowed to read. Push tenant/owner predicates into the database query from the start.

Post-load checks may occasionally be necessary for complex policies, yet the query should still filter by tenant and project only needed columns. Never return an entity before authorization completes.

### 6.2. Native queries must include tenant conditions themselves

Example `@Query`:

~~~java
@Query("""
       SELECT *
       FROM orders
       WHERE id = :orderId
         AND tenant_id = :tenantId
         AND owner_user_id = :userId
       """)
Mono<Order> findOwnedOrder(
        @Param("orderId") Long orderId,
        @Param("tenantId") Long tenantId,
        @Param("userId") String userId);
~~~

With `DatabaseClient`, bind tenant and principal values as parameters. Never concatenate user or tenant values directly into SQL strings.

## 7. Every Write Operation Must Also Be Scoped

A common mistake is putting tenant predicates on `SELECT` while running `UPDATE` or `DELETE` by ID alone. An attacker unable to read a record could still modify or delete it by guessing IDs.

### 7.1. INSERT

Tenant and owner must be assigned from the trusted context:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return TenantContext.current()
            .flatMap(context -> {
                Order order = Order.newOrder(
                        context.tenantId(),
                        context.userId(),
                        command.customerId(),
                        command.totalAmount());
                return orderRepository.save(order);
            });
}
~~~

If the command includes `tenantId` or `ownerUserId`, ignore those fields or reject the request per your API contract. Clients should supply only business fields they are allowed to choose.

### 7.2. UPDATE

Conditional updates should include tenant and owner checks:

~~~java
@Modifying
@Query("""
       UPDATE orders
       SET status = :status,
           last_modified_at = :modifiedAt
       WHERE id = :orderId
         AND tenant_id = :tenantId
         AND owner_user_id = :userId
       """)
Mono<Integer> updateOwnedOrder(
        @Param("orderId") Long orderId,
        @Param("tenantId") Long tenantId,
        @Param("userId") String userId,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt);
~~~

The service must inspect the updated row count. For a unique ID, the expected count is `1`. A count of `0` may mean the resource does not exist, belongs to another tenant, or the caller is not the owner. Returning a generic `404` prevents existence disclosure; if the API requires `403`, implement a safe way to distinguish the cases.

### 7.3. DELETE

`DELETE` must also restrict tenant and permissions:

~~~sql
DELETE FROM orders
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND owner_user_id = :userId;
~~~

Do not rely on the controller checking permissions first and then calling a global `deleteById(orderId)`. Keep the authorization condition inside the mutating statement to reduce races between check and write.

### 7.4. Soft delete

For soft delete:

~~~sql
UPDATE orders
SET deleted_at = :deletedAt,
    deleted_by = :userId
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND owner_user_id = :userId
  AND deleted_at IS NULL;
~~~

Every subsequent read query must enforce consistent rules on `deleted_at`. Never let an endpoint forget this predicate and accidentally return soft-deleted data. If administrators can restore records, treat that as a separate permission and keep it tenant-scoped.

## 8. Role, Permission, and Ownership Rules

Roles usually represent groups of privileges, such as `TENANT_ADMIN`, `ORDER_MANAGER`, or `MEMBER`. Permissions represent specific actions, such as `ORDER_READ`, `ORDER_UPDATE`, or `ORDER_DELETE`. Ownership determines the caller's relationship to a specific record.

A policy can be expressed as:

~~~text
Allow reading order if:
  user belongs to the order's tenant
  AND (
      user has permission ORDER_READ_ALL
      OR user is the owner
      OR the order is shared with the user
  )
~~~

Edit permissions can be stricter than read permissions:

~~~text
Allow updating order if:
  user belongs to the order's tenant
  AND (
      user has permission ORDER_UPDATE_ALL
      OR (user is the owner AND order.status = DRAFT)
  )
~~~

Never infer that a user with read access also has update or delete access.

### 8.1. Tenant-scoped permission tables

A model might include:

~~~sql
CREATE TABLE tenant_roles (
    tenant_id BIGINT NOT NULL,
    user_id VARCHAR(120) NOT NULL,
    role_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, user_id, role_code)
);

CREATE TABLE role_permissions (
    role_code VARCHAR(80) NOT NULL,
    permission_code VARCHAR(100) NOT NULL,
    PRIMARY KEY (role_code, permission_code)
);
~~~

Roles must be scoped to a tenant. A user can be an admin in tenant A while only a member in tenant B. Never store a single global role and apply it across all tenants when permissions are organization-scoped.

### 8.2. Reactive method security

Spring Security WebFlux supports reactive method security. Enable it with:

~~~java
@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

A method can require a coarse-grained permission:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
public Mono<OrderSummary> listOrders() {
    return orderService.listCurrentTenantOrders();
}
~~~

Method security fits coarse-grained authorization such as action-level permissions. It does not automatically ensure each row belongs to the current tenant/owner. Repository queries still need tenant predicates and record-level policies.

### 8.3. Never put all authorization solely in controllers

If checks live only in controllers, a service could be invoked from a message consumer, scheduled job, or another endpoint while bypassing checks. Enforce critical rules at the application/service boundary and reinforce them at the database.

Controllers may still enforce endpoint-level rights, yet services and repositories must never assume every caller arrived through the right controller.

## 9. Sharing Records with ACLs

Not every application has only owners and tenant admins. A document may be shared with specific users or groups.

Example ACL table:

~~~sql
CREATE TABLE document_permissions (
    tenant_id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    principal_type VARCHAR(20) NOT NULL,
    principal_id VARCHAR(120) NOT NULL,
    permission_code VARCHAR(40) NOT NULL,
    PRIMARY KEY (
        tenant_id,
        document_id,
        principal_type,
        principal_id,
        permission_code
    )
);
~~~

A document read query can use `EXISTS`:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :documentId
  AND d.tenant_id = :tenantId
  AND (
      d.owner_user_id = :userId
      OR EXISTS (
          SELECT 1
          FROM document_permissions p
          WHERE p.tenant_id = d.tenant_id
            AND p.document_id = d.id
            AND p.principal_type = 'USER'
            AND p.principal_id = :userId
            AND p.permission_code IN ('READ', 'WRITE')
      )
  );
~~~

If permissions are inherited from groups, the query must check group membership and group status within the same tenant. Create indexes on `document_id`, `principal_id`, and `permission_code` matching actual query patterns.

### 9.1. Checking permissions and writing in the same operation

A race-prone pattern:

1. `SELECT` checks that the user holds `WRITE` permission.
2. Another request revokes the permission.
3. `UPDATE` runs afterward and still modifies the document.

When strict consistency is required, fold the authorization condition into the `UPDATE` using `EXISTS`:

~~~sql
UPDATE documents d
SET title = :title,
    last_modified_at = :modifiedAt
WHERE d.id = :documentId
  AND d.tenant_id = :tenantId
  AND (
      d.owner_user_id = :userId
      OR EXISTS (
          SELECT 1
          FROM document_permissions p
          WHERE p.tenant_id = d.tenant_id
            AND p.document_id = d.id
            AND p.principal_type = 'USER'
            AND p.principal_id = :userId
            AND p.permission_code = 'WRITE'
      )
  );
~~~

This enforces the authorization check at write time. For complex policies, determine the isolation/locking required and test races between permission revocation and concurrent updates.

### 9.2. Distinguishing owner from shared collaborator

Do not overwrite `owner_user_id` when sharing a document. Ownership and ACL entries are distinct relationships. Ownership transfer is a dedicated operation requiring permission checks, audit entries, and possibly notifications to the old and new owners.

## 10. Protecting Relational Queries and JOINs

If an order belongs to tenant 10 and a customer belongs to tenant 20 due to bad data, a query joining solely on `customer_id` can accidentally combine data across tenants.

Queries should enforce matching tenants:

~~~sql
SELECT o.id, o.status, c.name
FROM orders o
JOIN customers c
  ON c.id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.id = :orderId
  AND o.tenant_id = :tenantId;
~~~

Composite foreign keys prevent cross-tenant references on insert/update. Join predicates act as defense in depth and make the query's data boundary explicit.

### 10.1. Subqueries and aggregates also need tenant scope

Not only the outer table, but child tables inside subqueries must be constrained:

~~~sql
SELECT o.id,
       (
           SELECT COUNT(*)
           FROM order_items i
           WHERE i.order_id = o.id
             AND i.tenant_id = o.tenant_id
       ) AS item_count
FROM orders o
WHERE o.tenant_id = :tenantId;
~~~

When joining an ACL or membership table, constrain tenant on both sides. Never allow a group from tenant A to grant access to a resource in tenant B just because group IDs collide.

### 10.2. Bulk updates and exports

Bulk operations are especially prone to missing authorization checks. For example:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE created_at < :cutoff;
~~~

If executed in a tenant context, add the tenant predicate. If it is a system-wide job, require a dedicated service identity/permission and process in batches per tenant with actor auditing and resource limits.

Exports/reports are also a data access path. Check tenant before reading, restrict exported fields, enforce dedicated export permissions, and never store files at shared URLs accessible across tenants.

## 11. Using Row-Level Security as a Database Defense Layer

With PostgreSQL, Row-Level Security (RLS) can restrict rows at the database even if application SQL accidentally omits a tenant predicate.

Example:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_policy
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)::BIGINT
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::BIGINT
);
~~~

`USING` restricts rows visible to reads or targeted by `UPDATE`/`DELETE`. `WITH CHECK` validates inserted rows or new states after updates.

### 11.1. Setting tenant inside the transaction

PostgreSQL supports `set_config` with `is_local = true` to scope a setting to the current transaction:

~~~sql
SELECT set_config('app.tenant_id', :tenantId, true);
~~~

All RLS-protected queries must then execute on the same transaction connection:

~~~java
public <T> Mono<T> executeForTenant(
        Long tenantId,
        Mono<T> work) {

    Mono<Void> setTenant = databaseClient
            .sql("SELECT set_config('app.tenant_id', :tenantId, true)")
            .bind("tenantId", tenantId.toString())
            .fetch()
            .rowsUpdated()
            .then();

    return transactionalOperator.transactional(
            setTenant.then(work));
}
~~~

This sketch must be adapted to your project's `DatabaseClient` API version. The mandatory requirement is that setting context and running queries share the same transaction/connection. Never run `set_config` on one connection and query on another.

### 11.2. Runtime roles must not bypass RLS

PostgreSQL table owners normally bypass RLS unless `FORCE ROW LEVEL SECURITY` is enabled. Superusers and roles with `BYPASSRLS` also bypass policies.

~~~sql
ALTER TABLE orders FORCE ROW LEVEL SECURITY;
~~~

Application runtime should use a least-privilege role, not a superuser or migration owner. Tests must connect with a role matching production; testing as table owner creates false confidence that RLS protects the data.

### 11.3. RLS does not replace membership authorization

RLS merely enforces policies against whatever tenant context has been set. If an application reads an untrusted tenant ID from a header and writes it directly into `app.tenant_id`, RLS will dutifully isolate the attacker's chosen tenant.

Authenticate the principal and verify membership first, then set tenant context inside the transaction. If record-level owner/ACL rules are required, either extend the policy or keep owner/ACL predicates in queries.

## 12. Transactions and Timing of Permission Checks

A use case may read a resource, verify permissions, update data, and write an audit entry. Operations requiring atomicity should use reactive transactions on the proper `R2dbcTransactionManager`/`ConnectionFactory`.

~~~java
@Transactional
public Mono<Document> renameDocument(
        Long documentId,
        String newTitle) {

    return TenantContext.current()
            .flatMap(context -> documentRepository
                    .findWritableDocument(
                            documentId,
                            context.tenantId(),
                            context.userId()))
            .switchIfEmpty(Mono.error(new DocumentNotFoundException()))
            .flatMap(document -> {
                document.setTitle(newTitle);
                return documentRepository.save(document);
            });
}
~~~

This example assumes `findWritableDocument` applies owner/ACL predicates in the query. If permissions can be revoked concurrently and must take effect immediately, choose an appropriate isolation level or fold the permission check into the final `UPDATE`.

### 12.1. Pre-update authorization checks can race

Checking permissions in one query and updating in another leaves a window between check and use. If policy changes in that gap, the update may act on revoked rights.

Depending on requirements, you can:

- Fold the authorization predicate into `UPDATE`/`DELETE`.
- Use transaction isolation or locking appropriate to the database.
- Verify an ACL/membership version during the write.
- Treat permissions as evaluated at transaction snapshot if those semantics are acceptable.

Do not blindly raise isolation levels. Specify revocation semantics explicitly and test concurrent behavior.

### 12.2. Never hold a transaction open while waiting on external services

Avoid opening a database transaction and then calling a slow HTTP service to verify permissions. That holds connections open too long and pressures the pool.

When authorization depends on an external service, obtain bounded-lifetime claims/tokens or policy snapshots up front, then perform short database operations with explicit predicates and transactions. If cross-system coordination is required, design a dedicated workflow.

## 13. Reactive Method Security and Repository Boundaries

Spring Security reactive method security protects methods by authority:

~~~java
@Configuration
@EnableReactiveMethodSecurity
public class SecurityConfiguration {
}
~~~

Example:

~~~java
@PreAuthorize("hasAuthority('DOCUMENT_READ')")
public Flux<DocumentSummary> listDocuments() {
    return documentService.listVisibleToCurrentUser();
}
~~~

This annotation guards functional invocation permission. `listVisibleToCurrentUser` must still query by tenant and the current user's ACL.

### 13.1. Avoid exposing repositories as public entry points to every layer

If controllers, scheduled jobs, and message consumers can directly call `ReactiveCrudRepository.findById` or `deleteById`, code paths can easily skip tenant/owner checks.

You can:

- Encapsulate repositories inside tenant-scoped adapters/services.
- Expose domain-named methods like `findVisibleToUser` instead of `findById`.
- Keep repositories package-private or avoid injecting them directly into controllers.
- Enforce code review rules for queries on tenant-scoped tables.
- Add RLS as a final defense layer.

This architectural boundary reduces accidental misuse; it does not replace testing or database policies.

### 13.2. Method security does not replace database predicates

A method annotated with `@PreAuthorize("hasAuthority('ORDER_READ')")` can still return another tenant's order if its query filters only by ID. Action permissions and per-record authorization are independent checks.

## 14. Handling 403 and 404 Without Leaking Data

HTTP statuses must follow the API contract:

- `401 Unauthorized`: unauthenticated or invalid token.
- `403 Forbidden`: authenticated, but lacking permission for the server-identified action or resource.
- `404 Not Found`: resource does not exist within the accessible scope, or the API intentionally hides the existence of out-of-scope resources.

In tenant-scoped APIs, tenant-filtered queries return empty when an ID belongs to another tenant. Returning `404` prevents attackers from probing whether IDs exist in other tenants.

If the system needs to return `403` for a user in the same tenant who is not the owner, evaluate what information may be disclosed. Never run a global query and return a message like "record exists under another user" if doing so leaks sensitive details.

## 15. Caches, Files, and Messages Must Also Respect Tenant Boundaries

Correct database queries are not enough if caches or messages omit tenant scope.

### 15.1. Cache keys

Never use cache keys containing only the resource ID if IDs can collide or access depends on tenant:

~~~text
orders:{tenantId}:{orderId}
documents:{tenantId}:{documentId}:{userId}
~~~

For ACL-protected data, tenant-only caching may still be unsafe if two users within the same tenant hold different rights. Key caches by principal/permission scope, or cache shared metadata only and apply authorization before returning data.

### 15.2. Caches must never replace authorization

A cache hit does not prove the current user has read rights. Enforce authorization before serving cached objects, or partition caches strictly by permission scope.

When memberships or ACLs are revoked, apply appropriate invalidation or TTLs so data is not served under stale permissions.

### 15.3. Messages/events

Tenant-scoped events should carry `tenantId` and `eventId`. Consumers must authenticate the producer, construct a trusted tenant context, and query within tenant scope. Never trust a tenant ID inside a message from an untrusted source.

When publishing events after transactions, use an outbox to persist the event intent alongside business data. Consumers still need authorization/service identity and idempotency/deduplication.

### 15.4. Object storage and file exports

Object keys can use a tenant prefix:

~~~text
tenant/20/documents/481/contract.pdf
~~~

A prefix only organizes storage; it is not authorization. The server must verify read rights on the document before issuing a signed URL or streaming the file. Signed URLs should have short expirations and narrow object scope.

## 16. Special Cases Requiring Dedicated Policies

### 16.1. Tenant administrators

A tenant admin can read or manage records within their tenant, yet does not automatically gain access to other tenants. Queries must still constrain `tenant_id` to the administered tenant.

### 16.2. Support operators

Support staff may need temporary access to a tenant to investigate incidents. Treat this as a privileged workflow:

- Require an explicit approval flow and expiration.
- Record reason, actor, tenant, and accessed resources.
- Restrict read/write scope to the task.
- Maintain an audit trail that regular users cannot modify.
- Revoke access once resolved.

Never use a global `SUPPORT` role to bypass all tenant predicates.

### 16.3. Ownership or tenant transfer

Transferring ownership is a privileged action. Moving a resource from tenant A to tenant B is even more complex because relationships, foreign keys, ACLs, files, caches, and events can all be tenant-bound.

Treat tenant transfers as dedicated administrative workflows that verify permissions on both source and destination, update relations inside an appropriate transaction, and audit thoroughly. Never let clients change `tenant_id` via an ordinary `PATCH`.

### 16.4. Background jobs

Background jobs have no user principal but must still stay scoped. A job processing tenant 20 must pull the tenant ID from a trusted job registry and run tenant-scoped queries. The audit actor might be `system:billing-worker` paired with a correlation ID.

System-wide jobs require a dedicated permission/service identity and should process tenant-by-tenant or in small batches rather than scanning across all tenants in an unbounded query.

## 17. Common Authorization Mistakes

| Mistake | Risk | Remedy |
| --- | --- | --- |
| Checking only that the user is logged in | IDOR/BOLA via other resources' IDs | Check tenant, owner, or ACL |
| Trusting `tenant_id` from body/header | Users pick unauthorized tenants | Resolve tenant from verified membership |
| `SELECT` checks tenant, `UPDATE` omits tenant | Cross-tenant modification | Put tenant predicate on every DML statement |
| `DELETE` uses only ID | Deletes out-of-scope resources | `DELETE` by ID + tenant + policy |
| Using UUIDs instead of authorization | Leaked IDs allow unauthorized access | Always enforce permissions on the server |
| Checking permissions after returning entity | Data may be processed/leaked prior to check | Scope the query from the start |
| Relying solely on `@PreAuthorize` | Functional permissions do not filter rows | Add predicates at repository/database |
| Unscoped roles across tenants | Admin in tenant A acts in tenant B | Bind roles/memberships per tenant |
| Separate ACL check and update | Rights may be revoked between check and write | Fold `EXISTS` into DML or transaction policy |
| Cache keys missing tenant/user | Serves another tenant's or user's cache | Key caches by tenant and permission scope |
| Consumers trusting unverified tenant IDs in messages | Consumer writes into wrong tenant | Authenticate producer and build trusted context |
| Running RLS as table owner | Policies can be bypassed | Least-privilege runtime role and `FORCE RLS` |
| Connection retaining old tenant settings | Context leaks across connection pool | Transaction-local settings and pool reuse tests |
| Support role bypassing all filters | Excessive cross-tenant access | Just-in-time access, scoping, and auditing |
| Background jobs querying without tenant | Full-system scans or edits | Service identity and per-tenant batch scope |

## 18. Testing Tenant Boundaries and Record-Level Authorization

Tests should prove callers cannot read, create, update, delete, or share out-of-scope resources, even when substituting IDs in requests.

### 18.1. Two-tenant, multi-user fixture

Setup:

| Identity | Tenant | Resource |
| --- | --- | --- |
| user-A | tenant-10 | order-101, owner user-A |
| user-B | tenant-10 | order-102, owner user-B |
| user-C | tenant-20 | order-201, owner user-C |

Expectations:

- `user-A` can read `order-101`.
- `user-A` cannot read `order-201`.
- `user-A` cannot modify or delete `order-102` without management permission.
- `user-C` cannot read `order-101` even with a valid ID.
- A tenant admin of `tenant-10` can manage only `tenant-10` data.

### 18.2. Testing IDOR on GET

With `WebTestClient`:

~~~java
webTestClient.get()
        .uri("/api/orders/201")
        .headers(headers -> headers.setBearerAuth(tokenForUserA))
        .exchange()
        .expectStatus().isNotFound();
~~~

Tests should confirm the response contains no fields from `tenant-20`'s order. If the API uses `403` per policy, verify both status and body reveal no out-of-scope data.

### 18.3. Testing INSERT ignores client-supplied tenant

Send a body with `tenantId = 20` while the caller's token/context belongs to tenant 10. Verify the server rejects or ignores the disallowed field and any persisted row has `tenant_id = 10`.

### 18.4. Testing UPDATE/DELETE

In `user-A`'s context, send `PATCH`/`DELETE` with the ID of `order-102` or `order-201`. Confirm no rows were changed/deleted and audit records do not log a false success.

Inspect the database directly after the request rather than checking only the HTTP response.

### 18.5. Testing cross-tenant relationships

Attempt to create an order in `tenant-10` referencing a customer ID from `tenant-20`. The composite foreign key must reject the operation. This test proves database constraints protect integrity even if a service has a bug.

### 18.6. Testing ACLs

Create a document owned by `user-A` with `READ` ACL for `user-B`:

- `user-B` can read but cannot edit.
- `user-C` cannot read.
- After revoking the ACL, `user-B` can no longer read under the defined effective semantics.
- An update running concurrently with permission revocation produces the outcome defined by the isolation/policy rules.

### 18.7. Testing reactive context isolation

Run two concurrent requests:

- Request A with tenant 10/`user-A`.
- Request B with tenant 20/`user-C`.

Execute queries across scheduler boundaries or asynchronous steps to verify contexts never bleed across subscriptions. Do not test only sequentially on one thread.

### 18.8. Testing RLS with the runtime role

When using PostgreSQL RLS:

- Connect as the application role, not a superuser.
- Without a tenant context, zero rows are readable.
- Tenant 10 cannot read or write tenant 20.
- `INSERT` with a mismatched `tenant_id` is rejected.
- Reused pooled connections do not retain stale tenant settings.
- Confirm the runtime role lacks `BYPASSRLS`.

## 19. Workflow for Designing Access Control on an Endpoint

For every endpoint that reads or writes resources, verify in order:

1. Who is the authenticated principal?
2. Which tenant is selected, and is membership still active?
3. What functional permission does this action require?
4. Which tenant owns the target resource?
5. Is the caller the owner or covered by an appropriate ACL?
6. Does the resource's state permit this action?
7. Does the final query include tenant/owner/ACL predicates?
8. Can database constraints/RLS block invalid access?
9. Do `401`/`403`/`404`/`409` responses avoid leaking out-of-scope information?
10. Do caches, events, exports, and audits maintain the same boundary?

Express policies explicitly in code or queries. Avoid scattering ad-hoc authorization checks across controllers where they cannot be tested independently.

## 20. Example Tenant-Aware Service with Ownership Checks

Entity:

~~~java
@Table("documents")
public class Document {

    @Id
    private Long id;

    @Column("tenant_id")
    private Long tenantId;

    @Column("owner_user_id")
    private String ownerUserId;

    private String title;

    @Column("last_modified_by")
    private String lastModifiedBy;

    @Column("last_modified_at")
    private Instant lastModifiedAt;

    public static Document create(
            Long tenantId,
            String ownerUserId,
            String title) {
        Document document = new Document();
        document.tenantId = tenantId;
        document.ownerUserId = ownerUserId;
        document.title = title;
        return document;
    }
}
~~~

Repository:

~~~java
public interface DocumentRepository
        extends ReactiveCrudRepository<Document, Long> {

    Mono<Document> findByIdAndTenantIdAndOwnerUserId(
            Long id,
            Long tenantId,
            String ownerUserId);
}
~~~

Service:

~~~java
@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<Document> findMine(Long documentId) {
        return TenantContext.current()
                .flatMap(context -> repository
                        .findByIdAndTenantIdAndOwnerUserId(
                                documentId,
                                context.tenantId(),
                                context.userId()));
    }
}
~~~

This example allows only the owner to read. If the application includes tenant admins or ACL sharing, place those policy branches in a clearly named query such as `findVisibleToPrincipal` and test each branch. Never add a broad `OR` condition without tests proving its bounds.

## 21. Record and Tenant Protection Checklist

- [ ] Principals are authenticated by a trusted server mechanism.
- [ ] Tenants are resolved and memberships verified before accessing data.
- [ ] Client-sent `tenant_id`/`owner_id`/`role` values are never trusted.
- [ ] Tenant context is propagated via Reactor `Context` or a compatible reactive mechanism.
- [ ] Every `SELECT` on tenant-scoped tables has a tenant predicate or RLS protection.
- [ ] Every `INSERT` sets tenant and owner from trusted context.
- [ ] Every `UPDATE`/`DELETE` includes tenant and record-level policy in its predicate.
- [ ] `JOIN`s, subqueries, aggregates, and bulk operations preserve tenant scope.
- [ ] Composite foreign keys prevent cross-tenant relationships where applicable.
- [ ] Unique constraints reflect the business scope of uniqueness.
- [ ] Roles/permissions are scoped by tenant.
- [ ] Ownership and ACL sharing are cleanly separated.
- [ ] Revocation and races between authorization checks and updates have clear semantics.
- [ ] Cache keys and invalidation preserve tenant/user permission scope.
- [ ] Messages, object storage, exports, and background jobs enforce tenant boundaries.
- [ ] RLS runs with a runtime role that cannot bypass policies.
- [ ] Integration tests include at least two tenants and multiple users with differing rights.
- [ ] Tests cover `GET`, `INSERT`, `UPDATE`, `DELETE`, and cross-tenant relationships.
- [ ] Tests cover concurrent requests and reactive context isolation.

## 22. Record Access Control Decision Diagram

~~~mermaid
flowchart TD
    A[Receive request] --> B[Authenticate principal]
    B --> C{Principal valid?}
    C -->|No| D[401 Unauthorized]
    C -->|Yes| E[Resolve tenant and check membership]
    E --> F{Allowed in tenant?}
    F -->|No| G[403 or 404 per policy]
    F -->|Yes| H[Check functional permission]
    H --> I{Has permission?}
    I -->|No| J[403 Forbidden]
    I -->|Yes| K[Query by tenant and record policy]
    K --> L{Accessible row found?}
    L -->|No| M[404 Not Found]
    L -->|Yes| N{Action valid for state?}
    N -->|No| O[409 Conflict]
    N -->|Yes| P[Execute DML with protective predicate]
    P --> Q[Commit and write audit]
    Q --> R[Return response]
~~~

## 23. Conclusion

Authentication identifies the caller, but does not prove the caller has rights on every record. In Spring Data R2DBC, record-level authorization must be enforced on every read and write using appropriate tenant, owner, permission, or ACL checks. Tenant context must be constructed from the authenticated principal and verified membership, then propagated through reactive context. Never trust tenant IDs or owner IDs submitted by clients.

Include tenant and access rights in the predicates of `SELECT`, `UPDATE`, and `DELETE`; populate tenant/owner from context on `INSERT`; and protect `JOIN`s, subqueries, bulk operations, caches, events, and file exports. Composite foreign keys and Row-Level Security add strong database-side safeguards, though they do not replace application authorization. Reactive method security guards functional entry points while queries must still constrain individual records.

Test across multiple tenants and multiple users with differing permissions. Test substituting IDs, altering tenant fields in request bodies, editing/deleting others' records, forming cross-tenant links, and running concurrent requests. A secure boundary must hold even when a client sends valid IDs that belong outside their scope.
