# Tenant Isolation Across Identity, Data, and Resource Layers

A serverless application often serves multiple organizations or customers on a shared system. Each organization is called a **tenant**. Tenants may share APIs, functions, databases, queues, and object storage, yet one tenant's data and operations must be isolated from another's.

Tenant isolation is more than adding a `tenant_id` column to a table. The system must resolve the right tenant from an authenticated identity, enforce permissions per resource, preserve tenant context across requests and messages, and apply appropriate boundaries across databases, object storage, caches, queues, secrets, and network infrastructure. A small flaw at any layer can lead to cross-tenant data access.

In Java serverless, execution environments are reused and can process multiple requests or messages depending on platform configuration. Therefore, tenant context must be bound to each individual invocation and task. Static fields, threads, or connection pools must never leak tenant state across executions.

This lesson explains how to design multi-layer tenant isolation, from identity and authorization down to data, resources, operations, and testing.

## 1. Tenants and Isolation Boundaries

A tenant is the unit of data ownership and access control in a multi-tenant application. Depending on the product, a tenant may be a company, organization, workspace, enterprise customer, or personal account.

A user may:

- Belong to only one tenant.
- Belong to multiple tenants with different roles.
- Be an administrator of tenant A while being only a member of tenant B.
- Receive temporary access to another tenant through a support workflow.

Consequently, a tenant cannot be inferred solely from a user ID or email. The system needs an explicit membership relationship between principals and tenants.

### Boundaries to Protect

| Layer | Isolation Question |
|---|---|
| Identity | Who is calling and which tenant do they belong to? |
| Authorization | Does the principal have permission to perform this action on the tenant's resource? |
| Application context | Which tenant is being processed in the current invocation? |
| Database | Can queries or transactions read/write another tenant's data? |
| Object storage | Can a tenant download or upload another tenant's objects? |
| Queue/event | Can a message be processed under the wrong tenant context? |
| Cache/search | Can keys or indexes return cross-tenant data? |
| Secrets/keys | Can a workload read another tenant's credentials or keys? |
| Compute/network | Can one tenant exhaust resources or reach internal services? |
| Operations | Do staff, logs, backups, and admin tools respect tenant boundaries? |

Isolation must be designed across all layers. Checking only at the UI or API gateway is insufficient because workers, batch jobs, retries, and internal APIs can reach the same data via other paths.

## 2. Isolation Models: Pool, Bridge, and Silo

Three models are commonly used. Real-world systems often combine them per data type or tenant tier.

| Model | Organization | Pros | Trade-offs |
|---|---|---|---|
| Pool | Multiple tenants share databases/schemas/tables and resources | Low cost, centralized operations, easy aggregate scaling | Requires very strict `tenant_id` and policy enforcement |
| Bridge | Subsets of tenants share dedicated resource groups, split by shard or cell | Balances cost and isolation | Requires managing tenant-to-cell mapping and tenant migration |
| Silo | Each tenant or tenant group has dedicated databases, buckets, accounts/projects, or stacks | Strong boundaries, easy per-tenant quota and key customization | High cost and operational complexity |

### Pool

Pool fits when the number of tenants is large, per-tenant size is moderate, and the application has a relatively uniform schema. Shared tables require the tenant key in every query and data constraint.

### Bridge

Bridge partitions tenants into cells or shards. Each cell has its own database, queues, or compute for a subset of tenants. When one cell experiences an incident or overload, the blast radius is more contained than a system-wide pool.

A registry mapping tenants to cells is required, and every service must read from the same mapping source. Moving a tenant between cells requires a controlled migration and cutover process.

### Silo

Silo suits tenants requiring separate compliance, encryption keys, backups, networking, or quotas. Silo is not automatically secure if IAM permissions or operational workflows remain overly shared. Application-layer authorization and auditing are still mandatory.

There is no single best model. The decision depends on data sensitivity, regulatory requirements, tenant scale, cost, operability, and customization needs.

## 3. Resolving the Tenant from an Authenticated Identity

A secure flow starts by authenticating the principal. The backend must verify signatures, issuer, audience, expiration, and token conditions per the identity provider. Next, the application resolves tenant membership from a trusted data source.

A typical flow:

