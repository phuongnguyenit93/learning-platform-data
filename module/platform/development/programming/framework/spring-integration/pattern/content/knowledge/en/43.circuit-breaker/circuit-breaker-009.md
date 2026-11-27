# Monitoring circuit state

## 1. Monitoring breakers to know whether the system is protected or degraded

In **SPRING_INTEGRATION_PATTERN**, Spring Integration helps assemble Enterprise Integration Patterns into loosely coupled message flows: a Gateway receives requests, a Filter validates, a Transformer normalizes, a Router switches branches, a Service Activator calls dependencies, and Splitter/Aggregator coordinate results. A circuit breaker is attached close to the dependency call site to block new calls when upstream shows signs of errors or excessive slowness.

Once a breaker is in place, the operational question is not only **whether the external API is returning errors**, but also:

- Which dependency's breaker is currently **CLOSED**, **OPEN**, or **HALF_OPEN**?
- When did it open, for what reason, and how many times has it tried to recover?
- How many messages were rejected **before calling upstream**?
- Is the Gateway responding faster, or are users still hitting timeouts, fallbacks, and errors?
- Is a blocked Router branch causing the Aggregator to miss replies or queues to grow?
- Have some instances/pods recovered while other instances are still OPEN?

**Monitoring circuit state** means combining *current state*, *state transition events*, *call outcomes*, and *impact on the overall message flow*. You cannot look at a single "circuit opened" log line and conclude the system is effectively protected.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Filter / Transformer]
    B --> C{Router}
    C --> D[Breaker: stock-api]
    C --> E[Breaker: pricing-api]
    D --> F[Stock Client]
    E --> G[Pricing Client]
    D -.-> M[Events and Metrics]
    E -.-> M
    A -.-> T[Trace / Correlation]
    F -.-> T
    G -.-> T
    M --> H[Dashboard]
    T --> H
    H --> I[Alert / Incident response]
~~~

The key principle is **observing along the right failure domain**. Stock API being OPEN does not mean Pricing API is also failing, unless the two branches actually share a common failing dependency or resource.

## 2. What each state means when observed

| State | Technical meaning | What you should see in operations |
| --- | --- | --- |
| **CLOSED** | Permits calls and measures outcomes | Traffic reaches dependency; successes/failures are recorded |
| **OPEN** | Rejects new calls | Client call count drops; rejected/not-permitted count may rise |
| **HALF_OPEN** | Grants limited trial permits | Some probes reach dependency; requests exceeding permits may be rejected |

These three states belong to **the guard**, not to a single request. In CLOSED, a request can still fail. In OPEN, the application may serve a **fallback cache** response, while the dependency itself is not called. In HALF_OPEN, one successful probe is not guaranteed to close the circuit if policy requires multiple probes.

### 2.1. Current state differs from state-transition events

Suppose at 10:00 the breaker transitions **CLOSED → OPEN**. Afterward, no new requests arrive for 15 minutes.

- **Current state** may still be OPEN.
- **State-transition event count** may still be just 1.
- **Rejected call count** may be 0 because there was no new traffic.
- **HTTP error count to dependency** may be 0 because the breaker blocked calls.

A graph showing 0 HTTP errors during this window **does not prove upstream has recovered**. Inspect state, request volume, not-permitted calls, fallback usage, and probe outcomes together.

### 2.2. Special states

Some libraries, such as **Resilience4j**, also have operational states like **DISABLED**, **FORCED_OPEN**, and **METRICS_ONLY**. They do not share the same semantics as the three standard states:

- **DISABLED:** may allow execution without running normal circuit breaker logic.
- **FORCED_OPEN:** actively forces calls to be rejected.
- **METRICS_ONLY:** collects metrics without transitioning to OPEN to block requests.

Read the semantics for your exact library/version before building dashboards. Treating every unfamiliar state as CLOSED can misreport protection levels. Forcing state or resetting requires administrative authorization and dedicated audit logging.

## 3. Four layers of signals to collect

Good observability does not only emit metrics from the Circuit Breaker—it measures before and after it as well.

