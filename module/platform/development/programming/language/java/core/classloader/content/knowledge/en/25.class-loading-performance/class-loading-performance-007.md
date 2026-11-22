# Measuring Class Loading Performance with the Same JDK, Classpath, and Used Class Set

## 1. Goals and Principles of a Fair Comparison

When diagnosing a slow class loader, long startup time, slow plugin loading, or an application taking too long before its first request, it is tempting to measure twice and conclude that "configuration A is faster than B." However, timing measurements are only meaningful if **both runs perform the same kind of work in the same environment**, specifically:

1. **Same JDK/JVM**: vendor, version, build, architecture, JIT mode, garbage collector, and relevant JVM flags.
2. **Same classpath/module path**: artifact contents, dependency versions, entry ordering, module resolution, and parent delegation mechanism.
3. **Same set of classes actually requested for use**: same binary names, same defining loader by design, same number of loader creations/class definitions, same initialization requirements, and same application execution path.
4. **Same measurement conditions**: fresh JVM process or warmed-up JVM, CPU/RAM, page cache state, concurrent loads, GC, logging, input data, and iteration count.
5. **Change only one variable under evaluation** between A and B, and cross-check both **timing** and **actual class loading evidence**.

You must define exactly **what you are measuring** before choosing a tool:

| Measurement | Start → End | May Include | What Must Not Be Inferred |
|---|---|---|---|
| **Process startup** | Before process creation → application ready signal | JVM startup, bootstrap, CDS, framework, class loading, I/O | Do not infer how long the class loader alone took |
| **First-use latency** | Before first feature invocation → after first result returned | Loading, verification/linking, initialization, JIT, caching, I/O, business logic | Do not treat the entire duration as "class load time" |
| **Per-class resolution/initialization operation** | Before → after `Class.forName(...)` | Loader lookup, possibly loading/linking/initialization, or only finding an already-loaded class | Not equivalent to pure JVM class loading cost |
| **Steady-state latency/throughput** | After warm-up, across measurement windows | Already-loaded code, JIT, GC, thread scheduling, application logic | Do not use to claim fast cold-start performance |
| **Class count/metaspace** | Snapshot before → after | Number of classes recorded by the JVM, metadata memory | Does not measure latency; counter changes cannot be attributed to target classes |

**The most important control condition in this guide:** using the same JDK with different dependency JARs, or the same JARs when run A triggers more classes than run B, means the results no longer measure the same workload. You must prove that **the set of used classes is equivalent**, rather than merely noting that "the classpath looks similar."

## 2. Real-World Class Loading Has Multiple Cost Layers

Measuring `Class.forName` or `loader.loadClass` **does not automatically separate** JAR reading, verification, linking, initialization, and application I/O. The JVM may defer symbolic resolution; `Class.forName(name, true, loader)` actively requests initialization, whereas `false` does not. An already-loaded class is typically returned from the same loader without defining the class again.

To ensure A and B are truly equivalent, audit these separately:

- **Class identity:** binary name together with the intended defining loader, not just the class name string.
- **Search path:** JAR ordering, checksums, and parent delegation; a parent may pick a different version before the child.
- **Work unit:** number of class definitions, initialization calls, resource/provider/bean setup, and business results.
- **JVM state:** fresh process vs. warm class/JIT/CDS state, OS page cache, and number of concurrent loaders.

If A creates one loader per request while B reuses a single loader, that change in **the number of class definitions** is itself a variable that must be reported—you cannot claim the two workloads load the same number of classes. Conversely, if you are only testing classpath lookup speed, do not let one variant accidentally load additional framework classes.

`ClassLoadingMXBean` provides JVM-wide counters; combine it with event logs and dedicated defining-loader diagnostics to verify which target classes were actually processed.

## 3. Experiment Design: Hypothesis, Variables, and Validity Criteria

Before running, establish a control profile:

| Component | Keep Fixed or Record Explicitly |
|---|---|
| JVM | `java -version`, `java -XshowSettings:properties -version`, `java -XX:+PrintFlagsFinal -version` when needed; vendor/build/architecture |
| Application | Commit/build ID; bytes of all `.class`/JAR files that may be loaded |
| Classpath/module path | Entry list **in exact order**, artifact versions and checksums, `--module-path`/`--add-reads`/`--add-opens` if used |
| Loader topology | Bootstrap/platform/app loader; parent-child delegation; number of new loaders per run |
| Target class set | Binary name + loader/source and load/init events; do not compare by name alone when multiple loaders exist |
| Workload | Same request/entry point/feature flags/input; same required operations and same correct output |
| Runtime state | Cold JVM or warmed JVM, warm-up iterations, JIT, CDS, GC, memory flags |
| Host | CPU, RAM, system load, governor/container limits, file cache, and I/O |
| Observation | Metric, unit, timer boundaries, run count, distribution metrics, and error-exclusion rules |

Example of a valid hypothesis: "With the same set of JARs and the same 60 plugin classes to initialize, changing one resource lookup policy under **the same loader lifecycle model** reduces the median latency of plugin loading." During verification, if logs show A loads 60 classes while B loads 90 classes, you must investigate the discrepancy before attributing the timing difference solely to the resource lookup policy.

Examples of **invalid** comparisons:

- A runs on JDK 17, B runs on JDK 21, while also differing in CDS and dependency trees.
- A measures the first call in a JVM, while B measures a repeated `Class.forName` call in the **same** JVM after the class is already loaded and initialized.
- A enables `-Xlog:class+load=trace` writing to a file, while B disables logging.
- A has 3 JARs on the classpath, while B has 4 JARs or a different order.
- A executes a request that triggers 10 lazy-loaded classes, while B executes a request exercising fewer features.
- A reports a speedup based on **a single run** while CPU load is unstable.

A conditional comparison can intentionally vary one factor; in that case, record it as the **independent variable** (for example, JDK 17 vs. 21) and hold all other factors constant. In this guide, the goal is to **keep the JDK, classpath, and used class set identical**.

## 4. Java 17+ Example: Measuring Loading and Initialization of a Fixed Class Set

The following example runs from a single Java source file, defining three nested classes with fixed names. The goal is a small, repeatable workload with verifiable output. It is **not a general-purpose microbenchmark** for every class loader implementation.

Create the file **`BenchClassLoad.java`**:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public final class BenchClassLoad {
    private static final String[] TARGETS = {
        "BenchClassLoad$Alpha",
        "BenchClassLoad$Beta",
        "BenchClassLoad$Gamma"
    };

    private static final class Alpha {
        static int marker = 11;
    }

    private static final class Beta {
        static int marker = 22;
    }

    private static final class Gamma {
        static int marker = 33;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 0) {
            throw new IllegalArgumentException("Run without arguments");
        }

        // Get the bean before starting the timer to reduce setup noise.
        ClassLoadingMXBean mx =
                ManagementFactory.getClassLoadingMXBean();
        ClassLoader loader =
                BenchClassLoad.class.getClassLoader();

        long beforeCount = mx.getTotalLoadedClassCount();
        long startNs = System.nanoTime();

        long signature = 17L;
        for (String name : TARGETS) {
            // true: request first-time class initialization when appropriate.
            Class<?> type = Class.forName(name, true, loader);
            signature = signature * 31 + type.getName().length();
        }

        long elapsedNs = System.nanoTime() - startNs;
        long loadedDelta =
                mx.getTotalLoadedClassCount() - beforeCount;

        System.out.println("targets=" + TARGETS.length);
        System.out.println("signature=" + signature);
        System.out.println("duration_ns=" + elapsedNs);
        System.out.println("jvm_loaded_delta=" + loadedDelta);
    }
}
```

Compile once on JDK 17+:

```bash
javac BenchClassLoad.java
```

Run multiple **independent JVM processes**, always from the same directory and with the same classpath:

```bash
java -cp . BenchClassLoad
java -cp . BenchClassLoad
java -cp . BenchClassLoad
```

In every process, these two lines have the exact same values:

```text
targets=3
signature=526276
```

The other two lines are **dynamic measurements**. Example display format:

```text
duration_ns=<measured nanosecond value>
jvm_loaded_delta=<number of additional classes loaded by the JVM during the measurement window>
```

The angle-bracketed text above represents **output field descriptions**, not literal strings printed by Java; at runtime, they are actual integers and may vary across runs. The program measures **the execution time of three `Class.forName(..., true, loader)` calls**, including lookup and loading/verification/linking/initialization if not yet performed, rather than **isolating** I/O or VM define-class time. The `jvm_loaded_delta` count is **JVM-wide** and may include supporting JDK classes loaded during that window; it will not necessarily equal 3.

Computing `signature` confirms that the loop processed all three named classes: with name lengths `BenchClassLoad$Alpha` = 20, `...$Beta` = 19, and `...$Gamma` = 20, starting from 17 produces 526276. However, this signature is only a **code-level sanity check**; it does not prove the byte source or loader identity of classes in a complex application. For a real class set, inspect separate class loading logs.

### Why Should Each Run Be a Fresh JVM Process?

The same loader does not "load for the first time" a class it has already defined. If you place two measurement loops back-to-back in the same `main`, the second loop will usually measure **fetching already-loaded/initialized classes** rather than repeating the first loop's work. To measure JVM-lifecycle cold first-use/class loading, spawn fresh processes with identical configuration. Do not use `System.gc()` as a way to "reset" all loaded classes; GC does not force the JVM to unload classes still referenced by live loaders.

In this example, a fresh JVM guarantees that the application namespace is recreated. However, the **OS disk page cache** may already be warm after the first run, and JVM startup state still varies slightly between processes. Calling this *fresh JVM* or *first-use per process* is therefore more accurate than calling it a *true cold hardware/disk start*.

### Collecting Multiple Runs

Bash/macOS/Linux, from the directory containing the `.class` files:

```bash
for i in $(seq 1 20); do
  java -cp . BenchClassLoad
