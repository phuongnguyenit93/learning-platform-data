# Diagramming the Execution Chain and Verifying Order with Events

A dependency call in Spring Cloud CircuitBreaker can pass through multiple protection policies: Rate Limiter, Bulkhead, Retry, Circuit Breaker, TimeLimiter, and fallback. Each policy controls a different aspect. However, actual runtime behavior depends not only on which policies are enabled, but also on the order in which layers wrap the call.

For example, placing Bulkhead outside Rate Limiter can cause a call to hold a Bulkhead permit while waiting for permission to send the request. Placing Rate Limiter outside Bulkhead checks quota before acquiring a concurrency slot. Similarly, Circuit Breaker outside Retry typically measures the final outcome of the entire retry sequence; Circuit Breaker inside Retry can record each individual attempt.

Therefore, when designing policy composition, explicitly diagram the call path, identify which layer sees which errors, and verify with event publishers and ordered logs. This lesson presents how to express ordering, predict behavior, and confirm it via events in a Spring Cloud CircuitBreaker application using Resilience4j.

## 1. Why Does Execution Order Matter?

Policies are usually implemented as layers wrapping an underlying call. A layer can check preconditions before calling the inner layer, record outcomes after the inner layer finishes, or convert an error into a substitute result.

The notation:

\[
A(B(C(\text{HTTP})))
\]

is read from outside in as the request enters:

1. A begins processing.
2. A calls B.
3. B calls C.
4. C executes HTTP.
5. Results or errors unwind back through C, B, and then A.

Thus, the outermost layer typically starts first and finishes last. The innermost layer sits closest to HTTP.

For example, the same set of policies in two different orders can yield different statistics:

- **CircuitBreaker(Retry(HTTP))**: Circuit Breaker wraps the entire Retry chain and typically records one final outcome per logical call.
- **Retry(CircuitBreaker(HTTP))**: every Retry attempt passes through Circuit Breaker; each attempt can produce a separate measurement in the sliding window.

This is not merely a syntactic difference. It affects when the circuit opens, how many requests are sent, how many permits are consumed, and how dashboards reflect failures.

## 2. Diagram the Call Path Before Configuring

Before writing YAML or customizers, clarify these questions:

- What is the maximum number of attempts for one logical request?
- Is Rate Limiter checked once or on every attempt?
- For how long does Bulkhead hold a permit?
- Does Circuit Breaker measure the final outcome or each individual attempt?
- Does TimeLimiter span the entire Retry sequence or only each individual call?
- Does Fallback execute inside or outside the Circuit Breaker scope?
- Can local policy errors such as `BulkheadFullException` be miscounted as remote dependency errors?

An illustrative call path:

~~~mermaid
flowchart TD
    A[Request enters service] --> B[Deadline / TimeLimiter]
    B --> C[Circuit Breaker checks state]
    C --> D[Retry orchestrates attempts]
    D --> E[Rate Limiter grants permission]
    E --> F[Bulkhead acquires permit]
    F --> G[HTTP connection pool]
    G --> H[Remote dependency]
    H --> I[Result or exception]
    I --> J[Release permit and publish events]
    J --> K{Retries left and error retryable?}
    K -- Yes --> D
    K -- No --> L[Circuit Breaker records outcome]
    L --> M[Return result or fallback]
~~~

This diagram shows one specific choice: TimeLimiter on the outside, Circuit Breaker wrapping Retry, followed by Rate Limiter and Bulkhead. It is an option for discussion, not a mandatory default order for every starter. A Spring Cloud CircuitBreaker adapter may apply certain modules and decorator orders automatically depending on its implementation, version, and configuration. When exact ordering control is required, verify which chain the actual adapter builds.

## 3. Reading the Order Outside-In and Inside-Out

Given the chain:

\[
\text{TimeLimiter}(
  \text{CircuitBreaker}(
    \text{Retry}(
      \text{RateLimiter}(
        \text{Bulkhead}(\text{HTTP})
      )
    )
  )
)
\]

