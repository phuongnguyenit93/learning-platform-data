
# Timeouts and Cancelling External Tasks

## 1. Lesson Objectives

A Function calling a payment service, querying a database, or waiting on a partner API can hang longer than the caller tolerates. Putting a timeout only on the HTTP response leaves underlying work running; cancelling a message consumer too early can leave the database committed without the broker receiving an ACK. Therefore, timeouts and cancellation must be designed end to end, from the adapter down to I/O operations.

In the **SPRING_CLOUD_FUNCTION** module, business logic is built using `Supplier`, `Function`, and `Consumer`, registered via `FunctionCatalog`, composed into pipelines, and deployed over HTTP, events, or serverless. The same function can run in multiple environments, yet deadlines, timeouts, and cancellation behavior depend on the adapter, client, and operation type.

This lesson belongs to the **Reliability** chapter and focuses on **timeouts and cancelling external tasks**. After this lesson, you will be able to:

- Distinguish timeout, deadline, cancellation, and actual task termination.
- Allocate time budgets for the entire request and each external call.
- Configure timeouts for HTTP clients, JDBC/databases, brokers, and serverless runtimes.
- Understand the limitations of `Future.cancel`, `CompletableFuture.orTimeout`, interrupts, and Reactor cancellation.
- Propagate remaining deadlines across services without compounding timeouts excessively.
- Handle timeouts where side effects may already have committed.
- Coordinate timeouts with transactions, retries, idempotency, and ACKs.
- Test both timeout errors and whether tasks are genuinely cancelled.

> **Guiding Principle:** A timeout bounds wait time or raises a failure signal; it does not prove external work stopped or failed to commit. Set timeouts on the right client/driver, propagate deadlines, design cooperative cancellation, and protect side effects with idempotency.

## 2. Four Concepts That Must Not Be Conflated

| Concept | Meaning | What You Cannot Automatically Conclude |
|---|---|---|
| Timeout | A wait or operation exceeded its limit | External work stopped |
| Deadline | Final timestamp by which the whole operation must finish | Every layer automatically knows the deadline |
| Cancellation | Request to stop in-flight work | Task stopped immediately |
| Completion | Task finished (success, failure, or cancelled) | Caller necessarily received the outcome |

Example of a client sending a request to a payment service:

~~~text
Client sends POST
     |
     v
Payment service receives request
     |
     v
Payment service creates transaction
     |
     v
Response is slow or lost
     |
Client times out and stops waiting
     |
     +---- Payment service may still be processing
~~~

The client timed out, yet the transaction may still have been created. A timeout is **the caller's observation**, not proof that the server rolled back.

### 2.1. A Timeout at One Layer Does Not Automatically Cancel All Layers

A request can traverse:

~~~text
HTTP client
    |
API gateway
    |
Spring Cloud Function adapter
    |
Application service
    |
HTTP client / JDBC driver / broker client
    |
External system
~~~

If the HTTP client times out, it may close the socket or send a cancellation down the transport. Yet the remote server may already have received the whole request and continue processing. If an application thread is interrupted, a driver may not stop immediately. If Reactor sends `cancel`, an upstream Publisher may lack a mechanism to undo already-committed I/O.

Hence distinguish **cancelling the call at the caller**, **cancelling work in the current process**, and **stopping side effects in external systems**.

## 3. Timeouts, Deadlines, and Time Budgets

Timeouts are usually configured per step; a deadline is an absolute limit for the entire operation. For example, a request with a 3-second deadline:

~~~text
Total budget: 3000 ms
  |
  +-- acquire connection: max 300 ms
  |
  +-- call partner API: max 1500 ms
  |
  +-- write DB: max 700 ms
  |
  +-- serialize/response/ACK: reserve at least 500 ms
~~~

These numbers are illustrative. Measure real latency and reserve time for cleanup, responses, or ACKs.

### 3.1. Per-Step Timeouts Can Add Up Past the Deadline

If three dependencies each have a 3-second timeout and are called sequentially, total duration can approach 9 seconds plus overhead. Meanwhile, if the caller waits only 4 seconds, the service may keep working long after the caller gave up.

Do not set every timeout identically out of habit. Compute budgets from the **overall deadline** and allocate them across steps.

### 3.2. Remaining Deadline Shrinks Across Hops

If a request starts with a deadline at 17:00:03 and Service A spends 1 second, Service B has roughly 2 seconds left. Never pass a fixed "3-second timeout" to each hop or total duration exceeds the original limit.

Each layer should compute:

~~~text
remaining = deadline - now
effectiveTimeout = min(localCap, remaining - responseReserve)
~~~

If remaining budget is insufficient for an operation, fail fast or switch to a stateful async workflow rather than starting work doomed to miss the deadline.

### 3.3. Monotonic Clocks vs. Wall Clocks

Within one process, measure durations using a monotonic clock (such as `System.nanoTime()`) to avoid skew from system clock adjustments. Across processes, send an exchangeable timestamp (such as an epoch deadline) or a remaining-timeout header.

Clocks across machines can drift. Never trust a client wall-clock deadline blindly; validate its range, enforce a local cap, and subtract a safety reserve. Inside one process, convert the deadline into a monotonic remaining duration for wait calculations.

## 4. Choosing Timeout Types per Operation

No single timeout covers every type of I/O.

| Layer | Timeouts to Care About | Risk If Missing |
|---|---|---|
| Connection pool | Time waiting to borrow a connection | Requests queue indefinitely |
| DNS/connect/TLS | Establishing connection | Hangs before sending request |
| HTTP response | Waiting for response | Caller waits too long |
| Socket read/write | Reading/writing bytes | Connection stays open without progress |
| JDBC connect | Opening DB connection | Threads wait on network |
| SQL statement/query | Executing statement | Queries hold resources too long |
| Transaction | Total transaction duration | Holds locks/connections too long |
| Broker delivery/visibility | Processing time before ACK/visibility expiry | Message redelivered while still running |
| Serverless invocation | Maximum handler runtime | Runtime kills invocation |
| Overall request | Overall deadline | Per-step timeouts stack beyond limit |

Pool, connect, read, and response timeouts can differ. A response timeout does not necessarily bound connection-pool acquisition or server work after the client disconnects.

### 4.1. Per-Attempt Timeout vs. Overall Timeout

If retrying a call three times, distinguish:

- **Per-attempt timeout:** bounds each individual attempt.
- **Overall deadline:** bounds all attempts, backoffs, and result processing.

~~~text
Overall deadline: 2500 ms
  Attempt 1: max 600 ms
  Backoff: 100 ms
  Attempt 2: max 600 ms
  Backoff: 200 ms
  Attempt 3: uses only remaining budget
~~~

When overall budget is nearly exhausted, do not start a new attempt. Retry policies must coordinate with deadlines, not just attempt counts.

## 5. Blocking Java: Waiting Timeout Does Not Mean Task Stopped

A common pattern runs work on an `ExecutorService` and waits on a `Future`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

ExecutorService executor = new ThreadPoolExecutor(
        8,
        8,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy());

Future<PaymentResult> future =
        executor.submit(() -> paymentClient.charge(command));

