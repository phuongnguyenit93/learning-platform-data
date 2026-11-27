# Recording Architectural Decisions with ADRs: Context, Options, and Consequences

An architecture diagram shows **how a system is organized**: which components call which, where data flows, and which zones host networking and compute. Yet looking at a diagram alone, a newcomer to the project rarely knows **why** the team chose a managed database over self-managed, **why** they deployed in a single region, or **why** notifications run through a queue.

An **Architecture Decision Record (ADR)** is a short, versioned document that captures **one significant architectural decision**, the context behind it, the options considered, the rationale for the choice, and the accepted consequences. ADRs make decisions explainable, debatable, verifiable, and revisitable when assumptions change. They do not replace detailed design documents, diagrams, runbooks, or configuration docs; rather, they connect them with **the reasoning behind the decision**.

In a cloud architecture design module, ADRs are especially valuable because decisions around **networking, compute, data, and deployment models** always involve trade-offs across **reliability, security, performance, scalability, cost, and operations**. Well-Architected practice encourages evaluating those trade-offs with evidence rather than product names or personal preference.

After this lesson, you will be able to:

- Distinguish an ADR from architecture diagrams, design docs, implementation tickets, and changelogs.
- Determine **when a decision needs an ADR**, what scope is sufficient, and who should participate.
- Write a self-contained ADR with **context, decision drivers, options, decision, and consequences**.
- Record non-functional requirements, assumptions, evidence, and verification criteria for cloud decisions.
- Manage the ADR lifecycle from proposed to accepted, superseded, or deprecated.
- Read and critique an ADR from a Well-Architected perspective.

## 1. What Problem Does an ADR Solve?

Imagine a team building a booking application. In month one, the team picks a managed relational database because they need transactions and want to minimize operational overhead. Six months later, a new team member sees that database on the diagram without knowing why. They propose migrating to NoSQL because "it scales more easily". Without an ADR, the team has to dig through old meetings, chat logs, and people's memories.

A good ADR lets readers understand:

1. **At the time of the decision, what problem had to be solved?**
2. **Which requirements and constraints truly governed the choice?**
3. **Which options did the team consider, and why were they not chosen?**
4. **Which solution was chosen and within what scope?**
5. **What benefits, costs, risks, and follow-up work did the team accept?**
6. **Under what conditions must the decision be revisited?**

ADRs also establish **traceability** from business goals to concrete implementation. For example: "no double-booked time slots" → "must guarantee consistency at write time" → "choose a database supporting transactions and suitable constraints" → "test concurrent booking requests".

### What Documents Is an ADR Not?

| Document | Core question answered | Relationship to ADR |
| --- | --- | --- |
| **Architecture diagram** | What components and connections make up the system? | ADRs explain the choices shown on the diagram |
| **Design doc / RFC** | How is the overall solution analyzed, aligned on, and implemented? | One RFC may spawn multiple ADRs, each capturing one decision |
| **ADR** | Why was this option chosen over alternatives? | Records decision, rationale, trade-offs, and review triggers |
| **Ticket / backlog item** | Who does what, and when? | Executes one or more consequences/actions from an ADR |
| **Runbook** | What to do during deployment, operations, or incidents? | Operationalizes the practices committed to in an ADR |
| **Architecture review / Well-Architected report** | Where are the risks and areas for improvement? | May trigger a new ADR or require revisiting an older ADR |
| **Changelog / release note** | What changed in a release? | Announces changes without necessarily capturing long-term rationale |

Do not put an entire multi-dozen-page design doc into one ADR. An ADR should be **self-contained enough to understand the decision**, while linking out to diagrams, PoCs, load-test results, cost estimates, and runbooks when needed.

## 2. When Should You Write an ADR?

A change deserves an ADR when it **significantly impacts architecture or is hard to reverse**, has **multiple plausible options**, or involves **long-term risk, ownership, or cost**.

Examples that usually deserve an ADR:

- Choosing **single-region, multi-AZ, or multi-region** topology and target RTO/RPO.
- Choosing **managed relational database, NoSQL, or self-managed database**.
- Choosing **VMs, managed container platform, Kubernetes, PaaS, or serverless** for a workload.
- Choosing **synchronous calls vs. an event queue** for a business flow.
- Deciding **account separation, network boundaries, private connectivity, and identity management**.
- Adopting a **provider-specific proprietary service** and identifying switching risks.
- Choosing **encryption, key management, backup, and recovery** strategies with major impact.
- Moving from a **modular monolith** to microservices or changing data ownership.

