# Separating Access Logs in Java Logging

## 1. What Is Access Log Separation and Why Is It Needed?

An **access log** records when a client or another component accesses a service, especially **HTTP request/response** traffic. Each record typically indicates the method, path or route, HTTP status code, processing duration, and correlation metadata such as a request ID or trace ID. An **application log** records internal application activity: business processing, component state, dependency call errors, retries, and exceptions.

**Separating access logs** means routing these two types of events to separate streams or destinations so they can be filtered, stored, access-controlled, and analyzed independently. For example:

- `access.log`: one line or one structured event per HTTP request that the system has processed to a recordable point.
- `application.log`: internal service events such as "order created", "calling payment", or "payment timeout".
- `audit.log`, if present: audit events requiring separate trust, access control, and retention policies; **do not automatically equate audit logs with access logs**.

For instance, a `POST /checkout` request returning HTTP 504 may produce **one access log** and **multiple application logs** describing the internal steps, as both represent different perspectives on the same request.

```text
Client ─► Gateway ─► Java HTTP server ─► Application ─► Dependency
              │              │                │
              ▼              ▼                ▼
          Gateway         Access log       Application log
          access log      (request)        (business/error)
                              │                │
                              └──── trace/request ID ────┘
                                       │
                                       ▼
                          Collector / Logging Backend
                           ├── http_access index/stream
                           └── application index/stream
```

**Goal:** avoid mixing HTTP traffic logs with business messages, make it easy to compute HTTP status rates and latency, streamline incident investigation, and apply appropriate retention policies per event type.

## 2. How Do Access Logs Differ from Application Logs and Audit Logs?

| Criterion | Access log | Application log | Audit/security log |
| --- | --- | --- | --- |
| Core event | Access traffic, HTTP request/response | Processing behavior, state, internal errors | Auditable actions or security events |
| Creation time | Usually when the request finishes or reaches a recordable point | Anytime during processing | When an audited action occurs |
| Key fields | Method, route/path, status, duration, request ID | Logger, level, message, exception, trace ID | Actor, action, outcome, target, policy-defined timestamp |
| Volume | Can be close to the number of requests per hop | Can be 0, 1, or many records per request | Proportional to actions requiring auditing |
| Main question | Who/where/when/outcome and latency? | What did the system do, and why did it fail? | Who did what, and was it allowed or denied? |
| Retention, access | Based on traffic volume and investigation needs | Based on operations/debugging | May have stricter legal/compliance requirements |

An access log with HTTP status 500 **does not inherently carry an ERROR logger level**. An access event can be emitted at the `INFO` level with the field `http.status_code=500`, and dashboards can filter by status. If you use the `ERROR` level for all 5xx requests, establish a clear convention; do not use the log level as a complete replacement for the status field.

Similarly, a `404` response is not always an application bug: it could be a wrong URL, a crawler, or a business case where a resource is not found. From the access log alone, you only know the returned status, not the underlying internal cause.

## 3. Essential Attributes in an HTTP Access Log

A structured schema may include:

| Field | Purpose | Notes |
| --- | --- | --- |
| `timestamp` | Time the event was recorded | Explicit UTC/offset; distinguish start/end time if present |
| `service.name` and `environment` | Service/deployment identity | Useful with multiple instances/pods |
| `kind=http_access` | Event classification for routing | Naming agreed upon by the operations team |
| `http.request.method` | `GET`, `POST`, `PUT`, etc. | Matches the actual request value |
| `http.route` | Normalized route, e.g., `/orders/{id}` | Preferred for grouping metrics and searching |
| `url.path` | Received path | May contain sensitive data or IDs |
| `http.response.status_code` | Actual HTTP status | Do not infer from a single exception |
| `duration_ms` | Duration at the measured hop | Specify start/end points and unit |
| `request_id` / `trace_id` | Correlate events of the same request/trace | Requires a generation and propagation strategy |
| `client.address` | Connection source | Proxies/NAT and forwarded headers affect reliability |
| `response.bytes` | Size of sent data | Clarify whether HTTP headers are included |

The field names above are **schema suggestions**; OpenTelemetry semantic conventions or your collector may use different names, versions, and specific mappings. What matters is consistent classification and a documented schema.

Example of an illustrative JSONL event:

```json
{"timestamp":"2026-11-10T02:30:00.100Z","service.name":"checkout-api","kind":"http_access","http.request.method":"POST","http.route":"/checkout","http.response.status_code":504,"duration_ms":2501,"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736"}
```

Such an event enables querying `kind=http_access AND status>=500` without relying on whether application logs contain the keyword "failed".

**Data sensitivity:** raw paths, query strings, usernames, IP addresses, referers, and user-agents can contain personal data or tokens. Never log full request bodies, `Authorization` headers, cookies, or query strings into access logs by default. Use route templates and redaction/allowlists whenever possible.

## 4. Choosing Where to Capture Access Logs Before Separating

Access logs can be emitted by a **reverse proxy/API gateway**, an **in-process HTTP server**, or **middleware/filters**. Each layer observes a different "hop":

| Layer | What it observes | What it can miss |
| --- | --- | --- |
| Gateway/reverse proxy | Edge ingress requests, upstream status, some timing and retries | Full internal service logic |
| Embedded HTTP server (e.g., Tomcat) | Requests reaching the application and HTTP responses at the server | Total time spent at gateway/client; applies only to that server |
| Application filter/interceptor | Can attach route, correlation ID, and application metadata | Async/error dispatches, streaming, errors occurring before the filter |
| Collector | Routing based on tags/fields/files, access control, and data transformation | Cannot reconstruct events never emitted at the source |

**The right choice depends on the observability question.** Want to know if requests are blocked before reaching the application? Check the gateway access log. Want to know the processing path to embedded Tomcat? Check the server access log. Want to attach business route names and authorized tenant info? Middleware or instrumentation can provide those extra fields.

An HTTP request passing through a gateway and calling two microservices can produce **three access events across three hops**. This is not necessarily duplicate logging: each event describes a different hop. However, if the same Tomcat request is logged by both `AccessLogValve` and a custom filter to **the same destination**, the system may double-count traffic unless classified clearly.

## 5. Approach 1 — Separating Access Logs Using Embedded Tomcat in Spring Boot

For **Spring Boot applications using embedded Tomcat**, you can enable the container's access log. This is a server-level HTTP access logging mechanism, independent of `logger.info(...)` calls in business code. Example `application.properties`:

```properties
# Only for Spring Boot applications actually running embedded Tomcat.
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.prefix=access
server.tomcat.accesslog.suffix=.log
server.tomcat.accesslog.pattern=%a %t "%m %U %H" %s %b %D
```

**Tomcat AccessLogValve** tokens in the pattern above:

- `%a`: remote IP address as recorded by the container; may be the proxy IP if proxy handling is not configured properly.
- `%t`: request timestamp in access log format.
- `%m`: HTTP method.
- `%U`: URL path portion; differs from `%r` (request line) and does not intentionally include the query string.
- `%H`: request protocol version.
- `%s`: HTTP response status.
- `%b`: response data size as defined by `AccessLogValve`.
- `%D`: request processing time in **milliseconds** for this `AccessLogValve` pattern.

Example log line to illustrate the format:

```text
192.0.2.10 [10/Nov/2026:09:30:00 +0700] "GET /health HTTP/1.1" 200 17 3
```

This is an **illustrative line**, not fixed stdout: the address, timestamp, byte count, and duration depend on the actual request.

**Practical notes:**

1. `directory=logs` is resolved by Tomcat relative to **Tomcat's base directory**; the file will not necessarily appear in `./logs` of your command working directory. In containers or ephemeral environments, verify the final path and volume mounts.
2. Access filenames may include the date and undergo rotation per Tomcat configuration. Do not let multiple containers write arbitrarily to a shared file on a volume without designing locking and rotation.
3. `server.tomcat.*` properties **do not apply** when the application uses embedded Jetty, Undertow, or Reactor Netty. For those stacks, use their respective features and properties.
4. Method, path, and HTTP status are recorded at the server layer. If you need `http.route` as a `/orders/{id}` template, the container usually only has the raw request path; you will need additional instrumentation or normalization at the collector.
5. `%U` avoids the query string in the pattern above, yet **the path can still contain sensitive data**, such as emails or user identifiers; review endpoint design and security policies.
6. The container access log describes the request at Tomcat's hop. If an upstream proxy logs 504 due to timeout while Tomcat eventually logs 200 for another processing path or after client disconnect, the two statuses can differ; inspect the right hop during investigation.

