# Managing Threads, Executors, and CompletableFuture in Functions

Java functions in serverless environments typically handle an invocation within a bounded time limit and return a result to the platform. During processing, a function may call multiple services, read from a database, transform data, or run independent tasks. Using multiple threads and CompletableFuture can lower wait times by executing I/O operations concurrently, but also increases complexity around state, timeouts, error handling, and resource limits.

A function is not a continuously running server application. Execution environments can be reused, frozen, or reclaimed; a new invocation may land in a different environment. A thread pool created inside an environment can persist across invocations on that specific environment, yet is never shared globally across all instances and is not a place for durable state.

Concurrency design must guarantee that all request work completes or is durably handed off before the handler exits. Never rely on background threads to finish business logic after returning a response or acknowledging a message. Bound the number of threads, active tasks, and downstream connections so scaling the function does not overwhelm backend systems.

## 1. Why manage concurrency in serverless?

A function may execute multiple steps:

- Validating the request and access permissions.
- Reading user information from a database.
- Calling a payment API or external service.
- Fetching multiple independent resources.
- Transforming data and writing results.
- Emitting events or updating job status.

If independent calls execute sequentially, total wait time approaches the sum of each dependency's latency. With bounded parallelism, wait time approaches the slowest call plus coordination overhead.

For example, an API needs 120 ms to fetch a profile, 250 ms to fetch order history, and 180 ms to fetch loyalty points. Run sequentially, network wait time is roughly 550 ms. When the three independent calls run concurrently, wait time drops toward 250 ms, excluding coordination overhead and system load.

Parallelism does not make work disappear. It consumes additional threads, memory, connections, and capacity at target services. If each function opens 10 concurrent calls and the platform scales to 100 execution environments, downstream systems can receive up to roughly 1,000 concurrent calls. Optimizing single-invocation latency must therefore go hand in hand with system-wide load limits.

## 2. Invocation concurrency vs. thread concurrency

There are two concurrency layers:

- **Invocation concurrency:** the number of function invocations handled simultaneously by the platform across execution environments.
- **Thread concurrency:** the number of concurrent tasks running inside a single execution environment.

These two layers multiply when calculating load. If the platform processes 50 concurrent invocations and each spawns 8 I/O tasks, a dependency may face up to 400 queued or active operations depending on scheduling and connection pools.

Never assume every platform or runtime runs invocations the same way. Some models allocate a separate environment per concurrent invocation; some runtimes or frameworks allow multiple requests per process; event source mappings may deliver batches to a function. Read your runtime's concurrency contract and write thread-safe code whenever objects are shared.

Distinguish the following concepts:

| Concept | Scope | Example |
|---|---|---|
| Invocation | A single function call | Handling one HTTP request |
| Execution environment | Platform-provisioned runtime/process | One JVM with initialized dependencies |
| Thread | Execution flow inside the process | Handler thread or worker thread |
| Executor | Task scheduling and management mechanism | ThreadPoolExecutor |
| Future | Handle representing a result available later | CompletableFuture for an API call |
| Connection pool | Limits and reuses connections | JDBC pool or HTTP connection pool |

A static thread pool in a class can be reused while the environment remains alive. It is not shared across separate environments. During scale-out, each environment creates its own pool; total threads and connections therefore scale with the number of environments.

## 3. Thread lifecycle in an execution environment

Application-created threads live inside the runtime process. When an invocation completes, the handler thread may return to waiting; executor worker threads can remain alive. If the environment is reused, those threads and shared objects may still be present.

Some platforms freeze the environment between invocations and resume it later. While frozen, unfinished worker threads or callbacks cannot make progress like an always-on service. The platform can also reclaim an environment without giving the application sufficient time for cleanup.

Therefore:

1. Never return a response while mandatory tasks are still running.
2. Never rely on background threads to complete side effects after the handler returns.
3. Never use threads to maintain timers or precisely timed scheduled work.
4. Never rely on shutdown hooks to commit business data.
5. Never assume threads will resume immediately when an environment unfreezes.
6. Offload long-running or independent work to durable queues, workflows, or schedulers.

A safe execution flow:

~~~mermaid
flowchart TD
    A["Invocation starts"] --> B["Create bounded tasks"]
    B --> C["Await required tasks"]
    C --> D{"All results valid?"}
    D -->|"Yes"| E["Persist results durably"]
    E --> F["Return response or ack"]
    D -->|"No"| G["Best-effort cancel / handle error"]
    G --> H["Ensure no uncontrolled background side effects remain"]
    H --> I["Return error or let trigger retry"]
~~~

If work must continue after an HTTP response is returned, persist job state and enqueue a message before returning 202 Accepted. An independent worker processes the job and updates state. Never spawn a thread and hope the runtime keeps the process alive.

## 4. Choosing appropriate tasks to run in parallel

Parallelism works best when tasks are independent and waiting accounts for most of total latency—for example, calling two read APIs, fetching independent resources, or downloading multiple objects.

Do not parallelize a chain with data dependencies. If step B requires step A's output, use composition or run sequentially. Spawning many threads for small CPU-bound tasks can also degrade performance due to context switching and CPU contention.

| Workload type | Typically suitable strategy |
|---|---|
| I/O-bound: HTTP calls, databases, object storage | Small bounded thread pool or non-blocking async client |
| CPU-bound: encryption, compression, computation | Size workers to allocated CPUs and invocation budget |
| Tasks depending on prior results | Chain with thenCompose or run sequentially |
| Independent tasks all required | Run with bounded parallelism then await allOf |
| Tasks exceeding invocation limits | Durable queue or workflow |
| Optional, skippable tasks | Dedicated timeout and explicit fallback |

Before introducing concurrency, determine which tasks are truly independent, which outputs are mandatory vs. optional, and whether a single branch failure fails the entire request or permits partial results.

## 5. Executors and why arbitrary thread creation is dangerous

An Executor manages how tasks are queued and executed on threads. Spawning a new thread per call can cause unbounded thread growth during traffic spikes or dependency slowdowns.

Example to avoid:

~~~java
new Thread(() -> paymentClient.call()).start();
~~~

This snippet creates a thread with no count limit, no way to track results, no explicit deadline, and no guarantee the work finishes before the invocation ends.

Similarly, a cached thread pool can spawn excessive threads when work arrives faster than it completes. In serverless, scale-out already multiplies execution environments; an unbounded pool inside each environment can amplify load unexpectedly.

Prefer an executor with:

- An explicit maximum worker count.
- A bounded queue capacity.
- Descriptive thread names for logs and thread dumps.
- A rejection policy under overload.
- Timeouts on tasks and dependencies.
- Metrics for queue depth, active count, and rejected tasks.
- Thread-safe dependencies or per-task instances.

### Bounded ThreadPoolExecutor example

~~~java
private static final AtomicInteger THREAD_SEQUENCE =
        new AtomicInteger();

private static final ThreadFactory WORKER_FACTORY = task -> {
    Thread thread = new Thread(
            task,
            "function-io-" + THREAD_SEQUENCE.incrementAndGet()
    );
    thread.setDaemon(true);
    return thread;
};

private static final ThreadPoolExecutor IO_EXECUTOR =
        new ThreadPoolExecutor(
                4,
                4,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(32),
                WORKER_FACTORY,
                new ThreadPoolExecutor.AbortPolicy()
        );
~~~

This example creates a pool with at most 4 workers and a queue of 32 tasks per execution environment. When the queue is full and all workers are busy, AbortPolicy throws RejectedExecutionException so the application can return an overload error or apply a fallback.

The numbers 4 and 32 are illustrative only. Tune them based on memory, CPU, invocation duration, dependency latency, maximum environments, and downstream limits. One pool per environment multiplies during scale-out; never look only at one JVM's thread count.

