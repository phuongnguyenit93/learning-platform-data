# Reading Thread Dumps, GC Statistics, and Event-Loop Metrics to Verify Hypotheses

## 1. Goal: Evidence-Based Spring Boot Performance Diagnostics

A Spring Boot API's p99 latency jumps from 200 ms to 3 seconds. Container CPU spikes up and down; heap looks like a sawtooth; dozens of threads show up in a dump. You cannot glance at one chart and declare "GC caused the outage", "Tomcat needs more threads", or "the Netty event loop is blocked". This lesson focuses on **reading evidence to confirm or refute a hypothesis**, not just running JVM commands.

Scope: Spring Boot **3.3.x**, Spring Framework 6.1.x, Java 17+; application examples use Java 21 and Spring Boot 3.3.13. Tools `jcmd`, `jstat`, `jfr`, and `-Xlog` target **OpenJDK/HotSpot**; exact syntax, overhead, and outputs vary across JVM vendors and versions. Spring MVC runs on Servlet/Tomcat; WebFlux examples use Reactor Netty.

A solid workflow follows 6 steps:

1. Define the **symptom, time window, and request route**.
2. State a concrete hypothesis with predicted signals before collecting data.
3. Capture **multiple thread dumps** and metrics across the same window.
4. Check **GC counts, GC pauses, heap, and CPU** before blaming JVM memory.
5. For WebFlux, inspect **event loops and schedulers**; for MVC, inspect **Tomcat workers, queues, and pools**.
6. Change one variable in staging/canary, measure before/after, and update your conclusion.

Never blindly raise `-Xmx`, Tomcat threads, or Netty workers simply because timeouts occurred. Pool starvation, slow SQL, lock contention, CPU throttling, and GC pauses can look deceptively similar while demanding completely different fixes.

## 2. Diagram of Layers Where a Request Can Stall

```text
Browser / upstream caller
        |
        v
CDN / ingress / gateway / load balancer
        |
        v
Spring Boot HTTP runtime
        |
        +-- Spring MVC + Tomcat worker threads
        |      |
        |      +-- Service -> JDBC pool -> database
        |      +-- Service -> HTTP client pool -> downstream
        |
        +-- WebFlux + Reactor Netty event loops
               |
               +-- Non-blocking I/O
               +-- Reactive schedulers / boundedElastic
               +-- Connection pools / remote services
        |
        v
JVM heap, GC, safepoints, CPU, and OS scheduling
        |
        v
HTTP response
```

A request can lose 3 seconds **before entering the controller** due to gateway queues or connector backlogs. Conversely, the controller may start immediately and block waiting on a DB pool. When `http.server.requests` shows 500 ms while the browser sees 3 seconds, inspect intervals outside the HTTP observation boundary instead of staring solely at controller thread dumps.

Synchronize timestamps, timezones, deployment revisions, CPU quotas, request rates, p50/p95/p99, and error rates. A thread dump captured after the service has already recovered rarely explains the earlier incident.

## 3. Forming Falsifiable Hypotheses

| Hypothesis | Predicted Evidence If True | Additional Evidence Needed |
| --- | --- | --- |
| GC pauses inflate p99 | Pause duration/frequency rises during incident | GC logs, JFR, `jvm.gc.pause`, aligned HTTP latency timestamps |
| Tomcat worker threads exhausted | Busy threads near max, requests/queues wait | `tomcat.threads.busy`, thread dumps, connector metrics |
| Lock contention | Multiple threads `BLOCKED` on same monitor/owner | `Thread.print -l`, JFR monitor events |
| DB connection pool exhausted | Hikari `active=max`, pending rises, workers wait on borrow | Hikari metrics, SQL/transaction durations |
| Reactor Netty event loop blocked | Stacks on `reactor-http-nio` in blocking calls, pending tasks rise | Dumps, event-loop metrics, JFR |
| CPU-bound algorithm | High per-thread CPU delta, JFR execution samples clustered | `top -H`, `pidstat`, JFR |
| Container CPU throttling | Service p99 climbs alongside cgroup throttled time | cgroup / Kubernetes CPU metrics |
| Slow downstream | HTTP client / DB spans elongate; threads wait on I/O | Distributed traces and downstream telemetry |

**Never write vague hypotheses** like "Java performance is bad". A falsifiable hypothesis looks like: "Between 14:00 and 14:10, at least 80% of Tomcat request workers are parked in `HikariPool.getConnection`; Hikari pending climbs; therefore p99 rises due to waiting for DB connection leases." That states concrete observables that can be proven false.

## 4. Gather Baseline Context and Identify the Exact Java PID

First verify the service, JVM, and workload:

```bash
java -version
jcmd -l
jps -l
```

In Linux/containers, a container-namespaced PID can differ from the host PID. Minimal container images may omit JDK diagnostic tools. Only run attach tools when authorized; `jcmd` generally requires the same host/namespace, matching user/group permissions, and attach enabled.

The commands below use a **verified placeholder PID**:

```bash
PID=12345
jcmd "$PID" VM.version
jcmd "$PID" VM.uptime
jcmd "$PID" VM.command_line
jcmd "$PID" help
```

`jcmd -l` is not a universal inventory across isolated PID namespaces. In Kubernetes you may need an ephemeral debug container matching the target PID namespace and permissions, or pre-enabled metrics/JFR. Never run `jcmd 0` blindly, which broadcasts to every accessible JVM.

Record JDK version/GC collector, heap flags, CPU quota, instance/pod name, uptime, and release version before analyzing; changing collectors or images changes metrics and thread names.

## 5. Thread Dumps Are Snapshots, Not Time Profilers

With HotSpot JDK 17/21:

```bash
jcmd "$PID" help Thread.print
jcmd "$PID" Thread.print -l > dump-01.txt
sleep 3
jcmd "$PID" Thread.print -l > dump-02.txt
sleep 3
jcmd "$PID" Thread.print -l > dump-03.txt
```

