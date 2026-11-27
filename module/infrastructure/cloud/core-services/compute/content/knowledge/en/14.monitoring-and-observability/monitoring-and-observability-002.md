# Collecting CPU, Memory, Swap, Disk, and Network Metrics with an Agent

## Lesson Objectives

To operate virtual machines and cloud workloads, teams need to know how compute resources are being utilized. CPUs can saturate, memory can run low, swap can grow, filesystems can fill up, or network interfaces can drop packets. Looking only at overall CPU utilization misses many critical issues.

A monitoring agent running on a server or node collects operating system metrics, standardizes the data, enriches it with workload-identifying metadata, and sends metrics to a centralized monitoring platform.

After this lesson, you will be able to:

- Explain the metric collection flow from the host to the monitoring system.
- Select appropriate CPU, memory, swap, disk, and network metrics.
- Distinguish between counters, gauges, and rates to read metrics accurately.
- Install and configure an agent/collector with least-privilege permissions.
- Collect metrics on Linux, Windows, VMs, and Kubernetes nodes.
- Design labels, collection intervals, alerts, and data quality checks.

## 1. Why Do You Need a Monitoring Agent?

Virtual machines and compute nodes have many states that cannot be fully observed from application metrics alone. For example, an API may respond slowly because CPU is being stolen at the hypervisor, the system starts swapping, disk latency rises, or a network interface is dropping packets. Looking only at application latency tells the operations team that the service is slow, but not which resource layer is causing the problem.

A monitoring agent is a process or service running on the machine being observed. The agent reads data from the operating system, performance counters, or runtime APIs and sends metrics to a collector/backend.

Common tasks include:

- Reading counters for CPU, memory, paging/swap, filesystems, block devices, and network interfaces.
- Standardizing units, metric names, and timestamps.
- Adding metadata such as hostname, instance ID, zone, environment, and machine role.
- Sending metrics using a protocol supported by the backend.
- Buffering data temporarily when connectivity is interrupted, if supported by the agent.
- Reporting agent status to detect machines that stop sending data.

An agent alone does not solve all observability challenges. Metrics need to be stored, queried, visualized, and correlated with logs/traces. A complete monitoring system typically consists of an agent or exporter, collector, transport pipeline, time-series backend, dashboards, and alerting.

~~~mermaid
flowchart LR
    H["VM / host / node"] --> A["Agent or exporter"]
    A --> C["Collector / telemetry pipeline"]
    C --> B["Metrics backend"]
    B --> D["Dashboards and queries"]
    B --> E["Alerting / notification"]
    L["Application logs and traces"] --> C
    M["Cloud metadata / inventory"] --> C
~~~

In the compute module, the goal is to observe the foundational resources serving workloads: CPU, memory, swap, disk, and network. These metrics help determine machine capacity, detect resource bottlenecks, support sizing, and evaluate the impact of scaling load.

## 2. How Do Agents, Exporters, and Collectors Differ?

Monitoring tools can use many names. You should distinguish roles rather than relying only on product names.

| Component | Role | Example |
|---|---|---|
| Agent | Process running on the host that collects and usually ships telemetry | Cloud monitoring agent, OpenTelemetry Collector running in agent mode |
| Exporter | Exposes metrics from a system in a format that a collector can read | Prometheus Node Exporter |
| Collector | Receives, processes, enriches with metadata, filters, and forwards telemetry | OpenTelemetry Collector, Prometheus |
| Backend | Stores and queries metrics over time | Prometheus-compatible backend, cloud monitoring service |
| Dashboard/alerting | Presents status and evaluates alert conditions | Grafana or provider monitoring UI |

Common deployment models:

**Push agent:** the agent collects metrics and sends them to a central endpoint. This model fits when hosts sit behind firewalls or the backend cannot actively reach the hosts. Authentication, certificates, retries, and buffering must be managed.

**Pull exporter:** the exporter exposes a metric endpoint; Prometheus or a collector scrapes it on a schedule. Access to the endpoint should be restricted by IP/network and protected if it exposes sensitive details.

**Agent combined with collector:** the agent reads local metrics, and a collector processes and forwards them to one or more backends. This approach standardizes data and allows changing backends without reinstalling a different tool on every machine.

No single model fits every environment. Choose based on networking, scale, backend, security requirements, version management, and cloud platform integration.

## 3. Understanding Metric Types Properly

Metrics typically have a timestamp, name, value, unit, and a set of labels/attributes. Before creating dashboards or alerts, you need to know the data type you are observing.

- **Gauge:** a value at a point in time that can increase or decrease. Examples include memory in use, free filesystem space, and current connection count.
- **Counter:** a cumulative counter that normally only increases until the process or machine restarts. Examples include total bytes transmitted, total error packets, and total context switches.
- **Rate:** the rate of change of a counter over a time window. Examples include bytes/second or error packets/second.
- **Histogram:** a distribution of measurements grouped into buckets, commonly used for latency or size; not the primary type for basic host metrics, though useful for workloads.

