# Choosing Managed Services and Defining Remaining Responsibilities

When deploying a database in the cloud, a team can self-install the database on virtual machines, use a managed database platform, or select a specialized data service. The more managed a service is, the more operational tasks the provider typically takes over—such as infrastructure provisioning, hardware replacement, backups, platform patching, or failover. However, **a managed database does not mean the provider is responsible for all of your data and application reliability**.

The team is still responsible for choosing the configuration, data model, access permissions, retention policies, availability level, recovery objectives, cost strategy, and verification methods. A database with automated backups enabled can still cost a business hours of downtime during an incident if restores have never been tested. A database with encryption enabled by default can still leak data if application permissions are overly broad or snapshots are shared improperly.

This lesson is part of the **Database Architecture** chapter of the Cloud Architecture module. The focus is on choosing an appropriate managed service level and clarifying the boundary of responsibilities between the cloud provider and the development/operations teams. Decisions must tie back to business requirements and trade-offs across reliability, security, performance, scalability, cost, and operations under a Well-Architected mindset.

After this lesson, you can:

- Distinguish self-managed databases on IaaS, managed database platforms (DBaaS), and cloud-native database services.
- Identify what the provider handles and what the customer must still execute.
- Evaluate responsibilities for HA, backup/restore, DR, patching, versioning, security, and data access permissions.
- Select service configurations based on workload, RPO/RTO, performance, region, and budget.
- Design monitoring, recovery testing, change management, and incident response procedures.
- Compare total cost and vendor lock-in risks.
- Build a checklist and responsibility matrix to take a managed database into production.

## 1. What Is a Managed Database?

Every database requires compute, memory, storage, networking, an operating system or runtime, an engine, backups, monitoring, and recovery procedures. The difference across models primarily lies in **who provides, who operates, and who makes decisions** for each layer.

In a self-managed VM model, the team typically installs and configures the database, administers the OS, and handles patching, replication, backups, monitoring, and failover. With a managed database, the provider absorbs part of the underlying platform work behind APIs/consoles and a service SLA. The team still manages schemas, queries, data permissions, workload configuration, and verifies that business objectives are met.

### Common Management Levels

| Model | Provider Typically Manages | Customer Typically Manages |
| --- | --- | --- |
| **Self-managed database on VMs (IaaS)** | Physical infrastructure, hypervisor, and portions of networking/disks/VMs per service | OS, database engine, patching, replication, backups, restores, HA, monitoring, and data |
| **Managed database in the cloud (DBaaS)** | Provisioning, underlying OS/runtime, partial patching, backup/HA primitives, and hardware replacement per feature/SKU | Schema, queries, indexes, users/roles, network exposure, encryption policies, retention, HA/DR configuration, restore testing, and cost |
| **Serverless/elastic managed database** | Platform provisions and scales compute/storage according to service semantics | Data model, quotas/capacity guardrails, concurrency, cost controls, access, consistency, backup/restore policies, and testing |
| **Specialized SaaS database** | Most of the platform and product operations | Tenancy, data lifecycle, permissions, connectivity, configuration, integrations, and enterprise compliance obligations |

This is a broad classification. Actual boundaries depend on the provider, engine type, version, region, tier/SKU, and contract. Some managed services still require the customer to schedule maintenance; some have automated backups, yet PITR is only available after enabling an option or selecting a suitable retention window.

### Managed Does Not Mean Serverless

**Managed** describes how much operational work the provider assumes. **Serverless** describes how the service provisions/prices compute or how users consume capacity without managing instances in the traditional way. A database can be managed while running continuously on fixed provisioned capacity; a serverless service still has quotas, limits, cold-start/scaling latency, and usage-based costs.

Never choose a service simply because its name includes "managed" or "serverless." Identify which operational tasks you want to offload, which capabilities you require, and which responsibilities remain with your organization.

## 2. The Shared Responsibility Model

The cloud operates under a **shared responsibility** model: the provider secures the underlying infrastructure and the layers specified by the service; the customer secures workloads, data, identities, and configurations within their scope. With a managed service, the boundary may shift up to the database engine layer, but customer responsibility for data remains.

