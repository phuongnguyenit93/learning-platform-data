# Dedicated Single-Tenant vs. Shared Multi-Tenant Deployment

> **Chapter:** Deployment Models  
> **Scope:** Cloud application architecture design, from business requirements to selecting networking, compute, data, and deployment models. This lesson focuses on choosing tenant isolation levels and evaluating trade-offs across reliability, security, scalability, cost, and operations through Well-Architected thinking.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the difference between **dedicated single-tenant deployment** and **shared multi-tenant deployment**, without confusing tenancy models with public, private, or hybrid infrastructure models.
2. Distinguish **silo, pool, and bridge** deployment patterns and isolation levels across networking, compute, data, encryption keys, and operations.
3. Design tenant boundaries to mitigate data leakage, cross-tenant impact, and **noisy neighbor** effects.
4. Compare options against business requirements, compliance, SLOs, RTO/RPO, scalability, TCO, and operations team capacity.
5. Plan tenant onboarding, upgrades, monitoring, backups, recovery, and migration between models.
6. Document the choice with an Architecture Decision Record (ADR) and define the verification tests required before rollout.

## 1. Foundational Concept: What Is a Tenant?

In a SaaS application or platform serving multiple organizations, a **tenant** is a customer unit or organization with its own data, users, configurations, access permissions, and policies. One tenant may contain thousands of users; conversely, a user may be permitted to access multiple tenants if the business model supports it.

Example: a cloud booking management application serving 50 businesses. Each business is a tenant, and each business's employees are users belonging to that tenant.

Two common deployment choices:

- **Dedicated (single-tenant) deployment:** each tenant receives one or more dedicated deployment components, such as a dedicated application cluster and database. The exact unit of isolation must be explicitly specified: cloud environment, account/subscription, VPC/VNet, cluster, namespace, instance, database, or schema only.
- **Shared (multi-tenant) deployment:** multiple tenants share infrastructure or a single running application instance; the system identifies tenants and enforces access boundaries and resource allocation per tenant.

**The two concepts are not mutually exclusive.** An application may share its identity layer, control plane, or parts of its API while giving large tenants dedicated databases. Therefore, when designing, answer **"shared at which layers, dedicated at which layers?"** rather than merely slapping on a single-tenant or multi-tenant label.

### Do Not Confuse Tenancy with Cloud Deployment Models

- **Public cloud** describes provider-operated infrastructure; you can still run a **single-tenant** deployment inside a dedicated customer account/VPC.
- **Private cloud** describes cloud infrastructure dedicated to one organization; software inside it can still treat multiple departments or business units as separate tenants.
- **Hybrid cloud** refers to combining deployment environments; a hybrid system may use silo, pool, or mixed tenancy patterns.
- **Multi-tenant SaaS** describes how an application serves and isolates customer organizations; running on shared underlying cloud services does not automatically make an application properly multi-tenant.

## 2. Three Tenant Organization Patterns: Silo, Pool, and Bridge

### 2.1. Silo: One Dedicated Application Environment per Tenant

~~~mermaid
flowchart TB
    C["Customers"] --> A["Tenant A"]
    C --> B["Tenant B"]
    A --> AP["Compute / API A"]
    AP --> AD[("Database A")]
    B --> BP["Compute / API B"]
    BP --> BD[("Database B")]
    OP["Automation and observability platform"] -.-> AP
    OP -.-> BP
~~~

Each tenant gets its own deployment "silo." At high isolation levels, silos can span separate cloud accounts/subscriptions, VPCs, clusters, encryption keys, and databases. However, **a dedicated tenant deployment does not guarantee dedicated physical hardware**; managed cloud services may still share the provider's underlying physical hosts.

**Advantages:**

- Convenient when customers require distinct isolation scopes, configurations, data residency regions, or upgrade schedules.
- Easier to contain certain faults and measure direct infrastructure cost per tenant.
- Allows scaling capacity independently for large tenants or applying tenant-specific backup rules.

**Limitations:**

- Fixed costs scale with tenant count, risking wasted capacity when traffic is low.
- Many environments to patch, monitor, test, and configure; high risk of **configuration drift** if deployed manually.
- Onboarding, upgrades, and incident response become complex across hundreds or thousands of deployments.
- Demands consistent access governance and automation across every environment.

Silo fits when strong isolation is contractually or legally mandated, tenants carry heavy loads, deep customization is required, or tenants demand separate data regions and upgrade cycles.

### 2.2. Pool: Multiple Tenants Sharing Application and Resources

