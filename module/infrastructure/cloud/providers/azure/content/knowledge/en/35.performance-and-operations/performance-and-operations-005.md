# Diagnosing CPU, Memory, Disk, and Network Bottlenecks

## 1. Objectives and Context

An application deployed on Microsoft Azure can respond slowly even when its service status shows **Running** and health checks still return HTTP 200. The cause may be CPU operating at full capacity, memory under pressure, disks unable to keep up with I/O, or high latency in the network and network-bound dependencies. Sometimes multiple bottlenecks appear at once: database queries generate heavy I/O, slow I/O stretches connection hold times, and queued requests pile up.

This lesson belongs to the **Performance and Operations** chapter in the Azure ecosystem learning path: from subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute, storage, and data to deployment, monitoring, protection, and cost control. The focus is evidence-based diagnosis on **Azure Virtual Machines (VMs)**, while showing how to apply the same reasoning to Azure App Service, Azure Kubernetes Service (AKS), and managed data services.

After this lesson, you will be able to:

1. Distinguish **symptoms** (latency, timeouts, errors) from **saturated resources** and **root causes**.
2. Build an evidence chain from Azure Monitor, Application Insights, OS metrics, and resource configurations.
3. Recognize characteristic signs of CPU, memory, disk, and network bottlenecks, avoiding conclusions from a single metric.
4. Propose verifiable changes, re-measure before/after, and weigh SKU limits alongside Azure costs.

**Running scenario:** an API runs on a VM inside a virtual network (VNet), connecting to Azure SQL Database and an external service over HTTPS. Users report response times jumping sharply during peak hours. The operational task is to determine which layer is slowing the request flow and what evidence confirms it.

## 2. Understanding "Bottlenecks" Correctly

A resource is a bottleneck when demand exceeds its serving capacity over a period and causes queuing, latency, or errors. High utilization **is not sufficient** to declare a bottleneck. For example, 90% CPU while processing a background task may be fine if interactive requests still meet SLOs. Conversely, 40% average CPU can mask a single-threaded process saturating one core, or a CPU-throttled container.

Four signal groups to observe together:

| Signal Group | Question to Answer | Examples |
|---|---|---|
| **Latency** | How long must clients wait? | HTTP request P50/P95/P99; SQL call duration |
| **Traffic** | How much work is arriving and being processed? | Requests/second, queries/second, MB/second |
| **Errors** | Which work fails to complete? | HTTP 5xx, timeouts, connection errors, OOM kills |
| **Saturation** | Are resources or queues nearing their limits? | CPU, swap, disk latency, IOPS, retransmissions |

**P95** is the latency level below or equal to which roughly 95% of requests complete. P95/P99 expose slow requests easily hidden by averages. As load rises, queues typically grow rapidly before overt errors appear.

To conclude a root cause, prove a coherent chain: **specific load or change → saturation/queue metric → increased wait time in the request path → user-facing symptom**. Without a clear link in timing and scope, it remains only a hypothesis.

## 3. Collecting Evidence at the Right Layer on Azure

### 3.1. Identifying Measurement Sources

| Observation Layer | Useful Data | Azure Tools | Notes |
|---|---|---|---|
| Application experience | Request rate, P95/P99, errors, dependency calls | Azure Monitor Application Insights; distributed tracing | Requires instrumentation and appropriate sampling |
| Azure VM / resource | Percentage CPU, disk operations/bytes, network traffic, supported saturation metrics | Azure Monitor Metrics, Metrics Explorer, alerts | Metric names and availability depend on resource type/SKU |
| Inside the OS | Available memory, paging/swap, per-process CPU, disk latency, TCP retransmits | Azure Monitor Agent (AMA) with Data Collection Rule (DCR); VM insights; Linux/Windows tools | Many guest metrics are not collected automatically just by creating a VM |
| Configuration and limits | VM size, disk SKU, disk count/type, NIC, deployment zone, service limits | Azure Portal, Azure CLI, SKU limit docs | Effective limits can come from either VM or disk |
| Connected systems | DB CPU/IO, connection pools, downstream latency, DNS | Azure SQL metrics, Application Insights dependencies, Connection Monitor | "Slow request" does not necessarily mean the request-receiving VM is the cause |

