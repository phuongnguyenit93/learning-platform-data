# Applying the Reliability Pillar of the Azure Well-Architected Framework

An ordering system on Microsoft Azure can run normally for months and still lose revenue from a single database failure, misconfigured DNS, slow dependent service, or a new deployment that causes the entire API to return HTTP 500. Buying more servers does not automatically solve these scenarios: if all replicas connect to a single database without a recovery plan, the system still has a **single point of failure**; if there is no change management process, a single misconfiguration can bring down both deployment regions.

The **Reliability pillar** of the **Azure Well-Architected Framework (WAF)** provides guidance for building workloads capable of **maintaining committed functionality, withstanding failures, detecting degradation, recovering, and operating safely** according to the organization's actual needs. It is not a feature you can "turn on" once in the Azure Portal, but a **lifecycle-wide design and verification process** spanning business requirements, architecture, code, infrastructure, and incident drills.

The lesson **"Applying the Reliability Pillar of the Azure Well-Architected Framework"** belongs to the **Reliability and Disaster Recovery** chapter, in the **CLOUD_PROVIDERS_AZURE** module. It connects knowledge of Azure subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute services, storage, data, and messaging with deploying, monitoring, protecting, and controlling costs for Azure application architectures.

After this lesson, you will be able to:

- Explain the **Reliability design principles**, their scope, and their relationship with the other four WAF pillars.
- Translate business requirements into measurable **business-critical user flows**, SLIs/SLOs, error budgets, **RTO**, and **RPO**.
- Identify **fault domains** and common-mode failures using dependency mapping, failure-mode analysis, and single-point-of-failure evaluation.
- Choose **redundancy, Availability Zones, multi-region, active-passive/active-active**, and distinguish service failover from application recovery.
- Design applications that **tolerate dependency failures** using timeouts, bounded retries, backoff/jitter, circuit breakers, bulkheads, idempotency, queues, and degraded modes.
- Coordinate reliability across **App Service, Azure Container Apps, AKS, Azure Front Door, Azure SQL, PostgreSQL, Storage, Cosmos DB, Service Bus, and Key Vault**.
- Define **backups, restores, PITR, geo-recovery, consistent data, runbooks, and DR drills** aligned with committed targets.
- Organize **monitoring, alerting, incident response, change management, game days**, and improvements from postmortems.
- Balance **cost, complexity, recoverability, and performance** rather than mechanically maximizing the number of regions.

> **Learning scope:** The diagrams, SLO targets, configurations, and commands are assumed examples for a **lab workload**, not configurations applicable to every service/region. Zone redundancy, geo-replication, backup retention, failover, SLAs, and pricing depend on the Azure service tier, SKU, region, and time. When applying in practice, verify current documentation/support matrices/pricing/SLAs and rehearse on approved resources. Do not perform operations on Azure production while working through this lesson.

## 1. What Is Reliability and How Does It Differ from Availability?

**Availability** typically expresses how ready a service is to serve requests over a period of time. **Reliability** is broader: whether the system continues to produce **correct business outcomes** when components degrade, recovers within committed timeframes, keeps data within acceptable loss limits, and operates under abnormal conditions.

An API that returns HTTP 200 from a cache while issuing duplicate orders, losing data, or failing to submit payment transactions is **not reliable**, even if the availability dashboard is green.

| Term | Question to answer | Unit / manifestation |
|---|---|---|
| **Availability** | Can the service serve requests? | % of uptime / successful requests |
| **Reliability** | Does the workload preserve correct functionality, tolerate faults, and recover? | SLO, RTO/RPO, data correctness, resilience tests |
| **Durability** | Does written data survive failures? | Record durability/probability, backup/replication |
| **Resilience** | Can the system absorb fault impacts and continue serving at an acceptable level? | Fault tolerance, isolation, graceful degradation |
| **Recoverability** | After disruption, how quickly does the system restore functionality/data? | RTO/RPO, restore test evidence |
| **Disaster recovery** | When a large fault domain fails, how is the workload restored elsewhere/via another path? | Runbooks, secondary region, backups, and failover |
| **Security** | Does the workload resist unauthorized access/sabotage? | IAM, encryption, change approval, incident containment |

**Some essential boundaries:**

- **HA does not replace backups:** replicated data can immediately replicate accidental deletions or corrupted data.
- **Backups do not replace HA:** restoring can take hours and cannot meet near-zero-downtime objectives.
- **Multi-region does not replace a DR plan:** you still need ingress switching, data leadership, dependencies, rollback, and drills.
- **An Azure service SLA is not the whole application's SLO:** an end-to-end user flow can fail even when each individual component still meets its own SLA.
- **Monitoring alone does not make a system healthy:** alerts are only evidence for operations unless paired with appropriate recovery actions.

### 1.1. Reliability Among the Five Azure WAF Pillars

| Pillar | Relevance to this lesson |
|---|---|
| **Reliability** | Verified fault tolerance and recovery capability |
| **Security** | Identity, secrets, network, and change controls to limit incidents from attacks/misconfiguration |
| **Cost Optimization** | Cost of redundancy, backups, replicas, replication, drills, and standby |
| **Operational Excellence** | Observability, runbooks, CI/CD, automation, incident response, and postmortems |
| **Performance Efficiency** | Headroom, scaling, latency, throttling, and backpressure under peak/load |

The pillars involve **trade-offs**: multi-region improves recoverability but increases complexity, asynchronous data considerations, and cost; turning off all logs to save money can eliminate the ability to diagnose failures.

### 1.2. What Gets Measured: User Flow First, Resources Second

~~~mermaid
flowchart LR
    USER[Customer places order] --> API[Order creation API]
    API --> SQL[(Azure SQL Database)]
    API --> SB[Azure Service Bus]
    SB --> WORKER[Payment processing worker]
    WORKER --> PAY[Payment provider]
    API -. Trace / metrics .-> OBS[Azure Monitor / App Insights]
    SQL -. Health / logs .-> OBS
    SB -. Queue lag / dead letters .-> OBS
~~~

If SQL has already committed, Service Bus publishing fails, and the client retries, the reliability problem is **order consistency and idempotency**, not merely adding more API pods. The system must define when an order is considered accepted and how subsequent steps can be reconstructed or recovered.

## 2. Five Core Reliability Design Principles

Azure WAF frames Reliability around interrelated design areas. In this lesson, we use five thinking groups to evaluate an architecture:

1. **Design for business requirements** — start from business impact, functional goals, prioritizing critical flows, SLO/RTO/RPO.
2. **Design for resilience** — assume failures will happen; build redundancy, isolation, graceful degradation, and blast-radius/cascade control.
3. **Design for recovery** — maintain plans for data and service recovery, failover/failback, and RTO/RPO testing.
4. **Design for operations** — monitoring, alerting, runbooks, safe deployments, response, and continuous improvement.
5. **Keep it simple** — reduce components, dependencies, modes, and procedures that the operations team cannot realistically control.

### 2.1. Applying Them to a Real Workload

| Principle | Concrete design / activity | Required evidence |
|---|---|---|
| Business requirements | Checkout flow 99.9% SLO, assumed 5-minute RPO | Business owner approval and metric definition |
| Resilience | Multi-replica/zonal API, timeouts, and queue isolation | Fault-injection/load-test results |
| Recovery | SQL PITR, regional failover, traffic switching, runbook | Restore/failover drill and measured timings |
| Operations | Synthetic checks, metrics, on-call, change rollout/canary | Alert history, incident records, SLO dashboard |
| Simplicity | Remove unnecessary synchronous dependency from checkout path | Dependency diagram and change review |

**Do not apply all five by ticking a paper checklist.** Every decision must tie back to a user flow, failure mode, and test evidence; a complex architecture without a runbook is less reliable than a simple architecture with clear recovery.

### 2.2. Avoiding the "Everything Must Be HA" Anti-Pattern

Not every component of an application needs multi-region. For example:

- Checkout/orders: high SLO/RTO/RPO.
- Daily revenue reporting: tolerates delayed updates, batch retries.
- Marketing email: does not necessarily need 5-minute recovery.
- Marketing/intro website: cached static content can operate independently.

Prioritize **critical flows and data integrity** instead of spending uniformly. A single replica for an import job may be acceptable if it has checkpoints/replay and an appropriate deadline; conversely, a payment API with a single regional DB is a major risk if business requirements demand regional recovery.

## 3. From Business Impact to Critical User Journeys

### 3.1. Business Impact Analysis (BIA)

An effective BIA answers:

- If a capability stops for **5 minutes, 1 hour, 1 day**, what is the impact?
- Does an outage cause **lost transactions, delayed transactions, data exposure, or incorrect billing**?
- Are there peak/campaign periods or payment/regulatory constraints?
- Which flows have **synchronous dependencies** on external providers?
- Who has the authority to declare an incident and decide to degrade or invoke DR?
- Do specific customers/industries/regions require different SLOs?

Example tiering:

| User flow | Business criticality | Acceptable degradation | Unacceptable outcome |
|---|---|---|---|
| **Order creation** | Very high | Temporary wait, controlled pending state | Duplicate orders / losing committed orders |
| **Order lookup** | High | Reading a near-fresh copy within bounds | Returning stale/wrong status without marking it |
| **Payment** | Very high | Queue/retry with idempotency | Double charging, losing payment records |
| **Notification email** | Medium | Delayed by minutes/hours, replayed | Synchronously failing checkout |
| **BI reporting** | Lower | Batch-delayed data | Exhausting OLTP DB connections |

### 3.2. A Dependency Map Must Include People

~~~mermaid
flowchart TD
    U[User flow: Checkout] --> EDGE[DNS + Azure Front Door / ingress]
    EDGE --> APP[App Service / Container Apps / AKS]
    APP --> SQL[(Order database)]
    APP --> KV[Key Vault / identity]
    APP --> MQ[Service Bus]
    MQ --> W[Order worker]
    W --> EXT[Payment external API]
    APP --> OBS[Telemetry / alerts]
    SQL --> BK[Backup + secondary data strategy]
    TEAM[On-call / IAM / DBA / Network teams] -. Response and approvals .-> APP
    TEAM -. Recovery .-> BK
~~~

Beyond Azure resources, you must map the **DNS provider, certificate issuer, identity, deploy pipeline, external payment provider, on-call roster, and personnel authorized to restore**. A DR runbook that depends on a single admin who is on vacation is a real failure mode.

### 3.3. Classifying Data State

| Data category | Examples | Required durability / recoverability |
|---|---|---|
| Source of truth | Orders, payments, ledger | Consistency, backups/restore, audit |
| Transactional derived | Inventory reservation | Idempotent updates, reconciliation |
| Replayable stream | Service Bus messages/outbox | At-least-once handling, DLQ, and replay |
| Cache | Redis session/read models | TTL/invalidation, rebuild/backing store |
| Ephemeral | Scratch files, pod local disk | Must never be treated as durable |
| Telemetry/audit | Logs, traces, Activity Log | Retention/access per incident/compliance needs |

**RPO=0** for a flow is not guaranteed simply by choosing "geo-redundant storage" if steps across the source DB, queue, and external payment are not committed consistently. You must define the **transaction confirmation point (commit/acknowledge)** and the recovery mechanism for each state type.

## 4. SLI, SLO, SLA, and Error Budget

### 4.1. Three Easily Confused Concepts

**SLI (Service Level Indicator):** a metric measuring service experience, such as the proportion of checkout requests accepted and recorded accurately.

**SLO (Service Level Objective):** an internal target for an SLI over a window, such as 99.9% of valid requests succeeding over a rolling 30 days.

**SLA (Service Level Agreement):** a contractual/terms commitment with customers or providers; an Azure SLA typically defines availability for **a specific service and configuration**, not the end-to-end SLA of your application.

### 4.2. Defining a Good SLI

Example:

\[
\mathrm{CheckoutSuccessRate}
=
\frac{\text{number of valid requests that successfully create an order}}
{\text{total number of valid requests attempting to create an order}}.
\]

You must specify:

- **Numerator:** does HTTP 202 accepted into a queue count as success, and how is eventual fulfillment verified?
- **Denominator:** are client 4xx errors from invalid input excluded, and how are timeouts/cancellations handled?
- **Scope:** production, region, customer segment, operation?
- **Window:** rolling 28 days, calendar month, or daily?
- **Latency:** does a request succeeding after 2 minutes meet the checkout SLO?
- **Correctness:** duplicate prevention, accurate amount/order/address?

If the API returns 202 to mask a backend queue backed up for 24 hours, **an HTTP success SLI will mislead operations**. Pair it with an *order completion within 10 minutes* SLI, queue lag, and reconciliation.

### 4.3. Availability Error Budget

With a 99.9% SLO over **30 consecutive days**, the theoretical budget for failing to meet the objective (assuming uniform time-based measurement) is:

\[
30\times24\times60\times(1-0.999)
=43.2\text{ minutes}.
\]

| 30-day SLO target | Time-based error budget* |
|---|---:|
| 99.0% | 7 hours 12 minutes |
| 99.5% | 3 hours 36 minutes |
| 99.9% | 43 minutes 12 seconds |
| 99.95% | 21 minutes 36 seconds |
| 99.99% | 4 minutes 19.2 seconds |

\*Table assumes **time-based availability over exactly 30 days**. For a request-based SLI, the error budget is an **allowed count of failed requests**, which cannot be converted directly into minutes when traffic fluctuates.

### 4.4. Using Error Budgets to Drive Decisions

One operational approach:

~~~text
If recent burn rate is high:
  freeze risky releases
  prioritize resiliency fixes
  tighten rollout approvals and test recovery

If SLO is comfortably met:
  continue controlled feature delivery
  still review high-impact failure modes and DR readiness
~~~

An error budget is **not a license to neglect customers for 43 minutes**; it is a tool for balancing change velocity and risk. A data-loss incident cannot be "offset" by 99.99% uptime.

### 4.5. SLO Tree for an Application

