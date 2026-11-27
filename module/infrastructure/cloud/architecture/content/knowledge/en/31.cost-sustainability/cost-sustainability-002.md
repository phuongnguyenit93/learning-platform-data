# Resource, Request, Storage, Replica, and Data Transfer Costs

A cloud architecture can meet latency, availability, and security targets and still blow past its budget if the team only looks at server prices. Real costs also come from request counts, storage capacity and classes, backups/snapshots, replicas, caches, logs, network egress, cross-zone/cross-region transfers, and indirectly invoked services. As traffic grows, a design that seemed cheap at prototype scale can incur costs faster than the revenue or value the workload generates.

Evaluating architectural costs must start from the workload and data flow. **Compute cost** depends on resource type, runtime duration, and utilization. **Request cost** may be billed per API call, object operation, query, or message. **Storage cost** depends on capacity, class, retention duration, and read/write operations. **Replica cost** covers redundant resources, data copies, and recoverability. **Data transfer cost** arises when data moves across zones, regions, providers, the internet, or other services.

This lesson belongs to the **Cost and Sustainability** chapter of the **CLOUD_ARCHITECTURE** module. Its goal is to analyze cost drivers, build unit economics, allocate costs by workload/tenant, evaluate replication and data transfer trade-offs, control budgets, and optimize resource usage while still meeting SLOs, security, and resilience following Well-Architected principles.

## 1. Looking at Cost by Workload Flow

Do not estimate merely by adding up VM or container prices. A search request on the Booking API may:
1. Pass through DNS, CDN, WAF, load balancer, and API gateway.
2. Execute on application compute.
3. Read cache or query the database.
4. Fetch images/metadata from object storage or CDN.
5. Call an external recommendation or payment service.
6. Emit events to a queue and write logs, traces, and metrics.
7. Transfer data across zones or regions.

Each step can generate a different billing unit. A single HTTP request can trigger multiple database queries, cache operations, log events, and network transfers.

~~~mermaid
flowchart LR
    U["User request"] --> EDGE["CDN / WAF / Gateway"]
    EDGE --> APP["Application compute"]
    APP --> CACHE["Cache"]
    APP --> DB[("Database")]
    APP --> OBJ[("Object storage")]
    APP --> Q[("Queue / events")]
    APP --> EXT["External API"]
    EDGE -.-> NET["Data transfer"]
    APP -.-> OBS["Logs / metrics / traces"]
    DB -.-> REP["Replica / backup"]
    OBJ -.-> REP
~~~

A cost model must determine:
- Which workload generates the cost?
- Is the unit of measurement a request, transaction, user, tenant, GB, GB-month, compute-hour, or job?
- Which resources run continuously, and which run on demand?
- Where is data created, read, replicated, transferred, and deleted?
- Which components scale linearly with traffic, and which have step thresholds/quotas?
- Which costs belong to shared platforms and need driver-based allocation?

## 2. Main Cloud Cost Categories

| Category | Common Billing Units | Examples |
|---|---|---|
| Compute | vCPU-hour, instance-hour, GPU-hour, memory/time | VM, container, serverless execution |
| Request/operation | number of requests, operations, API calls | Object GET/PUT, queue request, database operation |
| Storage | GB-month, IOPS, throughput, requests | Block volume, object storage, database storage |
| Database | instance-hour, vCPU, capacity unit, storage, backup | Managed relational/NoSQL |
| Replica/HA | compute + storage + replication | Read replica, standby DB, multi-zone |
| Backup/snapshot | GB-month, snapshot delta, restore operations | Database backup, volume snapshot |
| Network transfer | GB, route, endpoint-hour | Internet egress, cross-zone/region, NAT |
| Observability | ingest GB, indexed GB, retained GB, query compute | Logs, traces, metrics |
| Managed services | requests, throughput, provisioned capacity | API gateway, CDN, WAF, stream |
| Support/license | subscription, support tier, feature | Enterprise support, commercial runtime |

Specific metric names and billing rules depend on the provider, service, region, pricing tier, and contract. A cost model should reference the provider's current price sheet or pricing calculator; never hard-code unit prices into a design document without recording the date and source.

