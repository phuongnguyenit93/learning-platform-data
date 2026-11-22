
# Changes to the Default Garbage Collector and Unsupported GCs

Upgrading Java does not only change language syntax, APIs, or bytecode formats. For a long-running system, the JVM's **Garbage Collector (GC) and GC selection mechanism** can directly affect response times, CPU usage, memory usage, application pause times (*stop-the-world pauses*), scalability, and service stability.

A Java 8 application that once ran smoothly on **Parallel GC** may switch to **G1 GC** when upgraded to a newer JDK without specifying a collector explicitly. A configuration retaining `-XX:+UseConcMarkSweepGC` can prevent a new JVM from starting because **Concurrent Mark Sweep (CMS) has been removed**. At the same time, GC logging options, how the JVM detects container memory/CPU, and available GC algorithms per distribution can also change.

The key point to understand in *Java Advance Compatibility Migration*, chapter *JVM and Performance*, is: **GC compatibility is not just "whether the application runs or not"**. A proper migration identifies the active collector, removes unsupported flags, tests realistic workloads, and records the impact on both throughput and tail latency.

This lesson primarily uses **HotSpot/OpenJDK-based JVM** terminology and examples. Other JVMs, such as OpenJ9, have different GC names, flags, and selection strategies; do not mechanically apply every HotSpot example to them.

## 1. What is GC and why can changing GC alter application behavior?

A Garbage Collector manages reclaiming memory from Java objects that are no longer reachable. However, GC is not merely a random "cleanup" task running occasionally. The collector must coordinate with application threads to:

- Track or identify the live referenced object graph.
- Locate objects that are no longer reachable.
- Reclaim or reuse memory regions.
- Occasionally move objects to prevent fragmentation.
- Coordinate with operations requiring heap consistency.
- Throttle GC work and CPU/memory resource usage.

Depending on the algorithm, part of the work runs while **application threads pause** (*stop-the-world, STW*) or **concurrently** with the application (*concurrent*). Collectors typically balance three competing objectives:

1. **Throughput:** percentage of CPU time dedicated to useful application work.
2. **Latency:** duration and distribution of pauses caused by GC or related runtime mechanisms.
3. **Memory footprint:** amount of heap and auxiliary memory needed to achieve the two goals above.

There is no single "fastest" collector for all workloads.

### 1.1. Throughput and pause times differ

Suppose a batch job processes 100,000 records/second with low total GC time yet occasionally pauses for a few hundred milliseconds. That may suit batch throughput.

Conversely, an online request-handling API may require low 99th-percentile (**p99**) latency. A collector with multiple short pauses may be a better fit than one achieving high throughput while occasionally introducing long pauses.

Do not measure only "total GC count":

| Metric | What it reflects | Limitation if viewed alone |
|---|---|---|
| Application throughput | Useful work completed | Can look good even with bad tail latency |
| GC pause p50/p95/p99/max | Distribution of pause durations | Does not show full CPU overhead |
| Total GC time | Time spent in GC over a measurement window | May omit concurrent CPU impact |
| Allocation rate | Rate of object creation | Does not measure live set directly |
| Live set/old occupancy | Long-lived data | Needs comparison against heap sizing |
| CPU utilization | Whole-process processing cost | Can suffer container throttling |
| RSS/native memory | Total memory used by the process | Differs from heap used and `-Xmx` |
| Request p99 | End-to-end application latency experience | Also depends on network, DB, locks, and I/O |

### 1.2. GC is a JVM choice, not an immutable Java SE API

No Java SE specification rule guarantees every JVM uses G1 or Parallel GC. Collector selection depends on **JVM implementation, version, platform, resources, and flags**.

Therefore:

- Never assume every Java 8 environment uses Parallel GC.
- Never assume every Java 17 or Java 21 environment always uses G1.
- Never assume the same `java -version` major release picks the same collector across all vendors/builds.
- Never infer the active collector from POM or Gradle settings if startup scripts differ.
- Never treat mentioning a GC in JDK docs as proof a specific build supports it.

## 2. Common collectors in HotSpot

### 2.1. Serial GC

**Serial GC** uses a simple approach suited for small heap setups or CPU-constrained environments. Certain collection phases use fewer GC threads than parallel collectors.

It is often selected explicitly or picked by the JVM under low-resource conditions, yet actual selection must be observed on the real runtime.

Typical HotSpot flag:

~~~bash
java -XX:+UseSerialGC -jar app.jar
~~~

"Serial" does not mean it is always slow; on small workloads, complex collector overhead may be unnecessary. However, it is not designed to meet the same latency targets as concurrent collectors on large heaps.

### 2.2. Parallel GC

**Parallel GC** focuses on throughput, using multiple threads for corresponding collection phases.

Typical flag:

~~~bash
java -XX:+UseParallelGC -jar app.jar
~~~

This is a common choice for batch jobs and workloads that tolerate pauses while needing maximum throughput. Do not interpret "Parallel" as having zero stop-the-world pauses; key collection phases still pause the application.

### 2.3. G1 GC

**Garbage-First (G1) GC** divides the heap into regions and plans collections around a pause target using both concurrent work and STW phases. G1 is designed to balance throughput with pause-time predictability across a wide range of heap setups.

Typical flag:

~~~bash
java -XX:+UseG1GC -jar app.jar
~~~

G1 is a common HotSpot default across many modern JDK setups. However, `-XX:MaxGCPauseMillis` is a **tuning goal**, not an SLA or hard pause cap.

### 2.4. Concurrent Mark Sweep (CMS)

**CMS** was a historical collector aiming to reduce long pauses through concurrent marking/sweeping, often seen in older Java 8 configurations:

~~~text
-XX:+UseConcMarkSweepGC
~~~

CMS was **deprecated in JDK 9** and **removed in JDK 14**. Consequently, startup configs once valid on older JDKs may fail to start newer HotSpot JVMs.

Treat CMS as legacy technology in modern migrations. Do not attempt keeping `UseConcMarkSweepGC` or CMS tuning flags as a long-term strategy.

### 2.5. ZGC

**Z Garbage Collector (ZGC)** targets very short pauses by doing most work concurrently with application threads. Common flag on supporting HotSpot builds:

~~~bash
java -XX:+UseZGC -jar app.jar
~~~

ZGC appeared as an experimental feature in earlier releases and became a production feature in JDK 15 via JEP 377. Generational (*generational*) features and mode selection flags for ZGC continued evolving in subsequent JDKs; never assume one set of flags behaves identically across all versions.

