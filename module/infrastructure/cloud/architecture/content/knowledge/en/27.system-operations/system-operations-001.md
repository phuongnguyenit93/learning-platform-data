# Service Ownership and On-Call Operating Models

> **Chapter:** System Operations  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business requirements to network, compute, data, and deployment model selection; balancing reliability, security, scalability, cost, and operations with a Well-Architected mindset.

## Learning Objectives

After this lesson, you will be able to:

1. Explain service ownership and why every service needs a clearly accountable team throughout its lifecycle.
2. Distinguish the responsibilities of the service owner, engineering team, platform team, operations, security, product owner, and incident commander.
3. Design an on-call operating model aligned with service criticality, SLOs, team size, and support capacity.
4. Build primary/secondary on-call rotations, escalation rules, handovers, and after-hours support mechanisms.
5. Connect ownership with SLOs, error budgets, observability, runbooks, deployment, and change management.
6. Organize incident response with clear roles and communication channels; transition from emergency mitigation to follow-up and improvement.
7. Evaluate risks related to on-call overload, single-person dependencies, alert fatigue, and insufficient recovery capability.
8. Apply RACI, service catalogs, ownership metadata, and hands-on exercises to design a verifiable operating model.

## 1. Why Define Service Ownership?

A cloud service may be built by multiple teams: product defines the experience, backend develops the API, platform provides the cluster and pipelines, the data team manages the database, security builds policies, and operations monitors the system. When everything runs smoothly, responsibility boundaries may remain blurry. When an incident strikes in the middle of the night, these questions become urgent:

- Who receives the alert and determines the blast radius?
- Who has permission to roll back the release that was just deployed?
- Who understands the business flow and knows which transactions might be lost?
- Who owns the database, queue, certificates, secrets, and dependencies?
- Who decides to degrade features, shift traffic, or trigger DR?
- Who communicates with customers and business stakeholders?
- After recovery, who is responsible for addressing the root cause and preventing recurrence?

Without agreed-upon answers, incidents easily bounce between teams, with each team only checking its own piece and no one taking accountability until the service recovers.

**Service ownership** designates a team/unit accountable for the health, behavior, and operational outcomes of a service. Ownership does not mean one person must do everything themselves. It means there is an owner responsible for coordinating, keeping documentation and operational readiness intact, and knowing when to engage other specialist teams.

### 1.1. Ownership Across the Lifecycle

Responsibility does not end when code is merged or deployed to production. A service requires ownership across all phases:

| Phase | Key Responsibilities |
|---|---|
| Design | Define SLOs, dependencies, threat model, failure modes, and operational plan |
| Build | Testing, instrumentation, security controls, migrations, and automation |
| Release | Release plan, canary, rollback, compatibility, and change communication |
| Run | Monitor SLIs, respond to alerts, handle incidents, capacity, backups, and support |
| Improve | Post-incident reviews, toil reduction, fixing recurring defects, and improving reliability |
| Retire | Migrate consumers, archive/delete data, revoke permissions, disable alerts and infrastructure |

Ownership must be handed over deliberately when teams change, a service moves to a platform, or a system is split/decomposed. Simply changing the team name in a catalog without transferring runbooks, permissions, dashboards, and on-call rotations creates an accountability gap.

### 1.2. Distinguishing Owner, Operator, and Contributor

- **Service owner:** the team with overall accountability for the service, its SLOs, risks, operations, and reliability roadmap.
- **Operator/on-call responder:** the person currently on shift who receives alerts and coordinates the initial response steps.
- **Contributor:** a team providing a dependency or specialized capability such as database, network, identity, security, or platform.
- **Business/product owner:** the person who decides business priorities, customer impact, and trade-offs between service availability and risk.

One person may hold multiple roles in a small team, but during a major incident, conflicting or high-load roles should be separated. For example, the person debugging the database should not simultaneously write all customer communications and coordinate the entire incident.

## 2. Defining Service Boundaries and Owners

### 2.1. Ownership Must Be Tied to a Service Boundary

A service boundary must be clear enough to know:

- Which APIs/events/jobs belong to the service.
- Which data is the source of truth and who is permitted to change the schema.
- Which infrastructure, databases, queues, caches, and cloud accounts are managed.
- Which dependencies belong to other teams and what their support agreements are.
- Which SLIs/SLOs measure the service's quality.
- Which alerts are routed to the on-call team.
- Where the release, rollback, backup/restore, and DR procedures reside.

If an alert only says “platform slow” without service, endpoint, region, tenant cohort, and owner, the responder wastes time determining the scope. Both the catalog and telemetry should use the same service identifier.

### 2.2. Minimum Service Catalog

A catalog entry can include:

| Field | Content |
|---|---|
| service_id / name | Stable identifier of the service |
| description | Business purpose and capabilities |
| owning_team | Primary accountable team |
| technical_owner | Technical point of contact, escalation |
| product_owner | Point of contact for business priority decisions |
| tier / criticality | Criticality level and support scope |
| SLO / SLA reference | Quality targets and related agreements |
| dependencies | Services, databases, queues, providers, and owners |
| repo / pipeline | Source code, build, release, IaC |
| dashboards / alerts | Links to dashboards, alerts, and telemetry |
| runbooks | Operational, rollback, restore, and DR procedures |
| data classification | Data classification and security requirements |
| support model | Support hours, on-call, escalation path |
| lifecycle | Proposed, active, maintenance, deprecated, retired |

The catalog requires an owner to review it periodically. A complete record with broken links, outdated on-call schedules, or renamed services still creates operational risk. Automatically pulling metadata from repositories/deployments can reduce drift, but accountability and business fields still require human confirmation.

### 2.3. One Service, One Accountable Owner

Multiple teams may contribute, but one team must be accountable for end-to-end outcomes. If ownership is split ambiguously, during an incident team A may assume the issue belongs to B and vice versa.

For shared capabilities such as identity, observability, or a data platform, a platform team owns the underlying service; product teams remain responsible for how they integrate, configure, and consume that dependency. “Using the platform” does not eliminate responsibility for bugs in code or policies authored by the service team.

## 3. Defining Responsibilities: RACI and Support Matrices

### 3.1. What Is RACI?

RACI is a way to clarify who executes work and who holds final accountability:

- **R — Responsible:** the person/team doing the work.
- **A — Accountable:** the person/team with final accountability and decision-making authority; there should be one clear A per activity.
- **C — Consulted:** people/teams consulted before a decision is made.
- **I — Informed:** people/teams who need to be notified.

RACI does not replace incident command. It describes ongoing responsibilities; during an incident, the incident commander coordinates according to trained roles.

### 3.2. Example RACI for a Booking Service

| Activity | Service team | Platform | Security | Product | Operations/Incident lead |
|---|---|---|---|---|---|
| API and business logic design | A/R | C | C | C | I |
| Service SLOs and error budget | R | C | I | A | C |
| Underlying cluster/network | C | A/R | C | I | C |
| IAM policies and threat model | R | C | A | I | C |
| Application release | A/R | C | C | I | I |
| Receiving service alerts | A/R | C | C | I | R on schedule |
| Customer-impacting incident | R | C | C | A for business impact | A/R for incident coordination |
| Database recovery | R with data owner | C | C | I | Coordination |
| Customer communication | C | I | C | A/R | C |
| Post-incident actions | A/R for service fixes | R for platform fixes | R for security fixes | C | Track actions |

This illustrative matrix must be adapted to the organization. If an “operations” role does not exist as a separate team, responsibility may belong to the service's on-call engineer. Avoid having multiple A's for one activity without defining decision-making authority when disagreements arise.

### 3.3. Dependency Ownership

A service depends on a database platform, message broker, identity, and network. The operational contract between consumer and provider must define:

- The dependency owner and support escalation channel.
- The dependency's SLO/availability or support window.
- Quota limits, timeouts, retries, and behavior when the dependency fails.
- Dashboards/metrics visible to the consumer.
- Breaking change processes and maintenance windows.
- Which party investigates first when the fault location is unclear.

A service team does not need database admin privileges to own an API. However, the team needs sufficient telemetry and diagnostic permissions; if every investigation requires help from a single individual, that is an operational risk.

## 4. Designing an On-Call Operating Model

### 4.1. What Is On-Call?

**On-call** is a mechanism for assigning someone to be available to respond when the system needs support outside regular business hours or during a defined operational shift. Being on call does not mean continuously operating the system; the goal is to receive critical signals, assess severity accurately, and route incidents to those capable of resolving them.

An on-call model must define:

- Which services are covered 24/7, and which only during business hours?
- Which alerts page the on-call responder, and which create tickets for the next business day?
- Who is primary, who is secondary, and who is the escalation manager?
- What are the alert acknowledgment window and escalation thresholds?
- Which paging channels, phone lines, chat rooms, and incident bridges are used?
- To what extent is the responder authorized to roll back, disable features, fail over, or throttle traffic?
- How are shift handovers, vacation coverage, and unreachable responders handled?

The on-call level must match business criticality and service commitments. Do not declare 24/7 support without the corresponding people, permissions, processes, and dependency coverage.

### 4.2. Common On-Call Models

| Model | Organization | Best Fit | Trade-offs |
|---|---|---|---|
| **Business-hours support** | One team handles requests during work hours | Internal or low-criticality systems | After-hours incidents may wait until the next shift |
| **Follow-the-sun** | Teams across multiple time zones hand off shifts | Multi-region organizations aiming to reduce night shifts | Complex handover and runbook standardization |
| **Primary/secondary rotation** | Primary receives alerts, secondary assists on escalation | Small/medium service teams | Requires enough people and a fair schedule |
| **Central NOC/SRE + service escalation** | NOC/SRE handles initial monitoring, engages service owner as needed | Many services, standardized operations | Easily creates a relay layer if NOC lacks context |
| **Dedicated operations team** | Dedicated team handles on-call and operations | Large workloads, stable procedures | Can create a gap between build and run |
| **Embedded service ownership** | The team that builds the service also runs it on call | Product teams with end-to-end ownership | Requires investment in operational capability and on-call load limits |

