# CLOSED: Allowing Calls and Recording Outcomes

## Position of CLOSED in the State Model

In Spring Cloud Circuit Breaker, the Circuit Breaker tracks the outcomes of calls to a dependent service to limit cascading failures when that service is slow or unavailable. With Resilience4j, `CLOSED` is the normal operating state: new calls are permitted to reach the target service, and the outcome of each call is recorded in a *sliding window*.

A new Circuit Breaker typically starts in `CLOSED`. This state does not mean the dependent service is guaranteed to be healthy. It only indicates that the circuit breaker does not yet have enough evidence, according to the configured thresholds, to block calls. Therefore, calls in `CLOSED` can still succeed, fail, or take too long.

Basic processing flow:

1. The application requests a call to the dependent service.
2. The Circuit Breaker checks its state. While `CLOSED`, it allows the call to proceed.
3. The call executes through the HTTP client, SDK, or corresponding component.
4. Once the call completes, the Circuit Breaker classifies the outcome and updates the metrics in the sliding window.
5. After reaching the minimum number of calls, the Circuit Breaker calculates the failure rate and slow call rate. If an open-circuit threshold is reached or exceeded, it transitions to `OPEN`.

Calls that were permitted before the state transition may still be in flight. The Circuit Breaker does not automatically cancel in-flight calls; it decides whether to permit new calls.

## Which Outcomes Are Recorded?

Resilience4j tracks call outcomes in the sliding window. Key details include:

- **Success:** the call completes normally.
- **Failure:** the call ends with an exception configured to be recorded as a failure.
- **Slow call:** execution duration exceeds `slowCallDurationThreshold`, even if the call ultimately succeeds.

The failure rate is calculated from the number of failed calls divided by the number of counted calls in the window. The slow call rate is calculated similarly from the number of slow calls. Exceptions configured to be ignored do not increase the failure rate. If `recordExceptions` is declared, keep in mind that exceptions not in that list are treated as successes by the circuit breaker; choose the list according to the service's actual failure contract.

There are two common sliding window types:

| Window Type | How It Works | When Suitable |
| --- | --- | --- |
| `COUNT_BASED` | Retains outcomes of a fixed number of the most recent calls, such as 10 calls. | Traffic is relatively steady and you want to evaluate based on call count. |
| `TIME_BASED` | Aggregates outcomes over a time interval, such as the last 10 seconds. | You want time-based evaluation, especially when traffic fluctuates. |

`minimumNumberOfCalls` specifies the minimum number of calls required before calculating rates to decide whether to open the circuit. For example, with `slidingWindowSize = 10` and `minimumNumberOfCalls = 5`, the Circuit Breaker can evaluate after the first five calls; it does not need to wait for all ten outcomes. Until the minimum number of calls is reached, the failure rate does not yet have sufficient basis to trigger a state transition.

## Configuring Thresholds for the CLOSED State

Example configuration of a Circuit Breaker named `inventory` in `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

With this configuration, the Circuit Breaker records up to the 10 most recent outcomes and begins evaluating once at least 5 calls have been made. If the failure rate reaches 50% or higher, or the slow call rate reaches 60% or higher, it can transition from `CLOSED` to `OPEN`. For instance, if three out of the first five eligible calls fail, the failure rate is `3 / 5 = 60%`, exceeding the 50% threshold.

`waitDurationInOpenState` and `permittedNumberOfCallsInHalfOpenState` control behavior in subsequent states. They are placed alongside the `CLOSED` configuration because they belong to the same Circuit Breaker, but they do not alter how outcomes are recorded while the circuit is closed.

When choosing thresholds, consider actual traffic. With low traffic, waiting to reach `minimumNumberOfCalls` can take a long time; with high traffic, a window that is too small may overreact to a brief spike of errors. The slow call threshold should also align with the response time the application can tolerate.

## Integrating with Spring Calls and Fallbacks

When using Resilience4j's annotation integration in Spring Boot, you can place `@CircuitBreaker` on the method that calls the dependent service:

```java
@Service
public class InventoryService {
    private final InventoryClient client;

