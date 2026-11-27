# Authorization and Preventing Cross-Tenant Access

## 1. Why Is Tenant Isolation a Core Security Boundary?

In a multi-tenant platform, multiple organizations share one application and part of the infrastructure. Each organization is a **tenant** with its own users, data, configuration, and permissions. A single data-filtering bug can allow a user from Tenant A to read, modify, or delete Tenant B's resources. This is a severe data isolation incident, even when both users are legitimately logged in.

In the **CLOUD_ARCHITECTURE** module, architecture is designed from business requirements through networking, compute, data, and deployment models, then evaluated across reliability, security, scalability, cost, and operations. For multi-tenant SaaS, tenant boundaries must be enforced across requests, databases, caches, object storage, queues, search, logs, backups, and administrative tools.

**Tenant isolation** is not just adding a `tenant_id` column to a table. It is a set of rules governing identity, permissions, ownership, resource access, asynchronous processing, and observability, ensuring every operation affects only the tenant a principal is authorized to represent.

After this lesson, you will be able to:

- Distinguish authentication, tenant resolution, and authorization.
- Build tenant context from authenticated identity without trusting client-declared tenant IDs.
- Prevent IDOR and cross-tenant access at the object/resource level.
- Compare shared database, schema-per-tenant, and database-per-tenant.
- Protect databases with tenant-scoped queries, composite keys, and row-level security.
- Design tenant-scoped cache keys, object paths, queue messages, search indexes, and background jobs.
- Control support/admin access, exports, backups, and break-glass operations.
- Write negative tests, audits, and alerts to detect tenant leakage.

## 2. Concepts and Trust Boundaries

### 2.1. Tenant, User, Principal, and Resource

| Concept | Meaning | Example |
|---|---|---|
| Tenant | Organization/customer owning a data domain | An Phat Company |
| User | End user belonging to one or more tenants | Equipment booking staff |
| Principal | Authenticated identity used for decision-making | User token or service identity |
| Membership | Relationship between user and tenant with status/role | User U has `booking-admin` role in Tenant A |
| Resource | Protected object | Booking, invoice, device, file, report |
| Tenant context | The tenant represented by the current request/operation | `tenant A` in an authenticated request |
| Policy | Conditions allowing a principal to perform an action | User can only read bookings in tenants they have access to |

A user can be a member of multiple tenants. Therefore, never assume a one-to-one mapping from user ID to tenant ID. Authorization must consider the principal, tenant context, membership, role/scope, and the resource being accessed.

### 2.2. Authentication Is Not Authorization

- **Authentication (AuthN):** determines who the principal is, e.g., verifying a token, session, or service identity.
- **Tenant resolution:** determines which tenant the request operates within, based on verified information and membership.
- **Authorization (AuthZ):** decides whether the principal is allowed to perform a specific action on a specific resource within that tenant.

A valid token only proves identity or claims issued by an issuer. It does not automatically prove the user may read every booking with a valid ID.

### 2.3. Tenant Context Must Have a Trusted Source

A request may carry a tenant slug in the hostname, path, header, or claim. Client-supplied values are only **input for selecting context**, not proof of permission.

Example:

~~~http
GET /tenants/tenant-a/bookings/bkg-8124
Authorization: Bearer <access-token>
~~~

The server must:

1. Authenticate the token/session and extract subject, issuer, audience, expiry, and trusted claims.
2. Verify the user has an active membership in Tenant A.
3. Check the role/scope for the operation.
4. Read the booking within tenant scope and verify ownership/relationship.
5. Return an appropriate response without revealing the existence of other tenants' resources beyond chosen policy.

Never do something like:

~~~text
tenant_id = request.header["X-Tenant-ID"]
query("SELECT * FROM bookings WHERE booking_id = ?", booking_id)
~~~

This logic both trusts an unverified header and queries without tenant scope. If a proxy or client sets the header, an attacker can attempt to switch tenants.

### 2.4. Secure Request Flow

~~~mermaid
flowchart TD
    CLIENT["Client request"] --> AUTHN["Verify token / session"]
    AUTHN --> ID["Trusted principal"]
    ID --> RESOLVE["Resolve requested tenant"]
    RESOLVE --> MEMBER{"Active membership?"}
    MEMBER -->|"No"| DENY["Deny without data access"]
    MEMBER -->|"Yes"| POLICY["Check action / role / scope"]
    POLICY --> RESOURCE{"Resource belongs to tenant?"}
    RESOURCE -->|"No"| DENY
    RESOURCE -->|"Yes"| ACCESS["Tenant-scoped data access"]
    ACCESS --> AUDIT["Audit security-relevant action"]
    AUDIT --> RESPONSE["Return allowed result"]
~~~