done
```

If you only need to save the timing values:

```bash
for i in $(seq 1 20); do
  java -cp . BenchClassLoad
done | awk -F= '/^duration_ns=/{print $2}' > timings-ns.txt
```

PowerShell (Windows), where each iteration also spawns a new JVM:

```powershell
1..20 | ForEach-Object {
    java -cp . BenchClassLoad
}
```

This is a **raw collection** example without A/B comparison or statistical significance testing. For an A/B experiment, run both conditions with the same number of processes, and randomize or alternate the order (`A/B/B/A`) to reduce bias from machine warm-up and time-dependent effects.

## 5. Verifying the Same Classpath, JDK, and Class Set

### A. Pinning the Actual JVM Used

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

Save the verbatim output and record `java.home`, `java.version`, `java.vendor`, `os.arch`, and JVM flags. Ensure `java` and `javac` do not point to two different JDKs due to `PATH`/`JAVA_HOME`, a CI image, or an IDE launcher. Having a build JDK different from the runtime JDK can cause incompatibility or behavioral differences.

If you are specifically studying default startup behavior, keep the same **CDS mode** and `-Xshare`/archive flags. Toggling CDS between two conditions alters class metadata work and introduces **a different experimental variable**. `-XX` flags are implementation-specific, so verify them on the exact JVM being run.

### B. Proving the Classpath Is Unchanged

For the demo, `-cp .` with the same four files (`BenchClassLoad.class`, `BenchClassLoad$Alpha.class`, `BenchClassLoad$Beta.class`, `BenchClassLoad$Gamma.class`) is the minimal input configuration. When using real JARs:

- Record the **path and order** of every classpath entry; order matters when multiple JARs contain the same binary class name.
- Record versions and SHA-256 checksums of JARs/class bytes. Matching filenames or manifest version numbers alone do not guarantee identical contents.
- If using Gradle/Maven, distinguish between `compileClasspath`, `runtimeClasspath`, test classpaths, plugin runtimes, and launcher-generated classpaths.
- If using `--module-path`, control the module graph, module descriptors, resolution, and `--add-reads`/`--add-opens` options.
- For Spring Boot executable JARs, inspect `BOOT-INF/lib` and `BOOT-INF/classes`; custom launchers may not represent the classpath the same way `java -cp ...` does.
- In plugin systems, the same JAR under **different parent delegation** may load bytes from a parent loader instead of the plugin's copy. Record the loader topology as well.

Example commands to verify checksums outside Java code:

```bash
sha256sum path/to/dependency.jar
```

On Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 path/to/dependency.jar
```

