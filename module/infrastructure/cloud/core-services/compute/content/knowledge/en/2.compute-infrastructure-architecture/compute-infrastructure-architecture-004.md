# Instance Families, Machine Types, and Custom Machine Configurations

When deploying virtual machines in the cloud, choosing "how many CPUs and how much RAM a machine has" is only the first step. Each provider packages CPU, memory, networking, local storage, and accelerators into different hardware groups. Selecting the right machine family and size helps applications achieve desired latency, throughput, and availability without paying for unused resources.

This lesson distinguishes between **instance family**, **machine type**, and **custom machine configuration**, then explains how to select configurations based on load characteristics, validate via testing, and tune in operations. The concepts apply to virtual machines across many cloud platforms; specific naming and catalogs vary between providers.

## 1. Three Concepts to Distinguish

### Instance Family: Grouping Machines by Hardware Characteristics

An instance family is a group of configurations designed to serve a specific workload profile. Machines in the same family typically share similar CPU-to-memory ratios, processor generations, network bandwidth, or storage devices.

Examples of common families:

- General purpose: balanced CPU and RAM for web apps, API services, application servers, and small databases.
- Compute optimized: prioritizes CPU processing power for data processing, encryption, simulation, compute tasks, and CPU-intensive services.
- Memory optimized: provides high RAM relative to vCPU count for caches, in-memory databases, data analytics, and apps holding large working sets.
- Storage optimized: focuses on IOPS, throughput, or local storage capacity, suitable for databases and data processing systems requiring fast disk access.
- Accelerated computing: adds GPUs or specialized accelerators for graphics, AI training and inference, parallel processing, or scientific computing.
- Burstable: provides a baseline CPU level with the ability to burst for certain periods, suited for low average loads with occasional spikes.
- Network optimized: prioritizes bandwidth, packets-per-second, or network latency for distributed systems, HPC, and high-volume data transfer services.

These labels describe orientation, not a universal standard. A family may simultaneously feature fast networking or local disks; always read the specifications of the exact machine series and generation.

### Machine Type or Instance Size: A Specific Configuration

A machine type is a concrete option within a family or machine catalog. It defines the exact set of resources and limits allocated to a VM, typically including:

- vCPU count and CPU architecture.
- RAM capacity.
- Maximum network bandwidth or network performance tier by machine size.
- Disk attachment capability, disk count, supported IOPS, and throughput.
- Capacity and characteristics of local disks, if present.
- GPU or accelerator support.
- Platform, deployment region, or hardware generation limits.

Naming varies by provider: AWS commonly uses *instance type*, Azure uses *VM size*, and Google Cloud uses *machine type*. Do not compare two SKU names solely by vCPU count; compare CPU platform, RAM, networking, storage, and attached limits as well.

### Custom Machine Configuration: Selecting Resource Ratios Within Supported Limits

Some platforms allow selecting custom vCPU counts and RAM sizes instead of relying only on predefined sizes. For instance, a service might need 4 vCPUs and 24 GiB of RAM. If predefined sizes only offer 4 vCPU/16 GiB and 8 vCPU/32 GiB, a custom configuration can avoid over-provisioning CPU or under-provisioning RAM, provided the family and deployment region support that combination.

Custom configurations remain constrained by the platform. Providers may specify:

- Which families or machine generations support customization.
- Minimum and maximum ranges for vCPUs and RAM.
- Valid RAM-to-vCPU ratios or RAM increment steps.
- Accompanying CPU architectures, network devices, and storage devices.
- Supported regions, availability zones, operating systems, or license types.

Thus, "custom" does not mean unrestricted freedom to pick arbitrary hardware specs. It is a way to pick a combination permitted by the platform.

| Concept | Question It Answers | Illustrative Example |
|---|---|---|
| Instance family | What workload profile is the machine optimized for? | General purpose, compute optimized, memory optimized |
| Machine type / size | How many resources and what limits does a specific machine have? | An SKU with 4 vCPUs, 16 GiB RAM |
| Custom machine configuration | Can we choose a better-fitting CPU/RAM ratio? | 4 vCPUs, 24 GiB RAM if supported by the platform |

## 2. Choosing a Family by Workload Characteristics

