# Enforcing Ownership and Tenant Checks in the Business Layer

In a multi-tenant application, successful JWT authentication and having the right scope are still not enough to let a user read or modify every resource. The API must verify **whether the caller is the resource owner** and **whether the resource belongs to a tenant the caller is permitted to access**. These decisions belong in the business layer because they depend on the relationship between the user, tenant, and specific data in the system.

A common mistake is checking permissions only at the URL level—such as `SCOPE_orders.read`—and then querying an order by the client-supplied ID. A user can change the ID in the path to read someone else's order or another tenant's order. This is an object-level authorization flaw commonly known as IDOR/BOLA. Scope indicates what kind of action is allowed; ownership and tenant policies determine **which object** that action can be applied to.

This exercise builds multi-layered enforcement: extracting identity from the `Authentication` verified by Spring Security, establishing tenant context, querying data with tenant constraints, checking ownership in the service/domain policy, protecting read/write/delete operations, handling concurrency, and testing with MockMvc alongside service/repository tests.

> **Illustrative context:** The Orders API uses Spring Boot 3.x and Spring Security 6.x. The JWT has already had its signature, issuer, audience, and expiration verified by the Resource Server. The token provides the subject `sub`, tenant claim `tenant_id`, and scopes such as `orders.read` or `orders.write`. The database has an `orders` table with `id`, `tenant_id`, and `owner_subject`. These values are examples; applications must map them to their actual token contract and schema.

## 1. Authentication, Scope, Ownership, and Tenant Are Distinct Decisions

A request to access a resource must pass multiple questions:

1. **Authentication:** Is the token valid and can a principal be identified?
2. **Coarse-grained authorization:** Does the principal have the scope/role for this operation?
3. **Tenant authorization:** Does the principal have permission within the tenant containing the resource?
4. **Object-level authorization:** Is the principal the owner or permitted to share/manage that specific resource?
5. **Business policy:** Does the resource's current state allow the operation at this time?

For example, `alice` has `SCOPE_orders.read` and `tenant_id=tenant-a`. Alice sends:

~~~http
GET /api/orders/order-42
Authorization: Bearer <access-token>
~~~

The `orders.read` scope alone does not prove `order-42` belongs to Alice or `tenant-a`. The service must verify the corresponding record before returning data.

| Check | Example | Question answered |
|---|---|---|
| Authentication | JWT signature, issuer, exp | Who is calling? |
| Scope | `SCOPE_orders.read` | Are they allowed to read this resource type? |
| Tenant | `tenant_id=tenant-a` | Is it within the allowed tenant boundary? |
| Ownership | `owner_subject=alice` | Are they allowed to access this specific object? |
| Business state | Order is not archived/cancelled | Does the current state permit the operation? |

Do not collapse these checks into a single `isAuthenticated()` or a single scope.

## 2. Extracting Subject and Tenant from the Verified Authentication

With a JWT Resource Server, Spring Security creates a `JwtAuthenticationToken`. The controller can receive `Jwt` via `@AuthenticationPrincipal`:

~~~java
@GetMapping("/api/orders/{orderId}")
public OrderResponse getOrder(
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    String subject = jwt.getSubject();
    String tenantId = jwt.getClaimAsString("tenant_id");

    return orderService.getOrder(orderId, subject, tenantId);
}
~~~

`sub` and `tenant_id` must come from a JWT already verified by the decoder. Do not take subject/tenant from request bodies, query parameters, or arbitrary client-sent headers and use them directly as identity.

### 2.1. Do Not Trust `tenantId` from the URL as Tenant Context

An endpoint might include the tenant in the path:

~~~http
GET /api/tenants/tenant-a/orders/order-42
~~~

The path variable is only the target the client wants to access. It does not prove the client is permitted to enter that tenant. Compare the path tenant against the authenticated tenant context, or use a membership policy to confirm the user is allowed to operate in the selected tenant.

~~~java
@GetMapping("/api/tenants/{tenantId}/orders/{orderId}")
public OrderResponse getTenantOrder(
        @PathVariable String tenantId,
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    String subject = jwt.getSubject();
    String tokenTenant = jwt.getClaimAsString("tenant_id");

    if (!tenantId.equals(tokenTenant)) {
        throw new AccessDeniedException("Tenant access denied");
    }

    return orderService.getOrder(orderId, subject, tenantId);
}
~~~

