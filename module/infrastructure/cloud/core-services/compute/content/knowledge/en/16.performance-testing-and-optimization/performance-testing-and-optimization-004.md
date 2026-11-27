# Distinguishing CPU, Memory, I/O, and Dependency Bottlenecks

When a cloud application runs slowly, immediately adding more vCPUs or RAM does not always solve the problem. The application may be waiting on disk, waiting on a database, constrained by a connection pool, throttled on CPU, or processing too much data in memory. To optimize properly, you must identify which component is limiting throughput or increasing latency.

This lesson focuses on four common bottleneck categories: **CPU-bound**, **memory-bound**, **I/O-bound**, and **dependency-bound**. This classification is based on the resource or component constraining the work. A real request can pass through many states: CPU processing, RAM/cache waits, disk reads, database calls, and back to CPU. Therefore, combine metrics, profiling, and controlled experiments to find the primary cause.

After this lesson, you can:

- Recognize symptoms of CPU, memory, I/O, and dependency bottlenecks.
- Choose appropriate metrics at the application, process, VM, container, and cloud service levels.
- Interpret CPU utilization, run queues, memory pressure, page faults, I/O latency, queue depth, and dependency latency.
- Use profiling, tracing, and OS tools to validate hypotheses.
- Design benchmarks and test changing one factor at a time to confirm effectiveness.
- Select suitable optimizations, avoiding scaling resources in the wrong direction or increasing cost without improving SLOs.

## 1. What Is a Performance Bottleneck?

A bottleneck is the resource or component limiting the system's processing rate at a given time. When that component reaches its limit, increasing load typically lengthens queues, increases latency, or causes request failures. Other components may still have spare capacity.

Examples:

- An image-compression process consumes nearly all CPU; adding vCPUs may increase throughput if the application parallelizes well.
- A JVM runs garbage collection continuously and its working set exceeds available RAM; adding RAM or reducing allocations may help.
- An API writes data to a volume with high I/O latency; adding CPU usually does not help.
- An API waits on a database or payment service; adding CPU to the API will not make the dependency respond faster.

Distinguish **utilization** from **saturation**:

- Utilization shows what percentage of a resource is being used over a measurement interval.
- Saturation shows demand exceeding or nearing serving capacity, typically manifested through queues, wait times, throttling, or pressure.

90% CPU can represent efficient usage if latency remains good and headroom remains. Conversely, 30% overall CPU can still have one core or one thread saturated, slowing down sequential requests.

### USE and RED Observation Models

Two complementary perspectives:

- **USE** (Utilization, Saturation, Errors) suits inspecting resources: CPU, RAM, disk, network, and queues.
- **RED** (Rate, Errors, Duration) suits observing services: request rate, error rate, and processing duration.

Combining both models connects user-facing symptoms to infrastructure limits.

## 2. Processing Flow and Where Waits Can Occur

A request typically traverses multiple layers. For example, an API receives a request, checks authorization, queries a cache, reads a database, calls another service, and returns a response.

    Client
      |
      v
    Load balancer / ingress
      |
      v
    Application process
      |-- CPU: parse, validate, compute, serialize
      |-- Memory: heap, cache, object allocation
      |-- Local/remote I/O: file, volume, socket
      |-- Dependency: database, queue, external API
      |
      v
    Response

Total latency can include CPU processing time, thread/connection pool wait time, I/O wait time, and dependency wait time. A thread waiting on a database consumes little CPU; hence low CPU does not prove an application is healthy.

Define measurement boundaries at each step:

- Client-side latency: total time observed by the user.
- Server-side latency: time from when the request enters the server until the response leaves the server.
- Queue wait: time a request/job waits to be processed.
- Application processing: time spent inside application logic.
- Dependency latency: time spent waiting on databases, caches, queues, or other APIs.

Distributed traces can split these durations into spans. If tracing is unavailable, per-dependency metrics and logs with correlation IDs still help isolate the bottleneck.

## 3. Symptoms of a CPU-Bound Bottleneck

CPU-bound bottlenecks occur when work requires more processing cycles than available CPU capacity. Common examples include encryption/decryption, compression, image/video processing, numerical computation, data analytics, heavy serialization, and high-complexity algorithms.

### Common Symptoms

