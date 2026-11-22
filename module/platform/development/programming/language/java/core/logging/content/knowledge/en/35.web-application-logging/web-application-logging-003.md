# Request Path in Java Web Application Logging

## 1. What Is a Request Path and Why Log It?

In a Java web application, the **request path** is the path portion of an HTTP request pointing to the resource or endpoint requested by the client, such as `/api/orders/42`. Recording the path helps identify which APIs are producing errors, inspect traffic distribution, investigate 404/403 responses, correlate requests across distributed systems, and analyze response times.

However, **request path is not synonymous with the full URL**. If an application logs the entire URL, it may accidentally store tokens in the query string, personal data in path segments, or generate millions of distinct values for metrics systems. The goal of this lesson is to understand which parts belong in operational logs, which parts should be restricted to access-controlled security analysis, and how to implement this properly with Servlet, Spring MVC, and plain Java.

Consider an illustrative HTTP request:

```http
GET /shop/orders/42?access_token=example-token&view=full HTTP/1.1
Host: api.example.test
```

It can be broken down into:

| Concept | Example Value | Meaning |
| --- | --- | --- |
| HTTP method | `GET` | HTTP action |
| Scheme | `https` if the external connection is HTTPS | Not included in an origin-form request-target |
| Host | `api.example.test` | Requested server; may be affected by proxies |
| Request path | `/shop/orders/42` | Path portion, **excluding the query string** |
| Query string | `access_token=example-token&view=full` | Portion after `?`, which may contain sensitive data |
| Route template | `/shop/orders/{orderId}` | Route pattern defined by the application/framework |
| Path variable | `orderId=42` | Dynamic value extracted from the path |
| Full URL | `https://api.example.test/shop/orders/42?access_token=example-token&view=full` | Includes scheme, authority, path, and query |

These components serve different purposes. For **querying logs by endpoint**, the route template is usually more suitable than the raw path. For **investigating a specific request**, use the request ID/trace ID, route, status, and necessary context. Only retain raw paths under controlled conditions when there is an investigative need and a dedicated policy.

**Do not assume a path is safe simply because the query string has been stripped.** Paths such as `/users/alice@example.com`, `/reset/example-token`, or `/documents/medical-record-123` can still contain sensitive information.

## 2. Distinguishing Path, Raw Path, URI, URL, and Route

### Path and Query Are Separate Components

According to URI syntax, the `?` character separates the path from the query:

```text
/api/products/20?sort=price&page=2
└──── path ──────┘ └──── query ────┘
```

HTTP clients may send full URLs or request targets in various forms depending on the proxy or protocol; at the typical web application layer, the Servlet container or HTTP framework already parses the request into components accessible via APIs. **Do not split the string manually with `split("?")` and treat that as a reliable URL parser.** A `?` character may appear percent-encoded inside a path, invalid characters require distinct handling, and request-targets also have special forms such as `*` or authority-form for certain methods.

### Raw Path and Decoded Path

A path may contain percent-encoding:

```text
Raw path:     /api/users/alice%40example.com
Decoded path: /api/users/alice@example.com
```

The **raw path** preserves the percent-encoded representation (within what the HTTP server exposes); the **decoded path** interprets `%HH` sequences according to URI and character rules. The two strings are not fully interchangeable:

- `%2F` can represent a slash; containers, proxies, and routing frameworks may handle encoded slashes under different policies.
- `%2e`, `..`, backslashes, consecutive slashes, and double-encoding can cause discrepancies between security checks, routing, and logging.
- Percent-decoding is not the same as `application/x-www-form-urlencoded`: in a URI path, `+` is not treated as a space by default. Do not use `URLDecoder` as a general path normalizer.
- Unicode, case sensitivity, and delimiters may be normalized differently by reverse proxies and backends.

**Logged values must never be used as the source of truth for authorization decisions.** The application must rely on the path/route that the server actually used for routing and policy enforcement, while preserving enough safe diagnostic information when proxies and backends disagree.

### Route Template vs. Request Path

The route `/api/orders/{orderId}` can match millions of actual paths such as `/api/orders/42`, `/api/orders/43`, and so on. If every concrete path becomes a separate metric label or name, time-series cardinality can grow out of control.

Therefore:

- **Standard logs:** should include `http.method`, `http.route`, `http.status_code`, `request_id`, `duration_ms`, and appropriate service metadata.
- **HTTP metrics:** the `route` label should use a defined template or a bounded constant such as `UNMATCHED`, never dynamic IDs or raw paths.
- **Dedicated investigation:** store only redacted/bounded paths in a channel with restricted access and appropriate retention.

Do not synthesize a route template by replacing every numeric sequence in a path with `{id}` and treating it as the real route: that can misclassify endpoints, lose structure, and mask routing issues. Obtain the route pattern matched by the web framework; if unmatched, use a fallback with a bounded set of values.

## 3. Request Path in the Servlet API

For Java Servlet applications using `HttpServletRequest`, relevant APIs include:

| API | Primary Content | Key Considerations |
| --- | --- | --- |
| `request.getRequestURI()` | The URI path requested by the client within the container, **excluding the query** | Includes the context path and remaining path; usually returned undecoded, though behavior on malformed input depends on the container |
| `request.getContextPath()` | Context path of the web application, which may be an empty string | For example `/shop` if deployed under the `shop` context |
| `request.getServletPath()` | Portion of the path matching the servlet mapping | Not necessarily the MVC controller's route template |
| `request.getPathInfo()` | Extra path following the servlet mapping, which may be `null` | Not universally applicable across all servlet mappings |
| `request.getQueryString()` | Undecoded query string, or `null` | May contain tokens, passwords, or personal data; avoid logging directly |
| `request.getRequestURL()` | `StringBuffer` containing the reconstructed URL up to the end of the path | Excludes query; scheme/host/port may require considering proxy/forwarded headers |
| `request.getMethod()` | HTTP method | Validate unusual methods against policy |
| `response.getStatus()` | Current HTTP response status | Measure at a meaningful completion point, especially for async requests |

For example, with context path `/shop` and application route `/orders/{id}`, the request URI might be `/shop/orders/42`. However, `getServletPath()` and `getPathInfo()` depend on the servlet mapping. Do not concatenate fields with a hardcoded formula to guess the MVC route.

`javax.servlet.*` is used in older systems; Jakarta EE / Spring Boot 3+ systems use `jakarta.servlet.*`. The distinction between request URI and query remains the same, but package names and integrations must match the actual dependencies.

### Illustrative Snippet Inside a Filter

```java
String method = request.getMethod();
String rawRequestUri = request.getRequestURI();
String query = request.getQueryString();

// Do not log rawRequestUri or query directly into the default access log.
// They may contain path variables, tokens, or personal information.
```

This is **not a standalone program**; it assumes `request` and `response` are Servlet API objects. In production, select log fields using framework routing metadata rather than assuming `getRequestURI()` is always safe just because it omits the query.

## 4. Request Path in Spring MVC

Spring MVC routes controllers based on mappings, for example:

```java
@GetMapping("/api/orders/{orderId}")
public ResponseEntity<OrderDto> findOrder(@PathVariable long orderId) {
    // Return data according to business logic and authorization policy.
}
```

This is an **illustrative snippet**, not standalone runnable code: it requires Spring MVC, `OrderDto`, a controller class, and an implementation. For a request `GET /api/orders/42`, the **route pattern** known to the framework is `/api/orders/{orderId}`. When analyzing requests by endpoint, prefer this pattern instead of attaching `/api/orders/42` to metrics.

In a Spring MVC component with access to the Servlet request, the framework can expose the matched route via:

```java
Object pattern = request.getAttribute(
        org.springframework.web.servlet.HandlerMapping
                .BEST_MATCHING_PATTERN_ATTRIBUTE);
String route = pattern == null ? "UNMATCHED" : pattern.toString();
```

This is also an **illustrative snippet**, not a standalone Java file. You must check the value type, dispatch phase, and Spring MVC version in use. The attribute may **not exist before a handler is matched**, such as in a Filter running before `DispatcherServlet`, or on 404s, error handling, or security rejections that occur before controller mapping.

### Logging an Event After Request Completion

You can use a `HandlerInterceptor`, a Filter, or the framework's observation/access-logging mechanism, but you must identify the actual completion point. With `HandlerInterceptor`, the idea is:

```java
@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler, Exception ex) {
    Object matched = request.getAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
    String route = matched == null ? "UNMATCHED" : matched.toString();

    accessLogger.info(
            "http request completed method={} route={} status={}",
            request.getMethod(), route, response.getStatus());
}
```

