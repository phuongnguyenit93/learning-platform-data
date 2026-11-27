# Evaluating Vendor Lock-In and How Much Portability Is Actually Needed

When designing cloud architectures, the question "will we be locked into a single provider?" is often asked too early, even before asking "why would the system need to switch providers?" Fearing *vendor lock-in*, a team may pass over suitable managed services, self-manage numerous components, and inflate operational costs even when the business has no need to switch platforms. Conversely, ignoring portability completely can make a contract change, regulatory mandate, or strategic incident extraordinarily expensive.

The practical principle is to **evaluate lock-in by business impact, likelihood, and the timeframe required to exit a dependency**, then invest in just enough *portability* for credible scenarios. The goal is not eliminating all dependencies. Choosing to depend on a specific cloud service can be completely justified if it shortens time to market, improves reliability, or reduces operational effort proportionately to future switching costs.

This lesson belongs to the **Cloud Architecture Design Principles** track: moving from business requirements to networking, compute, data, and deployment decisions while weighing reliability, security, scalability, cost, and operations under Well-Architected thinking.

After this lesson, you will be able to:

- Distinguish **provider dependency**, **switching cost**, and **verified portability**.
- Identify lock-in across application, data, infrastructure, security, operational tooling, and contractual layers.
- Determine the needed level of portability using a concrete exit scenario and acceptable timeline.
- Compare the benefits of specialized cloud services against development, operational, and switching costs.
- Propose architectural boundaries, migration tests, and exit plans that pass acceptance review.

## 1. What Is Vendor Lock-In?

**Vendor lock-in** is a situation where changing a provider, service, or operational model becomes difficult or costly because the system depends on technologies, data, APIs, workflows, contracts, or skills tied to the current choice.

Three closely related yet distinct concepts:

| Concept | Practical Question | Example |
| --- | --- | --- |
| **Dependency** | Which components do we rely on for the system to operate? | The application calls cloud A's object storage API. |
| **Switching cost** | How much effort, money, time, and risk does replacing that component take? | Changing SDKs, migrating files, reworking IAM, and re-testing. |
| **Portability** | Under what conditions can we run or move data to a target environment? | Test-deployed the app on cloud B and verified matching data. |

An application running PostgreSQL on cloud A still has dependencies on cloud A: networking, IAM, backups, failover, monitoring, and deployment tooling may be provider-specific. Yet **data model** lock-in may stay low if it sticks to standard PostgreSQL features and verifies data export/import. Conversely, an application using a proprietary analytics API may be deeply coupled to query syntax, event structures, and billing mechanics.

**There is no "zero-dependency" architecture.** Self-hosting Kubernetes, Kafka, or open-source databases still creates dependencies on versions, tooling, skilled staff, and operational practices. The useful question is *which dependencies deliver value, which introduce unacceptable risk, and what evidence do we have?*

### Forms of Dependency Often Overlooked

1. **APIs and SDKs:** application code directly invokes proprietary features; event schemas, query dialects, workflows, or authentication tied to a provider.
2. **Data:** large data volumes, proprietary formats, database extensions, transaction semantics, analytics pipelines, and costly data egress.
3. **Infrastructure and networking:** virtual networks, subnets, load balancers, NAT, private endpoints, service discovery, and zone/region mapping.
4. **Identity and security:** IAM roles, workload identities, KMS, secret managers, audit logs, access policies, and encryption keys.
5. **Operations:** CI/CD, logging, tracing, alerting, backups, disaster recovery, runbooks, and incident response expertise.
6. **Commercial and organizational:** committed-spend contracts, pricing discounts, licenses, support tiers, staff skills, and process change costs.

A provider may support exporting data while **offering no path to reproduce full application behavior** on another platform. Thus, statements like "our data always belongs to us" are insufficient to conclude we can migrate safely.

## 2. Start with an Exit Scenario, Not Technology

Before investing in portability, state **why**, **when**, **what** needs to move, and **what level of business disruption** is acceptable.

### Scenarios That Can Trigger Migration

