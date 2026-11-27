# How Circuit Breaker and Retry Wrapping Order Changes Statistical Samples

When a dependent service encounters a transient error, Retry can re-invoke it to increase the chance of success. Circuit Breaker monitors call outcomes and trips the circuit when a dependency shows signs of being unhealthy. These two policies are often combined, but the wrapping order around the call determines whether Circuit Breaker sees each individual attempt or sees the final outcome of the entire retry sequence.

There are two common nesting approaches:

- **Retry on the outside, Circuit Breaker on the inside:** each attempt goes through Circuit Breaker. Circuit Breaker records each attempt.
- **Circuit Breaker on the outside, Retry on the inside:** Circuit Breaker wraps the entire retry sequence. It records a single final outcome for each logical request.

This difference directly affects the sample count in the sliding window, failure rate, slow-call rate, when the circuit opens, and the amount of load sent to the dependency. This lesson explains both orders, illustrates them with Resilience4j, and shows how to choose the appropriate policy in Spring Cloud.

## 1. Roles of Retry and Circuit Breaker

Retry and Circuit Breaker solve two different problems.

**Retry** re-executes a call when encountering an error considered recoverable. Examples include temporary connection errors or HTTP 503 over a short period. Retry typically has a limit on the number of attempts, a wait duration between attempts, and conditions defining which exceptions are retried.

**Circuit Breaker** monitors calls passing through it. When the failure rate or slow-call rate in the sliding window exceeds the threshold and the minimum number of calls is met, it transitions to OPEN to reject new calls. After a wait duration, it can transition to HALF_OPEN to probe the dependency.

They can be distinguished by the question each answers:

| Policy | Primary Question |
| --- | --- |
| Retry | Is this error worth retrying, and at most how many times should it be tried? |
| Circuit Breaker | Given the recent state of the dependency, should we continue sending calls? |

Retry can help overcome temporary errors. However, if the dependency is experiencing a prolonged outage, many requests retrying simultaneously can amplify load. Circuit Breaker limits continued calls when evidence indicates the dependency is unhealthy.

## 2. Wrapping Order Determines the Unit Being Measured

Consider each business request as one logical call. That request may generate one or more attempts to Inventory.

~~~text
One logical request
       |
       v
      Retry
       |
       +---- attempt 1
       |        |
       |        v
       |   Circuit Breaker
       |        |
       |        v
       |   Inventory
       |
       +---- attempt 2
       |        |
       |        v
       |   Circuit Breaker
       |        |
       |        v
       |   Inventory
       |
       +---- attempt 3 ...
~~~

The diagram above illustrates Retry on the outside and Circuit Breaker on the inside. Each attempt goes through Circuit Breaker, so each attempt outcome can become a sample in the sliding window.

If the order is reversed:

~~~text
One logical request
       |
       v
Circuit Breaker
       |
       v
      Retry
       |
       +---- attempt 1 ---> Inventory
       |
       +---- attempt 2 ---> Inventory
       |
       +---- attempt 3 ---> Inventory
       |
       v
Final outcome of Retry
~~~

Circuit Breaker only receives the outcome after Retry completes. The three internal attempts are treated as a single execution of the protected supplier. If one attempt fails but a subsequent attempt succeeds, Circuit Breaker receives a success outcome.

## 3. Retry on the Outside, Circuit Breaker on the Inside

This nesting takes the form:

~~~java
Supplier<Inventory> protectedAttempt =
    CircuitBreaker.decorateSupplier(circuitBreaker, inventoryClient::getInventory);

Supplier<Inventory> retriedCall =
    Retry.decorateSupplier(retry, protectedAttempt);

Inventory result = retriedCall.get();
~~~

Retry invokes the protected supplier multiple times. Each time Retry executes a new attempt, the inner supplier passes through Circuit Breaker again.

### 3.1. Circuit Breaker Records Each Attempt

Suppose Retry allows up to 3 attempts and every attempt fails:

| Logical request | Attempt | Outcome recorded by Circuit Breaker |
| --- | ---: | --- |
| Request A | 1 | Failure |
| Request A | 2 | Failure |
| Request A | 3 | Failure |
| Request B | 1 | Failure |
| Request B | 2 | Failure |
| Request B | 3 | Failure |

