# Application Does Not Exit or Fails to Clean Up Resources After Closing Context

A Spring Boot application may finish its work yet the Java process refuses to terminate. Another case is when the context has closed, yet some threads, sockets, schedulers, or client connections remain active. In other cases, the application receives a stop signal yet fails to finish closing resources before the operating system terminates the process.

To diagnose accurately, separate three questions:

1. **Has the Spring ApplicationContext closed?**
2. **Have the resources managed by the application been released?**
3. **Has the JVM process terminated?**

These three states are related yet not identical. `ApplicationContext.close()` closes the Spring context lifecycle; it does not automatically terminate every thread or resource created outside the container. Conversely, the JVM can exit once no non-daemon threads remain, even if a command-line application never deliberately closed the context as intended.

This lesson explains the shutdown lifecycle, Spring cleanup callbacks, non-daemon threads, executors and background jobs, graceful shutdown, handling signals from containers, reading thread dumps, and design patterns for clean shutdowns.

> **Principle:** every resource must have one clear owner, one start time, and one corresponding closing mechanism. Do not rely on the JVM exiting on its own as a substitute for deliberate cleanup.

## 1. Distinguishing closing context, closing resources, and terminating the JVM

Suppose the application starts:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(OrdersApplication.class, args);
```

Then you call:

```java
context.close();
```

Spring begins closing the ApplicationContext. The container publishes appropriate lifecycle events, stops beans with managed lifecycles, and invokes destroy callbacks on singleton beans.

Yet the process may remain alive:

```text
Spring ApplicationContext
        |
        | close()
        v
Context lifecycle closes
        |
        +--> Spring-managed beans are destroyed
        |
        +--> Some executors are shut down
        |
        +--> Embedded server is stopped
        |
        v
Is the JVM still alive?
        |
        +--> Other non-daemon threads exist -> JVM keeps running
        |
        +--> No non-daemon threads remain -> JVM can exit
```

### 1.1. Three states not to conflate

| State | Meaning | How to observe |
| --- | --- | --- |
| Context active | Spring container is still running | `context.isActive()` |
| Context closed | Container has executed close lifecycle | `context.isActive()` returns `false`, `ContextClosedEvent` |
| Resource closed | Sockets, pools, executors, clients, etc. are closed | API/state specific to each resource |
| JVM terminated | Java process has ended | Process manager, PID, container status |

For example, `context.isActive()` returning `false` does not prove a manually created thread has stopped. Likewise, `executor.isShutdown()` does not prove every task has finished; distinguish `isShutdown()` from `isTerminated()`.

### 1.2. Why does the JVM stay alive after the context closes?

Common causes:

- A thread created with `new Thread(...)` is still running.
- An `ExecutorService` was never shut down.
- A scheduler or timer was never stopped.
- A native library/client spawned its own background threads.
- A listener or consumer is waiting on messages.
- A thread is blocked indefinitely on I/O, a lock, or a queue.
- A non-daemon thread was created inside a static initializer or unmanaged code.

### 1.3. Why does the JVM exit with incomplete cleanup?

Possible causes:

- A manually created resource has no destroy callback.
- A shutdown callback failed or timed out.
- The process received `SIGKILL`, the container runtime forced termination, or the machine powered off abruptly.
- Code called `Runtime.halt(...)`, skipping shutdown hooks.
- A cleanup callback did not wait for asynchronous work to finish.
- The application depends on a resource whose lifecycle was not managed.

Therefore, diagnosis must determine **how far the context closed, which resources remain alive, and which mechanism terminated the process**.

## 2. How can the Spring ApplicationContext be closed?

`ApplicationContext` is an abstraction for reading beans and managing dependencies. To actively close the context, Spring provides `ConfigurableApplicationContext`.

### 2.1. Closing via `close()`

```java
import org.springframework.context.ConfigurableApplicationContext;

ConfigurableApplicationContext context =
        SpringApplication.run(OrdersApplication.class, args);

// Once the application's work is done:
context.close();
```

`close()` instructs Spring to close the context and release container-managed singleton beans according to lifecycle.

This method can be called idempotently on an already-closed context without requiring you to destroy each bean manually.

### 2.2. `ApplicationContext` and `ConfigurableApplicationContext`

If a variable only has type:

```java
ApplicationContext context;
```

that abstraction does not expose `close()`.

When lifecycle control is required, use:

```java
ConfigurableApplicationContext context;
```

Do not arbitrarily cast an unknown context unless you know the implementation supports the corresponding lifecycle interface.

### 2.3. `SpringApplication.run()` returns the context

```java
public static void main(String[] args) {
    ConfigurableApplicationContext context =
            SpringApplication.run(OrdersApplication.class, args);
}
```

In a web application, `main` usually returns after Spring Boot starts, yet the JVM keeps running because of the embedded web server and necessary background threads.

In a non-web application, once `main` returns and no non-daemon threads remain, the JVM can begin shutting down. Spring Boot normally registers a shutdown hook to close the context during JVM shutdown, unless disabled or altered.

### 2.4. `SpringApplication.exit(...)`

For a command-line application that needs to exit after finishing its work:

```java
public static void main(String[] args) {
    ConfigurableApplicationContext context =
            SpringApplication.run(BatchApplication.class, args);

    int exitCode = SpringApplication.exit(context);
    System.exit(exitCode);
}
```

`SpringApplication.exit(context)` collects exit codes from relevant `ExitCodeGenerator` beans and closes the context. `System.exit(exitCode)` requests the JVM to terminate with that exit code after beginning its shutdown sequence.

**Do not call this pattern on a web server meant to keep serving requests.** It is meant for batch/CLI processes that have completed their task.

### 2.5. Do not call `System.exit()` inside a service or controller

Avoid:

```java
@Service
public class OrderService {

    public void submit() {
        // ...
        System.exit(0);
    }
}
```

`System.exit()` terminates the entire JVM, not just the current method or request. A service should not decide to terminate a shared process.

To stop an application intentionally, let the entry-point controller or process supervisor own the lifecycle.

## 3. JVM shutdown hooks and Spring Boot

The JVM supports **shutdown hooks**: threads registered to run when the runtime begins shutting down through normal termination mechanisms.

Spring Boot normally registers a shutdown hook to close the ApplicationContext when the JVM shuts down.

### 3.1. What is a JVM shutdown hook?

Plain Java example:

```java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            System.out.println("JVM is shutting down");
        })
);
```

This hook is invoked when the JVM starts normal shutdown, such as via `System.exit(...)` or termination signals handled as shutdown.

### 3.2. Shutdown hooks do not run on every kind of termination

Do not treat hooks as an absolute cleanup guarantee. Hooks may fail to run when:

- The process is forcefully killed, e.g., `SIGKILL`.
- The machine or container host shuts down abruptly.
- The JVM hits a fatal error preventing normal shutdown.
- Code calls `Runtime.getRuntime().halt(...)`.
- An external mechanism terminates the process without letting the JVM run its shutdown sequence.

In Kubernetes, the container runtime can send `SIGTERM`, wait the grace period, and then send `SIGKILL` if the process has not exited. Cleanup must finish within the allotted window.

### 3.3. Do not create shutdown hooks for every bean

Spring already provides bean lifecycle callbacks. If every bean registers its own JVM shutdown hook, the application ends up with many independent hooks whose ordering and duration are hard to control.

For resources owned by a Spring bean, prefer:

- `@PreDestroy`.
- `DisposableBean`.
- `@Bean(destroyMethod = "...")`.
- `Lifecycle` or `SmartLifecycle`.

Use JVM shutdown hooks for process-level logic only when truly needed; let Spring manage bean lifecycles.

### 3.4. `spring.main.register-shutdown-hook`

Spring Boot provides the property:

```properties
spring.main.register-shutdown-hook=true
```

This setting controls whether SpringApplication registers its shutdown hook. In standard setups, the hook is registered by default.

If set to:

```properties
spring.main.register-shutdown-hook=false
```

the application must have another mechanism actively closing the context during process shutdown. Do not disable the hook merely to dodge an uninvestigated cleanup error.

### 3.5. Hooks are not a place to wait indefinitely

A shutdown hook should:

- Finish within bounded time.
- Never wait indefinitely on an unreachable service.
- Never call `System.exit()` and cause nested shutdown issues.
- Never assume other hooks run in a specific order.
- Include timeouts and appropriate diagnostic logs.

The JVM may run multiple shutdown hooks concurrently; do not rely on hook startup order for dependencies.

## 4. Spring destroy callbacks

Spring supports several ways to specify cleanup when a bean is destroyed.

### 4.1. `@PreDestroy`

This is the common way to mark a cleanup method:

```java
package com.example.orders.worker;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class MessageWorker {

    private static final Logger log =
            LoggerFactory.getLogger(MessageWorker.class);

    @PreDestroy
    public void cleanup() {
        log.info("message.worker.cleanup.started");
        // Release resources owned by this bean
        log.info("message.worker.cleanup.completed");
    }
}
```

With Spring Boot 3, the annotation is usually imported from `jakarta.annotation.PreDestroy`. Older Spring Boot 2 applications may use `javax.annotation.PreDestroy` depending on dependencies/version.

### 4.2. `DisposableBean`

A bean can implement:

```java
import org.springframework.beans.factory.DisposableBean;
import org.springframework.stereotype.Component;

