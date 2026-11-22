# Trade-Offs Between Warm-Up Depth, Image Build Time, and Image Size

When using CRaC (Coordinated Restore at Checkpoint), a Java application is typically started and warmed up before creating a checkpoint. The goal is bringing the JVM and application close to their real serving state: necessary classes are loaded, the framework is initialized, commonly used code paths have executed, the JIT compiler has had an opportunity to optimize, and needed caches have been prepared.

Warming up more can help restored instances become ready faster and lower the latency of initial requests. However, warm-up also consumes CPU and time before checkpointing, and can increase live heap, code cache, cached data, and the number of memory pages saved. Therefore, the warm-up level must be chosen based on measurements across three factors: **preparation time**, **checkpoint creation time**, and **checkpoint size**.

There is no single optimal warm-up level for every application. An API service, a batch worker, and a Spring Boot application can have vastly different startup paths, caches, and workloads. Warm the right critical processing paths, measure post-restore benefits, and stop when incremental costs no longer justify the gain.

## 1. What is warm-up in the JVM?

Warm-up is the process of running an application with a deliberate workload before creating a checkpoint. It helps the JVM and application complete upfront some work that normally happens only once an instance starts receiving real requests.

Commonly warmed activities include:

- Loading classes and initializing required classes.
- Initializing frameworks, dependency injection containers, and configuration.
- Running commonly used code paths so the JVM collects profiles.
- Letting the JIT compiler compile sufficiently hot methods.
- Loading metadata, schemas, and reference data.
- Preparing certain application caches that can be retained safely.
- Initializing data structures and lazy-initialization paths.

Warm-up is not just calling a single endpoint many times. A good workload must reflect real processing paths, yet be designed so it creates no unwanted business side effects.

### 1.1. JVM execution and optimization stages

The HotSpot JVM normally begins executing bytecode via an interpreter. Once a method or loop is called enough times, the JVM may compile the code to machine code. With tiered compilation, the JVM can pass through different compilation levels, such as fast compilation to reduce initial cost followed by deeper optimization once sufficient profiles exist.

A high-level model:

~~~mermaid
flowchart TD
    A["Application starts up"] --> B["Class loading and initialization"]
    B --> C["Interpreter execution"]
    C --> D["Collect invocation and branch profiles"]
    D --> E["Low-tier JIT compilation"]
    E --> F["Continue collecting profiles"]
    F --> G["Deeper JIT optimization when appropriate"]
    G --> H["Checkpoint"]
    H --> I["Restore"]
    I --> J["Application continues with prepared state"]
~~~

The diagram only illustrates the concept. Tiers, compilation thresholds, and state-saving behavior depend on the JDK, JVM flags, and workload. Not every method gets fully optimized merely because the application has run for some time.

### 1.2. Warm-up can prepare more than just JIT

An application can be slow on the first request for many different reasons:

| Cost source | Examples | How can warm-up help? |
|---|---|---|
| Class loading | Loading controller or serializer classes | Pre-load required classes |
| Class initialization | Static initializers, metadata registration | Perform initialization upfront |
| Framework initialization | Creating beans, routes, mappers | Prepare containers and structures |
| JIT compilation | Frequently called methods not yet optimized | Supply profiles and compilation opportunities |
| Cache miss | Missing reference data | Pre-load critical keys |
| Lazy initialization | Creating clients or parsers on first use | Trigger beforehand if safe |
| Connection setup | DNS, TCP, TLS, authentication | Can be established beforehand, yet must be re-managed after restore |

Do not lump all these costs together as "JIT warm-up." An application may already have good JIT compilation yet still be slow due to cache misses or database connections. Conversely, caches may already be warm while critical methods remain unoptimized.

## 2. How does warm-up affect checkpoints?

A checkpoint saves process state at a point in time. That state can include the heap, thread state, JVM metadata, compiled code, and other memory regions depending on the JDK, operating system, and checkpoint/restore mechanism.

Warm-up can alter these memory regions:

- Loaded classes and metadata increase runtime state that must be preserved.
- Live cached objects increase live heap.
- The JIT compiler may generate machine code in the code cache.
- Profiles and runtime metadata may grow.
- Threads created for warm-up can increase thread count and stacks if not stopped.
- Buffers and native resources can increase process memory usage.

