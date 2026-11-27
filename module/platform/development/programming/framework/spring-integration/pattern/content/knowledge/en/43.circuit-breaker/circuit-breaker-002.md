# Closed, open, and half-open state

## 1. Why does a Circuit Breaker need a state machine?

In **Spring Integration**, an Enterprise Integration Patterns (EIP) flow typically receives a message through a Gateway, uses a Filter/Transformer to normalize it, a Router to select a branch, and then calls a dependency in a Service Activator. Having steps communicate via channels reduces coupling between components, yet a slow or repeatedly failing external API can still congest the entire branch.

A **Circuit Breaker** is placed at the dependency call site to decide **whether to allow a new call to pass through**. That decision depends on three core states:

- **CLOSED:** allows requests through and observes the outcomes.
- **OPEN:** rejects new requests early, avoiding further load on a failing dependency.
- **HALF_OPEN:** after a wait duration, allows a controlled number of probe requests to check whether the dependency has recovered.

This is the **state of the guard**, not the success/failure state of an individual message. For example, when the breaker is CLOSED, a call can still fail; it is precisely those recorded failures that can lead to OPEN.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> CLOSED: Call succeeds / failures below threshold
    CLOSED --> OPEN: Circuit open condition met
    OPEN --> OPEN: Reject new requests during wait duration
    OPEN --> HALF_OPEN: Wait duration elapsed and probe request arrives
    HALF_OPEN --> CLOSED: Probe outcome meets recovery condition
    HALF_OPEN --> OPEN: Probe outcome shows continued failure
~~~

The diagram above describes **conceptual behavior**. How "condition met" and the number of probe requests are defined depends on the library and configuration. For instance, Spring Integration's **RequestHandlerCircuitBreakerAdvice** uses a consecutive-failure threshold, whereas **Resilience4j** can base transitions on failure rate within a statistical window.

## 2. CLOSED: normal operation and signal collection

In the CLOSED state, the breaker lets calls reach the dependency:

~~~mermaid
sequenceDiagram
    participant G as Gateway / Flow
    participant B as Circuit Breaker
    participant D as Dependency
    G->>B: Request A
    B->>D: Forward A
    D-->>B: Response / exception
    B-->>G: Response / exception
    Note over B: Record outcome, evaluate open condition
~~~

Importantly, **CLOSED does not guarantee the dependency is healthy**. This state only indicates that the breaker does not yet have sufficient evidence to reject new requests. Some requests in CLOSED may still time out or receive HTTP 5xx responses.

### What counts as a failure?

You must clearly distinguish three classes of outcomes:

| Outcome | Example | Should it affect the breaker? |
| --- | --- | --- |
| Technical and business success | Service returns valid inventory data | Counted as a successful call |
| Transient dependency failure | Connection refused, timeout, HTTP 503 | Should generally count as a failure |
| Expected business error | Negative quantity, non-existent SKU, invalid request | Typically handled as a business result; should not open the circuit |

If a handler catches all exceptions and returns a fake "success" object, the breaker may never know the dependency has failed. Conversely, if input validation errors are included inside the protected execution, bad client data can trip the circuit unnecessarily.

### Failure thresholds and statistical windows

There are two common counting approaches:

1. **Consecutive failures:** after a sufficiently long streak of failures, the breaker transitions to OPEN. With a threshold of three consecutive failures, the sequence **failure → failure → success → failure** does not yet form three consecutive failures.
2. **Failure rate over a sliding window:** tracks a window of recent calls; once enough samples are collected and the failure rate exceeds the configured threshold, the breaker can transition to OPEN. For example, **5/10 failed calls** corresponds to a 50% failure rate, but only applies if the minimum calls requirement has been met.

The two metrics answer different questions: "how many times in a row did the dependency just fail?" and "among recent requests, how high is the failure rate?". Choose based on actual traffic, failure characteristics, and tolerance for degradation.

## 3. OPEN: cutting off the dependency call and failing fast

