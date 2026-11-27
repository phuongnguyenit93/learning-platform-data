# High CPU: Distinguishing Legitimate Load, Error Loops, and Resource Contention

High CPU is one of the most common indicators when a server or application experiences performance issues. However, a 90–100% CPU reading does not explain its cause on its own. The machine might be handling a normal surge in incoming requests; a process might be repeating a failing operation and burning CPU uselessly; or the workload might be contending for CPU with other VMs/containers, slowing the application down even though its allocated compute capacity has not changed.

Proper diagnosis combines CPU utilization, runnable process counts, application latency, error logs, resource limits, and metrics from the hypervisor or container platform. The goal is to determine **whether CPU is being spent on useful work, wasted by errors, or whether the workload is waiting to be scheduled CPU time**.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module, in the **Compute Troubleshooting** chapter. It guides you through distinguishing legitimate load, error loops, and resource contention; collecting evidence on Linux, Windows, VMs, and containers; isolating the responsible process; and choosing an appropriate remediation.

## 1. High CPU does not automatically mean an application error

CPU utilization represents the proportion of time a CPU spends executing work over a measurement interval. On multi-core machines, tools display percentages differently:

- Some tools report aggregate machine utilization, where 100% equals total measured CPU capacity.
- Some tools report per-core utilization, so a single-threaded process can hit 100% even when a multi-core host still has spare capacity.
- Inside a VM/container, percentages may be calculated relative to provisioned vCPUs or a quota/limit, rather than the host's full physical CPU capacity.

For example, an 8-vCPU VM running at 75% CPU may be handling normal load. A 1-vCPU VM pinned at 100% for extended periods may need more capacity or application optimization. A container capped at 0.5 CPU can report 100% CPU against its quota even while the physical host has plenty of idle CPU.

Therefore, inspect CPU alongside:

- Throughput: completed requests, messages, or tasks per second.
- Latency: average response time and percentiles such as p95/p99.
- Error rate: percentage of failed requests or jobs.
- Queue depth: volume of pending work.
- CPU time by process, thread, and user/system state.
- Run queue, CPU pressure, steal time, or CPU throttling.
- Timing of deployments, scaling, configuration changes, or dependency incidents.

High CPU accompanied by rising throughput and stable latency may indicate legitimate workload. High CPU accompanied by falling throughput, rising errors, or sharp latency spikes usually requires deeper investigation.

## 2. Three cause categories to distinguish

| Cause category | Common indicators | Diagnostic questions |
|---|---|---|
| Legitimate workload | CPU rises alongside requests/jobs, throughput increases; primary processes perform expected work | Did demand actually increase? Are resources sufficient for peak load? |
| Error/retry loop | CPU rises without an increase in useful work; logs repeat errors, tight retries, crash/restart loops, or abnormal call volume | Which operation is the process repeating? Why is it not exiting or backing off? |
| Resource contention | Guest CPU may or may not be high; run queue, steal, CPU ready, throttling, or scheduling delay rises | Is the workload waiting on physical CPU or hitting quota limits? |

All three categories can coexist. For example, legitimate load spikes can overload a service; the service retries aggressively and drives CPU even higher; meanwhile, the VM runs on a crowded host and suffers CPU contention. Diagnosis must uncover the root cause and temporal sequence rather than forcing every incident into a single label.

## 3. Interpreting CPU and system metrics accurately

### 3.1. User time and system time

CPU time is commonly broken down into:

- **User time:** CPU time spent executing application code in user mode.
- **System time:** CPU time spent running kernel code on behalf of processes, such as system calls, the network stack, filesystems, or drivers.
- **Idle:** time when the CPU is not executing work.
- **I/O wait:** time the CPU is idle while the system has pending I/O operations waiting to complete; this is not CPU actively executing instructions.
- **Steal:** time when a VM is ready to run, but the hypervisor is allocating physical CPU to another workload.

