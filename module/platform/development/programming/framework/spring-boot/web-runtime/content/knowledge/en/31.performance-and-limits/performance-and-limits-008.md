# Distinguishing Platform Thread Tuning, Virtual Threads, and the Reactive Model in Spring Boot

A web server can handle hundreds to thousands of concurrent requests, yet how each request waits on a database, HTTP client, filesystem, or CPU creates vastly different limits. In modern Java and Spring Boot, three approaches are commonly compared:

1. **Platform threads:** Java threads backed 1:1 by OS threads, typically managed in a **bounded pool** such as Tomcat's worker threads in Spring MVC.
2. **Virtual threads (Project Loom):** lightweight Java threads scheduled by the JVM onto a pool of carrier platform threads, fitting **synchronous, blocking I/O** coding styles when serving many concurrent waiting tasks.
3. **Reactive model (Spring WebFlux + Project Reactor):** applications express pipelines via **`Mono`/`Flux`**, non-blocking I/O, and event loops/schedulers, paired with a **demand/backpressure** protocol to regulate data flow.

Core insight: **virtual threads do not turn blocking APIs into reactive ones**, and **reactive is not simply "using more threads"**. Both can scale I/O-bound concurrency, yet neither creates CPU cores, database connections, memory, network bandwidth, or downstream capacity. For an application already running stably, tuning the platform thread pool and backing resources can yield better results than switching frameworks.

This lesson belongs to **Spring Boot - web-runtime → Performance and Limits**. The comparison targets **Spring Boot 3.3.13, Java 21, Spring MVC on embedded Tomcat, and Spring WebFlux on Reactor Netty**. Java 17 suffices for many MVC/WebFlux apps, while **virtual threads require Java 21+**. Examples include standalone Maven projects, real HTTP tests, a Java 21 program demonstrating I/O waits, and a benchmarking/profiling workflow. No single framework is declared universally fastest.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Explain **OS thread, Java platform thread, virtual thread, carrier thread, event loop, task, blocking I/O, non-blocking I/O, CPU-bound, and I/O-bound**.
- Analyze bottlenecks using **throughput (RPS), latency p50/p95/p99, concurrency, queue time, CPU, heap, GC, thread counts, and connection pools**.
- Know when to tune **`server.tomcat.threads.max`/`min-spare`**, accept queues, connection limits, connection/request timeouts, and downstream pools.
- Enable **`spring.threads.virtual.enabled=true`** on Java 21 with Spring Boot 3.3, verify **`Thread.currentThread().isVirtual()`** inside a controller, and understand JDK 21 pinning caveats.
- Explain why you **must not pool virtual threads**, avoid wrapping them in arbitrary semaphores, and still bound concurrency hitting databases and remote APIs.
- Implement **Spring MVC blocking** and **Spring WebFlux non-blocking** endpoints with identical HTTP contracts for comparison.
- Distinguish **`Mono`/`Flux`, subscribe, `publishOn`, `subscribeOn`, `Schedulers.boundedElastic`, backpressure, and cancellation**, and avoid calling `block()` or `Thread.sleep()` on event loops.
- Understand why adding **`spring-boot-starter-webflux`** to an app that already has **`spring-boot-starter-web`** does not automatically switch the server to WebFlux.
- Design controlled performance experiments without jumping to conclusions from a single run or `sleep`-only endpoints.
- Choose a concurrency model based on real I/O libraries, complexity, SLOs, operability, and migration cost.

## 2. First Identify the Workload

### 2.1. CPU-Bound and I/O-Bound Are Different Problems

**CPU-bound:** processing time is dominated by CPU execution—compression, encryption, heavy parsing, or image math. Once CPU saturates, adding threads or switching to virtual threads can increase context switching, contention, or memory without raising throughput.

**I/O-bound:** most wall-clock time is spent waiting on databases, networks, filesystems, or external APIs. While waiting, CPU may sit idle while a platform request thread stays occupied. Virtual threads or non-blocking reactive APIs lower the cost of holding many waiting tasks concurrently.

~~~text
Request A on a platform thread:
[CPU 5 ms] [waiting DB 200 ms] [CPU 5 ms]
             ^ thread remains occupied

Request A on a virtual thread:
[CPU 5 ms] [waiting DB 200 ms] [CPU 5 ms]
             ^ virtual thread typically unmounts,
               carrier can run another request

Request A with a reactive non-blocking client:
[CPU 5 ms] [async DB/network] [CPU callback 5 ms]
             ^ holds no worker thread while waiting;
               completion signal triggers next operator
~~~

This is a conceptual diagram. Virtual threads **do not always unmount** (pinning or native code can prevent it); reactive code **is not automatically non-blocking** if it calls JDBC, `Thread.sleep`, or `block()`.

### 2.2. Throughput, Latency, and Concurrency

- **Throughput/RPS:** requests completed per second under a given load.
- **Latency:** time experienced by a request from client or server perspective. Track **p50/p95/p99**, not just the average.
- **Concurrency:** requests/tasks simultaneously in-flight—computing, waiting on I/O, or waiting in queues.
- **Queue time:** time a request waits for a worker or connection before execution begins.
- **Utilization:** CPU, worker threads, DB pools, network connections, and memory.

By **Little's Law** in steady state, average in-flight requests approximate **arrival rate × time in system**:

\[
L = \lambda W
\]

If 200 requests/second average 0.2 seconds each, the system sustains roughly **40 in-flight requests**. That estimates concurrency—it does not mean you need 40 CPU cores or 40 DB connections, because requests may spend most of that time waiting.

**Choosing a thread model without measuring the workload is blind optimization.** Measure CPU, JDBC, HTTP client, queue, serialization, and lock times before changing models.

### 2.3. One Endpoint, Three Waiting Behaviors

| Model | How Waiting Requests Are Represented | Primary Risk |
| --- | --- | --- |
| MVC + platform threads | Holds a worker thread across blocking calls | Pool exhaustion; queueing; OS thread memory overhead |
| MVC + virtual threads | Holds a virtual thread; unmounted carrier serves other work | Carrier pinning, excessive in-flight tasks, downstream pool/socket overload |
| WebFlux + reactive clients | Signal/continuation pipeline; non-blocking I/O holds no dedicated thread | Blocking the event loop, oversized buffers, unbounded operator concurrency, harder context debugging |

## 3. Platform Threads: Traditional, Not Obsolete

### 3.1. What Is a Platform Thread?

A Java **platform thread** is normally a thin wrapper around an **OS thread**, carrying an OS stack and kernel scheduling cost. Platform threads handle both CPU and blocking work well, though they cannot scale without bound. Hence traditional web servers use **reusable pools** rather than spawning an OS thread per request.

In Servlet Spring MVC on embedded Tomcat, requests enter through a connector and run on a worker executor executing filters, `DispatcherServlet`, and controllers. When a controller invokes blocking JDBC or a synchronous HTTP client, that worker thread remains occupied until completion.

~~~text
Tomcat acceptor / network connector
              |
              v
Worker pool: [P1] [P2] [P3] ... [P16]
              |
              +-- P1 handles request A, awaits DB
              +-- P2 handles request B, awaits REST API
              +-- P3 handles request C, burns CPU
              ...
              |
Requests exceed serving capacity -> queueing / connection pressure
~~~

### 3.2. Key Tomcat Settings

In Spring Boot 3.3, an example lab cap:

~~~yaml
server:
  port: 8080
  tomcat:
    threads:
      max: 16
      min-spare: 4
    max-connections: 256
    accept-count: 100
~~~

- **`server.tomcat.threads.max`**: max worker threads in Boot's managed Tomcat platform thread executor.
- **`min-spare`**: minimum spare workers per executor; not a system-wide request limit.
- **`max-connections`**: connector connection limit; distinct from active requests and DB pool size.
- **`accept-count`**: requested OS accept queue depth once connector limits hit; actual behavior depends on OS/socket implementation.

Do not read **`max-connections=256`** as "Tomcat has 256 threads" or "256 requests run handlers simultaneously". Keep-alive connections can sit idle, and HTTP/2 multiplexes streams; thread pool size and request concurrency are different quantities.

When virtual threads are enabled in Boot, platform-thread settings like **`server.tomcat.threads.max`** no longer cap per-request concurrency in the same way. Other connector and network limits still apply and must be evaluated.

