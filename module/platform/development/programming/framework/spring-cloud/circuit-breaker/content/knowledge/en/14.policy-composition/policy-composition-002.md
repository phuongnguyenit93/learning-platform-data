# Retrying Transient Errors and Ignoring Business Errors or Open Circuits

In a Spring Cloud CircuitBreaker application integrated with Resilience4j, Retry and Circuit Breaker are commonly combined to handle two different situations. Retry re-attempts a call when the error is likely only temporary; Circuit Breaker prevents the application from continuing to call a dependent service showing signs of being unhealthy. Exception classification determines which errors are retried, which errors are recorded in the failure rate, and which errors must stop immediately.

Business errors such as an invalid product code or insufficient stock usually cannot be resolved by calling again. Similarly, **CallNotPermittedException** indicates that Circuit Breaker is rejecting the call because the circuit is open or no further probe calls are permitted. If Retry keeps retrying this type of error, the application only creates extra work without helping the dependency recover. This lesson presents how to configure the exception policy and choose the composition order of the two mechanisms.

## 1. Distinguishing Transient Errors from Non-Retryable Errors

Before configuring Retry, identify the meaning of each error according to the dependent service's contract.

| Error group | Examples | Typical appropriate behavior |
|---|---|---|
| Transient infrastructure errors | Connection reset, some connect timeouts, temporary HTTP 503 | Can be retried with a limited count and wait interval |
| Business errors | SKU does not exist, insufficient quantity, order already canceled | Return business result or error; do not retry |
| Authentication/authorization errors | HTTP 401 or 403 | Do not retry if credentials have not changed |
| Input errors | Missing SKU, negative quantity, malformed format | Reject the request before calling the dependency |
| Circuit Breaker rejection | **CallNotPermittedException** | Stop retrying; wait for Circuit Breaker to permit calls again |
| Programming or internal mapping errors | NullPointerException from application code, broken mapper | Investigate and fix the root cause; do not automatically retry every case |

An error should only be retried when the next attempt has a chance of succeeding without changing the input data or business state. For example, a dropped connection while the Inventory service is still healthy may be a transient error. Conversely, a request to reserve 10 items when the warehouse only has 4 items is a business outcome; resending the same request will not increase the stock count.

Some timeouts can also be retried, but you must consider whether the operation has already been executed by the target service. For write operations, the client may time out after the server has completed the work. Retrying without an idempotency key can create duplicate transactions or reserve stock twice. Therefore, error classification must be based on both the nature of the exception and whether the operation can be safely repeated.

## 2. Configuring Retry Only for Transient Exceptions

Resilience4j Retry lets you configure the maximum number of attempts, wait duration between attempts, and lists of exceptions to retry or ignore. The following example allows up to three executions, including the initial call:

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 200ms
        retryExceptions:
          - com.example.inventory.TransientInventoryException
          - java.net.SocketTimeoutException
          - java.net.ConnectException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.InsufficientStockException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException
~~~

In the example:

- **maxAttempts: 3** includes the first call and at most two retries.
- **waitDuration: 200ms** sets the wait interval between attempts.
- **retryExceptions** lists errors that are likely transient and allowed to be retried.
- **ignoreExceptions** lists business errors and Circuit Breaker rejection errors that Retry must skip.

When declaring the **retryExceptions** list, treat it as the policy for error types allowed to be retried. The **ignoreExceptions** list explicitly expresses cases that must not be retried. The exception policy needs to match the Resilience4j version in use and the actual exceptions thrown by the HTTP client or service layer; sometimes the error to classify lies in the inner cause of a wrapper exception.

Do not configure retry for all exceptions. If Retry retries authentication errors, invalid data, business errors, or programming bugs, the application will increase load and prolong response times without improving the chance of success.

## 3. Ignoring Business Errors in Both Retry and Circuit Breaker

Retry and Circuit Breaker have separate exception recording rules:

- Retry decides which exceptions cause it to perform another call.
- Circuit Breaker decides which exceptions count as a failed outcome in the sliding window.

Therefore, if a business error should not increase the failure rate, adding it only to Retry's **ignoreExceptions** is not enough. You must declare the exclusion in both mechanisms.

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 200ms
        retryExceptions:
          - com.example.inventory.TransientInventoryException
          - java.net.SocketTimeoutException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.InsufficientStockException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException

  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.InsufficientStockException
~~~

When Inventory returns **InsufficientStockException**, Retry does not retry it. Circuit Breaker also does not count this exception as a failure when evaluating the failure rate. The business result is still passed back to the calling layer so the application can return an appropriate response.

Exceptions ignored by Circuit Breaker are not counted as either success or failure in the failure rate evaluation. As a result, business errors do not distort the health signal of the dependency. Other infrastructure errors continue to be recorded according to the Circuit Breaker policy.

