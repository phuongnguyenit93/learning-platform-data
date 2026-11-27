# Cell-Based Architecture and Deployment Stamps to Bound Per-Unit Scale

> **Chapter:** System Scaling  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business requirements through network, compute, data, and deployment choices; balancing reliability, security, scalability, cost, and operations using Well-Architected principles.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why a system may need to split into multiple **cells** instead of scaling one shared cluster indefinitely.
2. Describe how a **deployment stamp** packages a complete, repeatable, cloneable, and version-managed deployment unit.
3. Define cell boundaries by tenant, workload, region, or business domain; choose routing keys and customer assignment mechanisms.
4. Design isolation for data, compute, networking, quotas, faults, and access permissions across cells.
5. Calculate per-cell scale limits from capacity, concurrency, dependencies, and blast radius; set alert thresholds and triggers for provisioning a new cell.
6. Organize the control plane, data plane, inventory, placement service, routing, and stamp lifecycle.
7. Plan tenant/workload migrations between cells, data and consistency handling, rollbacks, and load balancing.
8. Evaluate trade-offs in complexity, cost, operations, reliability, and security using Well-Architected thinking.

## 1. When One Shared Cluster Is No Longer the Right Boundary

Early on, a system is typically deployed as a single application or shared service cluster for all customers. That approach is simple: one set of APIs, one database, one queue, one set of dashboards, and one release pipeline. Handling early growth usually starts with sizing up the database, adding API instances, adding workers, and tuning queries.

However, a growing SaaS platform runs into limits beyond CPU or RAM:

- A shared database hits limits on connections, IOPS, transactions, storage, locks, and recovery speed.
- One tenant with abnormal traffic can exhaust connection pools, queues, caches, or workers for other tenants.
- A bad schema change, migration, or configuration can impact every customer at once.
- An outage in a single zone, dependency service, or cloud account creates a massive blast radius.
- Every new release hits all tenants simultaneously; rollbacks or progressive rollouts are hard to scope.
- Cloud service quotas, partition limits, or API limits can be reached before application compute runs out.
- Giant single-cluster scale drags out backups, restores, failovers, maintenance, and incident investigation.

**Cell-based architecture** splits a system into multiple relatively independent serving units, each bounded in scale and blast radius. One cell contains everything needed to serve a group of tenants or a workload: internal ingress/routing, compute, database or data partition, queues, caches, telemetry, and operational policies.

When one cell fails, the goal is to contain impact primarily to the tenants/workloads assigned to that cell. When a cell nears its limits, the system provisions a new cell and assigns new customers there or migrates a subset of existing customers over.

Cells do not eliminate all shared dependencies. DNS, identity providers, billing, control planes, container registries, observability, KMS, or network services may still be shared. The architecture must identify which shared components could become single points of failure or re-expand blast radius.

## 2. Cells, Deployment Stamps, and Related Concepts

### 2.1. What Is a Cell?

A **cell** is a bounded deployment and operational unit designed to serve a defined set of tenants/workloads with independent capacity and policies within architectural boundaries.

A cell may include:

- A cell entry point or internal route.
- One or more API/service instances.
- A cell-scoped database, schema, partition, or data cluster.
- Dedicated or strictly partitioned queues, workers, caches, and storage.
- Workload identities/roles and network policies.
- Metrics, logs, traces, alerts, runbooks, and capacity configurations.
- Application versions, runtime configurations, and cell identity metadata.

A cell can be a deployment within the same region, a dedicated account/subscription/project, a cluster group, a database shard, or a combination. **Logical boundaries and infrastructure boundaries do not have to match identically**, but the more core resources are shared, the more fault isolation depends on resource configuration and quotas.

### 2.2. What Is a Deployment Stamp?

A **deployment stamp** is a repeatable deployment package representing a configured copy of the workload. A stamp is typically built from IaC modules, configuration, application versions, policies, networking, and required data services.

A stamp is the packaging mechanism that creates cells consistently:

- Carries a template identifier and version.
- Parameterizes region, capacity, tier, service types, and policies.
- Registers a set of resource IDs in an inventory.
- Defines health/readiness checks, telemetry, and acceptance criteria.
- Follows a lifecycle: provision, activate, scale, upgrade, drain, retire.

In many architectures, one deployment stamp deploys one cell. However, one stamp can instantiate multiple cell instances, or one cell can comprise multiple sub-stamps per tier. What matters is a **repeatable unit with clear boundaries and contracts**, not the label itself.

### 2.3. Distinguishing Cells From Shards, Replicas, and Availability Zones

| Concept | Primary Purpose | How It Differs From a Cell |
|---|---|---|
| **Data shard/partition** | Split data and read/write load | May split only the database; apps, queues, and faults remain shared |
| **Replica** | Scale reads or provide redundancy | Copies typically belong to one logical service/dataset, not necessarily tenant-independent |
| **Availability zone** | Isolate certain infrastructure faults within a region | One cell can span multiple zones; multiple cells can share a zone |
| **Microservice** | Separate responsibilities and code/deploy boundaries | Split services can still share a database and blast radius |
| **Deployment stamp** | Replicate a complete deployment configuration | The deployment pattern/template; a cell is the isolated operational unit created from it |
| **Tenant isolation** | Prevent customers from accessing or impacting each other's data | Cells add an isolation layer, but in-cell authz and data controls are still required |

A sharded system is not automatically cell-based. If every shard shares a queue, a control plane holds permission to wipe everything, and a release pipeline updates all shards at once, blast radius remains huge. Conversely, a cell with its own database and multiple API replicas inside is not a microservice architecture just because it runs multiple instances.

## 3. Logical Architecture: Control Plane and Data Plane

### 3.1. Two Planes of Responsibility

A multi-cell architecture typically separates:

- **Control plane:** manages cell inventory, placement, tenant assignments, provisioning, policies, versions, capacity, lifecycle, and routing metadata.
- **Data plane:** processes business requests inside cells, accesses assigned tenants' data, and serves workloads.

The control plane should not sit in the mandatory synchronous path of every request. If the placement service temporarily fails, requests for already-assigned tenants should still route using stored/cached assignments within safe bounds. Administrative operations—onboarding tenants, moving cells, or provisioning new cells—can safely wait for the control plane.

### 3.2. Multi-Cell Diagram

~~~mermaid
flowchart TB
    U[Clients / Tenants] --> EDGE[Global Ingress / Gateway]
    EDGE --> ROUTER[Cell Router]
    ROUTER --> C1
    ROUTER --> C2
    ROUTER --> C3
    subgraph Control[Control Plane]
        REG[Cell Inventory]
        PLACE[Placement Service]
        PROV[Stamp Provisioner]
        POLICY[Policy / Capacity Controller]
        REG <--> PLACE
        PLACE --> ROUTER
        POLICY --> PROV
        PROV --> REG
    end
    subgraph C1[Cell A]
        AAPI[API + Workers]
        ADB[(Cell A Database)]
        AQ[Queue / Cache]
        AAPI --> ADB
        AAPI --> AQ
    end
    subgraph C2[Cell B]
        BAPI[API + Workers]
        BDB[(Cell B Database)]
        BQ[Queue / Cache]
        BAPI --> BDB
        BAPI --> BQ
    end
    subgraph C3[Cell C]
        CAPI[API + Workers]
        CDB[(Cell C Database)]
        CQ[Queue / Cache]
        CAPI --> CDB
        CAPI --> CQ
    end
    OBS[Central Observability] -.-> AAPI
    OBS -.-> BAPI
    OBS -.-> CAPI
~~~

This logical diagram does not imply central observability or the router is a single server. Shared services require HA deployments, scoped permissions, caching, and fallback plans. The router needs cell assignments, not internal business data.

### 3.3. Keeping the Control Plane From Becoming a Bottleneck

Control plane operations occur far less frequently than business requests, yet carry high impact:

- Creating new cells or upgrading stamp versions.
- Assigning, migrating, or suspending tenants.
- Marking cells degraded, full, or under maintenance.
- Updating routing metadata.
- Evaluating capacity and triggering scale-out.
- Retiring cells after tenants have migrated out.

Safeguards:

1. Expose administrative APIs with strict authentication, authorization, and auditing.
2. Separate provision/destroy permissions from standard request-handling permissions.
3. Persist workflow state durably; provisioning actions must be idempotently retryable.
4. Cache assignments at the router/data plane; define TTLs and stale-metadata handling.
5. Enforce quotas and rate limits on cell creation so automation cannot spin up unbounded resources.
6. Require explicit review for destructive actions, data migrations, and fleet-wide routing changes.
7. Ensure the control plane keeps operating when a cell fails and does not depend on the broken cell it is repairing.

If the router queries the placement database synchronously on every request, the placement service becomes a latency and availability bottleneck for the entire system. Distribute or cache assignments with appropriate reliability.

## 4. Choosing Cell Boundaries

No single cell split fits every product. Boundaries must weigh blast radius, data, load, geography, permissions, and cost.

### 4.1. Placement Strategies

| Strategy | Assignment Rule | Advantages | Limitations |
|---|---|---|---|
| Per tenant | Each tenant gets a dedicated cell | Clear isolation and routing | Huge tenants may exceed single-cell capacity |
| Per tenant group | Many small tenants share a cell | Cost-efficient, simpler operations | One noisy neighbor can impact the group |
| By geographic region | Tenants placed in cells near permitted regions | Low latency and data residency | Must manage multiple regions and uneven capacity |
| By tier/service plan | Premium, standard, or distinct workloads in separate cells | Allocates resources by value/SLO | Complex billing/placement and risk of mis-prioritization |
| By business domain/workload | Distinct workloads run in separate cells | Isolates load profiles and release cycles | May require cross-cell integration |
| Hybrid | Combines tenant, geography, tier, and capacity | Flexible | Harder policies and routing; requires consistent rules |

### 4.2. Principles for Selecting Boundaries

- **Blast radius:** how many tenants, revenue share, or business flows are affected if one cell fails?
- **Data ownership:** whose data is co-located; can deletion/export requests be cleanly scoped?
- **Workload profile:** do tenants in the cell share similar read/write ratios, bursts, batches, background jobs, and storage needs?
- **Quotas/capacity:** how do tenants share database, queue, or network quotas?
- **Geography/compliance:** which region must hold the data, and is cross-region replication permitted?
- **Release cadence:** do tenants require different versions, or should all cells stay uniform?
- **Support model:** can on-call teams quickly identify the cell, owner, and runbook?
- **Cost efficiency:** does cell count introduce excessive idle resources, control plane overhead, and operational toil?

Never size cells purely by tenant count. Ten small tenants may consume less than one heavy data-processing tenant. Base decisions on resource and workload metrics.

### 4.3. Large Tenants and Noisy Neighbors

A tenant can grow until it consumes a major share of a cell's capacity. Options:

- Move the large tenant into its own cell (silo/dedicated cell).
- Route heavy workloads to a separate pool while keeping shared metadata and identity.
- Enforce quotas, rate limits, and priorities to cap consumption.
- Separate batch/analytics tasks from interactive requests.
- Migrate the tenant to a newer, higher-capacity cell.

Dedicated cells provide strong isolation and custom SLOs, yet raise minimum baseline costs due to dedicated databases, compute, and monitoring. Use tiering tied to clear demand and value rather than opening ad-hoc dedicated cells manually.

## 5. Designing Repeatable Deployment Stamps

### 5.1. Stamps Must Be Declaratively Complete

A stamp should be described via versioned, parameterized templates:

| Group | Parameters to Declare |
|---|---|
| Identity | stamp ID, cell ID, environment, owner/team, tenant capacity |
| Location | cloud account/project, region, zone policy, network boundary |
| Compute | API/worker profiles, autoscaling min/max, resource limits |
| Data | database engine/tier, storage limits, backups, retention, encryption |
| Messaging/cache | queues/topics, partitions, retries, DLQs, cache capacity |
| Security | workload identities, IAM roles, KMS keys, ingress/egress |
| Routing | cell endpoints, router metadata, health status, traffic weights |
| Observability | logs, metrics, traces, dashboards, alerts, tags |
| Version | stamp template version, application release, schema version |
| Lifecycle | provision, acceptance, active, degraded, draining, retired |

Defaults must be secure: databases private, secrets never stored in repositories, ingress restricted through gateways, sensitive data masked in logs, backups enabled by data classification, and quotas bounded.

### 5.2. IaC and the Cell Provisioning Pipeline

Reference pipeline:

~~~mermaid
flowchart TD
    REQ[Cell request] --> VALID[Validate owner / region / capacity / budget]
    VALID --> PLAN[Render stamp + IaC plan]
    PLAN --> REVIEW[Policy checks and approval]
    REVIEW --> APPLY[Provision network / IAM / data / compute]
    APPLY --> BOOT[Bootstrap app and register endpoints]
    BOOT --> TEST[Health, security, connectivity, smoke tests]
    TEST --> ACCEPT{Acceptance passed?}
    ACCEPT -- No --> FIX[Remediate or rollback provisioning]
    FIX --> PLAN
    ACCEPT -- Yes --> INV[Register inventory and placement capacity]
    INV --> ACTIVE[Cell available for assignment]
~~~

The pipeline must:

- Separate IaC state per cell or independently manageable scope.
- Be idempotent so retries never duplicate resources.
- Bound parallel provisioning to avoid exhausting cloud quotas or overwhelming control planes.
- Review diffs/plans and catch destructive replacements of stateful resources.
- Run automated policy checks before and after `apply`.
- Record resource IDs, endpoints, versions, owners, and outputs into the inventory.
- Allow the placement service to pick the cell only after acceptance tests pass.
- Provide rollback/cleanup for partial provisioning and state reconciliation.

### 5.3. Preventing Configuration Drift Across Cells

As cell count grows, manually editing one cell causes drift and inconsistent behavior. Enforce:

1. Tracked stamp template versions and application versions.
2. A single source of truth for configs (Git/config service) with schema validation.
3. Scheduled drift detection, alerting, and reconciliation workflows.
4. Canary or wave-based rollouts for new template versions.
5. An inventory showing which cells lag behind and why.
6. Approved exceptions with explicit expiration dates and owners.

Not every cell must jump to the same release instantaneously. Wave rollouts by region, tier, or tenant cohort work well, provided supported version counts and support windows remain bounded to curb compatibility costs.

## 6. Routing and Assigning Tenants to Cells

### 6.1. Assignment Registry

The router needs to resolve which cell owns each tenant or workload. Minimum registry fields:

| Field | Meaning |
|---|---|
| `tenant_id` | Tenant identifier |
| `cell_id` | Assigned cell |
| `region` | Deployment location |
| `state` | `pending`, `active`, `moving`, `suspended`, `retired` |
| `routing_version` | Assignment version used to detect stale metadata |
| `assigned_at` | Timestamp of assignment |
| `placement_reason` | Rule/tier/capacity logic applied |
| `data_location` | Authoritative location where data resides |

The registry is critical control metadata requiring backups, auditing, write access control, and consistency. Avoid storing bulky business data in the registry or letting callers pick cells via unverified headers.

### 6.2. Request Flow

~~~mermaid
sequenceDiagram
    actor Client
    participant Edge as Global Gateway
    participant Auth as Identity / AuthN
    participant Router as Cell Router
    participant Reg as Assignment Cache / Registry
    participant Cell as Assigned Cell
    Client->>Edge: Request + access token
    Edge->>Auth: Validate identity and tenant claims
    Auth-->>Edge: Authenticated tenant context
    Edge->>Router: Route by verified tenant_id
    Router->>Reg: Resolve tenant assignment
    Reg-->>Router: cell_id + routing_version
    Router->>Cell: Forward to assigned endpoint
    Cell->>Cell: Authorize tenant and process request
    Cell-->>Client: Response
~~~

This is a logical flow; the router can use cached mappings rather than calling the registry synchronously on every request. **Identity verification and tenant authorization must still run inside the cell**: knowing a `tenant_id` does not grant unrestricted access to all data inside that tenant.

### 6.3. Selecting a Routing Key

`tenant_id` is usually the clearest routing key when each tenant lives in one cell. Never use mutable attributes like email addresses, customer names, or user properties as placement keys. Non-tenant workloads like telemetry ingestion or internal jobs may require separate workload IDs or domain keys.

A registry must guard against:

- **Hot keys:** a massive tenant overloading mapping caches or routers.
- **Stale assignments:** outdated caches sending requests back to the old cell post-migration.
- **Split assignments:** two routers simultaneously thinking a tenant lives in two different cells.
- **Missing assignments:** newly created tenants lacking an active cell yet.
- **Unauthorized overrides:** clients injecting a cell ID to reach another cell.

Mitigate using routing versions/generations, cache TTLs, invalidation, audits, and transition states. While a tenant is moving, the router can reject or forward according to a controlled policy, never writing to both places concurrently without an explicit synchronization design.

## 7. Bounding Per-Cell Scale

Cells only help if each cell stays bounded. If a cell is allowed to grow endlessly, single-cluster problems simply re-appear inside each cell.

### 7.1. Measuring Limits per Component

Minimum cell limits to evaluate:

| Component | Limits to Measure |
|---|---|
| API/compute | Requests/s, concurrency, CPU, memory, thread/connection pools, p95/p99 |
| Database | TPS, active connections, IOPS, storage, lock waits, replication lag, maintenance windows |
| Queue/broker | Publish/consume throughput, partitions, message size, backlog, oldest age |
| Cache | Memory, evictions, hot keys, network throughput |
| Network | NAT/egress, connection tracking, bandwidth, private endpoint/service quotas |
| Control plane | Provisioning rate, API quotas, cell/tenant mapping counts, registry throughput |
| Observability | Log/metric volume, cardinality, retention, ingestion limits |
| Backup/restore | Backup windows, restore throughput, RTO/RPO, and recovery capacity |

The most critical limit is usually **the earliest ceiling among critical dependencies**, not API CPU. If API CPU sits at 40% while database connections are maxed out, adding API instances makes things worse.

### 7.2. Calculating Capacity From SLOs

Hypothetical load measurement example for one cell:

- Database sustains 1,000 transactions/second before p95 breaches target.
- Team wants target utilization capped at 70% to keep headroom.
- An average tenant generates 5 transactions/second at peak.
- Background tasks and general variance reserve 100 transactions/second.

Capacity available for tenants:

~~~text
Target transaction rate = 1,000 × 70% = 700 txn/s
Platform headroom = 100 txn/s
Remaining capacity for tenants = 700 - 100 = 600 txn/s
Theoretical tenant count = 600 / 5 = 120
~~~

The figure 120 is a rough estimate, not a hard quota. Tenants are not uniform; one tenant can spike unexpectedly; transaction mixes and data sizes differ. If the cell's largest tenant is 10x the average, model that skew in tests or move it to a dedicated cell.

Never sum capacity across components with mismatched units or utilization ratios. Build capacity models around business-flow bottlenecks: one API request can fan out into multiple queries, messages, and external calls.

### 7.3. Rules for Opening a New Cell

Set multi-signal triggers:

- Projected database utilization or connection pool usage exceeds threshold across a stabilization window.
- p95/p99 degrades with load despite query tuning and in-cell scaling.
- Storage, backup, or restore durations approach operational limits.
- One tenant pushes usage skew past acceptable bounds.
- The cell lacks sufficient spare capacity to survive losing one zone.
- Cloud quotas lack headroom for autoscaling.
- Blast radius or tenant count exceeds governance caps.

Illustrative policy:

~~~text
if projected_peak_db_utilization > 70%
   for 3 consecutive review windows:
       mark cell = NEAR_CAPACITY
       stop assigning new tenants
       evaluate scale-up or create next cell

if critical_dependency_saturation > 85%
   or error_budget_burn exceeds alert policy:
       trigger immediate capacity / reliability review
~~~

Derive thresholds from load tests, SLOs, and fault tolerance; do not blindly apply 70%/85% to every database. Factor in absolute limits, growth velocity, and cell provisioning lead time so new cells exist before headroom runs out.

### 7.4. Scale-Up Inside a Cell vs. Scale-Out With a New Cell

| Action | Best When | Limitations |
|---|---|---|
| Scale up DB/compute inside cell | Quota headroom remains, clear benefit, acceptable blast radius | Hardware/service ceilings and potential downtime |
| Scale out API/workers inside cell | Bottleneck sits in stateless compute/workers | Can push extra load onto shared cell dependencies |
| Split large tenant to dedicated cell | Noisy neighbor or tenant outgrows cell profile | Requires migration and dedicated capacity operations |
| Open new cell for new tenants | Current cell nears capacity, need to cap blast radius | Increases footprint, routing, and baseline cost |
| Split workloads into dedicated cells | Batch/analytics degrade interactive requests | Increases integration and data-product management |

Opening a new cell does not fix global bottlenecks like a shared analytics database, identity provider, NAT gateway, or central broker. Shared dependencies need their own capacity models and partitioning plans.

## 8. Isolating Data and Transactions Across Cells

### 8.1. Data Isolation

Multiple isolation tiers exist:

| Tier | Example | Characteristics |
|---|---|---|
| Logical tenant partition | All tenants share a DB with `tenant_id` and row-level policies | Low cost; demands ironclad query/authz enforcement |
| Schema/database per cell | Each cell gets its own schema or DB | Better containment of data errors, yet still shares instance/cluster quotas |
| Cluster/account per cell | Dedicated database and data infrastructure | Stronger blast radius and IAM isolation; higher cost and ops effort |
| Dedicated cell per tenant | Large tenant gets dedicated DB and compute | Maximum isolation, largest footprint |

Choose the tier matching your threat model, data sensitivity, compliance, SLOs, cost, and independence needs. A separate database does not replace authorization; tenant A's token must still never access tenant B via APIs or exports.

### 8.2. Invariants When Data Lives Inside a Cell

- The cell is the authoritative writer for its assigned tenants.
- Every data access request must verify tenant context and resource ownership.
- Primary/unique keys should be tenant-scoped or guarantee global uniqueness as required.
- Background workers must know the tenant/cell context and validate message origins.
- Backups/restores must explicitly scope by cell and tenant; restoring one cell must never overwrite another cell's data.
- Per-tenant auditing and retention must span storage, backups, events, and analytics.

### 8.3. Cross-Cell Transactions

If a business operation must update data in two different cells, do not assume a simple ACID transaction spans them. Options:

- Keep tightly coupled transactional data inside the same cell if the domain allows.
- Use sagas/process managers with explicit steps, states, timeouts, and compensations.
- Use events/outboxes for asynchronous communication, accepting eventual consistency.
- Maintain an overarching ledger or authoritative service if business rules demand a single writer.

Never partition cells by tenant if cross-tenant synchronous writes without eventual consistency are frequent; revisit boundaries or data models instead.

### 8.4. Per-Cell Backup and Recovery

