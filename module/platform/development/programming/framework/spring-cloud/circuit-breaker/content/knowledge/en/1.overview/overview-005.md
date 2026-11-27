# Distinguishing Circuit Breaker, Timeout, Retry, Bulkhead, and Rate Limiter

In a microservices system, a call to a dependent service can be slow, failing, or overloaded. If many requests keep waiting and retrying, the calling service's resources also gradually deplete; the initial incident can escalate into a cascading failure. Spring Cloud CircuitBreaker combined with Resilience4j provides protection mechanisms to contain that impact.

Circuit Breaker, timeout, retry, Bulkhead, and Rate Limiter are often used together, yet each mechanism solves a different problem:

- **Circuit Breaker** observes recent call outcomes and temporarily stops calling a dependency when the failure rate or slow call rate exceeds thresholds.
- **Timeout** limits how long a single call is allowed to wait.
- **Retry** re-executes a call when encountering an error that is likely transient.
- **Bulkhead** caps concurrent calls so one dependency cannot consume all resources.
- **Rate Limiter** caps the number of calls accepted within a given time interval.

Understanding the boundaries between them helps choose the right mechanism, configure it properly, and avoid inadvertently amplifying an incident.

## 1. Circuit Breaker: Stopping Calls When a Dependency Shows Instability

A Circuit Breaker tracks the outcomes of calls to a dependency over a statistical window. When the failure rate or slow call rate exceeds configured thresholds, it transitions to the OPEN state and rejects new calls for a period of time. The application can return a fallback or a controlled error message instead of continuing to wait on a troubled service.

A Circuit Breaker typically has three states:

| State | Behavior | State Transition |
|---|---|---|
| CLOSED | Allows calls to reach the dependency and records outcomes | Transitions to OPEN when the failure rate or slow call rate reaches the threshold |
| OPEN | Fails fast on new calls; sends no requests to the dependency | Transitions to HALF_OPEN after the configured wait duration |
| HALF_OPEN | Allows only a small number of probe calls | Returns to CLOSED if the dependency recovers; transitions back to OPEN if probe calls still fail or are too slow |

In the OPEN state, a rejected call is typically represented by an error of type CallNotPermittedException in Resilience4j. This is an outcome of the protection mechanism, not necessarily a request sent to the target service.

### How Does the Sliding Window Work?

A Circuit Breaker needs a recent set of outcomes to decide when to open the circuit. Resilience4j supports two window types:

- **COUNT_BASED**: aggregates statistics over the most recent N calls. For example, a 20-call window retains the outcomes of up to the 20 latest calls.
- **TIME_BASED**: aggregates statistics over a recent time interval. For example, a 10-second window counts outcomes recorded in the past 10 seconds.

Distinguish window size from the minimum number of calls. If a 20-call window is configured yet only 3 calls have been made, the Circuit Breaker may not have enough data to calculate rates. The minimumNumberOfCalls property specifies the minimum sample count required before evaluating thresholds.

A Circuit Breaker can open the circuit based on two signal groups:

- **Failure rate**: the percentage of failed calls in the window reaches failureRateThreshold.
- **Slow call rate**: the percentage of calls exceeding slowCallDurationThreshold reaches slowCallRateThreshold.

For example, a slowCallDurationThreshold of 2 seconds and a slowCallRateThreshold of 50% mean that if at least half of the calls in the window take 2 seconds or more, the Circuit Breaker can open the circuit, even if those calls eventually succeed. This is useful when a dependency has not completely broken down yet responds slowly enough to put pressure on processing threads.

The duration in OPEN is controlled by waitDurationInOpenState. When this duration expires, the Circuit Breaker allows a number of probe calls in HALF_OPEN, bounded by permittedNumberOfCallsInHalfOpenState. Configuring a small number of probe calls tests recovery without placing heavy additional load on the dependency.

## 2. Timeout: Limiting Wait Time for a Single Call

A timeout sets a limit on how long to wait for an operation to finish. If the deadline expires, the call is considered timed out and the calling layer can handle the timeout error or switch to a fallback.

For example, an order service calls an inventory service with a 2-second timeout. If the inventory service has not responded after 2 seconds, the order service stops waiting for the result according to its configured policy and proceeds with error handling. Timeouts keep requests from holding threads, connections, or related resources for too long.

Timeout differs from Circuit Breaker in decision scope:

- Timeout handles a single specific wait. It does not need to wait for multiple requests to fail before taking effect.
- Circuit Breaker observes multiple recent outcomes. When a dependency shows signs of instability, it prevents subsequent requests from continuing to hit the dependency.

The two mechanisms complement each other. Timeout establishes a time bound for each individual invocation; Circuit Breaker can use timeout errors and slow call metrics as signals to open the circuit.

Configure timeouts at the right layer. For HTTP clients, set connect timeouts and response/read timeouts appropriate to the library in use. For Reactor flows, the timeout operator can limit how long a Mono or Flux may wait to emit signals. For Future or CompletionStage, Resilience4j TimeLimiter can manage wait durations.

A caller-side timeout does not always guarantee server-side work has stopped. Request cancellation, Future interruption, or query termination depends on the client, protocol, and server-side implementation. Therefore, timeouts should be coordinated with timeouts across network layers and the target service.

## 3. Retry: Retrying When Errors May Only Be Transient

Retry re-executes an operation after a previous attempt fails. This mechanism suits short-lived errors such as transient connection drops, temporary gateway errors, or brief 503 responses.

Retry does not restore a dependency and does not prevent cascading failures. If a dependency is overloaded, multiple callers retrying simultaneously can generate extra requests, worsening the overload. Hence, retries must be bounded:

- Limit total attempts. In Resilience4j, maxAttempts includes the initial call.
- Use wait intervals between attempts; in systems with multiple callers, consider exponential backoff and jitter so all callers do not retry at the exact same moment.
- Only retry errors that are likely transient. Authentication errors, invalid input, or business rule violations usually cannot be fixed by calling again.
- Only retry safe operations or those with idempotency mechanisms. Resending an order creation or payment charge command can cause duplicate side effects if the first attempt was processed but the response was lost.
- Set an overall time budget for the entire retry chain. Total retry duration must not exceed the deadline the upstream request can tolerate.

Retry and Circuit Breaker can be composed in different orders. Ordering affects how statistics are recorded:

- Circuit Breaker wrapping Retry: the Circuit Breaker observes the final outcome of the entire logical operation. One chain may make multiple attempts yet record only a single final outcome.
- Retry wrapping Circuit Breaker: each attempt passes through the Circuit Breaker, so individual failures can be recorded separately. Once the circuit is OPEN, the next attempt can be rejected immediately.

No single order fits every system. Choose based on how you want to measure failures, limit generated requests, and respect business deadlines. Whichever order you choose, keep retries tightly bounded so load does not increase while a dependency is degraded.

## 4. Bulkhead: Isolating Resources and Limiting Concurrent Calls

A Bulkhead limits how many operations can run concurrently against a dependency or resource group. The idea resembles watertight compartments on a ship: a breach in one compartment does not flood the entire vessel.

Suppose an aggregator service calls three dependencies: customer profile, inventory, and product recommendations. If all three share an unbounded thread pool, hung inventory calls can exhaust all threads and starve the other two dependencies. A Bulkhead establishes separate limits so one dependency cannot consume all processing capacity.

Resilience4j offers common Bulkhead types:

- **SemaphoreBulkhead** limits concurrent calls using a semaphore. Calls can be rejected immediately or wait briefly to acquire execution permission.
- **FixedThreadPoolBulkhead** uses a bounded thread pool and queue. It isolates execution from the calling thread, though pool size, queue capacity, and context-switching overhead must be considered.

Bulkhead controls **how many operations run simultaneously**, while Rate Limiter controls **how many operations occur over a time interval**. A system may receive 100 requests per second yet permit only 10 concurrent calls to a dependency. These two limits address two different dimensions of load.

A Bulkhead does not detect whether a dependency is failing. It only caps how many resources calls may consume. When slots run out, the application must decide whether to fail fast, return a fallback, or wait for a very short duration. An overly long wait queue may simply shift the bottleneck elsewhere.

## 5. Rate Limiter: Limiting the Rate of Accepted Calls

A Rate Limiter caps how many times an operation is permitted to execute within a period. For instance, a service might grant at most 50 permits per second to call a partner service. When permits run out, new requests can be rejected or wait until the next permit becomes available, depending on configuration.

In Resilience4j, RateLimiter is typically configured with properties such as:

- limitForPeriod: number of permits granted in each period.
- limitRefreshPeriod: duration of one permit refresh cycle.
- timeoutDuration: maximum time a caller waits to acquire a permit.

Rate Limiter is useful when protecting external API quotas, enforcing rate limits per product policy, or throttling load sent to a dependency. It does not evaluate whether a dependency is healthy on its own. A service can be operating fine while a caller is still throttled because its quota is exhausted.