Never use an unbounded queue. When a dependency slows down, an unbounded queue accumulates tasks, pins request contexts and payloads in memory, raises latency, and risks out-of-memory failures. Apply backpressure before accepting excessive work.

### Choosing a rejection policy

- **AbortPolicy:** rejects new tasks with an exception; suited when callers need an explicit overload signal.
- **CallerRunsPolicy:** the submitting thread executes the task when the pool is full; creates backpressure but can block the handler thread past its deadline.
- **DiscardPolicy:** silently drops tasks without errors; dangerous for important work.
- **DiscardOldestPolicy:** drops the oldest queued task; suitable only for workloads where newer data supersedes older entries.

For business side effects, never silently discard tasks. Choose explicit behavior, record rejections, and return an appropriate response. If work cannot run during the invocation, persist it to a durable queue.

## 6. Reusing executors across invocations

You can initialize a shared executor per execution environment to avoid creating and destroying pools on every invocation. This lowers overhead and reuses worker threads.

However, a shared executor outlives individual requests. Every task must be self-contained with its invocation data and must never read a mutable field holding the current request. Never store user ID, tenant, authorization context, or invocation payloads in static variables for workers to read later.

Guidelines:

- Create the executor after verifying runtime and concurrency needs.
- Keep the pool bounded; do not expand it indefinitely when queues fill up.
- Do not call shutdown on a shared executor at the end of every invocation.
- Do not use the executor to hold work after the handler returns.
- Never allow stale tasks to leak context or data into the next invocation.
- Monitor stuck pools, full queues, and overly long tasks.
- Reuse only clients or dependencies with a thread-safe contract.

Daemon threads prevent workers from blocking process exit in some situations, yet do not guarantee task completion. Daemon threads can still be frozen or terminated when an environment is reclaimed. Always await required tasks before returning.

If using a per-invocation executor, shut it down and await completion within the remaining time budget. That adds thread creation cost in exchange for strict ownership boundaries. Whether using a shared or per-invocation pool, bound concurrency and never let tasks outlive their business scope.

## 7. CompletableFuture and asynchronous composition

CompletableFuture represents a result that may complete in the future. It supports chaining steps, combining results, and handling exceptions without manual callback management.

Common methods:

| Method | Meaning |
|---|---|
| supplyAsync | Runs a value-returning task asynchronously |
| runAsync | Runs a void task asynchronously |
| thenApply | Transforms the result synchronously when the future completes |
| thenApplyAsync | Transforms the result on an executor |
| thenCompose | Chains another async step and flattens nested futures |
| thenCombine | Combines results of two independent futures |
| allOf | Waits for all futures to complete |
| anyOf | Completes when any one future completes |
| exceptionally | Produces a fallback result on error |
| handle | Processes both normal result and error |
| whenComplete | Observes result/error without intending to replace it |
| orTimeout | Completes the future with TimeoutException after a deadline |
| completeOnTimeout | Completes the future with a default value after a deadline |

Important note: `*Async` methods without an explicit executor default to `ForkJoinPool.commonPool()`. That can be unsuitable for blocking I/O or a function's thread budget. For blocking work, pass a bounded executor or use a non-blocking async client.

### Calling two dependencies in parallel

~~~java
CompletableFuture<Profile> profileFuture =
        CompletableFuture.supplyAsync(
                () -> profileClient.fetch(userId),
                IO_EXECUTOR
        );

CompletableFuture<List<Order>> ordersFuture =
        CompletableFuture.supplyAsync(
                () -> orderClient.fetchRecent(userId),
                IO_EXECUTOR
        );

CompletableFuture<Void> combined =
        CompletableFuture.allOf(profileFuture, ordersFuture);

combined.join();

Profile profile = profileFuture.join();
List<Order> orders = ordersFuture.join();

return new Dashboard(profile, orders);
~~~

