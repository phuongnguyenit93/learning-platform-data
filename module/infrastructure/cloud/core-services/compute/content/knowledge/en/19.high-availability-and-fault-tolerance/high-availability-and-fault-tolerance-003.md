# Replicating Workloads Across Zones and Avoiding Single Points of Failure

An application may run smoothly on multiple virtual machines yet still go down if all machines reside in the same Availability Zone, depend on a single load balancer, or share a single standalone database. Replicating workloads only delivers high availability when replicas are placed across independent failure domains and shared components also have redundancy plans.

**Multi-zone workload replication** is the practice of deploying multiple replicas of an application or service across different Availability Zones within the same region. When one zone experiences an outage, replicas in the surviving zones continue serving traffic. The design must coordinate placement, load balancing, health checks, data replication, spare capacity, and failover procedures.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module, chapter **High Availability and Fault Tolerance**. The content focuses on distributing workloads across zones, identifying Single Points of Failure (SPOFs), choosing active-active or active-passive models, protecting stateful data, and testing resilience.

## 1. Failure Domains and Availability Zones

A failure domain is the scope within which a fault can simultaneously impact one or more components. Examples include:

- A process or container.
- A virtual machine or physical machine.
- A rack or group of hosts.
- An Availability Zone.
- A region.
- A cloud provider or external service.

An Availability Zone (AZ) is a distinct infrastructure zone within a cloud region. Zones are engineered to reduce fault correlation by isolating components such as power, cooling, and networking. However, zones may still share certain regional services or control planes. Therefore, do not assume two zones have zero shared dependencies whatsoever.

A region typically contains multiple AZs. Placing workload replicas across multiple AZs helps an application survive certain zone-level outages without failing over the entire system to another region.

### 1.1. Distinguishing Multi-Instance, Multi-Zone, and Multi-Region

| Model | Redundancy Scope | Tolerates | Cost and Complexity |
|---|---|---|---|
| Multi-process | Multiple processes on one host | Single process failure | Low, but the host remains an SPOF |
| Multi-instance, same zone | Multiple VMs in one zone | Single VM or partial host failure | Moderate; cannot tolerate a zone outage |
| Multi-zone, same region | Multiple replicas across AZs | A zone disruption within design limits | Higher; requires distributing traffic and data |
| Multi-region | Multiple regions | A region disruption | Complex; higher cost and replication latency |

Multiple VMs in the same AZ do not provide zone fault tolerance. If all VMs, databases, and load balancers depend on the same zone, a zone outage can still take down the service.

### 1.2. Identifying Failure Boundaries Before Designing

List all components and ask: if this component or failure domain goes down, will the service keep working?

- If one VM fails, can other replicas absorb the load?
- If one AZ loses connectivity, does traffic shift to the remaining AZs?
- If a subnet or NAT gateway fails, can the application still reach required dependencies?
- If the primary database fails, is there a sufficiently up-to-date replica to promote?
- If DNS, identity, or secret manager services experience issues, can workloads keep processing?

HA design starts by defining what must continue operating and what level of degradation is acceptable.

## 2. Availability, Redundancy, and Fault Tolerance

These three concepts are related but distinct:

- **Availability:** the probability or percentage of time a service is ready to respond to requests.
- **Redundancy:** having backup components to take over when a primary component fails.
- **Fault tolerance:** the ability to continue operating when one or more defined faults occur, either uninterrupted or within bounded degradation.

Having two VMs does not automatically mean fault tolerance. If both read from a single storage volume, share a single database, or depend on a single network path, a common point of failure still exists.

### 2.1. Active-Active

In an active-active model, multiple replicas process traffic or work concurrently. A load balancer distributes requests across healthy replicas.

Advantages:

- Capacity from multiple replicas is utilized under normal conditions.
- When one replica or zone fails, the rest can absorb additional load.
- Well suited for stateless APIs, web services, and parallelizable workers.

Requirements:

- Session state or shared data must be managed appropriately.
- Replicas must be version- and configuration-compatible.
- Remaining capacity must be sufficient after losing a zone or instance group.
- Concurrent write operations need consistency rules and deduplication.

### 2.2. Active-Passive

In an active-passive model, one replica handles primary traffic while the standby replica waits ready or runs in standby mode. When the primary fails, the system promotes or shifts traffic to the standby.

Advantages:

- Well suited for stateful workloads that allow only one writer node at a time.
- Reduces the need to resolve concurrent write conflicts.
- Can reduce costs if the standby runs at lower capacity and scales up on failover.

In return, fault detection, promotion, state synchronization, and route updates can increase recovery time. The standby must be tested periodically to verify it is genuinely ready.

### 2.3. Comparing the Models

| Criterion | Active-Active | Active-Passive |
|---|---|---|
| Normal traffic serving | Multiple replicas | Primarily one replica |
| Failover transition | Remove failed replica from distribution | Promote or activate standby |
| Capacity utilization | Higher under normal operations | Standby may sit underutilized |
| State handling | Requires concurrency design and idempotency | Requires synchronization and primary switchover procedures |
| Best-fit use cases | Stateless APIs, web apps, distributed workers | Primary/standby databases, single-writer systems |

Both models can be combined: APIs run active-active across multiple AZs, while the database runs primary/standby with replication and controlled failover.

## 3. Distributing Workloads Across Multiple Zones

A basic multi-zone architecture places application replicas in subnets belonging to different AZs. A load balancer or orchestration layer routes traffic to healthy replicas.

~~~mermaid
flowchart TB
    U["User / Client"] --> DNS["DNS / Global entry"]
    DNS --> LB["Regional Load Balancer"]
    LB --> A1
    LB --> A2
    LB --> A3
    subgraph Z1["Availability Zone A"]
      A1["App replica A1"]
      W1["Worker A"]
    end
    subgraph Z2["Availability Zone B"]
      A2["App replica B1"]
      W2["Worker B"]
    end
    subgraph Z3["Availability Zone C"]
      A3["App replica C1"]
      W3["Worker C"]
    end
    A1 --> DB["Multi-zone Database"]
    A2 --> DB
    A3 --> DB
    W1 --> Q["Durable Queue"]
    W2 --> Q
    W3 --> Q
~~~

The diagram illustrates a region with three zones. The actual number of zones depends on the region and service. Some managed services automatically distribute data or endpoints; others require customers to configure subnets, replicas, and routing manually.

### 3.1. Placing Replicas in Different AZs

When creating VMs or node pools:

- Select subnets across multiple AZs.
- Spread instance groups or autoscaling groups across those subnets.
- Avoid pinning all replicas to a single AZ.
- Use anti-affinity or topology spread constraints for Kubernetes workloads.
- Verify the scheduler has sufficient capacity in the remaining zones.
- Check quotas and instance family limits per AZ.

Do not look solely at instance counts. Verify the actual AZ placement of each replica via metadata or cloud inventory.

### 3.2. Traffic Distribution

The load balancer must:

- Check backend health using an endpoint that reflects actual serving capability.
- Stop routing requests to unhealthy replicas.
- Have backends across multiple AZs.
- Maintain appropriate connections and timeouts.
- Support draining during deployments or scale-in.
- Have a plan when one zone loses all backends.

A health check that only verifies the process is alive may be insufficient. An API can return HTTP 200 on a health endpoint while unable to reach its database or critical dependency. Separate liveness from readiness and choose check depth carefully to avoid pulling all replicas out of service merely because a non-critical dependency is degraded.

### 3.3. Cross-Zone Load Balancing

Some load balancers route traffic only to backends in the same AZ; others support cross-AZ distribution. This behavior impacts capacity utilization and data transfer costs.

If cross-zone is disabled, an AZ with fewer backends can become overloaded even while other AZs have spare capacity. If enabled, traffic may cross AZs and incur network charges or latency. Understand your load balancer's policy and test behavior when an AZ is taken out of service.

## 4. Capacity Planning for Losing a Zone

A multi-zone system must retain sufficient capacity after losing the largest failure domain it commits to surviving. If three zones each run at 33% load with no spare capacity, losing one zone forces the remaining two zones to take on 50% more load than before.

Example: a system requires 900 requests/second. Distributed evenly across three AZs, each zone serves 300 requests/second. When one zone is lost, the remaining two zones must each serve 450 requests/second. If each zone has a maximum capacity of only 350 requests/second, the system will overload during an outage.

### 4.1. Basic Capacity Formula

Let N be the number of AZs running the workload, F be the number of AZs that can be lost in the design scenario, C be the maximum capacity per AZ, and D be peak demand. The minimum requirement is:

~~~text
(N - F) * C >= D
~~~