### 3.3. Tune in the Right Order

Before increasing `maxThreads`:
1. Measure CPU: if CPU sits at 100%, more threads can make it slower.
2. Measure Tomcat busy/current threads and request queue wait time.
3. Measure HikariCP active/idle/pending connections, slow DB queries, and lock waits.
4. Measure outbound HTTP client pools, timeouts, retries, and downstream error rates.
5. Measure memory, GC, filesystem, TLS, and serialization overhead.
6. Identify p95/p99 latency and the onset of saturation.
7. Only then adjust threads, `maxConnections`, `acceptCount`, or autoscaling.

For instance, if a service has 16 Tomcat workers and **8 DB connections**, raising Tomcat workers to 200 merely queues up 192 extra tasks waiting on the DB pool, inflating queues, memory, and timeouts. If the DB is the bottleneck, optimize queries, indexes, transactions, acquisition timeouts, and admission control instead of blaming Tomcat.

### 3.4. Raising Thread Pools Does Not Scale Throughput Linearly

When a request holds a worker for 300 ms while burning only 10 ms of CPU, higher concurrency can utilize idle CPU until the next bottleneck hits. Pushing it to 1,000 concurrent queries against an overloaded DB destabilizes the system.

Signs of over-tuning:
- p99 climbs sharply while throughput flattens;
- client timeouts and 503s increase;
- DB connection pool queues grow;
- excessive JVM threads and context switching;
- rising GC pauses and memory pressure;
- downstream rate limiters or circuit breakers tripping en masse.

## 4. Virtual Threads: Blocking Coding Style with Lightweight Threads

### 4.1. Java 21 Is the Minimum Requirement

Virtual threads became a standard feature in **Java 21 (JEP 444)**. A virtual thread is still an instance of **`java.lang.Thread`**, so familiar blocking idioms:

~~~java
Thread.currentThread();
Thread.sleep(250);
Thread.currentThread().isVirtual();
~~~

continue to work with the same programming style. The difference is that the JVM schedules virtual threads onto **carrier platform threads**, and on supported blocking operations, the virtual thread **unmounts** so the carrier can run another task.

~~~text
Virtual threads: V1 V2 V3 V4 V5 V6 ... V1000
                  \ | /  \ | /
Carrier threads:  C1     C2     C3 ...
                (platform/OS threads)
~~~

Never think 1,000 virtual threads equal 1,000 OS threads. The scheduler uses a bounded set of carriers; virtual threads can vastly outnumber carriers when mostly waiting on I/O.

### 4.2. Virtual Threads Scale Concurrency, Not CPU Speed

If each request needs 100 ms of actual CPU computation, virtual threads do not shrink those 100 ms—you still need CPU cores. If each request waits 500 ms on an external API, virtual threads let the server hold many waiting requests without dedicating an OS thread to each.

**Virtual threads still consume heap, stack chunks, `ThreadLocal`s, sockets, and dependency slots.** They are neither completely free nor infinitely scalable.

### 4.3. Do Not Pool Virtual Threads

The proper JDK 21 pattern is **one virtual thread per task**, e.g.:

~~~java
try (var executor =
        java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> {
        System.out.println(Thread.currentThread().isVirtual());
    }).get();
}
~~~

This Java 21 snippet prints:

~~~text
true
~~~

**Never build a fixed-size pool of 100 virtual threads like a traditional Tomcat worker pool.** That defeats lightweight per-task concurrency. To bound access to a dependency, use a **`Semaphore`, rate limiter, bulkhead, or connection pool** protecting that resource—do not pool threads solely to cap concurrency.

### 4.4. Standalone Java 21 Program: Platform vs Virtual Waiting

