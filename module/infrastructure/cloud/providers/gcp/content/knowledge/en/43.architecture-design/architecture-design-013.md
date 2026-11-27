# Practicing Writing and Reviewing GCP Architecture Decisions

A Google Cloud architecture can be deployed successfully yet still leave a critical question unanswered: **why did the team choose that design over alternatives?** Six months later, after team turnover, tighter security mandates, or unexpected operating costs, a diagram only shows *how* the system runs—not *why* it was built that way. At that point, architectural decisions need to be captured as technical evidence that can be reviewed, challenged, and updated.

An **Architecture Decision Record (ADR)** is a concise, structured record capturing the context, requirements, options, trade-offs, chosen decision, consequences, and verification criteria. An ADR is not meant to prove the author is always right; it makes the assumptions at decision time explicit so future readers can re-evaluate when circumstances shift.

This lesson belongs to the **GCP Architecture Design** chapter in the **CLOUD_PROVIDERS_GCP** module. The module explores Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability alongside cost. In this lesson, we practice **authoring a complete ADR and running a decision review** using a realistic yet hypothetical Java/Spring scenario.

> **Scope limitation:** All traffic, SLO, budget, recovery time, and scoring numbers in this lesson are **training assumptions**, not real benchmarks or Google Cloud service commitments. Before applying in production, replace them with organizational data, current pricing quotes, and test results from your actual workload.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish an ADR from an architecture diagram, detailed design doc, RFC, and runbook.
- Determine when an ADR is needed and how to maintain decision change history.
- Clearly document business context, critical user journeys, assumptions, hard constraints, and non-functional requirements.
- Evaluate designs against the six pillars of the Google Cloud Well-Architected Framework.
- Compare Compute Engine, GKE, Cloud Run, App Engine, or other service options without choosing by personal preference.
- Use weighted matrices properly alongside mandatory constraint checks and test evidence.
- Author an ADR for a Spring Boot service, run a multi-role review, address critiques, and build a verification plan.
- Identify when an ADR must be updated or superseded by a new ADR.

## 1. What Is an ADR and When Do You Need One?

An ADR captures **a significant architectural decision** along with its rationale. Examples:

- Choosing Cloud Run services over GKE to serve a Spring Boot API.
- Choosing single-region Cloud SQL HA and defining RTO/RPO boundaries.
- Using Pub/Sub for asynchronous events instead of synchronous HTTP calls between services.
- Choosing private ingress, VPC egress, and service-to-service IAM for a sensitive system.
- Splitting projects by environment, adopting Shared VPC, and separating runtime from deployer identities.

ADRs are valuable when at least two reasonable options exist, the choice carries long-term consequences, or the decision cannot be inferred directly from code. For minor changes covered by existing approved standards, a pull request and config docs suffice—do not create an ADR for every environment variable.

| Document | Core Question | Typical Contents |
|---|---|---|
| ADR | Why choose this option? | Context, options, decision, trade-offs, consequences |
| Design document | How will the system be built? | Components, sequences, API/data contracts, diagrams, migrations |
| RFC / Proposal | Should this proposal be approved? | Problem statement, stakeholder feedback, pending options |
| Runbook | What steps apply during deploy/incidents? | Operational commands, triggers, rollbacks, escalation |
| Threat model | How could the system be attacked? | Assets, trust boundaries, threats, controls, residual risks |
| Terraform / manifests | How is desired state declared? | Resources, IAM, networking, deployment configuration |

An ADR can link to these other artifacts without copying entire codebases or runbooks inline. Google Cloud recommends storing ADRs in Markdown close to the relevant codebase for discoverability, code review, and version-controlled history.

### 1.1. ADR Lifecycle

Teams can adopt a status convention such as:

| Status | Meaning |
|---|---|
| Proposed | Initial proposal and preliminary evidence ready, awaiting review |
| Accepted | Authorized approvers signed off on the option and conditions |
| Rejected | Option not selected; retained to avoid rehashing settled debates |
| Superseded | Old decision replaced by a newer ADR, with bidirectional links |
| Deprecated | No longer applies to current design; possibly mid-transition |

This is a **recommended governance convention**, not a status enforced automatically by Google Cloud. An `Accepted` ADR does not mean every component is already built; track implementation state in your issue tracker and attach validation evidence as needed.

~~~mermaid
flowchart LR
    A["Problem / requirement change"] --> B["Proposed ADR"]
    B --> C["Tech, security, and ops review"]
    C --> D{"Sufficient evidence?"}
    D -->|"Not yet"| E["PoC, benchmark, threat model, cost"]
    E --> B
    D -->|"Yes"| F{"Approved?"}
    F -->|"No"| G["Rejected + rationale"]
    F -->|"Yes"| H["Accepted"]
    H --> I["Deploy, monitor SLOs and cost"]
    I --> J{"Assumptions changed?"}
    J -->|"No"| I
    J -->|"Yes"| K["New ADR supersedes old decision"]
    K --> B
~~~

## 2. Minimum Structure of a Good ADR

A good ADR should answer the following questions on its own even if the author is not in the room:

| Section | What to Record | Signs of Weakness |
|---|---|---|
| ID, title | Unique ID and the specific decision under review | Generic titles like “Architecture” |
| Status, date | `Proposed`/`Accepted`..., decision date, and version | Unclear whether the decision is still active |
| Owners, reviewers | Accountable person, team, and approver roles | Nobody owns it |
| Context | Problem and user impact | Listing services without stating the problem |
| Critical user journey | Essential business flow to protect | Simply saying “system must be fast” |
| Requirements & NFRs | SLOs, latency, security, recovery, data residency, cost | Unmeasurable goals |
| Assumptions & constraints | Knowns, unknowns, and non-negotiable conditions | Picking a tool first and rationalizing later |
| Options | Viable candidates, including status quo when reasonable | Only one option listed |
| Evaluation | Evidence, pros/cons, cost, risks | Gut-feel scores with no explanation |
| Decision | What is chosen, within what scope, and why | “Use GCP because it is modern” |
| Consequences | Trade-offs, residual risks, required follow-up work | Claiming zero downsides |
| Verification | Tests, owners, deadlines, pass/fail thresholds | No proof steps |
| Revisit triggers | When to reopen the decision | Treating the ADR as permanent dogma |
| References | Design docs, issues, metrics, IaC, threat models | Untraceable evidence |

Distinguish three types of statements:

- **Fact:** verified via logs, benchmarks, service contracts, or versioned docs.
- **Assumption:** prediction awaiting verification, e.g., “traffic triples by year-end”.
- **Decision:** choice approved by accountable owners, e.g., “run the API on single-region Cloud Run backed by one Cloud SQL HA instance”.

Never present an assumption as a fact. Without load-test p95 data, mark it **“not yet measured”** rather than writing a number as if proven.

## 3. Review Framework: The Six Well-Architected Pillars

The Google Cloud Well-Architected Framework organizes guidance around **six pillars**. When reviewing an ADR, use them as a checklist of questions rather than a mandatory shopping list of services.

| Pillar | Review Questions | Evidence to Look For |
|---|---|---|
| Operational excellence | Are ops owners, CI/CD, rollbacks, observability, and incident playbooks defined? | Owners, release runbooks, Cloud Monitoring dashboards |
| Security, privacy, compliance | Are least-privilege IAM, trust boundaries, data protection, and audits clear? | IAM matrix, threat model, encryption and audit plans |
| Reliability | Are SLOs, fault tolerance, and recovery tested and verified? | Error budgets, failure drills, backup/restore results |
| Cost optimization | Are workload and growth-scenario costs compared? | Estimates, Billing exports, budgets/alerts, unit costs |
| Performance optimization | Are latency, throughput, quotas, bottlenecks, and load tests planned? | Load tests, p95/p99, CPU/memory, DB connections |
| Sustainability | Does the design avoid idle waste and measure resource efficiency? | Autoscaling, right-sizing, resource utilization |

An ADR does not need equal depth across all six pillars. However, if a pillar is omitted, explain why. For instance, an ADR selecting a queue technology will examine delivery semantics and reliability more deeply than VM sizing details.

### 3.1. Cross-Pillar Questions

Pillars naturally tension against one another:

- Raising minimum instances reduces cold starts yet increases cost and idle compute.
- Running multi-region reduces regional outage risk yet increases networking, sync complexity, and ops burden.
- Tightening network egress protects data yet adds proxy or DNS configuration overhead.
- Cutting replicas saves money yet reduces fault tolerance and may hurt latency.
- Using managed services cuts toil yet changes runtime control and provider coupling.

A good review does not demand maximum scores on every pillar. It demands **clear reasoning for chosen trade-offs, measurement plans, and contingencies when assumptions fail**.

## 4. Practice Exercise: Choosing Infrastructure for Orders API

### 4.1. Hypothetical Prompt

A company builds a Java 21 / Spring Boot app named **Orders API**. The API accepts orders, persists state in PostgreSQL, and emits events for an asynchronous fulfillment service. The company currently has two backend engineers, one part-time DevOps engineer, and no dedicated Kubernetes operations team.

Sample requirements:

| ID | Type | Hypothetical Requirement |
|---|---|---|
| F-01 | Functional | Accept HTTPS POST to create orders and GET for status |
| F-02 | Functional | Emit events after orders are durably persisted |
| F-03 | Functional | Decouple fulfillment worker processing from the API |
| NFR-01 | Reliability | API availability target: **99.9% monthly** |
| NFR-02 | Performance | POST p95 latency ≤ **300 ms** under defined load conditions |
| NFR-03 | Scalability | 20–150 requests/second normal, hypothetical peak 400 requests/second |
| NFR-04 | Recovery | Target RTO ≤ **60 minutes**, target RPO ≤ **15 minutes** for defined incidents |
| NFR-05 | Security | No direct public DB exposure; dedicated service identities; no static SA keys |
| NFR-06 | Data | Order data and backups must comply with company-approved storage locations |
| NFR-07 | Cost | Target operating budget **900 USD/month** for API runtime + data + related transfer |
| NFR-08 | Operations | Deploy multiple times/week; runtime rollback within ~10 minutes |
| C-01 | Constraint | Team does not yet operate Kubernetes as a standard platform |
| C-02 | Constraint | Must use PostgreSQL compatible with the existing application |

**All figures are hypothetical for practice.** A 99.9% SLO translates to roughly 43.2 minutes of unavailability over a 30-day month *if measured 24/7 under that SLI definition*; this is an academic error budget calculation, not a Google Cloud SLA. RTO/RPO targets in an ADR are operational goals that must be tested via backup/replication plans—never guaranteed automatically just by picking Cloud SQL HA.

### 4.2. Critical User Journey and System Boundaries

Critical user journey (CUJ): a customer submits an order, receives confirmation, and can check its status. Orders must never be dropped or duplicated on client retries.