This snippet fits a model where a token represents only a single tenant. If a user holds membership in multiple tenants, the `tenant_id` claim may not be the sole source of context; membership must be checked via a trusted policy/service.

### 2.2. Principal Name Is Not Necessarily Email or Username

Use the `sub` claim as a stable subject identifier if the issuer contract specifies so. Do not assume email is unique or immutable. In multi-issuer systems, a subject may only be unique within an issuer's scope; the identity key should then include both the issuer and the subject.

### 2.3. Missing Claims Must Be Handled Safely

If the tenant claim is required but missing or has the wrong type in the token, do not fall back to a default shared tenant or use a tenant from client input. Deny access according to policy and record the appropriate token/domain context error.

~~~java
private String requiredTenant(Jwt jwt) {
    String tenantId = jwt.getClaimAsString("tenant_id");

    if (tenantId == null || tenantId.isBlank()) {
        throw new AccessDeniedException("Tenant context is missing");
    }

    return tenantId;
}
~~~

In production, exception mapping must be consistent. If a missing claim indicates the token fails the access-token contract, it can be treated as an authentication/token validation failure via a custom validator; if tenant is a business membership context, the policy service can deny authorization.

## 3. Designing Data Models with Explicit Tenant and Owner

A minimal orders table might contain:

~~~sql
CREATE TABLE orders (
    id              VARCHAR(64) PRIMARY KEY,
    tenant_id       VARCHAR(64) NOT NULL,
    owner_subject   VARCHAR(255) NOT NULL,
    status          VARCHAR(32) NOT NULL,
    total_amount    DECIMAL(19, 2) NOT NULL,
    created_at      TIMESTAMP NOT NULL
);

CREATE INDEX idx_orders_tenant_owner
    ON orders (tenant_id, owner_subject);

CREATE INDEX idx_orders_tenant_id
    ON orders (tenant_id, id);
~~~

The `tenant_id` and `owner_subject` columns are critical authorization data, not merely display metadata. Control their creation/updates so clients cannot reassign a resource to another tenant or owner.

### 3.1. Tenant Must Be Part of the Query

Avoid querying by ID alone:

~~~java
Optional<Order> findById(String id);
~~~

For tenant-scoped data, prefer queries with a tenant predicate:

~~~java
Optional<Order> findByIdAndTenantId(String id, String tenantId);
~~~

If an endpoint is accessible only to the owner:

~~~java
Optional<Order> findByIdAndTenantIdAndOwnerSubject(
    String id,
    String tenantId,
    String ownerSubject
);
~~~

Database queries constrain the result set right from the start, reducing the risk of a code path forgetting to check after loading the entity.

### 3.2. Repository Methods Express Policy

Spring Data JPA example:

~~~java
public interface OrderRepository extends JpaRepository<Order, String> {

    Optional<Order> findByIdAndTenantId(
        String id,
        String tenantId
    );

    Optional<Order> findByIdAndTenantIdAndOwnerSubject(
        String id,
        String tenantId,
        String ownerSubject
    );

    Page<Order> findAllByTenantId(
        String tenantId,
        Pageable pageable
    );

    Page<Order> findAllByTenantIdAndOwnerSubject(
        String tenantId,
        String ownerSubject,
        Pageable pageable
    );
}
~~~

Method naming clarifies query scope. For repositories using custom SQL/QueryDSL/specifications, the tenant predicate must still be enforced across every read/write path.

### 3.3. Global Tenant Filters Can Help but Do Not Replace Domain Policy

Hibernate filters, database row-level security, or tenant-aware datasources can provide an additional layer of protection. However, they must be properly configured for every transaction/connection and do not solve ownership by themselves. A user may be permitted inside a tenant yet still not allowed to read another user's object.

Use defense in depth: tenant-scoped queries at the repository/domain layer plus database controls where appropriate. Do not rely on an implicit filter without tests proving the filter is always active.

## 4. Writing a Service That Checks Tenant and Ownership

The service is the right place to combine repository lookups with business policy, because multiple controllers may call the same business logic.

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderMapper orderMapper;

    @Transactional(readOnly = true)
    public OrderResponse getOrder(
            String orderId,
            String subject,
            String tenantId) {

        Order order = orderRepository
            .findByIdAndTenantIdAndOwnerSubject(
                orderId,
                tenantId,
                subject
            )
            .orElseThrow(ResourceNotFoundException::new);

        return orderMapper.toResponse(order);
    }
}
~~~