Some temporary data created by warm-up can be reclaimed by the garbage collector before checkpointing. Therefore, total bytes allocated throughout warm-up does not equal bytes stored in the final image. What matters is live state and memory pages the checkpoint mechanism must save.

### 2.1. Warm-up can improve post-restore time

If certain classes are already loaded, application structures are built, and hot methods are JIT-compiled, the restored instance can avoid repeating part of initialization and optimization work.

Benefits can manifest in:

- Shorter time from restore to readiness.
- Lower latency for the first requests.
- Fewer cache misses in the initial phase.
- Fewer JIT compilations after receiving traffic.
- Less performance variance between cold requests and steady-state requests.

The actual improvement depends on which state the runtime preserves and reuses after restore. Measure with the exact CRaC JDK and deployment environment in use.

### 2.2. Warm-up can increase image build time

Longer warm-up increases preparation time before checkpointing. Besides workload execution time, the JVM may need to perform compilation, GC, or synchronization operations.

If warm-up creates many active memory pages or substantial state to save, checkpointing may need extra time to dump. On some systems, checkpointing can also pause the process while state is written to storage.

Distinguish:

- **Warm-up duration:** time running the application and workload before checkpoint.
- **Checkpoint duration:** time from initiating the checkpoint request until the image finishes creating.
- **Preparation duration:** time draining tasks, closing resources, and preparing a safe state.
- **Restore duration:** time reconstructing the process from the image.
- **Time to ready:** total time from starting restore until the application can accept traffic.

A longer warm-up does not necessarily make checkpoint dumping proportionally longer. It may raise preparation time, increase live memory, or add very little to image size if most allocations were reclaimed.

### 2.3. Warm-up can increase image size

Checkpoint size is influenced by many components:

- Retained heap pages.
- Class metadata and runtime metadata.
- JIT code cache.
- Thread stacks and thread state.
- Native memory and direct buffers.
- Mapped memory regions or resources the checkpoint mechanism must save.
- Compression level, deduplication, and how the tool stores pages.

If warm-up populates more caches with many live objects, live heap may grow. If warm-up causes more methods to be compiled, code cache may grow. If warm-up spawns many threads without stopping them, thread state and stacks can also enlarge the image.

However, configured maximum heap size does not equal checkpoint size. A heap with high capacity yet few live objects can have a different footprint from a smaller heap holding many objects and active memory pages. Measure the actual artifact size produced by the checkpoint tool.

## 3. Three quantities to balance

When choosing a warm-up level, monitor at least three quantities:

1. **Preparation cost:** time and CPU to run warm-up, prepare resources, and create the checkpoint.
2. **Post-restore benefit:** restore duration, time to ready, latency, and throughput in the initial phase.
3. **Storage and operational cost:** image size, upload/download duration, number of images stored, and storage capacity.

~~~mermaid
flowchart TD
    A["Choose warm-up workload"] --> B["Warm-up time increases"]
    B --> C["More classes, profiles, code, and caches prepared"]
    C --> D["Initial post-restore performance may improve"]
    C --> E["Live memory and checkpoint footprint may grow"]
    E --> F["Checkpointing, storage, and distribution may cost more"]
    D --> G["Measure actual benefits"]
    F --> G
    G --> H["Select appropriate warm-up level"]
~~~

The goal is not maximizing the number of executed methods or cache size. The goal is achieving required post-restore performance within permitted time and resource budgets.

### 3.1. Preparation cost

Preparation cost includes:

- Application startup duration.
- Duration running warm-up requests or jobs.
- CPU spent on JIT compilation.
- GC triggered when warm-up allocates many objects.
- Time draining and closing resources before checkpoint.
- Time executing the checkpoint.

For systems building a checkpoint once and restoring hundreds of instances, warm-up and image build costs can be amortized across many restores. For systems continuously building images per instance, this cost can become a substantial fraction of total operational time.

### 3.2. Post-restore benefit

Do not measure restore duration alone. An application may restore very quickly yet still need several seconds to warm caches or re-JIT before reaching desired performance.

