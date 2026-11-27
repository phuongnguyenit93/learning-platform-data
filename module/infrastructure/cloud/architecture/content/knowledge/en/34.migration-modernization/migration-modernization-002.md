# Readiness Assessment, Risk Analysis, and Migration Strategies

## 1. Learning Objectives and Context

Migrating applications to the cloud is an architectural and operational decision, not simply moving servers to another infrastructure. In **CLOUD_ARCHITECTURE**, the designer must work from business requirements to networking, compute, data, and deployment models, then balance **reliability, security, scalability, cost, and operability** under Well-Architected principles.

After this lesson, you will be able to:

- Inventory applications, data, infrastructure, and dependencies to know exactly what will be migrated.
- Assess each workload's readiness using verifiable criteria, separating composite scores from mandatory gates.
- Identify and prioritize technical, business, security, data, legal, and operational risks.
- Select a migration strategy aligned with business goals, team capabilities, and system constraints.
- Propose migration waves, cutover plans, rollback strategies, and post-migration acceptance metrics.

The **intended output** of an assessment is a decision dossier containing: a current-state diagram, target-state requirements, dependency inventory, readiness score, risk register, recommended strategy per workload, test plan, and go/no-go criteria.

## 2. Before Deciding: Define Drivers and Scope

You cannot choose the right strategy without answering why the organization needs to migrate. Common drivers include expiring data center contracts, seasonal load growth, shorter release cycles, improved disaster recovery, or reduced infrastructure maintenance effort. Different drivers can lead to different target architectures.

For each application, document:

| Question Group | Details to Clarify | Example Output |
| --- | --- | --- |
| Business | Which process does the system serve? Acceptable downtime? | 24/7 order placement; maximum 30 minutes planned downtime |
| Quality of service | Current load, growth, latency, and required availability? | P95 under 300 ms at target load |
| Data | Which data is sensitive? Size, growth rate, retention requirements? | 500 GB transactional DB; retain backups per policy |
| Continuity | RTO and RPO of each system? | 2-hour RTO; 15-minute RPO |
| Compliance | Contractual, data residency, audit, and third-party constraints? | Obligation list requiring legal confirmation |
| Organization | Who decides, who operates, who responds to incidents? | Business owner, application owner, platform, security, DBA |
| Economics | Current costs, migration budget, timeline, and benefit metrics? | Projected 3-year total cost of ownership |

Two metrics must be understood accurately:

- **RTO (Recovery Time Objective)**: the target time to restore service after an incident. RTO is not synonymous with the allowed downtime window during a planned cutover.
- **RPO (Recovery Point Objective)**: the maximum acceptable data loss upon recovery, measured from the restored data point to the time of the incident. A 15-minute RPO requires real mechanisms and tests to prove.

Target architecture goals must be measurable. “Move to the cloud to be faster” is insufficient for making decisions; “meet P95 under 300 ms at 2,000 concurrent users” enables design and testing.

## 3. Current-State Discovery: Building Workload and Dependency Maps

### 3.1. Minimum Inventory

Assemble through interviews, discovery tools, existing monitoring, and verification against live configurations. Do not trust a CMDB blindly if it has not been updated recently.

| Asset | Information to Collect | Why It Matters |
| --- | --- | --- |
| Applications and services | Runtime version, OS, owner, peak hours, SLA | Determine compatibility and criticality |
| Compute | vCPU, RAM, P50/P95 utilization, disk, deployment automation | Select initial sizing and scaling bounds |
| Network | Inbound/outbound flows, DNS, firewalls, VPN, private links, bandwidth, latency | Avoid missing connections and bottlenecks |
| Data | DB engine, size, growth, transactions, locks, backups, encryption | Plan synchronization and consistency checks |
| Integrations | APIs, queues, batch schedules, SFTP, SMTP, IdP, vendors | Determine migration ordering |
| Operations | Logging, metrics, tracing, alerts, CI/CD, IaC, runbooks, on-call | Ensure the team can operate it |
| Legal and security | Data classification, access permissions, secrets, certificates, audit requirements | Design appropriate controls |

For hard-to-observe data, record confidence explicitly: **measured**, **owner-confirmed**, or **unverified**. Unverified assumptions must become verification items before finalizing decisions.

### 3.2. Dependency Maps Instead of Server Lists

