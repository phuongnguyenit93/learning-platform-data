# Measuring Startup, Linking, JIT Warm-up, and Steady-State Execution Separately When Java Calls Native Code

## 1. Objective: Properly Separating the Costs of a Native Interaction

In a Java application using **JNI (Java Native Interface)** or the **Foreign Function & Memory API (FFM)**, asking "how long does a native call take?" does not specify what is actually being measured. A fresh run can include JVM startup, class loading, dynamic library loading, symbol/call-path preparation, interpretation or JIT compilation of the Java side, and only then millions of steady-state calls. Lumping those phases into a single average can lead to wrong optimization decisions.

This lesson focuses on **Java ↔ native interoperability performance**: knowing how to set separate measurement boundaries for each phase, interpret numbers in the right context, and design reproducible benchmarks. The main examples use **Java 17+ and JNI/C**; a comparison with FFM is noted separately because FFM became a standard API in JDK 22. For JDK 24+, appropriate native access permissions must be granted when running the examples.

After this lesson, you can answer:

1. Is the application slow because of **JVM startup**, **library loading**, **the first native call**, **cold JIT**, or **steady-state repeated call cost**?
2. How do you measure "linking" without confusing it with execution cost?
3. When should you use the OS wall clock, `System.nanoTime()`, JFR, compiler logs, or **JMH**?
4. When reducing the number of Java/native boundary crossings, what is the actual improvement and is the trade-off worth it?

## 2. Map of the Four Phases to Distinguish

| Phase | Start/end points to observe | Appropriate measurement method | What **cannot** be concluded from that number alone |
| --- | --- | --- | --- |
| **A. Startup** (cold launch) | OS starts the `java` process → JVM is ready / application emits ready signal or completes a fixed task | Clock **outside the process**, running multiple fresh JVMs; application startup timestamp if available | `nanoTime()` inside `main` does not cover full JVM startup; wall time includes many other activities |
| **B. Native loading and linking** | `System.load / loadLibrary` call → return; **separately**, the first call to a `native` method → return | Two separate timers using `nanoTime()`; logs/JFR to confirm events | The "first call" time is **not** pure linking cost; it also includes function execution, adapters, class/JIT/OS |
| **C. JIT warm-up** | Repeating a representative workload before reporting steady-state numbers | Multiple batches, recording `ns/op` in order; inspect `-XX:+PrintCompilation`/JFR | One fast batch is not enough to prove stability; JIT may compile further or deoptimize |
| **D. Steady-state execution** | After the chosen warm-up, measure multiple batches/forks with the same workload | JMH for microbenchmarks; median, dispersion, and confidence intervals; real throughput/latency when needed | Numbers for a tiny native addition **do not** represent array copying, callbacks, or large native tasks |

Visualizing the typical progression:

~~~text
OS creates process
    ↓
JVM/bootstrap + class loading + initialization
    ↓
System.load / loadLibrary (+ OS dynamic loader, JNI_OnLoad if present)
    ↓
First call to native method (may bind symbol lazily)
    ↓
Multiple calls while JIT/interpreter and CPU caches are still changing
    ↓
Multiple calls in warmed-up state, collecting steady-state data
~~~

This is a **logical diagram**, not a guarantee that every JVM/library follows an absolute order. For example, a static initializer can load a library as soon as the class is used; a library can register native methods early via `RegisterNatives`; JIT is triggered and compiles asynchronously across multiple time slices.

### Why does "linking" need clarification?

- **OS loader:** when `System.load(...)` succeeds, the OS/JVM has already handled loading the library, necessary relocations, and potentially running initialization functions. If `JNI_OnLoad` exists, the JVM calls it during loading.
- **JNI native-method binding:** with standard JNI name-based linking, the JVM binds a `native`-declared call to the corresponding C function when that method is called for the first time. Libraries using `RegisterNatives` can perform registration eagerly, shifting the boundary above.
- **JIT compilation:** the HotSpot compiler optimizes **Java code** and call paths/adapters once hot enough. It does not "re-JIT compile" C functions already compiled by `cc/gcc/clang/MSVC`.