Spring Boot still produces application logs via SLF4J/Logback or another backend. Enabling container access logging gives you two separate log sources from the start; the collector will need to ingest the right files/streams and attach classification labels.

## 6. Approach 2 — Using a Dedicated Logger and Routing with Logback

If the application actively emits access events in a filter or interceptor, use a dedicated logger name—such as `http.access`—and configure a separate appender. The goal is **routing by event type** without sending every request to the application log appender.

Example **`logback.xml` or `logback-spring.xml`** configuration when using Logback-classic:

```xml
<configuration>
    <appender name="APPLICATION" class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ACCESS" class="ch.qos.logback.core.FileAppender">
        <file>logs/access-app.log</file>
        <append>true</append>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="http.access" level="INFO" additivity="false">
        <appender-ref ref="ACCESS"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APPLICATION"/>
    </root>
</configuration>
```

Key points:

- The `http.access` logger sends events to the `ACCESS` appender.
- `additivity="false"` prevents events from this logger from **propagating up to the root appender** and being written into `application.log` as well. If you omit this attribute in the example, the same access event can appear in both `ACCESS` and `APPLICATION`.
- Application loggers outside the `http.access` hierarchy continue to follow the standard root configuration.
- This configuration uses `FileAppender` to illustrate the routing path. In production, you typically need `RollingFileAppender`, rotation/retention, disk space controls, and a container logging strategy.
- `access-app.log` is distinct from Tomcat's file in the previous section. If you enable **both** Tomcat access logging and custom application access logging for the same requests, you must classify and deduplicate when counting requests, or pick a single canonical source.
- For JSONL output, use a JSON encoder/formatter compatible with your backend version instead of a plain-text pattern, and standardize the `kind=http_access` field.

Example access logger call in Java using **SLF4J**:

```java
// Illustrative snippet: the application must have SLF4J + backend dependencies.
private static final org.slf4j.Logger ACCESS =
        org.slf4j.LoggerFactory.getLogger("http.access");

// Call at the end of the request, with validated and sanitized data.
ACCESS.info("method={} route={} status={} duration_ms={}",
        "POST", "/checkout", 504, 2501);
```

The snippet above is **not a standalone Java program** and does not automatically emit access events per request. It only illustrates how to emit an event under a specific logger name; timing, HTTP scope, status, duration, and async handling must be measured properly by the system.

### Why Be Careful with Appender Additivity?

In Logback, loggers are hierarchical by name—for example, `http.access` sits under `http` and ultimately under `root`. If the access logger has its own appender but remains additive, events are also forwarded to parent logger appenders. Separating files while forgetting additivity creates **two physical records** for a single event, increasing storage, ingestion cost, and even triggering duplicate alerts.

However, `additivity=false` is not an "absolute deduplication switch": if two different middlewares both emit events, or a request is logged at both the gateway and the application, multiple events will still exist. Distinguish **duplicates caused by appender routing** from **legitimate multiple events across multiple hops**.

## 7. When Should Access Events Be Emitted?

An access event should reflect **the outcome actually observed by the measuring component**. Simple HTTP flow:

```text
Incoming request
   │
   ▼
Record start time, request ID
   │
   ▼
Authentication → routing → handler → response
   │
   ▼
Determine status, duration, response size (if available)
   │
   ▼
Emit exactly one access event for the measured hop
```

When writing a custom Servlet Filter for a Spring MVC/Servlet application:

- Start with `System.nanoTime()` to measure elapsed time; avoid wall-clock diffs that are vulnerable to clock adjustments.
- Read `HttpServletResponse.getStatus()` at the appropriate time; do **not** infer status solely from whether an exception occurred.
- Place the log emission in `finally` so you do not miss error branches actually observed by the filter, but note that an exception may be translated into a different status by an error handler **after the filter returns**.
- Do not assume the filter's `finally` block marks final response completion. With **async dispatch**, streaming, SSE, and WebSockets, the request lifecycle can continue after the initial filter invocation ends. When final completion timing is required, use container access logs or a properly designed and tested lifecycle/`AsyncListener` mechanism.
- Some requests are rejected before the application filter or at the gateway. The filter cannot log requests that never reach it.
- Preserve correctness when a filter is invoked multiple times due to error/async dispatches; enforce a "one event per request/hop" policy with a clear guard key.

Example Servlet Filter **illustrating synchronous scope** (using Spring Boot 3 with Jakarta Servlet and SLF4J, not standalone):

