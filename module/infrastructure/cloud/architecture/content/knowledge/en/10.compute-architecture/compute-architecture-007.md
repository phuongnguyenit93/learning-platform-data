# Setting Resource Limits and Controlling Cross-Workload Interference

When multiple applications or teams share a VM cluster, container node, or shared compute platform, a sudden surge in one workload can consume CPU, memory, I/O, or connections beyond expectations. Peer workloads start slowing down, timing out, or getting terminated even though nothing changed in them. This phenomenon is commonly called **noisy neighbor**—one "loud" workload degrading the quality of others sharing the same resources.

To control this, the architecture must define **who can use which resources, up to what ceiling, for how long, and what happens when limits are hit**. Mechanisms such as quotas, requests/limits, concurrency limits, reservations, isolation, priorities, and autoscaling allocate resources deliberately. Limits set too low trigger throttling or OOMs; limits set too high allow one workload to monopolize capacity and inflate costs.

This lesson belongs to the **Compute Architecture** section of the cloud architecture course. Setting limits must tie directly to business objectives and SLOs while balancing reliability, security, scalability, cost, and operations. Concepts span VMs, containers, Kubernetes, and serverless platforms.

After this lesson, you will be able to:

- Explain noisy neighbors and identify contention across CPU, memory, disk, network, connections, and quotas.
- Distinguish **requests/reservations**, **limits/caps**, **quotas**, and **concurrency limits**.
- Select appropriate isolation boundaries and limits for VMs, containers, Kubernetes, and serverless.
- Estimate capacity, headroom, reserve margins, and autoscaling impacts.
- Design observability, alerting, and load tests to prove limits do not break SLOs.
- Propose fair, prioritized policies and enforcement procedures when workloads exceed resource budgets.

## 1. What Is a Noisy Neighbor?

In shared compute environments, multiple processes or workloads compete over one or more resources:

- **CPU:** a heavy compute job hogs processor time, forcing peer APIs to wait on the scheduler.
- **Memory:** a growing heap or cache starves node RAM, triggering reclamation, swapping, OOMs, or evictions.
- **Storage I/O:** large batch reads/writes spike latency for databases or peer workloads on the same device.
- **Network:** heavy upload/download streams saturate bandwidth or inflate packet processing and connection tracking.
- **Runtime resources:** thread pools, file descriptors, processes, ephemeral ports, connection pools, or locks.
- **Platform limits:** API quotas, instance counts, IP counts, volume counts, request rates, or provider service caps.

For example, a booking system runs customer-facing APIs alongside a nightly reporting job on the same node group. The reporting job scans millions of records and compresses outputs. Without CPU, memory, and I/O limits, the job can push API p95 latency from 200 ms to several seconds. If it also opens too many DB connections, the API can time out even before node CPU reaches 100%.

Noisy neighbors do not only happen between external tenants. They occur between microservices, between an API and workers of the same product, or between production workloads and batch jobs deployed by the same operations team.

### Distinguishing Contention from Overall Capacity Shortage

| Situation | Symptoms | Investigation Direction |
| --- | --- | --- |
| Noisy neighbor | One workload surges while peer workloads degrade in correlation | Separate workloads, enforce limits, adjust priorities/isolation, inspect shared resources |
| Overall capacity shortage | Many workloads near saturation simultaneously despite sensible allocation | Expand capacity, optimize code, queries, and sizing |
| Downstream bottleneck | Compute has headroom yet APIs wait on DB, queues, or external services | Track dependency latency, connection pools, quotas, and retries |
| Overly tight config limits | Workload suffers frequent throttling/OOMs while nodes have spare capacity | Revisit requests/limits, memory sizing, and policies |

Not every latency spike is a noisy neighbor. Correlate **workload-level metrics**, **node-level metrics**, and dependency latency before drawing conclusions.

## 2. Resources Must Be Managed Across Multiple Layers

A workload can run inside a VM, container, pod, process, or function. Each layer has its own boundaries; total host capacity does not mean every process can consume all of it.

~~~mermaid
flowchart TD
    CLOUD["Cloud account / subscription / project<br/>Service quotas and budgets"] --> POOL["Compute pool / VM scale set / node group"]
    POOL --> NODE["Host / VM node<br/>CPU, RAM, disk, network"]
    NODE --> CG["Container / cgroup / runtime limits"]
    CG --> POD["Pod / service / process"]
    POD --> THREAD["Threads, workers, requests, connections"]
    THREAD --> DEP["Database, queue, storage, external API"]
~~~