ZGC is not automatically optimal for every small batch job. Evaluate CPU headroom, memory footprint, and throughput alongside pause times.

### 2.6. Shenandoah

**Shenandoah GC** also targets low pauses via concurrent work, included in certain OpenJDK-based builds:

~~~bash
java -XX:+UseShenandoahGC -jar app.jar
~~~

Shenandoah was introduced as an experimental collector in JDK 12 (JEP 189) and moved to production status in JDK 15 (JEP 379) in builds/distributions supporting it. Not all distributors or platforms bundle, enable, or support Shenandoah identically.

### 2.7. Directional comparison table

| Collector | Typical focus | Migration considerations |
|---|---|---|
| Serial | Simplicity, low overhead in small setups | Pauses can grow on large heaps/workloads |
| Parallel | Throughput | STW pauses may exceed API latency targets |
| G1 | Balance between throughput and pause times | Heuristics, region sizing, and pause targets vary across versions |
| CMS | Legacy low-pause | Removed from HotSpot since JDK 14 |
| ZGC | Very low pause | Verify availability, modes, and CPU/memory overhead |
| Shenandoah | Low pause / concurrent work | Depends on distribution/build and version |

This table is **directional**, not a performance ranking or a guarantee one collector always wins.

## 3. Notable GC milestones across JDK upgrades

The milestones below reflect common OpenJDK/HotSpot developments; individual vendors may include backports, policy differences, or alternative JVM implementations.

| JDK / phase | Key development | Migration significance |
|---|---|---|
| JDK 8 and earlier | Parallel GC commonly default on many server-class machines; CMS selectable explicitly | Record actual configuration rather than guessing by version |
| JDK 9 | G1 becomes default collector on qualifying HotSpot setups (JEP 248) | Applications omitting GC flags may switch collectors |
| JDK 9 | CMS marked deprecated (JEP 291) | Begin planning removal of CMS and its tuning |
| JDK 9 | Unified JVM Logging introduced | Must update legacy GC log collection and parsing |
| JDK 11 | ZGC available experimentally on supported platforms/builds | Do not assume universal availability |
| JDK 12 | Shenandoah available experimentally in supporting builds | Verify build support and activation flags |
| JDK 14 | CMS removed (JEP 363) | Legacy `UseConcMarkSweepGC` configs can break JVM startup |
| JDK 15 | ZGC and Shenandoah reach production status in supporting builds | Additional low-pause options become production-ready |
| JDK 17 | G1 commonly selected by default on server-class HotSpot unless overridden | Java 8 → 17 migration requires re-evaluating GC |
| JDK 21 | G1 remains a common HotSpot default; Generational ZGC introduced (JEP 439) | Do not confuse ZGC selection flags with generational mode flags across releases |
| Subsequent releases | Algorithms, modes, and flags may continue evolving | Verify on exact vendor/build rather than copying old tables |

**Important takeaway:** changing the default does not mean Parallel GC was removed. Parallel, G1, and Serial continue coexisting, whereas **CMS was genuinely removed** from HotSpot in JDK 14.

### 3.1. Why did JDK 9 make G1 default?

JEP 248 changed the default collector to G1 to improve pause-time behavior for typical applications without requiring manual GC selection. Still, that is **default ergonomics**, not a promise G1 wins on throughput everywhere.

A batch job heavily tuned for Parallel GC may need to pin Parallel explicitly after benchmarking. Conversely, a p99-sensitive API may benefit from default G1 yet still needs measurement under realistic workloads.

### 3.2. CMS deprecated vs. CMS removed

**Deprecated** means the feature carries warnings discouraging further reliance while potentially still working in that release.

**Removed** means the implementation or selector flag is no longer provided in the legacy form. When moving to a JDK where CMS is removed, applications must drop or replace CMS configuration.

This distinction shapes migration planning:

1. While deprecated, gather benchmarks on replacement candidates.
2. Locate every source of CMS flags.
3. Switch collectors and review heap and tuning strategy.
4. Remove obsolete CMS flags.
5. Verify startup and runtime behavior on the target JDK.

Never wait until production JVMs fail to boot before addressing deprecation.

## 4. Changing the default GC is not identical to changing flags

Example command without specifying a GC:

~~~bash
java -Xms1g -Xmx2g -jar orders.jar
~~~

The JVM picks a collector based on heuristics and runtime configuration. Upgrading the JDK can change what it picks.

An explicit command:

~~~bash
java -XX:+UseG1GC -Xms1g -Xmx2g -jar orders.jar
~~~

declares intent to use G1, though you must still confirm the collector is supported and accepted by the JVM.

### 4.1. When should you let the JVM choose the default?

Allowing the default can make sense when:

- The product has no specific collector mandate.
- Workloads have been validated on the target JDK/runtime.
- No special tail-latency, throughput, or footprint policies require another collector.
- Post-update monitoring and evaluation plans are in place.
- Runtime environments and resource limits are governed consistently.

Advantage: minimal config and automatic benefit from JVM ergonomics improvements. Drawback: the selected collector can shift when JDKs or container limits change.

### 4.2. When should you specify a GC explicitly?

Pinning a collector makes sense when:

- Benchmarks prove a specific collector meets targets better.
- Strict tail-latency commitments exist for given workloads and heaps.
- The product needs consistent collector behavior across a JDK transition.
- Special interactions with plugins/agents/providers must be tested.
- Rollout plans isolate JDK upgrades from GC changes.

However, **pinning a GC does not freeze all heuristics**. Even G1 across two JDKs can differ in region sizing, remembered sets, scheduling, logging, or memory footprint. Always re-measure on the target JDK.

### 4.3. Defaults can be affected by available resources

On JVMs implementing server-class machine detection or container awareness, CPU counts, available memory, and visible resource limits affect collector, heap, and GC thread ergonomics.

Therefore, the same JDK on a 32-core host may behave differently inside a tightly constrained container. Never write "Java 17 guarantees G1 in every Pod" without inspecting runtime logs.

## 5. How to verify which GC is actually running

This is a mandatory check before and after migration.

### 5.1. Check JVM startup logs

On modern HotSpot:

~~~bash
java -Xlog:gc=info -version
~~~

In many builds, logs display the selected collector, such as a line resembling:

~~~text
[info][gc] Using G1
~~~

This is an illustrative example. Exact tag names or messages may vary by JDK and config.

If more startup detail is needed:

~~~bash
java -Xlog:gc+init=info -version
~~~