Therefore, `T_first_call` is a **proxy measurement for the first-use path (first-use latency)**, including binding **if** binding happens on that call; you cannot subtract `T_steady_call` from it and claim the difference is the "exact JNI linking time." Subtracting two measurements taken under different conditions also easily adds scheduler, cache, and JIT variance.

## 3. Planning Measurements Before Writing a Benchmark

Specify the real workload and business boundaries: a one-shot CLI process, a long-lived server, a batch processing millions of elements, or the first request that uses a native library. For servers, distinguish **time to process ready** from **first native request latency**; if lazy loading is deferred until the first request, startup looks faster, but the first request absorbs the added cost.

Choose appropriate metrics:

- **Startup:** wall-clock time of the entire process and/or from process start to ready signal; report median/p95 across **fresh** process runs. Note that "cold JVM" differs from "cold OS page cache" because launching a new JVM does not clear the page cache.
- **Load:** elapsed time surrounding only the library load call, reported in milliseconds; try to prepare path strings / read configuration outside the timed region if you only want loader time.
- **First call:** elapsed time of **the single first call** after load, reported in microseconds or nanoseconds, but presented as a proxy and run across multiple separate forks.
- **Warm-up:** record the time of each batch in order (for example, 100,000 calls per batch), without mixing them into steady samples; record iteration counts, volume, and JVM flags.
- **Steady state:** time or throughput after warm-up, typically `ns/op` / `ops/s`. If real service latency is needed, capture p50/p95/p99 at the request layer under production-equivalent load; microbenchmarks only answer a narrow scope.

**Clock rules:** take `end - start` from `System.nanoTime()` within a single JVM for short intervals. Do not use `System.currentTimeMillis()` to divide down to nanoseconds, and do not subtract `nanoTime()` values from two different processes. Calling the clock twice around **one** tiny native call will be dominated by measurement overhead; therefore, the steady-state portion must measure a **batch** of many calls and divide by the call count, while the first-call portion accepts the noise of a single-shot measurement.

For a fair experiment, fix the JDK vendor/version, OS, CPU architecture, JVM arguments, native library compiler flags, input data, thread count, load level, and machine conditions. Do not compare numbers across two different machines or two different JDKs and conclude JNI is the cause when many variables are uncontrolled.

## 4. Complete JNI Lab: One Native Method, Four Modes

The example uses a very small native function `next(x) = x + 1` to highlight Java/native boundary overhead. This is a **lesson in measurement**, not a compute application that needs C acceleration. The Java code is valid from **JDK 17 onward**, and the C library is compiled separately for each operating system.

### 4.1. Create `JniPhases.java`

~~~java
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Locale;

public final class JniPhases {
    private static final int CALLS = 100_000;
    private static final int WARM_BATCHES = 12;
    private static final int STEADY_BATCHES = 10;
    private static volatile long observed;

    public static native long next(long value);

    private static long runBatch() {
        long sum = 0;
        for (int i = 0; i < CALLS; i++) {
            sum += next(i);
        }
        observed = sum; // Keep the result observable outside the loop.
        return sum;
    }

    private static double median(double[] source) {
        double[] copy = source.clone();
        Arrays.sort(copy);
        int mid = copy.length / 2;
        return (copy.length % 2 == 0)
                ? (copy[mid - 1] + copy[mid]) / 2.0
                : copy[mid];
    }

