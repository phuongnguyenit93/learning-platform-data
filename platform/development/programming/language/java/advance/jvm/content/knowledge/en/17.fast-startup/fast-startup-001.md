# Separating Process Creation, Class Loading, Initialization, and Warm-up Costs

## 1. The Problem: “Java starts slowly” is not just a single number

When a Java application is launched, multiple stages can contribute to the time before it serves useful results: the operating system creating the process, the launcher/JVM initializing the runtime, class loading and linking, class initialization, framework/application bootstrap, connecting to dependencies, and then **JIT warm-up** to reach stable operating performance.

A statement like “2-second startup” is only useful when you answer **measured from where to where**. For example:

- **Process creation:** the time for the OS to start a Java execution process; involving scheduling, executable, environment, and dynamic libraries.
- **VM/launcher startup:** the Java launcher reads flags/module/classpath, and the JVM creates the runtime structures, memory areas, and threads needed before calling `main`.
- **Loading/linking:** finding bytecode, creating class representation, verification, preparation, and resolution according to runtime policy.
- **Class initialization:** running static field initializers and corresponding static initialization blocks, compiled into `<clinit>`.
- **Application initialization:** creating the DI container, scanning annotations, initializing serializers, opening pools, reading config, running migrations, and loading data.
- **First useful response/readiness:** the point when the first business flow or readiness endpoint actually works.
- **Warm-up:** profiling, tiered compilation C1/C2, method linking, lazy classes, JIT inlining/deoptimization, and gradually changing cache and GC states.
- **Steady state:** the period when the system has relatively stable throughput/latency/GC/CPU under a representative workload.

**Do not add everything together by taking the time of a `System.nanoTime()` statement placed inside `main`**. That Java snippet has already missed the entire OS process creation and the JVM startup portion before `main`, and the class initializer of the main class may also occur before the first statement of `main`.

> **Goal of this article:** break down measurable milestones, point out measurement boundaries, illustrate that **loading is different from initialization**, and design benchmarks that separate **cold-start / first response / warm-up / steady-state**, instead of lumping them into “how many ms does JVM launch take”.

## 2. Full Timeline: OS launch to peak/steady throughput

~~~text
external process milestones                              inside the JVM
t0: OS receives request to create process
       |
       v
[OS process startup + java launcher + JVM bootstrap]
       |
       v
[JVM initializes runtime, classloader system, GC/JIT runtime]
       |
       v
[Load/Link/Initialize main class] ─────> t_main: enter main()
       |
       v
[Application/bootstrap: config, DI, pools, external dependencies]
       |
       +──────────────> t_first: first useful result
       |
       +──────────────> t_ready: readiness meets criteria
       |
       v
[Realistic warm-up: JIT compilation, caches, lazy class init, GC]
       |
       v
t_steady: candidate steady-state windows
       |
       v
[Optional saturation / peak / long-soak measurements]
~~~

The diagram only shows **groups of work**. In real systems, they can overlap:

- Thread pools and background tasks can perform application init **in parallel**.
- JIT compilation can occur **during** bootstrap, before the first response.
- Lazy initialization can be deferred until **after readiness**, causing cold-path latency.
- CDS can shorten some class-loading work but does not eliminate all linker work, `<clinit>`, or application bootstrap.
- A service may report ready before it is completely “warm”; app latency can continue to improve after readiness.
- `t_first` and `t_ready` are not forced into an absolute order; it depends on the protocol and workload.
- A system with a dynamic request mix can change workload continuously and **not have a single global steady state**.

**Time windows must be labeled by purpose**, not lumped into “JVM start” and then blamed on GC/JIT.

## 3. Stage A — OS process creation and JVM startup costs

### 3.1. What happens before `main()`?

When a user invokes:

~~~bash
java -cp app.jar com.example.Main
~~~

The operating system and launcher perform the work of initializing the process and loading the program. Then HotSpot must prepare the VM runtime: parsing options, runtime libraries, the class loading system, memory management, thread/runtime structures, GC/JIT services, and preparing to execute the main class.

The specific details depend on the OS, Java vendor, JDK build, flags, filesystem, classpath/module path, and launcher design. Do not write an immutable “nanosecond sequence” for every JVM.

**Do not confuse `javac` with `java`:** `javac` compiles source into `.class` bytecode before the application runs. During a normal launch with `java Main`, the JVM **does not re-invoke `javac` for all files**. The JIT may compile **bytecode into native code** at runtime, which is an entirely different operation from `javac`.

### 3.2. Why does `System.nanoTime()` at the start of `main()` not measure process creation?

~~~java
public static void main(String[] args) {
    long start = System.nanoTime();
    // Measures from here, not from when the OS creates the process.
}
~~~

By the time the first code in `main` runs, **the VM has already been created enough to invoke main**, and the main class has already met its class initialization condition. Therefore, taking the time from `start` to `READY` only measures **a portion of application init**, and cannot measure OS spawn cost or the VM steps that occurred before `main`.

