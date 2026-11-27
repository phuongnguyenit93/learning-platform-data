# recordExceptionPredicate and Custom Classification Rules

## Why Classify Exceptions?

In Spring Cloud Circuit Breaker backed by Resilience4j, the Circuit Breaker decides whether to open the circuit based on call outcomes recorded in a sliding window. By default, an exception escaping a call is treated as a failure. However, not every exception indicates that the dependent service is degrading.

For example, connection timeouts or HTTP 503 server errors are typically signs that the system needs protection. Conversely, invalid input data errors may be business errors sent by the client. If every input error is counted as an infrastructure error, a burst of malformed requests can cause the Circuit Breaker to open even while the dependent service remains healthy.

Resilience4j lets you define classification rules using predicates. A predicate accepts a `Throwable` and returns `true` or `false`. In configuration, the failure-recording rule is often referred to as `recordExceptionPredicate`; the Java builder provides APIs to set this predicate alongside an ignore-exception predicate.

## Evaluation Rules for an Exception

When a call ends with an exception, Resilience4j applies classification rules in order:

1. If the ignore-exception predicate returns `true`, the exception is ignored and does not participate in success or failure rates.
2. If the exception is not ignored and the record-exception predicate returns `true`, the call is counted as a failure.
3. If the exception is not ignored and the record-exception predicate returns `false`, the call is counted as a success for Circuit Breaker statistics.

Classification only affects metrics and Circuit Breaker state decisions. An ignored exception or one classified as a success can still propagate to the caller; a predicate does not automatically turn an exception into a successful response and does not replace a fallback.

| Ignore Predicate Result | Record Predicate Result | How the Circuit Breaker Counts It |
| --- | --- | --- |
| `true` | Not evaluated | Ignored; increments neither success nor failure counts. |
| `false` | `true` | Recorded as a failure. |
| `false` | `false` | Recorded as a success. |

By default, if no custom lists or predicates are configured, exceptions are recorded as failures and no exceptions are ignored. When `recordExceptions` is used, exception types matching the list are recorded; non-matching exceptions are treated as successes unless they match an ignore rule. `ignoreExceptions` takes higher priority than failure recording.

## Writing a Custom recordExceptionPredicate

Suppose a catalog service has the following error types:

- `TimeoutException` and `ConnectException`: the service is unresponsive or unreachable and must count as a failure.
- `ServiceUnavailableException`: the dependent service reports unavailability and must count as a failure.
- `InvalidCatalogRequestException`: the request has invalid business data and should not inflate the infrastructure error rate.
- Remaining exceptions: must be classified according to application policy; the example below does not automatically treat them as failures.

You can write explicit predicates:

```java
import java.net.ConnectException;
import java.util.concurrent.TimeoutException;
import java.util.function.Predicate;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

Predicate<Throwable> recordFailure = error ->
    error instanceof TimeoutException
        || error instanceof ConnectException
        || error instanceof ServiceUnavailableException;

Predicate<Throwable> ignoreFailure =
    InvalidCatalogRequestException.class::isInstance;

CircuitBreakerConfig circuitBreakerConfig = CircuitBreakerConfig.custom()
    .recordException(recordFailure)
    .ignoreException(ignoreFailure)
    .failureRateThreshold(50)
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .build();
```

`ServiceUnavailableException` and `InvalidCatalogRequestException` are application-defined exception types in this example. The `recordFailure` predicate only records the three stated error groups. Other exceptions that neither match the predicate nor are ignored will be counted as successes by the Circuit Breaker. This is an intentional policy in the example; in production systems, decide explicitly how to handle unknown errors rather than accidentally classifying them as successes.

If you want to record all exceptions by default except a few business exceptions, keep the default recording rule and declare only the ignore predicate. That approach is usually safer when the application may encounter new infrastructure error types in the future.

## Integrating Predicates into Spring Cloud Circuit Breaker

