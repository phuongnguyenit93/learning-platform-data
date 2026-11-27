# Reconciling Circuit Breaker Failure Rates with Fallback Outcomes

When a dependent service fails, an application can return backup data via a fallback so the business flow can continue serving requests. However, returning a valid result from a fallback does not mean the call to the dependent service succeeded. With Spring Cloud CircuitBreaker using Resilience4j, you must distinguish **the outcome of the protected call** from **the outcome returned by the fallback to the caller**. The circuit breaker classifies the call based on the outcome inside the protected region; the fallback usually executes after the circuit breaker has already recorded that outcome.

Distinguishing these two outcomes helps you interpret failure rates, slow-call rates, and rejected call counts accurately. If you fold service failures into a fallback and return them as a successful result directly inside the supplier, the circuit breaker may fail to detect that the dependent service is degrading.

## 1. Two Outcomes at Two Different Moments

A call flow with a circuit breaker and fallback typically proceeds as follows:

1. The application invokes the circuit breaker.
2. If the circuit breaker is `CLOSED` or allows a probe call in `HALF_OPEN`, the supplier calls the dependent service.
3. The circuit breaker records the supplier's outcome: success, failure, or slow call according to configuration.
4. If the supplier throws an exception, the Spring Cloud wrapper or code outside the circuit breaker can invoke the fallback.
5. The caller receives the fallback result if the fallback completes successfully.

If the circuit breaker is already `OPEN`, the supplier does not execute. The circuit breaker rejects the new call with `CallNotPermittedException`; the fallback can handle that rejection and return backup data.

```text
Business request
       |
       v
  Circuit breaker
       |
       +-- OPEN ----------------------> Reject call
       |                                  |
       |                                  v
       |                              Fallback
       |                                  |
       |                                  v
       |                           Result for caller
       |
       +-- CLOSED / HALF_OPEN
              |
              v
       Supplier calls service
              |
        +-----+------+
        |            |
     Success     Exception
        |            |
        v            v
   Record        Record failure
   success            |
        |             v
        |          Fallback
        |             |
        +------> Result for caller
```

Fallback is an application-layer recovery mechanism. It does not retroactively alter the call history the circuit breaker just recorded. Thus, a fallback can return valid data while the failure rate continues to climb.

## 2. Failure Rate Is Computed from Protected Calls

Resilience4j uses outcomes recorded in the sliding window to compute the failure rate:

\[
\text{failureRate} = \frac{\text{number of calls recorded as failed}}{\text{number of calls recorded in the window}} \times 100\%
\]

Calls in the sample include outcomes recorded by the circuit breaker as successes or failures. Exceptions configured to be ignored contribute to neither group. Calls rejected while the breaker is `OPEN` are also not failed calls to the dependent service; the supplier did not run and rejections are tracked separately.

Example configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
```

Suppose 10 calls are executed while the breaker is `CLOSED`:

| Dependent Service Outcome | Count | Fallback Returns Successful Result | Recorded by Circuit Breaker |
| --- | ---: | ---: | --- |
| Service returns normal data | 4 | No fallback needed | 4 successes |
| Service throws exception | 6 | Yes, all 6 times | 6 failures |

The failure rate is `6 / 10 × 100% = 60%`. Even though the caller received a fallback result on all six failed requests, the circuit breaker still observed six failed calls. Because `minimumNumberOfCalls` reached 10 and `failureRateThreshold` is 50%, the breaker transitions to `OPEN`.

Using the final responses returned to end users as the numerator or denominator would miscalculate the failure rate. Circuit breaker metrics describe the reliability of the protected dependency calls, while fallback success rates describe the application's resilience.

## 3. Slow-Call Rate Is Also Independent of Fallback Outcomes

A call may throw no exception yet still take too long. Resilience4j uses `slowCallDurationThreshold` to identify slow calls and `slowCallRateThreshold` to decide when the slow-call percentage is high enough to open the circuit.

For example, out of 10 calls, 7 take longer than 2 seconds before eventually returning successfully. If the slow-call threshold is 60%, the circuit breaker can transition to `OPEN` because the slow-call rate hits 70%, even though the failure rate is 0%.

If a slow call subsequently throws an exception, it can contribute to both the failure rate and the slow-call rate. The two rates are computed independently rather than summed together. Meeting either threshold is enough to open the circuit.

With standard wrapping, the fallback runs after the supplier completes and the circuit breaker has recorded the supplier's execution duration. Fallback execution time is not counted toward the protected call's duration. If you catch exceptions and run fallback logic directly inside the supplier, all fallback processing time becomes part of the supplier's duration; this can cause a successful outcome to be flagged as a slow call.

## 4. Placing Fallback Outside the Supplier to Preserve Classification

With Spring Cloud CircuitBreaker, pass the fallback to the `run(...)` method:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.fetch(sku),
            error -> inventoryFallback(sku, error)
        );
    }

    private InventoryResult inventoryFallback(String sku, Throwable cause) {
        return InventoryResult.unavailable(sku);
    }
}
```