`java -version` confirms only the runtime version. **GC logs or runtime flags identify the chosen collector.**

### 5.2. Inspect command-line flags

On HotSpot:

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

And to inspect flags after JVM ergonomics run:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

The output can be long. Filter with shell tools:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E 'UseG1GC|UseParallelGC|UseSerialGC|UseZGC|UseShenandoahGC'
~~~

On PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String 'UseG1GC|UseParallelGC|UseSerialGC|UseZGC|UseShenandoahGC'
~~~

Check the **flag values**, not merely whether the flag name appears. `UseG1GC = false` does not mean G1 is active.

### 5.3. Inspect a running JVM with jcmd

When process diagnostics are permitted:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

`VM.command_line` reveals launcher arguments, while `VM.flags` inspects active or visible flags. `GC.heap_info` can expose heap and collector info depending on the JVM.

Other `jcmd` commands can incur notable overhead or require elevated permissions. Avoid running heavy diagnostics in production without evaluating cost.

### 5.4. Using MXBeans from Java

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public final class GcRuntimeInfo {
    public static void main(String[] args) {
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("name=" + bean.getName());
            System.out.println("collections=" +
                    bean.getCollectionCount());
            System.out.println("collectionTimeMs=" +
                    bean.getCollectionTime());
        }
    }
}
~~~

Bean names typically indicate specific collector spaces/phases (such as young/old), yet **this is not a standardized API returning one uniform GC ID across every JVM**. Certain metrics may return `-1` if unsupported by the JVM.

Never hard-code MXBean string names into business rules or automatic collector-switching logic.

### 5.5. Never log sensitive data

Dumping full JVM command lines can expose arguments holding tokens, passwords, or internal URLs. Observability pipelines should extract **needed JVM GC flags** and redact sensitive data before saving or sharing.

## 6. Legacy CMS flags can break startup

Many Java 8 systems use startup templates like:

~~~bash
java \
  -XX:+UseConcMarkSweepGC \
  -XX:CMSInitiatingOccupancyFraction=70 \
  -XX:+UseCMSInitiatingOccupancyOnly \
  -Xms2g \
  -Xmx2g \
  -jar orders.jar
~~~

On JDKs that removed CMS, related options are unrecognized or unsupported. The JVM can exit before application code ever executes.

A typical message:

~~~text
Unrecognized VM option 'UseConcMarkSweepGC'
Error: Could not create the Java Virtual Machine.
~~~

Exact wording and exit behavior depend on release and vendor, yet **startup failure** is a real risk.

### 6.1. Legacy flags to search for

Names commonly found in older systems:

| Flag / group | Relevance | Migration action |
|---|---|---|
| `-XX:+UseConcMarkSweepGC` | Selects CMS | Remove and select a currently supported collector |
| `-XX:+UseParNewGC` | Legacy young-generation option | Verify validity on target JDK; never carry over blindly |
| `-XX:CMSInitiatingOccupancyFraction=...` | CMS scheduling | Drop if CMS is removed; never copy straight to G1 |
| `-XX:+UseCMSInitiatingOccupancyOnly` | CMS initiation policy | Remove and re-evaluate tuning goals |
| `-XX:+CMSClassUnloadingEnabled` | Legacy CMS flag | Do not assume it is still needed or valid |
| `-XX:+ExplicitGCInvokesConcurrent` | Explicit-GC handling | Verify semantics per collector/JDK rather than keeping out of habit |
| `-XX:+UseG1GC` | Selects G1 | Widely supported, yet requires testing |
| `-XX:+UseParallelGC` | Selects Parallel | Widely supported, not an automatic CMS replacement |
| `-XX:+UseSerialGC` | Selects Serial | Use only when workload fits |
| `-XX:+UseZGC` | Selects ZGC | Check availability and flags per JDK |

Not every flag in the table was removed in the exact same release. The table helps **classify legacy flags**, which must then be verified against official docs and actual runtimes.

### 6.2. Do not simply swap one CMS line for G1

Mistake:

~~~text
Remove -XX:+UseConcMarkSweepGC
Add -XX:+UseG1GC
Keep all CMS tuning unchanged
~~~

Collectors differ in heap layout, heuristics, and tuning meaning. Many CMS-specific flags have no relevance to G1 or are rejected outright.

A better approach:

1. Strip out all CMS-specific selector and tuning flags.
2. Keep general bounds such as `-Xmx` where appropriate.
3. Run G1 with defaults before applying custom tuning.
4. Capture baseline pauses, throughput, and memory footprint.
5. Add G1 tuning flags only with concrete evidence.
6. Canary and compare under matching workloads.

### 6.3. Why is IgnoreUnrecognizedVMOptions dangerous?

Some JVMs offer options to ignore unrecognized flags. Never use flags such as `-XX:+IgnoreUnrecognizedVMOptions` to "mass-fix" startup failures.

Silently ignoring options can:

- Hide configurations that silently stopped taking effect.
- Cause an unintended collector to be selected.
- Leave wrong assumptions about heap/GC in place.
- Create drift across environments.
- Suppress vital failure signals during migration.

For GC selection or memory safety, **failing loudly** is generally safer to control than silently ignoring critical flags.

## 7. Locate all sources of JVM GC flags

A GC flag does not always live in the primary startup script. It can come from:

- `JAVA_OPTS` or variables injected by service wrappers/frameworks.
- `JAVA_TOOL_OPTIONS`.
- `JDK_JAVA_OPTIONS` on supporting launchers.
- `_JAVA_OPTIONS` where used in legacy environments.
- Dockerfiles or container entrypoints.
- Kubernetes Deployments, Helm values, and Kustomize overlays.
- Systemd units and Windows service configurations.
- CI/CD jobs, test runners, and integration test tasks.
- Maven Surefire/Failsafe `argLine`.
- Gradle `Test` or `JavaExec` `jvmArgs`.
- Application server or plugin-host scripts.
- PaaS platforms injecting JVM options.
- IDE run configurations or profile scripts.

Search the repository with ripgrep:

~~~bash
rg -n --hidden --glob '!**/.git/**' -- \
  'UseConcMarkSweepGC|UseParNewGC|CMSInitiating|UseG1GC|UseParallelGC|UseZGC|UseShenandoahGC|PrintGC' .
~~~

Searching source repositories is only step one. Compare findings against **actual JVM arguments** of running processes. Servers often assemble variables and flags across multiple layers.

### 7.1. Watch out for overlapping configurations

