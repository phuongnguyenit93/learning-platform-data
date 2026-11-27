# How timeouts and errors increment the failure count

## 1. Why must you understand the exact failure count?

In the **SPRING_INTEGRATION_PATTERN** module, Spring Integration connects Enterprise Integration Patterns (EIP) into a flow: a Gateway receives calls, a Filter checks messages, a Transformer normalizes payloads, a Router selects branches, and a Service Activator calls external systems. Communicating through channels reduces coupling between components, yet a slow or frequently failing inventory API can still tie up threads, grow queues, and stretch Gateway response times.

A **circuit breaker** addresses part of this problem by observing dependency call outcomes. When failure count or failure rate reaches a threshold, the breaker transitions from **CLOSED** to **OPEN**, preventing new calls from reaching the dependency. After a wait period, **HALF_OPEN** allows probing to determine whether recovery is possible.

To protect the flow properly, answer four questions:

1. Does the timeout actually occur **inside the region observed by the circuit breaker**?
2. Which exceptions or HTTP responses count as dependency failures?
3. Is the **failure count** a count of **consecutive** failures or failures **within a statistical window**?
4. Do retries, fallbacks, and Gateway error handling alter the number of outcomes observed by the breaker?

A misrecorded timeout can leave the breaker CLOSED while the API is hanging. Conversely, counting input data errors can open the circuit even when the dependency is completely healthy.

## 2. Path of a call and where failures are recorded

~~~mermaid
flowchart TD
    A[Gateway receives message] --> B[Filter / Validate]
    B -->|Valid| C[Transformer]
    B -->|Invalid| V[Return validation error]
    C --> D{Router}
    D -->|Stock branch| E[Circuit breaker]
    D -->|Pricing branch| P[Separate breaker for Pricing]
    E -->|Permitted| F[Service Activator]
    F --> G[HTTP client with timeout]
    G -->|Valid response| H[Handler succeeds]
    G -->|Timeout / dependency error| I[Handler throws exception]
    H --> J[Breaker records success]
    I --> K[Breaker records failure]
    E -->|OPEN| L[Fast reject]
    K --> M{Threshold reached?}
    M -->|Yes| N[OPEN]
    M -->|No| O[Keep CLOSED]
    J --> Q[Reply / Aggregator]
    L --> R[Error / fallback boundary]
    R --> Q
~~~

In the diagram, only errors **thrown out of the execution wrapped by the breaker** have a chance to count as breaker failures. Filter errors happen before the breaker; a Gateway timeout waiting for a reply may occur at an outer layer and is **not automatically** recorded as a dependency failure. Likewise, a call rejected while OPEN is not the same as a failed dependency invocation.

| Where it occurs | Does the breaker protecting StockClient see it? |
| --- | --- |
| StockClient throws an exception and it exits the handler | **Yes**, per the exception recording policy |
| StockClient returns HTTP 503 but the handler treats it as a successful response | **Not necessarily**; must convert to an error or configure outcome evaluation |
| Gateway waiting for reply expires while an async worker is still running | **Not automatically**; a timeout at the Gateway boundary may lie outside the handler |
| Validator rejects negative quantity before the breaker | **No**, and that is the desired behavior |
| Transformer after the handler throws a NullPointerException | **Should not** be counted as a Stock API failure |
| Breaker is OPEN and rejects a new request | Recorded as a not-permitted request; **not** a failed client call |
| Handler catches the exception and returns a "success" object | The breaker may record **success**, even though upstream actually failed |

To observe accurately, place the breaker **right around the dependency call operation**. Do not use one breaker wrapping Router, Filter, Transformer, and Aggregator together.

## 3. Which timeouts increment the failure count?

"Timeout" is an umbrella term for many time limits at different layers. You need to know which layer reports the timeout and how it reports it.

| Timeout type | What does it limit? | Relation to failure count |
| --- | --- | --- |
| **Connect timeout** | Time to establish a connection to upstream | If the client throws out of the handler, the breaker can count a failure |
| **Read / response timeout** | Time waiting for data or response per HTTP client semantics | Exceptions passing through the breaker can count as failures |
| **Request deadline** | Overall execution deadline for a call, if supported by the client | Must ensure the timeout actually completes the call with an error |
| **Gateway reply timeout** | Time the Gateway waits for a reply message | May occur only at the Gateway, outside the breaker-protected zone |
| **Poller / queue receive timeout** | Time waiting for a message to become available for processing | Does not by itself prove an external dependency failed |
| **Breaker open wait duration** | Time staying OPEN before a HALF_OPEN probe opportunity | **Not a timeout** of a network request |
| **Slow-call duration threshold** | Threshold marking a call as slow for statistics | Slowness can increase **slow-call count**, not necessarily **failure count** |