A request succeeds only when **every required layer has capacity and sits below its limits**. A pod might have 2 CPUs available while the database permits only 30 connections; scaling to 20 pods can push total connection pools past the database ceiling.

| Resource | Useful Metrics | Signs of Contention |
| --- | --- | --- |
| CPU | usage, throttled time, load, run queue, steal time | Slow requests, CPU throttling, runnable threads waiting |
| Memory | working set, RSS, heap, cache, page faults, OOM | Elevated GC, reclaim/swap, OOM kills, evictions |
| Disk/storage | IOPS, throughput, queue depth, latency, burst balance | Slow DB queries or log writes |
| Network | throughput, packet rate, drops, retransmits, connection count | Timeouts, packet loss, queueing, NAT/port exhaustion |
| Threads/processes | active/blocked threads, process count, file descriptors | Exhausted thread pools, file/socket open errors |
| Downstream pools | DB connections, queue depth, API quotas | Connection waits, growing backlogs, rate limits |
| Platform | quotas, pending allocations, scaling events, throttling | Unable to provision instances despite scaling demand |

Node-wide averages can hide a saturated container or single CPU core. Inspect metrics **per workload and over time**, especially p95/p99 latency and contention during peak windows.

## 3. Distinguishing Requests, Limits, Quotas, and Concurrency

Exact meanings vary by platform, but these controls serve distinct roles:

| Mechanism | Meaning | Purpose |
| --- | --- | --- |
| **Request / reservation** | Declared required capacity or space reserved during scheduling/allocation | Guides scheduler placement and capacity reservation |
| **Limit / cap** | Maximum allowed usage or enforced hard/soft ceiling | Prevents a workload from exceeding its share |
| **Quota** | Aggregate ceiling per account, project, tenant, region, or service | Caps total resources/operations creatable or usable |
| **Concurrency limit** | Maximum concurrent tasks/requests/instances processed | Protects internal resources or downstreams from overload |
| **Priority / class** | Priority rank during contention or scheduling | Shields critical workloads or defines service order |
| **Reservation pool** | Capacity pre-allocated for a workload group | Reduces risk of peer workloads consuming needed capacity |

A request is not necessarily the minimum the app always consumes, nor is a limit always reserved capacity. For example, Kubernetes CPU requests guide the scheduler; CPU limits typically enforce cgroup CPU quotas over time slices. Memory limits are enforced differently—not via throttling like CPU.

### Example: Workloads A and B Sharing a Node

Suppose a node has 8 vCPUs and 16 GiB RAM. The platform team schedules:

| Workload | CPU Request | CPU Limit | Memory Request | Memory Limit |
| --- | ---: | ---: | ---: | ---: |
| Booking API | 2 CPU | 3 CPU | 3 GiB | 4 GiB |
| Notification worker | 1 CPU | 2 CPU | 2 GiB | 3 GiB |
| Reporting batch | 1 CPU | 2 CPU | 2 GiB | 3 GiB |
| Total declared | 4 CPU | 7 CPU | 7 GiB | 10 GiB |

Remaining node capacity must cover the OS, agents, daemons, overhead, and reserve headroom. Requests summing below physical vCPUs still do not guarantee zero contention: burst limits, CPU shares/weights, I/O, and background workloads all matter. Account for system overhead and test under realistic load.

### Behavior When Hitting Limits

- **CPU cap:** runtime throttles the process; the app stays alive but responds more slowly.
- **Memory cap:** allocations fail or the process gets OOM-killed; breaching memory limits usually causes abrupt failure rather than gradual slowdown.
- **Account quota:** requests to create more VMs/functions/IPs are rejected or queued; autoscalers cannot bypass quotas.
- **Concurrency cap:** incoming requests queue, get rejected, retry, or throttle depending on the platform.
- **Storage/network cap:** throughput gets capped or incurs higher burst charges; some services burst briefly then fall back to baseline.

Therefore, configuration docs must specify **behavior at thresholds**, not merely list numbers.

## 4. Setting Limits on VMs and Compute Instances

For VMs, providers expose profiles of vCPU, RAM, networking, and storage. VMs provide stronger isolation boundaries than processes sharing an OS, yet multiple VMs can still share underlying physical hardware or host/cloud limits.

Base sizing on:

- CPU profile: bursty, sustained, CPU-bound, or I/O-bound?
- Memory footprint and peak working set, not just declared heap.
- Network throughput and concurrent connection counts.
- Storage IOPS, throughput, latency, and burst models.
- Dependencies on CPU architecture, accelerators, local NVMe, or specialized hardware.
- Reserve margin for losing an instance or zone.