The query constrains by ID, tenant, and owner together. A record belonging to another tenant or another owner is never returned.

### 4.1. `404` or `403` When an Object Does Not Belong to the Caller?

There are two common API behaviors:

- Return `404 Not Found` for both non-existent objects and objects the caller is not permitted to see. This avoids leaking whether a resource ID exists.
- Return `403 Forbidden` when the caller is allowed to know the resource exists but lacks permission to perform the action.

Choose based on your threat model and API contract. To prevent resource enumeration, scoped queries can return the same not-found result in both cases. Ensure response bodies, timing, or client-facing logs do not unintentionally leak information.

### 4.2. Same Tenant, Different Owner

Some roles may read all orders within a tenant, while regular users only read their own. In that case, the policy must clearly distinguish them:

~~~java
public OrderResponse getOrder(String orderId, Actor actor) {
    Order order = orderRepository
        .findByIdAndTenantId(orderId, actor.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    boolean isOwner = order.getOwnerSubject()
        .equals(actor.subject());

    boolean canReadAll = actor.hasAuthority("ROLE_TENANT_ORDER_ADMIN");

    if (!isOwner && !canReadAll) {
        throw new AccessDeniedException("Order access denied");
    }

    return orderMapper.toResponse(order);
}
~~~

This example assumes `Actor` has been constructed from an authenticated principal and authorities. Never construct `Actor` from a client-controlled request body.

### 4.3. Policy Should Be Named, Testable Code

When rules become complex, extract a dedicated component:

~~~java
@Component
public class OrderAccessPolicy {

    public boolean canRead(Order order, Actor actor) {
        if (!order.getTenantId().equals(actor.tenantId())) {
            return false;
        }

        return order.getOwnerSubject().equals(actor.subject())
            || actor.hasAuthority("ROLE_TENANT_ORDER_ADMIN");
    }

    public boolean canModify(Order order, Actor actor) {
        return order.getTenantId().equals(actor.tenantId())
            && (
                order.getOwnerSubject().equals(actor.subject())
                || actor.hasAuthority("ROLE_TENANT_ORDER_ADMIN")
            )
            && order.getStatus() != OrderStatus.CANCELLED;
    }
}
~~~

The policy can be unit tested with combinations of owner, tenant, role, and state. The service must still fetch the entity safely from the repository before invoking the policy.

## 5. Preventing Clients from Self-Assigning Owner or Tenant

When creating an order, owner and tenant must come from the authenticated actor/context:

~~~java
@PostMapping("/api/orders")
public OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request,
        @AuthenticationPrincipal Jwt jwt) {

    Actor actor = actorFactory.from(jwt);
    return orderService.createOrder(request, actor);
}
~~~

~~~java
@Transactional
public OrderResponse createOrder(
        CreateOrderRequest request,
        Actor actor) {

    Order order = new Order();
    order.setId(idGenerator.nextId());
    order.setTenantId(actor.tenantId());
    order.setOwnerSubject(actor.subject());
    order.setStatus(OrderStatus.PENDING);
    order.setTotalAmount(request.totalAmount());

    return orderMapper.toResponse(orderRepository.save(order));
}
~~~

`CreateOrderRequest` should not allow callers to set `tenantId`, `ownerSubject`, `createdBy`, or other security-sensitive fields. If a DTO contains such fields for compatibility, the server must ignore or reject them; never bind a request body directly to an entity.

### 5.1. Beware of Mass Assignment

Avoid:

~~~java
Order order = objectMapper.convertValue(request, Order.class);
orderRepository.save(order);
~~~

Mapping the entire request onto an entity can allow clients to overwrite `tenantId`, `ownerSubject`, `status`, or internal properties. Use an allowlisted DTO and assign server-controlled fields explicitly.

## 6. Checking Ownership on Updates

Updates must load the object within the tenant context and verify the actor has permission to modify it before applying changes.

