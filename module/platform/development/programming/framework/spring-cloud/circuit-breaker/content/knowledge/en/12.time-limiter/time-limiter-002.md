# timeoutDuration and cancelRunningFuture

In Spring Cloud CircuitBreaker's integration with Resilience4j, TimeLimiter bounds the wait time of a protected operation. The two most important properties are **timeoutDuration** and **cancelRunningFuture**. The first sets the maximum deadline the application waits for a result; the second decides whether TimeLimiter requests canceling the running Future when the deadline is exceeded.

These two properties solve two different problems. Expiring a wait time lets the current request continue via a fallback, but that does not mean the underlying task has stopped. Understanding the difference between timeout and cancellation helps avoid holding resources too long, avoid sending retries while an old task is still running, and choose deadlines aligned with the system's latency budget.

## 1. What is timeoutDuration?

**timeoutDuration** is the maximum duration TimeLimiter allows a protected operation to complete before raising a timeout. In Resilience4j, this value is represented as a **java.time.Duration**. In YAML configuration, human-readable duration formats such as **2s**, **500ms**, or **1m** can be used.

For example, if **timeoutDuration** is set to two seconds, the application waits for the result within that deadline. If the operation has not completed yet, TimeLimiter signals a timeout so the calling layer can handle the error or run a fallback.

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

In the example, the TimeLimiter instance named **inventory** sets a two-second wait deadline. The instance name must match the Circuit Breaker ID created by the application, such as **create("inventory")**, when using ID-based Spring Cloud CircuitBreaker configuration.

Timeout is a wait-time limit for the operation within the integration scope. It does not automatically set all timeouts at the network or database layer. The HTTP client still needs appropriate connect and response/read timeouts; the JDBC or database driver still needs query execution limits. Those lower-layer limits ensure the I/O operation actually finishes rather than merely making the calling request stop waiting.

## 2. What does the application receive when a timeout occurs?

When the operation does not complete within the deadline, TimeLimiter raises a timeout error, typically represented as **java.util.concurrent.TimeoutException** in the synchronous execution path. With Spring Cloud CircuitBreaker, this error is passed to the call's fallback function if the application provides one.

~~~java
import java.util.concurrent.TimeoutException;

import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;

    InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient,
            InventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
    }

    Stock getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> {
                if (error instanceof TimeoutException) {
                    log.warn("Inventory call timed out, sku={}", sku);
                    return inventoryCache.findBySku(sku)
                        .orElseThrow(() ->
                            new InventoryUnavailableException(sku, error)
                        );
                }

                log.warn("Failed to get inventory, sku={}", sku, error);
                return inventoryCache.findBySku(sku)
                    .orElseThrow(() ->
                        new InventoryUnavailableException(sku, error)
                    );
            }
        );
    }
}
~~~

The example uses a cache when the stock lookup operation times out. If the cache has no data, the application throws a business exception so the API layer can return an appropriate response. Do not return a quantity of 0 just to avoid an error if 0 means stock was checked and is genuinely out of stock.

Depending on the version and integration layer, the timeout exception may be wrapped in another exception. When classifying errors in a fallback, also inspect the root cause via **getCause()** if needed. Log the Circuit Breaker name, error type, and trace identifier to distinguish timeouts from calls rejected due to the OPEN state.

## 3. What does cancelRunningFuture control?

**cancelRunningFuture** is the flag that indicates whether TimeLimiter requests canceling the running Future after a timeout.

| Value | Behavior when timeout expires | Consequences to note |
|---|---|---|
| **true** | TimeLimiter requests canceling the running Future. | Can release work or resources sooner if the task supports cancellation. |
| **false** | TimeLimiter does not request canceling the running Future. | The task may keep running even though the caller already received a timeout or fallback. |

Example enabling cancellation:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

Example without requesting cancellation:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      report-generation:
        timeoutDuration: 5s
        cancelRunningFuture: false
~~~

