# Identifying Pinned Virtual Threads and Measuring Behavior on JDK 21

## 1. The problem to solve

A **virtual thread** is a `java.lang.Thread` managed by the JVM that can execute Java tasks concurrently with many other virtual threads across a smaller number of **platform threads**. When a virtual thread performs a JVM-supported blocking operation (such as waiting on a socket or `Thread.sleep`), it can normally **unmount** from the platform thread running it, returning that platform thread to the scheduler to handle other work.

On **JDK 21**, under certain conditions, a virtual thread **cannot unmount when blocking**. It holds onto the platform thread executing it, called the **carrier**, for the entire wait duration. This state is called **pinning**.

Points to remember:

- Pinning **is not by itself a correctness bug** or deadlock.
- Pinning **can reduce scalability** if pinned durations are long and occur frequently while the application handles high concurrency.
- Not every blocking operation by a virtual thread pins its carrier.
- Not every `synchronized` block causes a problem: only when long/frequent waiting work occurs in a pinning situation are carrier resources held for too long.
- **JDK 21 differs from JDK 24+:** JEP 491 in JDK 24 changes monitor handling; the statement “blocking inside `synchronized` causes pinning” is the model to learn for JDK 21, not an immutable law for all future Java versions.

The goal of this lesson is to **accurately identify pinning on JDK 21, measure impact instead of guessing, fix selectively, and evaluate in Spring Boot**. The guide includes a Java 21 program compilable with `javac`, a controlled microbenchmark, and a Spring Boot 3.5.x example using virtual threads.

## 2. Virtual thread, carrier, mount, and unmount

One virtual thread does not equal one OS thread. JVM scheduling typically operates as follows:

~~~mermaid
flowchart TD
    A["Many virtual threads need to run"] --> B["Virtual-thread scheduler"]
    B --> C["Carrier / platform threads"]
    C --> D["Virtual thread is mounted, executes Java code"]
    D --> E{"Any waiting operation?"}
    E -->|"No"| D
    E -->|"Unmount-capable blocking"| F["Unmount virtual thread"]
    F --> G["Carrier free to run another virtual thread"]
    E -->|"Blocking while pinned on JDK 21"| H["Carrier held during wait"]
    H --> I["Fewer free carriers to handle other work"]
~~~

**Mount:** the virtual thread is executing on a carrier. **Unmount:** the virtual thread's execution continuation is saved so the carrier can run another virtual thread while work is waiting. When the awaited event completes, the JVM can schedule it to mount again; there is no guarantee a virtual thread always returns to the same carrier.

### Why does pinning hurt throughput?

Suppose there are very many independent requests, each waiting 200 ms on I/O. When virtual threads wait in an unmount-capable manner, a few carriers can support very many concurrently waiting requests. If each request **holds** a carrier for 200 ms, useful concurrency can become much more constrained by the number of carriers.

This is a **theoretical model**, not a guaranteed throughput number. A real application is also constrained by CPU, connection pools, databases, network ports, synchronized contention, GC, heap, logging, and external services. Virtual threads are designed to help scale concurrency for I/O-heavy workloads, **not make CPU-bound code run faster**.

### Daemon nature and JVM lifecycle

Virtual threads in Java 21 are **daemon threads**. If only virtual threads/daemon threads remain with no non-daemon platform threads, the JVM can exit. In standalone Java programs, the examples use `Thread.join()` or `Future.get()` from `main` to ensure work finishes before the JVM exits. In Spring Boot relying on virtual threads for schedulers/background tasks, `spring.main.keep-alive=true` may be needed to keep the process running; that is a **lifecycle** concern, distinct from pinning.

## 3. Pinning scenarios on JDK 21

Oracle JDK 21 documentation lists two foundational cases:

1. The virtual thread is executing code inside a **`synchronized` method or block**.
2. The virtual thread is executing a **native method** or foreign function in a way that pins the carrier.

What typically causes performance impact is **a blocking operation occurring inside those regions**. You should not conclude the entire application has an issue merely from seeing `synchronized` in a stack trace.

### Case A: blocking inside a Java monitor

~~~java
private final Object monitor = new Object();

public void load() throws InterruptedException {
    synchronized (monitor) {
        // JDK 21: if the virtual thread waits here,
        // the carrier can be held until the wait ends.
        Thread.sleep(200);
    }
}
~~~

This is a **snippet inside a class**, not a standalone Java file. `Thread.sleep(200)` simulates a wait operation; in a real application it might correspond to blocking network I/O, waiting on data, or a library call. When a virtual thread sleeps inside a monitor on JDK 21, JFR can record a `jdk.VirtualThreadPinned` event if the pinned duration exceeds the configured threshold.

**Do not view `Thread.sleep` as the only cause.** Pinning relates to **monitor + waiting operation**. Moving a waiting call outside the monitor or using an appropriate locking construct can allow the virtual thread to unmount.

### Case B: native/foreign calls

