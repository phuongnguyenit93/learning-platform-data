# Planning Migration Waves by Dependencies and Business Value

Migrating a system to the cloud is rarely as simple as moving servers one by one down a fixed spreadsheet. An application may call an identity service, share a database with another app, pull data from an on-premises ERP, and power a business process that cannot tolerate outages. Consequently, **migration sequencing must reflect both technical dependencies and business value and risk**.

This lesson shows how to turn an application portfolio into **migration waves** with clear scope, entry criteria, transition plans, acceptance criteria, and incident response plans. This is a cloud architecture design problem: deciding not only which app moves first, but also which data must move together, which hybrid links must remain active, which platform capabilities must be ready, and when legacy systems can be retired.

## 1. What Is a Migration Wave and Why Plan in Waves?

A **migration wave** is a group of workloads organized to be prepared, migrated, tested, and stabilized within a planned phase. Each wave has a business goal, target scope, owners, capacity allocation, cutover window, and completion criteria.

Distinguish three concepts:

| Concept | Meaning | Example |
|---|---|---|
| **Workload** | An application or technical capability with specific resources, data, and operations | Order processing service, order database |
| **Migration group / cutover unit** | Components that must move together or follow a tightly coordinated protocol to preserve consistency | Order service, data schema, and order-writing jobs |
| **Migration wave** | A governance phase that may contain one or more migration groups and separate cutovers | Wave 3 containing the ordering system and mandatory integrations |

Planning in waves helps:

- Limit **blast radius**: an issue in one wave does not automatically spread across the entire estate.
- Build a learning cadence: pilot first, standardize processes, then scale up in later waves.
- Coordinate scarce resources such as data engineers, networking, security, operations, and user acceptance testers.
- Deliver value early: select feasible workloads that yield clear benefits without waiting for the whole portfolio.
- Maintain business continuity while components operate across two environments.

There is no universal rule that “low-criticality apps always go first” or “highest-ROI apps always go first.” A low-criticality app tied to an inseparable database may make a poor pilot. A high-value app lacking a recovery plan is equally unqualified for an early wave.

## 2. Start with Business Objectives and Design Boundaries

Before scheduling, architects and product owners must align on **why we are migrating**. Common objectives include:

- Reducing risk from aging data centers or end-of-life hardware.
- Increasing peak-season scalability and reducing feature deployment lead time.
- Improving availability, disaster recovery, and observability.
- Meeting contract deadlines, regulations, data retention mandates, or customer SLAs.
- Reducing total cost of ownership (TCO) over a defined time horizon.

Each objective must include **measurable metrics and constraints**. For example:

| Objective | Measurable Metrics | Constraints to Plan Around |
|---|---|---|
| Sustain sales | Transaction success rate, lost/duplicate orders, downtime duration | Avoid peak hours and revenue close windows |
| Increase reliability | Service SLOs, RTO, RPO, recovery test results | Verified backups and recovery rehearsals before cutover |
| Improve performance | p95/p99 latency, throughput at target load | Measure cross-boundary latency between on-premises and cloud |
| Control costs | Dual-run costs, cross-region networking, licensing, operations | Budget for parallel-run period and optimization plan |
| Compliance | Data locality, access controls, audit logs | Security controls approved prior to moving data |

These metrics must take a **baseline** from the current system and target thresholds from business requirements. Never treat a sample threshold as a universal SLO for every project.

### 2.1. Defining Migration Scope

For each workload, determine the right strategy: keep in place (**retain**), decommission (**retire**), swap for another product (**repurchase**), lift-and-shift infrastructure (**rehost**), adjust platform (**replatform**), or redesign architecture (**refactor/re-architect**). Organizations may use “6R” or “7R” variants; labels matter less than **explicit decisions per system**.

If an application is retained on-premises, it may still be an **active dependency** of workloads moved to the cloud. Therefore, “not migrating” does not mean “no need to design connectivity, security, operations, and testing.”