@Component
public class LegacyConnectionManager implements DisposableBean {

    @Override
    public void destroy() {
        // Close connections managed by this bean
    }
}
```

`destroy()` is invoked by Spring during bean destruction.

Its advantage is clarity via interface; its drawback is direct coupling to the Spring API. If you prefer keeping business classes decoupled from framework APIs, `@PreDestroy` or `@Bean` configuration may fit better.

### 4.3. Custom destroy method on `@Bean`

When a bean is created by a `@Bean` method:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

When the context closes, Spring calls the specified `close()` method on the bean.

This is a clean choice when a library class exposes `close()` or `shutdown()` without carrying Spring annotations.

### 4.4. Inferred destroy method

Spring supports inferring certain common destroy methods for beans declared with `@Bean`, such as `close` or `shutdown` in appropriate cases.

Still, for critical resources, declare it explicitly:

```java
@Bean(destroyMethod = "close")
```

so readers clearly see who is responsible for closing it.

### 4.5. Do not invoke cleanup twice haphazardly

Avoid both calling `client.close()` manually in business code and letting Spring call `destroyMethod="close"` on context close without clear ownership design.

A resource should have **one lifecycle owner**. If a method may be called manually before context close, cleanup must be idempotent or track closed state explicitly.

### 4.6. Callback ordering and dependencies

Spring manages dependency relationships between beans when destroying singletons. Beans depending on another bean are typically destroyed before the dependency they require.

Do not assume destruction order between unrelated beans. If order matters, express dependencies and lifecycles explicitly, or use a coordinator managing shutdown.

## 5. `Lifecycle` and `SmartLifecycle`

Some components need **ordered start and stop**, such as message listeners, schedulers, or workers that accept external work.

Spring provides:

```java
org.springframework.context.Lifecycle
org.springframework.context.SmartLifecycle
```

### 5.1. `Lifecycle`

Basic interface:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

A component can implement this so Spring invokes start/stop during the context lifecycle.

### 5.2. `SmartLifecycle`

`SmartLifecycle` adds the ability to:

- Auto-start according to lifecycle.
- Specify `phase`.
- Stop asynchronously via `stop(Runnable callback)`.
- Report running state.

Example:

```java
package com.example.orders.worker;

