# Designing a Web Application from a Single Zone to Multiple Availability Zones

## 1. Exercise Objectives

A web application may run smoothly on several servers inside **a single Availability Zone (AZ)**. As user traffic grows, the risk of hardware failure, network loss, or power outages in that AZ becomes significant: an application with multiple instances where **all reside in a single fault domain** can still go down all at once.

This exercise belongs to the **Design Exercises** chapter of **CLOUD_ARCHITECTURE**. Learners start from business requirements, analyze single points of failure, and then design and rehearse a migration path for a web application from **one AZ to multiple AZs within the same region**. The lesson links decisions on **networking, compute, data, and deployment models** to trade-offs in **reliability, security, scalability, cost, and operations**, while self-evaluating against **Well-Architected** principles.

After this lesson, you will be able to:

1. Distinguish **region**, **AZ**, **multi-AZ**, and **multi-region**, avoiding misuse of protection scope.
2. Turn business availability and recovery goals into verifiable **SLI/SLO, RTO, and RPO** criteria.
3. Design a multi-tier web architecture, place components properly across AZs, and handle session state, storage, and databases.
4. Plan capacity for the complete loss of one AZ, identifying bottlenecks and redundancy costs.
5. Choose migration sequencing, deployment methods, rollback plans, fault injection tests, and acceptance criteria.

This is an **architecture design exercise** with assumed data and figures for practice. Service limits, SLA levels, data replication capabilities, product names, and specific pricing must be verified against the actual provider and configuration before implementation.

### 1.1. Understanding Geographic Units Correctly

| Concept | Meaning | Failures mitigated |
|---|---|---|
| **Region** | Logical geographic location of a cloud provider, which may contain multiple AZs | Determines data residency, latency, and service availability scope |
| **Availability Zone (AZ)** | Isolated infrastructure domain within a region, designed to reduce shared failures with other AZs | Outages affecting an individual AZ |
| **Multi-AZ** | Placing critical components or replicas across at least two AZs in the **same region** | Reduces risk of total application outage when one AZ fails |
| **Multi-region** | Deploying or replicating services across multiple regions | Can help handle region-level disasters, provided failover and data are designed appropriately |

**Design limitation:** multi-AZ does not equal multi-region. Region-wide failures, shared configuration errors, accidental data deletion, leaked credentials, or buggy application releases deployed everywhere simultaneously can still impact all AZs. Thus, multiple AZs are one layer of a reliability strategy, not a guarantee of zero downtime.

## 2. Business Problem: A Growing Retail Portal

You are the architect for **ShopHub**, a hypothetical retail web application. Currently, the entire web frontend, API, background workers, and a single database all run in AZ-A of one region. The system previously suffered an outage when AZ-A lost connectivity. The product team wants the system to keep operating when **any single AZ** stops serving.

Workload and requirement assumptions:

| Attribute | Exercise value | Notes |
|---|---:|---|
| Normal-hour traffic | 300 requests/second | Total requests to web/API |
| Peak traffic to sustain | 1,200 requests/second | Sustained for at least 15 minutes |
| Initial data size | 2 TB of order and account data | Needs backup and replica strategy |
| User files | 5 TB of product images, invoices | Do not store on app local disks |
| Service availability SLO | 99.95% per 30-day window | Define valid requests explicitly in measurement |
| Latency SLO | p95 under 400 ms for catalog reads during normal operation | Catalog reads differ from checkout |
| Single-AZ failure recovery | RTO no more than 5 minutes | Measured from start of outage until service meets serving threshold |
| Loss of confirmed orders | Zero loss accepted for orders reported as succeeded | Must verify DB commit/failover semantics |
| Loss of auxiliary product data | Target RPO no more than 5 minutes | Rebuilding indexes/caches is acceptable |
| Security | Never expose database publicly; only account owners view their orders | Enforce role- and data-level authorization |
| Scope | Tolerate **one AZ** failure; automatic region failover not yet required | Region outage is a separate expansion problem |

With 30 days = 43,200 minutes, a **99.95%** SLO corresponds to roughly **21.6 minutes of unavailability** in that window under simple uniform time-based math. In practice, SLOs may be measured by successful request ratio, where you **cannot directly convert** request ratio to downtime minutes if traffic varies. Likewise, a 5-minute RTO target for one AZ outage **does not mean** the system can suffer repeated 5-minute outages and still meet its SLO.

### 2.1. Questions to Clarify Before Drawing Diagrams

- **Critical business paths:** do product catalog, cart view, order placement, payment, and image loading share the same priority?
- **"No lost orders" criteria:** must every acknowledged write survive failover? Which DB mechanism proves this?
- **SLO during incidents:** must the system still serve **all** 1,200 requests/second during an AZ loss, or is declared degradation acceptable?
- **Dependency boundaries:** are third-party payment services, DNS, identity systems, and CDN outside our direct control?
- **Deployment constraints:** is scheduled downtime allowed, what is the max extra budget, and are there IP retention, data residency, or compliance rules?

In the reference solution, we assume **all valid traffic must be served at the 1,200 requests/second peak even when one AZ is lost**, forcing the architecture to provision spare capacity. If the business accepts degraded service quality, the design can use fewer resources, provided the degradation level and acceptance terms are documented.

## 3. Evaluating the Initial Architecture