~~~mermaid
flowchart TB
    A["Tenant A"] --> GW["API Gateway / Auth"]
    B["Tenant B"] --> GW
    C["Tenant C"] --> GW
    GW --> APP["Shared, tenant-aware application"]
    APP --> DB[("Shared database\nwith tenant isolation")]
    APP --> CACHE[("Shared cache / queue\nwith tenant keys and quotas")]
~~~

In the pool model, tenants are distinguished by authenticated identity and tenant context. APIs, workers, caches, or databases may be shared. The greater the sharing, the more critical **logical isolation controls** become.

**Advantages:**

- Maximizes utilization of idle capacity, especially across many small tenants.
- Single deployment pipeline for shared app components; streamlines bug fixes and rollouts.
- Infrastructure autoscales on aggregate demand, reducing per-tenant standby overhead.

**Limitations:**

- A flaw in tenant checks can leak data across customers.
- One heavy tenant generating high load or data volume can slow down other tenants without quotas.
- Multiple tenants share blast radius when shared application or infrastructure components fail.
- Requires per-tenant usage metering, cost allocation, and data lifecycle management even on shared infrastructure.

Pool fits when many tenants exhibit broadly similar behavior, logical isolation is acceptable, and the team can engineer rigorous multi-tenant protections.

### 2.3. Bridge: Combining Shared and Dedicated Components

~~~mermaid
flowchart LR
    A["Standard tenant"] --> GW["Shared gateway + identity"]
    B["Enterprise tenant"] --> GW
    GW --> S["Shared application"]
    S --> PD[("Pool database\nstandard tenants")]
    S --> DD[("Dedicated database\nEnterprise tenant")]
    B -. "If stronger isolation needed" .-> D["Dedicated app / VPC"]
    D --> DD
~~~

**Bridge** combines pool and silo. For example, login, billing, and catalogs are shared, while enterprise tenant transactional data sits in dedicated databases. For tenants with strict mandates, compute, networking, and databases can all be split out of the pool.

Bridge enables tiered service offerings, yet increases routing, provisioning, authorization, schema versioning, and multi-mode operational overhead. Clarify **what remains shared**, because a dedicated database alone does not satisfy a "no shared compute" mandate if the application still runs in a shared pool.

### 2.4. Quick Comparison Table

| Criterion | Silo (Dedicated) | Pool (Shared) | Bridge (Hybrid) |
| --- | --- | --- | --- |
| Isolation scope | Can be high if compute, network, data, and IAM are split | Mostly logical isolation; requires multi-layer enforcement | Varies by service and tenant tier |
| Fixed cost per tenant | Typically high | Typically low as tenant count grows | Intermediate; adds cost to support both modes |
| Software releases | Many environments; requires version tracking | One or a few shared clusters | Multiple release streams to coordinate |
| Complexity at scale | Grows with environment count | Grows with sophistication of tenant controls | Grows because both mechanisms coexist |
| Cross-tenant blast radius | Well-contained if isolated deeply | Larger blast radius on shared tiers | Depends on resource boundaries |
| Per-customer customization | Relatively easy, but risks code branching | Prefer safe configs/feature flags | Varies by customer tier |
| Cost attribution | Relatively direct for dedicated parts | Requires usage metering and allocation rules | Must combine both approaches |
| Tenant portability | Depends on dedicated-env automation | Needs tooling to extract one tenant's data | Needs tier-transition workflows |

These traits reflect general tendencies, **not absolute technical guarantees**. For instance, silos sharing one cluster do not automatically have a smaller blast radius than a pool partitioned into isolated cells.

## 3. Choosing Isolation Levels per Architectural Layer

"Shared vs. dedicated" is multi-dimensional. You can structure an isolation matrix like this:

| Layer | Shared / Logical Isolation | Stronger Isolation | Design Questions |
| --- | --- | --- | --- |
| **Identity** | Single login service with tenant-aware policies | Dedicated identity realm/provider if mandated | Who asserts which tenant a user belongs to? |
| **Networking** | Shared VPC/VNet with policy-enforced traffic | Dedicated VPC/VNet or cloud account with controlled links | Does the tenant require private networking or region pinning? |
| **Compute** | Shared services, pods, or serverless runtime | Dedicated namespace, node pool, cluster, or deployment | Where are CPU, memory, concurrency, and autoscaling caps enforced? |
| **Data** | Shared tables with tenant ID and policies | Dedicated schema, dedicated database, or dedicated data account | Can we prove zero cross-access and per-tenant recovery? |
| **Cache / queue** | Shared infrastructure with tenant-prefixed keys, partitions, and quotas | Dedicated instance/namespace/queue | Can one tenant fill the cache or choke the queue? |
| **Encryption keys** | Shared KMS with strict policies | Customer/tenant-specific keys, sometimes dedicated KMS account | Who manages permissions, rotation, revocation, and key audits? |
| **Monitoring / ops** | Shared observability platform tagged with tenant ID | Dedicated dashboards, log boundaries, ops teams, or upgrade windows | Can logs, costs, incidents, and sensitive data be segregated? |
| **Recovery** | Restore entire pool or cell | Tenant-specific backups, restores, and RTO/RPO | Can we restore one tenant without overwriting others? |

Isolation is **a spectrum**, spanning multiple tenants sharing one process all the way to each tenant owning a separate cloud account, VPC, compute, and data. Tie choices to the assets being protected and **concrete threat models**. Splitting databases does not stop an API bug from returning the wrong tenant's payload or logs from leaking another tenant's data.

### Physical Isolation vs. Logical Isolation

- **Physical/infrastructure isolation:** separates underlying resources or administrative domains, mitigating certain cross-tenant vectors, yet still requires proper IAM, config hygiene, and access path controls.
- **Logical isolation:** multiple tenants share infrastructure, apps, and data tiers using identity, policies, indexing, and quotas to maintain boundaries.
- **There is no single best isolation level for every tenant.** Choices depend on data sensitivity, SLAs, traffic, contracts, cost, and operational capacity.

## 4. Critical Choices at the Data Layer

Three common patterns exist when tenants share a common data model:

| Strategy | Data Organization | Strengths | Risks / Operational Effort |
| --- | --- | --- | --- |
| **Shared tables + tenant_id** | Single table holds records for multiple tenants | High resource efficiency; one schema to migrate | Every query/auth check must enforce boundaries; indexes and unique keys must include tenant |
| **Schema per tenant** | Each tenant gets a schema in a shared DB | Separates namespaces; migrations can be batched | Many schemas complicate migration tools/connections; still shares DB compute/IO |
| **Database per tenant** | Dedicated database, possibly on shared server/cluster | Simplifies per-tenant backups and DB permissions | Connection counts, migrations, cost, and ops grow; shared servers still share CPU/IO |

**A dedicated database does not automatically mean a fully isolated environment:** multiple databases may live on the same DB host or managed cluster. Conversely, a shared database can satisfy strict requirements if logical isolation, testing, and access controls are executed rigorously.

With shared tables, you typically must:

1. Store an **immutable `tenant_id`** on every tenant-scoped business record; every relevant unique constraint and foreign key must include tenant scope to prevent cross-tenant references.
2. Verify **tenant membership** before querying; never trust a tenant ID taken directly from arbitrary headers or request parameters.
3. Enforce protections **at the data layer** (such as row-level security where the DB supports it) alongside API/service-layer checks.
4. Include tenant scope in cache keys, object storage paths/prefixes, events, async jobs, and search indexes.
5. Test less-traveled read/write paths: reports, exports, background jobs, webhooks, customer support tools, and operational ad-hoc queries.

### Example: Implementing PostgreSQL Row-Level Security (RLS)

The SQL snippet illustrates **defense in depth** for shared tables. This is not a complete production configuration.

~~~sql
CREATE TABLE bookings (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    booking_code TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE (tenant_id, booking_code)
);

-- app_role is an application role granted appropriate permissions.
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_bookings_policy
ON bookings
FOR ALL
TO app_role
USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
)
WITH CHECK (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);
~~~

Inside the application, after **authenticating identity and verifying tenant membership**, the backend binds the tenant context to **each transaction** before executing business queries:

~~~sql
BEGIN;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
SELECT id, booking_code, status FROM bookings;
COMMIT;
~~~

**Critical safety conditions:**

- The `tenant_id` value must be resolved by the backend from verified identity and membership records, never from unvalidated client input.
- The application DB role must never hold superuser or `BYPASSRLS` privileges. Table owners bypass RLS unless `FORCE ROW LEVEL SECURITY` is set; admin/migration tasks need separate controlled roles.
- `SET LOCAL` scopes the setting to the current transaction, preventing stale tenant context from leaking across pooled connections. Verify exact behavior with your connection pooler, transaction pooling mode, and ORM.
- Custom config variables like `app.tenant_id` can be modified by application SQL; RLS **does not replace** SQL injection defenses or authentication/authorization systems.
- All queries, `SELECT/INSERT/UPDATE/DELETE` paths, joins, foreign keys, imports/exports, logs, and background jobs still require independent testing.
- Missing tenant context must **deny access by default**; never implement a fallback where "empty tenant means all data."

