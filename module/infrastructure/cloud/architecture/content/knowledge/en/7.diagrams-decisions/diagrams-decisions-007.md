# Managing Assumptions, Risks, and Architecture Debt

> **Chapter:** Diagrams and Decisions  
> **Scope:** Designing cloud application architectures from business requirements through networking, compute, data, and deployment models. This lesson focuses on how to capture, verify, and track **unknowns**, **potential sources of harm**, and **accumulated technical trade-offs** across the architecture lifecycle, guided by Well-Architected thinking.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **assumptions**, **risks**, **active issues**, **constraints**, and **architecture debt**.
2. Record an assumption with its rationale, confidence level, owner, verification plan, and review conditions.
3. Write risks using the **cause → uncertain event → consequence** structure, assess impact, define mitigations, and identify who accepts residual risk.
4. Identify architecture debt arising from deliberate decisions or system evolution; evaluate cost of delay and remediation options.
5. Link **architecture diagrams, quality requirements, ADRs, assumptions, risks, debt, tests, and runbooks** so decisions remain traceable.
6. Establish a review cadence and tracking metrics across reliability, security, performance, scalability, cost, and operations for cloud architectures.

## 1. Why Must These Three Be Managed Together?

Cloud design always begins with incomplete information: unknown peak load, third-party failure rates, data growth rates, six-month cost trajectories, or final customer operational requirements. Teams must make decisions before everything can be verified.

If uncertainties are left undocumented, architecture diagrams gradually look like "proven truth". When requirements change, newcomers struggle to understand why a database sits in a specific region, why no standby region exists yet, or why multiple services share one queue.

These three concepts are interconnected:

- **Assumption:** something temporarily treated as true so design can proceed. If false, the architecture or plan must change.
- **Risk:** an **uncertain future event or condition** that could negatively affect business goals or quality requirements. An unverified assumption can increase risk.
- **Architecture debt:** structural limitations or trade-offs making future changes, operations, or quality targets costlier than necessary. Debt can be accepted temporarily and managed intentionally—it is not necessarily a design flaw at the time the decision was made.

Example:

> **Assumption A-01:** Traffic will peak at 300 requests/second during the first three months.  
> **Risk R-01:** If actual load exceeds forecast and the shared database hits connection limits, checkout may breach latency SLOs or fail.  
> **Debt D-01:** The team temporarily shares one database between Booking and Reporting to launch faster; heavy reporting queries make later splitting and scaling harder.

Assumption A-01 can be verified with market analysis and load testing; Risk R-01 can be mitigated with resource limits, monitoring, and load drills; Debt D-01 can be addressed with read replicas, moving reporting to a read model, or separating data pipelines once evidence justifies it.

## 2. Distinguishing Assumptions, Risks, Issues, Constraints, and Decisions

| Concept | Core question | Example in cloud design | Management action |
| --- | --- | --- | --- |
| **Assumption** | What are we treating as true while still uncertain? | Peak load under 300 req/s | Verify, measure, set deadline and invalidation conditions |
| **Risk** | What might happen and cause damage? | DB connection exhaustion disrupting checkout | Analyze impact, mitigate, track residual risk |
| **Issue** | What has already happened or is currently broken? | DB is running out of connections in production | Resolve incident per procedure and track outcome |
| **Constraint** | Which boundary must be obeyed? | Data must be stored inside approved regions | Validate every option for compliance |
| **Architectural decision** | Which approach did we choose, and why? | Choose multi-AZ and warm standby | Record ADR, rejected options, evidence, consequences |
| **Architecture debt** | Which structural choice increases future cost or friction? | Shared schema couples releases across two domains | Measure impact, set remediation threshold, track roadmap |

**Key distinctions:**

- "The database is failing right now" is an **issue**; "the database may fail as load grows" is a **risk**.
- "The company may only store data in approved regions" is a **constraint** requiring confirmation from an authoritative source; never turn a mandatory legal requirement into a risk scored for optional acceptance.
- "Assuming traffic mainly originates from Vietnam" is not a region-selection decision. **Choosing a region** is a decision that must record its rationale and underlying assumptions.
- A system that has not split into microservices does not automatically carry architecture debt. Call something debt only when you can point to **specific costs, risks, or limitations relative to current or projected needs**.

### Relationships Across the Design Lifecycle

~~~mermaid
flowchart TD
    Q["Business and quality requirements"] --> A["Assumptions with owners and evidence"]
    Q --> ADR["Architectural decisions (ADRs)"]
    A --> ADR
    ADR --> DIAG["Logical / deployment / data-flow diagrams"]
    A --> R["Potential risks"]
    ADR --> R
    ADR --> D["Architecture debt / remaining trade-offs"]
    DIAG --> T["Testing, drills, and operational metrics"]
    T --> A
    T --> R
    T --> D
    R --> REV["Controlled review and change"]
    D --> REV
    REV --> ADR
~~~

The diagram depicts accountability and evidence links, not a strictly linear sequence. Teams can uncover risks or debt at any stage, including after years in production.