~~~mermaid
flowchart LR
    U["Users"] --> D["DNS"]
    D --> LB["Load balancer"]
    subgraph AZA["Region R / AZ-A"]
      APP1["Web + API instance 1"]
      APP2["Web + API instance 2"]
      DB[("Single-node database")]
      DISK[("File storage disk")]
      W["Background worker"]
      APP1 --> DB
      APP2 --> DB
      APP1 --> DISK
      APP2 --> DISK
      W --> DB
    end
    LB --> APP1
    LB --> APP2
~~~

**Two instances in the same AZ do not create multi-AZ.** A network or power outage in AZ-A makes both the application and data unreachable. Instances may also share a single DB, local disk, NAT, load balancer, or DNS endpoint. Moving half the web tier to AZ-B while leaving a single database in AZ-A still fails to eliminate transaction outage risk.

### 3.1. Single Point of Failure (SPOF) Analysis Table

| Component | Initial state | Impact if AZ-A fails | Mitigation to consider |
|---|---|---|---|
| Web/API | Multiple machines in AZ-A | Nowhere left to receive requests | Replicas in AZ-B/C, health checks, and multi-AZ routing |
| Database | Single primary in AZ-A | Cannot read/write orders | Choose HA DB with cross-AZ replica/failover, backups, and commit verification |
| Login sessions | Stored in each instance's memory | Sessions lost; users must re-login | Independently verifiable tokens or HA session store |
| Images and invoices | Local disk in AZ-A | May become inaccessible or lost | Durable object storage with explicit access controls |
| Background worker | Running solely in AZ-A | Queue processing halts | Multi-AZ workers, durable queue, idempotency |
| Egress / NAT | Single device or single AZ | Some outbound requests fail | Consider per-AZ egress and private endpoints where appropriate |
| Deployment | Updating all instances at once | Bad release impacts every instance | Rolling/canary deployments preserving serving capacity |

**Mini-exercise:** flag which components are mandatory for checkout versus secondary features. If the image service fails, you can temporarily serve placeholder images; if the order database fails, the system can pause checkout while keeping catalog browsing alive via suitable caching. This classification drives investment priority.

## 4. Choosing the Target Architecture

To solve the problem, pick a **region with at least three available AZs for the required services**. Spread components across **AZ-A, AZ-B, and AZ-C**. The application receives traffic via a multi-AZ load balancer; a managed database service uses cross-AZ HA mechanisms. Storage, queues, secret management, and monitoring are evaluated by **their actual fault-tolerance scope**—never assume "managed" automatically means zero SPOF.

~~~mermaid
flowchart TB
    USER["Users"] --> EDGE["DNS + CDN/WAF if needed"]
    EDGE --> LB["Multi-AZ load balancer"]
    subgraph REGION["Region R: one region, three AZs"]
      subgraph A["AZ-A"]
        APPA["App replicas A"]
        WA["Worker A"]
      end
      subgraph B["AZ-B"]
        APPB["App replicas B"]
        WB["Worker B"]
      end
      subgraph C["AZ-C"]
        APPC["App replicas C"]
        WC["Worker C"]
      end
      HA[("Managed HA DB / cross-AZ replica")]
      OBJECT[("Durable object storage")]
      QUEUE[["Durable queue"]]
      CACHE[("HA cache / session store")]
    end
    LB --> APPA
    LB --> APPB
    LB --> APPC
    APPA --> HA
    APPB --> HA
    APPC --> HA
    APPA --> CACHE
    APPB --> CACHE
    APPC --> CACHE
    APPA --> OBJECT
    APPB --> OBJECT
    APPC --> OBJECT
    APPA --> QUEUE
    APPB --> QUEUE
    APPC --> QUEUE
    QUEUE --> WA
    QUEUE --> WB
    QUEUE --> WC
    WA --> HA
    WB --> HA
    WC --> HA
~~~

The diagram above is a **logical model**. The DB and cache are drawn as single nodes for brevity, but in reality comprise primaries, standbys/replicas, or quorum members placed in distinct AZs; roles and failover paths must be explicit in the physical deployment. A database with a read-only replica does not automatically recover from write failures without configured promotion/failover.

### 4.1. Why Choose Three AZs?

In principle, **two AZs** can keep a service running after one AZ fails. With **three AZs**, the system gains better load distribution options and—depending on the database or consensus system—can preserve quorum when one member fails. However, available AZ count and quorum/replica placement **depend on each specific service**. Do not assume any DB running across three AZs fails over safely automatically.

Recommendation for this problem: **three AZs for the application tier**, and DB HA matching the selected service's model and limits. When budget or service availability limits you to two AZs, redesign the capacity margin, risk profile, and RTO instead of blindly copying a three-AZ layout.

### 4.2. Which Components Run Active-Active vs. Active-Standby?

| Tier | Suggested model | Reason |
|---|---|---|
| Stateless Web/API | **Active-active** across 3 AZs | Load balancer distributes requests; surviving AZs absorb traffic on failure |
| Independent workers | **Active-active** across 3 AZs | Queue dispatches jobs; workers in failed AZs are replaced |
| Transactional write DB | **Single writer + HA standby**, or multi-writer with verified consistency contract | Simplifies order write correctness; requires tested failover |
| Cache | Multi-AZ HA, or treat cache as rebuildable | Cache misses must never lose business data |
| Object storage | Durable service with appropriate scope | Decouples user files from instance lifecycles |
| Load balancing layer | Managed, multi-AZ routing | Fast health checks and unhealthy endpoint removal; verify SLA and scope |