**Distinguishing platform metrics and guest metrics:** most VM platform metrics are collected by Azure without installing an agent, whereas detailed memory, swap, process, or internal OS counters require guest collection setup. Installing AMA does not automatically mean the DCR collects every performance counter. On App Service or Azure SQL, metric names and collection differ from VMs.

### 3.2. Preparing an Investigation Window

Before drawing conclusions, record:

- **Time range in UTC**, e.g., 14:00–14:30 UTC, and when symptoms started.
- **Scope**: subscription, resource group, resource/VM name, instance, availability zone, region, deployment version.
- **Symptom definition**: specific API endpoint, P95/P99, error rate, load/requests per minute, affected user count.
- **Baseline**: the same hour on a normal day or the period before the latest deployment.
- **Recent changes**: code, app config, autoscale, VM size, disk, firewall/routes, database, connection counts.

Use matching time granularity when comparing—typically starting at **1-minute** intervals to see spikes, then aggregating at **5-minute** intervals for trends. Align timestamps across systems; aggregated or delayed data can make two charts appear unrelated.

Verify Azure RBAC/Entra ID permissions to read metrics and Log Analytics; OS access is also needed to run commands inside a VM. Do not open administrative ports to the public Internet: use Azure Bastion or an organization-approved management channel.

## 4. General Diagnostic Runbook

1. **Confirm application-layer impact.** Measure request rate, P95/P99, and errors by endpoint, version, and instance. Ask: are all requests slow, or only those calling a specific dependency?
2. **Isolate scope and timing.** Break down by VM/instance, pod, zone, environment, and version. Compare identical windows before/after the incident.
3. **Compare the four resources.** Inspect CPU, memory pressure, disk latency/IOPS/throughput, and network throughput/RTT/loss side by side with latency and traffic.
4. **Drill into the OS or processes.** Find the process, thread, disk device, connection, or container driving most of the anomalous signal.
5. **Check limits and dependencies.** Inspect VM/disk/NIC caps, container limits, Azure SQL, connection counts, DNS, and SNAT; verify where time is actually spent.
6. **Test one reversible hypothesis.** For example, throttle heavy concurrent queries, add controlled caching, move to an appropriate disk tier, or conditionally scale out.
7. **Re-measure and document conclusions.** Compare P95, error rate, equivalent load, queues, and cost. If symptoms persist, return to step 3 and revise the hypothesis.

Initial decision flowchart:

~~~mermaid
flowchart TD
    A["Slow API or timeouts"] --> B["Confirm P95, errors, traffic, and timing"]
    B --> C{"Do dependency traces dominate latency?"}
    C -- "Yes" --> D["Inspect SQL, DNS, connections, external services"]
    C -- "No or unclear" --> E["Compare CPU, memory, disk, network per instance"]
    E --> F{"Does saturation coincide with rising latency?"}
    F -- "Yes" --> G["Drill into processes, queues, and SKU limits"]
    F -- "No" --> H["Check locks, pools, GC, threads, traces, and dependencies"]
    D --> I["Propose hypothesis and small change"]
    G --> I
    H --> I
    I --> J["Re-measure under equivalent load"]
~~~

This flowchart guides the search. An application can suffer CPU and disk bottlenecks simultaneously; prioritize based on signals tied directly to request latency.

## 5. Diagnosing CPU Bottlenecks

### 5.1. Signals to Correlate

- **Azure VM Percentage CPU** rises alongside P95/P99; request rate plateaus even as incoming traffic keeps growing.
- One or more CPU cores remain continuously busy; run queue grows; thread wait time rises.
- CPU concentrates in a specific process—for example a Java process handling JSON, compression, TLS encryption, garbage collection (GC), or local query execution.
- Containerized apps can hit **CPU throttling** from CPU limits even while node-wide average CPU looks low.
- High CPU from retries or polling is sometimes a **consequence** of a slow dependency; check traces and retry counts.

