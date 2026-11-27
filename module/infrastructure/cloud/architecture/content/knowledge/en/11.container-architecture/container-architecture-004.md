# Scheduling, Workload Placement, and Anti-Concentration Across Failure Domains

## 1. Why Does Where Containers Run Matter?

A containerized application may have multiple replicas, yet a large replica count **does not automatically equal high availability**. If all replicas reside on the same node, rack, or availability zone, a failure in that domain can take down the entire service. Even when distributed evenly, the application can still become unavailable if all replicas depend on a single database, storage volume, network gateway, or control plane.

**Workload scheduling** determines which compute resources a workload is placed on. **Workload placement/spreading** determines how replicas are distributed across nodes, zones, or failure domains. Proper design combines both to balance:

- Satisfying CPU, memory, GPU, storage, and networking resources.
- Availability, node/zone fault tolerance, and recovery time.
- Latency between workloads and data or dependent services.
- Resource utilization, cost, and scalability.
- Security, compliance, operational policies, and deployment lifecycles.

In the **CLOUD_ARCHITECTURE** module, choosing container compute and deployment models must start from business requirements, then validate trade-offs across **reliability, security, performance, scalability, cost, and operations** using a Well-Architected mindset.

Running example: a booking platform consisting of web, search, booking, workers, and a database. A promotional campaign surges search traffic; simultaneously, the team needs to upgrade nodes or an availability zone goes down. The goal is to continue serving critical user journeys without letting a single failure domain take down all replicas or introducing additional risk to transactional data.

## 2. Key Concepts to Align On

### 2.1. Workloads, Replicas, and the Scheduler

- **Workload** is the deployed unit of work, such as a Deployment, StatefulSet, Job, or a containerized service.
- **Replica** is a copy of a workload. Replicas can run on different nodes, but do not inherently have independent data or availability if a shared dependency fails.
- **Node** is a machine (VM or bare-metal server) that a container platform uses to run Pods/containers.
- **Scheduler** selects an eligible node for an unassigned workload based on resources, constraints, policies, and cluster state.
- **Placement policy** is a set of rules guiding or enforcing how workloads are placed and distributed.

In Kubernetes, `kube-scheduler` evaluates feasible nodes through filtering and scoring phases, then assigns a Pod to a node. The standard scheduler does not inherently understand full business semantics; architects must express required resources and constraints using configuration, node labels, affinity, topology spread, and related mechanisms.

### 2.2. Failure Domains

A **failure domain** is the scope of resources that can be affected simultaneously by the same incident or shared root cause.

| Domain | Example | Potential Impacting Incidents |
| --- | --- | --- |
| Container/process | A single container or process | Process crash, memory error, application bug |
| Pod | A deployment unit in Kubernetes | Pod deletion, node drain, readiness failure |
| Node | A single VM or physical machine | Kernel panic, VM loss, resource exhaustion, NIC failure |
| Rack/host group | Group of servers sharing power, switches, or underlying hardware | Power outage, switch failure, shared maintenance |
| Availability zone | A zone within a region | Power, networking, infrastructure, or zonal service outage |
| Region | A cloud geographic region | Regional outage, widespread control plane failure |
| Shared dependencies | Database, DNS, identity, storage, load balancer | Multiple replicas lose availability simultaneously even while compute remains up |

Not every provider exposes rack/host group details, and a single zone may contain multiple internal physical failure domains. Base your design on the **platform's actual isolation scope and guarantees**, rather than assuming two VMs with different names always sit on independent power supplies or switches.

### 2.3. Spread, Pack, and Constraint Strictness

- **Spread:** prefers or requires replicas to reside across distinct failure domains to reduce the impact of shared faults.
- **Pack:** places workloads close together to conserve resources, reduce inter-component latency, or dedicate nodes to specialized targets.
- **Hard constraint:** a mandatory condition; if no node satisfies it, the workload remains Pending or unscheduled.
- **Soft preference:** a preferred condition; the scheduler attempts to satisfy it, but may relax it when resources or conditions do not allow.

Reliable architectures typically require a **combination**: spreading replicas that need fault tolerance while still packing certain workloads near data or specialized hardware. Document explicitly which requirements are mandatory and which can be relaxed under resource scarcity.

## 3. How Does the Scheduler Make Decisions?

Conceptually, the scheduler picks a feasible node for each workload that satisfies resources and constraints, then optimizes objectives such as load balancing, spreading, utilization, or data locality. The scheduler does not decide architectural goals on behalf of the architect; placement policies express those goals.

