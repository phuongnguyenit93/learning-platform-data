# Resetting the circuit and wait durations

## 1. How does a circuit breaker recover after opening?

In **SPRING_INTEGRATION_PATTERN**, Enterprise Integration Patterns are assembled into a message flow using Spring Integration: a Gateway receives requests, a Filter validates data, a Transformer normalizes payloads, a Router selects branches, a Service Activator calls dependencies, and Splitter/Aggregator may coordinate results. A channel-based structure reduces coupling between components, yet a failing dependency can still make handlers hold threads for a long time, grow queues, and slow down the entire flow.

When a dependency fails repeatedly, the **circuit breaker** transitions to **OPEN** to fast-reject new calls. However, the external service may recover after a few seconds. Without a mechanism to retry and close the circuit, messages would keep getting rejected even after the dependency becomes healthy again.

That is why it is necessary to understand **wait duration before probing**, the **HALF_OPEN state**, and **circuit reset**. They are related, yet they are not the same action:

- **Waiting in OPEN:** keeps rejecting new calls for a configured duration.
- **Probing in HALF_OPEN:** grants permits for a limited number of new calls to pass through and assess dependency health.
- **Automatic recovery to CLOSED:** probe outcomes satisfy the breaker's recovery policy; traffic returns to normal.
- **Manual reset:** an administrative operation that proactively restores the breaker to its initial state and statistics, discarding the current protective conclusion. Use only with a clear operational reason.

This lesson focuses on that behavior in Spring Integration flows, distinguishing the native **RequestHandlerCircuitBreakerAdvice** mechanism from **Resilience4j**, and covering configuration, testing, and monitoring.

## 2. Lifecycle: CLOSED → OPEN → HALF_OPEN → CLOSED

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failures meet open condition
    OPEN --> HALF_OPEN: Wait duration elapsed and transition mechanism triggers
    HALF_OPEN --> CLOSED: Probes meet recovery condition
    HALF_OPEN --> OPEN: Probes show dependency is still failing
    OPEN --> CLOSED: Intentional manual reset
    HALF_OPEN --> CLOSED: Intentional manual reset
~~~

| State | New calls | Transition condition |
| --- | --- | --- |
| **CLOSED** | Permitted to execute and measured | Enough failures or slow calls per policy transitions to **OPEN** |
| **OPEN** | Blocked before reaching dependency | Once wait duration elapses, **eligible** to move to HALF_OPEN |
| **HALF_OPEN** | Only a limited number of probe calls are permitted; others may be rejected | Probe outcomes lead to **CLOSED** or back to **OPEN** |

The diagram illustrates the typical lifecycle. The required number of probes, how outcomes are aggregated, and exact transition timing depend on the implementation.

**Important:** the wait duration elapsing does not mean the circuit has confirmed the dependency is healthy. The circuit needs **probe outcomes** before deciding to return to CLOSED. Without traffic, some implementations keep the OPEN state until the next request arrives.

A breaker is a **state controller for future incoming calls**. It does not repair broken connections on its own, restart the dependency, or automatically cancel requests that were already admitted before the circuit opened.

## 3. Four easily confused durations

| Duration | Where is it measured? | Meaning |
| --- | --- | --- |
| **Connect timeout** | HTTP/gRPC/DB client | Limits time to establish a connection |
| **Read/response timeout or deadline** | Client calling dependency | Limits wait time for a specific call |
| **OPEN wait duration / halfOpenAfter** | Circuit breaker | Wait interval before probing is permitted |
| **HALF_OPEN maximum wait** | Breakers supporting this setting | Limits time waiting to collect enough probe outcomes, implementation-dependent |
| **Gateway reply timeout** | Gateway / reply channel | Limits how long the caller waits for a reply message |
| **Aggregator group timeout** | Aggregator | Limits how long a message group waits for all parts |

Do not reuse the same value across them because each timer solves a different problem.

For example:

- Stock HTTP client has a per-request timeout of **2 seconds**.
- Breaker transitions to OPEN and waits **20 seconds** before a probe opportunity.
- Synchronous Gateway has its own wait limit compatible with the overall flow processing budget.
- Aggregator has a group timeout in case one branch fails to return a message.