## 3. Discovering and Classifying Dependencies

Building an asset inventory is necessary but insufficient. You must model relationships that fail when cut off from the legacy environment.

### 3.1. Dependency Types to Capture

| Dependency Type | Discovery Questions | Impact on Wave Grouping |
|---|---|---|
| **Synchronous calls** | Does service A call B over HTTP/gRPC/TCP, and with what latency and timeouts? | May need co-location or hybrid links meeting SLOs |
| **Data** | Who reads, who writes, are tables/schemas or distributed transactions shared? | May force grouping into one cutover unit; data often dictates wave boundaries |
| **Events/batch** | Are there queues, CDC, ETL files, schedules, and event-ordering requirements? | Must migrate producers/consumers per contract, prevent duplicates, handle lag |
| **Identity and security** | Which SSO, LDAP, encryption keys, certificates, and secrets does the app use? | Identity and access foundations must be ready first |
| **Network/DNS** | How are IP ranges, private endpoints, NAT, firewalls, DNS, and cross-region traffic set up? | Sets infrastructure prerequisites and limits cross-environment links |
| **Operations** | Who handles on-call, alert routing, deployments, backups, and restores? | A wave is incomplete until it can be operated and recovered |
| **Business/calendar** | Does the system support period close, billing, sales events, or regulatory reporting? | Constrains cutover timing and value sequencing |
| **Vendors/external** | Are IP allowlists, licenses, partner APIs, contracts, or certifications affected? | Can create blocking prerequisites outside the migration team's control |

Discovery sources should combine **architecture diagrams, tracing/APM, flow logs, app configs, database queries, data pipelines, batch schedules, infrastructure as code, owner interviews, and failure drills**. Do not rely only on old diagrams: infrequent dependencies like month-end reporting may not appear during a one-week observation.

For each relationship, record at minimum: **source → target; purpose; protocol; data; frequency/load; synchronous vs. asynchronous; criticality; verification method; owner**. Flag unverified dependencies explicitly rather than assuming they do not exist.

### 3.2. Dependency Graphs Do Not Automatically Dictate Order

Suppose **A → B**, meaning A needs B to perform a function. This does **not force** B to migrate before A. There are at least three options:

1. **Migrate B before A** if B is ready and backward-compatible while A remains on-premises.
2. **Migrate A first, keep B on-premises** if hybrid connectivity, latency, security, and operations meet requirements.
3. **Migrate A and B in the same cutover unit** if data or transaction constraints make split operation unsafe.

To turn a relationship into a scheduling rule, specify the **condition**: “B is live in the cloud,” “B has a tested hybrid endpoint,” or “A and B cut over simultaneously.” Never mechanically translate every dependency arrow into a rigid ordering rule.

### 3.3. Dependency Cycles and Shared Databases

If A calls B and B calls A, splitting A and B across waves can introduce cross-network call loops, higher latency, and hard rollbacks. Similarly, two apps writing to transactionally coupled tables create a **data consistency boundary**.

Remediation depends on the case:

- **Combine into one migration group** when split operation is unsafe.
- **Break the cycle** using well-defined API contracts, events, outboxes, or translation adapters; test backward compatibility during transition.
- **Separate data ownership** by domain and schema roadmap; use CDC for readers where appropriate, avoiding uncoordinated dual writes.
- **Defer migration** until consistency and recovery paths are proven.

A clean application diagram that ignores “shared database write” edges can derail wave planning from day one.

## 4. Prioritizing by Business Value and Readiness

Once dependency constraints are mapped, the team selects among **feasible options** based on value.

### 4.1. Per-Workload Assessment Profile

Each workload should have a concise decision record:

| Field | Details to Confirm |
|---|---|
| Business owner and technical owner | Who accepts business risk; who owns the system technically |
| Value and deadlines | Expected benefits, urgency, regulatory/contract dates |
| Criticality | Outage impact, sensitive data, customer blast radius |
| Mandatory dependencies | Systems, data, integrations, and compatibility conditions |
| Readiness | Automated tests, deployment docs, observability, backup/restore, target resources |
| Migration approach | Rehost/replatform/refactor/retain/... and design changes |
| Risks and mitigations | Data loss potential, downtime, cost, latency, staffing skills |
| Acceptance criteria | SLOs/SLAs, reconciliation results, UAT, operational gates |

### 4.2. Priority Scores Are Only a Decision Aid

You can score four factors on a 1–5 scale:

- **B**: business value once migrated; 5 is very high.
- **U**: urgency from deadlines/commitments; 5 is very urgent.
- **S**: technical readiness; 5 means full supporting evidence.
- **R**: residual risk; 5 is very high risk.

An illustrative formula:

\[
P=0.40B+0.25U+0.20S-0.15R
\]

Weights must be agreed upon by business and architecture owners; **P is not an industry standard**. Critically, a high score cannot override hard blockers such as missing data recovery, pending compliance approval, or missing mandatory integrations.

Hypothetical scoring example:

| Workload | B | U | S | R | P | Current Conclusion |
|---|---:|---:|---:|---:|---:|---|
| Orders | 5 | 5 | 2 | 5 | 2.90 | Not eligible yet due to integrations and rollback |
| Inventory | 4 | 4 | 3 | 3 | 2.75 | Needs bridge to ERP completed |
| Product catalog | 3 | 2 | 5 | 1 | 2.55 | Suitable as pilot |

Orders scores highest, yet catalog is the sensible Wave 1 candidate **at the time of evaluation**. As conditions change, recalculate scores and update the decision instead of locking the initial order.

### 4.3. Distinguishing “Worth Doing Early” from “Ready to Do Early”

Sequencing should pass through two filters:

1. **Feasibility gate:** are dependencies, data safety, connectivity, security, operations, testing, business windows, and staffing satisfied?
2. **Prioritization:** among candidates passing the gate, choose the bundle offering the best value, acceptable risk, and fit with team capacity.

Early waves typically favor representative workloads with clean boundaries, low customer blast radius, and solid observability to refine the process. However, if a regulatory deadline or data center risk forces an important system early, add resources and controls rather than blindly following a “easiest first” rule.

## 5. Designing Waves from Graphs, Value, and Delivery Capacity

A practical workflow can follow seven steps.

### Step 1: Inventory and Confirm Dependencies

Create one row per independently owned workload, database, integration, or infrastructure component. Mark the **system of record**, sync direction, and critical business paths. For revenue-generating paths, trace the **entire call chain**, not just the edge service.

### Step 2: Establish Shared Foundations (Wave 0)

Before migrating production workloads, prepare shared prerequisites: account/subscription/project partitioning, IAM/SSO, networking and DNS, keys/secrets, logging, tracing, alerting, IaC, CI/CD, backups, cost controls, incident operations, and connectivity to remaining on-premises systems.

**Wave 0 does not require migrating the entire IAM or ERP system.** It means finishing the capabilities and integration contracts needed for the next wave—such as federating with on-premises SSO or establishing private links to the ERP.

### Step 3: Identify Indivisible Groups

Identify component clusters that must move together: services and databases sharing transactions, tightly coupled dependency cycles, or incompatible protocol versions during mixed runs. For separable groups, specify decoupling mechanisms such as contract versioning, event bridges, and data adapters.

Do not bundle apps just because they share a host if they can move independently; conversely, do not split two apps merely because they live in separate repositories.

### Step 4: Form Wave Candidates Around Value Streams

Organize around **business capabilities** (e.g., “catalog lookup,” “ordering,” “fulfillment”) and data boundaries. Define pilot, early-value, core-system, and legacy-retirement waves. Inspect every cross-environment dependency that will exist in each intermediate state.

### Step 5: Check Capacity and Business Calendars