## 3. Managing Assumptions as Testable Hypotheses

### 3.1. How to Write a Good Assumption

A good assumption is specific, testable, and explicit about what happens if it turns out false. Use the template:

> **We assume** [condition/value] **within** [scope and timeframe], **based on** [evidence source]; **if false**, [impact]; **we will verify via** [method, target date, owner].

Example:

> **A-01:** During the first three months post-launch, API gateway p95 load will not exceed 300 requests/second during peak hours under the current sales plan. Evidence comes from pilot user volume and Product forecasts. If false, autoscaling policies and database capacity must be revised. SRE will compare forecasts against load tests and weekly production telemetry during month one.

The 300 requests/second figure here is an **illustrative assumption**, not a general recommended threshold.

Common sources of assumptions in cloud design:

| Area | Assumptions to clarify | How to verify |
| --- | --- | --- |
| **Business** | Concurrent users, peak events, user countries | Product interviews, real metrics, growth scenarios |
| **Networking** | Latency to region, partner bandwidth, DNS stability | Empirical tests from user locations, link checks |
| **Compute** | CPU/RAM per request, autoscaling speed, cold-start time | Benchmarks, load tests, startup and saturation observation |
| **Data** | Read/write ratio, record size, growth rate, consistency needs | Workload analysis, index/partition tests, concurrency tests |
| **Reliability** | Dependencies can tolerate local faults; replicas handle recovery load | Fault injection, AZ/region failover tests, restore drills |
| **Security** | Data classification, permitted residency, identity management | Security/Legal sign-off, data-flow mapping, threat modeling |
| **Cost** | Projected pricing, resource utilization, ingress/egress volume | Cost models, invoice audits, and budget alerts |
| **Operations** | Team capacity for 24/7 on-call, multi-region ops, IaC management | Capability assessment, tabletop exercises, runbook rehearsals |

### 3.2. Assumption Log

| ID | Assumption | Confidence | Current evidence | Impact if false | Verification / Due | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A-01 | Peak load does not exceed 300 req/s during trial phase | Medium | Product forecast, limited prod data | API/DB may overload | Load test and week-1 telemetry; before go-live | SRE | Unconfirmed |
| A-02 | Payment partner responds within checkout's acceptable window | Low | Sandbox results | Request timeouts, uncertain payment state | Live-like environment and fault tests; before go-live | Payment Team | Needs testing |
| A-03 | Standby region is approved to store customer data | Low | Preliminary discussion | Data-replication design violates policy | Written Security/Legal confirmation | Security | Decision blocker |
| A-04 | On-call ops team can recover within 60 minutes | Low | Unrehearsed runbook | Misses RTO target | Region-loss drill measuring real duration | SRE | Needs testing |

**Confidence levels** should reflect evidence quality: contractual/policy docs, production data, realistic test results, prototypes, expert estimates, or guesses. Never write "90% confident" without quantitative grounding.

An assumption moves through states: **New → Validating → Confirmed / Invalidated / Obsolete**. When invalidated, locate all ADRs, diagrams, risk registers, and test plans that depended on it.

### 3.3. Prioritizing Assumption Verification

Not every assumption deserves equal effort. Prioritize by:

1. **Impact if wrong:** does it affect revenue, data, correctness, SLOs, compliance, or recoverability?
2. **Uncertainty:** how strong is current evidence, and what is missing?
3. **Irreversibility:** would being wrong force changing data models, regions, contracts, or platforms?
4. **Lead time / urgency:** does it block an upcoming architectural decision or release date?
5. **Verification cost:** how much uncertainty can a spike, benchmark, or review eliminate?

For instance, an assumption about **data residency** must be confirmed before choosing where to place replicas; an assumption about dashboard color schemes can wait. Verification priority is not the same as product feature ranking: safety-critical assumptions must be tested even when testing takes effort.

### 3.4. Designing a Test That Can Falsify an Assumption

Assumption: "A primary database with 2,000 max connections can serve target load."

The test must specify:

- **Workload:** transactions/second, read/write ratio, dataset size equivalent to target tenants/orders.
- **Environment:** instance size, connection pool, replica count, network, cache, and data seeding state.
- **Metrics:** p95/p99, error rate, active connections, CPU, IOPS, lock waits, queue age, and cost.
- **Decision criteria:** thresholds to pass, approver, and expected safety margin.
- **Extra stress conditions:** one replica down, increased cache misses, heavy queries, high-latency network paths.

Record results with date, configuration, version, test dataset, and report links. A test on a tiny dataset does not prove the system sustains long-term production load.

## 4. Architecture Risk Register and Assessment

### 4.1. Writing Actionable Risks

Useful structure:

> **Because of** [cause/condition], **there is a possibility that** [uncertain event], **leading to** [impact on measurable objectives].

Example:

> **R-05:** Because the payment provider may send callbacks late after the API caller times out, the system may retry payment commands without checking status, leading to **duplicate charges** and reconciliation/refund costs.

Saying "payments have risks" is too vague; it lacks an actor, consequence, or owner.

### 4.2. Categorizing Risks Across Cloud Architecture