With three AZs and a goal of tolerating one AZ failure, each AZ needs capacity equal to at least half of total system demand assuming even load distribution. In practice, add headroom for uneven traffic, failover, deployments, and performance variance.

### 4.2. Autoscaling Does Not Replace Spare Capacity

Autoscaling can launch additional instances after load rises, but provisioning takes time and can fail if remaining AZs lack quota or capacity. A design must define:

- Minimum capacity always kept running.
- Maximum capacity and quotas per AZ.
- Application startup and warm-up time.
- Capacity immediately available after one AZ is lost.
- Autoscaling speed and instance launch rate limits.
- Ability to pull images, fetch secrets, and connect to dependencies during scaling.

If the SLO does not allow waiting for post-incident autoscaling, keep N+1 capacity or equivalent headroom pre-provisioned.

### 4.3. Workloads Capable of Graceful Degradation

When remaining capacity cannot support every feature, the system can prioritize:

- Keeping critical endpoints and core transactions running.
- Shedding background jobs or non-urgent analytics tasks.
- Applying per-tenant request limits or rate limiting.
- Temporarily disabling non-essential features.
- Using queues to accept work that can be processed more slowly.

Controlled degradation is better than letting every component keep accepting load until everything collapses.

## 5. Replicating Stateless Workloads

Stateless workloads do not keep unique session state or business data in a single replica's local memory. Any healthy replica can handle any request.

To run statelessly across multiple zones:

- Move sessions to a shared store or use independently verifiable tokens.
- Store uploaded files and outputs in object storage or appropriate shared storage.
- Store configuration and secrets in a centralized management service with appropriate availability.
- Use durable queues for asynchronous work.
- Ensure requests can be safely retried when clients do not know whether a previous replica completed them.
- Never rely on an instance's local disk as the sole storage location.

### 5.1. Sessions and Sticky Sessions

Sticky sessions keep a client pinned to the same backend for a period of time. This can help some legacy applications, but reduces the ability to freely reroute requests when a backend or AZ fails.

Whenever possible, externalize sessions to a shared store or use stateless tokens. If sticky sessions must be used, define behavior when a backend is lost and when users must re-authenticate.

### 5.2. Local Cache

Local caches reduce latency and database load, but should not be the sole authoritative data source. When a new replica launches in another AZ, its cache will be cold; manage cache warm-up, TTLs, invalidation, and database load spikes from cache misses.

If all replicas restart together and populate caches simultaneously, they can cause a thundering herd. Use jitter, request coalescing, rate limiting, or staged warm-up.

## 6. Replicating Stateful Workloads and Protecting Data

Stateful workloads must persist state across calls. Examples include databases, message brokers, distributed caches, file services, and storage systems.

Stateful workloads can be replicated via:

- Application-level or database-level replication.
- Cloud-provider-managed storage with multi-AZ replication.
- Clusters with quorum and leader election.
- Durable queues with distributed brokers or storage.
- Snapshots/backups stored in a separate failure domain.

Not all data requires millisecond-level synchronization. Choices depend on RPO, RTO, latency, consistency model, and cost.

### 6.1. Synchronous Replication

Synchronous replication typically acknowledges writes only after data is written to replicas meeting the system's commit condition. It can minimize data loss when a primary fails, at the cost of higher write latency and dependence on inter-zone connectivity.

When inter-zone networking slows down or partitions, the system may reject writes or reduce availability to preserve consistency. This is a trade-off that must be evaluated per database and business requirement.

### 6.2. Asynchronous Replication

Asynchronous replication lets the primary acknowledge writes before replicas receive all data. Latency is usually lower, but if the primary fails abruptly, un-replicated transactions may be lost during failover.

Replication lag must be measured and alerted on. A replica may appear online yet lag too far behind to be promoted safely.

### 6.3. Quorum and Split-Brain

Some distributed systems require quorum to decide which node holds commit or leadership authority. With three independent voters, quorum typically requires a majority—two voters. If one node is lost, the remaining two nodes can still reach quorum.

Split-brain occurs when both sides of a network partition believe they are the primary and accept writes concurrently. The result can be conflicting or irreconcilable data.

To prevent split-brain:

- Use consensus/quorum mechanisms supported by the system.
- Enforce leader election with explicit leases or terms/epochs.
- Fence the old node before promoting a new node.
- Never auto-promote a replica solely on a timeout without verifying the old primary's state.
- Test network partitions and recovery.

