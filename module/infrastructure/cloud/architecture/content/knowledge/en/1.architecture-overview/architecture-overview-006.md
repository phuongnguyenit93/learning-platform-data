# Roadmap for Designing and Reviewing Cloud Architecture

Designing cloud architecture is the process of turning **business goals and constraints** into a system that can be deployed, measured, operated, and improved. The work does not start with the question “should we use Kubernetes or serverless?”, but rather “who must the system serve, what quality levels must it meet, and which trade-offs are we willing to accept?”.

A good architecture does not require many services. It chooses the right level of complexity to meet requirements for **reliability, security, scalability, performance, cost, and operations**. Evaluating architecture with *Well-Architected* thinking helps turn those choices into verifiable assumptions and manageable risks.

After this lesson, you can:

- Progress from business requirements to an overall architecture diagram, networking, compute, data, and deployment model.
- Convert vague statements like “the system must be fast and stable” into measurable targets.
- Choose among common options based on load characteristics, team capabilities, and total cost.
- Design request paths, data paths, access permissions, and incident scenarios.
- Conduct a Well-Architected review cycle with evidence, priorities, and an improvement plan.

## 1. Big Picture: The Stages of an Architectural Decision

A practical roadmap can be divided into nine stages. This sequence helps avoid premature technology selection; in real projects, stages may iterate as new data emerges.

| Stage | Core Question | Inspectable Output |
| --- | --- | --- |
| 1. Understand the business | Who are the users, which business flows matter, and what creates value? | Scope, context diagram, primary user flows |
| 2. Quantify quality | How many users, and how fast and available must it be? | SLIs/SLOs, RTO/RPO, load forecasts, constraints |
| 3. Identify data and risks | What data exists, where does it travel, and who can access it? | Data classification, data flows, trust boundaries |
| 4. Choose application structure | Which blocks need separation, and how do they communicate? | Component diagram, Architecture Decision Records (ADRs) |
| 5. Design infrastructure | Where are networking, compute, storage, and databases placed? | Deployment diagram, service selection, network design |
| 6. Design for failure and growth | What happens when a component breaks or traffic grows? | HA, scaling, backup, DR, and testing plans |
| 7. Design operations and cost | How do we release, monitor, respond, and control spending? | IaC, CI/CD, runbooks, dashboards, cost estimates |
| 8. Well-Architected review | What risks exist in the architecture, and what evidence supports them? | Findings list, priority levels, owners |
| 9. Verify and iterate | Does the real system validate our assumptions? | PoCs, measurement results, adjustment decisions, review schedule |

Do not treat an architecture diagram as the final deliverable. A diagram only describes *the components*; a complete design must also specify **rationale**, **limits**, **how failures are detected**, and **how recovery works**.

## 2. Stage 1: Start from Business Needs

Before choosing a cloud provider, determine:

1. **Users and core journeys:** Who accesses the system? Which operations must be protected first: search, sign-in, ordering, or payment?
2. **Scope and external dependencies:** Which components does the team own? Are there payment gateways, identity providers, email services, or on-premises systems to integrate with?
3. **Timeline and budget:** When must it launch? How large is the engineering team, and what are its operational skills? What is the maximum spend?
4. **Constraints:** Are there regulations on data residency, retention periods, audit evidence, contracts, or incumbent vendors?
5. **Rate of change:** Is the product still experimental or running at steady load? Do certain features require frequent independent deployments?

**Running example:** a service-booking application where customers schedule appointments, staff process schedules, and the system sends notifications. The team expects 50,000 daily active users; peak traffic around 200 requests/second; peak hours concentrate on search and booking. These figures are **assumptions for learning and calculation**, not measurements from a live product.

Priority business flows are:

- Customers browse open slots and book appointments; two overlapping bookings must never be created for the same time slot.
- Staff update appointment statuses; changes must be stored durably.
- Notifications may arrive briefly delayed, but must never cause the booking transaction to fail.
- Administrators review action logs and handle disputes.