    public InventoryService(InventoryClient client) {
        this.client = client;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "availabilityFallback")
    public String getAvailability(String sku) {
        return client.fetchAvailability(sku);
    }

    public String availabilityFallback(String sku, Throwable cause) {
        return "UNKNOWN";
    }
}
```

The name `inventory` must match the instance name in the configuration. The fallback method has the same return type and business parameters as the original method, followed by an additional exception parameter. The value `UNKNOWN` is just an example: the application must clearly define how unknown data is represented so the caller does not mistake it for a valid result.

While the Circuit Breaker remains `CLOSED`, calls still reach `InventoryClient`. If a call fails and a matching fallback exists, Resilience4j can invoke the fallback to produce an alternative response. Executing the fallback does not automatically mean the Circuit Breaker has opened; the state transition decision still depends on the recorded outcomes and configured thresholds. When using Spring AOP-based annotations, calls must go through the Spring proxy; internal calls using `this.someMethod()` within the same bean may bypass the interceptor.

## Reactive Calls

With Reactor, you can apply `CircuitBreakerOperator` to a `Mono` or `Flux`. Use `transformDeferred` to apply the circuit breaker per subscription:

```java
Mono<String> availability = webClient.get()
    .uri("/inventory/{sku}", sku)
    .retrieve()
    .bodyToMono(String.class)
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

When the circuit is `CLOSED`, the subscription is allowed to run, and completion or error signals are used to update metrics. In a reactive pipeline, fallbacks should be handled with operators such as `onErrorResume` according to business rules; avoid blocking the thread with `block()` just to obtain the result.

## Distinguishing Circuit Breaker from Timeout and Bulkhead

In the `CLOSED` state, a slow call is still allowed to continue until the client or another timeout mechanism terminates it. The Circuit Breaker records a slow call after an outcome is received, but by itself it neither enforces a time limit nor cancels an in-flight request.

- **Timeout / TimeLimiter** limits how long to wait for a call.
- **Bulkhead** limits the number of concurrent calls or resources used for a dependent service.
- **Circuit Breaker** observes outcomes and blocks new calls when the failure or slow call rate exceeds thresholds.

Combining these mechanisms helps the application limit wait times, control concurrency, and prevent continuing to overload a degraded service.

## Monitoring Activity in CLOSED

You should monitor the current state along with the counts of successful, failed, slow, and rejected calls. Resilience4j provides metrics and event publishers for integration with logs, Micrometer, and monitoring systems. Example of reading some metrics from an instance:

```java
CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

log.info(
    "state={}, failureRate={}, slowCallRate={}, failedCalls={}, successfulCalls={}",
    circuitBreaker.getState(),
    metrics.getFailureRate(),
    metrics.getSlowCallRate(),
    metrics.getNumberOfFailedCalls(),
    metrics.getNumberOfSuccessfulCalls()
);
```

Before `minimumNumberOfCalls` is reached, `getFailureRate()` may return `-1` to indicate there is not yet an eligible rate to evaluate. Therefore, dashboards should distinguish the insufficient-samples state from a 0% failure rate. When investigating a state transition, correlate Circuit Breaker events with HTTP client logs, response times, and concurrent request counts.

## Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| `CLOSED` means the dependent service is healthy. | It only indicates that the circuit breaker still permits calls; failures can still occur. |
| A single failure opens the circuit. | The Circuit Breaker evaluates over a window and only computes rates after reaching the minimum number of calls. |
| Calling a fallback automatically opens the circuit. | Fallbacks handle results at the application layer; state transitions depend on metrics and thresholds. |
| The Circuit Breaker automatically times out in-flight requests. | Timeouts must be configured on the HTTP client or TimeLimiter; the Circuit Breaker does not cancel already-permitted calls. |

When designing the `CLOSED` state, ensure the sliding window reflects actual traffic, `minimumNumberOfCalls` is reliable enough, the exception list matches the failures you want to guard against, and the slow call threshold aligns with your SLA. This forms the foundation for the Circuit Breaker to detect degradation early and transition to `OPEN` on time, reducing the risk of cascading failures in a Spring Cloud system.