~~~mermaid
flowchart LR
    C["Client"] -->|HTTPS + identity| A["Orders API"]
    A -->|Transaction| DB[("Cloud SQL PostgreSQL")]
    A -->|Outbox event| DB
    DB --> O["Outbox publisher"]
    O -->|Publish| P["Pub/Sub topic"]
    P -->|Push / pull| W["Fulfillment worker"]
    W --> DB
    A --> L["Cloud Logging / Monitoring"]
    O --> L
    W --> L
~~~

This diagram illustrates a **reference option** for review, not an already-approved decision. Adding a direct event-publish call right after DB commit without an outbox or equivalent safeguard creates a failure window where an order is saved yet the event is never emitted. The ADR must document choices around consistency and replayability.

### 4.3. Separating Hard Gates and Priorities

**Hard gates** are non-negotiable rules: data must reside in approved locations; PostgreSQL compatibility; no over-privileged IAM; recovery targets must be testable.

**Priorities (weighted criteria)** are negotiable trade-offs: lowering ops toil, optimizing cost, reducing cold starts, portability, and leveraging team skills.

An option failing any hard gate must be rejected or marked **Conditional** until a remediation exists. Never award bonus points in “low cost” to excuse missing mandatory security controls.

## 5. Three Options to Compare

### Option A: Cloud Run Services + Cloud SQL + Pub/Sub

- Java Spring Boot runs as a Cloud Run service; pushes events to a worker service or uses a worker pool depending on consumption pattern.
- Managed PostgreSQL via Cloud SQL. Private connectivity over an approved VPC topology; isolated identities and secrets.
- Stateless API autoscaling on requests; max instances and connection pools capped to protect the database.
- Cloud Build/Cloud Deploy or standardized CI/CD deploying digest-pinned images with traffic splitting.

**Strengths:** minimal VM/cluster management; fits small teams and request-driven APIs; clean revisions and per-service IAM.

**Trade-offs:** cold starts, concurrency tuning, instance/region/quota caps, DB connection pressure; long or continuous tasks need dedicated resource types. Cloud Run does not automatically solve Cloud SQL availability or event consistency.

### Option B: GKE Autopilot + Cloud SQL + Pub/Sub

- API and workers run in Pods; Deployments, Services/Gateways, probes, and Horizontal Pod Autoscalers defined in Kubernetes.
- GKE manages node infrastructure in Autopilot, yet the team must still understand Kubernetes objects, IAM/RBAC, policies, resource requests, and deployments.
- Can adopt GitOps, service mesh, or custom controllers as needs grow.

**Strengths:** Kubernetes ecosystem; fits many microservices sharing a platform; supports fine-grained orchestration patterns.

**Trade-offs:** significant cluster/workload design, networking, policies, resource requests, and troubleshooting work. Without prior Kubernetes experience, time-to-operate exceeds Option A. Costs must be modeled by workloads and cluster fees, not Pod count alone.

### Option C: Compute Engine Managed Instance Group + Cloud SQL + Pub/Sub

- VM images or containers on VMs running service processes; MIGs, load balancing, autohealing, and rolling updates.
- Team manages guest OS, patching, runtimes, VM images, capacity, and observability agents.

**Strengths:** high OS and execution control; fits legacy Java apps requiring specialized agents, drivers, or OS dependencies.

**Trade-offs:** heavy operational burden; baseline idle resource costs during off-peak hours; team must maintain OS hardening and template rollbacks.

### Should App Engine Be Evaluated?

App Engine Standard/Flexible can be added as Option D if the company already runs App Engine or has existing operational expertise. Here, the team can note “excluded from the initial shortlist due to OCI artifact standardization and architectural alignment toward Cloud Run/GKE”, explicitly labeling this a **scope decision** rather than claiming App Engine cannot run Spring Boot. If a reviewer shows App Engine fits better, expand the shortlist and re-evaluate.

## 6. Evaluation Matrix and Scoring Method

A matrix is only a discussion aid. Provide rationale, data, and reviewers for every score; never treat self-assigned numbers as “scientific proof”.

| Criterion | Weight | A: Cloud Run | B: GKE Autopilot | C: Compute Engine MIG |
|---|---:|---:|---:|---:|
| Low operational effort | 25% | 5 | 3 | 2 |
| Projected cost | 20% | 4 | 3 | 3 |
| Elasticity with load | 15% | 5 | 4 | 3 |
| Security and config boundaries | 15% | 4 | 4 | 4 |
| Reliability and recoverability | 15% | 4 | 4 | 3 |
| Portability / long-term skills | 10% | 3 | 5 | 3 |
| **Sample weighted total** | **100%** | **4.30/5** | **3.65/5** | **2.90/5** |

Weighted score formula:

~~~text
Option score = Σ (weight_i × score_i) / 100

Cloud Run:
(25×5 + 20×4 + 15×5 + 15×4 + 15×4 + 10×3) / 100 = 4.30

GKE Autopilot:
(25×3 + 20×3 + 15×4 + 15×4 + 15×4 + 10×5) / 100 = 3.65

Compute Engine MIG:
(25×2 + 20×3 + 15×3 + 15×4 + 15×3 + 10×3) / 100 = 2.90
~~~

**Interpretation:** A leads under small-team and stateless HTTP assumptions. However, cost, reliability, and performance scores are **not yet measured**. Before approval, the team must verify via PoCs, load tests, pricing estimates, and failure drills.

### 6.1. Sensitivity Checks

Ask: if weights shift, does the decision still hold?

For example, if an organization already has a strong GKE platform team, Kubernetes operational toil drops substantially. If an operator or service mesh incompatible with Cloud Run is required, B clears hard gates better. If the workload needs custom kernel/OS tweaks, Option C may become the sole compliant choice.

