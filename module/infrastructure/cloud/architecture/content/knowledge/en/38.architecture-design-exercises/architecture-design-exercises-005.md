# Migrating a Single-Tenant System to Multi-Tenant SaaS

## 1. Design Problem and Learning Objectives

In the **CLOUD_ARCHITECTURE** module, cloud application architecture starts from business requirements, then moves to selecting networking, compute, data, and deployment models. This exercise in the **Design Exercises** chapter asks you to evolve an application serving a single customer/organization (**single-tenant**) into a **multi-tenant Software as a Service (SaaS)** platform where multiple organizations share the same product with controlled levels of isolation and service.

A **tenant** is the organizational/customer boundary across which the platform manages identity, access control, data, configuration, resource consumption, cost, and lifecycle. A tenant does not necessarily correspond one-to-one with a single user, a single database, a single cloud account, or a single hostname.

A successful migration is far more than adding a `tenant_id` column to tables. The architect must prove:

- **Isolation:** tenant A cannot read, modify, export, or infer tenant B's data across APIs, databases, caches, search, files, background jobs, and observability.
- **Reliability:** an outage or abnormal load from one tenant does not bring down service for other tenants beyond agreed thresholds.
- **Scalability:** infrastructure handles growth in tenant count and uneven traffic profiles.
- **Security:** identity, authorization, secrets, audit logs, and regulatory requirements are enforced end-to-end.
- **Cost:** costs can be attributed and forecasted, preventing one tenant from consuming unbounded resources.
- **Operations:** onboarding, provisioning, upgrades, monitoring, support, backups, and tenant offboarding can operate at scale.

After this lesson, you will be able to select data and compute isolation models, propose a target architecture, design a safe migration plan, and evaluate the design through Well-Architected perspectives.

## 2. Hypothetical Enterprise Scenario

A company provides order management software for a retail store chain. Today the system serves a single organization:

~~~mermaid
flowchart LR
    U[Staff] --> W[Web / API]
    W --> DB[(PostgreSQL)]
    W --> C[Redis cache]
    W --> Q[Queue]
    Q --> J[Order worker]
    J --> DB
    W --> S[Object storage]
~~~

Initial characteristics:

- The web/API app and workers are deployed as a dedicated environment per customer.
- Each environment uses one database; many queries implicitly assume "all data belongs to one customer."
- Caches, queues, report exports, and object keys lack tenant namespacing.
- Users log in with internal accounts and lack multi-organization membership support.
- Operations must provision infrastructure, deploy updates, and support each customer manually.

The **12-month goal** is to serve 120 organizations, including 10 large high-traffic enterprises. The business wants to cut onboarding time and operate from a shared platform where sensible, while still offering stronger isolation for customers with special requirements.

### 2.1. Input Requirements for Practice

The values below are **assumptions for this exercise** and must be renegotiated with the product owner and operations team in a real project:

| Category | Assumed requirement |
| --- | --- |
| Growth | 120 tenants in year one; 500 tenants after three years |
| System load | 400 requests/second normal peak; 1,000 requests/second burst for 5 minutes |
| Latency | Order-creation API p95 under 300 ms at defined target load |
| Availability | 99.9% monthly SLO for core services, with explicit definitions and exclusions |
| Recovery | RTO 2 hours, RPO 15 minutes for transactional data |
| Isolation | Zero cross-tenant access permitted, including via queries and background jobs |
| Configuration | Each tenant has custom subdomain, branding, quotas, and partner integrations |
| Commercial | Standard and Enterprise tiers; must meter usage and convert to invoices |
| Compliance | Some customers require data in a specific region; validate contracts |
| Deployment | Able to release multiple versions per week without per-tenant manual config |
| Operations | Per-tenant incident lookup, load isolation, and isolated service suspension |

**Required deliverables for this exercise:** architecture decision record, target-state diagram, data/isolation model, authentication–authorization flow, data migration plan, test strategy, and estimated budget.

## 3. Clarifying Choices Before Drawing the Architecture

The design team must ask and document answers, as they can alter the chosen option:

1. **Tenant boundary:** is a multi-branch company one tenant or many? Can one user belong to multiple tenants?
2. **Data:** does the system store PII, payment data, or sensitive records? Are there storage residency, deletion window, and export mandates?
3. **Customization:** do tenants differ only by configuration, or do they require custom logic or arbitrary plugins?
4. **Isolation level:** does the Enterprise tier require dedicated databases, encryption keys, networking, or regions?
5. **Performance:** do all tenants share the same SLO? Do a handful of customers drive most of the traffic?
6. **Economics:** is pricing per user, order count, request count, storage, or tier? Who absorbs spike costs?
7. **Operations:** must you suspend, migrate regions, export data, restore, and delete a single tenant without impacting others?
8. **Existing data migration:** how many live databases/customers exist, and are there colliding IDs or diverging schemas?

You cannot evaluate a design accurately without separating **non-negotiable mandates** from tradeable goals. For example, low-cost targets cannot override data isolation requirements.

