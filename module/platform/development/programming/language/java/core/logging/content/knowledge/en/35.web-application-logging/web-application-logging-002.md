# Request method in Java Web Logging: recording HTTP methods accurately and safely

## 1. What is a request method and why must it be logged?

An HTTP request has a **method** representing the action that the client asks the server to perform on the target resource. Common methods include GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS. In Java web application logs, the method helps answer key questions:

- Is an endpoint receiving queries (GET) or state-changing requests (POST/PUT/PATCH/DELETE)?
- Why does the same `/orders` path return 200 for GET but 405 for another method?
- Are there any unauthorized requests, CORS preflight requests, retries, or unusual probes?
- How are 4xx/5xx errors and p95/p99 latency distributed by method and route?
- Which method did a trace/request ID pass through at the gateway, application, and downstream services?

A concise, structured access log might look like this:

~~~text
http_request method=GET route=/orders/{id} status=200 duration_ms=12 request_id=req-101
http_request method=POST route=/orders status=201 duration_ms=45 request_id=req-102
http_request method=DELETE route=/orders/{id} status=403 duration_ms=3 request_id=req-103
~~~

The lines above are **illustrative**, not default Java output. Key points: the method is placed in a **separate field**, `route` is an application-defined template, `status` is the HTTP status, and `request_id` correlates related lines.

**Do not equate HTTP method with a Java method name.** HTTP POST is not a call to a function named `post()`; Spring `@PostMapping` maps an HTTP method to a Java handler. When logging, you must clearly identify the source of the HTTP method rather than inferring it from controller names, annotations, or business actions.

This article belongs to the **Logging in Web Applications** series. The focus is on extracting, normalizing, logging, and using the request method field in Java logging without distorting HTTP semantics, leaking data, or causing uncontrolled metric cardinality.

## 2. HTTP methods per RFC: semantics and common misconceptions

An HTTP method is a token in the request. Method tokens are **case-sensitive** according to HTTP Semantics; `GET` is the standard method, whereas `get` is not automatically equivalent to `GET`. Proxies, servers, or frameworks may reject or handle extension methods according to their own configuration.

| Method | Typical meaning | Safe per RFC? | Idempotent by default? | Logging guidance |
| --- | --- | --- | --- | --- |
| GET | Retrieve a representation of the resource | Yes | Yes | Log GET and route template; do not log queries containing tokens |
| HEAD | Like GET for metadata, but without returning response content | Yes | Yes | Separate HEAD from GET in metrics; do not count response body size like GET |
| POST | Process request content according to resource semantics | No | Not guaranteed | Do not infer that a resource was created solely from the method |
| PUT | Create/replace the target resource state per PUT semantics | No | Yes | Retries may produce multiple access logs with the same intended effect |
| PATCH | Apply a set of changes to a resource | No | Not guaranteed | Do not assume PATCH is always idempotent; depends on design |
| DELETE | Request removal of the current representations of a resource | No | Yes | Repeated calls may return different statuses while remaining idempotent |
| OPTIONS | Query communication options, commonly seen in CORS preflight | Yes | Yes | Classify preflight separately to avoid confusing with business traffic |
| TRACE | Request a message loop-back for HTTP diagnostics | Yes per RFC definition | Yes | Often restricted/disabled due to information disclosure risk; monitor unusual requests |
| CONNECT | Request establishing a tunnel to the target | No | Not guaranteed | Mainly at proxies; not a typical application endpoint by default |

**Safe** in the RFC means the client does not request a state change according to the method's semantics. It **does not mean** the request produces no side effects at all: the server can still generate access logs, counters, metrics, and cache activity.

**Idempotent** means the intended effect of multiple identical requests is the same as a single request; it does not mean the server writes only one access log. A DELETE sent three times can emit three access events, even though the delete action has idempotent semantics. The returned status of each attempt may still differ.

POST can be designed by an application to be idempotent using an idempotency key, but that property does not come automatically from the method name alone. PATCH may or may not be idempotent depending on its specification and patch definition. You should not infer business outcomes solely from the method column in logs.

### Status 405 and 501

According to HTTP Semantics:

- **405 Method Not Allowed**: the method is recognized/implemented by the server but **is not allowed on the target resource**. A 405 response must include an `Allow` header listing the supported methods for that resource.
- **501 Not Implemented**: the method is not recognized or not implemented by the server; the RFC recommends this status for that case.

A framework or reverse proxy may return 405/501 before the request reaches a controller. Therefore, if you only log inside controllers, you may completely miss requests blocked at an earlier layer.

### HTTP/2 and HTTP/3

In HTTP/2, the method is represented by the `:method` pseudo-header on the wire. Java Servlet applications still typically see the method through the standard API (`HttpServletRequest.getMethod()`), without needing to read pseudo-headers manually or reconstruct an HTTP/1.1 request line. Logging the method from a request API already parsed by the server/container is preferable to logging an arbitrary client-supplied header.

## 3. Which fields should accompany the request method?

An operational web request event typically includes the following fields:

~~~json
{
  "timestamp": "2026-11-10T03:00:00Z",
  "event_type": "HTTP_REQUEST_COMPLETED",
  "service": "orders-api",
  "method": "GET",
  "route": "/orders/{id}",
  "status": 200,
  "duration_ms": 12,
  "request_id": "req-101",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

This is an **illustrative schema**, not automatic output from JUL, Servlet, or Spring. You may also need response size, protocol, client class, outcome, or error category depending on your goals.

| Field | Recommended source | Notes |
| --- | --- | --- |
| method | HTTP request method parsed by server/container | Use the value observed at the specific layer; do not read from arbitrary headers |
| route | Route template resolved by router/framework | `/orders/{id}`, not `/orders/42?token=...` |
| status | Final HTTP result when request completes | Exceptions/async can mean an initial status is not yet final |
| duration_ms | Monotonic clock for elapsed time | Use `System.nanoTime` for elapsed; do not subtract wall-clock timestamps |
| request_id | Trusted system-issued ID or validated ID | Do not use arbitrary client tokens directly |
| trace_id | Valid trace context if present | Does not prove user identity |
| service | Deployment/application configuration | Avoid taking service name directly from user input |
| outcome | Success/failure by explicit definition | 4xx can be an expected client error, not a bug |
| request_bytes/response_bytes | Actual size measured at the appropriate layer | `Content-Length` does not always reflect actual bytes transferred |

**The method alone is not enough to conclude whether a request succeeded.** `POST status=201`, `POST status=400`, and `POST status=500` are three different outcomes. For debugging, combine method, route, status, latency, trace/request ID, and error category without putting sensitive payloads into logs.

## 4. How to obtain the HTTP request method in Java

### 4.1. Jakarta Servlet: HttpServletRequest.getMethod()

In Servlet/Jakarta EE/Spring MVC applications, the standard API is:

~~~java
// Snippet requires Jakarta Servlet API; does not run standalone with JDK.
String httpMethod = httpServletRequest.getMethod();
~~~

With Jakarta Servlet, the interface is `jakarta.servlet.http.HttpServletRequest`. Legacy applications may use `javax.servlet.http.HttpServletRequest`; choose the namespace matching your framework/server version.

`getMethod()` returns the HTTP request method name as recognized by the Servlet container, such as `GET` or `POST`. This comes from the request processed at the container layer, **not from `request.getParameter("method")`**. However, because the input ultimately originates from the client, unknown or custom methods still need to be controlled when used as labels or log text.

### 4.2. Java HTTP Server in the JDK

The JDK's `jdk.httpserver` module provides `com.sun.net.httpserver.HttpExchange.getRequestMethod()`. It works well for Java 17 examples without external libraries:

~~~java
// Snippet inside a JDK HttpServer HttpHandler.
String method = exchange.getRequestMethod();
~~~

`HttpExchange` represents a request to a minimal HTTP server in the JDK. It **differs from `HttpServletRequest`** and does not replace a production Servlet container or Spring MVC. The complete example in Section 7 uses this API.

### 4.3. Spring MVC/Spring Boot

In a Spring MVC controller:

~~~java
// Spring MVC snippet; requires Spring Web and framework-provided method parameters.
@GetMapping("/orders/{id}")
public ResponseEntity<String> getOrder(
        HttpServletRequest request,
        @PathVariable String id) {
    String observedMethod = request.getMethod();
    return ResponseEntity.ok("order");
}
~~~

This is a snippet, not a standalone Spring Boot application. A controller only observes requests routed to that specific handler; requests rejected by a gateway, Spring Security, CORS, or a servlet filter may never reach the controller. For **consistent access logs across all routes**, consider a filter, interceptor, or web server/gateway access logging.

Spring WebFlux uses a different request model (such as `ServerHttpRequest.getMethod()`); do not copy Servlet filters directly to a reactive stack. In reactive/async requests, measure at publisher/response completion rather than assuming the response is finished when the handler method returns.

## 5. Method is not an arbitrary log string

Per HTTP, a method is a token. Servers usually validate syntax in the HTTP parser, but an extension method can still produce rare or unexpected values. If you use the raw method as a metric label, file name, logger name, or route, the risk of high cardinality or injection/misconfiguration increases.

A **classification helper for logging/metrics** can look like this:

~~~java
// Java 17 snippet. Do not use this method to make authorization decisions.
static String methodBucket(String raw) {
    if (raw == null) {
        return "OTHER";
    }
    return switch (raw) {
        case "GET", "POST", "PUT", "PATCH", "DELETE",
             "HEAD", "OPTIONS", "TRACE", "CONNECT" -> raw;
        default -> "OTHER";
    };
}
~~~

Benefits:

- Only pre-designed labels appear in histograms or dashboards.
- No new metric series is created for each unusual method.
- Does not automatically rewrite `"get"` to `"GET"`, because HTTP methods are case-sensitive.
- Prevents untrusted values from choosing target files, indices, or logger categories.

**Important note:** `methodBucket` is only for **log/aggregation output**. Deciding whether a `GET` request is allowed still uses the original method or the HTTP server's dispatch result. If you replace the original method with `OTHER` before routing, you may lose the information needed to return 405/501 properly or mislead security checks.

If you need to investigate security requests with unusual methods, you can store a separate `raw_method` field that is **escaped and length-limited** in an appropriately restricted stream. Avoid turning that value into a metric label with unbounded cardinality.

## 6. When to write the access log?

There are three distinct points in time:

1. **On request arrival:** log `request_started`, knowing the method but not yet the outcome. Useful for investigating hung requests.
2. **When the application decides the status:** knows business routing and expected validation/exceptions, but the response may not be fully sent yet.
3. **When the request/response completes at an observation layer:** can report the actual status and elapsed time of that layer. This is usually the right place for a summary access log.

If you start by logging:

~~~text
request method=POST route=/orders status=201
~~~

**before committing the response**, and a socket error occurs while writing the response body, that log does not prove the client received a complete 201 response. Name fields accurately—such as `status_decided`, `status_written`, or `status_observed`—to reflect the exact milestone.

Use consistent event names, for example:

~~~text
HTTP_REQUEST_STARTED
HTTP_RESPONSE_STATUS_DECIDED
HTTP_REQUEST_COMPLETED
HTTP_REQUEST_ABORTED
~~~

You do not need to log all four events for every request. Many systems only need a single request-completed log plus tracing/metrics. Do not multiply log volume unnecessarily to represent lifecycle stages that other telemetry already covers.

### Duration: do not use wall-clock time to measure elapsed time

Use:

~~~java
// Java 17 snippet.
long startNanos = System.nanoTime();
try {
    handleRequest();
} finally {
    long elapsedMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startNanos);
    // Log elapsedMs using the configured logger/format.
}
~~~