**CallNotPermittedException** is added to Retry's ignore list to prevent retrying when this exception passes through Retry. Circuit Breaker itself raises the rejection error; it is not a new error returned by Inventory for the breaker to record as another failure.

## 4. Distinguishing Transient Errors from CallNotPermittedException

When Circuit Breaker is OPEN, new calls are rejected before the supplier invokes the dependent service. Resilience4j typically raises **CallNotPermittedException**. A similar situation can occur in HALF_OPEN when all permitted probe calls have already been used.

This is a signal that the protection mechanism is active. Retry should not treat it as a temporary connection error and keep retrying every few hundred milliseconds. Continuous retrying can:

- Generate unnecessary exceptions and logs.
- Increase request latency.
- Create load on the calling application while the dependency is still not permitted to receive requests.
- Add extra pressure right when the system needs load shedding.

The right time to try again is controlled by Circuit Breaker through its OPEN wait duration and transition to HALF_OPEN. When the circuit is open, the application should execute a fallback or return a retryable error to the caller. When Circuit Breaker permits probes, a limited number of probe calls will test the dependency's recovery.

If using Retry outside Circuit Breaker, include **CallNotPermittedException** in Retry's **ignoreExceptions** to stop immediately when the breaker rejects calls. If Circuit Breaker is outside Retry, the rejection exception is thrown before the supplier containing Retry runs; Retry never sees this error. The two orders have different behavior and must be chosen intentionally.

## 5. Composition Order of Retry and Circuit Breaker

The nesting order determines whether Circuit Breaker records each attempt or records one combined outcome for the entire logical call.

### Circuit Breaker on the Outside, Retry on the Inside

~~~java
return circuitBreakerFactory.create("inventory").run(
    () -> retry.executeSupplier(
        () -> inventoryClient.getStock(sku)
    ),
    error -> fallback(sku, error)
);
~~~

Execution flow:

1. Circuit Breaker checks its state before running the supplier.
2. If OPEN, the supplier does not run and the fallback is invoked.
3. If permitted, Retry performs the first call and retries transient exceptions according to configuration.
4. When Retry succeeds, Circuit Breaker receives a success outcome.
5. If Retry exhausts all attempts and still fails, Circuit Breaker receives the final exception of the logical call.

With this order, one logical request produces only one outcome in Circuit Breaker's sliding window, even though Retry may have called the dependency multiple times. This is the right choice when you want Circuit Breaker to evaluate the final success rate of the operation after the retry policy.

### Retry on the Outside, Circuit Breaker on the Inside

~~~java
Supplier<Stock> circuitBreakerProtected =
    CircuitBreaker.decorateSupplier(
        circuitBreaker,
        () -> inventoryClient.getStock(sku)
    );

Supplier<Stock> retryAroundCircuitBreaker =
    Retry.decorateSupplier(retry, circuitBreakerProtected);

return retryAroundCircuitBreaker.get();
~~~

Execution flow:

1. Retry starts an attempt.
2. Each attempt passes through Circuit Breaker.
3. Circuit Breaker records the outcome of each permitted execution.
4. If Circuit Breaker transitions to OPEN, the next attempt is rejected with **CallNotPermittedException**.
5. Retry ignores this exception and stops immediately.

With this order, failed attempts can be recorded individually in the sliding window. Circuit Breaker can open while Retry is still active; the next attempt is blocked. Configuring **ignoreExceptions** for **CallNotPermittedException** is critical in this case.

| Criterion | Circuit Breaker outside, Retry inside | Retry outside, Circuit Breaker inside |
|---|---|---|
| What Circuit Breaker records | Final outcome after Retry | Outcome of each permitted attempt |
| Samples in sliding window | Usually one sample per logical operation | Can be multiple samples per logical operation |
| When Circuit Breaker is OPEN | Supplier does not run; Retry does not start | Retry receives CallNotPermittedException and must ignore it |
| Ability to open mid-retry sequence | After Retry finishes and returns the outcome | Can open in the middle of a retry sequence |
| Suitable when | Wanting to measure the final request outcome | Wanting Circuit Breaker to react to each attempt |

There is no single right order for every system. Choose based on the sliding window semantics the operations team wants to observe. Whichever order you choose, still limit the number of retries, set an appropriate wait interval, and avoid retrying business errors.

## 6. Example Integrating Spring Cloud CircuitBreaker with Retry

You can use the Spring Cloud CircuitBreaker factory as the outer layer while Resilience4j Retry performs attempts inside the supplier. The following example assumes the application already has the **inventory** Retry instance configured in properties and can inject **RetryRegistry**:

~~~java
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryRegistry;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RetryRegistry retryRegistry;
    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;

    InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RetryRegistry retryRegistry,
            InventoryClient inventoryClient,
            InventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.retryRegistry = retryRegistry;
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
    }

    Stock getStock(String sku) {
        Retry retry = retryRegistry.retry("inventory");

        return circuitBreakerFactory.create("inventory").run(
            () -> retry.executeSupplier(
                () -> inventoryClient.getStock(sku)
            ),
            error -> inventoryCache.findBySku(sku)
                .orElseThrow(() ->
                    new InventoryUnavailableException(sku, error)
                )
        );
    }
}
~~~

Here, Circuit Breaker is the outer layer. When the circuit is OPEN, the supplier does not run so Retry does not start. When the circuit permits calls, Retry handles transient errors. If all attempts fail, the fallback reads cached data or throws a business exception.

This approach also separates two types of outcomes: transient errors handled by Retry inside the supplier and the final error recorded by Circuit Breaker for the logical operation. If you want Circuit Breaker to observe each attempt, use the opposite decorator order and configure Retry to ignore **CallNotPermittedException**.

## 7. Java Configuration

If you want to configure directly in code instead of declaring properties, you can build a `RetryConfig` and register Retry with `RetryRegistry`:

~~~java
import java.time.Duration;
import java.net.SocketTimeoutException;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.retry.RetryConfig;
import io.github.resilience4j.retry.RetryRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryRetryConfiguration {

    @Bean
    RetryRegistry retryRegistry() {
        RetryConfig retryConfig = RetryConfig.custom()
            .maxAttempts(3)
            .waitDuration(Duration.ofMillis(200))
            .retryExceptions(
                TransientInventoryException.class,
                SocketTimeoutException.class
            )
            .ignoreExceptions(
                InvalidSkuException.class,
                InsufficientStockException.class,
                CallNotPermittedException.class
            )
            .build();

        return RetryRegistry.of(retryConfig);
    }
}
~~~

If the application already has an auto-configured `RetryRegistry` from the Resilience4j Spring Boot starter, configure the instance via properties or customize the existing registry in a way compatible with the version in use. Avoid creating multiple independent registries for the same policy without reason, as that can cause components to use different Retry instances and metrics.

## 8. Using Backoff and Limiting Total Duration

A fixed wait interval helps avoid rapid-fire retries, but in a system where many clients fail at once, all of them may retry nearly simultaneously. Exponential backoff and jitter help spread out attempts.

Example properties using an increasing wait interval:

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 200ms
        enableExponentialBackoff: true
        exponentialBackoffMultiplier: 2
        enableRandomizedWait: true
        randomizedWaitFactor: 0.5
        retryExceptions:
          - com.example.inventory.TransientInventoryException
          - java.net.SocketTimeoutException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.InsufficientStockException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException
~~~

With a base duration of 200 ms and a multiplier of 2, the wait interval can increase across attempts; jitter varies the wait duration around the computed value. Property names and how backoff options combine depend on the Resilience4j version, so verify the configuration against your actual dependency version.

The total duration of the operation must stay within the API's response budget. If each attempt takes up to two seconds, there are three attempts, and there are wait intervals in between, the request could take over six seconds. Combine Retry with TimeLimiter and HTTP client timeouts. The overall timeout must cover all attempts and wait intervals, not just a single call's duration.

## 9. Fallback After Retry Finishes

Fallback should execute when Circuit Breaker rejects the call or when Retry has exhausted all attempts and still failed. Do not place a recovering fallback directly inside the supplier before Retry if the goal is for Retry to see the original error.

Example:

~~~java
Stock getStock(String sku) {
    Retry retry = retryRegistry.retry("inventory");

    return circuitBreakerFactory.create("inventory").run(
        () -> retry.executeSupplier(
            () -> inventoryClient.getStock(sku)
        ),
        error -> {
            if (error instanceof CallNotPermittedException) {
                log.warn("Circuit Breaker inventory is OPEN, sku={}", sku);
            } else if (error instanceof InsufficientStockException) {
                throw (InsufficientStockException) error;
            } else {
                log.warn("Inventory did not respond successfully, sku={}", sku, error);
            }

            return inventoryCache.findBySku(sku)
                .orElseThrow(() ->
                    new InventoryUnavailableException(sku, error)
                );
        }
    );
}
~~~

In the example, the business error **InsufficientStockException** is rethrown so the calling layer handles it with its proper meaning of “insufficient stock”, rather than turning it into “Inventory unavailable”. Errors rejected by Circuit Breaker are logged separately. Remaining infrastructure errors can use the cache if business rules allow.

