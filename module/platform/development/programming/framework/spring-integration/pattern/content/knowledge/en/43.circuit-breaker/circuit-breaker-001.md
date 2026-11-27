# Circuit breaker protecting dependency-calling flows

## 1. The problem: a slow dependency can stall the entire flow

In a system using **Spring Integration** to implement Enterprise Integration Patterns (EIP), a message typically passes through multiple steps: a Gateway receives the request, a Router selects the branch, a Transformer normalizes the data, a Service Activator calls an external system, and an Aggregator combines the results. Connecting steps via channels reduces direct coupling between components, yet **the flow can still be affected by a remote dependency**.

For example, an order processing flow needs to query the inventory service. When that service loses connectivity or repeatedly returns errors, every call has to wait for a timeout. If traffic increases, message-processing threads get held up, queues accumulate, the Gateway responds slowly, and other branches come under pressure as well.

A **circuit breaker** protects the dependency call site by tracking failed executions. When failures exceed a threshold, the breaker **opens the circuit** and rejects subsequent calls early. After a wait period, the breaker allows controlled probe attempts; if the dependency has recovered, the circuit closes and the flow returns to normal.

The goal of this lesson is to place the circuit breaker at the right position in a Spring Integration flow, understand its impact on Router, Gateway, retry, error channel, and correlation, and design how to test and monitor its state.

## 2. Position in the EIP architecture

~~~mermaid
flowchart LR
    A[Messaging Gateway] --> B[Validate / Transform]
    B --> C{Router}
    C -->|Stock check needed| D[Channel: stock.requests]
    D --> E[Circuit breaker]
    E -->|Closed / allow probe| F[Stock client]
    E -->|Open| G[Rejection handling / fallback]
    F --> H[Stock service]
    H --> I[Response / Aggregator]
    G --> I
    C -->|No stock check needed| J[Other branch]
    J --> I
~~~

The breaker should wrap **the operation that can fail due to the dependency**, not the entire flow. If you place the breaker before the validation step, input data errors can be miscounted as external service failures. If you wrap downstream branches after fetching the result, Mapper or Aggregator errors could also trip the circuit for the wrong reason.

One breaker is typically tied to **one dependency or a group of endpoints sharing the same failure domain**. If inventory and payment are two separate services, use two independent breakers so an inventory outage does not block calls to payment.

| Component | Responsibility | How does it differ from a circuit breaker? |
| --- | --- | --- |
| Timeout | Limits the duration of **each call** | Does not automatically stop subsequent calls when a dependency repeatedly fails |
| Retry | Retries when a call fails | Can increase load on the dependency if not bounded |
| Circuit breaker | Fails fast on calls when a dependency is unhealthy | Does not replace timeouts or concurrency-limiting mechanisms |
| Bulkhead | Limits resources or concurrent calls | Isolates resource pressure, even when a dependency is merely **slow** |
| Rate limiter | Throttles request sending rate | Does not infer on its own that a dependency is failing |
| Error channel | Routes message errors to an error-handling flow | Does not decide on its own when to temporarily stop calling a dependency |

A reliable flow typically combines HTTP/gRPC/DB client timeouts, bounded retries for transient errors, a breaker at the call site, and a strategy for handling unavailable dependencies.

## 3. The three states of a circuit breaker

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failures reach threshold
    OPEN --> HALF_OPEN: Wait duration elapsed, probe call arrives
    HALF_OPEN --> CLOSED: Probe call succeeds
    HALF_OPEN --> OPEN: Probe call fails
~~~

- **CLOSED:** requests are allowed to reach the dependency. The breaker tracks execution outcomes. This is the normal operating state.
- **OPEN:** new requests are rejected locally; no corresponding network call is made. The Gateway can receive a fast failure, or the flow can route to a fallback option.
- **HALF_OPEN:** one or a limited number of probe calls are allowed through to assess recovery. Success allows transitioning back to CLOSED; failure can reopen the circuit.

**Note on threshold semantics:** Spring Integration provides a native **RequestHandlerCircuitBreakerAdvice** based on a **consecutive failures** threshold. Libraries such as Resilience4j can compute a **failure rate over a statistical window** with a minimum number of samples and more options. Do not treat these two counting models as identical.

For example, with a threshold of three consecutive failures: two failures followed by one success is **not equivalent** to three consecutive failures. In a failure-rate model, that same sequence of events may still contribute to the statistical rate depending on the window configuration and minimum number of calls.