**Active-active does not mean infinite capacity:** surviving AZs must have sufficient compute, quotas, connection limits, and headroom across the database, queue, cache, NAT, and downstream dependencies.

## 5. Network and Security Design

### 5.1. Logical Network Diagram

Inside a VPC/VNet or equivalent network, create **dedicated subnets per AZ** separated by role:

~~~mermaid
flowchart TB
    INTERNET["Internet"]
    WAF["WAF / CDN, as needed"]
    INTERNET --> WAF
    WAF --> PUBLIC["Public entry: multi-AZ LB"]
    subgraph NETWORK["Private network within region"]
      subgraph A["AZ-A"]
        AAPP["Private app subnet A"]
        ADB["Private data subnet A"]
      end
      subgraph B["AZ-B"]
        BAPP["Private app subnet B"]
        BDB["Private data subnet B"]
      end
      subgraph C["AZ-C"]
        CAPP["Private app subnet C"]
        CDB["Private data subnet C"]
      end
    end
    PUBLIC --> AAPP
    PUBLIC --> BAPP
    PUBLIC --> CAPP
    AAPP --> ADB
    BAPP --> BDB
    CAPP --> CDB
~~~

Arrows into data subnets illustrate network segmentation; **the actual database writer may reside in a single AZ**, so requests from every app subnet can traverse across AZs to that writer. Network security must permit valid cross-AZ paths while denying unnecessary access.

**Illustrative IP addressing example:** the application network uses private range `10.40.0.0/16`; allocate non-overlapping subnets with room for autoscaling and upgrades. Exact CIDRs must be checked against corporate networks, site-to-site VPNs, and peering connections to avoid collisions with existing systems.

### 5.2. Baseline Security Rules

1. Only the **load balancer/ingress** has endpoints receiving Internet traffic; app instances and databases sit in private subnets without public IPs unless strictly required.
2. Enforce HTTPS from users to ingress and encrypt between sensitive tiers; use appropriate certificates and secret/identity management.
3. Firewalls/security groups or equivalent policies allow only **LB → app** and **app → DB/queue/object** on required protocols and ports; enforce least-privilege cloud IAM.
4. Configure egress properly: if workers/apps call external Internet APIs, consider independent per-AZ NAT/egress to reduce cross-AZ fate sharing; prefer private endpoints for internal cloud services when available and cost-effective.
5. Separate permissions for app transactional read/write, workers, deployers, human operators, and backup services. Retain audit logs for permission changes and sensitive actions.
6. Enforce rate limiting at ingress, risk-appropriate DDoS/WAF protection, tenant/session checks at the application tier, and encryption at rest.

Never use **availability** as an excuse to weaken security: replicating servers across three AZs while sharing overly broad admin credentials or exposing databases publicly simply widens the attack surface. At the same time, avoid placing a single security control inside one AZ and accidentally creating a new SPOF.

## 6. Compute Design and Capacity to Survive One AZ Loss

### 6.1. Calculating Mandatory Capacity

Suppose load testing shows **one group of app instances in one AZ** is sized and measured to sustain **600 requests/second** within acceptable latency. With three AZs:

~~~text
Peak traffic to serve                        = 1,200 requests/second
Active AZ count                              = 3
Surviving AZs after losing one AZ            = 2
Minimum capacity per surviving AZ            = 1,200 / 2 = 600 requests/second
Total 3-AZ capacity during normal operation  = 3 × 600 = 1,800 requests/second
Total capacity after losing one AZ           = 2 × 600 = 1,200 requests/second
~~~

This provisioning represents **50% extra capacity over peak demand**, since normal peak requires 1,200 while 1,800 requests/second is maintained. It allows absorbing peak load immediately after an AZ outage **without relying entirely on autoscaling reacting in time**. If you provision only 400 requests/second/AZ because normal traffic splits evenly to 1,200, losing one AZ leaves only 800—a 400 requests/second shortfall before scaling completes.

**Calculation caveats:** the division above assumes balanced LB distribution, identical instances, no shared bottlenecks, and that 600 requests/second was verified at SLO-compliant p95/p99 latency. The database, cache, network throughput, connection pools, memory, and provider quotas must all handle the full 1,200 requests/second on two surviving AZs.

### 6.2. Auto Scaling and Deployment Scheduling

- Use autoscaling to add or remove replicas based on CPU, concurrency, latency, and request rate—not CPU alone for I/O-bound apps.
- Enforce **minimum per-AZ counts** aligned with fault tolerance; configure placement/spread rules so the scheduler never packs replicas into one AZ.
- On Kubernetes, use **topology spread constraints** or equivalents; configure pod disruption budgets, readiness/startup/liveness probes, and per-AZ node pool limits. On VMs or managed container services, configure multi-AZ instance groups and verify actual placement.
- Rolling deployments must preserve **post-AZ-loss capacity**; never deploy across all AZs at once and drop healthy replica counts below threshold. Canary or zoned rolling deployments help limit software-bug blast radius.
- Distinguish a **healthy instance** from a **ready instance**: readiness probes must reflect true serving readiness so traffic is not routed to freshly booted instances still warming up.

### 6.3. Sessions and Statelessness Requirements

An application keeping sessions in a single instance's RAM loses sessions whenever the LB shifts requests to another AZ. Common solutions:

- **Stateless access tokens** with expiration and proper signature/revocation checks; avoid stuffing volatile business state into tokens.
- **Centralized HA session store** spanning multiple AZs, with configured TTLs, replication, and secret protection.
- Do not rely on **sticky sessions** as a fault-tolerance mechanism; affinity may improve locality, but it does not survive an AZ outage.
- Move file uploads to object storage; submit background jobs to a queue instead of holding them locally on one machine.

Run this test: **log in → add items to cart → terminate the instance/AZ serving the request → continue browsing/checkout**. If the user loses their cart, identify what state still resides in AZ-A's memory or disk.

## 7. Database: Write Recovery Matters More Than Replica Count

For a retail application, the database is the hardest part of multi-AZ. Three stateless app replicas still cannot create orders if the sole database writer sits in an unreachable AZ.

### 7.1. Distinguishing HA from Backups

| Mechanism | Problem solved | What it does not solve on its own |
|---|---|---|
| **Cross-AZ replica/standby** | Maintains a copy to fail over to when primary fails | Automatic failover speed, consistency, and RPO depend on configuration |
| **Synchronous commit** | Protects acknowledged transactions if the system confirms only after durable replica write | Does not protect against accidental deletes or logic bugs |
| **Asynchronous replica** | Lowers write latency; adds read capacity in some engines | Has replication lag; latest writes may be lost on promotion |
| **Backups/PITR** | Restores corrupted or accidentally deleted data to a prior timestamp | Not an automatic sub-minute failover path |
| **Multi-writer** | Can scale or increase write availability | Conflicts, split-brain, consistency; risky without understanding DB contracts |

**"Zero lost confirmed orders"** forces the team to verify the commit, durability, and failover semantics guaranteed by the DB service. Never promise **RPO = 0** solely because a checkbox labeled "Multi-AZ" is enabled: test primary failure right after commit, connection drops mid-commit, mid-transaction failover, and replication lag.

### 7.2. Failover Flow When the Primary Is Lost

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Web/API
    participant D as Database endpoint
    participant P as Primary AZ-A
    participant S as Standby AZ-B
    C->>A: Create order with idempotency key
    A->>D: Write order in transaction
    D->>P: Route write operation
    P--xD: Primary loses connectivity
    Note over D,S: HA mechanism detects failure, elects/promotes standby
    D->>S: Connect to new writer after failover
    Note over A,D: Drop stale connections; bounded retry and state check
    A->>D: Look up by idempotency key
    D->>S: Read committed result
    S-->>A: Order exists or not completed
    A-->>C: Return verifiable status
~~~

This sequence depicts an **uncertain-outcome scenario**, not an assumption that the transaction committed before the primary dropped. The backend must **look up by idempotency key** and return the corresponding state; never blindly create a new order or charge payment twice when the previous outcome is ambiguous.

### 7.3. Operational DB Questions You Must Answer

1. When the primary fails, how does the service verify a standby is eligible, who triggers failover, and how long does it usually take?
2. How does the writer endpoint update? Do connection pools refresh, do DNS caches honor low TTLs, and do retries have deadlines?
3. Are open transactions rolled back or left indeterminate? Are critical operations guarded by idempotency and reconciliation?
4. Is there stale-read risk if reads shift to a read-only replica? Which read paths require **read-after-write consistency**?
5. How are backups, PITR, and **isolated-environment restore drills** verified?
6. Does losing one AZ shrink quorum enough to halt writes? If so, does the design still meet the required RTO?

If the existing database cannot move to HA without a version upgrade or data-model change, treat that as a **dedicated migration workstream** requiring staging tests, backups, and a rollback plan.

## 8. Data Dependencies Outside the Main Database

### 8.1. Static Files and User Content

Product images, invoice documents, and report exports must not rely on disks attached to a single AZ. Move them to **object storage** or a managed storage service with appropriate durability and availability. Define object naming conventions, versioning if needed, lifecycle rules, and read/write permissions. The application issues scoped access URLs per user permission while keeping the underlying bucket/store private.

Regional object storage is typically distributed across multiple AZs by the provider, yet **not every storage class/tier or product offers the same redundancy scope**. Verify documentation and configuration for the chosen storage type rather than assuming from the word "object."

### 8.2. Caches and Search

Caches hold rebuildable data, so they can use an HA cluster or fall back to the source of truth; however, after an AZ outage, simultaneous cache misses can trigger a **cache stampede** against the database. Mitigate this with jittered TTLs, request coalescing, concurrency limits, pre-warming, and rate limiting.

A search index is a *projection* of source data; build a replay/rebuild pipeline in case an AZ-local index is lost. Decide whether search is business-critical or allowed to degrade temporarily during recovery. **Never treat cache or search index contents as the source of truth for orders.**

### 8.3. Queues, Workers, and Scheduled Tasks

Place workers across multiple AZs, reading from a **durable queue** with appropriate HA scope. Workers must:

- Execute **idempotently**, because a job may be redelivered if a worker in AZ-A crashes mid-flight.
- Cap retries, use backoff, and route failures to a dead-letter queue (DLQ); avoid infinite retry loops when a downstream dependency is down.
- ACK messages **only after** required business state is durably saved; set appropriate lease/visibility timeouts for longer jobs.
- Avoid running a **single scheduler** pinned to AZ-A; if multiple replicas evaluate schedules, use leader election/leases or business locks so critical tasks do not run twice.
- Implement reconciliation for stuck jobs and alert on **oldest message age**, retry rates, and DLQ depth.

### 8.4. External Dependencies