| Category | Example risk event | Warning signals / controls |
| --- | --- | --- |
| **Reliability/DR** | Full-region loss or corrupt backup that cannot restore | Replica lag, DR drills, backup validation |
| **Security** | Exposed secrets, overly broad permissions, cross-tenant access | IAM reviews, secret scanning, pentests/authorization tests |
| **Data integrity** | Double bookings, duplicate event processing, inconsistency | Idempotency, DB constraints, reconciliation |
| **Performance** | API fan-out, DB saturation, noisy neighbor | p95/p99, error rates, saturation, quotas |
| **Scalability** | Unable to scale fast enough during peak bursts | Load tests, autoscaling signals, queue age |
| **Cost** | Egress, replication, or logging exceeds budget | Budget alerts, forecasts, cost allocation |
| **Dependency/vendor** | Cloud service, DNS, or partner API outage | SLA/dependency maps, fallbacks, timeouts, tabletops |
| **Operations** | Configuration drift, missing incident permissions, wrong runbooks | IaC drift detection, drills, on-call readiness |
| **Compliance** | Data resides in an unapproved region | Data classification, flow mapping, Legal review |

### 4.3. Assessing Likelihood and Impact

A qualitative matrix aids **triage**, without fabricating exact probabilities:

| Likelihood \ Impact | Low | Medium | High |
| --- | --- | --- | --- |
| **Low** | Monitor | Monitor or mitigate | Prioritize controls |
| **Medium** | Mitigate if reasonable | Plan mitigation | High priority |
| **High** | Plan mitigation | High priority | Urgent / escalate |

Anchor levels to real context: high impact may mean losing customer data, failing security requirements, prolonged transaction outage, or major revenue loss. High likelihood means the event already occurs frequently or strong evidence shows it will occur within the evaluation horizon.

If an organization uses numeric scoring, it can use **likelihood 1–5** and **impact 1–5** to aid ranking, yet multiplying two **ordinal** scales is only a rough indicator; never treat "16" as quantitatively twice the loss of "8". When reliable probability and loss data exist, estimate **expected loss = probability × impact**, alongside tail-risk scenario analysis.

**Important:** compliance/legal risks with mandatory conditions must be remediated per authoritative requirements; you cannot use a low score to self-approve a violation.

### 4.4. A Practical Risk Register

| ID | Risk and consequence | Likelihood / Impact | Existing controls | Treatment plan | Owner / Due |
| --- | --- | --- | --- | --- | --- |
| R-01 | Primary region outage stops booking beyond RTO | Medium / High | Daily backups | Warm standby + failover drill | SRE / before go-live |
| R-02 | Non-idempotent retries cause duplicate charges | Medium / High | API timeouts | Payment keys, status lookups, replay tests | Payment / sprint 3 |
| R-03 | Reporting queries slow down checkout on shared DB | High / Medium | DB CPU dashboard | Queue/replica, quotas, measure checkout p95 | Data / sprint 4 |
| R-04 | Wrong backup region causes policy violation | Unknown / High | Resource tags | Security/Legal region sign-off, policy-as-code | Security / before provisioning |
| R-05 | Cross-region egress exceeds budget | Medium / Medium | Budget alerts | Measure real traffic, cost forecast, bound replication | FinOps / monthly |

After mitigation completes, record **residual risk**, evidence, and the authorized risk acceptor. A risk does not vanish merely because a ticket says "implemented retries": prove retries create no side effects under timeouts, packet loss, and duplicate events.

### 4.5. Four Ways to Respond to Risk

- **Avoid:** change the solution or scope so the specific risk cannot arise. For example, do not replicate personal data into an unapproved region.
- **Mitigate:** lower likelihood or impact through controls. For example, multi-AZ, restore-tested backups, least-privilege IAM, rate limits.
- **Transfer/Share:** contracts, insurance, or managed services can shift part of operational duties or financial loss, yet **never erase accountability** for customer data or outcomes.
- **Accept:** record explicit rationale, expiration, trigger thresholds, authorized approver, and residual risk; apply only when valid under policy and risk appetite.

**Avoid implicit "acceptance"** caused by failing to log risks, having no owner, or assuming a provider's SLA will reimburse full business damages.

## 5. What Is Architecture Debt and How Does It Form?

### 5.1. From Today's Trade-Off to Future Cost

**Architecture debt** is the accumulated consequence of a design or structure that makes future changes, operations, or quality targets harder, riskier, or costlier. It is a subset of technical debt focused on **component boundaries, data, dependencies, deployment models, scalability, and operations**.

Debt can arise from:

1. **Deliberate borrowing to launch:** temporarily using one shared queue before load data exists for cell partitioning.
2. **Missing information:** picking a region from an inaccurate customer-location forecast, later requiring migration.
3. **Shifting requirements:** growing from 10 tenants to 1,000 tenants exposes limits in an older data model.
4. **Accumulation across changes:** services gradually couple directly to each other's internal schemas and APIs.
5. **Skipping foundational engineering:** lacking IaC, tracing, backup restore tests, policy enforcement, or contract testing.