| Signal Group | Example | Consequence of Misconfiguration |
| --- | --- | --- |
| CPU/memory requests | Resources used for scheduling and calculating node capacity | Too low causes overcommitment; too high causes Pending Pods and waste |
| Limits | Runtime ceiling on container CPU/memory | Low CPU limits cause throttling; exceeding memory limits can trigger OOM kills |
| Node selector/affinity | Selects nodes by labels, machine types, or attributes | Overly strict rules shrink the pool of eligible nodes |
| Taints/tolerations | Repels non-permitted workloads from nodes or dedicates specialized nodes | Overly broad tolerations allow workloads onto the wrong nodes |
| Pod affinity/anti-affinity | Places workloads near or apart from other workloads | Unfeasible hard constraints when nodes are scarce |
| Topology spread | Balances Pod counts across nodes/zones/topology domains | Wrong selector or topology key causes skewed distribution |
| Volumes and devices | Persistent volume zone, GPU, local disk | Pods cannot run on nodes lacking access to the storage/device |
| Priority/preemption | Prioritizes more critical workloads | Can evict lower-priority workloads and cause disruption |

### 3.1. Requests Differ from Limits

In Kubernetes, `resources.requests` are used by the scheduler to calculate Pod resource demand. `resources.limits` enforce container execution caps based on runtime mechanics and resource types. The two have distinct meanings:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

This declaration tells the scheduler the Pod needs 0.5 CPU and 512 MiB of memory; the container is capped at a maximum of 1 CPU and 1 GiB of memory by configuration. If requests are significantly lower than actual usage, too many Pods can be packed onto the same node, causing resource contention. If requests are too high, the cluster cannot utilize remaining free capacity.

**CPU and memory behave differently when hitting limits.** CPU is typically throttled via cgroup mechanisms; memory cannot be throttled in the same way, and exceeding the limit can result in an OOM kill. Monitor usage, throttling, OOMs, evictions, and latency to tune appropriately.

### 3.2. Total Pod Resources and Overhead

The scheduler evaluates the sum of requests across all containers in a Pod along with certain overheads and configuration attributes. Sidecar proxies, security agents, log collectors, or init containers can push total resource consumption well above estimates based on the application container alone. When designing service meshes or sidecar injection, include this overhead in capacity planning.

Beyond CPU/memory, clusters have limits on Pods per node, ephemeral storage, CNI IP addresses, volume attachments, GPUs, and cloud-level quotas. A node with spare CPU and memory can still reject new Pods due to IP exhaustion or other limits.

## 4. Distributing Replicas Across Nodes and Availability Zones

When a service has multiple replicas, the baseline goal is to avoid placing all replicas inside the same failure domain. This can be applied at multiple levels:

1. **Across nodes:** reduces impact when a node fails or undergoes maintenance.
2. **Across racks/host groups:** reduces shared physical fault risk if the platform exposes corresponding topology.
3. **Across availability zones:** survives certain zone-level outages, while requiring attention to inter-zone network latency and data dependencies.
4. **Across regions:** expands geographic fault tolerance, but complicates data, routing, failover, cost, and RTO/RPO.

~~~mermaid
flowchart TB
    SVC["Booking Service: 6 replicas"]
    SVC --> Z1
    SVC --> Z2
    SVC --> Z3
    subgraph Z1["Availability Zone A"]
      A1["Node A1: 2 replicas"]
    end
    subgraph Z2["Availability Zone B"]
      B1["Node B1: 2 replicas"]
    end
    subgraph Z3["Availability Zone C"]
      C1["Node C1: 2 replicas"]
    end
~~~

This diagram shows a target 2–2–2 distribution. It is only achievable when zones have sufficient resources, the scheduler accurately recognizes topology, nodes reside in the right zones, other constraints do not conflict, and the data tier supports the scenario. **Six replicas across three zones does not mean the database also has three independently writable copies.**

### 4.1. Why Node-Level Anti-Affinity Alone Is Insufficient

If you only specify a rule prohibiting two Pods with the same label on the same node, the scheduler might spread them across multiple nodes that all belong to the same zone. When that zone goes down, every replica is lost. Therefore, you must choose the right topology key and spread domain: hostname, zone, rack, or another domain genuinely provided by the platform.

Conversely, forcing every replica into a different zone can leave Pods Pending if fewer zones are available than replicas or if capacity is exhausted. You must balance ideal distribution, minimum running replicas, and behavior when a failure domain becomes unavailable.

### 4.2. Topology Spread Constraints

Kubernetes supports `topologySpreadConstraints` to control the Pod count skew across topology domains. The following example prioritizes spreading `booking-api` replicas across zones and nodes:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
spec:
  replicas: 6
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: booking-api
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: booking-api
      containers:
        - name: api
          image: example.invalid/booking-api:v1
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
~~~

Explanation:

- `topology.kubernetes.io/zone` requests balancing across zones; `maxSkew` of 1 sets the allowed difference between domains as calculated by the scheduler.
- `DoNotSchedule` prevents the Pod from being scheduled if the spread condition for this rule cannot be satisfied.
- The hostname rule uses `ScheduleAnyway`: the scheduler tries to spread across nodes, but may relax the rule if no eligible option exists.
- `labelSelector` identifies the group of Pods counted in the distribution. The selector must accurately match the target workload, and you must account for any other Pods sharing that label in the topology.