Do not compare raw counter values between two points in time as if they were a rate. For counters, you usually need to compute a rate or delta over time. When a machine reboots, counters can reset; the query engine must handle resets properly.

Units must be consistent:

| Data type | Common units |
|---|---|
| CPU time | Cumulative seconds or percentage of time |
| CPU utilization | Percentage (%) |
| Memory | Bytes, KiB, MiB, or GiB |
| Swap | Bytes and bytes/second |
| Disk I/O | Bytes/second, operations/second (IOPS), seconds, or milliseconds |
| Network | Bytes/second, packets/second, error count, or drop count |

When a dashboard displays percentages, check the denominator. 50% CPU could mean half of total machine capacity or an average across a subset of cores, depending on the calculation. 80% memory could be calculated against total RAM or available memory. Do not compare two dashboards if their metric definitions differ.

## 4. Collecting CPU Metrics

CPU metrics help answer: does the machine have sufficient processing capacity, what kind of work is CPU time spent on, and is the workload constrained by the scheduler or hypervisor?

Key metrics:

| Metric | Meaning | Interpretation |
|---|---|---|
| CPU utilization | Percentage of time the CPU is busy in the measurement interval | Sustained elevation may indicate CPU pressure |
| User time | Time spent running user-space code | Can rise due to application computation |
| System time | Time spent running kernel code | Increases may relate to syscalls, I/O, or network processing |
| I/O wait | Time the CPU is idle while the system waits for I/O | Increases may accompany disk latency or I/O contention |
| Steal time | Time a vCPU is ready to run while the hypervisor allocates the physical CPU to another workload | May reflect CPU contention on the virtualization host |
| Load average / run queue | Number of runnable tasks or tasks in uninterruptible sleep as defined by the OS | Compare against CPU count and workload state |
| CPU throttling | Time or frequency a container is constrained by CPU quota | Can explain latency even when the node still has free CPU |
| Context switches | Number of context switches | Sharp increases may accompany excessive threads or contention |

### 4.1. CPU utilization does not tell the whole story

A 16-vCPU machine at 40% average utilization can still have one core completely saturated if the workload is single-threaded. Inspect per-CPU/core metrics when needed. For VMs, steal time can be critical because the guest sees CPU unallocated even though the application has work to run.

In Linux, CPU time is commonly read from `/proc/stat`. The `mpstat` command from the `sysstat` package displays user, system, iowait, steal, and idle percentages per CPU:

~~~bash
# CPU and load overview
uptime
lscpu

# Monitor per-core CPU every second, taking 5 samples
mpstat -P ALL 1 5

# Monitor run queue, swap, and system counters
vmstat 1 5
~~~

On Windows, Performance Monitor (PerfMon) or PowerShell `Get-Counter` can read counters such as `Processor(_Total)\% Processor Time`, `System\Processor Queue Length`, and per-processor counters.

~~~powershell
Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 5
Get-Counter '\System\Processor Queue Length' -SampleInterval 2 -MaxSamples 5
~~~

Counter names may be localized according to the Windows language. Windows agents typically read equivalent performance counters and export them as metrics.

### 4.2. CPU in containers

Containers can be constrained by CPU quotas or cpusets. Observe both node CPU and container CPU:

- Container CPU usage.
- CPU limits/requests.
- Throttled periods and throttled time.
- CPU usage per Pod/container.
- Node allocatable and overall utilization.

If a Pod's CPU hits its quota, the container can be throttled even when the node has idle CPU on other cores. In that case, examine limits, cpusets, scheduler behavior, and application parallelism before adding vCPUs to the entire node.

## 5. Collecting Memory Metrics

Memory metrics help detect RAM pressure, memory leaks, large caches, cgroup limits, and the risk of OS process termination.

Metrics to collect:

| Metric | Meaning | Notes |
|---|---|---|
| Total memory | Total RAM visible to the system | May differ from physical capacity due to firmware/hypervisor |
| Used memory | Memory currently in use as defined by the tool | Understand how cache/buffers are accounted |
| Available memory | Estimate of RAM available to allocate to applications without heavy swapping | Often more useful than looking at free memory alone |
| Cached/buffer memory | Memory used for caches or buffers that can be reclaimed to a certain extent | Not a memory leak by default |
| Working set / resident memory | Memory pages currently resident for a process or workload | May differ from virtual memory size |
| Page faults | Accesses to pages not in the page table or requiring reload | Distinguish minor vs. major faults |
| Memory pressure / OOM | Low-memory conditions or process termination | Inspect kernel logs, cgroups, and container events |