### 2.1. Fixed, Variable, and Step Costs

- **Fixed-like cost:** baseline compute or managed service capacity running continuously even during low traffic.
- **Variable cost:** requests, data transfer, storage growth, or executions that scale with workload.
- **Step cost:** crossing a threshold requires adding a node, shard, throughput tier, or license.
- **Commitment cost:** upfront or reserved spend/capacity commitments that can lower unit prices but increase the risk of paying for unused capacity.
- **Operational cost:** on-call staffing, administration, backup/restore testing, and incident response; these may not appear as a line item on the cloud bill, yet remain architectural costs.

An architecture optimized for unit price is not necessarily optimized for total cost. For example, an instance with a lower hourly rate that requires more instances and more network transfer can end up more expensive than a larger instance type.

## 3. Compute Cost: How Long Machines Run and How Efficiently They Are Used

Compute typically includes VMs, container nodes, serverless executions, batch workers, GPUs, and managed runtimes.

### 3.1. Influencing Factors

- Number of instances/replicas and vCPU/RAM/GPU sizing.
- Runtime duration and idle time.
- Autoscaling min/max, warm pools, and cold starts.
- Multi-AZ/multi-region topology.
- CPU/memory utilization and workload profile.
- Runtime licenses, OS licenses, and support.
- Disk/network attached to instances.
- Pricing by region, architecture, and pricing model.

Simplified:

\[
Compute\ Cost \approx \sum_i (InstanceHours_i \times Rate_i)
\]

For serverless, replace instance-hours with invocation counts, execution duration, and memory/CPU allocation according to how the service bills.

### 3.2. Right-Sizing

Right-sizing selects a configuration sufficient to meet SLOs and headroom at reasonable cost. Measure:
- CPU and memory across percentiles/peak load.
- Queueing time and concurrency.
- I/O wait and network throughput.
- Request latency p95/p99.
- Autoscaling events and idle time.
- Capacity when a node or zone is lost.

Do not shrink instance size solely because average CPU is low. The system may need burst headroom or be bottlenecked on network/I/O. Do not upsize solely because CPU is high if the code can be profiled/optimized or traffic can scale out.

### 3.3. Scale-to-Zero, Scheduling, and Commitments

Dev/test, batch, or internal tool workloads can be shut down after hours or scaled to zero. Latency-sensitive production workloads usually need a baseline to avoid cold starts. Reserved/committed capacity or savings plans can lower effective prices when demand is steady, but require utilization forecasting and understanding of scope, term, payment options, and flexibility.

A practical approach is to segment workloads:
- Steady baseline: evaluate commitments once data is available.
- Variable traffic: autoscaling and on-demand capacity.
- Interruptible batch: consider spot/preemptible capacity if checkpointing/retries are safe.
- Dev/test: schedule shutdowns and automated cleanup.
- Burst: maintain quota/headroom or use queueing/load shedding.

## 4. Request Cost: Every Small Operation Adds Up

Managed services frequently bill per request/operation or processing unit. Examples:
- Object storage GET/PUT/LIST.
- API gateway requests.
- Queue publish/receive/delete.
- Stream ingestion/reads.
- Serverless invocations.
- CDN requests.
- Database read/write capacity or queries.
- KMS API calls in certain models.

If a single business request triggers 20 storage operations and 5 service API calls, the cost per user action can be much larger than expected.

### 4.1. Request Amplification

Request amplification occurs when one incoming request generates many downstream operations:
- Retries on timeout.
- Fan-out to multiple services.
- Excessive polling.
- N+1 database queries.
- Repeated object LIST calls.
- Over-emitting log/trace spans and events.
- Cache misses causing repeated origin reads.

Track downstream operations per transaction and retry rates. Backoff, batching, pagination, connection reuse, proper caching, and event coalescing can cut call counts.

### 4.2. Cost Amplification Example

An API receives 1 million requests/day. On average, each request triggers:
- 1 API gateway request.
- 4 database queries.
- 2 cache operations.
- 1 object metadata request.
- 3 log events.