This is an illustrative configuration, not a production-ready manifest. Verify available zones/nodes, ensure topology labels are complete and accurate, check how existing Pods are counted, confirm cluster version support, and test behavior when a zone lacks capacity. When maintaining minimum availability under failure takes precedence, you may need to adjust `whenUnsatisfiable` and constraints to match business requirements.

## 5. Pod Affinity and Anti-Affinity

Topology spread balances replica counts across domains. **Pod affinity/anti-affinity** expresses attraction or repulsion relationships between groups of Pods.

| Mechanism | Meaning | Example |
| --- | --- | --- |
| `podAffinity` | Places Pods near other Pods matching a topology key | Place workers near a cache if latency reduction is critical and concentration risk is acceptable |
| `podAntiAffinity` | Avoids placing Pods of the same group near each other by topology key | Separate two API replicas from sharing the same node or zone |
| `requiredDuringSchedulingIgnoredDuringExecution` | Mandatory rule at scheduling time; does not automatically move running Pods if topology changes | Do not allow two booking replicas on the same hostname |
| `preferredDuringSchedulingIgnoredDuringExecution` | Preference at scheduling time, but may be violated if unfeasible | Attempt to separate replicas across nodes |

Example of hard node-level anti-affinity:

~~~yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: booking-api
        topologyKey: kubernetes.io/hostname
~~~

This rule prevents two Pods labeled `app: booking-api` from being scheduled onto the same node by hostname topology. If the number of available nodes is smaller than the replica count or nodes lack sufficient resources, Pods can remain Pending. In many systems, topology spread with `maxSkew` is more flexible than hard anti-affinity when running multiple replicas across a bounded set of nodes.

**Do not apply hard anti-affinity merely because it sounds safe.** For non-critical workloads or dev environments, preferred rules may suffice. For critical workloads, spread across zones, while clearly understanding how service capacity degrades if a zone is lost.

## 6. Node Affinity, Taints, and Tolerations

Workload placement is not just about fault tolerance; sometimes you need to land the right workload on the right node type:

- GPU nodes for inference/training.
- High-memory nodes for caching or analytics.
- Dedicated nodes for workloads with compliance requirements.
- System nodes for infrastructure components/daemons.
- Nodes with local devices or specific CPU architectures.

### 6.1. Node Labels and Node Affinity

Node labels describe node attributes. `nodeSelector` or node affinity selects nodes based on labels. Example:

~~~yaml
nodeSelector:
  node-pool: general-purpose
~~~

Or use affinity when complex conditions and preferences are needed:

~~~yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: node-pool
              operator: In
              values:
                - general-purpose
                - memory-optimized
~~~

Platform-managed labels (such as zone, region, hostname) should be distinguished from custom user-applied labels. For labels used as security boundaries, protect label modification permissions and consider mechanisms to prevent untrusted nodes from spoofing labels.

### 6.2. Taints and Tolerations

A **taint** on a node repels Pods unless the Pod has a matching **toleration** (with the corresponding effect). A toleration only indicates that the Pod accepts the taint; it does not select the node. Placing Pods onto dedicated nodes typically requires combining taints/tolerations with node affinity/selectors.

For example, GPU nodes carry the taint `workload=gpu:NoSchedule`. Only Pods needing GPUs and permitted to run there declare the matching toleration while also selecting GPU-labeled nodes. This prevents general workloads from filling up specialized compute resources.

Common effects:

- `NoSchedule`: do not schedule new Pods without a matching toleration.
- `PreferNoSchedule`: try to avoid the node, but still schedule if necessary.
- `NoExecute`: may also evict already-running Pods lacking the toleration, depending on timing and configuration.

Do not add overly broad tolerations to every workload; doing so defeats node isolation. Check DaemonSets, system Pods, node conditions, and drain procedures, as taints can alter operational behavior.

## 7. PodDisruptionBudgets and Controlled Maintenance

Spreading replicas only handles placement; in operations, teams must still replace nodes, upgrade clusters, or patch the OS. If too many healthy Pods are deleted at once, the service can lose availability even when the cluster still has enough nodes.

A **PodDisruptionBudget (PDB)** limits voluntary disruptions for a group of Pods, typically via `minAvailable` or `maxUnavailable`. PDBs apply to supported disruption events in Kubernetes, such as node drains via the eviction API. They do not guarantee Pods remain healthy, do not protect against sudden involuntary failures, and do not replace readiness probes or replica counts.

Example:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: booking-api-pdb
spec:
  minAvailable: 4
  selector:
    matchLabels:
      app: booking-api
~~~