## 5. Security: Protecting Tenant Boundaries End-to-End

The greatest risk in shared models is **cross-tenant access**, where a request, job, or config from Tenant A touches Tenant B's data or resources. Adding `tenant_id` to database tables solves only part of the problem.

A trustworthy access flow:

~~~mermaid
sequenceDiagram
    participant U as User
    participant I as Identity Provider
    participant G as Gateway / API
    participant S as Tenant-aware Service
    participant D as Database
    U->>I: Login
    I-->>U: Auth token / session
    U->>G: Request with token
    G->>G: Verify signature, expiry, audience
    G->>S: Authenticated identity
    S->>S: Verify tenant membership & role permissions
    S->>D: Query with tenant context + policy
    D-->>S: Authorized data only
    S-->>U: Response
~~~

Minimum controls to evaluate:

- **Authentication ≠ authorization.** A valid login does not prove permission on the selected tenant; multi-tenant users must be authorized per tenant.
- **Propagate tenant context securely** across APIs, workers, message queues, webhooks, and admin tools. Never treat a tenant ID in a payload or URL path as proof of access rights.
- **Least privilege** for service identities, cloud IAM, database roles, and support access; govern privileged access with auditing.
- **Encrypt data** in transit and at rest; manage keys, secrets, and certificates by policy. Tenant-specific keys increase isolation while adding operational cost and complexity.
- **Govern copied data:** backups, replicas, object storage, logs, traces, analytics, and third-party tools must obey data residency scopes and retention rules.
- **Test cross-tenant attacks:** attempt reading, modifying, deleting, and enumerating IDs belonging to other tenants; test cache poisoning, object access, exports, and background jobs.
- **Govern support operations:** customer support sessions require explicit authorization, time limits, audit logging, and must avoid blanket admin keys/roles for routine work.

For customers demanding **dedicated deployment**, clarify exact contractual expectations: "dedicated database", "dedicated compute", "isolated network", "dedicated cloud account", "dedicated support staff", and "dedicated storage region" are all distinct requirements.

## 6. Performance, Noisy Neighbors, and Reliability

### 6.1. What Is a Noisy Neighbor?

One tenant imports 10 million records or runs a heavy report, saturating shared CPU, IOPS, connection pools, queues, or service quotas. Other tenants' requests slow down even though their traffic did not change. This is the **noisy neighbor** problem.

Common mitigations:

- Enforce per-tenant or per-tier limits on **requests/sec, concurrency, storage, execution time, and job counts**.
- Use **fair scheduling**, partitioned queues, circuit breakers, bulkheads, and backpressure to stop one tenant from starving shared capacity.
- Set DB connection/statement timeouts, guard heavy queries, index for tenant-scoped access patterns, and isolate analytics jobs from online transactions.
- Autoscale on aggregate load **plus** real saturation signals (latency, queue age, resource saturation); adding pods alone will not fix a saturated shared database.
- Move heavy tenants into dedicated cells/clusters when economics and operational reality warrant it.

### 6.2. Blast Radius and Cell-Based Architecture

A shared model can shrink blast radius by partitioning into **cells**: each cell serves a subset of tenants with dedicated app clusters and data stores, while the control plane may remain shared.

~~~mermaid
flowchart TB
    GW["Tenant Router / Control Plane"] --> C1["Cell 1: Tenant group A"]
    GW --> C2["Cell 2: Tenant group B"]
    GW --> C3["Cell 3: Tenant group C"]
    C1 --> D1[("Data 1")]
    C2 --> D2[("Data 2")]
    C3 --> D3[("Data 3")]
~~~

Cells contain application and data outages to one tenant group; however, shared components such as identity, DNS, control plane, or billing can still become common failure points. Cell partitioning must include real **recovery, routing, and operational isolation**—not just logical labels.

### 6.3. Per-Tenant SLOs, SLAs, RTO, and RPO

- **SLI:** actual measured indicator, e.g., ratio of valid requests succeeding within target latency.
- **SLO:** agreed internal reliability target, e.g., p95 latency or monthly request success rate.
- **SLA:** contractual commitment; clarify calculation rules and exclusions.
- **RTO:** maximum acceptable time to restore service after an outage.
- **RPO:** maximum acceptable data loss measured in time.

