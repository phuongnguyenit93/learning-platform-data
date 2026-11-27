# Analyzing Availability Zone and Geographic Region Fault Tolerance

A serverless application scales automatically and runs on provider-managed infrastructure, yet that does not mean it automatically survives every infrastructure failure. A function can restart in another execution environment, while the database, queue, cache, network route, or secret store it depends on may still reside inside a single failure domain. When an infrastructure zone goes down, an entire business flow can halt even though function code did not change.

Fault-tolerant design requires understanding two common geographic tiers: **Availability Zone (AZ)** and **Region**. Multi-AZ keeps a system running when a single availability zone inside a Region fails. Multi-Region maintains service when an entire Region experiences an outage, though it introduces harder challenges around routing, data replication, consistency, write ownership, and recovery.

In the **CLOUD_SERVERLESS** module, learners build Java functions triggered by HTTP, messages, or events while handling state, permissions, retries, idempotency, cold starts, scaling, and cost. This lesson analyzes how to architect fault tolerance at the AZ and Region levels, define RTO/RPO, choose active-passive or active-active models, and test failover/failback procedures.

## 1. What is a failure domain?

A failure domain is an infrastructure boundary that can be affected by a single underlying fault. If multiple components depend on the same failure domain, an incident there can take them all down simultaneously.

Common failure domains:

- **Process/runtime:** A JVM, execution environment, or container crashes.
- **Instance/host:** A physical host or virtual machine fails.
- **Rack/network segment:** Power supply, switch, or local network link fails.
- **Availability Zone:** A relatively independent infrastructure zone within a Region.
- **Region:** A geographic area containing multiple AZs and cloud services.
- **Global service/control plane:** Shared DNS, identity provider, control plane, CDN, or management service fails.
- **External dependency:** Payment provider, email gateway, SaaS, or partner network becomes unavailable.

A system with many function instances that all write to the same single-AZ database still has a centralized failure domain. Adding more instances does not eliminate that point of failure.

~~~mermaid
flowchart TD
    G[Global entry / DNS] --> R[Cloud Region]
    R --> A[Availability Zone A]
    R --> B[Availability Zone B]
    R --> C[Availability Zone C]
    A --> F1[Function execution]
    A --> D1[Database node]
    B --> F2[Function execution]
    B --> D2[Database standby]
    C --> F3[Function execution]
    C --> Q[Queue / storage]
    G --> X[External identity / payment]
~~~

This diagram only illustrates scope separation. A managed serverless service may automatically distribute execution environments, while the HA and replication scope of each backing service depends on its configuration, service tier, and provider guarantees.

## 2. How do Availability Zones and Regions differ?

An **Availability Zone** is an isolated infrastructure zone within a Region. AZs are engineered to minimize correlated faults in power, networking, and physical facilities while remaining connected over low-latency links. Exact isolation boundaries and AZ naming vary by provider.

A **Region** is a broad geographic area typically comprising multiple AZs. Regions are spaced farther apart with separate failure domains and network connectivity. Geographic separation lowers the risk of a localized disaster hitting both simultaneously, at the cost of higher latency and greater data replication complexity.

| Criterion | Multi-AZ | Multi-Region |
|---|---|---|
| Protection scope | Failure of one AZ or zonal component | Broad outage across an entire Region |
| Network latency | Typically lower between AZs | Typically higher between Regions |
| Data replication | Can be synchronous or managed within the Region | Typically requires cross-Region replication |
| RPO | Can approach 0 with certain synchronous setups | Depends on replication lag and write model |
| RTO | Often shorter when failover is automated | Can be longer due to promotion, routing, and verification |
| Cost | Extra replicas/capacity and inter-AZ traffic | Extra stacks, replication, egress, and operations |
| Complexity | Moderate | Significantly higher |
| Use case | HA for localized infrastructure faults | DR for Region outages, geographic latency, or data residency |

Do not assume AZ names map identically across accounts or tenants if your provider uses randomized AZ mappings. Use provider-supported placement or zone IDs rather than hardcoding guessed names.

## 3. HA, fault tolerance, and disaster recovery

These three concepts are related yet target different goals:

- **High Availability (HA):** Minimizes downtime through redundancy, health checks, and failover.
- **Fault tolerance:** Continues serving partial or full functionality when a component fails, typically via replication and eliminating single points of failure.
- **Disaster Recovery (DR):** Restores services and data after a major disaster, such as losing an entire Region, widespread data corruption, or losing access to the primary environment.

