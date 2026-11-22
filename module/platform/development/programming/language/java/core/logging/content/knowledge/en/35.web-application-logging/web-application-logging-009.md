# Response Correlation in Java Web Applications

## 1. What Is Response Correlation?

In a web application, **response correlation** is the practice of attaching a request- or trace-scoped identifier to the **HTTP response** so that API callers, browsers, gateways, and operations teams can locate the exact sequence of logs generated while handling that request.

For example, suppose a user reports: "The order creation API returned HTTP 500 at 10:15." If the system relies solely on the timestamp and URL, finding the right log among thousands of concurrent requests is very difficult. If the response includes **X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f** and the logs also contain that `requestId`, the support team can query a single processing flow directly.

~~~text
Client                  Web application              Log backend
  | GET /api/orders/42         |                            |
  |--------------------------->|                            |
  |                            | create requestId = abc-123 |
  |                            | write log with requestId   |
  |                            |--------------------------->|
  |  HTTP 200                  |                            |
  |  X-Request-ID: abc-123     |                            |
  |<---------------------------|                            |
  |                            |                            |
  |      Support queries requestId=abc-123 ---------------->|
~~~

**Key point:** the response does not need to contain stack traces, internal system information, or log contents. It only needs to provide a **safe lookup code** that has been consistently logged on the server and, when needed, propagated across related services.

Key benefits:

- **Customer support:** users provide a request ID instead of sending personal information or screenshots containing sensitive data.
- **Error investigation:** links the HTTP response to logs in the controller, service, repository, gateway, and downstream services.
- **Operations:** searches logs by `requestId`/`traceId`, comparing status, processing time, errors, and business steps.
- **Testing and monitoring:** matches test case responses against log events, proving that an error was actually recorded.

A correlation ID is **not** an authentication token, does not grant access permissions, and does not guarantee that logs exist. If the backend filters/drops logs or the collector has not ingested them yet, logs may still be missing even if the response returns the correct ID.

## 2. Distinguishing requestId, correlationId, traceId, and spanId

These names are related, but they are **not completely equivalent**.

| Name | Role | Common Scope |
| --- | --- | --- |
| **requestId** | Identifies an HTTP request at the API boundary | A single request entering a gateway or one service hop |
| **correlationId** | Links logs/events belonging to the same processing context | Can span multiple services or messages |
| **traceId** | Identifies a distributed trace | Multiple spans across services in the same trace |
| **spanId** | Identifies a unit of work within a trace | A single span, with parent/child relationships |
| **businessId** | Identifies a business entity, such as `orderId` | May appear across multiple requests and timestamps |

A small system may use the same `requestId` as its `correlationId`. In systems that already use OpenTelemetry/Micrometer Tracing, **traceId** is often the key for finding logs in the tracing system. It is not mandatory to create a second identifier if the tracer already meets your needs; however, many APIs still want a **customer-friendly request ID** that is independent of the trace structure.

Example:

~~~text
response:
  X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f

server log:
  requestId=9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f
  traceId=4bf92f3577b34da6a3ce929d0e0e4736
  spanId=00f067aa0ba902b7
  status=200
~~~

`requestId` and `traceId` can be different, but they must be **linked in the logs** when cross-system lookup is required.

According to **W3C Trace Context**, the **traceparent** header has the format `version-trace-id-parent-id-trace-flags`. For version `00`, `trace-id` is 32 hexadecimal characters and `parent-id` is 16 hexadecimal characters; all-zero IDs are invalid. This is the protocol for propagating tracing context between services. It is not synonymous with an application-defined **X-Request-ID** response header.

**Do not hand-craft `traceparent`** by concatenating an improperly formatted UUID; let your instrumentation/tracer comply with the standard. If you want to add `X-Trace-ID` to the response, clearly define the ID source, scope, and information disclosure policy.

## 3. Where to Output the Correlation ID

A typical design uses the same ID across these locations:

1. **HTTP response header:** for example `X-Request-ID`, allowing clients or support to obtain the ID on both successful and error responses.
2. **Server logs:** in a structured `requestId` field or in MDC/ThreadContext for fast lookup.
3. **Error response body:** when the API returns an error, it can include `requestId` alongside the error code and a safe message.
4. **Downstream calls or messages:** propagate correlation/trace context according to policy to connect multiple services.
5. **Tracing/metrics:** logs can be linked to traces; avoid using `requestId` as a metric label due to high cardinality.

Example of a successful HTTP response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f

{"orderId":"order-42","status":"PAID"}
~~~

Example of an error HTTP response with Problem Details JSON:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f

{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "The request could not be completed.",
  "requestId": "9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f"
}
~~~

These examples illustrate the API contract, not mandatory content for every response. **The body only needs to include `requestId` when it adds value for the client and the schema is agreed upon**; adding it to the header is usually simpler because it does not alter the body of successful APIs, file downloads, streams, or bodyless responses such as `204`.

For errors, never return internal exception messages, SQL, tokens, file paths, downstream endpoints, or stack traces to the client. The client needs a **safe error code and `requestId`**, while technical details belong in a properly access-controlled logging system.

## 4. Lifecycle of an ID Across an HTTP Request

The design should establish a **single responsible point** for attaching the ID at a trusted boundary:

~~~text
Request arrives at gateway / application
               |
               v
     Receive or generate requestId
               |
               v
       Attach to request context
               |
               +----> MDC / structured logging
               |
               +----> response header
               |
               v
       Controller / service
               |
               +----> HTTP client / messaging downstream
               |
               v
       Build response (2xx/4xx/5xx)
               |
               v
          Clean up MDC / context
~~~

**Start early:** create/attach the ID before any controller, service, or business logging code runs. Set the response header before the response is committed so that error handling also has a chance to carry the ID.

**Once per request:** avoid having each layer generate a different ID and overwrite the header. If the gateway already issued a standard ID and the system has a policy to trust the gateway, the service can reuse or record that ID; otherwise, generate an internal ID and map them when needed.

**Clean up on time:** clear or restore the thread-local context so that the next request on the same thread pool does not "inherit" an old ID.

**Across multiple hops:** agree on the ID-issuing point and propagation policy. `requestId` can be the edge ID preserved across services, whereas `spanId` changes for each span; do not use `spanId` as the single identifier across all hops.

## 5. Should Client-Sent IDs Be Trusted?

You should not blindly trust **X-Request-ID**, **X-Correlation-ID**, or **traceparent** headers coming from the Internet. A client could intentionally:

- Use a spoofed ID matching another request to confuse logs.
- Send very long strings or control characters causing log injection, parser errors, or excessive storage costs.
- Embed personal data or secrets into the ID, causing it to be logged repeatedly across multiple systems.
- Generate an enormous number of distinct IDs, causing cardinality spikes if used as a metric tag.
- Send invalid trace context or attempt to forge false trace relationships.

Safe options:

1. **Always generate `requestId` yourself at the public edge** using a random UUID or a suitable opaque format. Record the upstream ID separately if genuinely needed and only after validation.
2. **Trust IDs from a trusted reverse proxy/gateway** if infrastructure authenticates the source, **strips Internet-supplied headers at the proxy**, enforces length/character-set limits, and explicitly defines which headers may pass through.
3. If you must accept client-supplied IDs, **validate format, size, character set, duplicate headers, entropy level, or anti-abuse policies**; the ID remains mere metadata and must never be used to grant permissions.
4. For **traceparent**, use a W3C-compliant parser/propagator from your tracing library rather than arbitrarily copying or formatting strings yourself.

Never put emails, account numbers, session tokens, or raw user input into `correlationId`. A random UUID is a convenient example of an identifier, not proof of identity or access rights.

## 6. Standalone Java 17+ Example: Matching Response ID and Logs

