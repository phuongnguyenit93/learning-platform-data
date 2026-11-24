# Lifecycle Management for Executors, Schedulers, Clients, and Connection Resources

## Objectives

After this lesson, you will be able to:

- Identify which component creates, owns, and is responsible for closing each resource.
- Distinguish the lifecycles of application singletons, tasks, subscriptions, workers, and connections.
- Configure bounded executors and schedulers with explicit shutdown policies.
- Use Spring lifecycle hooks to stop accepting work, wait for running tasks, and release resources in the right order.
- Close application-owned RSocket clients and transports while leaving framework-managed shared resources intact.
- Test graceful shutdown, timeouts, rejected tasks, and thread/connection leaks.

## 1. Why Must Resource Lifecycles Be Managed?

Spring Messaging applications typically hold resources that outlive a single request:

- Executors and thread pools processing messages asynchronously.
- Reactor `Scheduler` instances coordinating work across threads.
- `Subscription` and `Scheduler.Worker` instances for individual processing flows.
- `RSocketRequester`, WebSocket sessions, or broker client connections.
- Connection pools, timers, buffers, and message-receiving listeners.
- Consumers, adapters, or containers maintaining connections to external systems.

Each resource has its own creation point, usage scope, and termination procedure. When not closed properly, the application can suffer from:

- Threads remaining alive after the Spring context closes, preventing the JVM from exiting.
- New messages still arriving while dependencies have already begun shutting down.
- Queues continuing to accept work with no workers left to process them.
- Sockets or connection pools held open after they are no longer needed.
- Subscriptions continuing to emit data and retain references to stopped objects.
- Tasks lost mid-execution or cancelled without clear business state.
- Test contexts closing while threads from a prior test interfere with the next test.

Lifecycle management is not merely calling a `close` method. It is a contract defining **who owns the resource, when it stops accepting work, how in-flight work is handled, and when it is released**.

## 2. Distinguishing Ownership and Scope

First principle: the component that creates or is granted ownership of a resource is responsible for terminating that resource. A component that merely borrows a resource must not close it unilaterally.

| Scope | Examples | Typical Owner | When Released |
| --- | --- | --- | --- |
| Application | `ThreadPoolTaskExecutor`, client singleton | Spring `ApplicationContext` or owning component | On context shutdown |
| Connection | RSocket connection, WebSocket session | Component that opens/receives connection ownership | When peer closes, session ends, or component shuts down |
| Worker | Reactor `Scheduler.Worker` | Component that creates the worker | When work using the worker finishes |
| Subscription | `Disposable`/subscribe handle | Component that calls `subscribe` | When stream completes, errors, or is no longer needed |
| Task | `Future`, scheduled task | Component that submits the task | When task completes or is cancelled per policy |

Examples:

- A bean that creates an `RSocketRequester` to call a remote service is responsible for disposing the requester when the bean/context terminates.
- A handler receiving a connection's `RSocketRequester` via a server callback does not automatically own that connection. The framework/server manages its lifecycle; the handler closes the connection only if business logic explicitly requires disconnecting the peer.
- A service using a singleton `Scheduler` injected by Spring must not dispose the `Scheduler` on every message.
- A component creating its own `Scheduler.Worker` must dispose the worker when it is no longer needed.

Before adding cleanup, answer three questions:

1. Where is the resource created?
2. Who is allowed to use it, and who owns it?
3. Do any other components still depend on it during shutdown?

Do not close a resource solely because you hold a reference to it.

## 3. Spring `ApplicationContext` Lifecycle

Spring manages singleton beans according to the `ApplicationContext` lifecycle. At startup, the container instantiates beans, injects dependencies, and invokes initialization callbacks. On shutdown, the container invokes destruction callbacks according to the lifecycle contract.

Common mechanisms:

- **`@Bean(destroyMethod = "...")`:** declares the destruction method for a bean created by a configuration class.
- **`@PreDestroy`:** callback invoked before the bean is destroyed.
- **`DisposableBean`:** bean directly implements the destroy callback.
- **`Lifecycle` / `SmartLifecycle`:** components needing coordinated start/stop, especially background listeners and adapters.
- **`AutoCloseable` / `close()`:** resources with a standard close contract; Spring can infer the destroy method in many cases.

Choose one mechanism suited to the resource type. There is no need to call shutdown simultaneously in `@PreDestroy`, `DisposableBean`, and `destroyMethod` for the same executor. Cleanup should have a single owner and one clear path that is safe to invoke repeatedly if the framework does so.

### `@Bean` with `destroyMethod`

For resources with an explicit close/shutdown method, you can declare:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MessagingResourceConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService messageExecutor() {
        return Executors.newFixedThreadPool(8);
    }
}
~~~

Spring calls `shutdown` when the bean is destroyed. However, `shutdown` only stops accepting new tasks and lets already-submitted tasks continue; it does not enforce an indefinite wait timeout by itself. If you need a specific drain window and a fallback to `shutdownNow`, use a lifecycle-managing component with `awaitTermination` logic.

### `@PreDestroy`

For a component owning multiple resources, `@PreDestroy` can consolidate cleanup in one place:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class MessagingResourceOwner {

    private final SomeClient client;

    MessagingResourceOwner(SomeClient client) {
        this.client = client;
    }

    @PreDestroy
    void close() {
        client.close();
    }
}
~~~

This is a structural example; `SomeClient` must expose an appropriate `close` method. If the client is already managed by Spring as a separate bean with a destroy method, do not close it again from another component. Avoid long-running blocking network calls inside `@PreDestroy` if shutdown can be coordinated asynchronously via `SmartLifecycle`.

## 4. Ordered Shutdown: Stop Ingress First, Drain Afterward

A messaging system should not stop every resource at the same moment. Shut down along the dependency graph.

A typical sequence:

1. **Stop ingress:** stop receiving new messages from brokers, WebSockets, or RSocket listeners.
2. **Stop generating new work:** stop periodic schedulers, timers, and internal producers.
3. **Drain in-flight work:** allow consumers/handlers to finish within a deadline; handle tasks exceeding the deadline per policy.
4. **Close outbound clients and connections:** after tasks are no longer calling dependencies.
5. **Shut down executors and schedulers:** reject new tasks, wait for remaining tasks, and release threads.
6. **Close telemetry and logging last:** ensure shutdown logs and metrics are still recorded.

The exact order depends on dependency relationships. For instance, an executor processing messages needs an outbound client; therefore, the client must outlive tasks using it. Closing the client before draining the executor causes remaining tasks to fail en masse.

### `SmartLifecycle` and Phases

`SmartLifecycle` suits components that start/stop and must coordinate with other components. Spring starts components in ascending phase order and stops them in descending phase order. Consequently, a listener/ingress with a higher phase than the worker it uses will generally stop before the worker.

Illustrative example:

~~~java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
class MessageIngressLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        // Start the listener or message-receiving adapter.
        running = true;
    }

    @Override
    public void stop() {
        // Stop accepting new messages.
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
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

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

This is an illustrative skeleton: `start`/`stop` must invoke the real listener/container APIs. For asynchronous `stop`, invoke `callback` only after the stop operation finishes. Invoking the callback too early lets Spring proceed to destroy dependencies while the listener is still active.

A dependent worker/executor can use a lower phase, such as `0`, so the phase `100` listener stops first. Do not pick arbitrary phase numbers without mapping dependencies among components.

## 5. Managing `ExecutorService`

`ExecutorService` has two important shutdown steps:

- **`shutdown()`:** rejects new tasks while allowing already-submitted tasks to continue.
- **`shutdownNow()`:** requests immediate stop by interrupting running tasks and returns the list of tasks that had not started; tasks must cooperate with interruption to terminate.

Do not call `shutdownNow` right when the application starts stopping if you want in-flight messages to finish. Allow a finite drain window first, then fall back.

Java 17 example:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorShutdownDemo {

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        executor.submit(() -> System.out.println("task-finished"));
        executor.shutdown();

        try {
            boolean terminated =
                    executor.awaitTermination(2, TimeUnit.SECONDS);

            if (!terminated) {
                executor.shutdownNow();
                terminated = executor.awaitTermination(1, TimeUnit.SECONDS);
            }

            System.out.println("terminated=" + terminated);
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Run with Java 17:

~~~bash
javac ExecutorShutdownDemo.java
java ExecutorShutdownDemo
~~~

Exact stdout:

~~~text
task-finished
terminated=true
~~~

When `awaitTermination` is interrupted, call `shutdownNow` if policy requires stopping and restore the interrupt flag via `Thread.currentThread().interrupt()`. Never swallow `InterruptedException` and keep running as if nothing happened.

Long-running tasks must check interruption or use timeout-capable APIs. A task that ignores interruption can prevent `shutdownNow` from terminating. Never run unbounded blocking work on event-loop threads.

## 6. Configuring `ThreadPoolTaskExecutor` in Spring

`ThreadPoolTaskExecutor` integrates with the Spring lifecycle. When declared as a bean, the container manages initialization and shutdown. Set thread bounds, queue capacity, and wait times to match application load.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class MessagingExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor messageExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("message-worker-");

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);

        return executor;
    }
}
~~~

Meaning:

- `corePoolSize` is the baseline thread count kept alive under low load.
- `maxPoolSize` caps the maximum number of threads.
- `queueCapacity` caps waiting tasks before the executor expands threads or rejects per configuration.
- `waitForTasksToCompleteOnShutdown` instructs it to wait for accepted tasks to finish during shutdown.
- `awaitTerminationSeconds` sets the wait limit.

Do not set `queueCapacity` excessively high merely to avoid rejections. Long queues increase latency and retain payloads/objects in memory. When the executor rejects a task, the application needs an explicit response: bounded retry, overload error, or returning the message to the broker per acknowledgement policy.

When an executor is already a Spring bean, do not call `shutdown` after every batch or request. Let the container manage its lifecycle. If listeners must stop before the executor, configure phases or use an explicit lifecycle coordinator.

## 7. Managing Reactor `Scheduler` and Subscriptions

A Reactor `Scheduler` is a resource with its own lifecycle. Distinguish two categories:

- Reactor shared schedulers such as `Schedulers.parallel()`, `Schedulers.boundedElastic()`, and `Schedulers.single()`.
- Application-created schedulers such as `Schedulers.newParallel(...)` or `Schedulers.newBoundedElastic(...)`.

Shared schedulers are cached and shared across many components. Never dispose a common `Scheduler` just because one service stops using it; doing so can break other pipelines. Schedulers created and owned by the application must be disposed.

Example declaring a dedicated `Scheduler` as a Spring bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
class ReactorSchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    Scheduler messagingScheduler() {
        return Schedulers.newBoundedElastic(
                8,
                500,
                "messaging-io");
    }
}
~~~

Bounding threads and queued tasks lets the `Scheduler` reject load beyond capacity instead of holding an unbounded queue. Pick actual limits based on workload and machine resources.

`Scheduler` provides `disposeGracefully()` to request graceful resource release. It returns a lazy `Mono`; subscribe or block with a timeout inside an appropriate lifecycle coordinator. If graceful disposal exceeds the deadline, fall back to `dispose()` per policy. Never call `disposeGracefully()` and discard the returned publisher assuming cleanup has already started.

Each separately created `Scheduler.Worker` must also be disposed when leaving scope. Likewise, a subscription created via `subscribe()` returns a `Disposable`; if the stream must stop with a component's lifecycle, keep the handle and dispose it when the component stops.

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;

@Component
class MessageSubscriptionOwner {

    private final Disposable subscription;

    MessageSubscriptionOwner(MessageSource source) {
        this.subscription = source.messages()
                .subscribe(this::handle, this::handleError);
    }

    private void handle(MessageEvent event) {
        // Process the message.
    }

    private void handleError(Throwable error) {
        // Log/record the error and apply policy.
    }

