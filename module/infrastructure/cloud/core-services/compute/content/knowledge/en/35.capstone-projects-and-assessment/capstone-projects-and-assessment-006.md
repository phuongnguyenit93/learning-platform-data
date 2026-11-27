# Investigating Compute Incidents Using Logs, Metrics, and OS Signals

When a compute workload slows down, stops responding, or terminates abruptly, the root cause may lie in the application, operating system, container runtime, virtual machine, cloud infrastructure, or an external dependency. A high CPU chart merely indicates busy processing; it does not prove CPU is the root cause. A timeout log alone does not tell you whether a request stalled in the application, network, storage, or target service.

Investigating compute incidents requires combining three categories of evidence: logs reveal events and sequence of occurrence; metrics reveal trends and anomaly magnitude; and OS signals reveal how processes, memory, I/O, schedulers, network stacks, and the kernel are behaving. By correlating these sources over the same time window, instance, process, container, request, and deployment version, operations teams can move from guesswork to testable hypotheses.

This lesson outlines a structured investigation workflow for VMs, containers, Kubernetes, and serverless workloads. It spans impact scoping, timeline construction, evidence collection, metric interpretation, OS signal analysis, infrastructure change inspection, recovery verification, and post-incident reporting. After this lesson, you will be able to:

- Classify compute incidents across CPU, memory, disk/I/O, network, process, kernel, and capacity.
- Correlate logs, metrics, events, and OS telemetry into a unified timeline.
- Use Linux and Windows inspection commands to pinpoint abnormal processes or resources.
- Distinguish CPU saturation, throttling, memory pressure, OOM, I/O wait, and network failures.
- Investigate incidents across VMs, containers, Kubernetes, and serverless at the proper ownership layer.
- Formulate hypotheses, validate them with evidence, and choose safe mitigations.
- Preserve forensic data and avoid actions that destroy evidence or widen blast radius.
- Verify service recovery, monitor for recurrence, and write a root cause analysis report.

## 1. Investigation Goals and Principles

The primary goal of incident response is restoring service within acceptable risk limits. Finding the root cause is the next priority, but necessary mitigation should not be delayed while users are impacted. At the same time, actions like rebooting, deleting Pods, rotating logs, or scaling in can destroy vital evidence.

### Distinguishing Symptoms, Direct Causes, and Root Causes

- **Symptom:** API returns 503, VM is unreachable via SSH, container restarts continuously, or a job misses its deadline.
- **Direct cause:** process killed by OOM, filesystem out of space, CPU throttled, or connection pool exhausted.
- **Root cause:** memory leak, misconfigured requests/limits, unbounded log growth, a rollout changing concurrency, or autoscaler lacking capacity.
- **Contributing factors:** missing alerts, low quotas, slow dependencies, unbalanced node placement, or outdated runbooks.

An incident can involve multiple interacting causes. For instance, a slow database causes requests to hold connections longer; in-app queues back up; memory grows; finally the process hits OOM. Fixing memory alone without examining the dependency may lead to recurrence.

### Working Principles

1. Determine impact and scope before modifying the system.
2. Record timestamps, timezones, resource IDs, and workload versions.
3. Gather evidence across multiple layers, prioritizing timestamped sources.
4. Compare against baselines and healthy peer workloads.
5. State explicit hypotheses listing both supporting and refuting evidence.
6. Apply one controlled mitigation and measure the outcome.
7. Verify SLOs and dependencies after recovery.
8. Document decisions, impact, owners, and follow-up actions.

~~~mermaid
flowchart TD
    A["Alert fired / incident reported"] --> B["Determine impact and scope"]
    B --> C["Record timeline, resource IDs, deployments"]
    C --> D["Collect logs + metrics + OS signals"]
    D --> E["Formulate hypothesis"]
    E --> F{"Verifiable evidence?"}
    F -- "No" --> D
    F -- "Yes" --> G["Select controlled mitigation"]
    G --> H["Re-measure SLOs and health"]
    H --> I{"Stabilized?"}
    I -- "No" --> D
    I -- "Yes" --> J["Monitor, RCA, and action items"]
~~~

## 2. Assessing Impact and Scope

Before opening a terminal, know who and which resources are affected. This prevents debugging a single node when the actual problem spans an entire region or a shared dependency.

### Opening Questions

- Which services are affected? APIs, workers, batch jobs, database proxies, or the control plane?
- When did it start? Were there recent deployments, config changes, scaling events, or maintenance?
- Is impact global or isolated to specific tenants, regions, zones, node pools, or instance types?
- Are requests failing, timing out, experiencing higher latency, or dropping throughput?
- Which Pods/VMs/processes are affected? Is there a pattern by host, image, instance family, or zone?
- Is there data loss, duplicate jobs, request retries, or growing backlog?
- Is the incident ongoing or self-recovered?

### Scoping by Layer

| Layer | Objects to Inspect | Scope Indicators |
|---|---|---|
| Application | Endpoints, workers, processes, thread pools | Single route or single version failing |
| Container | Container IDs, Pods, restart counts | Pods on a specific node or image |
| Node/VM | Instance IDs, hostnames, kernel | Multiple workloads on the same host |
| Cluster | Node pools, scheduler, control plane | Pending Pods or multiple NotReady nodes |
| Network | Subnets, routes, firewalls, DNS, endpoints | One zone or destination failing |
| Storage | Volumes, filesystems, object stores | Workloads sharing a mount or storage backend |
| Region/provider | Regions, zones, quotas, managed services | Multiple apps or accounts impacted simultaneously |

