# Response Status in Java Web Application Logging

## 1. Objectives and Context

**Response status** in a web application is the **HTTP status code of the response that the server sends or intends to send to the client**, for example **200 OK**, **201 Created**, **404 Not Found**, **429 Too Many Requests**, or **503 Service Unavailable**. When logging an HTTP request, the response status answers a critical question: **what HTTP outcome did the request end with?**

This topic belongs to **logging in web applications**, not just a list of status codes. You need to understand **when to read the status**, **how it differs from exceptions and business results**, **which requests should be logged**, **which fields to record**, **how to avoid leaking data**, and **how to correlate logs with metrics/traces or the status the client actually sees**.

After this lesson, you will be able to:

1. Understand the 1xx–5xx status classes and the observability meaning of response status.
2. Determine the **final meaningful HTTP status at the layer you are measuring**, without guessing from exceptions or controller return values.
3. Design access logs and structured events containing method, route, status, duration, and correlation ID.
4. Identify when a status is altered by security filters, exception handlers, reverse proxies, retries, or async dispatches.
5. Run a **standalone Java 17** example using `HttpServer`/`HttpClient`, capture the status after the handler, and compare it against the client response.
6. Understand design-level integration with Servlet/Spring MVC, Spring Boot, WebFlux, gateways, and OpenTelemetry.
7. Test status logging for success, client errors, server errors, and requests that never produce an HTTP response.

## 2. What Response Status Is — and What It Is Not

An HTTP response includes a status line or pseudo-header field representing a **three-digit HTTP code**. In HTTP/1.1, you typically see a status line like:

~~~text
HTTP/1.1 404 Not Found
Content-Type: application/json
~~~

The response status is **404**, not the text `"Not Found"`. HTTP/2 and HTTP/3 represent the status according to their respective protocols, but the meaning of the code remains the HTTP status.

A log event designed for easy analysis might look like:

~~~text
event=http.request.completed method=GET route=/orders/{id} status=404 duration_ms=18
~~~

This is **an illustrative record**, not a mandatory default Java output. Field names may vary depending on the backend, tracing, and logging schema. If you follow OpenTelemetry HTTP conventions, the standard attribute is **http.response.status_code**.

Do not confuse response status with:

- **Business status:** `"order=PENDING"` or `"payment=DECLINED"` are business outcomes; they may accompany HTTP 200, 202, 409, or other codes depending on the API contract.
- **Log level (severity):** INFO/WARN/ERROR is a logging choice, not an HTTP status. A 500 request might be logged at INFO in the access log while the corresponding exception is logged at ERROR elsewhere.
- **Java exception type:** `IOException`, `IllegalArgumentException`, or a custom exception does not automatically map to a fixed HTTP code.
- **Client network outcome:** timeouts, DNS failures, TLS handshake errors, or connection resets may have **no HTTP status at all**.
- **gRPC codes:** gRPC status differs from HTTP status at the transport layer, even though a call may travel over HTTP/2.
- **Upstream codes:** an API gateway might receive 500 from an internal service yet send 502 to the client, or return a cached 200 without calling the service.
- **Dashboard search results:** someone searching logs might only see the status of a single hop, not the final status of the request across the Internet.

Always attach the **observation point**: application server, reverse proxy/gateway, another service's HTTP client, or browser. A single interaction can have multiple statuses across different hops.

## 3. Classification of HTTP Status Groups

| Group | General Meaning | Examples | How to Interpret When Logging |
| --- | --- | --- | --- |
| **1xx** | Informational | 100 Continue, 101 Switching Protocols | Not always the final status of a conventional HTTP exchange. |
| **2xx** | Request processed successfully per HTTP semantics | 200 OK, 201 Created, 202 Accepted, 204 No Content | Do not assume all downstream business steps are finished; 202 means accepted for processing. |
| **3xx** | Redirection or cache/resource semantics | 301, 302, 304, 307, 308 | Can be a valid outcome; clients often follow redirects and receive another status. |
| **4xx** | Request/client-related issue per HTTP semantics | 400, 401, 403, 404, 409, 422, 429 | Not automatically a server bug. Requires endpoint, auth, and user behavior context. |
| **5xx** | Server or intermediary failed to fulfill the request as expected | 500, 502, 503, 504 | Usually a notable signal of system or dependency failure at the originating layer. |

### Common Status Codes

| Code | Common Name | Example in Web Applications |
| --- | --- | --- |
| **200 OK** | Success | Fetching data or updating with a valid result. |
| **201 Created** | Resource created | Creating a new order. |
| **202 Accepted** | Accepted | Enqueuing a job to complete processing later. |
| **204 No Content** | Success with no body | Deleting/updating with no response content needed. |
| **301 / 308** | Typically permanent redirect | Changing canonical URL; 308 preserves the HTTP method in redirect semantics. |
| **302 / 307** | Typically temporary redirect | Redirecting elsewhere; 307 preserves the method per specification. |
| **304 Not Modified** | Cache validation | Responding to a conditional request. |
| **400 Bad Request** | Invalid request | Malformed syntax or data format. |
| **401 Unauthorized** | Missing or invalid authentication credentials | Not logged in / invalid token; the name is historical. |
| **403 Forbidden** | Not permitted to perform action | Identity is known but denied by policy, or another reason per contract. |
| **404 Not Found** | Not found | Resource ID does not exist, or API intentionally avoids revealing existence. |
| **409 Conflict** | State conflict | Version conflict or incompatible resource state. |
| **422 Unprocessable Content** | Syntactically valid content that cannot be processed semantically | Business validation violation per API contract. |
| **429 Too Many Requests** | Request threshold exceeded | Rate limiting. |
| **500 Internal Server Error** | Generic server error | Unhandled exception or inability to complete the request. |
| **502 Bad Gateway** | Gateway received an invalid upstream response | Upstream error when traversing a gateway. |
| **503 Service Unavailable** | Temporarily unavailable | Maintenance, overload, or unavailable upstream depending on the layer. |
| **504 Gateway Timeout** | Gateway waited too long for upstream | Timeout between proxy and dependent service. |

