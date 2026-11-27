# Multi-Tenancy Models by Database, Schema, or tenant_id

**Module:** Spring Data JPA  
**Knowledge Group:** Multiple Data Sources

## 1. Objectives

After this lesson, you will be able to:

- Explain the multi-tenancy model and data boundaries between tenants.
- Compare three organization patterns: separate database, separate schema, and shared schema with `tenant_id`.
- Choose the right model based on isolation level, operational cost, tenant scale, and growth needs.
- Design how to determine the tenant from an authenticated identity and pass tenant context into the persistence layer.
- Configure datasource or schema routing at the right point in the transaction lifecycle.
- Ensure all queries, relationships, caches, and background tasks preserve proper tenant scope.
- Plan migrations, provisioning, backups, monitoring, and cross-tenant data leak testing.

## 2. What is multi-tenancy?

Multi-tenancy is an architecture in which a single application serves multiple customers or organizations (tenants) on a shared platform. Each tenant has its own data and is only allowed to access data within its own scope.

For example, a SaaS sales management system serves multiple companies using the same application. Company A has its own users, products, orders, and invoices; Company B also has similar data, but cannot read or modify A's data.

A tenant may be identified by a tenant ID, organization in an account, hostname, or other routing metadata. However, the tenant used to access data must be determined from server-side authenticated identity and permissions. Never trust an arbitrary `tenant_id` sent by the client without verifying that the user has permission to access that tenant.

Core goals of multi-tenancy are:

1. **Data isolation:** one tenant cannot read, modify, or delete another tenant's data.
2. **Operational efficiency:** share application, infrastructure, or schema where appropriate.
3. **Scalability:** onboard new tenants without deploying a completely new system in every case.
4. **Governance:** ability to apply backups, migrations, quotas, monitoring, and policies per tenant.

Multi-tenancy is an architectural and security decision. Merely adding a `tenant_id` column to a few tables is not enough to build a secure multi-tenant system.

## 3. Three common storage models

There are three common ways to organize data:

- **Database per tenant:** each tenant has its own database.
- **Schema per tenant:** each tenant has its own schema inside the same database instance.
- **Shared schema:** multiple tenants share the same tables; each row carries a `tenant_id`.

| Criterion | Separate Database | Separate Schema | Shared Schema + tenant_id |
|---|---|---|---|
| Data boundary | Database | Schema | Data row |
| Physical/logical isolation | High | Medium to high | Depends on queries and constraints |
| Resource cost | Higher | Medium | Typically lower |
| Connection routing | By database | By schema | No database/schema switching needed |
| Migration | Per database | Per schema | One shared schema |
| Per-tenant backup/restore | Convenient | Possible per schema, DB-dependent | Harder, requires filtering data |
| Cross-tenant aggregate queries | Harder | Harder | Easier, but requires strict authorization |
| Risk of missing tenant predicate | Lower at query level | Lower if schema routing is right | Very significant |

No single model is best for all products. Decisions should be based on isolation requirements, tenant count, tenant size, operational cost, recoverability, and cross-tenant querying needs.

## 4. Database per tenant

Each tenant has a separate database, which may reside on the same database server or across different database clusters.

For example:

- tenant A → database `tenant_a`
- tenant B → database `tenant_b`
- tenant C → database `tenant_c`

The application determines the current tenant and then routes connections to the corresponding datasource.

### 4.1. Advantages

- Clear data boundaries at the database level.
- Can assign separate database privileges and limit blast radius when one tenant experiences issues.
- Per-tenant backup, restore, server migration, or upgrades are easier to organize.
- Large tenants can be moved to stronger database clusters without migrating all customers.
- Different configurations, quotas, or maintenance windows can be applied per tenant.

### 4.2. Disadvantages

- Must manage many databases and connection credentials.
- Separate connection pools per datasource can consume significant connections and memory.
- Migrations, backups, monitoring, and provisioning must run across many databases.
- Aggregate queries across all tenants are more complex.
- Onboarding new tenants requires automation to avoid manual configuration drift.