This snippet requires a class implementing `HandlerInterceptor`, the appropriate `jakarta.servlet.*` or `javax.servlet.*` imports for your stack, `HandlerMapping`, and `accessLogger`. It is **not a standalone program**. `afterCompletion` applies to requests passing through the interceptor in the Spring MVC lifecycle; **by default it does not cover all 404s, pre-routing errors, or every async scenario**. If full access logging across error and async dispatches is required, design a mechanism that covers those dispatches, test it in practice, and avoid duplicate logging across multiple dispatches.

### Spring WebFlux Differs from Servlet MVC

Spring WebFlux uses a reactive request/exchange API; it does not use `HttpServletRequest` as a required API. The path can be obtained from `ServerHttpRequest`/`ServerWebExchange`, while the matched route must be retrieved from the stack's router/handler mapping metadata. In reactive or async Java, MDC is typically thread-bound and does not automatically follow the request context across callbacks. Choose a context propagation mechanism supported by the framework instead of writing to a `ThreadLocal` and assuming every operator will read it correctly.

## 5. Standalone Java 17 Example: Safe Route-Only Logging

This example uses only JDK 17—no Servlet, Spring Boot, Maven, or external libraries required. It simulates three server-handled requests, parses each request-target with `java.net.URI`, and produces a **JSON access log** containing only bounded fields. Even when a request path contains IDs or personal data, the program logs only a **trusted route template** or `UNMATCHED`; the query string is excluded from the log.

This sample code is **not a production HTTP router**: the regex mapping is for demonstration only. In real Servlet/Spring MVC applications, use the route matched by the framework along with the actual response status.

Save as `RequestPathLoggingDemo.java`:

```java
import java.net.URI;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

public final class RequestPathLoggingDemo {
    private static final Pattern ORDER_DETAIL =
            Pattern.compile("^/api/orders/[0-9]+$");

    record Sample(
            String method, String requestTarget,
            int status, String requestId) {}

    private static String routeFor(String rawPath) {
        if (ORDER_DETAIL.matcher(rawPath).matches()) {
            return "/api/orders/{orderId}";
        }
        return "UNMATCHED";
    }

    private static String jsonString(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        out.append(String.format(
                                Locale.ROOT, "\\u%04x", (int) ch));
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static void log(Sample sample) {
        URI parsed = URI.create(sample.requestTarget());
        String rawPath = parsed.getRawPath();
        if (rawPath == null || rawPath.isEmpty()) {
            throw new IllegalArgumentException("Missing request path");
        }

        String matchedRoute = routeFor(rawPath);

        String line = "{"
                + "\"event\":\"http.request.completed\","
                + "\"method\":" + jsonString(sample.method()) + ","
                + "\"route\":" + jsonString(matchedRoute) + ","
                + "\"status\":" + sample.status() + ","
                + "\"request_id\":" + jsonString(sample.requestId())
                + "}";

        // Do not log rawPath, rawQuery, or tokens.
        System.out.println(line);
    }

    public static void main(String[] args) {
        List<Sample> requests = List.of(
                new Sample(
                        "GET",
                        "/api/orders/42?access_token=example-token",
                        200, "req-001"),
                new Sample(
                        "GET",
                        "/api/users/alice%40example.com/reset"
                                + "?token=example-token",
                        404, "req-002"),
                new Sample(
                        "POST",
                        "/api/orders/99?debug=true",
                        403, "req-003"));

        requests.forEach(RequestPathLoggingDemo::log);
    }
}
```

Compile and run:

```bash
javac RequestPathLoggingDemo.java
java RequestPathLoggingDemo
```

**Exact stdout:**

```json
{"event":"http.request.completed","method":"GET","route":"/api/orders/{orderId}","status":200,"request_id":"req-001"}
{"event":"http.request.completed","method":"GET","route":"UNMATCHED","status":404,"request_id":"req-002"}
{"event":"http.request.completed","method":"POST","route":"/api/orders/{orderId}","status":403,"request_id":"req-003"}
```

Analysis:

1. The first event receives a request-target with an `access_token` query parameter, but `URI.getRawPath()` returns only `/api/orders/42`. The route is mapped to `/api/orders/{orderId}`; neither the ID `42` nor the query value appears in the log.
2. The second event has a percent-encoded email in the path and a token in the query. Because it does not match a known route, the mapper records `UNMATCHED`; neither the email nor the token is stored in the event.
3. The third event matches the same route template as the first event but has a different method and status. This enables error analysis by method, status, and route instead of creating a separate label per `orderId`.
4. `jsonString` escapes quotes, backslashes, and control characters so values fit safely into a JSON string; in production, use your logging backend's standard JSON encoder.
5. `status` and `requestId` in this example are provided by `Sample`; a real application must obtain them from the completed HTTP response and a trusted request ID, preventing clients from injecting arbitrary log fields.
6. The demo does not log duration because it does not simulate actual request processing. For real requests, measure duration with an appropriate clock and log it in the completion event.

**Do not use the regex in this example to make access-control decisions or normalize security paths.** This is only a minimal mapper to illustrate the difference between a raw path and a matched route. The server and security framework determine routes and permissions through their own pipelines.

## 6. Designing a Structured Access Log Event

A completed-request event can carry:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "event.name": "http.request.completed",
  "service.name": "orders-api",
  "deployment.environment.name": "prod",
  "http.method": "GET",
  "http.route": "/api/orders/{orderId}",
  "http.status_code": 200,
  "duration_ms": 12.4,
  "request_id": "req-001",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

This is an illustrative JSON schema. **OpenTelemetry attribute names and how a cloud backend maps fields can vary by version**; do not assume the log system recognizes `http.route` or `http.status_code` as special fields without configuring parsing/encoding. Cross-check against the schema used in your organization.

Field meanings:

| Field | Purpose | Notes |
| --- | --- | --- |
| `timestamp` | Time when the event is emitted or request completes | Consistent UTC/offset; distinguish from ingest timestamp |
| `event.name` | Stable log event type | For example `http.request.completed` |
| `http.method` | Operation classification | Must come from the actual request; non-standard methods may occur |
| `http.route` | Matched endpoint template | Use a bounded fallback when unmatched |
| `http.status_code` | Protocol outcome | Capture the final status; status 200 does not guarantee business success |
| `duration_ms` | Request processing time | Measure with a monotonic clock; use clear units |
| `request_id` | Look up logs per request | Generate/validate at trusted ingress; can be propagated |
| `trace_id` / `span_id` | Correlate logs with distributed tracing | Propagate context properly; current span differs from request ID |
| `service.name` / environment | Identify service and environment | Attach metadata from trusted deployment configuration |

Do not force every access log to include username, email, IP, or all headers. Additional fields require a specific purpose, data classification, and appropriate retention. If a framework route template contains a dynamic ID segment, do not copy the dynamic value into metric labels.

### When the Path May Still Be Needed for Investigation

There are cases where you need to know which path a client requested—to analyze 404s, verify gateway rewrite errors, or investigate path traversal attempts. That does not mean you must **log the raw path in every event**. You can design it as follows:

- Default access log events store only `http.route` or `UNMATCHED`.
- A separately permissioned forensic/debug channel stores paths that are **length-bounded, escaped, checked for sensitive data, and subject to short retention**.
- For routing errors, log the error code, rule name, request ID, and ingress metadata, then query the gateway/WAF system by ID for the relevant evidence.
- For endpoints with tokens or emails in the path, fix the API design where possible: pass secrets via appropriate mechanisms instead of in the URL or path, since proxies, browser history, and analytics may already record them.

**Redaction is never foolproof if it relies on a single regex masking "token".** Tokens can appear in unnamed segments, different encodings, or arbitrary paths. Prefer field allowlists and route templates, combined with filters at the collection layer.

## 7. Middleware/Filter Ordering and Logging Exactly Once

A request can pass through multiple layers:

```text
Client
  -> CDN / WAF / API gateway / reverse proxy
  -> Servlet container / reactive server
  -> Authentication / authorization filters
  -> Router / controller
  -> Exception handler / response processing
  -> access log / exporter
```

If logging runs **before routing**, it usually does not know the route template yet. If it logs inside the controller, 404 or 401/403 requests rejected before the controller may be missed. If logging happens across multiple filters and interceptors, a single request may emit two or three equivalent access log lines.

You need to define:

1. **Start time:** capture monotonic time at an appropriate ingress point if latency is needed.
2. **Completion time:** log when the response is genuinely complete per the framework's contract—especially for async servlets, streaming responses, or WebFlux.
3. **Covered request set:** matched routes, 404s, authentication failures, exceptions, redirects, timeouts, and rejected requests.
4. **Correlation:** if both the gateway and the service emit access logs, use request ID/trace ID to join them and distinguish sources rather than treating multiple lines as a duplicate bug.
5. **One event per request per layer:** define clear event names/phases; if logging both start and completion, use distinct event types so they are not counted as two requests.
6. **Async/error dispatch:** filters can be invoked across multiple dispatches; frameworks provide dedicated hooks and requests may complete on a different thread than the initial one. Test to prevent duplicate or dropped events.
7. **Context synchronization:** with thread pools or reactive chains, `MDC`/`ThreadLocal` does not automatically follow every execution flow; clear/restore context after the request.

You can store the request ID in MDC so every log for the same request is easy to query. For thread-bound requests, use `try/finally` or a framework-supported scope mechanism to clear MDC after processing. However, an MDC entry is observability data, not an authoritative source for authorization.

## 8. Reverse Proxies, API Gateways, and Forwarded Headers

A proxy can rewrite the path before forwarding to the application. For example:

```text
External:  https://api.example.test/public/orders/42
Gateway:   strip /public
Internal:  http://orders-service/api/orders/42
Route:     /api/orders/{orderId}
```

If backend logs only record `/api/orders/42`, that differs from the path the client saw. If gateway logs record `/public/orders/42`, that provides another perspective. Both values can be accurate for **where the log was emitted**. Distinguish edge paths from internal paths rather than assuming one is broken.

Headers like `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto`, or `X-Forwarded-Prefix` are commonly used to pass proxy metadata. However, external clients can spoof these headers if the proxy boundary does not strip or overwrite them. **Only trust forwarded headers from an allowlisted set of proxies/network configurations** using the framework or container's mechanism, and distinguish header-derived paths from the path the server actually routed.

Avoid reconstructing full URLs from unverified headers and writing them to logs, investigative links, or redirects. The `Host` header is also controllable input. When a public-facing address is needed, use a canonical configured external URL or information from a trusted gateway.

To detect rewrite bugs, correlate gateway and application events via trace/request ID and hop metadata, then compare routes or paths according to data policy. Do not turn arbitrary client-supplied paths into metric labels.

## 9. Request Paths and Common Security Pitfalls

### Query Strings Containing Tokens, Passwords, or PII

Examples of patterns that are dangerous if logged verbatim:

```text
/reset-password?token=...
/login?password=...
/users?email=...
/oauth/callback?code=...
```

Even when the application omits the query from its logs, an upstream reverse proxy or access log may still retain the full URL. Audit **every logging point**: gateway, load balancer, WAF, servlet access log, application log, tracing attributes, APM agent, and cloud collector. Do not treat policy at a single layer as sufficient for the entire system.

### Sensitive Data in Path Segments

Paths like `/users/alice@example.com/profile` can expose identity. `/invites/{secret}` or `/download/{signedToken}` especially require avoiding raw path logging. When investigation is needed, log the matched route, event type code, and a non-secret internal ID.

### CRLF / Log Injection

A client can send a path containing percent-encoded control characters or strings crafted to mimic system log records. If the application decodes and concatenates them directly into text logs, the payload can corrupt log line boundaries. Use a standard JSON encoder for escaping, reject or avoid accepting arbitrary newlines/control characters, enforce size limits, and validate event schemas. **Escaping protects formatting; it does not validate data origin.**

### Encoded Slashes, Traversal, and Double Encoding

A URL like `/files/%2e%2e/private` may be interpreted differently by a proxy and a backend. Do not normalize a string yourself just to "clean up logs" and then use that value for security decisions or as sole evidence. Maintain separate security events recording authorization check results, the handling route/handler, and reason codes from trusted components. If raw evidence is needed, store it with strict limits and access controls.

### 404s and Arbitrary Paths Causing High Cardinality

An attacker or scanner can probe thousands of nonexistent paths. If every path becomes a metric label, series counts can explode. For metrics, use an `UNMATCHED` route or a bounded `NOT_FOUND` category; store controlled investigative events in a separate channel if individual paths truly need inspection. Rate limiting, policy-based sampling, and payload limits protect the logging pipeline from overload; **do not silently drop mandatory security events**.

## 10. Request Paths in Metrics and Distributed Tracing

Not every field suitable for logs belongs in **metric labels**. Log stores typically support searching across high-cardinality values, whereas time-series metrics systems incur heavy costs as cardinality grows.

