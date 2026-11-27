# Interrupt Limitations and HTTP Tasks Continuing After Timeout

A timeout limits how long the caller waits for an operation to finish. However, when TimeLimiter expires, that does not automatically prove the running work has stopped. A Future may receive a cancel request, a thread may receive an interrupt signal, the HTTP client may cancel the exchange, yet the remote service may still continue processing the received request.

In Spring Cloud CircuitBreaker with Resilience4j, you must distinguish three events: the caller receiving a timeout, the application-side task being requested to cancel, and server-side processing actually stopping. These three events are related, not synonymous. If timeouts are handled only at the Circuit Breaker layer without understanding the cancellation mechanisms of the HTTP client and background tasks, the application may keep consuming threads, connections, and resources after returning an error to the caller.

## 1. Timeout limits wait time, not a guarantee to stop work

Suppose the order service calls the inventory service. The caller sets a two-second timeout. The inventory service responds after eight seconds.

After two seconds, the caller can receive a timeout and switch to a fallback. Yet the sent request may still be processing on the inventory service. If the client side is running a blocking task on a thread pool, that task may also keep running if it does not receive or react to a cancel signal.

There are three layers to distinguish:

| Layer | What happens when timeout expires | What is not guaranteed |
|---|---|---|
| Caller | Stops waiting and receives a timeout error or fallback | Underlying work has stopped |
| Application task | May receive a cancel or interrupt request | Code has reacted to the interrupt and exited |
| HTTP client/server | Client may cancel the exchange or close the request | Server has received the cancel signal and stopped processing |

A timeout is a time limit on the result-observing side. To genuinely release resources, tasks, HTTP client, and server all need to be designed to support cancellation.

## 2. TimeLimiter and the cancelRunningFuture property

Resilience4j TimeLimiter limits how long to wait for a Future or CompletionStage to finish. The cancelRunningFuture property controls whether TimeLimiter requests canceling the running Future on timeout.

Example configuration:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

Meaning:

- timeoutDuration sets the wait time limit to two seconds.
- cancelRunningFuture: true requests canceling the Future on timeout.
- If set to false, TimeLimiter does not request canceling the running Future on timeout; the task may continue until it finishes on its own or is canceled elsewhere.

When using Spring Cloud CircuitBreaker with Resilience4j, TimeLimiter configuration is typically bound to the corresponding instance ID. Ensure the name inventory in code matches inventory in application.yml, and confirm that the adapter and API style in use actually apply TimeLimiter.

Cancellation configuration is a request sent to the Future mechanism, not a guarantee that all downstream work stops. The outcome depends on the Future type, executor, HTTP library, and how the task handles cancellation.

## 3. Future.cancel(true) and the meaning of interrupt

For a standard Future created by ExecutorService, calling cancel(true) can request that the thread executing the task receive an interrupt signal. If the task has not started yet, it may be prevented from running. If the task is running, stopping depends on the code and APIs the task is using.

Example of a task that can react to interrupts:

~~~java
Future<Inventory> future = executor.submit(() -> {
    try {
        return inventoryClient.fetchBlocking("SKU-001");
    } catch (InterruptedException error) {
        Thread.currentThread().interrupt();
        throw error;
    }
});
~~~

If the executing thread is waiting in an operation that throws InterruptedException, the task can stop and propagate the error to the caller. Restoring the interrupt flag via Thread.currentThread().interrupt() preserves the signal so higher layers can observe it.

Interruption in Java is a cooperative signaling mechanism. It does not force the JVM to terminate arbitrary code. A task only stops promptly when code actively checks or reacts to the interrupt signal.

Ways code reacts to interrupts:

- Calling blocking APIs with a contract to throw InterruptedException.
- Checking Thread.currentThread().isInterrupted() at safe points.
- Stopping loops or computation when an interrupt is detected.
- Releasing resources in finally or try-with-resources.
- Never swallowing InterruptedException and continuing to run as normal.

If code catches InterruptedException without stopping and without restoring the interrupt flag, the cancel request may be ignored.

## 4. Why CompletableFuture.cancel(true) does not guarantee thread interruption

Not every Future has the same cancellation behavior. CompletableFuture has different cancellation semantics from FutureTask or Futures created by ExecutorService.submit.