With **true**, TimeLimiter attempts to cancel the Future when the deadline expires. With **false**, it stops waiting according to the time limit but lets the Future continue under its execution mechanism. Which choice fits depends on the nature of the work: a read operation that can be safely canceled, or a write task that has already started and must finish according to business workflow.

Importantly, cancellation is a request to cancel, not a guarantee to forcibly stop all code. Actual stopping capability depends on the Future type, executor, client library, and whether the task responds to cancellation signals.

## 4. Canceling a Future does not guarantee stopping the I/O operation

For a Future that supports interruption, canceling can often request interrupting the executing thread. However, the thread only stops cleanly when the underlying code and library cooperate with interrupts or provide their own cancellation mechanism.

Common situations include:

- A Java task that checks interrupt status and exits cleanly can stop early.
- An HTTP call waiting on a socket may require connect/read timeouts or the HTTP client's request cancellation API to release resources.
- A database query may continue on the database server if the driver does not send a cancel command or the server does not process it.
- A request that has already reached a remote service may continue being processed on the server even though the client stopped waiting or closed the connection.

In particular, **CompletableFuture.cancel(true)** does not guarantee that the thread executing the underlying task is interrupted. **CompletableFuture** manages the completion state of a computation; the **mayInterruptIfRunning** parameter is not a mechanism for forcibly halting computation as many people assume from traditional Futures.

Therefore, treat **cancelRunningFuture: true** as a caller-side effort to cancel work. To bound actual execution time, configure timeouts on the client, driver, or target service. For write operations such as creating a transaction or reserving stock, add an idempotency key or status lookup mechanism to handle cases where the caller times out while the server already completed the operation.

## 5. Configuring TimeLimiter in Java

You can configure TimeLimiter directly via **TimeLimiterConfig** and pass it into the Spring Cloud CircuitBreaker Resilience4j builder.

~~~java
import java.time.Duration;

import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryTimeLimiterConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryTimeLimiter() {
        TimeLimiterConfig timeLimiterConfig =
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(2))
                .cancelRunningFuture(true)
                .build();

        return factory -> factory.configure(
            builder -> builder.timeLimiterConfig(timeLimiterConfig),
            "inventory"
        );
    }
}
~~~

In this example:

- **timeoutDuration(Duration.ofSeconds(2))** sets a two-second deadline.
- **cancelRunningFuture(true)** requests canceling the Future on timeout.
- **configure(..., "inventory")** applies the configuration to the Circuit Breaker with ID **inventory**.

If a default policy is needed across multiple IDs, you can use **configureDefault** and construct a **Resilience4JConfigBuilder** per ID. When using both YAML and a Java Customizer simultaneously, understand the precedence order of your Spring Cloud/Resilience4j version. Avoid declaring the same parameters in multiple places without knowing which configuration source takes effect.

## 6. Choosing timeoutDuration based on latency budget

Do not pick a timeout as an arbitrary number. Start from the response time promised by the external API, then divide the budget across processing steps and dependencies.

Example of an order API with a three-second response budget:

| Component | Illustrative budget |
|---|---:|
| Validation and business logic in service | 300 ms |
| Calling Inventory | 900 ms |
| Calling Pricing | 700 ms |
| Calling Payment | 800 ms |
| Buffer for serialization and network | 300 ms |
| **Total** | **3,000 ms** |

In this example, the TimeLimiter for Inventory can be set around 900 ms if the flow is sequential and the remainder is needed for other steps. If calls run in parallel, the budget must be calculated based on overall wait time and how Publishers/Futures are combined. Do not mechanically sum durations when tasks actually run concurrently.

Considerations:

- Normal latency and high-percentile latency (p95, p99) of the dependency.
- Response budget of the API calling it.
- Time for connect, TLS handshake, sending the request, and receiving the response.
- Retry time if applicable; retries must fit inside the total budget.
- Time needed for fallback and returning the response to the caller.

