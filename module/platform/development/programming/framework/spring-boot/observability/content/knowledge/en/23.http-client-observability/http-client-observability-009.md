# HTTP client status and outcome in Spring Boot

In the **HTTP client observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, status and outcome are two related but non-synonymous pieces of information when measuring outbound HTTP calls from an application. **HTTP status** is the response code returned by the server, such as 200, 404, or 503. **Outcome** is how instrumentation classifies the result of the client operation to aggregate metrics and investigate application behavior. A call may receive no HTTP response at all, thus having no status while still having an error outcome.

Spring Boot can instrument HTTP client requests via Micrometer Observation and integrations matching `RestClient`, `RestTemplate`, or `WebClient`. Observations typically provide dimensions such as `method`, URI template, client name, `status`, `outcome`, and `exception` depending on the stack/version. Distinguishing status from outcome helps dashboards show accurate error rates and avoids misunderstanding that every request completing at the HTTP layer is a business success.

In the **SPRING_BOOT_OBSERVABILITY** module, HTTP client metrics need to be linked with logs and distributed tracing to investigate slow dependencies, downstream errors, and retry behavior. This lesson moves from status/outcome semantics to how Micrometer creates observations, handles transport errors, retries, cardinality, and tests results.

## 1. How Do HTTP Status and Client Outcome Differ?

HTTP status describes the HTTP protocol response. Outcome describes the observed result from the client's perspective. For example:

| Scenario | HTTP status | Conceptual client outcome | Response received? |
| --- | ---: | --- | --- |
| Server returns data successfully | 200 | Success | Yes |
| Server creates resource | 201 | Success | Yes |
| Server redirects | 302 | Redirect | Yes |
| Resource does not exist | 404 | Client error | Yes |
| Request rate limited | 429 | Client error | Yes |
| Server temporarily unavailable | 503 | Server error | Yes |
| DNS fails to resolve | None | Transport error | No |
| TCP connection refused | None | Transport error | No |
| TLS handshake failed | None | Transport/TLS error | No |
| Client times out before receiving response | None | Timeout/transport error | No |

Some integrations may represent outcome using groups like `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR`, `REDIRECTION`, `UNKNOWN`, or other enums/labels depending on the version. Do not hard-code label names before inspecting your running stack's convention and metric output.

Key point: **status is a property of the HTTP response; outcome is the observed result classification of the client operation**. For DNS failures or timeouts before a response, status may be a fallback value such as `CLIENT_ERROR`, `IO_ERROR`, `UNKNOWN`, or omitted depending on the implementation; the exception/error signal is clearer evidence of the error type.

## 2. Why Are Both Status and Outcome Needed?

Looking only at status can miss errors where no response was received. Looking only at outcome can lose specific HTTP classification details. Combining both dimensions helps answer:

- Is downstream returning 4xx or 5xx?
- Is the client timing out or failing to connect before receiving a response?
- Are errors concentrated in one dependency or across multiple dependencies?
- Are retries increasing downstream call counts?
- Is an HTTP 404 an expected business result or an error requiring an alert?

Example:

```text
HTTP client observation
  method = GET
  uri = /inventory/{sku}
  client.name = inventory-service
  status = 503
  outcome = SERVER_ERROR
  exception = none
```

Another case:

```text
HTTP client observation
  method = GET
  uri = /inventory/{sku}
  client.name = inventory-service
  status = none / fallback
  outcome = transport error
  exception = ConnectException
```

The values in these two examples illustrate semantics, not exact promises of tag names across every version. Instrumentation may use a fallback status or store a separate `exception` tag when there is no HTTP response. Inspect actual metrics/observations.

## 3. Grouping HTTP Statuses

| Group | Range | General Meaning | Client Perspective |
| --- | --- | --- | --- |
| 1xx | 100–199 | Informational | Intermediate protocol information |
| 2xx | 200–299 | Successful | Server processed request successfully at HTTP layer |
| 3xx | 300–399 | Redirection | Redirect needed or redirect response used |
| 4xx | 400–499 | Client error | Request not processed as expected per server semantics |
| 5xx | 500–599 | Server error | Server/proxy encountered an error processing request |

Do not lump all 4xx statuses into system errors. 404 may be a valid lookup result; 409 may be a business conflict; 429 may signal rate limiting and require backoff. Likewise, 5xx is usually noteworthy, but distinguish transient errors, configuration errors, and upstream proxy errors.

Some clients automatically handle redirects or retries before the observation finishes. In that case, the final status observed by instrumentation may differ from intermediate responses. If you need the redirect chain or individual attempts, deliberate additional instrumentation/logging is needed.

