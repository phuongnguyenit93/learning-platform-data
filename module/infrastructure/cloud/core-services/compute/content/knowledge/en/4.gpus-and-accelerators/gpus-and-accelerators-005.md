# GPU Partitioning and Sharing Resources Across Multiple Workloads

GPUs contain thousands of parallel processing units and high memory bandwidth, making them well suited for tasks such as AI model training, inference, image processing, simulation, and data analytics. However, a GPU represents a significant capital investment, and not every workload saturates the entire device at all times. If every workload occupies an entire GPU exclusively, substantial capacity sits idle. Conversely, if multiple workloads share one GPU without controls, they can contend for compute, memory, and bandwidth, degrading stability.

**GPU partitioning** and **GPU sharing** are ways to organize device usage across multiple processes, containers, virtual machines, or users. Several granularity levels exist: assigning a whole GPU to one workload, time-slicing, runtime concurrency mechanisms, hardware partitioning, or GPU virtualization. Each approach carries distinct isolation, performance, complexity, and cost characteristics.

This lesson belongs to the **GPUs and Accelerators** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module helps learners understand cloud compute models from virtual machines and containers to serverless; how to choose CPU, memory, networking, and security configurations; and how to deploy applications, scale under load, ensure availability, and optimize operational costs. Within that scope, knowing how to share GPUs improves utilization, allocates appropriate capacity, and controls costs when multiple workloads need acceleration.

## 1. What Types of Resources Does a GPU Have?

A GPU is not just a single metric such as device count. A workload can be constrained by one or more internal GPU resources:

- **Compute units:** processing engines such as Streaming Multiprocessors (SMs) on NVIDIA GPUs or equivalent compute clusters on other architectures. They execute parallel threads or wavefronts.
- **GPU memory (VRAM):** stores tensors, input data, model weights, activations, buffers, and application state.
- **Memory bandwidth:** the rate at which data moves between compute units and VRAM.
- **Caches and shared memory:** facilitate data reuse, reduce VRAM accesses, and coordinate across threads.
- **Copy engines and data transfer capacity:** handle copies between host memory and GPU memory, or between GPUs.
- **Inter-device interconnects:** PCIe, NVLink, or equivalent technologies affecting data transfers between GPUs and CPUs or across GPUs.
- **Power and thermal limits:** can affect clock speeds and sustained performance under prolonged load.

Two workloads sharing one GPU may contend on different resources. A small-batch inference task may use little compute yet require memory to keep the model resident. A training task may consume heavy compute, VRAM, and memory bandwidth over extended periods. Looking solely at overall GPU utilization may be insufficient to diagnose slowdowns.

### 1.1. Compute and VRAM Are Distinct Limits

A GPU can have spare compute capacity while nearly exhausting VRAM. In that state, a new workload cannot allocate enough memory even though the utilization graph is well below 100%. Conversely, a GPU may have ample VRAM while compute units are saturated, causing new workloads to queue or run slowly.

Distinguish between:

- **GPU utilization:** how busy part or all of the device is over a measurement window; exact definitions depend on the tool and vendor.
- **Memory utilization:** how much VRAM capacity is currently allocated.
- **Memory bandwidth utilization:** how heavily memory bus bandwidth is saturated.
- **SM/compute utilization:** how busy the processing units are.
- **Queueing and latency:** time a workload waits for resources before executing.

An effective GPU sharing system must consider these limits together alongside application latency requirements and isolation needs.

## 2. GPU Allocation and Sharing Models

### 2.1. Exclusive Allocation

In this model, one workload receives an entire GPU for its runtime duration. The scheduler or cloud platform ensures that device is not allocated to another workload within the same management scope.

**Advantages:**

- More predictable performance since the workload controls the whole device.
- Avoids compute and VRAM contention with other workloads on the same GPU.
- Well suited for large training jobs, latency-sensitive workloads, or applications needing the full device memory.
- Easier to analyze and isolate root causes during performance issues.

**Limitations:**

