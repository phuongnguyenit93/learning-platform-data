# Trade-offs Between Latency, Durability, Cost, and Complexity

A good AWS architecture is not the fastest one, the one with the most replicas, or the one using the fewest services. The architecture must meet business objectives at a level of risk, cost, and operational effort acceptable to the organization. Reducing latency may require caching, replicas, or deploying closer to users. Those choices can raise costs, introduce brief stale-data windows, or complicate operations.

Four dimensions to weigh in this lesson are:

- **Latency:** the time a request or job takes to complete.
- **Durability:** the ability of data to survive and remain recoverable after failures or incidents.
- **Cost:** the total cost to provision, protect, operate, and evolve a workload.
- **Complexity:** the number of components, states, dependencies, procedures, and knowledge needed to build, operate, and troubleshoot.

These dimensions interact with one another. Synchronous replication may protect data better while adding network wait time. Caching cuts read latency while requiring freshness and invalidation policies. Multi-Region can improve geographic resilience while requiring solutions for replication, conflicts, identity, routing, and multi-site operations. A sound decision must rest on measurable requirements, experiments, and evidence from the workload.

## Learning Objectives

After this lesson, learners can:

- Distinguish latency, durability, availability, consistency, RPO, and RTO.
- Identify components contributing to latency on the critical path.
- Explain the impact of caching, replication, read replicas, partitioning, compression, and buffering.
- Compare synchronous writes with asynchronous processing and recognize data-loss risks.
- Choose backup, versioning, replication, and storage class strategies based on data value.
- Analyze infrastructure, data transfer, storage, operational, and recovery costs.
- Identify complexity introduced by distributed systems, multi-Region, event-driven processing, and cache invalidation.
- Use decision matrices, load tests, failure tests, and ADRs to document architectural decisions.
- Design tailored approaches for different data flows within the same AWS application.

## 1. Four Dimensions of an Architectural Decision

### 1.1. Latency

Latency is the time from when an operation starts until it produces a result usable by the caller. In web applications, users typically experience response time from sending a request to receiving the response. For background processing systems, latency can be the time from when an event is created until the job completes.

Do not look solely at averages. A handful of slow requests can severely degrade experience, especially when a request chains multiple service calls.

Common metrics:

| Metric | Meaning |
|---|---|
| p50 | 50% of requests complete within this duration or faster. |
| p95 | 95% of requests complete within this duration or faster. |
| p99 | 99% of requests complete within this duration or faster; exposes tail latency. |
| Throughput | Number of requests, transactions, or jobs processed per unit of time. |
| Queue age | Age of the oldest message/job still waiting to be processed. |
| Time to complete | Total time from start until a background job finishes. |

Example: an API has a p50 of 80 ms but a p99 of 2 seconds. Users can experience erratic performance even though the average looks good. Analyze slow requests, dependencies, retries, connection pools, and concurrent load.

### 1.2. Durability

Durability is the ability of acknowledged writes to survive failures of devices, hosts, racks, Availability Zones, or infrastructure components within the service's protection model.

Durability is not synonymous with availability:

- **Durability:** does the data still exist after a failure?
- **Availability:** is the data/service accessible when users need it?

A backup can be highly durable yet take time to restore, so it does not keep the application running immediately. Conversely, a service may remain available while the newest data has not yet replicated to the standby location.

Durability also does not automatically protect against every cause of data loss. If an authorized user or application deletes data, valid deletions can propagate across replicas. Malware, logic bugs, or a bad deployment can overwrite good data with bad data. Therefore, critical data also needs versioning, backups, retention, immutable copies, and restore testing.

### 1.3. Cost

Workload cost is more than EC2 hourly rates or GB of storage. Total cost can include:

- Compute, databases, caches, queues, and load balancers.
- Storage capacity, IOPS, requests, retrievals, and lifecycle transitions.
- Data transfer across AZs, Regions, Internet, edge, and on-premises.
- Replication, backups, snapshots, and cross-account/cross-Region copies.
- Logging, metrics, traces, security scanning, and data ingestion.
- Licenses, support plans, and third-party services.
- Engineering and operations effort for development, incident handling, and maintaining automation.
- Business cost of downtime, lost data, failed transactions, and missed opportunities.

An option with a higher unit price can still lower total cost if it finishes work faster, uses fewer instance-hours, or reduces incidents. Compare cost per request, cost per transaction, cost per GB processed, or cost per business outcome.

### 1.4. Complexity

Complexity is the amount of knowledge and effort required to understand, change, observe, deploy, and recover a system. It stems from:

- Number of components and dependencies.
- Number of Regions, accounts, AZs, and network boundaries.
- Number of data types, schemas, protocols, and consistency models.
- Caches, replicas, queues, retries, DLQs, and state machines.
- Multiple pipelines, deployment ordering, and migration procedures.
- Failover, reconciliation, backup, and restore mechanisms.
- Multiple teams or vendors co-owning a single processing flow.

Complexity carries direct costs: extra dashboards, runbooks, tests, IAM permissions, on-call load, and specialized skills. It also increases the probability of misconfiguration and extends incident investigation time.

A managed service can reduce operational complexity because AWS manages the underlying infrastructure, yet it still has service limits, IAM, quotas, network dependencies, and integration semantics to understand. Do not judge complexity solely by the number of service icons in a diagram.

## 2. Identifying What Is Mandatory vs. What Can Be Traded Off

Before choosing a solution, classify requirements into three buckets:

1. **Mandatory constraints:** compliance mandates, data residency, data-loss limits, security boundaries, contracts, or SLAs.
2. **Optimization targets:** p95 latency, throughput, cost per transaction, recovery time, or resource utilization.
3. **Acceptable trade-offs:** maximum staleness window, acceptable background-job delay, appropriate redundancy level, and operational steps the team can manage.

Examples:

| Data Type / Flow | Common Requirement | Acceptable Trade-off |
|---|---|---|
| Account balances and payment state | Never confirm a transaction until critical data is durably persisted; enforce tight consistency. | Accept extra latency on the critical write path. |
| Product catalog and content | Fast reads, high traffic tolerance, batchable updates. | Accept stale cache within a short, defined TTL. |
| Telemetry and clickstreams | High throughput, suited to batch or stream processing. | Accept processing delay and some eventual consistency. |
| Audit logs | Requires retention, access control, and tamper/deletion protection. | Can use slower-retrieval storage tiers if investigations tolerate retrieval time. |
| Analytical reports | Periodic updates, prioritizing reasonable processing cost. | Accept data lagging by minutes or hours per business needs. |

Do not force a single consistency model or SLA across the entire application. One workload may need synchronous writes for payments, caching for the catalog, and asynchronous processing for emails or reporting.

## 3. Where Does Latency Come From?

A request typically traverses many components. Total latency can include:

- DNS resolution and TLS handshake.
- Network round-trips across client, edge, load balancer, and backend.
- Queueing time when downstream components are overloaded.
- CPU, serialization, compression, and application processing time.
- Database queries, locks, commits, replication, and connection pools.
- External service calls or waiting on messages.
- Retries, timeouts, and backoff.

If steps run sequentially, latency roughly equals the sum of each step. If some steps run in parallel, duration depends on the slowest branch plus coordination overhead.

~~~mermaid
flowchart LR
    C["Client"] --> E["CloudFront / DNS / TLS"]
    E --> L["ALB / API Gateway"]
    L --> A["Application"]
    A --> D["Database"]
    A --> Q["Queue / Event"]
    Q --> W["Background worker"]
    D --> A
    A --> L
    L --> E
    E --> C
~~~

To reduce latency, first identify which steps lie on the critical path and measure each dependency's duration. Adding CPU or caching will not fix latency caused by DNS, networking, lock contention, or external services.

### 3.1. Tail Latency and Fan-Out

If a request calls multiple services in parallel, users typically wait for the slowest branch. When a page relies on 20 dependencies, the probability that at least one dependency is slow rises significantly. If called sequentially, total latency adds up directly.

Ways to reduce it:

- Reduce the number of dependencies on the critical path.
- Coalesce requests or build tailored read models.
- Set timeouts aligned with the latency budget.
- Use bounded retries with exponential backoff and jitter.
- Avoid synchronized retries causing retry storms.
- Offload non-immediate work to queues.
- Monitor p95/p99 per dependency rather than only overall API latency.

### 3.2. Moving Data Closer to Users

Amazon CloudFront can cache content at the edge to reduce round-trips to the origin. For static or infrequently changing data, longer TTLs increase cache hits and offload origins. Shorter TTLs or invalidations surface fresh content sooner, at the cost of more origin requests and potential charges.

For personalized APIs, design cache keys carefully. Omitting headers, cookies, or query parameters that identify the user can cause caches to serve one user's data to another. Never cache sensitive responses merely to shave off latency.

Implementation approaches:

- CloudFront for static assets and cacheable responses.
- ElastiCache for read-heavy data tolerating a freshness window.
- Browser caching for public content.
- API response caching when cache keys and access permissions are accurately scoped.

## 4. Trade-offs Between Latency and Durability

One of the most consequential decisions is when the system confirms a write has succeeded.

### 4.1. Synchronous Writes

In synchronous writes, the caller waits for the storage service to confirm the operation before returning success. Depending on the service, confirmation may include durable disk persistence or replication per service mechanics.

