# ExecutorChannel Dispatcher and Async Handoff

`ExecutorChannel` is a point-to-point channel in Spring Integration that uses a `TaskExecutor` to offload handler invocation to a worker thread. When a producer sends a message, the channel submits a task to the executor; a worker thread then performs the dispatch to the selected subscriber. As a result, the producer can proceed once the executor accepts the task without waiting for the handler to finish.

An async handoff introduces a new execution boundary. It changes when `send()` returns, how exceptions are observed, processing order, transaction boundaries, and propagation of thread-bound data. Understanding these changes helps avoid mistakenly assuming a message has been processed just because the send operation succeeded.

## 1. Where Does ExecutorChannel Sit in a Flow?

In a typical message flow, a producer sends a message into a channel and the channel passes it to a consumer. With `DirectChannel`, the subscriber is invoked synchronously on the sending thread. With `ExecutorChannel`, the channel submits a task to a `TaskExecutor` for asynchronous dispatch.

```mermaid
flowchart LR
    P[Producer thread] --> S[send message]
    S --> EC[ExecutorChannel]
    EC -->|submit task| Q[Executor task queue]
    Q --> W[Worker thread]
    W --> D[Dispatcher selects subscriber]
    D --> H[Message handler]
```

Main steps:

1. Producer calls `send()` on `ExecutorChannel`.
2. The channel creates a dispatch task for the message and submits it to `TaskExecutor`.
3. The executor accepts the task or rejects it if overloaded or shut down.
4. A worker thread picks up the task and the dispatcher invokes the selected handler.
5. The handler completes or raises an error on the worker thread.

The queue in the diagram is the executor's task queue, not a separate `QueueChannel` created by Spring Integration. `ExecutorChannel` is not a message broker and does not automatically provide persistence or acknowledgments for queued tasks.

## 2. Comparing DirectChannel and ExecutorChannel

| Characteristic | `DirectChannel` | `ExecutorChannel` |
|---|---|---|
| Dispatch | Synchronous on the sending thread | Submits task to an executor |
| When handler runs | Within the `send()` call stack | On a worker thread when the executor executes the task |
| When `send()` returns | Usually after dispatch/handler finishes | Usually after the task is accepted by the executor |
| Exceptions from handler | Can propagate to the caller | Occur asynchronously; caller usually does not receive them directly |
| Transaction | Can share the producer's thread and active transaction | Does not carry the sender's thread-bound transaction to the worker |
| Completion order | Follows synchronous dispatch | Can differ from send order when multiple workers process concurrently |
| Resources to manage | Caller's thread | Executor, workers, task queue, and rejection policy |

`DirectChannel` is appropriate when you want immediate execution in the sending call flow and need exceptions/transactions in the same call stack. `ExecutorChannel` is appropriate when you want to decouple processing time from the producer, allow parallel worker execution, and accept asynchronous semantics.

Do not swap `DirectChannel` for `ExecutorChannel` merely to increase thread counts. An asynchronous boundary affects consistency, ordering, error handling, and the response behavior of the API calling the flow.

## 3. ExecutorChannel Is Point-to-Point

`ExecutorChannel` uses a unicast dispatcher: each message is sent to one selected subscriber among those registered. When multiple subscribers exist, the dispatcher applies its load-balancing mechanism; the channel does not automatically broadcast the same message to all subscribers.

If the goal is to deliver the same message to every subscriber, use `PublishSubscribeChannel`. That channel has publish-subscribe semantics and can be configured with an executor for asynchronous dispatch to its subscribers.

| Requirement | Suitable channel |
|---|---|
| Send a message to one handler point-to-point | `DirectChannel` or `ExecutorChannel` |
| Offload handler execution to a worker thread | `ExecutorChannel` |
| Broadcast the same message to multiple subscribers | `PublishSubscribeChannel` |
| Buffer messages for consumers to pull later | `QueueChannel` or an appropriate `PollableChannel` |

Do not confuse `ExecutorChannel` with `QueueChannel`: the executor queue holds execution tasks, whereas a queue channel holds messages waiting for consumer polling. The two queues have different lifecycles, timeouts, and semantics.

## 4. Declaring an ExecutorChannel

You can create the channel by passing a `TaskExecutor`:

```java
@Configuration
class AsyncChannelConfiguration {

    @Bean("integrationExecutor")
    ThreadPoolTaskExecutor integrationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("si-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }

    @Bean("ordersAsyncChannel")
    MessageChannel ordersAsyncChannel(
            @Qualifier("integrationExecutor") TaskExecutor executor) {
        return new ExecutorChannel(executor);
    }
}
```