| Trigger Scenario | What Must Be Verified | Corresponding Preparation |
| --- | --- | --- |
| Contract terms or costs shift sharply | Net cost difference after discounts, egress, operations, commitment windows | Track alternative pricing and renewal dates; maintain migration estimates |
| New data residency or compliance rules | Permitted regions for storage, processing, backups, and support access | Data inventory, export/import verification, and available deployment regions |
| Provider sunsets a service or changes APIs | End-of-support dates, replacement APIs, compatibility limits | Isolate integrations, plan service upgrades or replacements |
| M&A or platform consolidation | Cutover deadlines, target systems, permissions, cross-org dependencies | Map services, data, contracts, and test on the target |
| Service capability no longer meets targets | Is the issue the product, how we architected its use, or provider reality? | Measure SLOs and root causes; test replacing affected components |
| Customer requires deployment in a private environment | Does the customer need isolated config, isolated data, or the entire workload on their infrastructure? | Define deployment boundaries and concrete operational agreements |

An exit plan needs a **viable destination**. "Can move to any cloud" is hard to verify. "Can migrate the booking API and customer data from cloud A to cloud B within at most 90 engineering days, with an agreed write-freeze window" is an assumption you can design for and test.

### Questions to Determine Real Need

- **Trigger:** What condition would force the company to move? Who holds decision authority?
- **Scope:** The entire application, only the database, one customer segment, or a specific deployment region?
- **Timeline:** Do we need recovery in hours after a disaster, or a planned migration over several months?
- **Data:** Volume, growth rate, consistency requirements, residency limits, retention duration?
- **Downtime:** Can writes be paused or rolled out by user cohort? For how long at most?
- **Budget and staffing:** Do we have staff capable of operating two environments concurrently?
- **Verification:** What evidence proves the scenario works: restore tests, cutover rehearsals, p95, error rate, data reconciliation?

**Distinguish two goals:** restoring service after a region fails (**disaster recovery, DR**) and replacing one provider with another (**provider exit/migration**) are two distinct problems. A multi-zone or multi-region system on the same cloud can meet infrastructure outage RTO/RPO without creating cross-provider portability. Conversely, being able to export data to cloud B in two weeks does not help restore service in 30 minutes.

## 3. Choose the Right Portability Level Instead of Defaulting to "Cloud Agnostic"

Portability comes in levels and layers. You may only need **scheduled data export and planned service replacement**, rather than running the same application across two clouds at all times.

| Level | What Is Achievable | Relative Time and Cost | When Appropriate |
| --- | --- | --- | --- |
| **M0 — Dependency map exists** | Understand what the system uses, where data lives, and exit conditions | Low; migration not yet proven | New products with no specific migration mandate yet |
| **M1 — Data can be exported and restored** | Extract in a known format, transfer, and verify data at target | Moderate; requires restore and reconciliation drills | Need to safeguard data control and long-term transition options |
| **M2 — Layered replacement plan** | Swap database/queue/storage or APIs via adapters and migration playbooks | Moderate to high; requires boundary separation and contract tests | Realistic risk concentrated in a few core components |
| **M3 — Redeployable on a second platform** | Stand up environment, deploy app, and operate key functions at target | High; ops, IAM, networking, monitoring must all translate | Contractual obligation for another environment or clear migration plan |
| **M4 — Active multi-provider operations** | Serve load/recover across multiple clouds with synchronized data and ops | Very high; introduces distributed data and split challenges | Only when benefits, contractual duties, or recovery time truly demand it |

This is a **reference scale for discussion**, not a universal standard or maturity certification. A system might sit at M2 for storage while sitting at M0 for identity; never collapse everything into one "portable" label.

### Portability Must Be Evaluated by Dimension

**Application portability:** Can application code run on another runtime or environment?

**Data portability:** Can schemas, data, event history, keys, and metadata be extracted, transformed, imported, and validated?

**Infrastructure portability:** Can networking, compute, storage, IAM, and service configurations be built at the target via repeatable processes?

**Operational portability:** Can dashboards, logs, alerts, CI/CD, backup/restore, runbooks, audits, and teams operate successfully at the target?

**Contractual portability:** Do data export clauses, termination terms, software licensing, egress caps, and support commitments permit executing the plan?

Running a container image in environment B proves only **partial runtime compatibility**; it does not prove database transactions, network connectivity, permission models, observability, or failover work properly. Kubernetes and Terraform aid automation and repeatability, but do not automatically make managed services, IAM, or networking identical across providers.