**Example:** the Gateway has a 1-second reply timeout, while the Stock HTTP client allows waiting 10 seconds. If the request runs on an asynchronous worker, the caller may time out after 1 second while the client is still waiting; the breaker wrapping the handler has not yet seen an exception. Thus, a Gateway timeout does not replace a client timeout.

Conversely, if StockClient proactively throws an exception upon exceeding an 800 ms deadline, and that exception exits the handler observed by the breaker, the breaker can record a failure. In a synchronous flow, the Gateway can receive that exception; in an asynchronous flow, the error can flow through the ErrorMessage/error channel mechanism depending on the endpoint and channel.

### 3.1. Per-request timeout differs from OPEN wait duration

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant B as Breaker CLOSED
    participant C as HTTP Client
    participant S as Stock API
    G->>B: Message 1
    B->>C: Call permitted
    C->>S: Send request
    Note over C: Client deadline 800 ms
    S--xC: Fails to respond in time
    C--xB: Timeout exception
    Note over B: Record one failure
    B--xG: Propagate error / fallback
    Note over B: Transition to OPEN when threshold reached
~~~

The breaker only records an outcome when the protected call completes or errors. If the client has no timeout and a call hangs indefinitely, **no completed failure event** occurs to increment the counter in the usual way. You need client timeouts and, under high concurrency, concurrency limits/bulkheads as well.

**A slow-call threshold does not cancel a slow call.** A library can record a successful-but-too-slow call once it eventually finishes. To stop waiting, configure timeouts/deadlines at the execution layer or use an appropriate time limiter.

## 4. Mapping errors before feeding them to the breaker

Not every exception should be treated as an infrastructure failure.

| Situation | Example | Recommended policy |
| --- | --- | --- |
| Connection error | Connection refused, reset, DNS failure | Usually record failure |
| Upstream timeout | Connect timeout, read timeout | Usually record failure |
| Server-side error | HTTP 500/502/503/504 | Usually record failure after mapping response to an error |
| Upstream rate limit | HTTP 429 | Consider recording failure, combined with backoff/rate limiting |
| Malformed request | Empty SKU, negative quantity | Validate before the breaker, do not count as dependency failure |
| Product not found | HTTP 404 as a valid business outcome | Return "not found" outcome instead of an exception |
| Business conflict | HTTP 409 per domain contract | Handle separately, do not default to dependency failure |
| Programming bug | NullPointerException in Transformer | Fix the bug; do not let it affect the dependency breaker |
| Call blocked by breaker | Not-permitted / circuit OPEN | Record rejection count separately, do not treat as a client execution outcome |

Classification depends on the contract: the same HTTP 404 could mean "item does not exist" in an inventory API or "endpoint does not exist" due to misconfiguration. Base decisions on actual semantics, not status code alone.

### 4.1. Do not swallow exceptions inside the protected section

~~~java
// Wrong: the breaker only sees a normal return value.
StockResult lookup(StockQuery request) {
    try {
        return stockClient.lookup(request);
    } catch (Exception ex) {
        return new StockResult(request.sku(), false);
    }
}
~~~

This approach both hides errors from the failure count and confuses "unable to check inventory" with "checked and out of stock".

Instead, let the dependency throw a **classified exception** out of the breaker-protected section, then handle fallback at the outer boundary. A fallback outcome should distinguish **FRESH**, **STALE_REFERENCE**, and **UNAVAILABLE**, with correlation ID and reason so downstream never misinterprets it.

## 5. Spring Integration: counting consecutive handler failures

Spring Integration provides **RequestHandlerCircuitBreakerAdvice**. This advice attaches to an endpoint handler, tracks handler executions, and uses a **consecutive failure threshold** to transition to OPEN.

Suppose the threshold is **3**:

| Request | Handler execution outcome | Consecutive failures after request | State after request |
| --- | --- | ---: | --- |
| A | Timeout exception | 1 | CLOSED |
| B | Timeout exception | 2 | CLOSED |
| C | Success | 0 | CLOSED |
| D | HTTP 503 converted to exception | 1 | CLOSED |
| E | Connect timeout exception | 2 | CLOSED |
| F | Read timeout exception | 3 | **OPEN** |
| G | Arrives while OPEN, client not called | Does not add another dependency call | **OPEN** |