Score **after** verifying hard gates. Record uncertainty ranges rather than false precision, e.g., “A cost = 4 ± 1 until load tests and networking estimates finish”.

### 6.2. Evidence to Collect

| Assumption | Verification Method | Condition to Record in ADR |
|---|---|---|
| Cloud Run meets throughput | Load-test at target concurrency; measure p95/p99, 5xx, cold starts | Load scenario, region, CPU/RAM config, and results |
| Cloud SQL avoids overload | Measure active connections, pool size, CPU, IO, p95 queries | Max instances × connections/instance, safe thresholds |
| SLOs are met | Define SLIs and track in Cloud Monitoring | Measurement window, numerator/denominator, targets |
| RTO/RPO are met | Run backup/restore/failover drills in staging | Actual measured RTO/RPO per failure scenario |
| Budget is met | Pricing Calculator + Billing monitoring | Assumptions for requests, vCPU/GiB, egress, logs, DB |
| Security is sound | IAM review, threat model, private connectivity checks | Trust boundaries and configuration evidence |

## 7. Repository-Ready ADR Template

A template should be concise and reviewable like code. Here is a Markdown skeleton; teams adapt fields to their approval workflow:

~~~markdown
# ADR-NNN: [Decision Under Review]

- Status: Proposed
- Date: YYYY-MM-DD
- Owners: [team or role]
- Reviewers: [Architecture, Security, SRE, Finance as needed]
- Scope: [service/project/environment]
- Related: [design doc, threat model, issue, benchmark]

## Context
[Business problem and current architecture]

## Critical user journey
[Business flow to protect and unacceptable user failures]

## Functional and non-functional requirements
[SLIs/SLOs, throughput, latency, data residency, RTO/RPO, budget]

## Assumptions and constraints
[Knowns, unknowns, and hard gates]

## Options considered
[A / B / C, including pros/cons and rejection reasons]

## Decision
[Chosen option, scope, date, accountable owner]

## Consequences and risks
[Cost, lock-in, toil, residual risks, mitigation plans]

## Validation and rollout
[PoC, pass/fail thresholds, owners, rollbacks]

## Revisit triggers
[Traffic growth, regulation changes, SLO breaches, cost surprises...]

## References
[Links to verified sources]
~~~

Assign each ADR a stable ID like `ADR-013`. File naming follows team conventions; when changing a decision, create a new ADR referencing the old one instead of erasing history. Store under `docs/adr/` inside the application repository or a shared location accessible to reviewers.

## 8. Completed ADR Example: Choosing a Platform for Orders API

The example below is **solely a hypothetical case record**, not an approval for any real production system.

### ADR-013: Run Stateless Orders API on Cloud Run Services

**Metadata**

| Field | Illustrative Value |
|---|---|
| Status | **Proposed**, pending PoC and formal review |
| Proposed Date | 2026-11-19 |
| Owner | Orders API Team |
| Reviewers | Platform/DevOps, Security, SRE, Data Owner, FinOps |
| Environment | Staging first, production after passing gates |
| Scope | HTTP API runtime choice; excludes standalone data-platform decisions |
| Links | Design doc, load-test report, IAM matrix, and pricing sheet (to be added) |

#### Context

Orders API is written in Spring Boot, serves HTTP requests, and does not rely on local filesystem state. Traffic sees sharp peaks alongside long low-load periods. The development team is small and lacks dedicated Kubernetes staff. The system must durably store orders and emit events reliably across retries.

#### Hard requirements

- Never write personal data to logs or treat container filesystems as durable storage.
- Approved PostgreSQL database with data/backups complying with corporate storage location policies.
- API runtime identity holds only required permissions on Cloud SQL, Secret Manager, and related APIs.
- 99.9% SLO and 60-minute RTO / 15-minute RPO targets must have verifiable measurements.
- Must include strategies for runtime rollback, backup/restore, and duplicate message handling.

#### Options

- A — Cloud Run + Cloud SQL + Pub/Sub: minimizes ops toil and scales by request, yet requires tuning concurrency/cold starts and DB connection caps.
- B — GKE Autopilot + Cloud SQL + Pub/Sub: rich Kubernetes capabilities, yet lacks a suitable platform owner today.
- C — Compute Engine MIG + Cloud SQL + Pub/Sub: full OS control, yet heavy patching and capacity management toil.

#### Proposed decision

**Conditionally select A**, using a Cloud Run service for Orders API, Cloud SQL PostgreSQL for state, and Pub/Sub for asynchronous event flows. Transactional events use an outbox or equivalent mechanism to prevent dropped events between DB commit and publish. Consumers must handle redeliveries idempotently; do not assume Pub/Sub provides default exactly-once delivery across all delivery modes.

This proposal is not yet `Accepted` because full load-test data, restore drill results, and cost checks are pending. Authorized approvers switch status to `Accepted` only after gates pass.

#### Reference architecture

~~~mermaid
flowchart TD
    subgraph Clients["Outside trust boundary"]
      U["User / frontend"]
    end
    subgraph GCP["Application project - approved environment"]
      E["HTTPS entry / Auth"]
      R["Cloud Run: Orders API"]
      D[("Cloud SQL PostgreSQL HA")]
      O["Outbox publisher"]
      P["Pub/Sub topic"]
      W["Fulfillment consumer"]
      S["Secret Manager"]
      M["Cloud Logging / Monitoring"]
    end
    U --> E --> R
    R -->|Private connection / IAM| D
    O --> D
    O -->|Publish| P
    P --> W
    W --> D
    R --> S
    R --> M
    O --> M
    W --> M