**Example:** an 8-vCPU VM averages 25% CPU while one critical-path thread pegs a single core at 100%. Adding more total vCPUs will not necessarily speed up a single thread; profile the code, introduce safe parallelism, or optimize the hot path.

### 5.2. On-Host Checks

Linux, inside the VM:

~~~bash
# Show load average and CPU-consuming processes.
uptime
top -H -p 12345            # replace 12345 with actual PID; inspect threads
ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -20

# If sysstat tools are installed:
mpstat -P ALL 1 5
pidstat -u 1 5
vmstat 1 5
~~~

Inspect **%usr/%sys**, per-core CPU, runnable processes (column **r** in `vmstat`), and per-process CPU. Compare the run queue against vCPU count. High **%iowait** does not mean compute CPU is short; it usually points toward checking I/O.

Windows PowerShell:

~~~powershell
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name,Id,CPU
Get-Counter '\Processor(_Total)\% Processor Time'
Get-Counter '\System\Processor Queue Length'
~~~

The **CPU** property from `Get-Process` is cumulative CPU seconds, not instantaneous percentage. Use `Get-Counter` or Performance Monitor to inspect rates over time. Counter names depend on Windows OS and locale.

In AKS:

~~~bash
kubectl top nodes
kubectl top pods -A --containers
kubectl describe pod api-7d6c8fbd8d-abcde -n production
~~~

These commands require Metrics Server and appropriate observability setup. Confirming CPU throttling requires container/cgroup metrics or matching telemetry; **`kubectl top` alone does not prove throttling**.

### 5.3. Distinguishing Causes and Actions

| Evidence | Hypothesis | Follow-Up Check | Actions to Consider |
|---|---|---|---|
| High CPU, high request rate, growing queue | Compute cannot keep up with load | Profile hotspots, measure throughput/vCPU | Optimize algorithms, cache, scale out, or choose suitable VM size |
| One core pegged, rest of VM idle | Single-threaded bottleneck | Inspect thread dumps/profiles | Trim work on critical path, split work, or improve concurrency |
| GC consumes CPU, long pauses | Excessive allocation / heap pressure | GC logs, allocation profile | Reduce allocations, adjust heap after measuring |
| Pod slow while node CPU stays modest | CPU limit/throttling | Check throttled periods and limits/requests | Adjust resource limits and replicas |
| CPU climbs after downstream timeouts | Retry storm | Trace dependencies, retry counts | Add backoff, circuit breakers, cut unnecessary retries |

Never scale CPU simply because a chart crosses a fixed percentage. Tie outcomes to latency and throughput, and review VM/AKS cost after the change.

## 6. Diagnosing Memory Bottlenecks

### 6.1. Distinguishing Three Concepts

1. **High memory utilization**: RAM actively used by processes, kernel, or page cache; on Linux this can be completely normal.
2. **Memory pressure**: the system struggles to satisfy allocations, continuously reclaiming memory, swapping/paging to disk, or running frequent garbage collection.
3. **Out of memory (OOM)**: a process is terminated or allocation fails; containers may be marked **OOMKilled**.

Better indicators than "low free RAM" are **available memory**, paging/swap rate, major page faults, OOM events, commit usage, GC pauses, and latency. For managed-heap runtimes like Java, inspect both heap and **native/off-heap memory**, since total RSS can far exceed heap.

### 6.2. Inspection Commands

Linux:

~~~bash
free -h
cat /proc/meminfo
vmstat 1 5
ps -eo pid,comm,rss,%mem --sort=-rss | head -20

# Search for OOM events in kernel logs, if authorized:
journalctl -k --since "1 hour ago" | grep -i -E 'out of memory|oom|killed process'
~~~

Quick reading guide:

- **MemAvailable** in `/proc/meminfo` estimates RAM usable without heavy swapping.
- Columns **si/so** in `vmstat` show swap-in/swap-out; sustained activity alongside rising latency signals pressure.
- **RSS** reflects a process's resident memory; summing RSS across processes can double-count shared pages.
- An OOM kill is strong evidence, though it typically happens **after** an interval of memory pressure.

Windows:

~~~powershell
Get-Counter '\Memory\Available MBytes'
Get-Counter '\Memory\Pages/sec'
Get-Counter '\Memory\Committed Bytes'
Get-Process | Sort-Object WorkingSet64 -Descending |
    Select-Object -First 10 Name,Id,WorkingSet64
~~~

**Pages/sec** can include paging activity that does not indicate RAM shortage; inspect it alongside **Available MBytes**, page reads/writes, and application latency. Check Event Viewer for resource exhaustion warnings or process restarts.

In AKS:

~~~bash
kubectl top pods -A --containers
kubectl describe pod api-7d6c8fbd8d-abcde -n production
kubectl get pod api-7d6c8fbd8d-abcde -n production \
  -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'
~~~

If output shows **OOMKilled**, inspect memory limits, working set, leak indicators, and load before raising limits. Raising limits alone will not cure an ongoing leak.

### 6.3. Diagnostic Questions

- Does memory rise and fall with **traffic**, or climb steadily across hours/days? The latter points to a leak or unbounded cache.
- Do **swap-in/out** spikes coincide with disk I/O spikes? An apparent disk bottleneck can stem from RAM shortage.
- Do **GC pauses**, restarts/OOMs, or allocation errors align with P99 spikes?
- Is there a gap between container **memory requests/limits** and free RAM on the node?
- Is one process hitting a memory cap, or is the entire VM short on RAM?

Fixes can include patching memory leaks, bounding caches, reducing allocations, tuning heap size, capping concurrency, adding replicas, or moving to a higher-RAM VM SKU. Verify each change via post-change latency, OOM/restart rate, and memory pressure.

## 7. Diagnosing Disk and Storage Bottlenecks

### 7.1. Four Non-Interchangeable Metrics

| Metric | Meaning | Prominent Scenario |
|---|---|---|
| **IOPS** (operations/s) | Read/write operations per second | Many small, random accesses |
| **Throughput** (MB/s) | Data volume transferred per second | Large file reads/writes, backups, sequential I/O |
| **Latency** (ms/op) | Time to complete a single operation | Directly affects wait time |
| **Queue depth / queue length** | Pending or in-flight operations | Shows whether requests are piling up |

One system can hit its **IOPS** cap while MB/s stays low; another hits its **throughput** cap with fewer large operations. In Azure, there are also two limit tiers:

**Effective I/O capability ≈ the minimum of each managed disk's capability, the VM/SKU's aggregate I/O limit, and the application/I/O path's capability.**

Disk caching, bursting, and workload patterns can cause measured performance to differ from nominal specs. When analyzing Azure Disks, inspect **disk SKU/tier**, size/provisioned performance, caching mode, **disk IOPS/bandwidth consumed percentage** where supported, and **VM uncached IOPS/bandwidth consumed percentage**. Check both disk and VM sides; upgrading the disk will not help if the VM has already hit its aggregate I/O ceiling.

### 7.2. Measuring Inside the Guest

Linux:

~~~bash
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT
df -h
vmstat 1 5

# If sysstat is installed:
iostat -xz 1 5

# Identify heavy read/write processes, when tools are available:
pidstat -d 1 5
~~~

With **`iostat -x`**, inspect **r/s**, **w/s**, **rkB/s**, **wkB/s**, **r_await/w_await** (I/O latency in ms in common versions), and average queue length (**aqu-sz**, version-dependent). Do not treat **%util** alone as definitive proof of saturation on highly parallel storage devices. **`df -h`** detects **out-of-space** conditions, which are critical errors distinct from IOPS/throughput saturation.

Windows:

~~~powershell
Get-Counter '\PhysicalDisk(_Total)\Avg. Disk sec/Read'
Get-Counter '\PhysicalDisk(_Total)\Avg. Disk sec/Write'
Get-Counter '\PhysicalDisk(_Total)\Current Disk Queue Length'
Get-Counter '\PhysicalDisk(_Total)\Disk Transfers/sec'
Get-Volume | Select-Object DriveLetter,SizeRemaining,Size
~~~

**Avg. Disk sec/Read** and **Avg. Disk sec/Write** report in **seconds**; multiply by 1,000 for milliseconds. Inspect per-disk/instance counters if totals mask a single hot volume.

### 7.3. Interpreting Causes

- **Disk latency rises, queue grows, IOPS plateaus near a cap**: suspect disk or VM IOPS limit.
- **Throughput plateaus near a cap with large request sizes**: suspect MB/s limit.
- **Read latency climbs during low memory and active swapping**: prioritize RAM root cause, since faster disks may only mask symptoms.
- **Disk has headroom yet DB queries are slow**: check query plans, locking, transaction logs, and Azure SQL Database limits rather than immediately blaming the VM's managed disk.
- **Latency climbs after deployment**: check for changed access patterns, full table scans, synchronous logging, or write amplification.

Solutions may include query/index optimization, batching I/O, appropriate read caching, cutting unnecessary logging, tuning concurrency, selecting an appropriate disk tier/performance level, or resizing the VM when the VM itself caps I/O. Before changing disk cache modes, verify the workload's consistency and durability requirements; never alter caching based solely on throughput benchmarks.

## 8. Diagnosing Network Bottlenecks

Networking is not just "bandwidth." An API transferring tiny payloads can still crawl due to DNS, TCP handshakes, TLS, excessive round trips, packet loss, TCP retransmissions, connection counts, or downstream service limits.

### 8.1. Metric Groups and Possible Causes

| Symptom | What to Check | Possible Causes |
|---|---|---|
| Network bytes/s near SKU sustained cap; rising queues or retransmits | Azure Monitor network metrics, NIC, TCP stats | Bandwidth/packet-rate ceiling, app sending excessive data |
| Slow connection establishment | DNS lookup, TCP connect, TLS handshake | DNS, routing, firewall, proxy, remote endpoint |
| Intermittent connection failures under heavy fan-out | Connection count, ephemeral ports, SNAT | SNAT port exhaustion, connection churn, poor pool settings |
| Rising RTT, packet loss/retransmits | Connection Monitor, mtr/pathping, TCP stats | Path or destination issue; compare both directions |
| Only one dependency has high wait times | Application Insights dependency spans, DB metrics | Downstream service, queries, pools, or protocol |
| Connections consistently refused/timed out | NSG rules, route tables, DNS, firewall, endpoint | Reachability/config issue; distinct from bandwidth saturation |

**Network In Total / Network Out Total** (or equivalent metrics) show volume, not proof that bandwidth is saturated. In particular, **slow DNS** or a **slow downstream service** can reduce network throughput below normal levels.

### 8.2. Checking Connectivity from the VM

Linux:

~~~bash
ip -s link
ss -s
ss -tan state established | head -20

# Measure phases of a test HTTP request:
curl -sS -o /dev/null \
  -w 'dns=%{time_namelookup}s connect=%{time_connect}s tls=%{time_appconnect}s ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  https://example.com/health

# If installed in the environment:
sar -n DEV,TCP,ETCP 1 5
~~~

Replace **example.com** with an authorized endpoint. A **`curl`** run is a single sample and may not reflect application connection pooling/keep-alive, parallel calls, or private routing; take multiple samples and cross-check distributed tracing.

Windows:

~~~powershell
Get-NetAdapterStatistics
Get-NetTCPConnection | Group-Object State |
    Select-Object Name,Count
Test-NetConnection -ComputerName example.com -Port 443 -InformationLevel Detailed
Resolve-DnsName example.com
~~~

