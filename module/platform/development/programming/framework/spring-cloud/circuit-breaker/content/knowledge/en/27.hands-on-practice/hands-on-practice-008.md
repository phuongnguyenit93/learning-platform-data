# Reordering Retry and Circuit Breaker and Comparing Statistics

In a Spring Cloud CircuitBreaker application integrated with Resilience4j, Retry and Circuit Breaker can wrap the same call, yet the wrapping order changes the number of calls made to the dependency, the number of outcomes recorded in the sliding window, and when the breaker transitions to `OPEN`. Two common arrangements are **Circuit Breaker outside Retry** and **Retry outside Circuit Breaker**.

This hands-on practice uses the same simulated failing dependency, the same retry count, and the same Circuit Breaker thresholds to compare both arrangements. The goal is to measure three quantities separately: the number of logical operations from the caller, the actual number of attempts reaching the dependency, and the number of outcomes recorded by the Circuit Breaker. Once you understand this difference, your team can pick the order that matches what your failure rate is meant to measure, while preventing Retry from continuing attempts when the Circuit Breaker has already rejected the call.

## 1. Practice Objectives and Conditions

Build a Catalog read call with Retry up to three executions, including the initial attempt. The Circuit Breaker opens when at least four outcomes have been recorded and the failure rate reaches 50% or higher.

Run two independent scenarios:

- **Scenario A — Circuit Breaker outside, Retry inside:** one logical operation is observed by the Circuit Breaker as a single outcome after all retries finish.
- **Scenario B — Retry outside, Circuit Breaker inside:** each attempt passes through the Circuit Breaker and can be recorded as an individual outcome.

Use two separate Circuit Breaker IDs and two separate Retry IDs so state and metrics from one scenario do not affect the other. Each scenario starts with a fresh registry or instance in the `CLOSED` state.

Test conditions:

| Parameter | Value |
|---|---:|
| Retry maxAttempts | 3 |
| Retry waitDuration | 20 ms |
| Circuit Breaker minimumNumberOfCalls | 4 |
| Sliding window size | 10 |
| Failure rate threshold | 50% |
| Open duration | 10 seconds |
| Simulated dependency | Always throws TransientCatalogException |
| Fallback | Captures final error and returns unavailable result |

Short values make behavior easy to observe in a test environment. In real deployments, choose timeouts, attempt counts, backoff intervals, and thresholds based on SLOs, latency, and dependency capacity.

## 2. Prepare a Simulated Dependency That Counts Attempts

Create a test client that increments a counter every time the dependency is invoked. In the baseline scenario, the client always throws a transient error so all attempts fail.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class FakeCatalogClient {

    private final AtomicInteger attempts = new AtomicInteger();

    Product find(String productId) {
        int attempt = attempts.incrementAndGet();

        throw new TransientCatalogException(
            "Catalog temporarily unavailable, attempt=" + attempt
        );
    }

    int getAttemptCount() {
        return attempts.get();
    }

    void reset() {
        attempts.set(0);
    }
}
~~~

Test exception:

~~~java
class TransientCatalogException extends RuntimeException {
    TransientCatalogException(String message) {
        super(message);
    }
}
~~~

Fallback result:

~~~java
record Product(String id, String name, boolean available) {

    static Product unavailable(String id) {
        return new Product(id, "Temporarily unavailable", false);
    }
}
~~~

The counter in `FakeCatalogClient` tracks how many times the supplier actually calls the dependency. It is neither the logical operation count nor the count recorded by the Circuit Breaker. These three figures must be measured separately throughout the practice.

In a real integration environment, replace `FakeCatalogClient` with an HTTP stub or WireMock. The stub should record the number of received requests to verify attempts from the server side, rather than relying solely on an in-process counter in the caller.

## 3. Configure Two Independent Retry and Circuit Breaker Pairs

Declare two instance groups in application YAML:

~~~yaml
resilience4j:
  retry:
    instances:
      catalog-retry-inside:
        maxAttempts: 3
        waitDuration: 20ms
        retryExceptions:
          - com.example.TransientCatalogException
        ignoreExceptions:
          - com.example.ProductNotFoundException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException

      catalog-retry-outside:
        maxAttempts: 3
        waitDuration: 20ms
        retryExceptions:
          - com.example.TransientCatalogException
        ignoreExceptions:
          - com.example.ProductNotFoundException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException

  circuitbreaker:
    instances:
      catalog-cb-outside:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2

      catalog-cb-inside:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

In the configuration:

- **catalog-retry-inside** is used when Retry sits inside the Circuit Breaker.
- **catalog-cb-outside** is the breaker wrapping the entire Retry sequence.
- **catalog-retry-outside** is used when Retry sits outside the Circuit Breaker.
- **catalog-cb-inside** records each attempt invoked by Retry.
- **CallNotPermittedException** is ignored by Retry so it stops immediately when the Circuit Breaker rejects the next attempt.
- **ProductNotFoundException** is an example business error; it is not retried.

Both pairs use identical thresholds for a fair comparison. Never reuse the same Circuit Breaker ID across both scenarios, as state and sliding window entries from the first scenario will skew the second scenario's results.

## 4. Scenario A: Circuit Breaker Outside, Retry Inside

The execution order is:

~~~text
Caller
  |
  v
Circuit Breaker
  |
  v
Retry
  |
  v
Catalog client
~~~

With this arrangement, the Circuit Breaker grants permission once for the logical operation. Its supplier contains the entire Retry. Retry may call Catalog multiple times; only when Retry finishes does the Circuit Breaker receive the final outcome.

This can be expressed using Resilience4j decorators:

~~~java
Supplier<Product> catalogCall =
    () -> fakeCatalogClient.find(productId);

Retry retry = retryRegistry.retry("catalog-retry-inside");
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.circuitBreaker("catalog-cb-outside");

Supplier<Product> retryInside =
    Retry.decorateSupplier(retry, catalogCall);

Supplier<Product> circuitBreakerOutside =
    CircuitBreaker.decorateSupplier(circuitBreaker, retryInside);

Product product = circuitBreakerOutside.get();
~~~

If using the Spring Cloud CircuitBreaker factory for the outer layer, keep Retry inside the supplier:

~~~java
Retry retry = retryRegistry.retry("catalog-retry-inside");

Product product = circuitBreakerFactory
    .create("catalog-cb-outside")
    .run(
        () -> retry.executeSupplier(
            () -> fakeCatalogClient.find(productId)
        ),
        error -> Product.unavailable(productId)
    );
~~~

In this example, the factory creates the outer Circuit Breaker. Retry wraps only the client call inside the supplier. The fallback executes after the protected operation terminates with an error or is rejected.

With an always-failing dependency and `maxAttempts` set to 3, one logical operation generates three requests to Catalog. Retry rethrows the final error after the third attempt. The Circuit Breaker records only one failure for that operation.

If you run four consecutive logical operations:

| Logical operation | Attempts to Catalog | Final Retry outcome | Circuit Breaker sample |
|---|---:|---|---|
| 1 | 3 | Failure | 1 failure |
| 2 | 3 | Failure | 1 failure |
| 3 | 3 | Failure | 1 failure |
| 4 | 3 | Failure | 1 failure |
| **Total** | **12** | **4 failed operations** | **4 failures** |

After the fourth operation, the Circuit Breaker has four samples and a 100% failure rate, exceeding the 50% threshold, so it transitions to `OPEN`. The fifth operation is rejected by the Circuit Breaker before Retry runs; the Catalog request count does not increase.

Key takeaway: the Circuit Breaker evaluates the final outcome after Retry. If Retry encounters two errors and then succeeds on the third attempt, the Circuit Breaker records only one success. The two intermediate failures do not become two failures in the outer breaker's sliding window.

## 5. Scenario B: Retry Outside, Circuit Breaker Inside

The execution order is:

~~~text
Caller
  |
  v
Retry
  |
  v
Circuit Breaker
  |
  v
Catalog client
~~~

In this arrangement, every attempt generated by Retry passes through the Circuit Breaker. Each attempt requires permission and produces its own outcome in the sliding window.

