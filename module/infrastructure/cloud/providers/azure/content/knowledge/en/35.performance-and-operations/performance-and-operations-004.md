# Optimizing JVM, Memory, and Garbage Collection on Azure

In the **CLOUD_PROVIDERS_AZURE** module, learners explore Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data services, as well as deploying, monitoring, securing, and controlling the cost of application architectures on Azure. Part of the **Performance and Operations** chapter, this lesson explains how to optimize the **Java Virtual Machine (JVM)**, memory usage, and **garbage collection (GC)** in environments such as **Azure Kubernetes Service (AKS), Azure App Service, Azure Container Apps, and Azure Virtual Machines**.

**Running scenario:** a Java 21/Spring Boot application ingests orders over a REST API, sends events to Azure Service Bus, and writes to Azure SQL Database. The app runs in an AKS container with a 2 GiB memory limit; as traffic increases, p99 latency spikes, Pods occasionally get `OOMKilled`, yet sometimes the heap dashboard shows only 900 MiB. The goal is not to hunt for "magic JVM flags," but to determine **where memory is actually going, whether GC is truly causing slowness, whether the container is experiencing CPU throttling, and which change produces measurable improvement**.

After this lesson, you will be able to:

- Explain **heap, metaspace, thread stacks, direct buffers, code cache, and native memory**, distinguishing JVM heap from RSS/container memory.
- Understand how modern JVMs read **cgroup CPU/memory limits**, and the relationship between `-Xmx`, `-XX:MaxRAMPercentage`, Kubernetes `requests/limits`, CPU throttling, and OOM.
- Compare **G1 GC, ZGC, and Parallel GC** across throughput, latency, heap size, JDK version, and operational conditions; choose a collector through experimentation rather than guesswork.
- Enable **GC logs, Java Flight Recorder (JFR), `jcmd`, Native Memory Tracking (NMT), and JMX/Micrometer/OpenTelemetry** aligned with data sensitivity and overhead.
- Tune memory/GC on AKS, App Service, Container Apps, and VMs; design **startup/readiness/liveness probes, graceful shutdown, and autoscaling** that do not worsen incidents.
- Use **load tests, SLIs/SLOs, p95/p99, allocation rate, GC pauses, CPU throttling, and working set** to prove effectiveness.
- Troubleshoot **`OutOfMemoryError`, `OOMKilled`, heap leaks, native-memory leaks, GC thrashing, thread explosions, memory spikes, and noisy neighbors** using ordered runbooks.
- Establish **cost control, security, rollback, production checklists, and a repeatable tuning process**.

## 1. JVM Optimization Starts with Service Objectives, Not GC Flags

A Java application can have "very little GC" yet respond slowly because Azure SQL is locked, Service Bus builds a backlog, DNS/Key Vault is slow, connection pools are exhausted, or container CPU is throttled. Conversely, you might see frequent short young GCs while the application comfortably meets its SLOs. Proper optimization must start from **user experience and serving capacity**.

### 1.1. Common Objectives

| Objective | SLI/KPI to Measure | Common Pitfalls |
|---|---|---|
| API latency | p50, p95, p99, and timeout rate | Averaging p95 across multiple Pods |
| Throughput | Successful requests/s or orders/s | Counting HTTP 500 responses as successful |
| Availability | Good/eligible requests over an SLO window | Equating a health endpoint with end-user availability |
| CPU efficiency | CPU usage, throttled periods, CPU/transaction | Watching CPU usage while ignoring throttling |
| Memory | RSS/working set, heap used/committed, non-heap, direct/native | Treating heap used as total Pod memory |
| GC | Pause distribution, GC time fraction, allocation/reclamation | Looking only at total GC count |
| Startup | Cold start, warm-up, readiness time | Comparing warmed runtime against a cold new version |
| Cost | Cost per good transaction, instances, memory tier | Cutting RAM while increasing CPU and Pod count |

### 1.2. Defining a Baseline for the Sample System

Assume criteria **set by the application team** (not an Azure SLA):

```text
Production SLO:
  API availability: >= 99.9% good requests / rolling 30 days
  p95 API latency under representative load: <= 250 ms
  p99 API latency under representative load: <= 800 ms
  OOMKilled in stable load: 0
  Capacity target: 400 good requests/s with agreed headroom
  Memory cost per good transaction: tracked weekly
```

These numbers are for learning; real thresholds must come from business requirements, baselines, and load tests. **GC latency does not equal HTTP latency**: a single 30 ms pause does not by itself create a 900 ms request p99, though multiple pauses or scheduling effects can contribute.

### 1.3. Performance Investigation Workflow

```text
Define user-facing SLO and workload mix
             |
             v
Collect baseline: latency, throughput, CPU, RSS, heap, GC
             |
             v
Find bottleneck and form one hypothesis
             |
             v
Choose one small, reversible change
             |
             v
Run comparable load test + diagnostics
             |
             v
Compare SLI, resource headroom and cost
             |
       +-----+-----+
       |           |
       v           v
   Improved     Not improved
       |           |
    Canary      Revert/rethink
       |           |
       +-----+-----+
             |
        Document result
```

Do not raise `-Xmx`, switch GCs, increase Pod limits, and change HTTP thread pools **simultaneously**: you will not know what caused an improvement or a new regression.

## 2. JVM Memory Model: Heap Is Only Part of It

In the HotSpot JVM, process memory typically spans multiple regions. Exact boundaries depend on JDK, vendor, OS, configuration, and workload.

```text
Container / process memory budget
┌───────────────────────────────────────────────────────────────┐
│ JVM process                                                   │
│ ┌───────────────────────────────┐ ┌─────────────────────────┐ │
│ │ Java Heap                     │ │ Native / Non-Heap       │ │
│ │ - Young generation            │ │ - Metaspace             │ │
│ │ - Old generation              │ │ - Thread stacks         │ │
│ │ - Live objects + free space   │ │ - Code cache / JIT      │ │
│ │ - GC-managed object memory    │ │ - Direct/NIO buffers    │ │
│ └───────────────────────────────┘ │ - GC structures         │ │
│                                   │ - JNI/native libraries  │ │
│                                   │ - Class data, malloc    │ │
│                                   └─────────────────────────┘ │
│ Native memory pages, mappings, allocations, runtime overhead  │
└───────────────────────────────────────────────────────────────┘
  Plus container-charged memory outside main JVM process:
  sidecars, shell/helper processes, some file cache/kernel charges...
```

### 2.1. Heap

**Heap** is where the JVM manages most Java objects. `-Xms` controls initial heap size, while `-Xmx` caps maximum heap per configuration/collector. `Used heap`, `Committed heap`, and `Max heap` are three distinct quantities:

| Metric | Meaning | Example |
|---|---|---|
| Heap used | Space currently occupied by objects in the heap at measurement time | 950 MiB |
| Heap committed | Heap memory committed by the JVM to the OS, not necessarily all used | 1,250 MiB |
| Max heap | Upper bound the JVM can use per configuration/ergonomics | 1,300 MiB |

Heap used is only an **instantaneous snapshot**. After a full/old collection, used heap typically drops, but if used heap climbs over time under steady load without dropping after collections, suspect **retained objects** or a growing cache.

### 2.2. Metaspace

Metaspace holds metadata about classes and class loaders, typically in native memory. Applications using heavy dynamic proxies, class generation, application reloads, or plugin loaders can grow metaspace. `-XX:MaxMetaspaceSize` can cap usage, but **setting it too low can trigger `OutOfMemoryError: Metaspace`**. Do not cap metaspace just to make a dashboard look lower without understanding the cause.

### 2.3. Thread Stacks

Each OS thread has its own stack and overhead. The JVM flag `-Xss` or `-XX:ThreadStackSize` (as supported by JVM/version) adjusts stack size; avoid shrinking it too aggressively as that can cause `StackOverflowError` or native thread creation failures. An app spawning thousands of threads can bloat native memory even while heap barely changes.

### 2.4. Direct/NIO Buffers

`ByteBuffer.allocateDirect()`, Netty, TLS/network I/O, and some storage/database clients allocate **native/direct buffers** outside the Java heap. If direct allocations grow excessive or leak, process/container memory rises while heap charts look normal. `-XX:MaxDirectMemorySize` can adjust the upper bound for **a subset of direct buffer allocations**, **not a cap on all native memory**.

### 2.5. Code Cache and JIT

The JIT compiler compiles hot methods into machine code stored in the code cache; JIT threads and compiler structures also consume memory/CPU. JVM warm-up can make initial CPU and latency differ from steady state. Blindly disabling JIT to save memory usually degrades throughput severely.

### 2.6. JNI/Native Libraries, GC Structures, and Memory Mapping

Java applications using compression, cryptography, image processing, RocksDB, Netty, or native drivers can allocate memory managed by native libraries. GC implementations also consume their own native structures. Mapped files and OS page cache have measurement semantics distinct from committed heap.

### 2.7. What `-Xmx` Does Not Limit

`-Xmx=1g` **does not limit total RSS/Pod memory to 1 GiB**. It does not cap metaspace, stacks, code cache, direct buffers, or sidecars. In a Pod with a 1.5 GiB limit, a 1 GiB heap can still get the Pod `OOMKilled` when native + sidecars + kernel/accounted cache exceed the budget.

## 3. Distinguishing Heap, RSS, Working Set, Cgroup Usage, and OOM

Tools and platforms measure memory in different ways. Record **unit, data source, and definition** before comparing.

| Metric | Typically Collected From | Interpretation |
|---|---|---|
| `jvm_memory_used_bytes{area="heap"}` | JVM/Micrometer/Prometheus | Heap currently used |
| `jvm_memory_committed_bytes` | JVM/Micrometer | Committed heap/non-heap by pool |
| `process_resident_memory_bytes` | Process exporter/metrics | Process RSS as reported by collector |
| `container_memory_working_set_bytes` | Kubernetes/container metrics | Working set per metric implementation; not equal to heap |
| cgroup memory current/usage | Linux cgroups v1/v2 | Kernel-accounted cgroup usage, including file/cache/kernel charges |
| `kubectl describe pod` OOMKilled | Kubernetes status | Container killed, usually for exceeding limit/cgroup OOM |
| `java.lang.OutOfMemoryError` | JVM exception/log | JVM failed to allocate the requested memory area |

### 3.1. Two Types of OOM to Distinguish

**JVM `OutOfMemoryError: Java heap space`:** heap lacks room to allocate after GC attempts; the JVM can write a heap dump if configured, and the process may continue or exit depending on flags and application code.

**Kubernetes `OOMKilled`:** the kernel/container runtime kills the process when the memory cgroup budget is breached. The JVM **may not have time to print a Java heap OOME or write a heap dump**, and events/exit codes help clarify (for instance, exit code 137 can come from SIGKILL—verify `Reason: OOMKilled`, do not rely on exit code alone).

A Pod with `heap used=800 MiB` and `Xmx=1.2 GiB` can still be `OOMKilled` if native memory/cgroup cache/sidecars push the total over the container limit.

### 3.2. Non-Heap Memory Regions Must Fit Within the Budget

When sizing, think in terms of:

```text
Container limit
  >= JVM max heap (Xmx or computed max heap)
   + metaspace
   + thread stacks
   + direct/native buffers
   + code cache/JIT/GC overhead
   + OS/runtime/process overhead
   + variation/headroom
```

This is a **budgeting model**, not a byte-exact accounting formula. Some metrics overlap or define RSS/working set differently; do not add metrics from different sources when one already includes another.

### 3.3. Process Memory vs. Pod Memory

In a Pod with a **main Java container** and **sidecar containers**, each container has its own configured memory limit/usage. Pod-level accounting and eviction behavior depend on Kubernetes version, OS, and resource configuration; **do not treat main Java process memory as the total Pod cost**. A sidecar OOM can break logging or networking even if the Java process is not killed.

## 4. How Does the JVM Understand Container/Cgroup Limits?

Modern HotSpot JDKs support **container awareness**, typically enabled via `-XX:+UseContainerSupport` depending on JDK/version/build. This lets JVM ergonomics read cgroup CPU/memory limits instead of only host total RAM/cores. Older JDKs, backports, vendor builds, cgroups v1/v2, and runtimes can behave differently; **always inspect the running JDK**, rather than assuming every Java 8 or base image sees containers identically.

### 4.1. Checking Actual JDK Version and Flags

```bash
java -version
java -XX:+PrintFlagsFinal -version \
  2>&1 | grep -E 'UseContainerSupport|MaxHeapSize|MaxRAMPercentage|InitialRAMPercentage|ActiveProcessorCount'
```

`PrintFlagsFinal` output depends on JVM vendor/version, active flags, and output format. In production, inspect the running JVM process (not just a freshly spawned JVM with different flags).

### 4.2. Printing Container Detection Information

On supported HotSpot/JDK builds:

```bash
# Diagnostic command for a standalone JVM launched in a test environment.
java -XshowSettings:system -version
```

Output may include provider/cgroup limits; exact fields depend on JDK and OS. If a JDK fails to detect cgroups v2, it may size against host RAM, producing an inappropriate heap ceiling. **Upgrading to a supported JDK version** is usually safer than patching with undocumented flags; pin image digests/versions and test on real AKS node runtimes.

### 4.3. Cgroup v1 and v2

Linux may use **cgroup v1 or v2**, with different file/metric names. On cgroup v2, `memory.max` holds the limit in bytes or `max` (unlimited at that level); `memory.current` reports cgroup usage. However, do not rely on a hardcoded path like `/sys/fs/cgroup/memory.max` across all containers: filesystem mounts/namespaces and JDKs/runtimes can differ.

### 4.4. Memory Request Does Not Equal Memory Limit

In Kubernetes:

- **`requests.memory`** governs scheduling and resource guarantees; it is not the heap ceiling.
- **`limits.memory`** sets the cgroup/container ceiling as enforced by Kubernetes/runtime.
- **`requests.cpu`** is used by the scheduler for CPU reservation/shares.
- **`limits.cpu`** can impose CPU quota/throttling when constrained.

A Pod with `request.memory: 1Gi` and `limit.memory: 2Gi` can use above its request when the node has spare capacity; container-aware JVMs generally look at the **limit** and container environment, not just the request.

## 5. Sizing Example for a JVM in a 2 GiB Container

Suppose an AKS JVM container has a **2 GiB = 2048 MiB** memory limit, and the team wants to set heap at roughly **60%** of the container limit. This is a **starting point to test**, not a universal production setting.

```text
Container memory limit                 2048 MiB
Target maximum Java heap (60%)         ~1229 MiB
Remaining upper-level budget           ~819 MiB

Possible contributors to remainder:
  metaspace + code cache
  direct memory
  thread stacks
  JIT/GC/native structures
  malloc/memory mapping
  OS/runtime accounting + headroom
```