import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class QueueConsumerLifecycle implements SmartLifecycle {

    private static final Logger log =
            LoggerFactory.getLogger(QueueConsumerLifecycle.class);

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            log.info("queue.consumer.started");
            // Start consumer or begin receiving messages
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            if (running.compareAndSet(true, false)) {
                log.info("queue.consumer.stopping");
                // Stop accepting new messages and close resources properly
            }
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        stop(() -> {
        });
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
```

This is a lifecycle skeleton. In a real consumer, `stop()` must instruct the client to stop receiving messages, wait for in-flight processing with a timeout, commit/ack per policy, and close connections.

### 5.3. The callback is critical

In `SmartLifecycle.stop(Runnable callback)`, Spring expects the callback to be invoked once the component **has finished stopping**.

If the component forgets to call the callback, the lifecycle processor may stall until timeout. If it calls the callback too early while resources are still running, the context may proceed to destroy dependencies the component still uses.

### 5.4. Phase and start/stop ordering

Spring orders lifecycle beans by phase:

- On start, lower phases generally start first.
- On stop, the order reverses; higher phases generally stop first.

Example:

```text
Start:
  Phase 0  -> connection infrastructure
  Phase 10 -> message consumer

Stop:
  Phase 10 -> message consumer stops accepting work
  Phase 0  -> connection infrastructure closes afterward
```

This is one reason `SmartLifecycle` is useful when stop ordering depends on other resources. Assign phases according to real application dependencies, not arbitrary numbers.

### 5.5. Timeout for lifecycle phases

Spring Boot provides the property:

```properties
spring.lifecycle.timeout-per-shutdown-phase=30s
```

This property configures the wait time per shutdown phase in the lifecycle processor according to supported versions.

Setting a timeout too short can cut off resources before they stop; setting it too long can push the process past the container's grace period.

Do not treat timeouts as an automatic fix for a hung component. Components must still stop cleanly and invoke the callback on time.

## 6. Which resources need cleanup?

A Spring Boot application can own many kinds of resources:

| Resource | Action needed on shutdown |
| --- | --- |
| `ExecutorService` | Stop accepting new tasks, await running tasks, close executor |
| `ThreadPoolTaskExecutor` | Stop executor per configured lifecycle |
| `ThreadPoolTaskScheduler` | Stop schedule and running tasks per policy |
| `ScheduledExecutorService` | Cancel schedule and shut down |
| `Timer` | Call `cancel()` |
| HTTP client | Close connection manager/client if API requires |
| JDBC pool | Close application-owned datasource/pool |
| Kafka/Rabbit consumer | Stop accepting messages, process/ack per policy, close client |
| File stream | Close stream; prefer try-with-resources for short scopes |
| Socket/server socket | Stop accepting connections and close socket |
| Database cursor/result set | Close after use |
| Subscription/listener | Unregister |
| Custom thread | Request stop, interrupt when appropriate, and bounded join/wait |
| Native resource | Invoke corresponding release API |
| Temporary files | Delete if lifecycle and policy require |

Not every object needs `@PreDestroy`. A file stream used inside a single method should normally be closed with try-with-resources right where it is opened.

## 7. Unclosed executors: common causes

An `ExecutorService` can create worker threads to execute tasks.

Example:

```java
ExecutorService executor =
        Executors.newFixedThreadPool(4);
```

If worker threads are non-daemon and the executor is never shut down, the JVM can keep running after `main` finishes or the Spring context closes.

### 7.1. Example causing a hung process

```java
public static void main(String[] args) {
    ExecutorService executor =
            Executors.newFixedThreadPool(2);

    executor.submit(() -> {
        while (true) {
            try {
                Thread.sleep(1000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    });

    System.out.println("Main completed");
}
```

After printing `Main completed`, the thread pool still has a running task. Because the executor was not shut down, the JVM can stay alive.

### 7.2. `shutdown()` and `shutdownNow()` differ

```java
executor.shutdown();
```

`shutdown()`:

- Stops accepting new tasks.
- Lets already-submitted tasks continue running.
- Does not wait by default for all tasks to finish.

```java
executor.shutdownNow();
```

`shutdownNow()`:

- Attempts to stop running tasks by interrupting worker threads.
- Returns the list of queued tasks that had not started per implementation.
- Does not guarantee running tasks stop immediately; tasks must cooperate with interruption.

### 7.3. Waiting for an executor to terminate

```java
executor.shutdown();

try {
    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

This example requires importing `java.util.concurrent.TimeUnit`.

Flow:

1. Stop accepting new tasks.
2. Wait for running tasks to finish within a bounded timeout.
3. If time expires, send interrupts.
4. If the cleanup thread itself is interrupted, restore the interrupt status.

### 7.4. Interrupt is not a thread kill command

`Thread.interrupt()` sets the interrupt flag or wakes up certain blocking operations. Task code must cooperate:

```java
while (!Thread.currentThread().isInterrupted()) {
    doOneUnitOfWork();
}
```

If a task swallows `InterruptedException` and keeps looping forever, shutdown will not finish on time.

There is no general safe API to forcefully kill an arbitrary running Java thread. Design tasks with stopping points and timeouts.

## 8. Managing an executor as a Spring bean

If an executor belongs to the application, let Spring manage its lifecycle instead of creating it in a service and forgetting to close it.

### 8.1. Declaring `ExecutorService` with a destroy method

```java
@Configuration(proxyBeanMethods = false)
public class WorkerConfiguration {

    @Bean(destroyMethod = "shutdown")
    public ExecutorService workerExecutor() {
        return Executors.newFixedThreadPool(4);
    }
}
```

When the context closes, Spring calls `shutdown()` on the executor.

However, `shutdown()` does not automatically wait a bounded duration to verify all tasks finished. If waiting and escalation are needed, configure a lifecycle component or use Spring's executor with suitable shutdown properties.

### 8.2. Using `ThreadPoolTaskExecutor`

```java
@Configuration(proxyBeanMethods = false)
public class TaskConfiguration {

    @Bean("applicationTaskExecutor")
    public ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("orders-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);

        return executor;
    }
}
```

`ThreadPoolTaskExecutor` has its lifecycle managed by Spring and exposes shutdown-support properties. The example configures waiting up to 20 seconds for tasks before completing shutdown per executor behavior.

### 8.3. Choosing between waiting for tasks or canceling tasks

`setWaitForTasksToCompleteOnShutdown(true)` instructs the executor to wait for submitted tasks to finish during shutdown per supported mechanics.

If set to `false`, the executor may cancel queued tasks and interrupt running tasks according to its implementation's shutdown behavior.

The choice depends on:

- Is the task idempotent?
- Can it be retried after process restart?
- Is progress recorded durably?
- How long can a task run?
- Can it be interrupted mid-transaction?

Do not wait forever on a task lacking timeouts or recoverability.

### 8.4. Spring Boot auto-configured task executors

Spring Boot offers properties for auto-configured executors/schedulers in supported versions, for example:

```properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=20s

spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=20s
```

Property names and applicability depend on the Spring Boot version and auto-configured executor type. They do not automatically configure custom executors you instantiate yourself.

When declaring a custom `@Bean`, read that bean's lifecycle API and configure shutdown explicitly. Do not assume auto-configuration properties govern arbitrary manually constructed objects.

## 9. Manually created threads sit outside Spring's lifecycle

Example:

```java
@Component
public class PollingWorker {

    public PollingWorker() {
        Thread thread = new Thread(() -> {
            while (true) {
                poll();
            }
        });

        thread.start();
    }

    private void poll() {
        // ...
    }
}
```

A thread spawned in a constructor does not automatically become a Spring bean. Spring does not know how to stop it unless the class provides a lifecycle callback.

### 9.1. Managing a thread with a stop flag

```java
@Component
public class PollingWorker {

    private final AtomicBoolean running =
            new AtomicBoolean(false);

    private Thread workerThread;

    @PostConstruct
    public void start() {
        if (!running.compareAndSet(false, true)) {
            return;
        }

        workerThread = new Thread(this::runLoop, "orders-poller");
        workerThread.start();
    }

    private void runLoop() {
        while (running.get() &&
                !Thread.currentThread().isInterrupted()) {
            try {
                pollOnce();
                Thread.sleep(1000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }

    private void pollOnce() {
        // Process a time-bounded unit of work
    }

    @PreDestroy
    public void stop() {
        running.set(false);

        if (workerThread != null) {
            workerThread.interrupt();
            try {
                workerThread.join(5000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

The example requires importing `AtomicBoolean`, `PostConstruct`, `PreDestroy`, and corresponding annotations. In Spring Boot 3, `PostConstruct` and `PreDestroy` normally live in `jakarta.annotation`.

### 9.2. Why require both a stop flag and interrupt?

- The stop flag signals stop intent at the application level.
- Interrupt wakes threads sleeping or waiting in certain blocking operations.
- `join(timeout)` waits for the thread to finish within a bounded time.

If `pollOnce()` blocks inside a library that ignores interrupts or timeouts, `join(5000)` may return while the thread stays alive. In that case, configure timeouts/close on the underlying resource used by `pollOnce()`.

### 9.3. Do not use daemon threads to hide leaks

You could call:

```java
workerThread.setDaemon(true);
```

Daemon threads do not keep the JVM alive once all non-daemon threads exit. However, when the JVM exits, daemon threads can be abruptly halted without finishing work or cleanup.

Turning a thread into a daemon **is no substitute** for stopping, committing, flushing, or releasing resources.

## 10. Using `@Scheduled` and lifecycle-managed schedulers

Spring Scheduling is typically managed by a scheduler bean.

```java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
```

```java
@Component
public class CleanupJob {

    @Scheduled(fixedDelay = 60_000)
    public void run() {
        // Clean up expired data in a bounded batch
    }
}
```

Spring Boot/Spring Framework can use a task scheduler configured in the context. When the context closes, the Spring-managed scheduler has an appropriate shutdown lifecycle.

### 10.1. Tasks running when shutdown starts

If a scheduled method is mid-execution, decide:

- Should it be allowed to finish?
- Can it be interrupted?
- Can it re-run after restart?
- Does it write checkpoints?
- Could it hold transactions or locks too long?

Just because the scheduler bean shuts down does not guarantee every running business task finished safely.

### 10.2. Manually created `Timer` instances are easy to forget

```java
Timer timer = new Timer();
timer.scheduleAtFixedRate(task, 0, 1000);
```

`Timer` spawns its own thread. Without calling:

```java
timer.cancel();
```

the thread can keep the JVM alive.

When using Spring scheduling, let the container manage the lifecycle instead of creating manual timers inside services.

## 11. Closing HTTP clients, connection pools, and database resources

Threads are not the only source of trouble. Clients can hold sockets, connection pools, selector threads, or native resources.

### 11.1. Closing clients with `@Bean(destroyMethod=...)`

Conceptual example:

```java
@Configuration(proxyBeanMethods = false)
public class PartnerClientConfiguration {

    @Bean(destroyMethod = "close")
    public PartnerClient partnerClient() {
        return PartnerClient.create();
    }
}
```

Here `PartnerClient` is a hypothetical class with a `close()` method. When the context closes, Spring calls this method.

### 11.2. HTTP clients may manage their own connection pools

Some HTTP clients maintain:

- Connection managers.
- Event loops.
- Selector threads.
- Background eviction schedulers.
- Connection pools.

Closing a wrapper without closing the underlying resource owner can leave threads or sockets alive. Read the specific client's API to know which method truly shuts down the connection manager.

### 11.3. DataSource and connection pools

A `DataSource` auto-configured by Spring Boot is normally managed in the context. If you build a pool outside Spring, you must close the pool yourself.

Do not hold a borrowed connection forever in a singleton field. Borrowed connections must be returned:

```java
try (Connection connection = dataSource.getConnection()) {
    // Use connection
}
```

With a pooled datasource, `close()` on a connection usually returns it to the pool, while the datasource/pool itself is closed by the datasource's lifecycle.

### 11.4. Do not close a datasource still used by other beans

If a service calls `dataSource.close()` directly while the context is still active, other beans can encounter connection failures.

The lifecycle owner of a datasource should be the container or pool-managing component, not an arbitrary business service.

## 12. Kafka, RabbitMQ, and message consumers

A consumer typically owns polling threads, network connections, and ack/offset state. Closing a consumer is more than stopping one thread.

### 12.1. Required shutdown steps

1. Stop accepting new messages.
2. Wait for in-flight messages to finish within the allowed time.
3. Commit offsets or ack according to broker semantics.
4. Handle pending tasks per retry/dead-letter policy.
5. Close the consumer/client and connection.

### 12.2. Avoiding lost messages or duplicate processing

If the process stops mid-processing:

```text
Receive message
      |
      v
Update database
      |
      X process stops
      |
      v
Offset/ack uncommitted?
```

The message may be redelivered. The system needs idempotency or a matching transaction/ack strategy; shutdown cleanup alone does not guarantee exactly-once business effects.

### 12.3. Spring-managed listener containers

When using Spring Kafka or Spring AMQP listener containers, let the framework manage container lifecycles. Configure shutdown timeouts, acknowledgements, and listener concurrency per version and actual requirements.

Do not spawn manual broker-polling threads inside constructors without a clear lifecycle owner.

## 13. Graceful shutdown of the web server

A web server should not immediately sever every in-flight request when the process receives a normal stop signal if ongoing requests can be given time to finish.

**Graceful shutdown** is the process of:

1. Stopping acceptance of new requests.
2. Letting in-flight requests continue within a bounded window.
3. Closing remaining components and resources.
4. Exiting the process before the deployment environment's deadline.

### 13.1. Enabling graceful shutdown in Spring Boot

In supported Spring Boot versions:

```properties
server.shutdown=graceful
```

Spring Boot integrates graceful shutdown with supported embedded web servers. Exact behavior and server support depend on version and web server implementation.

Without configuring graceful mode, the server may fall back to its version's default shutdown behavior, often stopping immediately or waiting minimally for active requests.

### 13.2. Timeout for shutdown phases

Example:

```properties
spring.lifecycle.timeout-per-shutdown-phase=30s
```

This property gives the lifecycle processor a window to wait per phase. It should not be set arbitrarily larger than the time the orchestrator grants the process to exit.

### 13.3. Readiness during shutdown

When the application begins graceful shutdown, Spring Boot can transition readiness to refuse new traffic under the corresponding lifecycle.

This helps orchestrators/load balancers stop routing new requests while the server finishes active ones via graceful shutdown.

However, routing changes take time to propagate. If traffic goes directly to the process, readiness state alone does not block every client.

### 13.4. Graceful does not mean waiting forever

A hung request or unresponsive client can stall shutdown. Timeouts are needed on:

- HTTP requests.
- Database queries/transactions.
- Outbound HTTP calls.
- Message processing.
- Executor tasks.

Shutdown can finish on schedule only when active work is time-bounded or properly cancelable.

## 14. SIGTERM, SIGINT, and container lifecycle

On Unix-like systems, processes typically receive:

- `SIGTERM`: polite request to terminate cleanly.
- `SIGINT`: interrupt signal, typically from a terminal.
- `SIGKILL`: forced termination that cannot be handled by application shutdown hooks.

### 14.1. Docker

When stopping a container, Docker normally sends a stop signal to the main process (PID 1), waits a grace period, and only then forcefully kills it if it has not exited.

Example:

```bash
docker stop --time 40 order-service
```

The container is granted maximum stop time per this flag before Docker resorts to forceful termination.

### 14.2. Using exec-form ENTRYPOINT

Prefer:

```dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Exec form ensures the Java process is executed directly in the container in a clear manner.

If you use shell form:

```dockerfile
ENTRYPOINT java -jar /app/app.jar
```

the shell may occupy PID 1 and must forward signals properly. A shell wrapper without `exec` can prevent the Java process from receiving signals as expected.

If a wrapper is needed:

```sh
#!/bin/sh
exec java -jar /app/app.jar "$@"
```

The `exec` command replaces the shell process with the Java process.

### 14.3. Kubernetes termination grace period

In Kubernetes, Pod termination typically follows:

1. The Pod is marked terminating and removed from new traffic selection per endpoint/routing propagation.
2. `preStop` hook may run if declared.
3. Container runtime sends `SIGTERM` to the process.
4. Kubernetes waits up to `terminationGracePeriodSeconds`.
5. If the process is still running when time expires, the container may receive `SIGKILL`.

Exact ordering and timing must consider kubelet, endpoint propagation, and `preStop` hooks together. `preStop` consumes time out of the termination grace period; it does not automatically add extra grace time on top.

### 14.4. Choosing a grace period sufficient for shutdown

Example:

```yaml
spec:
  terminationGracePeriodSeconds: 60
```

This value is only illustrative. Actual time must cover:

- Time to stop receiving new traffic.
- Time for in-flight requests and messages to complete.
- Time to stop consumers/executors.
- Time to flush/close resources.
- A system safety margin.

Do not configure a 90-second Spring shutdown timeout if the container only allows 30 seconds. Kubernetes can kill the process before Spring finishes.

## 15. Using `ContextClosedEvent` to observe closing

Spring publishes `ContextClosedEvent` when the context begins closing.

Example:

```java
package com.example.orders.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownEventsLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ShutdownEventsLogger.class);

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        log.info("event=application.context.closed");
    }
}
```

This listener is useful for recording the lifecycle milestone. However, the event fires during context closing; **it is not the best callback for manually closing every dependency**.

### 15.1. Do not assume all beans are destroyed when the event fires

The context close lifecycle still has to stop lifecycle beans and destroy singleton beans. An event listener can run before all resources have been released.

If a bean owns an executor, use `@PreDestroy`, `DisposableBean`, or that bean's lifecycle interface.

### 15.2. Distinguishing the event from proof of completion

The log:

```text
event=application.context.closed
```

shows the event was published. To verify an executor terminated, check the executor's state or specific logs/metrics after awaiting completion.

Do not use a single "context closed" log line to conclude all background threads stopped.

## 16. Bean scopes and resource ownership

Destroy callbacks depend on the bean's lifecycle and scope.

### 16.1. Singleton

Singleton beans are container-managed and typically run destroy callbacks when the context closes.

```java
@Component
public class SingletonClientManager {

    @PreDestroy
    public void close() {
        // Close resource
    }
}
```

### 16.2. Prototype

Prototype beans are created upon request, yet Spring **does not manage the full destruction lifecycle of prototype instances** once handed to the client.

If a prototype owns a resource:

- The client is responsible for closing the instance after use.
- Or design a factory with an explicit acquire/release API.
- Avoid creating prototypes holding threads or sockets without an owner.

### 16.3. Request/session scope

Scoped beans follow their respective scope lifecycles. For request-scoped beans, resources should be closed when the request scope ends via the appropriate mechanism.

If a resource must outlive the request, do not hold it in a request-scoped bean expecting it to survive after the request ends.

### 16.4. Resources created outside the container

Example:

```java
public class ReportService {

    public void generate() {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        // ...
    }
}
```

If the executor is never shut down, Spring has no bean lifecycle callback to invoke.

Better:

- Inject a Spring-managed executor.
- Use try-with-resources for short-lived resources.
- If creating dynamic resources, close them in `finally` or a well-defined scope.

## 17. Using try-with-resources for short-lived resources

Not every resource should stay open until the context closes. For streams, files, connections, or handles used within one method, close them right after finishing.

Example:

```java
public String readConfig(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Try-with-resources guarantees `close()` is called upon exiting the block, even if an exception occurs.

### 17.1. JDBC connections

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "select current_timestamp"
             );
     ResultSet resultSet = statement.executeQuery()) {

    if (resultSet.next()) {
        return resultSet.getTimestamp(1).toInstant();
    }
}
```

With a pooled datasource, closing the connection returns it to the pool per the datasource contract. Never hold a connection in a singleton field waiting for context destruction.

### 17.2. Long-lived shared resources

An HTTP client or connection pool shared across multiple requests can live for the duration of the application context. In that case, `@Bean(destroyMethod=...)` or bean lifecycle fits well.

Distinguish:

```text
Short-lived resource -> try-with-resources
Shared resource      -> Spring bean + destroy lifecycle
Background task      -> executor/worker lifecycle
```

## 18. Shutdown in command-line and batch applications

A Spring Boot application does not need to include a web server. In a batch application, the process may finish its work and then exit.

### 18.1. Running a non-web application

```java
@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context =
                application.run(args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
```

This is a straightforward pattern for synchronous batch apps once runners finish and the process no longer needs to stay alive.

### 18.2. Do not call exit right after submitting async work

Wrong example:

```java
@Component
public class BatchRunner implements ApplicationRunner {

    private final Executor executor;

    public BatchRunner(Executor executor) {
        this.executor = executor;
    }

    @Override
    public void run(ApplicationArguments args) {
        executor.execute(this::processLargeFile);
        // Runner returns immediately
    }
}
```

If `main` calls `SpringApplication.exit(context)` right after `run()`, the context may start shutting down while the task is still processing.

Better designs:

- Wait for `Future`/`CompletableFuture` completion within a time limit.
- Use a batch framework with lifecycle and job status tracking.
- Ensure the executor is managed with a clear shutdown policy.

### 18.3. Returning a meaningful exit code

Spring Boot supports `ExitCodeGenerator`:

```java
@Component
public class BatchExitCode implements ExitCodeGenerator {

    @Override
    public int getExitCode() {
        return 0;
    }
}
```

In real applications, the exit code should reflect batch outcomes per operational contract. Never return 0 merely because the context closed if the job failed.

## 19. Why does `@PreDestroy` not run as expected?

Common causes:

### 19.1. Bean not managed by Spring

```java
MyClient client = new MyClient();
```

If an object is instantiated via `new` outside the container, Spring does not automatically invoke `@PreDestroy` on it.

**How to fix:** register the bean with `@Component` or `@Bean`, or manage the resource where it is created.

### 19.2. Prototype bean

Prototype instances do not have their full destruction lifecycle managed automatically by Spring once handed to the client.

**How to fix:** the client must close the resource, or use an appropriate factory/lifecycle abstraction.

### 19.3. Context never closed

If a context is created manually without a shutdown hook or explicit close call, destroy callbacks may fail to run after `main` ends when remaining threads keep the JVM alive.

**How to fix:** use `ConfigurableApplicationContext.close()` or ensure the process shutdown hook is registered.

### 19.4. JVM forcefully killed

`SIGKILL` gives the JVM no chance to run shutdown hooks. `@PreDestroy` is not a guarantee against a forced kill.

**How to fix:** design recoverable operations, consistent transactions, and message handling with retries/idempotency.

### 19.5. Cleanup method is blocked

Example:

```java
@PreDestroy
public void cleanup() {
    while (!remoteServiceAvailable()) {
        // Wait forever
    }
}
```

The context may never finish shutting down on time.

**How to fix:** set timeouts, avoid infinite retries, and provide an escape hatch when dependencies are unavailable.

### 19.6. Cleanup callback throws an exception

If a callback fails, Spring typically logs the error and proceeds to destroy other beans per container mechanics. However, the resource that callback meant to close may remain alive.

**How to fix:** log an appropriate failure code, preserve essential error details, and ensure cleanup callbacks handle exceptions per resource.

### 19.7. Annotation import mismatches version

Spring Boot 3 uses the Jakarta namespace for `@PreDestroy`; older code using `javax.annotation` may require migration or matching dependencies.

**How to fix:** use the annotation namespace matching your stack version.

## 20. Diagnosing a non-exiting process with thread dumps

When the context has closed yet the process stays alive, inspect **which threads remain alive**.

### 20.1. Capturing a thread dump with `jcmd`

On a machine with JDK installed and attach permissions:

```bash
jcmd <pid> Thread.print
```

Example:

```bash
jcmd 12345 Thread.print
```

This command instructs the JVM process with that PID to print its thread dump.

### 20.2. Using `jstack`

```bash
jstack 12345
```

A thread dump can show:

- Thread name.
- State (`RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED`, etc.).
- Stack trace.
- Related locks/monitors.

Do not conclude every `WAITING` thread is leaked. A thread pool may keep idle worker threads waiting for new tasks; what matters is **which resource owns the thread and whether that owner's lifecycle has closed**.

### 20.3. Thread names help locate the owner

Examples:

```text
pool-3-thread-1
orders-worker-2
scheduling-1
http-client-selector
kafka-consumer-0
```

Default names like `pool-3-thread-1` are harder to trace than meaningful custom names. When creating an executor:

```java
executor.setThreadNamePrefix("orders-worker-");
```

Clear thread prefixes let you filter thread dumps and locate the owning bean much faster.

### 20.4. Thread dumps on Linux

You can send `SIGQUIT` (`kill -3`) to the JVM to request a thread dump in supported environments; output typically goes to the process stdout/stderr per runtime config.

Never use `kill -9` to request a thread dump. `SIGKILL` terminates the process forcefully without letting the JVM handle the signal.

### 20.5. Windows

On Windows, you can use `jcmd` or `jstack` from the corresponding JDK:

```powershell
jcmd 12345 Thread.print
```

Use the PID of the right Java process and an account with attach permissions.

## 21. Reading thread dumps: signs to watch for

### 21.1. Worker thread running an infinite loop

Sample stack:

```text
"orders-worker-1" #42 prio=5 os_prio=0
   java.lang.Thread.State: RUNNABLE
   at com.example.orders.Poller.pollForever(Poller.java:42)
   at com.example.orders.Poller.run(Poller.java:25)
```

This signals a loop to inspect for a stop condition. `RUNNABLE` does not necessarily mean high CPU; it describes thread state from the JVM's perspective.

### 21.2. Thread pool waiting for tasks

```text
"pool-3-thread-1"
   java.lang.Thread.State: WAITING
   at java.util.concurrent.LinkedBlockingQueue.take(...)
   at java.util.concurrent.ThreadPoolExecutor.getTask(...)
```

The worker is waiting for new tasks. If the executor remains alive after context close, check whether the executor was ever shut down.

### 21.3. Scheduler thread

```text
"scheduling-1"
   java.lang.Thread.State: TIMED_WAITING
```

This may be a scheduler waiting for its next run time. Check whether the scheduler bean belongs to the closing context and whether its lifecycle callback ran.

### 21.4. Blocked thread

```text
"orders-worker-2"
   java.lang.Thread.State: BLOCKED
   - waiting to lock <...>
```

Inspect the lock owner and deadlock potential. Cleanup may be waiting for a lock that a task never releases.

### 21.5. Non-daemon or daemon?

Thread dumps may show daemon status depending on the tool/format. Live non-daemon threads can keep the JVM running.

Yet live daemon threads can also indicate uncleaned resources; they simply do not keep the JVM alive under daemon rules.

## 22. Writing shutdown callbacks with timeouts and resilience

A good cleanup method must:

- Stop accepting new work.
- Let active work finish within limits.
- Close resources in dependency order.
- Restore interrupt status when interrupted.
- Record errors without hiding root causes.
- Never wait indefinitely.

Example for a worker:

```java
package com.example.orders.worker;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import jakarta.annotation.PreDestroy;

@Component
public class ExportWorker {

    private static final Logger log =
            LoggerFactory.getLogger(ExportWorker.class);

    private final ExecutorService executor;

    public ExportWorker(ExecutorService exportExecutor) {
        this.executor = exportExecutor;
    }

    @PreDestroy
    public void shutdown() {
        log.info("export.worker.shutdown.started");
        executor.shutdown();

        try {
            if (!executor.awaitTermination(15, TimeUnit.SECONDS)) {
                log.warn("export.worker.shutdown.timeout");
                executor.shutdownNow();

                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    log.error("export.worker.did_not_terminate");
                }
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }

        log.info("export.worker.shutdown.finished");
    }
}
```

This example assumes `exportExecutor` is an injected bean and **ExportWorker is the sole owner** responsible for shutting it down. If the executor also has its own destroy callback, avoid shutting it down in two places or adjust ownership.

### 22.1. Do not let two beans own the same executor

A common design mistake:

```text
ExportWorker @PreDestroy -> executor.shutdown()
Executor bean destroy    -> executor.shutdown()
```

Double shutdown may be idempotent on `ExecutorService`, yet two places awaiting or interrupting concurrently can cause unpredictable behavior.

Prefer having one configuration bean own the executor lifecycle; the worker only submits tasks and stops accepting new work under its own lifecycle.

### 22.2. Closing in dependency order

If a consumer uses an executor to finish final callbacks, do not shut down the executor before the consumer stops.

A sensible order can be:

```text
Stop accepting new messages
          |
          v
Wait for in-flight message handling
          |
          v
Shutdown task executor
          |
          v
Close database / HTTP clients
```

Exact ordering depends on resources and transaction semantics. `SmartLifecycle` phases or a shutdown coordinator can express the sequence clearly.

## 23. Avoiding deadlocks during shutdown

Some cleanup callbacks can wait on each other:

```text
Bean A @PreDestroy
   waits for task in Executor
             |
             v
        Task needs Bean B
             |
             v
        Bean B already closing
```

If Bean B already closed the connection/client the task still needs, the task cannot finish. Bean A waits on the task, the context waits on A, and shutdown stalls.

### 23.1. Stop producing work before closing dependencies

A solid sequence is typically:

1. Stop accepting new traffic/messages.
2. Stop scheduling new tasks.
3. Wait for in-flight operations.
4. Stop workers/executors.
5. Close clients/connection pools.
6. Complete context close.

### 23.2. Do not hold locks while waiting for another thread

Avoid:

```java
synchronized void shutdown() {
    worker.interrupt();
    worker.join();
}
```

if the worker needs that exact monitor to finish. That can deadlock.

Separate updating state under the lock from waiting for the thread:

```java
public void shutdown() {
    synchronized (this) {
        running = false;
    }

    worker.interrupt();
    // Wait after releasing the monitor
}
```

## 24. Logging during shutdown

Logs reveal how far the lifecycle progressed:

```text
event=shutdown.started
event=consumer.stop.started
event=consumer.stop.completed
event=executor.shutdown.started
event=executor.shutdown.completed
event=application.context.closed
```

### 24.1. Logging meaningful details

Log:

- Component name.
- Shutdown action.
- Wait duration.
- Active/queued task counts if safely accessible.
- Failure codes when closing fails.

Do not log:

- Passwords/secrets.
- Entire configuration dumps.
- Sensitive message payloads.
- Request/response bodies.

### 24.2. Do not log only "shutdown complete" from one callback

One component may finish closing while other resources stay alive. Each owner should log cleanup outcomes for the resources it owns.

An `application.shutdown.completed` line should only be emitted where enough information exists to confirm critical steps finished, not merely because a listener received `ContextClosedEvent`.

### 24.3. The logging system also has a lifecycle

Spring Boot manages the logging system. Avoid shutting down the logging backend too early and still expecting subsequent bean destroy callbacks to log normally.

Let the framework manage logging shutdown and keep cleanup callbacks concise.

## 25. Testing context close lifecycle

You do not have to wait for a real JVM to exit to test a basic destroy callback. You can use a Spring test context and observe side effects.

### 25.1. Bean recording destruction

```java
public class CleanupProbe {

    private final AtomicBoolean destroyed =
            new AtomicBoolean(false);

    public boolean isDestroyed() {
        return destroyed.get();
    }

    @PreDestroy
    public void destroy() {
        destroyed.set(true);
    }
}
```

### 25.2. Testing with `AnnotationConfigApplicationContext`

```java
class ContextCloseTest {

    @Test
    void invokesPreDestroyWhenContextCloses() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        context.registerBean(CleanupProbe.class);
        context.refresh();

        CleanupProbe probe =
                context.getBean(CleanupProbe.class);

        assertThat(probe.isDestroyed()).isFalse();

        context.close();

        assertThat(probe.isDestroyed()).isTrue();
    }
}
```

This example assumes JUnit 5 and AssertJ, plus imports for `AtomicBoolean` and Spring context classes.

### 25.3. Checking that the executor terminated

```java
context.close();

assertThat(executor.isShutdown()).isTrue();
assertThat(executor.isTerminated()).isTrue();
```

Do not assert only `isShutdown()`. An executor may have stopped accepting tasks while running tasks have not yet finished.

### 25.4. Testing with `@SpringBootTest`

Spring Test usually caches the ApplicationContext across tests for speed. The context does not necessarily close immediately after every test method.

When testing context closing and recreation, you can use:

```java
@DirtiesContext
```

at an appropriate scope so Spring Test evicts the context from the cache and closes it under test framework lifecycle.

Avoid adding `@DirtiesContext` to every test unnecessarily; it slows down the test suite and alters shared state.

### 25.5. `ApplicationContextRunner`

For testing auto-configurations or small bean lifecycles, `ApplicationContextRunner` provides a callback running within a runner-managed context:

```java
new ApplicationContextRunner()
        .withBean(CleanupProbe.class)
        .run(context -> {
            CleanupProbe probe =
                    context.getBean(CleanupProbe.class);
            assertThat(probe.isDestroyed()).isFalse();
        });
```

The runner closes the context after the callback. If you need to assert post-close state, hold a reference to the probe and inspect it after `run(...)` finishes.

## 26. Testing shutdown in an integration test with a separate process

Sometimes you need to verify that the process actually exits upon receiving a signal. This is a process-level check, distinct from testing a Spring bean callback.

A test can:

1. Launch the executable JAR via `ProcessBuilder`.
2. Wait with a timeout for a startup/ready signal line.
3. Send an OS-appropriate stop signal.
4. Wait for the process to exit within a timeout.
5. Check the exit code and shutdown logs.

Conceptual Java example:

```java
Process process = new ProcessBuilder(
        "java",
        "-jar",
        "build/libs/demo.jar"
).start();

boolean exited = process.waitFor(
        30,
        TimeUnit.SECONDS
);
```

This snippet illustrates only waiting for the process; a complete integration test must also send the shutdown signal and drain stdout/stderr to avoid full pipes. Signal delivery differs between Windows and Unix.

### 26.1. Do not use `destroyForcibly()` as a graceful check

```java
process.destroyForcibly();
```

terminates the process forcefully. It does not verify Spring shutdown hooks or `@PreDestroy`.

Use normal shutdown signals supported by the environment, wait within a timeout, and use forceful termination only for test cleanup if the process hangs.

### 26.2. Tests must have timeouts

A hung shutdown test can stall a CI job indefinitely. Set timeouts on:

- Startup.
- Sending test requests.
- Shutdown signaling.
- Process exit.
- Output collection.

## 27. Common reasons a process fails to exit

| Cause | Symptom | Investigation direction |
| --- | --- | --- |
| Unclosed `ExecutorService` | `pool-N-thread-M` remains alive | Find where the executor was created and its lifecycle owner |
| Custom thread looping endlessly | Custom thread remains RUNNABLE | Inspect stop flag, interrupt handling, and timeouts |
| Scheduled executor still running | Scheduler thread stays alive | Check scheduler bean or `Timer.cancel()` |
| HTTP client keeping event loop | Selector/connection threads stay alive | Check client/manager close API |
| Message consumer not stopped | Consumer thread remains active | Check listener container and in-flight work |
| Cleanup waiting forever | Context close drags on | Add timeouts, inspect waiting thread stack |
| Async task ignores interrupt | `shutdownNow()` called yet task lives | Update task to check interrupt/cancel |
| Thread blocked on I/O | Stack sits in socket read/connect | Configure network timeouts and close socket/client |
| Non-daemon thread from library | Thread named after library | Identify owning bean and shutdown API |
| Context never closed | Destroy callbacks never run | Check `close()` and shutdown hook |
| Process held alive by multiple contexts | One context closes yet another remains active | Locate all `SpringApplication`/contexts created |
| Shell fails to forward signal | Java does not receive SIGTERM as expected | Check PID 1 and exec-form ENTRYPOINT |

## 28. Common mistakes in cleanup callbacks

### 28.1. Using `Thread.sleep()` to wait for shutdown

Avoid:

```java
@PreDestroy
public void cleanup() throws InterruptedException {
    Thread.sleep(30_000);
}
```

Sleeping does not prove resources closed or tasks finished.

Await specific state instead:

```java
executor.awaitTermination(10, TimeUnit.SECONDS);
```

### 28.2. Swallowing `InterruptedException`

Avoid:

```java
try {
    executor.awaitTermination(10, TimeUnit.SECONDS);
} catch (InterruptedException ex) {
    // Ignore
}
```

Normally, if you cannot propagate the exception, restore the interrupt:

```java
catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

### 28.3. Waiting on a remote dependency without a timeout

If cleanup calls a remote API with no timeout, the context can hang during network failures.

Configure appropriate connect/read/request timeouts. Shutdown must never depend indefinitely on an unresponsive external system.

### 28.4. Submitting cleanup tasks to a closing executor

Avoid:

```java
@PreDestroy
public void cleanup() {
    executor.submit(this::closeRemoteSession);
}
```

without waiting for the task afterward. The executor may shut down immediately after the callback, leaving the task unexecuted or unfinished.

If cleanup must be async, include an explicit mechanism to await completion within a timeout.

### 28.5. Closing dependencies before consumers

If a consumer still uses a database client, closing the database client before stopping the consumer can make consumer cleanup fail.

Express lifecycle ordering according to usage relationships.

### 28.6. Calling an `@Async` method from `@PreDestroy`

Do not assume:

```java
@PreDestroy
public void cleanup() {
    asyncService.flush();
}
```

will finish before the context moves on to destroy beans. If `flush()` is async, the callback may only submit the task.

Inside cleanup, prefer synchronous operations with timeouts or awaiting an explicit `Future`.

## 29. Comprehensive example: application with web server and worker

Suppose Orders API has:

- Embedded Tomcat.
- A message-receiving worker.
- An executor processing exports.
- An HTTP client calling pricing service.

Desired shutdown lifecycle:

```text
SIGTERM
   |
   v
Readiness -> REFUSING_TRAFFIC
   |
   v
Web server stops accepting new requests
   |
   v
Message consumer stops accepting new messages
   |
   v
Wait for in-flight requests/messages
   |
   v
Executor stops accepting tasks and awaits completion
   |
   v
Close HTTP client / connection pool
   |
   v
Destroy singleton beans
   |
   v
JVM exits
```

Actual ordering must be configured via the application's lifecycle mechanisms and dependencies; the diagram shows the design target.

### 29.1. Web graceful shutdown

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
```

### 29.2. Consumer lifecycle

The consumer needs `SmartLifecycle` or a framework-managed listener container to:

- Stop receiving new messages.
- Wait for in-flight messages.
- Commit/ack per policy.
- Close connections.

### 29.3. Executor lifecycle

Declare the executor bean with a thread prefix and shutdown wait:

```java
@Bean
public ThreadPoolTaskExecutor exportExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("export-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(15);

    return executor;
}
```

### 29.4. HTTP client ownership

Register the client as a bean and declare its destroy method:

```java
@Bean(destroyMethod = "close")
public PricingClient pricingClient() {
    return PricingClient.create();
}
```

`PricingClient` is an illustrative class with a `close()` method. In real projects, replace it with the proper resource-closing API of your chosen HTTP client.

### 29.5. Total time budget

Suppose:

| Phase | Illustrative budget |
| --- | ---: |
| Stop receiving new traffic/messages | 5 seconds |
| Wait for in-flight requests and messages | 15 seconds |
| Wait for export executor | 15 seconds |
| Close clients and pools | 5 seconds |
| Buffer | 10 seconds |
| Total | 50 seconds |

If Kubernetes `terminationGracePeriodSeconds` is only 40 seconds, the design above does not fit. Shorten/adjust phases or change the grace period within deployment limits.

Do not add timeouts mechanically: lifecycle phases may run sequentially or use other coordination mechanics. Measure actual shutdown duration and verify with integration tests.

## 30. Observing shutdown via metrics and events

Beyond logs, you can monitor:

- Active task count when shutdown starts.
- Queued task count.
- Time from signal to process exit.
- Number of still-active consumers.
- In-flight request count.
- Successful/failed resource closes.
- Container termination reasons and restart counts.

Sample events:

```text
event=shutdown.started
activeRequests=4
activeMessages=2
queuedExports=3
```

```text
event=shutdown.component.completed
component=message-consumer
durationMs=1200
```

```text
event=shutdown.completed
durationMs=18300
```

These are illustrative logs. Avoid putting payloads, tokens, or user information in shutdown events.

### 30.1. Shutdown metrics do not replace thread dumps

A metric `activeTasks=0` is useful, yet can miss threads spawned by libraries outside executors. When a process refuses to exit, thread dumps remain essential evidence.

### 30.2. Correlate by instance and deployment

When multiple replicas shut down simultaneously, logs should include instance/pod identity and version. This helps separate normal rollout shutdowns from abnormal crash shutdowns.

## 31. Investigation checklist when context closed yet process stays alive

Proceed in order:

1. Verify `ConfigurableApplicationContext.isActive()` and whether `ContextClosedEvent` fired.
2. Confirm critical Spring destroy callbacks were called.
3. Capture a thread dump using `jcmd <pid> Thread.print` or `jstack`.
4. Find surviving non-daemon threads and record thread names.
5. Trace threads back to their owning executor, scheduler, client, or library.
6. Check whether the resource owner has a destroy callback/lifecycle.
7. Check whether tasks are blocked on I/O, locks, or queues.
8. Check shutdown timeouts and container grace periods.
9. Verify whether the process actually received a normal stop signal.
10. Re-run a context-close or separate-process test to reproduce.

Do not simply add `System.exit(0)` to force the process to quit before understanding which threads remain alive; doing so can mask leaks and cut off work that needed to finish.

## 32. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "`context.close()` always terminates the JVM." | It closes the Spring context; other non-daemon threads can keep the process alive |
| "Once main returns, the JVM exits." | The JVM continues while non-daemon threads remain |
| "`@PreDestroy` runs on every object." | Applies only to appropriately Spring-managed beans/lifecycles |
| "Prototype beans are destroyed automatically by Spring." | Prototype instances do not have container-managed full destruction lifecycles |
| "`shutdown()` waits for all tasks to finish." | It stops new tasks; call `awaitTermination()` if waiting is required |
| "`shutdownNow()` kills threads immediately." | It requests interruption; tasks must cooperate |
| "Daemon threads fix resource leaks." | Daemon merely stops keeping the JVM alive; cleanup can still be skipped |
| "`ContextClosedEvent` means all resources are closed." | The event is a milestone during the close process |
| "Shutdown hook and `@PreDestroy` are the same thing." | JVM hooks start the shutdown process; Spring callbacks handle bean lifecycles |
| "Shutdown hooks even run on `kill -9`." | SIGKILL cannot be caught or handled by shutdown hooks |
| "Graceful shutdown waits indefinitely for requests." | It has timeouts and is bounded by the orchestrator |
| "Readiness DOWN automatically blocks every client." | Effective only with routing/orchestrators that honor readiness |
| "`@Async` inside `@PreDestroy` definitely completes." | Async calls may only submit a task before the callback returns |
| "A single shutdown-complete log line proves process exit." | Must observe the actual process and threads |
| "Executors created with `new` are closed automatically by Spring." | External resources need explicit owners and cleanup |
| "Database connections only need closing at context shutdown." | Per-request borrowed connections must be returned right after use |

## 33. Practice exercises

### Exercise 1 — Closing context and observing the JVM

Create a non-web application:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(BatchApplication.class, args);

context.close();
```

Observe destroy callback logs and process exit. Explain the difference between context state and JVM process state.

### Exercise 2 — Creating a thread that keeps the JVM alive

Create a non-daemon thread loop with a stop condition. Let `main` return without stopping the thread.

Observe the process remaining alive, capture a thread dump, and identify the thread name.

Then add `@PreDestroy` to stop, interrupt, and join within a timeout.

### Exercise 3 — Comparing `shutdown()` and `shutdownNow()`

Create an executor with one sleeping task and one task waiting in the queue.

Try shutting down both ways, measure completion time, and see which tasks run and which get interrupted.

Explain why task code must handle interruption.

### Exercise 4 — Managing an executor with Spring

Register a `ThreadPoolTaskExecutor` bean with thread name prefix, wait-on-shutdown, and await timeout.

Submit several finite-duration tasks. Close the context and verify the executor has terminated.

### Exercise 5 — Comparing `@PreDestroy` and `DisposableBean`

Create two beans:

- One bean with `@PreDestroy`.
- One bean implementing `DisposableBean`.

Close `AnnotationConfigApplicationContext` and record which callbacks run.

### Exercise 6 — Using `@Bean(destroyMethod)`

Create a hypothetical resource with a `close()` method. Register it using:

```java
@Bean(destroyMethod = "close")
```

Close the context and verify the method is called exactly once per ownership design.

### Exercise 7 — `SmartLifecycle` phases

Create two `SmartLifecycle` beans with different phases. Log start/stop ordering and explain why shutdown order is reversed.

Try forgetting to call the callback inside `stop(Runnable)` and observe the timeout.

### Exercise 8 — Graceful web server shutdown

Enable:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Create an endpoint that takes a few seconds to process. Send a request and stop the application, observing in-flight vs. new requests.

### Exercise 9 — Reproducing SIGTERM in a container

Package the application with exec-form ENTRYPOINT, run the container, and issue a stop command with a bounded grace period.

Observe shutdown hooks, Spring destroy callbacks, and process exit. Then try a shell wrapper without `exec` to understand signal forwarding.

### Exercise 10 — Reading a thread dump

Start an application having:

- An unclosed executor.
- A scheduler.
- A custom non-daemon thread.

Close the context and capture `jcmd Thread.print`. Classify each thread by owner and propose a stop callback.

### Exercise 11 — Testing a blocked cleanup bug

Create a `@PreDestroy` waiting on a latch that is never released. Observe context shutdown hanging.

Then add a timeout, log a failure code, and confirm the process can exit within its time budget.

### Exercise 12 — Shutdown when a dependency is unavailable

Create a mock client whose `close()` calls a remote endpoint. Make the remote endpoint unresponsive.

Add a cleanup timeout and explain why shutdown must never wait indefinitely on a remote dependency.

### Exercise 13 — Prototype resources

Create a prototype bean opening a resource and fetch it multiple times from a factory.

Test whether destroy callbacks run automatically. Then add an acquire/release API or make clients responsible for closing.

### Exercise 14 — Testing context lifecycle

Write a test with `AnnotationConfigApplicationContext` verifying:

- `@PreDestroy` is invoked.
- The executor is shut down.
- The executor is terminated after tasks finish.

Do not assert only `isShutdown()`.

### Exercise 15 — Batch app and exit codes

Create a non-web application using `ApplicationRunner`, process an input, and call `SpringApplication.exit(context)`.

Verify exit codes for success/failure. Confirm the runner waits for work to actually finish before closing the context.

### Exercise 16 — Designing a graceful shutdown budget

For a service with HTTP requests, a message consumer, an executor, and an HTTP client, build a timing table for each phase.

Cross-check total duration against Kubernetes `terminationGracePeriodSeconds`, define closing order, and identify which tasks can retry after restart.

## 34. Key takeaways

**Closing the Spring ApplicationContext does not mean the JVM has exited.** The context only manages the lifecycles of container-scoped beans and resources. Manually spawned threads, unmanaged executors, timers, or manually constructed clients still require explicit owners and cleanup mechanisms.

Spring provides `@PreDestroy`, `DisposableBean`, `@Bean(destroyMethod=...)`, `Lifecycle`, and `SmartLifecycle` to stop components according to lifecycle. For executors, stop accepting new tasks, await running tasks within a timeout, and interrupt when necessary; tasks must cooperate with interrupts and enforce timeouts on I/O.

For web applications, graceful shutdown stops new traffic and gives active requests bounded time to finish. In containers, this window must align with SIGTERM handling and `terminationGracePeriodSeconds`. `SIGKILL` skips shutdown hooks, so applications still need recoverability after forced termination.

When a process fails to exit, capture a thread dump and trace live threads back to their resource owner. When cleanup does not complete, check callbacks, dependency ordering, timeouts, and whether tasks are blocked. **Every resource needs an owner, a clear closing path, and an observable time limit**—that is the foundation for shutting down Spring Boot applications cleanly without leaving stray resources behind.