- The GPU can sit idle when the workload is not continuously active.
- Small workloads may underutilize compute and VRAM.
- Concurrent workload count is capped by physical GPU count.
- Cost per request or job can be high if the device is routinely underutilized.

Exclusive allocation does not automatically guarantee secure access or isolation across every layer. Combine it with appropriate device permissions, container runtimes, host access controls, and security policies.

### 2.2. Time-Slicing

**Time-slicing** allows multiple processes or workloads to share a single GPU by alternating execution time slices. While one workload runs, others wait their turn. The driver and GPU scheduler manage context switching between jobs according to platform mechanisms.

This model helps when multiple workloads have small, intermittent loads or do not need the entire GPU simultaneously. For example, several internal inference services receiving sporadic requests throughout the day can share a device instead of each holding a dedicated GPU.

~~~mermaid
gantt
    title Illustration of Time-Sliced GPU Sharing
    dateFormat X
    axisFormat %s
    section GPU
    Workload A :a1, 0, 3
    Workload B :b1, 3, 2
    Workload C :c1, 5, 2
    Workload A :a2, 7, 2
    Workload B :b2, 9, 2
~~~

The diagram only illustrates alternation. Time-slice duration, priority policies, concurrency behavior, and context switching depend on the driver, runtime, and platform. Do not assume every system uses strict round-robin scheduling with fixed slice lengths.

**Advantages:**

- Increases the number of workloads able to access a single GPU.
- Improves utilization when workloads have idle gaps.
- Can reduce the number of GPUs required for small services.
- Relatively simple to deploy on several container platforms.

**Limitations:**

- Performance and latency can fluctuate due to contention.
- Heavy workloads can slow down co-located workloads.
- Does not automatically partition VRAM into isolated regions.
- Does not provide fault or security isolation equivalent to hardware partitioning.
- A workload that over-allocates memory can impact other workloads.

Time-slicing is generally suitable for workloads that can tolerate variable latency and have application-level resource limits. It is not the default choice for workloads requiring strict latency SLOs or strong isolation.

### 2.3. Sharing via NVIDIA Multi-Process Service (MPS)

**NVIDIA Multi-Process Service (MPS)** is a mechanism that lets multiple CUDA processes share a GPU through a common coordination service. MPS can reduce CUDA context-switching overhead and allow kernels from multiple processes to execute concurrently on the GPU when resources remain available.

MPS is useful when multiple processes run small kernels or lack enough load individually to saturate the GPU. Rather than each process maintaining an independent context with wasted overhead, MPS helps combine work to raise utilization.

Key points to understand:

- MPS is a runtime/driver-level execution-sharing mechanism, not hardware partitioning.
- Multiple processes still share the physical GPU and device resources.
- Active thread percentages or client resource limits can be configured according to MPS version capabilities.
- MPS does not create physically isolated VRAM regions per workload.
- MPS does not provide the fault, security, or performance isolation of GPU partitioning technologies like MIG.
- Support, behavior, and limits depend on the GPU, driver, CUDA version, and deployment setup.

For instance, three inference processes with small batches can leverage MPS to schedule kernels onto the GPU more efficiently. However, if one process consumes most of the VRAM or runs long kernels, other processes can still be affected.

MPS must be tested with realistic workloads. Monitor VRAM, utilization, latency, and client errors, and verify how the MPS daemon is started, permissioned, and monitored in your deployment environment.

### 2.4. Hardware Partitioning with Multi-Instance GPU (MIG)

**Multi-Instance GPU (MIG)** is an NVIDIA technology on supported GPUs that splits a single physical GPU into multiple GPU instances. Each instance receives a dedicated subset of hardware resources, including compute and a slice of memory along with associated components, according to supported profiles.

Unlike time-slicing or MPS, MIG creates separate hardware partitions. This gives workloads stronger performance predictability and isolation compared to software sharing on the same device.

~~~mermaid
flowchart TB
    G["A physical GPU supporting MIG"]
    G --> P1["GPU Instance 1"]
    G --> P2["GPU Instance 2"]
    G --> P3["GPU Instance 3"]
    P1 --> C1["Workload A"]
    P2 --> C2["Workload B"]
    P3 --> C3["Workload C"]