~~~java
@Transactional
public OrderResponse updateOrder(
        String orderId,
        UpdateOrderRequest request,
        Actor actor) {

    Order order = orderRepository
        .findByIdAndTenantId(orderId, actor.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    if (!orderAccessPolicy.canModify(order, actor)) {
        throw new AccessDeniedException("Order update denied");
    }

    order.setDeliveryAddress(request.deliveryAddress());
    order.setCustomerNote(request.customerNote());

    return orderMapper.toResponse(order);
}
~~~

Do not copy an entire DTO onto an entity. Update only the fields permitted by the use case. `tenantId`, `ownerSubject`, `createdBy`, `createdAt`, and security status require their own dedicated business flows.

### 6.1. Conditional Updates Directly in SQL

For simple operations, you can use an update query constrained by tenant/owner:

~~~java
@Modifying
@Query("""
    update Order o
       set o.customerNote = :note
     where o.id = :orderId
       and o.tenantId = :tenantId
       and o.ownerSubject = :subject
    """)
int updateNoteIfOwned(
    String orderId,
    String tenantId,
    String subject,
    String note
);
~~~

If the updated row count is 0, the resource does not exist or the actor lacks permission per the query. This keeps predicate authorization and mutation inside the same SQL statement. For complex business policies, load and verify the entity inside a transaction and still apply appropriate optimistic locking/conditional updates.

### 6.2. Ownership Can Change During the Lifecycle

If an order can be transferred to another owner, reassigned, or moved between tenants, create a separate use case with stronger authorization. Never let regular updates change `ownerSubject` or `tenantId`.

Audit the actor, old owner, new owner, tenant, and reason. Only allow tenant transfers when business rules permit and permissions are verified in both source and target tenants.

## 7. Checking Ownership on Deletes

Deletes also require tenant/owner predicates:

~~~java
@Transactional
public void deleteOrder(String orderId, Actor actor) {
    Order order = orderRepository
        .findByIdAndTenantId(orderId, actor.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    if (!orderAccessPolicy.canModify(order, actor)) {
        throw new AccessDeniedException("Order deletion denied");
    }

    orderRepository.delete(order);
}
~~~

If deletion is a soft delete, list/detail queries must always filter out deleted records per policy. If cascading exists, verify child resources also belong to the same tenant and cannot be abused to delete out-of-scope data.

For bulk deletes, do not load a list of IDs and check only a few items. Use tenant-scoped queries and define explicit behavior when the list contains unauthorized objects: reject the entire request or process only valid objects under a clear contract.

## 8. Protecting List, Search, Count, and Export Endpoints

IDOR does not only occur on single-object endpoints. List/search/count/export endpoints can leak tenant data if queries are unrestricted.

Do not use:

~~~java
List<Order> findAll(Pageable pageable);
~~~

Prefer:

~~~java
Page<Order> findAllByTenantId(
    String tenantId,
    Pageable pageable
);
~~~

If users may only see their own orders:

~~~java
Page<Order> findAllByTenantIdAndOwnerSubject(
    String tenantId,
    String subject,
    Pageable pageable
);
~~~

Every secondary query also needs tenant scoping:

- Counts by status.
- Dashboard aggregates.
- Search index queries.
- CSV/PDF exports.
- Reports and analytics.
- Background jobs accepting a tenant ID.
- Downloading files or attachments linked to an order.

A list endpoint with a tenant filter while an export endpoint calls `repository.findAll()` is still an object-level authorization vulnerability.

### 8.1. Pagination Does Not Replace Authorization

Do not filter by tenant after fetching a page from the database. Doing so can leak totals, page counts, ordering, or returned data across tenants and breaks pagination. Tenant/owner predicates must sit in the query before pagination.

### 8.2. Search Indexes Require Mandatory Tenant Filters

If using Elasticsearch/OpenSearch or a search service, pass tenant context from the authenticated actor and enforce the filter in a server-side query builder. Never accept raw query DSL from the client without injecting the tenant condition. Test aggregations, facets, and suggestion endpoints as well.

## 9. Checking Permissions with Method Security

Spring Method Security can guard service methods using `@PreAuthorize`:

~~~java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderResponse getOrder(String orderId, Actor actor) {
        return orderService.getOrder(orderId, actor);
    }
}
~~~

This annotation checks operation-level scope. It does not by itself prove `orderId` belongs to the actor. The service/domain policy must still verify object-level access.

### 9.1. Calling a Policy Bean from `@PreAuthorize`

You can invoke a bean in SpEL:

~~~java
@PreAuthorize("@orderAccessPolicy.canReadById(#orderId, authentication)")
public OrderResponse getOrder(String orderId) {
    // ...
}
~~~

`canReadById` needs to take the authenticated principal and query by tenant/owner. Watch out for duplicate queries if the service then loads the entity a second time. For complex rules, it is often cleaner for the service to load the entity once within tenant scope and then evaluate the policy on that entity.

### 9.2. Method Security Requires a Spring Proxy

`@PreAuthorize` is enforced via a Spring AOP proxy. Call methods through a Spring-managed bean. Self-invocation inside the same object can bypass the proxy and skip the annotation. Unit tests instantiating the service with `new` also do not prove method security is active.

Use MockMvc or integration tests that inject beans from the Spring context to verify the real boundary.

## 10. Passing Verified Identity via an `Actor` Object

Avoid passing separate `subject` and `tenant` strings across many layers where arguments risk being swapped. Create an immutable context:

~~~java
public record Actor(
    String issuer,
    String subject,
    String tenantId,
    Set<String> authorities
) {
    public boolean hasAuthority(String authority) {
        return authorities.contains(authority);
    }
}
~~~

Factory converting from a verified `JwtAuthenticationToken`:

~~~java
@Component
public class ActorFactory {

    public Actor from(JwtAuthenticationToken jwtAuth) {
        Jwt jwt = jwtAuth.getToken();
        String tenantId = jwt.getClaimAsString("tenant_id");

        if (jwt.getSubject() == null
                || tenantId == null
                || tenantId.isBlank()) {
            throw new AccessDeniedException(
                "Required identity claims are missing"
            );
        }

        Set<String> authorities = jwtAuth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toUnmodifiableSet());

        return new Actor(
            jwt.getIssuer() == null ? null : jwt.getIssuer().toString(),
            jwt.getSubject(),
            tenantId,
            authorities
        );
    }
}
~~~

