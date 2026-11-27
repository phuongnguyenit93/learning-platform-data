# Designing with Availability Zones and Handling Local Failures

## 1. The Problem: One Zone Fails, Yet the Application Keeps Serving

An application running smoothly on Azure can lose availability even while multiple virtual machines (VMs) remain up: the VMs sit in the same infrastructure zone, the load balancer forwards traffic to only one zone, or the database rests on a single point of failure. When an **Availability Zone (AZ)** loses connectivity or suffers power, networking, or cooling disruption, components sharing that dependency can become unavailable.

In the **Reliability and Disaster Recovery** chapter of the `CLOUD_PROVIDERS_AZURE` module, this lesson connects knowledge of **subscriptions, resource groups, Entra ID, virtual networks, compute, storage, data, monitoring, and cost** to a concrete operational requirement: **a local failure within a single zone must not bring down the entire application**.

Imagine an ordering system with an API, a queue, a database, and an admin portal. Placing three VMs across three zones is only a starting point. The system keeps processing orders only when ingress, business logic, data, access permissions, and critical dependencies all tolerate the loss of one zone.

After this lesson, you will be able to:

- Distinguish instance, zone, and region failures and the protection scope of each Azure construct.
- Choose **zonal resources** or **zone-redundant resources** appropriately without assuming every service supports them identically.
- Trace request paths and eliminate single points of failure across both application and data tiers.
- Size capacity to survive a single-zone failure, and design fault detection, traffic shifting, and recovery.
- Build hands-on scenarios to observe and test local failures without causing a real production outage.

## 2. What Is an Availability Zone?

An **Azure region** is a geographical area housing cloud infrastructure. In regions supporting Availability Zones, zones are groups of datacenters with physically separated power, cooling, and networking designed to reduce correlated local failures. Zones within a region connect over a low-latency network suited to distributed applications.

Conceptual example:

~~~text
Region: Southeast Asia (illustrative only; verify support per service)
  ├── Availability Zone 1 ── API instance / worker
  ├── Availability Zone 2 ── API instance / worker
  └── Availability Zone 3 ── API instance / worker
~~~

`1`, `2`, `3` are **logical zone labels** exposed by Azure to a subscription. Never assume zone `1` in two different subscriptions always maps to the same physical location. If resources across multiple subscriptions must align physically, check Azure's supported zone-mapping capabilities for that scenario.

**Not every region, VM type, or Azure service supports the same number of zones or the same redundancy modes.** Before designing, verify support for the exact region, service tier/SKU, and configuration. Even when a service offers zone redundancy, enabling it may require selecting a specific tier or option.

### 2.1. Distinguishing Failure Scopes

| Failure scope | Examples | Appropriate protection mechanism |
| --- | --- | --- |
| **Instance/process** | API crash, unresponsive VM, container restart | Multiple replicas, health probes, restarts, autoscaling |
| **Host/rack or local maintenance** | Physical host failure or host update | Multiple instances, spread placement/fault domains |
| **Availability Zone** | Power or network loss in one zone | Spread workloads across zones; zone-resilient ingress and data |
| **Region** | Wide-area outage affecting a region | Multi-region architecture, cross-region replication, failover, and DR plan |
| **Logical / shared fault** | Buggy deployment, deleted data, revoked credentials, bad DNS config | Rollback, backups, change controls, permission isolation, and testing |

A multi-zone architecture reduces risk from **zone-local faults**. It does not replace a multi-region architecture for region-wide outages, nor does it protect against software bugs or simultaneous operational errors.

### 2.2. Zonal, Zone-Redundant, and Non-Zonal

Distinguish these concepts when reading each service's documentation:

- **Zonal resource** is pinned to a specific zone, such as a VM deployed into zone `1`. That resource does not automatically move to another zone if zone `1` fails. Resilience comes from running replacement instances in other zones.
- **Zone-redundant resource** is engineered by the service to operate across multiple zones within a region, potentially including data replication or cross-zone request paths; failover behavior is **service-specific**.
- **Non-zonal / regional resource** offers no direct zone selection or declares no zone-redundancy guarantee for the chosen configuration. Never assume a resource is zone-resilient merely because its name includes a region.

