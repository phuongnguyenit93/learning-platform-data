# Never retry endlessly when the circuit is open

## 1. The problem: the breaker cuts off the API yet retry keeps looping

In the **SPRING_INTEGRATION_PATTERN** module, Spring Integration enables building flows according to Enterprise Integration Patterns (EIP): a Gateway receives requests, a Filter checks messages, a Transformer normalizes data, a Router switches branches, a Service Activator calls dependencies, and Splitter/Aggregator coordinate multi-branch results. Message channels reduce coupling between components, yet an unavailable dependency can still cause congestion if the system lacks a proper error policy.

A **circuit breaker** protects the dependency call site through three states:

- **CLOSED:** allows requests through and measures outcomes.
- **OPEN:** fast-rejects new requests; the dependency receives no corresponding calls.
- **HALF_OPEN:** allows a number of probe requests per policy, then decides whether to close again or stay open.

**Retry** is meant for transient, recoverable failures. A dangerous mistake is letting Retry catch every exception and retry endlessly, even when the breaker is OPEN. Every attempt receives the same rejection error. Even without creating new HTTP requests, it still consumes time, worker threads, memory, logs, and can cause bottlenecks at the Gateway or queues.

**Rule:** when the breaker refuses execution, **stop retrying the current request immediately**. Return a meaningful error, use a safe fallback, or persist the work for later processing with explicit bounds, backoff, and deadlines. The OPEN wait period belongs to the breaker; an endless retry loop does not make the dependency recover.

~~~mermaid
flowchart TD
    A[Gateway receives message] --> B[Validate / Transform]
    B --> C[Circuit breaker]
    C -->|Permitted| D[Dependency]
    D -->|Success| E[Reply]
    D -->|Transient error| F{Retry budget left?}
    F -->|Yes and safe| G[Bounded backoff]
    G --> C
    F -->|No| H[Error / fallback]
    C -->|OPEN or out of permits| I[Stop retrying immediately]
    I --> H
    H --> J[Fail fast / Cache / Durable defer]
~~~

The diagram illustrates the logical policy. Whether Retry sits outside or inside the Circuit Breaker affects the number of attempts observed by the breaker; decide explicitly rather than wiring two advices out of habit.

## 2. Distinguishing dependency errors from breaker rejections

| Case | Was the dependency called? | Generally appropriate action |
| --- | --- | --- |
| Connection refused or response timeout | Yes | Bounded retry if safe, with backoff |
| HTTP 503 converted to exception by client | Yes | Can apply bounded retry per policy |
| HTTP 429 | Possibly | Respect quota policy or Retry-After if present |
| Validation error detected by Filter | No | Return input error, do not retry |
| Circuit is **OPEN** | **No** | Do not retry immediately; use fallback or fail fast |
| **HALF_OPEN** has no permits left | **No** | Do not loop contending for permits |
| HALF_OPEN probe times out | Yes | Let breaker record failure, handle per policy |
| Programming bug in Transformer | Not a dependency error | Fix application bug, do not blindly retry API |

With **Resilience4j**, calls rejected when the circuit grants no permit can throw **CallNotPermittedException**. This is an error from the guard, not proof that the HTTP client just failed. Do not add rejections to Stock API execution failure counts; track them with a separate **not-permitted/rejected calls** metric.

With Spring Integration's native **RequestHandlerCircuitBreakerAdvice**, the rejection exception type can differ from Resilience4j. When using Spring Retry, identify the exact exception from your library version in the flow and put it in the **non-retryable** group. Do not assume every breaker throws `CallNotPermittedException`.

## 3. How does retrying while OPEN waste resources?

Suppose the Gateway sends an inventory lookup request while the breaker is already OPEN. Retry is configured for up to 5 attempts, 200 ms apart, yet retries all `RuntimeException`s.

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant R as Retry
    participant B as Breaker OPEN
    participant S as Stock API
    G->>R: StockQuery
    loop 5 attempts
        R->>B: Retry
        B--xR: Not permitted
        Note over S: Receives no HTTP request
    end
    R--xG: Final error
