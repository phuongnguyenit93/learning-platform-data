# Processor timeout

In Spring Batch, `ItemProcessor` processes each item between the reader and the writer. The processor may normalize data, validate business rules, call repositories, or query an external service to supplement information. If a processing call hangs or takes too long, worker threads can be tied up, chunk transactions prolonged, connections held open, and the entire job slowed down or prevented from completing.

Spring Batch does not provide a universal timeout property on the `ItemProcessor` interface to automatically abort any `process(item)` call after a number of seconds. Timeouts must be designed where blocking work happens: HTTP clients, JDBC statements, databases, message clients, or a controlled deadline/wrapper. Chunk transaction timeout is a separate mechanism and is not guaranteed to interrupt arbitrary Java code running inside a processor.

A sound timeout design explicitly defines time limits, work cancellation, raised exceptions, retry/skip policies, and safe repeatability. This lesson explains how to apply those principles to processors in Spring Batch.

## 1. What is a processor timeout?

A timeout is the time limit an operation is allowed to wait or execute before the application considers it failed. Inside a processor, time can be spent in many places:

- CPU processing or data computation.
- Waiting for an HTTP connection or response from an external service.
- Waiting for a database connection or query result.
- Waiting on a lock, semaphore, queue, or thread pool.
- Reading data from object storage or a message broker.
- Waiting for an asynchronous future/task to complete.

Not all cases use the same type of timeout. Connect timeout bounds connection establishment; response/read timeout bounds waiting for data; total request timeout bounds an entire request. Queue timeout bounds waiting for a worker. An end-to-end deadline bounds total time across the entire item processing flow.

A processor may finish quickly under normal conditions yet hang when a dependent service fails. Therefore, timeouts are part of the operational contract, not merely a performance optimization.

## 2. Where the processor sits in a chunk step

The processor is invoked during the per-item processing phase of a chunk. A chunk typically contains multiple items; if one processor invocation waits too long, the worker cannot finish the chunk until that call returns or throws an exception.

~~~mermaid
flowchart LR
    A[ItemReader] --> B[ItemProcessor]
    B --> C[ItemWriter]
    C --> D[Commit chunk]
    B -.-> E[HTTP / JDBC / Service]
    E -. timeout .-> F[ProcessorTimeoutException]
    F --> G[Retry / Skip / Fail policy]
~~~

For example, with a chunk size of 100, if the processor handles 99 items in a few milliseconds but the 100th item waits 90 seconds on an API, the chunk cannot proceed to writer/commit. A bounded timeout allows the job to free the worker and handle the error per configured policy.

Timeouts should be placed as close as possible to the potentially blocking operation. If the processor makes HTTP calls, configure the HTTP client's timeouts. If the processor runs JDBC queries, configure query/statement timeouts. If the processor waits on another task, bound the wait duration and define how to cancel the task.

## 3. No universal timeout on ItemProcessor

The core Spring Batch contract:

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

The interface takes no timeout parameter and provides no callback for the framework to forcibly terminate the method after a duration. Hence, something like `processor.setTimeout(...)` is not a standard `ItemProcessor` API.

If `process` enters an infinite CPU loop, calls a library with no timeout, or blocks indefinitely on I/O, Spring Batch does not automatically know how to interrupt it. The step may keep waiting until the operation returns, the thread is interrupted and cooperative code stops, or the process is terminated.

Avoid confusing a single dependency's timeout with the whole processor's timeout. A processor might call three services, each with a 5-second timeout; total runtime can still exceed 5 seconds. If total time must be bounded, pass a deadline across steps and have each dependency honor remaining time.

## 4. Distinguishing timeout types

| Timeout type | Bounds | Example |
|---|---|---|
| Connection timeout | Time to establish a connection | HTTP connect or acquiring a connection from a pool |
| Response/read timeout | Time waiting for a response or next bytes | HTTP response, socket read |
| Request/call timeout | Total time for a single request | One complete HTTP request |
| Query/statement timeout | Time the database executes a statement | JDBC query |
| Pool/queue timeout | Time waiting for a resource or worker | Connection pool, bulkhead, executor queue |
| Processor deadline | Total time for item processing logic | Multiple service calls within one `process` invocation |
| Transaction timeout | Duration a transaction is allowed to remain open | Chunk transaction |
| Job/step operational limit | Execution runtime operational threshold | Alerting or stopping a job per governance workflow |

