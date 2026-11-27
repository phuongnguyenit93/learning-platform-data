# HTTP Returns an Error but Is Still Recorded as Success

A dependent service may return HTTP 500, 503, or 429, yet the Circuit Breaker keeps incrementing its success counter. This typically happens when the HTTP client converts an error response into a normal result object, or when an error-handling operator turns an error signal into a successful completion signal before the Publisher passes through the Circuit Breaker.

Resilience4j does not automatically inspect every HTTP status. The Circuit Breaker observes the outcome emitted by the protected call: a return value is treated as a success by default; only an exception or error signal classified per configuration counts as a failure. Therefore, proper diagnosis requires tracing the response from the HTTP client, adapter, ErrorDecoder, or WebClient operator right up to the Circuit Breaker boundary.

This article belongs to the **Troubleshooting** chapter of the SPRING_CLOUD_CIRCUIT_BREAKER module. It covers identifying root causes, fixing HTTP status mapping, configuring `recordResult` when intentionally returning a response object, avoiding swallowing errors before the breaker, and verifying with events, metrics, and tests.

## 1. What Outcomes Does the Circuit Breaker See?

The Circuit Breaker does not directly inspect the business meaning of an HTTP response. It observes the outcome of the Supplier or Publisher inside the protected boundary.

| Outcome from Protected Call | How Circuit Breaker Typically Records It |
|---|---|
| Returns a normal Product or ResponseEntity object | Success |
| Returns a ResponseEntity with status 500 without throwing an exception | Success by default, unless `recordResult` is configured |
| Throws an exception | Failure according to predicate and exception configuration |
| Publisher emits `onError` | Failure according to predicate and exception configuration |
| Publisher completes with `onComplete` after `onErrorResume` returns a fallback value | Success if recovery happens before the breaker |
| Breaker is OPEN and rejects the call | Call not permitted; no HTTP request is sent to the dependency |

For example, an adapter might return a result object like this:

~~~java
public record CatalogResult(
    int httpStatus,
    String body
) {}
~~~

If the call returns `new CatalogResult(503, "...")` normally, the Circuit Breaker does not automatically know that status 503 is an error. To the breaker, the Supplier returned a valid value. To record it as a failure, either convert the response into an exception before leaving the boundary or configure a `recordResult` predicate to evaluate the result.

Three kinds of state must be distinguished:

- **HTTP status**: protocol-level result, such as 404, 429, or 503.
- **Exception/error signal**: how the client propagates errors to the calling code.
- **Circuit Breaker outcome**: success, failure, ignored, or not permitted according to how Resilience4j classifies outcomes.

An HTTP 500 can become an exception, a ResponseEntity object, or a payload containing an error code inside an HTTP 200. Those three representations can lead to three different Circuit Breaker outcomes.

## 2. Symptoms That HTTP Errors Are Being Counted as Successes

Start from observable symptoms:

- Downstream logs show 500/503 responses, yet Circuit Breaker metrics keep incrementing successful calls.
- Failure rate is 0 or unusually low even though the API client receives many error responses.
- The breaker does not open despite continuous dependency errors and sample counts exceeding `minimumNumberOfCalls`.
- Error responses are returned as DTOs or `ResponseEntity` rather than exceptions.
- Code contains `onErrorResume`, `onErrorReturn`, `onErrorComplete`, or a handler converting error statuses into values before calling the breaker.
- A custom ErrorDecoder or HTTP status handler returns a result object instead of throwing an exception.
- The payload contains `status: ERROR` or `success: false`, but the HTTP status is still 200.

A breaker not opening immediately after one error response is not necessarily a configuration bug. It only evaluates the rate after reaching the minimum number of samples, and only opens when the rate exceeds the threshold. During investigation, verify step by step: whether calls actually go through the breaker, which breaker ID is used, whether it receives an exception or a value, and whether the sliding window has enough samples.

## 3. Common Causes Across HTTP Clients

