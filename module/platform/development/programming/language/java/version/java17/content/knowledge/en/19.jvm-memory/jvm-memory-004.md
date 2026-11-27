# Choosing Serial, Parallel, or G1 Based on Application Characteristics in Java 17

The Garbage Collector (GC) reclaims heap memory that an application no longer uses. Choosing a GC affects how the JVM uses CPU, processing throughput, and how long the application must pause to collect memory. Java 17 provides common collectors including **Serial GC**, **Parallel GC**, and **G1 GC**; each fits a different class of workloads.

There is no single best GC for every application. Serial prioritizes simplicity and low operational overhead; Parallel prioritizes throughput on multi-CPU systems; G1 aims to balance throughput and targetable pause times. The choice should be based on workload characteristics, CPU/memory limits, and actual measurements.

This lesson focuses on these three GCs in Java 17, how they work, use cases, how to enable them with JVM options, and how to validate your choice via GC logs. The options presented are current HotSpot options used in Java 17.

## 1. How does GC affect an application?

Java objects are typically allocated on the heap. When an object is no longer referenced from reachable paths, GC can reclaim its memory. The JVM must determine which objects are still live, reclaim memory from unneeded objects, and prepare free space for subsequent allocations.

Some GC work can run in parallel or concurrently with the application, yet collectors still have **stop-the-world (STW)** phases. During an STW phase, application threads are paused so the JVM can perform work requiring heap consistency.

Therefore, GC affects several metrics:

- **Throughput:** the percentage of time the JVM spends on application work rather than GC.
- **Pause time:** how long the application is stopped during a pause.
- **Latency:** how long a user waits for a request or task to finish; GC pauses can contribute to higher latency.
- **CPU usage:** CPU time spent on application threads and GC threads.
- **Memory footprint:** heap, metadata, thread stacks, direct buffers, and other native regions used by the process.

For example, a batch application processing millions of records may prioritize finishing the work as fast as possible, even if occasional GC pauses are longer. An interactive API may need to limit pauses to reduce latency at high percentiles such as p95 or p99.

Do not evaluate a GC by a single metric alone. Short pauses with excessive CPU consumption can slow down the overall application; high throughput with overly long pauses can violate SLAs.

## 2. Three options in Java 17

The three collectors have different design goals:

| GC | Primary goal | Key characteristics | Typical workload considerations |
| --- | --- | --- | --- |
| Serial GC | Simplicity, low overhead | Collects using one GC thread; collection phases stop application threads | Small applications, small heaps, low-CPU environments |
| Parallel GC | High throughput | Uses multiple GC threads to collect; can utilize multiple cores | Batch jobs, background processing, throughput-oriented workloads |
| G1 GC | Balance throughput and pauses | Divides heap into regions, collects by collection set, has concurrent phases | Server services, medium/large heaps, applications needing pause-target control |

You can explicitly select a collector using JVM options:

```bash
# Serial GC
java -XX:+UseSerialGC -jar app.jar

# Parallel GC
java -XX:+UseParallelGC -jar app.jar

# G1 GC
java -XX:+UseG1GC -jar app.jar
```

In a JVM configuration, choose one primary collector. Do not enable multiple selection flags such as `UseSerialGC`, `UseParallelGC`, and `UseG1GC` simultaneously expecting the JVM to combine them; these flags select different GC strategies.

## 3. Serial GC: simple and single-threaded collection

Serial GC performs collection work using a single GC thread. Major collection phases pause application threads while GC runs.

Enable Serial GC:

```bash
java -XX:+UseSerialGC -jar app.jar
```

### How it works

Serial GC has young generation and old generation areas:

- The young generation uses copying to move live objects to an appropriate region and reclaim the old area.
- The old generation is collected via mark and compact.
- Collection phases are stop-the-world and use only one GC thread.

Because there is only one collector thread, Serial avoids multi-worker GC coordination. This reduces overhead in low-CPU environments or small heaps. However, as the heap grows or the object graph enlarges, pause times can increase because GC work is not split across multiple cores.

### When to consider Serial GC?

Serial is worth considering when:

- The application is small and runs as a simple single process.
- The heap is small and object allocation rate is modest.
- The deployment environment has few CPUs or tight CPU limits.
- GC CPU cost and simplicity matter more than occasional long pauses.
- The application has no strict latency requirements.