For Pods matching the selector, the goal is to keep at least four Pods ready during PDB-governed voluntary disruptions. If only four Pods exist and `minAvailable` is four, node drains can be blocked until replacement Pods come up or the policy changes. That can stall maintenance; never pick `minAvailable` arbitrarily.

| Mechanism | What It Solves | What It Does Not Solve |
| --- | --- | --- |
| Replicas | Desired copy count | Does not guarantee replicas sit in independent failure domains |
| Topology spread/anti-affinity | Physical/logical placement distribution | Does not guarantee fast Pod startup or app readiness |
| Readiness probe | Controls whether a Pod receives traffic | Does not maintain replica count when a node is lost |
| Liveness/startup probes | Detects stuck processes or slow startup | Does not replace fault tolerance across nodes/zones |
| PDB | Caps concurrent voluntary disruptions | Does not prevent sudden failures, zone loss, or simultaneous OOMs |
| Deployment strategy | Controls rolling updates via rollout parameters | Does not guarantee spare capacity if requests/quotas are insufficient |

Evaluate PDBs alongside rolling updates, cluster autoscaler, node drains, capacity headroom, and topology spread. An overly strict PDB combined with hard anti-affinity and tight resources can stall both upgrades and self-healing.

## 8. Combining the Scheduler with Autoscaling and Capacity Planning

The scheduler can only place Pods onto existing resources or resources added afterward. **Autoscaling cannot fix an unfeasible placement policy**; conversely, placement policies can force the autoscaler to expand specific node pools or add nodes in particular zones.

### 8.1. Three Scaling Layers

- **Horizontal Pod Autoscaler (HPA):** scales Pod count based on metrics like CPU/memory or custom/external metrics.
- **Cluster Autoscaler or platform node autoscaling:** adds/removes nodes when Pods are unschedulable or resources are idle, within node pool configs and quotas.
- **Vertical Pod Autoscaler (VPA):** recommends or adjusts requests/limits depending on deployment mode; applying updates may require Pod restarts and must coordinate with HPA.

Do not drive HPA solely by CPU if CPU requests do not reflect real load; CPU percentage is calculated relative to requests. For a search service, requests per second, queue depth, latency, or active in-flight tasks may be better signals if those metrics are reliably defined and operated.

### 8.2. Headroom and Capacity Upon Losing a Zone

Suppose an application needs 9 Pods to handle normal load, with each Pod requesting 1 vCPU. Split evenly across 3 zones, each zone holds 3 Pods. When one zone is lost, the remaining 6 Pods may not handle full load without spare headroom.

If the goal is to still serve full load after losing one zone, calculate capacity across the **remaining zones**, rather than adding an arbitrary percentage buffer. For instance, with a target of 9 serving Pods across 3 balanced zones, surviving the loss of one zone without dropping below 9 serving Pods cannot be achieved with 12 total Pods (4 per zone): losing one zone leaves 8, still short of 9. To retain at least 9 Pods after losing one of 3 zones, the distribution requires at least 5 Pods per zone (15 total), barring other constraints. This is simple arithmetic; real capacity must be based on measured throughput, node resources, and application behavior.

### 8.3. Diagnosing Pending Pods

When Pods stay Pending, investigate the root cause rather than blindly adding nodes:

- No node has sufficient CPU/memory requests or ephemeral storage.
- Hard node affinity, taints/tolerations, anti-affinity, or topology spread cannot be satisfied.
- A zone lacks resources, cloud quotas are hit, or capacity for that instance type is unavailable.
- Insufficient IPs, volume attachment slots, GPUs, or device resources.
- PersistentVolume topology binds the Pod to a different zone.
- Priority/preemption cannot free enough resources or would disrupt other critical workloads.

Scheduler events and Pod status typically report reasons such as `Insufficient cpu`, `Insufficient memory`, `volume node affinity conflict`, or `node affinity mismatch`. Teams must correlate those signals with node metrics, cloud quotas, and autoscaler status.

## 9. Stateful Workloads and Storage Constraints

Placing stateless Pods is generally simpler than placing stateful workloads. Databases, brokers, persistent caches, or file processing systems may depend on **persistent volumes, zones, replication protocols, and data identity**.

### 9.1. Storage Topology Affects Placement

Depending on the storage type, a persistent volume may only be attachable or accessible from a single zone or node. When a Pod is scheduled in another zone, volume topology can leave the Pod Pending. Even for multi-zone volumes or shared filesystems, verify attachment limits, concurrency semantics, and latency.

Before deciding placement for a StatefulSet, verify:

1. Which zone does the storage class provision volumes in, and when does binding occur?
2. How many nodes can attach a volume concurrently, and under which access modes?
3. When a zone fails, how is the volume recovered or replicated to another zone, and how long does it take?
4. Does the database/broker replicate data at the application layer or rely on storage replication?
5. How are quorum, leader election, split-brain prevention, and recovery ordering handled?