Examples that usually **do not need a separate ADR**: temporarily scaling up an instance size during an approved load test, fixing resource tags, renaming internal variables, or tuning alert thresholds under an established procedure. If such changes alter SLO commitments, major cost baselines, or the security model, they can still become decisions warranting an ADR.

### One Decision, One ADR

A practical test is whether the ADR can be summarized in **one decision statement**:

> Use managed PostgreSQL for booking data because consistent transactions are required and the operations team is small; verify performance, recovery, and cost before production.

If a document is simultaneously deciding database, queue, Kubernetes, multi-region, and identity model, split it into multiple linked ADRs. Each decision has distinct drivers, consequences, change timelines, and owners.

Conversely, do not over-split to the point where every minor setting gets its own ADR. The goal is to capture **decisions that outlive a single deployment**, not to log every operational tweak.

## 3. Core Structure of an ADR

There is no single mandatory template. The template below intentionally keeps core fields readable while adding fields that help verify cloud decisions.

| Section | What to record | Self-check question |
| --- | --- | --- |
| **ID, title, date, status** | Stable identifier, decision statement, current status | Can readers find the decision and tell whether it still applies? |
| **Context** | Problem, current state, business requirements, constraints, and decision actors | Why does the team have to decide right now? |
| **Decision drivers** | NFRs, risks, budget, timeline, skills, compliance, priority order | By what criteria are options compared? |
| **Options considered** | Viable alternatives, including keeping the status quo when appropriate | Did the team avoid biased comparisons? |
| **Decision** | Chosen option, scope of applicability, and conditions | Who must implement what? |
| **Rationale** | Why this option satisfies the criteria best in the current context | If conditions change, can it be re-evaluated? |
| **Consequences** | Benefits, trade-offs, residual risks, operational impact, and follow-up work | Are downsides, ownership, and costs explicitly listed? |
| **Validation / evidence** | PoC, benchmarks, threat model, restore drills, cost estimates, measurements | Is there a way to prove the decision meets requirements? |
| **Review triggers** | Events/thresholds that require reviewing the ADR | When might this decision stop fitting? |
| **References** | Diagrams, requirements, test artifacts, related ADRs | Can future readers re-verify the facts? |

### 3.1. Context Is Not a Product Pitch

Context must describe **the problem and relevant facts**, without pre-writing the conclusion.

Insufficient:

> We need to use Kubernetes because it is the modern standard.

More useful:

> The engineering team has six developers and needs to operate two Java APIs and one worker. Load has not been fully measured yet; target launch is in eight weeks, requiring continuous deployment and recovery if an instance fails. The team currently has no engineer dedicated to cluster administration.

Good context helps readers immediately see the trade-off axes: delivery speed, availability, operational effort, and scalability.

### 3.2. Separate Requirements, Assumptions, and Constraints

Distinguish three kinds of facts:

- **Confirmed requirements:** e.g., customer data must be stored in an approved region under contract.
- **Assumptions to verify:** e.g., peak traffic will not exceed 300 requests/second during the first six months.
- **Real-world constraints:** e.g., capped operations budget or team lacking Kubernetes orchestration skills.

Whenever you cite a number, state its **source**, **measurement method**, or mark it as an **illustrative assumption**. Saying "needs to be fast" is not enough to choose compute; "read API p95 under 300 ms at target load" yields a testable criterion.

### 3.3. Write Decisions as Clear, Scoped Statements

A good decision states:

- **What is chosen:** concrete service class or model.
- **Where it applies:** workload, environment, region, and data path.
- **What is left undecided:** issues deferred to separate ADRs or experiments.
- **Mandatory conditions:** security, reliability, data, cost, and required tests to pass.

Avoid "we should consider using a managed database". If undecided, set status to **Proposed**, list the options, and state the open questions.

## 4. Process for Making Decisions and Writing ADRs

An ADR is most valuable when created **close to the decision point**, before full switching costs are incurred. The process can happen in a brief review session, provided the right information and owners are present.

~~~mermaid
flowchart TD
    N["Identify decision needed"] --> C["Record context, requirements, and assumptions"]
    C --> O["Propose viable options"]
    O --> E["Compare trade-offs and gather evidence"]
    E --> P["ADR in Proposed status"]
    P --> R{"Enough evidence in review?"}
    R -- "No" --> X["PoC, load measurement, threat model, cost estimate"]
    X --> E
    R -- "Yes" --> A["Accept decision and assign work"]
    A --> V["Implement, measure, and link evidence"]
    V --> T{"Assumptions or requirements changed?"}
    T -- "No" --> V
    T -- "Yes" --> S["Review and create superseding ADR if needed"]
~~~

**Step 1 — Pin down the decision question.** Example: "Which data store should hold booking data with anti-double-booking guarantees?" A narrow question prevents debates from sprawling across the entire platform.