### Assessing Severity

Severity should reflect real impact, not just alert counts:

- Number of impacted users or tenants.
- Error rate and degree of SLO breach.
- Risk of data loss or corruption.
- Potential security impact or unauthorized access.
- Availability of workarounds or alternate serving regions.
- Backlog growth rate and runway before capacity exhaustion.

If signs indicate intrusion, data exfiltration, or unauthorized permission changes, trigger the appropriate security incident process in parallel with the compute investigation.

## 3. Building a Timeline and Synchronizing Clocks

Logs and metrics can only be correlated reliably when timestamps are standardized. A host with a few minutes of clock skew can invert event order, especially across distributed requests.

### Recording Milestones

At minimum, record:

- First alert timestamp.
- When users first reported errors.
- Sample request IDs or trace IDs.
- Deployment, restart, scaling, patching, or configuration change times.
- When metrics first diverged from baseline.
- Mitigation timestamp and service recovery timestamp.

Prefer storing UTC timestamps while preserving original timezones if log sources are unnormalized. Note each source's time resolution: millisecond logs, 1-minute metric intervals, event ingestion time versus processing time.

### Checking Clocks on Linux

~~~bash
date -u
timedatectl status
chronyc tracking
~~~

If the system uses `chrony`, `chronyc tracking` displays sync status and clock offset. Time-sync service names vary by distribution. Never alter NTP configuration mid-incident without authorization and a plan.

### Checking Clocks on Windows

~~~powershell
Get-Date -Format 'yyyy-MM-ddTHH:mm:ss.fffK'
w32tm /query /status
~~~

`Get-Date -Format o` outputs local time with UTC offset in ISO 8601 format; record the timezone explicitly when placing entries onto a shared timeline.

### Correlation IDs

Request IDs, trace IDs, job IDs, Pod UIDs, container IDs, and instance IDs tie logs together across components. Avoid relying solely on generic service names when multiple replicas exist. For async workloads, propagate correlation IDs through queues and workers to trace from initial request to final job.

## 4. Collecting Evidence Before Making Changes

Remediation actions can erase clues: rebooting wipes process state and kernel ring buffers; deleting Pods destroys ephemeral filesystems; rotating logs may drop unshipped entries; scaling in removes nodes holding forensic state.

### Minimum Evidence Pack

- Incident ID, commander, and start timestamp.
- Account/project/subscription, region, zone, and resource IDs.
- Hostname, OS version, kernel version, instance type.
- Application version, image digest, config version.
- Process ID, container ID, Pod UID, or function invocation ID.
- Relevant logs and query time windows.
- Raw metrics or dashboard snapshots.
- Cloud provider, scheduler, and OS events.
- Commands run, execution timestamps, and relevant outputs.
- Changes applied and approving authority.

### Preserving Data

1. Export logs and events for the relevant time window.
2. Record exact queries, filters, and data sources.
3. Capture metric snapshots or save reproducible queries.
4. Save command outputs alongside hostname and timestamp.
5. If memory dumps or packet captures are required, follow security and privacy procedures.
6. Protect evidence with restricted access and proper retention.
7. Never include secrets, tokens, or personal data in incident reports.

### Safe Inspection Commands vs. Risky Actions

Read-only inspection commands such as `top`, `free`, `df`, `journalctl`, `kubectl describe`, or `Get-WinEvent` are generally safe initial steps. Commands that kill processes, reboot, truncate logs, delete files, flush firewalls, or modify routes can disrupt service and destroy evidence. Run mutating actions only with impact assessment, an accountable owner, and a rollback plan.

## 5. Log Sources to Collect

No single log source captures an entire compute incident. Combine application, OS, runtime, orchestration, and cloud control plane logs.

| Source | Useful Contents | Investigation Question |
|---|---|---|
| Application logs | Errors, timeouts, exceptions, request IDs | Which code path is failing? |
| System logs | Service start/stop, daemons, drivers, filesystems | Did OS or services change? |
| Kernel logs | OOM, device resets, filesystems, network drivers | What events did the kernel record? |
| Container runtime | Image pulls, create/start/stop, runtime errors | Did the container start or get killed? |
| Kubernetes events | Scheduling, probes, evictions, volume mounts | Why was the Pod affected? |
| Cloud activity/audit | Create/update/stop, IAM, networking, quotas | Were there control plane changes? |
| Load balancer/API gateway | 4xx/5xx, target health, backend latency | Did requests reach the backend? |
| Network flow/firewall | Accept/deny, bytes, connections | Which flows are blocked or anomalous? |
| Storage service | Latency, throttling, capacity, errors | Is storage bottlenecked? |
| Scheduler/job logs | Queues, allocations, exit codes, retries | Did jobs stall or fail at a specific step? |

### Linux Logs

Common commands:

~~~bash
journalctl -u my-service --since "2026-11-22 10:00:00 UTC" --until "2026-11-22 10:30:00 UTC"
journalctl -p warning..alert --since "1 hour ago"
journalctl -k --since "1 hour ago"
~~~