```java
@Component
public class AccessLogFilter extends OncePerRequestFilter {
    private static final org.slf4j.Logger ACCESS =
        org.slf4j.LoggerFactory.getLogger("http.access");

    @Override
    protected void doFilterInternal(
            jakarta.servlet.http.HttpServletRequest request,
            jakarta.servlet.http.HttpServletResponse response,
            jakarta.servlet.FilterChain chain)
            throws jakarta.servlet.ServletException, java.io.IOException {

        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                    java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);

            ACCESS.info("method={} path={} status={} duration_ms={}",
                    request.getMethod(),
                    request.getRequestURI(),
                    response.getStatus(),
                    elapsedMs);
        }
    }
}
```

Compiling this snippet requires `import` statements for `org.springframework.stereotype.Component` and `org.springframework.web.filter.OncePerRequestFilter`, along with the Spring Boot Web dependency; it is a framework-dependent excerpt. This example **does not completely handle** async completion/error dispatches, does not normalize paths into routes, and does not redact sensitive data. Do not copy it verbatim as a production design for SSE, async, or private data; those cases require server instrumentation or tested lifecycle hooks.

If an endpoint is `/orders/42`, logging `request.getRequestURI()` directly exposes the raw ID; for grouping and data protection, use a route template like `/orders/{id}` once the framework resolves the route, or apply valid normalization policies at the collector.

## 8. Standalone Java 17: Two Independently Routed Log Streams

This example uses **java.util.logging (JUL)** built into the JDK to clearly demonstrate logger-based event separation. To keep output deterministic and avoid machine-dependent file I/O, two handlers write to **two separate buffers**, and finally print each buffer as if it were the contents of `access.log` and `application.log`.

This is a **routing simulation**, not an HTTP server and not a Logback configuration. In practice, replace the buffers with a `FileHandler` or appropriate appender.

Save as **`AccessLogRoutingDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class AccessLogRoutingDemo {
    private static final class BufferHandler extends Handler {
        private final StringBuilder lines = new StringBuilder();

        BufferHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                lines.append(record.getMessage()).append('\n');
            }
        }

        @Override
        public void flush() {
            // Data is held in the example's StringBuilder.
        }

        @Override
        public void close() {
            flush();
        }

        String content() {
            return lines.toString();
        }
    }

    public static void main(String[] args) {
        Logger access = Logger.getLogger("http.access");
        Logger application = Logger.getLogger("app.business");

        // Do not forward events to parent/root logger handlers.
        access.setUseParentHandlers(false);
        application.setUseParentHandlers(false);
        access.setLevel(Level.INFO);
        application.setLevel(Level.INFO);

        BufferHandler accessSink = new BufferHandler();
        BufferHandler applicationSink = new BufferHandler();
        access.addHandler(accessSink);
        application.addHandler(applicationSink);

        try {
            application.info("Payment request started");
            application.severe("Gateway timeout");

            // HTTP status is a data field, not necessarily a log level.
            access.info("POST /checkout status=504 duration_ms=2501");
            access.info("GET /health status=200 duration_ms=2");

            System.out.println("=== access.log ===");
            System.out.print(accessSink.content());
            System.out.println("=== application.log ===");
            System.out.print(applicationSink.content());
        } finally {
            access.removeHandler(accessSink);
            application.removeHandler(applicationSink);
            accessSink.close();
            applicationSink.close();
        }
    }
}
```

Compile and run commands:

```bash
javac --release 17 AccessLogRoutingDemo.java
java AccessLogRoutingDemo
```

Exact stdout:

```text
=== access.log ===
POST /checkout status=504 duration_ms=2501
GET /health status=200 duration_ms=2
=== application.log ===
Payment request started
Gateway timeout
```

**Why are they not mixed?** Both loggers are attached to separate handlers; `setUseParentHandlers(false)` prevents forwarding to root. The 504 status event still goes through `access.info(...)` because **HTTP status and JUL log level are two independent concepts**.

**Example limitations:** `StringBuilder` is not thread-safe for concurrent writes; the program logs sequentially on a single thread so output is deterministic. Production logging requires thread-safe appenders/handlers, rotation, I/O error handling, queuing/flushing/shutdown, and proper field structure; do not use this example as a real logging system.

## 9. Separating at the Collector by Tag, File Path, or Kind Field

