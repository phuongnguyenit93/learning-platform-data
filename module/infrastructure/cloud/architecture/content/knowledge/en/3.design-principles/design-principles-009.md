# Simplifying Architecture and Controlling Accidental Complexity

## 1. Simplification Is a Verifiable Design Principle

In cloud application design, **a good architecture is not the one with the newest or most numerous services**, but the one that meets business requirements and quality targets with a level of complexity the team can understand, change, secure, and operate sustainably.

An application composed of a few well-managed components can satisfy scalability, performance, and reliability goals. Conversely, splitting a small application into dozens of microservices, adopting multiple database engines, and deploying multi-region from day one can introduce risks the business does not yet need to solve.

However, **simplicity does not mean cutting corners**. Omitting authentication, data recovery, auditing, or duplicate-transaction handling may shrink a diagram yet make the system harder to operate and repair. True simplification means **removing components, dependencies, and processes that do not deliver sufficient value**, while retaining the controls necessary to meet requirements.

This principle runs throughout the **CLOUD_ARCHITECTURE** module: from business requirements through networking, compute, data, and deployment model choices, every added component must deliver clear value in **reliability, security, scalability, performance, cost, or operations**. Evaluation in the Well-Architected spirit examines both benefits and total maintenance cost.

After this lesson, you will be able to:

- Distinguish **essential** complexity of the problem from **accidental** complexity introduced by implementation choices.
- Recognize when microservices, queues, multiple databases, multi-region, or multi-cloud are genuinely needed.
- Evaluate the total cost of architectural decisions, including operational, security, data, and human coordination costs.
- Design a right-sized initial architecture with clear module boundaries and an evolution path as requirements change.
- Monitor complexity and decide when to remove, consolidate, or replace redundant components.

## 2. Two Sources of Complexity

### 2.1. Essential Complexity

This is the inherent difficulty that cannot be removed while keeping the same business requirements. For example, a booking platform must guarantee two guests cannot confirm the same slot simultaneously; a payment system must handle late or duplicate callbacks; a healthcare system must enforce access controls on sensitive data. These demands remain whether the app runs on a single server, containers, or serverless.

### 2.2. Accidental Complexity

This is difficulty created by design, technology, and organizational choices, such as:

- A booking flow calling through six synchronous services even though only two business domains are involved.
- The same customer state existing across four databases with no clear synchronization rules.
- Every service using a different framework, configuration style, and observability stack.
- A small feature requiring edits across three repositories, five pipelines, and multi-team sign-offs.
- Deploying across two cloud providers even though the application has no legal or business constraint requiring it.

Not all accidental complexity can be eliminated; some is a reasonable price to pay to satisfy requirements. The goal is **reducing the portion whose benefits fail to outweigh its costs**.

| Perspective | Complexity Indicator | Diagnostic Question |
| --- | --- | --- |
| **Structural** | Too many components, abstraction layers, APIs, and dependencies | How many boundaries must one small change cross? |
| **Data** | Multiple copies, events, consistency rules, and reconciliation flows | Where is the source of truth, who owns it, and how are errors fixed? |
| **Operational** | Many pipelines, environments, alerts, and recovery procedures | During an incident, who can diagnose and restore? |
| **Security** | Many machine identities, secrets, policies, and entry points | What permissions and attack surface does a new component add? |
| **Organizational** | Too many teams and handoffs, fragmented knowledge | Who owns end-to-end accountability for a user journey? |
| **Temporal** | Legacy versions, backward compatibility, data transitions | How many system generations must a contract change support? |

**Complexity does not live solely on component diagrams.** An architecture with few boxes can still have tangled source-code dependencies that are hard to modify and error-prone. Conversely, many components can still be justified when responsibilities are crisp, operations standardized, and genuine requirements exist.

## 3. Common Causes of Gradual Architectural Bloat

### 3.1. Designing for Unproven Scale

Teams pick sharding, multi-region, microservices, or event streaming anticipating "millions of users," without distinguishing **total accounts**, **concurrent users**, **peak traffic**, **stored data volume**, and **criticality per flow**. Define load, growth, latency thresholds, and run load tests before adding mechanisms.

### 3.2. Splitting Services by Technical Layers Instead of Business Boundaries

