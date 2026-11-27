# Circuit Breaker Fails to Open Due to Insufficient Samples or Misconfigured ID

A circuit breaker can remain in the `CLOSED` state even when the dependent service is returning errors. Two early causes to check are **not having enough samples to evaluate the rate** and **configuring a different ID than the one the application actually creates**. Additionally, exceptions might be ignored, error responses might be treated as successful outcomes, or a reactive pipeline might recover from errors before the circuit breaker observes them.

With Spring Cloud CircuitBreaker using Resilience4j, you should not start by immediately lowering `failureRateThreshold`. Verify the correct circuit breaker instance, runtime configuration, number of recorded outcomes, and evaluation timing. This article presents a diagnostic workflow applicable to synchronous services, WebClient/Reactor, and OpenFeign.

## 1. Understand the Condition for the Circuit Breaker to Transition to OPEN

In the `CLOSED` state, the circuit breaker allows calls to pass through and collects outcomes. Resilience4j only calculates the failure rate or slow-call rate after the number of outcomes in the sliding window reaches `minimumNumberOfCalls`.

For example:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
```

With the configuration above:

- The window holds up to the 20 most recent outcomes.
- At least 10 outcomes are required in the window before evaluating the rate.
- Once enough samples are collected, the circuit breaker opens if the failure rate reaches or exceeds 50%.

If there have only been 8 calls and all 8 failed, the observed rate is 100%, but the circuit breaker does not yet have 10 samples to evaluate. Staying `CLOSED` in this situation is the expected behavior per configuration.

The basic conditions can be expressed as follows:

\[
\text{Eligible for evaluation} \iff N_{recorded} \geq minimumNumberOfCalls
\]

\[
\text{Open circuit on failure} \iff failureRate \geq failureRateThreshold
\]

Where `N_recorded` is the number of outcomes recorded in the current window. It does not necessarily equal the total number of requests arriving at the application: requests rejected before the supplier executes and ignored exceptions do not contribute as regular failures.

## 2. Distinguish Between slidingWindowSize and minimumNumberOfCalls

These two properties are frequently confused:

| Property | COUNT_BASED | TIME_BASED |
|---|---|---|
| `slidingWindowSize` | Number of most recent calls retained in the window. | Window duration in seconds. |
| `minimumNumberOfCalls` | Minimum number of outcomes required before evaluation. | Still the minimum number of outcomes required within the time window. |

With `COUNT_BASED`, configuring `slidingWindowSize: 20` and `minimumNumberOfCalls: 10` allows evaluation to begin once 10 outcomes are recorded, without waiting for 20. Once the window is full, new outcomes replace the oldest ones.

With `TIME_BASED`, suppose `slidingWindowSize: 10` and `minimumNumberOfCalls: 20`. The circuit breaker requires at least 20 outcomes within the last 10 seconds. If an instance receives only one call per second on average, this condition is hard to meet. The circuit breaker may remain `CLOSED` even if most calls fail because the window never accumulates enough samples.

Verify that `minimumNumberOfCalls` does not exceed the achievable capacity of the window. For a count-based window, the minimum cannot exceed the window size. For a time-based window, estimate the per-instance call volume within the configured duration, not the total cluster traffic.

## 3. Check Whether the ID Created in Code Matches the YAML

Resilience4j applies instance configuration by ID. If the code creates a circuit breaker via `create("inventory")`, while the YAML only declares `inventoryReadClient`, the specific configuration for `inventoryReadClient` will not automatically apply to the `inventory` instance.

Example of a potential ID mismatch:

```java
return circuitBreakerFactory.create("inventory").run(
    () -> inventoryClient.getStock(sku),
    error -> Stock.unavailable(sku)
);
```

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryReadClient:
        slidingWindowSize: 20
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
```

Here, the code creates the ID `inventory`, whereas the custom configuration is placed under `inventoryReadClient`. The `inventory` circuit breaker may be using the default configuration or another config; the values under `inventoryReadClient` do not control that instance.

