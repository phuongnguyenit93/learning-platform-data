# Virtual Threads in Java 21 and Spring Boot Support Scope

## 1. What is a virtual thread and why is it important to understand it accurately?

A **virtual thread** is a lightweight type of **java.lang.Thread** managed by the JVM. Java 21 standardized virtual threads under **JEP 444**, without needing to enable preview features. They allow code to be written in a synchronous, one-thread-per-task style, while serving a very large number of concurrent tasks waiting on I/O without holding a separate OS thread for each task.

Comparison:

- **Platform thread**: a traditional Java thread that typically holds an OS thread throughout its lifecycle. While waiting for JDBC, a socket, or an HTTP response, the OS thread remains occupied.
- **Virtual thread**: the JVM can mount a virtual thread onto a **carrier thread** (a platform thread), then unmount it when encountering supported blocking I/O, freeing the carrier for another virtual thread. When I/O is ready, the virtual thread resumes.
- **No free CPU**: CPU-bound code still needs CPU cores. Virtual threads help scalability when **many tasks wait on I/O**, rather than making a single DB query or computation run faster by itself.

Conceptual diagram:

~~~text
Platform thread:
Request A -> waiting for DB ... -> response
(OS thread is held during wait time)

Virtual thread:
Request A -> waiting for DB -> unmount from carrier
                                |
                                +-> carrier runs request B/C
DB responds -> virtual A resumes -> response
~~~

A virtual thread is not a Spring-level coroutine, not a new Kafka worker, and does not automatically switch a system to reactive programming. It is still a Java Thread, supporting try/catch, stack traces, synchronized, ThreadLocal, and many synchronous APIs.

## 2. Quick comparison between platform and virtual threads

| Attribute | Platform thread | Virtual thread (Java 21) |
| --- | --- | --- |
| Java type | java.lang.Thread | java.lang.Thread |
| OS thread binding | Usually bound long-term | Mounted/unmounted on a carrier |
| Creation cost / count | Relatively high, OS-limited | Lighter, suited for many waiting tasks |
| Intended usage | Worker pool, CPU-bound, native calls | Thread-per-request/task with blocking I/O |
| Thread reuse via pool | Usually yes | **Should not pool virtual threads** |
| Daemon thread | Can be daemon/non-daemon | **Always daemon** |
| ThreadLocal | Supported | Supported, but many threads can consume RAM |
| Scheduling | OS schedules OS threads | JVM schedules virtual threads onto carriers |
| Speeding up CPU code | Not automatic | Not automatic |

A request doing continuous CPU work usually does not gain significant benefit. A request spending most of its time waiting on HTTP/JDBC can help the server increase throughput when switching to virtual threads, **provided** downstream services, connection pools, heap, and carriers do not become the new bottleneck.

## 3. Important Java 21 APIs

Java 21 supports:

- **Thread.startVirtualThread(Runnable)**: creates and starts a virtual thread.
- **Thread.ofVirtual().name(...).start(...)**: creates with a builder.
- **Executors.newVirtualThreadPerTaskExecutor()**: an executor that creates one virtual thread per task.
- **Thread.currentThread().isVirtual()**: verifies the current thread.
- **Future.get()** or **join()**: coordinates waiting for completion.

Short example:

~~~java
Thread worker = Thread.ofVirtual().name("io-task").start(
        () -> System.out.println(Thread.currentThread().isVirtual()));
worker.join();
~~~

This is an illustrative Java 21 snippet inside a method that can throw InterruptedException. When run properly, it prints true. There is no --enable-preview requirement for Java 21 virtual threads.

### Standalone Java 21 program

Create **VirtualThreadBasics.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadBasics {
    public static void main(String[] args) throws Exception {
        List<Future<Boolean>> results = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 3; i++) {
                results.add(executor.submit(() -> {
                    Thread.sleep(40);
                    return Thread.currentThread().isVirtual();
                }));
            }

            for (int i = 0; i < results.size(); i++) {
                System.out.println("task-" + (i + 1)
                        + " virtual=" + results.get(i).get());
            }
        }

        System.out.println(
                "main virtual=" + Thread.currentThread().isVirtual());
    }
}
~~~