High user time may reflect genuine computation, application loops, or inefficient algorithms. High system time can relate to heavy system calls, network packets, context switches, filesystems, or drivers. High I/O wait usually points toward checking storage; do not treat I/O wait as proof of CPU saturation.

### 3.2. Run queue and load average

The run queue is the number of tasks ready to run and waiting for CPU. If runnable tasks consistently exceed CPU capacity, scheduling wait time increases.

On Linux, load average is the mean number of running or uninterruptible (uninterruptible sleep) tasks over 1-, 5-, and 15-minute intervals. It is not a CPU percentage. A high load average can stem from busy CPUs, yet it also rises when many processes wait on I/O in state D.

Compare load average against logical CPU count, run queue length, CPU utilization, and process states. A load average of 8 means something very different on a 2-vCPU machine than on a 32-vCPU machine.

### 3.3. Context switches and threads

A context switch occurs when the CPU switches from one thread/process to another. Elevated context switching can be normal when handling many connections or threads; however, excessive short-lived threads, lock contention, or busy polling can create significant overhead.

An application with more threads does not necessarily run faster. If thread count far exceeds CPU capacity, the system can spend substantial time scheduling, synchronizing, and context-switching instead of completing work.

### 3.4. CPU pressure

Linux Pressure Stall Information (PSI) measures how much time tasks are stalled waiting for CPU, memory, or I/O. Rising CPU PSI shows that workloads are delayed waiting for CPU, even when average utilization does not continuously reach 100%.

In containers, PSI helps distinguish spare host CPU from a workload group experiencing limits or contention. Check PSI at the appropriate host/cgroup scope and compare against quotas, requests, and limits.

## 4. General diagnostic workflow

When receiving a high-CPU alert, do not immediately reboot or add vCPUs. Follow this sequence:

1. **Confirm scope:** a single VM, container, node, or the entire fleet?
2. **Confirm timing:** did CPU jump suddenly or climb gradually? Did it coincide with a deployment, cron job, scaling event, or traffic shift?
3. **Measure utilization:** inspect aggregate usage as well as per-core, per-process, and per-thread usage.
4. **Correlate with workload:** request rate, queue depth, batch schedules, throughput, and latency.
5. **Identify CPU-consuming processes:** find the top processes/threads and examine their behavior.
6. **Check for errors:** logs, exceptions, retries, restarts, timeouts, and outbound calls.
7. **Check limits/contention:** quotas, throttling, steal, CPU ready, run queue, and host utilization.
8. **Test hypotheses:** make one controlled change or reproduce in a test environment.
9. **Remediate and verify:** monitor CPU alongside latency, throughput, and error rate after the change.

~~~mermaid
flowchart TD
    A["High CPU alert"] --> B["Identify scope and start time"]
    B --> C["Measure CPU by host, process, and thread"]
    C --> D{"Did throughput / useful work increase?"}
    D -- "Yes" --> E["Check legitimate load and capacity"]
    D -- "No" --> F["Check logs, retries, and restarts"]
    F --> G{"Error loop or repeated activity?"}
    G -- "Yes" --> H["Isolate error and stop unbounded retries"]
    G -- "No" --> I["Check run queue, steal, ready, and throttling"]
    I --> J["Identify CPU contention or limits"]
    E --> K["Optimize / scale / tune concurrency"]
    H --> L["Fix root cause, backoff, and circuit breaker"]
    J --> M["Right-size / adjust quota / placement"]
    K --> N["Re-measure latency, throughput, error rate"]
    L --> N
    M --> N
~~~

## 5. Collecting evidence on Linux

Capture a sample long enough to reveal trends rather than running a single command only at the instant of an alert. The tools below are typically available in `procps`, `sysstat`, or `perf` packages depending on the distribution.

### 5.1. View aggregate and per-core CPU

~~~bash
# Check logical CPU count and topology
nproc
lscpu

# View CPU, load average, and processes over time
top

# Monitor each CPU every second
mpstat -P ALL 1

# View run queue, blocked processes, context switches, and CPU
vmstat 1
~~~

