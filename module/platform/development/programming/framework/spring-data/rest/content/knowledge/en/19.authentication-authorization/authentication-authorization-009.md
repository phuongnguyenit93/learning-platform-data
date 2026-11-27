# Limiting Queries by User or Tenant in the Data Layer

## Objective

In a multi-user or multi-tenant application, every query must return only the data that the current principal is permitted to view or modify. For example, two companies sharing an Order management API must not see each other's orders. A user within a company may only access records belonging to their own tenant and may also be restricted by owner or role.

Data scoping must be enforced at the query/persistence layer. Hiding buttons in the UI, checking tenant on the frontend, or filtering responses only after loading all data cannot protect the data. Clients can call the API directly, alter IDs, pass different query parameters, or hit another endpoint.

Key principles:

- Resolve user and tenant from the authenticated identity on the server.
- Include user/tenant predicates in every read, update, and delete query.
- Never trust a tenant ID sent by the client in paths, query strings, or JSON bodies.
- Control collections, items, associations, query methods, counts, and pagination.
- Use database constraints and, where appropriate, row-level security as an additional defense layer.
- Test cross-tenant access cases, not just valid cases.

## 1. Distinguishing authentication, authorization, and data scoping

These three concepts answer different questions:

| Concept | Question | Example |
|---|---|---|
| Authentication | Who is calling the API? | User logged in with OAuth2/JWT |
| Authorization | Is the user permitted to perform this action? | ORDER_READ role or management permission |
| Data scoping | Which rows is the user permitted to see? | Only Orders whose tenant_id matches the user's tenant |

A user holding the `ORDER_READ` role does not mean that user can read every Order in the database. The role permits the action; the tenant/user predicate restricts the dataset that the action may touch.

Example:

- User A belongs to tenant Alpha.
- User B belongs to tenant Beta.
- Both hold read permission on Order.
- When A calls GET collection, only Alpha's Orders are returned.
- When B calls GET item with an ID belonging to Alpha, the server must not return that data.

Do not treat an unpredictable ID or UUID as an authorization mechanism. If a client knows or guesses the ID of a record in another tenant, the request must still be denied.

## 2. Resolving the tenant from the authenticated identity

The tenant must be derived from the authentication context or a trusted server-side mapping. Never take the tenant as a source of truth from the request body or query parameters.

Example JWT with a tenant claim:

    {
      "sub": "user-100",
      "tenant_id": "tenant-alpha",
      "scope": "orders.read orders.write"
    }

Once the token's signature, issuer, audience, expiration, and other security conditions are validated, the application can read the tenant claim from the authenticated principal.

If the tenant is not included in the token, the application can look up the user's membership from a UserTenant table or internal identity service. Clearly define whether a user can belong to one or multiple tenants and the rules for selecting the active tenant.

### 2.1. Server-side tenant context

You can define an abstraction for services to obtain the current tenant:

    public interface CurrentTenantProvider {
        UUID requireTenantId();
    }

An implementation can read claims from the Spring Security Authentication:

    @Component
    public class SecurityCurrentTenantProvider
            implements CurrentTenantProvider {

        @Override
        public UUID requireTenantId() {
            Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()) {
                throw new AccessDeniedException(
                    "Authenticated tenant is required"
                );
            }

            Object principal = authentication.getPrincipal();

            if (!(principal instanceof TenantPrincipal tenantPrincipal)) {
                throw new AccessDeniedException(
                    "Tenant context is unavailable"
                );
            }

            return tenantPrincipal.tenantId();
        }
    }

This is an illustrative example. The principal type and claim extraction depend on your application's Spring Security/OAuth2 setup. Do not cast directly to a specific class if the application uses JwtAuthenticationToken or another principal type.

### 2.2. Do not trust tenant IDs from the client

Avoid designing endpoints like:

    GET /orders?tenantId=tenant-alpha
    GET /tenants/tenant-alpha/orders

if the server uses the client-supplied value as the basis for authorization. Clients can swap the tenant ID to another tenant.

If the API needs a tenant in the URL to select context, the server must still verify that the authenticated user holds membership and permission for that tenant. A tenant in the URL is an input selection to validate, not proof of access rights.

Similarly, do not accept tenant_id from JSON when creating or updating an entity and save it directly. The service should assign the tenant from CurrentTenantProvider:

    order.setTenantId(currentTenant.requireTenantId());

If the tenant ID is a server-managed field, do not expose it as a freely writable client field.

### 2.3. Clearing context after requests