This example uses **JDK HttpServer** from the `jdk.httpserver` module, **HttpClient**, and **java.util.logging**. The program starts an HTTP server on `127.0.0.1` with an OS-assigned port, sends a real request to it, and proves that the `X-Request-ID` header **matches the exact ID recorded in the server logs**.

For deterministic test output, the logger is attached to an in-memory `Handler`. Because each run generates a new UUID, the program **does not print a hardcoded UUID value**; instead, it prints boolean match results.

Create **ResponseCorrelationDemo.java**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.io.OutputStream;
import java.util.UUID;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ResponseCorrelationDemo {
    private static final Logger LOG = Logger.getLogger("demo.web");
    private static final List<String> EVENTS = new CopyOnWriteArrayList<>();

    public static void main(String[] args) throws Exception {
        Handler memory = new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    EVENTS.add(record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(memory);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/orders", exchange -> {
            String requestId = UUID.randomUUID().toString();
            exchange.getResponseHeaders().set("X-Request-ID", requestId);

            LOG.info("requestId=" + requestId
                    + " path=" + exchange.getRequestURI().getPath()
                    + " status=200");

            byte[] bytes = "ok".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/orders");

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .GET().build();

            HttpResponse<String> response = HttpClient.newHttpClient()
                    .send(request, HttpResponse.BodyHandlers.ofString());

            String returnedId = response.headers()
                    .firstValue("X-Request-ID").orElseThrow();

            System.out.println("status=" + response.statusCode());
            System.out.println("body=" + response.body());
            System.out.println("validId=" +
                    UUID.fromString(returnedId).toString().equals(returnedId));
            System.out.println("sameIdInLog=" + EVENTS.stream()
                    .anyMatch(e -> e.contains("requestId=" + returnedId)));
            System.out.println("logCount=" + EVENTS.size());
        } finally {
            server.stop(0);
            LOG.removeHandler(memory);
            memory.close();
        }
    }
}
~~~

Compile and run with JDK 17+ with the `jdk.httpserver` module:

~~~bash
javac --add-modules jdk.httpserver ResponseCorrelationDemo.java
java --add-modules jdk.httpserver ResponseCorrelationDemo
~~~

**Deterministic stdout** when the program runs successfully:

~~~text
status=200
body=ok
validId=true
sameIdInLog=true
logCount=1
~~~

Explanation:

- Each request to `/orders` is assigned a separate UUID via `UUID.randomUUID()`.
- The server sets `X-Request-ID` **before** `sendResponseHeaders()`, ensuring the ID is present in the response.
- `LOG.info` records `requestId` and the URL/status context in the same message; an internal `Handler` captures the record.
- The client reads `X-Request-ID`, validates the UUID format, and searches for that exact value in the recorded log message.
- The HTTP server runs on loopback with an OS-assigned port so no port needs to be hardcoded; after verification, the server is stopped and the `Handler` is removed.

**Example limitations:** there is only one HTTP request, a successful response, in-memory logging, and no testing of concurrency, proxies, error dispatches, or async tracing. The `Handler` is only a verification tool, not a production logging system, and does not indicate whether data has been indexed or durably stored. In real applications, use SLF4J + a logging backend, context propagation, and structured logging.

## 7. Spring Boot: OncePerRequestFilter to Attach IDs to Requests and Responses

In a **Spring Boot application using Spring MVC/Servlet (suitable for Spring Boot 3+ or 4+)**, you can use `OncePerRequestFilter` to assign a `requestId`, put it into SLF4J's MDC, set the response header, and clean up the context after the request completes.

Example **RequestIdFilter.java**, requiring compatible Spring Web/Servlet and SLF4J dependencies:

~~~java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Request-ID";
    public static final String ATTRIBUTE = "requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        // Public edge: proactively generate the ID, do not trust arbitrary client headers.
        String requestId = UUID.randomUUID().toString();

        // Shared for error handlers and servlet components.
        request.setAttribute(ATTRIBUTE, requestId);

        // Set early so normal responses and many error paths carry the ID.
        response.setHeader(HEADER, requestId);

        // try-with-resources cleans up the context after the current request.
        try (MDC.MDCCloseable ignored =
                MDC.putCloseable(ATTRIBUTE, requestId)) {
            filterChain.doFilter(request, response);
        }
    }
}
~~~

This is a **complete class but must be placed inside a Spring Boot application**, not a standalone Java program compiled with `javac` without dependencies. Registering the filter with `@Component` may vary depending on project structure; do not register **the same filter twice** via both `@Component` and `FilterRegistrationBean`.

**Key points:**

- `request.setAttribute` allows controllers and error handlers in the same request to access the ID without depending directly on MDC.
- `response.setHeader` should run **before** `filterChain.doFilter`; if set afterward, the response may already be committed and its headers can no longer be modified.
- `MDC.putCloseable` scopes the value and cleans up MDC on exit, even if `filterChain` throws an exception. Since MDC is thread-scoped, proper cleanup prevents leaking IDs to other requests on the thread pool.
- This approach **intentionally ignores client-sent `X-Request-ID`** to prevent spoofing. In environments where a gateway issues IDs, you can replace this with a policy that trusts only gateway-authenticated and validated headers.
- Filter ordering/placement matters. An error occurring in a gateway, proxy, security filter **before this filter**, or a separate error handler may not receive the header if this filter has not run yet.

**Async limitation:** `OncePerRequestFilter` by default does not filter subsequent async dispatches and does not automatically carry `ThreadLocal` MDC across threads. When using Servlet async, `CompletableFuture`, `@Async`, scheduled tasks, or Reactor, you must design propagation explicitly; never claim that simply adding one filter is enough for all asynchronous logs.

## 8. Configuring Logback and Log4j 2 to Include requestId in Logs

Having `requestId` in MDC **does not mean appenders will print that field automatically**. The pattern or JSON encoder must be configured to extract the right key.

### 8.1. Logback pattern

Minimal configuration example in **logback-spring.xml**:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level requestId=%X{requestId:-} %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

When `RequestIdFilter` adds the `requestId` MDC key, every log call on the same thread includes this field via `%X{requestId:-}`. Without a context, that part may be empty according to the pattern; a log event running outside an HTTP request does not necessarily have a `requestId`.

Logback can use a structured JSON encoder instead of a text pattern. With centralized logging, keep **requestId** as a separate field, index it appropriately, and query by exact key rather than free-text search.

### 8.2. Log4j 2 pattern

For a Log4j 2 backend, example **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout
          pattern="%d{ISO8601} %-5p requestId=%X{requestId} %c - %m%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

In Log4j 2, `ThreadContext`/MDC handles per-thread metadata storage; SLF4J MDC integrates with the Log4j 2 backend when the proper binding/provider is present. Do not copy Logback XML syntax or classes into Log4j 2. Verify actual output because logger names, context maps, and patterns can be affected by other configuration settings.

### 8.3. If Already Using Micrometer Tracing

Spring Boot with Micrometer Tracing can add **traceId** and **spanId** to MDC and correlate them in logs, depending on version and configuration. In that case, leverage the existing tracing setup instead of building a competing correlation system. Clearly determine:

- Should the API return **X-Request-ID**, **X-Trace-ID**, or both?
- Does the log structure store the `requestId` ↔ `traceId` mapping?
- Does the ID in the response correspond accurately to the request's **active span**?
- Sampling may prevent a trace from appearing in the tracing backend; logs still need their own retention policy.

Having `traceId` in the logger does not mean the response automatically contains `X-Request-ID`. They are two separate integration paths and both must be tested.

## 9. Consistently Attaching requestId to Error Responses

Many applications expose JSON API errors, for example using Spring `ProblemDetail`. You can retrieve the `requestId` stored via `request.setAttribute()` in the filter and include it in the error body.