1. The HTTP function receives a bearer token or identity token.
2. Middleware or the platform validates the token per contract.
3. The application extracts the principal ID from verified claims, typically the issuer and subject pair.
4. The membership service checks whether the principal belongs to the requested tenant and whether the membership is active.
5. The authorization service determines roles and permissions within that tenant.
6. The application constructs an immutable tenant context for the request.
7. All data and resource accesses use this context.

~~~mermaid
sequenceDiagram
    participant U as User/Client
    participant F as Java Function
    participant I as Identity Provider
    participant M as Membership/Authorization
    participant D as Tenant Data

    U->>F: Request + access token
    F->>I: Verify token / claims
    I-->>F: Verified issuer, subject, audience
    F->>M: Check membership and permissions
    M-->>F: Tenant and role context
    F->>F: Build immutable TenantContext
    F->>D: Query with tenant boundary
    D-->>F: Tenant-scoped result
    F-->>U: Response
~~~

Never grab a tenant ID from a header such as `X-Tenant-Id` and trust it outright. Headers, query parameters, path parameters, and message bodies are all caller-controlled. They can serve only as a **tenant selector** after the backend verifies the principal has access to that tenant.

### User Identity Differs from Workload Identity

In serverless, there are at least two types of identities:

- **User/client identity:** the person or application requesting a business operation.
- **Workload identity:** the service account, execution role, or managed identity the function uses to call cloud services.

Workload identity lets the function access databases, secrets, queues, or object storage. It does not prove the end user is authorized to read a record. If the function holds permissions to read data across all tenants, the code must enforce accurate tenant authorization per request.

Never use a broadly scoped service account as an excuse to skip user and tenant checks at the application layer.

## 4. Tenant Selectors and Authorization

An API might let users select a workspace via URL:

~~~http
GET /tenants/tenant-42/orders/order-918
Authorization: Bearer <access-token>
~~~

The backend must verify:

- The token is valid and issued for this API.
- The principal holds an active membership in `tenant-42`.
- The principal has permission to read orders.
- Order `order-918` actually belongs to `tenant-42`.
- The tenant is not suspended or locked by policy.

It is not enough to check that the user belongs to `tenant-42` and then query the order by order ID without a tenant predicate. If IDs are guessable or leaked, an attacker can access another tenant's resources.

Authorization should bind to resources and actions, not just routes. For example, an `orders:read` permission does not automatically allow reading all orders if data also has owner, region, or project boundaries.

### Preventing IDOR and Cross-Tenant Access

Insecure Direct Object Reference (IDOR) occurs when an API accepts an object ID without checking access rights. In multi-tenant systems, this commonly becomes a cross-tenant flaw.

Dangerous query example:

~~~sql
SELECT * FROM orders WHERE order_id = ?;
~~~

Query with tenant boundary:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = ?
  AND order_id = ?;
~~~

Obtain the tenant ID from the verified context, never from an unchecked caller-supplied field. For updates/deletes, the tenant predicate must appear in the mutating statement itself, not merely in an earlier read step.

## 5. TenantContext in Java Serverless

After authentication and membership verification, create an immutable object holding the data needed for the request:

~~~java
import java.util.Set;

public record TenantContext(
        String tenantId,
        String issuer,
        String subject,
        Set<String> permissions,
        String correlationId) {

    public TenantContext {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("principal is required");
        }
        permissions = Set.copyOf(permissions);
    }

    public void require(String permission) {
        if (!permissions.contains(permission)) {
            throw new SecurityException("Permission denied");
        }
    }
}
~~~

Pass the context explicitly through layers:

~~~java
public OrderView getOrder(
        TenantContext tenant,
        String orderId) {

    tenant.require("orders:read");

    return orderRepository.findByTenantAndId(
            tenant.tenantId(),
            orderId);
}
~~~

Explicit parameter passing makes code easier to review and test. Services do not have to read a global variable that could be mutated by another request.

### Why Should Tenant State Never Be Stored in Static Fields?

A function instance can be reused across multiple invocations. If a handler sets:

~~~java
static String currentTenantId;
~~~

then tenant B's request can overwrite the value while tenant A's request is still running, especially when the runtime supports concurrency or the application uses threads/async tasks. Even with sequential invocations, stale values can be reused by mistake if a code path forgets to update them.