Create **`ThreadModelsMain.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadModelsMain {

    private static void run(
            String label, ExecutorService executor)
            throws Exception {

        long start = System.nanoTime();
        try (executor) {
            List<Future<Boolean>> futures = new ArrayList<>();

            for (int i = 0; i < 40; i++) {
                futures.add(executor.submit(() -> {
                    Thread.sleep(200);
                    return Thread.currentThread().isVirtual();
                }));
            }

            int virtualCount = 0;
            for (Future<Boolean> future : futures) {
                if (future.get()) {
                    virtualCount++;
                }
            }

            long elapsedMs =
                    (System.nanoTime() - start) / 1_000_000L;

            System.out.printf(
                "%s: completed=%d, virtual=%d, elapsedMs=%d%n",
                label, futures.size(), virtualCount, elapsedMs);
        }
    }

    public static void main(String[] args) throws Exception {
        run("platform-pool",
                Executors.newFixedThreadPool(4));

        run("virtual-per-task",
                Executors.newVirtualThreadPerTaskExecutor());
    }
}
~~~

Run with JDK 21:

~~~bash
javac --release 21 ThreadModelsMain.java
java ThreadModelsMain
~~~

Output has a **deterministic part**:

~~~text
platform-pool: completed=40, virtual=0, elapsedMs=<actual measured value>
virtual-per-task: completed=40, virtual=40, elapsedMs=<actual measured value>
~~~

The lines above show **output structure**, not literal stdout to assert verbatim: `elapsedMs` varies by machine, scheduling, GC, system load, and thread creation overhead. With 40 tasks sleeping 200 ms, a 4-worker fixed pool runs in roughly 10 waves, whereas virtual threads can wait concurrently. This solely illustrates **waiting concurrency**, not production HTTP performance—`Thread.sleep` differs from real databases and networks.

### 4.5. Pinning in Java 21

A virtual thread can become **pinned** to its carrier when blocking inside specific contexts. On **JDK 21**, classic causes include:
- blocking inside a **`synchronized` method or block**;
- certain native/foreign calls.

~~~java
private final Object lock = new Object();

// Illustrates a design flaw: holding a monitor during a long wait.
public void risky() throws InterruptedException {
    synchronized (lock) {
        Thread.sleep(250);
    }
}
~~~

This is a **method snippet**, not a standalone class. On JDK 21, frequent long-lived pinning ties up carrier threads and hurts throughput. Moreover, that lock **serializes every caller** regardless of whether platform or virtual threads are used.

**Do not conclude `synchronized` is always bad.** Short pure-CPU critical sections are fine. Where `synchronized` spans long I/O waits, move I/O outside the lock, narrow the critical section, or use **`ReentrantLock`** appropriately. Always verify thread safety against races/deadlocks rather than replacing `synchronized` mechanically.

**JDK version matters:** JDK 24+ improved monitor-related pinning (JEP 491), though other limits and lock contention remain. Because this lab targets **Java 21**, account for Java 21 caveats rather than projecting JDK 24/25 behavior backward.

### 4.6. Debugging Pinning with JFR

Capture a JFR recording while running the MVC virtual-thread demo:

~~~bash
java -XX:StartFlightRecording=filename=vt.jfr,settings=profile,dumponexit=true \
  -jar target/mvc-thread-demo-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true
~~~

After generating load, stop the app normally to flush the JFR file, then inspect:

~~~bash
jfr print --events jdk.VirtualThreadPinned vt.jfr
~~~

On JDK 21, **`jdk.VirtualThreadPinned`** highlights long pins (default profile threshold is typically 20 ms). Zero events **does not prove all VT usage is optimal**; thresholds, settings, workload, or recording duration might simply miss them. You can also dump virtual threads with **`jcmd`** on supported runtimes:

~~~text
jcmd <PID> Thread.dump_to_file -format=json threads.json
~~~

This is a **sample command**—substitute the real PID. Thread dumps and JFR files can reveal internal details; store and share them under security policies.

### 4.7. `ThreadLocal`, MDC, and Virtual Threads

Virtual threads support `ThreadLocal`, yet a `ThreadLocal` cache replicated across hundreds of thousands of virtual threads costs far more than 20 reused platform workers. Avoid caching large buffers, JDBC connections, or user secrets in per-request `ThreadLocal`s. Scope and clean up MDC tracing and Spring Security contexts properly after every request instead of assuming threads are pooled and reused.

## 5. How Does Spring Boot 3.3 Enable Virtual Threads?

### 5.1. Exact Configuration

On **Java 21+**, Spring Boot 3.3 supports:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true
~~~

- **`spring.threads.virtual.enabled=true`** tells Boot to use virtual threads across supported Boot integrations, including supported Servlet request executors.
- **`spring.main.keep-alive=true`** keeps the JVM alive when only daemon threads remain, important for apps running `@Scheduled` or background tasks on virtual threads.
- **It does not convert every JVM thread into a virtual thread.** Carrier threads, Netty event loops, JVM internal threads, third-party pools, and custom executors remain platform threads.

Spring Boot docs note that with virtual threads enabled, several traditional **thread-pool** properties no longer behave the same way because virtual threads schedule onto shared carriers. Raising `server.tomcat.threads.max` will not scale virtual request task counts in the old way.

### 5.2. Tomcat Servlet + Virtual Threads

Spring Boot 3.2+ integrates virtual threads with Tomcat and Jetty; Servlet HTTP request handling runs on virtual threads. Verify directly inside a controller with:

~~~java
boolean virtual =
        Thread.currentThread().isVirtual();
~~~

**Never assume the whole app uses VT simply because the JVM is Java 21.** The property must be enabled, the web runtime must support it without custom executor/connector overrides, and real HTTP tests must confirm it.

### 5.3. `@Async`, `@Scheduled`, and Task Executors

When virtual threads are enabled, Boot's auto-configured **`applicationTaskExecutor`** switches to virtual-thread execution, affecting scheduling too. However, if your application declares its own custom **`Executor`**, **`ThreadPoolTaskExecutor`**, or scheduled executor bean, inspect that bean—Spring Boot will not override every user-defined executor.

**`Thread.sleep`** on a virtual thread lets the carrier do other work, yet it remains **blocking-style Java code** keeping the virtual task/request open. Do not wrap everything in `@Async` solely to dodge MVC worker pools without bounding latency, cancellation, and in-flight task counts.

### 5.4. Watch Out for Daemon Threads and Keep-Alive

Virtual threads are always daemon threads in JDK 21. If an app has only virtual threads left running and zero non-daemon threads, the JVM can exit. Boot recommends **`spring.main.keep-alive=true`** when relying on virtual threads—especially relevant for job/scheduler services, even though a standard Tomcat web app usually keeps non-daemon threads active.

## 6. Reactive WebFlux: Optimizing via Non-Blocking Composition

### 6.1. Reactor Does Not Dedicate a Thread per Request

WebFlux on Reactor Netty uses a relatively small pool of **event-loop threads** to drive network events. Handlers return **`Mono<T>`** (0 or 1 item) or **`Flux<T>`** (0..N items). Reactor builds a processing graph, registers callbacks, and reacts to I/O completion signals rather than blocking a platform worker thread while waiting.

~~~text
Netty event loop
    |
    +-- HTTP request A -> builds Mono/Flux pipeline
    |                        |
    |                        +-- async I/O pending, thread released
    |
    +-- HTTP request B -> builds Mono/Flux pipeline
    |
    +-- I/O A completes -> onNext/onComplete signal
                             |
                             v
                       serialization/response
~~~

**Not every operator runs on the event loop:** Reactor provides schedulers like `parallel` and `boundedElastic`; sources plus `publishOn`/`subscribeOn` decide where operators execute. Reactive ≠ async magic; it demands genuinely non-blocking I/O libraries.

### 6.2. `Mono`/`Flux` and Reactive Streams Backpressure

- **`Mono<T>`**: publisher emitting 0 or 1 value, or an error signal.
- **`Flux<T>`**: publisher emitting 0..N values, or an error signal.
- **Subscribers** subscribe to publishers and signal **`request(n)`**: how many items they are ready to receive.
- **Backpressure** lets downstream consumers regulate upstream emission rate; it is not a service-wide HTTP rate limiter and does not automatically shrink database queries unless coded to cooperate.
- **Cancellation** terminates subscriptions and releases resources if operators/drivers support it.
- **Error/completion** are stream signals, distinct from throwing unchecked exceptions out of a blocking controller method.

Example:

~~~java
Flux.range(1, 100)
    .map(n -> n * 2)
    .take(5);
~~~

This **explanatory snippet** has no subscriber, so it only describes a pipeline; upon subscribing, `take(5)` limits how many items the consumer requests. Even then, upstream/network work only cancels immediately if the underlying driver supports cancellation.

### 6.3. `block()` Does Not Turn a Library Non-Blocking

Inside a WebFlux controller running on a Netty event loop, code like:

~~~java
Thread.sleep(250);             // Blocks the event loop.
webClient.get()
    .uri("/api/data")
    .retrieve()
    .bodyToMono(String.class)
    .block();                    // Blocking bridge at the wrong layer.
~~~

is an **anti-pattern** in reactive handlers. Reactor throws **`IllegalStateException`** when `block()` is called on certain non-blocking scheduler threads, aside from stalling the event loop. Never "fix" this by shifting every operator onto an unbounded scheduler, which defeats reactive architecture.

### 6.4. Offloading Legacy Blocking Calls to `boundedElastic`

When forced to invoke a synchronous DAO/SDK inside a reactive pipeline:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> legacyClient.fetch())
    .subscribeOn(Schedulers.boundedElastic());
~~~

This is a **snippet** omitting `Result`, `legacyClient`, and imports. **`Schedulers.boundedElastic()`** uses bounded workers and queues to isolate blocking work from event loops, yet **blocking calls still tie up `boundedElastic` workers** rather than becoming reactive I/O. Prefer switching to R2DBC or reactive HTTP drivers for true end-to-end non-blocking I/O when feasible.

**Do not confuse `boundedElastic` with virtual-thread-per-task.** Starting in Reactor 3.6+, `boundedElastic` offers an option to back workers with Java 21 virtual threads via the system property **`reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true`**; that is a separate Reactor switch, not automatic just because `spring.threads.virtual.enabled` is set.

### 6.5. `publishOn` and `subscribeOn`

**`subscribeOn(scheduler)`** affects where subscription and upstream source work run, whereas **`publishOn(scheduler)`** switches execution context for downstream operators placed after it. Neither guarantees backpressure nor cuts I/O latency by itself:

~~~java
Mono.fromCallable(() -> legacyClient.fetch())
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::transformResult);
~~~

This snippet will not compile standalone without `legacyClient` and `transformResult`. Measure `transformResult`'s CPU cost and verify scheduler suitability; avoid gratuitous `publishOn` hops that merely add context switching.

### 6.6. Reactive Concurrency Still Needs Bounds

A WebFlux pipeline firing 100,000 HTTP requests at once can exhaust sockets, hit rate limits, or blow memory. With `Flux.flatMap`, pass an explicit concurrency limit when appropriate:

~~~java
Flux.fromIterable(ids)
    .flatMap(
        id -> webClient.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(Item.class),
        16);
~~~

This **snippet requires `ids`, `webClient`, and `Item`**. The `16` parameter is an **example concurrency cap**, not a universal optimum. You still need connection pools, timeouts, rate limiters, retry budgets, batching, and real backpressure. Avoid unbounded `onBackpressureBuffer`, which can grow heap indefinitely.

## 7. Decision Matrix: Which Model Should You Pick?

| Criterion | MVC + Platform | MVC + Virtual | WebFlux Reactive |
| --- | --- | --- | --- |
| Minimum Java | Per Spring Boot (Boot 3: Java 17) | **Java 21+** | Boot 3: Java 17+ |
| Programming style | Imperative, blocking | Imperative, blocking | Publisher/async, non-blocking |
| Typical HTTP runtime | Tomcat/Servlet worker pool | Tomcat/Servlet with virtual request threads | Reactor Netty event loops |
| Blocking JDBC/SDK I/O | Native fit, holds worker | Native fit, virtual task can unmount | Must offload to `boundedElastic` or replace with reactive driver |
| Non-blocking R2DBC/`WebClient` | Can call reactive client, yet servlet isn't fully reactive | Same | Native end-to-end fit |
| CPU-heavy operations | Bounded by CPU/workers | Does not add CPU | Keep off event loops; offload appropriately |
| Backpressure API | Usually controlled via pools/queues | Controlled via bulkheads/resource limits | Reactive Streams demand, operator concurrency/buffers |
| Stack trace debugging | Straight-line, easy to read | Straight-line, many tasks | Async boundaries and Reactor `Context` |
| Major failure modes | Worker starvation, queueing | JDK 21 pinning, downstream overload | Event-loop blocking, buffer blowup |
| Migration cost | Low for existing MVC apps | Often much lower than a WebFlux rewrite | Higher if codebase is blocking today |
| Throughput/latency | Depends on workload and tuning | Depends on workload, pinning, and resources | Depends on non-blocking pipeline and backpressure |

**There is no universal ranking.** For CPU-bound workloads, neither virtual threads nor reactive adds cores. If an app primarily awaits blocking JDBC, MVC + virtual threads on JDK 21+ is worth testing before rewriting everything to WebFlux. If the system already relies on reactive drivers and streaming, WebFlux shines at async composition. If traffic is moderate and platform-thread MVC meets SLOs, prioritize tuning and maintainability.

## 8. Why Two Separate Spring Boot Projects When Comparing?

Spring Boot 3.3 selects **Spring MVC** whenever both **`spring-boot-starter-web`** and **`spring-boot-starter-webflux`** appear on the classpath, letting MVC apps use reactive `WebClient`. Adding the WebFlux starter **does not automatically switch the server to reactive**. Therefore the lab separates them:

~~~text
performance-model-lab/
  mvc-thread-demo/
     pom.xml
     src/main/java/com/example/mvc/
         MvcThreadApplication.java
         WaitController.java
     src/main/resources/application.yml
     src/test/java/com/example/mvc/
         PlatformThreadHttpTest.java
         VirtualThreadHttpTest.java

  webflux-reactive-demo/
     pom.xml
     src/main/java/com/example/reactive/
         ReactiveApplication.java
         ReactiveWaitController.java
     src/main/resources/application.yml
     src/test/java/com/example/reactive/
         ReactiveWaitHttpTest.java
         ReactorDelayTest.java

  LocalLoadProbe.java
~~~

The **MVC project** uses **`spring-boot-starter-web`** and runs twice via platform/virtual config without Java code edits. The **Reactive project** uses only **`spring-boot-starter-webflux`**, running Reactor Netty and `Mono.delay`. **`LocalLoadProbe`** is a standalone Java 21 program targeting one running server at a time.

Never run both MVC and Reactive simultaneously on port 8080. Java 21 is required across the lab for virtual-thread checks.

## 9. MVC Project: Platform or Virtual Threads

### 9.1. `mvc-thread-demo/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-thread-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 9.2. `MvcThreadApplication.java`