| Layer | Signals to collect | Helps answer |
| --- | --- | --- |
| **State** | Current state, state transitions, OPEN/HALF_OPEN timestamps | How long has the circuit been open, and is it flapping? |
| **Protected operation** | Successful, failed, slow, buffered calls, latency | Is upstream truly healthy or slow/failing? |
| **Blocked calls** | Not-permitted/rejected calls, reason code | How many requests did the breaker reject before the client? |
| **Message flow** | Gateway latency, errors/fallbacks, retries, queue depth, Aggregator pending | How is the circuit affecting users and other EIPs? |

These metrics are not interchangeable. A **not-permitted** call is not a failed HTTP attempt; a business-wise successful fallback also does not mean upstream is healthy.

### 3.1. What are gauges, counters, and events best used for?

- **State gauge:** represents current state per breaker name and instance. Standardize mapping or use per-state gauges provided by instrumentation.
- **State-transition events/counters:** count CLOSED → OPEN, OPEN → HALF_OPEN, HALF_OPEN → OPEN, and HALF_OPEN → CLOSED transitions. Useful for spotting circuit flapping.
- **Call outcome counters:** record successful, failed, slow, and rejected calls over your metrics system's time windows.
- **Latency histogram/timer:** observe p95/p99 or latency distributions; none of this can be inferred from failure count alone.
- **Trace/log:** investigate a specific message by correlation ID, exception, dependency, and branch.

Do not use a **cumulative counter** to represent "circuit is currently OPEN". Conversely, a current OPEN gauge does not tell you how many times the breaker tripped within an hour.

## 4. Metrics that are easy to misinterpret

Suppose the Stock API breaker opened due to errors, while the Gateway still receives 1,000 requests/minute and all quickly return **UNAVAILABLE**.

| Metric | What may be observed | Correct interpretation |
| --- | --- | --- |
| Actual calls to Stock API | Very low or 0 | Breaker is keeping traffic off the dependency |
| HTTP errors from Stock API | May drop to 0 | Insufficient proof that Stock API is healthy |
| Not-permitted calls | Close to Stock-API request volume | Many requests are being short-circuited at the breaker |
| Gateway latency | May decrease | Fail fast is working, yet business functionality is still degraded |
| Gateway error or fallback rate | May spike sharply | Users are not receiving fresh results |
| State | OPEN | Not yet enough evidence of recovery |

Looking only at dropping HTTP timeouts can make a dashboard look **falsely green**. Therefore, display **state + rejected calls + Gateway outcomes + fallback rate** together, ideally alongside dependency health checks independent of the breaker.

### 4.1. Failure rate and minimum calls

For sliding-window breakers, failure rate takes the form:

\[
\text{Failure rate}
=
\frac{\text{Recorded failed calls}}
{\text{Recorded calls in window}}
\times 100\%.
\]

For instance, 5/10 failed calls gives 50%. However, **Resilience4j** has **minimumNumberOfCalls**: before enough samples exist, failure rate can be represented by a sentinel value such as **-1**, meaning **no valid rate yet**, not "-1% failure".

Do not build alerts or charts that default negative failure rates to 0%. Display **INSUFFICIENT_DATA** or insufficient samples, alongside buffered calls/throughput to explain it.

### 4.2. Slow calls are not necessarily failed calls

A call taking 2 seconds yet returning a valid result can be a **slow success**. It increments slow-call counts without necessarily incrementing failure counts. A call timing out can be both **slow** and **failed**. Never add failed calls and slow calls together as if they were disjoint call totals.

**Not-permitted calls** occur before the supplier/handler invokes the client, so they must not be included in the denominator of failure rates for executed dependency calls.

## 5. Monitoring circuits in Resilience4j

**Resilience4j** provides APIs to inspect state, metrics snapshots, and an **EventPublisher** to listen for state transitions. The Spring Integration Java DSL example below shows reusing one breaker at the Stock API call site.

### 5.1. Message contract and client

~~~java
public record StockQuery(String sku, int quantity) {}

public record StockReply(
        String sku,
        int availableUnits
) {}

public interface StockClient {
    StockReply lookup(StockQuery query);
}

@MessagingGateway(defaultRequestChannel = "stock.requests")
public interface StockGateway {
    StockReply lookup(StockQuery query);
}
~~~

