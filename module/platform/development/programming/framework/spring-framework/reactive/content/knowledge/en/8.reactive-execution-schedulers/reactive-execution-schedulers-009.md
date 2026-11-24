# Virtual Threads with boundedElastic and Version/Configuration Requirements

**Context:** Spring Framework – Reactive, **Execution Threading** topic. This lesson explains how Project Reactor uses **virtual threads** in `Schedulers.boundedElastic()`, when the feature is available, how to enable it properly in the JVM or Spring Boot, how to verify it in code, and what limits must still be kept when running a WebFlux application.

## 1. Problem: Reactor Needs a Safe Place to Run Blocking Work

Spring WebFlux and Project Reactor encourage using non-blocking I/O. However, real-world systems still contain synchronous operations such as:

- JDBC/JPA libraries, synchronous HTTP SDKs, legacy clients, blocking file reads.
- A library waiting for a result, calling `Thread.sleep(...)`, or an external API lacking reactive support.
- Transitional steps while migrating from an imperative architecture to reactive.

**Do not place prolonged blocking operations on the Netty event loop or non-blocking processing threads.** When an event loop is blocked, other connections sharing that thread also wait, causing high latency and reduced throughput.

Reactor provides `Schedulers.boundedElastic()` to **offload blocking work onto a suitable scheduler with concurrency and queue bounds**. Under standard configuration, the scheduler uses **platform threads** (traditional Java threads). With **Java 21+ and Reactor 3.6+**, this shared scheduler adds an option to run tasks on **virtual threads** when a system property is enabled.

Key distinction:

> **Virtual threads reduce the cost of waiting on blocking operations in many cases; they do not turn a blocking API into a non-blocking API, nor do they make CPU tasks run faster by themselves.**

For example, JDBC still invokes a blocking API and still occupies a connection from the pool. Moving the call onto a virtual thread can cut the cost of holding a platform thread while waiting, yet does not speed up the database query or increase the number of allowed connections.

## 2. What Are Virtual Threads and How Do They Differ from Platform Threads?

A **platform thread** is a traditional Java thread mapped by the JVM to an OS thread, with corresponding stack and scheduling cost. Under a model holding one blocked platform thread per task, many simultaneous I/O waits can require many threads and consume heavy resources.

A **virtual thread** is a lightweight thread managed by the JVM, finalized in **Java 21**. The JVM schedules many virtual threads onto a smaller pool of **carrier platform threads**. When a virtual thread performs a blocking operation that the JVM can handle efficiently, it is typically *unmounted* from its carrier while waiting; the carrier can run another virtual thread. When data is ready, the work resumes.

| Criterion | Platform thread | Virtual thread |
| --- | --- | --- |
| Logical unit | A traditional Java thread | A lightweight Java thread managed by the JVM |
| Resources with very many I/O-waiting tasks | Higher OS thread/stack cost | Usually cheaper when many tasks wait |
| CPU-bound work | Still CPU-bound | Still CPU-bound |
| Blocking API | Can block a platform thread | Can run in blocking style; JVM optimizes many wait cases |
| Controlling DB connections, API rate limits | Must be bounded separately | Still must be bounded separately |
| Ordering, transactions, shared data | Not automatically safe | Not automatically safe |
| Library/native-code compatibility and pinning | Can suffer contention | Must also check sections that can pin a carrier |

A **carrier thread** is the platform thread the JVM uses to execute a virtual thread at a given moment. Virtual threads do not mean "a dedicated CPU core each"; thousands of virtual threads doing CPU math together cannot exceed physical cores.

Virtual threads can experience **pinning** in certain cases, especially on JDK versions prior to Java 24 improvements when blocking inside `synchronized` blocks, native code, or operations unable to unmount. Prolonged pinning can hold the carrier and negate virtual thread benefits. Details vary by JDK version, so observe actual runtime behavior via JFR, `jcmd`, and profiling rather than assuming every blocking call always unmounts.

## 3. Role of `Schedulers.boundedElastic()` in Reactor

Reactor offers several schedulers for different purposes:

| Scheduler | Typical purpose |
| --- | --- |
| `Schedulers.immediate()` | Runs work directly on the current thread |
| `Schedulers.single()` | Executes on a single-thread scheduler, suited for tasks needing serial execution |
| `Schedulers.parallel()` | Executes short, bounded CPU computational work |
| `Schedulers.boundedElastic()` | Holds blocking/legacy I/O operations that must be kept off the event loop |
| Custom scheduler via `Schedulers.newBoundedElastic(...)` | Dedicated scheduler with its own limits and lifecycle, configured per version API |

`boundedElastic` is called **bounded** because it does not create unlimited threads or queued waiting tasks. Depending on version/configuration, it bounds active backing threads or virtual threads and queued work. When limits are exceeded, scheduling can be rejected (e.g., `RejectedExecutionException`) instead of spawning unbounded resources.

In **shared `Schedulers.boundedElastic()`**, there are two main implementation modes:

1. **ExecutorService-based, platform-thread mode (default):** uses a pool of backing platform threads; threads can be reused and long-idle threads are reclaimed.
2. **Thread-per-task, virtual-thread mode (conditionally enabled):** each task is scheduled to run on a **new virtual thread**, without keeping an idle virtual-thread pool for reuse. Delayed/periodic tasks still have an internal scheduling component, while execution moves onto a virtual thread when due.

Enabling this option does not automatically convert every Reactor scheduler in a program to virtual threads. It selects the **implementation mode of shared `boundedElastic()`**. Code running on the Netty event loop, `parallel()`, `single()`, a custom `Executor`, or another scheduler does not automatically switch to virtual threads.

### 3.1. Why Are Limits Still Needed When Virtual Threads Are So Light?

Virtual threads are cheaper than platform threads while waiting, yet each task still has objects, logical stack frames, working resources, and can hold connections/locks. Creating too many tasks at once can still:

- Exhaust the database connection pool or another API's limits.
- Increase queues, heap, GC, timeouts, and p99 latency.
- Trigger retry storms, contention, or stall upstream services.
- Consume CPU if tasks involve significant computation.

**Adding virtual threads does not replace concurrency control and backpressure.** Use `flatMap(..., concurrency)`, semaphores/bulkheads, connection pools, and rate limits where actually needed, rather than just raising scheduler caps.

## 4. Exact Version Requirements

The **virtual-thread implementation of shared Reactor `boundedElastic()`** appeared in **Reactor Core 3.6.0**.

| Component | Requirement | If unmet |
| --- | --- | --- |
| Java runtime | **JDK/JRE 21 or higher**, with finalized virtual threads | This virtual-thread mode cannot be enabled; uses platform-thread scheduler/compatible strategy |
| Reactor Core | **3.6.0 or higher**, with version-supported API/configuration | Reactor prior to 3.6 lacks this shared `boundedElastic` option |
| Reactor configuration | `reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true` **before the scheduler is initialized** | Shared `boundedElastic` uses platform threads by default |
| Code execution path | Work must be scheduled onto shared `Schedulers.boundedElastic()` | Work on the event loop or other schedulers does not auto-switch to virtual threads |
| Actual deployment JVM | Container, IDE, Gradle/Maven, or production runtime must run Java 21+ | Compiling with a newer JDK while running on an older runtime breaks expectations |

**Do not infer the Reactor version solely from Spring Framework or Spring Boot names.** Spring Boot manages versions via BOM/dependency management; verify the actual runtime dependency. In Gradle apps, use a dependency report such as `./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath`. In Maven, you can use `mvn dependency:tree -Dincludes=io.projectreactor:reactor-core`.

Java 21 is a **runtime requirement**; code samples calling `Thread.currentThread().isVirtual()` also require compiling with a JDK supporting that API. With Java 17, you can still use platform-thread `boundedElastic` to isolate blocking work, but **cannot use Reactor's virtual-thread mode under these requirements**.

## 5. Enabling Virtual Threads for Reactor via JVM System Property

**Exact**, case-sensitive property name:

```properties
reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true
```

Example with a packaged JAR app on a Java 21+ JVM:

```bash
java -Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true -jar app.jar
```

In Docker/Kubernetes runtimes, pass the equivalent flag via JVM startup args or `JAVA_TOOL_OPTIONS`; ensure the property reaches the **JVM running the application**, not merely the build tool process.