Per Java's CompletableFuture contract, the mayInterruptIfRunning parameter of cancel is not used to control computation execution. CompletableFuture does not necessarily own the thread executing the task, so cancel(true) primarily completes the CompletableFuture in a canceled state and does not guarantee interrupting the thread executing the computation.

Example:

~~~java
CompletableFuture<Inventory> future =
        CompletableFuture.supplyAsync(
                () -> inventoryClient.fetchBlocking("SKU-001"),
                executor
        );

future.cancel(true);
~~~

Calling cancel may transition the CompletableFuture to the canceled state. However, the task running via supplyAsync may keep executing in the executor. Do not treat cancel(true) on a CompletableFuture as a reliable way to interrupt a blocking HTTP call.

Comparison:

| Task type | Behavior on cancel(true) |
|---|---|
| Running FutureTask | Can interrupt the executing thread |
| Future from ExecutorService | Typically requests canceling the task and interrupts if running |
| CompletableFuture.supplyAsync | Does not guarantee interrupting the running computation |
| CompletionStage returned by HTTP client | Depends on the implementation and client's cancellation propagation |
| Reactor Mono/Flux | Sends cancel signal upstream; actual effect depends on publisher and transport |

Therefore, when using TimeLimiter with CompletionStage, determine which library created that CompletionStage and whether cancellation propagates to the background task. Simply seeing cancelRunningFuture: true in YAML is not enough to conclude that the HTTP thread has stopped.

## 5. Example using TimeLimiter with an interruptible Future

For a blocking task executed via ExecutorService, you can use TimeLimiter to bound Future wait time:

~~~java
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import io.github.resilience4j.timelimiter.TimeLimiter;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

public class InventoryService {

    private final ExecutorService executor =
            Executors.newFixedThreadPool(10);

    private final TimeLimiter timeLimiter = TimeLimiter.of(
            TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(2))
                    .cancelRunningFuture(true)
                    .build()
    );

    private final BlockingInventoryClient inventoryClient;

    public InventoryService(BlockingInventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public Inventory fetch(String sku) throws Exception {
        return timeLimiter.executeFutureSupplier(() ->
                executor.submit(() -> inventoryClient.fetch(sku))
        );
    }
}
~~~

This example assumes fetch can react to interrupts or the client has an appropriate cancellation mechanism. The executor should be lifecycle-managed by the application, such as declared as a bean and shut down when the application stops; do not create a new thread pool per request.

If fetch is waiting inside an HTTP library that does not respond to interrupts, the Future may transition to canceled while the thread or I/O activity does not terminate right away. Therefore, configure timeouts on the HTTP client itself and verify the cancellation behavior of the library in use.

## 6. How can an HTTP task keep running after timeout?

An HTTP request goes through multiple stages:

~~~mermaid
sequenceDiagram
    participant Caller
    participant TimeLimiter
    participant HttpClient
    participant Server
    Caller->>TimeLimiter: Start call
    TimeLimiter->>HttpClient: Send HTTP request
    HttpClient->>Server: Request arrives at server
    Note over Server: Server begins processing
    TimeLimiter-->>Caller: Timeout after 2 seconds
    Note over Caller: Caller runs fallback or returns error
    Note over HttpClient,Server: Request may still be processing
    Server-->>HttpClient: Late response arrives
~~~

A caller-side timeout does not necessarily recall a request already sent over the network. Once the server has received the request, the server may continue:

- Running database queries.
- Calling additional dependent services.
- Writing data or updating transaction state.
- Completing a business operation even after the client closed the connection.

Even if the HTTP client cancels the request or closes the connection, the server is not forced to stop work immediately. The server may not have detected the client disconnect yet, or business logic may not check connection state during processing.

Thus, a timeout is not a rollback mechanism. If a request to create an order or execute payment was already accepted by the server, the caller receiving a timeout does not mean the operation failed. Retrying immediately can create duplicate transactions if the first attempt was already processed.

## 7. HTTP client cancellation and limits of disconnecting

Cancellation capability depends on the HTTP client:

- An asynchronous client may provide a handle or Future representing the request and allow canceling the exchange.
- A reactive client may react to a cancel signal by releasing the subscription, canceling the exchange, or closing transport resources.
- A blocking client may not stop immediately when the thread is interrupted, depending on I/O APIs and socket configuration.
- An HTTP request that already reached the server may continue processing even though the client no longer waits for the response.

