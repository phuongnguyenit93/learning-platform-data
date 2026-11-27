# Public, Private, and Hybrid Cloud: Selection Criteria

## 1. Choosing a Deployment Model Is an Architectural Decision

When designing a cloud system, the question is not simply "Which cloud should we put the app on?" but rather **where each workload, dataset, and operational responsibility should reside** to meet business requirements. Three models are commonly evaluated:

- **Public cloud:** resources and services operated by a cloud provider serving multiple customers over a shared platform, with appropriate resource isolation mechanisms.
- **Private cloud:** a cloud environment dedicated to a single organization; it may reside in the organization's own data center or be operated by a third party.
- **Hybrid cloud:** combining heterogeneous cloud environments—typically private cloud with public cloud—using connectivity and integration mechanisms that enable them to coordinate or move data/workloads as needed.

These are **deployment models**, not service levels. Within each model, the organization must still consider how services are delivered, such as IaaS, PaaS, container platforms, or SaaS. "Choosing public cloud" does not automatically mean "using serverless"; "choosing private cloud" does not force you to self-manage every single virtual machine.

In the **CLOUD_ARCHITECTURE** module, this decision bridges business requirements with network, compute, data, and deployment design choices. Every choice must explain its trade-offs across **reliability, security, scalability, cost, and operations**, then be validated using Well-Architected thinking.

**Running example:** an enterprise operating a booking service has a website serving customers across multiple regions; its accounting system and some transactional data currently live in a private data center. During holidays, search queries spike sharply; meanwhile, booking confirmation and payment processing require correctness, recoverability, and access control. The numbers in this lesson are **illustrative learning assumptions**; real projects must substitute measured data and approved requirements.

## 2. Understanding the Three Models and Common Misconceptions

### 2.1. Public Cloud

Public cloud provides compute, storage, networking, and managed services on a flexible consumption model. Infrastructure may be shared across multiple customers at the physical layer, while each customer is separated using logical isolation, identity, permission, and private networking controls.

Typical strengths include rapid resource provisioning, access to a broad range of managed services, multi-region distribution, and avoiding upfront hardware purchases. In return, the organization must engineer secure configurations and govern service limits, data, usage costs, and provider dependencies.

**Note:** "public" describes how the infrastructure is offered—it **does not mean every customer's data is publicly accessible**. A database deployed on public cloud can still be reachable only over a private network, encrypted, and restricted to authorized accounts.

### 2.2. Private Cloud

Private cloud dedicates cloud resources to one organization and delivers capabilities in a cloud-like manner—such as self-service, automated provisioning, usage metering, and centralized resource management. It can be built on enterprise-owned infrastructure, in a colocation data center, or operated exclusively for the customer by a provider.

The defining trait is **the level of control and environmental dedication**; you cannot assume every private cloud runs on hardware located at company headquarters. Conversely, an internal virtualization cluster lacking self-service, automation, and cloud-style resource management should be called on-premises infrastructure or a virtualization environment rather than automatically labeled a complete private cloud.

Private cloud allows deep control over the platform and change schedules, yet requires the capability to maintain hardware, power, networking, updates, redundancy, monitoring, security, and capacity expansion plans. **Dedicated does not automatically mean more secure or always more available.**

### 2.3. Hybrid Cloud

Hybrid cloud connects heterogeneous environments and unifies certain processing flows, data, or operational workflows so each workload runs where it fits best. You might place the frontend and search on public cloud while keeping core data and specialized systems in private cloud, or place backup/recovery resources in the other environment.

Hybrid is not merely "having a VPN tunnel." You must clarify **which services communicate, which data is synchronized, which authentication model is used, how resilient the connection is, and how unified operations work**. A system whose public-cloud application queries a private database directly over a long-haul link may be called hybrid, yet suffer terrible performance and reliability.

### 2.4. How Do Hybrid, On-Premises, and Multi-Cloud Differ?