**StockClient** is an application-implemented adapter that needs connect/read/response timeouts and maps dependency failures into appropriate exceptions. The Java snippets omit imports and actual HTTP configuration to focus on the circuit.

### 5.2. Configuring registry, breaker, and event listener

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockCircuitConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(StockCircuitConfiguration.class);

    @Bean
    public CircuitBreakerRegistry circuitBreakerRegistry() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreakerRegistry.of(config);
    }

    @Bean
    public CircuitBreaker stockCircuitBreaker(
            CircuitBreakerRegistry registry
    ) {
        CircuitBreaker breaker =
                registry.circuitBreaker("stock-api");

        // Register exactly once at startup,
        // do not re-attach a listener on every request.
        breaker.getEventPublisher()
                .onStateTransition(event ->
                        log.warn(
                                "breaker={} transition={} time={}",
                                event.getCircuitBreakerName(),
                                event.getStateTransition(),
                                event.getCreationTime()
                        )
                );

        return breaker;
    }

    @Bean
    public IntegrationFlow stockFlow(
            StockClient stockClient,
            CircuitBreaker stockCircuitBreaker
    ) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) ->
                                stockCircuitBreaker.executeSupplier(
                                        () -> stockClient.lookup(query)
                                )
                )
                .get();
    }
}
~~~

Here, **stock-api** is a stable breaker name. All requests passing through this bean share state within **the same process**. On state transition events, the listener logs a record with breaker name, transition direction, and timestamp.

**Never attach listeners inside a per-request handler.** Every request would register another listener, causing memory leaks or duplicate log entries per event. Nor should you register the same listener repeatedly in multiple places when using a registry. In systems with multiple endpoints/tenants, attach listeners once when each breaker instance is created while bounding total key count.

**Never log exception payloads, access tokens, or sensitive data** in state-transition logs. When investigating a specific failed request, use traces/logs in the client adapter with correlation IDs and data protection policies.

### 5.3. Reading state and metrics snapshots

~~~java
CircuitBreaker.State state = stockCircuitBreaker.getState();
CircuitBreaker.Metrics metrics = stockCircuitBreaker.getMetrics();

int buffered = metrics.getNumberOfBufferedCalls();
int failed = metrics.getNumberOfFailedCalls();
int successful = metrics.getNumberOfSuccessfulCalls();
long rejected = metrics.getNumberOfNotPermittedCalls();

float failureRate = metrics.getFailureRate();
float slowCallRate = metrics.getSlowCallRate();
~~~

This example uses common Resilience4j APIs; verify exact signatures against the dependency version in your project.

**What to distinguish:**

- **buffered/failed/successful** are typically statistics for the current window, not all-time uptime counters.
- **failureRate/slowCallRate** may be invalid before minimum sample count is reached.
- **rejected/not-permitted** reflects requests rejected at the breaker, not HTTP client failures.
- **state** is a point-in-time snapshot; concurrent requests can change it right after reading.

Do not build total request counters by summing per-second window snapshots. A single call can appear in multiple snapshots, causing double counting. For long-term counts, use dedicated metric counters or the event publisher.

## 6. Micrometer integration and dashboards

If your application has **Micrometer** and a compatible **resilience4j-micrometer** module, bind the breaker registry to `MeterRegistry`. Example binder bean:

~~~java
@Bean
public MeterBinder circuitBreakerMeterBinder(
        CircuitBreakerRegistry circuitBreakerRegistry
) {
    return meterRegistry ->
            TaggedCircuitBreakerMetrics
                    .ofCircuitBreakerRegistry(circuitBreakerRegistry)
                    .bindTo(meterRegistry);
}
~~~

With Spring Boot Actuator, the application can expose metrics via actuator or your configured collector. Verify **the module is actually on the classpath**, the endpoint is enabled/authorized, and check **exact metric names/tags in your version**. Do not assume simply adding a breaker automatically populates Prometheus charts.

A minimal dashboard should include:

| Panel | Contents |
| --- | --- |
| **Breaker states** | List of breakers and states per instance |
| **State transitions** | Count of OPEN/HALF_OPEN/CLOSED transitions over time |
| **Call outcomes** | Successful, failed, slow, and not-permitted |
| **Latency** | p50/p95/p99 of HTTP client and Gateway |
| **Fallback** | Rate of stale cache, UNAVAILABLE, fail fast |
| **Queue** | Depth, oldest message age, DLQ count |
| **Retry** | Attempts per logical request, rejected-retry attempts |
| **Aggregator** | Pending groups, expired groups, partial results |

