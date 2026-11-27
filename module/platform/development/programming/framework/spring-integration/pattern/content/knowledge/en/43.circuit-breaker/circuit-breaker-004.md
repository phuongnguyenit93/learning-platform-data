# Fallback when the circuit is open

## 1. The problem: the circuit breaks cleanly, yet the business still needs a response

In an application using **Spring Integration** to implement Enterprise Integration Patterns (EIP), a request may flow from a **Gateway** through a **Filter**, **Transformer**, **Router**, and on to a **Service Activator** calling an external API. Organizing flows this way decouples steps via message channels and makes them easy to extend. However, when a dependency such as the inventory service goes down, simply placing a circuit breaker to block calls is not enough: the caller still needs to know **how its request will be handled**.

A circuit breaker has three fundamental states:

- **CLOSED:** allows calls to the dependency and observes outcomes.
- **OPEN:** fast-rejects new calls to the dependency.
- **HALF_OPEN:** allows a number of probe calls according to the implementation's policy; requests not granted a permit may still be rejected.

**Fallback** is the handling strategy defined for situations where a dependency result is unavailable. A fallback may return marked cached data, a clear error notification, a reliable alternative data source, or route the request to a deferred-processing queue. The breaker **does not create a fallback on its own**; the Spring Integration flow or application layer must explicitly decide what is business-safe.

This lesson focuses on **fallback when the circuit is OPEN**, while also showing how to handle real failures when the dependency fails in CLOSED/HALF_OPEN, how to preserve correlation across branches, and how to test that the fallback never hides failure signals the breaker needs to record.

## 2. Where does fallback sit in the message flow?

~~~mermaid
flowchart TD
    A[Gateway receives request] --> B[Filter / Transformer]
    B --> C{Router}
    C -->|Stock needed| D[Stock circuit breaker]
    C -->|Other branch| S[Independent dependency]
    D -->|Call permitted| E[Stock API]
    D -->|Rejected| F[Fallback policy]
    E -->|Success| G[Fresh stock result]
    E -->|Recorded failure| F
    F -->|Eligible cache| H[STALE_REFERENCE]
    F -->|No safe data| I[UNAVAILABLE / Fail fast]
    F -->|Deferrable work| J[Queue / process later]
    G --> K[Gateway reply / Aggregator]
    H --> K
    I --> K
    S --> K
~~~

The diagram illustrates a **design where policy is chosen by business requirement**. A given request typically applies one policy: return cached data, fail fast, or defer the work. Never default to both returning success and writing an ambiguous command into a queue.

**Processing order is decisive:**

1. Filter/Validator rejects invalid requests before calling the dependency.
2. The circuit breaker wraps **the operation that actually calls the dependency**, so it sees the exceptions or error outcomes it needs to measure.
3. The fallback policy sits **outside the protected execution** and receives errors/rejection signals after the breaker has had a chance to record statistics.
4. The Gateway or downstream branch receives an explicit outcome contract, such as **FRESH**, **STALE_REFERENCE**, or **UNAVAILABLE**.

If you put the fallback **inside** the call wrapped by the circuit breaker, a timeout error might get caught and converted into a normal object; the breaker sees a success and **never opens the circuit even though the API is failing**. This is a common design mistake.

### Distinguishing two fallback triggers

| Situation | What is happening | Required handling |
| --- | --- | --- |
| Breaker is already OPEN | No new call sent to dependency | Fall back immediately; do not attempt to call again |
| HALF_OPEN with no permit left | Call was not granted a probe permit | Can also fall back immediately |
| Breaker is CLOSED, call times out | Dependency was called and failed | Record failure before falling back |
| HALF_OPEN, probe call fails | Dependency was called, may return to OPEN | Record failure; appropriate fallback |
| Input validation error | Should not call dependency | Return validation error, **do not** use fake cache |
| Programming bug in Transformer | Does not prove dependency is broken | Report application error; do not use fallback to hide bugs |

