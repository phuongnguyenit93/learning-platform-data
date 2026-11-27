# Designing Tenant Identity and Cross-System Context Propagation

In a multi-tenant platform, multiple organizations share a single product or service cluster. The system must know which tenant, which user, which permissions, and which data scope each request is acting on behalf of. This information must be reliably determined at the entry point, then propagated across APIs, services, queues, workers, databases, caches, and object storage.

If tenant context is missing, spoofed, or altered along the way, the system may read another tenant's data, apply the wrong quota, write inaccurate audit logs, or execute operations beyond authorized scope. Therefore, **tenant identity and tenant context are a core security boundary**, not merely a `tenantId` field added to a request.

In the **CLOUD_ARCHITECTURE** module, this lesson focuses on designing tenant identity, authentication and authorization, propagating context across synchronous/asynchronous boundaries, data isolation, observability, and testing. The goal is to preserve the correct relationship between **who is calling, which tenant they represent, what they are allowed to do, and which tenant owns the data being processed** across the entire journey.

## 1. Distinguishing Tenant, User, Principal, and Tenant Context

These concepts are related but not synonymous:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Tenant** | Organization or customer scope owning data/configuration | Company A, seller B, workspace C |
| **User** | End user or member of a tenant | Accountant at Company A |
| **Principal** | Authenticated identity performing an action | User, service account, workload identity |
| **Tenant membership** | Relationship between a principal and a tenant along with role/status | User 123 is an admin of tenant A |
| **Tenant context** | Set of verified information used to process a request within a tenant scope | Tenant ID, actor, roles/scopes, request ID, policy version |
| **Resource owner** | Tenant or scope owning the accessed resource | Booking 987 belongs to tenant A |

A user can belong to multiple tenants. A service-to-service call might not represent a specific user but must still run within an authorized tenant context. A resource ID does not by itself prove access rights or tenant ownership of the resource.

### Relationship to Maintain

~~~mermaid
flowchart TD
    USER["User / workload principal"]
    AUTH["Authentication"]
    MEMBERSHIP["Tenant membership / service grant"]
    TENANT["Selected tenant"]
    POLICY["Authorization policy"]
    RESOURCE["Tenant-owned resource"]
    USER --> AUTH
    AUTH --> MEMBERSHIP
    MEMBERSHIP --> TENANT
    TENANT --> POLICY
    POLICY --> RESOURCE
~~~

This diagram illustrates a conceptual verification path. In practice, authorization must combine principal, tenant membership, action, resource ownership, tenant status, and other policy conditions.

## 2. Tenant ID Is an Identifier, Not Proof of Permission

A tenant ID may be a UUID, internal slug, or system-issued identifier. It helps partition data and route requests. However, if a client sends `tenantId=tenant-A`, the server must never assume the caller has permission to access tenant A.

A common mistake:

~~~http
GET /api/invoices/INV-001
X-Tenant-ID: tenant-A
Authorization: Bearer <user-token>
~~~

If the server simply reads `X-Tenant-ID` and queries the invoice by ID, a user can change the header to another tenant to attempt unauthorized data access. This is a variant of insecure direct object reference (IDOR) / tenant isolation failure.

Rules:

- A client-supplied tenant ID is only the **requested tenant selection**, not an authentication source.
- The server authenticates the principal and verifies the principal has a valid membership/grant for that tenant.
- Resources must be verified to belong to the tenant within the same query/authorization scope.
- Every downstream service receives context from a trusted source or re-verifies credentials/delegation.
- Never allow request bodies, query parameters, or arbitrary headers to overwrite an established tenant context.

### An Identifier Is Not a Secret

Hard-to-guess UUIDs help reduce enumeration but do not replace authorization. Tenant IDs may appear in URLs, logs, or events; do not treat keeping the ID secret as an access control layer.

### Canonical Tenant ID

A tenant may have a display name, slug, custom domain, and multiple aliases. The system should have an immutable internal ID as the key linking data; slugs/domains are only lookup names and may change. When a tenant changes its name or domain, you should not have to migrate all data simply because an external identifier changed.

## 3. Determining the Tenant at the Entry Point (Tenant Resolution)

A request may identify a tenant via:

- A tenant selected in the session or user interface.
- A subdomain/custom domain, e.g., `acme.example.com`.
- A path segment, e.g., `/tenants/{tenant}/...`.
- A claim inside an access token.
- An internal header between services.
- A mapping from a client/application registration to a tenant.

There is no single right method for every product. Regardless of the method used, the server must verify the mapping and membership before creating a trusted tenant context.

### Recommended Resolution Flow

1. **Authenticate principal:** validate token/session, issuer, audience, expiry, signature, and required claims.
2. **Resolve tenant candidate:** extract the tenant from host/path/session/claim/client registration per contract.
3. **Validate tenant:** verify the tenant exists, is active, belongs to the correct environment/region, and is not suspended.
4. **Validate membership/grant:** verify the principal is permitted to operate in that tenant; check role, scope, service grant, and membership status.
5. **Authorize action/resource:** check the specific action on the resource, not just general membership.
6. **Create trusted context:** create an immutable context for the request, attaching actor, tenant, scopes, correlation ID, and policy metadata.
7. **Propagate safely:** pass context across authenticated and authorized calls.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant I as Identity / Membership
    participant S as Service
    C->>G: Request + credential + tenant candidate
    G->>G: Authenticate principal
    G->>I: Validate membership / service grant
    I-->>G: Tenant membership + scopes
    G->>G: Build trusted tenant context
    G->>S: Forward authenticated request/context
    S->>S: Authorize action + resource ownership
    S-->>C: Response
~~~

In some architectures, the gateway only authenticates while services resolve/authorize the tenant themselves. Responsibilities must be clearly delineated so no endpoint skips verification.

## 4. Designing Tokens and Tenant Claims

An access token can carry a tenant claim or membership information, but you need to understand its scope and when the claim is valid.

Illustrative payload example (not a usable token):

~~~json
{
  "sub": "user-123",
  "iss": "https://identity.example",
  "aud": "booking-api",
  "exp": 1795000000,
  "tenant_id": "tn_7f31",
  "scope": ["booking:read", "booking:create"],
  "roles": ["booking_operator"]
}
~~~

Points to consider:

- **Single tenant claim:** suitable when a token represents only one tenant context for its entire lifetime.
- **Multi-tenant membership list:** can bloat tokens, hold stale information, and make rapid role revocation difficult.
- **Tenant selection exchange:** the user authenticates first, then exchanges a token for the selected tenant with a specific audience and scopes.
- **Service identity:** workload tokens can represent a service; a grant must specify on behalf of which tenant and which actions the service may call.

Avoid stuffing the entire tenant list, resource permissions, and detailed policies into long-lived access tokens. Tokens are snapshots of claims at issuance time; memberships/roles may be revoked before the token expires. For sensitive permissions, use short-lived tokens, introspection/revocation, server-side policy checks, or equivalent mechanisms.

### Issuer, Audience, and Subject

When verifying JWT/OIDC tokens, services must check at least the properties required by contract:

- Valid signature and issuer key.
- Issuer matches a trusted identity provider.
- Audience matches the API/resource server receiving the token.
- Expiration and not-before timestamps.
- Valid subject/principal.
- Scope/role/tenant claims match expected schema and semantics.

