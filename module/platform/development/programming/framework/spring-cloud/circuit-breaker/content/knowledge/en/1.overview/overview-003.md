# Failing Fast and Maintaining Availability When Downstream Dependencies Fail

In a Spring Cloud system composed of multiple services, a request often passes through several components before returning a result. For example, an order service needs to call an inventory service to confirm product availability. If the inventory service responds slowly, processing threads in the order service must wait longer. As request volume grows, threads and connections can become exhausted; requests that do not even need inventory also start slowing down or failing. A localized issue can therefore escalate into a cascading failure.

A circuit breaker helps limit that impact. When the number of failed or slow calls exceeds a threshold, it temporarily stops sending requests to the dependent service and fails fast on subsequent calls. The application can return fallback data, a controlled degraded result, or an appropriate message. This mechanism is part of the resilience strategy in Spring Cloud CircuitBreaker, commonly implemented with Resilience4j.

## Why Fail Fast?

If every call to a troubled service waits out a long timeout, the calling system can accumulate many in-flight requests. Threads, HTTP connections, and memory become tied up, reducing capacity to serve even healthy features.

Failing fast has three goals:

- **Isolating incidents:** limiting the number of calls continuing to hit a failing dependency.
- **Freeing resources:** avoiding holding threads and connections during unnecessary wait times.
- **Maintaining core functionality:** allowing the application to return fallback results or continue processing parts that do not depend on the failing service.

A circuit breaker does not fix the dependent service, does not guarantee every request will succeed, and does not replace timeouts. It decides when calls should be allowed to proceed based on observed outcomes. Timeouts limit how long a single call may wait; bulkheads limit resources dedicated to a group of calls; fallbacks define how the application responds when a call cannot complete normally.

A typical processing flow:

~~~mermaid
flowchart LR
    A[Incoming Service Request] --> B[Circuit Breaker]
    B -->|CLOSED or HALF_OPEN| C[Dependent Service]
    C -->|Success| D[Normal Result]
    C -->|Error or Too Slow| E[Fallback]
    B -->|OPEN: Fail Fast| E
    E --> F[Controlled Degraded Result]
~~~

## The Three States of a Circuit Breaker

A circuit breaker has three primary states. The state determines whether a call is forwarded to the dependent service or rejected fast.

| State | Behavior | Transition Condition |
|---|---|---|
| **CLOSED** | Allows calls to reach the dependent service and records outcomes. | When the failure rate or slow call rate exceeds the threshold after enough samples are collected, transitions to OPEN. |
| **OPEN** | Sends no new calls to the dependent service; fails fast so the application handles fallback. | After a configured wait duration, transitions to HALF_OPEN. Some configurations can automatically transition when the wait duration expires. |
| **HALF_OPEN** | Allows only a small number of probe calls to test whether the service has recovered. | If the probe calls meet requirements, transitions back to CLOSED. If errors or slow calls continue to exceed thresholds, returns to OPEN. |

**CLOSED** is the normal operating state. Each call is tracked to compute failure rates and slow calls in a sliding window. Not every single error opens the circuit breaker; the decision also depends on the minimum sample count and configured thresholds.

**OPEN** is the tripped state. New calls are rejected immediately without waiting for the dependent service. With Resilience4j, this case is typically represented by a **CallNotPermittedException**. The calling layer can use a fallback to return cached data or a temporary status.

**HALF_OPEN** tests recovery without generating a sudden surge of load. For example, only three probe calls are allowed. If they succeed according to configured criteria, the circuit breaker closes. If the service is still failing, the circuit opens again and continues waiting.

HALF_OPEN should not be treated as proof that the service is completely healthy. It is only a limited probe; you must continue monitoring error rates, latency, and traffic after the circuit closes again.

## Sliding Windows and Determining Circuit-Opening Thresholds

Resilience4j uses a **sliding window** to compute outcomes of recent calls. There are two window types:

| Window Type | Calculation | When Appropriate |
|---|---|---|
| **COUNT_BASED** | Evaluates the outcomes of the most recent N calls. | Traffic is relatively steady or you want decisions based on call count. |
| **TIME_BASED** | Evaluates outcomes over a recent time interval. | Traffic fluctuates and you want to evaluate incidents over time. |