~~~text
Business objective: 99.9% valid checkout within 2 seconds
  ├─ Front-end endpoint availability
  ├─ API success and p95/p99 latency
  ├─ Order DB commit and data integrity
  ├─ Queue accepted and consumer lag
  ├─ External payment provider success/reconciliation
  └─ Dependency auth and network connectivity
~~~

Do not make every resource CPU alert into an SLO. High CPU can be a **signal to investigate**, whereas an SLO must describe user/business outcomes.

## 5. RTO, RPO, and Recovery Objectives

**Recovery Time Objective (RTO):** the maximum duration the business tolerates to **restore functionality** after a defined incident.

**Recovery Point Objective (RPO):** the maximum data loss the business tolerates, typically expressed as the age of the recovery point relative to when the incident occurred.

### 5.1. Timeline

~~~text
Last recoverable consistent point       Failure              Recovery
            |                              |                     |
            v                              v                     v
------------+------------------------------+---------------------+---
            <-------- RPO window ---------><------ RTO -------->
~~~

RTO is usually measured from the organization's defined incident trigger, so it must include **detection, failover decision, provisioning/restoring, startup, DNS/traffic rerouting, and business validation**. If you only measure the restore command duration and omit 45 minutes waiting for on-call, RTO has been miscalculated.

### 5.2. Example Targets by Workflow

| Workflow | Assumed RTO | Assumed RPO | Architecture to consider |
|---|---:|---:|---|
| Checkout | 30 minutes | 5 minutes | Multi-zone + geo recovery, outbox, replay |
| Order lookup | 1 hour | 15 minutes | Read replica/cache rebuild |
| Email notification | 8 hours | 1 hour | Durable queue, replay, and rate limiting |
| Internal reporting | 24 hours | 24 hours | Batch restore/recompute |
| Audit/legal ledger | Per strict policy | May require near 0 | Consistent data, record controls |

**These numbers are for learning design trade-offs only**, not Azure SLAs or default recommendations. Near-zero RPO may require synchronous commit architectures with latency/cost trade-offs; asynchronous replication generally risks losing writes that had not reached the secondary at failover.

### 5.3. Why RTO and RPO Are Not the Same Metric

A system might restore the DB to a backup from 1 minute ago (**RPO ≈1 minute**) yet require 6 hours to redeploy apps/networking/IAM (**RTO ≈6 hours**). Conversely, the frontend might switch to region B in 2 minutes (**good RTO**) while the secondary database lags 30 minutes behind (**poor RPO**).

### 5.4. Choosing a Recovery Pattern from Targets

| Pattern | Typical RTO | Typical RPO | Cost / limitations |
|---|---|---|---|
| Rebuild from code + daily backup | Long | May be many hours | Cheap, but unsuitable for critical write flows |
| Automated PITR backup | Medium, must be measured | Follows backup/log chain and service | Restores a new instance/database; cutover needs planning |
| Warm standby regional | Shorter when well rehearsed | Follows async replication lag | Pays for standby/data replication |
| Active-active read + single writer | Short for reads | Writes still depend on leader/failover | Routing/consistency complexity |
| Multi-region multi-write | Can be low for regional failover | Depends on consistency/conflict model | Conflict resolution, latency, complex design |

**Do not write "RPO=0 and RTO=0" on a slide and call it an architecture.** You must account for every stateful dependency and prove it by testing; an external payment gateway without idempotency can break correctness even when data replication is fast.

## 6. Fault Domains and Failure-Mode Analysis

Reliability starts by asking: **what can fail, how wide is the blast radius, what signals detect it, and what can self-heal?**

### 6.1. Failure Classes to Model

| Fault domain | Examples | Prevention and recovery |
|---|---|---|
| **Process/instance** | JVM crash, OOM, VM reboot | Multi-instance, health probes, restart/replacement |
| **Host/rack** | Host fault, storage path error | Managed service/multiple replicas, platform healing |
| **Availability Zone** | Zone-scoped power/network loss | Zone redundancy supported by SKU/region |
| **Region** | Regional service outage | Multi-region plan, geo replication, traffic failover |
| **Control plane** | Deployment API unavailable | Pre-provision, avoid deploy dependencies during incidents |
| **Identity/secrets** | Entra/Key Vault/network policy failure | Bounded caching, circuit breaker, controlled break-glass |
| **Dependency** | SQL timeout, Service Bus throttling | Timeouts, queues, isolation, backpressure |
| **Data** | Accidental deletion, logical corruption, ransomware | Backup/PITR, immutable copies, restore rehearsal |
| **Configuration** | Misconfigured DNS, NSG, certificate, role | IaC/PR review, canary, config rollback |
| **Human/process** | Absent on-call, outdated runbook | Ownership, drills, approvals |
| **External provider** | Payment/SMS API down | Idempotency, fallback, async processing |

**An Availability Zone only isolates certain infrastructure risks.** If all three zones run buggy code or depend on the same misconfigured secret/DB connection string, the failure still spreads across the entire workload.

### 6.2. FMEA: Failure Mode and Effects Analysis

| Component | Failure mode | User flow impact | Detection | Prevention / mitigation | Recovery owner |
|---|---|---|---|---|---|
| API | Replicas run out of memory | Checkout 5xx | Error rate + OOM/restarts | Memory sizing, HPA, load testing | App/SRE |
| Azure SQL | Primary unavailable | Cannot commit order | DB errors/health | HA tier, failover strategy | DBA/platform |
| Service Bus | Send throttled | Order completion delayed | Send errors, queue lag | Backoff, outbox, retry budget | App/platform |
| Key Vault | Role/grant modified | Secret lookup fails | Key Vault audit + API failure | IaC review, least privilege | IAM/SRE |
| DNS/Front Door | Routed to wrong region | Traffic hits wrong target | Synthetic multi-region probes | Config review, staged rollout | Network/SRE |
| Schema migration | Column dropped early | Old/new versions fail | Error spikes, migration logs | Expand/contract | DBA/release |

Evaluate each mode by **severity, likelihood, detectability, and recovery difficulty**. You can use a Risk Priority Number for relative prioritization, but never let a low score hide a **high-consequence data-loss or financial risk**.

### 6.3. Common-Mode Failures

~~~text
App deployed in zones 1, 2, 3
All three zones depend on one Key Vault config / DB writer
One bad RBAC or DNS change → every zone affected
~~~

Similarly, a pipeline with permissions to modify all regions, a shared Azure Firewall rule, or a deleted DNS zone can take down multi-zone/multi-region simultaneously. The dependency map must include **shared services and people**, not just VM/pod placement.

### 6.4. FMEA Outputs

For each critical risk, create a record containing: **failure mode, affected SLI, owner, mitigation, alert, recovery runbook, rollback conditions, latest test, and residual risk**. Review periodically after architecture changes, incidents, and provider changes.

### 6.5. Dependency Availability Math Is Only a Model

If three **serial, mandatory, and independent dependencies** each have 99.9% availability over the same window:

\[
0.999^3\approx 0.997003,
\]

or about **99.7003%** in a simplified model. Real failures are often **correlated**, and systems can use caches/fallbacks/async paths. **Never multiply Azure SLAs and call the result a measured SLO.** Use the math to question which dependencies truly belong on the synchronous user path.

## 7. Reliability Architecture: Eliminating Single Points of Failure

### 7.1. From Single Point to Fault Tolerance

~~~mermaid
flowchart LR
    subgraph BAD[Single-point architecture]
      U1[Users] --> ONE[One API instance]
      ONE --> ONEDB[(One DB primary)]
    end
    subgraph BETTER[Zone-aware architecture with recovery]
      U2[Users] --> LB[Ingress / health-based routing]
      LB --> API1[API zone A]
      LB --> API2[API zone B]
      LB --> API3[API zone C]
      API1 --> DB[(Managed database with verified HA)]
      API2 --> DB
      API3 --> DB
      DB -. Backup / regional recovery .-> REC[Recoverable state]
    end
~~~

The diagram does **not** promise the DB automatically has zone redundancy just because the API runs across three zones. You must verify **each database tier**, configuration, failover time, and consistency.

### 7.2. Redundancy Has Three Parts

1. **Compute redundancy:** multiple instances/pods/sites to survive node failures.
2. **Data redundancy:** replicas/zone-geo copies matching durability, consistency, and failover needs.
3. **Recovery/control redundancy:** DNS/routing, backups, scripts, identities, operational permissions, and decision-makers.

Compute redundancy without data or recovery redundancy still leaves write workflows with a shared point of failure.

### 7.3. Do Not Amplify Bottlenecks with Autoscaling

30 API replicas × a 30-connection Hikari pool can create **900 potential DB connections**. If the database does not have that connection budget, adding replicas **increases failures**. Sizing requires capacity headroom, pool limits, load shedding, retry budgets, admission control, and load testing.

### 7.4. Bulkheads and Separating Secondary Functions

~~~mermaid
flowchart LR
    CLIENT[Checkout request] --> CORE[Order API]
    CORE --> DB[(Order database)]
    CORE --> OUTBOX[(Transactional outbox)]
    OUTBOX --> BUS[Service Bus]
    BUS --> EMAIL[Notification worker]
    BUS --> ANALYTICS[Reporting worker]
~~~

If email/SMS fails, checkout can still succeed when email is a secondary function. A **bulkhead** isolates executor pools, concurrency limits, resource quotas, or separate workloads so a failing dependency cannot exhaust threads for other flows. An **outbox** preserves events after DB commit, though delivery may be at-least-once: consumers must still be idempotent.

### 7.5. Simplicity and Operational Burden

Every new service brings DNS, credentials, capacity, monitoring, runtime/versions, and runbooks. Do not add an API gateway, service mesh, cache, queue, or extra database unless it addresses a specific failure mode. Multi-region active-active when the operations team has not mastered conflict resolution can be **less reliable** than a simple, well-drilled active-passive setup.

## 8. Availability Zones: When Are They Enough, and When Are They Not?

An **Availability Zone (AZ)** is a physically isolated fault domain within a supported Azure region. **Not every Azure region, service, or SKU** supports zones or provides the same distribution/HA model.

### 8.1. Zonal vs. Zone-Redundant

| Model | Meaning | Risk |
|---|---|---|
| **Zonal resource** | Specific zone selected at provisioning | A single zone can still be a single point of failure |
| **Multi-zonal replicas** | Multiple app replicas across multiple zones | Ingress, placement, shared state |
| **Zone-redundant managed service** | Azure manages cross-zone redundancy per tier | Availability/features/latency/failover depend on service |
| **Regional service without zone config** | Provider handles per product design | Does not automatically carry an AZ SLA |

**A VM in zone 1 does not automatically replicate to zone 2.** Azure Storage ZRS does not automatically provide a secondary region. For App Service, Container Apps, SQL, PostgreSQL, and AKS, check SKU/region/replica prerequisites.

### 8.2. Zone Outage Test

~~~text
Region A:
  Zone 1: API replica A (failed)
  Zone 2: API replica B (healthy)
  Zone 3: API replica C (healthy)

Ingress routes only to healthy instances.
DB, queue and identity dependencies remain usable.
Expected: critical user flow remains within SLO.
~~~

After losing zone 1, do the remaining 2 zones have enough capacity for the full traffic? If every zone runs near its ceiling, losing one zone triggers a cascading failure. Design **N+1/N+K headroom** around load and fault models rather than assuming "one replica is enough."

### 8.3. Per-Service Checklist

| Service | What to verify |
|---|---|
| **VM/VMSS** | Zone placement, Load Balancer/probes, disk support |
| **App Service** | Plan tier, region, zone redundancy setting, minimum instances |
| **Container Apps** | Managed environment SKU/region support and zone redundancy setting |
| **AKS** | Node pools, topology spread, PDB, ingress, stateful dependencies |
| **Azure SQL** | Service tier/region zone redundancy, failover behavior |
| **PostgreSQL Flexible Server** | Zone-redundant HA/standby, expected failover |
| **Storage** | LRS vs. ZRS vs. GRS/GZRS and read access to secondary |
| **Service Bus** | Namespace tier, data availability, disaster recovery features |

### 8.4. How to Verify

1. Record resource type/SKU/region/replica count.
2. Check current documentation/support matrices **at that time**.
3. Verify actual active replica placement and network routing.
4. Identify shared dependencies across zones.
5. Rehearse faults safely in staging.
6. Measure end-to-end user SLI, p95, and failover time.

Do not hardcode universal zone numbers: **logical zone identifiers** can map differently to physical zones across subscriptions, and regional support also evolves.

## 9. Multi-Region Resilience: Active-Passive and Active-Active

A regional outage exceeds the fault-tolerance scope of Availability Zones. Multi-region can help, but **it does not mean Azure automatically fails over your entire workload just because you picked paired regions**.

### 9.1. Active-Passive (Warm Standby)

~~~mermaid
flowchart TB
    USERS[Global users] --> FD[Azure Front Door / global router]
    FD -->|Primary healthy| R1[Region A application]
    FD -. Failover after decision .-> R2[Region B standby]
    R1 --> D1[(Primary database A)]
    D1 -->|Async geo replication if supported| D2[(Secondary DB B)]
    R2 --> D2
    MON[Incident command] -. routing/DB promotion .-> FD
~~~

Region B must have **runnable infrastructure, identities, certificates, images, DNS, networking, quotas, and a data recovery path**; an undeployed Bicep template is not a warm standby. Front Door health routing and database failover are **two separate actions**: never route write traffic to B before the secondary database is safely promoted and consistency/replay semantics are clear.

### 9.2. Active-Active

~~~mermaid
flowchart TB
    U[Users] --> EDGE[Global router]
    EDGE --> A[Region A active app]
    EDGE --> B[Region B active app]
    A --> STATE[Single-writer or supported multi-write data]
    B --> STATE
    STATE --> CONS[Consistency/conflicts/lag]
~~~

Two active application regions **do not imply a multi-write database**. If the DB only has a writer in A, requests in B may have to write cross-region. With multi-write (such as supported Azure Cosmos DB configurations), you must define consistency levels, conflict resolution, ordering, and idempotency.