Linux uses free RAM to cache the filesystem to accelerate I/O. Therefore, low free memory is not necessarily a problem if available memory is sufficient and the system shows no abnormal paging or pressure.

Linux inspection commands:

~~~bash
free -h
cat /proc/meminfo
vmstat 1 5
ps -eo pid,comm,rss,vsz,%mem --sort=-rss | head
~~~

Where:

- `free -h` displays total, used, free, shared, buff/cache, and available.
- `/proc/meminfo` provides detailed fields such as MemAvailable, Cached, Buffers, and SwapTotal.
- `vmstat` shows memory, swap, and run queue states.
- RSS approximates the process's resident pages; VSZ is mapped virtual address space and does not equate to physical RAM occupied.

On Windows, useful counters include `Memory\Available MBytes`, `Memory\Committed Bytes`, `Memory\% Committed Bytes In Use`, `Process(*)\Working Set - Private`, and `Memory\Pages/sec`. Distinguish committed memory from resident RAM; a process can commit a large amount of memory without keeping all of it in RAM at the same time.

### 5.1. Memory in containers and cgroups

In containers, host memory figures do not reveal how much an individual container is using relative to its limit. The agent needs to collect metrics per cgroup or from the corresponding runtime source:

- Current memory usage.
- Memory limits and requests.
- Working set or usage excluding cache as defined by the tool.
- OOM kills and memory events.
- Page faults or memory pressure if available.

Check the cgroup and runtime versions. Cgroup v1 and v2 have different files, counters, and semantics; the agent should support the version in use. Do not compare `memory.current`, working set, and RSS as though they share the same definition.

## 6. Collecting Swap and Paging Metrics

Swap is storage space used by the operating system as backing store for memory pages not currently held in RAM. On Linux, swap can be a partition or a file. Windows uses a page file with its own virtual memory management mechanism.

Swap gives the OS additional headroom for memory management, but excessive paging can increase latency because storage is much slower than RAM.

Metrics to observe:

- Total swap capacity and swap in use.
- Swap-in and swap-out rates.
- Page-in/page-out counts.
- Major page faults.
- Memory pressure and OOM events.
- Page file usage on Windows.

Non-zero swap usage on a machine does not automatically indicate an incident. The OS may keep infrequently accessed pages in swap even after pressure subsides. More concerning signals are continuous swap-in/swap-out activity, rising major faults, low available memory, and degrading application latency at the same time.

Linux:

~~~bash
# Swap capacity
swapon --show
free -h

# Monitor swap-in (si) and swap-out (so)
vmstat 1 10

# Paging and memory activity statistics
sar -W 1 5
~~~

Windows can monitor `Paging File(_Total)\% Usage`, `Memory\Pages Input/sec`, `Memory\Pages Output/sec`, and related counters. Exact names and availability depend on the OS version.

Do not alert solely because swap usage crosses a fixed threshold. Combine swap level, paging rate, available memory, OOMs, and workload performance. If the system is designed not to use swap, distinguish a configured swap size of 0 from an agent failing to collect the metric.

## 7. Collecting Disk and Filesystem Metrics

Disk has two aspects that must be separated:

- **Filesystem capacity:** available space and inodes in mounted filesystems.
- **Block device performance:** speed and latency of the underlying storage device.

A filesystem with plenty of free capacity can still be slow due to high IOPS or latency. Conversely, a low-throughput disk causes no harm if the workload performs very few reads.

### 7.1. Filesystem capacity

Key metrics:

- Total capacity, used space, and free space.
- Utilization percentage.
- Used and free inodes on filesystems that support inodes.
- Mount point, filesystem type, and read-only status.
- Provisioned volume capacity versus actual filesystem size.

Linux:

~~~bash
# Filesystem capacity by mount point
df -hT

# Inodes
df -i

# Block devices, partition relationships, and mounts
lsblk -f

# Identify mounted filesystems
findmnt
~~~

Windows can collect volume capacity via logical disk counters, WMI/CIM, or OS APIs. Common counters include `LogicalDisk(*)\Free Megabytes` and `% Free Space`.

The agent should filter out virtual or temporary filesystems that do not need monitoring, such as certain `tmpfs`, `overlay`, or runtime mounts. However, do not blindly filter all container filesystems, as that could skip real data volumes.

### 7.2. Block device performance

Commonly used metrics:

| Metric | Meaning |
|---|---|
| Read/write bytes per second | Read/write throughput |
| Read/write operations per second | IOPS |
| Average read/write latency | Time to complete I/O |
| I/O queue depth | Number of requests waiting or in flight |
| Device utilization | How busy the device is as measured by the OS |
| I/O errors/timeouts | Errors or timeouts at the block device layer |

Linux:

~~~bash
# Per-device I/O every second
iostat -xz 1 5