More vCPUs will not speed up every workload; more RAM will not fix a service bottlenecked on database locks. Find the right profile by benchmarking with matching CPU/memory/network tiers and realistic configs.

If multiple applications share a single VM, enforce process/service-level controls:

- Linux `cgroups` and `systemd` slices can cap CPU, memory, I/O, and process counts per configuration.
- Windows Job Objects and service controls can bound process resources.
- Thread pools, connection pools, internal queues, file descriptors, and process limits each need explicit caps.
- Batch jobs should run at lower priority than interactive APIs when OS and runtime settings support it.

Process boundaries are weaker than separate VMs in many cases. When processes run with root/administrator privileges or share a kernel, security compromises or kernel-level resource exhaustion can still cross over.

### Burstable Instances and CPU Credits

Some VM families are **burstable**: during low load they accrue CPU credits to burst above baseline briefly; once credits deplete, CPU performance throttles or incurs surplus charges. Monitor credit balances, sustained utilization, and long-load behavior. Never size production from a 5-minute benchmark assuming peak burst speed holds all day.

## 5. Setting Limits on Containers and Kubernetes

Containers package apps cleanly, yet co-located containers typically share a host kernel and resources. `cgroups`, namespaces, runtimes, and schedulers work together to bound and isolate workloads.

### CPU Requests and Limits in Kubernetes

- **CPU request** tells the scheduler how much capacity a node must have to place the Pod, and sets relative CPU weight under contention.
- **CPU limit** sets a hard ceiling enforced by the runtime via cgroup CPU quotas. Containers get throttled when attempting to exceed it.
- CPU is expressed in cores or millicores; e.g., `500m` equals half a logical CPU in Kubernetes resource specs.

Example manifest:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: booking-api
spec:
  containers:
    - name: api
      image: example.invalid/booking-api:1.0
      resources:
        requests:
          cpu: "500m"
          memory: "768Mi"
        limits:
          cpu: "1500m"
          memory: "1Gi"
~~~

This is an **illustrative example**, not production sizing. If a Java workload needs heap, metaspace, thread stacks, and native memory, total container memory must exceed `-Xmx`. Setting the memory limit right at max heap can trigger OOM-kills even before heap fills.

### Memory Limits Differ from CPU Limits

CPU is compressible and time-sliced; exceeding CPU quota typically causes throttling. Memory is incompressible in the same way: exceeding a container's memory limit causes the kernel/runtime to OOM-kill processes. Memory requests influence scheduling and eviction order, whereas memory limits act as a hard enforcement boundary.

Setting memory limits too low triggers restart loops and drops throughput. Setting them too high hinders scheduling or encourages node overcommit. Measure **working set**, heap, direct buffers, metaspace, native allocations, sidecars, and GC peaks.

### Should CPU Always Have a Limit?

There is no single default suitable for every container. Some interactive APIs benefit from short CPU bursts and perform better without overly tight CPU throttling, whereas batch jobs need explicit caps to protect co-located APIs.

1. Set requests accurately so the scheduler places workloads cleanly.
2. Monitor latency and CPU throttling metrics to check whether limits hurt performance.
3. Combine limits, priorities, dedicated node pools, or workload separation when stronger isolation is needed.
4. Test contention when nodes near saturation—not just single isolated pods.

### QoS Classes and Eviction

Kubernetes assigns Pods to QoS classes—**Guaranteed**, **Burstable**, and **BestEffort**—based on how requests/limits are configured (exact behavior depends on resources and configuration). Under node memory pressure, `kubelet` evicts Pods using factors including QoS, usage relative to requests, and priority. QoS does not replace availability policies or node separation.

For critical workloads, ensure:

- Requests are grounded in measured consumption.
- Memory limits leave headroom for peaks and native memory.
- `PodDisruptionBudget` limits voluntary disruptions where appropriate (PDBs do not prevent hardware/zone failures).
- Anti-affinity/topology spread constraints prevent all replicas from landing on one node/zone.
- `PriorityClass` is governed strictly; high priority never manufactures physical hardware.
- Sensitive or noisy workloads get dedicated node pools when stronger isolation is required.

### Namespace Quotas and `LimitRange`

At cluster/namespace scope, Kubernetes provides:

- **`ResourceQuota`** to cap aggregate requests/limits, Pods, Services, PVCs, or supported objects.
- **`LimitRange`** to enforce default/min/max resources per container or PVC.
- Admission policies to block workloads missing requests/limits or violating standards.

