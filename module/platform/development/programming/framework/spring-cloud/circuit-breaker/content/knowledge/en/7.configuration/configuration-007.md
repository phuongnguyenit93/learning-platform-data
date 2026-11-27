# Setting Thresholds, Durations, and Explicit Duration Units

A circuit breaker protects a service effectively only when its thresholds and durations accurately reflect the characteristics of the dependent call. If the failure threshold is too low, a few transient errors can cause the circuit to open repeatedly. If the threshold is too high or the window requires too many samples, the application can continue calling a failing service for a long time. If time units are misconfigured, a timeout of a few seconds can become a few milliseconds or several minutes.

In Spring Cloud CircuitBreaker with Resilience4j, you must explicitly specify values such as `failureRateThreshold`, `slowCallRateThreshold`, `slowCallDurationThreshold`, `waitDurationInOpenState`, and `timeoutDuration`. Rate values are percentages; durations should be expressed explicitly using `java.time.Duration` in Java or unit suffixes in YAML. This lesson guides you on how to read, choose, and verify those parameters in the **SPRING_CLOUD_CIRCUIT_BREAKER** module.

## 1. Distinguishing rate thresholds, duration thresholds, and sample counts

Circuit breaker configuration parameters often appear together, yet they represent three different kinds of quantities:

| Group | Typical parameter | Unit | Effect |
|---|---|---|---|
| Rate | `failureRateThreshold` | Percentage (%) | Specifies the failure rate sufficient to open the circuit. |
| Rate | `slowCallRateThreshold` | Percentage (%) | Specifies the slow call rate sufficient to open the circuit. |
| Duration | `slowCallDurationThreshold` | `Duration` | Defines how long a call takes before being counted as slow. |
| Duration | `waitDurationInOpenState` | `Duration` | Defines how long the circuit breaker stays `OPEN` before allowing probes per the configured mechanism. |
| Count | `slidingWindowSize` | Number of calls or seconds depending on window type | Defines the scope of data used for statistics. |
| Count | `minimumNumberOfCalls` | Number of calls | Specifies the minimum number of outcomes required before evaluating rates. |
| Duration | `timeoutDuration` | `Duration` | Limits the wait time of an asynchronous task supported by TimeLimiter. |

Do not confuse `slidingWindowSize` with `minimumNumberOfCalls`. With a `COUNT_BASED` window, both are call counts, yet they have different meanings. With `TIME_BASED`, `slidingWindowSize` is in seconds, while `minimumNumberOfCalls` remains the minimum number of outcomes.

The circuit breaker only begins evaluating rates after the window has collected the minimum number of samples. Once enough samples exist, the circuit can open if either the failure rate or the slow call rate reaches its respective threshold. For example, if `failureRateThreshold` is 50%, 5 failures out of 10 recorded calls reach the threshold. If only 4 outcomes exist, the observed rate is 100%, yet 10 samples have not been reached, so that rate cannot trigger a decision under this configuration.

## 2. Choosing failureRateThreshold and slowCallRateThreshold

`failureRateThreshold` is the failure percentage threshold. `slowCallRateThreshold` is the slow call percentage threshold. Both are typically set between 0 and 100. A lower value makes the circuit breaker more sensitive to errors or latency; a higher value requires a larger anomaly rate to open the circuit.

Example:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        failureRateThreshold: 50
        slowCallRateThreshold: 60