This table is only a summary; specific codes must follow your **API contract and HTTP semantics**. An API may use 404 for a normal missing resource, 409 for optimistic locking, and 429 to protect the service. **Do not automatically log every 4xx at ERROR**, as this creates noise and can allow attackers to trigger log flooding.

## 4. Why Is Status an Important Field in Access Logs?

Each request typically produces **one logical access event** at a well-defined point in time:

~~~text
HTTP request → routing/auth/controller → HTTP response
                              │
                              ▼
                 status + duration + route
                              │
                              ▼
                      structured log
~~~

Combining status with other fields helps with:

- **Diagnostics:** identifying which routes frequently produce 500 or 404.
- **SLO measurement:** tracking success/error request ratios against operational targets.
- **Release analysis:** comparing 5xx rates before and after a deployment.
- **User support:** looking up a request by `requestId`/`traceId` and viewing its status and latency.
- **Abuse detection:** unusual spikes in 401/403/429 can be a security signal, though insufficient alone to conclude an attack.
- **Layer isolation:** distinguishing an application 500 from a gateway 502/504.
- **Rate-limit/cache evaluation:** 304, 429, and 503 help explain the client experience.

Do not turn access logs into the **single source of truth** for all requests. When a logging backend drops events, queues fill up, collectors go down, or retention expires, logs can be incomplete. Combine **metrics, traces, health checks, and transaction data** according to your observability requirements.

### 4.1. Recommended Fields

A reference schema:

| Field | Purpose | Security Notes |
| --- | --- | --- |
| **timestamp** | When the event was emitted/completed | Use a timestamp with an explicit timezone or UTC. |
| **service / environment** | Identifies the process and environment | Avoid confusing staging with production. |
| **http.request.method** | GET, POST, DELETE... | Normalize to avoid unexpected values from untrusted requests. |
| **http.route** | Route template, e.g., `/orders/{id}` | Low cardinality and avoids logging real IDs. |
| **http.response.status_code** | Actual determined HTTP code | Integer, not a custom string like `"200/OK"`. |
| **duration_ms** | Processing time measured with a monotonic clock | Do not compute by subtracting two text timestamps. |
| **request_id / trace_id** | Correlates events within the same request | Validate client-supplied metadata; never log tokens. |
| **error.type** | Error category when an error occurs | Do not dump sensitive full exception messages into the field. |
| **response_bytes** | Response size under a consistent definition | Do not treat body bytes as total wire bytes when framing/compression applies. |
| **client category / tenant** | Analysis within permitted scope | Log only truly needed fields with proper read access control. |

These fields are **design recommendations**, not what every framework produces by default. Use a structured encoder such as JSON and let the logging backend serialize it rather than concatenating delimiters manually, which helps prevent log forging.

JSON example:

~~~json
{
  "event": "http.server.request.completed",
  "service": "order-service",
  "environment": "prod",
  "http.request.method": "GET",
  "http.route": "/orders/{id}",
  "http.response.status_code": 404,
  "duration_ms": 18,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

This is **illustrative data**, not the default output of any specific backend. The route template contains no user ID, and the example trace ID does not belong to a real request.

## 5. When Should Status Be Captured?

A very common mistake is logging status **too early**:

~~~text
1. Request arrives            → status not yet determined
2. Security filter runs       → may reject with 401/403
3. Controller handles         → may return 200/201/204
4. Exception resolver runs    → may convert to 400/404/500
5. Response headers sent      → status begins to be sent to client
6. Body sent / finished       → I/O error may still occur after headers are sent
7. Access log completes       → record value at the designed measurement point
~~~

At the start of a request, do not immediately log **status=200** just because a response object defaults to 200. An exception, filter, redirect, authentication failure, or error page can change the outcome later.

For normal requests, emit the access event **at processing completion or close to when the response is committed**, reading the status from the layer responsible for producing the response. Distinguish between:

- **Before headers are sent:** the status can still change.
- **After the response is committed:** the HTTP status already sent to the client normally cannot be changed.
- **After the body starts sending:** I/O errors can still happen; status 200 may already have been sent even if the body is truncated. Add a transport error field if available.
- **No HTTP response:** do not invent status 500 when the connection fails before headers can be returned.

### 5.1. No Status Does Not Mean 500

In Java 17's `HttpServer`, **`HttpExchange.getResponseCode()`** returns **`-1`** if no response code has been set yet. That is **not an HTTP status of -1**; it is an API indicator that **no status exists yet**.

In tracing SDKs, the **`http.response.status_code`** attribute is only recorded **when a status is actually sent/received**. If a network/TLS/DNS timeout prevents an HTTP response from existing, record the appropriate error/exception type instead; do not force `status=0` or `status=500` and corrupt your data.

A schema might separate this case:

~~~json
{
  "event": "http.server.request.failed",
  "http.response.status_code": null,
  "error.type": "connection_aborted",
  "outcome": "incomplete"
}
~~~

This illustrates an internal schema for a missing-code scenario, **not a requirement that OpenTelemetry emit `null`**. When using standard semantic conventions, **omitting the attribute entirely** when no status exists is preferable to emitting an undefined `null`.

### 5.2. Do Not Infer Status Solely From Exceptions

A business exception can be converted by **`@ExceptionHandler`** into a `ResponseEntity` with 404, 409, or 422; a Servlet container may generate a 500 error page; Spring Security may block with 401/403 before reaching the controller. Even the same exception class may be handled differently across different APIs.

Conversely, a controller can return **`ResponseEntity.status(503)`** **without throwing an exception**. Therefore, logging like this:

~~~java
// Illustrates the wrong approach: relying only on exceptions in business code.
int status = exception == null ? 200 : 500;
~~~

is error-prone. Read the HTTP code from the **actual response** at the right layer and time; the exception is only **an additional field** when present.

## 6. Standalone Java 17 Example: Logging Actual Response Status

JDK 17 includes the **`jdk.httpserver`** module, which provides **`HttpServer`**, **`HttpExchange`**, **`HttpContext`**, and **`Filter`**. We will create an HTTP server on loopback with an OS-assigned port, send three requests using **`HttpClient`** (also built into the JDK), and use **`Filter.afterHandler`** to record the status after the handler runs.

This example requires no Maven, Gradle, Spring Boot, or external dependencies.

### 6.1. Complete Source Code

Save the file as **`ResponseStatusDemo.java`**:

~~~java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class ResponseStatusDemo {

    private static int statusFor(String path) {
        return switch (path) {
            case "/ok" -> 200;
            case "/missing" -> 404;
            case "/maintenance" -> 503;
            default -> 404;
        };
    }

    private static String routeFor(String path) {
        return switch (path) {
            case "/ok" -> "/ok";
            case "/missing" -> "/missing";
            case "/maintenance" -> "/maintenance";
            default -> "/other";
        };
    }

    private static void respond(HttpExchange exchange)
            throws java.io.IOException {
        try {
            String path = exchange.getRequestURI().getPath();
            int status = statusFor(path);
            byte[] body = ("status=" + status)
                    .getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, body.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        server.setExecutor(executor);

        List<String> accessLogs = Collections.synchronizedList(
                new ArrayList<>());
        CountDownLatch logged = new CountDownLatch(3);

        HttpContext context = server.createContext(
                "/", ResponseStatusDemo::respond);

        context.getFilters().add(Filter.afterHandler(
                "Record response status", exchange -> {
                    String route = routeFor(
                            exchange.getRequestURI().getPath());
                    int status = exchange.getResponseCode();
                    accessLogs.add(
                            "ACCESS method=" + exchange.getRequestMethod()
                            + " route=" + route
                            + " status=" + status);
                    logged.countDown();
                }));

        List<String> clientResults = new ArrayList<>();
        server.start();

        try {
            HttpClient client = HttpClient.newHttpClient();
            int port = server.getAddress().getPort();

            for (String path : List.of(
                    "/ok", "/missing", "/maintenance")) {
                URI uri = URI.create(
                        "http://127.0.0.1:" + port + path);
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .GET()
                        .build();

                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));

                clientResults.add(
                        "CLIENT path=" + path
                        + " status=" + response.statusCode());
            }

            if (!logged.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Access logging did not complete");
            }
        } finally {
            server.stop(0);
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        for (String line : accessLogs) {
            System.out.println(line);
        }
        for (String line : clientResults) {
            System.out.println(line);
        }
    }
}
~~~

### 6.2. Compile and Run

With a JDK 17 installation that includes the **`jdk.httpserver`** module:

~~~bash
javac --add-modules jdk.httpserver ResponseStatusDemo.java
java --add-modules jdk.httpserver ResponseStatusDemo
~~~

**stdout on a successful run**, with loopback networking working normally:

~~~text
ACCESS method=GET route=/ok status=200
ACCESS method=GET route=/missing status=404
ACCESS method=GET route=/maintenance status=503
CLIENT path=/ok status=200
CLIENT path=/missing status=404
CLIENT path=/maintenance status=503
~~~

The requests are sent **sequentially** and the server uses a single-thread executor, so the access log order for the three requests is deterministic. Logs are buffered in a list and printed only after **`CountDownLatch`** confirms the filter has processed all three exchanges. The output omits random ports, timestamps, and durations so it remains stable.

### 6.3. Walkthrough

- **`/ok` → 200**: the request was handled and returned OK.
- **`/missing` → 404**: the server explicitly returned Not Found; no exception was thrown in the example.
- **`/maintenance` → 503**: the handler explicitly responded with Service Unavailable, also without throwing an exception.
- **`Filter.afterHandler`** runs after the handler and subsequent filters finish, reads **`HttpExchange.getResponseCode()`**, and appends to `accessLogs`.
- **`HttpClient.statusCode()`** is the code the local client actually received from this direct endpoint.
- **`routeFor`** maps the path to a known set of routes instead of using arbitrary raw URLs as log labels. In a real application, use the matched route template from your routing framework.
- **`CountDownLatch`** and the single-thread executor are only for reproducible lesson output, not for production throughput configuration.
- **`server.stop(0)`** stops the server after the test requests complete. This example does not write log files, send to a collector, or simulate a proxy.
- **`respond`** closes the exchange after writing the body. If an exception occurs before **`sendResponseHeaders`**, `getResponseCode` can remain `-1`. This simple demo does not handle all production network failures.

**Key takeaway:** the three `ACCESS` lines record the **status emitted by the server** after the handler; the three `CLIENT` lines show the **status received by the client** for comparison. The two sets match because there is no reverse proxy and no retry/redirect.

### 6.4. Why Not Log at the Beginning of the Handler?

If you write:

~~~java
// Incorrect placement: placed before sending the response.
int code = exchange.getResponseCode();
System.out.println("status=" + code);
~~~

at this point you may get **`-1`**, not 200. The status is only known after the server decides on the code and begins the response via **`sendResponseHeaders`**. Servlet/Spring MVC applications have the same timing issue, even though the APIs differ.

### 6.5. Extension Exercises From the Example

Change the `"/maintenance"` route to 429 to simulate rate limiting; add a `"/created"` route returning 201; emit an event when `getResponseCode` is still undetermined; observe what happens if the filter measures status after the handler when the handler fails before sending headers. **Do not map `-1` to 500** if the server has not sent an HTTP response.

This program also has design limitations: storing access events in an unbounded list would exhaust memory under continuous traffic, and the demo lacks a structured JSON encoder, backpressure, or fail-safe auditing. Production systems should use a controlled observability framework or logging backend rather than buffering every event in an in-memory list.

## 7. Servlet API and Spring MVC: Which Layer Should Capture Status?

In a Servlet-based web application, **`HttpServletResponse`** provides **`getStatus()`**, **`setStatus(...)`**, **`sendError(...)`**, and **`sendRedirect(...)`**. The filter layer can observe the response passing through the filter chain; Spring MVC has controllers, argument conversion, validation, and exception resolvers that participate in deciding the status.

### 7.1. Three Ways an Endpoint Produces a Status

**Success case with `ResponseEntity`:**

~~~java
// Spring MVC illustration; requires dependencies and an enclosing class.
@GetMapping("/orders/{id}")
public ResponseEntity<OrderDto> getOrder(@PathVariable String id) {
    OrderDto order = service.getOrder(id);
    return ResponseEntity.ok(order);
}
~~~

**Returning 201 after creating a resource:**

~~~java
// Spring MVC illustration, not a standalone class.
@PostMapping("/orders")
public ResponseEntity<OrderDto> create(@RequestBody OrderInput input) {
    OrderDto created = service.create(input);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

**Converting an exception into an HTTP response:**

~~~java
// Illustration inside an appropriate @RestControllerAdvice.
@ExceptionHandler(OrderNotFoundException.class)
public ResponseEntity<Void> notFound(
        OrderNotFoundException exception) {
    return ResponseEntity.notFound().build();
}
~~~

These snippets **cannot run standalone**: they require Spring Web, DTOs/services/exceptions, and the corresponding imports. They show that an exception can be translated into **404**, not necessarily **500**. In addition, validation, security, CORS, and gateways can determine the status **before the controller ever runs**.

### 7.2. Filter, Interceptor, Controller Advice: Different Roles

| Location | Advantages | Limitations to Remember |
| --- | --- | --- |
| **Servlet Filter** | Wraps most of the request/response in the filter chain; can record duration and status. | Must handle dispatcher types, async, and error dispatches; may not see status after container-generated error pages. |
| **HandlerInterceptor** | Has Spring MVC handler/route context; convenient for attaching route templates. | May miss requests blocked before `DispatcherServlet` or errors in filters/gateways. |
| **Controller / `@ExceptionHandler`** | Knows business meaning and explicitly produced statuses. | Easy to miss pre-controller errors; logging in multiple places causes duplicates. |
| **Framework observability** | Can standardize metrics/traces for the HTTP lifecycle. | Must verify framework/version/config and which fields are collected. |
| **Proxy/Gateway access log** | Reflects the status the gateway actually sends at the outer edge. | Does not inherently know deep Java exception and business context. |

**There is no single Java hook that accurately observes every error path across every stack.** Choose the execution layer based on your goal: whether you want to know what the controller decided, what the gateway actually sent, or what the client observed end-to-end.

### 7.3. Caution With `OncePerRequestFilter`

In Spring MVC, **`OncePerRequestFilter`** restricts execution to **once per request dispatch**, which does not guarantee "once per logical request" across all async and error dispatches. Spring's documentation notes that **`REQUEST`, `ASYNC`, and `ERROR`** dispatches can participate in the lifecycle and provides methods to filter them selectively.

If you write:

~~~java
// Illustration of the idea for a standard synchronous request.
long start = System.nanoTime();
try {
    filterChain.doFilter(request, response);
} finally {
    log.info("method={} status={} duration_ms={}",
            request.getMethod(),
            response.getStatus(),
            (System.nanoTime() - start) / 1_000_000);
}
~~~

do not treat this as a complete end-to-end implementation. When a request transitions to async processing, the **`finally` block of the initial dispatch** can run before the final response is ready. When an exception has not yet been converted by the framework/container into an error response, **`getStatus()` inside `finally`** may not yet reflect the status the client receives. Similarly, an **`ERROR` dispatch** may run afterward or in another pass; logging in both dispatches without rules can create duplicates.

Production solutions typically rely on the framework's built-in instrumentation, or design a filter/listener that handles **`AsyncListener` (complete/error/timeout)**, error dispatches, and a tested **once-only logical completion guard**. Do not slap together a simple `finally` block and claim it "always logs the final status."

### 7.4. `RequestLoggingFilter` and Response Status

A filter that only logs requests before/after may lack a standard status field. For example, in Spring, **`AbstractRequestLoggingFilter`** / `CommonsRequestLoggingFilter` is intended to log request details and has its own rules for async dispatches; do not assume it replaces full access logging with status, latency, route template, and exception classification. Always inspect the actual output.

## 8. Spring Boot and Observability

Spring Boot integrates observability via Micrometer Observation depending on dependencies, configuration, and version, while Spring Framework supports observation for HTTP servers and clients. In servlet applications, instrumentation can create observations for requests/responses, and metrics/tracing exporters can extract status from them.

Things to verify:

- Has the application added the **right dependencies** and enabled observation/metrics/tracing?
- Is it using the **Servlet stack (Spring MVC)** or the **reactive stack (WebFlux)**?
- Does the observability configuration collect the **status code**, and which route label is attached?
- Is custom filter/controller logging duplicating access logs from Tomcat/Jetty/Undertow or the gateway?
- Does **an observation/timer** measure the full time to send the response or only handler execution time? This depends on the framework and instrumentation.
- Are **Spring Boot Actuator** and an appropriate exporter enabled if the goal is SLO dashboards rather than just text logs?

Metric or tag names can vary by exporter and version. OpenTelemetry HTTP semantic conventions use **`http.response.status_code`** for the numeric status **when a response was sent/received**; **`http.route`** should be a low-cardinality route template. In Spring Framework, an observation may be named **`http.server.requests`**, which an exporter may translate into another standard metric name.

**Do not drop access logs just because you have metrics**, as metrics are usually aggregated. Conversely, do not rely solely on logs to compute SLOs if logs can be dropped. Combine them sensibly based on cost and goals.

## 9. Status and Log Levels (INFO/WARN/ERROR)

A practical strategy is to record **every observed HTTP request** as **one access event at an appropriate level**, and emit separate error logs when a stack trace or cause is needed.

You can use a sample policy like this:

| HTTP Status | Suggested Access Log Level | Rationale |
| --- | --- | --- |
| **2xx** | INFO or dedicated access event | Normal flow. |
| **3xx** | INFO/DEBUG depending on volume | Redirects/cache hits are usually normal. |
| **Expected 400/404** | INFO or WARN per endpoint | Clients may send invalid requests; not necessarily a system error. |
| **401/403** | INFO/WARN and security signal per policy | Can be normal behavior or abuse; avoid logging credentials. |
| **409/422** | INFO/WARN per contract | Expected business/validation outcomes. |
| **429** | WARN or aggregate/rate-limit metric | Can occur at high volume; avoid per-request log floods if unnecessary. |
| **5xx** | WARN/ERROR depending on ownership; error event with cause | Usually requires investigation; can occur at proxy, app, or dependency. |

This is an **illustrative policy**, not a mandatory rule. Some systems put access logs in a separate channel without varying severity by status, storing the numeric field instead and alerting on metrics. That approach is completely valid as long as logs remain searchable and no information is lost.

Do not automatically log an ERROR stack trace for **every 404**. Conversely, a 200 event where a business invariant was violated may still warrant a business error log. **HTTP status, severity, and outcome are three distinct dimensions.**

### 9.1. Avoiding Duplicate Logs

If you have:

- Reverse proxy access logging
- Tomcat access log
- A custom servlet filter
- A Spring interceptor logging at the end of a request
- A controller logging `"request completed"`

a single request can generate **multiple** valid or redundant records. Define the purpose of each source clearly and use distinct event/source names, such as `gateway.access` and `app.http.server.completed`; each **logical request at each layer** should have a single-write rule by design to prevent unintended duplication.

## 10. Misleading Status Scenarios

### 10.1. Redirects: 302 Followed by 200

A browser calls **`GET /old`**, the server sends **`302 Location: /new`**, and the browser follows with `GET /new` and receives **`200`**. If the client automatically follows redirects, the final client result shows 200 while the server access log contains **one 302 request and one 200 request**.

Do not assume one of the logs is wrong. They are **two separate HTTP exchanges**. Use an appropriate trace or correlation ID to link them rather than collapsing them into a single status.

### 10.2. Gateway Status Differs From Application Status

~~~text
Client → Gateway → Order Service
            │            │
            │         HTTP 500
            │◄───────────┘
            │
         HTTP 502  → Client
~~~

This is a hypothetical example: a gateway **can** translate an upstream error into another code based on configuration, though not every gateway turns 500 into 502. A gateway may also return 503/504 when it cannot connect to upstream, while the app **emits no status at all** for that request.

Therefore, record **service, hop/role, route, and trace ID** so you can distinguish statuses logged at the gateway from those logged at the application.

### 10.3. Errors After Headers Are Sent

The application sends status **`200`** and part of the body; then the stream fails or the client disconnects. The app log may show 200 because the headers were already committed, while the client did not receive a complete response.

Depending on instrumentation, include a separate field such as **`error.type=broken_pipe/client_disconnected`**, **`response_completed=false`**, or an equivalent outcome **if observed**. Do not overwrite an already-sent status with 500 just to reflect a body failure.

### 10.4. Async, Streaming, SSE, and WebSocket

- With **async servlet requests**, the initial controller/filter may return control before the response finishes.
- With **streaming/SSE**, headers may send 200 while the connection stays open; access logs at commit time and stream close measure **two different milestones**.
- With **WebSocket upgrades**, **`101 Switching Protocols`** describes the handshake, not the status of individual WebSocket messages.
- With **serverless or gateways**, the platform may generate or modify statuses outside Java code.

Record the event/phase name or appropriate fields so dashboards do not mix "headers sent" with "full body completed."

### 10.5. Retries Between Services

An HTTP client may call an upstream service three times: 503 on the first attempt, 503 on the second, and 200 on the third. The upstream access log has **three exchanges**; the client's log may record one successful **logical business operation**. Do not calculate upstream error rates from a single aggregated client event and conclude there were no 503s.

Distinguish between **request attempt ID**, **logical operation ID**, and **trace/span IDs**. To measure retries, use a `retry_attempt` field or a dedicated metric when observable.

### 10.6. Caching and Conditional Requests

**304 Not Modified** indicates a successful cache exchange even without a response body like 200. Traffic served by a cache or CDN may never reach the origin service, so origin access logs do not cover all client requests.

### 10.7. Status 401 and 403

Typically 401 relates to **missing or invalid authentication credentials**, while 403 relates to **access denial**. However, an API may return 404 instead of 403 to avoid disclosing a resource's existence per policy. When logging, never include tokens, cookies, passwords, or the full `Authorization` header in the record.

A user submitting wrong credentials repeatedly can increase 401s, but status alone is not enough to conclude an attack; combine rate, source, behavior, policy, and other security signals.

## 11. Status, Metrics, and SLOs: Measuring the Right Denominator

A common simple formula:

~~~text
HTTP 5xx ratio = number_of_5xx_responses / number_of_eligible_requests
~~~

However, you must define it precisely:

- What are **eligible requests**? Does the denominator include health checks, load balancer probes, static assets, or internal admin APIs?
- **Observation layer:** gateway, application, or client? If both app and gateway log, never sum them directly without deduplicating or separating layers.
- **4xx statuses:** 404 may be normal on a search resource; 429 may count against an SLO for one user tier but not another.
- **Timeouts without an HTTP status:** counting only response statuses may miss requests that dropped before headers.
- **Sampling/drops:** if logs are sampled or queues drop events, log counts do not equal actual request counts.
- **Time windows:** define event time vs. ingest time and handle late arrivals.
- **Route cardinality:** never create metric labels from full URLs containing IDs; use route templates.

An API with a low 5xx rate that returns wrong data in 200 responses can still have a business incident. Also monitor **latency, business transaction success, dependency errors, saturation, and traces**.

### 11.1. OpenTelemetry HTTP Status and Span Status

Per HTTP semantic conventions, **`http.response.status_code`** records the numeric status when a status actually exists. For **server spans**, 4xx **does not automatically set the span status to Error** by default; 5xx is typically marked as Error. A 404 is sometimes an expected outcome.

Do not confuse the tracing **span status** (e.g., Error) with **`http.response.status_code`**; they serve different purposes. A 500 is usually an error signal, but the rules around context and failed requests with no response still apply.

## 12. Security and Privacy When Logging Status

Status codes themselves rarely contain PII, but **accompanying fields** can be highly sensitive.

### 12.1. Do Not Log Excess Data

Avoid logging:

- Full **`Authorization`**, **`Cookie`**, session tokens, or API keys.
- Request/response bodies containing passwords, payment details, or unnecessary personal data.
- Full query strings containing emails, tokens, or free-form user input.
- IP addresses, user IDs, or account IDs without a clear purpose, policy, and appropriate access control.
- Raw exception messages when they may contain URLs, SQL parameters, or user data.

To support troubleshooting a request, prefer validated **request IDs/trace IDs**, **method, route template, status, and duration**; loggers can retain the error class instead of the raw payload.

### 12.2. Log Injection From Paths or Headers

Raw URLs, `user-agent`, `x-request-id`, or custom metadata can contain special characters. When concatenating text access logs, untrusted data can inject fake lines (CR/LF) or break delimiters. Use a **structured encoder** and escape according to the output format; validate ID fields against their grammar.

A route template like **`/orders/{id}`** does not expose order IDs, has low cardinality, and works well for metrics. If a resource ID is still needed for investigation, evaluate purpose, redaction, and read permissions.

### 12.3. Protecting Access Log Read Permissions

Access logs can reveal that someone is viewing a sensitive endpoint, even without a body. Enforce RBAC/ABAC on collectors and dashboards, restrict exports, and manage retention and access auditing per organizational policy. CSV exports, downloads, and reports must also be controlled.

## 13. Integration With Logback, Log4j2, and JUL

### 13.1. Choosing How to Log a Schema-Compliant Event

With SLF4J and a suitable backend, an illustrative example in an existing project with a logger:

~~~java
// Illustrative snippet; not a standalone Java class.
logger.info(
        "http.request.completed method={} route={} status={} duration_ms={}",
        method, routeTemplate, responseStatus, durationMillis);
~~~

Do not rely solely on string interpolation if you need to query status as a numeric field. Use SLF4J 2.x **key-value pairs** (with a supporting provider/encoder) or a dedicated structured JSON layout to preserve typed fields.

With Logback, Log4j2, or JUL, the backend's job is to serialize events and write them to appenders/handlers. **HTTP status is not a backend log level**, so setting the root logger to INFO/WARN/ERROR does not map to status 200/400/500.

### 13.2. Dedicated Access Logs

Servlet containers like Tomcat provide built-in access logging, typically emitting events in a predefined format. An access log pattern can supply method, URI, status, and bytes/duration depending on the server. However, the pattern syntax **differs** from Logback's `PatternLayout`. Do not use Logback converters expecting Tomcat's access log to understand them.

When enabling container-level access logs, check:

- Is the status field truly the **final status at the container layer**?
- Does it log requests blocked by security filters?
- Does it log async and error response cases?
- Where are files/streams written, and how are retention/rotation configured?
- Does it duplicate logs from a Spring filter or gateway?
- Are fields like query strings and `user-agent` sanitized?

### 13.3. Level and Volume

Logging an INFO record for every request in a service handling tens of thousands of RPS can produce massive log volume. Depending on operational needs, use dedicated access logs, deliberate sampling, or aggregated metrics. **Never sample mandatory audit/security events** just to cut costs, and understand how sampling affects counts.

Make a clear architectural choice: **count requests with metrics**, **investigate specific requests with traces/logs**, and **observe errors with logs/alerts**, rather than forcing one tool to do everything if it cannot meet reliability requirements.

## 14. Testing Response Status Logging

Test matrix for a web application:

| Scenario | Expected Client Response | What to Verify in Logs |
| --- | --- | --- |
| Successful GET | 200 | One event with `status=200` and the correct route. |
| Resource creation | 201 | `status=201`, not defaulting to 200. |
| Successful delete without body | 204 | `status=204`, no body needed for verification. |
| Redirect | 301/302/307/308 | Each exchange is logged, not just the post-redirect status. |
| Conditional cache | 304 | Recognized as a valid status with no body. |
| Invalid payload/syntax | 400 | `status=400`, no sensitive body logged. |
| Missing authentication | 401 | `status=401`, no token/header leaked. |
| Forbidden | 403 or 404 per policy | Records the exact code sent without exposing private data. |
| Missing resource | 404 | Does not automatically log ERROR for expected 404s. |
| Conflict/version | 409 | Does not turn mapped business exceptions into 500. |
| Semantic validation | 422 | Not confused with Java exception types. |
| Rate limit | 429 | Correct status, metric recorded, protected against log floods. |
| Unhandled exception | Usually 500 if server can return HTTP response | Logs accurate status after resolution/container; stack trace per policy. |
| Service maintenance | 503 | Distinguishes explicitly returned status from exceptions. |
| Gateway timeout | 504 at gateway | Check gateway logs; the app may not see the same status. |
| Connection reset before headers | No status | Does not invent 500 or 0. |
| Streaming body aborted after 200 | Headers may already be 200 | Separate error/outcome recorded; sent status is not overwritten. |
| Async servlet | Depends on final outcome | Does not log status too early or duplicate events. |
| Request via gateway | May differ from app | Includes hop/service field and correlation ID. |
| Multiple retries | Each attempt has its own status | Does not collapse all attempts into the final status. |

### 14.1. Writing Assertions

An integration test can verify:

1. The client actually receives the expected status.
2. The server's access event has the right status, route, method, and request ID.
3. There is **one logical access event at the defined layer** per exchange, with no duplicates from filter dispatches.
4. No tokens, passwords, cookies, or sensitive raw bodies appear in the event.
5. Valid 4xx responses do not generate unnecessary stack traces or spam alerts outside policy.
6. Exception-driven 5xx responses are logged after the status is determined, or intentionally omit status if no response could be sent.
7. Route templates have low cardinality and contain no sensitive path parameters.
8. When testing through a proxy, verify **gateway status** and **app status** using two distinct datasets.

For Spring MVC, **`MockMvc`** can verify status on the controller/`DispatcherServlet` path, but it does not necessarily simulate the full container, gateway, async lifecycle, or production routing. Add integration tests against a real server when verifying the final measurement point.

## 15. Diagnosing Mismatches Between Logged Status and Client Status

Example: the client receives **500**, while the controller log records **200**.

### Step 1 — Confirm It Is the Same Request

Compare method, route, timestamp, `requestId`/`traceId`, service, instance, and deployment version. Avoid comparing two different requests that happen to share the same URL.

### Step 2 — Identify the Two Observation Layers

Is the controller log at the application? Was the client status decided by a gateway? Is there a WAF, load balancer, cache, or service mesh in between? Across two hops, statuses can legitimately differ.

### Step 3 — Check the Logging Timing

Was the 200 line written before the filter chain finished? Did an exception resolver, error dispatch, or response commit change the status afterward? If 200 was already committed and the body failed, the client might report a transport error rather than a true 500.

### Step 4 — Inspect Logging and Exporter Configuration

Were events dropped? Are there two different access log sources? Did a parser change the status type, a collector normalize it, or a dashboard display a different hop's status?

### Step 5 — Verify With an Isolated Request

Send a test request with a safe correlation ID, capture the status at the client, capture access logs at both the application and gateway, and inspect the corresponding trace. Use **one request at a time** to avoid concurrency confusion, then retest under load.

### Step 6 — Fix at the Source

If logged too early, move the capture point to the appropriate completion hook. If a gateway rewrites it, tag the source/hop. If a controller logs a predicted status, replace it with the actual status. If a parser is wrong, fix the schema rather than changing the controller's HTTP code.

**Never alter old logs or label a 200 record as 500 just to make a chart look right**; faulty observability must be fixed in instrumentation with regression tests.

## 16. Common Pitfalls to Avoid

**1. Logging 200 at the start of the request.** Status can change to 401, 404, or 500 after filters, controllers, or exception handlers run.

**2. Inferring status from exceptions.** Exceptions can be mapped to 404/409; a 503 response can be returned without any exception.

**3. Treating every 4xx as a critical server error.** 404, 409, 422, and even 401 can be expected API outcomes. Analyze frequency and context.

**4. Treating response status and log severity as the same thing.** `status=500` does not mean every access log must be ERROR; establish a clear schema and policy.

**5. Assuming root INFO suppresses all ERROR events.** Log levels and HTTP statuses have no default mapping, and filters/appenders can have their own rules.

**6. Logging only in controllers.** Security filters, static resources, error pages, and gateways may bypass controllers.

**7. Forgetting async and ERROR dispatches.** Access filters may log twice or log before the final response is sent.

**8. Confusing gateway 502/504 with service 502/504.** A different layer may have generated the status.

**9. Turning timeouts/no-response into status 0 or 500.** Only record numeric status when a value exists; log network errors separately.

**10. Using raw URLs as metric labels.** Paths with order IDs explode cardinality and can leak data.

**11. Logging full URLs/queries/bodies for debugging convenience.** This can leak tokens/PII, enable log injection, or inflate costs.

**12. Computing SLOs from sampled/dropped logs without adjustment.** Use reliable metric sources, define the denominator, and specify the measurement layer.

**13. Ignoring redirects and retries.** One user action can produce multiple HTTP exchanges with different statuses.

**14. Omitting service/environment/trace.** When statuses mismatch, it is hard to tell which hop produced the record.

**15. Testing only 200 and 500.** This misses 201, 204, 304, 401, 403, 409, 429, and framework/security-generated statuses.

**16. Including raw exceptions in every access event.** Increases volume and risks data exposure; separate standard access events from error details per policy.

**17. Assuming an HTTP status means the client received the full body.** I/O errors can happen after headers are sent.

**18. Assigning the final `HttpClient` status to every redirect hop.** Each hop has its own status; client and server logs must define their scope.

## 17. Practice Exercises

**Exercise 1 — Run Java 17.** Compile and run `ResponseStatusDemo.java`, and compare the three `ACCESS`/`CLIENT` pairs. Why is `status=503` logged even though the code throws no exception?

**Exercise 2 — Add 201.** Extend `statusFor` with `/created` returning 201; add a client request and increment `CountDownLatch` accordingly. Predict the exact output order.

**Exercise 3 — Inspect undetermined status.** In a test environment, observe `getResponseCode` before `sendResponseHeaders`. Explain why `-1` must not be emitted as HTTP 500 in the status field.

**Exercise 4 — Spring MVC.** Design three endpoints: 200 success, 404 missing resource via `@ExceptionHandler`, and 503 service unavailable without throwing an exception. Identify where status should be measured to capture all three.

**Exercise 5 — Spring Security.** An unauthenticated request receives 401 or a redirect depending on authentication configuration. Is the controller invoked? Which filter/interceptor can observe the status?

**Exercise 6 — Async.** Explain why a filter logging in the `finally` block of the initial dispatch can print `status=200` even if the request ultimately fails, and how to choose a completion hook.

**Exercise 7 — Gateway.** Suppose a gateway terminates with 504 while the app has a slow request. Which logs/metrics at the two layers should you compare?

**Exercise 8 — Privacy.** Transform the URL `/users/1234/orders?token=secret` into a log using the route template `/users/{id}/orders`; identify which fields are safe to keep for correlation.

**Exercise 9 — SLO.** Write a `5xx ratio` definition with a clear denominator, excluding health checks if policy requires, and handling timeouts with no response. Why should you not compute it directly from line counts across two different access log sources?

## 18. Key Takeaways

**Response status in Java web logging is the actual HTTP code determined at a specific observation layer, not a value guessed ahead of time from exceptions or controllers.** To capture it accurately, understand **completion/commit points**, **async/error flows**, how **gateway** statuses can differ from the application, and how **retries/redirects** can generate multiple statuses.

A good access event typically includes **method, route template, numeric status, duration, service/environment, and correlation ID**, without secrets or excess data. Status logs aid investigation; metrics and tracing measure system health. When no HTTP response exists, **leave the status absent and represent the transport error separately** instead of fabricating a fake code.

### Official References

- RFC 9110 — HTTP Semantics and status codes: https://www.rfc-editor.org/rfc/rfc9110
- Oracle Java 17 — HttpExchange, sendResponseHeaders, and getResponseCode: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java 17 — HttpServer: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java 17 — Filter.afterHandler: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html
- Spring Framework — OncePerRequestFilter Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — Observability Support: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- OpenTelemetry — HTTP semantic conventions: https://opentelemetry.io/docs/specs/semconv/http/http-spans/
- OpenTelemetry — HTTP metrics: https://opentelemetry.io/docs/specs/semconv/http/http-metrics/
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html