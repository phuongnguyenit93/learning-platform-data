# OPEN: Rejecting Calls and CallNotPermittedException

In the Circuit Breaker pattern, the OPEN state temporarily trips the call path to a service showing signs of unhealthiness. When the breaker transitions to OPEN, the application rejects new calls immediately on the caller side. The call to the dependent service is not executed, preventing the system from continuing to send load to a slow or unavailable service.

With Spring Cloud CircuitBreaker using Resilience4j, this rejection is typically represented by **CallNotPermittedException**. Properly understanding the OPEN state and this exception helps distinguish a call blocked by the breaker from a call that crossed the network and failed, while also designing appropriate fallbacks and monitoring.

## 1. Where Does OPEN Sit in the State Machine?

A Circuit Breaker typically operates across three primary states:

| State | Behavior | Transition Condition |
|---|---|---|
| CLOSED | Permits calls to reach the dependent service and records outcomes. | Transitions to OPEN when the failure rate or slow call rate exceeds the threshold after sufficient minimum samples. |
| OPEN | Rejects new calls immediately on the caller side; does not execute the call to the dependent service. | After the configured wait duration, the breaker can transition to HALF_OPEN. |
| HALF_OPEN | Permits only a limited number of probe calls to check whether the service has recovered. | If probe outcomes are good enough, returns to CLOSED; if still bad, goes back to OPEN. |

While in CLOSED, the breaker observes call outcomes in a sliding window. The window can be based on call count or a time interval. Parameters such as minimum number of samples, failure rate threshold, and slow call rate threshold determine when the breaker opens. Thus, OPEN is the result of evaluating collected samples, not a state triggered by just any single exception.

After transitioning to OPEN, the breaker stays in this state for the duration configured by **waitDurationInOpenState**. Once the wait duration expires, it allows recovery verification via HALF_OPEN. With the default configuration where automatic transition is not enabled, the actual state transition usually happens when the next call arrives after the wait duration has elapsed. If **automaticTransitionFromOpenToHalfOpenEnabled** is enabled, Resilience4j can automatically transition the state using a scheduler without waiting for a new call.

The diagram below illustrates the basic flow:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure or slow call rate exceeds threshold
    OPEN --> HALF_OPEN: Wait duration expires
    HALF_OPEN --> CLOSED: Probe calls meet requirements
    HALF_OPEN --> OPEN: Probe calls continue to fail
~~~

## 2. What Happens When the Circuit Breaker Is OPEN?

Suppose the order service calls the inventory service. The inventory service repeatedly responds slowly, causing the slow call rate or failure rate to exceed the threshold. The Circuit Breaker for inventory calls transitions from CLOSED to OPEN.

From that point onward, a new request needing to read inventory goes through the Circuit Breaker's execution permission check. Because the state is OPEN, the breaker rejects the request immediately. The HTTP call, WebClient, or corresponding client does not run. The application does not wait for a connection, timeout, or error response from the inventory service for this rejected request.

This behavior has three implications:

- **Reduces load on the dependent service:** the troubled service stops receiving additional traffic from protected calls.
- **Frees caller-side resources:** processing threads, connections, and wait time are not wasted on a call known not to be ready for execution.
- **Limits error propagation:** a failing service is less likely to cause cascading thread exhaustion or increased latency across its callers.

OPEN does not heal the dependent service by itself. It only pauses sending calls and creates a cool-down period before controlled retries. During that time, the application must decide whether to return fallback data, use a cache, return a meaningful error to the client, or apply another behavior appropriate to the business logic.

## 3. Understanding CallNotPermittedException

Resilience4j throws **io.github.resilience4j.circuitbreaker.CallNotPermittedException** when the Circuit Breaker does not grant permission to execute a call. The most common case is when the breaker is OPEN. This exception can also appear when the breaker is HALF_OPEN if all allocated probe slots have been used and none have completed to free up capacity for further checks.