**`src/main/java/com/example/mvc/MvcThreadApplication.java`**

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcThreadApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcThreadApplication.class, args);
    }
}
~~~

### 9.3. `WaitController.java` — Same Blocking Endpoint

**`src/main/java/com/example/mvc/WaitController.java`**

~~~java
package com.example.mvc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WaitController {

    public record WaitReply(
            long simulatedWaitMs,
            boolean virtualThread,
            String threadName) {
    }

    @GetMapping("/wait")
    public WaitReply waitFor(
            @RequestParam(defaultValue = "250") long ms)
            throws InterruptedException {

        long bounded = Math.max(0L, Math.min(ms, 2000L));

        // Illustrates WAIT time only, not real I/O.
        Thread.sleep(bounded);

        Thread requestThread = Thread.currentThread();
        return new WaitReply(
                bounded,
                requestThread.isVirtual(),
                requestThread.getName());
    }
}
~~~

In **platform mode**, requests run on Tomcat platform worker threads such as `http-nio...` with **`virtualThread=false`**. In **virtual mode** on a supported Spring Boot/embedded Tomcat setup, the controller runs on a virtual thread with **`virtualThread=true`**. Virtual thread names vary or may be empty—never hardcode them in assertions.

`Thread.sleep` is a blocking-style wait simulating I/O delay. **Never expose query-controlled delay endpoints in production**: attackers can abuse them to exhaust in-flight limits, memory, and workers. For real performance testing, replace sleep with real downstream I/O inside an isolated test environment.

### 9.4. `application.yml`

**`src/main/resources/application.yml`**

~~~yaml
spring:
  application:
    name: mvc-thread-demo
  main:
    keep-alive: true

server:
  port: 8080
  tomcat:
    threads:
      max: 16
      min-spare: 4
    max-connections: 256
    accept-count: 100

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
~~~

We **omit `spring.threads.virtual.enabled` from the file** so we can toggle it via CLI flags. A 16-worker pool creates easily observable contention in platform mode. Once virtual threads are enabled, `threads.max` no longer caps request virtual threads the same way; external resource limits still remain critical.

Management metrics are exposed only for the localhost lab; never expose Actuator openly in production.

### 9.5. Running MVC Platform-Thread Mode

Inside `mvc-thread-demo`:

~~~bash
mvn clean package
java -jar target/mvc-thread-demo-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=false
~~~

In another terminal:

~~~bash
curl -i "http://localhost:8080/wait?ms=250"
~~~

HTTP **200**, response structure:

~~~json
{
  "simulatedWaitMs": 250,
  "virtualThread": false,
  "threadName": "http-nio-8080-exec-1"
}
~~~

**`threadName` is illustrative only**, not guaranteed literal stdout—JVM, connector, and load affect it. What matters is `virtualThread=false`.

### 9.6. Running MVC Virtual-Thread Mode

Stop the platform-mode process, then run:

~~~bash
java -jar target/mvc-thread-demo-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true
~~~

Call:

~~~bash
curl -i "http://localhost:8080/wait?ms=250"
~~~

Example structure:

~~~json
{
  "simulatedWaitMs": 250,
  "virtualThread": true,
  "threadName": ""
}
~~~

Virtual thread names may differ or be blank—do not assert a fixed name. **The flipped boolean** proves the request handler ran on a virtual thread under this configuration. That **does not prove virtual mode is faster**: measure throughput and latency under identical workload and resource caps.

### 9.7. Why Use One App for Both Modes?

Holding POM, controller, serialization, and HTTP responses constant isolates the server execution model. Even so, comparing two processes run at different times still sees noise from CPU load, JIT, GC, network, and warm-up. Repeat trials, alternate mode order, and capture metrics. **Platform `max=16`** creates a deliberately narrow test cap—do not generalize it as representative of all Tomcat configurations.

## 10. MVC HTTP Integration Tests: Do Not Rely Only on `MockMvc`

**`MockMvc`** does not dispatch requests through Tomcat's real worker executor. Testing `Thread.currentThread().isVirtual()` in `MockMvc` often tests the **JUnit caller thread**, not the HTTP server thread. Comparing thread models requires **`@SpringBootTest(webEnvironment=RANDOM_PORT)`** and real HTTP requests.

### 10.1. `PlatformThreadHttpTest.java`

**`src/test/java/com/example/mvc/PlatformThreadHttpTest.java`**

~~~java
package com.example.mvc;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.threads.virtual.enabled=false")
class PlatformThreadHttpTest {

    @LocalServerPort
    int port;

    @Test
    void mvcUsesPlatformWorkerThreads() throws Exception {
        URI uri = URI.create(
                "http://localhost:" + port + "/wait?ms=0");
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> response =
                HttpClient.newHttpClient().send(
                        request,
                        HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        JsonNode body = new ObjectMapper()
                .readTree(response.body());
        assertEquals(0L, body.path("simulatedWaitMs").asLong());
        assertFalse(body.path("virtualThread").asBoolean());
    }
}
~~~

### 10.2. `VirtualThreadHttpTest.java`

**`src/test/java/com/example/mvc/VirtualThreadHttpTest.java`**

~~~java
package com.example.mvc;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.threads.virtual.enabled=true")
class VirtualThreadHttpTest {

    @LocalServerPort
    int port;