Payment providers, email services, auth providers, tax engines, or partner APIs can still suffer regional or global outages. Internal multi-AZ cannot cure external outages. Define business fallbacks, deadline-bounded timeouts, circuit breakers, and concurrency caps. For side-effecting calls like payments, require idempotency keys and status reconciliation when outcomes are unclear; **never blindly retry after a timeout**.

## 9. Designing RTO, RPO Targets, and Fault Detection

**Recovery Time Objective (RTO)** is the maximum downtime the business accepts for a defined recovery scenario. **Recovery Point Objective (RPO)** is the maximum acceptable data loss, usually expressed as a time window of lost writes.

### 9.1. RTO Must Include Detection and Traffic Shift

Example breakdown of a **5-minute RTO** when losing one AZ:

| Step | Illustrative budget | Mechanism |
|---|---:|---|
| Detect unresponsive instance/AZ | 45 seconds | LB health checks and monitoring |
| Remove unhealthy targets and shift routing | 30 seconds | LB updates healthy target list |
| App connection recovery / cold cache | 45 seconds | Pool reconnect, load shedding, cache warming |
| Database failover and reconnect | 90 seconds | Managed HA DB; endpoint refresh and bounded retries |
| Transaction verification and SLO stabilization | 60 seconds | Synthetic checkout, DB/queue health checks |
| **Total budget** | **270 seconds = 4.5 minutes** | 30-second buffer inside the 5-minute RTO |

Steps may **overlap** or take longer depending on the cloud, service, health-check intervals, networking, and live traffic. This table is a budget plan for **measurement and verification**, not a guaranteed provider failover SLA. If actual p99 DB failover takes 4 minutes, adding routing and verification can exceed the RTO—requiring an architecture change or renegotiating the target.

### 9.2. RPO by Data Category

| Data | Practical requirement | Verification mechanism |
|---|---|---|
| Successfully paid orders | Zero loss of confirmed records | Verify DB durability/commit mode and run failover drills; reconcile state via idempotency keys |
| Uncertain payment outcomes | Never double-charge | Provider references, idempotency keys, lookup APIs, and reconciliation |
| Shopping cart state | Minimize lost state; confirm with business | HA session/cart store, tested across AZ switches |
| Confirmed uploaded images/files | Preserve objects intact | Appropriately scoped durable storage with versioning/checksums if needed |
| Search index and cache | Rebuildable within bounds | Rebuild/replay from source data; monitor backlog |

A daily backup is vital for recovering from accidental deletion, yet **cannot satisfy** zero confirmed-transaction loss during an AZ failover. Conversely, synchronous replicas do not replace backups because accidental deletes replicate to replicas as well.

## 10. Phased Migration Plan

Migrating from single-AZ to multi-AZ should minimize simultaneous changes and keep steps reversible. Changing database topology or data storage can be trickier than changing compute; isolate risks and test thoroughly before shifting production traffic.

| Phase | Work items | Exit criteria |
|---|---|---|
| **0. Baseline** | Measure traffic, latency, error rates, DB throughput, connections, and dependencies; capture initial state diagrams | Baseline SLO/SLIs and load metrics recorded |
| **1. Externalize app state** | Move sessions, files, and background jobs off single-instance RAM/disks | Can stop any single instance without losing carts, files, or jobs |
| **2. Expand network** | Create app subnets and network/permission rules for AZ-B/C; test routing/egress | Apps in every AZ can reach required dependencies |
| **3. Add app replicas** | Deploy instances/workers in AZ-B/C; configure LB health checks and autoscaling | Live traffic spreads across multiple AZs; per-AZ capacity sufficient |
| **4. Enable DB HA** | Select HA model/service, cross-AZ standby/replica, backup/PITR, failover endpoint | DB failover drill meets correctness and RTO targets |
| **5. Isolate dependencies** | Check cache/queue, NAT, schedulers, pools, and timeouts; enforce idempotency | No critical transaction path depends exclusively on AZ-A |
| **6. Monitored traffic shift** | Canary or percentage-based traffic ramp; watch latency/errors/DB and rollback triggers | Advance only after metrics meet agreed thresholds |
| **7. AZ-loss drill and sign-off** | Block traffic / simulate AZ outage; measure RTO/RPO/load/cost | Checklist passed; drill report and on-call runbooks finalized |

### 10.1. Details for High-Risk Steps

**Before migration:** take a consistent backup, verify restoring it into a test environment, snapshot configurations, and document connection-string/secret recovery. Provision networks, LBs, security policies, and autoscaling via Infrastructure as Code for repeatability.

**Migrating sessions:** if currently held in one web server's memory, roll out appropriate cookies/tokens or an HA session store and test logins across all replicas. For carts, ensure durable persistence; if cache-only, define recovery behavior on cache loss.

**Migrating local files:** you may need to backfill historical files while validating checksums, access permissions, and legacy URL mappings. Avoid writing to the old disk while reading from new object storage without consistency rules. Track backfill progress and handle concurrent file updates.

**Migrating the database:** bootstrapping/replicating 2 TB can take hours, increasing CPU, I/O, and network load. Monitor replication lag and transaction latency impacts, and never enable production failover untested. Some HA configuration changes cause brief interruptions; schedule and communicate them per change management.

**Traffic canary:** for example, step 5% → 25% → 50% → 100%, holding each stage long enough to observe p95/p99, error rates, DB locks, and saturation. These percentages illustrate *gradual progression*, not mandatory numbers. Sticky sessions and caches must be compatible before shifting users to new targets.