Measure:

- Restore-to-process-ready.
- Restore-to-application-ready.
- Restore-to-first-successful-request.
- Latency p50, p95, and p99 in the initial phase.
- Throughput across the first requests.
- Number of JIT compilations after restore.
- Cache hit rate and miss rate.
- Number of connection or refresh errors in the initial phase.

### 3.3. Image size and storage cost

Image size affects:

- Storage capacity.
- Checkpoint write duration.
- Image download duration to restore hosts.
- Bandwidth when scaling out many instances.
- Cost of retaining multiple checkpoint versions.
- Backup duration and artifact lifecycle.

A larger image can still be a good choice if it substantially reduces time to ready for a critical workload. Conversely, a larger image that does not improve latency may be unnecessary cost.

## 4. Commonly used warm-up levels

Warm-up can be organized into three levels for comparison. This is a design classification, not official CRaC or JVM modes.

### 4.1. Basic level: structural initialization

This level focuses on work necessary for the application to begin accepting requests:

- Initialize framework and dependency injection.
- Load common classes and routes.
- Read configuration.
- Initialize serializers, mappers, and metadata.
- Prepare small data structures.
- Verify essential dependencies.

Advantages:

- Short warm-up duration.
- Creates little extra cache and live heap.
- Images usually have a smaller footprint.
- Fits applications prioritizing checkpoint creation speed and storage capacity.

Limitations:

- Many methods may still run in the interpreter or lower compilation tiers.
- JIT profiles do not yet reflect real workloads.
- First requests may still encounter lazy initialization and cache misses.

### 4.2. Targeted level: warming common processing paths

This level runs a representative workload covering important and frequent requests:

- Invoke common endpoints.
- Execute common processing branches.
- Run serializers/deserializers with representative data.
- Load essential caches.
- Give the JVM time to collect profiles and compile hot methods.
- Check required database or external service access paths.

Advantages:

- Balances post-restore performance and checkpoint cost.
- Prepares heavily used methods and caches.
- Avoids running every rarely used feature.

Limitations:

- Requires knowing the real workload.
- May miss critical branches if the warm-up set is unrepresentative.
- Image size and preparation time may increase.

### 4.3. Deep level: running workload close to steady state

This level runs a longer workload with a request distribution close to production and can warm many code paths, caches, and methods.

Advantages:

- Can reach higher JIT optimization levels for hot paths.
- Can noticeably reduce latency in the initial phase after restore.
- Can pre-load substantial caches serving real workloads.

Limitations:

- Consumes substantial CPU and preparation time.
- Increases likelihood of large caches and large live heap.
- Checkpoint images may be larger.
- Risks warming unnecessary data or producing skewed profiles.
- Easier to trigger side effects if the workload is not controlled.

Deep level should be used only when measurements show post-restore benefits large enough to offset costs.

## 5. Too little warm-up and too much warm-up

### 5.1. Too little warm-up

If a checkpoint is created right after the application starts, many classes and code paths may not have executed yet. After restore, the application still must:

- Lazy-load classes.
- Initialize objects and framework components.
- Populate caches for the first time.
- Perform JIT compilation as methods become hot.
- Set up unprepared runtime structures.

The result is a checkpoint that may be small and fast to build, yet startup-time reduction falls short of expectations.

### 5.2. Too much warm-up

Extending warm-up does not guarantee performance keeps improving proportionally. Once critical code paths have executed and been optimized, additional warm-up rounds may yield diminishing returns.

Meanwhile, costs can keep rising:

- Additional time and CPU.
- Caches continue loading rarely used data.
- Heap gains more live objects.
- Code cache and metadata may grow.
- Scheduled tasks or background threads may be started.
- Warm-up may trigger business operations that should not run in the image-building environment.

An example of the diminishing returns trend:

~~~text
Post-restore performance benefit
^
|                  _________
|              ___/
|           __/
|        __/
|     __/
|  __/
|_/
+--------------------------------> Warm-up time

Preparation cost and footprint
^
|                          /
|                      ___/
|                  ___/
|              ___/
|          ___/
|      ___/
|_____/
+--------------------------------> Warm-up time
~~~