Never merely decode a JWT and trust its contents; always verify signatures and claims. A token for API A must not be accepted by default for API B if the audience differs.

### Preventing Confused Deputy

A broadly privileged service can accidentally use its own permissions to access another tenant's resource at a caller's request. This is a confused deputy risk. Downstream services must check the service's and tenant's delegation/grant, rather than relying solely on the service account having broad technical permissions.

## 5. What Is Tenant Context and What Should It Contain?

Tenant context is a runtime object created after authentication and resolution. It should be immutable for the request/job scope, explicitly passed, and structured.

Example fields:

| Field | Purpose |
| --- | --- |
| `tenantId` | Internal immutable tenant identifier |
| `principalId` | Authenticated user/service principal |
| `actorType` | `USER`, `SERVICE`, or delegated actor |
| `subjectUserId` | Original user if a service is acting on behalf of a user and policy permits |
| `scopes` / `roles` | Granted action scopes |
| `requestId` / `traceId` | Cross-system log/trace correlation |
| `authzPolicyVersion` | Policy version or relevant decision metadata if needed for auditing |
| `issuedAt` / `expiresAt` | Context/delegation validity window when serialized |
| `region` / `environment` | Routing and operational scope when needed |

Not every service needs all fields. Minimize sensitive data and avoid propagating unrelated profiles/PII.

### Immutable Context

Once a request is authorized, never allow a function to arbitrarily change the tenant ID on the context. If a workflow genuinely needs to switch to another tenant, it must create a new context via an explicit authorization step and audit it. Never mutate a shared context used by multiple requests/threads.

### Context Is Not Unlimited Permission

Having `tenantId` and roles in the context does not mean a service can access every resource belonging to the tenant. Authorization still needs to evaluate the action, resource, state, and conditions. For example, an operator role may read bookings but not export payment data.

## 6. Propagating Tenant Context Through HTTP and API Gateways

In a service architecture, the gateway is often the entry point for authentication, rate limiting, routing, and generating standard metadata. However, the gateway should not be the sole guarantor of tenant isolation; each service must still protect the data boundaries it owns.

### Internal Headers and Trusted Boundaries

A system may pass tenant context via internal headers such as:

- `X-Internal-Tenant-ID`
- `X-Internal-Principal-ID`
- `X-Internal-Actor-Type`
- `X-Internal-Request-ID`
- `X-Internal-Delegation-ID`

These are only example names for an internal contract, not an HTTP standard. If used:

1. The edge gateway must strip/overwrite headers of the same names sent by Internet clients.
2. Only authenticated workloads inside the private/service network may call internal endpoints.
3. Downstream services must verify the service identity and context origin.
4. Context is signed or encrypted if crossing a trust boundary requiring anti-tampering; key management and expiration are required.
5. Do not pass arbitrary roles/scopes if downstream cannot verify the issuing authority.
6. Do not log access tokens, cookies, or sensitive context payloads.

### Never Use Headers as Proof Without Channel Authentication

Private IPs or internal DNS do not by themselves prove a caller is trustworthy. If an attacker can call a service directly or compromise a workload in the cluster, they can forge tenant headers. Use mTLS/workload identity, service-to-service authorization, and network policies; downstream services should accept context only from authorized callers.

### Shared Responsibility Between Gateway and Service

The gateway can verify tokens and tenant membership and then forward context. The service must still:

- Verify the caller is an authorized calling service.
- Check delegation/tenant grants if required by contract.
- Verify the resource belongs to the corresponding tenant.
- Enforce action-level permissions.
- Never trust tenant data in the request body if it conflicts with the authenticated context.

## 7. Propagating Context Across Services and Preventing Confused Deputy

One service may call another using its own service identity. You must identify whether the service is acting:

- On behalf of a user (on-behalf-of/delegated).
- On behalf of a tenant under a machine-to-machine grant.
- With system privileges not tied to a specific tenant.

These three cases differ in principal, audit trail, and permission scope. Never collapse them into a single system-wide admin service account and let every downstream service infer the tenant from a header.

### Delegation Context

If Service A receives a user request and then calls Service B, it can pass:

- Original actor: authenticated user.
- Calling service: Service A.
- Tenant context: tenant in which the user is operating.
- Delegation/grant: scope within which Service A is permitted to call B.
- Specific action/scope.
- Target audience/service and expiration.
- Request/trace correlation.

Downstream services should verify that the token/delegation was issued for the correct audience. A token used between A and B does not automatically grant permission to call C without an appropriate delegation.

### Token Exchange and On-Behalf-Of

Some identity platforms support token exchange / delegated tokens. Service A presents the original token and requests a short-lived token scoped for Service B's audience with narrow scopes. This reduces the need to pass all claims manually via unprotected headers. Flow details depend on the identity provider and standard/product support.

Never forward raw access tokens to every service if the token has the wrong audience or contains broader permissions than needed. Never write tokens into queues or logs; for long-running jobs, use a separate service credential and store a revocable reference/delegation per policy.

### Auditing the Actor Chain

Audit logs should distinguish:

| Field | Example |
| --- | --- |
| `actor` | `user-123` |
| `caller_service` | `booking-api` |
| `effective_tenant` | `tn_7f31` |
| `action` | `invoice.export` |
| `resource` | `invoice-001` |
| `delegation_id` | `del-81` |
| `request_id` | `req-xyz` |
| `decision` | `allow` |

This way, when a service has permission to execute an action, operations teams still know who initiated the action and which service executed it. Audits must be tamper-resistant and follow data retention policies.

## 8. Propagating Tenant Context Through Asynchronous Queues and Events

An HTTP request ends, but work may continue through a queue. The consumer no longer has the original request thread or connection; tenant context must be stored in the message envelope or a secure reference.

~~~mermaid
flowchart LR
    API["API service"]
    DB["Transaction + outbox"]
    Q["Message broker"]
    WORKER["Background worker"]
    STORAGE["Tenant-scoped storage"]
    API --> DB
    DB --> Q
    Q --> WORKER
    WORKER --> STORAGE
~~~

### Event Envelope

An illustrative envelope:

~~~json
{
  "eventId": "evt-91",
  "eventType": "invoice.export.requested",
  "tenantId": "tn_7f31",
  "actor": {
    "type": "USER",
    "id": "user-123"
  },
  "delegationId": "del-81",
  "correlationId": "req-xyz",
  "occurredAt": "2026-11-18T10:20:30Z",
  "schemaVersion": 2,
  "data": {
    "exportJobId": "job-55"
  }
}
~~~

Not every event requires a user actor; service-generated schedules or system events can have their own actor type. Payloads should carry only necessary metadata, never embedded access tokens or secrets.

### Consumers Must Verify the Envelope

Consumers should check:

1. The event came from a trusted broker/topic/subscription.
2. The producer identity is authorized to emit this event type.
3. The tenant ID is an internal canonical ID and exists / is in a valid state.
4. The event schema/version is valid.
5. The tenant and actor/delegation align with the requested operation.
6. The job/resource is queried within tenant scope.
7. Idempotency/event ID prevents duplicate processing.