If the application uses ThreadLocal to store tenant context, set and clear the context within the same request boundary, even when exceptions occur. Servlet container threads are reused; leftover context can cause the next request to execute under the wrong tenant.

For async processing, scheduled jobs, or message consumers, do not assume SecurityContext/ThreadLocal propagates automatically to other threads. Pass the tenant explicitly in authenticated jobs/messages and establish the context within the corresponding execution scope.

## 3. Adding tenant predicates to repository queries

Example Order entity with a tenant ID:

    @Entity
    @Table(name = "orders")
    public class Order {

        @Id
        @GeneratedValue
        private UUID id;

        @Column(name = "tenant_id", nullable = false)
        private UUID tenantId;

        private String status;
        private Instant createdAt;
    }

The repository provides methods that always accept the tenant:

    public interface OrderRepository
            extends JpaRepository<Order, UUID> {

        Page<Order> findAllByTenantId(
            UUID tenantId,
            Pageable pageable
        );

        Optional<Order> findByIdAndTenantId(
            UUID id,
            UUID tenantId
        );

        boolean existsByIdAndTenantId(
            UUID id,
            UUID tenantId
        );

        long countByTenantId(UUID tenantId);
    }

The service obtains the tenant from the authenticated context and calls the scoped methods:

    @Service
    public class OrderService {

        private final OrderRepository orders;
        private final CurrentTenantProvider currentTenant;

        public OrderService(
                OrderRepository orders,
                CurrentTenantProvider currentTenant) {
            this.orders = orders;
            this.currentTenant = currentTenant;
        }

        @Transactional(readOnly = true)
        public Page<Order> list(Pageable pageable) {
            UUID tenantId = currentTenant.requireTenantId();
            return orders.findAllByTenantId(tenantId, pageable);
        }

        @Transactional(readOnly = true)
        public Order get(UUID id) {
            UUID tenantId = currentTenant.requireTenantId();

            return orders.findByIdAndTenantId(id, tenantId)
                .orElseThrow(OrderNotFoundException::new);
        }
    }

The tenant condition is applied directly in the SQL generated by Spring Data JPA. The database returns only matching rows; the application never has to load other tenants' data and filter it afterward.

### 3.1. Item lookups must include the tenant predicate

A common mistake is filtering the collection while item lookups still use:

    orders.findById(id);

If the ID belongs to another tenant, that method can return an out-of-scope entity. Use:

    orders.findByIdAndTenantId(id, tenantId);

The same principle applies to:

- existsById.
- update and save.
- deleteById.
- association lookups.
- query methods searching by business key.
- custom repository implementations.
- exports, downloads, and bulk operations.

For both nonexistent items and items belonging to another tenant, the API should typically return the same contract, such as 404, to avoid revealing whether another tenant's data exists. The exact status rule must remain consistent across the API.

### 3.2. Updates and deletes must be scoped

Do not load an entity solely by ID and assume the client may edit it. The service should look up the entity within the current tenant first:

    @Transactional
    public Order changeStatus(UUID id, String status) {
        UUID tenantId = currentTenant.requireTenantId();

        Order order = orders.findByIdAndTenantId(id, tenantId)
            .orElseThrow(OrderNotFoundException::new);

        order.setStatus(status);
        return orders.save(order);
    }

Deletes must also verify scope:

    @Transactional
    public void delete(UUID id) {
        UUID tenantId = currentTenant.requireTenantId();

        Order order = orders.findByIdAndTenantId(id, tenantId)
            .orElseThrow(OrderNotFoundException::new);

        orders.delete(order);
    }

A direct delete statement may use a scoped derived delete query when appropriate, while paying attention to lifecycle callbacks, entity events, and bulk delete semantics. Never use an unscoped deleteById(id) for client requests.

## 4. Pagination, counts, and sorting must also stay within scope

A collection endpoint may return only allowed rows yet still leak information if the count query is unfiltered. For example, page content contains only Alpha's Orders, while totalElements counts both Alpha and Beta.

Every part of a Page must use the same tenant predicate:

- Page content.
- Count query.
- Total pages.
- Aggregations and summaries.
- Facets or filter statistics.
- Exports and reports.

Derived methods such as `findAllByTenantId(tenantId, pageable)` normally let Spring Data generate both the page query and count query with the matching predicate.

