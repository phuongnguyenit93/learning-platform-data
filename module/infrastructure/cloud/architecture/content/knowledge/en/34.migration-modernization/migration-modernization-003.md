# Retain, Retire, Relocate, Rehost, Replatform, Repurchase, and Refactor

## 1. Seven Strategies in Cloud Architecture Decisions

When moving a system to the cloud, the first question is not “VMs, containers, or serverless?” but **what value does this system still create, how much must it change, and what risks can the organization accept?** The **7R** model is a decision classification framework for each application or workload:

1. **Retain** — keep in the current environment.
2. **Retire** — decommission because it is no longer needed.
3. **Relocate** — move the virtualization environment as-is to compatible cloud infrastructure.
4. **Rehost** — move the application to cloud infrastructure with minimal changes.
5. **Replatform** — adjust the underlying runtime platform to leverage cloud services without a full redesign.
6. **Repurchase** — replace existing software with another product/service, typically SaaS.
7. **Refactor (re-architect)** — substantially change source code or architecture to meet new goals.

These are **seven distinct options**, not seven sequential steps to pass through in order. An application portfolio can use all seven at once; a large system can also apply different strategies to different components.

In the **Cloud Architecture** module, the 7Rs connect business requirements to **networking, compute, data, and deployment** design, while requiring architects to balance five cross-cutting concerns: **reliability, security, scalability, cost, and operations**. “Getting it onto the cloud” is only a technical outcome; a sound decision also requires a business rationale and clear acceptance criteria.

### Distinguishing Migration and Modernization

- **Migration**: changing where a workload runs, where data is stored, or its deployment platform. Goals may include exiting a data center, improving recovery, or meeting contract termination deadlines.
- **Modernization**: changing technology, architecture, or operating model to improve long-term capabilities such as faster releases, autoscaling, fault isolation, or lower maintenance burden.
- A **rehost** can complete migration while leaving technical debt intact. A **refactor** is typically deep modernization and can be rolled out incrementally after migrating.

## 2. Comparing the Meaning and Trade-Offs of Each R

| Strategy | Execution | Typical Fit | Key Benefits | Risks/Limits to Verify |
|---|---|---|---|---|
| **Retain** | Keep application in place with a scheduled re-evaluation plan | On-premises hardware dependencies, legal constraints, no safe migration path yet | Avoids premature changes; protects specialized systems | Ongoing on-premises operating costs, hardware/software lifecycle risk |
| **Retire** | Verify zero active users/dependencies, then shut down, archive, or delete per policy | Duplicate tools, apps no longer serving active processes | Eliminates costs and attack surface | Accidentally breaking integrations, losing required retention data or audit capability |
| **Relocate** | Move VMs and configurations within a compatible virtualization ecosystem | Large VM fleets on supported virtualization needing fast cluster migration | Minimal app changes; preserves familiar tooling | Hypervisor/licensing lock-in, limited use of cloud-native services |
| **Rehost** | Move workload to cloud VMs/IaaS with minimal software changes | Early data center exit; stable app lacking budget for changes | Relatively fast execution, easy to bound scope | Still requires OS/middleware patching, potentially expensive if kept oversized |
| **Replatform** | Swap part of the platform: managed database, containers, managed runtime... | App remains viable but current infrastructure is hard to operate | Reduces admin toil and improves scalability within bounds | Version/driver differences, connection behavior, managed service limits |
| **Repurchase** | Switch to another product, usually SaaS, while adapting processes and data | Standard capabilities such as CRM or helpdesk | Offloads build and self-managed software burden | Subscription fees, integrations, data import/export, customization limits, vendor lock-in |
| **Refactor** | Redesign components, data flows, communication, deployment, or domain model | Core systems needing rapid releases, elastic scaling, better resilience | Unlocks new capabilities aligned with long-term goals | High effort, hard to verify, risk of altering business behavior |

**Degree of change does not equal degree of quality.** A system nearing end-of-life should probably be retired rather than refactored. A stable, low-change application may be better rehosted than split into microservices. Conversely, lifting a fragile design straight into the cloud will not magically produce high availability.

### Commonly Confused Boundaries