Request F **entered the client**, failed, and thereby caused the circuit to open. Request G is the first request in the table to be rejected early.

### 5.1. Advice configuration example

The following Java snippets assume Spring Integration Java DSL and corresponding component scanning are declared; common imports are omitted.

~~~java
public record StockQuery(String sku) {}

public record StockResult(String sku, boolean available) {}

public interface StockClient {
    StockResult lookup(StockQuery query);
}

@MessagingGateway(defaultRequestChannel = "stock.lookup.requests")
public interface StockGateway {
    StockResult lookup(StockQuery query);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockIntegrationConfig {

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
            StockClient client,
            RequestHandlerCircuitBreakerAdvice stockBreakerAdvice
    ) {
        return IntegrationFlow.from("stock.lookup.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> client.lookup(query),
                        endpoint -> endpoint.advice(stockBreakerAdvice)
                )
                .get();
    }
}
~~~

When StockClient throws an exception out of the handler, the advice can record a failure. Once the circuit is OPEN, the handler stops calling StockClient for rejected requests. **halfOpenAfter** controls the wait duration before a probe opportunity, not the HTTP request timeout.

An advice instance holds its own state. Do not share one instance across independent dependencies if you want Stock API outages not to trip Pricing API. In a multi-pod system, each instance typically keeps its own breaker state; do not assume automatic cluster synchronization.

### 5.2. How can timeouts produce exceptions?

The example below uses JDK's **java.net.http.HttpClient**. Assume the test endpoint returns plain text **true** or **false** for status 200, returns 404 when the SKU does not exist, and treats other statuses as integration failures in the example. A real API may return JSON and require parsing per its contract.

~~~java
public class StockDependencyException extends RuntimeException {
    public StockDependencyException(String message) {
        super(message);
    }

    public StockDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class HttpStockClient implements StockClient {

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(500))
            .build();

    private final String baseUrl;

    public HttpStockClient(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    @Override
    public StockResult lookup(StockQuery query) {
        String sku = URLEncoder.encode(
                query.sku(), StandardCharsets.UTF_8);

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create(baseUrl + "/stock?sku=" + sku))
                .timeout(Duration.ofSeconds(2))
                .GET()
                .build();

        try {
            HttpResponse<String> response = http.send(
                    request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 404) {
                return new StockResult(query.sku(), false);
            }

            if (response.statusCode() != 200) {
                throw new StockDependencyException(
                        "Unexpected Stock API status: "
                                + response.statusCode());
            }

            String body = response.body().trim();
            if (!body.equals("true") && !body.equals("false")) {
                throw new StockDependencyException(
                        "Invalid Stock API response body");
            }

            return new StockResult(
                    query.sku(), Boolean.parseBoolean(body));
        } catch (HttpTimeoutException timeout) {
            throw new StockDependencyException(
                    "Stock API timed out", timeout);
        } catch (IOException ioFailure) {
            throw new StockDependencyException(
                    "Stock API I/O failure", ioFailure);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new StockDependencyException(
                    "Stock API call interrupted", interrupted);
        }
    }
}
~~~

In JDK HttpClient, connect timeout bounds connection establishment, while timeout on **HttpRequest** bounds the duration allotted to the request. **HttpTimeoutException** is a subclass of IOException; catch it separately before IOException to distinguish timeout causes. Catching **InterruptedException** and restoring the interrupt flag preserves thread cancellation signals.

This example illustrates the exception propagation path: **handler calls StockClient → StockClient throws StockDependencyException → advice observes the failure**. Do not use it as a complete production HTTP adapter; you still need authentication handling, tracing, dedicated policies for 429/4xx, retries, and JSON payload handling per your actual contract.

**Thread-flow note:** if an outer layer cancels the request or times out before HttpClient finishes, whether the breaker records a failure depends on whether the protected operation actually completes with an exception. You cannot simply configure a Gateway timeout and assume the failure count will increment.

## 6. Resilience4j: failed calls in a sliding window

Resilience4j provides a CircuitBreaker based on **failure rate** and can also open on **slow-call rate**. Unlike the native advice's consecutive failure counter, Resilience4j stores outcomes in a statistical window.

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
        CircuitBreaker.of("stock-api", config);

StockResult result = stockBreaker.executeSupplier(
        () -> stockClient.lookup(query)
);
~~~