This is a snippet; `handleRequest()` represents part of a real application. `System.nanoTime` is the right source for measuring **elapsed duration** within the same JVM; do not use it as an absolute timestamp in logs. Event timestamps should come from an appropriate `Instant`/clock. If you need accurate p95/p99 at very low latencies, use microseconds or finer-grained histogram buckets.

## 7. Standalone Java 17 example: logging method with JUL and sending test HTTP requests

This example uses JDK 17 and includes:

- `HttpServer` (`jdk.httpserver` module) accepting GET and POST.
- `HttpExchange.getRequestMethod()` reading the actual HTTP request method.
- JUL `java.util.logging.Logger` logging `method`, `route`, and `status_decided`.
- `HttpClient` sequentially sending two requests to **127.0.0.1** on an OS-assigned ephemeral port.
- A JUL handler printing one line per event; no timestamps or dynamic port numbers are included so the output is deterministic.
- The example **does not log headers, queries, request bodies, or credentials**.

**File: RequestMethodLoggingDemo.java**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class RequestMethodLoggingDemo {
    private static final Logger ACCESS =
            Logger.getLogger("example.web.access");

    private static final Set<String> KNOWN = Set.of(
            "GET", "POST", "PUT", "PATCH", "DELETE",
            "HEAD", "OPTIONS", "TRACE", "CONNECT");

    private static String bucket(String raw) {
        return KNOWN.contains(raw) ? raw : "OTHER";
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        try {
            String rawMethod = exchange.getRequestMethod();
            String method = bucket(rawMethod);

            int status;
            String reply;
            if ("GET".equals(rawMethod)) {
                status = 200;
                reply = "order-list";
            } else if ("POST".equals(rawMethod)) {
                status = 201;
                reply = "created";
            } else if (KNOWN.contains(rawMethod)) {
                status = 405;
                reply = "method-not-allowed";
                exchange.getResponseHeaders()
                        .set("Allow", "GET, POST");
            } else {
                status = 501;
                reply = "not-implemented";
            }

            // Drain the entire request body, but do NOT log the payload.
            exchange.getRequestBody()
                    .transferTo(OutputStream.nullOutputStream());

            // Log the decision before sending the response:
            // status_decided is NOT proof that the client received it.
            ACCESS.info("request method=" + method
                    + " route=/orders status_decided=" + status);

            byte[] bytes = reply.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream body = exchange.getResponseBody()) {
                body.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        // Minimal JUL sink for reproducible output.
        Handler output = new Handler() {
            {
                setLevel(Level.INFO);
            }

            @Override
            public synchronized void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush(); // Do not close System.out.
            }
        };
        ACCESS.setUseParentHandlers(false);
        ACCESS.setLevel(Level.INFO);
        ACCESS.addHandler(output);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/orders",
                RequestMethodLoggingDemo::handle);
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/orders");
            HttpClient client = HttpClient.newHttpClient();

            for (String method : List.of("GET", "POST")) {
                HttpRequest.Builder builder =
                        HttpRequest.newBuilder(uri);

                HttpRequest request = "POST".equals(method)
                        ? builder.POST(
                                HttpRequest.BodyPublishers
                                        .ofString("{}")).build()
                        : builder.GET().build();

                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));

                ACCESS.info("client method=" + method
                        + " status=" + response.statusCode()
                        + " body=" + response.body());
            }
        } finally {
            server.stop(0);
            ACCESS.removeHandler(output);
            output.flush();
            output.close();
        }
    }
}
~~~

**Compile and run from the directory containing the file** using JDK 17 or later:

~~~bash
javac --add-modules jdk.httpserver -encoding UTF-8 RequestMethodLoggingDemo.java
java --add-modules jdk.httpserver RequestMethodLoggingDemo
~~~

**Expected stdout, on a machine allowing loopback sockets:**

~~~text
request method=GET route=/orders status_decided=200
client method=GET status=200 body=order-list
request method=POST route=/orders status_decided=201
client method=POST status=201 body=created
~~~

### Why is the output order deterministic?

The `for` loop sends GET and then POST using `HttpClient.send` (synchronous). Within each request, the server handler logs `status_decided` **before** sending response headers and body; the client only logs its `client` line after `HttpClient` receives the response. Therefore, both GET events appear before both POST events, independent of the ephemeral port number. The handler prints the message directly without adding dynamic timestamps or thread names.

### Why use status_decided?

The actual response can still fail between the moment the server chooses 200 and the moment the client receives the full body. In this demo, the goal is to observe method/routing with deterministic output, so `status_decided` accurately reflects that milestone. In production systems, a summary access log should typically be recorded at the container/gateway layer after the request completes, with an appropriate outcome for failed/aborted requests.

### Technical notes