Advantages:

- Caller knows the operation met the designed commit condition.
- Suits transactions that must never report success before data is persisted.
- Easier to uphold business invariants when one write is a precondition for the next step.

Trade-offs:

- Can add network round-trips or replication wait time.
- Latency can spike when dependencies are distant or degraded.
- When the write target is unavailable, callers must wait or receive errors.
- Requires careful timeout and safe retry design.

Example: a payment service must write order status and payment reference to the database before confirming the order was accepted. The team accepts extra write-path latency to preserve business consistency.

### 4.2. Asynchronous Writes

In asynchronous processing, the request writes to a durable buffer or queue and responds to the caller before all downstream work finishes.

Advantages:

- Callers do not wait on slow downstream processing.
- Absorbs traffic bursts and regulates consumer pace.
- Easy to scale workers independently.
- Decouples producers from consumers and reduces runtime coupling.

Trade-offs:

- Business outcome is not yet finalized when the caller gets a response.
- Data may not yet appear in read models or secondary systems.
- Requires retries, DLQs, idempotency, ordering, and reconciliation.
- Queues or event pipelines become critical components to monitor.

Only return success after the message has been accepted by a durable storage mechanism meeting requirements. If events stay only in memory when returning HTTP 200, a process crash can lose them.

### 4.3. Comparing the Two Models

| Criterion | Synchronous Write | Asynchronous Write |
|---|---|---|
| Caller response | Waits for commit or write condition completion. | Can respond once queue/buffer accepts data. |
| User-facing latency | Usually higher on the write path. | Usually lower if delayed completion is acceptable. |
| Durability | Depends on datastore write ack and replication settings. | Depends on queue/buffer durability and consumer workflow. |
| Consistency | Easy to return results after transaction commit. | Typically requires eventual consistency across components. |
| Failure handling | Caller handles timeouts, rollbacks, or retries. | Consumer retries, DLQs, replay, and idempotency. |
| Complexity | Simpler for a small transaction; coupling grows with chained synchronous calls. | Adds queues, consumers, pending states, and reconciliation. |
| Best suited for | Payments, balance updates, permissions, critical transactions. | Emails, notifications, analytics, thumbnails, exports, and background jobs. |

Not all asynchronous operations are less durable. Amazon SQS stores messages durably per its service design, yet applications must still handle delivery semantics and delete messages at the right time. With SQS Standard, messages may be delivered multiple times; consumers should be idempotent. SQS FIFO provides 5-minute deduplication for producer retries, but does not eliminate all duplicates across an entire business workflow.

### 4.4. Transactional Outbox

A common failure happens when an application commits to the database but fails to send the event, or sends the event and then rolls back the database transaction. Two independent operations do not automatically form a distributed transaction.

A transactional outbox closes this gap:

1. In the same database transaction, write business data and an outbox record.
2. A publisher reads the outbox and sends events to SQS/EventBridge.
3. The publisher marks events as published after receiving acknowledgment.
4. Consumers process events idempotently and record outcomes.
5. Reconciliation jobs detect stuck events or repeated failures.

~~~mermaid
flowchart TD
    R["API request"] --> T["Database transaction"]
    T --> O["Order row + Outbox row"]
    O --> P["Outbox publisher"]
    P --> Q["SQS / EventBridge"]
    Q --> C["Idempotent consumer"]
    C --> D["Update downstream state"]
~~~

An outbox adds a table, publisher, and cleanup logic, yet prevents lost events between database commits and publishing. For critical business flows, this is usually a better trade-off than making synchronous calls to many services inside the request.

## 5. Consistency, Replication, and Read Latency

Consistency describes how soon reads reflect completed writes. Strong consistency and eventual consistency are the two primary models.

- **Strongly consistent read:** reads reflect all previously completed writes according to service guarantees and supported scope.
- **Eventually consistent read:** after an update, some reads may briefly return stale data until replicas converge.

Eventual consistency does not mean data is lost or random. It means the application accepts a convergence delay and designs UX and logic accordingly.

### 5.1. DynamoDB

Amazon DynamoDB supports strongly consistent reads on base tables and local secondary indexes (LSIs). Global secondary indexes (GSIs) and DynamoDB Streams support only eventual consistency. Eventually consistent reads are the default and consume lower read cost than strong reads under DynamoDB's pricing model.

Global tables offer consistency modes. Multi-Region eventual consistency (MREC) replicates changes asynchronously across Regions; Multi-Region strong consistency (MRSC) synchronizes changes across supported Regions before writes return. Multi-Region strong consistency carries specific deployment requirements and constraints, so verify Region/feature support before selecting it.

Choices:

| Use Case | Read Direction | Rationale |
|---|---|---|
| Catalog pages | Eventual consistency is usually enough. | A few seconds of lag matters far less than the cost/latency of strong reads. |
| Balances and transaction status | Align consistency with business invariants; strong reads when verifying latest state within supported scope. | Avoids making decisions on stale data. |
| Analytics dashboards | Eventual or batch-updated read models. | Optimizes throughput and cost when real-time reads are unnecessary. |
| GSI lookups | Must accept GSI eventual consistency. | GSIs do not support strongly consistent reads. |

Do not switch every read to strong consistency. Identify where stale data breaks business logic and where it is acceptable.

### 5.2. Read Replicas

Read replicas offload read queries away from the writer. They increase read throughput and relieve primary database load. In return:

- Extra compute and storage costs.
- Replicas can exhibit replication lag.
- Applications must route reads and writes properly.
- Read-after-write can return stale data if the read hits a lagging replica.
- Failover and endpoint handling must be tested.

With RDS/Aurora, distinguish Multi-AZ deployments for availability/failover from read replicas/reader endpoints for read scaling. Specific deployment types behave differently; never assume every standby accepts read queries.

### 5.3. Partitioning and Sharding

Partitioning splits data into smaller segments by key or range. Sharding distributes partitions across multiple nodes or datastores.

Benefits:

- Reduces the data volume any single node must handle.
- Increases horizontal scalability.
- Limits hotspots if keys distribute evenly.

Costs:

- Must choose partition keys carefully.
- Cross-partition queries become more complex.
- Multi-shard transactions become harder.
- Rebalancing and migrations require tooling and procedures.
- A hot partition key can create a bottleneck.
- Monitoring and troubleshooting must know where data resides.

Do not shard solely because a database is growing large. First inspect query plans, indexes, connection pools, storage, IOPS, cache hit ratios, and vertical/managed scaling options.

## 6. Caching: Trading Memory and Freshness for Speed

Caches store copies of data near readers to reduce retrieval latency from the primary source. Caches can live in browsers, CloudFront, API layers, or ElastiCache.

### 6.1. Benefits and Costs

Benefits:

- Reduces read latency.
- Reduces load on databases/origins.
- Absorbs traffic bursts.
- Can keep serving stale data during brief origin outages if policy allows.

Costs:

- Adds memory/storage and request charges.
- Requires designing TTLs, invalidation, and cache keys.
- Cache misses or stampedes can cause sharp origin load spikes.
- Stale data can cause incorrect business decisions.
- The cache becomes a dependency requiring monitoring and capacity planning.

### 6.2. Cache-Aside

A common pattern:

1. Application reads from cache.
2. On a hit, return cached data.
3. On a miss, read from datastore.
4. Write the result into cache with a TTL.
5. When source data changes, invalidate or update cache per policy.

~~~text
read(key):
  value = cache.get(key)
  if value exists:
      return value

  value = database.get(key)
  cache.set(key, value, ttl)
  return value
~~~

Example: a product catalog can tolerate 30-second staleness. Caching relieves database load when popular items are viewed repeatedly. Account balances or payment statuses should not share the same cache policy if stale reads cause bad decisions.

### 6.3. TTL, Invalidation, and Cache Stampedes

Longer TTLs raise hit rates while widening staleness windows. Shorter TTLs surface updates faster while increasing origin requests. Active invalidation updates sooner, but requires tracking dependencies between data mutations and cache keys.

A cache stampede happens when many concurrent requests hit a miss or expired entry and flood the origin simultaneously. Mitigations:

- Request coalescing or single-flight.
- TTL jitter so keys do not expire en masse.
- Stale-while-revalidate when business rules permit.
- Pre-warming caches for predictable hot content.
- Capping concurrency and protecting origins.
- Negative caching for missing items when appropriate.

Never cache sensitive data across users unless the cache key includes the required security context.

## 7. Buffering, Batching, and Compression

### 7.1. Buffering and Queues

Buffering holds work temporarily so producers and consumers can run at different speeds. Amazon SQS, Kinesis Data Streams, and Amazon MSK support varied messaging/streaming models.

Benefits:

- Absorbs traffic bursts.
- Decouples producer speed from consumer speed.
- Enables retries and background processing.
- Cuts downstream call counts when batching messages.

Trade-offs:

- Adds queue age and wait times.
- Requires managing visibility timeouts, retries, DLQs, ordering, and retention.
- Messages may be processed multiple times depending on delivery semantics.
- Backlogs can grow rapidly if consumer capacity falls short.

Monitor `ApproximateAgeOfOldestMessage`, visible/in-flight message counts, retry counts, DLQ depth, and processing rates. Never watch queue length alone: a small backlog with old messages can still breach SLAs.

### 7.2. Batching