```

With this configuration, once enough samples exist, the circuit breaker can open if at least 50% of recorded calls fail or at least 60% of calls are considered slow. These are two independent conditions; either rate reaching its threshold can trigger opening the circuit.

Failure rate and slow call rate reflect two different kinds of degradation:

- A dependent service returning connection errors or exceptions drives up the failure rate.
- A dependent service still returning successful results but too slowly drives up the slow call rate.

For example, an inventory service returns HTTP 200 but takes 4 seconds to respond. If the ordering flow only has a 1-second budget for the inventory lookup step, this call still causes harm even without an HTTP error. `slowCallDurationThreshold` determines whether that call counts as slow; `slowCallRateThreshold` decides what proportion of slow calls is enough to open the circuit.

Do not pick thresholds solely based on a popular number. Use actual latency and error rate metrics, business response time targets, and dependency criticality. A data read service that can fall back to cache may have different thresholds from an authentication or payment service.

## 3. Setting slowCallDurationThreshold from the latency budget

`slowCallDurationThreshold` is the duration from which a call is classified as slow. This value should be less than or equal to the portion of the latency budget the application allocates to that dependency, accounting for remaining processing time in other steps.

Suppose an order API has a 1,500 ms response time target. After subtracting input validation, database writes, and response serialization time, the application can allocate only around 500 ms to the inventory service. You might begin evaluating with a slow call threshold around 400 ms or 500 ms, then adjust based on real metrics.

| Budget for dependent call | Illustrative slow threshold | Notes |
|---:|---:|---|
| 300 ms | 250 ms | Used for calls requiring very fast responses. |
| 500 ms | 400 ms | Leaves a buffer before exhausting the budget. |
| 2 seconds | 1.5 seconds | Can suit tasks with higher latency. |

These are illustrative starting choices, not standard thresholds for every system. Measure the client's latency distribution, inspect p95/p99, and determine where slowness starts affecting user experience or exhausting resources. If the threshold is set below normal latency, the circuit breaker may open even when the service is operating normally.

## 4. Setting waitDurationInOpenState and probing behavior

`waitDurationInOpenState` specifies how long the circuit breaker remains in the `OPEN` state before transitioning to the phase that allows testing recovery. Under typical configuration, after this wait duration the circuit breaker transitions to `HALF_OPEN` on the next call or via the automatic transition mechanism if the corresponding option is enabled.

Example:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

The circuit waits 15 seconds in `OPEN`, then permits up to 3 probe calls in `HALF_OPEN`. If the probe outcomes meet requirements, the circuit can return to `CLOSED`; if failures continue, the circuit returns to `OPEN` per Resilience4j's policy.

An open duration that is too short can cause the application to retry repeatedly before the dependent service has recovered. A duration that is too long delays restoring traffic even after the service is healthy. Consider the dependency's typical recovery time, retry policies at other layers, and the impact of continuing to reject requests.

`waitDurationInOpenState` is not a single-call timeout. It does not bound the duration of an in-flight HTTP request. Client timeouts and `TimeLimiter` are separate configurations.

## 5. Expressing durations in YAML

In `application.yml`, Resilience4j duration properties can be expressed using duration syntax with unit suffixes. Always write units explicitly so readers never have to guess.

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slowCallDurationThreshold: 750ms
        waitDurationInOpenState: 12s
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
```

Common notations:

| YAML value | Meaning |
|---|---|
| `250ms` | 250 milliseconds |
| `750ms` | 750 milliseconds |
| `2s` | 2 seconds |
| `3m` | 3 minutes |
| `1h` | 1 hour |
| `PT1.5S` | 1.5 seconds in ISO-8601 Duration format |

Spring Boot supports converting duration strings with units and ISO-8601 format into `java.time.Duration` for bound properties. When a suffix is omitted, a numeric value may be interpreted according to the property's or binder's default unit; that makes configuration hard to read and error-prone. Therefore, explicitly write `ms`, `s`, `m`, or ISO-8601 format rather than bare numbers.

Do not write `500` expecting 500 milliseconds if it could mean 500 seconds. Write `500ms`. Similarly, do not write `2` when you mean 2 seconds; write `2s`.

## 6. Expressing durations in Java with Duration

In Java, use `java.time.Duration` to represent time intervals. This API makes units explicit right where the value is constructed:

```java
import java.time.Duration;

Duration.ofMillis(500);       // 500 ms
Duration.ofSeconds(2);        // 2 s
Duration.ofMinutes(1);        // 1 minute
Duration.ofSeconds(1).plusMillis(250); // 1.25 s
Duration.parse("PT2S");      // 2 s in ISO-8601
```

Example Resilience4j configuration in Java:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerConfiguration {

    @Bean
    public Customizer<Resilience4JCircuitBreakerFactory> circuitBreakerDefaults() {
        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(CircuitBreakerConfig.custom()
                    .slidingWindowSize(20)
                    .minimumNumberOfCalls(10)
                    .failureRateThreshold(50)
                    .slowCallRateThreshold(60)
                    .slowCallDurationThreshold(Duration.ofMillis(750))
                    .waitDurationInOpenState(Duration.ofSeconds(12))
                    .permittedNumberOfCallsInHalfOpenState(3)
                    .build())
                .timeLimiterConfig(TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(2))
                    .build())
                .build()
        );
    }
}
```

Reading the Java values by unit:

- `Duration.ofMillis(750)` is 750 ms, or 0.75 seconds.
- `Duration.ofSeconds(12)` is how long the circuit stays `OPEN` before probing.
- `Duration.ofSeconds(2)` is the TimeLimiter timeout for an integrated asynchronous task.

When converting from external configuration into Java, you can use `Duration.parse("PT2S")` for ISO-8601 strings. For user-supplied values, validate format and valid bounds before passing them into configuration. Avoid concatenating numbers with unit strings manually when you can use the explicit `Duration` API.

## 7. Distinguishing client timeout, TimeLimiter, and circuit breaker

These three mechanisms often appear together in a single call, yet they have distinct responsibilities:

| Mechanism | Example parameter | What it bounds |
|---|---|---|
| HTTP client timeout | connect timeout, response/read timeout | Time spent waiting to establish a connection or receive a response from the server. |
| Resilience4j TimeLimiter | `timeoutDuration` | Wait duration of an asynchronous task wrapped by TimeLimiter. |
| Circuit breaker | `slowCallDurationThreshold` | Threshold to classify a call as slow in statistics. |
| Circuit breaker | `waitDurationInOpenState` | Duration to keep the circuit in the `OPEN` state. |

For example, the client has a 3-second response timeout, TimeLimiter has a 2-second timeout, and `slowCallDurationThreshold` is 1 second. A call completing in 1.4 seconds may be classified as slow even though the client did not time out. A call taking over 2 seconds may be terminated by TimeLimiter before the client waits the full 3 seconds, if the operation and cancellation mechanism support it. Once the circuit is `OPEN`, new calls can be rejected immediately without waiting for the client timeout.

TimeLimiter does not guarantee that all underlying I/O operations are cancelled. Specifically, timing out a `Future` does not necessarily stop the network request if the HTTP client does not support proper cancellation. Configure timeouts on the client and verify resource release behavior.

## 8. A complete YAML configuration for the inventory dependency

The following example combines window settings, failure threshold, slow call threshold, and explicit unit durations:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 750ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 12s
        permittedNumberOfCallsInHalfOpenState: 3

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
```