- Sustained high CPU utilization on the cores used by the workload.
- Rising run queue or CPU pressure; processes must wait for the scheduler to grant CPU time.
- Throughput stops scaling proportionally with rising load; latency rises.
- CPU profiles show a few functions consuming most of the time.
- For containers, CPU throttling rises when hitting quota/limits.
- For VMs on shared environments, CPU steal or contention signals may rise.
- A single thread can saturate one core while overall CPU remains low.

High CPU utilization does not automatically mean adding vCPUs is required. If a request runs on a single thread, scaling from 4 to 16 vCPUs may not improve that request's latency. If the bottleneck is a lock or sequential serialization, adding cores can even worsen contention.

### Metrics to Inspect

| Metric | Meaning | Interpretation |
|---|---|---|
| CPU utilization per core | Usage level of each core | Detects a single saturated core despite low average |
| CPU usage per process/container | CPU actually used by the workload | Identifies the CPU-intensive process or container |
| Run queue / load average | Demand waiting for CPU and runnable work | Read alongside vCPU count and workload type; load average may also include uninterruptible tasks depending on the OS |
| CPU pressure | Time tasks are delayed due to lack of CPU | Helps identify contention on Linux supporting PSI |
| CPU throttling | Time or periods limited by quota | High throttling can raise latency even when the node has free CPU |
| CPU steal | Time the VM was not scheduled CPU by the host as desired | May suggest contention on the virtualization host |
| Context switches | Switching between tasks | Abnormal spikes may relate to excessive threads or scheduling overhead |

### Distinguishing CPU-Bound from Lock-Bound

An application may show low CPU while threads continuously wait on locks. In that case, adding vCPUs usually does not help. Thread dumps, lock profiling, or contention traces can reveal many threads waiting on the same mutex, monitor, or critical section.

### Optimization Directions

1. Profile CPU to locate hot paths instead of guessing by service name.
2. Reduce high-complexity algorithms, redundant work, and unnecessary serialization.
3. Reduce allocations and data copies if they drive up GC or memory bandwidth.
4. Tune parallelism; avoid spawning excessive threads and context switches.
5. Check lock contention, thread pools, and concurrency limits.
6. For containers, tune CPU requests/limits based on target load and latency.
7. If work is genuinely CPU-bound and parallelizable, test an instance with more vCPUs or faster CPUs and benchmark again.

## 4. Symptoms of a Memory-Bound Bottleneck

Memory-bound can mean the application lacks RAM capacity, or is constrained by memory access speed. The two cases exhibit different symptoms.

### Memory Capacity Pressure

When an application's working set exceeds available RAM, the OS must reclaim page cache, swap, or trigger the OOM killer. The application may slow down due to page faults, GC, or repeatedly reloading data.

Symptoms:

- Available memory drops steadily.
- Swap-in/swap-out or major page faults increase.
- Memory pressure rises; processes get OOM-killed.
- Containers restart with `OOMKilled` status.
- Heap or resident set size (RSS) grows abnormally.
- Garbage collection runs frequently with long pauses or high allocation rates.
- Latency rises over time as caches or heaps bloat.

### Memory Bandwidth or Access Latency

A workload might not lack RAM capacity yet continuously read/write large volumes of data, such as matrix operations, data analytics, or scanning large data structures. Here, the limit may lie in memory bandwidth, cache misses, or NUMA locality.

These signals typically require hardware profilers, performance counters, or specialized tools. Looking solely at percentage of RAM used is insufficient to diagnose them.

### Metrics to Inspect

| Metric | Meaning | Notes |
|---|---|---|
| Available memory | RAM allocatable to workloads without heavy pressure | Usually more informative than free memory alone |
| RSS / working set | Physical memory used by the process or container | Distinguish shared memory and memory cache depending on the tool |
| Heap used/committed | Runtime heap memory | For JVM, inspect alongside GC and native memory |
| Allocation rate | Object creation rate | High allocation rates can trigger frequent GC |
| GC pause / frequency | Garbage collection duration and frequency | Long pauses can directly spike tail latency |
| Page faults | Faults when accessing memory pages | Major page faults may require reading from storage |
| Swap activity | Paging out/in to swap | High swap-in/out usually signals pressure |
| OOM events | Out-of-memory events | Check container and node limits, not just VM RAM |

### Optimization Directions

- Identify memory leaks or objects retaining references too long.
- Reduce allocations, copies, and intermediate data; use streaming where appropriate.
- Tune cache sizes and eviction policies; oversized caches can increase GC or pressure.
- Tune heap/runtime based on profiles and GC logs; do not raise heap blindly if native memory or container limits are the cause.
- Set memory limits large enough for heap, metaspace, thread stacks, direct buffers, and native allocations.
- For workloads with large working sets, consider more RAM or partitioning data.
- Check NUMA placement and memory bandwidth when workloads are hardware-architecture sensitive.