If the application and container already produce two files, the collector can route them to different streams or indices. Conceptual diagram (not a runnable config for a specific collector):

```text
logs/access*.log          ─┐
                            ├─► access parser → kind=http_access
logs/application*.log     ─┘
                              app parser    → kind=application
                                            │
                                            ▼
                                route by kind/service/env
                                  ├─ access stream
                                  └─ application stream
```

Rules to enforce:

1. **Sources are clearly identified** by filename, container stream label, or `kind` field. A single file mixing both types differentiated only by message keywords is much harder to process than structured logs.
2. **Parsers match the source format.** A Tomcat access pattern is not JSON; do not configure a JSON parser for plain-text access log lines.
3. **Queryable fields are normalized**: method, route, status, duration, and trace ID (when genuinely available). Keep measurement units explicit and consistent across services.
4. **An event never accidentally enters multiple identical routes** due to overlapping rules or both a file tailer and a stdout collector reading the same data.
5. **Retention and access permissions differ** for access, application, and audit logs, while ensuring logs can still be correlated during investigations.
6. **Track ingestion errors and dropped events** so you know when an access line is lost before reaching the backend, rather than assuming every request has a record.

If the system runs on containers/orchestration and the application writes to stdout, you can route by a **structured field** instead of creating separate files. Logical "separation" in the logging backend remains valuable even when sharing physical stdout. The choice depends on collection capabilities, operations, and desired isolation level.

## 10. Attaching Request ID and Trace ID Across Both Log Types

Separating storage streams does not mean separating investigations. Both streams should share a common join key, for example:

```text
access:
2026-11-10T02:30:00Z POST /checkout status=504 trace_id=4bf92f...

application:
2026-11-10T02:29:58Z ERROR payment gateway timeout trace_id=4bf92f...
```

This is an abbreviated illustration; real systems should preserve the **full trace ID** and span ID if available.

With Java and OpenTelemetry:

- HTTP server instrumentation can generate or accept trace context according to trust rules and propagate it within the request scope.
- Application logs can carry `trace_id`/`span_id` via MDC or structured logging integration.
- Custom access events can capture the **active and valid** trace context at the right processing point; raw container access logs usually do not include a trace ID field automatically.
- Simply logging client-supplied `traceparent` or `X-Request-ID` headers verbatim treats **untrusted input** as canonical system IDs; validate, bound length, and guard against log injection.
- For requests traversing a gateway and multiple services, each hop may have its own access event. Use `trace_id` + `service.name` + hop/timestamp to link them, without assuming one trace always corresponds to a single HTTP request.

Some backends store request IDs and trace IDs under different field names; standardize this in the ingestion pipeline. Never turn trace IDs or request IDs into unbounded-cardinality metric labels.

## 11. Calculating Request Counts and Latency from Access Logs

For example, suppose an access stream contains normalized events with `route`, `status`, and `duration_ms` attributes. You can compute:

- Total requests **recorded at the measured hop**.
- Count and rate of HTTP `4xx` and `5xx` responses (by status semantics), segmented by route/method/env.
- Latency distribution (p50, p95, p99) according to the exact measurement start/end points.
- Traffic over time, top routes, slow requests, and post-deploy error spikes.

Illustrative data example:

| Route | Status | Duration |
| --- | ---: | ---: |
| `GET /orders/{id}` | 200 | 12 ms |
| `GET /orders/{id}` | 200 | 18 ms |
| `POST /checkout` | 504 | 2501 ms |
| `GET /health` | 200 | 2 ms |

Looking at these rows reveals a slow 504 response, but **you cannot conclude** the payment gateway is the root cause without reading application logs, traces, and upstream metrics. Access logs excel at describing symptoms at the HTTP boundary; application logs explain what happened inside.

To compute reliable rates and percentiles, you must:

1. Choose **one canonical source/hop** for the statistical sample. Do not sum gateway and Tomcat logs for the same request.
2. Account for retries: a single user action can generate multiple HTTP requests, especially through proxies or client retries.
3. Check sampling and dropped lines. If you only sample successful requests while keeping all errors, error rates calculated directly from logs will be skewed.
4. Distinguish a 200 returned by the gateway, a 200 returned by the service, and a request blocked before reaching the service.
5. Understand source timestamp/duration limits; streaming and client aborts may not fit a "business processing latency" interpretation.

