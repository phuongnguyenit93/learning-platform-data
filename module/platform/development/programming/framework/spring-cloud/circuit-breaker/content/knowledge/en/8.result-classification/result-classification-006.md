# Converting HTTP Status Codes into Errors Before Circuit Breaker Recording

When calling an HTTP service, receiving an HTTP response does not mean the business operation succeeded. A `503 Service Unavailable` or `504 Gateway Timeout` response indicates the dependency is having trouble, yet if the application simply returns an object containing the status code as a normal result, the Circuit Breaker may treat that call as a success. For the Circuit Breaker to record failures accurately, HTTP status codes treated as dependency errors must be converted into exceptions before the outcome passes through the breaker.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, outcome classification is part of implementing Circuit Breakers in Spring Cloud and Resilience4j. We must distinguish infrastructure errors from business outcomes like resource-not-found, then decide which exceptions count toward the sliding window, which are ignored, and when to run a fallback.

## 1. Why Should HTTP Status Codes Be Converted into Exceptions?

The Circuit Breaker observes the outcome of the call it wraps. With the synchronous API, a call normally counts as a success when `Supplier<T>` returns a value and as a failure when it throws an exception. With the reactive API, a publisher completing normally is a success; a publisher emitting `onError` is a failure.

Suppose an Order service calls an Inventory service:

| Response from Inventory Service | Possible Meaning | Common Classification |
| --- | --- | --- |
| `200 OK` | Inventory lookup succeeded | Successful outcome |
| `404 Not Found` | SKU does not exist or resource not found | Usually a business outcome; not necessarily a dependency failure |
| `400 Bad Request` or `422 Unprocessable Entity` | Submitted payload is invalid | Input or business error needing separate handling |
| `401 Unauthorized` or `403 Forbidden` | Invalid authentication or permissions | Configuration or security issue needing investigation |
| `429 Too Many Requests` | Dependency is throttling traffic | May be treated as a transient error or rate-limited state |
| `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout` | Dependency or gateway encountered a failure | Usually counted as a dependency failure |

If a client returns `ResponseEntity<Inventory>` with status 503 without throwing an exception, the code wrapped by the Circuit Breaker completes normally. In that case, the Circuit Breaker has no failure signal to raise the failure rate. Status checking and exception throwing must occur inside the operation protected by the Circuit Breaker.

Desired processing flow:

~~~mermaid
flowchart TD
    A[HTTP call to dependent service] --> B[Read HTTP status]
    B --> C{Status counts as error?}
    C -->|No| D[Return normal result]
    C -->|Yes| E[Convert status to appropriate exception]
    D --> F[Circuit Breaker observes outcome]
    E --> F
    F --> G{Is exception ignored?}
    G -->|Yes| H[Exclude from failure rate]
    G -->|No| I[Record failure in sliding window]
~~~

The Circuit Breaker can only classify what the call delivers to it. If the HTTP client turns an error into a normal return value, normalize that value into an exception before the Circuit Breaker evaluates it.

## 2. Default Behavior of RestTemplate and WebClient

Spring's two common HTTP clients differ in API surface for status handling, yet both support converting error statuses into exceptions.

### RestTemplate

By default, `RestTemplate` uses `DefaultResponseErrorHandler`. This error handler treats 4xx and 5xx status codes as errors and throws an exception during execution—typically `HttpClientErrorException` for 4xx and `HttpServerErrorException` for 5xx. These exceptions belong to Spring Web's exception hierarchy.

Therefore, under default configuration, the call can be wrapped directly:

~~~java
public Inventory getInventory(String sku) {
    return circuitBreaker.run(
            () -> restTemplate.getForObject(
                    inventoryUrl + "/items/{sku}",
                    Inventory.class,
                    sku),
            failure -> fallbackInventory(sku, failure)
    );
}
~~~

If the Inventory service returns 503, `RestTemplate` throws an exception inside the `Supplier`. The Circuit Breaker receives that exception and applies its failure-recording policy. The fallback function receives the cause through the `failure` parameter.

If the application installs a custom `ResponseErrorHandler` that does not treat a given status as an error, `RestTemplate` may return a normal response for that status. In that case, inspect the status and throw an exception directly inside the `Supplier` before returning to the Circuit Breaker.

