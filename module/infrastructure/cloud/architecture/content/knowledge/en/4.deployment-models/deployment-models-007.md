# Distinguishing Availability, Geographic Distribution, and Data Sovereignty

When designing cloud architectures, three questions often arise simultaneously:

1. **Will the system keep serving when a component fails?** This is the question of **availability**.
2. **In which geographic locations must users, applications, and data reside?** This is the question of **geographic distribution**.
3. **Under whose jurisdiction and control does data fall; where may it be stored, processed, and accessed?** This is the question of **data sovereignty**.

These three concepts are related, yet **they do not substitute for one another**. A system running across two availability zones in one region may handle infrastructure faults well without serving users across two continents at low latency. A system with a global CDN may load fast in many countries while still having a single database as a single point of failure. A system storing data inside one country does not automatically satisfy mandates governing authorized viewers, jurisdiction, backups, logs, or operational contractors.

This lesson belongs to the **Deployment Models** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to choose networking, compute, data, and deployment approaches grounded in business requirements while analyzing trade-offs across reliability, security, scalability, cost, and operations using Well-Architected thinking.

## 1. Learning Objectives

After studying this lesson, you will be able to:

- Define and distinguish availability, geographic distribution, data residency, data localization, and data sovereignty.
- Identify **failure domains**, regions, availability zones, and the infrastructure layers that must be distributed.
- Translate business requirements into SLIs/SLOs, RTO/RPO, latency targets, and data placement/access constraints.
- Compare single-zone, multi-zone, multi-region, active-passive, active-active, hybrid, and multi-cloud deployments.
- Spot easily overlooked data paths such as logs, backups, caches, telemetry, operational support, and partner systems.
- Propose designs that are testable, trace clear accountability, and prove data constraints.

## 2. Concept Map: Three Independent Design Axes

| Axis | Core Question | Metrics or Evidence | Example Controls |
|---|---|---|---|
| **Availability** | When faults occur, does the service stay responsive and how fast does it recover? | Availability SLI/SLO; outage duration; RTO/RPO; drill results | Redundancy, eliminating SPOFs, health checks, failover, backup and restore |
| **Geographic distribution** | Where are resources and traffic placed to serve users and survive failures? | Regional latency, throughput, network distance, replica locations, regional errors | Multi-region, CDN/edge, latency-based routing, replication, data partitioning |
| **Data sovereignty** | Who and which systems can control, access, or process data under applicable laws and contracts? | Data inventory; data flows; storage/processing locations; contracts; operator access; access logs; audit evidence | Data classification, region pinning, IAM, key controls, third-party controls, audits |

A design can satisfy one axis while failing the other two. For example, replicating an entire database to a foreign region improves recovery from a region outage, yet introduces cross-border data transfers requiring assessment. Conversely, keeping all data in one region simplifies placement governance, yet creates outage exposure if that region becomes unavailable without a viable recovery plan.

## 3. Availability: How Long Does the System Keep Serving?

### 3.1. Availability, Reliability, and Durability Are Not Synonymous

- **Availability:** the ability to deliver a function or service when requested. Explicitly define what "available" means: web page loads, API returns valid results, or users actually complete transactions.
- **Reliability:** the system's ability to maintain correct required behavior over time, including fault handling, recovery, and sustained quality.
- **Durability:** the ability to preserve validly written data over time. A highly durable storage service can still become temporarily unavailable; conversely, a high-uptime API can still lose data if its write path is flawed.

Example: a booking search page still loads while the payment database is unreachable. If users cannot finish booking, measuring only HTTP 200 responses on the homepage creates an SLI that hides business failure.

### 3.2. SLI, SLO, SLA, RTO, and RPO

| Term | Meaning | How to Apply |
|---|---|---|
| **SLI – Service Level Indicator** | Defined metric measuring service quality | Ratio of valid booking requests processed successfully below a latency threshold |
| **SLO – Service Level Objective** | Internal target for an SLI over a defined window | Example: target 99.9% valid requests succeeding over a 30-day window |
| **SLA – Service Level Agreement** | Contractual service commitment with violation remedies/conditions | Read exact scope, calculation formula, exclusions, and remedies when a CSP misses targets |
| **RTO – Recovery Time Objective** | Target maximum duration to recover after a defined incident | Example: restore booking capability within 60 minutes |
| **RPO – Recovery Point Objective** | Maximum acceptable data rollback window upon recovery | Example: accept losing at most 5 minutes of written data prior to incident |