    @Test
    void mvcUsesVirtualRequestThreads() throws Exception {
        URI uri = URI.create(
                "http://localhost:" + port + "/wait?ms=0");
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> response =
                HttpClient.newHttpClient().send(
                        request,
                        HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        JsonNode body = new ObjectMapper()
                .readTree(response.body());
        assertEquals(0L, body.path("simulatedWaitMs").asLong());
        assertTrue(body.path("virtualThread").asBoolean());
    }
}
~~~

The two tests boot separate Spring `ApplicationContext`s due to distinct properties. They verify **mode correctness**, not RPS. Random ports avoid conflicts with an app already running on port 8080.

If run on Java 17, the virtual test fails because the feature requires **Java 21+**. Check:

~~~bash
java -version
mvn -version
mvn test
~~~

If tests fail due to port/config/connector overrides, inspect the actual Boot web server and classpath rather than assuming `true` from metadata.

## 11. Standalone Reactive WebFlux Project

### 11.1. Differs from MVC at the Dependency Level

For WebFlux on Netty, build a separate project with only **`spring-boot-starter-webflux`**. Never include **`spring-boot-starter-web`** in the same lab project, because Boot 3.3 selects Spring MVC whenever both are on the classpath.

### 11.2. `webflux-reactive-demo/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-reactive-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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

### 11.3. `ReactiveApplication.java`

**`src/main/java/com/example/reactive/ReactiveApplication.java`**

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
~~~

### 11.4. `ReactiveWaitController.java`

**`src/main/java/com/example/reactive/ReactiveWaitController.java`**

~~~java
package com.example.reactive;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveWaitController {

    public record WaitReply(
            long simulatedWaitMs,
            String strategy,
            boolean virtualThread) {
    }

    @GetMapping("/wait")
    public Mono<WaitReply> waitFor(
            @RequestParam(defaultValue = "250") long ms) {

        long bounded = Math.max(0L, Math.min(ms, 2000L));

        return Mono.delay(Duration.ofMillis(bounded))
                .map(ignored -> new WaitReply(
                        bounded,
                        "mono-delay",
                        Thread.currentThread().isVirtual()));
    }
}
~~~

**Why is `Mono.delay` non-blocking?** The controller returns a `Publisher` immediately; the runtime registers a timer and executes the mapping callback only when the timer emits. It **does not call `Thread.sleep`** to hold a worker for 250 ms. The `Mono.delay` callback typically executes on a **Reactor scheduler**, not necessarily the Netty event loop; thus the `virtualThread` boolean and thread name **do not capture how Reactor Netty uses its event loops**.

**A timer-only simulation** does not exercise non-blocking database or HTTP clients. Production demands reactive drivers, proper backpressure, timeouts, and end-to-end cancellation semantics.

### 11.5. `application.yml`

**`src/main/resources/application.yml`**

~~~yaml
spring:
  application:
    name: webflux-reactive-demo

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
~~~

Do not enable `spring.threads.virtual.enabled` in the reactive project: the aim is testing the default WebFlux/Netty model without creating an unintended hybrid. Reactive schedulers can run on platform threads here; **non-blocking WebFlux does not require virtual threads**.

### 11.6. Running WebFlux

Inside `webflux-reactive-demo`:

~~~bash
mvn clean package
java -jar target/webflux-reactive-demo-0.0.1-SNAPSHOT.jar
~~~

Stop the MVC app on port 8080 first. Call:

~~~bash
curl -i "http://localhost:8080/wait?ms=250"
~~~

Expected HTTP 200 response structure:

~~~json
{
  "simulatedWaitMs": 250,
  "strategy": "mono-delay",
  "virtualThread": false
}
~~~

`virtualThread` in this WebFlux lab is typically `false` on the default Reactor scheduler, though that does not mean Netty/an entire app could never use VT under another setup. **`strategy=mono-delay`** is the key distinction here.

### 11.7. `ReactiveWaitHttpTest.java`

**`src/test/java/com/example/reactive/ReactiveWaitHttpTest.java`**

~~~java
package com.example.reactive;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveWaitHttpTest {

    @LocalServerPort
    int port;

    @Test
    void nonBlockingTimerReturnsJson() throws Exception {
        URI uri = URI.create(
                "http://localhost:" + port + "/wait?ms=0");
        HttpRequest request =
                HttpRequest.newBuilder(uri).GET().build();

        HttpResponse<String> response =
                HttpClient.newHttpClient().send(
                        request,
                        HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode body = new ObjectMapper()
                .readTree(response.body());
        assertEquals(0L, body.path("simulatedWaitMs").asLong());
        assertEquals("mono-delay",
                body.path("strategy").asText());
    }
}
~~~

### 11.8. `ReactorDelayTest.java` — Virtual-Time Test

**`src/test/java/com/example/reactive/ReactorDelayTest.java`**

~~~java
package com.example.reactive;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorDelayTest {

    @Test
    void virtualTimeTestsDelayWithoutRealWaiting() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofHours(1)))
            .expectSubscription()
            .thenAwait(Duration.ofHours(1))
            .expectNext(0L)
            .verifyComplete();
    }
}
~~~

**`StepVerifier.withVirtualTime`** swaps in a virtual scheduler clock during the test so you can verify timer behavior without waiting an actual hour. This is **Reactor Test's virtual time**, **completely unrelated to Java 21 virtual threads**. They share the word "virtual" with zero relation.

Run:

~~~bash
mvn test
~~~

**The two Spring Boot projects exercise two separate HTTP server pipelines**, and these tests prove endpoint contracts rather than **performance benchmarks**.

## 12. Java 21 Load Probe for All Three Modes

This standalone Java tool lets you test controlled concurrency on **localhost**. It uses a **fixed client-side platform executor** to send concurrent HTTP requests, keeping client behavior identical across all server modes. All latencies are client-side, combining queueing, connection setup, network, and server response—it **does not isolate pure server processing time**.

Create **`LocalLoadProbe.java`** outside both Maven projects:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class LocalLoadProbe {

    record Sample(int status, long elapsedMs) { }

    public static void main(String[] args) throws Exception {
        String target = args.length > 0
                ? args[0]
                : "http://localhost:8080/wait?ms=250";

        int total = args.length > 1
                ? Integer.parseInt(args[1])
                : 200;

        int concurrency = args.length > 2
                ? Integer.parseInt(args[2])
                : 32;

        URI uri = URI.create(target);
        if (!List.of("localhost", "127.0.0.1")
                    .contains(uri.getHost())
                || total < 1 || total > 500
                || concurrency < 1 || concurrency > 100) {
            throw new IllegalArgumentException(
                "Use localhost, 1..500 requests, 1..100 workers");
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        long allStart = System.nanoTime();
        List<Future<Sample>> futures = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newFixedThreadPool(concurrency)) {

            for (int i = 0; i < total; i++) {
                futures.add(executor.submit(() -> {
                    long start = System.nanoTime();
                    int status = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding())
                        .statusCode();

                    long elapsedMs =
                        (System.nanoTime() - start) / 1_000_000L;

                    return new Sample(status, elapsedMs);
                }));
            }

            List<Long> times = new ArrayList<>();
            int ok = 0;

            for (Future<Sample> future : futures) {
                Sample sample = future.get();
                if (sample.status() == 200) {
                    ok++;
                }
                times.add(sample.elapsedMs());
            }

            Collections.sort(times);
            int p95Index =
                Math.max(0, (int) Math.ceil(times.size() * 0.95) - 1);

            long wallMs =
                (System.nanoTime() - allStart) / 1_000_000L;

            System.out.printf(
                "total=%d ok=%d errors=%d wallMs=%d p95Ms=%d%n",
                total, ok, total - ok,
                wallMs, times.get(p95Index));
        }
    }
}
~~~

**Intentional limits:** restricted to localhost and at most 500 requests / 100 workers to prevent unapproved load testing against external systems. Run only on environments you are authorized to test, never production. Results represent **closed-loop client load**, and p95 includes client queueing; this does not replace k6, wrk2, Gatling, JMeter, or open-loop load testing.

Compile and run on JDK 21:

~~~bash
javac --release 21 LocalLoadProbe.java
java LocalLoadProbe "http://localhost:8080/wait?ms=250" 200 32
~~~

Output format:

~~~text
total=200 ok=200 errors=0 wallMs=<machine-dependent> p95Ms=<machine-dependent>
~~~

If server timeouts or connection failures occur, `Future.get()` throws `ExecutionException` and terminates rather than summarizing errors cleanly; always record those failures rather than **hiding failed requests to flatter RPS**. Serious benchmarks require tools with latency histograms, warm-up, constant arrival rates, coordinated-omission correction, ramp-up, and error breakdowns.

## 13. Controlled Comparison Plan

### 13.1. Three Modes to Run

1. **MVC + platform**: run `mvc-thread-demo` with `spring.threads.virtual.enabled=false`.
2. **MVC + virtual**: stop the old process and run the same JAR with `spring.threads.virtual.enabled=true`.
3. **WebFlux**: stop MVC and run `webflux-reactive-demo` using only `spring-boot-starter-webflux`.