the request enters in this sequence:

1. TimeLimiter starts the time budget for the entire call.
2. Circuit Breaker checks state and permits or rejects.
3. Retry starts the first attempt.
4. Rate Limiter checks permission to send the request.
5. Bulkhead acquires a concurrency permit.
6. The HTTP client acquires a connection and sends the request.
7. The outcome unwinds back through the layers.
8. If the error is allowed by Retry and attempts remain, Retry starts the next attempt.
9. After Retry finishes, Circuit Breaker records the final outcome.
10. TimeLimiter completes based on result or deadline; on timeout, it emits a timeout signal and may request Future cancellation depending on the API.

In this chain, Rate Limiter and Bulkhead sit inside Retry so they are invoked again for each attempt. Circuit Breaker sits outside Retry so it only observes the final result of the retry sequence. TimeLimiter sits outermost so it bounds total duration, including wait intervals between attempts if the Retry mechanism sits inside the publisher or Future wrapped by TimeLimiter.

## 4. Circuit Breaker Outside Retry or Retry Outside Circuit Breaker?

This is one of the most important decisions when composing the two policies.

### Circuit Breaker Wrapping Retry

\[
\text{CircuitBreaker}(\text{Retry}(\text{HTTP}))
\]

One logical call passes through Circuit Breaker once. Inside, Retry can issue multiple attempts. Circuit Breaker typically sees only the final outcome of the Retry chain.

Example:

- Attempt 1 fails with a connection error.
- Retry waits and executes attempt 2.
- Attempt 2 succeeds.
- Circuit Breaker receives a final outcome of success.

In this approach, one logical request produces one Circuit Breaker measurement despite multiple HTTP attempts. This suits measuring the final success rate callers experience after the Retry policy.

### Retry Wrapping Circuit Breaker

\[
\text{Retry}(\text{CircuitBreaker}(\text{HTTP}))
\]

Each attempt passes through Circuit Breaker. If the first attempt fails, Circuit Breaker records a failure for that attempt. Retry may try again, but the next attempt must ask Circuit Breaker for permission again.

Example:

- Attempt 1 goes through Circuit Breaker and fails.
- Circuit Breaker records a failure.
- Retry starts attempt 2.
- If Circuit Breaker is still CLOSED, attempt 2 is permitted to proceed.
- If the circuit has become OPEN, attempt 2 is rejected with `CallNotPermittedException`.

This makes Circuit Breaker react faster to per-attempt errors, but Retry must be configured not to keep retrying rejections caused by Circuit Breaker being OPEN. Otherwise, retry may simply repeat rejections without sending any more requests to the remote dependency.

| Criterion | CircuitBreaker(Retry(HTTP)) | Retry(CircuitBreaker(HTTP)) |
|---|---|---|
| CB measurements per logical request | Usually one final outcome | Can be one measurement per attempt |
| First attempt fails, next succeeds | CB usually records final success | CB still records first attempt's failure and next attempt's success |
| Speed of CB reaction to per-attempt failures | Depends on final outcomes and thresholds | Can be faster because each attempt is recorded |
| When CB transitions to OPEN between attempts | Inner Retry may still continue per its own logic | Subsequent attempt may hit `CallNotPermittedException` |
| Watch out for | Retry can mask transient errors from CB | Retry must ignore CB rejection errors |

There is no universally right choice for every system. Decide whether you want Circuit Breaker to measure the health of each individual call to the dependency or the probability of successfully completing a logical request after Retry.

## 5. Rate Limiter and Bulkhead: Order Determines When Permits Are Held

The two arrangements:

\[
\text{Bulkhead}(\text{RateLimiter}(\text{HTTP}))
\]

and

\[
\text{RateLimiter}(\text{Bulkhead}(\text{HTTP}))
\]

allow analyzing when resources are acquired.

**Bulkhead outside Rate Limiter**:

1. Request acquires a Bulkhead permit.
2. Request waits or asks Rate Limiter for permission.
3. Only when permitted does the request proceed to the HTTP client.
4. The Bulkhead permit is held throughout both Rate Limiter wait time and HTTP call time.

If Rate Limiter has a long wait timeout, a Bulkhead slot can remain occupied even though the request has not yet been sent to the server.

**Rate Limiter outside Bulkhead**:

1. Request requests Rate Limiter permission.
2. Only after receiving permission does the request acquire a Bulkhead permit.
3. If no Bulkhead permits remain, the request is rejected even though it already consumed a Rate Limiter permit.
4. The request does not hold a Bulkhead permit while waiting on Rate Limiter.

For systems where Rate Limiter waits for permits over an interval, placing Rate Limiter outside Bulkhead generally avoids holding concurrency slots while waiting for quota. However, if Bulkhead rejects after Rate Limiter granted a permit, quota may be consumed even though HTTP was never sent. Evaluate quota policy and admission-control behavior together.

If Rate Limiter is configured to reject immediately when permits are exhausted, wait time is negligible and the difference in permit hold time shrinks. Still inspect events to verify whether requests entered Bulkhead.

## 6. TimeLimiter Wrapping the Whole Chain or Each Attempt?

TimeLimiter can be placed outside Retry or inside Retry. The two choices establish different deadlines.

### TimeLimiter Outside Retry

\[
\text{TimeLimiter}(\text{Retry}(\text{HTTP}))
\]

The deadline spans the entire logical request. For example, `timeoutDuration` is 3 seconds, Retry allows two attempts, and `waitDuration` is 500 milliseconds. Total time across attempts and waits must still stay within 3 seconds. If the deadline is exceeded, the caller receives a timeout even if Retry has not finished.

This is usually appropriate when the caller has a fixed business deadline.

### TimeLimiter Inside Retry

\[
\text{Retry}(\text{TimeLimiter}(\text{HTTP}))
\]

Each attempt can receive its own timeout. If each attempt may wait 3 seconds and Retry allows three attempts, total time could approach 9 seconds plus wait intervals between attempts. This can exceed the upstream request's deadline.

| Placement | Timeout scope | Impact |
|---|---|---|
| TimeLimiter(Retry(HTTP)) | Entire Retry chain | Enforces one overall budget |
| Retry(TimeLimiter(HTTP)) | Each attempt | Total time can multiply by attempt count |

Distinguish caller timeout from whether the HTTP task actually stops. When TimeLimiter expires, cancellation depends on the `Future`, `CompletionStage`, or publisher wrapped by the adapter. Placing TimeLimiter outside Retry does not automatically guarantee that every previously sent request stops executing on the server.

## 7. Where Does Fallback Sit in the Chain?

Fallback can change what outer layers observe. For example:

\[
\text{CircuitBreaker}(\text{Fallback}(\text{HTTP}))
\]

If Fallback turns an exception into a normal value before the result returns to Circuit Breaker, Circuit Breaker may record a success. This hides the dependency's failure rate.

Conversely:

\[
\text{Fallback}(\text{CircuitBreaker}(\text{HTTP}))
\]

Circuit Breaker can record the failure before fallback converts the error into a degraded response for the caller. This is usually the goal when you want fallback to serve users while keeping metrics accurate about dependency outages.

In Spring Cloud CircuitBreaker's API, fallback is typically passed as an error handler to `run`. The adapter is responsible for applying fallback per its contract. When using decorators or manually composing publishers, verify which layer applies fallback and whether Circuit Breaker recorded the failure before fallback emitted a substitute value.

Track fallback counts separately. A request returning HTTP 200 via cached data does not necessarily mean the dependency is healthy.

## 8. Build an Event Prediction Table Before Running

Before running tests, write down which events are expected to appear and which layer emits them.

