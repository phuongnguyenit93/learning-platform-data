# Impact of Network and Disk Limits When Selecting a Machine Type

When selecting a machine type for a cloud workload, vCPU count and RAM capacity do not tell the whole story of machine capability. An application can have plenty of CPU and memory yet still run slowly because the machine cannot transfer enough data over the network, cannot generate enough disk read/write operations, or stalls in I/O queues. A well-chosen machine type must satisfy compute, memory, networking, and storage requirements together based on real load characteristics.

In **CLOUD_CORE_SERVICES_COMPUTE**, understanding network and disk limits helps you pick the right instance family, predict serving capacity, maintain availability, and control costs. These limits also influence application design: data-heavy services need appropriate bandwidth and packet rates; databases need consistent IOPS, throughput, and latency; and mixed workloads must avoid having I/O streams contend on the same instance cap.

## 1. Machine Types Provide Multiple Capabilities

A machine type is a compute configuration offered by a cloud provider. Depending on the platform, a configuration may specify vCPU count, RAM, CPU model, network bandwidth, local storage capacity, network storage limits, and acceleration features.

Common machine type families include:

- **General purpose:** balances CPU, RAM, and I/O capability; suitable for many web apps, business services, and dev environments.
- **Compute optimized:** prioritizes CPU capacity per machine; suitable for computation, batch processing, or CPU-bound apps.
- **Memory optimized:** provides high RAM for caches, in-memory databases, and workloads with large working sets.
- **Network optimized:** focuses on bandwidth, packet rate, or high network traffic handling capacity.
- **Storage optimized:** provides local storage capacity or high storage throughput/IOPS for I/O-intensive workloads.
- **Accelerated computing:** adds GPUs or specialized accelerators; still requires checking networking and storage separately to feed data to the accelerator.

Family names are only directional guidance. Different machine type generations within the same family can have different network limits, disk limits, and bursting models. Read specifications for the exact machine type, deployment region, and volume type you plan to use.

## 2. Network Limits to Understand

Network capability is not just the Gbps figure listed in a specification table. An application can be constrained by aggregate bandwidth, packets per second, connection count, single-flow throughput, or path latency.

### 2.1. Bandwidth vs. Actual Throughput

**Bandwidth** is the maximum data transfer capacity of a link or interface under specified conditions. **Throughput** is the actual amount of data transferred per unit of time.

For example, 1 Gbps equals 1 billion bits per second, or at most roughly 125 MB/s in decimal units before protocol overhead. Application throughput is usually lower because Ethernet, IP, TCP/TLS, acknowledgments, encryption, peer limits, and intermediate hops all consume part of the link capacity.

When reading machine type specs, verify:

- Whether the published number is a maximum, baseline, or sustained rate.
- Whether bandwidth is bidirectional combined or published separately for ingress and egress.
- Whether the cap applies per NIC, per machine, per flow, or across all flows combined.
- Whether there are burst mechanisms, credits, or load-based adjustments.
- Whether bandwidth is shared with network storage or other services.

Do not convert Gbps directly into application file-transfer speed while ignoring overhead, packet loss, latency, and receiver limits.

### 2.2. Packets Per Second and Packet Size

**PPS (packets per second)** is the number of packets processed per second. A workload sending many small packets can hit a PPS limit before exhausting bit-per-second bandwidth.

For example, services processing millions of small messages, DNS, APIs with many short requests, or proxy systems may need high PPS. A large file-transfer stream usually cares more about bandwidth, though it still needs enough PPS to handle data packets.

Two machine types with the same Gbps rating can still differ in small-packet processing capacity, NIC queue count, network threads, and CPU required for networking. For workloads with many short connections or small packets, measure PPS, networking CPU, and packet drop rates alongside throughput.

### 2.3. Latency, Jitter, and Packet Loss

- **Latency:** time for data to travel from source to destination or for a network operation to complete.
- **Jitter:** variation in latency over time.
- **Packet loss:** percentage of packets lost in transit.