Never use mutable static fields to store tenant, user, authorization results, or request-specific state.

### Be Cautious with ThreadLocal

`ThreadLocal` is sometimes used by frameworks to propagate security context. In a thread pool, threads are reused. Failing to clear context in a `finally` block allows the next request to see the previous tenant's data.

With async/reactive execution, `ThreadLocal` also does not automatically propagate context across threads. Prefer passing `TenantContext` explicitly or using framework-supported context propagation, verifying cleanup on every exit path.

## 6. Tenant Isolation in Shared Databases

In the pool model, multiple tenants share tables. Every table holding tenant data needs a tenant key, and every query must scope by that key.

Schema example:

~~~sql
CREATE TABLE orders (
    tenant_id  VARCHAR(64) NOT NULL,
    order_id   VARCHAR(64) NOT NULL,
    status     VARCHAR(32) NOT NULL,
    total      DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE INDEX idx_orders_tenant_created
    ON orders (tenant_id, created_at);
~~~

A composite primary key scopes order identity within a tenant. Leading indexes with `tenant_id` also support tenant-scoped queries and can improve performance.

Query pattern:

~~~sql
SELECT order_id, status, total, created_at
FROM orders
WHERE tenant_id = ?
  AND order_id = ?;
~~~

For foreign keys, include the tenant key in the relationship to prevent cross-tenant references:

~~~sql
CREATE TABLE order_items (
    tenant_id VARCHAR(64) NOT NULL,
    order_id  VARCHAR(64) NOT NULL,
    item_id   VARCHAR(64) NOT NULL,
    sku       VARCHAR(100) NOT NULL,
    quantity  INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, item_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders (tenant_id, order_id)
);
~~~

Database constraints prevent an order item belonging to tenant A from referencing an order belonging to tenant B due to a code bug.

### Repositories Must Require Tenant Identity

A useful pattern is requiring the tenant ID in repository signatures:

~~~java
public interface OrderRepository {
    OrderView findByTenantAndId(String tenantId, String orderId);

    int updateStatus(
            String tenantId,
            String orderId,
            String newStatus);
}
~~~

Avoid repository APIs accepting only `orderId` when data belongs to a tenant. When writing updates/deletes, include the tenant in the predicate:

~~~sql
UPDATE orders
SET status = ?
WHERE tenant_id = ?
  AND order_id = ?;
~~~

Check the affected row count to distinguish missing resources from invalid state transitions per contract. Do not reveal the existence of another tenant's resources through differing error messages if doing so creates a side channel.

## 7. Row-Level Security in PostgreSQL

Row-Level Security (RLS) provides an additional protective layer in the database. PostgreSQL can apply policies restricting which rows a database role is allowed to read or write.

Example:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_orders
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

The application sets the tenant context inside the transaction before querying:

~~~sql
SELECT set_config('app.tenant_id', 'tenant-42', true);
~~~

The third parameter `true` scopes the setting to the current transaction only. When the transaction ends, the value resets. This is critical when connections return to a pool and are reused for another tenant.

Java JDBC example:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public List<Order> findOrders(
        DataSource dataSource,
        TenantContext tenant) throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement setTenant =
                    connection.prepareStatement(
                            "select set_config('app.tenant_id', ?, true)")) {
                setTenant.setString(1, tenant.tenantId());
                setTenant.execute();
            }

            List<Order> result = new ArrayList<>();

            try (PreparedStatement query =
                    connection.prepareStatement(
                            "select order_id, status, total "
                            + "from orders order by created_at desc")) {
                try (ResultSet rs = query.executeQuery()) {
                    while (rs.next()) {
                        result.add(new Order(
                                rs.getString("order_id"),
                                rs.getString("status"),
                                rs.getBigDecimal("total")));
                    }
                }
            }

            connection.commit();
            return result;
        } catch (SQLException | RuntimeException ex) {
            connection.rollback();
            throw ex;
        }
    }
}
~~~

This snippet assumes the domain class `Order` already exists in the application. The key point is setting the tenant context and executing the query inside the same transaction; every failure path rolls back and closes the connection via try-with-resources.

In the example, the query does not need to repeat the tenant predicate because RLS enforces the policy in the database. However, many systems keep the tenant predicate in queries as well so code makes scoping explicit and assists indexing. RLS is defense-in-depth, not a reason to skip authorization checks.