### WebClient

With `WebClient`, using `retrieve()` converts 4xx and 5xx statuses into `WebClientResponseException` by default. You can customize this conversion with `onStatus` to produce exceptions carrying application semantics:

~~~java
Mono<Inventory> primary =
        webClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .onStatus(
                        HttpStatusCode::isError,
                        response -> response.bodyToMono(String.class)
                                .defaultIfEmpty("")
                                .map(body -> mapInventoryError(
                                        response.statusCode().value(),
                                        body))
                )
                .bodyToMono(Inventory.class);
~~~

The `mapInventoryError` method returns an exception based on the status. `onStatus` requires the mapping function to return a publisher containing the exception; when the primary publisher is subscribed to, the exception is emitted as an `onError` signal.

Example classification helper:

~~~java
private RuntimeException mapInventoryError(int status, String responseBody) {
    if (status == 404) {
        return new InventoryNotFoundException();
    }
    if (status == 400 || status == 422) {
        return new InventoryRequestException();
    }
    if (status == 408 || status == 429 || status >= 500) {
        return new DownstreamUnavailableException(status);
    }
    return new DownstreamHttpException(status);
}
~~~

Exceptions such as `InventoryNotFoundException`, `InventoryRequestException`, `DownstreamUnavailableException`, and `DownstreamHttpException` are illustrative application-defined business classes. You can retain the status code inside the exception for logging and monitoring without re-parsing the response body.

In Spring Framework 6, predicates typically accept `HttpStatusCode`; older versions may require the corresponding `HttpStatus` type. Adjust the signature to match your Spring version.

### When Using exchangeToMono

`retrieve()` provides built-in handling for 4xx and 5xx status codes. With `exchangeToMono()`, the application decides how to handle every response itself. Therefore, you must proactively emit an error signal for statuses the Circuit Breaker should record:

~~~java
Mono<Inventory> primary =
        webClient.get()
                .uri("/items/{sku}", sku)
                .exchangeToMono(response -> {
                    if (response.statusCode().isError()) {
                        return response.createException()
                                .flatMap(error -> Mono.<Inventory>error(error));
                    }
                    return response.bodyToMono(Inventory.class);
                });
~~~

If you skip the status check branch and simply read the body, an error response may be processed as normal data depending on how the body decodes. When using `exchangeToMono`, decide explicitly which status codes produce exceptions, which become business outcomes, and which should be ignored.

## 3. Placing Error Conversion Inside the Circuit Breaker

The wrapping order determines whether the Circuit Breaker sees the exception. With reactive calls, build the HTTP publisher that already includes status-to-exception conversion, then pass that publisher to `ReactiveCircuitBreaker.run`:

~~~java
public Mono<Inventory> getInventory(String sku) {
    ReactiveCircuitBreaker circuitBreaker =
            reactiveCircuitBreakerFactory.create("inventory");

    Mono<Inventory> primary = webClient.get()
            .uri("/items/{sku}", sku)
            .retrieve()
            .onStatus(
                    HttpStatusCode::isError,
                    response -> response.bodyToMono(String.class)
                            .defaultIfEmpty("")
                            .map(body -> mapInventoryError(
                                    response.statusCode().value(),
                                    body))
            )
            .bodyToMono(Inventory.class);

    return circuitBreaker.run(
            primary,
            failure -> fallbackInventory(sku, failure)
    );
}
~~~

In this flow:

1. `WebClient` sends the request and receives the response.
2. `onStatus` converts error status codes into exceptions.
3. The primary publisher emits `onError` if the response falls into a mapped error group.
4. The Circuit Breaker observes the error signal and updates metrics per configuration.
5. The fallback is invoked to produce a backup response if one was supplied by the application.

For synchronous calls, the same principle applies: status checking and exception throwing must stay inside the `Supplier` passed to `circuitBreaker.run`.

Do not catch the exception and return a default value inside the primary operation if you want the Circuit Breaker to record the failure. The following example swallows the error signal:

~~~java
// Not suitable if you want the Circuit Breaker to record HTTP errors.
Mono<Inventory> primary = webClient.get()
        .uri("/items/{sku}", sku)
        .retrieve()
        .bodyToMono(Inventory.class)
        .onErrorReturn(Inventory.unavailable());

return circuitBreaker.run(primary, failure -> fallbackInventory(sku, failure));
~~~

`onErrorReturn` converts the error signal into a normally emitted value before the publisher enters the Circuit Breaker. The Circuit Breaker may record the call as a success and skip its fallback. Let the error propagate to the Circuit Breaker, then handle it in the fallback passed to the Circuit Breaker or at an outer layer after the error has been recorded.

## 4. Distinguishing Dependency Errors from Business Errors

Do not turn every 4xx status into the same infrastructure error. For instance, 404 may simply mean a SKU does not exist. If every lookup of a missing SKU raised the failure rate, the Circuit Breaker could open even while the Inventory service is operating normally.

One approach is mapping status codes into distinct exceptions:

| HTTP status | Application Exception | Suggested Circuit Breaker Policy |
| --- | --- | --- |
| 404 | `InventoryNotFoundException` | Exclude from error calculations if this is a normal business outcome |
| 400, 422 | `InventoryRequestException` | Handle as input validation error; usually excluded from dependency failure counts |
| 408 | `DownstreamUnavailableException` | Usually recorded as a transient error |
| 429 | `DownstreamUnavailableException` or dedicated rate-limit exception | Choose per retry, rate-limit, and operational policy |
| 500–599 | `DownstreamUnavailableException` | Usually recorded as a dependency failure |
| 401, 403 | `DownstreamHttpException` or dedicated security exception | Investigate credentials and permissions; decide dedicated policy |

For example, Resilience4j configuration can ignore business exceptions:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        ignoreExceptions:
          - com.example.InventoryNotFoundException
          - com.example.InventoryRequestException
~~~

Exceptions listed in `ignoreExceptions` are counted as neither successes nor failures in the sliding window. They do not increase the failure rate. Other exceptions follow the default recording policy or configured `recordExceptions` properties.

If `recordExceptions` is declared, note that exceptions not matching the record list will not count as errors under that policy; list every exception that should be counted. `ignoreExceptions` takes exclusion precedence for specified exceptions. Do not add `recordExceptions` just to record one error type without assessing the impact on all other exceptions.

Ignoring an exception in the Circuit Breaker does not mean ignoring error handling in the business layer. The API can still return 404 or 400 to the client, log appropriately, and show meaningful messages; only the dependency health calculation excludes those outcomes as failures.

## 5. Fallback Receiving Classified Exceptions

Once status codes have been mapped into exceptions, the fallback can decide how to respond based on the cause:

~~~java
private Mono<Inventory> fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof InventoryNotFoundException) {
        return Mono.error(failure);
    }

    return inventoryCache.findRecent(sku)
            .map(cached -> cached.withStale(true))
            .defaultIfEmpty(Inventory.unavailable());
}
~~~

In this example, the missing-SKU error is forwarded so the business layer returns the right result. For dependency failures or calls rejected by the Circuit Breaker, the application tries cached data and marks it stale. If no cache entry exists, it returns an indeterminate inventory state.

The fallback must not turn every error into zero inventory. A value of 0 can signify confirmed out-of-stock, whereas an unavailable status signifies unable to verify. These two outcomes differ and directly affect order placement decisions.

For synchronous APIs, you can apply the same classification approach:

~~~java
private Inventory fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof InventoryNotFoundException) {
        throw (InventoryNotFoundException) failure;
    }
    return inventoryCache.findRecent(sku)
            .orElseGet(Inventory::unavailable);
}
~~~

If the fallback itself throws an exception, the overall call can still fail. Track both how often fallbacks run and how often fallbacks fail to produce a result.

## 6. Verifying Circuit Breaker Recording of Error Statuses

Test each scenario using integration tests or component tests backed by a mock HTTP server:

| Scenario | Expected HTTP Client Outcome | Expected Circuit Breaker Outcome |
| --- | --- | --- |
| Service returns 200 | Publisher completes normally or returns object | Records success |
| Service returns 503 | Throws mapped exception | Records failure unless exception is ignored |
| Service returns 404 classified as business | Throws `InventoryNotFoundException` or returns explicit business result | Does not raise failure rate if exception is ignored |
| Circuit is OPEN | Call rejected by Circuit Breaker before sending HTTP request | Records rejection in appropriate metrics; fallback may run |
| Error handled by `onErrorResume` before Circuit Breaker | Publisher completes normally | May be recorded as success; avoid if wanting to count original failure |

In tests, verify more than just the final API return value. Verify the exact exception type emitted by the HTTP client, whether the fallback receives the expected exception, and whether the Circuit Breaker's failure rate changes as intended.

To inspect Resilience4j behavior, observe the instance's state and metrics across a series of test calls. Use small window sizes and minimum call counts in test environments to reproduce state transitions easily; never reuse those test numbers in production without evaluating real traffic.

## 7. Observability and Diagnostics

To verify HTTP status classification works effectively, monitor these metrics:

- Response counts broken down by status code per dependency.
- Exception counts by class, such as `DownstreamUnavailableException` and `InventoryNotFoundException`.
- Failure rate and slow call rate for each Circuit Breaker.
- Count of calls rejected by the Circuit Breaker while OPEN.
- Fallback invocation count and fallback success rate.
- HTTP client latency before a status is converted into an exception.

If logs show frequent HTTP 503 responses while the Circuit Breaker's failure rate stays flat, check whether the HTTP client returns the response as a normal value, whether a custom error handler skips that status, or whether an `onErrorResume` / `onErrorReturn` step handles the error before the Circuit Breaker.

If the failure rate spikes when many SKUs do not exist, revisit 404 mapping and `ignoreExceptions` configuration. If the circuit opens due to 401 or 403 errors, investigate credential and permission configuration instead of assuming a network outage.

When logging error response bodies, bound payload sizes and strip sensitive data. Do not store tokens, personal data, or private request payloads solely to diagnose status codes.

## 8. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning a response containing a 5xx status as a normal object | Circuit Breaker may record a success | Throw an exception inside the protected call |
| Using `onErrorReturn` before the Circuit Breaker | Errors become successful values before the Circuit Breaker sees them | Use the Circuit Breaker's fallback or handle errors at an outer layer |
| Treating all 4xx statuses as infrastructure errors | Business errors inflate the failure rate | Map status codes to meaningful exceptions and ignore appropriate ones |
| Checking status only after `circuitBreaker.run` returns | Circuit Breaker already observed the response before status turned into an exception | Move status checks inside the `Supplier` or primary publisher |
| Using `exchangeToMono` without handling the error status branch | Status codes may not become error signals as intended | Explicitly return `Mono.error(...)` for statuses to record |
| Overly narrow `recordExceptions` configuration | Some dependency failures go uncounted as errors | Verify the full list of recorded exceptions |
| Fallback returns fake data like zero stock | Clients mistake unknown state for accurate data | Return an unavailable state or timestamped cache entry |

## 9. Implementation Checklist

When integrating an HTTP client with a Circuit Breaker, follow these steps:

1. Identify which status codes represent dependency failures, which are business outcomes, and which need special handling.
2. Check the default behavior of your HTTP client: `RestTemplate`, `WebClient.retrieve()`, or `WebClient.exchangeToMono()`.
3. Convert status codes that should count as errors into exceptions inside the operation protected by the Circuit Breaker.
4. Set `ignoreExceptions` for business errors that should not inflate the failure rate; if using `recordExceptions`, verify all error types to count are included.
5. Supply a fallback to handle dependency failures and OPEN-circuit rejections while preserving business errors that must reach the client.
6. Test 200, 404, 503, and OPEN states; verify exceptions, fallbacks, and metrics alike.
7. Monitor status codes, failure rates, slow call rates, and fallbacks in production to refine the policy.

Converting HTTP status codes into exceptions at the right boundary lets the Circuit Breaker see dependent service failures and update its sliding window accurately. Classifying exceptions by business semantics ensures the protection mechanism reacts to infrastructure outages without mistaking outcomes like "not found" for a failing service.