Not every simplification is debt. If a modular monolith still meets SLOs, cost targets, and release speed, **not splitting into microservices yet** does not by itself create debt.

### 5.2. "Principal" and "Interest"

- **Principal — the work to fix:** estimated effort to redesign, migrate data, decouple dependencies, test, and release.
- **Interest — the ongoing tax:** extra time per deployment, extra infrastructure spend, recurring incidents, slower recovery, more security bugs, or blocked teams.

Example of "shared database" debt:

- Principal: separate Booking/Reporting ownership, build a read model, and migrate queries.
- Interest: heavy reports spike checkout p95; Reporting migrations force Booking to release simultaneously; the DB must continually scale up for mixed workloads.

**Do not blindly pay down every item of debt.** Debt with high principal yet low interest that threatens no current targets can be tracked with a clear re-evaluation trigger. Debt risking data loss or violating mandatory requirements must be addressed early, regardless of launch pressure.

### 5.3. Debt Register

| ID | Debt item | Reason/ADR | Observed interest | Remediation plan | Trigger/Owner |
| --- | --- | --- | --- | --- | --- |
| D-01 | Booking and Reporting share one primary DB | ADR-008: prioritized MVP launch | Checkout p95 spikes during reports; higher IOPS | Read replica/read model, offload batch jobs | When p95 breaches target or DB > threshold; Data |
| D-02 | Standby region lacks IaC | ADR-012: single-region initial launch | DR config drift, slow drills | IaC + pipeline + runbook | Before committing new RTO; Platform |
| D-03 | API changes lack contract tests | Rapid integration development | Consumer breakages on version bumps | Consumer-driven contract tests, versioning policy | Next compatibility incident; API lead |
| D-04 | Uniform logging without cross-service tracing | Correlation not yet wired | Rising MTTR, hard root-cause tracing | Tracing, trace propagation, dashboards | When flows > 3 sync hops or MTTR > threshold; SRE |

A debt record should capture: **ID, component, description, origin, evidence, impact, owner, remediation/estimate, remediation risks, trigger, and status**. Mark "paid off" only when real evidence shows impact dropped and the old workaround is removed or properly bounded.

## 6. Separating Architecture Debt from "Incomplete Features"

Do not turn the backlog into a dumping ground for everything undone. Distinguish categories because each is managed differently:

| Symptom | Appropriate category | Example |
| --- | --- | --- |
| New capability never previously requested | Feature backlog | Internal app lacks multi-language support |
| Currently violating an approved requirement | Defect / gap / issue | Sensitive data not encrypted per approved policy |
| Design choice creating ongoing change cost or compounding risk | Architecture debt | Multiple teams blocked on releases due to unowned shared schema |
| Future threat that could miss an objective | Risk | Backups might not restore fast enough because they are untested |
| Fact lacking sufficient evidence | Assumption | Only 10% of customers will run reports during peak hours |

Items can **link together**: debt (no automated restore testing) increases risk (missing RTO) because an assumption (ops can restore manually in 60 minutes) remains unverified. Do not create three duplicate tickets with identical text; create records by distinct accountability and link by ID.

## 7. Linking Registers to Diagrams and ADRs

An architecture drawing is useful only if viewers know **which version describes production**, which boundaries are real, which pieces are merely proposed, and which decisions set constraints.

### 7.1. What Should Diagrams Show?

At each diagram level, add helpful context without cluttering:

- **Context diagram:** users, external systems, providers, and ownership boundaries; mark critical dependencies with risk IDs.
- **Container/Deployment diagram:** apps, DBs, caches, queues, networks, regions, AZs, data flows; mark current vs. target state and high-impact assumptions.
- **Component/Sequence diagram:** critical business flows, retries, timeouts, idempotency, state transitions, and where messages could duplicate or drop.
- **Data-flow / threat model:** data classification, trust boundaries, encryption points, and storage/replication locations.
- **Operational/DR diagram:** backups, replicas, failover paths, permissions, and dependent services; link runbooks and tests.

Every diagram should include **title, purpose, scope, update date, owner, as-is/to-be status, and links to related docs**. Highlight major risks with short labels like R-02; keep full analysis inside the risk register.

### 7.2. Example Diagram Annotated with Assumption/Risk/Debt IDs

~~~mermaid
flowchart LR
    U["Users"] --> GW["Gateway / WAF"]
    GW --> API["Booking API\nA-01: peak load"]
    API --> DB[("Primary DB - AZ 1\nR-01: region outage\nD-01: shared reporting")]
    API --> PAY["Payment provider\nA-02: callback latency\nR-02: duplicate charge"]
    DB --> BAK[("Backups\nR-03: untested restore")]
    DB -. "Read/analytics queries" .-> REP["Reporting"]
~~~

When the diagram changes, reviewers need to know: was R-01 mitigated, does D-01 still exist, and was A-02 measured in a representative environment? If a component is removed, review linked IDs before closing records.

### 7.3. Linking Along the Chain: Requirement → Decision → Evidence

