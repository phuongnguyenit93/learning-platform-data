# HTTP Access Logs in Java Web Applications

## 1. Concept and Objectives

An **HTTP access log** is a metadata record of an HTTP request at a processing point (reverse proxy, gateway, web server/servlet container, or application). Basic information typically includes timestamp, method, endpoint, status code, processing duration, and correlation ID. It helps answer: “Which request arrived, where was it processed, did it succeed, how long did it take, and which error is it associated with?”

Example of a **data-minimized access event**:

```json
{
  "event": "http_access",
  "timestamp": "2026-11-10T03:15:30Z",
  "service": "orders-api",
  "method": "GET",
  "route": "/orders/{id}",
  "status": 200,
  "duration_ms": 13,
  "request_id": "req_7c9"
}
```

This is illustrative data, not actual measurements. The `route` field is an application-controlled **route template**, not a raw URL containing user IDs, query strings, or tokens.

Lesson scope within **Logging in Java Web Applications**:
- Distinguish access logs at the edge, web container, and application layers, and understand why events may be duplicated or lost.
- Choose a schema containing method, route, status, duration, timestamp, and request ID; consider bytes/IP according to policy.
- Configure Apache Tomcat `AccessLogValve` and Spring Boot using embedded Tomcat/Jetty/Undertow.
- Write a standalone Java 17+ example that receives real requests using `HttpServer` and emits access events safely.
- Handle error scenarios, asynchronous requests, reverse proxies, latency measurement, data minimization, storage, testing, and operations.

## 2. How Access Logs Differ from Application Logs and Tracing

| Source | Example | Used to Answer |
| --- | --- | --- |
| HTTP access log | `GET /orders/{id} 200 13ms` | Which endpoint, what status, what latency? |
| Application log | `order_validation_failed code=INVALID_STATE` | What business logic occurred? |
| Error log | Exception and stack trace | Why did an operation fail? |
| Distributed trace | Span from gateway to database | How is time distributed across services/operations? |
| Metrics | Request duration histogram, RPS, 5xx rate | Are long-term SLOs/alerts being met? |

An API can emit access logs, write application logs, and create trace spans simultaneously. They **complement one another** and should not be replaced by printing the entire request body for easier debugging.

### Three Layers Generating Access Logs

```text
Client
  |
  v
Load balancer / API gateway      -> access log A
  |
  v
Web server / Servlet container   -> access log B
  |
  v
Servlet Filter / Controller      -> access log C
  |
  v
Service -> database              -> application logs + traces
  |
  v
HTTP response
```

Key differences:
- The gateway may reject a request due to auth, rate limiting, or no available upstream; in that case only log A exists.
- The container may reject an invalid URL or certain errors before reaching the application filter; B may see it while C does not.
- The application filter knows the business route/context, but may miss errors occurring before the filter or asynchronous processing after the filter returns.
- If A, B, and C all log, **a single request produces multiple events**. Dashboards must not sum them as three separate requests.

Define a **primary measurement point** for RPS, error rate, and latency. Use a field such as `layer=gateway`/`layer=container` when multiple layers need to be retained for investigation.

## 3. Designing an HTTP Access Log Schema

| Field | Illustrative Value | Notes |
| --- | --- | --- |
| `timestamp` | UTC ISO 8601 | Wall clock with timezone for event correlation |
| `service`/`instance` | `orders-api` | Distinguishes sources when scaling horizontally |
| `method` | GET, POST | Do not put unvalidated raw input into text logs |
| `route` | `/orders/{id}` | Prefer route templates to avoid PII and high cardinality |
| `status` | 200, 404, 500 | Response code at the **logging point**, never default to 200 |
| `duration_ms` | 13 | Unit and start/end points must be clear |
| `request_id` | `req_7c9` | Generated/validated at ingress or server; must not contain secrets |
| `trace_id` | Trace span identifier string | Only include per tracing standard and policy |
| `response_bytes` | 8192 | Unit/definition may vary by server, compression, and headers |
| `client_ip` | Client/proxy IP | Potentially sensitive data; forwarded headers must be trusted |
| `user_agent`, `referer` | Client-sent headers | May contain PII, tokens, CR/LF; do not enable by default |
| `error_code` | Internal enum | Useful if business 4xx/5xx errors need to be separated |