Example:

```text
Avoid:
  http_requests_total{path="/api/orders/42"}
  http_requests_total{path="/api/orders/43"}
  http_requests_total{path="/api/orders/44"}
  ...

Prefer:
  http_requests_total{route="/api/orders/{orderId}",method="GET",status="200"}
```

This is an illustrative model; label syntax and metric names depend on your observability system. When no route matches, use a bounded value such as `UNMATCHED` or `UNKNOWN`, never a raw URI with arbitrary IDs.

In OpenTelemetry, HTTP semantic conventions define attributes for route templates and URL components. **Attribute names and instrumentation behavior can change across versions**, so verify against your actual SDK/agent and backend schema rather than hardcoding legacy names. Avoid enabling query string or sensitive raw path collection just for debugging convenience without a privacy review.

Distributed tracing should link `trace_id`/`span_id` with access logs to follow spans across services. A single trace contains multiple spans; a request ID may be generated by a gateway; the two IDs are not identical. Trace sampling may omit a trace from storage while access logs still need to be retained under a separate policy.

## 11. Measuring Request Latency and Status Alongside the Route

A path is far more actionable when paired with **status and execution time**. To identify slow endpoints, include:

```text
event=http.request.completed
method=GET
route=/api/orders/{orderId}
status=503
duration_ms=245.6
request_id=req-001
```

This is illustrative output only. In Java, `System.nanoTime()` is suitable for measuring elapsed time within the same JVM:

```java
long started = System.nanoTime();
try {
    // Process the request.
} finally {
    long elapsedNanos = System.nanoTime() - started;
    double durationMs = elapsedNanos / 1_000_000.0;
    // Log durationMs along with method, matched route, and response status.
}
```

The snippet above **is not standalone**; it must be placed inside request-processing code. Use `Instant.now()` for event timestamps, and do not subtract two wall-clock timestamps to measure elapsed time if the system clock can be adjusted.

**Async caveat:** if a request returns control immediately while the response continues to be written by an async handler or stream, a `finally` block in the initial filter may execute before the request actually finishes. Use the framework's proper completion callback/hook and clearly define whether latency measures server handler time or end-to-end response time. Do not assume that controller return always equals the moment the client receives the full response.

An HTTP status of 200 does not guarantee business success; many APIs return errors inside the response body. To detect business errors, log a separate business outcome or error code with its own schema. Conversely, 401/403 statuses occurring before route matching must still be logged according to security policy.

## 12. Testing Request Path Logging

A good test verifies both **what is logged** and **what must never be logged**. Recommended scenarios:

| Scenario | Expected Verification |
| --- | --- |
| GET `/api/orders/42` | Route template `/api/orders/{orderId}`, method GET, final status |
| GET `/api/orders/43?token=secret` | Same route; query and token absent from log |
| Path containing email `/users/alice%40example.com` | Raw email/path excluded from standard logs |
| 404 with no matching handler | Bounded fallback route; access event still emitted if policy requires |
| 401/403 before controller | Request not dropped due to hooking only at controller level |
| Exception in handler | Accurate final status/error type; no unintended duplicate events |
| Async request | Completion event emitted only when the request genuinely finishes |
| Error dispatch/retry | No duplicate request events caused by internal dispatches |
| Concurrent requests | Request ID/MDC does not leak across threads |
| Reverse proxy prefix rewrite | Internal route logged accurately with correlation to edge via request ID |
| Encoded `%2F`, `%2e`, Unicode, newline | Does not break log parser; routing/security matches container behavior |
| Query with access token, signed URL | Token absent from app/gateway/APM logs outside policy |
| Many dynamic paths | Metric cardinality does not grow with IDs; route labels remain bounded |

In Spring MVC, you can use integration tests at the `MockMvc` layer or against a real server to verify mappings, interceptors/filters, exception handlers, async handling, and header forwarding. In WebFlux, use the corresponding reactive test harness. Unit tests that only check formatters or route extraction do not prove the full logging pipeline works when deployed.

When using an async appender or collector, wait for events with a proper condition and reasonable timeout rather than relying on `Thread.sleep(1000)` to assume logs have flushed. Match event IDs/request IDs and counts to detect missing or duplicate events.

### Self-Diagnosis Sequence for Incorrect Path Logging