~~~

The diagram shows logical flows, **not a complete network specification**. The design doc must detail private networking, endpoints, DNS, IAM, firewalls, Cloud SQL connection method, and where the outbox publisher runs. Drawing a “private connection” arrow alone does not prove traffic is private.

#### Consequences

**Positive:** team deploys only images/revisions without managing VMs or clusters; scales per request; per-service IAM; supports progressive releases.

**Negative:** cold starts can impact p95; max instances and connection pools require caps; network/egress configs can add fees; Cloud Run and Pub/Sub carry specific runtime semantics; no custom host OS/kernel tweaks.

**Residual risks:** Cloud SQL regional outage, backward-incompatible schema rollbacks, delayed event publishing, duplicate processing on retries, sensitive data accidentally logged, and traffic surges exhausting DB connections.

#### Mitigations

| Risk | Mitigation | Owner | Evidence |
|---|---|---|---|
| DB connection exhaustion | Cap Cloud Run max instances, tune HikariCP pool; load test | Backend + SRE | DB metrics under peak |
| Dropped events post-commit | Outbox + publisher retries + idempotent consumers | Backend | Failure injection tests |
| Missed SLOs | Metrics/alerts/traffic splitting and runbooks | SRE | Canary and SLI results |
| Slow data recovery | Required backups/PITR, restore rehearsals | Data owner | Measured RTO/RPO |
| IAM risks | Least privilege, Workload Identity, zero JSON keys | Security | IAM review |
| Cost overruns | Billing budgets, quotas, right-sizing, periodic reviews | FinOps | Cost reports and unit economics |

#### Validation gates

- **Gate 1 — Security:** Security signs off on service identities, secrets, ingress/egress, project boundaries, encryption, and logging.
- **Gate 2 — Performance:** Load test at hypothetical 400 RPS peak hits target p95 under defined scenarios without overloading the DB. If it fails, tune configs or revisit options.
- **Gate 3 — Reliability:** Test failover/restore, measure RTO/RPO under specified failure scenarios; verify retries/idempotency.
- **Gate 4 — Operability:** SLOs, dashboards, alerts, runbooks, release/rollback rehearsals, and on-call rotation active.
- **Gate 5 — Cost:** Estimates under normal and peak scenarios stay within approved budget, including Cloud SQL, networking, and logging.
- **Gate 6 — Approval:** Architecture owner, Security, and Service owner accept residual risks or request revisions.

#### Revisit triggers

Reopen the decision if any of these occur:

- Sustained traffic/throughput exceeds assumptions or p95 breaches target repeatedly.
- The team adopts a shared GKE platform with lower net cost/operational burden.
- Runtime needs host capabilities unsupported by Cloud Run.
- Regional, compliance, or connectivity policies change.
- Cost per 1,000 orders exceeds approved thresholds.
- A major incident shows RTO/RPO or event delivery strategies fell short.

#### Decision record

*Current status:* `Proposed`. Owner gathers Gate 1–5 evidence; reviewers post feedback in the pull request; approvers promote to `Accepted` only after conditions are closed or risks formally signed off.

## 9. Running an Architecture Decision Review Meeting

Never let a single author write and self-approve an ADR for a critical system. Reviews need representatives from operations, data, security, and relevant business stakeholders, scaled to risk level.

### 9.1. Pre-Review Preparation

The author circulates ahead of time:

1. The `Proposed` ADR with design diagrams.
2. Functional/NFR table and hard gates.
3. Options matrix, scoring assumptions, and open questions.
4. Threat model scaled to data sensitivity and trust boundaries.
5. Cost estimates across at least two load scenarios.
6. Plans for PoCs, load tests, restore drills, and rollbacks.
7. Residual risks list, owners, and decision deadlines.

Never send a slide deck listing only product names and ask reviewers to rubber-stamp it. Reviewers need enough data to challenge key assumptions.

### 9.2. 45-Minute Review Agenda

| Sample Time | Topic | Lead |
|---|---|---|
| 5 min | State business problem and CUJs | Product / owner |
| 10 min | Hard gates, architecture, and three options | Author |
| 10 min | Trade-offs, threat model, reliability, cost | Reviewers |
| 10 min | PoC evidence, unverified assumptions, challenges | SRE / Security / Data |
| 5 min | Provisional decision, residual risks, owners | Architecture owner |
| 5 min | Validation plan and revisit deadline | Facilitator |

Reviewers must give **issue + impact + evidence + requested change**, not merely “I prefer GKE”.

### 9.3. Review Room Question Checklist

**Scope and Argument Quality**

- Is the core decision summarized in one clear sentence?
- Are at least two genuinely viable options evaluated?
- Why were rejected options eliminated?
- Do metrics cite measurement sources, assumptions, and timestamps?
- Were any failure modes or sudden traffic spikes overlooked?

**Security and Compliance**

- Through which components and trust boundaries does sensitive data flow?
- Who can deploy, what is the runtime identity, and who can read secrets?
- Are ingress/egress, private connectivity, firewalls, and audit logs clear?
- Does data residency cover data, backups, logs, and replicas alike?
- Have any IAM or security policy exceptions been formally approved?

**Reliability and Operability**

- Which CUJs do SLIs/SLOs protect, and where are they measured?
- Are there single points of failure, retry storms, or cascading dependency risks?
- Under which exact failure scenarios were RTO/RPO measured?
- Are on-call owners, alerts, runbooks, rollbacks, and canary guardrails in place?
- If the database or region fails tonight, who acts first?

**Performance and Cost**