### 10.2. Specific Rollback Conditions

Rollback does not mean "shove everything back into one AZ" if the DB or data has moved to a new layout. Define rollback per layer:

- **Compute/traffic:** if error rates or p95 breach thresholds during canary, halt ramp-up, drain unhealthy instances from the LB, and revert to the healthy baseline target group.
- **Network configuration:** preserve the last known good state, using IaC to restore verified routes/security policies; never delete subnets or resources actively processing transactions.
- **Data layer:** never automatically roll back schemas or restore old snapshots once new writes have committed. Reverting requires backward migrations or reconciliation workflows to avoid losing orders.
- **Degraded features:** if the DB cannot accept writes, gracefully reject checkout rather than faking success, while keeping independent read features online.

**Change records** must name the decision owner, post-deploy observation window, abort signals, runbooks, backup checks, and incident escalation channels.

## 11. Fault Injection Drills: From Hypothesis to Evidence

Before running fault injection, confirm test scope, target resources, and an emergency kill switch. Prefer staging with simulated load first, then run in production only with agreed scope, approvals, and guardrails.

### 11.1. Test Scenario Matrix

| Scenario | Test action | Expected observation |
|---|---|---|
| **Loss of one app instance** | Stop one instance in AZ-A | LB removes failed target; traffic shifts to healthy replicas; sessions remain valid |
| **Total loss of AZ-A app tier** | Block traffic to all AZ-A app replicas or run controlled AZ failure | AZ-B/C serve 1,200 req/s within error/latency budgets on critical paths |
| **DB primary in failed AZ** | Trigger provider-supported failover in staging | Writer endpoint recovers, app reconnects; confirmed orders remain intact |
| **Worker crashes mid-job** | Kill worker after partial output | Job is reprocessed idempotently without duplicate side effects |
| **Cache node/AZ loss** | Simulate losing part of cache cluster | App tolerates cache misses, DB avoids stampede, source data stays accurate |
| **AZ-A egress failure** | Block AZ-A outbound path | Apps/workers in AZ-B/C still reach external dependencies |
| **Misconfigured LB/target health check** | App returns 200 while a critical dependency is down | Readiness catches dependency failure before routing live traffic |
| **Bad deploy in one AZ** | Release an intentionally broken canary in staging | Blast radius stays contained; rollback completes before error budget exhaustion |
| **Object storage permission failure** | Simulate access policy error | Graceful denial; alerts fire and no data leaks |
| **Payment timeout after commit** | Simulate timeout receiving response | Look up via idempotency key; never double-charge or double-order |

**RTO must be measured from the user's perspective**, not just when the cloud provider reports "failover completed." If the LB routes traffic but the app returns HTTP 500s because DB pools have not reconnected, the service has not recovered.

### 11.2. Detailed AZ-Loss Test Script

1. Generate synthetic traffic covering catalog reads, login, add-to-cart, and checkout, ramping up to **1,200 requests/second**. Attach correlation IDs, set checkout idempotency keys, and snapshot pre-test state.
2. Record a 10–15 minute baseline of request rate, p95/p99, HTTP 5xx, CPU, DB connections, cache hit rate, replication lag, and queue age.
3. Simulate the loss of AZ-A while **maintaining full incoming load** rather than throttling traffic to make the test pass easily.
4. Verify the LB stops routing new requests to failed targets; verify client timeouts and retries are bounded without cascading retry storms.
5. Verify DB failover completes, connection pools recover, and zero confirmed orders are lost. Reconcile ambiguous transactions via idempotency keys.
6. Test cross-AZ sessions/carts, uploaded images, unacknowledged jobs, and independent features.
7. Measure **RTO**, error budget burned, post-stabilization p95/p99, and failed request count. Sample business records against the DB.
8. Restore AZ-A and reintroduce targets gradually to avoid cold-cache or traffic surges causing a secondary incident; monitor load balance and replication.
9. Write a drill report capturing outcomes, timestamps, metrics, disproven assumptions, gaps to fix, owners, and the next drill date.

One successful drill proves only **the tested scenario under those conditions**. Long-term confidence requires repeating drills after major changes, under realistic load, and testing AZ recovery—not just AZ failure.

## 12. Observability, Alerting, and Runbooks

To verify SLO compliance, measure **end-to-end**, per AZ, and per dependency—not just instance CPU.

| Signal group | Required metrics / logs / traces | Anomaly indicators |
|---|---|---|
| **User experience** | Request success rate, p50/p95/p99, synthetic login/checkout | Checkout failing even while health checks pass |
| **Routing** | Healthy targets per AZ, requests and errors per AZ | One AZ receives traffic without responding |
| **Capacity** | RPS, concurrent requests, CPU/RAM, container restarts, queue depths | Surviving AZs saturate after failover |
| **Database** | Writer status, failover events, replication lag, connections, locks, commit latency | App fails on stale endpoints or DB overload |
| **Cache/queue** | Cache hit rate, oldest message age, retries, DLQ depth | Jobs stuck or DB hit by heavy cache misses |
| **Security** | WAF blocks, auth failures, secret rotation, IAM audit logs | Permission failures or anomalous config changes |
| **Cost** | Per-AZ compute, storage, cross-AZ transfer, NAT, DB HA, and logs | Spikes from cross-AZ chatter, over-provisioning, or verbose logs |