The key point is that the exception is raised at the Circuit Breaker layer before the dependent service call is executed. Therefore:

| Scenario | Typical Symptom | Meaning |
|---|---|---|
| Circuit Breaker is OPEN | **CallNotPermittedException** | The call was blocked locally; no new call was sent to the dependent service. |
| Dependent service fails to respond in time | Timeout or corresponding error | The call was permitted and execution encountered an issue. |
| Dependent service returns an error | Client exception or business error | The call was executed and received an error result. |
| Bulkhead is at capacity | **BulkheadFullException** | The Bulkhead concurrency limit rejected the call; this is a different protection mechanism from Circuit Breaker. |

Therefore, you should not record **CallNotPermittedException** as if the dependent service just returned a new error. A rejected call is not a new failure sample of the dependent service in the sliding window. Resilience4j can separately track the count of not-permitted calls, helping observe how actively the Circuit Breaker is protecting the system.

When handling the exception, log the Circuit Breaker name and the state or call context clearly. Avoid logging only a generic message such as "inventory service error," because that makes it hard for operators to distinguish an actual service failure from the application proactively blocking calls.

## 4. Configuring OPEN with Spring Cloud CircuitBreaker and Resilience4j

Spring Cloud CircuitBreaker provides an abstraction for applications to invoke a Circuit Breaker by name. Resilience4j is the underlying implementation that can be configured beneath that abstraction. The following example specifically configures a Circuit Breaker named **catalog**:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> catalogCircuitBreaker() {
        return factory -> factory.configure(
            builder -> builder.circuitBreakerConfig(
                CircuitBreakerConfig.custom()
                    .slidingWindowType(
                        CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                    .slidingWindowSize(20)
                    .minimumNumberOfCalls(10)
                    .failureRateThreshold(50)
                    .waitDurationInOpenState(Duration.ofSeconds(15))
                    .permittedNumberOfCallsInHalfOpenState(3)
                    .automaticTransitionFromOpenToHalfOpenEnabled(false)
                    .build()
            ),
            "catalog"
        );
    }
}
~~~

The values in this example have the following meanings:

- **slidingWindowType(COUNT_BASED)** and **slidingWindowSize(20)** instruct the breaker to evaluate at most the 20 most recent outcomes.
- **minimumNumberOfCalls(10)** requires at least 10 recorded calls before evaluating the failure rate.
- **failureRateThreshold(50)** sets the open-circuit threshold at a 50% failure rate.
- **waitDurationInOpenState(Duration.ofSeconds(15))** sets the wait duration in OPEN to 15 seconds.
- **permittedNumberOfCallsInHalfOpenState(3)** limits the number of probe calls when transitioning to HALF_OPEN.
- **automaticTransitionFromOpenToHalfOpenEnabled(false)** keeps the transition to HALF_OPEN triggered by the next call after the wait duration expires.

For example: once at least 10 calls are available for evaluation, if at least 5 calls fail, the failure rate reaches 50% and the breaker can transition to OPEN. Over the next 15 seconds, new calls are rejected. After the wait duration, the breaker transitions to HALF_OPEN and grants at most three probe slots. If the probe outcomes meet the criteria, the breaker closes again; otherwise, it reopens to continue protecting the service.

This is an illustrative configuration to explain the mechanism. In real deployments, choose the window, minimum sample count, thresholds, and wait duration according to each service's traffic, normal latency, recovery capability, and business requirements. A window that is too small can cause state changes from a few anomalous samples; an OPEN duration that is too short can create repeated retry waves before the service has recovered.

## 5. Handling Fallbacks When Calls Are Rejected

With Spring Cloud CircuitBreaker's synchronous API, you can provide a fallback function to **run**. This function receives the exception that caused the call to fail, including **CallNotPermittedException**:

~~~java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;