~~~

The diagram is conceptual. Instance counts, profile sizes, and valid partition combinations depend on the GPU model, hardware generation, and supported MIG configurations. Not all NVIDIA GPUs support MIG.

Profiles are typically expressed by compute slice ratio and memory capacity, such as names like 1g.5gb or 2g.10gb on certain GPU lines. These are naming examples only; actual capacities and profiles vary by model. Check the official documentation for your specific GPU before designing partitions.

**Advantages:**

- Separates compute and memory into distinct GPU instances per profile.
- Improves workload isolation compared to software sharing.
- Helps schedule smaller workloads onto the same physical GPU.
- An instance's performance is far less affected by compute usage in another partition than under software sharing.
- Can increase performance predictability and resource allocation clarity.

**Limitations:**

- Supported only on specific GPU models and profiles.
- Partitions come in discrete sizes, which can leave unused capacity or make profile packing awkward.
- Certain GPU features, operating modes, or management tools have restrictions when MIG is enabled.
- Changing MIG configurations may require device reconfiguration and disrupt running workloads.
- MIG does not replace high-availability redundancy; the physical GPU remains a shared failure domain.

MIG fits well when multiple workloads must share a GPU while maintaining relatively strict hardware resource boundaries, such as multiple independent inference services or multiple teams with moderate GPU needs.

### 2.5. Virtualized GPUs (vGPU) and Sharing Across Virtual Machines

Some platforms support **vGPU** or GPU virtualization mechanisms so multiple virtual machines can access the same physical GPU. The hypervisor or GPU management layer exposes virtual devices to each VM, applying profiles, limits, or sharing policies per vendor solution.

Common approaches in virtualization ecosystems include:

- **PCI passthrough:** assigns the entire physical PCIe device directly to a single VM. This typically yields near-native performance, but the GPU cannot be concurrently shared across multiple VMs through standard mechanisms.
- **Mediated device/vGPU:** the hypervisor creates virtual GPU devices for VMs and mediates hardware access.
- **SR-IOV or similar mechanisms:** devices can expose separate virtual functions if supported by hardware and platform. Not all GPUs support this model.
- **GPU partitioning:** splits the device into units with dedicated resources, depending on hardware and software technology.

vGPU setups may require specialized drivers, compatible hypervisor versions, and commercial licensing. Before choosing, check GPU model, profile, guest OS, driver versions, VM count, licensed features, and performance limits.

Do not equate vGPU with MIG. vGPU is a model for exposing virtual GPU devices to VMs; MIG is a hardware partitioning technology on certain NVIDIA GPUs. Some solutions combine or build upon hardware partitioning features, but exact support depends on the product.

## 3. Comparing Sharing Methods

| Method | Core Mechanism | Resource Isolation | Best-Fit Use Cases |
|---|---|---|---|
| Exclusive GPU | One workload holds the entire GPU | High at device allocation level; still needs protection at other layers | Large training, latency-sensitive workloads, full VRAM needs |
| Time-slicing | Alternates execution time across multiple workloads | Low; shares VRAM and device resources | Small tasks, intermittent load, variable latency acceptable |
| NVIDIA MPS | Multiple CUDA processes coordinate via MPS server | Software sharing; no physical VRAM partitioning | Multiple small CUDA processes; GPU underutilized |
| NVIDIA MIG | Partitions GPU into hardware GPU instances | Higher than software sharing; profile-based compute and memory slices | Multi-tenant inference or workloads needing clear resource caps |
| vGPU | Hypervisor provides virtual GPUs to VMs | Depends on profile, hypervisor, and vendor solution | Multi-user VM infrastructure, VDI, or GPU workloads inside VMs |
| PCI passthrough | Assigns physical GPU directly to a VM | Device exclusively assigned to one VM | VMs needing near-native performance and direct GPU control |

This table provides high-level guidance. Consult vendor documentation to confirm support, isolation guarantees, limits, and licensing requirements for each method.

## 4. Sharing GPUs in Kubernetes

### 4.1. Device Plugins and Extended Resources