An application rarely operates in isolation. For example:

~~~mermaid
flowchart LR
    U[Customer] --> DNS[DNS / CDN]
    DNS --> W[Web and API]
    W --> DB[(Transaction DB)]
    W --> Q[Queue]
    Q --> B[Order Processing Worker]
    B --> X[Shipping Partner]
    W --> ID[Identity / SSO]
    B --> R[(Reporting System)]
~~~

If web/API moves to the cloud while the worker, database, or identity system remains in the legacy data center, every cross-network call adds latency and connectivity risk. Measure **communication flows** (who calls whom, protocol, frequency, volume, latency), not merely where servers reside.

Use this map to identify **migration groups**: components that must move in the same wave or require temporarily compatible communication contracts. For cyclic dependencies, you can maintain stable interfaces during a transition phase and decouple later.

### 3.3. Classifying Criticality and Complexity

A pragmatic approach is to classify along two axes:

- **Business impact on failure**: low, medium, high, mission-critical.
- **Migration complexity**: low, medium, high based on dependency count, data state, downtime limits, compliance requirements, software compatibility, and automation level.

Low-impact applications with few dependencies are often good pilots to validate deployment methods, telemetry, and team training. Mission-critical transactional applications require stronger test evidence, even when the target infrastructure looks simple.

## 4. Evidence-Based Readiness Assessment

“Readiness” means the ability to **migrate and operate safely in the target architecture**. Do not ask only whether the application can boot on a cloud VM.

### 4.1. Sample Scoring Framework

Score each dimension from **0 to 4**:

- **0 – Unknown**: no owner or reliable evidence yet.
- **1 – Not ready**: critical gaps exist that require remediation.
- **2 – Conditional**: remediation path is known but not fully verified.
- **3 – Controlled readiness**: key requirements met with test results.
- **4 – Proven**: satisfied with documentation, automation, and repeatable tests.

| Assessment Dimension | Illustrative Weight | Expected Evidence |
| --- | ---: | --- |
| Network and connectivity | 20% | Routing, DNS, firewalls, bandwidth, and latency tested |
| Application compatibility | 20% | Runtime PoC, libraries, licenses, dependencies |
| Data and recovery | 20% | Successful backup/restore, data checks, RPO/RTO tests |
| Operations | 15% | Monitoring, alerts, on-call access, runbooks, CI/CD |
| Security and compliance | 15% | Identity, authorization, encryption, audits, and mandatory controls |
| Economics and capability | 10% | TCO estimate, budget, assignees, and technical skills |

Formula with weights summing to 100%:

**Readiness (%) = Σ [dimension score / 4 × dimension weight]**

For example, with scores **3, 2, 2, 1, 3, 2**:

**Readiness = 3/4 × 20% + 2/4 × 20% + 2/4 × 20% + 1/4 × 15% + 3/4 × 15% + 2/4 × 10% = 55%**.

55% indicates gaps to address; it is **not** a probability of migration success. Assessment thresholds are internal conventions and must be calibrated to each system's criticality and evidence. For instance, a team might treat below 60% as “needs further preparation,” 60–79% as “controlled pilot only,” and 80%+ as “eligible for go-live review,” without letting score thresholds replace formal approval.

### 4.2. Mandatory Gates (Hard Gates)

A workload may still be **blocked from migrating**, even with a high composite score, if conditions like these remain:

1. Usage rights and data storage locations under applicable contracts/regulations are unconfirmed.
2. Consistent backups and restore test results are absent.
3. Least-privilege access, secret management, or mandatory access logging cannot be demonstrated.
4. An application owner, incident response team, or cutover communication plan is missing.
5. Downtime targets or RTO/RPO cannot be met and no mitigation is accepted.
6. Essential network paths/dependencies that could disrupt transactions are not understood.

Decision rule: **composite scores help prioritize improvements; hard gates decide whether deployment eligibility is met**.

### 4.3. Grounding Assessments in Well-Architected

To look beyond “the server boots,” evaluate the design against common pillars: operational excellence, security, reliability, performance efficiency, cost optimization, and sustainability. Not every cloud provider uses the same pillar names or count; apply the specific framework of your chosen platform.