On systems using `rsyslog` or `syslog-ng`, inspect files under `/var/log`. Exact filenames depend on distribution and configuration; never assume every Linux system uses identical paths.

### Windows Logs

~~~powershell
Get-WinEvent -FilterHashtable @{
  LogName = 'System'
  StartTime = (Get-Date).AddHours(-2)
} | Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message
~~~

Application, System, and service/driver event channels provide distinct evidence. Interpret Event IDs in context of the provider and Windows version rather than by ID number alone.

### Structured Logs

Structured logs should include timestamp, severity, service, version, environment, instance/pod identity, request ID, operation, duration, and error class. Filter by dedicated fields rather than parsing inconsistent message strings.

Never log passwords, access tokens, private keys, session cookies, or sensitive payloads. Use approved identifiers and redaction for correlation.

## 6. Reading Metrics: From Symptoms to Hypotheses

Metrics reveal changes over time. Compare the incident window against prior baselines, equivalent times of day, or comparable workloads. 80% CPU may be normal for a batch worker yet anomalous for an API that normally runs at 20%.

### Golden Signals

For request-driven services, four signal groups are standard:

- **Latency:** time taken to serve requests.
- **Traffic:** request rate or work volume.
- **Errors:** error rates, timeouts, retries, and status codes.
- **Saturation:** how close resources or queues are to capacity limits.

For compute hosts, add CPU, memory, disk, network, processes, file descriptors, and kernel events.

### Metrics to Compare

| Group | Metrics | Interpretation |
|---|---|---|
| CPU | Utilization, load average, run queue, throttling, steal | CPU busy, waiting for CPU, or hypervisor stealing time |
| Memory | Used/available, working set, page faults, swap, OOM | RAM pressure, reclamation, or memory exhaustion |
| Disk | Read/write latency, IOPS, throughput, queue depth, utilization | Slow storage or hitting limits |
| Filesystem | Free bytes, inode usage, growth rate | Out of space or inodes |
| Network | Throughput, packet loss, retransmits, connection counts | Congestion, packet drops, or connection exhaustion |
| Process | CPU, RSS, thread count, open files, restarts | Specific process behaving abnormally |
| Container | CPU/memory usage, throttling, OOM, restarts | Limit or cgroup pressure |
| Platform | Node health, quotas, capacity, provider events | Infrastructure issues or service limits |
| Application | Queue age, pool usage, p95/p99, error rates | Logic or dependency bottlenecks |

### Rates, Averages, and Percentiles

Averages conceal slow outliers. Use p50/p95/p99 and histograms to evaluate latency. For monotonic counters like network bytes or CPU time, examine per-second rates/deltas rather than cumulative totals.

When comparing metrics:

- Keep units and aggregation windows consistent.
- Verify whether metrics are host-level or container-level.
- Check sampling intervals and missing data points.
- Distinguish brief spikes from sustained conditions.
- Watch label cardinality and filters to avoid accidentally aggregating multiple instances.

## 7. Investigating CPU: Saturation, Throttling, and Steal

High CPU has many causes: traffic spikes, infinite loops, GC churn, retry storms, thread contention, concurrent batch jobs, or noisy neighbors.

### Signals on Linux

~~~bash
uptime
top -H
ps -eo pid,ppid,comm,%cpu,%mem,stat,etime --sort=-%cpu | head -20
mpstat -P ALL 1 5
pidstat -u 1 5
vmstat 1 5
~~~

Interpretation:

- Sustained load averages above available CPU cores can indicate runnable queues or tasks waiting on I/O; load average is not solely CPU utilization.
- `top -H` displays individual threads to spot single-thread CPU hogs.
- `mpstat` reveals busy or imbalanced cores.
- `pidstat` ties CPU usage to specific PIDs.
- `vmstat` shows runnable processes, blocked processes, and CPU breakdown.

Linux CPU outputs typically report `user`, `system`, `idle`, `iowait`, `irq`, `softirq`, and `steal`. Significant `steal` on a VM indicates the hypervisor is not scheduling as much CPU time as the guest requests; cross-check platform metrics and instance types.

### CPU Throttling in Containers

Containers with CPU limits can be throttled even when the underlying node has idle CPU. Inspect cgroup metrics or container monitoring:

- CPU usage.
- CPU quota/period.
- Throttled periods.
- Throttled time.
- CPU requests versus limits.

If throttling rises alongside p99 latency, review CPU limits, requests, concurrency, or hot code paths. Adding replicas sometimes masks the symptom while inflating costs.

### Signals on Windows

~~~powershell
Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 5
Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name, Id, CPU, WorkingSet64
Get-Counter '\System\Processor Queue Length' -SampleInterval 2 -MaxSamples 5
~~~

Counter names may be localized or vary by Windows version. Use Performance Monitor to verify available counters.

### Common CPU Hypotheses

| Signal | Hypothesis | Evidence to Look For |
|---|---|---|
| CPU and traffic rise together | Legitimate load growth | Request rate, queues, replica count |
| High CPU, flat traffic | Regression or loop | Profiles, deployment diffs, hot stacks |
| High CPU and rising GC | Allocation pressure | GC pauses, allocation rate, heap |
| Low host CPU, high container latency | Throttling or lock contention | cgroup throttling, thread dumps |
| Rising steal on certain VMs | Host contention | Cloud metrics, instance placement, provider events |
| One core at 100%, others idle | Single-thread bottleneck | Thread profiles, locks, serialized sections |

