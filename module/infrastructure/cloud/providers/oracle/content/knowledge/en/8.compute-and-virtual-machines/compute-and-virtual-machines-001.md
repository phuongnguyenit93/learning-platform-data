# Choosing VMs, Bare Metal, and Compute Shape Families

## Lesson Objectives

In Oracle Cloud Infrastructure (OCI), choosing a Compute instance means selecting an application runtime environment with specific resource limits and operational characteristics. Two instances with the same CPU and RAM counts can still differ in processor architecture, network performance, storage type, and configuration flexibility.

This lesson is part of the **Compute and Virtual Machines** chapter of the **CLOUD_PROVIDERS_ORACLE** module. After this lesson, you will be able to:

- Distinguish between a virtual machine (VM) and bare metal to choose the right environment for a workload.
- Read shape names and distinguish a shape family from an instance's CPU/RAM configuration.
- Verify CPU, operating system, image, and software compatibility before deployment.
- Propose an initial configuration, measure with a representative workload, and adjust based on results.
- Place Compute choices in the context of OCI compartments, IAM, VCN, monitoring, cost, and availability.

Shape names used in this lesson illustrate how to read them. Actual shapes, limits, pricing, and availability must be verified in the target deployment region, availability domain, and tenancy.

## 1. Instance and Shape Answer Two Different Questions

An **Instance** is a Compute resource created to run an operating system and applications. A **Shape** describes the hardware profile or set of resource limits that an instance can use.

When designing an instance, you need to answer at least the following questions:

| Component | Question to Answer | Primary Impact |
| --- | --- | --- |
| Instance type | VM or bare metal? | Physical host sharing, provisioning scale, operational model |
| Shape family | Standard, DenseIO, GPU, or another specialized family? | CPU characteristics, local storage, acceleration, and networking |
| Shape configuration | What are the CPU, RAM, and related limits? | Processing capacity and allocated resource levels |
| CPU architecture | x86-64 or Arm? | Ability to run images, binaries, libraries, and containers |
| Image | Which operating system and version? | Boot capability, software support, and maintenance |
| Location and network | Which region, availability domain, and subnet? | Latency, availability, access path, and provisioning capacity |
| Storage | Boot volume, block volume, or local NVMe? | Capacity, data durability, IOPS, and latency |

Choosing a shape does not solve the entire design on its own. For example, a powerful VM still cannot reach a database if routes, security rules, or related permissions are incorrect. Similarly, adding more CPUs will not compensate for a block volume that is throttling throughput.

## 2. VMs and Bare Metal

### 2.1. Virtual Machine: Flexibility at Individual VM Scale

A VM runs in a virtualized environment on a provider's physical host. You administer the guest operating system, install software, and deploy applications; OCI manages the physical infrastructure and the service's virtualization layer.

VMs fit many common workloads: backend APIs, Java applications, asynchronous workers, development environments, and services that can be split across multiple smaller instances.

Common benefits:

- Start with a modest amount of resources instead of provisioning an entire physical server.
- Broad configuration choices, with some shapes allowing CPU and RAM adjustments.
- Easy to build groups of identically configured instances to distribute load.
- Can reduce the blast radius of application failures by splitting across multiple instances.

Virtualization does not mean performance is always unstable. Nor should you assume every workload requires bare metal for good speed. Measure the application on candidate shapes and look at CPU, memory, networking, storage, latency, and dependent service limits.

### 2.2. Bare Metal: Provisioning a Dedicated Physical Server

Bare metal provisions a dedicated physical server for your instance, without a Compute service hypervisor layer sitting between the instance OS and the hardware as with a VM. You still use OCI mechanisms for IAM, networking, and resource management; this is not self-managing a data center.

Bare metal is worth considering when a workload has clear requirements such as:

- Needing hardware characteristics or an execution environment that candidate VM shapes do not provide.
- Needing the resource scale of an entire server and being able to utilize that scale effectively.
- Running specialized compute or I/O tasks that have been measured and verified to suit a specific bare metal shape.
- Having software requirements or licensing terms that need to be evaluated against a physical server configuration.

Constraints to account for:

- The provisioning unit is usually larger, so a small application can leave substantial resources unused.
- You cannot assume CPU/RAM can be adjusted in small increments like a flexible VM shape.
- If a single host runs multiple workloads, an incident or maintenance on that host has a large blast radius.
- Shape availability at the target deployment location must still be verified.

**Bare metal does not automatically provide high availability.** An application on a single bare metal instance still depends on a single host. Designing multiple replicas, fault distribution, and data recovery must still be handled separately.

### 2.3. Comparison for Decision Making

| Criterion | VM | Bare Metal |
| --- | --- | --- |
| Provisioning unit | Virtual machine configured per shape | Dedicated physical server per shape |
| Small or variable workloads | Often convenient to start and adjust | Risk of large over-provisioning |
| CPU/RAM options | Fixed shapes and flexible shapes available | Depends on the shape's hardware configuration |
| Specialized hardware needs | Must verify capabilities of each VM shape | Can fit if the shape provides the exact hardware |
| Performance validation | Benchmark the application on candidate shapes | Benchmark the application on candidate shapes |
| Availability | Requires multiple replicas and recovery design | Requires multiple replicas and recovery design |
| OS responsibility | User-managed | User-managed |

If the requirement is simply "run a horizontally scalable Java API", a VM is a reasonable first candidate to evaluate. Moving to bare metal should be backed by requirements or metrics, not just the name.

## 3. Reading Shape Names and Understanding Compute Families

### 3.1. Shape Names Are Pointers to Look Up Specifications

Two examples of naming structure are `VM.Standard.E4.Flex` and `BM.Standard.E4.128`.

- `VM` or `BM` indicates the instance type.
- `Standard` suggests a family serving general-purpose compute needs.
- A segment like `E4` identifies the platform line or generation; check the exact shape specification for the processor and supported capabilities.
- `Flex` indicates the shape has a flexible configuration within supported limits.
- A numeric suffix carries meaning according to that shape's convention; no single decoding rule applies across all families.

Do not write automation logic that relies solely on parsing shape names to infer all CPU, RAM, and bandwidth figures. The authoritative source is the shape specification provided by OCI in the target environment.

### 3.2. Shape Families and Workload Patterns

| Shape Family or Group | Characteristics to Review | Potentially Suitable Workloads | Points to Verify |
| --- | --- | --- | --- |
| Standard | Balanced resources for general-purpose compute | Backends, workers, enterprise applications | CPU, RAM-to-CPU ratio, networking, and scaling options |
| DenseIO | Includes local NVMe storage on supported shapes | Data processing with heavy local I/O, scratch space, cache | Data lifecycle, capacity, and recovery mechanisms |
| GPU | Includes GPU accelerators | Model training or inference, graphics processing | GPU type, VRAM, drivers, frameworks, and supply |
| Optimized or HPC | Emphasizes compute, latency, or interconnect characteristics depending on shape | Simulation, scientific computing, performance-sensitive workloads | Per-thread performance, cluster networking, and deployment requirements |

This table groups needs rather than serving as a complete shape catalog. Not every family offers both VM and bare metal, and not every shape in a group has the same networking or storage capabilities.

Family names only help build a shortlist of candidates. For example, a read-heavy application does not automatically need DenseIO: if the data lives on a remote service and latency is mainly in queries, local NVMe may not improve that bottleneck.

### 3.3. Fixed Shapes and Flexible Shapes

A **Fixed shape** provides a predetermined configuration. A **Flexible shape** lets you choose CPU and RAM within supported ranges and ratios.

For example, two workloads may need different configurations:

- Compute worker: high CPU usage with moderate RAM needs.
- Cache-backed service: requires more RAM per unit of CPU.

Flexible shapes help tailor to these needs, though CPU and RAM cannot be chosen arbitrarily. You must verify minimums, maximums, RAM-to-CPU ratios, and associated resource limits. Network capacity or I/O limits may depend on the allocated configuration.

The ability to change the shape of an existing instance also depends on the instance type, source/target shapes, image, and related settings. Plan for downtime or instance replacement; do not assume configuration changes can always happen live while the application is running.

## 4. CPU: Count Alone Is Not Enough to Conclude Performance

### 4.1. Distinguishing OCPU, vCPU, and Application Processing Capacity