**Set the property before Reactor's scheduler is first initialized.** Reactor reads configuration from system properties when initializing the relevant components; the shared scheduler also has its own lifecycle/caching. Calling `System.setProperty(...)` late after a library has already touched `Schedulers.boundedElastic()` does not guarantee converting an already-created instance from platform threads to virtual threads.

Therefore, the reliable approach is passing `-D...=true` at **JVM startup** and restarting the application. For tests comparing both modes, run **two separate JVM processes**, each configured from the start; avoid trying to toggle the property inside a single process after the scheduler is initialized.

### 5.1. `boundedElastic` Limit Properties

Alongside thread-mode selection, Reactor exposes bound settings for shared boundedElastic:

```properties
reactor.schedulers.defaultBoundedElasticSize=80
reactor.schedulers.defaultBoundedElasticQueueSize=1000
```

These are **illustrative example values**, not recommended production defaults. Reactor documentation describes:

- `reactor.schedulers.defaultBoundedElasticSize`: caps active threads/backing tasks in the shared scheduler; defaults typically derive from **10 × available CPUs**.
- `reactor.schedulers.defaultBoundedElasticQueueSize`: caps internally queued pending tasks, defaulting in referenced versions to **100,000 extra tasks per backing thread/corresponding bound structure**.
- When limits are exceeded, scheduling may be rejected. Very large queue sizes can turn traffic spikes into prolonged **queueing latency** instead of resolving bottlenecks.

Size values from real load: I/O-waiting requests, connection pools, task duration, wait times, timeout rates, and memory budgets. **Do not automatically raise both caps to huge numbers just because virtual threads are lightweight.** Defaults or exact queue-distribution details may vary across versions; check the `Schedulers` Javadoc for the exact artifact you run.

### 5.2. Which Schedulers Does the Reactor Flag Apply To?

The `reactor.schedulers.defaultBoundedElasticOnVirtualThreads` flag is documented for **shared `Schedulers.boundedElastic()`**. Do not assume that a custom scheduler built with `Schedulers.newBoundedElastic(...)`, a custom executor, `Schedulers.parallel()`, or Netty threads also use virtual threads. Custom scheduler factory APIs can vary across Reactor versions; check the Javadoc of the overload you use.

If your application declares a custom `Schedulers.Factory`, custom scheduler, Spring `Executor`, or overrides the global scheduler lifecycle, verify behavior at runtime. Similar method names do not guarantee identical configuration.

## 6. Spring Boot: Distinguishing Spring's Property from Reactor's Property

Spring Boot supports:

```properties
spring.threads.virtual.enabled=true
```

When running **Java 21+**, this property directs **Spring Boot-managed** executors/schedulers toward virtual threads where Boot supports them. It also integrates with Reactor configuration in Spring Boot versions containing `ReactorEnvironmentPostProcessor`: Boot can **set the Reactor system property** so shared `boundedElastic()` uses virtual threads right during startup.

Thus there are **two practical configuration paths**:

1. **Standalone Reactor apps or explicit configuration:** pass `-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true` directly before the JVM initializes the scheduler.
2. **Integrated Spring Boot versions:** set `spring.threads.virtual.enabled=true` and confirm the Boot version configures Reactor as intended. Boot 3.2+ includes `ReactorEnvironmentPostProcessor`, which sets the Reactor property when Java meets requirements.

Example `src/main/resources/application.properties` in a compatible Spring Boot project:

```properties
spring.threads.virtual.enabled=true
```

**Note:** `spring.threads.virtual.enabled` and `reactor.schedulers.defaultBoundedElasticOnVirtualThreads` are **not the same key**. The first is handled by Spring Boot; the second is handled by Reactor. In an app **not launched via `SpringApplication`**, merely putting the Spring key in a properties file does not configure Reactor.

Nor should you conclude that every WebFlux request runs on a virtual thread when the property is enabled: WebFlux normally uses the Netty event loop for non-blocking I/O. Only segments explicitly moved to boundedElastic (or another virtual-thread-configured executor) use them by design.