The `path/to/dependency.jar` argument is just a placeholder—replace it with the actual JAR. Do not reorder the classpath or clear caches mid-collection unless that is an intentional experimental variable.

### C. Verifying the Used Class Set with Separate Logging

On HotSpot JDK 17+, a **separate audit run** can use:

```bash
java -Xlog:class+load=info:file=class-load-%p.log:uptime,level,tags -cp . BenchClassLoad
```

In the log, look for the three names:

```text
BenchClassLoad$Alpha
BenchClassLoad$Beta
BenchClassLoad$Gamma
```

They will appear alongside many other Java classes. Check the **load source**, matching line counts, timestamps, and loader identity (if provided by the runtime log or diagnostic command). Simply matching three names is insufficient if one condition loads 200 extra framework classes or defines a class multiple times across different loaders.

If you are also investigating initialization:

```bash
java -Xlog:class+load=info,class+init=info:file=class-events-%p.log:uptime,level,tags -cp . BenchClassLoad
```

`class+load` and `class+init` reflect two distinct phases. Use the same event type when counting—do not compare total loaded classes in condition A against initialized classes in B.

**Do not use verbose logging runs as your primary performance benchmark:** logging every class increases CPU/I/O and can heavily skew timing. Run the audit separately to prove the workload/class set; then measure timing with **identical, minimal logging** on both branches (typically disabling info/debug class logs). If enabling JFR or a profiler, keep **the same instrumentation configuration** across directly compared runs.

### D. Distinguishing the Target Set from JVM-Wide Statistics

In the example, `TARGETS` is the **intended target class set**. `ClassLoadingMXBean.getTotalLoadedClassCount()` reports the **total classes loaded since JVM startup**; the delta inside the timer can grow due to auxiliary classes. `getLoadedClassCount()` is the currently loaded class count, and `getUnloadedClassCount()` is the total unloaded count. These values **do not identify which class, which JAR, or which loader**.

Therefore, store two kinds of evidence:

1. **Target list:** binary names/class identities required by the operation, expected load/initialization counts, and checksum/functional outputs.
2. **Process data:** JVM total counters, load/unload event logs, CPU/GC stats, and memory footprint under measurement conditions.

If two processes show different loaded deltas, do not rush to "normalize time by dividing by loaded count," because classes have vastly different costs, many classes load before the timer starts, and loaders may cache results. Investigate the differing classes first.

## 6. Choosing Tools Based on the Measurement Question

| Tool | When to Use | Limitations |
|---|---|---|
| `System.nanoTime()` | Measuring short elapsed intervals with clear boundaries | Timer overhead/JIT/scheduling; a single sample is too noisy |
| Java Flight Recorder (JFR) | Observing startup, class loading, CPU, allocation, GC, and enabled events | Event overhead depends on configuration; not all class events are enabled by default |
| `-Xlog:class+load`/`class+init` | Auditing which classes actually load/initialize and their sources | Logging adds overhead; huge output on large applications |
| `ClassLoadingMXBean` | JVM-wide loaded/current/unloaded counters | Does not identify specific classes; does not measure latency |
| `jcmd <pid> VM.classloader_stats` | Runtime snapshot of loader/class counts | Snapshot only; attaching/diagnostics can add overhead |
| `jcmd <pid> VM.metaspace` | Analyzing metadata memory in HotSpot | Footprint does not equate to load time |
| JMH | Benchmarking **steady-state micro-operations** with configured warm-up/forks/measurement | For one-time JVM first-load goals, repeated JMH method invocations usually measure **already-loaded** classes |
| OS profiler / CPU profiler | Finding I/O, CPU, and hot methods during loading/initialization | Profiling adds observation overhead; does not replace controlled A/B runs |

