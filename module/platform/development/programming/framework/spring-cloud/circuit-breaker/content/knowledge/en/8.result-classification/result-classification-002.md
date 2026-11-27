# recordExceptions, ignoreExceptions, and Exception Scope

Resilience4j's circuit breaker decides whether a call is counted as a success or a failure based on the outcome returned by the protected function. For calls that throw exceptions, the application can configure which exception types are recorded as failures and which should be ignored. The two key properties are `recordExceptions` and `ignoreExceptions`.

Proper classification helps the circuit breaker accurately reflect dependency outages. If every business exception is counted as an infrastructure error, the circuit may open even though the service is operating normally. Conversely, if timeouts or connection errors are ignored, the circuit breaker may fail to notice that the dependency is experiencing an outage.

## Three Outcomes When Classifying Exceptions

With Resilience4j, an exception thrown from a protected call falls into one of three categories:

| Category | How the Circuit Breaker Records It | Impact on Rates |
|---|---|---|
| **Recorded as failure** | Increments the failed call count. | Increases the failure rate. |
| **Ignored** | Counted as neither a success nor a failure. | Leaves both outcome counters in the window unchanged. |
| **Matches neither the record nor ignore list** | When `recordExceptions` is configured, exceptions not matching this list are treated as successes unless they are in the ignore list. | Increments the successful call count. |

By default, if no custom exception list or classification predicate is configured, exceptions thrown by a call are recorded as failures. Once `recordExceptions` is declared, the application switches to opting in specific exception types as failures. Therefore, it is important to understand how all remaining exceptions will be classified.

## recordExceptions: Selecting Exceptions Counted as Errors

`recordExceptions` is a list of exception classes that the circuit breaker must record as failures. These are typically errors indicating the dependency cannot fulfill requests, such as timeouts, connection errors, or remote service errors.

For example, an ordering service calls an inventory service. Errors like `SocketTimeoutException` or `InventoryUnavailableException` indicate the call did not complete because the dependency encountered a problem. The application can configure them in the record list.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
          - com.example.inventory.InventoryUnavailableException
~~~

In this example, the listed exceptions are counted as failures. Once at least the minimum number of calls is reached and the failure rate meets the threshold, the circuit breaker can transition from CLOSED to OPEN.

When `recordExceptions` is configured, exceptions that do not match the record list are typically counted as successes, except for exceptions declared as ignored. This is an important caveat: an overly narrow record list can inadvertently treat many unexpected errors as successes.

## ignoreExceptions: Excluding Exceptions from Statistics

`ignoreExceptions` specifies exceptions that the circuit breaker does not use when calculating success or failure rates. They usually represent predictable business outcomes or invalid input data, rather than failures of the dependent service.

Examples:

- `InvalidSkuException`: the product code submitted by the user is invalid.
- `ProductNotFoundException`: the product does not exist according to business rules.
- `BusinessRuleViolationException`: the request violates a defined business rule.

You can add the ignore list to the configuration:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
          - com.example.inventory.InventoryUnavailableException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.ProductNotFoundException
          - com.example.common.BusinessRuleViolationException
~~~

An exception matching `ignoreExceptions` takes precedence and is ignored, even if its exception type also matches a class in `recordExceptions`. An ignored exception can still propagate out of the call for the calling layer to handle or for a fallback to respond to. "Ignored" here only means the exception is excluded from circuit breaker statistics; it does not mean swallowing the exception or turning the outcome into a success.

Only ignore exceptions that genuinely do not reflect dependency health. If you ignore `SocketTimeoutException`, `ConnectException`, or remote server errors, the circuit may stay closed while calls fail en masse.

## Distinguishing Business Errors from Dependency Errors

Classification should be based on the meaning of the exception within the specific call flow, not solely on its class name.