When using a custom `@Query`, apply the tenant condition to both the main query and countQuery when declared explicitly:

    @Query(
        value = """
            select o from Order o
            where o.tenantId = :tenantId
              and o.status = :status
            """,
        countQuery = """
            select count(o) from Order o
            where o.tenantId = :tenantId
              and o.status = :status
            """
    )
    Page<Order> findByTenantAndStatus(
        UUID tenantId,
        String status,
        Pageable pageable
    );

This is a JPQL example. The tenant condition must never be omitted from the count query.

Client-requested sorting should be restricted to valid properties appropriate for the API. Sorting does not replace the tenant predicate. If a client requests sorting on sensitive or expensive fields, enforce an allowlist in the service/controller before building Pageable.

## 5. Combining tenant scope with business filters

Clients may send filters such as status, creation date, or Order type. Those filters must be combined with the tenant predicate using AND.

Logical example:

    tenant_id = currentTenant
    AND status = requestedStatus
    AND created_at >= requestedStart

The tenant predicate must always be present, even when the client sends no filters.

With Spring Data JPA Specification:

    public static Specification<Order> belongsToTenant(
            UUID tenantId) {
        return (root, query, builder) ->
            builder.equal(root.get("tenantId"), tenantId);
    }

    public static Specification<Order> hasStatus(String status) {
        return (root, query, builder) ->
            builder.equal(root.get("status"), status);
    }

The service combines the specifications:

    Specification<Order> specification =
        Specification.where(belongsToTenant(tenantId))
            .and(hasStatus(status));

    return orders.findAll(specification, pageable);

This example assumes the repository extends JpaSpecificationExecutor. If filters are optional, only append the corresponding specification when a value is supplied; never omit the tenant specification in any branch.

Never accept an arbitrary client-constructed Specification directly. The API should parse allowed filters, and the service always combines the security predicate into the query.

## 6. Spring Data REST: default endpoints to watch carefully

Spring Data REST can automatically export repositories as REST resources. This requires extra caution in multi-tenant applications: default CRUD methods like `findAll(Pageable)`, `findById(id)`, `save(entity)`, or `deleteById(id)` are not automatically aware of the current tenant just because the entity has a `tenantId` field.

Adding a `findAllByTenantId(...)` method does not automatically replace default CRUD endpoints. If the collection exporter still invokes the unscoped `findAll(Pageable)`, the endpoint can return data from multiple tenants.

### 6.1. Do not protect only search query methods

Suppose the repository has:

    Page<Order> findAllByTenantId(UUID tenantId, Pageable pageable);

If this method is exported as a search endpoint, clients can invoke it with a client-supplied tenant ID if the API exposes that parameter. Never let clients pick a tenant and treat that as isolation.

Beyond search endpoints, review:

- Default GET collection.
- Default GET item.
- PUT/PATCH item.
- DELETE item.
- Association resources.
- Query methods.
- Projections and excerpts.
- Custom controllers and export endpoints.

### 6.2. Safe integration options

Two common approaches exist:

**Option A — Disable repository exporting and use scoped controllers/services**

Mark the repository as not exported:

    @RepositoryRestResource(exported = false)
    public interface OrderRepository
            extends JpaRepository<Order, UUID> {
        // Tenant-scoped methods
    }

Then create dedicated controllers/services. Controllers get the tenant from CurrentTenantProvider and call only scoped repository methods. This is a clear approach when strict control over every endpoint is needed.

**Option B — Keep Spring Data REST while hiding unscoped methods**

You can use `@RestResource(exported = false)` on unsafe CRUD methods and provide separate endpoints that call scoped services/repositories. Inspect all inherited methods that the exporter may invoke, including collection, item, update, and delete operations.

Example intending to hide a method:

    @Override
    @RestResource(exported = false)
    Page<Order> findAll(Pageable pageable);

Hiding this single method is not enough to protect the entire repository. You must handle remaining unscoped methods and related association/query paths. When you cannot prove every access path is scoped, disable repository exporting and use custom controllers.

### 6.3. Method security does not automatically filter collections

Spring Security can protect methods with `@PreAuthorize`:

    @EnableMethodSecurity

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public Page<Order> list(Pageable pageable) {
        // Tenant-scoped repository query.
    }

This annotation checks permission to call the method. It does not automatically inject `tenant_id = ...` into SQL or filter pages/counts.

Similarly, `@PostFilter` can filter results after a method runs, but is usually unsuitable for protecting large collections or Pages: data is already loaded, counts/pagination can become wrong, and leaks can occur through other paths. Apply the tenant predicate directly inside repository/database queries.

## 7. Controlling relationships between entities

A foreign key only proves the referenced row exists. It does not necessarily prove both rows belong to the same tenant.