Run `java -Xlog:help` to see available tags on your JVM. The `jcmd` commands below are snapshot examples; replace `<pid>` with the actual JVM PID and ensure attach permissions are available:

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace
```

When measuring **wall-clock process startup** from outside the JVM, use an external launcher/script that measures from process creation to a consistent "ready" milestone; `System.nanoTime()` inside `main` **does not include** JVM bootstrap that occurs before `main`.

## 7. Warm-Up, JIT, CDS, GC, and OS Page Cache

**Warm-up/JIT:** If the measurement repeatedly calls a class lookup or API after classes are loaded, run an adequate warm-up and measure steady-state. Use JMH with appropriate forks to reduce noise and prevent JIT dead-code elimination. However, if the goal is **first-time class loading**, each process has only one cold first-use per loader; "warming up" by invoking the target classes beforehand destroys the very phenomenon you want to measure. Keep these two benchmark types strictly separate.

**CDS:** Class Data Sharing can reduce part of the loading work for eligible classes. Keep archive state/`-Xshare` and the runtime image identical; you cannot attribute startup gains to a custom class loader if CDS settings changed at the same time.

**Garbage collection:** Some runs experience GC near or inside the timer window. Correlate GC timestamps with outliers in the distribution; do not simply discard slow runs because they are slow. Heap sizing, collector choice, and allocation patterns must match.

**OS cache and I/O:** When the classpath resides on disk, the filesystem cache can make subsequent JAR reads much faster. To model production startup, define the corresponding cold/warm cache state and reproduce it fairly. Do not measure run A right after a reboot and run B after repeated JAR reads and call that an A/B JVM comparison.

**CPU scheduling/thermal:** CPU governors, turbo boost, thermal throttling, container quotas, background services, and host load all introduce noise. On shared CI runners, variance can be high; run multiple iterations, record host metadata, and report distributions instead of a single number.

**Class initialization side effects:** `<clinit>` may perform I/O, read configuration, initialize logging, or register drivers. If profiling shows time spent in static initializers, optimizing class loader search will not eliminate most of the latency. Place timers and analysis so you know which phase dominates the cost.

## 8. From Raw Measurements to Conclusions

Suppose experiment A and B differ only in one class resource lookup policy; **the numbers below are purely illustrative, not measurements from a real application**:

| Condition | JDK / Classpath / Target Set | Median First-Use Latency | P95 |
|---|---|---:|---:|
| A | Same JDK 17 / same JAR hashes / 60 target classes | 48 ms | 64 ms |
| B | Same JDK 17 / same JAR hashes / 60 target classes | 41 ms | 58 ms |

In this example, the median difference is `48 - 41 = 7 ms`, or `7 / 48 ≈ 14.6%`. Still, before concluding that "B improves performance," you must verify run counts, distributions, system noise, JIT, I/O, logging, absence of unexpected class sets, and functional equivalence.

A good report does not just state a percentage. It specifies:

- **Workload:** measured operation, class names and defining-loader semantics, loader/class counts, and functional output.
- **Setup:** JVM version/vendor, flags, dependency hashes/classpath ordering, module path, machine specs, and cache state.
- **Method:** timer start/end boundaries, warm-up vs. fresh process, fork/run counts, A/B ordering, and failed runs.
- **Results:** median, P95, spread (min/max or IQR), units, and raw data/log paths for reproducibility.
- **Supporting evidence:** class loading/initialization audit, GC/counters, and where a profiler shows most time is spent.
- **Limitations:** remaining JIT/cache effects and how representative the synthetic benchmark is of production workloads.

Prefer **median** and percentiles for skewed/noisy data, along with per-run distribution plots if needed. Small sample sizes or heavily overlapping distributions may not be enough to prove a real change. For measurements with instrumentation overhead, compare A and B using **the exact same toolset and settings**.

## 9. Common Measurement Mistakes and Fixes

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| Different JDK, vendor, or JVM flags | Compilation, GC, CDS, and runtime behavior differ | Pin the runtime image and save `java -version`/flags |
| Same dependency name but different JAR | Loaded bytes may not be identical | Compare SHA-256 hashes and runtime class sources |
| Changing classpath order | A class with the same name may be resolved from a different entry | Keep the exact ordered classpath |
| Ignoring parent/child loader topology | Same class name does not guarantee the same runtime class | Record defining loader, delegation, and loader count |
| A loads 50 classes, B loads 80 classes | Different workloads mean latencies are not comparable | Audit class sets, functionality, and execution order |
| First loop and second loop in the same process | Classes in the second loop are already loaded/initialized | Use fresh JVMs for first-use; separate warm-up for steady-state |
| Treating `main` duration as JVM startup | Bootstrap already occurred before `main` | Measure from an external launcher to the ready signal |
| Enabling class trace only on A | Logging alters CPU and I/O | Audit separately; use identical logging across timed runs |
| Reading `getTotalLoadedClassCount()` as plugin class count | The counter is JVM-wide | Filter events by class/loader or use scoped instrumentation |
| Using `System.gc()` to "reset" classes | GC does not unload classes retained by live loaders | Design appropriate loader/process lifecycles |
| Running once and taking the fastest number | Noise and cache bias | Repeat multiple times; report median, P95, and raw data |
| Reporting only "B is 25% faster" | Omits task, runtime, and changed variable | Document protocol, workload, and checksums |
| Optimizing based on arbitrary class count reduction | Fewer classes do not automatically mean lower latency or equivalent behavior | Verify targets and measure latency/CPU directly |

## 10. Reproducibility Checklist

Before accepting an A/B comparison:

- [ ] Defined whether measuring **process startup**, **first-use**, or **steady state**, with clear timer boundaries.
- [ ] JDK/JVM vendor, version, build, flags, collector, CDS, and architecture are **identical**.
- [ ] Classpath/module path have **identical entries, ordering, and artifact checksums**; class loader topology is recorded.
- [ ] The same target class set is invoked, loaded, and initialized; verified by a separate audit log.
- [ ] Same number of loader/class-definition operations, feature flags, and input data.
- [ ] Logging/profiler/JFR are configured identically across runs and do not distort the comparison.
- [ ] JVM state (fresh/warmed), JIT, page cache, GC, and CPU/RAM load follow controlled rules.
- [ ] Multiple independent runs executed, with raw data, median/P95, and units saved.
- [ ] Measurements can be reproduced by others using the exact commands and artifacts.
- [ ] Conclusions clearly state what **was measured**, what **could not be isolated**, and the scope of applicability.

## 11. Self-Check Questions

**1.** Why is calling `Class.forName("X", true, loader)` twice in a row in the same JVM not equivalent to two cold-loading measurements?  
**Answer:** The second call may simply look up a class that is already defined and initialized. Measuring cold first-use for the same defining loader requires a new loader lifecycle or a fresh JVM, while keeping the workload equivalent.

**2.** Can you conclude A is faster than B if B accidentally loads 100 extra framework classes?  
**Answer:** No, you cannot attribute the difference solely to the intended change; first investigate why the actual used class sets differ.

**3.** Why is keeping the same JAR filenames insufficient to guarantee the same classpath?  
**Answer:** JAR contents, entry ordering, paths, and loader delegation can differ; you must check artifact hashes and runtime sources.

**4.** What is the risk of using `-Xlog:class+load` during timing benchmarks?  
**Answer:** Logging increases CPU and I/O, skewing timing results; audit separately and measure with the same minimal logging configuration across conditions.

**5.** If `jvm_loaded_delta` in the sample program is 8 instead of 3, does that mean the code loaded classes other than the three targets?  
**Answer:** The loop still targets only the three specified names; the JVM-wide counter can include other Java/runtime classes loaded during that window. Inspect the class load log to identify them.

## References

- [Java SE 17 — `Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): distinguishes initialization requests when loading a class.
- [Java SE 17 — `ClassLoadingMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): JVM-wide loaded/unloaded class counters.
- [JDK 17 `java` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog`, class load/initialization/unloading tags, classpath configuration, and `-Xshare`.
- [Java Language Specification 17, Chapter 12](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization, and unloading.
- [Java Microbenchmark Harness (OpenJDK JMH)](https://github.com/openjdk/jmh): tool for microbenchmarks with warm-up, measurement, and forks; choose appropriately between steady-state and cold first-use questions.