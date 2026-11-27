# Response Status

A Spring Boot API receives a request to create an order. The controller returns HTTP 201 when creation succeeds, 400 when input data is invalid, 404 when the resource is not found, and 500 when an unexpected error occurs. Status codes help dashboards show whether requests succeed or fail on the client or server side. However, for observability to be genuinely useful, you must understand where response status is recorded, how it affects metric tags and traces, and why a 4xx response does not necessarily imply an exception.

The **Response status** lesson belongs to the **HTTP server observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; you learn context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

> **Key Point:** HTTP response status describes the protocol-level result of an HTTP exchange. An Observation can record keys such as `method`, `status`, `outcome`, `uri`, and `error`. Status, outcome, and error/exception carry distinct meanings. A request can return 404 without throwing an exception; conversely, an exception can be handled and the final response can be 400 or 500. Read status alongside the Observation context rather than inferring errors from a single tag alone.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of HTTP response status in HTTP server observability.
2. Distinguish status code, outcome, error, and exception in Micrometer Observation.
3. Read the default low-cardinality keys of HTTP server Observation.
4. Classify 1xx, 2xx, 3xx, 4xx, and 5xx by outcome.
5. Understand why 4xx does not automatically mean an Observation error or exception.
6. Understand how Servlet/WebFlux and Spring MVC exception handling affect Observation.
7. Query metrics by status/outcome and correlate them with traces/logs.
8. Design a custom `ObservationConvention` without increasing cardinality.
9. Test successful responses, redirects, client errors, server errors, and exceptions.
10. Investigate `UNKNOWN` status, handled errors missing an error tag, and responses modified after filters.

## 2. What Is Response Status?

An HTTP status code is a three-digit code in the response indicating the protocol-level result of processing the request. For example:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/ord-123
~~~

Status 201 expresses that the request successfully created a resource. The body may contain the order representation; `Location` indicates the path to the new resource.

In HTTP server observability, response status is typically recorded as a low-cardinality key-value to group requests into measurable buckets. It helps answer:

- What percentage of requests return 2xx?
- Which routes have high 4xx rates?
- From which release or deployment did 5xx errors start rising?
- Are 3xx redirects increasing abnormally?
- Which status is an endpoint returning when latency increases?

Status alone does not explain the detailed root cause. It is just one signal alongside metrics, logs, and traces.

## 3. Distinguishing Status, Outcome, Error, and Exception