Follow-the-sun is not simply having people in three time zones. It requires cleanly transferring context, tickets, incident timelines, permissions, and responsibilities. If the incoming team does not know the current state and ongoing actions, shift changes can cause secondary failures.

### 4.3. Primary/Secondary Diagram

~~~mermaid
flowchart TD
    ALERT[Monitoring / Paging Alert] --> PAGE[On-call Scheduler]
    PAGE --> P[Primary Responder]
    P --> ACK{Acknowledged in target window?}
    ACK -->|Yes| TRIAGE[Triage and classify]
    ACK -->|No| S[Secondary Responder]
    S --> ACK2{Acknowledged?}
    ACK2 -->|Yes| TRIAGE
    ACK2 -->|No| M[On-call Manager / Escalation]
    M --> TRIAGE
    TRIAGE -->|Need specialist| SME[Service / Platform / Data SME]
    TRIAGE -->|Major incident| IC[Incident Commander]
    SME --> RESOLVE[Mitigate and recover]
    IC --> RESOLVE
    RESOLVE --> CLOSE[Validate, communicate and hand off follow-up]
~~~

This diagram is a reference flow. Acknowledgment timeouts, paging retries, and escalation paths should be based on criticality, support agreements, and actual staffing capacity.

## 5. Defining On-Call Tiers and Service Scope

### 5.1. Tiering Service Criticality

A reference classification:

| Tier | Characteristics | Applicable Support |
|---|---|---|
| Tier 0 / Critical | Outage causes wide impact, core transactions, or safety risk | 24/7 primary/secondary, major incident process, DR |
| Tier 1 / High | Important business capability with limited workarounds | 24/7 or extended hours per SLO |
| Tier 2 / Standard | Limited impact, deferrable | Business-hours/on-call best effort |
| Tier 3 / Internal | Internal tools or experimental workloads | Ticket/office-hours, no paging unless special risk applies |

Tiering does not reflect revenue alone. Consider the number of affected users, data and compliance, downstream dependencies, availability of workarounds, outage duration, and safety consequences.

### 5.2. Alert Severity and Escalation

| Level | Example | Response |
|---|---|---|
| SEV1 | Core service down, data loss, or widespread impact | Page immediately, incident commander, bridge, periodic updates |
| SEV2 | Severe degradation, large customer cohort affected, fast SLO burn | Page primary, engage specialists, consider incident lead |
| SEV3 | Error with workaround, limited scope/impact | Ticket or page per support policy |
| SEV4 | Informational warning, minor issue with no service impact | Backlog, follow up during business hours |

Severity names and criteria must be consistent across the organization. Do not use SEV1 for every alert; if everything is urgent, responders lose the ability to prioritize.

### 5.3. Acknowledge, Triage, and Resolution Are Three Distinct Milestones

- **Acknowledge:** confirming someone has taken ownership of the alert.
- **Triage:** determining scope, severity, symptoms, owner, and next actions.
- **Mitigation/recovery:** restoring service or reducing impact.
- **Resolution:** addressing the root cause or confirming a stable permanent fix.
- **Follow-up:** actions to prevent recurrence, improve detection, or reduce recovery time.

Meeting the acknowledgment target does not mean the incident is resolved. Dashboards should distinguish time to detect, acknowledge, triage, mitigate, and recover.

## 6. Building a Sustainable On-Call Schedule

### 6.1. Scheduling Principles

- Distribute shifts fairly by skill, time zone, experience, and support capacity.
- Ensure primary and secondary responders are genuinely available, not scheduled during vacations or unreachable periods.
- Avoid having one person on call for too many consecutive days/weeks or covering multiple services simultaneously without limits.
- Provide compensatory time off and reduce daytime workload after a night with incidents.
- Maintain backup coverage when a responder is sick, loses connectivity, or cannot continue a shift.
- Define escalation when a service owner does not respond or no specialist is available.
- Verify access permissions, authentication devices, VPN, and paging tools before starting a shift.

The on-call schedule is part of system design, not administrative overhead. If only one engineer knows how to restore the database, the service has a human single point of failure.

### 6.2. Weekly Rotation Example

| Week | Primary | Secondary | Escalation manager |
|---|---|---|---|
| 1 | Engineer A | Engineer B | Engineering Manager |
| 2 | Engineer B | Engineer C | Engineering Manager |
| 3 | Engineer C | Engineer A | Engineering Manager |
| 4 | Engineer A | Engineer C | Engineering Manager |