### 5.1. Percentage-Based Configuration

```bash
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0 -XX:+UseG1GC"
```

`-XX:MaxRAMPercentage=60.0` instructs the JVM to compute max heap as a share of **RAM the JVM considers available**; when the cgroup memory limit is detected properly, heap is ~60% of the limit. Do not assume every JDK/JVM gives exactly 1229 MiB: ergonomics, min/max constraints, and runtime flags can affect it.

### 5.2. Absolute Heap Cap Configuration

```bash
JAVA_TOOL_OPTIONS="-Xmx1200m -XX:+UseG1GC"
```

`-Xmx1200m` sets an explicit cap; if used across containers whose limits vary by environment, ensure this cap is never carried into a 1 GiB Pod. Avoid setting **both `-Xmx` and `MaxRAMPercentage` expecting both to act as dynamic limits**: an explicit max heap generally governs heap sizing and makes configuration confusing.

### 5.3. Should `-Xms` Equal `-Xmx`?

Not by default. `-Xms=-Xmx` can reduce some heap resizing and fits steady workloads, but it increases memory commitment/footprint at startup, reduces Pod density, and can waste memory on bursty workloads. For scale-to-zero/scale-out microservices on Azure, a moderate `-Xms` can benefit **memory efficiency**. Measure startup, GC pauses, RSS, CPU, and cost before deciding.

### 5.4. Easily Misunderstood JVM Percentage Flags

- `-XX:MaxRAMPercentage`: caps heap as a percentage of memory seen by the JVM.
- `-XX:InitialRAMPercentage`: influences initial heap sizing when no explicit `-Xms` is set.
- `-XX:MinRAMPercentage`: **not a universal "minimum heap percent"**; in modern HotSpot this flag relates to setting max heap on small-memory systems. Do not use it as a way to set Xms.
- `-XX:MaxDirectMemorySize`: sets the limit for JVM direct buffer memory where applicable; does not cover all native allocations.
- `-XX:MaxMetaspaceSize`: caps metaspace, though too low causes OOME.

### 5.5. Do Not Pick One Heap Ratio for Every Workload

A REST API using heavy native Netty buffers and connections may need a larger non-heap budget than a pure-Java batch job. In small containers, native overhead takes a significant share. In large containers, an overly large heap cap can hurt GC/latency/cost. **Measure allocations and native memory before locking in a ratio.**

## 6. CPU Limits and Their Impact on Garbage Collection

GC uses CPU too. A CPU-throttled application can respond slowly while GC lacks enough CPU time to keep pace, pushing up live heap occupancy or GC pressure.

### 6.1. CPU Request and CPU Limit

Kubernetes example:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "2"
    memory: "2Gi"
```

This is a **Kubernetes Pod container resources fragment**, not a complete manifest. `500m` reserves half a CPU core for scheduling; `limits.cpu: "2"` sets a quota up to 2 CPUs per runtime enforcement. Node core count and CPU quotas affect JVM ergonomics differently.

### 6.2. CPU Throttling

If a workload has brief CPU bursts, a 1-CPU quota can drive up `container_cpu_cfs_throttled_periods_total` (metric name depends on Prometheus/cAdvisor setup) even when average CPU usage is only 0.7 CPU. Those scheduler pauses can cause **tail latency** for both request threads and GC threads.

Do not see a long GC pause and immediately blame G1. Check:

- JVM CPU usage and container throttled periods/time.
- CPU requests/limits and processor count seen by the JVM.
- GC worker threads and runnable application threads.
- Host/node pressure and noisy neighbors.
- Request p99 broken down by Pod and throttling timestamps.

### 6.3. `ActiveProcessorCount`

HotSpot provides `-XX:ActiveProcessorCount=N` to override the processor count the JVM uses for certain ergonomics. It can affect GC worker pools and thread pools/frameworks consulting `availableProcessors()`. This is an **intentional tuning tool**, not a default flag for every service. Setting N above the real CPU quota can increase contention; setting it too low reduces throughput.

### 6.4. Choosing Scale-Up or Scale-Out?

If a service is CPU-bound, raising `limits.cpu`/instance size can reduce throttling; if the workload is stateless and parallelizes well, adding replicas helps too. Yet adding Pods increases **baseline heap, connection pools, cache memory, startup CPU, DB connections, and cost**. Compare **good requests/s per vCPU and cost** rather than looking only at single-instance latency.

## 7. Java Workload Types and GC Profiles

| Workload | Memory/GC Characteristics | Priority | Pitfalls |
|---|---|---|---|
| Java/Spring Boot REST API | Short-lived objects, thread pools, HTTP serialization | p95/p99 and good throughput | Heavy tiny allocations, CPU throttling |
| Batch ETL/analytics | Large heaps, large arrays, long-running loops | Throughput and total runtime | Long full GCs, harmless to users if within batch window |
| Message consumer | Bursty traffic, object queues, retries | Stable processing lag/idempotency | Unbounded in-memory queues |
| Reactive Netty service | Direct buffers, event loops | Low latency/low memory | Off-heap native/direct memory |
| JVM in serverless container | Cold starts, memory tiers, scaling | Startup and cost per request | Overly large Xms, eager initialization |
| Search/cache engine | Large live set, caching | Memory utilization + predictable pauses | Large heap/long-lived objects |

**There is no single best GC for every workload.** Collector choice depends on JDK vendor/version, allocation profile, latency SLO, heap size, CPU quota, and available memory headroom.

## 8. How Garbage Collection Works in Principle

GC manages Java objects that are no longer reachable. Modern HotSpot collectors employ strategies such as **generational collection, concurrent marking/relocation, evacuation, and compaction** with different trade-offs.

### 8.1. Young and Old Generations

Many applications allocate numerous short-lived objects (request DTOs, JSON fragments, temporary lists). Generational collectors exploit that pattern:

```text
New Java objects
       |
       v
Young generation (Eden / Survivor concepts)
       |
       +--> unreachable objects reclaimed
       |
       +--> surviving objects retained/promoted over time
                        |
                        v
                    Old generation
                        |
                        +--> long-lived caches/session/data structures
```

This is a conceptual model, not an identical layout across every collector or JDK version. For instance, ZGC has evolved generational support depending on JDK version.

### 8.2. Stop-the-World (STW)

An **STW pause** is an interval during which the JVM halts some—typically most—application threads to perform a GC/VM phase. A concurrent collector moves much work off STW pauses yet typically still has **short synchronization/pause points**. "Concurrent GC" does not mean "zero pause."

### 8.3. Throughput, Latency, and Footprint

| Concept | Goal | Trade-off |
|---|---|---|
| GC throughput | Share of time/CPU spent on application work | Throughput-oriented collectors/pauses |
| Pause latency | Pause duration per GC, often evaluated at p95/p99/max | Concurrent work can require extra CPU/memory |
| Footprint | Heap/native memory and RSS | Tight footprint can increase GC pressure |
| Allocation rate | Rate of object allocation | High rate raises young GC count, not always bad |
| Live set | Long-lived reachable data | Large live set near Xmx pressures GC |
| Headroom | Free space for allocation/relocation | Insufficient headroom can trigger expensive GC/OOME |

### 8.4. One GC Metric Is Not Enough

Rising GC frequency can simply reflect higher traffic while pauses stay short and SLOs hold. Conversely, a single 4-second full GC can break p99 latency and readiness probes. Examine **pause distribution, GC CPU time, allocation rate, old-gen occupancy, RSS/cgroup usage, application p99, and throughput** together.

## 9. Choosing a GC Collector: G1, ZGC, or Parallel?

HotSpot supports multiple collectors. **The JDK version is part of the choice**: LTS/vendor-specific builds can have different defaults and capabilities. The examples below target **HotSpot Java 17/21**; check `java -version` and release notes for your exact runtime before enabling a flag.

| Collector | Typical Goal | Strengths | Risks/Considerations |
|---|---|---|---|
| **G1 GC** | Balance throughput and pause times across many server workloads | Region-based, generational, adaptive; often a useful baseline | Pause target is a soft goal; mixed/full GCs can occur |
| **ZGC** | Low pauses and predictable latency when sufficient headroom exists | Highly concurrent phases, suits tail-latency-sensitive services | Concurrent CPU/memory overhead; may need different tuning/capacity |
| **Parallel GC** | Throughput/batch workloads | Parallel collection, strong throughput potential | STW pauses can be long; poor fit for tight API p99 |
| **Serial GC** | Small/simple JVM environments in specific configurations | Low overhead in suitable scenarios | Single GC thread; prone to long pauses as heap/load grows |

**Neither "G1 is always slow" nor "ZGC is always fastest" is true.** ZGC can improve pause p99 while increasing CPU; Parallel GC can finish batches faster under suitable conditions; each JDK/image's default collector should be verified.

### 9.1. What Does G1 GC Do?

G1 divides the heap into **regions**, prioritizing regions yielding high reclamation benefit within a pause target, combining concurrent marking and pause phases. It performs young collections and mixed collections when appropriate.

```bash
# HotSpot; test in staging before production:
java -XX:+UseG1GC -jar orders-api.jar
```

G1 is a practical starting point for many Java APIs when there is no evidence requiring another collector. However, if heap is too small, native buffers are large, or CPU is throttled, switching collectors will not cure the root cause.

### 9.2. ZGC and JDK Compatibility

```bash
# HotSpot build supporting ZGC:
java -XX:+UseZGC -jar orders-api.jar
```

In **JDK 21**, Generational ZGC can be selected in supported HotSpot builds via `-XX:+ZGenerational` alongside `-XX:+UseZGC`; in later JDK releases, ZGC defaults/behavior evolved. **Do not copy flags across JDK 17/21/newer releases without verifying support and actual mode.**

```bash
# Example for HotSpot JDK 21 supporting Generational ZGC:
java -XX:+UseZGC -XX:+ZGenerational -jar orders-api.jar
```

An unrecognized flag fails startup. Verify via `java -XX:+PrintFlagsFinal -version`, startup logs, and GC logs; record the active collector/mode in the run report.

### 9.3. Parallel GC

```bash
java -XX:+UseParallelGC -jar batch-worker.jar
```

For batch jobs without tight tail-latency SLOs, a throughput-oriented collector is worth considering. Still, if the job runs inside a tight Pod memory limit or low CPU quota, pauses and memory pressure must be checked.

### 9.4. Quick Decision Chart

```text
Is request p99 sensitive to GC pauses?
       |
       +-- No --> Benchmark default/G1 vs Parallel throughput
       |
       +-- Yes --> Start with G1 baseline
                        |
                        +-- SLO met, cost acceptable --> Keep
                        |
                        +-- GC proven dominant tail-latency cause
                                   |
                                   v
                              Benchmark ZGC
                              with sufficient CPU/memory headroom
```

**Switch collectors only after proving GC is a major bottleneck.** If p99 is slow due to SQL queries, connection pools, CPU quotas, or GC root scanning from excessive references, switching to ZGC may not be enough.

## 10. G1 GC Tuning: Set Goals, Do Not Force Numbers

G1 relies heavily on self-tuning ergonomics; start with **JVM-tuned defaults** and alter only a few parameters when backed by data.

### 10.1. `MaxGCPauseMillis` Is a Soft Goal

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar orders-api.jar
```

`200` is an **ergonomic pause-time target** (ms), **not a guarantee** every pause stays under 200 ms. The JVM balances work against pause goals; setting `MaxGCPauseMillis=5` merely because an HTTP SLO is 5 ms can spike collection frequency and CPU without achieving the target.

### 10.2. Do Not Pin the Young Generation Arbitrarily

`-Xmn` or fixed young-generation sizing flags can prevent G1 from resizing young space to meet its pause target. Without clear benchmark evidence, avoid overriding young-generation sizing. Frequent short young GCs are generally fine for short-lived objects; do not try to "minimize GC count" at all costs.

### 10.3. Signs G1 Is Struggling

- Young GC pauses repeatedly exceed target and correlate with request p99.
- Mixed collections drag on and old-gen occupancy fails to drop enough.
- **Humongous allocations** (objects large relative to region size) add pressure under G1 region semantics.
- Rare but very long Full GCs.
- To-space exhaustion / evacuation failures in logs.
- Rapid allocation/promotion when live set approaches max heap.

Inspect **allocation profile, object sizes, cache retention, heap sizing, and CPU headroom** before touching advanced flags like `G1HeapRegionSize` or IHOP thresholds.

### 10.4. Do Not Optimize for "Fewest GCs"

Suppose A has 20 young GCs/second at 4 ms each with 180 ms API p99; B has 2 GCs/second at 250 ms each with 850 ms API p99. If the p99 SLO is 500 ms, **A is better** despite higher GC frequency. Optimize for user impact and total cost, not event counts.

## 11. ZGC: When Is It Worth Using?

ZGC moves most collection work into concurrent phases to shrink STW pause lengths. It can help APIs requiring very low tail latency, especially when G1 GC demonstrably accounts for a significant share of p99.

### 11.1. Measure All Three Sides

When benchmarking G1 vs. ZGC, compare:

1. **HTTP p95/p99/p99.9 and SLO** under the same load mix.
2. **CPU per good request**, including background GC CPU.
3. **RSS/cgroup memory, allocation headroom, and cost**.

A collector with tiny pauses that burns extra CPU and triggers Pod throttling can still produce **worse end-to-end latency**.

### 11.2. Concurrent Collection Needs Headroom

With concurrent collectors, the application keeps allocating while GC processes objects. If allocation rate is too high, CPU quota too tight, or heap lacks headroom, GC may fall behind, causing **allocation stalls** or allocation failures. Do not simply raise `-Xmx` without checking native/cgroup ceilings.

### 11.3. Never Mix Collectors

A single JVM process selects only **a valid collector** per flag combination. Never pass both `-XX:+UseG1GC` and `-XX:+UseZGC` in the same deployment and guess which wins; startup may reject the configuration. When benchmarking, create separate profiles and review `JAVA_TOOL_OPTIONS`, startup args, and Helm variables.

### 11.4. Other Collectors

Shenandoah GC may exist in certain OpenJDK/vendor builds though not in every Azure base image; Parallel/Serial were covered above. **Stick to what your actual runtime supports** rather than listing collectors as "Azure-managed features."

## 12. GC Logs: The First Tool When Suspecting GC Slowdowns

In HotSpot **JDK 9+**, unified logging supports `-Xlog:gc...`. This is relatively lightweight in many environments, though overly verbose logging increases disk I/O, log volume/cost, and can add overhead.

