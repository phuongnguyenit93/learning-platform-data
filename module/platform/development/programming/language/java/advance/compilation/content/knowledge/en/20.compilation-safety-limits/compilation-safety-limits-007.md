# Evaluating Compiler Startup Overhead and Bounded Resource Reuse

## 1. Problem and objectives

One run of `javac` does not consist solely of parsing source code and emitting `.class` files. The tool may have to start a process/JVM, load the compiler, process options, access the classpath/module path, read JARs, resolve types, run annotation processors, and write outputs. For a large compilation, work on the source code may dominate execution time; for hundreds of small compilations, **repeated startup overhead** can be substantial.

Consequently, multi-compilation systems such as code grading platforms, IDE tools, on-demand compilation services, or multi-module pipelines frequently ask: should we batch sources, invoke the compiler inside an existing JVM, or reuse resources to reduce overhead?

However, keeping resources alive too long can increase memory, file handles, stale caches, contention across tasks, and risks from compiler plugins/annotation processors. The real problem is **measuring costs and defining a bounded reuse lifecycle**, rather than assuming “longer-lived means faster”.

After this lesson, you will be able to:

- Separate process startup costs, compiler setup, dependency scanning, and actual compilation work.
- Use `javax.tools.JavaCompiler` and `StandardJavaFileManager` with the proper lifecycle to run **sequential** tasks.
- Measure latency, throughput, and memory across cold, warm, in-process, and external compiler scenarios.
- Design bounded worker pools, queues, timeouts, invalidation, and finite resource budgets.
- Recognize when reuse brings no benefit or causes stale compilation outputs.

## 2. Cost components to measure

An approximate model can be used:

```text
T_total ≈ T_spawn_JVM
        + T_compiler_setup
        + T_discover_dependencies
        + T_parse_and_type_check
        + T_annotation_processing
        + T_generate_class_files
        + T_file_IO
```

This is an analytical model, not a JDK measurement contract: stages can overlap and are affected by GC, JIT, OS page cache, disk, and system load.

| Component | Manifestation | How to Evaluate |
| --- | --- | --- |
| Process/JVM startup | Each normal external `javac` command spawns a new JVM | Compare external process vs. in-process compilation |
| Compiler/task initialization | Building internal structures, parsing options, establishing context | Measure setup separately from `CompilationTask.call()` |
| Reading sources and dependencies | Scanning directories, reading metadata/class files from JARs | Separate small/large dependency sets; measure I/O and cache |
| Annotation processing | Processors scanning Java structures or generating code | Compare with processor enabled vs. disabled in diagnostic measurements |
| Type checking/code generation | Resolving names, types, generics, writing bytecode | Vary source count/complexity to identify bottlenecks |
| JVM resources | GC, heap, metaspace, file handles, CPU | Record RSS, GC, CPU, and resource errors during benchmarks |

Do not label all `javac` duration as “startup”. A project with heavy annotation processors or complex generics/dependencies can spend its time in type analysis or I/O even after the JVM has already started.

## 3. Four ways to run multiple compilations

### 3.1. A fresh `javac` process per pass

Example from a directory with two Java files:

```powershell
javac --release 17 -d out src/Alpha.java
javac --release 17 -d out src/Beta.java
```

This model is simple, easy to isolate, and easy to enforce deadlines at process boundaries, yet repeats startup costs. If both sources share compatible configurations, they can be batched:

```powershell
javac --release 17 -d out src/Alpha.java src/Beta.java
```

Do not batch sources mechanically if source sets use different Java releases, module paths, dependencies, annotation processors, or access boundaries. Improper batching can alter semantics and mask dependency errors.

### 3.2. JavaCompiler API inside an existing JVM

`ToolProvider.getSystemJavaCompiler()` returns a compiler when the current runtime contains the corresponding tool. An application can create multiple `CompilationTask` instances without spawning an external `javac` process per task.

The potential benefit is avoiding repeated process/JVM startup. However, a new `CompilationTask` must still parse inputs and emit outputs. It does not automatically become an incremental compiler or build cache.

