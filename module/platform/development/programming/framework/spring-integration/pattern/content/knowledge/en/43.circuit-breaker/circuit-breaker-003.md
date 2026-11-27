# Circuit open conditions

## 1. What actually causes a circuit breaker to open?

In **Spring Integration**, an Enterprise Integration Patterns (EIP) flow typically receives messages via a Gateway, checks them with a Filter, normalizes them with a Transformer, branches with a Router, and calls a dependency in a Service Activator. An external API experiencing repeated failures can slow down the entire branch, even when steps are connected via message channels to reduce coupling.

**The circuit breaker transitions from CLOSED to OPEN** when the outcomes of permitted dependency calls satisfy an **open policy**. Thereafter, new requests are rejected early at the breaker to relieve load on the unstable dependency.

The open condition does not necessarily mean "open on a single failed request". There are three common strategies:

1. **Consecutive failures**: for example, three consecutive handler executions throw an exception.
2. **Failure rate**: for example, at least 10 requests have been measured and 50% in the recent window failed.
3. **Slow-call rate**: for example, too many calls exceed a latency limit, even if some eventually succeed.

Spring Integration provides **RequestHandlerCircuitBreakerAdvice** with a consecutive-failure counting model. When you need a statistical window, failure rate, or slow-call rate, you can use **Resilience4j** at the dependency call site. The two mechanisms calculate differently, so you must identify which library you are using before choosing thresholds.

~~~mermaid
flowchart TD
    A[Message arrives at handler] --> B{Is breaker CLOSED?}
    B -->|Yes| C[Call dependency]
    B -->|No| X[Reject or probe according to state]
    C --> D[Observe response, exception, duration]
    D --> E[Classify success / failure / slow]
    E --> F[Update counter or window]
    F --> G{Open condition met?}
    G -->|Not yet| H[Keep CLOSED]
    G -->|Yes| I[Transition to OPEN]
~~~

**Key point:** the request that trips the threshold has already been sent to the dependency and failed. Requests **arriving afterward** are what get blocked in OPEN.

## 2. Defining which outcomes count as failures

Open conditions are only meaningful when the input signals are accurate. Not every exception or HTTP status proves that a dependency is unhealthy.

| Outcome | Should it count as a failure? | Reason |
| --- | --- | --- |
| Connection refused or connection error | Usually yes | Cannot complete the call |
| Timeout during inventory lookup | Usually yes | Dependency did not respond within the limit |
| HTTP 500/502/503 | Usually yes | External service failed to process the request |
| HTTP 400 due to missing payload fields | Usually no | Input error; should be filtered before calling |
| HTTP 404 meaning SKU does not exist | Usually no | May be a normal business result |
| HTTP 429 | Depends on policy | May require separate backoff/rate limiting |
| NullPointerException in Transformer | No | Internal bug, does not reflect dependency health |
| Call succeeds but is very slow | Depends on breaker | Can be recorded as a slow call, not necessarily a failure |

If a handler catches an exception and turns the failure into a fake success object, an outer breaker will not record the failure:

~~~java
// Anti-pattern: the dependency fails, yet the handler returns normally.
StockResult lookup(StockQuery query) {
    try {
        return stockClient.lookup(query);
    } catch (Exception ex) {
        return new StockResult(query.sku(), false);
    }
}
~~~

In this example, the value **false** is easily misinterpreted as "checked and out of stock", when in reality it means "unable to check inventory". Represent a **TEMPORARILY_UNAVAILABLE** state at the fallback layer or return an explicit error to the caller, after the breaker has observed the failure.

An API client also does not necessarily throw an exception upon receiving HTTP 503. If the handler returns a response containing status 503 as a normal value, an exception-counting breaker will treat the execution as a success, unless there is a step converting it into an error or a policy evaluating return values.

## 3. Opening on consecutive failures

With a **threshold of 3 consecutive failures**, a single success breaks the failure streak. For example:

| Call | Handler outcome | Consecutive failures | State after outcome |
| --- | --- | ---: | --- |
| 1 | Timeout | 1 | CLOSED |
| 2 | Timeout | 2 | CLOSED |
| 3 | Success | 0 | CLOSED |
| 4 | Timeout | 1 | CLOSED |
| 5 | Timeout | 2 | CLOSED |
| 6 | Timeout | 3 | **OPEN** |
| 7 | New request | Handler not executed | **OPEN**, rejected early |

An important difference: a sequence of "failure, success, failure, success" can yield a high failure rate, yet **never reach the consecutive threshold**. Therefore, consecutive failure counting fits scenarios where the dependency is completely down across several requests in a row, whereas failure rate fits intermittent failures better.

### 3.1. Configuring RequestHandlerCircuitBreakerAdvice

The Spring Integration Java DSL example below shows how to protect a Service Activator. Imports are omitted to focus on the message flow:

~~~java
public record StockQuery(String sku, int quantity) {}
public record StockResult(String sku, boolean available) {}

public interface StockClient {
    StockResult lookup(StockQuery query);
}

@MessagingGateway(defaultRequestChannel = "stock.requests")
public interface StockGateway {
    StockResult lookup(StockQuery query);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockFlowConfiguration {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockBreaker() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();
        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000); // milliseconds
        return advice;
    }

    @Bean
    public IntegrationFlow stockFlow(
            StockClient stockClient,
            RequestHandlerCircuitBreakerAdvice stockBreaker
    ) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> stockClient.lookup(query),
                        endpoint -> endpoint.advice(stockBreaker)
                )
                .get();
    }
}
~~~

Execution flow:

1. The Gateway sends a **StockQuery** to the **stock.requests** channel.
2. The handler calls **StockClient.lookup** and the advice observes the outcome.
3. When the consecutive failure threshold is reached, the breaker opens. Subsequent messages are not forwarded to the client during OPEN.
4. After the configured wait duration, the breaker has an opportunity to probe recovery with the next arriving request.

The value **15_000** is the wait duration before a probe opportunity, **not a request timeout**. Connection timeout and read/response timeout must still be set on the HTTP client.

Note that **RequestHandlerCircuitBreakerAdvice** counts failures at the handler boundary. If you place retry inside the advice, a business request with multiple attempts may only expose the final outcome to the advice. Do not confuse a threshold of three handler failures with three low-level network exceptions if those exceptions were handled by retries.

## 4. Opening on failure rate

When a dependency responds erratically, another measurement approach is computing the failure rate over a statistical window:

\[
\text{Failure rate} =
\frac{\text{Number of calls recorded as failed}}
{\text{Total number of measured calls in the window}}
\times 100\%.
\]

**Resilience4j** supports windows that are:

- **COUNT_BASED:** a fixed number of most recent calls, such as 10 or 100 requests.
- **TIME_BASED:** calls within a recent time interval, such as 30 seconds.

You typically also configure **minimumNumberOfCalls**. This is the minimum number of samples required before deciding to open the circuit based on failure rate; if samples are insufficient, even a single failure yielding a 100% rate is not enough to conclude the dependency is broken.

Suppose you configure a window of 10 calls, minimum 5 calls, and a **50%** failure rate threshold:

| Recorded calls | Failed calls | Rate | Can it OPEN? |
| ---: | ---: | ---: | --- |
| 4 | 4 | 100% | Not yet, minimum calls not reached |
| 5 | 2 | 40% | Threshold not reached |
| 6 | 3 | 50% | **Yes**, if breaker is CLOSED |
| 10 | 4 | 40% | Threshold not reached |
| 10 | 7 | 70% | **Yes**, if breaker is CLOSED |

These are **independent scenarios**, not consecutive rows within a single run: if the breaker already opened in one scenario, blocked requests do not continue entering the window like normal dependency calls.

Java example:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(
                CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50.0f)
        .waitDurationInOpenState(Duration.ofSeconds(15))
        .permittedNumberOfCallsInHalfOpenState(2)
        .build();

CircuitBreaker stockBreaker =
        CircuitBreaker.of("stock-service", config);