Interactive applications, transactional workloads, and distributed systems are typically sensitive to latency and jitter. TCP may have to retransmit lost packets, increasing completion time; for real-time protocols, packet loss can directly degrade session quality.

High bandwidth does not automatically guarantee low latency. A link may have spare throughput while queues at the NIC, gateway, or network device inflate latency. Measure latency percentiles, packet loss, and retransmissions under representative load.

### 2.4. Per-Flow and Connection Limits

Some platforms enforce per-flow, per-connection, or network-queue limits. Consequently, an application using a single TCP connection may not reach the maximum aggregate bandwidth advertised for the whole instance. Multiple parallel flows can sometimes unlock more capacity, though adding flows increases connection state, CPU overhead, and pressure on the target service.

Do not increase connection counts indefinitely to bypass a limit. Check connection pools, file descriptor limits, NAT/conntrack, ephemeral ports, server-side limits, and provider policies.

## 3. Storage Limits to Understand

A disk subsystem is typically evaluated using three core metrics:

- **IOPS (I/O operations per second):** number of read/write operations per second.
- **Throughput:** volume of data read/written per second, usually measured in MB/s or MiB/s.
- **Latency:** time to complete a single read/write operation.

The three metrics are related but not interchangeable. A volume may achieve high IOPS with small operations without reaching high throughput; conversely, sequential reads of large blocks may achieve high throughput at lower IOPS.

### 3.1. Relationship Between IOPS, I/O Size, and Throughput

Under ideal conditions, approximate throughput is calculated as:

\[
\text{Throughput} \approx \text{IOPS} \times \text{I/O size}
\]

For example, if a workload performs 8,000 operations per second at 16 KiB each:

\[
8.000 \times 16\ \text{KiB} = 125\ \text{MiB/s}
\]

This is the theoretical data rate before overhead and other caps. If the volume only permits 100 MiB/s, throughput will be capped lower. If the machine type supports only 80 MiB/s for network storage, effective capacity cannot exceed that 80 MiB/s cap either.

I/O size is usually determined by the application, filesystem, database, or storage controller. Use operation sizes close to the real workload when benchmarking.

### 3.2. Random Reads, Sequential Reads, and Writes

**Sequential I/O** accesses contiguous data regions, typically fitting large file reads, backups, or data streaming. This load pattern generally cares about throughput.

**Random I/O** accesses scattered locations, typical of databases, indexes, and workloads touching many small records. This load pattern generally cares about IOPS and latency.

The read/write ratio also matters. A synchronous write workload may wait for durable persistence confirmation before proceeding; a read-heavy workload with caching can cut disk trips. Benchmarks using only sequential reads will poorly represent a database performing many random reads and small writes.

### 3.3. Queue Depth and Latency

**Queue depth** is the number of pending or in-flight I/O requests. When requests arrive faster than they complete, queues grow and latency usually rises with them.

Increasing queue depth can help devices leverage internal parallelism better, but beyond a certain point, extra requests only lengthen wait times. For latency-sensitive workloads, find the queue depth where throughput meets requirements while p95/p99 stays within SLOs.

Do not judge a disk solely by peak IOPS. A volume delivering high IOPS with excessive p99 latency may still be unsuitable for transactions needing fast responses.

## 4. Instance-Level vs. Volume-Level Limits

This is a critical point when selecting a machine type: storage performance can be capped simultaneously at both the volume level and the instance level.

A volume may be provisioned with a certain IOPS and throughput level. However, the machine type attaching that volume may also have an aggregate storage bandwidth ceiling. If multiple volumes are attached, their combined capacity can still be capped by the instance ceiling.

Available storage capacity can be thought of as bounded by the minimum of all applicable limits:

\[
\text{Available capacity} \leq
\min(\text{instance limit},\ \text{total volume limit},\ \text{burst/quota limit})
\]

This is a general model. Exact calculations depend on the provider, volume type, volume count, region, and sharing policies.

Example:

| Component | Hypothetical limit |
| --- | ---: |
| Machine type: max storage bandwidth | 500 MiB/s |
| Volume A: provisioned throughput | 300 MiB/s |
| Volume B: provisioned throughput | 300 MiB/s |
| Combined total across two volumes | 600 MiB/s |
| Maximum through the instance | 500 MiB/s |

Even though the two volumes combined could deliver 600 MiB/s on paper, the machine type only allows up to 500 MiB/s at the instance layer. When both volumes run under heavy load simultaneously, they must share that cap.

Some providers also impose separate instance-level IOPS caps, volume-size-dependent limits, or baseline and burst performance tiers. Verify all limits together before locking in a configuration.

## 5. Storage Types and Their Impact on Machine Selection

### 5.1. Network-Attached Block Storage

Block storage is presented as block devices attachable to a virtual machine. Data is typically stored on the provider's distributed storage system, decoupled from the VM lifecycle to a certain degree.

Common advantages include independent sizing of capacity, performance, snapshots, and backup mechanisms. However, I/O travels across storage networking infrastructure and can hit caps at the volume, instance, or shared transport layer.

When selecting a machine type for block storage, check volume IOPS and throughput limits, the instance's storage ceiling, maximum supported volumes, and whether storage traffic shares network bandwidth budgets with application traffic.

### 5.2. Local SSD/NVMe

Local SSDs or NVMe drives attached directly to the host generally offer low latency and high throughput. This storage type suits caches, scratch data, intermediate data, rebuildable indexes, or workloads requiring very fast I/O.

Be careful: local data may be tied to the instance or host lifecycle. Upon stop, termination, host migration, or hardware failure, data may not be preserved depending on service type and policy. Do not use local ephemeral storage as the sole copy of critical data unless the service provides appropriate durability guarantees.

For local SSDs, check device count, capacity, aggregate performance, per-instance caps, and RAID or striping mechanisms if the app requires them. A machine type with many vCPUs but little local storage may not suit an I/O-intensive workload.

### 5.3. Performance Tiers and Burst Mechanisms

Storage services may offer general-purpose volumes, provisioned-IOPS volumes, throughput-optimized volumes, or HDD/SSD devices at varying price tiers. Some tiers scale performance with capacity; others allow temporary bursting or use credits.

If a workload has short spikes, bursting may handle them well. If a workload sustains high load continuously, size for sustained capacity after credits run out. Clearly verify baseline, burst levels, credit earn/spend rates, and how metrics expose throttling.

## 6. Networking and Storage May Share Limits

In many cloud environments, block storage is accessed over the provider's internal network. Some machine types impose a combined cap across network and storage traffic, or maintain separate budgets that still share underlying physical infrastructure.

This can create contention among:

- Application traffic sent and received over the NIC.
- Volume reads and writes from the VM.
- Backups, snapshots, or replication.
- Inter-node data transfers within a cluster.

For example, a machine both serving a file-transfer API and running a large scan job off a network volume can push both traffic types onto the instance's network path. The API may slow down even though CPU has headroom and the volume has not hit its individual cap.

Not every provider bundles these limits together. Check the documentation for the exact machine family to see whether network and storage bandwidth are accounted separately or shared, and inspect observable metrics.

## 7. Determining How Much Network or Disk a Workload Needs

Before picking a machine type, classify the workload by I/O profile.

| Workload | Network characteristics | Storage characteristics |
| --- | --- | --- |
| API serving large content | High egress, many connections, needs steady throughput | May require streaming large file reads |
| Transactional database | Many small requests, latency- and connection-sensitive | Random I/O, synchronous writes, IOPS and p99 latency critical |
| Data warehouse / ETL | Heavy data transfer between nodes or services | Large sequential reads/writes, high throughput |
| Distributed cache | Many small packets, PPS and latency critical | May need persistence or snapshots depending on requirements |
| Backup / replication | Sustained egress/ingress, can contend with primary traffic | Heavy data reads and continuous replica writes |
| Streaming | Long-lived connections, many messages, jitter control needed | Periodic log or segment writes, retention-dependent |
| AI/ML | Data transfer between workers and accelerators | Dataset reads, checkpoints, and model saves can create heavy load |