A pool serving multiple tiers can offer differentiated SLOs, **only if the architecture and telemetry genuinely enforce that differentiation**. If everyone shares one database, promising a "5-minute RTO exclusively for Tenant A" without a dedicated recovery workflow is not credible.

**Per-tenant data recovery challenge:** restoring a full shared-DB backup can overwrite other tenants' newer data. Engineer selective recovery workflows (logical export, point-in-time recovery into a staging instance, tenant-filtered extraction, foreign key and event reconciliation) and drill them. Silos must also test backup/restore and failover—separating environments does not automatically guarantee RTO/RPO.

## 7. Cost Analysis and Scalability

Evaluating on single-VM price alone leads to wrong conclusions. Total Cost of Ownership (TCO) must include compute, databases, storage, backups, data transfer, observability, security, licenses, ops labor, deployments, DR, and support.

A preliminary cost model:

\[
C_{\text{silo}} \approx \sum_{i=1}^{N}(F_i+V_i+O_i)
\]

\[
C_{\text{pool}} \approx F_{\text{platform}}+\sum_{i=1}^{N}V_i+O_{\text{shared}}+I
\]

Where:

- \(N\): number of tenants.
- \(F_i\): fixed cost per dedicated tenant (baseline compute, DB, environment).
- \(V_i\): variable cost driven by tenant load/storage.
- \(O_i\): per-tenant operational/deployment overhead.
- \(F_{\text{platform}}\): fixed cost of the shared platform.
- \(O_{\text{shared}}\): shared pool operations.
- \(I\): cost of enforcing and verifying tenant isolation (policies, metering, testing, auditing, governance).

**Illustrative example, not a cloud quote:** 20 tenants with relatively light load.

| Cost Category | Silo (Hypothetical) | Pool (Hypothetical) |
| --- | ---: | ---: |
| Fixed resources | 20 × 100 = 2,000 USD | 900 USD |
| Load-driven cost | 20 × 30 = 600 USD | 20 × 30 = 600 USD |
| Operations and isolation controls | 20 × 40 = 800 USD | 650 USD |
| **Monthly total** | **3,400 USD** | **2,150 USD** |

Under these assumptions, pool saves **1,250 USD/month**. However, the conclusion flips if the pool requires multiple cells, beefier databases, multi-region residency, complex compliance, or suffers multi-tenant outage costs. For silos, shared CI/CD, logging, and automated provisioning also drive operational costs below naive estimates.

### Variables to Include in Your TCO Model

1. **Load distribution:** aggregate traffic is insufficient; inspect concurrent peaks and skew across tenants.
2. **Data growth:** dataset sizes, connection counts, indexes, retention windows, and backup/restore times.
3. **Service tiers:** do premium tenants get dedicated quotas, SLOs, regions, or scaling headroom?
4. **Redundancy and operations:** standby environments, DR drills, security logs, audits, and on-call staffing.
5. **Engineering complexity:** one cross-tenant isolation breach can cost far more to remediate than infrastructure savings.
6. **Non-negotiable mandates:** mandatory security/contract requirements must be satisfied **before** optimizing budget.

Never rely on "cost per tenant" as your sole metric. Track **cost per valid transaction**, resource utilization, margin by tier, and support/ops overhead to avoid local misoptimization.

## 8. Tenant Lifecycle and Operational Workflows

### 8.1. Onboarding and Provisioning

A new tenant needs a **stable tenant ID**, service tier, permissions, and data residency policy—then gets mapped to the right environment, cell, or database.

~~~mermaid
flowchart LR
    A["Customer signs up"] --> B["Create tenant ID and policy"]
    B --> C{"Tier / isolation condition"}
    C -- "Pool" --> D["Assign cell + initialize data/config"]
    C -- "Dedicated" --> E["Provision environment via IaC"]
    D --> F["Configure IAM, quotas, keys, logging"]
    E --> F
    F --> G["Verify permissions, data, and health"]
    G --> H["Activate tenant"]
~~~

The **control plane** manages tenant metadata, provisioning, entitlements, routing, billing, and operations; the **data plane** serves business traffic and tenant data. Separating these responsibilities keeps pool, silo, and bridge consistent. Yet a shared control plane still requires hardening, HA, and DR because its outage impacts many tenants.

### 8.2. Releases and Schema Migrations