Merely increasing OPEN wait from 20 to 60 seconds still leaves **admitted network calls able to hang** when the client lacks a timeout. Merely lowering the Gateway reply timeout to 1 second does not guarantee a breaker wrapping an asynchronous handler will observe a failure right when the Gateway stops waiting.

### 3.1. When is the wait duration measured from?

For settings like **waitDurationInOpenState**, the anchor timestamp is typically tied to when the circuit **transitioned to OPEN**. Calls rejected while OPEN are not new dependency invocations and generally **do not restart the wait interval**.

An illustrative example with 20 seconds:

| Time | Event | Behavior |
| --- | --- | --- |
| 10:00:00 | Final failure reaches threshold | Transitions to **OPEN**; wait interval starts |
| 10:00:05 | Request A arrives | Fast-rejected |
| 10:00:17 | Request B arrives | Still rejected; open timestamp is not pushed forward |
| 10:00:20 | Wait duration satisfied | Circuit becomes eligible for probing |
| 10:00:23 | Request C arrives | May become the first probe call if implementation transitions on traffic |
| After probe | Success/failure outcome received | Decides **CLOSED** or **OPEN** per policy |

The wait duration after a failed probe typically starts from when the circuit **reopens**, not from the first OPEN timestamp.

## 4. Wait duration elapsed does not automatically mean a probe happens

Distinguish two trigger modes:

**Call-driven transition:** a request arriving after the deadline triggers a check and can transition OPEN to HALF_OPEN; that request becomes a probe candidate. If no new request arrives, no network call may be attempted at all.

**Background monitor transition:** the library can transition OPEN to HALF_OPEN once the wait duration elapses, even with no caller. However, **transitioning state does not mean sending a probe automatically**; a test call still requires a request source or a separate probing mechanism.

In Resilience4j, the common default behavior evaluates the OPEN → HALF_OPEN transition opportunity when a new request arrives. Depending on the version, you can enable **automaticTransitionFromOpenToHalfOpenEnabled(true)** to transition state via a background monitoring task. Do not turn it on thinking it will "auto-ping the dependency": that option does not generate probe traffic on its own.

~~~mermaid
sequenceDiagram
    participant A as Caller / Gateway
    participant B as Circuit breaker
    participant D as Stock API
    Note over B: OPEN, still within wait duration
    A->>B: Request 1
    B--xA: Fast reject
    Note over B: Wait duration elapsed
    A->>B: Request 2
    Note over B: Evaluate HALF_OPEN condition
    B->>D: Permit probe
    D-->>B: Probe outcome
    B-->>A: Response or exception
    Note over B: Evaluate transition to CLOSED / OPEN
~~~

**Do not confuse with health checks:** if you implement an active job sending probe requests, it must have timeouts, frequency limits, observable outcomes, and must not execute operations with unintended side effects.

## 5. Native Spring Integration: threshold and halfOpenAfter

When you need to protect a Service Activator in Spring Integration, attach **RequestHandlerCircuitBreakerAdvice** to the handler via the Java DSL.

Illustrative example:

~~~java
public record StockQuery(String sku, int quantity) {}

public record StockResult(String sku, int availableUnits) {}

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
public class StockIntegrationConfiguration {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockBreakerAdvice() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();

        advice.setThreshold(3);
        advice.setHalfOpenAfter(20_000); // milliseconds
        return advice;
    }

    @Bean
    public IntegrationFlow stockFlow(
            StockClient stockClient,
            RequestHandlerCircuitBreakerAdvice stockBreakerAdvice
    ) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> stockClient.lookup(query),
                        endpoint -> endpoint.advice(stockBreakerAdvice)
                )
                .get();
    }
}
~~~

Imports are omitted in the snippet, assuming the project already has Spring Integration and corresponding Gateway registration configured.

**Two key parameters:**