    public static void main(String[] args) {
        String mode = args.length == 0 ? "all" : args[0];

        if ("baseline".equals(mode)) {
            System.out.println("baseline_ready");
            return;
        }
        if (!"load".equals(mode) &&
                !"first".equals(mode) &&
                !"all".equals(mode)) {
            throw new IllegalArgumentException(
                    "Use: baseline | load | first | all");
        }

        String lib = Path.of(System.mapLibraryName("jniphases"))
                .toAbsolutePath().toString();

        long start = System.nanoTime();
        System.load(lib);
        long loadNs = System.nanoTime() - start;

        if ("load".equals(mode)) {
            System.out.printf(Locale.ROOT,
                    "load_ms=%.3f%n", loadNs / 1_000_000.0);
            return;
        }

        start = System.nanoTime();
        long firstResult = next(3);
        long firstNs = System.nanoTime() - start;

        if (firstResult != 4L) {
            throw new AssertionError("Unexpected JNI result");
        }
        System.out.println("jni_result=" + firstResult);
        System.out.printf(Locale.ROOT,
                "load_ms=%.3f%n", loadNs / 1_000_000.0);
        System.out.printf(Locale.ROOT,
                "first_call_us=%.3f%n", firstNs / 1_000.0);

        if ("first".equals(mode)) {
            return;
        }

        double[] warm = new double[WARM_BATCHES];
        for (int i = 0; i < WARM_BATCHES; i++) {
            start = System.nanoTime();
            runBatch();
            warm[i] = (System.nanoTime() - start) / (double) CALLS;
        }

        double[] steady = new double[STEADY_BATCHES];
        long checksum = 0;
        for (int i = 0; i < STEADY_BATCHES; i++) {
            start = System.nanoTime();
            checksum = runBatch();
            steady[i] = (System.nanoTime() - start) / (double) CALLS;
        }

        if (checksum != 5_000_050_000L ||
                observed != 5_000_050_000L) {
            throw new AssertionError("Incorrect checksum");
        }

        System.out.println("batch_checksum=" + checksum);
        System.out.printf(Locale.ROOT,
                "warmup_ns_per_call_first=%.2f last=%.2f%n",
                warm[0], warm[warm.length - 1]);
        System.out.printf(Locale.ROOT,
                "steady_ns_per_call_median=%.2f%n", median(steady));
    }
}
~~~

Design notes of the program:

- The `baseline` mode does not load JNI and exits quickly, used to observe the baseline startup component. It does **not** strictly isolate JVM cost because it still includes class loading, `println`, class initialization, and shutdown.
- The `load` mode calls `System.load` exactly once in a fresh JVM and reports `load_ms`. The path is prepared **before** the timer; the variable still includes `System.load` call overhead and the OS loader.
- The `first` mode adds measurement of the single first JNI call after load; then it **stops** without mixing into steady-state measurements.
- The `all` mode continues by executing 12 warm-up batches and 10 measurement batches. Each batch has 100,000 calls; `observed` is a `volatile` variable holding the checksum to reduce the risk of the benchmark being optimized away.
- Do not print to the console **inside** the loop. Timing numbers are stored and only printed at the end of the phase to avoid I/O cost overshadowing the native function.
- `System.nanoTime()` measures time within a single JVM; the `ns_per_call` output is the **average cost of the loop + JNI + C function** divided by the call count, not a "pure crossing cost."

### 4.2. Create `jni_phases.c`

~~~c
#include "JniPhases.h"

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

JNIEXPORT jlong JNICALL Java_JniPhases_next(
        JNIEnv *env, jclass declaringClass, jlong value) {
    (void)env;
    (void)declaringClass;
    return value + 1;
}
~~~

`javac -h` generates the header `JniPhases.h` with the exact JNI signature for `next(long)`. The C function name `Java_JniPhases_next` matches the Java class in the **default package** and the method name. If you add a package or rename the class/method, you must regenerate the header and update the C code to the generated name; do not copy old symbols. `JNI_OnLoad` returns the supported JNI version; it runs during library loading, so its cost belongs to the **load phase**, and must not be misattributed to first-call binding.

### 4.3. Compile

Requires JDK 17+ (with `javac` and `jni.h` headers), a C compiler, and the `JAVA_HOME` environment variable pointing to the **same JDK** used to compile/run. Place both files in a working directory; the commands below run directly inside that directory.

**Linux** (GCC or Clang; example uses `cc`):

~~~bash
javac -h . JniPhases.java
cc -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libjniphases.so jni_phases.c
~~~

**macOS**:

~~~bash
javac -h . JniPhases.java
cc -O2 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -o libjniphases.dylib jni_phases.c
~~~

**Windows**, run in x64 Native Tools Command Prompt for Visual Studio (with `cl` and `JAVA_HOME` set):

~~~bat
javac -h . JniPhases.java
cl /LD /O2 /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jni_phases.c /Fe:jniphases.dll
~~~