A minimal schema typically keeps **method + route template + status + duration + request/trace ID** and a timestamp. Do not turn this table into a mandate to collect every field; the organization must define purpose, retention, read permissions, sampling, and ownership for each field.

### What Do Status Codes Mean?

- **2xx:** the request succeeded according to the HTTP contract; not necessarily that all related backend work has completed.
- **3xx:** redirect, cache, or redirection response.
- **4xx:** client/policy errors such as 400, 401, 403, 404, 409, 429; do not treat every 4xx as a server error.
- **5xx:** server/gateway errors; must be monitored for SLOs and investigated.
- **Response not yet sent:** a logging API may return `-1`/unknown. Do not automatically log 200 when not yet committed.

In a system behind a proxy, the gateway may return 502/504 to the client even if the application is returning another code or has not yet responded. When investigating, read the access log at the exact layer that emitted the status.

## 4. Access Log Formats: Common, Combined, and JSON

**Common Log Format** typically includes the sender's address, access information, timestamp, request line, HTTP status, and response bytes. **Combined Log Format** adds headers such as Referer and User-Agent. Data from URLs and headers is untrusted input and may contain sensitive information.

In Apache Tomcat, `AccessLogValve` understands patterns such as:

```text
%t %m %U %s %D
```

The codes here (per Tomcat 11):
- `%t`: request timestamp.
- `%m`: HTTP method.
- `%U`: requested URL path; **does not automatically become a route template**.
- `%s`: HTTP response status.
- `%D`: processing time, **microseconds (µs)**.
- `%T`: processing time, **seconds**.
- `%q`: query string; avoid if it contains tokens or personal data.
- `%r`: request line; do not use by default when policy prohibits logging raw request targets.

`common` and `combined` are convenient for traffic analysis, but must be **reviewed before use in production**. In particular, a raw path can also contain user IDs or tokens when a system places secrets in the path. Simply omitting the query string does not guarantee the path is safe.

Structured JSON has a schema that is easier to validate:

```json
{"event":"http_access","method":"POST","route":"/orders","status":201,"duration_ms":42}
```

Use a compliant formatter/encoder to escape quotes, CR/LF, and control characters. JSON does not automatically protect privacy if you still include an `authorization` field or the entire request.

## 5. Configuring Tomcat AccessLogValve

Tomcat provides `org.apache.catalina.valves.AccessLogValve` to write access logs at the container layer, independent of most application logging APIs. **Enabling DEBUG for SLF4J/Logback does not automatically enable Tomcat access logs.**

Example **integration configuration snippet** placed in a valid Tomcat Valve location (Engine/Host/Context):

```xml
<Valve className="org.apache.catalina.valves.AccessLogValve"
       directory="logs"
       prefix="http_access."
       suffix=".log"
       pattern="%t %m %U %s %D"
       rotatable="true"/>
```

Explanation:
- `directory`: file path, which may be relative to `CATALINA_BASE`.
- `prefix` and `suffix`: parts of the file name.
- `pattern`: access log fields; `%U` is still the raw URL path.
- `rotatable`: Tomcat has a file rotation mechanism, but retention, quota, ACLs, backup, and collectors still need to be designed.
- If using multiple Valves, choose different files to avoid overlapping writes. A single request may be logged by multiple container layers if multiple Valves are attached.

Tomcat also provides `conditionIf` and `conditionUnless` (conditional filtering based on request attributes). If you choose to exclude health checks, verify that 5xx responses, requests rejected before reaching the application, and important incidents are not accidentally filtered out. `requestAttributesEnabled` relates to retrieving IP/protocol/port from request attributes configured by Valves such as `RemoteIpValve`.