Both calls start independently on IO_EXECUTOR. allOf completes when both futures finish. If either fails, combined also completes exceptionally, and join throws CompletionException. Handle errors at the handler boundary and map them to the right response or trigger retry behavior.

Never call join immediately after creating one future before starting the next; doing so accidentally serializes the work. Launch all independent futures first, then wait on their combined completion.

## 8. Chaining and combining results properly

Use thenApply when the next step simply transforms an already-available value:

~~~java
CompletableFuture<String> displayName =
        profileFuture.thenApply(Profile::displayName);
~~~

Use thenCompose when the next step itself returns a CompletableFuture:

~~~java
CompletableFuture<List<Order>> orders =
        profileFuture.thenCompose(profile ->
                orderClient.fetchRecentAsync(profile.userId())
        );
~~~

Using thenApply with a function returning a CompletableFuture yields CompletableFuture<CompletableFuture<T>>. thenCompose flattens that nesting.

Use thenCombine when two futures are independent and their results must be combined:

~~~java
CompletableFuture<Dashboard> dashboard =
        profileFuture.thenCombine(
                ordersFuture,
                Dashboard::new
        );
~~~

Use allOf when you have multiple futures and must wait for all of them. allOf returns CompletableFuture<Void> rather than collecting values into a list. Keep references to each individual future to read their results once allOf finishes.

Use anyOf when you only need the first completed result, such as querying two replicas or a fallback endpoint. However, plan how to cancel remaining tasks so redundant work does not keep consuming resources. Completing the first future does not automatically stop the others.

## 9. Handling exceptions and partial results

Exceptions inside a CompletableFuture pipeline are typically wrapped in CompletionException or ExecutionException depending on how you await them. Unwrap the cause at the handling boundary to classify the actual failure.

~~~java
try {
    return future.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();

    if (cause instanceof DependencyUnavailableException) {
        throw new RetryableFunctionException(cause);
    }

    if (cause instanceof ValidationException) {
        throw new InvalidRequestException(cause);
    }

    throw new FunctionExecutionException(cause);
}
~~~

Never turn every exception into a default value if that makes a response appear successful while required data is missing. For optional data, you can use exceptionally or handle to supply a fallback, but record that degradation occurred.

Example of a dashboard where the profile is required while recommendations are optional:

~~~java
CompletableFuture<Profile> profileFuture =
        CompletableFuture.supplyAsync(
                () -> profileClient.fetch(userId),
                IO_EXECUTOR
        );

CompletableFuture<List<Recommendation>> recommendationsFuture =
        CompletableFuture.supplyAsync(
                () -> recommendationClient.fetch(userId),
                IO_EXECUTOR
        ).exceptionally(error -> List.of());

return profileFuture.thenCombine(
        recommendationsFuture,
        Dashboard::new
);
~~~

In this example, a recommendation error yields an empty list, whereas a profile error fails the entire operation. Apply fallbacks only when business semantics permit and indicate partial data in the response when necessary.

With message triggers, never swallow exceptions if the runtime relies on exceptions to trigger retries. If part of a batch already committed, use partial batch acknowledgment or idempotency so retries do not duplicate completed side effects.

## 10. Timeouts, deadlines, and cancellation

Serverless invocations have a hard maximum duration. Waiting on futures must fit within the remaining invocation budget, leaving room to persist results, build the response, and clean up.

A request may have a 3-second total deadline. If 1 second was already spent at the gateway and validation, only ~2 seconds remain for concurrent dependency calls. Do not give every dependency a 3-second timeout and expect the entire request to finish in 3 seconds.

Distinguish these terms:

- **Invocation timeout:** platform limit on how long the handler can run.
- **Request deadline:** point after which the caller stops waiting.
- **Dependency timeout:** maximum time waiting on an API or database.
- **Future timeout:** time spent waiting for a future to complete.
- **Cancellation:** signaling a task to stop; does not always halt underlying I/O calls.