Important considerations:

- The application's database role must not be the table owner or a role permitted to bypass RLS.
- `FORCE ROW LEVEL SECURITY` applies the policy even to the table owner where applicable; superusers and roles with `BYPASSRLS` can still bypass it.
- If `app.tenant_id` is unset, the policy must deny rather than widen access.
- Tenant context must be set in the same transaction as the query.
- Roll back on errors and close connections properly.
- Never use session-level settings that persist after returning connections to the pool.
- Test using the exact database role used by the production function.

A custom setting like `app.tenant_id` is application-supplied context, not an independent database identity. If an attacker can execute arbitrary SQL under the application's role, they could attempt to alter this setting. Thus, this form of RLS acts as defense-in-depth against queries missing a tenant predicate; it does not replace parameterized queries, SQL injection prevention, application authorization, and database role least privilege.

## 8. Dedicated Schema or Database per Tenant

For stronger isolation requirements, you can use a dedicated schema or dedicated database per tenant.

### Schema-per-Tenant

Each tenant gets its own schema within the same database. This isolates namespaces and can help manage per-tenant migrations, yet still shares the database instance, high-level privileges, and compute resources. If an application concatenates schema names from input, it can introduce SQL injection or cross-schema access.

Never interpolate identifiers directly from requests. Use a verified tenant registry to map to a system-generated schema name, then validate identifiers against strict fixed rules. Prepared statements cannot bind schema names as regular parameters.

### Database-per-Tenant

Each tenant gets a separate database or cluster. Data isolation is stronger, and credentials, backups, and quotas can be separated. In return, provisioning, migrations, connection pooling, and monitoring become more complex.

With large tenant counts, do not maintain unbounded connection pools for every database inside every execution environment. Use bounded pool caches, idle eviction, and pool shutdown when tenants become inactive.

### Choosing Isolation Level by Risk

| Need | Options to Consider |
|---|---|
| Many small tenants, uniform schema | Shared tables + tenant key + RLS |
| Tenants needing grouped resources | Cell/shard or schema-per-tenant |
| Regulated tenants or contractual separation | Separate database/account/project/bucket |
| Tenants needing dedicated encryption keys | Per-tenant key or dedicated encryption context |
| Very high-volume tenants | Dedicated cell or silo to control noisy neighbors |

## 9. Object Storage and Per-Tenant Files

Object keys should use a backend-generated tenant namespace:

~~~text
tenants/{tenantId}/documents/{documentId}
~~~

However, a prefix inside a key is not automatically a security boundary. If the runtime service account has permission to read the entire bucket, code can still access another tenant's objects if it constructs the wrong key.

Safeguards:

- Take `tenantId` from the verified `TenantContext`.
- Generate object keys server-side; never let clients choose arbitrary keys.
- Verify tenant ownership before issuing presigned URLs.
- Scope URLs to the exact bucket, object key, HTTP method, and expiration.
- Never return presigned GETs for objects the caller is not authorized to read.
- Use bucket/prefix policies or access points where IAM-level boundaries are required.
- Encrypt data and consider dedicated keys for high-requirement tenants.
- Sanitize metadata and filenames; never embed sensitive data in object keys.

Upload API example:

1. The client requests an upload to the current tenant.
2. The backend verifies upload permissions and quotas.
3. The backend generates `documentId` and the object key.
4. The backend issues a presigned PUT scoped strictly to that key.
5. The client uploads directly.
6. The backend verifies the object and saves a record carrying `tenantId`.
7. Workers process the file with the same tenant context and verify ownership.

With shared buckets, protect upload, download, copy, delete, and lifecycle cleanup paths alike. A cleanup job running with broad permissions can accidentally delete another tenant's objects if prefixes or registries have bugs.

## 10. Queues, Events, and Tenant Context

Asynchronous messages must carry enough metadata for consumers to identify the tenant, yet the message body is not an independent authentication source.

Example envelope:

~~~json
{
  "eventId": "evt-9182",
  "tenantId": "tenant-42",
  "eventType": "order.paid",
  "schemaVersion": 2,
  "aggregateId": "order-918",
  "occurredAt": "2026-11-17T10:20:00Z",
  "payload": {
    "paymentReference": "pay-774"
  }
}
~~~