**Recommended alerts:** healthy target count drops below fault-tolerance minimum; surviving-AZ replica count insufficient; 5xx rate or p95 breaches SLO; DB failover stalls; queue age nears business deadline; replication lag climbs; unexpected egress cost jump.

An AZ-outage runbook should answer: who is on call, how to confirm which AZ failed, how to check LB routing and DB writer placement, when to freeze deployments, how to reconcile ambiguous transactions, criteria for re-enabling the recovered AZ, and how to compile the post-incident report. Manual recovery steps must be rehearsed and pre-authorized.

## 13. Cost Analysis and Trade-Offs

Multi-AZ is not free. Because the exercise requires surviving one AZ outage at peak load, **spare capacity must exist somewhere**. Relying purely on autoscaling once failure hits risks blowing the RTO due to instance boot times, quotas, or AZ capacity exhaustion.

### 13.1. Simple Estimation Model

Assume for comparison that one unit of app capacity of **600 req/s** costs **C per month** (symbolic unit):

| Architecture | Provisioned app capacity | Illustrative app cost | Surviving capacity after losing one AZ |
|---|---:|---:|---:|
| One AZ, two capacity units | 1,200 req/s | 2C | 0 |
| Three AZs, one unit per AZ | 1,800 req/s | 3C | 1,200 req/s |
| Three AZs, only 400 req/s per AZ | 1,200 req/s | Roughly 2C if linear | 800 req/s (short by 400) |

This table counts **app compute only**, excluding DB, cache, LB, data transfer, NAT, storage, backups, monitoring, or commitment discounts. Assuming **linear cost scaling** often breaks down at small scale or with services billed by startup time, utilization, and request count.

### 13.2. Cost Increases and Optimization Levers

- **Spare compute:** minimum instances/containers across AZs for immediate failover absorption; tune instance sizing and time-of-day scaling.
- **Database HA:** standby/replicas, replication storage/I/O, backup/PITR; pricing and features vary by product.
- **Networking:** cross-AZ data transfer, per-AZ NAT gateways/egress, traffic to a DB writer in another AZ, LBs, and private endpoints. Do not assume all intra-region traffic is free.
- **Cache/queue:** HA clusters or managed services cost more than single nodes but reduce outage risk.
- **Observability and operations:** metrics, traces, log retention, synthetic checks, load testing, drills, and on-call staffing.
- **Outage cost:** weigh infrastructure cost against lost revenue/transactions, brand trust, support load, and SLA penalties.

**Trading down to cut costs:** accept graceful degradation of non-critical features during an AZ loss, lower redundancy on non-real-time search/index/workers, and apply storage lifecycle tiering. Never strip transactional DB redundancy or weaken security if it violates acceptance criteria.

## 14. Well-Architected Evaluation of the Solution

| Pillar | Evaluation questions | Evidence / controls in this exercise |
|---|---|---|
| **Operational Excellence** | Can we deploy, roll back, and run drills reliably? | IaC, canary rollouts, runbooks, change logs, documented drills |
| **Security** | Do new AZs enforce the same network, access, and encryption boundaries? | Private app/DB subnets, least-privilege IAM, audits, secrets, object permissions |
| **Reliability** | Does losing one AZ stop the entire transaction pipeline? | Multi-AZ LB, app replicas, DB failover, idempotency, backups, RTO/RPO tests |
| **Performance Efficiency** | After an AZ loss, do p95 and capacity still meet peak load? | N+1 capacity, 1,200 req/s testing, autoscaling, DB/cache checks |
| **Cost Optimization** | Which redundancy pays off, and what cross-AZ costs arise? | C vs. 3C comparison, feature tiering, lifecycles, network cost tracking |
| **Sustainability** | Are we holding idle excess resources or doing wasteful retries? | Right-sizing, sensible autoscaling, data lifecycles, bounded retries |

There is no single optimal choice. **Three-AZ active-active** improves fault tolerance and lowers app failover delay at the cost of extra idle capacity. **Active-standby** can trim running resources on some tiers, but adds startup/switchover delay, data consistency concerns, and activation failure risk.

Document choices in an **Architecture Decision Record (ADR)**: context, SLO/RTO/RPO targets, options weighed, decision, trade-offs, residual risks, and verification plan. Never stop at "we picked three AZs so we are highly available."

## 15. Applied Exercise: Completing the Design Yourself

Step into the architect role. You may change technologies, provided you uphold the business requirements in Section 2—or explicitly flag which requirements must be renegotiated.

### Deliverables to Submit

1. **Current and target diagrams:** show region, three AZs, public/private networks, load balancer, web/API, workers, data services, DNS, and primary communication paths.
2. **SPOF and dependency table:** identify which features and AZs each component failure affects, plus mitigations.
3. **SLO/RTO/RPO table:** separate API availability, recovery time, and data loss; specify exact measurement methods.
4. **N+1 capacity plan:** prove 1,200 req/s survives one AZ loss across LB, DB, pools, queues, and network.
5. **Migration roadmap:** phases, exit criteria, gradual traffic shift, backups, and per-step rollback.
6. **Chaos/failover test matrix:** at least five scenarios, observed metrics, expected outcomes, and abort conditions.
7. **One-page ADR:** justify two vs. three AZs, the DB HA model, and redundancy costs.

### Essay Questions

**Question 1.** Three app replicas run across three AZs, but login sessions live in a single Redis node in AZ-A. What happens when AZ-A fails? What is the architectural fix?

