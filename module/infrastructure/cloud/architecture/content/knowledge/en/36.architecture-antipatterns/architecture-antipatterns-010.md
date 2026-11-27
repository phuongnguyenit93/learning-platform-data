# Overengineering and lack of operational ownership

## 1. Why can a “pretty” architecture still fail?

A cloud architecture does not succeed merely by having many modern services, a high microservice count, or an intricate redundancy diagram. An architecture must **meet proven business needs** while being **operated across its lifecycle** by a team with the authority, tooling, and capacity to do so.

In **CLOUD_ARCHITECTURE**, learners move from business requirements to choices in **networking, compute, data, and deployment models**; every choice carries trade-offs in **reliability, security, scalability, cost, and operations**. The two antipatterns below frequently appear together:

1. **Overengineering:** building excessive components, abstraction layers, or redundancy mechanisms without corresponding requirements, evidence, or capability.
2. **Unclear operational ownership:** a system can be deployed, yet no person or team is explicitly accountable for monitoring, incident response, recovery, patching, cost control, and continuous improvement.

The two antipatterns can exist independently: a simple monolith can still be “unowned,” and a very complex system can have a dedicated operations team. However, when combined, **complexity grows while accountability does not keep pace**, causing incidents to spread and repairs to stall.

> **Principle:** A good architecture is **sufficient for current goals, has a clear upgrade path, and is operable with real-world resources**.

## 2. Identifying overengineering

**Overengineering does not mean complex technology is inherently wrong.** Multi-zone architectures, multi-region active-active, or distributed transactions can be completely justified for services requiring extreme availability. It becomes an antipattern when cost, risk, and operational toil exceed the value delivered in **your specific context**.

### Common warning signs

| Symptom | Concrete manifestation | What to verify |
|---|---|---|
| Splitting too many services | A small team maintains dozens of services, each with its own pipeline, DB, and API | Is there a real need to scale/release independently? Who owns each API and dataset? |
| Designing for huge hypothetical load | Building multi-tier autoscaling, queues, sharding, and complex caching before measuring load | What are actual peak traffic, throughput, and latency? |
| Redundancy beyond the SLO | Deploying multi-region active-active even though the business tolerates longer downtime | Do RTO, RPO, data consistency, drill capacity, and budget actually require it? |
| Too many intermediate layers | Data passes through multiple API gateways, brokers, proxies, adapters, and a service mesh | Which measurable problem does each layer solve? |
| Building custom instead of using managed services | Writing custom schedulers, secret stores, or database replication | Is there a requirement unmet by managed services? Who maintains that code? |
| Hype-driven technology | Adopting Kubernetes, event sourcing, CQRS, or microservices by default | Have benefits over a simpler solution been proven? |
| Overly generic configuration | Creating frameworks to handle scenarios that have never occurred | Are there real users for each extension point? |
| Heavy deployment workflows | Every minor change requires editing multiple repos, contracts, and infra stacks | What are lead time, release frequency, and change failure rate? |

These signs are **investigation leads**, not conclusive proof. For instance, a service mesh can bring genuine traffic control and service identity at scale; the issue is deploying it without matching requirements or operators.

### Root causes

- **Confusing “might need later” with “need right now”:** choosing technology for load levels or business models with no validated probability or timeline.
- **Measuring success by technology count:** treating many services as maturity even as lead time, cost, and incidents climb.
- **Copying reference architectures:** lifting a giant enterprise's design into a small product and team while ignoring original assumptions.
- **Missing telemetry:** optimizing for massive throughput or availability before benchmarking, calculating TCO, or defining SLOs.
- **Separating design from operations:** decision-makers do not take night pages, patch vulnerabilities, investigate incidents, or own budgets.
- **Fear of future change:** maximizing “generality” upfront even though many components will never be used.

### Technical and business consequences

Every new component adds **dependencies**, configurations, IAM policies, failure domains, network paths, logs, alert channels, API contracts, and upgrade obligations. Increasing service counts also multiplies the failure interactions among them.