Consumers should:

1. Verify the event comes from an authorized queue/topic and producer.
2. Validate schema and version.
3. Cross-check `tenantId` against the record or aggregate in the authoritative data store.
4. Verify `eventId` has not already been processed or use an idempotency store.
5. Construct a dedicated `TenantContext` for the message.
6. Query and update data using the tenant key.
7. Record results and idempotency markers in an appropriate transaction.

Never trust `tenantId` inside a message merely because the queue is called internal. A compromised or buggy producer could publish a message carrying the wrong `tenantId`.

### Dedicated Queue or Shared Queue?

A dedicated queue per tenant bounds backlogs and policies, yet increases resource count, mappings, and operational overhead. Shared queues are simpler, yet require message-level tenant validation, fair scheduling, quotas, and DLQ handling that never leaks data across tenants.

The bridge/cell model can use one queue per cell or tenant group. Choose based on throughput, isolation needs, operability, and retention requirements.

## 11. Caches, Search Indexes, and Partition Keys

Caches are an easy place for cross-tenant leaks if keys omit tenant scope.

Dangerous key:

~~~text
order:order-918
~~~

Tenant-scoped key:

~~~text
tenant:tenant-42:order:order-918
~~~

If a cache stores user- or role-dependent data, add appropriate dimensions or cache a permission-safe representation. Do not use only `tenantId` if two users inside the same tenant hold different permissions.

Search systems also require server-side tenant filtering. Never trust a tenant filter sent by the client. Shared search indexes must have a tenant field and enforce filters in the query layer; for sensitive data, consider separate indexes or collections.

Guidelines:

- Namespace caches by tenant and data type.
- Prevent cache key collisions across tenants.
- Enforce TTLs and invalidation when memberships or permissions change.
- Never cache authorization decisions longer than policy permits.
- Audit every cache-hit path, not just database-read paths.
- Never write tenant data into a global cache lacking a tenant dimension.

## 12. Encryption, Secrets, and Per-Tenant Keys

Encryption at rest at the storage/database layer protects stored data, yet does not automatically establish an authorization boundary. If every tenant shares one key and one runtime identity, the application must still enforce access checks.

For tenants requiring dedicated keys:

- Use per-tenant KMS keys or envelope encryption with dedicated data keys.
- Bind encryption context to `tenantId` and resource ID if supported by the service.
- Grant decrypt permissions per tenant/cell when architecture allows.
- Never let callers set arbitrary encryption contexts without validation.
- Manage rotation, disabling, and deletion along the tenant lifecycle.
- Audit encrypt/decrypt operations and key policies.

Tenant integration secrets (such as tenant-specific API keys) should reside in a secret manager, linked to the tenant registry, and readable only by authorized workloads. Never put secrets into shared queues, logs, or caches without commensurate protection.

If a runtime identity can read all tenant secrets, the application needs a strict authorization layer and auditing. For tenants requiring strong isolation, separate workload identities or resource policies per cell/tenant can narrow the access scope.

## 13. Compute Isolation and Preventing Noisy Neighbors

In serverless, multiple tenants can share the same functions and execution environments. One tenant can generate heavy load, message backlogs, or slow requests that degrade service for other tenants. This is the **noisy neighbor** problem.

Per-tenant quotas are needed for:

- Requests per minute.
- Concurrent running jobs.
- Total upload volume.
- Published messages.
- Partner API calls.
- Created resources or records.
- Concurrency limits or priority tiers by plan.

Do not enforce limits solely at the API gateway. Workers also need quotas because tenants can build up backlogs via queues or events.

### Layered Controls

- API: rate limits per tenant and principal.
- Queue: limits on publishing, consumer concurrency, and pending jobs.
- Worker: limits on concurrent jobs per tenant/cell.
- Database: connection quotas, query timeouts, and workload management if available.
- Object storage: storage capacity and object count quotas.
- External APIs: separate rate limits per credential or tenant.
- Compute: max instances, concurrency, and queue-based buffering.

When a tenant exceeds its quota, return an actionable error such as `429` or throttle work per contract. Never let one tenant exhaust worker capacity or database connection pools.

### Fair Scheduling

