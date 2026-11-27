# Propagating Customer Context and Preventing Cross-Tenant Data Leaks

## 1. Problem statement and key terms to distinguish

In a Spring Data JPA application serving multiple customers, each request must carry context identifying the data the user is permitted to access. When multiple customers share an application or database, missing this context can let a user read, modify, or delete another customer's data.

In multi-tenant architectures, the following terms are commonly used:

- **User/actor**: the person or system making a request.
- **Customer/account**: a business customer or organizational account.
- **Tenant**: the data and configuration isolation boundary in the system.
- **Tenant context**: the authenticated and selected tenant for a request or background job.
- **Data source**: the database connection source. A tenant may use a dedicated database, dedicated schema, or share a schema with other tenants.

Not every customer is a tenant. For example, one company (tenant) may manage thousands of business customers (customer). Never treat a `customerId` sent by the client as proof that the user has permission to access that customer. Clearly define your domain security boundaries before designing context propagation.

The goal of this lesson is to ensure every persistence operation executes inside the right tenant context, even when the application uses multiple DataSources, asynchronous processing, caching, or native queries.

## 2. Choosing a data isolation model

There are three common models. Context propagation works similarly at the security layer, while connection selection and query protection differ.

| Model | Data Storage Approach | Advantages | Trade-offs |
|---|---|---|---|
| Database per tenant | Each tenant has its own database | Strong isolation, easier per-tenant backup/restore | Managing many databases, connection pools, and complex migrations |
| Schema per tenant | Each tenant has its own schema in the same DBMS | Can share server while separating namespaces | Must manage schemas, search paths, and connection/schema switching |
| Shared schema | Multiple tenants share tables, each row has `tenant_id` | Resource-efficient, easy to scale tenant count | Every query, cache, unique key, and write must be scoped accurately |

You may also have multiple DataSources for different purposes such as OLTP, reporting, analytics, or legacy databases. That is the problem of choosing a data source by function. Multi-tenancy is the problem of scoping data by tenant. A system may need both: first select the functional database group, then select the tenant database/schema within that group.

Never select a database based solely on an arbitrary header. The tenant must be authenticated and authorized before being used as a routing key.

## 3. Building a secure tenant context

### 3.1 Never trust self-declared client tenant IDs

A client can send `X-Tenant-Id`, a tenant in the URL, or a field in the request body to select the workspace account. That value is only a **selection to verify**, never proof of access rights.

The flow should be:

1. Authenticate the user with Spring Security or a trusted identity mechanism.
2. Retrieve the list of tenants the principal is authorized to access from verified claims or a membership service.
3. Read the requested tenant from the request if the application allows choosing among multiple tenants.
4. Verify that the requested tenant belongs to the authorized list and that the user has permission to perform the current action.
5. Create the tenant context from the verified result.
6. If there is no tenant or the tenant is invalid, reject the request; never silently fall back to a default tenant.

If the principal belongs to only one tenant, derive that tenant from the authenticated principal. If a user can access multiple tenants, verify membership on each tenant switch or use a signed/verified selection while still enforcing policy checks. Admin accounts may be permitted cross-tenant access, but cross-tenant operations must require dedicated permissions and audit logging.

### 3.2 TenantContext using ThreadLocal with a clear lifecycle

For synchronous requests on a servlet thread, `ThreadLocal` can carry the tenant across service/repository layers without adding parameters to every method. Always clear the context when the request ends because threads are reused in thread pools.

```java
import java.util.Optional;

public final class TenantContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private TenantContext() {
    }

    public static String requireTenantId() {
        String tenantId = CURRENT.get();
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalStateException("Tenant context is missing");
        }
        return tenantId;
    }

    public static Optional<String> currentTenantId() {
        return Optional.ofNullable(CURRENT.get());
    }

    public static Scope open(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }

        String previous = CURRENT.get();
        CURRENT.set(tenantId);

        return () -> {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        };
    }

    public static Runnable propagate(Runnable task) {
        String capturedTenant = CURRENT.get();

        return () -> {
            String previous = CURRENT.get();
            try {
                if (capturedTenant == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(capturedTenant);
                }
                task.run();
            } finally {
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
            }
        };
    }

    @FunctionalInterface
    public interface Scope extends AutoCloseable {
        @Override
        void close();
    }
}
```

Use `Scope` with try-with-resources to guarantee restoring the previous context even when an exception occurs:

```java
try (TenantContext.Scope ignored = TenantContext.open(tenantId)) {
    orderService.createOrder(command);
}
```

In web requests, an interceptor or filter manages the scope. In jobs/message consumers, the worker opens a scope from verified tenant metadata and closes it after processing. Do not let business code arbitrarily overwrite the context without a restoration mechanism.

Do not use `InheritableThreadLocal` as a default solution for executors. Thread pools reuse threads and context can outlive the request lifecycle, causing data leaks between two tasks. Propagate context explicitly or use a controlled propagation mechanism.

### 3.3 Set context after authentication and before calling services

Spring Security handles authentication in its filter chain before requests enter Spring MVC. A `HandlerInterceptor` can read the authenticated principal, validate the selected tenant, and open the context before the controller invokes a `@Transactional` service.

The example below assumes the application has a `TenantAuthorizer` responsible for verifying membership:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.AsyncHandlerInterceptor;

@Component
public class TenantContextInterceptor implements AsyncHandlerInterceptor {

    private static final String SCOPE_ATTRIBUTE =
            TenantContextInterceptor.class.getName() + ".scope";

    private final TenantAuthorizer tenantAuthorizer;

    public TenantContextInterceptor(TenantAuthorizer tenantAuthorizer) {
        this.tenantAuthorizer = tenantAuthorizer;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        String requestedTenant = request.getHeader("X-Tenant-Id");
        String authorizedTenant =
                tenantAuthorizer.resolveAuthorizedTenant(
                        authentication, requestedTenant);

        TenantContext.Scope scope = TenantContext.open(authorizedTenant);
        request.setAttribute(SCOPE_ATTRIBUTE, scope);
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        closeScope(request);
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        closeScope(request);
    }

    private void closeScope(HttpServletRequest request) {
        Object value = request.getAttribute(SCOPE_ATTRIBUTE);
        if (value instanceof TenantContext.Scope scope) {
            scope.close();
            request.removeAttribute(SCOPE_ATTRIBUTE);
        }
    }
}
```

`TenantAuthorizer` is a security business component of the application; never implement it by simply returning the header without verifying principal/membership. Register the interceptor via `WebMvcConfigurer`. Because the interceptor runs in MVC after the Spring Security filter chain, `SecurityContextHolder` already holds the authentication when security is configured properly.

`afterCompletion` cleans up context in synchronous requests. For async MVC, `afterConcurrentHandlingStarted` cleans up the initial thread; work on the executor must receive its own tenant context via a `TaskDecorator` as shown later. Do not rely on the servlet thread's context after a request shifts to asynchronous execution.

If using WebFlux/reactive stack, do not use `ThreadLocal` this way; use Reactor Context and the corresponding propagation mechanism because a request can switch threads across operators.

## 4. Selecting a DataSource per tenant

### 4.1 Separate database per tenant

When each tenant has its own database, Spring's `AbstractRoutingDataSource` can select the DataSource based on the current tenant context:

```java
import org.springframework.jdbc.datasource.lookup.AbstractRoutingDataSource;

public class TenantRoutingDataSource extends AbstractRoutingDataSource {

    @Override
    protected Object determineCurrentLookupKey() {
        return TenantContext.requireTenantId();
    }
}
```

Configure the routing datasource with registered tenants:

```java
Map<Object, Object> targets = new HashMap<>();
targets.put("tenant-a", tenantADataSource);
targets.put("tenant-b", tenantBDataSource);