## 5. Symptoms of an I/O-Bound Bottleneck

I/O-bound bottlenecks occur when processes spend significant time waiting to read/write data or transfer data over the network. I/O may involve block storage, filesystems, object storage, network filesystems, sockets, or other devices.

### Storage I/O

Common symptoms:

- CPU is not high while request latency rises.
- Disk read/write latency increases.
- IOPS or throughput hits volume/instance limits.
- I/O queue depth grows; processes wait long on I/O.
- Filesystem is nearly full or inodes are exhausted.
- Small random reads/writes are much slower than sequential operations.

Distinguish three quantities:

- **IOPS:** number of read/write operations per second.
- **Throughput:** amount of data transferred per second, typically in MiB/s or MB/s.
- **Latency:** time to complete a single I/O operation.

A volume may hit its IOPS limit with many small operations, or its throughput limit when transferring large blocks. Increasing volume size sometimes raises performance limits in certain services, though this rule depends on the provider and volume type.

### Network I/O

Common symptoms:

- Network throughput nears NIC or instance limits.
- Packet drops, retransmissions, or RTT increase.
- Sockets sit waiting; connection establishment is slow.
- DNS lookups or TLS handshakes take a large share of time.
- Cross-zone/region traffic incurs high latency or cost.
- NAT gateways, load balancers, or connection tracking hit quotas.

### Metrics to Inspect

| Metric | Meaning | Signs to Watch |
|---|---|---|
| Read/write IOPS | I/O operations per second | Hitting provisioned limits |
| Read/write throughput | Data read/written per second | Volume bandwidth saturation |
| I/O latency | Operation completion time | Rising alongside queue depth |
| Queue depth | Requests waiting or in flight | Sustained growth shows the device cannot keep up |
| Disk utilization | Time device is busy as defined by exporter | Does not always equate to saturation in cloud storage |
| Network throughput | Bytes/bits transferred per second | Compare against NIC/instance limits |
| Retransmissions/drops | Retransmitted or lost packets | Can raise latency and lower throughput |
| Connection count | Open sockets/connections | Detects connection exhaustion or excessive short-lived connections |

### Optimization Directions

- Use batching to reduce small I/Os; choose appropriate block sizes.
- Cache frequently read data if consistency allows.
- Optimize queries and indexes to reduce data read from storage.
- Use persistent volumes with adequate IOPS/throughput; check limits on both the volume and the instance.
- Separate logs, scratch data, and business data according to I/O needs.
- Use async I/O or pipelining when parallel processing helps without overloading downstream targets.
- For networking, reuse connections, use keep-alive, shrink payloads, and avoid unnecessary transfers.
- Check MTU, DNS, routing, packet loss, NAT, and bandwidth limits before changing instances.

## 6. Symptoms of a Dependency-Bound Bottleneck

Dependency-bound bottlenecks occur when the application must wait for another service to finish work. Dependencies can be databases, caches, message brokers, object storage, third-party APIs, identity providers, or cloud control/data plane services.

Example: an API processes a request in 20 ms but spends 800 ms waiting on the database; API CPU is only 15%. Adding vCPUs to the API barely changes query time.

### Common Symptoms

- High application latency while application CPU and memory remain low.
- Traces show a dependency span dominating total time.
- Connection pool is exhausted or requests wait to acquire a connection.
- Database query latency, lock waits, or replication lag increase.
- Queue depth and message age grow because consumers process slowly.
- External APIs return errors, timeouts, or rate limits.
- Retry rate increases, making requests to the dependency exceed user requests.
- A failing dependency slows down multiple downstream services simultaneously.

### Distinguishing Connection Pool Wait from Query Time

A request calling a database may wait in several places:

1. Waiting to acquire a connection from the pool.
2. TCP/TLS setup or authentication if opening a new connection.
3. Waiting for the database to receive and schedule the query.
4. Query execution, waiting on locks or I/O.
5. Returning results to the application.
6. Application deserializing and processing results.

Measuring only total database call duration makes it hard to identify which part is the cause. Instrument pool acquisition, connect time, query execution, and result processing separately when frameworks support it.

### Metrics to Inspect

