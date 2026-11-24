# Avoiding Closing Resources While Dependent Components Are Still Active — Spring Boot 3.3

## 1. Problem and Goal

In Spring Boot, objects such as `DataSource`, HTTP clients, Kafka/RabbitMQ connections, file streams, sockets, task executors, or cache managers are often shared across multiple components. When a component is executing work backed by resource A, closing A too early can break the running process.

Example:

```text
A consumer is still processing a message
   |
   +-- Uses a JDBC transaction and sends an ACK via the broker client
   |
Application closes the context
   |
   +-- Broker client.close() runs too early
   |
   +-- Consumer tries to ACK => error, message may be reprocessed
```

**The goal is not to keep resources open forever, but to stop consumers before the resource owner closes the resource.** This requires distinguishing:

- **Bean initialization/destroy**: Spring creates and destroys beans according to the dependency graph.
- **Component running/stopping**: a consumer may still be performing work even after the bean has begun shutting down.
- **Async task completion**: issuing a stop request does not prove all tasks have actually stopped.
- **Resource ownership**: a service borrowing a resource must not close the shared resource itself.
- **Operational readiness**: a service can stop accepting new work before shutting down completely.

After this lesson, you should be able to explain `@PreDestroy`, `@DependsOn`, constructor injection, `SmartLifecycle.getPhase()`, `stop(Runnable)`, `ApplicationContext.close()`, Spring Boot graceful shutdown, and how to coordinate draining, timeouts, and retries in Java 21 / Spring Boot 3.3 code.

## 2. How Do Lifecycles Differ?

| Point in Time | Meaning | Misconception to Avoid |
| --- | --- | --- |
| Constructor | A Java instance has been created | The resource is not necessarily ready yet |
| Dependency injection | References to dependencies are provided | Background tasks are not necessarily done |
| `@PostConstruct` | Bean initialization callback | Does not automatically await futures it launches |
| `SmartLifecycle.start()` | Component starts operating | May happen before runners |
| `ApplicationReadyEvent` | Boot has finished startup and runners successfully | Does not prove all background tasks have completed |
| `SmartLifecycle.stop(Runnable)` | Stops operation, signals completion to lifecycle processor | Do not invoke the callback right when merely enqueuing stop work |
| `@PreDestroy` | Cleanup during bean destruction phase | Does not replace draining in-flight work |
| `ApplicationContext.close()` | Closes context, stops lifecycle beans, destroys singletons | Context cannot be started again after close |

The two easiest states to confuse are **"stop requested"** and **"fully stopped"**.

```text
RUNNING
  |
  | stop accepting new work
  v
STOPPING
  |
  | wait for in-flight tasks; flush/checkpoint/ACK; controlled cancellation
  v
STOPPED
  |
  | resource owner closes the resource
  v
CLOSED
```

`@PreDestroy` is invoked later during bean destruction, yet does not guarantee tasks using the resource have finished unless the consumer cooperates.

## 3. Who Has the Right to Close a Resource?

This can be split into three roles:

| Role | Responsibility | Example |
| --- | --- | --- |
| **Owner** | Creates, configures, closes the resource | Spring-managed `HikariDataSource`, HTTP client bean, broker connection factory |
| **Borrower/consumer** | Uses the resource, returns borrowed handles promptly | Repository, message handler, report exporter |
| **Coordinator** | Stops intake, drains work, orders shutdown | `SmartLifecycle`, listener container, job controller |

### 3.1. Do not close a shared DataSource from a service

```java
@Service
class InvoiceReport {
    private final DataSource dataSource;

    InvoiceReport(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    void run() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Perform SQL operations...
        }
    }
}
```

This is a **non-standalone illustrative snippet**, requiring imports and real query logic. `Connection.close()` usually returns the borrowed connection to the pool. However, the service **must not call `dataSource.close()`** when the pool is shared with other services: closing the pool is the resource owner/container's responsibility.

Conversely, if a method creates its own stream and uses it synchronously only:

```java
try (InputStream input = Files.newInputStream(path)) {
    return parse(input);
}
```