**Step 2 — Record context and affected stakeholders.** Cross-check requirements from product, SRE, security, data, and finance where relevant; separate current facts from forecasts.

**Step 3 — Propose plausible options.** List at least the options capable of meeting the goal, including keeping the status quo if viable. Avoid inventing artificially weak strawman options just to highlight a preferred choice.

**Step 4 — Compare against agreed criteria.** Assess reliability, security, time to launch, performance, cost, operations, data, vendor lock-in, and reversibility. Weight each criterion according to business priorities.

**Step 5 — Gather evidence on high-risk areas.** PoC, load test, restore drill, permission model, failover test, log-delivery check, or cost estimate based on concrete configuration/load. Never cite "provider supports HA" alone as proof that RTO is met.

**Step 6 — Decide, record consequences, and define verification.** The authorized owner accepts or rejects; create tickets for required work and select verification metrics.

**Step 7 — Preserve history.** When things change, link the new ADR to the old ADR and keep the original rationale intact so future readers understand how the design evolved.

### Who Owns What?

| Role | Responsibility in the ADR |
| --- | --- |
| **Proposer / Author** | Documents context, options, evidence, and draft content |
| **Decision owner / Approver** | Accepts trade-offs and makes the decision within delegated authority |
| **Reviewers** | Check correctness and consequences across security, reliability, data, cost, and operability |
| **Implementers** | Build changes and run tests per the decision; flag when assumptions fail |
| **Architecture maintainer** | Keeps links, statuses, and review cadence up to date |

A small team may have one person wear multiple hats, yet it must remain clear **who has authority to accept risk**. A reviewer pointing out a security risk does not make the reviewer responsible for accepting that risk if the business chooses to proceed.

## 5. Complete ADR Example: Choosing a Database for a Booking Service

**Hypothetical scenario:** A team is building a medical consultation booking app in the cloud. The app must prevent two patients from booking the same doctor in the same fixed time slot. There are six engineers, with one sharing operational duties. The system is expected to grow, though long-term traffic data does not exist yet.

The figures below are **illustrative data for this lesson only**, not cloud service SLAs:

| Condition | Assumed value | Implication |
| --- | --- | --- |
| Peak forecast | 250 requests/second app-wide, 20 booking requests/second | Must load-test realistic read/write mix and concurrent contention |
| Correctness | Never two successful bookings for the same doctor + slot | Requires data constraints at write time |
| SLO | 99.9% of valid booking transactions succeed over 30 days | Needs SLIs, dependency error handling, and monitoring |
| RTO | Maximum 60 minutes | Must drill recovery under failure scenarios |
| RPO | Maximum 15 minutes | Backup/replication and recovery capability must be measured |
| Budget | Limited staffing and operational budget | Prefer reducing self-managed toil where beneficial |
| Changeability | Traffic may double during promotions | Needs scaling mechanisms and bottleneck evaluation |

### ADR-007 — Select a Managed Relational Database for Booking Transactions

> **ID:** ADR-007  
> **Status:** Accepted  
> **Accepted Date:** 2026-11-18 (illustrative)  
> **Owner:** Booking Team  
> **Scope:** Appointment data in Booking Service, production environment  
> **Related:** Booking data diagram, SLO/RTO/RPO requirements, load and recovery test plans

#### Context

Booking Service must store booking transactions so that **no two transactions occupy the same defined time slot**. Appointment data links customers, doctors, statuses, and change history. The operations team is small and lacks capacity for 24/7 on-call maintenance of a self-managed database cluster. The system must recover from instance failures or data incidents.

We need a data store with appropriate transactions that preserves correctness under concurrent requests, supports backup/restore, and keeps total operational cost acceptable.

#### Decision Drivers

1. **Top priority:** preserve booking transaction correctness even when the API retries requests or multiple requests contend.
2. **Reliability:** the solution needs an HA design, backups, and a recovery plan drilled against agreed RTO/RPO.
3. **Operability:** reduce OS management, patching, failover, and backup burden given current team size.
4. **Performance:** meet projected load based on testing, monitoring p95/p99, connection capacity, and lock contention.
5. **Cost:** review service pricing by configuration, storage/IOPS, backups, networking, monitoring, and staffing.
6. **Portability:** data can be exported, schemas and extensions are inventoried, and restore procedures are tested.

#### Options Considered