The table above only illustrates rotation for a small team and is not a recommended schedule for all teams. You must consider the number of qualified engineers, labor laws/internal policies, holidays, and actual incident load. If a team does not have enough people for safe on-call coverage, you must reduce support scope, increase automation, or establish another support arrangement; you cannot solve it by overloading a single individual.

### 6.3. Shift Handover

A handover should record:

- Open incidents, severity, and customer impact.
- What has been tried, results, and remaining hypotheses.
- Ongoing actions, unfinished commands/jobs, and risks of stopping them.
- Contacts, bridges/tickets, incident commander, and next update time.
- Key dashboards/traces/queries and timestamps.
- Approved decisions, active rollbacks/mitigations.
- Muted/silenced alerts and their expiration times.

Do not hand over a shift with a single phrase like “currently investigating.” The incoming responder needs enough context to continue within minutes without repeating the entire investigation.

### 6.4. Post-Shift Review

Track page volume, after-hours incident count, sleep disruption time, escalation count, and toil. If a service repeatedly wakes responders for issues that do not require immediate action, fix the alerting or reliability rather than accepting it as the nature of the job.

## 7. Alerting and Observability for On-Call Responders

### 7.1. Page on Symptoms and Customer Impact

Alerts should answer “how are users or the business being affected?” rather than just “CPU high.” High CPU can be a useful signal, but page only when tied to meaningful saturation/latency/error conditions.

A good alert typically includes:

- Service, environment, region, tenant cohort, and endpoint.
- Severity, violated SLI/SLO, or burn rate.
- Start time, duration, and trend.
- Links to dashboards, traces, log queries, and runbooks.
- Owner/on-call schedule and escalation policy.
- Safe first action, stop conditions, and rollback steps if applicable.

### 7.2. Golden Signals and SLIs

Commonly useful metric categories:

| Category | Examples | Question |
|---|---|---|
| Latency | p50/p95/p99, queue age | How long are users waiting? |
| Traffic | RPS, concurrent requests, messages/s | Is load rising or the pattern changing? |
| Errors | 5xx, timeouts, failed jobs, business rejections | Are requests failing or business logic misfiring? |
| Saturation | CPU, memory, DB connections, IOPS, queue capacity | Do dependencies still have headroom? |
| Freshness | Replication lag, data age, last successful job | Is data sufficiently up to date? |
| Availability | Successful eligible requests / total eligible requests | Is the service fulfilling requests? |
| Business outcome | Booking completed, payment success, duplicate booking | Are users completing the business flow? |

Metrics should distinguish system errors from valid business rejections. For example, a booking rejected because a slot is full is not necessarily an availability failure; however, a timeout during booking confirmation is a different symptom.

### 7.3. Alert Fatigue

Alert fatigue occurs when high alert volume, repeated alerts, or non-actionable alerts reduce responder attentiveness. Ways to reduce it:

- Page only when an action must be taken during the on-call shift.
- Use tickets/notifications for non-urgent issues.
- Group alerts by incident/root symptom.
- Configure deduplication, conditional suppression, and maintenance windows.
- Base thresholds on SLOs, baselines, and sustained durations.
- Review non-actionable pages and delete/adjust the metrics.
- Require an owner and expiration time for silenced alerts; never mute indefinitely just to keep dashboards green.

### 7.4. Runbooks Must Live Near Alerts

A runbook should contain:

1. Symptoms and criteria for identifying the incident.
2. Scope/impact and initial safety checks.
3. Dashboards, logs, traces, and queries to open.
4. Read-only commands or checks first; state-changing actions afterward.
5. Escalation conditions and when to stop.
6. How to mitigate, roll back, or fail over along with associated risks.
7. How to verify recovery and data correctness.
8. Owner, dependency, and incident channel contacts.

Dangerous commands must specify required permissions, impact, preconditions, approvals, and verification steps. Never include secrets, tokens, or personal data in runbooks.

## 8. Incident Response: Roles and Coordination Flow

### 8.1. Roles in a Major Incident

| Role | Responsibilities |
|---|---|
| Incident Commander (IC) | Coordinate, set objectives, assign tasks, decide escalations, and maintain timeline |
| Operations/Technical Lead | Coordinate technical diagnosis and recovery |
| Service Owner | Provide architecture context, SLOs, dependencies, and decisions within service scope |
| Communications Lead | Send internal/customer updates at the agreed cadence and using standard templates |
| Scribe | Record timeline, decisions, actions, and evidence |
| Subject Matter Expert (SME) | Provide deep support for database, network, security, or cloud provider issues |
| Business/Product Owner | Assess business impact, select workarounds, and prioritize recovery |

In small incidents, one person may cover multiple roles. In large incidents, separate the IC from hands-on responders fixing the system to avoid losing the big-picture view.

### 8.2. Incident Handling Flow