| Term | Meaning | Misconception to Avoid |
| --- | --- | --- |
| **On-premises** | Infrastructure located on the organization's own premises | Not automatically a private cloud; depends on delivery and operating model |
| **Hosted private cloud** | Dedicated cloud environment hosted/operated by an external party | Still qualifies as private cloud if it meets dedication and cloud delivery traits |
| **Hybrid cloud** | Integration of heterogeneous cloud environments, typically private + public | Requires interoperable data, connectivity, identity, and operations architecture |
| **Hybrid IT** | Broad term for concurrently using traditional on-premises systems and cloud | Not every on-prem system has become a private cloud |
| **Multi-cloud** | Using services from more than one cloud provider | May consist solely of two public clouds; not necessarily hybrid cloud |
| **Dedicated host on public cloud** | Physical server resources dedicated to one customer within a public cloud service | Not enough to classify the entire environment as private cloud |

## 3. Decision-Level Comparison

| Criterion | Public Cloud | Private Cloud | Hybrid Cloud |
| --- | --- | --- | --- |
| **Provisioning and scaling** | Usually fast if services and quotas are available; still bounded by architecture and limits | Depends on purchased capacity and hardware procurement/expansion cycles | Scales flexibly in some parts; constrained at integration points |
| **Infrastructure control** | Customer controls configuration and workloads within service scope; provider controls many lower layers | Allows deep control over hardware, networking, and change schedules | Control varies by environment; requires policy standardization |
| **Data and compliance** | Depends on service availability regions, contracts, configuration, and specific obligations | Offers more direct control over physical location and hardware, but you must prove controls yourself | Can keep a subset of data where mandated; cross-environment sync flows add compliance review scope |
| **Cost** | Tends toward usage-based pricing and fast experimentation; varies with traffic, storage, and data transfer | Involves CapEx/leasing and capacity operations; cost-efficiency depends on utilization | Combines costs of both environments plus connectivity, integration, and governance |
| **Reliability** | Rich built-in services and redundancy tools; requires proactive distributed design and testing | Can be tailored to specific needs; redundancy quality depends on capital and operations | Adds fault-isolation options while introducing link failure points and cross-environment dependencies |
| **Security** | Shared responsibility model; requires proper IAM, networking, logging, and key config | Dedicated control across many layers, but you bear patching, physical, and ops duties | Attack surface and identity lifecycle expand across multiple environments |
| **Operations** | Many managed services available, yet demands cloud, IaC, and FinOps skills | Requires infrastructure teams, platform operations, and capacity planning | Requires capabilities on both sides plus cross-boundary monitoring, change, and incident response |
| **Latency** | Strong when services sit close to users/data sources | Advantageous when close to internal systems, factories, or specialized equipment | Sensitive to distance, cross-environment links, and synchronous traffic |

The table above shows general tendencies, **not fixed rankings**. A well-architected public cloud can meet strict compliance demands; a misconfigured private cloud can still be breached and lose data; a hybrid cloud can increase latency if chatty components are placed far apart.

## 4. Favorable Conditions for Choosing Public Cloud

Public cloud is typically a strong candidate when:

1. **Demand is variable or uncertain:** new products need rapid experimentation, traffic fluctuates hourly/seasonally, and you want to avoid buying peak capacity upfront.
2. **Market expansion:** you need to reach users across multiple regions, spin up test environments, or serve distributed customer groups.
3. **The team wants to focus on the application:** you can leverage managed databases, queues, monitoring, key management, and deployment services to reduce infrastructure toil.
4. **Region and service options satisfy data requirements:** obligations regarding data residency, contracts, access controls, retention, and auditing have been specifically verified.
5. **Usage governance is in place:** the team has budgets, cost alerts, data transfer forecasts, and resource governance controls.

For the booking service example: search, catalog display, thumbnail generation, content delivery, and test environments can fit public cloud well, especially when query volume spikes unpredictably. However, you must inspect database bottlenecks, payment system limits, data egress costs, and transaction state guarantees.

### When to Exercise Caution?

- Workloads depend on specialized hardware or internal systems with ultra-low latency requirements.
- Data is bound by residency or control forms that the candidate public cloud service/region **has not been verified** to satisfy.
- Load is very steady, long-term, and large: compare multi-year TCO instead of assuming public is always cheaper.
- The application uses many provider-specific features while facing strict portability mandates: evaluate API, data, and operational lock-in alongside migration costs.
- The responsible team lacks capability to govern cloud IAM, networking, configuration, quotas, deployments, or costs.