- `KNOWN` is only the set of methods used in this example for classification; real systems may support extension methods or other policies. Do not use this list as a firewall.
- `bucket()` keeps log labels low-cardinality; the server still uses `rawMethod` for dispatching and distinguishing 405/501.
- The route `/orders` in the event is a **server-defined literal**, not the request URI which could contain queries or personal data.
- The code uses `localhost` to avoid making requests to the Internet or external services. Port `0` lets the OS pick an available port, and that port is not written to stdout.
- The JUL handler here is a learning aid; production appenders must handle formatting, concurrent logging, I/O errors, and framework-managed shutdown.
- The program drains the entire request body for proper connection handling while intentionally not logging body contents. Production services must also enforce input size limits and timeouts to prevent clients from holding connections indefinitely.
- `Content-Type` is set explicitly; the example responses have non-empty bodies. For `HEAD`/`204`/`304`, follow the specific rules regarding response content.

**Limitations:** This is a demo server, not a production replacement for Tomcat, Jetty, Undertow, or Spring Boot. Do not deploy this example code as a public endpoint or claim it provides request size limits, DoS protection, TLS, authentication, tracing, or graceful shutdown.

## 8. Jakarta Servlet Filter: logging methods across multiple routes

A Filter can observe a request before invoking the handler and log after `FilterChain` finishes. Below is a structurally complete snippet for a Jakarta Servlet application, though it **requires the Jakarta Servlet API and a compatible container**; it does not run standalone with `javac` without dependencies.

**File: RequestMethodLogFilter.java**

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

public final class RequestMethodLogFilter implements Filter {
    private static final Logger LOG =
            Logger.getLogger(RequestMethodLogFilter.class.getName());

    private static String methodLabel(String raw) {
        return switch (raw) {
            case "GET", "POST", "PUT", "PATCH", "DELETE",
                 "HEAD", "OPTIONS", "TRACE", "CONNECT" -> raw;
            default -> "OTHER";
        };
    }

    @Override
    public void doFilter(ServletRequest request,
                         ServletResponse response,
                         FilterChain chain)
            throws IOException, ServletException {

        if (!(request instanceof HttpServletRequest http)
                || !(response instanceof HttpServletResponse res)) {
            chain.doFilter(request, response);
            return;
        }

        long started = System.nanoTime();
        boolean returnedNormally = false;

        try {
            chain.doFilter(request, response);
            returnedNormally = true;
        } finally {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            String statusObserved =
                    http.isAsyncStarted() ? "ASYNC_PENDING"
                    : returnedNormally
                        ? Integer.toString(res.getStatus())
                        : "UNRESOLVED";

            LOG.info(() -> "http_filter"
                    + " method=" + methodLabel(http.getMethod())
                    + " status_observed=" + statusObserved
                    + " elapsed_ms=" + elapsedMs);
        }
    }
}
~~~

**Explaining the filter's limitations:**

1. The filter must be **registered** via `web.xml`, `@WebFilter`, or framework configuration. Having the class file alone does not make the filter run.
2. `request.getMethod()` retrieves the method from the Servlet request, not from a request parameter.
3. `System.nanoTime()` is used for elapsed time, not timestamps. `elapsed_ms` here only covers the **`chain.doFilter` execution for that dispatch**.
4. If the chain throws an exception, the final status may be changed to 500 by the container **after** `finally` runs. To avoid falsely logging `"final 200"`, the example records `UNRESOLVED` when an exception occurs.
5. If the request starts async processing, `chain.doFilter` can return before the response finishes. The example marks `ASYNC_PENDING` and **does not call it request completed**. Production needs an `AsyncListener` or an observation lifecycle hook to log the final outcome.
6. For `FORWARD`, `INCLUDE`, and `ERROR` dispatches, a filter may run multiple times depending on mapping/dispatcher types. Avoid double-counting by designing explicit dispatch/once-per-request handling; do not assume each `Filter.doFilter` invocation is a single network request.
7. The example does not log the raw URI because the route template may not be resolved when the filter runs. If you need the route, obtain it after router matching at a layer with reliable information.
8. For applications using `javax.servlet` prior to Jakarta EE 9, package imports must be changed. Do not mix `javax.servlet` and `jakarta.servlet` in the same codebase if the server does not support it.

In Spring MVC, another option is `HandlerInterceptor` or framework-provided observation/metering. An interceptor sees the handler mapping, but requests can be rejected **before** the interceptor runs. Therefore, the observation point must match the goal: access logs at the gateway/container to see all traffic, and filters/interceptors in the application to enrich with route, trace, and business context.

## 9. Spring MVC: route template and method

Suppose a Spring Boot application has a controller:

~~~java
// Snippet requires Spring Web MVC.
@RestController
@RequestMapping("/orders")
class OrderController {
    @GetMapping("/{id}")
    ResponseEntity<String> find(@PathVariable String id) {
        return ResponseEntity.ok("found");
    }

    @PostMapping
    ResponseEntity<String> create() {
        return ResponseEntity.status(201).body("created");
    }
}
~~~

The same `/orders` path can serve `POST`, while `/orders/{id}` serves `GET`. Logging by **method + route template** groups traffic accurately instead of relying on literal paths.

In Spring MVC, the matched route template can be retrieved from the request attribute `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE`:

~~~java
// Spring MVC snippet, after HandlerMapping has resolved the route.
Object value = request.getAttribute(
        org.springframework.web.servlet.HandlerMapping
                .BEST_MATCHING_PATTERN_ATTRIBUTE);
String route = value instanceof String template
        ? template
        : "UNMAPPED";
~~~

This snippet does not run standalone; `request` is an `HttpServletRequest` within a Spring MVC context. It must run at the **right time**: a `Filter` running before `HandlerMapping` typically does not have this attribute yet. An interceptor or lifecycle hook after route matching can observe the route, while also accounting for async and exceptions.