OCI uses OCPUs in many Compute configurations. The relationship between an OCPU, physical cores, and vCPUs depends on the architecture and the shape definition. On many x86 shapes with SMT, one OCPU corresponds to one physical core with two execution threads; on Arm shapes such as Ampere A1, the execution thread relationship differs from that model. Always read the shape specification before converting units or comparing quotes.

For example, the statement "both have 4 CPUs" is not enough to conclude equivalence, because you might be comparing:

- 4 vCPUs against 4 OCPUs.
- Processors of different generations with different per-thread performance.
- A multi-threaded workload against a mostly single-threaded workload.
- Strong CPUs paired with lower network or storage limits than needed.

When comparing, state the resource unit explicitly and measure work completed: requests/second at a target latency, batch completion time, or successful tasks per hour.

### 4.2. x86-64 and Arm Architectures

Java applications are portable at the bytecode level, but the entire deployment package is not necessarily CPU-architecture independent.

Before choosing Arm over x86-64 or vice versa, verify:

- Whether the OS image supports the shape's architecture.
- Whether the JDK distribution is built for the right architecture.
- Whether JNI, native libraries, monitoring agents, or helper binaries contain architecture-specific binaries.
- Whether container images have manifests and layers matching `linux/amd64` or `linux/arm64`.
- Whether backup, security tools, and commercial software support that deployment combination.

Containers do not automatically erase architecture differences. An image containing only `amd64` binaries will not natively run directly on an Arm host.

For instance, a pure Java API may be easier to migrate than a document-processing service that invokes native libraries. Both still require functional testing and performance measurement on the target architecture.

## 5. Memory, Storage, and Networking Can Determine the Shape

### 5.1. RAM Must Account for the Entire Process

For a JVM application, do not set the heap to the instance's entire RAM. Beyond the Java heap, there are metaspace, thread stacks, direct buffers, native memory, OS page cache, and operational agents.

An initial budgeting approach:

```text
Required RAM
  = workload heap
  + off-heap and native memory
  + OS and agents
  + headroom for spikes
```

This is an estimation model, not a fixed-ratio formula. Observe actual usage, GC, swap, and out-of-memory events under a representative workload. Low average CPU does not mean RAM can be safely reduced.

### 5.2. Boot Volume, Block Volume, and Local NVMe

| Storage Type | Typical Role | What to Remember When Choosing Compute |
| --- | --- | --- |
| Boot volume | Operating system and boot contents | Capacity, performance, and volume retain/delete policy must be configured separately |
| Block volume | Data or filesystems attached to the instance | Performance also depends on volume settings, attachment path, and instance-side limits |
| Local NVMe | Scratch space, cache, or data with suitable replication/recovery | Tied to the host and instance lifecycle; not durable by default like a block volume |

Having local NVMe does not mean data is automatically backed up. Before using it for important data, understand which operations can cause data loss and how to recover when an instance or host fails.

A batch-processing design might place intermediate files on NVMe and store final results in durable storage. Conversely, putting the sole copy of data on a local drive and relying only on bare metal power is a recovery flaw.

### 5.3. Bandwidth and Data Path

A backend with spare CPU yet slow requests may be waiting on the network or a dependent service. When choosing a shape, inspect:

- Network bandwidth limits of the selected shape and configuration.
- Paths to databases, object storage, or external systems.
- Latency, concurrent connections, and payload size per request.
- Limits of load balancers, storage services, and related components.

Increasing CPU may help in some configurations, but it does not replace identifying the bottleneck. VCN, subnets, routes, and security rules must be designed alongside Compute so the application has the right communication path.

## 6. Process for Choosing a Shape by Workload

### Step 1: Express Requirements as Application Behavior

Instead of starting with "need a big machine", specify:

- Whether the workload serves requests, runs batches, uses GPUs, or provides a stateful service.
- Normal and peak traffic; target latency or completion time.
- Working memory, data volume, and I/O requirements.
- CPU architecture and mandatory software.
- Recovery requirements when an instance becomes unavailable.

### Step 2: Select VM or Bare Metal and Candidate Shape Families

Use requirements to eliminate incompatible options first. If the application does not require specialized hardware and can distribute load, evaluating general-purpose VMs is a practical starting point. If GPU or local NVMe is needed, check the exact shape family that provides that resource.