Java selects the library name using `System.mapLibraryName("jniphases")`: `libjniphases.so`, `libjniphases.dylib`, or `jniphases.dll` depending on the OS. It is loaded using an **absolute path** to the working directory, so `-Djava.library.path` is not needed. If running from another directory, you must adjust the path/directory accordingly. The binary architecture must match the JVM architecture (x64/ARM64).

### 4.4. Run Each Phase and Verify Output

For **JDK 17–23**:

~~~bash
java -cp . JniPhases baseline
java -cp . JniPhases load
java -cp . JniPhases first
java -cp . JniPhases all
~~~

For **JDK 24+**, JNI loading/binding falls under native access restrictions. When benchmarking, grant access to code on the class path to prevent warnings or access errors from skewing results:

~~~bash
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp . JniPhases baseline
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp . JniPhases load
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp . JniPhases first
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp . JniPhases all
~~~

The **exact, machine-independent** output lines of the program are:

~~~text
baseline_ready
~~~

for `baseline` mode alone; for `first` and `all`, it always outputs:

~~~text
jni_result=4
~~~

For `all`, it also outputs:

~~~text
batch_checksum=5000050000
~~~

The numbers after `load_ms=`, `first_call_us=`, `warmup_ns_per_call_first=... last=...`, and `steady_ns_per_call_median=` **vary by machine and run**, so there are no fixed stdout numbers valid for copying. Reason for the fixed checksum: in each batch, the C function returns `1, 2, ..., 100000`, whose sum is `100000 × 100001 / 2 = 5000050000`.

If `UnsatisfiedLinkError` is thrown, check the native file name, working directory, architecture, dependent libraries, and generated function signature. If `IllegalCallerException` is thrown on JDK 24+, check the native access flags and module/class path; that is a permissions issue, not a performance conclusion.

## 5. Measuring True Startup from **Outside** the JVM

If you only start `System.nanoTime()` inside `main`, a large portion of JVM bootstrap, VM preparation, class reading, and initial setup has already elapsed. Use the clock of the process invoking the JVM to measure **inclusive wall-clock** time.

Example on **Linux with GNU time**:

~~~bash
/usr/bin/time -f 'wall_s=%e' java -cp . JniPhases baseline
/usr/bin/time -f 'wall_s=%e' java -cp . JniPhases load
/usr/bin/time -f 'wall_s=%e' java -cp . JniPhases first
/usr/bin/time -f 'wall_s=%e' java -cp . JniPhases all
~~~

On JDK 24+, add the two native access flags to **each command** as in section 4.4. `/usr/bin/time` measures from process creation until process exit, including shutdown and I/O time; that is the **end-to-end number of the mode** being run, not solely "JVM bootstrap time." If you only need "time until ready to receive requests," use a ready milestone in the application or a reproducible startup observability mechanism.

Example on **Windows PowerShell**:

~~~powershell
Measure-Command { java -cp . JniPhases baseline }
Measure-Command { java -cp . JniPhases load }
~~~

The PowerShell command also incurs measurement/shell operation overhead, so it is suitable for preliminary observation. Use the same measurement method and launcher for all samples; run repeatedly across **multiple fresh processes**, recording median/p95 and run order. Consider rotating the run order to reduce warm page-cache effects, and record machine state / CPU governor rather than treating a second fresh JVM run as a cold disk run. On macOS, `time` syntax differs from GNU `/usr/bin/time -f`; use `time java ...` or the OS timing tool.

**Do not mechanically subtract** "wall all – wall baseline" to deduce exact native time; two independent runs have noise, and `all` also adds warm-up, steady measurement, output, and many other steps. The `load_ns` and `first_call_ns` timers provide supplementary internal milestones, and do not turn subtraction into a dedicated result.

## 6. Correctly Interpreting Load, First Call, Warm-up, and Steady Metrics

### 6.1. Native library load

Run `load` across multiple fresh JVMs while keeping the `.so/.dylib/.dll` file unchanged. The `System.load` interval can include the OS dynamic loader, relocations, native initializers, `JNI_OnLoad`, and the JVM's native library management logic. If the first load is unusually slow, compare fresh JVM processes and OS cache state. Do not call `System.load` repeatedly inside a single JVM and treat that as 20 "cold loads": the library may already be tracked as loaded, and calling it again does not reproduce the initial load.