The pool in this example has 4 core workers, up to 8 max workers, and a queue capacity of 200 tasks. These are illustrative numbers; size them based on processing time, CPU, I/O, target latency, and downstream system limits.

When using `ThreadPoolTaskExecutor`, queue capacity and max pool size work together. Typically, the executor creates workers up to the core size, then queues tasks; only when the queue is full does it grow workers beyond core up to max size. When both the pool and the queue are full, the rejection policy takes effect.

## 5. Wiring the Channel into an IntegrationFlow

Example flow routing messages through an `ExecutorChannel` before invoking a service:

```java
@Bean
IntegrationFlow ordersFlow(OrderService orderService) {
    return IntegrationFlow
            .from("orders.input")
            .channel("ordersAsyncChannel")
            .handle(orderService, "process")
            .get();
}
```

Here, steps before `ordersAsyncChannel` run under the upstream execution model. Once the message is sent through this channel, dispatching to the downstream handler is delegated to the executor. The `process` handler runs on a worker thread when the task executes.

You can use `@ServiceActivator` instead of Java DSL:

```java
@ServiceActivator(inputChannel = "ordersAsyncChannel")
public void process(Order order) {
    orderService.process(order);
}
```

The channel name must point to the declared `ExecutorChannel` bean. If multiple flows share an executor, clarify which pool is responsible for each workload so one traffic type cannot starve workers needed by another.

## 6. Meaning of `send()` and Async Handoff

With `ExecutorChannel`, `send()` normally returns after the executor accepts the task. That result confirms that the dispatch was accepted according to executor/channel semantics; it does not confirm that the handler has started or that business processing has finished.

Three states must be distinguished:

1. **Message not accepted:** the executor rejects the task or the channel cannot dispatch. An error may appear immediately on the sending thread.
2. **Task accepted and queued:** the message is sitting in the executor's task queue; the handler has not run yet.
3. **Task running or completed:** a worker executes the handler; business outcomes and failures are observed via the asynchronous execution path.

Therefore, the following code does not mean `orderService.process()` has completed:

```java
boolean accepted = ordersAsyncChannel.send(message);
if (accepted) {
    log.info("Message was accepted for dispatch");
}
```

If the caller needs to know the processing outcome, design a reply, callback, job status, or correlation mechanism. Do not treat the return value of `send()` as a business acknowledgment.

## 7. Handling Overload and Rejection Policies

When the executor runs out of workers and its queue is full, new tasks are rejected according to the rejection policy. This is an important aspect of async handoff: the producer can be rejected even though the channel still exists and the message is valid.

| Policy | Behavior | Impact on `ExecutorChannel` |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException` | Producer receives an immediate overload signal at dispatch time |
| `CallerRunsPolicy` | The thread calling `execute()` runs the task if the executor is not shut down | Async handoff can degrade into synchronous execution under load; the sender blocks |
| `DiscardPolicy` | Drops the new task without reporting an error | Risk of silent message loss |
| `DiscardOldestPolicy` | Drops the oldest queued task and retries submitting the new task | Risk of losing a waiting message |

For business messages that must be preserved, do not use task-discarding policies unless data loss is explicitly acceptable. `AbortPolicy` surfaces overload, but the application must decide how to respond: return an error to the caller, perform bounded retry, throttle the producer, or route messages to durable storage.

`CallerRunsPolicy` provides natural backpressure because the sender executes the work when the pool is saturated. However, it changes the execution thread and can block an HTTP request thread or broker listener thread for a long time. Measure the impact and make sure the handler is safe to run on both sender threads and worker threads.

## 8. An Executor Queue Is Not a Durable Message Store

The task queue in `ThreadPoolTaskExecutor` normally resides in process memory. If the JVM stops abruptly, queued tasks can be lost. `ExecutorChannel` does not write messages to a database or broker on its own and provides no durable redelivery mechanism like a message broker.

If data must survive restarts, pass messages through a broker with persistence/acknowledgments or a durable persistence mechanism before crossing the async boundary. An executor is suitable for in-process scheduling and concurrency; it does not replace durable messaging infrastructure.

Queue capacity should also be bounded. An overly large queue can hold many message payloads on the heap, increasing latency and eventually causing `OutOfMemoryError`. Monitor queue depth, remaining capacity, task wait times, and rejected counts.

## 9. Processing Order and Concurrency

When an executor has multiple workers, tasks can start or finish in an order different from send order. For example, message A is sent before message B, but A's handler calls a slow API; another worker may complete B before A.

Even when the executor queue is FIFO, FIFO only governs the order in which tasks are pulled from the queue; it does not guarantee completion order when multiple workers run concurrently. Additionally, if `ExecutorChannel` has multiple subscribers, the dispatcher can distribute messages to different subscribers via load balancing.

If business logic requires ordering:

- Use a single worker for the group of messages that must be serialized, if throughput allows.
- Partition by business key so the same key goes through the same processing stream.
- Use sequence numbers and a resequencing mechanism if ordering must be restored downstream.
- Make handlers idempotent and handle late or duplicate messages.

Do not use a multi-threaded executor for strictly ordered business operations without an application-level ordering guarantee.

## 10. Exceptions and Error Channels at the Async Boundary

With `DirectChannel`, handler exceptions can return to the sender because the handler runs on the same call stack. With `ExecutorChannel`, the worker runs after the sender has already moved on. Exceptions thrown in the handler therefore cannot automatically propagate back to the thread that called `send()` and may not be caught by a `try/catch` around the send call.

Configure and test error handling for asynchronous endpoints explicitly. Spring Integration supports routing errors via an error channel; you can use the `errorChannel` header on the message or the application's default error channel depending on configuration. An error flow typically receives an `ErrorMessage` containing the exception and related message metadata.

Example of declaring an error channel to observe errors:

```java
@Bean
MessageChannel integrationErrors() {
    return new PublishSubscribeChannel();
}