### 12.1. Writing GC Logs to Stdout

```bash
java -Xlog:gc*:stdout:time,uptime,level,tags \
  -XX:MaxRAMPercentage=60 \
  -XX:+UseG1GC \
  -jar orders-api.jar
```

Container logs flow through the AKS/App Service/Container Apps log collector when logging is configured. **Do not assume all stdout automatically lands in Log Analytics**; verify Container Insights/agents/diagnostic settings and ingestion costs.

### 12.2. Rotating GC Log Files

```bash
java -Xlog:gc*,safepoint:file=/var/log/java/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders-api.jar
```

The file path must exist and be writable with sufficient quota and container filesystem permissions; writing to ephemeral disk loses logs when a Pod is replaced. Ship needed logs to centralized logging via an approved mechanism with **retention/cost** controls, and avoid unbounded volume mounts.

### 12.3. Signals in GC Logs

```text
[2026-11-20T...] [info][gc,start] GC(142) Pause Young ...
[2026-11-20T...] [info][gc,heap ] GC(142) Eden regions: ...
[2026-11-20T...] [info][gc      ] GC(142) Pause Young ... 72M->35M(...) 8.7ms
```

This is an **illustrative log**, not actual output from a JDK/container. Look for:

- Event type (young/mixed/full/concurrent).
- Pause duration and timestamp/uptime.
- Heap before/after and capacity.
- Frequency and promotion/old-gen occupancy.
- Safepoint data if enabled.
- Warnings when GC lacks headroom.

### 12.4. Java 8 Uses Different Syntax

JDK 8 builds prior to unified logging use flags such as `-XX:+PrintGCDetails` and `-Xloggc:...` depending on vendor/build. **Never copy `-Xlog:gc*` into Java 8 without checking**; prefer supported LTS JDKs and standardized base images.

### 12.5. Stopping at "Correlation" Is Not Enough

If an HTTP request took 1.2 seconds during a 10 ms GC pause, GC does not explain the rest. Correlate GC logs with **request traces, CPU throttling, database spans, and thread dumps**. Distinguish **GC pauses** from **other VM safepoint operations**.

## 13. Java Tools: `jcmd`, `jstat`, `jstack`, and JFR

These tools ship with **JDK distributions** or images; slim JRE/container images may lack `jcmd`/`jfr` or attach permissions. In production, JVM diagnostic access is sensitive: enforce least privilege, change tickets, time bounds, and avoid leaking secrets.

### 13.1. `jcmd`

```bash
# List Java processes in the current namespace/container.
jcmd -l

# Inspect heap overview when permitted by JVM/OS.
jcmd <pid> GC.heap_info

# Inspect flags actually used by the JVM process.
jcmd <pid> VM.flags
```

`<pid>` is a placeholder; do not paste it verbatim into a shell. `jcmd` may require the **same OS user/namespace** and an enabled JVM attach mechanism. Avoid casually sending `kill -QUIT` if app logging is unmanaged, as it can print dumps into logs.

### 13.2. `jstat`

```bash
jstat -gcutil <pid> 1000 10
```

For example, taking roughly 10 samples 1 second apart. Columns depend on JDK; check young/old occupancy and GC counts/times, not just `FGC`. A process in another Pod cannot attach automatically if container namespaces/security policies block it.

### 13.3. Thread Dumps

```bash
jcmd <pid> Thread.print
```

Thread dumps reveal blocked/waiting/runnable threads, deadlocks, and pool saturation. Many WAITING threads are **normal** in servers; do not treat every WAITING thread as a thread leak. Thread dumps may expose class/method names and sensitive context; store them only in authorized locations.

### 13.4. Java Flight Recorder

**JFR** captures event-level profiling (GC, allocations, locks, CPU, thread scheduling, I/O, etc.) with overhead often suitable for production when configured carefully. Create a sample recording:

```bash
jcmd <pid> JFR.start name=orders-profile settings=profile duration=120s filename=/tmp/orders-2min.jfr
```

Or enable at startup:

```bash
java -XX:StartFlightRecording=duration=120s,filename=/tmp/startup.jfr,settings=profile \
  -jar orders-api.jar
```

JFR files can contain **class names, stack traces, method references, endpoints, allocation data, and internal details**. Never upload raw recordings to public channels; restrict access and retention. `settings=profile` can incur higher overhead than `default`; keep durations short, verify disk space, and measure impact.

### 13.5. Inspecting JFR with Java Mission Control

**Java Mission Control (JMC)** analyzes recordings to uncover allocation hotspots, GC pauses, CPU method activity, and threads/locks. Distinguish the **allocation profile** from the **retained heap graph**: where most objects are allocated is not necessarily where objects are held long-term.

### 13.6. Choosing Tools by Symptom

| Symptom | First Diagnostic Step |
|---|---|
| p99 spikes, GC suspected | GC logs + JFR GC events + request traces |
| High CPU | JFR CPU profiling + thread analysis + CPU throttling |
| Heap steadily climbing | Heap occupancy trend, class histogram, retained heap analysis |
| RSS rising while heap stays flat | NMT/direct-buffer/native metrics |
| Thread count growing | Thread dump + thread metrics |
| Slow startup | Startup JFR, class loading/JIT, dependency initialization |
| 403/SQL timeouts after deploy | Azure networking/RBAC/dependency tracing; likely unrelated to GC |

## 14. Native Memory Tracking (NMT) When Heap Does Not Explain RSS

**Native Memory Tracking** is a HotSpot feature that records **JVM-managed native memory allocations** (JVM-dependent), useful when process RSS is high while heap used stays modest.

### 14.1. Enabling NMT Requires Process Restart

```bash
JAVA_TOOL_OPTIONS="-XX:NativeMemoryTracking=summary"
```

Or `detail` for finer granularity if needed; both carry **CPU/memory overhead and different output**. Do not leave `detail` enabled indefinitely in production without evaluating overhead.

### 14.2. Viewing Statistics

```bash
jcmd <pid> VM.native_memory summary
```

NMT categorizes memory into Java Heap, Class/Metaspace, Thread, Code, GC, Compiler, Internal, Symbol, Arena, etc. depending on JDK/version. To compare before/after:

```bash
jcmd <pid> VM.native_memory baseline
# Run the target workload, then:
jcmd <pid> VM.native_memory summary.diff
```

### 14.3. NMT Does Not Equal Total RSS

NMT primarily observes native allocations tracked by HotSpot/JVM and **cannot be treated as a complete profiler of all third-party native allocations, mapped files, page cache, or cgroup charges**. Allocations made by external libraries outside JVM tracking may be incomplete. Cross-check OS process maps/smaps and container metrics when needed.

### 14.4. When Thread Memory Is Abnormal

If NMT shows rising Thread reserved/committed memory, check **thread count and stack usage**. Tune thread pool sizes, avoid spawning threads per request, use appropriate async I/O or concurrency limits, and lower `-Xss` only after testing worst-case stack depth.

### 14.5. Direct Buffer Leaks

For Netty/ByteBuffer, inspect direct memory gauges, pooling, and buffer release behavior. `OutOfMemoryError: Direct buffer memory` differs from `Java heap space`. Some native libraries manage memory outside the direct buffer cap; profile the relevant allocator rather than merely raising `-XX:MaxDirectMemorySize`.

## 15. Heap Dumps, Class Histograms, and Data Safety

### 15.1. Heap Dump on Java Heap OOME

```bash
java -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/dumps \
  -jar orders-api.jar
```

Heap dumps can contain **passwords, tokens, customer PII, request payloads, and application objects**. Enable only under an incident/data handling policy with sufficient disk, encrypted storage, access control, and retention. Heap dumps are often huge, can fill ephemeral disk, and **are not guaranteed to be written on kernel `OOMKilled`**.

### 15.2. `jcmd GC.heap_dump` Has Cost

```bash
jcmd <pid> GC.heap_dump /dumps/orders-heap.hprof
```

This command can cause pauses/overhead and consume substantial disk; depending on flags/JDK, it may trigger a full GC to dump live objects. Never run it simultaneously across the entire production fleet under overload. Follow a runbook and canary a single Pod with adequate resource headroom.

### 15.3. Class Histogram

```bash
jcmd <pid> GC.class_histogram
```

A class histogram shows instance counts and bytes per class at a point in time; **it does not prove what holds references**. Analyze retained graphs/GC roots from a heap dump when suspecting a leak, keeping pause risk and data sensitivity in mind.

### 15.4. Common Leak Categories

- Caches lacking eviction/TTL or with unbounded key growth.
- Static collections holding objects indefinitely.
- `ThreadLocal` values not cleaned up in thread pools.
- Unreleased listeners/subscriptions/`CompletableFuture` references.
- ClassLoader leaks during dynamic reloads/plugins.
- Unbounded queues where producers outpace consumers.
- Unreleased direct buffers/Netty resources.
- Unclosed JDBC connections/streams/sockets creating native/resource pressure.

**Do not treat raising `-Xmx` as a universal fix**: increasing heap merely delays when a leak hits the ceiling, raises costs, and can lengthen full GC cycles.

## 16. Allocation Profiling and Improving Java Code

If an app allocates 2 GB of temporary objects per second, the collector must process heavy allocation churn. Optimizing allocations **can reduce GC CPU and memory**, yet blind optimization easily harms readability or introduces bugs.

### 16.1. Measure Allocation Hotspots First

JFR allocation events/profilers can reveal:

- Methods allocating excessive `String`/`byte[]`/DTO instances.
- JSON parsing/serialization creating temporary buffers.
- Mapping database rows into objects.
- Regex compilation on hot paths.
- Log string concatenation at disabled log levels.
- Heavy in-memory collection copies/streams.

Evaluate **bytes allocated per successful request**, not just total bytes/sec; rising traffic can explain higher total allocations while per-transaction efficiency remains fine.

### 16.2. Anti-Pattern: Eager Log String Concatenation

```java
// Avoid building large strings when DEBUG is disabled and the logger still evaluates the expression.
logger.debug("Order payload: " + serializeOrder(order));
```

Replace with structured/lazy logging:

```java
if (logger.isDebugEnabled()) {
    logger.debug("Processing orderId={}", order.getId());
}
```

This snippet uses an SLF4J-style logger. Do not log raw order payloads/PII/tokens for allocation tuning; the primary win is **avoiding unnecessary serialization**, not just string concatenation.

### 16.3. Avoiding Unbounded Caches

```java
// Bad idea: memory grows for every customer key ever accessed.
Map<String, Order> foreverCache = new ConcurrentHashMap<>();
```

Replace with a **bounded cache** with max size/weight, eviction/TTL, and metrics; specific cache libraries (such as Caffeine) require project-appropriate dependencies and versions. Validate **cache hit rate, retention, eviction, stale-data policy**, and heap usage under peak traffic.

### 16.4. Do Not Optimize into a Functional Bug

Hand-rolled object pooling for short-lived objects can worsen contention, retention, and bugs compared to GC; generational collectors already handle short-lived allocations well. Optimize only after profiling identifies a substantial hotspot, and always back changes with regression tests.

## 17. AKS: Configuring JVM CPU/Memory and Kubernetes

AKS uses Kubernetes to manage Pods and Deployments. Because the JVM runs inside a container, it is subject to **container resource limits**, cgroup policies, and node pool scheduling. Tuning involves at least two independent layers: **Java flags** and **Kubernetes resources**.

### 17.1. Sample Deployment Manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: java-api
          image: <approved-acr>/orders-api:<pinned-image-tag>
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "2Gi"
          env:
            - name: JAVA_TOOL_OPTIONS
              value: >-
                -XX:MaxRAMPercentage=60
                -XX:+UseG1GC
                -Xlog:gc*:stdout:time,uptime,level,tags
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 6
      terminationGracePeriodSeconds: 45
```

**This is an illustrative manifest**; a real project needs namespaces, images, ports, application endpoints, policies, identities, ingress/services, and ConfigMaps/secrets. `<approved-acr>` and `<pinned-image-tag>` are placeholders. Never deploy this directly to production without verifying **Spring Boot Actuator health probes** are enabled and real paths exist. Values like 5s/10s/36/45s are examples; measure startup and workload behavior before choosing them.

### 17.2. `JAVA_TOOL_OPTIONS`

The JVM reads `JAVA_TOOL_OPTIONS` in supported launchers/embedding modes, often helpful when container entrypoints invoke Java. However, **flags from the environment may not apply as expected if the entrypoint overrides args**. Verify startup logs/commands and `jcmd VM.flags` on the live JVM. Never accidentally place credentials/tokens in `JAVA_TOOL_OPTIONS` since environment variables can appear in process diagnostics.

### 17.3. ~60% Max Heap Does Not Prove 2 GiB Is Enough

A Kubernetes 2Gi memory limit plus JVM MaxRAMPercentage 60 sets only a **relative heap limit**. Measure direct buffer memory, metaspace, thread count, code cache, RSS, and cgroup usage under peak traffic. If 800 MiB remains yet native memory uses 900 MiB, the Pod still OOMs. Reduce native memory usage or raise the container limit appropriately rather than blindly shrinking heap.

### 17.4. CPU Limits in AKS Affect GC

If `limits.cpu: 500m` is set while load demands 2 cores for JIT + GC + request threads, CPU throttling can severely degrade p99. Tune per SLO and node capacity; some workloads omit CPU limits by policy, but that requires understanding multi-tenant fairness, cost, and quotas. Do not treat "remove CPU limits" as a blanket best practice for every cluster.

### 17.5. Proper Probes Prevent Restart Storms

A transient STW GC can cause a probe timeout. If liveness is overly aggressive, Kubernetes restarts the Pod before it recovers; right after restart, classloading and JIT warm-up spike CPU and memory and trigger another timeout—creating a **restart loop**.

Distinguish:

- **Startup probe:** allows longer initialization without being interrupted by liveness/readiness checks where supported.
- **Readiness probe:** signals whether a Pod should receive traffic; when unready, it is removed from service routing per Kubernetes semantics.
- **Liveness probe:** determines whether the process needs restarting; use only for evidence of unrecoverable stalls/hangs.

Do not tie liveness directly to every external dependency (Azure SQL/Key Vault/Service Bus) such that a shared dependency blip restarts the entire fleet. Readiness and circuit breakers should reflect the service's degraded-operation design.

## 18. Spring Boot Startup, Readiness, and Graceful Shutdown

### 18.1. JVM Warm-Up and JIT

A Java service may need to:

1. Load classes and initialize frameworks.
2. Load the Spring application context and validate configuration.
3. Initialize database connection pools and HTTP clients.
4. Warm JIT code paths under traffic.
5. Populate bounded caches.
6. Reach steady memory and latency levels.

Do not equate "JVM is listening on port 8080" with "the app is warmed up and ready for peak traffic."

### 18.2. Spring Boot Health Endpoints

When using Spring Boot Actuator with configured liveness/readiness probes:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Endpoints need exposure, configuration, and security aligned with your Spring Boot version. Never expose `/actuator/heapdump`, `/env`, `/configprops`, or sensitive diagnostic endpoints to the public Internet. Only required health details should be exposed internally.

### 18.3. Graceful Shutdown

During Kubernetes scale-down or rollouts:

```text
SIGTERM to container
    |
    +--> stop accepting new traffic/readiness false
    +--> finish in-flight requests / commit offsets where safe
    +--> close DB pools, HTTP clients, telemetry exporters
    +--> exit within terminationGracePeriodSeconds