### Do not log raw URLs blindly

Compare:

~~~text
method=GET path=/customers/12345?email=user@example.com&token=secret
method=GET route=/customers/{id}
~~~

The first line contains personal identifiers and a query that may hold secrets; the second still measures the endpoint without exposing payloads. If you must retain the request target for investigation, use allowlisting/redaction, length limits, control-character escaping, access controls, and appropriate retention.

**A route template alone is not enough to trace a specific request.** Combine `request_id`/`trace_id` and error category; do not turn user IDs or order IDs into metric labels if their cardinality can grow unbounded.

### Built-in container/gateway logging

Tomcat, Jetty, reverse proxies, and load balancers often have their own access logs, emitted even when a Java controller is never invoked. An application should designate a **canonical access log** source and trace correlation strategy to avoid counting a single request two or three times when gateway, container, and filter all log the same thing.

If you need separate logs at each hop, include a field such as `observer=api-gateway`, `observer=servlet-container`, or `observer=service` to identify which layer observed each line. Log line count does not equal unique business request count.

## 10. Request method override: what the client says vs. what the server processes

Some stacks support "method override" for HTML form or legacy client compatibility—for example, a `POST` with a `_method=DELETE` parameter or an `X-HTTP-Method-Override` header interpreted by **a specially configured filter**.

Distinguish between:

- **Wire/original method:** the method received by the outer HTTP parser, e.g., `POST`.
- **Effective method:** the method used by the framework for routing after a valid override step, e.g., `DELETE`.
- **Client-declared override:** parameter/header values that may not be trusted or executed.

Illustrative example:

~~~text
wire_method=POST
effective_method=DELETE
route=/orders/{id}
status=204
override_applied=true
~~~

This is a simulated event in a system with override enabled; **not every Java server does this automatically**. Do not log `"DELETE"` merely because the client sent an arbitrary header while the server actually processed `POST`.

### Logging choices when override is enabled

- An outer gateway/access log may record the wire method.
- Application logging after the override filter may see the effective method depending on filter/wrapper ordering.
- During security investigations, both fields are sometimes needed, but they must be produced by **trusted observation layers**, not self-reported client labels.
- Authorization, CSRF, and idempotency must rely on the actual effective routing semantics, not on fields formatted for logging.

Logging the method's source clearly explains why a request looks different at the gateway versus the Spring handler. Do not compare two fields from different hops and declare tampering when a valid override filter sits in between.

## 11. Special cases to distinguish in logs

### 11.1. HEAD

`HEAD` semantically retrieves the metadata corresponding to `GET` without sending response content. Some frameworks handle `HEAD` automatically via the `GET` route; others define a dedicated handler.

- When a client sends `HEAD`, **the method in the access log should still be `HEAD`**.
- Do not add response body size as if it were `GET` when the body is actually suppressed.
- `HEAD` may return status/headers similar to `GET` per HTTP Semantics; do not assume the backend processed a `GET` just because they share a handler.
- Check body suppression at the gateway/container if measuring bytes sent.

### 11.2. OPTIONS and CORS preflight

Browsers may send an `OPTIONS` preflight before an actual cross-origin request. A sequence might look like:

~~~text
OPTIONS /orders 204  # preflight per server configuration
POST    /orders 201  # actual request
~~~

An `OPTIONS` preflight **does not by itself prove** the browser subsequently sent the `POST`. CORS middleware, a gateway, or a container may respond to preflight without reaching the controller. If you only count requests in application controllers, dashboards may miss this `OPTIONS` traffic.

When measuring error rates or latency, you can separate preflight from actual requests; however, do not exclude `OPTIONS` from all security logging if analyzing attacks or endpoint scanning. Depending on your needs, preflight can be tracked separately in access metrics.

### 11.3. TRACE

The RFC defines `TRACE` for HTTP message loop-back. Because the response can expose sensitive headers or data, many deployments disable `TRACE`. Seeing `TRACE` in access logs may indicate a probe worth reviewing, though it is not automatically a successful exploit.

Do not log sensitive request headers just because `TRACE` appeared. Verify server/gateway configuration and per-route method policies.

### 11.4. CONNECT

`CONNECT` is commonly used by HTTP proxies to establish tunnels; typical REST applications usually do not accept it. A proxy may handle `CONNECT` before the Servlet layer, so proxy-layer access logs may contain `CONNECT` entries that the backend application never sees.

Do not infer from the absence of `CONNECT` in backend logs that the edge system never received that method.

### 11.5. Unknown/extension methods

HTTP allows extension methods. A request with an unknown method may be blocked early by the server or fall through to a default handler. If you use a hardcoded enum, keep these separate:
- **Actual method value** during request processing.
- **Method bucket** for log aggregation/metrics, such as `OTHER`.
- **Server policy** for unsupported methods, returning 405/501 as appropriate.

Do not write a fallback like `"OTHER -> GET"` to continue processing, as that changes request semantics and introduces authorization vulnerabilities.

## 12. Security and privacy when logging methods

A `GET` or `POST` method token by itself rarely contains personal data. However, **accompanying fields** can carry sensitive information or create log-forging risks:

- URLs with query strings containing emails, tokens, API keys, or session identifiers.
- `Authorization`, `Cookie`, `Set-Cookie` headers, request bodies, or form data.
- `User-Agent`, `Referer`, or `X-Forwarded-For` containing client-supplied input.
- Exception messages that may include raw requests or payloads.
- MDC `request_id` or `user_id` injected from untrusted sources.
- Path segments containing account IDs, emails, or identifying business data.