Examples: short-lived command-line utilities, small data transformation jobs, or an auxiliary service with a small heap and low concurrency.

### When is Serial unsuitable?

Serial is generally not a good fit for high-concurrency servers or heavy-allocation workloads on large heaps. One GC thread may not collect fast enough, forcing the application to wait through longer STW phases.

Do not pick Serial just because it uses fewer GC threads. Consider pause duration, GC frequency, and the CPU the application needs to get work done.

## 4. Parallel GC: prioritizing throughput

Parallel GC is also known as the throughput collector. It uses multiple GC threads to execute collection phases, leveraging multiple CPU cores to shorten total time spent in GC.

Enable Parallel GC:

```bash
java -XX:+UseParallelGC -jar app.jar
```

In HotSpot Java 17, this option uses parallel mechanisms for both the young generation and old generation. Collection phases still involve stop-the-world pauses; the main difference is that multiple GC threads work together during those pauses.

### How it works

- The young generation is collected with parallel copying.
- The old generation uses parallel mark-compact.
- Multiple GC workers process parts of the work simultaneously.
- The JVM can resize heap regions according to configured throughput and pause targets.

Parallel GC suits workloads that can utilize multiple CPUs and prioritize total work completed over a period of time.

### When to consider Parallel GC?

- Large data-processing batch jobs.
- Background compute or ETL tasks.
- Applications where high throughput is the primary goal.
- Multiple CPU cores are available for GC workers.
- Occasional pauses longer than G1 are acceptable.
- SLAs are not overly sensitive to a few long GC pauses.

For example, a scheduled reporting job may prioritize processing 10 million records in the shortest time. If no interactive user is waiting during the batch run, throughput can matter more than keeping every pause very short.

### Things to consider

Parallel GC can consume significant CPU during GC. If a container is granted few CPUs or the application is already busy handling requests, GC workers can contend for CPU with application threads.

Pauses are still STW. Having multiple GC threads does not mean the application never stops; it only means GC work executes in parallel during the pause.

## 5. G1 GC: region-based heap and pause targets

G1 (Garbage-First) is a region-based collector. Instead of treating the heap as traditional fixed-size contiguous areas, G1 divides the heap into many equal-sized **regions**. Regions are used for the young generation, old generation, or other management purposes at any given time.

Enable G1:

```bash
java -XX:+UseG1GC -jar app.jar
```

In Java 17, G1 is the default GC on server-class JVM configurations via ergonomics. The actual default still depends on the platform, JVM setup, and passed options. To know what the JVM actually selected, inspect flags and GC logs instead of guessing from the Java version.

### High-level operation

G1 performs these main types of work:

1. **Young collection:** collects regions belonging to the young generation. Live objects are evacuated to other regions.
2. **Concurrent marking:** marks live objects in the heap while the application continues running in certain phases.
3. **Mixed collection:** after marking, G1 can collect young regions alongside selected old regions.
4. **Region reclamation:** reclaims regions after live objects have been evacuated.

G1 chooses regions with high reclaimable free space, hence the name Garbage-First. It can prioritize a collection set expected to reclaim substantial memory within the target pause budget.

### Pause-time goal