- With **pool**, one database migration affects many tenants immediately upon rollout. Use backward-compatible migrations, phased rollouts, load throttling, and safe application rollbacks.
- With **silo**, tenants may sit on different versions. Automate version tracking, batched migrations, and security patching without manual intervention.
- With **bridge**, support schema/database diversity cleanly during releases; avoid scattering customer-specific branches across core business code.

A safe release sequence is **expand → deploy → migrate data (if needed) → contract**: add backward-compatible schema changes first, deploy code compatible with both schemas, migrate data under observation, and remove legacy structures only once unused. Every step still needs a practical rollback plan.

### 8.3. Monitoring and Chargeback/Showback

Collect metrics per tenant (and per cell/deployment): request count, error rate, p50/p95/p99 latency, quota usage, DB size, queue lag, cost attribution, backup failure rate, and incident recovery time. **Guard metric label cardinality**, as attaching every tenant ID to every metric label can explode monitoring costs. Tracing data containing tenant IDs must obey log privacy policies.

- **Showback:** reporting usage/costs for stakeholder visibility.
- **Chargeback:** allocating or billing costs to tenants/business units using approved rules.
- Shared infrastructure costs need transparent allocation rules: by transactions, storage, reserved headroom, or support tier.

### 8.4. Contract Termination, Deletion, and Data Export

Offboarding requires verifying requester authority, exporting data per contract terms, revoking access/tokens/keys, halting scheduled jobs/webhooks, draining queued data, and purging data per retention policy. Backups, replicas, logs, and third-party systems have separate lifecycles that must be inventoried, processed, and evidenced; running a single `DELETE` statement is not completion.

### 8.5. Incident Recovery

Runbooks must distinguish tenant-level, cell-level, and shared-component outages—stating who triggers failover, restore sources, consistency verification, drill-proven recovery times, customer comms, and failback steps. In a pool, testing **single-tenant restore** is just as vital as full-application recovery.

## 9. Decision Framework for Selecting a Model

### Step 1: Gather Requirements and Separate Mandatory Constraints

Interview stakeholders directly:

- **Business/Product:** current/projected tenant count, peak loads, customization needs, pricing tiers, launch timeline?
- **Security/Legal:** which data is regulated, required residency regions, exact contractual definition of "dedicated", who may access data?
- **SRE/Operations:** SLOs, RTO/RPO, tenants needing custom maintenance windows, how many environments can the team operate?
- **Finance:** fixed/variable budget, customer support costs, forecasting/chargeback needs?
- **Engineering:** readiness for tenant-aware design, cross-tenant testing, IaC automation, migrations, observability, and quotas?

Mandatory security or contractual obligations cannot be overridden because an alternative is cheaper. If mandatory conditions clash with budget or schedule, escalate to authorized decision-makers to adjust scope, budget, or timeline.

### Step 2: Compare Options Against Measurable Criteria

| Question | Signal Favoring Silo | Signal Favoring Pool | Signal Favoring Bridge |
| --- | --- | --- | --- |
| Contractual isolation needed? | Explicit compute/network/data separation | Logical isolation accepted with evidence | Multiple customer tiers |
| Tenant count and size? | Few large tenants or wildly skewed loads | Many small tenants with complementary loads | Mix of small and large tenants |
| Customization needs? | Deep customization, separate upgrade schedules | Config/feature flags suffice | Optional enterprise tier customizations |
| Operational readiness? | Strong IaC and multi-environment governance | Strong tenant-aware security, quotas, monitoring | Can operate both patterns plus transitions |
| Data residency needs? | Each tenant needs its own approved region | Tenants share valid regions | Grouped by region/policy |
| Cost objective? | Accepts higher fixed cost for other benefits | Prioritizes sharing to cut idle waste | Balanced by segment |

### Step 3: Validate Through Testing

Design tests mirroring real risk scenarios:

1. Attempt **cross-tenant access** across APIs, DB, caches, object storage, search, exports, and background jobs.
2. Spike load for one tenant and measure **p95/p99 latency, error rate, and saturation** for other tenants.
3. Intentionally fail a service/cell and observe **blast radius**, circuit breakers, and recovery.
4. Drill **single-tenant restore** (or cell restore) and measure actual RTO/RPO.
5. Provision multiple new tenants; measure onboarding time, rollback capability, and configuration drift.
6. Model and reconcile TCO at normal load, peak load, and during DR activation.

### Step 4: Record an Architecture Decision Record (ADR)

~~~markdown
# ADR-021: Tenancy Model for Booking Platform

Status: Conditionally Approved
Decision owner: Lead Architect + Business Representative