### 9.3. Azure Region Pairs Do Not Replace a DR Plan

- Not every Azure region follows the traditional paired-region model.
- A paired region does not automatically create replicas for apps, DBs, secrets, or container images.
- Different services have different geo-replication/failover semantics and regional support.
- Choose B based on data residency, SKU availability, quotas, capacity, networking, identity, and operations—not mechanically by "pair."
- Never assume Azure region pairing guarantees a specific RTO for an application.

### 9.4. Choosing a Secondary Region

| Criterion | Questions |
|---|---|
| Data residency | Can data/logs be replicated to region B? |
| Failure independence | Are there shared dependencies between A and B? |
| Service support | Are required App/AKS/SQL/ACR tiers available in B? |
| Capacity | Are quotas and scaling capacity in place when A is lost? |
| Network | Are Private Endpoints/DNS/NSGs/Firewalls/VPNs sufficient? |
| Identity | Are Entra/Key Vault/certificates/roles configured? |
| Data | Sync/async, writer promotion, RPO/conflicts? |
| Cost | Standby compute, storage replication, network egress? |
| Operations | Who declares DR, and are runbooks and drills in place? |

### 9.5. Failback Is a Separate Release

After A recovers, **do not automatically switch traffic back**: establish the authoritative writer, inspect divergent data, re-seed A from source-of-truth B via a supported service procedure, restore replication/recovery posture, test consistency, and then cut back with approvals and a rollback plan. Avoid **split-brain**, where A and B both accept writes without a multi-write conflict model.

## 10. Entry Points: DNS, Front Door, and Load Balancing

| Service | Best suited for | Limitations |
|---|---|---|
| **Azure Front Door** | Global HTTP/HTTPS routing, origin health, WAF | Health probes, reroute timing, TLS, and config |
| **Traffic Manager** | DNS-based steering | DNS TTL/resolver/client caching |
| **Application Gateway** | Regional Layer 7/WAF | Zone config, listener certs, backend probes |
| **Azure Load Balancer** | Regional Layer 4 TCP/UDP | Zone/SKU/probe/outbound rules |
| **AKS ingress** | Cluster routing | Controller redundancy, DNS/TLS/service endpoints |

**Front Door does not automatically replicate data or promote an Azure SQL secondary.** DNS-based failover does not guarantee every client switches endpoints within seconds.

### 10.1. Health Probes

~~~text
BAD /health:
  Always returns HTTP 200 if process is alive.

BETTER /ready:
  Checks critical readiness with bounded timeouts.
  Does not perform payment writes or heavy DB queries.

LIVENESS:
  Checks local process responsiveness.
  Does not restart every pod on a transient remote DB outage.
~~~

If liveness depends on SQL, a 30-second DB outage can restart every pod simultaneously and trigger a reconnection storm. If readiness always returns 200, ingress keeps routing to an instance that cannot complete checkout. Distinguish liveness, readiness, startup, and synthetic user-flow probes.

### 10.2. Routing RTO

\[
T_{\mathrm{failover}}\approx T_{\mathrm{detect}}+
T_{\mathrm{decision}}+T_{\mathrm{reroute}}+
T_{\mathrm{backend\ ready}}+T_{\mathrm{validate}}.
\]

This is an **estimation model**, not an Azure SLA formula; stages can overlap. Health intervals/thresholds, control/data planes, and DNS caching all affect the total.

### 10.3. Routing Drill

~~~text
1. Baseline user-flow SLI and primary region.
2. Simulate approved endpoint degradation in staging.
3. Verify health-based routing detects failure.
4. Verify traffic reaches secondary.
5. Verify data and identity readiness.
6. Stop test; check duplicate/missing orders.
7. Measure RTO/RPO.
8. Verify safe failback and restored redundancy.
~~~

Never induce a production outage by turning off DNS/NSG/Key Vault/DB without approved fault-injection scope and authorizations.

## 11. Compute: App Service, Container Apps, AKS, and VMs

### 11.1. App Service

- Choose a plan/SKU/region with availability and **zone redundancy** when objectives require it.
- Run multiple instances where supported; autoscale with headroom and load tests.
- Use deployment slots/canary where appropriate; review slot-specific settings, app configuration, and connections before swapping.
- Distinguish App Service **VNet Integration outbound** from Private Endpoint inbound; all instances must reach the database/Key Vault.
- Separate durable state from local ephemeral files and in-memory sessions.
- Configure health checks, warm-up, and multi-region apps + global routing when RTO requires it.

**Slot swaps do not undo database migrations or data writes.** Do not copy a production connection string into a staging slot if there is any risk of affecting live data.

### 11.2. Azure Container Apps

- Configure min/max replicas and cold-start trade-offs; avoid scale-to-zero for latency-critical flows.
- Configure readiness/liveness/startup probes, graceful shutdown, and concurrency limits.
- Use single/multiple revision modes, traffic splitting, and rollback as applicable.
- Use a zone-redundant managed environment if supported by SKU/region and configured at provisioning.
- Ensure runtime image pull identity, ACR networking, DNS, and secrets work.
- Pair HTTP/KEDA queue autoscaling with DB/queue connection budgets.
- Jobs must have idempotency, checkpoints, and bounded retries.

Example:

~~~text
Normal:  6 replicas × 10 DB connections = up to 60.
Peak:   40 replicas × 10 DB connections = up to 400.
If DB budget is 100, blindly autoscaling API may worsen outage.
~~~

These represent **potential connections**, not a claim that every connection is open at once. Capacity/connection budgets must be measured in practice.

### 11.3. AKS

| Layer | Measures |
|---|---|
| Control plane | Appropriate SLA/tier; do not depend on the API server in the serving path |
| Nodes | Zone-spread node pools, autoscaler, and spare capacity |
| Pods | Replicas/topology spread/anti-affinity |
| Disruptions | PodDisruptionBudget, drain safety, maintenance |
| Runtime | Liveness/readiness/startup probes, graceful termination |
| Scaling | HPA/KEDA, rate limits, backpressure, and database budget |
| Network | Ingress controller replicas, DNS/CNI/NetworkPolicy |
| State | PV/CSI zone binding, app-aware backups, and DB strategy |
| Upgrade | Surge/node image rotation/API version compatibility |
| DR | Cluster/registry/GitOps/IaC/data restore in recovery region |

**PDBs typically govern voluntary evictions and do not heal host/zone outages.** Three replicas on the same node remain a single fault domain; verify actual pod placement. With stateful PVCs, replica scheduling may be constrained by zone-bound volumes.

### 11.4. VM/VMSS

VM workloads need zone placement/VMSS, LB probes, golden images, OS patching/Update Manager, disks/backups, replacement automation, zone quotas, and must never store the sole source of data on a temporary local disk. A single VM with a managed disk **is not automatically HA** without replacement/failover mechanisms.

### 11.5. Do Not Let the Serving Plane Depend on the Pipeline

A temporary outage in GitHub Actions or Azure Resource Manager should not stop a running app from serving requests because every request depends on a deploy API. However, scaling and recovery may still need the control plane, so maintain reserved capacity/pre-provisioning aligned with RTO and verify permissions/quotas before an incident.

## 12. Relational Data: Azure SQL Database and PostgreSQL Flexible Server

A multi-replica stateless application still depends on **database correctness and recovery**. Database reliability design addresses three distinct questions: **primary HA**, **backup/point-in-time restore**, and **recovering when an entire region fails**.

### 12.1. Azure SQL Database: Three Layers of Recovery

| Capability | Purpose | Notes |
|---|---|---|
| **Built-in high availability** | Platform handles many compute/storage faults per service tier | Does not guarantee zero downtime; drivers/retries must handle transient disconnects |
| **Zone redundancy** | Reduces zone-outage impact when supported by tier/region and configured properly | Check performance/failover behavior and SKU |
| **Automated backups/PITR** | Restores to a point before deletion/logical corruption | Restore typically creates a new DB; requires cutover and RTO/RPO measurement |
| **Geo-replication/auto-failover groups** | Regional DR design options per supported feature | Typically async, with replication lag/data-loss trade-offs |
| **Long-term retention** | Longer backup retention for compliance | Does not replace hot standby/HA |

An Azure SQL **failover group** can provide a listener/traffic switching for properly configured databases, but it does not automatically recover the **application, Key Vault, Front Door, VNets, secrets, or message queues**. Evaluate failover group scope and behavior for the specific service/version.

### 12.2. PostgreSQL Flexible Server

Reliability architecture typically evaluates:

- **High availability** per tier/region, with same-zone or zone-redundant standby options where supported; evaluate actual RTO/replica mechanics.
- Automated backups/PITR with configured retention and tested restores.
- Replication/read replicas/geo read replicas/failover availability by region, service generation, and feature.
- WAL/replication lag and transaction consistency limits.
- DNS/connection strings/roles/extensions/networking when a server is restored.
- Connection pooling and retry/idempotency when failover closes existing sessions.

**A PostgreSQL read replica does not automatically become a writable primary in every failure mode**, nor does it guarantee zero data loss with asynchronous replication. You must verify **planned/unplanned promotion**, feature support, role changes, and application cutover.

### 12.3. RTO/RPO Must Be Measured from the Application

Example:

~~~text
09:00 DB primary failure begins
09:02 Platform/monitor detects failure
09:04 Database failover or restore operation starts
09:10 New writer ready
09:12 Application connections refresh and health checks pass
09:15 Checkout success SLI returns to expected range
~~~

RTO defined as "checkout recovered" is about **15 minutes**, not just the 6 minutes of DB promotion. If the restore point is 08:55, RPO measured by acknowledged data may be up to **5 minutes**; inspect actual transaction logs and durable commits.

### 12.4. SQL Client Resiliency

- Set **connection timeout, command timeout**, and budgeted request deadlines.
- Hikari/JDBC pools must evict stale connections on failover and avoid holding expired passwords/tokens.
- Retry only classified transient errors (connection reset, throttling, deadlock/serialization) with bounded attempts.
- Do not blindly retry any `@Transactional` exception: transaction outcome after a lost response may be **indeterminate**.
- Use a **business idempotency key**, unique constraints, and reconciliation when recording orders/payments.
- With failover group listeners, verify DNS/driver behavior and reconnect semantics.
- In Spring Data/JPA, `@Transactional` does not make two databases or queues into a single atomic transaction.

### 12.5. Migrations and Rollback

~~~text
Phase 1: Add new nullable/compatible schema fields.
Phase 2: Deploy v2 while v1 still works.
Phase 3: Backfill and validate data.
Phase 4: Migrate readers/writers to new representation.
Phase 5: Remove old columns only after rollback window.
~~~

Rolling back an app image **does not roll back DDL or written data**. Rehearse releases with old/new database versions, locks, and long-running transactions. For critical data, migrations need dedicated DDL leadership and an approved backup/recovery checkpoint.

### 12.6. Database Checklist

| Check | Evidence |
|---|---|
| Appropriate tier/region HA | Configuration and vendor support |
| Zone/geo recovery support | Failover target, replica status |
| PITR/backup retention | Backup policy and restore rehearsal |
| Encryption/keys/IAM | Entra/DB roles and key availability |
| Application reconnect | Transient error tests and pool metrics |
| Recovery correctness | Unique orders, balances, no double-charge |
| Observability | CPU/IO/locks/failed connections/replication lag |
| Runbook | Who promotes, updates DNS/listener, validates |

## 13. Azure Storage and Cosmos DB: Durability Is Not Availability

### 13.1. Storage Replication

| Replication model | General meaning | Not automatically included |
|---|---|---|
| **LRS** | Copies within a single region under the local model | Zone/geo durability |
| **ZRS** | Copies across zones in a region where supported | Secondary region access |
| **GRS** | Geo-replication to secondary region per feature | Automatic app failover, zero RPO |
| **RA-GRS** | GRS + secondary read capability where supported | Writable secondary, synchronous replication |
| **GZRS** | ZRS primary + geo-copy secondary per model | Failover-free recovery during regional outage |
| **RA-GZRS** | GZRS + read-access secondary where supported | Zero-lag replicated reads |

**Replication names are not a guarantee of RPO=0.** Geo-replication is typically **asynchronous**; if the primary region fails before writes reach the secondary, unreplicated data can be lost. Study **last sync time, account failover policies, access modes, DNS/endpoint behavior, and supported account types**.

### 13.2. Account Failover and Applications

Procedures must evaluate:

- Does the app use idempotent uploads and content checksums?
- Do write retries after timeout create duplicate blobs or unintended overwrites?
- Does switching regions change client SDK/DNS/endpoints and require reconnection?
- Are SAS tokens/Entra permissions/keys/private endpoints valid in the recovery region?
- Are blob metadata/indexes/lifecycle/immutability preserved as expected by the feature?
- Can readers of the secondary tolerate stale data?

Never trigger an **unplanned Storage account failover** on production just to test, as it can affect durability/replication state and business operations. Use a separate lab storage account.

### 13.3. Soft Delete, Versioning, Immutability, and Backup

To mitigate **logical deletion/corruption**:

- Blob soft delete/versioning/snapshots per supported feature/account type.
- Container soft delete or blob version restore per policy.
- Object replication/backup where aligned with RPO/RTO.
- Immutable blobs (WORM) when compliance requires tamper/delete protection.
- Separation between least-privilege data-plane roles and backup/restoration roles.

**Another replica can immediately sync an accidental delete**; you need independent versioning/backups/immutability. Retention policies carry cost and immutable data cannot be deleted arbitrarily before expiry.

### 13.4. Azure Cosmos DB: Consistency and Multiple Regions

Cosmos DB can support multi-region distribution, consistency configurations, and automatic failover depending on account/API/capabilities. You must understand:

| Factor | Reliability question |
|---|---|
| **Single write region** | If the writer region is unavailable, what are the promotion mechanism and lag? |
| **Multi-write** | How are conflicts resolved and idempotency enforced when the same item is edited in two regions? |
| **Consistency level** | Does strong/bounded staleness/session/consistent prefix/eventual match the API/region setup and business contract? |
| **Partitioning** | Could a hot logical partition cause throttling even when total RUs are sufficient? |
| **RUs** | Does the SDK safely retry 429/throttling within the deadline? |
| **Backup** | Continuous/periodic backups, point-in-time restore per supported mode/region? |
| **Change feed** | How are consumer checkpoints/replay/idempotency handled during failover? |

**A multi-region database does not automatically prevent conflicts.** If two regions deduct inventory simultaneously, you must define concurrency handling, version/ETag checks, invariants, and reconciliation. Do not enable eventual consistency on a payment ledger just for lower latency without evaluating correctness.

### 13.5. Storage and Cosmos DB Health Must Be Measured from the App

- Upload/download/Cosmos query SLIs per operation and tenant.
- p95/p99 latency, 429/503 responses, RU/throughput, retry attempts.
- Replication lag/last sync, effective consistency, stale reads.
- Data corruption detection via checksums/business invariants.
- Failover rehearsals and restoration correctness.

A green storage availability dashboard means little if the application uses the wrong endpoint or lacks container permissions; user SLOs remain the focus.

## 14. Service Bus, Event Hubs, and Background Workers

### 14.1. Why Queues Improve Reliability

Queues provide **temporal decoupling**: producers can accept requests and durably store intent while consumers are temporarily down. However, queues do not guarantee workflow correctness if:

- The producer commits to the DB and publishing fails, leaving a missing message.
- The consumer succeeds but its ack is lost, causing redelivery.
- A poison message loops forever and blocks consumer progress.
- Backlog exceeds retention/TTL or quotas.
- Regional DR lacks message state/namespace mapping.

### 14.2. At-Least-Once Delivery and Idempotent Consumers

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as Order DB + Outbox
    participant P as Outbox publisher
    participant BUS as Service Bus
    participant C as Consumer
    API->>DB: Commit order + outbox event atomically
    P->>DB: Read pending event
    P->>BUS: Send message with stable eventId
    BUS-->>C: Deliver message
    C->>C: Check idempotency / process
    C->>BUS: Complete message
    Note over BUS,C: Delivery or completion may be retried
~~~

A consumer should persist **processed message/event IDs** or enforce business unique keys in the authoritative store. Do not treat Service Bus duplicate detection as the **sole solution** against business duplication: it has window/configuration/namespace-specific limitations, and ack/retry after side effects still require separate handling.

### 14.3. Service Bus Recovery: Distinguish Geo-DR from Geo-Replication

Depending on the current tier and feature set, Service Bus offers **metadata disaster recovery aliases** or **geo-replication** with different data scopes. **Do not equate metadata replication with copying in-flight messages stored in queues.**

A DR procedure must ask:

1. Is the secondary namespace already provisioned in another region?
2. Does that tier's geo capability replicate **metadata only or also message data**?
3. How do failover aliases/connection strings/managed identities change?
4. Can **unsettled/in-flight/dead-letter** messages at the source be lost or require replay?
5. Do producers/consumers already have outbox/checkpoints/idempotency?
6. Have message ordering, sessions, TTL, scheduled messages, and DLQ been tested under the actual topology?

If the requirement is "never lose an accepted order," design a **database outbox or durable source of truth** capable of re-emitting messages that did not reach the secondary; do not rely on the name "Geo Disaster Recovery" as a promise that all messages are replicated.

### 14.4. Event Hubs Semantics

Event Hubs is an event streaming platform where consumers read partitions by offsets, with retention/replay. Reliability requires:

- Producer retries with stable IDs/partition keys per use case.
- Checkpoints and consumer group offsets.
- Consumer idempotency since processing can repeat after crashes.
- Throughput/partition count/headroom, consumer lag, and throttling alarms.
- Sufficient retention for outages; archiving/reprocessing when needed.
- Verification of DR namespace/replication features and data-loss semantics.

Event Hubs is **not a transactional queue that keeps messages forever until processed**; retention is bounded. Do not delete checkpoints to "repair" production if it would trigger massive replay or duplicate downstream writes.

### 14.5. Backpressure and Dead-Letter Queues

~~~text
Incoming: 1,000 messages/min
Consumer: 500 messages/min
Backlog growth: ~500 messages/min
After 60 minutes: ~30,000 additional pending messages
~~~

Scaling producers without scaling consumers and downstream dependencies reduces reliability. Monitor **queue age of oldest message**, DLQ count, active consumers, processing latency, and retry counts; establish a policy for poison messages instead of infinite abandon/retry loops.

### 14.6. Redis/Cache: Always Keep a Source of Truth

Redis/managed caches reduce latency and load, but you must decide:

- Does a cache miss/failure halt checkout or fall back to the DB?
- What are the TTL, invalidation, thundering herd, and cache stampede mitigations?
- What are the HA/replication/persistence modes of the Redis tier?
- Does cached session state require durable persistence?
- When the cache is cold after failover, does the DB have enough capacity for re-warming?

Never use a cache as the sole authoritative store for orders/ledgers. For secondary caches, graceful degradation can return **labeled/bounded** stale data or temporarily disable features depending on business correctness.

## 15. Identity, Key Vault, Networking, and Configuration: Overlooked SPOFs

### 15.1. Azure Resource Manager vs. Data Plane

An application should be designed to continue serving requests from the **existing data plane** when the management/control plane is temporarily unavailable. However, scaling, deploying, modifying networks/keys, and recovery may require the control plane; maintain **pre-provisioned/standby headroom and runbooks** so a management outage does not become a user outage.

### 15.2. Microsoft Entra / Managed Identity

Managed identities avoid long-lived passwords, yet the application still needs:

- Proper SDK/driver token acquisition, retry, and caching.
- Data-plane permissions on DB/Key Vault/Storage and correctly scoped Azure RBAC.
- Avoiding calls to the login/token endpoint on **every request** when SDKs provide safe caching.
- Avoiding caching expired tokens or using tokens with the wrong audience after failover.
- Tested identities/role assignments/tenant policies in the DR region.
- Securely managed break-glass identities that do not rely on one person.

**Azure RBAC Contributor does not automatically grant SQL SELECT**, and having a managed identity does not automatically open network paths. Losing identity or misconfiguring RBAC can take down an entire multi-zone workload simultaneously.

### 15.3. Key Vault Secrets and Certificates

- Avoid reading Key Vault synchronously **in every HTTP request**.
- Use supported SDK/managed integrations and caching/rotation with expiry and revocation policies.
- Define secret expiration, certificate rotation, and Key Vault access/network policies.
- If Key Vault is unavailable, decide how long the application continues with cached secrets **while maintaining security**.
- Region B must have secrets/certs/keys and permitted principals matching the chosen replication/DR model.
- Never copy client secrets manually into GitHub or container images.

**Security and reliability can conflict**: caching credentials for longer increases uptime during an Entra/Key Vault outage but increases exposure if a credential is revoked. Choose TTL/rotation based on your threat model rather than defaulting to "cache forever."

### 15.4. Private Endpoints and DNS

An App Service in region B might look healthy yet fail to connect to Azure SQL because:

- Private Endpoints exist only in region A/VNet A.
- Private DNS zone links/forwarding are not configured for B.
- NSGs/UDRs/Firewalls block outbound TCP/TLS.
- An FQDN resolves to or is replaced by a private IP causing a TLS hostname mismatch.
- Entra principals/DB roles differ on the secondary.

**A health endpoint returning 200 in region B does not prove DB writer/queue/Key Vault paths work.** Rehearse an **end-to-end transaction test** in staging using production-like credentials and networking.

### 15.5. IaC and Drift Management

Use Bicep/Terraform/ARM to version:

- Networking/DNS/Private Endpoints/routing.
- Zone/multi-region deployment settings.
- Identity/federation/role assignments.
- Databases, backup/HA/geo configurations.
- Diagnostic settings, alerts, runbooks, and outputs.
- Secret **references** rather than literal secrets in source/state.

However, **IaC can also be a source of common-mode failure**: a bad merge can alter all regions at once. Separate stages, restrict permissions, review what-if/plan outputs, enforce policy gates, and maintain rollback and state backups. Never run `terraform destroy` or `az group delete` to fix drift without analyzing dependencies.

## 16. Resilient Application Design: Timeouts, Retries, Circuit Breakers, Bulkheads

Reliability is not just redundant infrastructure. **Application code must decide what happens when a dependency is slow, returns 429/503, drops connections, or recovers from disruption.**

### 16.1. Deadlines First, Retries Second

Suppose checkout has a **2-second** p95 latency SLO. If an HTTP call to inventory has a 10-second timeout and the SDK retries three times automatically, a single request blows past its deadline before the app can respond.

~~~text
Client overall deadline:      2,000 ms
API work and serialization:     250 ms
DB transaction budget:          500 ms
Dependency budget:              750 ms
Network/margin:                 500 ms
~~~

This is an **assumed allocation**, not an Azure SDK default. When the caller has 250 ms left, downstream calls must not take 5 seconds. Propagate **deadlines/cancellation** properly; set connect timeouts, read timeouts, request timeouts, and retry budgets aligned with the SLO.

### 16.2. Exponential Backoff + Jitter

~~~text
Attempt 1 failed with transient 503.
Wait: small randomized backoff.
Attempt 2 if deadline still allows.
Wait: larger randomized backoff.
Attempt 3 only if policy permits and idempotent.
Otherwise fail fast / enqueue / degrade.
~~~

**Never retry infinitely**: when 10,000 clients retry immediately at once, a recovering dependency gets knocked down a second time. Jitter spreads load. Azure SDKs often include default retry policies; avoid **nested retries** across SDK + service + gateway + frontend that multiply requests exponentially.

### 16.3. Retry Matrix

| Failure | Retry? | Conditions |
|---|---|---|
| HTTP 429/rate limit | Possible | Backoff/`Retry-After` if available, quota and deadline |
| HTTP 503/transient network reset | Possible | Bounded attempts, idempotent operation |
| HTTP 401/403 | Generally not as a transient data error | Check tokens/permissions/policies; do not spam auth |
| HTTP 400/validation | No | Fix input |
| SQL deadlock/serialization conflict | Possible to retry **whole transaction** | Isolation/policy and idempotency |
| Unique key conflict | Do not retry blindly | Check business idempotency |
| Timeout after write that may have committed | Only with idempotency/reconciliation | Outcome is uncertain |
| Event Bus message redelivery | Reprocess safely | Stable event ID/processed IDs |

### 16.4. Circuit Breaker

When a payment service fails 90% of requests, instead of making every request wait for a 5-second timeout:

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Error threshold reached
    Open --> HalfOpen: Cooldown elapsed
    HalfOpen --> Closed: Limited probes healthy
    HalfOpen --> Open: Probe fails
~~~

**Closed:** requests flow normally. **Open:** fail fast / return degraded response, protecting resources. **Half-open:** allow a small probe volume to check if the dependency recovered. Circuit breaker thresholds must account for **sample size**, latency, error types, and duration; a breaker alone does not answer business questions like "was the payment already charged?"

### 16.5. Bulkheads

~~~text
Orders API:
  Max concurrent payment calls: 30
  Max concurrent catalog lookups: 100
  Bounded DB pool: 20

If payment hangs:
  payment calls are limited;
  catalog reads still have dedicated capacity.
~~~

These are **illustrative thresholds**. Separating thread pools, concurrency semaphores, or queue workloads prevents starvation. If everything still shares a single DB pool of 20, application bulkheading is incomplete.

### 16.6. Graceful Degradation and Fail-Safe

| Capability | When dependency fails | Acceptance criteria |
|---|---|---|
| Product recommendations | Omit recommendation panel | Does not block order creation |
| Email confirmation | Queue/retry later | Order is still saved and accessible |
| Catalog read | Serve near-fresh cached data with TTL | UI indicates staleness if it affects decisions |
| Inventory reservation | Reject/mark pending when unconfirmed | Never oversell |
| Payment authorization | Do not report success without proof | Never double-charge |
| Mandatory audit logging | Per compliance, may block operation | Do not "fail open" against policy |

**Fail open vs. fail closed** must follow business and security requirements. Product recommendation caches can serve stale results; auth decisions and payments must never assume success just because a provider is unreachable.

### 16.7. Bounded Retries in Java: Illustration

Plain Java example for an **idempotent HTTP GET**—do not use for a payment-creation POST:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

class ResilientCatalogClient {
    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .build();

    String readCatalog(URI uri) throws Exception {
        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofMillis(700))
                    .GET().build();
                HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

                if (response.statusCode() == 200) {
                    return response.body();
                }
                if (response.statusCode() != 429
                    && response.statusCode() != 503) {
                    throw new IllegalStateException(
                        "Non-retryable status " + response.statusCode());
                }
            } catch (IOException e) {
                if (attempt == maxAttempts) throw e;
            }
            if (attempt == maxAttempts) break;
            long jitterMs = ThreadLocalRandom.current()
                .nextLong(25, 125);
            Thread.sleep((1L << (attempt - 1)) * 100L + jitterMs);
        }
        throw new IllegalStateException("Catalog temporarily unavailable");
    }
}
~~~

**This illustrates the mechanism and is not a production-grade client:** it risks exceeding the **overall 2-second deadline** across attempts + sleeps, does not honor `Retry-After`, lacks circuit breaker/telemetry/cancellation support, and should not treat every `IOException` as transient. In production, prefer Azure SDK / Resilience4j / Spring Retry (supported versions) with enforced deadlines, error classification, and tests. Never copy this pattern to write endpoints lacking idempotency.

## 17. Idempotency, Transactions, Outbox, and Data Correctness

### 17.1. Why a Timeout After Commit Is Dangerous

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Orders API
    participant DB as SQL Database
    C->>API: POST /orders (idempotencyKey K)
    API->>DB: INSERT order with unique K
    DB-->>API: Commit OK
    Note over API,C: Network response lost
    C->>API: Retry POST /orders (same K)
    API->>DB: Look up K
    DB-->>API: Existing order
    API-->>C: Return same order ID, not a new order