When tenant counts grow into the thousands, do not default to creating a large pool for every single tenant. Consider shared routed pools, bounded pools per tenant group, or on-demand connection allocation governed by operational policies.

### 4.3. Datasource routing in Spring

Spring provides `AbstractRoutingDataSource` to select a datasource based on a lookup key. The example below illustrates the routing mechanism:

~~~java
public final class TenantContext {

    private static final ThreadLocal<String> CURRENT =
            new ThreadLocal<>();

    private TenantContext() {
    }

    public static void setTenantId(String tenantId) {
        CURRENT.set(tenantId);
    }

    public static String getTenantId() {
        return CURRENT.get();
    }

    public static void clear() {
        CURRENT.remove();
    }
}
~~~

Routing datasource:

~~~java
public class TenantRoutingDataSource
        extends AbstractRoutingDataSource {

    @Override
    protected Object determineCurrentLookupKey() {
        String tenantId = TenantContext.getTenantId();

        if (tenantId == null) {
            throw new IllegalStateException(
                    "Tenant context has not been set");
        }

        return tenantId;
    }
}
~~~

During configuration, the application registers a map of verified tenant IDs to their corresponding datasources. For example:

~~~java
Map<Object, Object> targets = new HashMap<>();
targets.put("tenant-a", dataSourceA);
targets.put("tenant-b", dataSourceB);

routingDataSource.setTargetDataSources(targets);
routingDataSource.setDefaultTargetDataSource(defaultDataSource);
routingDataSource.afterPropertiesSet();
~~~

These are configuration snippets; in real applications, datasources, transaction managers, and EntityManagerFactories must be built with consistent settings. Never use an unverified tenant ID as an arbitrary datasource name or connection detail. If a tenant is not in the registry, reject the request rather than falling back to a default database containing another tenant's data.

### 4.4. Tenant context must exist before connection acquisition

A routing datasource chooses the database when acquiring a connection. Therefore, the tenant context must be set before the transaction begins and before the EntityManager acquires a connection.

If a transaction has already acquired a connection for tenant A, changing the ThreadLocal to tenant B mid-transaction will not switch the connection to database B. Never change tenants inside an active transaction.

In web requests, tenant context is typically set in a filter/interceptor after authentication and membership checks. Afterward, the Service runs its transaction. At the end of the request, clear the context in `finally`:

~~~java
try {
    TenantContext.setTenantId(authorizedTenantId);
    filterChain.doFilter(request, response);
} finally {
    TenantContext.clear();
}
~~~

This snippet belongs inside a filter; `authorizedTenantId` must come from authentication and authorization checks, never directly from an untrusted header.

For async tasks, executors, or message consumers, ThreadLocal does not propagate automatically to other threads. Pass the tenant ID inside verified message/job context, set the context at the start of the task, and clear it in `finally`. Never let a thread pool reuse a thread with leftover tenant context.

## 5. Schema per tenant

Each tenant uses a separate schema within the same database instance. For example:

- tenant A → schema `tenant_a`
- tenant B → schema `tenant_b`

Schemas can share identical table names like `customer`, `product`, and `orders`, while data lives in isolated namespaces.

### 5.1. Advantages and disadvantages

Advantages:

- Clearer data isolation at the schema level compared to shared schema.
- Shares a single database instance and can share connection pool infrastructure.
- Can back up/restore or grant permissions per schema depending on database capabilities.
- Can migrate per tenant or by tenant batches.

Disadvantages:

- Still must manage a large number of schemas.
- Each schema must be created, upgraded, and checked for consistency.
- Incorrect schema routing can cause the application to read the wrong data.
- Some databases impose limits or notable overhead on managing many schemas.
- Cross-schema queries and per-schema backups depend on the database.

### 5.2. Switching schema per connection

Schemas can be configured on the connection upon acquisition, for example via `Connection.setSchema(schemaName)` if supported by the driver/database. Some DBMSs have dedicated mechanisms like `search_path`.

Ensure the schema name comes from a trusted tenant registry mapped from an authenticated tenant ID. Never concatenate a raw client header into SQL such as `SET search_path TO <client value>`.