### 3.3. Reusing `StandardJavaFileManager`

Official JDK 21 `JavaCompiler` documentation recommends the pattern of using the same standard file manager across **multiple sequential compilations**. This *can* reduce filesystem scanning and JAR reading costs; the documentation does not promise every workload will be faster.

Distinguish:
- **Creating a new task:** mandatory per compilation, because `CompilationTask.call()` may be called only once.
- **Reusing the file manager:** potentially helpful across sequential passes with stable classpaths/resource sets.
- **Closing the file manager:** needs an explicit end point to release resources; use `try-with-resources`.

### 3.4. Long-lived worker or daemon

A compiler worker process can serve multiple requests to reduce startup; however, you must manage worker counts, heap/RSS, JAR handles, queue limits, timeouts, and lifecycles. Gradle's daemon or build tools have their own policies; do not assume the `JavaCompiler` API creates a daemon itself or guarantees thread safety for all resources.

## 4. Java 17+ example: compiling twice and reusing the file manager

The **`CompileTwice.java`** file below creates two test source files, compiles them sequentially using **two separate tasks** sharing one `StandardJavaFileManager`, then closes the manager. The example illustrates API behavior, **not a benchmark measurement**.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileTwice {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        Path src = Files.createDirectories(Path.of("sample-src"));
        Path out = Files.createDirectories(Path.of("sample-out"));

        Files.writeString(
            src.resolve("Alpha.java"),
            "public class Alpha { public static int n() { return 1; } }\n",
            StandardCharsets.UTF_8
        );
        Files.writeString(
            src.resolve("Beta.java"),
            "public class Beta { public static int n() { return 2; } }\n",
            StandardCharsets.UTF_8
        );

        List<String> options = List.of(
            "--release", "17", "-proc:none", "-d", out.toString()
        );

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                    null, Locale.ROOT, StandardCharsets.UTF_8)) {
            for (String name : List.of("Alpha.java", "Beta.java")) {
                Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(
                        List.of(src.resolve(name))
                    );

                JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, null, options, null, units
                );

                boolean ok = Boolean.TRUE.equals(task.call());
                System.out.println(name + "=" + ok);
                if (!ok) {
                    throw new IllegalStateException("Compile failed: " + name);
                }
            }
        }

        System.out.println("Alpha.class=" +
            Files.exists(out.resolve("Alpha.class")));
        System.out.println("Beta.class=" +
            Files.exists(out.resolve("Beta.class")));
    }
}
```

In a separate test directory, with JDK 17 or higher:

```powershell
javac --release 17 CompileTwice.java
java CompileTwice
```

When the directory is writable and the compiler operates normally, expected stdout:

```text
Alpha.java=true
Beta.java=true
Alpha.class=true
Beta.class=true
```

Analysis of key points:

1. `getSystemJavaCompiler()` can return `null` in a runtime image lacking the compiler, even if `java` can still run many applications. Run the experiment with an appropriate full JDK.
2. Two sources are created in `sample-src`; outputs go to `sample-out`, relative to the working directory. Run only in a test directory because `Files.writeString` overwrites the contents of identically named files if they already exist.
3. `getStandardFileManager` runs once and is used for two **sequential** tasks. `getTask` creates a new task each iteration; `call()` runs only once per task.
4. `-proc:none` disables annotation processing so the experiment focuses on the compiler/file manager; do not use results from this experiment to infer performance of projects with processors.
5. `try-with-resources` closes the manager at the end of the block; do not keep it alive forever merely because it can cache.
6. Seeing two `.class` files confirms the example output. In real systems, still inspect bytecode, classpath, and test results to ensure outputs are neither stale nor version-mismatched.

The code above makes no claim about timing differences. To measure reuse benefits, you must also run a **fresh-manager-per-task** version and compare identical workloads, options, source counts, outputs, and environments in the same experiment.

### Do not call `call()` twice

The API specifies that a `CompilationTask` may execute only once. Calling `task.call()` a second time on an old task throws `IllegalStateException`. Reuse belongs to resources designed to be shared; a task is a single-use unit of work.

If collecting diagnostics, create a separate `DiagnosticCollector` per pass or maintain an explicit management policy. Do not accidentally mix warnings/errors across multiple requests when measuring compilation failure rates.

## 5. Bounded reuse: defining scope, quotas, and ownership

**Bounded reuse** means each resource is kept alive within a defined scope, with criteria for continued use and a termination point. Aspects to design:

| Limit | Question to Answer | Illustrative Policy |
| --- | --- | --- |
| Worker count | How many compilations run concurrently? | Fixed pool and bounded queue |
| Per-task time | What is the maximum duration a task may run? | Monitored deadline; terminate process if hard timeout is required |
| Memory | Maximum heap, metaspace, RSS, file handles? | Memory budget and checks before accepting new tasks |
| Reuse count | How many tasks does one worker handle before recreation? | Max task count/worker age, tuned by measurement |
| Freshness | What happens when classpath/sources/options change? | Invalidation or creating a fresh manager/worker |
| Isolation | Who has read/write access to task sources and outputs? | Per-request/tenant directory and process isolation |

These limits are **system design policies**, not built-in properties of every `JavaCompiler`. Do not pick arbitrary fixed constants like “10 tasks is definitely optimal”: appropriate thresholds must be measured per JDK, dependencies, project size, core count, and server resources.

A processing flow can be used:

```text
Request -> validate -> bounded queue
                          |
                     acquire slot
                          |
                  check input/version
                          |
                  create new task
                          |
                 compile + collect diagnostics
                          |
                release task data
                          |
               check resource budget
                          |
               reuse or close worker