Context:
- 60 small tenants, 4 enterprise tenants with distinct load and policy needs.
- Small tenants may share app and data with logical isolation.
- Enterprise tenants require dedicated databases; 1 customer
  contractually requires dedicated compute and networking.
- Goal: contain cross-tenant blast radius while controlling cost and ops effort.

Options:
A. Silo for all tenants.
B. Pool for all tenants.
C. Bridge: pool for standard tier; split components per contract.

Decision:
- Choose C, backed by a centralized tenant directory and router.
- Verify cross-tenant isolation and per-tenant load limits.
- Do not publish SLA/RTO/RPO commitments prior to live drills.

Trade-offs:
- Increases provisioning, routing, and migration complexity.
- Control plane and shared services remain broad blast-radius points.

Review triggers:
- Data policy changes; load/cost breaches thresholds;
  stricter isolation mandates; failed security or DR tests.
~~~

## 10. Real-World Scenario: Growing B2B Booking Platform

Suppose a product serves **80 business customers**, each with its own users, booking schedules, and data policies:

- 70 small tenants: under 5 requests/sec average; mostly identical features.
- 8 mid-sized tenants: heavy data syncs and off-hours reporting jobs.
- 2 large tenants: contracts mandate dedicated databases; one additionally requires dedicated compute/networking and an approved storage region.
- Product wants weekly feature releases for standard customers.
- SRE wants the number of operated environments kept within automated, recoverable bounds.

### Evaluating Options

**Option A — All Silo:** satisfies multi-layer separation for large tenants, yet 70 small environments inflate fixed costs, backup/pipeline counts, and ops load. Without strong IaC and test automation, stability suffers.

**Option B — All Pool:** optimizes resource utilization and speeds delivery for the 70 small tenants. However, it violates contracts demanding dedicated DB or compute/networking, and requires tight quotas so the 8 heavy-reporting tenants never degrade online bookings.

**Option C — Tiered Bridge:** one pool/cell for small tenants; heavy-reporting tenants use isolated queues/quotas or a dedicated cell; the two large tenants get dedicated data stores; the strictly isolated tenant gets dedicated compute, network, and access controls. A control plane manages tenant → cell/deployment mapping and routing.

**Conditional choice:** C is a sensible starting point **if** testing proves data isolation, quotas, routing, SLOs, and DR, and TCO stays within approved limits. If bridge costs or orchestration complexity exceed team capacity, adjust tier scope/packaging or options before committing.

### Suggested Operational Structure

~~~text
Shared Control Plane
  ├─ Tenant directory, contracts, service tiers
  ├─ Identity / access policies / configuration
  ├─ Provisioning / routing / billing / observability
  └─ Auditing and change management
           |
           v
Data Plane
  ├─ Pool/Cell 1: many small tenants
  │    ├─ Shared app & workers + tenant-aware authorization
  │    └─ Shared DB + tenant isolation, quotas, backup/restore
  ├─ Cell 2: heavy-workload tenants
  │    ├─ Rate-limited app / queues
  │    └─ DB per selected policy
  └─ Silo: tenants requiring strict isolation
       ├─ Contract-scoped Account/VPC/compute
       └─ Dedicated DB, keys, backups, and runbooks
~~~

Pitfall to avoid: drawing the control plane as a box "needing no redundancy." It is usually critical because a tenant directory or routing outage can lock out many tenants simultaneously.

## 11. Migrating Tenants Between Pool and Silo

Many systems start with a pool and later graduate large tenants to silos, or consolidate dedicated environments when contracts change. Transitions must preserve data integrity and recoverability.

Reference procedure:

1. **Scope the tenant:** transactional data, files, caches, search indexes, queues, secrets, keys, identity mappings, audit history, and external system state.
2. **Prepare destination:** compute/DB resources, compatible schemas, IAM roles, data region and backup policies, quotas, and monitoring.
3. **Controlled data copy:** export/snapshot and apply incremental changes (if needed) via CDC or equivalent; record exact sync watermarks.
4. **Reconcile:** verify row counts, checksums, relational integrity, permissions, balances/bookings, and event history; ensure zero data from other tenants leaked in.
5. **Controlled cutover:** pause or coordinate writes, drain final sync, update tenant routing, and verify critical business flows.
6. **Monitor and rollback readiness:** watch error rates/latency; predefine rollback criteria, approvers, and reconciliation if both sides accepted divergent writes.
7. **Decommission:** revoke old access and reclaim source resources after an agreed observation/retention window; update runbooks and ADRs.

