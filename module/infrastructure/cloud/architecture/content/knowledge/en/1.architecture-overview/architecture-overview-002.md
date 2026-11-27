# The Role of the Architect and Collaboration with Development, Security, and Operations

## 1. What Problems Does an Architect Solve?

Designing cloud application architecture does not start with the question “which cloud service should we use?”, but with **business requirements, constraints, and acceptable trade-offs**. An application may run on a server yet still fail to meet requirements for resilience, data security, scalability, cost, or long-term operability.

A **solution architect** is responsible for creating and maintaining the overarching technical picture: translating business goals into well-reasoned design decisions, aligning boundaries between components, and ensuring those decisions can be implemented, verified, and operated. In an organization, this function may be held by a dedicated architect, principal engineer, or tech lead; the job title alone does not dictate full authority.

For example, the requirement “customers must be able to complete bookings even during peak hours” leads to a chain of questions:

- Is “success” measured by valid request completion rate, response time, or zero double-bookings?
- What are normal and peak traffic volumes? How long can peaks last?
- How consistent must booking data be? What happens if the notification service fails?
- How quickly must the system recover, and what is the maximum allowable data loss?
- What are the budget, team capabilities, deployment regions, and data protection obligations?

Together with stakeholders, the architect turns these questions into measurable requirements, proposes options, articulates trade-offs, and records decisions. Architecture is not just a diagram; it is **a set of decisions, boundaries, and evidence showing that the system meets its objectives**.

### Key Outcomes After This Lesson

After this lesson, you can:

1. Explain the responsibilities and boundaries of the architect role within the cloud application lifecycle.
2. Distinguish the architect's work from that of development, security, and operations teams while recognizing their shared responsibilities.
3. Facilitate an architectural decision involving relevant teams, stating the rationale and consequences of the decision.
4. Evaluate a design based on reliability, security, performance, scalability, cost, and operations using Well-Architected thinking.

## 2. Core Responsibilities of an Architect

| Responsibility | Question to Answer | Verifiable Output |
|---|---|---|
| Understand business and constraints | What value does the system deliver? What must always be true? | Confirmed goals, critical business flows, assumptions, and constraints |
| Translate requirements into quality attributes | How fast, secure, available, and operable does it need to be? | Measurable criteria: latency, peak load, SLO, RPO/RTO, budget |
| Propose overall architecture | Where are component boundaries, data paths, integration points, and failure points? | System diagrams, deployment options, data flows, and alternatives |
| Make trade-off-aware decisions | Why choose option A over B? When should it be revisited? | Architecture Decision Record (ADR), assumptions, risks, and change criteria |
| Align with development, security, and operations | Can the design be built, protected, observed, and recovered? | Peer-reviewed design, test plan, operational readiness criteria |
| Follow up post-deployment | Do production metrics confirm initial assumptions? | Measurement results, improvements, updated ADRs, or replacement decisions |

An architect does not necessarily write every line of code, operate every server, or approve every change directly. However, they must understand the implications of those domains deeply enough for the design to become a working system. Good architecture is **continuous and feedback-driven**, not a blueprint finished once at project kickoff.

### From Functional Requirements to Non-Functional Requirements

**Functional requirements** describe what the system does: search rooms, create bookings, process payments, send notifications. **Non-functional requirements / quality attributes** describe how well the system must perform those functions and under what conditions:

| Attribute | Example Measurable Requirement | Design Implications to Discuss |
|---|---|---|
| Performance | 95% of search requests have latency under 300 ms at agreed threshold load | Caching, data queries, resource limits, load testing |
| Reliability | Booking operation success SLO reaches 99.9% per month, excluding invalid requests per defined measurement rules | Error handling, timeouts, idempotency, dependency limits |
| Recovery | Maximum RPO of 15 minutes, maximum RTO of 60 minutes for a specific failure scenario | Backups, recovery, drills, redundancy cost |
| Security | Sensitive data is role-access controlled and does not appear in logs | IAM, encryption, data classification, log filtering, auditing |
| Scalability | Meets SLOs when load increases 5x during a forecasted peak | Scale-out, queues, connection limits, load testing |
| Cost | Operating cost stays within approved budget under expected load | Forecasting, budget alerts, retention policies, and resource optimization |

These numbers **are illustrative examples only**, not default standards for every application. A target lacking measurement methods, load conditions, or an owner is usually not specific enough to serve as a design basis.

Some key terms:

- **SLI (Service Level Indicator):** an observable metric, such as the ratio of successful booking requests.
- **SLO (Service Level Objective):** a target for an SLI over a defined time window.
- **RPO (Recovery Point Objective):** the maximum amount of data that can be lost, measured in time, within a defined recovery scenario.
- **RTO (Recovery Time Objective):** the target duration to restore service after an incident within a defined scope.

