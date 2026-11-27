# slowCallDurationThreshold and Slow Call Classification

In Spring Cloud Circuit Breaker using Resilience4j, a circuit breaker can open when a dependent service responds too slowly, even if calls still return successful results. The `slowCallDurationThreshold` property defines the duration above which a call is considered slow. Resilience4j aggregates slow calls in the **sliding window**; when this rate reaches `slowCallRateThreshold` and the sample count reaches `minimumNumberOfCalls`, the circuit breaker can transition from `CLOSED` to `OPEN`.

The key point is that call duration and call outcome are two independent dimensions. A call can be successful yet slow, failed yet fast, or both slow and failed. Understanding this classification helps configure the circuit breaker according to actual response quality rather than relying solely on exceptions.

## What does `slowCallDurationThreshold` define?

`slowCallDurationThreshold` is the duration threshold for a call monitored by the circuit breaker. When a call's execution time exceeds this threshold, Resilience4j marks that call as a **slow call**. The value is usually declared as a Duration, such as `2s`, `500ms`, or `1500ms`.

This threshold applies to each individual call. It answers the question: *how long must a single call take to be considered slow?* It does not decide the acceptable percentage of slow calls across the entire window. That belongs to `slowCallRateThreshold`.

| Property | Meaning | Example |
| --- | --- | --- |
| `slowCallDurationThreshold` | Duration above which a call is classified as slow. | `2s`: calls exceeding 2 seconds are considered slow. |
| `slowCallRateThreshold` | Maximum percentage of slow calls in the window before the circuit opens. | `50`: open the circuit when slow call rate reaches 50% or higher. |
| `minimumNumberOfCalls` | Minimum number of calls required before calculating rates. | `10`: require at least 10 recorded calls. |
| `slidingWindowType` and `slidingWindowSize` | Defines the set of calls used for statistics. | Last 20 calls or last 30 seconds. |

For example, a product catalog service has a response SLA of around 1 second. The development team chooses `slowCallDurationThreshold: 2s` to identify calls that far exceed the expected response time. A call that takes 2.5 seconds yet returns valid data is still a slow call, even though no exception occurs.

## Classifying calls by duration and outcome

Resilience4j evaluates duration and outcome independently. The following table illustrates four cases when the duration threshold is 2 seconds:

| Duration and outcome | Duration classification | Outcome classification |
| --- | --- | --- |
| Returns data after 400 ms | Not slow | Success |
| Returns data after 3 seconds | Slow | Success |
| Throws exception after 300 ms | Not slow | Failure if the exception is recorded as an error |
| Throws exception after 4 seconds | Slow | Failure if the exception is recorded as an error |

A call that is both slow and failed is counted in both slow call statistics and failure statistics. However, the two rates are calculated separately:

- `failureRate` reflects the percentage of calls classified as failed.
- `slowCallRate` reflects the percentage of calls exceeding `slowCallDurationThreshold`.

Therefore, a service can have a low `failureRate` yet a high `slowCallRate`. This is common when a dependent service still manages to process requests, but latency increases due to overload, slow database queries, or resource contention.

## Slow call rate condition for opening the circuit breaker

Resilience4j calculates the slow call rate over the results remaining in the sliding window:

\[
\text{slowCallRate} = \frac{\text{number of slow calls}}{\text{total recorded calls in the window}} \times 100\%
\]

Only when the sample count reaches `minimumNumberOfCalls` does the circuit breaker evaluate the rate. If `slowCallRate` meets or exceeds `slowCallRateThreshold`, the circuit transitions to `OPEN`. This condition is independent of the opening condition for `failureRateThreshold`.

Suppose the configuration has:

- `minimumNumberOfCalls = 10`
- `slowCallDurationThreshold = 2s`
- `slowCallRateThreshold = 50`

After 10 calls are in the window, the following cases occur:

| Calls exceeding 2 seconds | Slow call rate | Decision based on slow calls |
| ---: | ---: | --- |
| 3 out of 10 | 30% | Do not open circuit yet based on slow call rate. |
| 5 out of 10 | 50% | Threshold reached, transition to `OPEN`. |
| 7 out of 10 | 70% | Threshold exceeded, transition to `OPEN`. |

For example, 5 calls take 2.8 seconds yet all succeed, and the remaining 5 calls take 200 ms. The failure rate can be 0%, while the slow call rate is 50%. If the configuration and minimum sample count are satisfied, the circuit breaker still opens to relieve pressure on the slow-responding service.

The call that causes the rate to cross the threshold must complete so the circuit breaker can record its duration and outcome. If that call succeeds, its own result can still be returned to the caller; the `OPEN` state will block subsequent calls. The circuit breaker does not cancel in-flight calls when transitioning state.

## Configuration in Spring Cloud with Resilience4j

