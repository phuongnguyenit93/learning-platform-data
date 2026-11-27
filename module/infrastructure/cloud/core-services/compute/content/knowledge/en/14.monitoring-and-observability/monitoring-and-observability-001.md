# Distinguishing Metrics from the Hypervisor, Operating System, and Application

When a virtual machine or workload runs slowly, dashboards can show seemingly different numbers: the cloud platform reports low CPU, the operating system sees CPU near saturation, and the application records rising latency. These figures do not necessarily contradict one another. They are measured at different layers, with different observation scopes, calculation methods, and sampling intervals.

To diagnose accurately, it is necessary to understand the three main telemetry layers:

- **Hypervisor/platform layer:** observes virtualized resources, physical hosts, and cloud services provisioned for the VM.
- **Guest operating system layer:** observes CPU, RAM, disk, network, and processes inside the VM.
- **Application layer:** observes requests, transactions, queues, dependencies, and the results that users actually receive.

No single layer can completely replace the other two. The platform helps identify infrastructure limits and health; the operating system indicates which resource is busy; the application reveals the impact on functionality and user experience. This lesson guides you on how to read, correlate, and combine those metrics to find the root cause rather than looking at only a single dashboard.

## 1. Three Observation Layers and Measurement Boundaries

### Hypervisor and cloud platform layer

The hypervisor is the virtualization software layer that divides physical server resources into virtual machines. In the public cloud, operators typically do not access the hypervisor directly. Instead, the provider publishes metrics at the level of the VM, host, virtual NIC, volume, or managed service.

Metrics at this layer can reflect:

- CPU time or vCPU utilization allocated to the VM.
- Performance limits of the machine type, CPU credits, or policy-based throttling.
- Allocated memory, host-level consumption, or memory pressure if published by the provider.
- IOPS, throughput, latency, and queue depth of block volumes.
- Bytes, packets, drops, or bandwidth limits of virtual NICs.
- VM status, host maintenance, migration, and platform events.
- Quotas, capacity, and service limits.

Not every cloud provider publishes the same set of metrics. Some metrics only appear when enhanced monitoring is enabled, a guest agent is installed, or an appropriate instance type is selected. Even a metric named "CPU utilization" can have different definitions, intervals, and scopes across platforms.

### Guest operating system (guest OS) layer

The guest OS is the operating system running inside the VM, such as Linux or Windows. It sees the virtual CPUs, the RAM allocated to the VM, and virtual block devices and network interfaces.

Common metrics include:

- CPU user, system, idle, iowait, steal, and run queue.
- RAM total, available, cache, buffer, RSS, and swap.
- Page faults, memory pressure, and OOM kills.
- Disk read/write, I/O wait, queue depth, filesystem capacity, and inodes.
- Network bytes, packets, errors, drops, retransmissions, and connection states.
- Process count, threads, file descriptors, sockets, and service health.

The guest OS shows how resources visible from inside the machine are being used. It does not always know how heavily loaded the physical host is or at which layer the provider is throttling resources.

### Application layer

The application sees business activity and actual processing time:

- Request rate, number of transactions, or completed jobs.
- Error rate, timeouts, retries, and business outcomes.
- Latency p50, p95, p99, and per-stage duration.
- Queue depth, number of busy workers, and wait time.
- Connection pools, cache hit ratio, and database query latency.
- Duration of calls to dependent services and errors by endpoint.
- Number of sessions, concurrent users, or pending messages.

Application metrics show whether users are affected. CPU can be low while the application is still slow due to the database, DNS, locks, queues, or external services.

### Observation map

~~~mermaid
flowchart TB
    U["User / Client"] --> A["Application"]
    A -->|Request, latency, error, queue| AM["Application metrics, logs, traces"]
    A -->|System calls, socket, file I/O| G["Guest OS"]
    G -->|CPU, RAM, disk, network, process| GM["OS metrics and logs"]
    G --> H["Hypervisor / Cloud platform"]
    H -->|vCPU scheduling, virtual NIC, volume, host| HM["Platform metrics and events"]
    AM --> O["Observability system"]
    GM --> O
    HM --> O
~~~

The diagram illustrates the high-level observation flow. Application, guest, and platform metrics are typically collected through different paths and then unified in the observability system.

## 2. What Is a Metric and Which Metadata Should You Read?

A metric is a measurement recorded over time. A time series usually consists of a metric name, a value, a timestamp, and labels describing its scope.

For example, a VM's CPU utilization might have labels such as:

- instance ID.
- region and availability zone.
- account/project/subscription.
- device or interface.
- environment and service.
- image version or deployment version.