With WebClient and Reactor Netty, the cancel signal from the subscriber can be propagated down to the HTTP exchange publisher to cancel or release client activity. However, test with your actual Reactor Netty version and connection pool configuration. Do not assume the server definitely stops processing just because the Mono was canceled.

You can set timeouts on the HTTP client to bound individual stages:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

In this example:

- Connect timeout limits the time to establish a connection.
- Reactor Netty's response timeout limits the wait interval for the response per client policy.
- An overall request timeout can also be added using the timeout operator in the pipeline.

These timeouts address different stages. Check your HTTP client version's documentation to know exactly when response timeout starts measuring and whether it includes reading the entire body. If you need to bound body read time, an extra read timeout or publisher-level deadline may be needed.

## 8. Combining TimeLimiter, Circuit Breaker, and HTTP timeouts

The three mechanisms have distinct roles:

- HTTP client timeout limits wait times at the connection or response layer.
- TimeLimiter limits how long the caller waits for a Future or CompletionStage.
- Circuit Breaker observes outcomes and prevents new calls when the dependency shows signs of instability.

Example configuration:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 3s
        cancelRunningFuture: true
~~~

Here, TimeLimiter bounds the overall call at three seconds. The HTTP client might have a one-second connect timeout and a two-second response timeout. Circuit Breaker records the corresponding timeouts or errors if they pass through the protected publisher/Future and are not configured to be ignored.

Deadlines must be designed in a sensible order. If the HTTP client can wait longer than TimeLimiter, TimeLimiter may expire first while I/O is still running. If the HTTP timeout is shorter than TimeLimiter, the client has a chance to end its operation and release the connection before the caller hits the overall deadline.

An example with Spring Cloud CircuitBreaker and CompletionStage:

~~~java
import java.util.concurrent.CompletionStage;

import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;

public class InventoryClient {

    private final CircuitBreaker inventoryBreaker;
    private final AsyncInventoryHttpClient httpClient;

    public InventoryClient(
            CircuitBreakerFactory<?, ?> factory,
            AsyncInventoryHttpClient httpClient) {
        this.inventoryBreaker = factory.create("inventory");
        this.httpClient = httpClient;
    }

    public CompletionStage<Inventory> find(String sku) {
        return inventoryBreaker.run(
                () -> httpClient.fetch(sku),
                error -> Inventory.unavailable(sku)
        );
    }
}
~~~

TimeLimiter configuration for the inventory instance may be applied by the Resilience4j adapter depending on the version and how the breaker is created. Verify whether the adapter wraps the CompletionStage with TimeLimiter and whether cancellation propagates to the HTTP client. If the HTTP client returns a CompletableFuture, canceling the Future does not automatically interrupt threads or cancel the exchange; inspect the client's own cancellation API.

## 9. Overall deadline and avoiding retries that double work

A per-call timeout is not the same as the overall business deadline. Suppose:

- Each HTTP call has a two-second timeout.
- Retry allows one additional attempt.
- Wait interval between the two attempts is 200 milliseconds.
- Fallback needs another 100 milliseconds.

Total time can exceed four seconds. If the upstream request only allows three seconds, the caller may time out before the retry chain finishes.

Besides time, retries can also cause the server to keep executing multiple old requests. For example, the first attempt timed out on the client while the server still created the order; retrying the exact same request a second time can create another order.

For operations with side effects:

- Use a stable idempotency key for the same business operation.
- Persist request or transaction status so the caller can look up the outcome after a timeout.
- Design server APIs to recognize duplicate requests.
- Cap retry counts and the overall deadline.
- Do not retry blindly without knowing whether the previous request was already processed by the server.

A timeout only states that the caller did not receive a result within the deadline. It does not prove the server has not executed the business action.

## 10. How to design tasks to react to interrupts

If the application manages blocking tasks itself, code should react to interrupts intentionally.

Example of a signal-checking loop:

~~~java
public Inventory fetchWithPolling(String sku) throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        Inventory inventory = tryFetch(sku);

        if (inventory != null) {
            return inventory;
        }

        Thread.sleep(100);
    }

    throw new InterruptedException("Inventory lookup interrupted");
}
~~~

When the thread receives an interrupt during Thread.sleep, the method throws InterruptedException. The task can terminate and release resources. If a method catches the exception at one layer and cannot rethrow it, restore the interrupt flag:

~~~java
try {
    performBlockingOperation();
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    cleanup();
    return;
}
~~~

Avoid busy-waiting loops to repeatedly poll interrupt status. Use interruptible blocking APIs or appropriate waiting mechanisms. For HTTP operations, prefer client APIs with explicit cancellation and transport timeouts rather than relying solely on thread interrupts.

## 11. Observing work still running after timeout

To verify whether timeouts actually free resources, observe both the caller and background tasks:

- Number of timeouts returned to callers.
- Number of Futures requested to cancel.
- Number of tasks that actually terminated after receiving cancellation.
- Number of active threads in the executor and waiting queue size.
- Number of in-use connections and pending connections.
- Time elapsed between timeout and background task completion.
- Number of requests the server continues processing after the client disconnected.
- Retry rate and detected duplicate-operation rate.

You can add logs tagged with correlation ID and operation ID on both client and server. When the caller times out, log the timestamp and ID. When the server finishes processing, log the same ID. Those two timestamps reveal whether work continued running after timeout.

Do not look solely at TimeLimiter timeout metrics and conclude resources were released. Cross-check against active tasks, thread pools, connection pools, and server-side logs.

## 12. Testing cancellation behavior

A good test should create a simulated endpoint that takes longer than the timeout. For example, an endpoint waiting five seconds while the client times out after two seconds.

Check the following points:

1. The caller receives a timeout or fallback after the configured duration.
2. Whether the Future receives a cancel request.
3. Whether the executing thread receives an interrupt.
4. Whether the blocking task terminates early or keeps running to completion.
5. Whether the HTTP client closes or cancels the exchange.
6. Whether the server detects client disconnect and stops processing.
7. Whether the executor and connection pool return to normal after load testing.
8. Whether retries cause duplicate requests or duplicate side effects.

Run tests with both FutureTask and CompletableFuture to see the differences in cancellation behavior. For HTTP clients, test against the exact implementation and production version in use; behavior of mocks or other clients may not represent real transport behavior.

## 13. Common mistakes

- **Assuming timeout means the task stopped**: timeout only ends the caller's wait.
- **Assuming cancel(true) always interrupts the thread**: CompletableFuture does not guarantee interrupting the computation.
- **Swallowing InterruptedException**: the task may continue running despite receiving a cancellation signal.
- **Setting only TimeLimiter without HTTP timeouts**: I/O operations may keep consuming resources after the caller has timed out.
- **Assuming closing the connection makes the server roll back**: the server may have already executed side effects before the client disconnected.
- **Retrying immediately after timeout without idempotency**: can create duplicate transactions.
- **Creating a new executor per request**: thread pools grow unchecked and are hard to clean up.
- **Not monitoring background tasks**: dashboards only show caller timeouts without revealing that workers are still active.
- **Using one timeout across all layers**: connect, response, read, and overall deadline have different purposes.
- **Believing all HTTP clients support cancellation identically**: you must verify the contract and behavior of the actual client.

## 14. Configuration and implementation workflow

When using TimeLimiter to protect HTTP calls in Spring Cloud CircuitBreaker, you can follow this sequence:

1. Determine the overall deadline acceptable to the caller.
2. Set appropriate connect timeout, response timeout, and read timeout for the HTTP client.
3. Configure TimeLimiter's timeoutDuration based on the call's remaining deadline.
4. Set cancelRunningFuture: true if you want to request canceling the Future on timeout.
5. Identify what Future or CompletionStage type the HTTP client returns and check whether cancellation propagates to the transport.
6. If using blocking tasks, ensure code reacts to interrupts and releases resources.
7. With reactive publishers, check whether cancel signals propagate to the HTTP exchange and understand server limits when a client disconnects.
8. Design idempotency and status-lookup mechanisms for operations with side effects.
9. Monitor tasks still running after timeout, active threads, connection pools, and actual completion times.
10. Test timeout, cancellation, fallback, and retries under slow-dependency conditions.

TimeLimiter helps limit how long the caller waits for a result and can request Future cancellation via cancelRunningFuture. Interrupts are cooperative signals; CompletableFuture does not guarantee interrupting computations; an HTTP client can cancel an exchange yet the server may still keep processing a received request. By combining TimeLimiter timeouts, HTTP client timeouts, verifiable cancellation, and server-side idempotency, an application reduces leftover work and limits the impact of slow dependencies after the caller has timed out.