Multi-AZ typically underpins HA within a Region. Multi-Region typically serves DR or multi-geography user latency requirements. A multi-Region active-active architecture can also provide HA, provided data and write ownership are designed accordingly.

Never equate HA with backups. Replicas will faithfully replicate accidental deletes or corrupted writes; backups let you restore to a point in time prior to an incident. Critical systems usually need both replication and independent backups.

## 4. Defining RTO and RPO

Before picking an architecture, establish two recovery targets:

- **RTO (Recovery Time Objective):** Maximum acceptable duration to restore service after an outage.
- **RPO (Recovery Point Objective):** Maximum acceptable amount of data loss, usually expressed as a time window of recent data.

For example, if RTO is 15 minutes, the service must return to an acceptable operational level within 15 minutes. If RPO is 1 minute, the system can tolerate losing at most roughly one minute of the newest data under the defined scenario.

RTO/RPO must be driven by business needs, not picked solely from cloud feature checklists.

| Illustrative workload | Target RTO | Target RPO | Architectural direction to consider |
|---|---|---|---|
| Low-priority internal reports | Several hours | Several hours | Backup and restore |
| Standard business APIs | 30–60 minutes | 5–15 minutes | Warm standby, asynchronous replication |
| Critical payments/ordering | Minutes | Near 0 to a few seconds where feasible | Multi-AZ, rehearsed cross-Region DR |
| Reproducible public content | Minutes to hours | Reproducible | CDN/cache and backup origin |

Values in this table are discussion examples, not default recommendations or provider SLAs. A zero RPO may demand synchronous writes, quorum consensus, or specialized distributed storage; in return, latency and write availability during network partitions may suffer.

### Defining RTO/RPO per capability

A system can have distinct RTOs for read APIs, write APIs, payment processing, and reporting. If the database recovers in 10 minutes while DNS failover takes 20 minutes, overall RTO is still governed by DNS. Measure from the user's perspective: the moment the first request succeeds with valid data and correct side effects.

When planning, decompose RTO into measurable phases: incident detection, failover decision, fencing the old writer, data promotion/restore, capacity readiness, traffic rerouting, and business verification. For queue-based systems, include the time to drain backlogs back within SLA; an API may already accept requests while orders remain queued. Measure RTO per capability as well as end-to-end business flow recovery.

## 5. Multi-AZ for serverless: functions are not the entire architecture

Serverless functions typically have their execution environments and scaling managed by the provider within a Region. However, the dependencies a function relies on may have different zonal or regional architectures.

A Multi-AZ design must evaluate:

- Does the function/API endpoint depend on a single subnet or single network route?
- When the function attaches to a VPC, do its subnets span multiple AZs?
- Do NAT gateways, firewalls, route tables, or VPC endpoints have single-AZ dependencies?
- Does the database have a standby/failover node in another AZ?
- Do caches, search clusters, and message brokers maintain replicas across multiple AZs?
- Is object storage/queue a regional service or a resource pinned to a single AZ?
- Are secrets, KMS keys, certificates, and identity dependencies available in fallback AZs?
- Can logs, metrics, and traces continue shipping if one AZ loses connectivity?

Not every cloud service requires users to deploy an instance per AZ manually. Many managed services already distribute internally or offer a Multi-AZ option. Read the actual availability scope and configuration of your exact service tier.

### Example of a function in a VPC

If a Java Lambda needs access to a private database, the function can be configured with multiple subnets across different AZs. That gives the function's network interfaces path diversity across AZs, yet it does not automatically make the database, NAT, or routes highly available.

If a function only calls regional services via managed endpoints, the network path and failure domain differ. Identify which dependencies are truly zonal and which are provider-managed at the Region level.

## 6. Protecting network paths across multiple AZs

Networking can become a single point of failure even when compute and databases are Multi-AZ.

Key checks:

- Subnet placement: Are workload subnets spread across multiple AZs?
- Route tables: Does every subnet keep required routes when one AZ fails?
- NAT: If outbound Internet access is needed, is NAT redundant per AZ or backed by alternatives?
- VPC endpoints/private links: Do endpoints have zonal placement limits or quotas?
- Firewalls/security appliances: Are clusters and routes redundant?
- DNS resolvers: Does the application depend on a single self-managed resolver?
- Connection pools: After failover, are stale connections replaced properly?

If multiple subnets route through a single NAT instance or network appliance, the architecture can still lose outbound connectivity when that component fails. Assess both inbound request paths and outbound dependency paths.

Do not funnel all traffic through a single centralized choke point solely to simplify networking unless that choke point has matching redundancy.