Start by identifying which resource limits the application. One app may need lots of CPU with little RAM; another may do minimal compute yet hold tens of gigabytes of data in memory. Equal vCPU counts do not mean two machines offer equivalent performance.

| Family | Typical Traits | Suitable Workloads | What to Verify |
|---|---|---|---|
| General purpose | Balanced CPU and RAM | Web/API, app servers, dev environments, small-to-medium databases | CPU/RAM ratio, network performance at chosen size |
| Compute optimized | High CPU capacity per GiB of RAM | Data processing, encryption, image/video processing, simulation | CPU generation, single/multi-thread performance, CPU limits |
| Memory optimized | Large RAM relative to vCPUs | Caches, in-memory databases, analytics, large JVM heaps | Actual usable RAM, memory bandwidth, network connection limits |
| Storage optimized | Local storage or high throughput/IOPS | Databases, scratch data stores, log and big data processing | Disk type, data durability, IOPS, throughput, and latency |
| Accelerated | GPUs or accelerators | AI/ML, graphics, parallel compute | GPU type, VRAM, drivers, frameworks, GPU sharing, and cost |
| Burstable | Baseline CPU with CPU credit/accumulation mechanism | Small services, test environments, low intermittent loads | Baseline CPU, credit mechanics, sustained CPU behavior |
| Network optimized | High bandwidth or packet-processing rate | Distributed systems, HPC, data transfer services | Bidirectional bandwidth, PPS, latency, size-dependent limits |

### Examples by Application Type

**Standard request-handling API service.** If the app uses CPU and RAM in a relatively balanced way, a general-purpose family is a sensible starting point. When profiling shows CPU is consistently the bottleneck while RAM has plenty of headroom, try compute optimized. If heap, cache, or working set grows and creates memory pressure, consider memory optimized.

**In-memory database.** RAM capacity and memory bandwidth may matter more than adding vCPUs. Account for memory used by the OS, caches, connections, background processes, and headroom. Do not treat total nominal RAM as usable application data capacity.

**Large file processing job.** If most time is spent reading/writing data, adding vCPUs may not yield significant improvement. Measure storage latency and throughput, and check networking if data resides on network disks or external storage services.

**AI workloads.** Only choose GPU machines after confirming the framework and model actually utilize the GPU. Check VRAM, driver compatibility, data transfer bandwidth, and GPU wait time on CPU. A powerful GPU sitting idle waiting for data may not deliver commensurate value.

## 3. Reading Machine Specifications Before Sizing

### vCPU Does Not Always Equal One Physical CPU Core

A vCPU is the unit of CPU capacity a platform allocates to a VM. Depending on architecture and provider implementation, one vCPU may correspond to a hardware thread or a scheduled share of processing capacity. Hence, performance cannot be inferred solely by comparing vCPU counts across two families or two providers.

When workloads are CPU-sensitive, also check:

- CPU generation and family, clock speed, and boost behavior.
- Single-thread performance if the application has sequential sections.
- Multi-thread performance if tasks can run in parallel.
- x86-64 vs. Arm architecture and compatibility of images, libraries, and binaries.
- Throttling behavior, CPU wait time, and CPU steal if exposed by the OS.

An application may run well on fewer newer-generation vCPUs, or require more vCPUs when using CPUs with different characteristics. Benchmarking on the actual workload type is a more reliable verification method.

### RAM: Size for Working Set and Growth

RAM must accommodate the working set during peak hours, not just average usage. The working set is the data and processes that need to stay in memory for stable operation. When RAM runs short, the OS may reclaim caches, swap, or kill processes via OOM. These behaviors often cause sharp latency spikes or service outages.

When estimating RAM, include:

1. OS and monitoring/security agent memory.
2. Runtime heap or memory allocation.
3. Caches, buffers, and hot data.
4. Memory for concurrent connections and requests.
5. Background tasks, batch jobs, and projected growth.
6. Headroom for traffic spikes and restarts.

Do not apply a fixed headroom percentage to every system. A service with bounded caches behaves differently from a JVM, database, or data-processing app with a fluctuating working set.

### Network: Bandwidth, PPS, and Size-Based Limits

Network specs may be published as peak, baseline, or variable performance scaling with machine size and load conditions. Check:

- Inbound and outbound bandwidth, and how aggregate bandwidth is calculated.
- Packets per second (PPS) and capacity for handling many small connections.
- Latency, jitter, and retransmission rates.
- Virtual NIC limits, accelerated networking modes, and queue counts.
- Inter-region, cross-AZ, or internet egress traffic that may incur separate charges.

If an app handles many small connections, PPS and latency may matter more than peak bandwidth. When transferring large files, throughput and link caps usually matter more.

### Storage: Distinguish Local Disks from Persistent Volumes

Some machines include local SSD/NVMe drives with low latency and high throughput. However, local disks may be ephemeral storage tied to the machine lifecycle; data can be lost when the machine stops, is replaced, or moves to another host depending on the platform.

Network disks or block storage services typically provide persistence decoupled from machine lifecycle, though performance depends on volume type, provisioned IOPS/throughput, queues, and networking. Clearly distinguish:

- Storage capacity.
- IOPS (input/output operations per second).
- Throughput (data read/written per second).
- Latency and latency stability.
- Aggregate limits across the VM, volume, and network link.

Never store a system's sole copy of data on ephemeral disks without appropriate replication or recovery mechanisms.

### GPUs and Accelerators

When workloads require GPUs, select based on compute precision/operation types and device memory needs. GPU count alone is insufficient to describe capacity: two GPUs can differ in architecture, VRAM, memory bandwidth, and software support.

Verify compatibility across GPU, driver, runtime, framework, and deployment image. Measure GPU utilization, GPU memory, and data-loading wait time. For inference workloads, measure throughput and latency across batch sizes and concurrency levels.

## 4. When Should You Use a Custom Machine Configuration?

Custom configurations are useful when workloads have unusual CPU/RAM ratios or when predefined sizes create clear waste.

Suppose a peak-load measurement shows a service needs roughly 2.8 vCPUs and a 17 GiB RAM working set. The operations team wants headroom for near-term growth. Two predefined options might be:

- 4 vCPUs, 16 GiB RAM: CPU may suffice, but RAM is too close to the working set, risking memory pressure.
- 8 vCPUs, 32 GiB RAM: ample RAM, but allocates extra CPU the app may never use.

If supported by the platform, 4 vCPUs and 24 GiB RAM can fit better. This is only a candidate configuration: verify family limits, CPU performance, networking, cost, and benchmark results before production rollout.

Consider custom configurations when:

- The app needs large RAM without utilizing additional CPU.
- The load needs relatively high CPU with a small working set.
- A custom size cuts waste while still meeting SLOs.
- Measurement data is solid enough to define CPU/RAM requirements.
- The family and deployment region support the desired combination.

Do not customize merely to get a "neat" number. If demand swings widely over time, autoscaling or adjusting instance counts can be more effective than provisioning one oversized machine.

Before finalizing, verify vCPU limits, valid RAM ratios, availability zones, quotas, OS/software licensing, capacity reservations, and compatibility with features like live migration or resizing. Custom configuration pricing may also follow separate billing rules; verify actual quotes.

## 5. Process for Selecting a Family and Machine Type

### Step 1: Characterize the Workload with Metrics

Collect metrics under normal and peak traffic. Record request throughput, concurrent connections, p50/p95/p99 latency, CPU, RAM, I/O, and network. Separate baseline traffic from batch runs or scheduled jobs.

If no production environment exists yet, generate representative synthetic load matching expected data and user behavior. A test running only a few simple requests rarely reflects real load.

### Step 2: Define Constraints and SLOs

Clarify targets for latency, throughput, error rates, and recovery times. Identify CPU architecture, OS, GPU requirements, data residency, deployment regions, and security requirements. These constraints can rule out certain families upfront.

### Step 3: Pick Family First, Size Second

Choose the family based on the resource constraining the workload. Then pick one or a few machine types with adequate CPU, RAM, networking, and storage. Do not scale every resource simultaneously without knowing where the bottleneck is.

### Step 4: Benchmark Candidate Configurations

Run the same test suite across candidates. Keep application version, dataset, client count, and network conditions constant. Compare:

- Achieved throughput at the same error rate.
- p95/p99 latency at peak load.
- CPU and RAM consumption, including peaks.
- Storage IOPS, throughput, and latency.
- Bandwidth, PPS, retransmissions, and packet drops.
- Cost per unit of completed work.