then `try-with-resources` is appropriate. It is **wrong** when the method passes `input` to a worker thread and exits the `try` block, because the stream will be closed before the worker can read it.

### 3.2. Spring-managed resource beans

Common mechanisms:

- `@Component` + `@PreDestroy`.
- `@Bean` and the corresponding destroy callback/destroy method.
- `DisposableBean.destroy()` or `AutoCloseable` properly managed by the bean lifecycle.
- `SmartLifecycle` to start/stop activity and coordinate start/stop with other components.

Do not let multiple consumers automatically call `close()` on the same shared object. Even if a resource has an idempotent `close`, that only reduces double-close errors—it **does not** fix closing too early.

## 4. Dependency Graph and @DependsOn

### 4.1. Constructor injection expresses real dependencies

```java
@Component
class AuditConsumer {
    private final SharedGateway gateway;

    AuditConsumer(SharedGateway gateway) {
        this.gateway = gateway;
    }
}
```

This snippet illustrates a `SharedGateway` bean not declared here. Because the consumer receives the gateway via its constructor, Spring knows the consumer depends on the gateway. For singleton beans, container-known dependency relationships ensure **dependent beans are destroyed before their dependency beans**.

When B genuinely uses A's API, constructor injection is clearer, type-safe, and easier to test than referencing bean names as strings.

### 4.2. Indirect dependencies and @DependsOn

If B needs A's initialization side effects without injecting A:

```java
@Component("startupRegistrar")
class StartupRegistrar {
}

@Component
@DependsOn("startupRegistrar")
class DependentWorker {
}
```

This is **illustrative code**, requiring imports. `@DependsOn` takes the **bean name** `startupRegistrar`; it tells Spring to initialize A before B. For singleton beans, this dependency also creates the reverse destruction order: B is destroyed before A.

Keep the distinction clear: `@DependsOn` orders **bean initialization/destruction**, yet **does not automatically force waiting for an async task using A**. If `DependentWorker.@PreDestroy` merely enqueues a future and returns, the provider can still close while the future has not finished.

### 4.3. Why is @Order not enough?

`@Order` is typically used to sort collections, runners, or callbacks at extension points that support ordering. It is **not a shutdown contract** for all singleton beans. To coordinate component start/stop, use `SmartLifecycle.getPhase()` together with the dependency graph; to await async completion, use proper futures/latches/acks/stop callbacks.

## 5. SmartLifecycle and Phase-Based Shutdown

Spring Framework 6.1 uses `DefaultLifecycleProcessor` to coordinate `Lifecycle`/`SmartLifecycle` beans.

- Components with **lower phase values start first**.
- Components with **higher phase values stop first**.
- Spring-known dependency relationships can **take precedence over phase**: a dependency starts before its dependent and stops after its dependent.
- Beans in the same phase with no explicit dependency should not be assumed to follow alphabetical order.
- `SmartLifecycle.isAutoStartup()` defaults to `true`: components can start during `refresh()` before `ApplicationRunner`.
- `SmartLifecycle.stop(Runnable)` lets a component signal when async shutdown has finished; the callback must be invoked once stop processing completes per policy.

Example:

```text
ResourceGateway:   phase = 0
MessageConsumer:   phase = 100

START: ResourceGateway.start() -> MessageConsumer.start()
STOP:  MessageConsumer.stop(callback) -> ResourceGateway.stop(callback)
```

This is the right design when the consumer needs the gateway to flush/ack at the end, and the gateway must stay alive until the consumer no longer uses it.

### 5.1. stop() differs from stop(Runnable)

With `SmartLifecycle`:

```java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    }
    finally {
        callback.run();
    }
}
```

This is a **synchronous stop** pattern. Calling the callback in `finally` keeps the lifecycle processor from waiting forever on error, yet **does not turn a failed cleanup into a success**. Production code must log/emit metrics for errors, report status, and have an explicit fallback.

If stopping is asynchronous, **do not** do:

```java
@Override
public void stop(Runnable callback) {
    executor.execute(this::drainAndClose);
    callback.run(); // WRONG: work may not have finished yet.
}
```