| Situation | Typically Appropriate Classification | Reason |
|---|---|---|
| Dependent service unreachable | Record failure | The dependency is unavailable to handle calls. |
| Call exceeds timeout | Record failure | The dependency failed to respond within the time budget. |
| Remote service returns 5xx server error and client throws exception | Record failure | Usually indicates a processing error at the dependency. |
| Invalid product code | Ignore | Invalid input does not prove the dependency is failing. |
| Product does not exist per business rules | Ignore or return domain result | This can be a valid outcome, not an infrastructure failure. |
| Remote service returns 4xx due to auth or permissions | Classify by context | May indicate an integration configuration error or an invalid business request. |
| Internal programming bug in the calling service | Evaluate separately | May not reflect dependency status, yet not every runtime error should be automatically ignored. |

For instance, HTTP 404 may mean a product does not exist, whereas HTTP 401 may indicate misconfigured service-to-service credentials. Do not lump all HTTP 4xx errors into an ignore group without understanding their cause. Similarly, do not record every `RuntimeException` as a dependency error if it may include programming bugs or business rule violations.

With HTTP clients, examine the actual exception types thrown by the client. For example, Spring WebClient may throw `WebClientResponseException`; RestClient may also throw exceptions reflecting HTTP response status codes. Classify the exact exception types passed to the circuit breaker, or translate them into clear domain exceptions at the client boundary.

## Exception Scope: What Does the Circuit Breaker See?

A circuit breaker only classifies the outcome of the unit of work wrapped by it. For synchronous calls, this is typically the supplier or callable passed to `run`. Exceptions caught and handled inside that unit of work never reach the circuit breaker, so they are not recorded as call exceptions.

The following example catches the exception right inside the supplier:

~~~java
return circuitBreaker.run(() -> {
    try {
        return inventoryService.find(sku);
    } catch (SocketTimeoutException ex) {
        log.warn("Inventory request timed out", ex);
        return Inventory.unavailable(sku);
    }
}, fallback);
~~~

In this case, the supplier returns `Inventory.unavailable(sku)` normally. The circuit breaker sees a returned value, so it has no way of knowing that the inner call timed out. If you want the circuit breaker to record the timeout, let the appropriate exception escape the supplier and handle it in the fallback or outer calling layer.

Also pay attention to wrapped exceptions. Suppose the client throws `SocketTimeoutException`, but the adapter catches it and throws `InventoryClientException` with the timeout as its root cause. The circuit breaker receives `InventoryClientException` at the protected boundary. If only `SocketTimeoutException` is declared in `recordExceptions`, the wrapper class may not match that list. Declare the exception type that actually escapes the supplier, choose a suitable superclass, or use a classification predicate that inspects the cause if your Resilience4j version supports that approach.

~~~java
public Inventory find(String sku) {
    try {
        return remoteClient.find(sku);
    } catch (SocketTimeoutException ex) {
        throw new InventoryClientException(
                "Inventory service timed out", ex
        );
    }
}
~~~

With this conversion, the configuration needs to recognize `InventoryClientException` if that is the type escaping the protected call. Do not assume the circuit breaker will always traverse the entire `cause` chain to look for an inner exception.

## Java Configuration

Besides `application.yml`, you can build `CircuitBreakerConfig` in Java. The following example uses both exception lists:

~~~java
import java.io.IOException;
import java.net.SocketTimeoutException;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .recordExceptions(
                IOException.class,
                SocketTimeoutException.class,
                InventoryUnavailableException.class
        )
        .ignoreExceptions(
                InvalidSkuException.class,
                ProductNotFoundException.class
        )
        .build();
~~~

Then, you can apply the configuration to an ID via Spring Cloud CircuitBreaker's Resilience4j factory:

~~~java
@Bean
public Customizer<Resilience4JCircuitBreakerFactory>
        inventoryCircuitBreakerConfiguration() {

    return factory -> factory.configure(
            builder -> builder.circuitBreakerConfig(config).build(),
            "inventory-read"
    );
}
~~~