class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;
    private final ProductCache productCache;

    CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    Product getProduct(String id) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.getProduct(id),
            error -> {
                if (error instanceof CallNotPermittedException) {
                    // Circuit Breaker blocked the call before calling Catalog.
                    log.warn("Circuit Breaker catalog is rejecting calls, id={}", id);
                } else {
                    // The call was executed but encountered another error.
                    log.warn("Failed to fetch Catalog data, id={}", id, error);
                }

                return productCache.findById(id)
                    .orElseThrow(
                        () -> new CatalogUnavailableException(id, error));
            }
        );
    }
}
~~~

The example assumes **ProductCache** returns **Optional<Product>** and **CatalogUnavailableException** is an application-defined business exception. When the Circuit Breaker is OPEN, the fallback looks up data in the cache. If the cache has no data, the application throws a deliberate error rather than fabricating an empty object that could be mistaken for valid data.

The fallback function in the example receives all errors from the protected call, so it is necessary to distinguish **CallNotPermittedException** from timeouts or client errors. If business logic requires different handling, branch by error type as shown above. Do not assume every error means the Circuit Breaker is OPEN.

The fallback must also be independent of the troubled service. If the fallback calls the same Catalog service over the same network path, or calls another dependent service experiencing cascading failures, it can recreate the problem the Circuit Breaker is trying to prevent. Cached data or fallback responses must have clear staleness and validity rules; never silently return stale data if business requirements do not allow it.

## 6. Reactive Calls Must Also Handle the OPEN State

For WebFlux applications, Spring Cloud CircuitBreaker provides ReactiveCircuitBreaker. Rejected calls are propagated in the reactive pipeline as error signals. You can handle **CallNotPermittedException** in the fallback function:

~~~java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

class ReactiveCatalogService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveCatalogClient catalogClient;
    private final ProductCache productCache;

    Mono<Product> getProduct(String id) {
        return circuitBreakerFactory.create("catalog").run(
            catalogClient.getProduct(id),
            error -> {
                if (error instanceof CallNotPermittedException) {
                    return productCache.findById(id)
                        .map(Mono::just)
                        .orElseGet(() -> Mono.error(
                            new CatalogUnavailableException(id, error)));
                }

                return Mono.error(error);
            }
        );
    }
}
~~~

In a reactive pipeline, errors are not necessarily thrown immediately at the method call line; they may be emitted when the publisher is subscribed to. Therefore, handle errors using reactive operators or the fallback provided by the abstraction. Avoid calling **block()** just to catch exceptions, as doing so negates non-blocking benefits and can block processing threads.

## 7. Distinguishing OPEN from Timeout, Retry, and Bulkhead

Protection mechanisms can be used together, but they reflect different situations:

- **Circuit Breaker OPEN:** rejects calls because previous outcomes show the dependent service is unhealthy.
- **Timeout or TimeLimiter:** limits the wait time of a call that was permitted to execute. Timeouts may be counted as failures or slow calls depending on Circuit Breaker configuration.
- **Retry:** retries a failed operation according to a policy of attempt counts and backoff intervals. When the Circuit Breaker is OPEN, continuous retries usually just receive more **CallNotPermittedException** errors without helping the dependent service recover.
- **Bulkhead:** limits concurrent calls or resources dedicated to a part of the system. When capacity is exhausted, the Bulkhead may reject calls with its own exception such as **BulkheadFullException**.

The ordering of combined decorators affects which exception the calling layer receives and how retries interact with the Circuit Breaker. Configure and observe them as separate mechanisms, and avoid retry policies that hit a weakened service with extra load right as it begins to recover.

## 8. Monitoring and Operating the OPEN State

A properly functioning Circuit Breaker can stay OPEN while the dependent service is experiencing an outage. Therefore, merely seeing the OPEN state is not enough to conclude the configuration is wrong. You need to monitor the state, rejected call count, and dependent service health together.

When integrating Micrometer with Resilience4j, you can observe Circuit Breaker metrics such as successful, failed, and not-permitted call counts; failure or slow call rates; current state; and state transition counts. Exact metric names and tags depend on version, registry, and integration configuration. Tag data with the Circuit Breaker name, such as **catalog**, to distinguish each dependent service.