```

Applications must handle SIGTERM and server graceful shutdown per framework/runtime. If a Pod receives `SIGKILL` due to cgroup OOM or expired grace period, `finally` blocks and shutdown hooks are not guaranteed to run. For Service Bus workers, implement **idempotency + at-least-once handling**, never assuming every message was ACKed.

### 18.4. Java Framework Settings

Spring Boot configures graceful shutdown and lifecycle timeouts by version. Never copy a property from Boot 2.x to Boot 3.x without checking docs and testing deployment. Across health probes and shutdown, the goal is **never routing unready Pods into the load balancer** and **never killing Pods momentarily paused by GC**.

## 19. HPA, VPA, Cluster Autoscaler, and JVM Impact

Scaling replicas or size is part of performance tuning, though each mechanism solves a different problem.

### 19.1. Horizontal Pod Autoscaler (HPA)

HPA typically scales Pod replicas based on CPU utilization or custom/external metrics via configured adapters. If `requests.cpu` is set far below real usage, relative CPU utilization looks artificially high and HPA scales out unnecessary Pods. If CPU is high due to GC thrashing, scaling out may help temporarily while inflating total memory/cost and hiding heap/cache bugs.

### 19.2. Vertical Pod Autoscaler (VPA)

VPA can recommend or adjust requests per policy, and in some modes/versions requires Pod recreation. Never deploy VPA auto-updates alongside a CPU-based HPA without coordinated design; avoid autoscalers fighting each other or causing disruptive restarts.

### 19.3. Cluster Autoscaler

Cluster Autoscaler adds or removes nodes when scheduling capacity demands it under constraints; it does not tune `-Xmx` for containers. An oversized Pod memory request can remain unschedulable even if runtime heap is small. **Requests drive bin packing, node pool SKUs, and cost.**

### 19.4. Queue-Based Workload Autoscaling

For Service Bus consumers, external queue-length metrics or KEDA-based scaling can be used in supported patterns. Monitor **processing rate, oldest message age, DLQ, and downstream Azure SQL capacity**; scaling to 100 workers when SQL has a tight connection cap can drop total throughput due to contention.

### 19.5. Heap Cost Under Scale-Out

Suppose 6 Pods each have 1.2 GiB committed heap despite a small live set; scaling to 18 Pods multiplies fleet-wide heap reservations/committed memory substantially. When comparing scale-up vs. scale-out, evaluate **cost per good transaction, node utilization, connection pressure, and failure isolation**.

## 20. Azure App Service: Optimizing JVM by Plan and Runtime

Java apps can run on **Azure App Service** as a managed runtime stack or custom container depending on configuration, plan, and OS. App Service abstractions differ from AKS: resource quotas, plan instance sizes, scale-out, and startup flag injection depend on the hosting model.

### 20.1. Managed Java Runtime vs. Custom Container

| Model | JVM Flags/Configuration | What to Verify |
|---|---|---|
| App Service managed Java runtime | Startup settings/platform configuration per OS/stack/version | JVM version, supported settings, plan memory, restarts |
| App Service custom container | Docker image entrypoint/`JAVA_TOOL_OPTIONS`/App Settings | Container memory constraints, image/JDK, logs |
| App Service plan scale-out | Multiple plan worker instances | Instance memory, shared plan contention, autoscale |

Do not assume an environment variable or option for a Linux custom container works identically on a Windows managed Java runtime. **Verify how App Service actually launches Java.**

### 20.2. App Service Plan Is a Critical Resource Boundary

Multiple apps can share the same App Service Plan instances. One Java app consuming heavy heap/native memory can impact sibling apps on the same plan. Under memory pressure, evaluate **total plan memory, workers/instances, and co-located apps**, not just a single web app's heap.

### 20.3. Sizing Before Scaling the Plan

1. Review App Service metrics: memory/CPU, HTTP queue, restarts, and per-instance health as supported.
2. Review Application Insights requests/dependencies/p95.
3. Review app-level JVM heap/GC/native metrics.
4. Check connection pools, threads, and native memory.
5. Choose Plan SKU upgrade, scale-out, or JVM tuning based on the bottleneck.

Do not double the Plan SKU if the bottleneck is SQL queries or an unbounded memory leak.

### 20.4. Warm-Up and Slot Swaps

Deployment slots and slot swaps can minimize interruption when configured properly, yet **JVM warm-up, cached state, slot-specific settings, Key Vault references, and database connections** must be checked. Do not treat slot swap as a silver bullet that "automatically eliminates all cold starts." An app with an oversized `Xms=Xmx` can consume extra warm-up time/memory or pressure the shared plan.

### 20.5. Logs and Dumps on App Service

GC logs, JFR, and heap dumps must be collected via platform-supported mechanisms respecting access and retention policies. App Service filesystem paths, quotas, and per-instance lifecycles differ from AKS; do not hardcode `/dumps` assuming persistent volumes exist. Heap dumps contain PII/secrets; never expose unauthenticated diagnostic endpoints.

## 21. Azure Container Apps: Memory Tiers, Revisions, and Scaling

**Azure Container Apps** runs containerized workloads with platform-managed CPU/memory resources, revisions, and scaling; the JVM still operates inside its container budget.

### 21.1. Similar Principles, Different Operational Mechanics

When sizing Container Apps CPU/memory, select combinations supported by your active workload profile/plan. **Do not assume every CPU/memory pairing is valid.** JVM flags like `MaxRAMPercentage` still require validation via JDK/container detection.

### 21.2. Scale-to-Zero and Startup Latency

For scale-to-zero workloads, **JVM cold starts** affect request latency and cost; oversized heap/Xms, classloading, Spring context initialization, network auth, and dependency warm-up all contribute. Weigh minimum replicas against availability/SLOs and cost; if the first request must return within 200 ms, scale-to-zero may not fit unless startup meets that target.

### 21.3. Revision Rollouts

Changing a JVM flag creates a new container revision/config change per platform mechanics. Use **traffic splitting/canary/revision health** where supported, comparing p95/GC/memory before and after. Do not shift 100% of traffic to a revision that has not passed warm-load testing merely because the container reports healthy.

### 21.4. Secrets and Identity

When fetching config from Azure Key Vault via managed identity at startup, network or identity failures can cause slow cold starts or restart loops. **Do not fetch Key Vault secrets on every request** unnecessarily. Separate GC diagnostics from dependency startup/connection errors.

## 22. Azure Virtual Machines: When Deeper Tuning Is Available

On Azure VMs, you control the OS/JDK, memory, CPU, GC logs, NMT, profilers, and disk layout far more directly than on managed PaaS, while also owning patching, identity, scaling, backups, and security.

### 22.1. Lack of Cgroup Limits Can Mislead JVM Sizing

When running Java directly on a VM without container limits, the JVM inspects **VM physical memory**; yet a VM may also run SQL agents, monitoring daemons, reverse proxies, and multiple Java processes. Setting `MaxRAMPercentage=75` on multiple processes can overcommit total memory. With multiple JVMs on one VM, **set `-Xmx` against the VM's total resource budget**.

### 22.2. NUMA and Instance Sizes

On large/multi-socket/NUMA VMs, memory locality and GC thread placement can affect performance. Do not enable NUMA flags blindly from generic "best practice" guides; benchmark on the exact VM SKU/OS/JDK. On multi-tenant hosts, burstable VM vCPU credits or host contention can also impact CPU throughput.

### 22.3. Disks for Dumps and Logs

Heap dumps, JFR files, and GC logs can grow very large. Plan disk paths, encryption, I/O budgets, retention, and export; avoid filling the OS disk or treating temporary disks as persistent. When a VM Scale Set replaces instances, local-disk logs/dumps are lost unless centrally collected.

### 22.4. Service Configuration

If using `systemd` or a process supervisor, version-control JVM args/`JAVA_TOOL_OPTIONS`, memory limits, and restart policies rather than editing manually during incidents and forgetting IaC. Watch for runtime flags being overridden by entrypoints or `systemd` environment files.

## 23. Dockerfiles and Production Java Container Images

A reliable image needs **pinned JDK versions, a non-root user, minimal dependencies, observability**, and verifiable runtime flags.

### 23.1. Sample Dockerfile

```dockerfile
# Replace placeholders with approved, pinned runtime image/digest.
FROM <approved-jre-21-base-image>

WORKDIR /app
COPY --chown=10001:10001 orders-api.jar /app/orders-api.jar
USER 10001:10001

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60 -XX:+UseG1GC -Xlog:gc*:stdout:time,uptime,level,tags"
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
```

**This cannot be built verbatim** because `<approved-jre-21-base-image>` is a placeholder. Pick a security-approved JDK/JRE base image and pin its digest/tag; if `jcmd`/JFR diagnostics are needed, slim runtime images may require dedicated debug provisioning workflows.

### 23.2. Do Not Hardcode Heap Around One Memory Request

If dev sets a 1Gi container limit and prod sets 4Gi, `MaxRAMPercentage` helps when the JVM detects cgroups accurately, though if native memory scales non-linearly with traffic, benchmarking is still required. One static sizing assumption does not fit every plan or instance size. Override values via controlled deployment/Helm configuration under review.

### 23.3. JDK and Security Patching

Pin **JDK major/build versions** to prevent GC behavior drift across environments, while planning regular **security patches**. JDK upgrades can alter GC defaults, TLS libraries, cgroup detection, and JIT optimizations; run load tests and compare metrics before production rollout.

### 23.4. JDK Runtime vs. Diagnostic Tools

Minimal Java runtimes shrink attack surface and image size but may omit `jcmd`, `jfr`, shells, and `nslookup`. Design **ephemeral debug containers or pre-approved diagnostic images** with proper permissions; never run production services as root just to attach a profiler.

## 24. Azure Monitor, Application Insights, Prometheus, and JVM Telemetry

Effective observability connects **JVM internals** to **user request SLIs** and **Azure infrastructure signals**.

```text
JVM/Spring Boot
    |     |
    |     +--> OpenTelemetry / Application Insights traces
    |             requests, dependencies, exceptions
    |
    +--> Micrometer/JMX JVM metrics
          heap, non-heap, GC pause, threads, CPU
             |
             v
      Metrics exporter / Prometheus scrape / Azure Monitor integration
             |
             v
Azure Monitor / Log Analytics / Azure Monitor workspace
             |
             +--> Workbook: request latency + GC + RSS
             +--> Alerts: error-rate, OOM, throttling, leak pattern
             +--> Grafana dashboard (when integrated)
```

### 24.1. Azure Sources

| Source | What It Measures | Notes |
|---|---|---|
| **Application Insights** | Java requests, exceptions, dependencies, traces per instrumentation | Does not automatically include all JVM/native/cgroup metrics without instrumentation |
| **Azure Monitor Metrics** | Platform CPU/memory/restarts per resource and supported features | Units, aggregation, and delay differ from JMX |
| **AKS Container Insights** | Container/node logs and certain performance inventory/metrics per config | Capabilities vary by agent/collection mode |
| **Managed Prometheus + Azure Monitor workspace** | Prometheus-style metrics from cluster/app exporters | Requires configuring scraping, ingestion, labels, RBAC |
| **Azure Managed Grafana** | Visualizes Prometheus/other sources | Viewers need datasource permissions |
| **Log Analytics/KQL** | Collected logs/GC events | Does not automatically tabulate raw JVM metrics |
| **JFR/heap dump** | JVM-level diagnostics | Does not replace continuous metrics; sensitive and adds overhead |

### 24.2. Common JVM Metrics

Depending on Micrometer/Prometheus naming/version:

```text
jvm_memory_used_bytes{area="heap"}
jvm_memory_committed_bytes{area="heap"}
jvm_gc_pause_seconds_count
jvm_gc_pause_seconds_sum
jvm_threads_live_threads
process_cpu_usage
process_resident_memory_bytes
```

**These metric names are illustrative across certain exporters** and are not guaranteed to appear identically in every Micrometer/OTel/Prometheus setup. Check actual metric discovery/exposition before building Grafana panels on nonexistent metrics.

### 24.3. Spring Boot Actuator + Micrometer

With appropriate dependencies and configuration, Spring Boot Actuator exposes health/metrics. A typical Prometheus endpoint is:

```text
GET /actuator/prometheus
```

Prerequisites: Micrometer Prometheus registry/Actuator added and endpoint exposure/security configured. **Never expose exporter endpoints publicly** if metrics reveal sensitive details; restrict scraping to authorized networks and bound label cardinality and runtime overhead.

### 24.4. OpenTelemetry Does Not Automatically Capture Every Metric

Java OpenTelemetry instrumentation/exporters can send JVM/runtime metrics depending on agent/version/config, yet that does not automatically yield exact GC pause histograms in Log Analytics. Verify **schema, exporter, sampling, collection interval, and backend** before building SLOs.

### 24.5. Stdout GC Data Needs Labeling

With multiple Pods, a log line `GC(42)` is scoped only to that process and uptime, not a global GC ID. Log collectors should attach **cluster, namespace, workload, pod, container, image version, and timestamp**. In Workbooks, separate old and new Pods across rollouts rather than treating pre- and post-restart "GC counts" as one continuous series.

## 25. Dashboards: Connecting GC, Memory, and CPU Throttling to API Latency

A Java performance Workbook/Grafana page should display **business impact first** and JVM internals second.

```text
Orders API — production, southeastasia, last 60 minutes
┌────────────────────────┬────────────────────────┬────────────────────┐
│ Good requests/s        │ Error rate / timeouts  │ HTTP p95/p99       │
├────────────────────────┴────────────────────────┴────────────────────┤
│ CPU utilization / throttled time   | Container working set / limit   │
├────────────────────────┬────────────────────────┬────────────────────┤
│ Heap used / committed  │ GC pause p95/max       │ GC CPU / time %    │
├────────────────────────┴────────────────────────┴────────────────────┤
│ Thread count | Native/direct memory | JVM old-gen occupancy         │
├────────────────────────┬────────────────────────┬────────────────────┤
│ Pod restarts / OOMKilled│ Deployment version    │ Data freshness     │
└────────────────────────┴────────────────────────┴────────────────────┘
     Drill-down: trace ID / GC log segment / JFR / runbook / cost