**Test-NetConnection** proves TCP reachability under test conditions, not HTTP/TLS latency or throughput. To measure paths between two endpoints, use **Azure Network Watcher Connection Monitor** where configured and permitted to inspect latency, reachability, and loss. **Network Watcher packet capture** supports deep inspection when specific investigation needs and permissions apply.

### 8.3. Separating Network Issues from Application Limits

Suppose traces show requests waiting **900 ms in a SQL dependency** while DNS and TCP phases are fast. Check SQL CPU, Data IO, Log IO, query duration, locking, and application pooling before blaming the VNet or NIC. If outbound connections surge alongside timeouts opening new connections, examine connection reuse, SNAT port counts, NAT Gateway, or the corresponding egress architecture.

On AKS, beyond node networking, examine service discovery, internal DNS, ingress, pod limits, and proxy/sidecar layers. On App Service, inspect request/dependency latency and outbound connections before changing the App Service Plan.

## 9. Querying Data with Azure CLI and Log Analytics

The following examples use hypothetical resource names and perform read-only queries. Sign into Azure CLI and select an authorized subscription. Available metrics depend on the resource; always verify published metric definitions for the actual resource.

### 9.1. Querying VM Platform Metrics

~~~bash
RG="rg-perf-demo"
VM="vm-api-01"

# Retrieve the exact Azure resource ID from the active subscription.
VM_ID=$(az vm show --resource-group "$RG" --name "$VM" --query id -o tsv)

# List metric names actually supported by the resource.
az monitor metrics list-definitions --resource "$VM_ID" \
  --query "[].name.value" -o table

# Inspect CPU over the CLI's default supported window.
az monitor metrics list --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --interval PT1M \
  --aggregation Average Maximum \
  --output json
~~~

Use the resource ID to avoid colliding with same-named VMs in other resource groups. For specific incidents, pass explicit UTC **start-time** and **end-time** flags rather than relying on defaults, e.g.:

~~~bash
az monitor metrics list --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --start-time "2026-11-20T12:00:00Z" \
  --end-time "2026-11-20T13:00:00Z" \
  --interval PT1M --aggregation Average Maximum -o json
~~~

These timestamps only illustrate syntax. Platform metrics do not expose every signal such as available RAM or per-process latency—those require guest instrumentation.

### 9.2. Analyzing CPU in Log Analytics

If a Data Collection Rule collects Windows performance counters into the **Perf** table, an example query is:

~~~kusto
Perf
| where TimeGenerated > ago(2h)
| where ObjectName == "Processor"
    and CounterName == "% Processor Time"
    and InstanceName == "_Total"
| summarize CpuAverage = avg(CounterValue),
            CpuP95 = percentile(CounterValue, 95)
    by Computer, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

**Note:** data appears only when the DCR collects those exact counters and the VM reports to the queried workspace. On Linux, object/counter/instance names can differ; verify what is actually collected rather than copying Windows filters blindly:

~~~kusto
Perf
| where TimeGenerated > ago(2h)
| summarize Samples = count()
    by Computer, ObjectName, CounterName, InstanceName
| order by Samples desc
~~~

If VM insights writes to **InsightsMetrics**, inspect the actual deployment's schema, namespaces, names, and tags before writing queries. Do not assume all guest telemetry lands in `Perf`.

### 9.3. Analyzing Disk Latency with Windows Counters

~~~kusto
Perf
| where TimeGenerated > ago(2h)
| where ObjectName == "PhysicalDisk"
| where CounterName in ("Avg. Disk sec/Read", "Avg. Disk sec/Write")
| summarize LatencySeconds = avg(CounterValue)
    by Computer, CounterName, InstanceName, bin(TimeGenerated, 5m)
| extend LatencyMs = round(LatencySeconds * 1000.0, 1)
| order by TimeGenerated asc
~~~

Combine guest latency with managed disk/VM platform metrics to see which ceiling is being hit. An empty query result may simply mean the DCR is not collecting the counter, not that the disk is healthy.

### 9.4. Correlating Request and Dependency Latency

With **workspace-based Application Insights** telemetry, query requests as follows:

~~~kusto
AppRequests
| where TimeGenerated > ago(2h)
| summarize Requests = count(),
            P95Ms = percentile(DurationMs, 95),
            Failed = countif(Success == false)
    by Name, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

To see which dependency consumes time:

~~~kusto
AppDependencies
| where TimeGenerated > ago(2h)
| summarize Calls = count(),
            P95Ms = percentile(DurationMs, 95),
            Failures = countif(Success == false)
    by Target, Type, bin(TimeGenerated, 5m)
| order by P95Ms desc
~~~

`AppRequests` and `AppDependencies` contain data only when the app is instrumented; other Application Insights setups may use different table/schema names. When sampling is active, counts reflect observed telemetry records; review sampling settings before estimating actual traffic. Never mechanically sum dependency P95 and request P95, because percentiles operate over different sample sets and concurrency.

## 10. Hands-On Scenario: Slow API Caused by I/O

Suppose an API's P95 climbs from **180 ms to 2,400 ms** over 20 minutes while request rate rises from **300 to 900 requests/minute**. The VM stays Running. Operations records these figures (purely hypothetical data for practicing reasoning):

| Metric During Incident | Observation | Preliminary Meaning |
|---|---|---|
| Average VM CPU | 42%, no core pegged continuously | CPU is not the strongest suspect |
| Available memory | 4.5 GiB, swap-in/out near 0 | No evidence of memory pressure |
| Disk read latency P95 | Jumps from 5 ms to 55 ms | Suspected I/O wait time |
| Disk queue | Grows steadily with request rate | I/O requests are backing up |
| Disk IOPS consumed | Approaches effective config limit | Likely hitting an IOPS ceiling |
| Network throughput | Below SKU cap; no notable loss rise | Does not support bandwidth bottleneck |
| Application trace | Most time spent reading files/indexes on VM | Matches suspicion from disk metrics |

**Diagnostic reasoning:**

1. Latency rises with request rate, while CPU and memory pressure do not explain it.
2. Disk latency and queue depth surge in the exact same window, with IOPS pinned at a ceiling.
3. Traces confirm request threads are waiting on reads against that volume.
4. Check VM SKU, managed disk tier, IOPS limits of **both VM and disk**, access patterns, and caching; if limits are not saturated, look further for locks or synchronous I/O.
5. Check post-deploy app changes: did redundant file/index reads appear? Eliminating unnecessary I/O is usually more sustainable than merely upgrading tiers.

**Experiment:** optimize file/index access to cut reads per request, or in a controlled test use a storage/VM configuration with higher IOPS. Re-run at equivalent load (**900 requests/minute**) and record P95, errors, disk latency, queue depth, IOPS, and cost. For example, P95 returning to **260 ms**, disk read latency dropping to **7 ms**, and shrinking queues support the hypothesis. If disk IOPS climbs while P95 stays unchanged, look for another bottleneck.

Two takeaways from this scenario: (1) the highest-utilization resource is not always the root cause, and (2) **evidence of where requests wait** must connect directly to **saturation metrics**.

## 11. Quick Differentiation Table and Check Order

| When You See... | Do Not Jump to Concluding... | Check Further... |
|---|---|---|
| 95% CPU | Just adding vCPUs solves it | Request latency, run queue, processes/threads, GC, CPU throttling |
| 35% CPU yet one endpoint is slow | CPU is definitely unrelated | Per-core/thread CPU, locks, serialization, container limits |
| Low "free" RAM | Out of RAM | `MemAvailable`, swap, page faults, OOM, GC, RSS trend |
| High disk queue | Must upgrade disk tier | Read/write await, IOPS/MB/s, VM/disk ceilings, swapping, access patterns |
| Disk full on capacity | Same as IOPS saturation | Distinguish capacity vs. performance, inodes/quotas, write errors |
| High network bytes/s | Network is definitely saturated | SKU bandwidth, RTT, loss/retransmits, connection counts |
| HTTP timeouts | VNet/NSG failure | DNS/TCP/TLS timing, App Insights dependency spans, DB/egress |
| Log query returns empty | No incident occurred | Agent, DCR, workspace, query filters, retention, sampling |