With shared queues, simple FIFO can let a high-volume tenant monopolize the head of the queue. Use per-tenant/cell queues, weighted-fair schedulers, or cap messages per tenant within a batch. Balance latency, ordering, and cost.

## 14. Tenant Context Across Services

A request may traverse an API gateway, Java function, queue, worker, and downstream service. Tenant context must be propagated under a verified contract.

Do not simply forward an `X-Tenant-Id` header that every service blindly trusts. Options:

- Pass the signed user token and let target services verify issuer/audience.
- Use an internal token carrying tenant claims and a specific audience.
- Pass an event envelope with `tenantId` where consumers cross-check the producer and authoritative data.
- Use workload identity for service-to-service authentication while passing signed or contract-trusted user/tenant authorization context.

The target service must know which context is authoritative and what permissions it grants. Never let an intermediate service escalate privileges by setting a different `tenantId` in a header.

### Do Not Confuse Service Identity with Delegated User Context

A worker may be permitted to read the database using its workload identity. That does not mean the worker is allowed to act across arbitrary tenants. If a job was created on behalf of a user, the event should retain references to the actor and tenant; the consumer verifies permissions or authorization state per business policy at execution time.

For long-running tasks, a user's membership might be revoked after the job is enqueued. The system must decide whether permissions are evaluated at enqueue time or execution time. Document that decision explicitly in contracts and audits.

## 15. Tenant Provisioning, Migration, and Offboarding

Tenant isolation extends beyond request handling. The tenant lifecycle must be managed:

### Provisioning

1. Create an immutable tenant ID and registry record.
2. Assign cell, database/schema, bucket/prefix, and quotas.
3. Create encryption keys or secret namespaces if needed.
4. Set up roles/memberships and initial owner.
5. Initialize configurations and resource policies.
6. Run access-control checks before activating the tenant.

### Migration Between Cells or Isolation Models

- Define data snapshot and write-freeze/dual-write strategy.
- Keep tenant mappings consistent across services.
- Copy data and verify row/object counts and checksums.
- Switch routing at a clean cutover point.
- Check in-flight queue messages and late-arriving events.
- Have a rollback plan and prevent two cells from concurrently writing authoritative data.

### Offboarding

- Revoke memberships, tokens, API keys, and access permissions.
- Stop accepting new jobs and drain backlogs per policy.
- Delete or archive data per retention/legal hold rules.
- Revoke or schedule deletion of encryption keys per procedure.
- Clean up objects, caches, search indexes, and related secrets.
- Retain audit records per policy.
- Verify the tenant can no longer access APIs, workers, or previously issued URLs.

Do not delete the tenant record immediately upon starting offboarding if workers or audits need it to complete teardown. Use lifecycle states such as `ACTIVE`, `SUSPENDED`, `DEPROVISIONING`, and `DELETED` to coordinate.

## 16. Per-Tenant Logging, Metrics, and Auditing

Observability must aid incident investigation without leaking data.

Logs may record:

- Internal tenant ID or pseudonymized identifier.
- Normalized principal ID.
- Request/correlation ID.
- Resource type and action.
- Authorization decision.
- Service, revision, and region.
- Policy version or config version if relevant.

Never log access tokens, secrets, sensitive payloads, or raw customer data. Avoid using tenant ID as a metric label when tenant counts are large, as cardinality can explode. Instead, use system-wide aggregate metrics paired with controlled logging/tracing to investigate a specific tenant.

Audit logs should capture sensitive actions: role changes, membership additions/removals, file downloads, data exports, key changes, support access, and tenant admin actions.

Support/admin permissions must be isolated, require a reason for access, be time-bounded, require approval where needed, and be audited. Never use a shared untraceable admin account.

## 17. Testing Tenant Isolation

Tests must prove tenant A cannot read, modify, delete, or infer tenant B's data across any access path.