A fallback should not call the same failing dependency through another path. If the fallback continues calling Inventory, the application can recreate the failure chain and defeat Circuit Breaker. A cache or an independent backup source is usually more suitable.

## 10. Do Not Retry Write Operations Without Guaranteed Idempotency

Retrying a read operation is generally less risky than a write operation. For stock reservation, payment, or order creation commands, a timeout can occur after the server has finished processing before the response reaches the client.

Example:

1. The client sends a command to reserve 2 items.
2. Inventory receives the command and updates the stock count.
3. The response is lost in transit.
4. The client times out and Retry resends the command.
5. If the server does not recognize duplicate requests, the quantity may be reserved twice.

To retry safely, use an **idempotency key** or a stable business request ID for the same logical operation. The server should store the processing result by key and return the previous result when receiving a duplicate request. Do not use the Circuit Breaker ID as an idempotency key: a Circuit Breaker ID is shared across many requests, whereas an idempotency key identifies one specific write operation.

Only retry recoverable errors and operations that can be safely repeated. For errors where the outcome of a write operation is unknown, you may need to query the transaction status before deciding to resend.

## 11. Observing Retry and Circuit Breaker

When combining both mechanisms, monitor separate metrics to know whether the system is retrying due to transient errors or rejecting due to Circuit Breaker.

| Signal | Operational question |
|---|---|
| Retry attempts | How many attempts does an operation take on average? |
| Retry success | How many transient errors were recovered on a subsequent attempt? |
| Retry exhausted | How many operations exhausted all attempts and still failed? |
| Retry ignored errors | How many business errors or CallNotPermittedException were ignored? |
| Circuit Breaker failure rate | Is the final or per-attempt failure rate exceeding the threshold? |
| CallNotPermitted count | How many calls were rejected while the circuit was open or probes were exhausted? |
| Fallback count | How often does the application have to fall back to cache or fallback behavior? |
| Overall latency | Is Retry pushing requests past the response time budget? |

Specific metric and tag names depend on the version, Micrometer registry, and integration configuration. Use a stable instance name like **inventory** to group metrics. Do not put SKU, order ID, or trace ID into Retry/Circuit Breaker names or high-cardinality metric tags.

When you see Retry rising while Circuit Breaker remains CLOSED, check transient errors, wait durations, and attempt counts. When `CallNotPermitted` rises, Circuit Breaker is rejecting calls; inspect the state and dependency health instead of increasing Retry attempts. When fallback rises, evaluate the cache, fallback data quality, and service recovery time.

## 12. Practice Scenario

An order service calls Inventory to check stock levels. The policy is configured as follows:

- Retry allows up to three executions, retrying only **TransientInventoryException** and **SocketTimeoutException**.
- **InvalidSkuException** and **InsufficientStockException** are ignored by both Retry and Circuit Breaker.
- **CallNotPermittedException** is ignored by Retry so it stops immediately when Circuit Breaker rejects calls.
- Circuit Breaker uses a window of 20 samples, a minimum of 10 calls, and a 50% failure rate threshold.
- Fallback reads from cache or returns a business error if no suitable data exists.

Consider these scenarios:

| Call outcome | What does Retry do? | What does Circuit Breaker do? |
|---|---|---|
| First attempt gets **TransientInventoryException**, next succeeds | Retries and returns the successful result | Records according to the chosen composition order |
| Receives **InsufficientStockException** | Ignores it, does not retry | Ignores the exception, does not count toward failure rate |
| Circuit Breaker is OPEN | Does not continue retrying after **CallNotPermittedException** | Rejects the call before Inventory is called |
| All three attempts hit transient errors | Stops after max attempts and returns the final error | Records the outcome according to Circuit Breaker's position in the decorator chain |
| Inventory recovers and Circuit Breaker transitions to HALF_OPEN | Does not continuously retry rejected calls | Permits only the configured number of probe calls |

During practice, make sure you can identify:

1. Which exceptions can actually be retried.
2. Which exceptions must be ignored in Retry and Circuit Breaker.
3. Whether Circuit Breaker is outside or inside Retry.
4. Whether the sliding window records each attempt or the final outcome of the operation.
5. When fallback runs and whether it continues calling the failing dependency.
6. Whether write operations have an idempotency key to prevent duplicate execution.

## Conclusion

Retry should perform bounded retries on recoverable transient errors. Business errors such as invalid data or insufficient stock should be ignored in both Retry and Circuit Breaker if they do not reflect dependency health. **CallNotPermittedException** must stop Retry so Circuit Breaker controls retry timing via HALF_OPEN. The nesting order determines whether Circuit Breaker records each attempt or the final outcome; choose the semantics explicitly, align backoff with timeout budgets, and ensure write operations are idempotent before retrying.