A metric name and a numeric value are not enough. Before comparing, you need to know the unit, measurement type, sampling interval, scope, and aggregation method.

### Three basic metric types

| Type | Meaning | Example | How to read |
|---|---|---|---|
| Gauge | Value at a point in time, can increase or decrease | RAM available, queue depth, connection count | Check current value, min/max, and trend |
| Counter | Cumulative total, usually only increases and resets when a process restarts | CPU seconds, request count, bytes sent | Compute rate via delta over time, handling resets |
| Histogram | Distribution of observations grouped into buckets or statistical structures | Request duration, response size | Used to calculate percentiles and inspect distribution tails |

Do not take derivatives or rates on a gauge the way you would for a counter. Conversely, do not treat a cumulative counter value as the number of requests in one minute.

### Units and scope

Example units:

- CPU: percentage, vCPU, CPU-seconds.
- RAM: bytes, MiB/GiB, percentage.
- Disk: bytes/s, operations/s, milliseconds, queue depth.
- Network: bits/s, bytes/s, packets/s, errors.
- Application: requests/s, milliseconds, jobs, messages.

Distinguish bits from bytes, MiB from MB, GiB from GB, and instantaneous values from averages over a time window. An 80% metric aggregated as a 5-minute average can hide a 100% spike lasting 20 seconds.

### Labels and cardinality

Labels help filter and group metrics. For example, filtering by instance ID to find a specific VM or grouping by service to compare replicas.

However, do not put very high-cardinality values into labels, such as user ID, request ID, session ID, or URLs containing arbitrary parameters. The number of time series can grow rapidly, consuming memory and storage cost while making queries slow or difficult.

Use trace IDs or log fields for per-request identifiers. Keep metric labels stable, such as service, endpoint template, region, environment, and status class.

## 3. CPU: From Host Scheduler to Process

CPU is a classic example of how the three layers can report different results.

### Metrics at the hypervisor/platform layer

Depending on the provider, there may be:

- VM vCPU utilization or CPU usage.
- CPU credit balance and credit consumption for burstable machine families.
- CPU throttling or performance limits.
- CPU ready time or scheduling delay on certain virtualization platforms.
- Host maintenance or migration events.

CPU ready is the time a VM has work to run but must wait for the hypervisor to schedule its vCPU onto a physical CPU. This metric is meaningful on certain platforms such as VMware environments, but it is not a universal metric published by all public clouds.

CPU credits on burstable machines reflect the ability to sustain high performance according to the machine type's credit accumulation and consumption mechanism. When credits are low or reach their limit, performance may be reduced by policy. Do not apply the credit model to every instance family.

### CPU metrics in Linux

Linux commonly breaks CPU time into the following categories:

- **user:** running code in user space.
- **system:** running kernel code.
- **idle:** CPU has no work to do.
- **iowait:** CPU is idle while the system waits for I/O to complete; this is not a direct measure of disk latency.
- **steal:** time the guest wanted to run, but the hypervisor allocated the CPU to another workload.
- **irq/softirq:** handling hardware interrupts and software interrupts.

They can be observed with:

~~~sh
mpstat -P ALL 1
vmstat 1
top
pidstat -u 1
cat /proc/stat
~~~

If steal time increases, the VM may be experiencing CPU scheduling contention at the virtualization layer. However, this metric is not provided or interpreted identically across all platforms. Some environments hide or cannot measure guest steal time.

### CPU metrics in Windows

Windows can observe CPU across multiple scopes:

- Processor Time per logical processor.
- Process/Thread CPU time.
- Processor Queue Length.
- Context switches.
- Hypervisor or virtualization counters if supported by the host/guest and tooling.

PowerShell examples:

~~~powershell
Get-Counter '\Processor(_Total)\% Processor Time'
Get-Counter '\System\Processor Queue Length'
Get-Counter '\Process(*)\% Processor Time'
~~~

Counter names may be localized or vary by Windows version. Performance Monitor can be used to select the exact counters on the target machine.

### CPU metrics at the application layer

The application can measure:

- Request rate and processing duration.
- Worker busy/idle.
- Thread pool queue.
- Number of active running tasks.
- CPU time per process or runtime.
- GC CPU and pause time for JVM applications.
- Event loop lag for asynchronous runtimes.

A service with high CPU and high request latency may be compute-bound. However, if CPU is low, queues are high, and latency increases, the cause may be slow dependencies, lock contention, or a thread pool unable to allocate workers.

### Cross-layer CPU reading examples