Kubernetes does not natively understand all GPU hardware specifics. To expose GPUs to Pods, vendors typically deploy a **device plugin**. The plugin discovers devices, advertises extended resources to kubelet, and assists in allocating devices when Pods are scheduled.

For NVIDIA GPUs, the resource is commonly named **nvidia.com/gpu**. A Pod can request one GPU:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-worker
spec:
  restartPolicy: Never
  containers:
    - name: worker
      image: registry.example.com/ml/worker:1.0.0
      resources:
        limits:
          nvidia.com/gpu: 1
~~~

This example assumes the node already has compatible drivers, NVIDIA Container Toolkit, and a running device plugin. Kubernetes schedules based on resource counts advertised by the plugin. It does not automatically split VRAM or throttle GPU usage inside containers.

For extended resources, GPUs are typically declared under **limits**; if **requests** are also specified, the values must match per Kubernetes resource rules. Refer to your deployed Kubernetes and device plugin versions.

### 4.2. Time-Slicing with the NVIDIA Device Plugin

The NVIDIA Kubernetes device plugin can be configured for time-slicing to advertise multiple logical slots per physical GPU. The example below illustrates a configuration advertising four logical replicas of one GPU:

~~~yaml
version: v1
sharing:
  timeSlicing:
    renameByDefault: true
    failRequestsGreaterThanOne: true
    resources:
      - name: nvidia.com/gpu
        replicas: 4
~~~

When **renameByDefault** is enabled, shared resources may be advertised under a name like **nvidia.com/gpu.shared** depending on plugin version and settings. Pods request one unit of the shared resource matching the name advertised on the node.

The configuration above is an example for the device plugin, not a Kubernetes Pod manifest. Administrators create a corresponding ConfigMap or configuration, attach it to nodes/plugin per version documentation, and verify advertised resources using **kubectl describe node**.

Time-slicing increases the number of schedulable workload slots, but it does not divide VRAM into isolated slices. If four Pods share one GPU, total VRAM remains the physical capacity of that single GPU. Processes can collectively over-allocate memory and trigger out-of-memory errors.

Specifically, logical replicas are not physical GPUs. If a node advertises four shared resources, the scheduler treats them as four allocatable units; this does not mean the device has four times the compute or memory.

### 4.3. MIG in Kubernetes

When GPUs support MIG, the device plugin can advertise GPU instances as distinct resources. Depending on configuration, nodes may advertise generic resources or specific profiles such as **nvidia.com/mig-1g.5gb**. Available names and profiles depend on the GPU, driver, MIG strategy, and plugin version.

A Pod requesting a corresponding profile looks like:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: inference-small
spec:
  restartPolicy: Never
  containers:
    - name: inference
      image: registry.example.com/ml/inference:1.0.0
      resources:
        limits:
          nvidia.com/mig-1g.5gb: 1
~~~

This is an illustrative example. Before using it, check that nodes actually advertise that exact resource name. If the profile does not exist or no matching instance remains free on any node, the Pod will stay Pending due to insufficient resources.

MIG must be configured at the GPU/node level before workloads request instances. Changing the MIG layout can disrupt workloads currently using the device. Manage configurations through controlled infrastructure workflows and re-verify after every change.

### 4.4. GPU Scheduling and Allocation

The Kubernetes scheduler primarily decides which node a Pod can land on based on declared resources and constraints. By default, the scheduler does not fully understand VRAM demands, SM usage, memory bandwidth, or priority between GPU processes.

When designing a cluster, consider:

- **Node pools:** separate nodes by GPU model, VRAM capacity, architecture, region, and intended purpose.
- **Extended resources:** declare the exact number of GPUs or GPU instances required by the Pod.
- **Node affinity and taints/tolerations:** direct workloads to the right node groups and prevent unintended usage of expensive devices.
- **MIG profiles:** pick profiles with enough VRAM and compute for each workload tier.
- **Priorities and quotas:** manage usage rights across teams, namespaces, or tenants.
- **Topology:** account for NUMA, PCIe, NVLink, and GPU placement for communication-heavy workloads.
- **Autoscaling:** scale node pools on demand while factoring in GPU provisioning times, quotas, and real capacity availability.

