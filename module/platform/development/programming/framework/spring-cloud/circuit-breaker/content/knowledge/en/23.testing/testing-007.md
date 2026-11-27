# Testing recordExceptions, ignoreExceptions, and Predicates

A Circuit Breaker does more than count raised exceptions. It needs to classify exceptions to know which calls truly reflect a dependency failure, which calls are normal business outcomes, and which error types require custom rules. Resilience4j provides `recordExceptions`, `ignoreExceptions`, and predicates to determine how each exception enters the sliding window.

This lesson belongs to the **Testing** chapter of the `SPRING_CLOUD_CIRCUIT_BREAKER` module. We will test classification configurations with JUnit, verify success/failure metrics, check OPEN transition thresholds, and ensure business errors do not corrupt breaker state. The examples use Resilience4j directly to test classification rules independently, then apply the same configuration to Spring Cloud CircuitBreaker by ID.

## 1. Why Must Exception Classification Be Tested?

A dependency can return many kinds of outcomes:

- Timeouts or connection errors: the dependency failed to deliver a result on time.
- HTTP 5xx: the dependency or gateway encountered a server-side error.
- HTTP 404: resource does not exist, which may be a valid business outcome.
- HTTP 400/422: invalid request or business rule violation.
- Authentication errors: the calling application's credentials may be expired or lack permissions.
- Local-code exceptions: mapping or processing errors inside the calling service.

If every exception is counted as a failure, a burst of invalid requests or many missing product SKUs could open the breaker even while the dependency is healthy. If too many exceptions are ignored, the breaker may fail to detect that the dependency is down.

Classification tests must answer four questions:

1. Which exceptions are recorded as failures?
2. Which exceptions are completely ignored, counting toward neither success nor failure?
3. Are exceptions that do not match the list or predicate treated as success or failure?
4. Once enough samples exist, does the failure rate transition the breaker to OPEN at the right threshold?

## 2. Distinguishing recordExceptions, ignoreExceptions, and Predicates

The three mechanisms have different meanings:

| Configuration | When an exception matches | Effect on sliding window |
|---|---|---|
| `recordExceptions(A.class)` | Recorded as failure | Increases failed calls and buffered sample count |
| `ignoreExceptions(B.class)` | Ignored | Does not increase success, failure, or buffered sample count |
| `recordException(predicate)` | Predicate returns `true` -> failure; `false` -> success | Outcome depends on the boolean rule |
| `ignoreException(predicate)` | Predicate returns `true` -> ignored | Counts as neither success nor failure |

There is a subtle distinction that is easy to confuse: when a `recordExceptions` list is configured, exceptions not in that list are treated as successes under that list's default rule, unless they match `ignoreExceptions`. They are not automatically ignored.

Conversely, `ignoreExceptions` excludes the exception from both success and failure. The exception still propagates to the caller; the Circuit Breaker simply does not use it for rate calculations.

When both record and ignore are configured together, the ignore rule takes precedence: an ignored exception is not counted as a failure even if it also matches the record rule. With predicates, `ignoreException` also acts as an exclusion before deciding to record a failure. Therefore, test cases where an exception could match multiple rules.

## 3. Configuring recordExceptions and ignoreExceptions in Java

Suppose the Catalog service has these exception types:

- `RemoteTimeoutException`: timeout when calling Catalog Service; must count as failure.
- `RemoteServerException`: server error from the dependency; must count as failure.
- `ProductNotFoundException`: product does not exist; a business outcome that should be ignored.
- `BusinessRuleException`: request failed a business condition; should be ignored.

You can configure it as follows:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(10)
    .minimumNumberOfCalls(5)
    .failureRateThreshold(50)
    .recordExceptions(
        RemoteTimeoutException.class,
        RemoteServerException.class
    )
    .ignoreExceptions(
        ProductNotFoundException.class,
        BusinessRuleException.class
    )
    .build();
~~~

In this configuration:

- Timeouts and server errors are recorded as failures.
- Missing products and business rule errors are ignored.
- Exceptions outside the record list are treated as successes, unless ignored.
- The breaker only computes failure rate after at least five counted samples have been recorded.

Configuring `recordExceptions` fits when the application wants to declare explicitly which error types count as failures. Make the list comprehensive enough to cover infrastructure errors that may occur. If a new exception is missing from the list, it could be counted as a success and mask an outage.