You can configure a pause target with:

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar app.jar
```

`MaxGCPauseMillis` is a **soft goal**. The JVM tries to adjust GC work toward the pause target, but does not guarantee every pause will stay below the configured value. If the workload allocates heavily, creates large objects, or lacks heap headroom, some pauses can still exceed the goal.

Do not set an extremely low number expecting G1 to always meet it. An overly tight target can force GC to collect smaller increments more frequently, hurting throughput.

### When to consider G1?

- Server services handling many requests.
- Medium or large heaps.
- Need to balance throughput and pause times.
- Want a pause goal to guide how the JVM selects collection sets.
- Workloads with latency requirements, though not hard real-time systems.

G1 is a strong general-purpose default for many Java 17 server applications. However, it cannot guarantee low latency on its own if the application allocates excessively, has a memory leak, or is CPU/memory constrained.

## 6. Deeper comparison

| Criterion | Serial | Parallel | G1 |
| --- | --- | --- | --- |
| GC threads | Single thread | Multiple threads | Multiple threads for parallel phases; has concurrent phases |
| Primary goal | Simplicity, low overhead | Throughput | Balance throughput and pause goal |
| Heap organization | Young/old generation | Young/old generation | Region-based heap, still with young/old generations |
| STW phases | Yes | Yes | Yes |
| Concurrent marking phase | Not part of Serial GC design | Not part of Parallel GC design | Yes |
| Multi-core utilization | Low | High during parallel GC phases | Yes |
| Pause time | Can be long as heap/workload grows | Can be long; multiple workers shorten GC work | Aims for pause target, no hard guarantee |
| Coordination overhead | Low | Worker coordination overhead | Additional region management and concurrent work overhead |
| Typical workload considerations | Small apps, low CPU | Batch, high throughput | Servers, medium/large heaps, balanced needs |

Do not treat this table as an absolute rule. For example, Parallel GC may achieve good pauses on a specific workload; G1 may use more CPU than expected; Serial may run very efficiently for a small utility. Your application's metrics are the deciding factor.

## 7. Choosing a GC by workload characteristics

Start by asking what the application needs to optimize.

### Case A: small application, low CPU, small heap

Examples:

- Command-line tools.
- Short-lived tasks.
- Sidecar/auxiliary processes in resource-constrained environments.
- Applications with few objects and few threads.

You can try Serial GC:

```bash
java -Xms128m -Xmx512m -XX:+UseSerialGC -jar small-tool.jar
```

Reason: no need for multiple GC workers, low coordination overhead. Still, if pause times directly impact task completion, measure and compare against G1 or Parallel.

### Case B: batch or background processing prioritizing throughput

Examples:

- Scheduled ETL jobs.
- Large report generation.
- Bulk image/document processing.
- Background compute on multi-core machines.

You can try Parallel GC:

```bash
java -Xms4g -Xmx4g -XX:+UseParallelGC -jar batch-job.jar
```

Reason: multiple GC threads leverage available CPUs to finish collection faster. Ensure GC does not starve the CPU needed by the application's core processing.

### Case C: server needing balanced throughput and latency

Examples:

- REST APIs.
- High-concurrency request services.
- Backends with larger heaps than small utility apps.
- Workloads requiring pause-time observation and control.

You can start with G1:

```bash
java -Xms2g -Xmx2g -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar service.jar
```

Reason: G1 manages the heap in regions, supports concurrent marking, and adapts collection sets toward the pause goal.

The 200 ms value in the example is purely illustrative, not suitable for every service. Set targets based on your SLA and observed pause data.

### Initial suggestion table

| Application profile | First GC to test | Must verify with metrics |
| --- | --- | --- |
| Small heap, low CPU, simple tasks | Serial | Do pauses affect completion time? |
| CPU-bound batch, many cores, throughput priority | Parallel | Total GC time and actual throughput. |
| Server, many requests, balanced latency/throughput | G1 | p95/p99 latency, pause distribution, and CPU. |
| CPU-constrained container | Serial or G1/Parallel depending on workload | GC worker count and CPU contention. |
| Large heap, high allocation rate | G1 is a reasonable starting point | Evacuation pauses, concurrent cycles, and allocation capacity. |

These are initial testing directions, not rigid selection rules.

## 8. What does "G1 is the default" mean?

Since Java 9, G1 has been the default GC on HotSpot server-class configurations. Thus, in many Java 17 server environments, an application may already be using G1 even without passing `-XX:+UseG1GC`.

However, never assume the active GC solely from the Java version:

- The JVM can pick a different collector via ergonomics and environment traits.
- Command-line flags can override the default selection.
- Container CPU/memory limits and platform differences can influence JVM configuration calculations.
- JDK distributions or deployment scripts can differ.

Check effective flags:

```bash
java -XX:+PrintCommandLineFlags -version
```

In a running process, use `jcmd`:

```bash
jcmd <pid> VM.flags
jcmd <pid> VM.info
```

Replace `<pid>` with the application's process ID. The `jcmd` tool ships with the JDK. Inspect flags related to the collector, heap, and GC thread counts to confirm the actual configuration.

## 9. Recording GC logs in Java 17

Java 17 uses Unified Logging. Enable GC logs with:

```bash
-Xlog:gc*:file=gc.log:time,uptime,level,tags
```

Example running G1 with logging:

```bash
java -Xms2g -Xmx2g -XX:+UseG1GC \
     -Xlog:gc*:file=gc-g1.log:time,uptime,level,tags \
     -jar service.jar
```

Similarly, create separate logs for Serial and Parallel:

```bash
java -Xms2g -Xmx2g -XX:+UseSerialGC \
     -Xlog:gc*:file=gc-serial.log:time,uptime,level,tags \
     -jar service.jar