- Are there representative load benchmarks, p95/p99 numbers, and max connection calculations?
- Where do peak load and growth assumptions come from?
- Do costs include egress, storage, logging, backups, HA, and support?
- What happens if traffic triples or drops 90%?
- How can idle resources and cost per business unit be trimmed?

## 10. Approval Criteria, Revisions, and Rejections

Reviews should conclude with one actionable outcome:

| Outcome | Meaning | Next Step |
|---|---|---|
| Accepted | Sufficient evidence and residual risks signed off | Finalize ADR, proceed through release gates |
| Accepted with conditions | Option fits, yet specific items must close pre-release | Record owners, deadlines, evidence, and release blocks |
| Needs revision | Missing data or weak assumptions | Complete PoC/costing/threat model and re-review |
| Rejected | Fails hard gates or poorly suited | Record rationale to avoid rehashing without new data |
| Deferred | Premature to decide now | Record triggers and revisit date |

If an organization restricts ADR statuses to `Proposed`/`Accepted`/`Rejected`, track “Accepted with conditions”, “Needs revision”, or “Deferred” as **review outcomes** in the issue/PR without complicating the ADR state machine.

### 10.1. Writing High-Quality Review Comments

Ineffective comment example:

> “GKE is better, use GKE.”

Actionable comment:

> “The ADR has not yet shown Cloud Run meets 300 ms p95 at 400 RPS, especially as Cloud SQL connections scale with instances. Please run a load test capturing p95/5xx/DB connections and document concurrency and max-instance settings before we Accept.”

Good reviews pinpoint **missing evidence**, rather than swapping the author's personal preference for the reviewer's.

## 11. Hands-On Verification and Cost Control Practice

The lab goal is completing an ADR and review—**do not create billable GCP resources** without an authorized test project.

### Step 1: Write the problem statement

In two to four sentences, state the users, business flow, current bottleneck, and decision needed. Avoid opening with “we must use Cloud Run”, which jumps to a conclusion before analysis.

### Step 2: List hard gates and NFRs

Create a requirements table with IDs, sources, measurement methods, and priorities. Separate “must have” from “nice to have”. Assign owners for data residency, RTO/RPO, and budgets.

### Step 3: Diagram current and proposed architectures

Mark network/data trust boundaries and at least three flows: requests, database transactions, and asynchronous events. Check for unauthenticated paths or data crossing unauthorized boundaries.

### Step 4: Compare options and score

Include at least three options, stating scales and weights upfront. Check weights sum to 100%, eliminate options failing hard gates before ranking, and document score rationales alongside missing data.

### Step 5: Build the verification plan

For each critical assumption, specify **verification method, owner, pass/fail threshold, deadline, and artifact to save**. Saying “we will benchmark later” cannot earn unconditional `Accepted` if performance is a hard gate.

### Step 6: Adversarial peer review

Assign roles: author, Security, SRE, and Finance. Reviewers pose at least three decision-changing questions. The author answers with evidence or explicitly flags unknowns.

### Step 7: Record outcome and link evidence

Document review outcome, unresolved risks, owners, deadlines, and issue/PR links. Never delete rejected options; keep rejection reasons so newcomers understand history.

### Step 8: Set a review cadence

Once running, monitor SLOs, costs, incidents, capacity, and ops time. Define **revisit triggers** rather than assuming the ADR stays valid forever.

## 12. Using Google Cloud Tools to Collect Evidence

When granted access to a test environment, gather evidence across these categories:

| What to Prove | Data Source / Tool |
|---|---|
| SLIs/SLOs, error rates, p95/p99 | Cloud Monitoring dashboards and app metrics |
| Request failures, exceptions | Cloud Logging / Error Reporting |
| Dependency latency | Cloud Trace or instrumented spans |
| Compute/instance capacity | Cloud Run / GKE / Compute Engine metrics and quotas |
| Cloud SQL saturation | Cloud SQL metrics and Query Insights where fitting |
| Cost | Cloud Billing reports, BigQuery exports, Pricing Calculator |
| IAM & service identities | IAM policies, audit logs, service account inventory |
| Deploys / rollbacks | Cloud Build / Cloud Deploy logs, revision history, Git commits |
| Backups / restores | Timestamped drill results and verification data |

Use only data you are authorized to collect. Never pull sensitive payloads, secrets, customer info, or private configs beyond your access level into public ADRs. Link to access-controlled records rather than pasting credentials or sensitive audit entries.

### 12.1. Writing a Validation Record

~~~yaml
check_id: PERF-01
scenario: "400 RPS for 15 minutes, 10% order creation requests"
environment: "staging, same target region as production"
configuration:
  cloud_run_max_instances: 20
  cloud_run_concurrency: 40
  hikari_maximum_pool_size: 10
pass_criteria:
  p95_latency_ms: 300
  http_5xx_ratio_max: 0.001
  database_connections: "must not exceed DBA-approved threshold"
evidence:
  status: "NOT_RUN"
  dashboard: "link pending"
  load_test_report: "link pending"
owner: "Orders API + SRE"
~~~

This is a **planned validation record**, not measured results. When executed, replace `NOT_RUN` with the verified status per policy, recording image config, commit SHA, test date, metrics, and report links. Never extrapolate one simple staging load test to claim production SLO compliance across all failure modes.

### 12.2. Checking Unit Economics

Beyond total monthly spend, compare cost per successful order:

~~~text
Cost per 1,000 successful orders =
  (In-scope infrastructure cost / Successful orders)
  × 1,000
~~~

Define scope explicitly: does it include Cloud SQL, Pub/Sub, egress, Logging, and shared cluster/VM overhead? When splitting shared costs across apps, state the allocation rule. Never report standalone Cloud Run spend as total system cost.