## 4. Outcome Is Not Always Derived Only from Status

Outcome is usually derived by the convention from the response status when a response exists. However, client operation semantics also depend on which stage an error occurs at:

1. **Before sending the request:** invalid URL, configuration error, or serialization error.
2. **During connection:** DNS, TCP, proxy, or TLS failure.
3. **During send/read:** connection reset, socket timeout, response body decode failure.
4. **After receiving the response:** HTTP 4xx/5xx status, body parsing, or business validation.
5. **After retries:** an attempt fails, but the final attempt succeeds.

For example, a request receives status 200, yet the JSON response is invalid. At the HTTP layer, the response status is success; at the client decoding/business operation layer, the operation can fail. Do not replace status 200 with 500 in HTTP client metrics if the server actually returned 200. Record a separate exception/operation outcome to reflect the decode error.

Conversely, status 404 is not necessarily a technical error. If the client is checking whether a resource exists, 404 can be a normal business branch. Dashboards should distinguish "HTTP client received 4xx" from "business operation failed."

## 5. HTTP Client Observations in Micrometer

Micrometer Observation provides the observation lifecycle for client operations. Spring Framework/Spring Boot HTTP client integrations can create an observation when sending a request and record relevant key-values.

Common dimensions, depending on convention and version:

| Dimension | Example | Usage |
| --- | --- | --- |
| Method | `GET`, `POST` | Group by HTTP method |
| URI | `/products/{productId}` | Stable route/path template |
| Client name | `catalog-service` | Identify dependency |
| Status | `200`, `404`, `503`, or fallback | Response/fallback code per integration |
| Outcome | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR`, or matching enum | Broad classification |
| Exception | `ConnectException`, `SocketTimeoutException`, or `none` | Normalized error type |

Observation names and tag keys can differ across Spring Boot/Spring Framework/Micrometer versions and across client implementations. For instance, HTTP client metrics are commonly represented by a timer like `http.client.requests` in supported stacks, but verify via Actuator/registry instead of assuming.

### Low-cardinality and high-cardinality

Status, method, outcome, client name, and URI template are usually suitable as metric dimensions when values are controlled. Exception classes also need control so proxy-generated classes or custom exception names do not create unbounded values.

Do not put these values into metric tags:

- Raw URLs or raw paths containing IDs.
- Query strings or request bodies.
- Correlation IDs, Trace IDs, Span IDs.
- Verbatim exception messages.
- Arbitrary headers from callers.

Per-request details belong in structured logs or trace attributes per data policies, not in metric labels.

## 6. RestClient Example in Spring Boot

Spring Framework `RestClient` is a synchronous HTTP client. With a Spring Boot-managed builder and configured observation support, client requests can be instrumented automatically.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    RestClient catalogClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
```

When using Spring Boot's auto-configured builder, the observation registry/convention can be wired according to framework configuration. If creating a standalone client/builder manually, do not assume observation instrumentation is enabled the same way as the Boot-provided builder. Verify the exact version and customizers in your application.

Client call example:

```java
CatalogItem item = catalogClient.get()
        .uri("/products/{productId}", productId)
        .retrieve()
        .body(CatalogItem.class);
```

The URI template `/products/{productId}` gives instrumentation the opportunity to record a stable route instead of a raw identifier. If passing a string-constructed URI containing a product ID, depending on the client/convention, the `uri` tag may become high-cardinality; verify the output.

## 7. RestTemplate and WebClient

`RestTemplate` is the long-standing synchronous client, while `WebClient` supports reactive/non-blocking calls. Spring Boot can configure observation for properly managed builders/clients.

### RestTemplate

```java
RestTemplate restTemplate = restTemplateBuilder.build();

CatalogItem item = restTemplate.getForObject(
        "http://catalog-service/products/{productId}",
        CatalogItem.class,
        productId);
```

Use the `RestTemplateBuilder` injected by Spring Boot to receive applied customizers/observation configuration. If instantiating `new RestTemplate()` directly, Boot's customizers and instrumentation may not apply.

### WebClient

```java
WebClient webClient = webClientBuilder
        .baseUrl("http://payment-service")
        .build();

Mono<PaymentResult> result = webClient.post()
        .uri("/payments/{paymentId}/authorize", paymentId)
        .retrieve()
        .bodyToMono(PaymentResult.class);
```

With `WebClient`, the observation wraps the subscribe/execute process according to the reactive lifecycle. Creating a publisher without subscribing may not yet trigger a request. Observe when the request actually runs; do not measure `Mono` creation count as HTTP call count.