## 4. Choosing a Multi-Tenancy Model: Silo, Bridge, Pool

Three common patterns exist and can be combined within the same platform:

| Model | Illustration | Pros | Main cons | When to consider |
| --- | --- | --- | --- | --- |
| **Silo** | Each tenant gets dedicated resources, e.g., its own DB or environment | Strong data/resource boundaries, per-tenant customization, small blast radius | Higher idle resources and management overhead | Tenants with strict isolation or compliance demands |
| **Pool** | Multiple tenants share app, compute, and one or more shared tables | Resource efficiency, uniform deployments, fast onboarding | Must enforce isolation at every layer; control noisy neighbors | Many Standard tenants with similar profiles |
| **Bridge** | Share some layers while isolating others | Balances isolation, operations, and cost | Routing complexity and managing mixed topologies | Enterprise tier gets dedicated DBs while sharing the API tier |

These concepts apply per layer: pooled compute with siloed databases, or pooled application tier with dedicated clusters for specific tenant groups.

### 4.1. Three Data Models to Compare

| Data model | Approach | Key considerations |
| --- | --- | --- |
| **Database per tenant** | Dedicated database per tenant | Connection management, fleet-wide upgrades, backup/restore, small-tenant cost |
| **Schema per tenant** | One DBMS, separate schemas | Bulk schema migrations, object limits, permission and connection management |
| **Shared schema with `tenant_id`** | Shared tables; every business row has `tenant_id` | RLS/authorization checks, foreign keys, indexes, and scoping every query |

No model is "automatically safe" by name alone. Even database-per-tenant can leak data through faulty routing, backups, exports, or operator permissions. Shared schemas can deliver strong isolation when defense-in-depth controls are rigorously engineered and tested.

### 4.2. Initial Option Selected for This Scenario

Suppose after evaluation, the team picks a **bridge model**:

- **Standard:** shared API/workers, shared PostgreSQL schema with `tenant_id` and data-layer isolation policies.
- **Enterprise:** same product codebase and single control plane, routing data to dedicated databases when required; compute can also be isolated if SLO/economics justify it.
- **Shared services:** identity, configuration portal, tenant provisioning, metering/billing, monitoring, and release management.
- **Region:** tenants are pinned to approved data regions; data paths and backups follow the chosen residency constraint.

This is a **conditional reference option**, not a blanket prescription for all SaaS apps. A PoC must prove that the shared schema meets isolation and performance targets while Enterprise routing never misroutes a tenant.

## 5. Reference Architecture: Control Plane and Data Plane

~~~mermaid
flowchart TB
    CLIENT[Web / Mobile / API Client] --> EDGE[DNS / WAF / API Gateway]
    EDGE --> AUTH[Identity Provider / Auth]
    EDGE --> API[Stateless API]

    subgraph CP[Control plane]
      REG[Tenant registry / Lifecycle]
      CFG[Plan / Quota / Feature config]
      BILL[Metering / Billing]
      ADMIN[Admin / Audit / Support]
    end

    API --> REG
    API --> CFG
    API --> ROUTER[Tenant-aware data router]
    ROUTER --> POOL[(Shared DB - Standard)]
    ROUTER --> DED[(Dedicated DB - Enterprise)]

    API --> CACHE[Tenant-namespaced cache]
    API --> BUS[Queue / Event with tenant context]
    BUS --> WORKER[Quota- and auth-enforcing worker]
    WORKER --> ROUTER
    API --> OBJ[Tenant-partitioned object storage]
    WORKER --> OBJ

    API --> METER[Usage events]
    WORKER --> METER
    METER --> BILL
    API --> OBS[Metrics / Logs / Traces / Alerts]
    WORKER --> OBS
    REG --> ADMIN
~~~

The **control plane** manages tenants (onboarding, tiers, policies, configs, provisioning, billing, support); the **data plane** processes business transactions and data. Separating the two planes lets teams govern tenant lifecycles and platform rollouts cleanly, though the control plane can become a critical dependency. Decide upfront which state may be cached or kept running if the registry is temporarily unreachable.

For instance, authenticated requests might use short-TTL cached tenant config if policy permits; however, **suspended** transitions or permission revocations need prompt invalidation to avoid overrunning compliance limits.

### 5.1. Request Flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant G as Gateway
    participant A as API
    participant I as Tenant registry/IAM
    participant D as Data access
    participant DB as DB
    U->>G: HTTPS + access token
    G->>A: Forward request + verified claims
    A->>I: Verify user belongs to selected tenant
    I-->>A: Tenant context / plan / permissions
    A->>A: Enforce action permissions and quotas
    A->>D: Pass verified tenant context
    D->>DB: Query within tenant boundary
    DB-->>D: Tenant-scoped data
    D-->>A: Result
    A-->>U: Response
~~~

The tenant identifier may come from a hostname, path, parameter, or UI organization switcher. **Never trust `tenant_id` merely because the client sent it.** The backend must verify the chosen tenant against membership records, tenant status, and caller permissions.

