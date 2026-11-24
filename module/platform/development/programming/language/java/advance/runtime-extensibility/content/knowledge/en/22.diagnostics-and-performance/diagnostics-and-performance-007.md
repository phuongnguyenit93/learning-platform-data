# Measuring Discovery, Compilation, Initialization, and Warmed Invocation Costs Separately

## 1. Why Separate Performance Measurements?

In runtime-extensible Java systems (SPI, plugin JARs, custom class loaders, `JavaCompiler`, reflection, or JShell), a single number labeled "plugin load and execution time" often mixes several distinct operations:

- **Discovery:** locating provider lists, metadata, descriptors, or plugin modules to learn which extensions are available.
- **Compilation:** compiling Java source into bytecode (if plugins are compiled at runtime); pre-packaged plugin JARs do not always need this phase.
- **Initialization:** may include loading/linking classes, running static initializers, looking up constructors/factories, allocating objects, and lifecycle hooks; you must state explicitly which parts are measured.
- **Warmed invocation:** executing an operation on an **existing instance** after the JVM has had the opportunity to profile and JIT-compile the hot path.

Measuring all of these inside one `System.nanoTime()` span and calling it "cost per invoke" misrepresents the scope. Discovery and compilation are typically **setup costs**, whereas method invocations may run millions of times. These two cost classes affect startup SLAs and throughput differently.

The goal of this article is to **clearly define four measurement boundaries**, write a standalone Java 17+ program, validate meaningful output, distinguish cold vs. warm runs, recognize microbenchmark pitfalls, and know when to move to JMH/JFR.

## 2. Draw Boundaries Before Picking a Timer

~~~text
JAR / source / plugin manifest
    |
    +--> A. Discovery: enumerate names/types (no instances created yet)
    |
    +--> B. Compilation: source -> byte[] (if compiled at runtime)
    |
    +--> C. Class preparation / constructor / provider activation
    |
    +--> D. Invoke on an already warmed-up instance
~~~

These four paths form a **cost taxonomy**, not a mandatory execution sequence. For example, Java plugin source may be compiled **before** being registered for discovery; an iterator-based `ServiceLoader` loop can **discover and instantiate providers inside the same loop**. When designing measurements, split those operations into concrete units of work.

Ask four questions before measuring:

1. **What is one operation?** Scanning one provider or all providers? One compiler task or an entire project build? One `newInstance()` or the full `start()` hook? One `apply()` call or a request including network I/O?
2. **Cold or warm?** Freshly started JVM, classes unloaded, OS caches cold, JIT uncompiled, or already executed many times?
3. **What is included and excluded?** Filesystem scans, JAR reads, metadata parsing, classloading, constructor reflection lookup, GC, logging, network, test harness?
4. **Which metric fits?** Median/p95 latency, ops/s, allocation bytes/op, CPU utilization, GC pauses, or startup-to-ready time?

A report stating only "12 ns" without specifying the operation unit, JVM/CPU, iteration count, and measured code is practically unusable for decision-making.

## 3. Discovery Phase: Do Not Confuse Creating `ServiceLoader` with Enumerating Providers

`ServiceLoader` uses lazy discovery. Calling:

~~~java
ServiceLoader<Task> serviceLoader =
        ServiceLoader.load(Task.class, apiLoader);
~~~

only constructs the service loader without necessarily locating all implementations yet. This is an integration snippet (requiring `Task`, `apiLoader`, and `import java.util.ServiceLoader`).

If the goal is to **scan provider metadata without instantiating providers yet**:

~~~java
List<Class<?>> types = ServiceLoader.load(Task.class, apiLoader)
        .stream()
        .map(ServiceLoader.Provider::type)
        .toList();
~~~

`Provider.type()` returns the provider type without calling `Provider.get()`. Enumeration may read `META-INF/services`, parse names, load type metadata, validate providers, and benefit from class/resource caches. It is **not** a "pure string-reading" operation, yet it avoids deliberately folding constructor execution into timed discovery.

