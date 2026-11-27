# Outcome of HTTP Server Observation in Spring Boot

> **Chapter:** HTTP server observability  
> **Lesson:** Outcome  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Why Is a Consistent Outcome Needed?

An HTTP server receives a request, runs a controller and service, and returns a response. Knowing merely whether the request finished is not enough to operate a system. Development and operations teams need to know whether the request succeeded, was rejected per contract, failed to find a resource, encountered a dependency failure, or failed due to an internal error.

**Outcome** is how the result of an operation is classified after processing. In HTTP server observability, outcome helps interpret request results to aggregate metrics, search traces, build dashboards, and configure alerts.

| HTTP Status | Scenario | Possible Interpretation |
| --- | --- | --- |
| 200 | Query completed | Success |
| 201 | Resource created | Success |
| 204 | Completed with no body | Success |
| 400 | Malformed request | Client/input outcome |
| 401/403 | Unauthenticated/unauthorized | Security/policy outcome |
| 404 | Resource does not exist | May be a normal business result |
| 409 | State conflict | Business conflict |
| 429 | Limit exceeded | Throttling |
| 500 | Unexpected server error | Server error |
| 502/503/504 | Gateway/dependency unavailable/timeout | Infrastructure or dependency error |

Do not equate an HTTP status with a single business outcome. The status code is one piece of evidence; the root cause and semantics of the operation also depend on the API contract, exception mapping, and how the application handles errors.

~~~mermaid
flowchart TD
  A["HTTP request starts"] --> B["Server Observation / span"]
  B --> C["Controller and business operation"]
  C --> D{"Operation ends"}
  D -->|"Normal response"| E["Read status / outcome"]
  D -->|"Exception"| F["Exception handler / error mapping"]
  F --> E
  E --> G["Record response status and outcome"]
  G --> H["Stop observation / span"]
  H --> I["Metrics + trace + logs"]
~~~

Logging proper context and outcome does not mean logging all request headers or full objects. Record only sufficient, safe metadata with appropriate cardinality.

## 2. Where Does Outcome Fit in HTTP Server Observation?

HTTP server observation represents the server-side request processing lifecycle. Framework instrumentation typically creates an observation/span when a request arrives, collects request/response metadata, and ends when the server finishes processing.

An HTTP server observation can contain:
- HTTP method and route template.
- Response status code.
- Processing result or outcome per convention.
- Exception if the request failed.
- Processing duration.
- Trace context to link the request with downstream calls.

In Spring Boot, Micrometer Observation is a core instrumentation layer for many server requests. Metrics and tracing handlers can receive the same Observation context to record signals. Key names and tag mappings depend on the Spring Boot/Micrometer version, web stack, and convention.

**Outcome is not an HTTP header sent to the client.** It is observable metadata computed or inferred in the server-side lifecycle once the framework knows the response or exception.

## 3. Distinguishing Outcome, Status Code, and Exception

These three concepts are related but distinct:

| Concept | Question Answered | Example |
| --- | --- | --- |
| HTTP status code | Which code did the server send to the client? | 503 |
| Exception | What was thrown at runtime? | `SocketTimeoutException` |
| Outcome | How is the operation's result classified? | `success` / `client_error` / `server_error` |

An exception can be caught and converted into a valid response. For example, a service calls a payment gateway and times out, yet the business contract allows creating a pending payment. The application can return 202 Accepted after enqueuing the work. The exception remains an event to monitor in the dependency span or log, while the HTTP server request may complete successfully per contract.

Conversely, a server can return 500 without an exception being thrown to the framework—for example, code explicitly constructing a 500 response. If instrumentation relies solely on exceptions, outcome will lack visibility; response status must also be considered.

### 3.1. A Concrete Example

~~~java
@PostMapping("/payments")
public ResponseEntity<PaymentAccepted> submit(
        @RequestBody PaymentRequest request) {
    try {
        PaymentAccepted accepted = paymentService.submit(request);
        return ResponseEntity.accepted().body(accepted);
    } catch (PaymentGatewayTimeoutException ex) {
        PaymentAccepted pending = paymentService.enqueueForLater(request);
        return ResponseEntity.accepted().body(pending);
    }
}
~~~

