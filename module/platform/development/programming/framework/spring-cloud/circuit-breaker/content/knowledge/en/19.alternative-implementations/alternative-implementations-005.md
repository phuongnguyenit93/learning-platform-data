# Distinguishing Spring Retry Semantics from Resilience4j's Failure-Rate Window

Both Spring Retry and Resilience4j Circuit Breaker can help an application tolerate transient failures in a dependent service, but they observe different things. Spring Retry decides whether to re-execute an operation within the same invocation. Resilience4j Circuit Breaker observes the outcomes of multiple calls across a sliding window, calculates the failure rate or slow-call rate, and decides whether subsequent calls should be allowed through.

When implementing **SPRING_CLOUD_CIRCUIT_BREAKER**, you need to distinguish these two semantics clearly. Retry can help get past a transient glitch; Circuit Breaker helps stop sending further requests when a dependency is degraded. Using retry does not mean you have a Circuit Breaker, and enabling a Circuit Breaker does not automatically perform retries.

## 1. Two Mechanisms Answering Two Different Questions

| Aspect | Spring Retry | Resilience4j Circuit Breaker |
| --- | --- | --- |
| Primary question | Should the operation that just failed be attempted again? | Should a new call to the dependency be permitted? |
| Observation scope | Attempts of a single logical operation | Outcomes of multiple calls within a window |
| Decision unit | One call that may contain multiple attempts | One call recorded as success, failure, or slow |
| Stopping condition | Attempts exhausted, non-retryable error encountered, or policy denies further attempts | Circuit transitions to OPEN when the rate hits threshold; only controlled probing in HALF_OPEN |
| Wait period | Backoff between attempts | Duration spent in OPEN before allowing recovery probes |
| Final response | Result from a successful attempt or recover method when retries are exhausted | Call result, fallback, or rejection error due to OPEN circuit |

For example, the Order service calls the Inventory service. One request hits a transient connection error. Spring Retry can retry that request twice more. If all three attempts fail, the operation ends with an error or a recover method. Resilience4j Circuit Breaker does not resend the request itself; it records the outcome and can open the circuit once enough samples accumulate in the sliding window.

## 2. Spring Retry: Attempts Within a Single Call

Spring Retry provides abstractions such as `RetryTemplate`, `RetryPolicy`, `BackOffPolicy`, and the `@Retryable` annotation. A policy specifies which exceptions are retried and when to stop. Backoff specifies the wait interval between attempts.

With annotations, you can configure attempt counts and backoff:

~~~java
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Recover;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class InventoryClientService {
    @Retryable(
            retryFor = InventoryUnavailableException.class,
            noRetryFor = InventoryNotFoundException.class,
            maxAttempts = 3,
            backoff = @Backoff(
                    delay = 200,
                    multiplier = 2.0,
                    maxDelay = 1000
            )
    )
    public InventoryResult getInventory(String sku) {
        return inventoryClient.get(sku);
    }

    @Recover
    public InventoryResult recover(
            InventoryUnavailableException failure,
            String sku) {
        return InventoryResult.unavailable(sku);
    }
}
~~~

This example requires enabling annotation processing with `@EnableRetry` in Spring configuration and having a Spring Retry dependency compatible with the Spring version in use. `InventoryClient`, `InventoryResult`, and the exceptions are illustrative domain types.

Key points to understand:

- `maxAttempts = 3` includes the first call, meaning three attempts in total, not three retries on top of the initial call.
- `retryFor` specifies exceptions permitted for retry.
- `noRetryFor` excludes errors that should not be retried, such as a nonexistent SKU.
- `@Backoff` sets the wait interval between attempts; with multiplier 2, the wait grows exponentially up to `maxDelay`.
- Once attempts are exhausted, Spring Retry looks for a matching `@Recover` method if present. If no matching recover method exists, the last exception is propagated.

Retry fits transient errors that can self-recover, such as brief connection drops or 503 responses. Do not retry every exception. Bad input, authorization errors, or non-idempotent operations can cause side effects if executed again.

With Spring proxy-based annotations, self-invocation from one method to another `@Retryable` method on the same object usually bypasses the proxy. Invoke through a Spring-managed bean or use `RetryTemplate` when explicit control at the call site is needed.