For each mode, target the same **`GET /wait?ms=250`** URL, same request count/concurrency, machine, JDK, and heap/resource limits where possible. Enable **`/actuator/metrics`** in the lab to inspect request timings plus Tomcat/Netty/JVM metrics.

### 13.2. Controlling Benchmark Noise

- **Warm up** first: JIT compilation, class loading, and connection setup slow down the initial run.
- **Repeat multiple rounds**, interleaving mode order rather than trusting one run.
- **Fix heap, CPU limits, GC, network path, and client settings**.
- **Measure p95/p99 + throughput + error rate**, never p50 alone.
- **Monitor CPU/GC, live threads, queues, and connection pools**, not only latency.
- **Keep mock delays equal**, while recognizing `sleep` timers do not reflect real DB/JDBC behavior.
- **Never cripple the platform worker pool and claim the competing technology is inherently superior**: you might simply be measuring an artificially tiny platform pool.
- **Check both client and server concurrency**: a 32-worker client pool cannot expose server limits at 1,000 in-flight requests.
- **Never ignore HTTP 5xx/timeouts**; throughput only counts alongside success rate and SLOs.

### 13.3. Lab Scenarios

| Scenario | Objective | What to Expect (Not a Guarantee) |
| --- | --- | --- |
| 50 requests, concurrency 4, wait 250 ms | Light load without server saturation | All three modes perform similarly; minor overhead differences |
| 200 requests, concurrency 32, wait 250 ms, MVC `maxThreads=16` | Expose platform-mode worker limit | Virtual / `Mono.delay` hold many I/O waits without consuming 32 platform worker threads |
| 200 requests, concurrency 32, wait 0 ms | Negligible waiting | Do not expect virtual/reactive speedups; overhead may differ |
| Real CPU computation, high concurrency | Measure CPU saturation | All modes hit CPU core limits; VT adds no CPU capacity |
| Downstream DB pool 8 connections | Inspect resource bottlenecks | Higher concurrency stalls DB throughput; queueing/timeouts still occur |
| Rate-limited HTTP downstream | Inspect overload behavior | Bulkheads, rate limiting, and backoff are required in all models |

**Trial values are local lab suggestions only**, not production configs or pre-measured benchmarks. Never claim an exact RPS figure for any mode without running it on the target environment.

### 13.4. Distinguishing Response Time from Service Time

In platform mode, once Tomcat's worker pool fills, requests wait in the server connector/executor before the controller even starts. `LocalLoadProbe` measures from client send to response receipt, so high latency reflects **queue + service**.

In virtual mode, requests may enter the handler sooner yet stall at the DB pool. In reactive mode, the pipeline may hold no worker thread while queueing on connection pools or operator buffers. Isolating the true bottleneck requires stage-level tracing and metrics.

## 14. Optimizing Resource Pools Under Each Model

### 14.1. JDBC and HikariCP

JDBC is a blocking API. With platform threads, workers stay held during queries. With virtual threads, some JDBC blocking I/O can unmount the carrier, yet **the HikariCP pool remains bounded** and the DB executes finite concurrent queries. Never raise `maximumPoolSize` recklessly: the DB server pays connection, thread, transaction-memory, and lock-contention costs.

With 10 DB connections and 1,000 concurrent virtual requests, hundreds of requests **wait to acquire a connection**. Cheap threads do not speed up the DB. Enforce admission control, query optimization, timeouts, and rate limits.

### 14.2. Reactive R2DBC

WebFlux + R2DBC suits non-blocking database access where drivers and frameworks support it. Even R2DBC has connection pools, buffer limits, and distinct transaction semantics. Never assume a reactive driver is automatically faster than JDBC. For codebases heavily invested in synchronous JPA/Hibernate/JDBC, rewriting to WebFlux adds complexity that may not pay off.

### 14.3. HTTP Client Calls

- **MVC platform/virtual**: synchronous `RestClient` or `RestTemplate` is readable. Virtual threads make waiting on I/O lighter when compatible with the underlying HTTP transport/JDK.
- **WebFlux**: `WebClient` returns `Mono`/`Flux` for non-blocking composition. Inject Boot's managed **`WebClient.Builder`** to preserve auto-configured observation/tracing.
- **MVC using `WebClient`**: MVC apps can use reactive clients; **that does not make the server WebFlux**. Calling `.block()` on an MVC platform worker blocks that worker; on an MVC virtual thread it may unmount depending on underlying operations, yet remains a blocking boundary.
- **Netty server**: never run `RestTemplate` or blocking JDBC directly on the event loop.

Across all three models, timeouts, TLS, connection reuse, retry budgets, circuit breakers, and credential security matter more than framework hype.

### 14.4. External Rate Limits and Cascading Failures

Virtual threads and reactive pipelines easily launch far higher outbound concurrency than a small platform pool; without **bulkheads** and rate limiters, you can overwhelm a partner API and trigger retry storms. Maintain:
- maximum in-flight calls per downstream;
- deadline propagation and connect/request timeouts;
- bounded retries with backoff and jitter;
- circuit breakers and safe fallbacks;
- idempotency keys for mutating requests;
- observability into queue waits and dependency errors.

Scaling concurrency is **managing bounded resources**, not removing all limits.

## 15. Practical Reactive Data Streaming and Backpressure

### 15.1. `Flux` Streams Large Data, Without Making Memory Infinite

An endpoint returning a `Flux` of millions of records can stream incrementally if encoding, transport, and consumer keep up. Yet loading all records into a `List` first and wrapping with `Flux.fromIterable(list)` still pays the full memory spike. Backpressure only helps when data is produced on demand and drivers avoid buffering excessively.

Check:
- Does the source honor demand (`request(n)`)?
- Do serialization and HTTP transfer encoding truly stream?
- Does any `buffer()` or `collectList()` silently accumulate everything?
- Does a client disconnect cancel the subscription and close the DB cursor?
- Does a proxy/CDN buffer the whole response, defeating streaming?
- Does a slow consumer push upstream memory usage up?

### 15.2. Reactor `Context` Replaces `ThreadLocal`

Reactive pipelines hop across threads. A `ThreadLocal` set on a Netty event-loop thread is not guaranteed to survive `publishOn`/`subscribeOn`. Reactor uses **`Context`** to carry per-subscription metadata, and Spring/Micrometer provide context propagation depending on version and config. When migrating blocking `ThreadLocal` code to reactive, handle tracing, Spring Security context, transactions, and MDC systematically—never stash request state in global static fields.

### 15.3. Cancellation Does Not Undo Remote Side Effects

When a client cancels a subscription, `WebClient` or the driver may stop reading or abort, while the remote server may already have executed the POST. Likewise, a virtual or platform request timeout never guarantees the DB transaction rolled back. Enforce business idempotency and proper transaction semantics rather than treating cancellation as rollback.

## 16. Distinguishing Concurrency, Parallelism, and Asynchrony

**Concurrency** means multiple tasks making interleaved progress. **Parallelism** means multiple tasks executing on CPU cores at the exact same instant. **Asynchrony** means initiating work and receiving completion via callbacks, `Future`s, or `Publisher`s without blocking the caller at the launch site.

- A 16-thread platform pool handles concurrent requests, with some running in parallel on CPU cores.
- 10,000 virtual threads can be concurrent, while parallel execution remains bounded by carrier threads and CPU cores.
- Reactor Netty multiplexes huge numbers of concurrent network operations on a few event loops; CPU computation still requires cores and schedulers.

**Virtual threads do not provide Reactive Streams backpressure**; you enforce concurrency bounds explicitly in your app. **Reactive backpressure does not guarantee parallel operator execution**; it is purely a publisher/subscriber demand contract.

## 17. When Should You Enable Virtual Threads in WebFlux?

Enabling **`spring.threads.virtual.enabled=true`** switches Spring Boot-supported executors/schedulers, yet does not turn Reactor Netty's event-loop request handling into "one virtual thread per request". WebFlux remains a reactive framework whose event loops must never be blocked.

Certain blocking-execution helpers in WebFlux can use Boot's configured **`applicationTaskExecutor`** and benefit from virtual threads in specific integrations. Reactor's **`boundedElastic`** also has its own virtual-thread backing switch. Still, use hybrid setups only for well-tested cases rather than flipping multiple flags and calling the whole system virtual/reactive.