You cannot blindly trust a `tenantId` field simply because it sits in queue JSON. If a producer is compromised, consumers still need least-privilege permissions and resource ownership checks.

### Long-Running Jobs and Expired Context

Never store long-lived user access tokens in messages for workers to use hours or days later. Tokens may expire or be revoked while the message sits in the queue. Instead:

- Store the operation/job ID and canonical tenant ID.
- Store necessary audit actor/delegation references.
- Workers use their own workload identity and check whether the job grant is still valid.
- If user permissions must continue to hold, define a reauthorization policy when starting/executing each step.
- Optionally require user re-confirmation for sensitive operations.

A job's context should have an expiration and state; if the tenant is suspended or permissions are revoked, the worker must check policy before the next side effect.

## 9. Propagation Across Workflows and Sagas

Multi-step workflows can span multiple services and long durations. Each step needs the appropriate tenant context and actor lineage alongside the workflow ID and state version.

A booking saga may call Inventory, Payment, Booking, and Notification. Commands/events need:

- The same verified tenant context.
- A correlation/workflow ID linking the entire chain.
- Actor/delegation if the action originated from a user.
- Command ID / idempotency key.
- Version/state to prevent out-of-order processing.
- Policy rechecks at sensitive steps.

### Compensation Must Never Cross Tenants

When a saga fails, compensating actions such as releasing a reservation or issuing a refund must use the exact original tenant and resource. Never pull the tenant from an unrelated new message or from mutable global workflow state that could be overwritten. Store the tenant owner in an immutable workflow record; re-validate it when executing compensation.

### Scheduled Jobs

Periodic jobs may run for all tenants. Never create an empty context, query all data, and rely on code at every step remembering to filter. A safer pattern:

1. The scheduler generates the list of eligible tenants.
2. Emit an independent job per tenant or clearly bounded batch.
3. Each worker creates its own tenant-scoped context.
4. Queries, cache keys, storage paths, and logs all carry tenant scope.
5. One tenant's failure must not leak data to or inadvertently block other tenants.

If batching multiple tenants, bound concurrency and control context switching; never reuse a mutable context between two tenants.

## 10. Context in Threads, Async, and Reactive Execution

In Java applications, request context may be held in parameters, scoped objects, framework contexts, or thread-locals. The implementation must fit the concurrency model.

### Prefer Explicit Passing

A function can accept `TenantContext` as a parameter:

~~~java
public Invoice getInvoice(
        TenantContext context,
        InvoiceId invoiceId
) {
    authorization.require(
            context.principalId(),
            context.tenantId(),
            "invoice:read",
            invoiceId
    );

    return invoiceRepository.findByTenantAndId(
            context.tenantId(),
            invoiceId
    ).orElseThrow(InvoiceNotFoundException::new);
}
~~~

This is an illustrative example; `TenantContext` and the authorization service are application-defined components. Explicit passing makes dependencies visible and testing easier compared to reading the tenant from a global variable.

### Limitations of `ThreadLocal`

`ThreadLocal` can be convenient in thread-per-request servlets, but carries risks:

- Thread pools reuse threads; stale context can leak to the next request if not cleared.
- `CompletableFuture`/Executors switching to another thread do not automatically carry `ThreadLocal`.
- Reactive pipelines are not bound to a fixed thread.
- Async callbacks may run after the request has expired or context has been cleaned up.

If the framework provides supported request context propagation, use that mechanism and verify cleanup. Never hand-roll propagation for every executor without testing.

### Context Propagation in Async

When submitting a task, you can capture an immutable snapshot of the authorized context and pass it explicitly with the task. The snapshot should have limited scope, an expiration, and carry no secrets. If the task is long-running or has side effects, the worker must check job state and whether permissions/delegation remain valid rather than using snapshot permissions indefinitely.

### Never Use Mutable Singletons

Never store `currentTenantId` in a field of a singleton service. Concurrent requests can overwrite each other's context, causing cross-tenant data exposure. Context must belong to a specific request/job and be thread-safe in the manner the framework uses.

## 11. Tenant Context in the Database and Query Layer

Tenant context must reach every tenant-scoped data query. Defense in depth is necessary because one query missing a tenant filter can return another customer's data.

### Tenant Discriminator in Shared Schemas

A shared-table schema typically includes a `tenant_id` column in tables storing tenant data:

~~~sql
CREATE TABLE invoice (
    tenant_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id)
);

CREATE INDEX idx_invoice_tenant_status
    ON invoice (tenant_id, status);
~~~

A composite primary key combining `tenant_id` and `invoice_id` clearly identifies scope; queries should filter on both:

~~~sql
SELECT invoice_id, status, total_amount
FROM invoice
WHERE tenant_id = :trusted_tenant_id
  AND invoice_id = :invoice_id;
~~~

`trusted_tenant_id` must come from a verified `TenantContext`, never directly from the request body. Do not query by `invoice_id` alone even if IDs appear globally unique; the tenant predicate provides defense in depth and supports partitioning/indexing.

### Row-Level Security (RLS)

Some databases support row-level security to enforce session/role-based filters at the database layer. RLS can reduce risk if an application query omits a tenant condition, but it must be configured properly:

- Session variables/context must be set securely per transaction/connection.
- Connection pools must reset context before reusing a connection.
- Application roles must not accidentally have privileges to bypass RLS.
- Background jobs and migrations have explicit, audited permissions.
- Test raw SQL, ORMs, stored procedures, and rarely used query paths.

RLS does not replace action-level authorization, nor does it help if the application can arbitrarily set the tenant session variable without authentication.

### Connection Pools and Session Leakage

If using a session variable to restrict the tenant, a connection may be reused by the next request. If context is not reset or a transaction leaks, tenant B's request may run with tenant A's context or vice versa. Use transaction-scoped settings when the database supports them, reset in `finally`/connection lifecycle hooks, and test interleaved tenants on the same pool.

### Composite Foreign Keys

Related tables should preserve tenant ownership in referential relationships. For example, line items referencing an invoice:

~~~sql
CREATE TABLE invoice_line (
    tenant_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    line_id UUID NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id, line_id),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES invoice (tenant_id, invoice_id)
);
~~~

Composite foreign keys prevent a row from tenant A from referencing an invoice from tenant B inside the database. Apply this consistently to relations, unique constraints, and joins.

### Repository APIs Should Require Context

Avoid public repository methods like `findById(id)` when data is tenant-scoped. Design methods requiring the tenant:

- `findByTenantAndId(tenantId, id)`
- `listByTenantAndStatus(tenantId, status)`
- `updateByTenantAndId(tenantId, id, version)`

Do not leave it up to controllers to remember adding `WHERE`. Query builders or base repositories can accept `TenantContext` and automatically append predicates, but tests must ensure they cannot be bypassed.

## 12. Cache Keys and Tenant Context

Caching is an easily overlooked boundary. If a key relies solely on a resource ID while the result depends on the tenant, data can be served across tenants.

Example:

- Unsafe when tenant-specific pricing is stored at `price:product-42`.
- Better-scoped key: `price:v3:tenant-17:product-42:currency-VND`.
- Private profile: `profile:v2:tenant-17:user-123`.
- Tenant configuration: `config:v1:tenant-17:feature-set`.