With **Resilience4j**, **CallNotPermittedException** indicates the call was not permitted to execute due to breaker state, usually OPEN or no remaining permits in HALF_OPEN. Therefore, a reason code named **BREAKER_REJECTED** is more accurate than assuming every rejection happens in OPEN.

## 3. Choosing fallback by business safety level

Not every service can accept stale data or complete work later.

| Option | Suitable for | Risks to control |
| --- | --- | --- |
| **Fail fast** | Payments, authentication, inventory reservation, workflows requiring fresh data | Return errors distinguishing unavailable dependency from invalid input |
| **Read-only cache** | Catalog display, reference info, non-real-time stats | TTL, data capture timestamp, missing-data cases, stale-data label |
| **Graceful feature degradation** | Show product page while hiding buy button when stock is unconfirmed | Never present fake data as a trustworthy result |
| **Queue / defer** | Sending notifications, data sync, deferred report generation | Idempotency, durability, TTL, retry, dead-letter, queue bounds |
| **Alternative source** | Multiple read replicas or backup providers with compatible contracts | Alternative source also needs timeouts, its own circuit, and consistency control |

Example: an **inventory check API** serving two workflows:

- **Product page:** can display reference stock count from cache with a label "updated 1 minute ago".
- **Order confirmation step:** must not rely on cached counts to conclude items are in stock; when the dependency is OPEN, return **unable to confirm** or pause order confirmation.

Same data source, yet **the fallback policy differs** by use case. Design the policy at the business boundary instead of using a default like **available = false** everywhere.

## 4. Designing an unambiguous outcome contract

A straightforward approach is returning an object containing **data source status**, the quantity if available, the timestamp when the data was captured, and a correlation ID.

~~~java
public enum LookupStatus {
    FRESH,           // Fresh result from dependency
    STALE_REFERENCE, // Cached result for reference only
    UNAVAILABLE      // No sufficiently safe data available
}

public record InventoryRequest(
        String sku,
        int requestedQuantity,
        String correlationId
) {}

public record StockSnapshot(
        String sku,
        int availableUnits
) {}

public record CachedSnapshot(
        StockSnapshot snapshot,
        Instant capturedAt
) {}

public record InventoryReply(
        String sku,
        String correlationId,
        LookupStatus status,
        Integer availableUnits,
        Instant sourceTime,
        String reasonCode
) {}
~~~

Conventions to standardize:

- **FRESH:** **availableUnits** holds fresh data from the dependency; **sourceTime** reflects when the result was fetched.
- **STALE_REFERENCE:** data comes from cache; **sourceTime** is when the cache entry was created, not when the current request was processed. Can be displayed for reference, not used as a substitute for inventory confirmation.
- **UNAVAILABLE:** no acceptable data available; **availableUnits** and **sourceTime** may be **null**, rather than setting 0 which misleads users into thinking stock is empty.
- **reasonCode:** machine-readable values such as **BREAKER_REJECTED**, **UPSTREAM_FAILURE**, **CACHE_EXPIRED**, helping UI, logs, and workflows decide how to respond.
- **correlationId:** preserves the request identifier for tracing across Gateway, Router, Splitter, Aggregator, and error paths.

You may add **dataVersion**, **cacheAge**, **retryable**, or **retryAfter** if the contract genuinely needs them. However, avoid turning every failure into an HTTP 200 success lacking a degraded status; HTTP status and business status should be mapped intentionally at the API boundary.

## 5. Java example: fallback outside the circuit breaker

The following example uses **Spring Integration Java DSL** to wire the message flow and **Resilience4j** to protect the Stock API call. Resilience4j is used because rejections in OPEN/HALF_OPEN produce an explicit exception and a sliding window can be defined. With Spring Integration's native **RequestHandlerCircuitBreakerAdvice**, the same principle of placing fallback **outside the advice-protected handler** still applies; specific exception identification must match your API/application version.

### 5.1. Dependency and read-only cache

These interfaces define a clear contract. In a real system, **StockClient** is an HTTP/gRPC adapter with timeouts that maps connection/5xx errors to a dedicated exception. The cache stores only previously verified snapshots.