Metrics emitted directly by HTTP server instrumentation are usually better suited for rate calculations, while access logs retain per-request detail; the two complement each other.

## 12. Protecting Sensitive Information in Access Logs

Access logs are typically written at high volume and shared with operations teams, so data must be restricted right at the point of emission.

**Do not include by default** the following in access logs:

- `Authorization`, `Cookie`, tokens, session IDs, API keys, passwords.
- Request/response bodies, especially payment details, personal profiles, or medical data.
- Full query strings: URLs may contain `token` or sensitive parameters.
- Raw route paths containing emails, document numbers, or identifiers when a template can be used.
- Arbitrary client-sent headers just for "easy debugging"; `User-Agent` and `Referer` can also contain unintended data or control characters.

IP addresses, timestamps, routes, and response codes can also constitute personal data when correlated; apply appropriate retention, access control, export limits, and handling policies. If you must store IPs for security, define the purpose and retention period clearly.

**Client IP behind proxies:** `X-Forwarded-For` can be spoofed by clients if the application trusts any header. Only use addresses derived from a trusted proxy chain or proper server/gateway configuration; do not arbitrarily take the first element and treat it as the "real IP".

**Log injection:** paths, custom methods, user-agents, or headers containing newlines/control characters can break plain-text log structure. Structured encoders, escaping, and field allowlists prevent forged multi-line entries. Never let an unchecked input string determine a filename or stream name.

## 13. Performance, Storage, and Reliability Considerations

Access logs can be emitted for **every request**, including health checks, failed requests, static assets, or bot traffic. At high volume, logging easily becomes a significant I/O load.

- **Capacity:** estimate requests/day × average event size × retention period; check quotas, rotation, and growth rate.
- **Traffic filtering:** consider dropping or reducing logs for health checks or static assets, but remember this makes logged request counts lower than actual traffic; do not use a filtered sample to compute total rates without adjustment.
- **Sampling:** sampling a fraction of requests can aid debugging at high volume, but does not guarantee accurate statistics and can hide rare events.
- **Async appenders:** reduce logging wait time in some cases; full queues can block or drop events. Count dropped events and monitor event-to-sink latency.
- **File rotation:** access files are often larger than application logs; configure dedicated rotation schedules, size limits, and retention. Avoid multiple processes writing concurrently to the same path without proper design.
- **Failure modes:** full disks, missing permissions, stopped collectors, network timeouts, and process crashes can all lose logs. A "successful response" does not guarantee the access event was durably stored.

If access logs serve as audit evidence or billing records, design a durable write/reconciliation path per business requirements; ordinary operational log files rarely provide exactly-once transactional guarantees.

## 14. Common Pitfalls During Investigation

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Two identical access events per request in one file | Both Tomcat access log and custom filter are logging, or collector reads the same file twice | Check sources, logger/appender, collector, and event ID |
| Access events leak into `application.log` | Access logger is still additive to root in Logback | Use a dedicated logger name, verify `additivity=false` and appender refs |
| Gateway shows 504, service has no 504 | Gateway timed out/blocked before service, service returned another code, or request was aborted | Compare hops, trace/request ID, proxy timeout |
| Service has application ERROR but no access event | Error occurred outside HTTP, request never completed, access logging disabled, or pipeline dropped data | Identify task type and request lifecycle |
| Access shows 200 but client reports an error | Proxy/client failed after server, buffering, or hop mismatch | Check client, gateway, and server logs |
| Filtered access logs alone yet dashboard traffic doubled | Counting both gateway and application for the same request | Pick one canonical hop or group by hop |
| Tomcat creates files in an unexpected location | `directory` is relative to Tomcat base directory | Check actual path and container config |
| Access log lacks trace ID | Container access log is uninstrumented / correlation field not injected | Check context creation and schema at emission point |
| Wrong client IP behind reverse proxy | Reading proxy connection IP or trusting unverified headers | Configure trusted proxies, verify trusted IP ranges |
| Log contains sensitive path/query | Using raw request line/URI without data rules | Use route templates, strip queries, redact via allowlist |
| Access latency is lower than client-observed total time | Service measurement differs from gateway/client measurement | Compare start/end points, retries, network, and queueing |
| Access logs disappear after restart | Path inside ephemeral container, unmounted, or retention too short | Check volumes, lifecycle, file shipper |
| Logs dropped under high load | Queue/backpressure, file I/O, collector drops | Monitor dropped/failed writes and sink load |