~~~

In this example Stock API receives **0 calls**, yet Retry enters the breaker **5 times**. Without a retry limit, a single request can hold a worker for a very long time. Under heavy load, the system burns CPU, adds latency, and piles up messages only to discover the circuit is still OPEN.

An even worse case: a consumer pulls a message from a broker, receives an OPEN error, and **NACKs/requeues immediately**. The broker redelivers the message, the consumer fails again, and NACKs again. This loop can run indefinitely even with zero HTTP requests reaching upstream.

Distinguish three retry layers that may exist simultaneously:

1. **HTTP/client retry:** retries the physical call to the dependency.
2. **Handler/message-flow retry:** Spring Retry or Resilience4j Retry re-executes the handler's logic.
3. **Broker/Gateway caller redelivery:** the entire message or business request is resent.

If each layer has its own cap without an overall budget, call counts can multiply. For example, 3 client attempts, 4 broker deliveries, and 2 caller resends can generate up to **24 physical calls** if all layers execute. Therefore, bound **overall** attempts, preserve correlation, and deduplicate when needed.

## 4. Building a retry policy with a stopping point

| Rule | How to apply |
| --- | --- |
| Retry the right error types | Only transport errors or select transient upstream errors |
| Stop on OPEN | Exclude `CallNotPermittedException` and equivalent rejection errors |
| Bound attempts | E.g. max 3 attempts, including the initial one |
| Use backoff and jitter | Reduce risk of many clients retrying in lockstep |
| Enforce overall deadline | Never exceed how long the Gateway is allowed to wait |
| Check idempotency | Avoid duplicating create-order, reserve-stock, or charge commands |
| End cleanly when budget expires | Return error, fallback, or durable defer with TTL |
| Observe attempts | Separate logical requests, breaker entries, HTTP calls, and redeliveries |

**Resilience4j Retry** defines **maxAttempts(3)** as total executions, consisting of one initial attempt and at most two retries. With other libraries, verify whether `maxAttempts` means total attempts or additional retries.

### Backoff, jitter, and deadlines

Exponential backoff might increase wait intervals across failures from 200 ms to 400 ms and then 800 ms; **jitter** adds a bounded random offset so callers do not retry simultaneously. Exact numbers are illustrative and must be tuned to SLOs and upstream load.

An 800 ms client timeout with up to three attempts, plus 200 ms and 400 ms backoffs, can take roughly **3 seconds** if all three hit the timeout. If the Gateway has a 1.5-second reply deadline, that policy fails the requirement even if it eventually succeeds. Other steps in the flow consume time too, so the overall deadline must cover Transformer, Router, handler, and reply.

When the breaker is OPEN, waiting a few hundred milliseconds and retrying immediately **is not equivalent** to waiting out the OPEN duration. The right approach is terminating the current execution and, if permitted, scheduling future work via durable infrastructure rather than sleeping a thread.

## 5. Ordering Retry and Circuit Breaker

### 5.1. Breaker outside Retry

~~~mermaid
flowchart LR
    G[Gateway] --> B[Circuit breaker]
    B --> R[Bounded retry]
    R --> D[Stock API]
~~~

The breaker can observe **the final outcome of one logical request**. If all three retries time out, the outer breaker may record one failed execution. If the third succeeds, the breaker may see one success even though the client had two failed attempts.

When the circuit is OPEN, the inner Retry **does not run** because the breaker rejects from the outside. However, in HALF_OPEN, **one probe permit can contain multiple network calls** due to the inner Retry. This can add load onto a barely recovered dependency. Bound attempts and deadlines for probes.

### 5.2. Retry outside Breaker

~~~mermaid
flowchart LR
    G[Gateway] --> R[Bounded retry]
    R --> B[Circuit breaker]
    B --> D[Stock API]
~~~

Each attempt passes through the breaker and can contribute to the failure count. One business request can push the breaker to OPEN mid-retry. When that happens, rejection errors must be classified as **non-retryable**, avoiding pointless retries.