**Rule:** log method, route template, status, duration, and controlled IDs; do not log entire requests "for debugging convenience" by default. Events requiring investigation can include additional fields in an access-controlled stream with an appropriate retention period.

### Log injection

If an appender writes raw text from paths or headers, CR/LF or control characters can break log line boundaries. The raw method also comes from the request parser; for unknown methods, always length-limit and escape before putting them into text fields or metrics. Use a battle-tested JSON encoder when structured logging is needed.

**Placeholders are not sanitizers:** SLF4J's `log.info("method={}", rawMethod)` formats parameters but does not automatically escape CR/LF when the final layout is plain text. For canonical methods from an allowlist, risk is low; for other untrusted values, apply format-appropriate neutralization.

### CSRF and authorization cannot be inferred from the method alone

`GET` should follow safe semantics, but a `GET` route that deletes data is a design bug. `POST` does not imply by default that the client is authorized to create a resource. Authorization, CSRF, CORS, and rate-limiting controls must be enforced by server policy, not inferred from access logs.

Do not treat a method log as "proof" that a state change was committed. A `POST` request can fail after the server decides the status, or client retries can produce identical events. For durable business events, use proper transaction/outbox/audit mechanisms.

## 13. Method in metrics: cardinality and grouping

A useful metric set might look like:

~~~text
http_server_requests_total{method="GET",route="/orders/{id}",status_class="2xx"}
http_server_requests_total{method="POST",route="/orders",status_class="2xx"}
http_server_requests_total{method="OTHER",route="UNMAPPED",status_class="4xx"}
~~~

This is an **illustrative label model**; exact metric names and emission depend on OpenTelemetry/Micrometer/Prometheus or your monitoring stack. Label values are quoted.

Labels should come from a bounded set:

| Label | Why it is useful | Risk if unbounded |
| --- | --- | --- |
| method | Distinguishes HTTP request types | Extension methods create arbitrary labels |
| route | Shows load/errors per endpoint | Raw paths with IDs create millions of time series |
| status or status_class | Analyzes 2xx, 4xx, 5xx | Should use bounded numeric codes or status classes |
| service | Separates services | Dynamic request-derived names are hard to control |
| environment | Dev/staging/prod | Must come from trusted deployment config |
| outcome/error_type | Analyzes failures | Random exception messages cause high cardinality |

Do not use `user_id`, `order_id`, raw URLs, emails, or `trace_id` as high-cardinality Prometheus labels. Store those in logs or traces when needed, with proper access controls and retention, rather than turning them into time-series labels.

### Error rate by method

For example, to calculate the 5xx error rate of `POST /orders`:

~~~text
5xx error rate =
  number of POST /orders requests with 5xx status
  / total POST /orders requests in the same time window
~~~

The denominator must be **requests observed at the same layer**—do not take gateway `POST` logs as the denominator and controller `POST` errors as the numerator without adjustment. For `OPTIONS` preflight, `HEAD`, retries, and method overrides, define the scope clearly to avoid misleading dashboards.

## 14. Latency and observation points in multi-tier architectures

In a system with a gateway, load balancer, and Java service:

~~~text
Client
  │
  ▼
API Gateway (method on the wire, all edge requests)
  │
  ▼
Servlet Filter / Security / CORS (method observed at app entry)
  │
  ▼
Spring HandlerMapping (route template, effective method)
  │
  ▼
Controller → Service → DB
  │
  ▼
Response / exception mapping / async completion
  │
  ▼
Gateway response to client
~~~

**The same request** can produce multiple logs:

~~~text
observer=gateway method=POST route=/orders status=502 duration_ms=310
observer=app method=POST route=/orders status=201 duration_ms=280
~~~

These two simulated lines are not necessarily contradictory: the application may have chosen or sent a response, while the gateway hit a connection error or timeout and returned 502 to the client. Do not overwrite the gateway status with the app status and declare the request successful.

### Observation rules

1. Name the observer clearly: `gateway`, `servlet`, `application`, `client`.
2. Distinguish `status_decided`, `status_observed`, and `status_sent`/`received` where needed.
3. Use trace/request IDs to correlate hops, but do not treat a trace ID as authentication.
4. Use the same route template and method bucket standards at each hop for comparison, while preserving wire/effective semantics when overrides exist.
5. If logs are already emitted at the gateway, decide whether the app still needs its own log with the same fields or only business exception events.
6. Do not infer business ordering solely from log line order across nodes; clock skew, buffering, and async logging can make display time differ from occurrence time.

## 15. Logging methods with SLF4J/Logback or Log4j 2

In Java web code using SLF4J:

~~~java
// Snippet requires SLF4J and a compatible logging backend.
accessLog.info(
        "http_request method={} route={} status={} duration_ms={}",
        methodBucket, routeTemplate, status, durationMs);
~~~

Placeholders avoid string formatting when the level is disabled, but **Java arguments are still evaluated before the call**. If route resolution or serialization is expensive, compute fields lazily when needed and avoid any I/O solely for `DEBUG` logging.

With Logback, you can use `ConsoleAppender` with a `PatternLayout` or a JSON encoder. In containers, consider structured JSON to stdout so collectors/backends can index `method`/`route`/`status` as fields without regex:

~~~json
{"event":"HTTP_REQUEST_COMPLETED","method":"GET","route":"/orders/{id}","status":200,"duration_ms":12}
~~~

This is an illustrative JSON line; Logback/Log4j 2 does not produce this exact structure automatically just by using `ConsoleAppender`. You must configure the corresponding encoder/layout, schema, and proper escaping for all values.

### Avoiding log storms

