# Customizing ExecutorService and Resource Lifecycle

## Role of executors in Resilience4j integration

A Circuit Breaker decides whether a call is permitted to reach a dependent service and records the call's outcome. The Circuit Breaker itself does not create a thread pool to run every call. In the Spring Cloud Circuit Breaker integration with Resilience4j, executors typically appear in two scenarios: scheduling `TimeLimiter` timeout tasks and executing asynchronous work or isolating execution with a thread pool.

Distinguishing resource types helps avoid misusing thread pools:

| Resource | Role | Management approach |
| --- | --- | --- |
| Factory's `ScheduledExecutorService` | Schedules timeout-related tasks in the Resilience4j integration. | Configured via `Resilience4JCircuitBreakerFactory`; managed as a shared Spring bean. |
| Application's `ExecutorService` | Runs asynchronous work proactively submitted by the application. | Created, load-bounded, and closed by the application following the ApplicationContext lifecycle. |
| `ThreadPoolBulkhead`'s thread pool | Isolates thread counts and queues dedicated to a group of calls. | Configured via ThreadPoolBulkhead policy; do not use the timeout scheduler as a substitute. |

In many applications, the most important customization is the scheduler that `Resilience4JCircuitBreakerFactory` uses for `TimeLimiter`. This scheduler needs to run stably across the application's entire lifecycle. Do not create a new executor per request or per `create()` call.

## Customizing ScheduledExecutorService for CircuitBreakerFactory

Spring Cloud Circuit Breaker allows configuring the factory's executor using `configureExecutorService`. You can declare a `ScheduledThreadPoolExecutor` as a Spring bean, then pass that bean into a `Customizer`:

```java
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.scheduling.concurrent.CustomizableThreadFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CircuitBreakerExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService circuitBreakerScheduler() {
        ScheduledThreadPoolExecutor executor = new ScheduledThreadPoolExecutor(
            4,
            new CustomizableThreadFactory("circuit-breaker-timeout-")
        );
        executor.setRemoveOnCancelPolicy(true);
        executor.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        executor.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
        return executor;
    }

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> circuitBreakerExecutorCustomizer(
            @Qualifier("circuitBreakerScheduler")
            ScheduledExecutorService scheduler) {
        return factory -> factory.configureExecutorService(scheduler);
    }
}
```

In the example, `circuitBreakerScheduler` is a singleton bean. The factory receives this same scheduler rather than creating a separate pool per breaker. `CustomizableThreadFactory` sets a thread name prefix for easy identification when reading thread dumps or logs. `setRemoveOnCancelPolicy(true)` removes canceled tasks from the delay queue, avoiding retaining large numbers of unneeded timeout tasks. The two shutdown policies prevent delayed or periodic tasks from continuing to run once the application begins shutting down.

A thread count of 4 is only an illustrative value. Choose it according to the number of timeouts that must be handled concurrently, load levels, and the characteristics of scheduled tasks. The scheduler's job is typically handling short timeout signals; do not run long-blocking I/O or heavy computation tasks on this pool. A blocking task can occupy a worker and delay timeout signaling for other calls.

The specific configuration API must match the Spring Cloud Circuit Breaker version in use. The Resilience4j starter already provides the factory and auto-configuration; `Customizer` merely adds configuration to the existing factory. Avoid declaring a new factory just to swap the scheduler, as doing so can accidentally replace configurations and beans created by the starter.

## Executor lifecycle in Spring

An executor is a stateful resource that creates threads. When Spring creates the bean, the pool starts serving work; when the ApplicationContext closes, the pool must be shut down so the JVM can exit cleanly.

With the bean in the example, `destroyMethod = "shutdown"` instructs Spring to call `shutdown()` when the bean is destroyed. This works well when the scheduler is shared throughout the application's lifecycle. Typical management steps are:

1. Create the executor once when the ApplicationContext starts.
2. Inject the executor into the customizer and let the factory use it.
3. Never call `shutdown()` after individual requests, per circuit breaker, or inside fallbacks.
4. When the application stops, Spring invokes the bean's destroy method to stop accepting new tasks.
5. If the application needs to wait for in-flight tasks to finish within a deadline, add a graceful shutdown policy with a bounded wait time.

`shutdown()` does not force currently running tasks to stop immediately. It rejects new tasks and gives already-accepted tasks a chance to complete according to the executor's policy. `shutdownNow()` attempts to interrupt running workers and returns tasks that have not started; interruption only works if tasks cooperate with interrupts. Therefore, do not use `shutdownNow()` as a substitute for network call timeouts.

If bounded graceful shutdown is required, you can wrap the executor in a dedicated managed bean:

```java
import java.time.Duration;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public final class ManagedScheduler implements AutoCloseable {
    private final ScheduledExecutorService delegate;
    private final Duration shutdownWait;

    public ManagedScheduler(
            ScheduledExecutorService delegate,
            Duration shutdownWait) {
        this.delegate = delegate;
        this.shutdownWait = shutdownWait;
    }

    public ScheduledExecutorService executor() {
        return delegate;
    }

    @Override
    public void close() {
        delegate.shutdown();
        try {
            if (!delegate.awaitTermination(
                    shutdownWait.toMillis(), TimeUnit.MILLISECONDS)) {
                delegate.shutdownNow();
            }
        } catch (InterruptedException interrupted) {
            delegate.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

This is an application-defined management class. If you use it as a bean, ensure only one owner is responsible for closing `delegate`; do not simultaneously let another bean shut down the same executor. The wait duration must be finite so application shutdown cannot hang indefinitely. Restoring the interrupt flag after catching `InterruptedException` preserves the stop signal for the current thread.

In simpler cases, an executor bean with `destroyMethod = "shutdown"` is usually sufficient. Only add a graceful shutdown wrapper when the application has explicit requirements around finishing in-flight work before process exit.

## Distinguishing timeout schedulers from business execution executors

The factory's `configureExecutorService` is for the executor that the Resilience4j integration uses for scheduling. It does not automatically turn every call to a dependent service into a call running on that pool. If the application needs to run an asynchronous task, declare a separate executor sized for that task's load:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.scheduling.concurrent.CustomizableThreadFactory;

@Bean(name = "catalogIoExecutor", destroyMethod = "shutdown")
ExecutorService catalogIoExecutor() {
    return Executors.newFixedThreadPool(
        8,
        new CustomizableThreadFactory("catalog-io-")
    );
}
```