Tenant resolution and resource authorization are two distinct checks. A user with membership in Tenant A still cannot read Tenant B's resources just because the client sends B's ID.

## 3. Types of Cross-Tenant Access Attacks

### 3.1. Insecure Direct Object Reference (IDOR)

An API uses a client-sent object ID without verifying whether the resource belongs to the principal's tenant.

Example:

~~~http
GET /api/bookings/bkg-1002
Authorization: Bearer <token-of-tenant-a-user>
~~~

If `bkg-1002` belongs to Tenant B and the server queries solely by `booking_id`, a Tenant A user can read B's data. UUIDs are harder to guess than sequential numbers, but they are not an authorization mechanism.

### 3.2. Mass Assignment and Over-Posting

Clients send extra fields such as `tenant_id`, `owner_id`, `role`, or `status` to overwrite properties the server does not allow users to set directly.

~~~json
{
  "deviceId": "dev-017",
  "slotId": "slot-0900",
  "tenantId": "tenant-b",
  "status": "confirmed"
}
~~~

Booking creation APIs should bind only allowed fields from the request; tenant ID, owner ID, and workflow status must be set by the server from context and business logic. Never deserialize the entire body straight into an entity and persist it.

### 3.3. Confused Deputy

A broadly privileged service fulfills a request on a caller's behalf without preserving tenant context or checking scope. For example, a `report-export` service has permission to read all objects; a Tenant A user passes an object key belonging to Tenant B, and the service downloads that file.

A broadly privileged service must check caller context, resource ownership, and purpose before exercising its privileges. Never treat service-to-service authentication as permission to access all tenants.

### 3.4. Leaks via Cache or Shared Storage

An application queries the database for the right tenant but uses a cache key based only on booking ID. If IDs can collide across tenants or cache entries lack tenant scope, subsequent requests can receive another tenant's response.

Other leak vectors include guessable object paths, signed URLs lacking proper permissions/expiry, search indexes missing tenant filters, queue consumers trusting unverified tenant IDs, and logs/exports containing cross-tenant data.

## 4. Authorization Must Be Tied to the Resource

### 4.1. Principal + Tenant + Action + Resource Policy

At minimum, an authorization decision must examine:

- Principal: which user/service?
- Tenant: which tenant is being represented?
- Action: read, create, update, delete, export, approve, or administer?
- Resource: which object, which tenant owns it, and what is its relationship to the principal?
- Context: relevant environment, status, purpose, time, or risk signals?

The decision can be expressed as:

~~~text
ALLOW when:
  principal is authenticated
  AND membership(principal, tenant) is active
  AND role permits action
  AND resource.tenant_id == tenant.id
  AND resource-specific policy permits this principal
~~~

Not every endpoint checks every factor identically, but the system must explicitly define the applicable policy. For example, regular users can read bookings they created; `tenant-admin` can read all bookings in the tenant; support agents can gain support permissions bound by ticket and expiration.

### 4.2. Role-Based and Attribute-Based Access

**RBAC** (Role-Based Access Control) grants permissions by role within a tenant scope:

| Role in Tenant | Example Permissions | Limits |
|---|---|---|
| `tenant-owner` | Manage billing, members, and tenant settings | Only tenants they own/administer |
| `tenant-admin` | Manage members and resources | Does not automatically grant cross-tenant access |
| `booking-manager` | View and process tenant bookings | Only assigned operations |
| `member` | Create and view bookings within their own scope | Cannot view all tenant data unless policy permits |
| `auditor` | Read permitted reports/audits | Usually cannot write business data |

**ABAC** (Attribute-Based Access Control) evaluates attributes such as tenant ID, department, resource classification, owner, support ticket, environment, or time-bound approval. ABAC is flexible for complex organizations but harder to debug; tooling is needed to explain why an allow/deny decision occurred.

RBAC can be combined for stable roles with ABAC for resource scoping. Never turn roles into an arbitrary self-declared string from the client.

### 4.3. Object-Level and Relationship-Based Permissions

The "member" role does not mean permission to read every object in the tenant. For example:

- Staff view only bookings they created or are assigned to.
- Team managers view their team's bookings.
- `Tenant-admin` views resources across the tenant.
- Auditors read replicas or read-only views.

When rules depend on relationships between users, teams, projects, and resources, relationship-based access control (ReBAC) or a policy engine can be used. Regardless of framework, the final decision still needs tenant boundaries and resource ownership checks.

### 4.4. Deny by Default

If tenant context is missing, membership is undetermined, the policy engine times out, or a resource is not found within tenant scope, the default must be to deny or return a safe state. Never fall back to "allow" to increase availability.