java -Xms2g -Xmx2g -XX:+UseParallelGC \
     -Xlog:gc*:file=gc-parallel.log:time,uptime,level,tags \
     -jar service.jar
```

Use distinct log filenames so results from separate runs are not mixed up. In production, manage log size and retention to avoid filling up disk space.

### What to inspect in GC logs

Depending on the collector and log level, logs can reveal:

- Timestamp and type of GC event.
- Pause duration.
- Heap occupancy before and after GC.
- Young/old or region sizes.
- G1 concurrent marking/cycles.
- GC trigger cause.
- CPU and worker metrics at corresponding log levels.

Do not merely count GC events. An application with many short young GCs can perform better than one with fewer GCs that each pause for a very long time.

## 10. Which metrics should you measure for comparison?

To choose a GC, collect the following metric groups.

### Pause time

Inspect:

- Average pause.
- Maximum pause.
- p50, p95, p99 distributions.
- Pause frequency per unit time.

For APIs, p99 pauses can strongly impact request latency even when average pauses are low.

### Throughput and completion time

Measure requests/second or records/second, along with batch completion time. If throughput is the goal, compare total work completed under identical conditions.

### CPU

GC uses CPU for marking, copying, compacting, or evacuation. Monitor total process CPU and CPU contention between GC threads and application threads.

### Heap and allocation rate

Inspect:

- Heap occupancy before and after GC.
- Object allocation rate.
- Young GC frequency.
- Whether the old generation grows steadily or stabilizes.
- Full GCs or unusual collection events.

If heap keeps growing after many GC cycles, the application may be retaining references to unneeded objects. Switching GCs will not fix a memory leak.

### Application metrics

Combine GC metrics with:

- Request latency.
- Error rate and timeouts.
- Throughput.
- Queue depth.
- Container CPU throttling.
- Total process memory usage.

A GC with low pauses that drives up CPU throttling can worsen overall application latency.

## 11. A fair benchmarking workflow

Do not switch GCs in production based solely on claims like "G1 is slower" or "Parallel is faster." Test on a representative workload.

A practical workflow:

1. **Choose a workload:** use data, concurrency, and read/write ratios close to production.
2. **Keep the environment consistent:** identical JDK 17 build, CPU, memory limit, heap size, app config, and endpoints.
3. **Run each collector separately:** Serial, Parallel, and G1 must be tested in separate processes/runs.
4. **Warm up:** let the JIT, caches, and runtime reach steady state before taking primary measurements.
5. **Log metrics:** enable Unified GC Logging and application metrics.
6. **Repeat:** execute multiple runs to reduce environmental noise.
7. **Compare:** examine pause distribution, throughput, CPU, heap occupancy, and SLAs.
8. **Validate in production-like staging:** before broad rollout, test under realistic resource limits and traffic.

Keeping the same `-Xms` and `-Xmx` during initial comparisons eliminates one variable. Once you select an appropriate collector, you can test tuning heap size or collector-specific parameters.

Do not use a tiny microbenchmark to draw conclusions about GC for a large system. GC depends on allocation rate, object lifetimes, object graphs, thread counts, heap size, and runtime duration.

## 12. Tuning options worth knowing

### 12.1. Heap size

`-Xms` sets initial heap; `-Xmx` sets maximum heap limit:

```bash
java -Xms2g -Xmx2g -XX:+UseG1GC -jar app.jar
```

Using equal values in this example prevents the heap from resizing the way a `-Xmx`-only configuration might. Still, not every application should set `-Xms` equal to `-Xmx`; the decision depends on memory limits and allocation behavior.

Do not set `-Xmx` equal to the entire container memory limit. The process also needs metaspace, thread stacks, direct buffers, JIT code cache, and other native memory.

### 12.2. G1 pause target

`-XX:MaxGCPauseMillis` gives G1 a soft pause goal:

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=150 -jar app.jar
```

Lowering the pause target can cause G1 to choose smaller collection sets or adjust work, but may raise GC frequency and reduce throughput. Adjust incrementally and observe logs.

### 12.3. Parallel throughput target

Parallel GC can use `-XX:GCTimeRatio` to express a target ratio of application time to GC time:

```bash
java -XX:+UseParallelGC -XX:GCTimeRatio=19 -jar batch.jar
```