try {
    PaymentResult result = future.get(2, TimeUnit.SECONDS);
    return result;
} catch (TimeoutException timeout) {
    future.cancel(true);
    throw new PaymentTimeoutException(
            "Payment call exceeded its deadline", timeout);
}
~~~

`future.get(timeout)` bounds how long **the caller waits**. `future.cancel(true)` requests cancellation and may interrupt the running thread, yet does not guarantee that the task or socket I/O stops immediately.

### 5.1. Interrupts Are Cooperative

A Java task can check for interruption:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    doSmallUnitOfWork();
}
~~~

When blocked inside interruptible APIs, a thread may receive `InterruptedException`. When catching it without rethrowing directly, usually restore the interrupt flag:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationCancelledException(ex);
}
~~~

Never ignore an interrupt and continue as if nothing happened. Still, many native, network, and database calls do not stop just because a thread is interrupted; use the client's or driver's own timeout/cancel APIs.

### 5.2. Do Not Spawn Unbounded Threads to Work Around Timeouts

Never spawn a new thread per request and let hung tasks accumulate unboundedly. When a dependency slows down, threads and connections can grow until resources exhaust.

Use bounded executors, bounded queues, I/O client timeouts, and load-shedding on overload. Monitor active tasks, queue depth, and timed-out tasks.

## 6. CompletableFuture: Timing Out the Result vs. Cancelling the Work

Java provides `orTimeout` and `completeOnTimeout`:

~~~java
CompletableFuture<PaymentResult> future =
        paymentClient.chargeAsync(command);

return future.orTimeout(2, TimeUnit.SECONDS);
~~~

`orTimeout` completes the future with a timeout exception if the deadline expires. It does not guarantee the request sent to the external system is cancelled. Similarly:

~~~java
return paymentClient.lookupAsync(id)
        .completeOnTimeout(
                PaymentResult.unknown(id),
                2,
                TimeUnit.SECONDS);
~~~

`completeOnTimeout` supplies a fallback value to the caller when expired; the underlying task may still continue. Never use a fallback result to claim a transaction failed or was never created.

### 6.1. CompletableFuture.cancel() Does Not Guarantee Computation Interruption

`CompletableFuture.cancel(true)` does not behave like interrupting an application-managed thread; the `mayInterruptIfRunning` flag does not control underlying computations the way many developers expect.

To actually stop work, retain a handle from a cancellation-capable client/task and call its cancellation API. For example, an HTTP client may expose a handle/subscription to abort a request; a database driver may support cancelling a statement.

### 6.2. Do Not Use the Common Pool for Uncontrolled Blocking I/O

`CompletableFuture.supplyAsync(...)` without an executor uses the common `ForkJoinPool`. Long blocking I/O can starve shared workers. Use a dedicated bounded executor or an appropriate non-blocking client.

## 7. WebClient and Reactor: Timeouts Signal Errors, Cancellation Propagates Upstream

On a `Mono`, you can place a timeout at the dependency boundary:

~~~java
Mono<PaymentResult> result =
        webClient.post()
                .uri("/payments")
                .bodyValue(command)
                .retrieve()
                .bodyToMono(PaymentResult.class)
                .timeout(Duration.ofSeconds(2));
~~~

If no result arrives within the limit, Reactor emits a timeout error and cancels the upstream subscription per operator semantics. The client connector may close or abort the in-flight request. However, the remote server may already have received the request and keep processing; cancellation never rolls back an already-committed transaction.

### 7.1. timeout on Flux Can Act as an Idle Timeout

On a `Flux`, `timeout(Duration)` normally bounds the wait for the next signal; the timer resets on every item. That detects stalled streams, yet does not necessarily cap the total lifetime of a continuously emitting stream.

If a stream needs a total deadline, wrap it in an overall deadline mechanism or duration limit matching your semantics. `take(Duration)` completes normally when time expires, unlike `timeout` which signals an error. Pick the operator matching your contract.

### 7.2. Observing Cancellation Differs from Observing Errors

~~~java
Mono<PaymentResult> operation =
        remoteCall()
            .doOnError(error -> metrics.recordFailure())
            .doOnCancel(() -> metrics.recordCancellation())
            .doFinally(signal -> logTerminalSignal(signal));
~~~

`doOnError` is not invoked merely because downstream cancels. `doOnCancel` observes cancellation; `doFinally` observes complete, error, or cancel. Never lump every cancellation together with dependency failures.

### 7.3. Cancelling Upstream Does Not Guarantee External Side Effects Stop

Cancellation propagates across Publishers, yet each adapter must support it. A custom Publisher ignoring cancel, a blocking JDBC call, or a remote server that already committed may continue running.

For blocking I/O in Reactor:
- Use an appropriate scheduler to avoid blocking event loops.
- Configure driver/socket/query timeouts.
- Never treat cancelling a subscription as proof that JDBC stopped.
- Design idempotency and state lookup when commit outcomes are unclear.

 
## 8. Configuring Timeouts on WebClient / Reactor Netty

An HTTP request spans multiple phases. Example Reactor Netty configuration:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

ConnectionProvider pool = ConnectionProvider.builder("payment-client")
        .maxConnections(100)
        .pendingAcquireTimeout(Duration.ofMillis(300))
        .build();

HttpClient httpClient = HttpClient.create(pool)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
        .responseTimeout(Duration.ofSeconds(2));

WebClient paymentWebClient = WebClient.builder()
        .baseUrl("https://payment.example")
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
~~~

Each limit here serves a distinct role:

- `pendingAcquireTimeout` caps time waiting to acquire a connection from the pool.
- `CONNECT_TIMEOUT_MILLIS` caps TCP connection establishment.
- Reactor Netty's `responseTimeout` bounds response reading per connector semantics—do not treat it blindly as an overall business deadline.
- `Mono.timeout` at the boundary can cap total time the caller waits for the result Publisher.

Combined example:

~~~java
Mono<PaymentResult> charge =
        paymentWebClient.post()
                .uri("/payments")
                .bodyValue(command)
                .retrieve()
                .bodyToMono(PaymentResult.class)
                .timeout(Duration.ofSeconds(3));
~~~

The overall deadline must accommodate required phase timeouts while staying inside the caller's budget. Setting only a per-request timeout without pool/connect/read limits can allow another phase to stall unexpectedly.

### 8.1. Read Timeout vs. Write Timeout

Read timeout typically bounds inactivity between reads; write timeout bounds a stalled write operation. Neither necessarily bounds the total duration of an entire HTTP request. Exact property names and behavior depend on the connector/client.

If adding Netty handlers, understand how handlers attach per connection and their lifecycle. Avoid attaching arbitrary timeout handlers that break reused connections. Prefer official client configs for your version and test connection reuse.

### 8.2. Do Not Configure Timeouts Only at the Gateway

A 3-second gateway timeout does not automatically halt downstream requests. If the gateway aborts the response while the application continues calling payment or DB, resources are still consumed.

Propagate remaining deadlines to the application and outbound clients; every layer must reject new work once budget runs out.

## 9. Database / JDBC: Connection Acquire, Query, and Transaction Timeouts

A JDBC operation can wait in several places:

1. Waiting for a connection from the pool.
2. Opening a socket/connection to the database.
3. Waiting for the server to execute SQL.
4. Reading results over the network.
5. Waiting on locks or transaction commit.