This extracts subject/claims from the `Jwt` principal and authorities from the authentication converter configured in security configuration. Check the authentication type before casting if an endpoint can use multiple authentication mechanisms.

### 10.1. Identity Keys in Multi-Issuer Systems

If multiple issuers can issue the same `sub` value, do not use `subject` alone as a global owner key. Combine issuer and subject or map them to a unique internal user ID. The same email/username from two issuers does not automatically represent the same person.

## 11. Tenant Context in Requests and Background Jobs

### 11.1. Tenant Context Must Have a Trusted Source

Tenant context can come from a claim, a membership service, or an authenticated tenant-selection step. If a user belongs to multiple tenants, choosing a tenant in the request is only a scope-selection request; the server must still verify membership and build `Actor`/context after verification.

Do not let an `X-Tenant-Id` header automatically override the tenant in the JWT without a verification policy. A header can be useful to select among tenants the user is a member of, but it must be cross-checked against a membership store.

### 11.2. Do Not Rely on Unmanaged `ThreadLocal`

If using a `ThreadLocal`-based `TenantContextHolder`, set and clear it inside `try/finally` or a filter/interceptor with a strict lifecycle. Thread pools reuse threads; failing to clear context can cause the next request to run under the wrong tenant.

In async/reactive execution, `ThreadLocal` does not propagate automatically. Use proper context propagation or pass `Actor`/tenant context explicitly across call boundaries.

### 11.3. Background Jobs Without an End-User `Jwt`

Job schedulers, message consumers, or batch tasks may not have a user `SecurityContext`. Use a service identity and an explicit tenant scope recorded in the job envelope, then verify the job is authorized for that tenant. Do not impersonate an arbitrary user to bypass ownership checks.

A job message containing a tenant ID is still untrusted input to verify. Verify the source, signature/message authentication, or service producer permissions; then validate the tenant exists and the job type is permitted.

## 12. Checking Ownership When Calling Downstream Services

If the Orders API calls an Inventory API or Document Service, do not forward an arbitrary client-supplied tenant ID. Determine whether downstream calls use user delegation, service identity, or token exchange:

- **User delegation:** pass an access token with the appropriate audience/scope.
- **Service identity:** use client credentials/service tokens and pass verified business context.
- **Token exchange:** exchange tokens per the authorization server's audience/resource and policy.

Downstream services must still verify their own tokens and tenant/object authorization. The fact that the Orders API checked an owner does not automatically grant the Document Service access to every file.

If using a shared service token, transmit subject/tenant context under a verified trust contract rather than treating client-supplied headers as proof. Audits should record both the end-user actor (if any) and the service identity.

## 13. Preventing TOCTOU and Race Conditions