A flag baked into a Docker image can be overridden by or conflict with a deployment manifest. The exact same app might run G1 in tests and Parallel in production without the team noticing.

When auditing, build an inventory table:

| Source | Environment | GC flag | JVM version | Owner |
|---|---|---|---|---|
| Gradle Test task | CI | Explicit G1 | Build JDK | Build team |
| Docker entrypoint | Staging | None | Runtime JDK | Platform |
| Helm values | Production | Parallel | Runtime JDK | SRE |
| App server startup | Batch | Legacy CMS | Old runtime JDK | Ops |

Rows above are management examples only, not recommended settings.

## 8. GC logging also changes across JDK upgrades

Since JDK 9, **Unified JVM Logging** is the standard framework for runtime logging, including GC logs.

Legacy Java 8 GC logging configs often contain:

~~~text
-verbose:gc
-XX:+PrintGCDetails
-XX:+PrintGCDateStamps
-Xloggc:/var/log/app/gc.log
-XX:+UseGCLogFileRotation
-XX:NumberOfGCLogFiles=5
-XX:GCLogFileSize=20M
~~~

Some legacy options may map with warnings or cease working depending on the JDK. Never retain the entire legacy block without checking.

### 8.1. Unified Logging example

On modern HotSpot:

~~~bash
java \
  -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -Xms1g \
  -Xmx2g \
  -jar app.jar
~~~

This is a structural example; the `logs` directory must exist and the process must have write permissions.

Components:

- `gc*`: selects all GC-related log tags using Unified Logging wildcards.
- `safepoint`: adds selected safepoint events.
- `file=...`: destination file.
- `time,uptime,level,tags`: decorators.
- `filecount` and `filesize`: output rotation settings.
  
Verify syntax and tag levels against your exact JDK. Command:

~~~bash
java -Xlog:help
~~~

prints the logging capabilities of that runtime.

### 8.2. GC log formats are not an immutable API

A custom parser or dashboard built for Java 8/CMS GC logs may fail to understand JDK 17 G1 logs or ZGC logs.

Risks:

- Log parsers fail to match events.
- Dashboards report 0 pauses even while the JVM executes GCs.
- Legacy alert patterns stop triggering.
- Before/after pause histograms get compared inaccurately.
- Concurrent phases get misclassified as STW pauses.
- Milliseconds vs. seconds unit mismatches.

During migration, upgrade **logging pipelines and dashboards** alongside the runtime rather than changing JVM flags alone.

### 8.3. Which log data should be collected?

Minimum data for benchmarks:

- GC start/end timestamps and duration.
- Pause cause and type.
- Heap before/after, committed size, and capacity.
- Young/old collection events where the collector uses those spaces.
- Concurrent phase durations.
- Allocation pressure and memory occupancy.
- Safepoint durations when affecting latency.
- CPU context and container resource limits.

Never use raw pause count between two architecturally different collectors as a single quality metric.

## 9. Heap sizing and GC are coupled decisions

Common flags:

~~~bash
java -Xms1g -Xmx4g -jar app.jar
~~~

- `-Xms`: initial Java heap size.
- `-Xmx`: maximum Java heap size.

These do not govern a process's total memory footprint. Beyond the Java heap, processes allocate:

- Metaspace and class metadata.
- Thread stacks.
- Direct/native buffers.
- JIT code cache.
- Native GC structures.
- JNI/native libraries.
- Other runtime/framework memory.

A 4 GiB container limit does not mean `-Xmx4g` is safe. Processes always need **native headroom**.

### 9.1. Changing GC can change memory overhead

Each collector maintains its own metadata, thread pools, and concurrent machinery. Even with identical `-Xmx`, RSS, peak memory, and CPU differ.

In G1, remembered sets and region metadata consume extra memory. In ZGC/Shenandoah, concurrent machinery and memory mapping can show different signatures in OS metrics.

Do not conclude "collector A uses less RAM than collector B" from a point-in-time `heap used` value alone. Measure **RSS, heap, native memory, and workload** together.

### 9.2. Is setting Xms equal to Xmx always better?

No. Setting `-Xms` equal to `-Xmx` reduces heap resizing in some workloads yet can increase memory footprint, committed memory, and impact startup or multi-tenant resource sharing.

The choice depends on:

- Latency requirements.
- Container memory limits.
- Startup/warmup behavior.
- Whether multiple JVMs share one node.
- Live set and allocation rate.
- Chosen collector.
- Memory commit/uncommit mechanics of that JVM/GC version.

Measure rather than applying one blanket rule.

### 9.3. MaxRAMPercentage and containers

HotSpot offers ergonomic sizing options such as:

~~~bash
java -XX:MaxRAMPercentage=65.0 -jar app.jar
~~~

Exact behavior depends on how the JVM computes available RAM. On modern JDKs with container awareness, cgroup limits can influence heap sizing and GC thread counts.

Do not combine multiple heap-sizing mechanisms without understanding precedence. When `-Xmx` is set explicitly, it overrides maximum heap calculations and can invalidate expectations set for `MaxRAMPercentage`.

## 10. Container awareness and CPU ergonomics

After moving an application onto Kubernetes or upgrading the JDK inside containers, GC behavior can shift even with similar-looking configs.

HotSpot JDKs often support detecting container limits via `-XX:+UseContainerSupport` (enabled by default in many modern releases). Support details, cgroup handling, and backports differ across releases and vendors.

In containers, record:

- CPU limits/quotas and CPU requests.
- Memory limits.
- cgroup version.
- JVM-reported active processor count.
- Actual maximum heap.
- GC and concurrent worker thread counts.
- CPU throttling statistics.
- RSS and `OOMKilled` events.

### 10.1. How do CPU limits affect GC?

Concurrent collectors use CPU cycles to mark/reclaim concurrently with application threads. When a container experiences CPU throttling, background GC can fall behind allocation rates, increasing latency or triggering allocation stalls.

G1, Parallel, and ZGC organize worker threads differently. Increasing GC thread counts will not improve performance if the container lacks CPU quota.

For controlled experiments, HotSpot may offer:

~~~text
-XX:ActiveProcessorCount=4
~~~

This flag alters how heuristics observe processor count; use it intentionally and validate on the matching JDK. Never expect it to "create extra physical CPU" beyond container quotas.

### 10.2. Why can the same JDK select different GCs?

When a JVM detects very small CPU/memory resources, ergonomics may pick a different collector than on a large multi-CPU server. Therefore, knowing only the JDK version never gives 100% certainty of the default collector.