In `top` or `mpstat`, inspect `user`, `system`, `idle`, `iowait`, and `steal` separately. If one core is near 100% while other cores remain idle, the workload may be bottlenecked by a single thread or sequential execution path.

`vmstat` typically displays columns such as `r` (runnable), `b` (blocked), `cs` (context switches), and `us`/`sy`/`id`/`wa`/`st`. Read the header of your installed version, as column layouts can vary.

### 5.2. Identify processes and threads

~~~bash
# Sort processes by CPU
ps -eo pid,ppid,comm,%cpu,%mem,etime --sort=-%cpu | head -20

# Monitor per-process CPU every second
pidstat -u 1

# View threads of a process
top -H -p <PID>

# Monitor per-thread CPU of a process
pidstat -t -p <PID> 1
~~~

`%CPU` in `ps` may reflect average usage over the process lifetime rather than an instantaneous measurement like other tools. Confirm with `top`, `pidstat`, or time-series telemetry.

### 5.3. Inspect system calls and profiling

If a process spends high system time, observe system calls or sample stack profiles over a short interval:

~~~bash
# Summarize system calls for a process
sudo strace -c -p <PID>

# View CPU-consuming functions if perf is supported
sudo perf top -p <PID>

# Capture a profile over a short window
sudo perf record -F 99 -p <PID> -g -- sleep 30
sudo perf report
~~~

Profiling adds overhead and may require elevated privileges or kernel support. Enable it only for the required scope and duration, and avoid capturing sensitive data in production without proper controls.

## 6. Identifying legitimate load on Linux

Legitimate load usually shows a reasonable correlation between incoming work and completed work.

Indicators:

- Request rate or message rate increases alongside CPU.
- Throughput increases or remains at the expected high level.
- CPU time concentrates in the primary application processes.
- Error logs do not spike abnormally.
- Retry rate and restart rate remain stable.
- Latency may rise near capacity limits without exhibiting error loops.
- When load drops, CPU drops accordingly.

For example, a video-encoding worker may consume nearly 100% CPU while processing a large batch. If completed videos per minute scale proportionally with no errors, this may represent normal operation.

### 6.1. Check parallelism

If a process saturates 100% of one core on a 16-vCPU machine, check:

- Is the task inherently sequential?
- Is a lock or mutex forcing other threads to wait?
- Is the thread pool configured too small?
- Is a single partition or shard receiving all the work?
- Can the work be split without breaking ordering or consistency?

Adding vCPUs does not necessarily make single-threaded code run faster. Profile to locate the bottleneck before resizing the VM.

### 6.2. Forecast capacity

If legitimate load grows steadily, compare current capacity against demand:

- Hourly/daily CPU utilization and peak levels.
- p95/p99 latency and SLOs.
- Throughput per vCPU.
- Concurrent requests or jobs.
- Headroom for deployments, failover, and traffic bursts.

You can scale out additional replicas for stateless applications, or scale up VMs when workloads require more memory/CPU per instance. Check for bottlenecks in databases, networks, and storage before adding compute.

## 7. Identifying error loops and retry storms

An error loop happens when an application repeatedly performs a failing operation yet retries too quickly or without bounds. CPU is burned constructing requests, serializing payloads, handling exceptions, writing logs, and repeating identical work.

Examples:

- A service calls a dependent API that times out and immediately retries.
- A worker receives a poison message, fails processing, and immediately re-consumes the same message.
- A process reads a broken config file in a tight loop with no sleep.
- A service crashes and restarts continuously due to misconfiguration, running heavy bootstrap work each time.
- Clients time out waiting for a response and resend requests while the server is still processing earlier ones.

### 7.1. Indicators in metrics and logs

- CPU rises while successful throughput stagnates or drops.
- Error rate, timeouts, retry counts, or dead-letter counts climb.
- Logs repeat the same stack trace or error message at high frequency.
- Outbound request volume to a dependency surges abnormally.
- Processes restart or spawn new threads/tasks continuously.
- Context switches, network syscalls, or log I/O rise sharply.
- Queue depth fails to drain despite high worker CPU.