## 6. Identity, Authorization, and Tenant Context Model

Distinguish three concepts:

- **Identity:** who is calling? E.g., user ID or service identity.
- **Tenant context:** on behalf of which organization is the call acting?
- **Authorization:** given current roles/permissions, what may the caller do to resources in that organization?

One user can be an admin in tenant A, staff in tenant B, and have zero access in tenant C. Do not lock each user to a single tenant if multi-org access is needed.

Example entities:

| Entity | Core fields | Role |
| --- | --- | --- |
| `tenants` | `id`, `status`, `tier`, `region`, `created_at` | Defines organization and policies |
| `users` | `id`, `identity_subject`, `email` | Global user identity |
| `memberships` | `tenant_id`, `user_id`, `role`, `status` | Binds users to tenants and roles |
| `service_identities` | `id`, `tenant_scope`, `permissions` | Scoped machine-to-machine integration |
| `api_keys` | `id`, `tenant_id`, `scopes`, `expires_at`, `revoked_at` | Managed tenant API keys with clear lifecycles |
| `audit_events` | `tenant_id`, `actor_id`, `action`, `target`, `timestamp` | Audits modifications and access |

**Recommended flow:**

1. Validate tokens for issuer, audience, signature, expiration, and session policies over TLS.
2. Identify the target tenant; backend verifies the caller is authorized to select that tenant.
3. Compute effective permissions from memberships/roles and resource-level policies.
4. Construct a trusted tenant context (`tenant_id`, user/service ID, permissions, correlation ID) and propagate it through the app stack.
5. When calling other services or enqueueing jobs, propagate tenant context via a controlled mechanism ensuring receivers verify origin and cannot tamper with values.
6. At the data tier, enforce tenant boundaries independently of API-layer checks.

**Cross-tenant support access:** operators need diagnostic tooling with a logged justification, approved scope, time-bound access, audit trails, and oversight. Never use a standing superadmin account with blanket access to all tenants.

## 7. Multi-Tenant Data Design with a Shared Schema

### 7.1. Modeling Principles

With a shared schema, every table holding customer-specific data must carry an explicit tenant attribute. A foreign key on `order_id` alone is unsafe if two tenants share predictable or colliding IDs. Enforce composite constraints on `(tenant_id, id)` wherever appropriate.

Minimal PostgreSQL example (data types and indexes tune to actual workloads):

~~~sql
CREATE TABLE orders (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    external_order_no text NOT NULL,
    customer_id uuid NOT NULL,
    amount numeric(18, 2) NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, external_order_no)
);

CREATE TABLE order_lines (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    order_id uuid NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, order_id)
      REFERENCES orders (tenant_id, id)
);

CREATE INDEX idx_orders_tenant_created
    ON orders (tenant_id, created_at DESC);
~~~

That foreign key stops a line item in `tenant_id` A from ever referencing an order in tenant B. Every index, unique constraint, and table partition must reflect per-tenant query patterns; not every index needs `tenant_id` prefixed if proven unnecessary, but uniqueness scopes must be explicit.

### 7.2. Defense-in-Depth with Row Level Security

PostgreSQL supports **Row Level Security (RLS)** as an extra protective layer:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation ON orders
    USING (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    )
    WITH CHECK (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    );

ALTER TABLE order_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_lines FORCE ROW LEVEL SECURITY;

CREATE POLICY order_lines_tenant_isolation ON order_lines
    USING (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    )
    WITH CHECK (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    );
~~~

An application transaction sets the backend-verified context before running queries:

~~~sql
BEGIN;
-- :verified_tenant_id is bound by the backend after authorization,
-- never taken directly from unverified headers or query parameters.
SELECT set_config('app.tenant_id', :verified_tenant_id, true);

SELECT id, amount, status
FROM orders
WHERE tenant_id = :verified_tenant_id;

COMMIT;
~~~

This is an **illustrative pattern**, not a standalone SQL script: `:verified_tenant_id` represents a safely bound driver parameter. The setting is transaction-local and clears on commit/rollback; verify connection poolers, transaction pooling modes, and all other access paths so stale context is never reused.

Mandatory security precautions:

- The application DB role must **not** own the tables, must not be superuser, and must not hold `BYPASSRLS`; prevent bypass via alternate roles, views, or `SECURITY DEFINER` functions lacking checks.
- RLS policies do not verify user membership on their own. The app must set tenant context only after authentication/authorization, and never allow clients to send raw SQL or set context directly.
- Test `SELECT`, `UPDATE`, `DELETE`, and `INSERT` with a valid tenant, wrong tenant, missing context, and under connection pooling.
- Analytics/backup jobs using separate roles or pipelines must be tightly controlled and audited—never reuse global-access credentials inside the API.
- Audit triggers, stored procedures, reporting views, migration scripts, and data exports; each can bypass application-layer checks.

### 7.3. Two Data Paths: Standard and Enterprise