Connection pools reuse connections. Therefore, a schema set for one request must be reset to a safe state when the connection returns to the pool or reliably re-applied each time a connection is borrowed. If tenant A's connection is reused for tenant B with the old schema lingering, wrong data can be accessed.

Test connection acquisition, connection return, transaction rollback, and connection reuse in the pool.

### 5.3. Hibernate multi-tenancy

Hibernate has multi-tenancy mechanisms to identify tenants and supply matching connections. Depending on the Hibernate version, common components include:

- `CurrentTenantIdentifierResolver`: determines the current tenant for a Session.
- `MultiTenantConnectionProvider`: supplies and releases connections appropriate for the tenant.
- Multi-tenancy configuration and strategy matching database or schema mode.

API names and configuration vary across Hibernate versions. Consult documentation for the exact version managed by your Spring Boot release; do not copy Hibernate 5 configs to Hibernate 6 or vice versa without verifying.

When using Hibernate native multi-tenancy, the tenant identifier must be set before opening a Session/EntityManager. A regular transaction/session works with only one tenant. Accessing multiple tenants within one business workflow requires dedicated design rather than arbitrarily switching tenants between repository calls.

## 6. Shared schema with tenant_id

All tenants share the same tables. Which tenant owns a record is determined by a `tenant_id` column.

Example:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    CONSTRAINT uq_customer_tenant_code
        UNIQUE (tenant_id, name)
);
~~~

Data might look like:

| id | tenant_id | name |
|---:|---|---|
| 1 | tenant-a | An Company |
| 2 | tenant-b | Binh Company |
| 3 | tenant-a | Hanoi Branch |

IDs can be globally unique across the table, but business uniqueness rules usually must include `tenant_id`. For instance, two tenants might both use customer code `KH001`, so the unique constraint should be `(tenant_id, customer_code)` rather than `customer_code` alone.

### 6.1. Entity mapping

~~~java
@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_customer_tenant_code",
        columnNames = {"tenant_id", "customer_code"}
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private String tenantId;

    @Column(name = "customer_code", nullable = false)
    private String customerCode;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }
}
~~~

`tenantId` must be assigned from the server-side authenticated tenant context. Never let clients dictate `tenantId` during creation or updates. The `updatable = false` attribute prevents Hibernate from including the column in normal UPDATE statements after creation, though it is not a complete security barrier on its own. Setters, services, queries, and database constraints must all be controlled.

### 6.2. Repositories must restrict by tenant

A clear approach is including the tenant ID in method names or query predicates:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByTenantIdAndId(
            String tenantId,
            Long id);

    List<Customer> findAllByTenantId(
            String tenantId);
}
~~~

The service obtains the tenant from server-side context:

~~~java
@Transactional(readOnly = true)
public Customer getCustomer(Long id) {
    String tenantId = TenantContext.getTenantId();

    return customerRepository
            .findByTenantIdAndId(tenantId, id)
            .orElseThrow(() ->
                    new EntityNotFoundException("Customer not found"));
}
~~~

Do not call `findById(id)` for tenant-scoped data and rely only on UI-level permission checks. A client could swap IDs in the URL and access another tenant's records if the Service does not constrain the query.

Every operation must enforce tenant scope:

- `findById`, `findAll`, `existsById`, and `count`.
- `update`/`delete` by ID.
- JPQL, native SQL, Specifications, and Querydsl.
- Joins to other tenant-scoped entities.
- Bulk updates/deletes and batch jobs.
- Exports, reports, and paginated queries.

### 6.3. Foreign keys must also protect tenant boundaries

Filtering only parent tables by tenant is insufficient if a child row can reference a parent row belonging to another tenant.

For example, `OrderLine` has `order_id` and `tenant_id`. You can define a composite unique key on the `orders` table:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT uq_orders_tenant_id
UNIQUE (tenant_id, id);
~~~

Then use a composite foreign key:

~~~sql
ALTER TABLE order_line
ADD CONSTRAINT fk_order_line_tenant_order
FOREIGN KEY (tenant_id, order_id)
REFERENCES orders (tenant_id, id);
~~~

