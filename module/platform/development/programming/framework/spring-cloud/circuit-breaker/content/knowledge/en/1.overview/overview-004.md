# Core Concepts: Calls, Failures, Thresholds, States, and Fallbacks

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, we learn how to use Circuit Breakers in Spring Cloud to protect a service when a service it depends on responds slowly or becomes unavailable. The goal of this design pattern is to prevent a localized issue from turning into a cascading failure: instead of continuing to send requests to an overloaded system, the application temporarily stops calls, returns an appropriate fallback result, and only tries reconnecting after a period of time.

To understand how to integrate Resilience4j, configure sliding windows, fallbacks, timeouts, bulkheads, reactive calls, and monitor protection effectiveness, we first need to align on five concepts: calls, failures, thresholds, states, and fallbacks.

## 1. Why Can a Failed Call Cause a Cascading Failure?

Suppose an Order service calls an Inventory service to check product stock quantities. When the Inventory service is operating normally, calls usually complete within tens of milliseconds. When Inventory encounters an outage, each call may take several seconds before timing out. During the wait, the Order service's processing threads remain occupied. Concurrent request counts climb, queues grow longer, and memory and connections see heavier usage. Eventually, the Order service itself may slow down or stop serving even though nothing is wrong with it internally.

If the system keeps calling Inventory in the exact same way, it both adds load to an already troubled service and consumes the calling service's resources. A Circuit Breaker establishes a temporary cutoff mechanism:

1. When the system is healthy, calls are forwarded to the dependent service and outcomes are recorded.
2. When the failure rate or slow call rate exceeds configured thresholds, the Circuit Breaker opens the circuit.
3. While the circuit is open, new calls are rejected fast. The application can return fallback data or report that the service is temporarily unavailable.
4. After a wait duration, the Circuit Breaker allows a number of probe calls to assess recovery.

A Circuit Breaker does not fix faults in the dependent service. It controls how the calling service reacts to incidents, helping limit impact and buy time for the system to recover.

## 2. Calls and Recorded Outcomes

A **call** is a single execution by the application against a dependent system, such as making an HTTP call to retrieve inventory, an RPC call to calculate fees, or querying an external service. A Circuit Breaker is typically placed around operations that depend on resources or systems outside the application's direct control.

A call can end in one of the following ways:

| Outcome | Meaning | How the Circuit Breaker Treats It |
| --- | --- | --- |
| Success | Receives a valid result within an acceptable duration | Records a successful call |
| Failure | Encounters an exception, connection error, or an error configured as a dependency failure | Records a failed call |
| Slow | Completes, but execution duration exceeds the slow call threshold | Records a slow call; it may still count as a success |
| Rejected | The circuit is OPEN so the actual operation is not executed | Returns a fast-rejection error, typically CallNotPermittedException |

Distinguishing **failed** from **slow** is crucial. A call may return HTTP 200 yet take 8 seconds; at the protocol level it succeeded, yet in terms of user experience and serving capacity it can be harmful. Resilience4j allows tracking failure rate and slow call rate separately.

Not every exception necessarily indicates that the dependent service is broken. For example, a non-existent product SKU may be a normal business outcome. If every 404 error is treated as an infrastructure failure, the Circuit Breaker might open even though the Inventory service is healthy. Therefore, you must define which exception types are recorded as failures and which should be ignored.

A call rejected while the circuit is OPEN also differs from a call that was sent and failed. The application receives a response from the Circuit Breaker itself without adding load to the dependent service. Rejection counts still need monitoring because they show the protection mechanism is intervening.

## 3. Thresholds and Sliding Windows

A Circuit Breaker should not open just because a single call failed. It needs to observe a group of recent calls, calculate the failure rate or slow call rate, and compare it against configured thresholds.

A **sliding window** is the data region the Circuit Breaker uses to compute these rates. As new call outcomes arrive, older data gradually leaves the window. As a result, decisions reflect the recent health of the dependent service rather than retaining failure history from hours ago.

Resilience4j supports two window types:

| Window Type | How It Works | When Appropriate |
| --- | --- | --- |
| COUNT_BASED | Tracks a fixed number of most recent calls, such as the last 20 completed calls | Traffic is relatively steady or evaluation by call count is needed |
| TIME_BASED | Tracks outcomes within a time interval, such as the last 10 seconds | Traffic fluctuates and real-time evaluation is needed |