These timeouts do not substitute for one another. For instance, a connection timeout does not bound how long a server processes a request after connecting. A transaction timeout is not a reliable mechanism to interrupt a blocking REST call.

## 5. Setting timeouts directly on the HTTP client

This is usually the most effective approach when a processor calls REST services. Configure timeouts on the client so the I/O operation terminates with an exception when the limit is exceeded.

With Java HTTP Client:

~~~java
@Bean
HttpClient customerHttpClient() {
    return HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();
}
~~~

When creating a request, set the request timeout:

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create(customerUrl))
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Synchronous invocation:

~~~java
HttpResponse<String> response =
        httpClient.send(request, HttpResponse.BodyHandlers.ofString());
~~~

In this example, connect timeout bounds connection setup; request timeout bounds waiting for the request to complete per Java HTTP Client semantics. Choose values based on service SLAs and the job's time budget.

Do not set overly large timeouts just to avoid errors. When a service hangs, long waits tie up workers and can build up backlogs. Also avoid setting timeouts too short, causing normal requests to fail under high system load.

## 6. Translating HTTP timeouts into business exceptions

A processor should not depend on every HTTP library exception detail. You can wrap timeout errors into a dedicated exception so the step can clearly configure retry/skip:

~~~java
public class ProcessorTimeoutException extends RuntimeException {
    public ProcessorTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Service calling the API:

~~~java
public class CustomerApiClient {

    private final HttpClient httpClient;
    private final URI customerUri;

    public CustomerApiClient(HttpClient httpClient, URI customerUri) {
        this.httpClient = httpClient;
        this.customerUri = customerUri;
    }

    public CustomerDetails fetch(String customerId) {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(customerUri.resolve("/customers/" + customerId))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        try {
            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() / 100 != 2) {
                throw new CustomerServiceException(
                        "Customer service returned HTTP "
                                + response.statusCode());
            }
            return parseCustomer(response.body());
        } catch (HttpTimeoutException ex) {
            throw new ProcessorTimeoutException(
                    "Timed out fetching customer " + customerId, ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new CustomerServiceInterruptedException(
                    "Interrupted while fetching customer " + customerId, ex);
        } catch (IOException ex) {
            throw new CustomerServiceException(
                    "Could not fetch customer " + customerId, ex);
        }
    }
}
~~~

This is an illustrative example; applications need to add JSON parsing, status code checks, and response body handling per the actual API. The key point is distinguishing timeouts from business HTTP errors and thread interruptions. Upon receiving `InterruptedException`, restore the interrupt flag and do not turn it into a normal retryable error if thread stopping was intentional.

Do not include tokens, authorization headers, or full sensitive payloads in exception messages. Log correlation IDs and business keys at appropriate levels for investigation.

## 7. Setting timeouts for JDBC queries

If the processor queries a database, configure query timeouts at the JDBC layer. Example with `JdbcTemplate`:

~~~java
@Bean
JdbcTemplate reportingJdbcTemplate(DataSource dataSource) {
    JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
    jdbcTemplate.setQueryTimeout(10);
    return jdbcTemplate;
}
~~~

The value above is the maximum number of seconds a JDBC statement is allowed to execute, subject to driver/database support. Drivers may implement timeouts differently; verify target database behavior and test with genuinely slow queries.

For queries needing different timeouts, configure separate templates or use JDBC APIs to set query timeouts on specific statements. Avoid mutating the timeout property of a singleton `JdbcTemplate` per item because multiple workers may share the bean concurrently.

A JDBC client-side timeout also does not always guarantee the server stopped immediately. On timeout, the driver may send a cancel request or close the statement/connection depending on implementation. Monitor database sessions and query execution to verify.

## 8. Transaction timeout is not a processor timeout

A chunk step typically executes read/process/write inside a step-managed transaction. A transaction attribute with a timeout can be configured:

~~~java
DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();
transactionAttribute.setTimeout(45);

return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .transactionAttribute(transactionAttribute)
        .build();
~~~

Transaction timeout helps the transaction manager/database enforce a time limit on the transaction or supporting resource operations. Exact effects depend on the transaction manager and resources. It does not forcibly abort a CPU loop, an HTTP call lacking a timeout, or a blocking library that ignores interrupts.

If the processor calls an API while the chunk transaction is open, the API may wait long past the transaction timeout. The transaction may later fail on a database operation or at commit, yet the API wait itself is not necessarily cut off at the timeout boundary.

Therefore, configure both dependency timeouts and transaction timeouts where appropriate. Do not rely on transaction timeout as the sole mechanism to bound processor runtime.

## 9. Designing a time budget per item

If a processor calls multiple dependencies, define an overall deadline. For example, an item has an 8-second budget:

| Stage | Maximum budget |
|---|---:|
| Fetch reference data | 2 seconds |
| Call scoring service | 3 seconds |
| Calculation and mapping | 1 second |
| Reserve/overhead | 2 seconds |

Do not grant every dependency the full 8 seconds. If two services sequentially wait 8 seconds each, total time reaches 16 seconds or more.

Deadlines should propagate throughout the processing chain. Each step checks remaining time and does not start a new operation if the budget is exhausted. Use `System.nanoTime()` to measure elapsed time because it suits monotonic intervals; do not use `System.currentTimeMillis()` for timeouts because system clocks can jump.

Example of a small deadline helper:

~~~java
public final class Deadline {