Total operations are 1M, 4M, 2M, 1M, and 3M, respectively. This is not yet a currency conversion, as each service has different unit prices and billing units. However, measuring this makes clear why counting inbound requests alone is insufficient.

### 4.3. Be Careful with Retries

Retries can improve reliability, but when a dependency slows down, synchronized retries can multiply load and cost. Implement:
- Retry budgets and maximum attempt caps.
- Exponential backoff with jitter.
- End-to-end deadline-aware timeouts.
- Idempotency for operations with side effects.
- Circuit breakers/load shedding.
- Separate tracking of original requests versus downstream attempts.

## 5. Storage Cost: Capacity, Class, and Data Lifecycle

Storage cost is not only the capacity currently occupied. Depending on the service, it also includes tier, request count, retrieval, replication, backup, minimum retention, early deletion fees, or data processing.

### 5.1. Classifying Data by Access Pattern

| Data Group | Access Pattern | Storage Direction to Consider |
|---|---|---|
| Hot transactional database | Frequent reads/writes, low latency | High-performance block/database storage |
| Public images and assets | Read-heavy, rarely modified | Object storage + CDN |
| Recent logs/telemetry | Continuous writes, fast search | Hot observability/search tier |
| Old logs/archives | Rarely accessed, long retention | Cold/archive object tier |
| Backups | Scheduled writes, restored during incidents | Separate backup tier |
| Temporary uploaded files | Short lifecycle, deletable | Temporary object lifecycle |
| Data lake | Large datasets, batch queries | Object storage, compressed/columnar formats |

Choose storage classes based on read frequency, acceptable retrieval time, durability, availability, minimum storage duration, and retrieval charges. The cheapest tier can become expensive if data must be read back frequently or restored urgently.

### 5.2. Storage Growth

Forecast storage:

\[
Future\ Storage \approx Current\ Data + (Daily\ Growth \times Retention\ Days)
\]

This is a preliminary model that must be adjusted for compression, compaction, indexes, replicas, versioning, tombstones, metadata, and backups. For databases, indexes and WAL/logs can add substantial overhead compared to business record size.

### 5.3. Retention and Lifecycle

Design lifecycles:
- Delete temporary data once workflows finish.
- Transition logs/telemetry to cheaper tiers as query frequency drops.
- Retain backups per policy and legal holds.
- Expire old object versions according to retention rules.
- Compact or partition databases/logs.
- Expire cache entries with appropriate TTLs.
- Audit orphan objects and incomplete multipart uploads.

Do not shorten retention merely to reduce bills if legal, investigative, or recovery requirements exist. Data owners and legal/privacy teams must approve appropriate policies.

### 5.4. Compression, Format, and Small Files

Compression lowers storage and transfer costs but consumes CPU to compress/decompress. Columnar file formats and partition pruning can cut the volume of data scanned in analytics queries. Too many small files increase request/listing/metadata overhead and degrade query efficiency; batching/compaction can help.

Evaluate by total cost: storage + requests + retrieval + compute + network, not GB-month alone.

## 6. Replica Cost: HA and Read Scaling Both Have a Price

Replicas are copies of compute, data, or services used to increase availability, throughput, or recoverability. Every replica can incur both direct and indirect costs.

Types include:
- Application replicas/pods/VMs.
- Database read replicas or standbys.
- Multi-AZ synchronous replicas.
- Cross-region asynchronous replicas.
- Cache cluster replicas.
- Object replication/version copies.
- Search/index replicas/shards.
- Queue/stream replication or cross-region mirrors.
- Backup/snapshot copies.

### 6.1. Replicas Cost More Than Storage Alone

Total cost may include:
- Continuously or minimally running standby compute.
- Replica storage.
- Replication logs/throughput.
- Cross-zone/cross-region data transfer.
- Snapshots/backups and retention.
- Monitoring and licensing.
- Headroom capacity for failover.
- Testing, operations, and reconciliation.

### 6.2. Active-Active, Active-Passive, and Warm Standby