The curves are purely illustrative. The real shape must be measured on your application and environment.

## 6. Components that can increase footprint

### 6.1. Live heap and application caches

Caches containing live objects can increase live heap. For example, warming millions of products or all metadata may reduce cache misses, yet also increases objects that must be saved in the checkpoint.

Consider:

- Load frequently used keys instead of all data.
- Set maximum sizes and eviction policies.
- Use appropriate TTLs.
- Do not retain unnecessary request objects or entities.
- Do not cache connections, transactions, or native handles as ordinary data.

A warm-up generating many temporary allocations without holding references may not raise live heap proportionally. Therefore, distinguish allocation volume from retained heap.

### 6.2. JIT code cache

The JIT compiler generates machine code for methods deemed sufficiently hot. Compiled code can reside in the code cache and is part of runtime state to consider at checkpointing.

Warming additional code paths can increase the amount of compiled code. However, do not try to warm every method. Rarely used methods may offer no significant post-restore benefit.

The JVM may also deoptimize or recompile when optimization assumptions no longer hold. For example, a warm-up profile heavily skewed from real workloads may render certain optimizations ineffective.

### 6.3. Class metadata and class initialization

Loading more classes and initializing classes can increase metadata and static state in the process.

Class initialization in Java usually occurs once per class loader lifecycle. If a class already initialized before checkpoint, that state may be preserved in the restored process. However, static fields may hold stale configuration or environment-dependent data.

Do not trigger every class merely to inflate loaded class counts. Focus on classes in critical processing paths and check whether static state depends on time, secrets, or endpoints.

### 6.4. Threads and stacks

Warm-up can inadvertently create many workers, schedulers, connection monitors, or background threads. If they remain active at checkpoint, thread state and stacks can complicate restoration.

Before checkpointing, you need to:

- Stop warm-up tasks.
- Drain workers.
- Stop unnecessary schedulers.
- Close or re-prepare executors according to lifecycle.
- Keep only threads actively supported by the runtime and application.

Do not create thousands of threads just to "warm up" the system. Warm-up should focus on code paths and data, not keeping unnecessary background activity alive.

### 6.5. Native memory and direct buffers

Some libraries use direct ByteBuffers, native libraries, compression contexts, or off-heap structures. Warm-up may allocate or retain these memory regions.

Not every native resource has the same checkpoint/restore capability. Check library documentation and handle lifecycles via appropriate integrations or Resource callbacks.

### 6.6. Garbage collection before checkpoint

Warm-up can create many temporary objects. If those objects are no longer referenced, GC can reclaim them before checkpointing.

Do not treat calling System.gc() as a way to guarantee a smaller image. GC behavior depends on the collector and configuration, and a full GC can increase preparation time. Measure live heap and checkpoint footprint before adding a forced GC step.

## 7. Designing representative warm-up workloads

A good warm-up must answer: which code paths genuinely need to be fast right after restore?

### 7.1. Selecting by traffic share

Production statistics can be used to identify:

- Endpoints with high request rates.
- Operations with large p95/p99 latency.
- CPU-intensive methods.
- Heavily used serializers and parsers.
- Common queries and cache keys.
- High-frequency logic branches.

You do not have to warm every endpoint strictly proportional to traffic. A rarely used endpoint with high business impact may need dedicated preparation.

### 7.2. Selecting by code path, not just by URL

One endpoint may traverse multiple logic branches depending on input kind. Calling a single URL with one payload may warm only part of the code.

For example, a search API might have branches for:

- Searching by name.
- Filtering by category.
- Sorting by price.
- Pagination.
- Handling empty results.
- Handling large datasets.

Choose payloads representative of common and critical paths. Avoid creating overly broad workloads that drag out warm-up without adding value.

### 7.3. Warm-up data must be safe

Do not run warm-up with production data that can cause real side effects:

- Do not send emails or SMS to customers.
- Do not create payment transactions.
- Do not issue invoices.
- Do not mutate inventory.
- Do not produce real business messages.
- Do not trigger workflows with external effects.