**Relocate vs. rehost:** Relocate preserves most of the existing virtualization model by shifting workloads between compatible environments, such as a VM cluster running on a cloud-supported virtualization stack. Rehost moves the OS/application onto new compute resources such as cloud VMs; this may involve converting machine formats, networking, disks, and management tools. Both minimally alter business logic, but the **platform responsibility handoff point** differs.

**Rehost vs. replatform:** Changing VM addresses while keeping a self-managed database service is generally rehost. Moving the database to a managed service—after checking compatibility and updating configurations/connections—is an example of replatform. Running an app in containers does **not automatically** count as replatform or refactor; look at the actual scope of change.

**Replatform vs. refactor:** Replatform mainly swaps infrastructure/runtime layers while keeping the core business structure intact. Refactor significantly alters source code, service boundaries, or communication/data models—such as decomposing order processing into services with explicit API and event contracts.

**Repurchase vs. replatform:** Moving an in-house CRM onto a managed runtime is replatform; replacing it with a SaaS CRM is repurchase because the organization switches products and must migrate data, users, and workflows.

**Retain vs. retire:** Retain means continuing operational accountability and revisiting at a defined date. Retire means ending the application lifecycle after handling data, integrations, access permissions, and audit evidence.

## 3. Gathering Facts Before Choosing an R

7R decisions are made at the **workload/application** level based on evidence. Avoid applying one blanket label across an entire company or deciding solely by programming language.

| Information Group | Questions to Answer | Impact on Decision |
|---|---|---|
| Business value | Who uses it, how often, can it be dropped or replaced by a product? | Prioritizes retire/repurchase vs. long-term investment |
| Criticality | What happens during a 1-hour outage? What are SLA/SLO, RTO, RPO? | Drives HA/DR design, cutover, and rollback approaches |
| Current architecture | OS, runtime, database, batches, queues, VM/hypervisor, support status? | Determines feasibility of relocate/rehost/replatform |
| Dependencies | APIs, DNS, authentication, shared files, devices, job schedules, payment systems? | Sets migration wave order; identifies hybrid connectivity needs |
| Data | Volume, rate of change, sensitivity, allowed storage regions, retention period? | Shapes sync method, data placement, access controls |
| Security & compliance | IAM, encryption, key management, logging, audit requirements, data residency? | Defines landing zone and architectural constraints |
| Costs | Licensing, hardware, network, storage, operations, dual-run, and egress traffic? | Informs TCO and phased affordability |
| Team & timeline | Cloud skills, migration deadline, tolerance for change? | Selects a path safe enough within the available window |

A minimum inventory should record: **application owner, technical owner, environment, criticality, bidirectional dependencies, data sources, constraints, recommended R, supporting evidence, and review date**. If you do not yet know who uses a system, retiring it remains an untested hypothesis.

### Initial Orientation Flow

~~~mermaid
flowchart TD
    A["Assess workload and business requirements"] --> B{"Still needed?"}
    B -- "No" --> R1["Retire: verify dependencies and archive data"]
    B -- "Yes" --> C{"Ready to migrate?"}
    C -- "Not yet" --> R2["Retain: document blockers and review date"]
    C -- "Yes" --> D{"Can function be replaced by a suitable product?"}
    D -- "Yes and cost-effective" --> R3["Repurchase: evaluate SaaS and migrate data"]
    D -- "No" --> E{"Deep architectural change needed to meet goals?"}
    E -- "Yes" --> R4["Refactor: phase delivery and control risk"]
    E -- "No" --> F{"Compatible virtualization platform for full-stack move?"}
    F -- "Yes, fits TCO" --> R5["Relocate"]
    F -- "No / unsuitable" --> G{"Partial platform swap beneficial and compatible?"}
    G -- "Yes" --> R6["Replatform"]
    G -- "No" --> R7["Rehost"]
~~~

This diagram only **initiates option screening**; it does not replace cost, security, and architecture analysis. Every “yes” branch needs evidence; sometimes a workload fits SaaS yet needs deep customization, or one module is retained while another is replatformed.

## 4. Applying 7R to an Application Portfolio

Suppose a retail enterprise wants to exit its data center within 12 months, cut operational toil, and keep its sales systems stable. The table below is a **hypothetical example** illustrating how each workload can receive a distinct decision:

| Workload | Candidate Strategy | Rationale and Accompanying Conditions |
|---|---|---|
| Legacy reporting app with zero active users, replaced by new BI | **Retire** | Verify end users, job schedules, and report retention period before shutdown |
| Factory equipment management software using specialized drivers | **Retain** | Must stay connected to on-site equipment; schedule review once a compatible gateway exists |
| Internal VM cluster on a cloud-supported virtualization platform | **Relocate** | Prioritize rapid full-cluster move; check licensing, bandwidth, latency |
| Legacy ERP on VMs whose licensing and runtime are not ready to change | **Rehost** | Move VMs first; plan version patching and validate compute costs |
| Inventory management API able to move its database to a managed service | **Replatform** | Verify schema, extensions, connection pooling, and failover |
| In-house CRM tool mostly following standard workflows | **Repurchase** | Evaluate SaaS, data import, SSO, permissions, and subscription costs |
| High-load ordering platform with continuous releases and coupled modules | **Refactor** | Incrementally extract capabilities needing independent scale while preserving order consistency |

After selecting an R, the organization must create an **Architecture Decision Record (ADR)** documenting context, options considered, decision, rationale, assumptions, residual risks, and review milestones. “Rehost because it is fast” is incomplete unless it records that the app still runs a self-managed database requiring a follow-on modernization wave.

## 5. Evaluating Trade-Offs with Well-Architected

Well-Architected evaluates a migration option across multiple dimensions rather than speed alone. The six common pillars apply as follows:

| Pillar | Post-Migration Architecture Review Questions |
|---|---|
| **Operational Excellence** | Are deployments automated? Are runbooks, alerts, on-call rotations, and change controls in place? |
| **Security** | Is IAM least-privilege? Are secrets, encryption, keys, network segmentation, and audit logs protected? |
| **Reliability** | Are failed components replaced/recovered? Have backup/restore, failover, and RTO/RPO been tested? |
| **Performance Efficiency** | Do hybrid network latency, compute sizing, IOPS, caching, and connection limits handle target load? |
| **Cost Optimization** | Have real fees, right-sizing, licenses, cross-region/egress traffic, and idle resources been accounted for? |
| **Sustainability** | Are idle resources minimized and utilization aligned with actual demand? |

Objectives can conflict. For example:

- Using **two availability zones** typically improves availability but raises costs and requires appropriate data design.
- Moving a database to a **managed service** lowers infrastructure maintenance burden, yet requires verifying features, backup policies, and service permissions.
- **Autoscaling** helps variable workloads, but apps storing login sessions in local memory or relying on local disks require changes.
- **Splitting into microservices** can enable independent deployments while adding network hops, distributed tracing, failure handling, and data consistency complexity.

Therefore, every 7R option needs **measurable targets**: for instance, p95 latency under a business threshold, max RTO of 60 minutes, max RPO of 5 minutes, monthly run cost within budget, and shorter release times post-refactor. These are **example thresholds**, not universal defaults; final targets must be approved by business stakeholders.

## 6. From R Selection to Target Architecture

### 6.1. Networking and Foundation (Landing Zone)

Before putting production workloads in the cloud, define accounts/projects/subscriptions, environment separation, network topology, DNS, IP addressing, connectivity paths, and access controls. When apps still depend on on-premises systems, account for **latency, bandwidth, availability, and cost** of VPNs or dedicated links.

Do not inspect only app-to-database paths: include callbacks, webhooks, internal DNS, identity sync, SMTP, license servers, monitoring services, and partner systems. Inbound/outbound controls, private endpoints, firewalls/security groups, and secret isolation must be derived from real data flows.

### 6.2. Compute and Deployment Model

- **Relocate/rehost:** define VM sizing, images, disks, hypervisor conversion capability, deployment regions, and OS patching workflows. Test boot, drivers, agents, recovery times, and storage performance.
- **Replatform:** assess how managed runtimes, container orchestration, or PaaS impact health checks, sessions, filesystems, configuration, database connections, service limits, and CI/CD.
- **Refactor:** establish API and event contracts, timeout/retry handling, idempotency, backpressure, data ownership boundaries, and backward compatibility during transition.
- **Repurchase:** design SSO/IAM, integrations, data synchronization, data export, auditability, and vendor exit plans.

Never assume “cloud = serverless” or “modernization = microservices.” Pick compute after locking **load profiles, statefulness, operational model, and team skills**.