Each cell should define:

- Named backup policies, snapshots/PITR, and encryption keys.
- RTO/RPO targets matched to tenant/tier requirements.
- Runbooks for restoring into the same cell or a replacement cell.
- Consistency checks across databases, object storage, queues/outboxes, and metadata.
- Independent restore drills per cell, plus control plane/registry drills.
- Post-restore/failover routing updates with fencing and versioning.

Per-cell backups isolate recovery scopes, yet multiply schedules, keys, policies, and verification artifacts. Automation must prove every cell is backed up and restore-tested per policy.

## 9. Fault Isolation and Incident Coordination

### 9.1. Bounded Blast Radius

One degraded cell should not take down the entire platform. The router can stop placing new tenants into that cell while existing tenants follow recovery policies. The control plane provisions a fresh cell for new signups or replaces the retired cell.

~~~mermaid
flowchart TB
    U[Requests] --> R[Cell Router]
    R -->|Healthy assignments| A[Cell A: Healthy]
    R -->|Healthy assignments| B[Cell B: Healthy]
    R -.->|Block new placement| C[Cell C: Degraded]
    C --> ALERT[Incident + Recovery workflow]
    ALERT --> REPAIR[Repair / restore / drain]
    REPAIR --> HEALTH{Acceptance and health restored?}
    HEALTH -->|Yes| C
    HEALTH -->|No| MIGRATE[Controlled tenant migration]
    MIGRATE --> N[Cell D: Replacement]
~~~

Never blindly evacuate all tenants out of a degraded cell before understanding the failure. If the issue involves database corruption or unsynced data, shifting traffic to another cell without verified data makes matters worse.

### 9.2. Cell Health Classification

A cell can track lifecycle states:

- **Provisioning:** resources are being created; not accepting tenants yet.
- **Ready:** passed acceptance tests and available for assignments.
- **Active:** actively serving tenants.
- **Near-capacity:** still serving, but blocked from accepting additional load/tenants per policy.
- **Degraded:** one or more critical components are impaired.
- **Draining:** accepting no new tenants while migrating or finishing workloads.
- **Recovering:** undergoing restore/reconciliation; not reopened yet.
- **Retired:** decommissioned with resources, data, and permissions reconciled.

Cell status should never be a bare green/red boolean. Store reason codes, dependency states, transition timestamps, owners, permitted actions, and routing policies.

### 9.3. Shared Dependencies and Correlated Failures

Cell-based architecture limits cell-to-cell blast radius, yet shared services can still trigger correlated outages:

| Shared Dependency | Risk | Mitigation |
|---|---|---|
| Identity provider | Cannot authenticate requests across any cell | HA, safe token/session caching policies, fail-closed fallbacks |
| Global router/DNS | Cannot route to any cell | Redundancy, cached assignments, health and failover controls |
| Shared message broker | Backlogs or quotas impact multiple cells | Quota/namespace/partition isolation, capacity, and backpressure |
| Central KMS | Cannot decrypt or start workloads | High key availability, scoped permissions, break-glass access |
| Observability pipeline | Fleet-wide telemetry loss | Local buffering, multi-region ingestion, independent alerts |
| CI/CD/artifact registry | Cannot deploy or patch cells | Artifact caching, version pinning, control-plane outage procedures |
| Control plane database | Cannot update placement/lifecycle | Replication/backups, caching, and fallback operational procedures |

The goal is not necessarily eliminating every shared dependency, but **knowing blast radius, limiting impact, and never assuming absolute cell independence**.

## 10. Tenant and Cell Lifecycle

### 10.1. Onboarding a New Tenant

Assignment flow:

1. Validate tenant/business owner, region/data residency, and service tier.
2. Estimate initial resource needs and locate a `Ready`/`Active` cell with headroom.
3. Check quotas, tenant mix, locality, and policies.
4. Create tenant metadata and configure namespace/partition or database scope.
5. Verify access, seed data, and routing.
6. Record the active assignment state alongside `routing_version`.
7. Admit traffic per policy while monitoring errors and capacity.

A tenant is not active simply because it has a `cell_id`. Verify seed data, permissions, encryption, quotas, and live routing all work.

### 10.2. Cell Full or Near Capacity

When a cell reaches `Near-capacity`:

- Halt new tenant placements if forecasts exceed headroom.
- Shed or throttle non-essential workloads if required.
- Scale up within the cell if dependencies and quotas allow.
- Provision a new stamp and run acceptance checks.
- Assign incoming tenants to the new cell.
- Pick tenants to migrate out if the existing cell breaches thresholds or needs noisy-neighbor isolation.

Provision new cells well before hitting hard saturation; provisioning, DB initialization, catalog seeding, and testing take time. Capacity controllers must forecast using growth velocity and cell provisioning lead times.

### 10.3. Retiring a Cell

Never delete a cell while tenant assignments or retained data remain. Retirement workflow:

1. Mark `Draining`, blocking new assignments.
2. Inventory remaining active tenants, jobs, queues, secrets, API clients, and dependencies.
3. Migrate tenants or complete contractual offboarding.
4. Reconcile data, pending events, backups, and retention requirements.
5. Revoke routing, credentials, and workload identities in safe order.
6. Execute the reviewed destroy plan while preserving approved archives.
7. Reconcile inventory, cloud resources, quotas, and billing.
8. Archive audit records and mark `Retired`.

## 11. Migrating Tenants Between Cells

Tenant migration is complex because data, new writes, events, and routing must stay consistent end-to-end.

### 11.1. Migration Approaches

