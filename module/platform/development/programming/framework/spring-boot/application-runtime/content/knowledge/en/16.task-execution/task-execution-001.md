# Main Thread, Server Threads, and Task Threads in the Spring Boot Application Lifecycle

## 1. The problem: why does the application still accept requests after main() has finished?

When writing simple Java programs, beginners often assume that the entire application terminates when **main(String[] args)** returns. With Spring Boot running an embedded server, that understanding is incorrect: the **main execution thread**, **HTTP serving threads**, and **background task execution threads** have different responsibilities and lifecycles.

For example, a Spring MVC application running embedded Tomcat:

~~~text
Thread "main"
  |
  +-- SpringApplication.run(...)
  |     +-- prepare Environment, create ApplicationContext
  |     +-- refresh(), create beans, start web server
  |     +-- run ApplicationRunner/CommandLineRunner
  |     +-- publish ApplicationReadyEvent
  |
  +-- run(...) returns ConfigurableApplicationContext
  +-- main() returns
                  |
                  | JVM still has threads keeping the process alive
                  v
HTTP server accept/worker threads
  +-- receive GET /orders request
  +-- invoke Controller -> Service -> Repository
  +-- return response
                  |
                  v
Application executor/scheduler threads
  +-- @Async runs tasks submitted from another bean
  +-- @Scheduled triggers scheduled jobs
  +-- infrastructure-managed listeners/message consumers
~~~

**Key takeaway:** **SpringApplication.run(...) is not an infinite loop receiving HTTP requests on the main thread**. It initializes the ApplicationContext and required infrastructure; requests are subsequently handled by threads orchestrated by the server/framework.

Three types of threads to distinguish:

- **Main thread:** typically performs synchronous startup. In a normal Java program, this thread is commonly named **main**; the thread name can be changed, so the name is not an API contract.
- **Server threads:** used by Tomcat, Jetty, Undertow, or Reactor Netty to accept connections and handle networking/requests. The thread model depends on the server and Servlet/Reactive stack.
- **Task threads:** used by TaskExecutor, TaskScheduler, schedulers, or integration libraries to run work not necessarily on the request path. **@Async** and **@Scheduled** are two common examples.

This article uses **Java 17+, Spring Boot 3.3.13, and Spring Framework 6.1**. Thread names printed below are runtime observations, not fixed identifiers that every version or environment must use.

## 2. Which stages of SpringApplication does the main thread participate in?

In a typical application:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

The JVM invokes **main(...)** on an initial thread. Calling **SpringApplication.run(...)** performs bootstrap in the following general order:

1. Prepare the **Environment** and required configuration sources.
2. Create an **ApplicationContext** appropriate for the application type.
3. Load configuration and **BeanDefinition** entries.
4. Call **ApplicationContext.refresh()** to run post-processors, register BeanPostProcessors, instantiate normal singletons, and start required infrastructure.
5. In a web application, create/start the **embedded web server** according to the context lifecycle.
6. Publish **ApplicationStartedEvent** after refresh.
7. Run **ApplicationRunner** and **CommandLineRunner** beans in their configured order.
8. Publish **ApplicationReadyEvent** and transition availability state to accepting traffic when startup succeeds.
9. Return **ConfigurableApplicationContext** to the caller.

Diagram:

~~~text
Java launcher
    |
    v
main(String[] args)
    |
    +-- SpringApplication.run(...)
           |
           +-- prepare Environment
           +-- create ApplicationContext
           +-- refresh ApplicationContext
           |      +-- BeanFactoryPostProcessor
           |      +-- create required singletons
           |      +-- start embedded web server
           |      +-- publish ContextRefreshedEvent
           |
           +-- ApplicationStartedEvent
           +-- ApplicationRunner / CommandLineRunner
           +-- ApplicationReadyEvent
           +-- readiness ACCEPTING_TRAFFIC
           |
           v
       return context
    |
    v
main() finishes
    |
    +-- DOES NOT mean context.close()
    +-- DOES NOT mean JVM exit if non-daemon threads remain
~~~

**Common misconception:** the startup sequence in the diagram is a lifecycle order, **not a guarantee that every callback always runs solely on the main thread**. Default synchronous listeners typically run directly on the event-publishing thread, but an application can configure an asynchronous multicaster, spawn background tasks in callbacks, or use custom infrastructure.

If an **ApplicationRunner** performs 30 seconds of synchronous work, the **SpringApplication.run(...)** call must wait for the runner to finish. In that case, the ready milestone may be delayed even though the server already created HTTP-accepting threads earlier.

### 2.1. run() returning and the JVM stopping are two different events

In a normal web app, after **run(...)** returns, **main(...)** can finish while the embedded server and required threads keep running, so the Java process continues serving requests.

The JVM normally exits when **no non-daemon threads** remain active (and no suitable process keep-alive mechanism is active). Spring Boot does not require you to write:

~~~java
while (true) {
    // keep main from finishing
}
~~~

The snippet above is an **anti-pattern**: it occupies the main thread, makes shutdown hard to control, and does not properly address the lifecycle. Let Spring Boot and the embedded server manage the application's lifetime.

**Exception to consider:** a **non-web** program with no work keeping the JVM alive may exit when main finishes; background tasks, schedulers, and especially virtual threads can change this behavior. Do not infer process lifetime solely from the existence of a bean.

### 2.2. run() returning does not mean the server has stopped

A proper way to start a web app:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

// Can log or use context for appropriate purposes.
// Do not automatically close a web service's context here.
~~~

An approach **unsuitable for a long-running web service**:

~~~java
try (ConfigurableApplicationContext context =
             SpringApplication.run(MyApplication.class, args)) {
    // When the try block finishes, context.close() will be called.
}
~~~

**try-with-resources** in the second example causes the application to close the context **as soon as the block finishes**. That can suit a CLI tool meant to run to completion and exit, but it shuts down a web server immediately after startup unless intended.