Every benchmark result must record the **runtime resource profile**, not just `java -version`.

## 11. Comparing GCs against workload and SLO

Before switching collectors, clarify product requirements.

### 11.1. Batch / throughput-oriented

A data-processing job may prioritize:

- Total completion duration.
- Record/s throughput.
- CPU efficiency.
- Stable heap occupancy.
- Zero OOMs on large datasets.

When p99 request latency is not a primary goal, Parallel GC remains a valid benchmark candidate on supporting JDKs.

### 11.2. Online API / tail-latency-oriented

Latency-sensitive APIs typically prioritize:

- p95/p99/p99.9 response times.
- GC pause durations.
- Fraction of requests impacted by pauses.
- Error rates, timeouts, and retry amplification.
- Latency under peak load and autoscaling events.

G1 or low-pause collectors can fit depending on workloads, yet conclusions require benchmarking. Never assert "ZGC is always optimal for APIs" if CPU headroom, heap sizing, or throughput goals are unmet.

### 11.3. Memory-constrained services

When packing many small JVMs onto a node, goals may include:

- Small RSS footprint.
- Avoiding OOMKills.
- Fast startup.
- Few background worker threads.
- Adequate throughput.

Serial or G1 can fit depending on constraints. Do not pick a complex low-latency collector by default just because it is "newest".

## 12. MaxGCPauseMillis is a target, not a guarantee

A common G1 setup:

~~~bash
java \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -Xms2g \
  -Xmx4g \
  -jar app.jar
~~~

`MaxGCPauseMillis` is a **target** guiding GC ergonomics to size collection increments appropriately. It does not force every pause under 200 ms, nor does it cap HTTP request latency.

Setting it overly low can cause:

- More frequent GC pauses.
- Lower application throughput.
- Higher memory pressure.
- Increased background/concurrent CPU load.
- Occasional full GCs or unrelated long safepoints.

Tune using full pause distributions and SLOs rather than lowering this value endlessly.

### 12.1. Full GCs differ from young/mixed pauses

For G1 especially, separate:

- Young evacuation pauses.
- Mixed collection pauses.
- Concurrent marking/cleanup phases.
- Full GCs or fallback modes requiring larger STW pauses.
- Non-GC safepoints that should not always be misattributed to GC pauses.

If dashboards lump everything into "GC pause", root causes blur. Long full GCs demand inspecting allocation pressure, live set, evacuation failures, humongous objects, heap sizing, and fragmentation per collector/JDK.

### 12.2. Allocation rate and live set

Applications allocating many short-lived objects may trigger steady GCs while still meeting latency targets. Applications retaining large long-lived object graphs pressure the old generation and leave little room to reclaim.

Consequently, GC optimization often requires fixing application code:

- Cache sizes and TTLs.
- Object retention leaks.
- Oversized temporary allocations.
- Batch buffer lifetimes.
- Direct buffer usage.
- Retained `ThreadLocal` data.
- Memory-heavy data structures.

**Switching GCs cannot cure logical memory leaks.** It may shift symptoms or failure timing, yet reachable data never disappears by itself.

## 13. ZGC and Shenandoah: lower pauses are not free

Low-pause collectors aim to move work out of STW pauses. Common trade-offs include:

- Extra CPU headroom required for concurrent phases.
- Extra memory headroom potentially required.
- Runtime barrier/coordination overhead with application threads.
- Throughput potentially differing from throughput-focused collectors.
- Different native memory and OS accounting patterns.
- Generational modes altering how short-lived vs. long-lived objects behave.
- Availability varying by JDK distribution and build flags.

### 13.1. Do not compare a tuned ZGC config with an old CMS config indiscriminately

CMS has been removed and old configs often accumulate legacy tuning flags. When benchmarking new collectors:

- Use the exact same JDK version (where both collectors exist) to isolate the GC variable.
- Keep artifacts, dependencies, and input datasets identical.
- Keep CPU/memory resource limits equivalent.
- Allow proper JVM/JIT warmup.
- Run multiple repeated iterations.
- Report throughput, tail latency, RSS, and CPU together.
- Separate JVM upgrade effects from GC replacement effects.

### 13.2. Generational ZGC

JDK 21 introduced **Generational ZGC** as an option when running ZGC. Historical example on a JDK supporting that mode:

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -jar app.jar
~~~

Never treat this flag pair as permanent across all newer Java releases. Mode selection and flag availability evolve as ZGC develops in subsequent releases. Inspect `java -XX:+PrintFlagsFinal -version`, release notes, and startup logs of the **target JDK**.

Once a generational mode becomes default or a legacy flag is removed, leaving the old flag can become redundant or break startup. The same discipline applies to all GC flags.

## 14. Process for inventorying and replacing GC in legacy applications

A practical migration checklist can follow staged phases.

~~~mermaid
flowchart TD
    A["Record JDK, collector, flags, and workload baseline"] --> B["Find legacy flags and config sources"]
    B --> C["Select supported target JDK/GC"]
    C --> D["Remove invalid flags"]
    D --> E["Startup test and verify active GC"]
    E --> F["Run benchmarks / integration tests"]
    F --> G{"Do SLO, memory, CPU, and startup pass?"}
    G -->|Yes| H["Canary and monitored rollout"]
    G -->|No| I["Analyze logs, heap, CPU, workload"]
    I --> C
    H --> J["Record evidence, guardrails, and rollback"]
~~~

### Step 1 — Capture a reproducible baseline

Before upgrading:

- JDK vendor, version, and build.
- OS/architecture and container image.
- Process startup command and effective GC flags.
- Actual selected collector.
- `-Xms`, `-Xmx`, and memory flags.
- CPU/memory limits and cgroup version.
- Application artifact hash.
- Workload, dataset, and traffic profile.
- GC logs, latency histograms, throughput, CPU, and RSS.
- Log parser/dashboard versions.

Not every project requires identical detail, yet without a baseline it is hard to answer "is the new GC better or worse?".

### Step 2 — Classify every GC flag

Group into:

1. **Collector selection**: `UseG1GC`, `UseParallelGC`, `UseConcMarkSweepGC`, etc.
2. **Heap sizing**: `Xms`, `Xmx`, `MaxRAMPercentage`.
3. **Collector-specific tuning**: CMS, G1, ZGC, or Shenandoah options.
4. **Logging/diagnostics**: `PrintGCDetails`, `-Xlog:gc...`.
5. **Ergonomics/resources**: processor counts, GC worker counts.
6. **Other**: safepoints, explicit-GC handling, native-memory diagnostics.