## 4. Implementation with Spring Integration Java DSL

### 4.1. Message contract and Gateway

Suppose an inventory check flow takes a SKU and quantity as input payload. The external client is represented via an interface so it can be easily replaced with a mock/fake in tests.

~~~java
public record StockRequest(String sku, int quantity) {}

public record StockResult(
        String sku,
        boolean available,
        int remaining
) {}

public interface StockClient {
    StockResult check(StockRequest request);
}

@MessagingGateway(defaultRequestChannel = "stock.requests")
public interface StockGateway {
    StockResult check(StockRequest request);
}
~~~

A Messaging Gateway allows application code to invoke a synchronous method, while Spring Integration handles converting that method call into a message, sending it to the channel, and receiving the reply.

### 4.2. Attaching RequestHandlerCircuitBreakerAdvice to the right handler

The example below uses Spring Integration Java DSL and **RequestHandlerCircuitBreakerAdvice**. Java imports are omitted to focus on the wiring. In a Spring Boot application, configure component scanning for the Gateway (for example via **@IntegrationComponentScan**) and declare the Spring Integration dependency matching your project version.

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockIntegrationConfig {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockCircuitBreaker() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();

        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000); // milliseconds
        return advice;
    }

    @Bean
    public IntegrationFlow stockFlow(
            StockClient client,
            RequestHandlerCircuitBreakerAdvice stockCircuitBreaker
    ) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockRequest.class,
                        (request, headers) -> client.check(request),
                        endpoint -> endpoint.advice(stockCircuitBreaker)
                )
                .get();
    }
}
~~~

In this snippet:

1. The Gateway sends a **StockRequest** to the **stock.requests** channel.
2. The Service Activator invokes **StockClient.check(...)**; the advice wraps this handler's execution.
3. When the dependency succeeds, **StockResult** returns to the reply channel the Gateway is waiting on.
4. When the handler consecutively throws exceptions up to the configured threshold, the breaker opens; new calls are rejected before reaching the client.
5. After the **halfOpenAfter** duration, a new call can be used to probe for recovery.

Breaker state belongs to the **advice instance**. Do not share the same advice bean between two independent dependencies if you want them to maintain separate failure states. When running multiple application instances, each instance typically holds its own breaker state; this is not a global switch automatically synchronized across pods.

### 4.3. Boundaries to keep clear

The **StockClient.check** method must have timeouts at the actual client layer. For example with HTTP, configure connection timeout and response/read timeout according to your SLA; the **halfOpenAfter** duration only determines when the breaker is allowed to probe and does **not** bound the duration of a network request.

Do not convert every error into a successful result inside the handler wrapped by the advice. If you catch the exception and return a fake StockResult before the exception reaches the breaker, the breaker will not see the failures it needs to record.

Nor should you let expected business errors (invalid SKU, negative quantity, valid business rejections) open the breaker. Validate before the dependency call step and represent business outcomes via a clear data contract. Only failures belonging to the dependency domain should affect circuit state.

## 5. Handling an open circuit and handler failures

**Opening the circuit does not create a fallback automatically.** In a synchronous Gateway/DirectChannel flow, errors from the handler or from the advice typically propagate back up the call stack; the calling layer needs to know whether to return an error, use stale data, or defer processing. In an asynchronous flow, errors can be published as an ErrorMessage through the corresponding error channel mechanism; the exact handling depends on the channel type, poller, and configured error channel.

There are three common handling strategies:

| Strategy | When appropriate | What must be controlled |
| --- | --- | --- |
| Fail fast | Payments, authorization, data that must be immediately accurate | Return a service temporarily unavailable status; do not pretend success |
| Fallback cache | Catalogs, reference inventory, or data allowed to be stale | Attach timestamps and freshness metadata; avoid using stale data for payment decisions |
| Defer / queue | Tasks that can be processed later such as synchronization or notifications | Ensure idempotency, later retry, TTL, and storage for failed tasks |

Represent fallback states using an explicit result type, for example:

~~~java
public enum LookupStatus {
    FRESH,
    STALE_CACHE,
    TEMPORARILY_UNAVAILABLE
}

public record StockLookupOutcome(
        String sku,
        LookupStatus status,
        StockResult data,
        String correlationId
) {}
~~~