This value is an ergonomics goal, not a strict throughput guarantee. The JVM may adjust the heap toward this target within resource limits and other constraints.

You can set a pause target via `-XX:MaxGCPauseMillis` for Parallel GC as well, though optimizing pauses may reduce throughput. Do not set extreme values for both goals without understanding the trade-offs.

### 12.4. Do not tune GC thread counts right away

Flags like `-XX:ParallelGCThreads` and `-XX:ConcGCThreads` control thread counts in applicable GC phases. However, the JVM uses ergonomics to choose thread counts automatically based on CPU and configuration.

Adjust these flags only when logs and profiling demonstrate a specific issue, such as GC threads contending for CPU or worker counts mismatched with container limits. Changing thread counts without measuring can degrade performance.

## 13. Signs that you should revisit your GC choice

### Long pauses affecting p99

If the application experiences long pauses coinciding with request latency spikes, inspect GC events, heap pressure, and allocation rate. G1 may be worth testing if you are using Serial or Parallel and need balanced pauses.

### Excessive GC CPU usage

If GC consumes high CPU, check allocation rate, object lifetimes, heap size, and worker counts. Parallel can use many cores to boost throughput but may also contend with application threads. G1 also needs CPU for marking and evacuation.

### Repeated Full GCs

Full GCs usually indicate a need to investigate heap pressure, the old generation, allocation capacity, or long-held object references. Do not merely swap collectors to mask the symptom.

### Heap stays nearly full

High post-GC heap occupancy can stem from a genuinely large live set, a memory leak, or an undersized heap. Analyze heap dumps or liveness/allocation data. Raising `-Xmx` only helps if the application truly needs more heap and the host/container has spare memory.

### Pause goal missed

With G1, `MaxGCPauseMillis` is a soft goal. If pauses exceed the target, inspect object sizes, humongous allocations, heap headroom, allocation rate, and CPU availability. Do not treat raising or lowering the target number as a cure-all.

## 14. Common misconceptions

| Misconception | Reality |
| --- | --- |
| Parallel GC does not pause the application because it uses multiple threads. | Parallel GC still has STW pauses; multiple threads simply share GC work during the pause. |
| G1 guarantees every pause stays under `MaxGCPauseMillis`. | It is a soft goal, not a hard time limit. |
| G1 is always faster than Parallel. | G1 and Parallel have different goals; workload and hardware determine the winner. |
| Serial is always slow. | With small heaps and limited CPU, Serial's low overhead can be ideal. |
| The default GC is identical on every Java 17 machine. | JVM ergonomics and environment configurations can affect the chosen collector. |
| Raising `-Xmx` always fixes slow GC. | A larger heap may reduce GC frequency, yet can lengthen some collection phases and increase memory footprint. |
| Fewer GCs are always better. | Consider pause duration, throughput, and overall application impact. |
| GC logs immediately pinpoint memory leaks. | Logs surface symptoms; identifying retaining objects typically requires heap analysis. |
| You only need to pick a GC, not measure. | Any choice must be verified with representative workloads and metrics. |

## 15. Serial, Parallel, or G1: decision workflow

Use the following questions to choose a starting point:

```text
Does the app have a small heap, low CPU, and low concurrency?
                 |
          +------+------+
          |             |
         Yes            No
          |             |
          v             v
      Try Serial   Is throughput the primary goal?
                        |
                  +-----+-----+
                  |           |
                 Yes          No
                  |           |
                  v           v
            Try Parallel   Need balanced latency
                           and throughput?
                                |
                                v
                              Try G1
                                |
                                v
                       Benchmark real workload
                                |
                                v
                    Choose by pauses, CPU, throughput,
                    heap, and actual SLA
```

This workflow selects a **starting point**. Benchmark results may lead you to choose a collector different from the initial suggestion.

## 16. Example: running the same application with three GCs

Suppose a batch or service application is packaged as `app.jar`. To compare, run separate processes with identical heap sizes and GC log formats:

```bash
java -Xms2g -Xmx2g -XX:+UseSerialGC \
     -Xlog:gc*:file=serial.log:time,uptime,level,tags \
     -jar app.jar

java -Xms2g -Xmx2g -XX:+UseParallelGC \
     -Xlog:gc*:file=parallel.log:time,uptime,level,tags \
     -jar app.jar

java -Xms2g -Xmx2g -XX:+UseG1GC \
     -Xlog:gc*:file=g1.log:time,uptime,level,tags \
     -jar app.jar
```