A plan can be architecturally sound yet unexecutable if every wave relies on the same DBA, network security team, or business owner. For each wave, confirm:

- Implementation staff, cutover approvers, on-call rotation, and UAT sign-off;
- Link bandwidth, quotas, buffer capacity, and parallel-run budget;
- Peak traffic periods, reconciliation schedules, financial close, and change freezes;
- Rehearsal windows, data transfer time, hypercare duration, and readiness lead time for the next wave.

Waves can be prepared in parallel, but cutovers sharing resources or data dependencies must be staggered appropriately.

### Step 6: Define Entry and Exit Gates for Each Wave

An example **entry gate** includes: approved target architecture; owners assigned to dependencies; network, access, and encryption tested; data sync plan ready; backup/restore rehearsed; functional and load tests passed; cutover/rollback runbook staffed; business sign-off on timing.

An **exit gate** includes: users routed via the new path; transactions accurate; data reconciled; service metrics within agreed thresholds; alerts and on-call active; docs/configs updated; open items assigned with due dates. Only after stabilization should subsequent waves expand scope or pace.

### Step 7: Record Decisions and Update Continuously

The wave plan is a **living plan**. Every change in dependencies, risks, or readiness must update the graph, sequence, budget, and schedule. Significant choices should be captured in ADRs (Architecture Decision Records): context, options, trade-offs, decision, approvers, and review triggers.

## 6. End-to-End Example: Migrating an E-Commerce Platform

An enterprise operates an e-commerce website, product catalog, order management, inventory, reporting, and ERP integration. The goal is peak-season scalability and reduced reliance on legacy infrastructure, while the **ERP stays on-premises** initially. The partner payment gateway remains an external service.

### 6.1. Illustrative Dependency Diagram

~~~mermaid
flowchart LR
    U[Customer] --> F[E-commerce Web]
    F --> C[Catalog API]
    F --> O[Order API]
    O --> I[Inventory API]
    O --> P[External Payment Gateway]
    O --> D[(Order DB)]
    I --> E[On-premises ERP]
    E --> S[Catalog sync stream]
    S --> C
    D --> X[CDC / order events]
    X --> B[BI / reporting]
~~~

Arrows show call or data flows; the diagram does **not mean** every target node must migrate first. For instance, Inventory can run in the cloud and call the on-premises ERP provided latency, network security, resilience, and disconnect behavior have been tested.

The delivery team identifies key conditions:

- The catalog sync stream from ERP to Catalog runs reliably over a tested connection.
- Inventory implements timeouts, bounded retries, and graceful degradation if ERP slows down; it never assumes hybrid links are always up.
- Order API and order transaction storage form a single **cutover unit** for consistency; write-authority handoff is designed before shifting customer traffic.
- Payment gateway integration prevents double-charging using idempotency keys and partner reconciliation workflows.
- BI consumes CDC/events, tolerates replays and duplicates, and never queries the live migrating write database directly.

### 6.2. Proposed Wave Breakdown

| Wave | Scope | Value/Rationale | Key Prerequisites Before Moving |
|---|---|---|---|
| **Wave 0: Foundation** | Landing zone, hybrid network, SSO, DNS, logging, secrets, IaC, backups, monitoring, catalog sync | Builds safe operating foundation and testability | Connectivity, permissions, incident drills, cost controls passed |
| **Wave 1: Pilot** | Catalog API and read-only catalog data | Early value, low write volume, validates migration pipeline | Stable ERP→Catalog feed; fallback path to old version ready |
| **Wave 2: Integration** | ERP bridge and Inventory API | Reduces legacy dependency at app tier, proves hybrid model | Integration contracts, latency, retries, link-loss tests passed |
| **Wave 3: Core transactions** | Order API and Order DB as one cutover unit; payment integration config | Moves core business capability | Inventory ready; CDC, order reconciliation, load tests, recovery runbook passed |
| **Wave 4: Experience & analytics** | E-commerce Web and event-driven BI | Completes customer flow on cloud, unlocks fresh analytics | Orders stable; API contracts and reporting data reconciled |
| **Wave 5: Decommission** | Retire old resources no longer serving traffic | Cuts cost and operational debt | Zero consumers remaining; data retention, audit, rollback horizon met |