Use mocks, sandboxes, test tenants, read-only requests, or dedicated warm-up endpoints. If testing a write path is necessary, have data and an environment designed to roll back or remove changes safely.

### 7.4. Avoiding skewed profiles

JIT uses profiles collected during execution to guide optimization decisions. If warm-up uses only one input shape or a single branch, profiles may not represent production workloads.

For example, a list-processing method may normally receive 10 elements in production, whereas warm-up only runs with empty lists. The resulting JIT profile may not reflect the common processing path.

Use multiple representative inputs in a controlled way. You do not need to run every data combination; prioritize realistic distributions and meaningful branches.

## 8. Phased warm-up workflow

A workflow can be divided into the following phases:

~~~mermaid
flowchart TD
    A["Start JVM"] --> B["Initialize framework and configuration"]
    B --> C["Warm up essential classes and code paths"]
    C --> D["Warm up representative workload"]
    D --> E["Load critical caches"]
    E --> F["Measure JIT, heap, and caches"]
    F --> G{"Goals reached?"}
    G -->|Not yet| D
    G -->|Yes| H["Stop warm-up and background tasks"]
    H --> I["Prepare Resources for CRaC"]
    I --> J["Create checkpoint"]
    J --> K["Restore in target environment"]
    K --> L["Measure time to ready and latency"]
~~~

### Phase 1: Structural initialization

Start the application, build the framework container, read configuration, and initialize required components. Identify external resources that will need to be closed or refreshed.

### Phase 2: Warming classes and processing paths

Invoke critical endpoints or service methods using representative data. Monitor JIT compilation if needed to verify hot methods were compiled at appropriate levels.

Do not use just a fixed duration like "warm up 60 seconds" without observing results. Two different workloads can require vastly different durations.

### Phase 3: Populating essential caches

Load configuration, metadata, and popular cache keys. Do not load all data if most of it goes unused. Set TTLs and versions so caches can be re-evaluated after restore.

### Phase 4: Stopping background activity

Before checkpointing, stop warm-up generators, schedulers, and unnecessary tasks. Drain running requests and tasks. Close connections or environment-dependent resources per CRaC callbacks.

### Phase 5: Creating checkpoint and measuring

Record preparation time, dump duration, and artifact size. Then restore the image in a production-like environment and measure time to ready alongside initial request performance.

### Phase 6: Tuning warm-up level

Compare warm-up levels. If increasing warm-up by 30% reduces latency very little while inflating image size sharply, consider stopping at the previous level.

## 9. Java example: running a bounded warm-up workload

The following example illustrates a coordinator running warm-up requests for a specified number of rounds. Services are application-defined abstractions.

~~~java
import java.util.List;

public final class ApplicationWarmup {

    private final List<WarmupScenario> scenarios;

    public ApplicationWarmup(List<WarmupScenario> scenarios) {
        this.scenarios = List.copyOf(scenarios);
    }

    public void run(int rounds) throws Exception {
        if (rounds <= 0) {
            throw new IllegalArgumentException(
                "rounds must be greater than zero"
            );
        }

        for (int round = 0; round < rounds; round++) {
            for (WarmupScenario scenario : scenarios) {
                scenario.execute();
            }
        }
    }
}
~~~

A scenario can represent one code path:

~~~java
public interface WarmupScenario {
    String name();

    void execute() throws Exception;
}
~~~

At startup, the application can supply read-only scenarios or scenarios running on sandbox data:

~~~java
List<WarmupScenario> scenarios = List.of(
    new ProductSearchWarmup(searchService, warmupTenant),
    new CatalogWarmup(catalogService),
    new JsonSerializationWarmup(objectMapper)
);

ApplicationWarmup warmup = new ApplicationWarmup(scenarios);
warmup.run(20);
~~~

This example only shows how to organize workloads. The round count 20 is not a universal recommendation. Choose rounds based on JIT profiles, preparation duration, and post-restore measurements.

A production warm-up coordinator should add:

- Overall timeout and per-scenario timeouts.
- Duration logging per scenario.
- Concurrency limits.
- Safe stop on errors.
- Zero business side effects.
- Ensuring no warm-up threads remain running when checkpointing begins.