## 3. Embedded server threads in a Servlet application

When **spring-boot-starter-web** is present without special overriding configuration, Spring Boot 3.3 typically selects **embedded Tomcat** with a **Spring MVC/Servlet** application.

Tomcat uses components related to sockets, acceptors, pollers, and workers/executors to accept connections and invoke the servlet pipeline. A request thread may execute:

~~~text
HTTP client
    |
    v
Tomcat socket / connector
    |
    v
Request worker thread
    |
    +-- Servlet filters
    +-- DispatcherServlet
    +-- HandlerMapping / HandlerAdapter
    +-- @RestController method
    +-- @Service / @Repository
    +-- write HTTP response
    |
    v
Worker returns to pool to serve other requests
~~~

When controller code calls:

~~~java
System.out.println(Thread.currentThread().getName());
~~~

in a Spring MVC application running Tomcat, you commonly see a name like:

~~~text
http-nio-8080-exec-1
~~~

**This is only an example of a typical naming pattern**, not an absolute guarantee: names vary by port, connector, Tomcat version, executor, configuration, and thread mode. You should rely on **thread role and infrastructure** rather than writing business logic that branches on thread name prefixes.

### 3.1. Request threads are not the main thread

With an endpoint:

~~~java
@RestController
class GreetingController {

    @GetMapping("/greet")
    String greet() {
        return "handled-by=" + Thread.currentThread().getName();
    }
}
~~~

this is a **snippet** in Spring MVC assuming imports are present. HTTP requests to **/greet** typically run on a server worker thread. **main** may have already returned earlier; thus the two points in time and two threads are not the same.

### 3.2. How does blocking in Spring MVC affect the system?

If a request worker performs long synchronous I/O:

~~~java
@GetMapping("/slow")
String slow() throws InterruptedException {
    Thread.sleep(5000);
    return "done";
}
~~~

then in the standard Servlet thread-per-request model, this worker is occupied while sleeping and cannot serve other requests. This is a **latency demonstration snippet**, not a recommendation to use **Thread.sleep** in controllers.

Under high concurrency, the worker pool is bounded. Increasing the worker count does not automatically fix I/O lacking timeouts, unindexed database queries, or backend outages. You need to measure workload, configure timeouts, bound concurrency, and use appropriate async or reactive mechanisms when suitable.

### 3.3. Spring MVC can handle asynchronous processing at the HTTP level

An MVC controller can return **Callable**, **DeferredResult**, **CompletableFuture**, **WebAsyncTask**, or an appropriately integrated reactive type. Spring MVC can then release the initial request thread and re-dispatch once the result is ready.

**Do not equate adding @Async to a service with the entire HTTP request automatically becoming non-blocking.** For example, a controller calling **future.join()** still blocks the request thread until the task completes, even though the task itself runs on another executor.

### 3.4. Do not arbitrarily share one thread pool across all roles

The web server manages request workers; the application's **TaskExecutor** can serve @Async; **TaskScheduler** is meant for scheduled work. One saturated executor pool does not necessarily mean Tomcat's pool also runs out of workers, yet shared dependencies such as CPU, DB pools, and network can still bottleneck the entire system.

For long I/O or heavy tasks, clearly define which pool owns the work, queue limits, backpressure capacity, and task cancellation timing.

## 4. Spring WebFlux and Reactor Netty have a different thread model

If an application uses **spring-boot-starter-webflux** with **Reactor Netty** as the server, the common model relies on **event-loop threads** instead of dedicating a separate blocking platform thread per request for the entire processing duration.

An event-loop thread can handle many connections:

~~~text
Reactor Netty event loop
    |
    +-- receive data from socket A
    +-- run non-blocking callbacks
    +-- continue with socket B
    +-- resume processing when I/O signals arrive
~~~

Because a single event loop multiplexes many I/O operations, **heavy blocking calls on the event loop are a serious design flaw**. Do not invoke **Thread.sleep**, blocking JDBC, or a blocking HTTP client directly on the event loop without offloading execution appropriately.

In Reactor:

- **subscribeOn(scheduler)** affects where subscription/source work executes.
- **publishOn(scheduler)** switches the execution context for downstream operators.
- **Schedulers.boundedElastic()** is commonly used to isolate blocking work when integrating non-reactive libraries, with managed resource bounds.

This describes the **reactive model**; it does not mean WebFlux automatically moves all blocking calls onto worker threads. Nor should you switch to WebFlux just to run a background job.

### 4.1. Comparing Servlet and Reactive

| Characteristic | Spring MVC on embedded Tomcat | WebFlux with Reactor Netty |
| --- | --- | --- |
| Typical model | Worker thread processes servlet request | Event loop and reactive pipeline |
| Blocking in handler | Holds worker while waiting | Can block event loop, affecting many connections |
| Async coordination | MVC async support and suitable executor | Publisher, Reactor Scheduler, backpressure |
| Thread name | Often shaped like **http-nio-...-exec-N** | Often shaped like **reactor-http-nio-N** |
| Rule of thumb | Do not misuse request workers for very long tasks | Do not block the event loop |
| Limitations | Worker pool/connection pool are bounded | Scheduler/pool and downstream remain bounded |

**Thread names in the table are illustrative.** In systems running WebFlux on a servlet container, custom executor configurations, or virtual threads, thread assignment may differ from the table.

## 5. Spring-managed task threads: @Async and TaskExecutor

Spring Framework supports **@Async** for methods invoked through a proxy. To enable this capability in a typical application, add **@EnableAsync** to a configuration class.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfiguration {
}
~~~

When another bean invokes an **@Async** method and the call is intercepted by the proxy, the method can run on a thread belonging to a **TaskExecutor**, while the caller receives a handle such as **CompletableFuture** or proceeds without waiting for void methods.