When the open condition is satisfied, the breaker transitions to OPEN. New requests are blocked right at the breaker and **are not sent to the dependency**:

~~~mermaid
sequenceDiagram
    participant G as Gateway / Flow
    participant B as Circuit Breaker
    participant D as Dependency
    G->>B: Request B
    Note over B: State = OPEN
    B--xG: Exception / fallback result
    Note over D: Does not receive Request B
~~~

The purpose of OPEN is to **limit cascading damage**: avoiding wasting additional sockets, threads, wait time, and requests on a dependency showing signs of failure. However, OPEN **does not automatically generate replacement data**. The flow must define what happens to rejected messages.

There are three common options:

| Policy | Behavior in OPEN | Example |
| --- | --- | --- |
| Fail fast | Return a service-temporarily-unavailable error to the caller | Payment confirmation API |
| Conditional fallback | Read from cache and mark data as stale | Product catalog recommendations |
| Defer | Place the request into a queue for later processing | Notification or report synchronization |

Do not turn "unable to reach inventory service" into "definitely out of stock". The two states have different business meanings, and downstream Transformers/Aggregators must be able to tell them apart.

In a **synchronous** Gateway using a DirectChannel, errors in OPEN typically propagate back to the caller along the synchronous call path. In an **asynchronous** flow or a poller-driven endpoint, errors can flow through the appropriate **ErrorMessage/error channel** mechanism. Do not assume that merely declaring an error channel will automatically route all exceptions from a synchronous Gateway to it.

### OPEN does not mean stopping everything already in flight

Some requests may have been admitted **before** the circuit opened and are still executing. A breaker typically blocks **new** calls rather than canceling in-flight calls. Therefore, you still need timeouts on HTTP/DB clients and resource limits when a dependency is slow. You also need to keep monitoring upstream errors, queue depth, and rejected call counts while OPEN.

## 4. HALF_OPEN: probing for recovery

OPEN should not remain active forever once the dependency has recovered. After the **configured wait duration**, the breaker can enter a controlled retry phase called HALF_OPEN.

- One or a limited group of **probe** calls are permitted to reach the dependency.
- If the outcome satisfies the recovery policy, the breaker returns to CLOSED and resumes normal traffic.
- If the probe outcome shows the dependency is still failing, the breaker transitions back to OPEN to rest again.
- When multiple threads call concurrently, admission/rejection behavior depends on how the library manages permits and concurrency; do not assume every library allows strictly one probe.

~~~mermaid
sequenceDiagram
    participant G as Gateway / Flow
    participant B as Circuit Breaker
    participant D as Dependency
    Note over B: OPEN, wait duration elapsed
    G->>B: Probe request
    Note over B: HALF_OPEN
    B->>D: Attempt call
    alt Recovery condition met
        D-->>B: Success
        Note over B: CLOSED
        B-->>G: Response
    else Not recovered yet
        D--xB: Failure
        Note over B: Back to OPEN
        B--xG: Exception / fallback
    end
~~~

**The wait duration before HALF_OPEN is different from a request timeout.** For example, the circuit waits 15 seconds before retrying, while the probe call still has its own 2-second HTTP timeout. Increasing the breaker wait duration cannot replace a network timeout.

In many implementations, the wait duration elapsing does not mean a background thread proactively calls the dependency. The state may only change—or the probe only start—**when the next request arrives**. Therefore, if you want proactive recovery checks, you need a dedicated health check with an appropriate policy rather than assuming the breaker sends heartbeats on its own.

### HALF_OPEN under heavy traffic

Suppose the dependency has just recovered and 500 requests arrive simultaneously: if all of them are allowed through HALF_OPEN, the service could be overloaded again. Libraries such as **Resilience4j** let you configure the number of permitted calls in HALF_OPEN, while calls not granted a permit are rejected. With **native Spring Integration advice**, do not assume a probe limiter with the exact same semantics exists; verify the exact version and configuration in use.

