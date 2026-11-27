# What Is a Circuit Breaker and How Does It Prevent Cascading Failures

In a microservices system, a user request often traverses multiple services. For example, when placing an order, the Order service may call Inventory to reserve stock, Payment to process payment, and Shipping to calculate delivery fees. If Inventory responds slowly or stops working, Order requests have to wait longer. As the number of waiting requests grows, Order's threads, connections, and queues can become exhausted. Other services calling Order also start slowing down. An initial failure in Inventory can therefore cascade into a system-wide outage.

A Circuit Breaker is a design pattern that helps limit this impact. It tracks the outcomes and processing times of calls to a dependent service. When it detects that the dependent service is experiencing problems, the Circuit Breaker temporarily stops sending new calls to that service, returning an error or switching to a fallback option for a short period. After a wait duration, it allows a number of probe calls to determine whether the service has recovered.

In Spring Cloud, Spring Cloud CircuitBreaker provides an abstraction layer so applications can use a Circuit Breaker with minimal coupling to a specific implementation library. Resilience4j is a popular choice for this implementation. This lesson focuses on how a Circuit Breaker works, how it prevents cascading failures, and the concepts you need to know before configuring it in Spring Cloud.

## 1. Why Can a Failure in One Service Cascade?

Suppose the Order service handles 100 requests per second and each request calls Inventory. Normally, Inventory responds in 50 ms. When Inventory encounters an outage, response time rises to 8 seconds. Each Order request must hold resources throughout the wait time. If traffic keeps arriving, the number of pending calls increases rapidly.

Some common consequences include:

- **Thread exhaustion:** request-handling threads are held while waiting on the dependent service, leaving new requests without threads to process them.
- **Connection exhaustion:** HTTP or database connection pools are occupied by incomplete calls.
- **Queue growth:** requests pile up, increasing latency even for features that do not need the failing service.
- **Load amplification from retries:** multiple layers retrying the same request can generate far more calls than the original traffic.
- **Cascading failures:** interdependent services start slowing down or rejecting requests, even though they are healthy themselves.

Timeouts help limit how long a single call is allowed to wait, but if many requests keep calling a failing service, the system can still face heavy load. Retries can be helpful for transient errors, but excessive or simultaneous retries can overwhelm a recovering service even further. A Circuit Breaker adds a mechanism to cut off calls for a period of time so the troubled service has a chance to recover while the rest of the system continues operating.

## 2. How Does a Circuit Breaker Work?

You can think of a Circuit Breaker like an electrical circuit breaker. When electrical current exceeds a dangerous threshold, the breaker trips to protect the rest of the system. In software, "current" is replaced by call outcomes and processing times.

A Circuit Breaker typically performs the following actions:

1. Allows calls to reach the dependent service when the state permits.
2. Records successful calls, failed calls, and overly slow calls.
3. Evaluates the results within a sliding window.
4. Transitions to the OPEN state when the failure rate or slow call rate exceeds the configured threshold, once a minimum number of samples has been reached.
5. Fails fast on new calls while in the OPEN state. The application can return a controlled error or use a fallback.
6. After a wait duration, transitions to HALF_OPEN and allows only a limited number of probe calls.
7. Closes the circuit if the probe calls show the service has recovered; reopens it if they continue to fail.

A Circuit Breaker does not fix the dependent service itself, nor does it guarantee every request succeeds. Its goal is to limit the number of calls continuing to hit a troubled service, reduce wait times, and protect the resources of calling services.

## 3. The Three States: CLOSED, OPEN, and HALF_OPEN

<figure>
<pre>
CLOSED
  |  Failure rate or slow call rate exceeds threshold
  v
OPEN
  |  Wait duration expires
  v
HALF_OPEN
  |  Probe succeeds             |  Probe fails
  v                           v
CLOSED                      OPEN
</pre>
</figure>

### CLOSED — allowing calls

This is the normal operating state. The Circuit Breaker allows calls to reach the dependent service and records outcomes in the sliding window. Once the sample count reaches the minimum threshold, it calculates the failure rate and/or slow call rate. If these rates exceed their thresholds, the Circuit Breaker transitions to OPEN.

For example, consider a window configured for 10 calls, requiring a minimum of 5 calls for evaluation and a failure rate threshold of 50%. Once there are at least 5 samples, if the failure rate reaches or exceeds 50%, the Circuit Breaker can open the circuit. In a 10-call window with 6 failed calls, the failure rate is 60%.

### OPEN — cutting off calls

When in the OPEN state, the Circuit Breaker fails fast on new calls without invoking the dependent service. This avoids continuing to waste wait time, threads, and connections on a service currently evaluated as unhealthy.

Rejected calls can trigger a fallback if the application has provided an appropriate fallback. If there is no fallback, the error is propagated up to the caller for handling. The Circuit Breaker remains in the OPEN state for a configured period, commonly referred to as the wait duration in open state.