### Components to Include in Keys

Include every factor that changes the output:

- Canonical tenant ID.
- User/principal if the output is personalized.
- Role/permission scope or policy generation if the response depends on permissions.
- Region, locale, currency, customer tier.
- Schema/data version if the payload changes.

Do not mechanically stuff every claim into the key; keys become overly long, cardinality grows, and invalidation becomes difficult. Analyze response variation accurately and construct a stable fingerprint.

### Cache Collisions Between Tenants

When the same product ID appears across multiple tenants with different prices/metadata, cache keys must distinguish tenants. Even when a cache instance is shared, the key namespace still needs scoping. At the same time, authorization must be checked before returning a cache hit; knowing a key does not mean the caller has read permission.

### Invalidation and Context

Invalidation events should include the tenant ID and resource/version. Consumers only delete keys belonging to the matching tenant. If the key schema changes, bridge invalidation across both old and new namespaces during migration. Avoid flushing the entire cache when one tenant updates its configuration.

## 13. Tenant-Scoped Object Storage and File Access

Object storage typically stores files by bucket/container and key. Separation strategies include:

- Separate bucket/container per tenant.
- Separate prefix per tenant inside a shared bucket.
- Separate account/project/storage account for tenant groups.
- Combining shared buckets with separate encryption keys or access points.

### Choosing a Model by Isolation and Scale

| Model | Advantages | Trade-offs |
| --- | --- | --- |
| Bucket/container per tenant | Clearer policies, retention, quotas, and tenant deletion | Many resources, policies, and quotas to manage |
| Prefix per tenant | Easy to scale tenant count and reduces bucket count | IAM/policies must be tight; list/delete prefix carries risk |
| Account/project per tenant | Strong isolation for permissions and blast radius | High operational/control-plane cost, many resources |
| Hybrid tiering | Large/sensitive tenants separated, small tenants shared | Needs placement rules and tenant migration |

### Never Trust Client-Supplied Object Keys

Clients can send a `fileName` or path containing `../`, Unicode confusables, or another tenant's prefix. The server must construct storage keys itself from the canonical tenant ID and object ID; the original filename is only sanitized metadata. Never concatenate a tenant header directly into a path and allow the client to control arbitrary suffixes.

Example logical key:

~~~text
tenants/tn_7f31/invoices/2026/obj_8b2f.pdf
~~~

This key is merely a namespace and does not protect the object by itself. Use IAM/bucket policies, short-lived signed URLs, verify tenant ownership when generating signed URLs, and never let clients pick buckets/prefixes.

### Signed URLs and Delegation

Signed URLs are typically bearer capabilities: anyone possessing the URL within its validity window can perform the signed operation. When generating a URL:

1. Verify tenant context and permissions on the document.
2. The server resolves bucket/key/version from trusted metadata.
3. Restrict HTTP method, content type, size, and expiration if supported by the provider.
4. Audit actor, tenant, resource, and URL expiration.
5. Do not log the full URL since the query string may contain the signature.

If a tenant is suspended or permissions are revoked, previously issued signed URLs may remain usable until expiration or service-level revocation. Choose appropriate TTLs and provide URL controls for sensitive data.

## 14. Tenant Context in Search Indexes and Analytics

Search engines, data warehouses, and analytics platforms often aggregate data from multiple services. This is where tenant boundaries risk being lost because data is flattened, denormalized, or aggregated.

### Search Indexes

Every document/index record must retain tenant ownership or a trusted access scope. Search queries must add a tenant filter from trusted context; never let clients supply arbitrary tenant filters as the source of authorization.

Checkpoints:

- Is the tenant ID written to every document requiring isolation?
- Are search aliases/indexes separated by tenant or do they enforce mandatory filters?
- Do facets, aggregations, autocomplete, and suggestions filter by tenant?
- Do reindex/backfill jobs preserve tenant IDs?
- Do delete/retention requests properly remove all documents/versions of the tenant?
- Do admin endpoints have full-tenant access permissions and corresponding audits?

A common bug is filtering search hits by tenant while total counts, autocomplete, or aggregations still run across the entire index. Statistical metadata can also leak scale, resource names, or behavior of other tenants.

### Analytics and Data Lakes

Ingestion pipelines must attach the canonical tenant identity to events/records, verify producers, and normalize schemas. Query permissions can rely on row-level policies, separate views, or separate datasets/accounts depending on isolation requirements. Do not rely on analysts "remembering to add `WHERE tenant_id`" in every query.

For cross-tenant reports serving platform operators, require dedicated privileged roles, stated purpose, audits, masking, and export limits. Platform-wide visibility should not be the default for analytics service accounts.

### Aggregation and Inferred Data

A dashboard showing only aggregate totals can still leak tenant information if groups are too small or can be reverse-engineered via multi-dimensional filtering. Consider minimum group sizes, masking, aggregation policies, and export controls.

## 15. Tenant Context Across Message Brokers and Dead-Letter Queues

A broker may use a shared cluster for multiple tenants or separate topics/namespaces per tenant. Regardless of the model, producers and consumers must preserve tenant scope.

### Choosing a Topic Model

| Model | Advantages | Risks / Trade-offs |
| --- | --- | --- |
| Shared topic, tenant ID in envelope | Fewer topics/resources, easy to operate at scale | Filters/ACLs and consumer logic must be exact; prone to noisy neighbors |
| Topic per tenant | Clearer per-tenant ACLs and quotas | Large topic counts, complex metadata and consumer management |
| Topic by tenant tier/domain | Balances count and isolation | Requires reliable tenant-to-topic mapping |
| Dedicated broker/namespace for large tenants | Dedicated isolation and capacity | Higher cost and operational overhead |

### Partition Keys and Ordering

Message partition keys can be the tenant ID, aggregate ID, or entity ID. Using tenant ID keeps a tenant's events in the same partition, but one large tenant can create a hot partition. Aggregate ID usually preserves per-entity ordering better and spreads tenants with many entities. Choose based on ordering requirements and load distribution.

Never use a raw client-supplied tenant ID as a partition key before the producer authenticates the context. Use the canonical tenant ID inside events created at a trusted boundary.

### Dead-Letter Queues and Replay

DLQs typically contain raw payloads. They can include PII, invoice data, tenant identifiers, and permission metadata. Requirements:

- ACLs restricting producers, consumers, and operators.
- Appropriate encryption and retention.
- Replay tools requiring selection of tenant/event type and approval when needed.
- Replay consumers still verify tenant ownership and idempotency.
- Audit who views, downloads, or replays DLQ messages.
- Never copy messages into a shared topic that drops the tenant filter.

### Poison Messages

If a message has a malformed tenant ID or a tenant that no longer exists, never fall back to a system tenant or default tenant. Move it to quarantine/DLQ with a reason, alert, and handle per runbook.

## 16. Tenant Context and Region Routing

A tenant may be assigned a home region to satisfy data residency, latency, or ownership requirements. Tenant context may contain a region hint, but the server must verify the mapping from the registry/control plane.

### Tenant Home Region

The registry can map:

| Tenant | Home Region | Data Classification | Status |
| --- | --- | --- | --- |
| `tn-A` | `region-1` | standard | active |
| `tn-B` | `region-2` | restricted | active |
| `tn-C` | `region-1` | standard | suspended |

A client-supplied region must never override the authoritative mapping. If a request arrives at an edge region different from the home region, the gateway can route to the authoritative region or serve read-only per policy.

### Tenant Migration

Migrating a tenant to a new region requires:

1. Freezing/coordinating writes according to protocol.
2. Synchronizing data and verifying replication lag/checksums.
3. Transferring ownership/mapping through an audited control plane.
4. Ensuring service discovery, cache namespaces, queue consumers, and storage policies are updated.
5. Verifying signed URLs, backups, encryption keys, and data residency.
6. Opening writes in the new region and keeping a rollback plan.

Do not merely flip a `homeRegion` field and assume every service routes properly. Caches, queues, search indexes, backups, and scheduled jobs must also know the tenant moved.

### Tenant Suspension and Deletion

When a tenant is suspended, consistent policies are needed for APIs, queues, scheduled jobs, signed URLs, caches, search, and service-to-service grants. Do not merely block UI login; already queued workers could keep processing.

Tenant deletion is a long lifecycle: export/retention/legal hold, deleting source data, replicas, caches, indexes, backups per policy, keys, and audits. A state machine and completion evidence are needed; never execute it with a single `DELETE` on a tenant record.

## 17. Observability: Keeping Tenant Context Without Leaking Data

Tenant context helps investigate incidents, quotas, and noisy neighbors. However, adding tenant IDs to every metric/log can also create high cardinality or leak sensitive metadata.

### Logging

Logs should include essential fields:

- Normalized tenant ID or pseudonymous ID per policy.
- Principal/actor type as needed.
- Service, operation, resource type, decision.
- Request ID, trace ID, delegation ID.
- Status/error category and latency.

Never write access tokens, signed URLs, session secrets, invoice data, or PII into regular logs. Control who can search logs across multiple tenants; platform support accesses require auditing and justification.

### Metrics

Metric labels containing tenant IDs across millions of tenants easily trigger cardinality explosions. Approaches:

- Aggregate metrics by service/region/tier.
- Top-N tenant dashboards with bounded queries without creating unbounded labels.
- Tenant-specific telemetry in a specialized system with separate retention/quotas.
- Pseudonymized identifiers or sampled traces when troubleshooting.
- Separate noisy-neighbor and per-tenant quota metrics in a bounded-cardinality manner.

### Distributed Tracing

Trace context must propagate standard trace/span IDs; tenant metadata may be added to baggage or span attributes per policy. Baggage can propagate downstream and cross trust boundaries if unfiltered. Never put secrets, PII, or full role lists into traces.

### Cross-Tenant Access Auditing

Support/admin actions viewing multi-tenant data must record:

- Operator principal and role.
- Accessed tenant/resource.
- Purpose/ticket or approval.
- Action (read/export/modify/delete).
- Timestamp and outcome.

Avoid relying on ordinary logs as an immutable audit store if actors have permission to modify those same logs; consider exporting to a dedicated audit system.

## 18. Noisy Neighbor, Quotas, and Per-Tenant Rate Limiting

One tenant can generate load far exceeding all others. Even with accurate tenant context, the system still needs to use it to allocate quotas and protect shared resources.

### Quota Dimensions

- Requests per second and bursts.
- Concurrent requests/jobs.
- Storage bytes and object counts.
- Database rows, connections, or query cost.
- Message rates, queue depth, and retention.
- Export/report sizes.
- CPU/memory in dedicated workloads.

### Rate Limiting by Tenant and Principal

Rate limits can be layered:

- Tenant-level limits protect overall resources.
- User-level limits prevent a single user from overwhelming a tenant.
- API/client-level limits protect specific credentials or integrations.
- Resource-level limits protect hot resources.

Do not rely on IP alone because multiple users in a tenant may share NAT, or attackers may rotate IPs continuously. Tenant identity must come from authenticated context.

### Fairness

Some systems use weighted fair queuing or per-tenant worker concurrency so one tenant cannot monopolize the worker pool. Quotas need burst allowances, backpressure, and retry guidance. When returning 429, provide `Retry-After` per contract. Do not apply active-tier quotas to suspended tenants under the same policy.

### Tiering

Small tenants can use a shared pool; large tenants can be separated into dedicated caches/databases/queues or worker pools. Tier upgrades must update mappings and capacity without breaking tenant context or access controls.

## 19. Data Isolation: Shared Schema, Schema per Tenant, and Database per Tenant

Tenant context must be applied consistently whether data is shared or separated.

| Model | Organization | Advantages | Trade-offs |
| --- | --- | --- | --- |
| **Shared tables** | Multiple tenants in the same table, `tenant_id` discriminator | Low cost, easy to scale tenant count | Needs strict query/RLS guardrails; noisy neighbors |
| **Schema per tenant** | Each tenant has its own schema inside one database | Logical boundary and per-tenant migrations | Many schemas, connection/migration overhead |
| **Database per tenant** | Each tenant has its own database | Dedicated isolation, backup/restore, encryption, and tuning | Managing many databases and high cost |
| **Dedicated account/cluster** | Large/sensitive tenants have dedicated infrastructure | Better blast-radius and capacity isolation | Complex provisioning, networking, and operations |
| **Hybrid** | Tenants placed differently based on tier/policy | Balances cost and isolation | Needs reliable abstraction, migration, and registry |

### Tenant Context Is Still Required in Dedicated Models

A separate database does not mean skipping tenant authorization. Services must still verify the requested tenant matches the resolved database endpoint, preventing confused deputy or routing bugs. A forged tenant ID can trick a service into picking the wrong endpoint if registry lookups are unchecked.

### Data Placement Registry

The control plane can manage tenant mappings to databases/schemas/clusters/regions. The registry needs:

- Canonical tenant ID as primary key.
- Versioned mappings and active/migrating/suspended statuses.
- Clear read/write permissions and audited changes.
- Controlled cache TTLs/invalidations.
- Fail-safe behavior when the registry is unreachable; never randomly fall back to a default database.
- Migration, rollback, and reconciliation workflows.

When mappings change, every service must follow the same semantics/version; avoid service A querying the new cluster while service B still writes to the old cluster.

## 20. Case Study: Multi-Company Booking Management SaaS Platform

A SaaS platform has customer companies as tenants. Each tenant has staff, bookings, invoices, custom catalogs, and supporting documents. Staff may belong to multiple companies; some integration partners call the API using client credentials.

Requirements:

- Users can switch tenants in the UI.
- No tenant may read another tenant's invoices.
- APIs can create bookings and export reports asynchronously.
- Supporting documents are stored in shared object storage.
- Some large tenants have dedicated databases.
- Support can investigate incidents, but all tenant accesses must be audited.

### Identity Design

The identity provider authenticates users and issues a user-subject token. A tenant selection endpoint verifies membership and issues a delegated/tenant-scoped token with the booking API audience and required scopes. Clients do not choose their own roles. For integration services, client registrations are mapped to specific tenants and grants.

### Synchronous API Flow