~~~mermaid
flowchart TD
    A[Alert or customer report] --> B[On-call acknowledge]
    B --> C[Triage: scope, severity, service]
    C --> D{Major incident?}
    D -->|No| E[Service responder investigates]
    D -->|Yes| F[Assign Incident Commander]
    F --> G[Create incident channel and roles]
    G --> H[Set objective and update cadence]
    E --> I[Mitigate / recover]
    H --> I
    I --> J[Validate user and business outcomes]
    J --> K{Stable?}
    K -->|No| I
    K -->|Yes| L[Communicate recovery and close]
    L --> M[Post-incident review and actions]
~~~

At every stage, information should be shared in a single standard incident channel. Avoid fragmented coordination over DMs that leaves others unaware of decisions made.

### 8.3. Update Cadence

Major incidents need a consistent update cadence, such as every 15 or 30 minutes depending on severity. Updates should state:

- What is happening and the confirmed scope of impact.
- Which features/regions/tenants are affected; what still works.
- Whether a workaround is available.
- Actions currently underway and the next update time.
- Explicit statement of unknowns; do not speculate on an ETA without evidence.

Send a recovery notice only after the service owner verifies SLIs and required business flows. A single green dashboard is not enough if queue backlogs are still growing or data has not been reconciled.

## 9. Connecting Service Ownership to SLOs and Error Budgets

### 9.1. SLI, SLO, and SLA

- **SLI (Service Level Indicator):** a quality measurement, such as successful request ratio or p95 latency.
- **SLO (Service Level Objective):** an internal target for an SLI over a defined window.
- **SLA (Service Level Agreement):** a commitment to customers/partners, potentially with terms/credits.

The service owner is responsible for establishing, tracking, and improving SLOs together with product/business. SLOs must be measurable with reliable telemetry; clearly define eligible requests, errors, windows, and exclusions.

Hypothetical example: 99.9% of eligible booking requests must succeed over a 30-day rolling window, with p95 latency under 300 ms at defined load. Concrete targets must be validated against traffic, regions, and business needs.

### 9.2. Error Budget

The error budget is the tolerable amount of errors/downtime corresponding to the SLO. If the availability SLO is 99.9% over 30 days, the theoretical time budget is approximately:

~~~text
30 days × 24 hours × 60 minutes × (1 - 0.999)
= 43.2 minutes
~~~

This is an illustrative conversion when the SLI is time-based availability; for request-based SLIs, the error budget is calculated from failed requests relative to total eligible requests.

When the budget burns quickly:

- Prioritize reliability work and reduce release risk.
- Temporarily pause high-risk feature rollouts per agreed policy.
- Investigate recurring errors, noisy neighbors, and dependencies.
- Notify the product owner to reprioritize the backlog.

An error budget is not a quota of errors you are allowed to cause. It is a tool to balance feature velocity and stability; decisions to pause releases require clear authority and criteria.

### 9.3. Dependency SLO Ownership

A service team needs to define end-to-end SLOs but does not necessarily own every dependency. For example, Booking API has a 99.9% SLO and depends on a 99.95% database SLO, identity, and a payment provider. The service owner must:

- Measure latency/errors at the point observed by users.
- Know the error budget of each dependency.
- Implement sensible timeouts, retries, circuit breakers, and fallbacks.
- Avoid mechanically summing dependency availability when redundancy or failure correlation exists.
- Align escalation paths with dependency providers/owners.

## 10. Releases, Changes, and Operational Permissions

### 10.1. Who Has Permission to Change Production?

Ownership must define operational permissions:

- Who can deploy, roll back, and toggle feature flags?
- Who can modify schemas, IAM, networks, keys, and firewalls?
- Who can fail over a database or shift regional traffic?
- Who can delete data, queues, or resources?
- Which actions require dual approval or an incident commander?

Do not grant broad admin privileges to all on-call responders for convenience. Use short-lived roles, just-in-time access, auditing, and policy-approved break-glass access.

### 10.2. Risk-Based Change Management

Every production change should specify:

- Scope, owner, version, dependencies, and affected customers.
- Preconditions, tests, canary strategy, and success metrics.
- Rollback/roll-forward plan and trigger conditions.
- Database/schema backward compatibility.
- Monitoring, assigned observer, and completion criteria.
- Additional approvals if the change is high risk.

Not every deploy needs a manual change-approval meeting. Pipelines with policy-as-code, automated tests, and progressive delivery can reduce risk and toil; destructive changes or changes affecting data/permissions require stricter controls.

### 10.3. Run Ownership and Build Ownership

When the development team does not directly staff on-call, clear agreements are needed on:

- Who handles the initial alert and who has permission to change code/config?
- Within what timeframe does the service owner join an escalation?
- Can platform safely roll back infrastructure without corrupting application state?
- Who handles migrations, data fixes, and consumer compatibility?
- What after-hours SLAs apply to vendor/managed service support?