With poorly designed and operated microservices, a simple request can traverse many network hops, triggering timeouts, stacked retries, data-consistency bugs, and hard tracing. With multi-region active-active, the challenge goes well beyond “duplicating infrastructure”: you must solve routing, replication, split-brain, update conflicts, RPO bounds, and failover testing.

Common outcomes are **longer development cycles**, **longer incident recovery times**, **unpredictable infrastructure and staffing costs**, and ultimately **lower actual reliability than the diagram promised**.

## 3. Identifying missing operational ownership

A workload “having developers” does not guarantee it **has an operational owner**. Operational accountability must attach to **an identified team** with access rights, skills, on-call rotation, budget, tooling, and decision authority.

### Easily overlooked symptoms

- Deployment pipelines succeed, yet nobody receives 5xx or disk-full alerts.
- Dashboards exist without alert thresholds, recipients, or remediation guides.
- Backups run under defaults, yet nobody has **tested a restore** or knows who authorizes one.
- Platform thinks the database belongs to the app team; the app team thinks platform manages it.
- Secrets, certificates, domains, or API tokens expire with no audit or renewal schedule.
- An auto-scaling service causes a billing spike while nobody owns cost monitoring.
- During a security incident, nobody knows which team has authority to block access, rotate keys, or sever connections.
- After a product handoff or engineer departure, no documentation or successor exists.

**“Everyone is responsible”** usually diffuses accountability: without specifying who decides and who acts, people wait for someone else.

### A table every workload needs

| Responsibility | Verifiable question |
|---|---|
| **Service owner** | Who owns SLOs, user experience, and risk prioritization? |
| **Technical owner** | Who approves architectural changes, upgrades, and bug fixes? |
| **On-call responder** | When a production alert fires at 02:00, who receives and responds? Who is the backup? |
| **Data owner** | Who decides data classification, access, retention, backups, and recovery targets? |
| **Security owner / liaison** | Who reviews vulnerabilities, permissions, secrets, and handles security incidents with security teams? |
| **Infrastructure / platform owner** | Who manages clusters, networking, IaC, quotas, shared platform services, and related incidents? |
| **Cost owner** | Who owns the budget, receives spend alerts, approves scaling, and runs cost reviews? |
| **Incident commander** | Who coordinates major incidents, communications, and rollback/failover decisions? |

Multiple roles can sit inside **one small team**, provided they are explicitly assigned. You do not need eight separate people or formal job titles for every row.

## 4. Why do these two antipatterns amplify each other?

~~~mermaid
flowchart TD
    A["Unclear requirements or missing measurements"] --> B["Add services / layers / redundancy"]
    B --> C["More dependencies and failure points"]
    C --> D["Need more observability, maintenance, drills, and coordination"]
    D --> E{"Owner, on-call, and runbooks assigned?"}
    E -- "No" --> F["Unanswered alerts / silent failures"]
    F --> G["Higher MTTR, rising costs, lost trust"]
    G --> H["Add firefighting tools or extra layers"]
    H --> B
    E -- "Yes" --> I["Re-evaluate value and measure effectiveness"]
    I --> J["Simplify or strengthen operational capacity"]
~~~

Example: a company routes a small API through **API gateway → service mesh → three internal services → two message brokers → multiple databases**. When checkout slows down, logs are fragmented, retries stack across layers, and nobody owns the end-to-end user journey. Each team claims “my service is green,” while customer transactions fail.

This incident has **two distinct root causes**: an unnecessarily fragmented execution path (**design**) and no single team accountable end-to-end for checkout (**operations**). Adding another dashboard or broker will not fix either.

## 5. Analyze requirements before deciding complexity

Architects must translate vague statements into **measurable targets and binding constraints**.