In each run, use the same dataset and load scenario. Record at least:

| Metric | Serial | Parallel | G1 |
| --- | --- | --- | --- |
| Workload completion time | Measure | Measure | Measure |
| Throughput (requests/s or records/s) | Measure | Measure | Measure |
| Pause p95/p99/max | Measure | Measure | Measure |
| Total GC time | Measure | Measure | Measure |
| Process CPU | Measure | Measure | Measure |
| Post-GC heap | Measure | Measure | Measure |
| Full GC count | Measure | Measure | Measure |
| Application errors/timeouts | Measure | Measure | Measure |

Do not fill the table with guessed numbers. Results depend on the application and runtime environment.

## 17. Notes for containerized applications

In container environments, the JVM can detect container CPU and memory limits on supported platforms. This affects ergonomics, default heap sizing, and GC thread counts.

When comparing collectors in containers:

- Keep CPU quota and memory limit identical.
- Check how many CPUs the JVM detects.
- Do not assume a 32-core host means the container can use all 32 cores.
- Monitor CPU throttling and memory pressure.
- Reserve memory for off-heap native memory.
- Use the same heap settings across benchmark runs.

A parallel GC with many workers may not help if the container is allocated only one or two CPUs. Conversely, forcing Serial in a container with many CPUs and high allocation workloads can make GC a bottleneck.

## 18. When are these three choices not enough?

Serial, Parallel, and G1 handle most common Java workloads. However, if a system has ultra-low pause requirements or special heap characteristics, you may need to evaluate other collectors provided by the JDK/vendor, such as ZGC or Shenandoah on supported distributions.

Do not view G1 as a hard real-time collector. If SLAs require very strict pause limits, test a low-latency collector separately and review architecture, allocation rate, and resource limits. The existence of a collector in Java 17 does not imply identical support status or defaults across all JDK distributions; verify your vendor and build documentation.

This lesson focuses on choosing among Serial, Parallel, and G1; there is no need to switch to another collector if your current workload already meets its SLA.

## 19. Practice exercises

### Exercise 1 — run and identify collectors

Run the same small application three times with:

- `-XX:+UseSerialGC`
- `-XX:+UseParallelGC`
- `-XX:+UseG1GC`

Enable `-Xlog:gc*` and identify which collector appears in the logs.

### Exercise 2 — measure batch throughput

Create a workload processing a large dataset with object allocations. Run with Serial, Parallel, and G1 under identical conditions. Record completion time and records processed per second.

### Exercise 3 — observe pauses

Use GC logs to record pause times for each collector. Compare p95, p99, and max pauses; explain why average pause is insufficient to describe request experience.

### Exercise 4 — test G1 pause target

Run G1 with different `-XX:MaxGCPauseMillis` values, such as 100 and 200. Observe GC frequency, pause distribution, and throughput. Explain why this target is not a hard guarantee.

### Exercise 5 — check CPU impact

Run the same workload under low and high CPU quotas. Observe how Serial and Parallel behave. Explain why many GC workers may offer no benefit when CPU is constrained.

### Exercise 6 — identify issues not solved by changing GC

Create a workload that keeps adding references to objects in an ever-growing Collection. Monitor post-GC heap. Explain why switching from Serial to G1 will not fix a memory leak.

## 20. Quick summary

| Characteristic | Serial GC | Parallel GC | G1 GC |
| --- | --- | --- | --- |
| JVM option | `-XX:+UseSerialGC` | `-XX:+UseParallelGC` | `-XX:+UseG1GC` |
| Goal | Simplicity, low overhead | Throughput | Balance throughput and pauses |
| GC threads | One | Multiple | Parallel and concurrent |
| Heap organization | Young/old | Young/old | Region-based, young/old |
| Pauses | STW | STW | Has STW and concurrent phases |
| Suggested workload | Small, low CPU | Batch, high throughput | Servers, balanced latency needed |

**Core principle:** Start from workload characteristics: Serial for small, low-CPU apps; Parallel for throughput-oriented workloads on multiple cores; G1 for many server applications balancing throughput and pauses. In Java 17, G1 is often the default on server-class JVMs, but verify the active collector using flags and GC logs. Benchmark under identical conditions and track p95/p99 pauses, throughput, CPU, and heap before finalizing your choice.