**Initialization order:** If a library calls `Schedulers.boundedElastic()` too early, before Spring Boot processes the environment, the result may not match expectations. Verify in the real JVM. Avoid initializing global schedulers in static initializers of startup classes before configuration is guaranteed to have applied.

### 6.1. Note on Spring Boot Auto-Configured Tasks

When `spring.threads.virtual.enabled=true` is set, certain Boot-created `AsyncTaskExecutor` or scheduling beans can switch to virtual-thread executors. This impact is **broader** than `boundedElastic` alone and can render traditional thread-pool settings inapplicable to those virtual-thread executors.

Virtual threads are daemon threads. If an application relies primarily on scheduled tasks to keep the JVM alive, check JVM shutdown rules; Spring Boot documentation mentions `spring.main.keep-alive=true` for suitable cases. A web app with a running server keeping the JVM alive differs from a scheduled-job-only tool, so check your specific lifecycle.

## 7. Runnable Java 21 Example: Proving Whether boundedElastic Uses a Virtual Thread

The example below is a **complete Java class** with no Spring dependency. It uses Reactor to schedule `Mono.fromCallable(...)` onto shared `boundedElastic` and checks directly with `Thread.currentThread().isVirtual()`.

File `src/main/java/demo/VirtualBoundedElasticDemo.java`:

```java
package demo;

import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class VirtualBoundedElasticDemo {
    public static void main(String[] args) {
        Boolean virtual = Mono.fromCallable(() ->
                        Thread.currentThread().isVirtual())
                .subscribeOn(Schedulers.boundedElastic())
                .block(Duration.ofSeconds(5));

        System.out.println("boundedElastic isVirtual=" + virtual);
    }
}
```

Compile/run requirements: **JDK 21+**, `reactor-core 3.6+`, and compatible `org.reactivestreams:reactive-streams` on the classpath. In a Spring Boot app with the WebFlux starter, Reactor dependencies are normally managed already. To run manually, place the appropriate JARs in `lib/` and run:

```bash
# Linux/macOS (in project directory)
mkdir -p out
javac -cp "lib/*" -d out src/main/java/demo/VirtualBoundedElasticDemo.java

# Default mode: platform threads
java -cp "out:lib/*" demo.VirtualBoundedElasticDemo

# Virtual-thread mode: enable before initializing Reactor
java -Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true \
     -cp "out:lib/*" demo.VirtualBoundedElasticDemo
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
javac -cp "lib/*" -d out src/main/java/demo/VirtualBoundedElasticDemo.java

java -cp "out;lib/*" demo.VirtualBoundedElasticDemo

java "-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true" `
    -cp "out;lib/*" demo.VirtualBoundedElasticDemo
```

**Exact stdout across the two runs under the stated conditions:**

Without the property enabled:

```text
boundedElastic isVirtual=false
```

With the property enabled on Reactor 3.6+, Java 21+:

```text
boundedElastic isVirtual=true
```

**Explanation:**

1. `Mono.fromCallable(...)` defers the thread check until the publisher is activated.
2. `subscribeOn(Schedulers.boundedElastic())` switches subscription/upstream callable onto the scheduler. Thus `isVirtual()` inspects the **thread executing the work**, not the main thread.
3. `block(Duration.ofSeconds(5))` is a blocking bridge in a command-line program with `main`, used here to retrieve the result and print deterministically. **Do not call `block()` inside the WebFlux event loop**.
4. The two Java commands are separate processes, letting platform and virtual modes be tested independently without relying on resetting global schedulers.
5. Make sure no other environment property (such as `JAVA_TOOL_OPTIONS` or IDE launch configs) enables virtual threads during the "default" run.

A `true` result proves **the task scheduled on boundedElastic** ran in a virtual thread; it **does not prove** all application threads, Netty, or every publisher in the pipeline use virtual threads.

## 8. Combining with Blocking Code: Using `fromCallable` + `subscribeOn`

A legacy service with a synchronous API can be bridged temporarily:

File `src/main/java/demo/LegacyLookupService.java` in a Spring Boot/WebFlux project with `spring-boot-starter-webflux`:

```java
package demo;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class LegacyLookupService {

    public Mono<String> lookup(String key) {
        return Mono.fromCallable(() -> legacyLookup(key))
                .subscribeOn(Schedulers.boundedElastic());
    }

    private String legacyLookup(String key)
            throws InterruptedException {
        // Represents a blocking call in a legacy library.
        Thread.sleep(50);
        return "value-for-" + key;
    }
}
```

In a WebFlux controller, return the publisher created by the service:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class LegacyLookupController {
    private final LegacyLookupService service;

    public LegacyLookupController(LegacyLookupService service) {
        this.service = service;
    }

    @GetMapping("/lookup/{key}")
    public Mono<String> lookup(@PathVariable String key) {
        return service.lookup(key);
    }
}
```

