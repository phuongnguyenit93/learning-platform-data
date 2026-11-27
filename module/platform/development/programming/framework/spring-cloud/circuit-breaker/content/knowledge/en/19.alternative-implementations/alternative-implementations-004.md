# Customizing RetryPolicy, Open Duration, and RetryListener

In a Spring Cloud system, a call to a dependent service can fail transiently due to a dropped connection, timeout, or service overload. Retry lets you reattempt certain recoverable errors. A circuit breaker observes call outcomes and temporarily stops sending requests when a dependency keeps failing. The two mechanisms complement each other but serve different goals: RetryPolicy decides whether a call should be retried; the OPEN duration determines when the circuit breaker attempts recovery; RetryListener observes the lifecycle of attempts.

When customizing them, you need to bound the number of attempts, select the right exception types, configure appropriate backoff, and avoid retrying while the circuit breaker is OPEN. If retries are excessive or lack a time limit, the recovery mechanism itself can amplify load and prolong the outage.

## Distinguishing RetryPolicy, OPEN Duration, and RetryListener

These three components answer three separate questions:

| Component | Question | Responsibility |
|---|---|---|
| RetryPolicy | Can this call be retried after this error? | Decides retry conditions, attempt counts, and which error types are eligible for retry. |
| Circuit breaker OPEN duration | How long must the circuit wait before testing recovery? | Keeps calls rejected for a duration, then permits probing in HALF_OPEN. |
| RetryListener | What happens during the retry lifecycle? | Records start, per-attempt errors, final outcome, and attempt count. |

RetryPolicy does not replace a circuit breaker. A call may be retried a few times and still fail; the circuit breaker can record the final outcome and open the circuit if the failure rate exceeds the threshold. Conversely, when the circuit is OPEN, the circuit breaker rejects calls immediately; repeated retries in this state rarely help the dependency recover.

The examples below use Spring Retry to illustrate `RetryPolicy` and `RetryListener`, combined with Resilience4j as the circuit breaker. These are two separate libraries with their own APIs and configurations; use versions compatible with your project's Spring Boot and Spring Cloud versions.

## Customizing RetryPolicy by Error Type

Spring Retry provides `RetryPolicy` to decide whether an operation can continue attempting. You can use a built-in policy such as `SimpleRetryPolicy` to cap attempts and select which exceptions are retryable.

For example, an inventory read call should only retry on connection or timeout errors. Business errors such as an invalid SKU or missing product should not be retried.

~~~java
import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.HashMap;
import java.util.Map;

import org.springframework.retry.policy.SimpleRetryPolicy;

Map<Class<? extends Throwable>, Boolean> retryable =
        new HashMap<>();

retryable.put(ConnectException.class, true);
retryable.put(SocketTimeoutException.class, true);
retryable.put(IOException.class, true);
retryable.put(InvalidSkuException.class, false);
retryable.put(ProductNotFoundException.class, false);

SimpleRetryPolicy retryPolicy =
        new SimpleRetryPolicy(3, retryable, true);
~~~

In this example, `3` is the maximum number of executions, including the initial call. The `true` parameter tells the policy to inspect the cause chain when classifying exceptions, which is useful when an HTTP client or adapter wraps the root error inside another exception. Check the constructor signature appropriate for the Spring Retry version you are using.

When configuring the retryable map, be explicit about the remaining error types. Do not retry every `RuntimeException`, as that category can include programming bugs, bad input, or business rule violations. Retries only make sense for errors that can self-recover when retried after a delay.

### When Do You Need a Custom RetryPolicy?

Built-in policies fit most cases of capping attempt counts and classifying exceptions. You can implement a custom `RetryPolicy` when retry conditions depend on context, such as:

- Retrying only specific error codes from a partner service.
- Stopping retries once the request deadline has expired.
- Limiting attempts differently depending on the operation type.
- Skipping retries if the request has been canceled by the caller.
- Retrying only when the operation carries an idempotency key.

A custom policy must manage state through `RetryContext`. The main methods of the contract are:

| Method | Role |
|---|---|
| `open(parent)` | Creates a context for the retry execution and links the parent context if present. |
| `canRetry(context)` | Decides whether further execution is permitted. |
| `registerThrowable(context, throwable)` | Records the exception from the attempt that just failed. |
| `close(context)` | Releases or finalizes the context after completion. |