For workloads requiring multiple GPUs simultaneously, specify GPU count, topology, and inter-GPU communication needs. Provisioning enough devices on mismatched nodes or topologies can severely degrade distributed training performance.

## 5. Memory Protection and Isolation Levels

### 5.1. VRAM Is Not Automatically Divided by Percentage

A common misconception is that splitting a GPU into four time-sliced slots automatically caps each workload at 25% of VRAM. This is not the default behavior. Time-slicing only increases the logical slots advertised by the scheduler or device plugin; processes still share physical GPU memory.

Similarly, MPS coordinates multiple CUDA processes but does not turn VRAM into isolated hardware partitions. One process can allocate more memory than expected and cause failures for co-located processes.

MIG can provide profile-based memory partitioning on supported GPUs. It is a better choice when hardware-enforced VRAM and compute bounds are required, though you must still verify the exact limits of each profile.

### 5.2. Performance Isolation and Fault Isolation

There are at least three dimensions of isolation to consider:

1. **Resource isolation:** limiting the compute, memory, or bandwidth a workload can consume.
2. **Performance isolation:** preventing other workloads from altering a running workload's latency or throughput.
3. **Fault and security isolation:** preventing a crashing process or unsafe operation from affecting other workloads.

Exclusive GPUs are generally more predictable at the device level. MIG improves isolation through hardware partitioning. Time-slicing and MPS are software sharing, offering lower isolation and requiring tighter controls at the application, OS, and platform layers.

Even with MIG, the physical GPU, node, driver, and power supply remain shared failure domains. Do not treat GPU partitioning as hardware redundancy.

### 5.3. Tenant Isolation and Security

When multiple teams or customers share GPUs, define clear trust boundaries:

- Grant device access only to authorized containers or VMs.
- Do not mount host management sockets or elevated host privileges into untrusted workloads.
- Maintain GPU drivers and runtimes on supported versions.
- Restrict access to data, models, checkpoints, and secrets.
- Separate namespaces, service accounts, network policies, and quotas per tenant.
- Verify scrubbing or sanitization of sensitive data when reassigning devices.
- Use partitioning and virtualization mechanisms validated by the provider for multi-tenant environments.

Do not place untrusted workloads onto the same software-shared GPU on the assumption that containers provide a complete security boundary. Containers share the host kernel and GPU driver; evaluate the threat model of the entire platform.

## 6. Choosing a Model by Workload Type

### 6.1. Large Model Training

Training can consume nearly all GPU compute, VRAM, and bandwidth. Some workloads also require multiple GPUs and high-speed interconnects. Exclusive GPUs usually offer the most predictable performance.

If training can be broken into small jobs using batching or checkpointing, time-shared scheduling might be considered for low-priority jobs. However, measure queue wait times, total completion time, and contention impact.

### 6.2. Model Inference

Inference takes several forms:

- **Online inference:** continuous incoming requests, usually with strict latency requirements.
- **Batch inference:** batch processing that can tolerate longer wait times.
- **Embedding or reranking:** workloads that may be small per call yet run at high frequency.
- **Multi-model serving:** many small models kept resident in VRAM.

MIG can fit well when assigning separate profiles to multiple inference services needing moderate isolation. MPS or time-slicing can fit many small processes if latency and contention stay within thresholds. For latency-sensitive online inference, benchmark p95/p99 latency with multiple tenants running concurrently.

### 6.3. Image, Video, and Simulation Processing

Image or video processing tasks can have bursty loads, suited for sharing if the pipeline supports queuing and retries. Scientific simulations or data analytics can consume heavy VRAM and memory bandwidth; benchmark to determine whether software sharing prolongs runtimes unacceptably.

### 6.4. Development and Experimentation Environments

Notebooks, staging environments, and development jobs often have intermittent activity. GPU sharing allows more users to access devices at lower cost. However, enforce per-user quotas, runtime limits, application-level memory caps, and automated cleanup after sessions end.