## 7. Multi-AZ databases and the role of failover

The database often dictates actual RPO/RTO. Common models include:

- **Synchronous standby:** Primary confirms commit only after data reaches a replica via synchronous/quorum replication. Reduces RPO at the expense of network sensitivity and write latency.
- **Asynchronous replica:** Primary acknowledges first, replica updates afterward. Lowers write latency but introduces replication lag and potential loss of recent writes on abrupt failover.
- **Managed Multi-AZ:** Provider manages standby provisioning, health detection, and part of the failover transition.
- **Read replica:** Primarily serves read scaling or DR depending on the product; does not automatically accept writes by default.

Distinguish database failover from application failover. After the database promotes a new primary, a Java function may still hold pooled connections pointing to the old endpoint. Connection pools must detect stale connections, perform bounded retries, and reconnect.

### During database failover

1. Database detects the primary is unavailable.
2. System selects/promotes a standby per service mechanics.
3. Endpoints or DNS records may update.
4. Clients must evict old connections and reconnect.
5. In-flight requests may receive timeouts or transaction errors.
6. Application must retry safely using idempotency keys.
7. Queues/workflows may replay unacknowledged work.

Never retry a non-idempotent write merely because the client timed out. The transaction may have committed while the response was lost. Before retrying, use an idempotency key or query operation state to confirm the outcome.

## 8. Queues, event buses, and streams in Multi-AZ architectures

Managed queues and event services carry their own availability models. A regional queue does not require creating one queue per AZ. Still, consumers, producers, encryption keys, permissions, and downstream destinations must be verified.

For queues/events:

- Producers must handle publish timeouts without generating duplicate business events.
- Consumers must be idempotent because redelivery is normal behavior.
- Visibility timeouts/leases must exceed processing duration.
- DLQs must have retention, read permissions, and alerts.
- Event schemas and event IDs must remain stable for replay.
- Workflows require checkpoints or durable state.
- If one AZ fails, consumers in other AZs must continue picking up work where supported by the service.

For streams with partition/shard ordering, do not arbitrarily alter consumer placement or checkpoints. Failover must preserve sequence semantics and avoid two consumers concurrently processing the same partition unless supported by the service.

## 9. Multi-Region: when is it needed?

Multi-Region brings higher cost and complexity than Multi-AZ. Consider it when one or more of the following apply:

- RTO for a Region outage is tighter than intra-Region recovery capabilities.
- RPO requires replication to a separate geographic area.
- Data residency rules or multi-geography user latency demand it.
- A single Region lacks sufficient capacity or cannot meet latency targets.
- Broad-area disruption risk must be mitigated.
- Business continuity is required even if the primary Region is completely lost.

Never adopt Multi-Region simply because "clouds can fail." First quantify impact, probability, RTO/RPO, and downtime cost. A well-tested backup strategy may fit better than active-active if the business tolerates a longer RTO.

## 10. Common DR patterns

### Backup and restore

Retain only necessary data backups, artifacts, configs, and IaC definitions. During an outage, rebuild the stack in another Region and restore data.

- Lower ongoing cost than keeping full compute running.
- Longer RTO due to provisioning and restore times.
- RPO depends on backup frequency and log shipping capabilities.
- You must test restores, not merely confirm backup jobs succeeded.

### Pilot light

Keep minimal core components running in the standby Region, such as a database replica or essential foundation infrastructure. During an outage, scale up and deploy the remaining stack.

- Shorter RTO than pure backup and restore.
- Moderate cost.
- Requires automating scale/deploy steps and checking dependencies.
- Standby capacity may not absorb full production load instantaneously.

### Warm standby

Maintain a more complete deployment in the standby Region running at reduced capacity. On failover, scale capacity up and shift traffic.

- RTO is typically shorter than pilot light.
- Ongoing costs for running compute and data replication.
- Must test capacity ramp-up and service quotas in the standby Region.

### Hot standby / active-passive

The primary Region serves traffic; the standby Region keeps capacity ready or near-ready. On failover, the standby Region takes over most or all traffic.

- RTO can be short if data, routing, and capacity are pre-warmed.
- Expensive to maintain idle standby capacity.
- Requires fencing so the old Region cannot keep writing once the new Region is promoted.

### Active-active

Multiple Regions serve live traffic simultaneously. Users can route to the nearest Region or by policy.

- Can reduce user latency and sustain service if one Region fails.
- Must solve write ownership, conflict resolution, and consistency.
- Higher replication, networking, and operational costs.
- Failover traffic must be controlled so surviving Regions do not overload.