| Initial statement | Clarify into a question | Data to collect |
|---|---|---|
| “Must scale infinitely” | What are current peak load and 12-month forecast? | RPS/TPS, concurrency, p95/p99 latency, throughput |
| “Must always be online” | What are the availability SLO and acceptable downtime minutes? | Incident history, affected revenue, availability target |
| “Cannot lose any data” | Is RPO=0 truly required for all data or only specific transactions? | Data classification, per-flow RPO/RTO |
| “Must use microservices” | Which teams need independent releases/scaling? Where are data boundaries? | Team topology, lead time, change cadence, hot spots |
| “Cloud saves money” | Comparing which costs, over what horizon, including staffing? | Three-year TCO, licensing, network, dual-run, operations |
| “Use multi-region for safety” | Must we survive a full region outage? How can data sync? | BIA, RTO/RPO, residency, tested failover scenarios |

**BIA (Business Impact Analysis)** quantifies outage impact and separates hard requirements from wish lists. Never apply the same SLO/RTO/RPO to a rarely used internal page and a critical payment service.

### SLOs, error budgets, and realistic thresholds

In a 30-day month, a **99.9%** availability SLO allows roughly **43.2 minutes** of unavailability; **99.99%** allows only about **4.32 minutes**. These are illustrative time-based calculations; in practice, define **SLI measurement**, user scope, downtime accounting, and valid exclusions before operationalizing an error budget.

Higher SLOs generally demand matching self-healing, change control, redundancy, and drills. Never claim “four nines” merely from picking multiple availability zones; config bugs, dependencies, data corruption, or application defects can still cause outages.

## 6. Choosing a “just enough” architecture with a growth path

Follow a pragmatic decision loop:

1. **Lock down business invariants:** critical transactions, data correctness, RTO/RPO, residency, security, and required load.
2. **Baseline the simplest viable option:** the architecture with the fewest components that satisfies invariants and can be operated by the team.
3. **Measure or test the baseline:** load testing, failover tests, backup/restore, cost estimates, and delivery speed.
4. **Identify evidenced bottlenecks:** CPU, database connections, I/O, latency, release coupling, incidents, or product constraints.
5. **Add complexity only to solve a specific problem:** caching for repeated reads, queues for async work, partitioning for large data, service extraction for independent scaling/releases.
6. **Set explicit upgrade triggers:** e.g., p95 persistently above threshold, peak load nearing benchmark ceiling, release cadence blocked, or recovery drills missing RTO.
7. **Assign ownership before operating new components:** designate on-call, runbooks, alerts, cost center, and rollback paths.

~~~mermaid
flowchart TD
    A["Business requirements + SLO + constraints"] --> B["Simplest viable architecture"]
    B --> C["Benchmark, failure drill, TCO, security review"]
    C --> D{"Evidence of failing targets?"}
    D -- "No" --> E["Deploy, observe, schedule review"]
    D -- "Yes" --> F["Identify specific bottleneck or risk"]
    F --> G["Compare remediation options"]
    G --> H{"Can the team operate the option?"}
    H -- "Not yet" --> I["Simplify / train / use managed service"]
    I --> G
    H -- "Yes" --> J["Add needed capability and re-measure"]
    J --> C
~~~

### Reasonable starting choices (context-dependent)

- **Compute:** a stateless application structured as a modular monolith on managed compute is usually easier to operate than a dozen microservices for a small team.
- **Data:** start with a managed relational database configured with backups, monitoring, and HA matching RTO/RPO; shard or split databases only when separation and capacity needs are proven.
- **Networking:** segment public/private networks, IAM, and policies by risk; add a service mesh, custom private links, or multi-region only when requirements justify them.
- **Integration:** simple synchronous APIs for operations needing immediate answers; async queues to decouple load or absorb bursts, paired with idempotency and queue monitoring.
- **Deployment:** a CI/CD pipeline with clear tests, rollouts, and rollbacks before building intricate delivery platforms.

**Simplicity never means skipping safety.** Data encryption, least privilege, backup/restore, monitoring, logging, secret management, and change control remain baseline requirements even for a single-service app.

## 7. Establishing ownership: who is accountable for what?

### 7.1. Distinguish cloud provider vs. customer responsibilities