In this example:

- **slidingWindowSize(10)**: tracks up to the 10 most recent calls in CLOSED.
- **minimumNumberOfCalls(5)**: requires enough samples before failure rate is used to decide opening.
- **failureRateThreshold(50.0f)**: once enough samples are collected and failure rate reaches the threshold, the breaker can OPEN.
- **waitDurationInOpenState(15 seconds)**: wait time before a probe opportunity, not an HttpClient deadline.
- **permittedNumberOfCallsInHalfOpenState(2)**: limits trial calls in HALF_OPEN.

Formula:

\[
\text{Failure rate} =
\frac{\text{Calls recorded as failed in window}}
{\text{Total calls recorded in window}}
\times 100\%.
\]

| Outcomes in window | Failed outcomes | Failure rate | Eligible to open? |
| ---: | ---: | ---: | --- |
| 4 | 4 | 100% | **Not yet**, below minimumNumberOfCalls |
| 5 | 2 | 40% | Below 50% |
| 6 | 3 | 50% | **Yes**, if breaker is still CLOSED |
| 10 | 4 | 40% | Below 50% |
| 10 | 7 | 70% | **Yes**, if breaker is still CLOSED |

These rows are **independent scenarios**, not a continuous timeline of a single breaker after it has already opened.

### 6.1. Failed calls differ from not-permitted calls

When the breaker is OPEN, Resilience4j can throw **CallNotPermittedException** instead of executing the supplier. This call is tracked as **not permitted / rejected**, not as a StockClient invocation that executed and failed inside the CLOSED window.

Therefore, monitor **both signals**: failed calls indicate outcomes of permitted calls, while not-permitted calls indicate how much traffic the breaker is protecting via rejection.

If you merely count exceptions caught at the Gateway without classifying them, you can accidentally add **CallNotPermittedException** into "new Stock API errors", even though the API never received those requests.

### 6.2. Slow does not necessarily mean failed

Resilience4j can add an open policy based on slow calls:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .slowCallDurationThreshold(Duration.ofMillis(800))
        .slowCallRateThreshold(60.0f)
        .failureRateThreshold(50.0f)
        .build();
~~~

A call taking 1,200 ms yet returning a valid result can be a **successful slow call**. It contributes to slow-call statistics, without automatically becoming a **failed call**. A call timing out after 2 seconds can be both **slow** and **failed**, depending on configuration and recorded outcome.

Do not add failure rate and slow-call rate together to decide OPEN. The two conditions are evaluated separately by the implementation.

## 7. Specifying recorded and ignored exceptions

With Resilience4j, you can configure which exception types count as failures or should be ignored during evaluation.

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .recordExceptions(
                StockDependencyException.class,
                java.net.SocketTimeoutException.class
        )
        .ignoreExceptions(BusinessValidationException.class)
        .build();
~~~

**BusinessValidationException** here is an application-defined exception type. This is a policy example, not an exhaustive list of errors for every HTTP client.

Read the library's semantics carefully when using **recordExceptions**: exceptions not in the recorded list may be treated statistically as successful calls unless configured as ignored. This can skew the failure rate if a network error is wrapped in an exception type outside your chosen list.

If you need more flexibility, use **recordException** or **ignoreException** predicates per your application contract. Prefer mapping HTTP client exceptions to one or a few **StockDependencyException** types in the adapter, so the breaker policy does not depend on every transport-library exception type.

**Do not mask application bugs with blanket fallbacks.** For example, a NullPointerException caused by a bug in a Transformer should not be converted into a StockDependencyException just to route all errors through one handler. That miscounts breaker failures and makes diagnosis harder.

## 8. Retries can multiply attempts and alter failure count

Suppose a business request can be retried up to 3 times. Advice ordering determines whether the breaker observes **one logical request** or **individual physical attempts**.

### 8.1. Breaker wrapping retry

~~~mermaid
flowchart LR
    G[Gateway] --> B[Breaker]
    B --> R[Retry up to 3 times]
    R --> C[StockClient]
~~~

If all three attempts time out, the outer breaker may observe only **one final failed execution**. If the third attempt succeeds, the breaker may see only one successful outcome for that request.

### 8.2. Retry wrapping breaker

~~~mermaid
flowchart LR
    G[Gateway] --> R[Retry up to 3 times]
    R --> B[Breaker]
    B --> C[StockClient]
~~~