Run with JDK 21:

~~~bash
javac VirtualThreadBasics.java
java VirtualThreadBasics
~~~

Program output lines in order:

~~~text
task-1 virtual=true
task-2 virtual=true
task-3 virtual=true
main virtual=false
~~~

The tasks can complete in any order, but main reads each **Future** in list order so the printed output is deterministic. Main is normally created by the Java launcher on a platform thread. Thread.sleep(40) only illustrates blocking; do not use sleep as a synchronization mechanism in production.

**Do not create a fixed-size virtual thread pool.** The intended model is one virtual thread per task; limiting database or API access must be handled by connection pools, Semaphores, bulkheads, or rate limiters.

## 4. Requirements for Spring Boot support

**Spring Boot 3.2** introduced virtual threads integration. In the examples, **Spring Boot 3.3.x + Spring Framework 6.1.x + Java 21** is chosen for clear APIs.

To enable the integrations managed by Spring Boot:

~~~properties
spring.threads.virtual.enabled=true
~~~

Requirements:

1. **The actual runtime JVM must be Java 21 or higher**, not just sourceCompatibility 21.
2. Spring Boot must be at a supported version, such as 3.2 or later.
3. The property must be effective in the active profile.
4. The component must use a **Boot-configured virtual executor/container** or be explicitly configured appropriately. Threads created directly by application code or external libraries do not change type just because of the property.

**Java 21 does not automatically enable the property.** Without declaring spring.threads.virtual.enabled=true, Spring Boot 3.3 still uses traditional executors at the corresponding auto-configuration points.

### Integration scope reference table

| Component | Support in Spring Boot 3.2+/3.3 when properly enabled | Limitations |
| --- | --- | --- |
| Embedded Tomcat + Spring MVC | Processes HTTP requests on virtual threads | Only with Boot-supported containers/configurations |
| Embedded Jetty servlet | Supports virtual threads on compatible versions | Custom executors may behave differently |
| Auto-configured applicationTaskExecutor | SimpleAsyncTaskExecutor using virtual threads | No longer a traditional ThreadPoolTaskExecutor pool |
| @Async combined with @EnableAsync | Can use Boot's virtual executor | Custom Executor/AsyncConfigurer or self-invocation changes the outcome |
| Spring MVC asynchronous request handling | Uses supported applicationTaskExecutor | Does not mean every handler is async |
| Spring for GraphQL Callable async handling | Can leverage auto TaskExecutor | Depends on integration and actual executor |
| Spring WebFlux blocking offload support | Can use auto AsyncTaskExecutor | **Reactor Netty event loops do not automatically switch to virtual threads** |
| @Scheduled with auto TaskScheduler | SimpleAsyncTaskScheduler supports virtual threads | fixedDelay is limited to a single scheduler thread |
| Boot auto-configured Kafka/Rabbit listener integrations | Configures virtual executor in supported integrations | Does not mean all custom poll loops/workers are virtual |
| Custom TaskExecutor/TaskScheduler | Only virtual if explicitly configured | Boot's flag does not force custom pools to change |
| Undertow/external servers | Must be checked separately | Do not generalize from Tomcat/Jetty |
| Database, Redis server, Kafka broker | Unaffected | These are separate processes/systems outside the JVM |

To verify a specific component, measure **Thread.currentThread().isVirtual()** directly inside that method and inspect the actual executor/container, rather than inferring from class names or properties.

## 5. Minimal configuration and JVM keep-alive

In **src/main/resources/application.properties**:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Equivalent YAML:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true
~~~

**spring.main.keep-alive=true** is important because **virtual threads are always daemon threads**. The JVM can exit if no non-daemon threads remain. A typical case is an application that only has **@Scheduled** and a virtual scheduler, without a web server or another component keeping the process alive.