### 6.3. Data: The Decisive Cutover Risk Point

For critical data, the plan must answer:

1. Where does the **source of truth** reside before, during, and after transition?
2. Will migration use **backup/restore**, dump/import, replication, CDC, or application-level sync?
3. Can writes be paused temporarily? If not, how are consistency and update ordering preserved?
4. How will data be reconciled: row counts, checksums, transaction totals, business reconciliation?
5. Is there sensitive data, encryption, deletion, or regional residency requirements?
6. If rolling back, how will data created after traffic cutover be handled?

**RPO** is the maximum acceptable data loss to the business (usually measured in time); **RTO** is the maximum time to restore service after an outage. Asynchronous snapshots or replication do not automatically guarantee zero RPO. Test recovery under realistic conditions, measure results, and document the limitations of your chosen mechanism.

For ordering/payment systems, avoid **concurrent writes to two independent databases without explicit coordination**. Returning to an older version must account for schema compatibility, emitted events, in-flight transactions, and newly created post-cutover data.

## 7. Controlled Wave-Based Migration Process

A program can be organized into six phases. Each phase requires clear deliverables and a gate review before advancing:

| Phase | Core Activities | Gate Criteria to Advance |
|---|---|---|
| **1. Discover** | Inventory apps, owners, dependencies, data flows, baseline costs | Dependency map and criticality complete; zero “unknown owner” entries |
| **2. Assess & decide** | Propose 7R, analyze TCO/risks, design target state, write ADRs | Options confirmed by business, security, and operations |
| **3. Prepare** | Build landing zone, IAM, network, logging, backups, CI/CD, runbooks | Minimum connectivity, permissions, security, and recovery tests passed |
| **4. Pilot & migrate** | Run low-load pilot; migrate apps/data in waves | Functional, performance, data reconciliation, and cutover window verified |
| **5. Cutover & stabilize** | Shift traffic, monitor metrics, handle errors, keep rollback ready | Stable operation within SLOs over the agreed observation window |
| **6. Optimize & close** | Right-size, optimize costs, delete old resources, update docs | Handover evidence, DR tests complete, unnecessary costs terminated |

### Sequencing Migration Waves

A **wave** should group tightly coupled applications or systems sharing a change window. You can start with low-impact workloads, provided the pilot still represents real risks: hybrid networking, data sync, IAM, logging, observability, and recovery.

For example, a web service and database separated across a high-latency hybrid link may perform poorly even when each machine passes standalone benchmarks. Migrating servers one by one from a spreadsheet without inspecting the **dependency graph** creates subtle failures. For coupled groups, decide explicitly which components move together, which stay behind, and the conditions for hybrid operation.

### Runbook for a Cutover

An actionable runbook needs **assignees, timestamps, actions, verification steps, stop conditions, and decision authority**. Reference sequence:

1. Lock the maintenance window and contacts; check the latest backup/restore, target environment health, and emergency access.
2. Check replication and data lag; if required, enable read-only mode or pause writes safely.
3. Complete sync, execute consistency checks, and run synthetic business transactions.
4. Shift traffic via DNS/load balancer/routing; verify TTLs, sessions, and long-lived connections.
5. Monitor error rates, p95/p99 latency, replication lag, queue backlogs, payment flows, and business KPIs.
6. Decide **proceed** or **rollback** against pre-approved thresholds; reconcile transactions created during transition before restoring the old path.
7. During stabilization, maintain heightened monitoring before retiring legacy resources once the retention window expires.

**Rollback is not just flipping DNS back.** For write-heavy apps, rollback involves schema compatibility, newly created data, and external side effects. If safe reversal is impossible, define a **roll-forward** plan and state the risks explicitly before cutover.

## 8. End-to-End Scenario: Modernizing an Ordering Platform

### Context and Requirements

Suppose an ordering system runs a Java monolith across two VMs, using self-managed PostgreSQL, connecting to a payment gateway, and sending emails synchronously. Every promotion triggers traffic spikes; releasing new versions usually requires maintenance windows. The numbers below are **exercise assumptions only**:

- Scaling target: handle peak load at 4x normal traffic.
- Operational target: deploy with minimal downtime.
- Recovery target: RTO ≤ 60 minutes, RPO ≤ 5 minutes, **requiring explicit confirmation** of acceptable data loss with ordering/payment stakeholders.
- Constraint: the company has six months to exit the data center without capacity for a full rewrite.

### Comparing Three Viable Options

**Option A — Full Rehost:** move the monolith and PostgreSQL to cloud VMs. Fast exit from the data center; the team still manages the database, backups, patching, and HA. If the app stores session state in VM memory, adding instances can break logins or shopping carts.

**Option B — Selective Replatform:** run the application on compute with proper health checks/autoscaling; move PostgreSQL to a compatible managed service. Must test extensions, encoding, collation, version, transactions, connection pooling, replication, and query performance. The goal is lowering operational risk first without splitting business modules.

**Option C — Sliced Refactor:** keep the existing ordering core, extract email/notification handling into an asynchronous consumer; later extract catalog or search only when load and ownership justify it. Order-related events need a **transactional outbox** (or equivalent), **idempotent** consumers, retries, and a dead-letter queue to prevent lost/duplicate side effects. Do not immediately split ordering/payment transactions across multiple databases without solving business consistency.

A staged roadmap could be **replatform in phase one, refactor bottlenecks in phase two**. If the data center deadline is tighter than replatform readiness, rehost first as an interim step, recording parallel-run costs and a technical-debt retirement plan. Choices depend on measured evidence, not technology trends.

### Phased Target Architecture Sketch

~~~mermaid
flowchart LR
    U["User"] --> E["DNS / WAF / Load balancer"]
    E --> A["Ordering app<br/>multiple instances"]
    A --> D[("Managed PostgreSQL<br/>backup + HA")]
    A --> O["Outbox / event publisher"]
    O --> Q["Event queue"]
    Q --> N["Notification worker"]
    A --> P["External payment gateway"]
    A -.-> M["Logging / metrics / tracing"]
    N -.-> M
~~~

This diagram is a **reference design**; not every service is automatically needed in phase one. Add IAM controls, private networking, encryption, secrets, fault isolation, backups, restore testing, and rate limiting based on real requirements. The system only qualifies as meeting RTO/RPO after rehearsal and measurement.

### Acceptance Evidence for the Example

- **Business:** creating/updating/canceling orders, payments, refunds, emails, batch jobs, inventory sync, and reconciliation run accurately.
- **Data:** order counts and statuses match reconciliation; zero orphaned transactions; duplicate events handled safely.
- **Reliability:** test failure of an instance/infrastructure zone; prove restore and failover meet requirements.
- **Performance:** test normal and peak loads, tracking p95 latency, CPU, database connections, and queue lag.
- **Security:** proper authentication/authorization, zero secrets inside images, restricted database access, compliant audit logs.
- **Operations/cost:** dashboards and alerts have owners; pilot billing and TCO projections stay within approved budgets.

## 9. Weighted Scoring: Decision Aid, Not an Architecture Substitute

When multiple options are viable, use a weighted matrix for transparent discussion. For example, scoring the ordering platform above from **1–5 (5 is best)** under team assumptions:

| Criterion | Weight | Rehost | Replatform | Immediate Refactor |
|---|---:|---:|---:|---:|
| Low implementation risk | 25% | 4 | 4 | 2 |
| Speed to complete | 20% | 5 | 4 | 2 |
| Favorable 3-year TCO | 20% | 3 | 4 | 3 |
| Operational ease | 15% | 2 | 4 | 5 |
| Development/scaling agility | 20% | 2 | 4 | 5 |
| **Weighted total score** | **100%** | **3.30/5** | **4.00/5** | **3.25/5** |

Calculation: **total score = sum (weight × criterion score)**, with weights expressed from 0–1. For example, Replatform: 0.25 × 4 + 0.20 × 4 + 0.20 × 4 + 0.15 × 4 + 0.20 × 4 = **4.00**.

This table only illustrates the method; scores must be agreed upon by business, engineering, security, and finance teams using data. **Mandatory constraints** such as residency, legal obligations, compatibility, or RTO/RPO are **disqualifying gates**: a violating option cannot be “rescued” by a high total score.

### Do Not Confuse Infrastructure Price with Total Cost of Ownership

A minimal 3-year TCO model can be calculated as:

~~~text
3_Year_TCO =
  one_time_migration_cost
  + compute_storage_network_cost_36_months
  + licensing_and_SaaS_cost_36_months
  + operations_staff_cost_36_months
  + dual_run_and_remaining_on_premises_cost
  + backup_DR_monitoring_security_cost
  + vendor_exit_cost_if_applicable
~~~

Avoid overlooking network egress, cross-region data access, support contracts, OS/database licenses, engineering labor, and legacy decommissioning costs. For **Retire**, include compliance data archiving; for **Repurchase**, factor per-user/transaction fees and data exportability; for **Refactor**, account for building and operating two architectures during transition.

## 10. Common Mistakes and Prevention

| Signal | Why It Is Dangerous | Control |
|---|---|---|
| “Rehost everything to move fast” | Preserves design flaws and suboptimal VM costs | Set optimization milestones, right-sizing, and follow-up ADRs |
| “Microservices automatically equals modern” | Increases data, network, release, and observability complexity | Split only where clear independence is needed and ops readiness exists |
| Moving servers only, forgetting integrations | Breaks DNS, batches, identity, links, and callbacks | Dependency mapping and end-to-end flow testing |
| Labeling retire because “nobody seems to use it” | Hidden jobs, retention obligations, or audits may remain | Confirm owner, access logs, backups, retention, dependencies |
| Repurchase while ignoring workflows | SaaS mismatches data fields, roles, and workflows | Gap analysis, sample data, integration trials, training plan |
| Cutover without rollback testing | New data makes returning unsafe | Rehearsals, sync and reconciliation, defining point of no return |
| Comparing only VM price vs. physical server | Omits migration, licensing, network, and dual-run costs | Compare TCO and operational impact across the same horizon |
| Retain without a re-evaluation date | Legacy systems keep accumulating risk and cost | Assign owner, review triggers, and checkpoint dates |

## 11. Applied Exercise

You are the cloud architect for an enterprise with four workloads:

**(A)** A legacy time-tracking system with zero logins since migrating to a new platform, though HR records must be retained per policy. **(B)** A manufacturing system tied to specialized serial hardware that the vendor does not yet support outside the factory. **(C)** A quoting API with actively maintained code whose self-managed database consumes heavy toil and needs lower failover risk. **(D)** An in-house customer support tool handling standard workflows where the team is considering SaaS.

Perform the following:

1. Select **one primary R** for each workload and name at least two pieces of evidence to verify before finalizing.
2. For (C), propose an initial target architecture: network, compute, database, backup/DR, logging, and access control; specify what belongs to the cloud provider versus the application team.
3. For (A) and (D), design data retention/export, reconciliation, and legacy shutdown criteria.
4. Choose one workload to draft a **cutover runbook**, including go/no-go criteria, verification steps, and a rollback scenario.
5. State at least one **Well-Architected trade-off** among reliability, cost, performance, security, or operations.

**Self-Check Hints:** (A) leans toward **Retire**, provided records are retained per policy; (B) conditional **Retain** with a scheduled review date; (C) typically **Replatform** if database/runtime are compatible; (D) could be **Repurchase** if SaaS satisfies data, integration, security, cost, and user workflows. New evidence may change the choice.

## 12. Pre-Approval Checklist for a 7R Plan

- [ ] Workload has verified owner, business requirements, criticality, and dependencies.
- [ ] Chosen R includes **rationale, alternatives, and disqualifying conditions**; not based on slogans.
- [ ] Target architecture specifies network, compute, data, IAM, monitoring, backups, HA/DR, and operational responsibilities.
- [ ] RTO/RPO, SLOs, performance, security, and compliance have measurable acceptance criteria.
- [ ] Data is reconciled; cutover and rollback/roll-forward have been rehearsed.
- [ ] TCO includes migration, dual-run, licensing, network, and long-term operations.
- [ ] Migration waves, runbook, go/no-go authority, and handover plan are defined.
- [ ] For **Retain**, a review date exists; for **Retire**, dependency removal and data preservation are evidenced; for the remaining Rs, post-migration optimization steps exist.

**Core principle:** 7R is a decision **grounded in each workload's value and risk**. A cloud architecture succeeds when it satisfies business requirements and proves operations, security, recovery, scalability, and cost against agreed targets.