**Common mistake:** choosing public cloud because services carry labels like "multi-AZ", "auto scaling", or "managed" and assuming SLOs are already met. You must define application architecture, backup strategy, service dependencies, and test evidence.

## 5. Favorable Conditions for Choosing Private Cloud

Private cloud is usually worth considering when at least one strong driver exists and the team has sufficient operational capability:

1. **Deep control requirements:** needing platform customization, hardware/device selection, or upgrade schedule control unsuitable for public services.
2. **Physical or on-site integration constraints:** data and processing must sit near manufacturing equipment, control systems, specialized storage, or hard-to-move internal dependencies.
3. **Confirmed data residency/governance requirements:** legal and technical assessments show a private solution satisfies mandatory obligations better than other candidates.
4. **Existing efficient infrastructure investment:** the system has steady load, available capacity, and truly competitive lifecycle TCO after including maintenance, redundancy, staffing, power, cooling, and hardware refresh.
5. **Mature operations team:** possessing provisioning automation, identity governance, patching, monitoring, change management, backups, and incident drill practices.

Example: factory operations analytics software must ingest signals from on-site equipment under strict latency bounds. Running some processing near the equipment on private infrastructure can make more sense than shipping all raw data over the Internet. The decision must still account for fault tolerance and downstream aggregated analytics.

### What Makes Private Cloud Unsuitable?

If you must buy an entire new system to handle rare peak loads, upfront CapEx can be high and idle capacity wasted. If the team lacks platform engineering skills, the control advantage turns into security risks, availability gaps, and prolonged recovery times.

**A single data center does not provide disaster recovery.** If the business must survive a full site outage, you need an independent remote environment, appropriate data replication, failover playbooks, and RTO/RPO drills; the private model alone does not solve this.

## 6. Favorable Conditions for Choosing Hybrid Cloud

Hybrid cloud is valuable when workload groups have distinct requirements and **the value of splitting environments exceeds integration costs**. Common scenarios include:

- **Phased modernization:** temporarily keeping hard-to-move core systems in private cloud while building new APIs or services in public cloud, reducing big-bang change risk.
- **Segregating constrained data:** keeping certain data or processing in a private environment while sending only authorized datasets/outputs to public cloud for supplemental tasks.
- **Separating edge/device-adjacent processing from analytics:** processing real-time signals where data is generated, and syncing aggregated data to cloud for batch analytics.
- **Using elastic capacity for independently scalable parts:** such as rendering or batch jobs that are well-packaged with a sound data movement plan.
- **Meeting failover or recovery plans:** using another environment for replica storage or recovery compute if timing, data safety, and operational procedures permit.

Hybrid **does not automatically provide infinite scaling or instant failover**. A workload can only "burst" to another environment if the application, data, connectivity, licenses, identity, and routing mechanisms are ready. Never assume replicating an active transactional database over a wide-area link will not add latency or can easily preserve consistency.

### Reference Architecture: Hybrid Booking Application

~~~mermaid
flowchart TB
    U[Customers] --> E[CDN / Web / Public cloud API]
    subgraph PUB[Public cloud]
        E --> S[Search and catalog service]
        E --> B[Booking application]
        S --> C[(Read replica / search index)]
        B --> G[Authenticated integration adapter]
        O[Data-governed logs / metrics / traces]
    end
    subgraph CONN[Cross-environment connectivity]
        G --> L[Monitored private connectivity or VPN]
    end
    subgraph PRI[Private cloud]
        L --> I[Internal business API]
        I --> D[(Transactional data source)]
        I --> P[Accounting / reconciliation system]
    end
    B -. measure journey .-> O
    I -. measure dependencies .-> O
~~~

This diagram is **one candidate option to evaluate**, not the single standard design. If every booking action must wait on the internal API across a remote link, the public cloud app remains tightly coupled to private cloud. The team must define behavior when the link drops, acceptable error levels, retry bounds, and reconciliation logic.

### Five Questions to Answer Before Choosing Hybrid