For example, an Order belongs to tenant Alpha, but a client tries to attach a Customer belonging to tenant Beta. If the foreign key only references `customer.id`, the database may still allow that association.

The service must verify both entities belong to the same tenant:

    UUID tenantId = currentTenant.requireTenantId();

    Customer customer = customers
        .findByIdAndTenantId(customerId, tenantId)
        .orElseThrow(CustomerNotFoundException::new);

    Order order = new Order();
    order.setTenantId(tenantId);
    order.setCustomer(customer);

    orders.save(order);

Do not deserialize an association object from the client and assign it directly onto an entity without verifying ownership.

### 7.1. Composite foreign keys to protect tenant boundaries

If the database should also enforce same-tenant relationships, composite keys/constraints can be used. Example:

    CREATE TABLE customer (
        tenant_id UUID NOT NULL,
        id UUID NOT NULL,
        PRIMARY KEY (tenant_id, id)
    );

    CREATE TABLE orders (
        tenant_id UUID NOT NULL,
        id UUID NOT NULL,
        customer_id UUID NOT NULL,
        PRIMARY KEY (tenant_id, id),
        CONSTRAINT fk_order_customer_same_tenant
            FOREIGN KEY (tenant_id, customer_id)
            REFERENCES customer (tenant_id, id)
    );

This foreign key forces Order and Customer to share the same tenant_id. Actual key structure depends on existing schemas and databases; if ID remains a standalone primary key, you may need a unique constraint on `(tenant_id, id)` as the reference target.

This serves as an additional safeguard for associations that business rules require to be same-tenant. You still need authorization and tenant checks in the service to return clear errors.

## 8. Per-tenant unique constraints and business keys

In a multi-tenant system, a code may be unique within a tenant rather than globally unique across the system.

For example, each tenant can use the same external key:

    @Table(
        uniqueConstraints = @UniqueConstraint(
            name = "uk_order_tenant_external_key",
            columnNames = {"tenant_id", "external_key"}
        )
    )

The repository check for duplicates must include both fields:

    boolean existsByTenantIdAndExternalKey(
        UUID tenantId,
        String externalKey
    );

Do not use `existsByExternalKey(...)` if business rules permit different tenants to use the same key.

A database unique constraint is still necessary to prevent race conditions between concurrent requests in the same tenant. Validators or exists queries only catch duplicates early.

## 9. Row-level security in the database

For databases supporting row-level security, policies can be added so the database itself restricts rows by tenant. This is defense in depth when an application has many repositories, custom queries, or varied data access paths.

PostgreSQL example:

    ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

    CREATE POLICY orders_tenant_policy
    ON orders
    USING (
        tenant_id = current_setting('app.tenant_id')::uuid
    )
    WITH CHECK (
        tenant_id = current_setting('app.tenant_id')::uuid
    );

The application must set the tenant context inside the transaction before running queries:

    SELECT set_config('app.tenant_id', :tenantId, true);

The final argument `true` scopes the setting to the current transaction. Exact setup depends on the JDBC/JPA transaction manager and database.

Important points when using RLS:

- Use a least-privilege database role.
- Ensure the application sets tenant context before every query.
- Tenant context must be bound to the active transaction/connection.
- Prevent a prior request's tenant value from leaking into a pooled connection reused later.
- Check table owners, superusers, and roles with BYPASSRLS; those roles can bypass policies under PostgreSQL rules.
- Consider FORCE ROW LEVEL SECURITY if policies must apply to the table owner.
- Test read, insert, update, and delete queries.
- Never treat RLS as a replacement for application-layer authorization.

RLS is database-specific. PostgreSQL syntax and semantics cannot be copied verbatim to MySQL, SQL Server, or Oracle.

## 10. Hibernate filters and multi-tenancy mechanisms

Hibernate provides features such as discriminator-based multi-tenancy, `@TenantId`, or `@Filter` depending on version.

These mechanisms can automatically add tenant conditions to some ORM queries, but their scope must be understood:

- Hibernate `@TenantId` is provider-specific, not a portable JPA annotation.
- Hibernate filters must be declared and enabled on the session according to the proper lifecycle.
- A filter not enabled on every execution path can leave queries without a tenant predicate.
- Native SQL, direct JDBC, bulk operations, or tools outside Hibernate may not pass through filters like regular ORM queries.
- Test caching, association loading, and session lifecycles with the chosen mechanism.

