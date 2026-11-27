# Distinguishing Request-Creation Errors from Response-Handling Errors

## Why Distinguish These Two Error Groups?

When a Spring Cloud application calls a dependent service synchronously, the calling thread waits until the HTTP client returns a result or throws an exception. The Circuit Breaker observes the outcome of the call to assess the health of the dependent service. Therefore, it is necessary to determine at which stage an error occurred and whether that error truly reflects the target service's ability to serve requests.

The two common groups are:

- **Request-creation errors:** the application fails to construct a valid request before sending it, such as missing input data, malformed URIs, invalid parameters, or request body serialization failures on the client side.
- **Errors during sending and receiving the response:** the request has entered the HTTP client, but the client cannot connect, fails to send, times out waiting, or receives an error response from the dependent service.

Errors in the first group usually reflect the caller's own data or code. Counting them toward the failure rate can cause the Circuit Breaker to open even though the dependent service is operating normally. The second group usually signals connectivity or availability problems with the target service and generally needs to be recorded.

## Stages of a Synchronous Call

A synchronous HTTP call can be viewed as a sequence:

```text
Receive input data
        |
        v
Validate data and build URI/request
        |
        v
Serialize request body
        |
        v
Acquire connection / DNS resolution / TLS / send request
        |
        v
Wait for response headers and body
        |
        v
Parse response and handle HTTP status
        |
        v
Return result to business logic
```

Errors can occur at multiple points. For example, a malformed URI can be detected before any network activity happens. By contrast, `Connection refused`, DNS failures, TLS handshake errors, or read timeouts occur while the HTTP client is communicating with the dependent service. An HTTP 500 response indicates the server answered and reported an error; this is not a request-creation error.

Timeouts while waiting for a response must be handled carefully. The client did not receive a response within the configured deadline, but that does not prove the server never processed the request. The server may have executed a write operation before the response was lost on the return path. For non-idempotent operations such as order creation or charging money, blind retries can cause duplicate side effects.

## Identifying Request-Creation Errors

Common request-creation errors include:

| Error | Example | Handling |
| --- | --- | --- |
| Input validation failure | Blank product code, negative quantity, missing required field. | Return a validation error at the application layer before invoking the Circuit Breaker. |
| URI construction failure | Invalid base URL or path parameter. | Validate configuration and encode parameters before the call. |
| Request body serialization failure | Object cannot be serialized to JSON due to invalid structure or converter. | Fix the DTO, converter, or data; do not treat this as a target service failure. |
| Missing client configuration | Base URL, header, or credentials not configured. | Fix application configuration and explicitly decide whether it should count toward the protection policy. |

Perform validation and construct verifiable request values before entering the region protected by the Circuit Breaker. This ensures the Circuit Breaker observes only actual dependency calls. Some body conversion errors only surface once the HTTP client begins executing; if that step cannot be moved outside the protected region, identify the specific local exception type and configure the breaker to ignore it.

Do not ignore every `RuntimeException` or every `RestClientException` just because some exceptions in those hierarchies originate on the client side. Those broad exception classes also cover connection errors, response-reading errors, and server errors; ignoring them would prevent the Circuit Breaker from detecting real outages it is meant to guard against.

## Identifying Request-Sending and Response-Receiving Errors

Errors during communication with a dependent service typically include:

| Error | Example | Meaning for Circuit Breaker |
| --- | --- | --- |
| Unable to connect | Connection refused, DNS resolution failure, TLS handshake failure. | Usually recorded as a dependency call failure. |
| Connect or read timeout | Failed to establish connection within deadline or waited too long for response. | Usually recorded as a failure; timeouts must be set on the HTTP client. |
| Server 5xx response | HTTP 500, 502, 503, 504. | Usually recorded as a failure since the service or gateway reported it could not process the request. |
| Client 4xx response | HTTP 400, 401, 403, 404. | Usually a bad request, authorization issue, or business outcome; recording policy should be decided separately. |
| Rate-limit response | HTTP 429. | Can be treated as an overload signal from the dependent service and recorded as a failure; consider `Retry-After` and retry policy. |
| Malformed response body | JSON does not match DTO or is missing required fields. | May indicate a service contract violation; record and investigate rather than assuming caller input error. |