Then pass this executor directly into the application's asynchronous API, such as `CompletableFuture.supplyAsync(task, catalogIoExecutor)`. Set concurrency limits matching the dependent service's capacity and the process's resource bounds. If work can block for a long time, configure timeouts on the HTTP client or corresponding `TimeLimiter`; do not assume that using a thread pool implies having a timeout.

Do not share a single pool across all types of work if their loads can interfere with one another. A burst of slow I/O can exhaust workers and delay other tasks. Separating the timeout scheduler from the I/O executor gives timeout tasks a fair chance to execute on time.

## ThreadPoolBulkhead owns a different pool

Resilience4j `ThreadPoolBulkhead` provides isolation with its own core threads, max thread limit, and queue. It is suited for capping concurrent work dedicated to a dependent service. This is a different resource from the scheduler configured for `TimeLimiter`.

Example configuration via `application.yml`:

```yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      catalog:
        maxThreadPoolSize: 8
        coreThreadPoolSize: 4
        queueCapacity: 20
        keepAliveDuration: 20ms
```

`coreThreadPoolSize` is the baseline worker count, `maxThreadPoolSize` is the worker cap, `queueCapacity` bounds queued tasks, and `keepAliveDuration` controls how long excess workers are retained per pool policy. When the queue is full and the pool cannot accept more work, calls may be rejected. The application must handle this as an overload signal, potentially recording metrics and returning an appropriate response.

Do not increase `queueCapacity` without bound to mask a lack of processing capacity. Large queues increase wait times, hold onto many tasks, and can cause requests to expire before they even start running. Choose concurrency and queue limits based on latency targets, processing time, and the target service's capacity.

When using Resilience4j's registry or provider, let the bulkhead manager control its pool lifecycle according to the library version. Do not take the factory's scheduler and pass it to `ThreadPoolBulkhead` or manually shut down an internal pool while the registry is still using it. If you manually create a `ThreadPoolBulkhead` or registry, clearly identify which component owns the resource and invoke the corresponding close mechanism when the ApplicationContext stops.

## Context propagation and thread observability

A task running on a different thread does not automatically carry all `ThreadLocal` state from the original calling thread. This can affect MDC logging, tracing, or security context. If the application needs to propagate context across schedulers or executors, use a context propagation mechanism compatible with the Spring and library versions in use, or wrap tasks with an appropriate decorator.

Do not indiscriminately copy all `ThreadLocal` variables. Only propagate necessary context, clean up after the task completes, and verify that data from a previous request does not leak into a subsequent request on the same worker. When replacing a context-aware default executor with a plain executor, re-verify tracing and logging behavior.

Monitor the following indicators:

- Active worker counts and queued task counts.
- Counts of timed-out, canceled, or rejected tasks.
- Queue wait time and execution duration.
- Threads remaining alive after the ApplicationContext begins shutting down.
- Thread names in thread dumps to distinguish timeout schedulers, I/O executors, and bulkheads.

Clear thread names such as `circuit-breaker-timeout-` and `catalog-io-` help identify which pool is bottlenecked. Combine executor metrics with Circuit Breaker metrics to tell whether failures stem from the dependent service, timeouts, or worker starvation.

## Common resource management mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Creating a new executor on every factory call or request. | Thread count grows, hard to bound resources, and potential thread leaks. | Declare a singleton executor or intentionally workload-scoped pools. |
| Not closing the executor when Spring stops. | Live threads prevent the process from exiting cleanly. | Use bean lifecycle with `destroyMethod` or a bounded graceful shutdown mechanism. |
| Calling `shutdown()` inside a fallback. | A single service error can stop the pool from serving subsequent requests. | Only close resources at the component that owns their lifecycle. |
| Using the timeout scheduler to run blocking I/O. | Other timeout tasks get delayed because scheduler workers are occupied. | Separate the scheduler from business executors. |
| Using an unbounded bulkhead queue. | Memory and latency grow, requests expire while waiting. | Set a finite `queueCapacity` and handle rejections. |
| Replacing the default executor without checking context propagation. | Missing trace IDs or MDC in worker thread logs. | Add context propagation and verify context cleanup. |

## Pre-production verification checklist

1. Identify which executor serves `TimeLimiter`, which executes business tasks, and which pool belongs to `ThreadPoolBulkhead`.
2. Declare each pool in the right ownership scope, assign recognizable thread names, and bound its size.
3. Inject the scheduler into `Resilience4JCircuitBreakerFactory` via a `Customizer`.
4. Confirm timeouts fire accurately, calls do not block on the scheduler, and fallbacks never close shared resources.
5. Shut down the ApplicationContext in a test environment, observe threads, and verify executors shut down cleanly.
6. Re-verify metrics, tracing, and logs after replacing the default executor.

When customizing `ExecutorService`, the goal is clear control over who creates, who uses, and who closes each pool. Proper lifecycle management keeps the Resilience4j integration stable as load rises, when timeouts occur, and as the application starts up or shuts down in a Spring Cloud system.