TenantRoutingDataSource routing = new TenantRoutingDataSource();
routing.setTargetDataSources(targets);
routing.setLenientFallback(false);
routing.afterPropertiesSet();
```

This is the core configuration; the `tenantADataSource` and `tenantBDataSource` beans, credentials, and connection pools must be created from secure configuration. Never hardcode passwords in maps or source code. In real Spring Boot configurations, the routing datasource is typically exposed as `@Primary` and used by the appropriate `EntityManagerFactory`/`JpaTransactionManager`.

Important principles:

- Never declare a default datasource pointing to tenant A. Missing context must fail closed rather than silently accessing a default tenant's data.
- `setLenientFallback(false)` rejects lookup keys absent from the target map. `requireTenantId()` also rejects empty context.
- Route only to tenants registered in the tenant registry; never create datasources from unvalidated client-supplied strings.
- Never create a new connection pool per request. Pool count and total connections scale with tenant count; enforce limits, lifecycle management, and connection budgets.
- When adding/removing tenants, update the registry safely and manage migrations/credentials through a dedicated process. `AbstractRoutingDataSource` by default suits targets configured at startup; dynamic registries require dedicated synchronization design.

### 4.2 Separate schema per tenant

If tenants share a database while each tenant has its own schema, you can switch schemas on connections or use Hibernate multi-tenancy. With Hibernate, the relevant components are typically `CurrentTenantIdentifierResolver` and `MultiTenantConnectionProvider`.

When using schema switching:

- Tenant identifiers must be resolved from verified context.
- Connections must switch to the right schema before querying.
- When returning a connection to the pool, reset the schema/`search_path` to a safe state.
- Never let the previous tenant's schema linger on a connection handed to the next tenant.
- Migrations must create/update schemas for all tenants to the same version.
- Tests must verify schema switching across reused pooled connections.

Configuration details depend on the Hibernate version and DBMS. Standard JPA does not fully standardize multi-tenancy strategies; consult documentation for the exact provider you use instead of copying configs from another version.

### 4.3 Shared schema with tenant_id

When multiple tenants share tables, every tenant-data table must have a `tenant_id` column. Every read/write query must be constrained by tenant. A single missing tenant predicate in one repository method can expose cross-tenant data.

Example entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
    name = "orders",
    schema = "app",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_orders_tenant_external",
        columnNames = {"tenant_id", "external_id"}
    )
)
public class PurchaseOrder {

    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private String tenantId;

    @Column(name = "external_id", nullable = false)
    private String externalId;

    @PrePersist
    void assignTenant() {
        String currentTenant = TenantContext.requireTenantId();

        if (tenantId != null && !tenantId.equals(currentTenant)) {
            throw new SecurityException("Entity tenant does not match context");
        }

        tenantId = currentTenant;
    }

    @PreUpdate
    void preventTenantChange() {
        if (!TenantContext.requireTenantId().equals(tenantId)) {
            throw new SecurityException("Cross-tenant entity update rejected");
        }
    }
}
```

This snippet is illustrative; the entity needs constructors/accessors and the appropriate JPA imports. In practice, it is better not to expose a setter for `tenantId`. The tenant ID must be assigned from server-side context upon entity creation, never taken directly from the request body. Unique constraints usually must include `tenant_id` alongside business keys; enforcing uniqueness solely on `email` or `external_id` globally could block tenants from using the same values or create flawed validation logic.