1. **Latency:** how many cross-environment round trips does one user request require? Do end-to-end journey p95/p99 latencies stay within thresholds?
2. **Data:** where is the *source of truth*? Which fields are replicated? Do legal policies allow transmitting that data across environments/regions?
3. **Consistency:** how stale can read data be? What atomicity, idempotency, ordering, and reconciliation do write transactions require?
4. **Failures:** if the VPN/private link drops or one side goes down, which journeys remain functional? Are RTO/RPO still met?
5. **Operations:** who monitors the link, manages federated accounts, rotates certificates, traces requests end-to-end, and handles incidents?

### Common Integration Patterns

| Integration Pattern | Best Suited When | Risks to Verify |
| --- | --- | --- |
| Synchronous API over private link/VPN | Transactions need immediate responses at moderate frequency | Compounded latency, timeouts, circuit breakers, cascading failures |
| Asynchronous queues/events | Delayed processing is acceptable; decoupling system cadence is needed | Duplicate/out-of-order messages, replay, reconciliation, backlog monitoring |
| Controlled read data replication | Read-heavy workloads tolerating update lag | Data freshness, PII protection, deletion propagation, access control |
| Scheduled batch | Analytics, reporting, less time-sensitive data archiving | Transfer volume, sync windows, data lineage |
| Cross-environment backup/DR | DR requirements exist with a pre-engineered recovery path | Real recoverability, DNS/IAM dependencies, standby cost, sync lag |

## 7. Decision Process: From Requirements to the Right Model

Do not start with a table saying "public 8 points, private 7 points" before knowing which constraints are mandatory. Split the process into two tiers.

### Tier A — Eliminate Options Violating Mandatory Conditions

First, compile a list of constraints backed by **evidence and owner sign-off**:

- Where must data be processed/stored? Does "storage" include backups, logs, system snapshots, support data, and DR?
- Are there mandatory hardware types, licenses, connections to on-site equipment, or audit standards?
- What is the latency budget in milliseconds for communicating with existing systems? Can the dependency be redesigned?
- Are budget and launch deadline hard gates or adjustable targets?
- Does the option have adequate operational capability, support, recovery, and incident authority?

If an option fails a mandatory condition, **never let it win via high scores on other criteria**. For example, if data must reside in a designated jurisdiction where a provider lacks an appropriate region and has no approved alternative, that provider's public cloud is invalid for that data subset. This **does not rule out all public cloud services** nor imply only private cloud satisfies compliance; evaluate specific products, locations, and obligations.

### Tier B — Score Trade-Offs Among Viable Options

Suppose all three options pass Tier A for a booking application with seasonal search spikes and transactional dependencies at a private site. The table below shows **illustrative scores assumed by a hypothetical project team** on a 1–5 scale (5 = better fit). Do not treat these scores as universal truth.

| Criterion | Weight (%) | Public | Private | Hybrid |
| --- | ---: | ---: | ---: | ---: |
| Meets verified data/control requirements | 25 | 3 | 5 | 5 |
| Handles variable load | 20 | 5 | 2 | 4 |
| Latency integrating with core systems | 20 | 2 | 5 | 4 |
| Meets reliability and recovery targets | 15 | 5 | 3 | 4 |
| Lifecycle TCO within budget | 10 | 4 | 2 | 3 |
| Current team operational readiness | 10 | 4 | 2 | 2 |
| **Weighted total / 500** | **100** | **370** | **350** | **395** |

**Calculation:** total = Σ(weight × score), max 500. Hybrid example: 25 × 5 + 20 × 4 + 20 × 4 + 15 × 4 + 10 × 3 + 10 × 2 = **395**. You can normalize to 79/100, though the validity of the conclusion depends on the evidence behind scores and weights.

**Proper interpretation:** hybrid leads tentatively under these assumptions, but also scores low on operations and introduces connectivity risks. If experiments reveal high link latency or operations cost exceeding budget, re-score or adjust workload placement. If the team wants simplicity, consider co-locating tightly coupled components in one environment and splitting out only loosely coupled parts.

### Decision Matrices Must Include Evidence