| Client or Invocation Style | Behavior to Check |
|---|---|
| OpenFeign | Does ErrorDecoder convert non-2xx responses into exceptions, or does a custom decoder return a normal result? Is the 404 decoding option enabled? |
| WebClient `retrieve()` | By default 4xx/5xx creates a WebClientResponseException; does any `onStatus` return `Mono.empty()` and suppress the error? |
| WebClient `exchangeToMono()` | Does the error status branch emit `Mono.error`, or does it still decode the body into a normal DTO? |
| RestTemplate | Default ResponseErrorHandler usually throws exceptions for 4xx/5xx; does a custom handler ignore error statuses? |
| RestClient | Does the status handler throw an exception or return the response as a normal value? |
| Custom HTTP wrapper | Does it convert error statuses into an `ApiResult` without throwing an exception? |
| API envelope | Does the server return HTTP 200 with a body containing a business or internal error code? |

Do not assume all HTTP clients behave the same way. Inspect the exact configuration and return types in use. Given the same 503 server response, one client may throw an exception while another returns a `ResponseEntity` for the caller to handle.

## 4. Fix for WebClient: Preserve the Error Signal Before the Circuit Breaker

With `WebClient.retrieve()`, 4xx/5xx statuses are converted into `WebClientResponseException` by default. As long as the code does not override that behavior with a status handler that drops the error, the Circuit Breaker can receive the error signal.

Example:

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCatalogService {
    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> breakerFactory;

    public ReactiveCatalogService(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> breakerFactory) {
        this.webClient = webClient;
        this.breakerFactory = breakerFactory;
    }

    public Mono<Product> findProduct(String id) {
        Mono<Product> remoteCall = webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .onStatus(HttpStatusCode::isError, response ->
                response.createException().flatMap(Mono::error))
            .bodyToMono(Product.class);

        return breakerFactory.create("catalog-read").run(
            remoteCall,
            error -> Mono.error(
                new CatalogUnavailableException(id, error))
        );
    }
}
~~~

The `onStatus` block converts error responses into an error signal. When the Publisher is subscribed through the Circuit Breaker, that error is observed by the breaker. The fallback callback receives the error cause and returns an alternative Publisher or propagates an error.

If using `exchangeToMono()`, check the status before decoding the body:

~~~java
Mono<Product> remoteCall = webClient.get()
    .uri("/products/{id}", id)
    .exchangeToMono(response -> {
        if (response.statusCode().isError()) {
            return response.createException().flatMap(Mono::error);
        }
        return response.bodyToMono(Product.class);
    });
~~~

This is clear when you need explicit control over how each status is handled. Do not decode a 503 response into a Product or an error DTO and emit it normally if the goal is for the Circuit Breaker to count it as a failure.

### Common Pitfall: onStatus Returning Mono.empty()

The snippet below explicitly tells WebClient that statuses matching the predicate do not need to be turned into errors:

~~~java
.retrieve()
.onStatus(HttpStatusCode::isError, response -> Mono.empty())
.bodyToMono(CatalogEnvelope.class);
~~~

When the callback returns `Mono.empty()`, WebClient does not emit an error signal for that status and continues processing the body as a normal response. If the body is decoded into `CatalogEnvelope`, the Circuit Breaker typically records a success.

This can be valid if the application intentionally treats that status as a normal business outcome. If 500/503 should count as availability errors, create an exception instead of returning `Mono.empty()`.

## 5. Fix for OpenFeign: ErrorDecoder Must Return an Appropriate Exception

Feign invokes `ErrorDecoder` when receiving a response considered non-success under Feign's rules. The decoder must return an exception so the call terminates with an error. If custom code turns an error status into a normal result at another layer, the Circuit Breaker may miss the failure.

Example ErrorDecoder classifying errors:

~~~java
import feign.Response;
import feign.codec.ErrorDecoder;