Guiding questions: Can incidents be automatically recovered and observed? Can permissions be audited? Does failing an availability zone lose data or exceed RTO? Does load growth spike costs unpredictably? Does the team measure wasted power/resources and eliminate excess capacity?

## 5. Building an Evidence-Driven Risk Register

Risks should be written in the form **cause → event → impact**, with an owner, mitigation action, and trigger indicator. “Network has issues” is not actionable; “WAN link saturates during DB sync, causing higher transaction latency and delayed cutover” is a testable risk.

For initial prioritization, score **likelihood L** from 1 (rare) to 5 (very likely) and **impact I** from 1 (minor) to 5 (severe), then compute **L × I**. Scores from 1–25 only order remediation work and do not represent true probability measurements. For safety or compliance risks, still enforce independent hard gates.

| Risk | L × I | Mitigation Action | Trigger / Evidence | Owner |
| --- | ---: | --- | --- | --- |
| Insufficient bandwidth during data transfer | 4 × 4 = 16 | Measure throughput, test sync, throttle load, consider offline transfer | Sample copy time, app latency | Network lead |
| Incompatible DB version | 3 × 5 = 15 | Check extensions, collation, SQL, replication, and run PoC | Functional and performance test results | DBA |
| IAM/permission misconfiguration | 3 × 5 = 15 | IaC, least-privilege review, policy scanning, audit | Access verification results | Security lead |
| Partner dependency on fixed IP | 3 × 4 = 12 | Inventory allowlists, provision IP/NAT, confirm with partner | End-to-end connectivity test | Integration owner |
| Cost spike during parallel run | 4 × 3 = 12 | Set budgets, cost tags, caps, and retirement date for old environment | Daily cost reports | FinOps owner |
| Data changes after snapshot | 3 × 5 = 15 | Replication/CDC, monitor lag, freeze writes at cutover | Data drift, record reconciliation | Data owner |

After mitigation, re-evaluate **residual risk** and designate who is authorized to accept it. The risk register must be updated as designs or assumptions evolve, not completed once at kickoff.

## 6. Choosing a Migration Strategy: The 7R Framework

The Rs are an **options framework**, not a mandatory sequence. Each application, database, or component can follow its own strategy.

| Strategy | When Appropriate | Benefits | Trade-offs or Risks |
| --- | --- | --- | --- |
| **Retire** – decommission | Low usage, no remaining value, replaced elsewhere | Reduces technical debt and cost | Must verify data retention rights and lingering dependencies |
| **Retain** – keep as-is | Bound by legal/licensing rules, specialized latency, no benefit to move | Avoids premature changes before conditions are met | Still must manage operations, security, hybrid connectivity |
| **Rehost** – lift and shift | Need fast move, app is VM-compatible | Minimal code change, straightforward initial scoping | May retain scaling limits and higher costs |
| **Replatform** – lift, tinker, and shift | Can swap DB, runtime, containers, or managed services with little business logic change | Reduces operational toil, leverages cloud services | Requires compatibility, config, and performance testing |
| **Repurchase** – replace with product/SaaS | Commodity capability, SaaS meets requirements | Transfers much operational responsibility to vendor | Data migration, lock-in, process changes, integrations |
| **Refactor / Rearchitect** – redesign | Need elasticity, self-healing, new release model, or massive scale | Long-term architectural optimization | Build cost, timeline, and major change risk |
| **Relocate** – move hypervisor or compatible stack | Mechanism exists to move clusters/VMs across compatible platforms | Minimizes application-layer changes | Depends on service capabilities, licenses, and infrastructure compatibility |

“6R/7R” terminology can vary across documentation. In reports, define what each R means to prevent identical terms from carrying different scopes.

### 6.1. Strategy Selection Flow

~~~mermaid
flowchart TD
    A[Start with workload and requirements] --> B{Still has business value?}
    B -- No --> C[Retire and handle data retention]
    B -- Yes --> D{Must stay on-premises?}
    D -- Yes --> E[Retain and design hybrid connectivity]
    D -- No --> F{Does SaaS meet features, data, and compliance?}
    F -- Yes --> G[Evaluate Repurchase]
    F -- No --> H{Need architecture change to meet NFRs?}
    H -- Yes --> I[Refactor / Rearchitect]
    H -- No --> J{Clear benefit from changing platform services?}
    J -- Yes --> K[Replatform]
    J -- No --> L{Compatible full-stack relocation mechanism?}
    L -- Yes --> M[Relocate or Rehost, compare TCO]
    L -- No --> N[Rehost if compatible, or re-evaluate]