~~~mermaid
flowchart TD
    subgraph CSP["Cloud Provider — Service-dependent layers"]
        PHY["Datacenter / hardware"]
        HYP["Hypervisor / virtualization layer"]
        BASE["Base OS / runtime<br/>per DBaaS scope"]
        ENGINE["Engine operations / base patching<br/>per service configuration"]
        PHY --> HYP --> BASE --> ENGINE
    end
    subgraph CUSTOMER["Customer — Workload and data responsibilities"]
        ID["Identity, IAM, secrets"]
        NET["Network, private access, firewall"]
        DATA["Schema, data, classification"]
        CFG["Configuration, HA/DR, retention"]
        APP["Application, queries, connection pool"]
        TEST["Restore testing, runbooks, cost"]
    end
    ENGINE --> DATA
    ID --> APP
    NET --> APP
    DATA --> CFG
    CFG --> TEST
~~~

This diagram is conceptual, not a responsibility contract for a specific SKU. A provider may manage database patching and backup infrastructure, but the customer must still select maintenance windows, retention, access permissions, supported versions, and verify that restores meet business requirements.

### 2.1. Responsibilities That Do Not Disappear with a Managed Service

A managed service reduces installation effort, yet the team remains responsible for:

- Defining what data is stored, classifying sensitive data, and setting retention durations.
- Designing tables, keys, transactions, indexes, partitions, and queries.
- Managing users, roles, service identities, secrets, and database-level permissions.
- Allowing connections only from authorized networks and identities.
- Choosing region, tier, storage configuration, HA, and backups.
- Setting up monitoring, alerts, access logging, and auditing.
- Testing restores, failovers, upgrades, and post-failure recovery against RTO/RPO.
- Controlling costs, quotas, data growth, and egress.
- Maintaining migration, export, and end-of-life transition plans for the service/engine.

### 2.2. Sample Responsibility Matrix

| Task | Provider Typically Handles | Customer Must Confirm/Execute |
| --- | --- | --- |
| Datacenter, power, hardware | Operates and replaces per SLA | Select appropriate region/zones, understand SLA scope |
| VM/host infrastructure | Platform provisioning and maintenance | Choose tier/capacity, set quotas and budgets |
| Base OS/runtime | Patches/manages when included in DBaaS | Review maintenance policies, notices, and impact |
| Database engine | Installation, backup/patching, or failover per feature | Select engine/version/parameters, ensure app compatibility |
| Schema and data | Provides storage capability | Design, classification, migrations, retention, and integrity |
| IAM and database roles | Provides identity/access primitives | Grant least privilege, rotate, review, and revoke |
| Network | Provides VPC/private endpoint/firewall primitives | Configure routes, subnets, sources, TLS, and segmentation |
| Backup service | Runs backups per configuration | Enable/set retention, PITR, encryption, cross-region copies if needed, and test restores |
| HA/failover | Provides mechanism and supporting infrastructure | Choose topology, verify client retries, measure downtime and dependencies |
| DR | Provides replication/backup options | Define RTO/RPO, runbooks, drills, and failback |
| Platform monitoring | Service-level metrics and health | Workload dashboards, alerts, query performance, and business SLIs |
| Cost | Publishes service pricing | Sizing, budgets, egress, storage growth, and cost allocation |
| Incidents | Remediates provider-owned platform issues | Detect impact, engage support, decide failover, and communicate |

These columns are not rigid walls. For instance, the provider executes backups, but **recoverability** is a shared outcome: the provider must offer a reliable feature, and the customer must configure and test the recovery process.

## 3. Selecting a Managed Service Based on Workload Requirements

Do not start with a list of products. Start with the workload and data:

1. Is the data relational or key-value/document/time-series/graph?
2. What are the read/write ratio, transaction needs, consistency requirements, and access patterns?
3. What are initial volume, growth rate, bursts, and peak concurrency?
4. What are p95/p99 latency targets, throughput, and critical queries?
5. What are the SLOs, RTO, RPO, maintenance windows, and user scope?
6. What are the data residency, encryption, audit, and compliance requirements?
7. What are the team's skills, acceptable self-management level, and budget?
8. What capabilities exist for export, restore, engine switching, or provider migration?

### High-Level Selection Map

| Need | Potentially Suitable Database Type | Items to Verify |
| --- | --- | --- |
| Relationships, transactions, joins, and constraints | Managed relational (PostgreSQL/MySQL/SQL Server or appropriate engine) | Isolation levels, connections, extensions, replicas, failover, backups |
| Key-value/document with defined access patterns | Managed NoSQL | Partition keys, consistency, transaction scope, hot partitions, indexes, TTL |
| Short-lived cache/sessions | Managed in-memory cache | Persistence, eviction, replication, failover, private access |
| Large-scale data analytics | Data warehouse/lakehouse service | Ingestion, query concurrency, storage/compute separation, cost per query |
| Time-series/metrics | Managed time-series database or equivalent platform | Retention, downsampling, cardinality, compression |
| Graph traversal | Managed graph database | Query patterns, throughput, graph size, and portability |

