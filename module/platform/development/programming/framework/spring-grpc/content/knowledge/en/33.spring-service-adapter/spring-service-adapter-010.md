# Handling Blocking I/O

In **SPRING_GRPC**, the gRPC service adapter receives protobuf requests, invokes application use cases, and sends results via `StreamObserver`. Many use cases still require synchronous operations such as JDBC/JPA, file reads, legacy SDK calls, or calling downstream services with blocking clients. These operations wait for I/O to complete before returning; while waiting, the thread executing the RPC cannot handle other work.

The goal is not to eliminate every blocking call. The goal is to place them on appropriate threads and inside appropriate transactions, bound concurrency, respect deadlines/cancellation, and avoid holding resources while waiting on the network. This lesson focuses on handling blocking I/O in a Spring gRPC adapter, from unary RPCs to streaming and downstream calls.

## 1. Identifying Blocking I/O

An operation is blocking when the calling thread must wait for the result before continuing. Common examples:

- JDBC/JPA queries or transaction commits.
- Reading/writing files or object storage via synchronous APIs.
- Calling synchronous REST clients or cloud SDKs.
- Calling gRPC via a blocking stub.
- Waiting on synchronous locks, semaphores, or queues.

When an RPC handler performs blocking I/O, the thread serving that call is occupied until the operation completes. If many requests wait on the database or a downstream service simultaneously, occupied threads climb; once the executor runs out of threads and the queue fills, new requests are delayed or rejected.

Distinguish blocking application calls from the Netty event loop. Native gRPC Java normally dispatches application listeners through a server executor; do not assume service methods run directly on Netty event-loop threads. Nevertheless, blocking handlers still occupy threads of the RPC-serving executor. If a custom transport configuration or adapter runs callbacks on the event loop, blocking there can stall I/O across many connections.

## 2. Unary RPC: Direct Synchronous Calls When Work Is Bounded

For unary RPCs with short, predictable execution times and matching concurrency, the adapter can call the use case synchronously right in the handler:

```java
@Override
public void getStock(
        StockRequest request,
        StreamObserver<StockReply> observer) {
    try {
        StockView result =
                stockQuery.findBySku(new Sku(request.getSku()));

        observer.onNext(mapper.toProto(result));
        observer.onCompleted();
    } catch (StockNotFoundException error) {
        observer.onError(Status.NOT_FOUND
                .withDescription("Stock item not found")
                .asRuntimeException());
    } catch (RuntimeException error) {
        log.error("GetStock failed", error);
        observer.onError(Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException());
    }
}
```

This is simple and usually appropriate when:

- Query response time is bounded.
- Connection pools and server executors have sufficient capacity.
- There are no long or unbounded waits.
- RPC deadlines and dependency timeouts are configured sensibly.

Synchronous calls are not inherently wrong. Offloading every method onto another executor also introduces queueing, context propagation, cancellation, and lifecycle complexity. Offload only when you need to isolate slow work or protect a shared executor.

## 3. Do Not Use Ad-Hoc Threads or Unbounded Executors

Never spawn a new thread per RPC and never use cached/unbounded executors for uncontrolled load. When a downstream service slows down, thread count and memory can grow with the number of waiting requests.

Use a dedicated bounded executor for blocking workloads. Spring example:

```java
@Configuration
class GrpcBlockingIoConfiguration {

    @Bean
    ThreadPoolTaskExecutor grpcBlockingExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(16);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("grpc-blocking-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

These numbers are only illustrative starting points. Size pools based on I/O duration, CPU, connection pool limits, downstream concurrency, and measured load. Large queues do not make the system faster; they only hold more waiting requests and can cause deadlines to expire before work even starts.

A dedicated executor creates a bulkhead: one slow downstream service cannot consume all threads serving every RPC type. Separate pools can be created for database, file storage, and remote SDKs when groups have distinct load profiles.

## 4. Offloading Unary RPCs While Preserving gRPC Context

When separating blocking I/O from the handler thread, submit the work to an executor. Capture the current Context and wrap the task so gRPC's request-scoped state, deadline, and cancellation attach to the executing thread.

```java
@Service
class StockGrpcService
        extends StockServiceGrpc.StockServiceImplBase {

    private final AsyncTaskExecutor blockingExecutor;
    private final StockQueryUseCase stockQuery;
    private final StockProtoMapper mapper;

    StockGrpcService(
            @Qualifier("grpcBlockingExecutor")
            AsyncTaskExecutor blockingExecutor,
            StockQueryUseCase stockQuery,
            StockProtoMapper mapper) {
        this.blockingExecutor = blockingExecutor;
        this.stockQuery = stockQuery;
        this.mapper = mapper;
    }

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        Context rpcContext = Context.current();

        try {
            blockingExecutor.submit(rpcContext.wrap(() -> {
                if (rpcContext.isCancelled()) {
                    return;
                }

                try {
                    StockView result = stockQuery.findBySku(
                            new Sku(request.getSku()));

                    if (rpcContext.isCancelled()) {
                        return;
                    }

                    observer.onNext(mapper.toProto(result));
                    observer.onCompleted();
                } catch (StockNotFoundException error) {
                    observer.onError(Status.NOT_FOUND
                            .withDescription("Stock item not found")
                            .asRuntimeException());
                } catch (RuntimeException error) {
                    log.error("GetStock failed", error);
                    observer.onError(Status.INTERNAL
                            .withDescription("Internal server error")
                            .asRuntimeException());
                }
            }));
        } catch (TaskRejectedException rejected) {
            observer.onError(Status.RESOURCE_EXHAUSTED
                    .withDescription("Server is busy")
                    .asRuntimeException());
        }
    }
}
```

The example uses Spring's `AsyncTaskExecutor` and `ThreadPoolTaskExecutor`. Imports, constructor injection, and mappers are condensed to match typical application structure. The task is wrapped with the Context captured before the handler returns; without wrapping, Context keys or the active deadline may be missing on the worker thread.

For each task, only one thread should invoke `onNext`/`onCompleted`/`onError`. Never let multiple workers write concurrently to one `StreamObserver`; the observer is not a synchronization point for multiple producers. If emitting from multiple sources, collect results through a queue and use a single sequential writer.

When the executor rejects a task, return a meaningful status such as `RESOURCE_EXHAUSTED` or `UNAVAILABLE` per the service's load policy. Do not silently drop requests or spawn unbounded overflow threads.

## 5. Cancellation Must Stop Blocking Work

When the client cancels an RPC or its deadline expires, the server receives cancellation status via gRPC Context. However, cancellation does not automatically stop blocking JDBC drivers, file APIs, or SDKs.

With a server call, you can observe cancellation and ask the worker to stop:

```java
ServerCallStreamObserver<StockReply> serverObserver =
        (ServerCallStreamObserver<StockReply>) observer;

AtomicReference<Future<?>> taskRef = new AtomicReference<>();

serverObserver.setOnCancelHandler(() -> {
    Future<?> task = taskRef.get();
    if (task != null) {
        task.cancel(true);
    }
});

Context rpcContext = Context.current();
Future<?> task = blockingExecutor.submit(
        rpcContext.wrap(() -> performBlockingLookup()));

taskRef.set(task);

if (rpcContext.isCancelled()) {
    task.cancel(true);
}
```

This is an illustrative skeleton; in real code, response emission and exception handling belong inside the task as in the unary example above. Handle the race between cancellation and task submission, and guarantee only one terminal signal is emitted.

`Future.cancel(true)` sends an interrupt to the worker if the task is running. This is a best-effort cancellation request, not proof that I/O stopped. A JDBC driver, socket, or SDK may ignore interrupts. Therefore, you still need query timeouts, socket/read timeouts, client cancellation APIs, and dependency-level timeouts.

Do not call `onError` from the cancellation handler while letting the worker continue and call `onNext`. Designate a single place responsible for completing the observer; the worker must check cancellation before emitting responses.

## 6. Deadlines Must Bound I/O Wait Times Too

gRPC deadlines limit RPC duration. If the client only has 300 ms remaining while a database query has a 10-second timeout, the worker may keep holding the thread and connection long after the client has given up.

Read the remaining time from Context and use it to set a budget for dependencies:

```java
Context context = Context.current();
Deadline deadline = context.getDeadline();

long remainingMillis = deadline == null
        ? 1_000
        : deadline.timeRemaining(TimeUnit.MILLISECONDS);

if (remainingMillis <= 0 || context.isCancelled()) {
    throw new RpcWorkCancelledException();
}

long operationBudgetMillis = Math.min(
        remainingMillis, DEFAULT_QUERY_BUDGET_MILLIS);

return repository.findWithTimeout(
        sku, Duration.ofMillis(operationBudgetMillis));