Metric names can vary by module, version, and exporter. When writing PromQL or dashboards, **inspect the actual exported metric names** instead of copying names from examples for a different version.

### 6.1. Never use unbounded-cardinality labels

Breakers can be named by service, endpoint, region, or tenant group. Avoid naming breakers with:

- Request ID, correlation ID, or trace ID.
- Full URLs containing query parameters or SKUs.
- Unbounded tenant IDs when tenant count is large.
- Emails, tokens, or confidential identifiers.

Prefer stable labels like **breaker_name**, **operation**, **region**, **instance**, **outcome**, or a bounded **tenant_group**. Detailed IDs belong in access-controlled traces/logs, not metric tags that explode time series.

## 7. How do you monitor native Spring Integration advice?

Spring Integration provides **RequestHandlerCircuitBreakerAdvice** to wrap request handlers. It is useful when you only need a consecutive-failure threshold, but **do not assume it provides the full event API and Micrometer metrics of Resilience4j**.

Example placing the advice directly on a Service Activator:

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
public IntegrationFlow stockFlow(
        StockClient stockClient,
        RequestHandlerCircuitBreakerAdvice stockCircuitAdvice
) {
    return IntegrationFlow.from("stock.requests")
            .handle(
                    StockQuery.class,
                    (query, headers) -> stockClient.lookup(query),
                    endpoint -> endpoint.advice(stockCircuitAdvice)
            )
            .get();
}
~~~

**Principles for instrumenting native advice:**

1. **Count handler entries and duration** in the client adapter to know how often upstream is actually invoked.
2. **Count exceptions exiting** the handler, classifying timeouts, connection errors, HTTP 5xx, and business errors.
3. **Count rejected/fallback outcomes** at the error boundary by accurately classifying the exception thrown by your version's native advice.
4. **Record correlation IDs** from the message flow to link requests and outcomes.
5. **Measure Gateway latency/errors, retry attempts, queues, and Aggregator group timeouts** to see the circuit's system-wide impact.
6. If you need exact **CLOSED/OPEN/HALF_OPEN state** reporting, use APIs/extension points supported by your version or choose an implementation exposing state/events, rather than guessing state from client error counts.

Do not count "last 3 timeouts" in a custom counter and report `state = OPEN` without reading real state: the advice may have reset its counter on a success, be in HALF_OPEN, or have had failures masked by retries/fallbacks. Such inferred measurements can drift from the breaker's internal state.

## 8. Tracing and correlation across Gateway, Router, Splitter/Aggregator

In a multi-branch flow, an "stock-api OPEN" event only tells you the status of one breaker. To know which requests were affected, you need message-flow context:

~~~mermaid
flowchart LR
    A[Gateway: correlation id] --> B{Router}
    B --> C[Stock breaker]
    B --> D[Pricing breaker]
    C --> E[Stock reply / UNAVAILABLE]
    D --> F[Pricing reply]
    E --> G[Aggregator]
    F --> G
    G --> H[Response / Error]
    C -.-> I[Trace / Log]
    D -.-> I
    G -.-> I
~~~

**Correlation ID** traces a logical request across endpoints and message channels. With a **Splitter**, each sub-message also carries sequence metadata and a branch ID. The **Aggregator** uses correlation/group semantics to assemble results; if one branch is rejected by a breaker without replying, the group can linger until timeout.

Collect or log these fields at relevant boundaries:

| Field | Meaning |
| --- | --- |
| **traceId / correlationId** | Links events belonging to one logical request |
| **messageId** | Identifies a specific message on a channel |
| **flow / endpoint name** | EIP branch that processed the message |
| **breaker name** | Failure domain the request traversed |
| **operation / tenant group** | Normalized context without exposing sensitive data |
| **outcome** | FRESH, FALLBACK, UNAVAILABLE, REJECTED, ERROR |
| **exception category** | Timeout, connection, upstream 5xx, not-permitted |
| **duration and attempt count** | Distinguishes slowness due to upstream vs. retries |
| **aggregator group / sequence status** | Investigates groups missing replies |