In this order, each attempt can contribute to the failure counter. With a threshold of 3 consecutive failures, a single business request can trip the circuit to OPEN after three attempts. Attempts after OPEN only receive rejection errors; **never blindly retry not-permitted errors from the breaker**.

| Criterion | Breaker outside retry | Retry outside breaker |
| --- | --- | --- |
| Unit typically seen by breaker | Final outcome of one logical request | Each attempt passing through breaker |
| One request failing all 3 attempts | Can contribute 1 failure | Can contribute 3 failures |
| Final attempt succeeds | Can be recorded as success | May have already recorded prior failed attempts |
| Effect on opening speed | Can open more slowly by request count | Can open faster by attempt count |
| What must be controlled | Bounded retries, overall deadline | Do not retry not-permitted calls and avoid amplifying traffic |

Neither order fits every system. Choose based on the unit you want to measure and your protection goals, then test the actual advice ordering.

When retrying write operations such as deducting inventory or creating orders, a timeout does not prove the receiver never processed the request. Require an **idempotency key** and duplicate-handling safeguards before enabling retries or message replay.

## 9. Gateway, error channel, and correlation can obscure root causes

### 9.1. Synchronous and asynchronous errors

With a synchronous Gateway over **DirectChannel**, exceptions from handlers/advice can propagate straight back to the caller. In flows with **ExecutorChannel**, pollers, or asynchronous adapters, exceptions can be packaged into an **ErrorMessage** via the corresponding error channel mechanism. Declaring an error channel does not mean all synchronous errors automatically shift into an error flow.

**Breaker placement** must follow the actual dependency call. For example, a Gateway timeout from waiting on an Aggregator to gather three branches does not prove Stock API timed out. Incrementing Stock API's failure count just because the Gateway timed out waiting for the Aggregator would trip the wrong dependency's circuit.

### 9.2. Splitter and Aggregator

A Splitter can generate multiple sub-messages, each calling a dependency. If one branch is blocked by the breaker or times out, the Aggregator may not receive all replies. You must:

- Preserve **correlation ID**, sequence headers, and branch identifier across success, error, and fallback outcomes.
- Define **group timeout**, partial results, expired-group handling, and a clear discard/error path.
- Avoid leaving an Aggregator group waiting indefinitely when one branch's circuit is OPEN.
- Do not count an Aggregator timeout as a client failure without evidence that the client call itself failed.

### 9.3. Router and Filter

The Router helps isolate Stock, Pricing, and Shipping branches; each failure domain should have its own breaker. Filter and Validator must reject invalid data **before** the dependency call site. Transformers converting payloads should sit outside the failure-counting scope of a breaker dedicated to an external API, unless the transformation itself is intentionally part of the dependency call.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Filter]
    B --> C[Transformer]
    C --> D{Router}
    D --> E[Stock breaker]
    D --> F[Pricing breaker]
    E --> G[Stock service]
    F --> H[Pricing service]
~~~

## 10. Testing: proving failure count increments at the right time

Testing only that the Gateway throws an exception is not enough. A Circuit Breaker test must verify **actual dependency invocation counts** before and after OPEN.

### 10.1. JUnit 5 example with Resilience4j

The test below demonstrates that 4 failures open the circuit, and the fifth call **never enters the client**:

~~~java
@Test
void timeoutsOpenBreakerAndRejectNextCall() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50.0f)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger remoteCalls = new AtomicInteger();

    Supplier<StockResult> failingClient = () -> {
        remoteCalls.incrementAndGet();
        throw new StockDependencyException(
                "request timed out",
                new java.net.SocketTimeoutException());
    };

    for (int i = 0; i < 4; i++) {
        assertThrows(
                StockDependencyException.class,
                () -> breaker.executeSupplier(failingClient)
        );
    }

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertEquals(4, remoteCalls.get());

    assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(failingClient)
    );
    assertEquals(4, remoteCalls.get());
}
~~~

This test uses a simulated timeout exception without making real network calls. The first four calls are permitted to execute and fail; the subsequent call is immediately rejected by the breaker. When testing the HTTP client's own timeout behavior, add an integration test with a slow mock server or active connection closure to verify the adapter actually throws the expected exception.

### 10.2. Flow test matrix