~~~text
REQ-AVAIL-01: RTO <= 60 minutes and RPO <= 15 minutes
  ├── A-04: can the on-call team complete failover within 60 minutes?
  ├── R-01: primary region outage disrupts bookings
  ├── ADR-012: choose warm standby in an approved region
  │     ├── DIAG-DEPLOY-03: region/AZ/replication diagram
  │     └── D-02: standby region IaC incomplete
  ├── TEST-DR-05: region-loss drill, measure RTO/RPO
  └── RUNBOOK-DR-02: failover/failback and data reconciliation
~~~

These IDs are **illustrative examples**. This chain answers an auditor's question—"Can you prove your recovery commitment?"—by tracing straight to the design option, diagram, drill results, and remaining debt status.

## 8. Writing ADRs with Assumptions, Risks, and Reversal Conditions

An **Architecture Decision Record (ADR)** logs an important decision alongside its context and consequences. A useful ADR does not merely state "chose service X", but clarifies **under which conditions that choice holds true**.

### Abbreviated ADR Example

~~~markdown
# ADR-012: Standby Region for Booking Service

Status: Conditionally Accepted
Date: YYYY-MM-DD
Decision owner: System Architect and Business Representative

Context:
- REQ-AVAIL-01: RTO <= 60 minutes; RPO <= 15 minutes.
- REQ-COST-01: cloud infrastructure within approved budget.
- A-03: standby region complies with data residency (requires confirmation).
- A-04: SRE can recover within required timeframe.

Options:
A. Single multi-AZ region with periodic backups.
B. Primary multi-AZ region + warm standby region.
C. Dual active-active regions.

Proposed Decision:
- Choose B provided Security/Legal confirms A-03 and
  TEST-DR-05 proves both RTO and RPO are met.
- Do not claim RTO/RPO compliance until drill results are recorded.

Trade-offs and Risks:
- R-01: region failure, mitigated by standby and runbooks.
- D-02: temporary lack of standby IaC, must resolve before commitment.
- Replication incurs cost and does not replace point-in-time backups.

Review Triggers:
- DR drill fails; data policy changes;
  load or cost exceeds threshold; RTO/RPO targets change.

Linked Evidence:
- DIAG-DEPLOY-03, TEST-DR-05, RUNBOOK-DR-02, COST-PLAN-01.
~~~

RTO/RPO numbers are **illustrative requirements** only. Multi-AZ or warm standby does not inherently guarantee targets; you must test failover, replication lag, data restoration, and cross-region dependencies.

**When a decision changes**, create a new ADR or update the old ADR's status to *superseded* per organizational process with bidirectional links. Never erase the trade-off history that shaped the current architecture.

## 9. Prioritizing Action: Validate Assumptions, Mitigate Risks, or Pay Debt First?

No single formula fits every item. Follow this priority order:

1. **Mandatory conditions:** address active vulnerabilities, policy/contract violations, and ongoing incidents through proper emergency procedures.
2. **Decision-changing uncertainties:** validate assumptions that could mean picking the wrong region, data model, recovery strategy, or platform.
3. **High-consequence risks:** build controls, run drills, and quantify residual risk, especially around data and revenue paths.
4. **Debt compounding cost and incident rate over time:** prioritize using MTTR, change-failure rate, deployment duration, invoices, and SLOs.
5. **Additional optimizations:** pursue once quality targets are met and capacity remains.

Build an **action-selection table**:

| Item | Value if done | Cost/effort | Impact if delayed | Illustrative decision |
| --- | --- | --- | --- | --- |
| Verify A-03 (data residency region) | Eliminates wrong-architecture risk | Low/medium | Could force data migration | Do before provisioning |
| Drill R-01 (region loss) | Confirms RTO/RPO | Medium | Risk of overpromising SLAs | Block go-live until passed |
| Fix D-01 (Reporting shares DB) | Improves p95 and release independence | Medium/high | Ongoing degradation as reports grow | Schedule based on measured load |
| Upgrade secondary dashboard | Improves internal UX | Low | Minimal impact on core targets | Can defer |

You can apply **cost of delay divided by job size** for comparable items when data is solid. Always cite sources and uncertainty ranges for estimates; never fabricate false precision or dump mandatory compliance items into an arbitrary scoring queue.

### Debt-Reduction Strategies by Intervention Level

- **Stop debt growth:** restrict new dependencies on shared schemas, enforce API contracts and automated architecture checks.
- **Contain blast radius:** quotas, separate connection pools or queues for heavy workloads.
- **Pay down incrementally:** extract read models first, migrate data in batches, measure impact, and retire legacy paths.
- **Re-architect:** when debt harms platform goals, write a new ADR with migration and rollback plans.
- **Time-boxed acceptance:** when remediation cost exceeds ongoing interest and no mandatory rule is broken, set a clear review trigger.

Prefer **small, measurable, reversible** changes unless an urgent large migration is unavoidable.

## 10. Measuring for Evidence-Based Governance

Good metrics answer: which assumptions are proven, which risks remain high, and which debt truly hurts?