The code below is a **Spring Boot MVC fragment** that belongs in an application with `RequestIdFilter` and Spring Web. It illustrates returning a safe body with `requestId` without exposing exception internals:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> unexpected(
            Exception exception,
            HttpServletRequest request) {

        Object requestId = request.getAttribute("requestId");

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setTitle("Internal Server Error");
        problem.setDetail("The request could not be completed.");
        if (requestId != null) {
            problem.setProperty("requestId", requestId.toString());
        }

        // Log the error in one unified location to avoid duplicate logs.
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

**This is not a complete error-handling pattern:** exceptions may map to `400`, `401`, `403`, `404`, or other statuses; not every exception should return `500`. In production, design exception-to-status mapping according to business policy and Spring Security; only use a catch-all handler for unexpected errors when appropriate.

Some errors occur **before the controller**, in a proxy, authentication filter, gateway, or request parsing; `@RestControllerAdvice` does not necessarily handle those errors. Therefore, to ensure every response has an ID, implement and test it **at the appropriate boundary layer**, not just in controller advice.

When logging exceptions, avoid logging the stack trace repeatedly in the controller, interceptor, and error handler. Designate one primary error-logging point; other layers can add context as needed. The `requestId` in the body and header must **match**, and you must not generate a new ID when catching an exception.

## 10. CORS: Can the Frontend Read X-Request-ID?

For a cross-origin frontend, the browser can receive the response, but JavaScript **cannot automatically read all custom response headers**. `X-Request-ID` is not a CORS-safelisted response header, so **Access-Control-Expose-Headers** must be configured to allow the client to access it when permitted.

Example response from an API with valid CORS enabled:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: X-Request-ID
X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f
Content-Type: application/json

{"status":"ok"}
~~~

On the frontend:

~~~javascript
// Illustrative browser fragment.
const response = await fetch("https://api.example.test/orders/42");
const requestId = response.headers.get("X-Request-ID");
console.log("Support request ID:", requestId);
~~~

`Allow-Origin`/credentials configuration must follow its own CORS policy. **Access-Control-Expose-Headers only allows JavaScript to read a header that was already received**; it does not grant API call permissions and does not replace authentication/authorization. For credentialed requests, avoid relying on the `*` wildcard to expose headers because the specification semantics differ.

Non-browser HTTP clients are not governed by browser JavaScript CORS rules, so they can read custom headers directly. However, proxies, CDNs, ingress controllers, or API gateways can still strip or modify headers.

## 11. Correlation with Downstream Responses and Distributed Tracing

In a multi-service system:

~~~text
Client --(requestId=edge-1)--> Gateway
                                  |
                                  v
                               Service A
                                  |
                                  v
                               Service B
                                  |
                                  v
                               Database
                                  |
                                  v
Client <--(X-Request-ID=edge-1)---+
~~~

When Service A calls Service B over HTTP, there are two needs:

- **System-managed `requestId`:** propagate `X-Request-ID` to **trusted internal services** according to policy and log it at each hop. Do not blindly forward this ID to untrusted URLs or third parties if data policy forbids it.
- **Distributed trace context:** use OpenTelemetry/Micrometer or a compatible library to propagate `traceparent` and optionally `tracestate` per the W3C standard. `traceId` generally remains constant across the trace; `spanId` changes per span.

There is no need to generate a new UUID at every service if the goal is to keep the same `correlationId` across the chain. However, **each inbound request** may have its own `requestId`, while a larger business transaction may have a separate business-layer ID. Document the contract clearly to avoid confusing IDs.

When a downstream service returns an error or times out, the upstream service should log with its **local/edge ID** and trace context. If you need to record the downstream's `requestId`, use a separate field (such as `downstreamRequestId`) to avoid overwriting the primary ID that the client will read from the upstream response.

With retries, a single client request can trigger multiple downstream attempts. The correlation ID links them together, but you should have an **attemptId** or separate span to distinguish each attempt. Never assume one ID corresponds to exactly one log record.

## 12. Async, Thread Pools, and Reactive: Why MDC Is Easily Lost

SLF4J's MDC is typically backed by **thread-bound context**; having `requestId` in a controller call does not guarantee that a task on another thread will automatically have that `requestId`. This affects:

- `@Async`, `ExecutorService`, `CompletableFuture`;
- Servlet async dispatches or streaming responses;
- Reactive stacks like Spring WebFlux/Reactor;
- Messaging consumers or scheduled/background jobs;
- Certain concurrency patterns and virtual threads.

Example:

~~~text
HTTP thread: requestId=A
      |
      +--> asynchronous job on worker thread
               |
               +--> MDC requestId is empty if not propagated
~~~

For Servlets, a `OncePerRequestFilter` may not run on async dispatches under default behavior. If async support is required, check dispatcher mappings, `shouldNotFilterAsyncDispatch()` behavior, request attribute storage, and the framework's context propagation mechanisms. Do not simply override one method while ignoring dispatcher types and cleanup, because a single request can execute across multiple threads.

For Reactor/WebFlux, prefer **Reactor Context** or propagation mechanisms supported by Micrometer/Tracing instead of relying on manual `ThreadLocal` across operators. For task runners, if copying the MDC map, you must restore/clear the context on the worker thread after the task finishes; never let request A contaminate request B's logs.

**Rule:** the correlation ID must travel with the **execution context**, not merely stay bound to a single thread for the entire business lifecycle. Testing async paths is mandatory if your system uses them.

## 13. Status Codes and Error Paths to Cover

Do not test only HTTP 200:

| Scenario | Correlation Requirement |
| --- | --- |
| 200/201 success | Header has ID; server logs have the same ID |
| 204 No Content | No body needed; header can still contain ID |
| 400 validation error | Safe error body and header share the same ID if handled in app |
| 401/403 security error | Check filter order; security/gateway may terminate before app |
| 404 routing error | If request reaches app, check which layer handles filter/router |
| 500 from controller/service | Do not generate a new ID in error handler; header and error body match |
| Gateway timeout | Gateway may return response; app may not produce a response |
| Streaming/SSE/file download | Header must be set before response commits |
| Async/background completion | Context must propagate across threads/dispatches; final log still has ID |
| Preflight OPTIONS/CORS | Requires explicit rules to expose header and handle CORS |
| Repeated/retried request | Each request or attempt must have an identifier per contract |

If the server has already written part of the response before failing, it may no longer be able to change headers or status. In that case, logs and metrics must record the server-side error, but do not promise the client will always receive a standard error body.

If the gateway itself returns `502`/`503`/`504`, the response ID may be issued by the **gateway** and will not match a service ID if the service never received the request. This is not always a bug in the application filter; align on the correlation policy at the edge.

## 14. Designing Log Data for Easy Lookup by Response ID

A structured log entry might look like:

~~~json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service": "order-service",
  "requestId": "9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http": {
    "method": "POST",
    "route": "/api/orders/{id}",
    "status": 500
  },
  "errorCode": "ORDER_BACKEND_UNAVAILABLE",
  "durationMs": 241
}
~~~