| Code Snippet | What It Actually Measures |
|---|---|
| `ServiceLoader.load(...)` only | Creating the loader object; providers not yet iterated |
| `stream().map(Provider::type).toList()` | Discovering provider types without intentionally instantiating them |
| `for (Task provider : loader)` | May include **instantiating providers** via the iterator |
| `Provider.get()` | Obtaining/instantiating the instance; belongs to initialization |
| Iterating **the same loader** again | May hit internal caches, differing from fresh discovery |
| `ServiceLoader.reload()` then iterating | Clears the instance's cache; does not reset JVM/classloading/JIT/OS caches |

**Demo unit:** each `discovery operation` creates a new `ServiceLoader` with an explicit SPI loader, iterates all provider **types**, and checks the names. Because the descriptor has one provider, each operation is **scanning 1 provider**. When comparing across runtimes, keep the provider count consistent.

**Do not mix scopes:** scanning `plugins/*.jar` on the filesystem, enumerating `URLClassLoader` resources, JPMS service provider resolution, and metadata parsing can be separate sub-phases. Measure the exact mechanism you deploy; `ServiceLoader.loadInstalled` is likewise not an API for scanning application-managed plugin directories.

## 4. Compilation Phase: Separate the Compiler Task from Loading/Running Classes

For dynamic Java source, you can use `javax.tools.JavaCompiler` in the same JVM:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
Boolean ok = compiler.getTask(
        null, fileManager, diagnostics, compilerOptions,
        null, sourceFiles).call();
~~~

This is an illustrative API snippet, not a standalone program. `ToolProvider.getSystemJavaCompiler()` can return `null` if the runtime image lacks the compiler; JDK 17+ with `jdk.compiler` available is required.

The **compilation phase** should be scoped precisely:

- **In-process compile task:** `JavaCompiler.getTask().call()` and associated source objects, diagnostics, and file manager.
- **In-memory compile:** source and output `JavaFileObject` backed by `String`/`ByteArrayOutputStream`; the compiler **still accesses the classpath** to resolve dependencies.
- **On-disk compile:** writes `.class` files to the filesystem, adding I/O and filesystem cache effects.
- **Forked `javac`:** spawns a new `javac` process; includes process/JVM startup and work outside the compiler task.
- **Compile + load + instantiate:** if you load the compiled class/output and invoke its constructor after compilation, do not label it simply "compilation".

In the demo, the program uses `SimpleJavaFileObject` for in-memory source, `ForwardingJavaFileManager` to capture `.class` output into a byte array, verifies that bytes actually exist, and **does not load or instantiate the newly compiled class**. Each operation measures one compiler task on a small source class.

Factors to record: source length, number of compilation units, classpath/module path, compiler flags, annotation processors, file manager reuse, JDK, and cache state. The sample passes `--release 17`, `-proc:none`, and the host classpath; `-proc:none` avoids running unnecessary annotation processors during the experiment.

## 5. Initialization Phase: Do Not Lump Class Init and Constructors Together

The word "initialization" in Java has multiple layers of meaning:

1. **Class loading:** the loader finds and defines the type from bytes.
2. **Linking/verification/resolution:** the JVM verifies and links symbolic references as needed.
3. **Static class initialization (`<clinit>`):** runs static initialization **once per runtime class identity**.
4. **Object construction:** instance allocation, instance initializers, and constructor **every time an object is created**.
5. **Plugin activation:** calling `start()`, injecting config, registering listeners, or opening files/sockets/connections per contract.

To measure **per-instance construction** cleanly, the demo prepares ahead of time:

~~~java
Class<? extends Task> type =
        provider.type().asSubclass(Task.class);
Constructor<? extends Task> constructor = type.getConstructor();
Task stable = constructor.newInstance(); // outside timed measurement
~~~

And then measures **many iterations**:

~~~java
Task another = constructor.newInstance();
~~~

`getConstructor()` and the first class initialization sit outside the timed constructor benchmark. `Constructor.newInstance()` still includes reflection overhead, allocation, constructor body execution, and `volatile` sink effects. The demo **does not** claim this represents cold-start time.

