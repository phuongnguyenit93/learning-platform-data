# Combining CircuitBreakerConfig with TimeLimiterConfig

In the Spring Cloud Circuit Breaker integration with Resilience4j, `CircuitBreakerConfig` and `TimeLimiterConfig` solve two different parts of the same call to a dependent service. `CircuitBreakerConfig` decides when to stop sending requests based on failure rate, slow call rate, and a statistical window. `TimeLimiterConfig` limits how long to wait for a supported task to complete. When combined for the same instance, the application gains both a per-call time limit and a mechanism to trip subsequent calls when the service repeatedly has issues.

The two configurations must be designed together. If the timeout is too long, callers still wait a long time before receiving an error. If the timeout is too short, normal requests can be terminated early and inflate the failure rate. If you only have a timeout without a circuit breaker, the application can still keep sending new requests to an overloaded service.

## Role of each configuration

| Configuration | Responsibility | Example properties |
|---|---|---|
| `CircuitBreakerConfig` | Evaluates outcomes in the window, transitions between `CLOSED`, `OPEN`, `HALF_OPEN` | `slidingWindowSize`, `failureRateThreshold`, `slowCallRateThreshold`, `waitDurationInOpenState` |
| `TimeLimiterConfig` | Limits task wait time and configures Future cancellation on expiration | `timeoutDuration`, `cancelRunningFuture` |

`timeoutDuration` is the time limit for a TimeLimiter-protected execution. When it expires, TimeLimiter terminates waiting with a timeout exception. The circuit breaker receives this error outcome and records it according to the active exception classification policy. Once enough samples are collected per `minimumNumberOfCalls`, the breaker evaluates the failure rate and slow call rate; if either rate reaches its corresponding threshold, the breaker transitions to `OPEN`.

TimeLimiter does not itself decide that the circuit breaker must open. A timeout can increase the failed call count, but opening the breaker still depends on the minimum number of calls and thresholds in `CircuitBreakerConfig`. Conversely, the circuit breaker can open due to other exceptions or the slow call rate, even if no request has hit the timeout.

## Distinguishing timeout and slow-call threshold

`timeoutDuration` and `slowCallDurationThreshold` are both time-related, but they have different meanings:

- `timeoutDuration` determines when TimeLimiter stops waiting for the task.
- `slowCallDurationThreshold` determines the duration at which a call is classified as slow in circuit breaker statistics.

For example, set `slowCallDurationThreshold` to 2 seconds and `timeoutDuration` to 3 seconds. A call completing after 2.5 seconds can succeed yet still be recorded as a slow call. A call that does not complete within 3 seconds will be terminated by TimeLimiter with a timeout; if the timeout exception is recorded as a failure, that call contributes to the failure rate. Its execution duration may also exceed the slow threshold and therefore contribute to the slow-call rate.

If `slowCallDurationThreshold` is set longer than `timeoutDuration`, requests terminated by TimeLimiter at the timeout limit may be recorded as errors without reaching the threshold to be classified as slow calls. Choose both values according to monitoring goals: timeout is the wait cap, whereas slow-call threshold is the marker for degraded performance.

## Combined configuration using Java Customizer

With Spring Cloud Circuit Breaker Resilience4j, an instance can be configured using `Resilience4JCircuitBreakerFactory`. The `configure` method accepts a configuration built from `Resilience4JConfigBuilder`, containing both the circuit breaker and time limiter.

```java
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

@Configuration
public class CircuitBreakerConfiguration {

    @Bean
    public Customizer<Resilience4JCircuitBreakerFactory> catalogConfiguration() {
        return factory -> factory.configure(builder -> builder
                .circuitBreakerConfig(CircuitBreakerConfig.custom()
                        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                        .slidingWindowSize(20)
                        .minimumNumberOfCalls(10)
                        .failureRateThreshold(50)
                        .slowCallRateThreshold(50)
                        .slowCallDurationThreshold(Duration.ofSeconds(2))
                        .waitDurationInOpenState(Duration.ofSeconds(10))
                        .permittedNumberOfCallsInHalfOpenState(3)
                        .build())
                .timeLimiterConfig(TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(3))
                        .cancelRunningFuture(true)
                        .build())
                .build(), "catalog");
    }
}
```

In the example, the `catalog` instance uses a 20-call window and begins evaluation only once at least 10 calls have occurred. The breaker opens when the failure rate or slow-call rate reaches 50%. After 10 seconds in `OPEN`, the breaker can attempt recovery with up to three calls in `HALF_OPEN`. TimeLimiter limits the wait duration to three seconds and requests cancellation of the running Future upon expiration.

The ID passed to `factory.configure(..., "catalog")` must match the ID the application uses when creating the circuit breaker. If you configure instance `catalog` while code calls `factory.create("catalogService")`, the two configurations are not bound to the same instance name as intended.

## Configuration via application.yml

Per-instance configuration can be declared in `application.yml`. The instance names under `circuitbreaker.instances` and `timelimiter.instances` need to match so both configuration sections apply to the same backend.

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 50
        slowCallDurationThreshold: 2s
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      catalog:
        timeoutDuration: 3s
        cancelRunningFuture: true