## 6. Spring Boot: Enabling Access Logs on the Right Embedded Server

When using Spring Boot 3.5 with **embedded Tomcat**, `application.properties` can contain:

```properties
server.tomcat.basedir=./runtime-tomcat
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%t %m %U %s %D
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.prefix=access.
server.tomcat.accesslog.suffix=.log
```

In this example configuration, the file is typically located at `./runtime-tomcat/logs` relative to the working directory if the application has permission to create/write it. Check the actual process path when running via an IDE, CI, service manager, or container; `logs` is not necessarily next to the JAR. `server.tomcat.accesslog.enabled` controls Tomcat and **does not replace** `logging.level.*` for application loggers.

For **Undertow**, the namespace is different:

```properties
server.undertow.accesslog.enabled=true
server.undertow.accesslog.pattern=%t %a %r %s (%D milliseconds)
server.undertow.options.server.record-request-start-time=true
```

Per the Spring Boot 3.5 configuration example, `record-request-start-time=true` is required to record response time `%D`, and **`%D` here is expressed in milliseconds**, unlike Tomcat. Do not copy patterns back and forth and compare latency numbers without normalizing units.

For **Jetty** (when the application actually uses Jetty):

```properties
server.jetty.accesslog.enabled=true
server.jetty.accesslog.filename=./logs/jetty-access.log
```

These are illustrative configuration snippets based on Spring Boot 3.5; verify properties and behavior against the **deployed Spring Boot/container version**. Do not enable Tomcat configuration and assume it affects Jetty/Undertow.

A system where both the gateway and container log should have a clear schema/layer. Do not double-count RPS/error rate when the same request appears in two files.

## 7. Standalone Java 17+ Example: Logging Real HTTP Requests

This example uses the JDK's `jdk.httpserver`, `HttpClient` sending requests to loopback, and `java.util.logging` (JUL) capturing access events. No Spring Boot, Maven, or external libraries are needed.

Behavior to verify:
1. Request `GET /orders/42?token=TEST_ONLY_SECRET` also sends the header `Authorization: Bearer TEST_ONLY_SECRET`.
2. The application logs the **route template** `/orders/{id}`, without logging ID 42, the raw query, or Authorization.
3. The event contains method, actual status, and duration measured with a monotonic clock.
4. An in-memory handler captures the `LogRecord`, and the test asserts the schema and that no secrets are leaked.
5. Standard output only prints deterministic test results, since real timestamps vary by system.