public class CatalogErrorDecoder implements ErrorDecoder {
    private final ErrorDecoder delegate = new ErrorDecoder.Default();

    @Override
    public Exception decode(String methodKey, Response response) {
        int status = response.status();

        if (status == 404) {
            return new ProductNotFoundException(
                "Product not found");
        }

        if (status == 503 || status == 502 || status == 504) {
            return new CatalogUnavailableException(
                "Catalog Service temporarily unavailable");
        }

        return delegate.decode(methodKey, response);
    }
}
~~~

In this example, 404 is a business outcome and is mapped to a dedicated exception so the application can exclude it from the failure rate if needed. Statuses 502/503/504 produce availability exceptions. The default decoder handles remaining statuses.

If 404 is configured to be decoded as a normal response, such as via Feign's dismiss/decode 404 option, verify the decoder and return type in use. In that case, a 404 response may go to the data decoder instead of ErrorDecoder. Exact behavior depends on the Feign version and Spring Cloud OpenFeign configuration.

Do not return a `CatalogError` DTO as a valid value for status 503 if the breaker needs to count a failure. If the API contract requires returning an error DTO to the caller, convert the status into an exception inside the protected boundary and let the fallback or an outer layer translate the exception into the appropriate HTTP response after the breaker has recorded the outcome.

## 6. Fix for RestTemplate or RestClient

By default, RestTemplate uses a ResponseErrorHandler to convert most 4xx/5xx responses into exceptions. If the application replaces the handler and lets every response pass through normally, the Circuit Breaker may only see a ResponseEntity.

For example, when intentionally returning a ResponseEntity, classify outcomes via `recordResult` or throw an exception inside the adapter:

~~~java
ResponseEntity<Product> response =
    restTemplate.getForEntity(url, Product.class);

if (response.getStatusCode().isError()) {
    throw new CatalogHttpException(
        response.getStatusCode().value());
}

return response.getBody();
~~~

This causes the call to fail with an exception on error statuses. If you need to return the raw ResponseEntity to the caller, use `recordResult` so the Circuit Breaker knows which statuses to count as failures.

With RestClient, check the status handler and how the method returns responses. If the status handler does not throw an exception, error statuses may still become normal results. Standardize conventions in the adapter so services do not have to guess statuses across multiple places.

## 7. When Should You Use recordResult?

Sometimes an application intentionally wants to return a response object, for instance to preserve the HTTP status and body for an API gateway or adapter layer. In that case, you can use Resilience4j's `recordResult` to specify which return values must be recorded as failures.

Example with `ResponseEntity`:

~~~java
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

@Bean
Customizer<Resilience4JCircuitBreakerFactory> catalogResultClassification() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .recordResult(result -> {
            if (result instanceof ResponseEntity<?> response) {
                int status = response.getStatusCode().value();
                return status == 429 || status >= 500;
            }
            return false;
        })
        .ignoreExceptions(ProductNotFoundException.class)
        .build();

    return factory -> factory.configure(
        builder -> builder.circuitBreakerConfig(config),
        "catalog-response"
    );
}
~~~

The predicate returns `true` when the response should be counted as a failure. In this example, 429 and all statuses 500 and above are failures; other statuses are considered successful according to the predicate. Adjust conditions to match your API contract. For instance, a 429 due to a user quota might be a business outcome, while 409 or 422 usually should not trip the breaker if the dependency processed the request normally.

When using `recordResult`, understand that the predicate must thoroughly classify all possible return types. Any result not matching the predicate is treated as a success under `recordResult` rules. Do not configure a predicate that checks only 500 if the application also needs to record 502, 503, 504, or 429.

If using `recordExceptions` to restrict which exceptions count as failures, exceptions outside that list may be treated as successes unless ignored. Avoid making the list overly narrow, which can cause newly introduced errors to be miscounted as successes. When you only need to exclude a few business errors, `ignoreExceptions` is usually clearer.