If you write your own policy, make sure `canRetry` always has a clear bound and never permits infinite retries. Reuse `SimpleRetryPolicy` or other built-in policies when they meet your requirements; a custom implementation adds testing and maintenance responsibility.

## Combining RetryPolicy with BackOffPolicy

RetryPolicy answers whether a call may be retried. BackOffPolicy decides the wait interval before the next attempt. These two parts should be configured separately so they are easy to understand and tune.

Example using `RetryTemplate` with up to three executions and exponential backoff:

~~~java
import java.time.Duration;

import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;

RetryTemplate retryTemplate = new RetryTemplate();
retryTemplate.setRetryPolicy(retryPolicy);

ExponentialBackOffPolicy backOffPolicy =
        new ExponentialBackOffPolicy();
backOffPolicy.setInitialInterval(100);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(1_000);

retryTemplate.setBackOffPolicy(backOffPolicy);
~~~

With this configuration, the wait interval grows exponentially: roughly 100 ms, 200 ms, then 400 ms, capped at 1,000 ms. These values are examples; base yours on the dependency's response time and the request's deadline.

In multi-replica systems, backoff with jitter prevents clients from retrying in lockstep at the exact same instant once the dependency recovers. If your Spring Retry version provides a random/exponential backoff policy, choose that policy or add jitter through an appropriate mechanism. Do not write manual sleep loops in business code as a substitute for BackOffPolicy.

## Using RetryTemplate and Fallback After Exhausting Attempts

You can use `RetryTemplate.execute` to run the operation and provide a `RecoveryCallback` once attempts are exhausted:

~~~java
import org.springframework.retry.RecoveryCallback;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.support.RetryTemplate;

public Inventory findInventory(String sku) {
    RetryCallback<Inventory, RuntimeException> operation =
            context -> inventoryClient.fetch(sku);

    RecoveryCallback<Inventory> recovery =
            context -> Inventory.unavailable(sku);

    return retryTemplate.execute(operation, recovery);
}
~~~

`Inventory` and `Inventory.unavailable` are illustrative data types. In a real application, the fallback should clearly indicate unavailable data or cached data with a defined freshness. Never return a default stock quantity as if it were confirmed by the source service.

`RecoveryCallback` runs only when the policy finishes retrying and the operation has still failed. If the exception is not permitted for retry by the policy, the operation can stop immediately and proceed to recovery. If you need to distinguish business errors from dependency failures, handle them according to the API contract rather than returning the same default result for every exception.

## Customizing How Long the Circuit Breaker Stays OPEN

In Resilience4j, `waitDurationInOpenState` defines how long the circuit breaker stays in the OPEN state before transitioning to HALF_OPEN to test recovery. This is not the wait time between two retry attempts.

Configuration example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

With the configuration above, the circuit stays OPEN for 15 seconds. After the wait, it transitions to HALF_OPEN and allows up to three probe calls. If the probe calls succeed within requirements, the circuit breaker returns to CLOSED; if failures or slow calls continue past the threshold, the circuit opens again.

You can also configure the OPEN duration in Java when constructing an instance:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .waitDurationInOpenState(Duration.ofSeconds(15))
        .permittedNumberOfCallsInHalfOpenState(3)
        .build();
~~~

Choose the OPEN duration according to the dependency's recovery capacity:

- Too short: the application keeps probing before the service can recover, adding extra load.
- Too long: the service is already healthy, yet callers continue getting rejected longer than necessary.
- Balanced: enough time for the dependency to release resources or recover, without disrupting functionality for too long.

In systems with multiple replicas, the OPEN duration is typically managed inside each process's circuit breaker instance. Replicas may transition states at different times; if you need cluster-wide synchronized quotas or state, use an appropriate distributed mechanism rather than assuming local circuit breakers automatically share state.

## Distinguishing OPEN Duration and Retry Backoff

These two wait periods are easily confused because both make calls wait before trying again:

| Duration | Where Does It Live? | What Happens When It Elapses? |
|---|---|---|
| Retry backoff | Between executions of the same retry operation. | RetryTemplate runs the next attempt if RetryPolicy still permits it. |
| `waitDurationInOpenState` | Inside the lifecycle of an OPEN circuit breaker. | The circuit breaker permits recovery probing in HALF_OPEN. |
| Call timeout | Surrounding a single execution. | The call is terminated per timeout policy; may be recorded as an error. |

For example, RetryTemplate might attempt three times with 100 ms and 200 ms backoff. If the entire chain still fails, the circuit breaker records the failure outcome and transitions to OPEN when the threshold is reached. The circuit stays OPEN for 15 seconds before allowing probes. Retry backoff does not shorten the OPEN duration, nor does the OPEN duration determine how many attempts RetryTemplate makes.

## Attaching a RetryListener to Observe the Retry Lifecycle

Spring Retry provides `RetryListener` to observe operations before, during, and after retry attempts. Listeners are useful for logs, metrics, and diagnostics; they do not decide in place of RetryPolicy whether to retry.

Key callbacks:

| Callback | Timing | Usage |
|---|---|---|
| `open` | When a retry session starts. | Attach context or record operation start. |
| `onError` | After each failed attempt. | Record error type and current attempt count. |
| `close` | When the retry session ends. | Record the final outcome and release tracking resources. |

Listener example:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

public class InventoryRetryListener implements RetryListener {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryRetryListener.class);

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context,
            RetryCallback<T, E> callback) {
        log.debug("Starting inventory retry operation");
        return true;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        log.warn(
                "Inventory attempt {} failed with {}",
                context.getRetryCount(),
                throwable.getClass().getSimpleName()
        );
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        if (throwable == null) {
            log.debug(
                    "Inventory retry operation succeeded after {} retries",
                    context.getRetryCount()
            );
        } else {
            log.error(
                    "Inventory retry operation exhausted after {} retries",
                    context.getRetryCount(),
                    throwable
            );
        }
    }
}
~~~

Registering the listener with RetryTemplate:

~~~java
retryTemplate.registerListener(new InventoryRetryListener());
~~~

In this example, `onError` is called for each failed execution. `close` receives the final exception if the retry session ended in failure; if the operation succeeded, throwable may be null. The count in RetryContext generally represents the number of retries that have occurred, not necessarily total executions; when exposing metrics, name your metrics clearly to avoid confusion.

Listeners should keep callbacks brief. Avoid making HTTP calls, querying databases, or performing blocking work inside a listener, because that lengthens retry duration and can introduce another dependency on the hot path. Do not log tokens, personal data, or full sensitive payloads.

## Registering Listeners and Metrics

You can register one or more listeners as needed:

~~~java
RetryTemplate retryTemplate = new RetryTemplate();
retryTemplate.setRetryPolicy(retryPolicy);
retryTemplate.setBackOffPolicy(backOffPolicy);
retryTemplate.registerListener(new InventoryRetryListener());
~~~

In systems requiring metrics, a listener can increment counters for retry attempts or retry sessions ending in failure. Use tags with bounded value domains such as dependency, operation, and exception family. Do not use SKU, user ID, order ID, or request ID as metric tags, as cardinality will grow with traffic.

Useful metrics:

- Retry sessions started.
- Additional retry attempts per session.
- Sessions succeeding after retry.
- Sessions exhausting attempts and falling back to recovery.
- Overall operation latency including backoff.
- Breakdown of exceptions triggering retries.

Do not measure retry counts alone while ignoring final session success counts. Rising retries may mean transient glitches are being recovered, or it may be a sign that the dependency is degrading or timeouts are set too low.

## Coordinating RetryTemplate with CircuitBreaker

The wrapping order of retry and circuit breaker affects how many samples the circuit breaker records.

**Retry inside circuit breaker:** the circuit breaker wraps the entire retry sequence. One logical operation is recorded based on the final result after retries succeed or are exhausted. This prevents one operation from generating multiple failure samples in the window, though the circuit breaker only learns of the failure after retries finish.

**Retry outside circuit breaker:** each attempt can pass through the circuit breaker. When the circuit is OPEN, the next attempt is rejected fast. This lets the circuit breaker see errors sooner, but requires classifying `CallNotPermittedException` so retries do not loop pointlessly while the circuit is open.