Do not treat "using up an entire machine" as an independent goal. The goal is meeting application requirements at appropriate cost and operational effort.

### Step 3: Verify Deployment Feasibility

Before finalizing a configuration, confirm in the target environment:

- The shape is available in the required region and availability domain.
- The image is compatible with the shape and CPU architecture.
- Tenancy service limits and compartment quotas are sufficient, where applicable.
- IAM policies allow creating Compute along with related network and volume resources.
- The platform has actual provisioning capacity at instance creation time.

Having spare quota or service limits does not guarantee capacity is always available. Your deployment plan should identify pre-validated compatible fallback shapes or locations.

### Step 4: Benchmark Under Equivalent Conditions

Use the same data, application version, appropriate configuration, and load-generation method. For a JVM, allow warm-up time before collecting results to reduce startup and JIT effects.

Record at least:

| Group | Suggested Metrics | Used to Distinguish |
| --- | --- | --- |
| Application | Throughput, error rate, p95/p99 latency | Whether the configuration meets targets |
| CPU | Utilization, run queue, busy threads | CPU shortage vs. serialized processing |
| Memory | Available RAM, GC, swap, OOM | RAM shortage, heap pressure, or native memory pressure |
| Storage | I/O latency, IOPS, throughput | Disk or attachment path bottlenecks |
| Network | Throughput, errors, dependent service wait time | Network limits or external dependencies |

Do not draw conclusions from a short run. Measure under normal load, peak load, and a duration long enough to observe GC, caches, and background application behavior.

### Step 5: Compare Cost for the Same Service Level

Compare options when they equally meet targets for latency, throughput, and availability. An instance with a lower unit price that requires more replicas can yield a different system-level outcome.

Costs to include cover Compute, volumes, backups, networking, and supporting services. If commercial software or self-managed databases are involved, licensing terms must also be evaluated separately; do not infer them solely from the CPU count in the shape name.

Promotional credits or free-tier resources, where applicable, do not replace checking limits, capacity, and application requirements. This lesson does not assume a fixed price list or free-tier catalog.

## 7. Example: Choosing a Configuration for a Java API Accessing an Oracle Database

### 7.1. Context

A team deploys a Java API on OCI. The API accesses a separately deployed Oracle database service. Illustrative targets:

- Serve 300 requests/second at peak load.
- p95 latency not exceeding 250 ms for the test request suite.
- Continue serving when one application instance fails, within the designed load limits.
- Track costs by compartment or tags defined by the organization.

These numbers are exercise assumptions, not OCI performance guarantees.

### 7.2. Building the Candidate List

The first option is multiple Standard VMs behind a load balancer. The team chooses a CPU architecture supported by the entire JDK, containers, and agents, then tests CPU/RAM configurations under representative load.

Bare metal becomes a candidate only if data shows the multi-VM model fails a specific requirement or an entire physical machine yields a better fit. DenseIO is also not chosen merely because the system has a database: the data lives in a separate database service, so local NVMe on the application host is not necessarily a needed resource.

The team needs to measure connection pools, query times, and network latency to the database. If requests mainly wait on queries, adding CPU to the application host may not solve the problem.

### 7.3. Reading Hypothetical Measurement Results

The table below only illustrates how to interpret results; the options do not represent specific commercial shapes. Metrics are measured under the same workload during steady state.

| Option | CPU | Available RAM | p95 | Additional Observations | Next Decision |
| --- | --- | --- | --- | --- | --- |
| A | Sustained high | Sufficient | 340 ms | Worker threads busy, DB wait time low | Try increasing CPU or distributing load across more instances |
| B | Moderate | Nearly exhausted | 310 ms | Frequent GC, memory pressure present | Inspect allocations, heap, and RAM requirements |
| C | Low | Sufficient | 420 ms | Most time spent in DB queries | Analyze queries, connection pool, and DB service |
| D | Headroom available | Headroom available | 220 ms | Error rate within target | Proceed to cost evaluation and fault testing |

Option D is not enough to finalize the configuration. The team must still test losing one instance, verify whether remaining instances handle the load, and check whether dependent services can handle the resulting connection count.