The build-and-run model shortens the feedback loop but requires the team to have time, skills, and tooling. Handing off to dedicated operations requires documentation, automation, and acceptance testing; a handoff cannot transfer accountability without transferring capability.

## 11. Post-Incident Reviews and Continuous Improvement

### 11.1. Systems-Focused Reviews

A post-incident review (PIR) should examine:

- Timeline and actual impact.
- Triggers, contributing factors, and conditions that allowed the failure to spread.
- Available signals, missing signals, and time of detection.
- Decisions, mitigations, and what worked or did not work.
- Gaps in ownership, permissions, runbooks, or dependency contracts.
- Actions to reduce likelihood, shrink blast radius, detect earlier, and recover faster.

Reviews are not meant to assign blame to individuals. If responders had to make choices with incomplete information and limited tools, improve the system so future decisions are safer.

### 11.2. Action Categories

| Action Type | Example | Appropriate Owner |
|---|---|---|
| Prevent | Fix race condition, quota, validation, or unsafe config | Service/platform owner |
| Detect | Add SLI, symptom-based alert, data integrity check | Service/SRE |
| Mitigate | Rate limit, feature flag, isolation, circuit breaker | Service/platform |
| Recover | Restore automation, rollback, failover/runbook | Service/data/platform |
| Learn | Update training, architecture decisions, dependency map | Service owner/engineering manager |

Actions must have an owner, priority, due date, acceptance criteria, and status. “Improve monitoring” is too vague; “alert when oldest queue age exceeds 5 minutes over 3 windows and include runbook link” is verifiable.

### 11.3. Closing the Loop

The service owner is responsible for tracking service-specific actions and coordinating cross-team actions. An engineering manager or reliability review can inspect overdue actions and accepted risks. A PIR only delivers value when changes are implemented and their impact is measured afterward.

## 12. Managing Toil and On-Call Team Capacity

### 12.1. What Is Toil?

Toil is repetitive, manual, predictable operational work that creates little lasting value—for example, manually restarting workers every night, handling the same false-positive alert, repeatedly issuing credentials, or running unautomated reconciliation scripts.

Track:

- Pages per shift, non-actionable pages, and false positives.
- Repeated handling time by incident category.
- Percentage of tickets requiring a single specialist.
- Recurring manual tasks and the percentage automated.
- Outdated runbooks or tasks impossible to perform with current roles.

### 12.2. Order of Toil Reduction

1. Delete unhelpful alerts and fix thresholds/deduplication.
2. Clarify symptoms, dashboards, runbooks, and escalations.
3. Automate read-only/diagnostic tasks.
4. Automate safe mitigations with guardrails and rollback.
5. Fix the root causes creating repetitive work.
6. Re-measure page volume, MTTR, and time spent on reliability work.

Do not automate a dangerous operation simply because it happens often. Production automation requires idempotency, scoped permissions, auditing, rate limits, appropriate dry-runs or confirmations, and safe stop conditions.

### 12.3. On-Call Team Health

Overly dense shifts cause fatigue, impair judgment, and increase errors. Organizations must review page volume alongside actual disruption, ensure compensatory rest, allow legitimate shift swaps/declines, and maintain adequate backup staffing. If volume exceeds team capacity, the fix is to reduce errors, reduce alerts, add skilled staff, or change the support model—never normalize burnout.

## 13. Operational Architecture: Ownership in the Cloud

### 13.1. Mapping Ownership to Resources

Cloud resources should be tagged/labeled by service, team, environment, cost center, data classification, and owner. This enables:

- Identifying who manages a resource during a security alert.
- Querying costs by service/team.
- Assessing blast radius when modifying a shared VPC/database/cluster.
- Distinguishing production from experimental resources.
- Detecting orphaned resources when a team or service is retired.

Tags are not an authorization mechanism; IAM/policies must still enforce permissions. Never let missing tags block recovery of an incident-stricken service.

### 13.2. Shared Platforms and Paved Roads

A platform team can provide standard service templates, CI/CD, observability, secrets, networking, deployments, and runbooks. A paved road reduces burden on product teams but requires clear contracts:

- Which capabilities and support boundaries does the platform guarantee?
- Which configurations and code remain the product team's responsibility?
- During a platform outage, how do escalation and status communication work?
- Are there SLOs for platform APIs and service dependencies?
- How are exceptions granted and what is the timeline to return to standard?

Good self-service requires documentation, guardrails, and safe defaults—not merely a portal for provisioning resources.

### 13.3. Dependency Ownership Map

~~~mermaid
flowchart TB
    subgraph Product[Product service]
        API[Booking API]
        WORKER[Notification Worker]
        DB[(Booking Database)]
    end
    subgraph Platform[Platform capabilities]
        NET[Network / Ingress]
        OBS[Observability]
        IAM[Identity / Secrets]
        MQ[Message Broker]
    end
    API --> DB
    API --> MQ
    WORKER --> MQ
    API --> IAM
    WORKER --> IAM
    API --> NET
    WORKER --> NET
    API -. telemetry .-> OBS
    WORKER -. telemetry .-> OBS
    DB -. telemetry .-> OBS
    OWN1[Booking team owns API, worker and data contract]
    OWN2[Platform team owns shared capabilities and SLO]
    OWN1 -.-> API
    OWN2 -.-> NET