## 8. Investigating Memory: Pressure, Swap, and OOM

Memory pressure can trigger reclamation, swapping, latency spikes, OOM kills, or container restarts. Distinguish host memory from process/container memory.

### Linux Signals

~~~bash
free -h
cat /proc/meminfo
vmstat 1 5
ps -eo pid,comm,rss,vsz,%mem --sort=-rss | head -20
journalctl -k --since "2 hours ago" | grep -i -E 'oom|out of memory|killed process'
~~~

Key indicators:

- `MemAvailable` is usually more informative than `MemFree` because the kernel uses RAM for reclaimable page cache.
- RSS estimates resident memory for a process; it is not strictly exclusive memory due to shared pages.
- Sustained swap-in/swap-out activity degrades latency.
- Major page faults force processes to wait for storage reads.
- OOM logs identify killed processes, cgroups, and memory constraints.

### Host OOM vs. Container OOM

Host OOM occurs when the kernel cannot satisfy memory allocations system-wide. Container OOM happens when a cgroup memory limit is exceeded even if the host still has free RAM. In Kubernetes, an OOM-killed container shows `OOMKilled` as its last termination reason and the Pod may restart.

Check:

- Host memory pressure and kernel OOM messages.
- Container working set, RSS, and memory limits.
- Pod status, `lastState`, restart count, and events.
- Memory requests/limits, QoS class, and eviction events.
- Application heap/GC, caches, buffers, and memory leaks.

Do not immediately raise limits if nodes lack allocatable memory. Raising limits can cause co-located Pods to contend and trigger host-level OOMs.

### Windows Signals

~~~powershell
Get-Counter '\Memory\Available MBytes' -SampleInterval 2 -MaxSamples 5
Get-Counter '\Memory\Pages/sec' -SampleInterval 2 -MaxSamples 5
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Name, Id, WorkingSet64, PrivateMemorySize64
~~~

`Pages/sec` reflects paging activity but does not prove RAM exhaustion alone; inspect alongside `Available MBytes`, hard faults, disk activity, and application metrics.

### Investigating Memory Leaks

Compare memory trends over time under equivalent load. If RSS/working set grows monotonically across cycles and fails to drop after workload bursts subside, suspect a leak or unbounded cache. Collect heap profiles or dumps per procedure, weighing sensitive data exposure and pause overhead.

## 9. Investigating Disk, Filesystem, and I/O

Slow or full storage can hang processes, crash databases, block container logging, or flip nodes to `NotReady`. Inspect both capacity and latency.

### Linux

~~~bash
df -hT
df -i
lsblk -f
findmnt
iostat -xz 1 5
pidstat -d 1 5
~~~

Meaning:

- `df -hT`: used capacity and filesystem type.
- `df -i`: inode utilization.
- `lsblk`/`findmnt`: block devices and mount points.
- `iostat -xz`: device utilization, queue depth, and latency where supported.
- `pidstat -d`: processes performing significant read/write I/O.

If `df` reports full disk while `du` finds no large files, files may have been unlinked from directories while a process still holds open file descriptors. Run `lsof +L1` to find open deleted files; close or restart the holding process only per plan because doing so can disrupt service.

~~~bash
lsof +L1
du -xhd1 /var 2>/dev/null | sort -h
~~~

### Windows

~~~powershell
Get-Volume | Select-Object DriveLetter, FileSystem, Size, SizeRemaining
Get-PhysicalDisk | Select-Object FriendlyName, HealthStatus, OperationalStatus
Get-Counter '\PhysicalDisk(_Total)\Avg. Disk sec/Read' -SampleInterval 2 -MaxSamples 5
Get-Counter '\PhysicalDisk(_Total)\Avg. Disk sec/Write' -SampleInterval 2 -MaxSamples 5
~~~

### Distinguishing Capacity from Performance

- Low free space with normal latency: approaching capacity exhaustion.
- Ample free space with rising write latency: storage backend, queuing, or burst credits may be throttled.
- High IOPS with rising latency: workload may exceed provisioned IOPS.
- Full inodes with free bytes remaining: creating new files fails.
- Read-only filesystem: inspect kernel logs, device errors, and mount state.

Never delete logs or data haphazardly to free space. Identify file owners, retention policies, and recoverability before cleaning up.

## 10. Investigating Network and Connections

Network issues manifest as request timeouts, DNS failures, connection resets, retransmissions, packet loss, or reduced throughput. A workload with low CPU and plenty of memory can still appear hung while waiting on the network.

### Linux

~~~bash
ip -s link
ss -s
ss -tanp
ip route
resolvectl status
sar -n DEV,TCP,ETCP 1 5
~~~

Indicators:

- Rising RX/TX errors or drops on network interfaces.
- Rising TCP retransmissions and resets.
- Unusual spikes in sockets stuck in `SYN-SENT`, `TIME-WAIT`, or `CLOSE-WAIT`.
- Connection counts hitting file descriptor or connection pool limits.
- DNS resolver timeouts or unexpected address answers.
- Incorrect routes or MTU mismatches after network changes.

### Windows

~~~powershell
Get-NetAdapterStatistics
Get-NetTCPConnection | Group-Object State | Select-Object Name, Count
Get-DnsClientServerAddress
Test-NetConnection example.internal -Port 443
~~~