    private final long deadlineNanos;

    private Deadline(Duration budget) {
        this.deadlineNanos = System.nanoTime() + budget.toNanos();
    }

    public static Deadline after(Duration budget) {
        return new Deadline(budget);
    }

    public Duration remaining() {
        long nanos = deadlineNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0, nanos));
    }

    public void throwIfExpired() {
        if (deadlineNanos - System.nanoTime() <= 0) {
            throw new ProcessorTimeoutException(
                    "Processor deadline exceeded", null);
        }
    }
}
~~~

This is a simple example for a single `process` call. In production systems, validate positive budgets, avoid overflow when adding durations, and clearly set exception causes. When calling HTTP/JDBC, pass `remaining()` into the dependency timeout rather than always using a static constant.

Deadlines can only be enforced where code actively checks them or dependencies accept timeouts. They do not automatically interrupt an already blocking method.

## 10. Propagating deadlines across a processor chain

When using multiple delegates in `CompositeItemProcessor`, each delegate can receive the same context holding the deadline. One approach is an item envelope:

~~~java
public record ProcessingContext<T>(
        T item,
        Deadline deadline,
        String correlationId) {
}
~~~

The first processor creates the context:

~~~java
public class StartDeadlineProcessor
        implements ItemProcessor<OrderInput, ProcessingContext<OrderInput>> {

    @Override
    public ProcessingContext<OrderInput> process(OrderInput input) {
        return new ProcessingContext<>(
                input,
                Deadline.after(Duration.ofSeconds(8)),
                input.orderId());
    }
}
~~~

The next delegate checks remaining time before calling a dependency:

~~~java
public class EnrichWithCustomerProcessor
        implements ItemProcessor<ProcessingContext<OrderInput>,
                                 ProcessingContext<EnrichedOrder>> {

    private final CustomerClient customerClient;

    @Override
    public ProcessingContext<EnrichedOrder> process(
            ProcessingContext<OrderInput> context) {
        context.deadline().throwIfExpired();
        Customer customer = customerClient.fetch(
                context.item().customerId(),
                context.deadline().remaining());
        context.deadline().throwIfExpired();

        EnrichedOrder output = enrich(context.item(), customer);
        return new ProcessingContext<>(
                output,
                context.deadline(),
                context.correlationId());
    }
}
~~~

This example only illustrates deadline propagation; constructor injection, null handling, and method signatures must be completed for your application model. Another option is an orchestrating service accepting the deadline as a parameter instead of wrapping every item in an envelope. Either way, never store the current item's deadline in a singleton field.

## 11. Timeouts for CPU-bound processing

For CPU-bound processing, timeouts cannot safely stop code simply by throwing an exception from another thread. The right approach is breaking work into chunks that check the deadline or interruption:

~~~java
public Result calculate(Input input, Deadline deadline) {
    Result result = Result.empty();

    for (Part part : input.parts()) {
        deadline.throwIfExpired();
        if (Thread.currentThread().isInterrupted()) {
            throw new ProcessingInterruptedException(
                    "Processing thread was interrupted");
        }
        result = result.add(calculatePart(part));
    }

    return result;
}
~~~

Periodic checks allow cooperative termination. Check frequency should balance overhead against stopping latency. If a third-party computation library offers no cancellation or deadline hook, the application cannot guarantee stopping precisely at timeout.