To measure **first class initialization**, you must deliberately create a fresh JVM or a fresh class loader so the class has an uninitialized identity; you cannot re-run `<clinit>` on a class already initialized by the JVM. If measuring loader creation, bytecode lookup, linking, and the first `new` together, report it as `cold load+initialize+construct` rather than pure constructor cost.

For a provider in a named module, `ServiceLoader.Provider.get()` may use either a constructor or a provider factory method. If your production system uses a factory, benchmark the **actual factory path**; do not treat the demo's `newInstance()` as representative of every SPI.

## 6. Warmed Invocation Phase: Keep the Instance Stable

When measuring invocation:

~~~java
Task prepared = constructor.newInstance(); // outside measured region

// Warm up the exact operation and critical code paths
int result = prepared.apply(input);
~~~

This is an illustrative snippet; variables must be declared inside an actual method. **Never** call `ServiceLoader.load(...)`, `JavaCompiler.getTask(...)`, or `constructor.newInstance()` inside the timed invocation loop if you want to isolate hot-call metrics.

Why does warm-up matter?

- The JVM/JIT gathers profiling data and compiles/optimizes code over time; initial calls may run in the interpreter or still resolve dependencies.
- Interface calls may be **devirtualized/inlined** once the JVM knows the implementation; the measured cost is then no longer a simple "interface call fee".
- Garbage collection, safepoints, tiered compilation, deoptimization, and CPU scheduling affect latency.
- The JIT can eliminate computations whose results are never observed.

In the demo, `CallJob` maintains an incrementing input and an accumulated checksum; the checksum is retained after the benchmark. This reduces the risk of dead-code elimination, yet the measurement **still includes** loop overhead, updating input and checksum, the interface call, and JIT optimizations. It represents **invocation cost on the demo workload**, not an absolute number for `invokeinterface`.

## 7. Reading the Clock and Statistics

`System.nanoTime()` is used via **the difference of two readings** to measure elapsed time, not as a Unix timestamp. For short operations, batch many invocations together:

~~~java
long start = System.nanoTime();
for (int i = 0; i < repetitions; i++) {
    job.run();
}
long elapsed = System.nanoTime() - start;
double nsPerOp = (double) elapsed / repetitions;
~~~

This is an **illustrative integration snippet** assuming `Job job` is defined; a usable benchmark still needs warm-up, multiple rounds, sanity checks, and statistics.

**A sound educational workflow:**

1. Warm up the exact operation before timing.
2. Run multiple measured rounds with **the same batch size**.
3. Measure `nanoTime` elapsed for **each round**, not around each individual call.
4. Take the median across rounds and divide by operations per batch to estimate `ns/op`.
5. Report units, sample counts, JVM/JDK/CPU, and warm state.
6. When actually optimizing, use **JMH** and multiple JVM forks, and report variance/p95 whenever tail latency matters.

Never sum medians of phases measured under different conditions to infer exact end-to-end p99. Phases depending on caches, JIT, GC, and schedulers can interact strongly. `System.nanoTime` measures elapsed wall-clock time; it is not synonymous with CPU cycles of a single thread.

## 8. Complete Java 17+ Example: Benchmarking the Four Phases Separately

The demo uses classpath SPI for reproducibility. It has one provider, the built-in Java compiler, and one small method. The four timing numbers **vary by system**, while the verification lines for provider count, compiled class, and checksum remain stable.

### 8.1. Project Structure

~~~text
phase-bench/
  src/
    demo/
      spi/Task.java
      impl/BasicTask.java
      PhaseBench.java
  out/
    META-INF/services/demo.spi.Task
~~~

`out` is created by the compile and descriptor-generation commands. The descriptor file must be named with the exact **fully qualified service interface name** `demo.spi.Task`, containing the provider's binary name.

### 8.2. Service API — `src/demo/spi/Task.java`

~~~java
package demo.spi;

public interface Task {
    int apply(int value);
}
~~~

`Task.apply(int)` is an operation with deterministic output and no network/disk I/O. It helps demonstrate checksum tracking and hot calls.