    @PreDestroy
    void stop() {
        subscription.dispose();
    }
}
~~~

`MessageSource` and `MessageEvent` represent application abstractions. For publishers whose lifecycle is managed by the framework, use the framework's lifecycle contract instead of subscribing manually a second time.

## 8. Closing `RSocketRequester` and Client Connections

`RSocketRequester` is the client API for sending requests over RSocket. When the application creates and owns a client requester, it must be disposed when no longer used or on application context shutdown. `RSocketRequester` implements `Disposable`; `dispose()` closes the underlying transport connection and notifies subscribers.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
class RSocketClientConfiguration {

    @Bean(destroyMethod = "dispose")
    RSocketRequester remoteRequester() {
        return RSocketRequester.builder()
                .tcp("localhost", 7000);
    }
}
~~~

This is a client requester created and owned by the application. If a requester is received as a connection-specific argument inside a server-side handler, do not dispose it just because the handler finished one request; that connection belongs to the server/framework lifecycle.

During shutdown, stop producers/consumers using the requester first, drain running requests within bounds, and then dispose the requester. New requests after disposal must be rejected or routed through a new client/connection per policy; never reuse a disposed requester.

For WebSocket/STOMP or broker clients, apply the same principles:

- Stop message-receiving adapters/listeners first.
- Stop publishing new messages.
- Wait for acknowledgements and active processing within a deadline.
- Close component-owned sessions/connections/clients.
- Cancel associated timers, heartbeat tasks, and subscriptions.

If the framework or a connection factory already manages the lifecycle, call stop/close on the proper framework abstraction. Never close the underlying socket while a broker container still thinks the connection is active.

## 9. Graceful Shutdown and Deadlines

Graceful shutdown does not mean waiting indefinitely for every task. Every stage needs an explicit deadline:

| Stage | Action | What Happens on Deadline Expiration |
| --- | --- | --- |
| Stop ingress | Stop accepting new messages | Close listeners/sessions per policy |
| Drain in-flight | Wait for handlers and acknowledgements | Cancel or mark for retry/redelivery |
| Close outbound clients | Close connections after tasks finish | Cancel hung requests and record errors |
| Shut down workers | Reject new tasks, wait for workers to finish | Interrupt/fallback dispose |
| Finalize telemetry | Flush logs/traces/metrics | End by timeout so JVM can exit |

The overall deadline must be smaller than the container/orchestrator's termination grace period. If Kubernetes gives the process only a short grace period while the application waits too long on executors, the process will be killed before cleanup completes.

Distinguish:
- **Task completed:** business logic and acknowledgement finished.
- **Task cancelled:** computation stopped, though side effects may already have occurred.
- **Message redelivered:** broker redelivers per acknowledgement/retry policy.
- **Request timed out:** caller stopped waiting; server may still be processing.

Never send an ACK before required side effects have committed. Never treat cancellation as a rollback. For operations with side effects, use idempotency and reconciliation to handle shutdown occurring mid-flight.

## 10. Avoiding Common Lifecycle Mistakes

- **Closing shared resources:** one service disposes a `Scheduler` or connection pool used by many services, breaking other components.
- **Leaking self-created resources:** custom executors, schedulers, workers, or requesters leave threads/sockets alive after shutdown.
- **Closing clients before workers:** running tasks keep calling closed clients and fail in bulk.
- **Waiting indefinitely:** `awaitTermination` without a timeout hangs shutdown.
- **Using unbounded queues:** rising load increases latency and memory until OOM.
- **Ignoring rejections:** tasks are rejected yet messages are already ACKed or lack a retry path.
- **Subscribing without keeping `Disposable`:** unable to proactively stop the subscription on lifecycle boundaries.
- **Closing subscriptions too early:** in-flight messages are cancelled without clear retry/ack policies.
- **Calling cleanup in multiple places:** `@PreDestroy`, `destroyMethod`, and another callback all close the same resource, creating unpredictable ordering.
- **Spawning a thread per request:** threads are not reused and counts become uncontrollable.
- **Blocking the event loop:** shutdown or network waits on an event loop stall many unrelated connections.