| Test | Expected Result |
|---|---|
| User A accesses tenant A's resource | Allowed if permitted |
| User A switches path to tenant B | Denied |
| User A sends header for tenant B | Denied without membership |
| Multi-tenant user switches workspace | Context and permissions update properly |
| Query with only resource ID | Repository requires tenant or DB policy blocks |
| RLS unset | Cannot read/write tenant rows |
| Connection reused for another tenant | Transaction-local tenant context does not leak |
| Message carrying spoofed `tenantId` | Consumer cross-checks and rejects |
| Cache key missing tenant | Test catches collision/cross-tenant result |
| Presigned URL for tenant A object | Cannot be used to read tenant B's object |
| Tenant exceeds quota | Throttled within that tenant's scope |
| Membership revoked | New requests denied per policy |
| Support access | Temporary access and audited |
| Tenant offboarding | APIs, queues, caches, and storage reject unauthorized access |

### Property-Based and Negative Testing

In addition to regular unit tests, seed multi-tenant data and run the same set of operations with randomized tenant IDs. For every response, verify all returned records match the expected `tenant_id`. For every mutation, verify only rows belonging to the current tenant changed.

Test failure paths too: exceptions mid-transaction, timeouts before commit, message retries, and function instance reuse. More isolation bugs surface in cleanup code and retry paths than in happy paths.

## 18. Common Implementation Mistakes

- **Trusting `tenantId` from the request:** attackers can swap the tenant selector; verify membership from the authenticated identity.
- **Checking tenant only in the UI:** callers can hit APIs directly; authorization belongs in the backend.
- **Querying solely by object ID:** creates IDOR/cross-tenant access; every query needs a tenant boundary.
- **Omitting composite keys or tenant-scoped foreign keys:** allows cross-tenant data links.
- **Using `ThreadLocal`/static tenant context without cleanup:** subsequent requests can inherit stale context; pass explicit context and clean up per lifecycle.
- **Setting RLS context outside a transaction:** connection pools can retain context for the next tenant; use transaction-local settings.
- **Using a database role with `BYPASSRLS`:** policies fail to guard application queries; use a restricted runtime role.
- **Treating object prefixes as security boundaries:** bucket permissions may still allow reading everything; verify IAM and exact keys.
- **Trusting `tenantId` in messages:** producer bugs or compromises can emit wrong-tenant messages; consumers must cross-check.
- **Cache keys missing tenant scope:** tenant A's data can be served to tenant B.
- **Sharing one secret across all tenants:** a single credential leak impacts all customers; isolate secrets as required.
- **Missing quotas:** one tenant can exhaust concurrency, connections, or storage for other tenants.
- **Uncontrolled support access:** staff or operational tools can access data without auditing.
- **Offboarding that deletes only users:** objects, queues, secrets, and caches may remain alive or accessible.

## 19. Multi-Tenant Design Workflow for Java Serverless

When building or reviewing a multi-tenant system, follow this sequence:

1. Define whether a tenant is an organization, workspace, or data-ownership unit.
2. Design identity and membership; never infer tenants from emails or client-supplied IDs.
3. Verify issuer, subject, audience, and principal status.
4. Construct an immutable `TenantContext` per HTTP request or message.
5. Enforce permissions by tenant, resource, and action.
6. Choose pool, bridge, or silo for databases and resources.
7. Include tenant keys in schemas, queries, unique constraints, and foreign keys.
8. Add RLS or database policies as defense-in-depth where appropriate.
9. Namespace object storage, caches, search, and queues by tenant.
10. Manage secrets and encryption keys according to required isolation levels.
11. Propagate tenant context across services/events under verified contracts.
12. Enforce quotas and fair scheduling to prevent noisy neighbors.
13. Design provisioning, migration, suspension, and offboarding.
14. Set up auditing, logging, and metrics without leaking data or exploding cardinality.
15. Test cross-tenant access, retries, connection reuse, and all async paths.

## 20. Key Takeaways

Tenant isolation must begin with an authenticated identity and trusted membership, then be enforced across authorization, databases, object storage, queues, caches, secrets, and compute resources. A tenant ID inside a request or message is merely untrusted input until cross-checked against an authoritative source.

In Java serverless, build a dedicated `TenantContext` per invocation, pass it explicitly across layers, and never store tenant state in static fields or uncleaned `ThreadLocal`s. For shared databases, tenant keys, composite constraints, and RLS provide layered defense; for tenants requiring stronger isolation, consider cells or silos.

Enforce quotas so one tenant cannot impact others, manage provisioning/offboarding lifecycles, and test negative paths on both HTTP handlers and workers. The goal is to guarantee that every operation affects only the data and resources the current tenant is permitted to use.