```

This example illustrates budget calculation; exact timeout APIs depend on the repository, JDBC driver, or SDK. In production applications, set a default cap per operation and take the minimum between that cap and the RPC's remaining time. Avoid rounding that makes dependency timeouts significantly longer than the remaining deadline.

Deadlines do not replace per-dependency timeouts. An RPC may call a database, HTTP, and downstream gRPC; each step needs timeouts compatible with the remaining budget. Reserve a slice of time for mapping and sending the response instead of spending the entire budget on the final I/O call.

## 7. Transactions Must Begin on the Worker Thread

Spring transactions with JDBC/JPA are typically thread-bound. If the handler opens a transaction and dispatches blocking work to another executor, the worker thread does not automatically join that transaction.

Invoke a public `@Transactional` application method from the worker thread; the Spring proxy opens the transaction on the thread executing the use case:

```java
@Service
class ReserveStockService implements ReserveStockUseCase {

    @Override
    @Transactional
    public ReservationResult reserve(ReserveStockCommand command) {
        Stock stock = repository.findBySku(command.sku())
                .orElseThrow(StockNotFoundException::new);

        stock.reserve(command.quantity());
        reservationRepository.save(Reservation.create(command));
        return ReservationResult.from(stock);
    }
}
```

The adapter submits `reserveStock.reserve(command)` to the executor; the transaction opens and closes on the worker thread when the method finishes. Never pass an `EntityManager`, JDBC connection, or managed entity from the handler thread to a worker.

Avoid holding a transaction open while waiting on a remote HTTP/gRPC call whenever possible. Networks have variable latency and can hold database locks/connections too long. Use an outbox, saga, or split business steps when coordinating multiple services.

## 8. Blocking Downstream gRPC or HTTP Clients

Calling a downstream service with a blocking stub also occupies the current thread:

```java
StockReply reply = inventoryStub
        .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
        .getStock(request);
```

If this is part of a synchronous use case, include its duration in the RPC budget and avoid calling it while holding a database transaction. If the downstream call can be slow, isolate it in its own executor/bulkhead or use an async stub with appropriate callbacks.

Do not use one shared unbounded pool for all downstream services. One slow dependency can exhaust workers needed by other services. Configure timeouts, concurrency limits, and backoff retry policies; retries must account for idempotency and remaining deadlines.

When using synchronous Spring HTTP clients, configure connection timeouts, response/read timeouts, and connection pools. Setting only a gRPC deadline without an HTTP client timeout can still leave threads stuck long after the RPC has ended.

## 9. Streaming: Do Not Hold Threads and Transactions While Waiting on Consumers

In server streaming, a producer may read from a database and emit multiple responses. If it reads a blocking cursor and calls `onNext` continuously, the server may produce data faster than the client consumes it; if the client is slow, buffers and memory grow.

With `ServerCallStreamObserver`, check readiness and register `onReadyHandler` to emit data at the transport's pace:

```java
ServerCallStreamObserver<StockReply> output =
        (ServerCallStreamObserver<StockReply>) observer;

