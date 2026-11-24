# Observing Memory Allocation, Class Loading, and GC During Spring Boot Startup

## 1. Learning Objectives and Questions to Answer

A Spring Boot application can take several seconds to start due to a cascade of work: the JVM prepares the runtime, loads classes, scans the classpath, parses annotation metadata, creates bean definitions, instantiates singletons, runs auto-configuration, builds proxies, opens connections, warms caches, and executes runners. During that time, the JVM may allocate many objects, load thousands of classes, and perform several Garbage Collections (GC).

Three **measurement groups** must be distinguished:

- **Memory allocation:** how many new objects/bytes are created over time, from which classes and stack traces? Do objects live long or quickly become garbage?
- **Class loading:** how many classes have been loaded into the JVM, at what time, and through which class loader/source? Class loading differs from class initialization and differs from bean creation.
- **Garbage Collection:** were there any collection/stop-the-world pauses during startup? How long did they take and how was memory reclaimed?

They can affect one another, yet are not synonymous. A small heap snapshot after Ready can be accompanied by a huge volume of short-lived object allocations. Thousands of loaded classes do not prove there are thousands of beans. Seeing GC events does not prove GC is the primary cause of slow startup.

```text
JVM startup
     |
     +-- Load/verify/link classes -----+
     |                                 |
     +-- Spring scan/bind/create beans +--> Allocation --> Heap occupancy
     |                                 |                       |
     +-- Reflection/proxies ----------+                    GC when needed
     |
     +-- Disk I/O / network / CPU / locks / JIT
                    |
               Startup wall time
```

Formulate **testable hypotheses**: "Bean X creates many temporary arrays during initialization", "the classpath pulls unnecessary libraries into the JVM", or "a large GC pause sits on the critical path to Ready". Each hypothesis requires different data.

This lesson uses **Java 17+ and Spring Boot 3.3.x** with a runnable Gradle project and JDK tools: MemoryMXBean, ClassLoadingMXBean, GarbageCollectorMXBean, Unified JVM Logging, Java Flight Recorder (JFR), `jcmd`, and `jstat`.

## 2. First Define the Boundaries of "Startup"

There are several different intervals:

| Measurement milestone | Start | End | Notes |
|---|---|---|---|
| Process startup from OS view | OS starts the Java process | App reaches serving state | Includes time before `main` |
| Java main → Spring Boot Ready | Start of `main` | `SpringApplication.run(args)` returns | Past refresh, runners, and Ready event if successful |
| Spring Started | Bootstrap process | `ApplicationStartedEvent` | Before runners, distinct from Ready |
| Ready | After runners | `ApplicationReadyEvent`/readiness update | Background work may still be running |
| First-use latency | First invocation of a feature | Functional result | May include lazy beans, caches, and JIT warmup |

`System.nanoTime()` inside `main` only measures from when that Java code runs; it does not measure all of the JVM process setup before `main`. `time java -jar app.jar` measures until **process exit**, not just Ready if a Web app does not exit on its own. Boot's log "Started ... in ... seconds" is a different milestone from process lifetime or the first request.

In the analysis below, the main boundary for the demo is **from the measurement start in `main` until `SpringApplication.run(args)` returns**. State this boundary explicitly whenever comparing results.

## 3. Reading Memory Metrics Correctly

### 3.1. Heap used, committed, max, and allocated Differ

`MemoryMXBean.getHeapMemoryUsage()` returns a `MemoryUsage` containing:

- `used`: heap bytes currently used at snapshot time.
- `committed`: heap bytes the JVM has committed and guaranteed for use.
- `max`: maximum heap limit reported by the JVM; may be `-1` if undefined.
- `init`: initial heap value reported by the JVM.

These variables are **not** total bytes of Java objects allocated since process start. Theoretical example:

```text
t0: heap used 24 MiB
t1: startup allocates 250 MiB total objects, many short-lived
t2: GC reclaims most temporary objects
t3: heap used 38 MiB
```

`38 - 24 = 14 MiB` is the difference in heap occupancy between two snapshots, **not** the `250 MiB` total allocated. To find allocation hotspots, you need JFR/a profiler or an appropriate allocated-bytes API, not just subtracting two `getUsed()` values.

### 3.2. Live Set, Churn, and Allocation Rate

- **Live objects:** objects still reachable at the moment under consideration.
- **Allocation rate:** volume of new data/objects allocated per unit of time.
- **Allocation churn:** many objects rapidly ending their lifetime, potentially creating GC pressure.
- **Retained heap:** memory kept alive by the reference graph, not equal to total allocation.