Example `ResourceQuota`:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: booking-team-quota
  namespace: booking
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 16Gi
    limits.cpu: "12"
    limits.memory: 24Gi
    pods: "30"
~~~

This quota is an **aggregate namespace cap for the declared fields**, not pre-reserved capacity. Node pools must still hold enough resources for scheduling; exhausting a quota prevents new deployments from creating replicas.

## 6. Setting Limits on Serverless and Managed Platforms

Not managing nodes directly does not eliminate contention or limits. Serverless and managed platforms still enforce limits per account, region, function, request, memory, timeout, or concurrency.

| Platform | Mechanisms to Review | Risk If Ignored |
| --- | --- | --- |
| Function/serverless compute | Coupled memory/CPU profiles, timeouts, concurrency, request rates, concurrent executions | Throttling, cold starts, queue backlogs, quota breaches |
| Managed container platform | CPU/memory per instance, min/max replicas, request concurrency, scale-to-zero, regional quotas | Single instances overloaded or failing to scale in time |
| PaaS web/app service | Worker sizes, instance counts, plan capacity, connection caps | Multiple apps on the same plan contending for resources |
| Managed batch/job | vCPU, memory, GPU, concurrent jobs, queues, and quotas | Batches exhaust capacity; jobs stall or get rejected |
| Managed database | Connection caps, storage, IOPS, throughput, query concurrency, replica lag | API compute has headroom while DB chokes |

### Concurrency Is a Critical Limit

A function can handle many simultaneous invocations. If each invocation opens 5 database connections and the platform scales to 100 concurrent invocations, demand jumps to 500 connections. If the database allows fewer connections, function autoscaling amplifies the bottleneck.

~~~text
Estimated peak connections
  = concurrent instances/invocations
    × max connection pool per instance
    + connections from workers and admin tasks
~~~

This is an upper bound based on config, not guaranteed steady usage. Pools may lazy-create or multiplex, so measure and verify actual runtime behavior.

### Backpressure Instead of Blind Scaling

When downstreams hit limits, systems should **throttle ingress rate**:

- Queues to absorb bursts within bounded length and message age.
- Concurrency caps for workers and functions.
- Rate limits per client, tenant, or task type.
- Timeouts, retries with backoff and jitter, and circuit breakers when downstreams degrade.
- Load shedding: reject or degrade low-priority features under overload with explicit responses.

Expanding intake when downstreams are already saturated usually worsens outages. Backpressure keeps systems inside a recoverable operating zone.

## 7. Isolation: How Much Sharing Is Appropriate?

Isolation tiers trade cost and operational complexity against blast radius:

| Isolation Level | Example | Strengths | Trade-offs |
| --- | --- | --- | --- |
| Same process | Thread pools, executors, bounded queues | Low overhead, easy data sharing | Process crash hits all co-hosted workloads |
| Same container/Pod | Multiple processes or sidecars | Shared network namespace/volumes by design | Coupled resources and lifecycles |
| Separate containers on same node | Pods/containers with cgroups and namespaces | Separate resource caps and management | Shares kernel, node, disk/network, and hardware |
| Separate VMs on shared host/zone | Multiple VMs on cloud infrastructure | Clearer OS boundaries | Still shares physical fabric and shared services |
| Dedicated node pool/host | Dedicated node groups or dedicated hosts | Reduces interference and tightens control | Higher cost and idle capacity |
| Separate account/project/subscription | Isolating workloads or tenants at admin level | Clearer governance and quota boundaries | Distributed config, logging, networking, and ops |

**Isolation is multidimensional:** security isolation does not guarantee performance isolation. Separate VMs can still share a NAT gateway or database; separate namespaces do not automatically reserve dedicated physical CPUs. Specify which class of interference you need to contain.

### Multi-Tenancy and Fairness

If a platform serves multiple customers or teams, resource policies must balance:

- **Fair share:** prevent one tenant from starving others when demand overlaps.
- **Priority:** critical transactions or higher tiers can receive explicit policy-backed precedence.
- **No starvation:** lower-priority workloads still make progress when capacity permits.
- **Per-tenant quotas:** cap total requests, storage, concurrency, or resources per customer.
- **Burst policies:** allow bounded, time-limited bursts above baseline under control.
- **Noisy tenant detection:** track usage and anomalies per tenant, not just aggregate load.

Never force one fixed quota onto every customer if scale and contracts vary. Conversely, prioritizing one tenant without bounds starves everyone else.

## 8. Autoscaling Does Not Replace Resource Limits

Autoscaling adjusts instance/replica counts based on metrics or policies. It adds capacity when possible, but never guarantees scaling finishes ahead of sudden bursts or that downstreams can absorb added load.