| Item to Record | Verification Question |
| --- | --- |
| Source of each weight | Who considers data, latency, or cost most important and why? |
| Source of each score | Quotes, benchmarks, legal mandates, or mere guesses? |
| Peak and failure scenarios | How does the model behave under traffic spikes, link loss, or site outage? |
| Sensitivity of conclusion | If cost weight rises or hybrid ops score drops, does the ranking change? |
| Transition costs | What do data migration, training, ops setup, and exit cost? |

The matrix's purpose is to **expose assumptions and sharpen debate**, not to replace engineering, security, and business judgment with a single total score.

## 8. Do Not Force One Model Across Every Workload

An enterprise can choose public cloud for most systems, private cloud for a small subset, and hybrid integration only where needed. To allocate workloads, profile each component:

| Workload | Data to Gather | Placement Tendency to Verify |
| --- | --- | --- |
| Web frontend, images, static assets | Where are users located? Is global delivery needed? | Public cloud/CDN often favorable; still verify security and budget |
| Search, catalog reads | What is peak load? Is stale data acceptable? | Public with read index/replica can make sense if data policy permits |
| Booking writes and payments | Where is the source of truth? Consistency, RTO/RPO, and duplicate prevention needs? | Place near write store and payment integrations; do not pick purely on platform popularity |
| Existing finance/accounting | Portability, licensing, interfaces, and release cadence? | May stay in private during transition if migration risk is high |
| Batch analytics | Which data is permitted to move? Volume and schedule? | Can leverage elastic public capacity if transfer cost and data controls fit |
| Observability and audit | What do logs contain? Who can view them? Retention period? | Controlled centralized collection, segregating sensitive data and enforcing retention |
| Backup and DR | RPO/RTO? Need separate site/region or separate provider? | Choose an appropriately independent location; test restore and dependencies |

**Practical rule:** place components requiring frequent synchronous transactions **close together in network and data terms** whenever feasible; decouple parts needing only async responses, caches, or read replicas once freshness bounds are clear. Never split across environments along org-chart boundaries if doing so increases network hops and creates hard-to-observe failure chains.

## 9. Cross-Cutting Trade-Off Axes

### 9.1. Security, Privacy, and Shared Responsibility

On public cloud, the provider is responsible for the infrastructure underlying the services they deliver; the customer remains responsible for data, access configuration, applications, identities, and operational layers depending on the service type. On private cloud, the organization or contracted operator takes on the underlying infrastructure as well. On hybrid, you must **define responsibility at each end of the connection and wherever data is replicated**.

Controls to review regardless of model: least-privilege IAM, strong authentication for sensitive roles, appropriate encryption in transit and at rest, key and secrets management, network segmentation, hardening, logging/auditing, vulnerability management, backups, and incident response processes.

Identify sensitive data, processing locations, transfer mechanisms, authorized viewers, and retention limits. **"Using private cloud" is not sufficient to prove regulatory compliance**; likewise, public cloud region selection is not the full story if logs, backups, support access, or replicas leave that region. Cross-check specific obligations against actual configurations and contracts.

### 9.2. Performance, Networking, and Data Gravity

When data volumes are large and network call rates are high, **data gravity** often makes moving compute closer to the data more sensible than moving data on every request. Estimate at least:

- Initial data migration size, daily change rate, and achievable network throughput.
- **p95/p99** network latency between components; total synchronous round trips per transaction.
- Transfer speed, egress fees, and resilience of the link against disruption.
- Behavior under slow networks, packet loss, or one-way partitions: timeouts, bounded retries, circuit breakers, and queues.

Example: a booking API makes 5 sequential calls to a private system, each incurring 40 ms of added network latency. Network latency alone adds roughly 200 ms along the critical sequential path, before application processing, TLS, DB execution, and jitter. This is an illustrative calculation, not a fixed hybrid latency; measure at the actual deployment sites.

### 9.3. Reliability and Disaster Recovery

Two environments can remove one single point of failure while adding new dependencies. Draw a **dependency map** for every user journey; measure availability by journey, not solely by server status.

You must be able to answer: if one availability zone, one site, one network link, or the central identity system fails, what stops working? Are backup access paths, appropriate DNS/routing, accessible backups, and operators trained to switch into recovery mode ready? **RTO** is recovery time target and **RPO** is time-based data loss tolerance; both must be proven through drills simulating the exact failure scenario.