Just two logical requests have produced six failure samples in the sliding window. If the window size is 10 and `minimumNumberOfCalls` is 5, Circuit Breaker can reach enough samples after part of the second request, depending on timing and specific outcomes.

This makes Circuit Breaker react faster to repeated errors at the attempt level. It also means a single business request can contribute multiple samples to the same window.

### 3.2. Advantages and Limitations

Advantages:

- Circuit Breaker sees every call to the dependency, including errors later recovered by Retry.
- The failure rate reflects the error level per attempt.
- A continuous streak of failures can cause Circuit Breaker to open early.

Limitations:

- One logical request can generate multiple samples, so the sliding window no longer corresponds to the number of user requests.
- When Circuit Breaker transitions to OPEN after a failed attempt, the next attempt may be rejected with `CallNotPermittedException`.
- If Retry keeps retrying `CallNotPermittedException`, it only repeats a call already blocked by Circuit Breaker and adds useless latency.

When using this order, Retry must be configured to ignore `CallNotPermittedException`. This is an error from the caller-side protection mechanism, not a transient error to be sent back to the dependency.

## 4. Circuit Breaker on the Outside, Retry on the Inside

This nesting takes the form:

~~~java
Supplier<Inventory> retriedCall =
    Retry.decorateSupplier(retry, inventoryClient::getInventory);

Supplier<Inventory> protectedRequest =
    CircuitBreaker.decorateSupplier(circuitBreaker, retriedCall);

Inventory result = protectedRequest.get();
~~~

Circuit Breaker invokes Retry once. Retry executes the attempts inside and returns the final result or throws an exception after exhausting all attempts. Circuit Breaker only records that final outcome.

### 4.1. Circuit Breaker Records One Outcome per Logical Request

Suppose Retry allows up to 3 attempts:

| Logical request | Attempts | Outcome returned by Retry | Circuit Breaker sample |
| --- | --- | --- | --- |
| Request A | Failure, Success | Success | Success |
| Request B | Failure, Failure, Success | Success | Success |
| Request C | Failure, Failure, Failure | Failure | Failure |

Even though the dependency returned multiple errors on initial attempts, Circuit Breaker only records one success sample for Request A and Request B. Request C creates one failure sample after Retry runs out of attempts.

This causes Circuit Breaker's failure rate to reflect the rate of logical requests that ultimately could not complete after retries, rather than the failed attempt rate.

### 4.2. Advantages and Limitations

Advantages:

- The sliding window aligns closely with the number of logical requests that the calling layer cares about.
- A transient error recovered by Retry does not increase Circuit Breaker's failure rate.
- Circuit Breaker only opens when the entire retry sequence still fails or is slow.

Limitations:

- Circuit Breaker can react more slowly because it must wait for Retry to finish before getting a single sample.
- Errors on initial attempts do not appear in Circuit Breaker's failure rate; Retry metrics or logs are needed for visibility.
- The execution time of the supplier inside Circuit Breaker includes all attempts and the wait durations between them.

If Retry has a long backoff, an outer Circuit Breaker may classify a request as a slow call even if each individual HTTP attempt was fast. This can be desirable behavior if the goal is to protect logical request latency.

## 5. Comparing the Impact on the Sliding Window

Consider a Circuit Breaker configuration with:

- `slidingWindowType` is `COUNT_BASED`.
- `slidingWindowSize` is 10.
- `minimumNumberOfCalls` is 5.
- `failureRateThreshold` is 50%.

Suppose each logical request has at most 3 attempts and all three attempts fail.

| Nesting approach | Circuit Breaker samples after 2 logical requests | Failure rate | Meaning |
| --- | ---: | ---: | --- |
| Retry outside, Circuit Breaker inside | Can reach 6 failure samples if all attempts are permitted to run | 100% | Evaluates errors per attempt |
| Circuit Breaker outside, Retry inside | 2 failure samples | 100% | Evaluates errors per logical request |

In the example, the failure rate is 100% in both cases, but the sample counts differ. With `minimumNumberOfCalls` equal to 5, the first approach can reach enough samples to evaluate in fewer than two logical requests; the second approach needs at least five logical requests if each request produces one sample.

If the first attempt fails and the second attempt succeeds:

- Retry outside, Circuit Breaker inside records one failure and one success.
- Circuit Breaker outside, Retry inside records one success.