- Do not emit three access logs for the same request at the same layer unless explicitly required by design.
- Prefer a single summary event and metrics for high-frequency successful traffic.
- For `DEBUG` body/header logging, enable it only with a narrow target, time limit, and safe data rules.
- Use sampling for events that can be sampled; do not blindly drop security audit or required business events.
- Async appenders reduce I/O blocking under normal load but introduce queues, overflow, drop/block behavior, and shutdown flush concerns. They do not guarantee durable storage.
- Keep `method` and `route` as stable fields; do not serialize the full `HttpServletRequest` or headers on every request.

## 16. Status and errors during servlet dispatch

Pay special attention to the following cases:

| Scenario | If logged too early | How to handle |
| --- | --- | --- |
| Synchronous successful request | Status may be logged before response is sent | Log at the end of a verifiable observation layer |
| Controller throws exception | Response still shows default 200 | Log `UNRESOLVED` or measure after exception resolver/container |
| Spring Security rejects | Controller does not run | Measure at gateway or a filter placed before security if needed |
| Servlet async / `DeferredResult` | `chain.doFilter` returns before response | Log `ASYNC_PENDING`; use `AsyncListener`/observation completion for final status |
| `ERROR` dispatch | One request has multiple dispatches | Control dispatcher types and deduplicate |
| `Forward`/`include` | Multiple handlers may execute | Log source/dispatch type or only the canonical request |
| Client disconnect | App may choose 200 but client never receives it | Log aborted/IO error at the observation layer |
| Gateway returns timeout | App status and gateway status differ | Distinguish observers; do not overwrite |
| Exception after commit | Cannot change an already-sent status | Log response-committed state and appropriate outcome |

In a web filter, a response wrapper or status tracker can be used to capture the final status and bytes, but its lifecycle must be tested. If the application supports streaming/SSE, requests can stay open for a long time; a filter logging only after the chain completes is not enough to describe the stream lifecycle.

## 17. Testing correctness when logging request methods

A test suite should verify method handling, routing, status, and privacy.

| Test | Behavior to verify |
| --- | --- |
| `GET /orders` | Logs `method=GET`, correct route, status 200 |
| `POST /orders` | Logs `method=POST`, status 201, does not log body |
| `PUT` or `DELETE` on GET/POST-only route | 405 with `Allow` header if server recognizes the method |
| Unsupported method | 501 if server does not recognize/implement it per design |
| `HEAD` | Logs `HEAD`, does not confuse response body size with `GET` |
| `OPTIONS` preflight | Seen accurately at gateway/CORS layer; not counted as `POST` |
| `GET` with query containing token | Logs route template, does not log token |
| URL with dynamic ID | Route label excludes ID to avoid high cardinality |
| Lowercase or unknown method | Not auto-uppercased to alter semantics; labeled `OTHER` in metrics |
| Method override enabled | Distinguishes `wire_method`/`effective_method` per filter |
| Authorization denied | Emits event at chosen observation layer, does not leak credentials |
| Controller throws exception | Does not report initial status as final status |
| Async completion | Single canonical completion event and properly scoped latency |
| `ERROR`/forward dispatch | Does not unintentionally double-count requests |
| Client disconnect | Appropriate outcome; does not claim client received success |
| Multiple threads | Does not mix `request_id`/MDC across requests |
| Collector JSON parsing | `method`/`route`/`status` have correct types; message does not split into extra records |

### Unit tests

Test `methodBucket` independently of the HTTP server: `GET -> GET`, `POST -> POST`, `PATCH -> PATCH`, `"get" -> OTHER`, custom method `-> OTHER`. This tests **label classification**, not protocol parsing or authorization.

### Integration tests

For Servlet/Spring applications, send real HTTP requests to a test server and inspect appender/collector output. Tests must run through the same filter/security/CORS/exception-handling chain that will be deployed. Mocking `HttpServletRequest.getMethod()` in a unit test does not prove that an edge proxy or method override works in practice.

### Counting requests

If gateway, container, and application all emit logs, distinguish requests by `observer` to avoid summing log lines as actual HTTP requests. A request may be retried by a client and legitimately create multiple requests; do not blindly deduplicate by `method+path`, because two distinct requests can share the same method and path.

## 18. Common mistakes and how to fix them

**Mistake 1 – Logging method from `request.getParameter("method")`.**  
That value is a query/form parameter, not the HTTP method. Use `getMethod()` on the request API or the method determined by the gateway/server.

**Mistake 2 – Logging only inside controllers.**  
401/403/404/405 requests or CORS preflights may be handled before reaching a controller. For full access coverage, use the appropriate gateway/container/filter/observation hook.

**Mistake 3 – Using raw paths as the route in metrics.**  
`/clients/1` and `/clients/2` create separate time series. Use route templates like `/clients/{id}`, with `UNMAPPED` when no route matches.

**Mistake 4 – Reporting `status=200` before the response completes.**  
That may only be the default or intended status. Clearly log `status_decided` or measure after completion; handle exceptions, client disconnects, and async.

**Mistake 5 – Assuming `GET` is always safe because the RFC calls it safe.**  
"Safe" is a semantic requirement the application must uphold; a `GET` route that mutates state is a design bug. Logging cannot fix that bug.

**Mistake 6 – Assuming `POST` can never be idempotent, or `PUT`/`DELETE` only write one log.**  
`POST` can be made idempotent with dedicated mechanisms; `PUT`/`DELETE` can be sent multiple times and generate multiple access events.

**Mistake 7 – Merging `OPTIONS` into `POST`.**  
Preflight is an independent `OPTIONS` request that may be handled at the edge. Do not assume an actual request always follows a preflight.