If a workload is cleanly reactive I/O end-to-end, there is little reason to replace its event-loop model with virtual threads per request. If most logic uses blocking JDBC SDKs, MVC + VT is usually simpler to operate than cramming every blocking call onto `boundedElastic`.

## 18. Optimizing CPU-Bound Tasks and Preventing Event-Loop Starvation

### 18.1. Virtual Threads Are Not a Magic CPU Scheduler

If an image-compression endpoint burns 100 ms of CPU, 1,000 concurrent virtual tasks still contend for the same CPU cores. When CPU saturates:
- cap CPU-work concurrency via a worker pool or bulkhead;
- optimize algorithms, data structures, and allocations;
- apply caching or batching where valid;
- consider offloading heavy CPU jobs to background queues/workers;
- monitor p99 and GC instead of spawning more tasks.

Never spawn millions of virtual threads to run pure CPU loops with no I/O; memory and scheduling overhead increase without improving speed.

### 18.2. Keep Long CPU Work Off Reactive Event Loops

In WebFlux, a `map` operator burning 500 ms of CPU on an event loop stalls many unrelated HTTP requests. Offload CPU-heavy stages to **`Schedulers.parallel()`** or a bounded custom executor while measuring switching overhead and maintaining backpressure. Do not offload every CPU task onto `boundedElastic` by reflex; `boundedElastic` is primarily meant for blocking I/O compatibility.

## 19. Observing Performance in Production

### 19.1. Metrics to Collect

| Signal | Why It Matters |
| --- | --- |
| **`http.server.requests`** latency/count/status | Tracks HTTP SLOs and 5xx/4xx rates by route template. |
| Tomcat busy/current threads in platform mode | Shows worker pool saturation; interprets differently in VT mode. |
| Netty event-loop lag/blocked duration (if instrumented) | Detects reactive event-loop starvation. |
| **`jvm.threads.live`** and virtual-thread/JFR events | Tracks live Java threads and pinning; do not rely on a single metric for VT counts. |
| CPU utilization, load, context switches | Distinguishes CPU-bound work from waiting. |
| JVM heap, allocation rate, GC pauses | Captures request/context/buffer memory cost. |
| Hikari active/idle/pending, slow DB queries | Locates JDBC and connection pool bottlenecks. |
| Outbound HTTP client latency, connection pool, timeouts | Reveals dependency bottlenecks. |
| Request queue time, 503s, rejected executions | Flags overload and missing backpressure. |
| Throughput, p95, p99, SLO error budget | Evaluates service quality rather than raw RPS alone. |

Never put user IDs, emails, full query strings, or raw request bodies into metric tags: it causes **high cardinality**, leaks data, and bloats monitoring bills.

### 19.2. JFR and Thread Dumps

- Use Java Flight Recorder for CPU profiling, allocations, locks, pinning, and thread behavior.
- For JDK 21 virtual threads, **`jdk.VirtualThreadPinned`** reveals monitor/native blocks holding carriers too long.
- For platform threads, thread dumps expose `BLOCKED`/`WAITING` states, deadlocks, and connection pool waits.
- For Reactor, inspect event-loop thread stacks when suspecting blocking; use Reactor debug/checkpoint or controlled observability hooks when needed.

Never capture production heap/thread dumps containing secrets and share them carelessly; they can expose tokens, payloads, request paths, and user data.

### 19.3. RPS Means Nothing While Requests Are Failing

If one mode hits 500 RPS with 20% 500s/timeouts while another hits 450 RPS with 0.1% errors and lower p99, you cannot call the first mode "faster" from RPS alone. Compare under **identical offered load and latency SLOs**, tracking accepted vs failed request splits.

## 20. Misconceptions to Eliminate

**1. Virtual threads are just a bigger platform thread pool.** Wrong. Virtual threads are JVM-scheduled onto carriers; never pool virtual threads like scarce resources.

**2. Enabling virtual threads makes the database faster.** Wrong. Queries still take the same time and DB pools stay bounded. The gain is cheaper concurrent waiting in request threads.

**3. Virtual threads speed up CPU-bound code.** Not by default; CPU cores remain finite.

**4. Setting `spring.threads.virtual.enabled=true` turns every thread virtual.** Wrong. Runtimes, app executors, custom pools, Netty, and library threads vary.

**5. Spring WebFlux guarantees non-blocking execution.** Not if handlers invoke JDBC, `Thread.sleep`, or `block()` on the event loop. Non-blocking must extend through dependencies.

**6. Adding `spring-boot-starter-webflux` to an MVC project switches the server to WebFlux.** Wrong in Boot 3.3; MVC takes precedence when both starters are present.

**7. `Mono`/`Flux` is a thread.** Wrong. Publishers represent signal pipelines; schedulers and context determine where work executes.

**8. Reactive backpressure prevents excess HTTP requests.** No. The demand protocol does not replace rate limiters, connection pools, or bulkheads.

**9. `Thread.isVirtual()` returning `false` in WebFlux means WebFlux isn't async.** Wrong. Reactive non-blocking concurrency does not depend on virtual threads.

**10. A `MockMvc` test reporting `virtualThread=true` proves Tomcat uses VT.** No. `MockMvc` can run on the test runner thread; use real HTTP server tests.

**11. `synchronized` in JDK 21 is always safe for virtual threads.** Not guaranteed; frequent long blocking sections inside `synchronized` risk carrier pinning on JDK 21. JDK 24 improves monitor pinning, yet lock contention still applies.

**12. Switch frameworks before measuring p95.** Usually a risky gamble. Measure the real bottleneck first to choose between tuning and migration.

## 21. Common Errors and Debugging Guide

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| VT enabled yet controller sees `virtualThread=false` | Running Java 17, property not applied, custom executor/other runtime | `java -version`, active config, Tomcat integration, real HTTP test |
| MVC platform p99 spikes at high concurrency | Worker pool full, DB waits, queueing | Busy threads, DB pool, response-time breakdown, CPU |
| MVC virtual throughput doesn't improve | CPU-bound workload, pinning, DB/network limits | CPU, JFR `jdk.VirtualThreadPinned`, Hikari pending, downstream RPS |
| JVM memory climbs under VT | Too many in-flight tasks, `ThreadLocal` caches, buffered responses | Heap, allocations, request concurrency, limits |
| WebFlux throughput collapses when calling JDBC | Blocking on Netty event loop | Thread dump / event-loop lag; use `boundedElastic` or reactive DB driver |
| WebFlux `block()` throws `IllegalStateException` | `block()` called on Reactor non-blocking scheduler | Compose `Mono`/`Flux`; offload legacy blocking if unavoidable |
| WebFlux OOM on large `Flux` | Unbounded buffering, `collectList()`, excessive concurrency | Bounded buffers, streaming, demand and operator concurrency limits |
| App still boots as MVC after adding `webflux` | `starter-web` still on classpath | Separate projects, verify Boot web application type |
| Throughput rises while errors rise | Downstream overload and retry storms | Bulkheads, rate limits, idempotency, latency/error SLOs |
| Local VT test fast, production slow | Real workload differs from `sleep`, pinning, GC, DB | Production-like load tests and profiling |
| `ThreadLocal` context lost in async/reactive | Thread hops or missing Reactor `Context` propagation | Instrument context propagation for security and tracing scopes |
| `@Scheduled` app exits under VT | Only daemon threads active | `spring.main.keep-alive=true`; inspect lifecycle |
| Raising Tomcat `maxThreads` changes nothing in VT mode | Pool property no longer bounds VT tasks the same way | Inspect connection limits and backing resource pools |
| MVC uses `WebClient` returning `Mono`, assumed reactive server | Reactive client does not dictate server framework | Check Spring web application type |
| Request times out yet DB commits anyway | Cancellation/timeout doesn't undo committed side effects | Idempotency, transaction semantics, reconciliation |

### Step-by-Step Investigation Workflow

1. **Confirm the actual web stack:** Servlet MVC/Tomcat or WebFlux/Netty? Are both starters present?
2. **Confirm Java runtime/config:** Java 21, is `spring.threads.virtual.enabled` active?
3. **Classify the workload:** CPU busy, DB wait, HTTP wait, lock contention, or queueing?
4. **Compare server/DB/client pool metrics** to spot the earliest saturation point.
5. **Check tail latency and error rate** at the same offered load.
6. **For VT**, capture JFR pinning, `ThreadLocal`, and heap stats if scaling disappoints.
7. **For reactive**, audit event-loop blocking, scheduler hops, buffers, and `flatMap` concurrency.
8. **Fix one bottleneck** and re-run the identical workload; never flip 10 configs at once.
9. **Add overload protection** instead of simply letting more in-flight requests pile up.
10. **Audit security, cancellation, and correctness:** fast latency is worthless if transactions break.