~~~

A dependency map should attach an owner and escalation contact to each node/edge. Diagrams do not replace the catalog; they help expose where ownership or support contracts are missing.

## 14. Process for Building a Service Ownership Model

A team can start with the following steps:

1. **Inventory:** list services, resources, data, dependencies, customers, and business owners.
2. **Set criticality:** evaluate impact, RTO/RPO, data sensitivity, and support requirements.
3. **Assign owner:** designate an owning team, technical owner, product owner, and backup.
4. **Define service contract:** SLO/SLI, dependencies, escalation, release, and support windows.
5. **Build operations kit:** dashboards, actionable alerts, runbooks, access roles, backup/restore, and DR.
6. **Design rota:** primary/secondary, escalation, coverage, handover, holidays, and backup staffing.
7. **Exercise:** simulate alerts, incidents, rollbacks, dependency failures, and restores.
8. **Measure:** page volume, MTTA, MTTR, SLOs, toil, action closure, and handover quality.
9. **Review:** periodically inspect owners, catalog, rota, support scope, and dependency contracts.
10. **Transition/retire:** hand over ownership or decommission the service along with data, permissions, and monitoring.

### 14.1. Service Ownership Record Template

~~~text
Service: booking-api
Owning team: Booking Platform Product Team
Technical owner: On-call Engineering Lead
Product owner: Booking Product Manager
Criticality: Tier 0
Support: 24x7 primary + secondary
SLO:
  - successful eligible requests: 99.9% / 30 days
  - p95 latency: < 300 ms at defined load
Primary dashboard: [service dashboard reference]
Runbook: [incident and recovery runbook reference]
Dependencies:
  - booking-db (Data Platform Team)
  - identity (Platform Team)
  - event-broker (Messaging Team)
Escalation:
  - Primary -> Secondary -> Incident Commander
  - DB issue -> Data Platform on-call
Review date: [date]
~~~

Items in square brackets are placeholders to be filled with real organizational links, not existing addresses.

### 14.2. Escalation Policy Template

| Condition | Action | Owner |
|---|---|---|
| SEV1/SEV2 alert | Page primary immediately | Scheduler |
| Primary does not acknowledge within target | Page secondary and notify manager | Scheduler |
| Dependency owned by another team | Page dependency on-call, retain service incident owner | Primary/IC |
| Widespread or growing impact | Assign IC and open incident bridge | Engineering manager/IC |
| Data/security risk present | Engage security/data owner per incident policy | IC |
| Recovered but backlog remains | Keep incident open for monitoring until backlog/invariants pass | Service owner |

Target times must be populated based on service tier and support policy. No single acknowledgment timeout fits every system.

## 15. Common Pitfalls

| Pitfall | Consequence | Remediation |
|---|---|---|
| No clear single owning team | Incidents bounce around, actions get dropped | Designate an accountable owner and catalog |
| Assigning a single individual as sole owner | Single point of failure, vacations break support | Team-level ownership, backups, and shared knowledge |
| Build team has no run responsibility | Releases cause bugs with no end-to-end owner | Clear build/run contract and escalation |
| NOC receives alerts without context | Repeated transfers, higher MTTR | Service catalog, runbooks, symptom-based alerts |
| Schedule lacks sufficient backup | Nobody answers pages when primary is unavailable | Primary/secondary rotation and escalation drills |
| Paging on every anomalous metric | Alert fatigue, real incidents missed | Page on user impact/SLO and review alerts |
| Insufficient permissions during on-call shift | Responder waits for an admin after hours | JIT access, role design, and break-glass drills |
| Verbal-only handovers | Repeated investigation, ongoing actions dropped | Incident logs and handover templates |
| Not measuring page volume/toil | Unclear whether on-call model is sustainable | Track pages, MTTA/MTTR, and after-hours load |
| Post-incident actions lack owner/deadline | Recurring failures | Concrete actions, acceptance criteria, and tracking |
| Overlapping platform/product ownership | Unclear who fixes issues at the boundary | RACI and dependency contracts |
| Declaring 24/7 support without coverage | Misaligned customer expectations and SLA risk | Match support scope to actual staffing |

## 16. Exercise: Designing Ownership and On-Call for a Booking Platform

**Scenario:** A booking SaaS includes a Booking API, Notification Worker, relational database, event broker, and analytics dashboard. Booking API handles core transactions; notifications can tolerate delay; analytics can recover the next day. There are three teams: Booking Product, Platform Engineering, and Data Platform. Alerts currently go to one shared chat channel with no service catalog or standard on-call schedule.

Propose an operating model:

1. **Service inventory:** separate services/capabilities, owners, dependencies, data classification, and criticality.
2. **RACI:** define accountable/responsible/consulted/informed for deploy, incident, database restore, security incident, customer communication, and post-incident actions.
3. **Support tier:** assign Tier 0/1/2; decide 24/7 vs business-hours support and justify by business impact.
4. **On-call rota:** design primary/secondary, escalation manager, vacation backup, and handover.
5. **Alert taxonomy:** define SEV1–SEV4, page vs ticket, acknowledge, triage, and escalation conditions.
6. **Observability/runbook:** choose SLIs for booking, queues, and analytics; create dashboards/alerts with clear owners and actions.
7. **Incident process:** assign IC, technical lead, communications lead, scribe, and SMEs; set update cadence.
8. **SLO/error budget:** propose hypothetical targets, calculate the error budget, and define policy when burn rate spikes.
9. **Access/release:** define JIT roles, break-glass, rollback permissions, failover, and schema changes.
10. **Sustainability:** measure page load, toil, after-hours interruption, MTTA/MTTR, and action closure.

### Sample Ownership Table

| Service/capability | Owning team | Tier | Support | Key SLIs |
|---|---|---|---|---|
| Booking API | Booking Product | 0 | 24x7 primary/secondary | Successful booking, p95 latency |
| Notification Worker | Booking Product | 1 | Extended hours or 24x7 per SLA | Oldest queue age, delivery success |
| Relational DB | Data Platform | 0 | 24x7 dependency escalation | Connections, transaction latency, replication lag |
| Event Broker | Platform Engineering | 1 | Platform on-call | Publish/consume errors, backlog |
| Analytics | Data Platform/Analytics owner | 2 | Business-hours | Freshness, job success, completeness |

### On-Call Readiness Checklist

| Check | Evidence |
|---|---|
| Primary and secondary assigned | Scheduler shows current and next shifts |
| Acknowledge/escalation works | Test page reaches primary then secondary |
| Safe permissions in place | JIT role and break-glass rehearsed |
| Dashboards/runbooks accessible | Working links pointing to the right environment |
| Dependency owners clear | Catalog lists contacts and escalation paths |
| Handover complete | Incident log template captures state and decisions |
| Communication mechanism ready | Channel, templates, communications owner |
| Post-incident process active | Action tracker includes owners/deadlines |

**Completion criteria:** Reviewers can identify who holds end-to-end accountability for each service, who receives pages, who holds decision/recovery authority, how escalation works, and whether the on-call model is sustainable for actual headcount. Unverified SLOs and response times must be marked as assumptions requiring validation.

## 17. Well-Architected Review

| Pillar | Ownership and On-Call Questions | Evidence |
|---|---|---|
| **Operational Excellence** | Does the service have an owner, catalog, runbooks, rota, handover, and PIRs? | Ownership record, escalation drill, action closure |
| **Security** | Are on-call permissions, break-glass, auditing, and access reviews properly scoped? | JIT access test, access logs, role reviews |
| **Reliability** | Are responders available with the skills/permissions to recover within SLO? | Paging drill, restore exercise, MTTA/MTTR |
| **Performance Efficiency** | Do alerts reflect latency/traffic/saturation and real workloads? | SLI dashboard, page quality, capacity reviews |
| **Cost Optimization** | Are on-call level, tooling, and toil proportional to criticality? | Cost per service, page volume, toil tracking |
| **Sustainability** | Is on-call workload sustainable, reducing interrupts and automating repetitive tasks? | After-hours load, rotation fairness, toil trends |

Good ownership accelerates decisions and actions, but it is not meant to dump every responsibility onto the on-call responder. The goal of the model is for services to operate through systems, processes, and shared knowledge rather than relying on one always-available individual.

## 18. Key Takeaways

- **Service ownership** is team-level accountability for a service's health and operational outcomes across its entire lifecycle.
- **Each service needs a clear accountable owner**, service catalog entry, dependency map, SLOs, dashboards, and runbooks.
- **RACI** clarifies who executes, who is ultimately accountable, who is consulted, and who must be informed.
- **An on-call model** must match criticality and staffing capacity; primary responders need secondary coverage, escalation, and handovers.
- **Alerts must be actionable:** prioritize symptoms/customer impact, SLOs, and saturation; reduce false positives and alert fatigue.
- **Incident response** requires an IC, technical lead, communications, scribe, and SMEs scaled to incident severity.
- **SLOs/error budgets** connect quality targets to release decisions and reliability work.
- **PIRs and toil reduction** turn incidents into improvements with owners, deadlines, and acceptance criteria.

Defining service ownership and on-call operating models transforms accountability from implicit understandings into a visible, testable, and improvable system. When owners, permissions, alerts, runbooks, and escalations are clear, organizations can respond more consistently, reduce recovery time, and maintain service quality without placing the entire burden on a few individuals.