For instance, classpath scanning creates many temporary metadata structures and then retains only a small amount for runtime use. Final heap is small, yet initial allocations still consume CPU and can trigger GC.

### 3.3. Heap Is Not Total Process Memory

A HotSpot process also consumes:

```text
Java heap
Metaspace / class metadata
JIT code cache
Thread stacks
GC/compiler native structures
Direct/native buffers
Mapped libraries / other native allocations
```

**Metaspace** stores class metadata primarily outside the Java heap. When very many classes are loaded, looking only at `heap used` is not enough to understand total process memory. **RSS** from the OS differs from `heap committed`; RSS relates to resident pages. NMT can report JVM reserved/committed memory, yet is not a complete RSS measurement and does not cover all native allocations from every non-JVM library.

### 3.4. Common Units

`1 KiB = 1024 bytes`; `1 MiB = 1,048,576 bytes`. Do not mix or add "MB", "MiB", or byte counts without normalizing units. Record raw data in bytes and convert when reporting.

## 4. Understanding Class Loading Before Inspecting Class Logs

A class typically involves several phases:

1. **Loading:** the class loader locates and defines the class from bytecode.
2. **Linking:** verification, preparation, and resolution according to JVM rules.
3. **Initialization:** runs the static initializer when active-use conditions trigger.
4. **JIT compilation:** the JVM optimizes executed code; not the same event as class loading.
5. **Bean instantiation:** Spring calls a constructor/factory method to create a bean object, an application-level mechanism.

A loaded class may **never become a Spring bean**. A bean definition may be registered while a lazy bean is not yet instantiated. Generated proxy classes can appear when AOP is used; loaded class counts also include JDK, logging, serializers, and auto-configurations.

`ClassLoadingMXBean` provides three key measurements:

| API | Meaning |
|---|---|
| `getLoadedClassCount()` | Classes currently loaded in the JVM at measurement time |
| `getTotalLoadedClassCount()` | Total classes ever loaded since JVM start, including those later unloaded |
| `getUnloadedClassCount()` | Total classes unloaded since JVM start |

These counts are **at the JVM level**, not the `ApplicationContext` level. Do not use `getTotalLoadedClassCount()` as the count of created beans. A class can be loaded for bytecode verification or a first-time code path; do not blame every class on component scanning.

## 5. Reading GC with Proper Semantics

GC reclaims objects that are no longer needed. In Java 17 HotSpot, G1 is often the default collector on eligible server-class configurations, though the actual collector depends on runtime, flags, and environment. **Check which collector the JVM is running** rather than assuming.

### 5.1. Three Groups of Questions

1. **Events:** did any GC occur during startup? Were there young/full/concurrent activities?
2. **Time:** what was the total stop-the-world pause on the critical path? When did the largest pause occur?
3. **Memory:** before/after collection, how did heap occupancy/capacity change?

Some collectors have concurrent phases. Summing `GarbageCollectorMXBean.getCollectionTime()` across multiple collectors **does not necessarily equal the total time the application was paused for GC**. For exact pause timestamps, use GC unified logs or JFR.

### 5.2. Zero GC Can Still Mean Heavy Allocation

If startup finishes before the JVM needs GC, `GC count delta` can be 0. That does not mean 0 objects were allocated. In that case, look for slow startup in classpath scanning, bean initialization, I/O, parsing, JIT/CPU, or lock contention.

### 5.3. Metrics from GarbageCollectorMXBean

`ManagementFactory.getGarbageCollectorMXBeans()` returns multiple collector beans. `getCollectionCount()` and `getCollectionTime()` can return `-1` when a metric is unsupported. If summing values, skip `-1` and state clearly that these are figures **reported by JVM MXBeans**, not a universal definition of pause time.

## 6. Choosing Tools by Question

| What you want to know | Tool | Strengths | Limitations |
|---|---|---|---|
| Heap used/committed/max | `MemoryMXBean` | Lightweight, easy Java integration | Snapshot is not total allocations |
| Loaded/unloaded classes | `ClassLoadingMXBean`/`jstat -class` | Shows JVM-level trends | Does not show stack trace per class |
| GC count/time | `GarbageCollectorMXBean` | Fast, no profiler needed | Collector-dependent semantics |
| GC pauses at exact uptime | `-Xlog:gc*` | Includes timestamp/heap/GC ID | Does not measure all allocations |
| Class loads over time | `-Xlog:class+load=info` | Shows class name and source | Large logs, has overhead |
| Allocation stacks and timeline | JFR/JMC | Sampling analysis, class/GC/CPU | Must enable events and understand sampling |
| Process heap/class snapshot | `jcmd` | Live attach by PID | Process must still be alive/attachable |
| Periodic JVM statistics sampling | `jstat` | Periodic polling | Can miss short spikes |
| Native memory categories | NMT + `jcmd VM.native_memory` | Reserved/committed by JVM | Must enable at launch, not RSS |
| Spring startup steps | `ApplicationStartup` | Shows what Spring step is running | Does not replace JFR allocations/GC |