Expressed with decorators:

~~~java
Supplier<Product> catalogCall =
    () -> fakeCatalogClient.find(productId);

Retry retry = retryRegistry.retry("catalog-retry-outside");
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.circuitBreaker("catalog-cb-inside");

Supplier<Product> circuitBreakerInside =
    CircuitBreaker.decorateSupplier(circuitBreaker, catalogCall);

Supplier<Product> retryOutside =
    Retry.decorateSupplier(retry, circuitBreakerInside);

Product product = retryOutside.get();
~~~

If using the Spring Cloud CircuitBreaker factory, create a Circuit Breaker first and let Retry wrap the protected operation:

~~~java
Retry retry = retryRegistry.retry("catalog-retry-outside");
var circuitBreaker = circuitBreakerFactory.create("catalog-cb-inside");

Supplier<Product> circuitBreakerProtected =
    () -> circuitBreaker.run(
        () -> fakeCatalogClient.find(productId),
        error -> {
            if (error instanceof RuntimeException runtimeException) {
                throw runtimeException;
            }
            throw new IllegalStateException(error);
        }
    );

Product product = Retry.decorateSupplier(
    retry,
    circuitBreakerProtected
).get();
~~~

The fallback in this snippet intentionally rethrows the error so Retry can classify the exception. If the fallback returned `Product.unavailable` immediately, Retry would see a successful result and would not retry. In real designs, decide explicitly whether fallback runs after Retry completes or per attempt.

With a minimum of four samples configured, trace the sequence:

1. First logical operation starts; Retry runs attempt 1 through the Circuit Breaker.
2. Dependency fails; Circuit Breaker records failure #1.
3. Retry runs attempt 2; Circuit Breaker records failure #2.
4. Retry runs attempt 3; Circuit Breaker records failure #3.
5. Second logical operation starts; its first attempt passes through the Circuit Breaker and produces failure #4.
6. Circuit Breaker reaches `minimumNumberOfCalls` and transitions to `OPEN`.
7. Retry tries to execute the next attempt; Circuit Breaker rejects it with `CallNotPermittedException`.
8. Retry ignores this exception and stops without calling the dependency again.

Summary table:

| Execution via Retry | Circuit Breaker | Calls Catalog? | Outcome |
|---|---|---|---|
| Operation 1, attempt 1 | CLOSED, records failure 1 | Yes | TransientCatalogException |
| Operation 1, attempt 2 | CLOSED, records failure 2 | Yes | TransientCatalogException |
| Operation 1, attempt 3 | CLOSED, records failure 3 | Yes | TransientCatalogException |
| Operation 2, attempt 1 | CLOSED, records failure 4 then OPEN | Yes | TransientCatalogException |
| Operation 2, attempt 2 | OPEN, rejects | No | CallNotPermittedException |
| Operation 2, next attempt | Not invoked by Retry | No | Retry stopped |

In this scenario, only four requests reach the dependency before the Circuit Breaker opens. The rejected call is not a request to Catalog and must not be mistaken for a new dependency failure.

## 6. Why Ignore CallNotPermittedException in Retry?

When the Circuit Breaker is `OPEN`, it throws **CallNotPermittedException** before the supplier invokes the dependency. This signals that the breaker is actively blocking calls to protect the system.

If Retry treats this exception as a retryable transient error, it can keep calling the Circuit Breaker repeatedly while the breaker remains `OPEN`. Every one of those calls will be rejected, does nothing to help the dependency recover, and only adds unnecessary executions, logs, and latency.

Ignore configuration:

~~~yaml
resilience4j:
  retry:
    instances:
      catalog-retry-outside:
        maxAttempts: 3
        waitDuration: 20ms
        retryExceptions:
          - com.example.TransientCatalogException
        ignoreExceptions:
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException
          - com.example.ProductNotFoundException
~~~

When Retry encounters `CallNotPermittedException`, it ends the retry loop and propagates the error to the caller or an outer fallback. Never retry Circuit Breaker rejection errors.

Distinguish clearly:

- **TransientCatalogException:** the dependency was called and returned a transient error; safe to retry if the operation allows it.
- **CallNotPermittedException:** the dependency was not called because the Circuit Breaker rejected the call; stop retrying.
- **ProductNotFoundException:** business outcome; do not retry if repeating the same request cannot make the product exist.

If you use a fallback inside the Circuit Breaker that turns every exception into a default value, an outer Retry can no longer see the original exception. Only turn errors into fallbacks at the outermost layer of the chain, or rethrow exceptions that Retry needs to classify.

## 7. Comparing Both Orders with the Same Failure Schedule

To keep results comparable, run both scenarios under identical conditions:

- Same simulated dependency that always fails.
- Same `maxAttempts` of 3.
- Same `waitDuration` of 20 ms.
- Same `minimumNumberOfCalls` of 4.
- Same `failureRateThreshold` of 50%.
- Same number of logical operations submitted.
- A fresh Circuit Breaker instance for each scenario.

Expected results for four consecutive failures and a subsequent operation:

| Metric | Circuit Breaker outside, Retry inside | Retry outside, Circuit Breaker inside |
|---|---:|---:|
| Logical operations needed to open circuit | 4 | 2 |
| Dependency attempts before OPEN | 12 | 4 |
| Failures recorded by Circuit Breaker before OPEN | 4 | 4 |
| Attempts rejected after OPEN | 0 within running Retry; next operation blocked outside | 1 on the next Retry attempt of the second operation |
| Dependency requests after OPEN | Does not increase | Does not increase |
| Meaning of failure rate | Rate of operations failing after Retry | Rate of attempts observed by the Circuit Breaker |

The table above assumes every Catalog call fails, Retry makes up to three attempts, and Retry ignores `CallNotPermittedException`. If the dependency recovers on the second or third attempt, the results change: the outer Circuit Breaker may record only one success for the operation, whereas the inner Circuit Breaker may have recorded intermediate failures before that success.

Do not use rejected attempt counts to measure requests sent to the dependency. `CallNotPermittedException` means the call was blocked before the supplier ran; separate rejection counts from HTTP request counts.

## 8. Comparing When the Dependency Recovers on the Third Attempt

A second failure schedule highlights the difference when Retry succeeds:

- Attempt 1: `TransientCatalogException`.
- Attempt 2: `TransientCatalogException`.
- Attempt 3: returns `Product` successfully.

With Circuit Breaker outside, Retry runs all three attempts and returns `Product`. The Circuit Breaker sees only one successful outcome. The sliding window increments by one success.

With Retry outside, the Circuit Breaker sees two failures followed by one success. The sliding window increments by three samples: two failures and one success. If those two failures push the failure rate above the threshold once minimum calls are met, the Circuit Breaker can open before the third attempt; in that case, the third attempt is rejected and the dependency is not called again.

Operational implications:

- Circuit Breaker outside prioritizes evaluating the final outcome of an operation after Retry.
- Circuit Breaker inside reacts faster to individual attempt failures, but can open the circuit before Retry finishes.
- If Retry has a high attempt count, an inner Circuit Breaker can accumulate failures much faster than the logical operation count.
- If the goal is to measure the caller's end-user experience, placing Circuit Breaker outside may fit better.
- If the goal is to shield the dependency from individual failing attempts, placing Circuit Breaker inside may fit better, provided `CallNotPermittedException` is ignored.

No single ordering is universally best for every system. Choose based on the statistical meaning your team wants to observe and how you balance single-operation resilience against shedding dependency load early.

## 9. Measuring the Right Statistics for Comparison

In each run, record at least the following metrics:

| Metric | Measurement source | Meaning |
|---|---|---|
| Logical operations | Counter in service or test harness | How many operations the caller requested |
| Dependency attempts | `FakeCatalogClient` counter or HTTP stub | How many requests actually reached the dependency |
| Retry attempts | Retry metrics or events | How many attempts Retry executed |
| Retry success after retry | Retry metrics | How many operations succeeded only after retrying |
| Circuit Breaker successful calls | Circuit Breaker metrics | Successful outcomes recorded by the breaker |
| Circuit Breaker failed calls | Circuit Breaker metrics | Failures counted in statistics |
| Not permitted calls | Circuit Breaker metrics/events | Times the breaker rejected before calling the supplier |
| State transitions | Circuit Breaker events | When `CLOSED`, `OPEN`, and `HALF_OPEN` changed |
| Fallback count | Fallback counter | How many operations used fallback data or responses |
| End-to-end latency | Timer in service | How long the caller waited per logical operation |

Do not infer backend request counts from Retry metrics or Circuit Breaker failure counts. With Circuit Breaker outside, one breaker failure can correspond to three requests to the dependency. With Circuit Breaker inside, three breaker failures can correspond to three requests. Only the dependency request count directly answers how many requests the backend received.

In Resilience4j, you can observe events such as state transitions, errors, successes, and calls not permitted. Micrometer metrics, depending on version and registry configuration, expose corresponding metric groups. Use the exact metric names and tags exported by your runtime version; do not hardcode dashboards from assumed names.

## 10. How to Run Both Scenarios and Reset State

Run each scenario separately so no state or counters are shared.

### Scenario A

1. Initialize Circuit Breaker **catalog-cb-outside** in `CLOSED`.
2. Reset the dependency counter.
3. Send four sequential logical operations, each experiencing three failed attempts.
4. After each operation, record dependency request count and Circuit Breaker sample count.
5. Verify that after the fourth operation, the breaker transitions to `OPEN`.
6. Send a fifth operation.
7. Verify the fifth operation is rejected and dependency attempt count remains 12.

### Scenario B

1. Create a fresh instance **catalog-cb-inside** in `CLOSED`.
2. Reset the dependency counter and Retry metrics.
3. Send the first logical operation, letting Retry run three failed attempts.
4. Send the second logical operation.
5. Verify the first attempt of the second operation is the fourth failure and opens the breaker.
6. Verify the next attempt is rejected with `CallNotPermittedException`.
7. Verify dependency attempt count is 4 and does not increase once the Circuit Breaker is `OPEN`.

In automated tests, never reuse an `OPEN` Circuit Breaker instance across tests. Create a fresh registry or instance per scenario, or use a test-only state reset mechanism per your library version's API. Do not rely on waiting 10 seconds for a breaker to reset itself; elapsing wait duration only enables `HALF_OPEN`, and does not return it to `CLOSED` without suitable probes.

## 11. Verifying Fallbacks and Exception Policies

The fallback must be placed appropriately for the wrapping order.

**Fallback outside the entire Retry and Circuit Breaker chain:** the caller receives the fallback only after Retry finishes or the Circuit Breaker rejects the operation. This is usually the easiest placement for preserving semantics when Retry must inspect the original exception first.

**Fallback inside the Circuit Breaker when Retry is outside:** if the fallback converts errors into `Product.unavailable`, Retry sees `Product` as a normal return value and stops retrying. For Retry to work, an inner fallback must rethrow the error or only convert exceptions that should not be retried.

Example outermost fallback:

~~~java
Product getProduct(String productId) {
    try {
        return retryOutsideCircuitBreaker(productId);
    } catch (CallNotPermittedException error) {
        return productCache.find(productId)
            .orElse(Product.unavailable(productId));
    } catch (TransientCatalogException error) {
        return productCache.find(productId)
            .orElse(Product.unavailable(productId));
    }
}
~~~

In a real application, you can classify additional business exceptions to propagate rather than returning unavailable. Never turn `ProductNotFound` into an infrastructure error; likewise, do not turn every exception into a cache fallback if cached data may be stale or invalid.

For write operations such as inventory reservation or payment, retry only when the operation is idempotent or carries an idempotency key. A caller timeout does not prove the backend did not execute the operation; blind retries can create duplicate transactions.

## 12. Notes When Using Annotations Instead of Decorators

Spring AOP lets you declare Retry and Circuit Breaker with annotations, yet aspect ordering can change how the two mechanisms wrap each other. Never deduce execution order solely from the visual order of annotations on a method.