```

Separate responsibilities: a task holds inputs and diagnostics for **one request**; a manager can serve multiple sequential tasks when valid; a worker manages processes/JVMs, concurrency, limits, and restarts. Queue wait time is also part of the latency perceived by users.

## 6. Why can caching produce wrong results?

Reusing a manager is not automatically synonymous with incremental compilation. If a JAR at the same path is replaced by another version, or the classpath/annotation processors/options change, do not assume old caches in every implementation detect the changes accurately.

Scenarios requiring refreshing the manager or worker by input version:

- A dependency JAR changed contents or classpath ordering changed.
- Sources, generated sources, or module path changed across multi-pass compilations.
- An annotation processor/plugin was upgraded or holds internal state.
- A task from another tenant requires a different classpath or filesystem permissions.
- Output contains orphan `.class` files after sources were deleted/renamed.
- A long-lived worker grows in RSS, heap, file handles, or shows signs of resource leaks.

**Distinguish four mechanisms**:

| Mechanism | What Is Reused? | Risk If Poorly Managed |
| --- | --- | --- |
| Process/JVM reuse | Living compiler process | Memory, GC, interference, access permissions |
| File manager reuse | File manager across sequential compilations | Caches/handles and modified source data |
| Incremental compilation | Skipping unaffected sources based on a graph | Missing dependencies leaving stale bytecode behind |
| Build cache | Prebuilt artifacts for a matching input fingerprint | Incomplete cache key causing wrong outputs |

One mechanism does not automatically replace the others. For instance, a reused manager does not remove the need to recompile clients depending on a modified compile-time constant.

### Resource closing rules

`StandardJavaFileManager` provides a `close()` method; use `try-with-resources` as in the example to close at the end of scope. Documentation also notes the standard manager can reopen itself after `flush`/`close` when accessed; however, that does not turn `close()` into an immediate release of all JVM memory. GC and the implementation determine the rest.

Close the manager and stop the worker when quotas expire; when guaranteeing zero open handles or strict state isolation is needed, verify actual implementation behavior and consider terminating the process.

## 7. Avoiding unguaranteed concurrent sharing of compiler state

`JavaCompiler` documentation recommends the `StandardJavaFileManager` reuse pattern for **multiple sequential compilations**. This is not a guarantee that sharing a manager or all compiler components **concurrently across multiple threads** is always safe.

For parallel execution, the conservative approach is giving each worker its own manager/owner and running only one task within that manager at a time. Even if a specific implementation advertises different concurrency support, test thoroughly and isolate state/diagnostics/outputs per task.

Increasing workers from 1 to 8 does not guarantee an eightfold throughput increase: the compiler can be bottlenecked by CPU, I/O, memory, or GC. Under resource contention, median latency may improve while p99 worsens. Choose concurrency via progressive-load benchmarks, monitoring throughput, p95/p99, RSS, and error rates.

**Timeouts:** `Future.cancel(true)` or interrupting a Java thread does not guarantee a custom compiler/processor stops immediately. If the system requires hard deadlines, CPU/RAM limits, and reliable termination, use process/container isolation and termination at the process boundary.

**Security:** compiling untrusted sources inside the host application JVM is not a sandbox. Annotation processors, compiler plugins, and build scripts can run code with process permissions. Establish appropriate safety policies/limits and isolation before accepting external sources.

## 8. Designing fair benchmarks

You cannot conclude reuse is faster if two approaches perform different amounts of work. A valid benchmark must compare on the **exact same workload**.

Scenarios to measure separately:

1. **Cold external `javac`:** spawn a new process, compile a designated set of sources.
2. **Repeated external `javac`:** a new process each run, measuring multiple runs to observe OS cache effects.
3. **In-process fresh manager:** one long-lived JVM, yet creating a fresh manager for every task.
4. **In-process reused manager:** one long-lived JVM, manager used sequentially for multiple tasks.
5. **Real build tool:** the actual Gradle/Maven/IDE pipeline in use, including workers, incremental builds, or caches.
6. **Concurrent load:** multiple requests, queueing, worker scheduling, and memory pressure.

Record alongside the results: JDK vendor/version, OS, CPU, RAM, disk, source/LOC count, dependency count and JAR sizes, options, annotation processors, heap flags, output policy, warm-up counts, sample counts, concurrency, and background load. Do not compare numbers from two different machines/JDKs as though they were one controlled experiment.

Track:

- **Per-task latency:** wall-clock milliseconds, median/p50, p95, and p99 when sample count permits.
- **Throughput:** compilations/second at defined load.
- **Startup overhead:** process/JVM creation + initialization, separated from compiler work when feasible.
- **Resources:** CPU, peak RSS, heap/metaspace, GC pauses, open handles.
- **Correctness:** compilation success rate, diagnostics, generated bytecode names/counts, and test outcomes.
- **Stability:** run-to-run variance and tail latency as load increases.

Running 100 consecutive passes on an already-warmed system does not measure cold start. Conversely, clearing OS caches or repeating clean builds inconsistently between approaches yields an unfair comparison.

## 9. Measuring external `javac` runs in PowerShell

After running `CompileTwice`, the sources `sample-src/Alpha.java` and `sample-src/Beta.java` already exist. You can measure ten invocations of `javac`, **each in a separate process**:

```powershell
New-Item -ItemType Directory -Force external-out | Out-Null