Cloud operates under a **shared responsibility** model: the provider manages part of the underlying service infrastructure, while the customer organization remains heavily responsible for configuration, data, and applications. Boundaries shift across IaaS, PaaS, and SaaS, and by service contract.

| Component | With VMs / IaaS | With managed databases / PaaS |
|---|---|---|
| Physical facilities, underlying cloud infra | Cloud provider | Cloud provider |
| OS, runtime, patching | Organization manages VM/OS and app | Provider manages service slice per SLA; organization still manages its code and config |
| IAM, network, policy, secret config | Customer organization | Customer organization |
| Schemas, queries, data permissions, correctness | Customer organization | Customer organization |
| Backup/restore and RTO/RPO | Organization designs, configures, and drills | Provider may run backup engine; organization still sets targets, configures, and verifies recovery |
| App performance monitoring and incidents | Customer organization | Customer organization, coordinating with provider on platform-layer issues |

Using managed services reduces **hands-on infrastructure toil**, yet **does not transfer application SLO accountability** to the provider. The owning team still owns business metrics, configurations, permissions, quotas, testing, and incident response.

### 7.2. A minimal RACI matrix

Suppose there are three groups: **Product (PRD)**, **Application (APP)**, and **Platform/SRE (PLT)**; specialized security and finance roles join relevant decisions. RACI stands for **R (Responsible: executes)**, **A (Accountable: final decision/owner)**, **C (Consulted)**, **I (Informed)**.

| Activity | PRD | APP | PLT |
|---|---|---|---|
| Define SLOs and business priorities | **A** | R | C |
| App quality, releases, code rollbacks | I | **A/R** | C |
| Manage cloud network, clusters, shared platform | I | C | **A/R** |
| Monitor end-to-end service health | C | **A/R** | R |
| App data backup/restore | C | **A** | R |
| Coordinate user-impacting incidents | I | **A/R** | R |
| Control service costs | **A** | R | C |

This is an **example for discussion**, not a rigid org chart. Every activity needs **one clear Accountable (A)** so nobody says “both had authority, so nobody decided.” If a platform is vendor-managed, document support SLAs and escalation paths clearly.

### 7.3. Ownership must be governed data

Every production workload should have an entry in a service catalog or equivalent config store:

~~~yaml
service: order-api
environment: production
business_owner: commerce-product
technical_owner: order-team
on_call_primary: order-team-primary
on_call_backup: platform-oncall
platform_owner: cloud-platform
data_owner: commerce-data
slo:
  availability: "99.9%"
  latency_p95_ms: 300
runbook: "internal://runbooks/order-api"
dashboard: "internal://dashboards/order-api"
incident_channel: "internal://incidents/order-api"
cost_center: "commerce"
last_dr_drill: "YYYY-MM-DD"
review_due: "YYYY-MM-DD"
~~~

This example is an **illustrative schema**, not internal data or live URLs. SLO thresholds are hypothetical and must be agreed with the business. More important than field names is **being able to locate who receives alerts and who holds authority to act immediately when faults happen**. Update ownership records whenever teams reorganize or services change hands.

## 8. Operational readiness before entering production

An architecture may work in a demo yet fall short of **operational readiness**. Run a **production readiness review (PRR)** backed by concrete evidence:

| Review area | Required evidence | Approver |
|---|---|---|
| **Ownership** | Service owner, primary/backup on-call, escalation path, active rotation | APP + PLT |
| **SLO / SLI** | Definitions for error rate, latency, availability, business metrics; alert thresholds | PRD + APP |
| **Observability** | Dashboards, logs/traces with correlation IDs, test alerts delivered to on-call | APP |
| **Recovery** | Backup policy, restore test, failover drill, measured RTO/RPO | APP + PLT + data owner |
| **Security** | IAM, secret rotation, vulnerability scans, audit logging, response plan | APP + security |
| **Deployment** | CI/CD, rollback, smoke tests, risk-tiered change approvals | APP |
| **Capacity** | Load benchmarks, quotas, capacity plan, dependency limits | APP + PLT |
| **Cost** | Monthly estimate, tags/cost center, budget alerts, scaling caps | PRD + APP + finance |
| **Documentation** | Runbooks, dependency map, external contacts, ADRs | APP |