This is sample data, not a real log record. The `route` field uses a **route template** rather than the full URL with query strings that might contain PII. Each event can add `component`, `eventCode`, and `outcome`, but should avoid logging request bodies or credentials.

In a centralized logging system, prefer querying by structured field:

~~~text
service = "order-service"
AND requestId = "9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f"
~~~

Query syntax depends on the backend (Loki, Elastic, OpenSearch, Cloud Logging, etc.). This is only a logical representation, **not a query that runs as-is on every system**.

One request ID can appear across multiple log events, multiple services, and multiple attempts. Do not assert that "one response must have exactly one log line." Correlate by the same `requestId` and add `traceId`/`spanId` or `attemptId` when needed.

**Cardinality:** `requestId` has high uniqueness. It is well suited as a log field for access-controlled search; it is usually **unsuitable as a metric label/tag** in time-series systems because it can create an enormous number of series.

## 15. Security and Privacy

Because the correlation ID is returned externally, treat it as a **non-sensitive reference code**:

- Use random/opaque IDs; do not embed `userId`, email, secret `orderId`, or session tokens.
- Do not use the ID as a "key" to access logs or download files. Every support tool for viewing logs must still enforce authentication and authorization.
- Do not expose a public endpoint that "looks up any `requestId`" and returns stack traces and PII; this easily creates an insecure direct object reference (IDOR) vulnerability.
- If trusting headers from a gateway, ensure the gateway strips spoofed headers from clients and validates source/trust state.
- Limit header size/character set and sanitize values before logging to prevent log injection.
- Avoid logging raw query strings, `Authorization`, `Cookie`, or HTTP bodies solely for correlation purposes.
- Review retention of request IDs, logs, and traces according to purpose; correlation across multiple datasets can enable identity linking.
- Minimize copies of correlation IDs sent to external vendors when unnecessary.