Thus, the database itself prevents an OrderLine of tenant A from referencing an Order of tenant B, even if application code has a bug. Adjust syntax and column types for your specific database.

### 6.4. Indexes should account for tenant_id

Tenant-scoped queries often take the form:

~~~sql
SELECT id, customer_code, name
FROM customer
WHERE tenant_id = ?
  AND customer_code = ?;
~~~

A composite index `(tenant_id, customer_code)` often fits this query pattern well. For large tables, column ordering in an index should depend on filter predicates, selectivity, sorting, and actual workload. Do not blindly prepend `tenant_id` to every index; inspect execution plans and benchmark.

## 7. Using Hibernate's discriminator feature

Hibernate supports discriminator-based multi-tenancy in certain versions, where entities can be marked with a tenant identifier via Hibernate's own `@TenantId` annotation.

This is a Hibernate feature, not a standard Jakarta Persistence annotation. How it is enabled, how tenant identifiers are resolved, and how it applies to queries depend on the Hibernate version and SessionFactory configuration. If used, verify:

- Tenant identifiers are resolved from an authenticated context.
- Every tenant-scoped entity is properly mapped.
- Native SQL, bulk queries, and special access paths maintain isolation.
- Migrations and unique/foreign key constraints still protect tenants.
- Caches and queries are tenant-aware.
- Intentional cross-tenant access tests are all blocked.

For projects not using Hibernate discriminators, repository methods with explicit tenant predicates are easy to read and audit. Even when using automatic mechanisms, never treat an annotation as an excuse to skip security reviews of native queries, background jobs, or non-ORM access paths.

## 8. Safely determining the tenant from a request

A request may contain a hostname, path, or header indicating a tenant. These values are merely hints to locate a tenant, not proof that the user is authorized to access that tenant.

A secure flow typically looks like:

1. Authenticate the user or service principal.
2. Determine the requested tenant from domain, route, or valid selection.
3. Verify the principal holds membership/permission in that tenant.
4. Bind the normalized tenant ID into the request context.
5. Service and persistence layers use only the tenant ID from the trusted context.
6. Clear the context after the request finishes.

If a user has access to multiple tenants, switching or selecting the active tenant must be validated against their membership list. Never allow clients to pass an arbitrary `tenant_id` and query directly.

Also avoid leaking the existence of another tenant's data through error messages. For out-of-scope resources, many APIs return 404 rather than distinguishing between nonexistent records and records belonging to another tenant. The response policy must be consistent.

## 9. Transactions and multiple tenants

A normal JPA transaction should operate on a single tenant. The tenant context must stay stable from the moment the transaction acquires a connection until the transaction completes.

Do not do the following within the same transaction:

- Start a transaction under tenant A and switch context to tenant B.
- Call a Repository of another tenant while still using tenant A's EntityManager/connection.
- Let an async task accidentally inherit the caller thread's tenant context.
- Use a local transaction manager and assume it commits atomically across multiple independent databases.

If a business operation must affect multiple tenants or multiple databases, design a dedicated workflow. Options include sequential coordination of separate transactions, outbox, saga, and compensating actions. JTA/XA is only appropriate when the infrastructure and databases support it and the operational overhead of distributed transactions is acceptable.

Avoid holding locks across multiple tenants for long durations inside a single transaction.

## 10. Caching in multi-tenant systems

Caches are a common source of data leaks if cache keys omit the tenant.

Example of a dangerous key:

~~~java
@Cacheable(cacheNames = "customer", key = "#id")
public CustomerDto getCustomer(Long id) {
    // ...
}
~~~

If tenant A and tenant B both have ID 10 in their own scopes, a cache key of just `10` can serve one tenant's data to the other.

Keys must include the tenant identifier:

~~~java
@Cacheable(
    cacheNames = "customer",
    key = "T(com.example.TenantContext).getTenantId() + ':' + #id"
)
public CustomerDto getCustomer(Long id) {
    // ...
}
~~~

The expression syntax must match your project's package and Spring Cache configuration. A custom `KeyGenerator` can be used to normalize and validate tenant IDs.