```

The YAML snippet expresses the same policy as the Java example. When opting for properties configuration, check the Spring Cloud Circuit Breaker and Resilience4j versions in use to ensure the properties are supported. Avoid declaring conflicting values for the same instance in both a Java Customizer and the configuration file if the team has not clearly established which configuration source takes effect.

## Using the configured instance

Once the factory receives the configuration, the service retrieves the instance using the exact ID `catalog` and wraps the dependent call inside a supplier:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public Product findProduct(String productId) {
        CircuitBreaker circuitBreaker = circuitBreakerFactory.create("catalog");

        return circuitBreaker.run(
                () -> catalogClient.findProduct(productId),
                error -> Product.unavailable(productId)
        );
    }
}
```

The `catalogClient.findProduct` call sits inside the supplier so it is executed through the circuit breaker. When a request times out or the breaker rejects execution because it is `OPEN`, the fallback overload returns `Product.unavailable`. The fallback gives the caller an alternative result; it does not erase the failure outcome of the original call from circuit breaker statistics.

TimeLimiter can only bound tasks on execution paths supported by the integration. When working with a Future or CompletionStage, let the integration recognize and track task completion. Do not wrap a `CompletableFuture` and return it as a plain value if the circuit breaker only observes the moment the supplier creates the Future; otherwise the breaker may record success before the asynchronous work actually finishes. With reactive APIs, use `ReactiveCircuitBreaker` and publisher timeout mechanisms appropriate to the stack version in use; do not assume a synchronous call timeout and a `Mono`/`Flux` timeout execute the same way.

## Understanding the impact of cancelRunningFuture

`cancelRunningFuture(true)` instructs TimeLimiter to cancel the running Future when a timeout occurs. This is a task cancellation signal at the Future layer; it does not guarantee that a request already sent to a remote system stops immediately. Actual termination depends on the executor, thread interruption support, and whether the HTTP client supports request cancellation.

Therefore, configure timeouts on the underlying HTTP client or RPC library to bound connection establishment and response read times. TimeLimiter guards the wait duration at the execution layer; client timeouts help control the network request itself. When both layers use different deadlines, choose a sensible ordering so errors from the client have a chance to surface before TimeLimiter terminates the task.

Do not enable Future cancellation without considering its impact on the task. If the task performs an operation with side effects, canceling on the caller side does not mean the operation on the remote system was rolled back. For data-writing transactions, design idempotency, unique request keys, or status-lookup mechanisms to handle cases where the caller times out while the dependent service still completes.

## Choosing timeouts and circuit breaker thresholds

Start from the dependent service's normal response time, the caller's response-time requirements, and network-layer timeouts. A reference configuration could be:

| Parameter | Example value | Purpose |
|---|---:|---|
| HTTP client response timeout | 2.5 seconds | Bounds wait time for a response from the service |
| `slowCallDurationThreshold` | 2 seconds | Records prolonged requests as slow calls |
| `TimeLimiter.timeoutDuration` | 3 seconds | Bounds wait time at the protected execution layer |
| `waitDurationInOpenState` | 10 seconds | Duration the breaker stays `OPEN` before attempting recovery |

These are only examples to illustrate the relationship between timeout layers. Actual values must be based on latency percentiles, load, resource limits, and the overall request time budget. Do not set timeouts longer than callers can usefully wait; likewise, do not set them so tight around normal latency that valid requests repeatedly time out.

## Verifying combined behavior

After configuring, test the scenarios below and observe return values, exceptions, metrics, and state transition events:

1. **Fast and successful call:** the supplier returns data normally; TimeLimiter does not expire and the circuit breaker records a success.
2. **Slow call that still completes before timeout:** the caller receives data; if duration exceeds `slowCallDurationThreshold`, the call contributes to the slow-call rate.
3. **Call exceeding timeout:** TimeLimiter raises a timeout; if the exception is recorded as a failure, the failure rate increases. If duration also exceeded the slow threshold, the slow-call rate may increase simultaneously.
4. **Consecutive timeouts:** once `minimumNumberOfCalls` is reached and the failure rate hits `failureRateThreshold`, the breaker transitions to `OPEN`.
5. **Breaker is OPEN:** the supplier is rejected before sending a new request; the fallback is invoked if configured.
6. **Breaker is HALF_OPEN:** only permitted probes are executed. A probe timeout is evaluated as a call outcome and can send the breaker back to `OPEN`.
7. **Canceled Future:** confirm the task inside the application reacts to cancellation; also check the HTTP client and dependent service to see whether the network request actually stopped.

When analyzing metrics, examine `failureRate` and `slowCallRate` separately. Timeouts are usually failure signals and can simultaneously be slow calls, yet the two rates are compared against two independent thresholds. If the breaker opens too often, inspect actual response times, client timeouts, `timeoutDuration`, `slowCallDurationThreshold`, `minimumNumberOfCalls`, and the exception classification policy before changing thresholds.