# Kernel block device statistics
cat /proc/diskstats

# Find processes generating I/O (if sysstat/iotop is installed)
pidstat -d 1 5
~~~

On Windows, PerfMon provides counters such as `PhysicalDisk(*)\Disk Reads/sec`, `Disk Writes/sec`, `Disk Read Bytes/sec`, `Disk Write Bytes/sec`, `Avg. Disk sec/Read`, `Avg. Disk sec/Write`, and `Current Disk Queue Length`.

Some cloud platforms provide volume-level metrics such as IOPS, throughput, burst balance, or queue length. Host metrics and block storage service metrics can differ due to caching, virtualization, and measurement methodology. Compare both when investigating disk bottlenecks.

### 7.3. Inodes and file handles

A filesystem can run out of inodes even while free bytes remain. When that happens, applications cannot create new files. Similarly, a process can exhaust file descriptors or handles even when the disk has free capacity.

For workloads that create many small files, monitor inode usage. For applications that open many files or sockets, monitor file descriptors, handles, or appropriate process limits. These are not purely disk capacity metrics, yet they frequently explain write failures.

## 8. Collecting Network Metrics

Network metrics help determine whether the machine is transmitting data as expected and whether packet loss or interface errors are occurring.

Metrics to collect:

- Bytes received/sent.
- Packets received/sent.
- Receive/transmit errors.
- Receive/transmit drops.
- Interface state and link speed when readable.
- TCP retransmissions, connection counts, and socket states.
- DNS requests/errors or network latency if supported by the agent and tooling.
- Flow logs or cloud network telemetry to understand connectivity between resources.

Linux:

~~~bash
# Interfaces, addresses, and state
ip -s link

# Sockets and connection states
ss -s
ss -tan

# Interface counters
cat /proc/net/dev

# TCP statistics
nstat
~~~

If `sar` from `sysstat` is available:

~~~bash
sar -n DEV 1 5
sar -n TCP,ETCP 1 5
~~~

Windows can use PerfMon counters such as `Network Interface(*)\Bytes Total/sec`, `Bytes Received/sec`, `Bytes Sent/sec`, `Packets Received Errors`, `Packets Outbound Errors`, and TCP connection counters. Counter names depend on locale and OS version.

### 8.1. Throughput does not equal network health

Low throughput can be normal when the application has no traffic. High throughput can be valid during batch jobs. Rising packet drops, retransmissions, or interface errors are the signals that must be examined alongside load.

For cloud VMs, actual bandwidth may be capped by instance type, VM size, flow count, placement, or platform policies. Some instances have burst mechanisms or aggregate traffic limits. Compare guest metrics with cloud provider metrics when determining whether the limit sits in the guest OS or network infrastructure.

### 8.2. Network in containers

On Kubernetes, network metrics can appear at multiple layers:

- Pod/container network bytes and packets.
- Node interface.
- Virtual interfaces or bridges.
- CNI dataplane.
- Cloud NIC or load balancer.

Do not sum all layers together as if they were independent traffic; the same packet may be counted at multiple points. Identify the measurement point and traffic direction before building dashboards.

## 9. Agent-Based Metric Collection Architecture

A basic host metric pipeline involves these steps:

1. The agent reads data from OS APIs, `/proc`, `sysfs`, performance counters, or cgroups.
2. The receiver/scraper converts the data into typed metrics with timestamps and units.
3. The processor filters unneeded metrics, renames/converts units if necessary, and adds resource attributes.
4. The exporter sends metrics to the backend using a supported protocol.
5. The backend stores time series; dashboards and alerting query the data.

~~~mermaid
flowchart TD
    subgraph HOST["Linux / Windows / VM node"]
        OS["OS counters: CPU, memory, swap, disk, network"]
        CG["cgroup / container runtime"]
        AG["Agent: receiver + processor"]
        OS --> AG
        CG --> AG
    end
    AG -->|TLS / authenticated telemetry| COL["Central collector"]
    COL --> PROC["Filter, enrich, batch"]
    PROC --> MET["Metrics backend"]
    MET --> DASH["Dashboards"]
    MET --> ALERT["Alert rules"]
~~~

### 9.1. Choosing tools

Common options:

| Tool | How it is used | Best suited when |
|---|---|---|
| OpenTelemetry Collector | Uses `hostmetrics` receiver and exporters to collect/forward metrics | You want standardized telemetry and ability to send to multiple backends |
| Prometheus Node Exporter | Exposes host metrics via HTTP endpoint for Prometheus to scrape | Your stack uses Prometheus and you want Linux host visibility |
| AWS CloudWatch Agent | Collects metrics/logs on EC2 and supported servers | Using Amazon CloudWatch as the monitoring platform |
| Azure Monitor Agent | Collects guest data and forwards to Azure Monitor via data collection rules | Managing VMs with Azure Monitor |
| Google Cloud Ops Agent | Collects metrics/logs on VMs and sends to Cloud Monitoring/Logging | Using the Google Cloud Operations suite |
| Windows Performance Counters | Native counter source for agents or collectors on Windows | Observing Windows hosts and processes |