Do not blindly enable keep-alive for **CLI/batch jobs that need to run to completion and exit**: the property can keep the process alive after the main work finishes. A web server may already have other non-daemon threads, but do not rely on such an assumption for scheduler-only applications.

Check runtime:

~~~bash
java -version
~~~

Ensure Java 21 is actually used in the container image, processes run by Gradle/Maven, and CI/CD environments.

## 6. Complete Spring Boot 3.3 and Java 21 example

The Spring MVC application below verifies two paths:

- **HTTP request thread** dispatched by embedded Tomcat.
- **@Async method** running through Spring Boot's auto-configured applicationTaskExecutor.

### File structure

~~~text
virtual-thread-boot-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          VirtualThreadDemo.java
      resources/
        application.properties
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'virtual-thread-boot-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Requires JDK 21, a compatible Gradle version, and permission to download dependencies or a pre-populated cache.

File **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

File **src/main/java/example/VirtualThreadDemo.java**:

~~~java
package example;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class VirtualThreadDemo {
    public static void main(String[] args) {
        SpringApplication.run(VirtualThreadDemo.class, args);
    }
}

@Service
class AsyncProbeService {
    @Async
    public CompletableFuture<Boolean> checkAsyncThread() {
        boolean virtual = Thread.currentThread().isVirtual();
        return CompletableFuture.completedFuture(virtual);
    }
}

@RestController
class ThreadProbeController {
    private final AsyncProbeService service;

    ThreadProbeController(AsyncProbeService service) {
        this.service = service;
    }

    @GetMapping("/threads")
    public Map<String, Boolean> checkThreads() throws Exception {
        boolean requestVirtual = Thread.currentThread().isVirtual();
        boolean asyncVirtual =
                service.checkAsyncThread().get(5, TimeUnit.SECONDS);

        return Map.of(
                "requestVirtual", requestVirtual,
                "asyncVirtual", asyncVirtual);
    }
}
~~~

**Why this example runs:**

- The single public class matches the filename, and the remaining classes are package-private.
- @EnableAsync enables proxy infrastructure for @Async.
- The controller calls the async method **through the injected AsyncProbeService bean**, not via self-invocation on this.
- There is no custom Executor or AsyncConfigurer, so Spring Boot can use its auto-configured virtual executor.
- @Async returns CompletableFuture<Boolean>, and the controller retrieves the result using get(timeout).
- Uses default starter-web with embedded Tomcat instead of running WebFlux Reactor Netty.

### Run and compare

If Gradle wrapper is available:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If only a compatible pre-installed Gradle is available, use gradle bootRun.

From another terminal:

~~~bash
curl -s http://localhost:8080/threads
~~~

With Spring Boot 3.3, JDK 21, default Tomcat, and virtual=true, the two expected values are:

~~~json
{"requestVirtual":true,"asyncVirtual":true}
~~~

**Do not depend on JSON key order**: Map.of does not guarantee serialization order. Compare the values of requestVirtual and asyncVirtual.

Try changing to:

~~~properties
spring.threads.virtual.enabled=false
~~~

Restart. With standard Tomcat and executor configuration, the expected output is:

~~~json
{"requestVirtual":false,"asyncVirtual":false}
~~~

If different, check profile overrides, custom executors, JDK, web container, and startup flags. **The returned data only describes the measured execution paths**, and does not prove every thread in the application is virtual.

## 7. @Async and auto-configured TaskExecutor

In Spring Boot 3.3:

- If no custom Executor alters auto-configuration conditions and virtual threads are off, Boot typically configures **ThreadPoolTaskExecutor**.
- If virtual threads are enabled on Java 21+, Boot typically configures **SimpleAsyncTaskExecutor** with virtual threads.
- This executor is used in Boot-supported integrations, such as @EnableAsync and Spring MVC asynchronous processing.
- A custom **AsyncConfigurer/Executor** can replace the default executor.
- For certain web integrations, a custom bean must have the matching name/type to be used, such as **applicationTaskExecutor** of type **AsyncTaskExecutor**.