~~~

Without an idempotency key, a client retrying after a timeout can create **two orders**. "HTTP 500" or a dropped socket does not tell you whether the transaction committed.

### 17.2. Database Uniqueness Is the Final Guardrail

Illustrative logical DDL:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL
);
~~~

This is **conceptually portable illustrative DDL** that omits identity IDs/timestamps/currency/specific SQL dialects and is **not for creating a production table**. The service must verify that the same key carries the **same payload/business intent**; reusing a key with a different payload should raise a conflict rather than silently returning the wrong order.

### 17.3. Transactional Outbox

~~~text
Transaction:
  INSERT orders(...)
  INSERT outbox(eventId, orderId, payload, state='PENDING')
COMMIT

Publisher:
  Read pending outbox
  Send event to Service Bus
  Mark published (may repeat)

Consumer:
  Deduplicate by eventId or business invariant
  Apply side effect once
  Complete message after successful processing
~~~

The producer may successfully send the message and crash before marking the outbox row published, causing the event to be sent again. Therefore, **an outbox typically provides at-least-once delivery**, not exactly-once across DB and broker without additional invariants/idempotency.

### 17.4. Payment Providers and Reconciliation

An external payment outside Azure requires:

- A stable merchant/order idempotency key if supported by the provider.
- Querying payment status before retrying after a timeout.
- Webhook processing with signature validation + deduplication.
- Periodic reconciliation between the provider ledger and the order DB.
- A manual exception queue/operational playbook.

**Never blindly retry a charge** after an API timeout, as the provider may already have accepted the transaction.

### 17.5. Data Schema Evolution During Failover

In active-passive setups, the secondary may run the same or a different app version during failover. Never recover region B from an older container image incompatible with the new DB schema. Decouple infrastructure deployment from schema rollout, use **forward/backward-compatible migrations**, test failover after releases, and periodically verify standby images/digests.

## 18. Observability: From Azure Monitor to SLO Dashboards

### 18.1. Telemetry Sources

| Source | Examples | Usage |
|---|---|---|
| **Application Insights/OpenTelemetry** | HTTP requests, exception traces, dependency spans | User flow latency, errors, correlation |
| **Azure Monitor platform metrics** | DB CPU/IO, App instances, queue length | Capacity/availability signals |
| **Diagnostic settings/resource logs** | Key Vault audit, DB errors, App Service logs | Detailed investigation/forensics |
| **Azure Activity Log** | Role changes, NSG, configuration, deployments | Control-plane change correlation |
| **Synthetic probes** | Test checkouts with synthetic data from multiple locations | End-to-end availability |
| **Business events** | Orders accepted, charged, reconciled | Business correctness |
| **DR/backup evidence** | Restore success, last sync, lag | Recoverability readiness |

**"No errors in logs" does not mean the service is healthy.** If diagnostic settings were deleted or ingestion broke, log error dashboards will look empty while customers still experience failures.

### 18.2. An SLI Dashboard Is More Than CPU

A Reliability dashboard should display:

~~~text
Checkout success SLI (request and business-based)
Checkout latency p50/p95/p99
Remaining error budget + burn rate
API 5xx and timeouts by region/version
DB connection failures/locks/CPU/IO/replication lag
Queue age, DLQ, retries and consumer processing lag
Key Vault/Entra failures and network reachability
Synthetic checks per region
Active region/writer/image digest
Last successful restore/DR drill and measured RTO/RPO
~~~

### 18.3. KQL Example: Request-Based Availability

If the workload instruments Application Insights into a workspace with an `AppRequests` table and columns as illustrated:

~~~kusto
AppRequests
| where TimeGenerated > ago(24h)
| where Name has "POST /orders"
| summarize
    Total=count(),
    Succeeded=countif(Success == true)
    by bin(TimeGenerated, 5m)
| extend SuccessRatePercent =
    iff(Total == 0, real(null), 100.0 * Succeeded / Total)
| order by TimeGenerated asc
~~~

**Do not apply the query verbatim to every workspace**: table/column names differ between workspace-based and classic App Insights. HTTP `Success` does not measure data correctness; if the API returns 202 while queue processing fails, you need a separate **business event completion SLI**.

### 18.4. KQL Example: Azure Activity Log After an Incident

If the subscription exports Activity Logs to `AzureActivity`:

~~~kusto
AzureActivity
| where TimeGenerated > ago(6h)
| project TimeGenerated, Caller, OperationNameValue,
          ActivityStatusValue, ResourceGroup, _ResourceId
| order by TimeGenerated desc
~~~

Correlate code/configuration changes with when the SLI degraded, but **temporal correlation does not prove causation**. Confirm the failure mode through logs/traces and reproduction.

### 18.5. Error-Budget Burn-Rate Alerts

Instead of alerting only when the error rate exceeds 1% for 1 minute, evaluate:

- **Fast burn:** the SLO budget is draining rapidly over a short window; page on-call.
- **Slow burn:** the budget is draining gradually over hours/days; file a ticket or lower-severity alert.
- **Traffic volume:** 1 error out of 2 requests is not the same as 10,000 errors out of 1 million requests.
- **Monitoring gaps:** missing metrics must be detected rather than treated as "0 errors."

Set multi-window, multi-burn-rate thresholds based on your SLO and real noise levels; do not copy-paste formulas across services without testing historical false positives.

### 18.6. Azure Service Health and Resource Health

**Azure Service Health** provides signals about incidents/maintenance/advisories affecting Azure services by region/scope. **Resource Health** reports the status of certain resources from the platform's perspective. Both are useful but do not replace end-to-end SLIs: service health can be green while a deployment breaks your app, or a platform incident may not capture all of your network/app dependencies.

Runbooks must distinguish **Azure service events**, **resource degradation**, **application bugs**, **data inconsistency**, and **security incidents** before deciding to fail over.

## 19. Incident Response, On-Call, and Controlled Change

### 19.1. Incident Lifecycle

~~~mermaid
flowchart LR
    ALERT[SLI/health alert] --> TRIAGE[Confirm scope and severity]
    TRIAGE --> COMMAND[Incident commander + owners]
    COMMAND --> MITIGATE[Contain / degrade / failover if justified]
    MITIGATE --> VERIFY[Validate critical flows and data]
    VERIFY --> POST[Postmortem and corrective actions]
    POST --> TEST[Update drills, SLO and runbooks]
~~~

**You do not need to wait for full root cause before mitigating impact:** shifting traffic, rate-limiting, or disabling secondary features can be effective mitigations when backed by safety checks. However, high-risk actions like failing over a DB writer or altering identity policies require authorized personnel and consideration of data impact.

### 19.2. What Belongs in a Standard Runbook?

- Trigger: what symptoms and SLO thresholds activate it?
- Preconditions: scope/subscription/resource IDs/region/identity.
- Decision tree: regional, DB, network, code, or external provider failure?
- Risk: data loss window, downtime, split-brain, compliance.
- Steps: who acts, exact commands, required approvals, abort/rollback points.
- Verification: real traffic + synthetic tests + data integrity checks.
- Escalation: DBA/IAM/network/Azure support, business representative.
- Communication: incident updates, stakeholder/customer status.
- Evidence: UTC timestamps, dashboard links, logs, last successful restore.
- Post-incident: action items with owners/deadlines and re-drilling.

### 19.3. Do Not Auto-Failover on a Single Probe Failure

A single HTTP 500 from one origin does not necessarily mean a regional outage. Automated failover without hysteresis can cause **flapping** between two regions and risk data divergence. Combine multiple signals: multi-location synthetic probes, regional health, DB writer/lag, queues, retry rates, readiness, and proper quorum/timeout logic.

### 19.4. Change Management Is Part of Reliability

Build/deploy pipeline:

~~~text
PR → tests + security checks → staging → canary →
health/business SLO gates → production traffic ramp →
monitor → rollback/forward-fix
~~~

Network, identity, and DB schema changes must also go through review/what-if/canary with bounded blast radius. **Rolling back an app image does not roll back all side effects.** If feature flags are used for mitigation, ensure the flag service does not become a mandatory dependency on every request and has safe defaults.

### 19.5. Blameless Postmortems

Postmortems should document: SLO/data impact, UTC timeline, contributing factors, detection gaps, mitigations that worked/failed, recovery metrics, and prioritized corrective actions. The goal is **improving the system**, not finding "who clicked the wrong button," while still maintaining accountability and appropriate change controls.

## 20. Backup, Restore, Regional Failover, and Disaster Recovery Plans

**Disaster Recovery (DR)** is the ability to **restore user flows and data** after a disaster beyond what individual components can self-heal. A DR plan must start from business flows, not merely list backup files.

### 20.1. Three Different DR Scenarios

| Incident | Is HA or a replica enough? | Appropriate recovery |
|---|---|---|
| A single VM/pod dies | Possibly, with proper replicas and health routing | Auto replace/rollout |
| Primary DB node fails | Possibly, depending on tier/HA settings | Platform failover + reconnect and verify |
| Entire Availability Zone fails | Possibly, with zone redundancy | Zone-tolerant routing/capacity |
| Entire region unavailable | Typically requires a dedicated DR design | Secondary region/data promotion/cutover |
| App accidentally drops a table | Replicas may already receive the drop | PITR/backup/logical recovery, reconciliation |
| Ransomware/credential compromise | Replicas may also be compromised | Protected immutable backups, incident containment |
| Global DNS/identity misconfiguration | Multi-region may fail together | Config rollback/break-glass/cross-team response |

**Logical data-loss risks** and **infrastructure outages** require different recovery patterns. Never assume a geo-replica replaces independent backups.

### 20.2. Recovery Inventory: Every Component Needed to Recover

~~~text
Global entry:
  DNS, Front Door / Traffic Manager, certificates, WAF policies

Compute:
  App Service / Container Apps / AKS / VM images and configuration

State:
  Azure SQL/PostgreSQL, Storage, Cosmos DB, queues, outbox, cache

Identity and secrets:
  Managed identities, Entra roles, Key Vault, certificates, access policies

Networking:
  VNets, Private Endpoints, Private DNS, NSGs, UDRs, Azure Firewall

Observability:
  Log Analytics, telemetry, SLO alerts, incident communications

Delivery:
  IaC state, artifact image digests, release versions, runbooks
~~~

Without **service configuration, DNS, RBAC, or container images**, a restored DB still does not make a working application for users.

### 20.3. DR Runbook with Clear Preconditions

1. **Declare:** the incident commander confirms scope, severity, customer impact, and failover criteria.

2. **Freeze risky writes/deployments:** pause operations that could cause divergence per policy while preserving logs/forensic evidence.

3. **Determine data authority:** which region is the writer, what is the last replication timestamp, and which transactions were acknowledged?

4. **Recover data:** promote a replica or restore a backup via a supported method; record the recovery point.

5. **Validate dependencies:** secrets, identities, TLS, Private DNS, Service Bus namespaces, Storage access, app configs.

6. **Start/reconfigure workloads:** scale secondary compute/consumers and verify correct image/digest.

7. **Switch traffic:** update Front Door/global router/DNS per policy after DB B is ready.

8. **Verify:** synthetic checkout, idempotency, order totals, queue lag, health/latency, telemetry.

9. **Communicate:** share status, actual RPO/RTO, degraded features, and ownership.

10. **Stabilize/plan failback:** restore redundancy, re-seed the former primary, assess data repair.

These steps are a **framework**, not an automated Azure failover command. Each service needs a detailed runbook with **resource IDs, commands, preconditions, approvals, and rollbacks** tested in a lab.

### 20.4. What Backup Health Requires

- Latest backup succeeded with appropriate retention.
- Backup scope covers all databases/containers/critical configurations.
- Restore points are **actually readable and consistent** at the application level.
- Backup copies cannot be easily deleted/altered by the same production principal.
- Permissions and network paths exist to restore into an isolated environment.
- Encryption keys/certificates/KV permissions remain available after a disaster.
- **Restore duration is measured** on realistic dataset sizes.
- Data validation/query sampling/checksums run before cutover.

**Never confuse "backup job status succeeded" with "accurate data has been recovered."** Restore rehearsals test recoverability, not merely whether a copy exists.

### 20.5. PITR Does Not Undo All Side Effects

If you restore the DB to 10:00 after sending a payment and Service Bus event at 10:03:

~~~text
10:00 DB restore point
10:01 Order accepted
10:02 Payment charged externally
10:03 Email sent / downstream message processed
10:04 Incident
10:15 DB restored to 10:00
~~~

After restoration, the DB may "not know" about the charged payment. **Reconciliation is required** using the payment provider ledger, event/outbox logs, and audit trails; do not simply replay every event if that risks double-charging.

### 20.6. Measuring RPO/RTO Across the Full Workflow

~~~text
Failure start UTC:               09:00
Incident detected UTC:           09:03
Failover approved UTC:           09:07
DB secondary writable UTC:       09:15
App/network fully ready UTC:     09:19
Checkout SLI recovered UTC:      09:22

Measured RTO: 22 minutes
Last confirmed recoverable order: 08:58
Potential RPO: 2 minutes, subject to reconciliation
~~~

Retain measurement evidence. If the target RTO is 15 minutes, the runbook **FAILED** even if "database recovery succeeded," and you must plan how to reduce detection, approval, cutover, and validation times.

### 20.7. DR Protection and Security

The DR site must maintain your Security posture:

- Do not open public database access or broad firewalls just to recover faster if it violates policy.
- Do not grant subscription Owner to general users.
- Do not restore sensitive data into an unauthorized region/tenant.
- Do not store cleartext secrets or unmanaged key material in backups.
- Do not allow automatic failover where **split-brain** or unhandled data conflicts can occur.
- Provide just-enough emergency privileges with auditing and time bounds.

## 21. Reliability Testing: Chaos Engineering and Game Days

### 21.1. Why Run Controlled Fault Tests?