If an ID is exposed, outsiders must not be able to infer request contents or access log dashboards from it. Security does not come from keeping `requestId` top secret; it comes from real access control and keeping sensitive information out of the ID.

## 16. Designing Integration Tests

A test suite should run against a **real server** (Spring Boot Test, MockMvc with header checks, or an end-to-end HTTP test) and a test appender/collector:

1. Send an HTTP 200 request; verify the response has a properly formatted `X-Request-ID` and the log contains the exact `requestId`.
2. Send multiple sequential and concurrent requests; IDs must be distinct, with no MDC bleed across threads.
3. Send requests with a spoofed, oversized, or invalid-character `X-Request-ID` header; verify regeneration/validation policy.
4. For `400`/`401`/`403`/`404`/`500` errors, verify the header and error body share the same ID **on paths actually handled by the application**.
5. For `204`, file download, and streaming APIs, confirm the header is set before commit.
6. Enable CORS from a valid origin; verify JavaScript can read `X-Request-ID` once exposed, without granting access beyond policy.
7. Through a reverse proxy/gateway, verify headers are not unexpectedly altered or stripped; for gateway-generated errors, confirm the gateway ID behavior.
8. Across async/`Executor`/Reactor paths, verify downstream logs remain linked to the right context with no cross-contamination between requests A and B.
9. Across multiple services, verify `X-Request-ID` alongside `traceId`/`traceparent` and request attempts.
10. If using sampling or async logging, verify minimal investigative signals remain; do not treat dropped logs solely as a response correlation bug.
11. Verify the ID cannot be used as a credential and does not leak PII on lookup.

**Example acceptance matrix:**

| Check | Expectation |
| --- | --- |
| Response header present | `X-Request-ID` present per policy |
| ID format | Opaque, valid, within length limit |
| Corresponding log | Same `requestId`, appropriate `service`/`status` |
| Error body has ID | Matches header if required by contract |
| Two distinct requests | Non-duplicate IDs in test, context cleaned up |
| Different threads | Propagated as designed, no lost/swapped ID |
| Gateway | Defined ID rule when gateway generates errors |
| Lookup | Authorized staff can find the right logs by `requestId` |
| Security | Cannot access logs merely by possessing `requestId` |
| CORS | Frontend allowed to read custom response header |

Do not hardcode a specific UUID as the expected result of a random ID generator. Instead, assert that **the header is non-empty, validly formatted, matches the logs, and is not reused out of scope**.

## 17. Common Issues and Troubleshooting

### Response has ID, but logs do not

Check whether the logging pattern includes `%X{requestId}`, whether MDC was set before `logger.info`, whether the filter matched the request path, whether the request crossed an async thread, and whether the collector is delayed or dropping events. Inspect the raw field in structured logs if available.

### Logs have ID, but response does not