| Pattern | Standby capacity | Relative RTO | Relative RPO | Cost/complexity |
|---|---|---|---|---|
| Backup and restore | None or minimal | Long | Per backup/replication | Lower |
| Pilot light | Core components | Medium to long | Per replica/log shipping | Moderate |
| Warm standby | Low-capacity running stack | Medium to short | Per replication | Higher |
| Hot standby | Near-production capacity | Short if cutover is smooth | Per replication/consistency | High |
| Active-active | Multiple Regions serving live | Potentially very short at routing layer | Depends on write model | Highest in most cases |

Relative ratings are not guarantees. A warm standby with unprepared DNS, database promotion, or quotas can suffer a longer RTO than a well-automated pilot light.

## 11. Choosing active-passive vs. active-active

Active-passive fits when you want a single write owner and a secondary Region waiting to assume that role upon failover. It simplifies consistency and business ownership, though it requires testing promotion and fencing.

Active-active fits when serving multiple geographies concurrently or requiring very high continuity, and when data can be partitioned by ownership or conflict resolution is well-defined.

Questions to answer before choosing:

- Can data be partitioned by tenant/customer/aggregate so each Region owns a disjoint slice?
- Can two Regions update the exact same record simultaneously?
- If concurrent writes happen, are conflicts resolved via versions, sequences, or business merges?
- Is eventual consistency acceptable?
- Can writes be routed back to a home Region?
- If one Region loses connectivity to the other, does the system keep accepting writes or switch to read-only?
- Is there a mechanism preventing the old Region from continuing writes after failover?

Never implement active-active merely by deploying the same function in two Regions behind round-robin DNS. If both functions write to the same database or two uncoordinated replicas without a conflict strategy, data corruption/inconsistency will follow.

## 12. Cross-Region replication and consistency

Replication can be synchronous or asynchronous.

**Synchronous replication** requires consensus confirmation before returning success. It reduces RPO, yet increases latency and can halt writes when inter-Region networks partition.

**Asynchronous replication** lets the primary acknowledge before replicas receive all data. It lowers write latency, yet introduces replication lag. On sudden primary loss, recent writes may not have reached the replica.

### Replication lag example

Suppose Region A writes an event at `10:00:00.100Z`. Region B receives that event at `10:00:02.100Z`. If Region A fails at `10:00:01Z`, replica B does not yet have the latest write. That lag window directly determines RPO.

Do not measure only average lag. Monitor p95/p99 replication lag, oldest unapplied log/event, replica health, and catch-up speed after link recovery.

### Read-after-write

A user who just wrote data in Region A and gets routed to Region B may read stale replica state. Mitigations:

- Pin session affinity to the home Region for a bounded window.
- Pass version tokens to check whether the replica has caught up.
- Route to the primary when strict read-your-writes is required.
- Return a pending state if the domain tolerates eventual consistency.
- Never route writes to another Region without clear ownership transfer.

## 13. Split-brain and writer fencing

Split-brain occurs when two Regions both believe they are primary and both accept writes. This happens during a network partition separating the Regions while clients can still reach both.

Consequences:

- Two records with the same ID diverge in content.
- Sequences/versions fork.
- Inventory or quotas get over-allocated.
- Payment/order side effects execute twice.
- Subsequent replication cannot automatically merge business intent cleanly.

You need explicit writer ownership enforcement:

- A single authority or quorum decides the active writer.
- Time-bounded leases with renewal.
- Monotonic fencing tokens/epochs incremented on every primary promotion.
- Storage layer rejects writes carrying stale epochs.
- Runbooks forbid promoting a new Region before fencing the old Region.

### Fencing tokens

Suppose Region A holds epoch 41. During failover, the system issues epoch 42 to Region B. The authoritative database or storage service accepts writes only with the latest epoch. If Region A recovers and sends writes tagged with epoch 41, those operations are rejected.

Fencing must be enforced at the storage write boundary, not merely inside a Java process's memory. If an in-memory boolean indicates whether a Region is active, a lingering instance can still write after another process switched roles.

## 14. Idempotency during failover and replay

During DR, events may be replayed from queues, streams, outboxes, or backups. A request might process in Region A and get resent to Region B because the response never reached the client. Consumers require stable cross-Region idempotency keys.

An idempotency record should include:

- Stable event ID or operation ID.
- `PROCESSING`/`COMPLETED`/`FAILED` status.
- Stored result or reference to created side effects.
- Version/epoch if write ownership moves across Regions.
- Creation timestamp and retention duration.
- Origin Region and trace/correlation references if needed.