~~~java
public interface StockClient {
    StockSnapshot fetch(String sku);
}

public interface InventoryCache {
    Optional<CachedSnapshot> find(String sku);
}

public class StockDependencyException extends RuntimeException {
    public StockDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Do not catch every generic **RuntimeException** from the flow and treat it as Stock API unhealthiness. **StockDependencyException** is the error type translated by the adapter from a dependency cause, while programming/validation errors must be handled separately.

### 5.2. Configuring a breaker per dependency

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class InventoryFlowConfig {

    @Bean
    public CircuitBreaker stockBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(15))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreaker.of("stock-api", config);
    }

    @Bean
    public InventoryLookupService inventoryLookupService(
            CircuitBreaker stockBreaker,
            StockClient stockClient,
            InventoryCache inventoryCache
    ) {
        return new InventoryLookupService(
                stockBreaker,
                stockClient,
                inventoryCache,
                Clock.systemUTC(),
                Duration.ofMinutes(2)
        );
    }

    @Bean
    public IntegrationFlow inventoryFlow(
            InventoryLookupService lookupService
    ) {
        return IntegrationFlow.from("inventory.requests")
                .handle(
                        InventoryRequest.class,
                        (request, headers) -> lookupService.lookup(request)
                )
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "inventory.requests")
public interface InventoryGateway {
    InventoryReply lookup(InventoryRequest request);
}
~~~

Java/Spring Integration/Resilience4j imports are omitted for readability. In a real Spring application, declare the dependencies and register the Gateway via **@IntegrationComponentScan** or equivalent configuration.

### 5.3. Execution and fallback handling

~~~java
public class InventoryLookupService {

    private final CircuitBreaker breaker;
    private final StockClient stockClient;
    private final InventoryCache cache;
    private final Clock clock;
    private final Duration maxCacheAge;

    public InventoryLookupService(
            CircuitBreaker breaker,
            StockClient stockClient,
            InventoryCache cache,
            Clock clock,
            Duration maxCacheAge
    ) {
        this.breaker = breaker;
        this.stockClient = stockClient;
        this.cache = cache;
        this.clock = clock;
        this.maxCacheAge = maxCacheAge;
    }

    public InventoryReply lookup(InventoryRequest request) {
        // Only the dependency call sits inside executeSupplier.
        try {
            StockSnapshot fresh = breaker.executeSupplier(
                    () -> stockClient.fetch(request.sku())
            );

            return new InventoryReply(
                    request.sku(),
                    request.correlationId(),
                    LookupStatus.FRESH,
                    fresh.availableUnits(),
                    clock.instant(),
                    "OK"
            );
        } catch (CallNotPermittedException rejected) {
            // OPEN or HALF_OPEN with no permit granted.
            return fallback(request, "BREAKER_REJECTED");
        } catch (StockDependencyException dependencyError) {
            // Breaker already observed the exception before entering catch.
            return fallback(request, "UPSTREAM_FAILURE");
        }
    }

    private InventoryReply fallback(
            InventoryRequest request,
            String reason
    ) {
        Optional<CachedSnapshot> cached = cache.find(request.sku());
        Instant oldestAccepted = clock.instant().minus(maxCacheAge);

        if (cached.isPresent()
                && !cached.get().capturedAt().isBefore(oldestAccepted)) {
            CachedSnapshot entry = cached.get();

            return new InventoryReply(
                    request.sku(),
                    request.correlationId(),
                    LookupStatus.STALE_REFERENCE,
                    entry.snapshot().availableUnits(),
                    entry.capturedAt(),
                    reason
            );
        }

        return new InventoryReply(
                request.sku(),
                request.correlationId(),
                LookupStatus.UNAVAILABLE,
                null,
                null,
                "CACHE_MISSING_OR_EXPIRED"
        );
    }
}
~~~

**Why does this placement protect the breaker?** The supplier inside **executeSupplier** only calls StockClient. If StockClient throws **StockDependencyException**, the breaker observes the failed outcome before the exception is caught in **InventoryLookupService.lookup** and converted into a fallback. If the circuit is already OPEN, the supplier does not run, so the external API receives no additional requests.