| Criterion | Breaker outside Retry | Retry outside Breaker |
| --- | --- | --- |
| Unit measured by breaker | Usually final outcome of logical request | Each attempt permitted to execute |
| Three timeouts on one request | Can contribute 1 failure | Can contribute 3 failures |
| Breaker OPEN before request | Retry does not run | Retry must stop upon receiving rejection |
| HALF_OPEN | One probe can include multiple HTTP attempts | Each attempt may need its own permit |
| Signals to observe | Logical calls and HTTP attempts | Retry count, breaker events, rejected calls |

No single order fits every system. Choose based on the **failure unit to measure**, upstream protection level, and total physical calls in HALF_OPEN; then test the actual advice chain implemented.

## 6. Spring Integration Java DSL example with Resilience4j

This example illustrates an inventory lookup flow. **StockClient** is an application adapter with timeouts that converts connection/5xx errors into **StockTransportException**. Java imports are omitted; use Resilience4j Retry/CircuitBreaker modules matching your project version.

### 6.1. Contract

~~~java
public record StockQuery(String sku, int quantity) {}

public record StockReply(String sku, int availableUnits) {}

public interface StockClient {
    StockReply lookup(StockQuery query);
}

public class StockTransportException extends RuntimeException {
    public StockTransportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Place a Filter or Validator before the handler to reject negative quantities and empty SKUs. Do not convert validation exceptions into `StockTransportException`: the breaker should only evaluate dependency health.

### 6.2. Configuring the breaker and bounded retry

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockFlowConfig {

    @Bean
    public CircuitBreaker stockBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreaker.of("stock-api", config);
    }

    @Bean
    public Retry stockRetry() {
        RetryConfig config = RetryConfig.custom()
                .maxAttempts(3)
                .waitDuration(Duration.ofMillis(200))
                .retryExceptions(StockTransportException.class)
                .ignoreExceptions(CallNotPermittedException.class)
                .build();

        return Retry.of("stock-retry", config);
    }

    @Bean
    public StockLookupService stockLookupService(
            StockClient client,
            CircuitBreaker stockBreaker,
            Retry stockRetry
    ) {
        return new StockLookupService(client, stockBreaker, stockRetry);
    }

    @Bean
    public IntegrationFlow stockFlow(StockLookupService service) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> service.lookup(query)
                )
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "stock.requests")
public interface StockGateway {
    StockReply lookup(StockQuery request);
}
~~~

**retryExceptions** restricts which error types are retried. **ignoreExceptions(CallNotPermittedException.class)** lets rejection exceptions exit without further retries. You still need to verify whether exceptions get wrapped in another exception type at the handler boundary.

### 6.3. Executing in the right order with decorators

~~~java
public class StockLookupService {

    private final StockClient client;
    private final CircuitBreaker breaker;
    private final Retry retry;

    public StockLookupService(
            StockClient client,
            CircuitBreaker breaker,
            Retry retry
    ) {
        this.client = client;
        this.breaker = breaker;
        this.retry = retry;
    }

    public StockReply lookup(StockQuery request) {
        Supplier<StockReply> remoteCall =
                () -> client.lookup(request);

        Supplier<StockReply> breakerProtected =
                CircuitBreaker.decorateSupplier(breaker, remoteCall);

        // Retry is the outer layer. When the breaker rejects, retry stops.
        Supplier<StockReply> boundedRetry =
                Retry.decorateSupplier(retry, breakerProtected);

        return boundedRetry.get();
    }
}
~~~

The order here is **Retry → Circuit Breaker → StockClient**. If StockClient times out while CLOSED, the error passes through the breaker and can be retried by Retry within limits. If the circuit is OPEN, the breaker skips the supplier and throws `CallNotPermittedException`; Retry is configured to ignore this error, so it exits immediately. The Gateway receives the exception or the fallback layer handles it.

**Do not catch exceptions inside `remoteCall` to return a fake `StockReply`**. Doing so makes the breaker see only successes and fail to open when upstream breaks. If you want caching/fallback, apply it **after the breaker has recorded the failure**, at the boundary outside the decorators.

### 6.4. If you choose Breaker wrapping Retry