One team does not have to **execute** every item, yet someone must be **accountable** for each. Missing a critical check must force an explicit decision: fix before go-live, accept time-boxed risk, or delay launch.

### What questions should a runbook answer?

A good runbook is organized around **observable symptoms**, such as “p95 latency above threshold for 10 minutes” rather than a vague “database error”:

1. Who receives the alert and how to confirm it is a real incident and who is impacted.
2. Dashboards, logs/traces, and **safe** diagnostic commands to isolate the fault.
3. Mitigation actions: release rollback, concurrency throttling, feature-flag toggle, bounded scaling, or authorized traffic shifting.
4. **Explicit prohibitions:** never delete data, never fail over while replication misses safety gates, never run irreversible schema migrations mid-firefight.
5. Escalation thresholds, decision-makers, and user communication steps.
6. How to verify recovery and run a postmortem to prevent recurrence.

When emergency steps live solely inside one engineer's head, operational risk stays high even on a simple architecture diagram.

## 9. Designing operations across Well-Architected pillars

| Pillar | Risk from the two antipatterns | Verifiable improvements |
|---|---|---|
| **Operational Excellence** | Missing owners and runbooks; releases need multi-team coordination | Service catalog, on-call, IaC, CI/CD, PRR, game days, postmortems |
| **Security** | Many components widen attack surface; nobody owns secrets/patching | Least-privilege IAM, inventory, policies, clear authz, secret rotation, security owner |
| **Reliability** | Nested dependencies, retry storms, nobody runs DR drills | SLO/RTO/RPO, backup/restore tests, fault isolation, breakers where fitting, on-call owner |
| **Performance Efficiency** | Heavy scaling still yields high latency from network hops and DB bottlenecks | Benchmarks, profiling, p95/p99 tracking, concurrency caps, right-sizing |
| **Cost Optimization** | Always-on multi-cluster/multi-region infra and unowned resources | Cost allocation, budget alerts, TCO, decommissioning, idle-resource reviews |
| **Sustainability** | Overprovisioned resources, duplicate pipelines, and idle compute | On-demand scaling, higher utilization, retiring surplus infrastructure |

**Hidden operational costs** typically include version upgrades, patching, maintaining dashboards, failover drills, distributed debugging, cert/secret management, incident handling, and onboarding new team members. A cloud service with cheap unit rates can still have high **TCO** if the team has to self-manage too many moving parts.

A “simpler” option must still satisfy all **hard constraints**. Data residency, transaction recovery, auditing, or tenant isolation are non-negotiable; never drop them just to lower service count.

## 10. Illustrative scenario: a fast-growing ordering platform

### Hypothetical context

A retail company has **5 developers**, no dedicated SREs, processes **10,000 orders/day**, and sees traffic jump roughly **4x** during promotions. The app covers ordering, catalog, inventory, payments, and email notifications; current goals are releasing twice a week, keeping order data accurate, and having a clean recovery path on failure.

Numbers in this scenario are for practicing architectural decisions; they do not prove upfront that any model has sufficient capacity. Measure **peak RPS, write ratio, DB size, payment latency, downtime tolerance, and RTO/RPO**.

### Option A: overengineered architecture

The team proposes **15 microservices**, each with its own repo/pipeline/DB, a central message broker for every interaction, a service mesh, three Kubernetes clusters, and two-region active-active. Meanwhile, there is no on-call schedule, many dashboards lack alerts, restores are untested, and nobody owns inter-region transfer bills.

Assuming business requirements have not proven independent releases/scaling across 15 domains, this design carries clear risks:

- A single checkout request crosses many network hops and dependencies; retries can duplicate side effects.
- Order, inventory, and payment changes are hard to keep consistent across separate databases.
- When one service fails, nobody owns the end-to-end checkout experience.
- Active-active requires conflict-arbitration rules and regional failover testing—never just “flipping a switch.”
- Fixed baseline cost and operational labor climb before delivering measurable value.

### Option B: right-sized evolvable architecture

Start with a **modular monolith** with clean module boundaries (order, inventory, catalog, payment) running on managed compute across multiple instances when needed. Use a **managed relational database** with backups, HA aligned to RTO/RPO, caching for measured heavy reads, and a queue for work not needing instant responses such as email delivery.

~~~mermaid
flowchart TB
    U["Customers"] --> E["DNS / WAF / Load balancer"]
    E --> A["Modular monolith app<br/>Order | Inventory | Catalog | Payment"]
    A --> DB[("Managed relational database<br/>backups + HA per RTO/RPO")]
    A --> Q["Queue for async tasks"]
    Q --> W["Worker for email / background jobs"]
    A -.-> OBS["Metrics / logs / tracing / alerts"]
    W -.-> OBS
    DB -.-> OBS
    OBS --> O["App on-call + Platform"]
~~~

This is a **reference logical diagram**. For order data, the team must still prove transaction consistency, retry correctness, access controls, and recovery. Add caches, queues, or multi-AZ HA only as validated needs and tests confirm them.

**Potential benefits:** fewer initial deploy steps and failure points; a small team can reason about the whole checkout flow; still scales horizontally if the app is stateless and the DB/shared components do not bottleneck. **Limitations:** not unconditionally suitable for every load; requires benchmarks, load tests, and module discipline to avoid internal coupling.

### Comparing the two options with evidence

| Criterion | A: many microservices / multi-region | B: modular monolith + managed services |
|---|---|---|
| Handles current load | Unproven; must benchmark | Unproven; must benchmark |
| Deployment and change | Many pipelines/contracts; independent only if org is ready | Fewer parts, though app modules release together |
| Reliability | Can survive regional faults if designed right; adds failure modes | Meets moderate SLOs if HA/restore/tests pass |
| Consistency | Requires cross-service transaction design | Single-DB transactions are usually easier to control |
| Cost / operations | High fixed base, networking, and SRE skill demands | Easier to control at small scale; still needs cost owner and on-call |
| Evolvability | Independent scale/release if domain boundaries hold | Can extract modules into services once evidence warrants it |

**Selection:** If benchmarks and SLO checks show Option B meets requirements, choose B and document **upgrade triggers** (e.g., catalog needs independent scaling for read load, or release cadence is repeatedly blocked). If B cannot meet a mandatory constraint, raise complexity deliberately and staff operational capacity before launch.

### Assigning accountability for Option B

- **Product owner:** confirms acceptable downtime and RPO/RTO, prioritizes incidents, owns product budget.
- **Order team:** owns app SLOs, releases/rollbacks, primary on-call, payment-error handling, and transaction correctness.
- **Platform team or designated ops partner:** owns networking, compute platform, baseline IAM, and DB/network support per charter; backup on-call/escalation.
- **Data/security owner:** approves data permissions, retention, encryption, and joins recovery drills and security response.

If current staffing cannot cover 24/7 rotation, **renegotiate support targets**, contract external support explicitly, or invest in on-call staffing. Never publish an SLA your operating model cannot uphold.

## 11. Incident scenario: nobody owns the failure at 02:00

Suppose after a release, a config change causes database connections to spike. The API returns 503 errors, yet individual service dashboards stay “green” because each service tracks only CPU. Alerts post to an unstaffed channel; platform on-call assumes it is an app bug, while developers assume the managed DB is the cloud provider's responsibility.

### Consequence and root-cause analysis