output.setOnReadyHandler(() -> {
    // Wake up producer/writer when transport can accept more data.
    streamPump.signalReady();
});
```

`onReadyHandler` may be invoked multiple times and should not run a long blocking loop directly on the callback thread. Use a producer/writer with a clear lifecycle; only one writer should call `onNext`. When `isReady()` is false, pause fetching or emitting data and wait for the ready signal.

For database data, read by page/chunk in short transactions and emit each batch. Avoid holding a cursor, transaction, or connection open for the entire duration the client receives the stream whenever possible. When the client cancels, stop the producer and close cursors/resources.

Client streaming must also bound the volume of buffered work waiting to be processed. Do not accumulate an entire stream into an unbounded `List` or queue. Process in batches, apply backpressure/flow control, and define clear partial-commit/resume policies if the stream is interrupted.

## 10. Bounded Concurrency, Queues, and Overload

Executor sizing must align with downstream limits. For example, if the database pool has only 20 connections, spawning 200 concurrent workers waiting on the database will not scale throughput proportionally; it only increases queueing, context switching, and wait times.

Metrics to monitor:

- Active workers, pool size, and queue depth.
- Rejected task counts and time spent in queue.
- Connection pool wait times and query execution times.
- RPC deadline exceeded counts, cancellations, and `RESOURCE_EXHAUSTED` statuses.
- Open connection/stream counts.
- Per-dependency p95/p99 latency.

When the queue is full, rejecting early allows clients to back off or pick another replica. A request that sits in a queue too long before starting I/O will often exceed its deadline and only create wasted load.

Do not blindly set `CallerRunsPolicy` on an executor receiving tasks from gRPC handlers. That policy can force the handler thread to run blocking work when the pool is full, defeating isolation. Use explicit rejection and map it to a status per overload policy.

## 11. Virtual Threads and Non-Blocking I/O

Virtual threads (Java 21+) can make the thread-per-request model lighter for blocking I/O across many workloads. However, they do not make database connections, remote services, or CPU capacity infinite.

If choosing virtual threads:
- Explicitly configure an executor using virtual threads for blocking tasks.
- Verify that the gRPC server executor actually uses that executor; enabling Spring Boot's virtual-threads property does not mean every transport executor automatically switches.
- Still bound concurrency to databases/downstream services using semaphores, bulkheads, or connection pools.
- Measure thread pinning, throughput, and latency on your actual JDK and drivers.
- Keep timeouts and cancellation because virtual threads cannot automatically cancel uninterruptible I/O.

If the entire stack supports reactive/non-blocking, non-blocking drivers and clients can reduce waiting threads. Never call blocking JDBC/JPA directly on a reactive runtime's event loop; a single blocking step can stall many other requests.

## 12. Testing Blocking I/O and Cancellation

Tests should prove both business results and behavior under load/waiting:

1. Use a stub or fake repository simulating slow I/O controllable via a latch.
2. Send multiple concurrent RPCs and verify the number of blocking tasks does not exceed executor bounds.
3. Fill the queue in an isolated test; verify new requests receive the expected overload status.
4. Set a deadline shorter than the I/O duration; verify the worker stops or dependency timeout triggers.
5. Cancel an RPC while a task is running; verify the cancellation handler runs and resources are released.
6. Verify domain exceptions map to the right statuses and unexpected errors do not leak internal details.
7. For streaming, simulate a slow-reading client; verify the producer respects readiness/backpressure.
8. Verify transactions open on the worker thread and commit/roll back properly.
9. Measure queue wait, execution time, and p95/p99 under representative load.

Use latches or controllable fakes instead of long `Thread.sleep` calls for deterministic tests. In-process transport works well for interceptor and status logic, while testing networking, TLS, or flow control requires a transport suited to the goal.

## 13. Common Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Blocking I/O without timeouts | Workers held indefinitely | Set timeouts on each dependency and RPC deadlines |
| Spawning a thread per request | Unbounded thread/memory growth | Use bounded executors with rejection policies |
| Using unbounded queues | Latency spikes, requests expire in queue | Use bounded queues and fail fast |
| Offloading without wrapping Context | Loss of request-scoped state/deadlines | Capture and wrap gRPC Context |
| Assuming cancellation interrupts JDBC | Queries keep running and hold connections | Use query/socket timeouts, driver cancellation, best-effort interrupts |
| Opening transaction before offloading | Worker does not join handler transaction | Open transaction in application method on worker |
| Writing to observer from multiple threads | Races or response ordering violations | Use one sequential writer per RPC |
| Streaming faster than consumer reads | Buffer and memory growth | Use readiness, flow control, chunking |
| Blocking downstream inside transaction | Locks/connections held during slow network calls | Separate network calls, use outbox or saga |
| Enabling virtual threads without resource bounds | Database/downstream still overwhelmed | Use bulkheads and connection/concurrency limits |

## 14. Practice Exercises

1. Write a unary adapter calling an application service with JDBC/JPA blocking I/O and measure execution time.
2. Create a dedicated `ThreadPoolTaskExecutor` with bounded pool size, queue capacity, and rejection policy.
3. Offload an RPC to the executor using `Context.current().wrap(...)`.
4. Add a client deadline and translate the remaining budget into a query/downstream timeout.
5. Add a cancellation handler; verify best-effort worker cancellation and resource cleanup.
6. Verify `@Transactional` executes on the worker thread via Spring proxying.
7. Call a downstream service via a blocking stub with a deadline shorter than the overall deadline.
8. Write a server-streaming producer that reads by page and emits only when the observer is ready.
9. Fill the queue in a test and verify the overload status is returned accurately.
10. Measure active workers, queue wait, I/O latency, cancellation, and p95/p99 under representative load.

### Key takeaway

**Blocking I/O can be used in gRPC adapters when threads, timeouts, and concurrency are managed intentionally.** For short unary calls, synchronous execution may suffice; for long-waiting work, use bounded executors and preserve gRPC Context when offloading. Set per-dependency timeouts, check cancellation, open transactions on the proper worker thread, and pace streaming via readiness/backpressure. Virtual threads reduce thread overhead, but do not replace database, downstream, or queue limits.

## References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html)
- [gRPC Java — ServerCallStreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ServerCallStreamObserver.html)
- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/)
- [gRPC — Flow Control](https://grpc.io/docs/guides/flow-control/)