Standardize on one primary agent per purpose and avoid installing multiple agents collecting the same metrics without a reason. Duplicate collection increases CPU, memory, network, and storage costs; it can also produce metrics with conflicting names and definitions.

### 9.2. OpenTelemetry Collector hostmetrics example

The conceptual configuration below illustrates collecting CPU, load, memory, paging, disk, filesystem, network, and process metrics and sending them over OTLP. You need a Collector distribution containing the corresponding `hostmetrics` receiver and `otlp` exporter; the endpoint, certificates, and supported scrapers must match your deployed version.

~~~yaml
receivers:
  hostmetrics:
    collection_interval: 30s
    scrapers:
      cpu:
      load:
      memory:
      paging:
      disk:
      filesystem:
      network:
      processes:

processors:
  batch:
    timeout: 10s
  resourcedetection:
    detectors: [system]
    timeout: 2s

exporters:
  otlp:
    endpoint: metrics-gateway.internal.example:4317
    tls:
      insecure: false

service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      processors: [resourcedetection, batch]
      exporters: [otlp]
~~~

In this configuration:

- `collection_interval` sets the metric reading interval to 30 seconds.
- `scrapers` selects the data categories to collect.
- `resourcedetection` adds system metadata if supported by the detector and environment.
- `batch` groups metrics before sending to reduce overhead.
- `otlp` sends data to the collector/backend over TLS.

This is a foundational template, not a complete configuration for every operating system. On Windows, some scrapers or fields may differ from Linux. In cloud environments, an additional detector may be needed to attach cloud provider, region, instance ID, and account/project. Verify the schema of the deployed Collector version before rolling out.

### 9.3. Node Exporter scraping example

When using Prometheus Node Exporter, Prometheus can scrape the exporter's endpoint:

~~~yaml
scrape_configs:
  - job_name: linux-hosts
    scrape_interval: 30s
    static_configs:
      - targets:
          - vm-app-01.internal.example:9100
          - vm-app-02.internal.example:9100
~~~

Protect the exporter port with a firewall, management network, or authentication via an appropriate proxy/service mesh. Do not expose metrics endpoints to the Internet; endpoints can leak hostnames, mount points, kernel versions, interfaces, and operational details.

## 10. Installing and Configuring Agents Securely

Agent deployment should be managed as an infrastructure change:

1. Identify the OS, CPU architecture, agent version, and trusted package source.
2. Verify package signatures or checksums according to vendor procedures.
3. Pilot on a representative VM first.
4. Grant permissions to read required counters using a dedicated service account.
5. Configure endpoint, TLS, certificates, and authentication.
6. Enable only the scrapers/metrics actually needed.
7. Configure resource labels and drop excessively high-cardinality data.
8. Set appropriate retry, batch, and buffer policies.
9. Enable service auto-start and verify health.
10. Roll out by machine group, monitoring overhead and data quality.

Agents often need read access to certain OS sources. Do not grant broad root/Administrator privileges if the tool supports running with narrower capabilities or permissions. If an agent requires elevated privileges to read kernel metrics, restrict binary permissions, package sources, config modification rights, and who can restart the service.

Securing agent connections:

- Use TLS and client authentication when supported by the backend.
- Store certificates/keys in a protected location with minimal read permissions.
- Never place tokens or credentials on command lines, in logs, or in images.
- Restrict egress from hosts to the collector endpoint.
- Track agent version, status, and last metric transmission time.
- Have a procedure to revoke certificates when a host is terminated or compromised.

### 10.1. Managing agents via images and bootstrap

In the cloud, agents can be baked into a custom image or installed during VM bootstrap. Baking into an image ensures machines boot with the agent ready, though it requires an image update workflow when agent patches arrive. Installing during bootstrap gives version flexibility, but depends on package repositories, networking, and startup scripts.

Either way, never bake per-machine credentials into images. When a VM boots, provision a distinct identity or retrieve short-lived credentials via instance identity/managed identity.

## 11. Labels and Metadata for Metrics

Metrics are only useful when operators know which machine, workload, and environment they belong to. Common resource attributes/labels include:

- `service.name` or workload name.
- `deployment.environment` such as dev, staging, production.
- `host.name` or stable instance ID.
- Cloud provider, account/project, region, and zone.
- Machine/instance type or node pool.
- Operating system and architecture.
- Cluster, namespace, node, Pod, or container when applicable.
- Owner or responsible team.