Review:

- Do Spring Cache keys include the tenant ID?
- Are cache regions separated per tenant, or shared with properly namespaced keys?
- Does eviction on update/delete target the right tenant and right key?
- Do Hibernate second-level/query caches behave tenant-aware under your configuration?
- Are global data and tenant-scoped data clearly separated?
- Do distributed caches avoid key collisions across applications or environments?

Never cache objects containing tenant data unless you can prove that keys and invalidation maintain proper boundaries.

## 11. Tenant migrations and provisioning

### 11.1. Shared schema

Shared schema usually has a single migration applied to the shared tables. When adding `tenant_id` to an existing populated table, do not immediately add a `NOT NULL` column if existing rows lack values.

A multi-step process might be:

1. Add nullable `tenant_id`.
2. Backfill `tenant_id` for each row based on verified data sources.
3. Verify no rows remain missing or assigned to the wrong tenant.
4. Create indexes and unique constraints including `tenant_id`.
5. Switch the application to tenant-scoped queries.
6. Add `NOT NULL` and composite constraints once the data is valid.

If legacy data lacks tenant ownership information, resolve the business mapping before backfilling. Never assign all records to a default tenant just to make a migration pass.

### 11.2. Database per tenant and schema per tenant

Migrations must be applied to every database or schema. A tenant registry should track schema version, provisioning status, target database/schema, and last migration timestamp.

When onboarding a new tenant, the workflow might:

1. Create the database or schema from a controlled template.
2. Grant permissions and provision connection details.
3. Run all migrations in order.
4. Verify schema version and run health checks.
5. Register the tenant in the registry.
6. Allow the tenant to receive traffic once provisioning succeeds.

Never mark a tenant active before its database/schema is ready.

### 11.3. Rolling deployments

When multiple application versions run simultaneously, migrations should stay backward-compatible with the older version during rollout. Use expand-and-contract:

- Expand: add new columns/tables such that the old version still works.
- Migrate data: backfill or sync data.
- Switch: deploy code reading/writing the new structure.
- Contract: remove the old structure in a later release once no instances depend on it.

With many tenants, maintain visibility into which tenants migrated successfully, which are pending, and how to retry safely.

## 12. Backup, restore, and operations

Storage models directly impact data recovery:

- Database per tenant: simpler per-tenant backup/restore, but requires managing many backups.
- Schema per tenant: can back up/restore per schema if supported by the database and tested.
- Shared schema: restoring a single tenant is harder because multiple tenants share tables; may require export/import filtered by tenant ID or restoring to a staging environment and extracting data.

Beyond backups, monitor:

- Active tenant count and provisioning states.
- Database/schema version per tenant.
- Connection pool usage per tenant or tenant group.
- Slow queries, locks, deadlocks, and connection errors.
- Data volume and growth rate per tenant.
- Cache hit/miss and eviction rates per namespace.
- Authorization error rates and invalid tenant access attempts.

With database per tenant, prevent one heavy-traffic tenant from exhausting the entire connection pool or database resources. Set quotas, concurrency limits, and isolate large tenants on dedicated infrastructure.

## 13. Testing isolation between tenants

Multi-tenancy tests must prove tenant A cannot access tenant B's data, even when knowing record IDs.

An integration test suite should include at least two tenants with overlapping IDs or business keys. Verify:

1. Tenant A can read A's records.
2. Tenant B can read B's records.
3. Tenant A cannot read B's IDs.
4. Tenant A cannot update or delete B's records.
5. Lists, counts, and pagination never mix data.
6. Joins, native queries, and bulk updates do not bypass tenant scope.
7. Caches never return cross-tenant results.
8. Tenant context is cleared after requests and never leaks through thread pools.
9. Transaction rollbacks leave no data in another tenant.
10. Migrations and provisioning build the right structure for new tenants.

For shared schema, add composite constraint tests proving the database rejects cross-tenant relationships. If using PostgreSQL Row-Level Security (RLS), test policies using the exact database role the application uses; table owners or roles with bypass privileges may not be subject to the same policies as normal runtime users.