A workload's profile can shift across phases. For example, a database may read heavily from disk at startup, serve mostly from cache during steady operation, and generate heavy read/write I/O during checkpoints or backups.

## 8. Rough Estimation of Network and Disk Needs

Initial estimates help narrow down machine types before benchmarking. Add overhead, peak load, growth, and headroom to the estimate.

### 8.1. Estimating Network Bandwidth

For an API, application egress can be estimated as:

\[
\text{Egress} \approx
\text{Responses per second} \times
\text{Average response size}
\]

For example, a service returning 200 responses/second at an average of 80 KB each:

\[
200 \times 80\ \text{KB} = 16\ \text{MB/s}
\]

This equals roughly 128 Mbps in decimal units, before protocol overhead and other traffic. When sizing, add request ingress, replication, logs, health checks, backups, and traffic spikes. If response sizes are skewed, also check p95/p99 sizes and peak-hour traffic.

### 8.2. Estimating Disk Capacity

Suppose a database needs 12,000 IOPS with an average I/O size of 8 KiB:

\[
12.000 \times 8\ \text{KiB} = 93.75\ \text{MiB/s}
\]

The volume must sustain both that IOPS level and corresponding throughput. If the machine type has an 80 MiB/s storage ceiling, the machine itself becomes the bottleneck even if the volume is provisioned with higher IOPS. If latency climbs at high queue depths, check sustained limits and read/write patterns before upgrading specs.

### 8.3. Headroom and Peak Load

Do not choose a machine type sized merely for average load. Account for:

- Peak load and peak duration.
- Growth in data, users, and connection counts.
- Background traffic such as backups, replication, logging, and monitoring.
- Performance drops when burst credits deplete or contention occurs.
- Remaining capacity when a node or network path fails.

Headroom must align with SLOs and load patterns. Too little headroom leads to saturation; too much headroom increases costs without proportional value.

## 9. Process for Selecting a Machine Type

A workflow applicable to new workloads or when optimizing existing systems:

1. **Define service objectives:** throughput, p95/p99 latency, error rate, job completion time, and availability requirements.
2. **Measure baseline:** collect ingress/egress traffic, PPS, connections, network latency, IOPS, I/O size, disk throughput, and queue depth.
3. **Classify load patterns:** many small packets vs. large file transfers; random vs. sequential disk; read-heavy vs. write-heavy; steady vs. bursty.
4. **Read platform limits:** check maximum and sustained caps for NIC, instance, volume, storage pool, quotas, and credits.
5. **Calculate combined limits:** check whether volumes share an instance ceiling and whether network and storage share a bandwidth budget.
6. **Choose a machine type family:** network optimized for heavy networking, storage optimized for heavy I/O, or general purpose for balanced needs.
7. **Benchmark on representative configs:** use data and read/write ratios close to production; step load upward incrementally.
8. **Identify saturation points:** find where throughput plateaus while latency, queue depth, packet drops, or errors begin climbing.
9. **Evaluate cost:** compare machine, volume, provisioned IOPS/throughput, data transfer, and headroom capacity costs.
10. **Deploy and monitor:** track metrics post-change, validate SLOs, and keep a rollback path to the prior configuration.

## 10. Monitoring and Diagnosing Limits

When an application slows down, pinpoint which layer is throttling before changing machine types.

| Layer | Metrics to check | Signs to investigate |
| --- | --- | --- |
| Application | Request latency, timeouts, throughput, queues, retries | Which downstream call step is slow? |
| Instance network | Ingress/egress, PPS, packet drops, retransmissions, connection count | Is it hitting NIC, PPS, or connection caps? |
| Network path | Latency, jitter, loss, throughput to peer | Is the bottleneck at the host, gateway, or destination? |
| Volume | IOPS, throughput, read/write latency, burst balance/credits | Has the volume hit its provisioned limit or run out of credits? |
| Instance storage | Total throughput/IOPS, queue, machine storage limit | Are multiple volumes hitting the shared instance ceiling? |
| Operating system | I/O wait, queue depth, CPU softirq, socket statistics | Is CPU busy processing network interrupts or waiting on I/O? |