## 8. Distinguish HTTP Errors from Errors Inside the Payload

Some APIs always return HTTP 200 while representing errors in the body:

~~~json
{
  "success": false,
  "code": "CATALOG_UNAVAILABLE",
  "message": "Dependency is unavailable"
}
~~~

At the HTTP layer, this is a successful response. If the adapter decodes the body into a DTO and returns it normally, the Circuit Breaker records a success. If the application contract defines `success: false` as an availability error, convert that DTO into an exception or use `recordResult` to classify it.

Example converting payload to an exception:

~~~java
CatalogEnvelope envelope = catalogClient.fetch(id);

if (!envelope.success()
        && "CATALOG_UNAVAILABLE".equals(envelope.code())) {
    throw new CatalogUnavailableException(envelope.message());
}

return envelope.product();
~~~

Do not treat every `success: false` as an infrastructure failure. A payload might represent record not found, insufficient permissions, or a business rule violation. Only outcomes reflecting an unavailable or degraded dependency should affect the breaker's failure rate.

## 9. Avoid Swallowing Errors Before Entering the Circuit Breaker

In reactive flows, where error-handling operators are placed determines whether the breaker sees the error.

Wrong if the goal is to record the original error:

~~~java
Mono<Product> remoteCall = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class)
    .onErrorResume(error ->
        cache.findUsable(id)); // Error was already recovered before the breaker.

return breaker.run(remoteCall, error -> fallback(id, error));
~~~

When the cache returns a Product, the Publisher completes normally. The Circuit Breaker sees only a success and does not know the Catalog call failed.

Better to place the fallback in the Circuit Breaker's callback:

~~~java
Mono<Product> remoteCall = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class);

return breaker.run(
    remoteCall,
    error -> cache.findUsable(id)
        .switchIfEmpty(Mono.error(
            new CatalogUnavailableException(id, error)))
);
~~~

In this case, the Circuit Breaker observes the primary call's error before the fallback produces an alternative result. If you want further error handling after the breaker, attach `onErrorResume` to the already-protected Publisher. Avoid placing operators that recover into success values inside the original Publisher before calling `run`.

For synchronous calls, the same principle applies: do not catch exceptions and return a success-like DTO before the Supplier enters the breaker. If you need to translate the exception type, use `throw new ... (cause)` so the error outcome is preserved.

## 10. Classify Business Errors to Avoid False Breaker Trips

Not every HTTP 4xx is an availability error. Several statuses indicate the dependency is healthy and responded according to business rules.

| Status / Outcome | Typical Classification | Impact on Breaker |
|---|---|---|
| 404 product not found | Business outcome | Usually ignore |
| 400/422 invalid request | Request/business error | Usually ignore |
| 401/403 wrong service credentials | Integration or config error | Alert separately; deliberately decide record vs. ignore |
| 409 state conflict | Business outcome | Usually ignore |
| 429 throttling from dependency | Overload / rate limit | Can record |
| 500/502/503/504 | Server or gateway error | Usually record |
| Timeout / connection failure | Infrastructure error | Record |
| HTTP 200 with payload indicating dependency unavailable | Application-contract error | Convert to exception or `recordResult` |

Determine the origin of 429 responses. If it is a customer's business quota, it should not open the dependency's breaker. If it is rate limiting caused by an overloaded dependency, it may be a signal worth recording and possibly retrying in a bounded way according to `Retry-After`.

## 11. Verify That the Circuit Breaker Receives the Right Outcome

After fixing the adapter or configuration, verify with a controlled test. Do not check only the HTTP response; inspect metrics or events for the exact breaker ID.

A verification scenario:

1. Call the dependency returning 200; verify success count increases.
2. Call the dependency returning 503; verify failure count increases or `recordResult` classifies the response as a failure.
3. Call the dependency returning 404; verify business errors are ignored if configured to be.
4. For WebClient, verify `onStatus` emits an error signal rather than `Mono.empty` for availability statuses.
5. For Feign, verify `ErrorDecoder` returns an exception for statuses that should be recorded.
6. For HTTP 200 API envelopes, verify error payloads are mapped according to the application contract.
7. Trigger enough errors to exceed `minimumNumberOfCalls`; verify failure rate and breaker state change per threshold.
8. Verify the fallback is invoked after the breaker has observed the primary call's error.
9. Open the breaker and send a new request; verify `CallNotPermitted` does not trigger additional HTTP requests to the dependency.

You can monitor events such as `onSuccess`, `onError`, `onIgnoredError`, `onStateTransition`, and `onCallNotPermitted`. Resilience4j metrics generally expose successful, failed, slow, and not-permitted calls. Verify exact metric names and tags for your integration version.

If server logs show 503 while breaker successes increase, log the following as well:
- Breaker ID passed to `CircuitBreakerFactory.create(...)`.
- HTTP status received from the client.
- Object type returned by the Supplier or Publisher.
- Exception class or whether an error signal crosses the boundary.
- Whether any `onErrorResume`, custom decoder, or status handler converts errors into values.
- Whether any `recordResult`, `recordExceptions`, or `ignoreExceptions` configuration alters classification.

## 12. Diagnostic Flowchart

~~~mermaid
flowchart TD
    A["Downstream returns HTTP error"] --> B{"Does HTTP client emit exception/error signal?"}
    B -- "Yes" --> C{"Does error pass through Circuit Breaker?"}
    C -- "Yes" --> D{"Is exception ignored or not recorded?"}
    D -- "Yes" --> E["Check ignoreExceptions / recordExceptions"]
    D -- "No" --> F["Check minimum calls and failure threshold"]
    C -- "No" --> G["Check catch/onErrorResume before breaker"]
    B -- "No" --> H["Client returns response object or DTO"]
    H --> I{"Does recordResult classify status/payload?"}
    I -- "Yes" --> F
    I -- "No" --> J["Convert error to exception or add recordResult"]
~~~

This flowchart helps isolate the cause before adjusting thresholds. Do not raise `failureRateThreshold` or lower `minimumNumberOfCalls` to mask a classification bug. Ensure the breaker receives the correct outcomes first.

## 13. Mistakes to Avoid

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming Circuit Breaker reads HTTP statuses automatically | 500 response returned as an object counts as success | Convert status to exception or configure `recordResult` |
| Using `onStatus` returning `Mono.empty` for 5xx | WebClient continues as a normal response | Emit `Mono.error` for statuses that must be recorded |
| Using `onErrorResume` before the breaker | Primary error is replaced with a success-like value | Move fallback into the `run` callback or place handling after the breaker |
| Custom `ErrorDecoder` returning a DTO instead of an exception | Feign invocation can complete normally | Return an exception for statuses that must be recorded |
| Ignoring all 4xx/5xx | Breaker fails to reflect availability | Classify by status and API contract |
| Overly narrow `recordExceptions` | New exceptions may be treated as successes | Review predicate and intentionally add error types |
| Looking only at `CLOSED` state | Missing failure rate that hasn't hit threshold yet | Check metrics, events, and `minimumNumberOfCalls` |
| Raising thresholds to stop the breaker from opening | Masks classification or dependency issues | Fix adapter and outcomes first, then tune thresholds |

## Conclusion

An HTTP error being recorded as a success by the Circuit Breaker usually indicates that the status was converted into a normal value or the error signal was recovered before the protection boundary. Inspect the behavior of your HTTP client, ErrorDecoder, and status handlers; ensure availability errors become exceptions/error signals, or use `recordResult` when intentionally returning response objects. Classify business errors separately, avoid swallowing errors before the breaker, and verify with metrics and events under the exact ID. Only when the Circuit Breaker receives accurate outcomes will failure rates and `CLOSED`/`OPEN`/`HALF_OPEN` states reflect true dependency health.
