# Node Pools, Machine Types, and Workload Separation by Demand

In Kubernetes, a Pod can only be scheduled onto a Node that has sufficient resources and satisfies the workload's constraints. If the entire cluster uses a single uniform group of machines, web applications, batch jobs, database caches, GPU workloads, and system components all compete for the same type of capacity. Organizing node pools by resource profile lets you choose the right machine types, isolate load, control costs, and preserve scalability.

A **node pool** is a group of Nodes managed under the same configuration or lifecycle policy, typically sharing a machine type, OS image, CPU architecture, deployment zone, labels, taints, and autoscaling limits. A cluster can have multiple pools: a system pool, a general-purpose application pool, compute-optimized, memory-optimized, GPU, Spot, or dedicated pools for sensitive workloads.

Choosing node pools is not just picking vCPU and RAM counts. It must be based on workload profiles, Kubernetes requests/limits, storage and networking, failure domains, autoscaling capabilities, security requirements, and budget. This lesson covers how to design node pools, select machine types, and separate workloads using standard Kubernetes scheduling mechanisms.

## 1. Nodes, Node Pools, and Clusters

### What Is a Node?

A Node is a compute machine running Kubernetes workloads. A Node can be a cloud VM, a physical server, or a provider-managed compute environment. Each Node typically runs:

- `kubelet` to communicate with the control plane and manage Pods.
- A container runtime such as `containerd`.
- `kube-proxy` or an equivalent dataplane mechanism.
- A CNI plugin to provide Pod networking.
- A CSI node plugin if the cluster uses persistent storage.
- System DaemonSets such as logging agents, monitoring agents, security agents, and networking components.

A Node has physical or virtualized resources such as CPU, memory, local disk, network, and accelerators. Kubernetes reports a portion of those resources as capacity and allocatable.

### Capacity and Allocatable

- **Capacity:** total resources visible and advertised by the Node.
- **Allocatable:** the portion of resources available for Pods after subtracting `system-reserved`, `kube-reserved`, and other configured reservations.
- **Requested:** total requests of Pods already placed on the Node by the scheduler.
- **Actual usage:** actual CPU/memory currently consumed by workloads.

For example, a Node has 16 vCPUs and 64 GiB of RAM, but after reserving resources for the OS and Kubernetes, allocatable capacity is 15 vCPUs and 58 GiB. The scheduler uses allocatable capacity to decide Pod placement and cannot assume all 16 vCPUs and 64 GiB are available for applications.

### What Is a Node Pool?

A node pool groups Nodes with similar configurations and policies. Depending on the platform, it may be called a node group, machine pool, agent pool, or managed node group.

A node pool typically manages:

- Machine type or instance family.
- CPU architecture and accelerators.
- OS image, kernel, and container runtime.
- Boot disk, local SSD, or ephemeral storage.
- Network interfaces and subnets.
- Availability zones or topology.
- Minimum, maximum, and desired node counts.
- Labels and taints.
- Upgrade strategies, autoscaling, and repair policies.

Exact names and capabilities vary across managed Kubernetes services. Distinguish standard Kubernetes objects from cloud-provider-specific resources.

### Multi-Node-Pool Cluster

~~~mermaid
flowchart TB
    CP["Kubernetes control plane"] --> CL["Cluster scheduler"]
    CL --> SYS["System pool"]
    CL --> GEN["General-purpose pool"]
    CL --> CPU["Compute-optimized pool"]
    CL --> MEM["Memory-optimized pool"]
    CL --> GPU["GPU / accelerator pool"]
    CL --> SPOT["Spot / interruptible pool"]
    SYS --> S1["DNS, monitoring, ingress, agents"]
    GEN --> G1["Web/API workloads"]
    CPU --> C1["CPU-heavy workers"]
    MEM --> M1["Cache, memory-heavy services"]
    GPU --> G1A["Training / inference jobs"]
    SPOT --> P1["Retryable batch jobs"]
~~~

The scheduler selects suitable Nodes based on requests, node selectors, affinity, taints/tolerations, topology constraints, and other policies. A node pool alone does not guarantee workloads land in the right group; you must declare the corresponding scheduling constraints.

## 2. Why Use Multiple Node Pools?

A cluster can use a single homogeneous pool if workloads are simple, resource profiles are similar, and operational simplicity is prioritized. When workloads diversify, multiple pools provide several benefits:

- **Resource alignment:** match CPU, RAM, disk, network, and GPU to application characteristics.
- **Reduced contention:** separate batch jobs or bursty workloads from latency-sensitive APIs.
- **Failure isolation:** capacity exhaustion or upgrades in one pool do not necessarily affect the whole cluster.
- **Cost optimization:** use smaller machines or Spot instances for retryable workloads; keep stable machines for critical services.
- **Security/compliance:** dedicate Nodes for workloads with compliance requirements, sensitive data, or specialized hardware.
- **Architecture separation:** run `amd64` and `arm64` workloads on corresponding Nodes.
- **Upgrade management:** upgrade images or kernels group by group, reducing blast radius.

### Trade-offs of Splitting Too Many Pools

Every pool increases the configuration footprint you have to manage:

- More machine types and images.
- More autoscaling policies and quotas.
- Potential empty or stranded Nodes caused by overly rigid workload constraints.
- Harder to balance Pod distribution and maintain sufficient capacity.
- More variants to patch, scan, and test.
- Higher administrative, monitoring, and upgrade overhead.

Do not create a separate pool for every single application if they share the same resource profile and operational requirements. Start with workload groups that clearly differ in compute, memory, accelerator, isolation, or availability needs.

## 3. Classifying Workloads by Resource Profile

Before choosing machine types, classify workloads based on empirical data.

### CPU-Bound

CPU-bound workloads spend most of their time computing:

- APIs performing data transformation or encryption.
- Video transcoding.
- Compression and decompression.
- Workers processing data or running model computations.
- Builds and compilation.
- Simulations or batch computations.

Signals:
- High, sustained CPU usage.
- Growing run queue as load increases.
- Throughput scales with CPU until saturation.
- Memory working set is not the primary bottleneck.
- Latency rises when CPU throttling or contention occurs.

Consider compute-optimized Nodes with strong CPUs, a high CPU-to-RAM ratio, and adequate networking. Check single-core performance if the workload has sequential phases.

### Memory-Bound

Memory-bound workloads require a large working set or frequent RAM access:

- In-memory caches.
- Search/indexing.
- Large JVM heaps.
- Data processing keeping many records in RAM.
- Analytics engines.
- Stateful services with large working sets.

Signals:
- High memory usage and working set.
- OOMs or evictions when RAM runs short.
- Increased GC or paging activity.
- CPU is not saturated, yet latency climbs due to memory pressure.
- Memory bandwidth or NUMA locality impacts performance.

Consider memory-optimized Nodes with high RAM per vCPU. Verify Pod memory limits, heap sizing, and Node allocatable limits.

### Storage-Bound

Storage-bound workloads depend on IOPS, throughput, or latency:

- Databases.
- Stateful workloads.
- Search indexes.
- Queue/log brokers.
- File processing.
- Workloads writing heavy logs or checkpoints.

Evaluate both the volume type and the Node. A Node with abundant vCPU/RAM cannot compensate for low volume IOPS. Check:
- Provisioned IOPS and throughput.
- Read/write latency.
- Queue depth.
- Local NVMe or ephemeral disks.
- Persistent volume topology.
- CSI driver and attachment limits.
- Durability and backups.

### Network-Bound

Network-bound workloads require high throughput or packet rates:

- API gateways and proxies.
- Service mesh sidecars with many connections.
- Streaming and message brokers.
- Cross-zone data transfers.
- Distributed storage.
- Network functions or packet processing.

Check bandwidth, packets-per-second, connection tracking, NIC limits, CNI overhead, MTU, NAT, and cross-zone traffic. A VM type with high CPU but a low network cap can still be a poor choice.

### GPU/Accelerator-Bound

GPU or accelerator workloads:
- Machine learning training/inference.
- Video processing.
- Rendering.
- Scientific computing.
- Certain encryption or vector-processing workloads.

Verify GPU model, VRAM, drivers, CUDA/ROCm or matching stack, device plugins, runtimes, node images, and quotas. Do not look only at GPU count; two accelerators of the same count can differ significantly in VRAM, bandwidth, and throughput.

### Mixed and Bursty Workloads

Some workloads have brief CPU bursts, steady memory working sets, or uneven I/O. Look at p95/p99 and peaks over time, not just averages. Bursty workloads may need headroom or fast autoscaling, but avoid keeping oversized machines running continuously if a queue can absorb spikes.

## 4. Choosing Machine Families and Instance Types

Cloud providers typically offer several common machine families. Family names differ, but the categories are generally similar.

| Machine Family | Characteristics | Suitable Workloads | What to Check |
|---|---|---|---|
| General-purpose | Balanced CPU and RAM | Web/API, microservices, control workloads | CPU/RAM ratio, network, and cost |
| Compute-optimized | Fast CPUs, high CPU/RAM ratio | CPU-bound, builds, transcoding | Single-core, sustained CPU, and quota |
| Memory-optimized | High RAM per vCPU | Caches, JVM, analytics, suitable databases | Allocatable RAM, NUMA, memory bandwidth |
| Storage-optimized | High IOPS/throughput or local disks | Data-intensive, local scratch, log processing | Durability, disk failure, and backups |
| Network-optimized | High bandwidth/packet capacity | Proxies, streaming, network-intensive | NIC limits, packet rate, and topology |
| GPU/accelerator | Equipped with accelerators | ML, rendering, HPC | GPU model, VRAM, drivers, and device plugins |
| Burstable | Baseline CPU with credits/burst | Dev/test or lightly bursty workloads | Credit balance, throttling, and sustained load |
| Arm-based | Arm64 CPU architecture | Portable and multi-arch workloads | Binaries, native libraries, images, and performance |

### Do Not Compare by vCPU Alone

When comparing two machine types, examine:
- CPU generation and architecture.
- Core/thread topology.
- Single-thread and multi-thread performance.
- RAM and memory bandwidth.
- Local disk and volume bandwidth.
- Network bandwidth and packet rate.
- GPU/accelerators.
- Regional pricing and pricing models.
- CPU credit or throttling policies.
- Quotas and zone availability.