**Rule of thumb:** Spreading VMs across zones does not mean every other component automatically gains zone availability. You must inspect the entire request path, from DNS/ingress down to data systems and dependencies.

## 3. Reliability Targets: SLI, SLO, RTO, and RPO

Before picking services, engineering must turn "must keep running when a zone fails" into verifiable targets.

| Term | Question to answer | Example for Orders API |
| --- | --- | --- |
| **SLI** (Service Level Indicator) | Which metric measures system health? | Request success rate; p95 latency of order placement |
| **SLO** (Service Level Objective) | What target should the SLI meet over a time window? | Minimum successful request ratio per internal objective |
| **RTO** (Recovery Time Objective) | How long can service be disrupted after an outage? | Ingress must recover within the business-approved duration |
| **RPO** (Recovery Point Objective) | How much written data loss is acceptable? | Zero loss of confirmed orders, if data architecture supports it |

Numbers must align with business needs and actual service capabilities. Never assume zone redundancy always delivers **zero RTO** or **zero RPO**. For example, data-service failover can cause brief disconnects requiring client reconnection; consistency and potential data loss depend on the service's replication mode.

Distinguish **high availability (HA)** from **disaster recovery (DR)**:

- HA typically limits the impact of common failures and zone outages automatically via replicas, health checks, redundancy, and failover.
- DR covers recovery from larger disasters: backups, data restoration, cross-region failover, role assignments, and runbooks.

This lesson focuses on HA during a **single-zone outage**; a full-region DR plan must still be designed separately.

## 4. Reference Architecture for a Three-Tier Application

Assume the ordering service deploys into an Azure region with three zones and that required SKUs support them.

~~~mermaid
flowchart TB
    U["Client / user app"] --> I["Zone-resilient entry point<br/>e.g., Standard Load Balancer + suitable frontend"]
    I --> H["Health probes / routing"]
    H --> A1["AZ 1<br/>API replicas + workers"]
    H --> A2["AZ 2<br/>API replicas + workers"]
    H --> A3["AZ 3<br/>API replicas + workers"]
    A1 --> D["Data service supporting zone redundancy<br/>with configuration properly enabled"]
    A2 --> D
    A3 --> D
    A1 --> Q["Queue / cache verified for zone availability"]
    A2 --> Q
    A3 --> Q
    M["Azure Monitor + Application Insights<br/>alerts and multi-location checks"] -.-> I
    M -.-> A1
    M -.-> A2
    M -.-> A3
    M -.-> D
~~~

This diagram shows each layer's **role** and does not promise every listed service shares the exact same zone deployment mechanics. When implementing, select exact products and SKUs that satisfy your requirements.

### 4.1. Entry Points Must Keep Receiving and Routing Traffic

One option for regional VM workloads is **Azure Standard Load Balancer** with an appropriately configured zone-resilient frontend public IP (where the region supports it). The backend pool spans instances across multiple zones; health probes stop sending traffic to unhealthy backends.

If using **Application Gateway v2** or another ingress service, verify that service's own zone-redundancy support and settings. A zone-resilient frontend solves only **the entry point**; if all backends sit in one zone, the application still goes down when that zone fails.

Note: **Azure Front Door** handles global routing and is especially useful for multi-region architectures; it does not replace distributing workloads and data across zones within a region.

### 4.2. The Compute Tier Should Be Stateless and Distributed

Run multiple independent replicas across zones, such as:

- **Virtual Machines or Virtual Machine Scale Sets (VMSS)** deployed/distributed across available zones, with scaling and placement rules verified for the orchestration model in use.
- **Azure Kubernetes Service (AKS)** with zone-spread node pools and workload replicas; consider `topologySpreadConstraints` and `PodDisruptionBudget` to reduce the chance of all pods landing in one zone.
- **Azure-managed application services** with zone-redundancy options (if supported in the selected region/tier).

Stateless APIs minimize reliance on local disks or per-instance in-memory sessions. Data such as sessions, user state, and long-running workflow state should live in fault-tolerant stores accessible across replicas.

Do not merely count "three replicas"—verify **where they actually run** and whether the orchestrator can pack them onto a single zone.

### 4.3. The Data Tier Must Tolerate a Zone Failure

The approach depends on data type and service:

| Need | Design direction | What to verify |
| --- | --- | --- |
| Blob/storage account | Choose **ZRS** or **GZRS** when SKU, region, and requirements allow | Service/data-type support; cost; failover semantics |
| Relational database | Choose a **zone-redundant high availability** tier/config when Azure SQL or equivalent supports it | Replica model, failover, expected RPO/RTO, reconnection |
| Data running on VMs | Design cross-zone replication/clustering yourself; check Managed Disk types and ZRS support | A single disk attached to a VM does not turn a workload into a cluster |
| Queues, caches, brokers | Choose tiers/deployments supporting zone availability; protect state and reprocessing | Actual config, message ordering, duplicates, failover |
| Shared secrets/configuration | Use identity, secret, and configuration services with suitable reliability | Entra ID access, DNS, Private Endpoints, quotas, network rules |

**ZRS (Zone-Redundant Storage)** replicates data synchronously across zones within a supported region per Azure Storage's model; **GZRS** adds cross-region replication per service behavior. Choosing **LRS**, **ZRS**, **GRS**, or **GZRS** involves fault-domain scope, access patterns, and cost; never treat them as direct drop-in swaps.

For databases, "having multiple copies" is not enough: understand how many replicas can be lost, quorum, leader election, acknowledged-write semantics, and client behavior during failover. For self-managed clusters, place voting members in independent zones and verify losing one zone preserves **quorum** to prevent split-brain.

### 4.4. Hidden Dependencies Can Still Be Single Points of Failure

Trace a request's real path: DNS → ingress → API → identity/tokens → database → queue → worker → storage → response. Also inspect **outbound connectivity**, NAT, private networking/Private Endpoints, DNS resolution, certificates, Entra ID, Key Vault, and shared services.

For instance, if the API runs in all three zones while the worker runs only in zone `1`, order placement might return HTTP 202 and never finish processing. Or the API stays up while a single cache instance fails and causes every request to time out. Single points of failure frequently hide in **dependencies and state**, not only compute placement.

## 5. Sizing Capacity to Survive a Single-Zone Failure

A three-zone architecture can still lack enough capacity after losing one zone. Capacity must be sized against **actual peak load** and the surviving resources.

Assume design peak load is **900 requests/second (RPS)**. Replicas are spread evenly across three zones; each zone is benchmarked to handle **600 RPS** safely within target latency.

| State | Serving zones | Total safe capacity | Compared to 900 RPS peak |
| --- | --- | ---: | --- |
| Normal | 1, 2, 3 | 1,800 RPS | Sufficient, with reserve |
| Zone 2 fails | 1, 3 | 1,200 RPS | Sufficient, 300 RPS margin |
| Zones 1 and 2 fail together | 3 | 600 RPS | Insufficient for peak load |

Verification rule for surviving **any single zone** failure:

~~~text
For each zone z:
  SUM(safe_capacity_of_remaining_zones) >= peak_request_load × headroom_factor

If all 3 zones have equal capacity C:
  2 × C >= peak_request_load × headroom_factor
~~~

For example, if the headroom factor is `1.2`, losing one zone must leave at least `900 × 1.2 = 1,080 RPS`. Two remaining zones provide `1,200 RPS`, clearing the threshold under the benchmark assumptions. This is an illustrative capacity calculation, **not an Azure performance guarantee**.

Also account for:

1. **Shared bottlenecks:** Can the database, queue, NAT/outbound ports, connection pools, and storage throughput handle all load shifting to the remaining zones?
2. **Quotas and stock:** Does Azure have enough vCPU quota, resource limits, and VM allocation capacity in the surviving zones?
3. **Scale-out lag:** Autoscaling takes time; keep **pre-warmed headroom** when RTO cannot wait for new replicas.
4. **Load distribution:** Do health probes and load-balancing algorithms actually steer requests to healthy zones? Does session affinity skew traffic?
5. **Incident load spikes:** Does load increase when clients retry or when backlogs drain?

## 6. Two Bicep Patterns: Zonal and Zone-Redundant

In IaC, distinguish declaring **placement into a specific zone** from declaring **a service that manages redundancy across multiple zones**. The example below deploys only one public IP and one storage account to illustrate syntax; it is **not a complete HA architecture**, as it creates no backend, load balancer, or database.