Builders should be configured using the Spring Boot/Spring Framework mechanism of the version in use. Do not add a custom interceptor that creates a duplicate timer over automatic observation if the goal is just basic HTTP client metrics.

## 8. Exceptions and Status When There Is No Response

When DNS/TCP/TLS/timeouts fail before a response is received, there is no HTTP status to classify. Client integration typically ends the observation with an exception/error signal and a fallback status depending on the convention.

Example:

```java
try {
    return catalogClient.get()
            .uri("/products/{productId}", productId)
            .retrieve()
            .body(CatalogItem.class);
} catch (ResourceAccessException ex) {
    log.warn("Catalog service is unreachable", ex);
    throw ex;
}
```

`ResourceAccessException` is an example in some Spring synchronous client paths; the actual exception type depends on the client implementation. `WebClient` may emit different exceptions, and decode errors can occur after a response is received. Do not build dashboards relying on only a single exception class for all clients.

The `exception` tag should be a normalized class/type, not the message. Messages can contain dynamic hostnames, URLs, queries, user input, or sensitive data, while also creating high cardinality.

## 9. How Do Retries Affect Status and Outcome?

Retries give a single logical operation multiple HTTP attempts. Determine whether metrics are measuring **each attempt** or the **entire logical operation**:

```text
Business operation: load product
       |
       +--> Attempt 1: HTTP 503 (server error)
       |
       +--> Attempt 2: connection timeout
       |
       +--> Attempt 3: HTTP 200 (success)
       |
       v
Logical operation: success after 3 attempts
```

If client instrumentation creates an observation per attempt, metrics can record two failures and one success. A business-level metric can record one successful logical operation with retries. Both perspectives are useful:

- HTTP client metrics show the actual load received by the dependency and the stability of individual attempts.
- Business operation metrics show whether the user/application ultimately completed the task.
- Retry metrics show attempt counts, retry counts, and exhausted retries.

Do not add attempt counts into logical request counts. If a dashboard needs retry rates, create a separate metric with finite tags such as `dependency`, `retry outcome`, and normalized `policy name`. Do not attach request IDs or exception messages to metrics.

### Retries can mask dependency degradation

If the first attempt frequently returns 503 while a subsequent attempt succeeds, the business success rate may stay high even as downstream degrades and latency climbs. Therefore, monitor both client attempt statuses/outcomes, retry counts, and logical operation results.

## 10. Redirects, 404, and 429 Need Clear Semantics

Not every non-2xx status means the same thing:

| Response | Common Interpretation | What to Check |
| --- | --- | --- |
| 301/302/307/308 | Redirect | Does the client follow redirects? Does it create extra attempts/spans? |
| 400 | Invalid request | Client code bug or valid rejection of bad input? |
| 401/403 | Authentication/authorization | Token/config/permission issue or expected policy? |
| 404 | Not found | Expected lookup miss or wrong endpoint? |
| 409 | Conflict | Business conflict or retryable conflict? |
| 429 | Rate limited | `Retry-After`, backoff, and quota |
| 500 | Internal server error | Downstream application error |
| 502/503/504 | Gateway/service unavailable/timeout | Proxy, service health, and network path |

Dashboards should display status codes or status classes alongside dependency/route so operations teams can find root causes. Alerts should not fire on any single 404 if the business flow routinely looks up non-existent resources.

For 429, immediate retries can worsen rate limiting. Use backoff/jitter and honor `Retry-After` if the client policy supports it. Retries must cap attempt counts and total deadlines.

## 11. Linking Status/Outcome with Logs and Traces

HTTP client observations can typically create a client span when tracing integration is enabled. Traces show which step of the overall request contains the dependency call:

```text
orders-service server span
    |
    +--> order.load
             |
             +--> HTTP GET catalog-service
             |       status=503
             |       outcome=SERVER_ERROR
             |
             +--> retry attempt
                     status=200
                     outcome=SUCCESS
```

Structured logs can record:

```json
{
  "service.name": "orders-service",
  "event": "catalog.client.request.failed",
  "dependency": "catalog-service",
  "http.method": "GET",
  "http.route": "/products/{productId}",
  "http.status_code": 503,
  "outcome": "SERVER_ERROR",
  "retry.attempt": 1,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7"
}
```

The example above illustrates fields; actual schemas should follow your active semantic conventions. Do not log raw URLs, authorization headers, or uncontrolled response bodies.

Metrics aggregate status/outcome by dependency and route template; logs hold concrete events; traces represent parent-child relationships and duration. Trace sampling may mean some requests have no trace in the backend, yet metrics still reflect attempts via their own pipeline.