Do not automatically treat an SLO as a legal commitment to customers; a service level agreement (SLA) can be defined separately.

## 3. Who Does an Architect Collaborate With?

The division below is a **reference model**. Final decision authority varies by organization, regulation, and operating model. Cross-team work requires clear ownership.

| Role | Focus | What Requires Collaboration with the Architect |
|---|---|---|
| Product owner / business representative | Customer value, scope, and priorities | Goals, critical user journeys, opportunity cost, acceptable risk levels |
| Tech lead / development team | Detailed design, source code, testing, integration | Service boundaries, API contracts, data models, failure modes, and feasibility |
| Security specialist / AppSec / cloud security | Threats and risk controls | Data classification, identity, authorization, networking, encryption, audit, compliance |
| SRE / Platform / Cloud Operations | Deployment, operations, reliability, recovery | SLOs, monitoring, alerting, safe deployments, runbooks, backups, and drills |
| Data engineer / DBA (if present) | Data lifecycle and integrity | Schemas, transactions, recoverability, retention, replication, and data system capacity |
| FinOps / finance (if present) | Cloud cost efficiency | Load forecasts, unit pricing, budgets, cost tagging, cost-per-transaction analysis |

An effective collaboration model needs three things: **early discussion**, **clear decisions**, and **feedback from deployment/operations**. A design handed to security right before launch day, or handed to operations only after reaching production, usually triggers expensive rework.

## 4. Collaborating with the Development Team

The development team knows the existing codebase, system dependencies, technical debt, and cost of change. The architect provides overall direction and constraints to uphold; developers contribute ground-truth data and lead detailed design.

### Points to Align On

1. **Boundaries and contracts:** which component owns which data, synchronous vs. asynchronous communication, how APIs return errors, and how versioning compatibility works.
2. **Consistency:** which operations require strong transactions (e.g., confirming an available slot), and which data can be updated later (e.g., notification emails).
3. **Error handling:** timeouts, bounded retries, backoff, idempotency, circuit breakers, or fault isolation where appropriate. Uncontrolled retries can amplify overload across the system.
4. **Performance and scaling:** anticipate bottlenecks through measurement; consider DB connection counts, memory, caches, queue sizes, and peak loads.
5. **Evolvability:** separate configuration from code, design safe migrations, contract testing, rollback capability, and incremental rollouts.

For example, the architect proposes using a queue for booking notifications. The development team should challenge: “How do we avoid sending duplicate emails if a message is reprocessed?”, “How do we guarantee the event is published after the booking transaction commits?”. From this pushback, an **idempotent consumer** mechanism and, if needed, a **transactional outbox** can emerge. Those details are part of the architecture, even though finalized through joint design with developers.

### Helpful Practices

- Agree on **architectural acceptance criteria** before coding: API contracts, error handling, load limits, and security conditions.
- Hold short design reviews when decisions affect multiple components or are hard to reverse; let engineers present proposals and evidence.
- Build small proofs of concept to verify unknowns, such as DB connection limits under load, rather than debating by intuition.
- Record decisions and rationale in ADRs; local adjustments that do not affect shared constraints should be decided autonomously by the development team.

Architects must avoid becoming a bottleneck approving every code detail. A useful rule of thumb: **the harder a decision is to reverse and the wider its blast radius, the higher the level of collaboration required**.

## 5. Collaborating with the Security Team

In the cloud, providers and customers share security under the **shared responsibility model**. Exact boundaries vary by IaaS/PaaS/SaaS service and provider; using a managed service does not automatically guarantee that customer applications, identities, data, and configurations are secure.

Architects work with security on **security by design**, embedding controls into early decisions rather than waiting for late-cycle vulnerability scans.

| Design Question | Required Content in the Proposal |
|---|---|
| What data is processed? | Personal/sensitive data classification, usage purpose, retention, and deletion |
| Who gets access? | User/service identities, least privilege, separation of duties, and privileged access controls |
| Where does data travel? | Data flow diagrams, trust boundaries, encryption in transit and at rest, data residency requirements |
| Which components are Internet-facing? | Entry points, network segmentation, WAF where appropriate, inbound/outbound policies |
| How are secrets managed? | Secret manager, rotation, no hard-coded tokens/passwords in code or pipelines |
| How are actions detected and traced? | Appropriate audit logs, masked/filtered log data, anomaly detection, log access controls |
| What if compromised? | Threat scenarios, blast radius containment, incident response and recovery procedures |