Points to complete in a real application:

1. **StockClient must have a timeout**. A breaker does not cancel a hung HTTP call.
2. **The cache must be reliable**. Handle cache errors or unreachability and return UNAVAILABLE/fail fast per policy; a cache outage must not hang the Gateway indefinitely.
3. **TTL must follow business requirements**. Two minutes in the example is purely illustrative; fast-changing inventory data might not be safe as reference for that long.
4. **Do not use the STALE_REFERENCE branch to finalize orders**. The checkout route must require fresh confirmation.
5. **Do not swallow programming errors**. The example only catches breaker rejections and intentional dependency exceptions.
6. **Map statuses for API callers**. The UI can display a notice, or a REST adapter can translate UNAVAILABLE into a structured error response, depending on the contract.

In this example, **InventoryCache** is read-only. Refreshing the cache requires a separate write path when verified fresh data arrives or an independent sync process, avoiding overwriting the cache with fallback data.

## 6. Native Spring Integration advice and fallback placement

If the flow uses **RequestHandlerCircuitBreakerAdvice**, the core idea is that **the handler calling the dependency is wrapped by the advice**, while recovery/fallback runs at a boundary **after the exception leaves the protected section**.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Fallback boundary]
    B --> C[RequestHandlerCircuitBreakerAdvice]
    C --> D[Service Activator]
    D --> E[StockClient]
    C -->|Error / rejection| B
    B --> F[Outcome with status]
    E -->|Success| F
~~~

Distinguish clearly:

- The advice controls whether to invoke the Service Activator based on observed failures and circuit state.
- The fallback component turns **errors from the advice/handler** into a business outcome. When implementing, follow the exact exceptions, error channel, and advice chain configured in your Spring Integration version.
- Declaring an error channel does not automatically turn an exception in a **synchronous Gateway over DirectChannel** into a branched message. In many cases the exception bubbles straight back to the caller.
- For endpoints running with a **poller** or asynchronous channels, errors can be wrapped in an **ErrorMessage** sent to the appropriate error channel; handlers on the error flow must extract the original message, cause, and correlation ID.

If both **retry advice** and a breaker are enabled, decide their order explicitly. Placing fallback before the breaker records failures can prevent the circuit from ever opening; placing uncontrolled retries on OPEN-circuit rejections can generate pointless bursts of internal requests.

## 7. Fallback cache: handling TTL, data source, and consistency

Caching is most useful for **display-oriented reads**. A safe fallback cache should satisfy these conditions:

| Rule | How to implement |
| --- | --- |
| Know when data was captured | Store **capturedAt** from when the fresh response arrived |
| Bound staleness | Compare against TTL or use-case age limit |
| Preserve provenance | Return **status = STALE_REFERENCE** and sourceTime |
| Do not confuse missing data with 0 | Return **UNAVAILABLE** if no snapshot exists |
| Store only verified data | Never cache error responses or unverified payloads |
| Have a plan when cache itself fails | Cache timeout and final fallback to UNAVAILABLE/fail fast |
| Prevent cross-scope cache leaks | Include tenant/context attributes in keys if data is not public |

**Example:** an inventory snapshot was captured at 10:00:00, a request arrives at 10:01:00, and the display TTL is 2 minutes. You can return **STALE_REFERENCE** with sourceTime 10:00:00. If a request arrives at 10:05:00, the snapshot is expired, so return **UNAVAILABLE**; do not set **availableUnits = 0**.

For data scoped by tenant, region, warehouse, or currency, the cache key must include all distinguishing dimensions. Sharing one cache key by SKU when each warehouse holds separate stock is a serious business bug.

## 8. Queue-based fallback when work can be processed later

For tasks that do not require an immediate result, instead of calling an OPEN dependency, you can send the message to a durable queue for later execution:

~~~mermaid
flowchart TD
    A[Gateway / Command] --> B[Router / policy]
    B -->|Dependency ready| C[Execute]
    B -->|Breaker rejects| D[Persist outbox / durable queue]
    D --> E[ACK: ACCEPTED_FOR_LATER]
    D --> F[Consumer with retry backoff]
    F --> G{Dependency ready?}
    G -->|Yes| H[Idempotent execution]
    G -->|No| I[Defer / DLQ per limits]
~~~

This policy fits **sending notification emails, exporting reports, or background synchronization**. It does not fit steps requiring an **immediate decision**, such as charging payment or reserving inventory where the application returns completion before the work actually succeeds.

Define clearly:

- **What does ACK mean?** **ACCEPTED_FOR_LATER** only confirms the request has been durably persisted, not that the dependency has processed it successfully.
- **No lost messages:** only return ACK after saving to the queue/outbox succeeds; manage transaction boundaries accordingly.
- **Idempotency key:** guards against a consumer receiving the same message twice.
- **Bounded retry:** backoff, jitter, max attempts, dead-letter channel/queue, and replay capability.
- **Bounded queue:** timeout/TTL, queue depth, alert thresholds, and policy when the queue is full.
- **Preserve correlation:** retain request ID, tenant ID, and trace/correlation ID to look up tasks when users ask for status.

An OPEN breaker can cause a queue to build up very rapidly. Unboundedly "accepting for later" merely shifts the bottleneck from the HTTP client to the queue. Monitor backpressure and enforce intake limits.

## 9. Gateway, Router, Splitter, Aggregator, and error channel

### 9.1. Gateway: callers must see degraded state

For a synchronous Gateway, design two clear contracts:

- **Return outcome:** calling the Gateway method returns an **InventoryReply** with status **FRESH**, **STALE_REFERENCE**, or **UNAVAILABLE**.
- **Fail fast via exception:** if business rules disallow fallback, the exception propagates to the application, and the REST/controller boundary maps it to a service-temporarily-unavailable response.

Do not return a fake **StockResult** identical to a fresh result just to preserve the API signature. The caller has no way to detect stale data and can make wrong decisions as a result.

### 9.2. Router and Filter: route by result usability

The Router should branch on **business requirements**: read-only display can go to a branch permitting cache; checkout requires fresh data. Filters can reject invalid requests before touching the dependency. You can add a Router after the fallback to direct **UNAVAILABLE** into an error-notification flow instead of treating it like a valid stock result.

### 9.3. Splitter and Aggregator: avoid waiting indefinitely

Suppose a Splitter divides an order into three messages checking inventory across different warehouses. One warehouse is OPEN while the other two return fresh data. If the OPEN branch is dropped without emitting a reply, the Aggregator can wait forever.

Clear handling approach:

1. Attach an order-level **correlation ID** and sequence metadata to each branch.
2. The OPEN branch emits an appropriate **UNAVAILABLE/STALE_REFERENCE** outcome keeping the same correlation.
3. The Aggregator receives all three outcomes and decides on a **partial result**, a missing-data notice, or declining order confirmation.
4. Configure group timeout, group expiration, and discard/error paths per actual requirements to avoid groups lingering forever if a branch loses signal completely.

Do not conflate **partial result** with **business completion**. Whenever there is risk of inaccurate data, the Aggregator should report uncertainty rather than assuming success.

### 9.4. Error channel and correlation

When an asynchronous endpoint fails to process a message, Spring Integration can dispatch an **ErrorMessage** containing the cause and original message details. The error flow needs **dependency name**, **cause**, **correlation ID**, **message ID**, retry policy, and potentially an **idempotency key**.

If the application returns a fallback outcome directly inside the handler, **no exception may be emitted to the error channel**, because the error was already converted into a result. In that case, proactively emit logs/metrics for the degraded state; do not rely solely on ErrorMessage counts to gauge total errors.

## 10. Avoiding bad interactions between retry, fallback, and breaker

The three mechanisms serve distinct roles:

| Mechanism | Function | Principle |
| --- | --- | --- |
| **Retry** | Retry transient failures | Bounded, with backoff, only when repetition is safe |
| **Circuit breaker** | Stop calling when dependency is unstable | Observe real outcomes; fail fast |
| **Fallback** | Define outcome when dependency is unavailable | Replacement data must carry status and usage constraints |