These are **two classes inside a running Spring Boot project**, not two standalone files with `main`. With these classes and a properly configured Boot app, calling `curl http://localhost:8080/lookup/abc` returns body `value-for-abc` if the server runs on port 8080; whether virtual threads or platform threads are used depends on the runtime boundedElastic configuration explained above.

### 8.1. Why Must `fromCallable` Be Used?

Wrong:

```java
return Mono.just(legacyLookup(key))
        .subscribeOn(Schedulers.boundedElastic());
```

**The snippet above illustrates a bug**, not a standalone method: it would need checked-exception handling and a matching `legacyLookup` definition. Java evaluates `legacyLookup(key)` **before calling `Mono.just(...)`**. Hence the blocking call executes right where the publisher is constructed, possibly right on the event loop. `subscribeOn` appearing afterward cannot travel back in time to move a call that has already run.

Right:

```java
return Mono.fromCallable(() -> legacyLookup(key))
        .subscribeOn(Schedulers.boundedElastic());
```

The lambda inside `fromCallable` executes only upon subscription; `subscribeOn` routes upstream work onto boundedElastic.

### 8.2. `subscribeOn` and `publishOn` Do Not Have the Same Meaning

- `subscribeOn(scheduler)` affects where subscription and upstream processing run. For a blocking source inside `fromCallable`, it is the standard way to offload the blocking source to boundedElastic.
- `publishOn(scheduler)` shifts **downstream signal processing after the operator's position** onto the scheduler. Useful when a specific downstream processing stage must use a different executor.
- Neither **automatically turns** a synchronous HTTP client into non-blocking; they only affect which threads execute work.
- Schedulers are selected at **each placement point**. One pipeline may switch threads multiple times; do not assume a WebFlux request always stays on one thread or always uses a virtual thread.

Example:

```java
Flux<Integer> values = Flux.range(1, 3)
        .publishOn(Schedulers.boundedElastic())
        .map(value -> expensiveBlockingTransform(value));
```

This is an illustrative snippet with an application-defined `expensiveBlockingTransform(...)`. If the transform function blocks, `publishOn` can isolate that downstream stage from the preceding thread, though for large pipelines check thread-switching overhead, prefetch size, and task limits. In many cases, legacy sources are better isolated with `fromCallable(...).subscribeOn(...)`.

### 8.3. Virtual Threads Do Not Automatically Make Blocking Transactions Reactive

JPA/JDBC still use synchronous transactions and connections, which may rely on Spring's `ThreadLocal`. Merely wrapping a `JpaRepository` in a publisher does not turn a transaction into a reactive transaction. Keep **imperative transaction boundaries** inside work running on an appropriate thread; do not assume reactive `@Transactional` automatically spans a `Mono` chain switching across schedulers.

When a transaction requires multiple atomic JDBC writes, let a dedicated transactional imperative service method execute the whole operation, then call it across a suitable `fromCallable` boundary—or choose an MVC/virtual-threads architecture if most of the system remains blocking. Mixing JPA with WebFlux requires carefully evaluating transactions, connection pools, error propagation, and cancellation.

## 9. What Actually Changes When Virtual-Thread boundedElastic Is Enabled?

Separate the **thread type executing tasks** from **publisher semantics**:

| Aspect | Platform-thread boundedElastic | Virtual-thread boundedElastic |
| --- | --- | --- |
| How tasks run | Backing platform threads, reusable | New virtual thread per scheduled task per Reactor's implementation |
| `Mono/Flux`, `subscribeOn`, `publishOn` APIs | Unchanged | Unchanged |
| Blocking state of sync JDBC/SDKs | Still blocking | Still blocking, though many waits can use platform carriers more efficiently |
| Scheduler concurrency/queue bounds | Yes | Yes |
| Reactive Streams signal ordering guarantees | Per operator/source | Per operator/source, unchanged |
| Backpressure | Per subscription and operator | Not automatically added by virtual threads |
| DB query speed | Depends on DB, pool, query | Still depends on DB, pool, query |
| CPU-bound work | Not faster by itself | Not faster by itself |
| ThreadLocal/log context | Must be designed per request/runtime | Still must be designed; does not auto-propagate across scheduler boundaries |

In Reactor, **cancellation** sends a signal to the subscription; yet you cannot assert that every legacy blocking call running on a virtual thread stops instantaneously, especially if the driver/library ignores interruption or already dispatched work to an external system. For work with side effects like payments, order writes, or resource-creating API calls, enforce separate timeouts, idempotency, and consistency rules.

**Do not inflate `flatMap` concurrency excessively** just because virtual threads have low overhead. Each inner can still hold a DB connection or wait on a resource-limited service. If 10,000 concurrent tasks hit a DB pool of 30, the system may simply turn the bottleneck into a longer queue.

## 10. Verifying Correct Configuration in a Running Application

Merely having config in a file or launch command does not prove the scheduler operates as expected. A solid verification includes these steps:

1. **Verify the JVM** with `java -version` in the environment running the app (not only the dev machine). In containers, check the Java version **inside the image**.
2. **Verify runtime Reactor Core** via dependency reports (Gradle/Maven) and the active BOM; requirement is **3.6+**.
3. **Verify how the property is enabled**: directly via JVM `-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true`, or via compatible Spring Boot integration with `spring.threads.virtual.enabled=true`.
4. **Start a fresh process**, rather than relying on `System.setProperty` after Reactor schedulers were first referenced.
5. **Check directly inside work scheduled on shared `boundedElastic`** using `Thread.currentThread().isVirtual()` as in the Java 21 example.
6. **Measure load and resources**, including throughput alongside error rate, p50/p95/p99, pending tasks, scheduler rejections, heap, CPU, DB connection pool, and upstream wait time.
7. **Test cancellation, timeouts, and tracing**; confirm legacy clients and transactions behave properly on request disconnect, timeout, or retry.

Compare platform-thread mode and virtual-thread mode under the **same workload and identical downstream limits**. A benchmark that merely creates hundreds of thousands of sleeping virtual threads without hitting a DB, connection pool, and business logic can mislead you into expecting similar production throughput.

### 10.1. Configuration Test Based on `isVirtual()`

If the app already has JUnit Jupiter and `reactor-test`, a test can confirm behavior when the **process is started with virtual mode enabled**:

File `src/test/java/demo/VirtualBoundedElasticTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class VirtualBoundedElasticTest {

    @Test
    void boundedElasticUsesVirtualThreadWhenConfigured() {
        Mono<Boolean> onVirtualThread =
                Mono.fromCallable(() ->
                        Thread.currentThread().isVirtual())
                    .subscribeOn(Schedulers.boundedElastic());

        StepVerifier.create(onVirtualThread)
                .expectNext(true)
                .verifyComplete();
    }
}
```

**Test conditions:** run the test JVM on JDK 21+, Reactor Core 3.6+, and pass `-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true` **when starting the test JVM**. `reactor-test` is required on the test classpath. If run in a default process without the mode enabled, expecting `true` will fail—this is how the test catches misconfiguration, **not by having the test try to set the property after the scheduler is already initialized**.

In Gradle, you can configure JVM args on the dedicated test task; when running `./gradlew test`, a `-D...` flag passed to the Gradle daemon JVM **does not automatically mean** it is forwarded to forked test workers. Configure `systemProperty`/`jvmArgs` on the test task if the test JVM must receive the flag. Similarly, verify Maven Surefire/Failsafe configuration.

When testing multiple environments (Java 17, Java 21 mode off, Java 21 mode on), use separate test processes and matching expectations; do not write a test asserting `true` and then run it on Java 17.

## 11. Operational and Performance Issues to Watch

### 11.1. No Speedup for CPU-Bound Work