For example, a CPU metric might carry attributes: `service=orders-api`, `environment=production`, `region=asia-southeast1`, `instance_id=vm-example`, `role=application`.

Avoid placing high-cardinality values into labels on every metric, such as request IDs, user IDs, session IDs, full command lines, constantly changing container IDs, or random filenames. Every label combination creates a new time series; rapid cardinality growth drives up storage, query, and backend memory costs.

Labels should describe relatively stable resources. Per-request or per-event details belong in logs/traces, which have storage and query mechanisms suited for them.

## 12. Collection Intervals, Overhead, and Storage

The scrape interval affects granularity, detection latency, and cost. Collecting every second captures short fluctuations but generates more samples and increases overhead. Collecting every minute reduces data volume but may miss brief spikes.

| Reference interval | Use case | Trade-off |
|---|---|---|
| 5–10 seconds | Latency-sensitive workloads, incident investigation, or fast-reacting metrics | More samples and higher cost |
| 15–30 seconds | Standard operational monitoring | Balances granularity and cost |
| 60 seconds or more | Capacity trends and low-volatility workloads | Coarser data, harder to see short spikes |

These are reference ranges, not mandatory standards. Choose based on alerting goals, backend capacity, host count, and budget.

Overhead depends on the number of scrapers, interfaces/filesystems, processes, collection interval, processing, and exporters. Measure the CPU/memory footprint of the agent itself during piloting. If the agent consumes significant resources, disable unneeded metrics, increase the interval, or offload processing to a central collector.

With time-series backends, sample volume scales with host count multiplied by metrics per host, intervals per day, and retention days. Labels multiply time series count, so factor in cardinality as well. Design retention by purpose: keep high-resolution metrics shorter, and keep downsampled/aggregated data longer for trend analysis.

## 13. Building Dashboards for CPU, Memory, Swap, Disk, and Network

Dashboards should answer operational questions rather than merely displaying lots of charts.

A suggested layout:

| Section | Charts | Questions to answer |
|---|---|---|
| CPU | Per-core utilization, user/system/iowait/steal, load, throttling | Is the machine saturated or CPU-constrained? |
| Memory | Available, used, cache, working set, OOMs | Is there RAM pressure or abnormal growth? |
| Swap | Used, swap-in/out rate, page faults | Is the system continuously paging? |
| Disk | Filesystem used %, inode %, IOPS, throughput, latency, queue | Is a volume filling up or I/O-bottlenecked? |
| Network | RX/TX throughput, packet errors/drops, retransmissions | Is an interface seeing errors or abnormal traffic? |
| Agent health | Last scrape, last export, agent process, queue/drops | Is data being delivered reliably? |

Maintain both overview dashboards by environment/cluster/role and detailed per-host dashboards. When selecting a host from an overview table, operators should be able to drill down into CPU, memory, disk, network, and related deployment events.

A good dashboard clearly displays units, time ranges, metric sources, percentage definitions, and missing-data states. If an agent stops sending metrics, a chart can look as if resource usage dropped to zero; distinguish no data from an actual zero value.

## 14. Designing Context-Aware Alerts

Alerts should detect sustained conditions or combined signals, avoiding notifications on every brief spike.

Example conditions to consider:

- Sustained high CPU utilization over several minutes accompanied by rising run queue or request latency.
- Sustained low available memory accompanied by major page faults or OOM events.
- Continuous swap-in/swap-out activity paired with memory pressure.
- Filesystem or inode usage nearing exhaustion and trending toward full before the next operational window.
- Rising disk latency/queue depth without a corresponding increase in I/O throughput.
- Rising network errors/drops or retransmissions above baseline.
- Agent failing to send metrics for longer than the expected interval.

Do not apply a single threshold across all workloads. Databases, web servers, and batch workers have different usage profiles. Filesystem alerts should consider absolute free space, percentage, and growth rate. A 100 GiB volume with 10% left may fill up faster than a 10 TiB volume with 5% left depending on write rate.

### Illustrative PromQL examples

If the backend is Prometheus-compatible and metrics follow corresponding naming conventions, queries can follow patterns like:

~~~promql
# Average CPU busy across cores
100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])))

# Filesystem usage percentage
100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"}
         / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})

# Network receive rate per interface
rate(node_network_receive_bytes_total[5m])
~~~

Metric names and labels depend on the exporter. Filter out virtual filesystems or irrelevant mounts according to your actual environment, and handle filesystems with zero size or without valid `avail` values. The CPU query above averages across selected CPUs; on multi-core systems, also include a per-core dashboard to catch single-core saturation.

### Avoiding false positives and duplicate alerts

- Use `for` or sustained duration windows to filter brief spikes.
- Group alerts by host, workload, and root cause.
- Attach owner, runbook URL, and severity to alerts.
- Create time-bound silences for maintenance windows.
- Alert on agent health independently from host resource metrics.
- Avoid high-churn labels that cause every instance to fire redundant separate alerts.