If the idempotency table lives only in Region A's database and was not replicated before failover, Region B may not know the event already completed. For critical side effects, decide where deduplication records live and define their RPO.

For external providers like payment gateways, forward the same idempotency key if the API supports it. If not, store provider references and reconcile before retrying an operation that may have already succeeded.

## 15. Cross-Region event routing and queues

A Multi-Region architecture must decide where events are produced and consumed.

Common patterns:

- **Dedicated regional queues:** Each Region has its own queue/consumer; producers route events to the data-owning Region.
- **Replicated event streams:** Events replicate to another Region for DR or analytics.
- **Global event routing:** A routing layer dispatches events by Region, tenant, or event type.
- **Central queue:** Multiple Regions consume a shared queue if supported by the service and latency/availability fit.

Key questions:

- Are events published simultaneously to two Regions?
- If publishing succeeds in A but fails in B, what does retry do?
- Can consumers process the same event in both Regions?
- Is event ordering preserved per aggregate/partition key?
- On failover, is old backlog in Region A replayed or skipped?
- Which Region hosts the DLQ and who is authorized to redrive?
- Are event schemas and encryption keys available in the standby Region?

A transactional outbox writes business changes and outbound events inside the same transaction. A dispatcher retries publishing while idempotent consumers handle duplicates—preventing lost events if the app crashes between database commit and publish.

## 16. Serverless workflows in Multi-Region

Workflow engines usually persist execution state inside a single Region or service boundary. Never assume a running workflow execution automatically continues in another Region if the primary Region goes down.

Determine:

- Are workflow definitions deployed in the standby Region?
- Is execution state replicated or checkpointed to an independent store?
- Can timers, callback tokens, and wait states be recovered?
- Can an in-flight task safely re-run in the new Region?
- Are tasks and external side effects idempotent?
- Are compensation steps persisted and safely replayable?
- Are workflow run IDs stable across restore/restart?

For long-running workflows, persist business state and operation checkpoints durably outside function memory. During DR, start a fresh execution from the last checkpoint rather than attempting to live-migrate a running execution.

Never restart a workflow from scratch before reconciling prior side effects. Before resuming, determine which tasks committed, which have unknown outcomes, and which are safe to re-execute.

## 17. Traffic routing and failover

Traffic shifts between Regions via DNS failover, global load balancers, anycast routing, CDNs, or API gateways. Each mechanism has distinct convergence speed and semantics.

### DNS failover

DNS can return the healthy Region's address. However, resolvers, clients, and connection pools may cache DNS past its TTL, and existing open connections do not automatically migrate. Therefore, a low DNS TTL does not guarantee instantaneous client migration.

### Global load balancers

Global load balancers health-check endpoints and route requests to healthy Regions. Ensure health checks reflect real business readiness rather than just process liveness.

### Client-side routing

SDKs or clients can select Regions by policy. This requires managing endpoint lists, certificates, auth, and client caches. Outdated clients may hold stale routing configurations longer than expected.

### Health checks

Distinguish clearly:

- **Liveness:** Is the process/runtime alive?
- **Readiness:** Can the service accept new requests?
- **Dependency health:** Can the database, queue, or external API support business operations?
- **Synthetic transactions:** Does a representative end-to-end test flow succeed?

If a health check probes too deeply across many dependencies, it can add heavy load or mark an entire Region unhealthy over a non-critical dependency slowdown. Design readiness per capability: read APIs might stay operational while write APIs pause.

## 18. Controlled failover procedure

Failover should never be just flipping DNS. A typical sequence:

1. **Detect:** Confirm the outage via multiple independent signals, ruling out single monitoring glitches.
2. **Declare:** An incident commander or authorized automation declares failover.
3. **Fence:** Prevent the old Region from accepting writes if write ownership is moving.
4. **Assess data:** Inspect replication lag, actual RPO, and in-doubt transactions.
5. **Promote:** Promote the database/replica or restore data stores in the target Region.
6. **Verify dependencies:** Check IAM, KMS, secrets, networking, queues, event sources, and external allowlists.
7. **Scale capacity:** Increase instances/concurrency and verify quotas.
8. **Enable consumers:** Start queue/stream consumers only after writers and idempotency stores are ready.
9. **Route traffic:** Cut over DNS/global routing or API endpoints.
10. **Observe:** Track error rates, p95/p99 latency, backlogs, duplicates, replication lag, and business completion.
11. **Communicate:** Publish service status and data impact updates per organizational process.

