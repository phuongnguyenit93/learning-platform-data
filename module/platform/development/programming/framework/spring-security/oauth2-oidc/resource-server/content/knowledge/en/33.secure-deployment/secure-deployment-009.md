# Tenant Isolation and Business Data Authorization Checks

## 1. Why Token Authentication Alone Is Not Enough to Protect Multi-Tenant Data

An OAuth 2.0 Resource Server can verify an access token completely accurately and still leak data if the business layer does not restrict queries by tenant.

Suppose a SaaS system manages orders for multiple businesses:

- Tenant **blue** owns order 1001.
- Tenant **red** owns order 2001.
- User Alice belongs to tenant blue.
- User Bob belongs to tenant red.

Alice sends:

~~~http
GET /api/orders/2001 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <valid-access-token-for-alice>
~~~

The token has a valid signature, right issuer, `orders-api` audience, and `orders.read` scope. Authentication succeeds. Yet if the code simply queries:

~~~sql
SELECT * FROM orders WHERE id = :orderId
~~~

then Alice can read tenant red's order if she knows or guesses ID 2001.

This is **Broken Object Level Authorization (BOLA)**, often called IDOR in ID-based object access scenarios. A valid token does not by itself prove the caller has permission for every object in the API.

A decision to grant access to tenant data requires at least:

~~~text
Valid access token
  AND required API scope
  AND authenticated actor belongs to requested tenant
  AND resource belongs to that tenant
  AND actor has permission for this operation
  AND business state permits the operation
~~~

**Tenant isolation is a security boundary at every data-access layer.** It must be enforced in routing/context, services, repositories/queries, caches, background jobs, event consumers, and export/search flows.

## 2. Distinguishing Authentication, Tenant Resolution, and Authorization

Three concepts are frequently conflated:

| Concept | Question | Example |
|---|---|---|
| **Authentication** | Who is calling the API? | Issuer + subject or client identity |
| **Tenant resolution** | Which tenant is this request operating in? | Tenant from verified path or host |
| **Authorization** | What may this actor do on that resource? | Read tenant's order, edit open order |

An access token can prove the actor was authenticated by the issuer. It may carry a tenant claim, yet that claim must still be interpreted according to the issuer and domain contract.

A tenant ID in a URL:

~~~text
/api/tenants/blue/orders/1001
~~~

only expresses the **requested tenant context**. It does not prove the caller is a member of tenant blue.

Similarly, a header:

~~~http
X-Tenant-Id: blue
~~~

is request-supplied data. Without verifying membership, this header can become a way for callers to select someone else's tenant.

### Three Decisions Must Be Made Separately

1. Spring Security verifies the access token.
2. The application resolves the tenant context and verifies the actor is permitted to use that tenant.
3. Domain services/repositories operate only on resources belonging to the verified tenant, then check specific business permissions.

Never treat success in step 1 as an automatic conclusion for steps 2 and 3.

## 3. Stable Identity: Issuer, Subject, and Actor Kind

In OAuth/OIDC, the `sub` claim typically identifies a subject scoped to the issuer. Two issuers might both emit `sub=user-42`, yet those may be two separate people or accounts.

When mapping an external identity to a local identity, use:

~~~text
ExternalIdentity = (issuer, subject)
~~~

For example:

~~~text
(https://auth-a.example.com/, user-42)
(https://auth-b.example.com/, user-42)
~~~

are two distinct identity keys.

With client credentials, the token may represent a machine client rather than a human user. In that case, the actor key may be based on issuer + `client_id` per contract:

~~~text
USER actor:
  issuer + sub

CLIENT actor:
  issuer + client_id
~~~

Do not use email or username as the sole identity key unless the issuer guarantees uniqueness, stability, and account-linking semantics.

### Tenant Membership Is Not the Same as the Subject Claim

A JWT may contain:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["orders-api"],
  "tenant_id": "blue",
  "scope": "orders.read orders.write"
}
~~~

If the issuer emits `tenant_id` after verifying membership and the Resource Server trusts that specific issuer/profile, the claim can be an authorization input. Yet you must know:
- Does the tenant claim represent a default tenant, an actively selected tenant, or all memberships?
- Is the claim updated when membership is revoked?
- How long is the token lifetime?
- Does the API require up-to-date membership freshness at request time?
- Can one user belong to multiple tenants?
- Can tokens be issued to both users and machine clients with different semantics?

If membership changes rapidly, relying solely on a claim snapshot inside a JWT may not satisfy revocation SLAs. Querying current membership or enforcing a version/cache invalidation policy may be needed.

## 4. Sources of Tenant Context and Trust Levels

Tenant context is typically derived from one of these sources:

| Source | What Can It Be Used For? | Condition |
|---|---|---|
| Path parameter | Requested tenant for the resource | Check actor membership |
| Subdomain/host | Selecting tenant workspace | Host mapping must be configured and verified |
| JWT claim | Issuer-issued tenant context | Verified token, clear claim semantics |
| Opaque introspection attribute | Tenant metadata from the AS | Active introspection and trusted issuer contract |
| Gateway-added header | Gateway-verified context | Strip caller-sent header, trust gateway-to-service |
| Request body | Target tenant for create/move actions | Only after explicit authorization |
| Query parameter | Requested tenant filter | Never treat as proof of membership |

### Requested Tenant Differs from Authenticated Tenant

An API may accept the tenant in the path:

~~~http
GET /api/tenants/blue/orders/1001
Authorization: Bearer <token>
~~~

The service must verify the actor belongs to tenant blue or holds an explicitly granted cross-tenant permission.

Do not:
- Take the tenant from the path and trust it immediately.
- Trust `X-Tenant-Id` without verifying the source.
- Allow a body `tenantId` to override the authenticated tenant context.
- Reuse a tenant from a previous request in a `ThreadLocal` or mutable singleton.
- Pick a tenant by decoding an unverified JWT payload.

### Gateway Headers

If a trusted gateway adds `X-Verified-Tenant`:
1. The backend accepts traffic only through the protected gateway.
2. The gateway strips any same-named header sent by the client.
3. The gateway builds the header from verified identity/context.
4. The gateway-to-backend connection is protected by mTLS or an appropriate network boundary.
5. The backend accepts this header only on routes with a matching contract.

An internal header is not automatically trustworthy merely because its name contains the word `Verified`.

## 5. Tenant Context Must Be Built from the Verified Principal

In WebFlux, a controller can receive `OAuth2AuthenticatedPrincipal`:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class TenantOrdersController {

    private final TenantAccessService tenantAccessService;
    private final OrdersService ordersService;

    public TenantOrdersController(
            TenantAccessService tenantAccessService,
            OrdersService ordersService) {
        this.tenantAccessService = tenantAccessService;
        this.ordersService = ordersService;
    }

    @GetMapping("/api/tenants/{tenantId}/orders/{orderId}")
    public Mono<OrderView> getOrder(
            @PathVariable String tenantId,
            @PathVariable String orderId,
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {

        return tenantAccessService.resolve(principal, tenantId)
                .flatMap(context ->
                        ordersService.findOrder(context, orderId));
    }
}
~~~

`OAuth2AuthenticatedPrincipal` is a fitting abstraction when an application supports both JWT principals and opaque-token principals. For a JWT-only API, controllers can also accept `Jwt`/`JwtAuthenticationToken`. Use the exact principal type matching your configured security strategy.

**Do not pass raw Bearer tokens down to domain services** when the service only needs actor identity and tenant context. Reducing credential scope prevents accidental logging or storage of tokens.

### The Principal May Lack `tenant_id`

If the API uses the tenant in the path plus a membership store, the principal does not need to carry a default tenant. What matters is that issuer + subject or client identity is authenticated and membership is checked against the requested tenant.

## 6. Resolving Tenants via a Membership Service

A service can construct `TenantContext` after verifying membership:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class TenantAccessService {

    private final TenantMembershipRepository memberships;

    public TenantAccessService(TenantMembershipRepository memberships) {
        this.memberships = memberships;
    }

    public Mono<TenantContext> resolve(
            OAuth2AuthenticatedPrincipal principal,
            String requestedTenantId) {

        String issuer = principal.getAttribute("iss");
        String subject = principal.getAttribute("sub");

        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            return Mono.error(new AccessDeniedException(
                    "A user identity is required"));
        }

        return memberships.existsActiveMembership(
                        issuer, subject, requestedTenantId)
                .filter(Boolean::booleanValue)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Tenant access is not permitted")))
                .thenReturn(new TenantContext(
                        issuer, subject, requestedTenantId));
    }
}
~~~

Illustrative types:

~~~java
public record TenantContext(
        String issuer,
        String subject,
        String tenantId) {
}
~~~

Repository contract:

~~~java
public interface TenantMembershipRepository {
    Mono<Boolean> existsActiveMembership(
            String issuer,
            String subject,
            String tenantId);
}
~~~

Points to note:
- Validate identity fields before using them.
- Membership keys use issuer + subject + tenant.
- Only an active membership may create a `TenantContext`.
- Never construct a default tenant context when the principal lacks data.
- The repository must query memberships within the right identity namespace.
- If the actor is a machine client, provide a dedicated resolver/contract based on client identity rather than assuming `sub` is always present.

This is a reactive example. The repository implementation must return `Mono<Boolean>` and never invoke a blocking database driver on the event loop.

### Do Not Let Controllers Decide Membership Independently

If each controller writes different tenant conditions, a new endpoint can easily miss a check. Centralizing resolution in a shared service, policy component, or appropriate method-security layer keeps semantics consistent across routes.

## 7. `TenantContext` Is Verified Data, Not a Raw Header

A `TenantContext` in the domain may contain:

~~~java
public record TenantContext(
        String issuer,
        String subject,
        String tenantId) {
}
~~~

In complex applications, it can also include:
- `actorKind` (`USER` or `CLIENT`).
- `localActorId`.
- `membershipId`.
- `membershipVersion`.
- Permitted roles/permissions.
- Request correlation ID.
- Authentication method/context if required by business policy.

Do not store raw access tokens inside `TenantContext`.

Create `TenantContext` only after:
1. Authentication succeeds.
2. Identity is normalized by issuer/subject or client identity.
3. The requested tenant is validated.
4. Current membership/tenant permissions are checked.
5. The context is bound to the current request/reactive chain.

`TenantContext` is the outcome of an authorization step. It must never be a mutable singleton shared across requests.

## 8. Configuring WebFlux Resource Server and Coarse-Grained Scopes

Spring Security can protect routes by scope:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ResourceServerSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/tenants/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/tenants/**")
                            .hasAuthority("SCOPE_orders.write")
                        .pathMatchers(HttpMethod.PUT, "/api/tenants/**")
                            .hasAuthority("SCOPE_orders.write")
                        .pathMatchers(HttpMethod.DELETE, "/api/tenants/**")
                            .hasAuthority("SCOPE_orders.delete")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

This is coarse-grained authorization: the route requires the corresponding scope. It does not yet know which tenant a specific order belongs to, which memberships the user holds, or what state the order is in.

Therefore, scope checks must be combined with tenant/object/business checks in services or method authorization.

### Scope Does Not Replace Ownership

A token with `SCOPE_orders.read` does not mean the actor can read every order across every tenant.

~~~text
SCOPE_orders.read
  -> Allowed to call the order-reading API type

Tenant membership
  -> Allowed to work within tenant blue

Order tenant filter
  -> Order 1001 actually belongs to tenant blue

Domain policy
  -> Actor is allowed to view order 1001 per ownership/state
~~~

Each condition answers a different question.
## 9. Reactive Method Security and Tenant-Aware Services

Reactive method security can be enabled:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Use `@PreAuthorize` for scopes/coarse permissions:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrdersService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderView> findOrder(
            TenantContext tenant,
            String orderId) {
        return repository.findByIdAndTenantId(
                orderId, tenant.tenantId());
    }
}
~~~

This is an illustrative example. The repository method must actually filter by tenant in the database query, rather than loading the object by ID first and merely trusting a tenant parameter in the controller.

**`@PreAuthorize` scope checks do not replace object-level authorization.** If a method is invoked from an internal path or another service bypassing the same security proxy, tenant isolation must still hold in the service/repository contract.

### Do Not Rely Solely on Method Security

Business methods can be called from:
- HTTP controllers.
- Scheduled tasks.
- Message consumers.
- Internal services.
- Admin workflows.
- Batch imports/exports.

If checks exist only in a filter chain or controller annotation, other call paths can bypass them. Enforce tenant predicates and domain checks in shared data/service layers.

## 10. Always Include `tenantId` in Data Queries

Wrong:

~~~java
Mono<Order> findOrder(String orderId) {
    return databaseClient.sql(
            "SELECT id, tenant_id, status FROM orders WHERE id = :id")
            .bind("id", orderId)
            .map(this::mapOrder)
            .one();
}
~~~

The snippet above looks up by ID alone. If `orderId` can be guessed or obtained from logs, a caller can access another tenant's object.

Better:

~~~java
Mono<Order> findOrder(TenantContext tenant, String orderId) {
    return databaseClient.sql(
            "SELECT id, tenant_id, status FROM orders " +
            "WHERE id = :id AND tenant_id = :tenantId")
            .bind("id", orderId)
            .bind("tenantId", tenant.tenantId())
            .map(this::mapOrder)
            .one();
}
~~~

Outcome:
- Order belongs to the current tenant: returned.
- Order belongs to another tenant: not found within tenant scope.
- Non-existent ID: also not found.

Depending on the API's disclosure policy, the last two cases can both return 404 to avoid disclosing the existence of objects belonging to other tenants.

### Tenant Predicates Must Apply to Every Query Path

Not just `SELECT`:
- `UPDATE`.
- `DELETE`.
- `INSERT`.
- `COUNT`/aggregates.
- Search.
- Export.
- Joins.
- Batch operations.
- Subqueries.
- Reporting views.

A safe list query:

~~~sql
SELECT id, status, total
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC
LIMIT :limit
~~~

A safe update query:

~~~sql
UPDATE orders
SET status = :newStatus
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND status = 'DRAFT'
~~~

A safe delete query:

~~~sql
DELETE FROM orders
WHERE id = :orderId
  AND tenant_id = :tenantId
~~~

Never query by ID first and then forget the tenant check in an error branch or secondary mapper.

## 11. Inserts: Tenant Comes from Trusted Context

A common bug is letting the client choose the tenant when creating data:

~~~json
{
  "tenantId": "blue",
  "productId": "p-100",
  "quantity": 2
}
~~~

If the service copies `tenantId` from the body into the `INSERT`, callers can create records for other tenants.

Better:
- Derive the tenant from the verified `TenantContext`.
- Omit `tenantId` from the body, or if present, compare it against context and reject mismatches.
- `INSERT` sets `tenantId` from server-side context.
- Foreign keys enforce valid relationships between records and tenants.

Example:

~~~java
Mono<Order> createOrder(
        TenantContext tenant,
        CreateOrderRequest request) {

    return databaseClient.sql(
            "INSERT INTO orders (id, tenant_id, product_id, quantity) " +
            "VALUES (:id, :tenantId, :productId, :quantity) " +
            "RETURNING id, tenant_id, product_id, quantity")
            .bind("id", UUID.randomUUID().toString())
            .bind("tenantId", tenant.tenantId())
            .bind("productId", request.productId())
            .bind("quantity", request.quantity())
            .map(this::mapOrder)
            .one();
}
~~~

This snippet assumes `DatabaseClient`/R2DBC and a database supporting `RETURNING`. Adjust syntax for your actual database driver.

## 12. Updates Must Check Tenant and Business State in the Same Statement

If code does:
1. `SELECT` order by ID.
2. Check tenant in Java.
3. `UPDATE` order by ID.

a race condition can occur if tenant/ownership/state changes between steps or if another code path skips the check.

For simple conditions, put tenant and state in the same `UPDATE`:

~~~sql
UPDATE orders
SET status = :newStatus,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND status = 'DRAFT'
~~~

If the updated row count is 1, the operation succeeded. If 0, the resource does not exist in the tenant or is no longer in an allowed state. The API may need a step to distinguish 404/409 per disclosure/business policy, while preserving tenant isolation.

For complex state transitions, use transactions and optimistic locking:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = version + 1
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND version = :expectedVersion
  AND status = 'DRAFT'
~~~

The tenant predicate must appear in the final update itself, not only in the initial `SELECT`.

## 13. Database Schema: Tenant-Aware Keys and Foreign Keys

A simple schema:

~~~sql
CREATE TABLE tenants (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, id),
    CONSTRAINT fk_orders_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
~~~

Using a composite key `(tenant_id, id)` helps express object identity within the tenant namespace.

If another table references orders:

~~~sql
CREATE TABLE order_items (
    tenant_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    item_id VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, item_id),
    CONSTRAINT fk_item_order
        FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, id)
);
~~~

The composite foreign key prevents an `order_item` of tenant blue from referencing an order of tenant red by order ID alone.

### Indexes Should Support Tenant Predicates

If queries frequently run:

~~~sql
WHERE tenant_id = :tenantId AND status = :status
ORDER BY created_at DESC
~~~

consider an index:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Indexes do not replace security checks, yet they help tenant-scoped queries run efficiently. Inspect execution plans and actual workloads before adding indexes.

### Random IDs Are Not Authorization

UUIDs/ULIDs are harder to guess than sequential integers, yet they do not solve BOLA. An ID leaked via URLs, logs, emails, or analytics can still be replayed. Always filter by tenant and check permissions.

## 14. Row-Level Security as Defense in Depth

Some databases support Row-Level Security (RLS), such as PostgreSQL. RLS can force the database to return only rows belonging to the current tenant context.

Example PostgreSQL policy:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

The application must set the tenant context on the transaction/connection before querying:

~~~sql
SELECT set_config('app.tenant_id', :tenantId, true);
~~~

The `true` parameter scopes the setting to the transaction in PostgreSQL. This is critical with connection pools so that a prior request's tenant context never leaks into the next request.

### RLS Caveats to Watch

- The application's database role must not be a superuser or have `BYPASSRLS`.
- Table owners can bypass RLS in some cases; `FORCE ROW LEVEL SECURITY` enforces policies on the owner too.
- Transactions must set the tenant context properly before every query.
- Never let callers set an arbitrary tenant ID without going through application membership checks.
- Every connection-pool path must ensure transaction scoping.
- Migrations/admin jobs need separate roles/policies and auditing.
- Tests must run with the actual application role, not only the database owner.

RLS is defense in depth. Still include explicit tenant predicates in repositories so query semantics remain clear and easy to review.

### Reactive Transactions and Connection Pooling

In WebFlux/R2DBC, transactions and connections have reactive lifecycles. Never execute a session-wide SQL `SET` and return the connection to the pool without resetting it. Use transaction-scoped settings and Spring's reactive transaction manager appropriately; verify all queries in a transaction actually share the same connection.

Never use `ThreadLocal` to pass tenant IDs to R2DBC connections. Reactive execution can switch threads; use transaction/context-aware mechanisms.

## 15. Joins and Subqueries Must Also Be Tenant-Scoped

A query with a tenant filter on `orders` that joins `customers` without a tenant predicate can still leak data if customer IDs are not globally unique or relations are malformed.

~~~sql
SELECT o.id, c.name
FROM orders o
JOIN customers c
  ON c.id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.tenant_id = :tenantId
  AND o.id = :orderId
~~~

Subqueries must preserve tenant scope too:

~~~sql
SELECT o.id
FROM orders o
WHERE o.tenant_id = :tenantId
  AND EXISTS (
      SELECT 1
      FROM order_permissions p
      WHERE p.tenant_id = o.tenant_id
        AND p.order_id = o.id
        AND p.subject_id = :subjectId
  )
~~~

If shared/global reference data exists, clearly define which tables are global and which are tenant-owned. Not every table must have `tenant_id`, yet every join must preserve ownership boundaries.

## 16. Object-Level Authorization: Checking Each Resource

Scopes are usually coarse-grained permissions. Object-level policies must check:
- Which tenant does the resource belong to?
- Does the actor have ownership or assignment?
- Does the actor hold a role on the resource?
- What state is the resource in?
- Are there separation-of-duties or approval rules?

An order may have a policy:

~~~text
Read order:
  hasAuthority(SCOPE_orders.read)
  AND tenant membership active
  AND order.tenantId == tenantContext.tenantId
  AND actor can view order

Update order:
  hasAuthority(SCOPE_orders.write)
  AND tenant membership active
  AND order.tenantId == tenantContext.tenantId
  AND actor is owner or assigned operator
  AND order.status == DRAFT
~~~

A user permitted to read every order in a tenant is not necessarily permitted to edit every order. There may be `ORDER_VIEWER`, `ORDER_EDITOR`, `ORDER_APPROVER` roles, or ownership-based policies.

### Check Permissions Server-Side

Never rely on:
- Hidden buttons on the frontend.
- Hard-to-guess order IDs.
- Browser-sent tenant IDs.
- Role names in request bodies.
- User-chosen URL paths.
- A single check in one controller that another repository bypasses.

Every resource request must be authorized server-side.

## 17. BOLA/IDOR and How to Prevent It

A vulnerable API:

~~~http
GET /api/orders/1001
~~~

If order IDs are a global sequence, an attacker can probe 1002, 1003. Even with random UUIDs, an attacker can obtain IDs from emails, logs, shared links, or client-side state.

Wrong:

~~~java
return repository.findById(orderId)
        .map(orderMapper::toView);
~~~

Right:

~~~java
return repository.findByIdAndTenantId(
                orderId, tenantContext.tenantId())
        .switchIfEmpty(Mono.error(
                new OrderNotFoundException()))
        .flatMap(order ->
                authorizationService.canRead(
                        tenantContext, order)
                        .filter(Boolean::booleanValue)
                        .switchIfEmpty(Mono.error(
                                new AccessDeniedException(
                                        "Order access denied")))
                        .thenReturn(orderMapper.toView(order)));
~~~

If hiding object existence is desired, return the same 404 for non-existent objects and objects belonging to other tenants. If policy requires 403 to indicate existence without permission, ensure no unintended metadata is disclosed.

## 18. Reactive Authorization Service

A policy service can verify membership, ownership, and business roles:

~~~java
public interface OrderAuthorizationService {

    Mono<Boolean> canRead(
            TenantContext tenant,
            Order order);

    Mono<Boolean> canUpdate(
            TenantContext tenant,
            Order order);
}
~~~

Example implementation:

~~~java
@Service
public class DefaultOrderAuthorizationService
        implements OrderAuthorizationService {

    private final OrderAssignmentRepository assignments;

    public DefaultOrderAuthorizationService(
            OrderAssignmentRepository assignments) {
        this.assignments = assignments;
    }

    @Override
    public Mono<Boolean> canRead(
            TenantContext tenant,
            Order order) {

        if (!tenant.tenantId().equals(order.tenantId())) {
            return Mono.just(false);
        }

        return assignments.existsActiveAssignment(
                tenant.issuer(),
                tenant.subject(),
                tenant.tenantId(),
                order.id());
    }

    @Override
    public Mono<Boolean> canUpdate(
            TenantContext tenant,
            Order order) {

        if (!tenant.tenantId().equals(order.tenantId())
                || !"DRAFT".equals(order.status())) {
            return Mono.just(false);
        }

        return assignments.existsEditAssignment(
                tenant.issuer(),
                tenant.subject(),
                tenant.tenantId(),
                order.id());
    }
}
~~~

This example assumes the actor is a user and the assignment store has current data. With client credentials, a dedicated machine-actor policy may be needed.

### Avoid Nested Subscriptions

Do not do:

~~~java
authorizationService.canUpdate(tenant, order)
        .subscribe(allowed -> {
            if (allowed) {
                repository.save(order).subscribe();
            }
        });
~~~

These are fire-and-forget nested subscriptions, breaking composition, error propagation, and transaction contexts. Use `flatMap`/`filter`/`switchIfEmpty`:

~~~java
authorizationService.canUpdate(tenant, order)
        .filter(Boolean::booleanValue)
        .switchIfEmpty(Mono.error(
                new AccessDeniedException("Update denied")))
        .flatMap(allowed -> repository.save(order));
~~~

In production code, if the repository query already filters tenant and state, combine authorization carefully to reduce race conditions.
## 19. Reactive `SecurityContext` and Tenant Context Propagation

In WebFlux, `SecurityContext` is stored in the Reactor Context. Use `ReactiveSecurityContextHolder` when retrieving `Authentication` inside a reactive chain:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication());
}
~~~

Do not rely on imperative `ThreadLocal`/`SecurityContextHolder` as the sole guarantee in reactive pipelines.

### Passing Tenant Context via Method Parameters

An explicit approach is usually easier to review:

~~~java
return tenantAccessService.resolve(principal, tenantId)
        .flatMap(tenant ->
                ordersService.findOrder(tenant, orderId));
~~~

Advantages:
- Method signatures make the tenant boundary visible.
- Unit tests can construct explicit contexts cleanly.
- Repositories are forced to accept the tenant.
- Zero reliance on thread-local state.
- Background tasks can receive explicit context.

If using Reactor Context to propagate the tenant, you must:
- Set it only after verification.
- Scope it to the request chain.
- Never use static mutable state.
- Ensure context propagation across operators/libraries.
- Never trust context set by the caller.
- Never reuse context across subscriptions.

## 20. Tenant Context in Scheduled Jobs and Message Consumers

Not all data access flows through the HTTP filter chain. Examples:
- Scheduled billing tasks.
- Kafka/Rabbit message consumers.
- Webhook processors.
- Batch exports.
- Async order fulfillment.
- Retry workers.

These flows must have their own actor/tenant context.

An event may carry a tenant identifier from a trusted producer source:

~~~json
{
  "eventId": "evt-100",
  "eventType": "OrderPaid",
  "tenantId": "blue",
  "orderId": "1001",
  "actor": {
    "issuer": "https://auth.example.com/",
    "subject": "user-42"
  }
}
~~~

Consumers must:
- Verify the message came from a trusted producer/broker.
- Check `tenantId` and the order's tenant in the database.
- Never trust event tenants if the producer is untrusted.
- Never use expired raw access tokens embedded in events.
- Use service identities for background execution where appropriate.
- Audit actor/tenant/source event.
- Keep tenant predicates on every query and side effect.

### Revalidate Permissions at Processing Time

An event might be emitted while the user held membership, yet processed after membership was revoked. Decide the policy:
- Is the event a command already authorized at emission time?
- Or must the consumer check current membership at execution time?
- Should the actor be recorded as the requester while executing under a service identity?
- How should pending events be handled if a tenant is suspended?

This is a business/security contract, not something inferred automatically from the initial JWT.

## 21. Caches, Search Indexes, and Exports Must Also Be Tenant-Scoped

### Application Caches

Wrong:

~~~text
cache key = order:1001
~~~

If caches are not namespaced by tenant, tenant red could receive an object cached for tenant blue on ID collision or wrong mapping.

Better:

~~~text
cache key = tenant:blue:order:1001
~~~

Cache keys should include the tenant and every dimension affecting authorization:
- Tenant.
- Resource ID.
- Actor/permission context if caching user-filtered responses.
- Locale/representation if needed.
- Policy/version if caching authorization results.

Never cache a response authorized for Alice and serve it to Bob simply because the URL/resource key matches.

### Search Indexes

Elasticsearch/OpenSearch or search systems must filter by tenant in every query. Never filter only in the UI or post-filter a limited result set; aggregations/facets/counts can also leak other tenants' data.

### Exports/Reports

An export can contain thousands of rows. You must:
- Use tenant-scoped queries from the outset.
- Authorize the export action.
- Limit exported fields and PII.
- Use tenant-aware storage paths/bucket prefixes.
- Issue time-limited download URLs with proper permissions.
- Check tenant when users download files.
- Never share object storage keys accessible across tenants.

## 22. Multi-Tenant Transactions and Consistency

A business action may consist of:
1. Resolving tenant membership.
2. Loading the order.
3. Checking ownership/state.
4. Updating the order.
5. Inserting an audit record.
6. Publishing an event.

If these steps are uncoordinated, race conditions or side effects in the wrong tenant can occur.

You should:
- Use the reactive transaction manager in R2DBC when multiple DB operations require atomicity.
- Place tenant predicates in the final write query.
- Use optimistic locking/versioning when state can change concurrently.
- Write audit records in the same transaction when using the same database and atomicity is required.
- Use the outbox pattern for event publication.
- Include `tenantId` in outbox records and event keys.
- Have consumers still verify tenant/object ownership.

A check at the start of a request does not guarantee state stays unchanged at `UPDATE` time. For sensitive actions, check state and tenant inside the write statement or in a transaction with appropriate isolation.

## 23. Database Constraints and Defense in Depth

A multi-layered design:

~~~text
HTTP / Security:
  Verify issuer, audience, signature, expiry
  Require coarse scope

Tenant resolver:
  Map issuer + subject/client
  Check active tenant membership

Domain service:
  Check object ownership, role, business state

Repository:
  Every query includes tenant predicate

Database:
  Composite keys / foreign keys / optional RLS

Cache/search/export:
  Tenant namespace and filters

Operations:
  Audit, metrics, negative tests
~~~

Never rely on a single layer. If a controller forgets to call the membership service, repository tenant predicates still reduce data leak risk. If one query misses a predicate, database RLS can provide defense in depth when properly configured.

## 24. Cross-Tenant Administration Must Be a Separate Privilege

Some platform operators have permission to support multiple tenants. Never create shortcuts like:

~~~text
if role == ADMIN:
    skip all tenant checks
~~~

A cross-tenant admin policy should:
- Use a separate authority, e.g., `SCOPE_platform.tenants.read` or a governed operational role.
- Separate actor kind (platform operator) from tenant users.
- Require a reason/support ticket for sensitive access where appropriate.
- Audit actor, target tenant, resource, action, reason, and request ID.
- Bound time/privileges using just-in-time elevation if supported by the organization.
- Protect admin endpoints separately with network/MFA requirements.
- Never use `tenantId` from the request as proof; operators must still select target tenants per policy and auditing.

Example:

~~~text
Normal tenant user:
  access only within active membership

Platform support operator:
  explicit cross-tenant permission
  explicit target tenant
  audited access
  restricted actions
~~~

**Admin does not mean bypassing all tenant isolation.** Cross-tenant access is a controlled, auditable capability.

## 25. Tenant-Aware Error Handling

When an order ID does not exist or belongs to another tenant, the API can choose:
- **404 Not Found** to avoid disclosing object existence.
- **403 Forbidden** if policy allows disclosing object existence while denying actor access.

Stay consistent with the API contract. Never return:

~~~json
{
  "error": "Order exists but belongs to tenant red",
  "tenantId": "red"
}
~~~

to Alice from tenant blue.

Do not expose sensitive details in client responses. Internal audits can record tenant/resource IDs per data handling policy.

### Authentication Failures vs. Tenant Authorization Failures

- Invalid token: 401.
- Valid token lacking membership in the requested tenant: typically 403 or 404 per disclosure policy.
- Membership database unavailable: fail closed; classify as dependency failure, never create a default `TenantContext`.
- Resource belongs to another tenant: return no data.
- User has membership but lacks `orders.write`: 403.

Do not turn a membership service outage into "user does not belong to tenant" when operational distinction is needed. Client responses can stay generic, while logs/metrics need clear failure categories.

## 26. Common Anti-Patterns

| Anti-Pattern | Risk | Correct Approach |
|---|---|---|
| Trusting `tenantId` from path/header | Caller picks any tenant | Verify membership |
| Verifying JWT then querying by object ID alone | BOLA/IDOR | Tenant-scoped queries |
| Using `sub` without issuer | Identity collision | Issuer + subject |
| Using email as identity key | Email can change/collide | Stable issuer identity |
| Treating tenant claim as permanent membership | Stale claim after revocation | Current membership/version policy |
| Body `tenantId` overriding context | Cross-tenant writes | Tenant from server-side context |
| `SELECT` has tenant filter, `UPDATE` does not | Cross-tenant writes | Tenant predicate on all writes |
| Checking tenant only in controller | Internal paths can bypass | Service/repository enforcement |
| Cache key contains only `orderId` | Cross-tenant cache leak | Tenant namespace |
| Search filtering only in UI | Data/facet leakage | Server-side tenant filters |
| Export queries not tenant-scoped | Bulk data leak | Scope queries and downloads |
| `ThreadLocal` tenant in WebFlux | Context bleed | Explicit parameters / Reactor Context |
| Event consumer trusting `tenantId` from any message | Forged events | Trusted producer + revalidation |
| Admin role bypassing everything | Privilege escalation | Explicit audited cross-tenant capability |
| Using UUIDs instead of authorization | BOLA still exists | Object-level checks |
| RLS with pooled session setting not reset | Tenant context leak | Transaction-scoped setting |
| Testing only the happy path | Cross-tenant bugs undetected | Cross-tenant negative tests |

## 27. Testing Tenant Isolation

Tests must prove tenant A's data cannot be accessed by an actor from tenant B, even when the actor holds a valid token.

| Test Case | Setup | Expectation |
|---|---|---|
| Blue user reads blue order | Active blue membership, read scope | Allowed if object policy passes |
| Blue user reads red order | Valid token, red tenant order | No data returned |
| User without blue membership | Requests tenant blue | 403/404 per contract |
| User has membership but token lacks scope | Right tenant, missing scope | 403 |
| Identical `sub` JWT from another issuer | Different issuer namespace | Does not use the other issuer's membership |
| Client credentials calling user-only route | No user subject | Rejected per actor policy |
| Body sends tenant red while context is blue | Create/update | Rejected or field ignored per contract; never writes to tenant red |
| Path tenant differs from claim/default tenant | No membership | Denied |
| Forged `X-Tenant-Id` header | Caller-supplied | Not trusted |
| Guessable order ID | Cross-tenant ID | No access |
| Update red order by ID | Blue tenant context | 0 rows updated / denied |
| Cross-tenant delete | Blue tenant context | Not deleted |
| Cross-tenant customer/order join | Wrong foreign relation | DB constraint/query returns nothing cross-tenant |
| Cache same order ID across two tenants | Tenant-aware cache keys | No wrong response served |
| Search/facets | Multi-tenant dataset | Counts/results reflect only current tenant |
| Export | Blue tenant export | File contains only blue data |
| Async event tenant mismatch | Red tenant event, blue order | Rejected/quarantined |
| Revoked membership | Stale cache/context | Behavior matches freshness SLA |
| DB RLS | Actual app DB role | Queries cannot read/write cross-tenant |
| R2DBC connection reuse | Tenant A then tenant B on pool | No context leakage |
| Platform admin | Explicit cross-tenant permission | Only granted actions, audited |
| Tenant membership store outage | Cannot verify | Fail closed, never default allow |

### Integration Tests Should Traverse All Boundaries

- Real `SecurityWebFilterChain` to verify JWT/opaque authentication.
- Real tenant resolver or controlled membership repository.
- Services and repositories with a test database.
- Cache/search adapters when testing cross-tenant leakage.
- R2DBC transactions/connection pools if using a reactive DB.
- Event consumer tests for async contexts.
- Assertions on side effects, not only HTTP status codes.

`mockJwt` is useful for authorization tests but does not verify real signatures. Dedicated signed JWT/JWKS integration tests are required to verify authentication.

## 28. Observability and Auditing Without Leaking Data

Logs/audits can record:
- `requestId`/`correlationId`.
- Configured issuer ID.
- Actor kind (`USER`/`CLIENT`/`PLATFORM_OPERATOR`).
- Internal actor ID if permitted by policy.
- Verified tenant ID.
- Resource type and resource ID per data classification.
- Action (`read`/`update`/`delete`/`export`).
- Authorization outcome and failure category.
- Membership/policy version if helpful.
- Timestamp and source service.

Never log:
- Raw access tokens or refresh tokens.
- `Authorization` headers.
- Passwords/client secrets.
- Full JWT claims.
- Sensitive business record data.
- Unverified tenant IDs as authenticated context.
- Full request bodies if they contain PII.

Metrics should use bounded-cardinality labels. Never use `userId`/`orderId`/tokens as metric labels. You can measure:
- Tenant authorization allow/deny counts.
- Denied cross-tenant lookups.
- Membership cache age.
- RLS violations.
- Queries missing tenant predicates via code review/static analysis or query instrumentation.
- Export row counts per tenant.
- Cache namespace mismatches.
- Async event tenant mismatches.

Audit logs must be protected against unauthorized modification or deletion per system compliance requirements.

## 29. Process for Designing a Tenant-Aware Endpoint

Example update-order endpoint:

~~~text
PUT /api/tenants/{tenantId}/orders/{orderId}
  |
  v
1. Verify Bearer token
   issuer, audience, signature, exp/nbf
  |
  v
2. Require SCOPE_orders.write
  |
  v
3. Normalize actor identity
   issuer + subject/client identity
  |
  v
4. Resolve requested tenant
   active membership / explicit platform permission
  |
  v
5. Load/update only within tenant
   WHERE id = orderId AND tenant_id = tenantId
  |
  v
6. Check object/business permission
   owner/assignment/status/version
  |
  v
7. Persist with tenant predicate
   transaction / optimistic lock
  |
  v
8. Audit and publish tenant-scoped event
  |
  v
9. Return only allowed representation
~~~

At each step, errors must preserve exact semantics:
- Invalid token: authentication failure.
- Missing scope: authorization failure.
- No tenant membership: tenant access denied.
- Absent/out-of-tenant resource: 404 or denial per disclosure policy.
- DB/membership dependency down: fail closed.
- Business state conflict: conflict/domain response per API contract.

Never return data before all relevant checks complete.

## 30. Summary

~~~text
Trusted OAuth/OIDC token
        |
        v
Authentication
  issuer + subject/client
  audience + token validity
        |
        v
Tenant resolution
  requested tenant
  + verified membership
        |
        v
TenantContext
        |
        v
Coarse authorization
  scopes / authorities
        |
        v
Object authorization
  tenant ownership
  assignment / role
  business state
        |
        v
Tenant-scoped repository
  SELECT / INSERT / UPDATE / DELETE
        |
        v
Database constraints / optional RLS
        |
        v
Tenant-safe cache, search, export and events
~~~

Principles to remember:

1. **A valid token does not automatically grant access to every object** in the API.
2. **Authentication, tenant resolution, and authorization are three separate decisions**.
3. Map identities by issuer + subject; distinguish human users from machine clients.
4. Tenants in paths/headers/bodies are requested contexts requiring membership or capability verification.
5. `TenantContext` is created only after identity and tenant access are verified.
6. Scopes are coarse-grained permissions; object ownership, tenant membership, and business state need separate checks.
7. Every `SELECT`/`INSERT`/`UPDATE`/`DELETE`/join/search/export must enforce the tenant boundary.
8. Cache keys, search filters, download paths, and async events must be tenant-aware.
9. R2DBC/WebFlux requires proper reactive context/transactions; avoid `ThreadLocal` and session state leaking across connection pools.
10. Database composite keys, foreign keys, and RLS add defense in depth.
11. Cross-tenant admin is a separate, bounded, auditable capability.
12. Negative tests must prove tenant A cannot read/write tenant B's data, even with a valid token for A.

**Conclusion:** Spring Security verifies the access token and provides the principal/authorities, yet the application must turn that identity into a verified tenant context and enforce permissions on every resource. Tenant isolation only holds when tenant predicates and business authorization span end to end—from request to service, repository, database, cache, search, export, and background processing.

## 31. References

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server:** JWT/opaque token authentication in WebFlux. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security Reference — Reactive Authorization:** `authorizeExchange`, authorities, and reactive access decisions. https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- **Spring Security Reference — Reactive Method Security:** `@EnableReactiveMethodSecurity` and method authorization. https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- **Spring Security Reference — Reactive Security Context:** `ReactiveSecurityContextHolder` and Reactor Context. https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- **Spring Framework Reference — R2DBC:** reactive relational database access and `DatabaseClient`. https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- **Spring Framework Reference — Reactive Transactions:** reactive transaction management. https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- **PostgreSQL Documentation — Row Security Policies:** `ENABLE`/`FORCE ROW LEVEL SECURITY`, `USING`, and `WITH CHECK`. https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- **PostgreSQL Documentation — SET and SET LOCAL:** transaction-scoped configuration settings. https://www.postgresql.org/docs/current/sql-set.html
- **OWASP API Security Top 10 — API1 Broken Object Level Authorization:** object-level authorization failures. https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- **OWASP Authorization Cheat Sheet:** deny by default, least privilege, and server-side authorization. https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- **OWASP Multi-Tenant Security Cheat Sheet:** tenant isolation, context propagation, and cross-tenant access controls. https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html
- **RFC 7519 — JSON Web Token:** issuer, subject, audience, and claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access token profile and audience. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection:** active state and introspection attributes. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer credentials and scope semantics. https://www.rfc-editor.org/rfc/rfc6750