$measurements = foreach ($run in 1..10) {
    $duration = Measure-Command {
        & javac --release 17 -proc:none -d external-out sample-src/Alpha.java sample-src/Beta.java
    }

    if ($LASTEXITCODE -ne 0) {
        throw "javac failed at run $run"
    }

    [pscustomobject]@{
        Run = $run
        Milliseconds = $duration.TotalMilliseconds
    }
}

$measurements | Format-Table
```

**There is no fixed table of numbers:** timings depend on hardware, JVM, OS cache, and background load. The measurement includes PowerShell's process-spawning cost, compiler startup, and compilation execution. Sources are specified directly so the compiler is instructed to process them each pass; however, the OS file cache may still be warm and outputs already exist.

Do not compare this command directly with the `CompileTwice` example, because the API example did not measure timing and split compilation into two tasks. For a fair comparison, compile the exact same source set, options, pass count, and output policy; collect multiple samples and compute the latency distribution.

To measure a **clean build**, clean outputs *consistently* across both approaches and separate directory cleanup time from compiler time if cleanup is not what you intend to measure. Do not include file deletion in approach A while omitting it in B.

### Measuring `CompilationTask.call()` duration in Java

The code below is a **snippet inserted into a method that already has a `task` variable**, not a standalone program:

```java
long startedNanos = System.nanoTime();
boolean success = Boolean.TRUE.equals(task.call());
long elapsedNanos = System.nanoTime() - startedNanos;