## 5. Tracing a real-world lifecycle

Suppose an inventory check system has a **threshold of 3 consecutive failures** and waits **15 seconds** before allowing a probe. The table below illustrates a progression under the consecutive-failure model, with time measured from when the circuit opens:

| Step | Event | State after event | Stock Service called? |
| --- | --- | --- | --- |
| 1 | Request A succeeds | CLOSED | Yes |
| 2 | Request B times out | CLOSED | Yes |
| 3 | Request C times out | CLOSED | Yes |
| 4 | Request D times out, threshold reached | OPEN | Yes (Request D was already invoked before failing) |
| 5 | Request E arrives while circuit is OPEN | OPEN | **No** |
| 6 | Once probe window is reached, Request F arrives | HALF_OPEN during probe | **Yes, probe** |
| 7a | F succeeds and meets recovery condition | CLOSED | Yes |
| 7b | Or F continues to fail | Back to OPEN | Yes |

Steps 7a and 7b are **mutually exclusive branches**, not two sequential events. The example illustrates the essence of the state machine, while exact transition details after one or multiple probes are determined by the implementation.

A common point of confusion: **call D had to fail for the circuit to become OPEN**. Request D was not blocked beforehand; Request E arriving afterward is what experiences the protective effect of OPEN. Tests must inspect actual client invocation counts to prove this.

## 6. Attaching a Circuit Breaker in Spring Integration

### 6.1. Gateway and message contract

The examples below assume Spring Integration and the Java DSL are configured in a Spring project. Imports are omitted for readability.

~~~java
public record StockQuery(String sku, int requiredQuantity) {}

public record StockSnapshot(
        String sku,
        int availableQuantity,
        boolean enoughStock
) {}

public interface StockClient {
    StockSnapshot lookup(StockQuery query);
}

@MessagingGateway(defaultRequestChannel = "stock.lookup.requests")
public interface StockGateway {
    StockSnapshot lookup(StockQuery query);
}
~~~

The **StockClient** adapter layer must configure connection timeout and response timeout. Validation for SKU and requiredQuantity should happen before the dependency call to keep input data errors out of the inventory service's health statistics.

### 6.2. Using RequestHandlerCircuitBreakerAdvice

**RequestHandlerCircuitBreakerAdvice** protects a request handler. Example using a consecutive-failure threshold and a wait duration before probing:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockFlowConfiguration {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockBreakerAdvice() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();

        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000); // milliseconds
        return advice;
    }

    @Bean
    public IntegrationFlow stockLookupFlow(
            StockClient stockClient,
            RequestHandlerCircuitBreakerAdvice stockBreakerAdvice
    ) {
        return IntegrationFlow.from("stock.lookup.requests")
                .handle(
                        StockQuery.class,
                        (request, headers) -> stockClient.lookup(request),
                        endpoint -> endpoint.advice(stockBreakerAdvice)
                )
                .get();
    }
}
~~~

In this flow, the Gateway sends a **StockQuery** to the channel; the handler calls StockClient when the breaker allows it. The advice records the handler's outcome and decides whether to reject subsequent executions. When OPEN, the call does not proceed to StockClient, so the Gateway needs a clear exception-handling contract.

**Note:** the native advice's consecutive-failure threshold is **not** a sliding-window failure-rate configuration. The failure-rate and HALF_OPEN probe count examples in the next section belong to **Resilience4j** and do not apply directly to the native advice.

### 6.3. When you need HALF_OPEN customization with Resilience4j

Resilience4j supports failure-rate thresholds, minimum calls, statistical windows, and the number of permitted calls in HALF_OPEN. Configuration example:

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

// Only wrap the dependency call inside the handler:
StockSnapshot snapshot =
        stockBreaker.executeSupplier(() -> stockClient.lookup(query));
~~~