A configuration is suitable only when it meets SLOs under representative load with necessary headroom.

### Step 5: Check Deployability and Availability

Verify the machine type is available in the target region with sufficient quota and capacity. If high availability is required, deploy multiple machines across independent availability zones, using health checks and automated instance replacement. Confirm autoscaling can provision the chosen machine type during spikes.

A configuration that looks ideal on paper still fails to deploy if the provider runs out of capacity in the selected zone or quota is insufficient.

### Step 6: Calculate Total Cost

Compare costs for the same volume of work, not just hourly per-machine rates. Total cost may include:

- Machine runtime and on-demand, committed, or spot/preemptible pricing models.
- Disks, snapshots, provisioned IOPS, and throughput add-ons.
- Cross-region or internet egress network traffic.
- GPUs, OS licenses, and commercial software licenses.
- Spare capacity for high availability.
- Operational overhead from managing many machines or incident response.

A larger machine can be cheaper per unit of work if it finishes tasks faster and reduces instance count. Conversely, an oversized machine wastes money sitting mostly idle. Measure cost per request, per record, per job, or per useful compute hour.

### Step 7: Monitor and Tune

After deployment, track the same metrics used in benchmarking. As load grows, decide whether to scale up (larger machine), scale out (more machines), or optimize the application. Set alert thresholds based on SLOs and workload traits, not CPU utilization alone.

The selection flow can be summarized as follows:

~~~mermaid
flowchart TD
    A["Measure workload and SLOs"] --> B["Identify bottleneck: CPU, RAM, network, I/O, GPU"]
    B --> C["Choose suitable instance family"]
    C --> D["Select machine type or custom configuration"]
    D --> E["Benchmark under representative load"]
    E --> F{"Meets SLOs and cost targets?"}
    F -- "No" --> G["Adjust family, size, or application"]
    G --> E
    F -- "Yes" --> H["Verify quota, region, and redundancy"]
    H --> I["Deploy, monitor, and rightsize periodically"]
~~~

## 6. Example: Choosing a Machine for an API Service

An operations team runs an API service with the following peak-hour metrics:

- CPU usage around 2.8 vCPUs at peak load.
- RAM working set around 17 GiB.
- Moderate network traffic, no GPU requirement.
- Primary data stored on an external persistent storage service.
- Service must keep p95 latency within SLO under rising load.

The team starts with a general-purpose family since the load shows no specialized CPU, memory, network, or GPU skew. They compare 4 vCPU/16 GiB and 8 vCPU/32 GiB sizes, and evaluate a 4 vCPU/24 GiB custom configuration if supported by the platform.

The 4 vCPU/16 GiB size risks lacking RAM headroom. The 8 vCPU/32 GiB size can handle it, though they must verify whether the extra CPU yields enough gain to justify the cost. The 4 vCPU/24 GiB configuration is a better-balanced capacity candidate, but is only selected after benchmarks confirm latency, throughput, networking, and cost.

The team continues testing above projected load, verifies behavior when an instance is replaced, and confirms autoscaling can add instances in the target region. If CPU becomes the bottleneck as concurrency climbs, they test a compute-optimized family. If RAM grows rapidly from caching or working set expansion, they evaluate memory optimized or tune cache policies before upsizing machines.

This example shows that choosing a machine type is an engineering hypothesis to be validated. Measured metrics determine the final configuration.

## 7. Relationship to Containers and Serverless

With containers, instance families and machine types are usually chosen for cluster nodes. The scheduler then places containers onto nodes based on CPU requests, memory requests, limits, and available capacity. Choosing nodes that are too small causes scheduling failures or memory pressure; choosing nodes that are too large lowers utilization efficiency. Evaluate node size, pod density, overcommit levels, and node pool scaling together.

With serverless, users typically do not choose instance families or machine types directly. The platform manages underlying hardware; users configure parameters such as memory, CPU if supported, execution timeout, concurrency, and scaling limits. Even without picking machine SKUs, the principles of measuring workloads, defining SLOs, and optimizing cost per unit of work still apply.