Do not mix multiple tenant context mechanisms without clear rules. When using Hibernate multi-tenancy or filters, test actual access paths and consider database RLS as an extra defensive layer.

## 11. Caches, search, and auxiliary data

Even when repository queries are scoped, auxiliary layers can still leak data:

- Cache keys must include the tenant ID or equivalent scope.
- Never key caches solely on entity ID if IDs are not globally unique.
- Search indexes must store tenant metadata and enforce mandatory tenant filtering.
- Export files must be generated from scoped queries and enforce download permissions.
- Dashboards, counts, aggregations, and autocomplete must be tenant-restricted.
- Events/messages must carry a verified tenant context.
- Logs and audits should record appropriate tenant IDs without exposing sensitive data.

If a cache or search service is shared across tenants, tenant filters must be applied on every query and must never be bypassable by the client.

## 12. Testing tenant isolation

Tests must prove tenant A cannot read, edit, delete, or link to tenant B's data.

Data setup:

- Tenant Alpha has Order A1 and Customer AC1.
- Tenant Beta has Order B1 and Customer BC1.
- Two authenticated users belonging respectively to Alpha and Beta.

Cases to verify:

| Scenario | Expected verification |
|---|---|
| Alpha GET collection | Sees only Order A1 |
| Beta GET collection | Sees only Order B1 |
| Alpha GET item B1 | Does not return Beta's data |
| Alpha PATCH/PUT item B1 | Does not modify Beta's row |
| Alpha DELETE item B1 | Does not delete Beta's row |
| Alpha filter status/page/sort | Both content and totalElements count only Alpha |
| Alpha creates Order linked to Beta Customer | Rejected |
| Client sends tenantId=Beta in body | Server ignores or rejects it; tenant comes from auth context |
| Two tenants use the same external key | Allowed if unique scope is tenant + key |
| Two requests in same tenant use the same external key | One request rejected by unique constraint |
| Cache/search/export | Never returns results from another tenant |
| Background job | Tenant context is set explicitly and does not leak to other jobs |

Inspect the database directly after denied requests to verify no side effects occurred. For pagination, check both content and count metadata. For RLS, test with the actual application database role, not only as a superuser or table owner.

## 13. Common pitfalls

| Symptom | Cause to investigate |
|---|---|
| Collection is filtered but GET item still leaks data | Item lookup uses findById without a tenant predicate |
| totalElements is larger than visible row count | Count query lacks the tenant condition |
| Client changes tenantId and sees another tenant's data | Server trusts tenant ID from query/path/body |
| Search endpoint ignores tenant | Query method accepts client-supplied tenantId |
| Method security exists yet data still leaks | Authorization checks role, but query is unscoped |
| @PostFilter breaks pagination | Filtering runs after loading the page; count is unrestricted |
| Order attaches Customer from another tenant | Foreign key only checks ID existence, not same tenant |
| Duplicate key falsely reported across tenants | Unique constraint covers only business key without tenant_id |
| Cache returns another tenant's entity | Cache key or cache lookup lacks tenant scope |
| Background job reuses previous tenant | TenantContext/ThreadLocal is not set and cleared properly |
| Hibernate filter sometimes does not apply | Filter is not enabled on every session or SQL path bypasses it |
| Repository REST endpoint still calls default findAll | Unscoped exporter method was not hidden/disabled |

## 14. Implementation checklist

1. Define the tenant model: one user/one tenant or users with multiple tenant memberships.
2. Derive tenant from the authenticated principal or verified memberships.
3. Never trust client-supplied tenant IDs as the basis for authorization.
4. Create a server-side CurrentTenantProvider or equivalent abstraction.
5. Add tenant predicates to every read, count, update, and delete repository query.
6. Use findByIdAndTenantId instead of unscoped findById in user flows.
7. Combine the tenant predicate with all filters, sorting, pagination, and aggregations.
8. Verify Spring Data REST CRUD exporters do not expose unscoped default methods.
9. Use custom controllers/services or hide endpoints that cannot guarantee tenant scoping.
10. Verify association ownership and consider same-tenant composite foreign keys.
11. Scope unique constraints per tenant when business keys only need uniqueness within a tenant.
12. Consider RLS or Hibernate multi-tenancy as an extra defense layer.
13. Include tenant in cache keys, search filters, exports, and background job contexts.
14. Test reads, updates, deletes, counts, associations, and cross-tenant access.
15. Test the database using the actual application role, not solely administrative privileges.

## References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA — Query methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Hibernate ORM — Multi-tenancy](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#multitenacy)
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