An overall HTTP timeout does not replace timeouts at these layers.

### 9.1. JDBC Query Timeout

JDBC provides `Statement.setQueryTimeout`:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT status FROM payment WHERE payment_id = ?")) {

    statement.setString(1, paymentId);
    statement.setQueryTimeout(2);

    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            return rs.getString("status");
        }
        return null;
    }
}
~~~

`setQueryTimeout(2)` asks the driver to limit statement execution in seconds. Drivers and databases vary in semantics and granularity; verify against the real database. Query timeout does not automatically bound all network operations or connection-pool acquisition time.

### 9.2. Connection Pool Timeout Differs from Query Timeout

In HikariCP, `connectionTimeout` limits how long a caller waits to borrow a connection from the pool. It does not limit how long SQL executes on an acquired connection. Configure pool timeouts, JDBC driver connect/socket timeouts, and statement/query timeouts separately.

### 9.3. Database-Side Statement Timeout

Databases can enforce query limits server-side. For example, PostgreSQL offers `statement_timeout`. Server-side timeouts help when clients disconnect or cannot deliver cancels in time, yet must be tuned per role/session/transaction considering legitimate long queries.

A timed-out or cancelled statement can leave the current transaction in an aborted state depending on the database. Roll back and close the transaction cleanly before returning the connection to the pool.

### 9.4. Spring Transaction Timeout Is Not Universal

`@Transactional(timeout = 3)` sets a timeout for new transactions where the transaction manager and resources support it. It does not guarantee interrupting arbitrary Java code, stopping an HTTP request, or cancelling external side effects.

~~~java
@Transactional(timeout = 3)
public void updateOrder(Order order) {
    repository.save(order);
}
~~~

Transaction timeouts are generally propagated to resource-aware operations when supported by the framework and driver. Verify your transaction manager, JDBC/JPA provider, and generated statements; never use the annotation as a substitute for query or socket timeouts.

### 9.5. Query Cancellation Is Best-Effort

JDBC provides `Statement.cancel()` and `Connection.setNetworkTimeout`. The driver may send a cancel packet to the database, yet network errors or an already-finished query can leave the outcome ambiguous. When a timeout occurs near commit, check state via idempotency/business key before re-running.

## 10. Timeouts and Transactions: Caller Timing Out Does Not Mean Transaction Rolled Back

Consider a synchronous application service:

~~~text
HTTP caller deadline: 2 seconds
       |
       v
Application service begins transaction
       |
       v
UPDATE order
       |
       v
DB waits 4 seconds for lock
       |
Caller times out after 2 seconds
       |
       +---- Thread/DB call may still be running
       |
       v
DB may commit after caller already gave up
~~~

If the caller simply stops waiting, the transaction can still finish. If the framework interrupts the thread, the driver may not abort the query. If the query is cancelled before commit, the transaction may roll back—but verify it.

### 10.1. Do Not Leave Side Effects Running Unowned After Caller Timeout

When a request exceeds its deadline, make a business decision:

- Work is no longer wanted: request cancellation and verify it stopped.
- Work must finish even if caller leaves: convert into an asynchronous job with an ID/status and return `202 Accepted`.
- Commit outcome is unclear: persist/query status by idempotency key.
- Side effects may already have occurred: do not retry blindly; reconcile or use idempotent operations.

Never spawn a detached thread to keep updating the DB after returning an HTTP timeout without tracking job state and observing outcomes.

### 10.2. Do Not Hold a DB Transaction Open While Waiting on External Services

~~~java
@Transactional
public PaymentResult placeOrder(OrderCommand command) {
    orderRepository.save(command.toOrder());
    return paymentClient.charge(command); // Never wait on remote calls inside a DB transaction.
}
~~~

If payment is slow, the DB transaction holds connections and locks. If payment succeeds and the DB rolls back, the two systems diverge. If the whole method retries, the payment command may be sent again.

Split the workflow: save state in a transaction, call payment with an idempotency key under controlled orchestration, and update state—or use an outbox/saga for multi-step coordination.

### 10.3. Timeouts During Transaction Commit

A connection failure during commit can leave the client unsure whether the DB committed. Never assume "commit threw an error means rollback." Query state by business key / operation ID from a fresh connection and reconcile.

## 11. Deadline Propagation Across Services

A multi-service system must pass **remaining budget**, not just a static timeout.

~~~text
Ingress receives 4-second deadline
    |
    +-- validate/auth uses 200 ms
    |
    v
Service A has 3.8 seconds left
    |
    +-- calls Service B, passes remaining ~3.8 seconds
    |
    v
Service B has remainder after processing
    |
    +-- calls DB with min(local cap, remaining)
~~~

### 11.1. Deadline Headers Are a System Contract

You can use an internal header like `X-Request-Deadline` or `X-Timeout-Ms`, provided semantics are agreed upon:

- Is it an epoch deadline or a remaining duration?
- Does the server enforce a maximum cap?
- Is a network/clock-skew reserve subtracted?
- Is a client allowed to request an infinite timeout?
- Can gateways strip or overwrite the header?

No arbitrary HTTP header becomes a universal standard by itself. With gRPC, deadlines/contexts have native mechanisms; when bridging HTTP or messaging, map them explicitly.

### 11.2. Convert Wall-Clock Deadlines into Remaining Duration

Upon receiving an epoch deadline, validate bounds and compute remaining time. Then track remaining duration internally with a monotonic clock so clock adjustments mid-request do not distort waits.

If the deadline has already expired or too little budget remains, reject early or transition to an async flow without starting downstream calls.

### 11.3. Reserve Budget for Responses and ACKs

Do not spend the entire deadline on the final outbound call. Reserve time to:

- Commit or roll back transactions.
- Write necessary logs/metrics.
- Serialize responses or build error responses.
- ACK or checkpoint messages if managed by an adapter.
- Clean up and release connections.

Choose reserves based on real p95/p99 latency rather than an arbitrary constant.

## 12. Cancellation Tokens for Cooperative Work

Some tasks cannot be aborted automatically. Pass a cancellation abstraction down to steps capable of checking it.

~~~java
package example.functions;

public interface CancellationToken {
    boolean isCancellationRequested();

    default void throwIfCancellationRequested() {
        if (isCancellationRequested()) {
            throw new OperationCancelledException();
        }
    }
}
~~~

An application exception can be defined as:

~~~java
public class OperationCancelledException extends RuntimeException {
    public OperationCancelledException() {
        super("Operation was cancelled");
    }

    public OperationCancelledException(Throwable cause) {
        super("Operation was cancelled", cause);
    }
}
~~~

Tokens can be backed by `AtomicBoolean`, framework contexts, or built-in cancellation primitives. Executors from earlier examples should be lifecycle-managed beans shut down on application stop—never create a new pool per request.

### 12.1. Checking Between Steps

~~~java
public Result process(Input input, CancellationToken token) {
    token.throwIfCancellationRequested();

    Prepared prepared = prepare(input);

    token.throwIfCancellationRequested();

    ExternalResult external = client.call(prepared);

    token.throwIfCancellationRequested();

    return finalizeResult(external);
}
~~~

A token works only if code and dependencies **cooperate by checking it**. It does not stop a method blocked inside JDBC or a remote server already processing a request.