| Approach | How It Works | Best Suited For | Risks/Trade-Offs |
|---|---|---|---|
| Offline migration | Freeze writes, copy data, verify, switch route | Small datasets with acceptable maintenance windows | Downtime proportional to copy/verify duration |
| Snapshot + delta sync | Initial snapshot, sync ongoing changes, cut over | Large datasets needing minimal downtime | Must manage logs/CDC and commit ordering |
| Controlled dual-write | Write to both places during transition | Rare cases needing short transitions | High drift risk, hard rollback; needs idempotency/reconciliation |
| Temporary proxy/forwarding | Old cell forwards requests or writes to new cell | Smoothing client/routing transitions temporarily | Extra hop, coupling, and forwarding failure modes |

Never enable dual-write just to feel "safe." Without a shared distributed transaction, a write can succeed on Cell A and fail on Cell B. Outboxes, retries, reconciliation, and an explicit source of truth are mandatory.

### 11.2. Reference Cutover Workflow

~~~mermaid
sequenceDiagram
    participant CP as Control Plane
    participant Old as Source Cell
    participant New as Destination Cell
    participant Router
    CP->>New: Provision and validate tenant scope
    CP->>Old: Start snapshot / CDC export
    Old-->>New: Initial snapshot
    Old-->>New: Delta changes / CDC
    New->>New: Validate counts, checksums, invariants
    CP->>Old: Freeze writes or enter controlled cutover
    Old-->>New: Final delta and checkpoint
    New-->>CP: Consistency gate passed
    CP->>Router: Update assignment + routing version
    Router-->>New: Route new requests
    New-->>CP: Observe successful traffic
    CP->>Old: Retain read-only rollback window
    Note over Old,New: Retire source only after acceptance and retention checks
~~~

Key steps:

1. Provision the destination cell with matching schema/config versions.
2. Copy snapshot with a recorded version/checkpoint.
3. Sync deltas via CDC/event logs or an equivalent mechanism.
4. Reconcile row counts, per-partition checksums, business invariants, and permissions.
5. Pause writes or apply fencing to block the old writer during the cutover window.
6. Apply the final delta, confirm checkpoint, and mark the authoritative data store.
7. Update assignment/`routing_version` atomically or via safe transition states.
8. Monitor requests, events, latency, errors, and data post-cutover.
9. Keep the source read-only for the approved rollback retention window.
10. Retire the source only after data and operational gates pass.

### 11.3. Migration Rollback

Rollback is not simply flipping routing back to the old cell. Post-cutover transactions may already exist in the destination cell. Switching back without reverse-syncing deltas risks data loss.

Rollback plans must specify:

- The exact last checkpoint when the old cell was authoritative writer.
- The timestamp when the new cell became writer.
- How every post-cutover mutation is captured.
- Whether reverse-sync to the old cell is possible or roll-forward/fix-forward in the new cell is required.
- Who authorizes rollback and the maximum rollback window.
- Which roll-forward/fix-forward recovery path applies if data rollback is impossible.

Keeping the source read-only helps auditing and reconciliation, but does not automatically make write rollbacks safe.

## 12. Releasing and Upgrading a Cell Fleet

### 12.1. Wave Rollouts

With dozens or hundreds of cells, deploying everywhere simultaneously blows up blast radius. Roll out in waves:

1. Validate integration/staging stamps.
2. Canary on an internal cell or opt-in test tenant cohort.
3. Small waves by region/tier while monitoring SLIs and data correctness.
4. Expand cell count after each quality gate passes.
5. Pause if error budgets, schema errors, latency, or dependencies breach thresholds.
6. Complete rollout and confirm remaining cells by deadline.

Manage compatibility across app versions, schemas, and events. Cell A may be upgraded while Cell B runs the prior version. Shared services and event formats must tolerate coexistence windows.

### 12.2. Version Skew

A fleet with excessive version skew suffers from:

- Divergent API/event contracts across cells.
- Incompatible operational/admin tools.
- Schema migrations applied to only part of the fleet.
- Aggregated dashboards misinterpreting old vs new metrics.
- Unpatched security vulnerabilities on lagging cells.

Maintain an inventory tracking stamp version, application version, schema version, and release dates; define support windows, minimum supported versions, and upgrade deadlines. Automatically flag out-of-policy cells and pause new tenant placements onto them.

### 12.3. Canary Cells Must Be Representative

Never choose a canary cell just because it has few tenants. Verify:

- Whether workload profiles and traffic match the broader fleet.
- Whether internal/partner tenants can give rapid feedback.
- Whether regions and cloud dependencies are representative.
- Whether data volumes and schemas are rich enough to surface migration bugs.
- Whether rollback/fix-forward can proceed without broad disruption.

A tiny idle cell only proves startup works; it rarely exposes database or streaming bottlenecks under load.

## 13. Fleet Observability and Governance

### 13.1. Cell-Level vs. Fleet-Level Metrics

| Category | Cell-Level Metrics | Fleet-Level Metrics |
|---|---|---|
| Traffic | RPS, request success, p95/p99 per endpoint | Total traffic, load distribution, tenant skew |
| Compute | CPU/memory/concurrency/API saturation | Cell utilization distribution, near-capacity cell count |
| Database | TPS, connections, IOPS, locks, storage, replica lag | Top cell bottlenecks, capacity forecasts |
| Queues | Depth, oldest age, retries, DLQs, consume rate | Total backlog, cells with consumer lag |
| Reliability | Availability/SLOs, incidents, restarts, failovers | Error budgets by cell/fleet, correlated failures |
| Capacity | Headroom, tenant count, growth rate | Cell provisioning lead time, utilization ratio, reserved capacity |
| Security | IAM drift, policy violations, access anomalies | Out-of-policy cells, credential rotation status |
| Releases | Version, deployment outcomes, rollbacks | Version skew, rollout progress percentage |
| Cost | Cost per tenant/cell, idle resources | Cost per active tenant, cost per unit of workload |

Never rely solely on fleet-wide averages. A few saturated cells easily hide behind many idle cells. Track percentiles, distributions, and top-N cells/tenants by resource usage.