Do not conclude purely from log volume. A high-traffic system can legitimately emit many logs; group by error type, endpoint, dependency, and correlation ID to spot repeating patterns.

### 7.2. Inspect retry policies

Retries should include:

- A maximum attempt count or total retry time budget.
- Exponential backoff so wait intervals grow progressively.
- Jitter so clients do not retry in lockstep.
- Classification between retryable errors and non-retryable failures.
- A circuit breaker to pause calls to a failing dependency.
- A dead-letter queue or failure queue after max attempts.
- Idempotency to prevent side effects when requests/jobs are retried.

Unbounded retries can escalate a minor dependency glitch into a system-wide outage.

### 7.3. Example of retry with backoff

~~~python
import random
import time

MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 0.5
MAX_DELAY_SECONDS = 8.0

def call_dependency_with_retry():
    for attempt in range(MAX_ATTEMPTS):
        try:
            return call_dependency()
        except TransientDependencyError:
            if attempt == MAX_ATTEMPTS - 1:
                raise

            delay = min(
                MAX_DELAY_SECONDS,
                BASE_DELAY_SECONDS * (2 ** attempt),
            )
            delay = random.uniform(0, delay)
            time.sleep(delay)
~~~

This illustrates handling transient errors. Do not retry every exception; authentication failures, invalid input, or permission denials typically require configuration fixes rather than repeated attempts. In asynchronous or high-concurrency applications, use non-blocking retry policies paired with a circuit breaker.

### 7.4. Distinguish CPU loops from I/O loops

A retry loop can consume CPU building requests and handling errors, or it may spend most of its time waiting on I/O. If CPU stays low while latency and queue depth climb, the fault may lie in a dependency or the network. If CPU is high alongside rising system time, inspect syscalls, sockets, logging, and context switches.

## 8. Identifying CPU contention in VMs

In a VM, vCPUs are logical resources scheduled onto physical CPUs by the hypervisor. An 8-vCPU VM is not necessarily backed by 8 dedicated physical cores at all times. When multiple VMs on a host want to run simultaneously, the hypervisor must time-slice physical CPU.

### 8.1. CPU steal in Linux guests

CPU steal is the time a VM is ready to run while the hypervisor has not allocated a physical CPU to it. On Linux, observe the `st` column in `top`, `mpstat`, or equivalent tools.

Notable indicators:

- CPU steal rises at the same time latency spikes.
- The guest has runnable processes yet throughput drops.
- Guest CPU utilization alone does not explain the wait time.
- Multiple VMs on the same host or instance group exhibit similar symptoms.

Steal time often suggests host-layer contention or CPU scheduling limits, though it must be cross-checked with provider metrics and workload patterns. Not every cloud exposes the same level of host placement detail.

### 8.2. CPU ready and scheduling delay

Some hypervisors expose a CPU ready metric or vCPU scheduling wait time. Sustained high CPU ready indicates the VM wants to run but is not receiving physical CPU. Metric names, units, and formulas vary by platform; consult hypervisor/provider documentation before comparing thresholds.

If a VM has more vCPUs than it actually needs, co-scheduling a large vCPU group can increase complexity or wait time on some hypervisors. Right-size vCPU counts instead of defaulting to "more is always better."

### 8.3. Noisy neighbor

Noisy neighbor issues occur when other workloads sharing the same physical host or shared infrastructure consume resources and degrade your VM. Beyond CPU, contention can affect cache, memory bandwidth, storage, and networking.

If only one VM is affected, inspect that VM's configuration and workload first. If multiple VMs in the same group or timeframe show high CPU ready/steal, gather instance IDs, zones, timestamps, and metrics to engage the cloud provider or migrate workloads using supported placement policies.

### 8.4. Remediation measures

- Choose an instance family suited to sustained vs. burstable CPU demand.
- Right-size vCPUs based on telemetry, avoiding over- or under-provisioning.
- Use dedicated hosts or dedicated instances if isolation requirements and budget permit.
- Migrate or recreate the VM on a different host/placement when supported by the provider.
- Isolate heavy batch workloads from latency-sensitive services.
- Maintain cluster capacity headroom to reduce contention during failover.