### 8.3. Provider — `src/demo/impl/BasicTask.java`

~~~java
package demo.impl;

import demo.spi.Task;

public final class BasicTask implements Task {
    public BasicTask() {}

    @Override
    public int apply(int value) {
        return value * 3 + 1;
    }
}
~~~

A public provider with a public no-arg constructor implementing the shared service interface. Classpath `ServiceLoader` will discover it from the matching descriptor.

### 8.4. Host Benchmark — `src/demo/PhaseBench.java`

~~~java
package demo;

import demo.spi.Task;
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.lang.reflect.Constructor;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.ServiceLoader;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class PhaseBench {
    private static volatile Object sink;
    private static final String DYNAMIC_SOURCE = """
            package demo.generated;
            import demo.spi.Task;
            public final class CompiledTask implements Task {
                public CompiledTask() {}
                public int apply(int value) { return value + 7; }
            }
            """;

    @FunctionalInterface
    interface Job {
        void run() throws Exception;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader apiLoader = Task.class.getClassLoader();
        List<ServiceLoader.Provider<Task>> providers =
                ServiceLoader.load(Task.class, apiLoader).stream().toList();
        if (providers.size() != 1) {
            throw new IllegalStateException("Expected exactly one provider");
        }
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        Class<? extends Task> type =
                providers.get(0).type().asSubclass(Task.class);
        Constructor<? extends Task> constructor = type.getConstructor();
        Task stable = constructor.newInstance();
        CallJob callJob = new CallJob(stable);

        Job discovery = () -> {
            List<String> names = ServiceLoader.load(Task.class, apiLoader)
                    .stream().map(p -> p.type().getName()).toList();
            if (!names.equals(List.of("demo.impl.BasicTask"))) {
                throw new IllegalStateException("Discovery mismatch");
            }
            sink = names;
        };
        Job compilation = () -> compileOne(compiler);
        Job initialization = () -> sink = constructor.newInstance();

        double discoveryNs = medianNsPerOp(discovery, 3, 7, 40);
        double compilationNs = medianNsPerOp(compilation, 1, 5, 1);
        double initializationNs = medianNsPerOp(initialization, 3, 7, 20_000);
        double callNs = medianNsPerOp(callJob, 3, 7, 100_000);
        sink = callJob.checksum;

        System.out.println("providers=" + providers.size());
        System.out.println("compiled-class=demo.generated.CompiledTask");
        System.out.printf(Locale.ROOT, "discovery=%.1f ns/op%n", discoveryNs);
        System.out.printf(Locale.ROOT, "compilation=%.2f ms/compile%n",
                compilationNs / 1_000_000);
        System.out.printf(Locale.ROOT, "initialization=%.1f ns/newInstance%n",
                initializationNs);
        System.out.printf(Locale.ROOT, "warmed-call=%.1f ns/apply%n", callNs);
        System.out.println("checksum-positive=" + (callJob.checksum > 0));
    }

    private static double medianNsPerOp(
            Job job, int warmRounds, int measuredRounds, int batch)
            throws Exception {
        for (int r = 0; r < warmRounds; r++) {
            for (int i = 0; i < batch; i++) {
                job.run();
            }
        }
        long[] times = new long[measuredRounds];
        for (int r = 0; r < measuredRounds; r++) {
            long start = System.nanoTime();
            for (int i = 0; i < batch; i++) {
                job.run();
            }
            times[r] = System.nanoTime() - start;
        }
        Arrays.sort(times);
        return (double) times[measuredRounds / 2] / batch;
    }

    private static void compileOne(JavaCompiler compiler) throws Exception {
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        try (StandardJavaFileManager standard =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            MemoryFiles files = new MemoryFiles(standard);
            JavaFileObject source =
                    new Source("demo.generated.CompiledTask", DYNAMIC_SOURCE);
            Boolean ok = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none", "-classpath",
                            System.getProperty("java.class.path")),
                    null, List.of(source)).call();
            if (!Boolean.TRUE.equals(ok)) {
                throw new IllegalStateException(
                        "Compilation failed: " + diagnostics.getDiagnostics());
            }
            byte[] output = files.getBytes("demo.generated.CompiledTask");
            if (output == null || output.length == 0) {
                throw new IllegalStateException("Missing compiled class");
            }
            sink = output;
        }
    }

    private static final class CallJob implements Job {
        private final Task task;
        private int input;
        private long checksum;
        CallJob(Task task) {
            this.task = task;
        }
        @Override
        public void run() {
            checksum += task.apply(input++);
        }
    }

    private static final class Source extends SimpleJavaFileObject {
        private final String source;
        Source(String name, String source) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }
        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    private static final class BinaryOutput extends SimpleJavaFileObject {
        private final ByteArrayOutputStream output =
                new ByteArrayOutputStream();
        BinaryOutput(String name, Kind kind) {
            super(URI.create("mem:///" + name.replace('.', '/')
                    + kind.extension), kind);
        }
        @Override
        public OutputStream openOutputStream() {
            return output;
        }
        byte[] getBytes() {
            return output.toByteArray();
        }
    }

    private static final class MemoryFiles
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, BinaryOutput> outputs = new HashMap<>();
        MemoryFiles(StandardJavaFileManager standard) {
            super(standard);
        }
        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String name,
                JavaFileObject.Kind kind, FileObject sibling) {
            BinaryOutput target = new BinaryOutput(name, kind);
            outputs.put(name, target);
            return target;
        }
        byte[] getBytes(String name) {
            BinaryOutput output = outputs.get(name);
            return output == null ? null : output.getBytes();
        }
    }
}
~~~

