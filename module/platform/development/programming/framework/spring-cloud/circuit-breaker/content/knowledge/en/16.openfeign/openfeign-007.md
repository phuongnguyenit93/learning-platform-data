# Coordinating Timeouts, ErrorDecoder, and Feign Retry Policies

When Spring Cloud OpenFeign calls a remote service, three mechanisms determine how the call ends: timeouts bound the wait duration, ErrorDecoder converts erroneous HTTP responses into exceptions, and Retryer decides whether to retry when a retryable error occurs. When OpenFeign is protected by Spring Cloud CircuitBreaker, the ordering and limits of these three mechanisms directly affect latency, load on dependencies, and Circuit Breaker failure metrics.

This topic belongs to the OpenFeign chapter in the SPRING_CLOUD_CIRCUIT_BREAKER module. The goal is to configure timeouts per Feign client, classify HTTP statuses using ErrorDecoder, retry only transient errors, and coordinate retries with the Circuit Breaker without exceeding deadlines or unintentionally repeating business operations.

## 1. Roles of the Mechanisms

| Mechanism | Responsibility | Question to Answer |
|---|---|---|
| Timeout | Limits connection and response wait time | How long is a single call allowed to wait? |
| ErrorDecoder | Converts unsuccessful HTTP responses into exceptions | Is this response a business error, infrastructure error, or retryable error? |
| Retryer | Decides whether to repeat a call upon encountering RetryableException | Can this error recover by retrying, and at most how many attempts? |
| Circuit Breaker | Tracks final call outcomes and blocks calls to a degraded dependency | Is the dependency repeatedly failing or slow? |

These mechanisms complement one another. Timeouts do not decide retries. ErrorDecoder does not perform retries itself; it only creates the appropriate exception. Retryer does not inspect every HTTP response directly; it handles RetryableException thrown by transport or ErrorDecoder. Circuit Breaker observes the outcome of the protected call to update its state.

A helpful rule is to retry only potentially transient errors and operations that are safe to repeat. Do not retry every 4xx or 5xx error simply because it appears as an exception.

## 2. Configuring Connect Timeout and Read Timeout

OpenFeign distinguishes two durations:

- Connect timeout: maximum time to establish a connection to the endpoint.
- Read timeout: maximum time waiting for response data after the connection is established, according to the semantics of the HTTP client in use.

With Spring Cloud OpenFeign, timeouts can be configured per Feign client name in application.yml:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalogClient:
            connectTimeout: 500
            readTimeout: 1200
            loggerLevel: basic
          paymentClient:
            connectTimeout: 700
            readTimeout: 1800
            loggerLevel: basic
~~~

Timeout values in the example are in milliseconds. The names catalogClient and paymentClient must match the client names declared by the application. You can place shared settings under the default key and override them for specific clients when needed.

Example Feign client declaration:

~~~java
@FeignClient(name = "catalogClient")
public interface CatalogClient {
    @GetMapping("/products/{id}")
    Product findById(@PathVariable("id") String id);
}
~~~

Do not set timeouts by guesswork. Measure normal and p95/p99 dependency latency, the end-to-end request time budget, gateway processing time, and remaining time for fallbacks. A read timeout that is too short creates false errors during brief fluctuations; one that is too long holds threads and connections while the dependency is slow.

Feign timeouts apply to each individual request attempt. If Retryer performs multiple attempts, the total duration can be much larger than the read timeout. Therefore, include retry count and backoff intervals in the total deadline calculation.

## 3. Classifying HTTP Responses with ErrorDecoder

Feign invokes ErrorDecoder when receiving an HTTP response outside the success range. ErrorDecoder converts that response into an exception. This is the right place to separate business outcomes from transient dependency failures.

For example, Catalog Service might return:

| HTTP Status | Meaning in Example | Desired Exception |
|---|---|---|
| 404 | Product does not exist | ProductNotFoundException, no retry |
| 400 or 422 | Invalid request or business rule unmet | CatalogRequestException, no retry |
| 401 or 403 | Service credentials or permissions issue | CatalogCredentialException, no automatic retry |
| 429 | Dependency is throttling via rate limit | RetryableException if contract permits retry |
| 502, 503, 504 | Gateway or dependency temporarily unavailable | Bounded retry possible |
| 500 | Server-side error | Retry only if service policy confirms error is transient |

Example ErrorDecoder:

~~~java
import feign.Response;
import feign.Request;
import feign.RetryableException;
import feign.codec.ErrorDecoder;