An architecture with sufficient replicas and backups on paper can still fail in practice:

- The autoscaler reacts too slowly to add capacity.
- DB clients hold stale connections for too long.
- Readiness probes stay green even when the DB writer is unavailable.
- Front Door reroutes quickly, but Key Vault/DNS in region B fails.
- The secondary SQL replica lags beyond RPO.
- On-call lacks permissions to promote/restore.
- The runbook references outdated resource names.

**Controlled fault injection** uncovers these failure modes before customers hit them. Start small in lab/staging and expand scope as maturity grows.

### 21.2. Hypothesis-First Game Day

~~~text
Hypothesis:
  "When one API pod fails in staging, checkout success remains ≥99.9%
   and p95 latency stays below the approved threshold."

Baseline:
  synthetic order requests, DB/queue metrics, pod placement

Injection:
  safely terminate one chosen staging replica

Observe:
  retries, load balancer routing, latency, errors, autoscaler response

Abort:
  stop if error budget/latency threshold exceeded

Verify:
  no lost/duplicated synthetic orders, system fully healthy
~~~

Never run an experiment that is just "shut down a server to see what happens." Define an **objective, baseline, owner, blast radius, safety stop, and cleanup**.

### 21.3. Test Cases by Maturity Level

| Level | Safe fault injection | What it verifies |
|---|---|---|
| 1 | Terminate one staging pod/instance | Redundancy and readiness |
| 2 | Simulate dependency latency/503 | Timeouts, retries, circuit breakers |
| 3 | Briefly interrupt staging DB connection | Pool refresh, transaction outcomes |
| 4 | Stop staging queue consumer | Backpressure, DLQ, replay |
| 5 | Simulate zone loss in an authorized environment | Placement and headroom |
| 6 | Rehearse staging regional traffic failover | Global ingress/secondary readiness |
| 7 | Restore database backup into isolated environment | PITR accuracy + RTO |
| 8 | Full-workflow DR game day (approved) | Incident command, RPO/RTO, and reconciliation |

### 21.4. Azure Chaos Studio and Other Tools

Azure Chaos Studio supports various **fault actions/experiments** for supported targets with required permissions. However, **not every Azure resource supports the same fault types**, and fault injection has **real impact** if run against production. Beyond Chaos Studio, you can use test doubles/proxies, Kubernetes fault tools, or safe scripts in lab environments.

Verify targets/SKUs/agents/permissions/regions, blast radius, and recovery before running. **Never use Chaos Studio to wipe out an entire regional database or delete production resources just to prove an SLO.**

### 21.5. Injection vs. Rehearsal

- **Injection:** introducing controlled faults (latency, killing a replica, throttling).
- **Rehearsal:** practicing people/processes (declaration, bridge, DB restore, failback).
- **Load test:** verifying throughput/headroom and overload behavior.
- **Restore test:** proving backup recovery.
- **Security response drill:** simulating lost keys or compromised principals without real unauthorized access.

A good game day combines **technical and procedural** exercises, measuring human decision time and verifying data correctness.

### 21.6. Results Must Become Action Items

After each drill, record:

~~~text
Experiment ID:
  reliability-lab-zone-failure-001

Scope and owners:
  staging orders-api / SRE + DBA

Expected:
  Checkout p95 below objective; no lost orders

Observed:
  transient 5xx, reconnect time, database queue lag

RTO/RPO:
  measured vs objectives, include detection and validation

Findings:
  source of common-mode failure, operational gap

Actions:
  code/config/IaC/runbook changes with owner and deadline

Evidence:
  metrics/traces/checksums and approved change ticket
~~~

Do not mark a game day passed merely because the system "came back up." If backlogged messages or unpublished outbox rows remain after the test, measure **drain time and reconciliation** before closing.

## 22. FinOps of Reliability: Pay for Targets, Not Complexity

### 22.1. Layers of Redundancy Cost

| Component | Costs that can increase with higher reliability |
|---|---|
| Multi-zone compute | Replicas/instances, load balancers, cross-zone paths |
| Multi-region compute | Warm/hot standby, minimum cluster/plan in secondary |
| Data replication | Geo copies, standby databases, extra storage/IO |
| Backups | Retention, immutable copies, restore drills, egress |
| Global entry | Front Door/Traffic Manager, WAF, probes, traffic |
| Messaging | Premium tier, redundancy features, throughput units |
| Monitoring | Logs/metrics retention, synthetic tests, on-call tooling |
| Networking | Private Endpoints, NAT, VPN/ExpressRoute, firewalls |
| Operations | Game days, incident response, change reviews, training |
| Security | Key management/role separation and backup protection |

**Actual costs depend on region, SKU, reservations, data usage, and pricing at deployment time.** Do not infer exact Azure prices from this table; use the Azure Pricing Calculator/Cost Management and check service-specific pricing.

### 22.2. Costing Against Business Impact

A sound decision compares:

~~~text
Cost of additional zone/region redundancy
  VS
Expected business impact of downtime/data loss
  + compliance penalties
  + reputational impact
  + operational recovery cost
~~~

Not every workload warrants the cost of multi-region active-active. If BI reporting tolerates a 24-hour delay, **batch restore** may be far more appropriate than running a warm standby year-round.

### 22.3. Two Illustrative Architectures

| Criterion | Zone-redundant single region | Multi-region active-passive |
|---|---|---|
| Survives single zone failure | Can be strong if all components support it | Primary still needs zone design |
| Survives region outage | Insufficient | Provides recovery path when fully prepared |
| Data RPO | Follows HA/backup | Follows replication/backup lag |
| RTO | Can be low for instance/zone | Depends on promote/cutover/secondary capacity |
| Cost | Typically lower | Higher standby/replication/network/operations cost |
| Complexity | Lower | More identities/DR states/rollback scenarios |

### 22.4. Budget Alerts Are Not Hard Caps

Azure budget alerts detect rising costs; they do not automatically shut off resources when exceeded. **Never configure automation to delete production DBs or secondary clusters when a cost threshold is crossed.** Instead: find orphaned resources, tune replicas, pools, logging, and retention, and right-size scale/standby to SLOs with owner sign-off.

### 22.5. Improving Reliability by Reducing Load

Before upgrading to a larger DB tier:

- Fix missing indexes and N+1 queries.
- Shorten transactions and tune Hikari pool × replicas.
- Cache read-only/non-critical data with appropriate TTLs.
- Move notifications/reporting to async queues.
- Add backpressure and request admission control.
- Trim duplicate logging and unnecessary debug data.
- Scale compute only against measured bottlenecks.

**Performance optimization and architectural simplification can increase reliability while lowering cost.** Never cut backup retention or critical HA just to hit short-term cost targets.

### 22.6. Documenting Decisions

Every reliability decision should capture:

~~~text
Decision: warm standby in secondary Azure region
Business flow: checkout
Targets: RTO 30m, RPO 5m (illustrative)
Alternatives: backups only, multi-zone, active-active
Evidence: drill logs, load tests, replication lag
Costs: compute, storage, monitoring, drills
Risks: async data loss, split-brain, operator delay
Owner/review: platform + DBA + business / quarterly
~~~

This is a **skeleton Architecture Decision Record (ADR)**, not an actual decision for any specific system. Whenever business SLOs change, re-evaluate both cost and design.

## 23. Case Study: An Ordering System with 30-Minute RTO and 5-Minute RPO

### 23.1. Scenario

An e-commerce business deploys:

~~~text
Global edge:        Azure Front Door
Frontend/API:       Spring Boot on Azure Container Apps
Order data:         Azure SQL Database
Messaging:          Azure Service Bus + outbox
Object storage:     Azure Blob Storage
Secrets:            Azure Key Vault / managed identity
Telemetry:          Application Insights + Azure Monitor
IaC/CI:             Bicep/Terraform and GitHub Actions OIDC
DR region:          approved secondary Azure region
~~~

**Example targets** assumed by the business owner:

| User flow | SLO | RTO | RPO |
|---|---|---:|---:|
| Checkout accepted accurately | 99.9% over 30 days | 30 minutes | 5 minutes |
| View order status | 99.5% | 1 hour | 15 minutes |
| Email processing | Complete within 4 hours | 8 hours | 1 hour |
| BI reporting | Previous day's data available | 24 hours | 24 hours |

Not all of these values fall under Azure SLAs. They are **workload targets** that must be designed and proven, and the business may require **zero tolerance for losing payment evidence** even when the order RPO is 5 minutes.

### 23.2. High-Level Design

~~~mermaid
flowchart TB
    USERS[Customers] --> FD[Azure Front Door]
    FD -->|Primary traffic| APPA[Region A Container Apps multi-zone]
    FD -. DR traffic .-> APPB[Region B warm standby]
    APPA --> SQLA[(Azure SQL A writer)]
    SQLA -->|Geo data replication if supported| SQLB[(Azure SQL B secondary)]
    APPB --> SQLB
    APPA --> OA[(Order outbox A)]
    OA --> SB[Service Bus / worker with idempotency]
    SB --> PAY[Payment provider]
    APPA --> KVA[Key Vault + MI A]
    APPB --> KVB[Key Vault + MI B]
    OBS[App Insights + Azure Monitor] -. monitor .-> APPA
    OBS -. monitor .-> APPB
    OBS -. monitor .-> SQLA
    OWNER[Incident command + DBA + SRE] -. control .-> FD
    OWNER -. promote safely .-> SQLB
~~~

**This diagram is an assumed architecture and does not guarantee that the Azure SQL secondary is writable.** You also need regional recovery for Blob Storage and Service Bus; if order data moves to B while queues remain only in A, many worker workflows can be lost or replayed incorrectly.

### 23.3. Failure-Mode Review

| Failure | Expected impact | Countermeasure | Verification |
|---|---|---|---|
| One Container App replica dies | Brief latency/retry bump | Replicas and readiness routing | Kill 1 staging replica |
| Zone A fails | 1/3 capacity lost | Zone redundancy/headroom | Safe zone test |
| Azure SQL primary failover | JDBC reset/timeout | Driver reconnect, bounded retry | SQL failover in staging |
| Service Bus publish fails | Outbox pending grows | Retry publisher/replay | Stop consumer / simulate 503 |
| Payment provider down | Order pending, no double charge | Idempotency/reconciliation | Provider sandbox outage |
| Region A outage | Primary unavailable | Warm B, DB promotion, traffic switch | DR game day |
| Operator drops table | Logical data deletion | PITR protected backup | Restore test in isolated env |
| DNS/Key Vault misconfig | Single/all regions may fail | IaC, region-specific validation, rollback | Config negative test lab |

### 23.4. Failure Timeline and Actual RTO

~~~text
09:00 Region A cannot serve requests.
09:02 External synthetic probes fail in 2+ locations.
09:05 Incident commander declares regional incident.
09:09 DBA reviews last replication point, approves promotion.
09:14 Azure SQL secondary available as primary.
09:17 Region B app/Key Vault/private networking checked.
09:20 Front Door routes production traffic to Region B.
09:24 Checkout synthetic and real SLI recover.
09:28 Outbox/queue reconciliation initiated.
~~~

In this example, user-flow **RTO = 24 minutes**, meeting the 30-minute objective. However, RPO **must still be measured against actual transaction data**, not inferred from DB promotion time. If the last committed/replicated order in B only reached 08:54, a potential 6-minute data gap **exceeds the 5-minute RPO objective** even though RTO passed.

### 23.5. Data Reconciliation After Failover

Identify:

- Order IDs acknowledged in A that are missing in B.
- External payments already charged whose order record is missing in B.
- Outbox events already published where the DB restore rolled back to pending.
- Service Bus messages in-flight, DLQ, or duplicated.
- File/blob attachments not yet replicated to B.
- The right recovery path: replay from authoritative evidence while avoiding double-writes.

Sample reconciliation table:

| Order ID | Client received success? | Payment state | DB B record? | Action |
|---|---|---|---|---|
| O-100 | Yes | Charged | Yes | OK |
| O-101 | Yes | Charged | No | Investigate and reconstruct with audit |
| O-102 | Unknown | Not charged | No | Safe idempotent retry |
| O-103 | Yes | Pending | Yes | Resume worker from outbox |

**These rows are synthetic data**, not real transactions. Rebuild actions require business rules, approvals, and auditing; never manually insert ledger records from unverified logs.

### 23.6. Failback B → A

Once A recovers:

1. Confirm B is the current authoritative writer.
2. Recreate data replication from B back to A using supported Azure SQL features.
3. Ensure identity/Key Vault/Service Bus/Blob/config in A are not stale.
4. Verify canary traffic does not cause split-brain.
5. Cut back only after approval, under SLO monitoring and reconciliation.
6. Verify the new standby DR posture is re-established.

### 23.7. Architectural Outcomes That Cannot Be Skipped

Multi-region provides a recovery path, but carries an **RPO trade-off due to async replication**. Checkout must use idempotency/outbox. Region B must have full **compute, networking, DB, credentials, queues, artifacts, and on-call**—not just an empty Azure subscription. RTO/RPO thresholds are considered **met only when proven by an actual drill**, not when the design document is finished.

## 24. Azure Tools and Read-Only Inventory Commands

The commands below are solely for **inspecting configuration on authorized resources**—not for creating resources, promoting databases, failing over, or deleting data. Run from a lab terminal with Azure CLI and appropriate Reader/Monitoring Reader permissions; replace placeholders with approved resource IDs.

### 24.1. Confirm Tenant/Subscription and Inventory

~~~bash
az account show \
  --query "{subscription:id,name:name,tenant:tenantId}" \
  -o table

az resource list \
  --resource-group "<approved-lab-resource-group>" \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table
~~~

Do not identify production vs. lab solely by names like `dev` or `test`; a resource group can contain shared components.

### 24.2. Inspect App Service / Container Apps

~~~bash
az webapp show \
  --resource-group "<approved-rg>" \
  --name "<approved-webapp-name>" \
  --query "{id:id,state:state,location:location,hostNames:hostNames}" \
  -o json