In this example, the dependency exception is handled. The server sends 202 because the work was accepted for later processing. You should not mark the HTTP server operation as an error merely because an internal exception occurred and was handled per contract. However, the payment client span or a separate metric can still record the timeout.

## 4. HTTP Status Classes and Outcome Classification

HTTP statuses are divided into 1xx, 2xx, 3xx, 4xx, and 5xx. This is a useful protocol-level classification, though it does not always reflect business health accurately.

| Status Class | Protocol Meaning | Examples |
| --- | --- | --- |
| 1xx | Informational | 100 Continue |
| 2xx | Success response | 200, 201, 202, 204 |
| 3xx | Redirection | 301, 302, 304 |
| 4xx | Client error | 400, 401, 403, 404, 409, 429 |
| 5xx | Server error | 500, 502, 503, 504 |

Tracing conventions may use status code, exception, and span kind to set status/error attributes. However, **do not assume a specific outcome taxonomy in Micrometer/Spring Boot without checking the convention of the version you are running**.

For example:
- An HTTP server request returning 404 may be a valid response per contract.
- An HTTP client receiving 404 from a dependency may be an error for the client operation depending on contract.
- 429 may indicate intentional rate limiting, not a bug.
- 503 during maintenance may be a controlled service state.
- 500 usually requires investigation, though it could come from an exception mapped at the boundary.

Outcome should be a small, stable set of categories, such as `success`, `client_error`, `server_error`, `timeout`, or `rejected`. If more detail is needed, use status codes or span/log attributes on the appropriate signal.

## 5. How Does Spring Boot Create HTTP Server Observations?

For Spring MVC/WebFlux applications with Actuator and corresponding instrumentation, Spring Boot can automatically create server observations for requests. The observation typically has a framework-defined convention name and is processed by configured `ObservationHandler`s.

~~~mermaid
sequenceDiagram
  participant Client
  participant Servlet as Web stack
  participant Obs as ObservationRegistry
  participant MH as Metrics handler
  participant TH as Tracing handler
  Client->>Servlet: HTTP request
  Servlet->>Obs: Start server observation
  Obs->>MH: Start timing / tags
  Obs->>TH: Start server span
  Servlet->>Servlet: Controller + service
  Servlet->>Obs: Response / exception context
  Obs->>MH: Stop and record
  Obs->>TH: End span / set status
  Servlet-->>Client: HTTP response
~~~

For the pipeline to work, the proper dependencies and configuration must be in place. If the tracing bridge is missing, metrics may still be generated without server spans from the tracing integration. If the registry/exporter is missing, observations may be created without data reaching the corresponding backend.

Do not create manual filters or interceptors for every request before checking built-in instrumentation; doing so can produce duplicate observations/spans.

## 6. Outcome and HTTP Server Metrics

HTTP server metrics typically measure request count and processing duration across dimensions such as method, outcome, status, and URI template, depending on instrumentation/version.

A common meter in the Spring ecosystem is:

~~~text
http.server.requests
~~~

Common tags may include:
- `method`: GET, POST, PUT…
- `status`: 200, 404, 500…
- `uri`: normalized route template.
- `outcome`: HTTP result category per convention.
- `exception`: exception type or a `none`/`unknown` value per convention.

Actual tag names and values must be verified via the Actuator metrics endpoint or the running registry.

Conceptual PromQL examples:

~~~text
Total requests:
  sum(rate(http_server_requests_seconds_count[5m]))

Rate of 5xx server responses:
  sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
  /
  sum(rate(http_server_requests_seconds_count[5m]))
~~~

These are examples; metric names and suffixes depend on the exporter/registry. With Prometheus, a Timer can be exposed as count, sum, and histogram buckets depending on configuration.

### 6.1. How Does the `outcome` Tag Help Dashboards?

A stable `outcome` tag makes it easy to compare success/error ratios without writing long status-code filters on every dashboard.

