# Enabling spring.threads.virtual.enabled in Spring Boot: Configuration, Mechanism, and Verification

## 1. Lesson objective

In Spring Boot, the **spring.threads.virtual.enabled** property is a configuration switch that allows components **auto-configured by Spring Boot with virtual threads support** to use Java's virtual threads. This is a way to leverage Project Loom from Java 21 to handle a large volume of I/O-waiting work in a readable synchronous coding style.

Typical examples:

- A REST API calling another HTTP service and waiting for a response.
- An **@Async** task waiting for a query result or I/O processing.
- An application running **@Scheduled** jobs with external system wait time.
- A system with many requests simultaneously waiting on a database/network, aiming to reduce the cost of holding a separate platform thread for each task.

Key distinctions to make right from the start:

1. **Enabling the property does not turn all Java threads into virtual threads.** It changes specific integrations that Spring Boot knows how to configure.
2. **A virtual thread does not automatically speed up a CPU-bound task.** The main benefit lies in sustaining many I/O-waiting tasks with lower thread overhead.
3. **Enabling virtual threads does not automatically solve limits of connection pools, downstream APIs, databases, memory, or quotas.**
4. **Java 21 or later is required.** Spring Boot 3.5 documentation also recommends Java 24+ if deployment conditions permit, due to JVM improvements for virtual threads.
5. You must observe **Thread.currentThread().isVirtual()** at the exact place where the task runs, not merely check that the property was read as true.

This lesson focuses on **Spring Boot 3.5.x and Java 21+** to present clear APIs, results, and references. If using a different Boot major version, check the official documentation for that exact version.

## 2. What is a virtual thread?

Java has two groups of threads commonly compared:

- **Platform thread:** bound to operating system thread resources in the traditional model. When a platform thread hits blocking I/O, it typically occupies an OS thread during the wait.
- **Virtual thread:** a lightweight Java Thread managed by the JVM and scheduled to run on **carrier platform threads**. During compatible blocking operations, the JVM can temporarily **unmount** the virtual thread from its carrier so the carrier can serve other tasks.

Visualization:

~~~text
Platform-thread-per-request style:

Request A -> OS thread #1 -> waiting on network
Request B -> OS thread #2 -> waiting on database
Request C -> OS thread #3 -> waiting on network
...

Virtual-thread-per-request style:

Request A -> VirtualThread A --- waiting on network, carrier free
Request B -> VirtualThread B --- waiting on database, carrier free
Request C -> VirtualThread C --- running on carrier when scheduled
                     |
               JVM scheduler
                     |
         A set of carrier platform threads
~~~

Virtual threads are still **java.lang.Thread**. You can use **Thread.currentThread()**, **ThreadLocal**, and standard exception semantics per the Java API. However, the number of virtual threads can be much larger than platform threads, so patterns using **ThreadLocal caches**, thread affinity, or blocking operations inside native code should be re-evaluated.

Java 21 provides the API:

~~~java
Thread.startVirtualThread(() -> {
    System.out.println(Thread.currentThread().isVirtual());
});
~~~

This is an **illustrative Java snippet**; the program must wait for the thread to finish if you want to reliably see output before main exits. You can use **Thread.ofVirtual()** or **Executors.newVirtualThreadPerTaskExecutor()** when the application manages tasks directly.

**The Spring Boot property is not required to use the Java APIs above directly.** It helps Spring Boot choose implementations that support virtual threads for auto-configured components.

## 3. How to enable spring.threads.virtual.enabled?

### Method 1: application.properties

Create or update **src/main/resources/application.properties**:

~~~properties
spring.threads.virtual.enabled=true
~~~

This is the shortest way when already running Spring Boot on JDK 21 or higher.

### Method 2: application.yml

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

There is no need to declare the same property across both files unless for a specific override purpose.

### Method 3: command-line argument

~~~bash
java -jar app.jar --spring.threads.virtual.enabled=true
~~~

Here **app.jar** is an illustrative name for the project's executable JAR, not a pre-generated file path. Spring Boot processes command-line arguments when using SpringApplication.run under default mechanics.

### Method 4: environment variable

On Linux/macOS, you can pass an environment variable following standard relaxed binding rules:

~~~bash
SPRING_THREADS_VIRTUAL_ENABLED=true java -jar app.jar
~~~