~~~

The diagram aids screening; the final choice requires testing, cost evaluation, data ownership confirmation, and risk review. **Retain** does not mean skipping modernization: you can still implement protection, backups, and observability for systems kept on-premises.

### 6.2. Characteristic Trade-offs

**Reliability:** moving VMs to a cloud region does not automatically create HA/DR. You must address failure domains, replica counts, availability zones, backups, and recovery tests.

**Security:** the cloud provides tools such as IAM, KMS, firewalls, and logs, but the team must still design, configure, and operate its portion under the shared responsibility model.

**Scalability:** rehosting can scale up machine sizes, yet bottlenecks in a single database, locks, or session state persist. Replatforming or refactoring may be needed for horizontal scaling.

**Cost:** cloud costs include compute, storage, backups, egress/inter-zone data transfer, managed services, monitoring, and support. During transition, old and new systems often run in parallel. Compare **3-year TCO** including migration costs and risks of missing targets, rather than comparing monthly VM rates alone.

**Operations:** managed services reduce certain maintenance tasks but demand new capabilities: IaC, monitoring, access governance, backup/restore, quota control, and cost management.

## 7. Designing the Target State and Minimum Foundation

A migration plan can fail even when applications are compatible if the **landing zone** is unprepared. Minimum capabilities typically include:

1. **Account/project/subscription structure:** environment isolation, naming and cost-tagging standards, ownership permissions, quotas.
2. **Identity and access:** identity provider integration, MFA for admins, least privilege, service accounts, key and secret rotation lifecycles.
3. **Networking:** network segmentation, subnets, routing, inbound/outbound controls, DNS, hybrid VPN/interconnects, non-overlapping IP plans.
4. **Data protection:** classification, encryption at rest and in transit, key management, snapshots/backups, retention, and restore testing.
5. **Observability and response:** centralized logs, metrics, tracing, SLO-based alerts, log retention, incident on-call workflows.
6. **Deployment:** CI/CD, infrastructure as code (IaC), change reviews, configuration checks, version rollback mechanisms.
7. **Cost governance:** budgets, threshold alerts, tagging, and reporting by application, environment, and owning team.

Resources should be designed around **failure domains** and real requirements: at minimum, determine how losing an instance, a zone, or hybrid connectivity affects the service. Avoid assuming multi-region is always required; weigh cost, complexity, and RTO/RPO.

## 8. Dedicated Assessment of Data Migration

Data migration often dictates the downtime window and rollback feasibility of stateful systems.

| Approach | Typical Mechanism | When Suitable | Conditions to Verify |
| --- | --- | --- | --- |
| Offline / backup-restore | Stop writes, take backup, transfer, and restore | Moderate data size, downtime acceptable | Copy duration, restore time, integrity |
| Online / replication | Continuous sync, drain lag, switch write role at cutover | Short downtime, source and target compatible | Transaction ordering, replication lag, failover |
| CDC and phased migration | Stream changes via data logs | Large systems needing parallel run and checks | Idempotency, schema evolution, duplicate/lost events |
| Format conversion / ETL | Extract, cleanse, transform, and load | Data model changes or SaaS replacement | Mapping, reconciliation, quality, and business rules |

**Rough transfer-time estimate**: minimum time ≈ data volume / effective throughput. For 500 GB over a link achieving an effective 100 MB/s, the raw ideal transfer alone takes about 5,000 seconds (roughly 83 minutes), **excluding** backup, encryption, compression, verification, retries, and restore. Test with a sufficiently large sample to measure actual throughput and end-to-end processing time.

Verify data at multiple levels: row counts, batch checksums or hashes, foreign keys, daily transaction totals/amounts, replication lag, and business query results. Merely confirming “the DB opens” is not sufficient proof.

If both source and target accept writes, you must design conflict resolution, event ordering, and deduplication. **Dual-write** can introduce drift; do not use it by default to avoid downtime. With a single write authority, define the **write-cutover point** and steps ensuring clients cannot mistakenly keep writing to the old source.

## 9. Wave Planning, Testing, and Cutover