1. Gateway verifies token, resolves tenant, and checks membership.
2. Gateway forwards trusted service credentials/context over an authenticated service-to-service channel.
3. Booking service checks scopes and resource ownership.
4. Repositories always query `tenant_id` alongside booking/invoice ID; RLS serves as an additional layer if supported by the database.
5. Cache keys and object keys include canonical tenant scope.
6. Audits record actor, caller service, tenant, and operation.

~~~mermaid
flowchart TB
    USER["User / integration client"]
    IDP["Identity provider"]
    GW["Gateway + tenant resolver"]
    BOOK["Booking service"]
    DB["Shared DB / dedicated DB"]
    CACHE["Tenant-scoped cache"]
    OBJ["Tenant-scoped object storage"]
    USER --> IDP
    IDP --> GW
    GW --> BOOK
    BOOK --> DB
    BOOK --> CACHE
    BOOK --> OBJ
~~~

### Asynchronous Export Flow

The booking service authorizes the export permission, writes the operation and outbox inside a transaction; the event carries the canonical tenant ID, actor reference, and job ID. Workers use workload identity, check job grants/status, read tenant-scoped data, write files to the tenant's object key, and update the job. A signed URL is generated after verifying the principal has permission to download the report.

Closing the browser does not automatically cancel an accepted export. If the tenant is suspended while the worker is running, the worker checks status before publishing the file; if needed, it stops or quarantines the output per policy.

### Support Flow

Support operators require tenant access tied to a ticket/approval. The system issues short-lived delegation permitting only required actions; all reads/exports are audited. Support roles do not have permission to arbitrarily impersonate users or bypass logging.

### Dedicated Databases for Large Tenants

Large tenants are migrated from the shared database to dedicated clusters. The control plane updates versioned mappings. During migration, services use a tenant-aware routing layer; cutover happens only when data copies/checksums and replication lag meet criteria. Rollback must know which region/database is the current writer to prevent unintended dual-writes.

## 21. Case Study: Service Accounts and Machine-to-Machine Integration

A partner sends booking data via API using client credentials. There is no end user in the request, yet every record still belongs to a tenant.

### Grant Constraints

A client registration maps to:

- Canonical tenant ID.
- Client/service principal.
- Audience of the receiving API.
- Scopes such as `booking:create` and `booking:read`.
- Rate limits/quotas.
- Allowed networks/IPs or mTLS identity if required.
- Credential expiry/rotation and revocation status.

A tenant ID in the partner's payload must never overwrite the tenant bound to the client registration. If an integration is allowed to send for multiple tenants, an explicit grant must restrict selection to an allowlist.

### Never Use an All-Powerful Service Credential

A single API key shared across all customers reduces auditability and increases blast radius. Issue separate credentials per tenant/integration with narrow scopes, independent rotation, and independent revocation. Attach request IDs and idempotency keys to write operations.

### Auditing

The audit actor is the client service principal; the effective tenant is the granted tenant. If there is an originating user in the partner's system, you can record a verified external actor reference, but never treat an arbitrary string in the payload as a trusted identity.

## 22. Workflow for Building `TenantContext`

An implementation should have a clear lifecycle:

1. **Resolve principal:** authenticate credentials and build an immutable principal.
2. **Select tenant candidate:** extract the candidate from claims, domain, path, or service registration per contract.
3. **Validate membership:** verify active relationship and tenant state.
4. **Derive effective permissions:** obtain tenant- and action-specific scopes/roles; never carry permissions over from another tenant.
5. **Bind resource scope:** verify resource ownership or enforce tenant predicates in queries.
6. **Create context:** instantiate an immutable object with request/job ID and expiration.
7. **Propagate:** pass context explicitly or via authenticated protocols.
8. **Reauthorize at boundaries:** queue consumers, scheduled jobs, exports, or sensitive side effects check current grants per policy.
9. **Audit decision:** log principal, tenant, action, resource, and decision.
10. **Cleanup:** when the request/task finishes, clear context from thread/request scope, release references, and prevent reuse.

### `TenantContext` Should Be a Dedicated Type

Do not use an untyped `Map<String,Object>` to hold tenant context. Strong types catch compile-time errors, validate fields, and control serialization. Distinguish between:

- `AuthenticatedPrincipal`.
- `TenantMembership`/`Delegation`.
- Authorized `TenantContext`.
- `ResourceTenantScope`.

This clarifies data state at each step and reduces the risk of passing an unverified tenant candidate as a trusted context.

### Never Arbitrarily Serialize Runtime Context

`TenantContext` may hold object references, internal permissions, or sensitive information. When placing messages on a queue, serialize only a defined event schema; consumers build a fresh context from the verified envelope and current policy. Never use Java native serialization or dump raw runtime objects onto a queue.

## 23. Threat Scenarios and Mitigations

| Scenario | Cause | Mitigation |
| --- | --- | --- |
| Tenant spoofing | Trusting client-sent tenant headers/bodies | Resolve from identity/membership; overwrite headers at trusted gateway |
| IDOR / cross-tenant read | Querying solely by resource ID | Tenant predicates, ownership checks, RLS, and negative tests |
| Confused deputy | Broadly privileged service acting without delegation | Narrow audience/delegation, actor chains, downstream authorization |
| Context leakage | `ThreadLocal`/async context lingering across requests | Immutable request scope, cleanup, explicit propagation |
| Queue poisoning | Consumer trusts tenant ID in payload | Verify producer/topic, schema, tenant state, and resource ownership |
| Cache collision | Keys missing tenant/permission dimensions | Canonical tenant scope in keys, authorization before cache hits |
| Search leakage | Aggregations/autocomplete missing tenant filter | Mandatory tenant filters and testing across all query modes |
| Signed URL leakage | Bearer URLs logged or shared | Short TTLs, log redaction, object/version scoping, audits |
| Support privilege abuse | Broad operator impersonation without audits | Just-in-time access, tickets/approvals, session recording/auditing |
| Noisy neighbor | One tenant exceeds quotas | Per-tenant quotas, fair scheduling, and tier isolation |
| Stale membership | Token claims retain rights after revocation | Short-lived tokens, rechecks/invalidation, sensitive action reauthorization |
| Tenant migration split-brain | Services route to two database writers | Versioned placement registry, cutover protocol, fencing |

### Defense in Depth

No single layer is enough to protect multi-tenancy. A secure request needs:

- Credentials authenticating the true principal.
- Validated tenant selection.
- Action- and resource-level authorization.
- Service-to-service identity/delegation.
- Data query/storage/cache scoping.
- Auditing and observability.
- Negative-path testing and operational revocation/suspension handling.

If one layer fails, the next layer should reduce the likelihood of another tenant's data leaking.

## 24. Tenant Lifecycle: Onboarding, Suspend, Migration, and Deletion

Tenant context must operate alongside the tenant lifecycle. Tenant state can impact every request and job.

### Onboarding

1. Generate a canonical tenant ID.
2. Set domain/slug and provisioning state.
3. Create data placement, schema/bucket/namespace, and encryption policy if needed.
4. Configure quotas/tier, service grants, and default roles.
5. Initialize admin membership via a verified flow.
6. Test isolation and access before activating.
7. Record provisioning audits and operational owners.

### Suspension

Tenant suspension may be triggered by billing, security, legal, or operational reasons. Define:

- Are new APIs rejected or switched to read-only?
- How long do user sessions/tokens remain valid?
- Do running queue jobs continue, stop, or get quarantined?
- How are already-issued signed URLs handled?
- How are scheduled jobs, webhooks, and integration credentials disabled?
- Does support retain read/export access to handle inquiries?

Do not rely solely on an `active` field in a long-lived cache; status changes must propagate to enforcement points within the SLA.

### Migration

A tenant may change regions, database clusters, or tiers. Use a state machine with states such as `PREPARING`, `COPYING`, `VERIFYING`, `CUTOVER`, `ACTIVE_NEW`, and `ROLLBACK`. The placement registry is versioned; services must know the authoritative writer. Use checksums, replication lag checks, write freezes/fencing, and audits.

### Deletion and Retention

Tenant deletion must verify:

- Legal holds/retention and data export obligations.
- Databases, objects, caches, search, analytics, queues, and backups.
- Replicas in other regions and data held by subprocessors.
- Encryption keys and recoverability during hold periods.
- Audits that must be kept after tenant data is deleted.
- Deletion evidence and approvals.

Do not delete audit trails proving data handling merely because the tenant record was deleted. Retain remaining metadata strictly per purpose and policy.

## 25. Tenant Registry and Consistency

The control plane often stores tenant mappings to domains, memberships, regions, databases, tiers, quotas, and statuses. Because this data governs routing and authorization, it requires high reliability.

### Registry Read Path

Caching the registry reduces latency, but stale status can allow a suspended tenant to keep operating or misroute databases. Requirements:

- Versioned records and event-based invalidation.
- TTLs aligned with risk/status-change SLAs.
- Strong-source rechecks for sensitive operations.
- Defined fail-closed or degraded mode when the registry is unavailable.
- Audited updates and optimistic concurrency to prevent overwriting placements.

### Tenant Context Snapshots

Context created at the start of a request may contain a snapshot of tenant status/permissions. If a request runs long, policies may change mid-flight. For long-running operations, recheck at side-effect boundaries or use short authorization leases; you do not need to query membership for every single row of data, but you must define verification checkpoints.

### Cache Invalidation on Revocation

When a user is removed from a tenant:

1. The membership source commits the revoked status/new version.
2. Emit an invalidation event via outbox.
3. Gateway/service caches receive it and evict stale permissions.
4. Tokens/delegations are revoked or expire per policy.
5. New requests are rejected; in-flight requests are handled at side-effect boundaries.

If the system cannot guarantee instantaneous invalidation, document the maximum revocation latency and never use stale caches for high-impact operations.

## 26. Testing Tenant Isolation and Context Propagation

Multi-tenant tests must have distinct data and principals for at least two tenants, then prove no cross-read/write paths exist. Single-tenant happy paths cannot catch missing-scope bugs.

| Test Case | Scenario | Expected Result |
| --- | --- | --- |
| Header spoofing | Tenant A user sends `X-Tenant-ID` for tenant B | Gateway/service rejects without membership/grant |
| Resource IDOR | User A guesses tenant B's invoice ID | Reveals neither content nor sensitive metadata |
| Query missing predicate | Call list/search/report endpoints | Results belong strictly to the tenant context |
| Cache collision | Same resource key in two tenants with different values | Never returns cross-tenant cache entries |
| RLS pool reuse | Interleave A/B requests on a connection pool | Transaction context is reset; no data leakage |
| Async propagation | Submit task A then task B on the same executor | Contexts are never mixed up |
| Queue forged event | Unauthorized producer emits for tenant B | Message is rejected/quarantined |
| DLQ replay | Operator without grant replays tenant A's event | Blocked and audited |
| Signed URL | User A requests URL for tenant B's object | No URL generated |
| Search aggregation | Counts/facets/autocomplete | Aggregates only authorized tenant's data |
| Tenant suspended | Send API calls and process queued jobs | Behavior follows suspension policy |
| Membership revoke | Revoke user while token is still valid | Sensitive actions rejected within SLA |
| Region migration | Change placement while requests are running | No dual-writers or misrouting |
| Support access | Operator opens tenant resource | Full approval, scope, and audit present |
| Noisy neighbor | Large tenant creates bursts | Quotas/fairness protect other tenants |

### Property-Based Isolation Tests

Randomly generate tenants A/B/C, user memberships, resource owners, and actions. For every request, verify invariants:

- No principal reads another tenant's resource without an explicit cross-tenant grant.
- All writes record the tenant owner taken from trusted context.
- Events created from transactions preserve the same tenant ID and aggregate ID.
- Cache keys include all scopes affecting the response.
- List/count/search queries all filter by the correct tenant.
- Suspended tenants produce no new side effects outside policy allowances.

Tests must verify responses, database state, caches, events, object storage, and audits; checking HTTP status alone can miss data leakage via side channels.

### Fuzzing and Negative Tests

Test malformed tenant IDs, slug aliases, case/Unicode variants, missing headers, duplicate headers, expired tokens, wrong audiences, mismatched claims, delegated tokens with wrong audiences, suspended tenants, null contexts, and gateway-stripped headers. Specifically test all paths calling services directly outside the gateway in a controlled environment.

## 27. Hands-On Exercise and Guided Solutions

A SaaS platform has tenant A and tenant B. User Alice is an admin of tenant A, and Bob is a member of tenant B. The Booking service receives requests through the gateway; the Invoice service uses a shared-table database; report exports run via a queue; files are stored in shared object storage. Alice can send a request with header `X-Tenant-ID: tenant-B`.

### Question 1 — How should the gateway handle the tenant header?

**Answer:** Never trust client-supplied headers. The gateway authenticates Alice, resolves tenant candidate B, and checks membership; because Alice does not belong to B, it rejects the request. If the tenant is selected from a single-tenant token claim, the claim must be verified and its audience/expiry must be valid.

### Question 2 — How must the Invoice service protect its queries?

**Answer:** Trusted tenant context is passed from the authenticated caller. Queries mandate `tenant_id` alongside `invoice_id`; composite keys/foreign keys and RLS can act as defense-in-depth layers. Repositories must not expose ID-only query methods for tenant-scoped data.

### Question 3 — Should the worker receiving the export job from the queue trust `tenantId` in the envelope?

**Answer:** Not blindly. Verify the producer/topic, schema, job record, and tenant status; check the export grant and resource ownership. The worker uses its workload identity and reauthorizes at side-effect boundaries. Never store Alice's long-lived access token in the message.

### Question 4 — What should the cache key for an invoice contain?

**Answer:** Canonical tenant ID, invoice ID, schema version, and any dimensions altering response/permissions. Authorization must still be verified before returning a cache hit. Never use `invoice_id` alone if the cache is shared across tenants.

### Question 5 — What controls are needed for signed URLs of invoice files?

**Answer:** The server verifies Alice has permission on tenant A's invoice, retrieves bucket/key/version from trusted metadata, restricts HTTP method and sets a short TTL, audits URL issuance, and never logs the signature. Clients must never supply raw object keys to sign.

### Question 6 — Tenant A is suspended while a report worker is running. What happens?