### 7.4. Tying the Compute Decision to OCI Operations

After selecting a configuration that meets requirements, record the deployment decisions:

- Management compartment and IAM policies for the operations team.
- Subnets, access paths, security rules, and database connectivity.
- Application configuration, image, and CPU architecture so instances can be recreated consistently.
- Metrics, logs, and alerts to detect resource exhaustion or application errors.
- Instance distribution across fault domains or availability domains where available and appropriate to requirements.
- Data management, backup, and recovery approach; do not keep critical state solely in a single application instance's memory.

When automating, parameterize the shape and related settings explicitly. Do not automatically switch CPU architecture when trying a fallback shape if the software stack has not been verified compatible.

## 8. Hands-On: Collecting Data Before Changing Shapes

This exercise does not require creating new resources. If you already have a Linux test machine you are authorized to use, you can gather information with the following read-only commands; some tools may need to be preinstalled:

```bash
# Architecture and CPUs as seen by the OS
uname -m
lscpu

# RAM, swap, and storage devices
free -h
lsblk
df -h

# Sample CPU, memory, and I/O state over a short interval
vmstat 1 10
```

These commands provide only the OS perspective. They do not fully confirm OCI service limits, quotas, pricing, capacity, billing model, or full shape specifications. Combine them with OCI instance details and application metrics for proper interpretation.

In a virtualized environment, the CPU count seen by the OS is also insufficient proof to infer the full physical host hardware. With `vmstat`, note that the first sample can represent the average since boot; subsequent samples reflect each sampling interval.

Complete the following decision sheet with your test data:

| Item | Result to Record |
| --- | --- |
| Workload and targets | Task type, traffic, latency, acceptable error rate |
| Instance type | VM or bare metal, with rationale |
| Candidate shape | Full name, architecture, CPU, RAM, and specialized resources |
| Compatibility | Image, JDK, container, native libraries, agents |
| Deployment constraints | Region, availability domain, limits/quotas, permissions, and capacity |
| Measurement results | Throughput, latency, CPU, RAM, I/O, network |
| Cost and operations | Related billable resources, monitoring, and instance recreation |
| Recovery | Behavior on losing an instance and durable data storage location |
| Decision | Keep, scale up, scale down, or change candidate; state evidence |

## 9. Common Pitfalls

| Misconception | Why It Causes Poor Choices | How to Handle |
| --- | --- | --- |
| "Bare metal is always faster and cheaper than VM" | Outcome depends on workload, shape, and whole-host utilization | Benchmark at the same service level and calculate total cost |
| "Same CPU count means equal performance" | OCPU/vCPU units, architectures, and generations may differ | Standardize units and measure the application |
| "Java runs the same everywhere" | JDK, JNI, agents, and bundled binaries can be CPU-dependent | Verify the full deployment package on the target architecture |
| "Flexible means arbitrary configuration" | CPU/RAM and associated resources have limits | Check valid ranges for the shape |
| "DenseIO replaces backup design" | Local drives carry host-lifecycle risks | Design replication, durable storage, and recovery |
| "Low CPU means we can downsize" | RAM, networking, or I/O may still be the bottleneck | Read application and system metrics together |
| "One very large machine meets availability needs" | Still dependent on a single instance | Design multiple replicas and test failure scenarios |
| "Having quota guarantees instance creation" | Quota differs from actual physical capacity | Check capacity and prepare compatible alternatives |

## 10. Self-Check

1. Is a pure-bytecode Java API guaranteed to move to Arm simply by changing the shape? Which additional components must be verified?
2. An instance has low CPU but high p95 latency and high query wait times. What additional evidence would you collect before increasing CPU?
3. When does local NVMe provide clear benefits, and how must data stored on it be protected?
4. Why does a large bare metal instance still fail to satisfy the requirement to keep serving when a host fails?
5. What details must you record to meaningfully compare two shapes that use different CPU units?
6. If the preferred shape runs out of capacity in the deployment location, what compatibility conditions must fallback options preserve?

A well-founded Compute selection must connect three parts: **workload requirements**, **shape characteristics and constraints**, and **measurement results alongside the operational plan**. The decision sheet in the hands-on section serves as the output for reviewing configurations with development, operations, and cost-management teams.