### 10.1. Cloud Quality Metrics

| Goal | Metrics to track | Action when threshold is breached |
| --- | --- | --- |
| Reliability | SLIs/SLOs, error budgets, incident rate, MTTR, DR results | Open risk/issue, inspect dependencies, and verify recovery |
| Performance | p95/p99 latency, saturation, throughput, queue age | Re-check load assumptions, caches, DB, network, and autoscaling |
| Security | IAM drift count, risky misconfigurations, vulnerability remediation time | Escalate by severity; update threat model/ADR |
| Scalability | Throttled request rate, autoscaling lag, growth rate | Run capacity tests, adjust quotas and data architecture |
| Cost | Budget forecast, cost/request, egress, idle DB/compute | Re-check resource assumptions, add cost debt to backlog |
| Operations | Lead time for changes, deployment failure rate, toil, recovery time | Inspect CI/CD, observability, and ownership debt |
| Data | Replication lag, backup success, restore verification, reconciliation errors | Check RPO/RTO and data-integrity risks |

An **error budget** is the allowable failure margin under a defined SLO. It helps Product and SRE balance release velocity against stability, yet can never justify bypassing security or data-residency obligations.

### 10.2. Assumption/Risk/Debt Governance Metrics

- **Assumptions:** count of high-impact assumptions lacking evidence; assumption age; on-time verification rate before decision milestones; count of invalidated assumptions forcing rework.
- **Risks:** count of high risks without mitigation plans; open duration; residual risk after drills; count of threshold-breaching risks lacking owner sign-off.
- **Architecture debt:** time awaiting remediation; interest manifested in incidents, deployment duration, or cost; share of ops spend caused by structural limits; share of debt items with clear triggers and owners.
- **Traceability:** critical ADRs linked to requirements, diagrams, assumptions, test evidence, and runbooks; stale docs out of sync after production changes.

Closed tickets alone **do not prove architectural quality improved**. Closing D-01 simply because a read replica was added while checkout remains slow due to another lock-contention hotspot leaves the real problem unsolved.

## 11. Establishing a Governance Cycle Across Changes and Time

Managing assumptions, risks, and debt should not happen only during initial design.

### 11.1. A Suggested Operating Cycle

~~~mermaid
flowchart LR
    A["Collect: architecture reviews, incidents, telemetry"] --> B["Classify: assumption / risk / issue / debt"]
    B --> C["Owner + impact + due date + ADR/diagram links"]
    C --> D["Validate or execute remediation"]
    D --> E["Measure outcomes and residual risk"]
    E --> F{"Goals or assumptions changed?"}
    F -- "Yes" --> G["Update ADRs, diagrams, and plans"]
    G --> A
    F -- "No" --> H["Monitor triggers and review date"]
    H --> A
~~~

In every cycle, owners must distinguish **approved decisions**, **work in progress**, **unverified assumptions**, and **accepted risks**.

### 11.2. Events That Trigger a Review

- Launching new markets/channels, traffic shifts, new tenant tiers, or new data regions.
- Changes in contractual obligations, security policies, or data classifications.
- Cloud spend exceeding forecast, pricing changes, or adopting new managed services.
- Missed SLOs, failed DR drills, major incidents, or data-integrity errors.
- Major API/DB/network changes, region migrations, multi-AZ/multi-region shifts, or service splits.
- Provider changes to service limits, support lifecycles, or operational policies.

### 11.3. Ownership and Sign-Off

| Role | Responsibility |
| --- | --- |
| **Product/Business owner** | Confirms impact on users, revenue, deadlines, and approves business trade-offs within authority |
| **Architecture/Tech lead** | Maintains ADRs, dependency maps, assumptions, and structural debt; proposes options |
| **SRE/Platform** | Proves SLOs, RTO/RPO, operability, observability, and DR drills |
| **Security/Legal** | Confirms security, data, and compliance conditions; decides within authority |
| **Finance/FinOps** | Verifies cost models, budgets, forecasts, and actual spend |
| **Risk/Steering owner** | Resolves cross-department conflicts and approves residual risk per policy |

The person who surfaces a risk does not necessarily hold authority to **accept** it. Threshold-exceeding risks require a clear escalation path and decision deadline.

## 12. End-to-End Case Study: Booking App Expanding to New Markets

### 12.1. Context

A cloud booking application currently runs:

- API and workers in one region across multiple availability zones.
- One primary database serving both Booking and Reporting, with daily backups.
- An external payment API.
- A small operations team that has never drilled failing over to another region.

Business plans add enterprise customers and high-traffic campaigns. Proposed targets (**illustrative** values) include: checkout p95 under **400 ms** in the agreed load scenario, **RTO ≤ 60 minutes**, **RPO ≤ 15 minutes**, and cloud spend within approved budget. Security requires verifying data and backup residency regions prior to expansion.

### 12.2. Analysis