Use the same ID where the breaker is created and where the configuration is declared:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 20
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
```

The ID must be consistent across Java Customizers, properties, event listeners, metrics dashboards, and alert rules. Use stable IDs scoped by dependency and operation group, such as `inventory-read` or `payment-authorize`; avoid embedding SKUs, user IDs, or request IDs in the ID.

## 4. With OpenFeign, Do Not Guess the Circuit Breaker Name

When Spring Cloud CircuitBreaker is enabled for OpenFeign, the breaker name may be generated from the client and method according to the naming rules of the Spring Cloud version in use. Therefore, do not assume the breaker name always equals the `name` or `contextId` of `@FeignClient`.

Example client:

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryReadClient"
)
public interface InventoryReadClient {
    Stock getStock(String sku);
}
```

A Feign call may generate a breaker ID tied to both the client and the method. This rule can be customized via `CircuitBreakerNameResolver`; some versions also support converting IDs to alphanumeric format. When configuring Resilience4j, obtain the **actual ID generated at runtime** and use that exact name in `resilience4j.circuitbreaker.instances`.

Verification procedure:

1. Check that `spring.cloud.openfeign.circuitbreaker.enabled` is enabled if you want OpenFeign calls to go through Spring Cloud CircuitBreaker.
2. Determine whether a custom `CircuitBreakerNameResolver` is present.
3. Check the `alphanumeric-ids` option if supported by your version.
4. Observe logs, events, or metrics to retrieve the actual breaker name.
5. Match that exact name against the instance key in YAML.

Group support does not automatically mean every method of a Feign client shares a single circuit breaker ID. Group name and breaker ID are two separate pieces of information; check how the factory/provider in your version uses them.

## 5. Check Runtime Configuration Instead of Only Reading YAML

A syntactically valid YAML file does not prove the configuration has been bound to the running instance. Multiple profiles, external configuration files, environment variables, or other configuration sources might override the values.

Check the following:

- Active profiles and loaded `application-{profile}.yml` files.
- Whether the instance name in YAML matches the runtime ID.
- Whether `default` and `instances` configurations are misunderstood or overridden.
- Whether a Java `Customizer` configures the same ID.
- Precedence order between properties and Java Customizers according to the Spring Cloud release train in use.
- Whether environment variables or externalized configuration override the values.

For example, when you need a base configuration and an instance-specific override:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventory:
        baseConfig: default
        minimumNumberOfCalls: 5
```

The `inventory` instance uses the base configuration and overrides `minimumNumberOfCalls`. If a Java Customizer or another profile also configures this ID, determine which source takes effect. Avoid declaring the same parameter in multiple places without a clear precedence convention.

Do not publicly expose configuration or environment endpoints just for a quick look. If using Actuator for diagnostics, expose and secure endpoints according to your application's security policy; display only the information operators need.

## 6. Verify That Exceptions Are Actually Recorded as Failures

Enough calls do not guarantee enough failures. Resilience4j classifies outcomes based on how the supplier terminates and the exception configuration.

Cases to distinguish:

| Scenario | Common Impact on Circuit Breaker |
|---|---|
| Supplier throws a recorded exception | Increases failure count in the window. |
| Supplier throws an exception listed in `ignoreExceptions` | Counted as neither a success nor a failure. |
| Supplier completes normally | Counted as a success, even if the return value indicates a business failure. |
| Circuit breaker rejects before supplier runs | Produces a rejection (`CallNotPermittedException`), not a new dependency failure. |
| Supplier returns a 5xx HTTP response as a normal object | May be counted as a success if the client does not convert the response to an exception and no corresponding result predicate is configured. |

Example classification configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
```

When declaring `recordExceptions`, confirm the actual exceptions thrown by the client. If the HTTP client wraps `SocketTimeoutException` inside another exception, the configuration may not match as intended. With `recordExceptions` rules, exceptions not in the list may be treated as successes unless ignored or handled by another predicate; check the semantics of the Resilience4j version in use.

Do not ignore timeouts or connection errors just to lower the failure rate. Doing so can prevent the circuit breaker from opening even when the dependency is unresponsive.

## 7. Check Whether the HTTP Client Converts Error Responses to Exceptions

The circuit breaker tracks the outcome of the supplier and does not inherently treat every HTTP status as an error. Behavior depends on the client:

- Feign typically uses an `ErrorDecoder` to convert unsuccessful responses into exceptions; a custom decoder can alter this behavior.
- `WebClient.retrieve()` converts 4xx/5xx responses into `WebClientResponseException` by default unless handled otherwise.
- `exchangeToMono()` lets the application inspect the response manually and may return a normal object for error statuses.
- Another HTTP client might return a `ResponseEntity` or response wrapper without throwing an exception.

If the supplier returns an `InventoryResponse(status=503)` object and completes normally, the circuit breaker may record a success. Clearly decide which statuses should be converted into exceptions or use an appropriate result evaluation predicate. Do not mechanically turn all 4xx responses into failures; validation or authorization errors may not reflect dependency health.

## 8. Check Fallback Placement in Reactive Pipelines

In Reactor, operator ordering can prevent the circuit breaker from seeing the original error.

This example places the fallback before the circuit breaker:

```java
Mono<Stock> result = inventoryClient.getStock(sku)
    .onErrorResume(error -> Mono.just(Stock.unavailable(sku)))
    .transform(CircuitBreakerOperator.of(circuitBreaker));
```

`onErrorResume` turns the exception into a normally completing publisher before the circuit breaker observes it. Consequently, the breaker may record a success even though the underlying HTTP call failed.

If you want the circuit breaker to record the original error before falling back, place the operator first:

```java
Mono<Stock> result = inventoryClient.getStock(sku)
    .transform(CircuitBreakerOperator.of(circuitBreaker))
    .onErrorResume(error -> Mono.just(Stock.unavailable(sku)));
```

Check similarly for `onErrorReturn`, `onErrorComplete`, `retry`, and other error-handling operators. In reactive code, verify that the circuit breaker is attached to the right subscription and that the supplier is actually subscribed to; merely constructing a `Mono` without subscribing will not trigger any calls.

## 9. Read Metrics to Identify Missing Samples or Misclassification

When integrating Micrometer and Actuator, inspect metrics under the exact breaker ID. Specific meter names and tags can vary by Resilience4j/Micrometer version, so inspect the actual list at `/actuator/metrics` or the Prometheus endpoint rather than guessing names.

Useful indicators:

- Current state of the breaker.
- Number of successful and failed calls.
- Number of rejected calls (`not permitted`).
- Failure rate and slow-call rate.
- Number of recorded calls in the window if exposed by the metric/version.
- Number of state transitions and corresponding events.

| Symptom | Possibility to Check |
|---|---|
| Many requests arrive at the service, but breaker call count is low | Requests are not passing through that breaker, wrong ID, or a code path bypasses the wrapper. |
| Call count increases, but failure count stays at 0 | Supplier may be completing normally, error responses are not converted to exceptions, or exceptions are ignored. |
| Failures increase, but breaker has not evaluated yet | `minimumNumberOfCalls` has not been reached in the window. |
| Metrics for the configured ID do not change | Code may be creating a different ID, or the instance config is not being used. |
| `not permitted` increases after the breaker opens | The breaker is blocking requests; these are not new supplier failures. |
| Slow-call rate is low despite high latency | Slow-call threshold has the wrong unit, wrong ID, or calls are outside the observed breaker. |

If using an event listener, log `event.getCircuitBreakerName()` along with the state transition to see the runtime ID. Register the listener once during configuration or instance creation; do not register it per request, as that produces duplicate logs.

## 10. Ordered Diagnostic Procedure

When a breaker does not open as expected, follow these steps in order to avoid changing thresholds before understanding the root cause:

1. **Confirm requests pass through the breaker:** inspect the code path, factory, and ID passed to `create(...)` or the OpenFeign resolver.
2. **Obtain the runtime ID:** inspect breaker events, metrics, or logs; do not infer the name from the service name.
3. **Cross-check YAML:** the key under `resilience4j.circuitbreaker.instances` must match the runtime ID.
4. **Verify effective configuration:** check profiles, external config, default config, Java Customizers, and precedence order.
5. **Count samples:** compare the number of outcomes in the window against `minimumNumberOfCalls`; for TIME_BASED, calculate per-instance traffic within that time window.
6. **Check exception classification:** verify timeouts/5xx responses are converted to exceptions and not excluded by `ignoreExceptions` or predicates.
7. **Check reactive operators:** ensure fallbacks do not swallow errors before the circuit breaker if original errors need to be tracked.
8. **Check thresholds:** once the conditions above are verified, compare failure rate/slow-call rate against the threshold.
9. **Check state and timing:** confirm the breaker has not been forced open/closed, reset, or switched to another instance.