@ServiceActivator(inputChannel = "integrationErrors")
public void handleError(ErrorMessage errorMessage) {
    Throwable cause = errorMessage.getPayload();
    Message<?> failedMessage = errorMessage.getOriginalMessage();
    log.error("Asynchronous message handling failed: {}", failedMessage, cause);
}
```

This snippet illustrates the structure of an error flow; actual configuration must ensure errors from the executor/endpoint are published to the right error channel. Do not assume all exceptions automatically arrive at a bean named `integrationErrors` unless that linkage is configured.

If a task is rejected by the executor before running, that is a dispatch failure on the sender path. If a handler throws an exception after a worker starts, that is an asynchronous processing failure. Both cases need distinct logging and recovery handling.

## 11. Transactions Do Not Automatically Cross the Executor Boundary

Standard Spring transactions are bound to the current thread. `DirectChannel` keeps the handler on the same thread, so the handler can join the sender's active transaction if using the same transaction manager and compatible propagation.

`ExecutorChannel` moves the handler to a worker thread. An open transaction on the sender thread does not automatically propagate to the worker. Consequently, a transaction wrapping `send()` cannot implicitly cover handler execution downstream of the channel.

If the handler needs a transaction, place the transaction boundary on the worker-side endpoint using a transaction advice or equivalent mechanism. If consistency between database updates and message publishing is required, consider outbox/inbox patterns, transactional brokers, or idempotent/retry designs.

Do not rely on `send()` returning successfully to commit a transaction under the assumption that the handler has finished. With async handoff, the sender only knows the task was accepted; the business outcome may occur later.

## 12. ThreadLocal, SecurityContext, and MDC

Thread-local state does not automatically transfer from the sender thread to the worker thread. Commonly affected data includes:

- MDC logging context, such as correlation ID and request ID.
- Thread-bound security context.
- Thread-bound transaction resources.
- Locale or custom application contexts stored in `ThreadLocal`.

Data needed for business processing should travel in the payload or message headers. If you need to propagate security context or MDC, use an appropriate context propagation mechanism such as `TaskDecorator` or a supported wrapper, and clear the context after the task finishes to prevent leakage across tasks reusing the same worker.

For example, a correlation ID should be placed in a header before sending through the channel:

```java
Message<Order> message = MessageBuilder
        .withPayload(order)
        .setHeader("correlationId", correlationId)
        .build();