### 12.2. Cancellation Does Not Replace I/O Timeouts

A token lets the application skip starting the next step. While waiting on a socket, you still need socket/read timeouts or client cancel APIs. Combine:
- Deadlines to know how much time remains.
- Cancellation tokens to propagate stop requests.
- Client/driver timeouts to bound I/O.
- Idempotency to handle uncertain outcomes.

### 12.3. Do Not Turn Cancellation into a Normal Business Error

Cancellation typically means the caller or runtime stopped waiting. It differs from validation errors and transient dependency failures. Never auto-retry an operation simply because it was cancelled; first determine whether side effects occurred and who remains responsible for completion.

## 13. Applying Timeouts in Spring Cloud Function

A Function can accept input, compute results, and invoke dependencies. However, `FunctionCatalog` does not impose an overall deadline on every Function.

### 13.1. FunctionCatalog Is Not a Timeout Manager

`catalog.lookup("chargePayment")` resolves a bean by name and compatible type. It does not automatically:
- Set timeouts on JDBC, HTTP clients, or broker clients.
- Cancel running threads.
- Send cancellations to external servers.
- Bound the duration of a composed pipeline.
- Guarantee transaction rollback on caller timeout.

Timeouts must be set at **the boundary that understands the work**: HTTP clients for outbound HTTP, JDBC/drivers for queries, transaction managers for transactions, and adapters for invocation/message lifecycles.

### 13.2. Keep Functions Pure and Enforce Deadlines at the Application Boundary

~~~java
@Bean
Function<OrderCommand, Quote> calculateQuote() {
    return command -> new Quote(
            command.orderId(),
            command.quantity(),
            Math.multiplyExact(command.quantity(), 125_000L));
}
~~~

Pure computation needs no I/O timeout. When a workflow calls external services, create a dedicated application service:

The intermediate record below is an illustrative domain type:

~~~java
public record PricedOrder(OrderCommand command, Price price) {}
~~~

~~~java
@Service
public class QuoteApplicationService {

    private final Function<PricedOrder, Quote> calculate;
    private final PricingClient pricingClient;

    public QuoteApplicationService(
            Function<PricedOrder, Quote> calculate,
            PricingClient pricingClient) {
        this.calculate = calculate;
        this.pricingClient = pricingClient;
    }

    public Mono<Quote> quote(OrderCommand command) {
        return pricingClient.fetchPrice(command.sku())
                .timeout(Duration.ofMillis(800))
                .map(price -> calculate.apply(
                        new PricedOrder(command, price)))
                .timeout(Duration.ofSeconds(2));
    }
}
~~~

This example is illustrative; `PricingClient` returns `Mono<Price>`, and `PricedOrder` is a domain record defined by the app. The 800 ms timeout caps pricing; the 2-second timeout caps the workflow Publisher. If pricing times out, Reactor emits an error and cancels the upstream subscription as supported by the client.

### 13.3. Message<T> Can Carry Deadline Metadata

Spring Cloud Function can work with Spring `Message`. An adapter can read deadline/trace headers and translate them into an application context. Still, avoid coupling domain Functions directly to arbitrary transport headers.

One option is passing context explicitly:

~~~java
public record ExecutionContext(
        Instant deadline,
        String correlationId) {}

public record CommandEnvelope<T>(
        T payload,
        ExecutionContext context) {}
~~~

Adapters map HTTP/message/serverless metadata into `ExecutionContext`. The application service computes remaining budget and passes it down to clients. To keep the pure core reusable, hold context at the workflow boundary instead of embedding every header in domain models.

### 13.4. Composition Does Not Sum Deadlines Automatically

`validateOrder|calculateQuote|chargePayment` describes only composition order. If each Function has a 2-second timeout, the combined pipeline can exceed 2 seconds. Enforce an overall deadline in the workflow and per-call timeouts on outbound clients, each using the remaining budget.

## 14. Supplier, Function, and Consumer with External Tasks

### 14.1. A Supplier Can Block While Polling Data

A `Supplier<OrderCommand>` may poll an external source:

~~~java
@Bean
Supplier<OrderCommand> pollOrder(QueueClient queue) {
    return () -> queue.pollNext();
}
~~~

If `pollNext` blocks forever, the thread triggering the Supplier can hang indefinitely. Configure a poll timeout / long-poll duration on the source client and a deadline for the Supplier call. Never rely on an HTTP adapter timeout to replace the queue client's timeout.

Once a Supplier pulls a message and returns it, a caller cancelling later does not automatically return the message to the queue. Source visibility/lease/ack semantics govern recovery.

### 14.2. Functions Calling External Services

~~~java
@Bean
Function<OrderCommand, Mono<EnrichedOrder>> enrich(
        InventoryClient inventory) {
    return command -> inventory.lookup(command.sku())
            .timeout(Duration.ofSeconds(1))
            .map(stock -> new EnrichedOrder(command, stock));
}
~~~

Reactive Functions return a Publisher; adapters must subscribe and observe completion per contract. Timeout emits an error if inventory does not respond in time. If the inventory server already processed the call and the response was lost, retries require idempotency or genuinely read-only semantics.

### 14.3. Consumers Must Finish Side Effects Before Returning

~~~java
@Bean
Consumer<OrderCreated> saveOrder(OrderApplicationService service) {
    return service::handle;
}
~~~

With an imperative Consumer, `handle` must finish the transaction before returning if the binder relies on invocation completion to ACK. If the method merely launches async work and returns, the adapter may ACK before the DB commits.

With reactive consumers, use the signature and lifecycle supported by the binder; never self-subscribe and drop terminal signals.

### 14.4. Do Not Put a Timeout Inside a Pure Function Expecting to Interrupt Caller Loops

A pure CPU-bound calculation can run long, yet a caller's timeout does not automatically stop a Java loop. To bound CPU work, check a deadline or cancellation token per batch or chunk work rather than letting unbounded CPU loops starve workers.

## 15. Messaging: Processing Time and Visibility/Leases

A message broker may enforce visibility, lock, or delivery leases. If a consumer processes longer than that window, the broker may redeliver the message while the first consumer is still running.

~~~text
Broker delivers message to Consumer A
        |
        v
Consumer A takes 45 seconds in DB
        |
Visibility/lease expires after 30 seconds
        |
        v
Broker delivers same message to Consumer B
        |
        +-- A still running
        +-- B also processing
~~~

Both can execute side effects simultaneously. Inbox/unique constraints stop duplicate storage writes, yet contention and wasted work still consume resources.

### 15.1. Processing Budget Must Fit Within the Delivery Lease

Set the processing deadline comfortably shorter than the visibility/lease timeout to leave room for commit and ACK. If valid workloads take longer than the lease, use broker visibility/lease extension or heartbeats if supported, or switch to a stateful async job.

Do not assume every binder supports lease extension through one common API.

### 15.2. Kafka: Max Poll Interval and Consumer Liveness

In Kafka consumers, time between polls plus session/heartbeat timeouts affect group membership and rebalances. Processing a batch longer than limits such as `max.poll.interval.ms` can mark the consumer stalled and trigger partition reassignment.