Several common parameters include:

- **slidingWindowType**: chooses COUNT_BASED or TIME_BASED.
- **slidingWindowSize**: number of calls in a COUNT_BASED window or window duration in seconds in TIME_BASED.
- **minimumNumberOfCalls**: minimum number of calls required before calculating rates. This parameter avoids making decisions from too small a sample.
- **failureRateThreshold**: failure rate threshold, expressed as a percentage.
- **slowCallDurationThreshold**: duration from which a call is considered slow.
- **slowCallRateThreshold**: slow call rate threshold, expressed as a percentage.

For example, a COUNT_BASED window has size 20 and minimumNumberOfCalls set to 10. The Circuit Breaker needs at least 10 call outcomes before calculating rates. Once enough samples exist, if the failure rate reaches or exceeds 50%, the circuit can transition to OPEN. If the slow call rate reaches or exceeds slowCallRateThreshold, the circuit can also open even if many calls still return successful responses.

The two rates have distinct meanings:

$$
\text{Failure rate} = \frac{\text{failed calls}}{\text{total recorded calls}} \times 100\%
$$

$$
\text{Slow call rate} = \frac{\text{calls exceeding duration threshold}}{\text{total recorded calls}} \times 100\%
$$

For example, suppose 10 calls are recorded: 4 failed calls, 3 slow-but-successful calls, and 3 fast successful calls. The failure rate is 40%; the slow call rate is 30%. If the failure threshold is 50% and the slow threshold is 60%, this sample alone does not open the circuit. If 6 out of 10 calls fail, the failure rate reaches 60% and exceeds the 50% threshold.

Incomplete calls cannot contribute to the window's rates yet. Therefore, call timeout settings also affect when the Circuit Breaker receives an outcome to evaluate.

### Resilience4j Configuration Example

With Spring Cloud CircuitBreaker using Resilience4j, an instance named inventory can be configured in application.yml:

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
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

In this configuration, a call lasting longer than 2 seconds is considered slow. Once there are at least 10 outcomes in the window, a failure rate of 50% or higher or a slow call rate of 60% or higher can open the circuit. The circuit stays OPEN for 10 seconds; then it transitions to HALF_OPEN and allows up to 5 probe calls as configured.

The values above only illustrate how to read the configuration, not thresholds suited to every system. Choose them based on normal latency, traffic, timeout duration, and the service objectives of each dependency.

## 4. The Three States: CLOSED, OPEN, and HALF_OPEN

A Circuit Breaker operates primarily through three states. The state determines whether new calls are permitted to reach the dependent service.

### CLOSED — closed circuit

This is the normal operating state. Calls are allowed to pass through to the dependent service. The Circuit Breaker records outcomes and execution durations to update the sliding window.

Once the sample count reaches minimumNumberOfCalls, the Circuit Breaker computes the failure rate and slow call rate. If either rate reaches its respective threshold, the circuit transitions to OPEN. If thresholds are not reached, the circuit stays CLOSED.

### OPEN — open circuit

When the circuit is OPEN, the Circuit Breaker fails fast on new calls without invoking the dependent service. This avoids continuing to send requests to a system showing signs of overload or outage.

The application typically receives CallNotPermittedException when a call is blocked. If an appropriate fallback exists, the application can return a fallback result. The duration spent in OPEN is controlled by waitDurationInOpenState.

When the wait duration expires, the Circuit Breaker transitions to HALF_OPEN. With Resilience4j, you can enable automaticTransitionFromOpenToHalfOpenEnabled so the transition happens automatically; otherwise, the state may transition when the next call arrives after the wait duration.

### HALF_OPEN — half-open circuit

HALF_OPEN is the recovery-testing phase. The Circuit Breaker permits only a limited number of calls to reach the dependent service. The number of probe calls is configured via permittedNumberOfCallsInHalfOpenState.

- If probe outcomes show the service has recovered and rates remain within thresholds, the Circuit Breaker transitions back to CLOSED.
- If the failure rate or slow call rate continues to exceed thresholds, the Circuit Breaker transitions back to OPEN and continues protecting the system.