Do not conclude a cloud provider fault from a brief CPU steal spike alone. Confirm the trend and SLO impact before opening a support case.

## 9. Identifying CPU throttling in containers

Containers can have CPU constrained via quotas or CPU limits. Once a container exhausts its quota within a scheduling period, its threads can be throttled until the next period. The host may have idle CPU while the container still suffers slowdowns.

### 9.1. Kubernetes requests and limits

- **CPU request:** the CPU amount used by the scheduler for Pod placement, representing requested capacity.
- **CPU limit:** the maximum CPU a container is permitted to consume, enforced by the runtime/cgroup mechanism.

If the CPU limit is too low, the container can be throttled under load. If requests are too low, the scheduler can pack too many Pods onto one node, causing contention when multiple workloads spike together.

Example:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

In this example, the container requests 0.5 CPU and can burst up to 1 CPU per its declared limit. `500m` equals half a CPU in Kubernetes units. This is not a guarantee that the container receives 0.5 dedicated physical cores.

### 9.2. Inspecting cgroup v2

On Linux using cgroup v2, `cpu.stat` inside the cgroup reports throttling counts and duration. The exact path depends on the runtime and cgroup mount layout:

~~~bash
# View the cgroup of the current shell
cat /proc/self/cgroup

# Inspect cpu.stat in the corresponding cgroup
cat /sys/fs/cgroup/cpu.stat
~~~

Fields such as `nr_periods`, `nr_throttled`, and `throttled_usec` help determine whether the container is throttled frequently. Read the file at the target container/Pod's cgroup path; the root cgroup file reflects aggregate host workloads.

### 9.3. Inspecting on Kubernetes

~~~bash
# View current CPU and memory if metrics-server is available
kubectl top pod -n <namespace>
kubectl top node

# View requests/limits configuration and Pod status
kubectl describe pod <pod-name> -n <namespace>

# View events and container logs
kubectl get events -n <namespace> --sort-by=.lastTimestamp
kubectl logs <pod-name> -n <namespace> --all-containers
~~~

`kubectl top` shows resource usage, though it does not always surface CPU throttling counts directly. Combine it with cAdvisor/Prometheus metrics or cluster monitoring to inspect throttling, CPU pressure, and wait times.

### 9.4. Addressing throttling

- Increase the CPU limit if the workload genuinely needs more CPU and node capacity allows.
- Adjust requests so the scheduler distributes Pods more appropriately.
- Tune concurrency and thread pools to avoid spawning excessive threads.
- Scale out if the application can distribute load horizontally.
- Use an appropriate node pool for CPU-intensive workloads.
- Check namespace-level and cluster-level quotas.

Raising limits without checking node capacity can cause multiple Pods to compete for CPU and overload the entire node. Evaluate requests, limits, node allocatable capacity, and co-located Pod load together.

## 10. Diagnosing on Windows Server

Windows reports CPU overall, per logical processor, and per process. Task Manager works well for quick observation; Performance Monitor (PerfMon) records trends and counter-level analysis.

### 10.1. Counters to monitor

| Counter | Meaning |
|---|---|
| Processor(_Total)\\% Processor Time | Overall CPU utilization |
| Processor(*)\\% Processor Time | Utilization per logical processor |
| System\\Processor Queue Length | Number of threads waiting for CPU |
| System\\Context Switches/sec | Context switches per second |
| Process(*)\\% Processor Time | CPU time per process |
| Process(*)\\Thread Count | Thread count per process |
| Process(*)\\ID Process | Maps counter instance to PID |

Counter names may be localized depending on Windows display language. Select the matching counters on the target machine and interpret values relative to logical processor count.

### 10.2. Quick collection with PowerShell

~~~powershell
# View top CPU-consuming processes by cumulative CPU time
Get-Process |
  Sort-Object CPU -Descending |
  Select-Object -First 15 Id, ProcessName, CPU, Threads