### 9.1. Sequencing Migration Waves

A plan can be structured as follows:

| Phase | Scope | Evidence Required Before Advancing |
| --- | --- | --- |
| Foundation | Landing zone, connectivity, security, observability | Policy checks, network flows, backups, and alerts verified |
| Pilot | Low-criticality, low-dependency services | Automated deployment, access, incident handling, costs |
| Wave 1 | Low-data / low-dependency application groups | Integration testing, performance, recovery, and rollback |
| Wave 2 | Mission-critical apps and transactional data | Cutover rehearsal, reconciliation, on-call readiness, approvals |
| Optimization | Rightsizing, autoscaling, architecture refinements | SLOs, actual costs, stability, and handover |

A wave must account for dependency coupling, not standalone difficulty alone. A low-criticality system tightly coupled to the transactional core may be a poor pilot candidate.

### 9.2. Sample Cutover Runbook

**Before cutover**

- Lock the change window, accountable leads, communication channels, allowed disruption, and go/no-go authority.
- Verify backups and restore capability; check health of source/target systems, replication lag, quotas, and partner links.
- Rehearse cutover on an equivalent environment; time each step and refine the plan.
- Lock observability metrics: errors, p95/p99 latency, queue lag, CPU/memory, connection pools, order counts, and data drift.
- Prepare load-shedding procedures, batch/write pauses if needed, and user communication plans.

**During cutover**

1. Announce start; record timestamp and configuration versions.
2. Pause or coordinate writes on the source per design; wait for replication lag to reach acceptable bounds.
3. Run final data checks and switch the write authority; update endpoints, DNS, or routing.
4. Execute smoke tests over real access paths: login, ordering, simulated payment, queues, partner APIs.
5. Monitor SLOs and business reconciliation during the defined observation window.
6. Authorized owners decide to proceed, fix forward, or roll back based on pre-published criteria.

**After cutover**

- Heightened monitoring, metric reconciliation, and updating runbooks, inventories, diagrams, and support docs.
- Retire legacy infrastructure only after the retention reserve expires and archival, audit, and compliance obligations are complete.
- Log variances between plan and execution to calibrate estimates for the next wave.

### 9.3. Rollback Must Account for New Data

Once writes have been accepted at the target, routing traffic back to the old source does **not** automatically preserve data consistency. You must predefine one verifiable mechanism: controlled reverse sync, restoring from a consistent snapshot, compensating business operations, or **forward fix**. Where no safe data rollback exists, establish a **point of no return** and require appropriate sign-off before crossing it.

Go/no-go criteria must be objective, such as: restore rehearsal completed within RTO; transaction errors within approved thresholds; reconciled data matches; all hard gates passed; on-call and business representatives present. Do not approve merely because “servers are green.”

## 10. End-to-End Example: Order Management System

Suppose an enterprise runs an order system with web/API on VMs, a 500 GB relational DB, a worker sending requests to a shipping partner, and nightly batch reports. The enterprise wants to reduce server administration overhead and increase peak-season capacity. This is a **hypothetical scenario** to illustrate decisions, not a universal default configuration.

Agreed requirements:

- Order service RTO: **2 hours**; RPO: **15 minutes**.
- Order creation P95 at target load: **under 300 ms**.
- Sensitive data access logging, least-privilege access, and data encryption required.
- Must test integration with a partner enforcing an IP allowlist.

### 10.1. Discovery Findings

| Component | Finding | Preliminary Strategy |
| --- | --- | --- |
| Web/API | Compatible with target runtime; sessions stored in single-node memory | Replatform after moving sessions to a shared store or making stateless |
| Database | Uses an extension with unconfirmed managed DB support | Run compatibility PoC before picking managed DB; temporarily Rehost if unready |
| Integration worker | Partner accepts traffic only from registered IPs | Provision stable egress IP, confirm allowlist, run end-to-end test |
| Nightly reporting | Runs once daily, no low-latency requirement | Move after core services once data dependencies are clear |
| Operations | Lacks tracing and SLO-based alerts | Add observability and run incident drills before pilot |

Suppose the scoring framework from section 4 yields **55%**. The system lacks sufficient evidence for go-live because **restore has not been rehearsed** and the DB extension is unverified. Simply booting the web tier on a cloud VM is only a small part of the evaluation.