One 8-vCPU VM may not perform like another 8-vCPU VM. Benchmarking the real workload provides a much sounder basis for decisions.

### Mixing Multiple Machine Types in One Pool?

A pool may support multiple equivalent instance types or shapes if the managed service allows it. Ensure they satisfy the same workload requirements:
- Compatible CPU architecture.
- Minimum RAM.
- GPU or device requirements.
- Network/storage capabilities.
- OS image and drivers.
- Matching capacity units/weights.

If a pool contains vastly different machines, the scheduler—looking only at requests—might place a Pod onto a smaller Node than the workload actually needs. Constrain placement using labels, resource classes, or separate pools.

## 5. Calculating Requests and Limits Before Node Sizing

The Kubernetes scheduler uses requests for placement. Limits are enforced by the runtime/cgroup while the Pod runs.

- **CPU request:** CPU amount used to evaluate Pod placement capacity.
- **CPU limit:** maximum CPU a container may consume per quota.
- **Memory request:** RAM reserved by the scheduler.
- **Memory limit:** memory threshold a container can use before OOM handling by the kernel/runtime.

Example:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: api-example
spec:
  containers:
    - name: api
      image: example.invalid/api:1.0
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
        limits:
          cpu: "2"
          memory: "1Gi"
~~~

In this example, the scheduler counts 500 millicores and 512 MiB of requests. The container may use up to 2 CPUs and 1 GiB of memory under the declared limits.

### Requests Too Low

If requests are lower than actual demand:
- The scheduler may pack too many Pods onto one Node.
- CPU/memory contention rises.
- Nodes may suffer eviction pressure or OOMs.
- Autoscalers misjudge capacity.
- Latency increases when concurrent workloads spike together.

### Requests Too High

If requests are higher than actual demand:
- Nodes appear full despite low actual usage.
- Pods stay Pending unnecessarily.
- Cluster autoscaler provisions extra Nodes.
- Bin packing degrades and costs rise.
- Some pools leave capacity underutilized.

### CPU Limits and Throttling

CPU limits protect Nodes from runaway CPU consumption, but limits set too low cause containers to be throttled even while the Node has idle CPU. For latency-sensitive workloads, measure CFS throttling and p95/p99 latency before setting tight limits.

### Memory Limits and OOM

Memory limits are hard boundaries. When a container exceeds its limit, the kernel may OOM-kill a process inside the container. Setting limits too close to peak memory can cause restarts during traffic bursts or before GC reclaims memory. Use working set, peaks, and runtime overhead to pick safe thresholds.

### QoS Classes

Kubernetes classifies Pods into:
- Guaranteed.
- Burstable.
- BestEffort.

QoS class depends on the requests/limits of the containers in the Pod. Guaranteed requires CPU and memory requests to equal limits for every container. QoS affects eviction order in certain node pressure scenarios, but it does not replace requests, limits, PDBs, or HA design.

## 6. Calculating Node Counts and Headroom

Suppose a pool has Nodes with 7.5 CPUs and 28 GiB RAM allocatable. The workload has total requests of 24 CPUs and 80 GiB RAM. Minimum Node count per dimension:

\[
N_{CPU} = \left\lceil \frac{24}{7.5} \right\rceil = 4
\]

\[
N_{Memory} = \left\lceil \frac{80}{28} \right\rceil = 3
\]

Capacity is constrained by the larger dimension, so at least 4 Nodes are required by simple aggregate math. However, this is not the final sizing.

You must add:
- DaemonSet and system Pod overhead.
- Pod fragmentation when requests do not pack cleanly onto Nodes.
- Pod anti-affinity or topology spread.
- Max Pods per Node and IP address capacity.
- Persistent volume topology.
- N-1 Node or AZ failure reserve.
- Rolling upgrade surge.
- Autoscaling delay.
- Burst and SLO headroom.

### Bin Packing and Fragmentation

The scheduler cannot always fill every remaining CPU/RAM slot because a Pod must fit both dimensions simultaneously along with other constraints. For example, a Node with 2 CPUs free but only 1 GiB RAM free cannot accept a Pod requesting 1.5 CPUs and 2 GiB RAM.

Therefore, total requests divided by allocatable capacity is only a lower bound. Simulate or test scheduling with realistic Pod distributions.

### Capacity After Losing a Node

If a pool has 4 Nodes and each serves 25% of traffic, losing one Node reduces capacity by 25%. If you must continue serving full load after a Node failure, add headroom or standby Nodes. In multi-AZ setups, calculate remaining capacity after losing an entire zone, not just a single Node.

## 7. Separating Workloads with Labels and nodeSelector

Node labels are metadata describing Node attributes, such as:
- `node-pool`.
- `workload-class`.
- CPU architecture.
- Accelerator type.
- Storage profile.
- Zone.
- Compliance boundary.

Example of applying labels:

~~~sh
kubectl label node node-a workload-class=general
kubectl label node node-b workload-class=compute
kubectl label node node-gpu accelerator=nvidia
~~~