If the timeout is too short relative to normal latency, the application produces false timeouts and may open the Circuit Breaker even when the dependency is healthy. If the timeout is too long, threads, connections, and request contexts can be held for a long time, reducing serving capacity under load.

## 7. Distinguishing TimeLimiter timeout from Circuit Breaker slow calls

TimeLimiter and Circuit Breaker both care about time, but serve different roles:

- **TimeLimiter** limits the wait time for a single execution.
- **Circuit Breaker** observes outcomes and slowness across multiple calls in a sliding window to decide state transitions.

Circuit Breaker can configure **slowCallDurationThreshold** and **slowCallRateThreshold**. A call exceeding the slow-call threshold can be recorded as a slow call even if it has not timed out. If a call exceeds **timeoutDuration**, TimeLimiter stops waiting and raises a timeout error.

Example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        slowCallDurationThreshold: 700ms
        slowCallRateThreshold: 50
        failureRateThreshold: 50
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

Here, a call taking 900 ms exceeds the 700 ms slow call threshold without hitting the two-second timeout. Circuit Breaker can record it as a slow call. If the call lasts longer than two seconds, TimeLimiter signals a timeout. Whether a timeout counts as a failure in Circuit Breaker depends on the integration and exception recording configuration.

Do not unintentionally set the timeout shorter than the slow call threshold. If TimeLimiter terminates a call at 500 ms while **slowCallDurationThreshold** is one second, Circuit Breaker may only see timeout exceptions instead of slow calls having enough time to be classified. Choose thresholds according to measurement goals: TimeLimiter protects the request's budget; slow-call thresholds detect latency degradation trends.

## 8. Timeouts and retries must be coordinated

Retries can increase call volume and extend total processing time. If each attempt has a two-second timeout and the application tries three times sequentially, total time can exceed six seconds, not counting backoff intervals between attempts.

Some principles:

- Set a per-attempt timeout and cap total duration across the entire retry chain.
- Only retry recoverable errors, such as certain transient connection errors.
- Do not retry indefinitely or keep retrying when the Circuit Breaker is already OPEN.
- For write operations, use idempotency keys or duplicate-processing guards.
- Avoid letting an old call keep running after timeout while a retry has already started a new call.

When **cancelRunningFuture** is **false**, the old task may keep running after the caller times out. Retrying immediately can cause two operations to execute concurrently. Even when **true** is enabled, you must still verify whether the client actually stops the old request.

## 9. TimeLimiter in reactive calls

In WebFlux applications, calls typically return a **Mono** or **Flux**, and time limiting can be expressed directly in the reactive pipeline using the **timeout** operator. Spring Cloud CircuitBreaker provides a corresponding reactive factory to wrap Publishers and handle fallbacks.

~~~java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    ReactiveInventoryService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            ReactiveInventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Mono<Stock> getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            inventoryClient.getStock(sku)
                .timeout(Duration.ofSeconds(2)),
            error -> Mono.just(Stock.unavailable(sku))
        );
    }
}
~~~

In the example, Reactor's **timeout** operator emits an error if the Publisher does not emit the required signal within the deadline. A reactive subscription can be canceled on timeout or when the subscriber cancels. This is Reactive Streams cancellation, different from canceling a Future in a blocking API.

Do not assume that **cancelRunningFuture** has the same effect for every reactive client. With WebClient, subscription cancellation is normally propagated down to the connector to cancel or close the request if the connector supports it. The remote service may still have received and continued processing the request. Verify client/connector behavior and set HTTP-layer timeouts when network time limits are needed.

If the **timeout** operator is used before the Circuit Breaker, the timeout error is inside the protected Publisher and can be recorded by the breaker. If you recover with **onErrorResume** before passing the Publisher into the Circuit Breaker, the breaker may only observe a successful fallback outcome. The placement of timeout and fallback therefore affects metrics.

## 10. Observing and verifying timeouts

To know whether timeouts are protecting the application effectively, monitor both timeout counts and execution resource health.