## 3. RetryTemplate Representing the Retry Loop

When you want programmatic control over retries, use `RetryTemplate`:

~~~java
import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;

RetryTemplate retryTemplate = new RetryTemplate();

SimpleRetryPolicy retryPolicy = new SimpleRetryPolicy(
        3,
        Map.of(InventoryUnavailableException.class, true)
);
retryTemplate.setRetryPolicy(retryPolicy);

ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
backOff.setInitialInterval(200);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(1000);
retryTemplate.setBackOffPolicy(backOff);

InventoryResult result = retryTemplate.execute(
        context -> inventoryClient.get(sku),
        context -> InventoryResult.unavailable(sku)
);
~~~

In this example, the retry policy permits up to three attempts for `InventoryUnavailableException`; backoff increases the wait interval between attempts. The second callback is the recovery callback used when retries are exhausted. In practice, configuration should be created and managed as a shared bean rather than instantiated on every request.

RetryTemplate manages the retry state of the current operation. It does not by default maintain a sliding window of outcomes across multiple requests to compute a failure rate like Resilience4j Circuit Breaker.

## 4. Resilience4j Circuit Breaker: Rates Over a Sliding Window

Resilience4j Circuit Breaker records the outcomes of protected calls. The sliding window can be based on call count or time duration:

| Window Type | Meaning |
| --- | --- |
| `COUNT_BASED` | Tracks the most recent N calls |
| `TIME_BASED` | Tracks outcomes over the most recent time interval |

Configuration example:

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
        permittedNumberOfCallsInHalfOpenState: 3
~~~

In this configuration:

- `slidingWindowSize: 20` tracks up to the 20 most recent calls.
- `minimumNumberOfCalls: 10` requires at least 10 outcomes before computing rates.
- `failureRateThreshold: 50` sets the threshold to open the circuit when the failure rate reaches 50% or higher once enough samples are collected.
- `slowCallDurationThreshold: 2s` defines a slow call.
- `slowCallRateThreshold: 60` sets the slow-call rate threshold.
- `waitDurationInOpenState: 10s` is the wait duration in OPEN before allowing recovery checks.
- `permittedNumberOfCallsInHalfOpenState: 3` caps test calls in HALF_OPEN.

For example, once 10 calls have been recorded, if 5 calls fail, the failure rate is 50%. The circuit can transition from CLOSED to OPEN. If 4 calls fail and 2 slow calls succeed, the failure rate is 40% and the slow-call rate is 20%; both rates are evaluated separately against their configured thresholds.

Resilience4j Circuit Breaker does not re-execute a call when an exception occurs. It decides whether to let a new call pass through or reject it fast when the circuit is OPEN. Once the OPEN duration elapses, the circuit transitions to HALF_OPEN to test recovery with a limited number of calls.

## 5. One Request Makes Three Attempts, Yet Circuit Breaker May Record Only One Outcome

An important difference emerges when combining retry with Circuit Breaker. If Retry sits inside Circuit Breaker, the Circuit Breaker wraps the entire retry process. It sees only the final outcome of the logical operation:

~~~mermaid
flowchart TD
    A[One business request] --> B[Circuit Breaker]
    B --> C[Spring Retry]
    C --> D[Attempt 1]
    D -->|Fail| E[Backoff]
    E --> F[Attempt 2]
    F -->|Fail| G[Backoff]
    G --> H[Attempt 3]
    H --> I[Final outcome]
    I --> J[Circuit Breaker records one outcome]
~~~

For example, the first two attempts fail, but the third succeeds. Retry returns the successful result to the Circuit Breaker; the Circuit Breaker records one successful logical call. The two intermediate failures still need to be logged or metered separately if you want visibility into retry quality.

If all three attempts fail, the Circuit Breaker generally records one failed logical call after Retry finishes. Thus, one external request made three HTTP attempts yet contributed a single sample to the Circuit Breaker's window.

This ordering fits when you want the Circuit Breaker to measure the final success rate callers experience after the retry policy runs.

## 6. If Circuit Breaker Sits Inside Retry

If each attempt passes through the Circuit Breaker while Retry wraps the outside, each attempt can be recorded as an individual call:

~~~mermaid
flowchart TD
    A[One business request] --> B[Spring Retry]
    B --> C[Circuit Breaker]
    C --> D[Attempt 1]
    D -->|Fail| E[Retry backoff]
    E --> F[Circuit Breaker]
    F --> G[Attempt 2]
    G -->|Fail| H[Retry backoff]
    H --> I[Circuit Breaker]
    I --> J[Attempt 3]
~~~

In that case, a single business request can contribute multiple failure samples to the sliding window. The circuit can open mid-retry sequence. Subsequent attempts will be rejected with `CallNotPermittedException` if the Circuit Breaker has already transitioned to OPEN.

If Retry also retries `CallNotPermittedException`, it may keep looping while the circuit remains OPEN without giving the dependency any chance to recover. Therefore, configure Retry to handle only appropriate exceptions and exclude Circuit Breaker rejection errors.

This ordering can be useful when you want the Circuit Breaker to react to each actual physical attempt, though it makes window metrics reflect attempts rather than final business request outcomes. Choose intentionally and verify with metrics.

## 7. Comparing with a Numerical Example

Suppose there are 10 business requests. Each request is tried by Spring Retry up to three times. Across the 10 requests:

- 6 requests succeed on the first attempt.
- 2 requests fail on the first attempt but succeed on the second.
- 2 requests fail all three attempts.

The numbers differ depending on wrapping order:

| Wrapping Order | Outcomes Circuit Breaker Can Record | Failures Recorded |
| --- | ---: | ---: |
| Circuit Breaker outside, Retry inside | 10 final outcomes of 10 requests | 2 final failures |
| Retry outside, Circuit Breaker inside | 16 attempts | 8 failed attempts |

The attempt count in the second approach is 6 requests succeeding on attempt one, 4 attempts for the two requests succeeding after one retry, and 6 attempts for the two requests failing completely, totaling 16 attempts. Failed attempts are the 2 initial errors from the two retry-succeeded requests plus 6 errors from the two fully failed requests, totaling 8 failures.

In both approaches, 2 business requests ultimately failed. However, the Circuit Breaker window sees 2/10 failures in the first setup and 8/16 failures in the second. Those rates are 20% and 50%, respectively. This is why wrapping order changes the meaning of the failure rate.

These numbers assume Retry stops as soon as an attempt succeeds and no attempt is rejected by the Circuit Breaker. If the circuit transitions to OPEN mid-sequence, actual executions also depend on how Retry classifies `CallNotPermittedException`.

## 8. Spring Retry Recovery and Circuit Breaker Fallback

Spring Retry uses `@Recover` or `RetryTemplate`'s recovery callback when retries are exhausted. Resilience4j Circuit Breaker can use a fallback when a call fails or is rejected due to an OPEN circuit. The two fallback mechanisms trigger at different points:

| Mechanism | When It Runs | Goal |
| --- | --- | --- |
| Spring Retry `@Recover` | After the retry policy disallows further attempts | Supplies a result or handling once attempts are exhausted |
| Circuit Breaker fallback | When the protected operation throws an error or the circuit rejects the call | Supplies an alternative response while the dependency is failing or tripped |

If Retry sits inside Circuit Breaker, Spring Retry's recovery can turn failed attempts into a normal return value before the Circuit Breaker receives the outcome. In that case, the Circuit Breaker may record a success because recover returned a value. If you want the Circuit Breaker to record the final failure, let the exception propagate out of Retry or design recovery to preserve the appropriate failure signal.

Avoid letting both fallback layers silently return a default value without recording the cause. Otherwise, dashboards can show APIs succeeding even while the dependent service is continuously failing and every request is served from fallback data.

## 9. Spring Retry Does Not Replace a Sliding Window

Spring Retry primarily decides whether to reattempt an operation based on that operation's policy and context. A retry policy typically limits attempt counts, retryable exception types, and backoff intervals. It does not by default compute the failure rate of the last 20 calls or the slow-call rate over 10 seconds like Resilience4j Circuit Breaker.

Some Spring Retry versions include a policy named Circuit Breaker to block attempts for a duration after failure. However, you should not equate that policy's mechanism with Resilience4j's sliding-window failure-rate model. Read the exact API and semantics of the version you use rather than inferring from the name.