```

### 25.1. Aligning on a Shared Timeline

When spotting an HTTP p99 spike at 10:03, align GC pauses around 10:03, CPU throttling, request queues, SQL duration, and Pod restarts. Traces, GC logs, and Prometheus have different **scrape intervals, timestamps, clock skew, and ingestion latencies**; inspect a wide enough window and avoid inferring causality solely because two dots sit close together.

### 25.2. Normal Average CPU Yet High Throttling

An average CPU usage of 70% of the limit does not rule out burst throttling. When `container_cpu_cfs_throttled_seconds_total` rises, examine **throttled time / CPU periods / API request latency** per Pod, especially during traffic/JIT/GC bursts. If platform metrics omit throttling, use Managed Prometheus/cAdvisor or another collector.

### 25.3. Low Heap Used Yet High RSS

Place `heap used` alongside `heap committed`, NMT categories, and `container working set`. If heap remains 800 MiB while cgroup usage climbs from 1.2 → 1.9 GiB, investigate native/direct memory, threads, sidecars, and page cache before adjusting Xmx.

### 25.4. GC Pauses from Counters and Summaries

A Prometheus exporter often exposes `jvm_gc_pause_seconds_count` and `jvm_gc_pause_seconds_sum` (depending on setup). You can query:

```promql
# GC pause events/second (within the selected scope).
rate(jvm_gc_pause_seconds_count{application="orders-api"}[5m])

# Total GC pause wall-clock seconds/second, not CPU usage.
rate(jvm_gc_pause_seconds_sum{application="orders-api"}[5m])
```

Do not label the second ratio "GC CPU %," because **total pause wall-clock duration** does not accurately reflect concurrent GC worker CPU. Parallel GC threads run concurrently, making wall-clock seconds and CPU-seconds distinct. Verify exact metrics from exposition.

### 25.5. p95 GC Pause from Histograms

If the exporter genuinely provides `jvm_gc_pause_seconds_bucket` histograms with appropriate labels, you can query:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(jvm_gc_pause_seconds_bucket{application="orders-api"}[5m])
  )
)
```

**`jvm_gc_pause_seconds_bucket` is not guaranteed to exist.** Some exporters emit only count/sum or different SLO buckets, and instrumentation may track different pause types. Reliable percentiles require fine-grained histogram buckets and proper calculation; never compute an average from count/sum and call it p95.

### 25.6. Data Freshness on Dashboards

When a Pod is OOMKilled, JVM metrics may vanish. Dashboards should surface **missing data / Pod terminated** rather than displaying `heap used=0` as "optimized." Separate "zero GC events" (potentially normal) from "missing exporter data."

## 26. KQL and Log Correlation on Azure

The following KQL queries are examples when **workspace-based Application Insights** populates tables like `AppRequests` and `AppDependencies`. Table/column names may vary by instrumentation, SDK, and workspace config; check the schema explorer before running. KQL does not directly query all Prometheus metrics without an appropriate query integration.

### 26.1. API Latency and Errors in 5-Minute Bins

```kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize
    Requests = count(),
    Failed = countif(Success == false),
    P95Ms = percentile(DurationMs, 95),
    P99Ms = percentile(DurationMs, 99)
  by bin(TimeGenerated, 5m)
| extend ErrorPct = iff(
    Requests > 0, 100.0 * todouble(Failed) / Requests, real(null))
| order by TimeGenerated asc
```

**`Success=false` does not necessarily match the business error SLI** (how client 4xx, 429, timeouts, and sampling are counted must be defined). To compare across collector versions, check `DurationMs` units and trace sampling weights.

### 26.2. SQL/Service Bus Dependency Latency

```kusto
AppDependencies
| where TimeGenerated >= ago(2h)
| where AppRoleName == "orders-api"
| summarize
    Calls = count(),
    Failures = countif(Success == false),
    P95Ms = percentile(DurationMs, 95)
  by Target, Type
| order by P95Ms desc
```

If `Target` contains full URLs with PII/order IDs, sanitize or canonicalize before sharing. If SQL p95 rises alongside request p99 while GC pauses stay flat, **investigate SQL/connection pools first**.

### 26.3. GC Log Ingestion

If stdout GC logs are shipped to a Log Analytics table, the schema may be `ContainerLogV2` or another table depending on collection mode. The KQL below is illustrative only:

```kusto
ContainerLogV2
| where TimeGenerated >= ago(1h)
| where PodName has "orders-api"
| where LogMessage has "gc"
| project TimeGenerated, PodName, ContainerName, LogMessage
| top 100 by TimeGenerated desc
```

**This query depends on actual tables and columns.** Do not treat `LogMessage has "gc"` as a rigorous pause-duration parser, since unified logging formats, tags, and versions vary. For accurate pause p95, use **structured metrics/JFR or a tested parser**.

### 26.4. Resource/Pod Correlation

Correlate Java metrics/traces with Azure resources via **service name, environment, pod UID/name, container ID, deployment revision, and image digest**, not just the `orders-api` string. Pod names change on restarts; queries must align timelines properly.

## 27. Designing Load Tests to Evaluate GC Tuning

JVM tuning is meaningful only when **comparing before/after on an equivalent workload**, not running a toy microbenchmark.

### 27.1. Variables to Hold Constant

- Same Java source/build/dependencies and **container image/JDK**.
- Same AKS node SKU, CPU/memory requests/limits, and cluster background load where possible.
- Same API endpoints, request mix, payload size/shape, and authentication flow.
- Same Azure SQL/Service Bus tiers/connection limits or clearly scoped test doubles.
- Same concurrency/RPS/ramp-up/duration and warm-up protocol.
- Same sampling/metrics collection, dashboard time range, and comparison method.
- Same database dataset size and cache state per test design.

If you upgrade the database tier at the same time, results cannot attribute p99 gains to the collector.

### 27.2. Test Phases

```text
Preflight
  validate JDK/container flags and resource limits
        |
Warm-up
  app startup, JIT, caches, connection pools
        |
Steady state
  realistic request mix at target load
        |
Ramp-up / peak
  gradually increase concurrency and throughput
        |
Soak test
  30-120 min or workload-defined duration for leaks/GC trends
        |
Failure/recovery
  restart a Pod, pause dependency, traffic burst, scale event
        |
Analysis
  compare user SLO, GC, RSS/native, CPU, OOM, cost
```

**Soak test** duration must match the leak rate or workload cycle; 30 minutes is unlikely to catch a 10 MiB/day leak. Exclude warm-up metrics when computing steady-state baselines.

### 27.3. Open-Loop vs. Closed-Loop Load

**Closed-loop tests** keep virtual users fixed and wait for each response before sending the next; when the server slows down, total request rate drops and hides overload. **Open-loop tests** dispatch requests at a predetermined arrival rate, revealing queuing/timeouts at saturation—provided the load generator is not bottlenecked and backpressure is controlled. Match the model to SLOs without generating traffic meant to crash production subscriptions.

### 27.4. Standardized Result Table

| Signal | Baseline G1 | ZGC Trial | How to Read |
|---|---:|---:|---|
| Good RPS | 390 | 405 | Near 400 target |
| API p95 | 230 ms | 215 ms | Slight improvement |
| API p99 | 720 ms | 440 ms | Clear improvement |
| Max GC pause | 180 ms | 12 ms | Lower pause; verify event types |
| CPU cores used | 1.2 | 1.7 | Substantial CPU increase |
| cgroup memory peak | 1.65 GiB | 1.85 GiB | Less headroom |
| OOMKilled | 0 | 0 | Needs longer soak |

**These numbers are completely illustrative**, not real Azure benchmarks. ZGC improved p99 while consuming more CPU and memory; if cost or throughput is the primary goal, G1 may still be preferable. Decide based on **SLOs, capacity, and cost**, not a single column.

### 27.5. Statistical Discipline

- Run multiple trials and report **median/range/confidence** as appropriate; one run is insufficient.
- Collect enough samples for p99—never compute p99 from 20 requests.
- Keep windows and units fixed; avoid average-of-percentiles.
- Discard runs skewed by unrelated deployments or database maintenance.
- Record image digest, flags, memory/CPU limits, region/VM SKU, and timestamps.

### 27.6. Regression Gates

A CI performance gate might fail if:

- p99 significantly exceeds target under representative load.
- `OOMKilled` or a native memory leak appears.
- Good throughput drops below the acceptance threshold.
- CPU cost/good transaction rises past the approved cap.
- GC pauses rise against baseline and correlate with user impact.

Never let a noisy shared CI runner block production releases based on an unisolated 30-second performance test.

## 28. Memory Leak and Retention Indicators

### 28.1. Normal Heap "Sawtooth"

Heap used naturally rises during allocation and drops after GC, forming a sawtooth pattern:

```text
Heap used
 ^
 |      /\       /\       /\       /\
 |     /  \     /  \     /  \     /  \
 |____/    \___/    \___/    \___/    \___
 |
 +------------------------------------------> time
```

A sawtooth alone **does not prove a leak**. Track the **post-GC live set** across many cycles under steady load. If the post-collection baseline keeps climbing without reaching steady state, suspect retained objects.

### 28.2. Leaks Can Happen Outside the Heap

```text
Heap post-GC live set: stable ~600 MiB
Direct/native memory: grows 200 -> 800 MiB
Container usage: grows 1.0 -> 1.8 GiB
Observed result: OOMKilled at 2 GiB limit
```

This is an illustrative example; investigate Netty buffers, JNI/mmap, threads, direct memory pools, and NMT. GC tuning cannot fix a native allocator leak.

### 28.3. Do Not Conclude Leaks During Warm-Up

During the first few minutes, Spring/ORM/JIT/caches naturally grow heap and committed memory as they initialize. Compare retained baselines **after warm-up** across identical traffic phases; a true leak continues climbing across cycles at constant cache cardinality and workload.

### 28.4. Practical Leak Detection

1. Confirm workload and deployment version are steady.
2. Collect post-GC heap used/old-gen, committed, RSS, and direct memory metrics.
3. Verify request rate, cache key cardinality, and thread count.
4. Run a soak test or observe a production canary with headroom.
5. For heap leaks, take a class histogram/JFR and consider a heap dump per policy.
6. Trace GC roots/retained objects with an analyzer.
7. For native leaks, use NMT and allocator-specific diagnostics.
8. Fix the root cause, run a regression soak, and compare costs.

## 29. Optimizing Thread Pools and Connection Pools

Many "GC problems" are actually **excessive concurrent work**.

### 29.1. HTTP Thread Pools

In servlet containers, each request may occupy a worker thread. If DB latency spikes and the thread pool balloons, stack/native memory and request queues both grow; raising heap will not make the database faster. Configure **max threads and request queues/backpressure** based on load testing.

### 29.2. HikariCP / JDBC Connection Pools

A Java service with 50 database connections per Pod, scaling from 5 to 30 Pods, creates a theoretical **1,500 connections**—potentially exceeding Azure SQL tier, network, or identity limits. Shrinking heap will not help. Size pools based on **DB capacity, query duration, concurrency, retries, and total fleet size**.

### 29.3. Service Bus Consumer Concurrency

Raising `maxConcurrentCalls` or worker counts can lift initial throughput, but if handlers hold large payloads without backpressure, **live heap set and in-memory queues** grow simultaneously. Use bounded processing queues, idempotency, controlled prefetch/batch sizes, and monitor processing lag and DLQ.

### 29.4. Reactive Does Not Automatically Mean Low Memory

Reactive I/O reduces threads blocked on I/O in suitable use cases, yet buggy code can cause **buffer accumulation, direct-memory pressure, and event-loop blocking**. Switching from servlet to reactive is not an automatic "GC fix."

### 29.5. Virtual Threads (JDK 21) and Memory

Java 21 provides **virtual threads** (per supported release) to represent many concurrent blocking tasks more efficiently than platform threads in suitable scenarios. However, virtual threads **do not make CPU or database throughput infinite**; each task still consumes heap/stack chunks and downstream capacity. Enforce concurrency limits, monitor pinning/locks/blocked operations with JDK tooling, and never spawn millions of tasks without backpressure.

## 30. Spring Boot Startup and Memory on Azure

### 30.1. Separating Startup Phases

When a Pod takes 80 seconds to become ready, inspect:

- Image pull and container start.
- JVM initialization/class loading.
- Spring context and bean creation.
- Database migrations and connection validation.
- Key Vault/config retrieval.
- JIT warm-up and cache initialization.
- Readiness checks.

Break down phases using startup logs, traces, and JFR; never assume "GC makes Spring Boot start slowly" when GC logs show no significant pauses.

### 30.2. Reducing Startup Dependency Work

Some startup tasks can initialize lazily or warm up in the background when semantics allow. Yet if endpoints depend on schema migrations or secrets, readiness must not report true before minimum dependencies are satisfied. Balance **fast startup** with **accurate readiness**.

### 30.3. CDS/AppCDS and JVM Class Metadata

Class Data Sharing (CDS) and AppCDS can improve startup and class-loading footprint in compatible JDKs/builds/configs. Benchmark their actual effect; do not treat CDS as a cure for live-heap leaks or SQL latency.

### 30.4. Native Image Is a Different Architectural Choice

GraalVM Native Image carries distinct trade-offs in startup/footprint, reflection configuration, and runtime memory management; **HotSpot G1/ZGC flags do not apply identically to native images**. This lesson focuses on the **HotSpot JVM**, so adopting native image requires an independent benchmarking and compatibility effort.

### 30.5. Cold Starts and Azure Plans

On Azure Container Apps with scale-to-zero, or App Service/Functions modes subject to cold starts, optimizing initialization time can noticeably improve UX. Conversely, if a workload runs 24/7 already warmed, shaving 5 seconds off startup may matter far less than cutting p99 from 1 s to 400 ms.

## 31. Securing JVM Diagnostics on Azure

While tuning the JVM, many diagnostic tools expose internal process state. This is not purely a performance topic—it is also about **data security and operational authorization**.

### 31.1. Artifacts to Classify