| Topology | Cost Profile | Benefits | Trade-offs |
|---|---|---|---|
| Active-active | Multiple regions run serving capacity concurrently | Geographic latency, compute used across regions | Replication, consistency, routing, and coordination |
| Hot active-passive | Standby maintains full or near-full capacity | Short RTO, faster cutover | High idle capacity |
| Warm standby | Backup region runs scaled down | Balances cost and RTO | Requires scale-up and warm-up during failover |
| Pilot light | Only minimal components stay always ready | Generally lower cost | Longer RTO, provisioning during incidents |
| Backup/restore | Pays primarily for backups/storage | Low normal-state cost | Long RTO and requires restore testing |

Do not cut replicas based solely on normal-state utilization. When a region fails, traffic may shift to the remaining region; without enough capacity, the DR strategy will miss its SLO. Weigh standby cost against RTO/RPO targets and avoided outage cost.

### 6.3. Read Replicas and Caching

Read replicas can increase read throughput, but they add storage/compute, replication lag, and network cost. Caching reduces database requests, but costs memory/ops and introduces invalidation complexity. Compare cost per successful read, correctness, and freshness; do not assume adding replicas is always cheaper than query optimization.

## 7. Data Transfer: Hidden Costs Between Tiers and Regions

Data transfer is often difficult to estimate when an architecture lacks clear data-flow diagrams.

Common flows:
- Internet ingress/egress.
- Cross-AZ or cross-zone.
- Cross-region replication.
- VPC/VNet peering or transit networks.
- NAT gateways/egress gateways.
- CDN origin fetches and delivery.
- Object storage to compute or database.
- Log/trace export to SIEM.
- Third-party API and SaaS transfers.
- Backup copies and restores.

~~~mermaid
flowchart LR
    USER["Internet users"] --> CDN["CDN / edge"]
    CDN --> APP["Region A app"]
    APP --> DB["Region A database"]
    APP --> OBJ["Object storage"]
    APP <-->|"Cross-zone calls"| CACHE["Cache in another zone"]
    DB <-->|"Cross-region replication"| DR["Region B replica"]
    APP --> NAT["NAT / egress"]
    NAT --> EXT["External APIs"]
    APP --> LOG["Central log archive"]
~~~

### 7.1. Egress and Locality

Data egress to the internet or another provider usually has different pricing from ingress. If the app and database reside in different regions or zones, cross-zone traffic can incur charges according to service rules. Reading objects from another region or shipping logs to a centralized region can also generate transfer costs.

Optimizations:
- Co-locate compute near data subject to latency and residency constraints.
- Use private connectivity when beneficial, while still checking endpoint/transfer fees.
- Cache near users for appropriate content.
- Use a CDN for static/public content.
- Compress payloads when the CPU trade-off makes sense.
- Avoid serializing large payloads or making cross-region service calls on the critical path.
- Batch exports/logs instead of sending many tiny requests.
- Match replication scope to actual business requirements.

Do not optimize transfer by breaking network isolation or data residency. Security and compliance are constraints, not optional costs.

### 7.2. Cross-Zone Traffic

Spreading replicas across multiple AZs improves resilience, yet cross-zone requests, replication, or shared services can incur transfer fees. Inspect the topology: cross-zone load balancers, database client routing, cache placement, service mesh, and replication behavior.

You can favor locality or zone-aware routing to cut transfer costs, provided it does not overload a single zone or reduce availability. Measure cost alongside latency and failure behavior.

### 7.3. NAT and Egress Gateways

NAT gateways, firewalls, egress proxies, or inspection services may bill per hour and per volume of data processed. Routing all workloads through a single centralized NAT can create both high costs and bottlenecks. You should:
- Distinguish traffic bound for the public internet from traffic that has private endpoints.
- Check whether destinations support private service endpoints.
- Track bytes and costs per gateway/route.
- Avoid routing unnecessary log/object downloads through expensive egress paths.
- Preserve required security inspection and policies.

## 8. Cost Allocation: Knowing Who Owns the Cost