If the goal is to treat all exceptions as failures by default and only exclude a few business errors, you can configure only `ignoreExceptions`. This is often the cleaner choice when the set of exceptions to ignore is small and well-categorized.

## 4. Using Predicates for Conditional Classification

Class lists work well when error types are known ahead of time. Predicates are useful when inspecting exception attributes such as HTTP status, error code, or inner cause type.

For example, treating only HTTP 5xx errors as failures while ignoring not-found and business errors:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .failureRateThreshold(50)
    .recordException(exception ->
        exception instanceof RemoteCallException remote
            && remote.statusCode() >= 500
    )
    .ignoreException(exception ->
        exception instanceof ProductNotFoundException
            || exception instanceof BusinessRuleException
    )
    .build();
~~~

In this example:

- `RemoteCallException(503)` is recorded as a failure.
- `RemoteCallException(404)` does not match the record predicate, so it is counted as a success.
- `ProductNotFoundException` is ignored, so it counts as neither success nor failure.
- Other exceptions not matching the record predicate are treated as successes, unless ignored.

Predicates must be short, deterministic, and side-effect free. Do not perform I/O, database queries, or calls to other services inside a predicate. The predicate runs in the result-processing path of the call; slow work here can increase latency.

Never let a predicate throw an exception. Check for nulls and exception types before reading properties, and use standardized internal exceptions so the rules are easy to test.

## 5. Independent Testing with JUnit and AssertJ

You can construct a Circuit Breaker directly from `CircuitBreakerConfig` to test classification rules without starting the entire Spring context.

Example helper for JUnit 5:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CircuitBreakerExceptionClassificationTest {

    private static void invokeFailure(
            CircuitBreaker circuitBreaker,
            RuntimeException exception) {

        assertThatThrownBy(() ->
            CircuitBreaker.decorateSupplier(
                circuitBreaker,
                () -> {
                    throw exception;
                }
            ).get()
        ).isSameAs(exception);
    }

    private static void invokeSuccess(CircuitBreaker circuitBreaker) {
        String result = CircuitBreaker.decorateSupplier(
            circuitBreaker,
            () -> "ok"
        ).get();

        assertThat(result).isEqualTo("ok");
    }

    // Exception fixtures used in tests in the following sections.
    static class RemoteTimeoutException extends RuntimeException {}
    static class RemoteServerException extends RuntimeException {}
    static class BusinessRuleException extends RuntimeException {}
    static class ProductNotFoundException extends RuntimeException {}

    static class RemoteCallException extends RuntimeException {
        private final int statusCode;

        RemoteCallException(int statusCode) {
            this.statusCode = statusCode;
        }

        int statusCode() {
            return statusCode;
        }
    }
}
~~~

The `invokeFailure` helper verifies that the exception still propagates to the caller. The Circuit Breaker does not automatically convert exceptions into a fallback when using only the Resilience4j core decorator. Fallbacks must be declared at the Spring Cloud CircuitBreaker layer or in the corresponding call pipeline.

Tests should verify both the propagated exception and the internal breaker metrics. Checking only the thrown exception is insufficient to tell whether the exception was counted as a failure, success, or ignored.

## 6. Testing Record and Ignore Lists

The following test verifies three cases: a recorded exception, an ignored exception, and an exception not in the record list:

~~~java
@Test
void recordAndIgnoreExceptionsHaveDifferentMetricEffects() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50)
        .recordExceptions(
            RemoteTimeoutException.class,
            BusinessRuleException.class
        )
        .ignoreExceptions(BusinessRuleException.class)
        .build();

    CircuitBreaker breaker = CircuitBreaker.of("catalog-record-test", config);

    invokeFailure(breaker, new RemoteTimeoutException());
    // BusinessRuleException matches both record and ignore; ignore must take precedence.
    invokeFailure(breaker, new BusinessRuleException());
    invokeFailure(breaker, new IllegalStateException("not in record list"));

    assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isEqualTo(1);
    assertThat(breaker.getMetrics().getNumberOfSuccessfulCalls()).isEqualTo(1);
    assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isEqualTo(2);
}
~~~

Expected results:

- `RemoteTimeoutException` increments failed calls by one.
- `BusinessRuleException` is ignored, so it is not included in buffered calls.
- `IllegalStateException` does not match `recordExceptions`, so it is counted as a success.
- The total number of recorded samples is two, not three.