### Threat Modeling Is a Joint Activity

A **threat modeling** session should include at least someone who understands the business, architecture/data flows, a developer, and a security owner. A simple process:

1. Draw data flows, assets to protect, and trust boundaries.
2. List actors, entry points, and abuse scenarios: identity spoofing, unauthorized access to another user's bookings, data exposure in logs, excessive API calls.
3. Assess likelihood and impact using the organization's methodology.
4. Select appropriate controls, assign implementation, define verification methods, and have an authorized owner accept residual risk.

Example: an API retrieving booking details must verify that **the caller is authorized for that specific record**, not just confirm the user is authenticated. Development implements checks at the application layer; security sets test criteria; the architect ensures identity flows, access controls, and service separation support that mechanism.

Automated tests, dependency scanning, infrastructure-as-code checks, and authorization tests provide fast feedback. However, scanning tools do not replace understanding business flows and threat models.

## 6. Collaborating with Operations and SRE

A system that merely “works in staging” is not a complete design. Operations and SRE help answer: when a failure occurs at 2 a.m., can the team detect the issue, pinpoint the cause, mitigate impact, and recover within targets?

### Designing for Observability, Deployment, and Recovery

**Observability** must be designed from the start:

- **Metrics:** throughput, error rates, latency, resource saturation, and business metrics such as booking confirmation rate.
- **Logs:** structured, carrying correlation IDs, free of sensitive data, with retention policies.
- **Traces:** tracking request flows across gateways, services, DBs, and queues when distribution makes diagnosis hard.
- **Alerts:** tied to user impact and SLOs; alerts must have an owner and action path, avoiding noisy alerts with no actionable response.

**Safe deployment** typically requires Infrastructure as Code (IaC), validation pipelines, environment-isolated configuration, traceable changes, and rollback or roll-forward mechanisms. Progressive delivery options (canary/blue-green) should be chosen only when risk levels and operational maturity justify the added complexity.

**Recoverability** is more than having backups:

1. Explicitly state scenarios: single instance failure, availability zone disconnect, accidental DB deletion, bad deployment, full region loss.
2. For each scenario, define desired recovery levels and budget constraints.
3. Design replicas, backups, retention, recovery permissions, and step dependencies.
4. Test recovery in a suitable environment; measure **actual RPO/RTO** and improve if targets are missed.

Architects must factor operational cost and complexity into design choices. Moving a simple service to a multi-region, multi-cluster architecture may improve one type of fault tolerance while increasing misconfiguration risk, on-call burden, and cost.

### Minimum Operational Handover Package

A production-ready system typically needs: up-to-date diagrams, service owners, deploy/rollback procedures, SLIs/SLOs and dashboards, alert conditions, runbooks for common failures, backup/recovery plans, critical dependency lists, and escalation procedures. These artifacts should be dry-run with the development team rather than left solely as documentation.

## 7. Collaboration Workflow from Requirements to Production

~~~mermaid
flowchart TD
    A["Business: goals and constraints"] --> B["Architect + teams: confirm quality requirements"]
    B --> C["Propose options and trade-offs"]
    C --> D["Dev + Security + Ops: design review & critique"]
    D --> E["ADRs, diagrams, acceptance criteria"]
    E --> F["Implement & verify: tests, load, security, recovery"]
    F --> G{"Meets criteria?"}
    G -- "No" --> C
    G -- "Yes" --> H["Controlled release"]
    H --> I["Observe SLOs, incidents, costs"]
    I --> C
~~~

The workflow above does not have to run sequentially like “handing off across silos.” In sprint-based product teams, activities can iterate within each increment. What matters is that **decisions have owners, impacted teams have input, and verification criteria exist**.

### Reference Responsibility Matrix (RACI)

RACI uses four letters: **R** (Responsible: executes the work), **A** (Accountable: ultimately answerable), **C** (Consulted: provides input), **I** (Informed: kept updated). Each activity should have a clear A; one person can be both A and R.

| Activity | Business | Architect | Development | Security | Ops / SRE |
|---|---|---|---|---|---|
| Finalize goals, priorities, cost limits | A | R | C | C | C |
| Decide overall system structure | C | A/R | C | C | C |
| Design APIs and detailed logic | I | C | A/R | C | C |
| Establish baseline security controls | I | C | R | A | C |
| Define monitoring, runbooks, recovery drills | C | C | R | C | A |
| Release and confirm operational readiness | I | C | R | C | A |

This is only an **example role split**, not a rigid rule. An organization may assign release authority to a release manager or delivery lead; decisions accepting security, compliance, and budget risks must follow internal authority lines.