az containerapp show \
  --resource-group "<approved-rg>" \
  --name "<approved-containerapp-name>" \
  --query "{id:id,location:location,latestRevision:properties.latestRevisionName}" \
  -o json

az containerapp revision list \
  --resource-group "<approved-rg>" \
  --name "<approved-containerapp-name>" \
  -o table
~~~

The latest revision **does not automatically receive 100% of traffic** in multiple-revision mode; verify actual ingress, weights, and health. Commands depend on the corresponding Azure CLI / Container Apps extension.

### 24.3. Inspect Azure SQL and PostgreSQL

~~~bash
az sql db show \
  --resource-group "<approved-rg>" \
  --server "<approved-sql-logical-server>" \
  --name "<approved-db-name>" \
  --query "{id:id,name:name,location:location,status:status}" \
  -o json

az postgres flexible-server show \
  --resource-group "<approved-rg>" \
  --name "<approved-pg-server-name>" \
  --query "{id:id,location:location,state:state,highAvailability:highAvailability}" \
  -o json
~~~

**Metadata inspection does not prove backups can be restored.** Check HA/backup/replica/failover details via the proper service API/version and run a restore rehearsal in an isolated environment. Never run `az sql failover-group failover` or PostgreSQL promotion commands on production during this lesson.

### 24.4. Inspect Storage Account and Service Bus

~~~bash
az storage account show \
  --resource-group "<approved-rg>" \
  --name "<approved-storage-account>" \
  --query "{id:id,location:location,sku:sku.name,kind:kind}" \
  -o json

az servicebus namespace show \
  --resource-group "<approved-rg>" \
  --name "<approved-servicebus-namespace>" \
  --query "{id:id,location:location,sku:sku.name}" \
  -o json
~~~

`ZRS`/`GZRS` SKUs and Service Bus tiers are evaluation inputs; they **do not prove DR/data-loss semantics have been rehearsed**. Never run a Storage account failover to "check" without risk approval.

### 24.5. Discover Metrics Before Querying Data

~~~bash
APP_ID="<approved-resource-id>"

az monitor metrics list-definitions \
  --resource "$APP_ID" \
  --output table

# Once a listed metric name is chosen:
az monitor metrics list \
  --resource "$APP_ID" \
  --metric "<supported-metric-name>" \
  --interval PT5M \
  --output json
~~~

Metric names, aggregations, and dimensions vary by resource provider; pick them from **list-definitions**. Do not assume a `CpuPercentage` query exists on every resource.

### 24.6. Read Activity Log

~~~bash
az monitor activity-log list \
  --resource-group "<approved-rg>" \
  --offset 1d \
  --query "[].{time:eventTimestamp,operation:operationName.value,status:status.value}" \
  -o table
~~~

Activity Log records **control-plane events**, not full request traces or DB queries. Use Azure Monitor/Application Insights/diagnostic settings to correlate runtime evidence.

### 24.7. Read-Only Does Not Mean Non-Sensitive

Some `az resource show` or `list` calls can return sensitive metadata (hostnames, IDs, configuration references). Restrict output with `--query`, avoid printing tokens/secrets/connection strings in shared terminal logs, and never publish production output in public learning materials.

## 25. Guided Lab: Applying Reliability to an Azure Application

**This lab must not be run on production without approval.** You can complete it at two levels:

- **Lab A — architecture and read-only inspection:** no resource creation or modification required.
- **Lab B — hands-on rehearsal:** only within an authorized **dedicated subscription/resource group and synthetic data**.

### 25.1. Step 1: Define User Flows and Business Contract

Choose a hypothetical application `orders-api`:

~~~yaml
workload: orders-api
environment: staging
businessOwner: ecommerce-operations

criticalFlows:
  checkout:
    successSlo30dPercent: 99.9
    latencyP95TargetMs: 2000
    rtoMinutes: 30
    rpoMinutes: 5
    sourceOfTruth: azure-sql-orders
  orderStatusRead:
    successSlo30dPercent: 99.5
    rtoMinutes: 60
    rpoMinutes: 15
  emailConfirmation:
    completionTargetMinutes: 240
    rtoMinutes: 480
    rpoMinutes: 60

notes:
  - Example only; obtain real business approval
  - Define denominator, synthetic checks and data correctness
~~~

**This is an example target specification document**, not an Azure ARM/Bicep schema or YAML configuration you can apply directly with `kubectl apply`. Owners and SLOs must be approved by the business, with exact numerator/denominator definitions.

### 25.2. Step 2: Draw the Dependency Graph

Use the diagram from Section 3 or draw your own:

~~~text
Client → Front Door → API → Azure SQL
                           ↓
                          Outbox → Service Bus → Worker → Payment
                           ↓
                          Blob Storage / Key Vault / Identity

CI/CD and IaC → provision / update
Azure Monitor → telemetry and alerts
On-call/DBA/IAM → incident decisions and recovery
~~~

Mark **critical synchronous dependencies** and services that can wait asynchronously. Identify one SPOF and one common-mode failure that could affect multiple zones/regions.

### 25.3. Step 3: Build an FMEA

Select at least **5 failure modes**:

1. An API replica crashes.
2. Azure SQL failover/connection reset.
3. Service Bus send timeout or consumer backlog.
4. Key Vault RBAC/config misconfiguration.
5. A zone/region becomes unavailable.

For each mode, document user impact, detection, bounded mitigation, recovery owner, whether data is affected, and the verifying test case.

### 25.4. Step 4: Read-Only Azure Inventory

If you have a lab subscription:

~~~bash
az account show --query "{name:name,id:id}" -o table

az resource list \
  --resource-group "<approved-lab-rg>" \
  --query "[].{name:name,type:type,location:location}" \
  -o table
~~~

Do not read unrelated project source code or modify resources while performing the theoretical exercise. Without Azure access, use hypothetical resource names in your diagram.

### 25.5. Step 5: Verify Zone / Multi-Region Choices

Fill in the table:

| Component | Zone config | Region/DR config | RTO/RPO risk |
|---|---|---|---|
| Ingress | Does global routing have a health policy? | Is secondary origin ready? | Routing out of sync with DB promotion |
| API | Multiple replicas across zones? | Warm/active region B? | Capacity/cold start |
| Azure SQL | HA/zone supported/active? | Replica/backup/failover group? | Async lag/restore time |
| Service Bus | Tier/HA behavior? | Secondary namespace/data recovery? | Missing in-flight messages |
| Storage | LRS/ZRS/GRS/GZRS? | Last sync/account failover? | Potential data loss |
| Key Vault | Access/identity/region? | Secret/key recovery? | Common-mode access failure |
| Monitoring | Multi-location synthetics? | Do alerts still work if A fails? | Blind spots |

If a row lacks evidence, record **UNKNOWN / TO VALIDATE**—never assume "zone redundant" merely because a resource is a managed service.

### 25.6. Step 6: Design Bounded Retries

Assuming a read-only catalog GET, try:

~~~text
First attempt times out after 500 ms.
Retry once after random backoff.
If second attempt fails or deadline nearly exhausted:
  return a controlled degraded response
  and emit a metric/trace.
~~~

Evaluate a **retry storm** if 1,000 clients retry simultaneously. For payment POSTs, explain why a stable idempotency key and ledger reconciliation are needed.

### 25.7. Step 7: Non-Destructive Game Day

In staging:

1. Confirm owner, approvals, scope, and abort conditions.
2. Enable synthetic traffic with dummy data.
3. Record baseline SLI, p95, queue lag, and DB connection counts.
4. Simulate a dependency returning HTTP 503/latency using a **test double**—never alter production DNS/networking.
5. Observe timeouts, circuit breakers, retry budgets, and API responses.
6. Stop injection; confirm service recovery with no backlog or duplicate transactions.
7. Record actual duration and corrective actions.

If you want real zone/DB failover, use **separate lab resources** and a service-specific procedure approved by DBA/SRE. Never run it on production just to "pass the lab."

### 25.8. Step 8: Restore Rehearsal

Instead of deleting a DB to test:

~~~text
1. Identify authorized isolated database and backup point.
2. Request restore to a NEW test database/server.
3. Measure restore duration.
4. Validate schema, row counts, key business invariants.
5. Check permissions, application connectivity, TLS, DNS.
6. Check consistency with synthetic outbox/payment records.
7. Record RPO/RTO evidence.
8. Clean up only lab restore resources after approval.
~~~

**Restores must target an environment without altering source data.** If you lack permissions/backups, simulate the runbook and document the blocker—never request Owner or modify live environments on your own.

### 25.9. Step 9: Calculate Error Budget and Capacity

Assume a 99.9% SLO over 30 days and 17 minutes of measured downtime:

\[
\mathrm{ErrorBudgetRemaining}
=43.2-17=26.2\text{ minutes}
\]

This is valid only for the **30-day time-based availability** example. For a request-based SLO, calculate failed requests over total requests, where high-traffic periods carry greater weight.

If there are 24 API replicas, each with a pool capped at 15 DB connections:

\[
24\times15=360\text{ potential DB connections}.
\]

Propose a pool/replica/capacity plan that stays within the connection budget while leaving headroom for failover/reconnect storms.

### 25.10. Step 10: Passing Criteria

| Deliverable | Evidence |
|---|---|
| Business SLO/RTO/RPO | Owner sign-off and measurement definitions |
| Dependency map | Includes identity/network/data/people |
| FMEA | At least 5 failures, mitigations, and owners |
| Zone/region strategy | Distinguishes zone vs. geo and supported tiers |
| Retry/idempotency | Bounded attempts, no double-charge |
| Data recovery | PITR/backup vs. geo-replica, restore plan |
| Drill | Safe hypothesis/baseline/injection/abort/results |
| Observability | User SLI + dependency metrics + synthetic checks |
| FinOps | Cost/redundancy trade-off and budget owner |
| Operational | Incident runbook, failback, and corrective actions |

## 26. Comprehensive Review Questions and Model Answers

### 26.1. Review Questions

1. How does reliability differ from availability, durability, and recoverability?
2. List the five Reliability design principles and give an example for each.
3. Why can a workload with multiple API replicas still have a single point of failure?
4. Distinguish Service Level Indicator, Objective, and Agreement.
5. How large is the time-based error budget for a 99.9% SLO over 30 days?
6. Why can a request-based SLI not always be converted into minutes of downtime?
7. How does RTO differ from RPO? Give an example where one is good and the other is poor.
8. What questions must a Business Impact Analysis answer?
9. How does FMEA help design, and can it replace a game day?
10. Distinguish process, Availability Zone, region, and control-plane failures.
11. What kind of failure mode is a shared Key Vault/RBAC configuration across three zones?
12. How does a zonal resource differ from a zone-redundant resource?
13. Why must N+1 capacity be evaluated for losing a zone?
14. How does active-passive differ from active-active? Is a two-writer database always needed?
15. Do paired Azure regions automatically guarantee full application failover?
16. Why must Front Door routing and SQL failover be coordinated?
17. What factors affect Traffic Manager DNS failover?
18. How does a liveness probe differ from readiness and synthetic user-flow probes?
19. In AKS, does a PodDisruptionBudget prevent every zone outage?
20. Does choosing an App Service zone-redundant plan guarantee database HA?
21. How does Azure SQL PITR differ from a failover group / geo-replica?
22. Does a PostgreSQL Flexible Server read replica automatically become writable when the source goes down?
23. Distinguish LRS, ZRS, GRS/GZRS, and their read-access variants.
24. Why can geo-replicated data still lose records written shortly before an incident?
25. What conflict/consistency policies does Cosmos DB multi-write require?
26. Distinguish Service Bus metadata DR from message data replication.
27. Why do queues need idempotent consumers and an outbox?
28. Why should Redis Cache not be the sole source of truth for orders?
29. How do bounded retries, exponential backoff/jitter, circuit breakers, and bulkheads differ?
30. When is fail-open vs. fail-closed safe?
31. Why is HTTP 200 insufficient proof that order data is accurate?
32. Why can a timeout after DB commit still cause duplicate orders?
33. With 30 replicas × 30 connections, what is the potential connection budget?
34. During an Entra/Key Vault outage, what risk comes from caching tokens indefinitely?
35. Why does a Private Endpoint in region A not guarantee region B runtime can connect to the DB?
36. Why can IaC create a common-mode failure in multi-region setups?
37. What should an SLI/SLO dashboard include besides CPU?
38. How do you distinguish Azure Service Health, Resource Health, and app health?
39. What minimum steps belong in a regional failover runbook?
40. Why is a separate failback runbook needed after the old region recovers?
41. Why does a PITR restore not automatically reverse external payments?
42. How should fault injection define its hypothesis, abort conditions, and owner?
43. How do you prove that measured RTO/RPO targets are met?
44. When is a multi-region standby not worth the cost?
45. Design a checkout architecture resilient to regional failure without double-charging.

### 26.2. Model Answers

**Question 2:** Business requirements, resilience, recovery, operations, and simplicity. Examples: 99.9% checkout SLO; zone replicas + backpressure; PITR/DR drills; Azure Monitor/on-call/runbooks; decoupling email from the synchronous checkout path.

**Question 5:** `30 × 24 × 60 × 0.001 = 43.2 minutes` of error budget for 30-day time-based availability.

**Question 7:** RTO is the time to restore service; RPO is the acceptable data age/loss. Restoring a DB to 1 minute before an incident while taking 6 hours to start the application yields an RPO near 1 minute and an RTO of 6 hours.

**Question 12:** A zonal resource resides in one chosen zone; a zone-redundant service is designed to replicate/remain available across zones where supported by SKU/region. A single-zone resource still has a zone SPOF.

**Question 15:** No. Paired regions do not automatically replicate apps, DBs, Key Vaults, or Private DNS. You must design app/data/routing/failover/DR separately.

**Question 21:** PITR recovers data from backups/logs to a point before a fault and usually requires restore/cutover. Failover groups/geo-replicas address regional availability/failover per feature and can incur replication lag. Both require application verification.