~~~text
HTTP request worker
    |
    +-- service.submitTask() via Spring proxy
    |       |
    |       +-- submit work to TaskExecutor
    |       |
    |       v
    |     executor worker runs @Async method
    |
    +-- controller can continue doing other work
~~~

### 5.1. @Async does not mean manually creating new Threads

Example:

~~~java
@Service
class ReportWorker {

    @Async("reportExecutor")
    public CompletableFuture<String> createReport() {
        String threadName = Thread.currentThread().getName();
        return CompletableFuture.completedFuture(threadName);
    }
}
~~~

This is a **snippet** requiring an executor bean named **reportExecutor** and corresponding imports. Spring uses a proxy + the specified executor. Developers do not need to manually call:

~~~java
new Thread(() -> createReport()).start();
~~~

Creating threads manually like this is an **anti-pattern** for common application tasks because shutdown management, concurrency limits, exception handling, and observability become difficult.

### 5.2. Return values and exceptions of @Async

An asynchronous method can return **CompletableFuture<T>**. When calling:

~~~java
CompletableFuture<String> future = worker.createReport();
~~~

the caller can use **thenApply**, **thenCompose**, **whenComplete**, or **exceptionally** to handle results/errors without blocking immediately. Calling **future.join()** **blocks the caller until the task completes**, and exceptions are typically wrapped in **CompletionException**.

With **@Async void**, errors cannot be propagated via a Future to the caller; Spring can log them via **AsyncUncaughtExceptionHandler**. When business logic needs result tracking and explicit error handling, prefer a Future return type or an appropriate durable task/messaging mechanism.

### 5.3. Self-invocation does not trigger @Async in proxy mode

A common mistake:

~~~java
@Service
class BatchService {

    public void start() {
        processAsync(); // Same object, does not go through Spring proxy.
    }

    @Async("reportExecutor")
    public void processAsync() {
        // May still run on the caller thread!
    }
}
~~~

This is a **bug-illustration snippet**. In default proxy mode, an internal call **this.processAsync()** is not intercepted by the Spring proxy, so offloading to an executor is not guaranteed.

The usual fix is to move the **@Async** method to another bean, inject that bean, and call it through the proxy. Do not rely solely on method names or annotations while ignoring actual dispatch semantics.

### 5.4. ThreadPoolTaskExecutor and resource bounds

Spring Boot 3.3 can auto-configure an **AsyncTaskExecutor** when no custom Executor bean is present in the context; on Java 17, the typical default is **ThreadPoolTaskExecutor**. Configuration and executor selection also depend on existing executor beans in the context.

For example, you can configure:

~~~properties
spring.task.execution.thread-name-prefix=app-task-
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100
~~~

This example applies **when using the auto-configured executor**. If the application defines its own Executor bean, check which pool is actually used rather than assuming these properties apply to every executor.

**A pool with bounded size and queue** constrains resource usage and forces the application to define an overload policy. Do not leave queues unbounded and then mistake rising latency for an unexplained network issue.

## 6. Scheduled task threads: @Scheduled and TaskScheduler

Spring supports **@Scheduled** for scheduled or periodic work. You must enable **@EnableScheduling** in configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableScheduling
class SchedulingConfiguration {
}
~~~

An example:

~~~java
@Component
class CacheRefreshJob {

    @Scheduled(initialDelay = 1000, fixedDelay = 5000)
    public void refreshCache() {
        System.out.println(
                "SCHEDULED | " + Thread.currentThread().getName());
    }
}
~~~

This is a snippet with corresponding imports. **initialDelay** waits before the first execution; **fixedDelay** measures the interval from when **the previous execution finishes** until the next one starts (in milliseconds in this example).

**@Scheduled does not automatically run on HTTP request threads.** Spring uses a dedicated scheduler to trigger callbacks. In Boot 3.3 with platform threads, the auto-configured scheduler is typically **ThreadPoolTaskScheduler** with one thread by default, though an application can define a custom scheduler or use virtual threads on Java 21+.

### 6.1. fixedDelay, fixedRate, cron

| Setting | General meaning | Notes |
| --- | --- | --- |
| **fixedDelay** | Wait an interval after the previous run finishes | Long-running work pushes back the next run |
| **fixedRate** | Trigger cadence measured from start times | Depending on scheduler, may lag if threads are exhausted |
| **cron** | Run according to a schedule expression | Pay attention to timezone, DST, and server clock |
| **initialDelay** | Delay the first execution | Useful when startup needs stabilization time |

With a single-threaded scheduler pool, one blocked task can delay other periodic tasks. With multiple threads or work handed off to another executor, tasks can run concurrently. Therefore you must design for **idempotence**, deduplication, and preventing overlapping runs when business rules forbid them.

**Note:** do not assume **@Scheduled** is a durable job queue or distributed mechanism. When running multiple application instances, each instance can independently trigger the same scheduled method, causing duplicate execution. To ensure only one instance processes the job, use a distributed lock, centralized scheduler, or appropriate job infrastructure.

### 6.2. Can a scheduled task run before ApplicationReadyEvent?

Yes. Scheduling registration and activation happen around context refresh; with a short **initialDelay** and lengthy startup/runners, a scheduled callback may execute while pre-ready steps are still ongoing. **Do not assume every scheduled task is guaranteed to run only after ApplicationReadyEvent**.

If a task must wait for readiness, design an explicit state gate or start the scheduler/consumer at the appropriate lifecycle stage. Do not use **Thread.sleep** to guess when the application is ready.

## 7. Runnable Java 17+ example: observing all three thread types

The example below includes:

1. The **main** thread calling SpringApplication.run and continuing after run returns.
2. **Tomcat** handling **GET /threads** requests on a request worker thread.
3. **@Async("demoExecutor")** executing a method in a pool prefixed **task-**.
4. **@Scheduled** recording the **sched-** scheduler thread name.
5. **ApplicationRunner** and **ApplicationReadyEvent** illustrating startup milestones.
6. **@PreDestroy** logging when the context closes.