~~~text
outcome="SUCCESS"
outcome="CLIENT_ERROR"
outcome="SERVER_ERROR"
~~~

This is just an illustrative taxonomy. Spring Boot/Micrometer conventions may emit different outcome values. Do not assume the strings above are the defaults across all versions.

Metrics should remain low-cardinality. Do not put request IDs, user IDs, raw URLs, or exception messages into tags. Routes should be templates such as `/orders/{id}`, not concrete paths like `/orders/987654`.

## 7. Outcome on Traces/Spans

A server span helps observe the duration and result of a single request. When the request ends, tracing instrumentation can record HTTP status attributes, exception events, and span status per semantic conventions.

Example span attributes:

~~~text
span.kind = SERVER
http.request.method = POST
http.route = /orders
http.response.status_code = 503
service.name = order-service
~~~

Under current HTTP semantic conventions, attribute names have been standardized across versions; older systems may use legacy keys. When reading traces, check the convention version and do not assume every backend displays the exact same field names.

Span status `ERROR` should reflect an operation that genuinely failed per tracing semantics. Do not automatically set `ERROR` for every 4xx if that is valid API behavior. A failed validation request may be an expected client outcome; a 404 may be a normal business result. Depending on convention and policy, span status may differ from the HTTP status class.

### 7.1. Exception Events and Status

If an exception escapes server instrumentation, the framework can record an exception event and error status. If the exception is handled, the handler might not treat the server operation as failed. In custom code, if you record exceptions onto a span manually, avoid duplicating what built-in instrumentation already records.

Do not mark a span as `ERROR` solely to populate a dashboard count. Choose the right layer to emit the outcome and keep metrics, trace status, and log severity aligned to the same semantics.

## 8. Outcome and Exception Handlers

A global exception handler typically maps exceptions to HTTP responses. This mapping directly determines the status code seen by server observation.

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            OrderNotFoundException ex) {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Order not found");
        problem.setDetail("The requested order does not exist.");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(DependencyUnavailableException.class)
    public ResponseEntity<ProblemDetail> handleUnavailable(
            DependencyUnavailableException ex) {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("A dependency is temporarily unavailable");
        problem.setDetail("Please retry later.");
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }
}
~~~

HTTP observation typically observes the final status after the exception handler runs. Therefore:
- `OrderNotFoundException` maps to 404; this may be an expected client/business outcome.
- `DependencyUnavailableException` maps to 503; usually an availability signal requiring alerting/investigation.
- Not every exception should be logged at `ERROR` or mark the span `ERROR` by the exact same rule.
- Error handlers must keep responses safe, without leaking stack traces or internal details.

If the handler returns a 200/202 response after recovering gracefully, the HTTP server outcome should be interpreted according to the final response and contract. The internal exception can still be recorded in dependency instrumentation/metrics/logs.

## 9. Customizing `ObservationConvention`

When built-in conventions do not supply required metadata, Micrometer allows using an `ObservationConvention` to customize the name or key-values for the corresponding observation, depending on the web stack extension point and Spring Boot version.

Conceptual convention example:

~~~java
public class CustomServerObservationConvention
        implements ServerRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ServerRequestObservationContext context) {
        KeyValues values = KeyValues.of(
                KeyValue.of("api.version", "v1"));

        int status = context.getResponse() == null
                ? 0
                : context.getResponse().getStatus();

        return values.and(
                KeyValue.of("response.family", statusFamily(status)));
    }

    private String statusFamily(int status) {
        if (status >= 200 && status < 300) return "2xx";
        if (status >= 400 && status < 500) return "4xx";
        if (status >= 500 && status < 600) return "5xx";
        return "other";
    }
}
~~~

This example illustrates the convention API; constructors, context types, interface packages, and bean registration depend on the Spring Boot/Micrometer version and web stack. Check your project's actual APIs before copying code verbatim.

### 9.1. Only Add Low-Cardinality Metadata

A convention should emit bounded values:
- `response.family`: `2xx`, `4xx`, `5xx`, `other`.
- `api.version`: `v1`, `v2`.
- `operation`: `create`, `read`, `update`, `delete`.
- `outcome`: `success`, `rejected`, `error` per a defined taxonomy.