Flags valid on an old collector are not necessarily valid or beneficial on a new collector.

### Step 3 — Confirm target JDK support

Verify:

- Is the collector included in the build?
- Does the JVM accept the flags?
- Does the release require experimental unlock flags?
- Are there generational/mode-specific flags to note?
- Are there OS/CPU caveats?
- Do custom runtime images affect anything?
- Does vendor support impose restrictions?

Test startup early; never let unrecognized-option errors surface during production rollouts.

### Step 4 — Move from legacy config to a clean baseline

When switching from CMS to G1, replace CMS-specific configs with a **clean G1 baseline**. Example:

~~~bash
java \
  -XX:+UseG1GC \
  -Xms2g \
  -Xmx4g \
  -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

This is illustrative; adapt log file paths and heap sizes to your system. Run G1 with suitable defaults before adding custom tuning.

### Step 5 — Verify startup and active collector

Confirm:

- Zero warnings/errors about JVM options.
- GC logs identify the expected collector.
- Heap sizing matches expectations.
- Container limits are detected properly by the JVM.
- Metrics pipelines parse the new logs cleanly.
- No leftover legacy flags get injected elsewhere.

### Step 6 — Benchmark under representative load

Include:

- Warmup.
- Steady-state load.
- Peak traffic.
- Long-running soak tests.
- Batch jobs with distinct allocation profiles.
- Load while downstream dependencies slow down or fail.
- Restart and rolling-deploy behavior.
- Runs near memory limits.

Compare across identical metric tables and measurement windows; never compare two unrelated busy hours and call it an A/B GC test.

### Step 7 — Canaries and monitoring

Roll out to a small instance slice or staging environment, watching:

- GC pause p99/max.
- Request p99 and timeouts.
- CPU throttling.
- Memory/RSS and OOMKills.
- GC overhead.
- Thread counts and allocation pressure.
- Startup, readiness, and shutdown times.
- Business throughput and error rates.

If SLOs fail, keep a plan ready to switch to another supported collector on the target JDK, or roll back the entire runtime depending on scope.

## 15. Isolate three change variables for easier diagnosis

A migration can simultaneously alter:

1. **JDK version**.
2. **Collector**.
3. **Heap/resource configuration**.

Changing all three together obscures root causes.

Example experiment matrix:

| Experiment | JDK | GC | Heap/resources | Objective |
|---|---|---|---|---|
| A | Old JDK | Old collector | Baseline | Control baseline |
| B | New JDK | Closest still-supported GC | Same as baseline where valid | Isolate JDK impact |
| C | New JDK | Target collector | Same as B | Isolate GC impact |
| D | New JDK | Target collector | New heap/CPU tuning | Measure tuning impact |

Experiment B is not always feasible: for example, CMS was removed in JDK 14+, making CMS on a newer JDK impossible to run. Document experimental constraints explicitly and use available supported baselines.

### 15.1. Minor JVM updates can also matter

JVM updates can fix GC bugs or adjust heuristics, logging, and container detection. Major releases are not the only ones impacting performance.

For latency-sensitive systems, benchmark notable patch/update releases within the same JDK line before rolling out.

## 16. Walkthrough: migrating Java 8 with CMS to Java 17 with G1

Suppose a legacy order service launches with:

~~~bash
java \
  -XX:+UseConcMarkSweepGC \
  -XX:+UseCMSInitiatingOccupancyOnly \
  -XX:CMSInitiatingOccupancyFraction=65 \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -Xloggc:logs/gc-old.log \
  -Xms2g \
  -Xmx4g \
  -jar orders.jar
~~~

### 16.1. Identifying issues

- CMS is no longer available in HotSpot JDK 17.
- CMS-specific occupancy initiation flags no longer apply.
- Legacy GC logging options must be updated.
- Existing GC log parsers may only recognize CMS output.
- Current SLOs must be recorded before switching.
- Application, server, and frameworks must support Java 17 independently of GC.

### 16.2. Switching to a G1 baseline

~~~bash
java \
  -XX:+UseG1GC \
  -Xms2g \
  -Xmx4g \
  -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders.jar
~~~

Do not carry CMS occupancy flags over to G1. Avoid setting `G1HeapRegionSize` or explicit GC thread counts prematurely without data.

### 16.3. Running verification

- Startup on the exact target JDK runtime and container image.
- API smoke tests.
- Traffic benchmarks with representative request rates and payloads.
- Heap pressure tests.
- Long-running soak tests.
- GC log parser tests.
- Error, latency, CPU, and RSS comparisons.
- Canary and rollback drills.

### 16.4. Evaluation outcomes may vary

**Favorable case:** G1 eliminates long pauses, API p99 improves, and throughput drops negligibly.

**Needs tuning case:** G1 incurs frequent mixed pauses, elevated CPU overhead, or tight memory pressure; inspect live set, allocation rates, and heap sizing.

**Fails target case:** batch throughput drops past allowed thresholds; benchmark Parallel GC as a supported candidate and select accordingly.

Never blindly claim "G1 is faster than CMS" across all apps. Evaluate using explicit criteria and measurements.

## 17. Walkthrough: migrating Java 8 default Parallel to Java 21 default

Suppose a Java 8 batch job omits `UseParallelGC`, running in an environment where HotSpot selected Parallel GC automatically.

Moving to Java 21 with no GC flags can change HotSpot's default to G1 on qualifying setups.

The trigger here is not a removed flag, rather a **changed default selection**.

### 17.1. Verification procedure

1. Run the Java 8 baseline and record the active collector.
2. Run Java 21 without GC flags and record the active collector.
3. Keep datasets and CPU/memory limits comparable.
4. Compare batch duration, CPU, RSS, and total GC time.
5. If needed, benchmark Java 21 with `-XX:+UseParallelGC`.
6. Choose the collector based on goals and extended test runs.
7. Update documentation so operations knows whether GC is pinned or defaulted.

### 17.2. Do not measure GC time alone

A job with shorter pauses does not necessarily finish faster. Concurrent collectors use CPU alongside application threads. Total throughput benchmarks reflect real business completion time.

Conversely, a job finishing a few percent faster while saturating node CPU and starving neighboring services may be a poor operational choice.

## 18. Container scenario: upgrading JDK shifts heap and GC threads

A service runs under a 2 GiB container memory limit and 1 vCPU quota. The older JVM detected container boundaries differently from the newer release.