| Platform | Guest OS | Application | Hypothesis to verify |
|---|---|---|---|
| High CPU | High CPU, high run queue | Throughput drops, latency rises | Insufficient CPU or overly heavy processing code |
| Low CPU | Steal time or throttling rises | Latency rises | Virtualization-layer limits/scheduling or CPU quota |
| Low CPU | High iowait | Requests slow when reading data | Disk or filesystem is slow |
| Low CPU | Low CPU, queue grows | Slow requests, dependency duration rises | Database, network, or dependent service |
| Low average CPU | One core at 100% | One endpoint is slow | Sequential execution or single-threaded hotspot |

Do not resize CPU solely because utilization is high for a short burst. Look at the run queue, throughput, latency, steal/throttle, number of busy cores, and the application's parallelism.

## 4. Memory: Allocated Memory, Available Memory, and Working Set

### Metrics at the platform layer

The platform may provide the RAM size configured for the VM, host memory usage, or certain memory pressure metrics. However, many public clouds cannot accurately infer memory usage inside the guest without an agent or metrics reported by the OS.

Distinguish between:

- RAM allocated to the VM.
- Host RAM consumed to back the VM.
- RAM used by the guest.
- Memory ballooning or host swapping if published by the platform.
- Memory the application actually needs to hold its working set.

Do not treat the VM's configured RAM capacity as a utilization metric.

### Metrics in Linux

Useful commands:

~~~sh
free -h
cat /proc/meminfo
vmstat 1
ps -eo pid,comm,rss,vsz --sort=-rss | head
~~~

Key concepts:

- **Total:** total RAM visible to the guest.
- **Available:** estimate of memory that can be allocated to new workloads without significant swapping; usually more useful than looking at free alone.
- **Cache/buffers:** memory used for caching data and metadata, part of which can be reclaimed.
- **RSS:** memory pages currently resident in RAM and mapped into the process.
- **VSZ:** virtual address space, not synonymous with physical RAM in use.
- **Swap:** storage space used as backing for memory pages evicted from RAM.
- **Page fault:** page fault; a minor fault requires no disk read, whereas a major fault requires I/O to load the page.
- **OOM kill:** the kernel terminates a process when it cannot satisfy an allocation under memory pressure.

Memory utilization percentage can be misleading if reclaimable cache is treated as permanently occupied memory. Inspect available memory, working set, swap activity, page faults, and OOM events together.

### Metrics in Windows

Commonly used counters:

- Available MBytes.
- Committed Bytes and Commit Limit.
- Pages/sec or page reads/writes.
- Process Working Set and Private Bytes.
- Pool Nonpaged Bytes and Paged Bytes.

Examples:

~~~powershell
Get-Counter '\Memory\Available MBytes'
Get-Counter '\Memory\Committed Bytes'
Get-Counter '\Memory\Pages/sec'
Get-Counter '\Process(*)\Working Set - Private'
~~~

Pages/sec alone does not automatically mean the machine is out of RAM; it should be combined with page reads, available memory, disk activity, and application impact.

### Memory metrics at the application layer

The application/runtime can provide:

- Heap used, committed, and maximum.
- Garbage collection count, pauses, and allocation rate.
- Native/direct memory.
- Cache size and evictions.
- Object count or session count.
- Memory per worker or process.
- OOMs, allocation failures, and memory leak indicators.

With the JVM, low heap used does not prove total process memory is low. Native memory, thread stacks, metaspace, direct buffers, and native libraries still consume RAM.

### Cross-layer memory reading examples

If the cloud dashboard shows the VM has 32 GiB of RAM, Linux reports only 1 GiB available, process RSS steadily climbs, and the application hits OOM, there may be insufficient RAM or a memory leak. If Linux reports low free memory but most of it is reclaimable page cache, the application has no OOMs, and latency is stable, there is not enough evidence to increase RAM.

If the guest has plenty of available memory but the application reports allocation failures, check container/cgroup limits, heap caps, process address space, or runtime limits before increasing VM size.

## 5. Storage: Volumes, Block Devices, Filesystems, and Application Operations

Storage also has multiple measurement layers.

### Platform or volume service layer

Metrics may include:

- Read/write IOPS.
- Read/write throughput.
- Latency.
- Queue length or outstanding operations.
- Burst balance/credits if the volume type has a burst mechanism.
- Throttling or provisioned performance limits.
- Volume status and attach/detach events.

Volume metrics are typically measured at the storage service or virtualization path. They may not include all the time the application spends waiting on the filesystem, locks, or synchronous processing.

### Guest OS layer

On Linux:

~~~sh
iostat -xz 1
lsblk
df -hT
df -i
pidstat -d 1
~~~