Raising timeouts only masks certain long workloads; it does not replace bounded processing, pause/resume, controlled concurrency, and idempotency. Check the properties of your active Kafka client/binder.

### 15.3. RabbitMQ and Consumer Acknowledgement Timeouts

Rabbit consumers are affected by ACK timeouts, channel/connection limits, and requeues. Holding messages unacknowledged too long can cause the broker or client to close the channel depending on configuration/version and redeliver messages.

Check prefetch, concurrency, consumer timeouts, retries, and dead-letter policies. Never use a delivery tag as a business key.

### 15.4. Never ACK Merely Because the Caller Timed Out

If an application service times out with unclear DB state, never catch the error and return normally from the Consumer. If the transaction committed, the inbox makes redelivery a no-op; if it did not commit, the adapter needs the error to retry or route to DLQ per policy.

## 16. Serverless: Invocation Deadlines

Serverless runtimes usually cap execution time per invocation. Upon expiration, the platform may freeze/kill the runtime, abort execution, or reinvoke the event depending on the trigger. Semantics differ across cloud providers and event sources.

### 16.1. Use Remaining Time from the Runtime

A serverless adapter should query remaining execution time from the platform's context API (when available), then:
- Subtract cleanup and response reserve.
- Cap outbound HTTP/DB timeouts to remaining time.
- Avoid starting new retries once budget is spent.
- Persist job state if work must continue beyond the invocation.

Never hard-code fixed timeouts exceeding the runtime's invocation limit.

### 16.2. Invocation Timeouts Do Not Roll Back Remote Side Effects

~~~text
Serverless handler sends payment creation command
          |
          v
Payment provider accepts
          |
          v
Handler exceeds deadline; runtime stops it
          |
          v
Trigger reinvokes event
          |
          v
Payment command may be sent a second time
~~~

Use a stable provider idempotency key per operation, query payment state, and implement reconciliation. Never rely on in-memory state from a prior invocation to prevent duplicates.

### 16.3. Offload Long Work to Async Jobs

If work routinely approaches invocation limits, do not blindly crank timeouts to the maximum. Accept the event, persist a job/outbox row, return an accepted status, and let a worker with its own lifecycle process it; clients poll or subscribe by operation ID.

## 17. Combining Timeouts with Retries

Timeouts are often retriable, yet not every timeout is safe to retry. For read-only queries, retrying may fit. If an operation created a payment, order, or email, idempotency is mandatory before retrying.

### 17.1. Per-Attempt Timeout and Overall Deadline in Reactor

~~~java
Mono<PaymentResult> payment =
        Mono.defer(() -> paymentClient.charge(command))
            .timeout(Duration.ofMillis(700))
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .filter(error ->
                        error instanceof TimeoutException
                        || error instanceof TemporaryPaymentException))
            .timeout(Duration.ofSeconds(2));
~~~

Assuming `paymentClient.charge` returns a cold `Mono<PaymentResult>` and sends the same idempotency key inside `command`:

- The 700 ms timeout bounds each individual attempt.
- `Retry.backoff(2, ...)` allows up to two additional retries.
- The outer 2-second timeout bounds the entire sequence, including attempts and backoffs.
- `Mono.defer` builds a fresh call per subscription/retry if the client method constructs a fresh Publisher.
- If the provider received the command and the response timed out, the provider must support idempotency or the service must query state before resending.

Never add retry time endlessly beyond the deadline. The outer timeout can terminate the caller before the retry budget is spent.

### 17.2. Do Not Retry If Remaining Budget Is Too Low

Before each attempt, check remaining deadline. If only 50 ms remain while connect timeout alone is 200 ms, launching a new request only adds load and cannot finish in time.

Retry policies should:
- Cap attempt counts.
- Apply appropriate backoff and jitter.
- Respect the overall deadline.
- Never retry validation or conflict errors.
- Enforce idempotency on side-effecting calls.
- Leave budget for response/ACK.

### 17.3. Timeouts and Circuit Breakers

When a dependency is overloaded, immediate retries worsen the outage. A circuit breaker fails fast once error rates cross a threshold; concurrency limits and bulkheads prevent one dependency from exhausting all workers.

Timeouts cap wait time; circuit breakers decide whether to send requests at all. Both complement each other, yet neither replaces idempotency.

## 18. Timeouts After Side Effects: Outcomes May Be Unknown

A payment request can time out at multiple points:

~~~text
A. Before reaching the provider
   → Likely no side effect yet.

B. Provider received request, still processing
   → State is in progress.

C. Provider committed payment, response lost
   → Payment exists even though caller timed out.

D. Provider returned response, client dropped before reading
   → Caller does not know outcome.
~~~

You cannot tell A, B, C, and D apart solely from a caller-side `TimeoutException`.

### 18.1. Use a Stable Idempotency Key

Each operation should have a stable ID, e.g., `paymentOperationId`. Every retry reuses the same key; never mint a new UUID per attempt.

~~~text
charge(key=pay-901) → response timeout
charge(key=pay-901) → provider returns prior result
~~~

When the provider supports idempotency, verify key scope, retention window, and behavior when the same key arrives with a different payload. If unsupported, store operation state locally and query/reconcile by reference ID before resending.

### 18.2. Query State Before Deciding to Retry

~~~text
Timeout from payment provider
       |
       v
Query operationId
       |
       +-- SUCCEEDED → record success
       |
       +-- FAILED_FINAL → terminate as failed
       |
       +-- PROCESSING → wait/poll within deadline
       |
       +-- NOT_FOUND → may resend per policy
       |
       +-- UNKNOWN → keep state for reconciliation
~~~

`NOT_FOUND` is trustworthy only when the provider guarantees consistent read-after-write lookups. An eventually consistent system may not show a brand-new payment immediately; do not resend instantly just because the first lookup missed it.

### 18.3. Do Not Turn Timeouts into Definitive FAILED

If a caller times out while the provider may have committed, internal state should record `UNKNOWN` or `PENDING_RECONCILIATION` instead of `FAILED`. That prevents issuing compensating actions or duplicate charges based on false assumptions.

## 19. Cancellation and Compensation Are Different Mechanisms

Cancellation asks an in-flight task to stop. Compensation is a new business action restoring state after a previous side effect already took place.

Examples:
- Aborting an HTTP request awaiting response is cancellation.
- Issuing a refund after a payment captured is compensation.
- Cancelling a Reactor subscription does not trigger a refund.
- Rolling back a DB cannot unsend an email or broker message.

### 19.1. When Is Compensation Needed?

When a multi-step workflow cannot fit in one transaction:

~~~text
Create order
    |
    v
Reserve inventory
    |
    v
Charge payment
    |
    v
Confirm order
~~~

If payment succeeds and order confirmation fails, the workflow may need to release inventory or issue a refund. That is a saga/compensation dictated by business rules; a timeout is only a signal prompting state verification.

### 19.2. Compensation Can Also Time Out

A refund call can time out after the provider executed it. Compensation must carry its own operation ID / idempotency key, tracked state, and reconciliation—never retry blindly just because "it is an undo step."

### 19.3. Cancellation Does Not Replace Cleanup

When cancelling a task, still release local resources: connections, files, locks, subscriptions, and executor tasks. Use `try`-with-resources, `finally`, or cancellation hooks. Never hold resources indefinitely after the caller's deadline expired.




