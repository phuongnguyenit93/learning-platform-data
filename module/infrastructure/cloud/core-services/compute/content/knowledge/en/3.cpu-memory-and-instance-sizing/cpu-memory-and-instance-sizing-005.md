# NUMA, CPU Pinning, and Memory Locality

## Lesson Objectives

In multi-processor servers, application performance depends on where the CPU executes and where data resides in memory. If a thread runs on one NUMA node while repeatedly accessing RAM belonging to another node, it may have to traverse inter-processor interconnects. Latency increases and available memory bandwidth can decrease.

After this lesson, you will be able to:

- Explain NUMA, NUMA nodes, local memory, and remote memory.
- Distinguish CPU affinity, CPU pinning, and memory allocation policies.
- Inspect CPU and memory topology on Linux.
- Align CPU and memory for a process or workload within the boundaries permitted by VMs, containers, and cloud platforms.
- Evaluate when to pin execution placement and when to let the operating system schedule freely.

## 1. What Is NUMA?

NUMA (Non-Uniform Memory Access) is a memory architecture in which access time depends on a CPU's physical location relative to a RAM region. A NUMA system is divided into **NUMA nodes**. Each node contains a group of CPUs and typically a region of memory directly attached to that CPU group.

When a CPU accesses RAM on the same node, it is a local memory access. When a CPU accesses RAM on a different node, it is a remote memory access. Remote requests must traverse links connecting the nodes, such as inter-socket links or an internal processor fabric.

This contrasts with UMA (Uniform Memory Access), where processors exhibit relatively uniform memory access characteristics. NUMA allows systems to scale CPU counts and memory capacity, though software must pay attention to data placement to avoid unnecessary remote traffic.

One socket does not necessarily correspond to exactly one NUMA node. A modern socket can be partitioned into multiple nodes depending on firmware configuration or processor design. In virtualized environments, the hypervisor can also expose a virtual topology (vNUMA) to the guest. Always inspect the topology actually visible to the guest OS rather than inferring it from advertised socket counts.

### Two-Node Topology Example

Suppose a server has two NUMA nodes:

- Node 0 has logical CPUs 0–15 and 64 GiB of local RAM.
- Node 1 has logical CPUs 16–31 and 64 GiB of local RAM.

If a thread runs on a CPU belonging to node 0 and its data resides in node 0 RAM, most memory accesses can stay on the local path. If its data resides on node 1, the thread must perform remote RAM accesses. This is an illustrative example; actual CPU counts, RAM sizes, and topology depend on the server or VM configuration.

~~~mermaid
flowchart LR
    subgraph N0["NUMA node 0"]
        C0["CPU 0–15"]
        M0["Local RAM 64 GiB"]
        C0 <--> M0
    end
    subgraph N1["NUMA node 1"]
        C1["CPU 16–31"]
        M1["Local RAM 64 GiB"]
        C1 <--> M1
    end
    C0 <-->|"Remote access via interconnect"| M1
    C1 <-->|"Remote access via interconnect"| M0
    N0 <-->|"Inter-node link"| N1
~~~

This diagram illustrates conceptual relationships only. On real hardware, paths and latency also depend on memory controllers, caches, fabric, node count, and firmware settings.

## 2. Why Does Memory Locality Matter?

A CPU can execute instructions very rapidly, yet an application still stalls if data is not ready. Remote RAM accesses generally have higher latency and consume bandwidth across inter-node links. If many threads simultaneously perform remote memory accesses, they can contend for interconnect resources.

Common effects include:

- **Increased latency:** data-dependent operations may wait longer.
- **Reduced memory bandwidth:** one node may underutilize its local RAM bandwidth while the inter-node link becomes a bottleneck.
- **Unstable performance:** threads or memory pages migrating over time can cause response times to fluctuate.
- **Resource contention:** multiple workloads sharing one node can saturate CPUs, RAM controllers, or inter-node links.