After upgrading:

- The JVM may observe a different memory limit.
- Default maximum heap size may shift.
- GC thread ergonomics change with active processor count.
- Default collector selection may shift.
- CPU throttling appears as concurrent GC work rises.
- RSS approaches OOMKill even while heap usage stays below `-Xmx`.

### 18.1. Diagnosis

Capture on both runtimes:

~~~bash
java -version
java -XX:+PrintCommandLineFlags -version
java -XX:+PrintFlagsFinal -version
~~~

Where supported by the JDK:

~~~bash
java -XshowSettings:system -version
~~~

Correlate cgroup/container metrics, GC logs, and process RSS. Never read memory limits from YAML alone assuming the JVM perceives the exact same value.

### 18.2. Remediation

- Set heap bounds leaving sufficient native headroom.
- Verify CPU quotas and requests.
- Choose a collector matching available resources.
- Reduce allocation rate or object retention if needed.
- Tune concurrency/worker threads based on measurements.
- Run load/soak tests under production-exact resource limits.

## 19. Measurement tools instead of guesswork

### 19.1. GC logs

Primary data source for pause analysis, heap occupancy, GC causes, and concurrent phases. Ensure log parsers match the target JDK and collector.

### 19.2. JDK Flight Recorder (JFR)

JFR records events covering:

- GC pauses and phases.
- Allocations.
- Object statistics depending on profile config.
- CPU and thread activity.
- Lock contention.
- JVM configuration.

Example on supporting HotSpot/JDK builds in authorized test environments:

~~~bash
jcmd <pid> JFR.start name=gc-migration settings=profile duration=5m filename=gc-migration.jfr
~~~

Verify syntax, permissions, and overhead for the target runtime. Never enable heavy profiling or collect sensitive data in production without approval.

### 19.3. Micrometer/JMX/OpenTelemetry metrics

Applications often export JVM GC metrics via JMX or monitoring libraries, yet metric names or collector series names differ across GCs and JDKs.

If an alert dashboard queries series names like "G1 Young Generation", switching collectors causes that series to vanish. Test instrumentation and dashboards after migrating.

### 19.4. OS/container metrics

Correlate GC metrics with:

- Process CPU and system CPU.
- Cgroup throttled time.
- Process RSS.
- Container memory working set.
- Major page faults where relevant.
- Disk I/O and network.
- Pod restarts / `OOMKilled`.
- Node pressure.

If p99 spikes due to CPU throttling or database latency, staring solely at GC logs can lead to counterproductive heap tuning.

## 20. Metrics for evaluating GC migration

An evaluation table could look like (all numbers illustrative only):

| Metric | Baseline | New JDK/GC | Criterion |
|---|---:|---:|---|
| Throughput (req/s) | 2,500 | 2,480 | Within approved reduction limit |
| Application p99 (ms) | 210 | 170 | Below SLO |
| GC pause p99 (ms) | 95 | 38 | Lower or within threshold |
| GC pause max (ms) | 620 | 180 | Within planned budget |
| Process CPU (%) | 55 | 61 | Causes no throttling |
| Process RSS (GiB) | 2.8 | 3.0 | Sufficient headroom remains |
| OOMKilled | 0 | 0 | None observed |
| Batch completion | 9m40s | 9m45s | Within acceptable bounds |

Never treat these sample figures as universal thresholds. SLOs and resource budgets come from your system's requirements.

### 20.1. Never use p50 to prove tail latency

A collector can leave median latency nearly flat while still introducing occasional severe pauses. For strict SLAs, watch p95/p99/max and timed-out requests.

### 20.2. Never assume high GC count is always bad

Many brief pauses can reflect healthy behavior for a collector. Evaluate **overall impact** on throughput, latency, and footprint rather than raw event count.

### 20.3. Compare distributions under matching workloads

During benchmarks, ensure:

- Comparable request rates or batch sizes.
- Comparable read/write ratios and payload sizes.
- Comparable cache warmup state.
- Stable database/network dependencies.
- Controlled replica counts and autoscaling.
- Adequate JVM warmup / JIT compilation time.
- No unrelated major business-logic changes mixed in.

## 21. Test suite recommended when changing GCs

### 21.1. Startup tests

Verify:

- JVM accepts all flags.
- Expected collector is active.
- Heap and resource settings are valid.
- GC logging writes properly.
- Zero warnings from legacy flags or wrong distributions.
- Servers, plugins, and Java agents initialize cleanly.

### 21.2. Functional tests

GC preserves Java heap semantics in principle, yet runtime or native integration bugs can emerge across JDK upgrades:

- API and batch business flows.
- Serialization and database integrations.
- JNI/JNA/native libraries if used.
- Java agents and bytecode instrumentation.
- Plugins and dynamic class loading.
- Reference processing, cleaners, and designed resource lifecycles.

Never rely on `System.gc()` as a mandatory mechanism to "free business resources". Explicit GC calls may be ignored or behave differently depending on flags and collectors.

### 21.3. Performance tests

- Steady-state throughput.
- Latency distribution.
- Peak load.
- Heap occupancy / live set.
- Allocation rate.
- GC pause histograms.
- CPU and RSS.
- Multi-hour soak tests per requirements.
- Behavior near memory limits and CPU throttling.
- Startup and warmup behavior.

### 21.4. Rollback tests

Verify whether you can:

- Switch back to another collector **on the same target JDK**.
- Revert to the previous JDK/runtime image.
- Revert server/framework configuration.
- Restore GC log parsers and dashboards.
- Preserve data compatibility if rolling back artifacts.

GC rollback is often a JVM flag change and restart, yet in practice may tie to container image, JDK, or heap adjustments; validate the full path.

## 22. GC configuration is versioned operational state

Maintain an operational profile for each service:

~~~yaml
service: orders-api
runtime:
  vendor: "Approved OpenJDK-based distribution"
  version: "Target JDK release and update"
deployment:
  type: "container"
  cpu_limit: "Recorded from deployment"
  memory_limit: "Recorded from deployment"
gc:
  selection: "G1"
  explicit_flag: "-XX:+UseG1GC"
  heap_initial: "2g"
  heap_max: "4g"
  logging: "-Xlog:gc*,safepoint:..."
  reason: "Approved after performance comparison"
validation:
  startup: "PASS"
  load_test: "PASS"
  soak_test: "PASS"
  canary: "PENDING"
ownership:
  team: "Platform"
  review_trigger: "Next JDK upgrade"
~~~