TOCTOU occurs when an application checks ownership, and then the data changes before the mutation completes.

Example:

1. The service reads an order and confirms the owner is Alice.
2. Another transaction transfers ownership to Bob.
3. The first transaction continues updating the order based on the stale check.

Mitigations:

- Perform lookup, policy check, and mutation within the same transaction.
- Use optimistic locking (`@Version`) to detect concurrent updates.
- Use conditional updates/deletes with tenant/owner predicates.
- Use pessimistic locking when business semantics truly require it.
- Enforce unique/foreign-key constraints on tenant relationships.
- Ensure every mutation path follows the same policy.

### 13.1. Optimistic Locking

Entity with version:

~~~java
@Entity
public class Order {

    @Id
    private String id;

    @Version
    private long version;

    private String tenantId;
    private String ownerSubject;
    private String status;
}
~~~

If another transaction updates the entity after it is loaded, Hibernate detects the version conflict on flush/commit. Handle conflicts per business rules; do not blindly retry mutations if ownership may have changed.

### 13.2. Conditional Mutation

An update statement with tenant/owner predicates eliminates the gap between check and write:

~~~sql
UPDATE orders
   SET customer_note = ?
 WHERE id = ?
   AND tenant_id = ?
   AND owner_subject = ?
   AND status = 'PENDING';
~~~

Check the affected row count. If it is 0, the resource does not exist, does not belong to the actor, or is no longer in a permitted state. Choose the response per the API contract without leaking out-of-scope data.

## 14. Ownership for Relationships and Child Resources

An order may have line items, invoices, shipments, and attachments. Never allow access to a child solely by child ID.

For example, an invoice query must verify the invoice belongs to an order in the actor's tenant:

~~~java
Optional<Invoice> findByIdAndOrderTenantIdAndOrderOwnerSubject(
    String invoiceId,
    String tenantId,
    String subject
);
~~~

If a child resource has its own tenant column, verify consistency with the parent relationship. Do not merely check that `child.tenantId` matches the tenant while ignoring whether the child belongs to an authorized order.

For file attachments, verify authorization before generating a signed download URL. A time-limited URL is itself a bearer capability; its TTL, audience, and scope must be bounded. Do not issue the URL before confirming the user is authorized to read the attachment at request time.

## 15. Multi-Tenant Membership Instead of a Static Tenant Claim

Some systems allow users to belong to multiple tenants. In that case, `tenant_id` in the token may represent the active tenant, or the token may contain only the subject while the application resolves membership.

Membership model:

~~~text
user_tenant_membership
----------------------
issuer
subject
tenant_id
role
status
valid_from
valid_until
~~~

Service checking membership:

~~~java
public Actor selectTenant(
        Jwt jwt,
        String requestedTenantId) {

    String issuer = jwt.getIssuer().toString();
    String subject = jwt.getSubject();

    TenantMembership membership = membershipRepository
        .findActiveMembership(
            issuer,
            subject,
            requestedTenantId,
            clock.instant()
        )
        .orElseThrow(AccessDeniedException::new);

    return new Actor(
        issuer,
        subject,
        membership.tenantId(),
        membership.authorities()
    );
}
~~~

Membership checks must validate active status, validity window, role, and policy. If membership is revoked, cached memberships create a revocation window; set TTL/invalidation according to your SLA.

### 15.1. Do Not Conflate Tenant Claims and Membership Policies

If a token includes a tenant ID, define whether the claim is authoritative or merely a hint. If the membership database is the source of truth, do not treat a stale claim as sufficient to grant access after membership has been revoked. You can combine a token claim to select a candidate tenant and then verify active membership.

## 16. Auditing and Protecting Authorization Data

Record sensitive events:

- Verified actor issuer/subject.
- Tenant context.
- Resource ID and operation.
- Allow/deny outcome.
- Policy/reason code.
- Correlation ID.
- Timestamp and service identity.

Do not log raw JWTs, access tokens, client secrets, or unnecessary personal data. For denied cross-tenant access, internal logs may need to distinguish the reason code, while client responses should not reveal the actual tenant or owner.

Audit logs must be tamper-resistant per system requirements and must never be used as the sole enforcement mechanism for authorization.

## 17. Testing Service/Domain Policies

### 17.1. Owner and Tenant Matrix