| Artifact | May Contain | Controls |
|---|---|---|
| Heap dump `.hprof` | Plaintext credentials, secrets, tokens, customer PII, request payloads | Encryption, restricted access, retention |
| JFR `.jfr` | Stack/method/class names, I/O events, endpoints, internal metadata | Scope/retention/redaction policy |
| Thread dump | Class names, stack traces, operation context | Masking, restricted access |
| GC logs | Uptime, memory sizes, process behavior | Prevent log flooding, manage lifecycle |
| Environment variables | App settings, possibly secrets if poorly designed | Never dump all env values |
| JVM system properties | Endpoints, config, sometimes secrets | Avoid `-Dpassword=...`; restrict access |

### 31.2. Never Enable Unsecured Remote JMX

JMX can expose runtime internals and management operations. A public JMX port without authentication and TLS is a severe risk. On AKS/VMs, prefer **local diagnostics/secured exporters** accessed over approved network segments and identities, never exposing JMX on a public load balancer.

### 31.3. Diagnostic Permissions in Kubernetes

Running `jcmd`/JFR may require Pod exec, ephemeral debug containers, attach capabilities, and JDK tools. Enforce **Kubernetes RBAC/Entra integration, auditing, and just-in-time privileges** rather than adding `privileged: true` or running containers as root for diagnostics. Time-bound and resource-limit debug sessions.

### 31.4. Heap Dumps Under Incident Policy

One workflow:

1. Security/incident owner approves taking the snapshot.
2. Record Pod/image version, timestamp, and expected size.
3. Pick one canary replica with sufficient disk/volume headroom.
4. Write the dump to encrypted, private storage.
5. Restrict read access strictly to authorized responders.
6. Redact findings in tickets/reports; never attach raw dumps publicly.
7. Delete artifacts per retention policy and audit access.

### 31.5. Java Flags Can Leak via Process Metadata

Avoid passing passwords/JWTs via `-Dsecret=...` command-line flags or `JAVA_TOOL_OPTIONS`. Use **managed identities, Azure Key Vault references, or secure runtime injection** appropriate to the Azure service, and control who can inspect process environments/configs.

## 32. Optimizing JVM Cost and Azure Capacity

JVM tuning is not just about lowering `heap used`; the economic goal is **good throughput and stability** at acceptable cost.

### 32.1. Related Cost Drivers

| Component | Cost Impact | Action |
|---|---|---|
| AKS nodes/VMs | vCPU/RAM and node-hours | Right-size instances/nodes, requests/limits |
| App Service Plan | Tier/instance count | Sizing, caching, warm-up, scale-out |
| Container Apps | CPU/memory usage, replicas/workload profile | Reduce cold starts and overprovisioning |
| Azure SQL/Service Bus | Tier, throughput, connection pressure | Tune pools and backpressure |
| Log Analytics/managed metrics | Ingestion/retention/queries | Sampling, label hygiene, data lifecycle |
| Diagnostic artifacts | JFR/dump/log storage and egress | Rotate, encrypt, enforce retention |
| Resilience | Extra replicas/headroom | Align with SLOs and RTO |

### 32.2. A Cost Comparison Exercise

Suppose:

```text
Configuration A
  8 Pods x 2 GiB limit
  400 good RPS
  measured monthly node and observability cost: C_A

Configuration B
  6 Pods x 3 GiB limit
  430 good RPS
  measured monthly cost: C_B

Compare:
  cost per million successful requests
  p95/p99
  OOM/restart rate
  operational headroom
```

Reducing Pod count alone may not cut the bill if node SKUs stay unchanged or VPA/HPA keeps reserved capacity high. Compare **actual Azure Cost Management** data over matching baselines; VM/AKS/App Service/Container Apps prices and log fees vary by region and tier, so avoid relying on fixed "standard unit prices."

### 32.3. Heap vs. Density Trade-Off

Larger heaps reduce GC pressure for some workloads but inflate memory requests and may force extra nodes. Smaller heaps raise Pod density yet risk high GC CPU or OOMs, creating costs from retries and incidents. Find the **performance–cost sweet spot** through testing.

### 32.4. Observability Overhead

Continuous `debug/trace` GC logging, unbounded JFR profiling, high-cardinality exporter labels, and automatic heap dumps on every OOME can drive up storage, I/O, and ingestion bills. Keep **signals that inform decisions**, cap data volume, and enforce retention. Never disable mandatory security/compliance logs solely to cut costs.

### 32.5. Tuning Changes Resource Ratios

A collector needing more CPU can push AKS into larger node sizes; a lower Xms can fit more replicas yet increase startup GC. Evaluate **total fleet cost + SLO + recovery**, not just one Pod's CPU%.

## 33. An Auditable JVM Tuning Process

Maintain a **tuning record** for each change, stored alongside incident/performance reviews (in an approved system):

```yaml
# Illustrative analysis record; not an Azure configuration.
experimentId: jvm-orders-20261120-01
service: orders-api
environment: staging
region: southeastasia
jdk: "OpenJDK 21 build recorded by CI"
container:
  memoryLimit: "2Gi"
  cpuLimit: "2"
baseline:
  gc: G1
  maxHeap: "60% of detected container memory"
candidate:
  gc: ZGC
  flags: ["-XX:+UseZGC"]
load:
  requestMix: "recorded synthetic profile v3"
  duration: "after warmup + steady + soak"
metrics:
  - goodRps
  - httpP99Ms
  - gcPauseP99Ms
  - memoryPeakMiB
  - cpuThrottledRate
  - oomKills
decision: "pending measurement"
reviewer: "orders-platform"
```

### 33.1. Running the Closed Loop

1. **Goal:** e.g., cut HTTP p99 from 850 to 500 ms without exceeding a pre-approved cost cap.
2. **Baseline:** record actual JVM/JDK flags, memory/CPU constraints, request mix, and resource metrics.
3. **Hypothesis:** GC STW pauses drive a large share of p99, rather than SQL latency.
4. **Candidate:** change a single flag group (e.g., G1 → ZGC) while holding everything else constant.
5. **Validate:** verify startup/JDK compatibility and confirm active collector in runtime logs.
6. **Benchmark:** warm-up, steady, peak, soak, and failure phases.
7. **Analyze:** compare SLOs, GC, native memory, CPU throttling, and cost.
8. **Canary:** small rollout with rollback ready; watch user impact.
9. **Decide:** keep or revert, documenting rationale and risks.
10. **Update runbooks:** reflect active settings, dashboards, triggers, and version.

### 33.2. Negative Results Are Still Valuable

If switching collectors leaves p99 unchanged while raising CPU by 25%, **revert** and record that GC is not the primary bottleneck. That is a successful experiment because it disproves a hypothesis; never massage metrics to justify an initial preference.

### 33.3. A JVM Change Often Requires a Deployment Rollout

Changing `JAVA_TOOL_OPTIONS` typically requires a **restart/revision rollout**; do not assume environment variables apply dynamically to running processes. Verify zero-downtime strategy, health probes, PodDisruptionBudgets/replicas, and deployment windows.

## 34. Runbook 1: AKS Pod `OOMKilled` While Heap Is Not Full

**Symptom:** Java API container has a 2Gi memory limit, Pod restarts with `Reason: OOMKilled`, while prior heap metrics showed only ~900 MiB.

### 34.1. Triage and Evidence Gathering

1. Confirm **Pod/container name, namespace, image digest, last termination reason, and timestamp**.
2. Inspect `kubectl describe pod` events/`lastState.terminated.reason`, memory limits, and restart count.
3. Inspect container **memory working set/cgroup usage** before OOM, not just heap.
4. Inspect process RSS, heap used/committed/max, metaspace, direct memory, and thread count.
5. Check whether the Pod runs sidecars or additional processes.
6. If NMT is enabled, check category growth against baseline.
7. Check for spikes from batch payloads, direct buffers, logging, large classloaders, or thread explosions.
8. Check node pressure/evictions separately; `Evicted` due to node pressure differs from container `OOMKilled`.
9. Apply targeted mitigation: bounded caches, thread pools, buffer releases, or balanced Xmx/limit adjustments.
10. Verify under load/soak tests, canary deploy, and monitor OOM restarts.

### 34.2. Reference Kubernetes Commands

```bash
kubectl -n orders get pods -l app=orders-api -o wide
kubectl -n orders describe pod <pod-name>

kubectl -n orders get pod <pod-name> \
  -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'

# Requires Kubernetes metrics API/metrics-server.
kubectl -n orders top pod <pod-name> --containers
```

`<pod-name>` is a placeholder. `kubectl top` shows only current point-in-time metrics if supported, **not history prior to a crash**. Centralized monitoring is needed to inspect peak leading indicators.

### 34.3. Common Mistakes

- Raising `-Xmx` from 1.2 to 1.8 GiB inside a 2Gi limit without checking native headroom.
- Treating exit code 137 as sole proof of OOM.
- Expecting `HeapDumpOnOutOfMemoryError` to always run during a Linux kernel SIGKILL.
- Lowering memory requests without adjusting limits to "save money," worsening node bin-packing/evictions.
- Deleting dumps/logs before forensic approval and root-cause analysis.

### 34.4. Recovery Criteria

Zero `OOMKilled` events across representative peak/soak tests, memory high-watermark safely below budget with headroom, GC/application p99 within SLO, and costs within policy.

## 35. Runbook 2: `OutOfMemoryError: Java heap space`

**Symptom:** logs record `java.lang.OutOfMemoryError: Java heap space`; committed/max heap sits near Xmx, and GC runs continuously without reclaiming enough space.

### 35.1. Ordered Investigation

1. Confirm actual Xmx and JDK/container detection from process flags.
2. Inspect post-GC heap live set, old-generation occupancy, and allocation rate.
3. Inspect payload sizes, cache cardinality, queues, and retained session state.
4. If approved, capture JFR/class histogram/heap dump from **one** instance.
5. Analyze dominant classes, GC roots, and retained references; distinguish cache warm-up from leaks.
6. Determine whether the memory cap fits the real workload or is simply too low.
7. Fix bounded data structures or raise heap/container memory with evidence.
8. Run regression/soak tests and compare GC, latency, and cost.

### 35.2. Heap Retention Example

```java
// Illustrative anti-pattern (not production code).
final Map<String, byte[]> payloadCache = new ConcurrentHashMap<>();
void handle(String orderId, byte[] payload) {
    payloadCache.put(orderId, payload); // No eviction.
}
```

If each payload is 100 KiB and 100,000 keys are retained long-term, the payload data alone approaches **~9.8 GiB**, excluding object/map overhead. Raising Xmx from 2Gi to 4Gi only postpones the OOME. Replace with a size/weight/TTL-bounded cache or store in Blob/DB per business requirements.

### 35.3. When Is Raising Xmx Reasonable?

If the heap live set is stable with no leak, the workload genuinely needs more memory than budgeted, and the container has **sufficient native headroom**, raising Xmx (alongside container limit/node sizing if needed) can reduce GC frequency and OOMEs. Always test throughput/latency/committed memory and cost; never push Xmx right up against the cgroup ceiling.

### 35.4. Recovery Evidence

Post-GC heap does not grow indefinitely under steady load, zero OOMEs occur, API/worker SLOs hold, peak traffic has margin, and the fix has an assigned owner and regression test.

## 36. Runbook 3: Severe p99 Spikes Coinciding with GC Pauses

**Symptom:** HTTP p99 jumps from 400 → 1,600 ms, and GC logs show frequent 200–500 ms pauses.

### 36.1. Isolating the Root Cause

1. Verify application/request p99 has sufficient sample volume rather than coming from tiny sample buckets.
2. Align GC pause timestamps with request latencies and traces.
3. Inspect GC types: young/mixed/full, frequency, heap before/after, and promotion pressure.
4. Check CPU throttling/CPU quotas and node resource pressure.
5. Check request mix, payload sizes, allocations, traffic bursts, and recent deployments.
6. Check dependency latencies to rule out SQL or Service Bus as the primary driver.
7. Check heap live set/cap and native headroom.
8. Test allocation/heap or collector adjustments in staging, changing only one variable at a time.
9. Canary the version that improves p99 while keeping CPU/memory cost bounded.
10. Update alert thresholds and runbooks.

### 36.2. Tune in the Right Order

**Start from root causes**, typically in this order:

- Eliminate large or unnecessary allocations.
- Fix cache retention and unbounded queues.
- Ensure CPU quotas are not causing severe throttling.
- Set appropriate heap and native memory headroom.
- Only then experiment with collector/GC tuning.

If GC pauses are tiny while HTTP p99 is huge, switching GCs is not the priority. If GC demonstrably dominates p99, benchmark ZGC vs. G1.

### 36.3. Do Not Lower `MaxGCPauseMillis` Indefinitely

G1's pause target is a soft goal, not an SLA. Setting it too low can inflate GC work/CPU without improving overall p99. Use test data to select thresholds and flags rather than copying values from a "tuning cheat sheet."

## 37. Runbook 4: CPU Throttling Slowing GC/JIT and APIs

**Symptom:** latency rises during traffic bursts; average CPU usage looks moderate, yet throttled periods/time climb.

### 37.1. Steps

1. Check actual Pod CPU requests/limits in manifests and runtime.
2. Measure CPU throttled periods/time per Pod/node from appropriate metrics.
3. Inspect JVM `availableProcessors()`/`ActiveProcessorCount` and GC worker behavior.
4. Inspect JFR CPU hotspots and thread contention.
5. Check request worker counts and DB/Service Bus concurrency.
6. Test raising CPU quota, removing quota per policy, or scaling replicas (one variable at a time).
7. Observe good RPS, p95/p99, GC CPU, and cost.
8. Verify node sizing/quotas and AKS HPA behavior.
9. Retain the winning config and add alerts for user-impacting throttling.

### 37.2. Do Not Misinterpret CPU Cores

`requests.cpu=500m` does not mean the JVM is capped at 0.5 CPU at all times, and `limits.cpu=2` does not mean two dedicated physical cores. These are Kubernetes reservation and quota semantics. **CPU throttling correlated with request p99** matters far more than a standalone CPU percentage.

## 38. Runbook 5: Rising RSS with Unexplained NMT/Direct Memory

**Symptom:** container memory climbs from 1.0 to 1.9 GiB over 2 hours while post-GC heap/old-gen stays steady around ~700 MiB.

### 38.1. Diagnosis

1. Compare committed/used heap against process RSS and cgroup usage.
2. Check NMT summary/diff if enabled.
3. Check thread count, `jvm_threads_live_threads`, and thread dumps.
4. Inspect direct buffers/pooling, Netty/TLS/mmap, and native JNI libraries.
5. Check OS page cache, file I/O, container sidecars, and GC logs.
6. Correlate memory growth with payload sizes, concurrency, or deployment version.
7. Enable native-specific profilers in staging if NMT misses the allocations.
8. Fix resource lifecycles/close handling or set bounded direct-memory limits.
9. Compare RSS high-watermark and performance; do not only tweak Xmx.