The "controller service → business service → database service" pattern turns function calls into remote call chains, introducing timeouts, retries, service-to-service auth, distributed logs, and network failures. Service decomposition should be based on **independent business capabilities, change lifecycles, data ownership, distinct scaling needs, or trust boundaries**, not merely having many classes.

### 3.3. Putting Asynchrony Everywhere

Queues and events help offload background work, absorb spikes, and reduce runtime coupling. Yet they add message redelivery, ordering, duplicate consumption, schema evolution, dead-letter queues, and eventual consistency. Use them only when a flow needs no immediate response, must absorb bursts, requires fault isolation, or offers another concrete benefit. Operations needing instant confirmation and strong consistency often suit synchronous transactions better.

### 3.4. Choosing Too Many Technologies

Combining multiple databases, frameworks, service meshes, monitoring suites, and CI/CD tools multiplies skill requirements, patching, contracts, and upkeep. **Technology diversity carries a fixed cost** even at low traffic. Standardizing a "paved road" for applications, deployments, monitoring, and permissions cuts configuration errors. Exceptions need clear rationale and an owner.

### 3.5. Keeping Old Mechanisms After Adding New Ones

For example, migrating to centralized identity while keeping two legacy authorization flows; adding a notification queue while an old cron job still sends the same data; switching storage while letting both sources accept writes indefinitely. Whenever adding a component, ask: **which mechanism is being replaced, when is it retired, and how do we verify safe removal?**

## 4. Decision Principle: Simplest Option That Fully Meets Requirements

Before picking a technology, answer in order:

1. **What problem must be solved?** State behavior, traffic, risk, or constraint.
2. **Is there evidence?** Grounded in measurements, load tests, incidents, confirmed obligations, or assumptions?
3. **Can the current approach be improved?** For example, optimizing queries, adding indexes, targeted caching, scaling resources, or bounded retries.
4. **What does the new option add?** Count services, datastores, network boundaries, secrets, pipelines, owning teams, and recovery workflows.
5. **Are the benefits measurable?** State expected improvement and how it will be evaluated.
6. **When should the decision be revisited?** Define growth signals, limits, risks, or organizational shifts.

~~~mermaid
flowchart TD
    A["Business requirement or NFR"] --> B{"Metrics and acceptance criteria defined?"}
    B -->|Not yet| C["Measure baseline, verify assumptions"]
    C --> B
    B -->|Yes| D{"Small improvements to current option suffice?"}
    D -->|Yes| E["Optimize, load test, monitor outcomes"]
    D -->|No| F["Compare architectural options"]
    F --> G["Evaluate benefits, complexity, and risks"]
    G --> H["Pick sufficient option, record ADR"]
    H --> I["Roll out incrementally, re-measure"]
    E --> I
    I --> J{"Metrics and limits still fit?"}
    J -->|Yes| K["Continue maintaining"]
    J -->|No| A
~~~

Two supporting principles:

- **KISS (*Keep It Simple, Stupid*):** Choose the option easiest to understand and maintain when it satisfies required needs.
- **YAGNI (*You Aren't Gonna Need It*):** Avoid implementing mechanisms solely for an unproven future. YAGNI is never an excuse to skip mandatory safety, security, or recovery requirements.

Distinguish **investing in changeability** from **deploying all that separation upfront**. Clean module separation enables splitting into services later, without forcing modules to deploy as microservices from day one.

## 5. Comparing Common Architectural Decisions

| Decision | Usually Simpler Starting Option | When to Accept Added Complexity? | New Costs and Risks |
| --- | --- | --- | --- |
| **Monolith / microservices** | Well-modularized monolith | Measurable need for independent deploy/scale, clear business domains, matching team ownership | Remote APIs, distributed transactions, multiple pipelines, cross-service observability |
| **Synchronous / asynchronous** | Synchronous calls with timeouts for immediate responses | Background work, fan-out, reducing runtime coupling, absorbing bursts | Retries, duplicate messages, ordering, lag, failure investigation |
| **One database / polyglot persistence** | One engine fitting most data needs | Proven specialized data needs poorly served by current engine | Multiple backup systems, IAM, migrations, monitoring, and skill sets |
| **Single region / multi-region** | One region across multiple Availability Zones where appropriate | Demanded by RTO/RPO, geography, data obligations, or region-loss impact | Replication, failover, routing, split-brain, disaster drills |
| **Single cloud / multi-cloud** | One provider with necessary dependency governance | Justified by contracts, regulations, market, or concentration risk | IAM, networking, data, staffing, and operations across platforms |
| **Managed / self-hosted** | Managed service when constraints fit | Specialized control/features needed or proven lower TCO | Patching, backups, capacity planning, on-call, provider limits |
| **Shared CI/CD / custom per team** | One shared pipeline and observability template | Verified specialized deployment requirements | Fragmented workflows, harder support and auditing |

These are **guidelines**, not immutable technology rankings. A poorly structured monolith can be more complex than a well-managed set of small services; a managed service may look pricier on the invoice yet lower total cost. Comparisons must reflect context and organizational capability.

## 6. End-to-End Example: Cloud Booking Application

Suppose a team of 5 developers and 1 infrastructure engineer is building a booking app for an initial market. Customers search slots, place holds, pay via a partner, and receive confirmations; support staff look up transactions. The team must protect personal data, prevent double-booking, recover from incidents, and control cost.

**The figures below are illustrative only** and must be replaced with real measurements and approved requirements in an actual project. Assume peak demand is 200 requests/second for lookup; booking mutations carry lower load; API lookup target is p95 under 500 ms at peak. No evidence yet justifies deploying business domains independently.

### 6.1. Starting with a Modular Monolith and Managed Services

~~~mermaid
flowchart TB
    U["Customers / Partners / Support Staff"] --> Edge["DNS / HTTPS / Edge as needed"]
    Edge --> LB["Load balancer or API entrypoint"]
    subgraph Cloud["Cloud region; AZ count per SLO"]
        LB --> App["Modular monolith: Search • Booking • Payment Integration • Support"]
        App --> DB[("Managed relational database")]
        App --> O[("Object storage if needed")]
        App --> Q["Managed queue for background jobs"]
        Q --> W["Worker sending notifications / retries"]
        App -.-> Obs["Logs • Metrics • Traces • Alerts"]
        W -.-> Obs
    end
    App <--> Pay["External payment gateway"]
    W --> Notify["Email / SMS service"]
~~~

This option has few **deployment boundaries** yet still requires:

- Managing **booking confirmation** with appropriate database transactions and constraints to prevent duplicates or overlaps; precisely defining rules by unit and time interval.
- Payment integration with **idempotency keys**, callback verification, timeouts, sensible retries, and reconciliation. Never assume partners call back only once and in order.
- Offloading email/SMS to the background since it does not need to finish inside the booking transaction. When emitting events after DB writes, account for event-loss protection such as a **transactional outbox** when reliability requires.
- Protecting sensitive data via authorization, encryption, lifecycle rules, and auditing; managing secrets centrally.
- Having monitoring, backups, restore testing, on-call policies, and approved SLOs from the start.

The diagram does not imply "one instance is always enough" or "one region is always enough." Replica counts, database HA, and RTO/RPO targets must follow business criticality. Early on, a modular monolith on managed compute can meet needs without self-operating Kubernetes.

### 6.2. Internal Modules Keep Change Costs Low

~~~text
application/
  booking/             # holds, confirmations, cancellations
  inventory/           # data source and availability rules
  payment-integration/ # payment partner, reconciliation
  notification/        # dispatch requests and delivery status
  support/             # support features
  shared-platform/     # shared logging, config, auth adapters
~~~

The principle matters more than folder names: **each module owns clear business responsibilities, a defined internal API, and controlled dependency direction**. Never turn the shared module into a place where every module mutates everyone else's data. If modules share one database inside a monolith, still enforce table ownership and data-access rules. Do not force internal calls over HTTP merely to mimic a distributed system.

### 6.3. An "Ultra-Scalable" Option Expensive to Operate

Suppose the team splits immediately into 12 independent services, each with its own database, plus a service mesh, heavy event streaming, dual-cloud deployment, and cross-region failover. The team must manage 12 release lifecycles, service-to-service auth, API contracts, data consistency, schema migrations, tracing, disaster recovery, and network sync.

Under current illustrative needs, there is no evidence benefits outweigh costs. The team should load test, track bottlenecks, and plan evolution from real data.

### 6.4. When to Split Incrementally?

Suppose search later develops vastly different load and release cycles from booking. You can:

1. Identify which search data is a **derived read model**, while booking transactions use the authoritative datastore.
2. Standardize the lookup API/module and measure coupling to the rest of the system.
3. Trial extracting search into a scoped service, with a read-model update mechanism and data-lag monitoring.
4. Compare p95/p99, error rate, independent release velocity, cost, and on-call toil before/after.
5. Expand the split only if gains are substantial; retain a rollback or merge-back path if the hypothesis fails.

**Signals for extracting a service:** one module routinely blocks another's releases; load/resource scaling profiles diverge sharply; business boundaries and owners are stable; the team can monitor and operate an independent service. "Codebase reached 50,000 lines" is not enough on its own.

## 7. Clear Boundaries Without Over-Abstraction

**Good boundaries** keep business changes localized; **poor boundaries** turn minor edits into multi-step coordination. For each module or service, explicitly document:

1. **Responsibilities:** Which rules and data does it own?
2. **Contracts:** Which calls, events, and data are public?
3. **Dependency direction:** Who may call whom, and are circular dependencies absent?
4. **Failure policies:** How are timeouts, retries, partial results, idempotency, and recovery handled?
5. **Owners:** Who develops, secures, operates, and upgrades it?

Abstraction helps when wrapping likely changes or removing meaningful duplication. It hurts when every action traverses layers of interfaces/factories/adapters adding zero value, or when a team builds an "all-purpose internal framework" ahead of demand. There is no rule saying "every module must have an interface"; value comes from **reducing coupling and cost of change**.

## 8. Managing Data and Processing Flow Complexity

Data is often what makes system splits hard to reverse. Every copy of data must answer:

- **Source of truth:** Which record holds final authority?
- **Freshness:** What maximum data lag is acceptable for each feature?
- **Consistency:** Which operations need strong consistency, and which tolerate eventual consistency?
- **Recovery:** If sync fails or processing duplicates, how is it detected and repaired?
- **Lifecycle:** How is data retained, deleted, archived, and authorized?

For example, a slot browse page may use a cache or search index updated with bounded lag, **but the confirmation step must recheck booking eligibility and authoritative state**. If the read model shows free slots while authoritative data is sold out, the system must reject or prompt reselection.

| Mechanism | Problem Solved | Complexity Accepted |
| --- | --- | --- |
| Cache | Reduces read load and latency | Invalidation, TTLs, stale data, cache stampedes |
| Queue | Decouples background work and absorbs bursts | At-least-once delivery, retries, deduplication, DLQs, monitoring |
| Transactional outbox | Reduces risk of DB commit succeeding without emitting event | Outbox table, relay worker, duplicate handling, cleanup |
| Read replica | Scales read capacity and offloads primary | Replication lag, query routing, failover, and cost |
| Event sourcing | Stores event stream as primary data when justified | Projections, replay, schema evolution, querying, and operations |
| CQRS | Separates read/write models when requirements diverge sharply | Dual models, data sync, monitoring inconsistency |

Never apply all these techniques as a "standard checklist." Each mechanism is justified only when concrete benefits can be described, measured, and governed.

## 9. Simplifying Operations, Security, and Infrastructure

A simple application diagram is not enough if operations and security demand heavy manual work. Controlling complexity also means reducing repetitive tasks and configuration drift risk.

### 9.1. Standardize Operational Workflows

- Use one common deployment workflow, automated testing, and appropriate rollback or roll-forward mechanisms.
- Centralize configuration and secrets management; minimize unjustified per-environment exceptions.
- Standardize logs, metrics, traces, correlation IDs, dashboards, actionable alerts, and runbooks.
- Use *Infrastructure as Code* where it aids environment reproducibility, change previewing, and reducing manual config.
- Drill recovery, verify backups and access permissions; eliminate manual steps during incident recovery.

Repeatable workflows reduce reliance on "the one person who knows how to run it." Nevertheless, uncontrolled automation can propagate errors broadly; reviews, least privilege, and remediation plans remain essential.

### 9.2. Never Drop Security Controls for Surface Simplicity

Authentication, least-privilege authorization, encryption, network protection, secrets management, backups, audit trails, and compliance audits may be mandatory. Simplification means **choosing more effective ways to deliver security capabilities**: use centralized identity instead of each app handling passwords itself; use a secrets manager instead of scattering credentials in unmanaged configs.

Adding a service also adds machine identities, permissions, secrets, network links, and control configs. **Attack surface** and **audit cost** must enter the decision.

### 9.3. Base Scalability and Reliability on Business Impact

A low-traffic system may need very high availability if downtime causes severe harm; a high-traffic system might tolerate batch processing. Never infer "no HA needed" from "small" or "must go multi-region" from "large."

Align on **SLOs, response times, RTO, RPO, critical task classification, and downtime impact**, then compare options by cost and operability. Unrehearsed multi-layer redundancy can add failure points rather than raising reliability.

## 10. Measuring Complexity via Changeability and Operability

No single metric captures complexity completely. Counting services, databases, or lines of code is only an initial clue. Combine change, incident, and real cost data:

| Dimension | Reference Metric / Signal | Interpretation |
| --- | --- | --- |
| Changeability | Lead time from approved change to production; number of teams or repos coordinating | Rising for similar feature scope signals hard-to-manage coupling |
| Stability | Change failure rate, recovery time after failed deploys | Exposes toll from overly complex boundaries or processes |
| Operations | Non-actionable alert count, diagnosis time, manual steps | Cutting noise and manual toil dramatically lowers operational load |
| Structure | Synchronous steps on critical path, dependency count, cyclic module dependencies | Helps spot coupling and cascading failure risks |
| Data | Duplicate data sources, sync errors, replication lag, failed reconciliations | Reveals real cost of distributed data |
| Economics | Infrastructure cost plus ops staffing; cost per successful transaction | Avoids shrinking cloud bills while inflating human effort |
| Cognitive load | Time for new engineers to fix bugs/deploy safely; ratio of components with owners and runbooks | Reflects how understandable and transferable the system is |

An illustrative dashboard after consolidating pipelines (all numbers hypothetical):

| Signal | Before Improvement | After Improvement | What to Verify |
| --- | --- | --- | --- |
| Deploy/approval steps for a small change | 7 | 3 | Were handoffs reduced while keeping mandatory controls? |
| Median recovery time for comparable incidents | 90 minutes | 35 minutes | Is sample size sufficient, and were severities comparable? |
| Pipelines edited when an internal contract changes | 5 | 1 | Did cross-team coupling genuinely drop? |
| Operational cost per successful transaction | No baseline yet | Measuring | Cannot conclude economic efficiency from these numbers yet |

Improving a few metrics does not prove the whole system improved. Inspect SLOs, security risks, error rates, and load together to avoid local optimization. For instance, deploying less often may lower failure counts while slowing feature delivery; evaluate context and trends.

## 11. Establishing a Complexity Budget

A complexity budget is an **internal governance rule**, not an industry-wide fixed number. The team defines how many technology stacks, deployment models, and dependency types it can sustainably operate; exceptions require evidence, an owner, and a review trigger.

An example policy:

- **Default** to runtimes, databases, observability, and pipelines supported by the platform team.
- **New services** require an independent business domain, distinct deploy/scale rationale, and plans for SLOs, security, data, and on-call.
- **New datastores** must cite queries or requirements that existing engines cannot reasonably meet, plus backup, migration, and access plans.
- **Multi-region or multi-cloud** requires risk-impact analysis, failover criteria, drills, and ongoing cost estimates.
- **Temporary components** require an owner, review date, and criteria to retire or formalize.

Scoring rubrics can structure discussions, provided **scores never become an automated decision algorithm**:

| Criterion | How to Evaluate | Priority Direction |
| --- | --- | --- |
| Meets mandatory requirements | Satisfies SLOs, security, data, recovery, and applicable obligations? | **Disqualifying gate**: reject if unmet |
| Implementation cost | Build, migration, testing, and training time | Lower when benefits are equal |
| Operational cost | On-call, backups, incidents, upgrades, provider management | Lower when benefits are equal |
| Cognitive load, dependencies | Components to understand, change together, and trace during errors | Lower when benefits are equal |
| Future scalability | Cost, speed, and risk under load growth or new domains | Sufficient for evidence-backed growth scenarios |
| Reversibility | Can we roll back, move data, consolidate, or swap providers? | Easier to reverse amid high uncertainty |

Evaluate **total cost of ownership** over a sensible horizon, such as 12–24 months, rather than monthly cloud bills alone. When outcomes hinge on big assumptions, run a technical spike or *proof of concept* to reduce uncertainty before committing.

## 12. ADRs and Architectural Debt

An **Architecture Decision Record (ADR)** is a concise note explaining why an option was chosen in a specific context. ADRs curb repeated debates and help newcomers tell temporary choices from lasting constraints.

ADR example:

~~~markdown
# ADR-007: Modular monolith for Phase 1

## Context
Small team, single market; bookings require strong consistency.
No evidence yet requiring independent domain deployments.

## Mandatory Requirements
Prevent double-booking; enforce access controls, observability,
backups, and recovery matching approved targets.

## Options
1. Modular monolith on managed compute.
2. Domain-driven microservices.

## Decision
Choose Option 1, enforce crisp module boundaries and standardized observability.

## Trade-Offs
Lowers network/ops cost, though modules cannot yet scale or deploy independently.

## Revisit Conditions
A module needs independent scaling/deployment backed by measurements;
or release lead time rises due to cross-module coupling.

## Owner and Review Date
Tech Lead; revisit in 3 months or upon anomalous signals.
~~~

When uncovering **architectural debt**, log it with concrete impact:

| Item | Example |
| --- | --- |
| Debt | Two login workflows coexisting simultaneously |
| Impact | Increases configuration drift risk and complicates access audits |
| Evidence | Access permission incident or prolonged permission-change lead time |
| Remediation | Consolidate onto standard identity flow, add authorization tests |
| Owner | Platform and affected application teams |
| Removal criteria | Zero callers remaining on legacy flow; confirmed by logs |

Not every debt item must be fixed immediately. Prioritize by business impact, change frequency, incident risk, and carrying cost. Debt without an owner or removal criteria easily becomes permanent architecture.

## 13. Controlled Simplification Workflow

To avoid a high-risk "big-bang overhaul," change in small slices:

1. **Scope:** Pick a flow with frequent incidents, slow change lead time, or high cost; capture a baseline.
2. **Map:** List request paths, dependencies, data, access permissions, pipelines, and owners.
3. **Spot redundancy:** Overlapping tools, zero-value intermediary layers, manual steps, duplicated state.
4. **Identify non-negotiables:** SLOs, data, security, audits, RTO/RPO, integration contracts, and compliance obligations.
5. **Propose one small change:** Merge modules, remove unnecessary call hops, standardize deployments, reduce database engine variety.
6. **Verify:** Run relevant functional, load, fault, and security tests; compare change lead time, errors, cost, and operability.
7. **Retire legacy paths:** Remove unused configs, secrets, permissions, pipelines, and components once zero dependencies are confirmed; update runbooks and ADRs.

**For data**, never delete or merge datastores without a migration plan, reconciliation, backups, rollback, and owner sign-off. Long-term architectural simplicity must pair with safe transitions.

## 14. Well-Architected Evaluation

Simplification balances multiple dimensions rather than optimizing service count alone:

| Perspective | Potential Benefit of Simplification | Must Never Be Unconsciously Sacrificed |
| --- | --- | --- |
| **Operational Excellence** | Fewer custom processes; consistent runbooks and pipelines | Observability, incident response, continuous improvement |
| **Security** | Smaller attack surface, fewer permissions and secrets to manage | Least privilege, auditing, data protection, encryption |
| **Reliability** | Shorter dependency chains and fewer distributed failure sources | Backups, recovery, target fault tolerance |
| **Performance Efficiency** | Shorter call paths, fewer network hops | Latency, throughput, real-world scalability |
| **Cost Optimization** | Fewer redundant tools, lower operational effort | Essential redundancy and quality |
| **Sustainability** | Fewer idle resources and less duplicate processing | Measurable service levels and efficiency |

These perspectives remind teams to evaluate continuously. "Fewer services" is not always better: if merging everything causes a minor bug to crash the entire app or blocks safe releases, actual operational costs can climb. Decisions must rest on failure scenarios, recovery capability, and accountable teams.

## 15. Common Mistakes

| Mistake | Why It Causes Problems | Remediation |
| --- | --- | --- |
| "Use microservices from day one to avoid refactoring later" | Pays distributed overhead upfront for unverified demand | Modularize business domains, measure extraction needs, preserve evolution paths |
| "Simple means skipping backups/observability" | Shrinks box count while risking data loss and slow detection | Retain controls matching system criticality |
| "Async always scales better" | Adds ordering, retries, deduplication, eventual consistency | Use background processing only when tasks and SLOs permit |
| "Managed services need zero operations" | Still requires config, permissions, monitoring, backups, and quota management | Assign responsibilities and drill failure modes |
| "Few boxes on a diagram equals simple" | A monolith can still have cyclic coupling and zero boundaries | Measure change difficulty, coupling, and ownership |
| "Multi-cloud increases reliability by default" | Adds failure paths, sync points, and operational divergence | Analyze disaster scenarios, contracts, and goals first |
| "Keep the legacy path just to be safe" | Two live paths cause drift bugs and prolonged upkeep | Define cutover criteria and decommission legacy paths |
| "Cut the cloud bill at any cost" | Can increase downtime, labor, and risk | Track total cost alongside SLOs and risk |
| "Architectural decisions are permanent" | Retains designs no longer fitting context | Write ADRs with revisit triggers and owners |

## 16. Hands-On Exercise: Choosing a Minimal Evolvable Architecture

A team of 6 engineers is building an order management platform. The system handles order creation, partner payments, inventory management, email sending, and reporting. Over the next 12 months, the business expects traffic growth but lacks baseline metrics. Sales proposes "Kubernetes, 15 microservices, 4 databases, and multi-cloud to guarantee scale."

**Practice tasks:**

1. List at least **5 missing pieces of information** to confirm with business, operations, and security.
2. Draw a **conceptual context and deployment diagram** for Phase 1, specifying data ownership and external integrations.
3. Propose modules ensuring accurate order creation and inventory updates; choose **2 flows suitable for background processing**.
4. Compare a modular monolith and microservices across **performance, data, operations, security, cost, and scalability**.
5. Write **one ADR** and define **3 measurable signals** that would trigger revisiting the decision.
6. Build a before/after measurement plan: feature change lead time, API p95, error rate, cost per successful order, and incident recovery time.

### Evaluation Guide

A proposal meets standards when it **never ignores mandatory constraints**, justifies every component with concrete demand, clearly defines authoritative data sources, assigns owners and error handling, and specifies criteria to scale or extract components after real measurements.

Without independent deployment demands and when order/inventory operations require strong consistency, a modular monolith with a managed relational database can be a **reasonable candidate**. Emails, reporting, or analytics sync can be **background-processing candidates** with deduplication and failure recovery. Treat this as a starting point to verify, not a rigid rule for every system.

## 17. Checklist Before Adding a Cloud Component

- [ ] A **business requirement/NFR**, owner, and evidence exist for the problem being solved.
- [ ] Improving the current approach was considered; if not chosen, clear rationale exists.
- [ ] **Success criteria** and a before/after measurement method are defined.
- [ ] Costs include infrastructure **plus** development, security, upgrades, on-call, backups, and recovery.
- [ ] Data boundaries, access permissions, failure behavior, timeouts/retries, and observability are documented.
- [ ] A team owns deployment, operations, support, and incident decision-making.
- [ ] An ADR records the choice, trade-offs, revisit triggers, and exit path.
- [ ] A plan exists to retire legacy components or experiments once they no longer deliver value.

**Key takeaway:** Complexity is an architectural cost affecting every networking, compute, data, deployment, and operational choice. Invest in **clear business boundaries, consistent workflows, measurable requirements, and evolvability**. Start with the fewest components capable of meeting all mandatory constraints, and add complexity only when benefits are proven and trade-offs are accepted.