- **threshold = 3:** the advice opens the circuit once consecutive failed handler executions reach the threshold under the native mechanism.
- **halfOpenAfter = 20,000 ms:** wait duration before an opportunity to test the dependency while the circuit is OPEN.

Place the advice **right on the handler calling StockClient**, avoiding letting exceptions from Filter, Transformer, or Aggregator improperly affect the Stock API breaker. StockClient must still have connection and response timeouts; **halfOpenAfter does not replace client timeouts**.

### What does "reset" mean with native advice?

In CLOSED mode, a successful call can reset the consecutive-failure streak according to the advice's rules. After OPEN, the breaker needs to probe recovery; the outcome during the half-open phase determines whether it closes again or stays open.

Do not apply Resilience4j properties like **sliding window**, **minimumNumberOfCalls**, or **permittedNumberOfCallsInHalfOpenState** to the native advice: they belong to a different algorithm and API. When you need fine-grained control over probe counts, recovery failure rates, or manual resets via an administrative API, evaluate a dedicated library instead of guessing native features.

## 6. Resilience4j: wait configuration and HALF_OPEN rules

Resilience4j offers more options to control breaker sensitivity and recovery timing. Example:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(
                CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50.0f)
        .waitDurationInOpenState(Duration.ofSeconds(20))
        .permittedNumberOfCallsInHalfOpenState(2)
        .maxWaitDurationInHalfOpenState(Duration.ofSeconds(10))
        .automaticTransitionFromOpenToHalfOpenEnabled(false)
        .build();

CircuitBreaker stockBreaker =
        CircuitBreaker.of("stock-api", config);
~~~

| Property | Role |
| --- | --- |
| **slidingWindowSize(10)** | Retains outcomes of the last 10 calls to compute statistics |
| **minimumNumberOfCalls(5)** | Requires enough samples before evaluating failure rate |
| **failureRateThreshold(50%)** | Open condition when failure rate reaches threshold |
| **waitDurationInOpenState(20s)** | Duration the circuit stays OPEN before probing is possible |
| **permittedNumberOfCallsInHalfOpenState(2)** | Number of permits allocated for probes in HALF_OPEN |
| **maxWaitDurationInHalfOpenState(10s)** | Limits how long to wait for the HALF_OPEN phase to finish per Resilience4j's mechanism |
| **automaticTransitionFromOpenToHalfOpenEnabled(false)** | Transitions state on incoming requests rather than scheduling a transition |

**Condition to return to CLOSED after HALF_OPEN:** when probe outcomes meet the success criteria without violating the breaker's failure/slow-call thresholds, state returns to CLOSED. With **2 probes** and a **50%** failure rate threshold, if one probe fails and one succeeds, the failure rate reaches 50%; that situation can cause the breaker to transition back to OPEN. Never claim "one successful probe always closes the circuit" across all configurations.

**HALF_OPEN limit differs from network timeout:** the 10-second limit in HALF_OPEN coordinates outcome collection and state; it does not guarantee a hung HTTP request will be canceled. Each StockClient call still needs its own timeout/deadline.

### 6.1. Wiring Resilience4j into a handler

~~~java
@Bean
public IntegrationFlow stockFlow(
        StockClient stockClient,
        CircuitBreaker stockBreaker
) {
    return IntegrationFlow.from("stock.requests")
            .handle(
                    StockQuery.class,
                    (query, headers) ->
                            stockBreaker.executeSupplier(
                                    () -> stockClient.lookup(query)
                            )
            )
            .get();
}
~~~

What must be preserved is that **the supplier wraps only the dependency call**. If the handler catches exceptions and returns a fake success result **inside** the supplier, the breaker may fail to increment the failure count and fail to transition to OPEN when truly needed. If using fallback, place it at the boundary **outside** `executeSupplier`, after the breaker has observed the outcome.

Do not stack both the native breaker and Resilience4j on the same call site without a clear reason. Two controllers can make different OPEN/HALF_OPEN decisions, making observation and diagnosis difficult.

## 7. Distinguishing natural closing, counter reset, and manual reset

The word "reset" is often used for three distinct behaviors:

| Behavior | Example | Meaning |
| --- | --- | --- |
| **Clearing consecutive failure streak in CLOSED** | Native breaker sees a success amidst failures | Consecutive failure counter is no longer its prior value |
| **Recovering to CLOSED after HALF_OPEN** | Dependency is healthy, probes succeed sufficiently | Breaker closes the circuit per recovery policy |
| **Manual reset to initial state** | Operator invokes library-supported reset API | Discards current state and statistics per API semantics; new calls may be admitted immediately |

With **Resilience4j**, the **reset()** API resets the circuit breaker to its initial state and clears internal statistics per the library's mechanism:

~~~java
CircuitBreaker breaker = circuitBreakerRegistry
        .circuitBreaker("stock-api");

// Intentional administrative operation; do not invoke on the normal request path.
breaker.reset();
~~~

After reset, the breaker typically returns to **CLOSED** and new requests can reach the dependency. This is a **stronger** operation than waiting for OPEN duration to expire. If the dependency is still broken, resetting triggers a fresh wave of failed requests before hitting the threshold again.

**Do not automatically call reset() inside catch blocks or per-request error channels.** Doing so defeats protection: as soon as the circuit opens it gets closed immediately, and the next request hits the dependency again.

If you want to reset after operations fixes network config or restores upstream, verify the dependency is genuinely healthy, have a plan to control returning traffic, and record an audit log. Reset privileges should be authorized and scoped specifically, such as **stock-api** rather than all breakers in the application.

### 7.1. What are the risks of manual reset?

- **Thundering herd:** a backlog of requests floods the newly recovered dependency all at once.
- **Short-term loss of evidence:** clearing prior failure statistics can slow incident investigation if metrics/logs were not captured.
- **No cross-pod synchronization:** an in-process breaker in each instance keeps its own state; resetting one pod does not automatically reset all pods.
- **Treating symptoms:** resetting repeatedly without fixing root cause merely repeats the failure → OPEN cycle.
- **Wrong business boundary:** resetting permits future calls, but does not reprocess messages that already failed or were dropped.

Therefore, **automatic recovery via HALF_OPEN** should be the normal path. Manual reset is reserved for operational actions with clear justification and authorization.

## 8. Illustrative timeline: wait 20 seconds, allow two probes

Suppose a Resilience4j breaker opened at **12:00:00**, waits **20 seconds**, and allows **2 probes** in HALF_OPEN. This example uses a failure-rate policy, with the open condition already met before this timestamp.

| Time | Event | Behavior / state |
| --- | --- | --- |
| 12:00:00 | Open condition met | **OPEN**, rejects new calls |
| 12:00:06 | Request A arrives | Rejected; Stock API not called |
| 12:00:19 | Request B arrives | Rejected; does not extend wait duration |
| 12:00:20 | Wait duration satisfied | Eligible to transition to HALF_OPEN per configured mechanism |
| 12:00:22 | Request C arrives | Granted first probe permit |
| 12:00:22 | Request D arrives | May be granted second probe permit |
| 12:00:23 | Request E arrives, permits exhausted | Rejected; no third Stock API call |
| After C and D complete | Both probes succeed | Can transition to **CLOSED** |
| Alternative branch | One probe fails, one succeeds | Can transition back to **OPEN** because HALF_OPEN failure rate meets threshold |

The last two rows are **two alternative outcome branches**, not sequential events within one probe round.

If the circuit reopens at **12:00:24**, the new wait duration starts from that reopen timestamp. A call arriving too early is still blocked; never assume "we already waited 20 seconds once, so all requests can pass from now on".

### When no request arrives after the wait duration

In call-driven transition mode, by 12:00:20 no test call may have occurred yet. If the next request arrives at **12:05**, probing can begin then. A separate health-check job can observe the dependency externally, but it must avoid side effects and must not be mistaken for the breaker testing itself.

## 9. HALF_OPEN under heavy load and hung probes

In high-traffic systems, hundreds of requests may arrive simultaneously after the OPEN duration. Without limiting probes, a partially recovered dependency can be overwhelmed immediately.