| ID | Statement | Relationships | Next actions |
| --- | --- | --- | --- |
| A-11 | Peak load does not exceed 800 requests/second | Affects capacity and cost | Load test with representative read/write mix |
| A-12 | A standby region is permitted to store replicas | Mandatory condition needing proof | Security/Legal confirmation before creating resources |
| A-13 | Ops team can recover within 60 minutes | Linked to RTO | Tabletop and live DR drill |
| R-11 | Reporting overloads DB during peak campaigns, slowing checkout | Depends on A-11 and D-11 | Quotas, offload read workloads, measure p95 |
| R-12 | Untested backup/replica restores may breach RTO/RPO | Depends on A-13 | Run drill and record actual timings |
| R-13 | Payment timeouts create uncertain states; retries cause double charges | External dependency | Idempotency, status lookup, reconciliation |
| D-11 | Booking and Reporting share DB/schema | Interest: p95 and release coupling | Phased extraction of read model |
| D-12 | Standby infrastructure lacks IaC | Interest: slow restore, config drift | IaC templates, pipeline, and runbooks |

The team **cannot yet commit** to RTO/RPO targets merely because backups or multiple AZs exist. If A-12 is invalidated, the proposed multi-region option must change; never move data into an unapproved region.

### 12.3. Options and Trade-Offs

| Option | Reliability / data | Cost and operations | Remaining risks / debt |
| --- | --- | --- | --- |
| **P1: Keep multi-AZ, improve backups and DB** | Reasonable for AZ faults; does not solve full-region loss | Fewer changes; likely lower cost | R-12 on region loss; D-11 may persist |
| **P2: Warm standby in approved region + IaC/DR** | Can meet recovery targets if replication/runbooks pass drills | Adds replication, standby cost, cross-region ops | A-12 must be confirmed; R-12 needs drill; data lag possible |
| **P3: Multi-region active-active** | Can minimize disruption in certain scenarios | Complex routing, consistency, high ops and cost | Split-brain, write conflicts, data residency, shared blast radius |

There is not enough evidence yet to declare any option **compliant**. The team should verify A-12 and A-13, build a cost model, load test, and simulate region-loss recovery. Only then should they approve the ADR, record residual risk, and define rollback conditions. If no option fits both budget and RTO/RPO, escalate to decision-makers authorized to adjust scope, budget, or targets.

### 12.4. Milestone-Based Action Plan

| Milestone | Required deliverable | Owner |
| --- | --- | --- |
| Before choosing standby region | Written confirmation of data residency and data classification | Security/Legal |
| Before locking capacity | Load test, p95/p99, error rate, saturation, and cost forecast | SRE + Backend |
| Before committing RTO/RPO | Loss-of-region, restore, and data-reconciliation drill results | SRE + Data |
| Before launching campaign | Payment idempotency, retry, late-callback, and fault-injection tests | Payment |
| During first month in production | Compare A-11 against actual traffic and spend; track R-11/D-11 | Product + SRE |
| When D-11 trigger fires | Extract read model or adjust queries/DB per updated ADR | Data + Architecture |

This plan reduces major uncertainty **before** making customer commitments, while monitoring deferred debt through concrete metrics.

## 13. Minimum Viable Record Templates

A lightweight, maintainable documentation setup uses simple tables or existing tracking tools. You do not need a heavy governance platform just to track a few dozen items; what matters is clear ownership and traceability.

### 13.1. Assumption Record Template

~~~yaml
id: A-11
title: "Peak load does not exceed 800 req/s"
scope: "Booking API, first 3 months post-launch"
owner: "SRE lead"
confidence: medium
evidence: "Product forecast and benchmark data"
if_false: "Must adjust API/DB capacity and cost model"
validation:
  method: "Load test + production telemetry"
  due: "Before finalizing capacity design"
  success_criteria: "Approved load scenario passes"
links:
  - REQ-PERF-01
  - R-11
  - ADR-014
status: validating
~~~

This is an **illustrative documentation template**, not a required repository config schema. Success criteria must be concrete in practice—for instance, throughput, p95, test duration, and dataset conditions.

### 13.2. Risk Record Template

~~~yaml
id: R-12
title: "Miss RTO/RPO when primary region fails"
cause: "Restore/failover not drilled and replica lag unverified"
event: "Region outage or backups fail to restore within deadline"
consequence: "Service outage exceeds SLA or data is lost"
owner: "SRE lead"
likelihood: "Needs evaluation via drill"
impact: high
response: "Run DR drill, verify backups, IaC, and runbooks"
evidence: "TEST-DR-05"
residual_risk: "Pending drill results"
acceptance_owner: "Business/SRE per approval workflow"
trigger: "DR test fails, SLO breached, or region changes"
links:
  - A-13
  - D-12
  - ADR-014
status: open
~~~

### 13.3. Debt Record Template

~~~yaml
id: D-11
title: "Reporting and Booking share primary DB"
owner: "Data lead"
origin: "ADR-005 - launch timeline constraint"
impact:
  reliability: "Report queries can spike checkout p95"
  delivery: "Migrations couple release schedules of two teams"
evidence:
  - "Checkout p95 and DB saturation dashboards"
candidate_remediation:
  - "Dedicated read model for Reporting"
  - "Separate batch processing from transactional path"