`Test-NetConnection` tests connectivity from one host at a single point in time; it does not prove every client or network path works.

### Layer-by-Layer Verification

1. Does DNS resolve to the expected IP?
2. Do routes and subnets have a valid path to the destination?
3. Are security groups, firewalls, NACLs, or host firewalls blocking traffic?
4. Does the TCP handshake succeed?
5. Do the TLS handshake and certificate validate?
6. Is the backend accepting connections with remaining capacity?
7. Does the application have sufficient pools/workers to process requests?

When packet captures are needed, restrict interface, host, port, and duration. Captures may include sensitive payloads; require authorization, encryption, and bounded retention.

## 11. Processes, Threads, File Descriptors, and Kernel Signals

A process can remain alive while making zero progress due to deadlocks, blocked I/O, exhausted thread pools, or exhausted file descriptors. Checking process states distinguishes CPU saturation from waiting processes.

### Process States on Linux

~~~bash
ps -eo pid,ppid,stat,wchan:24,etime,comm --sort=stat | head -40
ps -L -p <PID> -o pid,tid,stat,pcpu,comm
cat /proc/<PID>/status
ls /proc/<PID>/fd | wc -l
ulimit -n
~~~

Common states:

- `R`: running or runnable.
- `S`: interruptible sleep.
- `D`: uninterruptible sleep, typically waiting on I/O or kernel operations.
- `Z`: zombie, exited process not yet reaped by its parent.
- `T`: stopped or traced.

Many processes stuck in `D` state against the same mount or volume point to I/O or kernel waits. Open file descriptors nearing `ulimit -n` cause socket/file open failures. Runtime thread dumps reveal lock contention, deadlocks, or pool starvation.

### Kernel and Drivers

Kernel logs can record:

- OOM killer invocations.
- Disk I/O errors or filesystems remounted read-only.
- NIC resets, link-down events, queue timeouts.
- GPU/accelerator driver resets or lost devices.
- Kernel panics, soft lockups, hung tasks.
- cgroup memory/CPU pressure.

Do not draw conclusions from a single isolated log line. Correlate timestamps with metrics and workload versions, and check whether events recur against the affected resource.

### Windows Processes and Services

~~~powershell
Get-Process | Sort-Object CPU -Descending | Select-Object -First 20 Name, Id, CPU, WorkingSet64
Get-Service | Where-Object Status -ne 'Running'
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddHours(-1)}
~~~

Inspect service recovery actions, Windows Service Control Manager events, driver events, and application-specific channels. A stopped service may be the consequence of a crash or dependency failure rather than the root cause.

## 12. Investigating Containers and Cgroups

Containers share the host kernel while using namespaces and cgroups to isolate processes, networking, and resources. Host-level metrics may look healthy while a single container is hitting its limit.

### Inspecting Docker

~~~bash
docker ps -a
docker inspect <container-id>
docker stats --no-stream
docker logs --since 1h <container-id>
docker events --since 1h
~~~

Check:

- Exit code and `OOMKilled` flag.
- Restart policy and restart timestamps.
- CPU/memory limits and actual usage.
- Mounts, network mode, and environment/config version.
- Image digest and pull timestamp.
- Runtime events such as `die`, `oom`, `kill`, and `restart`.

### Cgroup Signals

On cgroup v2, cgroup files expose:

- `cpu.stat`: usage and throttling statistics.
- `memory.current`: current memory consumption.
- `memory.max`: memory ceiling.
- `memory.events`: counts of `high`/`max`/`oom`/`oom_kill`.
- `io.stat`: per-device I/O statistics.
- `cpu.pressure`, `memory.pressure`, `io.pressure`: pressure stall information if enabled in the kernel.

Exact cgroup paths depend on the runtime and mount layout. Be careful not to read the host cgroup instead of the container's cgroup.

### Pressure Stall Information (PSI)

PSI measures how long tasks are stalled waiting for CPU, memory, or I/O. It catches contention even when average utilization sits below 100%. Inspect `/proc/pressure/cpu`, `/proc/pressure/memory`, and `/proc/pressure/io` if supported by the kernel.

PSI is a supplemental signal; correlate it with application latency and cgroup metrics to determine which workload is impacted.

## 13. Investigating Kubernetes Workloads

Kubernetes adds scheduler, kubelet, controllers, CNI, CSI, and admission layers. When a Pod fails, determine whether the issue lies in the application, node, placement, volume, network, or control plane.

### Basic Inspection Commands

~~~bash
kubectl get pods -A -o wide
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --all-containers --since=1h
kubectl logs <pod-name> -n <namespace> --previous
kubectl get events -n <namespace> --sort-by=.lastTimestamp
kubectl describe node <node-name>
kubectl top nodes
kubectl top pods -A
~~~

### Pod States and Events

| Signal | Possible Meaning | Next Evidence to Check |
|---|---|---|
| Pending | Unschedulable or volume not attached | Events, requests, affinity, taints, quotas |
| ImagePullBackOff | Image pull failed | Registry auth, tag/digest, network, rate limits |
| CrashLoopBackOff | Container exits repeatedly | Previous logs, exit codes, probes, OOM |
| OOMKilled | Container exceeded memory limit or hit OOM | Last state, cgroup, memory usage, kernel logs |
| Evicted | Kubelet evicted due to node pressure | Node conditions, ephemeral storage, memory/disk |
| NotReady node | Kubelet/runtime/network/host issue | Node conditions, kubelet logs, provider events |
| Prolonged ContainerCreating | Mount, CNI, image pull, or runtime stall | Events, CSI/CNI logs, node status |