public class CatalogErrorDecoder implements ErrorDecoder {
    private final ErrorDecoder defaultDecoder = new ErrorDecoder.Default();

    @Override
    public Exception decode(String methodKey, Response response) {
        int status = response.status();

        if (status == 404) {
            return new ProductNotFoundException(
                "Product not found"
            );
        }

        if (status == 400 || status == 422) {
            return new CatalogRequestException(
                "Invalid catalog request"
            );
        }

        if (status == 401 || status == 403) {
            return new CatalogCredentialException(
                "Invalid Catalog Service credentials"
            );
        }

        if (status == 429 || status == 503) {
            if (response.request().httpMethod() == Request.HttpMethod.GET) {
                return new RetryableException(
                    status,
                    "Catalog Service is temporarily rate-limiting or shedding load",
                    response.request().httpMethod(),
                    null,
                    null,
                    response.request()
                );
            }

            return new CatalogTemporarilyUnavailableException(
                "Do not automatically retry write operations without confirmed idempotency"
            );
        }

        Exception decoded = defaultDecoder.decode(methodKey, response);
        if (decoded instanceof RetryableException
                && response.request().httpMethod() != Request.HttpMethod.GET) {
            return new CatalogTemporarilyUnavailableException(
                "Do not automatically retry write operations without confirmed idempotency"
            );
        }
        return decoded;
    }
}
~~~

In the example, 404 and bad request errors are converted to business exceptions; 401/403 are converted to credential errors requiring alerting and configuration fixes; 429/503 are marked as retryable. Other statuses are delegated to the default decoder.

This is an illustrative policy and must be adapted to the API contract. For example, 429 could represent a business quota for an account rather than dependency throttling, in which case you should not retry. Similarly, 503 could be scheduled maintenance; retrying continuously will not help. For 429/503 responses carrying a Retry-After header, the decoder should read and pass the retry timestamp into RetryableException so Retryer honors the server-requested wait time. The sample above passes null for the retry timestamp and thus uses local backoff; in production implementations, add Retry-After handling if the API provides this header.

ErrorDecoder only handles error HTTP responses. Connection errors such as DNS failure, connection refused, or socket timeout occur before a response arrives and are typically thrown as exceptions by the HTTP client. Transport errors may already be wrapped by Feign into RetryableException depending on error type and HTTP client; verify actual behavior in your running version and transport.

## 4. Spring Cloud OpenFeign Does Not Retry by Default

Core Feign and Spring Cloud OpenFeign have different defaults. Core Feign has a default Retryer capable of retrying certain errors. Spring Cloud OpenFeign registers Retryer.NEVER_RETRY by default, meaning failed requests are not automatically retried.

This is intentional: retries can multiply request volume while a dependency is overloaded and cause duplicate business operations. If you want retries, declare a Retryer explicitly with strict bounds.

Example configuring a dedicated Retryer for the Catalog client:

~~~java
import feign.Retryer;
import org.springframework.context.annotation.Bean;

public class CatalogFeignConfiguration {
    @Bean
    Retryer catalogRetryer() {
        // period=100 ms, maxPeriod=1000 ms, maxAttempts=3
        return new Retryer.Default(100, 1000, 3);
    }

    @Bean
    ErrorDecoder catalogErrorDecoder() {
        return new CatalogErrorDecoder();
    }
}
~~~

Attach the configuration to the specific client:

~~~java
@FeignClient(
    name = "catalogClient",
    configuration = CatalogFeignConfiguration.class
)
public interface CatalogClient {
    @GetMapping("/products/{id}")
    Product findById(@PathVariable("id") String id);
}
~~~

In this configuration, Retryer.Default only retries when receiving a RetryableException. The ErrorDecoder in the previous section decides which statuses produce that exception. 404, validation, and credential exceptions are not RetryableException, so they are not retried by this Retryer.

Keep client-specific configuration outside the application-wide component scan scope if you do not want it applied mistakenly to other Feign clients. If this configuration is registered globally, unrelated clients could also receive the same ErrorDecoder and Retryer.

## 5. Understanding Attempt Count and Backoff

Parameters of Retryer.Default include:

- period: initial wait interval before the next attempt.
- maxPeriod: maximum backoff interval.
- maxAttempts: maximum number of attempts as defined by Feign Retryer.

With Retryer.Default, maxAttempts equal to 3 means at most three total executions, consisting of the initial attempt plus up to two retries. Confirm the attempt count in logs during testing and read the exact Retryer semantics if using another implementation.