The configuration snippet above illustrates attaching a policy to the `inventory-read` ID. In a real project, place `config` in a bean or appropriate factory method so Spring manages its lifecycle, and use the exact packages and starter version managed by the project.

Avoid configuring the same instance from multiple sources without clearly defining which source takes precedence. If you use `application.yml` for exception lists and a Java customizer for other settings, verify how the factory merges them in the version you are using.

## Combining Exception Classification with Fallback

Fallback determines what the application returns when a call fails or when the circuit breaker rejects execution because it is OPEN. Exception classification and fallback selection are two distinct responsibilities.

~~~java
public Inventory findInventory(String sku) {
    return circuitBreakerFactory.create("inventory-read").run(
            () -> inventoryClient.find(sku),
            error -> {
                if (error instanceof ProductNotFoundException) {
                    return Inventory.notFound(sku);
                }
                return Inventory.unavailable(sku);
            }
    );
}
~~~

This is an illustrative example of `Inventory` model methods. If `ProductNotFoundException` is configured to be ignored, the circuit breaker does not increment the failure count for that exception, yet the fallback can still receive the exception and convert it into a business result. If `InventoryUnavailableException` is recorded as a failure, the fallback can return a temporary status or cached data.

Do not let a fallback hide every error behind a plausible-looking default result. For example, returning zero stock when the service is unreachable may cause the system to reject valid orders; returning stale cached quantities without marking them may cause the system to accept orders beyond available stock. Represent data status and fallback confidence explicitly.

If the fallback itself throws an exception, that exception may continue propagating to the caller. This does not alter the original classification of the supplier already recorded by the circuit breaker; handle fallback errors at an appropriate boundary and track them separately for monitoring.

## Testing Exception Classification

Test each exception group using calls with deterministic outcomes. With a count-based window, set a small minimum number of calls in test environments so state transitions are easy to observe.

| Scenario | Expected Outcome to Verify |
|---|---|
| Supplier throws an exception in `recordExceptions` | Failure count increments. |
| Supplier throws an exception in `ignoreExceptions` | Neither success count nor failure count increments. |
| Supplier throws an exception not matching the list when `recordExceptions` is configured | Counted as a success, unless a matching ignore rule applies. |
| An exception matches both record and ignore lists | The ignore rule takes precedence. |
| Supplier catches the exception and returns a normal result | The circuit breaker records the returned result and does not see the caught exception. |
| Adapter wraps a timeout in a domain exception | Confirm the exception type at the supplier boundary is classified properly. |
| Ignored exception flows through fallback | The fallback can still handle the propagated exception. |
| Circuit is OPEN | New calls are rejected; the fallback handles the not-permitted case. |

During testing, inspect success, failure, and ignored call counts along with circuit breaker state. If a business exception raises the failure rate, review the record and ignore lists. If timeouts fail to raise the failure rate, inspect the actual exception at the supplier boundary, exception translation logic, and whether errors are being caught too early.

## Design Principles

1. Identify which exceptions indicate a dependency is unavailable or unable to meet deadlines.
2. Use `recordExceptions` to capture error types that should affect the failure rate.
3. Use `ignoreExceptions` for business errors or invalid inputs that do not reflect dependency health.
4. Remember that when a record list is configured, non-matching exceptions are generally counted as successes unless ignored.
5. Classify according to the exception type that actually escapes the protected unit of work; watch out for caught or wrapped exceptions.
6. Let fallbacks shape the outcome for callers while keeping circuit breaker classification semantics separate.
7. Test fast errors, timeouts, business errors, and wrapped exceptions before deploying configurations to production.

With Spring Cloud CircuitBreaker backed by Resilience4j, accurate exception classification ensures the sliding window reflects true dependency failures. `recordExceptions` defines which errors count toward the failure rate; `ignoreExceptions` excludes exceptions unrelated to dependency health from statistics. By properly defining call boundaries and actual exception types, the circuit breaker can open when needed to protect the system without reacting improperly to normal business outcomes.