In Windows PowerShell, you can set **$env:SPRING_THREADS_VIRTUAL_ENABLED = "true"** before running the JAR in the same terminal. Do not write secret values onto the command line for testing; this property is only a boolean.

### Method 5: enable only in a specific profile

~~~properties
# application-virtual.properties
spring.threads.virtual.enabled=true
~~~

When enabling the **virtual** profile via **--spring.profiles.active=virtual**, this configuration is loaded according to ConfigData rules. A profile can be used for canary benchmarking before enabling it for all instances.

**A clear configuration for learning:**

~~~properties
spring.application.name=virtual-thread-demo
spring.main.web-application-type=none
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

The last two properties have distinct meanings:

- **spring.threads.virtual.enabled=true:** instructs Spring Boot to use virtual threads in supported components.
- **spring.main.keep-alive=true:** instructs Boot to keep the JVM alive appropriately in cases where the only threads sustaining the application are daemon threads. This is especially important for applications running **@Scheduled** without a web server or any other non-daemon thread.

**Do not use Java 17 and expect the property to turn the JDK into Java 21.** Verify the actual runtime with **java -version**, Java target/source, and the Docker base image.

## 4. Which components does Spring Boot change when the property is enabled?

According to Spring Boot 3.5's **Task Execution and Scheduling** documentation, provided the application does not declare custom executors/schedulers that cause auto-configuration to back off:

| Mechanism | When virtual threads are disabled | When virtual threads are enabled |
| --- | --- | --- |
| Auto-configured **AsyncTaskExecutor** | **ThreadPoolTaskExecutor** | **SimpleAsyncTaskExecutor** using virtual threads |
| Auto-configured **TaskScheduler** | **ThreadPoolTaskScheduler** | **SimpleAsyncTaskScheduler** configured to use virtual threads |
| **@Async** with **@EnableAsync** | Typically runs on Boot-provided platform-thread executor | Can run on virtual-thread executor if resolution selects it |
| Spring MVC async request integration | Uses appropriate applicationTaskExecutor | Can use the executor configured with virtual threads |
| Spring WebFlux blocking execution support | Uses Boot-configured executor | Can offload blocking execution to virtual-thread executor |
| Boot-supported Tomcat/Jetty servlet request processing | Server's default threading | Can handle requests on virtual threads with Boot-supported config |

**Important condition:** the rows in the table describe **auto-configuration** mechanisms, not a promise that every library or every piece of code in the process is converted.

### 4.1. Task execution

Spring Boot can auto-create the **applicationTaskExecutor** bean of type **AsyncTaskExecutor**. With Java 21+ and virtual threads enabled, the typical implementation is **SimpleAsyncTaskExecutor** with virtual thread mode enabled. It can be used by integrations such as **@Async** (when @EnableAsync is enabled), MVC async, WebFlux blocking execution support, and certain WebSocket/GraphQL/JPA bootstrap scenarios under documented conditions.

**SimpleAsyncTaskExecutor is not ThreadPoolTaskExecutor.** It creates a new thread for each task; when using virtual threads, thread creation cost is lighter, though underlying resource limits still exist. It does not operate as a pool with core size, max size, and queue capacity.

### 4.2. Task scheduling

When Boot auto-configures a scheduler and virtual threads are enabled, the typical implementation is **SimpleAsyncTaskScheduler**. It is designed around scheduling on a single scheduler thread and can launch task executions on separate threads.

**Important Spring Framework note:** with **SimpleAsyncTaskScheduler**, scheduled tasks using **fixed delay** execute on **a single scheduler thread** to preserve fixed-delay semantics, so **fixed rate or cron triggers** are usually more suitable when aiming to leverage virtual-thread-per-task. You should not claim every **@Scheduled** method always executes on a virtual thread.

### 4.3. Servlet Web server

Spring Boot has supported virtual threads in corresponding web server integrations since Boot 3.2. With Boot-configured embedded **Tomcat** or **Jetty** and a suitable Java runtime, servlet request handling can use virtual threads.

For **Spring WebFlux using Reactor Netty**, do not assume all event-loop threads become virtual threads just because the property is enabled. WebFlux has its own event-loop model and offload mechanisms; you must measure and observe the actual threads.

### 4.4. Integrations outside Spring Boot

Libraries that create platform threads directly with **new Thread(...)**, create **Executors.newFixedThreadPool(...)**, or manage their own worker pools **do not automatically switch to virtual threads**. If a message broker client or database driver has an internal thread pool, the library itself and its configuration determine threading.