In simple measurement terms:

~~~text
Availability = Time service satisfies SLI conditions / Total observation time

RTO = Target recovery time from an agreed incident start marker
RPO = Target maximum age of recoverable data
~~~

The SLO, RTO, and RPO examples in this lesson are **illustrative assumptions**. No technology guarantees specific numbers simply because it is marketed as highly available. Define measurement methods, agree on incident start/end timestamps, and verify via drills.

**Distinguish two scenarios:** automated failover to a standby instance reduces downtime, yet does not protect against accidental data deletion; backups restore deleted data, yet may not meet a tight RTO if manual restoration and verification are needed.

### 3.3. Failure Domains and Redundancy at the Right Layer

A *failure domain* is a set of resources that can be impacted together by a shared fault, such as a process, virtual machine, node, rack, availability zone, region, or shared control plane. Naming and isolation guarantees of zones/regions vary by CSP.

| Deployment Level | Failures Tolerated When Designed Properly | Typical Limitations |
|---|---|---|
| Multiple instances on **one node** | Single application process crash | Cannot survive node failure |
| Multiple nodes in **one zone** | Single node failure | The zone itself can be a common point of failure |
| Multiple zones in **one region** | Single zone failure within service and architecture scope | Region-wide outages or shared dependencies can still halt service |
| Multiple regions | Can survive a single region outage if data, routing, and dependencies support it | Higher cost; state/consistency, latency, failover, and data residency grow complex |
| Multiple providers | Can mitigate certain CSP-level dependency risks | Does not eliminate shared faults in app code, DNS, identity, processes, or third parties; harder ops |

**Do not infer** that "having two instances" means "high availability": if both depend on a single database, unreachable secrets, a shared subnet, or a deployment pipeline capable of pushing a broken config everywhere, a single point of failure still exists.

### 3.4. High Availability Differs from Disaster Recovery

**High availability (HA)** focuses on sustaining or rapidly resuming service during routine, anticipated component failures. HA designs use multiple instances, load balancing, health checks, and cross-zone redundant data.

**Disaster recovery (DR)** focuses on recovering from severe incidents that knock out an entire infrastructure scope or corrupt system state; it requires coordinated recovery plans for apps, data, identities, keys, networks, DNS, ops runbooks, and data validation.

- **Active-passive:** standby environment awaits activation or runs partial capacity; usually lowers write conflicts, while startup and switchover time govern RTO.
- **Active-active:** multiple sites serve concurrently; can reduce latency and disruption, yet must solve state, transactions, concurrent writes, and network partition failures.
- **Backup/restore:** protects against accidental deletes or logical corruption; recovery duration depends on dataset size, procedures, and service throughput limits.

A synchronous or asynchronous replica **is not automatically a backup**: accidental deletes, ransomware encryption, or application bugs replicate right along with valid writes. Consider independent, immutable backups or point-in-time recovery (PITR) based on your targets.

## 4. Geographic Distribution: Where to Place Compute, Data, and Network Paths?

### 4.1. Regions, Availability Zones, Edge, and User Locations

- **Region:** a geographic area of CSP infrastructure, usually containing multiple zones. Region is the deployment unit for many services, though some services are global and have different data-storage rules.
- **Availability zone:** an infrastructure unit engineered to contain localized faults within a region; verify actual independence in CSP documentation.
- **Edge / CDN point of presence:** compute or caching locations near users to lower latency for specific content or functions. Edge nodes are not necessarily where source-of-truth data is stored long-term.
- **On-premises / private environment:** resources operated by the organization or a third party at a dedicated site, optionally linked to cloud regions in a hybrid topology.

**Geographic distribution does not require distributing every system component.** You can use a global CDN across dozens of countries for public images while keeping transactional data and the database in a single approved region—or deploy APIs in two regions while centralizing writes in one.

### 4.2. Different Objectives Drive Different Topologies