Metrics to understand:

- Read/write throughput and operations/s.
- Await or average latency as defined by the tool.
- Queue depth.
- Device utilization.
- CPU I/O wait.
- Filesystem capacity and inodes.
- Process I/O bytes.

Device `%util` on certain NVMe or parallel devices cannot be interpreted simply as "100% means performance ceiling reached." Inspect latency, queue depth, IOPS, and the actual limits of the device.

On Windows, Performance Monitor can be used with counters such as Disk Reads/sec, Disk Writes/sec, Avg. Disk sec/Read, Avg. Disk sec/Write, and Current Disk Queue Length.

### Application layer

The application can measure:

- Database query latency.
- Transaction commit time.
- File read/write duration.
- Cache hit ratio.
- Log flush duration.
- Queue persistence latency.
- Number of retries or timeouts when accessing storage.

A volume with low latency alongside slow database queries may point to locks, query plans, connection pools, or application processing. Conversely, rising database query latency occurring together with rising volume queue depth and latency suggests a storage bottleneck.

### Cross-layer storage reading

| Platform/volume | Guest OS | Application | Investigation direction |
|---|---|---|---|
| IOPS hits limit | Queue and await increase | Query latency increases | Insufficient volume throughput/IOPS or exhausted burst |
| Low volume latency | Filesystem full or out of inodes | Upload failures | Capacity/inodes and permissions |
| Normal volume | High iowait on another device | Slow requests | Check swap, local disk, log disk, or another mount |
| Normal volume | Low disk I/O | Slow database | Locks, query plan, connection pool, CPU, or network |

## 6. Network: Virtual NIC, TCP Stack, and Requests

### Metrics at the platform layer

The platform can provide:

- Bytes and packets in/out.
- Packet drops or errors.
- Virtual NIC bandwidth.
- Network performance limits/throttling.
- Flow logs or network security events.
- Load balancer and interface status.

Some metrics only count traffic at the interface; they do not indicate whether the application has processed the request. Flow logs typically describe network flows and policies, and do not replace application latency metrics.

### Metrics in the guest OS

On Linux:

~~~sh
ip -s link
sar -n DEV 1
sar -n TCP,ETCP 1
ss -s
nstat
~~~

You can track:

- RX/TX bytes and packets.
- Interface errors and drops.
- TCP retransmissions.
- Connection resets.
- Listen queue overflows.
- Socket counts and connection states.
- DNS lookup time if measured by an agent or application.

On Windows, Performance Monitor can be used with Network Interface counters, TCPv4/TCPv6, and tools such as Get-NetAdapterStatistics.

### Metrics at the application layer

Useful metrics:

- Request rate.
- Connection establishment time.
- DNS resolution duration.
- TLS handshake duration.
- Time to first byte.
- Request duration.
- Upstream/dependency latency.
- Timeouts, retries, and status codes.

High network bytes do not necessarily mean an incident; it may be legitimate load. Compare against the baseline, work throughput, and errors/latency.

### Cross-layer network reading examples

If the cloud NIC shows no drops but Linux reports rising TCP retransmissions, the issue may lie further along the path beyond the interface or on the peer side. If Linux shows no retransmissions but the application times out, check DNS, TLS, connection pools, slow server processing, or overly short deadlines.

If bytes/sec reaches the machine type's network limit while latency and queues rise together, a machine type with higher bandwidth or traffic reduction may be needed. If only one endpoint is slow while other endpoints behave normally, investigate that specific dependency rather than resizing the NIC.

## 7. Application Metrics: RED, USE, and the Four Golden Signals

### RED for request-driven services

RED is a way of observing services through three groups:

- **Rate:** number of requests processed per unit of time.
- **Errors:** number or rate of failed requests.
- **Duration:** request processing time, usually expressed in percentiles.

Example metrics:

~~~text
http_server_requests_total
http_server_request_duration_seconds_bucket
http_server_request_duration_seconds_count
http_server_request_duration_seconds_sum
~~~

Exact metric names depend on instrumentation. With a Prometheus histogram, p95 can be calculated from buckets:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_server_request_duration_seconds_bucket[5m])
  )
)
~~~

Do not average the p95 values of multiple instances to produce a cluster-wide p95. Aggregate histogram buckets or distribution data properly instead.

### USE for resources

USE is a method for inspecting resources through:

- **Utilization:** the portion of the resource that is busy.
- **Saturation:** the amount of work waiting or queued.
- **Errors:** errors when using the resource.