From here comes the first decision: **booking** is a flow requiring strong consistency at the write point; **sending notifications** can be decoupled from the synchronous path via a queue. This decision originates from business needs, independent of any specific cloud service.

## 3. Stage 2: Convert Quality Expectations into Measurable Targets

Requirements like “fast,” “secure,” and “zero downtime” are insufficient for design or acceptance. Pair each requirement with what is measured, thresholds, measurement conditions, and an owner.

| Attribute | Illustrative Target | Design Implication |
| --- | --- | --- |
| Availability | 99.9% of valid booking requests succeed monthly, excluding client input errors | Avoid single points of failure; measure along business journeys |
| Latency | 95% of schedule read requests complete under 300 ms server-side at expected load | Measure p95, optimize queries, consider caching |
| Throughput | Sustain 200 requests/second at peak and double during promotional campaigns | Load testing, rate limits, and controlled scaling |
| Recovery | Maximum 60-minute RTO, maximum 15-minute RPO for booking data | Appropriate recovery strategy and backup/replication schedule |
| Security | Only authorized staff can view customer data; log sensitive access | IAM, authentication, authorization, and audit logs |
| Cost | Monthly operating spend stays within approved budget at baseline load | Cost tagging, budget alerts, and headroom planning |
| Operability | Alerts fire when error rates cross thresholds; rollback procedure exists | Observability, CI/CD, runbooks, and incident on-call |

Two concepts to distinguish:

- **SLI (Service Level Indicator):** actual measurement, such as booking request success rate or p95 latency.
- **SLO (Service Level Objective):** target applied to an SLI over a period, such as 99.9% per 30 days. A 99.9% success-rate SLO equals an error budget of 0.1% of eligible requests; it does not automatically equal exactly 43.2 minutes of downtime when measured per request. For a *time-based uptime* metric, 99.9% over 30 days equals at most roughly 43.2 minutes of unavailability.

**RTO** is the maximum acceptable time to restore service after an incident; **RPO** is the maximum acceptable data loss expressed in time. Daily backups alone cannot prove a 15-minute RPO. Having standby replicas also does not prove a 60-minute RTO without rehearsing recovery.

Record the origin of each target: contractual commitments, compliance mandates, business impact analysis, or assumptions needing validation. Avoid picking “five nines” when the business does not need it and resources cannot support it, as higher availability requirements typically carry greater complexity and cost.

## 4. Stage 3: Analyze Load, Data, and Trust Boundaries

### 4.1. Estimate Load Before Sizing

Gather at least average traffic, peak traffic, read/write ratio, payload size, dataset size, growth rate, and seasonality. Check for sudden event-driven spikes rather than extrapolating from registered user counts.

For example, with 200 requests/second and an average processing time of **0.2 seconds** at a component, Little's Law gives a rough estimate:

~~~text
Average concurrent requests ≈ arrival rate × average processing time
                            = 200 requests/second × 0.2 seconds
                            = 40 requests
~~~

The number 40 only describes the average in-flight requests under those assumptions. It is **not** the number of containers to deploy: you must still measure CPU, memory, I/O, contention, queue wait time, connection limits, safe utilization thresholds, and failover headroom. Final sizing results must be verified with load tests.

### 4.2. Classify Data Before Choosing Storage

For each dataset, determine **sensitivity**, **authoritative source of truth**, **consistency level**, **retention period**, **access permissions**, **recoverability**, and **permitted geographic regions**.

| Data Group | Key Characteristics | Typically Suitable Choice |
| --- | --- | --- |
| Bookings, payments, ownership | Transactions and consistency constraints | Managed relational database, transactions, and constraints |
| Images, attachments | Large objects accessed via URL or API | Object storage with access policies and lifecycle rules |
| Sessions or reproducible search results | Fast access, tolerates refresh | Cache with TTL and invalidation strategy |
| Notification events | Asynchronous processing, retryable | Queue/event service and worker |
| Metrics, traces, logs | Observability and incident investigation | Observability service with retention policies |