The following example configures the `catalogService` instance in `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogService:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        failureRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

In this configuration, the circuit breaker tracks up to the 20 most recent calls. Once at least 10 calls are recorded, if at least half of the calls in the window exceed 2 seconds, the slow-call opening condition is satisfied. The failure rate has its own threshold of 60%; reaching either rate threshold is enough for the circuit breaker to open.

The name `catalogService` must match the ID the application uses when creating the circuit breaker. With Spring Cloud CircuitBreaker, you can invoke it via the factory and supply a fallback:

```java
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

    public Product findProduct(String sku) {
        return circuitBreakerFactory.create("catalogService").run(
            () -> catalogClient.findProduct(sku),
            error -> cachedProduct(sku)
        );
    }

    private Product cachedProduct(String sku) {
        return Product.unavailable(sku);
    }
}
```

When the circuit breaker is `OPEN`, new calls are rejected and the fallback function is invoked. The fallback can also be invoked when a dependency call throws an error. When a call is only marked slow yet succeeds, its successful outcome is still returned; the slow call classification updates the statistics so the circuit breaker can decide state for subsequent calls.

## Does exception classification affect slow calls?

The `recordExceptions` and `ignoreExceptions` properties control how the circuit breaker classifies exceptions when computing the failure rate. They do not replace `slowCallDurationThreshold` and do not decide whether a call is slow.

Configuration example:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogService:
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
        ignoreExceptions:
          - com.example.catalog.ProductNotFoundException
```

With this configuration, `SocketTimeoutException` and `IOException` are counted as failures per the recorded list; `ProductNotFoundException` is ignored in circuit breaker statistics. Exceptions matching neither the recorded list nor the ignored list are typically treated as successful outcomes. Because ignored exceptions are not ordinary success or failure outcomes recorded into the window, you should not assume they are counted in `slowCallRate` by default. If you also need to monitor latency for ignored outcomes, measure additionally at the client layer or test the behavior of the specific Resilience4j version in use.

When more complex classification rules are needed, you can configure predicates in Java via `CircuitBreakerConfig`, such as recording only certain exception types as failures. Verify both statistical groups in tests: recorded failures and calls exceeding the duration threshold.

## Distinguishing slow call from timeout

`slowCallDurationThreshold` only marks a call as slow after an actual duration is available to record. It does not set a wait limit and does not automatically cancel an in-flight call. If a call takes 8 seconds while the slow call threshold is 2 seconds, the circuit breaker can record it as slow after the call completes at the 8th second.

Timeouts serve a different purpose: limiting how long an operation waits. Timeouts can be configured at the HTTP client, WebClient, or using a `TimeLimiter` suited to the call model. When a timeout triggers, the operation may be cancelled or terminate with an exception depending on the client and integration. That exception counts toward the failure rate if error recording rules permit; the duration can also cause the call to be classified as slow.

When combining both mechanisms, choose a slow call threshold aligned with your SLA and set a timeout to cap maximum wait duration. For example, if normal calls usually finish under 500 ms, you might set the slow call threshold at 2 seconds and the timeout at 4 seconds. That way, the circuit breaker detects slow trends before the timeout cuts off calls. Verify decorator ordering and how the client measures timing to ensure the circuit breaker observes the exact time span of the operation being protected.

## Reactive calls and execution time

In reactive flows, constructing a `Mono` or `Flux` typically does not perform I/O immediately. The operation starts only upon subscription. Therefore, the duration to monitor is the time of the circuit-breaker-decorated call during subscription until the stream ends with a completion or error signal.

In reactive Spring Cloud CircuitBreaker, create the circuit breaker from `ReactiveCircuitBreakerFactory` and apply it directly to the dependency call's publisher:

```java
@Service
public class ReactiveCatalogService {
    private final ReactiveCircuitBreakerFactory<?, ?> factory;
    private final ReactiveCatalogClient client;

    public ReactiveCatalogService(
            ReactiveCircuitBreakerFactory<?, ?> factory,
            ReactiveCatalogClient client) {
        this.factory = factory;
        this.client = client;
    }

    public Mono<Product> findProduct(String sku) {
        return factory.create("catalogService").run(
            client.findProduct(sku),
            error -> Mono.just(Product.unavailable(sku))
        );
    }
}
```

Ensure the publisher executes inside the protected block. If you only measure a segment that constructs the publisher without including execution time, metrics will not reflect the dependency's actual latency. In multi-step flows, where the circuit breaker is placed determines which portion of work is included in the duration.

## Monitoring and tuning thresholds

When the circuit breaker opens due to slow calls, find the root cause of latency rather than simply raising the threshold. Observe dependency response times, slow call counts, failure rate, circuit breaker state, and traffic within the same timeframe. Micrometer alongside a compatible monitoring system can provide call metrics by state and outcome to support analysis.

Some principles when tuning:

- Choose `slowCallDurationThreshold` based on SLAs, normal latency percentiles (such as p95 or p99), and user-tolerable wait times.
- Set `slowCallRateThreshold` to define degradation severe enough to warrant opening the circuit; too low a rate may cause short-term fluctuations to trigger frequently.
- Choose `minimumNumberOfCalls` appropriate to traffic. If the minimum sample count is too high relative to calls in the window, the circuit breaker may fail to evaluate rates.
- Ensure a sensible relationship between client timeouts and the slow call threshold. If the timeout is much shorter than the slow call threshold, calls may time out before being classified as slow under the intended threshold.
- Separately test slow successful calls, fast failures, and slow failures to confirm metrics reflect actual system behavior.

Common configuration mistakes include treating slow calls like exceptions, assuming the circuit breaker aborts slow requests on its own, or looking only at failure rate while ignoring slow call rate. By clearly distinguishing duration, outcome, and window rates, the development team can detect degrading services earlier, protect caller resources, and limit cascading latency across a Spring Cloud system.