Certain JNI/native operations and foreign-function invocations can keep a virtual thread attached to its carrier. Converting every `synchronized` to `ReentrantLock` **does not fix** native code pinning a carrier. If JFR shows stacks with native frames, analyze the library, driver, I/O API, and JDK version. You may consider using a platform-thread executor for specific native blocking paths, bounding concurrency, or upgrading the library version.

### What does NOT equate to pinning

| Observation | Guaranteed to pin carrier? | Explanation |
| --- | --- | --- |
| Virtual thread calls `Thread.sleep` outside a monitor on JDK 21 | No | Normally unmount-capable blocking |
| Virtual thread waits on virtual-thread-friendly socket I/O outside monitor | No | JVM normally unmounts while waiting |
| `synchronized` only guarding a very brief in-memory assignment | Cannot conclude an issue | No prolonged blocking; short monitors do not necessarily degrade performance |
| Virtual thread waiting to acquire `ReentrantLock` | Not via the same monitor pinning mechanism | Locks in `java.util.concurrent.locks` support a better wait mechanism |
| Many virtual threads in WAITING state | No | WAITING is a thread state; does not by itself mean carriers are held |
| Thread pool/DB connection pool exhausted | No | Can be downstream contention; must distinguish using metrics |
| High overall request latency | No | Latency has many causes; needs JFR and profiling |
| `jdk.VirtualThreadPinned` appears once | One occurrence was recorded | Not yet enough to claim throughput/SLO impact |
| No `jdk.VirtualThreadPinned` observed | Does not prove “never pins” | Subject to duration threshold, sampling/recording window, and workload |

## 4. Which tools does JDK 21 provide to observe pinning?

Three common ways to analyze:

| Tool | Purpose | When to use |
| --- | --- | --- |
| `-Djdk.tracePinnedThreads=full` or `short` | Prints stack trace when a virtual thread blocks while pinned | Quick debugging on JDK 21–23 |
| Java Flight Recorder, event `jdk.VirtualThreadPinned` | Records pinning events exceeding threshold duration | Measuring under real load, aggregating stacks and durations |
| `jcmd PID Thread.dump_to_file -format=json ...` | Dumps virtual/platform thread list and stacks | Inspecting who is waiting and on which call paths at a point in time |

The tools differ in coverage: **tracing helps locate code spots**, **JFR captures events and durations**, **thread dumps show thread states**, while **load testing** reveals end-to-end impact.

### 4.1. jdk.tracePinnedThreads

On **JDK 21**, place the JVM property **before** the main class name or `-jar`:

~~~bash
java -Djdk.tracePinnedThreads=full VirtualThreadPinningLab monitor
~~~

Or shortened:

~~~bash
java -Djdk.tracePinnedThreads=short VirtualThreadPinningLab monitor
~~~

`full` prints detailed stack traces, marking native/monitor frames; `short` reduces output volume. Output is printed by the JVM depending on circumstances, usually to stderr, with **no fixed stdout format** suitable for brittle snapshot tests.

**Limitation:** a stack trace indicates a suspect location, not who holds the monitor, business impact, or percentiles. Furthermore, this property is specific to JDK 21–23; do not assume it remains effective on JDK 24+ where pinning mechanics and diagnostics changed.

### 4.2. JFR: jdk.VirtualThreadPinned

In Oracle JDK 21, JFR includes these events:

- `jdk.VirtualThreadPinned` — a virtual thread was pinned and its carrier was not released for longer than the threshold. Per Oracle JDK 21 docs, this event is enabled by default with a **20 ms threshold**.
- `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd` — virtual thread start/end, **usually disabled by default** because event volume can be huge.
- `jdk.VirtualThreadSubmitFailed` — reports start/unpark failure, typically due to resource limits; not a pinning indicator.

Example starting a recording for a small program:

~~~bash
java -XX:StartFlightRecording=filename=monitor.jfr,dumponexit=true,settings=profile \
  VirtualThreadPinningLab monitor
~~~

After the process exits and `monitor.jfr` is created:

~~~bash
jfr print --events jdk.VirtualThreadPinned monitor.jfr
~~~

If you also want to inspect supporting events:

~~~bash
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed monitor.jfr
~~~

**Note:** `jfr print` output can be empty if the program did not pin, durations stayed below threshold, the recording missed the target phase, or JFR config differed. Do not assume empty events prove zero pinning absolutely. To capture events shorter than 20 ms, adjust JFR event settings/thresholds in a controlled manner; do not lower thresholds in production without assessing overhead.

### 4.3. Thread dumps via jcmd

For a running JDK 21 JVM, find its PID (e.g., via `jcmd -l`) and dump:

~~~bash
jcmd PID Thread.dump_to_file -format=text threads.txt
jcmd PID Thread.dump_to_file -format=json threads.json
~~~

Replace `PID` with the actual PID. Depending on OS, JVM, attach permissions, and timing, the file is written in the Java process's working directory when given a relative path. On JDK 21, `Thread.dump_to_file` can include both virtual and platform threads, helping reveal waiting stacks. It **differs** from a traditional `Thread.print` dump; do not rely on every format displaying lock/JNI statistics identically.