Therefore **spring.threads.virtual.enabled=true** is a **scoped** option, not a JVM flag that turns every Thread into a virtual thread.

## 5. Runnable Java 21+ and Spring Boot 3.5.x example

The example below verifies three things:

1. The **spring.threads.virtual.enabled** property is read as true by Environment.
2. Auto-configured **AsyncTaskExecutor** uses virtual threads.
3. A method in another bean annotated with **@Async** runs on a virtual thread.
4. The **ApplicationRunner** method itself still runs on the normal bootstrap platform thread — enabling the property does not change every execution path.

To keep output clear, the example avoids long sleeps, does not use a web server, and **waits for CompletableFutures to complete before printing**. The Maven project uses **Java 21+**, not Java 17.

### 5.1. Create the project

Create a project using Spring Initializr with:

- **Spring Boot 3.5.x**.
- **Java 21** or a newer Java version supported by the Boot/JDK version.
- **Maven**.
- Group **com.example**, artifact **virtual-thread-demo**, package **com.example.demo**.
- Dependency **Spring Boot Starter**. Spring Web is not needed for this executor test.

Keep the Maven Wrapper, parent/BOM, and Spring Boot Maven Plugin generated by Initializr. The minimal dependency section corresponds to:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

This is a **POM XML snippet**, not a complete pom.xml. The Java version in the project must be 21 or higher.

### 5.2. Configuration file

Create **src/main/resources/application.properties**:

~~~properties
spring.application.name=virtual-thread-demo
spring.main.web-application-type=none
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

The application runs without a web server, yet uses **keep-alive** to highlight the requirement for keeping the JVM alive when only daemon virtual threads exist. The example closes the context explicitly so the process does not run forever.

### 5.3. Complete Java file

Create **src/main/java/com/example/demo/VirtualThreadDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableAsync
public class VirtualThreadDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             VirtualThreadDemoApplication.class, args)) {
            // Spring Boot has already executed ApplicationRunner inside run().
            // Close the context after completing the test.
        }
    }

    @Bean
    ApplicationRunner inspectVirtualThreads(
            Environment environment,
            AsyncTaskExecutor taskExecutor,
            ThreadProbeService service) {

        return args -> {
            boolean enabled = environment.getProperty(
                    "spring.threads.virtual.enabled",
                    Boolean.class, false);

            System.out.println("property=" + enabled);
            System.out.println("runnerVirtual="
                    + Thread.currentThread().isVirtual());
            System.out.println("executorClass="
                    + taskExecutor.getClass().getSimpleName());

            CompletableFuture<Boolean> executorResult =
                    new CompletableFuture<>();

            taskExecutor.execute(() -> {
                boolean virtual = Thread.currentThread().isVirtual();
                executorResult.complete(virtual);
            });

            System.out.println("executorVirtual="
                    + executorResult.join());

            // Call through the Spring bean proxy, not self-invocation within the same class.
            boolean asyncVirtual = service.inspect().join();
            System.out.println("asyncVirtual=" + asyncVirtual);
        };
    }

    @Service
    public static class ThreadProbeService {

        @Async
        public CompletableFuture<Boolean> inspect() {
            boolean virtual = Thread.currentThread().isVirtual();
            return CompletableFuture.completedFuture(virtual);
        }
    }
}
~~~

**Code check:**

- Public class **VirtualThreadDemoApplication** matches the filename.
- **@SpringBootApplication** activates Boot auto-configuration and component scanning.
- **@EnableAsync** lets Spring manage **@Async** execution.
- **ThreadProbeService** is a standalone Spring bean in a nested static class; **inspect()** is called from **ApplicationRunner in another bean**, going through the proxy.
- **AsyncTaskExecutor** is injected from auto-configuration when the project has no custom Executor/AsyncConfigurer.
- The **taskExecutor.execute(...)** call uses a block lambda returning **void**, matching Runnable's signature; there is no overload ambiguity.
- **CompletableFuture.join()** makes printed output order deterministic, even if background execution order varies.
- **Thread.currentThread().isVirtual()** is a Java 21 API; source cannot compile on JDK 17.
- **try-with-resources** closes the ApplicationContext only after SpringApplication.run finishes; the runner executes during run.