Do not let a forgotten notebook kernel hold onto a GPU indefinitely. Platforms should track idle sessions, enforce timeouts, apply quotas, and use preemption to return idle resources to the shared pool.

## 7. Estimating and Allocating GPU Resources

### 7.1. Measure Demands Before Picking Profiles

For each workload, gather:

- Minimum and peak VRAM.
- Compute utilization and kernel duration.
- Memory bandwidth usage.
- Batch size and concurrent request count.
- Target latency and required throughput.
- Runtime duration, load cycles, and priority level.
- Size of model weights, activations, caches, and buffers.
- GPU count and inter-GPU communication needs.

For inference, batch size and concurrency can cause VRAM to grow quickly. For training, optimizer states, gradients, activations, and checkpoints can take more memory than model weights. Do not size GPUs solely from model file size.

### 7.2. Headroom and Limits

When assigning MIG profiles or setting sharing quotas, leave headroom for peak memory and load spikes. If a workload averages 4 GB but occasionally spikes to 7 GB, a 5 GB profile is unsuitable simply because the average looks low.

With time-slicing, cap the number of workloads per GPU and enforce memory limits inside the application. With MPS, consider configuring active thread percentages per client if supported by the platform, keeping in mind that compute percentage limits are not VRAM limits.

With MIG, pick profiles based on both compute and memory. A profile with enough VRAM but too little compute may miss throughput targets. Conversely, a profile with enough compute but insufficient VRAM may fail to load the model or batch.

### 7.3. Avoiding Resource Fragmentation

MIG uses discrete profiles. A GPU may have total spare capacity yet lack an instance combination matching a new request. For example, smaller partitions may be consumed in a pattern that blocks a workload needing a larger profile, even though spare resources sit in non-combinable slices.

This is **resource fragmentation**. Monitor demand by profile, utilization rates, and queue wait times. Mitigate fragmentation by standardizing a small set of profiles, grouping similar workloads, rescheduling during off-peak hours, or reserving dedicated GPUs for large workloads.

## 8. Monitoring and Troubleshooting

### 8.1. Metrics to Monitor

| Metric Group | Examples | Meaning |
|---|---|---|
| Compute | GPU utilization, SM activity, kernel duration | Determines whether the GPU is actively busy |
| Memory | VRAM used/free, allocation failures | Detects memory exhaustion or abnormal allocation growth |
| Memory bandwidth | Memory read/write throughput | Detects internal data transfer bottlenecks |
| Latency | Queue wait, inference latency p50/p95/p99 | Measures contention impact on end users |
| Throughput | Requests/s, samples/s, jobs/hour | Measures actual processing capacity |
| Reliability | GPU resets, Xid/errors, Pod restarts | Detects hardware or driver faults |
| Scheduling | Pending Pods, allocation failures, profile usage | Detects resource exhaustion or fragmentation |
| Cost | GPU cost per request/job/model | Evaluates resource efficiency |

Use vendor tools such as NVIDIA System Management Interface (nvidia-smi), NVIDIA Data Center GPU Manager (DCGM), Prometheus exporters, or cloud platform dashboards. For non-NVIDIA GPUs, use the corresponding manufacturer monitoring tools.

### 8.2. Diagnosing Common Scenarios

**Low GPU utilization but slow workload:** CPU preprocessing, I/O, networking, small batches, or data synchronization may be the bottleneck. Do not rush to add GPUs.

**Full VRAM despite low compute:** the model or cache is holding memory; batch size, process count, or model replicas may be too high. Check allocations and memory leaks.

**Multiple workloads slow down simultaneously:** contention for GPU compute, bandwidth, copy engines, or host CPU. Break down metrics per workload and test reducing co-located tenants.

**Pod stuck Pending:** inspect GPU resources advertised by nodes, MIG profiles, namespace quotas, node selectors, taints, and extended resource names.

**Container reports exec or driver errors:** check driver version, CUDA runtime, container toolkit, image architecture, and component compatibility.

**GPU resets or device disappears:** inspect kernel logs, driver logs, hardware errors, power delivery, and temperatures. Cordon/isolate the node if device errors affect multiple workloads; recover per platform runbook.