Do not take hundreds of thread dumps per second in production: collection has overhead and creates large outputs. Prefer taking a few snapshots during latency spikes, combined with JFR and request metrics.

## 5. Complete Java 21 example: reproducing controlled pinning and comparing

The example below uses only **JDK 21**, without Maven or Spring Boot. It intentionally calls `Thread.sleep(250)` inside a monitor to demonstrate pinning. Control branches use `ReentrantLock`, and an unlocked branch demonstrates normal blocking.

Create **`VirtualThreadPinningLab.java`**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public final class VirtualThreadPinningLab {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    private VirtualThreadPinningLab() {
    }

    public static void main(String[] args)
            throws InterruptedException {

        String mode = args.length == 0 ? "monitor" : args[0];

        if (!mode.equals("monitor")
                && !mode.equals("reentrant")
                && !mode.equals("plain")) {
            throw new IllegalArgumentException(
                    "Use monitor, reentrant or plain");
        }

        Thread virtual = Thread.ofVirtual()
                .name("pinning-lab")
                .start(() -> {
                    System.out.println("virtual="
                            + Thread.currentThread().isVirtual());

                    if (mode.equals("monitor")) {
                        synchronized (MONITOR) {
                            sleep250();
                        }
                    } else if (mode.equals("reentrant")) {
                        LOCK.lock();
                        try {
                            sleep250();
                        } finally {
                            LOCK.unlock();
                        }
                    } else {
                        sleep250();
                    }

                    System.out.println("completed=" + mode);
                });

        // Main is non-daemon; wait for the virtual thread so the
        // JVM does not exit while the worker is still running.
        virtual.join();
        System.out.println("joined=true");
    }

    private static void sleep250() {
        try {
            Thread.sleep(250);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Lab sleep was interrupted", e);
        }
    }
}
~~~

### Build and run

~~~bash
javac -encoding UTF-8 VirtualThreadPinningLab.java

java VirtualThreadPinningLab monitor
java VirtualThreadPinningLab reentrant
java VirtualThreadPinningLab plain
~~~

The three modes print deterministic **program stdout** lines in order. With `monitor`:

~~~text
virtual=true
completed=monitor
joined=true
~~~

With `reentrant`:

~~~text
virtual=true
completed=reentrant
joined=true
~~~

With `plain`:

~~~text
virtual=true
completed=plain
joined=true
~~~

This is explicit Java code stdout, **excluding** JVM-dependent diagnostic lines. `join()` ensures `joined=true` appears after the virtual worker prints `completed`. In this program, `Thread.sleep(250)` is a simulated wait, not a throughput measurement.

### Enable tracing to detect pinning

~~~bash
java -Djdk.tracePinnedThreads=full VirtualThreadPinningLab monitor
~~~

On **JDK 21**, the monitor path typically emits stack trace warnings while the virtual thread sleeps; the `reentrant` or `plain` paths have no reason to pin from **this example's monitor**. However, how the JVM formats stack traces is not a program output contract. Avoid hardcoding raw stack trace lines with line numbers into assertions.

### Record JFR for two modes

~~~bash
java -XX:StartFlightRecording=filename=monitor.jfr,dumponexit=true,settings=profile \
  VirtualThreadPinningLab monitor

java -XX:StartFlightRecording=filename=reentrant.jfr,dumponexit=true,settings=profile \
  VirtualThreadPinningLab reentrant

jfr print --events jdk.VirtualThreadPinned monitor.jfr
jfr print --events jdk.VirtualThreadPinned reentrant.jfr
~~~

**Observation expectation, not an event-count guarantee:** the monitor case is likely to produce a pinned event because a 250 ms wait exceeds the 20 ms threshold; the reentrant branch does not produce monitor pinning from the illustrative code. Differences in stacks/durations must be verified from actual JFR output. Running the two modes in separate processes avoids mixing recordings.

### Conclusions drawn from the example

- Both virtual threads print `virtual=true`, so the difference is **not** due to one branch using a platform thread.
- `Thread.sleep` does not inherently mean pinning; **monitor context** on JDK 21 is the key factor here.
- `ReentrantLock` can allow a virtual thread to wait without monitor-style carrier pinning, while preserving **mutual exclusion** among callers sharing the lock.
- Pinning can reduce **throughput under load**; a single worker waiting 250 ms does not prove low throughput. Concurrency must be measured in section 6.

## 6. Controlled microbenchmark: carrier starvation under concurrent load

One drawback of using a single shared monitor: many requests get **serialized by the lock itself**, whether pinning happens or not. Thus, measuring with a single shared lock can confuse **lock contention** with **carrier pinning**. To isolate the effect on JDK 21, the next example gives each task **its own monitor**, differing only in whether waiting occurs inside or outside a monitor.