Do not emit exception messages, raw request URLs containing IDs, user IDs/order IDs, SQL queries with literals, or stack traces. Low-cardinality values can become metric labels; per-request dynamic values can create millions of time series.

## 10. Distinguishing Technical Outcome and Business Outcome

An operation can succeed at the HTTP level while being rejected by business logic. Conversely, an HTTP 4xx can be an expected outcome.

Examples:
- Wrong password on login: HTTP 401; the request was handled per contract, yet authentication failed.
- Looking up a nonexistent order: HTTP 404; may be an expected business result.
- Creating an order with insufficient stock: HTTP 409 or 422 depending on API; a business rejection.
- Inventory service timeout: HTTP 503 or a fallback response, depending on contract.
- `NullPointerException`: usually leads to HTTP 500 and is a server defect.

If a dashboard simply classifies 2xx as success and 4xx/5xx as failure, label it clearly as **HTTP success ratio**, not business success ratio. If the business needs the rate of accepted orders, create a dedicated domain metric with values such as `accepted`, `rejected`, `pending`; do not infer it from status codes alone.

### 10.1. Measuring Business Outcome Separately

~~~java
Counter accepted = registry.counter(
        "orders.submission",
        "outcome", "accepted");
Counter rejected = registry.counter(
        "orders.submission",
        "outcome", "rejected");
~~~

These are custom domain metrics. Use only finite-set label values. The HTTP server request metric still records HTTP status separately; the business counter measures the business result.

## 11. Async Requests and Final Outcome

With async or streaming requests, the moment a response is committed and the moment business processing finishes can differ. For example, the server returns 202 Accepted after enqueuing a job, and the job subsequently fails. The HTTP request outcome is `accepted`; the job execution outcome is `failed`.

~~~mermaid
sequenceDiagram
  participant Client
  participant API
  participant Queue
  participant Worker
  Client->>API: POST /reports
  API->>Queue: Enqueue job
  API-->>Client: 202 Accepted
  Worker->>Worker: Generate report
  Worker-->>Queue: Job failed
  Note over API,Worker: HTTP request accepted, job outcome failed
~~~

Do not retroactively change the HTTP server outcome to `ERROR` just because a job failed after the response finished. Create separate Observations/metrics/logs for the background job, propagate context across the message if supported, and link the job to the request using trace context or an appropriate correlation key.

With streaming/SSE, a response may remain open for a long time before the client disconnects. Determine the outcome according to the lifecycle actually observed by framework/server instrumentation. A client disconnect is not necessarily an application error; distinguish cancellation, normal completion, and server exceptions.

## 12. Outcome, Retries, and Dependency Failures

A single server request may make multiple dependency attempts. For example, a client calls inventory three times: two time out, and the third succeeds. The final server response is 200, while dependency spans show two retry failures.

~~~text
HTTP server observation:
  status = 200
  outcome = success

Inventory client observations:
  attempt 1 = timeout
  attempt 2 = timeout
  attempt 3 = success
~~~

Do not collapse dependency outcomes into a single HTTP server outcome. Each span/observation reflects a distinct operation. If retries succeed at the cost of higher latency, latency metrics and retry counters help surface the issue even when the server request still returns success.

If all retries fail and the server returns 503, the server observation reflects the final response while client spans capture the details of each attempt.

## 13. Security and Cardinality When Recording Outcome

Outcome is usually suitable as a low-cardinality dimension when normalized. However, putting statuses, exceptions, and routes into metrics/traces requires boundaries.

**Use:** status code/status family per convention; route template; outcome from a finite set; normalized exception type if permitted by policy; service/version/resource identity.

**Avoid:** raw URL paths containing resource IDs, query strings, raw exception messages, usernames/emails/tokens, request/response bodies, or outcome values that vary per request.

Exception messages may contain SQL, URLs, user input, or infrastructure details. Never place them verbatim into an `outcome` tag. When details are needed, use log/trace events with proper redaction and retention.