Batching groups multiple operations into a single request or processing cycle. It lowers network/API overhead and raises throughput.

In return:

- Early items wait until the batch fills or times out.
- One bad item can affect multiple records.
- Larger payloads may hit service quotas.
- Partial failures and per-item retries must be handled.

Batching suits ingestion, log processing, and analytics. For interactive transactions needing immediate feedback, avoid waiting to fill batches if the latency budget cannot afford it.

### 7.3. Compression

Compression shrinks bytes transferred or stored, lowering network transfer time and storage bills. In return, CPU usage for compression/decompression rises and latency can worsen on tiny payloads or CPU-bound hosts.

Measure:

- Size before vs. after compression.
- CPU time.
- Network throughput.
- End-to-end p95/p99 latency.
- Storage and data transfer costs.

Do not compress already-compressed data or small payloads where overhead outweighs savings.

## 8. Durability: Replication Does Not Replace Backups

### 8.1. Replication

Replication maintains copies of data in one or more locations. It boosts resilience and can speed up recovery, yet replicas generally mirror changes from the source.

If an application accidentally deletes an object or encrypts data incorrectly, that operation can replicate to copies. Replication is not an independent historical point-in-time copy.

Examples:

- S3 Standard redundantly stores objects across multiple devices in at least three Availability Zones within a Region by service design.
- S3 One Zone-IA stores data in a single AZ; suitable for regenerable data or secondary copies, though exposed to full-AZ loss.
- S3 Replication copies objects across buckets/Regions for geographic or data-isolation needs.
- RDS Multi-AZ provides database availability/failover per deployment model; it does not replace backups and point-in-time recovery.

Durability/availability figures describe storage class/service design properties, not immunity against accidental deletion or overwrites.

### 8.2. Backups and Versioning

Backups create recovery points independent of current workload state. Layers of protection can include:

- S3 Versioning to retain object versions.
- S3 Object Lock to protect objects via retention/legal hold when configured properly.
- AWS Backup to manage backup plans, vaults, and lifecycles for supported resources.
- Snapshots and point-in-time recovery for databases/storage.
- Copying backups to another account or Region.
- Backup vault protection and IAM permissions separated from workload owners.

Backups incur storage, copy, retrieval, and governance costs. Longer retention reaches further back at higher cost. Too-short retention may miss slow ransomware or silent corruption.

### 8.3. RPO and RTO

- **RPO (Recovery Point Objective):** maximum data loss an organization accepts, typically measured in time.
- **RTO (Recovery Time Objective):** target duration to restore service after an outage.

| Strategy | Relative RPO / RTO | Cost / Complexity |
|---|---|---|
| Periodic backups, restore on demand | Longer RPO; RTO depends on restore duration. | Lower operating cost, but restores must be tested. |
| Frequent backups + PITR | Shorter RPO; RTO depends on service and data size. | Higher backup cost and retention management. |
| Warm standby | Typically lower RPO/RTO than backup-only if replication and capacity stay healthy. | Ongoing cost for standby environment and failover testing. |
| Multi-Region active-active | Can minimize disruption for eligible workloads. | High cost and complexity; must solve consistency, conflicts, and routing. |

Never pick a DR strategy by label alone. Measure RPO/RTO during restore/failover drills. An untested backup proves nothing about timely recovery.

## 9. Multi-AZ and Multi-Region: Higher Resilience, Higher Cost

### 9.1. Multi-AZ

Deploying across multiple AZs within a Region helps workloads survive localized infrastructure or AZ failures. Components such as load balancers, Auto Scaling, RDS Multi-AZ, and regional storage services support this model.

Benefits:

- Reduces reliance on a single physical facility.
- Allows failover or continued service from healthy AZs.
- Fits most production systems requiring high availability.

Trade-offs:

- Increases resource counts or spare capacity.
- Can incur cross-AZ data transfer charges.
- Requires testing application sessions, connection retries, DNS, and failover behavior.
- Does not protect against logic bugs, compromised credentials, or accidental deletions.

### 9.2. Multi-Region

Multi-Region places workloads or data in multiple AWS Regions. It addresses disaster recovery, data residency, or lower latency for globally distributed users.

Benefits:

- Isolation from Region-wide events.
- Serves users from closer locations.
- Enables geographic failover and data residency compliance.

Trade-offs:

- Increases compute, storage, replication, and data transfer costs.
- Must manage DNS/routing, certificates, secrets, IAM, quotas, and deployments across Regions.
- Replication may be asynchronous with lag.
- Multi-writer setups must handle conflicts and concurrent updates.
- Runbooks, game days, and monitoring grow more complex.
- Certain services or features are not available in every Region.