In this example, the supplier only runs `inventoryClient.fetch(sku)`. If the client throws an exception, the circuit breaker records the outcome according to Resilience4j's classification rules, and Spring Cloud then calls the fallback function. If the breaker is `OPEN`, the supplier is skipped and the fallback can still return a backup result for the request.

With Resilience4j's native API, you can run the supplier via `executeSupplier(...)` and handle errors outside:

```java
try {
    return inventoryBreaker.executeSupplier(
        () -> inventoryClient.fetch(sku)
    );
} catch (CallNotPermittedException ex) {
    return InventoryResult.unavailable(sku);
} catch (RuntimeException ex) {
    return InventoryResult.unavailable(sku);
}
```

This is a condensed example: production applications should distinguish business errors, technical errors, timeouts, and rejections to choose an appropriate fallback. Never catch every `Throwable` and return a generic default, as that hides programming bugs, misconfigurations, or critical process failures.

## 5. What Happens If You Catch Errors Inside the Supplier?

A misleading pattern is catching dependent-service exceptions inside the supplier and immediately returning backup data:

```java
return circuitBreakerFactory.create("inventory").run(
    () -> {
        try {
            return inventoryClient.fetch(sku);
        } catch (RuntimeException ex) {
            // Fallback is executed inside the circuit breaker boundary.
            return InventoryResult.unavailable(sku);
        }
    },
    error -> InventoryResult.unavailable(sku)
);
```

In this case, the exception is handled by the supplier. From the circuit breaker's perspective, the supplier completed normally and returned a value. The breaker records the call as a success; it has no idea the dependent service threw an exception. If all failed calls are turned into backup results inside the supplier, the failure rate can stay at 0% and the breaker will never open even while the service is down.

This pattern is only appropriate if the application deliberately defines the backup value as a successful outcome of the protected operation. If your goal is to detect dependent-service failures, let exceptions propagate out of the supplier so the circuit breaker records them, then execute the fallback in an outer layer.

| Fallback Handling Location | Outcome Observed by Circuit Breaker | Impact on Failure Rate |
| --- | --- | --- |
| Fallback after `run(...)` or after `executeSupplier(...)` | Supplier throws exception | Call recorded as failed if the exception is configured to be recorded |
| Catching exception and returning fallback inside supplier | Supplier returns normally | Call recorded as successful |
| Breaker is `OPEN`, supplier does not run | Call rejected | Does not increase dependent-call failure rate; rejections tracked separately |

## 6. Classifying Exceptions Before Reconciling with Fallback

Not every exception should increase the failure rate. Resilience4j allows configuring which exceptions to record or ignore. Review this policy before comparing fallback counts against error counts.

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
        ignoreExceptions:
          - com.example.inventory.ProductNotFoundException