## 15. Observing in Cloud Environments

Guest OS metrics and cloud provider metrics complement one another.

| Observation layer | Examples | Value |
|---|---|---|
| Guest OS agent | CPU, memory, swap, filesystem, processes, interfaces | Shows state as seen by the guest OS |
| Hypervisor/cloud host | CPU credits, host contention, or service-level instance metrics | Adds provider-managed infrastructure perspective |
| Block storage service | IOPS, throughput, queue/burst metrics | Cross-checks volume performance at the service layer |
| Network service | NICs, load balancers, flow logs, packet/drop metrics | Analyzes network paths and service limits |
| Container platform | Pods, nodes, cgroups, throttling, and networking | Connects host resources to scheduled workloads |

A guest agent cannot always observe everything at the hypervisor or storage service. Conversely, cloud provider metrics may not show how much RAM a specific process is using. Combining both sources narrows down root causes faster.

### 15.1. Virtual machines

On VMs, the agent reads guest OS data. Attach instance ID, instance type, region/zone, account/project, and environment to correlate with cloud metrics. When VMs are replaced by autoscaling, use stable resource IDs and logical service labels to track the entire fleet.

### 15.2. Containers and Kubernetes

Agents can run as a DaemonSet so every node has a host metric collector. Container metrics should be read from cgroups or the appropriate kubelet/runtime API. Distinguish between:

- Node capacity and node allocatable.
- Pod requests/limits.
- Container usage and throttling.
- Host filesystem and container ephemeral storage.
- Node networking and Pod networking.

Do not run a separate host agent inside every container just to read the same node metrics. A one-agent-per-node design typically reduces duplication; container-level metrics are pulled from the runtime or kubelet according to architecture.

### 15.3. Serverless

Serverless environments typically do not allow installing a host agent on provider-managed physical machines or runtimes. Use built-in service metrics and logs such as invocations, duration, concurrency, memory allocation/usage where provided, throttling, errors, and timeouts. If detailed application metrics are needed, instrument code with the OpenTelemetry SDK or telemetry mechanisms supported by the service.

## 16. Checking Data Quality and Agent Health

An active agent does not guarantee complete and accurate data. Monitor the agent itself:

- Whether the service/process is running.
- Agent version and last update time.
- Timestamp of the most recent scrape.
- Timestamp of the most recent successful export.
- Number of metrics sent, export errors, and dropped data points.
- Queue/buffer size and retry duration.
- CPU/memory consumed by the agent.
- Certificate status and backend connectivity.

Cross-verification checks:

1. Compare `free`, `vmstat`, `iostat`, and `ip -s link` against the dashboard at the same timestamp.
2. Verify metric units and labels.
3. Verify timestamps and time synchronization.
4. Check counter resets after reboots.
5. Verify each host has only one primary metric source for the same data type.
6. Confirm dashboards show no data when an agent stops.
7. Compare guest metrics with cloud provider metrics when discrepancies arise.

Do not treat missing data as zero resource usage. Alerting must include dedicated rules to detect targets/agents losing data.

## 17. Troubleshooting Metric Collection

| Symptom | Possible cause | Where to check |
|---|---|---|
| Host has no metrics | Agent not running, wrong scrape target, or host not registered | Check service, endpoint, and target discovery |
| Delayed metrics | Full queue, slow network, retries, or slow backend ingestion | Inspect export errors, queues, network, and backend |
| Metrics always zero | Wrong permissions, wrong scraper, wrong label, or unsupported OS | Compare with OS tools and check agent logs |
| Duplicate metrics | Multiple agents installed or same exporter scraped multiple times | Check pipeline and target discovery |
| Filesystem cardinality growth | Containers/mounts continuously creating new series | Filter temporary mounts, standardize labels, and tune retention |
| High agent CPU usage | Too many scrapers, overly short interval, or heavy process scanning | Disable unneeded metrics, increase interval, and re-measure |
| Export failures | TLS, certificates, DNS, firewall, or credentials | Check endpoint, trust chain, and permissions |
| Host/cloud metric discrepancy | Two sources measuring at different layers or intervals | Check definitions, timestamps, and measurement points |

On Linux, check the agent with systemd:

~~~bash
systemctl status otelcol
journalctl -u otelcol --since "15 minutes ago"
~~~

Service names vary by installation method and distribution. On Windows, inspect Services, Event Viewer, and agent logs. Never include tokens or private keys in output when sharing logs for incident support.

## 18. Securing Telemetry Data

Infrastructure metrics are usually less sensitive than application payloads, yet they can still reveal internal information: hostnames, network topology, mount points, instance types, load patterns, uptime, and indicators of critical systems.