## 4. Mapping Dependencies and Assessing Risk with Focus

First, list the components on the serving path of critical business journeys. For each dependency, document **what it is used for**, **how specialized it is**, **affected data**, **replacement time**, and **consequence if it cannot be replaced**.

Example of an online consultation booking app with an API, appointment database, email queue, and file store:

| Component | Lock-In Indicators | Impact If Leaving Provider | Relative Migration Difficulty | Sensible Action |
| --- | --- | --- | --- | --- |
| Containerized business API | Standard containers, but provider-specific ingress and identity configs | Medium | Moderate | Separate environment configs; test build/deploy at target |
| Managed PostgreSQL | Uses SQL/extensions, provider backups, and failover mechanisms | High because it holds booking data | Moderate to high | Inventory extensions, test logical export/restore, reconcile data |
| Managed queue | Provider-specific SDK, metadata, retries, dead-letter policies | Medium to high | Moderate | Isolate publish/consume; design for idempotency |
| Object storage | Provider-specific SDK, IAM, and signed URLs | Medium | Moderate; volume-dependent | Abstract file storage API; test migrating objects and metadata |
| IAM/KMS | Platform-coupled roles, policies, and cryptographic keys | Very high if data readability could be lost | High | Map permissions and plan lawful decryption/re-encryption |
| Logging/monitoring | Provider-specific queries, metrics, alerts, and retention | High for post-cutover operations | Moderate to high | Standardize signal names; build dashboards and alerts at target |
| Contracts and networking | Spend commitments, egress pricing, IP allowlists | Depends on terms and traffic | Moderate to high | Track commitment dates, estimate egress, update partner dependencies |

Each team can use a qualitative **low / medium / high** scale to prioritize; if numerical scoring is used, explicitly state how impact, likelihood, and migration difficulty are determined. Self-assigned scores only aid discussion and never replace evidence or business owner alignment.

A simple way to prioritize first steps is asking:

1. **If this component cannot be swapped, what happens?** Revenue disruption, data loss, non-compliance, or merely slower delivery of one feature?
2. **Is the scenario forcing a switch genuinely likely within our planning horizon?** Are there concrete contracts, regulations, customer demands, or product signals?
3. **How long does the component take to replace, and can it be pre-tested at reasonable cost?**

The answer is rarely "make everything portable." You might invest in **M1 for customer data**, **M2 for the queue**, while deferring full production replication on a second cloud until concrete demand arises.

## 5. Designing Boundaries for Targeted Replaceability

A sound architectural boundary keeps **how business logic uses services** insulated from specific SDKs and APIs. Nevertheless, not every cloud API warrants a hand-rolled abstraction layer.

### 5.1. Isolating Dependencies at Sensible Interfaces

In a booking application, the domain needs two capabilities: saving appointments and emitting notification events. The domain does not necessarily need to know the queue or database product name. You can define interfaces for business-needed behaviors and place adapters in the infrastructure layer to translate calls.

~~~mermaid
flowchart TD
    UI[Web or mobile client] --> API[HTTP API]
    API --> SVC[Booking domain service]
    SVC --> REPO[BookingRepository contract]
    SVC --> PUB[NotificationPublisher contract]
    REPO --> DBAD[Database adapter]
    PUB --> QAD[Queue adapter]
    DBAD --> DB[(Managed relational database)]
    QAD --> Q[(Managed message queue)]
    Q --> WORKER[Notification worker]
    WORKER --> MAIL[Email/SMS provider]
~~~

Java business interface example:

~~~java
import java.time.Instant;
import java.util.UUID;

public interface BookingRepository {
    // Double-booking prevention must also be enforced at data transactions/constraints.
    Booking createIfSlotAvailable(UUID customerId, UUID slotId);
}

public interface NotificationPublisher {
    // Define semantics: idempotency, retries, and error handling.
    void bookingConfirmed(UUID bookingId, Instant occurredAt);
}
~~~

This is an example of logical boundaries. The code above **does not by itself guarantee atomicity** between writing the database and publishing the event. If the business transaction must persist first and reliably publish afterward, use a **transactional outbox** and relay worker; consumers still need idempotency since duplicate deliveries can occur.