A managed database does not automatically make a data model fit. Choosing NoSQL "to scale" when you still need arbitrary joins, cross-aggregate transactions, and ad-hoc queries merely shifts cost from infrastructure operations into application complexity.

### Early Elimination Criteria

Remove a service from the shortlist when a mandatory requirement is not met, for example:

- Engine/region fails data residency or contractual obligations.
- Essential extensions, collations, or SQL features are unsupported.
- RPO/RTO exceeds committed targets.
- Private network access cannot be enforced per policy.
- Lacks export/restore capabilities needed for an exit plan.
- Quotas or connection limits cannot handle measured peaks.
- Projected cost under realistic load exceeds the approved budget.

## 4. HA, Backup, Restore, and DR: Who Does What?

This is where managed databases are most often misunderstood. A provider can manage replication or snapshots, yet cannot know which point in time your business must recover to, which data must be preserved, or whether your application will actually keep serving after a failover.

### 4.1. High Availability

HA aims to minimize disruption when a component or failure domain fails. A service may support standby instances, multi-AZ deployments, replication, or automatic failover. The customer must:

- Select the right HA configuration and understand which failure scopes are covered.
- Deploy applications across multiple zones with compatible network/connection settings.
- Handle DNS/endpoint changes, connection resets, and safe retries.
- Monitor replication lag, health, failover events, and recovery duration.
- Test failover and measure its impact on in-flight transactions.

**HA does not replace backups.** Replication can propagate accidental deletes or corrupted data to replicas. When you need to roll back to before a logic bug, backups/PITR play a distinct role.

### 4.2. Backups and Point-in-Time Recovery

The provider may run snapshots or continuous backups according to the service tier. The customer must still decide:

- How many days/months of retention are required by business and regulatory rules?
- Is point-in-time recovery (PITR) needed?
- Are backups encrypted with the appropriate key?
- Should snapshots be copied to another account/region?
- Who is authorized to restore, copy, or delete backups?
- During a restore, how will the application switch endpoints and reconcile data?

A successful backup does not guarantee a successful restore. Rehearse restores in an isolated environment, time the procedure, validate the data, and document cutover steps.

### 4.3. RTO and RPO

- **RTO (Recovery Time Objective):** maximum downtime the business accepts to restore service.
- **RPO (Recovery Point Objective):** maximum acceptable data loss, expressed in data time.

For example, a scheduling workload targets a 60-minute RTO and a 5-minute RPO. This must be proven through topology, backups/replication, restore/failover procedures, access permissions, and the time required for the application to resume serving. Choosing a multi-AZ feature alone does not prove a 60-minute RTO; the configuration and failure modes must be tested.

### 4.4. Disaster Recovery

DR handles incidents beyond normal HA scope, such as a region outage, account failure, widespread data deletion, or compromise. Common models:

| Model | Standby Resources | Trade-offs |
| --- | --- | --- |
| Backup and restore | Backups stored elsewhere; provision infra when needed | Lower baseline cost, typically longer RTO |
| Pilot light | Core data/minimal infra kept ready | Requires scaling up and cutover during a disaster |
| Warm standby | Scaled-down copy running in a standby region | Higher cost, faster recovery if rehearsed |
| Active-active | Multiple regions serving concurrently | Complex writes, conflicts, consistency, and cost |

A managed database may offer cross-region replicas or backup copies, but the customer must define replication mode, failover authority, data residency, failback, and how the application handles dual-region writes.

## 5. Patching, Versions, and Maintenance

Managed databases typically reduce OS administration and part of database patching. However, maintenance schedules, version support lifecycles, and engine changes still affect applications.

The team must clarify:

- Which layers does the provider auto-patch: host, OS, engine, minor versions, or major versions?
- Can maintenance windows be pre-configured? Are there advance notices and deferral options?
- Do failovers/restarts happen during maintenance?
- Do versions nearing end-of-support have extended support policies and extra fees?
- Which parameters/extensions are unsupported or modified?
- Is there a staging environment to test upgrades before production?
- Is a pre-change backup/snapshot sufficient for rollback, and how long does a restore take?