This is an anti-pattern, not standalone code; it requires an executor and matching method. The callback must be called after `drainAndClose` genuinely finishes, or after a timeout/error policy has reached a state where waiting can no longer continue.

### 5.2. Container lifecycle and close timing

`ConfigurableApplicationContext.stop()` asks running lifecycle components to stop, **without** destroying all singletons; it can be restarted if the implementation supports it.

`ConfigurableApplicationContext.close()` coordinates stopping lifecycle components and then destroys beans. A closed context cannot be reopened with `start()`.

Even when callbacks run in the right order, `close()` is not a durable transaction and does not guarantee tasks survive a crash or `SIGKILL`.

## 6. Runnable Java 21 and Spring Boot 3.3.13 Example

This non-web demo includes:

- `ResourceGateway`: simulated resource owner, `SmartLifecycle` phase **0**, rejects `use()` calls after stopping.
- `DependentConsumer`: injects `ResourceGateway`, `SmartLifecycle` phase **100**; during stop it still uses the gateway to perform a final drain before stopping.
- `LifecycleTrace`: records events into a list.
- `SafeShutdownApplication`: starts up, closes the context, and prints the entire trace after shutdown.
- `SafeShutdownTest`: verifies ordering with JUnit, without relying on `Thread.sleep`.

The demo simulates synchronous operations only, letting us verify **the lifecycle ordering contract** deterministically. For real background tasks, extend this with the completion protocol in Section 9.

### 6.1. File structure

```text
safe-shutdown-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/shutdown/
    │   ├── SafeShutdownApplication.java
    │   ├── LifecycleTrace.java
    │   ├── ResourceGateway.java
    │   └── DependentConsumer.java
    └── test/java/com/example/shutdown/
        └── SafeShutdownTest.java
```

### 6.2. Maven pom.xml

```xml
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
    <artifactId>safe-shutdown-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
```

Java 21 runs with Boot 3.3.13; the base starter provides Spring context, lifecycle, and Jakarta annotations. The test starter provides JUnit Jupiter.

### 6.3. LifecycleTrace.java

```java
package com.example.shutdown;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.stereotype.Component;

@Component
public class LifecycleTrace {
    private final CopyOnWriteArrayList<String> steps =
            new CopyOnWriteArrayList<>();

    public void add(String step) {
        steps.add(step);
    }

    public List<String> snapshot() {
        return List.copyOf(steps);
    }
}
```

This is the bean recording lifecycle steps. In the demo events run sequentially, though `CopyOnWriteArrayList` also supports recording traces from other threads when extended.

### 6.4. ResourceGateway.java

```java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class ResourceGateway implements SmartLifecycle {

    private final LifecycleTrace trace;
    private volatile boolean running;

    public ResourceGateway(LifecycleTrace trace) {
        this.trace = trace;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        running = true;
        trace.add("RESOURCE start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        running = false;
        trace.add("RESOURCE stop");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        }
        finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 0;
    }

    public synchronized void use(String taskName) {
        if (!running) {
            throw new IllegalStateException("Resource is already closed");
        }
        trace.add("RESOURCE used: " + taskName);
    }

    @PreDestroy
    void destroy() {
        trace.add("RESOURCE destroy");
    }
}
```

`start()`/`stop()` simulate opening/closing the resource; `use()` rejects calls if the resource has already stopped. This is not a real connection pool: every call is synchronous and order-verifiable.

`@PreDestroy` records the destroy step after lifecycle stop. With a real resource, this can be the final release step; ensure no other component is still using it.

### 6.5. DependentConsumer.java

```java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class DependentConsumer implements SmartLifecycle {

    private final ResourceGateway gateway;
    private final LifecycleTrace trace;
    private volatile boolean running;

    public DependentConsumer(ResourceGateway gateway, LifecycleTrace trace) {
        this.gateway = gateway;
        this.trace = trace;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        if (!gateway.isRunning()) {
            throw new IllegalStateException("Gateway must start first");
        }
        running = true;
        trace.add("CONSUMER start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        gateway.use("final-drain");
        running = false;
        trace.add("CONSUMER stop");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        }
        finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }

    @PreDestroy
    void destroy() {
        trace.add("CONSUMER destroy");
    }
}
```