Create **`HttpAccessLogDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class HttpAccessLogDemo {
    static final Logger ACCESS = Logger.getLogger("demo.http.access");
    static final AtomicReference<LogRecord> CAPTURED =
            new AtomicReference<>();
    static final CountDownLatch LOGGED = new CountDownLatch(1);

    static String route(String path) {
        return path.matches("/orders/[0-9]{1,8}")
                ? "/orders/{id}" : "/unmapped";
    }

    static void handle(HttpExchange exchange)
            throws java.io.IOException {
        long start = System.nanoTime();
        try {
            byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } finally {
            int code = exchange.getResponseCode();
            long ms = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start);

            String event = "event=http_access method="
                    + ("GET".equals(exchange.getRequestMethod())
                       ? "GET" : "OTHER")
                    + " route="
                    + route(exchange.getRequestURI().getPath())
                    + " status="
                    + (code >= 100 && code <= 599
                       ? Integer.toString(code) : "unknown")
                    + " duration_ms=" + ms;

            ACCESS.info(event);
            LOGGED.countDown();
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        boolean oldParent = ACCESS.getUseParentHandlers();
        Level oldLevel = ACCESS.getLevel();
        ACCESS.setUseParentHandlers(false);
        ACCESS.setLevel(Level.INFO);

        Handler capture = new Handler() {
            @Override public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    CAPTURED.set(record);
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };
        capture.setLevel(Level.ALL);
        ACCESS.addHandler(capture);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/orders", HttpAccessLogDemo::handle);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(base
                            + "/orders/42?token=TEST_ONLY_SECRET"))
                    .header("Authorization",
                            "Bearer TEST_ONLY_SECRET")
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> reply = HttpClient.newHttpClient()
                    .send(request,
                          HttpResponse.BodyHandlers.ofString());

            if (!LOGGED.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Access event missing");
            }
            String event = CAPTURED.get().getMessage();

            if (!event.matches(
                    "event=http_access method=GET "
                    + "route=/orders/\\{id\\} status=200 "
                    + "duration_ms=[0-9]+")
                    || event.contains("TEST_ONLY_SECRET")
                    || event.contains("token=")
                    || event.contains("/orders/42")) {
                throw new AssertionError("Unsafe event: " + event);
            }

            System.out.println("http_status="
                    + reply.statusCode());
            System.out.println("access_event_verified=true");
            System.out.println("secret_absent=true");
        } finally {
            server.stop(0);
            ACCESS.removeHandler(capture);
            ACCESS.setLevel(oldLevel);
            ACCESS.setUseParentHandlers(oldParent);
            capture.close();
        }
    }
}
```

JDK 17 or later, using the `jdk.httpserver` module:

```bash
javac --add-modules jdk.httpserver HttpAccessLogDemo.java
java --add-modules jdk.httpserver HttpAccessLogDemo
```

**Exact standard output when the environment permits loopback sockets:**

```text
http_status=200
access_event_verified=true
secret_absent=true
```

An example internal access event (not stdout; actual duration may vary):

```text
event=http_access method=GET route=/orders/{id} status=200 duration_ms=12
```

### Code Explanation

- `HttpServer` listens on `127.0.0.1` with port `0` so the OS picks an available port. It does not expose the service to the internet.
- `HttpClient` sends a real HTTP request, but uses only a **dummy** token; never test with real credentials.
- `getRequestURI().getPath()` is only used to **match against an application-controlled route list** and must never be printed directly. If it does not match, print `/unmapped`.
- `System.nanoTime()` measures **duration**, not wall-clock timestamp; the ms result is non-deterministic and is tested with a regex.
- `getResponseCode()` returns the code set by `sendResponseHeaders` or a special value if no response was sent yet. The example uses `unknown` instead of defaulting to 200.
- `finally` logs the event even when the handler encounters normal errors, though process crashes or appender failures can still drop logs.
- `CountDownLatch` lets the test wait until the event reaches the handler; do not use `Thread.sleep` to guess when the worker finishes.
- `server.stop(0)` and `ACCESS.removeHandler` clean up resources in `finally`.

The example demonstrates a successful GET, **not a complete HTTP router**. For production handling, proper method/status/error mapping, disconnect/timeout handling, and an appropriate logging framework/collector are required.

## 8. Servlet Filter: When Should the Application Log Itself?

In systems using the Servlet API, a filter can attach a correlation ID, route template, and measure the time of logic passing through the filter chain. However, not every request reaches the filter:
- The gateway may return 401/403/429 before the request reaches the application.
- The container may return 400/404 or parsing errors before dispatching.
- An async servlet may process **after** `chain.doFilter(...)` returns; if you log immediately in `finally`, the status and latency may not be final.
- Servlets have dispatcher types `REQUEST`, `ASYNC`, `ERROR`, etc.; a filter may run again and cause duplicate logs if not controlled.
- An exception handler or error page may change the status code after the controller/filter step.

Core snippet example **for synchronous processing only** (requires the `jakarta.servlet` API and an SLF4J logger; not a standalone JDK program):