## 11. Scenario to Reproduce Insufficient Samples

Suppose the configuration is:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 8
        failureRateThreshold: 50
        waitDurationInOpenState: 5s
```

You can verify with a test that controls supplier outcomes:

1. Send 7 calls and make all 7 fail with a recorded exception.
2. Confirm the breaker remains `CLOSED` because there are only 7 samples.
3. Send the 8th call and make it fail.
4. Once 8 samples are collected, the failure rate is 100%, exceeding the 50% threshold; confirm the breaker transitions to `OPEN`.
5. Send the next call while the circuit is `OPEN`; confirm the supplier does not execute and the caller receives a rejection or fallback as designed.

When writing tests, use the exact same instance the service uses. If the test creates a standalone `CircuitBreaker` while the service calls the factory to create another instance, the observed behavior does not represent the runtime breaker.

## 12. Scenario to Reproduce an ID Mismatch

To detect an ID mismatch, you can intentionally create a discrepancy between code and YAML in an integration test:

1. Configure instance `inventory-read` with a low sample threshold.
2. Have the service call `circuitBreakerFactory.create("inventory")`.
3. Send enough failures and inspect the runtime configuration of ID `inventory`.
4. Confirm that the custom configuration of `inventory-read` does not control ID `inventory`.
5. Fix the code or YAML so both sides use the same ID.
6. Re-run the test and confirm the breaker opens at the configured threshold.

Put IDs in constants to prevent typos:

```java
public final class CircuitBreakerIds {
    private CircuitBreakerIds() {}

    public static final String INVENTORY_READ = "inventory-read";
}
```

Then use `CircuitBreakerIds.INVENTORY_READ` in the service and declare the same name in YAML. If the ID is generated by an OpenFeign resolver, inspect the actual resolver name instead of replacing it with a guessed name.

## 13. What Not to Do During Investigation

- Do not drop `minimumNumberOfCalls` to 1 just to force the breaker to open immediately; a single error can cause overly sensitive decisions.
- Do not lower `failureRateThreshold` before confirming that exceptions are being recorded.
- Do not ignore timeouts or connection errors just to make dashboards look less red.
- Do not generate a new ID per request to "isolate errors"; that starves the breaker of samples and increases cardinality.
- Do not aggressively retry `CallNotPermittedException`; it is a rejection from the protection mechanism.
- Do not place a fallback before the circuit breaker in a reactive pipeline if you want the breaker to record the original error.
- Do not assume total traffic across multiple replicas is aggregated into a single local sliding window.
- Do not conclude the breaker is not working solely from a fallback response; inspect the state and supplier execution.

## 14. Checklist Before Concluding

- [ ] Requests actually pass through Spring Cloud CircuitBreaker.
- [ ] The runtime ID is verified via events, metrics, or logs.
- [ ] The ID in YAML matches the runtime ID exactly.
- [ ] The runtime configuration uses the right profile and is not overridden by another source.
- [ ] `minimumNumberOfCalls` is achievable within the sliding window.
- [ ] `minimumNumberOfCalls` does not exceed `slidingWindowSize` for COUNT_BASED.
- [ ] Exceptions from the dependency are recorded as failures.
- [ ] No ignored exception or predicate unintentionally filters out errors.
- [ ] HTTP error responses are converted to exceptions or explicitly classified.
- [ ] Reactive fallbacks do not swallow errors before the circuit breaker.
- [ ] Metrics are read under the right breaker ID and right application instance.
- [ ] Tests use the exact circuit breaker instance that the service uses.

When a circuit breaker fails to open, verify the right ID and sufficient samples first, and only then check error classification, client responses, and fallback placement. `minimumNumberOfCalls` determines when evaluation begins; the ID determines which configuration applies; exception mapping determines which outcomes count as failures. Checking these three points using metrics and a controlled reproduction test will help pinpoint the true cause without making protection policies overly sensitive or masking real errors.