**Assumptions:** The target region supports zones `1`, `2`, `3` for Standard public IPs and supports Storage ZRS with the chosen SKU; the storage account name is globally unique across Azure and meets naming rules.

~~~bicep
targetScope = 'resourceGroup'

param location string = resourceGroup().location

@description('Globally unique Azure storage account name, lowercase letters and digits.')
@minLength(3)
@maxLength(24)
param storageAccountName string

// Standard Public IP configured across multiple zones.
// Availability depends on region and SKU.
resource ingressPublicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-orders-zr'
  location: location
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  zones: [
    '1'
    '2'
    '3'
  ]
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

// For Azure Storage, redundancy is selected via the SKU.
// Do not add zones: ['1', '2', '3'] to a Storage Account.
resource ordersStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_ZRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

output ingressPublicIpId string = ingressPublicIp.id
output storageAccountId string = ordersStorage.id
~~~

Key points:

- `zones: ['1', '2', '3']` on a supported public IP creates a zone-redundant frontend config; that **alone** does not guarantee healthy backends.
- The storage account uses `sku.name: 'Standard_ZRS'` to instruct Azure Storage to store data under the ZRS model where supported. ZRS is a service capability, not three user-managed VMs.
- When creating a **zonal VM**, use the `zones` property on the VM resource itself or zone settings on VMSS/AKS per service docs; real deployments still need networking/OS/disks and replication.
- Run **what-if**, and confirm SKUs, locations, quotas, and policies before deploying. Successful Bicep compilation does not prove every zone is available in the chosen region.

**Deployment takeaway:** For many PaaS services, zone redundancy is not configured via a resource `zones` property, but via tier, SKU, or service-specific properties. Always read the resource provider specification instead of copying VM syntax to storage or databases.

### 6.1. Verifying Placement After Deployment

For VMs and existing resources, inspect `zones` via Azure CLI:

~~~bash
az account show --query "{subscription:id,tenant:tenantId}" -o json

az vm show \
  --resource-group rg-orders \
  --name vm-orders-z1 \
  --query "{name:name,location:location,zones:zones}" -o json

az network public-ip show \
  --resource-group rg-orders \
  --name pip-orders-zr \
  --query "{name:name,sku:sku.name,zones:zones}" -o json

az storage account show \
  --resource-group rg-orders \
  --name storderssample001 \
  --query "{name:name,location:location,sku:sku.name}" -o json
~~~

Resource group, VM, and storage account names here are examples; `show` commands succeed when the resources exist and the identity has read access. For many PaaS resources, inspect the **actual HA setting** in service-specific properties; an absent `zones` field does not by itself prove the lack of zone redundancy.

**Networking note:** A resource group is not a private network or availability boundary. Subnets in one VNet can serve workloads spanning multiple zones within the same region; security architecture—NSGs, routes, firewalls, Private DNS, and Private Endpoints—must be reviewed holistically.

## 7. Detecting Failures and Isolating an Unhealthy Zone

**Proper failover** requires distinguishing an instance fault from a zone fault and removing **only genuinely unhealthy backends** from the request path.

### 7.1. Health Probes and Readiness

Distinguish three checks:

| Check | What it verifies | Purpose |
| --- | --- | --- |
| **Liveness** | Is the process running and free of deadlocks? | Restarts the process/container when unhealthy |
| **Readiness** | Can this instance currently serve service requests? | Controls whether load balancer/ingress sends traffic |
| **Synthetic end-to-end** | Does an external sample transaction succeed? | Catches path or dependency faults missed by local probes |

For example, `/ready` might return `200` only after initialization finishes, requests can be processed, and the instance is not draining. `/live` checks process health. Avoid turning either into deep queries against every external service on every probe: a brief hiccup in a shared dependency could cause **every instance to be evicted simultaneously**, amplifying the incident.

With Azure Load Balancer, appropriate probes determine which backends stay in rotation. Choose check intervals, failure thresholds, and existing-connection behavior per service; **never assume instantaneous failover**.

### 7.2. Typical Fault-Handling Flow