The application should call a unified **data-access abstraction**. The data router reads `tenant_id` from verified context, looks up the controlled tenant registry, and picks the corresponding connection:

~~~text
Standard tenant -> shared DB endpoint -> RLS + tenant-scoped queries
Enterprise tenant -> dedicated DB endpoint -> tenant-specific DB credentials/pool
~~~

Never construct connection strings, schema names, or table names from user-editable tenant IDs. Restrict write access to routing config, manage secrets securely, and fail closed if a mapping breaks. Even when routed to a dedicated database, keep app-layer tenant checks in place in case a routing mapping is misconfigured.

## 8. Isolation Outside the Database: Cache, Queue, Files, and Search

Many cross-tenant leaks originate in auxiliary systems rather than the primary SQL queries.

| Component | Risk | Mitigation |
| --- | --- | --- |
| **Cache** | Two tenants collide on `order:123` and read each other's data | Namespace keys by tenant and data version; authorize before returning |
| **Queue/events** | Worker receives job missing `tenant_id` or acts on wrong tenant | Verified tenant context, event schemas, idempotency, policy-aligned DLQs |
| **Object storage** | Predictable URLs or keys let users download another tenant's files | IAM policies, dedicated prefixes/buckets as required, short-lived signed URLs, auth checks |
| **Full-text search** | Query returns documents from another tenant | Mandatory tenant filters in indexes/queries plus isolation tests |
| **Data warehouse** | ETL drops `tenant_id` or performs cross-tenant joins | Tenant lineage, report access controls, transform and export validation |
| **Logging / tracing** | Logs capture sensitive fields or dashboards expose all customers | Redaction, dashboard RBAC, tenant dimensions, appropriate retention |
| **Webhooks / email** | Callbacks route to another tenant's endpoint | Per-tenant endpoint mapping, signatures, isolated retries, config checks |
| **Feature flags** | Wrong feature or version enabled for a tenant | Scoped flags with audit trails and explicit fallbacks |

**Example cache key:** `tenant:8f...:order:123:version:2`. Key prefixing is only one layer of defense; never skip authorization checks just because a key has a tenant prefix.

**Idempotency:** if the queue redelivers a message, workers must avoid creating duplicate orders. Scope idempotency keys per tenant, define TTLs, and enforce unique constraints in the DB. Never assume a message broker provides "exactly once" semantics across business logic and DB writes without proving it.

## 9. Noisy Neighbors and Resource Allocation

A **noisy neighbor** occurs when one tenant saturates CPU, DB connections, IOPS, cache, or queues, driving up latency for others. Sharing resources lowers costs when managed well, provided contention is measured and bounded.

Recommended throttling layers:

- **Gateway/API:** rate limits and quotas per tenant, user, and operation type, with clear responses when exceeded.
- **Workers:** per-tenant concurrency caps, separated queues or weighted scheduling where appropriate, plus backpressure.
- **Database:** connection caps, expensive-query timeouts, access-pattern indexes, and heavy-query monitoring.
- **Cache/storage:** prevent one tenant from evicting everyone else's cache entries; apply sensible TTLs and quotas.
- **Enterprise tier:** consider isolated instances/clusters or dedicated DBs when SLOs and pricing justify it.

An Enterprise tenant generating 60% of traffic does not automatically require dedicated compute right away; first measure p95/p99 latency of **other tenants while the large tenant spikes** before deciding.

### 9.1. Capacity Allocation Example

Suppose normal load is 400 req/s with a 1,000 req/s burst for 5 minutes. If effective processing capacity while meeting SLOs is 700 req/s, queue accumulation during the burst is roughly:

**(1,000 − 700) × 300 seconds = 90,000 requests**

This math holds only if those transactions are eligible to queue and arrivals remain steady. Synchronous APIs with timeouts will fail before a queue absorbs that backlog. To evaluate the design, classify which requests **can move asynchronously**, forecast drain time, and load-test realistically.

If post-burst arrival drops back to 400 req/s while processing runs at 700 req/s, theoretically clearing the backlog takes **90,000 / (700 − 400) = 300 seconds**, excluding retries, priority work, and downstream caps. Measure end-to-end business completion latency, not just HTTP 202 response times.

## 10. Networking, Data Regions, Security, and Resilience

Choose regions based on data residency, user proximity, and service availability. Isolate dev/test/prod environments and segment networks. Open only required paths to data tiers; private resources are not automatically safe if IAM or application code is misconfigured.

For SaaS, analyze these failure domains:

| Incident | Potential blast radius | Mitigation strategy |
| --- | --- | --- |
| Single API instance fails | Slice of traffic | Health checks, auto-replacement, sufficient replicas |
| Single zone fails | Apps or DB placed in that zone | Multi-AZ aligned with SLO/RTO; run drills |
| Shared DB exhausts connections | All Standard tenants | Pooling, caps, capacity planning, alerts |
| Tenant submits massive batch | Multiple tenants if contending | Quotas, fair queuing, isolated workers |
| Tenant registry fails | Onboarding and policy-lookup requests | Controlled caching, degraded mode, DR |
| Region outage | All tenants pinned to that region | DR respecting data residency and budget |
| Admin privilege mistake | Multiple tenants | Least privilege, change review, audit, break-glass |
| Restoring shared DB from backup | Risks impacting other tenants | Per-tenant restore tooling and reconciliation |