High-level diagram:

~~~mermaid
flowchart TD
    A[Business request] --> B[RetryTemplate]
    B --> C[Circuit Breaker]
    C --> D[HTTP client]
    D -->|Success| E[Result]
    D -->|Error| F[RetryPolicy evaluates]
    F -->|Attempts left| G[Backoff]
    G --> B
    F -->|Exhausted| H[Recovery / fallback]
    C -->|OPEN| I[Fast reject]
~~~

The diagram illustrates one coordination pattern. When implementing, decide explicitly whether the circuit breaker should count individual physical calls or a logical operation spanning multiple attempts. For an overloaded dependency, retry very cautiously; if all callers retry in lockstep, traffic can spike sharply right as the service begins to recover.

Do not retry rejection errors caused by an OPEN circuit breaker. If your retry policy allows retrying `CallNotPermittedException`, each attempt only produces another rejection without ever reaching the service. Exclude this exception from the retryable set or order the circuit breaker appropriately so rejection errors are not retried.

## Setting an Overall Deadline for the Entire Retry Chain

The number of attempts and backoff must fit within the request's time budget. If each call has a two-second timeout, retries three times, and has one second of total backoff, processing time can exceed seven seconds before counting time spent in other layers.

Before enabling retries, calculate:

- Maximum timeout per individual call.
- Maximum number of executions, including the initial call.
- Total backoff duration between attempts.
- Remaining time for upstream processing and response.

If a request has a 2-second deadline, you may need to cap each call at 500 ms and allow only one short retry. Once the deadline has elapsed, do not continue retrying even if the policy still has attempts left. For write operations, retry only when an idempotency key or state-check mechanism is present to avoid duplicate transactions.

## Testing RetryPolicy, OPEN Duration, and RetryListener

Test all three parts separately before testing them together:

| Scenario | Expected Outcome to Verify |
|---|---|
| Encounters retryable ConnectException | RetryPolicy permits the next attempt if attempts remain. |
| Encounters excluded InvalidSkuException | No unnecessary retries occur. |
| Reaches maxAttempts | RetryTemplate stops and invokes recovery if configured. |
| Backoff grows as configured | Wait intervals between attempts increase and stay within bounds. |
| Listener receives per-attempt errors | onError is called with the matching exception and retry count. |
| Retry session finishes successfully | close receives a null final exception. |
| Retry session exhausts attempts | close receives the final exception and recovery is invoked. |
| Circuit breaker transitions to OPEN | Subsequent calls are rejected during waitDurationInOpenState. |
| OPEN duration elapses | Circuit transitions to HALF_OPEN and permits the configured number of probe calls. |
| Retry encounters CallNotPermittedException | Does not loop retries while the circuit is OPEN. |
| Request exceeds deadline | Stops retrying and returns outcome per timeout policy. |

Use a mock clock or virtual scheduler when testing timing to avoid real waits. Verify execution counts, wait durations, listener invocation counts, and circuit breaker state. Do not check only the final fallback value, since the same fallback can originate from a timeout, a business error, or an OPEN circuit.

## Implementation Workflow

1. Select transient exceptions eligible for retry and exclude business errors, authorization errors, and unrecoverable errors.
2. Configure RetryPolicy with an explicit maximum number of executions.
3. Configure a bounded BackOffPolicy and consider jitter when multiple replicas retry concurrently.
4. Set an overall deadline for the retry chain and an individual timeout per call.
5. Configure `waitDurationInOpenState` based on how long the dependency needs to recover.
6. Choose a HALF_OPEN probe count suited to the dependency's capacity.
7. Register a RetryListener to observe per-attempt errors and final outcomes.
8. Choose the retry/circuit breaker order and exclude `CallNotPermittedException` from retries.
9. Test transient errors, business errors, exhausted attempts, OPEN/HALF_OPEN, timeouts, and cancellation.

RetryPolicy decides whether to retry an error; BackOffPolicy tunes the wait between attempts; `waitDurationInOpenState` determines when the circuit breaker tests recovery; RetryListener supplies observability signals for each retry session. By capping attempt counts, classifying exceptions accurately, and coordinating them within the request deadline, a Spring Cloud application can handle transient failures without amplifying load on dependent services.