### 8.5. Compile, Register Provider, and Run

From the `phase-bench/` root using Bash (Linux/macOS or Git Bash):

~~~bash
mkdir -p out/META-INF/services

javac --release 17 -d out \
  src/demo/spi/Task.java \
  src/demo/impl/BasicTask.java \
  src/demo/PhaseBench.java

printf '%s\n' 'demo.impl.BasicTask' \
  > out/META-INF/services/demo.spi.Task

java -cp out demo.PhaseBench
~~~

On Windows PowerShell, the equivalent commands to create the descriptor:

~~~powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
javac --release 17 -d out src/demo/spi/Task.java src/demo/impl/BasicTask.java src/demo/PhaseBench.java
[System.IO.File]::WriteAllText(
    "out/META-INF/services/demo.spi.Task",
    "demo.impl.BasicTask" + [Environment]::NewLine)
java -cp out demo.PhaseBench
~~~

**Important point:** `javac --release 17` compiles **the host and provider** on disk in `out`. That is the **demo preparation step**, not the measured phase B. Phase B inside the program invokes `JavaCompiler` **inside the running JVM** to compile `demo.generated.CompiledTask` into in-memory output. The program **does not pass that compiled class into a class loader or instantiate it**, so phase B is not mixed with C.

Requires a JDK 17+ runtime containing `jdk.compiler`. The program uses `System.getProperty("java.class.path")` as the classpath for the compilation task; with `java -cp out` it resolves the SPI from `out`. If `ToolProvider.getSystemJavaCompiler()` returns `null`, the program intentionally fails fast.

### 8.6. What Output Is Correct?

In the example configuration with one descriptor and one provider, the stable lines are:

~~~text
providers=1
compiled-class=demo.generated.CompiledTask
...
checksum-positive=true
~~~

The three lines above use `...` to **elide** the four timing lines in the middle, not literal JVM output. The four actual timing lines have the format:

~~~text
discovery=<number> ns/op
compilation=<number> ms/compile
initialization=<number> ns/newInstance
warmed-call=<number> ns/apply
~~~

`<number>` is an **illustrative placeholder** for the measured value on each run; there is no fixed number to use as expected output. Tested by compiling with `javac --release 17` and running successfully on OpenJDK 24: one provider, class generated in memory by the compiler, all four timings printed, and `checksum-positive=true`.