Do not spawn a new thread per item just to call `Future.get(timeout)`. That can grow thread counts without bound when dependencies slow down, further destabilizing the job.

## 12. Using Future with timeout: when is it appropriate?

A wrapper can submit tasks to an executor and wait for results via `Future.get(timeout, unit)`. On expiry, the wrapper calls `cancel(true)` and throws a timeout exception:

~~~java
public class TimedProcessor<I, O> implements ItemProcessor<I, O> {

    private final ItemProcessor<I, O> delegate;
    private final ExecutorService executor;
    private final Duration timeout;

    public TimedProcessor(
            ItemProcessor<I, O> delegate,
            ExecutorService executor,
            Duration timeout) {
        this.delegate = delegate;
        this.executor = executor;
        this.timeout = timeout;
    }

    @Override
    public O process(I item) throws Exception {
        Future<O> future = executor.submit(() -> delegate.process(item));
        try {
            return future.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
            future.cancel(true);
            throw new ProcessorTimeoutException(
                    "Processor exceeded " + timeout, ex);
        } catch (ExecutionException ex) {
            Throwable cause = ex.getCause();
            if (cause instanceof Exception exception) {
                throw exception;
            }
            throw new IllegalStateException(
                    "Processor failed with an error", cause);
        } catch (InterruptedException ex) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            throw new ProcessingInterruptedException(
                    "Waiting for processor was interrupted", ex);
        }
    }
}
~~~

This is a specialized pattern, not a default solution for every processor. The executor must be managed by the Spring/application lifecycle, have bounded threads and queues, define a clear rejection policy, and shut down properly. Validate positive timeouts and handle `CancellationException` if tasks are canceled externally.

`cancel(true)` only sends an interrupt to the task's thread. It does not forcibly kill uncooperative code, cannot stop every I/O client, and does not undo already-executed side effects. The task may keep running after the caller receives the timeout.

Another major risk is that Spring's transaction context is typically thread-bound. If the delegate runs on a different executor thread, it does not automatically join the chunk transaction running on the calling thread. Never use this wrapper to offload JDBC work that must share the chunk transaction to a background thread. Use it only when task semantics are independent of the caller's transaction and have clear cancellation/idempotency mechanisms.

## 13. Bounded executors and bulkheads

If using an executor for processor work, bound both worker count and queue capacity. An unbounded executor can create too many threads or queue infinite tasks when downstream services slow down.

Example:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService processorExecutor() {
    return new ThreadPoolExecutor(
            8,
            8,
            0L,
            TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(100),
            new ThreadPoolExecutor.AbortPolicy());
}
~~~

In this example, at most eight tasks run concurrently and the queue holds at most 100 tasks. When the queue is full, new tasks are rejected instead of growing memory unboundedly. The application must decide how to translate `RejectedExecutionException` into an observable error and whether to retry after backoff.

A bulkhead isolates resources allocated to a dependency or work group. It prevents one slow service from consuming every batch worker. However, adding separate executors increases total thread count; compute total concurrency across the step, processor executor, HTTP connection pool, and database pool.

## 14. Spring Batch async processor does not create timeouts automatically

Spring Batch Integration provides components such as `AsyncItemProcessor` and `AsyncItemWriter` to process items asynchronously. An async processor typically returns a `Future` per item; the async writer waits for results before writing output.

Asynchrony and timeouts are two separate concerns:

- An async processor changes execution mechanics and intermediate data types.
- Timeouts specify maximum wait duration and how to cancel tasks.
- If a future never finishes, the writer may keep waiting depending on implementation.
- Never assume using an async processor automatically bounds per-item execution time.

If timeouts are needed on futures, explicitly design wait locations, cancellation, exception translation, and executor lifecycle. Also check transaction and restart semantics for your Spring Batch Integration version.

Do not use async processing merely to work around an HTTP call lacking a timeout. First configure timeouts on the HTTP client; only then consider async for throughput with appropriate concurrency limits.

## 15. Retrying on processor timeout

Timeouts can be transient errors, yet not every timeout should be retried. For example:

- A temporarily overloaded API may succeed on a retry.
- A query always performing a full table scan may time out repeatedly due to a missing index.
- A request that timed out after server processing may have already created a side effect.
- An item with an oversized payload may consistently exceed the time limit.