### Minor and Major Upgrades

Minor updates typically deliver patches or compatibility improvements within the same version branch, yet still require reviewing release notes and testing the application. Major upgrades can alter behavior, extensions, the query planner, replication, or protocols; they require a migration plan, compatibility testing, and a planned window.

**Do not assume version rollback is as simple as rolling back application code.** Once a database writes in a new schema or storage format, it may no longer be compatible with the older version. Upgrade plans require backward-compatible migrations or restoring into a new environment and cutting over.

### Recommended Maintenance Workflow

1. Track provider support schedules and maintenance notices.
2. Read release notes, CVEs, and relevant behavior changes.
3. Clone/snapshot representative data into a protected test environment.
4. Run integration, load, query-plan, and failover tests.
5. Finalize the window, owner, backup plan, and rollback/recovery path.
6. Execute using a supported rollout flow while monitoring metrics and errors.
7. Reconcile post-maintenance and update runbooks and version inventories.

## 6. Security: Managed Databases Do Not Prevent Misconfiguration

Providers may secure the datacenter, host, hypervisor, and underlying DBaaS layers. Customers remain responsible for controlling identity, data permissions, networking, encryption policies, secrets, auditing, and information lifecycles.

### 6.1. Identity and Least Privilege

- Use service identities/managed identities instead of long-lived credentials wherever possible.
- Separate roles for migrations, application runtime, read-only analytics, and DBAs.
- Never use an admin account in the application's connection pool.
- Revoke access and rotate secrets on a defined schedule.
- Restrict permissions to create snapshots, export, restore, change encryption keys, and share backups.
- Audit changes to roles, policies, parameters, and endpoints.

### 6.2. Network Boundaries

- Prefer private endpoints/private subnets where appropriate.
- Never expose a database publicly to all IPs simply for convenience.
- Restrict source security groups/firewalls, ports, and routes.
- Enforce TLS from client to database; verify server identity per driver/engine.
- Use dedicated administrative access paths with logging and access approval.
- Account for DNS, NAT, private links, and egress across multi-account/multi-VPC setups.

### 6.3. Encryption and Key Management

Distinguish encryption at rest from encryption in transit. The provider may encrypt storage by default, but the customer must define key ownership, rotation, KMS/key-manager permissions, snapshot copy behavior, and what happens if a key is disabled or deleted.

If using customer-managed keys, revoking a key prematurely can render databases and backups unreadable. Key policies and recovery procedures must be part of the DR plan.

### 6.4. Data Lifecycle and Auditing

Teams must define retention, deletion, masking, tokenization, backup retention, and data export permissions. Deleting a record in the live database does not necessarily purge copies in snapshots or exports immediately. Understand the service's lifecycle and deletion semantics.

Audit logs can capture access and changes, but should not be enabled indiscriminately without considering cost, retention, and sensitive data exposure. Forward logs to independently protected storage when investigative integrity is required.

## 7. Performance, Scaling, and Service Limits

Managed databases eliminate hardware chores, but they do not eliminate query, index, lock, connection, or storage bottlenecks.

### Limits to Verify

| Category | Example Limits | Customer Responsibility |
| --- | --- | --- |
| Compute | CPU, memory, serverless capacity, burst credits | Sizing, autoscaling guardrails, peak testing |
| Connections | Max connections, pools, proxy capacity | Pool sizing, concurrency limits, and connection reuse |
| Storage | Capacity, IOPS, throughput, auto-grow limits | Forecasting, alerting, retention, performance testing |
| Queries | Transaction duration, locks, query concurrency, timeouts | Indexes, query plans, isolation levels, workload tuning |
| Replication | Lag, read replica limits, failover semantics | Define consistency and read-after-write behavior |
| API/control plane | Provisioning rate, quotas, instance/replica counts | Quota management and scaling procedures |
| Network | Throughput, connection paths, cross-zone transfer | Network design, latency, and data transfer costs |

### Read Replicas Do Not Automatically Speed Up Queries

Read replicas can offload read traffic, but:

- Replication lag causes stale data to appear on read paths.
- Heavy queries can still saturate a replica.
- Some systems disallow certain query types or transaction semantics on replicas.
- Failover/replica promotion can change endpoints and roles.
- Replicas add compute, storage, and network costs.

Applications must classify which queries tolerate eventual consistency and which must read from the writer. Do not route every `SELECT` to a replica just because an endpoint exists.