A Deployment can use `nodeSelector`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: video-worker
spec:
  replicas: 4
  selector:
    matchLabels:
      app: video-worker
  template:
    metadata:
      labels:
        app: video-worker
    spec:
      nodeSelector:
        workload-class: compute
      containers:
        - name: worker
          image: example.invalid/video-worker:2.1
          resources:
            requests:
              cpu: "4"
              memory: "8Gi"
            limits:
              cpu: "6"
              memory: "12Gi"
~~~

`nodeSelector` is a hard constraint: Pods can only run on Nodes possessing all specified labels. If no Node matches, Pods stay Pending.

### Use Platform-Managed Labels

For security or critical isolation properties, do not rely on arbitrary labels that users can modify themselves on Nodes. Use protected label namespaces and `NodeRestriction`/Node authorizer controls per cluster configuration. Verify admission policies and who is authorized to change labels.

## 8. Node Affinity and Pod Affinity

Node affinity provides more expressive rules than `nodeSelector`.

### requiredDuringSchedulingIgnoredDuringExecution

This is a hard constraint when the scheduler selects a Node. If no Node satisfies it, the Pod is not scheduled.

### preferredDuringSchedulingIgnoredDuringExecution

This is a soft preference. The scheduler tries to pick matching Nodes but can fall back to other Nodes if necessary.

Example preferring the compute pool while allowing fallback:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: report-job
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 80
          preference:
            matchExpressions:
              - key: workload-class
                operator: In
                values:
                  - compute
  containers:
    - name: report
      image: example.invalid/report:1.0
      resources:
        requests:
          cpu: "2"
          memory: "4Gi"
~~~

If hardware requirements are mandatory, use `required` affinity or `nodeSelector`. `preferred` affinity is not an isolation guarantee.

### Pod Affinity and Anti-Affinity

- **Pod affinity:** places Pods near another group of Pods within a topology scope, such as the same zone.
- **Pod anti-affinity:** avoids placing Pods from the same group on the same Node or topology domain.

Anti-affinity helps spread replicas but reduces bin-packing efficiency. In small clusters or node pools spanning too few zones, Pods may stay Pending.

Use precise label selectors and appropriate `topologyKey` values; avoid hard anti-affinity in capacity-constrained clusters unless genuinely needed.

## 9. Taints and Tolerations: Reserving Nodes for Matching Workloads

Labels and affinity help Pods select Nodes. Taints help Nodes repel Pods that lack matching tolerations.

Example tainting a GPU pool:

~~~sh
kubectl taint nodes node-gpu-1 dedicated=gpu:NoSchedule
~~~

A Pod needing a GPU can declare a toleration:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: inference
spec:
  tolerations:
    - key: dedicated
      operator: Equal
      value: gpu
      effect: NoSchedule
  nodeSelector:
    accelerator: nvidia
  containers:
    - name: model
      image: example.invalid/inference:3.0
      resources:
        limits:
          nvidia.com/gpu: 1
          cpu: "4"
          memory: "16Gi"
~~~

A toleration permits a Pod to be scheduled onto a tainted Node, but does not select the Node by itself. That is why the example also uses `nodeSelector` to require the `accelerator` label.

### Taint Effects

- **NoSchedule:** the scheduler will not place new Pods onto the Node without a matching toleration.
- **PreferNoSchedule:** the scheduler tries to avoid the Node, but may place Pods there if needed.
- **NoExecute:** Pods without a toleration may be evicted from the Node; Pods with a toleration may specify `tolerationSeconds`.

Some taints are added automatically by Kubernetes or the node lifecycle controller, such as `node.kubernetes.io/not-ready` or `unreachable`. Understand system taints carefully; do not add broad tolerations that mask unhealthy Nodes.

### Dedicated Node Pools

A dedicated pool for specific workloads can combine:
- Labels so target workloads select the pool.
- Taints so other workloads stay out of the pool.
- RBAC/admission policies to restrict who can add the toleration.
- Resource quotas to govern tenants.
- Network policies and security contexts to strengthen isolation.

Taints/tolerations are only a scheduling mechanism, not a complete security boundary. Privileged Pods or cluster-admin permissions can still undermine isolation goals if policies are not enforced.

## 10. Separating System Pools and Application Pools

A production cluster commonly separates:

### System Pool

Runs platform components:
- CoreDNS or DNS services.
- Metrics/monitoring agents.
- Ingress or gateway controllers.
- CNI/CSI components.
- Cluster autoscaler or node management agents.
- Security and logging agents.
- Required add-ons.

This pool needs enough capacity so cluster management components remain operational when application pools are overloaded or scaled down. Do not undersize the system pool; DaemonSets and control workloads can require substantial resources.

### User/Application Pools

Run product workloads:
- APIs and frontends.
- Background workers.
- Batch jobs.
- Stateful apps if the architecture supports them.
- GPU jobs.
- Tenant-specific workloads.

You can have multiple pools by profile, while ensuring required system DaemonSets are permitted to run on each pool as needed.

### Why Not Just One Pool?

If batch workloads saturate Nodes, CoreDNS or ingress controllers can be starved of resources. Separating system and app pools reduces contention and preserves a recovery path during application incidents.

### Why Not Undersize the System Pool?