### 12.3. Budget Alerts Are Not Hard Spending Caps

Cloud Billing Budgets track spend and fire threshold alerts, yet alerts do not automatically halt all spending. An ADR must define real operational guardrails—max instances, quotas, resource creation permissions, timeouts, retention, and spend-surge response workflows—while accounting for Billing data lag.

## 13. Risk Management and Rollback Planning

Writing “we will roll back if errors occur” is insufficient. Specify **when**, **who**, **what rolls back**, **which dependencies cannot reverse**, and **how recovery is verified**.

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Cloud SQL overload when API scales out | Medium | High | Max instances, pool sizing, load testing | Backend + SRE |
| Release makes incompatible schema change | Medium | High | Expand-and-contract, rollback rehearsals | Backend + DBA |
| Pub/Sub redelivery duplicates orders | Medium | High | Idempotency keys, unique constraints/outbox | Backend |
| Peak-season cost spike | Medium | Medium | Budget alerts, capacity caps, cost reviews | FinOps |
| Over-privileged runtime IAM | Low–Medium | High | Least privilege, reviews, and audits | Security |
| Cannot restore backup within RTO | Unknown | High | Restore drills and measured targets | DBA / SRE |

These likelihood/impact ratings are **illustrative labels**. In real work, apply your organization's risk scales; “Unknown” must pair with an investigation task rather than being treated as low risk.

### Rollback vs. Recovery

- **Runtime rollback:** shift traffic back to a prior Cloud Run revision or revert deployment versions on GKE/MIG.
- **Database rollback:** you cannot default to reverting schemas/data simply by swapping container images. Design backward-compatible migrations or dedicated data recovery plans.
- **Recovery after data loss:** relies on backups, PITR, and verified restore capabilities.
- **Message stream recovery:** requires retries, dead-letter handling, replay, idempotency, and duplicate reconciliation.

Each rollback/recovery path needs its own owner and test case inside the ADR or linked docs.

## 14. Managing ADRs in Git and Superseding Decisions

Illustrative repository layout:

~~~text
orders-api/
├── src/
├── deployment/
│   └── cloud-run/
└── docs/
    └── adr/
        ├── README.md
        ├── 001-use-postgresql.md
        ├── 013-run-orders-api-on-cloud-run.md
        └── 024-supersede-013-for-kubernetes.md
~~~

This is only a structural example; you do not need to create these files for this exercise.

Governance workflow:

1. Create a new ADR with a fresh ID in `Proposed` status inside a pull request.
2. Assign owners, reviewers, and issue/architecture-board links scaled to scope.
3. Review alongside code/IaC changes or before building hard-to-reverse components.
4. Upon approval, mark `Accepted` with the date and remaining verification conditions.
5. When changing decisions, create a new ADR, mark the old one `Superseded`, and cross-link both.
6. Never delete `Rejected` or `Superseded` ADRs: history prevents repeating debates without new data.
7. Periodically audit ADRs whose assumptions—cost, regional rules, scale—have gone stale.

If an ADR bundles independent choices, split them. For instance, “choose Cloud Run runtime” and “use an outbox for reliable events” can be two cross-referenced ADRs so changing eventing later does not force rewriting the runtime record.

## 15. Critique Exercise: Spotting Flaws in a Poor ADR

Read this hypothetical ADR excerpt:

~~~markdown
# ADR-X: Use GKE Because We Are a Large Enterprise

Status: Accepted

We choose GKE because Kubernetes is best for microservices.
The app needs to run fast, stay always available, and be cheap.
No comparison needed because GKE is industry standard.
Security uses an Owner service account to avoid permission errors.
If deployment fails, we will roll back.
Estimated cost is 100 USD per month.
~~~

Group discussion: could this be approved for production?

**Flaws to call out:**

1. Missing context and CUJs; unclear what app or problem is being solved.
2. “Best”, “fast”, and “cheap” have no metrics or evidence.
3. Zero alternatives compared; Cloud Run and Compute Engine were ignored.
4. Missing cluster mode, region, node/workload requests, and networking details.
5. Granting `Owner` to runtime violates least-privilege IAM.
6. No SLOs, error budgets, RTO/RPO, or backup strategies.
7. The 100 USD cost guess lacks assumptions, SKUs, duration, networking, and storage.
8. Rollback lacks triggers, owners, runbooks, and database migration handling.
9. No named approvers, test evidence, or accepted residual risks.
10. `Accepted` status is untrustworthy without a review/validation trail.

**Appropriate review outcome:** `Needs revision` or `Rejected` per organizational rules. Reviewers should ask the author to rewrite context/NFRs, build a shortlist, fix security, and propose a test plan rather than blindly mandating a switch to Cloud Run.

## 16. Scoring ADR Quality with a Rubric

Score each criterion from 0 to 2:

- **0:** missing or unverifiable description.
- **1:** present, yet missing evidence or owners.
- **2:** clear, justified, or backed by an actionable verification plan.

| Criterion | Max Points |
|---|---:|
| Problem statement, CUJs, and scope | 2 |
| Functional/NFRs, assumptions, and hard gates | 2 |
| Options and rejection rationales | 2 |
| Well-Architected trade-offs | 2 |
| Performance/reliability/security evidence | 2 |
| Cost estimates and sensitivity | 2 |
| Decision and consequences/risks | 2 |
| Validation gates, owners, and deadlines | 2 |
| Rollback/recovery and operations | 2 |
| Revisit triggers, history, and links | 2 |
| **Total** | **20** |