**Thread pool properties no longer configure a virtual-thread pool**. For example:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
~~~

These properties are for the pool-based ThreadPoolTaskExecutor and do not limit SimpleAsyncTaskExecutor's virtual threads. However, **not all task execution properties are ineffective**; other prefixes/customizations may still apply depending on the version.

**@Async does not automatically get virtual threads if @EnableAsync is missing** or if a **this.asyncMethod()** call bypasses the Spring proxy. For @Async returning void, exceptions in the worker do not propagate back to the publisher/caller once the task is submitted. Use Future results, an error handler, metrics, or a message queue when execution guarantees are needed.

## 8. Do not pool virtual threads; limit downstream resources

A virtual thread corresponds to a single task. If you need to cap concurrency at a maximum of 20 HTTP calls, use a **resource** limiting mechanism, not a “virtual thread pool size 20”.

Illustrative example inside a service:

~~~java
private final Semaphore permits = new Semaphore(20);

public String limitedCall() throws InterruptedException {
    permits.acquire();
    try {
        return blockingHttpCall();
    } finally {
        permits.release();
    }
}
~~~

This is an illustrative snippet; you must import Semaphore and define blockingHttpCall(). In production, you can use tryAcquire(timeout), a rate limiter, a bulkhead/circuit breaker, and metrics.

A HikariCP connection pool with 10 connections **cannot run 1,000 concurrent queries just because there are 1,000 virtual threads**. Many virtual threads will wait for connections, potentially causing timeouts and memory pressure. Likewise, downstream APIs still have finite quotas and processing rates.

| Resource | Scales infinitely thanks to virtual threads? |
| --- | --- |
| CPU cores | No |
| JDBC connections | No |
| HTTP connection pool | No |
| Kafka partitions | No |
| Remote API quota | No |
| RAM / heap | No |
| File descriptors | No |
| Business exactly-once | No |

The measurable benefit is **the ability to hold many I/O-waiting tasks** with lower thread overhead, not scaling dependencies infinitely.

## 9. @Scheduled and SimpleAsyncTaskScheduler

Spring Boot 3.3 can auto-configure a scheduler when the application uses **@EnableScheduling**. When virtual threads are enabled, the auto-configured scheduler is typically **SimpleAsyncTaskScheduler**; when disabled, it is typically **ThreadPoolTaskScheduler**.

Excerpt example, requiring Spring Scheduling imports:

~~~java
@Configuration
@EnableScheduling
class SchedulingConfig {
}

@Component
class ScheduledProbe {
    @Scheduled(fixedRate = 5000, initialDelay = 5000)
    public void tick() {
        System.out.println(
                "scheduled virtual=" + Thread.currentThread().isVirtual());
    }
}
~~~

With SimpleAsyncTaskScheduler and fixedRate, work can run on a virtual thread. **Important note**: **@Scheduled(fixedDelay=...)** uses a single scheduler thread in SimpleAsyncTaskScheduler to preserve fixed-delay semantics. Therefore, it is **not equivalent to a separate virtual thread per invocation**, and a slow fixed-delay task can block other fixed-delay tasks.

Spring Framework 6.1 recommends considering **fixedRate or cron** when aiming to leverage the virtual-per-task model. However, fixedRate/cron can cause overlapping invocations if work takes too long, so you must design against overlap using locks, rate limiting, or a dedicated scheduler/job.

For scheduler-only apps, note that **all virtual threads are daemon threads**: enable **spring.main.keep-alive=true** if no other non-daemon thread keeps the JVM running.

## 10. Spring MVC differs from Spring WebFlux

### Spring MVC + embedded Tomcat or Jetty