Do not copy personal data into logs, traces, caches, or test environments without genuine need and proper safeguards. A data flow that stays “inside the cloud” can still cross multiple trust zones: Internet users, application services, databases, third-party partners, and operations teams.

## 5. Stage 4: Choose Application Structure at the Necessary Level

Before splitting into microservices, identify business boundaries and assess how teams collaborate:

- **Modular monolith:** suits small teams, evolving business domains, and needs for simple internal transactions. Still separate modules cleanly to reduce coupling.
- **Microservices:** suits domains with clearly independent deployment lifecycles, scaling profiles, or ownership; in return, requires managing network communication, distributed data, observability, and error handling.
- **Event-driven architecture:** suits deferrable tasks, multiple event consumers, or absorbing traffic bursts; in return, requires handling duplicates, ordering, retries, and eventual consistency.

You do not need a single label for the whole system. The booking example can start with **a modularized application**, a relational database, and a notification worker. Only split out domains that genuinely benefit from independent deployment when scaling or organizational needs shift.

### Choosing Compute

| Option | Strengths | Costs and Limits to Weigh |
| --- | --- | --- |
| Virtual machine (VM) | Strong OS and runtime control; supports specialized workloads | Self-managed patching, OS, autoscaling, and capacity |
| Containers on managed services | Consistent packaging, convenient rollout, fits APIs/workers | Must design images, networking, resources, and health checks |
| Kubernetes | Flexible orchestration across diverse workloads for teams with platform capability | High operational, security, and governance complexity/cost |
| Function/serverless | Automatic event-driven scaling; useful for short tasks or variable traffic | Execution time limits, cold starts, connection limits, quotas, and pricing model |
| PaaS/managed application platform | Accelerates deployment; reduces infrastructure administration | Less deep control; dependent on platform capabilities |

Base decisions on **needed control**, **load profile**, **application state**, **latency sensitivity**, **regulations**, and **operational capacity**. Service names differ across AWS, Azure, and Google Cloud, but the trade-off principles remain similar.

### Synchronous vs. Asynchronous

Keep work requiring an immediate answer to the user on the synchronous path, such as booking confirmation and transactional writes. Work like sending email/SMS can go through a queue to reduce latency and isolate notification provider faults.

When using a queue, design for **idempotency**: reprocessing the same message must not cause unintended side effects. Messaging systems can commonly redeliver messages; never assume every message is processed exactly once by default. Implement retries with backoff, a dead-letter queue, retention policies, backlog alerts, and safe replay mechanisms. If events must be guaranteed to emit after a database transaction commits, consider the **transactional outbox** pattern.

## 6. Stage 5: Combine Networking, Compute, Data, and Deployment

The illustrative diagram below is a starting design for the booking application. Components and links express logical responsibilities; concrete implementation must fit the chosen services.

~~~mermaid
flowchart TD
    U[Customers and staff] --> EDGE[DNS, TLS, CDN/WAF if needed]
    EDGE --> LB[Public load balancer]
    subgraph NET[Virtual network in one region]
        LB --> APP[Stateless app across at least 2 availability zones]
        APP --> DB[(Managed relational database HA)]
        APP --> Q[Managed queue]
        Q --> W[Notification worker]
    end
    APP --> OBJ[(Private object storage)]
    APP --> OBS[Logs, metrics, traces]
    W --> OBS
    W --> EXT[Email/SMS provider]
    DB --> BAK[Backups and restore checks]
~~~

This diagram must be interpreted across four layers:

**Network and access layer.** Design virtual networks/VPCs/VNets, subnet segmentation, routes, ingress/egress, DNS, and TLS. Place only mandatory entry points in the public tier; application and database tiers should reside in private networks where the solution permits. Control ports, sources, and destinations with appropriate firewalls/security groups/ACLs. Outbound Internet access from private subnets needs valid egress paths, such as NAT or private endpoints to supported services; a “private” subnet does not automatically reach every service. Never expose databases directly to the Internet merely for connection convenience.