## 14. Verifying Outcome via Actuator and Backends

A verification workflow goes from real requests to metrics and traces.

### Step 1 — Generate Test Responses

Send test requests to produce 2xx successes, 4xx validation/not-found/business-conflict responses, 5xx from a simulated dependency error or exception handler, and a 202 async request whose job later fails.

### Step 2 — Inspect the Metrics Endpoint

~~~http
GET /actuator/metrics/http.server.requests
~~~

Meter and tag names may vary by version/instrumentation. Inspect the available tags and measurements rather than guessing. Actuator endpoints must be protected; do not widen exposure unnecessarily in production.

### Step 3 — Inspect Traces

Open the corresponding trace and check the server span kind, route, response status, span status, exception events, trace/span IDs, and client/dependency spans.

### Step 4 — Cross-Check Logs

Search logs by trace ID/span ID if logging correlation is active. Confirm log severity/message accurately reflects the error without duplicates or leaked sensitive data.

### Step 5 — Compare Business Outcome

Compare custom business counters with HTTP status metrics. For example, 401/404 may increase without the service degrading; rising 503s usually warrant an availability investigation. Dashboards must clearly label HTTP error rate versus business rejection rate.

## 15. Common Pitfalls When Designing Outcome

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Every 4xx triggers alerts as server failure | Misunderstanding API contract | Separate client/business outcomes from 5xx |
| 404 causes error rate to spike | Legitimate lookup misses | Define separate HTTP/API SLIs |
| Exception occurred yet server outcome is success | Exception caught/fallback with 2xx response | Observe the dependency separately |
| Server returns 500 yet span is not `ERROR` | Custom response or different convention | Check response mapping |
| Metrics cardinality grows | Raw URL, ID, or exception message became a tag | Normalize route/outcome |
| Missing `outcome` tag | Convention/custom filter not running or context lacks response | Check lifecycle/instrumentation |
| Async job fails yet request metrics show success | Request completed 202 before job ran | Create a separate job observation |
| Client disconnects counted as server errors | Cancellations not distinguished | Check server stack semantics |
| Retries fail yet overall successful request treated as failure | Merging dependency spans with server span | Track each operation independently |
| Dashboard status and outcome mismatch | Different convention/version or mapping | Check actual emitted tags |
| Metrics missing | Missing registry/exporter or endpoint | Verify meter registration |
| Exception/log/span record conflicting outcomes | Each layer classifies independently | Define taxonomy and ownership |

### Investigation Workflow

1. Identify the server observation measuring the request.
2. Inspect the final response status after exception mapping.
3. Check whether exceptions were handled/fallen back.
4. Inspect dependency spans and retry attempts.
5. Check actual emitted outcome/status tags.
6. Check span status/events per convention.
7. Cross-check application logs and business metrics.
8. Align taxonomy/dashboards with the API contract rather than exception names alone.

## 16. Practical Scenario: HTTP Success and Business Outcome

**Context:** `order-service` serves `POST /orders`. Many requests return 409 when an item is out of stock; this is not a server error. Some requests return 503 because the inventory dependency is unavailable.

### Step 1 — Keep HTTP Status Metrics

Server request metrics record 2xx, 409, and 503 per the status/outcome convention. This reflects the response the client actually received.

### Step 2 — Create Business Metrics

Add domain metrics for `accepted`, `rejected` (due to out-of-stock), and `pending`. Label values are finite and exclude product IDs/customer IDs.

~~~text
orders.submission{outcome="accepted"}
orders.submission{outcome="rejected"}
orders.submission{outcome="pending"}
~~~

### Step 3 — Track Dependency Operations

Inventory client observation records timeouts, retry counts, and latency. The server request returns 503 when it cannot complete per contract.

### Step 4 — Build Dedicated Dashboards

- HTTP availability: percentage of 5xx responses or failed requests per SLI.
- Business conversion: `accepted / submission attempts`.
- Dependency health: timeout/error rate of the inventory client.
- Latency: HTTP server duration and dependency duration.

### Step 5 — Verify