Examples:
- CPU utilization, run queue, and throttling.
- Disk utilization, queue depth, and I/O errors.
- Network utilization, packet queues/drops.
- Connection pool utilization, waiters, and acquisition errors.

USE is helpful for CPU, disk, network, and pools. RED is helpful for request-handling services. Combining both connects resource usage to service impact.

### Four golden signals

Another approach is tracking latency, traffic, errors, and saturation. These signals help detect when a service is slow, traffic changes, errors rise, or resources saturate.

Do not monitor only HTTP 5xx statuses. A request can return 200 while producing a wrong business result or taking too long. Track domain metrics such as completed transactions, failed jobs, backlogged messages, and valid processing rate.

## 8. Why Can Metrics Across the Three Layers Differ?

Discrepancies usually stem from measurement boundaries rather than a broken telemetry system.

### Different scopes

- The hypervisor measures resources allocated or consumed on the host.
- The guest OS measures time and resources seen by the guest kernel.
- Process metrics measure CPU/RAM attributed to a single process.
- The application measures business duration, which may include waiting on the network or dependencies.

An application waiting 500 ms on a database may show near-zero CPU during that time, while the user still experiences a 500 ms request.

### Different sampling intervals and aggregations

The platform may sample every minute, the guest agent every 10 seconds, and Prometheus may scrape every 15 seconds. When the system experiences short bursts, charts can display different values.

In addition, one dashboard may show averages while another shows max or percentiles. Always check the aggregation period and statistic.

### Different definitions and units

For example:

- CPU usage may be percentage of vCPU, CPU time, or percentage of total logical processors.
- Memory usage may be resident, working set, committed, or host consumed.
- Disk latency may be latency at the volume service or I/O completion time in the guest.
- Network throughput may count interface bytes excluding overhead or dropped traffic.

Do not compare two metrics just because their names look similar. Read the metric definition and unit from the publishing source.

### Caching and buffering

The guest OS can write data into the page cache and complete the write operation for the application before flushing it to the volume. In that case, the application sees fast writes, while volume metrics appear later.

Similarly, reading data from cache can make the application fast even though the volume has few read IOPS.

### Virtualization and contention

The guest may see CPU idle or steal depending on how the hypervisor exposes it. The host may be experiencing resource contention, or the VM may be constrained by CPU credits or quotas. Guest and provider metrics should be read alongside platform events.

### Containers and cgroups

A container can be throttled on CPU/memory even when the node VM still has plenty of available resources. Low node CPU utilization does not prove a pod can use more CPU if its cgroup quota has already hit its limit.

## 9. Containers and Kubernetes: Adding Another Observation Layer

In container environments, distinguish between:

1. Hypervisor or cloud VM.
2. Node OS.
3. Container runtime and cgroups.
4. Pod/container.
5. Application.

A node metric does not represent a single pod. A pod can experience CPU throttling while the node still has idle CPU because the container's quota has reached its limit.

### Container CPU

Common metrics include:

- CPU usage over time.
- CPU requests and limits.
- CFS throttled periods and throttled time on Linux cgroup v1/v2.
- Run queue and node CPU pressure.

Inspect the throttling ratio alongside request latency. Low CPU usage with high throttling can result from short burst limits or how the metric is aggregated.

### Container memory

Distinguish between:

- Container memory usage.
- Working set.
- RSS/anonymous memory.
- File cache.
- Memory requests/limits.
- OOM events and restart count.

How an exporter computes working set may exclude part of the cache or non-reclaimable metrics depending on the implementation. Do not rely on a single container memory metric to conclude total RAM usage.

### Container storage and network

Pods may use ephemeral storage, PVCs, hostPath, or network file shares. Node disk metrics do not identify which pod causes the I/O without cgroup- or container-runtime-level metrics.

Network metrics can appear at the pod interface, node interface, CNI, and cloud NIC. Identify the measurement point to avoid double-counting traffic.

### Quick Kubernetes checks

~~~sh
kubectl top nodes
kubectl top pods -A
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -A --sort-by=.lastTimestamp
~~~

`kubectl top` depends on Metrics Server and does not replace a historical metrics system. Use Prometheus, cloud monitoring, or an equivalent platform to inspect trends, throttling, and percentiles.

## 10. Collecting Metrics and Unifying Telemetry

### Common data sources