**Compute layer.** Application replicas should be stateless or manage sessions out-of-process, with readiness/liveness checks, timeouts, resource limits, and rollback-capable releases. When deploying across multiple availability zones, verify that network paths, load balancing, and state stores all tolerate single-zone outages. Two instances inside the same zone do not equal a zone-fault-tolerant architecture.

**Data layer.** A managed relational database fits booking operations needing transactions and constraints to prevent double-booking. Configure indexes, connection pooling, backups, encryption, retention policies, and failover mechanisms. Read replicas can boost query capacity yet may lag behind the primary; never use a replica for consistency-critical availability checks without verification. Caching helps once invalidation strategies and staleness bounds are defined.

**Deployment layer.** Separate dev/test/prod environments using accounts/projects/subscriptions or appropriate authorization boundaries. Define infrastructure via **Infrastructure as Code (IaC)**, version configurations, curb manual changes, and enforce pre-release pipeline checks. Store secrets in a secret management system, never in source code or container images.

### Typical Data Choices

| Question | Decision Guidance |
| --- | --- |
| Transactions with rich relational constraints needing strong consistency? | Prioritize evaluating a relational database with transactions |
| High-scale key-value access, flexible schema, tolerating specific consistency models? | Evaluate NoSQL based directly on access patterns and transaction support |
| Long-term storage for files, images, backups? | Object storage, lifecycle policies, versioning/retention as needed |
| Heavy repeated reads tolerating brief staleness? | Cache with TTL, invalidation, memory bounds |
| Long-running tasks or external partner dependencies? | Queue/events with retries, timeouts, idempotency, and DLQ |

Do not adopt NoSQL simply because “it scales,” nor use a cache as authoritative transactional data. Suitability depends on access patterns, consistency, reporting needs, and recovery methods.

## 7. Stage 6: Design Ahead for Failures, Load Growth, and Security Incidents

### 7.1. Distinguish HA, Backups, and DR

- **High availability (HA):** limits disruption when a component or fault domain fails; e.g., multiple app replicas across zones with health checks and a failover-capable database.
- **Backup:** retains recoverable copies of data after accidental deletion, corruption, or other incidents. Continuous replication does not replace backups: logical errors can replicate to standbys.
- **Disaster recovery (DR):** recovery plan for incidents beyond HA scope, such as losing an entire region. DR strategies range from backup restoration to cross-region hot standby, chosen according to practical RTO/RPO.

Multi-region designs can reduce certain risks but increase cost, latency, data complexity, and operational burden; they are not mandatory by default for every application. A multi-AZ architecture only addresses scenarios within its configured scope and does not automatically survive full-region outages.

### 7.2. Prevent Cascading Failures

When a dependency slows down or fails, the system needs **explicit timeouts**, bounded retries with backoff/jitter, circuit breakers, or concurrency limits where appropriate. Reckless retries can amplify load onto an already overloaded dependency. Background work needs backpressure-aware queues; critical operations need idempotency keys to prevent duplicates when users resubmit requests.

Test key scenarios: one instance dies; one zone becomes unavailable; database fails over; email provider times out; queue fills up; bad deployment occurs; backup restore is needed; credentials are revoked. Record **time to detect**, **time to recover**, **actual data loss**, and remaining manual steps.

### 7.3. Security Across Trust Boundaries

Security design must span the entire data path, not just a WAF layer:

1. Authenticate users and services; authorize per API by resource and role.
2. Grant least privilege to workloads and operators; separate deployment, admin, and data-reading roles.
3. Encrypt data in transit with TLS; encrypt at rest with proper key management and lifecycle policies.
4. Centralize secret management, rotate as needed, and never write tokens or sensitive data to logs.
5. Scan images/dependencies, manage patches, audit configs, and monitor audit logs.
6. Analyze key attack paths: leaked credentials, misconfigured public storage, API abuse, unauthorized data modification, backup exfiltration.