**RTO 2 hours, RPO 15 minutes** requires concrete test scenarios: which incident, how it is detected, start clock, what counts as lost data, and recovery steps. Automated backups alone do not prove you can restore within RTO. On a shared database, **restoring a single tenant** likely requires controlled extraction and re-import, because restoring the entire database affects every other tenant.

For data residency mandates, account for backups, logs, caches, search indexes, analytics stores, and sub-processors—not just the primary DB location. Verify actual contracts and regulations rather than assuming every customer shares identical obligations.

## 11. Tenant Lifecycle and Control Plane

SaaS must manage each tenant as an entity with explicit states:

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Provisioning: Confirm registration
    Provisioning --> Active: Provision & smoke test pass
    Provisioning --> Failed: Provisioning error
    Failed --> Provisioning: Controlled retry
    Active --> Suspended: Overdue / policy hold
    Suspended --> Active: Valid reinstatement
    Active --> Offboarding: Contract ended
    Suspended --> Offboarding: Contract ended
    Offboarding --> Retained: Retain per policy
    Retained --> Deleted: Retention expired / cleared
    Deleted --> [*]
~~~

Key lifecycle steps:

1. **Onboarding:** verify tenant details, data region, plan, and permissions; create config/keys/registry records; provision DB connections if needed.
2. **Provisioning:** create resources via IaC or idempotent automated workflows; record per-step state and support safe retries.
3. **Activation:** run smoke tests for identity, data isolation, logging, and billing before admitting live traffic.
4. **Plan change:** update quotas/features and effective schedules with full auditability and zero data loss.
5. **Suspend:** block unauthorized operations while respecting contractual export/view rights; clarify whether background jobs pause.
6. **Offboarding:** export data, revoke tokens/keys/webhooks, settle billing, and enforce retention periods.
7. **Delete:** purge per policy across backups, object storage, logs, and legal holds; retain proof of deletion.

**Provisioning must be idempotent:** if DB creation succeeds and DNS creation fails, retrying must never create two tenants or two billing records. Use workflow state, correlation IDs, and compensating actions where needed.

## 12. Upgrades, Configuration, and Per-Tenant Features

With a shared codebase, SaaS gains the ability to ship once for many organizations—but a bug can spread widely too. Therefore:

- Maintain **one codebase** with per-tenant configuration wherever feasible; avoid per-customer code forks without compelling justification.
- Scope feature flags to tenants or tenant cohorts, with clear owners and cleanup deadlines for stale flags.
- Keep database migrations backward-compatible with active application versions during rollout windows.
- Sequence releases: test env → internal tenants → canary cohort → Standard cohort → Enterprise cohort, tuned to risk.
- For dedicated DBs, automate batched schema migrations, track progress, and handle individual tenant failures cleanly.
- Gate customizations behind configuration and sandboxed/quota-limited extension APIs if plugins are supported; never execute arbitrary tenant code with platform privileges.

**Safe schema change example:** add a nullable column, deploy dual-compatible code, backfill in batches, validate, then tighten constraints. Dropping a column in one release will break older running API versions.

## 13. Migration Strategy from Single-Tenant to Multi-Tenant

Never swap the entire application, database, identity, and billing in one big bang without proving the path. Establish **stage gates**:

### Phase A – Discovery and Design

- Inventory tables, keys, APIs, SQL, caches, queues, object storage, reports, and operator accounts that implicitly assume a single tenant.
- Classify every table/dataset as tenant-owned, genuinely global, or intentionally shared.
- Design the tenant registry, identity, memberships, routing mechanism, and data model.
- Plan backup/restore, versioning, observability, metering, residency, and privilege boundaries.

### Phase B – Make the Application Tenant-Aware

- Inject verified tenant context into request pipelines and background jobs.
- Replace raw queries with tenant-scoped repositories/data access; enforce RLS or equivalent DB controls.
- Add `tenant_id` to business tables and create properly scoped composite keys, foreign keys, and indexes.
- Update cache keys, object storage paths, search indexes, webhooks, and events to carry tenant scope.
- Add cross-tenant access tests and role tests.

### Phase C – Data Preparation and First Pilot Tenant

For an initial customer:

1. Assign a **stable `tenant_id`** and map every existing record.
2. Take a backup and test restoring it before backfilling.
3. Backfill in batches, verifying which tables are legitimately allowed to lack `tenant_id`.
4. Reconcile row counts, financial totals, foreign keys, files, and business outputs.
5. Verify legacy queries/workers cannot execute outside a tenant context.
6. Enable strict enforcement only once data and access scoping are proven.
7. Run a monitored canary/pilot with a documented fallback path.