When the status is **TEMPORARILY_UNAVAILABLE**, data may be absent; Router/Aggregator steps must handle this state explicitly. Do not turn an error into **StockResult.available = false**: "inventory unknown" is completely different from "checked and out of stock".

For the error channel, distinguish two situations:

- **Synchronous:** The Gateway calls through a DirectChannel; exceptions can bubble directly to the caller. You can handle them at the application boundary or use an intentionally configured error flow.
- **Asynchronous:** An ExecutorChannel or a poller-driven endpoint has an ErrorMessage dispatch path. Consumers on the error channel need to identify the original message, cause, correlation ID, and retry/dead-letter policy.

Simply attaching an **errorChannel** header to a message does not mean all synchronous errors automatically route through an error-handling branch. Check the dispatcher model and execution boundaries of the actual flow.

## 6. Interaction with retry, Router, Splitter, and Aggregator

### Where does retry sit relative to the breaker?

~~~mermaid
flowchart LR
    A[Gateway] --> B[Breaker]
    B --> C[Bounded retry]
    C --> D[Dependency]
~~~

With the order **breaker wrapping retry**, a business request going through multiple internal attempts can be seen by the breaker as **one final successful or failed execution**. This is useful when you want the breaker to evaluate outcomes per logical request, though retries must cap the number of attempts and use backoff to avoid amplifying load.

If you place **retry wrapping the breaker**, each attempt passes through the breaker and contributes to its counter individually; once the breaker is OPEN, subsequent retries typically just receive fast rejections. Design your retry policy so it does not blindly retry when the circuit is open.

An example of a sensible policy: short client timeout, at most one or two retries for recoverable transient errors, backoff with jitter, and the breaker on the outside. Numbers must be based on your SLA, dependency characteristics, and how safe repeated calls are.

### Router and Filter

The Router should choose branches based on **the business meaning of the message**. Place the breaker inside the branch containing the corresponding dependency; do not use circuit state as the sole condition for business routing without an explicit fallback state. Filters remain responsible for discarding invalid messages before they trigger resource-intensive calls.

### Splitter and Aggregator

If an order is split by a Splitter into multiple sub-requests to call several services, an open circuit on one branch can leave the Aggregator missing replies. In that case, clearly define:

- When is a message group considered complete: all results present, partial results, or timeout?
- When no result is received from a dependency, is a **TEMPORARILY_UNAVAILABLE** outcome emitted so the Aggregator can make a decision?
- How are group timeout, expiration, discard channel, and group cleanup configured?

**Correlation ID** and sequence headers must be preserved across all branches, including fallback or deferred-processing branches. In an asynchronous flow, error messages must also carry enough context to correlate back to the original request. Do not let an Aggregator group wait indefinitely simply because the breaker rejected part of the work.

### Idempotency during retry and recovery

Read calls are generally easier to retry than operations with side effects (charging payment, creating orders, deducting inventory). If the dependency processed the request successfully but the reply was lost, retrying can duplicate the operation. For write commands, require an idempotency key and duplicate-handling protection on the receiving side before enabling retries or replaying messages from a queue.

## 7. Choosing native advice or Resilience4j?

**RequestHandlerCircuitBreakerAdvice** fits Spring Integration flows that need a simple consecutive-failure threshold and wait duration, attached directly to a handler via the advice chain. Its advantages are concise configuration, few extra components, and clear illustration of the protection point.

When you need failure-rate evaluation over a sliding window, minimum number of calls, limiting probe calls in HALF_OPEN, exception classification, or detailed metrics/events, **Resilience4j CircuitBreaker** is a suitable option. Even then, the breaker should still wrap the dependency call itself:

~~~java
// Illustrates the handler part when using Resilience4j instead of native advice.
// pricingBreaker is io.github.resilience4j.circuitbreaker.CircuitBreaker.
.handle(
    StockRequest.class,
    (request, headers) ->
        pricingBreaker.executeSupplier(() -> client.check(request))
)
~~~

Do not stack both Resilience4j and native advice to protect the same call without a specific reason, as two state machines can reach different conclusions and make observability harder. If you choose Resilience4j, name the breaker after the dependency, configure the sliding window/minimum calls/failure threshold/wait duration, and specify which exception types count as failures when business rules require it.

## 8. Observing state and troubleshooting

A properly functioning breaker can still reject many requests while the dependency has not recovered. Therefore, monitor **both the root cause and the impact on the flow**:

| Signal | Operational question |
| --- | --- |
| CLOSED / OPEN / HALF_OPEN state per dependency | Which circuit is open, since when, and is it recovering? |
| Client error/timeout count, p95/p99 latency | Is the dependency actually failing, or is the timeout too short? |
| Number of fast-rejected calls | How many requests are affected even without making a network call? |
| Fallback/cache usage rate and data staleness | To what extent is the system operating in degraded mode? |
| Gateway latency, queue depth, thread pool saturation | Has the breaker relieved pressure on the flow, or has congestion shifted elsewhere? |
| Correlation ID / trace ID and exception type | In which branch did a request fail, and for what reason? |

With Resilience4j, you can register event listeners and integrate Micrometer to track state transitions, call outcomes, and denied calls. With native advice, instrument around the handler, Gateway, and dependency client using your metrics/tracing stack; do not assume all metrics appear automatically.

Logs should record the dependency, breaker name, state, exception class, correlation ID, and timestamp; avoid logging sensitive payloads or emitting duplicate logs per retry. You can alert when the rejected-call rate rises for a sustained period, or when the breaker continuously flaps between OPEN and HALF_OPEN.

## 9. Required test scenarios

Use a fake **StockClient** where you can control invocation counts, return values, and exceptions. Decouple time logic so tests remain deterministic; with native configuration you can use a short, controlled wait duration in integration tests, avoiding dependence on long real wait times.

| Scenario | Expected verification |
| --- | --- |
| Healthy dependency | Gateway receives the expected reply; client is called; breaker stays closed |
| Below consecutive failure threshold | Subsequent requests still reach the client |
| Consecutive failure threshold reached | Breaker opens; new calls are rejected before reaching the client |
| While OPEN | Client invocation count **does not increase**; caller receives error or fallback outcome per contract |
| Wait duration elapsed | Probe call is permitted; success closes the circuit, failure reopens it |
| A business-error request | Validation and business errors do not cause the breaker to misjudge the dependency |
| Synchronous Gateway | Exception/reply propagates to the right boundary without hanging |
| Flow with Splitter/Aggregator | Correlation is preserved; missing branch has clear timeout/partial outcome |
| Multiple instances running in parallel | Understand that breaker state on each instance can differ |

Concrete mock example: the consecutive failure threshold is **3**; make the client throw an exception three times. Send a fourth request and assert that **the client is not called again**. After the wait period, have the client return a successful result on the probe call, then verify that new requests pass through again. If you only mock the Gateway to check for an exception without verifying how many times the client was invoked, the test has not proven the breaker's protective behavior.

## 10. Common design mistakes

1. **Not setting a timeout on the client:** a hung call holds resources for a long time before producing a failure for the breaker to record.
2. **Unbounded retries or retrying non-idempotent writes:** worsens outages and can cause duplicated side effects.
3. **Using one breaker for all dependencies:** one failing system takes down healthy systems along with it.
4. **Catching exceptions and returning fake success:** the breaker never learns the dependency is broken and downstream data becomes incorrect.
5. **Confusing business errors with infrastructure errors:** invalid input data unnecessarily trips the circuit.
6. **Not defining a fallback contract:** the Gateway/Aggregator cannot distinguish valid data, stale data, and an unknown state.
7. **Not monitoring rejected calls and queues:** the breaker may stay open for hours while looking only at client errors makes it appear errors have stopped.
8. **Assuming state is shared across pods:** one pod is OPEN while another pod keeps calling the dependency.

## 11. Pre-production checklist

- [ ] Correctly identify the dependency and handler to protect, using separate breakers for independent failure domains.
- [ ] Configure client timeouts, bounded retries if needed, and policies for non-idempotent operations.
- [ ] Explicitly choose the algorithm: consecutive failures of native advice or failure-rate window of Resilience4j.
- [ ] Define the outcome when OPEN: fail fast, controlled caching, or asynchronous processing.
- [ ] Preserve correlation ID, handle ErrorMessage according to the synchronous/asynchronous model, and set bounds for the Aggregator.
- [ ] Measure breaker state, blocked request count, dependency errors, latency, and queue impact.
- [ ] Test circuit opening, probing, recovery, and verify by **actual client invocation count**.

A circuit breaker helps a Spring Integration flow **degrade gracefully** when a dependency is unstable. Effective protection comes from placing it close to the external call, classifying errors properly, applying sensible timeouts and retries, and ensuring message branches still have a clear outcome or error-handling path.