Apply the cloud **shared responsibility** model: the provider manages part of the infrastructure depending on service type; customers remain appropriately responsible for configurations, identities, data, access permissions, and application protection. Using a “managed” service does not make a system secure by default.

## 8. Stage 7: Design Operations and Cost from Day One

A solution that works on demo day but cannot be monitored or recovered will struggle to meet SLOs in live operations.

### Observing the System

- **Metrics:** request rate, error rate, p50/p95/p99 latency, CPU/RAM usage, connection pools, queue depth, worker failure rate, and business metrics such as successful bookings.
- **Structured logs:** timestamp, severity, service name, error code, correlation/request ID; mask or omit sensitive data.
- **Distributed tracing:** trace journeys across APIs, databases, queues, and related services when diagnosing latency.
- **Actionable alerts:** prioritize user-impact and error-budget signals; link to dashboards, runbooks, and on-call owners. A standalone high-CPU alert does not necessarily correspond to a service outage.

### Deployment and Incident Response

Set up CI/CD with automated tests, appropriate security scanning, environment approvals or gates, progressive delivery (rolling/canary/blue-green depending on platform), rollback capability, and backward-compatible database migrations. Runbooks must cover symptom recognition, mitigation, escalation, recovery, and postmortems.

### Calculate Total Cost, Not Just Compute Cost

Estimate compute, databases, storage, IOPS, Internet and cross-zone/region traffic, load balancers/NAT, logs/metrics, backups, non-production environments, third-party services, and operational staffing.

~~~text
Projected monthly cost
  = compute + data + networking + observability + backup/DR
  + integration services + headroom for load variance
~~~

This is a cost-categorization model, not a cloud pricing calculator. Actual prices vary by region, configuration, usage, discount terms, and per-service billing models. Estimate at least three scenarios: **baseline load**, **expected peak**, and **above-forecast growth**. Tag/label by environment and owning team; track cost per successful transaction once reliable data is available.

An example trade-off: keeping two application instances always running may have a higher baseline cost than aggressive scaling, yet may fit better when steady latency and single-zone redundancy are required. Final decisions must rest on load-test results and cost models, not slogans like “serverless is always cheap” or “VMs are always fast.”

## 9. Stage 8: Well-Architected Architecture Review

Well-Architected is a framework of questions and practices to systematically examine workloads. In AWS's approach, the framework has the **six pillars** below; other platforms offer similar review frameworks though terminology and supporting services may differ.

| Pillar | Evidence-Backed Question to Answer | Signs Improvement Is Needed |
| --- | --- | --- |
| Operational Excellence | Are there runbooks, CI/CD, rollbacks, incident reviews, and controlled changes? | Manual deploys; unclear who responds to alerts |
| Security | Is access least-privilege, data protected, audited, and vulnerability-managed? | Secrets in source code; unintentionally public resources |
| Reliability | Have component failures, backup restores, failovers, and RTO/RPO been tested? | Single points of failure; backups never restore-tested |
| Performance Efficiency | Are load, p95, and bottlenecks measured, with data-driven sizing? | Intuition-based sizing; no load testing |
| Cost Optimization | Are there budgets, cost ownership, forecasts, and waste detection? | Unknown drivers behind rising bills |
| Sustainability | Are idle resources reduced, efficiency tuned, and data lifecycles enforced? | Resources left always-on unused; data retained indefinitely |

### A Repeatable Review Process

**Step 1 — Scope the workload.** Define the business journeys under review, environment, region, datasets, dependencies, SLOs, and owners. Do not review “the whole company” with vague generic answers.