| Dependency | Key Metrics |
|---|---|
| Database | Query latency, active connections, pool wait, lock wait, slow queries, CPU, I/O, replication lag |
| Cache | Hit ratio, miss rate, command latency, evictions, memory, connection count |
| Message broker | Queue depth, oldest message age, publish/consume rate, consumer lag, retries, dead-letter |
| External API | Request rate, latency percentiles, timeouts, error rate, 429/rate limits, retries |
| Object storage | Request latency, throughput, throttling, 4xx/5xx, request quotas |
| Identity/secrets service | Token/secret retrieval latency, throttling, failure rate, cache hits |

### Optimization Directions

- Optimize database queries, indexes, transaction scopes, and lock contention.
- Size connection pools to match database limits; an oversized pool can overload the database.
- Cache results according to consistency and TTL requirements.
- Use queues to decouple synchronous workloads from background work, while monitoring queue age and consumer lag.
- Set timeouts aligned with the end-to-end latency budget.
- Use bounded retries with exponential backoff and jitter; do not retry permanent errors or every error code.
- Use circuit breakers or bulkheads to prevent a failing dependency from exhausting application-wide threads/connections.
- Negotiate quotas/SLAs or implement fallbacks for critical external services.
- Reduce request fan-out; a request calling many dependencies in parallel can have its latency dominated by the slowest dependency.

## 7. Comparing the Four Bottleneck Categories

| Category | CPU | Memory | I/O | Dependency | Key Evidence |
|---|---|---|---|---|---|
| CPU-bound | High or single core saturated | May be normal | Not the main wait | Not dominating latency | CPU profiles, run queue, throttling |
| Memory-bound | May be low or elevated by GC | Pressure, page faults, OOM, or bandwidth limit | May rise due to swap/page-in | Usually not primary cause | Working set, GC, swap, memory pressure |
| I/O-bound | Usually low while waiting | May be normal | Latency/queue/throughput at limit | May involve network services | iostat, volume metrics, retransmissions |
| Dependency-bound | Usually low while waiting | Usually normal | May be low on calling host | High target latency, pool wait, queues, or errors | Distributed traces, dependency metrics |

These categories are not mutually exclusive. For instance, a database slowed by I/O can make an API dependency-bound; internally, the database is I/O-bound. Classify from the perspective of the component under investigation, then drill into the dependency.

## 8. Systematic Diagnostic Workflow

Do not start by resizing instances. Follow a progression from symptoms to evidence.

### Step 1: Identify Impact

- Which routes or workloads are affected?
- When did it start, and does it coincide with a deployment, maintenance, or configuration change?
- How did p50/p95/p99 latency, error rate, and throughput change?
- Is the entire fleet affected, or only one instance, zone, or tenant?
- Are SLOs/error budgets being violated?

### Step 2: Validate Measurement Data

- Are metrics continuous and using consistent units?
- Are there telemetry gaps or label changes?
- Are retried requests double-counted?
- Are client latency and server latency being mixed?
- Is there sufficient pre- and post-incident data for comparison?

### Step 3: Find Where Time Is Spent

Use traces or instrumentation to break latency into queue wait, application processing, and dependency calls. Without tracing, add per-step metrics or duration logs with correlation IDs.

### Step 4: Check Saturation at Each Layer

- CPU: per-core, run queue, throttling, steal, pressure.
- Memory: available, working set, GC, page faults, swap, OOMs.
- Storage: IOPS, throughput, latency, queue depth, filesystems.
- Network: throughput, drops, retransmissions, RTT, connection count.
- Dependencies: query latency, pool wait, queue age, timeouts, and quotas.

### Step 5: Form a Falsifiable Hypothesis

For example: "p99 rose because the API is waiting on the connection pool" is a hypothesis testable via pool wait duration, active/pending connections, and traces. "The VM lacks CPU" is a hypothesis that must be backed by CPU pressure, run queues, profiles, or throttling.

Each hypothesis should state:

- Which metrics should rise or fall if the hypothesis is true?
- Which logs/traces/profiles can confirm it?
- What is the smallest experimental change?
- What condition would disprove the hypothesis?

### Step 6: Test One Controlled Change

Change one factor at a time where possible: add vCPUs, raise memory limit, change volume type, reduce queries, adjust pools or caching. Compare under the same workload and measurement window. Avoid changing CPU, RAM, volume, and concurrency simultaneously, as you will not know which change caused the outcome.