If the bill has only one line reading "production platform", teams cannot tell which service, tenant, or product feature is driving cost increases. Design cost allocation from the start.

### 8.1. Tag/Label Strategy

Useful tags often include:
- environment: dev/stage/prod.
- service/product: booking-api/search/payment.
- owner/team.
- cost-center or business-unit.
- application/tenant class.
- data classification.
- criticality/tier.
- managed-by/IaC repository.
- expiration/temporary resource.

Tags must never contain PII, secrets, or sensitive data. Use standardized naming/schemas, allowed values, and policy enforcement. Some services or cost lines do not fully support tags; combine account/project/subscription structure, usage labels, billing exports, and allocation rules.

### 8.2. Direct Cost and Shared Cost

- **Direct cost:** can be cleanly attributed to a workload, such as a dedicated VM or bucket.
- **Shared cost:** shared across multiple teams, such as a network hub, logging platform, DNS, security tooling, or shared cluster.

Ways to allocate shared costs:
- By request/transaction count.
- By CPU/memory usage.
- By storage consumed.
- By bytes transferred.
- By tenant/user count.
- By reserved capacity or an agreed allocation key.

Allocation must be transparent. It does not need to capture exact marginal cost, but it must create sound incentives. Explicitly report unallocated shared costs so reports do not appear falsely complete.

### 8.3. Unit Economics

Common metrics:
- Cost per booking completed.
- Cost per search request.
- Cost per 1,000 API calls.
- Cost per GB stored per month.
- Cost per TB scanned.
- Cost per message delivered.
- Cost per active tenant.
- Cost per successful inference/prediction.
- Cost per GB transferred.

Example:

\[
Cost\ per\ Booking = \frac{Total\ attributable\ platform\ cost}{Completed\ bookings}
\]

Specify what the numerator includes (compute, DB, storage, transfer, shared platform, support) and whether the denominator counts created bookings or completed bookings. Keep definitions consistent when comparing over time or across services.

### 8.4. Do Not Use Unit Cost Alone as the Sole Target

A lower cost/request may happen because failed requests consume fewer resources or because quality degraded. Track cost per successful transaction alongside SLOs, error rate, support load, and business value. Cost optimization must maintain a quality floor.

## 9. Forecasting, Budgets, and Anomaly Detection

FinOps is not just reading last month's invoice. Put budgets, forecasts, and anomaly detection in place before thresholds are breached.

### 9.1. Driver-Based Forecasting

A forecast can be built from:
- Request rates and workload mix.
- Active user/tenant counts.
- New data volume and retention.
- Replica counts/backup policies.
- Egress/replication traffic.
- Upcoming releases or planned campaigns.
- Price changes, commitment expiries, and FX/currency policies.

Preliminary model:

\[
Monthly\ Cost = Compute + Requests + Storage + Replicas + Transfer + Observability + Other
\]

Do not sum different physical units before converting them into cost using their respective rates. Store assumptions, rate sources, and forecast confidence levels.

### 9.2. Budget Alerts

Budgets can be configured by:
- Account/project/subscription.
- Service or team/cost center.
- Environment.
- Product/tenant.
- Cost category or usage quantity.

Reference alert thresholds: 50%, 80%, 90%, 100% of budget; these can be paired with forecasted spend. This is a sample policy, not a mandatory threshold. Route alerts to owners who can take action and attach the top cost drivers.

### 9.3. Anomaly Detection

Anomaly signals:
- Sudden jump in compute-hours.
- Multi-fold spike in requests or retries.
- Unusual storage growth.
- Rising data egress.
- Mass snapshot/backup creation.
- Replica count failing to scale in.
- Surge in log ingestion/cardinality.
- Unexplained increase in NAT/endpoint traffic.

Investigations must correlate billing with deployments, traffic, incidents, new tenants, retention policies, and abuse. Never automatically shut down a production resource solely due to a cost anomaly; use owners, severity levels, and approval-gated playbooks.

## 10. Backup, Snapshot, and Retention Costs