To confirm which libraries were actually loaded, use **JFR events** `jdk.NativeLibraryLoad` / `jdk.NativeLibraryUnload` when enabled. These events confirm load/unload; they do not directly report the isolated resolve time of each native method. JFR recording has overhead, so keep diagnostic sessions separate from final benchmark runs.

### 6.2. First JNI call/binding

The `first` mode calls `next(3)` exactly once after `System.load` has completed. With standard JNI mechanics, the JVM looks up the symbol on the first call to the `native` method; `first_call_us` includes the C call returning `4`. It can also include JNI adapter setup or CPU/cache activity. On JDK 24+ without granted access, native access warnings may be printed to stderr or the operation blocked depending on mode; **grant fixed permissions before measuring**, and do not use warnings as a latency benchmark.

If the library uses `RegisterNatives` in `JNI_OnLoad`, registration may have already occurred in the **load phase**. If the OS loader defers resolving some symbols/relocations, part of the work may also happen after `System.load`. Thus, the first-call number is implementation-specific "cold first use," not a universal definition of native linker time.

### 6.3. JIT warm-up

The first 12 batches in `all` run **before** the 10 batches used to compute the steady median. Initially, HotSpot may interpret Java code; after sufficient hotness, it can compile the Java caller/loop and generate/optimize the call path. Many other factors such as CPU caches and branch predictors also change during the initial phase. Per-batch warm-up times **do not necessarily decrease monotonically** due to asynchronous compilation, OS scheduling, GC, or deoptimization.

Consult HotSpot compiler output (run in a **separate diagnostic session**; do not use timings from a logging-enabled run as final benchmark results):

~~~bash
java -XX:+PrintCompilation -cp . JniPhases all
~~~

On JDK 24+, add `--enable-native-access=ALL-UNNAMED --illegal-native-access=deny`. The `-XX:+PrintCompilation` flag shows which methods are JIT-compiled; not seeing a line for `next` does **not** mean the native call did not run, because C functions are not bytecode that gets JIT-compiled. You can use `java -Xint ...` as a diagnostic check with JIT disabled, but `-Xint` changes the execution mode and must not be compared as steady-state results of default JIT mode.

A server program does not necessarily have a single "warm-up complete" point; rarely used branches or newly loaded classes arriving later can still warm up late. Record which code paths were warmed, invocation counts, and signs of stable compilation; if variance remains, increase warm-up or investigate rather than arbitrarily dropping outliers by intuition.

### 6.4. Steady state

The lesson's batch measurement code returns `ns_per_call_median`, computed as the median of 10 values of `elapsed_ns / 100000`. This is an easy-to-understand observation method, but it is **not** a microbenchmark with reliability equivalent to JMH: it measures few forks, uses a fixed warm-up that may be insufficient, is affected by timers/safepoints, and provides no confidence interval.

For JNI/FFM performance conclusions used to make design choices, use **OpenJDK Java Microbenchmark Harness (JMH)**. Prepare the native library **outside the timed section** (for example in `@Setup(Level.Trial)`), run independent fresh JVM forks (e.g., `@Fork(3)`), `@Warmup(...)` iterations, and `@Measurement(...)` iterations, returning results from `@Benchmark` or passing them to `Blackhole` so observability is not lost. For native access on JDK 24+, ensure JVM flags reach **JMH's forked processes**, not only the coordinator process.

An illustrative configuration for a steady-state benchmark snippet is:

~~~java
// JMH configuration snippet, NOT a standalone Java program;
// requires a JMH project and JMH dependencies/annotation processor.
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
~~~

A JMH **steady benchmark** does not replace a **cold startup/first-call** benchmark: default warm-up eliminates the initial cost we are trying to quantify. If the goal is startup/first-use, design an experiment that spawns a **new process/fork per sample**, or use an appropriate single-shot mode and interpret the result as inclusive startup/first-use time. Do not accidentally use steady-state results to claim the first call is fast.

## 7. Comparing JNI, FFM, and Crossing Cost