### Step 7: Verify and Document

Re-measure throughput, latency percentiles, error rate, saturation, and cost. If nothing improves or another metric degrades, roll back and revisit the hypothesis.

## 9. Linux Observability and Profiling Tools

The following commands enable quick inspection on Linux VMs. Option names and detail levels may vary by distribution; some tools require installing packages or appropriate privileges.

### CPU and Processes

    # Process and CPU overview
    top

    # Periodic CPU, run queue, memory, swap, and I/O
    vmstat 1

    # Per-core CPU usage
    mpstat -P ALL 1

    # Per-process CPU and I/O
    pidstat -u -d 1

Use `top` or `pidstat` to identify processes; `mpstat` to check if any single core is saturated; `vmstat` to observe run queues, swap, and I/O wait. Interpret load average relative to CPU count and running task types.

### Memory

    # RAM and swap overview
    free -h

    # Paging and memory pressure info
    vmstat 1

    # Inspect current cgroup memory if using cgroup v2
    cat /sys/fs/cgroup/memory.current
    cat /sys/fs/cgroup/memory.max

Cgroup paths may differ when a process sits in a child cgroup or uses cgroup v1. For containers, prefer runtime/orchestrator metrics and cross-check against the node.

### Storage I/O

    # Per-device I/O
    iostat -xz 1

    # Per-process I/O
    pidstat -d 1

    # Filesystem capacity and inodes
    df -h
    df -i

Inspect `await`, `aqu-sz`, throughput, and IOPS per device. `%util` reflects device busy time as reported by the exporter; for cloud storage or parallel devices, do not rely on it alone to conclude saturation.

### Network

    # Sockets and connection states
    ss -s
    ss -tan

    # Interface statistics
    ip -s link

    # Measure TCP/HTTPS connection latency
    curl -sS -o /dev/null -w 'connect=%{time_connect} tls=%{time_appconnect} starttransfer=%{time_starttransfer} total=%{time_total}\n' https://service.example

Interpret `curl` output in the context of DNS, proxies, TLS, and the specific endpoint. Do not run network benchmarks or heavy load tests in production without a plan and guardrails.

### Profiling

- CPU profiler: identifies hot functions, call stacks, and CPU time.
- Heap profiler: finds objects retaining memory, allocations, and leaks.
- GC logs/profiler: measures runtime GC frequency, pauses, and allocation pressure.
- I/O tracing: identifies slow read/write syscalls and wait times.
- Distributed tracing: analyzes spans across applications and dependencies.
- eBPF/performance tools: observes syscalls, scheduler, network, and kernel when tooling is permitted.

Profiling has overhead. Start with short durations, appropriate sampling, and staging environments or a single canary instance. Protect profiles/logs because they may contain function names, paths, sensitive data, or internal details.

## 10. Windows Observability Tools

For Windows Server, Performance Monitor (PerfMon), Resource Monitor, and Event Viewer help analyze resources.

| Group | Counter or Tool | Question |
|---|---|---|
| CPU | Processor(_Total)\% Processor Time, Process\% Processor Time, System\Processor Queue Length | Is machine-wide CPU or one process saturated? |
| Memory | Memory\Available MBytes, Memory\Pages/sec, Process\Working Set, Committed Bytes | What are available RAM, paging, and working set? |
| Disk | PhysicalDisk\Avg. Disk sec/Read, Avg. Disk sec/Write, Disk Reads/sec, Disk Writes/sec | Are I/O latency and operation rates rising? |
| Network | Network Interface\Bytes Total/sec, Output Queue Length, TCPv4\Segments Retransmitted/sec | How are throughput, queues, and retransmissions behaving? |
| Process/service | Resource Monitor, Event Viewer, application logs | Which process is waiting on resources or logging errors? |

Counter names and interpretation may vary by Windows version, drivers, and storage type. Collect periodically and correlate with cloud provider metrics.

## 11. Designing Benchmarks to Confirm Bottlenecks

A benchmark is only useful when the test load represents real behavior and results are repeatable.

### Test Types

- **Baseline test:** measures the system at normal load to establish a comparison reference.
- **Load test:** increases load to expected operational levels.
- **Stress test:** exceeds expected load to find breaking limits and degradation behavior.
- **Spike test:** introduces sudden load surges to test autoscaling, queues, and recovery.
- **Soak test:** sustains load over long periods to detect memory leaks, cache drift, or resource exhaustion.
- **Component benchmark:** measures database queries, storage throughput, serialization, or a single algorithm separately to isolate costs.