```

The example above expresses classification intent: connection errors and timeouts count as failures; product-not-found is an ignored business outcome. When using `recordExceptions`, check the semantics of your Resilience4j version and ensure other exceptions are classified as intended. Ignore rules take precedence over record rules for exceptions matching ignore.

Suppose 10 calls yield 4 successes, 4 connection errors, and 2 ignored `ProductNotFoundException`s. The sample used to calculate rates has 8 recorded outcomes: 4 successes and 4 failures. The failure rate is `4 / 8 × 100% = 50%`, not `4 / 10 = 40%`. Even if a fallback returns backup results for all six exceptions, that still does not change how those exceptions were classified.

Business errors should only be ignored when they genuinely do not reflect dependency degradation. For example, `ProductNotFoundException` may be a valid response for a nonexistent SKU. Conversely, system authentication errors, database connection errors, or timeouts may be signals that should be recorded depending on the circuit breaker boundary and protection goals.

## 7. Calls Rejected When the Breaker Is OPEN Are Not New Service Failures

Once the circuit breaker transitions to `OPEN`, new calls are rejected before the supplier runs. The application can still invoke a fallback and return cached data, a temporary notice, or an unavailable status. However, do not count each fallback triggered by `CallNotPermittedException` toward the dependent service's failure rate: during those calls, the application sent no request to the service.

Distinguish at least three metric categories:

- **Dependent-call failures:** the supplier ran and terminated with a recorded exception.
- **Slow calls:** the supplier finished after `slowCallDurationThreshold`, even if it succeeded.
- **Rejected calls:** the circuit breaker prevented the supplier from running because the current state is `OPEN` or no further probe calls are permitted.

These metrics answer different operational questions. The failure rate tells you the reliability of executed calls. The slow-call rate tells you the latency of executed calls. The rejection count tells you how many requests the circuit breaker is blocking to shield the system. The fallback success rate tells you how many requests the application could still answer using its backup mechanism.

When the breaker is `HALF_OPEN`, only a limited number of probe calls are allowed. The supplier outcomes of those probe calls determine whether the breaker closes or re-opens. If a supplier fails while the fallback returns a valid result, the breaker still sees the supplier fail and can return to `OPEN`. Fallback outcomes are never treated as evidence that the dependent service has recovered.

## 8. Cross-Checking Metrics to Identify Root Causes

Do not watch a single metric in isolation. Combining total calls, failure rate, slow-call rate, rejection count, and fallback success count pinpoints which layer has a problem.

| Observation | Possible Interpretation | What to Check |
| --- | --- | --- |
| Failure rate rises, fallback success is high | Dependent service is failing, yet the application still responds using backup data | Check client errors, dependent service logs, and fallback policy |
| Slow-call rate rises, failure rate is low | Service responds slowly but still succeeds | Check latency, timeouts, and `slowCallDurationThreshold` |
| Rejections surge without a matching rise in failure rate | Breaker is `OPEN` and blocking new calls | Check state-transition timestamps and wait duration in open state |
| Fallback fails alongside dependency failures | Both primary service and backup mechanism are failing | Check cache, backup data sources, and fallback exceptions |
| Failure rate stays flat despite many client error logs | Exceptions may be ignored or caught inside the supplier | Check `recordExceptions`, `ignoreExceptions`, and catch block placement |

For example: a dashboard shows 40% of inventory calls failing, 95% of fallbacks completing successfully, and rejections climbing. You can conclude the application is still serving most requests via fallback, while the inventory service remains degraded and the breaker has begun blocking calls. Do not interpret 95% fallback success as a 95% success rate for the inventory service.

## 9. Testing to Prove Fallbacks Do Not Mask Failures

A solid test verifies both the caller-facing outcome and the breaker's state. With a test configuration of `minimumNumberOfCalls: 4`, `failureRateThreshold: 50`, and a count-based window of 4 calls, you can simulate four dependent-service failures and confirm the fallback still returns backup results while the breaker transitions to `OPEN`.

Example test using Resilience4j's native API:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(4)
    .minimumNumberOfCalls(4)
    .failureRateThreshold(50)
    .build();

CircuitBreaker breaker = CircuitBreaker.of("inventory", config);

for (int i = 0; i < 4; i++) {
    InventoryResult result;
    try {
        result = breaker.executeSupplier(() -> {
            throw new IllegalStateException("inventory unavailable");
        });
    } catch (RuntimeException ex) {
        result = InventoryResult.unavailable("SKU-1");
    }

    // Each call returns a fallback result to the business layer.
    assert result.isUnavailable();
}

// Four failed supplier executions are still recorded as failures by the circuit breaker.
assert breaker.getState() == CircuitBreaker.State.OPEN;
```

This snippet uses Java `assert` to illustrate the idea; in real projects, use your testing framework's assertions and enable the appropriate test configuration. The test confirms two separate facts: the caller receives the fallback result, and the breaker moves to `OPEN` because the supplier failed enough times. Once the breaker opens, another call will be rejected before the supplier runs; test supplier invocation counts separately to prove it.

With Spring Cloud CircuitBreaker, run the same scenario through `CircuitBreakerFactory` and the fallback passed to `run(...)`. Assert the fallback return value, then inspect state from the backend registry or observe corresponding metrics/events. Ensure the factory and registry reference the same instance; if you create an independent registry in a test, the state you read may not belong to the breaker managed by the factory.

When testing slow calls, make the supplier wait deterministically longer than `slowCallDurationThreshold` and then return successfully. The expected outcome is that the fallback does not run, while the slow-call rate increases. When testing ignored exceptions, verify the exception does not increment failed calls and that samples are calculated strictly from recorded outcomes. Every test should clarify which outcome type it is measuring.

## 10. Operational Rules

- Place fallback handling after the protected supplier region whenever the circuit breaker needs to observe real dependent-service errors.
- Catch exceptions inside the supplier only when you intentionally define the substitute value as a successful outcome of the protected operation.
- Configure recorded and ignored exceptions explicitly; do not use fallbacks as a substitute for classification policy.
- Track failure rate, slow-call rate, rejection counts, and fallback success rate as distinct metrics.
- Distinguish fallbacks triggered by supplier failures from fallbacks triggered when the breaker is `OPEN`; the two cases have different operational meanings.
- In `HALF_OPEN`, rely on supplier outcomes to judge recovery; a successful fallback does not prove the service is healthy again.
- Test both circuit breaker state and the final result received by the business layer.

When you reconcile both outcome layers accurately, operations teams can tell whether the application is answering via fallbacks during a dependency outage, or whether the dependency has recovered and calls are genuinely succeeding. This helps calibrate circuit breaker thresholds, improve backup data handling, and avoid masking cascading failures behind superficially successful responses.