`DependentConsumer` injects `ResourceGateway` via its constructor: **Spring knows the actual dependency**, so there is no need to add `@DependsOn` just to restate an already injected object. The consumer starts at phase 100; the phase-0 provider is already running.

When the context closes, the consumer performs `gateway.use("final-drain")` while the gateway is still open, and then reports stopped. Only afterward does the provider stop. The consumer's `@PreDestroy` runs before the provider's `@PreDestroy` due to the singleton dependency relationship.

**Note:** the example does not automatically wait on any other async task because it spawns no background tasks. In production, invoking a final `gateway.use()` must happen only after stopping new work intake and processing in-flight jobs per policy.

### 6.6. SafeShutdownApplication.java

```java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class SafeShutdownApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(SafeShutdownApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);
        LifecycleTrace trace = context.getBean(LifecycleTrace.class);

        try (context) {
            ResourceGateway resource = context.getBean(ResourceGateway.class);
            DependentConsumer consumer =
                    context.getBean(DependentConsumer.class);

            trace.add("MAIN resource=" + resource.isRunning()
                    + " consumer=" + consumer.isRunning());
        }

        trace.snapshot().forEach(System.out::println);
    }
}
```

`try (context)` closes the context in a controlled manner after startup succeeds. The trace is printed after destroy callbacks have executed. That eliminates any need to guess log ordering interleaved with the banner and Spring Boot messages.

### 6.7. Running and reading output

In the project directory:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/safe-shutdown-demo-0.0.1-SNAPSHOT.jar
```

Lines printed by `LifecycleTrace` after the context closes:

```text
RESOURCE start
CONSUMER start
MAIN resource=true consumer=true
RESOURCE used: final-drain
CONSUMER stop
RESOURCE stop
CONSUMER destroy
RESOURCE destroy
```

Explanation:

1. Phase-0 resource starts before phase-100 consumer.
2. When `SpringApplication.run()` returns, both components are running.
3. The consumer needs the resource for its final drain step, so `RESOURCE used: final-drain` appears before `CONSUMER stop`.
4. The provider stops only **after** the consumer, thanks to phases and dependencies.
5. The consumer singleton is destroyed before the provider singleton due to constructor dependency.
6. If the resource closed too early, `gateway.use(...)` would throw instead of completing the drain milestone.

**Do not mistake** this output as proof of async task completion: the demo only illustrates a synchronous operation finishing before the stop callback.

## 7. JUnit Test Verifying the Ordering

File `src/test/java/com/example/shutdown/SafeShutdownTest.java`:

```java
package com.example.shutdown;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SafeShutdownTest {

    @Test
    void dependentStopsBeforeResourceCloses() {
        LifecycleTrace trace;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             LifecycleTrace.class,
                             ResourceGateway.class,
                             DependentConsumer.class)) {
            trace = context.getBean(LifecycleTrace.class);
            assertTrue(context.getBean(ResourceGateway.class).isRunning());
            assertTrue(context.getBean(DependentConsumer.class).isRunning());
        }

        assertEquals(List.of(
                "RESOURCE start",
                "CONSUMER start",
                "RESOURCE used: final-drain",
                "CONSUMER stop",
                "RESOURCE stop",
                "CONSUMER destroy",
                "RESOURCE destroy"
        ), trace.snapshot());
    }
}
```

`AnnotationConfigApplicationContext` also includes the lifecycle processor and required annotation configuration processors. The test runs directly against the beans without starting a web server. The assertions verify the ordering of the entire lifecycle **without `Thread.sleep`**.

`mvn test` expects **one passing JUnit test** for this class when dependencies are correct; `mvn package` also runs tests under default Maven configuration.

## 8. When Real Async Tasks Exist: Stop Must Wait for Completion

### 8.1. Anti-pattern: calling back too early

```java
@Override
public void stop(Runnable callback) {
    executor.execute(this::drainOutstandingJobs);
    callback.run(); // WRONG: only enqueued, no guarantee work is done.
}
```

This is **illustrative, non-standalone code**; it requires an executor and drain method. Spring's lifecycle processor can proceed to stop the resource in the next phase while the task is still waiting for a worker thread.

A failing sequence:

```text
T0: consumer.stop(callback) starts
T1: consumer submits "drain" to thread pool
T2: callback.run() reports stopped
T3: provider.stop/close
T4: thread pool runs drain, calls provider.flush() -> resource closed
```

### 8.2. Timely completion callback

An **architectural illustration**, not a standalone compilable file:

```java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewJobs();

    CompletionStage<Void> drain = drainJobsWithDeadline();
    drain.whenComplete((unused, failure) -> {
        if (failure != null) {
            reportShutdownFailure(failure);
            applyTimeoutOrRetryPolicy();
        }
        markStopped();
        callback.run();
    });
}
```

Real code must also handle exceptions thrown **before** `drainJobsWithDeadline()` returns a stage. The callback must execute exactly once after all shutdown responsibilities per policy have been handled; never invoke it while jobs might still access the resource.

If draining fails and jobs remain running, never silently mark it "safe." There must be timeouts, cancellation/acknowledgment, persisted job state, and explicit resource-close handling.

### 8.3. Do not merely count in-flight work and forget the admission race

A common buggy logic pattern:

```java
if (accepting.get()) {
    inFlight.incrementAndGet();
    try {
        processJob();
    }
    finally {
        inFlight.decrementAndGet();
    }
}
```

This is an **illustrative snippet**. A race occurs when a task has read `accepting=true` without incrementing yet; meanwhile the stop thread sets `accepting=false`, observes `inFlight=0`, and closes the resource before the task uses it.

To fix this, **task registration and admission checks must be atomic with transitioning to STOPPING**: use a lock/condition, state machine, closeable semaphore, or a framework container supporting formal pause/drain.

### 8.4. Avoiding deadlocks from waiting on the same executor

Suppose an executor has only one worker:

```text
Single worker:
    stop() -> submits(flushTask) to the same executor
           -> future.get() waits for flushTask