| Objective | Candidate Deployment Direction | What Must Be Verified |
|---|---|---|
| Lower latency for images and static assets | CDN with edge caching | Cache policies, what gets cached, invalidation delay, cache PoP locations |
| Lower API latency for distant users | Multi-region APIs with geo/latency routing | Database placement, round-trip latency, session state, consistency, and egress cost |
| Survive single availability zone loss | Load balancing + multi-zone compute and data tiers | Zero remaining stateful components or shared networking causing full outages |
| Survive full region outage | Multi-region DR or active-active | RTO/RPO, failover, replicated datasets, dependency recoverability |
| Protect data within permitted locations | Policy-enforced regions, replicas, backups, logs, and flows | Audit real data flows; control operator and third-party access |

### 4.3. Latency and Data Consistency

As distance between regions grows, synchronous communication incurs higher network latency and partition risk. Placing applications near users will not speed up transactions if every query must still travel back to a distant database.

Two common replication modes:

- **Synchronous:** write commits may require confirmation from multiple sites; reduces post-failover data loss risk at the cost of higher latency or availability impact during partitions, depending on algorithm and config.
- **Asynchronous:** targets receive updates after the primary; lowers write-path latency at the risk of losing un-replicated writes if the primary fails. Measure replication lag and test real RPO.

In multi-writer active-active setups, you must also define conflict handling for duplicate writes, concurrent updates, payment transactions, inventory counters, and user sessions. Never default to "last write wins" for bookings or financial data if lost updates are unacceptable.

### 4.4. Global Components Can Still Be Single Points of Failure

Even a multi-region architecture must audit DNS, login/IdP, key management, CI/CD, config stores, global routing, certificate authorities, payment gateways, and third-party APIs. Two regions sharing one non-redundant dependency can still fail together. Traffic cutover is also never instant: DNS caching, health check intervals, persistent connections, sessions, and stateful caches all affect recovery time.

## 5. Data Sovereignty: Broader Than Where Servers Sit

### 5.1. Commonly Confused Terms

| Concept | Focus | Example |
|---|---|---|
| **Data residency** | Physical geographic location where data is stored or processed | Primary database records sit inside a designated region |
| **Data localization** | Legal mandate or policy requiring certain data to stay stored/processed in a specific location | Applicable regulations requiring specific data classes to remain inside a country |
| **Data sovereignty** | Jurisdiction, control, and accessibility of data under laws, contracts, and operating models | Evaluating provider legal entity, operator access, remote access, keys, and lawful disclosure rules |
| **Data privacy** | How personal data is collected, used, shared, and protected, plus data subject rights | Purpose limitation, retention windows, and read permissions on personal data |
| **Data governance** | Data ownership, lifecycle policies, quality, cataloging, and controls | Dataset owner approves storage regions, retention, and access rules |

**Data residency is one input to sovereignty assessment, not proof of sovereignty on its own.** A database whose primary rows sit in an approved region may still send logs, backups, analytics copies, or support access across borders. Likewise, encryption at rest is helpful yet insufficient to ensure no unauthorized party accesses data while services decrypt and process it.

### 5.2. Jurisdiction and Operational Factors to Examine

When stakeholders say "data must stay in-country" or "we must ensure data sovereignty," break it down into concrete questions:

1. **Which data classes?** Personal data, contracts, transactions, images, access logs, metadata, encrypted blobs, and derived copies may face distinct rules.
2. **What does "in-country" cover?** Long-term storage only, all processing, all backups, or zero cross-border read/share flows?
3. **Who has access?** Where are CSP operators, support contractors, enterprise admins, monitoring tools, and integration partners located?
4. **Who controls encryption keys?** Provider-managed keys, customer-managed keys, dedicated HSMs, or revocable key mechanisms? Who can technically compel decryption?
5. **Which legal entities and contracts apply?** Service provider entity, lawful access handling, subprocessors, and data transfer clauses.
6. **What evidence is available?** Audit reports, certification scopes, contracts, region policies, access logs, test results, and data-flow diagrams.

Legal mandates vary by country, industry, data class, and over time. In real implementations, verify **current regulations and specific contracts with legal/compliance teams**. Never infer compliance purely from a region name, a "sovereign cloud" label, or marketing claims.

### 5.3. Tracking the Entire Data Lifecycle and Flow