Do not assume Multi-Region is inherently better than Multi-AZ. If business RTO/RPO can be met with Multi-AZ plus cross-Region backups, active-active may not justify its cost and complexity.

## 10. Choosing Storage by Access Pattern and Data Value

A single workload often handles diverse data with differing needs. Do not store every dataset in the same storage tier.

| Data | Access Characteristics | Selection Direction |
|---|---|---|
| Public objects, frequent reads | Fast access, wide distribution needed. | S3 Standard + CloudFront. |
| Irregular access patterns | Fast retrieval needed, unpredictable frequency. | S3 Intelligent-Tiering if economics fit. |
| Infrequent access requiring fast retrieval | Lower storage cost acceptable alongside retrieval charges. | S3 Standard-IA or One Zone-IA per resilience needs. |
| Long-term archives | Rarely accessed, restore delay acceptable. | S3 Glacier storage classes matching retrieval time needs. |
| Transactional databases | Random reads/writes, transactions, and queries. | RDS/Aurora/DynamoDB based on data model and access patterns. |
| Caches | Regenerable or source-backed data. | ElastiCache or edge caches. |
| Shared concurrent files | Multiple compute nodes needing filesystem semantics. | Amazon EFS or Amazon FSx per protocol and workload. |

When selecting a storage class, consider minimum storage duration, retrieval fees, transition request fees, lifecycle policies, replication, and restore times. A class with lower per-GB storage rates can cost more if objects are accessed frequently.

## 11. The Cost of Latency, Durability, and Complexity

### 11.1. Estimating Total Cost of Ownership

A simple estimation model:

\[
TCO = C_{compute} + C_{storage} + C_{requests} + C_{network}
+ C_{replication} + C_{backup} + C_{observability}
+ C_{operations}
\]

Where `C_operations` includes personnel, tooling, and operational expenses. Real-world models may also include licensing, support, security, compliance, and downtime costs.

When comparing options, hold the workload profile constant:

- Daily and peak request/transaction counts.
- Read/write ratios.
- Payload sizes and retention.
- Number of AZs/Regions.
- Cache hit ratios and replication volume.
- RPO/RTO, backup retention, and restore frequency.
- Deployment frequency, incidents, and operational hours.

### 11.2. Example: Cache vs. Database Cost

Suppose a catalog API serves 1,000,000 reads per day. Without a cache, all requests hit the database. With a 90% cache hit ratio, roughly 900,000 reads are served from cache and roughly 100,000 hit the database (ignoring refreshes, invalidations, and auxiliary requests).

Caching reduces database reads by 90% in this simplified model, while adding cache infrastructure costs and freshness management. The change pays off only if combined cache + database costs drop or the business value of lower latency outweighs the added expense.

Do not assume a target hit ratio without verification. Measure against real key distributions, TTLs, evictions, and live traffic.

### 11.3. Example: Redundancy Cost

Suppose a workload considers two options:

- Option A: single Region, Multi-AZ, cross-Region backups.
- Option B: two Regions active-active, continuous replication.

Option B generally doubles compute/database capacity, adds network/replication traffic, and duplicates deployment pipelines and monitoring across both Regions. It can be worthwhile if a Regional outage causes severe losses or global latency demands it. If the workload tolerates a few hours to recover, Option A may meet goals at far lower cost.

Use the AWS Pricing Calculator and regional service pricing tables to calculate real figures. Never extrapolate one illustrative number across every account, Region, usage pattern, or contract.

## 12. Complexity and Operational Cost

A solution may lower latency while introducing multiple states to synchronize. For instance, combining a cache, read replicas, queues, and a search index creates multiple copies of the same data.

Teams must answer:

- What is the authoritative source of truth?
- When data changes, which copy updates first?
- How long can stale data be tolerated?
- If an event arrives twice, how do consumers handle it?
- If an event is lost or a consumer crashes, who detects it?
- How are caches/indexes/read models rebuilt?
- On failover, which node becomes the writer?
- Is there a way to reconcile data after concurrent writes across two Regions?
- Which runbooks are needed for on-call and who owns them?

Add a component only when it delivers measurable value. If caching saves a few milliseconds while introducing frequent stale-data bugs, invalidation headaches, and incidents, it may not be worth it.

### 12.1. Reversible vs. Irreversible Decisions

Some decisions can be reversed quickly:

- Cache TTLs.
- Autoscaling thresholds.
- Instance sizes.
- Batch sizes.
- Timeouts.

Some decisions are hard to reverse:

- Database engines or data models.
- Partition keys / sharding strategies.
- Event protocols / schemas.
- Multi-Region write ownership.
- Data residency and retention models.

For hard-to-reverse decisions, run PoCs and build migration plans, rollback paths, compatibility strategies, and ADRs before broad rollout.