| Symptom | Possible root cause | Remediation |
|---|---|---|
| Customers cannot place orders | Connection pool / DB limit; a release altered behavior | Track end-to-end error rate, DB connections, traces, and release markers |
| Alerts go unanswered | Missing on-call / escalation | Assign primary/backup and test alert delivery regularly |
| Unsure whether to roll back or scale | Missing runbook and decision authority | Assess impact, name incident commander, follow safe rollback steps |
| Teams blame each other | No end-to-end checkout owner | Make one team accountable for product SLO with clear support roles |
| Similar outage repeats | Missing postmortem / action owners | Record timeline, systemic causes, remediation deadlines, and verification |

**Immediate actions:** incident coordinator confirms impact, assigns app and platform investigators, inspects the recent release and DB connections, rolls back or throttles traffic if safe, and verifies transactions recover. **Long-term fixes:** add user-facing SLOs, checkout-flow dashboards, connection-limit load tests, pooling rules, on-call rotations, and runbooks.

Postmortems should ask **why systems and processes allowed the error to happen**, not stop at “who changed the config.” Useful lessons become tracked actions with owners and due dates.

## 12. Fixing both antipatterns in a running system

Do not rush to rewrite everything. An improvement program can proceed in measurable increments:

### Step 1: Map reality

List services, databases, queues, network hops, CI/CD, environments, cloud accounts, data flows, and dependencies. Attach **owning team, business goal, relevant SLOs, cost, and on-call** to each component. Prioritize investigating anything labeled “owner unknown.”

### Step 2: Restore minimum operability

Establish user-impact alerts, primary/backup on-call, dashboards, runbooks for major failures, backup/restore drills, and rollback paths. Grant on-call engineers sufficient IAM permissions to mitigate incidents while requiring approvals and guardrails for destructive actions.

### Step 3: Audit low-value complexity

For each layer, ask:

1. Which **SLO, risk, or product need** does this component solve?
2. Is there telemetry proving it outperforms a simpler alternative?
3. If removed or merged, what is the impact on data, API contracts, and recoverability?
4. Who operates it, and does monthly/annual cost and incident resolution time go up or down?
5. Under what condition would we bring it back?

You may **merge small services**, drop unnecessary brokers, consolidate pipelines, move self-hosted components to managed services, delete redundant clusters/regions, or replace custom tooling with standard features. Every change requires **compatibility, data migration, rollback, and security impact** checks.

### Step 4: Migrate incrementally, measuring before and after

Capture baselines: p95 latency, error rate, lead time, deployment frequency, change failure rate, time to restore, page volume, and cost per run or per month. Change one slice at a time, run canary/shadow tests where appropriate, compare SLIs and business behavior, and only then retire old components.

### Step 5: Sustain decision discipline

Record **ADRs (Architecture Decision Records)** for major decisions; schedule periodic reviews of ownership, SLOs, and costs. Allow new components into production only with **designated owners and operational readiness**. When teams reorganize, hand over roles and access as part of the architectural change.

## 13. Decision matrix: conditional simplification

Use the matrix to structure discussions, not as a raw score that overrides mandatory constraints:

| Factor | Scoring question | Evidence |
|---|---|---|
| **Business benefit** | How critically does the component solve a core requirement? | SLOs, product requirements, outage cost |
| **Implementation cost** | How much time and budget are needed to design, test, and migrate? | Effort estimates, migration plan |
| **Operational cost** | How many extra pages, dashboards, patches, licenses, quotas, and debug hours does it add? | TCO, on-call roster, pricing, toil |
| **Reliability** | Does it remove failure modes or introduce new ones? | Failure-mode analysis, drills |
| **Scalability** | Is independent scaling/release needed in the forecast window? | Benchmarks, capacity forecasts, lead time |
| **Security & compliance** | Does it meet IAM, retention, residency, and audit rules? | Security review, data classification |
| **Ownability** | Do a team, permissions, and on-call capacity exist to run it? | RACI, runbooks, on-call schedule, PRR |

Factors like **data regulations, baseline security, and transaction correctness** act as hard gates. A high total score never legitimizes an option that breaks those gates.

### Short ADR template

~~~markdown
# ADR: Keep a modular monolith for the current ordering platform

## Context
Current load X RPS, p95 Y ms; SLO target ...;
APP team ... engineers, on-call ...