If you cannot prove the old Region is fenced, never permit two Regions to write authoritative data simultaneously. Temporarily switching parts of the API to read-only or returning controlled write errors is safer than causing split-brain.

## 19. Failback after the primary Region recovers

Failback shifts workloads from the standby Region back to the primary Region. It should never happen the instant the primary Region reports healthy.

Before failback:

- Verify the root cause of the outage has been resolved.
- Check whether the old data store is stale or corrupted.
- Synchronize data generated during DR back to the primary.
- Establish new writer authority and a higher fencing epoch.
- Check event backlogs, DLQs, and running workflows.
- Verify capacity/quotas and networking.
- Test routing on a small slice or canary.
- Monitor consistency and business metrics before cutting over 100% of traffic.

In many systems, continuing to run in the standby Region longer is safer than rushing failback. Base timing on risk and cost, not simply on the old Region coming back online.

## 20. Cross-Region backup and restore

Replication provides near-real-time copies, whereas backups let you roll back to before accidental deletion or logical corruption. Both mechanisms must be independent enough that a logic bug cannot destroy every copy.

Backup checklist:

- Are backups stored in a separate failure domain?
- Are cross-Region or immutable/offline copies maintained?
- Are encryption keys accessible from the recovery Region?
- Does retention satisfy RPO and compliance requirements?
- Are checksums and integrity verified?
- Are restores rehearsed with representative production-like data?
- Are runbooks documented for restoring schemas, secrets, IAM, and networking?

A successful backup job does not prove restore capability. Measure restore duration, recovery point accuracy, and data verification coverage.

## 21. Security in Multi-Region architectures

The standby Region must maintain a security posture equivalent to the primary Region. Commonly overlooked items:

- IAM roles/policies and trust relationships.
- KMS keys, key policies, and decrypt permissions.
- Secret managers and secret versions.
- TLS certificates, custom domains, and DNS records.
- Network ACLs, security groups, firewalls, and private endpoints.
- Audit logs, security events, and alert destinations.
- Backup access, replication roles, and break-glass accounts.

Do not casually duplicate long-lived secrets across Regions. Use secret managers/KMS with least privilege and verify key accessibility during failover. If an encryption key exists only in the primary Region, replicated data may be unreadable in the target Region.

Failover is also a security-sensitive event. Audit who promoted databases, incremented writer epochs, switched routes, and redrove messages.

## 22. Cost and trade-offs of Multi-AZ / Multi-Region

Costs go far beyond function invocations:

- Database standbys/replicas and storage.
- Warm function capacity or provisioned concurrency.
- Queue, stream, and event replication.
- Cross-AZ and cross-Region data transfer.
- NAT gateways, private endpoints, load balancers, and DNS.
- Multi-Region logs, metrics, and traces.
- Backups, snapshots, and restore drills.
- KMS keys, secret replication, and auditing.
- Operational overhead, drills, and on-call support.

Active-active can increase capacity and reduce latency, yet it raises replication and conflict-resolution costs. Warm standby uses less compute than hot standby at the cost of a longer RTO. Backup/restore is generally cheapest to maintain, but incurs longer recovery times and demands strong automation.

Model costs across a full DR scenario: standby runtime duration, failover traffic, data egress, backlog replay, and post-incident capacity.

## 23. Observability across AZs and Regions

Dashboards should slice metrics by Region, AZ (where metadata is exposed by the provider), service, function, route, and dependency.

Key metrics:

- Request rate, error rate, and p95/p99 latency per Region.
- Invocation concurrency, throttling, and cold starts.
- Queue depth, oldest message age, retries, and DLQs.
- Database primary/replica health and replication lag.
- Connection errors, DNS resolution, and network latency.
- Workflows started/running/failed/completed per Region.
- Idempotency duplicate/conflict counts and fencing rejections.
- Failover/failback states and step durations.
- Backup/restore job statuses and restore drill durations.

Correlation IDs, trace IDs, and workflow run IDs link logs across Regions. Keep in mind that telemetry pipelines can also suffer during a Region outage—maintain independent status visibility or global monitoring outside the Region being monitored.

## 24. Testing fault tolerance

Testing does not stop at verifying a function returns 200. Verify data integrity, side effects, ordering, and RTO/RPO targets.

Test types:

1. **AZ isolation:** Blackhole a subnet, route, or zonal dependency in a test environment.
2. **Instance/runtime failure:** Terminate instances or force function timeouts to validate retries and idempotency.
3. **Database failover:** Switch primary/standby and verify connection pool recovery.
4. **Network partition:** Simulate broken inter-Region links to verify writer fencing.
5. **Region failover:** Cut routes to the primary Region and shift traffic to standby.
6. **Queue replay:** Redrive messages and verify zero duplicate side effects.
7. **Workflow resume:** Recover from checkpoints and confirm committed steps do not re-execute wrongly.
8. **Backup restore:** Restore data into an isolated environment and measure actual RTO/RPO.
9. **Failback:** Shift back to the original Region after synchronization and fencing.
10. **Capacity test:** Confirm the standby Region handles full failover load.

### Game days and chaos testing

A game day is a scripted exercise with defined scenarios, accountable owners, success criteria, and rollback steps. Chaos testing injects controlled faults such as latency, packet loss, process termination, or dependency outages.

Start in non-production with narrow scope. Test in production only with formal approval, strict blast radius limits, active monitoring, and explicit abort criteria.

## 25. Java example: verifying writer ownership and idempotency

The example below illustrates a consumer allowed to write only while the current Region holds the latest writer epoch. The repository must execute these checks via transactions/conditional writes at the authoritative storage layer.

~~~java
public final class OrderEventConsumer {
    private final WriterLeaseRepository leaseRepository;
    private final InboxRepository inboxRepository;
    private final OrderRepository orderRepository;

    public void handle(
            OrderCreated event,
            String region,
            long writerEpoch) {

        transaction(() -> {
            if (!leaseRepository.isCurrentWriter(region, writerEpoch)) {
                throw new StaleWriterException();
            }

            InboxClaim claim = inboxRepository.claim(event.eventId());

            if (claim.isCompleted()) {
                return;
            }

            if (!claim.isOwnedByCurrentAttempt()) {
                throw new RetryableProcessingException();
            }

            orderRepository.applyCreatedEvent(event);
            inboxRepository.markCompleted(event.eventId());
        });
    }
}
~~~

This is pseudocode since transaction and claim semantics depend on the database. Critical requirements:

- Writer epoch must be validated atomically at the storage boundary.
- Inbox event IDs must have a unique constraint or conditional write.
- Business updates and `COMPLETED` status must commit in the same transaction when sharing a database.
- If an event stays `PROCESSING` in a separate transaction, enforce leases/timeouts and recovery.
- External side effects need provider idempotency keys or outbox/reconciliation.
- The old Region must never write merely because a Java process still holds stale configuration.

Never rely solely on in-memory flags to decide write authority. Following a network partition or failover, older processes may not have received updated configuration.

## 26. Architecture selection matrix

| Requirement | Multi-AZ | Warm standby Region | Active-active Region |
|---|---|---|---|
| Survives single AZ failure | Yes, if dependencies are distributed | Possible, though not primary goal | Yes |
| Survives full Region failure | No | Yes, within designed RTO/RPO | Yes, if data plane and routing are ready |
| Cross-Region latency | Avoided for normal requests | Only during replication/failover | Frequent for cross-Region reads/writes |
| Write ownership | Single Region | Primary then promoted standby | Must partition or resolve conflicts |
| Operations | Low to moderate | Moderate to high | High |
| Cost | Moderate | High | Highest in most cases |
| Best suited for | HA for standard applications | DR with relatively short RTO | Multi-geography workloads with designed consistency |

No single pattern fits every system. Choose based on RTO/RPO, consistency needs, operational maturity, data residency, and budget.

## 27. Common design mistakes

| Mistake | Consequence | How to avoid |
|---|---|---|
| Deploying only multiple function instances | Database or network remains a single point of failure | Map failure domains across the entire dependency chain |
| Assuming managed serverless automatically makes all dependencies Multi-AZ | Queues, databases, or NATs may remain single-AZ | Verify each service's actual availability scope |
| Confusing Multi-AZ with Multi-Region DR | Fails to survive a full Region outage | Define failure scenarios and explicit RTO/RPO |
| Having replicas without independent backups | Accidental deletes/corruption propagate to replicas | Maintain immutable/cross-Region backups and test restores |
| Promoting a replica without checking lag | Data loss exceeds RPO | Measure replication lag and confirm acceptability |
| Two Regions writing simultaneously | Split-brain and conflicts | Writer ownership, quorum, and fencing tokens |
| Changing only DNS during failover | Cached DNS and open connections hit the failing Region | Routing plan, TTL tuning, connection retries, and health checks |
| Retrying POST after timeout without idempotency | Duplicate side effects | Stable keys and reconciliation |
| Replaying entire queues without checkpoints | Duplicate or out-of-order processing | Event IDs, inbox/outbox, and ordering guards |
| Restarting workflows from scratch | Re-executes already committed side effects | Durable checkpoints and controlled resume |
| Failing back immediately once old Region reports healthy | Data loss or writer conflicts | Reconcile, fence, and run canary failback |
| Neglecting KMS/IAM/secrets in target Region | Data cannot decrypt or functions fail to run | DR security readiness testing |
| Checking only process liveness in health checks | Endpoint responds while business operations fail | Capability-based readiness and synthetic transactions |
| Skipping restore/failover drills | Actual RTO misses targets | Periodic game days and restore tests |