Never assume a correlation header is secret or sufficient to authenticate a tenant. Client-supplied headers must be validated at ingress; tenant/authorization context must derive from authenticated identity.

### 8.1. Error channels are not identical to breaker events

In a **synchronous** Gateway over DirectChannel, exceptions from a Service Activator or breaker typically propagate back to the caller. In **asynchronous** flows, adapters or pollers can emit an **ErrorMessage** to an error channel per configuration.

A breaker **OPEN** event does not necessarily produce an ErrorMessage: it is a breaker state transition. Conversely, **CallNotPermittedException** may be caught at the Gateway with an immediate fallback, emitting zero ErrorMessages. Therefore:

- Measure **state transitions** at the breaker.
- Measure **not-permitted** calls at the breaker.
- Measure **fallback/terminal outcomes** at the Gateway or handler boundary.
- Measure **ErrorMessages** in the error flow if present.
- Keep correlation and error classification so one incident is not miscounted as multiple unrelated upstream errors.

## 9. Retry, fallback, and queues can mask an OPEN state

### 9.1. Retry masking errors when the breaker sits outside

If the breaker wraps **outside Retry**, three failed attempts followed by one successful attempt can make the breaker see only a logical-request success. A low **breaker failed calls** metric does not mean the HTTP client avoided retrying multiple times. Add **retry_attempts** and **client_call_errors** at the adapter.

If Retry wraps **outside the breaker**, each attempt can affect state. Once the breaker is OPEN, retry must **stop on rejection errors** instead of looping pointlessly. Measuring breaker entries alongside remote calls shows whether the policy behaves correctly.

### 9.2. Fallback returning responses must still report degradation

A valid fallback cache lets the Gateway return replies very fast. However, the application must distinguish:

- **FRESH:** newly fetched data from upstream.
- **STALE_REFERENCE:** cache within allowed TTL and tagged as reference-only.
- **UNAVAILABLE:** no sufficiently safe data available.

Without measuring **fallback_used** and **cache_age**, dashboards can show a high HTTP 200 rate while the dependency has been OPEN for hours. Never treat stale replies as evidence that Stock API is healthy.

### 9.3. Queues can grow even while the breaker protects upstream

For asynchronous notifications or syncs, an OPEN breaker can route work into a durable queue/outbox for later attempts. Although no extra HTTP calls are made, **pending messages** and **oldest message age** can keep climbing.

Measure **queue depth, age, attempts, dead-letter rate, and backlog recovery throughput**; enforce intake limits or backpressure. If a consumer keeps NACKing/requeuing immediately, it creates a pointless redelivery loop. A new ErrorMessage or broker redelivery must not be assumed to represent an actual failed dependency call.

## 10. State per endpoint, tenant, and instance

If an application has breakers for:

- **stock.read**
- **stock.reserve**
- **pricing.read**

each breaker can hold its own state. If certain tenants use independent quotas/providers, you may need breakers per **tenant group** or authenticated tenant with a bounded key set. Never accidentally share one breaker across all dependencies, and never create a breaker per SKU or request ID.

In **multi-pod** deployments, **in-process** breakers normally keep independent state:

| Instance | stock-api breaker | Observed behavior |
| --- | --- | --- |
| pod-1 | OPEN | Requests hitting pod-1 are rejected |
| pod-2 | CLOSED | Requests hitting pod-2 can keep calling upstream |
| pod-3 | HALF_OPEN | A few probes are testing recovery |

Therefore, a single chart saying "stock-api = CLOSED" does not accurately represent the entire cluster if it reads from one pod or takes an ambiguous last-write-wins value.

More useful representations:

- **Instance distribution by state**, grouped by dependency name.
- **State transitions by instance and time**.
- **Total rejected calls by breaker name**, with drill-down per pod.
- **Upstream traffic and latency** to tell global outages from localized issues.
- **Rollout/version labels** when checking if a breaker only trips on one application version.

Do not assume Resilience4j automatically synchronizes state across pods. If you need cluster-wide quota enforcement, add a shared control mechanism such as a distributed rate limiter rather than treating an in-process breaker as a global coordinator.

## 11. Example incident timeline and accompanying charts