Interpreting the configuration:

1. Resilience4j retains at most the 20 most recent outcomes and evaluates rates only after at least 10 outcomes.
2. The circuit can open when the failure rate reaches 50% or when the rate of calls taking 750 ms or more reaches 60%.
3. When the circuit opens, it waits 12 seconds before allowing probes per the state transition mechanism.
4. In `HALF_OPEN`, up to 3 probe calls are permitted.
5. TimeLimiter sets a 2-second wait timeout for supported asynchronous tasks.

These example values do not automatically guarantee a total request timeout of 2 seconds. Total duration also depends on client timeouts, retries, internal processing, and how mechanisms are nested.

## 9. Choosing values from real metrics

When configuring a new dependency, you can start with the following sequence:

1. **Determine the latency budget:** from the API's response target, subtract internal processing time and other dependencies to find the budget allocated to this call.
2. **Measure normal latency:** observe p50, p95, p99, and latency spikes to choose `slowCallDurationThreshold` above normal operating range yet below the limit that impacts business outcomes.
3. **Measure baseline error rate:** choose `failureRateThreshold` so ordinary random errors do not open the circuit, while real outages are detected promptly.
4. **Choose window and minimum samples:** use per-instance traffic to estimate how long it takes to accumulate enough samples. With `TIME_BASED`, check how many calls actually occur within that interval.
5. **Choose open duration:** weigh how long the dependency needs to recover against the impact of rejecting additional requests.
6. **Set client timeouts:** ensure connection and response waits are bounded; if using TimeLimiter, verify tasks are cancellable and resources are released.
7. **Monitor and tune:** compare circuit open counts, failure rate, slow call rate, and fallback counts against real user behavior.

Do not change many thresholds at once when investigating an incident. Change one related group of values, record a hypothesis, and observe before/after metrics to understand the effect of the adjustment.

## 10. Common mistakes when setting thresholds and Duration

| Symptom | Possible cause | How to check |
|---|---|---|
| Circuit opens almost immediately | `failureRateThreshold` is too low or `minimumNumberOfCalls` is too small. | Compare failure rate and sample count in the window. |
| Circuit stays closed even when the service is very slow | `slowCallDurationThreshold` is too high or not enough samples yet. | Measure call durations and inspect window configuration. |
| Timeouts happen almost instantaneously | Wrote a bare number without a unit suffix or confused milliseconds with seconds. | Check binding type and actual bound `Duration` value. |
| Circuit stays `OPEN` too long | `waitDurationInOpenState` exceeds recovery needs. | Compare wait duration with the dependency's actual recovery time. |
| Circuit oscillates continuously between OPEN and HALF_OPEN | Wait/probing interval is too short, service is still unstable, or thresholds are too sensitive. | Observe probe outcomes and recovery time. |
| TimeLimiter times out yet requests keep running | Task or HTTP client does not fully support cancellation. | Check cancellation, sockets, and client-side resources. |
| Environments behave differently | Configuration uses bare numbers or inconsistent units. | Write explicit unit suffixes and inspect bound configuration. |

## 11. Pre-deployment configuration checklist

Before deploying a circuit breaker to production, confirm:

- [ ] Rate thresholds are understood as percentages and fall within valid ranges.
- [ ] `minimumNumberOfCalls` and `slidingWindowSize` fit actual traffic.
- [ ] `slowCallDurationThreshold` is grounded in the dependency's latency budget.
- [ ] `waitDurationInOpenState` matches recovery time and probing policy.
- [ ] Every duration property in YAML has an explicit unit suffix.
- [ ] Every duration value in Java uses `Duration.ofMillis`, `ofSeconds`, `ofMinutes`, or `Duration.parse`.
- [ ] HTTP client timeouts and TimeLimiter are distinguished and do not substitute for one another.
- [ ] Tests cover success, error, slow call, timeout, and recovery scenarios.
- [ ] Metrics allow observing failure rate, slow call rate, and circuit breaker state.

Setting thresholds and durations with explicit units ensures the circuit breaker responds deliberately to dependency errors and latency. Use readable configuration grounded in operational metrics and verify bound values before deployment so a small unit mistake does not completely alter service protection behavior.