| Field | Meaning | Example |
|---|---|---|
| `status` | Actual HTTP status code of the response | 200, 201, 404, 503 |
| `outcome` | High-level result category based on status family | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` |
| `error` | Error recorded by Observation, typically based on exception/error context | `IllegalStateException`, `none` |
| `exception` | Exception object/type that occurred during processing | `PaymentTimeoutException` |
| `uri` | Handler URI pattern/template | `/orders/{orderId}` |
| `method` | HTTP method sent | `GET`, `POST`, `PATCH` |

For example, one request might look like:

~~~text
method = POST
uri = /orders
status = 400
outcome = CLIENT_ERROR
error = none
~~~

This can be a validation error response returned directly by the controller without throwing an exception. Another request might have:

~~~text
method = GET
uri = /inventory/{sku}
status = 503
outcome = SERVER_ERROR
error = InventoryUnavailableException
~~~

In this case, the exception may have bubbled across the instrumentation boundary and been recorded by the Observation. How `error` is recorded depends on where the exception is handled and the framework convention.

**Do not infer `error=none` solely from a 2xx status or `error != none` solely from a 5xx status.** Read the context and handler behavior.

## 4. Classifying HTTP Status and Outcome

Spring Framework/Spring Boot uses `outcome` to group status codes:

| Status Class | Code Range | Common Outcome | Examples |
|---|---:|---|---|
| 1xx Informational | 100–199 | `INFORMATIONAL` | 100 Continue |
| 2xx Success | 200–299 | `SUCCESS` | 200 OK, 201 Created, 204 No Content |
| 3xx Redirection | 300–399 | `REDIRECTION` | 301, 302, 304 |
| 4xx Client Error | 400–499 | `CLIENT_ERROR` | 400, 401, 403, 404, 409, 429 |
| 5xx Server Error | 500–599 | `SERVER_ERROR` | 500, 502, 503, 504 |

`outcome` reduces the number of groups to monitor and keeps cardinality bounded. `status` provides finer detail while still staying within the bounded HTTP status code domain.

### 4.1 2xx Is Not Only 200

- 200 OK: request processed and may return a representation.
- 201 Created: resource created successfully.
- 202 Accepted: request accepted, though processing may proceed asynchronously.
- 204 No Content: succeeded with no response body.

When a dashboard only counts 200, valid successes like 201/202/204 can be missed. Use `outcome=SUCCESS` or the 2xx status family.

### 4.2 3xx Must Be Interpreted Per API

301/302 may be normal navigation redirects. 304 Not Modified serves cache validation. 3xx is not automatically a server error. A spike in 3xx may be expected if the app uses redirects, or it could signal a redirect loop or misconfigured route if the rate is abnormal.

### 4.3 4xx Can Be an Expected Business Outcome

400 may be a validation failure, 401 unauthenticated, 403 unauthorized, 404 resource not found, 409 conflict, and 429 rate limited. These typically reflect the client request or rejection policies at the client/gateway side, not necessarily internal bugs.

Depending on the product, 404/409 can be a normal use-case result. An endpoint checking whether a username exists might return 404 frequently. Alerts should distinguish endpoints and abnormal rates rather than treating every 4xx as a service failure.

### 4.4 5xx Usually Requires Investigating the Service/Dependency

500 indicates an internal error not handled into a successful response; 502/503/504 typically point to gateway, upstream, or service unavailable/timeout issues. Status alone still does not identify which exact dependency failed. Open traces and logs for the same service/route/time window.

## 5. HTTP Server Observation in Spring

Spring Framework creates HTTP server exchange Observations for Servlet and Reactive applications. The standard Observation is typically named `http.server.requests`; when using OpenTelemetry conventions, metric/observation naming may be `http.server.request.duration`.

Spring Boot Actuator configures instrumentation for supported stacks when the appropriate dependencies are present. An Observation can be processed by handlers to produce Micrometer metrics and/or tracing spans.

Default key-values typically include:

| Key | Cardinality | Content |
|---|---|---|
| `error` | Low | Exception class name or `none` if no exception was recorded |
| `method` | Low | HTTP method, or `none` for non-standard/unrecognized methods |
| `outcome` | Low | Result category derived from response status |
| `status` | Low | Raw HTTP status code or `UNKNOWN` when no response was produced |
| `uri` | Low | Handler URI pattern or fallback such as `NOT_FOUND`, `REDIRECTION`, `UNKNOWN` |

A high-cardinality field may hold the full URL such as `http.url`; this field is intended for traces per the corresponding convention, not as a default metric tag. Never use raw URLs as metric dimensions.

Exact keys depend on the active convention and Spring Framework version. When choosing OpenTelemetry semantic conventions, names/mappings may differ from default Micrometer conventions. Refer to the Spring Framework Observability and Spring Boot Metrics documentation.

## 6. Status and Metrics

HTTP server Observation typically produces a timer metric to measure request processing duration. A meter like `http.server.requests` can be grouped by `method`, `uri`, `status`, `outcome`, and `error`.

Conceptual query example:

~~~text
http.server.requests{
  method="POST",
  uri="/orders",
  status="201",
  outcome="SUCCESS"
}
~~~

Actual metric/label names depend on the registry and naming convention. Prometheus typically converts dots to underscores, while OTLP can preserve names according to its export rules.

### 6.1 Why Measure Both `status` and `outcome`?

- `status` lets you inspect specific codes such as 401, 404, 429, 500, and 503.
- `outcome` groups results into `SUCCESS`, `CLIENT_ERROR`, and `SERVER_ERROR`.
- `error` distinguishes requests with a recorded exception from those without.
- `uri` identifies which route template has an issue.

For high-level dashboards, `outcome` is easier to read and more resilient. During investigations, drill down by specific `status` and `route`.

### 6.2 Do Not Use Raw URLs as Tags

Do not create tags with URLs containing IDs:

~~~text
uri="/orders/ord-1001"
uri="/orders/ord-1002"
uri="/orders/ord-1003"
~~~

Use a route template instead:

~~~text
uri="/orders/{orderId}"
~~~

Metric time-series cardinality is the Cartesian product of each dimension's possible values. Adding `userId`, `requestId`, full URL, or query string can cause series counts to grow nearly linearly with request count, increasing memory, storage, and query costs.

### 6.3 Status Codes Have Bounded Cardinality, Yet Still Need Control

HTTP status has a bounded domain, yet custom application response codes or arbitrary tags can still inflate cardinality. Never construct a `status` tag from free-form strings; always derive it from a valid response status and avoid adding other keys containing message/error text.

## 7. Status Is Not Synonymous with Observation Error

This is the most important distinction when reading HTTP server metrics.

Spring Framework Servlet instrumentation generally records an Observation error when an exception bubbles up to the observation filter, as well as for certain server errors handled by Spring MVC itself, such as 5xx rendered via `ProblemDetail`. 4xx errors and exceptions handled by `@ExceptionHandler` usually are not automatically recorded as Observation errors. The framework allows applications to explicitly mark an error on the `ObservationContext` when needed.

| Scenario | HTTP Status | Exception | Possible Observation Error? |
|---|---:|---|---|
| Controller returns bad request | 400 | No | Usually no |
| Validation exception handled by `@ExceptionHandler` into 400 | 400 | Yes, but handled | Usually not automatic |
| Resource does not exist, returns 404 | 404 | Possibly not | Usually no |
| `IllegalStateException` bubbles out of controller | 500 | Yes | Yes |
| Handler processes exception and returns 500 `ProblemDetail` | 500 | Yes, but handled | Per Spring MVC behavior/convention, may be recorded for server errors |
| Request terminates before a response is created | `UNKNOWN` | Possibly | Depends on exception path |

Exact rules vary across Servlet/WebFlux, Spring Framework versions, exception resolvers, and custom filters. Do not apply this table mechanically when custom instrumentation is present.

### 7.1 Why Is 404 Not Necessarily an Exception?

Spring MVC may fail to find a handler and complete the request with 404. This is the status returned to the client. Observation may use the `NOT_FOUND` URI fallback; `error` may still be `none` if no exception was recorded.

### 7.2 Why Might a 400 Validation Error Not Increment the `error` Tag?

`MethodArgumentNotValidException` can be handled by Spring and converted into a 400 response. Because the exception does not bubble outside the observation boundary, the `error` tag may be `none`. Nevertheless, `status` is still 400 and `outcome` is still `CLIENT_ERROR`.

If business/SLOs need to measure validation rejections, use a dedicated business metric or explicitly record it via the observation context/convention rather than assuming the `exception` tag will appear automatically.

### 7.3 Handled 5xx Errors Can Still Be Marked

Spring Framework includes logic so framework-handled server errors (including `ProblemDetail` in Spring MVC) can still be recorded as Observation errors. A handler may catch an exception and produce a clean JSON response, yet the underlying issue remains a server-side failure.

For WebFlux or custom exception handling, verify the behavior with tests on your specific version.

## 8. Example Controller Returning Various Response Statuses

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    ResponseEntity<OrderView> create(@RequestBody CreateOrder command) {
        OrderView created = orderService.create(command);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> find(@PathVariable String id) {
        return orderService.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/validate")
    ResponseEntity<Void> validate(@RequestBody CreateOrder command) {
        if (command.items().isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

This is an illustrative example; services, DTOs, and validation are simplified. A successful POST returns 201. A GET for a missing resource returns 404. The `validate` endpoint returns 400 without throwing an exception, so status/outcome still indicate a client error even though the `error` tag may be `none`.

## 9. Custom Exception Handling and Status

A controller advice can map an exception to a response status:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderConflictException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    ProblemDetail handleConflict(OrderConflictException ex) {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.CONFLICT);
        problem.setTitle("Order conflict");
        problem.setDetail("The requested order state is not valid.");
        return problem;
    }
}
~~~

HTTP status 409 informs the client of a conflict. However, because the exception is handled in the advice, the observation filter might not see the exception bubble up. If a separate error measurement is required, record the business error explicitly in an Observation or a dedicated meter.

Do not place arbitrary exception messages into response details, logs, or spans if they might contain SQL, tokens, or user data.

### 9.1 Do Not Mark Every 4xx as an Application Failure

Alerting on `outcome=CLIENT_ERROR` can be helpful for tracking API quality, but it should not always page the service team. Public endpoints receive bot traffic generating 404/401; 429 can confirm rate limiting is working. Build alerts around specific routes, statuses, baselines, and API SLOs.

### 9.2 Do Not Ignore 5xx Just Because the Exception Was Handled

An `@ExceptionHandler` might turn a downstream failure into a 503 response. That is good for the API contract, yet the platform still needs visibility into server failures. Check the error convention, log severity, trace status, and metric status/outcome so the signal is not lost.

## 10. Status in Traces and Logs

Traces typically keep a span for the HTTP server exchange, with attributes describing method, route, status code, and related info. Span status in the tracing data model is a distinct concept from HTTP status code. A span can have an HTTP status attribute of 404 while its span status remains `UNSET` per instrumentation conventions; do not assume every 4xx must set span status to `ERROR`.

Log level is a logging policy decision, not a rigid mapping from HTTP status:
- 404 may be `INFO`/`DEBUG` if it is a routine business flow.
- 401/403 may require security auditing without logging credentials.
- 429 may be `WARN` if rate limiting is abnormal or `INFO` per operational policy.
- 5xx usually requires `ERROR`/`WARN` depending on where the log is emitted; avoid emitting multiple error logs for the same handled failure.

Include `traceId`/`spanId` in logs for correlation when context propagation and logging integration are configured. Logs can include the route template and status, but never log raw URLs containing secrets/queries.

## 11. Customizing Status Tags with `ObservationConvention`

Micrometer Observation lets you customize low-cardinality key-values using `ObservationConvention`. You can adjust metadata rules, but you must preserve stable semantics.

Spring Framework provides `DefaultServerRequestObservationConvention` with `ServerRequestObservationContext`. When customizing, extend or decorate the default logic to retain essential keys.

Illustrative example declaring the default convention:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.observation.ServerRequestObservationConvention;
import org.springframework.http.server.observation.DefaultServerRequestObservationConvention;

@Configuration
class HttpObservationConfiguration {

    @Bean
    ServerRequestObservationConvention serverObservationConvention() {
        return new DefaultServerRequestObservationConvention();
    }
}
~~~

This is an illustrative declaration of the default convention; when genuinely customizing, implement the appropriate convention and return normalized low-cardinality values. Spring Framework has different extension points for Servlet and Reactive stacks; verify the exact interface used by your stack.

### 11.1 Example: Adding a Finite Business Outcome

If you need to know when a request is rejected by policy, add a key such as `business.result` with a small value set:
- `accepted`
- `validation_rejected`
- `conflict`
- `rate_limited`

Do not use exception messages or error details as tags. With a custom convention, use the context to safely derive status/outcome and add fields only when values are bounded.

### 11.2 Do Not Overwrite `status` with a Business Result

Keep `status` as the actual HTTP status. If the API returns 409 Conflict because the business result is `inventory_unavailable`, `status` stays 409; `business.result` is a separate key. Do not replace `status=409` with `inventory_unavailable`, as that breaks semantics and query conventions.

## 12. `UNKNOWN` Status and Uncreated Responses

Some requests fail before a complete response is produced—for example, a closed connection, container abort, early exception, or handler failing to complete the response. In such cases, instrumentation may record `status` as `UNKNOWN` because there is no response status to read.

`UNKNOWN` is not a valid HTTP response status code; it is a fallback in Observation metadata indicating the status could not be captured. Investigate:

- Did the exception bubble through the observation filter?
- Was the response already committed?
- Did the client disconnect before the server finished?
- Did the filter/interceptor end the observation according to its lifecycle?
- Does the server stack expose the response status to instrumentation?

Never use `UNKNOWN` as a status code in business logic or return `UNKNOWN` to clients.

## 13. Response Status and Response Commitment

In the Servlet stack, a response may be committed before the outermost filter reads the status; in streaming/reactive responses, status and body lifecycles may complete at different times. If an application/filter changes the status after the response is committed, the HTTP server cannot send the new status as a normal response.

Examples:
- Controller sets 200 and then streaming the body throws an exception midway.
- A filter writes/flushes the response body before the exception handler changes the status.
- Client cancels the connection while the server is still writing the response.
- An error dispatch creates a second error response or modifies metadata after the observation scope has closed.

When inspecting traces/metrics, distinguish the response status the server actually sent from an exception raised during streaming. A request may start with status 200 and encounter a stream error after headers commit; HTTP status stays 200 while the span/exception event may record the stream error depending on instrumentation.

## 14. Testing Response Status

Do not only test controller responses; verify that observability signals also reflect the expected result.

| Scenario | Expected Status | Expected Outcome |
|---|---:|---|
| Order created successfully | 201 | `SUCCESS` |
| Invalid validation request | 400 | `CLIENT_ERROR` |
| Resource not found | 404 | `CLIENT_ERROR` |
| Redirect | 302 | `REDIRECTION` |
| Conflict | 409 | `CLIENT_ERROR` |
| Dependency unavailable | 503 | `SERVER_ERROR` |
| Error before response is created | `UNKNOWN` in Observation if applicable | Not an HTTP response code |

### 14.1 Testing Observation with a Test Registry

You can use `SimpleMeterRegistry` and `ObservationRegistry` in tests to verify the timer/meter is created. Illustrative test structure:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HttpResponseStatusObservationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsCreatedStatus() throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType("application/json")
                        .content(validOrderJson()))
                .andExpect(status().isCreated());

        Timer timer = meterRegistry.find("http.server.requests")
                .tag("method", "POST")
                .tag("status", "201")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isGreaterThan(0);
    }
}
~~~

Imports, DTO fixtures, controllers, and metric name/tag conventions must match the real application. With OTel semantic conventions or a custom `ObservationConvention`, meter/tag names may differ. Do not copy tests as a fixed contract across every stack.

### 14.2 Testing Handled Exceptions

Write tests for `@ExceptionHandler` returning 400 and 500:
- Assert HTTP status.
- Assert status/outcome metadata.
- Verify `error` tag behavior for your framework version.
- If business rules require 4xx validation rejections to be tracked as separate errors, verify the custom observation/business metric is recorded.

### 14.3 Verifying No Cardinality Explosion

Send multiple requests to `/orders/{id}` with different IDs and verify the metric URI stays as the route template rather than the full path. Verify the number of meter IDs does not increase with the number of order IDs.

## 15. Dashboard Investigation: 5xx Spikes While Error Tag Remains Low

**Scenario:** The dashboard shows `status=500` increasing, yet `error` remains `none` for most requests.

1. Pick representative traces/logs for the same route and time window.
2. Check whether the controller/advice catches the exception and returns 500.
3. Determine whether the exception bubbles up to the observation filter.
4. Check whether the stack is Servlet or WebFlux and check the Spring Framework version.
5. Check whether a custom `ObservationConvention`/`Filter` alters the `error` key.
6. Check logs to see if the exception stack/cause was recorded.
7. If 500 is a business-controlled error without an exception, add a dedicated business error/outcome metric rather than forcing the `error` tag from status.
8. If 500 is a handled server failure, configure recording the exception onto the context via the proper extension point and re-test.

The `status` tag remains the source of truth for the HTTP response class; the `error` tag only reflects errors recorded on the Observation.

## 16. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| 404 spikes while `error` tag stays `none` | Not-found responses need no exception or are handled by the framework | Inspect `status`/`outcome`; break down 404 by route |
| 400 validation does not show an exception | `@ExceptionHandler` handles the exception | If needed, record a separate business validation metric/Observation |
| 500 has `status` but no `error` class | Exception was handled or custom convention omits `error` | Check handler/context and explicitly record when needed |
| `status=UNKNOWN` | Response not created yet or status unreadable | Check exception/commit/stream lifecycle |
| Dashboard only shows 200 | Query filter excludes 201/202/204 | Query by `outcome` or status family |
| 3xx triggers alerts as server errors | Query/threshold groups statuses incorrectly | Separate `outcome` per API semantics |
| 4xx increases due to bots/consumers | Traffic or client behavior changed | Analyze route/source/rate limit; do not page on every 4xx |
| 5xx increases without `error` tag increasing | Handled exception/`ProblemDetail`/different convention | Test framework path and custom `ObservationContext` |
| Trace span lacks `ERROR` status despite HTTP 404 | HTTP status attribute and span status differ | Use HTTP attributes and tracing semantic conventions |
| Metric cardinality grows by ID | Raw URI/user/request ID became a tag | Use URI templates and bounded values |
| Status in access log differs from metric | Reverse proxy modifies response or different log layer | Compare status at each hop |
| Streaming returns 200 but trace has exception | Headers already committed before body stream failed | Investigate stream lifecycle/client disconnect |
| Jersey tags differ from Spring MVC tags | Different stack instrumentation/convention | Check `JerseyObservationConvention` and server stack |

## 17. Self-Check Exercises

**Exercise 1 — status vs. outcome.** An API returns 429. What are `status` and `outcome`? Must there be an exception by default?

**Exercise 2 — status vs. error.** A controller returns 404 directly without throwing an exception. Why can `error` be `none`?

**Exercise 3 — handled exception.** A validation exception is turned into 400 by `@ExceptionHandler`. Why does Observation not necessarily record an exception error? How do you intentionally measure validation failures?

**Exercise 4 — 5xx ProblemDetail.** An exception is handled by Spring MVC into a 503 `ProblemDetail`. Why should you still ensure Observation marks a server error?

**Exercise 5 — UNKNOWN.** When does an Observation have status `UNKNOWN`? Is it an HTTP status sent to the client?

**Exercise 6 — Cardinality.** Why not use the raw URL `/orders/12345` as a metric tag when status 404 is bounded?

**Exercise 7 — Streaming.** A controller returns 200 and then streaming the body throws an exception. Why can the final status remain 200 while the trace still records an error?

**Exercise 8 — Dashboard.** 5xx errors spike, yet the `error` tag is mostly `none`. Outline the investigation order and explain why you should not rely solely on the `error` tag.

### Suggested Answers

1. `status=429`, `outcome=CLIENT_ERROR`; an exception is not required.
2. 404 is an HTTP outcome and does not necessarily have a recorded exception.
3. The exception was handled inside MVC and did not bubble to the observation filter. Use a low-cardinality business metric/Observation for `validation_rejected` if needed.
4. The response still represents a server failure even though the exception was formatted as a `ProblemDetail`; losing the error signal makes investigating exceptions harder.
5. When a response was not created/status could not be read; `UNKNOWN` is an Observation fallback, not an HTTP response code.
6. Per-order IDs generate many series; the route template `/orders/{id}` keeps the dimension bounded.
7. Headers were already committed so the status cannot change; an exception during streaming can be recorded separately on the span/event.
8. Inspect traces/logs, controller advice, exception propagation, stack/framework convention, and custom filters; `status` reflects the response, while `error` reflects the recorded exception.

## 18. Official References

- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): HTTP server observations, `KeyValues`, low/high cardinality, and Servlet exception handling.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): HTTP server metrics, outcome/status tags, and customization.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Observation, metrics/tracing integration, and conventions.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, `ObservationContext`, handlers, and conventions.
- [Micrometer — Observation API](https://docs.micrometer.io/micrometer/reference/observation/components.html): Observation conventions, handlers, and key-values.
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/): HTTP request/response attributes and status semantics.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): standard meanings of HTTP status codes.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail` and REST API error handling.

**Key Takeaway:** Response `status` indicates the HTTP result; `outcome` groups statuses into categories; `error`/`exception` describe errors recorded by Observation. A 400/404 may have no exception error, whereas a handled exception may still need to be recorded if it is a server failure. Use status and route templates for metrics, open traces/logs for root causes, test both handled and unhandled exceptions, and never use raw URLs or free-form data as metric tags.
