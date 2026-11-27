# Converting Selected HTTP Statuses to Errors to Trip the Circuit Breaker

When Spring Cloud Gateway forwards a request to a downstream service, that service may return an HTTP response with a 5xx code without throwing an exception in the Gateway processing flow. If relying solely on exceptions, a circuit breaker might treat a 5xx response as a normally completed call and fail to increase the failure rate. The Gateway CircuitBreaker filter solves this case using the `statusCodes` property: selected HTTP statuses are converted into error signals for the circuit breaker to record.

This configuration allows the Gateway to open the circuit when a service repeatedly returns failure status codes, such as 500, 502, 503, or 504. When the circuit is OPEN, the Gateway can fail fast on subsequent calls and route to a fallback. Choose status codes according to service semantics so business errors or client errors do not accidentally trip the circuit.

## Why Convert HTTP Statuses to Errors?

An HTTP response with code 500 is still a valid response at the protocol layer. The Gateway receives the response, reads the status, and can complete the reactive stream normally. Meanwhile, a circuit breaker typically evaluates call success or failure based on exceptions raised during the protected call.

If the Gateway does not convert selected status codes into exceptions, calls returning 500 may not be counted as circuit breaker failures. In that case, the downstream service could fail continuously while the circuit breaker stays CLOSED.

The `statusCodes` property lets you declare which HTTP codes should be treated as errors. When a response from the downstream service has a status matching the list, the Gateway CircuitBreaker filter generates an error signal for the circuit breaker. This signal participates in failure rate statistics just like a call exception.

Distinguish three cases:

- **Selected HTTP status:** Gateway converts the response into an error for the circuit breaker to record.
- **Unselected HTTP status:** the response continues passing through the Gateway as a normal HTTP outcome, unless another mechanism turns it into an error.
- **Exception during service call:** connection errors, timeouts, or execution errors already follow the exception path; no HTTP status is needed for the circuit breaker to detect them.

## Configuring statusCodes in the Gateway CircuitBreaker Filter

The following route example protects calls to the inventory service and treats certain 5xx codes as errors:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-route
          uri: lb://inventory-service
          predicates:
            - Path=/api/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventoryGateway
                fallbackUri: forward:/_fallback/inventory
                statusCodes:
                  - "500"
                  - "502"
                  - "503"
                  - "504"
~~~

In this configuration:

- `name` is the circuit breaker name used by the Gateway when creating the breaker.
- `fallbackUri` specifies the internal endpoint invoked when the circuit breaker falls back due to an error or being OPEN.
- `statusCodes` is the list of specific HTTP codes that the Gateway treats as failures of the protected call.
- `uri` is the target service; for example `lb://inventory-service` uses Spring Cloud's load-balancing mechanism.

Values in `statusCodes` are written as status code strings. These are specific codes such as 500 or 503, not wildcard expressions for an entire status family. If you want multiple 5xx codes treated as errors, list the applicable codes explicitly.

If you only want 503 to trigger circuit breaking, you can configure:

~~~yaml
statusCodes:
  - "503"
~~~

Do not habitually put all 4xx or 5xx codes into the list. Each code should reflect a condition that the application wants the circuit breaker to count as a dependency failure.

## Circuit Breaker Name and Resilience4j Configuration

The name in the `name` property must match the Resilience4j instance name if you want to apply a dedicated configuration for that route. For example, if the route uses `inventoryGateway`, you can configure:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryGateway:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

This example uses a window of 20 calls and starts evaluating the rate only when at least 10 samples exist. If the failure rate reaches 50%, the circuit breaker can transition to OPEN. Statuses selected in the Gateway have become call errors and therefore can contribute to this rate.

`statusCodes` and `failureRateThreshold` have distinct responsibilities:

| Setting | Responsibility |
|---|---|
| `statusCodes` | Determines which HTTP responses are converted to errors. |
| `failureRateThreshold` | Determines the failure rate in a large enough window to open the circuit. |
| `slidingWindowSize` | Determines the number of samples or time interval used to compute the rate. |
| `minimumNumberOfCalls` | Prevents rate evaluation before enough samples exist. |
| `waitDurationInOpenState` | Determines the wait duration before attempting recovery. |

A selected status does not necessarily open the circuit immediately. It is counted as one failed outcome; the circuit breaker still evaluates against the configured minimum number of calls, window, and threshold.

## Fallback When a Selected Status Occurs

When a status matches the list, the Gateway CircuitBreaker filter passes an error signal into the circuit breaker. If the error opens the circuit or the circuit is already OPEN, the filter can dispatch the request to the fallback declared with `forward:`.