Do not use self-invocation for @Async: calling **this.inspect()** from within the same bean instead of through a Spring proxy may prevent the @Async annotation from being applied.

### 5.4. Run with virtual threads enabled

From the Maven project root directory:

~~~bash
# Check JDK runtime and Maven wrapper:
java -version
./mvnw -version

# Linux/macOS:
./mvnw spring-boot:run

# Windows PowerShell/cmd uses:
# .\mvnw.cmd spring-boot:run
~~~

With JDK 21+, Boot 3.5.x, no custom executor, and the example configuration above, **the lines printed by the application itself** are expected to be:

~~~text
property=true
runnerVirtual=false
executorClass=SimpleAsyncTaskExecutor
executorVirtual=true
asyncVirtual=true
~~~

This is **the stdout printed by the program**, not the entire console; Maven/Spring Boot also log startup messages. The program does not need to listen on HTTP. **runnerVirtual=false** serves as a reminder that ApplicationRunner runs on the startup bootstrap thread, while tasks submitted to the executor and @Async execute on virtual threads.

### 5.5. Run again with virtual threads disabled

Package the executable JAR:

~~~bash
./mvnw package
~~~

If the artifact/version from Initializr is **virtual-thread-demo / 0.0.1-SNAPSHOT**, compare with:

~~~bash
java -jar target/virtual-thread-demo-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=false
~~~

If the artifact name or version differs, substitute the exact JAR filename in target.

**In the same configuration without a custom Executor**, typical output when disabled:

~~~text
property=false
runnerVirtual=false
executorClass=ThreadPoolTaskExecutor
executorVirtual=false
asyncVirtual=false
~~~

Compare the two runs:

| Observation | Enabled true | Disabled false |
| --- | --- | --- |
| Environment property | true | false |
| Main/runner bootstrap thread | platform | platform |
| Auto-configured AsyncTaskExecutor | SimpleAsyncTaskExecutor virtual | ThreadPoolTaskExecutor |
| Task submitted to auto executor | virtual thread | platform thread |
| @Async in separate bean | virtual thread | platform thread |

**Condition:** the table assumes the default case without custom executors/schedulers. For real applications, measure **isVirtual()** in the corresponding workloads instead of just reading class names.

## 6. Why do spring.task.execution.pool.* properties no longer work as before?

When Boot selects **ThreadPoolTaskExecutor**, the properties:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=32
spring.task.execution.pool.queue-capacity=200
~~~

tune a **platform thread pool** according to Spring Boot's policy.

When Boot selects **SimpleAsyncTaskExecutor using virtual threads**, **there is no longer the same core/max/queue pool model**. Therefore, pool configuration properties like the ones above **no longer control the number of virtual threads the way you might expect**; the Spring Boot Reference explicitly states that thread-pool properties have no effect when using virtual threads.

Do not conclude that virtual threads have a concurrency limit of 32 just because you still see **max-size=32** in an old configuration file. Some other executor properties (such as thread name prefix) may still be relevant depending on implementation and version; verify accurately instead of claiming the entire **spring.task.execution** namespace is ignored.

Similarly, **SimpleAsyncTaskScheduler** ignores scheduler pool properties. Do not expect **spring.task.scheduling.pool.size=10** to create a pool of 10 virtual threads.

### Where to limit concurrency?

Virtual threads are lightweight, yet **external systems are not infinite**:

- A database pool might only have 20 connections.
- An HTTP upstream might have a rate limit of 100 requests/second.
- A CPU only has a finite number of cores.
- A node has finite RAM and file descriptors.
- A downstream service can be overloaded if tens of thousands of requests are sent concurrently.

**Solution:** limit at the actual resource point, such as connection pools, semaphores, rate limiters, bulkheads, backpressure-aware queues, or an executor with a purposefully configured concurrency limit. Do not rely on platform-thread count as an implicit rate limiter and then assume removing that limit has no consequences.

Illustrative Java 21 example:

~~~java
Semaphore permits = new Semaphore(30);