In this illustrative configuration, once at least 5 calls have been recorded in the window and the failure rate reaches the threshold, the breaker can open. After 15 seconds, up to 2 probe calls are permitted in HALF_OPEN; evaluating whether to return to CLOSED or OPEN follows Resilience4j's rules based on their results.

In a production system, you must classify which exceptions are recorded versus ignored, add appropriate timeouts, name breakers by dependency, and integrate metrics. Do not share one breaker instance across multiple dependencies that do not share the same failure domain.

## 7. How does the state machine affect other EIPs?

### Gateway and Router

The **Gateway** is the boundary between application calls and the message flow. When the breaker is OPEN, the caller can receive an immediate exception, or an application layer can translate it into a response indicating the service is temporarily unavailable. The **Router** selects branches based on business logic; placing the breaker in the branch that actually calls the dependency preserves independence between branches.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Filter / Transformer]
    B --> C{Router}
    C -->|Lookup stock| D[Circuit breaker: stock]
    C -->|Lookup pricing| E[Circuit breaker: pricing]
    D --> F[Stock service]
    E --> G[Pricing service]
    D --> H[Reply / fallback]
    E --> H
~~~

When the stock breaker is OPEN while the pricing breaker is CLOSED, the price lookup branch can still run. That is one way a circuit breaker supports loosely coupled, extensible flow design.

### Retry and state

Retry and breaker solve different problems:

- **Retry** is for errors likely to recover quickly; each extra attempt adds load.
- **Circuit breaker** prevents generating new load when a dependency shows sustained signs of failure.
- **Timeout** limits how long a single call holds resources; a breaker does not replace a timeout.

The advice wrapping order changes the number of "calls" the breaker records. If the breaker wraps retry, a group of attempts can be evaluated as one final execution. If retry wraps the breaker, each attempt passes through the breaker; when OPEN, extra retries may just produce a burst of fast rejections. Therefore, **do not retry OPEN-circuit rejections indefinitely**.

### Splitter, Aggregator, and correlation

If a **Splitter** splits an order into multiple sub-messages, a branch calling an OPEN dependency may fail to return a normal payload. The **Aggregator** may be missing part of the results and wait forever without a group completion policy.

Preserve **correlation IDs** and sequence headers, and define clear outcomes for unavailable branches. For instance, a branch can emit a **TEMPORARILY_UNAVAILABLE** result with the correlation ID so the Aggregator assembles a partial response; or enforce a group timeout and route the message to a controlled error-handling flow.

For write operations with side effects, replaying messages after HALF_OPEN/circuit close can cause duplicate processing. Require an idempotency key before combining retries or queue replay.

### Error channel

When the breaker is OPEN, errors from a synchronous handler typically bubble up to the caller. For asynchronous endpoints, errors can be routed to an **error channel** per the channel/poller error-handling mechanism. Do not treat the error channel as a substitute for a fallback contract: the receiver still needs to know which request was rejected, whether it is safe to retry, and how to handle correlation.

## 8. Testing the three states with a fake dependency

Use a fake StockClient that can switch behavior between **returning success** and **throwing an exception**, while counting total invocations. From your test, send messages through the real Gateway to verify the full Spring Integration path.

| Scenario | Expected verification |
| --- | --- |
| CLOSED, dependency succeeds | Receive expected StockSnapshot; client invoked exactly once |
| CLOSED, failures below threshold | Caller receives error; subsequent requests can still reach the client |
| Open condition met | The failing call reached the client; breaker transitions to OPEN |
| OPEN, multiple new requests | Calls are rejected fast; **call counter does not increase** |
| Wait duration elapsed, request arrives | Probe request passes through according to HALF_OPEN policy |
| Probe succeeds | Breaker recovers to CLOSED when condition is met |
| Probe fails | Breaker returns to OPEN, blocking subsequent requests |
| Retry combined with OPEN | Client invocation count is bounded; no blind retrying of OPEN rejections |
| Splitter/Aggregator hits OPEN | Partial result/timeout/error path exists; does not wait indefinitely |
| Multiple application instances | Do not assume the breaker synchronizes state across instances |