**Do not spread stateless app replicas across zones and assume the stateful tier is fault-tolerant.** If every replica writes to a single database inside an unreachable zone, the API will still fail even while app Pods remain alive.

### 9.2. Decoupling Application and Data Placement

For a booking platform, stateless APIs can be spread across three zones while the database uses a primary/standby or quorum cluster model as provided by the data service. Measure:

- Latency from APIs to the database and the impact of cross-zone communication.
- Database failover mechanism, detection time, and client reconnection time.
- RPO, consistency, in-flight transactions, and reconciliation during primary switchover.
- Whether backups sit independently of the primary failure domain and whether restores are tested regularly.

A cross-zone primary/standby setup improves reliability, but can still be affected by shared misconfigurations, identity, DNS, storage, or control plane issues. Examine the entire dependency graph.

## 10. Anti-Concentration Against Shared Failure Domains

Spreading replicas is only meaningful if shared points of failure are also addressed. Common **single points of failure** include:

- A single ingress controller, load balancer, or gateway without redundancy across the required scope.
- A single DNS resolver, identity provider, or secret service that every Pod must call on startup.
- A message broker, storage endpoint, or database lacking an appropriate fault-tolerant topology.
- A single node pool hosting all critical workloads, or all replicas landing on nodes sharing a host failure.
- A shared deployment pipeline or control plane that prevents remediation during an outage.

### 10.1. Mapping Dependency Graphs by User Journey

~~~mermaid
flowchart TD
    CLIENT["Client"]
    LB["Load Balancer"]
    API["Booking API replicas across 3 zones"]
    DB["Database primary/replica"]
    ID["Identity provider"]
    DNS["DNS"]
    SECRET["Secret manager"]
    QUEUE["Message broker"]
    CLIENT --> LB --> API
    API --> DB
    API --> ID
    API --> DNS
    API --> SECRET
    API --> QUEUE
~~~

Expand the diagram to document the actual location and failure domain of each dependency, covering both runtime and startup paths. For example, if all API replicas restart simultaneously and must call a failing secret service, they may fail to start even when nodes and zones have plenty of capacity.

### 10.2. Blast Radius Analysis

| Simulated Incident | Affected Components | Questions to Answer |
| --- | --- | --- |
| Loss of one node | Pods on that node | Where are Pods recreated, and are there enough nodes and IPs? |
| Loss of one zone | Nodes, volumes, or endpoints in that zone | Do remaining Pods cover the load, and does the database fail over? |
| Node pool capacity exhausted | Workloads tied to that pool | Is there an alternate pool with compatible CPU/GPU/storage? |
| Slow DNS/identity/secret service | Multiple dependent apps | Are safe caches, timeouts, retries, and degraded modes in place? |
| Cloud quota exhausted | Autoscaler/rollouts/DR | Do quotas account for peak load, upgrades, and recovery? |
| Faulty fleet-wide rollout | Multiple replicas on the same version | Are staged rollouts, canaries, rollbacks, and compatibility in place? |

Not every dependency needs multi-region active-active. Redundancy can be tiered by criticality, provided acceptable outage windows and recovery procedures are documented with the business.

## 11. Anti-Concentration and Practical Placement Strategies

Anti-concentration is not simply "one Pod per node." Multiple placement strategies exist, each serving a different goal:

| Strategy | Implementation | Suitable When | Risks / Trade-Offs |
| --- | --- | --- | --- |
| Node spread | Anti-affinity or topology spread by hostname | Surviving single-node loss, rolling maintenance | Replicas may still concentrate in a single zone |
| Zone spread | Topology spread by zone | Surviving a zone outage | Higher resource overhead and potential cross-zone latency/traffic costs |
| Region spread | Multiple clusters/regions with global routing | Geographic disaster recovery requirements | Data, consistency, failover, and operational complexity |
| Rack/host group spread | Infrastructure-provided topology labels | Deeper physical fault isolation requirements | Not all platforms expose granular topology |
| Tenant/workload spread | Separate node pools, namespaces, quotas, or clusters per customer/team | Multi-tenancy, isolation, noisy-neighbor mitigation | Higher cost and capacity fragmentation |

### 11.1. When Should You Pack?

Packing workloads close together makes sense when:

- A group of tasks exchanges heavy data and is latency-sensitive.
- Specialized nodes or GPUs need high utilization.
- Batch/worker jobs can run in elastic pools without needing the same isolation as production APIs.
- Cache/compute needs data locality to reduce network transfer.

However, packing replicas of a critical service into the same failure domain increases blast radius. You can pack **within a zone while spreading across zones**, or pack low-criticality workers into a dedicated pool while keeping strict spread rules for APIs.

### 11.2. Separating Workloads by Class

A simple classification model:

| Class | Example | Placement | Resource Policy |
| --- | --- | --- | --- |
| Critical stateless | Booking API | Spread across nodes and zones, appropriate PDB | Measured requests, autoscaling, deployment priority |
| Read-heavy | Search API | Spread, with nearby caches/read replicas | Scale on throughput/latency and DB limits |
| Async worker | Email, analytics jobs | Can pack in dedicated pool, bounded queues | Concurrency limits, backlog-based scaling |
| Stateful | Database, broker | Follows data service topology/storage/quorum | Stable capacity, backup/restore procedures |
| System/management | DNS, monitoring, ingress, agents | Redundant across appropriate failure domains | Prevent user workloads from starving control/infra layers |

## 12. Observing and Validating Placement After Deployment

You cannot tell how workloads are actually distributed just by reading manifests. You must observe **scheduler status, Pod placement, and node utilization** over time.

| Observation Area | Metrics or Events | Meaning |
| --- | --- | --- |
| Scheduling | Pending Pods, unschedulable reasons, scheduling latency | Which constraints or capacity limits are blocking Pods? |
| Placement | Pods per node/zone/node pool, topology skew | Are replicas concentrating in a single domain? |
| Node health | Ready condition, pressure, restarts, node pool capacity | Which failure domain or node is at risk? |
| Resources | CPU/memory requests vs. usage, throttling, OOMs, ephemeral storage | Do requests/limits match reality? |
| Availability | Ready replicas, PDB `disruptionsAllowed`, per-zone availability | Are enough Pods serving during maintenance or failures? |
| Data | DB connections, replication lag, failover, storage latency | Compute is alive, but can the data tier keep up? |
| Cost | Node utilization, idle capacity, cross-zone traffic | Is the added reliability worth the cost? |

Combine Kubernetes APIs/metrics, scheduler events, node labels, and cloud platform dashboards. A strong dashboard shows **desired replicas, ready replicas, and replicas per zone**, rather than total Pod counts alone.

### 12.1. Detecting Placement Skew

Suppose a Deployment requests 6 replicas, yet the dashboard shows 5 Pods in zone A and 1 Pod in zone B. Before blaming a scheduler bug, check:

- Does zone C have Ready nodes with accurate topology labels?
- Did existing Pods already exist before the topology rule was applied, or were they created afterward?
- Are node affinity, taints, volume topology, or resource requests excluding other nodes?
- Do Pods match the selector, and does the scheduler recognize the topology domain properly?
- Do zones B/A still have quotas and cloud capacity?
- Are Pods from another workload sharing the same label selector and skewing the calculation?

Tweaking topology rules without diagnosing the root cause may simply shift Pending Pods from one zone to another. Capture before/after evidence and verify the actual number of Ready Pods.

## 13. Failure Drills and Cluster Upgrades

Good placement must be validated through controlled failure testing in an authorized environment.

| Test Scenario | Expected Outcome to Verify |
| --- | --- |
| Drain a node | PDB allows the right disruption count, replacement Pods schedule onto other nodes, SLOs remain within thresholds |
| Unexpected node NotReady | Replicas are recreated, readiness and routing update, no prolonged storage attachment errors |
| One zone cannot accept new Pods | Placement rules behave as designed, remaining capacity holds or degraded mode activates |
| Node pool runs out of CPU/memory | Autoscaler expands the right pool or raises actionable alerts; no infinite scaling loops |
| Database failover | APIs handle reconnection, in-flight transactions, and idempotent retries |
| Zone recovery | Workloads rebalance in a controlled way, avoiding mass evictions/churn |
| Rolling deployment | Enough Ready replicas remain, placement is preserved, and capacity/quotas are not exceeded |

### 13.1. Drain / Maintenance Procedure

1. Check zone/node status, Ready Pod count, PDBs, and remaining capacity.
2. Confirm replacement nodes exist or that the autoscaler can provision the right node type within quotas.
3. Drain in small batches; monitor Pod evictions, scheduling, and SLOs.
4. Pause if PDBs block progress, Pending Pods rise, or latency/errors breach thresholds.
5. Once new nodes are Ready and workloads stabilize, proceed with the remaining maintenance.
6. Re-verify replica distribution, database connectivity, caches/queues, and dashboards.

Never lower a PDB just to push maintenance through without evaluating fault tolerance and obtaining proper approval. A PDB should reflect **acceptable voluntary disruption**, not a number picked just so `drain` always succeeds.

## 14. Placement Design Example for a Booking Platform

Suppose a cluster spans three availability zones, each with two application nodes plus a dedicated node pool for specialized workloads. The Booking API needs 6 replicas for peak load; Search has 9 replicas and scales dynamically; email/analytics workers do not require low latency. The database is provided as a multi-zone managed service or stateful cluster with its own failover process.

### 14.1. Distribution Targets