### 10.2. Recommended Decisions and Sequence

1. Build the landing zone, IAM, logging, partner connectivity, and test environment with IaC.
2. Run a PoC for managed DB extensions/SQL; benchmark performance and test restore. If it fails, consider a controlled Rehost of the DB in the initial wave.
3. Move web/API to an autoscaling-capable platform after resolving session state, health checks, and idempotent request handling.
4. Validate data sync with a full-scale rehearsal, measure replication lag, and reconcile total orders/revenue.
5. Migrate low-latency coupled components together; keep integrations temporarily over the tested hybrid link.
6. Cut over per runbook and track business metrics, not only infrastructure metrics.
7. After stabilization, evaluate database optimization, reporting rearchitecture, and legacy decommissioning.

The example illustrates a conditional conclusion: **replatform the application first, choose the DB option after a PoC**, rather than forcing every component onto managed services in one shot. This lowers compatibility risk while still progressing toward operational goals.

## 11. Architecture Decision Records and Handover

For each workload, the decision document (ADR or equivalent template) should thoroughly cover:

| Section | Required Answers |
| --- | --- |
| Problem and goals | Business drivers, NFRs, scope, constraints |
| Current state | Architecture, data, dependencies, owners, unknowns |
| Options considered | Retain, Rehost, Replatform, Repurchase, Refactor… with evidence |
| Selected option | Target architecture and rationale for accepted trade-offs |
| Readiness | Dimension scores, hard gates, backlog, and re-check date |
| Risks | L/I, mitigation, residual risk, owner, acceptance decision |
| Plan | Wave, rehearsal, cutover, rollback/forward fix, go/no-go criteria |
| Measurement | SLOs, tested RPO/RTO, actual costs, business impact |
| Handover | Runbooks, monitoring, on-call schedule, approvers, post-migration docs |

When evaluating success, look **beyond the moment of cutover**: does the system stay stable during failures, scale properly, recover within targets, satisfy security controls, and stay within budget?

## 12. Common Mistakes and Prevention

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Starting with VMs while ignoring business needs | Platform fails downtime/SLO requirements | Lock measurable targets before discovery |
| Relying on server lists, forgetting dependency flows | Broken APIs, jobs, identity, or partner links | Draw and test the dependency map |
| Assuming cloud automatically provides HA and security | Single points of failure and overly broad permissions | Design failure domains, IAM, backups, and audits |
| Treating readiness scores as a go-live pass | Misses legal, data, or security hard gates | Separate hard gates from scoring |
| Testing only functional happy paths | Failures under high load, backups, or failover | Test load, recovery, security, and failure scenarios |
| Omitting data transfer and parallel-run costs | Budget overrun | Model TCO including transition overlap |
| Having only an application rollback plan | Data written on target cannot safely return to source | Define data strategy and point of no return |
| Shutting down legacy systems right after cutover | Loss of reconciliation capability or retention violations | Enforce approved decommissioning criteria |

## 13. Applied Practice Exercise

You are given three workloads:

- **A – Internal portal:** few dependencies, static data, can tolerate 4 hours of downtime.
- **B – Payment processor:** many integrations, continuous transactional data, near-zero RPO required by business.
- **C – Legacy reporting:** few users, data may need policy-based retention.

Create a table listing **business owner, dependencies, hard gates, readiness score, chosen 7R, rationale, residual risks, and wave** for each workload. Outline a test plan and go/no-go criteria for workload B.

**Reference Solution Approach:** A is a Rehost/Replatform pilot candidate after verifying access controls and backups. B should wait for dependency discovery, replication testing, reconciliation, and target RPO verification before deciding between Replatform and Refactor; you cannot infer the strategy from the label “payment” alone. C is a Retire candidate once confirmed unneeded, data retention is addressed, and remaining dependencies are removed. No single answer is universally right until all conditions are verified.

## 14. Decision-Making Takeaways

A credible migration proposal must answer **why we are migrating; which components depend on one another; what evidence proves readiness; which risks are controlled; why this strategy was chosen; how we verify before and after cutover; and who will operate the new system**.

Treat each workload as a conditional, verifiable decision. Safe migration happens when goals, architecture, data, people, and operational plans are all ready—not merely when target infrastructure has been provisioned.