**Mistake 8 – Reading `X-HTTP-Method-Override` without confirming it was applied.**  
An arbitrary header is not the effective method unless a corresponding filter/route policy applies it. Distinguish the raw header from the method actually used by the server.

**Mistake 9 – Not bounding unknown methods in metric labels.**  
Extension methods can cause high cardinality. Bucket them as `OTHER` and monitor unusual requests through a controlled security channel.

**Mistake 10 – Logging the entire `HttpServletRequest`, headers, or payload.**  
This can expose `Authorization`, `Cookie`, URL queries, personal data, and enable log injection; use a field allowlist.

**Mistake 11 – Logging simultaneously at multiple layers without an `observer` field.**  
This increases cost and skews dashboards. Define a canonical access log and the purpose of any supplementary logs.

**Mistake 12 – Using wall-clock time to measure request duration.**  
`System.currentTimeMillis` can jump when the system clock adjusts. Use `System.nanoTime` to measure elapsed time within the JVM.

## 19. Checklist for Java Web projects

1. Identify the layer to log at: gateway, web server, Servlet filter, Spring interceptor, or business handler.
2. Clarify whether the `method` field is the wire or effective method, especially when proxies or method overrides exist.
3. Use the right HTTP request API: `HttpServletRequest.getMethod`, `HttpExchange.getRequestMethod`, or the reactive framework's API.
4. Define a finite set of method buckets; keep the original method for routing and authorization logic.
5. Log route templates rather than raw URLs with IDs/queries.
6. Log status at the exact milestone using meaningful field names (`decided`, `observed`, `completed`).
7. Measure duration with a monotonic clock and proper scope; do not subtract timestamps from different servers to infer latency.
8. Handle CORS `OPTIONS`, `HEAD`, async/error dispatches, and client disconnects when full access coverage is required.
9. Restrict data: never log tokens, cookies, raw bodies, or sensitive queries; escape/encode untrusted fields.
10. Include controlled `request_id`/`trace_id`, and clear MDC when thread pools reuse threads.
11. Test concurrency, handler errors, forwards/dispatches, retries, and multiple observers to avoid miscounting.
12. Test on the actual runtime; verify access logs end-to-end from source to collector and dashboard.
13. Configure retention and access controls for access logs, since request metadata can still contribute to personal identification.
14. If enabling detailed `DEBUG` logging during an incident, limit its duration, log rate, and logger scope, then revert to normal config.

## 20. Practice exercises

### Exercise 1 – Add a disallowed method

Run `RequestMethodLoggingDemo.java`, then add an HTTP `PUT` request to `/orders` in a test environment. Predict that the server returns `405` and `Allow: GET, POST`. Verify that the log shows `method=PUT` and `status_decided=405`, with no message confirming an order was created.

### Exercise 2 – Distinguish unknown methods

Unit test the `bucket` function with `GET`, `get`, `PATCH`, and an extension token like `PROPFIND`. Explain why the `OTHER` metric label is appropriate, yet **`OTHER` must never be used as an authorization result** for all requests.

### Exercise 3 – Servlet Filter and exceptions

In a test Jakarta Servlet app, use the filter from Section 8. Create a route that throws an exception and inspect the `status_observed=UNRESOLVED` log on the initial dispatch. Design a way to observe the final status after error handling instead of guessing `500` inside `finally` before the outcome is known.

### Exercise 4 – CORS and HEAD

In a test web app, send `OPTIONS` preflight, `HEAD`, and `GET` to a matching route. Identify which layer sees each request, how request counts are calculated, and why `HEAD` must not return response content like `GET`.

### Exercise 5 – Privacy and metrics

A team uses a metric label `raw_path=/orders/123?email=...` and stores the `Authorization` header for diagnostics. Design a replacement schema with `method`, route template, `status_class`, `duration_ms`, `request_id`, and `error_category`. Explain how this reduces cardinality and avoids storing tokens.

### Exercise 6 – End-to-end with a reverse proxy

Suppose a gateway logs `wire_method=POST` while the application has a method-override filter that sees `effective_method=DELETE`. Create simulated log records with `observer`, `route`, `status`, and `trace_id`. Explain when differing methods are valid, how to verify the override was actually applied, and why raw client headers cannot be trusted as the final method.

## 21. Key takeaways

**The request method is a core field of access logging**, but it is only meaningful alongside route, status, duration, and observer source. `GET`/`HEAD`/`OPTIONS`/`TRACE` are defined as safe; safe methods plus `PUT` and `DELETE` have idempotent semantics per the RFC. `POST`/`PATCH` are not idempotent by default. Safe/idempotent **does not mean** no logs are written, no errors occur, or only one record is produced.

In Java Web, read the method from the parsed request API rather than request parameters; distinguish original/wire from effective method when overrides are used. Log the method at the appropriate layer, do not call an incomplete status final, and handle Servlet async, CORS preflight, `HEAD`, 405/501, and gateways properly. For metrics, use method buckets and route templates to control cardinality. For privacy, never log raw URL queries, headers, or bodies containing sensitive data. Test the full logging pipeline from application to collector, not just a single logger call.

### References

- RFC 9110 – HTTP Semantics, request methods, safe/idempotent, 405/501: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 5789 – PATCH Method for HTTP: https://www.rfc-editor.org/rfc/rfc5789
- Oracle Java 17 – HttpExchange.getRequestMethod: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java 17 – HttpServer: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java 17 – HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Jakarta Servlet – HttpServletRequest: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpServletRequest.html
- Spring Framework – Request Mapping: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework – Handler Mapping: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