The value of interfaces lies in keeping business logic clear and allowing adapters to swap; the cost is extra code layers and contract tests to maintain. If all features run on one cloud with no credible exit scenario, writing "abstract adapters for everything" can slow development and hide valuable native service capabilities.

### 5.2. Prefer Open Standards When They Meet Requirements

Examples:

- Use HTTP, TLS, OpenAPI, or well-documented protocols for appropriate system communication; document any proprietary extensions.
- When choosing a relational database, assess SQL compliance, PostgreSQL/MySQL semantics, extensions, stored procedures, and *actual* export/import capabilities.
- Use common data formats with explicit versions/schemas when exchanging or exporting data; retain metadata needed for reconstruction.
- Adopt observability standards like OpenTelemetry where appropriate to ease moving trace/metric data, while still mapping alerts, queries, and target tooling.
- Package runtimes in containers when sensible, keeping configurations and secrets out of images.

**Using standards does not guarantee one-click portability.** Providers differ in versions, quota limits, compatibility levels, transaction semantics, latency, locking behavior, authentication, or failure modes. Testing happy-path functionality is not enough; test under load and fault conditions.

### 5.3. Use Specialized Services When Benefits Are Proven

Choosing a proprietary serverless database or workflow service can sharply cut administration, auto-scale smoothly, and speed up product launch. That is genuine business value. When accepting deeper lock-in, explicitly document:

- Which proprietary feature delivers value and how is that value measured?
- If that feature is removed, how much code, infrastructure, and staffing does an alternative require?
- Is there a way to export data and phase out the dependency incrementally?
- How long is replacement estimated to take; who signs off on the cost and disruption?
- When should the decision be revisited: pricing shifts, regulations, load, customer demands, or service lifecycle?

What to avoid is not "using any proprietary service," but **not knowing what trade-off you are making**.

## 6. Data Portability Is Harder Than Code Portability

Across many workloads, the most time-consuming part is moving **accurate, complete, secure, and verifiable data**, especially while the system keeps generating transactions during migration.

### 6.1. Clarify What "Exportable Data" Actually Means

Inventory:

- **Primary data:** transaction tables, stored objects, files, events, user-generated content.
- **Structure:** schemas, indexes, constraints, extensions, collations, timezones, numeric types, timestamp precision.
- **Metadata:** file versions, ownership, tags, retention, timestamps, checksums, referential links.
- **Derived state:** unprocessed queues, sessions, caches, materialized views, search indexes; decide which must migrate and which can be rebuilt.
- **Data protection:** encryption keys, access permissions, policy-driven deletion, backup locations, and deletion proof obligations.

Example of migrating PostgreSQL to another managed PostgreSQL: check engine versions, extensions, collations, logical replication, identities/sequences, triggers, users/permissions, and connection limits. Identical product names do not guarantee full compatibility across two environments.

For object storage, reconcile **object counts, sizes, checksums, metadata, access permissions, and versioning states**, rather than checking total gigabytes alone. Signed URLs, bucket policies, and access APIs usually require application updates.

### 6.2. Common Migration Patterns

| Migration Approach | Suitable When | Key Risks |
| --- | --- | --- |
| **Offline export/import** | Writes can be paused during a cutover window | Downtime, export/import duration, and validation |
| **Snapshot + incremental / CDC** | Large datasets aiming to minimize write freeze | Lag, event ordering, schema errors, concurrent mutations during sync |
| **Phased by customer or domain** | Architecture permits tenant partitioning and routing | Cross-referenced data, split state |
| **Controlled dual-write** | Dedicated drift detection/reconciliation mechanisms are built | Partial writes, divergent ordering, duplicates, inconsistency |

**Never assume dual-write is safe by default.** Writing concurrently to two independent systems does not form a cross-system transaction. Without handling one-sided failures, retries, ordering, and reconciliation, data divergence becomes hard to spot. Whenever possible, favor a single authoritative write source per phase with clear sync and cutover mechanics.

### 6.3. Cutover Plans Need Stop and Rollback Conditions

A typical verification sequence:

1. Provision the target with appropriate access controls and data policies; verify storage regions, permissions, and encryption keys.
2. Check schema and structural compatibility; rehearse moving a sanitized data subset or suitable test dataset.
3. Transfer the initial dataset; synchronize ongoing changes if using an online model.
4. Reconcile record counts, checksums, business totals, and referential integrity; verify out-of-database data such as objects and queues.
5. Validate latency, throughput, transaction semantics, retries, and API access paths at the target.
6. Decide the write-freeze window or traffic-switch method; drain sync lag below approved thresholds and perform final reconciliation.
7. Shift traffic incrementally or wholly; monitor errors, success rates, p95, and data consistency.
8. Decommission the old environment only after the verification, retention, and rollback window closes with approval.

Quantify **go/no-go** criteria in advance: tolerable sync lag, mismatched record threshold, failed transaction threshold, downtime window, and who holds halt authority. Once new writes land on the target post-cutover, rolling back to the old source is **no longer as simple as flipping DNS**; you need reverse synchronization or a write pause and merge plan to avoid losing transactions.

## 7. Networking, Security, and Operations Must Accompany Migration Plans

Moving APIs and data while forgetting supporting layers yields a system that runs in a demo yet cannot operate in production.

**Networking:** remap ingress/egress paths, private endpoints, NAT, DNS, TLS termination, IP allowlists, partner links, firewalls, and inter-region paths. Check quotas, bandwidth limits, and egress charges. When syncing across two clouds, measure real latency and transfer costs rather than assuming local-network speeds.

**Identity and access:** map service identities, roles, policies, secrets, trust boundaries, and human permissions. Verify equivalence in **what is allowed and denied**, not merely copying role names. Verify audit trails remain intact post-migration.

**Encryption and keys:** check which keys encrypt data, whether keys work at the target, and whether decrypting and re-encrypting inside a secure pipeline is permitted. Never assume every cloud KMS allows exporting private keys. Plan key migration or recovery via valid copies under proper access controls.

**Observability:** migrate SLIs/SLOs, dashboards, alerts, log retention, trace sampling, and on-call workflows. Preserve correlation IDs across synchronous and asynchronous hops where feasible to trace bugs while running dual environments.

**Operations:** document bootstrapping, CI/CD, secret provisioning, backups, restores, scaling, patching, and rollback at the target. Moving Terraform modules to another cloud usually requires rewriting resource definitions and policies. Structure IaC to **manage platform variants cleanly** rather than forcing a "lowest common denominator" abstraction that blocks essential platform features.

**Compliance:** verify data processing locations, backup storage regions, logs, cross-border admin access, deletion workflows, and customer commitments. A second provider does not automatically create compliance if configs and data paths remain wrong.

## 8. Trade-Offs Between Managed Services and Portability

Architecture should optimize **total value and total cost of ownership (TCO)** over time, not simply minimize provider-specific APIs.

| Criterion | Specialized Managed Services | Common Technologies / More Self-Management |
| --- | --- | --- |
| Time to market | Often faster when features fit requirements | Can require more build and operational setup time |
| Infrastructure care | Provider assumes part of responsibility by service tier | Team bears heavier patching, backup, and scaling duties |
| Advanced features | Often deeply optimized and integrated | Depends on deployment choices, plugins, and team skill |
| Ongoing running cost | Can be better or worse depending on load, quotas, and pricing | Also varies; must factor engineering and on-call hours |
| Exit cost | Can be high due to APIs, data, contracts, and workflows | May be lower in some layers, yet networking, IAM, data, and ops still move |
| Scalability | Bounded by service quotas and characteristics | Bounded by sizing, tuning, and operational skill |

Neither column always wins. For example, a proprietary managed queue may fit an organization with limited SRE headcount far better than self-hosting a message broker cluster. If the queue is the likely exit point under customer contracts, adapters and migration drills can provide ample flexibility without self-managing the whole stack.

### Decision Cost Model

An option's total cost should include:

~~~text
Period TCO = initial build
           + load-driven cloud fees
           + operations, staffing, and on-call cost
           + testing, security, and compliance
           + expected switching or exit costs
           + grounded risk/downtime cost estimates
~~~