```java
long started = System.nanoTime();
try {
    chain.doFilter(request, response);
} finally {
    long durationMs = java.util.concurrent.TimeUnit.NANOSECONDS
            .toMillis(System.nanoTime() - started);

    int status = httpResponse.getStatus();
    // Only log allowed fields,
    // obtain the route template if provided by the framework.
    accessLogger.info(
            "event=http_access status={} duration_ms={}",
            status, durationMs);
}
```

`chain`, `request`, `response`, and `httpResponse` must be obtained from the running filter. For async Servlets, use `AsyncListener.onComplete`/`onError`/`onTimeout` or the framework's completion mechanism to measure status after processing finishes; avoid logging early in `finally` and treating it as the final value.

If the container already has `AccessLogValve`, consider keeping it as the primary source and using application logs only for business events. If both are required, attach a `layer` field and avoid summing two lines as two requests.

## 9. Reverse Proxies and Source IP

When a Java server sits behind Nginx/Envoy/a load balancer, the IP visible on the TCP socket is usually the proxy IP. Headers like `Forwarded`, `X-Forwarded-For`, and `X-Forwarded-Proto` can carry client information, but **untrusted clients can spoof these headers**.

Principles:
1. Only trust forwarded headers when the request arrives from a verified trusted proxy.
2. Ingress must strip/normalize client-sent headers according to the system topology.
3. Configure the list of trusted proxies and how to select the IP when there are multiple proxy hops.
4. If using Tomcat, study `RemoteIpValve` and `requestAttributesEnabled` on `AccessLogValve` to obtain normalized values.
5. Test behavior with forged-header requests in a test environment; never make security decisions based on raw `X-Forwarded-For`.

An IP address can also be personal data in specific contexts. Do not retain it longer than necessary; apply appropriate policy, access control, retention, and redaction criteria.

## 10. Request ID, Trace ID, and Privacy

Correlation ties logs together:

```text
Gateway   request_id=req_7c9 route=/orders/{id} status=200
Tomcat    request_id=req_7c9 status=200
Service   request_id=req_7c9 event=order_loaded
Trace     trace_id=... span_id=...
```

A client-sent `X-Request-ID` value should not be copied verbatim into logs without character/length restrictions. Use an ID generated by the server/ingress or validate it against a contract. Never use emails, tokens, or free-form user input as an ID.

In Java, MDC/ThreadContext typically attaches `requestId` to application logs; however, when hopping threads, using executors, or using virtual threads, context propagation requires proper framework support. Clean up the context in `finally` so requests do not bleed into one another when workers are reused. For container access logs, a mechanism to read request attributes/trace context from the right backend is needed; MDC data does not always appear automatically in a Valve.

Storing user/tenant IDs in every access event is not mandatory; if needed for security/analytics, there must be a defined purpose, permissions, retention, and measures to reduce re-identification risk.

## 11. Calculating Latency and RPS Accurately

Several metrics have similar-sounding names but different meanings:

| Metric | Typical Start/End Points |
| --- | --- |
| Server request processing time | From receipt/dispatch at the server until completion at the measurement layer |
| Time to first byte | Until the response begins being sent/committed |
| Gateway upstream duration | The proxy's exchange with the backend |
| Client end-to-end latency | Client DNS/TLS/network/server/body download |

Do not compare latency from two sources without verifying **units, measurement points, timeouts, and streaming handling**.

For example, Tomcat `%D` is in **microseconds**, whereas the Java code in Section 7 uses **milliseconds**. In the illustrative Spring Boot Undertow configuration, `%D` also uses milliseconds with the start-time recording option enabled. Mixing up units can skew dashboards by a factor of 1,000.

Useful metrics:
- RPS by route + method.
- 5xx/4xx rates, distinguishing 401, 403, 404, 429, 502, and 504.
- p50/p95/p99 of duration at the same measurement layer.
- Response size and traffic volume, if bytes are defined consistently.
- Counts of generated/accepted/written/dropped events when access logs use an async appender or collector.