Two arrangements can yield different results:

~~~mermaid
flowchart LR
    A[Gateway] --> B[Fallback]
    B --> C[Circuit breaker]
    C --> D[Bounded retry]
    D --> E[Dependency]
~~~

A breaker wrapping retry can see **one final outcome** per logical request. That fits when you want to evaluate requests as a whole. If retry wraps the breaker, each attempt contributes to circuit state; once OPEN, do not blindly retry breaker-rejected errors.

**Anti-pattern:** configuring 10 retries on **CallNotPermittedException** before finally returning cached data. Those attempts do not test dependency recovery; they only add CPU, latency, and log noise. Distinguish **call not permitted** from retryable network errors.

**Another anti-pattern:** every time StockClient times out, catching the exception inside the supplier, returning a cached object, and reporting success. The breaker sees every request "succeed" and never opens. The right approach is letting the breaker record the failure, then having the outer fallback translate it into an outcome for the caller.

## 11. Testing fallback with a fake dependency and call counter

Use a **fake StockClient** with controllable outcomes, a fake cache with fresh/stale entries, a fixed clock, and a breaker with a low test threshold. The primary goal is proving **when OPEN, the fallback still returns per contract and StockClient is not called again**.

Illustrative JUnit 5 example using the types defined above (imports omitted):

~~~java
@Test
void openBreakerUsesCacheWithoutCallingStockAgain() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(100.0f)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger remoteCalls = new AtomicInteger();

    StockClient failingClient = sku -> {
        remoteCalls.incrementAndGet();
        throw new StockDependencyException(
                "stock API timed out",
                new java.net.SocketTimeoutException()
        );
    };

    Clock clock = Clock.fixed(
            Instant.parse("2026-11-21T10:00:00Z"),
            ZoneOffset.UTC
    );

    InventoryCache cache = sku -> Optional.of(
            new CachedSnapshot(
                    new StockSnapshot(sku, 12),
                    Instant.parse("2026-11-21T09:59:00Z")
            )
    );

    InventoryLookupService service = new InventoryLookupService(
            breaker, failingClient, cache, clock, Duration.ofMinutes(2)
    );

    InventoryRequest request =
            new InventoryRequest("SKU-123", 2, "corr-1001");

    // First two requests actually call the dependency and receive fallback.
    service.lookup(request);
    service.lookup(request);

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertEquals(2, remoteCalls.get());

    // Third request is blocked at the breaker and uses the cache immediately.
    InventoryReply reply = service.lookup(request);
    assertEquals(2, remoteCalls.get());
    assertEquals(LookupStatus.STALE_REFERENCE, reply.status());
    assertEquals(Integer.valueOf(12), reply.availableUnits());
    assertEquals("BREAKER_REJECTED", reply.reasonCode());
    assertEquals("corr-1001", reply.correlationId());
}
~~~

**Additional test matrix** for real flows:

| Scenario | What to verify |
| --- | --- |
| CLOSED, Stock API succeeds | **FRESH**, accurate data; cache is not used as primary result |
| CLOSED, Stock API fails | Breaker records failure; fallback returns appropriate outcome |
| OPEN, cache within TTL | **STALE_REFERENCE**, accurate sourceTime, remote call counter does not increase |
| OPEN, cache expired | **UNAVAILABLE**; does not return fake stock quantity |
| OPEN, cache fails or unreachable | Safe exit policy; does not hang the Gateway |
| HALF_OPEN, no permit granted | Can fall back; does not count as an executed probe |
| HALF_OPEN, probe succeeds | Recovers per breaker rules; subsequent requests can be FRESH again |
| Validation error in Filter | Does not reach StockClient, does not use fallback to hide error |
| Retry combined with fallback | Bounded attempts, does not retry breaker rejections |
| Splitter/Aggregator with OPEN branch | Correlation remains intact; group completes via outcome/timeout |
| Deferred queue | ACK only after durable persistence, safe replay via idempotency |
| Multiple pods | Each breaker may be in a different state; fallback output obeys the same contract |