On Linux, tools like **iostat**, **sar**, **ss**, **ip -s link**, **vmstat**, and **ethtool** help inspect the OS and network interfaces if installed and permitted. Tools do not replace provider metrics: some limits reside at the host or network fabric layer where VMs cannot observe them directly.

Align timestamps between application metrics and infrastructure metrics. If API latency spikes right as volume queue depth climbs, that is evidence to investigate storage. If packet drops or retransmissions rise alongside timeouts, investigate networking. A single metric rarely proves root cause; correlate multiple signals and test under representative load.

## 11. Practical Example: Choosing a Machine for a Database Service

A team deploys a transactional database on a VM. The current machine has enough RAM to hold the working set and low average CPU utilization, yet slow queries appear during peak hours. Metrics show rising IOPS, high volume p99 latency, and prolonged I/O queues. The machine also runs backups, generating extra volume reads and network data transfers.

The team investigates systematically:

1. Measure read/write ratio, I/O size, and IOPS during both normal and peak hours.
2. Compare provisioned volume throughput/IOPS against the instance-level storage ceiling.
3. Check whether backups overlap with peak hours and share network or storage caps with queries.
4. Benchmark volumes using I/O sizes and read/write ratios close to production.
5. Compare machine types with higher storage ceilings, or move backups to off-peak windows or a dedicated machine.
6. Evaluate query p95/p99 latency, backup duration, replication lag, and total cost after changes.

If the volume has plenty of provisioned IOPS while the instance hits its storage ceiling, upgrading only volume specs will not remove the bottleneck. If backups cause contention, rescheduling or isolating workloads can improve queries without scaling up the entire machine. If latency remains high when all limits have spare headroom, investigate execution plans, caches, locks, and query design.

## 12. Common Mistakes

- Picking machines solely by vCPU and RAM while ignoring NIC and storage caps.
- Confusing Gbps with GB/s or MB/s; failing to distinguish bits from bytes.
- Checking only bandwidth while ignoring PPS, latency, jitter, and packet loss.
- Checking only IOPS without considering I/O size, throughput, and latency.
- Summing multiple volume specs while forgetting the aggregate instance-level cap.
- Assuming a dedicated volume implies dedicated physical hardware with zero contention.
- Using local ephemeral disks as the sole store for durable data.
- Sizing for short bursts when the workload runs under continuous high load.
- Raising connection counts or queue depth indefinitely to chase higher throughput.
- Benchmarking with datasets or read/write ratios unlike production.
- Omitting backups, replication, logging, and background traffic from network/disk budgets.

## 13. Selection and Operational Principles

1. **Evaluate the full configuration:** a machine type must fit CPU, RAM, networking, and storage simultaneously.
2. **Read limit types carefully:** distinguish maximum vs. sustained, per-flow, per-volume, and per-instance caps.
3. **Measure the real workload:** use representative traffic, packet sizes, I/O sizes, and read/write ratios.
4. **Watch latency percentiles:** high throughput means little if p95/p99 violates SLOs.
5. **Compute aggregate limits:** verify whether volumes and network streams share a common capacity ceiling.
6. **Match storage to durability:** local SSD fits temporary or rebuildable data; critical data requires services with proper durability guarantees.
7. **Isolate loads when needed:** backups, batch jobs, and replication may require separate schedules or resources to protect primary traffic.
8. **Evaluate cost per unit of work:** include machine, volume, provisioned IOPS/throughput, data transfer, and headroom costs.

Choosing the right machine type starts with understanding how the application exchanges data externally and accesses storage. By identifying network, IOPS, throughput, and latency limits at each layer, engineering teams can pick appropriate configurations, avoid paying for unused capacity, and reduce the risk of bottlenecks as load grows.