| Option | Key benefits | Costs/risks | Assessment in context |
| --- | --- | --- | --- |
| **A. Transaction-capable managed relational database** | Reduces self-management, offers configurable backup/HA options; fits relational data | Depends on service and quotas; still needs HA/DR design, failover tests, baseline cost | **Selected**, subject to verification |
| **B. Self-managed PostgreSQL on VMs** | Deep configuration control, flexible extensions and versions | Team owns patching, backups, replication, failover, monitoring, and incident on-call | Poor fit for current operational capacity |
| **C. Managed NoSQL document/key-value** | Can fit simple access patterns and key-based scaling | Requires redesigning transactions, uniqueness, relations, and queries; semantics vary across services | No clear benefit justifying added data complexity |

This comparison does not claim NoSQL lacks transactions or that VMs are unreliable. Actual features, limits, and reliability depend on the specific technology and implementation; the assessment here is tied to **the stated requirements and team capacity**.

#### Decision

Use a **PostgreSQL-compatible managed relational database** for booking data in Booking Service. Configure database transactions and unique constraints matching the time-slot model, deploy with the chosen HA configuration, and establish backups and recovery procedures. Before production, fully validate via load testing, concurrent transaction contention tests, and restore drills.

For schedules divided into **fixed time slots**, a natural key might be **(doctor_id, slot_start)**. For appointments with **variable durations that may overlap**, a simple unique constraint is insufficient; an exclusion constraint against overlapping ranges or appropriate transactional synchronization must be designed. Correctness rules must be tested independently of API instance count.

#### Rationale

Option A matches the product's relational and transactional model while reducing database operations work compared to B. Option C shows no needed advantage for this problem while adding design and testing effort for consistency rules. The team accepts managed service costs and provider dependency in order to prioritize **correctness and operability**.

#### Positive Consequences

- The domain can model relationships, constraints, and transactions cleanly.
- Reduces the database infrastructure administration the team must maintain directly.
- Enables deploying backups/HA via the chosen service when configuration and testing meet requirements.
- Straightforward to run queries across appointments and states in the current data model.

#### Negative Consequences and Residual Risks

- Baseline, storage/IOPS, backup, and data-transfer costs may exceed forecasts and require budget monitoring.
- The database still has connection, resource, and quota limits; scaling out API instances can overload the database.
- Failover may drop active connections or fail in-flight transactions; the application needs timeouts, safe retries, and idempotency.
- The team still owns schemas, queries, indexes, migrations, data permissions, encryption, secrets, and backup quality.
- Dependency on versions, extensions, HA mechanics, and managed-service specifics can increase future cloud migration cost.
- Having backups or replication does not by itself prove a 15-minute RPO or 60-minute RTO; drills are required to measure them.

#### Required Actions and Verification Tests

| Action | Owner | Acceptance evidence |
| --- | --- | --- |
| Design constraints and transactions preventing double booking | Backend / Data | Same-slot concurrency test: only one valid booking succeeds |
| Test idempotency and retries on connection failures | Backend | A retried request creates no extra appointment or unintended side effects |
| Configure connection limits and load test | Backend / Platform | p95, error rate, connection pool metrics, and ability to sustain assumed 250 RPS |
| Configure backups and run restore drill | Platform / DBA | Measured recovery duration and data loss compared against RTO/RPO |
| Validate IAM, TLS, encryption, and network access | Security / Platform | Allow/deny tests, permission inventory, and audit logs |
| Build dashboards and alerts | SRE / Platform | Metrics covering transaction errors, latency, storage, backups, and connections |
| Estimate costs at baseline and peak load | Platform / Finance | Configuration report, usage estimates, cost risks, and budget alert thresholds |
| Test data export/import portability | Backend / Platform | Reconcile test dataset in an independent environment |

#### Review Triggers

- Actual write load or contention exceeds accepted thresholds.
- SLO/RTO/RPO can no longer be met despite tuning within the design scope.
- Data requirements, residency rules, new features, or provider contracts change.
- Service costs exceed approved thresholds even after optimization options.
- A new data model must be integrated that the current design cannot reasonably support.

#### Explicitly Undecided

This ADR **does not select a specific cloud provider**, nor does it finalize region, instance size, IOPS tier, connection pool configuration, or multi-region DR strategy. Those details must be settled through deployment design, benchmarks, and separate ADRs if architecturally significant.

### Takeaways from the Example

Reading ADR-007, a newcomer understands **why** the database appears on the diagram, which alternatives were weighed, and what must be measured before claiming the architecture meets its SLO. They also see that **Accepted** does not mean all tests are already done; production readiness conditions may remain active work items.

An ADR must never serve as evidence in place of testing. Saying "chose HA database to achieve a 60-minute RTO" is only a **design target** until failover/restore measurements exist.

## 6. Reusable Markdown ADR Template for Projects