## 13. Decision Matrix: Evidence-Based Option Selection

A weighted scoring matrix helps compare options, though scores never override mandatory constraints. First eliminate options violating compliance, RPO/RTO, or security boundaries.

Example comparing three options for a read-heavy catalog:

| Criterion | Weight | A: Direct DB | B: DB + Cache | C: DB + Read Replica + Cache |
|---|---:|---:|---:|---:|
| Latency | 30% | 2 | 5 | 5 |
| Durability/consistency | 20% | 5 | 4 | 4 |
| Cost | 20% | 5 | 4 | 2 |
| Complexity | 20% | 5 | 3 | 2 |
| Scalability | 10% | 2 | 4 | 5 |

Scores are illustrative on a 1–5 scale, not AWS benchmarks. Teams must customize weights and scores to real requirements. Option B may be a balanced choice if caching satisfies latency and staleness tolerances. Option C fits when read load is so high that a single cache tier is insufficient.

### 13.1. Decision-Making Process

1. Document business and non-functional requirements.
2. Identify mandatory constraints: compliance, security, RPO/RTO, data residency.
3. Measure baseline latency, throughput, cost, and failure behavior.
4. List a small set of viable options.
5. Evaluate impact across all four dimensions and relevant pillars.
6. Build PoCs or load tests for critical assumptions.
7. Run failure tests: AZ loss, network partitions, queue backlogs, cache flushes, replica lag, or restores.
8. Select an option and document what is prioritized and what trade-offs are accepted.
9. Roll out in stages and monitor metrics.
10. Re-evaluate when traffic, data volume, service pricing, or business requirements shift.

## 14. Design Scenario: Online Store

An online store has three main flows:

- Product catalog and images: very read-heavy, updated intermittently.
- Checkout and payments: requires accurate order state, no duplicate writes, and no false transaction confirmations.
- Notifications and analytics: can run in the background after order creation.

### 14.1. Catalog

Design:

- CloudFront caches images and public assets.
- ElastiCache caches frequently read product details.
- Database remains the authoritative source.
- TTLs match update frequency; invalidate on critical changes.

Trade-off: increases cache cost and complexity to reduce latency and database load. When a product's price changes, caches must update within the agreed freshness SLA.

### 14.2. Checkout and Payment

Design:

- Write the order and outbox event in one database transaction.
- Use idempotency keys to handle retries from clients/payment providers.
- Confirm order receipt only after the transaction commits.
- Publisher sends events to a queue; workers handle inventory/notifications.
- Use a Multi-AZ database if workload availability demands it.
- Backups/PITR and restore tests to meet RPO/RTO.

Trade-off: the write path may be slightly slower due to commits and idempotency checks, yet minimizes risk of lost or duplicate transactions. Notifications run asynchronously so they do not prolong checkout latency.

### 14.3. Notifications and Analytics

Design:

- SQS or EventBridge receives events after order commit.
- Consumers process idempotently with retries and DLQs.
- Analytics pipelines batch data into a data lake.
- Dashboards tolerate lag per analytics SLAs.

Trade-off: analytics data is not real-time, but cost and complexity stay far lower than synchronously updating every downstream system during checkout.

### 14.4. Per-Flow Decision Summary

| Flow | Latency | Durability | Cost | Complexity |
|---|---|---|---|---|
| Catalog | Low latency prioritized | Source data must be durable; cache may be stale. | Cache adds cost while reducing DB load. | TTL/invalidation and cache keys. |
| Checkout | Latency matters, but correctness is a hard constraint. | Transaction commit, backups, and idempotency. | Accepts appropriate database/HA costs. | Outbox, retries, reconciliation. |
| Notifications | Real-time not required. | Queues and retries protect jobs. | Workers scale with backlog. | DLQs and duplicate handling. |
| Analytics | Batch delay acceptable. | Retention and replay as required. | Optimizes storage/compute by schedule. | Pipelines, schemas, and data quality. |

## 15. Anti-Patterns to Avoid

1. **Optimizing p50 while ignoring p99.** Users still suffer terribly slow requests.
2. **Adding caching before measuring bottlenecks.** Caching does not fix everything and can introduce wrong data.
3. **Treating replicas as backups.** Replicas can propagate deletions or corruption.
4. **Returning success before data is durably stored.** Process crashes can lose operations.
5. **Keeping every step synchronous inside requests.** One slow dependency drags down overall latency.
6. **Putting every event in a queue without idempotency.** Retries can create duplicate transactions.
7. **Choosing Multi-Region merely for high availability.** Complexity and cost may exceed business needs.
8. **Sharding too early.** Adds complexity before proving the current database cannot scale.
9. **Choosing storage classes solely by monthly per-GB rate.** Ignores retrieval fees, minimum duration, transitions, and restore times.
10. **Measuring cost only on compute.** Ignores data transfer, logs, backups, replication, and operations.
11. **Skipping restore tests.** Backups may exist yet fail to meet RTO.
12. **Omitting timeouts or retry caps.** Can cause retry storms and cascading outages.
13. **Not monitoring replication lag.** Read replicas or DR Regions may lack recent writes.
14. **Failing to document trade-offs.** Future teams will not know why choices were made when conditions change.