Backoff reduces synchronized retry bursts. If many instances fail simultaneously, immediate retries can create a secondary load spike on the dependency. In high-traffic systems, add jitter to spread out retry timing, and respect Retry-After if the server returns that header.

Never retry indefinitely. Once attempts are exhausted, Retryer rethrows the exception for the caller layer to handle. If a Circuit Breaker wraps the Feign invocation, that final outcome is used to record call success or failure.

## 6. In What Order Do Retry and Circuit Breaker Coordinate?

When Circuit Breaker is enabled for OpenFeign, Spring Cloud OpenFeign wraps the Feign call with a Circuit Breaker. Inside the Feign call, Retryer controls attempts of that single invocation. Therefore, the Circuit Breaker typically observes the final outcome of the invocation after Feign finishes retrying.

Overview flow:

~~~mermaid
flowchart TD
    A["Application calls Feign method"] --> B["Spring Cloud Circuit Breaker"]
    B --> C["Feign invocation"]
    C --> D["HTTP request with connect/read timeout"]
    D --> E{"Response or error"}
    E -- "Retryable error" --> F["ErrorDecoder or transport creates RetryableException"]
    F --> G{"Retryer has attempts left?"}
    G -- "Yes" --> H["Backoff then send next attempt"]
    H --> D
    G -- "No" --> I["Throw final exception"]
    E -- "Success or non-retryable error" --> J["Final invocation outcome"]
    I --> J
    J --> K["Circuit Breaker records outcome"]
    K --> L["Fallback or return result"]
~~~

This means one invocation can generate multiple HTTP attempts while the Circuit Breaker usually records a single final outcome for that invocation. If the first attempt returns 503 and the second succeeds, the breaker sees a successful invocation. If all attempts fail, the breaker records a failed invocation.

When the breaker is OPEN, calls may be rejected before Feign sends a request; Retryer never gets a chance to retry because the Feign invocation did not run. Do not retry CallNotPermittedException at the application layer, as doing so only creates additional rejected calls.

Avoid placing another retry loop outside the Circuit Breaker without careful calculation. If the service layer retries the entire invocation, each iteration can pass through its own breaker cycle and cause calls to grow exponentially. Pick one layer to own the retry policy and bound total attempts.

## 7. Calculating Deadlines Across Multiple Attempts

Per-attempt timeout is not the deadline for the entire invocation. Total duration can be approximated as:

~~~text
T_total <= N × (T_connect + T_read) + T_backoff + T_overhead
~~~

This is a conservative estimate; actual duration depends on when timeouts trigger, error types, and the HTTP client. For example, three attempts with a 1,200 ms read timeout plus backoff can exceed a 2-second API caller deadline.

Before enabling retries, calculate:

1. Caller or API gateway deadline.
2. Connect timeout and read timeout of a single attempt.
3. Maximum number of attempts.
4. Backoff between attempts and Retry-After duration.
5. Time reserved for Circuit Breaker fallback and response serialization.

If total duration could exceed the deadline, reduce timeouts or attempt counts. Do not let Feign continue retrying after the caller has canceled the request or the end-to-end deadline has expired.

## 8. Retry Only Safe Operations

Retries can cause the same request to be sent multiple times. For data-reading GETs, repeating is generally safer. For POSTs creating orders, payments, or reservations, the request may have been processed on the server while the response was lost. If the client retries, the operation could execute a second time.

Before retrying a write operation, ensure one of these guarantees:

- The API supports an idempotency key and the server stores outcomes by key.
- The operation has documented idempotent semantics.
- There is a status reconciliation check using a transaction ID before resending.
- Retries apply only to errors guaranteed to occur before the server executes the operation.

Do not infer from a timeout that the server never processed the request. For payments, if it is unknown whether the transaction was accepted, return an undetermined status and reconcile rather than automatically submitting a new transaction.

## 9. Enabling Circuit Breaker for OpenFeign

To integrate Spring Cloud OpenFeign with Spring Cloud CircuitBreaker, enable the property:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

The application needs the corresponding CircuitBreaker implementation starter, such as Resilience4j, alongside the OpenFeign starter. Once enabled, Feign calls are wrapped by a Circuit Breaker. You can configure fallback or fallbackFactory per client to return an alternative result when an invocation fails or the breaker rejects the call.

Example:

~~~java
@FeignClient(
    name = "catalogClient",
    configuration = CatalogFeignConfiguration.class,
    fallbackFactory = CatalogFallbackFactory.class
)
public interface CatalogClient {
    @GetMapping("/products/{id}")
    Product findById(@PathVariable("id") String id);
}
~~~

FallbackFactory lets you inspect why an invocation failed to choose an appropriate result. Do not turn every failure into a fake Product object. If cached data is unavailable or the fallback itself fails, return a service-unavailable error according to the API contract.

Circuit Breaker names are generated from the Feign client and method according to Spring Cloud OpenFeign's naming strategy. When configuring Resilience4j instances or viewing metrics, check the actual breaker name your application generates; do not assume the name is just the service ID.

## 10. Classifying Errors to Avoid Wrong Retries

A retry policy can start from the following table:

| Error Type | ErrorDecoder / Transport | Retry? | Circuit Breaker |
|---|---|---|---|
| 404 not found | ProductNotFoundException | No | Ignore if it is a valid business outcome |
| 400/422 | Request exception | No | Do not count as an availability failure if request validation follows contract |
| 401/403 | Credential exception | No automatic retry | Alert on configuration/permission error; decide recording separately |
| 429 throttling | RetryableException if recoverable | Bounded, honor Retry-After | Final failed outcome recorded per config |
| 503 temporary | RetryableException per policy | Bounded | If all retries fail, record failure |
| 502/504 | Per ErrorDecoder or transport | Bounded retry possible | Record final outcome |
| DNS/connect/read timeout | Transport exception | Retry only if error type is supported and operation is safe | Record final error / slow call |
| CallNotPermittedException | Breaker is OPEN | No | Already rejected by breaker |
| Bulkhead rejection | No local slots left | Do not retry immediately | Monitor separately; do not confuse with dependency failure |

Not every exception should be counted equally in the failure rate. You can configure Resilience4j to ignore classified business or credential exceptions, while not ignoring timeouts and connection errors if you want the breaker to detect dependency degradation.

## 11. Verifying Configuration and Retry Behavior

A test suite should observe both HTTP attempt counts and Circuit Breaker invocation counts:

1. Return 200: one attempt, successful outcome.
2. Return 404: ErrorDecoder creates a business exception; zero retry attempts.
3. Return 503 then 200: ErrorDecoder creates RetryableException, Retryer retries, final invocation succeeds.
4. Return 503 continuously: attempts do not exceed maxAttempts; final exception propagates to Circuit Breaker.
5. Return 429 with Retry-After: confirm Retryer waits according to the designed policy.
6. Trigger read timeout: confirm per-attempt timeout and that total duration does not exceed deadline.
7. Open Circuit Breaker: calls are rejected before sending a new HTTP request; Retryer does not run.
8. Call a non-idempotent POST: confirm no automatic retry without an idempotency key or reconciliation mechanism.

Log method key, status, attempt number, wait duration, exception class, and breaker state. Avoid logging Authorization headers, tokens, payment data, or sensitive payloads. Metrics should separate HTTP attempt count from Feign invocation count; looking at only one can misjudge actual load placed on the dependency.

## 12. Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Feign does not retry even though ErrorDecoder returns error | Spring Cloud OpenFeign uses Retryer.NEVER_RETRY by default | Declare a dedicated Retryer for the client |
| 404 is retried | ErrorDecoder turns a business error into RetryableException | Return a non-retryable exception for 404 |
| 503 retries too many times | maxAttempts or backoff is too large | Reduce attempts, add backoff/jitter, and compute deadline |
| Request exceeds gateway timeout | Per-attempt timeout multiplied by retry count | Calculate total budget before enabling retry |
| POST creates duplicate data | Retrying a non-idempotent operation | Use an idempotency key or status reconciliation |
| Circuit Breaker opens slowly despite many HTTP retries | Breaker records invocation outcome after internal retry loop | Monitor both attempts and invocations; tune retry/window intentionally |
| Retry config applies to all clients | Feign configuration was scanned globally | Scope configuration to the intended client |

## Conclusion

Timeouts bound the duration of each call attempt; ErrorDecoder classifies HTTP responses into exceptions; Retryer retries only errors marked retryable and must be bounded. Spring Cloud OpenFeign does not retry by default, so configure it explicitly per client only when genuinely needed. When coordinating with Circuit Breaker, understand that retries happen inside a Feign invocation, calculate total duration across all attempts and backoff, retry only safe operations, and let the breaker observe the final outcome. This coordination reduces cascading failures while preserving business semantics and request deadlines.