A team can agree on file naming, template, and storage location. The template below is short enough that decision-makers actually write it, and concrete enough for reviewers to evaluate:

~~~markdown
# ADR-<ID>: <One-sentence decision statement>

- Status: Proposed | Accepted | Rejected | Superseded | Deprecated
- Date: YYYY-MM-DD
- Proposer:
- Decision Owner:
- Scope: workload, environment, region, or applicable components
- Related / Supersedes:

## Context

What problem are we solving?
Current state, business requirements, constraints, and assumptions to verify?
Source of SLO, RTO/RPO, load, budget, and compliance rules?

## Decision Drivers

- Driver 1 (priority, source):
- Driver 2 (priority, source):
- ...

## Options Considered

### Option A
- Pros:
- Cons and risks:

### Option B
- Pros:
- Cons and risks:

## Decision

Choose option ... for scope ...
Conditions / exceptions ...

## Rationale

Why does the chosen option satisfy the drivers better?
Which critical assumptions lead to this conclusion?

## Consequences

- Positive:
- Negative / trade-offs:
- Residual risks:
- Cost and operational responsibilities:

## Validation / Follow-up Work

- Tests / measurements / acceptance criteria:
- Owner / due date / ticket links:

## Review Triggers

- Triggers for changing requirements, data, cost, load, or risk:

## References

- Diagrams:
- PoC / benchmarks / threat model:
- Business requirements / SLO / contracts:
~~~

**Note:** Status labels are a team convention. Some organizations use only Proposed, Accepted, and Superseded; others add Rejected or Deprecated. What matters is **defining statuses clearly** and never conflating "decision approved" with "feature deployed".

### Example Directory Structure

~~~text
docs/
  architecture/
    overview.md
    booking-deployment.mmd
    decisions/
      0001-use-managed-relational-database.md
      0002-asynchronous-notifications.md
      0003-multi-az-deployment.md
    reviews/
      booking-well-architected-2026-11.md
~~~

This is an **illustrative convention only**, not a requirement to create these files for this lesson. Each ADR should have a **stable ID**, searchable title, and entry in a decision index. Choose a naming scheme the team can sustain long term.

## 7. Managing the ADR Lifecycle as Architecture Evolves

A cloud system constantly changes in load, configuration, regulations, and staffing. ADRs must help readers **know when a decision is still valid** and **trace why changes occurred**.

| Status | Practical meaning | Next action |
| --- | --- | --- |
| **Proposed** | Gathering feedback or validating, not yet finalized | Review, PoC, clarify risks and decision owner |
| **Accepted** | Decision approved within the documented scope | Create implementation tasks and track results |
| **Rejected** | Option/proposal was not approved | Keep rationale to avoid repeating ungrounded debates |
| **Superseded** | Decision replaced by a newer ADR | Link to new ADR; preserve old rationale and history |
| **Deprecated** | No longer recommended for new changes; existing usage managed | State sunset plan or removal conditions |

Statuses can be streamlined to fit real workflows. Never mark an ADR **Accepted** merely because the Markdown PR merged; the authorized decision owner must genuinely approve the content and consequences.

### Why Not Silently Rewrite Old ADRs?

Suppose ADR-007 chose a relational database. A year later, traffic and data models shift, and the team chooses sharding or a different database. If you simply edit ADR-007 to match the new architecture, the history of "why did we pick that originally?" vanishes.

Instead:

1. Write a new ADR with the **new context and data**, such as ADR-021.
2. Explicitly note **Supersedes ADR-007** and explain what made the old decision no longer fit.
3. Update ADR-007's status to **Superseded by ADR-021**.
4. Link migration plans, tests, and diagrams reflecting the new decision.
5. Keep ADR-007 so readers see how the earlier choice made sense at that time.

You can fix typos or add links to verification evidence in an old ADR without changing the decision's substance; use version history for transparency. Whenever the **meaning of a decision** changes, a new ADR is clearer.

### ADRs Reflect Decisions; Configuration Reflects Current Reality

These two sources of truth are not interchangeable:

- An ADR states **what was approved and why**.
- Reconciled IaC, configuration, and deployment diagrams state **what is actually running**.

For example, an ADR states multi-AZ deployment, yet the live configuration has one instance in one zone. That is **drift to remediate**, not proof the architecture is complete. Reviews should include reconciling ADRs against IaC, service inventories, SLOs, and test results.

## 8. Comparing Options Without False Precision

When choosing among cloud architectures, a clear trade-off table is far more useful than an unsubstantiated claim that "Option A is better".

Example: choosing where to run two Java APIs and one worker for a small team:

| Criterion | Self-managed VMs | Managed container platform | Self-managed / deeply managed Kubernetes |
| --- | --- | --- | --- |
| Time to launch | Depends on VM automation and patching pipelines | Typically fast if the runtime is supported | Requires configuring clusters, networking, security, and operations |
| Level of control | High at OS/runtime level | Less low-level infrastructure control | High for workload scheduling and ecosystem |
| Operational effort | Team owns OS, scaling, and much of HA | Platform handles much underlying infrastructure | Requires cluster, networking, upgrade, and observability skills |
| Flexibility | Runs specialized workloads needing OS control | Fits stateless workloads and multiple workers | Useful for many complex workloads / larger teams |
| Platform dependencies | VM images, networks, IAM, scripts | Deployment APIs and managed services | Still depends on cloud, clusters, add-ons, and storage |
| Cost | Compute + admin + standby | Compute + service fees + usage + app ops | Nodes/control plane/add-ons + operations staffing |

You cannot conclude one universal winner for every organization from a qualitative table alone. If load tests, budgets, or team experience are missing, the ADR must flag **insufficient evidence** and specify the tests to run.

### When Is Weighted Scoring Useful?

A scoring matrix helps only when grounded in **measurable criteria or pre-agreed scoring rules**. For example, the team confirms operational simplicity and launching in eight weeks outweigh low-level infrastructure control. Relative weights can be assigned per decision, provided you:

- State the rationale for weights, data sources, and scoring method openly.
- Never let a weighted score override **mandatory requirements** such as compliance, data protection, or RTO limits.
- Treat small score differences as signals for deeper verification, not absolute truth.
- Run sensitivity checks: if one assumption flips, does the winning option change?

For instance, two options differing by a couple of points based on estimated costs without real unit pricing yield low-confidence conclusions. In an ADR, stating uncertainty clearly is worth far more than inventing an "exact" number you cannot explain.

## 9. Writing Consequences: The Most Commonly Skipped Part of an ADR

Many ADRs write decent context and then stop at "chose A because it fits". **Consequences** tell the team what costs and obligations they accept after choosing. This section must document **positive outcomes**, **drawbacks**, **residual risks**, and **follow-up work needed for the decision to succeed**.

Consider these prompts when writing consequences for a cloud decision:

| Well-Architected pillar | Consequences to document |
| --- | --- |
| **Operational Excellence** | Who operates, deploys, rolls back, patches, monitors, and handles incidents? Are runbooks and pipelines ready? |
| **Security** | Trust boundaries, identities, IAM, sensitive data, encryption, auditing, and areas needing threat modeling? |
| **Reliability** | Remaining failure points, HA, backups, DR, RTO/RPO, retries, and failover scenarios to test? |
| **Performance Efficiency** | Load limits, p95/p99, quotas, network latency, and where bottlenecks may appear? |
| **Cost Optimization** | Baseline cost, load-driven cost, data, egress, backups, logs, and operational effort? |
| **Sustainability** | Matching resources to demand, avoiding redundant replication and unnecessary retention? |

For example, the decision "route notifications through a queue" carries multiple consequences:

**Positive:** booking requests do not wait on the email provider; the queue absorbs traffic bursts and isolates downstream outages.

**Negative:** users may receive notifications with slight delay; requires monitoring queue age, retries, dead-letter queue, and retention limits.

**Data risks:** messages may arrive duplicated or out of order depending on the service; consumers must be idempotent, and post-transaction publishing needs a pattern like a transactional outbox if no events may be dropped.

**Follow-up work:** measure delivery latency, test email-provider outages, bound retries, and alert when the queue backs up.

These are actionable, testable consequences—far better than writing "a queue improves performance".

### Documenting Accepted Risks with an Owner

Not every risk can be fixed immediately. A team might temporarily accept single-region deployment if:

- The business owner explicitly approved the impact of a full-region outage.
- Target RTO/RPO and dependencies are clearly documented.
- Backups, a restore plan, and a review date or upgrade trigger exist.
- The risk is tracked in a risk register with a named owner.

If a decision violates mandatory requirements, never use "risk accepted" to rubber-stamp non-compliance. Scope, requirements, or design must be adjusted through an authorized governance process.

## 10. Tying ADRs to Diagrams, Measurements, and Deployment

ADRs must link to evidence. An illustrative Mermaid diagram for the booking app:

~~~mermaid
flowchart TD
    USER["Customer"] --> API["Booking API<br/>Container instances"]
    API --> DB[("Managed relational DB<br/>Transactions / constraints")]
    API --> OUTBOX["Outbox events"]
    OUTBOX --> RELAY["Event relay"]
    RELAY --> Q["Managed queue"]
    Q --> WORKER["Notification worker"]
    WORKER --> MAIL["Email/SMS provider"]
    API --> OBS["Logs, metrics, traces"]
    WORKER --> OBS