To measure end-to-end from the outside, use a parent process or load generator:

~~~bash
time java -cp . StartupPhasesDemo
~~~

PowerShell example (Windows):

~~~powershell
Measure-Command { java -cp . StartupPhasesDemo | Out-Null }
~~~

The `time` or `Measure-Command` command measures **the total time the process runs until exit**, including process launch, VM boot, work in `main`, shutdown, and wrapper overhead. This is **not purely startup latency** if the application continues working for a long time.

**For long-lived servers:** do not wait for process exit to take measurements; external tooling should measure from **the time of the spawn/start request** until receiving the **first useful response** or **readiness** signal according to defined criteria.

### 3.3. Can OS, launcher, and VM startup be separated completely?

A single Java tool is usually **not enough** to completely split the time before `main` into `OS spawn`, `dynamic loader`, `VM create`, and `classloader init` without overlap. You need to instrument at the appropriate level:

| What to measure | Appropriate observation |
| --- | --- |
| OS process start → process exit | Shell external timer |
| Process start → first useful result | Parent-process timestamp / external probe |
| Process start → ready | Orchestrator event + health/ready protocol, or external poll |
| OS spawn/exec and library loading | OS profiler, platform-appropriate process tracing |
| VM startup before `main` | Runtime-specific startup diagnostics/JFR + external measurement |
| Code inside `main` | `System.nanoTime()` milestones |
| Specific class loading | HotSpot Unified Logging, JFR if enabled |
| Specific class initialization | Class-init logs + markers inside `<clinit>` |
| JIT warm-up | Compilation events, throughput time windows, JFR |

Do not directly add durations from **different clocks, different milestones, or overlapping phases**. If `mainElapsedMs=20` and external `time java` measures 55 ms, the 35 ms difference **must not be labeled entirely as JVM bootstrap**: it also includes shell/OS process handling, output, shutdown, and non-equivalent measurement intervals.

## 4. Stage B — class loading, linking, and initialization are three distinct steps

The Java Language Specification (JLS 17, Chapter 12) separates:

- **Loading:** finding the binary form of a class/interface and using the appropriate class loader to create a representation of the type.
- **Linking:** consists of **verification**, **preparation**, and **resolution**, which can be performed eagerly or lazily within specification limits.
- **Initialization:** executing class-variable initializers and static initializer blocks, corresponding to `<clinit>` when generated by the compiler.

Do not assume that “as soon as a class is loaded, its static initializer has definitely run”. Do not equate **preparation** with **initialization**.

### 4.1. Loading: finding bytecode and creating the class representation

Classpath/module path, resource lookup, reading `.class` files, classloader delegation, verification dependencies, and built-in/custom class loaders can all affect cost. A framework scanning tens of thousands of classes or reading annotation metadata using various strategies can spend significant startup time, yet **not every metadata scan actually initializes all classes**.

Loading cost also relates to disk/page cache and archives. Opening a classpath JAR for the first time on a cold OS cache is very different from when the OS has already cached the file. That is why startup benchmarks need to control **cold/warm filesystem state** if it affects the real workload.

### 4.2. Linking: verify, prepare, resolve

| Step | Meaning |
| --- | --- |
| Verification | Verifies that bytecode/formats/type constraints meet JVM requirements |
| Preparation | Allocates/sets default values for `static` fields and certain metadata structures |
| Resolution | Converts symbolic references in the constant pool to appropriate runtime entities |

**Resolution can be lazy.** A class may already be loaded, verified, and prepared, yet some symbolic references are only resolved when the corresponding code path is actually used. Therefore, when a new route is called for the first time, additional linking work may appear **after startup/ready**.

JLS/JVMS mandates valid behavior and errors, but does not define a fixed millisecond cost for all classes.

### 4.3. Initialization: `<clinit>`

Static field initializers that are not compile-time constants, along with `static { ... }`, are typically arranged by the compiler into a special method `<clinit>`.

~~~java
final class Expensive {
    static int[] table = buildTable();
    static {
        System.out.println("Expensive initialized");
    }
}
~~~

This is an **illustrative class**, where `buildTable()` is defined by the application. When an active use requires initialization, the JVM runs `<clinit>` according to the rule of once per **class identity** in a JVM execution, with synchronization semantics defined by the specification.

**A class identity** consists of the binary name and the defining class loader; two different classloaders can create two distinct `Class` objects with separate initialization states. Do not state that “a static initializer only runs once across all processes/JVMs and classloaders”.

### 4.4. Key class initialization triggers

In many cases, class initialization is triggered before:

- Creating an instance with `new` of the class needing initialization.
- Accessing/writing a `static` field that is not a constant variable according to the JLS.
- Calling a `static` method.
- Reflection or method handles in operations with active-use semantics.
- Initializing the main class before the JVM calls `main()`.

A classic point:

~~~java
static final int CONST = 7; // constant variable if initialized with a constant expression
static int counter = 7;     // not a constant variable
~~~

Accessing a **constant variable** may not force the declaring class to be initialized, whereas accessing `counter` can trigger initialization. Do not use `static final` alone as the criterion: `static final int X = parse(...)` is not a compile-time constant.

`SomeType.class`, `ClassLoader.loadClass(name)`, or `Class.forName(name, false, loader)` **can obtain a class representation without forcing `<clinit>` to run immediately**. However, the default `Class.forName(name)` overload **normally requires initialization**.

## 5. Runnable Java 17 example: loading a class without initializing it

Create the file **`StartupPhasesDemo.java`**:

~~~java
public final class StartupPhasesDemo {
    static class InitProbe {
        static {
            System.out.println("probe=<clinit>");
        }
        static int value = 41;
    }

    static class LazyService {
        static {
            System.out.println("lazy=<clinit>");
        }
        static String work() {
            return "READY";
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("main=entered");
        Class<?> type = Class.forName(
                "StartupPhasesDemo$InitProbe",
                false,
                StartupPhasesDemo.class.getClassLoader());
        System.out.println("loaded=" + type.getSimpleName());
        System.out.println("aboutToInitialize=true");
        System.out.println("probeValue=" + InitProbe.value);
        System.out.println("serviceResult=" + LazyService.work());
        System.out.println("end=true");
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 StartupPhasesDemo.java
java StartupPhasesDemo
~~~

**Exact stdout compiled and run on JDK 24 with `--release 17`:**

~~~text
main=entered
loaded=InitProbe
aboutToInitialize=true
probe=<clinit>
probeValue=41
lazy=<clinit>
serviceResult=READY
end=true
~~~

### Why does the output follow this order?

1. Entering `main()` ⇒ the main class has already met the condition to be initialized (it has no static block printing a marker).
2. `Class.forName(binaryName, false, loader)` requests finding/loading/linking the corresponding type **but does not require initializing** it; therefore `probe=<clinit>` is not printed yet.
3. `type.getSimpleName()` can read metadata to return `InitProbe` without triggering the static block of `InitProbe` itself in this example.
4. The first read of `InitProbe.value` is an **active use** of a static nonconstant field, so the JVM initializes `InitProbe` first ⇒ prints `probe=<clinit>` then `probeValue=41`.
5. The first call to `LazyService.work()` also triggers initialization of `LazyService` ⇒ prints `lazy=<clinit>`, then the method returns `READY`.
6. The two classes may have been loaded/linked at different times; **the printed markers only reflect initialization**, not all prior costs.

**Do not use this snippet to conclude that every JVM will read the JAR at the moment `Class.forName` is called.** The class may already be loaded, the data may reside in a CDS archive/OS page cache, or the JVM may have resolved related items early. The example demonstrates **distinguishing two API behaviors**, not measuring disk cost.

### Different `Class.forName` overloads

~~~java
Class.forName("pkg.Type");                        // initializes per API contract
Class.forName("pkg.Type", false, someClassLoader); // does not require initialization
~~~

This is an **illustrative code snippet**; `pkg.Type` and `someClassLoader` must actually exist. Do not misuse the boolean overload and believe you have measured class loading in isolation.

## 6. Instrumenting class loading and class initialization with HotSpot logs

On HotSpot Java 17+, **Unified Logging** has tags for class load and class init. For example:

~~~bash
java '-Xlog:class+load=info,class+init=info' StartupPhasesDemo
~~~

This is a Bash syntax sample; on PowerShell, you can place the same option in single quotes. The specific JVM should be verified with:

~~~bash
java -Xlog:help
~~~

- `class+load=info` shows many classes being loaded and their corresponding source/loader, usually with timestamp decorations.
- `class+init=info` shows initialization events when the VM emits logs at the corresponding level.
- `class+resolve=debug` or other tags can help inspect resolution when supported by the JVM build, though log volume is large.
- Use `file=...:uptime,level,tags` to write logs and compare startup milestones by uptime.
- `PrintCompilation` helps observe JIT events, but **is not class loading**.

**Important note:** log markers are different from complete phase timers. A `class+load` line is usually just an **event** recording the class, and does not provide a complete “loading this class took N ms in total isolation”. The logger also has overhead, especially when there are thousands of events.

You can run:

~~~bash
java '-Xlog:class+load=info:file=classes.log:uptime,level,tags' StartupPhasesDemo
~~~

Then search for the binary names `StartupPhasesDemo$InitProbe` and `StartupPhasesDemo$LazyService`; on a JDK 24 verification run, the actual log recorded both classes. However, class logs **do not by themselves prove** initialization cost; you need init events or other markers.

### Using JFR in real investigations

Java Flight Recorder (JFR) has class load, class define, compilation, GC, CPU, and thread events depending on **recording settings, event thresholds, and JVM build**. For example:

~~~bash
java '-XX:StartFlightRecording=filename=startup.jfr,settings=profile' StartupPhasesDemo
~~~

Once the file exists:

~~~bash
jfr summary startup.jfr
jfr print --events jdk.ClassLoad,jdk.Compilation startup.jfr
~~~

A very short recording may not contain the desired events, or profile settings may not enable every event; **do not infer that not seeing `jdk.ClassLoad` means the JVM did not load classes**. When deep analysis is needed, enable the appropriate events in `.jfc`, control overhead, and observe for a sufficient duration.

## 7. Stage C — application/framework initialization

Separate JLS **class initialization** from **application bootstrap**. A Spring/Quarkus/microservice or CLI tool may itself perform:

- Parsing configuration, environment, YAML, certificate/key stores.
- Initializing the dependency injection context and object graphs.
- Scanning the classpath, finding annotations, loading configuration classes.
- Initializing logging, metrics registry, tracing/exporters.
- Starting thread pools and schedulers.
- Creating JDBC/HTTP connection pools, TLS handshakes.
- Running DB migrations, checking schemas, fetching secrets or config over the network.
- Preloading caches, loading dictionaries/models/templates/rules.
- Starting the server socket, registering routes and health probes.
- Performing readiness checks or waiting for dependencies to become available.

These tasks are **not automatically `<clinit>`**. They can run in constructors, methods, container lifecycle hooks, background tasks, or startup scripts.

### Why is clear separation necessary?

Two applications using the exact same JDK and a similar set of libraries can have very different “startup” times because of **bootstrap logic**. If 1.2 seconds is spent in a DB connection timeout, changing the GC collector or increasing JIT compiler threads is unlikely to solve the root cause.

### Instrumenting semantic milestones

You can place application-defined markers:

~~~text
process_spawn_requested
main_entered
config_loaded
di_context_created
db_pool_ready
http_listener_bound
first_successful_business_request
readiness_accepted
~~~

Then measure with a monotonic clock **between milestones emitted from the same process**. For milestones belonging to external processes, you must correlate via wall timestamps/protocol spans with proper clock handling.

To make logs useful:

1. Record a stable phase name and a separate run ID to avoid mixing multiple processes.
2. Record both duration and clock source, not just `"finished"`.
3. Limit heavy instrumentation during hot startup.
4. Separate the synchronous critical path from asynchronous work.
5. Mark when readiness returns **before** background tasks complete.
6. Log failures/timeouts and retries, not only successful startups.

**Do not sum the durations of sub-tasks running in parallel and compare that to end-to-end elapsed time**: total CPU/task durations can be greater than the wall-clock critical path.

## 8. Stage D — JIT warm-up and steady state

HotSpot typically starts with the interpreter and uses tiered compilation (C1/C2, depending on VM flags) when profiling shows a piece of code is hot enough. Code regions that have not been called may not be JIT-compiled yet. The JVM also has OSR for long loops and the ability to deoptimize/recompile if profiling assumptions change.

Therefore, `main()` or the first request completing **does not mean JIT warm-up is complete**. An app with 20 routes may warm up 2 popular routes first; the remaining 18 routes will still hit cold-path loading/JIT when traffic touches them for the first time.

### Effects beyond JIT

Besides JIT, throughput/latency can change due to:

- Lazy class initialization/late linking.
- Pool/cache warm state.
- GC allocation rate, heap occupancy, and promotion.
- OS filesystem page cache.
- Database page cache, prepared statements, query plans.
- TLS handshake/session resumption.
- CPU frequency scaling, scheduler, resource contention.
- JIT background compiler threads competing for CPU quota with request threads.

**A second batch being faster than the first batch does not by itself prove the code has been C2-compiled**, because countless other effects exist. To know JIT activity, use `-XX:+PrintCompilation`, JFR compilation events, and, if you truly need to verify native optimization, compiler IR/assembly tools appropriate for the build.

### “Steady state” is an operational concept, not a state guaranteed by the JVM

A measurement window can be called a **candidate steady state** when:

1. Same offered load and representative request mix.
2. Throughput, p99, CPU/GC, and heap live set no longer show a clear transient trend.
3. No compiler/classloading bursts large enough to skew results.
4. External dependencies/caches are stable.
5. Repeated windows give relatively consistent results with enough samples.

There is no public `Jvm.isSteadyState()` API guaranteeing that a program has reached “peak”. Therefore, warm-up policy needs to be determined based on measured data, rather than picking an arbitrary number of seconds for every application.

## 9. Runnable Java 17 example: measuring class-loading markers, init markers, and warm-up batches

Create the file **`WarmupPhasesDemo.java`**:

~~~java
import java.util.Locale;

public final class WarmupPhasesDemo {
    static class Kernel {
        static final int[] values = new int[1024];

        static {
            for (int i = 0; i < values.length; i++) {
                values[i] = i * 7 + 1;
            }
            System.out.println("kernel=<clinit>");
        }

        static long compute(int seed) {
            long sum = seed;
            for (int value : values) {
                sum += value ^ seed;
            }
            return sum;
        }
    }

    public static void main(String[] args) throws Exception {
        long enteredMain = System.nanoTime();
        System.out.println("main=entered");

        long beforeLoad = System.nanoTime();
        Class.forName("WarmupPhasesDemo$Kernel", false,
                WarmupPhasesDemo.class.getClassLoader());
        long afterLoad = System.nanoTime();
        System.out.println("loadWithoutInit=done");

        long beforeInit = System.nanoTime();
        int size = Kernel.values.length;
        long afterInit = System.nanoTime();
        System.out.println("kernelSize=" + size);

        long checksum = 0;
        for (int batch = 0; batch < 3; batch++) {
            long beforeBatch = System.nanoTime();
            for (int i = 0; i < 3000; i++) {
                checksum += Kernel.compute(batch * 3000 + i);
            }
            long elapsed = System.nanoTime() - beforeBatch;
            System.out.printf(Locale.ROOT,
                    "batch%dMs=%.3f%n", batch, elapsed / 1_000_000.0);
        }
        System.out.println("checksum=" + checksum);
        System.out.printf(Locale.ROOT, "loadingMs=%.3f%n",
                (afterLoad - beforeLoad) / 1_000_000.0);
        System.out.printf(Locale.ROOT, "initMs=%.3f%n",
                (afterInit - beforeInit) / 1_000_000.0);
        System.out.printf(Locale.ROOT, "mainElapsedMs=%.3f%n",
                (System.nanoTime() - enteredMain) / 1_000_000.0);
    }
}
~~~

Run:

~~~bash
javac --release 17 WarmupPhasesDemo.java
java WarmupPhasesDemo
~~~

**Invariant lines verified on JDK 24 targeting Java 17, in order of appearance:**

~~~text
main=entered
loadWithoutInit=done
kernel=<clinit>
kernelSize=1024
~~~

Next, the program prints:

~~~text
batch0Ms=<environment time>
batch1Ms=<environment time>
batch2Ms=<environment time>
checksum=44137339276
loadingMs=<environment time>
initMs=<environment time>
mainElapsedMs=<environment time>
~~~

The `<environment time>` placeholder describes numbers that are **not fixed**; it is not literal stdout. In a test run, `batch0Ms` was larger than `batch1Ms` and `batch2Ms`, but this result **must not be used as proof that every machine will warm up in the exact same ratio**.

### Explaining the milestones

- `enteredMain` only measures from the moment execution is already inside main.
- `Class.forName(..., false, ...)` only requests the class to be loaded/linked per the API contract; it does not trigger `<clinit>` of `Kernel`.
- `Kernel.values.length` is an active use of a nonconstant static array field: the JVM initializes `Kernel` before reading the value, so the `kernel=<clinit>` marker appears before `kernelSize=1024`.
- `initMs` measures the overhead around static field access, running `<clinit>`, and related runtime/JIT costs, **not “the time of all static initialization in the app”**.
- `loadingMs` is the elapsed time of **a single Class.forName call in a single run**; besides class loader work, it includes call overhead, logging if enabled, and OS/JIT effects. It is not the entire class-loading cost of the process.
- `batch0Ms`, `batch1Ms`, `batch2Ms` are computation measurement intervals; they do not assert that the third batch has reached steady state.
- `checksum` keeps the result observable to reduce the risk of dead-code elimination; it still does not replace a proper benchmark.
- `mainElapsedMs` measures the entire section after `enteredMain`, **including** the measured sub-intervals and output/formatting. **Do not add `mainElapsedMs + initMs + loadingMs`** because that would double-count.

**Reading the code intentionally:** the program inserts `System.out.println` between milestones so learners can clearly see the order. In a serious microbenchmark, printing can affect timings; measurement should be separated from output when timing individual operations.

## 10. Observing JIT: warm-up is different from class init

In Java 17 HotSpot, you can run:

~~~bash
java -XX:+PrintCompilation WarmupPhasesDemo
~~~

Diagnostics may record the `WarmupPhasesDemo$Kernel::compute` method being compiled at one or more tiers. You can run a comparison:

~~~bash
java -Xint WarmupPhasesDemo
~~~

`-Xint` runs interpreter-only: useful for understanding the role of JIT, but **it does not simulate the startup of a JVM with default JIT**. Cold code on the default JVM is still eligible to be JIT-compiled once hot enough.

Do not treat every `PrintCompilation` line as a promise that compilation is finished for all hot paths. HotSpot has C1/C2, OSR, deoptimization, inlining, and tier policies; compilation signals need to be analyzed with the current build.

### Batch numbers cannot replace a load test

An app processing 9,000 calls to `Kernel.compute` in 3 batches does not measure:

- Process spawn → first useful response.
- Readiness of DB, TLS, HTTP connections.
- Request queueing and p99/p99.9 at a fixed arrival rate.
- Dynamic route/class loading and memory retention over time.
- Full/concurrent GC behavior on a long workload.
- CPU quota/backpressure of the service in a container.

Therefore, use the example for **conceptual separation**, not for ranking JDKs or frameworks.

## 11. Distinguishing cold start and lazy first hit

This is a very practical trap in frameworks:

~~~text
Process starts
       |
       +-- load Main, init DI context, bind HTTP port
       |
       +-- /health GET 200 ⇒ readiness OK
       |
       +-- first /report request
             +-- class ReportRenderer is loaded
             +-- static fields/serializer registry initialize
             +-- template compile, DB query plan/cache load
             +-- JIT/profile for hot route begins
             +-- FIRST_HIT_LATENCY is high
       |
       +-- subsequent /report requests ⇒ may be faster
~~~

A service can reach **readiness** early yet still fail to meet the **first-hit latency SLO** for a critical route. Options include:

1. Add warm-up using a **meaningful request mix**.
2. Preload truly important classes/static data.
3. Defer rarely used work to lazy init to **reduce the startup critical path**, accepting a cold first hit.
4. Separate “ready to accept basic traffic” and “ready for critical workload” if needed.
5. Enable tracing per request route to find class/init/JIT/DB costs.

**Preloading every class is not always better.** Eager init can increase startup duration, heap footprint, and CPU bursts; lazy init, on the other hand, makes first-hit latency high. This is a trade-off based on SLO/lifecycle, not a single optimization for all systems.

## 12. CDS and AppCDS: optimizing part of class loading

**Class Data Sharing (CDS)** allows the JVM to use an archive containing metadata of prepared/shared classes, reducing part of startup work and memory footprint. Oracle JDK 17 has a **default CDS archive** with selected core classes; **Application CDS (AppCDS)** can extend coverage to classes from the application.

Potential impact:

- Part of the metadata can be memory-mapped from the archive.
- Multiple JVMs on the same host can share the corresponding read-only pages.
- Reduces some bytecode parsing/loading/preparation-related work.
- Most beneficial when class loading is a significant portion of startup, depending on app/JDK/config.

**CDS does not automatically run all application `<clinit>`s, does not replace business bootstrap, does not pre-open DB connections, and does not automatically warm up C2-compiled code for every route.** Do not call CDS a “complete warm-up solution”.

### Enabling/disabling CDS in controlled experiments

Example on a suitable HotSpot Oracle/OpenJDK 17:

~~~bash
java -Xshare:auto StartupPhasesDemo
java -Xshare:off StartupPhasesDemo
~~~

`-Xshare:auto` lets the JVM use the archive when appropriate; `-Xshare:off` disables CDS for diagnostic comparison. Multiple repetitions are needed, with the same JDK/classpath/filesystem cache, and a fresh process per run. Do not conclude that the difference from a single run is purely the effect of CDS because of OS cache and scheduler noise.

`-Xshare:on` forces archive usage and can cause the JVM to fail if the archive is unsuitable; Oracle documentation warns **not to use it as a default production option** in environments where archive/config compatibility is uncertain.

AppCDS can be created from a class list or a **dynamic archive** (HotSpot flag `-XX:ArchiveClassesAtExit=...`) matching the JVM version. Archive and deployment constraints must be followed; do not push an experimental archive path to production without checking compatibility/version.

## 13. HotSpot flags commonly useful for startup analysis

| Option/tool | Purpose | Limitations |
| --- | --- | --- |
| `-Xlog:class+load=info` | Log class load events | Not an independent phase duration |
| `-Xlog:class+init=info` | View class init events when supported | Logger has overhead, does not automatically equal total `<clinit>` elapsed |
| `-XX:+PrintCompilation` | Know which methods JIT compiles, tiers/timing | Does not measure OS spawn/class loading |
| `-Xint` | Run interpreter-only to compare mechanisms | Not a default cold JVM baseline |
| `-Xshare:auto/off` | Compare CDS effect | Must use same JDK, process forks, and caching |
| `-Xlog:gc=info` | Log GC activity, pauses | Does not measure full startup |
| `jfr`, JFR settings | Correlate CPU, class, compiler, and allocation events | Must enable right events, has overhead |
| `jcmd PID VM.flags` | View JVM flags of a process | Requires real PID, appropriate permissions |
| `jcmd PID VM.command_line` | Verify launch command | Process may have already exited during short startup measurements |

### Logging affects results

An app's very short startup can be dominated by log I/O if `class+load=trace` is enabled and prints tens of thousands of classes. Therefore, you should have:

- **Diagnostic runs** with logging enabled to identify causes.
- **Benchmark runs** using production-like logging config or identical config across candidates.
- Explicitly state logger configuration in reports; avoid comparing run A with `trace` against run B with `off`.
- If `file=...` is needed, choose separate file names, rotation, permissions, and do not mix processes.
- When exporting JFR/dumps/logs, note that classnames/paths/credentials can be sensitive data.

## 14. A single JVM process spawn measurement is not enough to conclude

Outline of a short measurement procedure:

1. Invoke a **fresh Java process** `N` times for each candidate, measuring each from the outside.
2. Randomize candidate order (A/B/B/A) to reduce bias from OS filesystem cache and thermal/CPU changes.
3. Record `java -version`, vendor/build, OS, CPU quota, heap flags, CDS settings, classpath, and working directory.
4. Separate **cold filesystem/cache** and **warm OS cache** into two scenarios if important; do not assume every new JVM has a cold OS cache.
5. Report median/p95/p99 startup, min/max, and variability, not just the fastest run.
6. For servers, use external first-response/readiness instrumentation instead of `time java` waiting for process exit.
7. Test startup failures/timeouts and retries, not only successful instances.
8. Collect class-load/JIT/JFR/OS metrics in a few diagnostic runs to explain each phase.
9. Distinguish main-internal elapsed time from process-external elapsed time; do not sum overlapping durations.
10. Continue testing after startup: first-hit latency and steady-state throughput, because an optimization may shift cost elsewhere.

### OS caches and working set

If opening a JAR the first time takes long due to filesystem page faults but the second time is faster thanks to page cache, **do not immediately attribute the entire delta to JIT**. A new JVM process does not have a “warm” native code cache from a previous process in the application sense, but the OS file cache and external DB cache can be reused.

If running in a container, include image start/cgroup scheduling, CPU throttling, memory pressure, and network startup in the context. `-XX:ActiveProcessorCount` **does not grant CPU quota by itself**; it only affects JVM ergonomics, while the OS/container enforces resource limits.

## 15. Cold vs warm, startup vs throughput: which KPI to choose?

| Workload | Startup KPI | Post-startup KPI | What to emphasize |
| --- | --- | --- | --- |
| Sub-second CLI | Full process elapsed / time-to-result | Less meaningful if process exits early | VM boot, classloading, init matter |
| Multi-minute batch job | Time-to-first-batch + total job time | Throughput when batch is steady | Startup may be small relative to total job |
| Long-running API server | Ready time, first useful request | p99/p99.9, throughput, GC, memory | Lazy routes and JIT warm-up |
| Serverless/short-lived function | Cold invocation latency | Warm invocation latency | Startup repeats many times |
| Autoscaling pod | Process/deploy → ready; traffic ramp | SLO-constrained throughput | Cold pods need ramp/backpressure |
| Desktop/interactive GUI | First interactive render | UI responsiveness | Do not treat process-created as ready |

**A “fast startup” option is not automatically a “high throughput” option.** For example, reducing initial compilation work may improve first response but hurt peak throughput; eager initialization may delay readiness but reduce first-hit spikes. This is a trade-off that must be measured **against the actual lifecycle and SLO**.

### Total work over a short lifecycle

For a function living 2 seconds, reducing startup by 0.5 seconds can be very valuable even if steady-state CPU throughput is unchanged. For a process living 24 hours, 0.5 seconds of startup may be less valuable if it increases CPU by 10% throughout the day.

**Do not apply a single goal of “optimize startup at all costs” to both.**

## 16. Common mistakes to avoid

1. **“Putting `nanoTime()` at the start of main measures OS spawn.”** False; process/JVM is already initialized enough to invoke main.
2. **“Once a class is loaded, `<clinit>` runs immediately.”** False; load/link/init are separate.
3. **“Preparation is running the static initializer.”** False; preparation differs from initialization.
4. **“All symbolic references are resolved at startup.”** False; resolution can be lazy.
5. **“`Class.forName(..., false, ...)` forces static blocks to run.”** False.
6. **“Every `static final` is a compile-time constant.”** False; only constant variables per the JLS.
7. **“The time of `Class.forName` equals the entire JVM classloading cost.”** False.
8. **“With `JIT`, all classes must be compiled before ready.”** False.
9. **“A fast second batch proves C2 compiled.”** Insufficient evidence.
10. **“CDS means there is no more class initialization.”** False.
11. **“A CDS archive warms up DB pools/JIT/HTTP routes.”** False.
12. **“Main printing READY means the server meets its SLO.”** No, unless the marker matches the exact contract.
13. **“First successful response = steady state.”** False.
14. **“A new process always has a cold filesystem cache.”** False.
15. **“The sum of subphase durations equals wall time if tasks run in parallel.”** False, may double-count.
16. **“`-Xint` simulates a cold JIT app identically.”** False.
17. **“GC log off means no GC occurs.”** False, just no corresponding log.
18. **“JFR profile always enables all ClassLoad/Compilation events.”** False.
19. **“Fastest run is more worth reporting than median or p99.”** Insufficient basis.
20. **“Lumping startup, warm-up, and long-run throughput into one ms number.”** Measurement-meaningless.
21. **“A lazy init optimization has no cost.”** False; cost may shift to the first request.
22. **“Thanks to JIT, OS process creation becomes cheaper.”** False; two different cost layers.
23. **“Comparing Java 17 and Java 24 without noting versions yields a general conclusion.”** False, the JVM has changed.
24. **“As soon as readiness succeeds, every route is class-initialized and compiled.”** False.

## 17. Checklist for investigating a slow-starting Java application

- [ ] Define **external start** and **response/readiness end** before measuring.
- [ ] Check command line, Java vendor/build, OS, classpath, JAR size, CDS state.
- [ ] Distinguish *process start → main* from *main → app ready* and *ready → warm throughput*.
- [ ] Run 5–10 independent runs, fresh processes, measure median/variance, and record filesystem cache state.
- [ ] Enable `class+load` and `class+init` in diagnostic runs to find lazy/eager classes.
- [ ] For Java `<clinit>`, identify active-use triggers, do not equate with loading.
- [ ] Instrument phase durations of config/DI/DB/TLS/cache/HTTP bootstrap.
- [ ] If there is background init, measure the critical path and real readiness dependencies.
- [ ] Check JIT events if warm-up throughput/latency changes.
- [ ] Check GC/class loading/OS CPU and page faults; do not blame everything on JIT.
- [ ] Test CDS/AppCDS on the same JDK/build; do not confuse with class init.
- [ ] For servers, measure first business request, first-hit per route, and p99 after ready.
- [ ] Measure plateau using windows, not just a single fast batch.
- [ ] For containers, record CPU quota, memory limit, I/O/network startup.
- [ ] Distinguish eliminated cost from cost **deferred to the first request**.
- [ ] Do not break correctness: static init side effects, connection readiness, and data consistency must remain valid.
- [ ] Record failures/timeouts and cases where the process dies during bootstrap.
- [ ] Conclude from multiple data sources, not just a single log timestamp.

## 18. Self-check: 18 questions and short answers

1. Does placing a timer at the first statement of `main()` measure OS process creation? **No**.
2. Can loading, linking, and initialization happen at different times? **Yes**.
3. Once a classloader finishes loading a class, has `<clinit>` necessarily run yet? **Not yet**.
4. Does `Class.forName(name, false, loader)` require initializing the class? **No**.
5. Can reading a static nonconstant field trigger initialization? **Yes**.
6. In the `StartupPhasesDemo` example, does the `probe=<clinit>` marker print before or after `loaded=InitProbe`? **After**.
7. Is JLS preparation running `static {}`? **No**.
8. Is resolution always eager before main? **No**, it can be lazy.
9. Does app readiness equal time-to-C2-peak? **No**.
10. Can a static init trigger happen on the first request? **Yes**, if that class is first used on the route.
11. Does a CDN/CDS archive pre-establish TLS/DB sessions for every app? **No**.
12. What can the default CDS archive in JDK 17 save? **Some class loading/metadata work and memory sharing**, depending on the environment.
13. Does `time java Program` running until exit measure only JVM bootstrap? **No**, it also includes main work and shutdown.
14. Does a new process mean the OS page cache is definitely cold? **No**.
15. Does a faster second batch prove JIT level 4? **No**.
16. If the first HTTP route is slow even though `/health` reports ready, what should you inspect? **Lazy class/init, pools, serializers, network, JIT, and caches on that route**.
17. Is running `java -Xint` a standard simulation of cold JIT startup? **No**.
18. For a 300 ms CLI, which part is usually worth looking at first? **Full process-to-result time**, not just hot-path throughput.

## 19. Authoritative Java 17 sources

- **JLS 17, Chapter 12 — Execution**, loading/linking/initialization and VM startup: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- **JVMS 17, Chapter 5 — Loading, Linking and Initializing**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- **`Class.forName` Java SE 17**, initialize boolean overload: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)
- **`ClassLoader` Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Oracle JDK 17 java command** (`-Xlog`, `-Xint`, `-XX:+PrintCompilation`, CDS flags): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle JDK 17 Class Data Sharing**, default CDS archive and AppCDS: https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html
- **Oracle JDK 17 `jcmd`**, VM flags, JFR diagnostic tools: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **Oracle JDK 17 `jfr` command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- **OpenJDK JMH project**, avoiding bias when measuring Java micro-workloads: https://openjdk.org/projects/code-tools/jmh/

**Technical conclusion:** The process of bringing a Java application to a useful state should be viewed as **multiple costs with distinct measurement boundaries**: OS process creation → launcher/JVM boot → class load/link → class init → application bootstrap/first response/readiness → JIT/cache/GC warm-up → steady state. A timer inside `main` misses every step before `main`; a loaded class **does not mean it is initialized**; CDS can reduce part of class-loading cost **without pre-running `<clinit>` or reaching JIT peak**. Combine **external milestones, class/JIT/GC logs, JFR, and application tracing** on the same workload/JDK/resources, measure across multiple runs, and report cold start, first-hit latency, readiness, warm-up ramp, and steady-state SLO separately.