You can configure retries for classified timeout exceptions:

~~~java
return new StepBuilder("enrichOrdersStep", jobRepository)
        .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(ProcessorTimeoutException.class)
        .retryLimit(2)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

In this example, timeouts are retried up to the configured limit, while data errors can be skipped. Verify retry/skip semantics against your project's Spring Batch and Spring Retry versions. Never mark timeout exceptions as skippable just so the job always finishes if dropping items corrupts business results.

Retries need backoff, a bounded total attempt count, and an overall time budget. If an item has a 5-second timeout and three attempts, processing time can exceed 15 seconds once backoff is added. End-to-end deadlines must account for retry attempts.

## 16. Backoff, circuit breakers, and retry storms

When a downstream service is overloaded, many workers timing out together and retrying immediately can amplify load. This is a retry storm.

Mitigations:

- Exponential backoff to increase wait intervals between attempts.
- Jitter to prevent all workers from retrying at the exact same instant.
- Circuit breakers to temporarily halt calls to continuously failing dependencies.
- Bulkheads to limit concurrent requests.
- Rate limiters to keep call rates within service limits.
- Retrying only transient errors and safely repeatable requests.

Illustrative policy example:

| Attempt | Wait before attempt |
|---|---:|
| 1 | No wait |
| 2 | 500 ms plus jitter |
| 3 | 1 second plus jitter |

Actual values must be based on SLAs, rate limits, and dependency latency distributions. Circuit breakers and retries do not replace timeouts; each individual request still needs its own time limit.

## 17. Timeouts and skip policies

There are two distinct decisions:

1. Should the timed-out operation be retried?
2. If retries are exhausted, may the item be skipped?

If the timeout is an infrastructure failure and the data is mandatory to process, failing the step is usually safer than skipping. If business rules allow un-enriched items to move to a review queue, route/reject the item with a clear reason. Never turn every timeout into a filter by returning `null`.

When using skip, record at least the business key, source resource, exception type, timestamp, and attempt count. Do not store sensitive payloads unnecessarily. Set a skip limit to prevent a job from completing during widespread dependency outages.

Some timeout errors have indeterminate outcomes: the server may have processed the request while the response was lost. Before retrying or skipping, know whether the operation is idempotent and whether status can be queried to verify.

## 18. Timeouts in a multi-threaded step

When a step uses a `TaskExecutor`, multiple items can be processed concurrently. If the processor calls a slow dependency, occupied threads accumulate. Reasonable timeouts bound occupancy time, yet concurrency still needs limits.

Coordinate:

- Step worker thread count.
- Per-dependency timeouts.
- Connection pool size.
- HTTP max connections.
- Bulkhead limits.
- Chunk size and transaction duration.
- Retry/backoff budgets.

For example, with 16 workers but an HTTP client allowing only 4 connections to the same host, the remaining 12 workers may wait on the pool. Set a pool-acquisition timeout or match concurrency limits so pool wait time also fits within the budget.

A processor bean called concurrently by multiple threads must be stateless or thread-safe. Never store the current deadline, current item, or job-mutable timeout in a singleton field. Pass them via method arguments or item-specific contexts.

## 19. Timeouts in partitioning

With partitioning, each worker has its own `StepExecution`. A processor timeout in one partition can fail that partition step; the manager step aggregates worker statuses via the partition handler mechanism.

Design points:

- Dependency timeouts must apply in each worker.
- Cap total worker count so downstream systems are not overloaded.
- Partition retries must preserve the same data range and idempotency keys.
- Never allow a worker to time out while an inner task continues writing side effects after the partition was marked failed.
- Track timeouts per partition to identify problematic data ranges.

If each partition needs different processor configuration, use `@StepScope`/`ExecutionContext` to pass worker parameters. Scope does not create timeouts by itself; it only manages bean lifecycle and late binding.

## 20. Timeouts and transaction/chunk size

Chunk size impacts transaction duration and rollback scope. Large chunks hold many processor calls, so total chunk time equals total read/process/write time plus commit overhead. Even if each item has its own timeout, a chunk can still exceed the transaction timeout if many items are slow or retried.

Example:

- 100 items.
- Average 100 ms per item in processor.
- 5 items hit a 3-second timeout.

Chunk runtime can jump far above the average. Under sequential processing, timed-out items add up; under parallel processing, they consume workers and dependency capacity simultaneously.