This is **one candidate plan**, not a mandatory sequence for every retail platform. If Web can safely use hybrid APIs, Web could move earlier for value. If Inventory and Order share database transactions, adjust boundaries to merge the cutover or split data first. Decisions rest on discovery evidence.

### 6.3. Intermediate States Are Architectures That Must Be Operated

Between Wave 1 and Wave 3, Catalog runs in the cloud while Order stays on-premises. The design must address:

- **Call paths:** endpoint locations, DNS, routing, certificates, timeouts, circuit breakers, and fallback during link outages.
- **Data:** source of truth; which data is read-only vs. writable; acceptable sync lag; detection of missing/duplicate records.
- **Security:** service identities, mTLS or equivalent auth, network segmentation, and least privilege.
- **Observability:** distributed traces spanning both environments, ordering flow dashboards, logs with correlation IDs, business-impact alerts.
- **Cost:** data transfer, parallel legacy and cloud runs, database replicas, dual-site operations overhead.

If cross-environment latency breaks p95 targets or network errors cause unreconcilable orders, revise the design: co-locate chatty components, replace synchronous calls with events where appropriate, or merge waves.

## 7. Coordinating Data, Cutover, and Rollback

Data is usually the riskiest part of a wave. Migrating compute cleanly does not mean the business has migrated safely.

### 7.1. Data Migration Plan

For write-intensive systems, answer:

1. **Where is the source of truth before, during, and after cutover?** Write authority must be unambiguous at every moment.
2. **How is initial data moved?** Bulk copy, backup/restore, replication, or schema conversion tools.
3. **How are ongoing changes caught up?** CDC, log shipping, or ordered application streams with watermarks and lag tracking.
4. **How is data accuracy verified?** Row counts, checksums, foreign keys, balances/totals, and business invariants.
5. **How is post-cutover data protected?** Backups, recovery, and handling if reverting to the old environment.

For databases with multiple writers, avoid **ad-hoc dual-write**: a transaction succeeding in place A while failing in place B creates hard-to-repair drift. If two-way writes are unavoidable, engineer explicit sync, idempotency, conflict detection, and compensation; normally prefer a **single write authority** per phase.

### 7.2. Typical Cutover Sequence

~~~text
1. Lock baseline, owners, and Go/No-Go criteria.
2. Back up or create restore point; verify restore actually works.
3. Bring target data to near-sync state; check watermarks/lag.
4. Pause or control required write flows; complete final sync.
5. Switch write authority and route traffic per runbook.
6. Run smoke tests, synthetic transactions, reconciliation, and monitor SLOs.
7. Decide to stay on target, restore per proven plan,
   or apply a forward fix when reversal is impossible.
8. Hand over on-call operations and hypercare; do not rush to delete the old source.
~~~

The duration of read-only windows, write pauses, DNS TTL reductions, or weighted traffic shifts depends on technology and product SLAs. Partial traffic splitting is **unsafe** if both sides write to data without a consistency mechanism.

### 7.3. Rollback Is a Tested Capability, Not a Promise

The runbook must specify:

- **Decision points:** before and after which steps is reversal still viable?
- **Trigger signals:** transaction errors, reconciliation mismatches, latency, data integrity issues, or security incidents.
- **Newly created data:** can it be safely reverse-synced, compensated in business logic, or must it be fixed forward?
- **Decision authority:** who issues Go/No-Go calls and who executes them?
- **Rehearsal evidence:** have backup restores, route failbacks, and reconciliations been practiced?