**Step 2 — Gather evidence.** Use live architecture diagrams, IaC configs, measurements, dashboards, restore/chaos test results, deploy logs, permission reports, and billing reports. Distinguish **implemented**, **tested**, and **planned**.

**Step 3 — Interview across the six pillars.** For each question, record answers, evidence, uncertainty, and consequences if assumptions fail. For instance, “automated backups exist” is evidence of backup *creation*; confirming recovery requires restore test results and completion times.

**Step 4 — Rank risks.** Prioritize by business impact, likelihood, exposure, and remediation effort. Do not use a single aggregate score to hide critical security flaws or data risks.

**Step 5 — Create owned actions.** Each finding must state current state, target state, remediation plan, owner, deadline, and acceptance criteria. For residual risks accepted intentionally, record who approved them and when to revisit.

**Step 6 — Re-review after changes.** Conduct reviews after major architectural changes, severe incidents, scale shifts, or on an appropriate cadence; compare actual metrics against initial goals.

Example findings log table:

| Finding | Evidence | Impact | Priority Action | Completion Criteria |
| --- | --- | --- | --- | --- |
| Backups never restore-tested | Backup schedule exists; no restore record | May miss RTO/RPO targets | Run restore drill in an isolated environment | Accurate data restored; measured RTO/RPO meets targets |
| App runs in a single zone | Deployment diagram and config | Zone outage could halt bookings | Deploy multi-zone and test load failover | Disconnecting one zone still meets agreed service levels |
| Queue lacks backlog alerts | Dashboard missing queue age and DLQ | Notifications could suffer prolonged delays | Add metrics, alerts, and runbook | Alerts trigger accurately during queue-congestion test |
| Production deploy permissions not separated | Current IAM policies | Risk of accidental modification/deletion | Enforce least privilege and auditing | Permission review and tests of allowed/denied actions |

The review framework helps **surface and prioritize trade-offs**, not certify that an architecture has “zero risk.” A small workload may consciously accept certain controlled risks to focus on business value, provided they are explicitly documented.

## 10. Stage 9: Prove the Architecture Through Experimentation

Once the design takes shape, run a **proof of concept (PoC)** or minimal vertical slice targeting the highest-risk assumptions. You do not need to build every component at once; choose experiments capable of reversing architectural decisions.

For the booking example:

1. **Load test:** exercise schedule reads, booking creation, and status updates at average, peak, and 2x peak load; measure p95, error rates, DB saturation, and estimated cost.
2. **Correctness test:** send multiple competing requests for the same slot; verify constraints/transactions block double-booking.
3. **Async processing test:** cut off the email provider, redeliver messages, crash workers; verify bookings stay intact and unwanted duplicate notifications are prevented.
4. **Fault-tolerance test:** terminate a simulated instance/zone within allowed scope; measure detection time, failover, and SLO impact.
5. **Recovery test:** restore the DB from backup/PITR under realistic conditions; record data loss and restore duration against RPO/RTO.
6. **Security test:** verify cross-account access, workload permissions, secrets, public exposure, and audit traceability.
7. **Rollback test:** release a controlled change and revert to a safe version, including backward-compatible schema changes.

Record results in the format **assumption → experiment → measurement → conclusion → decision**. If targets are missed, adjust assumptions or design and re-measure. For example, p95 breaches may stem from queries and missing indexes before instance counts; adding compute does not always fix the root cause.

### Architecture Decision Record (ADR) Template

ADRs capture context and rationale so future engineers understand the trade-offs:

~~~yaml
id: ADR-001
title: Use managed relational database for appointment bookings
status: accepted
context:
  - Must prevent double-booking of time slots
  - Small ops team needing controlled backups and failover
decision: Select managed relational database with transactions and unique constraints
alternatives:
  - Self-manage database on VMs
  - NoSQL combined with custom conflict-control mechanisms
consequences:
  positive: Lower ops toil, clear transactional semantics
  tradeoff: Baseline cost and dependency on managed service