Example:

~~~java
CompletableFuture<Profile> profileFuture =
        CompletableFuture.supplyAsync(
                () -> profileClient.fetchWithTimeout(userId, Duration.ofMillis(900)),
                IO_EXECUTOR
        );

CompletableFuture<List<Order>> ordersFuture =
        CompletableFuture.supplyAsync(
                () -> orderClient.fetchWithTimeout(userId, Duration.ofMillis(1200)),
                IO_EXECUTOR
        );

try {
    CompletableFuture.allOf(profileFuture, ordersFuture)
            .orTimeout(1500, TimeUnit.MILLISECONDS)
            .join();
} catch (CompletionException ex) {
    profileFuture.cancel(true);
    ordersFuture.cancel(true);
    throw ex;
}
~~~

This example illustrates an overall timeout and best-effort cancellation. orTimeout completes the future exceptionally after the deadline; it does not guarantee underlying sockets, JDBC queries, or blocking tasks stop automatically. Calling cancel(true) on a CompletableFuture also does not guarantee the executing thread is interrupted. Configure timeouts directly on HTTP clients, JDBC drivers, and dependency SDKs; use cancellation-aware APIs when needed.

Never return a response and leave futures running in the background. When a dependency cannot stop quickly, enforce connection limits, client-side deadlines, and idempotency so stray tasks cannot cause out-of-scope side effects.

## 11. Context propagation: tracing, logging, and security

New threads do not automatically inherit the calling thread's context. Data commonly held in ThreadLocal includes:

- Logging MDC.
- Trace/span context.
- Security principal or tenant context.
- Locale or request-scoped metadata.
- Framework contexts.

When switching to an executor, ThreadLocal values may be absent or contain stale values from a prior task if not cleaned properly. Never assume MDC or security context propagates automatically across every executor.

The safe approach is passing required context explicitly in parameters or using your framework/telemetry SDK's context-propagation utilities. When wrapping tasks to copy MDC, always restore or clear context inside finally:

~~~java
Map<String, String> capturedContext = MDC.getCopyOfContextMap();

Runnable task = () -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (capturedContext == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(capturedContext);
        }

        performWork();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
};

IO_EXECUTOR.execute(task);
~~~

This example uses SLF4J/Logback MDC; adapt it to your logging framework. For security context, never casually copy mutable objects or long-lived tokens across threads. Pass only the verified identity and minimal permissions required for the task, and enforce authorization where data operations occur.

## 12. Thread safety, shared state, and ThreadLocal

A shared executor means multiple tasks may access the same dependency concurrently. Verify whether each library is thread-safe. If a mapper or client is not thread-safe, instantiate it per task or synchronize access properly.

Never store invocation data in mutable static variables:

~~~java
private static String currentTenantId;
private static RequestContext currentContext;
~~~

Concurrent tasks can overwrite these values, and the environment can be reused across different requests. Use immutable local variables and pass context explicitly.

ThreadLocal can help libraries requiring per-thread context, yet thread pools reuse worker threads. Failing to clear ThreadLocal in a finally block leaks data from one task into subsequent tasks. This is especially dangerous for tenant IDs, user identities, tokens, and personal data.

Guidelines:

- Prefer immutable values and local variables.
- Never share mutable collections without synchronization.
- Use concurrent collections when sharing is genuinely required.
- Clear ThreadLocal and MDC after every task.
- Never infer user or tenant identity from thread identity.
- Verify thread safety of SDKs and connection pools.
- Never retain request objects inside futures beyond the invocation lifecycle.

## 13. Bounding dependencies with semaphores and connection pools

Limiting executor threads does not necessarily bound requests hitting a dependency. One worker can issue multiple parallel calls, or multiple executors and functions can target the same backend.

A Semaphore can cap concurrent operations within a single environment:

~~~java
private static final Semaphore PAYMENT_LIMIT =
        new Semaphore(3);