### Connection Pools and Autoscaling

Suppose an application runs 12 instances and each opens a pool of up to 20 connections—a potential total of 240 connections. If an autoscaler scales to 40 instances, the same config can demand 800 connections. The database may be overwhelmed even when application CPU has headroom.

Calculate:

~~~text
Potential connections
  = max application replicas × pool maximum per replica
  + worker connections
  + admin/monitoring/migration connections
~~~

Reducing pool sizes, using a connection proxy when appropriate, and capping max replicas/concurrency help protect the database. A proxy does not remove query concurrency or DB resource limits; it only changes how connections are managed.

### Workload-Based Capacity Planning

Benchmarks should simulate:

- Realistic read/write ratios and query mixes.
- Transaction durations, lock contention, and connection counts.
- Payloads, indexes, partitions, and storage growth.
- Peak bursts and sustained load durations.
- Failover/replica lag and load when a node/zone is lost.
- Concurrent background jobs, backups, vacuum/maintenance, and analytics.

Measuring average CPU or total RPS alone is insufficient for sizing. Track p95/p99 query latency, connection saturation, lock waits, IOPS, cache hit rates, replication lag, and error rates.

## 8. Monitoring and Observability: Who Watches What?

Providers typically expose service health and infrastructure metrics. Application teams must combine those with query, connection, business operation, and SLO metrics.

### Platform Metrics

- Instance/compute utilization and memory.
- Storage utilization, IOPS, and latency.
- Connection counts and connection errors.
- Replication lag and replica health.
- Backup success, backup age, and restore events.
- Failover, restart, maintenance, and throttling events.
- Quotas/service limits approaching thresholds.

### Application-Level Metrics

- Query latency by operation group and percentile.
- Transaction duration, deadlocks, lock waits, and retries.
- Pool active/idle/waiting counts, timeouts, and connection acquisition duration.
- Error rates by SQLSTATE/driver/provider.
- Business SLIs such as booking commit success, payment reconciliation, and stale-data rates.
- Cost per workload/tenant where allocatable.

### Logging and Auditing

Do not log full SQL parameters or sensitive payloads by default. Use query fingerprints, durations, error codes, and trace/correlation IDs for troubleshooting. Access to query logs and audit logs must be restricted, have defined retention, and be monitored.

### Risk-Driven Alerts

| Alert | Why It Matters |
| --- | --- |
| Backup failed or backup age exceeds threshold | Risk of missing RPO |
| Storage nearly full | Writes may fail or service may halt |
| Connection pool near exhaustion | API timeouts even when database CPU is low |
| Replication lag exceeds threshold | Stale read paths or DR missing targets |
| Unexpected failover/restart | Check downtime and application errors |
| Rising query p95/p99 | Detect bottlenecks before SLO breach |
| Sudden quota/cost spike | Prevent runaway scaling or unexpected charges |
| Unusual access denied events | Sign of misconfigured policy or suspicious activity |

## 9. The True Cost of a Managed Database

An instance's list price is only one piece. Estimate Total Cost of Ownership:

- Compute/base capacity and standby/HA replicas.
- Provisioned or consumed storage, IOPS, and throughput.
- Backup storage, snapshot copies, PITR logs, and retention.
- Read replicas, cross-region replication, and data transfer.
- Proxies, private endpoints, NAT, monitoring, auditing, and log ingestion.
- Licensing/engine/extended support or premium features.
- Migration, testing, staging environments, and DR drills.
- Engineering time managing queries, access, incidents, schemas, and compliance.

### Managed vs. Self-Managed

A managed database may cost more on the raw infrastructure bill than VMs, while cutting patching, backup operations, and HA maintenance effort. VMs may look cheaper on the base invoice, yet total cost rises once you add on-call staffing, automation, downtime risk, storage, and failover testing.

Compare using **TCO**:

~~~text
TCO =
  compute + storage + IOPS + backup + replication
  + network/egress + support/license
  + monitoring/security
  + migration/DR/staging
  + operational labor
  + expected incident/recovery cost
~~~

Not every factor converts cleanly to money; document assumptions explicitly. TCO should cover baseline load, peaks, 12–36 month growth, and failure scenarios.

### Serverless/Elastic Pricing

Usage-based pricing per request/capacity/compute consumed can be economical for spiky workloads. However, steady workloads or heavy queries can cost more than provisioned configurations. Measure against real patterns and set budget alerts, quotas, or capacity caps.