**Answer:** Per suspension policy: the worker checks tenant status before continuing processing/publishing the file; it can halt or quarantine the output. Do not merely block API logins while letting queued jobs keep exporting data.

### Question 7 — How should support view tenant B's invoice?

**Answer:** Grant just-in-time delegated access backed by a ticket/approval, scoped read-only to the exact resource/scope with a short expiration. Audit operator, tenant, invoice, purpose, and outcome. Never allow arbitrary impersonation or audit bypassing.

### Question 8 — How can context leakage between two requests be detected?

**Answer:** Run concurrent/async tests interleaving tenants A and B on the same thread pool and connection pool; inspect repositories, RLS settings, caches, logs, and events. Context must be immutable/request-scoped and cleaned up after each use.

## 28. Common Mistakes

1. **Trusting client-supplied tenant IDs:** enables tenant spoofing.
2. **Treating UUIDs as authorization:** hard-to-guess IDs do not replace policy.
3. **Checking roles without checking resource owners:** a user may hold a valid role while the resource belongs to another tenant.
4. **Gateway authenticates, but downstream trusts every header:** directly called services or compromised internal callers can spoof context.
5. **Forwarding access tokens without checking audience:** tokens can be replayed against wrong services or hold overly broad scopes.
6. **Using an all-powerful service account for all tenants:** confused deputy risk and massive blast radius.
7. **Serializing full runtime context into queues:** carries secrets/stale claims and lacks clear lifecycle/revocation.
8. **Not cleaning up `ThreadLocal`:** old tenant context leaks into new requests.
9. **Mutable `currentTenant` singletons:** race conditions between concurrent requests.
10. **Querying solely by resource ID:** IDOR / cross-tenant data leakage.
11. **Session-variable RLS without pool reset:** connection reuse leaks tenant scope.
12. **Cache keys missing tenant/permissions:** serves cached data to the wrong tenant.
13. **Accepting object keys from clients:** path traversal/prefix confusion and mis-scoped signed URLs.
14. **Search filters applied only to hits:** counts/facets/autocomplete still leak data.
15. **Queue consumers trusting event payloads:** buggy/compromised producers can write arbitrary tenants.
16. **Tenant suspension only blocking logins:** workers, webhooks, signed URLs, and scheduled jobs keep running.
17. **Unaudited support impersonation:** makes tracing sensitive data access difficult.
18. **Unbounded tenant ID metric labels:** cardinality explosions and telemetry cost spikes.
19. **Migrations updating only the registry:** caches, queues, search, backups, and writer ownership still use old mappings.
20. **Tenant deletion only deleting database rows:** data remains in objects, caches, indexes, replicas, and backups.

## 29. Process for Reviewing Tenant Context Design

During an architecture review, trace the journey of a request rather than merely looking at an identity diagram:

1. Pick a concrete request and identify the originating principal.
2. Point out where the tenant candidate comes from and who verifies membership.
3. Check where context is created, how it stays immutable, and when it expires.
4. Follow the request across every service, queue, and worker; identify how each hop verifies the caller/delegation.
5. Follow the data to databases, caches, search, object storage, and analytics; look for anywhere tenant scope could be dropped.
6. Inspect side effects and retries: is context still valid, and is resource ownership re-checked?
7. Verify logs/traces/audits record actor/tenant without leaking tokens/PII.
8. Trace lifecycle events: how suspend, revoke, migration, and deletion propagate across components.
9. Review negative tests: tenant spoofing, direct service calls, connection pool reuse, forged queue events.
10. Record owners, policies, revocation SLOs, handling RTOs, and review triggers.

### Key Review Questions Requiring Evidence

| Review Question | Evidence |
| --- | --- |
| Who is allowed to select a tenant? | Identity flow, membership policy, tests |
| Who can change tenant context? | API contract, immutable context type, trust boundaries |
| Who do downstream services trust? | mTLS/workload identity, audience, delegation validation |
| Which queries guarantee tenant scope? | Repository contracts, SQL/RLS tests, query reviews |
| How do cache/search/object/queue preserve scope? | Keys/envelopes/schemas/policies and negative tests |
| When permissions are revoked, how fast does it take effect? | Revocation SLA, event/cache invalidation metrics, tests |
| When a tenant is suspended, how are running jobs handled? | State machine, runbooks, worker checks |
| Are operator accesses to tenants audited? | Approval workflow, immutable audit trail |
| Can large tenants impact other tenants? | Quotas, noisy-neighbor dashboards, load tests |
| Do migrations/deletions leave behind copies? | Inventories, registry versions, reconciliation reports |

## 30. Pre-Production Checklist

- Canonical tenant IDs are centrally managed, independent of mutable slugs/domains.
- Tenant resolution verifies principal, membership, status, and service grants.
- Client-supplied tenant candidates are never treated as trusted context.
- Tokens validate signature, issuer, audience, expiry, subject, and scopes.
- Delegation/service identities follow least privilege, exact audience, and clear expiration.
- `TenantContext` is immutable, request/job-scoped, and cleaned up.
- HTTP, async, queues, workflows, and scheduled jobs propagate context via authenticated contracts.
- Database queries are always tenant-scoped; RLS/constraints are configured and tested where applicable.
- Cache keys, search filters, object keys, signed URLs, analytics, and DLQs preserve tenant boundaries.
- Cross-tenant support/admin access requires approval, just-in-time grants, and auditing.
- Tenant status/revocations propagate to caches, tokens, workers, webhooks, and signed URLs within SLA.
- Region/database placements are versioned with clear owners and migration/fencing protocols.
- Quotas/fairness protect other tenants from noisy neighbors.
- Logs/traces/metrics avoid leaking tokens/PII or creating unbounded cardinality.
- Negative tests cover spoofing, IDOR, context leakage, forged events, and pool reuse.
- Runbooks exist for suspension, breaches, tenant migration, exports, and deletion.

## 31. Well-Architected Evaluation

| Pillar | Key Question | Evidence |
| --- | --- | --- |
| **Reliability** | Is context preserved accurately across failovers, queue retries, async paths, and tenant migrations? | Propagation contracts, versioned registry, idempotency, recovery tests |
| **Security** | Is tenant identity verified at every trust boundary and resource scope? | Identity/delegation, IAM, RLS, negative cross-tenant tests, audits |
| **Performance Efficiency** | Do membership/registry lookups, query scoping, and quotas meet latency under heavy load? | Cache policies, p95/p99, per-tenant load tests, connection metrics |
| **Cost Optimization** | Can you run many tenants on shared infrastructure while isolating large tenants appropriately? | Pool utilization, tier costs, noisy-neighbor metrics, placement plans |
| **Operational Excellence** | Can you investigate, revoke, suspend, migrate, and delete a tenant cleanly under control? | Dashboards, runbooks, approvals, audit trails, reconciliation |
| **Sustainability** | Are tenant resources and data created, retained, moved, and deleted purposefully? | Lifecycle policies, quotas, retention, deletion evidence |

A solid tenant context design ensures uniform semantics end-to-end: **which principal is acting, which tenant defines the effective scope, which permissions are granted, and which resources belong to that scope**. Only when context is verified, securely propagated, re-checked at critical boundaries, and observable can a platform share infrastructure while preserving trust boundaries between customers.