**Question 24:** Asynchronous geo-replication may not have finished transferring recent writes to the secondary; failover can lose data beyond RPO if lag/last sync is not monitored.

**Question 26:** Some Service Bus geo-DR mechanisms focus on **namespace metadata** and do not replicate message payloads. Other geo-replication mechanisms have their own support scopes. Check the tier/feature and use outbox/replay.

**Question 29:** Timeouts prevent unbounded waiting; retries re-attempt transient failures within a budget; jitter prevents request storms; circuit breakers fail fast when a dependency is broken; bulkheads isolate capacity so faults do not cascade.

**Question 32:** The DB may have committed while the HTTP response was lost; client retries create a new record unless an idempotency key/unique constraint is enforced.

**Question 33:** `30 × 30 = 900 potential connections`, which must be checked against the DB tier/limits and reconnect headroom.

**Question 41:** External payments already charged are not undone when the SQL DB is restored to an earlier timestamp. You must reconcile against the payment provider ledger to avoid double-charging.

**Question 43:** Record UTC timestamps for failure/detection/traffic and data restoration, inspect the last recoverable consistent transaction, and run business correctness checks. Measure RTO until the user SLI recovers, and measure RPO by data rather than backup job status alone.

### 26.3. Evaluation Rubric

| Criterion | Passing bar |
|---|---|
| Business requirements | Defines SLI/SLO/error budget/RTO/RPO with owners |
| Fault model | Distinguishes process/zone/region/data/config/common-mode |
| Architecture | Redundancy and simplicity aligned to targets |
| Azure choices | Zone/geo features verified by SKU/region, not guessed |
| Data correctness | Idempotency, outbox, backup/geo/PITR consistency |
| Resilience code | Timeouts/retries/circuit breakers/bulkheads/degraded modes |
| Operations | Monitoring, alerts, incident command, failback |
| Testing | Safe restore/game-day RTO/RPO evidence |
| FinOps | Cost-risk trade-offs without cutting critical recovery |

## 27. Pre-Production Reliability Readiness Checklist

### 27.1. Business Requirements

- [ ] **Critical user flows** are identified by revenue/data/compliance impact.
- [ ] SLIs specify numerator, denominator, latency definition, scope, and measurement window.
- [ ] SLOs have business owners and error budget/burn-rate policies.
- [ ] RTO/RPO match each flow and data state, not just individual resources.
- [ ] Azure service SLAs are evaluated by **SKU/configuration**, not treated as end-to-end SLAs.
- [ ] Secondary features have valid degraded modes and do not fail checkout.

### 27.2. Failure Modes and Architecture

- [ ] Dependency map covers identity, DNS, networking, CI/CD, external services, and people.
- [ ] FMEA records severity/detection/recovery owners and common-mode failures.
- [ ] No single-instance/single-zone SPOFs violate approved targets.
- [ ] Zone redundancy is verified by region/SKU/instance count.
- [ ] Multi-region topology/quotas/capacity are approved when regional RTO requires it.
- [ ] Front Door/Traffic Manager routing has proper health policies and tests.
- [ ] Write traffic is never routed to a secondary before an authoritative writer exists.
- [ ] Staging/prod, DR regions, and cloud dependencies do not share unbounded secrets or control scopes.

### 27.3. State and Data Integrity

- [ ] Azure SQL/PostgreSQL HA/backup/PITR/geo features are verified and tested.
- [ ] Azure Storage replication model, last sync, backup/versioning are reviewed.
- [ ] Cosmos DB consistency/conflict policies match data invariants.
- [ ] Service Bus/Event Hubs recovery scope (**message data vs. metadata**) is properly understood.
- [ ] Outbox/idempotency/duplicate handling protect order/payment flows.
- [ ] Redis/cache is not treated as an authoritative durable store where business rules forbid it.
- [ ] Secondary region keys/secrets/certificates/roles are operational.
- [ ] Backup protection/retention/immutable copies and restore tests have evidence.
- [ ] Database/schema rollouts and rollbacks are compatible with multi-version apps.

### 27.4. Runtime Resilience

- [ ] Multiple instances/replicas and headroom tolerate zone/host loss.
- [ ] Liveness, readiness, startup, and synthetic probes each serve distinct purposes.
- [ ] Timeouts/connect/query deadlines align with request SLOs.
- [ ] Transient error retries are bounded, use jitter, and respect `Retry-After` where applicable.
- [ ] Circuit breakers/bulkheads/admission control are tested against degraded dependencies.
- [ ] Autoscaling cannot exhaust SQL/Service Bus/Key Vault capacity.
- [ ] Graceful shutdown, draining, and in-flight request handling are defined.
- [ ] APIs/pipelines report pending/uncertain states honestly instead of false successes.

### 27.5. Security and Networking

- [ ] Least privilege applies to deployment/runtime/migration/DR identities, with break-glass controls.
- [ ] DR region has valid private networking, DNS, TLS, routing, and firewall rules.
- [ ] Secrets and tokens are absent from IaC source/JARs/images/logs.
- [ ] Key Vault and encryption key recovery are approved and respect data residency.
- [ ] Resource locks/backup access do not block authorized restores.
- [ ] Activity Log/diagnostic settings retain change configurations and audits per policy.

### 27.6. Operations and Monitoring

- [ ] User SLIs/synthetic checks run from multiple locations with burn-rate alerts.
- [ ] Database replication lag/connection failures/CPU/IO/locks and queue age/DLQ are monitored.
- [ ] On-call/incident commander, escalation, and communication templates exist.
- [ ] Runbooks contain **exact resource IDs, approvals, safe aborts, rollbacks**, and owners.
- [ ] DR recovery path is rehearsed with synthetic data / isolated restores.
- [ ] RTO/RPO measurements include detection, failover, rerouting, and business verification.
- [ ] A failback plan exists to prevent split-brain and divergence.
- [ ] CI/CD for IaC/DB migrations passes tests/canaries and limits blast radius.
- [ ] Postmortems produce corrective actions re-verified through drills.

### 27.7. Cost and Governance

- [ ] Replicas/regions/backups/monitoring costs are estimated by region/tier.
- [ ] DR standby has an owner and a cost-risk review cadence.
- [ ] Budget alerts are configured without auto-deleting production to cut costs.
- [ ] Backup/geo retention meets compliance and business state recovery needs.
- [ ] Architecture complexity does not exceed the team's operational capacity.
- [ ] ADRs/Well-Architected reviews are updated when business needs/SLOs change.

## 28. Lab Cleanup and Safe Operations

**Reliability drills often carry a large blast radius.** An accidental failover or delete command in production is not a minor lab mistake: it can cause data loss, trigger split-brain, halt serving, and initiate a compliance incident.

### 28.1. Operations Never to Perform on Your Own

- **Never** fail over production Azure SQL/PostgreSQL/Storage just to "test RTO."
- **Never** drop real databases/tables or purge outbox/queue messages.
- **Never** disable all Key Vault/Entra RBAC/network/DNS to simulate an outage.
- **Never** take down production zones by arbitrarily deleting NSGs/VMSS/AKS node pools.
- **Never** run `terraform destroy` or `az group delete` on a shared resource group.
- **Never** generate real payments, send real emails/SMS, or charge real cards during synthetic tests.
- **Never** grant subscription-wide Owner or delete logs/backup retention to troubleshoot permissions.
- **Never** shift production traffic to a DR region without data authority and approval.

### 28.2. Safe Cleanup Procedure

1. Confirm the exact **subscription, resource group, resource ID, environment, and owner**.
2. Distinguish lab-only resources from shared/production resources.
3. Save authorized metrics, drill logs, RTO/RPO evidence, and records requiring retention.
4. Wait for synthetic events/queues/outbox to drain and complete data reconciliation.
5. Revoke lab-only principals/network exceptions/secrets per IAM approval.
6. Delete **staging/restore test resources** only when no longer needed and backed up/retained appropriately.
7. Do not delete previous app revisions/images while still within the rollback window.
8. Verify Front Door/Traffic Manager routes and DB primary/replica topology after the drill.
9. Confirm the DR standby posture has returned to a ready state.
10. Review Cost Management to ensure no orphaned lab resources remain.
11. Document post-lab changes, owners, and security/availability status.

### 28.3. Illustrative Delete/Failover Commands Are Dangerous

~~~bash
# DANGER — COMMENTED EXAMPLES. DO NOT EXECUTE AS A LAB STEP.

# Deleting an entire resource group may delete production dependencies.
# az group delete --name "<some-resource-group>" --yes

# Storage account failover changes account replication/active region state.
# az storage account failover --name "<some-storage-account>" ...

# Database promotion/failover is a production change, not an observation.
# <database-specific failover command omitted intentionally>
~~~

**To prove restore capability**, use an **isolated database restore target**. To prove timeouts/circuit breakers, use a **mock dependency or lab network fault**. To prove traffic failover, use **staging endpoints/data** and pre-agreed abort conditions.

### 28.4. Lab Handover

| Item | Required evidence |
|---|---|
| Target scope | Correct subscription/RG/resource IDs |
| Business SLO | Definition and owner |
| Drill | Hypothesis, timestamps, expected vs. actual |
| RTO/RPO | Measured, with reconciliation plan if failed |
| Data | No unexpected lost/duplicated synthetic records |
| Runtime | App/queues/DB back to expected healthy topology |
| IAM/network | No remaining temporary broad permissions |
| Backups | Restore points and retention per policy |
| Monitoring | Alerts/metrics/diagnostic settings operational |
| Costs | Lab-only resources inventoried |
| Actions | Findings/corrective actions assigned to owners |

## 29. References and Summary

### 29.1. Documentation to Consult at Implementation Time

- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — pillars, design methodology, and workload reviews.
- [Reliability pillar](https://learn.microsoft.com/azure/well-architected/reliability/) — Reliability guidance on requirements, resilience, recovery, and operations.
- [Azure Architecture Center](https://learn.microsoft.com/azure/architecture/) — reference architectures and resilient design patterns.
- [Azure Availability Zones](https://learn.microsoft.com/azure/reliability/availability-zones-overview) — fault domains, zone support, and design.
- [Azure regions and geographies](https://learn.microsoft.com/azure/reliability/regions-overview) — regions, pairs, and region-selection considerations.
- [Azure SQL Database reliability](https://learn.microsoft.com/azure/azure-sql/database/high-availability-sla) — availability by service tier and limitations.
- [Azure SQL automated backups](https://learn.microsoft.com/azure/azure-sql/database/automated-backups-overview) — PITR, retention, and restore.
- [Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/azure/postgresql/flexible-server/overview) — HA, backups, and geo options.
- [Azure Storage redundancy](https://learn.microsoft.com/azure/storage/common/storage-redundancy) — LRS/ZRS/GRS/GZRS and data durability.
- [Azure Cosmos DB high availability](https://learn.microsoft.com/azure/cosmos-db/high-availability) — multi-region/consistency capabilities.
- [Azure Service Bus resilience and disaster recovery](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-geo-dr) — verify metadata DR/geo capabilities.
- [Azure Front Door](https://learn.microsoft.com/azure/frontdoor/) — global routing, health probes, and WAF.
- [Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/) — platform metrics, logs, alerts, and Application Insights.
- [Azure Service Health](https://learn.microsoft.com/azure/service-health/overview) — incidents and service advisories.
- [Azure Chaos Studio](https://learn.microsoft.com/azure/chaos-studio/) — controlled failure experiments for supported targets.
- [Azure Backup](https://learn.microsoft.com/azure/backup/) — backup policies and restores.
- [Azure Site Recovery](https://learn.microsoft.com/azure/site-recovery/) — workload/VM recovery in supported use cases.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — cost estimation by region/tier.

**Check for updates:** Azure service tiers, availability zones, regional replication, disaster recovery features, backup retention, failover mechanisms, API names, and SLAs can change by service, version, and region. Before deploying to production, verify current documentation, support matrices, and pricing; figures and architectures in this lesson are **learning assumptions**, not Microsoft guarantees or compliance advice for every organization.

### 29.2. Fourteen Core Takeaways

1. **Reliability is not uptime alone:** it requires preserving functionality and data correctness, tolerating faults, and recovering.
2. **Start from business flows**, not from buying three regions.
3. **SLI, SLO, and SLA are distinct**; error budgets only make sense with clear measurement definitions.
4. **RTO is time to restore functionality; RPO is the acceptable data-loss bound.**
5. **FMEA and common-mode analysis** must include networking, identity, data, external providers, and people.
6. **Availability Zones** mitigate certain intra-region faults when supported by SKU/region, not regional outages.
7. **Multi-region** requires traffic routing, database writer/replication, quotas, identity, secrets, and a DR runbook.
8. **HA does not replace backups; geo-replicas do not replace PITR** when data is deleted or corrupted.
9. **Azure SQL, PostgreSQL, Storage, Cosmos, and Service Bus have different recovery semantics**—never infer them from feature names.
10. **Retries must be bounded and idempotent**, coordinated with deadlines, jitter, circuit breakers, and bulkheads.
11. **Outbox/queues and reconciliation** are essential when an application spans DB transactions plus brokers/payment providers.
12. **Monitor user SLIs and business correctness**, not merely CPU, process health, or Azure Activity Log.
13. **Recovery only counts when rehearsed**: measure end-to-end RTO/RPO, validate data, and include failback.
14. **Keep architectures simple enough and cost-appropriate**, with clear owners, runbooks, approvals, and corrective actions.

### 29.3. Conclusion

Applying the **Reliability pillar of the Azure Well-Architected Framework** is not enabling an HA checkbox and calling the job done. A reliable workload requires **measurable business targets, fault and common-mode dependency analysis, right-sized redundancy from instance to zone/region, accurately recoverable data, fault-tolerant code, operators equipped with observability and runbooks, drills proving RTO/RPO, and continuously evaluated cost and security decisions**. Only when these elements have verified evidence and clear owners does reliability become a **provable operational capability**, rather than a promise on an architecture diagram.