Was the header set before the response was committed? Did an exception, security filter, gateway, or CDN return a response before the application filter ran? Did a proxy strip the header? In browsers, the header may exist on the network but remain unreadable to JavaScript due to a missing `Access-Control-Expose-Headers`.

### Two consecutive requests share the same ID

`ThreadLocal`/MDC may have leaked because it was not removed in `finally`, or the server accidentally stored a static UUID for all requests. Check where the ID is generated, its lifecycle, and context cleanup. Also distinguish cases where a gateway intentionally preserves a `correlationId` across related requests.

### requestId in error body differs from header

Usually caused by the error handler generating a new UUID, the filter running multiple times, or the gateway modifying the response header. Pick a single ID source, store it in a request attribute/context, and reuse it.

### ID present in controller, lost in @Async/CompletableFuture

MDC does not automatically cross worker threads. Use the framework's context propagation utilities, ensure clear/restore at the end of the task, and test under concurrency.

### Using traceId, but trace cannot be found

The trace may have been sampled out, the exporter may have failed, the span may not have finished, or you may be querying the wrong environment. Log correlation may still work if logging policy allows it. Do not equate "having a `traceId`" with "having a stored trace."

### Duplicate logs or too many events returned

The same ID legitimately appears across multiple lines; however, appender additivity, logging the same exception multiple times, or retries can create duplicates. Support queries should filter further by service, time window, route, and attempt.

### Echoing back the exact X-Request-ID sent by the client

This can allow IDs containing PII/malicious strings or spoofed correlation. Establish a clear trust policy and validate/generate at the boundary.

## 18. Implementation Checklist

- [ ] Agree on the response header (e.g., `X-Request-ID`), format, and ID generation point.
- [ ] Distinguish `requestId`, `correlationId`, `traceId`, `spanId`, and business IDs.
- [ ] Keep IDs opaque without PII or secrets; never blindly trust headers from the Internet.
- [ ] Generate/attach the ID early enough, before the response commits.
- [ ] Use the same ID in the response header, logs, and error body if applicable.
- [ ] Ensure patterns/structured encoders include `requestId` and support field-based queries.
- [ ] Clean up MDC in `finally`/`AutoCloseable`; never leak context to another request.
- [ ] Implement proper propagation for async/thread pools/Reactor or Micrometer Tracing.
- [ ] Test `2xx`, `4xx`, `5xx`, security paths, `204`, streaming, and gateway errors.
- [ ] Configure `Access-Control-Expose-Headers` appropriately for cross-origin frontends.
- [ ] Use standard trace context and safe propagation rules for downstream calls.
- [ ] Never return stack traces, secrets, or internal logs in the response.
- [ ] Never use `requestId` as an auth token or high-cardinality metric label.
- [ ] Test multithreading, multi-service hops, retries, proxies, and collector delays.
- [ ] Ensure support teams know how to look up logs by ID while adhering to access control.

**Conclusion:** Response correlation creates a **verifiable link between the code returned to the client and server-side logs**. Issue IDs safely at the edge, set them in headers early, log them consistently via MDC/structured logging, clean up context properly, and propagate them downstream when needed. The response should only carry a useful reference code and never expose internal error details.

## 19. References

- [W3C Trace Context Recommendation](https://www.w3.org/TR/trace-context/): `traceparent`, `tracestate`, `trace-id`, `span-id`, and trace context propagation rules.
- [SLF4J MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html): `put`, `putCloseable`, `remove`, and diagnostic context details.
- [Spring Boot — Tracing and logging correlation](https://docs.spring.io/spring-boot/4.0/reference/actuator/tracing.html): Micrometer Tracing, `traceId`/`spanId` in logs, and correlation configuration.
- [Spring Framework — OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): filter lifecycle, async/error dispatches, and `doFilterInternal`.
- [MDN — Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers): how to allow cross-origin JavaScript to read custom response headers.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): pattern layouts and outputting MDC in logs.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): outputting `ThreadContext`/MDC with `%X`.
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server used in the example.
- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client for reading response headers and verifying results.