## Decision
Keep the app organized as well-bounded modules, deployed on
managed compute with a managed relational database.

## Options considered
1. Keep current monolith and strengthen operational controls.
2. Split into microservices across all business domains.
3. Extract only modules with measured bottlenecks.

## Rationale and trade-offs
Chosen option meets SLOs under load test ...;
fewer dependencies; accepts deploying one unified application.

## Ownership and re-evaluation triggers
SLO owner: ...; on-call: ...; data owner: ...
Revisit extracting catalog at ... RPS or if lead time exceeds ...
Review scheduled for ...; attach cost and benchmark results.
~~~

ADRs are valuable only when grounded in **real evidence**, revisited when assumptions shift, and backed by owners accountable for operational outcomes.

## 14. Applied exercise

A 7-person team is building an appointment-booking platform for a clinic chain. Initial load is 5,000 bookings/day, projected to triple within a year. The team proposes Kubernetes across three regions, 18 microservices, event sourcing for every mutation, and a separate database per service. There are no SLOs, RTO/RPO, on-call schedule, or runbooks. Sensitive health-related data demands strict protection and access control.

Tasks:

1. Identify **at least five investigation flags** pointing to overengineering or missing ownership. Separate known facts from unmeasured assumptions.
2. Propose an **initial architecture** covering networking, compute, data, deployment, and monitoring. Specify security, correctness, and recovery requirements that cannot be compromised.
3. Build a **RACI matrix** for SLOs, releases, DB/backups, security, on-call, and cost. Assign one A per activity.
4. Define **three evaluation metrics** indicating when to split a service or expand regions; specify measurement methods and trigger thresholds.
5. Write a **mini runbook** for when users cannot book appointments due to DB connection exhaustion; specify who gets paged, who coordinates, mitigation steps, and recovery checks.
6. Analyze at least **two Well-Architected trade-offs**: e.g., adding standby regions boosts availability while raising cost/data complexity, or managed DBs cut toil while still requiring schema, IAM, and restore-drill ownership.

**Self-check hints:** The platform can start as a modular monolith on managed compute and a managed database, separating permissions/resources by risk with backups/HA meeting RTO/RPO **once verified**. There is no basis to claim this handles target load without benchmarking. Three regions may become necessary if BIA, regulations, or SLOs prove it. With sensitive data, encryption, auditing, least privilege, and retention apply equally whether using a monolith or microservices.

## 15. Antipattern prevention checklist

### Before finalizing architecture

- [ ] Business requirements, current/peak load, RTO/RPO, SLIs/SLOs, and compliance constraints are verified.
- [ ] The option with the fewest components meeting constraints is identified; any added complexity has evidenced benefits.
- [ ] **TCO** is calculated, including infra, licensing, operational toil, on-call, drills, and data transfer.
- [ ] Every new service or layer states its purpose, assumptions, owner, and review triggers.
- [ ] Designs have passed benchmarks, security reviews, and risk-appropriate failure/restore tests.

### Before go-live and during operations

- [ ] Every workload has a **service owner, technical owner, primary/backup on-call**, and clear escalation path.
- [ ] SLIs/SLOs are measured end-to-end; alerts have recipients and test deliveries succeeded.
- [ ] Dashboards, logs/tracing, runbooks, operational permissions, and safe rollback mechanisms exist.
- [ ] Backups/restores and DR have been drilled and measured against RTO/RPO.
- [ ] Ownership for IAM, secrets, patching, data retention, security, and costs is assigned.
- [ ] CI/CD, releases, change reviews, and postmortems have owners driving improvements.
- [ ] Real metrics are periodically compared against ADRs to **prune complexity that no longer adds value**.

**Conclusion:** Never optimize an architecture for an unproven future and leave today's team carrying the bill. **Design for measurable needs, preserve clean growth paths, and assign clear operational ownership.** A simple, secure, recoverable system with active on-call ownership is usually far more reliable than a complex diagram nobody is equipped to run.