## 10. Portability and Vendor Lock-In Risks

Managed databases often have cloud-specific management APIs, extensions, backup formats, replication mechanisms, and features. Using specialized features can add immediate value while making future migration harder.

You do not need to avoid every proprietary service. Understand **exit costs and strategic recoverability**:

- Can schemas, data, indexes, roles, and sequences be exported?
- Can backups be restored outside that service/region, or only within the same engine?
- Which extensions or stored procedures are provider-specific?
- Are data types, collations, transaction isolation, and SQL dialects portable?
- Can CDC/replication sync to a different engine?
- Do DNS, connection strings, secrets, IAM, and networking depend on proprietary APIs?
- How will migration downtime, data validation, and rollback be handled?
- Are there significant egress fees or long export times?

### Portability Strategies

1. **Use common standards where sensible:** widely supported SQL, drivers, schema migrations, and protocols.
2. **Encapsulate adapters:** reduce direct coupling between application logic and proprietary management APIs.
3. **Maintain export/restore runbooks:** test them periodically, not just on paper.
4. **Manage data contracts:** version schemas and events; avoid relying on implicit engine behaviors.
5. **Accept proprietary choices intentionally:** record benefits, exit costs, and revisit triggers in an ADR.

Portability is not a goal at all costs. If a cloud-native service fulfills a critical requirement that portable engines cannot, choosing proprietary can be sound when the risk is accepted and a mitigation plan exists.

## 11. Migrating to a Managed Database

Moving from a self-managed database or another service to DBaaS requires controlled data validation and downtime management.

### Key Steps

1. **Inventory:** engine/version, extensions, schemas, data volume, roles, jobs, triggers, stored procedures, connections, and queries.
2. **Compatibility assessment:** check types, collations, SQL dialects, features, drivers, isolation, and limits.
3. **Target design:** region, network, identity, HA, backups, encryption, parameters, quotas, and sizing.
4. **Data migration:** snapshot/export-import, logical replication, or suitable migration tools.
5. **Validation:** row counts, checksums, constraints, nulls, sequences, query outputs, and business reconciliation.
6. **Performance testing:** representative workloads, indexes, connection pools, query plans, and peaks.
7. **Cutover:** planned write freeze or dual-write/CDC; swap endpoints/secrets; monitor errors.
8. **Rollback window:** define fallback criteria, reverse sync direction, and cutoff time.
9. **Decommission:** purge data per policy after confirming backups, audit, and approvals.

### Avoid Uncontrolled Dual-Writes

Writing simultaneously to source and target from the application can cause the two databases to diverge if one commits and the other fails. Prefer CDC/logical replication or a migration strategy with checkpoints and reconciliation; if dual-writes are unavoidable, enforce idempotency, ordering, and repair mechanisms.

Do not shut down the source database immediately after switching DNS. Keep it through the approved rollback window with restricted permissions and a plan for syncing post-cutover writes.

## 12. Building a Managed Database Selection Matrix

A reusable evaluation framework:

| Criterion | Question | Evidence Level |
| --- | --- | --- |
| Business fit | Does the engine satisfy transactions, consistency, and access patterns? | Schema/PoC/tests |
| Reliability | Do HA, backup, restore, failover, and DR meet RTO/RPO? | Failure/restore drills |
| Security | Private access, IAM, encryption, audit, key control? | Threat model and access tests |
| Performance | p95/p99 latency, throughput, concurrency, replica lag? | Workload benchmarks |
| Operability | Maintenance, upgrades, alerts, support, and runbooks? | Runbook exercises |
| Cost | Baseline/peak/growth/DR TCO? | Estimates + billing model |
| Portability | Export, restore, migration, dependencies? | Restore/export tests |
| Compliance | Region, retention, deletion, audit evidence? | Policy/contract validation |

### Weighted Scoring

You can score 1–5, but mandatory requirements should act as **gates** before summing scores. For example, a service failing data residency cannot be compensated by a low cost score.

Illustrative weights:

| Criterion | Assumed Weight |
| --- | ---: |
| Business/data fit | 20% |
| Reliability/restore | 20% |
| Security/compliance | 20% |
| Performance/scale | 15% |
| Operations | 10% |
| TCO | 10% |
| Portability | 5% |

Weights must be agreed upon by both business and engineering owners. If two services score closely or estimates remain weak, run another PoC rather than claiming a single objective winner.