## 11. Testing Lifecycles and Resource Leaks

Do not test only that a `close` method was called. Verify the system actually stops accepting work, drains properly, closes connections, and leaves no stray threads or tasks behind.

Key tests:

1. **Context shutdown:** create an `ApplicationContext`, retrieve executor/scheduler/client beans, close the context, and verify owned resources are disposed.
2. **In-flight task:** submit a task guarded by a latch, initiate shutdown, and verify the task is allowed to finish within the deadline.
3. **Task exceeding deadline:** hold a task longer than the timeout, verify fallback interrupt/dispose runs and shutdown completes.
4. **New task after shutdown:** verify the executor rejects new tasks.
5. **Listener ordering:** when ingress stops, workers stay alive until in-flight messages finish draining.
6. **RSocket close:** dispose the requester and verify `onClose` completes; new requests cannot be sent on a closed requester.
7. **Subscription cleanup:** dispose a subscription and verify the publisher stops emitting items.
8. **Context restart:** close and recreate the `ApplicationContext`, verifying no old threads or ports remain held.
9. **Repeated close:** invoke shutdown/dispose per contract and confirm cleanup causes no errors or duplicate side effects.
10. **Leak checks:** inspect thread name prefixes, connection counts, active task counts, and file/socket handles before and after tests.

Never use `Thread.sleep` to wait for shutdown. Use `CountDownLatch`, Awaitility, or `StepVerifier` with timeouts. Tests must have finite deadlines so failures do not hang CI.

Example verifying an executor terminates:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class ExecutorLifecycleTest {

    @Test
    void executorTerminatesAfterShutdown() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        executor.submit(() -> {
            // Finite task.
        });

        executor.shutdown();

        assertTrue(executor.awaitTermination(2, TimeUnit.SECONDS));
    }
}
~~~

In Spring integration tests, prefer testing the real bean lifecycle rather than calling shutdown manually first and testing only JDK objects. With real clients, verify the peer observes the close signal and the server no longer holds the old connection/session.

## 12. Observing Resources in Production

To detect leaks and stuck shutdowns, monitor:

- Thread counts by prefix and thread state.
- Active threads, pool size, queue size, and rejected task counts.
- In-flight messages, pending acknowledgements, and drain duration.
- Open connections/sessions, closed connection counts, and close reasons.
- Active subscriptions/workers where the application can measure them.
- Shutdown timeout counts and interrupted task counts.
- Elapsed time from shutdown signal until process exit.

Metric tags should have low cardinality: executor name, client name, operation type. Never use message IDs, user IDs, or connection IDs as metric tags. Identifying details belong in controlled logs.

During incidents, thread dumps help find blocked workers or tasks ignoring interrupts. Connection metrics and lifecycle logs distinguish leaked connections from intentionally retained connections.

## 13. Deployment Checklist

- [ ] Every executor, scheduler, client, and connection has an explicit owner.
- [ ] Shared resources are never disposed by consumers that merely borrow them.
- [ ] Executors have bounded threads, queues, and rejection policies.
- [ ] Self-created schedulers are disposed; common `Scheduler` instances are not closed arbitrarily.
- [ ] Subscriptions and `Worker` instances keep handles for scope-appropriate cancellation.
- [ ] Application-owned `RSocketRequester` instances are disposed on shutdown.
- [ ] Ingress stops before workers and outbound dependencies.
- [ ] In-flight tasks have explicit drain deadlines and fallbacks.
- [ ] Interruptions are handled properly without swallowing `InterruptedException`.
- [ ] Messages are never ACKed before required side effects commit.
- [ ] Tests cover context shutdown, in-flight tasks, timeouts, and resource leaks.
- [ ] Production metrics track threads, queues, connections, and shutdown duration.

## References

- [Spring Framework Reference — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework API — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Framework API — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Project Reactor API — Scheduler](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Scheduler.html)
- [Java API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