### How Should a Decision Be Documented?

An **Architecture Decision Record (ADR)** is a concise record capturing the context and rationale of a significant decision. A practical template:

~~~text
ADR-007 — Send notifications asynchronously after creating a booking
Status: Accepted
Context: Booking response time should not depend on the availability
         of an external email provider.
Options:
  A. Call email provider synchronously inside the request.
  B. Write booking to DB, publish event after commit,
     and have a worker process email asynchronously.
Decision: Choose B; use an outbox if consistency between DB commit
          and event emission must be guaranteed.
Consequences: Faster requests and email fault isolation; in return,
              notifications incur delay and require retries, idempotency,
              queue monitoring, and dead-letter handling.
Verification: Test when email provider fails; measure elapsed time from
              booking confirmation to notification delivery.
Revisit when: Notification latency exceeds business thresholds
              or operational volume grows excessively.
~~~

ADRs do not replace API designs, deployment diagrams, or runbooks. Their value lies in telling future engineers **why** the system is designed this way and what conditions could trigger revisiting the decision.

## 8. Practice Scenario: Designing a Cloud Booking System

Suppose a room-booking platform is migrating from a monolith to the cloud. The product team gives initial assumptions for discussion:

- Room search accounts for most traffic; activity spikes sharply during short campaigns.
- Two overlapping bookings for the same room in the same time range must never be confirmed.
- When the email system fails, bookings must still be recorded and users must receive a clear result.
- Critical transactions must be traceable; personal data must be protected; the business has a finite cloud budget.

This is only context. The architect cannot claim the system is “HA-compliant” without SLOs, failure scenarios, and testing methods. After aligning with the teams, they might select an initial structure like this:

~~~mermaid
flowchart LR
    U["Web / Mobile"] --> G["API Gateway / WAF"]
    G --> S["Application / Booking API"]
    S --> D[("Managed relational DB")]
    S --> C[("Search cache")]
    S --> O["Outbox / Message queue"]
    O --> W["Notification worker"]
    W --> E["Email provider"]
    S -. "Logs / Metrics / Traces" .-> M["Observability"]
    W -. "Logs / Metrics / Traces" .-> M
    D -. "Backup / Restore" .-> B["Backup storage"]
~~~

*Logical diagram for discussing responsibilities and data flows; it does not depict full networking, availability zones, firewalls, IAM, or high-availability mechanisms. Those choices must be designed based on actual requirements and cloud providers.*

### Case 1: Preventing Double-Booked Rooms

- **Business** defines overlap rules, hold durations, refunds/cancellations, and incomplete payment edge cases.
- **Architect + development + data specialists** designate a single authority to decide booking validity. Use DB transactions, appropriate locks, or data constraints to guarantee two conflicting transactions cannot both confirm; reading a cache before writing is insufficient.
- **Security** ensures users can only act on data and resources they are authorized for.
- **Operations** monitors conflict rates, transaction failures, lock contention, and peak-hour latency.

The design decision must be proven with **concurrency testing**: send multiple competing requests for the same slot and verify only one valid request commits.

### Case 2: Email Provider Outage

- The booking is confirmed once the data transaction succeeds, without waiting for the email result.
- The event is persisted and delivered to a worker; if the worker receives the same message again, the action must prevent duplicate processing where business logic requires it.
- Dashboards display unprocessed message counts, age of the oldest message, retry counts, and messages requiring intervention.
- Runbooks specify how to handle failed messages, when to notify customers, and how to clear backlogs.

This is a trade-off between **notification latency** and **booking transaction independence**. The business team must confirm how much notification delay is acceptable.

### Case 3: Losing an Availability Zone

Before choosing multi-AZ, operations and the architect must distinguish: is only one instance failing, an entire availability zone failing, or an entire region failing? Each scope demands different recovery mechanisms and costs. Even with a multi-AZ managed DB, you must still evaluate failover, application connections, DNS/client timeout limits, and data recovery from accidental deletion. **Multi-AZ does not replace backups**, nor does it automatically solve losing an entire region.

### Trade-off Matrix

| Decision | Potential Benefit | Incurred Cost / Risk | Who Needs to Decide Together? |
|---|---|---|---|
| Use a managed database | Reduces some infrastructure maintenance; offers backup/failover options | Service dependency, configuration limits, cost, and connection limits | Architecture, dev/DBA, ops, security |
| Add search cache | Reduces latency and DB read load | Stale data, invalidation complexity; never use cache as source of truth for booking confirmation | Development, architecture, business |
| Notifications via queue | Isolates provider outages; smooths burst load | Asynchrony, duplicate/error handling, backlog monitoring | Architecture, development, ops |
| Multi-availability-zone deployment | Tolerates certain infrastructure failures better | Cost, failover, connection handling, and testing complexity | Business, architecture, ops, finance |
| Least-privilege access control | Shrinks blast radius if identities/credentials leak | Requires role design, governance, and periodic testing | Security, development, ops |