### 9.4. Total Cost of Ownership (TCO) and Operating Cost

Never compare the rental price of one VM against buying one physical server and draw a conclusion. A multi-year cost model should cover the relevant buckets:

~~~text
Lifecycle TCO =
  compute + storage + network + data transfer
  + hardware/colocation + power + cooling (if applicable)
  + licenses + operations + support + security
  + backup/DR + observability + cross-environment connectivity
  + migration/training/transition costs
~~~

For public cloud, track average/peak load, idle resources, storage growth, log retention, egress, managed service fees, and redundancy configuration costs. For private cloud, include hardware depreciation/refresh, headroom capacity, dual-site upkeep, staffing, and upgrade lifecycles. For hybrid, add dedicated links/VPN, networking services, duplicated ops tooling, and contract change costs.

Evaluate at least three scenarios—**normal / peak / incident or scale-out**—and set budgets and alerts accordingly. Projected costs must be revisited after pilot telemetry; never treat public list prices as total cost.

### 9.5. Operational Capability and Change Agility

Can the team already execute IaC deployments, secrets management, end-to-end observability, incident response, patching, and DR drills? Hybrid can simultaneously demand on-prem networking, cloud networking, identity federation, database replication, and SRE skills. Without sufficient capability, a more distributed architecture becomes harder to operate.

Establish processes for config changes, access provisioning, deploy/rollback, fault detection, and on-call rotation. Multi-component models require a cross-environment version compatibility plan so an upgraded cloud app never breaks against an older internal API.

## 10. End-to-End Walkthrough: From Requirements to Decision

**Context:** an on-premises booking platform needs to serve more users during peak seasons. Transaction data currently resides in an internal accounting system; the team wants to modernize the UI and search first.

**Hypothetical requirements for stakeholder interviews and verification:**

| ID | Requirement Statement | Verification Method |
| --- | --- | --- |
| FR-01 | Customers search and book; system never double-confirms a room per business rules | Concurrency contention and idempotency testing |
| QR-01 | Search API p95 response time ≤ 800 ms at 200 requests/sec | Load test with agreed dataset and measurement points |
| QR-02 | Lookup journey achieves 99.95% monthly SLO | SLI on valid requests over approved measurement window |
| QR-03 | Upon primary site loss, target RTO ≤ 2 hours and RPO ≤ 15 minutes for booking data | Recovery drill and data timestamp verification |
| SEC-01 | Sensitive data traverses only approved flows with role-based access | Data flow diagrams, authorization tests, security review |
| FIN-01 | Cost stays within budget across three approved load tiers | TCO forecast checking logs, network, backup, DR, staffing |

### Three Candidate Options

**Option A — Primarily public cloud:** move most apps and data to managed cloud environments. Strength: fewer cross-environment integration points and easy resource provisioning. Moving critical transactional systems requires solving migration, consistency, contracts, and data obligations; otherwise A may be unviable in phase 1.

**Option B — Primarily private cloud:** modernize the platform on private infrastructure, optimizing connectivity to core systems. Strength: minimal disruption to transactions sitting close to internal data. Potential drawbacks: capacity expansion lead time and cost of provisioning for peak spikes.

**Option C — Hybrid cloud with clear boundaries:** host frontend/search in public cloud while keeping core writes in private during phase 1; integrate over authenticated APIs and sync read indexes under policy. Strength: incremental rollout; challenges: connectivity, latency, data sync, and cross-environment operations.

A sound outcome **is not declaring C the automatic winner**. The team must measure API latency under real conditions, test link outages, assess which data may be transferred, estimate TCO, and prove RTO/RPO. If cross-environment links miss latency targets or ops skills are lacking, you may need to move more processing near the source data, shift to async communication, or adjust the migration plan.

### Illustrative Architecture Decision (Short ADR)

~~~text
ADR-01: Split Search to Public Cloud in Phase 1

Context:
- Search experiences sharp peak load; transactional system is stable in private environment.
- Insufficient verified evidence yet to migrate transactional data.

Proposed decision:
- Pilot public cloud for frontend and search reads.
- Keep transaction writes in the private environment during phase 1.
- Sync permitted read data and use authenticated integration APIs.