~~~mermaid
sequenceDiagram
    participant U as Client
    participant LB as Ingress / Load Balancer
    participant Z2 as API AZ 2
    participant Z1 as API AZ 1
    participant DB as Database HA
    U->>LB: POST /orders
    LB->>Z2: Forward request
    Note over Z2: AZ 2 stops responding
    Z2--xLB: Timeout / missed health probe
    LB->>Z1: New request routed to healthy backend
    Z1->>DB: Write order
    DB-->>Z1: Result / acknowledgment
    Z1-->>U: Response
    Note over U,Z1: In-flight request may fail; client needs safe retry
~~~

Connections or in-flight requests in AZ 2 may fail; traffic shifting only guides **new requests** to healthy backends. Therefore, clients and applications need proper error handling, timeouts, and retries.

### 7.3. Retries, Timeouts, Idempotency, and Circuit Breakers

If all clients retry infinitely at once, a zone outage can trigger a **retry storm** that overwhelms the remaining two zones. Software must:

- Enforce **bounded timeouts** for network, database, and API calls, tracking a budget across the full request chain.
- Use bounded retries with **exponential backoff and jitter**, only for recoverable transient errors.
- Use an **idempotency key** or uniqueness constraint for critical writes. If an order request times out after the database committed, retries must return the same outcome or handle duplicates safely.
- Apply **circuit breakers** when a dependency fails persistently to avoid exhausting connection pools and threads.
- Implement backpressure, queue depth limits, load shedding, or degraded modes when remaining capacity falls short.
- For asynchronous work, account for **at-least-once processing**, duplicates, and out-of-order delivery depending on the queue service; workers must handle them safely.

Faults must be isolated by tier: losing one zone should not cascade due to hung connections, aggressive retries, or a local cache turning into a hard dependency.

## 8. Stateful Data: Harder Than Load Balancing

Stateless API instances are relatively easy to replace; **stateful workloads** need dedicated planning.

**Scenario A — Azure-managed database:** Select zone-aware HA options supported by the service and tier, and verify automatic vs. manual failover, role-switch latency, dropped connections, and post-failover throughput limits. Applications need connection retries, timeouts, pool recovery, and idempotent transactions. Never assume exact RPO/RTO without checking documentation and testing the specific tier.

**Scenario B — Self-managed cluster:** Suppose three voting nodes exist, one per zone, with a quorum of two. If one zone goes down, the two healthy nodes can retain quorum—but **only if** consensus, placement, and storage access are configured properly. If two nodes accidentally land in the same zone, losing that zone strips quorum.

**Scenario C — Object storage:** ZRS mitigates local faults per Azure Storage's model, yet cannot undo user object deletions or application overwrites. Add versioning, soft delete, backups, or retention policies based on logical recovery and compliance needs.

Never equate **replication** with **backups**. Replication usually propagates unwanted changes too; backups/restores recover from logical corruption and must be tested for restorability. Likewise, intra-region zone redundancy is insufficient for full-region outage plans.

## 9. Runbook: Responding When AZ 2 Loses Availability

Assume the Section 4 system spans three zones, all requests pass through probe-backed ingress, and surviving zones hold reserve capacity.

| Stage | Signals / actions | Pass criteria |
| --- | --- | --- |
| **Detect** | AZ 2 probes fail; 5xx rate, timeouts, or latency spike | Alerts fire from end-to-end SLIs and backend signals |
| **Scope** | Compare backend health by zone, data state, and Azure Service Health | Confirm blast radius instead of assuming the whole region is down |
| **Isolate** | Ingress stops sending **new** requests to unhealthy AZ 2 backends; workloads drop readiness if needed | No new requests reach faulty backends after convergence |
| **Maintain service** | AZ 1 and AZ 3 absorb traffic; check DB, queue, cache, and headroom | Ordering stays within SLO; error rate drops |
| **Stabilize** | Bound retries, scale cautiously, prioritize critical business paths | No retry storm or unbounded backlog |
| **Recover** | Wait for Azure/service zone recovery; verify data sync, readiness, and new instances | Backends rejoin the pool gradually without sudden load spikes |
| **Postmortem** | Record timeline, actual RTO/RPO, bottlenecks, preventive actions | Metrics, owners, and verifiable changes captured |