This is the core difference. The exact same dependency behavior can produce different failure rates simply because the policy wrapping order changed.

## 6. Slow-Call Rate Is Also Affected

Circuit Breaker can evaluate both failure rate and slow-call rate. The wrapping order affects the duration that Circuit Breaker measures.

**Retry outside, Circuit Breaker inside:**

- Each attempt is measured separately.
- Backoff time sits between calls and is not included in the duration of each supplier protected by Circuit Breaker.
- A fast but failed attempt can still be a failure; a slow attempt can be counted as a slow call.

**Circuit Breaker outside, Retry inside:**

- Circuit Breaker measures the total time Retry takes to execute.
- The duration of the attempts plus the backoff duration falls within one protected execution.
- A request can be considered a slow call even when every individual attempt is below `slowCallDurationThreshold`.

Example:

- Each HTTP call takes 300 ms.
- Retry has 3 attempts.
- Between attempts there are two wait intervals, each 400 ms.

The total time of the Retry sequence is approximately:

\[
3 \times 300\text{ ms} + 2 \times 400\text{ ms}
= 1{,}700\text{ ms}
\]

If `slowCallDurationThreshold` is 1 second:

- When Circuit Breaker is inside Retry, each 300 ms attempt is not considered a slow call.
- When Circuit Breaker wraps outside Retry, the entire sequence of about 1.7 seconds can be considered one slow call.

Therefore, you must decide whether the statistical target is the latency of a single network call or the latency a business request actually has to wait for.

## 7. Controlled Retry Configuration

Not every exception should be retried. Retry should only be applied to recoverable errors and operations that are safe to execute multiple times.

Example Resilience4j configuration:

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 200ms
        enableExponentialBackoff: true
        exponentialBackoffMultiplier: 2
        retryExceptions:
          - org.springframework.web.client.ResourceAccessException
          - org.springframework.web.client.HttpServerErrorException
        ignoreExceptions:
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException

  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

The values are only examples for a practice environment. `maxAttempts` usually counts the initial call as well, so a value of 3 corresponds to at most three attempts, not one call plus three retries.

Points to note:

- `ResourceAccessException` can represent network access errors or timeouts in a Spring HTTP client.
- `HttpServerErrorException` represents HTTP 5xx errors; in production, carefully consider which exact statuses can be retried.
- Do not retry 4xx business errors such as invalid data or unauthorized access.
- `CallNotPermittedException` should be ignored in Retry when Circuit Breaker is inside Retry.
- If the API supports `Retry-After`, respect the server's guidance instead of always using a fixed wait interval.

For write operations, submitting payments, or creating orders, only retry when the API has an appropriate idempotency mechanism. Otherwise, the first attempt may already have been processed by the server while the response was lost; retrying could create duplicate transactions.

## 8. Circuit Breaker Configuration and Reading Metrics

Circuit Breaker uses a sliding window to evaluate the outcomes it directly wraps. With `COUNT_BASED`, each completion of the protected supplier contributes one sample. With `TIME_BASED`, outcomes are aggregated by time buckets.

Metrics commonly observed include:

- Number of successful calls.
- Number of failed calls.
- Number of calls rejected due to Circuit Breaker being OPEN.
- Failure rate and slow-call rate.
- Number of state transitions.
- Number of attempts and retry outcomes from Retry metrics.

When Retry is outside Circuit Breaker, the total number of calls recorded by Circuit Breaker can be larger than the number of logical requests. Name dashboards and alerts clearly to avoid interpreting the attempt failure rate as the user request failure rate.

When Circuit Breaker is outside Retry, the Circuit Breaker sample count is close to the number of logical requests. However, Retry metrics are still necessary to see whether the dependency frequently fails on the first attempt. A system with 99% of requests eventually succeeding but frequently needing three attempts may still have stability and latency problems.

Do not look solely at Circuit Breaker's failure rate. Place them side by side:

| Metric | Question it helps answer |
| --- | --- |
| Circuit Breaker failure rate | How many protected executions failed at the chosen boundary? |
| Retry attempts | How many calls did a request need to complete? |
| Retry success after retry | How many initial errors were recovered by retrying? |
| End-to-end latency | How long did the user actually have to wait? |
| Rejected calls | How many calls were rejected by Circuit Breaker? |

## 9. Illustration with Resilience4j Decorators