If the system pool lacks capacity for DNS, ingress, or monitoring, the cluster can lose manageability and observability precisely during peak load. Capacity planning must include system DaemonSets, rollouts, and N-1 failures.

## 11. Pools by CPU Architecture: amd64 and arm64

A cluster can include Nodes of multiple architectures. This is useful when certain workloads support Arm64 and achieve better price/performance.

Verify:
- Images have manifests for `linux/amd64` and `linux/arm64`.
- Native libraries and agents support the architecture.
- JDK/runtime versions.
- CNI, CSI, security DaemonSets, and monitoring agents.
- Sidecar binaries.
- CPU features and benchmarks.
- Node labels such as `kubernetes.io/arch`.

Example selecting architecture:

~~~yaml
spec:
  nodeSelector:
    kubernetes.io/arch: arm64
~~~

Do not schedule workloads onto Arm64 just because the image pulls cleanly. Test native dependencies, performance, cryptography, JIT behavior, and operational agents on real Nodes.

You can maintain an `amd64` pool for non-portable workloads and an `arm64` pool for validated workloads. This allows incremental migration without converting the entire cluster at once.

## 12. GPU and Accelerator Pools

GPU Nodes require additional configuration beyond the machine type:
- GPU model and VRAM.
- Kernel drivers.
- CUDA/ROCm or matching runtime.
- Device plugin or GPU operator.
- Container toolkit.
- Images with matching library versions.
- Node labels and taints.
- Quotas and autoscaling policies.

Kubernetes device plugins advertise extended resources such as `nvidia.com/gpu`. Pods request those resources in `limits` as supported by the plugin.

Example:

~~~yaml
resources:
  limits:
    nvidia.com/gpu: 1
    cpu: "8"
    memory: "32Gi"
~~~

GPU resources are typically allocated in whole devices or vendor-specific sharing modes. Do not assume CPU requests or GPU utilization automatically reflect VRAM and memory bandwidth needs.

### GPU Scheduling and Fragmentation

GPUs can be wasted if Pods request a full GPU while using only a small fraction. Some platforms support time-slicing or MIG partitioning, with different semantics and isolation guarantees. Check:
- VRAM demand.
- GPU compute utilization.
- GPU memory utilization.
- Batch size.
- Concurrent model count.
- Device sharing policies.
- Failure and reset behavior.

Do not place non-accelerator workloads on GPU pools when cost and capacity constraints are high.

## 13. Spot/Preemptible Pools and Interruptible Workloads

Spot or preemptible Nodes cost less but can be reclaimed. Suitable for:
- Retryable batch jobs.
- Stateless workers.
- Build/test jobs.
- Checkpointed data processing.
- Queue consumers that can drain and resume.

Do not place strict-availability workloads or state stored solely on local disk onto easily preemptible pools without recovery mechanisms.

### Designing Interruption-Tolerant Workloads

- Use durable queues.
- Make tasks idempotent.
- Checkpoint periodically.
- Handle graceful termination.
- Retry with backoff and limits.
- Set appropriate PodDisruptionBudgets.
- Maintain fallback to an on-demand pool.
- Monitor interruption notices and job completion.

Spot pools can use taints so regular workloads are not placed there. Interruption-tolerant workloads declare the corresponding tolerations and node affinity.

### Do Not Treat PDBs as a Shield Against Every Interruption

PodDisruptionBudgets primarily govern voluntary disruptions via the eviction API. They do not prevent all forms of node failure or involuntary disruptions. Applications must still tolerate Pod loss and job reassignment.

## 14. Zone and Topology Pools

Node pools can span multiple availability zones or be split into per-zone pools, depending on the managed service.

Consider:
- Zone capacity and quotas.
- Persistent volume zone binding.
- Pod topology spread.
- Pod anti-affinity.
- Cross-zone load balancing.
- Network latency and egress costs.
- Failure scenarios when losing an entire zone.

### Topology Spread Constraints

Example spreading replicas across zones:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 6
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api
      containers:
        - name: api
          image: example.invalid/api:1.0
          resources:
            requests:
              cpu: "1"
              memory: "1Gi"
~~~

If one zone runs out of capacity, `DoNotSchedule` can leave Pods Pending to preserve distribution. Use `ScheduleAnyway` if running the workload takes priority over strict balance. Choose the policy based on availability requirements and actual zone count.

### Storage Topology

Persistent volumes may be bound to a specific zone. Pods with affinity requiring another zone may fail to schedule. Use an appropriate `StorageClass` and volume binding mode; understand that local PVs typically pin Pods to a Node or zone and require a data recovery plan.

## 15. Node Pool Autoscaling

Autoscaling can operate at two layers:

- **Horizontal Pod Autoscaler (HPA):** adjusts workload replica counts.
- **Cluster/node autoscaler:** adds or removes Nodes in response to Pending Pods or excess capacity.

HPA does not create Nodes directly. If a Pod needs 4 CPUs and no Node has enough allocatable CPU, the Pod may remain Pending until the node autoscaler provisions suitable capacity.

### Per-Pool Min/Max

Each pool needs:
- A minimum to maintain baseline and system capacity.
- A maximum bounded by peak load, quotas, and dependency budgets.
- Desired/current counts.
- Autoscaling signals and cooldowns.
- Upgrade surge and failure reserves.