For example, a project might set trial triggers like “transaction error rate exceeds 1% for 5 minutes” or “p95 doubles baseline for 15 minutes”; **these are illustrative numbers only**. Real thresholds must tie to SLOs, seasonality, and normal behavior. Notably, a payment already recorded by a partner cannot be erased simply by rolling back a database: it requires idempotency, reconciliation, and refund/compensation workflows where appropriate.

## 8. Wave Plan Template for Team Execution

An actionable wave plan can use the table below linked to detailed designs:

| Plan Field | Example Content |
|---|---|
| Wave ID / name | W3 – Order core |
| Business outcome | New orders processed from the cloud with zero lost or duplicate orders |
| In scope | Order API, Order DB, CDC pipeline, payment integration configuration |
| Out of scope | On-premises ERP, external payment gateway |
| Dependency gate | Inventory API stable; order data reconciled; PSP confirms integration flow |
| Migration strategy | Replatform application; replicate database then switch write authority |
| Accountable roles | Business owner, tech lead, DBA, SRE, security, change approver |
| Execution plan | Dry run → change freeze → final sync → cutover → acceptance |
| Go/No-Go criteria | Backup/restore passed; load tests passed; runbook and on-call staffed |
| Success criteria | Transactions, data, SLOs, and business metrics within approved thresholds |
| Incident plan | Fail back routes only if data-safe; otherwise forward fix/compensation |
| Hypercare and close | Dashboards, heightened on-call, acceptance sign-off, close open items before next wave |

Maintain a **risk register** per wave with likelihood, impact, mitigations, owners, and trigger signals. A high-score risk without a mitigation plan is a blocking decision item—never mask it behind percentage-complete metrics.

### 8.1. Tracking Dashboard

Do not report only “70% of servers migrated.” More useful metrics include:

- **Readiness:** workloads passing entry gates, dependencies missing owners, successful dry runs.
- **Delivery:** migration groups cut over, rollbacks/forward fixes, completion duration, on-time task rate.
- **Reliability:** availability, p95/p99, error rate, event lag, reconciliation results, and SLO burn.
- **Security & operations:** config compliance rate, acknowledged alerts, backup/restore passes, post-migration incidents.
- **Business value:** measured business outcomes and infrastructure debt/cost reductions after legacy shutdown.

A wave is only marked “complete” when it is **operable and meets criteria**, not merely when VMs or containers start running in the cloud.

## 9. Well-Architected Trade-Offs

Wave planning is a multi-objective optimization directly tied to architecture pillars:

| Review Lens | Questions When Selecting Waves | Example Trade-Off |
|---|---|---|
| **Operational Excellence** | Are runbooks, IaC, observability, change processes, and owners ready? | Migrate fewer workloads first to standardize operations before accelerating |
| **Reliability** | Are RTO/RPO, fault tolerance, and hybrid dependency handling met? | Group apps with their data to reduce consistency errors, despite larger waves |
| **Security** | Are least privilege, encryption, data locality, and audits verified? | Keep sensitive data on-premises until target controls pass verification |
| **Performance Efficiency** | Do network latency and throughput meet targets? | Co-locate services making heavy synchronous calls into the same region |
| **Cost Optimization** | What are parallel-run, data transfer, licensing, rollback, and ops costs? | Shorten dual-run periods while keeping an adequate verification window |
| **Sustainability** | Are idle resources reduced and redundant infrastructure retired post-stabilization? | Schedule controlled decommissioning instead of running two estates indefinitely |

Small waves limit blast radius but can prolong hybrid operations and increase cost. Large waves shorten transition phases but complicate testing and rollback. The right wave size depends on **data boundaries, team capacity, and organizational risk tolerance**.

## 10. Wave Anti-Patterns That Commonly Fail

**Grouping by server list or org chart:** real dependencies do not follow organizational boundaries. Fix by mapping business and data flows first, then assigning owners.

**Prioritizing solely by ROI score:** high-value workloads failing entry gates get scheduled prematurely. Separate feasibility gates from priority ranking.