## 20. Inbound and Outbound HTTP Timeouts

### 20.1. Inbound Timeouts Do Not Automatically Bound Service Methods

An HTTP server or gateway may stop waiting for a response after a timeout. Yet the application thread or outbound call can keep running. Enforce a deadline at the request boundary and propagate remaining budget down to services and clients.

### 20.2. Outbound Timeouts Belong on the Outbound Client

If a Function calls `WebClient`, configure timeouts on `WebClient`/Reactor Netty. If using `RestClient`/`RestTemplate`, configure the request factory/client. If using an SDK, configure the SDK's timeouts. Never set only an inbound controller timeout expecting downstream clients to stop on their own.

### 20.3. Response Timeout Differs from Socket Inactivity Timeout

A client can have:
- Connection acquisition timeout.
- Connect timeout.
- TLS handshake timeout.
- Response/read timeout.
- Write timeout.
- Overall Publisher/request deadline.

Read each library property's exact semantics. A read timeout may cap silence between two read packets, not total server processing time.

## 21. Broker and Serverless Timeouts: Align the Limits

A consumer must keep processing duration within the delivery lease or visibility timeout. If a message redelivers while the first consumer is still running, two workers execute concurrently.

~~~text
Processing deadline < visibility/lease timeout
       |
       +-- room for commit
       +-- room for ACK
       +-- buffer for network jitter
~~~

When workloads can outlast the lease, extend visibility via heartbeats if the broker supports it, or hand off to durable background jobs. Never raise leases arbitrarily high, or crashed consumers delay redelivery too long.

In serverless runtimes, overall deadlines must stay under invocation limits while reserving cleanup/response time. When triggers retry, total executions include reinvocations; idempotency must cover all of them.

### 21.1. Deadlines and Broker Retries

Binder retries can produce multiple attempts within one delivery; broker redeliveries create new deliveries. Never count only application retries. Observability should separate Function attempts, broker delivery counts (when available), and serverless invocation counts.

### 21.2. Batch Processing

In batch messaging, allocate the overall deadline across records. If the last record exhausts the budget, the binder may retry the entire batch depending on semantics; committed records still need per-record idempotency. Use partial batch responses or checkpoints where supported.

## 22. Managing Threads and Connections Under Mass Timeouts

When a dependency slows down, timeouts returning errors to callers while background work keeps running cause **load leaks**: new requests keep arriving while old tasks remain stuck.

Monitor:
- Requests currently waiting on each dependency.
- Tasks that timed out yet are still executing.
- Thread pool active, queued, and rejected counts.
- Connection pool active, idle, and pending acquire counts.
- Long-running queries and lock waits.
- Cancellation requests vs. cancellations actually observed.
- Timeout rates per dependency and operation.

### 22.1. Bulkheads and Bounded Queues

Keep executors and pools bounded. When queues fill up, failing fast with an overload error beats accepting more work only for everything to time out. Isolate slow dependencies in separate bulkheads so they cannot exhaust all application threads and connections.

### 22.2. Never Create a New Executor per Request

Creating a thread pool per request leaves thread counts uncontrolled. Use lifecycle-managed executor beans with bounded workers/queues and clean shutdown hooks.

### 22.3. Timeouts Do Not Free Connections If the Driver Keeps Running

If a JDBC query times out at the HTTP layer while the driver continues executing, the connection stays occupied. Configure driver/database query and network timeouts, and verify connections return safely to the pool after errors.

## 23. Testing Timeouts and Cancellation

A thorough test verifies:
1. The caller received the timeout.
2. Cancellation was emitted.
3. Upstream observed cancellation.
4. Whether side effects occurred or not.

Asserting only `expectError(TimeoutException.class)` is insufficient when testing cancellation behavior.

### 23.1. StepVerifier Verifying Timeout Cancels Upstream

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutCancellationTest {

    @Test
    void timeoutCancelsUpstreamSubscription() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Mono<String> source = Mono.<String>never()
                .doOnCancel(() -> cancelled.set(true));

        StepVerifier.withVirtualTime(() ->
                    source.timeout(Duration.ofSeconds(2)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify();

        assertTrue(cancelled.get());
    }
}
~~~

`Mono.never` performs no real I/O, yet proves the `timeout` operator cancels upstream when the timer fires. This test **does not prove** a JDBC driver or remote server stopped.

### 23.2. Testing Explicit Subscriber Cancellation

~~~java
@Test
void subscriberCancellationReachesSource() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Mono<String> source = Mono.<String>never()
            .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
            .thenCancel()
            .verify();

    assertTrue(cancelled.get());
}
~~~

Here no timeout occurred; the subscriber cancelled explicitly. Track both cases separately in metrics because causes and responses differ.

### 23.3. Testing Bounded Timeout Retries

~~~java
@Test
void timeoutRetryStopsAtConfiguredAttempts() {
    AtomicInteger calls = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.<String>never();
    });

    StepVerifier.withVirtualTime(() ->
                source.timeout(Duration.ofSeconds(1))
                    .retryWhen(Retry.max(2)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectError()
            .verify();

    assertEquals(3, calls.get());
}
~~~

This test illustrates one initial call plus two retries. In real tests, include exception filters and overall deadlines; verify attempt counts, not just terminal state.

### 23.4. Testing WebClient with a Mock Server

Use MockWebServer, WireMock, or an HTTP test server to:
- Delay responses past the timeout.
- Drop connections mid-response.
- Respond right near the deadline.
- Return 5xx or 429 per policy.
- Verify request counts and idempotency keys across retries.

A client timeout test proves only that the client stopped waiting as configured. If the server already received the request, assert server-side side effects or status lookups; never assume the server stopped just because the socket closed.

### 23.5. Testing JDBC / Database Timeouts

In database integration tests, run a lock-waiting query or controlled long query with query/transaction timeouts configured, then verify:
- Exceptions propagate to the application.
- Transactions roll back per database/driver behavior.
- Connections return cleanly to the pool.
- No orphaned queries continue consuming resources unexpectedly.
- When commit state is ambiguous, query by operation key on a fresh connection.

A unit test mocking a repository to throw `TimeoutException` does not verify real JDBC driver behavior.

### 23.6. Testing Post-Commit Timeouts

Simulate:
1. Transaction writes data and commits.
2. Test harness drops response/ACK before the caller sees it.
3. Caller times out or broker redelivers.
4. Same operation ID is sent again.
5. Assert only one business effect exists and prior state is retrieved.

This test is crucial to prove timeouts do not cause duplicate side effects.

## 24. Observing Timeouts and Cancellation in Production

Distinguish caller timeouts, issued cancellations, and actual task completions.

Suggested metrics/fields:

| Metric / Field | Meaning |
|---|---|
| `request_deadline_remaining_ms` | Remaining budget at step start |
| `dependency_timeout_total` | Dependency timeout count |
| `operation_cancel_requested_total` | Cancellation requests emitted |
| `operation_cancel_observed_total` | Tasks/Publishers that observed cancellation |
| `operation_completed_after_caller_timeout_total` | Tasks finishing after caller already timed out |
| `outbound_inflight` | In-flight external calls |
| `executor_queue_depth` | Queued work in executor |
| `connection_pool_pending` | Requests waiting for connections |
| `db_query_duration` | Query execution duration |
| `message_processing_duration` | Message processing duration |
| `message_redelivery_total` | Redeliveries when reported by adapter |
| `timeout_after_commit_total` | Committed operations whose caller/ACK timed out when observable |

Metric names are application suggestions, not built-in Spring Cloud Function defaults.

### 24.1. Log Which Phase Timed Out

A log saying only `TimeoutException` is not enough for triage. Record operation, dependency, phase (`pool`/`connect`/`read`/`query`/`overall`), remaining deadline, attempt index, correlation ID, and commit state if known.

Never log tokens, sensitive payloads, or payment credentials. Use trace IDs to link hops without logging duplicate stack traces at every layer.

### 24.2. Alert on Resource-Exhaustion Signals

Rising timeouts combined with rising connection-pool waits, executor queues, and inflight outbound calls often indicate a slow dependency with stuck background tasks. If callers fail fast while tasks stay alive, the system keeps burning resources and timing out newer requests.

Track p95/p99 latency, tasks alive past deadline, slow queries, pool saturation, and cancellation-observed vs. cancellation-requested ratios.

## 25. A Monotonic-Clock Deadline Helper

When multiple steps share one budget, create a deadline object so each layer stops inventing fresh full timeouts.

~~~java
package example.functions;

import java.time.Duration;

public final class Deadline {

    private final long expiresAtNanos;

    private Deadline(long expiresAtNanos) {
        this.expiresAtNanos = expiresAtNanos;
    }

    public static Deadline after(Duration budget) {
        if (budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException(
                    "Budget must be positive");
        }
        return new Deadline(System.nanoTime() + budget.toNanos());
    }

    public Duration remaining() {
        long nanos = expiresAtNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0, nanos));
    }

    public boolean isExpired() {
        return remaining().isZero();
    }

    public Duration timeoutFor(
            Duration localCap, Duration responseReserve) {

        Duration usable = remaining().minus(responseReserve);

        if (usable.isNegative() || usable.isZero()) {
            throw new DeadlineExceededException();
        }

        return usable.compareTo(localCap) < 0
                ? usable
                : localCap;
    }
}
~~~