Never enable dual-writes to both environments as a shortcut without conflict resolution, idempotency, and consistency verification. Tenant migration is an **architecture and data change** requiring rollback plans and testing on representative data.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming "dedicated" means absolute security | IAM, backups, ops, or networking can still be misconfigured | Define exact boundaries and test every layer |
| Only adding `tenant_id` to tables | APIs, caches, object storage, queues, or exports can still leak data | Tenant-aware authorization + data policies + end-to-end tests |
| Trusting client-supplied tenant IDs | Attackers spoof access to other tenants | Verify identity, membership, and permissions on the backend |
| Omitting quotas | Noisy neighbors degrade SLOs for the entire pool | Per-tenant limits, partitioned queues, cells, and fair scheduling |
| One schema migration breaking all tenants | Single change causes widespread outages | Backward-compatible migrations, canaries, monitoring, and rollbacks |
| Deploying silos manually | Configuration drift, slow patching, high ops cost | IaC, standardized pipelines, inventory, and automation |
| Promising per-tenant restore in a pool with only full-DB backups | Cannot restore one tenant without impacting others | Design and drill selective restore from day one |
| Comparing only compute prices | Misses support, DR, data transfer, security, and ops labor | Compare TCO and cost per transaction/tenant |
| Failing to track tenant → deployment mappings | Failovers or migrations route traffic wrongly | Access-controlled, audited tenant directory with update workflows |
| Isolating every tenant prematurely or sharing at all costs | Cost/complexity trade-offs misaligned with real needs | Decide from mandatory constraints, metrics, and tier-graduation thresholds |

## 13. Hands-On Exercise

A cloud-based warehouse management SaaS currently serves 30 customers, projected to grow to 150 customers over six months. Two large customers run heavy analytical reports; one requires a dedicated database and specific data residency region. Budget must be tracked per service tier. The engineering team is small, though it already uses CI/CD and basic IaC.

**Requirements:**

1. Write at least **six clarifying questions** to define isolation boundaries, load, SLOs, RTO/RPO, data, and cost; separate confirmed facts from assumptions.
2. Sketch three options: **silo, pool, and bridge**. For each, list shared vs. dedicated layers across gateway/identity, compute, network, DB, cache, queue, backups, and monitoring.
3. Build a **decision matrix** across security, compliance, tenant performance isolation, cost, scalability, and operations. Score only options satisfying all mandatory constraints.
4. Describe one **cross-tenant access** test and one **noisy neighbor** test, specifying output metrics and pass criteria.
5. Draft concise runbooks for **onboarding**, **offboarding**, and **single-tenant data restore**.
6. Write a 10–15 line ADR stating the chosen option, decision owner, trade-offs, required verification evidence, and review triggers.

**Self-assessment criteria:** a strong solution precisely defines technical boundaries, proves isolation through testing, models TCO with full operational factors, and provides an upgrade/migration path as customer segments evolve.

## 14. Pre-Finalization Architecture Checklist

- [ ] Defined what constitutes a tenant and who can switch tenants or access multiple tenants.
- [ ] Documented **shared/dedicated** choices per layer: network, compute, data, cache, queue, keys, and ops.
- [ ] Verified contractual, legal, data residency, and mandatory gating constraints.
- [ ] Designed authentication, authorization, tenant context, and data isolation on a default-deny basis.
- [ ] Planned tests for cross-tenant access, quotas/noisy neighbors, component failures, and blast radius.
- [ ] Defined SLIs/SLOs, RTO/RPO, and drill evidence matching committed scopes.
- [ ] Forecasted TCO covering growth, peak load, backups, data transfer, support, and ops.
- [ ] Built automated provisioning, inventory, schema migrations, auditing, and offboarding.
- [ ] Established per-tenant recovery workflows or formally approved limitations.
- [ ] Recorded an ADR with accountable owners, residual risks, and review triggers.

## Remember

**Dedicated deployment** prioritizes resource separation and per-customer control, typically raising fixed costs and operational effort. **Shared deployment** maximizes resource efficiency and release velocity, demanding strong tenant isolation, quotas, and cross-impact testing. **Bridge** lets you combine both across customer segments, provided orchestration and automation are deliberate.

Good decisions do not start from a pattern name, but from **business requirements and constraints → needed isolation level → network/compute/data design → measured SLOs and TCO → verified security, reliability, and operations**. Revisit the decision as tenant counts, load, contracts, or real-world evidence change.