| Signal | What to observe |
|---|---|
| Timeouts per Circuit Breaker ID | Which dependency frequently exceeds deadlines |
| p50, p95, and p99 latency | Whether timeouts fit the actual latency distribution |
| Canceled Futures or continuing tasks | Whether cancellation is actually freeing work |
| Active threads and executor queue | Whether slow tasks are exhausting the executor |
| In-use HTTP connections | Whether request timeouts release connection pool slots |
| Fallback count | How heavily the application relies on fallback data |
| Circuit Breaker state | Whether timeouts contribute to the breaker transitioning to OPEN |

You can verify with a test dependency whose response time is controllable:

1. Call an endpoint responding in 300 ms with a two-second timeout; the request should complete normally.
2. Call an endpoint responding in three seconds with a two-second timeout; the caller should receive a timeout or fallback before a normal result arrives.
3. Enable **cancelRunningFuture: true**, observe logs and threads to see if the task reacts to cancellation.
4. Repeat with **false** to compare whether the task keeps running after the caller times out.
5. Check the connection pool, executor, and target service state to determine whether resources are genuinely freed.

Do not rely solely on when the caller receives a fallback to conclude that the operation stopped. Observe both the client side and the dependency. Especially for write operations, inspect data state to see whether the server completed the work after the client timed out.

## 11. Common configuration mistakes

1. **Setting the timeout too low.** Valid calls time out, fallbacks spike, and the Circuit Breaker can open due to artificial errors.
2. **Setting the timeout too high.** Requests hold threads or connections for too long, reducing throughput when the dependency degrades.
3. **Assuming cancelRunningFuture=true definitely stops the remote request.** Canceling a Future is a caller-side effort; client and server must support actual stopping.
4. **Setting cancelRunningFuture=false yet retrying immediately.** The old task can continue running concurrently with the new attempt.
5. **Using only TimeLimiter while omitting HTTP client or database timeouts.** Underlying I/O can continue consuming resources after the caller times out.
6. **Failing to distinguish timeout from Circuit Breaker OPEN.** A timeout is an allowed operation that exceeded the deadline; **CallNotPermittedException** is a call rejected by the breaker.
7. **Ignoring slow-call thresholds.** TimeLimiter and Circuit Breaker may evaluate latency against two different thresholds.
8. **Not handling write-operation uncertainty.** A caller timeout does not prove the server has not executed the operation; idempotency or status lookup is needed.

## 12. Hands-on scenario

An order application calls Inventory to read stock quantities. The operations team sets **timeoutDuration = 2s** and **cancelRunningFuture = true**.

Progression:

1. A stock read request completes in 500 ms. TimeLimiter does not intervene and the response is returned normally.
2. Another request takes longer than two seconds. TimeLimiter signals a timeout; Spring Cloud CircuitBreaker invokes the fallback to try retrieving cached data.
3. TimeLimiter requests canceling the running Future. If the client supports cancellation, the request or task can stop early; otherwise, the operation may continue in the background.
4. If timeout is integrated and recorded as a Circuit Breaker error, this outcome contributes to the failure rate according to the exception policy.
5. If multiple timeouts push the failure rate above the threshold after enough samples, the Circuit Breaker can transition to OPEN and reject subsequent calls.

When changing **cancelRunningFuture** to **false**, the caller can still receive a timeout and fallback after two seconds, but the Future is allowed to keep running. If the application immediately retries, there is a risk of generating extra load while the old task has not finished.

Through this scenario, separately identify three outcomes: when the caller stops waiting, the actual state of the client-side task, and the processing state at the Inventory service. Those three timestamps can differ.

## Conclusion

**timeoutDuration** sets the maximum time the application waits for a protected operation; **cancelRunningFuture** decides whether TimeLimiter requests canceling the Future on timeout. Choose timeouts based on the request's latency budget, align them with HTTP client or database timeouts, and verify the cancellation capability of the execution library. Timeouts let the caller proceed via fallback, while actually stopping the task must be verified at the client layer and the dependent service.