Boot 3.2+ integrations can use virtual threads for **servlet request processing** in Tomcat/Jetty. Synchronous-style controller code can still call JDBC or blocking HTTP APIs while the carrier is yielded at appropriate I/O points.

Illustrative example:

~~~java
@GetMapping("/customer")
public Customer customer() {
    return customerRepository.findOneRequired();
}
~~~

This snippet is not standalone: Customer and customerRepository are business components that must be defined. **Virtual threads do not make DB queries faster**, but they can help handle more concurrently waiting requests more efficiently.

### Spring WebFlux + Reactor Netty

WebFlux on Reactor Netty relies on **event loops** and reactive/non-blocking I/O. Enabling spring.threads.virtual.enabled **does not convert Netty event-loop threads into virtual threads**. Spring Boot can only use the virtual executor for **blocking execution support/offload** paths that the framework integrates with.

Do not place a blocking JDBC call directly on the event loop thinking the property protects you. You need a reactive driver or proper offloading. Choose between servlet blocking + virtual threads or WebFlux reactive based on workload, libraries, and operational skills—do not mix them arbitrarily.

### Libraries and custom threads

Threads created directly by the application via ThreadPoolExecutor, custom schedulers, Kafka client internal polling, native libraries, Netty event loops, or a container not managed by Boot **do not change automatically**. Even though Boot's Kafka/RabbitMQ integrations support virtual executors on certain paths, verify each actual listener/container rather than assuming all threads are virtual.

## 11. Pinning on JDK 21

A notable limitation in **JDK 21** is that a virtual thread becomes **pinned** when encountering certain blocking operations inside a **synchronized** block or native/foreign call. The carrier is not released, reducing throughput if pinning is frequent and prolonged.

Java pseudocode example:

~~~java
private final Object monitor = new Object();

String fetch() {
    synchronized (monitor) {
        return slowBlockingHttpCall();
    }
}
~~~

If slowBlockingHttpCall() actually blocks for a long time inside synchronized on JDK 21, the carrier can be held. This **does not necessarily make the program incorrect**, but it can degrade scalability.

When frequent pinning is measured, you can refactor the critical section or consider ReentrantLock:

~~~java
private final ReentrantLock lock = new ReentrantLock();

String fetch() {
    lock.lock();
    try {
        return slowBlockingHttpCall();
    } finally {
        lock.unlock();
    }
}
~~~

The two snippets above **are not standalone programs**; slowBlockingHttpCall must be defined and ReentrantLock imported. **Do not mechanically replace every synchronized block.** Short, non-blocking monitors may still be appropriate.

JDK 21 diagnostics:

- JFR event **jdk.VirtualThreadPinned**.
- JVM flag **-Djdk.tracePinnedThreads=full** or **short** depending on JDK 21 support.
- **jcmd** virtual-thread dump/stack trace.
- Benchmark throughput and CPU/carrier utilization.

Note: Newer JDKs, especially from JDK 24 onward, have significant changes regarding monitor pinning. This lesson focuses on **Java 21** and does not claim synchronized behavior on all JDKs is identical to JDK 21.

## 12. ThreadLocal, transactions, and context propagation

Virtual threads still support ThreadLocal, but the number of threads can be very large:

- Heavy ThreadLocal usage across thousands of tasks increases heap consumption.
- MDC, SecurityContext, and transaction context may be bound to the running thread; crossing into **@Async** switches threads.
- **@Async does not automatically propagate a request's Spring transaction** to the worker virtual thread.
- To preserve logging/security/tracing context, use a TaskDecorator or framework-supported context propagation, and define clear transaction boundaries.
- Do not rely on thread name or thread ID as a business key.

Virtual threads help keep blocking-style code readable; they **do not change the safety rules of transactions**, cancellation, or shared data across threads.

## 13. InterruptedException, shutdown, and daemon behavior

A virtual thread still obeys many standard Thread rules. When waiting on I/O or sleep where interruption is possible, handle it responsibly:

~~~java
try {
    Thread.sleep(100);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted", e);
}
~~~

This is an illustrative snippet inside a method. Do not swallow interruption and continue an infinite loop.

When using a self-created ExecutorService, close the executor at a managed lifecycle boundary. With @Async, running a task on a virtual thread **does not make it finish automatically if the request has ended**; separate ownership, timeouts, cancellation, and error reporting are required.

**Virtual threads are daemon threads**, so if a program only has them left, the JVM can exit. For batch tasks that must complete, main should wait on Future and close the executor properly. For a scheduler-only long-lived app, consider spring.main.keep-alive=true.

## 14. Performance: measure the right things

Metrics to compare before and after enabling the flag:

1. **Throughput**: requests/second or tasks/second on the same workload.
2. **p50, p95, p99 latency**: virtual threads do not guarantee lower latency per individual request.
3. **CPU utilization and GC**: no extra CPU cores are created, and heap usage can rise if many tasks pile up.
4. **Database connection wait**, connection timeouts, and query latency.
5. **HTTP client pool saturation**, downstream rate limits, and error rate.
6. **Pinned virtual threads** on JDK 21, duration and frequency of pinning.
7. **ThreadLocal/MDC overhead**, context propagation, and memory.
8. **Executor/task backlog**, backpressure, cancellation, and shutdown behavior.
9. **Recovery behavior** when downstream is slow or disconnects.
10. **Replica count and resource limits** in containers/Kubernetes.

A test with a single request or a for-loop creating 1,000 virtual threads **is not enough** to conclude production will be faster. Test realistic workloads while keeping DB pools, downstream latency, and CPU/RAM limits identical for a fair comparison.

## 15. Checklist for enabling virtual threads in a project

Before deploying:

- Confirm production JVM uses **Java 21+**.
- Confirm Spring Boot **3.2+** and check documentation for the exact version.
- Enable **spring.threads.virtual.enabled=true** in the right profile.
- Measure **Thread.currentThread().isVirtual()** in the controllers, @Async methods, schedulers, and consumers you care about.
- Check whether there are **custom Executors, AsyncConfigurers, TaskSchedulers, or servlet executors**.
- Do not treat Reactor Netty event loops as servlet thread-per-request.
- Analyze blocking I/O, JDBC/HTTP connection pools, and expected concurrency levels.
- Use **Semaphores/rate limits/bulkheads** to throttle downstream calls.
- On JDK 21, check pinning in synchronized/native hot paths.
- Evaluate ThreadLocal, MDC, security, and transaction propagation.
- Review **@Scheduled(fixedDelay)** and the risk of occupying the scheduler thread.
- For scheduler-only apps, check **spring.main.keep-alive=true**.
- Benchmark throughput/latency/memory and test shutdown.
- Be ready to roll back the property if actual performance degrades.

## 16. Common misconceptions

**“JDK 21 automatically makes Spring Boot use virtual threads.”** No. The property and appropriate integrations are required.

**“Virtual threads speed up CPU.”** No. The main benefit is concurrency with blocking I/O.

**“Each virtual thread has its own OS thread.”** No. The JVM schedules them onto carriers.

**“Enabling the property makes every library's ThreadPoolExecutor virtual.”** No. Independently created executors must be configured separately.

**“@Async always runs virtually just by adding the annotation.”** No. @EnableAsync, proxy invocation, and an appropriate executor are needed.

**“spring.task.execution.pool.max-size limits virtual threads.”** Not with SimpleAsyncTaskExecutor using virtual threads.

**“Virtual threads should be pooled like platform threads.”** No. Create per task and bound downstream resources.

**“WebFlux on Reactor Netty automatically converts all handlers to virtual.”** No. The event loop still uses the reactive model.

**“@Scheduled(fixedDelay) uses a separate virtual thread for every run.”** Not with SimpleAsyncTaskScheduler in Spring Framework 6.1.

**“Virtual threads will keep the JVM alive for a scheduler-only process.”** No. They are daemon threads.