# Sample overall CPU utilization over time
Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 10

# Sample processor queue and context switches
Get-Counter '\System\Processor Queue Length', '\System\Context Switches/sec' -SampleInterval 1 -MaxSamples 10

# View processes and formatted CPU percentage
Get-CimInstance Win32_PerfFormattedData_PerfProc_Process |
  Sort-Object PercentProcessorTime -Descending |
  Select-Object -First 15 Name, IDProcess, PercentProcessorTime, ThreadCount
~~~

`Get-Process` shows cumulative CPU time per process rather than instantaneous percentage. `Get-Counter` provides interval-based samples. Some counter names may differ on non-English Windows installations.

### 10.3. Finding error loops on Windows

Correlate high-CPU processes with:

- Event Viewer: Application, System, and service-specific logs.
- Windows Service restarts and recovery actions.
- IIS request queues, application pool recycles, and failed request tracing if using IIS.
- .NET runtime exceptions, thread pools, and garbage collection.
- Windows Update, antivirus scans, or backup jobs running at the same time.

An antivirus scan or Windows Update can generate legitimate CPU load during a maintenance window. Verify task schedules and business impact before concluding it is an error loop.

## 11. Distinguishing application CPU from background tasks

Not every high-CPU process belongs to business application code. Background tasks may include:

- Antivirus/EDR scans.
- Backups, compression, or deduplication.
- Log rotation and log shipping.
- Package updates or Windows Update.
- Vulnerability scans.
- Indexing or filesystem scans.
- Inventory and configuration management agents.
- Batch jobs or cron/scheduled tasks.

Inspect the process name, command line, parent process, service owner, and execution schedule. If a security agent consumes sustained CPU, do not disable the agent immediately; inspect policies, version, scan scope, and vendor guidance.

## 12. Finding the cause at the application level

Once the primary process is identified, pinpoint the specific activity consuming CPU:

- Hot loops or algorithms whose complexity grows rapidly with input size.
- Excessive JSON/XML serialization.
- Regexes with heavy backtracking or unbounded expressions.
- Compression, encryption, or hashing on large payloads.
- Overly frequent garbage collection or memory allocation.
- Lock contention causing threads to spin or retry repeatedly.
- Excessive synchronous logging.
- Tight polling instead of event-driven waiting.
- Cache misses or repeated queries.
- Retry storms targeting dependent services.

### 12.1. Use a profiler instead of guessing

Profilers identify which functions or stacks consume CPU. Tools depend on the runtime:

- Java: Java Flight Recorder (JFR), Java Mission Control, or async-profiler.
- .NET: dotnet-counters, dotnet-trace, PerfView, or compatible profilers.
- Node.js: V8/Inspector CPU profiles.
- Python: cProfile, py-spy, or an appropriate profiler.
- Native Linux: perf, eBPF profilers, or equivalent tools.

Capture a profile over a window representative of the incident. Compare a baseline profile under normal load against a high-CPU profile to spot abnormal increases. Be mindful of overhead, permissions, and sensitive data.

### 12.2. Thread-level analysis

When a process exhibits high CPU, inspect which threads are consuming it:

- One thread at 100% can indicate a single-threaded loop.
- Multiple threads at 100% can reflect parallel load or concurrent retries.
- Many active threads with low throughput can indicate lock contention or busy waiting.
- Continuously growing thread pools can indicate stalled tasks or unbounded concurrency.

Increase thread counts only when you know the bottleneck is insufficient parallelism. For CPU-bound workloads, size concurrent workers according to available CPUs and container limits.

## 13. Quick diagnostic matrix