Suggested interpretation: 17–20 indicates an ADR ready for formal review; 13–16 needs additions; under 13 requires rewriting. **A rubric never overrides hard gates**: a 19-point ADR violating a mandatory security rule still cannot be `Accepted`.

### Extension Exercise

Swap one assumption of Orders API:

- The team already runs a mature GKE + GitOps platform hosting 50 microservices.
- The workload shifts from an HTTP API to a continuously running stream consumer.
- A native agent requiring kernel privileges is mandatory.
- Multi-region deployment with complex data residency rules is required.
- Budget drops 40% while p95 must stay unchanged.

For each shift, identify the new hard gate, update at least two matrix cells, specify the needed PoC, and conclude whether to keep or change the option. **Never start with a product name**; start from the changed requirement.

## 17. Submission and Review Closeout Checklist

- [ ] ADR includes ID, title, status, date, owners, and reviewers.
- [ ] Problem statement and CUJs are clearly written.
- [ ] Measurable functional requirements, NFRs, and hard constraints exist.
- [ ] Assumptions are separated from verified facts.
- [ ] At least two genuinely viable options plus rejection reasons are included.
- [ ] Diagrams clearly mark components, data flows, and trust boundaries.
- [ ] Weighted matrix sums to 100% with explained scores.
- [ ] Security review covers IAM, secrets, ingress/egress, and data protection.
- [ ] Reliability review covers SLIs/SLOs, RTO/RPO, backups, and failure tests.
- [ ] Performance review covers p95/p99, concurrency, and dependency bottlenecks.
- [ ] Cost review includes supporting services and business unit economics.
- [ ] Plans exist for rollout, runtime rollback, and data recovery.
- [ ] Residual risks have owners, mitigations, and deadlines.
- [ ] Missing evidence is clearly marked `NOT_RUN` or pending verification.
- [ ] Review outcome states `Accepted`/`Needs revision`/`Rejected` and conditions.
- [ ] ADR is stored with the codebase or a searchable hub with evidence links.
- [ ] Revisit triggers exist to reopen the decision when conditions shift.

## 18. Self-Check

1. How does an ADR differ from a design doc and a runbook?
2. Why shouldn't a scoring matrix alone dictate a GCP platform choice?
3. What are the six Well-Architected pillars, and must every pillar score maximally?
4. Why isn't a 99.9% SLO automatically guaranteed by choosing Cloud Run or Cloud SQL HA?
5. Why can a “Cloud Run for API” decision be right today yet require a new ADR later?
6. How do you distinguish facts, assumptions, and decisions when reading an ADR?
7. Why is Cloud Billing Budgets only one piece of cost evaluation?
8. During a review, what questions test whether a “rollback” plan is truly actionable?
9. If a design satisfies 5/6 pillars yet violates a data residency constraint, should it be `Accepted`?
10. When should an ADR be marked `Superseded`?

**Answer Hints**

1. An ADR captures rationale and trade-offs of a choice; a design doc details implementation architecture; a runbook guides deployment or incident actions.
2. Scores often rely on assumptions and subjective weights; hard gates and technical evidence must be verified first.
3. Operational excellence, security/privacy/compliance, reliability, cost optimization, performance optimization, and sustainability. The goal is understanding trade-offs and priority rationale, not maximizing every pillar blindly.
4. SLOs measure end-to-end CUJ behavior across the entire system; single-service HA does not prove DB recovery, networking, code, and downstream dependencies meet targets.
5. Team skills, load, cost, compliance, or runtime needs evolve, making earlier trade-offs obsolete.
6. Facts have verified sources or measurements; assumptions are unverified; decisions are approved choices following governance.
7. Budget alerts do not impose hard spending caps; you need estimates, quotas, timeouts, IAM, right-sizing, and Billing analysis.
8. Who triggers it, what conditions trigger rollback, which version you revert to, how schema/data changes are handled, and how recovery is verified?
9. No. Any option failing a hard gate must be fixed, granted a valid formal exception, or rejected.
10. When a newer ADR replaces an `Accepted` decision and history must preserve cross-links between both records.

## Conclusion

An ADR has value when it **turns a technical preference into a verifiable decision with clear ownership and a trigger for change when new data arrives**. On Google Cloud, connect runtime, data, networking, and IAM choices to business requirements, SLOs, cost, operations, and trade-offs. Scores, diagrams, and service names are merely tools; what matters is framing context accurately, testing assumptions, and maintaining a verification and post-launch review plan.

## References

- [Google Cloud Architecture Center — Architecture decision records overview](https://docs.cloud.google.com/architecture/architecture-decision-records)
- [Google Cloud Well-Architected Framework](https://docs.cloud.google.com/architecture/framework)
- [Well-Architected: Operational excellence](https://docs.cloud.google.com/architecture/framework/operational-excellence)
- [Well-Architected: Security, privacy, and compliance](https://docs.cloud.google.com/architecture/framework/security)
- [Well-Architected: Reliability](https://docs.cloud.google.com/architecture/framework/reliability)
- [Well-Architected: Cost optimization](https://docs.cloud.google.com/architecture/framework/cost-optimization)
- [Well-Architected: Performance optimization](https://docs.cloud.google.com/architecture/framework/performance-optimization)
- [Well-Architected: Sustainability](https://docs.cloud.google.com/architecture/framework/sustainability)
- [Google Cloud Architecture Center — Reference architectures](https://docs.cloud.google.com/architecture)
- [Google Cloud — Billing budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Google Cloud — Pricing Calculator](https://cloud.google.com/products/calculator)