If the requirement is:

- Retry up to three times on a brief connection error: use Spring Retry or Resilience4j Retry.
- Open the circuit when at least 50% of the last 20 calls fail: use Resilience4j Circuit Breaker with a COUNT_BASED sliding window.
- Open the circuit when the slow-call rate over 10 seconds exceeds a threshold: use a TIME_BASED sliding window and configure slow-call thresholds.
- Both retry transient errors and stop calling during sustained dependency degradation: combine Retry and Circuit Breaker with explicit ordering, timeouts, and exception classification.

## 10. Choosing Which Errors to Retry and Which to Record

Retry and Circuit Breaker need a consistent exception policy:

| Error Type | Spring Retry | Resilience4j Circuit Breaker |
| --- | --- | --- |
| Transient connection error | Can retry with bounded count and backoff | Records failure unless the exception is ignored |
| HTTP 503 | Can retry if the dependency can recover quickly | Typically recorded as a dependency failure |
| HTTP 404 due to missing resource | Usually do not retry | Can be ignored if it is a normal business outcome |
| HTTP 400 due to bad request | Do not retry | Usually ignored so it does not inflate dependency failure rate |
| Timeout | Can retry if operation is safe and time budget remains | Usually recorded as failure or slow call depending on completion time |
| CallNotPermittedException | Should not retry | Signal that Circuit Breaker is OPEN, not a new dependency failure |
| BulkheadFullException or RequestNotPermitted | Should not retry immediately when internal limits are full | Usually ignored in dependency failure rate and tracked separately |

Do not retry non-idempotent write operations without an idempotency key or duplicate-handling guard. For instance, a timeout when submitting a payment command does not prove the transaction was not processed; retrying can create a duplicate transaction.

## 11. Time Budget and Attempt Counts

Retries increase completion time because each attempt can consume call duration plus backoff. If one attempt times out after 1 second and you retry up to three attempts, total time can exceed 3 seconds once backoff is included. Calculate the overall budget:

$$
T_{total} \approx \sum_{i=1}^{n} T_{attempt_i}
 + \sum_{i=1}^{n-1} T_{backoff_i}
$$

This total time must fit within the external request's deadline. Do not set the API timeout shorter than the expected total retry duration, or the client may give up while attempts keep running.

Circuit Breaker also needs to coordinate with timeouts. If a dependency hangs indefinitely, the Circuit Breaker cannot observe an incomplete call's outcome to update its window. Set timeouts on the HTTP client or TimeLimiter so operations terminate and emit an observable failure outcome.

When the circuit is OPEN, do not let Retry keep hitting the same dependency. Exclude `CallNotPermittedException` from the retryable list and let the Circuit Breaker reject fast. Retries should apply only to errors recoverable within the time budget.

## 12. Workflow for Combining Spring Retry and Resilience4j

When a dependency needs both retry and circuit breaker, follow these steps:

1. Identify which transient errors can be retried and which business errors must return immediately.
2. Choose maximum attempts, backoff, and timeouts so they fit inside the request deadline.
3. Choose a COUNT_BASED or TIME_BASED sliding window for the Circuit Breaker based on traffic patterns.
4. Decide whether the Circuit Breaker measures a request's final outcome or each attempt by choosing the wrapping order.
5. If Retry is inside Circuit Breaker, decide whether recovery converts the final error into a normal result.
6. If Circuit Breaker is inside Retry, exclude `CallNotPermittedException` from retries to avoid retrying while OPEN.
7. Classify errors from Rate Limiter and Bulkhead so internal overload is not mistaken for dependency failure.
8. Track business requests, attempts, per-attempt errors, failure rate, slow-call rate, and fallback counts separately.
9. Test success after retry, exhausted retries, OPEN circuit, timeouts, and HALF_OPEN recovery.

Spring Retry and Resilience4j Circuit Breaker can work together, but they do not share the same semantics. Retry governs attempts within one operation; Circuit Breaker uses a sliding window to assess dependency health across many calls. Choosing the right order and exception policy helps the system weather transient errors while stopping load when a service genuinely degrades.