Example:

~~~java
@CircuitBreaker(name = "catalog", fallbackMethod = "fallback")
@Retry(name = "catalog")
public Product getProduct(String id) {
    return catalogClient.find(id);
}
~~~

The annotations above show both policies applied to the method, but actual aspect precedence must be determined from your Resilience4j version, aspect order configuration, and how Spring proxies the method. When you need exact control over ordering to compare behaviors, explicit decorator composition is clearer and less dependent on implicit aspect order.

When using annotations, make sure to:

- Verify aspect ordering in the version you are using.
- Verify the method is invoked through the Spring proxy, not via self-invocation.
- Assign distinct Retry and Circuit Breaker IDs per scenario.
- Configure ignoring `CallNotPermittedException` if Retry can sit outside Circuit Breaker.
- Use a test counting dependency calls to verify actual ordering.
- Verify fallbacks do not swallow exceptions before Retry classifies them.

Do not change production aspect order merely to make a test pass. First establish current behavior, document the required semantics, and verify with an integration test.

## 13. Analyzing Results and Choosing the Right Order

After running, fill your measured numbers into the table:

| Metric | CB outside / Retry inside | Retry outside / CB inside |
|---|---:|---:|
| Logical operations before OPEN |  |  |
| Dependency attempts before OPEN |  |  |
| CB failures before OPEN |  |  |
| CB not-permitted |  |  |
| Retry attempts |  |  |
| Fallback count |  |  |
| p95 operation latency |  |  |
| State transition time |  |  |

Use these questions to interpret the results:

1. Is the Circuit Breaker counting logical operations or individual attempts?
2. When Retry succeeds after one or more errors, how does the Circuit Breaker's failure rate change?
3. Can the Circuit Breaker open mid-Retry or only after Retry finishes?
4. Does `CallNotPermittedException` stop Retry immediately?
5. Does the dependency attempt count match the request count received by the HTTP stub?
6. Does the fallback run after all retries or inside each attempt?
7. Which order reduces backend requests faster when the backend fails continuously?
8. Which order more accurately reflects the failed-operation rate experienced by callers?

If you prioritize evaluating the final outcome after Retry policy, Circuit Breaker outside Retry is usually easier to reason about. If you prioritize tracking every attempt and opening early to shed backend load, Retry outside Circuit Breaker can fit well, provided rejection exceptions are ignored and fallbacks do not swallow errors prematurely.

## 14. Common Practice Mistakes

1. **Sharing a Circuit Breaker ID across both scenarios.** State from the first run corrupts numbers in the second; use separate instances.
2. **Counting only logical operations.** One operation can produce multiple attempts; measure requests to the dependency separately.
3. **Retry outside without ignoring CallNotPermittedException.** Retry keeps hammering an `OPEN` breaker and generates repeated rejections.
4. **Fallback returning a success value too early.** Retry stops seeing exceptions and aborts before the next attempt.
5. **Confusing not permitted with dependency failures.** Calls blocked by the Circuit Breaker never reached the backend.
6. **Misconfiguring minimumNumberOfCalls.** The breaker may lack enough samples to open or open earlier than intended.
7. **Comparing scenarios with different failure schedules.** Results no longer isolate the effect of decorator ordering.
8. **Not resetting dependency counters and metrics.** Counts accumulate across runs.
9. **Using annotations while assuming aspect order.** Actual ordering must be verified by tests.
10. **Retrying non-idempotent write operations.** Can cause duplicate side effects when responses are lost or time out.

## Conclusion

Placing Circuit Breaker outside Retry causes the breaker to record the final outcome of an operation after Retry completes. Placing Retry outside Circuit Breaker sends every attempt through the breaker so each can be recorded separately in the sliding window. The second ordering can trip the circuit sooner, but Retry must ignore **CallNotPermittedException** to stop immediately when the breaker rejects calls. During practice, use independent instances, identical failure schedules, and measure logical operations, dependency attempts, Circuit Breaker failures, not-permitted calls, Retry attempts, and fallbacks separately to select the ordering that fits your operational goals.