Only the stable lines should be treated as assertions. Measured times must not be compared as a "universal baseline" across machines, as they depend on JDK, CPU/JIT, OS caches, GC, and background processes.

### 8.7. What Does Each Job Include?

| Job | Timed Operation | Intentionally Excluded |
|---|---|---|
| `discovery` | Create new `ServiceLoader`, enumerate provider types, verify names, write sink | No `Provider.get()`, no compilation, no constructor |
| `compilation` | Create diagnostics/file manager/source, compile bytecode in memory, verify output | Does not load/instantiate the newly compiled class |
| `initialization` | Loop `Constructor.newInstance()`, write `volatile` sink | Constructor lookup and initial static class init are outside the timed loop |
| `CallJob` | `Task.apply(input++)` on one instance, accumulate checksum | No provider instantiation, compilation, or discovery |

This is the **scope of this specific example**, not the single definition for every system. In production systems, initialization may include dependency injection, configuration, network connections, and lifecycle hooks; a benchmark measuring only an empty constructor would miss those costs.

### 8.8. Warm-Up and Measured Rounds

`medianNsPerOp` warms up and then executes measured batches. Demo configuration:

| Phase | Warm-Up Rounds | Measured Rounds | Operations per Measured Round |
|---|---:|---:|---:|
| Discovery | 3 | 7 | 40 scans |
| Compilation | 1 | 5 | 1 compiler task |
| Initialization | 3 | 7 | 20,000 constructor invocations |
| Invocation | 3 | 7 | 100,000 method invocations |

We compute the **median batch time**, then divide by the batch's operation count. This is an educational choice and does not guarantee the JIT reaches steady state for every workload. In particular, compilation has few rounds while hot calls are very fast; use JMH for measurements requiring engineering rigor.

## 9. Common Mistakes When Measuring Each Phase Separately

### 9.1. `ServiceLoader.load` Looks Fast Only Because It Has Done No Work Yet

Because discovery is lazy, a benchmark that only creates the loader object underestimates total service-lookup cost. Iterate to types or instances according to the exact question being measured.

### 9.2. Iterating Providers with an Iterator and Calling It Discovery-Only

Iterating can instantiate providers. If constructors are heavy, the result blends discovery + initialization. Using `Provider.type` isolates metadata scanning from instantiation.

### 9.3. Initializing a Class Repeatedly When `<clinit>` Only Runs Once

The JVM does not re-run static initializers on the same class identity. For cold class-loading, you must use a fresh JVM or a fresh loader/class identity by design, and state explicitly whether loader creation cost is included. `ServiceLoader.reload()` does not reset class metadata, JIT state, or OS filesystem caches.

### 9.4. Measuring Compilation by Forking `javac` and Comparing Against `JavaCompiler.getTask`

One includes JVM/process startup and I/O, while the other is a compiler task inside an already running JVM. The two measurements answer different questions. If your real workflow forks `javac`, measure the end-to-end fork; if the compiler API runs in-server, measure in-process.

### 9.5. Timing a Tiny Call with Two `nanoTime` Calls

Timer overhead can equal or exceed the operation itself. Batching reduces the timer-overhead ratio, yet a batch still includes loop, state, and JIT effects; the result is not automatically "pure `invoke` instruction cost".

### 9.6. JIT Eliminates Work with No Observable Result

Example of valid code easily optimized away:

~~~java
long total = 0;
for (int i = 0; i < 1_000_000; i++) {
    int unused = i * 3 + 1;
}
System.out.println(total);
~~~

`unused` never affects output, so the JIT can eliminate the computation. A proper benchmark needs observable returns/sinks, varied workloads, and correctness checks; JMH provides helpful mechanisms such as return values and `Blackhole`.

### 9.7. Using a Single Median to Hide GC / p99

Constructors and compilers allocate memory; a low median does not rule out p99 spikes from GC or lock contention. For SLA requirements, track allocation rate, GC pauses, percentiles, CPU time, and throughput as well.

### 9.8. Comparing Systems with Different Provider Counts or Inputs