**Scope:** Spring Boot 3.3.13, Java 17+, Spring MVC/embedded Tomcat. This is a lifecycle observation example, not a complete production architecture.

### 7.1. Maven structure

~~~text
thread-life-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/threads/ThreadsRuntimeApplication.java
  src/test/java/com/example/threads/ThreadBoundaryTest.java
~~~

**pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>thread-life-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**src/main/resources/application.properties:**

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

This exercise uses port 8080. If the port is occupied, change the port or run with **--server.port=8081** and adjust the curl URL accordingly. Graceful shutdown is enabled explicitly to observe context closing behavior under Boot 3.3.

### 7.2. Single-file application source

**src/main/java/com/example/threads/ThreadsRuntimeApplication.java:**

~~~java
package com.example.threads;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class ThreadsRuntimeApplication {

    public static void main(String[] args) {
        System.out.println("MAIN BEFORE | " +
                Thread.currentThread().getName());

        SpringApplication app =
                new SpringApplication(ThreadsRuntimeApplication.class);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        ConfigurableApplicationContext context = app.run(args);

        System.out.println("MAIN AFTER | " +
                Thread.currentThread().getName() +
                " | active=" + context.isActive());

        // Do not close context here: HTTP server needs to continue running.
    }

    @Bean("demoExecutor")
    ThreadPoolTaskExecutor demoExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("task-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("sched-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(5);
        return scheduler;
    }

    @Bean
    ApplicationRunner printRunnerThread() {
        return args -> System.out.println("RUNNER | " +
                Thread.currentThread().getName());
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("READY | " +
                Thread.currentThread().getName());
    }
}

record ThreadSnapshot(
        String requestThread,
        String taskThread,
        String scheduledThread) {
}

@Service
class BackgroundWorker {

    @Async("demoExecutor")
    public CompletableFuture<String> reportThread() {
        String name = Thread.currentThread().getName();
        return CompletableFuture.completedFuture(name);
    }
}

@Component
class ScheduledReporter {

    private final AtomicReference<String> latest =
            new AtomicReference<>("not-yet-run");

    @Scheduled(initialDelay = 1000, fixedDelay = 3000)
    public void recordSchedulerThread() {
        String threadName = Thread.currentThread().getName();
        latest.set(threadName);
        System.out.println("SCHEDULED | " + threadName);
    }

    String latestThreadName() {
        return latest.get();
    }

    @PreDestroy
    public void onDestroy() {
        System.out.println("DESTROY | " +
                Thread.currentThread().getName());
    }
}

@RestController
class ThreadInspectionController {

    private final BackgroundWorker worker;
    private final ScheduledReporter scheduledReporter;

    ThreadInspectionController(
            BackgroundWorker worker,
            ScheduledReporter scheduledReporter) {
        this.worker = worker;
        this.scheduledReporter = scheduledReporter;
    }

    @GetMapping("/threads")
    ThreadSnapshot threadSnapshot() {
        return new ThreadSnapshot(
                Thread.currentThread().getName(),
                worker.reportThread().join(),
                scheduledReporter.latestThreadName());
    }
}
~~~

Java allows **one public top-level class** and package-private top-level classes/records in the same file. **ThreadsRuntimeApplication** is the public class matching the filename; **BackgroundWorker**, **ScheduledReporter**, and **ThreadInspectionController** carry stereotype annotations and are component-scanned in package **com.example.threads**.

### 7.3. Why does the example define two separate thread pool beans?

- **demoExecutor** is a **ThreadPoolTaskExecutor** explicitly targeted via **@Async("demoExecutor")**. It provides threads **task-1**, **task-2** when tasks arrive.
- **taskScheduler** is a **ThreadPoolTaskScheduler** that Spring scheduling infrastructure can look up by the conventional name **taskScheduler**; **@Scheduled** methods run on thread **sched-1** in this example configuration.
- The HTTP request pool is managed by Tomcat and **does not use task- or sched- names** by default in this configuration.

Separating the pools lets you directly distinguish roles when observing thread names. In practice, names are not security identifiers and can be configured differently.

**Important:** **worker.reportThread()** is called through the bean injected into the controller, meaning the call goes through the Spring proxy. Calling an @Async method via **this.method()** within the same bean will not offload to the executor under normal proxy mode.

### 7.4. Build and run

From the directory containing pom.xml:

~~~bash
mvn -q -DskipTests package
java -jar target/thread-life-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
mvn -q -DskipTests package
java -jar target/thread-life-demo-1.0.0.jar
~~~

After startup, from another terminal:

~~~bash
curl http://localhost:8080/threads
~~~

Some lines the program may print at startup:

~~~text
MAIN BEFORE | main
RUNNER | main
READY | main
MAIN AFTER | main | active=true
~~~

**This is the expected order of synchronous startup lines in the sample configuration**, when the default event multicaster is synchronous and the launcher does not rename the main thread. Spring/Tomcat logs may interleave; additionally, **SCHEDULED** lines may interleave because they run on a separate thread depending on startup timing.

An illustrative JSON response after the scheduler has run at least once:

~~~json
{
  "requestThread": "http-nio-8080-exec-1",
  "taskThread": "task-1",
  "scheduledThread": "sched-1"
}
~~~

Do not assert that the request worker name must be exact **http-nio-8080-exec-1**: it may be **http-nio-8080-exec-2** or another name. The task thread may be **task-2** depending on the pool. If a request arrives before the first **@Scheduled** execution, **scheduledThread** will validly be **"not-yet-run"**.

You will also see lines like:

~~~text
SCHEDULED | sched-1
~~~

printed periodically while the application runs. Exact names and counts depend on observation timing and machine configuration.

### 7.5. Why does the controller use join() only for demonstration?

The controller calls:

~~~java
worker.reportThread().join()
~~~