Suppose Stock API times out repeatedly, the breaker has a 20-second wait duration, and requests continue arriving:

| Time | Event | Signals you should see |
| --- | --- | --- |
| 14:00:00 | Breaker CLOSED; calling Stock API | Normal client calls, latency, and outcomes |
| 14:00:03 | Failures satisfy OPEN condition | State transition CLOSED → OPEN, failed calls |
| 14:00:04 | 100 new requests arrive | Not-permitted rises; remote calls do not rise correspondingly |
| 14:00:10 | Gateway returns fallback cache | Fallback rate rises, Gateway latency may stay low |
| 14:00:23 | Wait duration satisfied | Opportunity for HALF_OPEN per library policy |
| 14:00:25 | One probe request succeeds | Successful probe outcome; not necessarily enough for CLOSED yet |
| 14:00:26 | Probes meet recovery condition | State transition HALF_OPEN → CLOSED |
| 14:00:30 | Normal traffic resumes | Remote calls and fresh outcomes rise, rejected drops |

This is an **illustrative scenario**; exact transition timing and probe counts depend on the library, configuration, incoming request arrival, and call durations.

If at 14:00:26 a probe times out again, the breaker can transition back to OPEN, emitting **HALF_OPEN → OPEN**. When this repeats frequently, **state flapping** occurs. State transition metrics detect this far better than current-state gauges alone.

## 12. Designing actionable alerts

Do not alert on every isolated HTTP error. Combine **breaker condition**, **user impact**, and **duration**.

| Symptom | What the alert should state | Initial investigation step |
| --- | --- | --- |
| Sustained OPEN during peak hours | Which dependency, how many pods OPEN, fallback/rejected ratio | Check upstream, credentials, network, timeouts |
| Repeated HALF_OPEN → OPEN | Transition count and probe failures | Check recovery, overload, timeouts, and permit count |
| Rejections rising with limited fallback | UNAVAILABLE rate and Gateway errors | Review caller contract, cache TTL, and fail-fast policy |
| Queue depth/age climbing steadily | Backlog count, oldest message age | Throttle intake, inspect backlog and DLQ |
| CLOSED yet client timeouts rising | Failure rate, minimum calls, retry attempts | Check exception mapping, thresholds, scope, and retries |
| Only one pod abnormally OPEN | Specific pod/region/version | Investigate local environment issues |
| Unknown state / missing metrics | Loss of visibility into an active breaker | Check instrumentation, export, and monitoring pipeline |

Illustrative **alert conditions** (not default production thresholds):

- A breaker stays **OPEN continuously for more than 2 minutes** *and* real requests need it.
- Gateway **UNAVAILABLE** rate exceeds SLO budget over 5 minutes.
- **HALF_OPEN → OPEN** occurs 3 or more times within 10 minutes.
- **Queue oldest age** exceeds the business-allowed deadline.
- A breaker shows **high not-permitted calls while state/transition metrics are missing**.

Actual thresholds must reflect SLOs, traffic, recovery time, and dependency criticality. For low-traffic services, having no new requests after OPEN is not necessarily a page-worthy incident. Pair state alerts with request volume and user-impact signals to avoid noise.

## 13. Testing state monitoring and events

A good test proves **internal state, state-transition events, and actual behavior** align. Do not assert solely on log message counts because log formats can change or logs can be sampled.

### 13.1. JUnit 5: OPEN emits transition and blocks client

This example uses a fake supplier throwing exceptions to drive a Resilience4j breaker to OPEN. Event listeners record the transition and rejection count:

~~~java
@Test
void recordsTransitionAndRejectedCall() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(100.0f)
            .waitDurationInOpenState(Duration.ofMinutes(1))
            .build();

    CircuitBreaker breaker =
            CircuitBreaker.of("stock-test", config);

    List<String> transitions = new CopyOnWriteArrayList<>();
    AtomicInteger rejectedEvents = new AtomicInteger();
    AtomicInteger remoteCalls = new AtomicInteger();

    breaker.getEventPublisher()
            .onStateTransition(event ->
                    transitions.add(
                            event.getStateTransition().toString()
                    )
            )
            .onCallNotPermitted(event ->
                    rejectedEvents.incrementAndGet()
            );

    Supplier<String> failingClient = () -> {
        remoteCalls.incrementAndGet();
        throw new IllegalStateException("Stock API unavailable");
    };

    assertThrows(
            IllegalStateException.class,
            () -> breaker.executeSupplier(failingClient)
    );
    assertThrows(
            IllegalStateException.class,
            () -> breaker.executeSupplier(failingClient)
    );

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertTrue(transitions.contains("CLOSED_TO_OPEN"));
    assertEquals(2, remoteCalls.get());

    assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(failingClient)
    );

    assertEquals(2, remoteCalls.get());
    assertEquals(1, rejectedEvents.get());
}
~~~