Platform switching costs include engineering time, adapter development, data transfer, egress fees, parallel running, testing, IAM rework, observability, operations, and disruption risk. Comparisons must hold **load, SLOs, RTO/RPO, security bar, and planning horizon** constant.

**Illustrative calculation example (USD, hypothetical, not market pricing):** A company compares two designs over 36 months:

- **Option A:** leverages specialized managed services at \$12,000/month total operating cost, with no upfront portability investment.
- **Option B:** builds for redeployability on a second cloud at \$16,000/month operating cost plus \$50,000 extra initial build/test effort.
- If exiting the provider within 36 months, estimated migration cost is \$180,000 for A and \$60,000 for B. Business stakeholders roughly assume a 25% probability of migrating during the period.

Considering only those items:

~~~text
Extra cost to choose B over 36 months
  = (16,000 - 12,000) × 36 + 50,000
  = 194,000 USD

Expected migration cost savings from B
  = (180,000 - 60,000) × 25%
  = 30,000 USD
~~~

In this example, **expected migration savings alone do not offset B's extra cost**. That does not mean A wins unconditionally: non-linear consequences such as non-compliance, breached contracts, losing strategic customers, or prolonged downtime must also be weighed. The 25% figure is purely a thought-exercise assumption and must never be presented as a grounded forecast without data.

At the same time, **mitigating lock-in does not have to cost \$194,000**. A middle-ground option can keep A's managed services while building a data inventory, testing export/restore, and isolating a few key APIs at a fraction of the price. Comparisons should include this middle option.

### What Threshold Justifies Investing?

Invest in portability when at least one condition has strong evidence:

1. **Mandatory requirement:** laws, contracts, data residency rules, or customers require another environment within a defined deadline.
2. **Unacceptable business risk:** failing to exit would cause losses exceeding business risk appetite even at low probability.
3. **Measurable economic benefit:** after full TCO accounting, switching providers yields net value above cost and risk.
4. **High deployment variance:** the product must deploy on-premises, in private clouds, or in regions a single provider does not serve.
5. **Low-cost boundary opportunities:** placing adapters at key seams, storing data in standard formats, and testing restores significantly lower risk at modest cost.

## 9. Multi-Region, Multi-Cloud, and Hybrid Solve Different Problems

| Model | What It Solves Best | What It Does Not Guarantee |
| --- | --- | --- |
| **Single cloud, multi-AZ** | Instance/zone outages, service-level HA | Full-region outages, provider lock-in |
| **Single cloud, multi-region** | Certain region outage scenarios, geographic proximity | Ability to leave provider, automatic data consistency |
| **Multi-cloud active/passive** | Ready standby target if thoroughly designed and drilled | Automatic RTO/RPO; still requires syncing data, security, ops |
| **Multi-cloud active/active** | Specific mandates for continuous multi-platform serving | Cross-cloud latency, split-brain, write conflicts, and extreme complexity |
| **Hybrid cloud/on-premise** | Integrating local assets or strict data locality mandates | Seamless compatibility, cheaper or simpler operations |
| **Periodic export/import plan** | Preserves long-term exit capability at lower ongoing cost | Instant failover during severe outages |

**Multi-cloud is an architectural choice carrying continuous operational cost**, not a default badge of vendor independence. Specifically, many systems cannot run active/active across two independent databases without explicitly designing ownership, consistency, conflict resolution, and recovery workflows.

If the goal is surviving an availability zone loss with minute-scale RTO, multi-AZ fits. If the goal is leaving a provider within six months after a contract shift, an M1–M3 plan may suffice. Both make sense when matched to the actual business risk.

## 10. Evaluation Workflow for an Architecture Review Session

A review cycle should produce **verifiable decisions** rather than merely a list of technologies.

### Step 1 — Fix the Context

Document the system, users, critical transactions, traffic, sensitive data, SLOs, and RTO/RPO. Confirm who holds decision authority and who bears the impact if a migration is needed.

### Step 2 — Pick 1–3 Credible Migration Scenarios

Examples: must move data to an approved region within 12 months; provider contract expires in 24 months; enterprise customer mandates an isolated environment. Never turn "every provider could vanish tomorrow" into a hard requirement without risk analysis.

### Step 3 — Inventory Dependencies Along the Request Path