Acceptance criteria:
- Pass QR-01 via load testing and link-loss tests.
- Synced data complies with confirmed policies.
- Complete recovery drills for FR-01 and QR-03.
- Scenario TCO stays within approved budget.

Trade-offs:
- Increases read scalability and reduces big-bang migration risk.
- Adds hybrid operations, observability, and data reconciliation requirements.

Re-evaluate when:
- Transactional dependency becomes a bottleneck;
- connectivity costs rise or latency thresholds are breached;
- core data migration plan is ready for execution.
~~~

## 11. Incremental, Verified Execution of the Decision

Once a direction is chosen, avoid migrating everything based on a single architecture slide. Suggested execution steps:

1. **Classify workloads and data:** map dependencies, data sources, user journeys, deployment regions, backup/log locations, and third-party systems.
2. **Define acceptance criteria:** peak latency, journey SLOs, incident RTO/RPO, security/compliance, budget, and operability.
3. **Design networking and identity:** IP/DNS, segmentation, routing, private/VPN links if applicable, cross-environment authentication, certificates, and link-failure handling.
4. **Design data flows:** source of truth, consistency, data classification, recovery, sync/reconciliation strategy, and replica revocation/deletion.
5. **Run risk-focused proof of concept:** prioritize testing cross-environment links, sync lag, consistency, failover paths, and cost under real load.
6. **Stand up operations:** IaC, journey monitoring, tracing, alerting, runbooks, access controls, config audits, and owners per component.
7. **Migrate in small reversible waves:** clarify data rollback, controlled traffic shifting, SLI measurement, security sign-off, and approval before expanding.
8. **Review against Well-Architected:** using metrics and incidents, review operations, security, reliability, performance, cost, and resource efficiency.

In particular, **recovery is not merely having backups**. A DR plan requires executable procedures, accountable owners, access credentials when the primary environment is down, DNS/connectivity switchover time, the last recovered data point, and integrity verification methods.

## 12. Practice Exercise: Choosing Models for Three Workloads

Take the role of architect for an organization with:

- A website experiencing 8x traffic surges during short promotional campaigns.
- A factory machine control system requiring real-time response, currently on-site.
- Large long-term analytical datasets, partly containing sensitive information.

**Tasks:**

1. Write at least **six measurable requirements** (latency, reliability, RTO/RPO, traffic, data limits, budget) and flag which assumptions lack evidence.
2. Identify disqualifying constraints, especially data residency and on-site equipment dependencies.
3. Build a placement matrix across public/private/hybrid, explaining data exchange paths and operational ownership.
4. Create a weighted matrix, **without** using scores to override mandatory constraints. Adjust two weights to test whether the conclusion holds.
5. Sketch a preliminary architecture covering networking, compute, data sources, failure domains, and recovery paths; walk through **cross-environment link loss** and **primary site loss**.
6. Write an ADR stating the choice, considered options, remaining trade-offs, and tests required before formal sign-off.

**Passing criteria:** a reader can pinpoint **where each workload goes, why, what it depends on, its operational cost and risk, how it fails, and how it is verified**.

## 13. Pre-Finalization Decision Checklist

- [ ] Distinguished business requirements, quality attributes, constraints, and assumptions.
- [ ] Classified data and confirmed legal/contractual obligations for regions, backups, logs, and DR.
- [ ] Identified write source of truth, consistency needs, and portability for every workload.
- [ ] Measured or planned tests for latency and throughput along critical communication paths.
- [ ] Identified shared failure points, cross-environment dependencies, and disconnected behavior.
- [ ] Established targets and verification scenarios for SLO, RTO, and RPO—not relying solely on service marketing.
- [ ] Modeled multi-scenario TCO including ops, connectivity, data transfer, backups, and transition costs.
- [ ] Verified team skills, cross-party responsibilities, and end-to-end observability.
- [ ] Recorded disqualified options, priority conditions, ADR, and review triggers.

**Core Takeaway:** public, private, and hybrid clouds are ways to organize technology capabilities to serve requirements. Good architecture chooses **the right placement for each dataset and workload**, satisfies mandatory constraints, backs quality claims with evidence, and sustains acceptable cost and operational responsibility across the system lifecycle.