Flip the decorators so the breaker sees only the final outcome:

~~~java
Supplier<StockReply> remoteCall =
        () -> client.lookup(request);

Supplier<StockReply> retryInner =
        Retry.decorateSupplier(retry, remoteCall);

Supplier<StockReply> breakerOuter =
        CircuitBreaker.decorateSupplier(breaker, retryInner);

return breakerOuter.get();
~~~

When OPEN, `retryInner` does not run. However, HALF_OPEN can allow a logical request containing three physical attempts. Decide whether that load is acceptable, especially when the dependency recovers slowly.

## 7. Native Spring Integration advice and Spring Retry

Spring Integration provides **RequestHandlerCircuitBreakerAdvice** and **RequestHandlerRetryAdvice**. When using both on one handler, the **advice chain order** determines whether the breaker counts logical requests or individual attempts.

Conceptual configuration example:

~~~java
@Bean
public RequestHandlerCircuitBreakerAdvice stockCircuitAdvice() {
    RequestHandlerCircuitBreakerAdvice advice =
            new RequestHandlerCircuitBreakerAdvice();
    advice.setThreshold(3);
    advice.setHalfOpenAfter(20_000);
    return advice;
}

@Bean
public RequestHandlerRetryAdvice stockRetryAdvice() {
    RequestHandlerRetryAdvice advice =
            new RequestHandlerRetryAdvice();

    RetryTemplate template = new RetryTemplate();

    Map<Class<? extends Throwable>, Boolean> retryable =
            new HashMap<>();
    retryable.put(StockTransportException.class, true);

    SimpleRetryPolicy policy =
            new SimpleRetryPolicy(3, retryable, true, false);
    template.setRetryPolicy(policy);

    FixedBackOffPolicy backOff = new FixedBackOffPolicy();
    backOff.setBackOffPeriod(200);
    template.setBackOffPolicy(backOff);

    advice.setRetryTemplate(template);
    return advice;
}
~~~

In this example, the policy only allows retrying **StockTransportException** and is capped at **3 attempts**. **StockTransportException** is an application-defined class. Check exception wrappers and cause-chain traversal behavior in your Spring Retry version so real timeouts are classified properly.

Attaching the advices to a Service Activator:

~~~java
@Bean
public IntegrationFlow stockFlow(
        StockClient client,
        RequestHandlerCircuitBreakerAdvice stockCircuitAdvice,
        RequestHandlerRetryAdvice stockRetryAdvice
) {
    return IntegrationFlow.from("stock.requests")
            .handle(
                    StockQuery.class,
                    (query, headers) -> client.lookup(query),
                    endpoint -> endpoint.advice(
                            stockCircuitAdvice,
                            stockRetryAdvice
                    )
            )
            .get();
}
~~~

The example expresses the intent of **breaker wrapping Retry**. When implementing, confirm execution order of the advice chain with an integration test using a fake client, because advisor ordering and proxy mechanisms in a specific setup can affect semantics. Never put **breaker rejection** exceptions into the retryable whitelist.

If using a recovery callback to return a fallback, inspect recovery placement: a fallback inside the breaker-protected zone can swallow exceptions and prevent the breaker from seeing dependency errors. With both Resilience4j and native advice, the rule is letting the breaker **observe real failures** before converting them into degraded outcomes.

## 8. OPEN: fail fast, cache, or durable defer?

The circuit breaker does not decide the business outcome when OPEN. The flow must choose an appropriate strategy.

| Strategy | Case | Outcome to express |
| --- | --- | --- |
| **Fail fast** | Checkout, payment, reservation confirmation | **UNAVAILABLE** or structured exception |
| **TTL cache** | Catalog info for reference only | **STALE_REFERENCE**, include data origin and timestamp |
| **Backup provider** | Secondary source with equivalent contract | Use separate timeout and breaker for backup source |
| **Durable defer** | Notifications, background synchronization | **ACCEPTED_FOR_LATER** after durable persistence |