Do not invent custom quorum or fencing algorithms using ad-hoc scripts for production databases. Use the database's official HA mechanism or a managed service.

## 7. Multi-Zone Databases

The database is often an application's most critical dependency. If the API is replicated across three AZs while the database has only one instance in AZ A, the database remains an SPOF.

Common models:

- Provider-managed multi-AZ database with managed standby or replication.
- Database cluster with primary and replicas across multiple AZs.
- Distributed database with quorum.
- Self-managed primary/secondary.

When selecting a model, verify:

- Are replicas placed in different AZs?
- Is replication synchronous or asynchronous?
- Are fault detection and promotion automatic or manual?
- Does the endpoint automatically switch to the new primary?
- Do DNS caches and connection pools refresh after failover?
- How does the application handle open transactions and retries?
- Can the system recover if both primary and replica fail?

### 7.1. Database Failover

Failover typically involves detecting an unresponsive primary, verifying an eligible replica, fencing the old primary, promoting the replica, updating the endpoint, and letting applications reconnect.

During the transition:

- Existing connections may drop.
- Uncommitted transactions may roll back.
- Some requests may time out even though the transaction committed in the database.
- Clients may retry and cause duplicate writes without idempotency.

Applications need connection retries with backoff, clear transaction boundaries, and idempotency keys for retryable business operations.

### 7.2. Backups Do Not Replace Replication

Replication maintains a near-real-time copy and supports failover. Backups restore data after accidental deletion, malware, logic bugs, or corruption that has been replicated to standbys.

If a record is deleted by mistake and the deletion replicates, the replica can lose that record too. Therefore, keep independent backups with appropriate retention, immutable or protected copies, and regular restore tests.

## 8. Avoiding SPOFs in Dependent Components

A system with many app replicas can still fail because of one shared component. Build a dependency map from client to backend and inspect every hop.

| Component | Potential SPOF | Risk Mitigation |
|---|---|---|
| Load balancer | Single self-managed appliance or endpoint | Use an HA managed load balancing service or multi-entry layer |
| DNS | Single resolver or misconfigured zone | Use HA managed DNS, multiple authoritative endpoints, and record validation |
| Database | Single primary without eligible replicas | Multi-AZ replication, failover, and independent backups |
| Storage | Single volume or file server | Multi-AZ storage, replication, or per-zone mount targets |
| Queue/broker | Single broker or node | Managed cluster/broker with durability and replication |
| NAT/egress | Single NAT gateway or router in one AZ | Redundant egress paths, per-zone NAT, or failover routing |
| Identity/secrets | Single endpoint or secret service without caching/HA | Use managed services, design safe refresh and caching |
| KMS/encryption | Key policy or endpoint outage blocking data reads | Redundant endpoints, access policies, and key recovery procedures |
| Monitoring | Single collector | Multiple collectors or buffered telemetry pipelines |
| Deployment pipeline | Single runner or artifact server | Distributed runners and durable artifact storage |

Not every dependency must be replicated by the customer. Many managed services already include internal HA, though you must confirm their scope, SLA, behavior during a zone outage, and associated quotas.

### 8.1. Network Paths and Egress

An application in AZ B may still depend on a NAT gateway in AZ A to call external APIs. If AZ A goes down, the app in AZ B stays up yet loses outbound connectivity.

For workloads that must operate independently per AZ, consider:

- Per-AZ NAT gateways or egress paths.
- Route tables that do not point every subnet to a single appliance.
- Private endpoints or service endpoints where appropriate.
- DNS resolvers and network firewalls with appropriate availability.
- Testing dependency reachability from each AZ.

### 8.2. DNS and Service Discovery

DNS can become an SPOF or cause slow failover if TTLs are too long, resolvers become unavailable, or health checks fail to update records properly. Verify:

- Does the DNS record point to a regional load balancer or a single instance IP?
- Do TTLs and client caches delay switchover?
- Are resolvers provided per region/AZ or self-operated?
- Does service discovery remove unhealthy endpoints promptly?
- Do clients retry when stale addresses remain cached?

Do not use simple DNS round-robin as the sole HA mechanism for applications needing controlled failover.

## 9. Kubernetes: Spreading Pods Across Multiple Zones

Kubernetes can place multiple Deployment replicas on different nodes, yet if the scheduler places all Pods in the same zone, the workload still has an AZ-level SPOF.

### 9.1. Topology Spread Constraints