## 13. Practical Example: Choosing a Managed Relational Database for a Booking Service

**Hypothetical scenario:** A scheduling platform has a Booking Service and a Payment Service. The Booking Service needs transactions to prevent double-booking a time slot; the engineering team has six developers and no dedicated 24/7 DBA. Internal targets are a 60-minute RTO, a 5-minute RPO, and p95 common read latency under 100 ms at projected load. These are practice requirements, not verified guarantees.

### Options

| Option | Benefits | Trade-offs |
| --- | --- | --- |
| Self-managed PostgreSQL on VMs | Deep control, customization, broad extensions | Team operates OS, patching, backups, replication, failover, and on-call |
| Managed PostgreSQL-compatible relational DB | Less platform management, service-provided HA/backup options | Version/extension/limit constraints, still requires config and restore testing, managed fee |
| Managed NoSQL | Scales well for key-based access patterns | Requires reworking transactions, uniqueness, relationships, and queries; not an automatic fit |

### Proposed Decision

Choose a **managed relational database** for the Booking Service once a PoC confirms required engine/extensions and capabilities. Use transactions and constraints to enforce anti-double-booking rules; deploy HA per service-supported options; enable backups/PITR with appropriate retention. Configure private connectivity and service identities following least privilege.

### Divided Responsibilities

| Party | Responsibilities |
| --- | --- |
| Provider | Managed database infrastructure, maintenance of service-scoped layers, backup/HA primitives per selected config |
| Platform team | Region/tier, VPC/private routes, security policies, parameters, baseline monitoring, budgets, and quotas |
| Backend team | Schemas, constraints, migrations, queries, transactions, connection pools, retries, and idempotency |
| Security | Role reviews, secret/key policies, auditing, data classification, and access reviews |
| SRE/Operations | Dashboards, alerts, runbooks, restore drills, failover exercises, and incident response |
| Product/Data owner | Retention, RTO/RPO, downtime windows, deletion rules, and acceptable data loss |

### Pre-Production Gates

- Concurrent booking tests proving only one transaction succeeds for a single slot.
- Restore drills proving recovery time and data integrity meet agreed targets.
- Failover tests verifying the application reconnects without creating duplicate transactions.
- Load tests proving query latency and connection pooling under projected load.
- Access tests confirming the backend cannot be reached from unauthorized networks.
- Cost estimates covering storage, backups, HA replicas, network, logs, and operational effort.
- Export/restore tests demonstrating data can be extracted per the portability plan.

## 14. Lab: Defining Responsibility Boundaries for DBaaS

**Scenario:** An e-commerce application currently runs self-managed PostgreSQL on VMs. The team wants to migrate to a managed database to reduce operational toil. The workload peaks at 2,000 transactions/hour, 70% reads / 30% writes; data size is 1.5 TB growing roughly 5% per month. Targets are 45-minute RTO and 5-minute RPO. Customer data must be accessed privately; audit logs must be retained for 12 months. These are simulated figures.

### Task 1 — Define Requirements

List mandatory requirements: engine/version/extensions, data residency, private access, TLS, IAM, HA, backup/PITR, RTO/RPO, query latency, connections, storage growth, and budget.

### Task 2 — Build a Responsibility Matrix

For each item, clearly assign:

- Executed by provider.
- Configured by platform team.
- Verified by database/backend team.
- Approved by security.
- Policy owned by data owner.

Do not leave generic single cells like "backup," "security," or "monitoring"; split what the provider supplies from what the customer must execute.

### Task 3 — Design HA/DR

Select an appropriate topology, describing failover, backups/PITR, cross-region copies if needed, and recovery steps. Explain how RTO/RPO will be tested. Distinguish which incidents HA handles versus those requiring restore or DR.

### Task 4 — Create a Maintenance Plan

Define version policies, maintenance windows, staging tests, pre-upgrade backups, monitoring, and rollback/recovery procedures.

### Task 5 — Calculate TCO

Itemize compute, storage, IOPS, 12-month backups, replication, egress, monitoring, support/licensing, staging/DR, and operational labor. Compare self-managed VMs against managed DBaaS at baseline and peak load.

### Task 6 — Test Portability

Export schemas/data, roles, and database objects; test restoring into an independent environment or another compatible version. List which extensions, SQL behaviors, and tools create lock-in.

### Deliverables