A useful monitoring dashboard typically includes:

| Signal | Question to Answer |
|---|---|
| Current state and state transition count | Is the breaker CLOSED, OPEN, or HALF_OPEN? Is it flapping open and closed? |
| Not-permitted call count | How many requests were rejected during this interval? |
| Failure rate and slow call rate | Did errors or increased latency trigger the open circuit? |
| Fallback count and cache hit rate | Is the fallback behavior meeting demand? |
| Latency and dependent service status | Has the service recovered stably enough to accept traffic again? |

State transition logs should include the Circuit Breaker name, previous and new states, and transition timestamp. For individual rejected requests, log at an appropriate level or aggregate using metrics; avoid logging repeated stack traces for every **CallNotPermittedException**, as high traffic can put extra load on the logging system.

Alerts should combine time spent in OPEN, rejected call volume, dependent service errors, and fallback rate. If OPEN only appears briefly and then returns stably to CLOSED, the breaker may be doing its job properly. If it repeatedly cycles CLOSED → OPEN → HALF_OPEN → OPEN, check service health, thresholds, sliding window, wait duration, and probe outcomes.

## 9. Common Implementation Mistakes

1. **Confusing rejected exceptions with dependent service errors.** **CallNotPermittedException** indicates the breaker did not permit execution. Use separate logs and metrics to determine how many calls actually reached the service.
2. **Aggressive retries while the breaker is OPEN.** Retries continue to be rejected, increasing processing and logging load without verifying recovery.
3. **Fallback calling the same failing service.** This defeats the protective purpose of OPEN and can create additional failing dependency chains.
4. **Inappropriate OPEN duration.** Too short causes retries before the service recovers; too long forces a healthy service to wait unnecessarily before receiving traffic.
5. **Not limiting probe calls in HALF_OPEN.** Too many probes can create a traffic spike right as the service begins recovering.
6. **Undefined fallback data quality.** Stale cache, default values, or empty responses can cause business inaccuracies without clear rules.

## 10. Practice Scenario

An order service calls the Catalog service to fetch product information. The **catalog** Circuit Breaker is configured with a window of 20 calls, minimum 10 samples, 50% failure rate threshold, 15-second OPEN duration, and up to three probe calls in HALF_OPEN.

Sequence of events:

1. Initially the breaker is CLOSED. Calls are forwarded to Catalog and outcomes are recorded in the sliding window.
2. After at least 10 samples are collected, the failure rate reaches 50%. The breaker transitions to OPEN.
3. For the next 15 seconds, new requests are rejected with **CallNotPermittedException**. The Catalog client is not called for these requests; the application attempts to use the cache or returns a fallback error.
4. Once the wait duration expires, the breaker transitions to HALF_OPEN. Up to three probe requests are permitted to reach Catalog. Requests exceeding the allocated slots may still be rejected.
5. If the probe outcomes meet the allowed threshold, the breaker returns to CLOSED and resumes recording normal outcomes. If the failure rate still exceeds the threshold, it returns to OPEN and begins a new wait period.

When analyzing the scenario, answer three questions: which requests actually reached Catalog, which requests were rejected by the Circuit Breaker, and what conditions caused the breaker to transition from OPEN to HALF_OPEN and then back to CLOSED or OPEN. This forms the basis for reading logs, metrics, and verifying whether fallbacks were triggered properly.

## Conclusion

OPEN is the state that temporarily breaks the call path to a dependent service showing signs of unhealthiness. **CallNotPermittedException** indicates the Circuit Breaker rejected the call before the service invocation was executed. When combining Spring Cloud CircuitBreaker with Resilience4j, configure sensible wait durations and probe counts, handle fallbacks according to the specific error type, and monitor states and rejected call counts to evaluate service protection effectiveness.