During an incident, avoid repeatedly provisioning resources into the failing zone if doing so only produces errors and wastes quota. When the zone recovers, verify **reconciliation and rebalancing**: are instances/data back in desired state, placed across proper zones, and free of load skew?

### 9.1. When Is Failover Manual?

Depending on the service, zone failover may be automatic. For self-managed or stateful components, promoting a leader, removing a node, or switching endpoints may require an approved manual procedure. Runbooks must clearly state **authority, trigger conditions, verification steps, and rollback**; avoid blind automation that could cause split-brain or data loss.

## 10. Monitoring and Rehearsing Local Failures

A system proves zone resilience only when real impact can be observed. Use **Azure Monitor, Application Insights, Log Analytics, metric/log alerts, Availability Tests, and Service Health** as supported by each service.

Monitor at minimum:

- **User experience:** success rate, p95/p99 latency, timeouts, and incomplete transactions.
- **Ingress:** health probe status, healthy backend counts, cross-zone distribution, and 4xx/5xx breakdown by tier.
- **Compute:** healthy replicas per zone, CPU/memory, request queues, connection pools, CPU throttling, and scale-out duration.
- **Data:** leader/replica state, failover events, commit latency, failed connections, replication lag (if any), and backlog.
- **Platform:** Service Health events, limits/quotas, DNS/Private Endpoints/routing, and configuration change alerts.

Drills should start in test environments with progressive scope:

1. **Terminate one instance**: verify the load balancer stops routing to the failed backend and recovers once ready.
2. **Simulate losing all backends in one zone**: drain/disable that zone's replicas in a controlled environment while other zones run. No real power or network destruction needed.
3. **Ramp load to design peak** with one zone isolated: compare calculated capacity against actual throughput, latency, and stability.
4. **Rehearse stateful failover** using the data service's supported mechanism; verify writes, transaction idempotency, reconnects, and backlog.
5. **Restore the zone**: reintroduce replicas gradually, verify data consistency, rebalancing, and alert clearance.

Before every drill, establish an owner, schedule, abort criteria, environment scope, and recovery plan. For production, proceed only under organization-approved change management. Fault testing must preserve observability and never mask lost transactions or corrupt data.

### 10.1. Drill Acceptance Criteria

Example for the ordering system:

~~~text
Given:
  - 3 zones have healthy backends; remaining zones hold sufficient capacity.
  - Load is held at 900 RPS during the benchmark.
When:
  - All backends in AZ 2 are marked unhealthy.
Then:
  - Ingress shifts new requests to AZ 1 and AZ 3 based on probes.
  - Success rate and p95 latency return within agreed SLOs.
  - Zero duplicate orders from retries; zero lost confirmed orders.
  - Queue backlog drains within the defined threshold.
  - Logs, metrics, and timelines exist to measure actual RTO/RPO.
~~~

Acceptance uses **team-defined** SLO/RTO/RPO thresholds rather than assuming fixed values across all Azure services.

## 11. Cost, Performance, and Operations

Zone-resilient design improves availability while carrying operational costs:

| Factor | Impact | How to control |
| --- | --- | --- |
| **Reserve replicas/capacity** | Must keep enough remaining capacity after losing one zone | Size N-1 capacity, benchmark, combine autoscale with minimum baseline |
| **Storage/data replication** | ZRS/zone-redundant SKUs can cost more depending on service | Pick redundancy per RPO/RTO and data classification |
| **Cross-zone traffic** | May incur data-transfer charges and slight latency | Measure real flows; consider locality without pinning the app to one zone |
| **Multi-zone governance** | More placement rules, health probes, alerts, and runbooks | Standardize IaC, per-environment configs, and periodic drills |
| **Configuration drift risk** | One zone missing permissions, DNS/routes, or right release | Keep images/configs uniform, enforce change control, run post-deploy checks |

Avoid cutting costs by stripping capacity in two zones during low traffic and assuming autoscale will save you instantly during an outage. Allocation limits, startup duration, and warm-up time all impact RTO. Appropriate headroom balances SLO requirements against outage costs.

Azure RBAC and Microsoft Entra ID also factor into operations: automation identities need permissions across all target zones/scopes while upholding **least privilege** to reduce operator mistakes and security risk.

## 12. Hands-On Exercise: Redesigning a Single-Zone Application