Three scaling layers:

1. **Horizontal scaling:** adding or removing instances, Pods, or function workers.
2. **Vertical scaling:** changing CPU/RAM/IOPS profiles for instances or workloads.
3. **Cluster/account scaling:** adding nodes/VMs, raising quotas, or switching pools when current capacity runs out.

Each layer carries its own response lag, limits, and costs. Vertical scaling may require restarts; adding nodes depends on cloud quotas, provisioning lag, and zone availability. Autoscalers cannot provision resources once cloud quotas are exhausted.

| Metric | When Useful | Caveats |
| --- | --- | --- |
| CPU utilization | CPU-bound workloads where requests track CPU | Blind to DB or I/O bottlenecks |
| Memory utilization/working set | Workloads whose footprint scales with load | Scaling when already near OOM may be too late |
| Request rate / concurrency | Variable-load APIs with consistent per-request cost | Must account for heavy vs. light request mix |
| Queue depth / oldest message age | Async workers | High queue depth may reflect a broken downstream; adding workers may not help |
| Request latency / saturation | Tied directly to SLOs and UX | Latency can rise due to dependencies rather than compute shortage |
| Custom business metrics | E.g., unconfirmed bookings or pending tasks | Metrics must be well-defined and avoid oscillation |

Autoscaling designs need **min/max replicas**, faster scale-out than scale-in, cooldown/stabilization windows, appropriate targets, and oscillation testing. Minimum capacity keeps workloads warm; maximum capacity protects budgets and downstreams.

### Queue Worker Example

Suppose a worker averages 10 messages/second per instance. The system receives 300 messages/second over an hour. Considering theoretical throughput alone:

~~~text
Required workers = 300 / 10 = 30 instances
~~~

If each worker opens up to 4 DB connections, the pool can reach 120 connections. If the database only has 80 spare connections for workers, scaling from 20 to 30 workers exhausts the connection pool. Lower per-worker pool sizes, add a concurrency cap layer, optimize transactions, or scale database capacity based on measurements.

## 9. Sizing Capacity and Reserving Headroom

Setting limits without planning total pool capacity leaves workloads fighting for scraps. Sizing must combine **peak load, scaling lag, failure scenarios, and system overhead** in one calculation.

### CPU-Based Estimation

Suppose one API instance serves 100 requests/second at the agreed p95 target, while the system needs 400 RPS:

~~~text
N_instances = ceil(400 / 100) = 4
~~~

If surviving a zone outage across two balanced zones is required, each zone needs enough instances to carry the load when the other vanishes. Under those assumptions, at least 4 instances must remain in the surviving zone. Add headroom because ideal benchmarks omit traffic variance, deployments, cold starts, and skew.

### Headroom and Overcommit

**Headroom** is unallocated or idle capacity kept to absorb bursts, failures, and scale-out lag. **Overcommit** allows declared requests or expected peak sums to exceed physical capacity on the assumption that not every workload peaks simultaneously.

Overcommit improves utilization at the cost of higher noisy-neighbor risk. Safe tolerance depends on:

- Whether workloads burst together (correlated peaks).
- Criticality and SLOs of each workload.
- Ability to throttle, queue, retry, or shed requests.
- Time required to provision fresh capacity.
- Node/AZ failure scenarios and load concentration on survivors.

Never size solely from weekly average utilization. Inspect percentiles, correlated peaks, and stress tests.

### Example Capacity Allocation Across Workload Groups

A node pool provides 32 vCPUs and 128 GiB RAM. Suppose the platform team reserves 20% CPU as headroom and 16 GiB for OS/agents:

~~~text
Schedulable CPU = 32 × (1 - 0.20) = 25.6 vCPUs
Schedulable Memory = 128 - 16 = 112 GiB
~~~

The API group requests 12 vCPUs / 48 GiB; workers request 8 vCPUs / 32 GiB; batches request 4 vCPUs / 24 GiB. Total requests equal 24 vCPUs / 104 GiB, fitting within schedulable capacity in this hypothetical math. Yet if a node fails, surviving capacity may fall short; real math also needs topology, node allocatable overhead, DaemonSet/sidecar footprints, and failure domains.

This is a simplified planning exercise, not a universal sizing formula. True capacity depends on post-overhead allocatable node resources, memory pressure, I/O, and bin packing across individual nodes. Never sum cluster totals while ignoring whether any single node has room to schedule the next Pod.

## 10. Resource Control Goes Beyond CPU and RAM