Resilience4j Decorators can be used to express the order clearly in code. Assume we already have a `CircuitBreaker`, `Retry`, and a supplier calling Inventory:

~~~java
Supplier<InventoryResponse> remoteCall =
    () -> inventoryClient.getInventory("SKU-001");
~~~

### 9.1. Retry Outside, Circuit Breaker Inside

~~~java
Supplier<InventoryResponse> circuitProtectedAttempt =
    CircuitBreaker.decorateSupplier(circuitBreaker, remoteCall);

Supplier<InventoryResponse> retryAroundCircuitBreaker =
    Retry.decorateSupplier(retry, circuitProtectedAttempt);

InventoryResponse result = retryAroundCircuitBreaker.get();
~~~

Reading from outside in: Retry wraps the supplier already protected by Circuit Breaker. Each time Retry invokes the supplier, Circuit Breaker receives one attempt.

### 9.2. Circuit Breaker Outside, Retry Inside

~~~java
Supplier<InventoryResponse> retriedSequence =
    Retry.decorateSupplier(retry, remoteCall);

Supplier<InventoryResponse> circuitAroundRetry =
    CircuitBreaker.decorateSupplier(circuitBreaker, retriedSequence);

InventoryResponse result = circuitAroundRetry.get();
~~~

Reading from outside in: Circuit Breaker wraps the supplier already decorated with Retry. Circuit Breaker receives one outcome after Retry finishes.

Both examples use the same decorator type, but the nesting order differs. When testing, use two separate instance names or reset the application between scenarios so that the sliding window and state from the previous run do not skew observed results.

## 10. Integration in a Spring Cloud Service

Spring Cloud CircuitBreaker provides `CircuitBreakerFactory` to create a Circuit Breaker by name. Retry can be placed inside the call protected by the factory:

~~~java
@Service
public class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RetryRegistry retryRegistry;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RetryRegistry retryRegistry,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.retryRegistry = retryRegistry;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResponse getInventory(String sku) {
        Retry retry = retryRegistry.retry("inventory");

        return circuitBreakerFactory.create("inventory").run(
            () -> retry.executeSupplier(
                () -> inventoryClient.getInventory(sku)
            ),
            error -> InventoryResponse.unavailable(sku)
        );
    }
}
~~~

In this example, Spring Cloud's Circuit Breaker wraps outside the Retry sequence. The protected supplier completes only after Retry returns a result or throws an error. The Circuit Breaker fallback is invoked when the Retry sequence fails or Circuit Breaker rejects the call.

If you want Retry outside Circuit Breaker, each attempt must call into a Circuit Breaker and ensure errors are propagated outward for Retry to evaluate. Do not place a fallback returning a successful value inside each attempt, because Retry will see a successful result and stop even though it was only a fallback.

One way to express this at the Resilience4j level is to use `CircuitBreakerRegistry` and `RetryRegistry` directly with Decorators as shown earlier. When using the Spring Cloud factory, clearly define which layer holds the fallback and which exceptions propagate through each layer.

## 11. Where the Fallback Sits Also Changes Behavior

A fallback is an alternative result when a call fails or is rejected. The fallback's position affects Retry:

- **Fallback inside Retry:** if the fallback turns an exception into a normal value, Retry treats that attempt as successful and does not retry.
- **Fallback outside Retry:** Retry gets a chance to execute all attempts; the fallback only runs after Retry exhausts all attempts and still fails.
- **Circuit Breaker fallback:** if Circuit Breaker is outside Retry, the fallback receives the final error of the Retry sequence or the error from the OPEN state.

Example of what not to do:

~~~java
Supplier<InventoryResponse> attemptWithFallback = () ->
    inventoryClient.getInventory("SKU-001")
        .orElse(InventoryResponse.unavailable("SKU-001"));
~~~

If the function above always returns a valid value even when the dependency fails, Retry cannot know that it needs to retry. Preserve the exception or an error result type recognized by the Retry predicate until Retry completes; only then apply the fallback.

The fallback also needs to distinguish dependency errors from local overload errors or business errors. Avoid turning every exception into a successful response without clearly recording the fallback data state.

## 12. Retry Can Amplify Load

Retry increases the number of calls to a dependency. If multiple layers in a call chain all retry, the number of attempts can multiply.