### 38.2. NMT Cannot Account for 100% of Native Memory

A native library calling `malloc` outside HotSpot tracking may not appear completely in NMT. When NMT categories fail to explain RSS, inspect process maps/allocators, cgroup file cache, and sidecars. **Never conclude no leak exists just because NMT reports look flat.**

## 39. Runbook 6: Slow Startup or Restart Loop After Rollout

**Symptom:** deploying a new version on AKS/App Service/Container Apps delays readiness, Pods loop through restarts, and latency rises.

### 39.1. Triage

1. Check whether image digest, JDK version, or flags changed.
2. Compare startup/readiness/liveness thresholds against actual startup duration.
3. Inspect memory requests/limits, Xms/Xmx, CPU limits, and startup throttling.
4. Inspect GC logs and startup classloading/JIT/JFR where authorized.
5. Check DB migrations, Key Vault/Entra tokens, DNS/private endpoints, and app config errors.
6. Check HPA/scale-out/revision/slot behavior and how many instances are starting simultaneously.
7. Do not hastily disable all probes; adjust the startup window properly.
8. If the release causes an outage, roll back or forward-fix per the change plan.
9. Compare warm-start/cold-start SLIs and cost, and add startup tests.

### 39.2. When Probes Misread an STW Pause

Tight liveness thresholds can kill a Pod via SIGTERM/SIGKILL while the JVM is momentarily paused. Distinguish:

- **JVM OOME**: Java-level allocation failure.
- **OOMKilled**: cgroup/kernel kill.
- **Liveness kill**: kubelet restarts the container due to probe failures.
- **Normal rollout termination**: Pod replaced during deployment.

All four share the symptom "Pod restarted," yet each has a different runbook and fix.

## 40. Case Study: Cutting p99 and `OOMKilled` for Orders API on AKS

### 40.1. Context

The Orders Platform team runs **Spring Boot 3.x on HotSpot JDK 21** across 6 AKS replicas, each container with a 2 GiB memory limit and 1 CPU core limit. The Java app uses Azure SQL via HikariCP and the Azure Service Bus SDK. At peak traffic:

```text
Traffic                  420 requests/second
HTTP p95                 310 ms
HTTP p99                 1,400 ms
Java heap max            ~1.54 GiB (example of 75% setting)
Heap used at snapshot    900 MiB
Container working set    up to ~1.95 GiB
GC pause p99             75 ms
CPU throttling           elevated during bursts
Restart reason           OOMKilled on two Pods
```

**All figures are hypothetical**, intended to illustrate diagnostic reasoning rather than real Azure benchmarks.

### 40.2. Initial Analysis

Three key clues:

1. **900 MiB heap used does not explain 1.95 GiB container usage** → inspect committed heap, native memory, and sidecars.
2. **75 ms GC pause p99 does not explain a 1.4 s HTTP p99** → inspect SQL, CPU throttling, and thread queues.
3. **A 1-core CPU limit at 420 RPS peak** → could be a bottleneck, but cross-check throttled metrics and request traces.

### 40.3. Data Gathering

The application team:

- Checks `kubectl describe pod` and Pod OOM event timestamps.
- Verifies `-Xmx`/`MaxRAMPercentage` and HotSpot container detection.
- Reviews GC logs: young/mixed/full counts, max pauses, and post-GC heap.
- Captures NMT/JFR on a **staging replica** with controlled overhead.
- Inspects JVM threads, Hikari pool, and Netty buffer metrics.
- Reviews App Insights SQL dependency p95 and Service Bus operations.
- Correlates cgroup memory and CPU throttling with p99.

### 40.4. Finding the Root Cause

Suppose evidence reveals:

```text
Heap live set                stable ~650-850 MiB
Hikari connection pool       50 per Pod, many blocked threads
Direct buffers              rising with excess prefetch
Container memory peak       near limit
CPU throttling               high at load bursts
GC pauses                   moderate, not dominant
Azure SQL dependency p95    900 ms during peak
```

**Root cause hypothesis**: service concurrency exceeds database capacity; blocked requests hold objects, threads, and buffers longer, native memory climbs, and some containers OOM. GC is absorbing pressure but **is not the primary cause**.

### 40.5. Intervening in Order

**Change A – Bound concurrency:**

- Size total Hikari pool/concurrency to Azure SQL capacity.
- Bound Service Bus prefetch and handler concurrency.
- Enforce bounded queues and request backpressure policies.
- Re-benchmark; check good RPS, SQL p95, thread counts, and memory.

**Change B – Tune heap/headroom:**

- Test reducing max heap share from 75% → ~60% of 2 GiB after confirming live set.
- Measure native headroom and GC behavior; if heap becomes cramped and full GCs rise, revert.
- If real native demand stays high, raise container limits/instance sizes with cost evaluation.

**Change C – CPU quota/replicas:**

- Benchmark raising CPU limits or adjusting HPA settings within quotas/node capacity.
- Track throttling, API p99, GC CPU, and cost/transaction.
- Never allow unbounded scale-out while SQL remains bottlenecked.

**Change D – Collector:**

- Keep G1 if GC pauses do not dominate p99.
- Benchmark ZGC only if GC still clearly impacts p99 after the fixes above.

### 40.6. Illustrative Benchmark Results

| Metric | Baseline | After Changes A–C | Target |
|---|---:|---:|---:|
| Good RPS | 385 | 425 | >= 400 |
| HTTP p95 | 310 ms | 205 ms | <= 250 ms |
| HTTP p99 | 1,400 ms | 530 ms | <= 800 ms |
| GC pause p99 | 75 ms | 60 ms | Fits tail SLO |
| Container peak memory | 1.95 GiB | 1.55 GiB | Leaves headroom |
| OOMKilled/soak test | 2 | 0 | 0 |
| SQL p95 | 900 ms | 290 ms | Improved |

These **are not measured experimental results**. They illustrate a core lesson: targeted optimization can substantially improve p99 without switching collectors by reducing concurrency pressure, native memory, and CPU throttling.

### 40.7. Production Rollout

1. Run staging load tests with memory/CPU and an Azure SQL tier matching production.
2. Soak long enough for native leaks or queue buildup to surface.
3. Canary a subset of traffic/replicas, keeping rollback config and image digests ready.
4. Monitor App Insights SLOs, GC logs, working set, CPU throttling, SQL p95, and Service Bus DLQ.
5. If p99 or OOMs rise, roll back or forward-fix per runbook; never blindly raise Xmx to mask symptoms.
6. Post-rollout, update resource requests/limits and cost per good transaction.
7. Write an incident/postmortem review, adding performance regression tests and dashboard alerts.

### 40.8. Reusable Lesson

**Heap, GC, CPU, native memory, and downstream concurrency must be tuned as one system.** A single metric rarely suffices. On Azure, node/plan SKUs, network latency, connection limits, autoscaling, and cost matter just as much as JVM flags.

## 41. Practice Exercises

### Exercise A — Classifying Java Process Memory

**Prompt:** a JVM Pod has Xmx 1.2 GiB, heap used 850 MiB, metaspace 130 MiB, direct buffers 300 MiB, 400 OS threads, and container memory ~1.8 GiB.

**Task:** list at least five non-heap memory contributors and explain why heap used does not equal cgroup usage.

**Passing criteria:** distinguishes used/committed heap, metaspace, thread stacks, direct buffers, code cache, native libs, and OS/file cache without double-counting overlapping metrics.

### Exercise B — Sizing a 2 GiB Container

**Prompt:** Pod limit is 2Gi and the team tests `MaxRAMPercentage=60`.

**Task:** estimate max heap, remaining native budget, and what must be verified in JDK/cgroup detection.

**Solution guide:** ~1229 MiB heap and ~819 MiB remainder before runtime adjustments; verify actual JVM max heap flags and container detection.

### Exercise C — Distinguishing Requests and Limits

**Prompt:** `request.memory=1Gi`, `limit.memory=2Gi`; memory working set is 1.7 GiB.

**Task:** answer whether the Pod breached its hard limit, what scheduling/capacity risks exist, and which limit the JVM follows.

**Solution guide:** below the 2Gi limit yet above the request; node placement, eviction, and QoS class matter, and JVM sizing depends on verifying cgroup limit detection.

### Exercise D — G1 or ZGC?

**Prompt:** G1 p99 GC pause is 60 ms, API p99 is 1.2 s, and SQL dependency p95 is 900 ms.

**Task:** propose investigation steps before switching to ZGC.

**Solution guide:** GC pauses do not explain most of the latency; inspect SQL/connection pools/CPU throttling and examine JFR/traces before benchmarking collectors.

### Exercise E — HotSpot Java 21 GC Logs

**Prompt:** set up GC logging for a Java 21 app to stdout or rotating files.

**Task:** explain how to align log timestamps with request p99, cap log volume, and compare young/mixed/full pauses.

**Solution guide:** `-Xlog:gc*` with tags/time/uptime plus collection labels and retention; parse according to JDK version format.

### Exercise F — Distinguishing Java OOME and `OOMKilled`

**Prompt:** a Pod exits with 137, no `OutOfMemoryError` logs appear, and `kubectl describe` reports `Reason: OOMKilled`.

**Task:** explain why a heap dump may not be generated and how to find the cause.

**Solution guide:** kernel SIGKILL from cgroup limit; inspect historical memory, native/sidecar usage, and requests/limits; `HeapDumpOnOutOfMemoryError` is not guaranteed to execute.

### Exercise G — Enabling NMT

**Prompt:** post-GC heap is flat, yet RSS grows by 500 MiB over 45 minutes.

**Task:** explain how to enable NMT summary, take baseline/diff, and what NMT cannot see.

**Solution guide:** enable at startup, run `jcmd VM.native_memory baseline/summary.diff`, and cross-check process RSS/cgroup usage and native libraries outside HotSpot accounting.

### Exercise H — Thread Explosion

**Prompt:** a service jumps from 100 to 2,000 OS threads after a release; native memory and p99 climb.

**Task:** inspect thread pools, `jcmd Thread.print`, stack memory, and concurrency bounds.

**Solution guide:** locate pool leaks or unbounded thread creation, favor bounded pools/backpressure, and do not rely solely on shrinking `-Xss`.

### Exercise I — Direct Buffers

**Prompt:** a Netty service has a steady 700 MiB heap yet containers repeatedly OOM.

**Task:** distinguish `MaxDirectMemorySize` from total native memory and explain how to check resource release.

**Solution guide:** monitor direct buffer pools and native allocators, NMT/Netty metrics, ensure ref-counted buffers are released, and load test.

### Exercise J — CPU Throttling

**Prompt:** an AKS Pod has CPU limit 500m and request 100m; burst latency is high while average CPU usage is 300m.

**Task:** explain CPU CFS throttling, how to inspect throttled periods, and how to benchmark quotas/replicas.

**Solution guide:** bursts can exhaust quota despite a low average; compare request latency, GC CPU, and throttled time, and scale with node/SQL capacity in mind.

### Exercise K — Probes and GC Pauses

**Prompt:** 700 ms GC pauses cause the liveness endpoint to time out, triggering continuous Pod restarts.

**Task:** tune startup/readiness/liveness probes and distinguish a transient pause from a deadlock.

**Solution guide:** configure appropriate startup probes/timeouts, use readiness for traffic routing, reserve liveness for unrecoverable states; test under load rather than disabling all probes.

### Exercise L — Before/After Load Testing

**Prompt:** test `G1` and `ZGC` on Java 21 with identical 60% heap cap, 2Gi Pod, and 2 CPU cores.

**Task:** design test phases, fixed load, sampling, SLOs, and cost checks; record JDK build/flags.

**Solution guide:** warm-up, steady, peak, soak, and failure phases across multiple runs; compare good RPS, HTTP p99, GC pauses, RSS/CPU throttling, and cost.

### Exercise M — Evaluating Leaks

**Prompt:** heap sawtooths 400→900→450 MiB steadily for 10 minutes vs. another test where post-GC heap climbs 450→550→700 MiB over 1 hour.

**Task:** distinguish normal patterns from suspicious retention and list what else is needed before concluding.

**Solution guide:** measure after warm-up under constant workload, track old-gen live set trend, cache keys, allocation/retained heap, and extend soak duration if needed.

### Exercise N — JFR in Staging

**Prompt:** profile a 100-second Spring Boot startup.

**Task:** use JFR duration/settings to inspect classloading/JIT/dependencies and store recordings safely.

**Solution guide:** `-XX:StartFlightRecording` or `jcmd JFR.start` with filename, duration, and access controls; never publish heap/JFR artifacts publicly.

### Exercise O — HPA and Heap Commitment

**Prompt:** HPA scales 5→25 Pods with Xms=Xmx=1.5 GiB per Pod; API latency drops while node cost surges.

**Task:** evaluate Xms/replica, CPU/memory requests, total connection pools, and cost per transaction.

**Solution guide:** scale-out multiplies fleet footprint; benchmark lower Xms and pool bounds while preserving SLOs and headroom.

### Exercise P — Azure App Service

**Prompt:** two Java apps share an App Service Plan; App A's native RSS grows after a release and App B slows down.

**Task:** investigate shared plan capacity, per-app usage, and weigh splitting plans/scaling vs. fixing the leak.

**Solution guide:** do not blindly raise App B's Xmx; inspect plan contention, process RSS, heap/native metrics, and deployment history.

### Exercise Q — Container Apps Cold Start

**Prompt:** Container Apps scales to zero and the Java process takes 40 seconds to boot; faster response is needed.

**Task:** identify startup/JIT/context/Key Vault contributors and weigh min replicas vs. cost.

**Solution guide:** benchmark warm vs. cold, break down startup phases, evaluate min replicas or image/runtime optimizations, and do not assume ZGC cures cold starts.

### Exercise R — Spring Boot + Azure SQL

**Prompt:** scaling App Service replicas from 4 to 16 with a 40-connection Hikari pool each overloads Azure SQL.

**Task:** compute theoretical max connections, choose pool/concurrency/scaling policy, and project memory.

**Solution guide:** theoretical max is 640 connections if all pools fill; lower per-instance pool size or scale SQL capacity with evidence, checking timeouts/latency.

### Exercise S — Heap Dump Security

**Prompt:** an engineer wants to upload a production `.hprof` file to a public issue tracker for support.

**Task:** assess secrets/PII risks and outline a safe forensic workflow.

**Solution guide:** never upload publicly; use encrypted private storage, access approvals, retention, redacted findings, and sanitized artifacts.

### Exercise T — Incident Review