### 8.3. Controlled Contention Testing

Before co-locating multiple tenants on one GPU, test load combinations:

1. One workload running alone to establish a baseline.
2. Two workloads of the same type running concurrently.
3. Two mixed workloads, e.g., inference alongside batch processing.
4. Peak load with VRAM near capacity.
5. One workload terminating abnormally or being killed.
6. Varying concurrent workload counts while measuring latency and throughput.

Compare results against SLOs. If one tenant can push another over latency thresholds or cause OOM errors, reduce sharing density, switch to MIG, or allocate exclusive GPUs.

## 9. Cost Optimization and Usage Efficiency

GPUs generally cost more than other compute resources. Optimization is not merely raising utilization; it means lowering cost per unit of work while meeting quality requirements.

Measures include:

- **Consolidate small workloads:** co-locate compatible workloads via time-slicing or MPS when contention is acceptable.
- **Use MIG for multi-tenancy:** allocate right-sized profiles rather than giving each workload a whole GPU.
- **Tier workloads:** give latency-sensitive workloads dedicated GPUs or MIG; let batch jobs use remaining capacity under policy controls.
- **Batching:** group requests to improve compute efficiency while bounding latency and VRAM.
- **Autoscaling:** scale GPU counts or nodes based on queue depth, throughput, and latency.
- **Scale-to-zero or shut down idle nodes:** suited for dev environments and batch jobs when startup times are acceptable.
- **Enforce timeouts and quotas:** terminate inactive workloads, abandoned notebooks, or overdue jobs.
- **Track cost per tenant:** attribute costs by request, model, team, or project.

Do not aim for 100% utilization at all times. When GPUs stay saturated at the ceiling, new workloads lack headroom, latency spikes easily, and the system struggles to absorb bursts. Maintain headroom aligned with load patterns and SLOs.

## 10. Design Examples

### Example A: Multiple Small Inference Services on One GPU

A team has four small models, each receiving intermittent requests. None of them needs an entire GPU's compute, yet all must keep their weights resident in VRAM.

The team measures peak VRAM, latency, and compute usage. If the GPU supports MIG and each model fits a dedicated profile, GPU instances can separate resources cleanly. If models can share via software and latency sensitivity is low, the team can test MPS or time-slicing.

After testing, the team selects the method based on p95/p99 latency, memory allocation failure rates, throughput, and cost. Keep a fallback path to exclusive GPUs if contention breaches SLOs.

### Example B: Kubernetes Cluster with MIG GPUs

A cluster includes MIG-capable GPU nodes. Administrators configure profiles according to demand: several small instances for inference and larger profiles for heavy processing. The device plugin advertises resources by profile. Deployments request the exact extended resource and schedule onto matching nodes.

Monitoring tracks available instances, VRAM, utilization, Pending Pods, and latency. When small profiles fill up, the autoscaler adds nodes or operators adjust allocations per plan. Maintain a runbook for changing MIG layouts since reconfiguration can disrupt running workloads.

### Example C: Shared Notebook Platform

A development platform provides GPUs to multiple users. Users open notebooks for short sessions and frequently leave devices idle between cell runs.

The platform enforces team quotas, idle session timeouts, maximum runtimes, and GPU sharing. Latency-critical production workloads are isolated from the notebook pool. Dashboards display utilization, active sessions, wait times, and cost per team so operators can balance capacity.

## 11. Common Mistakes

**Assuming time-slicing splits VRAM into isolated slices.** Time-slicing shares execution time; GPU memory remains a shared pool that a single workload can over-consume.

**Treating MPS as hardware partitioning.** MPS helps multiple CUDA processes share execution, but it does not provide isolated VRAM regions or hardware-level isolation like MIG.

**Using MIG without checking profiles.** Profiles come in discrete sizes and depend on the GPU model. A profile available on one GPU line may not exist on another.

**Looking only at average GPU utilization.** Average utilization hides p99 latency spikes, peak VRAM, queue wait times, and resource fragmentation. Measure per workload.