The example uses JNI so the boundaries are easy to see. With **FFM (JDK 22+)**, equivalent phases must be separated, though the naming does not necessarily match:

| JNI milestone | Closest corresponding FFM activity | What to measure |
| --- | --- | --- |
| `System.load(...)` | Loading library via `SymbolLookup.libraryLookup(...)` or related library-loading mechanism | Library load, arena/lookup lifecycle, and OS |
| First `native` method bind | Finding symbol via `SymbolLookup.find(...)`; creating downcall handle via `Linker.downcallHandle(...)` | Separate **lookup**, **method handle creation**, and **first call** |
| JNI Java→C call | `MethodHandle.invokeExact(...)` on the created downcall | Measure repeated calls; marshalling, layout, memory scope, and ABI cost |
| Passing strings/arrays via JNI | Passing `MemorySegment` or native buffer | Measure copy/allocate/pin, scope, and memory management, not just "call overhead" |

**Do not recreate `downcallHandle` on every steady-state benchmark iteration** unless the goal is handle-creation cost; keep `Linker`/lookup/handle set up before starting the timer to measure calls in isolation. If real work always allocates an arena or copies data per request, run an **additional** end-to-end benchmark that includes that cost. When comparing JNI and FFM, ensure both call the **same C function**, with the same data, error conditions, ABI/layout, and buffer lifecycle before claiming which is faster. Boundary crossing cost can be much smaller than the actual native algorithm or data copying.

A useful qualitative model:

`T_workload ≈ N_calls × T_boundary + T_native_work + T_marshal_or_copy + T_other`

This is only an **analytical guiding model**. Components interact through caches, JIT, and contention, so linear additivity is not guaranteed. For APIs performing tiny operations (like `next(long)`), per-call overhead can stand out; using a batch-oriented native API sometimes reduces `N_calls`. For long native operations (such as image processing), saving a few nanoseconds of crossing is unlikely to matter compared to the native algorithm, memory, and I/O. Any "batching" change must be re-measured end-to-end to check for newly introduced copy/data-transfer costs.

## 8. Designing Comparable Reports

An experiment report should be split into tables with **distinct objectives**:

| Report sample | Unit | Reasonable run count | Mandatory notes |
| --- | --- | --- | --- |
| Fresh JVM `baseline`, `load`, `first` | ms wall/process | Multiple fresh JVMs, state actual N | Same Java/OS/launcher, run order, cold/warm page cache |
| `System.load` in a fresh JVM | ms/load | Multiple fresh JVMs | Library, JNI_OnLoad, binary dependencies, source JDK |
| First `next(3)` after load | µs/first call | Multiple fresh JVMs | This is a first-use proxy, not pure binding |
| Warm-up batches | ns/call per batch | Multiple batches/forks | Batch order, compilation log when investigating |
| JMH steady calls | ns/op + error or ops/s | Multiple forks, warm-up, measurement | With/without allocation/copy; fork JVM flags |
| E2E request latency | p50/p95/p99, throughput | Near-production load | Identify lazy native load, bursts, GC, contention |

When stating a conclusion, write it in the form: "On JDK X, OS Y, native library compiled with Z, workload W, median of N forks ...; the difference lies in phase ...". Avoid writing "JNI is 2× faster than FFM" from a toy addition or a single run full of logs.

Hypothetical interpretation example, **not real measured results**: If a CLI runs a single task and exits, with 200 ms startup, 15 ms load, and 1 ms steady processing, reducing steady from 1 ms to 0.5 ms has little impact on total time. If a server lives for many hours and crosses the boundary hundreds of millions of times, optimizing crossing count or data size per call can be much more worthwhile. It is **usage volume** that determines which phase needs optimization.

### Supporting observational events, not benchmark replacements

- **JFR:** `jdk.NativeLibraryLoad` / `jdk.NativeLibraryUnload` (when enabled) to verify load/unload, and compilation/GC/safepoint events to explain variance if configured for collection.
- **HotSpot `-XX:+PrintCompilation`:** observe when Java code is compiled; use outside the final measurement run to reduce log overhead.
- **JVM class loading:** `-Xlog:class+load=info` helps locate late class-loading branches; it logs heavily, so enable only during investigation.
- **OS profilers:** CPU sampling, native stack traces, loader trace (if supported) to distinguish slowness in Java, JNI stubs, libc/OS loader, or C functions; profiling tools also have overhead.
- **JMH:** separates forks, warm-up, measurement, and reports variance for short benchmarks; for real request latency, application load testing/profiling is still required.