**Question 2.** Two healthy AZs can each handle only 400 req/s, while peak traffic is 1,200 req/s. Can you claim single-AZ fault tolerance? What would you change?

**Question 3.** The database has a read replica in AZ-B using asynchronous replication. After AZ-A's primary fails, the app discovers an order reported as successful is missing from the replica. Why did this happen, and how must requirements or architecture change?

**Question 4.** Operations added plenty of app instances in AZ-B/C, yet checkout still fails when AZ-A goes down. Name at least three remaining dependencies to inspect.

**Question 5.** During a drill, the load balancer reroutes requests in 15 seconds, yet users cannot successfully place orders again for 4 minutes. What RTO do you record? Where do you measure to find the gap?

### Suggested Answers

**Question 1:** Web replicas are multi-AZ, yet sessions remain a SPOF; adopt an HA session store, cross-instance verifiable tokens, or durable cart storage. Sticky sessions do not protect against AZ failure.

**Question 2:** No; after losing one AZ only 400 req/s remains in a two-AZ setup, far below 1,200. Even with both AZs alive, total capacity is only 800. Either move to three AZs at 600 req/s each as in the primary solution, or size each of two AZs for 1,200 req/s—and test every dependency.

**Question 3:** Asynchronous replicas suffer replication lag, so writes acknowledged by the primary may not have reached the standby. Pick a commit/HA mode matching write-durability requirements, verify empirically, and add reconciliation/idempotency. If unachievable, renegotiate RPO or change database architecture; never claim zero data loss with an async read replica.

**Question 4:** Possible causes: DB writer still in AZ-A, cache/session store in AZ-A, single egress/NAT or scheduler in AZ-A, non-HA queue, AZ-A-bound DNS/endpoints/secrets, or insufficient DB capacity. Trace the entire checkout path from client through all dependencies.

**Question 5:** If outage starts when users cannot place orders and ends when orders succeed again, **measured RTO is roughly 4 minutes**, not 15 seconds. Inspect DB failover, stale connection pools, cold caches, retry/timeout settings, post-loss throughput, and synthetic checkout checks. Always state measurement conditions and exact start timestamps.

## 16. Common Anti-Patterns and Acceptance Checklist

| Anti-pattern | Why it fails | Fix |
|---|---|---|
| Duplicating apps in the **same AZ** and calling it HA | One AZ outage stops every instance | Spread replicas across distinct AZs |
| Multi-AZ apps with a single-AZ database | Checkout still loses its writer | Deploy HA database with tested failover and consistency checks |
| Relying purely on autoscaling **after** an AZ dies | Cold starts/quotas breach RTO or SLO | Provision N+1 headroom plus supplemental scaling |
| Using sticky sessions for state | Losing an AZ wipes sessions | HA session store or stateless/token design |
| Storing user files on instance disks | Losing a host/AZ loses file access | Appropriately scoped durable object storage |
| Checking only LB healthy targets | Misses DB or checkout failures | Synthetic transactions and end-to-end SLIs |
| Manual DB failover without runbooks | Actual RTO becomes unpredictable | Choose appropriate failover, automate, and drill |
| Non-idempotent order/payment retries | Duplicate charges on ambiguous timeouts | Idempotency, reconciliation, and bounded retries |
| Deploying to all AZs simultaneously | Software bugs take down the whole region | Zoned canary or rolling deploys with rollback |
| Thinking multi-AZ survives region outages | Confuses fault-domain scope | Design multi-region separately if required |

### Design Acceptance Checklist

- [ ] Clearly defines **region, AZ, fault domains, and unprotected failure modes**.
- [ ] Defines SLO/SLIs and RTO/RPO per critical flow, measured from the user perspective.
- [ ] Web/API, workers, and required resources operate across **at least two healthy AZs** after one AZ is lost.
- [ ] Calculates and tests **1,200 req/s after losing one AZ**, covering LB, DB, cache, queue, pools, and network.
- [ ] Database has an HA/failover plan, backup/restore, and verified correctness for confirmed transactions.
- [ ] Sessions, files, scheduled jobs, and temporary state do not depend on a single instance or AZ.
- [ ] Network is segmented, DB is private, cloud identities follow least privilege, and cross-AZ paths are tested.
- [ ] Phased migration plan includes canary/rolling steps, abort gates, and data-specific rollback.
- [ ] Measures real RTO with synthetic checkout and drills both **AZ loss and AZ recovery**.
- [ ] Per-AZ alerting, complete runbooks, and incident owners are assigned.
- [ ] Cost sheet covers spare capacity, DB HA, cross-AZ data transfer, and residual risks.
- [ ] ADRs are written and all six **Well-Architected** pillars are evaluated.

### Extension Exercise After Achieving Multi-AZ

Suppose executive leadership adds a requirement to **keep serving when an entire region loses connectivity**. The current design does not meet this. Investigate **multi-region** architectures, DNS/traffic failover strategies, cross-region data replication, consistency trade-offs, DNS TTLs, standby region capacity, legal/residency constraints, and failback to the primary region. That is a **different problem** from single-AZ to multi-AZ within one region, requiring new RTO/RPO, cost models, and tests.

**Expected outcome of the exercise:** do not stop at a diagram with multiple AZs. A solid design must prove that an AZ can go offline while users continue transacting within the agreed outage budget, critical data stays intact, and operations knows how to detect, recover, and verify at an acceptable cost.