**Approach:** establish a baseline first; turn on GC/class/JFR/NMT only when you have a hypothesis. Enabling every tool on the first run can distort latency.

## 7. Complete Project: Spring Boot 3.3.5 + Java 17

A non-web example requiring no HTTP server or database. A bean allocates arrays to create observable allocation; `main` captures JVM snapshots before and after `SpringApplication.run`. Includes `--probe.pause-seconds=30` to keep the JVM alive briefly for `jcmd`/`jstat`.

### 7.1. Structure

```text
startup-memory-observer/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/startupmemory/
    ├── StartupMemoryObserverApplication.java
    └── StartupSampleCache.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'startup-memory-observer'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

To use `./gradlew`, you need a Gradle Wrapper generated by Spring Initializr or a compatible Gradle installation. `build.gradle` does not generate the Wrapper by itself.

### 7.2. Bean with Controlled Allocation

**`src/main/java/com/example/startupmemory/StartupSampleCache.java`:**

```java
package com.example.startupmemory;

import org.springframework.stereotype.Component;

@Component
public final class StartupSampleCache {

    private final byte[][] blocks = new byte[128][];

    public StartupSampleCache() {
        for (int i = 0; i < blocks.length; i++) {
            blocks[i] = new byte[16 * 1024];
        }
    }

    public long payloadBytes() {
        return (long) blocks.length * 16 * 1024;
    }
}
```

The bean retains `128` byte arrays, each with a `16 * 1024`-byte payload. Deterministic total payload:

```text
128 * 16 * 1024 = 2,097,152 bytes = 2 MiB
```

This is **`byte[]` payload**, not exact retained heap: there are also object headers, array references, alignment, and all other Spring/JVM objects. Because the arrays are kept in a field, they stay observable for the bean's lifetime.

### 7.3. Snapshot Before/After SpringApplication.run

**`src/main/java/com/example/startupmemory/StartupMemoryObserverApplication.java`:**

```java
package com.example.startupmemory;