Do not return **available = false** when Stock API cannot be reached: "inventory unknown" is different from "verified out of stock". Use a contract separating **FRESH**, **STALE_REFERENCE**, and **UNAVAILABLE** so downstream Router and Aggregator never misinterpret it.

**Not retrying immediately when OPEN** does not mean permanently dropping the task. For deferrable work, you can schedule another attempt in the future. The difference is that **every attempt must be bounded and tracked**.

~~~mermaid
flowchart TD
    A[Consumer receives message] --> B{Attempt budget and TTL left?}
    B -->|No| Z[DLQ / terminal failure]
    B -->|Yes| C[Circuit breaker]
    C -->|Permitted| D[Dependency]
    D -->|Success| E[ACK complete]
    D -->|Transient error| F[Schedule retry with backoff]
    C -->|OPEN / no permit granted| F
    F --> G[Delayed queue / durable outbox]
    G -->|Scheduled time reached| A
~~~

To defer safely, you need:

- **ACK after durable save**, never return success before the message is actually persisted.
- **attemptCount / maxAttempts**, **firstFailureAt**, **nextAttemptAt**, **expiresAt**.
- **Backoff with jitter**, queue limits, and backpressure controls.
- **Dead-letter queue** or terminal state when attempt budget or TTL is exhausted.
- **Correlation ID, tenant context, and idempotency key** for tracing and preventing duplicate processing.

A consumer must not run a `Thread.sleep` loop spanning the OPEN duration, as that ties up workers and starves other messages. Prefer a scheduled poller, delayed queue, or outbox according to your infrastructure capabilities.

## 9. Error channel and broker redelivery

In Spring Integration, distinguish error boundaries:

- **Synchronous Gateway over DirectChannel:** exceptions can propagate straight to the caller. The REST/application boundary decides fail fast or fallback.
- **ExecutorChannel, poller, or async adapter:** depending on config, exceptions can be emitted as an **ErrorMessage** to an error channel.
- **Broker consumer:** rollback or NACK can cause broker redelivery. Infinite immediate redelivery while the breaker is OPEN creates a loop of rejected messages.

**An error channel is an error transport path, not a retry policy.** The error channel consumer must classify failures, attempt counts, and the message's next destination. Do not catch every exception and NACK/requeue immediately without limits.

A deferred message contract might look like this:

~~~java
public record DeferredCommand(
        String commandId,
        String correlationId,
        String tenantId,
        String idempotencyKey,
        int attemptCount,
        Instant firstFailureAt,
        Instant nextAttemptAt,
        Instant expiresAt,
        byte[] payload
) {}
~~~

This is an application-defined record, not a default Spring Integration type. Avoid storing or logging sensitive payloads outside data protection policies.

| Error type | Handling |
| --- | --- |
| **BREAKER_REJECTED** | Fail fast or scheduled defer; do not retry immediately |
| **UPSTREAM_TIMEOUT** | Bounded retry if safe; defer/DLQ once budget exhausted |
| **VALIDATION_ERROR** | Terminate, do not retry |
| **BUSINESS_REJECTED** | Return business result, do not retry transport |
| **EXPIRED_COMMAND** | Terminal failure, do not replay |
| **UNKNOWN_WRITE_RESULT** | Reconcile before retrying the write command |

**Broker delivery count is not equal to HTTP attempt count** if a Retry advice also lives inside the handler. To bound total effort, measure layers separately and align retry budgets per business request.

## 10. Splitter, Aggregator, and correlation

An order may be divided by a Splitter into **stock**, **pricing**, and **shipping** branches. If the stock breaker is OPEN, the inventory branch should return an **UNAVAILABLE** outcome or resolve via an error flow rather than endlessly retrying and leaving the Aggregator short of replies.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Splitter]
    B --> C[Stock breaker OPEN]
    B --> D[Pricing service]
    B --> E[Shipping service]
    C --> F[UNAVAILABLE outcome]
    D --> G[Aggregator]
    E --> G
    F --> G
~~~

If one branch fails to return a result, configure **group timeout**, expiration, partial results, or a discard/error path. Preserve **correlation ID** and sequence headers when routing to fallback or defer. Never let an Aggregator group wait indefinitely simply because a message is stuck in retry or broker redelivery.