**“Pinning means Java code is always buggy.”** No; it is usually a throughput issue when blocking is long/frequent.

**“Pinning cannot happen when using synchronized.”** False on JDK 21.

**“A DB has 10 connections, yet 10,000 virtual tasks all query in parallel.”** No. The connection pool remains the limit.

**“@Async automatically inherits the caller's transaction.”** No. Thread-bound transaction context must be handled separately.

**“Increasing the virtual-thread count is always better.”** No. It can overload downstream systems and increase memory pressure.

**“A preview flag is needed for Thread.ofVirtual in Java 21.”** No.

## 17. Self-check questions

**Question 1:** Is a virtual thread in Java 21 a different class from java.lang.Thread?  
**Answer:** No. It is still java.lang.Thread, but managed and mounted onto a carrier by the JVM.

**Question 2:** When a virtual thread waits on supported blocking I/O, can the carrier serve another task?  
**Answer:** Yes, if the virtual thread can unmount and is not pinned.

**Question 3:** Does Java 21 require --enable-preview for virtual threads?  
**Answer:** No.

**Question 4:** Starting from which version did Spring Boot support virtual threads integration?  
**Answer:** 3.2; requires Java 21 or later and enabling spring.threads.virtual.enabled=true.

**Question 5:** Which TaskExecutor does Boot 3.3 auto-configure when virtual=true?  
**Answer:** SimpleAsyncTaskExecutor using virtual threads, if auto-configuration conditions are not altered by custom beans.

**Question 6:** Can a Tomcat servlet controller run on a virtual thread?  
**Answer:** Yes, with appropriate Spring Boot integration; verify using Thread.isVirtual().

**Question 7:** Does enabling the property convert Netty event-loop threads to virtual?  
**Answer:** No.

**Question 8:** Why does fixedDelay have a caveat when using SimpleAsyncTaskScheduler?  
**Answer:** Fixed-delay tasks run on a single scheduler thread, unlike the virtual-per-task mechanism for fixedRate/cron.

**Question 9:** Why should a scheduler-only app pay attention to spring.main.keep-alive?  
**Answer:** Virtual threads are daemon threads, so the JVM can exit when no non-daemon threads remain.

**Question 10:** Does a virtual thread make a 500 ms JDBC query shrink to 50 ms on its own?  
**Answer:** No. It can help increase the number of concurrently waiting requests, not speed up the query itself.

**Question 11:** Why shouldn't you pool virtual threads to limit DB calls?  
**Answer:** Pooling virtual threads is not a resource-limiting tool; use a connection pool, Semaphore, or bulkhead.

**Question 12:** When is JDK 21 pinning concerning?  
**Answer:** When blocking I/O inside synchronized/native sections occurs frequently and lasts long, holding the carrier.

**Question 13:** Does @Async automatically pass the caller's Spring transaction to another virtual thread?  
**Answer:** No. Appropriate transaction boundaries and context propagation are needed.

**Question 14:** What should a minimal benchmark measure?  
**Answer:** Throughput, p95/p99 latency, CPU, memory/GC, pinning, connection wait, and downstream errors/timeouts.

**Conclusion:** Virtual threads in Java 21 provide a **lightweight thread-per-task** model suited for I/O-heavy blocking applications. **Spring Boot 3.2+** provides **selective** support via **spring.threads.virtual.enabled=true**, notably in Tomcat/Jetty servlets, TaskExecutor/@Async, and TaskScheduler; WebFlux Reactor Netty event loops do not automatically become virtual threads. When adopting them, you must consider **JDK 21 pinning, daemon keep-alive, fixedDelay, custom executors, ThreadLocal, connection pools, and backpressure**, and measure actual effectiveness before broad rollout.

### References

- [OpenJDK — JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Spring Boot — 3.2 Release Notes: Virtual Threads](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework 6.1 — SimpleAsyncTaskScheduler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html)