| Source | Data | Example tools |
|---|---|---|
| Cloud monitoring | VM, volume, NIC, load balancer, quota, events | Amazon CloudWatch, Azure Monitor, Google Cloud Monitoring |
| Guest OS | CPU, RAM, disk, network, processes, services | Node Exporter, Windows Exporter, Telegraf, cloud agent |
| Application | Requests, business transactions, queues, runtime | Prometheus client, OpenTelemetry SDK, APM agent |
| Logs | Events and detailed per-request/process information | journald, Windows Event Log, Fluent Bit, cloud logging |
| Traces | Request paths across services and dependencies | OpenTelemetry, Jaeger, Tempo, APM backend |
| Events | Deploys, restarts, scaling, maintenance, failover | Cloud audit/event service, Kubernetes events, CI/CD |

### Agents, exporters, and collectors

Agents/exporters collect metrics from the operating system or application. The OpenTelemetry Collector can receive, process, enrich with resource attributes, and forward telemetry to backends.

A typical pipeline:

~~~mermaid
flowchart LR
    P["Cloud platform metrics"] --> C["Collector / ingestion"]
    G["OS exporter / agent"] --> C
    A["Application SDK"] --> C
    L["Logs and events"] --> C
    T["Traces"] --> C
    C --> M["Metrics backend"]
    C --> LG["Logs backend"]
    C --> TR["Trace backend"]
    M --> D["Dashboards and alerts"]
    LG --> D
    TR --> D
~~~

Not all data has to flow through the same collector. You can use the cloud provider's API for platform metrics and a separate agent for the guest OS. What matters is having identifying metadata that can correlate the sources.

### Consistent labeling

Maintain a shared set of resource attributes or labels:

- service.name.
- service.version.
- deployment.environment.
- cloud.provider.
- cloud.region.
- cloud.availability_zone.
- cloud.account.id or project ID per policy.
- host.id or instance ID.
- k8s.cluster.name, namespace, and pod if using Kubernetes.

Do not use hostname as the sole identifier if hostnames can collide or change. Use a stable instance ID or resource ID, while storing hostname as a human-readable attribute.

### Time synchronization

Skewed timestamps make correlating metrics, logs, and traces difficult. Synchronize clocks using NTP or an appropriate time synchronization service, and keep timezones consistent in storage and display.

When investigating, compare timestamps across:
- Cloud metrics.
- Guest OS metrics.
- Application logs/traces.
- Deployment events.
- VM restart or host maintenance events.

Pay attention to ingestion delay: the time an event occurs can differ from the time the data appears on a dashboard.

## 11. Building Dashboards Around Operational Questions

A good dashboard should answer specific questions rather than simply packing in as many charts as possible.

### Platform dashboard

Display per VM or VM group:

- CPU utilization and limits/credits if applicable.
- Platform memory metrics if available.
- Volume IOPS, throughput, latency, and throttling.
- NIC bytes, packets, drops.
- VM state, maintenance, and scaling events.
- Quotas/capacity where relevant.

### Operating system dashboard

Display:

- CPU user/system/idle/iowait/steal.
- Run queue and CPU throttling.
- RAM available, working set, swap, and page faults.
- Top processes by CPU/memory.
- Disk await, queue depth, throughput, and filesystem capacity.
- Network errors, retransmissions, and socket states.
- Service status and restarts.

### Application dashboard

Display:

- Request rate, errors, and p50/p95/p99 latency.
- Business throughput and success rate.
- Queue depth and wait time.
- Dependency latency and errors.
- Worker/thread pool saturation.
- Runtime heap, GC, cache, and connection pools.
- Deployment version and errors by version.

### Linked dashboards

A linked dashboard should share common filters for service, environment, region, instance ID, and time range. When selecting an instance or deployment, an operator can drill down from application latency to the guest OS and then to volume/NIC/platform metrics.

Do not combine metrics with different units or meanings on the same chart just for convenience. Instead, align panels along the same time axis and add annotations for deployments and maintenance.

## 12. Designing Impact-Based Alerts

Alerts should detect issues that require action rather than firing on every metric threshold crossing.

### Infrastructure alerts

Examples:

- Sustained CPU saturation accompanied by a growing run queue.
- CPU credits nearing exhaustion on burstable machines.
- Disk latency or queue depth exceeding baseline for a sufficient duration.
- Volume throttling or low burst balance.
- Filesystem/inodes nearly full.
- Rising network errors or packet drops.
- VM or volume transitioning to an unhealthy state.

### Application alerts

Examples:

- p95/p99 latency breaching the SLO.
- Rising error rate.
- Unusual throughput drop while traffic is still arriving.
- Continuously growing queue age or backlog.
- Saturated worker pool.
- Dependency timeouts or exhausted connection pools.

### Combining multiple conditions

A high CPU alert alone may simply represent valid load. An alert is more actionable when high CPU coincides with rising latency or missed throughput targets.

Example logic:

~~~text
IF cpu_utilization > 85% FOR 10 minutes
AND request_p95 > service_latency_slo
THEN alert = "Compute saturation affects service"
~~~

The 85% threshold is only an example. Tune thresholds based on workload, baseline, and SLOs.

### Missing data and alert fatigue

Missing metric data can happen because an exporter crashed, the network failed, the VM stopped, or the ingestion pipeline had an outage. Do not treat missing data as zero by default. Create separate alerts for stale telemetry or failed target scrapes.

Use evaluation durations, hysteresis, or cooldowns to prevent flapping alerts. Classify severity by impact and specify owners, runbooks, or next steps.

## 13. Diagnostic Workflow When Layers Report Differently

An investigation workflow can proceed in the following order:

1. Identify user symptoms: latency, errors, throughput, or slow jobs.
2. Select the exact service, instance, region, and time window.
3. Mark deployments, restarts, scaling, maintenance, and related events.
4. Inspect application metrics to pinpoint the affected endpoint or dependency.
5. Inspect the guest OS to locate CPU, memory, disk, network, or process bottlenecks.
6. Inspect platform metrics to identify throttling, quotas, volume limits, or host events.
7. Compare timestamps, units, aggregation periods, and labels across sources.
8. Formulate a testable hypothesis.
9. Test a small, scoped change or measurement.
10. Verify impact using before/after application and infrastructure metrics.

### Symptom matrix

| Application symptom | Guest OS | Platform | Hypothesis and next steps |
|---|---|---|---|
| Latency rises, throughput drops | High CPU, high run queue | vCPU near limit | Profile code, check parallelism, consider adding CPU |
| Latency rises | Low CPU, high iowait | Volume latency/queue rises | Check IOPS, throughput, burst, and I/O patterns |
| Latency rises | Low available RAM, rising swap | Fixed VM RAM or memory pressure | Check process RSS, leaks, heap, and working set |
| Latency rises | Steal or throttling rises | CPU credit/limit or scheduling event | Check machine type, quotas, and host/platform events |
| Request timeouts | Retransmissions rise | NIC drops or network limit | Check routes, security policies, NIC limits, and peers |
| Request timeouts | Normal CPU/RAM/Disk | Normal infrastructure | Check DNS, TLS, dependencies, queues, and connection pools |
| Only one pod is slow | Node has free resources, pod throttled | Normal VM | Check cgroup CPU limits, requests, and scheduler |
| Database is slow | Normal guest disk | Normal volume | Check locks, query plans, connection pools, and replication |

The matrix only provides initial hypotheses. Verify with logs, traces, profiles, and additional measurements before changing configuration.

## 14. Real-World Example: Slow API Despite Low Cloud CPU

An API service running on a VM has platform metrics showing 35% average CPU. Yet the application dashboard reports p95 latency jumping from 120 ms to 900 ms. Looking only at cloud CPU, the operations team might conclude the VM still has spare capacity.

Upon deeper inspection:

- The guest OS reports rising iowait during the same interval.
- `iostat` shows await and queue depth on the data device increasing.
- Volume metrics show throughput hit its provisioned limit during peak hours.
- Traces show time is spent primarily in database read operations.
- Request rate nearly doubled following a campaign.

The team identifies the bottleneck in the storage/database path. Adding vCPUs would likely not solve the issue. They inspect query plans, caching, I/O patterns, and volume limits, then test a more suitable storage configuration in staging. Results are evaluated via query latency, API p95, throughput, and cost per request.

This example shows how application metrics detect user impact, the guest OS isolates the resource, and platform metrics confirm the service limit.

## 15. Real-World Example: Low VM CPU While Workload Is Throttled

A pod running on a Kubernetes node has low average CPU usage. The node OS uses only about half of its CPU, yet the pod's endpoints suffer from high latency and unstable processing times.

Container metrics reveal:

- The pod's CPU limit is low.
- CFS throttled periods are increasing.
- At times, CPU usage hits its quota.
- The node still has idle CPU.

The root cause is the container's CPU limit, not a lack of CPU on the VM. The team reviews requests/limits, concurrency, and worker counts; then tests adjusting the quota and re-measures latency, throttling, and node utilization.

Simply upgrading the machine type would still leave the pod constrained by the old CPU limit. Quota must be checked at the exact layer where it is enforced.

## 16. Telemetry Data Quality and Observation Limits

### Scrape interval and retention

Scraping too infrequently can miss bursts; scraping too frequently increases agent, network, and backend load. Choose the interval based on detection goals and cost. Raw data can be kept for a short duration, then downsampled or aggregated for long-term trends.