Queue:
    flushTask is waiting for the worker to become free
```

The task cannot run because the sole worker is blocking while waiting for that exact task. Stop from an appropriate coordinator thread, or use a completion callback and a separate executor when needed. Never block waiting on a future on a thread needed to complete that future.

### 8.5. Timeouts and cancellation

`Future.get(timeout, unit)` or `CountDownLatch.await(timeout)` only provides **a deadline to wait**; a timeout does not automatically erase work from external systems.

- `cancel(false)` does not interrupt a running task.
- `cancel(true)` requests an interrupt, yet the task must cooperate to stop.
- External HTTP/DB operations need client-side timeouts.
- Tasks with side effects need idempotency/retries or compensation.
- Abrupt process loss requires a durable store if data loss is unacceptable.

## 9. Web Graceful Shutdown and Background Jobs

In Spring Boot 3.3, a web application can configure:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Web server graceful shutdown runs when the application context closes, attempting to stop accepting new requests and letting in-flight requests finish within the grace period. How new requests are rejected depends on the server implementation, proxies, and connection mode.

**Limitation:** if an HTTP request submitted a task to an executor and returned a response, that task is now **detached from the HTTP request lifecycle**. Web graceful shutdown does not automatically know that the job must be awaited. The component owning the jobs needs its own lifecycle drain, with a deadline fitting the orchestrator's shutdown window.

In Kubernetes:

1. Readiness/routing shifts to reduce traffic.
2. Context receives a controlled shutdown (typically via `SIGTERM`).
3. Web requests and background jobs are stopped/drained per policy.
4. Resources are closed after consumers.
5. If the grace period expires, the container may be killed.

`SIGKILL`/JVM crashes do not guarantee `@PreDestroy` or `SmartLifecycle.stop()` will run. For jobs to recover after a crash, persist state durably rather than relying solely on lifecycle hooks.

## 10. Real-World Scenarios

### 10.1. Kafka/RabbitMQ consumers

Prefer the listener container's official lifecycle stop: pause/unsubscribe, await in-flight handlers, acknowledge/commit offsets or roll back per policy, then close the broker connection. Never close a shared connection factory from an active handler. If a message can be redelivered after a crash, handle it idempotently.

### 10.2. Shared HTTP clients

A `WebClient`/HTTP client or SDK channel used in many places should not be closed by a borrowing service. Stop producers first, await pending requests, then let the owner close the connection pool. When a resource closes mid-request, callbacks may fail with connection resets or cancellations.

### 10.3. JDBC connection pools

Running transactions should finish or roll back cleanly before closing the pool. Client code should close borrowed `Connection`s via `try-with-resources`, never closing the entire shared `DataSource`.

### 10.4. Scheduled tasks

A `@Scheduled` job that has already started can keep running even if you cancel the future for subsequent runs. If the job uses repositories/clients, stop and drain the job before its dependencies are destroyed. Distinguish **stopping new schedule triggers** from **the current run having finished**.

### 10.5. Asynchronous file exports

If a method opens a stream and hands that stream to a worker, exiting `try-with-resources` closes the stream too early. Better: pass an immutable payload or path to the worker, and let the worker open and close the stream across the full scope it owns.

### 10.6. Shared ThreadPoolTaskExecutor

A service must not call shutdown on a shared executor bean itself. The pool owner or Spring context coordinates shutdown; block new submissions, track both queued and running tasks, and only then close dependencies. `setWaitForTasksToCompleteOnShutdown(true)` helps wait for tasks, yet is insufficient if clients/databases are destroyed while tasks are still using them.

## 11. Exceptions, Logging, and Observability

Shutdown failures are often hard to reproduce because they appear only during deploys/restarts. Monitor:

- Counts of received, running, queued, and remaining jobs when `STOPPING`.
- Drain duration and timeout/cancellation rates.
- Timestamps for `consumer.stop()` start/complete and `resource.close()` start/complete.
- Errors such as `Connection is closed`, `RejectedExecutionException`, `TaskRejectedException`, `IllegalStateException`.
- Context ID/instance ID, message ID/job ID, while avoiding logging secrets.
- Shutdown phase timeout and the grace period Kubernetes grants the pod.

Do not just log "shutdown requested" and treat it as "shutdown completed." Those two milestones must be separated whenever asynchronous work exists.

If cleanup fails, never `catch(Exception ignored)`: log an actionable reason, determine whether retry/cancellation applies, and still ensure the lifecycle processor is not left waiting forever for a missing callback.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Consumer closes shared `DataSource` | Other consumers cannot connect | Owner/container closes pool; consumer closes borrowed connection |
| `@PreDestroy` enqueues async work and returns | Resource destroyed prematurely | `SmartLifecycle.stop(Runnable)` and completion protocol |
| Stop callback fires immediately upon submit | Provider stops while consumer still works | Invoke callback after genuine drain |
| `@Order` used to force closing order | Does not establish lifecycle dependency | `getPhase()` and DI/`@DependsOn` |
| Provider has higher phase than dependent without declared dependency | Provider risks stopping first | Declare dependency and fix phases appropriately |
| `@Lazy` used to "keep a bean alive longer" | Does not solve shutdown order | Dependency graph and lifecycle |
| `inFlight==0` read unsynchronized with admission | Race; tasks still enter after stop | Atomic admission protocol |
| Stop waits on task in the same single-thread pool | Deadlock | Separate coordinator/worker and use async completion |
| Resource closes as soon as readiness switches to refusing | In-flight jobs still need it | Readiness first, drain second, close last |
| Relying solely on HTTP graceful shutdown | Background tasks keep running | Worker-specific stop/drain |
| Timeout too long | Deployment hangs or gets killed | Finite deadlines, checkpoints/retries |
| JVM crashes while expecting `@PreDestroy` | Callback never runs | Durable jobs, idempotency |
| Tests rely on `Thread.sleep` | Fails to prove ordering/completion | Latches, futures, trace assertions |

## 13. Pre-Deployment Checklist

1. Who creates the resource, who owns it, and who has authority to close it?
2. How many consumers, thread pools, or callbacks share it?
3. Does constructor injection express all real dependencies?
4. Are there indirect dependencies needing `@DependsOn`?
5. Do resource providers and consumers have suitable `SmartLifecycle` phases?
6. Does `stop(Runnable)` wait for drain completion rather than just submitting?
7. Are admission and in-flight tracking atomic with transitioning to `STOPPING`?
8. Are there queued tasks that have not started yet?
9. Are there unfinished transactions, HTTP requests, or message acknowledgments?
10. Are finite timeouts, cancellation policies, and retry states defined?
11. Could the executor used for stopping be shut down first by the same shutdown?
12. Is there a deadlock risk from waiting on the same worker?
13. Does `@PreDestroy` run after stopping work, or accidentally launch new work?
14. Are platform grace periods sufficient and consistent across layers?
15. Are error paths tested when shutdown fails or a resource stops responding?
16. Can jobs recover after a restart/crash?
17. Do metrics/logs distinguish shutdown requested from shutdown completed?
18. Has resource destruction order after consumer destruction been verified?

## 14. Hands-On Exercises

1. State the differences among `@PostConstruct`, `SmartLifecycle.start()`, and `ApplicationReadyEvent`.
2. Why does a bean being destroyed not guarantee every task it submitted has finished?
3. In the demo, why does the phase-0 resource start before the phase-100 consumer?
4. Why does the consumer stop before the gateway and remain able to call `use("final-drain")`?
5. Why is constructor injection better than accessing resources via `static`?
6. When should you use `@DependsOn` instead of constructor dependency?
7. Why is `@Order(1)` not a reliable way to close a resource last?
8. If `stop(Runnable)` merely enqueues stop work and calls back immediately, what bug can occur?
9. Add a `CountDownLatch` for a task using the gateway, verifying the gateway is not closed before the callback completes.
10. Write a test where `resource.use()` throws an error after stop.
11. Set the resource to phase 100 and the consumer to phase 0 while keeping the constructor dependency; how might Spring prioritize the dependency relationship?
12. When the context only calls `stop()` without `close()`, has `@PreDestroy` run on the singleton resource yet?
13. In `InvoiceReport`, why should you close the borrowed `Connection` but not the `DataSource`?
14. Why can `try-with-resources` in the caller be wrong when passing a stream to an async worker?
15. Design a `RUNNING → STOPPING → STOPPED` state machine with race-free admission.
16. Why does `inFlight.incrementAndGet()` after `accepting.get()` still have a race?
17. With a single-worker consumer, why does submitting cleanup and waiting on that same worker deadlock?
18. Propose a policy when jobs fail to finish before the shutdown timeout.
19. Why does graceful HTTP shutdown not necessarily wait for tasks submitted by a request?
20. Design shutdown for a Kafka consumer: pause, drain, ACK, close connection.
21. Explain the limitations of `Future.cancel(true)` and interrupts.
22. Why does a resource still being live during `@PreDestroy` not guarantee it remains live for a late-running async callback?
23. Which metrics should be monitored to detect a resource closing before its consumer?
24. If a pod receives `kill -9`, which callbacks are not guaranteed?
25. When is a durable queue/outbox required instead of relying solely on an in-memory executor?

**Completion criteria:** run the Spring Boot example, understand ownership and the dependency graph, accurately explain the start–drain–stop–destroy order, coordinate `SmartLifecycle` callbacks with in-flight work, and avoid mistaking graceful shutdown for a zero-data-loss guarantee.

## 15. Official Documentation

- Spring Framework 6.1 — Using depends-on: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html
- Spring Framework 6.1 — `@DependsOn`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DependsOn.html
- Spring Framework 6.1 — `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — PostConstruct & PreDestroy: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Boot 3.3 — Graceful shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Application Availability and events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