ordersAsyncChannel.send(message);
```

The worker can read the correlation ID from the message for logging or correlating processing steps. Do not assume the sender thread's MDC will automatically be present on the worker.

## 13. Payloads and Thread Safety

The message envelope and headers are designed to be immutable, but the payload object does not automatically become immutable. When passing the same object through an `ExecutorChannel`, the producer and worker can hold references to that object at different times concurrently.

If the producer keeps mutating the payload after sending, the worker may observe partially updated data or hit a race condition. Use immutable DTOs, copy necessary data before the handoff, or apply proper synchronization if a payload must be mutable.

Handlers running concurrently must also be thread-safe. Avoid unsynchronized updates to shared mutable state, singleton services with unsafe mutable fields, or assuming a handler is only called by one thread at a time.

## 14. Request/Reply Over ExecutorChannel

`ExecutorChannel` can sit between a request and a handler that produces a reply. However, asynchronous dispatch does not mean the caller automatically receives a reply immediately. If using a messaging gateway, the gateway can wait for a reply on the reply channel up to a configured timeout. Meanwhile, the worker processes the request and sends the reply using correlation/reply-channel metadata.

If the caller does not need a reply, design it as fire-and-forget and provide a status-lookup or later result-retrieval mechanism. If the caller requires a synchronous result, define timeouts, reply channels, and handling for handler errors or late replies.

Do not tie up a request thread waiting for a long reply just to simulate synchronous behavior when the system could use a cleaner asynchronous API.

## 15. Interceptors and Observing the Async Handoff

Channel interceptors observe send/receive operations on a channel. With `ExecutorChannel`, callbacks around `send()` typically execute on the sender path and reflect sending/dispatching the task, not necessarily when the handler finishes on the worker.

To measure end-to-end processing, add metrics or observations at the worker-side handler/endpoint. Distinguish these milestones:

1. When the producer sends the message.
2. When the executor accepts the task.
3. When the worker begins processing.
4. When the handler completes or fails.

Useful metrics include queue wait time, active workers, queue depth, rejected tasks, handler duration, error count, and p95/p99 end-to-end latency. Use message ID/correlation ID to link sender and worker logs.

## 16. Shutdown and Executor Lifecycle

An executor is managed by the application context if declared as a bean. When the context closes, Spring performs shutdown according to `ThreadPoolTaskExecutor` configuration.

Properties to review carefully:

| Property | Meaning |
|---|---|
| `waitForTasksToCompleteOnShutdown` | Waits for accepted tasks to finish according to shutdown policy |
| `awaitTerminationSeconds` | Maximum time to wait for the executor to terminate |
| `threadNamePrefix` | Helps identify workers in logs and thread dumps |
| Queue capacity | Limits how many tasks wait in the executor before rejecting or applying policy |

Orderly shutdown requires stopping new message intake, waiting for or handling in-flight tasks, and then releasing the executor. If the timeout expires, know whether queued tasks are canceled or still run depending on policy and version. For dynamic flows, stop/destroy endpoints before closing any flow-owned executor. Do not shut down a shared executor while other flows still depend on it.

## 17. Troubleshooting ExecutorChannel Issues

| Symptom | Possible cause | Where to check |
|---|---|---|
| `send()` returns but handler has not run | Task is waiting in the executor queue | Queue depth, active workers, task wait time |
| `send()` fails immediately with an exception | Executor rejected the task or channel could not dispatch | Rejected count, max pool, queue capacity, executor shutdown |
| Handler fails but sender receives no exception | Error occurred on the worker thread | Error channel, error handler, worker logs |
| Messages complete out of order | Multiple workers or multiple subscribers | Executor concurrency, dispatcher load balancing, sequence key |
| Latency rises even with low CPU | Workers waiting on I/O or high queue wait | Thread dump, downstream latency, queue depth |
| Messages lost on restart | Task queue is in-memory only | Durable broker/store and shutdown policy |
| Sender unexpectedly blocks | `CallerRunsPolicy` or synchronous execution at another boundary | Rejection policy, channel topology, thread name |
| Context shuts down slowly | Worker task is blocked or executor waits too long | Await termination, I/O timeouts, thread dump |

When investigating, separate dispatch failures from handler failures. Check whether the executor is still accepting tasks, whether workers are picking them up, whether handlers have started, and whether the error flow receives failures. Looking only at producer-side logs is usually insufficient to see what happens after an async handoff.

## 18. Guidelines for Using ExecutorChannel

- **Choose it only when an async boundary is genuinely needed:** ensure callers do not expect handler completion upon return.
- **Use a bounded executor:** configure core/max size, queue capacity, and rejection policy for expected load.
- **Do not confuse queues:** executor queues hold tasks; `QueueChannel` holds messages.
- **Verify dispatch semantics:** `ExecutorChannel` is point-to-point; use `PublishSubscribeChannel` when broadcast is needed.
- **Design error flows:** separate task-rejection failures on the sender path from handler failures on the worker path.
- **Place transactions on the right thread:** sender transactions do not automatically extend to workers.
- **Propagate context deliberately:** use payload/headers for business data and wrappers/`TaskDecorator` for thread-bound context.
- **Protect ordering and payloads:** use immutable payloads, thread-safe handlers, and partitioning/resequencing if ordering is required.
- **Observe both sides:** measure dispatch acceptance, queue wait, handler completion, and rejected tasks.
- **Manage shutdown:** stop producers/endpoints, drain or handle in-flight tasks, then shut down the executor by its proper owner.

Before placing an `ExecutorChannel` in a flow, clarify what the caller needs to know when `send()` returns, how large the task queue is bounded, where worker errors go, which transaction applies to the handler, and whether message ordering matters. These answers define the async handoff contract and keep the channel stable under increased load or downstream failures.