**The number of access log lines does not always equal the true request count**: this can be due to sampling, filters, full queues, appender errors, stdout log driver data loss, or duplicate records across layers. Strict SLO measurement usually requires metrics at a consistent observation point.

## 12. Security, Log Injection, and Operational Cost

Access logs receive many fields from external sources: path, query, User-Agent, Referer, and forwarded headers. They may contain CR/LF, extremely long strings, emails, tokens, or private data. **Parameterized logging does not automatically neutralize CRLF injection** if a plain-text formatter still prints newlines. Solutions:
- Define a clear schema and log only allowed fields, preferring route templates.
- Never log `Authorization`, `Cookie`, `Set-Cookie`, access tokens, passwords, bodies, or raw queries.
- Validate IDs, enforce length limits, escape according to the output format, and use a reliable JSON encoder.
- Separate client data/metadata from key names and log templates so clients cannot dictate structure.
- Audit file/collector permissions, rotation, retention, backups, and exports.
- Never use raw paths containing secrets in path segments; fix this at endpoint design or map to a safe route name.

For high-traffic systems:
- Writing one event per request can generate massive data volume; multiple layers multiply it further.
- Async logging lets the producer return early but does not infinitely expand sink capacity; a bounded queue will fill up if logs are produced faster than written.
- Frequent health checks can be sampled or conditionally excluded, while protecting 5xx and abnormal signals.
- Monitor CPU, latency, queue depth, dropped events, disk/network, and collector lag.
- When access logs serve security/audit purposes, do not arbitrarily drop them to prioritize throughput.

When using Tomcat `conditionIf`/`conditionUnless` to filter events, test request paths that bypass the application, failed health checks, and unset attribute cases to avoid losing security-relevant events.

## 13. End-to-End Access Log Testing

### Schema Unit Tests

Verify that:
1. Method is within the valid set, route is a template, status code is accurate, and duration is non-negative.
2. Raw URL/query, Authorization/Cookie, emails, or canary tokens do **not** appear.
3. Overly long or CRLF-containing client Request IDs are replaced/rejected per policy.
4. Unknown paths are not logged as raw strings and do not cause cardinality explosion.
5. Events without a response code are represented as unknown/error rather than silently turning into 200.
6. JSON is parseable and client characters cannot break lines/fields.

### HTTP Integration Tests

- Send 200, 201, 302, 400, 401, 403, 404, 429, and 500 across endpoints that produce them; verify status at the chosen layer.
- Verify that requests blocked by the gateway never reach the application filter.
- Send canary queries/headers/paths and scan files, stdout, appenders, collectors, and exports.
- If using async servlets, measure after completion; verify no double logging across REQUEST/ASYNC/ERROR dispatches.
- For client disconnects, large uploads/streaming, and timeouts, verify the server logs what it can actually know.
- Verify request ID/trace ID propagation across layers without placing PII in IDs.
- Test log rotation, restarts, file permissions, retention, and flush/delivery.
- Test slow collectors, full queues, or sampling so enqueued logs are not mistaken for persisted logs.

In JUnit/CI, use dummy data and OS-assigned ports like the program in Section 7. Capture events as records/JSON, use a latch/poll with a deadline for async processing, and avoid `Thread.sleep(100)` or exact duration assertions since values vary by machine.