A simple fallback handler can return a structured 503 response:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InventoryFallbackController {

    @RequestMapping("/_fallback/inventory")
    public ResponseEntity<Map<String, String>> inventoryUnavailable() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                        "code", "INVENTORY_TEMPORARILY_UNAVAILABLE",
                        "message", "The inventory service is currently unavailable"
                ));
    }
}
~~~

This is an internal Gateway endpoint invoked via `forward:/_fallback/inventory`. In a real application, the fallback response should follow the shared API contract, optionally including a correlation ID or retry guidance if operational policy allows.

The fallback should not fabricate a confirmed business outcome. If the inventory service does not respond, the Gateway should not return a stock count of 0 or assert the product is out of stock. Return an unavailable status or cached data with clear freshness labels if the business permits.

Avoid letting the fallback endpoint pass through the failing CircuitBreaker route itself. With `forward:`, map directly to an internal handler inside the Gateway without calling back into the same downstream service. If the fallback calls the failing service itself, it can create a loop or keep increasing load.

## Which HTTP Statuses Should Trigger Circuit Breaking?

Not every non-2xx status reflects a failure of the dependent service. Choose statuses based on origin and business meaning.

| HTTP status | Common meaning | Should it be included in statusCodes? |
|---|---|---|
| 500 Internal Server Error | The downstream service hit an unexpected processing error. | Usually appropriate if protecting against repeated server errors. |
| 502 Bad Gateway | A downstream gateway/proxy received an invalid response from upstream. | May be appropriate if the status originates from a dependent service or proxy. |
| 503 Service Unavailable | The service is temporarily unable to process requests. | Usually appropriate when indicating dependency unavailability. |
| 504 Gateway Timeout | A downstream component did not receive a timely response. | Usually appropriate if the status reflects dependency timeouts. |
| 400 Bad Request | Invalid request. | Usually inappropriate; input errors do not indicate dependency health. |
| 401 Unauthorized / 403 Forbidden | Missing authentication or insufficient permissions. | Usually requires separate handling; may be a configuration or access issue. |
| 404 Not Found | Resource does not exist. | Usually inappropriate for a circuit breaker if this is a normal business result. |
| 429 Too Many Requests | Client or service is rate-limited. | Select only when 429 genuinely indicates dependency overload per policy; avoid tripping the circuit due to caller quota. |

For example, if a user requests a nonexistent SKU and the inventory service returns 404, that can be a normal business outcome. Adding 404 to `statusCodes` can cause queries for missing products to raise the failure rate and falsely open the circuit.

Similarly, 401 or 403 usually indicates an authentication or authorization problem. Opening a circuit breaker does not fix an expired token or misconfigured permissions. Record and alert on these errors appropriately unless the system has a clear reason to treat them as dependency unavailability.

429 requires careful evaluation. If an upstream service returns 429 because the Gateway itself exceeded a global quota, you may want to throttle traffic or apply a RateLimiter. If 429 is a per-tenant or per-user limit, opening a circuit breaker shared across all callers can disrupt other valid requests.

## Distinguishing Status-to-Error Conversion from Changing the Client Response Status

`statusCodes` is not a configuration to rewrite HTTP responses. It enables the circuit breaker to recognize selected responses as failed outcomes. When fallback executes, the client typically receives the status returned by the fallback handler, such as 503 in the example above.

If a status does not match the list and no other exception occurs, the Gateway can pass the original response from the downstream service back to the client. For instance, a 404 not in the list can continue being returned as 404 instead of triggering fallback.

This preserves accurate HTTP semantics:

- Business statuses like 404 can continue reaching the client.
- Incident statuses like 503 can be used to trigger the circuit breaker.
- Fallbacks can return a controlled degraded status, usually 503 or a cached response per API contract.

Do not treat circuit breaking as a way to normalize all errors into 200 or hide error codes. Clients need to receive statuses that accurately reflect the guarantees the application can provide.

## Relationship with Exceptions and Error Classification

The Gateway CircuitBreaker filter can trip the circuit from two signal groups:

1. Exceptions occurring when calling the downstream service, such as connection errors or timeouts.
2. HTTP statuses in the `statusCodes` list, which the Gateway converts into exceptions for the circuit breaker to record.

Exceptions and selected statuses together participate in the circuit breaker policy. If the application configures custom exception classification in the Resilience4j backend, verify that exceptions generated from selected statuses are not inadvertently ignored.

Do not confuse HTTP statuses with exception classes. `statusCodes` identifies response codes; `recordExceptions` or Resilience4j predicates classify exceptions. When combining both mechanisms, test both the response status path and the exception path in integration tests.

For example:

- Service returns 503: Gateway converts the status into an error and the circuit breaker records a failure.
- Service is unreachable: HTTP client throws an exception; circuit breaker records it per exception configuration.
- Service returns an unselected 404: Gateway forwards the response normally and does not trigger fallback solely for this status.
- Circuit breaker is already OPEN: new calls are rejected before forwarding to the service; Gateway executes fallback if configured.

## Combining statusCodes with Timeouts and Retries

Status 504 can often signify a timeout at a proxy or downstream service. However, the Gateway can also raise a timeout exception itself if a call exceeds its configured time limit. These two cases differ in where the error signal originates, though both can contribute to the failure rate.

Retries must also be configured in a controlled way. If a 503 response is converted into an exception, retries may attempt again according to the route's or caller's retry policy. Retrying too many times can send extra requests to an already overloaded service. Only retry transient recoverable errors, cap attempt counts, and keep total elapsed time within the request deadline.

For write operations, a timeout or 5xx does not prove the upstream service did not execute the operation. Before retrying a write command, require an idempotency key or status lookup API to avoid creating duplicate transactions.

Circuit breaker and retry require a clear order. The circuit breaker should observe the final outcome of the unit of work the application wants to measure; if retry is placed inside, a retry sequence can be counted as one logical call. If retry sits outside, each attempt can pass through the circuit breaker individually depending on filter structure. Define your measurement objective before choosing placement.

## Observation and Diagnostics

When operating the Gateway, monitor response statuses and circuit breaker state separately:

- Response counts by HTTP status before error conversion.
- Counts of `statusCodes` triggering exceptions for the circuit breaker.
- Connection error and timeout counts.
- Failure rate and slow call rate by circuit breaker name.
- Circuit breaker transition counts across CLOSED, OPEN, and HALF_OPEN.
- Requests fast-rejected when the circuit is OPEN.
- Fallback invocation counts and fallback statuses returned.

The circuit breaker name in the route should be stable so metrics and dashboards group properly. Do not append path parameters, SKUs, user IDs, or request IDs to the name. Per-request values belong in logs or traces, while metrics need bounded-cardinality labels.

When you see a circuit open, diagnose the cause in order: which statuses are selected, which service emitted the status, whether connection/timeout errors are rising, what window and thresholds are active, and whether fallbacks spiked abnormally. If the circuit opened due to many business 404s or 429s, revisit the `statusCodes` list rather than merely raising failureRateThreshold.

## Testing statusCodes Configuration

Use a mock service capable of returning specific statuses to confirm the Gateway behaves properly. Verify the final client response, circuit breaker state, and fallback execution.

| Scenario | Expected verification |
|---|---|
| Service returns 200 | Response is forwarded to client; failure count does not increase from status. |
| Service returns 404 and 404 is unselected | 404 continues to client; fallback is not called solely due to this status. |
| Service returns 500 in the list | Gateway converts status to error; circuit breaker records failure. |
| Service returns 503 in the list | Fallback is called when circuit breaker/fallback conditions apply. |
| Service is unreachable | Exception is recorded per circuit breaker configuration. |
| Service responds slower than timeout | Timeout is recorded; fallback handles per configuration. |
| Failure rate reaches threshold | Circuit breaker transitions to OPEN and fast-rejects subsequent calls. |
| OPEN duration expires | Circuit breaker allows probe calls in HALF_OPEN. |
| Fallback endpoint fails | Gateway returns an appropriate error and records fallback failure separately. |
| Business statuses such as 401/404/429 | Confirm only selected codes trip the circuit. |

In tests, set a small sliding window and low minimumNumberOfCalls to observe state transitions easily. Then re-test with thresholds close to production traffic. Do not verify only that the client receives 503; confirm the status is converted to an error and contributes to the statistics of the intended circuit breaker.

## Implementation Checklist

1. Identify which HTTP statuses reflect downstream service failures for each route.
2. List only the specific codes that should trigger the circuit breaker in `statusCodes`.
3. Choose a stable circuit breaker name matching the Resilience4j instance.
4. Configure sliding window, minimum number of calls, and failure rate suitable for traffic volume.
5. Declare an internal fallback using `forward:` and ensure the fallback does not call back into the failing route.
6. Separate business statuses, auth errors, quotas, and infrastructure failures.
7. Coordinate timeouts and retries within the request budget; protect write operations with idempotency.
8. Monitor upstream statuses, status-to-error conversions, circuit breaker state, and fallbacks.
9. Test selected statuses, unselected statuses, exceptions, timeouts, and HALF_OPEN recovery.

In Spring Cloud Gateway, `statusCodes` enables converting selected HTTP responses into errors that the circuit breaker can measure. When the code list accurately reflects dependency failures, the Gateway can open the circuit before failures spread and route requests to a controlled fallback. Choose codes by business semantics, keep names consistent, and test both selected statuses and statuses that should continue returning to clients.