HTTP 4xx does not mean all such responses are harmless. For example, 404 can be a normal business outcome if a resource does not exist; 401 or 403 can indicate misconfigured credentials or permissions; 429 can indicate the dependent service is overloaded. Classify them according to the API contract instead of applying a single blanket rule to all 4xx codes.

## Example with RestTemplate

`RestTemplate` typically throws `ResourceAccessException` for resource access failures such as connection errors or timeouts. Under the default error handler, HTTP 4xx and 5xx responses are translated into exceptions under `HttpStatusCodeException`: 4xx maps to `HttpClientErrorException`, and 5xx maps to `HttpServerErrorException`.

Example building the request first, then protecting only the network call:

```java
@Service
public class CatalogService {
    private final RestTemplate restTemplate;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public CatalogService(
            RestTemplate restTemplate,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restTemplate = restTemplate;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public CatalogItem find(String productId) {
        validateProductId(productId);
        URI uri = URI.create("https://catalog.internal/items/" +
            UriUtils.encodePathSegment(productId, StandardCharsets.UTF_8));

        return circuitBreakerFactory.create("catalog").run(
            () -> restTemplate.getForObject(uri, CatalogItem.class),
            error -> CatalogItem.unavailable(productId)
        );
    }

    private void validateProductId(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("productId is required");
        }
    }
}
```

`validateProductId` and URI construction happen before `run`, so validation errors or invalid URIs are not counted as dependency call outcomes. In production code, prefer a URI builder to encode path segments properly and avoid manual URL string concatenation; the snippet above focuses on illustrating the boundary between request preparation and the protected call.

The fallback in this example returns an undetermined product state. The application should represent that state clearly so the caller does not confuse it with a missing product. If 404 needs to be distinguished from 503, the fallback should inspect the exception type and return the corresponding business outcome.

## Configuring Exception Classification

With `RestTemplate`'s default error handler, you can ignore certain client errors identified as business outcomes or request errors while keeping connection errors and server responses in the failure statistics. Resilience4j allows configuring an exception-ignoring predicate:

```java
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.http.converter.HttpMessageNotWritableException;
import org.springframework.web.client.HttpClientErrorException;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

@Bean
Customizer<Resilience4JCircuitBreakerFactory> catalogFailurePolicy() {
    return factory -> factory.configureDefault(id -> {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .ignoreException(error -> {
                if (error instanceof HttpMessageNotWritableException) {
                    return true;
                }
                return error instanceof HttpClientErrorException clientError
                    && clientError.getStatusCode().is4xxClientError()
                    && clientError.getStatusCode().value() != 429;
            })
            .failureRateThreshold(50)
            .slidingWindowSize(20)
            .minimumNumberOfCalls(10)
            .build();

        return new Resilience4JConfigBuilder(id)
            .circuitBreakerConfig(config)
            .build();
    });
}
```

This example uses Resilience4j's default policy for recording exceptions, except for those matched by the ignore predicate. 4xx responses (excluding 429) are excluded from statistics; `HttpMessageNotWritableException` represents a client-side request body serialization failure and is also ignored. 5xx and `ResourceAccessException` remain recorded as failures. `HttpMessageNotReadableException` during response parsing is not ignored because it may indicate the server returned a body violating the contract.

This policy is only a sample choice. If 401 or 403 signals that the dependent service cannot authenticate due to expired credentials, operations teams may want to monitor them separately or count them in a different metric. If 404 is a normal business error, translate it into an explicit domain outcome or ignore it in the predicate. Because 429 signals overload, the example above intentionally keeps it in failure statistics.