| Layer | Events to observe | Meaning |
|---|---|---|
| Rate Limiter | Permission granted or request rejected | Whether the request was allowed to proceed under quota |
| Bulkhead | Permit acquired, rejected, or released | Actual concurrency level |
| HTTP client | Request started, response, or connection error | Whether the call actually reached transport |
| Retry | Attempt retried, succeeded, or exhausted | Actual number of calls made |
| Circuit Breaker | Call permitted, success, error, not permitted, state transition | Breaker decisions and statistics |
| TimeLimiter | Success, error, or timeout | Wait duration of the entire wrapped scope |
| Fallback | Fallback started and finished | Caller received an alternative result |

Specific event names can vary across Resilience4j versions. Use each module's event publisher to observe the event types provided by the running version. Do not assume an event exists merely from a label on a dashboard.

## 9. Registering Event Publishers to Record Ordering

Resilience4j exposes event publishers on components such as `CircuitBreaker`, `Retry`, `Bulkhead`, `RateLimiter`, and `TimeLimiter`. You can register consumers to log event type, timestamp, request ID, and instance name.

Illustrative example:

~~~java
import java.util.concurrent.atomic.AtomicLong;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.timelimiter.TimeLimiter;

public class PolicyEventLogger {

    private final AtomicLong sequence = new AtomicLong();

    public void observe(
            CircuitBreaker circuitBreaker,
            Retry retry,
            Bulkhead bulkhead,
            RateLimiter rateLimiter,
            TimeLimiter timeLimiter) {

        circuitBreaker.getEventPublisher().onEvent(event ->
                log("CB", event.getEventType().toString()));

        retry.getEventPublisher().onEvent(event ->
                log("RETRY", event.getEventType().toString()));

        bulkhead.getEventPublisher().onEvent(event ->
                log("BULKHEAD", event.getEventType().toString()));

        rateLimiter.getEventPublisher().onEvent(event ->
                log("RATE_LIMITER", event.getEventType().toString()));

        timeLimiter.getEventPublisher().onEvent(event ->
                log("TIME_LIMITER", event.getEventType().toString()));
    }

    private void log(String layer, String event) {
        long order = sequence.incrementAndGet();
        System.out.printf("%d layer=%s event=%s%n", order, layer, event);
    }
}
~~~

This snippet illustrates registering listeners. Constructors, event publisher types, and event sets may differ by Resilience4j version; use the API of your actual dependency. Under concurrent execution, a global sequence can interleave events from multiple requests. Attach a correlation ID or operation ID to logs to filter events belonging to a single request.

To verify whether HTTP was actually invoked, add logging at the HTTP client boundary:

~~~java
Mono<Inventory> remoteCall = Mono.defer(() -> {
    log.info("HTTP_START operationId={}", operationId);

    return webClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(Inventory.class)
            .doFinally(signal ->
                    log.info("HTTP_END operationId={} signal={}",
                            operationId, signal));
});
~~~

`HTTP_START` proves the publisher reached the request-creation layer. `HTTP_END` indicates the publisher terminated with complete, error, or cancel. It does not prove the server stopped processing; verifying that requires correlation on the server side.

## 10. Reading a Sample Event Trace

Suppose the chosen configuration is:

\[
\text{TimeLimiter}(
\text{CircuitBreaker}(
\text{Retry}(
\text{RateLimiter}(
\text{Bulkhead}(\text{HTTP})
))))
\]

A first attempt hits a connection error, and the second attempt succeeds. An illustrative event log might look like:

~~~text
001 TIME_LIMITER  execution_started
002 CIRCUIT_BREAKER call_permitted
003 RATE_LIMITER  permission_acquired
004 BULKHEAD      call_permitted
005 HTTP          request_started
006 HTTP          request_error: connection_reset
007 BULKHEAD      call_finished
008 RETRY         retry_scheduled: attempt=2
009 RATE_LIMITER  permission_acquired
010 BULKHEAD      call_permitted
011 HTTP          request_started
012 HTTP          response_received: 200
013 BULKHEAD      call_finished
014 RETRY         success
015 CIRCUIT_BREAKER success
016 TIME_LIMITER  success
~~~