The Router still picks branches by business meaning, the Filter validates input data, and the Transformer converts payloads. A Transformer error has no business turning into a Stock API request timeout; accurate classification prevents retrying dependency calls due to application bugs.

## 11. Write commands require idempotency—never retry just because no response arrived

With read operations, retries are generally easier to control. With **create-order, reserve-stock, or payment** commands, a timeout only tells the caller **no response was received**, not that upstream failed to process the command.

Example: Stock API already reserved 5 units, but the response was lost. The client times out and retries with a new command. Without duplicate protection, Stock API might reserve another 5 units even though the user only ordered once.

When retrying or replaying write commands, require:

1. A stable **idempotency key** scoped by business command and tenant.
2. Upstream returning the prior result for an already-processed key or guaranteeing no duplicate execution.
3. **Reconciliation** for states where completion is unknown.
4. Deadlines, max attempts, and terminal failure states.
5. An investigation/remediation path on failure, avoiding retrying side-effecting commands forever.

A circuit breaker protects new call volume; it **does not provide exactly-once processing**. Never use Retry and breakers as substitutes for idempotency.

## 12. Testing: OPEN skips client and Retry tries only once

To prove the policy works, measure at least two counters:

- **Remote calls:** total dependency executions.
- **Entries into breaker:** how many times Retry tried passing through the breaker.

The JUnit 5 example below demonstrates that once the circuit is OPEN, a new request is rejected, **the client is not called again**, and Retry **does not retry** the rejection exception despite `maxAttempts` being 5. Imports are omitted.

~~~java
@Test
void openBreakerIsNotRetried() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(100.0f)
            .waitDurationInOpenState(Duration.ofMinutes(1))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger remoteCalls = new AtomicInteger();

    Supplier<String> failingClient = () -> {
        remoteCalls.incrementAndGet();
        throw new StockTransportException(
                "timeout", new java.net.SocketTimeoutException()
        );
    };

    // Two real calls fail to open the circuit.
    assertThrows(
            StockTransportException.class,
            () -> breaker.executeSupplier(failingClient)
    );
    assertThrows(
            StockTransportException.class,
            () -> breaker.executeSupplier(failingClient)
    );

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertEquals(2, remoteCalls.get());

    RetryConfig retryConfig = RetryConfig.custom()
            .maxAttempts(5)
            .waitDuration(Duration.ofMillis(10))
            .retryExceptions(StockTransportException.class)
            .ignoreExceptions(CallNotPermittedException.class)
            .build();

    Retry retry = Retry.of("stock-test-retry", retryConfig);
    AtomicInteger entries = new AtomicInteger();

    Supplier<String> breakerProtected = () -> {
        entries.incrementAndGet();
        return breaker.executeSupplier(failingClient);
    };
    Supplier<String> outerRetry =
            Retry.decorateSupplier(retry, breakerProtected);

    assertThrows(CallNotPermittedException.class, outerRetry::get);
    assertEquals(2, remoteCalls.get());  // No new client call.
    assertEquals(1, entries.get());      // No retry on OPEN error.
}
~~~

This test does not test real HTTP client timeouts. To verify the adapter, add an integration test with a slow/connection-closing mock server and check exception mapping. Spring Integration retry advice tests should run through the real Gateway and handler, since advice order can alter results.

### Recommended test matrix

| Scenario | Expected outcome |
| --- | --- |
| CLOSED, upstream succeeds | One attempt, returns expected reply |
| CLOSED, timeout then success | Bounded retry, remote calls within budget |
| CLOSED, all attempts fail | Returns final error, breaker records per advice order |
| OPEN before request arrives | Client not called, not-permitted not retried |
| Circuit OPENS mid-retry | Retry stops upon receiving rejection |
| HALF_OPEN permits exhausted | Does not continuously retry fighting for permits |
| Breaker outside Retry, HALF_OPEN probe | Total network attempts per probe bounded |
| Validation rejected by Filter | Dependency not called, no retry |
| HTTP 429 with Retry-After | Deferred/throttled per policy, no retry storm |
| Broker redelivery while OPEN | Delay/TTL/DLQ applied, no infinite immediate NACK loop |
| Deferred message exhausts budget | Terminal failure, not replayed endlessly |
| Splitter with an OPEN branch | Aggregator gets outcome/timeout and correlation |
| Write command loses response | Replay has idempotency, no duplicate side effects |
| Multiple instances/pods | Do not assume breaker state is synchronized |