## 12. Building Dashboards and Alerts for HTTP Clients

A useful dashboard should break down by dependency and route template:

| Perspective | Metric/dimension | Question |
| --- | --- | --- |
| Request volume | Count by client name/method/URI template | Which dependency receives the most calls? |
| Status distribution | Status or status class | Is downstream returning 4xx/5xx? |
| Outcome | Success/error/redirect/unknown per convention | How are client operations trending overall? |
| Latency | Timer histogram, p50/p95/p99 | Which dependency is slow? |
| Transport failures | Normalized exception type | Are there DNS/connect/TLS/timeouts? |
| Retries | Attempts, retries, exhausted | Are retries masking errors or adding load? |

Alerts should rely on rates and durations over a sufficiently long window, avoiding alerting on a single 404 response. For example:

- 5xx rate from a dependency exceeds a threshold for several minutes.
- Timeout rate rises concurrently with p95 latency.
- Exhausted retries rise or retry attempts/request exceed a threshold.
- A dependency has no successful responses within a time window.

Metric names, labels, and query languages depend on the registry/backend. Do not copy PromQL/Datadog queries based only on guessed tag names; check actual series and counter/timer semantics.

## 13. Testing Status and Outcome

An integration test should generate responses with different statuses and transport errors:

| Scenario | What to Verify |
| --- | --- |
| Server returns 200 | Status and success outcome per convention |
| Server returns 302 | Redirect represented as expected; verify follow behavior |
| Server returns 404 | Status 404; business layer decides expected vs. failure |
| Server returns 429 | Status/outcome and retry/backoff behavior |
| Server returns 503 | Server error status/outcome |
| Port not listening | No response status; exception/transport failure recorded |
| DNS host does not exist | No HTTP response; normalized exception type |
| Client timeout | Timeout distinguished from server/proxy 504 response |
| 200 response with body decode error | HTTP status stays 200; separate decode/business error |
| Retry 503 then 200 | Each attempt and separate logical operation result visible |

Do not test only by calling a service method and asserting an exception. Verify that the observation/registry received the right measurements, tags contain no raw URLs, and tracing/log correlation is unaffected.

## 14. Scenario Exercise

An application calls `inventory-service` via an HTTP client. The dashboard shows:

- Low HTTP 5xx.
- Rising client timeouts.
- High business operation success rate.
- Retry attempts/request increased from 1.0 to 2.8.

The operations team concludes the dependency is healthy because the HTTP 5xx rate is low.

**Questions:**

1. Why does low HTTP 5xx not prove the client dependency is healthy?
2. Which status represents a timeout before a response?
3. Why can the business success rate stay high while the dependency is degrading?
4. Which dimensions/metrics should a dashboard include to detect this condition?
5. How should attempt outcomes be distinguished from logical operation outcomes?

**Analysis hints:**

- Timeouts before receiving a response have no HTTP status. They may be recorded via exception/fallback outcome and require transport failure metrics.
- Retries can let subsequent attempts succeed after the first fails, keeping the final business operation successful.
- Monitor HTTP client latency, exception type, timeout rate, retry attempts, exhausted retries, and status/outcome by dependency/route template.
- Instrumentation may record each attempt separately; the business layer records the logical operation once. Do not sum the two counters as having the same semantics.
- Set overall deadlines, retry budgets, backoff/jitter, and alerts when retries increase to avoid adding extra load onto the dependency.

### Completion Checklist

| Topic | Can explain/verify |
| --- | --- |
| HTTP status | 1xx–5xx response codes |
| Client outcome | Result classification of client operations, possibly without response |
| Transport errors | DNS/TCP/TLS/timeouts without HTTP status |
| Micrometer Observation | Understand HTTP client observation and convention |
| Spring clients | Distinguish `RestClient`, `RestTemplate`, `WebClient` |
| Cardinality | Use URI templates and normalized exception types |
| Retries | Distinguish attempt from logical operation |
| 3xx/4xx/5xx | Understand semantics per dependency/business |
| Logs/traces | Link status/outcome with trace and log fields |
| Dashboards/alerts | Monitor latency, errors, timeouts, and retries |
| Integration tests | Test responses, transport failures, and retries |

**Remember:** HTTP status describes the response received by the client; outcome classifies the result of the client operation and remains essential when no response arrives due to DNS, TCP, TLS, or timeouts. Micrometer HTTP client observations can record `method`, URI template, dependency, `status`, `outcome`, and `exception` per convention/version. Monitor both statuses and transport errors, distinguish each retry attempt from the logical operation, keep tags low-cardinality, and correlate metrics with logs/traces to fully understand downstream service health.