Topology spread constraints distribute Pods by a topology key, such as zone or hostname.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 6
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: catalog-api
      containers:
        - name: api
          image: registry.example/catalog-api:v3
          ports:
            - containerPort: 8080
~~~

With six replicas and three zones having capacity, the scheduler can balance them evenly, typically two Pods per zone. Actual placement also depends on node labels, node affinity, taints/tolerations, and per-zone capacity. `DoNotSchedule` can leave Pods `Pending` if the spread condition cannot be satisfied; evaluate behavior when a zone is already down.

### 9.2. Pod Anti-Affinity

Pod anti-affinity prevents replicas of the same application from being scheduled on the same node or zone by topology key. Hard anti-affinity strengthens isolation but can leave Pods unschedulable when suitable nodes are scarce. Soft preferences are more flexible but do not guarantee strict dispersion.

Choose constraint strictness based on availability targets and actual capacity. Topology spread constraints are often preferable when aiming to balance Pod counts evenly across zones.

### 9.3. PodDisruptionBudget

A PodDisruptionBudget (PDB) limits how many Pods can be disrupted during certain voluntary disruptions such as node drains. PDBs protect replica availability during maintenance, but do not prevent abrupt node or zone failures and do not create extra capacity.

Design PDBs alongside replica counts, topology spread, autoscaling, and maintenance workflows. Never treat a PDB as proof that an application can survive losing a zone.

### 9.4. Node Pools and Clusters

Node pools should span nodes across multiple AZs. Verify:

- Node labels accurately reflect their zone.
- The autoscaler can provision nodes in zones with remaining capacity.
- Persistent volumes have compatible topology.
- Pods can be rescheduled when a zone is lost.
- Ingress/load balancers have backends in the remaining zones.
- The cluster control plane and API endpoint use a provider-supported HA model.

A persistent volume bound to a single zone may not move instantaneously to another zone. Stateful workloads need storage and database architectures that support failover, rather than relying solely on Pod rescheduling.

## 10. StatefulSets, Volumes, and Zone-Scoped Data

A Kubernetes StatefulSet provides stable network identity and ordering for Pods, yet StatefulSet itself does not replicate data. If each Pod uses a persistent volume in one zone, moving a Pod across zones may be blocked by volume topology.

For databases or brokers:

- Use a vendor-supported operator or clustering mechanism.
- Place replicas across multiple zones and verify quorum.
- Determine whether volumes can attach across zones or require separate copies.
- Monitor replication lag and leader status.
- Test node/zone failures and restores.

Never run multiple database Pod replicas sharing a single writable volume unless the database engine explicitly supports that mode. Storage replication and database replication are distinct layers and must follow the product's architecture.

## 11. RTO, RPO, and Recovery Targets

HA design requires measurable targets:

- **RTO (Recovery Time Objective):** the maximum acceptable time to restore service after an outage.
- **RPO (Recovery Point Objective):** the maximum acceptable data loss, typically expressed as a time window of data.

Examples:

- A stateless API may achieve an RTO of a few minutes if surviving replicas quickly absorb traffic.
- A synchronous multi-AZ database may achieve a very low RPO under supported conditions, though service semantics and failure modes must still be confirmed.
- Daily backups may yield an RPO of nearly one day if no log shipping or other replication exists.

RTO/RPO must derive from business requirements, not from the capabilities of a single component.

### 11.1. Phases Making Up RTO

RTO can be broken down into intervals:

~~~text
RTO = T_detect + T_decide + T_promote + T_route + T_verify
~~~

Where:

- `T_detect`: time to detect the failure.
- `T_decide`: time to decide or trigger failover.
- `T_promote`: time to start or promote replicas.
- `T_route`: time to switch traffic or connections.
- `T_verify`: time to verify service recovery.

Measuring each segment reveals what slows failover down. If DNS caching dominates recovery time, adding more application replicas will not improve RTO.

### 11.2. RPO and Replication Lag

With asynchronous replication, actual RPO depends on the data transmitted and acknowledged at the moment the primary fails. Track replication lag, WAL/binlog/stream offsets, or equivalent metrics. Do not merely check whether a replica reports healthy; verify data freshness before promoting.

### 11.3. Restore Testing

Backups are only valuable if they can be restored. Practice:

- Restoring the database from backup.
- Applying transaction logs or point-in-time recovery where available.
- Restoring files/objects and access permissions.
- Launching workloads from backup images.
- Verifying data and business functionality.