Virtual threads focus on improving scalability for large numbers of **waiting tasks**. If requests perform hashing, encryption, compression, or long CPU calculations, having many virtual threads does not surpass CPU limits. Optimize the algorithm, bound concurrent compute tasks, or use appropriate compute resources.

### 11.2. Pinning, Native Calls, and Locking

A blocking operation can cause a virtual thread to hold its carrier (*pin*) in some cases. Depending on JDK and libraries, this can happen when blocking inside `synchronized` blocks or crossing native APIs lacking efficient unmount support. **JDK 24 and newer bring major improvements to monitor pinning**, so do not apply every Java 21 performance warning verbatim to all newer JDKs.

When performance is unexpectedly poor, use Java Flight Recorder and compatible JVM tools to check for pinning, contention, and blocked tasks. Optimize the actual root cause rather than guessing from scheduler names.

### 11.3. Context Propagation Does Not Happen Automatically

Spring Security context, log MDC, tracing spans, or `ThreadLocal`-bound values can be lost when Reactor switches threads unless a corresponding context-propagation mechanism is configured. Virtual threads have their own ThreadLocals, yet that **does not mean** the Netty event loop's context is automatically copied onto a new virtual thread.

In reactive pipelines, use **Reactor Context** and the context-propagation support provided for your Spring/Reactor versions. For legacy libraries requiring ThreadLocal, test the actual adapter/bridge rather than passing mutable request state via static variables.

### 11.4. Observe Resources at the Right Layer

Platform thread usage may drop while the bottleneck still sits at one of these points:

- JDBC connection pool exhausted, creating waiting queues.
- Upstream service enforcing QPS/concurrency caps or API rate limits.
- High CPU load across carriers and downstream tasks.
- `boundedElastic` scheduler hitting its cap or queue limit and rejecting tasks.
- Lock contention, native calls, pinning, or memory retention.
- Retries and timeouts pushing in-flight task counts higher than expected.

**What matters to measure** are real SLAs: p95/p99 latency, throughput at equal error rates, memory/GC, CPU, connection counts, and recovery after spikes. Never judge a configuration superior from virtual-thread count alone.

## 12. Distinguishing Three Misleading Statements

**"Enabling virtual threads turns WebFlux into thread-per-request."** Incorrect. WebFlux still uses the event loop and asynchronous pipelines where appropriate. Only parts running on schedulers/executors configured for virtual threads execute that way.

**"Running `boundedElastic()` on virtual threads makes JDBC reactive."** Incorrect. JDBC remains blocking and still needs connections, transactions, and query limits; only the blocking wait runs on a different kind of Java thread.

**"Virtual threads are unlimited, so ignore pools, queues, and backpressure."** Incorrect. BoundedElastic still enforces caps/queues; databases, CPU, memory, and external services remain bounded.

A useful mental model for combining them:

```text
                  Spring WebFlux request
                           |
                    Non-blocking chain
                           |
           [legacy blocking call still needed]
                           |
              Mono.fromCallable(() -> call())
                           |
              subscribeOn(boundedElastic)
                           |
     +---------------------+-----------------------+
     |                                             |
  Flag false                                  Flag true
  Compatible Java                             Java 21+, Reactor 3.6+
     |                                             |
  Platform thread                              Virtual thread
     |                                             |
     +---------------------+-----------------------+
                           |
               Return Mono result to WebFlux
                           |
                  Response / error / cancel
```

Each branch has different resource characteristics, yet **upstream limits, transaction rules, and error propagation must still be preserved**.

## 13. Common Misconfigurations and Fixes