Create **`PinningThroughputLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class PinningThroughputLab {
    private static final int TASKS = 100;
    private static final int SLEEP_MS = 200;

    private PinningThroughputLab() {
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "plain" : args[0];

        if (!mode.equals("plain") && !mode.equals("monitor")) {
            throw new IllegalArgumentException(
                    "Mode must be plain or monitor");
        }

        // Each task gets its own monitor, avoiding contention
        // on the same monitor across tasks.
        Object[] guards = new Object[TASKS];
        for (int i = 0; i < TASKS; i++) {
            guards[i] = new Object();
        }

        CountDownLatch gate = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            for (int i = 0; i < TASKS; i++) {
                Object monitor = guards[i];

                futures.add(executor.submit(() -> {
                    gate.await();
                    if (mode.equals("monitor")) {
                        synchronized (monitor) {
                            Thread.sleep(SLEEP_MS);
                        }
                    } else {
                        Thread.sleep(SLEEP_MS);
                    }
                    return null;
                }));
            }

            long started = System.nanoTime();
            gate.countDown();

            // Future.get() surfaces task errors,
            // and waits until all TASKS tasks finish.
            for (Future<?> future : futures) {
                future.get();
            }

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            System.out.println("mode=" + mode);
            System.out.println("tasks=" + TASKS);
            System.out.println("elapsed_ms=" + elapsedMs);
        }
    }
}
~~~

The code uses Java 21 because `Executors.newVirtualThreadPerTaskExecutor()` and `AutoCloseable` `ExecutorService` are supported in Java 21. The lambda returns `null` to match the `Callable` overload, letting `gate.await()` and `Thread.sleep(...)` throw `InterruptedException` cleanly. `Future.get()` waits for tasks and propagates any exceptions back to main.

### Run with identical scheduler parallelism

~~~bash
javac -encoding UTF-8 PinningThroughputLab.java

java -Djdk.virtualThreadScheduler.parallelism=2 \
  PinningThroughputLab plain

java -Djdk.virtualThreadScheduler.parallelism=2 \
  PinningThroughputLab monitor
~~~

JDK 21 has the implementation property `jdk.virtualThreadScheduler.parallelism` to adjust the number of standard platform threads serving virtual thread scheduling, defaulting based on processor count. Setting `2` is **solely for the experiment**, to clearly expose carrier limits on JDK 21; do not force production schedulers to 2 if real workloads need another level.

Output takes the form:

~~~text
mode=plain
tasks=100
elapsed_ms=<measured time>
~~~

And:

~~~text
mode=monitor
tasks=100
elapsed_ms=<measured time>
~~~

The bracketed text is **a placeholder describing the number computed by the program**, not literal stdout or a guaranteed performance number. The ratio varies by CPU, scheduler, container quota, host machine, JDK patch version, and measurement timing.

### Why can the two branches differ dramatically?

- `plain`: virtual threads wait via `Thread.sleep` outside monitors, normally unmounting and freeing carriers.
- `monitor`: on JDK 21, `Thread.sleep` inside `synchronized` holds the carrier while waiting. With few carriers and many tasks, subsequent tasks must wait to be scheduled.
- Each task has its own monitor, so the difference **is not caused by 100 tasks contending on one monitor**; this is a better experimental design than sharing a single lock.

Still, this benchmark remains a **synthetic lab**: sleep does not replace database queries, TLS/network I/O, application frameworks, memory pressure, or production p99. It demonstrates a mechanism, not a throughput forecast for a Spring Boot service.

### Repeat and never rely on a single number

Run multiple independent processes in an interleaved sequence:

~~~bash
java -Djdk.virtualThreadScheduler.parallelism=2 PinningThroughputLab plain
java -Djdk.virtualThreadScheduler.parallelism=2 PinningThroughputLab monitor
java -Djdk.virtualThreadScheduler.parallelism=2 PinningThroughputLab monitor
java -Djdk.virtualThreadScheduler.parallelism=2 PinningThroughputLab plain
~~~

Repeat rounds, take medians and dispersion ranges, and keep JDK, CPU quota, and parameters fixed. For precise JVM microbenchmarking, use JMH appropriately while controlling warm-up/JIT; the program above is a direct observation lab, not a substitute for rigorous benchmarking methodology.

## 7. Spring Boot 3.5.x + JDK 21: configuration and request path

Spring Boot supports virtual threads on Java 21+ via the property:

~~~properties
spring.threads.virtual.enabled=true
~~~

According to Spring Boot 3.5 documentation, Boot auto-configured executors/schedulers can use virtual threads, and supported embedded web servers can handle requests on virtual threads. **Do not infer every thread in the process is virtual**: custom request/filter/task executors, drivers, web stacks, SDKs, and libraries can still use platform threads.

Specifically, Spring Boot recommends considering:

~~~properties
spring.main.keep-alive=true
~~~

because virtual threads are daemon threads. This property addresses **keeping the JVM alive**, not carrier pinning. With a web server whose threads keep the process alive, keep-alive may not be the deciding factor, yet it helps when an application relies mainly on schedulers/virtual-thread tasks.

### Create a minimal Spring Boot project for testing

Structure:

~~~text
spring-vt-pinning/
├── pom.xml
└── src/main/
    ├── java/com/example/vtpin/
    │   ├── VirtualPinningApplication.java
    │   └── PinningController.java
    └── resources/
        └── application.yaml
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-vt-pinning</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version `3.5.0` is a specific Spring Boot 3.5.x release so the example builds with parent dependency management. Do not use `Thread.ofVirtual()`/virtual threads APIs with `java.version=17`; this code requires **JDK 21 when compiling and running**.

**File `src/main/resources/application.yaml`:**

~~~yaml
spring:
  application:
    name: spring-vt-pinning
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Metrics exposure here is only for **lab/local environments**. In real deployments, lock down Actuator access with proper network policies and security; never expose metrics endpoints openly to the Internet.

**File `src/main/java/com/example/vtpin/VirtualPinningApplication.java`:**

~~~java
package com.example.vtpin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VirtualPinningApplication {

    public static void main(String[] args) {
        SpringApplication.run(VirtualPinningApplication.class, args);
    }
}
~~~

**File `src/main/java/com/example/vtpin/PinningController.java`:**

~~~java
package com.example.vtpin;

import java.util.Map;
import java.util.concurrent.locks.ReentrantLock;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PinningController {
    private final Object monitor = new Object();
    private final ReentrantLock lock = new ReentrantLock();

    @GetMapping("/thread")
    public Map<String, Object> threadInfo() {
        Thread current = Thread.currentThread();
        return Map.of(
                "virtual", current.isVirtual(),
                "name", current.getName());
    }

    @GetMapping("/monitor")
    public String monitor() throws InterruptedException {
        synchronized (monitor) {
            Thread.sleep(200);
        }
        return "monitor-done";
    }

    @GetMapping("/reentrant")
    public String reentrant() throws InterruptedException {
        lock.lock();
        try {
            Thread.sleep(200);
        } finally {
            lock.unlock();
        }
        return "reentrant-done";
    }

    @GetMapping("/plain")
    public String plain() throws InterruptedException {
        Thread.sleep(200);
        return "plain-done";
    }
}
~~~

**Important:** the controller intentionally holds **one shared lock** to illustrate business code with synchronized or ReentrantLock. Because every request to `/monitor` or `/reentrant` contends on the same lock, **do not use throughput differences between those two URLs to isolate pinning impact alone**: lock serialization itself also caps concurrency. To isolate carrier pinning, use the per-task guard lab in section 6.

### Run and inspect request threads

~~~bash
mvn -q -DskipTests package

java -Djdk.tracePinnedThreads=full \
  -XX:StartFlightRecording=filename=boot-pinning.jfr,dumponexit=true,settings=profile \
  -jar target/spring-vt-pinning-0.0.1-SNAPSHOT.jar
~~~

In a second terminal:

~~~bash
curl -s http://127.0.0.1:8080/thread
curl -s http://127.0.0.1:8080/monitor
curl -s http://127.0.0.1:8080/reentrant
curl -s http://127.0.0.1:8080/plain
~~~

If requests are handled on virtual threads as expected by the configuration, the `/thread` response contains JSON with `"virtual":true`; thread names vary by runtime. The other three endpoints intentionally return:

~~~text
monitor-done
reentrant-done
plain-done
~~~

`jdk.tracePinnedThreads` diagnostic lines may be printed by the JVM **outside** HTTP responses. If `/thread` returns `"virtual":false`, **do not jump to concluding “virtual threads are broken”**; check the actual JDK used to run, the active web server, Spring Boot version, custom executors, and request processing path. Pinning benchmarks should be run on endpoints/tasks where `Thread.currentThread().isVirtual()` is already confirmed `true`.

### Stop and read the recording

Stop the application cleanly (e.g., Ctrl+C) so `dumponexit=true` writes the recording:

~~~bash
jfr print --events jdk.VirtualThreadPinned boot-pinning.jfr
~~~

When calling `/monitor` repeatedly on JDK 21 with a virtual-thread request handler, the recording may contain events from the monitor block. Calls to `/reentrant` and `/plain` do not generate monitor pinning from the example's Java code, yet other application code/libraries may still emit pinned events. Therefore **inspect event stack traces**, rather than counting all events in a shared recording and attributing them all to one URL.

## 8. Measuring behavior meaningfully: time, throughput, latency, and error rate

### A/B setup

A minimal lab design:

- **Variant A:** requests/tasks with blocking outside `synchronized` or under an appropriate `ReentrantLock`.
- **Variant B:** the same blocking inside `synchronized` on JDK 21.
- Identical JDK **21 and patch version**, identical Spring Boot artifact, classpath, JVM flags, CPU quota, heap, GC, logging, and downstream.
- Sufficient virtual concurrency so carrier pressure actually appears.
- Equivalent response semantics and verification that no corrupted data occurs.
- Capture JFR in the same load window, plus a profiler-free baseline measurement if JFR overhead affects results.
- Run multiple interleaved processes/rounds to reduce JIT, cache, scheduler, and network noise.
- Measure controlled warm-up, especially when framework and library initialization have high first-request cost.

### Four metric groups to separate

| Group | Metrics | What does it answer? |
| --- | --- | --- |
| Pinning diagnostics | Count `jdk.VirtualThreadPinned`, duration, stack/class/method, timestamp | Are prolonged pinning cases recorded, and where? |
| Scheduler/concurrency | Carrier utilization, runnable backlog, waiting virtual threads, lock contention | When pinning occurs, does it hold carriers long enough to matter? |
| HTTP/service | Throughput (req/s), p50/p95/p99 latency, timeout/error rate | What impact do users or downstream observe? |
| Resource | CPU, memory, GC, native threads, connection pool wait, downstream latency | Is impact caused by pinning or another limit? |

**Do not substitute p99 with average pinned event duration.** Duration reflects how long a carrier was held during one operation; p99 latency is end-to-end request time. The two metrics are related yet not identical.

### Use a load generator with representative concurrency

For the Spring Boot lab, you can use k6, wrk, Gatling, or JMeter on a load-generator machine separate from the app if appropriate. Cases should include low/medium/high concurrency, sufficient warm-up, and a long enough measurement window. Record HTTP 5xx errors, network timeouts, CPU throttling, and server resource saturation as well.

Do not run a benchmark using only sequential `curl` and claim pinning lowers system-wide throughput: one 200 ms request **does not** cause carrier contention.

### Control lock contention

In production, switching `synchronized` to `ReentrantLock` can preserve mutual exclusion yet **does not** eliminate requests queuing for the same resource. If an endpoint has a critical section holding a lock too long, lock wait time remains a bottleneck even when virtual threads can unmount.

To distinguish:
1. Locate `jdk.VirtualThreadPinned` using JFR.
2. Measure lock wait/contention separately.
3. Measure performance under identical input/transaction semantics.
4. Where possible, shrink critical sections or use immutable snapshots and concurrent structures rather than merely swapping lock types.

## 9. Fixing pinned code on JDK 21

### Approach 1: avoid blocking inside synchronized

Before:

~~~java
synchronized (monitor) {
    updateState();
    remoteCall();
}
~~~

If `remoteCall()` can block for a long time, this is a candidate to measure. After, work can be split outside the monitor:

~~~java
synchronized (monitor) {
    updateState();
}

remoteCall();
~~~

**The two snippets are not necessarily equivalent in correctness.** If business rules require `updateState` and `remoteCall` to stay in the same critical section, moving the call outside can introduce races or break invariants. Refactor only after verifying thread safety, transaction boundaries, and idempotency.

A better design may capture an immutable snapshot under the lock, release the lock, perform I/O, and commit new state with a version check if genuinely needed. That keeps the critical section small without silently altering consistency.

### Approach 2: ReentrantLock

Example replacing a monitor block when mutual exclusion is still required:

~~~java
private final ReentrantLock lock = new ReentrantLock();

public String load() throws InterruptedException {
    lock.lock();
    try {
        Thread.sleep(200);
        return "loaded";
    } finally {
        lock.unlock();
    }
}
~~~

This is a Java snippet for an instance class; import `java.util.concurrent.locks.ReentrantLock`. Use `finally` to ensure unlocking if the method throws an exception. On JDK 21, `ReentrantLock` fits virtual threads better for long waits because it avoids **monitor-induced pinning**. Even so, holding a lock across I/O can still block other requests. Sometimes the best solution is **holding no lock across I/O at all**, if semantics allow.

### Approach 3: fix at the library/driver layer

If JFR stack traces show code pinning inside a library:
- check whether a newer version has better virtual threads support;
- inspect whether `synchronized` holds a resource across a blocking call;
- evaluate switching libraries/drivers or adjusting client configuration;
- when native/JNI blocking occurs, consider isolating it to a concurrency-bounded platform-thread executor;
- build performance tests covering errors and realistic load before changing dependencies.

**Do not use reflection or patch a production library class** just to strip `synchronized` without thread-safety testing. Changing lock semantics can create bugs harder to diagnose than pinning.

### Approach 4: bound sources of contention

A code path with 200 virtual threads but only 10 JDBC connections still has to wait on the pool. Virtual threads do not remove capacity limits of databases, HTTP downstreams, file descriptors, or rate limiters. Use semaphores, bounded admission control, or proper connection pool sizing to protect downstream. This addresses **resource saturation**, not a substitute fix for a pinned native call.

## 10. Cases prone to false conclusions

### Seeing no events because 20 ms was not exceeded

JFR `jdk.VirtualThreadPinned` defaults to a 20 ms threshold on JDK 21. A 5 ms pin occurring thousands of times can still carry aggregate cost. If suspected, measure under load, adjust recording thresholds in test environments, and combine tracing with latency metrics. Do not claim “0 events” = “0 pinning” without checking the recording window/threshold.

### Seeing synchronized without blocking

An in-memory synchronized getter lasting a few microseconds is usually not worth changing. Replacing all of them with `ReentrantLock` not only wastes effort, it complicates code and risks concurrency semantics. Prioritize **frequent + long-lived blocking** spots confirmed by JFR.

### Seeing low throughput without pinning

Causes may include a small DB pool, custom thread pools still using platform threads, CPU throttling, GC pauses, lock contention, or downstream latency. Each has its own measurement. An app with virtual threads enabled yet an unmigrated custom executor may not be running the target workload on virtual threads at all.

### Running on JDK 24 and expecting synchronized to emit events like JDK 21

JEP 491 in JDK 24 addressed Java monitor pinning at the runtime level. On a newer JDK, the `synchronized + Thread.sleep` demo may no longer emit old-style pinned events. This is **not a failure of the JDK 21 demo**; it is a version difference that must be documented in reports.

### Using -Djdk.tracePinnedThreads on JDK 24+

This is a diagnostic flag for JDK 21–23 and is no longer a reliable approach on JDK 24+. Prefer JFR, thread dumps, and documentation for the exact JDK running. Do not copy a CLI command and conclude the tool is broken when running on the wrong version.

### Spring Boot logs started yet requests do not use virtual threads

`spring.threads.virtual.enabled=true` affects Boot-supported integrations, not forcing all library-owned code to switch executors. Check inside the exact request/worker with `Thread.currentThread().isVirtual()`, and inspect custom `TaskExecutor`/web servers.

### JVM exits early because only daemon threads remain

Virtual threads are always daemon. In apps without a non-daemon web server or other keeper component, the JVM can exit before scheduled tasks run. Use `spring.main.keep-alive=true` when appropriate; do not confuse this with pinning.

### Tracing or profiling alters results

Stack tracing for frequent pinning events can generate huge output, inflating latency due to logging. Therefore:
1. Run diagnostics to identify stacks.
2. Run A/B baselines with matching tool configurations.
3. If JFR is needed on both branches, enable identical settings and time windows.
4. Clearly report measurement overhead/limitations.

### Ignoring pinning that cannot be fixed with a Java lock

Native code can pin carriers even when outer Java code uses `ReentrantLock`. When stacks contain native frames, use library/driver-level fixes or workload isolation. Do not claim “just swap the lock to eliminate all pinning”.

## 11. Key differences between JDK 21 and JDK 24+

**Do not lump all JDK >=21 releases into one pinning behavior.**

| Issue | JDK 21 | JDK 24+ |
| --- | --- | --- |
| Official virtual threads | Yes, per JEP 444 | Yes |
| Blocking inside Java `synchronized` can pin carrier | Yes | Java monitor pinning addressed by JEP 491 |
| Native/foreign blocking can pin | Yes | Still requires evaluation |
| JFR `jdk.VirtualThreadPinned` | Yes | Still used to diagnose remaining pinning forms |
| `-Djdk.tracePinnedThreads` | Suitable diagnostic tool | Do not apply mechanically as on JDK 21 |
| Verification under real workload | Mandatory | Still mandatory |
| Thread scheduler, resource pools, downstream capacity | Bounded | Still bounded |

Spring Boot 3.5 documentation also notes that **Java 24+ is recommended for a better virtual threads experience**, even though support starts from Java 21. Reasons include JVM improvements like JEP 491; do not interpret that as upgrading the JDK solving every bottleneck or eliminating all native pinning.

While an organization stays on JDK 21 LTS, the right workflow is measuring and selectively fixing pinning that affects SLOs. When preparing to upgrade to JDK 24+ or a newer LTS JDK, **re-run benchmarks**, since the exact same source code can change pinning behavior substantially.

## 12. Standard experimental checklist for a Spring Boot service on JDK 21

**Before measuring:**
1. Record `java -version` to confirm JDK 21 specifically, not Java 17 or 24+.
2. Record artifact hash, Spring Boot version, container image, active profile, and JVM flags.
3. Confirm `spring.threads.virtual.enabled=true` in the target environment.
4. Verify actual request/task paths have `Thread.currentThread().isVirtual()==true`.
5. Record allocated CPUs, CPU quota/throttling, memory limits, GC, and downstream capacity.
6. Verify functional input/response correctness; pinning performance must not trade off against data corruption.

**Collecting data:**
7. Enable `-Djdk.tracePinnedThreads=short/full` in a diagnostic run; save stack traces.
8. Enable JFR `jdk.VirtualThreadPinned` during a representative load window; store logs/JFR files with secure access permissions.
9. Record counts/durations/stacks of pinned events and frequency per minute or per request.
10. If the app hangs/latency spikes, take `jcmd Thread.dump_to_file` a few times with timestamps.
11. Measure throughput, p50/p95/p99, errors/timeouts, CPU, GC, RSS, and connection pool waiting.
12. Measure differences between low and high concurrent requests; a single sequential request normally cannot reveal carrier starvation.

**Fixing and verifying:**
13. Prioritize places with frequent long blocking in monitors, rather than changing every synchronized.
14. Preserve business semantics when moving I/O out of critical sections or switching to `ReentrantLock`.
15. Inspect libraries/native code separately; do not assume all pinned events come from controller code.
16. Re-run A/B with identical artifact conditions, varying only the evaluated change.
17. Collect both latency/success and JFR events **after** fixing to confirm real improvement.
18. If there is no clear gain and the new code is more complex, consider keeping the old design, lowering concurrency, or upgrading the JDK per roadmap.

### Report template to avoid fabricated results

~~~text
JDK version/build: (record from java -version)
Spring Boot / artifact digest: (record actual)
Host / CPU quota / container memory: (record actual)
Workload: endpoint, RPS, concurrency, duration, inputs
Virtual request thread confirmed: true/false
JFR event settings / threshold: (record actual)
Variant A: monitor-blocking on JDK 21
Variant B: refactored / ReentrantLock / outside monitor
Pinning events per minute, A: (measured)
Pinning events per minute, B: (measured)
Median/p95 pinned duration, A/B: (measured)
Throughput, A/B: (measured)
p95/p99 latency, A/B: (measured)
Timeout/error rate, A/B: (measured)
CPU, RSS, GC, downstream pool wait, A/B: (measured)
Decision: (based on real numbers and SLOs)
~~~

Fields in parentheses are **fields to fill from actual measurements**, not results to infer from a code snippet.

## 13. Self-check knowledge

**Question 1. What is pinning on JDK 21?**  
It occurs when a virtual thread remains attached to its carrier during a blocking operation that cannot unmount, leaving the carrier unavailable to serve other virtual threads.

**Question 2. Is seeing synchronized enough to conclude a performance issue?**  
No. You need sufficiently long/frequent blocking and metrics on concurrency, throughput, or latency.

**Question 3. Does Thread.sleep(250) outside synchronized necessarily pin a carrier on JDK 21?**  
No. `Thread.sleep` on a virtual thread normally supports unmounting when not inside a pinning region.

**Question 4. Which JFR event records long-pinned virtual threads?**  
`jdk.VirtualThreadPinned`.

**Question 5. What is the default Oracle JDK 21 threshold for the pinned JFR event?**  
20 ms.

**Question 6. Which JVM flag prints pinning stack traces on JDK 21?**  
`-Djdk.tracePinnedThreads=full` or `short`, placed before the main class/JAR name.

**Question 7. Which command captures a thread dump containing virtual threads?**  
`jcmd PID Thread.dump_to_file -format=json threads.json` or text format.

**Question 8. Why can't a benchmark using a single shared synchronized lock isolate pinning?**  
Because requests are already serialized by lock contention, so low throughput may stem from contention rather than carrier pinning.

**Question 9. What is a simple way to avoid monitor-related pinning on JDK 21 in long blocking blocks?**  
When semantics permit, move blocking outside the monitor or replace with `ReentrantLock`; still evaluate contention.

**Question 10. If pinning occurs in a native method, does changing Java synchronized fix everything?**  
No; native/JNI/foreign code and the library must be analyzed.

**Question 11. Does enabling spring.threads.virtual.enabled=true guarantee every thread is virtual?**  
No. Only supported integrations not overridden by custom executors receive the corresponding configuration.

**Question 12. Does JDK 24+ still pin on synchronized like JDK 21?**  
Not under the old Java monitor mechanism: JEP 491 addressed that pinning class. Other pinning forms still require diagnostics.

**Question 13. Does a JFR file with no VirtualThreadPinned events prove zero pinning?**  
No. Events might have stayed below threshold or occurred outside the recording window.

**Question 14. Why measure p95/p99 and throughput in addition to pinned event counts?**  
Because the goal is service quality impact; event duration is not identical to response latency or success rate.

**Question 15. Are virtual threads faster than platform threads in CPU-bound loops?**  
No. They help scale blocking I/O-heavy workloads, not accelerate CPU computation by themselves.

## 14. Official references and further reading

- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): carrier/mount/unmount, two pinning scenarios, 20 ms JFR event threshold, `jdk.tracePinnedThreads`, `jcmd`.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): design, scheduling, limitations, and diagnostics on JDK 21.
- [Oracle JDK 21 — Thread API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `Thread.ofVirtual()`, `isVirtual()`, scheduler implementation properties.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.dump_to_file`, diagnostic commands.
- [Oracle JDK 21 — jfr tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): reading and analyzing events in `.jfr` recordings.
- [Spring Boot 3.5 — SpringApplication / Virtual Threads](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `spring.threads.virtual.enabled`, pinning caveats, `spring.main.keep-alive`.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured virtual-thread executors and schedulers.
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): Java monitor pinning changes from JDK 24.
- [Oracle JDK 21 — Flight Recorder Configuration](https://docs.oracle.com/en/java/javase/21/jfapi/): configuring recordings/events and observation thresholds.

**Conclusion:** On **JDK 21**, identify pinned virtual threads using **stack traces/JFR**, confirm the actual task path uses virtual threads, and measure impact via **throughput, tail latency, error rate, and carrier/resource metrics**. Refactor only when pinning is sufficiently long, frequent, **and** impacts the system. Do not confuse Java 21 mechanics with JDK 24+, do not replace every `synchronized` mechanically, and do not use virtual threads to mask another downstream bottleneck.