| Observation | Priority hypothesis | Evidence to collect |
|---|---|---|
| CPU rises alongside matching request rate and throughput | Legitimate load | Request metrics, per-process CPU, latency |
| CPU rises while throughput drops and errors/retries climb | Error loop or failing dependency | Logs grouped by error, retry counts, outbound requests |
| Guest CPU is low yet latency is high and steal/ready rises | Host/VM contention | Hypervisor CPU ready, guest steal, host metrics |
| Container hits limit and throttled time increases | CPU quota too low or high concurrency | cgroup `cpu.stat`, container limits, node capacity |
| One core at 100%, other cores idle | Sequential flow or hot thread | Per-core metrics, thread profile, locks |
| High system time and context switches | Kernel/network/driver or excessive threads | `mpstat`, `pidstat`, `perf`, network metrics |
| High load average, high iowait, CPU idle remains | Tasks waiting on I/O | `vmstat`, storage latency, state D processes |
| CPU spikes on a fixed schedule | Batch or background task | Cron/task scheduler, backups, scans, updates |

The matrix helps prioritize hypotheses. Confirm with data and controlled tests before altering configurations.

## 14. Remediation by root cause

### 14.1. If it is legitimate load

- Scale out replicas if the application is stateless and load can be distributed.
- Scale up VMs or containers when workloads need more sustained per-instance CPU.
- Optimize algorithms, queries, serialization, and caching.
- Tune concurrency to utilize CPU without spawning excessive threads.
- Use queues to smooth traffic peaks for asynchronous workloads.
- Separate batch workloads from latency-sensitive APIs.
- Configure autoscaling on appropriate metrics, combining latency/queue depth rather than CPU alone.

### 14.2. If it is an error loop

- Fix the underlying bug in code or dependency configuration.
- Cap retries and add exponential backoff and jitter.
- Use circuit breakers to halt calls to failing dependencies.
- Route poison messages to a dead-letter queue after max attempts.
- Ensure idempotency for operations that may be retried.
- Reduce repetitive logging with rate limits or log sampling while preserving metrics and diagnostic traces.
- Halt rollouts or roll back a recent release if evidence links it to the failure.

### 14.3. If it is contention or throttling

- Right-size vCPUs, requests, and limits based on metrics.
- Move workloads to more suitable nodes/instance types.
- Separate CPU-intensive workloads from latency-sensitive services.
- Adjust placement or use dedicated capacity when isolation is required.
- Maintain headroom for failovers and traffic surges.
- Escalate to the provider with evidence when abnormal CPU ready/steal persists.

### 14.4. If caused by background tasks

- Reschedule scans, backups, or batch jobs outside peak hours if policy permits.
- Cap agent concurrency and CPU usage where vendor-supported.
- Update agents if the running version has a confirmed bug.
- Separate maintenance windows from peak processing periods.
- Never disable security or backup tools without an approved replacement.

## 15. Practical example: API CPU at 95% while throughput drops

A catalog API runs on a 4-vCPU VM. After a deployment, CPU jumps from 45% to 95%, p95 latency quadruples, and successful throughput drops. Incoming request volume has not increased significantly.

The operations team collects:

1. `mpstat` shows a sharp rise in user time and low steal time.
2. `pidstat` identifies the API process as the primary CPU consumer.
3. Logs show many requests to the inventory service timing out.
4. Outbound metrics show inventory call counts per catalog request multiplied several times.
5. Application profiling shows most CPU spent inside a retry loop and exception serialization.

The team determines the new release changed the retry policy: whenever inventory times out, the API immediately retries multiple times within the same request. This drives CPU up despite flat inbound traffic, while successful throughput drops.

Remediation actions:

- Temporarily roll back the new release to restore service.
- Fix the retry policy with attempt caps, backoff, and jitter.
- Add a circuit breaker for the inventory service.
- Enforce an overall request deadline.
- Add per-dependency retry metrics and alerts when retries/request exceed thresholds.
- Re-test under simulated inventory timeout conditions before deploying.

Merely resizing the VM from 4 to 8 vCPUs would leave the retry loop intact and potentially burn twice the CPU. Adding compute does not replace fixing the root cause in application logic.

## 16. Practical example: Low VM CPU yet the application remains slow