### 13.2. Dashboards and Runbooks

Dashboards should quickly answer:

- Which cells are `Active`, `Near-capacity`, `Degraded`, `Draining`, or out-of-policy?
- Which tenant belongs to which cell, and when did its assignment last change?
- Is a cell's bottleneck in the API, DB, queue, network, or a shared dependency?
- Does the cell retain enough capacity if one zone fails?
- Which app and schema versions are running in each cell?
- When was the last backup/restore and last recovery drill?
- Which cell is driving cost increases, and due to which workload/retention/query?

Runbooks need isolation steps, owners, permitted commands/automation, stop conditions, and recovery verification. Avoid forcing on-call engineers to run manual ad-hoc queries across every cell without inventory and automation.

### 13.3. Fleet Compliance

A controller can periodically scan cells:

~~~text
for each cell in inventory:
    verify stamp_version is supported
    verify required security policies
    verify backups and restore evidence
    verify telemetry and alert ownership
    verify capacity and dependency health
    verify tenant assignments are consistent
    if violation:
        create remediation work
        block new placement when risk is critical
~~~

This is process pseudocode, not a runnable script. Policy enforcement needs audit, warn, placement-block, and time-bound exception modes; never auto-destroy a cell over a missing tag.

## 14. Security in Cell-Based Architectures

### 14.1. Cell Boundaries Do Not Replace Identity Boundaries

Even when tenants are separated across cells, APIs must still:

- Verify tokens, audience, and issuer.
- Extract tenant context from trusted claims post-authentication.
- Validate tenant assignment and resource ownership.
- Enforce authorization on every data operation.
- Block callers from tampering with tenant/cell IDs in paths, headers, or bodies to reach other tenants.
- Emit audit logs for sensitive operations, exports, admin actions, and migrations.

Dedicated cells shrink blast radius; they are never an excuse to skip IDOR/BOLA or tenant isolation testing.

### 14.2. Admin Privileges and Break-Glass Access

Control planes wield sweeping powers: creating/destroying networks, databases, IAM, and routing. Enforce:

- Separate identities for provisioners, routers, data migrations, operators, and workloads.
- Least privilege scoped per cell; avoid fleet-wide wildcard permissions.
- Approvals and auditing for destroys, reassignments, region moves, and high-impact key rotations.
- Time-bound break-glass access with MFA, full logging, and post-incident review.
- KMS keys/secrets scoped per cell or domain; never let one leaked credential open the entire fleet.
- Strict policies for cross-cell data access and audited support access.

### 14.3. Encryption and Sensitive Data

Tenants may require dedicated keys, regions, or retention rules. Stamp templates should support corresponding policy tiers without spawning uncontrolled snowflake variants. Every exception must be inventoried and reviewed.

When deleting a tenant, cover the cell database, queues, caches, object storage, snapshots, backups, analytics extracts, and data science datasets. Cell boundaries help group data, but do not automatically purge every downstream copy.

## 15. Cost and Resource Efficiency

### 15.1. Benefits and Costs of Replication

Cells duplicate components like databases, queues, caches, gateways, and monitoring. This raises total baseline cost even when individual cells are underutilized.

Trade-offs:

- Smaller cells reduce blast radius, but increase idle baseline cost and database/cluster counts.
- Larger cells improve utilization, but widen blast radius and lengthen recovery times.
- Dedicated cells maximize isolation, but sacrifice economies of scale.
- Shared control planes cut cost, but require HA, quotas, and correlated-failure controls.
- Shared brokers/storage save footprint, but can reintroduce noisy neighbors.

### 15.2. Rough Cost Illustration

Suppose a stamp has a baseline cost of \$500/month for the minimum database tier, \$200/month for baseline compute, and \$100/month for queues/caches/monitoring. Total baseline is \$800/month/cell before variable usage.

~~~text
10 cells × $800 = $8,000/month baseline

If each cell averages only 35% baseline compute utilization,
yet databases and core services must stay running:
costs do not shrink proportionally to 35%.
~~~

This example illustrates the mental model only, not real cloud pricing. Actual forecasts require provider calculators/billing rates, regions, reservations/discounts, network egress, backups, logs, data transfer, and HA tiers.

### 15.3. Tracking Utilization and Efficiency

Suggested metrics:

- Cost per active tenant and cost per transaction.
- Compute/database utilization ratio per cell.
- Number of `Near-capacity` cells and idle cells.
- Tenant count and workload skew per cell.
- HA/DR redundancy and backup costs.
- Provisioning cost/time and migration costs.

Never optimize cost-per-tenant blindly if it pushes tail latency or blast radius past targets. Evaluate SLOs, risk, and cost holistically.

## 16. Trade-Offs and When Not to Use Cell-Based Architecture

Cell-based architecture pays off when scale, independence, or isolation requirements are high enough. However, it adds an entire coordination and routing tier.

### 16.1. Complexity Costs

- Requires an accurate control plane and inventory.
- Routing must handle assignments, transitions, and cache invalidation.
- Cross-cell migrations must solve consistency and rollbacks.
- Fleets accumulate version skew and policy drift.
- Request debugging requires tracing across gateways/routers into the right cell.
- Backup/restore, security reviews, and capacity planning scale with cell count.
- Shared dependencies can still cause correlated failures.

### 16.2. When to Keep Architecture Simpler

Avoid cell-based architecture when:

- Traffic and data are small enough for one cluster to meet SLOs with ample headroom.
- Strict blast-radius or tenant-isolation requirements do not exist.
- The team lacks operational maturity to manage multiple independent units.
- Per-cell baseline costs outweigh scale/isolation benefits.
- Workloads require frequent synchronous cross-tenant transactions that cells complicate.

Start with modular architecture, tenant-aware schemas, quotas, rate limits, queue isolation, and solid observability. Keep access patterns, tenant registries, and IaC clean so you can evolve into cells later without premature complexity.