`-l` includes `java.util.concurrent` lock details. Capture 2–3 snapshots during the incident to spot **recurring patterns**. Adjust count and spacing carefully rather than spamming dumps on JVMs with thousands of threads. `Thread.print` incurs pause/safepoint cost proportional to thread count and stack depth. `jstack -l PID` works similarly if present, though running both adds redundant overhead.

Remember thread dumps contain thread names, class names, hostnames, query/operation descriptors, and internal metadata. Protect dump files and access permissions—never attach raw dumps to public tickets.

Spring Boot Actuator also provides `/actuator/threaddump`, returning JSON when enabled and exposed. It is not exposed over HTTP by default, nor does it fully replace HotSpot native dumps for lock/virtual-thread detail—choose the right tool for your goal.

## 6. Reading Thread Names, States, Stacks, and Locks

Illustrative excerpt:

```text
"http-nio-8080-exec-7" #77 daemon
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.service.InventoryService.reserve(...)
        - waiting to lock <0x000000000abc1234>
        at com.example.web.InventoryController.reserve(...)
```

Reading workflow:

1. Identify the thread's **role**: `http-nio-*` usually indicates Tomcat; `reactor-http-nio-*` usually indicates Netty; `boundedElastic-*` belongs to the Reactor scheduler. These are naming conventions, not API guarantees.
2. Note its **state** and top stack frames. Read further down the stack to see which method invoked a blocking call.
3. Match `- waiting to lock`, `- locked`, and the lock owner to identify the contested resource.
4. Check whether the same stack persists across all 3 dumps; recurring waits during timeouts point toward a bottleneck.
5. Correlate with resource metrics (Hikari pool, HTTP connection manager, Tomcat pool, OS CPU).
6. Never assume a single `RUNNABLE` frame means a CPU-hot thread.

A thread dump is **a single instant in time**. A request can spend 2 seconds waiting on the DB and happen to be serializing JSON at the exact millisecond the dump runs, making the snapshot look harmless. JFR, trace spans, and multiple dumps reduce misdiagnosis.

## 7. Meaning of Common JVM Thread States

| State | General Meaning | Do Not Misread As |
| --- | --- | --- |
| `RUNNABLE` | Executing or ready to run / in native execution | Definitely burning CPU |
| `BLOCKED` | Waiting to enter a Java intrinsic monitor (`synchronized`) | Every I/O or pool wait uses this state |
| `WAITING` | Waiting indefinitely on `wait`, `park`, `join`, etc. | Definitely a deadlock |
| `TIMED_WAITING` | Sleeping, timed wait, or timed park | Inherently a performance bug |
| `NEW`, `TERMINATED` | Not yet started or already finished | A runtime bottleneck |

Idle executor threads often sit in `WAITING` inside `LinkedBlockingQueue.take`. That is normal when queues are empty and requests complete fast. With `ReentrantLock`, `Semaphore`, or pool queues, threads typically show `WAITING` inside `LockSupport.park`, not `BLOCKED`.

A `RUNNABLE` thread inside native socket read or `epoll` wait does not mean it is burning CPU either. Verify with **per-thread CPU deltas**, JFR samples, or OS profilers.

## 8. Diagnosing Lock Contention, Deadlocks, and Pool Waits

When multiple threads show `BLOCKED` on the same monitor, find the thread **holding the monitor**:

```text
Worker A:
  java.lang.Thread.State: BLOCKED
  - waiting to lock <0xABC>

Worker B:
  java.lang.Thread.State: TIMED_WAITING
  at java.lang.Thread.sleep(...)
  - locked <0xABC>
```

Worker B can be sleeping while **still holding the `synchronized` monitor**. That is lock contention, not necessarily a deadlock. A true deadlock requires a dependency cycle—e.g., A holds lock 1 waiting for lock 2 while B holds lock 2 waiting for lock 1. HotSpot can flag Java-level deadlocks in thread dumps, yet cannot detect **distributed locks, DB transaction locks, or native deadlocks**.

A thread waiting on a database connection pool typically shows frames such as:

```text
at jdk.internal.misc.Unsafe.park(...)
at java.util.concurrent.locks.LockSupport.park(...)
at com.zaxxer.hikari.pool.HikariPool.getConnection(...)
at com.example.repository.OrderRepository.load(...)
```

This stack is illustrative; exact frames vary by JDK, Hikari, and driver versions. Many workers parked in `HikariPool.getConnection` alongside rising Hikari pending and `active=max` proves a **pool acquisition bottleneck**, not yet a database lock. Follow up with SQL durations, transaction lengths, connection leak checks, and pool sizing.

## 9. Standalone Java 17 Program Creating Controlled `BLOCKED` Threads

Example spawning two threads: one holds an intrinsic monitor while awaiting a latch, and the second tries to enter that monitor. Run it in one terminal and attach `jcmd` during its observation window.