`DeadlineExceededException` is an application-defined exception. This helper is for **a single process** because it uses `System.nanoTime`. Never serialize `expiresAtNanos` to another service; monotonic clocks across processes have different origins.

### 25.1. Passing Deadlines Across Multiple Steps

~~~java
public Mono<PaymentResult> charge(
        PaymentCommand command, Deadline deadline) {

    Duration timeout = deadline.timeoutFor(
            Duration.ofMillis(700),
            Duration.ofMillis(100));

    return paymentClient.charge(command)
            .timeout(timeout);
}
~~~

Recompute remaining time before each outbound call. If earlier steps spent most of the budget, later steps automatically receive tighter timeouts or fail before starting.

### 25.2. Do Not Confuse a Per-Request Deadline with Default Timeout Config

A deadline is state for **one specific operation**. Never store a request deadline in a singleton field shared across requests; each invocation needs its own context. Never share mutable deadlines across independent messages.

## 26. Common Design Mistakes

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| Timeout only at API gateway | Downstream continues running | Propagate deadlines and configure outbound client timeouts |
| Assuming timeout means task stopped | Old tasks still hold threads/connections | Track cancellation and enforce driver timeouts |
| Calling `Future.cancel(true)` and assuming stopped | Blocking I/O may ignore interrupts | Use client/driver cancellation and query timeouts |
| Using `completeOnTimeout` for payments | Returns fallback while payment may commit | Use `UNKNOWN` state, idempotency, and lookup |
| Using `Mono.timeout` on Flux expecting total cap | May only detect idle gaps between items | Enforce overall deadline / duration semantics |
| Treating read timeout as overall deadline | Continuous streams can run indefinitely | Add an overall deadline |
| Retrying timeouts without idempotency | Creates duplicate side effects | Stable keys and storage/provider dedupe |
| DB transaction wrapping slow HTTP calls | Holds locks/connections, not atomic remotely | Outbox/saga or multi-step workflow |
| ACK before commit | Messages lost on DB rollback | Commit before ACK, inbox for redeliveries |
| Fire-and-forget inside Consumer | Binder ACKs before completion | Return/await completion per adapter contract |
| Identical timeouts at every step | Total time exceeds caller deadline | Allocate remaining budget |
| Stacked multi-layer retries | Calls and latency multiply unexpectedly | One primary retry owner and overall deadline |
| Unbounded executors | Threads/queues explode when dependency slows | Bulkheads, bounded queues, rejection |
| Flag-based cancel never checked by code | Cancellation has no effect | Cooperative token/interrupt checks |
| Treating cancel as rollback | Remote side effects may already have committed | Reconcile / compensate |
| Assuming transaction timeout covers all I/O | Drivers/sockets may still wait longer | Configure pool, connect, query, and network timeouts |

### 26.1. Anti-Pattern: Returning Fake Success on Timeout

~~~java
try {
    return paymentClient.charge(command);
} catch (TimeoutException ex) {
    return PaymentResult.success(command.operationId());
}
~~~

This turns "unknown outcome" into "success." If the provider never processed it, the system lies; if it did process, the outcome should be verified. Returning a meaningful `PENDING` or `UNKNOWN` status is far safer when supported by the API.

### 26.2. Anti-Pattern: Setting Timeouts Below Normal Processing Latency

Overly tight timeouts repeatedly cancel valid requests, driving up retries and load. Pick timeouts from latency distributions, SLAs, caller deadlines, and resource budgets; watch p95/p99 and timeout rates rather than picking a round number blindly.

### 26.3. Anti-Pattern: Raising Timeouts High to Hide Hung Dependencies

Very long timeouts pin connections, threads, and message leases. Investigate root causes, cap concurrency, and add circuit breakers or bulkheads where needed instead of raising timeouts just to silence alerts.

## 27. Pre-Production Checklist

### 27.1. Deadlines and Timeouts

- [ ] Overall deadline defined per operation/request.
- [ ] Per-step timeouts allocated from remaining budget.
- [ ] Budget reserved for commit, response, ACK, and cleanup.
- [ ] Connection pools, connect, read/write, query, and transaction limits configured.
- [ ] Retries/backoff fit within the overall deadline.
- [ ] Client-supplied deadlines validated and capped locally.

### 27.2. Cancellation

- [ ] Know which layer emits cancellation.
- [ ] Know how far clients, drivers, and Publishers actually honor cancel.
- [ ] Interrupts are never swallowed; blocking code cooperates.
- [ ] No fire-and-forget pretending invocation completed.
- [ ] Resources released cleanly on cancel or timeout.
- [ ] Metrics separate cancellation requested vs. observed.

### 27.3. Transactions and Side Effects

- [ ] Caller timeouts are never treated as proof of transaction rollback.
- [ ] Timeouts near commit have state-lookup paths.
- [ ] Side effects use stable idempotency keys.
- [ ] No DB transactions held open around slow remote calls.
- [ ] Broker ACKs occur only after completion/commit per binder contract.
- [ ] Compensations have their own operation keys and tracked state.
- [ ] Long-running tasks offloaded to durable async jobs when needed.