NUMA does not automatically mean poor performance. When threads and data are properly distributed, the system can leverage multiple memory controllers and scale aggregate bandwidth. Problems arise when CPU placement and data placement mismatch the application's access pattern.

Workloads sensitive to memory locality commonly include in-memory databases, large-scale data analytics, HPC applications, large caches, packet processing, and low-latency services. Small applications or short-lived workloads rarely benefit much from manual NUMA tuning.

## 3. CPU Affinity and CPU Pinning

**CPU affinity** is the set of logical CPUs on which a process or thread is permitted to run. **CPU pinning** is the practice of configuring affinity to keep a process or thread bound to a chosen set of CPUs. Affinity can be set for an entire process or for individual threads.

Pinning can help:

- Reduce frequent thread migration across CPUs, improving cache reuse.
- Keep related threads within the same NUMA node.
- Make performance measurements more reproducible for certain workloads.
- Partition CPUs for workloads with strict latency or predictability requirements.

However, pinning does not automatically make an application faster. Selecting too few CPUs can force threads to wait even while other CPUs sit idle. Pinning multiple processes to the same CPU causes them to contend for execution time. Pinning to the wrong node can even increase remote memory accesses.

Distinguish three concepts:

| Concept | Meaning | What is not guaranteed |
|---|---|---|
| CPU affinity | Restricts the set of CPUs a process or thread may run on | Does not guarantee those CPUs are dedicated to the process |
| CPU pinning | Explicitly sets affinity to a specific set of CPUs | Does not automatically place data into local RAM |
| Dedicated CPU | Platform allocates CPUs to a workload under an exclusivity policy | Not supported in all environments; memory locality still needs checking |

Inside a virtual machine, the logical CPUs visible to the guest OS are typically vCPUs. Affinity inside the guest only constrains the guest OS scheduler; it does not let the application pick physical host CPUs directly. The hypervisor still decides how vCPUs map and schedule onto the host.

## 4. Memory Placement Policies

CPU affinity determines where threads can run. NUMA memory policy determines which node the OS allocates RAM pages from. These two settings must be considered together.

Common policies on Linux include:

| Policy | How it works | When to consider |
|---|---|---|
| Default / local allocation | OS prioritizes allocation based on execution location and default rules | Most general-purpose applications |
| Preferred | Prefers a specific node; falls back to others if needed per policy | Want locality preference while keeping fallback capability |
| Bind | Restricts allocation strictly to a specified node or node set | Measured workloads with sufficient capacity on target node(s) |
| Interleave | Distributes memory pages round-robin across multiple nodes | Certain large-dataset scans with relatively uniform access patterns |

One important detail is **first-touch allocation**. On many Linux configurations, a memory page is allocated on the node of the CPU that first touches (writes to/faults) that page, subject to the active memory policy. Thus, if an initialization thread runs on node 0 while worker threads later run on node 1, the data may reside on node 0 and generate heavy remote accesses.

Linux also provides automatic NUMA balancing on supported systems. This mechanism tracks access patterns and migrates tasks or memory pages to improve locality. When tuning manually, observe real behavior and understand active policies; do not disable automatic balancing based purely on assumptions.

## 5. Inspecting NUMA on Linux

Before pinning CPUs or binding memory, inspect the topology exposed by your environment. The following commands require appropriate permissions, and several require the `numactl` package.

~~~bash
# Overview of CPUs, sockets, cores, and topology
lscpu

# Mapping of logical CPUs to sockets, cores, and NUMA nodes
lscpu -e=CPU,NODE,SOCKET,CORE,ONLINE

# Node count, CPUs, and memory capacity per node
numactl --hardware

# System-wide NUMA allocation statistics
numastat

# NUMA statistics for a specific process
numastat -p <PID>

# View CPU affinity of a process
taskset -pc <PID>

# With cgroup v2: view permitted CPUs and memory nodes
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpuset.mems.effective
~~~

How to read the output:

- Cross-reference the `NODE` column in `lscpu` with the node list from `numactl --hardware` to see which CPUs belong to which node.
- Check RAM capacity per node. A node with low available RAM can become a bottleneck if a workload is bound to it.
- `numactl --hardware` typically displays relative distances between nodes. These are platform-reported relative metrics, not access times in nanoseconds.
- `numastat -p` helps inspect a process's allocation distribution. Counters such as `numa_miss`, `numa_foreign`, `local_node`, and `other_node` must be interpreted in context of the workload and tool version.
- Inside containers, visible topology and CPU/node lists may be constrained by the runtime or cgroups. Output inside a container can differ from the full host topology.

Do not draw conclusions from a single sample. Compare statistics while the application runs under representative load, alongside latency and throughput.

## 6. Aligning CPU and Memory in Practice

Suppose inspection shows CPUs 0–15 belong to node 0 and CPUs 16–31 belong to node 1. A service has a moderate thread pool whose data is mostly accessed by threads on node 0. After measuring a baseline, you can test running the service with both CPU and RAM on the same node:

~~~bash
numactl --cpunodebind=0 --membind=0 ./service
~~~

This command instructs the process to run on CPUs belonging to node 0 and allocate memory from node 0 using the `bind` policy. Make sure node 0 has enough CPU and RAM for the process. A strict `bind` policy can cause allocation failures if the specified node runs out of memory.

If you only want to restrict the CPU set, you can use `taskset`:

~~~bash
taskset -c 0-7 ./service
~~~

`taskset` only sets CPU affinity; it does not set memory policy by itself. To control both, use appropriate NUMA tools and policies.

For workloads sequentially scanning large datasets that can benefit from aggregate bandwidth, you can test interleaving across nodes:

~~~bash
numactl --interleave=all ./batch-job
~~~

Interleaving is not the right default for every application. For workloads whose data and threads are concentrated per node, spreading pages across all nodes can increase remote accesses. Benchmark using your actual dataset and load pattern.

A recommended testing workflow:

1. Measure the baseline without modifying affinity or memory policy.
2. Record topology, permitted CPUs, RAM capacity per node, and current policies.
3. Verify execution placement and memory distribution while the application is active.
4. Test one change at a time, such as restricting CPUs to one node first.
5. Re-measure throughput, p50/p95/p99 latency, CPU usage, context switches, memory pressure, and NUMA statistics.
6. Keep the new configuration when improvements are consistent under representative load; roll back if performance degrades or resources become imbalanced.

## 7. NUMA in Containers and Kubernetes

Containers share the host kernel. CPUs and memory nodes permitted to a container are typically constrained by cgroups and container runtime settings.

Docker example on a host with suitable topology:

~~~bash
docker run --rm \
  --cpuset-cpus="0-7" \
  --cpuset-mems="0" \
  my-service:latest
~~~

In this example, the container is restricted to CPUs 0–7 and memory node 0 according to the host topology. Only use these flags after inspecting the host and confirming the runtime permits that configuration. CPU quota or CPU shares settings mean something different: they throttle or weight CPU time without necessarily pinning the container to a specific CPU group.

On Kubernetes:

- CPU Manager with the `static` policy can allocate exclusive CPUs to containers in Pods meeting the Guaranteed QoS class with integer CPU requests, depending on Kubernetes configuration and version.
- Topology Manager can coordinate topology hints from CPU Manager, Device Manager, and other resource providers to improve resource alignment.
- Standard CPU requests and limits do not equate to CPU pinning.
- NUMA alignment capabilities depend on kubelet settings, container runtime, device plugins, node topology, and Kubernetes version.

For latency-sensitive workloads, inspect node configuration and actual allocation state after Pod scheduling. Do not assume declaring requests/limits guarantees CPU and RAM sit on the same NUMA node.

## 8. Constraints in Cloud Computing Environments

In cloud virtual machines, the hypervisor manages physical hosts and maps guest vCPUs and memory onto physical resources. As a result:

- A guest may see only a single NUMA node even when the host has multiple nodes.
- A guest may see vNUMA, but that topology is presented by the platform and does not necessarily reflect every detail of host data placement.
- CPU pinning inside the guest constrains only the guest OS scheduler; it does not override hypervisor pinning policies.
- Topology control capabilities typically differ across standard VMs, performance-optimized VMs, dedicated hosts, and bare-metal instances.

If an application requires strict NUMA control, choose an instance type whose documentation specifies matching topology and capabilities. On standard VMs, start from the topology visible inside the guest and benchmark the application. On bare-metal or host-managed environments, operations teams have deeper control over CPU affinity, cpusets, memory policies, and workload placement.

Do not infer physical NUMA node counts solely from vCPU count, instance name, or displayed socket count. Verify using tools in the runtime environment and provider documentation.

## 9. When Should You Use CPU Pinning and NUMA Binding?

| Workload type | Initial approach | Rationale |
|---|---|---|
| Standard web services, variable load | Let default scheduler and memory policy manage placement | Flexible as load fluctuates; tuning overhead may outweigh gains |
| Large databases, in-memory caches | Measure locality, then test aligning thread groups and memory per node | Frequent RAM access means data placement can noticeably affect latency |
| HPC, data analytics, matrix processing | Benchmark per-node partitioning and interleaving | Can leverage multiple memory channels and aggregate bandwidth |
| Packet processing or low-latency services | Consider pinning threads, IRQs, and memory per node | Reduces thread migration and improves predictability when tuned properly |
| Serverless or managed services | Optimize at application level and provided service settings | Users typically do not control underlying CPU/RAM topology |

CPU pinning and NUMA binding are appropriate once there is evidence of thread migration overhead or remote memory access penalties. For workloads showing no bottleneck, keep configurations simple and let metrics guide decisions.

## 10. Common Mistakes and How to Avoid Them

**Pinning all threads to one node:** that node can run out of CPU or RAM bandwidth while other nodes sit idle. Analyze thread count, parallelism, and memory capacity before restricting placement.

**Pinning CPU while ignoring memory:** threads may run steadily on node 0 while their data resides on node 1. Address both CPU affinity and memory policy.

**Binding to a node without enough RAM:** allocations may fail or the workload may starve for resources. Monitor per-node capacity and leave headroom for the OS and other processes.

**Confusing CPU quota with pinning:** quota caps CPU time within an interval; affinity restricts which CPUs can run the task. The two mechanisms solve different problems.

**Relying on host topology while inside a VM/container:** the guest or container may see only a subset of resources. Check actual limits of the current environment.

**Measuring only once or looking only at CPU utilization:** low CPU does not prove an application suffers from NUMA issues. Compare latency, throughput, NUMA stats, and memory pressure under identical load conditions.

**Applying interleave to every workload:** interleaving can help some sequential scan tasks while hurting locality for apps with concentrated accesses. Pick policies based on real access patterns.

## 11. Pre-Production Configuration Checklist

- [ ] Identified the CPU and NUMA node topology actually visible to the workload.
- [ ] Checked CPU and memory node limits for the VM, container, or Pod.
- [ ] Measured baseline under representative load.
- [ ] Identified evidence of remote memory access or thread migration.
- [ ] Aligned CPU affinity and memory policy consistently.
- [ ] Verified selected node(s) have sufficient CPU, RAM, and headroom.
- [ ] Tested behavior under load increases, decreases, and process restarts.
- [ ] Compared p95/p99 latency, throughput, and NUMA stats after changes.
- [ ] Prepared a rollback plan if results are unstable.

NUMA, CPU pinning, and memory binding are tools to control where execution and data reside. Effectiveness comes from understanding the exposed topology, measuring the right workload, and aligning CPUs with where data is accessed. In cloud environments, control depends on instance type and virtualization layer; optimize within the topology the operating system actually sees.