### 16.3. Evolution Path

1. Single shared cluster with `tenant_id`, proper authz, and quotas.
2. Isolate heavy workloads, add read replicas, or partition data as needed.
3. Standardize deployments with stamps/IaC while running one or a few cells.
4. Separate tenant cohorts and introduce control plane/placement.
5. Add cells driven by capacity and blast radius limits.
6. Add migration automation, fleet releases, and compliance scanning.

Not every system needs to walk through every stage; use concrete triggers rather than treating cell-based architecture as a mandatory destination.

## 17. Well-Architected Evaluation

| Pillar | Questions for Cells and Deployment Stamps | Evidence |
|---|---|---|
| **Operational Excellence** | Can cells be provisioned, tested, released, migrated, and retired repeatably? | IaC, pipelines, inventory, runbooks, fleet dashboards |
| **Security** | Do tenants, workloads, cells, and control planes enforce least privilege and data isolation? | Tenant isolation tests, IAM reviews, audits, KMS policies |
| **Reliability** | Are cell outages contained; are shared dependencies planned for; do restores/migrations pass? | Fault injection, cell outage drills, restores, routing tests |
| **Performance Efficiency** | Are per-cell capacity, quotas, noisy neighbors, and scale-out measured? | Load tests, skew tests, saturation metrics, capacity forecasts |
| **Cost Optimization** | Are cell footprint, idle baselines, dedicated tiers, and migrations cost-effective? | Cost per tenant, utilization, showback |
| **Sustainability** | Are idle resources, stamp lifecycles, and storage/backup retention optimized? | Idle cell reports, scale-down, retention compliance |

Cell-based architecture does not automatically improve every pillar. More cells can boost reliability through isolation while hurting operational excellence if automation lags. Choose boundaries matching your organization's execution capability.

## 18. Hands-On Exercise: Splitting a Booking Platform Into Cells

**Scenario:** A booking SaaS serves 2,000 tenants. Most are small, yet 20 large tenants drive 45% of traffic. Currently one shared cluster runs APIs, a relational database, queues, and caches. Peak hours suffer noisy neighbors; new releases hit every customer simultaneously. The team can deploy a single cell via IaC, but lacks a placement service or automated tenant migrations.

Design an evolution plan:

1. **Access/workload profile:** analyze traffic, DB TPS, connections, queue depth, storage, tenant skew, and peak profiles.
2. **Cell boundaries:** choose tenant cohorts, dedicated cells for large tenants, or a hybrid approach; explain blast radius and cost.
3. **Stamp:** parameterize networking, compute, DB, queues, caches, IAM, monitoring, backups, and versions.
4. **Control plane:** define inventory, placement, assignment states, routers, cache TTLs, and mutation permissions.
5. **Capacity:** use load tests to size database/compute/queue limits; calculate tenant counts per profile and post-zone-loss headroom.
6. **Isolation:** choose database-per-cell vs shared cluster/schemas; specify tenant authorization and backup/restore boundaries.
7. **Migration:** choose offline vs snapshot+delta sync; describe fencing, cutover, routing versions, rollbacks, and reconciliation.
8. **Fleet releases:** design canary cells and wave rollouts, version skew policies, and schema coexistence support.
9. **Operations:** cell/fleet dashboards, alerts for near-capacity, degraded cells, drift, and restores.
10. **FinOps/Well-Architected:** estimate baseline cost, cost per tenant, shared dependencies, and residual risks.

Minimum design summary table:

| Decision | Choice | Rationale | Verification |
|---|---|---|---|
| Cell placement | Tier + workload based, with dedicated cells for large tenants | Curb noisy neighbors and cap blast radius | Skewed load tests |
| Tenant registry | `tenant_id` → `cell_id` + `routing_version` | Stable routing and stateful migrations | Stale cache/split assignment tests |
| Data isolation | Dedicated database per cell | Bound connections/IO and backup scopes | Tenant isolation + restore drills |
| Capacity triggers | DB TPS, p95, connections, queue age | Detect real bottlenecks | Capacity tests and forecasts |
| Migration | Snapshot + delta sync + fencing | Minimize downtime for large datasets | Reconciliation and rollback drills |
| Fleet release | Canary followed by wave rollouts | Bound blast radius of new versions | SLI gates and version inventory |

**Completion Criteria:** Reviewers must clearly see what a cell contains, how tenants are assigned, what triggers a new cell, who is impacted when a cell fails, how data migrates, and who owns every operation. Any unmeasured numbers must be flagged as assumptions requiring measurement.

## 19. Key Takeaways

- A **cell** is a bounded serving and isolation unit aimed at shrinking blast radius and providing predictable capacity.
- A **deployment stamp** is a versioned, parameterized deployment template with a defined lifecycle for spinning up consistent cells.
- The **control plane** manages placement, inventory, and lifecycle; the **data plane** serves requests and business data.
- **Cell boundaries** should reflect workloads, tenants, data, regions, SLOs, and cost—not raw customer count alone.
- **Capacity limits** must account for bottlenecks and post-failure headroom; provision new cells before capacity runs dry.
- **Tenant routing** needs versioned assignments, caching, and in-cell authorization checks.
- **Migrations** require a single source of truth, snapshots/deltas, fencing, cutover, reconciliation, and a rollback plan.
- **Shared dependencies** can still cause correlated failures; design and test them as part of the fleet.
- **Automation and governance** keep stamps, releases, backups, security, and compliance consistent as cell count grows.

Cell-based architecture and deployment stamps turn scaling into controlled replication of smaller units, each with explicit limits, owners, and recovery behavior. The core payoff is bounded blast radius and predictable capacity; in return, teams must invest in placement, routing, migration, and fleet governance. Adopt this pattern only when reliability, isolation, or growth benefits outweigh the operational complexity it introduces.