## 9. Common Mistakes and How to Fix Them

| Mistake | Why it skews results | How to fix |
| --- | --- | --- |
| Taking the time of one `java Main` command as "JNI call latency" | Includes JVM startup, I/O, loader, JIT, shutdown | Separate fresh-process benchmarks from in-process phase timers |
| Measuring from the start of `main` and calling it "JVM startup" | The JVM has already initialized before `main` runs | Use an out-of-process clock and/or a clear ready milestone |
| Concluding "first call – steady = binding time" | First call contains many other costs; the two samples differ in conditions | Treat first-call as a proxy; gather loader/symbol evidence if needed |
| Merging warm-up and steady into a single average | JIT/tiering and caches change over time | Save per-batch data, identify steady window, use JMH |
| Calling a few-nanosecond function and timing each call with `nanoTime()` | Clock and scheduling overhead is large relative to payload | Measure long batches, divide by operation count; better yet, use JMH |
| Discarding computation results | Compiler may eliminate computations or hoist unobservable parts | Use result/volatile sink or JMH `Blackhole` |
| Measuring `System.load` multiple times in one JVM and calling it cold load | Library is already loaded; dynamic loader/cache state changed | One initial load per fresh JVM/fork |
| Comparing JNI/FFM when one copies arrays and the other uses native segments | Different workloads/semantics | Same data, ABI, C function; report marshalling separately |
| Enabling `PrintCompilation` or heavy profiling during steady measurement | I/O and instrumentation skew timing | One diagnostic run, one lean benchmark run |
| Forgetting native access on JDK 24+ | Warnings or `IllegalCallerException` break or invalidate the benchmark | Configure `--enable-native-access` for the right module on **every fork** |
| Not pinning CPU, compiler flags, JDK, and machine thermals | DVFS, background load, and GC make results non-reproducible | Record environment, repeat many samples, compare distributions |

## 10. Pre-Optimization Evaluation Checklist

- [ ] Clearly defined "ready," "native library loaded," "first-use," and "steady" for the application under study.
- [ ] Measured startup from outside the JVM across multiple fresh processes; distinguished cold JVM from cold OS page cache.
- [ ] Placed separate timers around `System.load` and the first `native` call; did not label the first-call proxy as exact binding time.
- [ ] Verified that the native code path actually executes and properly handled `--enable-native-access` permissions on JDK 24+.
- [ ] Recorded warm-up batches, inspected JIT/tiering effects, and completely separated them from steady samples.
- [ ] Benchmarked steady state with JMH or an equivalent procedure with multiple forks, warm-up, measurement, and observable results.
- [ ] Covered realistic copy/allocate/marshalling, crossing counts, GC, safepoints, and end-to-end latency if the target is production.
- [ ] Recorded JDK/OS/CPU/compiler/native binary versions, JVM flags, and load level; compared distributions across multiple runs rather than a single number.
- [ ] Interpreted results according to the system's lifetime and JNI/FFM usage frequency, then re-measured after optimizing.

## References

- OpenJDK JEP 472 — native loading/linking restrictions from JDK 24: https://openjdk.org/jeps/472
- Oracle JNI Specification — Design Overview, *Resolving Native Method Names*: https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html
- Oracle JDK Migration Guide — native access, `jnativescan`, and JFR library events: https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html
- Oracle JDK Java launcher — HotSpot `-XX:+PrintCompilation`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- Oracle FFM `Linker` API (JDK 25) and downcall handles: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html
- OpenJDK Java Microbenchmark Harness (JMH): https://github.com/openjdk/jmh

**Core takeaway:** To optimize Java/native interoperability, you must first quantify **startup**, **loading/linking**, **JIT warm-up**, and **steady state** with measurements that have separate boundaries, units, and run conditions. A metric from one phase cannot represent the entire application lifecycle.