Record actual restore times and compare them against committed RTO/RPO targets.

## 12. Failover and Failback

Failover shifts workloads to a backup component or zone when the primary fails. Failback returns the system to normal operation or its preferred location after the outage is resolved.

### 12.1. Automatic vs. Manual Failover

Automatic failover reduces response time but risks false positives if health checks are overly sensitive or a network partition leaves the primary running yet unobservable. Manual failover lowers the risk of wrong decisions but increases RTO due to human involvement.

You can automate failover for faults with reliable signals and tested procedures, while requiring manual approval for actions carrying data-loss or split-brain risk.

### 12.2. Application Failover Flow

1. Health checks determine a replica or zone is no longer serving.
2. The load balancer stops sending traffic to failed backends.
3. Surviving replicas absorb additional requests within capacity limits.
4. The autoscaler adds capacity if needed and if quotas allow.
5. Monitoring confirms latency, error rate, and saturation.

### 12.3. Database Failover Flow

1. Detect primary failure via health checks and consensus mechanisms.
2. Verify an eligible, sufficiently up-to-date replica to become primary.
3. Fence the old primary or ensure it cannot continue writing.
4. Promote the replica following the database's procedure.
5. Update the endpoint and allow connection pools to reconnect.
6. Verify transactions, replication, and consistency.
7. Monitor the system before restoring redundancy topology.

### 12.4. Failback Requires Planning

Do not shift traffic back to a newly recovered zone the moment machines respond to ping. You must:

- Confirm the root cause of the outage has been resolved.
- Synchronize data back to the recovered node/zone.
- Check replication lag and primary/standby roles.
- Verify capacity and networking.
- Shift traffic incrementally.
- Monitor metrics and be ready to roll back if errors recur.

## 13. Commonly Overlooked Single Points of Failure

An architecture that appears multi-zone can still harbor SPOFs in the following areas:

### 13.1. A Broken Shared Configuration or Secret

If all replicas load a bad configuration or an expired secret simultaneously, all zones can fail at once. Use config versioning, controlled rollouts, secret rotation testing, and rollback capability.

### 13.2. A Broken Image Rolled Out Everywhere

Multi-zone provides no protection if the same faulty image is deployed to every AZ simultaneously. Use canaries, rolling deployments, health gating, and rollout halt controls.

### 13.3. A Single External Service

The application may depend on an external payment, email, or identity provider API. Define behavior when that dependency fails: timeouts, retries, queuing, fallbacks, or degraded mode.

### 13.4. A Single Egress Path

Subnets across multiple AZs may all route out through a single NAT gateway. If that gateway or its AZ fails, all workloads lose outbound connectivity. Audit route tables and design per-zone egress.

### 13.5. A Single Operator or Operational Process

A runbook understood by only one person, untested break-glass credentials, or a deployment pipeline tied to a single runner can also slow recovery. Document procedures, assign appropriate access, and drill on-call teams.

## 14. Testing Fault Tolerance

You cannot conclude a system is HA from an architecture diagram alone. Induce controlled faults and measure actual behavior.

Tests to run:

1. Stop a VM or Pod.
2. Drain a Kubernetes node.
3. Temporarily disable backends in one AZ in a test environment.
4. Simulate a primary database failover.
5. Check replication lag before and after failover.
6. Cut a network path or egress dependency in a test environment.
7. Slow down DNS or a dependency to test timeouts and retries.
8. Scale workloads under high load while one AZ is removed.
9. Test backup restores in a separate failure domain.
10. Test failback after the zone recovers.

### 14.1. Pass Criteria

- Surviving workloads receive traffic according to health policy.
- Remaining capacity stays below saturation thresholds.
- Error rates and latency stay within targets or recover within RTO.
- Data loss stays within RPO.
- No split-brain or uncontrolled duplicate writes occur.
- Alerts detect the incident and runbooks guide the right steps.
- Failback causes no unexpected disruption or data loss.

### 14.2. Chaos Engineering

Chaos engineering proactively injects faults into a system to test fault-tolerance hypotheses. Start small in test or canary environments, with blast-radius limits, abort conditions, and an accountable owner.

Never shut down an entire production AZ for the first time just to see if the system survives. Build progressive drills, run game days, and expand scope only after controls prove effective.

## 15. Observability for Multi-Zone Systems

HA dashboards should show status both per zone and across the entire service:

- Healthy replica count per AZ.
- Request rate and traffic share per AZ.
- CPU, memory, network, and queue depth per AZ.
- Unhealthy backends and health check durations.
- Database primary/replica roles and replication lag.
- Failover events and per-phase durations.
- Error rate, p95/p99 latency, and SLOs.
- Remaining capacity when one zone is removed.
- Status of NAT, DNS, storage endpoints, and critical dependencies.

Avoid showing only region-wide aggregates. If AZ A is overloaded while AZ B sits idle, global averages can mask the issue.

### 15.1. Per-Zone Alerting

Alert when:

- An AZ has zero healthy replicas left.
- Traffic distribution becomes abnormally skewed.
- Replica count drops below the fault-tolerance threshold.
- Remaining capacity is insufficient to survive losing a zone.
- Replication lag exceeds business thresholds.
- Database failover or leader election stalls.
- A critical network/egress path loses redundancy.

### 15.2. SLOs and Error Budgets

Measure availability by successful requests and service SLO targets. A VM showing healthy while every request times out against the database does not mean the application is available. SLOs should reflect user behavior and critical transactions.

## 16. Example Architecture: E-Commerce API Across Three AZs

A retail system must serve catalog and order APIs continuously. Reference architecture:

| Component | Design | Goal |
|---|---|---|
| Entry point | Regional load balancer | Accept traffic and check backend health |
| API | Six replicas, spread two per AZ | Survive losing one AZ and keep serving |
| Worker | Multiple workers reading a durable queue | Asynchronous processing and load distribution |
| Database | Managed multi-AZ database or cluster with failover | Preserve data and write endpoint |
| Session | Tokens or shared session store | No dependence on local memory |
| File | Object storage with service durability/replication | No unique files on VMs |
| Egress | Per-AZ NAT/routes or private endpoints | Avoid a single outbound path |
| Observability | Per-zone metrics, logs, and alerts | Detect load skew and failover |

In a scenario where AZ B goes down:

1. The load balancer stops sending traffic to backends in AZ B.
2. The four replicas in AZ A and C absorb the requests.
3. The system checks capacity; if needed, the autoscaler launches instances in the two surviving AZs.
4. Workers continue pulling messages from the durable queue.
5. The multi-AZ database fails over if the primary was in AZ B.
6. The API handles connection resets and retries safely.
7. Monitoring confirms latency, error rate, database role, and queue depth.

The architecture meets its goal only if the four remaining replicas have enough capacity, the database can fail over, egress does not rely on AZ B, and secrets/configurations remain accessible.

## 17. Example Configuration for Multi-AZ VM Distribution

Abbreviated Terraform example for an EC2 Auto Scaling group using subnets across multiple AZs:

~~~hcl
resource "aws_launch_template" "api" {
  name_prefix   = "catalog-api-"
  image_id      = var.approved_ami_id
  instance_type = "m6i.large"

  user_data = base64encode(var.bootstrap_script)
}

resource "aws_autoscaling_group" "api" {
  name                = "catalog-api-multi-az"
  min_size            = 6
  desired_capacity    = 6
  max_size            = 12
  vpc_zone_identifier = var.private_subnet_ids

  launch_template {
    id      = aws_launch_template.api.id
    version = "$Latest"
  }

  health_check_type         = "ELB"
  health_check_grace_period = 180

  target_group_arns = [var.api_target_group_arn]
}
~~~

In this example, private subnets are passed from multiple AZs and the group maintains at least six instances. Verify that the subnet list actually spans distinct AZs; passing multiple subnets within the same AZ does not create multi-zone distribution.

For production use, add security groups, an IAM instance profile, metadata options, rolling instance refresh, scaling policies, appropriate health checks, and load balancer configuration. Also verify quotas and instance family capacity in each AZ.

### 17.1. What the Example Does Not Guarantee Alone

An Auto Scaling Group distributes instances across subnets, yet does not solve every SPOF by itself:

- The database must have its own HA.
- Storage and uploaded files must reside outside local disks.
- Egress paths must be distributed.
- Bootstrapping must pull config and secrets from highly available services.
- The application must be stateless or use session/data replication.
- Health checks must reflect readiness to serve traffic.

## 18. Costs and Trade-Offs of Multi-Zone

Multi-zone increases fault tolerance, as well as cost and complexity:

- Running more VMs/Pods for spare capacity.
- Replication and cross-zone data transfer charges.
- Per-zone load balancers, NAT gateways, or endpoints.
- Storage replicas, database standbys, or licensing.
- Monitoring, backups, and drills.
- Operational overhead for failover/failback procedures.

Do not reduce replica counts below the point of surviving a zone failure purely to save cost if availability targets still require multi-zone. Optimize using autoscaling, right-sized instance families, and capacity policies, while preserving committed headroom.

### 18.1. Optimizing by Criticality

Not every workload needs the same HA tier:

- Core transactional services may require multi-zone and database failover.
- Batch jobs can restart from checkpoints and tolerate a longer RTO.
- Development environments can run fewer replicas.
- Analytical tasks can be prioritized when spare capacity is available.

Classifying by business criticality balances cost against outage impact.

## 19. Common Mistakes

- **Running multiple VMs in one AZ and calling it multi-zone:** the entire workload can still go down when that zone fails.
- **Replicating only the application tier:** the database, storage, NAT, or DNS remains an SPOF.
- **Failing to size capacity for losing a zone:** surviving replicas overload immediately upon failover.
- **Using process-only health checks:** backends appear healthy yet cannot serve business requests.
- **Keeping sessions in one replica's RAM:** requests after failover lose sessions or force re-login.
- **Assuming autoscaling is instantaneous:** new capacity may take minutes or fail due to quotas.
- **Not monitoring replication lag:** promoting a stale replica can lose data beyond RPO.
- **Failing to fence the old primary:** can cause split-brain.
- **Treating PDBs as zone-failure protection:** PDBs mainly govern voluntary disruptions, not abrupt zone outages.
- **Assuming StatefulSets automatically replicate data:** Pod replicas do not mean data is replicated.
- **Not testing failback:** shifting traffic back can trigger a second outage.
- **Viewing only region-wide metrics:** failing to spot a single overloaded zone or missing replicas.

## 20. Multi-Zone Design and Testing Checklist

Before promoting a workload to production, confirm:

- [ ] Replicas actually reside in at least two independent AZs.
- [ ] The load balancer has healthy backends in multiple AZs.
- [ ] Health checks and readiness reflect serving capability.
- [ ] Remaining capacity is sufficient when losing one AZ under the chosen scenario.
- [ ] Autoscaling has quotas and subnets in surviving AZs.
- [ ] Sessions, files, and application state do not rely on a single VM's local disk/memory.
- [ ] The database has replication and failover aligned with RPO/RTO.
- [ ] Quorum/fencing or anti-split-brain mechanisms exist for leader-based systems.
- [ ] Independent backups and restores have been tested.
- [ ] DNS, NAT/egress, secrets, identity, queues, and storage do not introduce hidden SPOFs.
- [ ] Kubernetes uses appropriate topology spread/anti-affinity and nodes across multiple zones.
- [ ] Alerts and dashboards show health per AZ.
- [ ] VM, node, AZ loss, and failback have been drilled in a safe scope.
- [ ] Runbooks, owners, and escalation paths are defined.

## 21. Implementation and Maintenance Process

You can follow this workflow:

1. **Define SLOs:** agree on availability, RTO, and RPO with business owners.
2. **Build a dependency map:** list apps, databases, storage, networking, DNS, identity, and external services.
3. **Identify failure domains:** choose the AZs and failure scenarios to tolerate.
4. **Design placement:** spread VMs, Pods, workers, and database replicas.
5. **Calculate capacity:** confirm surviving capacity handles load after losing a zone.
6. **Design data protection:** select appropriate replication, quorum, backups, and consistency.
7. **Design traffic routing:** configure health checks, routing, draining, and retries.
8. **Test:** simulate faults layer by layer and measure RTO/RPO.
9. **Operate:** monitor per-zone metrics, replication lag, and capacity headroom.
10. **Review periodically:** check for new SPOFs introduced by architecture, routing, or dependency changes.

## 22. Key Takeaways

Replicating workloads across multiple zones reduces the risk of a single infrastructure outage taking down the entire service. However, HA is only truly effective when placement, load balancing, capacity, data, and critical dependencies are all designed for fault tolerance.

Stateless workloads generally fit active-active; stateful workloads require replication, quorum, fencing, and clear failover procedures. Calculate post-zone-loss capacity, protect databases with replication and independent backups, check DNS/NAT/identity/secrets/queues, and drill both failover and failback. Measure actual RTO, RPO, latency, and error rates to prove the system meets its availability targets.