Repositories should expose explicitly tenant-scoped methods:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {

    Optional<PurchaseOrder> findByIdAndTenantId(
            UUID id, String tenantId);

    List<PurchaseOrder> findAllByTenantIdAndStatus(
            String tenantId, OrderStatus status);

    boolean existsByTenantIdAndExternalId(
            String tenantId, String externalId);
}
```

Services obtain the tenant from verified context:

```java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public PurchaseOrder getOrder(UUID id) {
        String tenantId = TenantContext.requireTenantId();

        return repository.findByIdAndTenantId(id, tenantId)
                .orElseThrow(() -> new EntityNotFoundException(
                        "Order not found"));
    }
}
```

In shared schema setups, avoid calling `findById(id)` directly on tenant-owned entities unless that method is protected by a reliable tenant filtering mechanism. Do not reveal that an ID exists in another tenant; usually return not found or access denied according to API policy.

### 4.4 Hibernate @TenantId

Hibernate provides its own `org.hibernate.annotations.TenantId` annotation for discriminator-based multi-tenancy. When Hibernate multi-tenancy is properly configured with a `CurrentTenantIdentifierResolver`, Hibernate can assign the tenant ID on persist and apply tenant restrictions to provider-managed entity operations.

This is a Hibernate-specific feature, not a standard Jakarta Persistence annotation. Before using it:

- Verify your Hibernate version supports it and configure an appropriate resolver.
- Do not assume native SQL, direct JDBC, or all bulk operations are automatically protected like entity queries.
- Test access paths across EntityManager, repositories, native queries, bulk updates/deletes, and caches.
- Never allow clients to set the tenant field directly; context must come from authentication/authorization.

Even with `@TenantId`, cross-tenant tests and database-level defense in depth remain essential for sensitive data.

## 5. Ensuring transactions use the right tenant

This is the easiest place to introduce bugs when combining a routing datasource with `@Transactional`.

Spring's transaction manager normally acquires a connection or binds an EntityManager/connection to the thread when the transaction begins. Therefore, tenant context must be set **before calling the `@Transactional` service method**. If you set the tenant inside the method after the transaction has started, the connection may have already been chosen for an old tenant or with no context.

Correct flow:

1. Spring Security authenticates the user.
2. Interceptor verifies the tenant and opens `TenantContext`.
3. Controller calls the service.
4. Spring transaction proxy opens the transaction.
5. DataSource/EntityManager acquires a connection according to the tenant context.
6. Repositories execute within that transaction.
7. Transaction commits/rolls back.
8. Interceptor closes `TenantContext` when the request ends.

Never switch tenants mid-transaction. One transaction should remain bound to exactly one tenant from start to finish. If multiple tenants must be processed, split into separate transactions, each with its own context. When using `REQUIRES_NEW`, the current context stays on the thread; only switch tenants when genuinely required by the business logic, and open/restore context in a controlled manner before the new transaction begins.

With multiple EntityManagerFactories/transaction managers, bind repositories to the right pair via `entityManagerFactoryRef` and `transactionManagerRef`. Never allow a tenant group's routing datasource to be mistakenly used by repositories belonging to a different functional database.

## 6. Propagating context to @Async, executors, and message queues

### 6.1 ThreadLocal does not propagate automatically to other threads

`ThreadLocal` binds only to the current thread. When using `@Async`, `Executor`, `CompletableFuture`, or schedulers, work may run on another thread and fail to receive tenant context. If a thread pool retains stale context, subsequent tasks even risk running under the wrong tenant.

You can use Spring's `TaskDecorator` to capture context at submission time and set/restore context at execution time:

```java
import org.springframework.core.task.TaskDecorator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TenantAsyncConfiguration {

    @Bean
    TaskDecorator tenantTaskDecorator() {
        return TenantContext::propagate;
    }
}
```

Configure the `TaskDecorator` on the `ThreadPoolTaskExecutor` used by `@Async` or the corresponding executor. The `TenantContext.propagate()` method in Section 3 captures the current tenant, sets context in the worker thread, and restores the previous value in `finally`.

Never propagate the entire `SecurityContext` or unvalidated tenant context blindly across all executors. Pass only the minimal necessary data and re-verify permissions at appropriate execution boundaries. For long-running or cross-process tasks, store the tenant identifier in signed or trusted-service-generated message/job metadata, then re-verify when the consumer receives the message.

### 6.2 Message consumers and scheduled jobs

With Kafka/RabbitMQ/JMS or schedulers:

- Messages must carry an explicit tenant key if processing tenant data.
- Only trusted producers may generate tenant metadata; consumers still verify that the tenant exists and is authorized to process.
- Open `TenantContext` for the scope of a single message/job and always close it in `finally`.
- Never rely on leftover `ThreadLocal` state from a prior message.
- Retries and dead-letter queues must preserve the exact tenant metadata to avoid misrouting tenants.
- If a batch contains multiple tenants, partition the batch by tenant and open separate transactions per tenant.

Never treat a tenant ID inside a message as sole proof of authorization. If messages can originate from clients or untrusted sources, verify signatures/producers and validate relationships between the message, tenant, and business operation.

## 7. Preventing leaks via repositories, queries, and caches

### 7.1 Scope every query

In a shared schema, every tenant-scoped query needs a tenant predicate. This applies to:

- Derived queries and JPQL.
- Native SQL.
- Update/delete queries with `@Modifying`.
- Specifications and Criteria API.
- Pagination, sorting, and projections.
- Custom repository implementations and `JdbcTemplate`.

Never run an unrestricted `findAll()` for tenant data and filter in Java after loading all rows into memory. Another tenant's data has already traversed application memory, logs, or serialization before filtering. Scoping must happen at the database query level.

For bulk updates/deletes, verify tenant predicates in the SQL/JPQL statement itself. Bulk operations typically bypass lifecycle callbacks and may bypass the persistence context; consider `clearAutomatically` or clearing/refreshing the EntityManager appropriately afterward.

### 7.2 Cache keys must include the tenant

If a cache uses only an entity ID as its key, two tenants with the same business ID can read the same cache entry. Keys must include the tenant identifier:

```java
@Cacheable(
    cacheNames = "orders",
    key = "T(com.example.TenantContext).requireTenantId() + ':' + #id"
)
public OrderView getOrder(UUID id) {
    // Load order within the current tenant context.
}
```

This is a Spring Cache example; adjust package names and DTOs for your project. Apply the same principle to Redis, Caffeine, projection caches, API response caches, search indexes, object storage paths, and distributed lock keys.

With Hibernate second-level/query caches, verify tenant-aware behavior for your exact provider version. Custom caches or caches external to Hibernate must include the tenant in keys manually. On logout, tenant switching, or membership changes, consider tenant/user-scoped invalidation.

### 7.3 Unique keys and data relationships

In a shared schema, constraints typically must include the tenant:

- `UNIQUE (tenant_id, external_id)` instead of `UNIQUE (external_id)` alone when codes are unique only per tenant.
- Foreign keys should prevent a child row of tenant A from referencing a parent row of tenant B.
- Indexes commonly lead with `tenant_id` for tenant-filtered queries, depending on workload and query plans.
- Auxiliary tables like attachments, audit logs, outbox, notifications, and join tables also need tenant scope when holding tenant data.

For cross-tenant foreign key prevention, composite keys/constraints combining `tenant_id` and entity ID let the database enforce same-tenant integrity. Do not rely solely on service-layer validation.

## 8. Additional database protection with Row-Level Security

When using PostgreSQL with a shared schema, Row-Level Security (RLS) can add a database-level defense layer. Policies filter readable rows and validate inserted/updated rows.

Example when `tenant_id` is UUID:

```sql
ALTER TABLE app.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.orders FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON app.orders
USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::uuid
);
```

Within each transaction, set the tenant on the same connection before accessing tables:

```java
@Transactional
public void processTenantOrder(UUID orderId) {
    String tenantId = TenantContext.requireTenantId();

    entityManager.createNativeQuery(
            "select set_config('app.tenant_id', :tenantId, true)")
        .setParameter("tenantId", tenantId)
        .getSingleResult();

    // Subsequent queries in this transaction are subject to the RLS policy.
    orderRepository.findById(orderId);
}
```

The third parameter `true` of `set_config` scopes the setting to the current transaction only. The statement must execute on the same physical connection and before any protected query runs. In Spring transactions, use the same EntityManager/transaction-bound connection; never set session-level settings and return an unreset connection to the pool.

RLS is a PostgreSQL feature, not a portable solution across all DBMSs. Note:

- The application database role must not be a superuser, have `BYPASSRLS`, or own tables in a way that skips policies. `FORCE ROW LEVEL SECURITY` subjects table owners to policies, though superusers/`BYPASSRLS` can still bypass them.
- When `app.tenant_id` is unset, comparisons against `NULL` match no rows; this is the desired fail-closed behavior.
- Test `SELECT`, `INSERT`, `UPDATE`, `DELETE`, bulk SQL, and connection reuse.
- If there are non-tenant tables or cross-tenant admin jobs, design separate audited roles/policies; never relax policies for the entire application.

RLS complements authorization and query scoping. It does not replace user authentication, membership checks, and least-privilege application roles.

## 9. Testing against cross-tenant data leaks

Do not only test that tenant A can read its own data. Test that A cannot read, modify, delete, or infer the existence of B's data.

The test suite should cover:

| Scenario | Expected Outcome |
|---|---|
| Tenant A creates an order | Row is stamped with tenant A from server context |
| Tenant B creates the same `external_id` | Allowed if unique key is scoped per tenant |
| Tenant A reads an ID belonging to B | Returns no B data; API responds as not found/forbidden per policy |
| Tenant A updates or deletes an ID belonging to B | Zero rows of B are modified |
| Missing tenant context | Request/job is rejected before accessing tenant datasource |
| Tenant header outside user membership | 403 or corresponding authorization error |
| Tenant key has no datasource | Routing fails closed, never falls back to a default datasource |
| Exception mid-request | Context is cleared; next request on the same thread sees no stale tenant |
| `@Async`/message consumer | Task runs with the captured/verified tenant |
| Caching same ID across two tenants | Both tenants get distinct cache entries |
| Native/bulk queries | Tenant predicates or RLS still apply |
| RLS context not set | Database returns zero tenant rows |
| Reused connection | No leftover schema/tenant setting from previous request |

Testcontainers with the target DBMS can verify routing, schemas, RLS, constraints, and transactions. With database-per-tenant, test two separate databases; with schema-per-tenant, create two schemas; with shared schema, insert tenant A/B rows into the same table. Reuse the same entity ID (if design permits) or the same business key across two tenants to catch cache/query keys missing the tenant.

An important test is verifying context cleanup after exceptions. Use a single-threaded executor to force two tasks sequentially onto the same worker thread; the second task must not observe the first task's tenant.

## 10. Logging, auditing, and operations

Logs should include the verified tenant identifier to aid investigations without logging unnecessary sensitive data. You can place the tenant ID into MDC:

- Set MDC after the tenant context is verified.
- Clear MDC in the same cleanup path as `TenantContext`.
- Never log an unverified header tenant ID as a trusted identity.
- Restrict log access because logs can reveal tenant scale and activity.

Audit logs for sensitive operations should record actor, tenant, action, resource, timestamp, outcome, and correlation ID. For admins performing cross-tenant access, record the authorization/justification per policy. Avoid logging tokens, passwords, PII, or full business payloads unless necessary.

Metrics can be grouped by tenant at small scale, but avoid unbounded-cardinality metric labels across hundreds of thousands of tenants. Instead, use aggregate metrics, sampling, controlled logging/tracing, or targeted per-tenant dashboards during investigations.

## 11. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| First request hits right tenant, next reads wrong one | `ThreadLocal` was not cleared | Use try/finally scopes or interceptor cleanup |
| Async job runs with empty or stale tenant | `ThreadLocal` does not cross thread pools | Use `TaskDecorator` or explicit context propagation |
| Transaction hits wrong database | Tenant context set after transaction began | Set context before calling transactional services |
| Tenant without datasource falls back to default DB | Routing fallback allows default target | Do not set a default tenant; fail closed with `lenientFallback=false` |
| Query returns another tenant's data | Missing tenant predicate or native SQL skips filter | Scope queries, test cross-tenant access, consider RLS |
| Cache returns another tenant's object | Cache key contains only entity ID | Include tenant ID in every cache key |
| Entity created with client-supplied tenant | Trusting `tenantId` in request body | Assign tenant from server-side authenticated context |
| Child record references another tenant's parent | Foreign key checks only entity ID | Use composite constraints including `tenant_id` |
| RLS has no effect | App role is owner/superuser/`BYPASSRLS` or wrong connection setting | Check roles, `FORCE RLS`, and transaction-local settings |
| Tenant migrations drift out of sync | Schema updated for only some tenants | Track migration versions and roll out in controlled stages |

## 12. Secure design checklist

- [ ] Distinguish user, customer, and tenant in the domain.
- [ ] Resolve tenant from authenticated principal and membership, never blindly trusting headers/bodies.
- [ ] Reject requests lacking tenant context; never fall back to a default tenant.
- [ ] Open/close tenant context in explicit scopes and always clean up.
- [ ] Propagate context explicitly across async/job/message boundaries.
- [ ] Set tenant context before a transaction begins.
- [ ] Never switch tenants mid-transaction or within one persistence context.
- [ ] Ensure every query, native SQL, bulk operation, and cache enforces tenant isolation.
- [ ] Scope unique keys, foreign keys, audits, outbox, and file/object storage by tenant appropriately.
- [ ] Routing/schema switching resets connections before returning them to the pool.
- [ ] Consider database RLS as an extra defense layer for sensitive data.
- [ ] Tests prove tenant A cannot read/modify/delete tenant B's data.
- [ ] Tests cover missing context, exception cleanup, async propagation, and cache isolation.

## 13. Key takeaways

- Tenant context is the result of authentication and authorization; a client-supplied tenant ID is only a selection to verify.
- Database-per-tenant, schema-per-tenant, and shared schema require different routing and protection strategies.
- `ThreadLocal` requires cleanup and does not cross executors automatically; use scopes and `TaskDecorator`.
- Set tenant context before `@Transactional` opens a transaction; never switch tenants mid-transaction.
- Shared schema requires tenant predicates on every query and tenant-aware caches/constraints.
- Never configure a default tenant fallback; missing context must fail closed.
- RLS adds defense at the database layer, provided the application role cannot bypass policies.
- Test cross-tenant isolation across reads, writes, deletes, caches, async tasks, and connection reuse.

## 14. References

- [Spring Framework — AbstractRoutingDataSource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/lookup/AbstractRoutingDataSource.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Hibernate ORM — Multi-tenancy](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)