Scanning one provider is not equivalent to scanning hundreds of JARs. Compiling one tiny class differs vastly from compiling a large module. One tiny invocation does not represent HTTP/database calls. Keep workload, provider/JAR count, classpath, compiler options, and datasets fixed.

### 9.9. Confusing Method Warm-Up with Whole-System Warm-Up

Warming one call does not mean module layers, network pools, serializers, the compiler, or all logic branches are warm. Warm up **the exact operations and paths** under evaluation; for startup SLAs, still measure cold paths separately.

### 9.10. Enabling Profiling/Logging and Comparing Directly Against Uninstrumented Runs

JFR and JVM classloading logs add measurable overhead; enabling verbose logging can alter timings. Use profiling to find root causes, then compare timings under consistent conditions.

## 10. JMH: The Right Tool When You Need Microbenchmark Conclusions

OpenJDK's **JMH (Java Microbenchmark Harness)** specifically handles warm-up, forks, measured iterations, state, and JIT optimization pitfalls when measuring small operations.

**Illustrative** skeleton example (does not compile with JDK alone; requires JMH dependencies and annotation processor plugin):

~~~java
import demo.spi.Task;
import demo.impl.BasicTask;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class TaskInvocationBenchmark {
    private Task cached;
    private int input;

    @Setup(Level.Trial)
    public void setup() {
        cached = new BasicTask();
    }

    @Benchmark
    public int invokeAfterWarmup() {
        return cached.apply(input++);
    }
}
~~~

Here `@Setup(Level.Trial)` sits outside the timed invocation method; `@Fork` runs measurements in separate JVM forks to isolate JIT state. However, **JMH does not automatically fix a mis-scoped benchmark**: if you put compilation or provider construction inside `@Benchmark`, you are still measuring them. Discovery/compilation/initialization benchmarks must define state, samples, warmup/forks, and result validation tailored to each unit of work.

Do not extrapolate a "JMH score" from `PhaseBench`'s output; the two harnesses have different structures, durations, and statistical models.

## 11. JFR and Root-Cause Diagnosis

**Java Flight Recorder (JFR)** provides visibility into CPU, allocations, GC, threads/blocking, and certain classloading activities depending on configuration. Example JDK command:

~~~bash
jcmd PID JFR.start name=plugin-bench settings=profile duration=30s filename=plugin-bench.jfr
~~~

`PID` is the attachable Java process ID. This is an **illustrative command**; a short demo may exit before collecting enough data. For live services handling traffic, generate a sufficiently long workload and mark phase start/end boundaries to correlate JFR events.

You can enable class load/GC logging while debugging:

~~~bash
java -Xlog:class+load=info,gc*=info -cp out demo.PhaseBench
~~~

Enabling `-Xlog` increases log output and can shift timings; never use verbose-logged runs as a direct baseline comparison against unlogged runs. `jcmd` and `javap` are useful when inspecting JVM flags, bytecode, class descriptors, and diagnostic details. Use a profiler to understand *why* compilation, construction, or hot calls are slow rather than relying solely on a single `ns/op` number.

## 12. One-Time Costs vs. Per-Request Costs

An approximate accounting model, valid only when phases are defined **without overlap**:

~~~text
T_lifetime ~= T_discovery + T_compilation
            + T_load_init + T_activate
            + number_of_calls * avg_T_warmed_call
~~~

This is neither a p99 summation formula nor a claim that every plugin needs compilation. A prebuilt plugin JAR normally has `T_compilation_at_runtime = 0`, yet still pays startup scan, classloading, and initialization costs. For dynamic plugins, compilation can dominate startup.

- **Plugin loaded once, called heavily:** speeding up warmed invocation can pay off in CPU/throughput, while startup latency may still depend on compilation.
- **Plugin compiled or instantiated per request:** eliminating compilation and construction from the request path usually matters far more than shaving a few nanoseconds off a method.
- **Plugins scanned frequently via polling:** discovery/cache behavior can matter; measure using the real polling frequency, JAR count, and version churn.
- **End-to-end p99 SLAs:** collect tracing/JFR, request latencies, and GC metrics rather than letting a hot-method median represent the whole service.