When using the Resilience4j starter, customize the Spring-created factory with a `Customizer`. Here is an example configuring default predicates for Circuit Breakers created by the factory:

```java
@Configuration(proxyBeanMethods = false)
public class CatalogCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> catalogCircuitBreakerCustomizer() {
        return factory -> factory.configureDefault(id -> {
            CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .recordException(error ->
                    error instanceof TimeoutException
                        || error instanceof ConnectException
                        || error instanceof ServiceUnavailableException
                )
                .ignoreException(
                    InvalidCatalogRequestException.class::isInstance
                )
                .failureRateThreshold(50)
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .build();

            return new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(config)
                .build();
        });
    }
}
```

Required imports include `Customizer`, `Resilience4JCircuitBreakerFactory`, `Resilience4JConfigBuilder`, `CircuitBreakerConfig`, `TimeoutException`, and `ConnectException`. Builder API names must match the Resilience4j and Spring Cloud Circuit Breaker versions managed by the application's BOM. In the Java builder, `recordException(...)` sets the failure-recording predicate; the corresponding concept or configuration property is commonly referred to as `recordExceptionPredicate`.

`configureDefault` applies the default policy to IDs created by the factory. If each service needs its own policy, configure per ID rather than applying the same predicate to every service. For example, a payment service may need to record payment-gateway errors, whereas a search service may classify certain query errors as business errors.

Avoid declaring another Resilience4j factory just to swap predicates. The starter already provides the factory and auto-configuration; a customizer is the proper extension point to add configuration.

## Classifying Exceptions by Class and Inheritance Hierarchy

Predicates commonly use `instanceof` or `Class::isInstance` to match subclasses as well. This is useful when multiple specific exceptions inherit from a common base class:

```java
Predicate<Throwable> isRemoteServiceFailure = error ->
    error instanceof RemoteServiceException
        || error instanceof TimeoutException;
```

If `ServiceUnavailableException` extends `RemoteServiceException`, the predicate above matches that exception as well. Design your exception hierarchy around stable semantics—such as separating `RemoteServiceException` from `BusinessRuleException`—so predicates do not have to enumerate too many unrelated classes.

Avoid classifying solely based on string class names or message text. Messages can change across libraries, locales, or service versions; class names can also change during refactoring. Checking exception types and structured fields is usually far more reliable.

## Handling Wrapped Exceptions

In asynchronous calls, the actual exception may be wrapped in a `CompletionException` or `ExecutionException`. If a predicate only inspects the outermost exception class, it may miss a timeout or connection error nested in `cause`.

You can normalize the exception before classifying:

```java
private static Throwable unwrap(Throwable error) {
    while ((error instanceof CompletionException
            || error instanceof ExecutionException)
            && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}

Predicate<Throwable> recordFailure = error -> {
    Throwable cause = unwrap(error);
    return cause instanceof TimeoutException
        || cause instanceof ConnectException
        || cause instanceof ServiceUnavailableException;
};
```

Only unwrap known wrappers and stop when there is no `cause`. Do not loop indefinitely or assume every `cause` is the root error. In systems using HTTP clients, you may also need to check specific exception types thrown by the client, such as connection errors, response-read errors, or HTTP status errors. Write tests for the exact exception types thrown by your client in practice.

## Distinguishing recordExceptionPredicate and recordResult

The exception predicate is only invoked when the supplier terminates with a `Throwable`. Some clients instead return a response object carrying an error status without throwing an exception. In that situation, the Circuit Breaker sees a normal return value unless the application converts the HTTP status into an exception.

For example, a custom client may return a `CatalogResponse` with code 503. If you want that code counted as a failure, you can use a result predicate (`recordResult`) if your Resilience4j version supports it:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .recordResult(result ->
        result instanceof CatalogResponse response
            && response.statusCode() >= 500
    )
    .build();