estimate: "Spike needed to size"
trigger: "Reports cause SLO breach or release coupling"
review_date: "Next architecture review cycle"
links:
  - R-11
  - ADR-005
status: tracked
~~~

**Documentation quality rule:** without **owner, evidence, and action/trigger**, a record is just a note. Good templates support decisions; they do not replace cross-team communication.

## 14. Common Mistakes

| Mistake | Consequence | Remediation |
| --- | --- | --- |
| Treating assumptions as architectural facts | Wrong region/capacity chosen with unknown rationale | Log assumption ID, confidence, and validation due date |
| Diagrams missing as-is/to-be status | Teams build against unimplemented designs | Add version, owner, date, scope, and ADR links |
| Scoring risk with one number then closing it | Residual risk and control evidence stay unknown | Record cause, consequence, mitigation, owner, and test |
| Equating having backups with meeting DR | Misses RTO/RPO during real outages | Drill restore/failover and reconcile data |
| Using priority scores to skip compliance | Violates mandatory requirements | Verify and enforce constraints before scoring |
| Labeling every monolith as debt | Premature service splitting increases ops burden | Assess real impact and change requirements |
| Marking every risk "accepted" | No accountability and no thresholds | Only authorized owners may accept time-boxed risks |
| Turning debt register into a wish list | No basis for prioritization | Measure interest, principal, triggers, and owners |
| Writing ADRs without assumptions | Unclear when a decision must be revisited | Link assumptions/risks/debt/tests and review triggers |
| Updating docs only for audits | Diagrams and runbooks drift from production | Trigger updates on incidents, deploys, and major changes |
| Assuming all risks are independent | Underestimates shared region/account/control-plane faults | Analyze dependencies, common-cause failures, blast radius |
| Tracking only closed-ticket counts | Masks real remaining risk | Track SLOs, DR results, data errors, cost, and residual risk |

## 15. Practice Exercise

A cloud SaaS booking application running in a single region plans to scale traffic 5x and serve enterprise customers in a new region. Product wants to launch in eight weeks; SRE requires one-hour recovery; Finance requests monthly costs not increase by more than 30%; Security requires proof that sensitive data is stored/replicated only within approved boundaries. Currently Booking and Reporting share one DB and lack full distributed tracing.

**Tasks:**

1. Write **five assumptions** with source, confidence level, impact if false, owner, and test. Indicate which assumptions must be verified before picking a region.
2. Build a **risk register with at least five items** using cause → event → consequence, including likelihood/impact and mitigations.
3. Identify **three architecture debt items** with real impact; state principal, interest, telemetry/evidence, and payoff triggers.
4. Draw an **as-is deployment diagram** showing apps, DB, networking, backups, and external partners; annotate assumption/risk/debt IDs onto relevant components.
5. Propose **two to-be options** differing in availability, data, and TCO; highlight unverified limitations.
6. Write an **ADR** stating a conditional decision, key assumptions, residual risks, verification plan, and review triggers.
7. Design **three tests with acceptance criteria**: load test, restore/failover, and data-flow security check. Specify who signs off on results.
8. Plan **the next review cycle**, anchored to SLO, cost, data, and debt-remediation thresholds.

**Self-assessment hint:** a quality response does not aim to fill the most forms; it clearly distinguishes what is known, what remains uncertain, how requirements are affected, who holds decision authority, what evidence must be gathered, and what concrete actions precede launch.

## 16. Design Review Checklist

- [ ] Every major decision has an ADR, owner, alternatives, and rationale.
- [ ] Diagrams carry dates, scope, as-is/to-be status, and requirement links.
- [ ] High-impact assumptions have IDs, sources, confidence levels, verification methods, and due dates.
- [ ] Invalidated assumptions trace back to affected ADRs, diagrams, tests, and risks.
- [ ] Risk register captures cause, event, consequence, owner, mitigation, and residual risk.
- [ ] No mandatory compliance risk is arbitrarily accepted or missing formal approval.
- [ ] Shared failure modes across regions/AZs, dependencies, IAM, data, and control planes are evaluated.
- [ ] Debt register records interest, principal, evidence, triggers, and remediation options.
- [ ] Appropriate SLIs/SLOs, capacity tests, fault injection, backup validation, and DR drills exist.
- [ ] Cost model includes compute, data, networking, egress, replication, observability, and operations.
- [ ] Approvers and a review schedule based on time or major changes are defined.
- [ ] Production changes update related diagrams, runbooks, ADRs, and risk registers.

## Key Takeaways

An **assumption** is something requiring verification; a **risk** is an event that may cause harm; **architecture debt** is accumulated cost or friction from design structure. They are closely linked, yet each must be recorded, prioritized, and handled according to its nature.

A cloud architecture remains operable and evolvable long term when successors can trace **requirements → assumptions → decisions/ADRs → diagrams → tests → residual risks → debt remediation plans**. The value of this practice lies in data-backed decisions across **reliability, security, scalability, cost, and operations**—not in the number of forms filled out.