| Scenario | Expected outcome |
| --- | --- |
| Native advice: consecutive failures below threshold | CLOSED, handler continues to be invoked |
| Native advice: one success amidst failure streak | Consecutive failure counter resets |
| Native advice: threshold reached | Call that reached threshold entered client; subsequent call is blocked |
| Resilience4j: 4/4 failures, minimum calls = 5 | Not OPEN yet due to insufficient sample count |
| Resilience4j: failure rate reaches 50% with enough samples | OPEN |
| HTTP 503 returned as normal data | Breaker does not increment failures without an error-recording step |
| HTTP 503 mapped to exception by adapter | Breaker records failure |
| Validation rejected by Filter | Client not called, dependency failures not incremented |
| Gateway times out while client is still running | Not assumed to be a client failure |
| Client timeout actually throws exception | Failure recorded per policy |
| Breaker OPEN | New requests rejected, **remote call counter does not increase** |
| Retry before/after breaker | Recorded count matches logical call vs. attempt unit |
| Fallback outside breaker | Still records failure metric and returns degraded outcome |
| Splitter/Aggregator with a timed-out branch | Preserves correlation, completes group per policy, does not hang |

Time-dependent tests should use an appropriate clock/test configuration or short test-specific timeouts. Avoid long sleep loops to test OPEN thresholds; tests become slow, scheduler-dependent, and hard to reproduce.

## 11. Observing failure counts and spotting misconfigurations

Monitor at least the following signals by **dependency** and **breaker name**:

| Signal | Question to answer |
| --- | --- |
| Breaker CLOSED / OPEN / HALF_OPEN | Where is the circuit in its lifecycle? |
| Failure count or failure rate | Have enough failures been observed to open the circuit? |
| Successful calls | Are successes breaking up failure streaks? |
| Not-permitted / rejected calls | How many requests are short-circuited while OPEN? |
| Timeout type and exception class | Did the timeout occur in HTTP client, Gateway, or Aggregator? |
| Slow calls, p95/p99 latency | Is the dependency merely slow or genuinely failing? |
| Retry attempts per logical request | Are retries amplifying attempts and affecting failure counts? |
| Gateway error/latency, channel queue depth | Is the breaker relieving flow congestion? |
| Correlation ID and error channel outcome | Which branch failed and what was the original message? |

Resilience4j can emit circuit breaker events and integrate with **Micrometer** to measure state, permitted outcomes, rejected calls, and state transitions. With native advice, check what instrumentation exists in your Spring Integration version; when needed, add metrics at the handler, client, and Gateway to distinguish timeouts by layer.

Common symptoms:

- **Breaker stays CLOSED even though HTTP client repeatedly times out:** exceptions may be caught, timeouts may happen at the Gateway outside the advice, retries may mask outcomes, or threshold/minimum calls may not be reached.
- **Breaker OPENS even though dependency is healthy:** you may be counting validation errors, Transformer exceptions, or overly short timeouts.
- **Few failed calls yet Gateway reports many errors:** many requests may be rejected while OPEN, or the Gateway may be timing out due to queues/Aggregator.
- **Repeatedly cycling OPEN → HALF_OPEN → OPEN:** the dependency has not recovered stably, or wait duration and probe policy are misconfigured.

## 12. Design and verification checklist

- [ ] Breaker tightly wraps the dependency call site, not accidentally wrapping the entire message flow.
- [ ] Client has connect timeout, request/response timeout, or deadline per SLA.
- [ ] Timeouts complete the handler with an exception or signal recognized by the breaker.
- [ ] HTTP statuses, infrastructure exceptions, and business errors are classified; validation errors are handled before the breaker.
- [ ] Understand that native advice counts **consecutive** failures, whereas Resilience4j can compute **failure rate in a sliding window**.
- [ ] Minimum calls, failure threshold, slow-call threshold, and wait duration match real traffic.
- [ ] Do not confuse **not permitted** calls with failed dependency calls.
- [ ] Know whether retry sits before or after the breaker and what attempt count is actually measured.
- [ ] Fallback does not swallow errors before the breaker records them; degraded outcomes have clear status.
- [ ] Gateway, error channel, Router, Splitter, and Aggregator preserve correlation and error paths.
- [ ] Test client call counts in CLOSED/OPEN, test exception mapping, and test Gateway timeout scenarios.
- [ ] Metrics distinguish dependency timeouts, upstream errors, denied calls, slow calls, and business errors.

**Timeouts and errors only increment the failure count when they are observed by the breaker and treated as failures by the recording policy.** In Spring Integration, properly designing handler boundaries, timeouts, retries, and fallbacks ensures circuits open promptly when a dependency breaks while avoiding false trips on healthy processing branches.