import java.lang.management.ClassLoadingMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupMemoryObserverApplication {

    public static void main(String[] args)
            throws InterruptedException {

        Snapshot before = Snapshot.capture();
        long startedAt = System.nanoTime();

        SpringApplication app =
                new SpringApplication(StartupMemoryObserverApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            long elapsedNanos = System.nanoTime() - startedAt;
            Snapshot after = Snapshot.capture();

            before.print("BEFORE");
            after.print("AFTER");

            System.out.printf(
                    "RUN duration = %.1f ms%n",
                    elapsedNanos / 1_000_000.0);

            System.out.println(
                    "Class load delta = "
                    + (after.totalLoaded() - before.totalLoaded()));

            System.out.println(
                    "GC count delta = "
                    + (after.gcCount() - before.gcCount()));

            System.out.println(
                    "GC reported time delta = "
                    + (after.gcTimeMs() - before.gcTimeMs())
                    + " ms");

            int pauseSeconds = context.getEnvironment()
                    .getProperty(
                            "probe.pause-seconds", Integer.class, 0);

            if (pauseSeconds > 0) {
                pauseSeconds = Math.min(pauseSeconds, 60);
                System.out.println(
                        "PROBE: pause " + pauseSeconds + " seconds");
                Thread.sleep(pauseSeconds * 1000L);
            }
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner showCache(StartupSampleCache cache) {
        return args -> System.out.println(
                "CACHE payload bytes = " + cache.payloadBytes());
    }

    record Snapshot(
            long heapUsed,
            long heapCommitted,
            long heapMax,
            int currentlyLoaded,
            long totalLoaded,
            long unloaded,
            long gcCount,
            long gcTimeMs) {

        static Snapshot capture() {
            MemoryUsage heap = ManagementFactory
                    .getMemoryMXBean().getHeapMemoryUsage();

            ClassLoadingMXBean classes =
                    ManagementFactory.getClassLoadingMXBean();

            long count = 0;
            long time = 0;

            for (GarbageCollectorMXBean gc :
                    ManagementFactory.getGarbageCollectorMXBeans()) {
                long c = gc.getCollectionCount();
                if (c >= 0) {
                    count += c;
                }
                long t = gc.getCollectionTime();
                if (t >= 0) {
                    time += t;
                }
            }

            return new Snapshot(
                    heap.getUsed(),
                    heap.getCommitted(),
                    heap.getMax(),
                    classes.getLoadedClassCount(),
                    classes.getTotalLoadedClassCount(),
                    classes.getUnloadedClassCount(),
                    count,
                    time);
        }

        void print(String label) {
            System.out.printf(
                    "%s used=%d KiB committed=%d KiB max=%d KiB "
                    + "loadedNow=%d totalLoaded=%d unloaded=%d "
                    + "gcCount=%d gcTime=%d ms%n",
                    label,
                    heapUsed / 1024,
                    heapCommitted / 1024,
                    heapMax < 0 ? -1 : heapMax / 1024,
                    currentlyLoaded,
                    totalLoaded,
                    unloaded,
                    gcCount,
                    gcTimeMs);
        }
    }
}
```

**Explanation:**

- `Snapshot.capture()` reads data from MXBeans of the **current JVM**; it is not fake data.
- `before` is captured before creating `SpringApplication`, yet **after the JVM has already started running `main`**.
- `after` is captured right after `app.run(args)` succeeds, i.e., after runners and the Ready event.
- `Class load delta` uses the difference in `getTotalLoadedClassCount`, not the difference in currently loaded classes, to account for every class ever loaded.
- `GC count/time` sums statistics from collector MXBeans when values are non-negative. If the JVM does not support a statistic, the demo skips it; in practice, print an "unavailable" status or verify via GC logs.
- `showCache` in `ApplicationRunner` ensures the `StartupSampleCache` bean is requested before `run` returns. It prints the payload bytes defined by the code.
- `WebApplicationType.NONE` keeps the project from holding an HTTP server open; `try-with-resources` closes the context so the program exits on its own.
- `Thread.sleep` is only for the optional external snapshot pause and is **not** included in the `RUN duration` measurement; pause time is capped at 60 seconds.
- `System.out.printf` includes log-printing overhead after the snapshot; do not treat log output as a per-method precision profiler.

### 7.4. Running

```bash
./gradlew bootJar
java -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

The lines printed by the code have the form:

```text
CACHE payload bytes = 2097152
BEFORE used=... KiB committed=... KiB max=... KiB loadedNow=... totalLoaded=... unloaded=... gcCount=... gcTime=... ms
AFTER used=... KiB committed=... KiB max=... KiB loadedNow=... totalLoaded=... unloaded=... gcCount=... gcTime=... ms
RUN duration = ... ms
Class load delta = ...
GC count delta = ...
GC reported time delta = ... ms
MAIN: context closed
```

The ellipses **are only placeholders for runtime-dependent numbers**, not deterministic stdout. The only byte count predictable directly from the code is `CACHE payload bytes = 2097152`.

**Do not use a single run's result** to claim Java 17/Boot 3.3 always takes a fixed number of milliseconds. JDK distribution, CPU, OS cache, disk, dependency JARs, JVM flags, and system state all vary.

## 8. GC Unified Logging: -Xlog:gc*

How to record GC events from before `main`:

```bash
java '-Xlog:gc*:file=gc-startup.log:time,uptime,level,tags' -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

PowerShell uses the same single line:

```powershell
java '-Xlog:gc*:file=gc-startup.log:time,uptime,level,tags' -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

An illustrative GC log in HotSpot format:

```text
[2026-11-09T08:01:12.111+0000][1.123s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 40M->18M(128M) 9.123ms
```

This **is not an actual measurement** of the project. In this structural example:

- `1.123s` is JVM uptime, not total startup duration.
- `GC(0)` is the GC event ID.
- `40M->18M(128M)` shows heap usage before/after and capacity in the collector's format.
- `9.123ms` is the pause reported by the log line.

Identify events lying **within the measured startup window** before calculating pause share relative to time. GC logs have lines for collector, heap sizing, and regions depending on the JVM. Do not apply the same parser across all JDKs/GCs without checking the format.

### If the Log Shows No Collections

That can be normal for a small application with a large enough heap. **No collections does not mean no allocations.** You can use JFR to find allocation hotspots even if GC never ran during startup.

### Avoid Distorting Measurements

Do not add `System.gc()` into startup to "test GC"; that call can trigger a collection unrepresentative of the real application. Do not call `jcmd PID GC.run` in baselines. When comparing GC tuning, keep the workload and JVM version identical.

## 9. Class Loading Logs: -Xlog:class+load

Recording loaded classes:

```bash
java '-Xlog:class+load=info:file=class-load.log:time,uptime,level,tags' -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

An illustrative line:

```text
[0.923s][info][class,load] com.example.startupmemory.StartupSampleCache source: file:/.../app.jar
```

The source path can differ when using a Spring Boot executable JAR with a nested JAR classpath. Do not treat the example above as an absolute source format.

**How to read:** inspect which packages load many classes, when they occur, and correlate with Spring startup steps/JFR CPU. Do not merely count lines while ignoring timing. Class logging at `info` level can be **huge**, introducing I/O overhead and slowing startup. Run it in a separate diagnostic pass.

**Loading differs from initialization:** seeing a class in `-Xlog:class+load` does not prove its static initializer has run. If you need to study class initialization, use log tags supported on the running JVM (`java -Xlog:help`) or an appropriate deep tool.

**A reasoning trap:** more loaded classes do not necessarily lengthen startup proportionally. Class loading can overlap with I/O, CPU, JIT, and bean initialization. Only profiling/controlled tests let you evaluate actual impact.

## 10. JFR: Observing Allocation Hotspots, Class Loading, and GC on One Timeline

Java Flight Recorder can be enabled **from JVM launch**, ideal when startup is too fast to attach a profiler afterward:

```bash
java '-XX:StartFlightRecording=filename=boot-start.jfr,settings=profile,dumponexit=true' -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar
```

- `settings=profile` uses a more detailed configuration than `default` for short investigations; overhead may be higher.
- `filename` is where the recording is written.
- `dumponexit=true` writes the recording at JVM shutdown, useful for non-web programs.
- Which events are enabled depends on the JDK and JFR settings; **not every event is present by default**.

### 10.1. Inspecting the Recording Before Interpreting

```bash
jfr summary boot-start.jfr
jfr print --events jdk.GarbageCollection boot-start.jfr
jfr print --events jdk.ClassLoad boot-start.jfr
jfr print --events jdk.ObjectAllocationSample boot-start.jfr
```

If an event type is missing, inspect `jfr summary` and settings. Do not assert there was zero GC/class loading/allocations merely because an event type was disabled or sampling caught no samples.

`jdk.ObjectAllocationSample` **does not record every single allocated object**. It is sampling; use JDK Mission Control (JMC) or a profiler to inspect weighted hotspots and allocation stacks. Do not sum the `size` of samples and call that total allocated bytes without understanding sampling mechanics.

### 10.2. What Is Worth Looking At in JMC?

- Top allocating classes: `byte[]`, `String`, collections, reflection metadata, proxies, binder structures, application data.
- Allocation stack traces: which class/method creates objects and in which phase.
- Class loading events: when specific classes appear, whether proxy/generated types appear.
- GC pauses/heap summary: whether large pauses sit near bean creation/Ready.
- CPU/method sampling and threads: if GC is light yet startup is slow, look for classpath I/O, parsing, locks, or CPU-heavy work.

**Temporal correlation alone does not prove causation.** An allocation burst coinciding with a startup step might come from another library running concurrently. Use stack traces and single-factor experiments to confirm.

### 10.3. JFR Started After Ready Misses Cold Start

```bash
jcmd 12345 JFR.start name=late settings=profile
```

creates a recording for an already-running JVM, yet cannot record class loads/allocations **prior to when recording started**. For startup bottlenecks, choose `-XX:StartFlightRecording` on the Java command line or integrate recording before the part you want to observe.

## 11. Live Snapshots: jcmd, jstat, Native Memory Tracking

Because the example is a non-web application, keep the context alive to attach from another terminal:

```bash
java -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar --probe.pause-seconds=30
```

Once you see `PROBE: pause 30 seconds`, open another terminal:

```bash
jcmd -l
```

Find the real PID, e.g., `12345`, then run:

```bash
jcmd 12345 GC.heap_info
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.flags
jstat -gc 12345 1000 5
jstat -class 12345 1000 5
```

`jcmd GC.heap_info` describes the heap at attach time; `VM.classloader_stats` gives class loader statistics; `jstat` polls statistics at roughly one-second intervals. These are **mainly post-Ready snapshots/trends** in the demo; they cannot reconstruct allocation sites from the initial seconds if JFR/logs were not enabled from launch.

### 11.1. NMT: Tracking HotSpot Native Memory

For `jcmd VM.native_memory` to work, enable NMT **at JVM launch**:

```bash
java -XX:NativeMemoryTracking=summary -jar build/libs/startup-memory-observer-0.0.1-SNAPSHOT.jar --probe.pause-seconds=30
```

Then:

```bash
jcmd 12345 VM.native_memory summary
```

NMT categorizes Java Heap, Class, Thread, Code, GC, Compiler, and other native regions. Distinguish **reserved** (reserved address space) from **committed** (committed memory). Do not call total reserved the actual physical memory used (RSS). NMT does not fully track every native allocation from external non-JVM libraries and carries overhead.

If `VM.native_memory` reports the feature is not enabled, **you must restart** with the flag above; you cannot add the flag to a running JVM by editing a script command line and expecting the process to update itself.

### 11.2. Permissions and Environment

`jcmd` requires a live process, available JDK tools, the right PID, and appropriate attach permissions. In containers, PID namespaces can differ from the host; minimal JRE-only runtime images may lack `jcmd`/`jstat`. Do not install tooling ad hoc in production or request user heap dumps without a security procedure.

### 11.3. Heap Histogram and Heap Dump Are Different Tools

`jcmd PID GC.class_histogram` or `GC.heap_dump` can be very helpful for memory retention analysis, yet they add overhead, can trigger pauses/GC, and carry sensitive data. Do not use them as a default step in startup benchmarks when GC logs, JFR, or MXBeans suffice.

## 12. Combining JVM Milestones with Spring ApplicationStartup

The JVM knows about classes, objects, and GC; Spring knows about creating the context, loading bean definitions, binding configuration, and instantiating beans. Spring Framework provides the `ApplicationStartup` abstraction; Spring Boot 3.3 supports `BufferingApplicationStartup`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
```

This is an **integration snippet**, requiring a real `MyApplication` class in your project. `2048` is the startup steps buffer capacity, **not heap byte size or object count**.

With the Actuator startup endpoint enabled/exposed and a proper Web environment, you can inspect startup steps at `/actuator/startup`. A non-web demo does not automatically have an HTTP endpoint; do not assume merely importing Actuator makes the endpoint public. Restrict access because startup information can reveal internal structure.

Spring Framework also has `FlightRecorderApplicationStartup`:

```java
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

app.setApplicationStartup(new FlightRecorderApplicationStartup());
```

This is an alternative snippet; do not accidentally stack it alongside `BufferingApplicationStartup` on the same object. When combined with a JFR recording, startup steps can appear on the timeline to correlate with GC/classes/allocations.

**ApplicationStartup does not replace JFR.** It does not measure all Java allocations, report every GC pause, or provide loaded class counts. It provides Spring-specific context to understand which phase the JVM was busy in.

## 13. Designing a Reliable Experiment

1. **Pick the right target:** process-to-Ready time, `run` time, or first request? Do not mix them.
2. **Hold JVM and classpath fixed:** same Java version, same Boot, starters, profiles, flags, and data.
3. **Exclude build cost:** build the JAR first, then measure `java -jar`; do not include Gradle downloads/dependency resolution.
4. **Repeat multiple times:** cold/warm system caches, CPU frequency, disk, and machine load cause variance.
5. **Record a profiler-free baseline:** run several times, store median and spread; do not pick the fastest run as representative.
6. **Enable only one diagnostic tool per pass:** GC logs, class load logs, JFR, or NMT can alter startup.
7. **Align JVM uptime with Spring milestones:** do not mix wall-clock timestamps and uptime without conversion.
8. **Change one factor:** e.g., remove an unused starter, narrow classpath scanning, defer cache init, adjust heap budget.
9. **Re-measure the exact scenario:** same environment, measuring both startup and first-use if lazy init is used.
10. **Evaluate correctness:** an app that starts fast yet pushes a missing-config error to the first request can be an operational regression.

Sample report table (fields must be filled with real measurements):

| Run | Java/flags | run() ms | Loaded classes delta | GC count | GC pause ms (log) | Heap used after MiB |
|---|---|---|---|---|---|---|
| 1 | Java17 baseline | ... | ... | ... | ... | ... |
| 2 | Java17 baseline | ... | ... | ... | ... | ... |
| 3 | Java17 + JFR | ... | ... | ... | ... | ... |

Do not compute p95 from 3 runs and treat it as a reliable latency distribution. With small samples, present individual runs, median, and range; tail percentiles require sufficiently large samples.

## 14. Three Diagnostic Scenarios

### Scenario A: Many Classes Loaded, Few GCs

Suppose measurements show:

```text
run duration        = 3.5s
class load delta    = 4,200
gc count delta      = 0
heap used after     = 80 MiB
```

These are **illustrative hypothetical figures**, not project output. You cannot yet conclude class loading took 3.5 seconds; you need JFR CPU/method sampling, class logs, and Spring step timings. However, you already have grounds not to make GC your main hypothesis solely because startup is slow.

### Scenario B: Clear GC Pauses Near Ready

Suppose `run` takes 2 seconds, and GC logs show two pauses of 12 ms and 45 ms in that same window. If the two pauses do not overlap/double-count, roughly 57 ms is a small share of 2,000 ms wall time. Tuning GC right now may bring less value than inspecting bean initialization, I/O, and classpath.

Conversely, if logs show many large pauses with an undersized heap, profile allocations and compare heap/GC settings in a controlled experiment.

### Scenario C: Small Final Heap, High Allocation Churn

Suppose `heapUsed` grows by 20 MiB between two snapshots, yet JFR shows many allocation samples of `String`, `byte[]`, and temporary collections during startup. This can reflect object churn; do not infer `allocated=20 MiB` from the snapshot. Inspect stacks in JFR to confirm the garbage source, avoiding wrongly optimizing long-lived objects.

## 15. Common Mistakes and Fixes

| Wrong understanding or action | Why it is wrong | Fix |
|---|---|---|
| `heapAfter - heapBefore` is total allocation | Temporary objects were already GC'd | JFR allocations/allocated bytes |
| `Runtime.totalMemory()` is used heap | It approximates committed heap | `MemoryUsage.getUsed()` |
| GC delta = 0 means no new objects | GC may simply not have needed to run | Use JFR when allocation data is needed |
| GC occurred so GC must cause slowness | Pauses may be tiny | Compare pause time against wall time |
| Loaded classes = number of Spring beans | Class loading is at JVM level | Combine Spring StartupStep/bean diagnostics |
| Class loaded = static initializer ran | Loading differs from initialization | Observe init separately when needed |
| `-Xmx` caps all process memory | Metaspace/threads/native remain outside | OS RSS + NMT + heap |
| NMT reserved equals RSS | Reserved differs from committed/resident | Read NMT with proper semantics |
| `jcmd` after Ready reconstructs cold-start timeline | Snapshot is only at attach time | Enable JFR/`-Xlog` from launch |
| JFR allocation sample captures every object | Sampling does not log every allocation | Use JMC/weighted analysis |
| Enable heavy profiler then compare to light baseline | Overheads differ | Separate diagnostic passes |
| Call `System.gc()` before measurement | Creates unrepresentative behavior | Measure natural collector behavior |
| `GC.class_histogram` is harmless | Can cause pauses/overhead | Run as a separate diagnostic |
| Run `./gradlew bootRun` first time to measure JVM startup | Gradle includes build/download | Build first, measure JAR |
| One fast run proves optimization | OS cache/JIT/machine load vary | Multiple runs, identical config |
| NMT has no output so jcmd is broken | NMT was not enabled at launch | Launch with NMT flag |
| Leave huge class logs on permanently in prod | Disk/CPU overhead and metadata leak | Enable briefly, control logs |
| Cut startup with lazy init while ignoring first request | Cost was merely deferred | Measure Ready and first-use |

## 16. Security and Diagnostic Overhead

JFR files, class loading logs, heap dumps, and diagnostic snapshots can contain package names, classpaths, code stacks, JVM arguments, user/application data, or sensitive information. Never publish heap dumps publicly. Use restricted-access directories, retain data only as long as needed, and delete per policy.

`-Xlog:class+load` and JFR `profile` options carry runtime overhead; `GC.heap_dump` can cause major pauses. Do not enable extremely verbose system-wide class load logging in production just to count classes. For Actuator startup/threaddump, enforce authentication and management networking; never open endpoints to the Internet.

When measuring RSS/GC in containers, observe both **cgroup memory/CPU limits** and real process metrics. Free host RAM does not reflect a pod/container's budget.

## 17. Self-Verifying Practical Exercises

**Exercise 1 — Basic snapshots.** Run the JAR three times, recording `RUN duration`, `heap used/committed`, `class load delta`, `gc count delta`. Why do the numbers vary?

**Exercise 2 — Increase payload.** Change `blocks` from 128 to 256 and rebuild. By how much does `CACHE payload bytes` increase? Does heap used increase by that exact byte count? Explain overhead and GC.

**Exercise 3 — GC logs.** Enable `-Xlog:gc*`. Are there any GC pauses between JVM startup and Ready? If not, why can allocations still occur?

**Exercise 4 — Class logs.** Enable `-Xlog:class+load=info`, find `StartupSampleCache` and Spring classes. Compare load time with uptime. Why don't class logs prove the constructor has run?

**Exercise 5 — JFR.** Enable recording from JVM launch. Use `jfr summary`, check captured event types, and inspect `ObjectAllocationSample`/`ClassLoad`/`GarbageCollection` when present. Explain sampling.

**Exercise 6 — Attach jcmd.** Run `--probe.pause-seconds=30`, then `jcmd -l`, `GC.heap_info`, `VM.classloader_stats`. Why don't these snapshots replace a JFR startup timeline?

**Exercise 7 — NMT.** Run with `-XX:NativeMemoryTracking=summary`, attach `VM.native_memory summary`. Distinguish reserved/committed from RSS.

**Exercise 8 — jstat.** Run `jstat -gc` and `jstat -class` during the pause. Observe which numbers stabilize after Ready; how would you catch spikes when startup is very fast?

**Exercise 9 — Spring StartupStep.** Enable `BufferingApplicationStartup` or `FlightRecorderApplicationStartup` and correlate with JFR. Explain why correlation does not automatically imply causation.

**Exercise 10 — Heap budget.** On a test machine with sufficient RAM, compare `-Xms64m -Xmx256m` against `-Xms128m -Xmx512m`. Is a larger configuration always faster? Do not change the GC collector and classpath at the same time.

**Exercise 11 — Lazy initialization.** Try `--spring.main.lazy-initialization=true` on a separate copy of the project; compare before/after. Does any cost move to the first bean access?

**Exercise 12 — Real case.** Pick a Spring Boot app with slow startup. Write down a hypothesis, measurement boundaries, GC/class/JFR evidence, one minimal change, and controlled A/B measurements.

### Self-Assessment Questions

1. Why can't heap used represent total allocated bytes?
2. How does `getTotalLoadedClassCount` differ from `getLoadedClassCount`?
3. How does class loading differ from class initialization and bean instantiation?
4. Where does Metaspace reside in the HotSpot memory model?
5. Why can GC count be 0 even if startup creates thousands of objects?
6. When should you use `-Xlog:gc*` instead of only `GarbageCollectorMXBean`?
7. Does JFR `ObjectAllocationSample` record every allocation?
8. Why must JFR be enabled before `main` for cold-start profiling?
9. Are NMT reserved and OS RSS equal?
10. Why doesn't `jcmd` after Ready provide allocation stacks from the earlier startup seconds?
11. Why doesn't `BufferingApplicationStartup` replace JFR?
12. Which settings must be recorded to compare two startups reliably?

## 18. Checklist and Conclusion

- [ ] Defined main/Started/Ready/first-use milestones.
- [ ] Recorded Java/Boot version, JDK vendor, profiles, JVM flags, CPU/RAM/container limits.
- [ ] Built first and measured JAR rather than including Gradle cost.
- [ ] Ran baseline multiple times, documenting run conditions.
- [ ] Collected heap snapshots and class/GC counters as overview data.
- [ ] Used GC logs for pause/heap timeline.
- [ ] Used class load logs to inspect loaded classes and sources.
- [ ] Used JFR for sampled allocations, GC/class timeline, and CPU hotspots.
- [ ] Used `jcmd`/`jstat` while JVM is alive, without inferring past history from snapshots.
- [ ] Enabled NMT from launch before requesting native memory summary.
- [ ] Correlated JVM timeline with ApplicationStartup steps.
- [ ] Distinguished heap occupancy, total allocations, Metaspace, and OS RSS.
- [ ] Avoided `GC.run`/heap dump during baseline runs.
- [ ] Re-measured startup and first-use after a change, verifying correctness.
- [ ] Protected logs/JFR/dumps and kept profilers within needed scope.

**Conclusion:** To understand Spring Boot startup, measure **allocations** with JFR/profiler, **class loading** with `ClassLoadingMXBean` and class load logs, and **GC** with GC logs/JFR, then correlate with **Spring ApplicationStartup** to pinpoint the phase. Low heap used does not prove low allocation; many loaded classes do not equate to many beans; a few GC events do not prove GC makes startup slow. Only measurements with matching boundaries, matching environments, and controlled comparisons support reliable optimization decisions.

### Official Documentation

- Spring Boot 3.3 — Startup Tracking: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator startup endpoint: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Framework 6.1 — ApplicationStartup: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
- Spring Framework 6.1 — FlightRecorderApplicationStartup: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html
- Oracle Java 17 — java command / Unified Logging / JFR flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java 17 — jcmd: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle Java 17 — jstat: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html
- Oracle Java 17 — jfr command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle Java 17 — MemoryMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Oracle Java 17 — ClassLoadingMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
- Oracle Java 17 — GarbageCollectorMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html