try {
    permits.acquire();
    try {
        callRemoteService();
    } finally {
        permits.release();
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
~~~

This is an **illustrative code snippet**; you must import **java.util.concurrent.Semaphore**, define **callRemoteService()**, and apply an appropriate interruption handling policy. The point is to limit **30 concurrent calls** at the external service boundary, rather than trying to configure 30 platform threads.

Do not use a semaphore in a way where permits can be held while another path forgets to release them. Try/finally is mandatory to prevent permit leaks.

## 7. @Async and @EnableAsync when virtual threads are enabled

**@Async** does not work automatically just because the virtual threads=true property is set. In a Spring application using proxy-based async execution, you generally need:

1. **@EnableAsync** to enable processing of methods annotated with @Async.
2. The method must belong to a **Spring-managed bean** and be called **through a proxy**.
3. The executor must be resolved properly by Spring or **AsyncConfigurer**.
4. If the method returns **CompletableFuture**, handle errors and results in the caller rather than uncontrolled fire-and-forget.

Example:

~~~java
@Service
public class PricingService {

    @Async
    public CompletableFuture<Long> findPrice() {
        return CompletableFuture.completedFuture(100L);
    }
}
~~~

This is an **illustrative code snippet**, requiring imports, a package, and an application with @EnableAsync. This task is purely for demonstration; because there is no blocking I/O, virtual threads provide no significant benefit.

### Scenarios where property=true yet @Async remains a platform thread

- A custom **Executor** bean causes Boot's auto-configuration to back off.
- An **AsyncConfigurer** selects a different executor.
- The method is called directly via **this.method()**, so the proxy does not intercept it.
- Code does not use Spring-managed @Async and creates platform threads manually.
- A library uses its own internal thread pool.
- Some tasks are dispatched on platform threads by design in the application.

Spring Boot 3.5 provides the mechanism:

~~~properties
spring.task.execution.mode=force
~~~

When using **force** under documented supported conditions, Boot can still configure **applicationTaskExecutor** even if a custom Executor bean exists, and prioritize the Boot auto-configured executor for the documented integrations. However, a custom **AsyncConfigurer** can still determine @Async's executor. Do not use force blindly if the system needs separate threading per workload.

### Verify instead of guessing

Inside the method you actually want to run on a virtual thread:

~~~java
boolean virtual = Thread.currentThread().isVirtual();
log.info("virtualThread={}", virtual);
~~~

This is an illustrative snippet assuming a **log** logger is already defined. Measure both thread type and throughput/latency/CPU, and avoid emitting per-request thread names into monitoring with excessive cardinality.

## 8. @Scheduled and special caveats with virtual threads

When **@EnableScheduling** is present, Boot can auto-configure a TaskScheduler. With virtual threads enabled, Spring Boot 3.5 typically provides **SimpleAsyncTaskScheduler** instead of ThreadPoolTaskScheduler if not overridden by a custom bean.

Illustrating a scheduled task:

~~~java
@Component
public class HeartbeatJob {

    @Scheduled(fixedRate = 5000)
    public void tick() {
        System.out.println("virtual="
                + Thread.currentThread().isVirtual());
    }
}
~~~

This snippet **is not standalone** because it requires packages/imports for Component and Scheduled, **@EnableScheduling** on a configuration class, and a runtime that stays alive long enough. **fixedRate** is used to demonstrate the scheduler creating separate task executions; exact output depends on the scheduler, version, and injected configuration.

### Why does fixedDelay need attention?

According to Spring Framework 6.2, **SimpleAsyncTaskScheduler** uses a single scheduler thread and has an important exception: **fixed-delay tasks run on the scheduler thread**, in order to preserve the delay-after-previous-completion semantics. When the number of fixed-delay tasks is large or involves long blocking I/O, that single scheduler thread can become a bottleneck.

**Spring documentation recommendation:** consider **fixedRate** or **cron triggers** when wanting to leverage SimpleAsyncTaskScheduler's virtual-thread-per-task model.

Note that fixedRate/cron does not mean you can run CPU-bound tasks indiscriminately or skip concurrency protection. The scheduler only decides when to trigger; downstream resources remain limited.

### Why is spring.main.keep-alive=true needed?

**Virtual threads are daemon threads**. The JVM can exit when no non-daemon threads remain, even if periodic virtual threads are still waiting to run. A **non-web application mainly running @Scheduled** can unexpectedly exit right after bootstrapping completes if no other thread keeps the JVM alive.

Spring Boot 3.5 recommends:

~~~properties
spring.main.keep-alive=true
~~~

This property helps Boot keep the JVM alive in that situation. It does not replace shutdown policy: when the ApplicationContext is closed normally, lifecycle components must still be stopped and resources released.

For one-shot CLI programs that run and exit, you may **not need** keep-alive; the demo in section 5 uses try-with-resources to close the context in a controlled manner. For a long-running scheduler service, verify keep-alive and actual liveness/readiness states.

## 9. Virtual threads in Spring MVC and WebFlux

### With Spring MVC on Tomcat/Jetty

When using an embedded servlet server configured by Boot to support virtual threads, request-handling controllers can run on virtual threads. To observe directly in Spring MVC, you can use a dedicated controller:

~~~java
@RestController
class ThreadInfoController {

    @GetMapping("/thread-info")
    Map<String, Object> threadInfo() {
        return Map.of(
                "virtual", Thread.currentThread().isVirtual(),
                "threadName", Thread.currentThread().getName());
    }
}
~~~

This is an **illustrative code snippet**, requiring package and imports for **java.util.Map**, **RestController**, and **GetMapping** in a project with **spring-boot-starter-web**, Java 21+, and a compatible Boot servlet server.

In a default **Spring MVC / embedded Tomcat** project on Spring Boot 3.5, when the property is enabled and the server uses the virtual-thread request executor, the **virtual** field is expected to be true inside the controller. Verify on your specific Boot/server version rather than writing unconditional assertions for every servlet container or custom configuration.

### With Spring WebFlux

WebFlux/Reactor Netty uses an event-loop/non-blocking model. Enabling the property does not turn all event-loop threads into virtual threads. **Blocking execution support** integrations can use the Boot-configured virtual-thread executor in certain execution paths, but you need to inspect **which code actually offloads blocking work**.

One note: if you put a blocking JDBC call directly onto WebFlux's event loop, enabling the property does not automatically ensure that call is moved onto a virtual thread. Check Reactor scheduling, task execution support, and code instrumentation.

## 10. Performance limitations and technical risks

### 10.1. Virtual threads optimize concurrency, not CPU throughput

If the workload is heavy CPU computation:

~~~text
1 task: 500ms CPU computation
1,000 tasks: all need many CPU cycles
~~~

Creating 1,000 virtual threads does not produce extra CPU cores. Virtual threads are suited when each task spends most of its time **waiting on I/O**. For CPU-bound work, you still need to bound concurrent tasks according to core and memory budgets.

### 10.2. Pinning and JDK versions

On **Java 21**, certain blocking operations inside **synchronized** blocks or native frames can cause a virtual thread **to be pinned to its carrier platform thread**, reducing concurrency scalability.

**Java 24** introduces JEP 491, which greatly improves virtual thread synchronization: when blocking inside corresponding synchronized sections, the JVM can release the carrier instead of pinning as before. That does not mean every form of pinning or uncooperative blocking is impossible on Java 24+. Boot 3.5 recommends Java 24+ for a better virtual threads experience, if platform and compatibility allow.

When investigating:

- Use **Java Flight Recorder (JFR)** and virtual-thread/pinning events.
- Leverage **jcmd** and thread dumps per JDK version.
- Read JVM documentation for the exact running version.
- Measure blocked/waiting ratios, carrier saturation, and throughput under realistic load.

Do not conclude the entire application "has zero pinning" just because you upgraded from Java 21 to a newer JDK.

### 10.3. ThreadLocal still works, but caching patterns can be expensive

Many virtual threads mean there can be very many ThreadLocal values. A library using **ThreadLocal.withInitial(...)** to cache large buffers may allocate one buffer **per virtual thread**, instead of reusing them across a small platform-thread pool.

Review:

- ThreadLocals holding heavy objects and data lifetimes.
- SecurityContext/MDC propagation when running async.
- Context propagation across different thread boundaries.
- Libraries requiring thread affinity or specific native operations.

Do not assume ThreadLocal is completely forbidden with virtual threads; the issue is **cost and usage semantics** when thread counts can become very large.

### 10.4. Limits of connection pools and upstream APIs

For example, if 10,000 virtual threads call JDBC concurrently while the pool only has 30 connections, most of them will **wait for a connection**; increasing the number of Java tasks does not turn 30 connections into 10,000 connections. Under overload, request latency or memory usage still climbs.

You should:

- Set JDBC pool timeouts and HTTP client connect/read timeouts.
- Throttle concurrency using semaphores/bulkheads.
- Measure queueing time and downstream saturation.
- Define retries with backoff/jitter to avoid retry storms.
- Reduce unbounded fan-out to downstream services.

### 10.5. Virtual threads do not automatically guarantee structured concurrency or cancellation

Enabling the property does not turn every group of tasks into a structure with deadlines, interruption propagation, joining, and failure handling. For @Async or CompletableFuture, the caller must still manage results, timeouts, and exceptions. Do not fire-and-forget tasks with important side effects just because virtual threads are cheap.

### 10.6. Security, monitoring, and stability

Large numbers of virtual threads require different observability:

- CPU utilization, heap usage, and GC.
- HTTP request concurrency and p95/p99 latency.
- DB connection pool active/pending counts.
- Downstream timeouts/retries/rate limiting.
- Scheduler delays and task execution errors.
- JFR events and thread dump sampling.
- Runtime cancellations during shutdown.

These numbers must be compared under the same load and same environment before and after enabling the property. Do not compare an idle local machine against production traffic and attribute the difference to virtual threads.

## 11. Common errors when enabling the property

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Building or running on Java 17 | Virtual threads require Java 21+ | Upgrade build/runtime JDK and appropriate base image |
| Property=true set yet runnerVirtual=false | Runner still runs on bootstrap thread | Check inside executor/@Async or HTTP request |
| @Async still shows virtual=false | Custom Executor/AsyncConfigurer or self-invocation | Check proxy, actual executor, and Boot auto-configuration |
| applicationTaskExecutor bean differs from expected | Custom Executor or task execution mode | Review Spring Boot task execution configuration |
| spring.task.execution.pool.max-size set but doesn't cap virtual threads | SimpleAsyncTaskExecutor is not a thread pool | Limit concurrency at actual resources |
| @Scheduled doesn't run after app boot | Daemon virtual threads don't keep JVM alive | Check spring.main.keep-alive=true |
| fixedDelay jobs slow/sequential | SimpleAsyncTaskScheduler uses scheduler thread for fixed delay | Consider fixedRate/cron and suitable workload |
| Spring WebFlux event-loop stays platform | Not every event loop switches to virtual | Distinguish non-blocking/reactive from blocking offload |
| Enabling virtual drops throughput | Pinning, downstream contention, ThreadLocal overhead | Profiling and benchmarking; consider JDK 24+ |
| Thousands of tasks waiting on DB cause timeouts | Limited connection pool | Bounded concurrency, pool timeout, backpressure |
| App exits when only scheduler exists | No non-daemon threads remain | Check keep-alive and lifecycle |
| Manually created new Thread or fixed thread pool stays platform | Property only affects Boot-managed integrations | Explicitly configure executor/virtual thread per task |
| Property disabled yet thread is still virtual in custom library | Library uses Java API to create virtual threads directly | Locate the library's thread creation source |
| Benchmark results vary unclearly | Differing load, warm-up, JDK, pool limits | Hold A/B conditions constant, record p95/p99 and resource metrics |

## 12. Plan for enabling virtual threads in production

You do not need to switch the entire system at once. Follow this process:

### Step 1: Identify versions and workloads

- Confirm **java -version** inside the real container/host.
- Select a Spring Boot version that supports the property and corresponding integrations.
- List flows to improve: servlet requests, @Async jobs, scheduled jobs, or blocking integrations.
- Classify CPU-bound vs I/O-bound.

### Step 2: Audit custom executors

Search for **Executor**, **AsyncTaskExecutor**, **AsyncConfigurer**, **ThreadPoolTaskExecutor**, task scheduler beans, and libraries managing their own thread pools. Determine whether Boot's property affects the intended execution paths.

**Do not preflight executor beans by adding another bean with the same name** before understanding resolution rules. Measure the class type and **isVirtual()** inside the task itself.

### Step 3: Run controlled A/B tests

Run the same workload with:

~~~properties
# Group A
spring.threads.virtual.enabled=false
~~~

and:

~~~properties
# Group B
spring.threads.virtual.enabled=true
~~~

Keep JDK, RAM/CPU limits, replica count, database pool, concurrency, request mix, and downstream services fixed. Measure throughput, p95/p99 latency, errors, heap/GC, and resource usage.

### Step 4: Control resources

Add or verify limits on network clients, DB pools, rate limiters, and semaphores/bulkheads. For workloads with periodic tasks, verify keep-alive and scheduler fixed-delay behavior.

### Step 5: Run canary/rollback

Enable for a small percentage of instances or via a profile/env property. Have a rollback path by setting:

~~~properties
spring.threads.virtual.enabled=false
~~~

and restarting/redeploying per the system's rollout procedure. This is a **bootstrap property**; it does not dynamically alter running executors when editing properties at runtime without a dedicated reconfiguration mechanism.

### Step 6: Evaluate failure modes

Test shutdown, cancellation, upstream outages, DB pool exhaustion, CPU spikes, service overload, scheduler callbacks, and native libraries. If a library uses large ThreadLocal caches or holds monitors for long durations on Java 21, watch for pinning/memory overhead.

## 13. Comprehension check exercises

**Question 1.** Does simply declaring **spring.threads.virtual.enabled=true** turn every Thread in the application into a virtual thread?

**Question 2.** Why can **Thread.currentThread().isVirtual()** return false in ApplicationRunner while @Async returns true?

**Question 3.** When virtual threads are enabled, which classes does Boot typically auto-configure for AsyncTaskExecutor and TaskScheduler if no custom beans interfere?

**Question 4.** Why doesn't **spring.task.execution.pool.max-size=8** automatically cap the number of virtual threads?

**Question 5.** An @Async method is called via **this.method()**. Does property=true guarantee the method runs asynchronously on a virtual thread?

**Question 6.** Why does a non-web application primarily running @Scheduled need to pay attention to **spring.main.keep-alive**?

**Question 7.** With SimpleAsyncTaskScheduler, why does Spring recommend fixedRate/cron over fixedDelay to leverage virtual threads?

**Question 8.** Has Java 24 solved every virtual thread performance issue? Which type of pinning does it improve?

**Question 9.** A service uses 10,000 concurrent virtual threads calling a DB with a 20-connection pool. What is the bottleneck?

**Question 10.** Does setting property=true on WebFlux automatically convert all Reactor Netty event-loop threads into virtual threads?

**Suggested answers:**

1. No, only supported integration/auto-configuration paths or Java code that explicitly uses virtual threads.
2. The runner runs on the startup thread; @Async is dispatched through Boot's executor when properly configured.
3. Virtual SimpleAsyncTaskExecutor and virtual SimpleAsyncTaskScheduler.
4. Because the virtual executor is not a ThreadPoolTaskExecutor with those core/max/queue semantics.
5. No; self-invocation bypasses proxy-based @Async.
6. Virtual threads are daemon threads; the JVM can exit when no non-daemon threads remain.
7. Fixed-delay runs on a single scheduler thread; fixed-rate/cron fits thread-per-task better.
8. No; JEP 491 improves synchronized monitor pinning, but other bottlenecks still exist.
9. The DB pool/downstream throughput, not the virtual thread count.
10. No; WebFlux has an event-loop/non-blocking model and separate blocking offload.

## 14. Takeaways and official references

**Spring Boot switch:**

~~~properties
spring.threads.virtual.enabled=true
~~~

**Requirement: Java 21+; prioritize verifying on the actual running JDK.**

When using standard Spring Boot 3.5 auto-configuration:

~~~text
spring.threads.virtual.enabled = true
        |
        +--> auto AsyncTaskExecutor
        |      SimpleAsyncTaskExecutor (virtual threads)
        |
        +--> auto TaskScheduler (if needed)
        |      SimpleAsyncTaskScheduler (virtual-thread aligned)
        |
        +--> selected supported Boot/Web Server integrations
               |
               v
        Check Thread.currentThread().isVirtual()
        inside the actual task
~~~

**Three points not to miss:** this change does not convert all threads; thread pool tuning no longer works the same way; virtual threads are daemon threads and keep-alive must be checked for scheduler-only applications. Always measure with realistic workloads rather than assuming property=true means faster.

### Source references

1. Spring Boot 3.5 Reference — SpringApplication / Virtual Threads: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot 3.5 Reference — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
3. Spring Framework 6.2 Reference — Task Execution, SimpleAsyncTaskExecutor, SimpleAsyncTaskScheduler: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
4. Java 21 API — Thread.isVirtual(): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#isVirtual()
5. OpenJDK JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
6. OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24): https://openjdk.org/jeps/491

Runnable examples target **Spring Boot 3.5.x, Spring Framework 6.2.x, JDK 21+**. Before applying to production, cross-check official documentation for the exact Spring Boot/JDK version, custom executors, servlet container, and scheduling mechanism in use.