Backups help meet RPO/RTO, but create storage, API operation, transfer, and restore costs. Cost depends on:
- Full vs. incremental backups.
- Snapshot frequency.
- Retention period.
- Daily data churn rate.
- Cross-region/cross-account copies.
- Snapshot chains and deleted volume behavior.
- Restore performance and temporary capacity.

### 10.1. Backup Policy by Data Tier

| Data Tier | Criticality | Reference Strategy |
|---|---|---|
| Transaction/ledger | Very high | Backups + transaction log/PITR + restore drills |
| Booking operational data | High | Scheduled backups, PITR, and cross-region copies per RPO |
| Search index | Medium | Can be rebuilt from source; snapshot if rebuild is slow |
| Cache | Typically rebuildable | Not necessarily backed up; warm-up plan |
| Static objects | Depends on origin | Versioning/replication or backups |
| Temporary data | Low if rebuildable | TTL and cleanup |

Do not save money by dropping necessary backups. Conversely, do not back up rebuildable caches or temporary data at the same cadence as a transaction ledger without good reason.

### 10.2. Restore Cost and Recovery Capacity

Restores may require:
- Temporary compute.
- New storage.
- Network transfer.
- Elevated IOPS/throughput.
- Data reprocessing/replay.
- Operational staffing and downtime.

A cheap backup that takes two days to restore may fail RTO. Measure restore duration and cost at realistic scale rather than looking only at the backup bill.

## 11. Optimizing by Workload, Not Just by Resource Type

### 11.1. Compute

- Right-size after measuring peaks and SLOs.
- Autoscale on appropriate signals.
- Schedule dev/test and batch workloads.
- Use spot/preemptible capacity for checkpointed/retryable tasks.
- Optimize code, queries, and concurrency before adding instances.
- Select CPU/GPU architectures backed by benchmarks.

### 11.2. Request/Operation

- Cut N+1 queries and polling.
- Use batch APIs where supported.
- Coalesce similar events and logs.
- Use caches with clear freshness and invalidation semantics.
- Curb retry amplification.
- Use pagination and filtering to avoid full scans.

### 11.3. Storage

- Pick tiers according to access patterns.
- Use compression/columnar formats for analytics.
- Apply lifecycles to objects/logs/archives.
- Clean up orphaned/incomplete uploads.
- Partition/compact data.
- Set retention by requirement, not habit.

### 11.4. Replicas and Transfer

- Replicate only the data required for RPO/RTO.
- Choose warm standby/pilot light appropriate to criticality.
- Use zone-aware routing when safe.
- Place compute near data.
- Use a CDN for broadly distributed content.
- Batch/compact replication where semantics permit.
- Periodically verify that replicas/backups are actually serving their intended purpose.

## 12. Limits of Cost Optimization

Some ways of cutting a bill make the system worse:
- Reducing replicas leaves insufficient failover capacity.
- Downgrading storage tiers slows recovery.
- Shortening log retention destroys investigative capability.
- Stripping encryption or network inspection to save money.
- Raising cache TTLs serves stale data and causes business errors.
- Undersizing instances increases latency and errors.
- Running non-interruptible workloads on spot capacity.
- Disabling backups to reduce storage.
- Consolidating all services onto a single node to avoid network charges while expanding blast radius.

Before any change, establish the quality floor:
- Availability/latency SLOs.
- RTO/RPO.
- Security and compliance controls.
- Data freshness/correctness.
- Failover capacity.
- Operational toil and recoverability.

Count savings only when cost metrics drop while all of these constraints remain satisfied.

## 13. Sustainability and Resource Efficiency

Cost optimization often supports sustainability when it eliminates idle compute, redundant data, wasteful transfers, and duplicate processing. However, carbon footprint cannot be inferred from the bill alone, because impact also depends on regional energy mix, hardware efficiency, utilization, and embodied carbon.

Practical approaches:
- Right-size and shut down unused resources.
- Choose regions balancing latency, residency, and energy considerations.
- Compress data and cut unnecessary transfers.
- Apply lifecycle management and data minimization.
- Increase utilization without eroding resilience.
- Share resource pools where isolation permits.
- Track compute-hours, storage growth, and data transfer as operational proxies.
- Prefer services/instances with strong real-world workload efficiency when benchmarks confirm the gain.