## 14. Troubleshooting

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| App has `LOG.info` but no access log | Container access log not enabled | Valve / `server.tomcat.accesslog.enabled` property |
| Gateway shows 401/429 but controller logs nothing | Request was not forwarded to the app | Edge access log and routing policy |
| Access file is in the wrong location | Different `basedir`/`directory`/working directory | Check the actual process path |
| Filter status differs from client status | Async, error dispatch, or gateway altered the result | Compare status at each layer |
| Unusually large or small duration | Unit mix-up on `%D` or end-time measurement | Check backend docs, normalize µs/ms |
| IP is only the proxy IP | Forwarded headers not normalized | Trusted proxies, `RemoteIpValve` |
| One request counted twice | Logged at proxy + container/filter | Tag layer, pick primary RPS source |
| Token appears in URL log | Pattern uses raw path/query/headers | Use route template, allowlist |
| Log lines broken by input | CRLF/log injection from User-Agent/path | Validate and escape |
| Events missing or delayed | Async queue, I/O error, shipper lag, shutdown | Metrics and verify final sink |
| Filter reports 200 when actual is 500 | Response not yet committed or error occurred after filter | Use completion/container log |
| High-cardinality metrics | Actual path IDs used instead of route templates | Normalize endpoints before aggregation |

## 15. Production Deployment Checklist

- [ ] Identify the primary layer for access logs; have a plan to handle duplicate layers.
- [ ] Schema includes timestamp, method, **route template**, status, duration in the right unit, and correlation ID.
- [ ] Avoid raw query, Authorization, Cookie, request body, and unnecessary personal data.
- [ ] Verify raw paths and headers are escaped/bounded if logging them is strictly required.
- [ ] Only trust forwarded headers from verified proxies that have been normalized by ingress.
- [ ] Test 2xx/3xx/4xx/5xx, pre-app errors, async, timeout/streaming, and disconnects as needed.
- [ ] Configure the right server (Tomcat, Undertow, or Jetty), file output path, and service permissions.
- [ ] Have rotation, retention, backup, and log read/export access controls in place.
- [ ] Track RPS/5xx/p95/p99 from the right source, accounting for sampling/drops/backpressure.
- [ ] Use trace/request IDs for correlation, without putting personal data into IDs.
- [ ] Test canaries and log injection from the application through the collector, not just at the source.
- [ ] Verify behavior after restarts, during collector slowdowns, and when temporary debug configs are enabled.

## 16. Practice Exercises

1. Run `HttpAccessLogDemo`. Explain why `http_status=200` is printed, why the route is templated, and why `TEST_ONLY_SECRET` is not leaked.
2. Modify the handler to return 405 for non-GET methods; emit an access log with status 405 and add a corresponding test.
3. Add another route without logging raw paths when the route template is unknown.
4. Enable Tomcat access logging in a Spring Boot service. Check the file path and `%D` in microseconds.
5. Compare a request rejected by the gateway with 429 against a request reaching the app and returning 200: which events exist at each layer?
6. Send a spoofed `X-Forwarded-For`. Explain why this header cannot be trusted directly.
7. Run an async servlet; compare logging in the filter's `finally` block with logging in the completion callback.
8. Build RPS and p95 queries/dashboards by `route`, eliminating double-counting between gateway and container.
9. Send URLs and User-Agents containing fake sensitive data, CRLF, or long text; verify redaction and escaping.
10. Inspect access logs after rotation, archiving, and collection; who can read them and how long are they retained?

## 17. Key Takeaways

- **HTTP access logs** record request/response metadata at a web processing point, not a dump of HTTP bodies.
- Reverse proxies, containers, and filters see different subsets of requests; choose the appropriate layer and avoid double-counting.
- Use **method, route template, status, duration, timestamp, and correlation ID**, with a clear field/privacy policy.
- In Tomcat `%D` is **microseconds**; in the Spring Boot Undertow example it is **milliseconds**. Always convert units properly.
- Never trust client-sent forwarded headers; protect queries, paths, Authorization, Cookies, and fields prone to log injection.
- Combine access logs with metrics/traces; event counts may be duplicated, sampled, dropped, or delayed.
- Test error statuses, async, proxies, privacy, retention, and collectors before going to production.

### References

- Apache Tomcat 11 — AccessLogValve: https://tomcat.apache.org/tomcat-11.0-doc/config/valve.html
- Spring Boot 3.5 — Configure Access Logging: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Oracle JDK 21 — HttpExchange: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle JDK 21 — HttpServer: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