**Prompt:** production hits `OOMKilled` with normal GC logs, high CPU throttling, and rising Azure SQL p99.

**Task:** write an incident timeline, hypotheses, remediation/rollback, monitoring improvements, and ownership.

**Solution guide:** separate JVM/non-heap/container/dependency symptoms; re-measure under representative load and update alerts; never blame the collector solely because a Java process was killed.

## 42. Self-Check Questions

**1. Why not start optimization with `-Xmx`?** Because p99/throughput may be dominated by SQL, Service Bus, CPU throttling, or native memory; you need SLOs and a baseline first.

**2. How do Java heap used and committed differ?** Used is heap space holding objects per metrics, while committed is memory reserved by the JVM for the heap; committed can exceed used.

**3. Does `-Xmx` cap container RSS?** No. It caps the Java heap per JVM semantics; metaspace, direct buffers, stacks, and native memory sit outside it.

**4. What is Metaspace?** A native memory region holding class and classloader metadata in HotSpot.

**5. Why does thread explosion create memory pressure?** Each OS thread allocates a stack and native overhead alongside CPU scheduling and context-switching overhead.

**6. Where does direct memory typically come from?** NIO direct buffers, Netty/networking, TLS, and various native/client libraries.

**7. Does `MaxDirectMemorySize` cap all native allocations?** No; it governs direct-buffer allocations within HotSpot/JVM scope.

**8. How does `OutOfMemoryError: Java heap space` differ from `OOMKilled`?** OOME is a JVM-level allocation failure; `OOMKilled` is a kernel/container cgroup kill that may leave no Java exception.

**9. Is exit code 137 sufficient proof of `OOMKilled`?** No; verify termination reason/events and context, because SIGKILL has multiple causes.

**10. Is `requests.memory` a runtime ceiling?** No; `limits.memory` sets the cgroup limit when configured and enforced.

**11. Does `requests.cpu=500m` restrict the JVM to half a core maximum?** No; it is a scheduling reservation, while quota depends on `limits.cpu`/runtime.

**12. What does a container-aware JVM mean?** The JVM inspects cgroup CPU/memory constraints for ergonomics when supported by JDK/version/build.

**13. Do JDK 8 and JDK 21 share identical default cgroup detection?** Not necessarily; it depends on backports, builds, and cgroups v1 vs. v2.

**14. What does `MaxRAMPercentage=60` mean in a Pod with a 2Gi limit?** Assuming the JVM detects the limit accurately with no overrides, target max heap is ~60% = 1.2 GiB.

**15. Is `MinRAMPercentage` an Xms percentage?** No; do not treat it as a universal "minimum heap" setting on HotSpot.

**16. Should `Xms=Xmx` always be set?** No; trade-offs across heap commitment, startup, and Pod density must be measured.

**17. What kind of collector is G1?** A region-based, generational collector balancing throughput and pause times via heuristics/ergonomics.

**18. Does `MaxGCPauseMillis=200` guarantee no pause exceeds 200 ms?** No; it is a soft collector goal.

**19. When is ZGC most appropriate?** When GC pauses are a major proven driver of tail latency and sufficient CPU/memory headroom is verified by benchmarks.

**20. Does ZGC have zero stop-the-world pauses?** No. Concurrent collectors still have short synchronization/STW phases.

**21. Does `-XX:+ZGenerational` work identically on every JDK?** No; modes and flag support change across JDK versions.

**22. Is Parallel GC suitable for batch jobs?** Possibly, when throughput outweighs tail pause latency, though it must be measured.

**23. Is pinning a larger young generation always good for G1?** No; it can break adaptive pause sizing.

**24. Why do Full GCs deserve close attention?** They can run long, stall request processing, and cause severe p99 spikes.

**25. Is high GC frequency always bad?** No; frequent short young GCs can easily outperform fewer long pauses.

**26. Is GC pause p99 the same as HTTP request p99?** No; they are distinct distributions to correlate, not equate.

**27. Does `-Xlog:gc*` work on Java 8 by default?** No; unified logging arrived in JDK 9+, while Java 8 uses different build-dependent flags.

**28. Why must GC logs carry Pod/instance labels?** Each process/restart has its own GC IDs and uptime; never merge them into one series.

**29. What is JFR used for?** Collecting profiling events on allocations, GC, locks/threads, CPU, and supported runtime activity.

**30. Can heap dumps contain secrets?** Yes: tokens, passwords, PII, and payloads can live inside heap objects.

**31. Does `jcmd GC.class_histogram` identify GC roots?** No; histograms show per-class counts/bytes, requiring retained-reference analysis to see what keeps objects alive.

**32. Can NMT always be used if not enabled at startup?** Tracking generally must be enabled at startup; do not assume full NMT can be turned on without restarting.

**33. Does NMT summary equal process RSS?** No. It tracks JVM-recorded allocation categories, whereas RSS/cgroup usage includes other memory too.

**34. Is a heap sawtooth a leak?** Not necessarily; it is usually normal. Monitor post-GC live set after warm-up.

**35. Where do heap leaks commonly originate?** Unbounded caches/collections, `ThreadLocal`, retained listeners, queues, and classloader references.

**36. Can native leaks happen with a normal heap?** Yes, via direct buffers, JNI, native libraries, or threads.

**37. Why inspect CPU throttling when GC pauses grow?** Both GC threads and app threads need CPU; throttling stretches pause times and p99.

**38. Should `ActiveProcessorCount` be set to host cores inside a 1-CPU Pod?** Not by default; setting it too high causes contention—test against quota.

**39. Does HPA automatically adjust Xmx?** No; HPA scales replicas on metrics, while JVM heap sizing is a separate runtime configuration.

**40. Can VPA and HPA conflict?** Yes, if both manage overlapping resources/metrics without coordinated design.

**41. What does a startup probe help with?** Gives apps sufficient startup time before liveness/readiness probes trigger restarts or routing changes.

**42. Should liveness depend on every Azure SQL/Service Bus dependency?** Usually no; shared dependency blips can trigger fleet-wide restart storms.

**43. Does `terminationGracePeriodSeconds` guarantee shutdown hooks run on kernel `OOMKilled`?** No; SIGKILL bypasses normal application shutdown.

**44. Why can one Java app impact another on an App Service Plan?** Apps can share worker resources within the same plan.

**45. What does Container Apps scale-to-zero impact?** Cold starts and JVM warm-up can raise latency on initial requests.

**46. Why not assume stdout GC logs automatically reach Azure Monitor?** Log collectors and diagnostic pipelines must be configured and tables/retention verified.

**47. Is `jvm_gc_pause_seconds_sum/count` GC CPU usage?** No; wall-clock pause sum/count misses concurrent GC worker CPU.

**48. Why not compute GC p95 from average pauses?** Averages are not percentiles; use histograms or full event samples.

**49. What must stay constant in a G1 vs. ZGC test?** JDK/build, app code, load mix, CPU/memory, dependencies, warm-up, and metrics.

**50. When p99 slows alongside rising SQL p95, what comes first?** Inspect SQL, networking, connection pools, and saturation before switching GC.

**51. When a heap leak exists, should you keep raising Xmx?** No; that only delays OOME and increases cost.

**52. Why can low heap still result in `OOMKilled`?** Non-heap, native, sidecar, cache, and cgroup charges push total usage over the memory limit.

**53. Why does `OOMKilled` not always produce a heap dump?** The kernel may kill the process without triggering the Java OOME handler.

**54. Does low average CPU utilization rule out burst throttling?** No; check throttled time/period metrics aligned with latency.

**55. Why can adding Pods slow down Azure SQL?** Total JDBC connection pools and concurrency increase, creating downstream contention.

**56. Do Java virtual threads permit infinite concurrency?** No; CPU, memory, and downstream capacity remain finite.

**57. Why avoid exposing remote JMX publicly?** It can expose internals and management operations without auth, TLS, and network controls.

**58. Which metrics prove JVM tuning improved the system?** Good requests/SLOs, GC, RSS/headroom, CPU throttling, and cost under identical workloads.

**59. Why is a single benchmark run insufficient?** Noise, warm-up, and host contention affect runs; repeat runs and check variance.

**60. What matters most in JVM tuning on Azure?** Forming data-backed hypotheses, making reversible changes, measuring both app SLOs and infrastructure budgets, and avoiding "magic flags."

## 43. Production Deployment Checklist

### 43.1. Objectives and Environment

- [ ] Service has an owner and defined SLOs for p95/p99 latency, error rate, and throughput.
- [ ] Baseline exists for representative load, request mix, warm-up, and soak.
- [ ] JDK major/build/vendor, container image, and Azure compute tier are pinned/recorded.
- [ ] AKS/App Service/Container Apps/VM runtime model is clearly understood.
- [ ] JVM container awareness and cgroup v1/v2 compatibility are verified.
- [ ] Resource requests/limits are validated against actual JVM flags.
- [ ] Cost per good transaction targets and canary/rollback plans exist.

### 43.2. Heap, Native Memory, and GC

- [ ] `-Xmx` or `MaxRAMPercentage` is backed by measurements without conflicting flags.
- [ ] Max heap leaves headroom for metaspace, direct buffers, threads, code cache, native libs, and runtime.
- [ ] Heap used, committed, and max are tracked separately.
- [ ] Container RSS/working set and cgroup high-watermark are monitored.
- [ ] Thread count and direct-buffer/native memory metrics are tracked when used by the workload.
- [ ] Default/G1/ZGC/Parallel collector was chosen via benchmarking.
- [ ] GC flags are verified on the exact JDK without mixing incompatible collectors.
- [ ] G1 `MaxGCPauseMillis` is understood as a soft goal.
- [ ] Young generation is not pinned and deep flags are not tuned without evidence.
- [ ] GC logs include timestamps, rotation/retention, and Pod labels.
- [ ] GC pauses are correlated with request p99, CPU, and dependency latency.
- [ ] Soak tests run long enough to detect memory leaks.

### 43.3. AKS, CPU, and Autoscaling

- [ ] Memory requests/limits fit node capacity and JVM native budgets.
- [ ] CPU limits/requests monitor throttled time/periods.
- [ ] `ActiveProcessorCount` does not mis-override CPU quotas.
- [ ] Node pool SKUs and AKS HPA/VPA/Cluster Autoscaler are evaluated together.
- [ ] Readiness/startup/liveness probes are tested under real pauses and load.
- [ ] Liveness does not restart the entire fleet when a shared dependency slows down.
- [ ] Graceful shutdown handles in-flight requests/messages and timeouts.
- [ ] HPA scaling does not exceed Azure SQL/Service Bus downstream capacity.
- [ ] Sidecar and logging overhead are included in capacity.
- [ ] Pod restart reasons distinguish `OOMKilled`, eviction, probe kills, and redeploys.

### 43.4. Spring Boot / App Service / Container Apps / VM

- [ ] Spring Actuator health/metrics endpoints are secured and version-appropriate.
- [ ] HikariCP/HTTP/worker thread pools and retries are bounded.
- [ ] Caches are bounded by size/TTL/weight and business rotation policies.
- [ ] App Service Plan and co-located app memory consumption is monitored.
- [ ] Container Apps startup, cold starts, and min replicas have cost targets.
- [ ] Multiple JVMs on a VM do not overcommit host RAM.
- [ ] Docker images pin JDK patches, run non-root, and keep secrets out of flags.
- [ ] Actual runtime `JAVA_TOOL_OPTIONS`/entrypoint config is verified.
- [ ] Diagnostic paths and log persistence match the hosting plan/runtime.

### 43.5. Observability and Diagnostics

- [ ] Application Insights requests, dependencies, and traces are instrumented and verified.
- [ ] Micrometer/Prometheus JVM metrics exporter is working if used.
- [ ] Azure Monitor/Container Insights collection pipelines contain real data.
- [ ] Dashboards include API SLIs, CPU throttling, memory, GC pauses, and OOM counters.
- [ ] Heap, RSS, and working set are not confused or double-counted.
- [ ] Missing data / Pod termination is distinguished from zero GC pauses or healthy state.
- [ ] JFR/NMT/heap dumps have runbooks, access controls, and retention limits.
- [ ] No sensitive JMX/Actuator diagnostics are publicly exposed.
- [ ] GC/debug logs do not trigger unexpected log ingestion costs.
- [ ] Alerts exist for p99/error rates, OOM/restarts, and dangerous memory trends.

### 43.6. Tuning and Release Governance

- [ ] Every tuning change has a hypothesis, baseline, candidate, test, and conclusion.
- [ ] GC, heap, CPU, replicas, and pools are not all changed together when separable.
- [ ] Load tests hold JDK/build, limits, traffic, and dependency tiers constant.
- [ ] Repeated benchmark runs record percentile sample sizes and variance.
- [ ] Canaries have clear rollback/forward-fix paths without unnecessary outages.
- [ ] GC profiling/heap dumps are never run simultaneously across all production Pods.
- [ ] Native/heap leak fixes include regression tests and post-deploy soak checks.
- [ ] Cost per good transaction and Azure Cost Management are reviewed.
- [ ] Security reviews heap dump, JFR, credential, and PII handling.
- [ ] Incident runbooks exist for OOME, `OOMKilled`, GC pauses, throttling, native leaks, and restart loops.

## 44. Conclusion

**Optimizing JVM, memory, and garbage collection on Azure** is not merely tweaking `-Xmx` or switching from G1 to ZGC. The JVM executes inside a **real CPU/memory budget**: heap, metaspace, thread stacks, direct buffers, native libraries, code cache, and GC overhead all contribute to process and container footprint. On AKS and Container Apps, **cgroup limits, CPU throttling, readiness/liveness probes, and autoscaling** directly shape performance; on App Service and VMs, plan/instance sizing and co-located processes must also be controlled.

To improve a Java/Spring Boot application on Azure, measure **end-user SLIs/SLOs, p95/p99, GC pauses, allocation rates, live heap set, RSS, native memory, and dependency latencies** under the same workload. Use **GC logs, JFR, `jcmd`, NMT, Azure Monitor/Application Insights, and Prometheus** to pinpoint the real bottleneck. **A JVM `OutOfMemoryError` differs from a kernel `OOMKilled`**, and many incidents that look like GC issues actually stem from queues, SQL connection pools, CPU quotas, or network dependencies. Those distinctions govern safe remediation.

The durable workflow is **baseline → hypothesis → one controlled change → load/soak test → canary → verify SLO/cost → document results**. By combining JVM tuning with application design, managed identities, observability, AKS/App Service/Container Apps capacity, and Azure cost governance, engineering teams can achieve **stable latency, high throughput, sensible memory usage, and strong resilience** without relying on "magic JVM flags."