// Wrap only the dependency call inside the handler.
StockResult result = stockBreaker.executeSupplier(
        () -> stockClient.lookup(query)
);
~~~

Once enough samples are collected and the failure rate reaches 50% or more, Resilience4j can transition to OPEN. Requests rejected by the breaker can raise **CallNotPermittedException**; the Gateway or error flow must have a policy to handle this error type.

In low-traffic systems, a count-based window can retain stale outcomes for quite a long time before reaching minimum samples or rolling over. In high-traffic systems, a time-based window can contain a large volume of requests. Choose window parameters based on traffic characteristics and SLOs rather than picking one number for every dependency.

## 5. Opening on slow calls

A dependency may not throw exceptions yet take several seconds to respond. The Gateway still slows down, threads remain occupied, and queues grow. In such cases, **slow-call rate** can be an early indicator of an incident.

Resilience4j example:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .slowCallDurationThreshold(Duration.ofMillis(800))
        .slowCallRateThreshold(60.0f)
        .failureRateThreshold(50.0f)
        .build();
~~~

After 10 recorded calls have been collected, if 6/10 calls are slower than the **800 ms** threshold, the slow-call rate reaches **60%** and the breaker can OPEN, even if most of those calls did not throw exceptions. A call that is both slow and failed can appear in both slow and failed statistics; **do not add the two percentages together** to compute the open condition.

Distinguish three concepts:

| Mechanism | Responsibility |
| --- | --- |
| Client timeout | Limits how long a network call is allowed to wait |
| Slow-call threshold | Marks slow calls for statistical tracking |
| Circuit breaker OPEN | Blocks **new calls** when statistical metrics exceed thresholds |

A slow-call threshold **does not cancel an in-flight slow call**. Therefore, the system still needs client timeouts/deadlines and concurrency limits, especially when a dependency hangs without returning a response.

With the native consecutive-failure advice, a call that is slow yet completes successfully is usually not an exception that increments the counter; opening on slowness requires an appropriate measurement policy.

## 6. Recording the right exceptions and responses

A good threshold is useless if errors are misclassified. Separate into two zones:

~~~mermaid
flowchart LR
    A[Gateway] --> B[Validate / Filter]
    B -->|Valid| C[Transformer]
    C --> D[Circuit breaker]
    D --> E[External API]
    B -->|Invalid| F[Return validation error]
~~~

**Before the breaker:** Filter/Validator rejects empty SKUs or negative quantities so input errors are not counted as inventory API failures. The Router remains responsible for selecting business branches.

**Inside the breaker zone:** wrap only the execution capable of failing due to the dependency. Avoid letting errors in a Transformer or Aggregator pollute Stock API statistics.

Resilience4j provides exception classification configuration, for example:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .recordExceptions(
                java.io.IOException.class,
                java.util.concurrent.TimeoutException.class
        )
        .ignoreExceptions(BusinessValidationException.class)
        .build();
~~~

**BusinessValidationException** here is an application-defined business class. When using **recordExceptions**, check the actual exception thrown by your HTTP client, including wrapper exceptions, because a connection failure might not carry the exact primitive exception type you expect.

Operational notes:

- **HTTP 503** will not count as a failure if the handler swallows the status and returns normal data, unless you have explicitly configured return-value evaluation.
- **HTTP 404** may be a valid business outcome, depending on API semantics.
- **HTTP 429** may require backoff and rate limiting; deciding whether to record it as a breaker failure depends on the dependency's responsibilities and contract.
- An **ignored** exception does not necessarily have the same effect on sample count and counters as a failed call; follow implementation semantics rather than guessing from the exception name.

## 7. Retry directly affects the open condition

In EIP, retry can be implemented as an advice around a handler. The ordering of retry and breaker determines whether the breaker measures **logical requests** or **physical attempts**.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Circuit breaker]
    B --> C[Bounded retry]
    C --> D[Dependency]
~~~

**Breaker wrapping retry:** a request retried three times where all three fail may produce only **one final failed outcome** observed by the breaker.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Bounded retry]
    B --> C[Circuit breaker]
    C --> D[Dependency]
~~~