Rate Limiter also does not limit concurrent in-flight calls. If each request takes 30 seconds, even a rate of 10 requests per second can build up hundreds of concurrent requests. When both rate and active concurrency must be bounded, combine Rate Limiter with Bulkhead.

## 6. Quick Comparison of the Five Mechanisms

| Mechanism | What Does It Control? | Primary Effect | When to Use |
|---|---|---|---|
| Circuit Breaker | Failure rate and slow call rate over a statistical window | Stops sending requests when a dependency shows instability | Dependency frequently fails or responds slowly; cascading failures must be prevented |
| Timeout | Wait duration of a single call | Frees processing threads from indefinite or overly long waits | Any network call or operation with uncertain response times |
| Retry | Number of retry attempts after failure | Rides out transient errors | Errors likely to self-resolve and operations safe to re-execute |
| Bulkhead | Concurrent calls or execution resources | Isolates load and caps resource consumption | Slow dependencies that could exhaust threads, connections, or workers |
| Rate Limiter | Number of calls within a period | Regulates traffic rate and protects quotas | APIs with rate quotas or when outbound request rate must be capped |

You can remember them with five questions:

1. Is the dependency failing or slow on a broad scale? Use Circuit Breaker.
2. How long is a single call allowed to wait? Use Timeout.
3. Could this error resolve itself if retried? Use Retry.
4. At most how many calls may run concurrently? Use Bulkhead.
5. At most how many calls may be sent per second or per minute? Use Rate Limiter.

## 7. Integrating with Spring Cloud CircuitBreaker and Resilience4j

In a Spring Boot application, you can use Spring Cloud CircuitBreaker with the Resilience4j implementation. For reactive calls based on Reactor, the typical starter is spring-cloud-starter-circuitbreaker-reactor-resilience4j. Manage the Spring Cloud version with a BOM compatible with your project's Spring Boot version.

Example configuration of a Circuit Breaker for an inventory dependency:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
  retry:
    instances:
      inventory:
        maxAttempts: 2
        waitDuration: 100ms
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0
  ratelimiter:
    instances:
      inventory:
        limitForPeriod: 50
        limitRefreshPeriod: 1s
        timeoutDuration: 0s
~~~

With this illustrative configuration, the Circuit Breaker tracks up to the 20 most recent calls and begins evaluating only after at least 10 calls. The circuit opens when the failure rate reaches 50% or the slow call rate reaches 50%, according to the configured thresholds. After 10 seconds in OPEN, up to 3 probe calls are allowed to run in HALF_OPEN. Retry permits at most 2 total attempts; Bulkhead limits concurrent calls to 20; Rate Limiter grants 50 permits per second.

The values above are only examples to explain configuration structure. Tune them according to real traffic, SLAs, dependency latency, and request deadlines. If timeouts are not configured appropriately, a single call can hold a Bulkhead slot for too long. If retries are excessive, they can increase request counts and processing time beyond the caller's budget.

The following example illustrates using ReactiveCircuitBreakerFactory to protect a WebClient call. The timeout operator caps the Mono wait time; the Circuit Breaker observes call outcomes and switches to a fallback on error or when the call is rejected because the circuit is OPEN.

~~~java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class InventoryClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryBreaker;

    public InventoryClient(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = webClient;
        this.inventoryBreaker = circuitBreakerFactory.create("inventory");
    }

    public Mono<Inventory> findInventory(String productId) {
        Mono<Inventory> request = webClient.get()
                .uri("/inventory/{productId}", productId)
                .retrieve()
                .bodyToMono(Inventory.class)
                .timeout(Duration.ofSeconds(2));

        return inventoryBreaker.run(
                request,
                error -> fallback(productId, error)
        );
    }

    private Mono<Inventory> fallback(String productId, Throwable cause) {
        // Can read from cache or return a business-appropriate degraded result.
        return Mono.just(Inventory.unavailable(productId));
    }
}
~~~

In the example, the configuration name inventory must match the ID passed to the factory. The fallback method must return a data type compatible with the primary stream. In a real application, log the fallback cause and distinguish technical failures from business errors. For example, a 404 response may mean a product does not exist; do not automatically turn every 404 into a failed dependency state if it is a normal business outcome.

Fallbacks must also be designed carefully. A fallback reading from another remote service can introduce a new point of failure. Prefer cached data, safe defaults, or a degraded response meaningful to users. Do not return fabricated data as if it were fresh when business rules forbid it.