### Probe Failures

Readiness failures remove Pods from Service endpoints; liveness failures trigger container restarts. Startup probes protect slow-booting applications. If probes are overly aggressive or health endpoints depend on a slow database, all Pods may restart concurrently while the system is already overloaded.

Inspect probe events and startup duration. Avoid blindly raising `failureThreshold` just to mask a real bug; check what the health endpoint measures and whether it should depend on downstream services.

### Node Pressure and Eviction

Kubelet sets `MemoryPressure`, `DiskPressure`, or `PIDPressure` conditions. Pods can be evicted when nodes run low on resources. Inspect allocatable capacity, requests, limits, ephemeral storage, image filesystems, and log growth.

### Control Plane and Scheduler

If many Pods are `Pending` across multiple nodes, check scheduler events, API server availability, quotas, admission webhooks, and the node autoscaler. If only one node is affected, prioritize inspecting that node's kubelet, container runtime, disk, and networking.

## 14. Investigating VMs and Cloud Provider Events

The guest OS sees only part of the picture. The cloud control plane logs stop/start operations, host maintenance, instance health checks, volume detaches, quota failures, or network changes that guest logs cannot fully explain.

### Combining Guest and Provider Evidence

| Source | What to Check |
|---|---|
| Guest OS | CPU, memory, kernel, disk, networking, services |
| VM/instance metrics | CPU credits, burst balance, network/disk throughput, status checks |
| Activity/audit logs | Start/stop/reboot, resize, attach/detach, policy/config updates |
| Provider health/events | Maintenance, host issues, zone/region incidents |
| Volume metrics | Latency, IOPS, throughput, queue depth, burst credits |
| Network service | Flow logs, routes, firewalls, load balancer health |
| Quotas/capacity | Instance quotas, IPs, disks, accelerator availability |

### Example: CPU Credits or Burst Limits

Some instance families use CPU burst or credit models. When credits run out, CPU performance is throttled even though utilization graphs behave differently from fixed-performance instances. Check credit/baseline metrics specific to the instance type.

Similarly, storage volumes and network interfaces can have burst balances. When burst credits deplete, latency/throughput shifts even while guest CPU stays low.

### Instance Health Checks

Distinguish system/host checks from instance/guest checks where the provider exposes both. Failed host checks point to underlying infrastructure issues; failed guest checks point to an unresponsive OS, network misconfiguration, or resource exhaustion. Base recovery actions on the failure type and service policy.

## 15. Investigating Serverless and Managed Compute

Serverless platforms do not grant direct host OS access in most cases. Investigations rely on invocation metrics, runtime logs, platform events, and dependency telemetry.

### Signals to Inspect

- Invocation count, successes, errors, and throttles.
- Execution duration and timeouts.
- Concurrent executions and concurrency limits.
- Cold start/init duration.
- Configured memory versus actual memory usage if reported by the runtime.
- CPU architecture and runtime version.
- Queue age, retries, DLQ counts, and event source lag.
- Downstream latency, connection errors, and quotas.

### Common Patterns

| Symptom | Hypothesis | Evidence |
|---|---|---|
| Rising duration | Slow dependency or large input payload | Traces, downstream latency, payload size |
| Throttling | Concurrency/quota or account limit | Throttle metrics, concurrency settings |
| Timeouts | Long code path, network stall, or cold start | Phase timings, init duration, dependencies |
| Memory error | Allocation exceeded configured limit | Max memory used, runtime errors, payload size |
| Rising retries | Function errors or wrong ack/visibility config | Invocation logs, queue metrics, DLQ |
| Rising cold starts | Scale-out, large deployment package, slow init | Init duration, package size, runtime |

### Lack of Host Metrics Does Not Prevent Investigation

Instrument per-phase timing inside functions and log correlation IDs, model/version, non-sensitive input sizes, and dependency latencies. For queue-triggered functions, track message age and retries to distinguish slow processing from poison messages.

## 16. Correlating Logs, Metrics, and Traces

Three telemetry pillars complement one another:

- Logs capture discrete events, errors, and context.
- Metrics show trends, rates, and saturation levels.
- Traces show which services/spans a request traversed and time spent per step.

### Correlation Workflow

1. Pick a failing request/job with its timestamp and ID.
2. Locate the corresponding trace and identify the slowest span.
3. Query logs by trace ID, request ID, or job ID.
4. Cross-reference service, Pod, node, and dependency metrics over the same window.
5. Compare against a successful request hitting the same endpoint/input size.
6. Pinpoint when the anomaly first started—not just when the alert fired.

### Example

API p99 jumps from 200 ms to 4 seconds. Traces show the object storage span taking 3.5 seconds. Application logs show no CPU errors; node metrics look normal, yet storage read latency jumped on the same volume. The reasonable hypothesis is a storage bottleneck rather than API CPU. Inspect storage queues, IOPS, throttling, volume events, and recent changes.

## 17. Formulating and Testing Hypotheses