| Actor | Resource tenant | Resource owner | Expected |
|---|---|---|---|
| Alice / tenant-a | tenant-a | Alice | Allowed |
| Alice / tenant-a | tenant-a | Bob | Denied unless admin role |
| Alice / tenant-a | tenant-b | Alice | Denied |
| Alice / tenant-a | tenant-b | Bob | Denied |
| Admin / tenant-a | tenant-a | Bob | Allowed if role permits |
| Admin / tenant-a | tenant-b | Bob | Denied if admin is scoped to tenant-a |

This test matrix prevents testing only the owner case while missing cross-tenant access.

### 17.2. Policy Unit Tests

~~~java
class OrderAccessPolicyTests {

    private final OrderAccessPolicy policy = new OrderAccessPolicy();

    @Test
    void ownerCanReadWithinTenant() {
        Order order = order("tenant-a", "alice");
        Actor actor = actor("tenant-a", "alice");

        assertThat(policy.canRead(order, actor)).isTrue();
    }

    @Test
    void differentOwnerCannotReadWithoutAdminRole() {
        Order order = order("tenant-a", "bob");
        Actor actor = actor("tenant-a", "alice");

        assertThat(policy.canRead(order, actor)).isFalse();
    }

    @Test
    void sameOwnerCannotReadAcrossTenant() {
        Order order = order("tenant-b", "alice");
        Actor actor = actor("tenant-a", "alice");

        assertThat(policy.canRead(order, actor)).isFalse();
    }
}
~~~

The `order(...)` and `actor(...)` helpers are test fixtures. Add tests for admin roles, cancelled orders, owner reassignment, and inactive memberships per actual policy.

### 17.3. Repository Integration Tests

Use a test database to verify queries always enforce tenant/owner bounds. Create two tenants with the same subject or similar ID patterns and verify a query for `tenant-a` returns no rows from `tenant-b`. If using native SQL, specifications, or search repositories, test every query path.

Do not mock the repository in every test; mocks do not prove SQL/JPA predicates are actually applied.

### 17.4. Service Integration Tests

Verify the service:

- An owner in the right tenant can read the order.
- A different owner is denied.
- Cross-tenant access is denied.
- A tenant admin can read another user's order in the same tenant.
- A `tenant-a` admin cannot read `tenant-b`.
- Updates cannot change owner/tenant.
- Deletes do not remove out-of-scope child resources.
- No side effects occur when the policy denies access.

## 18. MockMvc Tests with a JWT Principal

MockMvc can use the `jwt()` post-processor to construct a simulated JWT authentication:

~~~java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk());
~~~

This post-processor is suitable for testing authorization/controller/service behavior. It does not verify signatures, issuers, or audiences of raw Bearer tokens. Test the decoder separately to verify the JWT validation pipeline.

### 18.1. Different Owner in the Same Tenant

~~~java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("charlie")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isNotFound());
~~~

Expecting `404` assumes the API hides resource existence from non-owners. If the contract uses `403`, adjust the assertion while preserving the policy.

### 18.2. Different Tenant

~~~java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", "tenant-b")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isNotFound());
~~~

If `order-42` belongs to `tenant-a`, a `tenant-b` actor must not see the data. Verify the response body does not contain the real owner, real tenant, or order fields.

### 18.3. Missing Tenant Claim

~~~java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isForbidden());
~~~

The status depends on how the application handles missing claims. If the claim is mandatory in the token profile, a decoder validator may reject the token and return an authentication failure instead of a domain `403`. What matters is not defaulting to a tenant or letting the request proceed.

### 18.4. Valid Scope but Wrong Owner