### Histograms and percentiles

Latency typically has a skewed distribution. Averages can hide a subset of very slow requests. Use appropriate histograms or summaries to calculate p95/p99.

If using summaries that generate percentiles per instance, those percentiles cannot be accurately aggregated into a cluster-wide percentile. Histogram buckets can be aggregated before computing quantiles if the bucket schema is compatible.

### Counter resets

Counters can reset when a process restarts. When computing rates, use your query system's counter-reset-aware functions rather than taking a simple difference between two points when resets are possible.

### Missing and stale series

A metric may fail to appear because:
- The agent/exporter is not running.
- The target cannot be scraped.
- Labels or metric names changed after a deployment.
- The VM stopped or was replaced.
- The ingestion pipeline or backend quota encountered errors.
- The metric is only emitted when an event occurs.

Dashboards must distinguish between zero, null, and stale. Alerts must monitor telemetry health separately.

### Sampling and overhead

Tracing may sample a fraction of requests to reduce cost. Logs may be filtered or rate-limited. Metrics may be aggregated before sending. Therefore, not every request will have a detailed trace or log. Understand the sampling policy and keep aggregated metrics reliable enough to spot trends.

## 17. Workflow for Building Compute Workload Observability

1. **Define SLOs:** latency, availability, throughput, or job completion time.
2. **Inventory resources:** VMs, vCPUs, RAM, volumes, NICs, containers, processes, and dependencies.
3. **Select metrics per layer:** provider, guest OS, and application.
4. **Standardize identifiers:** instance ID, service, environment, region, and version.
5. **Configure time synchronization:** NTP/time service and consistent timestamps.
6. **Deploy collectors:** cloud APIs, OS exporters, application instrumentation, and log/trace agents.
7. **Verify units/semantics:** read definitions, sample intervals, and aggregations.
8. **Build question-driven dashboards:** user impact, resources, dependencies, and platform events.
9. **Define alerts:** tied to SLOs, saturation, and telemetry health.
10. **Write runbooks:** describe how to correlate all three layers and verification steps.
11. **Test failure scenarios:** CPU saturation, memory pressure, disk throttling, packet loss, and exporter failures.
12. **Optimize cost:** reduce label cardinality, unnecessary scrapes, and overly long retention.

### Acceptance criteria

A compute observability system can be considered sufficiently foundational when:

- Platform metrics exist for VMs, disks, and NICs as appropriate.
- Guest OS metrics exist for CPU, memory, storage, and network.
- Application metrics exist for requests, errors, latency, and workload queues.
- Sources can be correlated by instance/service/time.
- Dashboards clearly display units and aggregations.
- Alerts distinguish workload incidents from telemetry failures.
- Runbooks exist for investigating mismatches across the three layers.
- Cardinality, retention, and cost are reviewed.

## 18. Metric Reading and Correlation Checklist

- [ ] Identified whether the metric comes from the hypervisor/cloud, guest OS, or application.
- [ ] Read the metric's definition, unit, and scope.
- [ ] Identified whether the metric is a gauge, counter, or histogram.
- [ ] Checked the sample interval and aggregation method.
- [ ] Filtered by the same instance ID, region, service, and time range.
- [ ] Synchronized timestamps or accounted for ingestion delay.
- [ ] Reviewed CPU together with run queue, steal/throttling, and application latency.
- [ ] Reviewed memory together with available, working set, swap, OOM, and runtime heap.
- [ ] Reviewed storage together with IOPS, throughput, queue depth, filesystem, and query latency.
- [ ] Reviewed network together with bytes, drops, retransmissions, DNS/TLS, and request timeouts.
- [ ] Checked container quotas/cgroups when the node still has free resources.
- [ ] Aggregated percentiles properly from histograms.
- [ ] Distinguished missing data from zero values.
- [ ] Included deployment and platform events on dashboards for correlation.
- [ ] Tied alerts to SLOs or saturation with runbooks attached.
- [ ] Ensured labels do not cause excessive cardinality.
- [ ] Monitored telemetry agents and backends as part of the system.

## Conclusion

Metrics from the hypervisor/platform, guest OS, and application describe different parts of the same workload. The platform reveals limits and the state of virtualized resources; the operating system shows how CPU, RAM, disk, network, and processes are behaving; the application shows how requests and business operations are impacted. To diagnose accurately, read definitions and units, align timestamps, correlate by instance/service, and compare the layers using the same symptom. Combining RED for services, USE for resources, platform metrics, and traces/logs helps pinpoint bottlenecks with evidence, design SLO-driven alerts, and avoid resizing the wrong component.