**Retry wrapping breaker:** each attempt can be observed individually by the breaker. A single request can push the breaker to its threshold faster; once OPEN, subsequent retries only receive rejection errors without helping the dependency recover.

With a threshold of 3 consecutive failures and one request whose 3 attempts all time out:

- Breaker outside retry: may record **1** failure.
- Breaker inside retry: may record all **3** failures.

No single order fits every business case. Choose according to your desired measurement unit and cap the number of attempts; only retry recoverable errors, with sensible backoff. For write commands, require an **idempotency key** to avoid duplicate side effects when the dependency processed the request but the response was lost.

## 8. Choosing thresholds per dependency

If the Router sends one branch to **Stock API** and another branch to **Pricing API**, use separate breakers. The two services have different failure domains, traffic volumes, and criticality levels.

| Context | Direction for choosing open condition |
| --- | --- |
| High-traffic service, intermittent errors | Failure rate over sliding window with minimum calls |
| Low-traffic service | Consecutive failure threshold or balanced sliding window/minimum calls |
| Service often slows down before failing | Slow-call rate combined with client timeout |
| Many business errors returned as HTTP 4xx | Classify responses/exceptions before counting |
| Dependency sensitive to retry storms | Cap attempts, apply backoff, rate limiter/bulkhead |
| Multi-pod deployment | Observe each breaker instance; do not assume synchronized state |

A threshold selection process:

1. Measure error rate, timeouts, throughput, and p95/p99 latency when the system is healthy.
2. Identify the error or latency level at which continuing to call becomes clearly harmful.
3. Choose a threshold sensitive enough to block incidents, yet with enough samples to avoid false positives.
4. Define the wait duration before HALF_OPEN and the degree of recovery probing.
5. Test scenarios with low traffic, high traffic, intermittent errors, sustained errors, and recovery.

A threshold that is too low trips the circuit on transient blips. A threshold that is too high lets requests keep timing out, occupying threads and growing queues. The goal is to protect **the overall flow**, not merely reduce error counts on a single client.

## 9. Once the open condition is met: what happens to messages?

~~~mermaid
flowchart TD
    A[Gateway] --> B{Router}
    B -->|Stock needed| C[Stock breaker]
    C -->|CLOSED| D[Stock API]
    C -->|OPEN| E{Handling policy}
    E -->|Fail fast| F[Return temporarily unavailable error]
    E -->|Suitable cache available| G[Return marked stale result]
    E -->|Process later| H[Queue with idempotency key]
    B -->|Pricing branch| I[Pricing API]
    D --> J[Response / Aggregator]
    G --> J
    I --> J
~~~

**An OPEN breaker does not create a fallback automatically.** In a synchronous Gateway over DirectChannel, exceptions can propagate back to the caller; in an asynchronous flow or poller-driven endpoint, errors can route through the **ErrorMessage/error channel** mechanism depending on configuration. Explicitly define the error-handling boundary rather than assuming every exception automatically goes to an error channel.

If a Splitter divides a message into multiple branches and one branch is rejected by the breaker, the Aggregator may miss a reply. Preserve **correlation IDs** and sequence headers and define a group completion policy: partial result, timeout, or routing to an error-handling flow. One OPEN branch must never leave the Aggregator waiting indefinitely.

Fallback results must preserve business semantics. **OUT_OF_STOCK** (checked and out of stock) is different from **TEMPORARILY_UNAVAILABLE** (unable to check because the dependency is unavailable).

## 10. Testing the exact OPEN condition

The best tests not only assert an error at the Gateway, they also verify **StockClient is no longer called** when the breaker is OPEN.

### 10.1. Unit test for Resilience4j failure rate

JUnit 5 example verifying that 4 failures are enough to open the circuit, while the fifth request is rejected immediately:

~~~java
@Test
void opensCircuitWhenFailureRateExceedsThreshold() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50.0f)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger clientCalls = new AtomicInteger();

    Supplier<String> failingClient = () -> {
        clientCalls.incrementAndGet();
        throw new IllegalStateException("dependency unavailable");
    };

    for (int i = 0; i < 4; i++) {
        assertThrows(
                IllegalStateException.class,
                () -> breaker.executeSupplier(failingClient)
        );
    }

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(failingClient)
    );
    assertEquals(4, clientCalls.get());
}
~~~