Map every stage: **collection → transit → processing → storage → replication → backup → observability → export/sharing → deletion**. For each stage, answer: what data, where, processed by whom, who has access, how long retained, and what evidence exists.

Frequently overlooked paths:

- **Backups, snapshots, replicas, DR:** secondary copies may sit elsewhere than primary rows; verify automated backup behavior and restore rules.
- **CDN and caches:** responses and metadata can be cached at global edge locations.
- **Logs, traces, crash dumps, support tickets:** payloads, tokens, PII, or queries often leak into external logging and ticketing tools.
- **Analytics, monitoring, and AI services:** analytics, notification, search, or inference pipelines may copy data to another location.
- **CI/CD and non-prod environments:** production data copied into dev/test or onto contractor laptops.
- **Email, payments, maps, and SaaS partners:** data sent to third-party processors with different locations and permissions.
- **Account and control-plane metadata:** administrative metadata often has global scope distinct from business payloads.
- **Remote support access:** storing data in one country does not inherently stop operators in another country from accessing it remotely.

If a CSP commits to data locality only for **a specific service's primary storage**, do not extrapolate that commitment to logs, backups, analytics, or support systems.

### 5.4. Common Controls

| Control Group | Typical Solutions | Limitations to Understand |
|---|---|---|
| Approved region enforcement | Region-restriction policies, IaC checks, config scanning | May not cover all global services or third-party resources |
| Data classification & minimization | Transmit only necessary fields; separate sensitive data from public assets | Data emitted into logs/traces must also be controlled |
| Identity and permissions | Least privilege, MFA, workload identity, separation of duties, access reviews | Internal IAM does not necessarily govern all CSP operator access |
| Encryption and keys | TLS, encryption at rest, customer-managed keys, or risk-matched HSMs | Key location may differ from data location; services may need decryption access during processing |
| Networking & private links | Private endpoints, segmentation, egress policies | Private links alone do not dictate where a target service processes data |
| Monitoring & evidence | Audit logs, policy configs, contracts, access tests, data-flow audits | Evidence must reflect live reality and be re-checked after every change |
| Lifecycle & deletion | Retention rules, lifecycle policies, backup rules, partner deletion requests | Replicas, archives, and deletion timelines depend on each service's capabilities |

## 6. Mapping Against Cloud Deployment Models

Public cloud, private cloud, hybrid cloud, and multi-cloud describe **who operates infrastructure and which environments a system spans**. They do not automatically determine availability, geographic reach, or data control. Every property requires deliberate design choices.

| Model | Potential Advantages | Additional Risks or Effort |
|---|---|---|
| **Public cloud, single region** | Simplifies intra-region latency, networking, and operations | Cross-region DR needs its own plan; verify service/tenant boundaries and data constraints |
| **Public cloud, multi-region** | Serves multiple geographies and reduces single-region outage exposure | Replication, routing, consistency, egress, incident coordination, and cross-border data flows |
| **Private cloud / on-premises** | Increases direct control over servers, networks, and certain operator rights | Enterprise owns most HA, DR, patching, capacity, and verification; physical location alone does not prove compliance |
| **Hybrid cloud** | Keeps sensitive data in restricted environments while using cloud where suitable | Connectivity, latency, authorization, data tracking, and shifting trust boundaries grow complex |
| **Multi-cloud** | Mitigates certain provider dependencies and meets feature/geographic needs | Dual IAM, networking, observability, incident response, higher cost, plus shared application-layer risks |

One region in Provider A and one region in Provider B are not automatically **fully independent failure domains**. They may share Internet transit, DNS, identity, deployment pipelines, misconfigurations, or common libraries. Evaluate along the actual dependency chain.

## 7. Architectural Example: Multi-Region Booking Platform

Suppose a booking product serves users across multiple countries. Business stakeholders provide three **illustrative** requirement sets:

- **Availability:** booking creation has a 99.9% SLO per 30 days; for full-region loss, target 60-minute RTO and 5-minute RPO.
- **Geography:** distant users need fast image loading; not every write transaction must execute in the user's nearest region.
- **Data:** user PII and booking records require controlled storage/processing locations; permitted regions are approved by Legal and data owners. Public promotional images follow different distribution rules than PII.

### 7.1. Reference Architecture