A practical priority order starts from the **slow request path** and drills down into the resource where requests actually wait. CPU, RAM, disk, and network charts are pieces for testing hypotheses—not four independent scoreboards.

## 12. Remediation, Verification, and Long-Term Operations

### 12.1. Building Load-Aware Baselines

Select at least two representative periods: normal hours and peak hours. For each, record **request rate**, **P50/P95/P99**, **error rate**, per-instance CPU, available memory/GC/swap, disk latency/IOPS/MB/s/queue, network latency/retransmits, and active VM/disk/service limits. Distinguish business days, batch jobs, and deployment windows when load behavior differs.

### 12.2. Alerting on Impact

- **User-facing alerts**: P95 breaching SLO and/or elevated error rate across consecutive windows.
- **Leading resource alerts**: memory pressure, `OOMKilled`, rising disk latency/queues, rising disk/VM IOPS consumed, CPU saturation, or network packet loss.
- **Diagnostic context alerts**: configuration changes, deployments, replica counts, and downstream dependency latency.

Set thresholds from each **workload's own baseline/SLO**, avoiding a blanket 80% rule across all CPUs, disks, and networks. Use Azure Monitor alerts and action groups per operational policy; watch log ingestion, retention, and label cardinality to avoid unnecessary observability spend.

### 12.3. Verifying Changes with Evidence

Every remediation action should document **hypothesis**, **expected metric improvement**, **comparison load**, **change timestamp**, **before/after results**, and **cost impact**. When resizing a VM, check network/disk limits and downtime or rollout mechanics. When tuning Java memory, measure GC and RSS—not just heap. When changing disk tiers, verify the VM SKU actually supports the higher limits.

Keep concise incident logs: affected scope, UTC timeline, charts/traces, confirmed or open root causes, applied changes, and preventive follow-ups so future investigations do not start from scratch.

## 13. Self-Check Exercises

**Exercise 1.** A VM averages 30% CPU, one endpoint's P99 spikes, and a single CPU core stays at 100% for 10 minutes. What additional data do you need to distinguish a single-threaded CPU bottleneck from lock contention or a slow dependency?

*Hint:* check per-thread CPU, stack profiles, endpoint traces, lock wait times, dependency latency, and retry rates.

**Exercise 2.** An API is slow; "free" RAM is down to 5%, yet `MemAvailable` remains relatively high with zero swap and no OOMs. Should you immediately add RAM?

*Hint:* insufficient evidence of memory pressure; check page cache, RSS, GC, waiting request threads, and other resources.

**Exercise 3.** Managed disk write throughput stays below the disk's nominal cap, yet disk latency climbs with traffic. List at least three possibilities.

*Hint:* VM IOPS/MB/s ceiling, small I/O sizes or access patterns causing queuing, synchronous app writes, caching effects, or wait time in another layer.

**Exercise 4.** Request P95 is 1,800 ms, CPU and disk look normal, and one dependency call takes ~1,500 ms. Outline a plan to inspect DNS, TCP/TLS, downstream responses, and connection pools without prematurely blaming "slow Azure networking."

**Completion criteria:** learners formulate hypotheses backed by **at least two evidence sources**, explain why competing causes are weaker, and specify how to re-measure under equivalent load.

## 14. On-Call Takeaways

Performance diagnosis on Azure starts with user-visible impact and links **request traces**, **platform metrics**, **guest metrics**, and **configured limits**. For CPU, inspect cores, threads, and run queues; for memory, inspect pressure rather than raw free RAM; for disk, separate IOPS, throughput, latency, and VM/disk caps; for networking, separate throughput from DNS, RTT, packet loss, connection handling, and downstream latency.

A trustworthy conclusion is reproducible: the fix targets the verified bottleneck, P95 and error rates improve under comparable load, and cost and stability remain aligned with operational requirements.