### Testing Workflow

1. Define the question: is CPU, RAM, I/O, or a dependency limiting performance?
2. Select a representative workload: payload, concurrency, read/write mix, cache hit ratio, and request distribution.
3. Lock success criteria: throughput, p95/p99, error rate, resource pressure, and cost.
4. Keep environment stable: same image, configuration, dataset, region, and dependency versions.
5. Run warm-up to eliminate startup and JIT compilation effects where appropriate.
6. Step load upward, holding each level long enough for metrics to stabilize.
7. Record application, VM/container, storage, network, and dependency metrics.
8. Change one variable, re-run under identical conditions, and compare.
9. Repeat to quantify variance; do not draw conclusions from a single run.
10. Verify the system returns to normal state and clean up test resources.

Do not generate load that impacts other tenants or exceeds service contract limits. For third-party dependencies, use sandboxes or approved test environments.

## 12. Scenario-Based Diagnostic Examples

### Scenario A: CPU-Bound in an Image Processing Service

Symptoms: request rate rises, p95 climbs, worker CPUs hit nearly 100%, queue depth grows. CPU profile shows resize and encode functions consume most of the time.

Analysis:

- Memory is sufficient, with no swap or OOMs.
- Storage read/write latency is normal.
- Dependency latency is low.
- CPU profile confirms most time is spent in image processing.

Actions:

- Use a more efficient encoding library and review format/quality settings.
- Cap input image dimensions.
- Split queues by task type and scale workers by backlog.
- Test instances with more vCPUs if the algorithm parallelizes well.
- Measure throughput per vCPU and cost per completed image.

### Scenario B: Memory-Bound in a Java API

Symptoms: latency gradually rises after several hours, GC pauses grow, containers get `OOMKilled` even though average CPU is not high.

Analysis:

- Post-GC heap occupancy climbs over time.
- Allocation profile reveals an unbounded cache retaining objects long-term.
- Container memory must also accommodate metaspace, thread stacks, and direct buffers outside the heap.

Actions:

- Identify object retention and fix cache eviction.
- Re-measure heap, native memory, and container working set.
- Size heap below the memory limit with headroom for native memory.
- Run a soak test to confirm memory no longer climbs continuously.

### Scenario C: I/O-Bound in a Logging Service

Symptoms: API CPU is low while write latency climbs; volume I/O queue and write latency increase.

Analysis:

- Many small, synchronous writes.
- Volume hits its IOPS limit.
- Application traces show flush wait time dominates requests.

Actions:

- Buffer/batch logs within acceptable data-loss tolerances.
- Separate logs from business data volumes.
- Size volumes for required IOPS and throughput.
- Avoid synchronous disk logging on the request path when unnecessary.

### Scenario D: Dependency-Bound in an API Calling a Database

Symptoms: p99 increases, API CPU is low, requests wait in the connection pool, database query latency rises.

Analysis:

- Pool acquisition wait accounts for a significant share.
- Database shows lock waits and a slow query.
- Increasing pool size increases database connection count but worsens query latency.

Actions:

- Analyze query plans and indexes.
- Shorten transaction durations and reduce lock contention.
- Size pools according to database limits, not solely by application thread count.
- Enforce timeouts and bounded retries; avoid retry storms.
- Monitor query latency and pool wait after changes.

## 13. Beware of Misdirected Optimizations

| Symptom | Tempting Reaction | Why It Can Be Wrong | How to Verify |
|---|---|---|---|
| High latency, low CPU | Add vCPUs | May be waiting on database, disk, or locks | Traces, I/O wait, pool wait, and dependency metrics |
| Low average CPU | Conclude CPU is not the bottleneck | One core or container quota may be saturated | Per-core CPU, throttling, run queue |
| High RAM usage | Immediately add RAM | May be reclaimable cache or a memory leak | Available RAM, working set, GC, OOMs, growth trend |
| Disk utilization 100% | Increase volume size | May be limited by IOPS, queues, or small random I/O | IOPS, throughput, await, queue depth |
| API slow calling DB | Increase connection pool | Database may already be overloaded or locked | Pool wait, active connections, query latency |
| Queue growing | Unboundedly add workers | Can overload downstream dependencies | Consumer throughput, downstream saturation, retries |
| Rising CPU throttling | Remove all CPU limits | Can cause noisy neighbors and lose resource control | Benchmark suitable limits and observe node pressure |