## 16. Self-Check Questions

**1. How does durability differ from availability?**

Durability concerns whether data survives failures; availability concerns whether the service/data is accessible when needed.

**2. Why does replication not replace backups?**

Replication can replicate accidental deletions, overwrites, or corruption. Backups/versioning retain independent recovery points per retention policies.

**3. When are synchronous writes appropriate?**

When callers must know a critical transaction committed before confirming success, such as updating balances or placing orders.

**4. When is asynchronous processing appropriate?**

When work can finish after the response, such as notifications, thumbnails, analytics, or background tasks.

**5. Does eventual consistency mean data is lost?**

No. It means replicas may briefly return older data before converging.

**6. Why can caching cause incorrect business outcomes?**

Caches can serve stale data or another user's data if TTLs, invalidation, or cache keys are misdesigned.

**7. What trade-offs do read replicas introduce?**

Higher read throughput and lower primary load, at the expense of extra cost, replication lag, and routing complexity.

**8. How do queues help during traffic spikes?**

Queues absorb bursts and decouple producer speed from consumer speed; in return, you must manage queue age, retries, DLQs, and delayed consistency.

**9. How do RPO and RTO differ?**

RPO is the maximum acceptable data loss; RTO is the target maximum duration to restore service.

**10. When is Multi-Region worth the cost?**

When business requirements for disaster recovery, data residency, or geographic latency cannot be met within one Region using Multi-AZ and backups.

**11. Why is p99 latency important?**

It reflects the experience of the slowest requests and reveals tail latency masked by averages.

**12. Why document ADRs?**

ADRs preserve context, alternatives, rationale, impacts, and review triggers so decisions can be understood and reassessed later.

## 17. Pre-Finalization Architecture Checklist

- [ ] Latency targets are defined by p50/p95/p99 and business outcomes.
- [ ] Data is classified and authoritative sources are identified.
- [ ] Consistency models are specified for each read/write path.
- [ ] RPO and RTO are defined, and restore/failover drills are tested.
- [ ] Replication, high availability, and backups are clearly distinguished.
- [ ] Cache hit ratios, freshness, invalidation, and stale-data risks are measured.
- [ ] Queues have retries, DLQs, idempotency, and backlog/age monitoring.
- [ ] Read replicas/partitioning are justified by workload measurements.
- [ ] Multi-AZ/Region aligns with business requirements and is costed out.
- [ ] Storage classes are chosen by access patterns, retrievals, and retention.
- [ ] Data transfer, request, replication, backup, log, and operational costs are calculated.
- [ ] Component count, dependencies, failure modes, and operational skills are evaluated.
- [ ] Load tests, failure tests, and PoCs validate critical assumptions.
- [ ] Key decisions have ADRs, owners, and review dates.
- [ ] Metrics/alarms exist to detect when a trade-off no longer holds.

## References

- [Evaluate trade-offs between performance and other non-functional requirements](https://docs.aws.amazon.com/wellarchitected/latest/framework/perf01-bp02.html)
- [Understanding trade-offs in the AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/perf-understanding-tradeoffs.html)
- [Evaluate how trade-offs impact customers and architecture efficiency](https://docs.aws.amazon.com/wellarchitected/2024-06-27/framework/perf_architecture_evaluate_trade_offs.html)
- [Data management best practices](https://docs.aws.amazon.com/wellarchitected/latest/framework/perf03.html)
- [Data protection and durability in Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DataDurability.html)
- [Amazon S3 FAQs – durability and data protection](https://aws.amazon.com/s3/faqs/)
- [S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)
- [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [S3 Replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html)
- [Amazon DynamoDB read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html)
- [Amazon DynamoDB global tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [Amazon RDS Multi-AZ deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.html)
- [Amazon CloudFront cache expiration](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Expiration.html)
- [Understanding CloudFront cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cache-key-understand-cache-policy.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Exactly-once processing in Amazon SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon SQS outage recovery scenarios](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/designing-for-outage-recovery-scenarios.html)
- [AWS Backup feature availability](https://docs.aws.amazon.com/aws-backup/latest/devguide/backup-feature-availability.html)
- [AWS Pricing Calculator](https://calculator.aws/)
- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/framework.html)