| Workload | Initial Replicas | Desired Distribution | Rationale |
| --- | ---: | --- | --- |
| Booking API | 6 | 2 per zone, separated across nodes if capacity allows | Preserves transaction confirmation during node/zone loss |
| Search API | 9 | 3 per zone, scaling on demand | Preserves read capacity and absorbs traffic spikes |
| Workers | 6 | Balanced across pool; may pack in dedicated pool | Optimizes resources, using queues for backpressure |
| Ingress controller | Per platform sizing/HA | Separated across nodes and zones | Prevents a single node failure from cutting off all ingress |
| Monitoring agents | DaemonSet or supported model | Present on every monitored node | Collects per-node telemetry; include overhead in sizing |

### 14.2. Calculating Zone Fault Tolerance

If 6 Booking API Pods are spread evenly 2–2–2, losing one zone leaves 4 Pods. The question is not just "are Pods still running?" but **"do 4 Pods have enough capacity to serve the business-required load during a zone outage?"**

Suppose load testing shows one Pod sustainably handles 50 requests/second at the target SLO, and peak load requires 180 requests/second:

~~~text
Pods needed for peak load = ceil(180 / 50) = 4
Remaining Pods after losing one zone (2-2-2 distribution) = 4
Post-incident headroom = 0 Pods
~~~

In theoretical division, the 4 remaining Pods barely meet the load. Yet there is zero headroom for traffic bursts, slow startups, or another Pod failing. If you want 5 Pods remaining after losing a zone, each zone needs at least 3 Pods so the remaining two zones supply 6 Pods—9 Pods total. Even that is only a starting point; you must still account for requests, node capacity, autoscaling delay, database throughput, and quotas.

**Do not substitute replica arithmetic for real testing.** Actual throughput depends on CPU, memory, DB connections, caches, downstream limits, request sizes, and cross-zone latency. Measure end-to-end user journeys under load and test under controlled degradation.

### 14.3. Pack/Spread Decisions by Workload

- Booking API: prioritize spreading across zones and nodes; PDB keeps enough Pods for core business flows; requests reflect real usage.
- Search API: spread across zones; place caches and read replicas close to serving Pods; optionally degrade advanced search features to protect the DB.
- Workers: bounded queues, capped concurrent consumers; allow packing in a dedicated pool to save cost, as long as backlog and processing time remain within SLO.
- Database: placement follows the data service's topology and HA model; do not try to manage database Pods with stateless app rules without understanding quorum/storage.
- Ingress and monitoring: reserve dedicated capacity so application workloads cannot starve the management/routing layer.

## 15. Placement Policy Selection Matrix

Before adding affinity or spread rules, walk through this matrix:

| Question | If "Yes" | Design Direction |
| --- | --- | --- |
| Would losing one node take down all replicas of a service? | Reduce node failure correlation | Spread by hostname or appropriate anti-affinity |
| Would losing one zone exceed allowed downtime? | Need zone fault tolerance | Spread by zone, keep capacity in remaining two zones, ensure data failover |
| Does the workload depend on special devices/hardware? | Only a subset of nodes can run it | Node affinity + taints/tolerations and node pool redundancy |
| Is data tied to a specific zone/volume? | Scheduler may pick incompatible nodes | Design storage topology and volume binding |
| Are there fewer nodes than replicas? | Hard anti-affinity can leave Pods Pending | Use soft preferences/topology spread or add capacity |
| Can tenant load cause noisy-neighbor issues? | Isolate resource groups or cap per tenant | Node pools, quotas, namespace/resource quotas, and scheduling policies |
| Must the workload run near a cache/database? | Locality improves latency/transfer cost | Consider data-local affinity while preserving failure-domain spread |
| Must maintenance happen without dropping below minimum replicas? | Must limit disruptions | PDBs, rollout strategies, headroom, and drain runbooks |

Good placement is a **context-driven decision**, not turning on every anti-concentration rule at once. Putting a hard rule at every layer can leave the scheduler with no node satisfying all conditions.

## 16. Well-Architected Evaluation

| Pillar / Perspective | Questions on Scheduling and Placement |
| --- | --- |
| **Operational Excellence** | Can we inspect replica placement, Pending Pods, scheduling reasons, node drains, and change processes? |
| **Security** | Are sensitive workloads isolated via node pools, identity, network policies, and protected label permissions? |
| **Reliability** | Are replicas spread across the right failure domains; are PDBs, storage, DNS, LBs, and databases fault-tolerant? |
| **Performance Efficiency** | Do requests/limits reflect measured load; are locality, autoscaling, sidecars, and network latency accounted for? |
| **Cost Optimization** | Is headroom reasonable; does packing non-critical workloads reduce idle nodes without creating single points of failure? |
| **Sustainability** | Are provisioned resources aligned with demand, avoiding prolonged overprovisioning and scaling down safely? |

### Trade-Offs to Document in the ADR