Values above are placeholders. Real configs must capture **exact versions and test evidence**, without secrets.

### 22.1. When should GC choices be re-evaluated?

- Major JDK upgrades.
- JDK updates altering GC or ergonomics.
- Switching JVM distributions.
- Changing container CPU/memory limits.
- Major workload or dataset shifts.
- Framework upgrades changing allocation profiles.
- Switching logging or monitoring agents.
- New latency SLOs.
- Warnings marking GC flags deprecated, obsolete, or removed.

## 23. CI and startup guardrails

### 23.1. Checking for legacy flags

A simple guardrail can scan for CMS flags:

~~~bash
rg -n --hidden -- \
  'UseConcMarkSweepGC|UseParNewGC|CMSInitiating|CMSClassUnloadingEnabled' \
  deploy scripts build.gradle pom.xml
~~~

If repositories contain docs mentioning CMS examples, narrow scan paths so valid README examples are not blocked.

An effective CI check compares against an approved allowlist and fails when removed JVM options appear inside **production startup configurations**.

### 23.2. Startup smoke test on the target JDK

Rather than parsing config files alone, launch the actual target JVM/runtime with real flags in an appropriate CI step to catch unrecognized options.

For application servers, exercise startup scripts and container images; never test `java -version` alone since servers inject flags from external scripts.

### 23.3. Never use an "ignore unknown options" flag to pass CI

That masks compatibility bugs and strips value from startup smoke tests. Fix the flag set and verify the active collector instead.

## 24. Common mistakes

### 24.1. "Upgrading Java automatically improves GC"

Not guaranteed. Newer JDKs bring real improvements, yet outcomes depend on workloads and resources. Throughput can dip or footprint can rise in certain cases.

### 24.2. "Java 17/21 guarantees G1 in all situations"

Not unconditionally. JVM vendors, flags, container limits, and ergonomics affect selection. Confirm from runtime logs.

### 24.3. "CMS deprecated means it stays usable forever"

False. CMS was removed from HotSpot in JDK 14. Remove related flags when moving to that release or later.

### 24.4. "Parallel GC was removed when G1 became default"

False. **Changing the default** differs from **removing an implementation**. Do not conflate the two.

### 24.5. "Switch CMS to G1 and keep all CMS flags"

False. Collector-specific tuning does not carry over cleanly across collectors and can break startup.

### 24.6. "`-XX:MaxGCPauseMillis` is a hard maximum pause limit"

False. It is a tuning goal, not an SLA hard bound.

### 24.7. "ZGC has zero stop-the-world pauses"

Overstated. ZGC designs pauses to be extremely short, yet systems still involve safepoint and stop-the-world phases within technical bounds. Never claim pause times are zero.

### 24.8. "Low-pause collectors always consume less CPU"

Not necessarily. Concurrent GC needs CPU headroom and carries distinct throughput/memory trade-offs.

### 24.9. "Setting Xmx equal to container memory limit is safe"

No. Processes still require native memory, thread stacks, code cache, GC structures, and more.

### 24.10. "New parsers automatically understand legacy GC logs"

Do not assume that. Unified Logging tags, levels, and event layouts differ across GCs and JDKs.

### 24.11. "The new JDK failed because of a bug in Java code"

Startup can fail **before `main()` ever runs** due to unsupported JVM flags. Read launcher errors first.

### 24.12. "Switching collectors fixes memory leaks"

No. While applications keep live references, no collector can reclaim those objects.

### 24.13. "One benchmark run is enough"

Insufficient. JVM/JIT warmup, load jitter, and noise skew single runs. Repeat runs and check distributions.

### 24.14. "MXBean names are a portable API for detecting GC"

No. Collector MXBean names are implementation-specific and should not be hard-coded into application logic.

### 24.15. "Same major JDK guarantees identical GC behavior"

Uncertain, especially across HotSpot vs. OpenJ9, custom builds, differing OS/CPUs, and GC feature updates.

## 25. GC migration checklist

### Before upgrading

- [ ] Recorded JVM vendor, version, update level, and platform.
- [ ] Verified the currently active collector in runtime logs.
- [ ] Captured all GC-related startup flags.
- [ ] Audited flags across Docker, Kubernetes, servers, CI, and tests.
- [ ] Recorded heap sizing, CPU/memory limits, and cgroup setup.
- [ ] Captured GC logs plus application p99 and throughput baselines.
- [ ] Defined SLOs and rollback criteria.

### Target JDK compatibility

- [ ] Confirmed the target collector is supported by the target runtime.
- [ ] Removed discontinued CMS and legacy flags.
- [ ] Distinguished deprecated flags from removed flags.
- [ ] Checked new and legacy GC logging options.
- [ ] Confirmed GC log parsers and monitoring tools handle the new format.
- [ ] Passed startup smoke tests with the exact JVM flags.
- [ ] Checked heap and GC thread ergonomics under container limits.

### Performance and functionality

- [ ] Ran functional regression tests.
- [ ] Measured throughput and p95/p99/max latency.
- [ ] Analyzed STW pauses and concurrent GC overhead.
- [ ] Monitored RSS/native memory and CPU throttling.
- [ ] Tested workloads with representative allocation pressure.
- [ ] Ran soak tests and peak-load tests where required.
- [ ] Tested agents, native integrations, and plugins if present.
- [ ] Executed canary rollouts before wide deployment.

### Completion

- [ ] Updated JVM flags across all target environments.
- [ ] Verified actual running collectors post-deployment.
- [ ] Updated startup scripts and Helm/Docker/service configs.
- [ ] Archived benchmark evidence tied to artifact, JDK, and GC.
- [ ] Added guardrails preventing CMS flags from creeping back in.
- [ ] Updated observability and rollback runbooks.
- [ ] Assigned owners and scheduled reviews for the next JDK upgrade.

## Conclusion

**Default collector** and **supported collectors** are two separate questions. G1 became HotSpot's common default in JDK 9 via JEP 248; that did not make Parallel GC vanish. Conversely, CMS was deprecated in JDK 9 and removed in JDK 14, meaning legacy startup flags can prevent applications from booting on newer JDKs.

A dependable Java transition workflow must: **record the actual GC and all flags → remove unsupported options → pick a collector suited to the workload → update GC logging → validate performance, heap sizing, and container limits → roll out with monitoring and rollback readiness**. JVM compatibility is measured not just by whether bytecode executes, but by whether the application sustains the throughput, latency, memory headroom, and stability demanded in operations.