The names here are illustrative labels to explain the trace; actual event types must be taken from the running version. Ordering may differ at points such as start events, completion callbacks, schedulers, or how adapters emit events. What you need to verify are the causal relationships:

- Does each attempt pass through Rate Limiter and Bulkhead?
- Is Bulkhead released after each attempt?
- Does Retry start a new attempt after an error?
- Does Circuit Breaker record only one final outcome?
- Does TimeLimiter span the entire Retry wait duration?

Do not use a single sample trace to assert an absolute event sequence for every adapter. Compare actual logs against the designed call path.

## 11. Designing Verification Scenarios

A test that only exercises a successful request is insufficient to verify policy composition. Create scenarios with predictable outcomes.

| Scenario | Simulated condition | What to verify |
|---|---|---|
| Immediate success | Dependency returns 200 quickly | One HTTP attempt; permit released; CB records success |
| Error then Retry succeeds | Attempt 1 fails, attempt 2 returns 200 | Retry event appears; HTTP requests equal two; CB records one or two outcomes per placement |
| Rate Limiter exhausted | No permissions left | Request does not reach HTTP; quota rejection event appears |
| Bulkhead full | All permits are held | Request is rejected or waits; HTTP does not start if rejected |
| Circuit Breaker OPEN | CB forced or tripped to OPEN | CallNotPermitted; no `HTTP_START` |
| Timeout | Dependency slower than deadline | TimeLimiter times out; verify cancellation and permit release timing |
| Fallback | Primary call fails or is rejected | Fallback runs; CB metrics still reflect failures per fallback position |
| Retry hits CB OPEN | CB opens between attempts | Next attempt is rejected; whether Retry ignores `CallNotPermitted` |

Use a mock dependency or test HTTP server whose responses, latency, and connection errors you can control. Give each scenario a distinct operation ID to correlate logs and events.

## 12. Example Verifying Circuit Breaker Outside Retry vs. Retry Outside Circuit Breaker

Suppose Retry permits two attempts, where the first attempt fails and the second succeeds.

**Case A — Circuit Breaker outside Retry**

~~~text
Request
  -> CircuitBreaker: permitted
      -> Retry: attempt 1
          -> HTTP: connection error
      -> Retry: attempt 2
          -> HTTP: 200 OK
  -> CircuitBreaker: success
~~~

Expectations:

- There are two HTTP requests.
- Retry records one retry.
- Circuit Breaker records a final outcome of success.
- Circuit Breaker's failure rate does not increase because the first attempt was recovered by Retry.

**Case B — Retry outside Circuit Breaker**

~~~text
Request
  -> Retry: attempt 1
      -> CircuitBreaker: permitted
          -> HTTP: connection error
      -> CircuitBreaker: error
  -> Retry: attempt 2
      -> CircuitBreaker: permitted
          -> HTTP: 200 OK
      -> CircuitBreaker: success
~~~

Expectations:

- There are two HTTP requests if the second attempt is permitted.
- Circuit Breaker records one error and one success.
- Retry records one retry.
- Circuit Breaker's failure rate reflects per-attempt errors.

If the first error causes Circuit Breaker to transition to OPEN, the second attempt can receive `CallNotPermittedException`. In that case, Retry configuration must explicitly decide whether to retry this exception. Usually, you should not repeat a call simply because Circuit Breaker is rejecting it.

## 13. Verifying Bulkhead and Rate Limiter Order via Events

To verify admission-control ordering, create a scenario where Rate Limiter must wait for permission while Bulkhead has only a single permit.

If the chain is:

\[
\text{Bulkhead}(\text{RateLimiter}(\text{HTTP}))
\]

expected events:

1. Bulkhead grants a permit.
2. Rate Limiter begins waiting for permission.
3. The Bulkhead permit remains held.
4. Only after permission is granted or Rate Limiter times out does Bulkhead release the permit.