- **Increasing replicas and spreading:** increases fault tolerance, but raises compute cost, cross-zone network traffic, and potentially database connection load.
- **Hard anti-affinity:** enforces strict isolation, but reduces bin-packing efficiency and risks Pending Pods.
- **Packing:** improves utilization/cost or locality, but increases the number of workloads impacted together by a node/zone failure.
- **Strict PDBs:** protect against voluntary disruptions, but slow down maintenance and rollouts.
- **Aggressive autoscaling:** handles spikes better, but can strain quotas, image registries, IP pools, databases, and budgets.
- **Cross-region spreading:** expands disaster recovery reach, but adds complexity in data, consistency, routing, permissions, and DR testing.

An ADR should capture context and SLOs, target failure domains, selected topology, hard vs. soft rules, capacity under normal and failure states, cost impact, rejected alternatives, and review triggers.

## 17. Lab: Scheduling and Placing a Booking Service

**Hypothetical context:** A Kubernetes cluster spans three availability zones. The Booking API has 6 replicas, the Search API has 9 replicas, and Workers have 6 replicas. Each application node has 4 vCPUs and 16 GiB of memory. Load tests show one Booking API Pod requires a 500m CPU request and 512 MiB memory request; one Search Pod requires 700m CPU and 1 GiB memory. One zone may fail in the recovery scenario. Numbers are for practice only.

### Tasks

1. **Draw a topology diagram:** three zones, node pools, node counts, Pod placement, storage, and database; explicitly mark which failure domains the provider truly guarantees.
2. **Calculate requests:** total CPU/memory requests for Booking and Search by replica count; calculate minimum capacity under normal operation and upon losing one zone. Include sidecar/agent overhead if applicable.
3. **Design scheduler rules:** choose node affinity/selectors, topology spread, anti-affinity, and taints/tolerations; specify which rules are hard vs. soft.
4. **Design disruption controls:** choose PDBs and rolling update strategies; explain how to drain a node without dropping below approved service levels.
5. **Evaluate autoscaling:** define HPA metrics, node autoscaling, cloud quotas, and node provisioning times; identify risks of Pending Pods due to anti-affinity or missing storage.
6. **Evaluate stateful dependencies:** where do databases/queues live, what is the storage topology, and how are failover and RPO/RTO verified?
7. **Run failure drills:** drain a node, simulate zone loss, exhaust quotas, or trigger DB failover in an authorized test environment. Record p95 latency, error rate, Ready replicas, Pending Pods, and recovery time.
8. **Write a short ADR:** explain why you chose spread/pack, hard/soft constraints, cost trade-offs, and fallback plans if a zone lacks capacity.

### Completion Criteria

| Criterion | Indicator of Success |
| --- | --- |
| Capacity calculation | Total requests and headroom calculated for steady state, rollouts, and zone loss |
| Feasible placement | Node/zone counts, topology labels, affinity, and storage are mutually compatible; no impossible hard rules |
| Real fault tolerance | Enough Pods remain to serve actual load post-incident, not just counting surviving Pods |
| Operations | PDBs, drains, autoscaling, quotas, and runbooks are actionable |
| Data | Databases/storage have independent HA/backup models and tested RTO/RPO |
| Evidence | Load/failure test results and architectural decisions are documented |

## 18. Pre-Production Container Workload Checklist

- [ ] Target failure domains are defined: container, Pod, node, rack, zone, region, and shared dependencies.
- [ ] CPU/memory requests/limits are measured, including sidecars, init containers, ephemeral storage, and dependent resources.
- [ ] Workloads requiring spread vs. eligible for packing are identified with business justification.
- [ ] Accurate node topology labels and cross-zone distribution capability are verified.
- [ ] `topologySpreadConstraints`, affinity/anti-affinity, and selectors are validated to avoid unfeasible hard rules.
- [ ] Taints/tolerations, node pools, specialized devices, and node label modification permissions are reviewed.
- [ ] PDBs, readiness/liveness/startup probes, rollout strategies, and drain procedures are coordinated.
- [ ] Capacity upon losing a zone is calculated, including quotas, IPs, volume attachments, DB, queues, and autoscaling lag.
- [ ] Topology of persistent volumes, databases, brokers, and data recovery capabilities is analyzed.
- [ ] Monitoring covers replicas per node/zone, Pending Pods, scheduling events, throttling, OOMs, and PDB `disruptionsAllowed`.
- [ ] Node/zone failure drills, maintenance, rolling deployments, and dependency failovers have been rehearsed.
- [ ] An ADR documents reliability, performance, security, cost, and operational trade-offs.

**Core takeaway:** the scheduler decides where a Pod runs based on resources and constraints; topology spread/affinity governs how replicas are distributed; PDBs and operational procedures limit voluntary disruptions. True reliability is achieved only when **compute, networking, storage, databases, quotas, and shared dependencies** are designed together around failure domains and validated through real drills.