Testcontainers helps run production-like databases to test migrations, foreign keys, schema routing, and RLS. H2 can be useful for quick unit-style tests, but cannot replace real database testing when relying on database-specific features.

## 14. Comparison and choosing a model

### Choose database per tenant when

- Customers require strong isolation or have specific contractual/regulatory requirements.
- Tenants are large and need independent scaling, backups, or restores.
- Tenant count is manageable for operating databases and connections efficiently.
- Provisioning and migrations can be automated.

### Choose schema per tenant when

- You want separate data namespaces while sharing a single database instance.
- The database supports schema isolation and stable schema routing.
- Tenant count is moderate or bulk schema management tooling is already in place.
- Schema state on connection pools can be reliably controlled.

### Choose shared schema + tenant_id when

- There are very many tenants and each tenant's dataset is relatively small.
- You want to share tables, indexes, and infrastructure.
- Cross-tenant queries, reporting, and operations need to be convenient.
- Mandatory tenant scoping can be enforced at the application layer and reinforced with constraints/RLS.

Hybrid models are possible: small tenants share a schema while large or high-isolation tenants get dedicated databases. Hybrid setups increase flexibility at the cost of more complex routing, migrations, observability, and operational support. Choose them only with clear business justification and operational readiness.

## 15. Common mistakes

### 15.1. Trusting tenant_id from the client

Clients can modify headers, paths, or request bodies to probe other tenants. Tenants must be verified via server-side identity and membership.

### 15.2. Forgetting the tenant predicate in a query

A repository method, native SQL, count query, or background job might accidentally return all tenants' data. Audit all data access paths, not only primary endpoints.

### 15.3. Using ID as cache key without tenant

IDs can collide across tenants or cache namespaces may be shared. Always include the tenant in the key or separate cache regions/namespaces per tenant.

### 15.4. Switching tenants inside an open transaction

The connection may already be bound to the previous tenant. A transaction must keep a stable tenant; never switch context mid-flight to access another tenant.

### 15.5. Failing to reset schema on pooled connections

Reused connections may retain the previous schema/`search_path`. Safely set and reset connection state on every borrow/return.

### 15.6. Checking only at the Service layer

Native SQL, batch jobs, or background tasks might bypass a guarded service method. Consider composite constraints, database permissions, or RLS as defense in depth.

### 15.7. Out-of-sync migrations across tenants

Some tenants are on a new schema while others remain un-upgraded. Track migration versions and statuses per tenant with retries and alerts.

### 15.8. Assuming cascades or JPA mappings guarantee isolation

JPA mappings describe object-relational relationships, not tenant access rights. Tenant scope must be enforced across queries, services, database constraints, and caches.

## 16. Multi-tenancy implementation checklist

- [ ] Chosen database, schema, or `tenant_id` model based on isolation and operational needs.
- [ ] Tenant is resolved from authenticated identity and valid membership.
- [ ] Tenant context is set before opening a transaction/connection.
- [ ] One transaction/session operates on only one determined tenant.
- [ ] ThreadLocal or async context is properly propagated and cleared.
- [ ] Repositories, native queries, counts, pagination, and batch jobs are all tenant-scoped.
- [ ] Unique constraints and foreign keys include `tenant_id` where needed.
- [ ] Cache keys, eviction, and Hibernate caches maintain proper tenant boundaries.
- [ ] Migrations/provisioning track versions per database or schema.
- [ ] Backup/restore is tested according to the data model.
- [ ] Cross-tenant access tests using known IDs are in place.
- [ ] Load, connections, storage, and migration status are monitored per tenant.

## 17. Conclusion

Database per tenant establishes clear database boundaries and supports per-customer operations at higher management cost. Schema per tenant partitions namespaces within one database instance and requires safe schema routing on connections. Shared schema with `tenant_id` conserves resources and scales smoothly to many tenants, but demands that every query, foreign key, cache, and background task preserve tenant scope. Regardless of the model chosen, tenants must be authenticated server-side, tenant context must remain stable within transactions, and isolation must be verified via integration tests alongside database-level safeguards.