~~~mermaid
flowchart TB
    USERS[Users across regions] --> EDGE[CDN / WAF / Global routing]
    EDGE --> WEB[Web app or API]
    subgraph R1[Primary region within permitted scope]
        API1[API - multi-zone]
        DB1[(Primary DB - multi-zone HA)]
        OBJ1[(Object storage)]
        API1 --> DB1
        API1 --> OBJ1
    end
    WEB --> API1
    DB1 --> REP{Does policy permit replication?}
    REP -->|Yes| R2[(Replica / backup in approved DR region)]
    REP -->|No| LOCAL[(Isolated backup within permitted scope)]
    API1 --> OBS[Location-governed logs / metrics / traces]
    API1 --> THIRD[Payment partner - data flow evaluated]
~~~

This diagram intentionally separates **"is replicating data to a second region permitted?"** from **"is DR required?"** If the intended standby site sits outside approved boundaries, you cannot simply turn on cross-region replication. Choose an approved site or adjust the DR strategy and sign off on residual risks with the business.

### 7.2. Classifying Data to Drive Decisions

| Data Class | Goal | Candidate Design | Verification |
|---|---|---|---|
| Public promotional images | Low latency, high throughput | Object storage + global CDN if policy permits | Cache policy, purge behavior, edge PoP locations, egress costs |
| Customer PII | Controlled privacy and placement | Store, process, back up, and govern access within approved scope | Data-flow map, region policies, access tests, logs |
| Booking transactions | Correctness, no double-booking, recoverability | HA database, proper transactions, idempotency; DR aligned to RTO/RPO | Zone-loss test, restore test, post-failover reconciliation |
| Logs and telemetry | Observability and incident investigation | Scrub sensitive fields; store logs per policy | Sample log inspection, retention, access control, actual storage region |
| Tokens / secrets | Protect service credentials | Secret manager, least privilege, rotation, never log | Secret revocation drill, audit, pipeline checks |

### 7.3. Three Options and Their Trade-Offs

**Option A — Single region, multi-zone.** App and database run HA within one region; CDN serves public assets. Strong option when zone fault tolerance is high priority while region-wide DR is not yet mandated or feasible. Drawback: region loss or shared control-plane outages can cause major disruption; document and accept this residual risk.

**Option B — Two regions, active-passive.** Keep primary in an approved region with standby capacity and compliant data sync to an approved DR region. Trade-off: idle standby cost, replication, runbooks, failover tests, non-zero RPO risk under async replication, and failback complexity.

**Option C — Multi-region, active-active.** Distribute APIs and potentially data to serve users across regions. Fits when latency or availability targets justify complexity. Challenges: keeping bookings consistent, preventing double writes, conflict resolution, user routing, cost, and cross-border data governance. Never choose this simply because "more regions is better."

Across all three options, verify whether proposed SLO/RTO/RPO targets are genuinely achievable. Never infer a 5-minute RPO solely from a replication checkbox if lag spikes above 5 minutes under heavy load or network issues.

### 7.4. Sample Decision Matrix

For each option, score **pass / fail / needs verification** on every mandatory requirement first, before comparing cost and complexity.

| Criterion | A: Multi-Zone, Single Region | B: Two-Region Active-Passive | C: Two-Region Active-Active |
|---|---|---|---|
| Survive single-zone failure | Achievable when all critical components are distributed | Achievable when designed inside each region | Achievable when dependencies are properly designed |
| Survive full-region failure | Needs external rebuild/recovery plan; not inherent | Achievable if failover and standby data work | Achievable if app keeps operating when one region drops |
| Consistent transaction writes | Usually simpler to enforce | Must handle state during cutover | Most complex if writing across multiple regions |
| Global latency | CDN helps static assets; API still hits one region | Can serve reads elsewhere if engineered | Multiple options to serve near users |
| Data placement constraints | Fewer sync flows, yet still check logs/backups | Viable only when DR region and flows are permitted | Requires rigorous review of storage, processing, routing, and sync |
| Cost and operations | Usually lower for equivalent load and services | Higher due to standby capacity and drills | Often highest due to duplication, ops, and conflict resolution |

Statements marked "achievable" are **design capabilities**, not test results or CSP guarantees.

## 8. Design Workflow: From Requirements to Verification