```

In this example, `CatalogResponse` is an application-defined response type. `recordResult` evaluates the return value; `recordException` evaluates exceptions. If the HTTP client already throws an exception for 5xx statuses, classify that exception rather than adding duplicate result rules. Not every business error or 4xx code should open the circuit breaker; decide according to the service contract.

## Relationship Between Error Classification and Fallback

Fallback handles the outcome at the calling layer, while the predicate decides how the Circuit Breaker records exceptions. Both mechanisms can appear together in a single call:

```java
public CatalogItem find(String id) {
    return circuitBreakerFactory.create("catalog").run(
        () -> catalogClient.find(id),
        error -> {
            log.warn("Catalog call failed for id={}", id, error);
            return CatalogItem.unavailable(id);
        }
    );
}
```

If a connection error matches `recordExceptionPredicate`, the Circuit Breaker records a failure and the fallback can then return an alternative response. If an input error matches the ignore predicate, the Circuit Breaker does not raise the failure rate; however, the exception can still enter the fallback per the wrapped call's contract. Therefore, do not infer the Circuit Breaker's failure count from how many times the fallback ran.

Fallbacks should preserve proper business semantics. `unavailable` should clearly convey indeterminate data or temporary service unavailability; do not return an empty object that tricks upper layers into thinking no matching record exists.

## Testing Classification Rules

Predicates are the business logic of your protection policy, so test each exception category. You can test the predicate directly first, then test the Circuit Breaker with simulated calls to verify metrics:

| Case | Ignore Predicate | Record Predicate | Expected Result |
| --- | --- | --- | --- |
| Connection timeout | `false` | `true` | Increments failure count. |
| Service error 503 | `false` | `true` | Increments failure count. |
| Invalid payload request | `true` | Not evaluated | Increments neither success nor failure count. |
| Exception not in recorded group | `false` | `false` | Counted as a success in statistics. |
| `CompletionException` wrapping timeout | `false` after unwrap | `true` after unwrap | Increments failure count. |

Example testing predicates with JUnit:

```java
@Test
void recordsTimeoutAsFailure() {
    Predicate<Throwable> recordFailure = error ->
        error instanceof TimeoutException;

    assertThat(recordFailure.test(new TimeoutException())).isTrue();
}

@Test
void ignoresInvalidRequest() {
    Predicate<Throwable> ignoreFailure =
        InvalidCatalogRequestException.class::isInstance;

    assertThat(ignoreFailure.test(new InvalidCatalogRequestException()))
        .isTrue();
}
```

These are standalone predicate tests; in real integration, add Circuit Breaker tests confirming that ignored exceptions do not alter the failure rate and that fallbacks behave properly. Also verify `minimumNumberOfCalls` and the sliding window so you do not draw false conclusions before enough samples accumulate.

## Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Recording every exception as an infrastructure error. | Request or business errors can trip the circuit prematurely. | Separate infrastructure error groups from groups to ignore. |
| Predicate inspects only the outermost exception. | Misses timeouts wrapped inside `CompletionException` or `ExecutionException`. | Unwrap known wrappers before classifying. |
| Assuming ignored exceptions are swallowed. | Callers may still receive the exception or trigger fallback. | Separate metric recording from exception handling. |
| Using a predicate returning `false` as a fallback. | The exception can still propagate out despite counting as a success in metrics. | Configure a dedicated fallback per the call contract. |
| Only classifying exceptions while the client returns normal error responses. | HTTP 5xx may be counted as a success. | Use `recordResult` or convert error responses into appropriate exceptions. |
| Mixing predicates and exception lists without checking precedence rules. | Effective policy differs from intent. | Define one clear rule and test it on the exact library version. |

A good `recordExceptionPredicate` accurately reflects what an error means for the dependent service. By clearly distinguishing exceptions to record, exceptions to ignore, error responses, and fallbacks, Resilience4j can calculate a realistic failure rate and only open the circuit breaker on reliable signs of degradation.