if (!success) {
    throw new IllegalStateException("Compilation failed");
}
double elapsedMs = elapsedNanos / 1_000_000.0;
```

`System.nanoTime()` is suitable for measuring elapsed time within one JVM, not wall-clock calendar timestamps. Measuring around `task.call()` **excludes** process/JVM startup, creating the compiler/manager/task, or pre-call queueing. Measure at the boundary matching your goal: “compiler execution” differs from “API request end-to-end latency”.

To validate file manager reuse effectiveness, measure setup and `call()` for **both** fresh and shared manager strategies, not just the `call()` time of one side alone.

## 10. Trade-offs between latency and resource budget

Reducing latency is insufficient if memory consumption or other requests' latency spikes sharply:

| Change | Expected Benefit | Risks / Metrics to Monitor |
| --- | --- | --- |
| Batching compatible sources in one compile | Fewer process startups and repeated resolution | Complexity / single partial error affecting the whole batch |
| Using in-process JavaCompiler | Eliminates per-pass JVM startup | Impacts host app heap, CPU, GC |
| Sequential file manager reuse | May reduce filesystem/JAR scanning | Handles, freshness, lifecycle, and concurrency |
| Long-lived worker JVM | Amortizes startup across many requests | Growing RSS/GC, open resources, accumulated state |
| Increasing worker count | Higher capacity if unsaturated | CPU/I/O/RAM contention, rising p95/p99 |
| Reducing concurrency and bounding queues | Protects system under load | Increased wait times or rejecting over-quota requests |

Keep a worker alive only when workload frequency is high enough that startup savings outweigh idle memory cost. For infrequent compilations, independent processes can be cheaper in total resources and easier to recover.

If using a pool, consider task-count and lifetime quotas, but validate thresholds with data instead of arbitrary numbers. When quotas are reached, close the manager/worker and recreate it; emit metrics on recycle reasons to detect memory leaks or input invalidation.

## 11. Common measurement or implementation pitfalls

**Reusing one `CompilationTask` across multiple passes.** Invalid: a task calls `call()` once. Create a new task.

**Sharing one file manager across threads assuming thread safety.** The standard pattern guarantees sequential reuse. You must establish an explicit ownership/concurrency strategy.

**Retaining a manager even when JARs or classpath change.** Do not assume caches always reflect new inputs. Invalidate/recreate under control.

**Keeping workers alive indefinitely to avoid startup.** Risks growing heap, file handles, GC pressure, and impacting the host application.

**Benchmarking with `-proc:none` and assuming production with processors is equally fast.** You must measure production workloads, including processors and generated sources.

**Looking only at `task.call()` and calling it “startup latency”.** Startup may have already occurred outside the measured interval. Define KPIs accurately.

**Comparing a clean build against a warm incremental build.** Both approaches perform different amounts of work; no valid conclusion can be drawn from one number.

**Scaling workers unboundedly when queues grow.** Can cause out-of-memory errors or reduce total throughput. Use bounded queues/backpressure.

**Using in-process JavaCompiler as a sandbox for untrusted sources.** Provides no security guarantee; use proper isolation.

**Seeing old outputs and concluding compilation succeeded.** Check the `call()` result, diagnostics, and fresh class files. Orphan outputs can persist if build-owned directories are not cleaned.

## 12. Decision process in real projects

1. **State the goal:** reduce cold start, median latency, p99, or increase throughput? What memory/CPU budgets exist?
2. **Record the baseline:** JDK, build commands, source count, dependencies, processors, cache state, time and memory metrics.
3. **Identify bottlenecks:** spawn/JVM, dependency scanning, processing, parse/type check, I/O, or queueing?
4. **Try low-risk changes first:** eliminate redundant compiles, split modules sensibly, batch compatible sources, fix dependency graphs and incremental caching.
5. **If in-process compilation is needed:** create a fresh task each time, consider sequential file manager reuse, and define close/invalidation policies.
6. **If a worker pool is needed:** bounded queue, concurrency limits, resource budgets, deadlines, and restart lifecycles.
7. **Re-benchmark fairly:** keep inputs and compile semantics constant, measuring memory/tail latency and error counts too.
8. **Verify correctness:** diagnostics, bytecode, classpath, and tests on the actual generated artifacts.
9. **Monitor post-deployment:** RSS/GC, handle counts, p95/p99, queue depth, timeouts, and compile failures.

### When to prefer which approach?

- Infrequent compilations, latency non-critical, isolation needed: **separate `javac` process** is usually simplest.
- Many small **sequential** compilations with relatively stable dependencies: test **JavaCompiler API + file manager reuse** and measure.
- Large multi-module builds: inspect **incremental compilation and build caching** of your existing build tool first.
- Concurrent load requiring strict limits: consider an **isolated worker pool**, never sharing mutable compiler state carelessly.
- Compiling untrusted sources: choose **process/container isolation** boundaries and appropriate resource limits.
- Reuse fails to improve metrics or increases memory: keep the simpler approach and look for another bottleneck.

## 13. Self-check questions

**1. Why can two small `javac` commands cost more than one batched command?**  
Because process/JVM creation and compiler setup may be repeated in addition to processing each source. Batch only when compile configurations are compatible.

**2. Which resource does the JavaCompiler API explicitly state can be reused across sequential compilations?**  
`StandardJavaFileManager`; reuse can help reduce scanning/JAR I/O, though there is no speed guarantee for every workload.

**3. Can `task.call()` be called again?**  
No. Each `CompilationTask` executes only once. Subsequent passes need a new task.

**4. Why does file manager reuse not replace incremental compilation?**  
It manages file/JAR access; it does not automatically determine the complete set of sources needing recompilation from a dependency graph.

**5. Why measure RSS and p99 when increasing workers?**  
An approach may boost average throughput while consuming excessive memory or worsening tail latency.

**6. Does `Future.cancel(true)` guarantee the compiler stops immediately?**  
No. Interruption is not a hard timeout, especially when custom processors/plugins do not cooperate; terminating an isolated process may be required.

**7. Is a result claiming “reuse is twice as fast” trustworthy if the reuse approach compiled one file while external `javac` compiled two files?**  
No. Benchmarks must keep workload volume and configuration equivalent.

## 14. Pre-adoption checklist

- [ ] Distinguished startup from parsing/type checking/annotation processing/I/O.
- [ ] Have a representative workload with explicit JDK, classpath, options, sources, and outputs.
- [ ] Measured cold and warm separately, with appropriate warm-up and sample counts.
- [ ] Created a new `CompilationTask` per pass; invoked `call()` exactly once.
- [ ] If reusing `StandardJavaFileManager`: sequential, clear ownership, stable inputs, and lifecycle-managed close.
- [ ] Implemented invalidation/restart when dependencies, sources, processors, or options change.
- [ ] Enforced limits on workers, queues, deadlines, heap/RSS, and handles.
- [ ] Measured latency, throughput, p95/p99, memory, and error rate; did not pick solely on fastest single number.
- [ ] Checked compiler diagnostics, output bytecode, and tests on fresh artifacts.
- [ ] Did not treat in-process compilation as a safe isolation boundary for untrusted code.

**Remember:** Reusing compiler resources is a conditional optimization. Keep alive only resources with a clear reuse contract, lifecycle control, resource limits, and benchmark evidence on real workloads.

## References

- [Java SE 21 — JavaCompiler API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Java SE 21 — JavaCompiler.CompilationTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html)
- [Java SE 21 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html)
- [Java SE 21 — ToolProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html)
- [Java SE 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)