**Storage:** IOPS, throughput, queue depth, burst credits, latency, and capacity. A batch workload can spike database volume latency even with spare CPU. Isolate volumes or storage classes, enforce I/O limits where supported, and test with realistic read/write patterns.

**Network:** bandwidth, packets per second, connection tracking, NAT ports, connection counts, load balancer caps, and egress. Heavy transfers can drive data-transfer bills up without moving CPU.

**Database:** connections, transactions, locks, query concurrency, storage IOPS, throughput, and replica lag. Bound connection pools; introduce caches only with sound invalidation and consistency strategies.

**Queue/event systems:** message age, queue depth, in-flight counts, partition/consumer capacity, retries, and DLQ volume. Worker scaling must respect downstream capacity and idempotency.

**Accelerators/GPUs:** GPU count, GPU VRAM, kernel execution duration, and device sharing. AI workloads can contend over VRAM and I/O; enforce proper profiles, node pools, and quotas.

**Control plane/API quotas:** cloud control-plane API call rates, resource limits, IPs, volumes, rules, and function concurrency. Platforms can block scaling or deployments even while compute nodes sit idle.

The fix is usually bounding **the exact resource acting as the bottleneck**. Giving more CPU to a disk-I/O-bound workload raises bills without improving throughput.

## 11. Observing and Diagnosing Noisy Neighbors

A resource policy only works when operators can observe its effects. Instrument metrics across workloads, hosts, and downstreams.

| Layer | Signals | How to Use |
| --- | --- | --- |
| Workload | CPU, throttling, working set, restarts, OOMs, requests/concurrency | Identify which workloads are hitting or consuming limits |
| Node/VM | allocatable, pressure, run queue, steal, disk latency, packet drops | Detect shared-infrastructure contention |
| Application | p50/p95/p99 latency, error rate, saturation, thread pools | Connect resource contention to user experience |
| Dependency | DB connections/locks, queue age, downstream latency, quota errors | Avoid mistaking downstream saturation for compute shortage |
| Platform | scale events, pending pods, failed provisioning, account quotas | Spot scheduler or cloud quota limits |
| Cost | CPU/RAM hours, storage/IOPS, egress, idle capacity | Evaluate allocation efficiency and over-provisioning |

### Step-by-Step Investigation Sequence

1. Pinpoint when SLOs degraded and which workloads were impacted.
2. Compare that workload's metrics against peers on the same node/pool.
3. Inspect CPU throttling, memory pressure, I/O queues, packet drops, and connection contention.
4. Correlate deploy logs, batch jobs, autoscaler events, quotas, and config changes.
5. Check downstreams: databases, caches, queues, external APIs.
6. Run a controlled experiment: cap the suspected workload or move it to an isolated node pool, then compare latency and utilization.
7. Tune policies, sizing, isolation, or code; re-measure to confirm root cause.

Never blindly raise limits for an impacted workload first. If the node is already full, raising limits worsens contention. First verify **whether spare capacity exists**, who is consuming it, and which limits are firing.

### Symptom- and Cause-Based Alerts

- p95/p99 latency and error rates breach targets.
- Sustained high CPU throttling paired with rising latency.
- Memory pressure/OOMs/restarts or evictions exceed baselines.
- Queue oldest message age crosses business processing deadlines.
- DB connection pool nears exhaustion or query latency spikes.
- Long-pending workloads due to insufficient allocatable capacity or quotas.
- Egress, log ingestion, or compute spend exceeds budget.

One minute at 90% CPU is not necessarily an incident if SLOs hold and headroom is intact; conversely, 40% CPU can hide terrible p99 latency caused by locks, I/O, or downstreams.

## 12. Priority Policies and Protecting Critical Workloads

Not all workloads carry equal importance. Peak-hour booking APIs need protection against reporting jobs that can afford to finish a few minutes later.

| Tier | Examples | Recommended Resource Policy |
| --- | --- | --- |
| Critical interactive | Login, booking, payment APIs | Adequate reservations/requests, tested limits, multi-replica/AZ, SLO-driven alerts |
| Important background | Notification workers, order processors | Queues, concurrency caps, retry/backoff, message-age SLAs |
| Batch/analytics | Reports, data aggregation | Lower priority, off-peak scheduling, I/O and concurrency caps |
| Best-effort | Experimental tasks, reproducible jobs | Low quotas; eligible for preemption/eviction per platform policy |

Priority tiers require clear definitions and owners. Calling a workload "critical" demands matching SLOs, capacity, and incident response—not merely assigning the highest priority number.

### Preemption and Fairness

Some schedulers can **preempt** low-priority workloads to free room for high-priority ones. Verify:

- Do preempted jobs checkpoint and resume safely?
- Does preemption cause duplicate side effects or data loss?
- Can low-priority workloads suffer indefinite starvation?
- Are there limits on preemption frequency or minimum runtime guarantees?
- Are users informed of job SLAs?

A fair system does not necessarily split CPU equally at all times; it allocates according to transparent policies, protects critical objectives, and prevents any group from being permanently starved.

## 13. Project Workflow for Setting Resource Limits

1. **Classify workloads:** record load type (interactive, streaming, batch, event-driven), criticality, CPU/memory/I/O/network profiles, data, and downstreams. Identify tenant scope and isolation needs.
2. **Define quality targets:** set SLIs/SLOs, throughput, concurrency, latency percentiles, error budgets, and RTO/RPO where applicable. Document peak conditions and failure scenarios.
3. **Measure baselines:** run representative loads and capture working set, CPU, memory, disk, network, pools, and dependencies. Record runtime configs, versions, and load-test setup.
4. **Set reservations, limits, and quotas:** base requests/reservations on steady needs, limits on acceptable peaks and pool size, quotas by team/tenant/account, and concurrency on downstreams. Document breach behavior.
5. **Design isolation and priorities:** pick process/container/node pool/VM/account boundaries matching risk; apply anti-affinity/topology spread, security boundaries, and priorities where justified. Isolate batches from interactive APIs when impact warrants it.
6. **Verify autoscaling and headroom:** calculate normal and post-node/AZ-loss capacity; measure scale-out lead time; check cloud quotas and max replicas. Prevent scalers from scaling infinitely into DB or budget exhaustion.
7. **Configure observability and alerts:** track workload/node/downstream resources; alert on SLO burn plus starvation, throttling, OOMs, queue age, quota failures, and cost.
8. **Run contention and failure tests:** execute co-located workloads under controlled noisy loads; test node drain/eviction, slow downstreams, and account quotas. Confirm critical workloads still meet SLOs.
9. **Review and tune from telemetry:** post-launch, compare actual utilization, latency, errors, cost, and headroom against assumptions. Tune requests/limits/quotas; version architectural decisions and exceptions.

~~~mermaid
flowchart TD
    A["Classify workloads"] --> B["Define SLOs and criticality"]
    B --> C["Measure baseline and peak"]
    C --> D["Set requests, limits, quotas, concurrency"]
    D --> E["Choose isolation and priority"]
    E --> F["Size headroom and autoscaling"]
    F --> G["Observability and alerts"]
    G --> H["Stress / noisy-neighbor / failure tests"]
    H --> I{"SLOs and fairness met?"}
    I -- "Not yet" --> C
    I -- "Met" --> J["Deploy and review periodically"]
~~~

## 14. Practice Exercise: Controlling Noisy Neighbors in a Booking App

**Hypothetical scenario:** A compute cluster hosts three workload groups:

- **Booking API:** user-facing, 400 RPS peak load; p95 target under 250 ms, 99.9% success SLO.
- **Notification worker:** processes email/SMS messages; must finish within 5 minutes under normal load.
- **Reporting batch:** runs nightly, scans large datasets and builds reports; can run longer under heavy load.

The cluster has 4 nodes, each with 8 vCPUs and 32 GiB RAM. During peak hours, a batch unexpectedly runs alongside the Booking API; API p95 spikes to 1.8 seconds and worker backlogs grow. Cluster-wide metrics report 75% CPU and 70% RAM.

The figures in this prompt are simulated facts—not enough on their own to prove root cause.

### Tasks

1. **Identify hypotheses:** propose at least five hypotheses covering CPU throttling, memory pressure, disk I/O, DB connection saturation, network egress, or lock/query contention. Specify which metrics verify each.
2. **Propose resource policies:** design requests/limits for Booking API and workers, namespace/team quotas, and concurrency caps for batches and queue workers. Account for OS, agent, daemon headroom, and node loss. If choosing a separate node pool, explain why and the cost impact.
3. **Protect downstreams:** suppose the database permits at most 100 additional application connections. Size connection pools, worker concurrency, and rate limits so batch/reporting cannot starve Booking API. Prove total connections under max replicas.
4. **Design autoscaling and fairness:** pick scaling metrics for the API and workers; set min/max replicas, cooldowns, and caps to prevent runaway scaling. Define priorities, batch preemption behavior, and anti-starvation safeguards.
5. **Design verification tests:** run competing loads, inject controlled CPU/memory/I/O pressure, test DB connections, node failures, quota exhaustion, and cost spikes; gather before/after telemetry.