Specifically, when the authorization service is unavailable, failing closed may reduce availability but protects confidentiality. If caching authorization decisions to reduce latency, bound TTL, scope, policy version, and revocation mechanisms; never cache allow decisions indefinitely.

## 5. Storage Strategies for Multi-Tenant Systems

Data isolation levels depend on the storage model. There is no single best model for every product.

### 5.1. Shared Database, Shared Schema

All tenants share one database and tables; each row has a `tenant_id`.

Advantages:

- Low infrastructure cost and efficient resource utilization.
- Centralized migrations and operations.
- Suitable for large numbers of tenants with moderate load.

Trade-offs:

- A query missing a tenant filter can leak data.
- Noisy neighbors can impact other tenants.
- Per-tenant backup/restore is more complex.
- Row-level permissions and connection context require careful governance.

### 5.2. Schema-per-Tenant

Each tenant has its own schema inside the same database instance.

Advantages: clearer namespace separation; can apply separate permissions/schema migrations; shares compute/database engine.

Trade-offs: large schema counts complicate migrations/catalogs/quotas; connections/search paths are easy to misconfigure; an overly broad credential can still read multiple schemas; instance-level noisy neighbors persist.

### 5.3. Database-per-Tenant

Each tenant has its own database or dedicated database cluster/instance.

Advantages: smaller data blast radius; clearer backup/restore, keys, quotas, and performance isolation; convenient for tenants with distinct compliance needs.

Trade-offs: higher costs and resource counts; complex provisioning, migrations, connection management, monitoring, and patching; small tenants may waste resources.

### 5.4. Model Comparison

| Criterion | Shared Schema | Schema-per-Tenant | Database-per-Tenant |
|---|---|---|---|
| Logical isolation | Relies heavily on tenant predicates/RLS | Separate namespaces, still needs privileges | Clearer database boundaries |
| Cost | Usually lowest | Medium | Usually higher |
| Migrations | One shared schema | Repeated across many schemas | Multi-database orchestration |
| Single-tenant backup/restore | Harder | Can separate by schema/tool | Usually easier to scope |
| Noisy neighbor | Higher | Still shares instance | Can separate compute/storage |
| Large tenant count management | Simpler with strong policies | Complex catalog and migrations | Complex provisioning/monitoring |
| Best fit | Many small/medium tenants | Need separate namespaces and lifecycles | Large tenants, high isolation demands |

### 5.5. Tiered/Hybrid Isolation

A platform can use a shared database for most tenants while moving large or specialized tenants to dedicated databases/clusters. This is the hybrid/tiered model.

Hybrid designs must maintain a unified data access interface while tenant-to-database mappings are managed by a trusted control plane. Never accept a hostname/database name from the client and connect directly. Clear migration, failover, backup, tenant move, and mapping validation workflows are required.

~~~mermaid
flowchart TB
    API["Tenant-aware API"] --> RES["Trusted tenant directory"]
    RES --> ROUTE{"Tenant placement"}
    ROUTE -->|"Standard tier"| SHARED[("Shared DB / schema")]
    ROUTE -->|"Dedicated tier"| DED[("Dedicated DB")]
    ROUTE -->|"Regional tier"| REG[("Regional DB cluster")]
    SHARED --> POLICY["Tenant authorization + data access layer"]
    DED --> POLICY
    REG --> POLICY
~~~

The directory determines data location and per-tenant policies; services must still authorize resources and tenants. Routing to the right database does not mean a user may read every record in that database.

## 6. Database Isolation: Composite Keys, Query Scoping, and RLS

### 6.1. Tenant-Scoped Composite Keys and Foreign Keys

With a shared schema, tenant ID can be included in primary/unique keys so the database reinforces ownership consistency:

~~~sql
CREATE TABLE bookings (
    tenant_id   UUID NOT NULL,
    booking_id  UUID NOT NULL,
    customer_id UUID NOT NULL,
    status      TEXT NOT NULL,
    PRIMARY KEY (tenant_id, booking_id)
);

CREATE TABLE booking_items (
    tenant_id  UUID NOT NULL,
    booking_id UUID NOT NULL,
    item_id    UUID NOT NULL,
    PRIMARY KEY (tenant_id, booking_id, item_id),
    FOREIGN KEY (tenant_id, booking_id)
      REFERENCES bookings (tenant_id, booking_id)
);
~~~

Composite foreign keys prevent one tenant's item from pointing to another tenant's booking within the same schema. This does not replace query authorization, but adds an invariant at the database layer.

### 6.2. Tenant-Scoped Queries

Every resource read/write query must attach tenant scope from trusted context:

~~~sql
SELECT booking_id, status
FROM bookings
WHERE tenant_id = :trusted_tenant_id
  AND booking_id = :booking_id;
~~~

Updates/deletes also require the tenant condition:

~~~sql
UPDATE bookings
SET status = :new_status
WHERE tenant_id = :trusted_tenant_id
  AND booking_id = :booking_id;
~~~

Verify affected row counts and business transitions. Never fetch a row by ID first and check the tenant only in a code branch after already reading sensitive data.

### 6.3. Row-Level Security (RLS)

Databases can enforce row-level security policies to restrict which rows a role may access. Conceptual PostgreSQL example:

~~~sql
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON bookings
USING (
  tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
  tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

The application must set tenant context inside the transaction before querying:

~~~sql
BEGIN;
SET LOCAL app.tenant_id = '2c0e2c3d-5a10-4b8e-ae8d-6e0a8ea7a4c1';
SELECT booking_id, status FROM bookings;
COMMIT;
~~~

This is an illustrative example and must be tested for your database version and configuration. Key points:

- Connection pools reuse connections; session-level settings must never leak to subsequent requests. Use appropriate transaction-scoped settings and always reset/rollback.
- Table owners, superusers, or roles with bypass-RLS privileges may ignore policies depending on the database. Application runtimes should never connect with overly privileged roles.
- RLS protects only tables with policies enabled; new tables or new query paths can be missed.
- Application-set tenant context must still originate from verified identity; if an attacker controls the setting, RLS cannot save you.
- Policy tests must cover `SELECT`, `INSERT`, `UPDATE`, `DELETE`, and all relevant roles/partitions.

### 6.4. Preventing Mistakes at the Data-Access Layer

Use repository/query abstractions that require `TenantContext` instead of letting developers write arbitrary queries:

~~~text
bookingRepository.findById(tenantContext, bookingId)
bookingRepository.update(tenantContext, bookingId, command)
~~~

Do not expose generic methods like `findById(bookingId)` for multi-tenant paths if they omit tenant scope. Static analysis, code reviews, and integration tests must catch queries lacking tenant predicates.

## 7. Tenant Isolation in Caching

Caches are a frequent source of cross-tenant leakage because many services share a single cluster.

### 7.1. Cache Keys Must Include Security Scope

Design:

~~~text
tenant:{tenant_id}:booking:{booking_id}
tenant:{tenant_id}:catalog:{catalog_id}
tenant:{tenant_id}:user:{user_id}:preferences
~~~

Avoid using:

~~~text
booking:{booking_id}
user:{user_id}:preferences
~~~

when IDs are not globally unique or data depends on the tenant. Even when IDs are globally unique, adding tenant scope to cache keys helps catch mistakes in calling layers and makes isolation boundaries explicit.

### 7.2. Caching Authorization Decisions

If caching permissions:

- Keys must include principal, tenant, resource/action scope, and policy version as needed.
- TTLs must be short relative to risk; include invalidation when membership/roles are revoked.
- Never share an allow decision across tenants or users.
- When tenant context is missing or the cache fails, never fall back to broad permissions.
- Never cache raw tokens or secrets in keys/logs.

### 7.3. Invalidation and Tenant Lifecycle

When a user is removed from a tenant, cached session/authorization data may persist. Use events/versions for invalidation or bounded TTLs to limit exposure. When a tenant is suspended/disabled, immediately enforce policy across APIs, caches, workers, signed URLs, and running export jobs.

## 8. Object Storage, Files, and Signed URLs

### 8.1. Tenant-Scoped Object Namespaces

Example path:

~~~text
tenants/{tenant_id}/bookings/{booking_id}/documents/{document_id}
~~~

Paths containing a tenant ID help organize files, **but are not an authorization mechanism**. Bucket/object policies and the application must still verify the principal has access to the tenant/resource.

Never allow clients to pass arbitrary full object keys that the backend reads with broad service permissions. Instead, the backend receives a resource ID, verifies tenant ownership, resolves the object key from trusted metadata, and then reads.

### 8.2. Signed URLs

Signed URLs let clients access objects for a limited period without sharing service credentials. However, URLs act as bearer capabilities: anyone holding an unexpired URL can perform the signed scope.

Rules:

- Issue URLs only after object-level authorization.
- Restrict to the exact object, HTTP method, and an appropriately short duration.
- Never write full URLs into logs, analytics, or tickets.
- Avoid long-lived signed URLs for sensitive data if alternatives exist.
- Consider revocation: many signed URLs only expire on timeout or when related resources/credentials/policies change.
- When a tenant is suspended or a user is revoked, assess the impact on already-issued URLs.

### 8.3. Secure Uploads

Uploads must validate tenant ownership, file size/type, malware scanning, checksums, content disposition, and storage destination. When using pre-signed uploads:

- The backend generates keys inside the tenant prefix after verifying context.
- Grant `PUT` permission only for the specific object/method.
- Prevent clients from overwriting another tenant's objects.
- After upload, the backend verifies metadata/object before marking the file accepted.
- Never trust client-declared MIME types or file extensions.

## 9. Queues, Events, and Background Jobs

Synchronous requests have a tenant context, but asynchronous messages may execute minutes or hours later after the user has logged out, membership changed, or the tenant was suspended. Never rely on thread-local/request context from the originating process.

### 9.1. Tenant Metadata in Messages

Events/commands can include:

~~~json
{
  "eventId": "evt-7812",
  "tenantId": "tenant-a",
  "eventType": "booking.export.requested",
  "actorId": "user-120",
  "resourceId": "export-812",
  "correlationId": "corr-991",
  "occurredAt": "2026-11-18T09:00:00Z",
  "schemaVersion": 1
}
~~~

This metadata supports routing, auditing, and verification; the message does not by itself prove the tenant ID is valid. Consumers must:

1. Authenticate message origin via broker identity/ACLs and signatures if required by design.
2. Validate schema and allowed event types.
3. Verify the tenant exists/is active and the resource belongs to the tenant.
4. Check actor/authorization context or service-to-service policy appropriate for the workflow.
5. Create a fresh tenant-scoped data access context inside the consumer process.
6. Record results with an idempotency key/event ID and audit log.

### 9.2. Tenant Context in Long-Running Jobs

Jobs must record tenant ID, actor/service identity, purpose, resource scope, creation time, policy version if relevant, deadline, and correlation ID. During execution, workers re-verify permissions against current policy or a business-approved snapshot authority. Never assume permissions at enqueue time remain valid hours later.

For example, if a tenant is suspended mid-export:

- If the export has not started, the worker can halt immediately.
- If processing is underway, the worker needs a safe checkpoint/cancellation path.
- If the artifact was generated but no URL issued yet, do not issue the URL after permissions are revoked.
- If a URL was already issued, evaluate expiry/revocation strategy.

### 9.3. Queue Isolation and Fairness

One tenant submitting millions of jobs can slow down all other tenants. Use per-tenant quotas, concurrency limits, fair scheduling, priority classes, or dedicated queues for large tenants. This provides both performance isolation and reduces the risk of one tenant causing denial of service for the rest.

## 10. Search, Analytics, and Exports

### 10.1. Search Indexes

Documents in a search index must have a tenant identifier and mandatory server-side filtering. Never allow clients to send arbitrary tenant filters and treat them as authorization.

Checkpoints:

- Does the search API attach a tenant filter from trusted context?
- Can aggregations/facets combine data across multiple tenants?
- Are autocomplete, suggestions, vector embeddings, and index aliases tenant-scoped?
- Do reindex/backfill jobs preserve tenant IDs and policies?
- Can admin/debug queries bypass filters?

In shared indexes, a missing filter in aggregations can still leak data even if document hits are filtered. For sensitive tenants, consider dedicated indexes or dedicated clusters.

### 10.2. Analytics and Data Lakes

Data warehouses often aggregate data across tenants for summary reporting. Cross-tenant analysis may be permitted to platform operators for specific purposes, but that never means tenant users may view raw data of other tenants.

Designs should:

- Separate raw, curated, and aggregate zones.
- Enforce tenant-based row/column-level security.
- Mask/pseudonymize identifying fields when plaintext is unnecessary.
- Prevent export jobs from producing multi-tenant files and handing out individual URLs.
- Track lineage, owners, purposes, and retention.
- Verify dashboards/shared queries enforce server-side filters.

### 10.3. Exports and Reports

An export request requires authorization at creation time and before delivering results. Export files should carry tenant ownership, storage policy, encryption keys, TTLs, audits, and creator metadata. If a report contains cross-tenant data for platform operations, it needs a dedicated approval and access workflow.

## 11. Identity, Tenant Provisioning, and Lifecycle

### 11.1. Membership Lifecycle

Memberships change over time:

- Invite, accept, and activate.
- Add/remove roles or scopes.
- Suspend user or tenant.
- Remove user from tenant.
- Transfer ownership or merge tenants.

These changes must update authorization, session/token claims, caches, API keys, jobs, and access links. If tokens hold stale roles too long, use short token lifetimes, introspection, revocation, or policy-version checks.

### 11.2. Tenant Directory / Control Plane

The control plane can manage:

- Stable tenant ID and active/suspended/closing statuses.
- Domain/slug and mappings to region/database/tier.
- Subscriptions/quotas and feature enablement.
- Encryption keys, data residency, and backup policies.
- Memberships/roles and owners.
- Lifecycle events: provision, migrate, suspend, delete.

The tenant directory is authoritative control-plane data; never allow arbitrary requests to query an unprotected config table. The directory needs dedicated availability, auditing, authorization, and caching policies.

### 11.3. Offboarding and Tenant Deletion

When closing a tenant, define steps to:

1. Block creation of new requests/jobs.
2. Revoke memberships, API keys, sessions, and service grants.
3. Stop or drain running workflows.
4. Handle retention, legal holds, ownership exports, and deletion requests.
5. Delete/purge primary data, caches, search indexes, objects, queues/DLQs, and replicas per policy.
6. Manage keys if crypto-erasure is used and appropriate.
7. Record evidence, audits, and completion notifications.

Do not hastily delete keys or backups while retention/legal holds remain active. Tenant lifecycles must tie into data lifecycle and backup/restore design.

## 12. Support and Platform Administrator Access

Support staff or platform admins may need to assist multiple tenants, but cross-tenant access must remain a controlled exception.

### 12.1. Time-Bound Support Access

A secure model:

- Support opens a ticket linked to the tenant and stated purpose.
- An authorized approver approves scope: data types, actions, and duration.
- Staff authenticate strongly (MFA/SSO) and activate just-in-time access.
- Grant only read or minimum necessary actions.
- Notify users/tenants if policy requires or where feasible.
- Audit all access to sensitive data.
- Permissions auto-expire; review access logs afterward.

### 12.2. Break-Glass

Break-glass is reserved for severe incidents when normal approval flows are too slow. Requirements:

- Clear activation conditions and approvers.
- MFA, dedicated credentials, very short durations.
- Restricted resources/actions and documented justification.
- Immutable audits that operators cannot modify or delete.
- Immediate alerts to security/on-call.
- Mandatory post-incident review and credential revocation.

Never share a standing admin credential across all support engineers. Never use a "support mode" flag to bypass tenant checks across the entire application.

## 13. Testing Tenant Isolation

You cannot test only a single tenant's happy path and assume tenant boundaries hold. Negative tests with Tenant A and Tenant B operating concurrently are required.

### 13.1. Test Matrix

| Scenario | Expectation |
|---|---|
| User A reads booking A | Allowed if role/resource policy permits |
| User A reads booking B via guessed ID | Denied; leaks none of B's data |
| User A updates booking B | Denied; data unchanged |
| User A deletes file B | Denied; attempt audited |
| User A changes header/host/path to Tenant B | Membership/context re-verified |
| User without membership selects Tenant A | Denied prior to data query |
| Removed user with unexpired old token | Access revoked per revocation policy |
| Cache with colliding keys across tenants | Never returns cross-tenant values |
| Search query missing tenant filter | Test fails or query layer injects filter |
| Queue message with tampered tenant ID | Consumer rejects or quarantines |
| Worker executes job after tenant suspension | Canceled/blocked per policy |
| Expired support access | Can no longer read tenant data |
| Export file containing another tenant | Test detects and blocks prior to release |

### 13.2. Two-Tenant Integration Tests

~~~text
tenantA = createTenant("A")
tenantB = createTenant("B")
userA = createMember(tenantA, role="member")
userB = createMember(tenantB, role="member")

bookingA = createBooking(as=userA, tenant=tenantA)
bookingB = createBooking(as=userB, tenant=tenantB)

assert readBooking(as=userA, tenant=tenantA, id=bookingA.id) == ALLOW
assert readBooking(as=userA, tenant=tenantA, id=bookingB.id) == DENY
assert updateBooking(as=userA, tenant=tenantA, id=bookingB.id) == DENY
assert deleteDocument(as=userA, tenant=tenantA, id=documentB.id) == DENY
~~~

Pseudocode should run against real APIs/repositories and verify side effects too: no rows modified, no events emitted, no cache entries written, and proper audit records created. Asserting HTTP 403 alone is insufficient if writes already happened before denial.

### 13.3. Property/Fuzz Testing

Generate combinations of users/tenants/resources and verify invariants:

~~~text
for every request:
    if resource.tenant_id != trusted_context.tenant_id:
        assert no_read
        assert no_write
        assert no_export
        assert no_side_effect
~~~

Test sequential IDs, fake UUIDs, disabled tenants, duplicate headers, wrong token audiences, Unicode/case variations in tenant slugs, and race conditions during membership revocation. Fuzzing must run in a test environment with synthetic data and bounded resources.

### 13.4. RLS and Database Testing

Create test connections using the exact runtime role, never an admin role. Run transactions through an actual connection pool; verify `SELECT`/`INSERT`/`UPDATE`/`DELETE` see only the current tenant's rows; verify reused connections carry no previous tenant context; verify new tables do not accidentally lack RLS/policies.

## 14. Auditing, Observability, and Leakage Detection

### 14.1. Recommended Audit Events

- Principal/user/service identity.
- Tenant context and relevant membership/role.
- Action and resource type/ID.
- Outcome (allow/deny), policy/version, or appropriate reason code.
- Correlation/trace ID and timestamp.
- Support/break-glass ticket, approver, and expiry if applicable.
- Exports/downloads/deletions and role/key/policy changes.

Never log access tokens, secrets, or unnecessary PII contents. Tenant ID logs need access controls and retention policies since they can enable customer mapping.

### 14.2. Essential Alerts

- A principal repeatedly accesses resources belonging to another tenant.
- A single request carries conflicting tenant contexts.
- Sudden spike in 403/404 responses across a range of resource IDs.
- Search/exports return row counts far exceeding a tenant's normal scale.
- Service roles exercising cross-tenant access outside expected jobs/approvals.
- Expired support sessions continuing to call APIs.
- Cache keys or object prefixes lacking tenant scope.
- RLS policies or table privileges modified outside change windows.

Not every cross-tenant attempt is malicious; it may stem from client bugs or stale links. Still, it must be measured, classified, and investigated by severity.

### 14.3. Metrics Without Data Exposure

Measure request counts, deny counts, export sizes, support access, and tenant quotas by group/tier. Avoid creating metric labels for every user/resource ID due to high cardinality and identifier exposure risks. Use controlled sampled logs/traces for targeted investigations.

## 15. Mitigating Noisy Neighbors and Protecting Fairness

Tenant isolation is not solely confidentiality. One tenant can degrade availability/performance for others by exhausting CPU, DB connections, queue throughput, cache memory, or storage IOPS.

Mitigations:

- Per-tenant quotas for API requests, concurrent jobs, storage, uploads, and exports.
- Rate limits per tenant/client/operation.
- Fair scheduling or per-tenant queue/concurrency budgets.
- Bounded connection pools and query timeouts.
- Appropriate cache memory namespaces and eviction policies.
- Admission control for batch jobs and heavy reports.
- Dedicated tiers for large/regulated tenants if needed.

Quotas must handle overages gracefully: return appropriate `429`/`403`, quota notifications, `Retry-After`, or upgrade tiers. Never let one tenant stall the control plane or global worker pool.

## 16. Reference Architecture for BookingCloud

~~~mermaid
flowchart TB
    U["Tenant user / client"] --> GW["API gateway"]
    GW --> AUTH["Identity + membership resolver"]
    AUTH --> CTX["Trusted TenantContext"]
    CTX --> SVC["Tenant-aware services"]
    SVC --> AUTHZ["Resource authorization"]
    AUTHZ --> DAL["Tenant-scoped data access"]
    DAL --> DB[("Shared DB with RLS/composite keys")]
    DAL --> CACHE[("Tenant-scoped cache keys")]
    DAL --> OBJ[("Private object storage prefixes")]
    SVC --> Q["Tenant-tagged commands/events"]
    Q --> W["Workers revalidate tenant/resource"]
    W --> DAL
    SVC --> AUDIT["Audit / security telemetry"]
    AUTHZ --> AUDIT
    W --> AUDIT
~~~

In this design:

- The gateway authenticates connections and forwards verified identity tokens.
- The membership resolver constructs tenant context from a trusted source.
- Authorization checks roles and resource relationships.
- The data-access layer enforces tenant scope across queries, caches, and object accesses.
- Workers reconstruct context from verified messages and re-check current tenant status.
- Audits correlate operations while limiting sensitive data.

For dedicated-database tenants, the DAL picks the right datastore from the tenant directory while still enforcing identity and object policies at the application layer.

## 17. Well-Architected Evaluation of Tenant Isolation

| Lens | Review Questions | Required Evidence |
|---|---|---|
| **Operational Excellence** | Who owns tenant policies, membership lifecycles, and support access? | Tenant catalog, runbooks, access reviews, audits, automation, and incident drills |
| **Security** | Is tenant context from a trusted source? Do all resources/queries/caches/exports check scope? | Threat model, IAM/RBAC/ABAC, RLS tests, negative tests, signed-URL controls |
| **Reliability** | How does the system fail safely if the authorization service, tenant directory, or policy cache fails? | Fail-closed behavior, bounded cache TTLs, recovery paths, multi-tenant fault tests |
| **Performance Efficiency** | Do tenant resolution and authorization introduce latency or DB contention? | Per-operation p95/p99, policy cache metrics, query plans, and load tests |
| **Cost Optimization** | Which isolation level fits each tier, and are backups/restores overly expensive? | Cost per tenant, dedicated-tier utilization, provisioning, and restore costs |
| **Sustainability** | Do closed tenants leave behind unnecessary data, caches, indexes, or jobs? | Retention/deletion evidence, resource lifecycles, storage and compute utilization |

Designs must balance isolation against cost and operability. Shared schemas conserve resources but require strict query enforcement; dedicated databases improve blast-radius isolation yet require automation to manage many resources. Decisions should rest on sensitivity, workload, service contracts, and policy provability.

## 18. Practice Exercise: Reviewing Cross-Tenant Access Bugs

An equipment management SaaS has these APIs:

- `GET /bookings/{bookingId}`
- `PATCH /bookings/{bookingId}`
- `POST /exports`
- `GET /files/{fileId}/download`

Tokens carry subject and role, while clients pass `X-Tenant-ID` in headers. The database uses a shared schema with `tenant_id`, yet repositories currently query bookings solely by `booking_id`. Cache keys are `booking:{bookingId}`. Export workers take `tenant_id` from messages and use a service role allowed to read all objects. Support teams use a shared admin role for investigations.

Complete the following:

**Task 1 — Threat model:** list at least five cross-tenant access or confused deputy paths.

**Task 2 — Tenant context:** design tenant resolution from verified memberships. Handle a user belonging to two tenants and a request selecting an unauthorized tenant.

**Task 3 — API authorization:** write policies for `GET`/`PATCH` bookings, exports, and file downloads. Distinguish role-level from object-level authorization.

**Task 4 — Database:** fix queries to enforce tenant scope; propose composite keys/foreign keys and evaluate RLS alongside connection pooling.

**Task 5 — Cache/object:** design tenant-scoped keys and object namespaces; specify signed URL generation rules.

**Task 6 — Worker:** fix the message contract, authenticate the source, verify tenant/resource/actor, and handle tenant suspension while a job is running.

**Task 7 — Support:** design just-in-time access, purpose, approval, expiry, and auditing to replace the shared admin role.

**Task 8 — Testing/monitoring:** build a negative test matrix, logs/metrics/alerts, and incident response triggers when cross-tenant data leakage is detected.

### Self-Check Answer Framework

| Current State | Risk | Remediation |
|---|---|---|
| Trusts `X-Tenant-ID` | Client spoofs tenant context | Resolve via verified principal and membership |
| Queries solely by booking ID | IDOR / cross-tenant read/write | Tenant-scoped queries and resource authorization |
| Cache keys without tenant | Serves another tenant's cached response | Tenant-scoped keys and authorization cache scoping |
| Worker trusts `tenant_id` in message | Forged/replayed messages or stale permissions | Authenticate publisher, validate tenant/resource, re-check policy |
| Service role reads all objects | Confused deputy, large blast radius | Prefix/resource scoping, short-lived identities, and policies |
| Shared support admin | Untraceable access exceeding purpose | JIT, MFA, tickets, approvals, expiry, audits |

Solutions must prove not only that requests are denied, but also that no side effects occur, no events are emitted, no caches are written, and no exports are generated before authorization completes.

## 19. Pre-Production Checklist for Multi-Tenant Workloads

- [ ] Tenant model, tenant owners, and membership lifecycles are defined.
- [ ] Authentication, tenant resolution, and resource authorization are separate steps.
- [ ] Tenant context comes from verified principals/memberships, never trusting raw headers/paths/queries alone.
- [ ] Every read/write/export/delete query has tenant scope.
- [ ] Object-level authorization verifies the resource actually belongs to the tenant and the principal has permission.
- [ ] Composite keys/foreign keys/RLS are enabled and tested with the runtime database role.
- [ ] Cache keys, authorization caches, and invalidation enforce tenant scope.
- [ ] Object paths, uploads, downloads, and signed URLs are issued after authorization.
- [ ] Queues/events authenticate sources, verify tenants/resources, and workers revalidate policies at runtime.
- [ ] Search, aggregations, analytics, reports, and exports enforce server-side tenant filters.
- [ ] Background jobs carry actor, purpose, deadline, idempotency, and cancellation paths.
- [ ] Support/admins use just-in-time access, approvals, expirations, and audits.
- [ ] Backups, snapshots, restores, and offboarding preserve data ownership/retention.
- [ ] Negative tests exist across at least two tenants for read/write/delete/export/cache/queue paths.
- [ ] Audits, cross-tenant access alerts, and incident response procedures are in place.
- [ ] Quotas/fairness prevent one tenant from degrading service for others.

Authorization and preventing cross-tenant access require guarding the same boundary across identities, requests, resources, and everywhere data is replicated or processed. A tenant ID is merely an attribute; it becomes a security boundary only when bound to a trusted principal, explicit policies, and query/resource enforcement. Negative testing, auditing, and time-bound operational permissions prove that boundary holds as the system scales and evolves.