~~~java
mvc.perform(put("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("charlie")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.write")
        ))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerNote": "Change delivery note"
            }
            """))
    .andExpect(status().isNotFound());
~~~

This test proves the `orders.write` scope does not replace ownership checks. Verify the repository/entity was not modified after the rejected request.

## 19. Testing List and Bulk Operations

For list endpoints, create fixtures spanning multiple tenants and owners:

~~~java
@Test
void listOnlyReturnsOrdersForCurrentTenant() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().jwt(jwt -> jwt
                .subject("alice")
                .claim("tenant_id", "tenant-a")
                .claim("scope", "orders.read")
            )))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.content[*].tenantId")
            .value(everyItem(is("tenant-a"))));
}
~~~

If the response does not expose `tenantId`, assert that the returned order IDs belong to the `tenant-a` fixture. Check `totalElements`, aggregations, filters, and exports as well; out-of-tenant data must not influence returned metadata if doing so could leak information.

For bulk updates/deletes, policy must be enforced across the entire ID set. One option is querying scoped by tenant/owner and comparing the count of matched IDs with the requested count. On mismatch, reject the entire mutation per contract to avoid unintended partial changes.

## 20. Coordinating Security Configuration and Method Security

Filter chain example:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                .hasAuthority("SCOPE_orders.delete")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Service:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderResponse getOrder(String id, Actor actor) {
    return orderService.getOrder(id, actor);
}
~~~

The filter chain enforces route-level scopes; the service enforces tenant/owner checks. These two layers protect different decisions and must be tested both independently and end-to-end.

## 21. Common Design Pitfalls

1. **Checking only scope:** `orders.read` does not prove a user can read every order.
2. **Trusting tenant ID from the request:** clients can alter headers, paths, or bodies to target another tenant.
3. **Querying by object ID alone:** easily leads to IDOR/BOLA.
4. **Loading an entity and forgetting the owner check:** another controller may return out-of-scope entities.
5. **Protecting only `GET`:** update/delete/export/bulk operations also require object-level policies.
6. **Mapping the request body directly to an entity:** can enable mass assignment of `tenantId`/`ownerSubject`.
7. **Filtering tenants after pagination:** counts, ordering, and page metadata can leak data.
8. **Using `ThreadLocal` without clearing it:** subsequent requests can inherit stale tenant context.
9. **Trusting tenant claims indefinitely:** membership/revocation may have changed.
10. **Method security self-invocation:** internal calls can bypass the Spring proxy.
11. **Only mocking repositories:** fails to prove real queries include the tenant predicate.
12. **Checking ownership then mutating outside a transaction:** creates a TOCTOU race.
13. **Checking only the parent and forgetting child resources:** invoices/attachments may be accessible directly by ID.
14. **Unclear bulk operation partial-update contracts:** out-of-scope resources may be modified.
15. **Not testing admin boundaries:** a `tenant-a` admin does not automatically have rights in `tenant-b`.
16. **Using email as a stable subject:** emails can change or collide across issuers.
17. **Changing tenant via regular updates:** can allow resources to escape boundaries.
18. **Not verifying downstream calls:** another service might trust caller-supplied tenant headers.

## 22. Ownership and Tenant Verification Checklist

- [ ] Subject is taken from the authenticated principal verified by the Resource Server.
- [ ] Tenant context comes from a verified claim or membership policy.
- [ ] Request bodies cannot set `ownerSubject` or `tenantId`.
- [ ] Repository queries always constrain by tenant.
- [ ] Owner predicates are applied for object-level operations.
- [ ] Admin roles have explicit tenant boundaries.
- [ ] Read, list, search, count, export, update, and delete are all protected.
- [ ] Child resources and file attachments verify parent/tenant/owner.
- [ ] DTOs allow updating only permitted fields.
- [ ] Tenant/owner reassignment is a dedicated audited use case.
- [ ] Transactions, optimistic locking, or conditional mutations handle TOCTOU.
- [ ] Async jobs and downstream calls have an explicit tenant trust contract.
- [ ] Method security executes through Spring-managed proxies.
- [ ] Unit, repository, service, and MockMvc tests cover cross-tenant/owner cases.
- [ ] Denied requests produce no side effects.
- [ ] Error responses do not leak resource existence outside policy.
- [ ] Audit logs record actor, tenant, resource, operation, and outcome without logging tokens.

## 23. References

- [OWASP API1:2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): per-object access control and preventing IDOR/BOLA.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default principles and enforcing permissions on every request.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, method interceptors, and authorization.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT principals, claims, and authority conversion.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): testing support for authentication/authorization.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/): repository query derivation, transactions, and persistence.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss` and `sub` claims in JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token profile and validation requirements.

**Conclusion:** Scopes and roles decide what kind of operation a caller may perform; tenant and ownership decide which resources that operation applies to. Extract the subject from the verified principal, establish tenant context via a trust policy, bind tenant/owner directly inside repository queries, and execute mutations inside controlled transactions. Protect detail, list, search, export, update, delete, and child resources uniformly; test cross-tenant, wrong-owner, admin boundaries, and side effects to prevent IDOR/BOLA in the business layer.