### Step 1 — Split Requirements into Three Criteria Sets

Write measurable criteria for each axis:

| Group | Questions to Quantify |
|---|---|
| Availability | Which behavior does the SLI measure, what SLO over what window, which failures must be survived, what RTO/RPO per business flow? |
| Geography | Where are users located, which features need low latency, where do reads/writes go, are there bandwidth/egress caps? |
| Data sovereignty | Which data classes, where stored/processed/backed up, who can access, are cross-border transfers allowed, what evidence is required? |

If requirements merely say "99.99% uptime", "global", or "domestic data", clarify exact meaning and scope before picking a model.

### Step 2 — Map Resources, Dependencies, and Data Flows

Include users, edge, APIs, queues, compute, databases, caches, storage, identity, KMS, DNS, logs, CI/CD, backups, partners, and operations teams. Tag each relevant component with its region, zone, legal entity, or environment. Mark primary write paths, read paths, replication streams, and support access channels.

### Step 3 — Identify Failure Domains and Single Points of Failure

Ask systematically: if one process, node, zone, region, network provider, control plane, or partner goes down, which functions fail? Which recover automatically, which need manual intervention, and which data risks inconsistency?

### Step 4 — Co-Design Topology and Data Policies

Evaluate single-region/multi-zone, multi-region, hybrid, or multi-cloud options alongside data residency rights. Every choice to replicate, cache, fail over, or adopt a new managed service can alter your data-processing footprint.

### Step 5 — Assign Owners and Controls

Specify who configures replication, manages the region allowlist, approves new data flows, handles incidents, verifies backup/restore, and coordinates with the CSP. Separate what the CSP operates from what the customer must configure and evidence.

### Step 6 — Implement Automated Controls

- Restrict deployment regions via policies and IaC checks where supported.
- Segregate data by sensitivity; minimize payloads sent to logs, edge nodes, and partners.
- Audit backups, snapshots, replicas, lifecycles, keys, and unintended access paths.
- Harden IAM, private connectivity, secrets, and cross-environment operational access.
- Alert on SLIs, replication lag, backup failures, error spikes, cost anomalies, regional latency, and sensitive policy changes.

### Step 7 — Inject Faults and Audit Data Paths

Test instance crashes, zone outages, lost dependencies, and full-region failover within safe bounds; measure detection, routing, recovery, and data reconciliation times. Test accidental deletes, restoring older datasets, unauthorized access attempts, and sensitive data leaking into logs. Inspect where logs/backups/caches are actually created—not just where the DB was configured.

### Step 8 — Review Upon Change

Whenever adding regions, enabling CDNs, onboarding SaaS tools, changing HA modes, entering new markets, or upgrading services, update the requirements matrix, data-flow map, threat model, runbooks, and compliance evidence.

## 9. Well-Architected Evaluation

| Perspective | Questions to Ask | Intentional Trade-Offs to Accept |
|---|---|---|
| **Reliability** | Does it survive target failure domains with measured RTO/RPO? | Multi-zone/region redundancy improves resilience while increasing state complexity |
| **Security** | Are data, keys, operator rights, and flows properly governed? | Strict residency controls may restrict service choices and DR strategies |
| **Performance Efficiency** | What must run near users versus near consistent data? | Edge/local processing cuts latency, yet cross-region writes risk lag or conflicts |
| **Cost Optimization** | What do replicas, standby, inter-region traffic, egress, and audits cost? | Multi-region raises fixed and transfer costs; single-region raises outage exposure |
| **Operational Excellence** | Who triggers failover, verifies data, and enforces placement policies? | Complex topologies demand regular drills, observability, and clear ownership |
| **Sustainability** | Are resources, caches, or replicas duplicated beyond actual need? | Redundancy is essential for reliability, yet overprovisioning wastes resources |

Well-Architected is not the name of one fixed configuration. It is a discipline for weighing competing objectives, recording residual risks, and selecting solutions suited to business context.

## 10. Common Mistakes