A good hypothesis must be falsifiable. Avoid vague claims like "the cloud is slow" or "the box lacks resources."

Hypothesis template:

> Starting at time T, workload X experienced rising p99 because resource Y became constrained; expected evidence is metric M rising and log/event E appearing on the exact impacted instance/Pod. If M did not change or healthy peer workloads on the same host are unaffected, revise the hypothesis.

### Hypothesis Matrix

| Hypothesis | Supporting Evidence | Refuting Evidence / Checks |
|---|---|---|
| CPU saturation | Run queue, CPU usage, and latency rise together | Idle cores, processes waiting on I/O, zero throttling |
| CPU throttling | cgroup throttled time increases | No CPU limit set or throttling counter is zero |
| Memory pressure | Low available RAM, rising swap/PSI/OOM | Stable memory, zero reclaim or OOM events |
| Disk bottleneck | Rising I/O latency/queue, processes in D state | Normal disk latency, errors located in network |
| Network issue | Retransmits, timeouts, DNS, or flow denies | Clean TCP, slow processing downstream |
| Dependency outage | Multiple callers failing against the same destination | Only one host/process failing |
| Bad deployment | Errors start right after a version/config change | Old and new versions fail identically at the same time |
| Provider event | Health/maintenance event aligns with timeline | No events; host metrics and peers unaffected |

### Controlled Experiments

If possible, test on a canary or a single replica:

- Shift a slice of traffic back to the prior version.
- Reduce concurrency to observe queue/latency response.
- Run the same workload on a known-healthy node.
- Pause competing batch jobs per change plan.
- Compare another volume or instance family in a test environment.

Avoid changing multiple variables simultaneously, as doing so obscures which change produced the effect.

## 18. Real-World Investigation Scenarios

### Scenario A: High CPU After Deployment

**Symptom:** API p95 spikes, CPU on a subset of Pods hits 95%, request rate is nearly flat.

**Evidence to gather:**

- Deployment version and configuration diff.
- CPU per container and per thread.
- CPU profiles/hot stacks.
- GC pauses or allocation rates.
- Retry counts and request distribution.

**Hypothesis:** the new build introduced a retry loop or CPU-heavy serialization. If CPU tracks retry counts and profiles highlight the same code path, rolling back the canary or shifting traffic away is a justified mitigation. Afterward, fix retry/backoff logic and load-test.

### Scenario B: Container Restarts Due to OOM

**Symptom:** Pod in `CrashLoopBackOff`, last termination reason `OOMKilled`.

**Evidence to gather:**

- Previous container logs.
- Pod requests/limits and node allocatable resources.
- Container memory working set over time.
- Kernel/cgroup OOM events.
- Input size, concurrency, and heap profile.

**Hypothesis:** a large batch pushed memory or caches past the limit. Temporarily reduce concurrency or batch size; then optimize memory usage, set limits/requests from peak measurements, and confirm nodes have sufficient capacity.

### Scenario C: Slow VM with Low CPU

**Symptom:** application times out, CPU at 15%, plenty of free memory.

**Evidence to gather:**

- `iostat`, `await`, queue depth, and device latency.
- Processes in `D` state and `pidstat -d`.
- Volume throughput/IOPS/burst credit metrics.
- Kernel disk errors and provider volume events.

**Hypothesis:** the volume is throttled or backend storage latency spiked. Adding CPU will not help; reduce I/O, upgrade volume throughput, or relocate the workload per change plan.

### Scenario D: Many Pending Pods After Scale-Out

**Symptom:** HPA raises replicas, but new Pods fail to start.

**Evidence to gather:**

- `kubectl describe pod` and scheduler events.
- Node allocatable resources, taints, affinity, and topology constraints.
- Node autoscaler logs, max node counts, and cloud quotas.
- PVC zone bindings and IP/subnet capacity.

**Hypothesis:** the node pool hit its max count or Pods request GPUs/zones lacking capacity. Raise max only if quotas and budget allow; if placement constraints are wrong, fix the placement policy rather than provisioning mismatched nodes.

### Scenario E: Request Timeouts Isolated to One Zone

**Symptom:** errors cluster on backends in Zone B; Zone A is healthy.

**Evidence to gather:**

- Load balancer target health per zone.
- Flow logs, route/firewall changes, and DNS responses.
- Node network retransmits/packet drops.
- Provider health events and dependency endpoints.

**Hypothesis:** Zone B routing or network paths are impaired. Shift traffic away from unhealthy targets per runbook while monitoring remaining zone capacity to avoid overload.

## 19. Mitigation, Recovery, and Verification

Mitigation reduces user impact even before the root cause is permanently fixed. Pick the smallest action that restores SLOs without introducing new risk.

### Mitigation Options

- Roll back a recent deployment or config change.
- Shed load, rate-limit, or enable backpressure.
- Scale out if capacity is genuinely the bottleneck and dependencies can absorb the load.
- Shift traffic away from faulty nodes or zones.
- Pause competing batch jobs.
- Increase storage capacity or throughput per change procedures.
- Restart a specific process/Pod after capturing evidence and assessing impact.
- Execute failover per a tested runbook.

### Pre-Restart/Reboot Checklist

- Required logs and metrics are saved.
- Checked whether the process holds local state or active jobs.
- Replacement replicas/capacity are available.
- Drain plan and unflushed data checks are in place.
- An accountable owner and rollback path are assigned.
- Considered whether restarting will mask or destroy root-cause evidence.