### 27.4. Testing and Operations

- [ ] Tested timeouts and cancellations separately.
- [ ] Tested per-attempt timeouts and overall deadlines.
- [ ] Tested client timeouts when the server already received the request.
- [ ] Tested query timeouts against a real database and driver.
- [ ] Tested commit followed by lost response/ACK.
- [ ] Tested message lease/visibility expiry while a consumer is still running.
- [ ] Monitored tasks still running after caller timeout.
- [ ] Tracked pool saturation, retries, redeliveries, and `UNKNOWN` operations.
- [ ] Tested shutdown and cleanup while tasks are being cancelled.

## 28. Practice Exercises

**Exercise 1 — Timeout or Deadline?** A request has a 2-second deadline and calls three dependencies sequentially, each with a 2-second timeout. Why can the request take nearly 6 seconds? Show how to allocate remaining budget.

**Exercise 2 — Future.cancel.** `future.get(1, SECONDS)` throws `TimeoutException`, then code calls `future.cancel(true)`. What is guaranteed and what is not?

**Exercise 3 — CompletableFuture.** Compare `orTimeout` and `completeOnTimeout`. Why does neither prove an external request stopped?

**Exercise 4 — Reactor Mono.** What signal does `Mono.timeout(Duration.ofSeconds(1))` emit if no result arrives? How far does cancellation propagate and where are its limits?

**Exercise 5 — Reactor Flux.** Why can `Flux.timeout(Duration)` behave as an idle timeout rather than an overall deadline? How does `take(Duration)` differ semantically?

**Exercise 6 — HTTP.** A `WebClient` has a connection pool timeout, connect timeout, response timeout, and an overall `Mono.timeout`. State each one's role.

**Exercise 7 — JDBC.** Why does Hikari's `connectionTimeout` not limit SQL execution time? Which other timeouts must be configured?

**Exercise 8 — Transactions.** An HTTP caller times out after 2 seconds while a DB query commits at second 3. What can the caller conclude? What must the system do when the request is resent?

**Exercise 9 — Retries.** A payment command times out after the provider already captured funds. Why is blindly retrying the command dangerous? Design idempotency/reconciliation.

**Exercise 10 — Deadline Propagation.** Service A spent 800 ms out of a 2-second deadline. Should Service B receive a 2-second timeout or remaining budget? Why is a response reserve needed?

**Exercise 11 — Supplier.** A Supplier polls a queue with a 20-second long poll while the invocation has only 3 seconds left. How must the poll step be bounded?

**Exercise 12 — Consumer.** A Consumer starts a `CompletableFuture` DB write and returns immediately. When might the binder ACK? How do you fix it?

**Exercise 13 — Message Leases.** Visibility timeout is 30 seconds, yet a consumer may take 45 seconds. Can two consumers run simultaneously? What mechanisms are needed?

**Exercise 14 — Serverless.** An invocation times out after a payment provider accepted the transaction. Why must the reinvocation reuse the old operation ID?

**Exercise 15 — Cancellation vs. Compensation.** Distinguish cancelling an HTTP request from refunding a captured payment. Why does the refund also need idempotency?

**Exercise 16 — StepVerifier.** Write a test confirming `timeout` emits `TimeoutException` and upstream receives cancel. Why does testing `Mono.never` not prove JDBC stopped?

**Exercise 17 — Metrics.** Propose metrics separating caller timeouts, cancellations requested, cancellations observed, and tasks completing after timeout.

**Exercise 18 — FunctionCatalog.** Why does composing `validate|calculate|charge` not automatically enforce an overall deadline? Where should deadlines be managed?

### Suggested Answers

- **Exercise 1:** Per-dependency timeouts add up sequentially; each step must receive remaining budget from the overall deadline.
- **Exercise 2:** The caller stops waiting and the `Future` receives a cancel request; the task stops only if it honors interrupts/cancellation. External I/O may continue.
- **Exercise 3:** `orTimeout` completes the future with a timeout error; `completeOnTimeout` completes with a fallback. Underlying work may continue.
- **Exercise 4:** `Mono` emits a timeout error and cancels the upstream subscription; adapters, drivers, and remote servers may not undo committed side effects.
- **Exercise 5:** Flux `timeout` typically measures gaps between signals; `take(Duration)` completes normally when the duration elapses rather than emitting a timeout error.
- **Exercise 6:** Pool timeout waits for a connection, connect timeout establishes TCP, response timeout governs reading responses per connector semantics, and `Mono.timeout` caps caller wait over the whole Publisher.
- **Exercise 7:** Hikari bounds pool borrowing; also configure driver connect/socket, statement/query, and transaction timeouts.
- **Exercise 8:** The caller knows only that its response timed out; the DB may have committed. Query by operation key or execute idempotently.
- **Exercise 9:** The provider may already have captured funds; reuse a stable idempotency key and query state before resending.
- **Exercise 10:** Pass remaining budget minus a response/cleanup reserve so total time stays within the original deadline.
- **Exercise 11:** Long-poll duration must be shorter than remaining budget leaving room for processing/response—or skip polling entirely.
- **Exercise 12:** The binder may see the Consumer return and ACK before DB completion. Await completion or use a binder-supported reactive/async contract.
- **Exercise 13:** Yes; the message can redeliver while the first consumer still runs. Extend leases/heartbeats or shorten processing, while keeping writes idempotent.
- **Exercise 14:** Reusing the operation ID lets the provider recognize the same command and return the prior result instead of charging twice.
- **Exercise 15:** Cancel requests stopping an in-flight task; refund is a new compensating side effect. Refunds can time out and retry, so they need their own key.
- **Exercise 16:** Use `doOnCancel` and `StepVerifier` virtual time; `Mono.never` verifies only operator/Publisher cancellation, not real drivers.
- **Exercise 17:** Measure `timeout_total`, `cancel_requested_total`, `cancel_observed_total`, `task_completed_after_timeout_total`, and `outbound_inflight`.
- **Exercise 18:** `FunctionCatalog` only composes functions; application workflows / adapter deadline contexts manage overall deadlines and per-client timeouts.

## 29. Key Takeaways

- Timeout, deadline, cancellation, and completion are distinct concepts.
- A caller-side timeout **does not prove** underlying tasks stopped or transactions rolled back.
- Use an overall deadline and propagate remaining budget; per-step timeouts must stay inside the shared budget.
- `Future.cancel(true)` and `CompletableFuture.orTimeout` do not guarantee external I/O is cancelled.
- Reactor `timeout` emits an error and sends cancellation upstream; adapters, drivers, and remote servers must support it to stop real work.
- Distinguish connection-pool, connect, response/read/write, query, and transaction timeouts.
- Enforce timeouts at the right boundaries in `WebClient`, JDBC/drivers, brokers, and serverless handlers; `FunctionCatalog` does not manage deadlines automatically.
- For side effects with unclear post-timeout state, use idempotency keys, state queries, and reconciliation—never blind retries.
- Cancellation requests stopping work; compensation is a new business action restoring state.
- Test timeouts, cancellations, commits after timeout, broker redeliveries, and tasks lingering past deadlines; observe both cancellation requests and observed cancellations.