Do not move workloads to a distant region purely for better pricing/energy metrics if doing so increases latency, transfer, data residency risk, or failure complexity.

## 14. Cost Governance and Ownership

A cost governance program requires clear roles:
- **Engineering owner:** owns workload design, utilization, and optimization.
- **Product/business owner:** defines value, demand forecasts, and quality trade-offs.
- **FinOps/finance:** owns billing data, allocation, forecasts, budgets, and commitments.
- **Platform team:** owns shared services, tagging policies, networking, and tooling.
- **Security/compliance:** ensures optimizations do not weaken controls or retention.

Process:
1. Establish account/project structure and tagging.
2. Export billing/usage data regularly.
3. Attribute costs to teams/services/tenants.
4. Review top cost drivers.
5. Create budgets and forecasts.
6. Detect anomalies.
7. Open optimization actions with owners.
8. Measure savings post-change and verify SLOs.
9. Review commitment utilization/expiry.
10. Update architecture decisions when traffic or product changes.

### 14.1. Unit Economics by Tenant

In a multi-tenant platform, you need to know which tenants drive disproportionate costs. You can allocate by:
- Request count and compute time.
- Storage GB-month.
- Data egress bytes.
- Database queries/throughput.
- Background job duration.
- Number of active users or workload class.

Do not measure per-tenant cost by attaching tenant IDs to every metric label if cardinality is high. Use billing meters, aggregation jobs, or a dedicated cost allocation pipeline.

## 15. Example Cost Model for the Booking API

Assume a monthly workload of:
- 100 million search requests.
- 5 million booking transactions.
- Application compute averaging 20 replicas.
- Database with a primary and one read replica.
- Object storage holding 8 TB of images and documents.
- 2 TB of logs in hot retention and 20 TB in archive.
- Cross-region replication for the database and critical objects.
- Egress to CDN and an external payment provider.

A model table lists quantities and rates:

| Component | Quantity Driver | Illustrative Cost Formula |
|---|---|---|
| API compute | replica-hours × instance rate | compute hours × rate |
| Search API operations | gateway request count | request units × request rate |
| Database | primary + replica hours, storage, I/O | instance + storage + I/O |
| Object storage | GB-month by class | capacity × class rate |
| Object operations | GET/PUT/LIST count | operation count × rate |
| Logs | ingest GB + retained GB-month | ingest + storage + query |
| Backup | snapshot storage + copies | backup GB-month + transfer |
| Cross-region | replicated GB | transfer GB × rate |
| Internet/CDN | requests + egress bytes | request units + delivery bytes |
| Payment integration | API requests/third-party fees | provider-specific rate |

You cannot calculate an exact bill without the provider, region, service tier, discounts, pricing contract, and current rates. This table serves as a data-collection framework for a pricing calculator or billing export.

### 15.1. Finding Optimization Opportunities

- If search requests rise while database QPS grows even faster, check for N+1 queries or cache misses.
- If storage grows faster than uploaded objects, check versioning, duplicates, incomplete uploads, and retention.
- If egress climbs, analyze CDN cache hit rates, cross-region reads, and log exports.
- If replica utilization is low, evaluate warm standby/pilot light while maintaining RTO/RPO.
- If the log bill spikes, check cardinality, debug logging, sampling, and retention.
- If cost per booking increases, separate fixed baseline from variable cost and check error/retry rates.

## 16. Illustrative ADR — Selecting a Replica Topology for the Booking Platform