### Verifying Recovery

After mitigation, confirm:

- Error rates, p95/p99 latency, and throughput return within thresholds.
- CPU, memory, disk, network, and queues stop climbing abnormally.
- Pods/VMs/processes remain healthy with stable restart rates.
- Dependencies and downstream services are not overloaded by shifted traffic.
- Jobs are not lost or duplicated uncontrollably.
- Alerts clear under sustained stability, not merely transiently.
- Monitor long enough to span relevant load cycles.

## 20. Writing Incident Reports and RCAs

A Root Cause Analysis (RCA) should explain what happened, why existing controls failed to prevent or detect it early, and what actions reduce recurrence risk. Focus on systems and conditions, not blaming individuals.

### Report Structure

| Section | Contents |
|---|---|
| Summary | Incident overview and primary impact |
| Impact | Affected users, tenants, requests, jobs, data, and SLOs |
| Timeline | Detection, escalation, mitigation, recovery |
| Evidence | Logs, metrics, traces, OS/provider events, and queries |
| Root cause | Technical mechanism that triggered the incident |
| Contributing factors | Missing guardrails, alerts, capacity, or tests |
| Mitigation | Actions taken during the incident and their effects |
| Resolution | Long-term fix and verification |
| Follow-up | Owners, due dates, priorities, and status |

### Writing Strong Action Items

Action items should include an owner, due date, verification criteria, and priority. Examples:

- Add an alert when cgroup memory pressure exceeds benchmarked thresholds persistently.
- Cap batch size and add tests using maximum expected input sizes.
- Add per-volume storage latency panels to the service dashboard.
- Update the CPU throttling investigation runbook.
- Add an admission/CI policy validating Pod requests/limits prior to deployment.

Avoid vague action items like "monitor the system better" or "improve performance."

## 21. Compute Incident Investigation Checklist

- [ ] Identify affected service, severity, scope, start time, and incident commander.
- [ ] Record region, zone, instance/node, Pod/container, process, and version.
- [ ] Standardize timestamps and correlation IDs.
- [ ] Collect application, system, kernel, runtime, orchestration, and cloud audit logs.
- [ ] Capture CPU, memory, disk, network, process, queue, and SLO metrics.
- [ ] Compare against baselines and healthy peer workloads.
- [ ] Check CPU saturation, throttling, steal, and run queues.
- [ ] Check memory pressure, swap, page faults, cgroups, and OOMs.
- [ ] Check disk latency, IOPS, throughput, free space, and inodes.
- [ ] Check network drops, retransmits, DNS, routes, firewalls, and connection states.
- [ ] Check process/thread states, file descriptors, kernel, driver, and service events.
- [ ] Check Pod events, probes, evictions, scheduler, and node autoscaler if on Kubernetes.
- [ ] Check VM health, quotas, provider maintenance, and storage/network events.
- [ ] Formulate hypotheses with supporting and refuting evidence.
- [ ] Preserve evidence before executing mutating actions.
- [ ] Apply controlled mitigations and monitor impact.
- [ ] Verify SLOs, dependencies, queues, and data after recovery.
- [ ] Write an RCA with owners, deadlines, and verification criteria for action items.

## 22. Practice Exercise

A document-processing API runs on Kubernetes. At 09:20 UTC, p99 latency jumps from 300 ms to 5 seconds and 5xx rates climb. HPA scales replicas from 4 to 12. Some new Pods stay `Pending`; running Pods show rising memory working sets and two containers hit `OOMKilled`. Node CPU sits around 55%, yet cgroup CPU throttling increases. Cache volume storage latency also jumps from 4 ms to 80 ms. A new release was deployed at 09:12 UTC.

1. Construct a timeline and list the log/metric sources to collect.
2. Why does 55% node CPU not rule out CPU as a contributing factor?
3. Which hypotheses simultaneously explain `OOMKilled`, throttling, and storage latency?
4. What should you inspect to determine whether `Pending` Pods are caused by capacity exhaustion or placement constraints?
5. Propose a safe mitigation sequence and what evidence to preserve before each step.
6. Define recovery verification criteria and preventive action items.

Hint: correlate the 09:12 UTC deployment with when latency began rising; check image/config diffs, requests/limits, cache behavior, and concurrency. Host CPU can have headroom while containers hit cgroup quota throttling. Slow cache storage can stall requests holding buffers/connections, inflating memory; new batching or concurrency settings can also trigger OOM. Collect previous Pod logs/events, cgroup stats, node allocatable resources, scheduler events, PVC/volume metrics, application traces, and cloud events. Mitigation could roll back the canary or reduce concurrency/batching after exporting evidence; do not scale out blindly when storage is the bottleneck. Verify p99/5xx, OOM/restarts, throttling, storage latency, queues, and downstream services return to baseline.

## Conclusion

Effective compute incident investigation relies on correlating logs, metrics, traces, events, and OS signals along a shared timeline and resource identity. Scope impact first, preserve evidence, classify bottlenecks across CPU, memory, disk, network, processes, or platform layers, and validate hypotheses with data. Mitigations must be controlled and verified against SLOs and dependency health. Post-incident RCAs must convert evidence into concrete actions that reduce the risk of recurrence.