In these tests, distinguish **logical request count**, **retry attempt count**, **remote call count**, and **message delivery count**. Asserting only the final exception is insufficient to tell whether a retry loop ran behind the scenes.

## 13. Monitoring to detect retry loops

An OPEN breaker can cause upstream HTTP error metrics to **drop**, simply because requests are blocked before the client. Therefore, monitor Retry and message flows as well.

| Signal | What to detect |
| --- | --- |
| Breaker state / state transitions | How long is circuit OPEN, is it flapping OPEN/HALF_OPEN? |
| Not-permitted / rejected calls | Volume of requests rejected at the breaker |
| Retry attempts per request | Are any requests being retried too many times? |
| Retry attempts due to breaker rejection | Is the policy mistakenly retrying OPEN errors? |
| Remote client call count | Is traffic to actual upstream actually decreasing? |
| Gateway latency and timeout rate | Are retries pushing past deadlines? |
| Deferred queue depth / oldest age | Are messages piling up? |
| Dead-letter volume | Are many tasks exhausting TTL/attempt budgets? |
| Fallback rate and cache age | Are dependency errors being hidden with overly stale data? |
| Aggregator pending / expired groups | Are branches hanging waiting for missing replies? |
| Correlation ID / idempotency key in traces/logs | Can requests be traced and duplicates prevented? |

Tag metrics with moderate-cardinality labels like **breaker name**, **operation**, and **outcome**; keep correlation IDs and specific tenant IDs in access-controlled logs/traces.

Common warning signs:

- **Rejected calls rising alongside retry attempts/request:** circuit rejections are being retried.
- **Remote calls low while queues grow endlessly:** enforce intake limits, defer schedules, and DLQ.
- **Continuous OPEN → HALF_OPEN → OPEN:** upstream has not recovered or probes/retries generate excessive load.
- **Breaker stays CLOSED despite frequent timeouts:** exceptions are caught before the breaker, or Retry masks outcomes.
- **Gateway times out while backend still executes:** risk of duplicates from caller/broker retries.

## 14. Spring Integration checklist

- [ ] Circuit breaker wraps the dependency call closely and client has real timeouts.
- [ ] Retry policy selects only recoverable transient errors, **never retrying breaker rejections**.
- [ ] Configure `maxAttempts`, backoff/jitter, and an overall deadline per request.
- [ ] Understand Retry/Breaker ordering and verify with call counters.
- [ ] HALF_OPEN limits both permits and physical attempts per probe.
- [ ] Fallback distinguishes **FRESH / STALE_REFERENCE / UNAVAILABLE**, never returning fake results.
- [ ] If deferring work, use durable outbox/queue, `nextAttemptAt`, `attemptCount`, TTL, and DLQ.
- [ ] Never use infinite immediate NACK/requeue on broker redelivery while OPEN.
- [ ] Write commands carry an idempotency key and reconciliation procedure for unknown responses.
- [ ] Router, Filter, Transformer, and error channel classify errors by responsibility domain.
- [ ] Splitter/Aggregator preserve correlation and have partial results or group timeouts.
- [ ] Test both breaker entry count and client call count during OPEN/HALF_OPEN.
- [ ] Measure retry attempts, rejected calls, queue age, fallback rate, and Gateway latency.

**Never retrying endlessly when the circuit is open** allows the breaker to genuinely shed load instead of shifting congestion from the HTTP client into Retry, Gateway, or the broker. In Spring Integration, stopping immediately on rejection errors, enforcing deadlines on transient failures, and bounding deferred work keeps EIP flows testable, observable, and able to recover smoothly.