## 8. Combining Mechanisms in a Single Call Flow

A call flow to a dependency can be protected in the following layers:

1. **Rate Limiter** checks whether the caller still has a permit to send a request in the current period.
2. **Bulkhead** checks whether a concurrent execution slot is available for the call.
3. **Timeout** caps the wait duration for the call to the dependency.
4. **Retry** retries only on permitted error groups while time budget remains.
5. **Circuit Breaker** decides whether to let the call proceed based on state and recent metrics.
6. **Fallback** produces an alternative response when a result cannot be obtained from the dependency.

This is a separation of responsibilities for design purposes, not a mandatory ordering for every library or configuration. When using Resilience4j decorators, nesting order determines which layer sees individual attempts and which layer sees only the final outcome. Verify the applied order in your actual configuration.

In particular, distinguish per-attempt timeout from the overall request deadline. For example, a 2-second per-call timeout with one extra retry can make the operation take over 2 seconds, not counting wait time between attempts. If the upstream request only allows 3 seconds, the entire execution chain must be bounded within that deadline.

## 9. Monitoring Protection Effectiveness

Resilience4j can integrate with Micrometer and Spring Boot Actuator to export metrics. Depending on application dependencies and configuration, metrics can be fed into monitoring systems like Prometheus and visualized in Grafana.

Monitor at least:

- Circuit Breaker state and counts of transitions between CLOSED, OPEN, and HALF_OPEN.
- Counts of successful, failed, slow, and rejected calls due to an OPEN Circuit Breaker.
- Retry counts, exhausted retry chains, and post-retry processing duration.
- Timeout counts and dependency latency.
- Calls rejected by Bulkhead, slot utilization, and wait times.
- Rate Limiter permits granted and throttled requests.
- Fallback rate and the quality of degraded responses users receive.

Do not look only at the overall error rate. If a Circuit Breaker is continuously OPEN, inspect dependency health, timeouts, and configured thresholds. If Bulkhead frequently rejects calls, review latency, concurrency levels, and resource limits. If retries spike, check underlying root-cause errors and traffic amplification risks. If fallbacks rise while dashboards still report successful requests, display the fallback response rate separately so incidents are not masked.

## 10. Common Design Mistakes

- **Using only Retry to handle an overloaded dependency**: extra requests sent can overload the dependency further. Combine timeouts, Circuit Breaker, and bounded retries.
- **Not setting a Timeout**: threads, connections, or Bulkhead slots can be held for too long.
- **Sharing one Circuit Breaker across multiple unrelated dependencies**: an outage in one service can disrupt calls to another. Choose IDs and configurations per dependency or operation group with matching characteristics.
- **Tripping the Circuit Breaker on normal business errors**: classify exceptions so cases like missing data or invalid requests do not skew technical failure rates.
- **Setting Bulkhead too large or queues too long**: limits lose effectiveness or requests keep piling up and expiring upstream.
- **Using only Rate Limiter to bound concurrency**: rate over time and concurrent in-flight operations are two distinct quantities.
- **Fallbacks masking stale or inaccurate data**: degraded responses must be clearly identified and observable via metrics and logs.
- **Configuring thresholds without data**: too small a sliding window fluctuates easily; too high a threshold opens the circuit too late, while too low a threshold opens on just a few random errors.

## 11. Selection and Tuning Workflow

When protecting a call from service A to service B, you can follow this sequence:

1. Determine A's request deadline and B's target response time.
2. Set a call timeout, ensuring time remains for A to handle errors or fallbacks.
3. Identify retryable errors, verify idempotency, and cap attempt counts.
4. Set Bulkhead limits based on B's load capacity and resources allocated to B.
5. Set Rate Limiter if there is a quota or rate limit to respect.
6. Enable Circuit Breaker with an appropriate sliding window, minimum sample count, failure/slow-call thresholds, and OPEN duration.
7. Build a business-meaningful fallback and measure fallback usage separately.
8. Observe metrics under normal load and during dependency degradation; tune configuration based on data.

These mechanisms form complementary layers of defense. Timeout caps wait duration; Retry handles certain transient errors; Bulkhead limits concurrent resources; Rate Limiter regulates throughput; Circuit Breaker stops calls from piling onto an unstable dependency. Properly combined, they help Spring Cloud protect calling services, reduce cascading failure risks, and maintain controlled responses when dependent systems fail.