This test is crucial because it catches a common configuration mistake: unexpected exceptions not in the record list get counted as successes. If you want all non-business errors to count as failures, use an appropriate ignore list instead of an overly narrow record list.

## 7. Testing Predicates by HTTP Status

Predicates should be tested with multiple boundary values. Example:

~~~java
@Test
void predicateRecordsServerErrorsAndIgnoresBusinessErrors() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50)
        .recordException(exception ->
            exception instanceof RemoteCallException remote
                && remote.statusCode() >= 500
        )
        .ignoreException(exception ->
            exception instanceof ProductNotFoundException
        )
        .build();

    CircuitBreaker breaker = CircuitBreaker.of("catalog-predicate-test", config);

    invokeFailure(breaker, new RemoteCallException(503));
    invokeFailure(breaker, new RemoteCallException(404));
    invokeFailure(breaker, new ProductNotFoundException());

    assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isEqualTo(1);
    assertThat(breaker.getMetrics().getNumberOfSuccessfulCalls()).isEqualTo(1);
    assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isEqualTo(2);
}
~~~

The test verifies that 503 is a failure, 404 does not match the record predicate so it counts as a success, and `ProductNotFoundException` is ignored. Add boundary cases matching your actual API, such as 429 throttling, 401/403 credential errors, 408 timeouts, and exceptions produced by the HTTP client.

If 429 represents a business quota rather than dependency throttling, classify it according to the API contract. Predicates should only inspect status codes after the client adapter has converted the response into a meaningful exception; do not assume every status means the same thing across all services.

## 8. Testing Failure Rate and OPEN State Transition

Classification tests should connect to Circuit Breaker behavior. A small count-based configuration makes it easy for tests to pinpoint when the breaker opens:

~~~java
@Test
void recordedFailuresCanOpenTheCircuitBreaker() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(4)
        .minimumNumberOfCalls(4)
        .failureRateThreshold(50)
        .recordException(exception ->
            exception instanceof RemoteCallException remote
                && remote.statusCode() >= 500
        )
        .ignoreException(exception ->
            exception instanceof ProductNotFoundException
        )
        .build();

    CircuitBreaker breaker = CircuitBreaker.of("catalog-open-test", config);

    invokeFailure(breaker, new RemoteCallException(503));
    invokeFailure(breaker, new RemoteCallException(502));
    invokeSuccess(breaker);
    invokeSuccess(breaker);

    assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isEqualTo(4);
    assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isEqualTo(2);
    assertThat(breaker.getMetrics().getFailureRate()).isEqualTo(50.0f);
    assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);

    assertThatThrownBy(() ->
        CircuitBreaker.decorateSupplier(breaker, () -> "not called").get()
    ).isInstanceOf(CallNotPermittedException.class);
}
~~~

Two server errors out of four samples yield a 50% failure rate. Once `minimumNumberOfCalls` is met and `failureRateThreshold` is reached, the breaker transitions to OPEN. The next call is rejected with `CallNotPermittedException` before the supplier runs.

In real tests, you can configure a sufficiently long open duration to prevent the breaker from automatically transitioning to HALF_OPEN before assertions finish. Do not use arbitrary sleeps to synchronize tests; if you need to test time-based behavior, use a controllable clock or scheduler via the API supported by your Resilience4j version.

## 9. Verifying That Ignored Exceptions Do Not Increment Sample Count

A dedicated test confirms that business exceptions still propagate to the caller without affecting the sliding window:

~~~java
@Test
void ignoredExceptionIsPropagatedButNotRecorded() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .ignoreExceptions(ProductNotFoundException.class)
        .build();

    CircuitBreaker breaker = CircuitBreaker.of("catalog-ignore-test", config);

    invokeFailure(breaker, new ProductNotFoundException());

    assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isZero();
    assertThat(breaker.getMetrics().getNumberOfSuccessfulCalls()).isZero();
    assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isZero();
    assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
}
~~~

Do not check only that the failure rate equals 0. An empty window can also return an undetermined or sentinel value depending on the API. Checking the success, failure, and buffered call counts confirms that the exception was genuinely ignored.

## 10. Testing Configuration Through Spring Cloud CircuitBreaker

Testing Resilience4j core verifies the classification rules. An application also needs to verify that the configuration is bound to the exact ID when using Spring Cloud CircuitBreaker.

Example customizer:

~~~java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> catalogCircuitBreakerConfig() {
    return factory -> factory.configure(builder -> builder
        .circuitBreakerConfig(CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(10)
            .minimumNumberOfCalls(5)
            .failureRateThreshold(50)
            .recordExceptions(RemoteTimeoutException.class)
            .ignoreExceptions(ProductNotFoundException.class)
            .build()),
        "catalog-read");
}
~~~

At the integration layer, use a Spring Boot test to verify:

- The customizer is loaded by Spring.
- The Feign client or service invokes the exact ID `catalog-read`.
- The client adapter converts error HTTP responses into the expected exception type.
- Business exceptions do not increase the failure rate.
- Timeouts or server errors are recorded according to configuration.
- When the breaker is OPEN, new requests are rejected and the fallback is invoked if configured.

Do not merely test that the configuration class exists. An integration test should send requests through the real client in the test, using a mock HTTP server or stub server to control status codes and timeouts. That way, the test verifies the `ErrorDecoder`, exception mapping, and Circuit Breaker together instead of just inspecting a config object.

## 11. Avoiding False Tests Caused by Unthrown Error Responses

A Circuit Breaker typically classifies error outcomes based on exceptions thrown from the supplier or Publisher. If an HTTP client returns a normal response object with status 500 without throwing an exception, the Circuit Breaker may treat the invocation as a success.

For example, if the client adapter returns `RemoteResponse(status=503)` as a normal value, `recordExceptions` will not be triggered. There are two ways to handle this:

- Translate error responses into strongly typed exceptions before the outcome passes through the Circuit Breaker.
- If you intentionally keep the response as a return value, configure `recordResult` to classify the returned result.

With WebClient `retrieve()`, 4xx/5xx responses are typically converted into `WebClientResponseException` unless handled as a normal response via `onStatus`. With OpenFeign, an `ErrorDecoder` can map status codes into business exceptions or `RetryableException`. Test the adapter separately to verify which exception each actual status produces.

## 12. Recommended Test Matrix

| Scenario | Expected classification | What to assert |
|---|---|---|
| Remote timeout | Failure | failed calls increases |
| HTTP 5xx mapped to server exception | Failure | failure rate increases |
| HTTP 404 mapped to ProductNotFoundException | Ignored or success per policy | ignored does not increase buffered calls |
| BusinessRuleException | Ignored | does not increase success/failure |
| Exception not matching record list | Success when using an explicit record list | successful calls increases |
| Predicate receives status 503 | Failure | predicate returns true |
| Predicate receives status 404 | Success if not ignored | predicate returns false |
| Exception matching both record and ignore | Ignored | ignore takes precedence |
| Enough samples and failure rate meets threshold | Breaker OPEN | state transitions to OPEN |
| Call while OPEN | Not permitted | supplier does not run |
| Error response without adapter throwing exception | May be counted as success | integration test must catch wrong mapping |

Each test should create a new Circuit Breaker instance. Do not share a registry or breaker across tests without resetting state and metrics, because the previous test's sliding window can affect the next test's outcome.

## 13. Common Testing Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Business exception opens the breaker | Missing ignore rule or overly broad predicate | Add an ignore rule and assert metrics |
| New error does not increase failure rate | Exception is missing from the record list | Expand the list or use a predicate |
| Ignored exception still counts as failure | Ignore predicate/class does not match actual exception type | Inspect the cause chain and thrown exception |
| Flaky OPEN test | Minimum calls, window, or threshold mismatched | Use a controlled small window and deterministic sample count |
| Test sees supplier running when breaker is thought OPEN | Not enough samples or failure rate has not reached threshold | Check buffered calls and failure rate before asserting |
| HTTP 503 counted as success | Client returns response as a normal value | Map to an exception or use `recordResult` |
| Tests share state | Reusing a breaker across tests | Create a separate instance per test |
| Predicate increases latency | Heavy processing or I/O inside predicate | Perform only synchronous, lightweight checks |

## Conclusion

`recordExceptions` defines which exceptions count as failures; when using an explicit list, non-matching exceptions are typically treated as successes. `ignoreExceptions` excludes exceptions from both success and failure, while predicates allow classification based on conditions such as HTTP status or error type. Test both the exception propagated to callers and the buffered/success/failed metrics, then verify that the failure rate transitions the breaker to OPEN at the configured threshold. Finally, run integration tests from the HTTP client through the Circuit Breaker to ensure error responses are actually translated into exceptions recognized by your classification policy.