For example, a request passes through three layers, each allowing up to 3 attempts. In the worst case, the number of calls reaching the final layer can be up to:

\[
3 \times 3 \times 3 = 27
\]

This is why you should designate a single layer responsible for retrying each dependency, limit the number of attempts, use backoff and jitter, and set an overall timeout.

Circuit Breaker inside Retry can observe multiple attempts and open early. However, once OPEN, Retry must stop immediately upon encountering `CallNotPermittedException`. Circuit Breaker outside Retry avoids recording each attempt into the sliding window, but Retry still keeps generating load until the sequence ends or times out.

Both orders need limits. Circuit Breaker does not replace a retry budget, and Retry does not replace Circuit Breaker.

## 13. How to Choose the Right Order

| Goal | Usually suitable order | Reason |
| --- | --- | --- |
| Evaluate dependency health per actual call | Retry outside, Circuit Breaker inside | Every attempt is a sample, including errors recovered by retry |
| Evaluate final failure rate of business requests | Circuit Breaker outside, Retry inside | Each logical request produces one final sample |
| Open the circuit quickly when the dependency continuously fails on each attempt | Retry outside, Circuit Breaker inside | Failure samples grow with the number of attempts |
| Evaluate latency that a request waits for across all retries | Circuit Breaker outside, Retry inside | Circuit Breaker measures both retry and backoff time |
| Track transient errors recovered by retry | Both orders need Retry metrics | Circuit Breaker may not reflect intermediate errors if it wraps outside Retry |

There is no single right order for every system. Choose based on the meaning the operations team wants to assign to failure rate and slow-call rate. If you want statistics per user request, Circuit Breaker outside Retry is usually easier to interpret. If you want statistics per attempt sent to the dependency, place Circuit Breaker inside Retry.

## 14. Scenario to Verify Both Nesting Approaches

You can create a mock supplier with a deterministic sequence of outcomes:

- Attempt 1 fails with a connection error.
- Attempt 2 succeeds.
- The next request fails all three attempts.

Use two separate pairs of Circuit Breaker and Retry to run the same scenario. Record how many times the supplier is called, the Circuit Breaker sample count, the number of retries, and the state after each request.

Expected results:

| Scenario | Retry outside, Circuit Breaker inside | Circuit Breaker outside, Retry inside |
| --- | --- | --- |
| Request where attempt 1 fails, attempt 2 succeeds | Circuit Breaker records one failure and one success | Circuit Breaker records one success |
| Request where all three attempts fail | Circuit Breaker records up to three failures if all three attempts are permitted | Circuit Breaker records one failure |
| Retry extends duration with backoff | Each attempt is measured individually by Circuit Breaker | Total retry time is measured as one call |
| Circuit Breaker is already OPEN | Next attempt is rejected; Retry must ignore `CallNotPermittedException` | Retry supplier is not started because Circuit Breaker rejects from the outside |

When actually running, there may be fewer attempts than expected if Circuit Breaker opens mid-retry sequence or the Retry predicate decides to stop early. That is the very behavior to observe, not a flaw in the test.

## 15. Design Principles

- Determine whether the sliding window should represent attempts or logical requests.
- Choose the wrapping order before tuning `minimumNumberOfCalls` and `failureRateThreshold`.
- Limit `maxAttempts`; remember that this number usually includes the initial call.
- Only retry transient errors and operations safe to re-execute.
- Ignore `CallNotPermittedException` in Retry when Circuit Breaker is inside Retry.
- Place fallback after Retry if you want Retry to have a chance to handle errors first.
- Monitor both Retry metrics and Circuit Breaker metrics.
- Evaluate slow-call rate by attempt duration or full request duration depending on the wrapping order.
- Use backoff, jitter, an overall timeout, and a retry budget to avoid load amplification.
- Test all cases: retry succeeding, retry exhausting attempts, and Circuit Breaker opening mid-sequence.

The wrapping order of Retry and Circuit Breaker determines the unit that Circuit Breaker records into its sliding window. Retry on the outside makes each attempt a sample; Circuit Breaker on the outside makes each retry sequence one final sample. Understanding this difference helps choose thresholds, read metrics, and design fallbacks aligned with the dependency protection goals of a Spring Cloud application.

## References

- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j Decorators](https://resilience4j.readme.io/docs/getting-started-3)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