**`ThreadDumpLab.java`:**

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadDumpLab {
    private static final Object LOCK = new Object();
    private static final CountDownLatch HELD = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final CountDownLatch ATTEMPTED = new CountDownLatch(1);

    public static void main(String[] args) throws Exception {
        Thread holder = new Thread(() -> {
            synchronized (LOCK) {
                HELD.countDown();
                try {
                    RELEASE.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lab-monitor-holder");

        Thread waiter = new Thread(() -> {
            ATTEMPTED.countDown();
            synchronized (LOCK) {
                // Can only enter after holder releases the monitor.
            }
        }, "lab-monitor-waiter");

        holder.start();
        HELD.await();
        waiter.start();
        ATTEMPTED.await();

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(3);

        while (waiter.getState() != Thread.State.BLOCKED) {
            if (System.nanoTime() > deadline) {
                RELEASE.countDown();
                throw new IllegalStateException("No BLOCKED thread");
            }
            Thread.sleep(10);
        }

        try {
            System.out.println("holder=" + holder.getState());
            System.out.println("waiter=" + waiter.getState());
            System.out.println("capture-window=5s");
            Thread.sleep(5000);
        } finally {
            RELEASE.countDown();
            holder.join();
            waiter.join();
        }
        System.out.println("done");
    }
}
```

Commands:

```bash
javac ThreadDumpLab.java
java ThreadDumpLab
```

**Stdout when running as designed:**

```text
holder=WAITING
waiter=BLOCKED
capture-window=5s
done
```

In a second terminal during the 5-second window:

```bash
jcmd -l
jcmd <PID> Thread.print -l
```

Replace `<PID>` with the actual PID. In the dump, `lab-monitor-holder` is `WAITING` on `CountDownLatch.await` while still holding `LOCK`, and `lab-monitor-waiter` is `BLOCKED` waiting for that exact monitor. On slow machines, extend the capture window in source and rerun. Never use this pattern to inject contention in production.

## 10. Diagnosing High-CPU Threads

`RUNNABLE` does not automatically mean high CPU usage. On Linux, inspect OS thread IDs (TIDs):

```bash
top -H -p "$PID"
pidstat -t -p "$PID" 1 5
```

`pidstat` requires the `sysstat` package. Traditional HotSpot thread dumps print native IDs as `nid=0x...` in hex, whereas OS tools report decimal TIDs. Convert decimal to hex to correlate:

```bash
printf '0x%x\n' 1234
```

**Never confuse Java `threadId`/`Thread.getId()` with OS TID.** Virtual threads also lack a 1:1 mapping to kernel threads. JFR execution samples or a CPU profiler give much stronger evidence of hot Java methods.

Strong corroboration looks like:

```text
top -H: OS thread TID 1234 sustains high CPU across several seconds
Thread.print: nid=0x4d2, stack inside ReportService.sortHugeList
JFR: jdk.ExecutionSample hotspots match the same call path
```

That evidence supports a CPU-bound hypothesis. Conversely, if a thread is in `EPoll.wait` with near-zero CPU delta, never claim it is "spinning nonstop" just because the dump says `RUNNABLE`.

## 11. Spring MVC/Tomcat: Compare Saturation Against the Worker Cap

In Servlet Spring MVC, Tomcat uses worker threads named `http-nio-8080-exec-*`. Blocking calls like JDBC, synchronous `RestClient`, `Thread.sleep`, lock contention, or file I/O keep workers occupied for the entire wait. When many concurrent requests block, busy threads approach the worker cap and new requests queue in the connector or gateway.

Spring Boot 3.3 properties:

```properties
server.tomcat.threads.max=200
server.tomcat.accept-count=100
```

`threads.max` and `accept-count` **govern different resources**: accept count never adds request workers. Do not treat 200/100 as universal defaults; they are illustrative values. Under async Servlets, SSE, or virtual threads, request lifetime and worker thread occupancy decouple from the synchronous model.

To verify Tomcat saturation: inspect `tomcat.threads.busy`, `tomcat.threads.current`, request p99/5xx, queue/connection metrics, and 2–3 thread dumps; confirm whether workers are busy **burning CPU**, **waiting on pools**, **waiting on I/O**, or **blocked on locks** before raising any cap.

## 12. Runnable Spring Boot MVC Demo for Observing Workers

Project uses Java 21, Spring Boot 3.3.13, and Gradle Wrapper. Run only on localhost/staging because the demo endpoint intentionally sleeps to create slow requests.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') { useJUnitPlatform() }
```

**`src/main/java/com/example/mvcdiag/MvcDiagApplication.java`:**

```java
package com.example.mvcdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDiagApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcDiagApplication.class, args);
    }
}
```

**`src/main/java/com/example/mvcdiag/SlowController.java`:**

```java
package com.example.mvcdiag;

import java.util.concurrent.TimeUnit;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class SlowController {

    @GetMapping("/demo/sleep")
    public String slow(
            @RequestParam(defaultValue = "2000") long delayMs)
            throws InterruptedException {

        if (delayMs < 0 || delayMs > 5000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid delayMs");
        }
        TimeUnit.MILLISECONDS.sleep(delayMs);
        return "slept";
    }

    @GetMapping("/demo/quick")
    public String quick() {
        return "quick";
    }
}
```

This is an **intentionally blocking example**, not production request-handling architecture. In real apps, occupied threads stem from slow SQL or downstreams rather than `Thread.sleep`.

## 13. Enabling JVM/Tomcat Metrics on Localhost

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080

server.tomcat.mbeanregistry.enabled=true
server.tomcat.threads.max=20

management.endpoints.web.exposure.include=health,metrics,threaddump
server.error.include-stacktrace=never
```

Per Spring Boot 3.3, Tomcat metrics auto-configure when Tomcat's MBean registry is enabled (`server.tomcat.mbeanregistry.enabled=true`). Micrometer `jvm.*` metrics generally auto-configure with Actuator. Always check live runtime metric names rather than assuming every meter exists automatically.

Run:

```bash
./gradlew bootRun
curl -i http://127.0.0.1:8080/demo/quick
curl -i "http://127.0.0.1:8080/demo/sleep?delayMs=3000"
```

Successful bodies are `quick` and `slept`; actual HTTP duration varies with scheduling and GC.

While `/demo/sleep` is running, in another terminal:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/jvm.threads.live
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/threaddump > dump.json
```

`dump.json` captures a JVM snapshot through Spring Actuator. Running a small controlled concurrent burst on **localhost** raises busy threads with stacks inside `TimeUnit.sleep`. However, **sleeping threads in a demo do not prove production lacks workers** without pool, throughput, and queue context.

Never expose Actuator `threaddump` publicly. Binding `server.address=127.0.0.1` only protects a local demo on one host—it does not replace RBAC, network policies, and production TLS.

## 14. GC Statistics: Separating Allocation, Pauses, and Retention

Garbage collection reclaims unreachable objects; heap climbing and dropping after GC is **normal behavior**. A performance incident involving GC can stem from:

- **High allocation rate:** rapid object churn triggering frequent young collections.
- **Long or frequent pauses:** stop-the-world pauses freezing application threads.
- **Concurrent GC CPU overhead:** background GC threads competing for CPU while the app runs.
- **Heap near capacity:** rising collection pressure, old-gen collections, and `OutOfMemoryError` risk.
- **Object retention / leak:** post-GC live set rising steadily under equivalent load.
- **Native/direct memory:** RSS climbing while Java heap barely moves.

Do not conflate G1, Parallel GC, and ZGC—collectors differ completely in pause phases and semantics. A concurrent GC phase lasting several seconds does not necessarily cause a multi-second **stop-the-world pause**. Conversely, a few 20 ms pauses during a request contribute partially to latency without explaining a 4-second slowdown.

## 15. Using `jstat -gcutil` for Trends, Not a Single Line

Example taking 10 samples 1,000 ms apart:

```bash
jstat -gcutil "$PID" 1000 10
```

Common columns (dependent on collector and JDK):

| Column | Practical Interpretation |
| --- | --- |
| `E` | Eden space utilization |
| `O` | Old generation usage |
| `YGC`/`YGCT` | Young GC count and cumulative time |
| `FGC`/`FGCT` | Full GC count and cumulative time |
| `CGC`/`CGCT` | Concurrent GC count/time when applicable |
| `GCT` | Total GC time reported by `jstat` |

Oracle marks `jstat` as experimental/unsupported, and column layouts change across JVM releases. Never hardcode parsers to column positions from old examples.

Always read **deltas**, never cumulative totals as single-request time. If `GCT` moves from 6.40 to 6.55 over 10 seconds, the delta is 0.15 seconds of reported GC time across that 10-second window; cross-check against HTTP latencies and GC pause logs before concluding anything.

Inspect `jvm.memory.used`, `jvm.gc.pause`, `jvm.threads.live`, `process.cpu.usage`, and container RSS alongside `jstat`. `jvm.gc.pause` is a Timer; check COUNT, TOTAL_TIME, MAX, or backend distributions rather than looking only at one average.

## 16. Unified GC Logging on Java 17/21

HotSpot supports unified logging since JDK 9, useful at startup in test/staging:

```bash
java \
  '-Xlog:gc*,safepoint:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M' \
  -jar app.jar
```

`app.jar` is illustrative—replace with your real `bootJar` path. `-Xlog:gc*` captures far more detail than `-Xlog:gc`, and `safepoint` catches non-GC JVM pauses too. Logging carries slight overhead and log rotation requires enough disk space.

Illustrative GC log line:

```text
[2026-11-08T09:00:00+0700][info][gc] GC(21) Pause Young (...) 140M->88M(256M) 18.7ms
```

Collector names, heap capacities, timestamps, and formatting **are not fixed literal stdout**. Align **pause timestamps** with traces and HTTP latencies. Never blame a 4-second request on GC when the log shows only an 18.7 ms pause.

If the JVM is already running and permissions allow:

```bash
jcmd "$PID" help VM.log
jcmd "$PID" VM.log list
jcmd "$PID" GC.heap_info
```

`VM.log` configures unified logging dynamically on HotSpot—verify syntax and overhead before raising log verbosity live. `GC.heap_info` inspects heap layout, not leaks from a single snapshot. Never trigger `GC.heap_dump` or `GC.class_histogram` in production without weighing pause impact and sensitive data exposure.

## 17. Three Commonly Misread GC Data Patterns

**Pattern A: Normal Sawtooth Heap**

```text
Used heap: 120M -> 190M -> GC -> 125M -> 195M -> GC -> 126M
Pause: low, HTTP p99 steady
```

There is no basis to call this a memory leak merely because heap grows before each GC.

**Pattern B: Allocation Pressure**

```text
Young GC count rises fast, high allocation rate
Total GC pause and GC CPU rise
HTTP p99 rises in the same window
```

Suspect excessive temporary object allocation, parsing/serialization churn, cache thrashing, or poorly sized heap. Use JFR allocation sampling/profiling, test cutting allocations in staging, and compare GC before/after.

**Pattern C: Retention Suspected as Leak**

```text
Post-GC live set: 180M -> 240M -> 300M -> 370M
Equivalent traffic mix across many GC cycles
```

Suspect retained objects: unbounded caches, unclosed listeners/SSE/WebSocket sessions, thread locals, or growing queues. Still not automatic proof of a leak—cache warm-up, batch jobs, or shifting workloads also grow live sets. Authorized heap dumps and retention graphs confirm.

**Bonus note:** flat heap paired with rising RSS points to Netty direct buffers, native allocations, thread stacks, JIT code cache, or memory-mapped files. `-Xmx` does not cap total process memory.

## 18. Java Flight Recorder Adds the Time Dimension

Thread dumps are snapshots; **JFR** records events continuously over an interval: CPU execution samples, monitor contention, thread parks, allocations, GC, network I/O, and other JVM events per configuration.

Example on JDK 21:

```bash
jcmd "$PID" JFR.check
jcmd "$PID" JFR.start \
  name=incident \
  settings=profile \
  duration=60s \
  filename=/tmp/incident.jfr
```

`settings=profile` captures more events than `default` with higher overhead; keep durations short and follow operational policy. If syntax varies on your JVM, run `jcmd "$PID" help JFR.start`.

Once the recording finishes:

```bash
jfr summary /tmp/incident.jfr
jfr print --events jdk.ExecutionSample,jdk.JavaMonitorEnter,jdk.GarbageCollection \
  /tmp/incident.jfr
```

Open in JDK Mission Control to examine timelines, hot methods, locks, and GC. Absence of an event in a recording **does not prove** the issue didn't happen: it may be disabled, below threshold, missed by sampling, or outside the capture window. JFR files can expose sensitive data in thread names, custom events, and paths—protect them carefully.

## 19. JFR and OS CPU Reveal What `RUNNABLE` Actually Means

**CPU-bound** is supported when:

```text
Repeated thread dumps: same thread RUNNABLE inside ReportService.sort
top -H: matching OS TID shows high CPU delta
JFR execution samples: hot method is ReportService.sort
GC: no pauses large enough to explain p99
```

**I/O wait** is supported when:

```text
Thread dumps: workers waiting on socket reads / JDBC pool
Per-thread CPU is low
JFR: thread park / socket events or slow downstream spans
GC: normal during incident window
```

This is an **evidence matrix**, not literal tool output. A `RUNNABLE` thread inside a native selector may still be waiting on network I/O; without CPU samples, never assume CPU-bound.

If OS threads run hot while JFR shows GC or JVM compiler/internal threads dominating, include GC/compiler/system overhead rather than blindly refactoring controller business code.

## 20. WebFlux/Reactor Netty: Why Is the Event Loop Sensitive to Blocking?

WebFlux on Reactor Netty uses **event-loop threads** for non-blocking I/O across many connections instead of dedicating one Java worker thread per request like traditional Servlet containers.

```text
Connections A, B, C
       |
       v
Reactor Netty EventLoop #1
       |
       +-- read/write callbacks
       +-- reactive operators
       +-- schedule work
       |
       +-- If blocking JDBC / Thread.sleep runs here:
             event loop stalls, other callbacks wait
```

Common thread names include `reactor-http-nio-1` or `reactor-http-epoll-2`, depending on transport and resource config. Event loops normally sit in `NioEventLoop.select`/`EPoll.wait` when idle; `RUNNABLE` there is not a bug.

A red flag is repeatedly catching stacks like:

```text
"reactor-http-nio-2"
    at java.lang.Thread.sleep(...)
    at com.example.LegacyClient.fetch(...)
    at reactor.core.publisher.MonoCallable.call(...)
```

If `reactor.netty.eventloop.pending.tasks` rises simultaneously and quick endpoints also slow down, **event-loop starvation** becomes a strong hypothesis to verify. Conversely, event loops sitting in `select`/`epoll` across all three dumps with low task backlog weakens the event-loop blocking hypothesis.

## 21. Separate WebFlux Example: Unsafe Blocking vs Offloaded Work

This is a **standalone project**, separate from the Spring MVC demo. Include only `spring-boot-starter-webflux` (no `starter-web` on the classpath) so the server runs on Reactor Netty.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') { useJUnitPlatform() }
```

**`src/main/java/com/example/reactivediag/ReactiveDiagApplication.java`:**

```java
package com.example.reactivediag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDiagApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDiagApplication.class, args);
    }
}
```

**`src/main/java/com/example/reactivediag/BlockingProbeController.java`:**

```java
package com.example.reactivediag;

import java.util.concurrent.TimeUnit;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class BlockingProbeController {
    private String legacyBlockingCall() {
        try {
            TimeUnit.MILLISECONDS.sleep(800);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
        return "done";
    }

    // Intentionally wrong: blocking work may run on the Netty event loop.
    @GetMapping("/demo/unsafe")
    public Mono<String> unsafe() {
        return Mono.fromSupplier(this::legacyBlockingCall);
    }

    // Proper direction when forced to call a blocking SDK.
    @GetMapping("/demo/offloaded")
    public Mono<String> offloaded() {
        return Mono.fromCallable(this::legacyBlockingCall)
                .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/demo/quick")
    public Mono<String> quick() {
        return Mono.just("quick");
    }
}
```

`Mono.fromSupplier` defers execution **without switching threads**; on a reactive server, a blocking supplier can occupy a Netty event loop. `subscribeOn(Schedulers.boundedElastic())` moves the blocking source onto a bounded scheduler suited for blocking calls. That **does not make the SDK/JDBC non-blocking**—you must still cap concurrent requests and check downstream pools.

## 22. Measuring Event-Loop Interference in Local Tests

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,metrics
```

Run:

```bash
./gradlew bootRun
curl -i http://127.0.0.1:8080/demo/unsafe
curl -i http://127.0.0.1:8080/demo/offloaded
curl -i http://127.0.0.1:8080/demo/quick
```

`/demo/unsafe` and `/demo/offloaded` return `done`; `/demo/quick` returns `quick`. Exact wall times are not byte-fixed.

To observe starvation, run **overlapping concurrent requests** locally: fire several `/demo/unsafe` calls while timing `/demo/quick`, then repeat with `/demo/offloaded`. Sequential calls never demonstrate event-loop interference. Capture thread dumps during the same window, plus `reactor.netty.eventloop.pending.tasks` if registered.

Expected trend: when unsafe blocking callbacks tie up the event loop, `/demo/quick` degrades alongside them. When properly offloaded, the event loop remains free to handle I/O while blocking tasks wait in `boundedElastic`. Numbers depend on CPU, scheduler, and transport—never assume a fixed latency threshold.

Never use these demo endpoints for production benchmarks or run heavy load against shared environments.

## 23. Reactor Netty Metrics: Verify Instrumentation Is Active

Metrics documented in Reactor Netty include reference names such as:

```text
reactor.netty.http.server.connections.active
reactor.netty.http.server.connections.total
reactor.netty.http.server.response.time
reactor.netty.http.server.errors
reactor.netty.eventloop.pending.tasks
```

Depending on Reactor Netty 1.1.x version and metrics setup, **not every metric appears automatically merely by adding Actuator**. You may need to enable Reactor Netty metrics/`LoopResources` instrumentation, Micrometer registries, and recorders explicitly. Check live runtime meter names rather than treating a 404 as proof that event loops don't exist.

With Spring Boot Actuator:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics
```

Only after confirming a meter exists, query `/actuator/metrics/<metric-name>`. Correlate alongside HTTP p99, process CPU, cgroup throttling, GC pauses, Netty direct buffer usage, and outbound client pending acquires.

**Rising pending tasks alone do not prove blocking code.** A huge I/O burst, event storm, scheduler overhead, or CPU throttling can also build queues. Pair with contemporaneous thread dumps and JFR to confirm callbacks are blocked.

## 24. `boundedElastic`, `subscribeOn`, and Scheduler Saturation

`boundedElastic` is one workaround for legacy blocking calls:

```java
Mono<Book> result = Mono.fromCallable(
        () -> blockingBookRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This is an **integration pattern** (`Book`, `blockingBookRepository`, and `id` defined by your app). If you call the repository **before constructing the `Mono`**, `.subscribeOn(...)` arrives too late—blocking already happened on the caller thread.

`boundedElastic` enforces finite threads and task queues. Funneling all WebFlux traffic into a blocking database can still saturate `boundedElastic`, spike p99, and exhaust the DB pool. Real fixes require concurrency bounds, timeouts/retry budgets, bulkheads, query optimization, or migrating to non-blocking I/O where justified.

Never confuse `publishOn` with `subscribeOn`: `publishOn` only switches execution context for downstream operators placed after it, never retroactively moving earlier blocking steps. Verify thread transitions via actual thread names/stacks rather than guessing from one line of code.

## 25. Why Adding Netty Event-Loop Threads May Not Solve the Problem

Some setups adjust the system property `reactor.netty.ioWorkerCount`. Reactor Netty normally defaults worker count to runtime CPU count with a version-dependent minimum. Bumping workers from 4 to 32 can **temporarily mask** a blocking call, yet blocking still stalls individual event loops while adding context-switch overhead.

Before changing worker counts:

1. Check thread dumps to see whether threads are stuck in blocking methods.
2. Switch to non-blocking clients or offload blocking sources.
3. Check CPU quota/throttling—adding workers under tight CPU caps helps nothing.
4. Inspect event-loop pending tasks, response times, active connections, and GC.
5. Load-test the exact same request mix before/after, checking throughput, p99, CPU, and errors.

Never create a fresh `LoopResources` per request; its lifecycle must be managed cleanly. Servers and clients can share default Reactor Netty event-loop resources inside the JVM.

## 26. Java 21 Virtual Threads and Choosing the Right Dump Tool

Spring Boot 3.3 enables Java 21 virtual threads via:

```properties
spring.threads.virtual.enabled=true
```

Boot switches supported auto-configured `AsyncTaskExecutor`s and schedulers to virtual threads. If custom executors or non-supported stacks exist, never assume every request runs on a virtual thread.

Traditional:

```bash
jcmd "$PID" Thread.print -l
```

does not give the full picture of all virtual threads. On Java 21 HotSpot, also use:

```bash
jcmd "$PID" Thread.dump_to_file -format=text /tmp/threads.txt
jcmd "$PID" Thread.dump_to_file -format=json /tmp/threads.json
```

Virtual-thread dumps can become huge and **do not include all lock/heap details of traditional dumps** in JDK 21. Protect dump files, capture deliberately, and check exact command syntax in your JDK runtime. On JDK 17, virtual-thread dump commands do not exist.

JFR event `jdk.VirtualThreadPinned` helps investigate pinning; in Java 21, blocking while holding a `synchronized` monitor can pin the carrier thread. Always check JFR evidence rather than blaming pinning for every slow virtual-thread call. Virtual threads never cure slow SQL or connection pool starvation.

## 27. CPU Throttling in Kubernetes Can Mimic Event-Loop Starvation

A tight CPU quota can cause:

- Event-loop pending tasks rising even with zero `Thread.sleep` calls.
- Tomcat workers progressing sluggishly, inflating p99.
- Concurrent GC competing with app threads for scarce CPU slices.
- Host CPU looking idle while the container cgroup is throttled.

Inspect: container CPU usage **against quota**, CFS throttled periods/time, `Runtime.availableProcessors()`, request throughput, and concurrency. A "40% process CPU" chart may use a **different denominator** than the container limit, misleading you into thinking 60% headroom remains.

If event-loop pending tasks are high while dumps show only `select`/`epoll`, investigate throttling and event volume. If GC pauses are tiny and threads aren't blocked while request queues spike in lockstep with CPU throttling intervals, the CPU-quota hypothesis beats "JVM heap is too small".

## 28. Pool and Downstream Bottlenecks: Waiting Outside the HTTP Worker

An MVC request may traverse:

```text
Tomcat worker
  -> Service
  -> Hikari connection lease
  -> SQL execution / DB transaction
  -> Outbound HTTP connection acquire
  -> Downstream response
```

Key pools:

| Component | Evidence |
| --- | --- |
| HikariCP | `hikaricp.connections.active`, `idle`, `pending`, `max` |
| Apache HttpClient 5 | Leased/available/pending per route |
| Reactor Netty HTTP client | Pending-acquire, active/idle connections |
| Tomcat | Busy/max worker count, accept backlog |
| App executors | Active/queued/rejected counts |
| Database | Slow queries, lock waits, transaction durations |

A stack frame in `HikariPool.getConnection` does not reveal **why connections ran out**—it could be an undersized pool, slow SQL, long transactions, holding a connection across external HTTP calls, or a connection leak. Form separate sub-hypotheses and cross-check traces and DB stats.

In reactive apps, synchronous JDBC offloaded onto `boundedElastic` can still starve Hikari; offloading merely shifts blocking from the event loop onto another pool. Never assume "Netty threads are no longer blocked" means the performance bottleneck is solved.

## 29. Build a Latency Timeline Before Drawing Conclusions

A 3.0-second p99 request might break down hypothetically as:

```text
Ingress / gateway waiting      0.5s
App dispatch                   0.1s
DB connection acquisition      0.7s
SQL execution                  1.2s
Serialization                  0.2s
Network response               0.3s
------------------------------------
Total                          3.0s
```

These numbers are illustrative only, not real measurements. **A thread dump captured while DB acquisition is happening does not prove Hikari caused all 3 seconds.** You need trace spans or stage metrics detailing each operation's budget.

Correlation requires synchronized clocks across JVMs, containers, proxies, and DBs, matching sanitized HTTP request/trace IDs and deploy revisions. Stop-the-world GC pauses stretch many traces simultaneously; JFR/GC timestamps distinguish GC pauses from a downstream spike.

Server-side observations can also differ from browser end-to-end durations, especially with async Servlets, WebFlux, and streaming. Never compare metrics across mismatched boundaries without stating so explicitly.

## 30. Confirming Hypotheses via Single-Variable Experiments

| Hypothesis | Staging/Canary Experiment | Metric Expected to Improve |
| --- | --- | --- |
| Blocked event loop | Replace blocking call with non-blocking/offload | Pending tasks and quick-route p99 drop |
| Tomcat worker saturation | Cut blocking duration, bound concurrency | Busy/queue drop, throughput rises |
| GC allocation pressure | Trim allocations at JFR hotspots | GC pauses and allocation rate drop |
| Hikari pool starvation | Fix leaks/SQL time, or tune pool after load test | Pending drops without overloading DB |
| Monitor contention | Narrow critical section | `BLOCKED` samples and lock wait drop |
| CPU throttling | Raise quota appropriately or cut CPU work | Throttled time and p99 drop |
| Slow downstream | Optimize query or HTTP dependency | Downstream span p99 and overall p99 drop |

Hold request mix, concurrency, deployment, JVM warm-up, and load-generator capacity constant; run enough repeats to filter noise. If a change fails to move **the predicted metric**, reject or revise the hypothesis. A prettier graph proves nothing if incoming load simply dropped at the same time.

## 31. Quick Diagnostic Matrix

| Thread Dump | GC / JFR | OS / Pool / Event Loop | Priority Hypothesis |
| --- | --- | --- | --- |
| Workers repeatedly waiting in `HikariPool.getConnection` | GC normal | Hikari pending rising, `active=max` | Pool acquisition contention |
| Many threads `BLOCKED` on same lock | JFR monitor wait rising | CPU may be low | Lock contention |
| Same thread `RUNNABLE` in algorithm | Hot JFR execution samples | High per-thread CPU | CPU-bound |
| Netty event loop inside `Thread.sleep`/JDBC | GC normal | Pending tasks rising | Event-loop blocking |
| Many requests stall simultaneously | Large GC pause at exact timestamp | JVM-wide latency | GC / safepoint contribution |
| Threads waiting on sockets | GC normal | Downstream p99 rising | External I/O bottleneck |
| No hot Java stack | GC normal | High cgroup throttling | CPU quota throttling |
| Post-GC live set climbs across windows | Allocation/retention evidence | RSS/GC pressure rising | Possible leak; investigate deeper |

**Never treat this matrix as final proof.** Multiple issues frequently overlap—for example, slow SQL causing Hikari pending and Tomcat saturation; trace the causal chain in order.

## 32. Common False Conclusions

**"RUNNABLE means 100% CPU."** False; selectors and network I/O can also appear `RUNNABLE`.

**"Lots of WAITING threads means deadlock."** False; idle executor workers waiting on queues are normal.

**"Heap grew, so there's a memory leak."** False; check post-GC live sets across equivalent workloads.

**"GC ran, so GC caused high p99."** False; normal GC pauses can be tiny.

**"One thread dump proves root cause."** False; capture multiple snapshots alongside metrics.

**"A WebFlux `Mono` can't run blocking code."** False; blocking suppliers can still execute on and stall the Netty loop.

**"Adding event loops fixes JDBC blocking."** False; blocking calls still stall whichever thread runs them.

**"Offloading to `boundedElastic` makes the database faster."** False; it only relocates where blocking waits happen.

**"Adding Tomcat threads always raises throughput."** False when DB, CPU, pools, queues, or downstreams are the limit.

**"JFR didn't record an event, so it didn't happen."** False; sampling, thresholds, and capture windows can miss events.

**"Actuator threaddump is safe to expose publicly because it holds no passwords."** False; stacks, threads, and diagnostics leak sensitive metadata.

**"Low CPU means the service isn't bottlenecked."** False when threads wait on locks, pools, or I/O, or when cgroups throttle CPU.

## 33. Security and Overhead of Diagnostics

Before running `Thread.print`, JFR, or heap dumps in environments with real users:

1. Verify the target JVM, authorization, purpose, and time window.
2. Agree on maximum acceptable overhead and whether JFR `profile` settings are safe.
3. Cap artifact disk size/retention and store in directories with restricted permissions.
4. Never expose `/actuator/threaddump` or `/actuator/heapdump` publicly.
5. Never paste raw heap dumps or JFR files into public chats/tickets: they can leak data paths, SQL/URLs, tokens, and PII.
6. Never turn on verbose wire logging cluster-wide just to inspect one slow request.
7. Weigh the invasiveness of `GC.class_histogram`/heap dumps when hunting leaks; never schedule them automatically every 5 seconds.
8. Revert debug settings after the incident and protect/purge artifacts per policy.

Actuator provides many endpoints, yet **usually only `health` is exposed over HTTP by default**; extra endpoints require explicit configuration and proper security. If you define a custom `SecurityFilterChain`, verify Actuator authorization explicitly instead of assuming auto-configured defaults apply.

## 34. Short Runbook for the First 15 Minutes of an Incident

**Minutes 0–3:** Record incident window, affected routes, throughput, p99/error rate, recent deploys/configs, JVM version, CPU limits, and MVC vs WebFlux stack.

**Minutes 3–6:** Collect `jvm.gc.pause`, heap/memory, process/container CPU, `jvm.threads.live`, Tomcat/Hikari/Netty metrics, and downstream spans. Verify which meters actually exist.

**Minutes 6–10:** Capture 2–3 thread dumps in the same window, noting timestamps and PID. Look for repeated stacks, locks, and pool waits. If CPU or lock contention remains unclear, take a short controlled JFR recording.

**Minutes 10–15:** Identify two independent pieces of evidence supporting one hypothesis and two pieces of potential counter-evidence; plan a single-variable test with guardrails and rollback.

Report template:

```text
Incident window: 14:00-14:10 +07
Affected route: /api/orders/{id}
Hypothesis: Tomcat requests are waiting for Hikari connection leases
Evidence 1: 3 dumps show workers at HikariPool.getConnection
Evidence 2: Hikari active=max and pending rises in same window
Counter-evidence: GC pauses stay low
Test: reduce long transactions / query time in staging
Before/after: compare p99, throughput, errors, pool pending
Conclusion: supported / rejected / inconclusive
```

This is an **investigation note template**, not real output. Recording `Counter-evidence` guards against confirmation bias. When signals conflict or data is missing, record **INCONCLUSIVE** instead of inventing a root cause.

## 35. Quick Commands and Review Questions

Bash/Linux with a verified `PID`:

```bash
jcmd -l
jcmd "$PID" VM.version
jcmd "$PID" help
jcmd "$PID" Thread.print -l > thread-1.txt
sleep 3
jcmd "$PID" Thread.print -l > thread-2.txt
sleep 3
jcmd "$PID" Thread.print -l > thread-3.txt

jstat -gcutil "$PID" 1000 10
jcmd "$PID" GC.heap_info

jcmd "$PID" JFR.start name=incident settings=profile \
  duration=60s filename=/tmp/incident.jfr
```

Java 21 virtual threads:

```bash
jcmd "$PID" Thread.dump_to_file -format=json /tmp/threads.json
```

Spring Boot Actuator on localhost in demos:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/jvm.gc.pause
curl -s http://127.0.0.1:8080/actuator/metrics/jvm.threads.live
```

**Review Questions:**

1. Is a `RUNNABLE` thread inside `EPoll.wait` definitely burning CPU? What extra metric is needed?
2. Why capture multiple thread dumps rather than a single snapshot?
3. Can a thread in `CountDownLatch.await` still hold another monitor?
4. How does `BLOCKED` on an intrinsic monitor differ from `WAITING` during a Hikari pool lease?
5. `jstat -gcutil` reports cumulative times; why compute deltas?
6. How does a normal GC sawtooth heap differ from a steadily rising post-GC live set?
7. Is a single 20 ms GC pause enough to explain a 3-second p99 spike?
8. Why can `Mono.fromSupplier(() -> jdbc())` block the event loop?
9. What does `subscribeOn(boundedElastic())` solve, and what does it not solve?
10. Why can event-loop pending tasks rise due to CPU throttling rather than blocking code?
11. What dump command do Java 21 virtual threads need beyond traditional `Thread.print`?
12. When many MVC workers wait on Hikari, why shouldn't you immediately enlarge the pool?
13. If JFR records zero instances of an event, can you rule out that hypothesis?
14. What must you prove before increasing `reactor.netty.ioWorkerCount`?
15. Which workload variables must stay constant during a canary comparison?
16. Why must heap dumps and JFR files be secured?
17. After fixing a bottleneck, why verify p99, throughput, errors, CPU, and GC together?
18. When should you report "insufficient evidence" instead of declaring a root cause?

## 36. Conclusion: Cross-Check Three Planes Instead of Guessing

To verify a web-runtime performance hypothesis, combine:

- **Thread dumps** to see what threads are doing and waiting on, especially across 2–3 snapshots.
- **GC metrics and unified logs** to quantify JVM GC/safepoint impact; not every allocation or heap growth is a leak.
- **Reactor Netty event-loop metrics and stacks** to catch callback blocking in WebFlux; in MVC, pair with Tomcat busy workers and pool waits.
- **OS/cgroup CPU, JFR, and downstream traces** to separate CPU-bound execution, I/O waits, lock contention, throttling, and GC.
- **Controlled single-variable before/after measurements** to move from correlation to causal proof.

A solid engineering conclusion answers: **where is the bottleneck, what time-aligned evidence confirms it, what fix was tested, how much did metrics change, and which competing hypotheses were ruled out?**

### Official References

- Spring Boot 3.3 — Actuator Metrics, JVM/Tomcat/HTTP: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Actuator Security/Endpoints: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Thread dump endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/threaddump.html
- Spring Boot 3.3 — Virtual Threads/Task Execution: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Oracle Java 21 — `jcmd`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 21 — `jstat`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstat.html
- Oracle Java 21 — GC Unified Logging: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java 21 — `jfr` command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java 21 — Virtual Threads and Dumps: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Oracle Java 21 — Garbage Collection Tuning: https://docs.oracle.com/en/java/javase/21/gctuning/
- Reactor Netty 1.1 — HTTP Server and Event-Loop Metrics: https://projectreactor.io/docs/netty/1.1.17/reference/index.html
- Project Reactor — Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html