Imports are omitted; requires JUnit 5, Resilience4j, and Java concurrency types. This test verifies one transition and one rejected request; it does **not** test real HTTP timeouts or time-based recovery logic.

### 13.2. Recommended test matrix

| Scenario | Observation to verify |
| --- | --- |
| CLOSED, request succeeds | State CLOSED; handler/client invoked |
| Enough failures to open breaker | Event CLOSED → OPEN, state OPEN |
| New request while OPEN | Remote calls do not increase; not-permitted increases |
| Wait duration elapsed and new request arrives | HALF_OPEN opportunity occurs per implementation |
| Probes succeed per policy | HALF_OPEN → CLOSED, fresh calls resume |
| Probe fails | HALF_OPEN → OPEN and rejected rises again |
| Retry outside breaker | Distinguish retry attempts from remote calls |
| Fallback cache returns result | Fallback metric increases even though client is not called |
| Synchronous Gateway throws exception | Outcome/latency accurate; do not assume ErrorMessage |
| Asynchronous error flow | Original message cause and correlation present |
| Splitter/Aggregator with OPEN branch | Partial/UNAVAILABLE/timeout and group does not hang |
| Two independent breakers | Stock OPEN state does not open Pricing |
| Multiple pods | Per-instance state accurate, dashboard does not misaggregate |
| Insufficient samples in sliding window | Failure rate is not shown as a valid 0% |
| Metrics export disabled | Missing telemetry detected, not falsely reporting healthy dependency |

In integration tests, use a fake dependency able to switch between success, timeout, error, and slow response; count invocations to confirm the breaker genuinely blocks requests. To test the HALF_OPEN lifecycle, use short test-specific wait config or library-supported time controls rather than flaky long sleeps.

## 14. Operational checklist

- [ ] Maintain an inventory of breakers per dependency/endpoint/tenant group with clear owners.
- [ ] Track current state **and** transition events; never rely on a single HTTP error metric.
- [ ] Collect successful, failed, slow, buffered, and not-permitted/rejected calls.
- [ ] Never equate not-permitted calls with executed client errors, nor successful fallbacks with healthy upstream.
- [ ] Distinguish insufficient-sample failure rate from a real 0% failure rate.
- [ ] If using Resilience4j, register listeners once and verify Micrometer binders against real metrics.
- [ ] If using native advice, never infer exact state from custom counters; instrument handlers, exceptions, and outcomes.
- [ ] Gateway, Router, Filter, Transformer, Splitter/Aggregator, and error channel preserve necessary traces/correlation.
- [ ] Have metrics for retry attempts, fallback rate, cache age, queue depth, DLQ, and Aggregator timeouts.
- [ ] Dashboards distinguish pods and do not assume cluster-wide synchronized breaker state.
- [ ] Metric labels have bounded cardinality; sensitive tenant IDs/request IDs are kept out of public metrics.
- [ ] Alerts combine OPEN duration, rejected calls, and user impact tied to SLOs.
- [ ] Tests verify state transitions, rejected events, and remote call counters, not just exceptions.
- [ ] Maintain runbooks to investigate upstream, timeouts, retries, breaker config, and recovery.

**Monitoring circuit state** means tracking both the guard's decisions and their consequences across the message flow. By combining state transitions, call outcomes, rejected calls, Gateway outcomes, and correlation, you know whether the breaker cut off the right dependency, whether load actually dropped, and whether users are receiving trustworthy results. This is the foundation for running Spring Integration safely, keeping it testable, and scaling cleanly as you add Routers, retries, error channels, or new processing branches.