There is no “best” choice detached from context. The architect must describe benefits **along with the conditions required to realize them**, trade-offs, and validation tests.

## 9. Evaluating with Well-Architected Thinking

Cloud providers offer Well-Architected principles with varying pillar names and groupings. When evaluating a design, the following common lenses can be used; do not treat this as an automated certification checklist.

| Lens | Challenge Question | Evidence to Look For |
|---|---|---|
| Reliability | Which component failure impacts the entire business? Has recovery been tested? | Failover results, restore tests, SLOs, and incident history |
| Security | Is access least-privilege? Does sensitive data pass through logs, queues, or backups? | Data flows, threat models, permission tests, audits, and secrets management |
| Performance / Scalability | How does the system degrade at peak load? Where are bottlenecks? | Load tests, p95/p99 latency, error rates, DB/queue limits |
| Cost Optimization | Which resources scale with traffic? Can cost per business unit be tracked? | Forecasts, cost allocation, budget alerts, optimization results |
| Operational Excellence | Who receives alerts, handles errors, and executes rollbacks? | Ownership, IaC, CI/CD, dashboards, runbooks, drills |
| Resource Sustainability (when applicable) | Are resources over-provisioned, repeatedly reprocessed, or retained too long? | Resource utilization metrics, retention policies, and optimization schedules |

It is essential to **examine interactions across lenses**: adding data replicas can improve availability while increasing cost, permission management overhead, and environmental impact. Downsizing resources can cut costs, but requires re-measuring performance and headroom.

## 10. Signs of Healthy Collaboration and Common Mistakes

### Positive Signs

- The business team knows which goals the system is optimizing for and what is being traded off.
- Development has autonomy over detailed design and knows when to escalate architectural changes.
- Security participates from data-model and access-flow design onward, with ways to verify every control.
- Operations participates in defining SLOs, deployment, monitoring, recovery, and incident on-call.
- Every major decision has rationale, assumptions, an owner, and review triggers.
- The team adjusts architecture based on actual load, incident, and cost data.

### Mistakes and Fixes

| Mistake | Consequence | How to Improve |
|---|---|---|
| Choosing technology before understanding the business | Over-complex architecture or failure to meet core requirements | Lock down use cases, quality attributes, and assumptions before evaluating tech |
| Architect makes unilateral decisions | Implementation teams lack buy-in; practical issues get missed | Review with builders and operators; record counterarguments |
| “Security will check before release” | Design flaws surface late, forcing major rework | Embed threat modeling, IAM policies, and security testing into development |
| Measuring only CPU, not business experience | Dashboards look green while customers still cannot book | Define SLIs around critical journeys and alert on user impact |
| Having backups never restore-tested | Unknown whether RTO/RPO can actually be met | Schedule drills, measure results, and fix recovery gaps |
| Choosing microservices/multi-region by trend | Increases integration, monitoring, and on-call operational overhead | Compare against simpler options based on load, team size, and concrete needs |
| Failing to update ADRs and diagrams | Documentation diverges from production | Tie doc updates to architectural changes and major incidents |

## 11. Checklist to Prepare for an Architecture Review

Use this list when an architect invites development, security, operations, and business stakeholders to evaluate a change:

- [ ] Stated core business flows, impacted users, and priority decision-makers.
- [ ] Distinguished mandatory requirements, aspirational targets, and assumptions lacking data.
- [ ] Defined measurable criteria for performance, reliability, security, recovery, and cost fitting the scope.
- [ ] Included component, data flow, trust boundary, and external dependency diagrams.
- [ ] Presented at least one viable alternative and the trade-offs of the primary decision.
- [ ] Development confirmed the design is implementable and testable, including failures and concurrency cases.
- [ ] Security reviewed data, identities, permissions, secrets, logging, and residual risks.
- [ ] Operations reviewed deployment, observability, alerting, runbooks, backups, and recovery.
- [ ] Major decisions are captured in ADRs with owners and revisit conditions.
- [ ] Established a verification plan using pre-release measurements, post-release monitoring, and design update mechanisms.

**Conclusion:** The architect creates alignment between **what the business needs**, **what development can build**, **what security can protect**, and **what operations can sustain**. Cloud architecture quality is demonstrated through well-understood trade-offs, explainable decisions, and results verified in real environments.