A simple test sequence for the **3 consecutive failures** example:

1. Have the fake client throw an exception for three requests sent through the Gateway.
2. Record **call counter = 3** (assuming retries are disabled).
3. Send the next request while the circuit is OPEN; assert **call counter is still 3**.
4. After the configured wait duration, configure the fake to return success and send a probe request.
5. Verify the probe handling path and subsequent requests after the breaker recovers.

To keep tests stable, use a short wait duration dedicated to the test environment or appropriate clock control if the library supports it. Avoid tests that only assert on exception messages: that does not prove OPEN actually blocked calls to the dependency.

## 9. Observing and diagnosing state transitions

For operations, record at a minimum:

| Signal | Meaning |
| --- | --- |
| Current state per dependency | Know which branch is CLOSED, OPEN, or HALF_OPEN |
| State transition event | Know when the circuit opened, recovered, and whether it is flapping |
| Failed / slow call rate | Distinguish dependency errors from rising latency |
| Rejected / not-permitted calls | Measure requests short-circuited in OPEN and when HALF_OPEN lacks permits |
| Gateway latency and queue depth | Assess impact on the entire flow |
| Correlation ID, error type, branch | Trace the message and the failing dependency |

Resilience4j provides an event publisher and Micrometer integration. With native Spring Integration advice, check the observability mechanisms available in your version and add appropriate instrumentation yourself; do not assume all of the metrics above appear automatically.

If the breaker continuously **flaps OPEN ↔ HALF_OPEN**, the dependency may not have genuinely recovered, the wait duration may be too short, or the probe count may be too high. If the breaker remains CLOSED while the Gateway is consistently slow, inspect client timeouts, failure thresholds, failure rates, thread pools, and concurrency limits.

## 10. Misconceptions that cause bugs

1. **"CLOSED means every request succeeds."** False: CLOSED only permits calls and measures outcomes.
2. **"OPEN means the client is called but returns an error immediately."** False: new requests are rejected at the breaker; the client does not need to be called.
3. **"After exactly 15 seconds, the dependency automatically receives a probe."** Not necessarily: many implementations only probe when the next request arrives.
4. **"HALF_OPEN definitely lets all requests through."** False: the number of probes may be capped; conditions and policies depend on the implementation.
5. **"Increasing the half-open wait will fix network timeouts."** False: the two durations serve different purposes.
6. **"Every exception reflects an infrastructure error."** False: you must separate business errors from dependency errors.
7. **"OPEN drops messages, so the Aggregator completes automatically."** False: you need timeouts, fallbacks, or error messages with explicit correlation.
8. **"One state is shared across all pods."** Not by default: in-process breakers typically maintain per-instance state.
9. **"More retries mean faster recovery from errors."** False: during a widespread outage, retries can overload the dependency and delay recovery.

## 11. Pre-production self-check

- [ ] Wrap only dependency calls that can fail; validate data before the breaker.
- [ ] Clearly understand whether your library counts **consecutive** failures or a **sliding-window rate**.
- [ ] Know what the caller receives in OPEN and where ErrorMessages are handled.
- [ ] Have real client timeouts; bounded retries that are safe with idempotency.
- [ ] Define the conditions, probe count, and HALF_OPEN wait duration per implementation.
- [ ] Ensure Router/Splitter/Aggregator handle missing-data branches and preserve correlation.
- [ ] Have tests proving OPEN blocks client calls using a call counter.
- [ ] Monitor state, state transitions, rejected calls, and effects on latency/queues.

**CLOSED** is the phase for permitting and observing, **OPEN** is the phase for protecting via early rejection, and **HALF_OPEN** is the phase for verifying recovery. Understanding these three states lets you place a Circuit Breaker into Spring Integration flows while preserving separation between EIPs, error-handling paths, and per-message result contracts.