| Test | Injected Stimulus | Evaluation Criteria |
| --- | --- | --- |
| CPU noisy neighbor | Batch drives sustained CPU on nodes hosting the API | API p95, throttling, and throughput stay within targets |
| Memory pressure | Controlled worker working-set growth | No mass OOMs; policy-driven evictions protect critical workloads |
| I/O contention | Heavy batch reads/writes on shared storage | Database/API latency and IOPS remain within thresholds |
| DB connections | Scale workers and API concurrently to max replicas | Pool never exhausts; critical requests retain connectivity |
| Node failure | Drain or kill one node in test | Surviving capacity, pending pods, SLOs, and recovery time |
| Quota exhaustion | Simulate node/instance quota limit | Alerts, graceful degradation, and clear operator runbook |
| Cost spike | Increase load or prolong batch | Budget guards trigger; alerts fire as expected |

### Guided Approach

You cannot conclude CPU is the culprit merely because the batch overlapped and cluster CPU hit 75%. Inspect per-container CPU usage/throttling, memory pressure, disk latency, DB connections/locks, and networking. Cluster averages often mask one saturated node or throttled container.

A sound design shields Booking API with proper reservations and caps the batch; puts reporting onto a queue/schedule with concurrency caps; and splits node pools if tests show noisy-neighbor impact persists despite container limits. Keep aggregate connection pools inside DB limits while reserving headroom for admin tasks and workers. Give autoscalers max caps aligned with cloud quotas.

Every design must be validated via **concurrent contention testing**. Testing Booking API or Reporting batch in isolation never proves isolation works.

## 15. Well-Architected Evaluation

| Pillar | Questions Related to Resource Limits |
| --- | --- |
| **Operational Excellence** | Are requests/limits/quotas managed via IaC, reviewed, and alerted? Are runbooks ready for OOMs, throttling, and quota errors? |
| **Security** | Could a tenant trigger denial of service via resource exhaustion? Are quotas, rate limits, resource boundaries, and least privilege enforced? |
| **Reliability** | Is headroom sufficient for node/AZ loss? Can noisy neighbors degrade critical SLOs? Have backpressure and recovery been tested? |
| **Performance Efficiency** | Is sizing grounded in representative benchmarks? Are CPU, memory, I/O, concurrency, and downstream bottlenecks monitored? |
| **Cost Optimization** | Are over-provisioning, idle capacity, runaway autoscaling, or costly IOPS/quotas controlled? |
| **Sustainability** | Are resources matched to load without oversized/idle nodes or unnecessary log/metric storage? |

A solid design proves **noisy workload impact stays bounded within acceptable limits**, while critical workloads retain enough capacity and limits protect budgets.

## 16. Pre-Production Checklist for Shared Compute

- [ ] Workloads classified by criticality, load pattern, tenant, and dependencies.
- [ ] SLIs/SLOs, baseline/peak loads, concurrency, and failure scenarios defined.
- [ ] Requests/reservations, limits, quotas, and concurrency distinguished with owners and rationale.
- [ ] Memory limits leave headroom for heap, native memory, sidecars, and peaks; CPU limits tested for throttling.
- [ ] Nodes/VMs reserve capacity for OS, agents, daemons, and single-node/zone loss.
- [ ] Storage IOPS/throughput, networking, connections, file descriptors, and quotas reviewed.
- [ ] APIs, workers, and batches enforce priority/fairness policies shielding critical workloads.
- [ ] DB connection pools, queue concurrency, and downstream quotas sized for max replicas.
- [ ] Autoscaling defines min/max, cooldowns/stabilization, headroom, and cloud quota checks.
- [ ] Backpressure, timeouts, bounded retries, load shedding, and idempotency configured.
- [ ] Metrics cover workload/node/downstream layers; alerts track SLOs plus starvation/noisy neighbors.
- [ ] Contention loads, OOM/throttling, node drain/failure, and quota exhaustion tested in controlled environments.
- [ ] Compute, storage, network, and reserve-capacity costs tracked.
- [ ] Resource policy exceptions carry expiration dates, approvers, and review schedules.

Setting resource limits is how an architecture **partitions capacity and bounds blast radius** across workloads. Limits too tight hurt availability; limits too loose expose critical workloads to interference and blow up budgets. Good outcomes come from measuring load profiles, selecting sound isolation boundaries, configuring requests/limits/quotas/concurrency, protecting downstreams, and testing under competing loads. As systems evolve, revisit numbers and policies against live SLOs, costs, and telemetry.