For example, a COUNT_BASED window of size 20 has a minimum call count of 10 and a failure rate threshold of 50%. Resilience4j only starts evaluating the rate once at least 10 outcomes exist. If at least half of the calls in the evaluated sample set fail, the circuit breaker can transition to OPEN. The window continues sliding as new outcomes arrive, so older outcomes gradually drop out of the calculation.

Several important parameters include:

- **slidingWindowType:** selects COUNT_BASED or TIME_BASED.
- **slidingWindowSize:** number of calls or window duration, depending on the selected type.
- **minimumNumberOfCalls:** minimum number of samples before calculating rates.
- **failureRateThreshold:** maximum failure percentage before opening the circuit.
- **slowCallDurationThreshold:** duration from which a call is considered slow.
- **slowCallRateThreshold:** percentage of slow calls that can trip the circuit.
- **waitDurationInOpenState:** duration to stay in OPEN before attempting recovery.
- **permittedNumberOfCallsInHalfOpenState:** number of probe calls permitted in HALF_OPEN.

Distinguish between failure rate and slow call rate. A service might still return HTTP 200 yet take far too long; if only errors are tracked, the calling system still risks exhausting resources. Conversely, if thresholds are overly sensitive to a few samples during low-traffic periods, the circuit may open unnecessarily. Choose windows and thresholds based on actual traffic, target response times, and functional criticality.

## Integrating Spring Cloud CircuitBreaker with Resilience4j

In a Spring Boot project, add the Spring Cloud CircuitBreaker Resilience4j starter and manage versions with a Spring Cloud BOM compatible with the project's Spring Boot version. Do not manually pick an arbitrary standalone starter version when the project already uses a BOM.

Example Maven dependency declaration:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

The configuration below illustrates a circuit breaker named catalog. The instance name must match the name passed to create("catalog") in code.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
  timelimiter:
    instances:
      catalog:
        timeoutDuration: 1s
        cancelRunningFuture: true
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 20
        maxWaitDuration: 0ms
~~~

This is a starter configuration illustrating the setting groups. Check how TimeLimiter integration and bulkhead types are supported by the project's version of Spring Cloud CircuitBreaker/Resilience4j. If the application uses a thread-pool bulkhead, configure the corresponding thread-pool-bulkhead group and also cap the queue size. A large queue can turn fast-rejection failures into prolonged latency.

### Wrapping Synchronous Calls

Spring Cloud CircuitBreaker provides CircuitBreakerFactory to create circuit breakers by name. The following example uses RestClient to call a catalog service:

~~~java
@Service
public class CatalogClient {