public PaymentResult charge(PaymentRequest request) {
    boolean acquired = false;

    try {
        acquired = PAYMENT_LIMIT.tryAcquire(
                200,
                TimeUnit.MILLISECONDS
        );

        if (!acquired) {
            throw new DependencyOverloadedException();
        }

        return paymentClient.charge(request);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new RetryableFunctionException(ex);
    } finally {
        if (acquired) {
            PAYMENT_LIMIT.release();
        }
    }
}
~~~

This semaphore bounds concurrency only within one JVM/execution environment. With 40 environments each allowing 3 concurrent calls, system-wide concurrency can still reach 120. Global limits require dependency quotas, API gateways, distributed rate limiters, or function concurrency caps.

Connection pools must also be sized against maximum environments. If each environment opens 5 database connections and the platform scales to 100 environments, the database may face 500 connections. Size pools from the total connection budget and database capacity, not from a single invocation.

When a dependency is overloaded, return a retryable error with backoff, offload work to a queue, or throttle concurrency. Never retry immediately across multiple threads, which triggers retry storms.

## 14. CPU-bound, blocking I/O, and virtual threads

Thread pools must match the workload type.

### CPU-bound

For CPU-bound computation, worker count should generally align with the CPUs allocated to the environment. Adding excessive threads does not speed up the CPU; it increases context switching and resource contention. Platform memory or CPU allocation settings directly affect throughput.

### Blocking I/O

With blocking I/O, a thread remains occupied while waiting on network or database responses. A thread pool increases concurrent calls, though it must be bounded by dependency capacity and deadlines. When clients offer async/non-blocking APIs, you can avoid tying up worker threads while waiting.

### Virtual threads

Java 21 introduced virtual threads to make blocking-style code scale more easily for many I/O-bound workloads. Virtual threads are lighter than platform threads, yet they do not make databases, partner APIs, CPUs, or socket limits infinite.

When using virtual threads:

- Verify your serverless runtime and framework support that Java version.
- Still bound concurrency to dependencies using semaphores, connection pools, or quotas.
- Configure timeouts on clients and databases.
- Measure memory, throughput, and latency in the real environment.
- Avoid holding locks across long blocking operations where pinning affects your runtime.
- Never spawn millions of tasks without backpressure.

Virtual threads help manage many blocking tasks, but do not replace durable queues for work that must continue past an invocation.

## 15. Retries and CompletableFuture

Asynchronous retries require bounds and error classification. Never retry every exception; validation errors, permission denials, or invalid business states rarely self-heal. Timeouts or throttling can be retried, provided you apply backoff, jitter, and an overall deadline.

When retrying with CompletableFuture, avoid creating unbounded future chains. Every attempt must fit inside the time budget, and retrying side effects requires a stable idempotency key.

A simple design:

~~~java
CompletableFuture<Inventory> loadInventory(String productId) {
    return CompletableFuture.supplyAsync(
            () -> inventoryClient.fetch(productId),
            IO_EXECUTOR
    ).exceptionallyCompose(error -> {
        Throwable cause = unwrap(error);

        if (cause instanceof RetryableDependencyException) {
            return delayedRetry(productId, Duration.ofMillis(200));
        }

        return CompletableFuture.failedFuture(cause);
    });
}
~~~

This conceptual example uses exceptionallyCompose (Java 12+). The delayedRetry helper must enforce max attempts, an overall deadline, and a managed scheduler; never call Thread.sleep on a worker thread because it blocks the thread. If your runtime or Java version lacks this API, implement retries with handle/thenCompose or a retry library with explicit policies.

For message triggers, let the broker manage retries where appropriate instead of performing lengthy retries inside one invocation. Retrying repeatedly inside a function consumes invocation time and can expire visibility timeouts. When failing back to the broker for retry, ensure side effects are idempotent.

## 16. Batches and parallel message processing