Send an out-of-stock request and an inventory-timeout request. Confirm 409 is not treated as a server defect, 503 appears as an availability failure, business `rejected` increments on out-of-stock, the dependency timeout metric increments on timeouts, and traces show the exact failing operation.

**Lesson:** HTTP outcome, business outcome, and dependency outcome answer different questions. Good dashboards label each ratio accurately.

## 17. Lab Exercises and Self-Check Questions

### Exercise A — Classifying Status and Outcome

Create endpoints returning 200, 201, 202, 400, 401, 404, 409, 429, 500, and 503. Observe response status, metric tags, and server spans. Identify which statuses are expected per the API contract and which indicate availability/technical failures.

### Exercise B — Exception Mapping

Create `OrderNotFoundException` mapped to 404 and `InventoryUnavailableException` mapped to 503. Use `RestControllerAdvice` to build the responses. Verify the server observation sees the final status and distinguish exception events/logs from HTTP outcome. Avoid logging duplicate stack traces.

### Exercise C — Fallback

Simulate a dependency call timeout where the service falls back and returns 202. Verify the server request outcome reflects the accepted response while the client span/metric still reflects the timeout.

### Exercise D — Async Job

Create an endpoint that enqueues a job and returns 202. Make the background job fail afterward. Create a separate observation for the job and verify the HTTP request outcome remains `accepted` while the job outcome is `failed`.

### Exercise E — Cardinality

Audit metric tags. Replace raw URIs with route templates; replace exception messages with exception types/categories; replace order IDs with a finite outcome. Measure the series count before and after.

### Exercise F — Dashboard

Build four panels: HTTP status/outcome, business accepted/rejected, dependency errors/retries, and latency. Write an alert for rising server 5xx errors that does not fire merely for legitimate business 404/409 responses.

### Self-Check Questions

1. How does outcome differ from HTTP status code?
2. Does a caught exception with a fallback necessarily fail the server request?
3. Why can 404 or 409 be an expected business outcome?
4. Which lifecycle does an Observation handler use to record metrics and spans?
5. Which dimensions do HTTP server metrics typically require?
6. Why are route templates better than raw URLs?
7. When an exception handler maps an error to 503, which response does the server observation see?
8. Does span status `ERROR` correspond to every HTTP 4xx/5xx?
9. If an HTTP request returns 202 and the background job fails later, how should outcomes be measured?
10. How should failed dependency retries on an eventually successful request be represented?
11. How do you distinguish HTTP success rate from business success rate?
12. Why are exception messages unsuitable as metric tags?
13. How do you verify outcome via Actuator and a trace backend?
14. When should you use a custom `ObservationConvention`?
15. How do you prevent duplicate instrumentation and duplicate error events?

**Completion criteria:** explain outcome/status/exception; understand the HTTP server observation lifecycle; inspect metric/span attributes; distinguish HTTP vs. business outcomes; handle fallbacks/async/retries; enforce low cardinality; verify via Actuator, traces, and logs.

## 18. Key Takeaways

- Outcome classifies the result of an operation; HTTP status describes the protocol-level response; exceptions describe runtime occurrences. They are related, not identical.
- HTTP server Observation tracks the request lifecycle and can supply status, route, duration, and error context to metrics/tracing handlers.
- Do not treat every 4xx as a server defect. 401, 404, 409, or 429 can be expected API outcomes.
- A caught/fallback exception may not fail the HTTP request; the dependency operation still needs to be observed separately.
- Use route templates and finite outcome values for metrics; never put raw URLs, IDs, or exception messages into tags.
- HTTP success rate is not business success rate. Create separate business metrics when measuring accepted/rejected/pending.
- A request returning 202 whose background job later fails requires two separate observations/outcomes.
- Use Actuator metrics, trace span status/events, and logs to cross-check results. Verify conventions/versions rather than assuming tag names.
- A custom `ObservationConvention` should only add genuinely needed, low-cardinality metadata compatible with the web stack.
- Define outcomes per the API contract, maintain clear ownership, and avoid creating duplicate spans/metrics.

## References

- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/)
- [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