## 15. Testing Access Log Separation

A meaningful test plan should cover:

1. **Happy path:** call `GET /health` returning 200; verify exactly one access event at the chosen source/hop and confirm it does not appear in the application sink due to appender routing.
2. **HTTP errors:** call endpoints producing 4xx and 5xx in a test environment; verify the access event has the actual status even when the application does not log an application ERROR.
3. **Business logs:** emit application `INFO` and `ERROR`; verify both go to the application sink without leaking into the access sink.
4. **Correlation:** send a request that triggers business logs; verify a valid correlation ID links both log types.
5. **Duplication:** if gateway, Tomcat, and custom filter are all enabled, aggregate per hop and verify dashboards do not double-count samples.
6. **Async/error dispatch:** test async requests, requests throwing exceptions, streaming, and client aborts to see where and how many times events are emitted.
7. **Sensitive data:** send queries with dummy sensitive values; verify tokens/headers/bodies are excluded from access logs; check character escaping.
8. **High load:** measure queue depth, dropped event count, write duration, file rotation, and business latency with access logging enabled.
9. **Deploy/restart:** verify files/streams persist per volume policy, collector parsing works, and actual retention matches config.
10. **Permissions:** verify authorized users can view access logs/traces while unauthorized users are restricted per system policy.

Example acceptance criteria for a service with `ACCESS` and `APPLICATION` appenders:

```text
Request POST /checkout returns 504
→ ACCESS: 1 event, with method, route, status=504, duration
→ APPLICATION: 0..N events depending on actual operations/errors
→ ACCESS event must not be automatically duplicated in APPLICATION sink
→ Correlation ID is accurate on both when provided by instrumentation
```

**Do not force application log counts to match HTTP request counts.** Some completely normal requests need no business logs; a complex request may need many.

## 16. Choosing an Implementation by Scenario

| Scenario | Usually suitable option | What to verify |
| --- | --- | --- |
| Spring Boot + Tomcat, needing basic HTTP access logs | Embedded Tomcat `AccessLogValve` | Actual file, status, elapsed time, retention, source |
| Need route templates and business metadata | App instrumentation/filter with proper lifecycle | Async/error completion, privacy, trace propagation |
| Gateway protecting multiple services | Gateway access log as edge traffic source | Retries, upstream/hop, blocked events |
| Already emitting classified JSON events on stdout | Collector routing by `kind` and service | Parser, labels, no double-ingest |
| Want a separate file for an access logger | Dedicated logger and Logback appender, `additivity=false` | Config drift, rollover, file permissions |
| Durable audit requirements | Dedicated audit/event store with guarantees | Integrity, permissions, retention, reconciliation |

There is no single right approach for every architecture. Define **where HTTP events originate**, **the authoritative source for metrics**, **storage destinations**, **correlation keys**, and **security requirements** before enabling more loggers or collectors.

## 17. Checklist and Key Takeaways

- Distinguish access, application, and audit logs by **event semantics**, not just filename.
- Decide the access source per hop and avoid double-counting a single HTTP request.
- Every access event has method, safely handled route/path, status, duration, and a clearly defined timestamp.
- Access logger/appender has a dedicated path; in Logback, additivity is handled.
- Verified that Tomcat configuration applies only to apps actually using Tomcat; know where files are written.
- If emitting access events in a custom filter, handle async, error dispatches, and response completion properly.
- Establish a trusted request/trace ID to join with application logs without copying unvalidated headers verbatim.
- Do not store tokens, cookies, `Authorization`, or bodies by default; control paths and headers.
- Configure separate retention, rotation, view permissions, and ingestion failure alerts as needed.
- Dashboards measure traffic from one consistent hop; applications and gateways can record different HTTP codes.
- Tested normal endpoints, 4xx/5xx, restarts, high traffic, and collector parsers.

**Takeaway:** separating access logs means **independently routing and governing HTTP access events** apart from internal Java operational logs. Access logs tell you **which request went where, its outcome, and its latency at a hop**; application logs help you find **what happened inside**. Keep a shared schema and correlation ID so both streams complement each other during incident investigation.

### References

- [Apache Tomcat — AccessLogValve and patterns](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html#Access_Logging)
- [Spring Boot — Embedded web servers / access logging](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Logback — Architecture and additivity](https://logback.qos.ch/manual/architecture.html)
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