When migrating a service from VMs to containers or serverless, do not copy the old machine's CPU/RAM numbers verbatim. Re-measure actual consumption and understand how the new platform allocates resources.

## 8. Post-Deployment Performance Monitoring

The table below maps symptoms to metric groups to inspect. A single metric is rarely enough to conclude you need to switch families.

| Symptom | Metrics to Inspect | Investigation Direction |
|---|---|---|
| Latency rises with concurrent requests | CPU utilization, run queue, CPU throttling, p95/p99 | Identify CPU starvation, sequential bottlenecks, or concurrency limits |
| Processes get OOM-killed or restart | RSS, working set, page faults, swap, OOM events | Inspect heap, caches, leaks, and RAM sizing |
| Slow reads/writes | IOPS, throughput, latency, queue depth | Separate volume, VM, and network path limits |
| Slow data transfers | Throughput, PPS, retransmissions, packet drops | Check network limits, packet sizes, and data locality |
| Low GPU utilization | GPU utilization, VRAM, CPU/I/O wait times | Inspect data pipeline, batch size, drivers, and GPU saturation |
| High cost with frequently idle machines | Usage over time, completed requests/jobs, cost per unit of work | Right-size, autoscale, or consider a different billing model |

On Linux, several commands can assist quick checks inside a VM:

~~~sh
lscpu
free -h
vmstat 1
iostat -xz 1
ip -s link
~~~

**iostat** is commonly provided by the sysstat package; exact metrics and tools may vary across distributions. Guest-side results should also be cross-checked against cloud platform metrics, since a VM cannot always observe all infrastructure-layer limits.

Track trends by hour, day, and business cycle. A machine with low CPU most of the time may still need headroom for brief yet critical spikes. Conversely, if CPU, RAM, and I/O remain low over extended periods, evaluate downsizing or scaling with load.

## 9. Common Selection Mistakes

1. **Choosing machines solely by vCPU count.** Two machines with identical vCPUs can differ in CPU platform, RAM, network, and storage performance.
2. **Treating vCPUs as physical cores.** vCPU mapping depends on platform and architecture; benchmark real applications.
3. **Using burstable instances for sustained high CPU loads.** Once exceeding baseline or exhausting credits, performance can drop per provider policy.
4. **Ignoring peak-hour RAM.** Low average RAM does not guarantee sufficient memory during batch jobs, cache growth, or concurrent connection spikes.
5. **Looking only at maximum network bandwidth.** PPS, latency, packet drops, and machine-size caps may be the actual bottleneck.
6. **Confusing local disks with persistent storage.** Understand whether data survives machine stop or replacement.
7. **Picking GPUs before checking software.** Incompatible drivers or frameworks can leave the GPU unused.
8. **Over-sizing machines for every possible edge case.** Headroom should be grounded in metrics and scaling strategy, as idle resources still cost money.
9. **Overlooking quotas and regional capacity.** An SKU may be unavailable in the target region or lack sufficient quota.
10. **Failing to re-measure after application changes.** A new release, data shift, or higher concurrency can significantly alter the resource profile.

## 10. Pre-Finalization Checklist

- [ ] Measured CPU, RAM, network, and I/O under representative load, including peak hours.
- [ ] Identified which resource constrains the SLO.
- [ ] Selected the family based on workload traits.
- [ ] Verified vCPUs, CPU architecture, hardware generation, and compatibility.
- [ ] Accounted for RAM across application, OS, caches, and headroom.
- [ ] Verified required bandwidth, PPS, IOPS, throughput, and latency.
- [ ] Confirmed whether local disks are ephemeral.
- [ ] Checked GPU/driver/framework compatibility if accelerators are needed.
- [ ] Confirmed the SKU or custom config is available in the deployment region with adequate quota.
- [ ] Benchmarked and compared cost per unit of work.
- [ ] Planned autoscaling, failed-instance replacement, monitoring, and rightsizing.

## Conclusion

Instance families help pick the right hardware orientation; machine types define concrete resource configurations; custom machine configurations adjust CPU/RAM ratios within platform bounds. A reliable process is to measure workloads, define SLOs, select a family, test several sizes, verify deployability, and monitor post-release. When choices are grounded in real CPU, memory, network, storage, and cost metrics, systems have a strong chance of achieving steady performance at an appropriate investment.