Batch triggers can deliver multiple messages in one invocation. Processing messages in parallel boosts throughput, provided you bound task counts and understand partial batch acknowledgment.

Never submit an entire batch into an unbounded executor. If a batch holds 500 messages and the pool has 4 workers, the queue must have capacity and batch execution must fit within the function timeout. If one message fails, determine whether succeeded messages already committed before returning the batch response.

A typical processing pattern:

1. Validate the envelope and event ID for each message.
2. Submit at most the permitted number of concurrent tasks.
3. Have each task execute idempotently and commit results durably.
4. Collect successes and failures keyed by message ID.
5. Report partial failures per the event source mapping contract, or throw to retry the batch.
6. Ensure no background tasks continue causing side effects after the invocation returns.

If the broker does not support partial acknowledgment, already-succeeded messages may be redelivered when one message in the batch fails. Per-message idempotency is mandatory to avoid duplicate processing.

## 17. Measuring and diagnosing concurrency

Measuring total handler duration alone is insufficient. You need visibility into where time goes and whether executors are saturating.

Useful metrics:

- Invocation count, concurrency, and timeouts.
- Active threads and total threads per environment.
- Executor queue depth, active count, and rejected task count.
- Queue wait time and execution duration per task.
- CompletableFuture successes, failures, timeouts, and cancellations.
- Dependency latency, error rates, and connection pool utilization.
- Semaphore acquire wait times and rejections.
- Batch size, partial failures, and message age.
- End-to-end request p50, p95, and p99 latency.
- Memory, CPU, and cold start duration.

Logs must carry correlation IDs or trace context across tasks. Record task name, dependency, queue wait time, execution time, and outcome. Never log tokens, secrets, sensitive payloads, or entire context objects.

If latency rises while CPU remains low, pools may be waiting on dependencies or connection pools may be exhausted. If CPU spikes and queues grow, CPU-bound tasks may be excessive or worker sizing may be misaligned. If rejected tasks climb, shed load, scale capacity carefully, or offload work to a queue.

## 18. Checklist for threads and CompletableFuture design

Before deploying, verify:

1. Which tasks are genuinely independent and benefit from parallel execution?
2. Does the runtime support the assumed thread and invocation concurrency model?
3. Does the executor have bounded worker counts and bounded queue capacity?
4. Is total thread count calculated against maximum execution environments?
5. Does the rejection policy surface overload rather than silently dropping critical tasks?
6. Does CompletableFuture pass an explicit executor for blocking I/O?
7. Are allOf, thenCompose, and thenCombine used according to true dependency relationships?
8. Are exceptions unwrapped and classified properly?
9. Does the overall timeout fit within the invocation deadline?
10. Do HTTP clients, JDBC drivers, and SDKs have their own timeouts?
11. Does cancellation actually stop I/O or only complete the future?
12. Does the handler await all required work before returning a response or ack?
13. Are trace context, MDC, and security context propagated and cleared properly?
14. Are shared clients and any mutable state thread-safe?
15. Do connection pools, semaphores, and concurrency caps protect downstream services?
16. Do retries enforce limits, backoff, jitter, and idempotency?
17. Are partial batch failures and duplicate deliveries handled safely?
18. Are metrics collected for queue depth, rejected tasks, task latency, and dependency saturation?

## Conclusion

Threads and CompletableFuture can lower Java function latency when multiple I/O tasks are independent, but concurrency must be bounded to match execution environment resources and downstream capacity. Executors with finite worker counts and queue capacities control load; CompletableFuture chains steps, combines results, and handles errors; timeouts and cancellation must be enforced on both futures and underlying I/O clients.

In serverless environments, thread pools can be reused while an environment remains alive, yet are never durable task queues. Complete or durably hand off all work before returning from the handler, propagate context explicitly, keep state thread-safe, cap connections, and monitor concurrency at both invocation and thread levels. For work that must continue past an invocation, use durable queues or workflows rather than background threads.