Trace requests through databases, queues, storage, identity systems, logs, and partners. Record impacts on data, source code, security, configs, and operators.

### Step 4 — Assign Required Portability Levels per Component

Pick M0–M4 per scenario rather than one blanket level for the entire system. For instance, you might require quarterly data export/restore drills (M1) while only documenting how to swap the email service (M0/M2 depending on execution needs).

### Step 5 — Compare at Least Three Options

Compare **specialized managed**, **managed with replacement boundaries**, and **broader redeployable stack**. For each option, evaluate TCO, time to market, operational capacity, security, reliability, and exit scenario duration.

### Step 6 — Prototype What Is Uncertain

Test with a properly sanitized slice of real data, run a minimal deployment on the target, reconcile functionality, load, and data; measure real cost and time. Small experiments can prevent costly, unnecessary multi-cloud investments.

### Step 7 — Decide and Set Revisit Triggers

Record an Architecture Decision Record (ADR): chosen option, alternatives, assumptions, impact, accepted risks, verification methods, and revisit triggers. A dependency justified today may become unsuitable as load, products, or markets evolve.

### ADR Template for Portability Decisions

~~~yaml
id: ADR-012
title: Choose managed queue while keeping adapter replaceable
status: accepted
context:
  - Application needs asynchronous notifications after booking
  - Small ops team, no current multi-cloud requirement
  - Need ability to replace queue if contract changes
decision:
  - Use current cloud's managed queue
  - Domain depends solely on NotificationPublisher contract
  - Idempotent consumer with retries and dead-letter policy
alternatives:
  - Self-host message broker cluster
  - Run dual queues concurrently across two clouds
consequences:
  benefits: Lower operational effort and faster time to market
  constraints: Adapter, IAM, and queue semantics still require rewriting upon exit
verification:
  - Test publish/consume/duplicate/timeout scenarios
  - Test swapping adapter in test environment
review_trigger:
  - Customer mandates different infrastructure
  - Provider pricing, quotas, or contract terms change significantly
~~~

This template records an architectural decision, **not live runnable config**. Using interfaces does not remove the need to verify retry policies, message ordering, and real service limits.

## 11. Practice: Evaluating a Lock-In Decision in Cloud Architecture

**Hypothetical scenario:** A booking platform has 100,000 daily active users, containerized backends running on managed compute in cloud A, managed PostgreSQL, a managed queue, object storage, and cloud A's observability suite. It holds roughly 4 TB of historical data and attachments. The product requires high booking availability and customer data protection; the engineering team has 8 people and no dedicated multi-cloud ops team.

The business may sign a contract with an enterprise customer requiring data processing in a region supported only by cloud B. No contract is signed yet; if signed, the delivery deadline is **9 months**. Leadership asks: "Should we rewrite everything for Kubernetes and deploy active/active across two clouds immediately?"

### Tasks

1. **Identify the trigger:** What turns this customer assumption into a real migration obligation? What customer scope, data regions, access rules, and delivery milestones must be confirmed?
2. **Build a dependency table:** Evaluate at least database, queue, object storage, IAM/KMS, networking, CI/CD, and observability. Highlight dependencies risking data loss or contract breach.
3. **Assign M0–M4 by layer:** Explain why each layer needs that level. Distinguish migrating one customer cohort to cloud B from running the entire system active/active.
4. **Propose three options:** Stay as-is and prepare an exit plan; establish boundaries and test selective migration; build a permanent second environment. Compare cost, timeline, reliability, security, and operational effort.
5. **Design a scoped PoC:** Stand up a booking path on cloud B with test data, test export/restore with reconciliation and timing; identify IAM, encryption, network, and monitoring risks.
6. **Set decision gates:** When should the team step up from M1/M2 to M3? What metrics or signed commitments must exist before investing in continuous dual-cloud operations?

### Evidence-Based Solution Direction

Given the facts provided, **there is insufficient evidence to mandate multi-cloud active/active**. A sensible path is:

- Validate customer requirements and data residency clauses with legal/product teams first; define the exact data scope that must move.
- Prioritize **data and encryption keys**: inventory data types, DB extensions, files, metadata, permissions, and backups; rehearse export/restore with checksums and business reconciliation.
- Evaluate deploying a vertical slice of the API and database on cloud B (**trial-scale M3**), without running long-term parallel production yet.
- Isolate queue, storage, and identity integrations where beneficial; avoid writing a universal "multi-cloud" abstraction for every service before target platforms are confirmed.
- Budget migration and parallel-run duration should the contract close; prepare cutover, rollback, and observability checklists.

If the contract signs with a 9-month deadline, the team must shift from **risk exploration** to a **milestone-driven delivery plan with clear owners**, validating cloud B deployment early. If the requirement entails serving two independent regions long-term, examine tenant sharding, data governance, and operating two environments. If the requirement is merely archiving a subset of data in another region, a smaller solution may exist without moving the whole system.

A final choice cannot rest on "4 TB" or user count alone. Measure transfer bandwidth, churn rate, throughput, schema complexity, legal rules, and team capacity.

### Practice Acceptance Criteria

A solid assessment must answer:

| Verification Question | Minimum Evidence |
| --- | --- |
| Why move? | Business/compliance trigger and requirement with an accountable owner |
| What must move? | Data inventory, dependency map, workload boundaries |
| How long will migration take? | Estimate grounded in PoC, data volume, and cutover steps |
| Is data accurate and secure? | Reconciliation, permissions, encryption, restore/cutover drills |
| Can it operate at the target? | CI/CD, dashboards, alerts, runbooks, load/failure tests |
| Do benefits justify cost? | TCO under shared assumptions, alternatives, accepted risks |

## 12. Common Misconceptions and Design Mistakes

**"Using Docker/Kubernetes makes us portable."** Containers and orchestrators solve part of packaging/deployment. Databases, identity, networking, secrets, queues, and operations can still remain deeply tied to a provider.

**"Write Terraform once, run on any cloud."** Terraform supports many providers, yet resource schemas, service capabilities, IAM, and networking differ. Separate modules/configs, testing, and migration workflows are still required.

**"Open source eliminates lock-in."** Account for operations, versions, plugins, storage formats, skills, and supporting infrastructure. Self-hosting can impose heavier burdens than a well-matched managed service.

**"We can export data so we can move quickly."** Restoring is more than copying bytes. Schemas, metadata, permissions, keys, reconciliation, ongoing mutations, and safe cutover are all required.

**"Multi-cloud always increases availability."** If data consistency is unsolved, cross-cloud networking adds dependencies, failover goes untested, or ops teams split focus, added complexity can actually increase outage risk.

**"All proprietary APIs are bad."** Specialized managed services can slash maintenance and boost delivery speed. The real issue is replacement risk without a plan to manage it.

**"Just pick the cheapest monthly option."** Factor total build, on-call, migration, egress, parallel-run, security, downtime, and contractual commitment costs.

**"Portability can be added later when we need to move."** When migrations are bound by legal/contract deadlines, lacking a data map and permission model can make timelines impossible. Maintain at least a dependency dossier and export/restore proof for critical data.

## 13. Well-Architected Review Checklist for Vendor Lock-In

| Perspective | Review Questions Related to Provider Lock-In |
| --- | --- |
| **Operational Excellence** | Which platform features do runbooks and pipelines rely on? Can the team operate and roll back at the target? |
| **Security** | Can IAM/KMS, secrets, audits, access permissions, and residency be preserved during migration? |
| **Reliability** | Are DR and provider exit clearly distinguished? Have restores, cutovers, and data errors been tested? |
| **Performance Efficiency** | Have latency, throughput, quotas, network egress, and load behavior been measured at the target? |
| **Cost Optimization** | Are TCO, contract commitments, migration fees, parallel runs, and egress accounted for? |
| **Sustainability** | Does standing multi-cloud create idle compute and unnecessary data duplication? |

A review produces value when it captures **assumptions → evidence → risks → decisions → owners → revisit dates**. You do not need maximum "provider independence score" across every layer. Prove that the architecture meets business goals, understands the price of accepted dependencies, and holds a credible path forward when conditions change.

Portability is a **quality attribute engineered to demand**, much like reliability or security: it requires scope, timelines, budgets, measurements, and explicit risk tolerance. Sound architectural decisions preserve the speed and strengths of the current cloud while protecting the business against migration scenarios that truly matter.