Choose chunk size based on actual processing times, memory, transaction duration, and rollback impact. Smaller chunks limit transaction scope at the cost of more commits. Never use chunk size as a substitute for per-item timeouts.

## 21. Overall deadlines for a chunk or job

Beyond per-item timeouts, operations may require time limits for a chunk, step, or job. Design these limits separately:

- Item deadline: bounds processing time of one item.
- Chunk/transaction timeout: bounds a chunk transaction.
- Step/job SLA: alert threshold or operational policy when execution runs long.
- Scheduler deadline: target completion time so the job does not encroach on the next batch window.

If a job must be stopped when exceeding its SLA, use controlled execution governance, cooperative cancellation, and proper shutdown procedures. Never simply kill the thread running the processor; doing so can leave resources or side effects in indeterminate states.

A scheduler can alert before a deadline arrives, block new job launches, or request a controlled stop. Stopping should wait for transaction rollback/commit and lifecycle close within framework capabilities.

## 22. Handling interrupts properly

Thread interruption is a signal requesting a thread to stop or cancel work. Cooperative code should:

- Check `Thread.currentThread().isInterrupted()` at safe points.
- If a blocking API throws `InterruptedException`, restore the interrupt flag when propagating the exception upward.
- Never catch `InterruptedException` and continue processing as if nothing happened.
- Never turn shutdown-driven interruption into infinite timeout retries.
- Close resources in `finally` or `try-with-resources`.

Example:

~~~java
try {
    return blockingService.call();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new ProcessingInterruptedException(
            "Processor was interrupted", ex);
}
~~~

If a library ignores interrupts, the application cannot guarantee stopping it via `Future.cancel(true)`. Prefer clients with real timeout/cancellation support and test job shutdown behavior.

## 23. Timeout observability and logging

Timeouts should be monitored as a distinct error category. Collect:

- Timeout counts by dependency and operation.
- Latency p50/p95/p99.
- Retry counts and total retry duration.
- Active worker counts and queue depth.
- Connection pool wait times.
- Circuit breaker state and bulkhead rejections.
- Processor duration by item type or step.
- Skipped/rejected item counts due to timeouts.

Logs should include step name, partition ID if applicable, business key or correlation ID, dependency, timeout budget, and attempt number. Avoid logging full requests/responses or sensitive data.

Do not put individual business IDs into metric tags because cardinality grows unboundedly. Use low-cardinality tags such as step, dependency, operation, and exception category.

## 24. Testing processor timeouts

Timeout tests should verify both the exception and its consequences for the step. Do not rely solely on long `Thread.sleep()` calls in every test, as tests become slow and flaky. Use mock services to deterministically throw timeout exceptions; use a fake clock for deadline logic; use an HTTP stub server for client timeout integration tests.

Scenarios to test:

1. Dependency responds within timeout: processor returns normal output.
2. Dependency exceeds timeout: processor throws the right `ProcessorTimeoutException`.
3. Connect timeout and response timeout are distinguished if the client supports both.
4. Deadline already expired before calling dependency: processor does not start a new operation.
5. Remaining deadline is shorter than default timeout: client receives the remaining duration.
6. Thread interrupted: processor restores the interrupt flag and stops cooperatively.
7. Retries: attempt counts obey limits and backoff is applied.
8. Retries exhausted: step fails or skips per policy.
9. Unknown outcome: side effects are not duplicated on retry.
10. Multi-threaded step: concurrency does not exceed dependency limits.
11. Executor queue full: rejections are handled intentionally.
12. Job shutdown: tasks and resources close per lifecycle.

## 25. Unit testing with simulated service timeouts

Mock dependencies to verify exception translation:

~~~java
@Test
void convertsHttpTimeoutToProcessorTimeout() {
    CustomerApiClient client = new CustomerApiClient(
            httpClientThatTimesOut(),
            customerUri);

    assertThrows(
            ProcessorTimeoutException.class,
            () -> client.fetch("CUS-1"));
}
~~~

`httpClientThatTimesOut()` is a test double or mock configured to throw `HttpTimeoutException`. In unit tests, `HttpClient.send` can be mocked if the API and test framework permit; integration tests with a stub server verify actual client timeout enforcement.