The ignore predicate only affects Circuit Breaker statistics. The exception can still reach the fallback or caller; ignoring does not mean swallowing the error.

## When the HTTP Client Does Not Throw Exceptions for Error Statuses

Some HTTP clients or custom error handlers return a response normally even when the status is 5xx. In that case, the Circuit Breaker sees the supplier complete normally and may record a success. `recordException` cannot classify a status if no exception is thrown.

There are two ways to handle this:

1. Configure the HTTP client to translate statuses needing protection into typed exceptions, then use exception predicates to record them.
2. If the API returns a response type carrying a status, use `recordResult` to evaluate the return value according to the Resilience4j version's contract.

Example with an application-defined response type:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .recordResult(result ->
        result instanceof CatalogResponse response
            && response.statusCode() >= 500
    )
    .build();
```

Do not mark all 4xx results as infrastructure failures. The application needs to distinguish validation errors, resource not found, unauthorized access, and rate limiting based on API semantics.

## Timeouts and Retry Safety

A Circuit Breaker does not automatically enforce a deadline on an in-flight synchronous call. If the HTTP client lacks a connect timeout and response/read timeout, the calling thread can be blocked for a long time even while the Circuit Breaker is `CLOSED`. Configure timeouts on the HTTP client or use `TimeLimiter` appropriate to the integration mechanism.

Distinguish between:

- **Connection timeout:** maximum time allowed to establish a connection.
- **Response/read timeout:** maximum time spent waiting for response data or a single read depending on client configuration.
- **Overall deadline:** total time the business operation permits for the entire call, including connection, sending, and receiving data.

When a read timeout occurs, the client cannot know how far the server progressed in processing the request. For write operations, use an idempotency key or deduplication mechanism on the target service before retrying. Do not automatically retry all timeouts, 5xx, or 429 errors; retries must be bounded in count, use backoff and jitter, and stay within the overall deadline.

## Verifying Behavior with Scenarios

You can use a mock HTTP server or a mocked `RestTemplate` to simulate scenarios and observe metrics:

| Scenario | Expected Error | Statistical Outcome Under Sample Policy |
| --- | --- | --- |
| Blank `productId` | `IllegalArgumentException` before `run` | Does not enter Circuit Breaker. |
| Request body fails to serialize | `HttpMessageNotWritableException` | Ignored. |
| Cannot connect to server | `ResourceAccessException` | Failure. |
| Server returns HTTP 503 | `HttpServerErrorException` | Failure. |
| Server returns HTTP 404 | `HttpClientErrorException` | Ignored under sample policy; application still handles exception/fallback. |
| Server returns HTTP 429 | `HttpClientErrorException` | Failure under sample policy. |
| Server returns malformed JSON | Response conversion error | Recorded if the exception is not ignored. |

Inspect the Circuit Breaker state, success/failure call counts, and ignored exception counts. Do not rely solely on the final HTTP status received by the end client, because a fallback can turn an exception into an alternative response.

## Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| Every exception in a synchronous call is a dependent service error. | Some errors arise during data validation, URI construction, or request serialization on the caller side. |
| HTTP 500 is a request-creation error. | It is a response from the server reporting a processing failure. |
| HTTP 404 is always an infrastructure failure. | It can be a normal business outcome, depending on the API contract. |
| Ignoring an exception means it is not propagated outward. | The predicate only controls statistics; the fallback and caller can still receive the exception. |
| A read timeout proves the server did not execute the operation. | The server may have processed the request while the response failed to reach the client. |
| Circuit Breaker replaces connect/read timeouts. | Timeouts must be configured separately on the HTTP client or TimeLimiter. |

By placing the right boundary between request preparation and the dependency call, and classifying responses and exceptions according to the API contract, the failure rate more accurately reflects the target service's health. This enables the Circuit Breaker in Spring Cloud to open when the dependent service is genuinely having trouble, rather than reacting to local data errors from the caller.