~~~

The diagram answers "where does the flow run?", yet does not explain:

- Why does the API run in containers instead of VMs or functions?
- Why is a relational database the authoritative data source?
- Why use an outbox, queue, and worker instead of calling email directly?
- Why choose one region, multiple zones, and the current backup tier?

Each significant question can map to its own ADR. For example:

| Decision | Reference ADR | Evidence to link |
| --- | --- | --- |
| Transactional database for bookings | ADR-007 | Schema/constraints, concurrency tests, restore tests |
| Asynchronous notifications | ADR-008 | Sequence flow, retry/idempotency tests, queue metrics |
| Compute for API/worker | ADR-009 | Load tests, capacity plan, cost estimate, rollback |
| HA and DR scope | ADR-010 | Region/zone diagram, RTO/RPO, failover/restore drills |
| Service authorization | ADR-011 | Data flow, IAM matrix, threat model, audit evidence |

These IDs are **linking examples**, not an assertion that corresponding files already exist in the repository.

### "Decision Traceability" in the Development Lifecycle

A clear traceability chain can look like:

~~~text
Need: prevent double-booked time slots
      ↓
ADR-007: use transactions + appropriate constraints
      ↓
Design: schema, idempotency rules, booking API
      ↓
Execution: migrations / IaC / security config
      ↓
Verification: concurrency test + load test + restore test
      ↓
Operations: metrics, alerts, runbooks, live reviews
~~~

When a test fails or a requirement shifts, traceability identifies **which decision needs adjustment**. If latency exceeds SLO, investigate queries, locks, and connection pools before concluding the database choice was wrong. If booking shifts from fixed slots to flexible intervals, revisit constraint design and related ADRs.

## 11. Common Mistakes and How to Fix Them

### Mistake 1 — Recording Only the Choice, Without Rationale

**Weak:** "Use Kubernetes."

**Better:** Explain why orchestration capabilities, operational policies, or scaling needs are required; which managed container options were compared; and whether the team has capacity to own cluster operations.

### Mistake 2 — Presenting Alternatives as Strawmen

**Weak:** "VMs are outdated and serverless is very slow, so we must use Kubernetes."

**Better:** Compare across workload, runtime, staffing, latency, quotas, cost, and supportability. Acknowledge where each option fits.

### Mistake 3 — Listing Only Positive Consequences

**Weak:** "Managed database guarantees HA, no DBA needed."

**Better:** List responsibilities still owned by the project team: schemas, permissions, backups/restores, connection pools, cost, monitoring, failover testing, and application-side incident handling.

### Mistake 4 — Using Service Features as Evidence

**Weak:** "Backups are enabled, so 15-minute RPO is guaranteed."

**Better:** Specify concrete backup/PITR settings, recovery drills, measured data loss, and time to restore service; if unmeasured, mark it as an assumption.

### Mistake 5 — Trying to Decide the Entire Architecture in One ADR

**Weak:** A 30-page document picking networking, compute, database, observability, DR, and CI/CD all at once.

**Better:** Split decisions that can change independently; connect them via a design overview or index.

### Mistake 6 — Omitting What Was Left Undecided

**Weak:** "Choose PostgreSQL", leaving readers assuming version, topology, data residency, and restore plans are all finalized.

**Better:** State scope and dependent decisions still to be made. This stops assumptions from being mistaken for settled facts.

### Mistake 7 — Editing ADRs After System Changes Without Preserving History

**Weak:** Changing an old doc from single-region to multi-region without recording why.

**Better:** Create a superseding ADR; clearly link the prior decision and new verification results.

### Mistake 8 — Writing ADRs Too Late or Purely as Paperwork

**Weak:** All resources are already deployed; the ADR is reverse-engineered from config with no memory of options considered.

**Better:** Write while preparing the decision, review with owners, and update through reviews; for legacy architectures, explicitly mark "decision reconstructed from current state" and note missing evidence.

## 12. Practice: Write an ADR for a Cloud Application Deployment Model

### Prompt

A team is building a service-booking platform with a Java backend, an availability read API, a booking write API, and a notification worker. The team has five engineers, one sharing operations duty, and aims to launch in two months. Peak load is **200 requests/second**, target read API p95 is **under 300 ms**, and SLO is **99.9% valid transactions succeeding over 30 days**. These figures are **assumptions for practice**, not yet proven by load testing.

You must decide **the compute model for the API and worker**. Three preliminary options:

- **A. VMs:** self-manage virtual machines, build images and deploy scripts, configure load balancing and autoscaling.
- **B. Managed container platform:** run stateless containers using managed orchestration and deployment pipelines.
- **C. Kubernetes:** build required control-plane components or use managed Kubernetes while the team remains responsible for workload config, add-ons, and upgrades under the chosen model.

Assume database and queue were decided in other ADRs. Focus this exercise solely on the **compute** decision.

### Required Deliverables

1. **Name the ADR:** ID, title stating the decision, Proposed status, date, proposer, and approver.
2. **Write context:** API/worker flow, load, p95, SLO, staffing, launch timeline, automation level, and unverified assumptions.
3. **Define drivers:** at least reliability, security, performance, scale, cost, and operations; distinguish mandatory requirements from trade-off criteria.
4. **Compare all three options:** state one grounded benefit and one grounded drawback for each option without claiming any technology is universally superior.
5. **Write the proposed decision:** pick one option, specify prod/non-prod scope and rationale; list conditions making the choice suitable.
6. **Document consequences:** at least two positive consequences, three negative consequences or risks, and follow-up work.
7. **Specify verification tests:** deploy a thin slice of API + worker, load-test 200 RPS and assumed peak, rolling updates, instance/zone failures, retries, and rollback capability.
8. **Define review triggers:** e.g., traffic grows 4x, product needs specialized workloads, costs exceed threshold, or the team builds new platform capabilities.

### Sample Partial Solution

**Proposed decision:** select a managed container platform for v1 because the team is small, launch timeline is tight, and API/worker are expected to package cleanly as containers. Run multiple API replicas across appropriate failure domains, and deploy workers with concurrency and queue limits. Approve production rollout only after load testing, rollback verification, and proving quality targets within approved scope.

**Positive consequences:** reduces OS and cluster administration compared to self-managed options; uses a unified packaging, release, and observability mechanism for API and worker.

**Negative consequences:** depends on platform quotas, autoscaling behavior, resource limits, regional availability, and pricing model; p95 and SLO remain unproven; must test cold start or scale-out time if applicable to the platform; application must remain stateless and manage database connections carefully.

**Review triggers:** error rate/p95 misses targets despite in-scope tuning, specialized runtime configuration needs emerge, or long-term TCO shifts materially.

This is **one illustrative option**. Learners may pick VMs or Kubernetes if they demonstrate a different context and trade-offs. Grading focuses on **rationale, evidence, consequences, and verifiability**, not matching the example's technology name.

### Self-Assessment Rubric

| Criterion | Needs work | Meets expectations | Strong |
| --- | --- | --- | --- |
| **Context** | Missing problem, constraints, and load | Includes requirements, limits, and assumptions | Includes sources, confidence, and impact of assumptions |
| **Options** | Only one choice | Real alternatives with pros/cons | Consistent trade-offs by criteria plus status quo option |
| **Decision** | Vague, unclear scope | Clear choice, scope, and conditions | Includes priority rationale, approver, and undecided items |
| **Consequences** | Lists benefits only | Lists benefits, costs, risks, and next steps | Assigns owners, priorities, and mitigations |
| **Validation** | No measurements | Includes tests and pass thresholds | Includes measurement procedure, test data, and review triggers |
| **Traceability** | No linked docs | Links related diagrams and tickets | Links evidence, deployment, SLOs, and other ADRs |

## 13. Checklist Before Accepting an ADR

- [ ] Title states **one clear decision**, not just a technology name.
- [ ] Context describes the problem, current state, and business needs rather than starting from the conclusion.
- [ ] Confirmed requirements, assumptions, and constraints are clearly separated.
- [ ] Key NFRs have measurements/thresholds or a measurement plan; RTO/RPO are not equated with provider marketing features.
- [ ] Options are viable alternatives compared against relevant criteria.
- [ ] Chosen option has clear enough scope, conditions, and rationale for another team to execute.
- [ ] Consequences include benefits, costs, residual risks, and operational/security ownership.
- [ ] Follow-up work has owners, tests, acceptance criteria, and tracking links.
- [ ] Impacts across relevant Well-Architected pillars have been examined.
- [ ] Links to diagrams, PoC results, benchmarks, threat models, cost estimates, or requirement sources where available.
- [ ] Status and approver are explicit; Accepted is never confused with deployed.
- [ ] Includes review triggers and a way to supersede the ADR while preserving history.

A good ADR does not have to be long or complex. Its value lies in clearly answering **what context led to the decision**, **why this choice beat alternatives in that context**, **which consequences were accepted**, and **what evidence lets us re-verify it**. While architecture diagrams answer "how is the system built?", ADRs preserve what is essential for intentional evolution: **"why did we choose this path?"**