Optimizations must improve user-facing targets at acceptable cost and risk. Never optimize a local metric if it degrades SLOs or shifts excessive pressure onto dependencies.

## 14. Measuring Effectiveness Before and After Optimization

To compare changes, record the same set of metrics before and after:

- Throughput at the same load level.
- p50/p95/p99 latency.
- Error/timeout rate.
- CPU and memory utilization/pressure.
- Disk IOPS, throughput, and latency.
- Network throughput, drops, and retransmissions.
- Dependency latency, pool wait, and queue age.
- Cost per completed request, transaction, or job.

For example, a worker processes 100,000 images per hour on 8 vCPUs. After optimizing the algorithm, the worker processes 150,000 images in the same time on 8 vCPUs. Throughput rose 50%; if image quality and error rate remain unchanged, cost per image may decrease. However, if CPU utilization spikes and p99 breaches limits, the result may not yet be production-ready.

You can use the formula:

    Cost per successful operation =
        Total resource cost in period
        / Number of successfully completed operations in period

For systems with multiple dependencies, include the cost of both the caller and called components if targeting end-to-end cost.

## 15. Bottleneck Diagnosis Checklist

### Before Investigating

- [ ] Identify affected services, routes, workloads, and time window.
- [ ] Record throughput, error rate, p50/p95/p99, and SLOs.
- [ ] Correlate deployments, maintenance, scaling, and configuration changes.
- [ ] Verify telemetry is continuous, uses proper units, and avoids double-counting.

### CPU

- [ ] Check CPU by core, process, container, and fleet.
- [ ] Check run queues, CPU pressure, steal, and throttling.
- [ ] Profile hot paths, lock contention, and thread pools.
- [ ] Verify whether the workload can utilize additional vCPUs.

### Memory

- [ ] Check available memory, RSS/working set, and limits.
- [ ] Check swap, major page faults, pressure, and OOMs.
- [ ] For managed runtimes, inspect heap, allocations, and GC pauses.
- [ ] Check caches, object retention, native memory, and NUMA if applicable.

### I/O and Network

- [ ] Check IOPS, throughput, latency, and queue depth.
- [ ] Check filesystems, inodes, disk pressure, and I/O wait.
- [ ] Check NIC throughput, drops, retransmissions, RTT, and connection counts.
- [ ] Identify limits of volumes, instances, NAT, load balancers, or network services.

### Dependencies

- [ ] Measure latency and errors of each dependency.
- [ ] Separate pool wait, connect time, query time, and response processing.
- [ ] Check queue depth, oldest message age, consumer lag, and retries.
- [ ] Check quotas, rate limits, timeouts, circuit breakers, and fallbacks.

### Validating Changes

- [ ] Each experiment has a specific hypothesis and validation metrics.
- [ ] Change only one primary variable at a time when possible.
- [ ] Keep workload and benchmark conditions comparable.
- [ ] Re-measure throughput, latency, errors, saturation, and cost.
- [ ] Have a rollback plan if SLOs or dependencies degrade.
- [ ] Document results and update runbooks/dashboards.

## 16. Self-Check Questions

1. An API has 20% CPU, 2-second p99 latency, and traces show 1.7 seconds waiting on the database. What type of bottleneck is this likely to be? Why might adding vCPUs not help?
2. A VM's average CPU is 35%, yet one core constantly hits 100%. How can this affect single-threaded requests?
3. Distinguish memory capacity pressure from a memory bandwidth bottleneck.
4. Why can a container memory limit cause OOM even when the node still has free RAM?
5. Which three aspects of storage do IOPS, throughput, and I/O latency describe?
6. When queue depth grows while worker CPU is low, which dependencies and concurrency settings should be checked?
7. Why can increasing a connection pool slow down a database?
8. How can distributed traces be used to distinguish pool wait from query execution time?
9. Why do benchmarks require warm-up, representative load, and single-variable changes?
10. Which metrics must be compared to prove an optimization improves performance while reducing cost?

Properly distinguishing bottlenecks enables evidence-based solutions. CPU-bound workloads need profiling and compute optimization; memory-bound workloads need working set, allocation, and pressure control; I/O-bound workloads need latency, throughput, and queue analysis; dependency-bound workloads need investigation of target services, pools, and call flows. Through controlled testing and re-measuring both SLOs and cost, teams can improve performance without wasting resources on the wrong layer.