Protective measures:

- Only allow agents to send to approved collectors/backends.
- Use TLS and agent authentication.
- Restrict access to dashboards, queries, and metric APIs.
- Isolate tenants/projects or workspaces across environments when needed.
- Restrict labels that may contain usernames, command lines, or sensitive details.
- Apply retention and data deletion policies.
- Audit changes to pipelines, alert rules, and access permissions.
- Never expose exporter endpoints publicly.

An agent with system read privileges is a privileged component. Keep agents patched, verify package sources, restrict configuration write permissions, and monitor binary/service modifications.

## 19. Phased Agent Rollout Process

A safe rollout can follow these steps:

1. **Survey:** inventory OSes, versions, architectures, VM/node groups, and backends.
2. **Design metrics:** select the CPU, memory, swap, disk, network, and metadata actually needed.
3. **Pilot:** deploy on a representative Linux VM, Windows VM, and node/container if applicable.
4. **Cross-check:** compare agent metrics with OS tools and cloud provider metrics.
5. **Assess overhead:** measure CPU, memory, disk, and network generated by the agent.
6. **Secure:** verify TLS, credentials, firewalls, and agent permissions.
7. **Expand:** roll out by environment/role/zone with ability to halt per group.
8. **Observe:** inspect coverage, missing data, duplicate series, and export errors.
9. **Standardize:** update dashboards, alert rules, owners, and runbooks.
10. **Operate:** manage agent versions, apply periodic updates, and decommission agents when hosts are terminated.

Use automation/configuration management to guarantee consistent configuration. For autoscaling groups or node pools, install the agent via image, bootstrap, or DaemonSet so new machines automatically join monitoring. Maintain inventory or service discovery so new targets are discovered and terminated targets are removed.

## 20. Common Mistakes and How to Avoid Them

**Monitoring only CPU:** misses memory pressure, disk latency, inode exhaustion, and packet drops. Use a baseline metric set covering all five resource groups.

**Judging RAM shortage by free memory:** Linux uses RAM for reclaimable caches. Monitor available memory, paging, pressure, and OOMs together.

**Alerting solely on swap usage:** used swap can be historical state. Watch swap-in/out rates and memory pressure.

**Watching only filesystem usage:** a volume with free space can still suffer IOPS or latency bottlenecks. Monitor capacity and block device performance separately.

**Looking at network throughput while ignoring errors/drops:** low traffic does not prove a healthy interface. Collect packet errors, drops, and retransmissions.

**Summing metrics across layers:** the same I/O or packet can be counted at the guest, container, and cloud service. Identify the measurement point before aggregating.

**Installing overlapping agents:** increases overhead and creates duplicate metrics. Standardize on one agent per host group.

**Setting scrape intervals too short:** increases agent, network, and backend load. Choose intervals based on detection objectives and budget.

**Using high-cardinality labels:** explodes time series counts and costs. Use only stable labels with operational value.

**Failing to monitor the agent itself:** a host can stop reporting without any dashboard warning. Create separate alerts for agent health and missing data.

**Exposing metrics endpoints to the Internet:** leaks system information and widens the attack surface. Restrict networks, use TLS, and enforce authentication.

## 21. Infrastructure Metric Collection Checklist

- [ ] Agent matches the OS, architecture, and cloud environment.
- [ ] Overall and per-core CPU metrics collected as needed, including user/system/iowait/steal.
- [ ] Memory available, usage, cache/working set, and OOM signals collected.
- [ ] Swap capacity, swap usage, and paging rates collected.
- [ ] Filesystem capacity, inodes, and block device performance collected.
- [ ] Network throughput, packets, errors, drops, and retransmissions collected where supported.
- [ ] Container metrics read from cgroups/runtime and separated from host metrics.
- [ ] Metrics have consistent timestamps, units, and resource labels.
- [ ] Scrape interval, retention, and cardinality fit within budget.
- [ ] Agent runs with least privilege, TLS, and protected credentials.
- [ ] Agent health, export errors, and missing data are monitored.
- [ ] Metrics cross-checked against OS tools and cloud provider metrics.
- [ ] Overhead measured before broad rollout.
- [ ] Dashboards, alert rules, owners, and runbooks exist for each resource group.
- [ ] Procedures exist for updating, rolling back, and removing the agent.

Collecting CPU, memory, swap, disk, and network metrics via an agent builds the foundation for observing virtual machine and compute node health. Select metrics based on operational questions, understand counters/gauges/rates, attach stable metadata, and verify readings against the OS. A secure agent pipeline requires least-privilege permissions, encrypted transport, monitoring of the agent itself, and controlled rollout. Combining guest metrics with cloud service metrics enables teams to pinpoint resource bottlenecks, plan sizing, and resolve incidents faster.