## 28. Workflow for building an HA/DR plan

1. **Build an inventory:** Functions, APIs, databases, queues, streams, caches, workflows, networks, identities, secrets, and external dependencies.
2. **Map failure domains:** Identify which components are zonal, regional, global, or external.
3. **Classify business flows:** Reads, writes, payments, notifications, reporting, and background jobs.
4. **Set RTO/RPO:** Drive targets by business impact and per-capability needs, not one blanket number.
5. **Design Multi-AZ:** Eliminate single-AZ dependencies for services requiring HA.
6. **Choose a DR pattern:** Backup/restore, pilot light, warm standby, hot standby, or active-active.
7. **Design data plane:** Replication, consistency, writer ownership, fencing, and backups.
8. **Design event plane:** Idempotency, outbox, queue routing, DLQs, and replay.
9. **Prepare standby Region:** Code, config, IAM, KMS, secrets, quotas, networking, and observability.
10. **Automate failover:** Runbooks, approvals, promotion, routing, and capacity scaling.
11. **Design failback:** Reconcile data, shift writer ownership, and phase traffic back.
12. **Test:** AZ failures, Region loss, network partitions, restores, replays, and post-failover load.
13. **Measure outcomes:** Actual RTO/RPO, data loss, error rates, and business completion.
14. **Iterate:** Update architecture and runbooks whenever dependencies or quotas change.

## 29. Production checklist

- **Failure domains:** Process, AZ, Region, global services, and external dependencies are classified.
- **Multi-AZ:** Compute, databases, caches, queues, and network paths are properly configured.
- **RTO/RPO:** Business-approved targets exist for each capability.
- **Databases:** Sync/async replication, failover endpoints, connection recovery, and transaction outcomes are understood.
- **Multi-Region:** DR pattern selected based on RTO/RPO and budget.
- **Writer ownership:** Primary authority, fencing/epochs, and split-brain protections are enforced.
- **Consistency:** Read-after-write, conflict resolution, and replication lag tolerances are defined.
- **Idempotency:** Event IDs and operation keys remain stable across Regions; external side effects have reconciliation.
- **Queues/workflows:** Replay, DLQs, checkpoints, and resume never duplicate side effects.
- **Routing:** DNS/global load balancers, TTLs, health checks, and client connection behaviors are tested.
- **Security:** IAM, KMS, secrets, certificates, network policies, and auditing are ready in the target Region.
- **Backups:** Independent copies exist and restore drills have measured timings.
- **Capacity:** Standby Region holds sufficient quotas and capacity for failover load.
- **Observability:** Global dashboards, per-Region/AZ metrics, correlated logs/traces, and alerts are live.
- **Runbooks:** Cover detect, declare, fence, promote, route, verify, communicate, and failback.
- **Testing:** Rehearsed AZ failure, Region failover, network partition, queue replay, and restore.
- **Cost:** Accounted for replicas, warm capacity, data transfer, backups, telemetry, and drill expenses.

## 30. Conclusion

Multi-AZ reduces the blast radius of outages within a single Region; Multi-Region extends resilience when an entire Region fails or when serving users across geographies. The two strategies address different failure domains and are not interchangeable. Serverless functions are only part of the architecture: databases, queues, networks, identities, secrets, workflows, and external providers must all be included in the analysis.

Start from business impact, RTO, and RPO, then choose backup/restore, pilot light, warm standby, hot standby, or active-active. Multi-Region architectures require careful design of replication, consistency, writer ownership, fencing, idempotency, and routing. Without controlling those elements, failover can turn an availability incident into data loss or corruption.

An HA/DR plan is only trustworthy once rehearsed: test AZ failures, Region outages, database promotions, queue replays, workflow resumes, backup restores, and failback. Measure real RTO/RPO, monitor per Region, and maintain up-to-date runbooks so Java serverless applications recover cleanly when any failure domain goes dark.