**Resilience4j** lets you cap permits in HALF_OPEN. Only requests granted a permit reach the dependency; remaining requests can take the error or fallback path. This reduces the risk of "recovering for one second then crashing again".

However, three issues still need handling:

1. **Slow or hung probes:** you must have HTTP/gRPC/DB client timeouts. While all permits are occupied, other requests can still be rejected.
2. **Not enough probe requests:** if traffic is very low, HALF_OPEN can linger before collecting enough outcomes. Timeouts in HALF_OPEN or active health checks must be evaluated against the actual library.
3. **Probes with side effects:** do not use create-order or charge-payment requests merely as health probes. If an actual write request is allowed through, it needs idempotency and a clear handling contract.

In a flow with a **Splitter**, one business request can produce multiple sub-messages targeting the same breaker. If only two permits are allowed, the remaining sub-messages may be rejected in HALF_OPEN. The Aggregator must understand each branch's state, preserve correlation IDs, and never wait indefinitely.

## 10. Retry, fallback, and error channel during recovery

### 10.1. Retries must not defeat the OPEN wait

~~~mermaid
flowchart LR
    A[Gateway] --> B[Fallback boundary]
    B --> C[Circuit breaker]
    C --> D[Bounded retry if appropriate]
    D --> E[Stock API]
    C -->|Not permitted| B
~~~

While the breaker is OPEN, continuously retrying **CallNotPermittedException** does not help the dependency recover. Every new attempt is still rejected, while wasting CPU, logs, and latency.

During a HALF_OPEN probe, if **retry wraps inside the breaker**, multiple network attempts of one logical request can generate more load than one physical probe. If **retry wraps outside the breaker**, each attempt may consume its own permit. Decide explicitly whether the breaker measures **logical requests** or **attempts**, bound retries/backoff, and honor the overall deadline.

Never use unbounded retries for operations with side effects. If the dependency received the command but the reply was lost, retrying can execute it twice. For write operations, require an idempotency key and replay controls.

### 10.2. Fallback in OPEN and HALF_OPEN

**The circuit breaker only decides whether a call is permitted.** It does not define replacement data itself.

| Business branch | When circuit rejects | Strategy |
| --- | --- | --- |
| Catalog lookup | Cannot fetch fresh data | Can use cache if TTL and data source meet requirements |
| Stock confirmation before checkout | Cannot confirm fresh count | **Fail fast** or return UNAVAILABLE, never assume out of stock |
| Sending deferred notifications | Cannot reach provider yet | Persist to durable queue/outbox with idempotency key |
| Payments | Cannot determine whether transaction completed | Return reconciliation-needed status; avoid assuming failure or blind retrying |

An outcome can carry **FRESH**, **STALE_REFERENCE**, or **UNAVAILABLE**, plus **reasonCode** to distinguish **BREAKER_REJECTED**, **UPSTREAM_TIMEOUT**, and **CACHE_EXPIRED**. Never use a fake "succeeded" payload to mask a failing dependency.

### 10.3. Gateway, error channel, and correlation

In a synchronous Gateway over **DirectChannel**, breaker-rejection exceptions can propagate directly back to the caller. In asynchronous flows or poller-driven endpoints, exceptions can become an **ErrorMessage** sent to the **error channel** depending on configuration. Distinguish execution boundaries before deciding where fallback runs.

With **Splitter/Aggregator**, a branch that is OPEN or in HALF_OPEN without permits may not produce a normal reply. Preserve **correlation ID**, sequence headers, and apply one of these mechanisms:

- Return a degraded outcome for that branch so the Aggregator has complete information.
- Allow partial results per business contract.
- Configure group timeout, expiration, and discard/error paths so groups are not held indefinitely.

Resetting a breaker does not automatically replay messages already routed to an error channel or dead-letter queue. If replay is needed, build a dedicated workflow that guarantees idempotency.

## 11. Observing whether the circuit has genuinely recovered

A breaker transitioning to CLOSED is only one signal; also check dependency health and caller experience.