**Co-locating untrusted workloads on software-shared GPUs.** Containers do not create complete security boundaries across GPUs, drivers, and kernels. Evaluate the threat model and isolation guarantees.

**Over-provisioning sharing replicas.** Increasing logical replicas allows more Pods to schedule without adding physical capacity. The result can be high latency and OOM errors.

**Leaving zero headroom capacity.** When GPUs run completely full, systems cannot absorb traffic spikes or recover smoothly from node failures.

**Changing MIG layouts while workloads are running.** Re-partitioning may require stopping or reconfiguring devices. Plan maintenance windows and workload draining.

**Ignoring cost per unit of work.** High utilization is not economical if latency, failure rates, or job completion times degrade sharply.

## 12. Pre-Deployment Checklist

- [ ] Identified GPU model, VRAM, compute capability, and supported sharing features.
- [ ] Measured peak VRAM, compute, bandwidth, latency, and throughput per workload.
- [ ] Defined performance, fault, and security isolation requirements across tenants.
- [ ] Selected exclusive GPU, time-slicing, MPS, MIG, or vGPU based on requirements.
- [ ] Verified compatible driver, CUDA, runtime, hypervisor, and device plugin versions.
- [ ] Verified actual MIG profiles or extended resource names advertised on nodes.
- [ ] Configured quotas, workload concurrency caps, and priority policies.
- [ ] Configured appropriate scheduling, node affinity, taints/tolerations, and topology settings.
- [ ] Set up monitoring for VRAM, compute, bandwidth, latency, errors, and queue wait times.
- [ ] Tested contention, OOM handling, restarts, and single-workload failure scenarios.
- [ ] Maintained headroom and fallback capacity for GPU or node failures.
- [ ] Calculated cost per request, job, or tenant and tuned sharing ratios accordingly.

## 13. Key Takeaways

- **GPUs have multiple resource dimensions:** compute, VRAM, memory bandwidth, copy engines, and inter-device interconnects.
- **Exclusive GPUs** offer predictable performance but can leave capacity idle.
- **Time-slicing** alternates execution time; it does not automatically split VRAM into isolated regions.
- **MPS** lets multiple CUDA processes share GPU execution; it is software sharing, not hardware partitioning.
- **MIG** divides supported NVIDIA GPUs into GPU instances with profile-defined hardware resources.
- **vGPU** exposes virtual GPU devices to VMs; capabilities and isolation depend on the virtualization solution.
- **Kubernetes device plugins** advertise GPUs or GPU instances for scheduling; the scheduler does not natively understand all VRAM and compute constraints.
- Model selection must weigh peak VRAM, latency, throughput, isolation needs, platform support, and cost.
- Per-workload monitoring and contention testing are essential for safe GPU sharing.

## Glossary

| Term | Meaning |
|---|---|
| GPU | Graphics Processing Unit, a parallel processor for graphics and accelerated computing. |
| VRAM | Dedicated memory on a GPU storing workload data and state. |
| SM | Streaming Multiprocessor, a cluster of processing units in certain NVIDIA GPU architectures. |
| Time-slicing | Sharing GPU execution time across multiple workloads. |
| MPS | NVIDIA Multi-Process Service, a mechanism coordinating multiple CUDA processes sharing a GPU. |
| MIG | NVIDIA Multi-Instance GPU, hardware partitioning technology on supported GPUs. |
| vGPU | Virtual GPU provided to virtual machines through a virtualization layer. |
| PCI passthrough | Assigning a physical PCIe device directly to a virtual machine. |
| Device plugin | Kubernetes component that discovers and advertises device resources to kubelet. |
| Extended resource | Custom resource type that Kubernetes can schedule and allocate to Pods. |
| GPU instance | A GPU partition created according to a hardware profile, such as in MIG. |
| VRAM fragmentation | Condition where spare memory or partitions remain but cannot satisfy an incoming allocation request. |
| Headroom | Reserve capacity kept to absorb load increases or spikes. |
| Throughput | Number of requests, samples, or tasks processed per unit of time. |
| Latency | Time elapsed from sending a request to receiving the result. |