### HALF_OPEN — probing for recovery

When the OPEN wait duration ends, the Circuit Breaker transitions to HALF_OPEN. It allows a limited number of calls through to test the dependent service. The number of probe calls is controlled by a configuration such as permittedNumberOfCallsInHalfOpenState in Resilience4j.

If the probe calls show that the service is operating stably, the Circuit Breaker transitions back to CLOSED and resumes recording normal results. If they continue to fail or are too slow according to the configured conditions, the Circuit Breaker returns to OPEN. Limiting the number of probe calls prevents flooding a service with a huge surge of traffic right as it begins to recover.

## 4. Sliding Windows and Failure Evaluation

A Circuit Breaker should not open just because a single call fails. One error can occur due to a brief network blip, input data, or a transient condition. A sliding window evaluates a recent group of results rather than looking only at the last outcome.

Resilience4j supports two common window types:

| Window Type | How It Works | When Appropriate |
| --- | --- | --- |
| COUNT_BASED | Keeps the results of a fixed number of most recent calls, such as 20 calls. | Traffic is relatively steady or you want sample-based evaluation. |
| TIME_BASED | Aggregates results over a time interval, such as the last 30 seconds. | Traffic varies and you want real-time window evaluation. |

Several key parameters include:

- **slidingWindowType:** selects COUNT_BASED or TIME_BASED.
- **slidingWindowSize:** number of calls in the window or number of seconds in the window, depending on the selected type.
- **minimumNumberOfCalls:** minimum number of calls required before calculating rates. This parameter avoids drawing conclusions from too small a sample.
- **failureRateThreshold:** percentage of failed calls that causes the Circuit Breaker to open.
- **slowCallDurationThreshold:** duration beyond which a call is considered slow.
- **slowCallRateThreshold:** percentage of slow calls that causes the Circuit Breaker to open.

Slow calls can also exhaust resources even when they eventually return successfully. Therefore, tracking both failures and latency helps the Circuit Breaker react before the dependent service completely stops responding.

Windows and thresholds must be chosen according to the characteristics of each service. A low-traffic service may need a longer time window or an appropriate minimum sample count. A service with naturally high normal latency also needs its own slow call threshold. You should not copy one set of thresholds to every dependency without basing it on operational data.

## 5. Spring Cloud CircuitBreaker and Resilience4j

Spring Cloud CircuitBreaker provides a unified API for applications to invoke a Circuit Breaker. The underlying implementation can be Resilience4j or another provider supported by Spring Cloud. With this abstraction layer, business code can focus on the call and how to handle its result, while provider configuration determines the thresholds and protection behavior.

For a Spring Boot application using Resilience4j, the typical dependency is the following starter (the version must be compatible with the project's Spring Boot and Spring Cloud release train):

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

The example below illustrates a synchronous call from Order to Inventory. The application retrieves a Circuit Breaker named inventory, calls the client when the circuit allows, and provides a fallback to return a state indicating inventory is temporarily unavailable.

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Inventory getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getInventory(sku),
            error -> Inventory.unavailable(sku)
        );
    }
}
~~~

InventoryClient and Inventory are types belonging to the illustrative application. The unavailable method should produce a business-domain result clearly indicating that inventory data is currently unavailable. The name inventory is the Circuit Breaker's configuration identifier; you should use a stable name tied to the dependency or protected operation.

Fallbacks must be designed carefully. For instance, on a product page, the application can return the latest inventory data from cache along with stale-data metadata. For an operation that requires exact inventory before confirming an order, the application can return a controlled error and ask the user to try again. You should not turn a failure into a fake "success" result, as that misleads the calling layer about the business state.

## 6. Basic Resilience4j Configuration

Each Circuit Breaker can be configured in application.yml. The following example creates a dedicated configuration for the inventory dependency:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

With this illustrative configuration, the Circuit Breaker evaluates up to the 10 most recent calls and only begins calculating rates after at least 5 calls. If the failure rate reaches the 50% threshold or the slow call rate reaches the 50% threshold, the circuit can transition to OPEN. A call lasting 2 seconds or more is counted as slow. After 10 seconds in OPEN, the Circuit Breaker transitions to HALF_OPEN to allow up to 3 probe calls.

This is only a starting point to illustrate how the parameters relate to one another. In a production environment, thresholds must be chosen based on traffic, normal latency, response time targets, and dependency criticality. If a system has low traffic, setting minimumNumberOfCalls too high can cause the Circuit Breaker to take a long time before evaluating service health.

You can fine-tune which exception types count as failures. For example, connection errors and timeouts usually should count toward the failure rate; a business error such as product not found probably should not trip the Circuit Breaker. Resilience4j supports the recordExceptions and ignoreExceptions properties to control exception recording. Classify exceptions based on business meaning and how the client represents errors, rather than treating all exceptions the same by default.

## 7. Combining Circuit Breaker with Timeout, Retry, and Bulkhead