validation: Test concurrent bookings, failover, restore, and load tests
review_when: Write load grows sharply or data requirements change
~~~

This is a **decision documentation template**, not a deployment configuration. Selecting a managed database is only validated once testing confirms it meets specific transaction, performance, and recovery requirements.

## 11. Minimum Architecture Dossier Before Production Launch

A design is ready for handover and review when it at least answers the following areas:

| Document / Evidence | Required Content |
| --- | --- |
| Context & data flow diagrams | Actors, external dependencies, sensitive data, ingress/egress points |
| Component & deployment diagrams | API, worker, database, queue, storage, network segments, zones, communication paths |
| NFR/SLO list | Metrics, measurement formulas, target thresholds, conditions, and owners |
| ADRs | Key choices, alternatives, rationale, consequences, revisit triggers |
| Security model | Trust boundaries, IAM, secrets, encryption, auditing, access controls |
| HA/DR plan | Failure points, backups, RTO/RPO, recovery scenarios, and drill results |
| Operations plan | CI/CD, IaC, alerts, runbooks, rollbacks, on-call owners, and response procedures |
| Cost estimate | Baseline/peak load, pricing assumptions, network/log/backup costs, alerts |
| Well-Architected report | Findings, evidence, priorities, owners, target dates |

You do not need ten different tools to assemble this dossier. Diagrams, concise docs, and versioned configurations stored in the same repository can suffice for a small team, provided the information stays current and verified.

## 12. Practice Exercise: Design and Review a Workload Yourself

**Prompt:** You are tasked with designing v1 of the booking application above, requiring 200 RPS peak, 99.9%/month success SLO, read API p95 under 300 ms, 60-minute RTO, and 15-minute RPO; booking data must prevent overlaps; notifications run in the background. Treat these numbers as assumed requirements to confirm with the product owner.

**Required deliverables:**

1. Draw context and deployment diagrams clearly showing public/private networks, API, database, queue, worker, object storage, and notification provider connection points.
2. Explain why you chose the compute and database models; state at least **one alternative** and the conditions that would cause you to switch decisions.
3. Identify three critical failure points, their impact on the booking flow, and how to detect/recover from them.
4. Design tests proving double-booking prevention, safe retries, single-instance fault tolerance, and data recovery within RPO/RTO.
5. Estimate cost categories across three load scenarios; define primary operational metrics and alerts.
6. Review across all six Well-Architected pillars; record at least one evidence-backed finding and verifiable action item per pillar.

**Self-assessment criteria:** You can explain *which requirement each component serves*, *what happens when it fails*, *how you measure whether the design meets targets*, and *what alternative could replace it if assumptions change*. If any of those four questions remains unanswered, the architecture still holds an unresolved decision.

## 13. Common Mistakes to Avoid

- **Starting from service names:** easily leads to complex architectures lacking clear SLOs, security, and cost targets.
- **Equating multiple replicas with full-system fault tolerance:** databases, networks, session state, or external dependencies can still act as single points of failure.
- **Equating replication with backups:** logic bugs, accidental deletions, or ransomware can propagate to synchronous replicas.
- **Designing scale solely by adding instances:** databases, connection pools, quotas, queues, and downstream services can become bottlenecks.
- **Using microservices before clear boundaries exist:** increases network chatter and operational overhead before delivering real independent benefits.
- **Reviewing diagrams only on paper:** without load tests, restore tests, or failure drills, evidence for commitments is lacking.
- **Treating cost as an afterthought:** network traffic, logs, backups, and operating models can directly dictate architectural choices.
- **Reviewing once and forgetting:** shifting workloads, traffic, and configurations quickly invalidate old conclusions.

Cloud architecture is a chain of conditional decisions. Start from business goals, quantify quality, build the simplest option that meets requirements, document trade-offs, test high-risk assumptions, and use Well-Architected reviews periodically. The value of this roadmap lies in being able to **explain, measure, and adapt** the architecture to operational reality.