Limiting the number of probe calls prevents creating a sudden traffic spike right as the service comes back online. Remaining requests during HALF_OPEN may still be rejected once the allocated probe attempts are exhausted.

State transition diagram:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure rate or slow call rate reaches threshold
    OPEN --> HALF_OPEN: waitDurationInOpenState expires
    HALF_OPEN --> CLOSED: Probe calls meet requirements
    HALF_OPEN --> OPEN: Probe calls still exceed thresholds
~~~

This cycle helps the Circuit Breaker balance two goals: stopping calls when a service is in trouble and restoring traffic in a controlled way when the service resumes operating.

## 5. Fallbacks

A **fallback** is how the application responds when the primary call cannot deliver a result. In Spring Cloud CircuitBreaker, a fallback can be passed alongside the run operation. When the primary operation throws an exception or the Circuit Breaker rejects the call because it is OPEN, the fallback function can produce an alternative result.

For example, a product page can display the latest stock information from cache when the Inventory service is temporarily unresponsive. Another API might return a status of "unable to verify stock at this time" so the UI can inform the user. The fallback result must accurately reflect the certainty level of the data.

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class InventoryClient {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RestTemplate restTemplate;

    public InventoryClient(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RestTemplate restTemplate) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.restTemplate = restTemplate;
    }

    public Inventory find(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> restTemplate.getForObject(
                        "http://inventory-service/items/{sku}",
                        Inventory.class,
                        sku),
                error -> Inventory.unavailable(sku)
        );
    }
}
~~~

The snippet illustrates how to use the Spring Cloud CircuitBreaker abstraction. CircuitBreakerFactory creates a circuit breaker named inventory; this name must match the instance configured in application.yml. The first function executes the HTTP call. The second function produces a fallback result when the primary call cannot provide one.

In the example, Inventory.unavailable(sku) should clearly represent an "inventory unknown" state. Do not automatically return a quantity of 0 if 0 means "confirmed out of stock"; those two states carry different business meanings. If a valid cache exists, the fallback can return cached data along with its update timestamp so users and downstream systems know the data is stale.

Fallbacks should follow several principles:

- Do not call the same failing service again from inside the fallback, as that can create loops or continue increasing load.
- Do not hide business errors or programming bugs behind a meaningless default value.
- Record how often fallbacks are used so you can detect when the system is degraded even while the API still returns responses.
- Keep fallbacks simple, fast, and minimally coupled. If a fallback also calls an external service, it can fail in the same way.
- Define which exception types are recorded. Input errors or business outcomes such as "product not found" usually need separate handling rather than inflating the infrastructure failure rate.

Fallback is not synonymous with retry. Retry re-executes the call; fallback provides an alternative response when the primary call fails or is rejected. Unbounded retries can amplify incidents, so if combining retries with a Circuit Breaker, cap attempt counts and pay attention to the wrapping order of the mechanisms.

## 6. Coordinating Circuit Breaker with Timeout, Bulkhead, and Reactive Calls

Circuit Breaker, timeout, and bulkhead solve different parts of the same service protection problem:

| Mechanism | Question It Answers | Effect |
| --- | --- | --- |
| Circuit Breaker | Should we keep calling a service showing signs of failure? | Temporarily stops calls when failure or slow rates exceed thresholds |
| Timeout / TimeLimiter | How long is a single call allowed to wait at most? | Caps wait duration and helps release processing when an operation takes too long |
| Bulkhead | How many calls can run concurrently? | Limits tasks or threads consuming resources for a dependency |

The slowCallDurationThreshold only helps the Circuit Breaker recognize slow calls after a measurable outcome arrives. A Circuit Breaker by itself does not guarantee stopping a hung call. Set timeouts on the HTTP client or use TimeLimiter as appropriate to cap wait times. Bulkheads further limit concurrent calls so a slow service cannot exhaust all of the calling application's resources.

For reactive applications, Spring Cloud CircuitBreaker provides ReactiveCircuitBreakerFactory. You can wrap a Mono or Flux and supply a fallback publisher:

~~~java
ReactiveCircuitBreaker circuitBreaker =
        reactiveCircuitBreakerFactory.create("inventory");

return circuitBreaker.run(
        webClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class),
        error -> Mono.just(Inventory.unavailable(sku))
);
~~~