A Circuit Breaker is one part of resilience and does not replace other protection mechanisms.

| Mechanism | Problem Solved | How to Coordinate |
| --- | --- | --- |
| Timeout | A call waits too long. | Set a time limit on calls to free resources; timeouts should be recognized as an appropriate failure outcome. |
| Retry | Transient errors might succeed on retry. | Only retry with a limit, backoff, and jitter when the operation is safe to retry. Avoid retrying repeatedly when the Circuit Breaker is already open. |
| Bulkhead | One dependency consumes all shared resources. | Limit concurrent calls or isolate thread pools so an issue in one dependency does not exhaust all processing capacity. |
| Fallback | The caller needs controlled behavior when a dependency is unavailable. | Return cached data, degraded results, or a clear business error depending on requirements. |

Timeouts are especially important because a Circuit Breaker can only evaluate a call after receiving a result or an error. If a call has no time limit and hangs indefinitely, resources remain held for a long time. For asynchronous calls, you can combine Resilience4j's TimeLimiter and verify task cancellation capability when time expires.

Bulkheads limit the concurrency of calls. For example, if Inventory is slow, a bulkhead can limit the number of requests currently calling Inventory so other execution flows still have resources available. Resilience4j offers semaphore-based or thread-pool-based bulkhead implementations; the choice depends on the application's execution model.

Retries need a clear budget. If every layer in a three-service chain retries three times, the number of calls reaching the final layer can multiply sharply. Limit retry attempts, configure backoff, add jitter, and avoid retrying errors that cannot recover via re-invocation. Circuit Breaker and Retry should be configured together so that when a dependency is failing, the system does not keep generating additional load.

## 8. Reactive Calls

For applications using Spring WebFlux and Reactor, Spring Cloud CircuitBreaker provides ReactiveCircuitBreakerFactory. The Circuit Breaker wraps a Publisher such as Mono so both the call and the fallback remain within the reactive stream.

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCatalogService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    public ReactiveCatalogService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            ReactiveInventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Mono<Inventory> getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            inventoryClient.getInventory(sku),
            error -> Mono.just(Inventory.unavailable(sku))
        );
    }
}
~~~

In this example, ReactiveInventoryClient's getInventory returns Mono<Inventory>. The fallback also returns a Mono to preserve the reactive return type. Avoid calling block() in WebFlux flows because blocking operations can tie up the event loop and negate the benefits of the non-blocking model. With reactive flows, also check whether timeouts, subscription cancellation, and bulkheads are compatible with the application's execution model.

## 9. Monitoring Circuit Breaker Behavior

Even a properly configured Circuit Breaker needs to be observed in production. Useful metrics include:

- Counts of successful calls, failed calls, and calls rejected by the Circuit Breaker.
- Failure rate and slow call rate per dependency.
- Number of state transitions between CLOSED, OPEN, and HALF_OPEN.
- Time the Circuit Breaker spends in the OPEN state.
- Number of times fallbacks are invoked and fallback success rate.
- Latency of calls to the dependency and actual latency experienced by users.

Resilience4j integrates with Micrometer to export metrics; Spring Boot Actuator can be used to expose metrics and health endpoints according to application configuration. When enabling health indicators, understand how Circuit Breaker states affect overall health status. An OPEN dependency does not necessarily mean the entire application must be marked DOWN, especially when the application can still serve degraded functionality via cache or fallback.

Tie Circuit Breaker names clearly to the dependency or operation, and add their metrics to dashboards and alerts. If a Circuit Breaker opens frequently, check logs, traces, dependency error rates, response times, and timeout configurations. If fallback usage spikes, operators need to know whether users are receiving stale data, degraded results, or rejection errors.

## 10. Design Principles

- **Place Circuit Breakers around remote calls:** apply them to dependencies that can become slow or unavailable, such as HTTP services, RPCs, or external systems.
- **Separate configurations by dependency:** each service has different traffic, latency, and criticality.
- **Choose meaningful exceptions:** routine business errors should not automatically trip the circuit if they do not reflect dependency health.
- **Design fallbacks around business needs:** fallback results must clearly reflect data reliability and limitations.
- **Limit time and concurrency:** combine timeouts and bulkheads to control resource consumption.
- **Control retries:** avoid amplifying load while a service is recovering.
- **Monitor states and metrics:** verify actual behavior before tuning thresholds.
- **Test failure scenarios:** simulate timeouts, connection failures, elevated error rates, service recovery, and fallbacks to understand how the system responds.

A Circuit Breaker is appropriate when a dependency can fail independently and continuing to call it risks exhausting the calling service's resources. It does not replace good system design, load control, or business error handling. When combining CLOSED/OPEN/HALF_OPEN states, sliding windows, timeouts, bulkheads, fallbacks, and operational observability, Spring Cloud CircuitBreaker with Resilience4j helps applications limit incident blast radius and recover in a controlled manner.