## 22. Practice Exercises

### Exercise 1 — Java 21 Mechanics

Run `ThreadModelsMain` with fixed platform pool=4 vs virtual-per-task. Compare completed counts, `virtualCount`, and `elapsedMs`. Explain why 40 `Thread.sleep` tasks finish with different wall times, and why you cannot extrapolate real database performance from this alone.

### Exercise 2 — Two Spring MVC Modes

Run the MVC project in platform mode then virtual mode, call `GET /wait?ms=250`, and verify the `virtualThread` boolean. Run `LocalLoadProbe` with 200 requests / concurrency 32, recording `wallMs`, `p95`, and success rate. Repeat 5 times and compare distributions rather than picking the fastest run.

### Exercise 3 — Harder Platform Tuning

Stay in MVC platform mode and test `server.tomcat.threads.max=8, 16, 32` under the same load test. Track CPU, request queues, and timeouts. Identify which setting best meets SLOs without assuming bigger is always better.

### Exercise 4 — Event-Loop Anti-Pattern

In a copy of the WebFlux lab, insert `Thread.sleep(250)` inside the handler before returning `Mono`, then measure latency as concurrency grows. Restore `Mono.delay` and explain why blocking the event loop stalls unrelated requests. **Run this only in a lab environment**, never ship intentional blocking endpoints to production.

### Exercise 5 — Blocking SDK and `boundedElastic`

Suppose a legacy library uses synchronous JDBC. Sketch `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` and analyze worker limits, queueing, and cancellation. Compare against MVC + VT when most business logic is blocking.

### Exercise 6 — 8-Connection DB Pool

Build a mock downstream allowing at most 8 concurrent operations with 100 ms latency. Compare 16 platform workers, 100 virtual tasks, and reactive `flatMap(concurrency=8)`. Explain why all three are bounded by the 8 connections, and how to protect the DB from overload.

### Exercise 7 — Java 21 Pinning

Write blocking I/O inside a `synchronized` block on JDK 21 and capture JFR `jdk.VirtualThreadPinned`. Narrow the `synchronized` section or change locking design, then re-measure. Never modify synchronization without verifying thread safety.

### Exercise 8 — Real-World Architecture Selection

Pick an initial model for three applications:
- A CRUD REST API on blocking Spring Data JPA/JDBC with growing traffic and Java 21 approved.
- A chat/streaming gateway using non-blocking `WebClient` and R2DBC.
- An image-processing batch service at 95% CPU utilization.

For each, state the initial choice, expected bottleneck, migration cost, resource limits, and key success metrics.

## 23. Checklist Before Changing Thread Models in Production

- [ ] Profiled workload: CPU-bound vs I/O-bound, with clear bottleneck evidence.
- [ ] Recorded baseline RPS, p95/p99, errors, CPU, memory, GC, queues, and DB pools.
- [ ] Verified Java version; VT only on Java 21+ with JDK-specific pinning evaluated.
- [ ] When enabling VT, verified real HTTP `thread.isVirtual()` in controllers and audited custom executors.
- [ ] Avoided fixed virtual-thread pools; bounded concurrency via resource-level bulkheads.
- [ ] Controlled connection pools, timeouts, retries, and downstream rate limits.
- [ ] Used JFR when suspecting JDK 21 pinning or lock contention.
- [ ] Kept `ThreadLocal`/MDC/security contexts small and cleaned up per request scope.
- [ ] In WebFlux, ensured blocking SDKs never run on event loops.
- [ ] Verified `Flux`/`Mono` pipelines enforce backpressure, buffer caps, and cancellation cleanup.
- [ ] Checked Boot web application type when both `web` and `webflux` starters are present.
- [ ] Verified `applicationTaskExecutor`/`@Async`/`@Scheduled` lifecycles and `keep-alive` where needed.
- [ ] Executed thread-model integration tests over `RANDOM_PORT`, not just `MockMvc`.
- [ ] Ran benchmarks with warm-up, repeated trials, fixed resources, p95/p99, and error rates.
- [ ] Scrubbed JWTs/`Authorization`/cookies from traces, metrics, and profiler artifacts.
- [ ] Prepared a config rollback plan if tail latency or connection exhaustion worsens.
- [ ] Verified Kubernetes readiness/liveness, graceful shutdown, and autoscaling do not misinterpret thread counts.
- [ ] Evaluated debugging complexity, maintainability, team training, and driver compatibility.

## 24. Self-Check Questions

**1. Do virtual threads add CPU cores?** No. They primarily cut the cost of holding many concurrent I/O-waiting tasks.

**2. If a platform thread pool saturates, should you immediately raise `maxThreads`?** No. First measure CPU, DB/client connection pools, queues, and bottlenecks.

**3. Can a virtual thread call blocking JDBC?** Yes. Imperative code keeps working; unmount efficiency depends on the library/JVM, and the DB pool still bounds concurrency.

**4. Does Java 17 run `spring.threads.virtual.enabled=true` properly?** Virtual threads require Java 21+, so this does not apply on Java 17.

**5. Should you pool virtual threads into 100 workers?** Not recommended. Use per-task virtual threads plus bulkheads around scarce resources.

**6. Is Reactor `Mono.delay` a virtual thread?** No. It is a non-blocking Reactor timer publisher, distinct from Java virtual threads.

**7. Can you call `Thread.sleep` on a WebFlux event loop?** No; it blocks the event loop and causes starvation.

**8. Does reactive backpressure replace connection pools and rate limiting?** No. Backpressure throttles item demand inside a stream; it does not bound all outbound calls globally.

**9. Does adding `spring-boot-starter-webflux` to an app with `starter-web` switch the server to Netty?** No; Boot 3.3 prefers Spring MVC when both starters are present.

**10. If `virtualThread=false` inside a Reactor callback, does that mean WebFlux isn't concurrent?** No; non-blocking async concurrency does not require virtual threads.

**11. What JDK 21 issue affects `synchronized`?** Long blocking calls inside a monitor can pin the virtual thread to its carrier, hurting throughput.

**12. Is a sleep-only benchmark enough to choose a production architecture?** No. Measure real I/O/CPU workloads, DB pools, error rates, and p95/p99 in production-like environments.

## 25. Official Documentation

1. [Spring Boot 3.3 — SpringApplication: Virtual Threads](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): `spring.threads.virtual.enabled`, thread-pool properties, pinning, and `keep-alive`.
2. [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): `applicationTaskExecutor`, `@Async`, `@Scheduled`, and virtual threads.
3. [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): Spring MVC, Tomcat connectors, and MVC web runtime.
4. [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): Spring WebFlux, Reactor, WebFlux dependencies, MVC precedence.
5. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): real HTTP `RANDOM_PORT` integration testing and web application types.
6. [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): platform/virtual threads, carrier scheduling, pinning, and JFR.
7. [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual-thread programming model, throughput, and structured concurrency distinctions.
8. [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): monitor pinning improvements in JDK 24.
9. [Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `Mono`/`Flux` scheduling, `boundedElastic`, `publishOn`, and `subscribeOn`.
10. [Spring Framework 6.1 — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): WebFlux non-blocking I/O goals and choosing between MVC and WebFlux.
11. [Reactive Streams Specification](https://www.reactive-streams.org/): `request(n)`, demand, backpressure, and publisher/subscriber contracts.

**Conclusion:** Spring Boot performance tuning must start from **bottlenecks and SLOs**, not from renaming the framework. For Spring MVC under moderate traffic, tuning platform thread pools, timeouts, and downstream resources may be plenty. On Java 21 with mostly **blocking I/O**, **virtual threads** preserve readable imperative code while lowering per-waiting-request cost, though DB/network protection and pinning checks remain vital. For end-to-end **non-blocking** and streaming architectures, **WebFlux/Reactor** provides event-loop I/O, composition, and explicit backpressure at the cost of pipeline and context complexity. **No model eliminates CPU, connection, memory, or downstream capacity limits; test, measure, verify, and roll out incrementally.**