| Misconception | Why It Is Wrong | What to Check Instead |
|---|---|---|
| "Three instances in one zone equals HA." | A zone failure can take down all three instances | Placement, dependencies, and zone fault tolerance |
| "Multi-zone survives a full-region outage." | All zones still sit inside the same region | DR topology, recovery region, and failover procedures |
| "Multi-region removes the need for backups." | Logical data corruption replicates to every region | Independent backups, PITR, retention, restore drills |
| "A global CDN means the app is active-active." | CDNs may cache only static content while APIs and DB stay in one region | Request path to origin, processing location, and data placement |
| "Putting data in a domestic region guarantees sovereignty." | Logs, replicas, operator access, contracts, and external tools can cross borders | Full inventory, data flows, and jurisdictional rights |
| "Encrypting data solves all cross-border transfer rules." | Services may need decrypted access during processing; laws may impose extra rules | Processing purpose, key control, recipients, and applicable regulations |
| "Two CSPs eliminate all single points of failure." | Login, DNS, app code, and pipelines can remain shared dependencies | Dependency graph and failure drills |
| "High vendor SLA guarantees high app SLO." | A component SLA excludes your configs and full business flow | End-to-end SLIs, error budgets, fault tests, and contract limits |

## 11. Scenario Exercises

### Exercise A — Single-Region E-Commerce App

An API runs three instances behind a load balancer, all inside the same zone. The database sits in that same zone. The product owner requires surviving a single-zone outage.

**Question:** Does this pass? What needs to change?

**Solution guidance:** Not yet. Spread compute across multiple zones, use multi-zone load balancing and health checks, configure the database and stateful components for zone fault tolerance, audit shared dependencies, and drill zone-isolation failures.

### Exercise B — Multi-Country CDN

An application distributes public images via CDN across multiple countries. Its API and database sit in one region. Users complain that booking remains slow.

**Question:** Can we claim the system is globally distributed?

**Solution guidance:** Only the public asset delivery layer is distributed. Measure API round-trip paths, database latency, synchronous processing, and cross-region calls; improve with targeted caching, fewer round trips, read-path separation, or additional compute regions if business and data policies allow.

### Exercise C — Enabling an Overseas Replica

A team wants to add a read/DR replica in an overseas region for higher reliability. Company policy mandates strict location and access limits for customer data, yet no approved region list exists yet.

**Question:** Should they enable the replica immediately?

**Solution guidance:** No. First identify data classes, storage/processing/backup limits, authorized parties, and applicable laws; obtain formal region approval per organizational process. In parallel, evaluate compliant intra-boundary DR, isolated backups, multi-zone tuning, and document region-loss risk for business sign-off. Never assume replication is permitted simply because the CSP offers the toggle.

### Exercise D — Two Regions Missing RPO

An active-passive system automatically shifts traffic to a secondary region. During a drill, the API recovers in 10 minutes, but the last 25 minutes of writes are missing; targets are 30-minute RTO and 5-minute RPO.

**Question:** Which target passed, which failed, and what must be done?

**Solution guidance:** Under these assumptions and measurement markers, RTO passed while RPO failed. Measure replication lag, bound writes during failover, choose appropriate replication/write-acknowledgment modes, adjust cutover procedures, or renegotiate targets with business approval—then re-drill and reconcile.

## 12. Pre-Approval Architecture Checklist

- [ ] Business-flow SLIs/SLOs, RTO/RPO, and failure scenario scopes are clearly defined.
- [ ] Failure domains identified across process, node, zone, region, network, and shared services.
- [ ] HA and DR strategies, failover/failback plans, backups, restores, and drill results exist.
- [ ] API, database, replication, and cross-region latencies are measured or credibly estimated.
- [ ] Public content, sensitive data, transactional data, logs, telemetry, and backups are separated.
- [ ] Inventory lists where data is stored, processed, cached, backed up, and accessed by third parties.
- [ ] Data placement and access regulations/contracts verified per concrete service and deployment scope.
- [ ] IAM policies, encryption, keys, region allowlists, and operator permissions have owners and audit evidence.
- [ ] Cost, egress, operational overhead, consistency, and residual risks evaluated across options.
- [ ] Review process established when adding regions, changing deployment models, or switching providers.

**Core Takeaway:** availability answers **whether the service keeps working when faults happen**; geographic distribution answers **where components and data sit and whom they serve**; data sovereignty answers **who holds jurisdiction, control, and access over the data**. Sound architecture solves all three using concrete requirements, consistent design, and real test evidence.