**Warning:** Once the target architecture accepts live writes, rolling back to the old source DB is not a simple DNS flip. You need reverse sync, controlled restore, or forward-fix plans; define the point of no return and who approves it.

### Phase D – Scaling to Many Tenants

- Onboard new synthetic test tenants; actively probe wrong-tenant access to confirm denial.
- Roll out tenancy-aware metering, quotas, and runbooks.
- Test two concurrent tenants, then many tenants with skewed traffic patterns.
- Migrate existing customers in waves, tracking per-tenant health and go/no-go gates.
- Decommission legacy environments only after meeting reconciliation, retention, rollback, and contractual sign-offs.

### Migration Decision Flow

~~~mermaid
flowchart TD
    A[Inventory & target architecture] --> B[PoC tenant isolation + performance]
    B --> C{PoC proves targets met?}
    C -- No --> D[Adjust isolation, routing, or compute model]
    D --> B
    C -- Yes --> E[Add tenant context, schema, and controls]
    E --> F[Backfill + reconciliation + restore rehearsal]
    F --> G{Hard gates passed?}
    G -- No --> H[Remediate and re-verify]
    H --> F
    G -- Yes --> I[Canary first tenant]
    I --> J[Measure SLOs, risks, and data]
    J --> K{Go / No-go}
    K -- No-go --> L[Rollback / forward fix per data state]
    K -- Go --> M[Open multi-tenant waves]
    M --> N[Observe, optimize, and hand over]
~~~

## 14. Mandatory Testing Before Scaling

A multi-tenant test suite must verify both **valid access** and **bypass attempts**.

| Test | How to run | Pass criteria |
| --- | --- | --- |
| Cross-tenant API access | User A requests B's order ID via REST, GraphQL, exports | Zero B content returned; policy-compliant error and audit entry |
| Missing tenant context query | Invoke repository/SQL without valid tenant bound | Cannot read or write tenant rows |
| RLS and pooling | Interleave A/B requests on shared pool at high concurrency | Zero cross-tenant results; no leaked transaction context |
| Foreign keys | Insert tenant A line pointing to tenant B order | Database rejects insert |
| Cache/search | Matching business IDs in A/B, identical search queries | Each tenant sees only its own data |
| Queue and retries | Job A retries while job B runs concurrently and worker restarts | No tenant bleed; duplicates handled per policy |
| Object storage | Attempt to fetch another tenant's URL/key | Denied by IAM policy and app checks |
| SSO/membership | User in A/B selects C or loses revoked permissions | Backend rejects invalid context |
| Rate limits | Large tenant blasts traffic beyond quota | Other tenants hold SLO within test bounds |
| Autoscaling | 400 req/s with 1,000 req/s burst for 5 minutes | p95, error rate, and capacity meet targets |
| Backup/restore | Recover from data corruption and infra loss | Meets RTO/RPO; reconciliation passes |
| Per-tenant restore | Restore one Standard tenant's data | Zero impact or overwrite on other tenants |
| Tenant lifecycle | Fail provisioning mid-flight, retry, suspend | Zero duplicate records or unauthorized access |
| Billing | Replay events, drop events, switch tenant plan | Usage never double-counted and fully traceable |

**Tenant isolation testing** does not stop at GET endpoints. Test less-obvious paths like bulk APIs, reporting, import/export, webhooks, file uploads, admin consoles, and background job privileges.

### 14.1. Illustrative Noisy-Neighbor Scenario

Create three test tenants: A drives 70% of traffic, B and C drive 15% each. Spike A severalfold for a short window while measuring B/C's p95/p99 latency, queue lag, DB connections, and error rate. Define success from product goals—for example, **B/C p95 stays under 300 ms within allowed load**. If it fails, tune quotas, isolate queues/workers, cap DB resources, or introduce tiered compute.

### 14.2. Pre-Go-Live Hard Gates

Do not approve launch on an average scorecard if any of these remain:

- Evidence of cross-tenant access or an unclosed data bypass path.
- Incomplete data reconciliation or untested restore drills.
- Unproven admin security, IAM, secret management, audit trails, or applicable data residency.
- Missing incident response, rollback/forward-fix procedures, or assigned owners.
- Unmeasured SLOs or noisy-neighbor impact under target load.
- Unverified metering/billing accuracy for paid features.

## 15. Observability, Metering, and Operations Support

The platform needs visibility at two levels:

- **Platform-wide:** request rate, p50/p95/p99 latency, error rate, CPU/memory, DB saturation, queue lag, cost, and region health.
- **Per-tenant:** traffic, errors, plan limits, per-tenant-tier latency, onboarding state, cost/usage, and admin audit events.

Attach `tenant_id` to logs, traces, and business events where appropriate, but watch **metric cardinality**. With tens or hundreds of thousands of tenants, avoid emitting high-cardinality time series per `(tenant, endpoint, user)` by default; use sampling, aggregation, or analytics tables. Partition dashboard access too: tenant A users must never view tenant B's logs or sensitive metrics.