| Metric / event | Operational question |
| --- | --- |
| State transitions CLOSED/OPEN/HALF_OPEN | Which circuit is waiting, which just recovered? |
| OPEN timestamp and reopen count | Is the breaker flapping continuously? |
| Failed and slow calls | Is the dependency still failing or slow during probes? |
| Not-permitted / rejected calls | How many requests were blocked in OPEN/HALF_OPEN? |
| Probe outcomes and latency | Are probes collecting enough samples within deadlines? |
| Fallback usage rate and cache age | Has the system been relying on stale data for too long? |
| Gateway latency/error rate | Are callers actually getting better service? |
| Queue depth and oldest message age | Is deferred work piling up? |
| Aggregator pending/expired groups | Are blocked branches causing missing results? |
| Correlation/trace ID in logs | Can we trace the message causing an incident? |

With Resilience4j, register state-transition events and integrate metrics (such as Micrometer). Native advice must be observed according to the capabilities of your Spring Integration version, potentially adding timing and error instrumentation at the handler/client.

Do not attach high-cardinality **correlation IDs** or SKUs as metric labels. Keep those IDs in logs/traces; metrics should carry bounded-cardinality labels like **breaker name**, **dependency**, **flow**, and **outcome type**.

### When the breaker flaps OPEN → HALF_OPEN → OPEN

Most likely the dependency has only partially recovered, timeouts are miscalibrated, or probe traffic is too high. Check actual data before changing thresholds:

1. Are probe calls actually reaching the right upstream?
2. Are HTTP client timeouts, DNS/TLS, and connection pools healthy?
3. What are the failure rate and slow-call rate during HALF_OPEN?
4. Is the probe count sufficient for evaluation without causing overload?
5. Is a fallback, retry, or cache masking outcomes the breaker needs to see?

Increasing wait duration gives the dependency more recovery time, but also extends the period during which users see rejections. Choose the duration based on SLOs, dependency recovery time, actual traffic, and fallback cost rather than raising it blindly.

## 12. Testing reset and wait durations

Use a **fake StockClient** that can toggle between success and failure, plus a **call counter** to prove OPEN behavior. In recovery tests, inspect state, permitted probe count, and rejected request count.

### 12.1. Unit test for manual reset with Resilience4j

The JUnit 5 test below shows **reset() closes the breaker** and admits new calls; this tests an **administrative operation**, not automatic wait duration verification.

~~~java
@Test
void manualResetClosesCircuitAndAllowsNewCall() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(50.0f)
            .waitDurationInOpenState(Duration.ofMinutes(1))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger remoteCalls = new AtomicInteger();
    AtomicBoolean dependencyHealthy = new AtomicBoolean(false);

    Supplier<String> call = () -> {
        remoteCalls.incrementAndGet();
        if (!dependencyHealthy.get()) {
            throw new IllegalStateException("Stock API unavailable");
        }
        return "OK";
    };

    assertThrows(
            IllegalStateException.class,
            () -> breaker.executeSupplier(call)
    );
    assertThrows(
            IllegalStateException.class,
            () -> breaker.executeSupplier(call)
    );

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertEquals(2, remoteCalls.get());

    assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(call)
    );
    assertEquals(2, remoteCalls.get());

    dependencyHealthy.set(true);
    breaker.reset(); // Illustrates an intentional administrative operation only.

    assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
    assertEquals("OK", breaker.executeSupplier(call));
    assertEquals(3, remoteCalls.get());
}
~~~

Imports are omitted; requires Resilience4j, JUnit 5, **AtomicInteger**, **AtomicBoolean**, **Supplier**. The test uses neither real HTTP nor sleep, directly verifying **manual reset** and the **call counter**.

### 12.2. Automatic recovery test matrix