so the HTTP worker thread must **wait** for the async task to return a result before building the response. This is intentionally kept simple in the example to display both thread names in a single HTTP response.

**Do not infer this is optimal for heavy work.** In real applications, consider returning **CompletableFuture<ThreadSnapshot>** or an appropriate async response type to avoid holding the request thread just while waiting on a task. For processing that does not need an immediate response, use a controlled job queue or an appropriate event/messaging model.

## 8. Tests verifying two thread boundaries

A unit test calling the controller directly runs on the **JUnit test thread**, which does not prove that requests are actually served by server worker threads. Therefore, to verify the boundary between servlet requests and @Async, run a real server using **@SpringBootTest(webEnvironment = RANDOM_PORT)**.

Create **src/test/java/com/example/threads/ThreadBoundaryTest.java**:

~~~java
package com.example.threads;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ThreadBoundaryTest {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void httpWorkerAndAsyncWorkerAreDistinct() {
        @SuppressWarnings("unchecked")
        Map<String, String> body =
                rest.getForObject("/threads", Map.class);

        assertNotNull(body);
        String requestThread = body.get("requestThread");
        String taskThread = body.get("taskThread");

        assertNotNull(requestThread);
        assertNotNull(taskThread);
        assertTrue(taskThread.startsWith("task-"));
        assertNotEquals(requestThread, taskThread);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**The test actually starts the embedded server on a random port**, avoiding port 8080 conflicts with other applications in CI. **TestRestTemplate** sends requests to the real server. Assertions only check that **taskThread starts with task-** and **differs from requestThread**, without depending on a fixed Tomcat thread naming pattern.

Because this example uses **join()**, the controller waits for the CompletableFuture to complete before returning JSON. That matches the sample's intended behavior, though it does not prove the request worker was freed while waiting.

### 8.1. Testing the scheduler without arbitrary sleeps

You can unit-test the logic called by **recordSchedulerThread** separately without testing the exact instant the scheduler invokes it. If the goal is to verify **@Scheduled** wiring/registration, use a context test with a timeout-bounded wait and a flag/CountDownLatch updated by the job.

**Do not assert an exact invocation count after exactly 1000 ms**, because CI load, GC, CPU contention, and startup timing make wall-clock assertions flaky. For scheduled work, tests should assert an **eventual condition within a reasonable timeout** rather than strict ordering between scheduler and main threads.

### 8.2. Testing lifecycle events

For **ApplicationReadyEvent**, if you want to confirm a listener ran, use a test bean recording the event or an observable state rather than matching verbatim stdout. Synchronous runners in the example are invoked by Boot before the ready milestone.

Do not assume event listeners always run on main when an application has configured an asynchronous **ApplicationEventMulticaster**: the actual contract is that listener callbacks run on **the thread used by event multicasting**.

## 9. Main, web server, and tasks in real-world scenarios

### 9.1. Startup: the server may accept requests before ready

The embedded web server is created/started during refresh. **ApplicationRunner** and certain startup callbacks may still be running afterward.

~~~text
refresh() creates/starts web server
          |
          +-- server socket may already be listening
          |
ApplicationRunner runs validation/cache warm-up
          |
ApplicationReadyEvent
          |
ReadinessState.ACCEPTING_TRAFFIC
~~~

If requests hit the port directly between these milestones, the system may receive them **before mandatory startup logic completes**. In orchestrators like Kubernetes, readiness probes/routing should help avoid sending traffic before the application is ready.

**Do not treat the “Tomcat started on port ...” log as meaning the application is completely ready.** Conversely, ApplicationReadyEvent does not automatically guarantee all external services are healthy unless the application checks them.

### 9.2. Request invokes an async task and waits

~~~text
HTTP worker             Async executor worker
    |                           |
    +-- call service proxy ----->
    |                         run task
    |                           |
    +-- join(): wait <----------+
    |
    +-- send HTTP response
~~~

The async task uses a different thread, yet the controller waiting via join still consumes the request worker's time. If the workload needs immediate responsiveness, choose a non-blocking async endpoint or move to a fire-and-track model with a job ID and status endpoint.

### 9.3. Request only submits a task and returns immediately

~~~text
HTTP worker
   |
   +-- submit work to bounded executor/queue
   +-- return 202 Accepted + jobId
           |
           v
Async task worker
   |
   +-- process work
   +-- save result/error status
~~~

This is an **architectural diagram**, not logic fully implemented in the section 7 example. In real deployments, a durable queue is needed if losing jobs on process death is unacceptable; **@Async with an in-memory executor does not automatically guarantee job persistence or crash recovery**.

### 9.4. Scheduled jobs do not depend on a specific request

A **@Scheduled** method is triggered on schedule by the scheduler without waiting for an HTTP client. Even with zero incoming requests, the scheduler can still run. When an application has multiple replicas, each replica can independently run scheduled jobs.

Therefore jobs must distinguish **local schedules** from **distributed schedules**, and use leader election/locks/job schedulers if execution must happen only once across the entire system.

## 10. What happens when stopping the application?

Upon receiving a normal stop signal (for example **SIGTERM**, closing the context, or runtime-managed shutdown), Spring Boot and Spring Framework can perform steps such as:

1. Begin closing the **ApplicationContext**.
2. Publish **ContextClosedEvent**.
3. Stop **SmartLifecycle** beans in phases.
4. With graceful shutdown, instruct the server to stop accepting new requests via supported mechanisms and give in-flight requests time to finish.
5. Stop executors/schedulers and invoke destruction callbacks (**@PreDestroy**, **DisposableBean**, destroy methods) on beans.
6. Finish closing resources and allow the process to exit when JVM conditions permit.

Exact ordering among infrastructure components, executors, and beans depends on phase/dependency settings and versions. Do not design logic assuming **@PreDestroy is guaranteed to run before or after a callback of every other bean**.

~~~text
SIGTERM / context.close()
          |
          v
ApplicationContext closing
          |
          +-- ContextClosedEvent
          +-- SmartLifecycle.stop(...)
          +-- graceful web server shutdown
          +-- stop scheduler / task executor
          +-- @PreDestroy / destroy callbacks
          |
          v
Resources are released
          |
          v
JVM can exit
~~~

**Cleanup is not guaranteed to run when a process receives SIGKILL, crashes, loses power, or when a container is forcibly terminated immediately.** Work that must not be lost requires durable state storage and recovery design.

### 10.1. Graceful shutdown in Spring Boot 3.3

Enable explicitly:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

With embedded servers supported by Spring Boot 3.3, graceful shutdown occurs during context closing, at an early phase of stopping **SmartLifecycle**. The server gives in-flight requests a window to complete and blocks new requests in a server-specific manner.

**A timeout does not mean every request or job is guaranteed to finish.** If a request holds a connection longer than the grace period, the system may have to terminate; if container orchestration sends SIGKILL before grace completes, cleanup time is cut short. You must align **terminationGracePeriodSeconds** (Kubernetes or equivalent) with Boot's shutdown policy and real I/O timeouts.

### 10.2. The shutdown hook is a separate thread

SpringApplication typically registers a shutdown hook to close the context when the JVM goes through normal shutdown. The hook **is not the main thread** and is not an HTTP worker.

In the section 7 example, when stopping with Ctrl+C or an appropriate SIGTERM, a line like:

~~~text
DESTROY | SpringApplicationShutdownHook
~~~

may appear with a similar thread name, though **you must not assume that is the only possible name**. If code explicitly calls **context.close()** from another thread, **@PreDestroy** may run on the thread calling close or on a thread used by lifecycle infrastructure.

**Do not create a custom shutdown hook that holds locks indefinitely.** When shutting down an application, relying on Spring lifecycle mechanisms, timeouts, and explicit dependency ordering is cleaner than manually managing lots of Threads.

### 10.3. Tasks still running when the context closes

With **ThreadPoolTaskExecutor** and **ThreadPoolTaskScheduler**, you can configure shutdown behavior to wait for tasks within bounds and stop accepting new submissions. In the example, both pools use:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(5);
~~~

These APIs express a waiting policy but **do not strictly guarantee that every long-running task completes**. Blocked tasks, new jobs submitted during shutdown, or abnormal failures still require a dedicated strategy.

For tasks that must survive restarts/crashes, do not treat an in-memory executor as a durable queue. Use a database/outbox/broker with appropriate retry/idempotence handling.

## 11. Virtual threads: an important exception on Java 21+

**The runnable example in section 7 uses Java 17 and platform threads.** On **Java 21+**, Spring Boot 3.3 supports enabling virtual threads:

~~~properties
spring.threads.virtual.enabled=true
~~~

When no custom Executor bean exists and virtual threads are enabled, Boot can use **SimpleAsyncTaskExecutor** creating virtual threads for @Async, and **SimpleAsyncTaskScheduler** for scheduled work. Defaults and pool properties vary by configuration.

**Note:** the section 7 example explicitly declares **ThreadPoolTaskExecutor** and **ThreadPoolTaskScheduler** and references the executor by name. Therefore **enabling spring.threads.virtual.enabled=true does not automatically turn the example's two custom pools into virtual-thread pools**.

### 11.1. Daemon threads and JVM keep-alive

Virtual threads are **daemon threads**. If the entire JVM has no remaining non-daemon threads and no keep-alive mechanism is active, **the JVM may exit once main returns**, even if you expect a scheduled task to keep running.

Spring Boot 3.3 supports:

~~~properties
spring.main.keep-alive=true
~~~

to ensure a mechanism keeps the JVM alive when remaining threads are daemon threads. When a non-web application relies primarily on @Scheduled running on virtual threads, this is a critical setting to verify.

**Do not conclude that every web server using virtual threads will exit immediately when main finishes**; server threads and keep-alive mechanisms vary by stack and configuration. Test empirically with the exact application setup in use.

### 11.2. Virtual threads do not automatically fix blocking, deadlocks, or missing bounds

Virtual threads reduce thread-per-task overhead for certain blocking I/O workloads. However:

- Connection pools, remote services, and CPU remain finite resources.
- Do not spawn millions of concurrent tasks simply because each virtual thread is cheaper than a platform thread.
- Monitor pinning and synchronized/blocking sections that reduce efficiency depending on JDK version.
- Bound concurrency according to downstream capacity.
- In a reactive stack, do not use virtual threads as an excuse to arbitrarily block the event loop.

Thus you must distinguish **the ability to create many threads** from **the system's capacity to process many concurrent tasks**.

## 12. Context propagation and thread-bound data

When work moves from an HTTP worker to an async executor thread, data bound to the original thread **is not automatically transferred in full**. Typical examples:

- **MDC** in logging.
- **SecurityContext** in certain Spring Security modes.
- **Transaction context** bound to a thread in the imperative stack.
- **RequestContextHolder** and request-scoped data.
- Any custom **ThreadLocal**.

Example:

~~~java
@Async("demoExecutor")
public void process() {
    // Do not assume that the HTTP worker's ThreadLocal
    // exists intact on task-1.
}
~~~

**Do not capture the HTTP request object and retain it for async use after the request has ended**, unless the framework/contract allows it. Request attributes have their own lifecycle.

### 12.1. Safer ways to propagate context

- For business data, **pass explicit IDs or immutable DTOs** to the async method.
- For tracing/MDC, use context propagation solutions or a **TaskDecorator** compatible with your logging/observability stack.
- For security, use **DelegatingSecurityContextAsyncTaskExecutor** or an appropriate security context propagation mechanism if truly needed.
- For transactions, define transaction boundaries on the task thread; a caller's **@Transactional** does not automatically transfer the same transaction to an @Async worker thread.

Do not rely on **InheritableThreadLocal** as a general solution for thread pools: worker threads are reused and can retain stale data or leak across requests.

### 12.2. Thread safety of singleton beans

A singleton bean can be invoked concurrently from:

- Multiple HTTP request workers.
- One or more @Async workers.
- Scheduler threads.
- Listener/message-consumer threads.

Therefore, shared mutable fields in a service must be designed to be thread-safe. For example, using **AtomicReference<String>** in ScheduledReporter to update the scheduler thread name so an HTTP request worker can read it. Do not use a plain **String lastThread** field updated from the scheduler and read from HTTP workers while ignoring visibility/concurrency issues.

When handling concurrent tasks, consider immutable state, **ConcurrentHashMap**, bounded synchronization, or delegating updates to an appropriate thread-safe data component.

## 13. Monitoring and debugging the three thread types

### 13.1. Logs include thread names, but do not use names for business control flow

A logging pattern often includes the thread name:

~~~text
2026-11-09 INFO [main] Starting application
2026-11-09 INFO [http-nio-8080-exec-1] Handling request
2026-11-09 INFO [task-1] Executing background work
2026-11-09 INFO [sched-1] Scheduled refresh
~~~

This is **illustrative**, not the exact log output of the program in section 7. Thread names help identify which mechanism is executing, but they are not a stable API. Also log request IDs, trace IDs, and job IDs appropriately; avoid logging sensitive data.

### 13.2. Using thread dumps and signs to look for

When the application is slow or hangs on shutdown:

1. Capture a thread dump using an appropriate tool such as **jcmd** or JDK diagnostic tooling.
2. Identify **RUNNABLE**, **WAITING**, **TIMED_WAITING**, and **BLOCKED** threads.
3. Look for HTTP workers with multiple stacks stuck at the same I/O or lock.
4. Look for **task-*** workers stuck on a queue, remote call, or synchronized block.
5. Look for a scheduler thread running a single job for too long.
6. Check which non-daemon threads remain alive after the context should have closed.
7. Correlate the thread dump with pool metrics, server connector metrics, and backend connection pool metrics.

**RUNNABLE does not always mean active CPU usage**; a thread in native I/O may report a state different from expectations. Combine profiling, metrics, and tracing before drawing conclusions.

### 13.3. Metrics to observe

| Component | Key metrics | Why |
| --- | --- | --- |
| HTTP server | Active requests, busy workers, queue/connections, and latency | Detect request intake bottlenecks |
| Async executor | Active threads, pool size, queue depth, rejections | Detect task backlog/overload |
| Scheduler | Task duration, missed runs, error count | Detect delayed or failing jobs |
| Application startup | Startup duration, runner duration, ready transition | Distinguish slow startup from slow runtime |
| Shutdown | Grace period, in-flight requests, task termination time | Assess safe shutdown capability |
| Downstream | DB pool usage, HTTP timeouts, retry rate | Understand bottlenecks outside the JVM |

Spring Boot Actuator, Micrometer, and monitoring systems can support these depending on configuration. Do not assume every metric is automatically enabled in every starter: you must enable the corresponding observability/metrics features.

## 14. Common design mistakes

### 14.1. Thinking the main thread is the request thread

Wrong. After run, the server has its own workers/event loops. Printing **Thread.currentThread().getName()** in main and in a controller will show different threads in a typical setup.

### 14.2. Adding Thread.sleep to main to keep the server running

Unnecessary in a properly configured web app. Rely on the server/lifecycle mechanisms managed by Boot instead of writing infinite loops or sleeps to keep the process alive.

### 14.3. Closing the context right after SpringApplication.run in a web service

A **try-with-resources** or **context.close()** right after run shuts down the server. Use explicit closing only when a CLI/test application actually intends to exit, not for a long-lived web app.

### 14.4. Assuming @Async always spawns another thread

Incorrect if **@EnableAsync** is not enabled, the method is not called through a proxy, or code calls **this.method()** within the same bean. Verify wiring and actual execution threads.

### 14.5. Calling future.join() and thinking the request is non-blocking

Join still waits for the result. The task may run on another worker, but the HTTP worker sits waiting. Use an MVC async return type or an appropriate job architecture when you need to free the request thread.

### 14.6. Letting @Scheduled execute the same job across multiple replicas uncontrolled

Each instance can run its own schedule. If a job must run system-wide exactly once, you need distributed coordination, idempotence, and state persistence.

### 14.7. Putting blocking JDBC calls directly on the Reactor event loop

This can block the thread serving many connections. Offload blocking work to an appropriate scheduler or use a reactive driver if suitable; never block the event loop.

### 14.8. Using unbounded thread pools without error management

Uncontrolled queue growth can lead to memory pressure, increased latency, and severely delayed tasks. Configure pool size, queue capacity, rejection policy, and monitoring.

### 14.9. Relying on strict ordering between scheduled jobs and ApplicationReadyEvent

A scheduled job may run while runners/ready are still progressing, depending on timing and configuration. If a task must run only after ready, design an explicit startup condition.

### 14.10. Expecting @PreDestroy to always run when a container is forcibly killed

Cleanup is not guaranteed during SIGKILL/crashes. Critical work must have recovery mechanisms and durable data.

### 14.11. Treating shutdown grace as a guarantee that all async jobs finish

Graceful web-server shutdown focuses on requests/lifecycle. Executors have their own shutdown policies; timeouts or forced termination signals can still interrupt jobs.

### 14.12. Passing ThreadLocal from request to @Async and leaking data

Full implicit propagation does not happen, and custom ThreadLocals can retain stale data when pool threads are reused. Use standard context propagation or pass explicit DTOs/IDs.

### 14.13. Using thread names for business checks

Logic like **if (threadName.startsWith("http-"))** is fragile. Thread names can vary by server or pool, and virtual threads change the model. Use abstractions, dependency injection, and business context instead of thread names.

### 14.14. Using @Async/@Scheduled as a durable message queue

In-memory task executors/schedulers do not inherently provide retry across restarts, dead-letter queues, or exactly-once delivery. Work requiring delivery guarantees needs persistence, a broker, or an appropriate job platform.

## 15. Production readiness checklist

- [ ] Understand that **main**, **HTTP worker/event loop**, **TaskExecutor**, and **TaskScheduler** have distinct roles.
- [ ] Do not close the web ApplicationContext immediately after run.
- [ ] Do not use infinite loops/sleeps to keep main alive.
- [ ] Startup runners have timeouts and do not unnecessarily delay readiness.
- [ ] Understand that the server may open its port before the ready milestone.
- [ ] @Async is enabled, invoked through a proxy, and uses the intended executor.
- [ ] Separate work needing immediate results from background jobs that can return 202.
- [ ] Do not call join/get in a request if the goal is to release the request thread.
- [ ] Async pools have sensible queue/size/rejection/monitoring settings.
- [ ] @Scheduled uses the right fixedDelay/fixedRate/cron and timezone.
- [ ] Multi-replica jobs enforce deduplication/idempotence when required.
- [ ] Do not block the Reactor Netty event loop.
- [ ] Graceful shutdown policy and container timeouts are properly aligned.
- [ ] Executors/schedulers have shutdown policies and do not accept uncontrolled new jobs.
- [ ] Do not rely on @PreDestroy during SIGKILL/crashes.
- [ ] Propagate context/tracing/security/transactions across thread boundaries via appropriate mechanisms.
- [ ] Singleton state is designed to be thread-safe.
- [ ] On Java 21+ with virtual threads enabled, daemon behavior and keep-alive have been verified.
- [ ] Have integration tests distinguishing HTTP workers from @Async workers against a real server.
- [ ] Logs/metrics do not expose secrets and do not use thread names as business rules.

## 16. Self-check questions

**Question 1.** When **SpringApplication.run(...)** returns and main finishes, does the embedded web server necessarily stop immediately?

**Answer:** No. The context/server can remain active and the JVM still has threads needed to serve requests. Main finishing alone does not equal context.close or process exit.

**Question 2.** Does a Spring MVC controller handling a request run on the main thread?

**Answer:** Normally no. Tomcat/the servlet container dispatches requests to worker threads. Do not write logic depending on a fixed thread name.

**Question 3.** Why can a Spring MVC controller calling **future.join()** after invoking @Async still bottleneck HTTP workers?

**Answer:** Because join blocks the caller until the future completes. The task uses another worker, but the request worker still has to wait.

**Question 4.** Is an @Async method called via **this.method()** within the same bean guaranteed to run on an executor?

**Answer:** No. Under standard proxy mode, self-invocation bypasses the Spring proxy, so @Async is not intercepted.

**Question 5.** A @Scheduled fixedDelay=5000 task takes 8 seconds to run; will the next execution start exactly 5 seconds after the previous start?

**Answer:** No. With fixedDelay, the delay is measured **after the previous execution finishes**, so the next run begins after the 8-second task finishes plus another 5-second wait (excluding other scheduler delays).

**Question 6.** In WebFlux Reactor Netty, why should you not call Thread.sleep(5000) directly on the event loop?

**Answer:** Because the event loop can serve many connections; blocking it stalls multiple concurrent I/O streams.

**Question 7.** Does ApplicationReadyEvent mean the server only starts opening its port at that exact moment?

**Answer:** No. The server can be started during refresh, before runners and the ready event. Ready is a milestone in the startup sequence, not the sole moment the socket begins listening.

**Question 8.** Can you rely on @Scheduled alone to guarantee a job runs only once across a multi-replica Kubernetes cluster?

**Answer:** Not automatically. Each replica can trigger the job, so coordination or a distributed lock is required if single execution is needed.

**Question 9.** Is @PreDestroy guaranteed to be called when a container sends SIGKILL?

**Answer:** No. SIGKILL and crashes do not guarantee running Java shutdown callbacks; durable recovery mechanisms are required.

**Question 10.** Does ThreadLocal data from an HTTP worker automatically appear in an @Async worker?

**Answer:** Not guaranteed. Use a task decorator/context propagation or pass required DTOs/IDs, and handle cleanup properly.

**Question 11.** Is the Tomcat thread name on every machine guaranteed to be **http-nio-8080-exec-1**?

**Answer:** No. That is only an example; names vary by port, connector, pool, server, and configuration.

**Question 12.** Why does **spring.main.keep-alive=true** matter when running tasks with virtual threads on Java 21+?

**Answer:** Virtual threads are daemon threads and therefore may not keep the JVM alive once non-daemon threads finish; keep-alive helps keep the process running in this case.

## 17. Summary

**The Spring Boot lifecycle involves multiple execution threads with distinct responsibilities**:

- **main** orchestrates bootstrap and synchronous callbacks of the run.
- **embedded web server** maintains network infrastructure and dispatches requests to servlet workers or reactive event loops.
- **TaskExecutor/TaskScheduler** execute async/scheduled work according to their own policies.

After **SpringApplication.run(...)** returns, a web application can continue serving requests. That does not mean main is running a server loop. When closing the context, Spring coordinates server lifecycle, schedulers, executors, and bean destruction; graceful shutdown is time-bounded and does not guarantee completing all work in every scenario.

When designing, separate request threads from background workers, avoid blocking the event loop, do not assume @Async runs off-thread merely because of the annotation, and protect shared state against concurrency. Use thread names for observation, never as a business contract. Write tests against a real server, monitor pools/queues, and account for virtual threads if moving to Java 21+.

## 18. Official references

- Spring Boot 3.3 — SpringApplication, Events and Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Embedded Servlet Containers: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Framework — Task Execution and Scheduling, @Async, @Scheduled: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — Lifecycle, SmartLifecycle and Shutdown: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Java 21 — Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html