| Symptom / confusion | Possible cause | How to check / fix |
| --- | --- | --- |
| Flag set yet `isVirtual()=false` | Runtime Java below 21; Reactor below 3.6; flag passed to wrong JVM; scheduler initialized too early | Verify JVM/process, runtime dependencies, startup args, then restart in a fresh process |
| Set `spring.threads.virtual.enabled=true` in a standalone Reactor app | No SpringApplication/Boot present to translate the key into Reactor's property | Pass Reactor's JVM system property directly |
| Thread in controller is still Netty event loop | Controller entry was not scheduled on boundedElastic; this is normal WebFlux behavior | Check inside the `subscribeOn(boundedElastic)` task instead of at controller entry |
| Calling `Mono.just(blockingCall())` then `subscribeOn` | Blocking already ran while evaluating the argument | Change to `Mono.fromCallable(() -> blockingCall()).subscribeOn(...)` |
| Tests via `./gradlew test -D...` do not use virtual threads | Property may not reach the forked test JVM | Configure `systemProperty`/`jvmArgs` explicitly on the Gradle Test task |
| System stays slow after enabling virtual threads | Bottleneck is in DB pool, locks, CPU, queues, pinning, or upstream | Measure p95/p99, queues, pools, JFR; bound concurrency and optimize root cause |
| HTTP times out yet legacy task keeps running | Canceling subscription does not always abort underlying blocking work | Design timeouts, SDK-supported interrupt/cancel, and idempotency |
| Raising `boundedElasticSize` worsens latency | More tasks contend for few connections/resources | Control concurrent work and queue depth, then re-benchmark |
| Log/security context lost after thread switch | ThreadLocal does not automatically cross Reactor/virtual-thread boundaries | Use Reactor Context and compatible context propagation |
| Custom scheduler ignores the flag | Property applies to shared `Schedulers.boundedElastic()`, not automatically to custom executors | Inspect the exact instance running the task, its API, and lifecycle |

## 14. Deployment Checklist

1. **Is there genuine blocking I/O to isolate?** If `WebClient`, R2DBC, or a non-blocking driver is available, prefer keeping that non-blocking path.
2. **Do Java runtime and Reactor Core meet requirements?** Java 21+, Reactor 3.6+.
3. **Is the right property enabled?** JVM `-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true` before startup, or compatible Spring Boot integration.
4. **Does code place blocking work inside a deferred lambda?** `fromCallable`/`fromRunnable` with `subscribeOn(boundedElastic)`; avoid blocking inside `Mono.just(...)`.
5. **Did you verify `Thread.isVirtual()` directly inside the task?** Do not measure on the main thread or event loop and draw wrong conclusions.
6. **Are concurrency, DB pool, API timeouts, and scheduler queues bounded?** Virtual threads do not bound those layers automatically.
7. **Have lifecycle, transactions, security context, and cancellation been checked?** Especially when using legacy SDKs/JDBC.
8. **Did you benchmark with realistic load?** Compare platform and virtual modes in two separate processes with identical data and bounds.
9. **Do you monitor pinning, scheduler rejections, and p99 latency?** Use appropriate metrics/JFR.
10. **Do you truly need WebFlux?** If all business logic stays imperative and blocking, Spring MVC + virtual threads is also worth comparing; decide based on operational needs.

## 15. References

- [Project Reactor Reference – Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): the two implementation modes of `boundedElastic`, Java 21+, and the system property enabling virtual threads.
- [Project Reactor Schedulers Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html): `boundedElastic()`, `DEFAULT_BOUNDED_ELASTIC_*` settings, and related bounds.
- [Spring Boot ReactorEnvironmentPostProcessor (Boot 3.3)](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/reactor/ReactorEnvironmentPostProcessor.html): how `spring.threads.virtual.enabled` links to Reactor's system property when Java meets requirements.
- [Spring Boot – Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): scope of virtual-thread settings on Boot-managed executors and scheduling.
- [Spring Blog – Reactor Core 3.6.0](https://spring.io/blog/2023/10/31/what-new-is-coming-in-reactor-core-3-6-0/): introduces the thread-per-task scheduler using virtual threads.

## 16. Key Takeaways

**For shared `Schedulers.boundedElastic()` to use virtual threads**, you need **Java 21+**, **Reactor Core 3.6+**, and **`reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true`** enabled before the scheduler is initialized. In compatible Spring Boot versions, **`spring.threads.virtual.enabled=true`** can configure that mode alongside Boot's other executors.

Virtual threads improve how the JVM manages many blocking I/O waits, yet **do not change the reactive contract, do not make JDBC non-blocking, and do not remove CPU, connection-pool, or upstream limits**. Always check `Thread.currentThread().isVirtual()` inside the task itself, keep concurrency/queue bounds in place, and validate with real operational metrics.