This is a general example for a call returning a Mono. In reactive flows, keep operations inside the publisher chain and avoid calling block() indiscriminately, as blocking can negate the benefits of the non-blocking model. Configure timeouts and resource limits appropriate for the reactive client in use.

## 7. Monitoring Protection Effectiveness

Merely seeing an API still returning HTTP 200 is not enough to conclude the Circuit Breaker is working well. If many responses come from fallbacks, users may still receive answers while data from the dependent service is no longer available.

Monitor the following metric groups:

- **Circuit state**: counts of instances in CLOSED, OPEN, or HALF_OPEN; timestamps and frequency of state transitions.
- **Call outcomes**: counts of successful, failed, slow, and rejected calls.
- **Rates**: failure rate and slow call rate compared against configured thresholds.
- **Fallback**: number of fallback invocations, fallback response rate, and fallback failure rate.
- **Latency**: response time of dependency calls and end-to-end API response time.

Spring Cloud CircuitBreaker combined with Resilience4j can export metrics via Micrometer when the application enables appropriate metrics configuration. With Spring Boot Actuator and a monitoring system like Prometheus, operations teams can build dashboards and alert when a circuit stays OPEN too long, oscillates repeatedly between OPEN and HALF_OPEN, or when fallback rates spike abnormally.

When reading dashboards, distinguish dependency errors from errors caused by Circuit Breaker rejections. If rejected calls increase, it shows the mechanism is blocking traffic; inspect circuit state, preceding call failure rates, and dependency health together to find the root cause.

## 8. Choosing Configuration and Common Pitfalls

No single threshold set fits every service. Key considerations include:

1. **Measure normal latency before setting slow thresholds.** If a service normally responds in 300 ms, a 2-second threshold may reasonably catch significant degradation; if a service inherently takes several seconds, that threshold will trigger false positives.
2. **Size sliding windows to traffic.** Too small a window reacts easily to random fluctuations; too large a window can delay incident detection.
3. **Set an appropriate minimumNumberOfCalls.** Too low a value computes rates from too few samples; too high a value forces the system to wait too long before it can open the circuit.
4. **Classify exceptions semantically.** Business errors, validation errors, or missing data should not be treated as infrastructure failures by default.
5. **Choose controlled OPEN durations and HALF_OPEN probe counts.** Too short a wait may make the application retry before the service recovers; too many probe calls may create a sudden load spike.
6. **Design meaningful fallbacks.** Stale data, undetermined data, and confirmed zero stock must be distinct states.
7. **Monitor fallback outcomes too.** A fallback that always succeeds can make the API's apparent error rate look very low even while the dependent service is down.

A Circuit Breaker is typically configured per dependency or group of operations with similar failure characteristics and latency targets. Sharing one circuit across multiple unrelated services can cause an outage in one service to mistakenly block calls to another.

## 9. Integrated Scenario

Consider an Order service calling an Inventory service with the inventory configuration above:

1. Initially the circuit is CLOSED. Inventory check calls execute and outcomes are fed into the sliding window.
2. The Inventory service starts responding slowly and throwing errors. Once the window has enough samples and the failure rate or slow call rate hits the threshold, the circuit transitions to OPEN.
3. Subsequent inventory check requests are rejected fast. Order uses cached data if still suitable, or returns a status indicating inventory cannot be verified yet.
4. After 10 seconds, the circuit transitions to HALF_OPEN and permits only a limited number of probe calls.
5. If the Inventory service recovers, probe calls complete within limits and the circuit returns to CLOSED. If errors persist, the circuit goes back to OPEN.

When analyzing this scenario, ask yourself:

- Which calls are counted in the sliding window, and why does a rejected call differ from a failed call?
- What causes the circuit to transition from CLOSED to OPEN?
- How does minimumNumberOfCalls protect the decision to open the circuit?
- Why does HALF_OPEN permit only a limited number of probe calls?
- What data should the fallback return so "unknown inventory" is not confused with "out of stock"?
- When do you need to add timeouts or bulkheads alongside a Circuit Breaker?

Mastering these concepts helps you read Resilience4j configurations, predict application behavior in every state, and design meaningful fallback responses. This forms the foundation for safely implementing Circuit Breakers in both synchronous and reactive calls in a Spring Cloud system.