For `Deadline`, inject a `LongSupplier` or `Clock` abstraction to test elapsed time without real waiting. For `System.nanoTime`-based deadlines, an abstraction supplying monotonic ticks enables deterministic, non-flaky expiration tests.

## 26. Integration testing timeouts and retries in a step

A step integration test should run with a processor calling a fake service:

- First attempt times out.
- Retry attempt succeeds.
- Verify the processor is called the expected number of times.
- Verify the writer writes the result only once.
- Verify step status and retry count are accurate.

Another test can make the service time out on every attempt to confirm the step fails after the retry limit or skips per policy. Inspect both outputs and reject stores; `COMPLETED` status alone does not prove data completeness.

For transactions, use a real transaction manager/test database when proving rollback. For HTTP, use a stub server to inject response delays and confirm request timeouts fire. Keep test timeouts short yet stable on CI; avoid depending on exact millisecond scheduler precision.

## 27. Common pitfalls

**Assuming `ItemProcessor` has a built-in timeout property.** The contract has no universal timeout. Configure timeouts at dependencies or build an appropriate deadline/wrapper.

**Using transaction timeout to interrupt HTTP calls.** The transaction manager does not forcibly abort arbitrary blocking calls. Set timeouts on the HTTP client.

**Configuring only connect timeout.** Connections succeed while the server hangs without responding. Configure request/read timeouts properly.

**Giving every dependency the full item timeout.** Sequential calls push total time past budget. Propagate deadlines and remaining time.

**Retrying every timeout immediately.** Can cause a retry storm. Use bounded retries, backoff/jitter, circuit breakers, and bulkheads.

**Treating a timeout as proof the server never processed the request.** Responses can be lost after side effects already committed. Use idempotency keys and reconciliation.

**Using `Future.cancel` as a kill switch.** Cancel only sends an interrupt; uncooperative tasks keep running. Configure real client timeouts and write cooperative code.

**Spawning a new thread per item.** When dependencies slow down, thread counts grow without bound. Use executors with bounded pools and queues only when truly needed.

**Offloading JDBC work to a background thread expecting the same transaction.** Transaction contexts are typically thread-bound. Keep transaction-bound work on the chunk thread.

**Catching `InterruptedException` without restoring the flag.** Shutdown/cancellation signals can be lost. Restore the interrupt flag and propagate errors properly.

**Timeouts too short or too long.** Too short causes false timeouts; too long ties up workers and transactions. Base values on latency distributions and SLAs.

**Failing to test timeouts in a step.** Unit testing dependencies does not prove retry/skip/rollback work. Add step integration tests.

## 28. Processor timeout design checklist

When a processor calls potentially slow dependencies, follow this sequence:

1. Identify which operations can block and their current latency profiles.
2. Choose appropriate connect, read/request, query, and pool timeouts per dependency.
3. Set an end-to-end item budget if the processor spans multiple steps.
4. Pass deadlines or remaining time to dependencies; do not reuse full timeouts at every step.
5. Translate timeouts into dedicated exceptions, preserving cause and essential context.
6. Classify transient errors, data errors, interruptions, and programming bugs.
7. Configure retry/backoff/skip/fail based on recoverability and business requirements.
8. Verify idempotency for any operation with side effects or indeterminate outcomes.
9. Bound concurrency, connection pools, and executor queues.
10. Distinguish processor timeouts from transaction timeouts and job SLAs.
11. Write unit tests for deadlines/exceptions and integration tests for clients and steps.
12. Monitor timeout rates, latencies, retries, queue depth, and worker utilization in production.

## Conclusion

Processor timeouts must be designed inside the operations the processor invokes. `ItemProcessor` has no universal timeout for Spring Batch to automatically abort the method. Set connect/request timeouts on HTTP clients, query timeouts on JDBC/databases, cap pool/executor waits, and apply end-to-end deadlines when an item traverses multiple dependencies.

Transaction timeouts bound transactions within transaction manager and resource capabilities; they do not guarantee stopping arbitrary Java code or I/O. `Future.cancel(true)` likewise only sends an interrupt, so it works only when tasks and dependencies cooperate with cancellation. For retryable timeouts, use dedicated exceptions, bounded attempts, and backoff; verify idempotency because a timeout does not prove server-side processing did not happen.

Finally, bound concurrency and test both the processor and the step. A reliable timeout policy defines wait limits, stopping behavior, recovery paths, and detection of dropped data or duplicated side effects.