Optimization priority depends on **actual cost multiplied by actual frequency**, not whichever line item looks nicest in nanoseconds.

## 13. Checklist for Reproducible Measurements

1. Define the exact **operation** for each phase and what is included/excluded.
2. Record commit/code version, JDK vendor/version, OS, CPU, and container quotas.
3. Fix provider/JAR count, source size, classpath/module graph, and compiler options.
4. Separate cold start, warm discovery, warm compiler, per-instance construction, and hot invocation.
5. Prevent code in a timed phase from "leaking" work belonging to another phase.
6. Use warm-up, multiple measured rounds, and multiple JVM forks when stability is needed.
7. Verify results are meaningful and kept live; never measure code eliminated by the JIT.
8. Report units explicitly: `ns/op`, `ms/compile`, `ops/s`; never mix units.
9. Record median, variance/percentiles, sample counts, and concurrency levels.
10. Inspect profiler/JFR/GC when outliers or large shifts appear.
11. For newly deployed plugins, verify classloader lifetime, caches, activation hooks, and unload/reload costs.
12. For dynamically compiled/executed code from untrusted sources, isolate at the process/OS level with resource limits; benchmarks are not sandboxes.

## 14. Self-Check

**1. Does calling `ServiceLoader.load(Task.class)` alone measure full discovery?**  
No. Discovery is lazy; you must iterate provider metadata or provider instances according to your target metric.

**2. What is the risk of using `for (Task t : loader)` to measure discovery-only?**  
It can also trigger provider instantiation, mixing two phases together.

**3. In the demo, is the compiled output loaded and executed by a class loader?**  
No. Bytecode stays in the in-memory output; compilation is measured separately from class loading and invocation.

**4. Does measuring `Constructor.newInstance()` after warm-up represent cold static class initialization?**  
No. The class was already prepared and instantiated before the timed loop.

**5. Does the hot invocation phase create a new provider on every call?**  
No. It reuses a pre-instantiated `Task stable`.

**6. Why are fixed timing numbers omitted from expected stdout?**  
Measurements depend on JIT, OS, CPU, GC, filesystem, JVM version, and system load; tests should assert labels/correctness only.

**7. When measuring a call taking a few nanoseconds, should you call `nanoTime` before and after each single call?**  
No. Timer overhead easily overwhelms the operation; use batching or JMH.

**8. Does `ServiceLoader.reload()` return the JVM to a cold state?**  
No. It clears only the `ServiceLoader`'s own cache without resetting JIT, loaded classes, or OS caches.

**9. Does JMH guarantee each benchmark measures only the phase you named it after?**  
No. Developers must still scope the unit of work and `@Setup` state properly.

**10. When startup SLAs are violated while hot calls are very fast, what should you optimize?**  
Separate discovery/compile/load/init/activate and optimize whichever phase dominates startup latency.

**11. Can an average `ns/op` metric replace p99 request latency?**  
No. Requests involve I/O, contention, and GC. Measure against end-to-end targets.

**12. When optimizing a compiler plugin, what should you compare?**  
Source count/size, classpath, file manager, output mode, JDK, caches, annotation processors, time per compile, and allocation/GC; never compare a single compiler task against an entire forked build.

**Key takeaway:** keep **discovery = enumerating provider metadata**, **compilation = compiler task producing bytecode**, **initialization = constructor/factory or separately scoped cold class init**, and **warmed invocation = calling an existing instance after warm-up**. Always report scope, cache/JIT warmth, operation units, correctness checks, and variance; use JMH/JFR when you need high-confidence engineering decisions.

## References

- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): lazy discovery, `Provider.type()` and `Provider.get()`, caching, `reload()`.
- [Java SE 17 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): compiler tasks, `getTask()`, compiler file managers, and diagnostics.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) and [`Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): class loading and reflective construction.
- [Java SE 17 — `System.nanoTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time measurement.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): microbenchmark harness, warm-up, measurement, forks, and benchmark state.
- [Java SE 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): JFR and JVM diagnostics.