An 8-vCPU VM shows guest CPU utilization around 35%, yet p99 latency spikes sharply during peak hours. `mpstat` shows rising steal time, and the hypervisor dashboard shows high CPU ready over the same window. Several other VMs on the same host group are affected as well.

The operations team verifies:

- No significant change in request rate.
- Process profiles show no hot loops or abnormal retries.
- The guest has runnable threads waiting for CPU.
- CPU ready rises in lockstep with latency.

The fitting hypothesis is host-layer CPU contention. The team records timestamps, instance IDs, and metrics, then migrates the VM using provider-supported placement controls. Afterward, steal/ready drops and latency returns to normal.

This case shows that low guest CPU utilization does not rule out a VM waiting for physical CPU.

## 17. Designing useful alerts

An alert triggered solely by CPU > 80% for 5 minutes can produce many false positives, especially for batch jobs or workloads designed to saturate CPU.

Combine signals:

- Sustained high CPU utilization.
- p95/p99 latency or SLO burn rate.
- Error rate and retry rate.
- Queue depth or request backlog.
- CPU throttling/steal/ready/pressure.
- Replica count and remaining capacity.

For instance, an alert can fire when CPU stays high **and** latency breaches SLO or queue depth grows. For batch jobs, track completion duration and progress instead of HTTP latency.

Thresholds must be tuned per workload, baseline, and service objectives. Never apply a single universal threshold across all VMs.

## 18. Common mistakes

- **Looking only at aggregate CPU:** misses a saturated single core or thread.
- **Treating load average as a CPU percentage:** load average also counts tasks in uninterruptible I/O wait.
- **Treating iowait as busy CPU:** iowait is usually CPU idle time waiting on I/O.
- **Adding vCPUs immediately on high CPU:** can mask retry loops or application bugs.
- **Mistaking low CPU for zero contention:** the VM may be waiting on the hypervisor or throttled.
- **Ignoring logs and throughput:** misses error loops that burn CPU while useful work falls.
- **Retrying without backoff:** triggers retry storms and further overloads dependencies.
- **Increasing threads indefinitely:** increases context switches, lock contention, and scheduling overhead.
- **Raising container limits without checking node capacity:** can overload the node and impact neighboring Pods.
- **Disabling agents to save CPU:** can remove security protection, backups, or monitoring.
- **Measuring only a single point in time:** misses batch schedules, traffic bursts, and deployment correlations.
- **Skipping post-fix re-measurement:** fails to prove the root cause was eliminated.

## 19. High-CPU troubleshooting checklist

When an alert fires, verify in order:

- [ ] Is the scope a host, VM, container, node, or the whole fleet?
- [ ] When did CPU rise, and does it coincide with a deployment, scale event, or scheduled job?
- [ ] What is the usage per core, per process, and per thread?
- [ ] How did user, system, idle, iowait, and steal change?
- [ ] Did run queue, load average, and CPU pressure increase?
- [ ] How did throughput, latency, error rate, retry rate, and queue depth change?
- [ ] Are there repeating error logs, restart loops, or abnormal outbound calls?
- [ ] Does the VM show high CPU ready/steal, or does the container show throttling?
- [ ] Are background agents, backups, antivirus scans, or updates running?
- [ ] Have processes been profiled to identify hot functions/threads?
- [ ] Does the chosen remediation address the actual root cause?
- [ ] After the change, have CPU, latency, throughput, and error rate returned to baseline?

## 20. Key takeaways

High CPU can signal legitimate load, an error loop, or resource contention. Legitimate load usually correlates with increased useful work; error loops correlate with abnormal retries, exceptions, or restarts; contention shows up through run queues, CPU steal/ready, pressure, or throttling.

Measure across host, process, and thread; correlate with throughput, latency, error rate, and queue depth; inspect logs and VM/container limits; then profile to pinpoint the exact cause. Scale only when the workload genuinely needs more capacity. For error loops, fix retry policies and application logic; for contention, adjust quotas, placement, or compute tier. Always verify outcomes with post-remediation metrics to ensure the service actually improved rather than merely shifting CPU numbers.