A maximum set too low leaves Pods Pending under load spikes. A maximum set too high can drive runaway costs or hit quotas. Set max based on capacity testing and database/network limits, not CPU demand alone.

### Scale from Zero

Some node autoscalers can scale a pool from zero if they recognize the labels/resources requested by Pending Pods. Verify:
- Pods declare the right node selector/affinity.
- The autoscaler recognizes taints and extended resources.
- Machine images and drivers are ready.
- Provisioning and warm-up times.
- Quotas and zone capacity.

Scaling a GPU pool from zero can take several minutes. If workloads need low startup latency, keep a minimum count or warm capacity.

### Scale-Down and Consolidation

When Nodes are underutilized, the autoscaler can drain and terminate them. However, Pods with PDBs, local storage, affinity rules, or disruption constraints can block scale-down.

Monitor:
- Node utilization and allocatable requests.
- Pod eviction and drain durations.
- Empty/underutilized node durations.
- Scale-up latency.
- Pending Pod age.
- Cost and interruptions.

Do not remove Nodes based solely on low average CPU if Pod requests are high or workloads experience bursts.

## 16. Upgrades and Maintenance by Node Pool

Separating pools allows group-by-group upgrades, though disruption must still be managed.

### Rolling Upgrades

The typical workflow includes:
1. Provisioning or upgrading new Nodes.
2. Waiting for Nodes to become Ready.
3. Draining old Nodes.
4. Evicting Pods per policy.
5. Waiting for workloads to reschedule onto new Nodes.
6. Confirming readiness and service health.
7. Removing old Nodes.

Depending on the provider, upgrades may use surge Nodes or `maxUnavailable`. Account for quotas and capacity while both old and new Nodes coexist.

### PodDisruptionBudget

A PDB sets the minimum available Pods or maximum disruption budget for voluntary evictions. PDBs do not replace replica counts, readiness probes, or HA application design. If a PDB is too strict, upgrades or scale-downs can stall.

### Pool Drift

Nodes in the same pool can drift in versions due to partial rollouts, autoscaling, or manual changes. Track:
- Kubernetes version.
- Node image version.
- Kernel and runtime.
- CNI/CSI agents.
- Security patches.
- Labels/taints.
- Instance types and zones.

Use immutable images and structured rollout processes to minimize drift. Never manually edit a single Node in ways that diverge from the pool configuration.

## 17. Security and Workload Isolation

Node pools can serve as one layer of separation, but they do not form a complete security boundary on their own.

### Scheduling Isolation

Combine:
- Labels and node affinity.
- Taints and tolerations.
- Dedicated pools.
- Namespaces and RBAC.
- Admission policies restricting tolerations.
- `ResourceQuota` and `LimitRange`.
- Pod Security Standards.
- `NetworkPolicy`.
- Scoped secrets and service accounts.

### Dedicated Nodes for Sensitive Workloads

Dedicated pools can be reserved for:
- Workloads processing sensitive data.
- License-bound workloads.
- GPUs/accelerators.
- Workloads requiring specific kernels or drivers.
- Workloads with noisy-neighbor risks.
- Workloads governed by placement policies.

Verify who is allowed to create Pods tolerating a taint and who is allowed to modify Node labels. If any tenant can add the toleration for a dedicated pool, isolation loses its value.

### Host-Level Security

Node pools need:
- Hardened OS images.
- Patch cadences.
- Disk encryption.
- Metadata access controls.
- Least-privilege node identities.
- Container runtime security.
- Auditing and monitoring.
- Node replacement procedures upon compromise.

Do not co-locate untrusted workloads on the same Node as sensitive workloads relying solely on namespaces. Namespaces are API management scopes, not kernel isolation.

## 18. ResourceQuota, LimitRange, and Namespace Limits

Node pools govern where Pods run; quotas limit how many resources a tenant or namespace may request.

### ResourceQuota

Example capping total requests and Pod count:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-quota
  namespace: team-a
spec:
  hard:
    requests.cpu: "40"
    requests.memory: 80Gi
    limits.cpu: "80"
    limits.memory: 160Gi
    pods: "100"
~~~

Quotas prevent one namespace from consuming the entire cluster's capacity. They do not guarantee the node pool actually has those resources, nor do they replace autoscaling.

### LimitRange

`LimitRange` can apply default requests/limits and min/max bounds for containers in a namespace. This reduces the risk of workloads omitting resource fields or requesting excessive amounts.

### Aligning Quotas and Node Capacity

When designing for multiple teams:
- Sum quotas across namespaces.
- Calculate pool capacities.
- Subtract system overhead.
- Reserve headroom for scaling and failures.
- Monitor unused quota vs. reserved capacity.
- Check whether Pods are Pending due to quota or Node constraints.

Pods can stay Pending for many reasons; read scheduler events before adding Nodes.

## 19. Example Design: Cluster for APIs, Batch, and GPUs

A product runs:
- Latency-sensitive APIs.
- CPU-bound file-processing workers.
- GPU-backed ML inference jobs.
- System add-ons.

A candidate design:

| Pool | Machine Profile | Taint/Label | Workloads |
|---|---|---|---|
| `system` | General-purpose, steady capacity | `node-role=system` | DNS, ingress, monitoring, agents |
| `api` | General-purpose, multi-zone, on-demand | `workload-class=api` | APIs and frontends |
| `compute` | Compute-optimized | `workload-class=compute` | File processing, CPU batch |
| `gpu` | GPU/accelerator | `dedicated=gpu:NoSchedule` | Inference/training |
| `spot-batch` | Compute-optimized Spot | `capacity-type=spot:NoSchedule` | Retryable jobs |

### API Pool

- Maintain minimum capacity for baseline load and N-1.
- Spread replicas across zones.
- Size requests/limits using p95/p99 data.
- Avoid overly low CPU limits that trigger throttling.
- Use PDBs for rollouts.
- Keep batch jobs off this pool.

### Compute Pool

- Use larger requests and bounded queue workers.
- Scale based on queue depth or Pending job count.
- Use Spot if jobs are idempotent/checkpointed.
- Cap concurrency to protect databases and storage.

### GPU Pool

- Only Pods needing accelerators tolerate the taint.
- Pin driver/device plugin versions.
- Monitor VRAM and GPU utilization.
- Enforce clear quotas and max node limits.
- Keep warm capacity if cold starts are too slow.

### System Pool

- Provision enough capacity for DaemonSets and control workloads.
- Do not scale to zero if the cluster needs continuous system services.
- Include upgrade headroom.
- Monitor Node pressure and DNS/ingress health.

## 20. Inspection and Diagnostic Commands

Inspect Nodes and labels:

~~~sh
kubectl get nodes -o wide --show-labels
kubectl describe node node-a
kubectl get nodes -L kubernetes.io/arch,topology.kubernetes.io/zone,workload-class
~~~

Inspect resources:

~~~sh
kubectl top nodes
kubectl top pods -A
kubectl describe pod api-7c8d9 -n production
kubectl get events -A --sort-by=.lastTimestamp
~~~

Inspect requests/limits and placement:

~~~sh
kubectl get pods -A -o wide
kubectl get pod api-7c8d9 -n production -o yaml
kubectl describe node node-a
~~~

Inspect taints:

~~~sh
kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints
~~~

Inspect GPU resources if advertised by a device plugin:

~~~sh
kubectl describe node gpu-node-1
kubectl get pods -A -o wide
~~~

### Reading Scheduling Errors

Common messages:
- `Insufficient cpu`.
- `Insufficient memory`.
- `Untolerated taint`.
- `Node affinity/selector mismatch`.
- `Too many pods`.
- `Volume node affinity conflict`.
- `Pod topology spread constraint`.
- `Node not ready` or `cordoned`.
- `Resource quota exceeded`.

Do not treat every Pending Pod by simply adding Nodes. Identify which constraint failed first, then fix requests, labels, taints, storage topology, or capacity in the right place.

## 21. Monitoring Effectiveness per Node Pool

A per-pool dashboard should track:

| Group | Metrics | Purpose |
|---|---|---|
| Capacity | Node count, allocatable CPU/memory, min/max | Know provisioned capacity |
| Scheduling | Pending Pods, unschedulable reasons, scheduling latency | Detect pool shortages or misconfigured constraints |
| Utilization | CPU/memory usage, request-to-allocatable ratio | Assess over/under-provisioning |
| Pressure | CPU throttling, memory pressure, disk pressure, evictions | Detect saturated Nodes |
| Scaling | Scale-up/down events, node provisioning time | Measure responsiveness |
| Availability | Ready Nodes, zone distribution, PDB disruptions | Evaluate fault tolerance |
| GPU | GPU utilization, VRAM, allocated devices | Optimize accelerators |
| Cost | Node-hours, instance types, Spot interruptions | Analyze spend |
| Operations | Upgrade status, image drift, patch level | Control lifecycle |

Measure each pool separately. A cluster showing 35% average CPU utilization may simultaneously have a GPU pool near 0%, a memory-saturated API pool, and an idle CPU batch pool. Aggregate numbers hide where optimization is needed.

### Unit Cost

You can measure:
- Cost per successful API request.
- Cost per completed batch job.
- Cost per GB processed.
- Cost per GPU inference.
- Cost per tenant or workload.

When allocating node costs, pick a clear cost driver such as CPU/memory requests, actual usage, or reserved capacity. Shared system overhead and idle headroom should also be allocated by policy.

## 22. Common Design Mistakes

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Pod Pending despite free cluster CPU | Pool lacks matching labels or enough RAM | Inspect events, affinity, and per-Node allocatable capacity |
| API latency spikes when batch runs | Both workloads contend on the same Nodes | Separate pools, add taints and affinity |
| Low CPU usage yet Pod throttles | CPU limit set too low | Check throttled time and adjust limits |
| Node has low memory, Pod OOMs | Mis-sized requests/limits or working set | Measure peak usage, heap, and memory pressure |
| GPU Node idle while jobs stay Pending | Driver/device plugin or taint/toleration mismatch | Verify extended resources and scheduling rules |
| Spot Node preemption fails jobs | Jobs lack checkpointing or idempotency | Use durable queues, retries, and graceful termination |
| New Node provisioned but Pod won't schedule | Node image/arch/taint mismatch | Check labels, runtime, and image manifests |
| Scale-out lags behind load | Slow provisioning and bootstrap | Keep warm capacity, trigger scaling earlier |
| Multiple pools have empty Nodes | Over-segmented pools or overly strict affinity | Merge similar profiles, use preferred affinity where suitable |
| Upgrades get stuck | Overly strict PDBs or disruption constraints | Check replicas, PDBs, and surge capacity |