This test produces 4/4 failures, meets minimum calls, and exceeds the 50% threshold. The OPEN duration is 30 seconds so the fifth call remains blocked during the test. Standard imports are omitted in the example.

### 10.2. Integration flow test matrix

| Scenario | Expected verification |
| --- | --- |
| Native advice: failures below threshold | CLOSED, new requests continue reaching the handler |
| Native advice: one success in between | Consecutive failure streak resets appropriately |
| Native advice: threshold reached | Request that tripped the threshold hit the client; subsequent request is blocked |
| Resilience4j: high failure rate but below minimum calls | Circuit does not open yet |
| Resilience4j: failure rate with enough samples reaches threshold | OPEN, client call count does not increase on rejected requests |
| Slow-call rate reaches threshold | OPEN if slow-call measurement policy is configured |
| Filter rejects invalid request | Input error is not counted as dependency failure |
| HTTP 503 mapped to exception | Breaker records failure |
| Retry inside and outside breaker | Outcome count seen by breaker matches advice placement |
| Splitter/Aggregator hits OPEN branch | Has fallback, timeout, or error with correlation |
| One breaker across multiple instances | Do not assume state synchronizes across pods |

Use a fake client where you can control return values, exceptions, response time, and a call counter. Gateway tests should run through the real handler and advice, avoiding mocking away the layer you need to verify.

## 11. Observing OPEN causes and tuning

Production operations need visibility into both **why the circuit opened** and **the impact on the flow**:

| Signal | Helps answer |
| --- | --- |
| Breaker state and state transitions | Which circuit opened, when it opened, has it recovered? |
| Failure count/rate, minimum calls, window | Were there enough samples and was the threshold genuinely reached? |
| Slow-call count/rate, latency | Is the dependency failing or just abnormally slow? |
| Not-permitted/rejected calls | How many requests were short-circuited? |
| Exception class, HTTP status, timeout | Are errors classified properly or swallowed? |
| Gateway latency, channel queue depth | Is OPEN relieving cascading pressure? |
| Correlation/trace ID, pending Aggregator groups | Which message branches are affected? |

Resilience4j provides an event publisher and metrics integration such as Micrometer. With native advice, inspect the built-in instrumentation for your Spring Integration version and add observability at the handler or client; do not assume all metrics above appear automatically.

If a breaker **stays CLOSED** even when the dependency frequently times out, check: are exceptions being caught, is retry changing the counting unit, is the threshold too high, or have minimum calls not been reached? If a breaker **OPENS too frequently** while the service is healthy, check business error classification, overly short timeouts, or too few samples in the sliding window. If it loops **OPEN → HALF_OPEN → OPEN**, examine actual dependency recovery, wait duration, and probe policy.

## 12. Implementation checklist

- [ ] Breaker protects only the dependency call, not accidentally wrapping Filter, Transformer, or Aggregator.
- [ ] Classify which responses/exceptions are infrastructure failures, business errors, and slow calls.
- [ ] Know whether the breaker counts **consecutive failures**, **failure rate**, or **slow-call rate**.
- [ ] If using a sliding window, configure reasonable minimum calls and window duration/size.
- [ ] Have real client timeouts and concurrency limits when the dependency is slow.
- [ ] Define retry ordering relative to the breaker, max attempts, and idempotency.
- [ ] Gateway/error channel and Aggregator handle OPEN branches and preserve correlation.
- [ ] Tests prove requests arriving after OPEN **do not increase the client call count**.
- [ ] Collect state transitions and failed/slow/rejected calls to tune thresholds against SLOs.

**Circuit open conditions** are conclusions drawn from observed dependency calls under a specific policy. Choosing the right signals, measurement scope, and thresholds helps Spring Integration protect failing branches while keeping Router, Gateway, Splitter, and Aggregator consistent and observable.