> **Context:** The Booking API must protect transactions and meet RTO/RPO recovery targets approved by the product owner. Two regions are planned; normal traffic is concentrated primarily in Region A.
>
> **Option A:** Active-active application and database across both regions. Improves geographic availability and uses compute continuously, but requires a data ownership/multi-writer strategy, replication, and conflict handling.
>
> **Option B:** Region A active; Region B warm standby with scaled-down application capacity and a database replica. During an incident, scale up B and promote per runbook.
>
> **Illustrative decision:** Choose B if RTO accommodates scale-up time and measured failover tests meet targets. Do not choose it solely for lower normal-state cost.
>
> **Cost model:** Includes standby compute, replica storage, cross-region replication, backups, network egress, and game-day capacity.
>
> **Resilience:** Test peak traffic when A is lost, confirming quotas and sufficient capacity in B. If targets are missed, raise the baseline or change topology.
>
> **Security:** KMS/identity/secrets exist in both regions; replication channels and data residency are controlled.
>
> **Verification:** p95/p99, replication lag, actual RTO/RPO, cost/month, cost per booking, restore time, and data reconciliation.
>
> **Revisit conditions:** Traffic distributes across multiple regions, RTO tightens, or egress/standby costs change significantly.

## 17. Practice Exercise: Diagnosing an Unexpected Cost Spike

A booking platform saw its bill jump 45% last month while bookings grew only 8%. Preliminary reports show:
- Application compute up 10%.
- Object storage up 35%.
- Request operations up 60%.
- Cross-region transfer doubled.
- Logging ingestion up 70%.
- Database read replica utilization is low.
- Backup storage growing steadily with no recent restore drill.

**Tasks:**
1. Formulate hypotheses for each cost driver.
2. Identify metrics/usage details to pull for verification.
3. Distinguish fixed, variable, and step costs.
4. Look for request amplification across objects/databases/APIs.
5. Check object versioning, lifecycles, duplicates, and incomplete uploads.
6. Analyze cross-region traffic and cache/CDN behavior.
7. Review log volume, cardinality, sampling, and retention.
8. Evaluate whether replicas can be reduced or topology changed within RTO/RPO.
9. Construct cost per booking and cost per successful search.
10. Propose optimizations ranked by benefit, risk, and owner.

### Solution Approach

- Object storage up 35%: inspect byte growth, versioning, multipart uploads, duplicates, retention, backups, and data replication; compare new object counts with capacity.
- Request operations up 60%: analyze GET/PUT/LIST, retries, polling, N+1 queries, and cache hits; determine operations per transaction.
- Cross-region transfer doubled: check routing, replication scope, cross-region reads, CDN origin fetches, logging/exports, and workload placement.
- Logging up 70%: find sources/fields with growing cardinality, debug logging levels, duplicate ingestion, and retention; do not drop required security/audit logs just to cut the bill.
- Low read replica utilization: check workload routing, failover roles, read-after-write needs, and capacity when primary/zone fails before scaling down.
- Steady backup growth: review retention/version chains and compression while preserving RPO; run a restore drill to validate backup value.
- Calculate cost per booking/search alongside SLOs and error/retry rates so you do not optimize against a flawed denominator.
- Prioritize actions by estimated savings, effort, risk, time-to-benefit, and owner; re-measure after changes.

### Self-Check Questions

1. Why can a single HTTP request trigger multiple cost-bearing operations?
2. How do fixed, variable, step, and commitment costs differ?
3. Under what circumstances can the cheapest storage tier result in a higher total cost?
4. What costs do replicas incur beyond compute and storage?
5. In which situations do cross-zone and cross-region traffic arise?
6. Why are egress and NAT often hard to estimate without a data-flow diagram?
7. Who benefits from cost allocation tags in decision-making, and what are their limitations?
8. How should the numerator and denominator of cost per booking be defined?
9. Why should you not cut log retention or backups solely to hit a budget?
10. How do you balance warm standby cost against RTO?
11. How does a retry storm affect request costs and downstream costs?
12. Why must cost optimization account for SLOs, security, and sustainability?

Effective cloud cost management does not start by hunting for the cheapest instance. It starts with **the workload, the operations it generates, and the data journey across compute, requests, storage, replicas, and network**. When quantity drivers, owners, and unit economics are clearly measured, teams can spot cost amplification, right-size resources, choose sensible lifecycles and replication strategies, and forecast budgets accurately. Every saving must be verified alongside SLOs, RTO/RPO, security, and business quality so the architecture remains both efficient and sustainable.