## 10. Measuring the JVM before checkpointing

Do not decide warm-up solely by elapsed runtime. Collect metrics that explain why performance changes.

### 10.1. JIT compilation time

The JVM provides CompilationMXBean in the Management API. Total compilation time can be read if the implementation supports it:

~~~java
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;

public final class JitMetrics {

    public static void printCompilationTime() {
        CompilationMXBean bean =
                ManagementFactory.getCompilationMXBean();

        if (bean != null && bean.isCompilationTimeMonitoringSupported()) {
            System.out.println(
                "JIT compilation time: "
                + bean.getTotalCompilationTime()
                + " ms"
            );
        }
    }
}
~~~

Increasing total compilation time is not necessarily bad. It shows the JVM spent time compiling. Combine it with latency and method compilation counts to judge whether warm-up is delivering benefits.

### 10.2. Monitoring memory pools and code cache

You can inspect memory pools exposed by the JVM:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;

public final class MemoryMetrics {

    public static void printPools() {
        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {

            System.out.println(
                pool.getName()
                + " used="
                + (pool.getUsage() == null
                    ? "unknown"
                    : pool.getUsage().getUsed())
            );
        }
    }
}
~~~

Memory pool names depend on the JVM and version. Some HotSpot builds expose pools with names related to Code Cache. Read actual names and usages instead of assuming fixed names.

### 10.3. Monitoring the heap

Basic heap info can be retrieved:

~~~java
Runtime runtime = Runtime.getRuntime();

long usedHeap = runtime.totalMemory() - runtime.freeMemory();
long committedHeap = runtime.totalMemory();
long maxHeap = runtime.maxMemory();
~~~

These values help observe committed heap and used heap at the time of measurement. They do not directly indicate checkpoint size. Measure both checkpoint artifacts and process memory footprint.

### 10.4. Monitoring JIT and GC with runtime tools

Depending on the JDK, Java Flight Recorder, compilation logging, GC logging, and JVM observability tools can be used to determine:

- Which methods were compiled during warm-up.
- Whether deoptimization or recompilation occurred.
- How many GC cycles ran.
- How many live objects remain on the heap after warm-up.
- Whether unnecessary threads or background activities exist.
- Whether code cache grows rapidly.

Flags and events can differ across JDK versions. Consult documentation for your exact CRaC JDK.

## 11. Test matrix across warm-up levels

To choose an appropriate level, create at least three profiles:

| Profile | Workload | Goal |
|---|---|---|
| A - Basic | Initialize framework and essential classes | Small, fast baseline |
| B - Targeted | Common request paths and critical caches | Balance latency and footprint |
| C - Deep | Near steady-state workload | Measure maximum achievable benefit |

For each profile, record:

| Measurement group | Metrics |
|---|---|
| Preparation | Startup, warm-up, drain, and checkpoint durations |
| JVM | JIT compilation time, code cache usage, GC count |
| Memory | Heap used/committed, live set, native memory if measurable |
| Artifact | Checkpoint directory/artifact size |
| Restore | Restore time and time to ready |
| Request | p50/p95/p99 latency, throughput, error rate |
| Stability | Cache misses, reconnects, deoptimization, and post-restore compilation |

Example illustrative results table, not real benchmark figures:

| Metric | Basic | Targeted | Deep |
|---|---:|---:|---:|
| Warm-up duration | 10 s | 45 s | 180 s |
| Checkpoint duration | 4 s | 5 s | 8 s |
| Image size | 100 MB | 125 MB | 175 MB |
| Restore-to-ready | 2.8 s | 1.9 s | 1.7 s |
| First-request p95 | 420 ms | 180 ms | 155 ms |

In the example, moving from Basic to Targeted brings clear improvement. Moving from Targeted to Deep brings little additional gain while substantially increasing warm-up duration and image size. In that case, Targeted may be the more balanced choice.

The numbers in the table merely illustrate how to compare. Do not use them as performance targets for real applications.

## 12. Measuring image size and checkpoint creation time

Checkpoints may be stored as a set of files or a directory depending on the tool. Do not measure only one representative file if the image consists of multiple components.

Record:

- Total size of all files belonging to the checkpoint.
- Number of files.
- Duration from checkpoint start until completion.
- Process freeze duration if reported by the tool.
- Compressed or packaged size if deployment stores artifacts as archives.
- Checkpoint upload/download duration.
- Storage capacity across multiple retained versions.

Distinguish raw image size from compressed archive size. Compression can alter storage footprint yet also consumes CPU and packaging/unpacking time.

One warm-up profile may increase live heap with memory pages that compress well. Another profile may produce high-entropy data that compresses poorly. Therefore, looking at heap usage alone is insufficient to predict artifact size.

## 13. Factors causing warm-up results to differ across environments

### 13.1. Different JDK or JVM flags

JIT compiler, GC, tiered compilation, and code cache can change across JDK versions, vendors, architectures, and JVM flags.

A checkpoint created with one JVM configuration and restored under another may be unsupported or behave differently. Follow CRaC JDK compatibility requirements and build images in an environment matching the restore target.

### 13.2. Different CPU and architecture

JIT compiles into machine code tailored to the CPU. Differences in architecture or CPU features can affect compatibility and performance.

Do not assume checkpoints can be distributed arbitrarily across hosts with different architectures. Verify runtime and deployment platform constraints.

### 13.3. Different real workloads

If warm-up represents only read traffic while production has heavy write operations, JIT profiles and caches may be mismatched. Similarly, a test workload with small payloads may fail to warm code paths handling large data.

Update warm-up profiles when traffic distributions or application versions change.

### 13.4. Changing data and configuration

Warm-up may populate caches or static state tied to the image-building environment. If restored in another environment, those values may no longer be accurate.

Do not bake frequently changing endpoints, credentials, or feature flags into retained state without a post-restore validation step. Refresh environment-dependent configuration before opening readiness.

## 14. Risks of warming up too deeply

### 14.1. Unrepresentative profiles

Warm-up using trivial data or a single branch can cause JIT to optimize under assumptions unsuitable for real traffic. Some assumptions may be invalidated, leading to deoptimization.

Use representative data and observe post-restore behavior. Do not optimize for a microbenchmark that does not reflect production workloads.

### 14.2. Overly stale cached data

If a checkpoint is retained long before restore, caches loaded during warm-up may go stale. TTL, versioning, and refresh policies are needed.

### 14.3. Business side effects

Warm-up invoking real code paths can create data, emit events, or alter systems. Use sandboxes or dedicated warm-up modes and verify no unintended side effects occur.

### 14.4. Background tasks continuing to run

Schedulers, executors, and refresh threads may still be running at checkpoint time. They can hold locks, connections, or unsafe state. Stop and drain them via appropriate lifecycle resources.

### 14.5. Preparation time exceeding benefits

If each checkpoint build takes many minutes while restore improves by only a few hundred milliseconds, total cost may not make sense. Evaluate how many restores each image serves and actual scale-out costs.

## 15. Strategy for selecting warm-up levels by workload

| Application type | Level to try first | Reason |
|---|---|---|
| API service with a few hot endpoints | Targeted | Focuses on frequently used processing paths |
| Spring Boot service with many beans | Basic then Targeted | Framework initialization can dominate startup |
| CPU-bound service | Targeted or Deep | JIT profiles can yield clear benefits |
| Read-heavy service with large caches | Targeted | Warms popular keys, avoids loading the entire cache |
| Batch worker | Targeted per job kind | Warms parsers, mappers, and primary processing paths |
| Service with many plugins or rare endpoints | Basic and lazy initialization | Avoids warming unused plugins |
| Very short-lived instances scaling continuously | Measure Targeted carefully | Balances image build cost against restore count |

This is only a starting point for designing experiments. Your own application's benchmark results are the basis for selection.

## 16. Decision rules

Use the following questions to decide whether to increase the warm-up level:

1. Is the first request after restore noticeably slower than steady state?
2. Does that latency come from JIT, class initialization, cache misses, or connections?
3. Has the current warm-up already executed critical code paths?
4. Does increasing warm-up reduce post-restore p95/p99?
5. Is the improvement large enough relative to added preparation time?
6. How much does image size grow and how does it affect distribution time?
7. Are any unnecessary cached data or threads retained?
8. Does the warm-up profile reflect production workloads?
9. Is the image restored in a compatible environment?
10. Can a smaller set be warmed while preserving most of the benefit?