**Moving applications before understanding data write authority:** two environments write to the same entities, causing drift and impossible rollbacks. Design write handoff and reconciliation criteria upfront.

**Leaving hybrid dependencies unmeasured for too long:** chatty synchronous cross-environment calls raise latency, egress costs, and failure modes. Measure real call paths and time-box intermediate states.

**Mistaking technical success for business success:** containers are healthy, yet refunds, financial close, nightly batches, or month-end reports break. Require business-journey test suites and UAT evidence aligned with operating calendars.

**Skipping hypercare and decommissioning:** teams rush to the next wave while alerts, data, and operations remain unstable and legacy systems keep accruing bills. Enforce exit gates, stabilization windows, and explicit teardown waves.

## 11. Wave Design Exercise

A company has five workloads: **Identity** (existing SSO supports federation), **Catalog** (read-heavy), **Order** (writes orders), **Inventory** (calls on-premises ERP), and **BI** (reads order data via CDC). Order depends on Inventory; Catalog receives synced data from ERP; BI needs Order data. The team has one dedicated DBA and capacity for only **one major write-data cutover at a time**.

Design three to four waves after the foundation wave, determining:

1. Which components must move together and which can stay on-premises temporarily?
2. If Inventory lacks resilience against hybrid network failures, should Order go in an early wave?
3. What are the three most critical Go/No-Go criteria for the wave containing Order?
4. When BI migrates after Order, how do you prove reporting data has no gaps or duplicates?

**Reference Solution:**

| Wave | Scope | Rationale |
|---|---|---|
| Wave 0 | SSO federation, hybrid network, IAM, DNS, logging, backups, CDC foundation | Enables applications to interact securely |
| Wave 1 | Catalog | Read-heavy pilot, validates ERP feed and operations |
| Wave 2 | Inventory and ERP bridge | Measures latency, tests timeouts and recovery on link loss |
| Wave 3 | Order with its transactional database/data store | After integrations and write-handoff plans are proven |
| Wave 4 | BI | Uses stabilized CDC; reconciles counts, keys, and revenue invariants |

For Order, three minimum gate groups are: **(1)** Inventory/ERP and payment dependency flows pass expected load/failure tests; **(2)** sync, write-authority handoff, backup/restore, and data reconciliation pass; **(3)** ordering journey tests, SLOs, on-call readiness, and Go/No-Go sign-off are approved. For BI, do not check row counts alone—verify CDC checkpoints/watermarks, duplicate-event handling, order totals, and revenue totals over time windows against the source system.

If discovery reveals that Order and Inventory write to the same inseparable database, the answer must **change**: merge them into one cutover unit or run a data-separation project first. That is the hallmark of a sound plan: sequence adapts to evidence rather than forcing the system to fit an initial diagram.

## 12. Pre-Lock Schedule Checklist

- [ ] Business value, business owner, deadlines, and success metrics are confirmed.
- [ ] Call flows, data flows, writers, batch jobs, and external dependencies are verified.
- [ ] All cross-environment links have network, security, latency, timeout, and monitoring designs.
- [ ] Components requiring consistency are grouped into proper cutover units or have a proven split strategy.
- [ ] Wave 0 provides minimum IAM, DNS, deployment, observability, data protection, and operations capabilities.
- [ ] Every wave has entry/exit gates, RTO/RPO, dry runs, UAT, Go/No-Go approvers, and incident runbooks.
- [ ] Write-handoff, CDC, reconciliation, rollback/forward fix, and newly created data handling have been tested.
- [ ] Team capacity, change freezes, dual-run costs, and hypercare windows are built into the schedule.
- [ ] Legacy systems are decommissioned only after confirming zero consumers and meeting retention requirements.

**Core principle:** build waves from **business and data boundaries that can operate safely in every intermediate state**, then prioritize by value, deadlines, and readiness. A strong migration plan does not just state *what moves first*—it proves *why that sequence is safe, valuable, and controllable when deviations occur*.