| Deliverable | Contents |
| --- | --- |
| Service shortlist | 2–3 options, elimination gates, and rationale |
| Responsibility matrix | Owner/RACI per layer |
| HA/DR plan | Diagrams, RTO/RPO, and failure scenarios |
| Security plan | IAM, network, TLS, keys, audit, retention |
| Maintenance plan | Versions, patches, tests, approvals, and recovery |
| Cost model | 12–36 month TCO, assumptions, and sensitivity |
| Validation plan | Load, failover, restore, access, and export tests |
| ADR | Context, options, decision, consequences, and review triggers |

## 15. Well-Architected Review

| Pillar | Questions for Managed Databases |
| --- | --- |
| **Operational Excellence** | Are owners, runbooks, maintenance plans, version inventories, IaC, alerts, and restore drills in place? |
| **Security** | Is the provider/customer boundary clear? Are IAM least privilege, private networking, TLS, keys, auditing, and retention enforced? |
| **Reliability** | Have HA, backups, restores, RTO/RPO, failover, quotas, and dependencies been tested? |
| **Performance Efficiency** | Does the engine fit the workload, are queries/indexes/connections/IOPS measured at peak, and is replica lag controlled? |
| **Cost Optimization** | Does TCO include standby, backups, egress, logs, support, staging, and labor? Are growth alerts configured? |
| **Sustainability** | Is sizing right-sized, retention reasonable, and unnecessary replicas/backups or inefficient queries avoided? |

## 16. Common Pitfalls

**Assuming "managed" means no DBA or data owner is needed.** Someone still must design schemas, queries, access controls, backup policies, and recovery procedures.

**Assuming provider-run backups are enough.** You must configure retention, encryption, restore permissions, and execute restore drills.

**Conflating HA with DR.** HA handles certain component/zone failures; DR addresses broader incidents like losing a region or widespread data corruption.

**Ignoring version and maintenance policies.** Services can alter engines, limits, or deprecate versions; applications need compatibility testing.

**Opening public access for convenience.** Private networks, identities, and TLS must be configured around trust boundaries.

**Granting admin permissions to applications.** Runtime accounts should hold least-privilege permissions per operation.

**Scaling applications without counting connections.** Multiple replicas can exhaust the database's max connection limit.

**Using read replicas without watching replication lag.** Queries requiring the latest data can read stale state.

**Comparing prices using only compute/hour.** Backups, HA, IOPS, egress, support, and labor can flip the TCO outcome.

**Having no exit plan.** When switching engines/regions, extensions, backup formats, and egress can incur steep costs.

**Skipping failover/restore tests.** Console checkboxes do not prove the application keeps working when an incident hits.

## 17. Pre-Production Checklist for Managed Databases

- [ ] Workload, engine, consistency, transactions, and access patterns are defined.
- [ ] Provider, tier/SKU, region, version, and quotas meet mandatory requirements.
- [ ] Responsibility matrix separates provider, platform, application, security, and data owner duties.
- [ ] IAM/service identities and database roles follow least privilege; secrets rotate.
- [ ] Database is private; firewalls/routes/TLS and administrative access are controlled.
- [ ] Encryption at rest/in transit, key ownership, backup encryption, and auditing are verified.
- [ ] HA topology, failover behavior, and remaining post-failure capacity have been tested.
- [ ] Backups, PITR, retention, cross-account/region copies, and restore runbooks are established.
- [ ] RTO/RPO are measured via restore/failover drills—not assumed from service descriptions.
- [ ] Version/patch/maintenance windows, compatibility tests, and recovery plans are documented.
- [ ] Connection pools, queries, indexes, IOPS, storage growth, replication lag, and quotas are monitored.
- [ ] Dashboards/alerts cover service metrics, application metrics, and business SLIs.
- [ ] TCO accounts for compute, storage, backups, replicas, egress, monitoring, support, and labor.
- [ ] Export/restore, portability, and vendor lock-in have been evaluated.
- [ ] Migrations/cutovers/rollbacks include validation and reconciliation.
- [ ] Owners, runbooks, support paths, an ADR, and periodic review triggers exist.

Managed databases offload part of the underlying infrastructure work to the provider, letting teams focus more on products and data. Yet **responsibility for correctness, access control, recovery, performance, cost, and compliance remains on the customer side**. A strong choice is not merely a feature-rich service, but one with clear responsibility boundaries, workload fit, and proof through real-world testing: access, load, failover, restore, maintenance, and data export.