**Illustrative SLO:** 99.9% monthly availability for the order-creation API, measured over eligible requests with explicit success definitions and boundaries. Use error budgets to govern release velocity, alerting, and incident response. Different tiers may carry different SLOs and support SLAs, published consistently.

## 16. Cost, Metering, and Unit Economics

Pool models save money by sharing infrastructure, yet variable costs per tenant and usage still need discipline. Separate cost buckets:

| Bucket | Components |
| --- | --- |
| Fixed platform | Gateway, control plane, CI/CD, observability, on-call |
| Per-tenant | Config, baseline storage, emails, keys, support overhead |
| Usage-based | Compute, DB I/O, requests, queues, object storage, data transfer |
| Isolation choices | Dedicated DB/compute/region, isolated backups, private networking |
| Migration | Running dual systems, data backfill, testing, training |
| Risk buffer | Capacity headroom, DR readiness, peak support |

**Hypothetical example** (for calculation practice only, not real cloud provider pricing):

- Shared platform fee: 6,000 currency units/month.
- Per-tenant baseline cost: 30 units/tenant/month.
- Variable usage cost: 0.08 units per 1,000 processed requests.
- 120 tenants generate 48 million requests/month total.

Monthly estimate:

**6,000 + (120 × 30) + (48,000,000 / 1,000 × 0.08) = 13,440 units/month.**

Average is **112 units/tenant/month**, though individual tenants do not actually cost the same. Heavy tenants must be tracked by real consumption—especially DB, storage, bandwidth, and support. If a hypothetical silo model cost 180 units/tenant/month, baseline cost would be **21,600 units/month** before adding other shared platform fees; compare figures only after normalizing service levels and included line items.

**Metering** should emit events with unique ID, `tenant_id`, service type, timestamp, quantity, source, and deduplication rules. Billing needs reconciliation against business transactions; never rely solely on access-log request counts if pricing is based on "completed orders." Set budgets, alerts, and runbooks for tenants driving sudden cost spikes.

## 17. Sample Design Risk Register

Score L (likelihood) and I (impact) from 1–5, using **L × I** to prioritize discussion—do not treat scores as failure probabilities. Legal and privacy risks still require separate hard gates.

| Risk | L × I | Verification / mitigation | Owner |
| --- | ---: | --- | --- |
| Cross-tenant leak from missing SQL filter | 4 × 5 = 20 | RLS, composite FKs, security tests, privilege reviews | Security + DBA |
| Background job runs under wrong tenant | 4 × 5 = 20 | Signed/verified context, event schemas, retry tests | Backend lead |
| Large tenant exhausts shared DB connections | 4 × 4 = 16 | Quotas, pool caps, per-tenant load tests | Platform + DBA |
| Registry misconfiguration routes to wrong DB | 3 × 5 = 15 | Change controls, validated mappings, audit trails | Platform lead |
| Restoring one tenant corrupts another tenant's data | 3 × 5 = 15 | Tenant-restore rehearsals, tooling, reconciliation | DBA + SRE |
| Billing errors from dropped metering or duplicate events | 4 × 4 = 16 | Idempotency, reconciliation, usage audits | Billing owner |
| Schema rollout breaks a subset of tenants | 3 × 4 = 12 | Expand/contract migrations, canary, rollback | Release manager |
| Backups/logs land in wrong data region | 3 × 5 = 15 | Data-flow inventory, policies, compliance reviews | Security + Compliance |

After testing, document **residual risks**, risk acceptors, and review dates. A design that hits performance targets can still be blocked if it lacks isolation or recovery evidence.

## 18. Deliverables for Submission

Use the scenario from Section 2 to complete the tasks below; if you change an assumption, state why and the downstream impact.

### Exercise A – Architecture Definition (30 points)

1. Draw the architecture covering gateway, identity, tenant registry, API, workers, routing, shared/dedicated DBs, storage, billing, and observability.
2. Pick silo/pool/bridge separately for compute and data; justify three critical trade-offs.
3. Describe how tenants route to the right data region and how requests degrade if the registry fails.
4. Pick at least two noisy-neighbor mitigations and define metrics to test them.

### Exercise B – Security and Data (25 points)

1. Design `tenants`, `users`, `memberships`, `orders`, and `order_lines` tables with keys and constraints.
2. Walk through authentication, tenant selection, authorization, and binding tenant context.
3. Explain how caches, queues, files, search, logs, and reporting are protected; write at least five cross-tenant test cases.
4. Propose a backup and **single-tenant restore** strategy inside a shared database.

### Exercise C – Migration Plan (25 points)

1. Build a four-phase roadmap with explicit go/no-go gates.
2. Explain how to backfill `tenant_id`, validate data consistency, and resolve legacy ID collisions.
3. Describe rollback or forward-fix paths once the new system has accepted writes.
4. Plan pilot waves covering internal tenants, opt-in customers, and broader migration cohorts.