1. **Capture a safe sample:** method, status, request ID, route, ingress/service name, and timestamp.
2. **Identify the emitter:** reverse proxy, servlet container, access logger, controller, or tracing agent; a single request can produce multiple events.
3. **Check the phase:** was the route matched yet? Was the event emitted in a pre-routing filter, `afterCompletion`, or an async callback?
4. **Compare path forms:** raw request URI, context path, servlet mapping, query string, and external gateway rewrites—access raw evidence only when authorized.
5. **Check security configuration:** does the encoder escape properly, is redaction applied at every layer, and are forwarded headers restricted to trusted proxy boundaries?
6. **Check data quality:** are there leaked tokens, high-cardinality labels, missing status/duration, or lost request IDs?
7. **Verify at the destination:** did logs arrive at the backend under the right service, environment, schema, and retention, and can dashboards filter by route template?

## 13. Common Mistakes

| Mistake | Consequence | Appropriate Approach |
| --- | --- | --- |
| Logging `request.getQueryString()` verbatim | Easy leak of tokens, passwords, or PII | Omit query by default; use a very narrow allowlist if needed |
| Assuming `getRequestURI()` is always safe | Path segments can still contain secrets/PII | Use matched route; keep raw paths in a controlled channel |
| Using concrete paths as metric labels | Cardinality grows with every ID | Use bounded route templates/fallbacks |
| Logging only in controllers and missing 404/401 | Requests rejected before mapping are invisible | Design hooks covering pre-controller failure points |
| Logging in a pre-routing filter and expecting a route | Matched pattern is not available yet | Read pattern after routing or use fallback |
| Logging gateway and app as identical events | Double-counts HTTP requests | Tag layer/service/event phase and correlation ID |
| Using `URLDecoder` to normalize URI paths | Mishandles `+` and encoded slashes | Rely on the appropriate URI parser/framework/router |
| Trusting `X-Forwarded-*` from any client | Allows spoofing host, proto, or prefix | Accept only from trusted proxies |
| Interpolating path/user input into text logs | CRLF/log injection, broken parsers | Use JSON encoder, validation, and size limits |
| Reading MDC in thread pools without cleanup | Request ID leaks to other requests | Use context propagation and `finally`/scope cleanup |
| Measuring time with wall-clock or before async completes | Inaccurate latency | Use a monotonic clock and proper completion lifecycle |
| Logging status before exception handlers run | Logged status differs from final response | Read status at the completion phase |
| Inferring routes via log regex and using for authorization | Disagrees with the HTTP router | Obtain route/security decisions from the trusted framework |
| Testing only on local console | Misses parser/cloud ingest failures | Test end-to-end from application to log backend against schema |

## 14. Implementation Checklist for Java Web Services

- [ ] Clearly distinguish **URL, URI path, query, route template, path variable, and context path**?
- [ ] Access logs use `http.route`/route pattern instead of raw paths when raw evidence is unnecessary?
- [ ] Query strings, tokens, emails, and secrets in paths/headers are excluded from standard logs?
- [ ] If raw paths must be stored for investigation, are redaction, escaping, length limits, access controls, and separate retention in place?
- [ ] Servlet/Spring MVC/WebFlux retrieves route metadata from the framework at the right point after route matching?
- [ ] Filters/interceptors cover 404, 401/403, exceptions, and async as required without producing duplicate events?
- [ ] Request ID/trace ID is generated or validated at trusted ingress and propagated properly across threads/tasks?
- [ ] Proxy rewrites and forwarded headers have trusted boundaries so clients cannot spoof metadata?
- [ ] Metrics attach route templates with bounded cardinality rather than user IDs or raw paths?
- [ ] Tested against encoded paths, CRLF injection, Unicode, and paths containing PII?
- [ ] Latency uses a monotonic clock and status is captured after request completion?
- [ ] Verified actual events in the log backend and confirmed sensitive fields are not unintentionally logged by agents or gateways?

**Key takeaway:** in Java web logging, the "request path" is an important source of context, but it can also carry sensitive data and high-cardinality dynamic values. **For operational request logging, prioritize route template + method + status + duration + correlation ID**; keep queries and raw paths out of the default log stream, collect them under security policy only when genuinely needed, and always obtain the matched route from the framework at the appropriate lifecycle point. Distinguishing external gateway paths from internal routes keeps logs accurate, easy to analyze, and secure.