    private final RestClient restClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public CatalogClient(
            RestClient.Builder builder,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restClient = builder
                .baseUrl("http://catalog-service")
                .build();
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductSummary findProduct(String sku) {
        return circuitBreakerFactory.create("catalog").run(
            () -> restClient.get()
                    .uri("/products/{sku}", sku)
                    .retrieve()
                    .body(ProductSummary.class),
            error -> ProductSummary.unavailable(sku)
        );
    }
}
~~~

In the example, the HTTP call is executed only when the circuit breaker permits it. If the call fails or the circuit is OPEN, the fallback function returns a degraded result. ProductSummary.unavailable(sku) is an illustrative method on the data model; in a real application, the fallback might read the latest data from cache or return an explicit business-domain state.

Fallbacks must be fast and meaningful. Do not call the same failing service again inside the fallback, as that recreates pressure on the dependency. Nor should you turn every error into a seemingly successful result, such as returning an empty list when an empty list means no products exist. Clearly distinguish fallback data, non-existent data, and an undetermined state.

### Wrapping Reactive Calls

With WebClient and Reactor, use ReactiveCircuitBreakerFactory to keep calls inside a Mono chain:

~~~java
@Component
public class ReactiveCatalogClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ReactiveCatalogClient(
            WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = builder
                .baseUrl("http://catalog-service")
                .build();
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Mono<ProductSummary> findProduct(String sku) {
        Mono<ProductSummary> request = webClient.get()
                .uri("/products/{sku}", sku)
                .retrieve()
                .bodyToMono(ProductSummary.class);

        return circuitBreakerFactory.create("catalog").run(
                request,
                error -> Mono.just(ProductSummary.unavailable(sku))
        );
    }
}
~~~

In reactive flows, keep the Mono or Flux return type throughout and avoid calling block() to wait for results. Blocking threads undermines the benefits of the non-blocking model and ties up resources. Also configure connection and response timeouts on the reactive HTTP client so a network request does not hang too long.

## Combining Circuit Breaker, Timeout, and Bulkhead

These three mechanisms address different facets of the same problem:

| Mechanism | What Does It Limit? | Role |
|---|---|---|
| Circuit breaker | Number of calls continuing to hit a failing or slow dependency. | Stops calling when error signals exceed thresholds and retries in a controlled manner after a wait duration. |
| Timeout / TimeLimiter | Time a single call is allowed to wait. | Returns control to the application when a dependency responds too slowly. |
| Bulkhead | Concurrent calls or processing resources allocated to a dependency. | Prevents one dependency from exhausting threads, connections, or processing capacity of the calling service. |

**Timeout:** set wait times compatible with the response budget of upstream requests. For example, if the order API must respond within two seconds, the inventory call cannot consume that entire budget. Configure HTTP client timeouts such as connect timeout and response/read timeout as well. TimeLimiter does not guarantee the remote server stops processing immediately when the caller times out; task cancellation also depends on the HTTP client and how tasks are executed.

**Bulkhead:** limits concurrent calls to each dependency. A semaphore bulkhead is suitable when limiting concurrency directly on the calling thread. A thread-pool bulkhead offloads calls to a separate thread pool, providing stronger resource isolation, though thread count and queue capacity must be capped. When the limit is reached, new calls are rejected so the application can handle a fallback or return an appropriate error.

**Ordering and coordination:** keep timeout budgets smaller than the maximum wait time of upstream caller requests, and choose bulkhead limits based on the actual capacity of the dependent service. Retries should be bounded and reserved for transient recoverable errors. Retrying too many times or retrying while the circuit breaker is OPEN can amplify traffic and worsen an incident.

## Monitoring Service Protection Effectiveness

A circuit breaker is only useful when operations teams know which state it is in and why states changed. Spring Boot Actuator and Micrometer can be integrated with Resilience4j to observe metrics such as:

- Counts of successful calls, failed calls, and calls rejected because the circuit is OPEN.
- Failure rate, slow call rate, and dependency latency.
- CLOSED, OPEN, or HALF_OPEN state.
- Number of fallback invocations and calls rejected by bulkheads.
- Running task count and queue depth if using a thread-pool bulkhead.

Health indicators for an instance can be enabled using registerHealthIndicator. Expose only necessary Actuator endpoints and secure them according to the deployment environment's access policies.

When reading metrics, look at both technical signals and business impact. A continuously OPEN circuit can indicate the dependency has not recovered or that timeouts/thresholds are misconfigured. A sudden spike in fallbacks may keep the API alive, yet it also means users are receiving degraded data. If a circuit rapidly oscillates between OPEN and CLOSED in short intervals, re-evaluate the sliding window, minimum sample count, thresholds, and wait duration.

## Design and Testing Steps

When adding a circuit breaker to a service call, you can follow this sequence:

1. Identify the dependency to protect, which features can degrade, and what results are acceptable to return when the dependency is unavailable.
2. Measure normal traffic and latency; determine the calling request's time budget to select timeouts.
3. Choose the sliding window type, window size, minimum sample count, and failure/slow-call thresholds.
4. Choose the OPEN duration and HALF_OPEN probe call count aligned with the dependency's recovery capability.
5. Limit concurrency with a bulkhead and design fast, meaningful fallbacks that do not call back into the failing dependency.
6. Monitor state, failure rates, latency, and fallback frequency in a test environment before tuning thresholds for production.

For an order service calling an inventory service, test at least these scenarios: the inventory service returning continuous errors, responding slower than the timeout, stopping responses altogether, and recovering after a period of time. Observe the circuit breaker transitioning from CLOSED to OPEN, from OPEN to HALF_OPEN, and back to CLOSED when probe calls succeed. Also verify that fast-rejected requests still receive meaningful fallback responses, concurrent calls do not exceed bulkhead limits, and metrics accurately reflect status.

A good configuration is not the one with the most thresholds. It is one tailored to traffic, response budgets, and the degree of degradation acceptable to the business. Start with one critical dependency, measure real behavior, and then adjust each parameter based on data.