### Exercise D – Quality and Cost (20 points)

1. Design load tests at 400 req/s and 1,000 req/s bursts measuring per-tenant SLOs.
2. Rehearse a DB/zone failure proving 2-hour RTO and 15-minute RPO for the scenario.
3. Calculate the hypothetical Section 16 cost; test impact when one tenant grows usage fivefold.
4. Define three service metrics and two alerts, plus two metrics for cost governance.

**Grading bar:** submissions must show sound trust boundaries, consistent isolation, justified trade-offs, measurable test thresholds, an actionable execution plan, and data-backed decisions. High marks elsewhere cannot compensate for security gaps: any option leaking data across tenants is unacceptable.

## 19. Reference Solution and Architecture Decision Record

This is **one reference solution**; learners may choose differently if justified by requirements, cost, and test evidence.

| Decision | Selected direction | Rationale and conditions |
| --- | --- | --- |
| Tenancy model | Bridge | Pooled Standard tier optimizes cost; Enterprise has an upgrade path to dedicated DBs |
| Authentication | Shared IdP, per-tenant memberships | Users can belong to multiple tenants; backend validates selected tenant |
| API and workers | Shared, stateless, tenant quotas | Uniform releases, autoscaling; test noisy-neighbor bounds |
| Standard data | Shared PostgreSQL schema with `tenant_id` + RLS | Efficient operations; requires defense-in-depth and thorough tests |
| Enterprise data | Dedicated DB plus per-tenant secrets/routing | Stronger data isolation and independent recovery; higher cost |
| Cache/files/search | Tenant-namespaced and authorized | Closes commonly overlooked leak paths |
| Tenant lifecycle | Control plane + idempotent provisioning | Fast onboarding, clear audits, controlled failure handling |
| Migration | Backfill, reconciliation, canary, then waves | Lowers cutover risk and catches defects early |
| Reliability | Multi-AZ per requirements and restore drills | Proves RTO/RPO and limits blast radius |
| Cost | Metering + quotas + dashboards | Tracks unit economics and prevents runaway spend |

A concise **ADR** can be written as:

~~~yaml
adr:
  id: ADR-SaaS-005
  title: "Bridge model for multi-tenant SaaS"
  status: proposed
  context: "120 tenants year one, two tiers, needs isolation and faster onboarding"
  decision:
    standard: "Shared application + tenant-scoped shared DB"
    enterprise: "Shared application + dedicated DB when required"
    isolation: ["Backend authorization", "RLS", "tenant-scoped dependencies"]
  consequences:
    benefits: ["Reduced infra duplication", "Fast tenant onboarding", "High-isolation upgrade path"]
    costs: ["Routing complexity", "Cross-tenant test matrix", "Managing migrations across two models"]
  proof_needed:
    - "Zero cross-tenant access across all data paths"
    - "Meets p95 and error thresholds under peak/burst load"
    - "Single Standard tenant restore does not impact other tenants"
    - "Meets contractual RTO/RPO and data residency"
  next_step: "Run isolation and performance PoC prior to pilot"
~~~

ADR conclusions must rest on test evidence rather than assuming cloud features automatically satisfy targets. If the PoC reveals pooled resources fail noisy-neighbor or isolation goals, move contending tenants to data/compute silos or redesign queues and caches.

## 20. Design Completion Checklist

- [ ] Defines what a tenant is, user–tenant relationships, and the trusted source of tenant context.
- [ ] Inventories every data access path, not just the primary API and SQL database.
- [ ] Explicitly selects silo, pool, or bridge per layer with documented rationale.
- [ ] Enforces tenant isolation across API, DB, cache, queues, files, search, webhooks, and analytics.
- [ ] Covers cross-tenant access, job retry, and connection-pooling tests.
- [ ] Implements quotas/rate limits, noisy-neighbor mitigations, and per-tenant SLO tracking.
- [ ] Provides operable onboarding, suspension, offboarding, deletion, and audit workflows.
- [ ] Defines schema/app deployment strategies and multi-tenant canary rollouts.
- [ ] Migration plan covers backups, backfill, reconciliation, cutover, and rollback/forward-fix.
- [ ] Tests backup/restore, RTO/RPO targets, and incident recovery across chosen failure domains.
- [ ] Enforces contractual data residency, including secondary copies and backups.
- [ ] Reviews IAM, secrets, support access, logging, and compliance policies.
- [ ] Models TCO, usage metering, unit economics, and parallel-run migration costs.
- [ ] Residual risks and hard gates have clear owners and sign-offs.
- [ ] Architectural decisions are recorded for verification and future review.

**Key takeaway:** Multi-tenancy is designing **trust boundaries and customer lifecycles across the entire system**. Moving a single-tenant app to SaaS aligns business rules, identity, networking, compute, data, deployment, monitoring, and economics. A strong architecture shares resources where safe, isolates where necessary, and proves its Well-Architected trade-offs with testing.