**Context:** `orders-api` currently runs two VMs both in AZ 1 behind Standard Load Balancer, with a database on a standalone VM and a storage account with unverified redundancy. Users must be able to place orders even when AZ 1 becomes unavailable.

**Requirement:** Design the system to survive the loss of any **single** zone in the region at 900 RPS peak load, with a way to measure RTO/RPO.

### Step 1: Map Dependencies and Flag Single Points of Failure

Document the path:

~~~text
Client -> Ingress -> orders-api -> Database
                              -> Queue -> Worker
                              -> Storage
                              -> Auth / Secret / DNS
~~~

For each component, list service/tier/SKU, deployment region, zone placement, health-check method, stateful data, and recovery mechanism.

### Step 2: Choose a Zone Model

Spread `orders-api` and worker replicas across multiple zones, configure resilient ingress/frontends, distribute backends, and add readiness probes. For data, evaluate whether a zone-redundant PaaS service or a self-managed cluster with cross-zone replication/quorum fits; verify availability and tiers in the exact region.

### Step 3: Verify N-1 Capacity

Using benchmark numbers, assume each zone handles 600 RPS within latency targets. Recalculate as each zone fails in turn; inspect database throughput, queue processing rates, and retries. If only two zones are supported for a chosen service, recalculate capacity/architecture for the actual region rather than blindly applying a three-zone formula.

### Step 4: Write a Failure-Injection Scenario

Draft a runbook for all backends in one zone becoming unhealthy. Define SLIs, alert thresholds, load-balancer eviction criteria, retry rules, data verification, recovery steps, and rollback criteria.

### Step 5: Report Findings

Deliver the dependency diagram, per-layer placement and redundancy table, N-1 calculations, drill logs/metrics, measured RTO/RPO, and remaining single points of failure. If any service lacks zone-redundancy support at the chosen tier, state the residual risk and mitigation plan clearly.

**Self-assessment rubric:**

| Question | Passing condition |
| --- | --- |
| If AZ 1 fails, is ingress still up? | Frontend and remaining backends keep accepting requests |
| Are VMs/pods distributed? | Actual placement shows replicas across multiple zones |
| Is capacity enough after losing one zone? | N-1 capacity meets peak load plus defined headroom |
| Can the database still commit writes? | Failover/quorum and write tests confirm success |
| Can clients retry safely? | Bounded timeouts/backoff; critical writes are idempotent |
| Is there RTO/RPO and fault-observability evidence? | Dashboards, logs, drill execution, and target comparison |
| What if the whole region fails? | Separate DR/multi-region/backup plan exists, not confused with zone redundancy |

## 13. Misconceptions to Avoid

**"Three VMs in three zones are enough."** Not enough: ingress, databases, queues, caches, DNS, outbound paths, and shared dependencies can still be single points of failure.

**"Zone redundancy means data is never lost."** False across layers and fault types. Replication mode, consistency, failover, and backups govern recoverability; accidental deletes and logic bugs can replicate too.

**"Autoscaling will spin up new capacity in time."** Never stake all fault tolerance on post-failure scaling. Quotas, VM stock, startup time, and warm-up can push RTO past targets.

**"A green health probe means business transactions succeed."** A process can return HTTP 200 while failing to write data. Combine readiness, synthetic transactions, and user SLIs.

**"Losing a zone equals losing a region."** A zone fault has a narrower scope than a regional outage. Isolate and handle at the right scope; use multi-region when regional fault tolerance is required.

**"Zone 1 is always the same physical location across subscriptions."** Logical zone labels can map differently; verify when cross-subscription physical colocation or separation matters.

## 14. Summary of Applied Knowledge

Designing for Availability Zones means engineering the **entire serving path** so any single zone can go down while the system still meets business objectives. Distribute compute, ensure frontends and data dependencies have zone-resilient configurations, size N-1 capacity, implement health probes and safe retries, and prove the outcome through observability and drills.

In the Azure ecosystem, region selection, subscriptions, resource groups, Entra ID/RBAC, VNets, compute, storage, databases, and monitoring must be treated as **one unified architecture**. A Bicep snippet or a zone-redundancy toggle on a single resource only delivers value when the rest of the system also behaves properly during a local failure.
