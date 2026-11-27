# RejectedExecutionHandler When the Executor Is Full

In Spring Integration, a `TaskExecutor` often establishes an asynchronous boundary for a message flow. For instance, `ExecutorChannel` accepts messages from the sending thread and hands processing off to a thread pool. When all workers are busy and the queue has reached its capacity, the thread pool can no longer accept tasks. `RejectedExecutionHandler` decides what happens at that moment.

This is part of the load-shedding and throttling mechanism. Choosing the wrong policy can silently drop messages, block the sending thread for a long time, or push errors back onto the producer. Therefore, it is essential to understand when an executor rejects tasks, the impact of each policy, and how to route overload signals to the right place in the system.

## 1. When Does the Executor Reject Tasks?

With `ThreadPoolExecutor`, task admission normally follows this order:

1. If the current worker count is less than `corePoolSize`, the executor creates a worker to run the task.
2. Once core workers exist, the executor attempts to insert the task into the work queue.
3. If the queue cannot accept the task and the worker count is still below `maxPoolSize`, the executor creates an additional worker.
4. If the task cannot be queued or a new worker created, the executor invokes `RejectedExecutionHandler`.

The executor also rejects tasks once it has shut down, even if the queue is not full. Thus, a rejection can signal either overload or application shutdown.

Three parameters directly govern the overload threshold:

| Parameter | Meaning | Effect of increasing |
|---|---|---|
| `corePoolSize` | Core workers kept according to configuration | More workers processing concurrently under normal load |
| `maxPoolSize` | Maximum workers | Allows scaling workers further once the queue is full |
| `queueCapacity` | Waiting tasks accepted into the queue | Absorbs larger traffic bursts, at the cost of potentially longer wait times |

With `ThreadPoolTaskExecutor`, a positive `queueCapacity` typically creates a bounded queue; a non-positive value uses direct handoff (`SynchronousQueue`). If an unbounded queue is used, the queue almost always accepts tasks so `maxPoolSize` rarely expands workers. Under sustained load, an unbounded queue can grow memory usage and wait times until the system degrades.

Do not simply increase both the queue and worker count just to silence rejection warnings. First measure incoming message rate, average processing time, downstream dependency capacity, and the latency budget acceptable to the business.

## 2. Where Do Rejections Surface in Spring Integration?

### ExecutorChannel

`DirectChannel` invokes handlers directly on the message-sending thread. It does not submit tasks to a thread pool, so there is no channel executor rejection.

`ExecutorChannel` uses a `TaskExecutor` to offload processing to a worker thread. Under normal operation, the send call can return before the handler finishes. If the executor rejects the task at submission time, the error arises at the message-sending boundary and can be returned to the caller of `send()`.

With `ThreadPoolTaskExecutor` and the default `AbortPolicy`, Spring translates the JDK's `RejectedExecutionException` into `TaskRejectedException` when calling `execute()`. The channel or sending component may wrap the failure in a Spring Integration messaging exception; therefore, when handling errors in the application layer, inspect the root cause rather than relying solely on a single outer exception type.

### Pollers and Other Asynchronous Execution Points

A task executor can also run pollers or subscribers of a publish-subscribe channel. The policy takes effect wherever that component submits tasks to the executor. Where the failure is observed depends on the submitting component and its configuration.

Distinguish between two scenarios:

- **Task submission fails:** the executor rejects before any worker begins processing. This is the domain of `RejectedExecutionHandler`.
- **Task runs, but message processing fails:** the failure occurs inside the handler or downstream flow. Use the message flow's error-handling mechanisms, such as an appropriate error flow, retry, or dead-letter pattern as designed. The rejection handler does not replace those mechanisms.

In particular, never assume every rejection automatically routes to `errorChannel`. Rejections occur during task submission, typically on the thread calling the executor; catch and handle them at the sending boundary or upstream where retry or backpressure can be applied.

## 3. The Four Built-In JDK Policies

`RejectedExecutionHandler` is an interface with a single method:

```java
void rejectedExecution(Runnable task, ThreadPoolExecutor executor);
```

The JDK provides four standard policies:

| Policy | Behavior upon rejection | Impact on message flow |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException` | Producer receives an explicit error signal; suitable when you must know a task was not accepted |
| `CallerRunsPolicy` | Runs the task directly on the thread calling `execute()` if the executor is not shut down | Creates natural backpressure because the sending thread must do the work; can raise producer latency |
| `DiscardPolicy` | Drops the new task without reporting an error | Risks silent message loss |
| `DiscardOldestPolicy` | Drops the task at the head of the queue and retries submitting the new task | Risks losing older waiting messages; ordering and fairness can suffer |

Key details to keep in mind:

- `CallerRunsPolicy` does not run the task if the executor has already shut down. In that state, the task may be dropped without an exception.
- `DiscardOldestPolicy` better suits replaceable tasks such as latest-state updates. It is dangerous for commands or events where every message must be processed.
- `DiscardPolicy` gives the producer no signal to retry. If used for business messages, the system must explicitly tolerate data loss or have separate observability and recovery.
- `AbortPolicy` is the default for `ThreadPoolExecutor` and `ThreadPoolTaskExecutor` when no other policy is configured.

### Choosing a Policy Based on Processing Requirements

| Requirement | Recommended direction | Reason |
|---|---|---|
| Every message must be processed or return an error upstream | `AbortPolicy` | Never hides that the executor failed to accept the task |
| Producer can be slowed down briefly | `CallerRunsPolicy` | Under saturation, the producer participates in processing and throttles its send rate |
| Only the latest value matters; stale tasks are expendable | Consider `DiscardOldestPolicy` | Older queued tasks may no longer carry value |
| Secondary tasks where loss is acceptable and separately monitored | Consider `DiscardPolicy` | Intentionally drops tasks without disrupting the producer |

For orders, payments, data updates, or events requiring preservation, generally start with `AbortPolicy`, then add bounded retries or push load back to a broker. Never pick a discard policy merely to keep the send path returning success.

## 4. Configuring ThreadPoolTaskExecutor for a Flow

The following example configures an executor with a bounded queue and `AbortPolicy`. `ExecutorChannel` provides the asynchronous boundary for an order-processing flow.

```java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class OrderIntegrationConfiguration {

    @Bean("integrationTaskExecutor")
    public ThreadPoolTaskExecutor integrationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("si-order-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }

    @Bean("asyncOrdersChannel")
    public MessageChannel asyncOrdersChannel(
            @Qualifier("integrationTaskExecutor") TaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("ordersIn")
                .channel("asyncOrdersChannel")
                .handle((payload, headers) -> {
                    // Process the order on a worker thread.
                    processOrder(payload);
                    return null;
                })
                .get();
    }

    private void processOrder(Object payload) {
        // Invoke order-processing business logic.
    }
}
```

Spring manages the `ThreadPoolTaskExecutor` bean lifecycle and initializes it while building the application context. When the context stops, `waitForTasksToCompleteOnShutdown` instructs it to wait for accepted tasks to complete; `awaitTerminationSeconds` caps that wait. Shutdown settings do not turn the executor into a durable queue: remaining tasks can still go unfinished if the process is force-killed or exceeds the timeout.

With the configuration above, the queue holds at most 100 waiting tasks. Once all 8 workers are busy and the queue is full, the next task is rejected. If the executor is shutting down, new tasks are rejected as well. `AbortPolicy` ensures the submitter receives an error so it can decide whether to retry, report failure, or fall back.

## 5. How Does CallerRunsPolicy Create Backpressure?

Suppose an `ExecutorChannel` uses `CallerRunsPolicy`. When both the pool and queue are full, the thread calling `send()` can run the handler directly. If the handler takes 300 ms, that send call can likewise take roughly the handler's remaining execution duration.

This behavior slows down the producer and curbs new tasks entering the pool. However, it also alters flow behavior during overload:

- The sending thread can be blocked by downstream work.
- Latency of the HTTP request, listener, or poller sending messages can spike sharply.
- The handler may execute on a thread whose context differs from normal worker threads.
- If the producer holds a transaction or lock, running the handler on that same thread can extend resource hold times.
- With `ExecutorChannel`, an otherwise asynchronous flow can temporarily behave synchronously while the pool is saturated.

Therefore, choose `CallerRunsPolicy` only when the producer can tolerate fallback synchronous execution. Also check what the actual sending thread is: blocking a web request thread for too long can exhaust the web server's thread pool, spreading overload to unrelated requests.

## 6. Writing a Rejection Handler That Counts Rejections

When explicit metrics are needed, you can write a custom policy. The example below retains `AbortPolicy`'s fail-fast behavior while counting how many times the executor rejects tasks:

```java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.LongAdder;

public final class CountingAbortPolicy implements RejectedExecutionHandler {

    private final LongAdder rejectedCount = new LongAdder();

    @Override
    public void rejectedExecution(
            Runnable task, ThreadPoolExecutor executor) {
        rejectedCount.increment();
        throw new RejectedExecutionException(
                executor.isShutdown()
                        ? "Integration executor is shutting down"
                        : "Integration executor is saturated");
    }

    public long getRejectedCount() {
        return rejectedCount.sum();
    }
}
```

Register this policy on `ThreadPoolTaskExecutor` via `setRejectedExecutionHandler(new CountingAbortPolicy())`. In production applications, feed the counter into Micrometer or your metrics system to track rejection rates over time. The counter in this example only illustrates behavior; when running multiple executors or multiple application instances, export metrics tagged with executor and instance identifiers.

Avoid logging a full stack trace at high severity for every single rejection while the system is overloaded. A flood of logs can worsen the situation. Use counters, rates, rate-limited logs, and threshold alerts.

A custom handler receives a `Runnable`, not a `Message<?>` directly. Hence, do not attempt to inspect messages by casting internal Spring Integration task wrappers. If handling by message ID, correlation ID, or business attributes is needed, do it at the message flow or producer layer where the message is still represented by explicit types.

## 7. Handling Rejections at the Message-Sending Boundary

With a throwing policy, the producer can catch submission errors and decide the next action. Illustrative example:

```java
try {
    messagingTemplate.send("ordersIn", message);
} catch (RuntimeException ex) {
    if (hasRejectedExecutionCause(ex)) {
        // Record overload and perform bounded retry,
        // or let the upstream broker redeliver per acknowledgement semantics.
    } else {
        throw ex;
    }
}
```

`hasRejectedExecutionCause` here is an application helper inspecting the `cause` chain for `TaskRejectedException` or `RejectedExecutionException`; its exact name and implementation depend on your Spring version and the wrapper exceptions around the send call. Never retry infinitely in a tight loop on the same thread. Retries need bounds, backoff, jitter where appropriate, and idempotent processing so redelivered messages do not cause duplicate side effects.

If messages arrive from a broker, consider letting the broker hold messages until the consumer can accept again, depending on the connector's acknowledgement semantics. If messages live only in producer or executor memory, process termination can lose that backlog.

When a buffer is needed between producer and consumer, you can use a `QueueChannel` with a poller to separate message intake from processing. Configure queue limits and full-queue behavior. If backlog must survive restarts, use a durable message store or broker suited to the requirements. A thread pool's internal queue is only a waiting area for runnable tasks, not a durable message store.

## 8. Watching for Saturation Signals

An executor can cause severe latency long before rejections appear if its queue grows continuously. Monitor together:

- Active worker count and total worker count.
- Queue length and remaining capacity.
- Task submission, completion, and rejection rates.
- Queue wait time and handler execution duration.
- Downstream error rates, timeouts, and retries.
- Producer latency when using `CallerRunsPolicy`.

Read these metrics together to isolate causes. A growing queue accompanied by falling completions typically points to slow downstream systems or stuck workers. Sudden spikes in rejections can result from traffic surges, slow dependencies, undersized pools, or executor shutdown. Raising `maxPoolSize` helps little if a database connection pool or downstream API is already the bottleneck.

When troubleshooting an incident, check in order: incoming message rate, handler duration, dependency health, queue depth, and workers. Then pick a controlled action: throttle producers, tune concurrency, scale downstream capacity, or shift backlog to a broker. Do not blindly enlarge the queue, because a larger queue turns rejections into long wait times and heavy memory consumption.

## 9. Testing Rejection Deterministically

You can test `AbortPolicy` using a pool with a single worker and a queue holding a single task. The first task occupies the worker, the second fills the queue slot, and the third must be rejected:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class RejectedExecutionHandlerTests {

    @Test
    void abortPolicyRejectsWhenWorkerAndQueueAreFull() throws Exception {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1,
                1,
                0,
                TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            executor.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker did not start");
            }

            executor.execute(() -> { }); // Second task sits in the queue.

            assertThrows(
                    RejectedExecutionException.class,
                    () -> executor.execute(() -> { })); // Third task is rejected.
        } finally {
            release.countDown();
            executor.shutdown();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

When testing with `ThreadPoolTaskExecutor`, also verify the Spring exception observed on `execute()` and on sending messages through the channel. For `CallerRunsPolicy`, verify that the task actually executes on the calling thread when the pool is saturated. For discard policies, verify that a metric or business signal detects dropped tasks; without that signal, tests can easily produce false passes.

## 10. Production Readiness Checklist

- Use a bounded queue and size `corePoolSize` and `maxPoolSize` from measured load.
- Explicitly define which messages may be dropped and which must be preserved.
- Choose an appropriate policy; for critical business messages, prefer observable, actionable rejections.
- Handle submission errors at the producer or upstream; do not confuse rejections with handler errors occurring after a task starts.
- Apply bounded retries, backoff, and idempotency; avoid retry loops that amplify load during congestion.
- Monitor queue depth, active workers, wait times, throughput, and rejection rates.
- Test shutdown behavior and task drain times.
- When durable backlog storage is needed, use an appropriate message store or broker instead of relying on an executor's internal queue.

`RejectedExecutionHandler` defines how the system reacts when an executor cannot accept more work. A sound configuration makes three things explicit: whether rejected tasks are reported upstream, whether the producer can be blocked, and how messages are preserved. When those three decisions are designed alongside queue limits and downstream capacity, Spring Integration can respond predictably whenever load exceeds processing capacity.