| Scenario | Expected verification |
| --- | --- |
| CLOSED, failures below threshold | Circuit not OPEN, handler keeps executing |
| Threshold reached | Circuit OPEN, next request does not call client |
| Request arrives before OPEN wait | Fast-rejected, **call counter does not increase** |
| No request arrives while OPEN | Do not assume a probe happened on its own |
| First request after wait | Evaluated for HALF_OPEN permit per policy |
| Probe count smaller than concurrent requests | Only valid permit count reaches client |
| Probes meet success criteria | Circuit returns CLOSED, subsequent requests permitted normally |
| Probe fails or is too slow | Circuit can reopen, starting a new wait duration |
| Probe hangs | Client timeout and HALF_OPEN wait have a clear exit mechanism |
| Operator calls reset() | State/counters reset, new requests permitted |
| Reset on one pod | Do not assume other pods were reset |
| Gateway/Splitter/Aggregator hits OPEN | Caller or branch gets clear outcome/error/timeout, correlation preserved |

To test real **wait durations**, use short wait durations in test config, library-provided time-control mechanisms (if available), or verify state transition events in integration tests. Avoid arbitrary long sleeps that depend on scheduler timing; also do not force state manually and claim wait-duration logic was tested.

### 12.3. Two easily missed verifications

**Verification 1: Reset does not replay messages.** Send a message while OPEN, verify it was routed to error/fallback or queue per policy. Call reset and send a **new** message; do not assume the old message is automatically resent.

**Verification 2: HALF_OPEN does not admit unbounded traffic.** When multiple calls arrive concurrently, use a barrier/latch in the test to hold probes long enough, observe that the call counter increases only up to the permit count, and assert excess calls receive a deterministic error or fallback.

## 13. Common design mistakes

1. **Equating OPEN wait with network timeout:** waiting 20 seconds before probing does not bound an in-flight HTTP request.
2. **Assuming wait expiration means CLOSED:** probe outcomes and evaluation policy are required.
3. **Assuming auto-transition to HALF_OPEN pings the dependency:** state transition may generate zero network requests.
4. **Not limiting probes:** traffic floods a barely recovered dependency, knocking it down again.
5. **Calling reset() on every exception:** disables OPEN and keeps hammering a broken service.
6. **Retrying CallNotPermittedException:** increases latency, logs, and CPU without adding health signal.
7. **Using non-idempotent write probes:** causes duplicate execution upon retry or timeout.
8. **No deadline for probes:** HALF_OPEN can stall because of hung requests.
9. **Resetting one pod and assuming all recovered:** each in-process breaker keeps separate state.
10. **Dropping correlation or Aggregator timeouts:** a rejected branch leaves groups waiting forever.
11. **Not measuring fallback:** the circuit stays OPEN for a long time while looking only at external API error rates makes the system look healthy.
12. **Closing the circuit because cached data succeeded:** if fallback runs inside the breaker zone, cache hits hide dependency failures.

## 14. Pre-deployment checklist

- [ ] Clearly distinguish client timeout, OPEN wait, HALF_OPEN wait, and Gateway/Aggregator timeouts.
- [ ] Understand whether the implementation transitions OPEN → HALF_OPEN on requests or via a background monitor.
- [ ] Configure timeouts on the dependency client and a safe probing policy.
- [ ] Tune thresholds, wait duration, and probe count to dependency load/SLOs.
- [ ] Do not share one breaker across Stock, Pricing, and independent failure domains.
- [ ] Place fallback outside the breaker boundary; outcomes distinguish fresh, stale, and unavailable.
- [ ] Bound retries, do not retry circuit rejections; operations with side effects require idempotency.
- [ ] Preserve correlation and define error paths/group timeouts in Splitter/Aggregator.
- [ ] Use manual reset only with operational justification, audit logging, and recovery traffic control.
- [ ] Test OPEN, wait, HALF_OPEN, closing, reopening, and reset using a call counter.
- [ ] Monitor state transitions, rejected calls, probe outcomes, Gateway latency, and queues.

**Resetting the circuit and wait durations** determine whether a system can recover in a controlled manner after a dependency outage. When the breaker sits at the right Spring Integration handler boundary, probes are bounded, real timeouts are enforced, and fallback/error flows are clearly defined, the Gateway and Router, Splitter, and Aggregator branches maintain a consistent message contract throughout OPEN → HALF_OPEN → CLOSED.