If the chain is:

\[
\text{RateLimiter}(\text{Bulkhead}(\text{HTTP}))
\]

expected events:

1. Rate Limiter waits and grants permission.
2. Bulkhead grants a permit afterward.
3. If Bulkhead rejects, HTTP does not start, yet the Rate Limiter permission may already have been consumed.

From events and metrics, observe:

- Timestamp when the Bulkhead permit is granted.
- Duration from permit acquisition to `HTTP_START`.
- Number of Rate Limiter rejections.
- Number of Bulkhead rejections.
- Average and p95 permit hold duration.

If permit hold time increases while `HTTP_START` does not increase correspondingly, requests may be waiting at a layer inside Bulkhead such as Rate Limiter or the connection pool.

## 14. Caveats When Reading Events

Event publishers help observe individual policy behavior, but they do not replace distributed tracing. A single Circuit Breaker event does not contain the entire request call path. Attach a correlation ID or operation ID to logs across layers.

Several caveats:

- Events can fire at slightly different times depending on implementation and scheduler.
- One request can emit multiple events of the same type, especially when Retry is involved.
- Bulkhead events can appear both when acquiring a permit and when finishing a call.
- A Rate Limiter event shows whether permission was granted or denied, not whether an HTTP request was actually sent.
- A Circuit Breaker event reflects outcomes observed at the Circuit Breaker layer, not necessarily each response if Retry sits inside.
- A TimeLimiter timeout does not prove the server-side HTTP task stopped.
- Fallback events should be logged separately if you want to distinguish remote responses from degraded responses.

Do not rely solely on event counts to infer HTTP request counts. Add logging in the HTTP client or count requests at the test server to cross-check.

## 15. Design and Verification Checklist

Before promoting a policy composition to production, confirm:

1. The call path is clearly documented from the outer layer down to HTTP and back.
2. Circuit Breaker's position relative to Retry matches statistical goals.
3. Rate Limiter and Bulkhead are ordered appropriately for permit hold times.
4. TimeLimiter covers the intended deadline scope: full logical request or each attempt.
5. Retry retries only appropriate errors and ignores rejections from local policies.
6. Fallback does not hide dependency failures in Circuit Breaker metrics.
7. Bulkhead permits and HTTP connections are released on complete, error, or cancel.
8. Event publishers are registered for every policy and logs include a correlation ID.
9. `HTTP_START`/`HTTP_END` are cross-checked against attempt counts and Retry events.
10. Success, error, timeout, rejection, and fallback scenarios have all been verified.

## 16. Implementation Workflow

When building or modifying policy ordering in Spring Cloud CircuitBreaker with Resilience4j, follow this sequence:

1. Define the objective of each policy and the protected dependency.
2. Write out the call path in nested notation, e.g., `TimeLimiter(CircuitBreaker(Retry(RateLimiter(Bulkhead(HTTP)))))`.
3. Document which layer starts first, which layer sees each attempt, and which layer records the final outcome.
4. Define timeout scope, permit hold duration, and fallback placement.
5. Inspect how the actual starter or adapter creates decorators; never assume automatic ordering without verifying.
6. Register event publishers for Circuit Breaker, Retry, Bulkhead, Rate Limiter, and TimeLimiter.
7. Add HTTP logging at the client boundary, correlation ID, and operation ID.
8. Run each verification scenario against pre-recorded expected outcomes.
9. Compare events, HTTP attempt counts, metrics, and final states.
10. Adjust ordering or exception predicates if events reveal local errors being miscounted as remote errors.

Diagramming the execution chain makes it clear which policy holds resources, which policy sees errors, and which scope is timed. Event publishers alongside HTTP client logs provide runtime evidence to verify that chain. By explicitly defining the order of Retry, Circuit Breaker, Rate Limiter, Bulkhead, TimeLimiter, and fallback, teams can explain why a request was rejected, retried, timed out, or served a degraded result, while keeping operational metrics faithful to dependency behavior.