### Avoiding Over-Segmentation

If every workload gets its own pool, the cluster ends up with stranded idle capacity and poor autoscaling. Only split pools when there is a measurable reason:
- Different resource profile.
- Different architecture or accelerator.
- Different isolation requirement.
- Different availability or interruption tolerance.
- Different lifecycle or policy.

## 23. Node Pool Design Process

1. **Inventory workloads:** list services, batch jobs, stateful workloads, GPUs, and system add-ons.
2. **Measure profiles:** CPU, memory working set, storage I/O, networking, peaks, and durations.
3. **Define SLOs:** latency, throughput, availability, and recovery targets.
4. **Select machine families:** general, compute, memory, storage, network, GPU, or Arm.
5. **Define pool boundaries:** system, application, dedicated, Spot, and architectures.
6. **Set requests/limits:** based on measurements and headroom.
7. **Design scheduling:** labels, `nodeSelector`, affinity, taints, tolerations, and topology spread.
8. **Size capacity:** allocatable, DaemonSet overhead, fragmentation, N-1, and rollout surge.
9. **Configure autoscaling:** min/max, scale signals, cooldowns, and warm capacity.
10. **Establish isolation:** RBAC, admission, quotas, Pod Security, and NetworkPolicies.
11. **Test:** scheduling, load, node failures, AZ failures, Spot interruptions, and upgrades.
12. **Measure cost:** node-hours, utilization, unit cost, and idle capacity.
13. **Operate:** monitor drift, patches, capacity, and periodically review pools.

### Acceptance Criteria

A node pool design is ready for production when:
- Every pool has a clear workload profile and owner.
- Machine types satisfy CPU/RAM/storage/network/GPU needs.
- Requests/limits are backed by measured data.
- Pods schedule onto their intended pools.
- Unauthorized workloads are blocked from dedicated pools by taints/policies.
- System services and DaemonSets have sufficient capacity.
- Autoscalers operate within min/max bounds and quotas.
- The cluster survives defined failure scenarios.
- Upgrades/drains do not breach SLOs.
- Dashboards show capacity, pressure, scaling, and cost per pool.

## 24. Node Pool and Workload Separation Checklist

### Pool Design
- [ ] Inventoried and classified CPU-bound, memory-bound, storage-bound, network-bound, GPU, and burst workloads.
- [ ] Decided the minimum necessary number of pools.
- [ ] Selected machine families based on benchmarks.
- [ ] Verified CPU architectures and native dependencies.
- [ ] Defined OS images, kernels, runtimes, and drivers.
- [ ] Calculated allocatable capacity after `system`/`kube` reservations.
- [ ] Accounted for DaemonSets, Pod density, and IP capacity.
- [ ] Budgeted headroom, N-1 reserves, and rolling upgrade surge.

### Scheduling and Isolation
- [ ] Labels have naming conventions and clear owners.
- [ ] `nodeSelector`/affinity are applied appropriately for required vs. preferred placement.
- [ ] Taints/tolerations restrict dedicated pools.
- [ ] RBAC/admission policies govern who may use privileged tolerations.
- [ ] Topology spread distributes replicas across failure domains.
- [ ] PDBs align with upgrade and availability requirements.
- [ ] Namespace quotas and `LimitRange` policies are configured.
- [ ] `NetworkPolicy` and security contexts satisfy isolation requirements.

### Autoscaling and Operations
- [ ] HPA and node autoscalers have distinct, coordinated targets.
- [ ] Node pool min/max values align with load and quotas.
- [ ] Scale-from-zero is tested if used.
- [ ] Spot workloads implement checkpointing, retries, and graceful shutdown.
- [ ] Upgrades support surge, drain, and rollback.
- [ ] Per-pool dashboards track capacity, usage, pressure, and cost.
- [ ] Alerts exist for Pending Pods, Node `NotReady`, throttling, and quotas.
- [ ] Processes exist to review empty pools, drift, and image patching.
- [ ] Unit cost is measured per successful output.

## Conclusion

Node pools allow organizing Kubernetes compute into groups of Nodes whose machine types, architectures, deployment zones, and lifecycle policies fit each workload. CPU-bound, memory-bound, storage-bound, network-bound, and GPU workloads should be matched to resources based on measured profiles. Requests/limits help the scheduler and runtime manage capacity; labels, affinity, taints/tolerations, and topology spread control where Pods run and how they are distributed. Separating system, application, dedicated, and Spot pools reduces contention, improves isolation, and optimizes cost, though too many pools increase fragmentation and operational burden. Good designs should be validated through scheduling tests, load tests, failure/upgrade rehearsals, and per-pool cost dashboards.