A pragmatic rule is choosing the lowest warm-up level that still meets latency and readiness goals. If raising the warm-up level does not improve key metrics or pushes footprint over limits, stay at the lower level.

## 17. Post-warm-up checkpoint preparation checklist

### Workload and JIT

- [ ] Warm-up covers critical code paths.
- [ ] Payloads and call frequencies represent the workload.
- [ ] No unintended business side effects are produced.
- [ ] Observed JIT compilation and post-restore latency.
- [ ] Avoided warming rare code paths without reason.

### Heap and caches

- [ ] Caches are bounded in size.
- [ ] Stale-prone data has TTL or versioning.
- [ ] Unreferenced temporary objects are allowed to be reclaimed.
- [ ] Short-lived transactions or connections are not retained in caches.
- [ ] Essential caches are refreshed per policy after restore.

### Threads and resources

- [ ] Warm-up generator is stopped.
- [ ] Background tasks are drained or paused.
- [ ] Executors have explicit lifecycles.
- [ ] Network connections are closed or re-prepared per CRaC Resource.
- [ ] No unnecessary warm-up threads remain.

### Checkpoint and measurement

- [ ] Measured warm-up duration and checkpoint duration separately.
- [ ] Measured total size of all checkpoint artifacts.
- [ ] Measured restore-to-ready and first-request latency.
- [ ] Tested at least Basic, Targeted, and Deep.
- [ ] Verified image in the target restore environment.
- [ ] Selected warm-up level based on measurements and operational limits.

## 18. Frequently asked questions

### Does a longer warm-up always make the restored application faster?

No. Benefits typically diminish once critical code paths have been warmed. Additional warm-up may mainly increase preparation time, CPU, caches, and image size without significantly improving latency.

### Does warm-up increase checkpoint size?

Possibly. Live caches, code cache, metadata, thread state, and native memory can increase footprint. However, temporary allocations reclaimed by GC do not necessarily enlarge the image proportionally. Measure actual artifacts.

### Do we need to run every endpoint before checkpointing?

No. Prioritize endpoints and code paths that are critical by traffic and business requirements. Rare features can be lazily initialized after restore if acceptable.

### Does JIT preserve all compiled code after restore?

Do not assume every compiled state is always retained and continues optimizing identically. Behavior depends on the JDK, CRaC implementation, and restore conditions. Observe compilation and latency after restore on the exact target runtime.

### Should System.gc() be called before checkpointing to shrink the image?

Do not treat it as a mandatory step. GC can reclaim dead objects, yet forcing it can increase preparation time and does not guarantee reducing artifact size proportionally. Measure live heap and image size before deciding.

### Can warm-up use real production traffic?

Only when the system is designed to guarantee no unintended side effects occur and data does not alter business state. Normally, use warm-up mode, test tenants, read-only requests, or sandbox data.

### Why is the image larger yet restore is no faster?

Warm-up may have increased caches and memory footprint without warming additional meaningful code paths. Post-restore cost might also come from external dependencies, DNS, authentication, or caches needing refresh. Break latency down by phase rather than just increasing warm-up time.

### Should one checkpoint be created for each warm-up level?

During testing, create comparable profiles. Each profile needs the same JDK, JVM flags, configuration, and measurement workload. Once a suitable level is chosen, promote that profile into the standard checkpoint build workflow.

## Conclusion

Warm-up helps prepare classes, frameworks, JIT profiles, code cache, and cached data before CRaC saves process state. Deeper warm-up can reduce post-restore latency, yet also increases preparation time, CPU, and checkpoint footprint. Benefits typically diminish once critical code paths have been executed and optimized.

Start with basic warm-up, then add representative workloads for common processing paths. Measure warm-up duration, checkpoint duration, image size, restore-to-ready, first-request latency, and initial-phase performance separately. Choose the lowest level meeting operational goals, while controlling caches, threads, connections, and side effects before creating the image.