For HALF_OPEN and wait-duration scenarios, use test-friendly configuration or library-supported clock controls; avoid long sleeps that make tests slow and flaky. The examples here illustrate behavioral verification and do not replace integration tests for your exact library version and transport.

## 12. Observing degraded state in production

A fallback may keep users from seeing exceptions, yet the system is still experiencing an incident. Therefore, observe **the breaker and the fallback separately**:

| Metric or log | Purpose |
| --- | --- |
| Breaker state/transitions per dependency | Distinguish CLOSED, OPEN, HALF_OPEN |
| Not-permitted calls | Measure requests short-circuited right at the breaker |
| Failure rate and client timeouts | Know whether the dependency is genuinely failing |
| **fallback_used** by type | See which traffic uses cache, fail fast, or defer |
| **cache_age** and cache misses | Track freshness and reliability of fallback data |
| Gateway latency / error rate | Measure user-perceived impact |
| Queue depth / oldest message age | Detect buildup of deferred tasks |
| Aggregator pending / expired groups | Detect fallback or error paths dropping results |
| Correlation ID / trace ID | Investigate a request across EIPs |

Tag metrics with **breaker name**, **dependency**, **fallback type**, **reason code**, and **flow name**, while avoiding high-cardinality labels like SKU or correlation ID; those IDs belong in traces/logs.

Alert if fallback cache is used continuously for an extended period, cache age exceeds limits, queues accumulate, or the breaker repeatedly cycles **OPEN → HALF_OPEN → OPEN**. A system returning 200 for every request via fallback while serving overly stale data can still violate business requirements.

## 13. Common mistakes when designing fallback

1. **Fallback sits inside the breaker's observation boundary:** exceptions are swallowed, so the circuit struggles to open during real dependency failures.
2. **Returning stale data as if fresh:** downstream uses inaccurate data for checkout/payment.
3. **Returning 0 on cache miss:** fails to distinguish "out of stock" from "unknown".
4. **Using one fallback for every use case:** reference pages and transaction confirmation have different consistency requirements.
5. **Retrying when breaker is OPEN:** increases latency even though the client is never called.
6. **No timeout on client and cache:** fallback itself gets blocked by the backup source.
7. **Losing correlation when branching:** Aggregator or error flow cannot correlate back to the original message.
8. **Unbounded queue or ACKing before durable save:** causes lost tasks or uncontrolled backlog growth.
9. **Measuring only upstream errors:** fallback returns results so error charts drop, masking prolonged degradation.
10. **Not separating programming bugs from dependency errors:** fallback hides internal bugs, making root-cause analysis harder.

## 14. Spring Integration checklist

- [ ] Breaker sits close to the dependency call; fallback sits outside the breaker boundary so failures are recorded.
- [ ] Choose fail fast, cache, backup source, or queue based on business consistency requirements.
- [ ] Outcomes clearly distinguish **FRESH**, **STALE_REFERENCE**, **UNAVAILABLE**, and include correlation ID.
- [ ] Cache has TTL, source timestamp, context-appropriate cache key, and cache-miss policy.
- [ ] Real client has timeouts; bounded retry that does not retry breaker rejections.
- [ ] Gateway returns structured degraded responses; never mask validation errors with fallback.
- [ ] Asynchronous flows configure the right error channel; Splitter/Aggregator handle missing-result branches.
- [ ] If using a queue, ensure persistence, idempotency, backpressure limits, and dead-letter handling.
- [ ] Test OPEN using a **remote call counter**, cache miss/expired, HALF_OPEN, and correlation paths.
- [ ] Observe **fallback rate**, cache age, breaker rejected calls, and effects on Gateway/queues.

**Fallback when the circuit is open** turns a call-blocking mechanism into an intentional service degradation policy. In Spring Integration, a well-designed fallback lets the Gateway return clear results, lets Router and Aggregator handle unavailable branches, and still lets the breaker record enough dependency failures to keep external outages from dragging down the rest of the system.
