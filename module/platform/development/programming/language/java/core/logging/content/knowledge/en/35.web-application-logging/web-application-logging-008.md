# Request Body and Logging Risks in Java Web Applications

## 1. Objectives and Real-World Problem

In a web application, the **request body** is the data payload sent by the client with an HTTP request, such as order-creation JSON, login forms, webhook payloads, file uploads, or binary data. While the body can help reproduce bugs, **logging the raw request body** is a high-risk decision: it can expose passwords, access tokens, personal data, payment details, and private content, or exhaust memory/I/O and break stream processing.

Dangerous example:

```java
// Demonstration code in an application with a logger and requestBody variable.
// DO NOT use in production if the body has not been classified as safe.
logger.debug("Incoming body={}", requestBody);
```

When DEBUG is enabled, the log may capture everything the user sends. Even when DEBUG is disabled, computing `requestBody` or `toJson(request)` **may still have executed** before the logger call. If logs are shipped to multiple sinks (console, files, centralized systems, alerts, backups), the blast radius of a leak extends far beyond a single local file.

**Core principle:** normally, **do not log raw request bodies**. Log **metadata and allowlisted fields** such as the HTTP method, route template, status, duration, a system-controlled request ID, measured body size, error code, or business action. If an investigation genuinely requires payload content, use a separate collection mechanism with narrow scope, structured redaction, size limits, and strict access control.

After this lesson, you will understand:
- What types of sensitive data a body can contain and why the DEBUG level is not a security control.
- The impact on **streams, memory, CPU, I/O, latency, DoS, and async operations** when attempting to read/log the body.
- How to log requests safely in Java 17 and Spring MVC/Servlet, along with considerations for WebFlux/streaming.
- The role of allowlisting, masking, redaction, size limits, consent, retention, and fault isolation.
- How to test to ensure the body is truly not written through appenders, exceptions, proxies, or collectors.

## 2. What Is a Request Body, and How Does It Differ from Headers/Query?

An illustrative HTTP request:

```http
POST /api/sessions HTTP/1.1
Host: example.test
Content-Type: application/json
Content-Length: 54

{"username":"alice","password":"demo-secret"}
```

Here, the body is JSON containing `username` and `password`. These values are **dummy data** to illustrate the risk. In a real system, the application may receive:
- `application/json`: objects, arrays, nested fields, long lists.
- `application/x-www-form-urlencoded`: key-value pairs, often including credentials or tokens.
- `multipart/form-data`: form fields plus file uploads.
- `text/plain`, XML, CSV, protobuf, or custom data formats.
- Bodies from webhooks, API calls, GraphQL (query/variables), gRPC over its respective transport, or streaming uploads.

**Not every request has a body.** A GET request typically needs no body; a request may declare `Content-Length: 0` or use chunked transfer encoding. `Content-Type` only indicates the representation format—it does not prove the content is safe. A JSON field named "debug" can still contain a token; a plain text file can contain personal data.

Some risks come from **headers and URL query parameters** rather than the body; they require their own policies. For example, `Authorization`, `Cookie`, signed URLs, and query tokens are not in the body, yet must not be logged indiscriminately either. This lesson focuses on the **body** and its interaction with the logging pipeline, though parallel leakage channels must not be ignored.

## 3. Risk Matrix for Logging Raw Request Bodies

| Risk Category | Concrete Examples | Consequences |
| --- | --- | --- |
| **Authentication secrets** | Passwords, OTPs, refresh tokens, API keys, session secrets, private keys | Account takeover or unauthorized service access if values are still valid |
| **Personal data** | Email, address, profile records, ID numbers, health information | Privacy exposure, exceeding processing purpose, policy violations |
| **Payment information** | Card data, bank accounts, payment details | Increased fraud and compliance risk |
| **Private content** | Messages, documents, uploaded source code, file attachments | Exposure of customer or business data |
| **System overhead** | Large bodies, nested JSON, Base64, multi-GB files | Increased allocation/GC, serialization CPU, bandwidth, and log storage |
| **Stream breakage** | Filter reads `getInputStream()` before the controller | Controller has no remaining data to deserialize |
| **Log injection** | Content containing newlines, control/escape characters | Forged log entries, broken parsers, masked events |
| **Business thread blocking** | Slow logger/encoder/file/network sink | Increased p95/p99 latency, held threads, timeouts |
| **Data duplication** | Console + rolling file + collector + backup | Sensitive data gets extra copies and more readers |
| **Flawed security model** | Redacting only on the dashboard while raw files remain intact | False sense of security; data is still exposed upstream |

**The body is untrusted client-supplied data.** Beyond preventing secret leaks, you must also prevent clients from dictating the size, line count, structure, or content of log fields in ways that degrade system operation.

## 4. Why DEBUG/TRACE Does Not Protect Data

Many projects log payloads at DEBUG expecting them to only be enabled in tests:

```java
// Illustrative integration code, not a recommendation.
logger.debug("Request: " + toJson(requestDto));
logger.trace("Payload: {}", requestDto);
```

Problems:
1. **Log level is a runtime configuration.** An operator may enable DEBUG/TRACE during an incident investigation; older logs or other threads may still have verbose levels enabled.
2. **Arguments may be evaluated eagerly.** `toJson(requestDto)` and string concatenation on the first line execute immediately. Even if the event is discarded, performance still suffers.
3. **Parameterized logging does not mask data.** `{}` only controls formatting; it does not automatically redact `requestDto`.
4. **The `toString()` of a DTO/record/entity may include every field**, including passwords. Generators, Lombok, or Java records can produce object representations unsuitable for logging.
5. **Sinks and collectors may retain copies**, even if the UI dashboard hides them or restricts access.
6. **Exception paths** may log the request differently, even when normal DEBUG calls have been removed.

When diagnostics are needed, **proactively select safe fields** and use event codes/trace IDs. Never define safety as "only when DEBUG is enabled."

## 5. Reading the Request Body Can Break HTTP Processing

### 5.1. The Body Typically Flows Through an Input Stream

In the Servlet API, a controller or framework calls `request.getInputStream()` or `request.getReader()` to consume bytes/characters. The body is normally read as a stream; it is **not an infinite String that can be re-read at will**.

A filter written like this can easily leave downstream components with no body:

```java
// ANTI-PATTERN EXAMPLE ONLY; requires Jakarta Servlet.
// Reading the stream for logging can leave the controller with no data.
byte[] raw = request.getInputStream().readAllBytes();
logger.debug("Body={}", new String(raw, java.nio.charset.StandardCharsets.UTF_8));
chain.doFilter(request, response);
```

This is **code you should not use** because:
- `readAllBytes()` can read the entire payload into the heap with no size limit.
- The stream is consumed; downstream frameworks may encounter an empty body, deserialization errors, or altered behavior.
- `new String(raw, UTF_8)` is inappropriate for binary bodies, other charsets, and multipart payloads.
- The raw body may contain credentials/PII; logging exposes its contents.
- If the request object is wrapped or the container enforces special reading modes, behavior also depends on the implementation.

**Do not add an extra body read solely for logging.** If business logic already deserializes the body, take metadata or approved fields **from the business processing result**. If you need to measure size, use a bounded streaming byte counter and respect the framework's flow rather than cloning the entire payload.

### 5.2. Content-Length Is Not the Actual Number of Bytes Received

In Servlet, `request.getContentLengthLong()` returns the declared length or the length known to the container, or `-1` if unknown. It may not represent the number of bytes actually consumed by the application, especially with chunked transfer encoding, mid-stream truncation, decompression, or intermediate middleware.

If logging `body_bytes`, clearly specify the source:
- `declared_content_length`: the declared length or length observed from metadata; may be `-1` or not fully trustworthy.
- `received_body_bytes`: the actual number of bytes counted by a reliable streaming counter during processing.
- `decoded_body_bytes`: the number of bytes after decompression/transformation if the framework performs that step.

Do not re-read the stream just to measure it. Distinguish byte size from `String.length()`: in Java, `String.length()` counts UTF-16 code units, not HTTP wire bytes.

### 5.3. The Body May Be Partially Read or Unread

When a request is rejected early (authentication, authorization, rate limiting, header validation), the application may **never read the body**. A logger running at the end of the filter chain should not assume it can reconstruct the full body. Attempting to drain the remaining stream just to "log everything" adds unnecessary overhead and can prolong handling of a malicious request.

When a client closes the connection mid-stream, the body may only be partially received. Audit logs should accurately reflect **received/consumed** bytes when actual measurements exist, rather than assuming the full payload arrived based solely on `Content-Length`.

## 6. Standalone Java 17 Example: Log Metadata Only, Never the Payload

The pure JDK 17 example below simulates an HTTP JSON body containing a **fake** password and access token. Assume the application has already received those bytes for business processing; the logging function **does not read further, re-deserialize, or log the body**. Instead, it logs an event with the method, route template, status, request ID, and known byte length.

Create `SafeRequestBodyLoggingDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SafeRequestBodyLoggingDemo {
    private static final class CaptureHandler extends Handler {
        private final StringBuilder captured = new StringBuilder();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                captured.append(record.getMessage()).append('\n');
            }
        }

        @Override
        public void flush() {
            // Keep logs only in memory for this demo.
        }

        @Override
        public void close() {
            flush();
        }

        String text() {
            return captured.toString();
        }
    }

    private static void logRequest(
            Logger logger, String method, String route,
            String requestId, int status, long receivedBytes) {
        // All fields are controlled/normalized by the application; NO raw body.
        logger.info("event=http_request"
                + " method=" + method
                + " route=" + route
                + " requestId=" + requestId
                + " status=" + status
                + " receivedBytes=" + receivedBytes
                + " bodyLogged=false");
    }

    public static void main(String[] args) {
        String body =
                "{\"password\":\"fake-pass\",\"access_token\":\"fake-token\"}";
        byte[] requestBytes = body.getBytes(StandardCharsets.UTF_8);

        Logger logger = Logger.getLogger("lesson.web.body.safe");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        CaptureHandler handler = new CaptureHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            // Example using the byte count already obtained from receiving/processing the body.
            logRequest(logger, "POST", "/sessions", "req-42",
                    401, requestBytes.length);

            String emittedLog = handler.text();
            System.out.print(emittedLog);

            boolean secretLeaked = emittedLog.contains("fake-pass")
                    || emittedLog.contains("fake-token");
            System.out.println("secretLeaked=" + secretLeaked);
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Compile and run:

```bash
javac SafeRequestBodyLoggingDemo.java
java SafeRequestBodyLoggingDemo
```

**Exact stdout** on JDK 17, in a fresh JVM with no external components interfering with the demo logger:

```text
event=http_request method=POST route=/sessions requestId=req-42 status=401 receivedBytes=52 bodyLogged=false
secretLeaked=false
```

Analysis:
1. The JSON payload contains two **simulated** secret values for illustration only. Because all characters in the JSON string are ASCII, `requestBytes.length=52`; for Unicode payloads, measure actual bytes rather than using `body.length()`.
2. `logRequest` accepts a byte count and application-controlled metadata. It **never receives the raw body**, so it cannot accidentally call `toString()` or re-serialize an object containing credentials.
3. `CaptureHandler` simply stores messages for assertion without adding timestamps or printing to stderr; `setUseParentHandlers(false)` prevents the root handler from emitting a duplicate record.
4. `secretLeaked=false` proves **only that the log emitted by this example** does not contain the two dummy strings. It **does not prove that the entire application, HTTP server, gateway, and collector are free from body logging**.
5. The code uses a single thread for demonstration; `StringBuilder` inside the handler is not thread-safe for concurrent application logging. In production, use a framework-managed backend and lifecycle.

**Note:** Body bytes appear in this code only because business logic already received the body. This example **does not recommend reading `getInputStream()` just to obtain bytes for logging**. Real-world logging APIs should accept normalized DTOs/events, not raw requests.

## 7. Designing Request Logs: Allowlist First, Redaction Second

A useful request log rarely needs the body content. Example:

```json
{
  "event": "http_request",
  "method": "POST",
  "route": "/orders",
  "status": 201,
  "duration_ms": 38,
  "request_id": "req-42",
  "received_body_bytes": 284,
  "body_logged": false
}
```

This is **illustrative data**, not output observed from a live system. A real schema should explicitly define:
- `method`: HTTP method validated/canonicalized by the framework.
- `route`: **route template** (`/orders/{id}`), avoiding raw URLs that may contain IDs or secrets in the path/query.
- `status` and `duration_ms`: measured from actual request processing.
- `request_id`: server-generated or validated/length-bounded; never blindly trust a client-supplied header.
- `received_body_bytes`: used only when an actual counter exists; otherwise omit it or use `declared_content_length` with an accurate field name.
- `body_logged`: reflects the logging policy at that point, not a guarantee that other components did not log the body.
- `event_code`, `validation_error_code`, `resource_type`: choose error/business codes that **do not contain free-form user input**.

**Allowlisting** means explicitly defining permitted fields before constructing the event. Conversely, blocklisting a few sensitive fields from an entire JSON payload often misses new fields, deeply nested JSON, arrays, aliases, tokens embedded in strings, or differently encoded data.

For business events, instead of logging the entire DTO:

```java
// SLF4J integration snippet. orderId/status have been validated,
// and are not credentials or sensitive personal data.
logger.info("event=order_created orderId={} status={} itemCount={}",
        orderId, "CREATED", itemCount);
```

If `orderId` can identify a user or sensitive order, apply appropriate access and retention policies. **Not every ID is harmless.** For a login endpoint, you can log a `LOGIN_DENIED` event code and a normalized reason without needing the username or password.

## 8. Spring MVC/Servlet: Where Should Logging Live?

### 8.1. Filters/Interceptors Do Not Need to Read the Body to Log Metadata

In a Spring MVC or Servlet application, a filter can observe the method and status; the route template can be retrieved from framework attributes after handler mapping runs, when available. This is an **integration snippet** illustrating Spring Web MVC/Jakarta Servlet, not a standalone class:

```java
// Inside a Servlet Filter, after chain.doFilter(request, response).
// HandlerMapping belongs to spring-webmvc; the attribute may be absent if unmatched.
Object matchedRoute = request.getAttribute(
        org.springframework.web.servlet.HandlerMapping
                .BEST_MATCHING_PATTERN_ATTRIBUTE);

String route = matchedRoute instanceof String s ? s : "UNMATCHED";
long declaredLength = request.getContentLengthLong();

logger.info("event=http_request method={} route={} status={} "
                + "declaredContentLength={} bodyLogged=false",
        request.getMethod(), route, response.getStatus(), declaredLength);
```

Important notes:
- `declaredContentLength` **is not guaranteed to equal received bytes**; `-1` means unknown.
- `UNMATCHED` can occur if the request is blocked before reaching a controller or has no mapping; do not fall back to logging the raw URL/query just to "fill in" the field.
- If the filter logs unauthenticated requests, treat client-supplied fields as untrusted and sanitize/bound them before writing.
- If you only need method/route/status, **you do not need** `ContentCachingRequestWrapper` and do not need to read `getInputStream()`.
- Place logging in an appropriate `finally` block when exception paths must also be logged, but understand how status/exceptions are handled by exception resolvers and the servlet container; the status when the filter returns does not always reflect the final response sent.
- When using asynchronous Servlet processing, the filter chain may return before the request actually completes; attach instrumentation to the appropriate lifecycle (`AsyncListener` or framework hooks) to measure the final duration/outcome.

### 8.2. ContentCachingRequestWrapper Is Not a "Harmless Body Reader"

Spring Web provides `ContentCachingRequestWrapper` to retain a copy of **the bytes that have been consumed through the wrapper**, up to a cache limit. It is useful in certain controlled integrations, but:

1. **The wrapper does not automatically read the entire body upon instantiation.** `getContentAsByteArray()` can be empty if downstream has not read the stream, or contain only the portion read so far.
2. The cache may have a **size limit** and hold only part of the body. Do not treat the cache as a complete copy of the payload.
3. If a filter reads the stream early, **downstream may not be able to re-read it** as expected. Never assume wrapping a request automatically makes it repeatable in all scenarios.
4. Caching **increases heap usage**. Even with an 8 KiB cache limit, high traffic and concurrent requests can accumulate significant memory; large requests and binary bodies require separate evaluation.
5. The cache is a copy of sensitive data that may appear in heap dumps/tracing and can easily be logged raw by another code path.
6. Multipart, form parsing, async dispatch, and error paths each have distinct behavior; test against your actual stack and version.

If there is no legitimate business need to cache the body, **do not add a wrapper just to log it**. If a special diagnostic requirement exists, explicitly define the endpoint, data classification, limits, structured masking, and how copies are cleared or minimized.

### 8.3. RequestBodyAdvice and DTOs

Spring MVC offers hooks around reading/converting the body, such as `RequestBodyAdvice`. They can inspect data already parsed into a DTO (depending on the converter and controller), allowing you to pick **specific permitted business fields** instead of copying raw bytes.

However, seeing the DTO **does not make the DTO inherently safe**. Logging `dto.toString()` or serializing the entire DTO can still leak tokens or passwords. Map it to an `AuditView`/event schema containing only allowed fields, or emit events from business logic after validation.

For JSON parse errors occurring before the controller, do not rely on the raw exception message to reconstruct the body. Log an error code, the location/type of issue when considered safe, a request ID, and relevant metrics; avoid dumping the full body into exceptions or debug diagnostics.

## 9. Reactive WebFlux, Streaming, and File Uploads

### 9.1. WebFlux Bodies Are Asynchronous Streams

In Spring WebFlux/Reactor, the body is typically represented by a publisher and `DataBuffer`. If a logging filter subscribes to the body just to inspect data, it can **consume the stream**, breaking the real processing subscriber or altering backpressure. Joining the body via `DataBufferUtils.join` scales memory usage with payload size; improper buffer management can also cause leaks in pooled buffer configurations.

Avoid:
- Subscribing separately to the body inside a logging filter.
- Calling `collectList()` or joining large uploads just to print logs.
- Holding a `DataBuffer` beyond its valid lifecycle or forgetting to release it per contract.
- Calling `block()` on an event-loop thread just to log.

If you need to count bytes, apply a decorator/metrics hook that **does not alter consumption/backpressure**, bounds resources, and follows the `DataBuffer` lifecycle of your stack. If your goal is simply logging method, route, status, duration, and trace ID, do it at the observation/filter layer without touching the body.

### 9.2. Multipart and Binary Bodies

`multipart/form-data` can contain text fields **and** binary files. Printing raw multipart payloads floods logs with filenames, uploaded content, boundaries, sensitive form fields, or MBs/GBs of data.

Log approved metadata when permitted:
- Allowlisted field names, not all fields.
- File count, measured size, validated media type, result code.
- Reference ID of the stored object, provided it does not leak personal information.
- Do not log client-supplied filenames by default: they may contain paths, emails/PII, or control characters.
- Do not extract byte slices or file headers as a "log preview."

Protobuf, PDFs, images, ZIPs, and compressed bodies should never be blindly converted to `String`. `Content-Encoding: gzip` also causes wire bytes to differ from decompressed bytes. If the decompressed body is vastly larger than the transmitted payload, both deserialization and auxiliary logging can be abused to exhaust resources.

### 9.3. GraphQL and Webhooks

- **GraphQL:** JSON bodies typically contain `query`, `operationName`, and `variables`. Variables can hold passwords, tokens, or private data. Log the validated operation name and error codes; do not log full queries or variables by default.
- **Webhooks:** Bodies may contain customer data, signatures, or private event payloads. If HMAC signature verification is needed, process bytes per contract at the boundary; **do not log the raw body or signing secret**. For diagnostics, log the provider ID, validated event type, and signature verification outcome.
- **Large streaming requests:** Favor counters and receive/validation states over body snapshots. Never buffer an entire stream for a single log event.

## 10. Redaction and Masking: Where to Place Them and How to Control Them

### 10.1. Convenient-Looking Solutions That Fall Short

For example, logging the body after regex replacement:

```java
// Illustrative anti-pattern code. This is NOT a reliable redactor.
String safe = body.replaceAll(
        "\"password\"\\s*:\\s*\"[^\"]*\"",
        "\"password\":\"[REDACTED]\"");
logger.debug("body={}", safe);
```

Risks:
- JSON syntax supports nesting, escapes, unicode escapes, arrays, and varied formatting. Simple regexes easily miss matches.
- Sensitive fields may have other names: `pwd`, `credentials`, `token`, `secret`, `auth`, or appear inside strings/URLs.
- The body might not be JSON—it could be binary, multipart, or XML.
- Regex matching and copying the body still consume CPU and heap.
- A misconfiguration or exception can accidentally log **`body` before redaction**.
- Redacting only the message text can miss structured fields, MDC, exceptions, and other appenders.

Better approach: **do not pass raw bodies into the logging API**. For content that genuinely must be observed, parse it with a media-type-appropriate safe parser (already used by business logic), extract only allowlisted fields, and pass data through a dedicated `SafeLogView`/DTO.

### 10.2. Structured Redaction

Suppose a signup request DTO contains `email`, `password`, `phone`, and `campaignCode`. If you only need to track the campaign source, an audit view might look like:

```json
{
  "event": "signup_attempt",
  "campaign_code": "CAMPAIGN_PUBLIC",
  "validation_result": "DENIED",
  "body_logged": false
}
```

Do not put `email`/`password`/`phone` into the log just to mask them if they are unnecessary. Even `campaign_code` must be bounded and validated, because a field intended as a campaign code can still receive arbitrary client input. Secret fields should be **omitted** from the schema rather than mechanically rendered as `[REDACTED]`.

### 10.3. Appender/Collector Redaction as Defense in Depth

In Logback or Log4j 2, you can configure layouts/encoders or custom converters/filters to mask data. These help when a component inadvertently emits an unsafe message, but:
- Appender A and Appender B may use **different encoders**; every destination must be verified.
- Raw events can sit in an async queue or heap before reaching the encoder.
- Stack traces, argument arrays, MDC, markers, and key-value fields may require separate handling.
- Collectors may retain raw data before indexing/redaction steps.
- Logs forwarded to stdout/console before dashboard masking may still persist in runtime logs.

Therefore, treat downstream redaction as a **second line of defense**, not a license to "log every body."

## 11. Data Limits, Cost, and DoS Resilience

### 11.1. Why Even a "Small" Snapshot Can Cause Harm

Suppose each request snapshot is capped at 8 KiB. Under high concurrency, retained heap data can quickly reach several megabytes or more—not counting copies created during `byte[]`-to-`String` conversion, formatting, JSON encoding, queue entries, and network buffers. If you capture and log the full body before truncating, a trailing limit does not prevent the initial allocation.

**Size limits are a resource control, not a secret-protection mechanism.** A short access token can sit within the very first 100 bytes. Never claim that "logging only the first 1 KiB" is safe.

### 11.2. Recommended Limits

| Limit | Purpose |
| --- | --- |
| Max request body size at ingress/server | Reject oversized payloads before processing |
| Max decoded/decompressed size | Prevent decompression bombs |
| Max JSON nesting depth / collection count | Prevent structurally expensive parsing/CPU attacks |
| Max string/field length in logs | Prevent a single value from breaking log streams or indexes |
| Max diagnostic snapshot on valid exceptions | Bound memory/bytes **after** data is classified and handled safely |
| Logging queue size | Control memory, backpressure, and drops |
| Rate limiting and intentional sampling | Mitigate log storms without dropping mandatory audits |
| Retention, quota, rotation | Control storage and data lifecycle |

When applying sampling—especially for authentication failures or security events—balance diagnostic signal against operational capacity. Sampling does not replace secret prevention: a sampled log can still leak sensitive data.

### 11.3. Async Appenders Do Not Eliminate Risk

Async logging reduces the time business threads spend waiting on files or networks, but:
- Eager `toJson(body)` still runs on the caller thread before enqueuing.
- Log events may hold references or snapshots of the body in the heap.
- A full queue can block producers, drop events, or spike latency.
- The worker thread's encoder still consumes CPU/heap for serialization.
- Shutdowns or crashes can lose unflushed events; files/collectors may still store secrets if emitted.

Measure end-to-end: CPU, GC, allocated bytes, p95/p99 latency, queue depth, dropped log events, bytes logged, collector cost, and flush duration on shutdown.

## 12. Errors, Exceptions, and Indirect Body Leakage

Even when a controller never calls `logger.debug("body")`, body content can leak into logs through:

1. **Validation errors**: exception messages containing the raw rejected field value.
2. **JSON parsing errors**: libraries or custom error wrappers embedding a payload snippet near the error offset.
3. **HTTP client diagnostics**: logging raw outbound request or response bodies during retries/timeouts.
4. **Framework debug/wire logs**: interceptors, filters, gateways, or proxies logging request bodies when enabled.
5. **Custom exceptions**: `throw new IllegalArgumentException("Bad payload: " + rawBody)`.
6. **AOP/tracing**: automatically logging controller method arguments, including `@RequestBody` DTOs.
7. **`toString()`/records/Lombok**: a single log line printing an entire object exposes every field.
8. **Security audits**: logging raw login payloads, OTPs, or tokens to investigate failures.
9. **MDC/ThreadContext**: storing body data in context, which the encoder then attaches to every event.
10. **Error pages/incident tickets**: copy-pasting raw payloads from logs into systems with broader visibility.

Inspect **active logging framework configurations**, effective levels per namespace, appenders/layouts, HTTP access logging, reverse proxies, API gateways, and collectors. Never just grep for logger calls in controllers and conclude there is no body leakage.

**For exceptions**, retain the error class, normalized reason code, route template, and request ID; avoid concatenating raw bodies or raw rejected values into messages. For severe errors requiring stack traces, evaluate whether exception messages or causes might contain secrets before writing to broadly accessible sinks.

## 13. Controlled Diagnostic Strategy When Payloads Are Truly Needed

In rare cases, capturing partial data is necessary to reproduce an integration bug. Instead of enabling "log all request bodies" system-wide, design a controlled workflow:

1. **Clear purpose, scope, and owner.** For example, only the `/vendor/callback` integration endpoint in staging, never all requests.
2. **Data classification and policy enforcement before collection.** Never use real payloads containing credentials, cards, or personal data if the issue can be reproduced with synthetic data.
3. **Post-parse allowlist**: capture only fields essential for diagnostics; never serialize the entire object graph.
4. **Enforce limits and expiration.** Bounded size, sampling/targeted requests only, time-boxed feature flags, and a rollback mechanism.
5. **Separate storage channel** if stricter protection is needed than standard application logs; apply encryption, restricted access, viewer auditing, short retention, and a deletion process.
6. **Never copy raw bodies into incident tickets or chat.** Use dummy data, request IDs, error codes, or controlled references only.
7. **Disable diagnostics after the incident**, verify where data still resides, and ensure no forgotten log paths remain.
8. **Verify the entire pipeline** with canary data beforehand, including console, secondary appenders, and collectors.

Never use this mechanism as a "backdoor" to bypass no-secret-logging policies. For valid credentials, no debug privilege justifies logging raw tokens without proper controls.

## 14. Testing: Proving Metadata Is Logged Without Leaking the Body

### 14.1. Canary Tests with Dummy Data

Send test requests containing markers that are **not real secrets**, such as:

```json
{
  "email": "demo-user@example.test",
  "password": "CANARY_PASSWORD_NOT_REAL",
  "access_token": "CANARY_ACCESS_TOKEN_NOT_REAL",
  "notes": "line1\nline2"
}
```

Trigger:
- Successful requests and validation failures.
- JSON parse exceptions, missing required fields, and converter errors.
- Login/password-reset endpoints.
- HTTP 401/403/500 responses.
- Multipart uploads and size-limited large bodies.
- Chunked requests, client disconnects, and partially read streams.
- Webhooks, GraphQL variables, and outbound HTTP retries where applicable.
- INFO, DEBUG, and TRACE modes **in test/staging** (never enable broadly in production).

Verify that canary values **do not appear** in log messages, structured fields, MDC, exception text, log files, console output, reverse proxies/gateways, log collectors, backups, or alerts. Also check for JSON-escaped or URL-encoded variants if the integration performs those transformations.

A test that only checks `message` is insufficient if the encoder can emit an independent structured `payload` field.

### 14.2. Verifying the Body Stream Remains Intact

Compare behavior with the logging filter **enabled vs. disabled**:
1. Controllers still read the full body and bind DTOs correctly.
2. Validation returns the expected error codes.
3. Empty, multi-MB, chunked, multipart, and streaming request bodies retain identical semantics.
4. No `IllegalStateException` occurs from misusing `getReader()`/`getInputStream()`.
5. No memory leaks or unbounded heap growth appear under concurrent load.
6. WebFlux suffers no double-subscription or backpressure loss.
7. Timeouts and async dispatches log consistent request outcomes without unintentional duplicate events.

For Spring MVC integrations, watch out for cases where downstream **does not read the body**: a caching wrapper may return an empty byte array, which does not prove the actual request had no body.

### 14.3. Performance and Resilience Testing

Measure throughput, p50/p95/p99 latency, CPU/GC, allocations, emitted log bytes, dropped records, and collector bandwidth. A 1 MiB request body should never turn into a 1 MiB log message (or multiple 1 MiB copies across appenders) simply because DEBUG is enabled.

If using async appenders, also measure queue depth and flush behavior. If a log sink fails or slows down, business logic must follow a clear policy; logging should never cause an outage for an entire endpoint. Mandatory audit logs may have separate durability guarantees and must be designed independently.

## 15. When a Sensitive Body Has Already Leaked into Logs

Handle this as a security/privacy incident rather than a simple one-line code fix:

1. **Stop ongoing exposure:** halt raw body logging, disable related wire/debug logging, fix the controller/filter/exception path, and deploy the change.
2. **Determine scope:** body types, timeframe, endpoints, service instances, and storage locations (console, files, collectors, exports, dashboards, backups, alerts).
3. **Assess credentials:** if valid passwords, tokens, API keys, or cookies/sessions were exposed, revoke/rotate/reset them per policy. Deleting logs **does not make an exposed secret safe again**.
4. **Contain and remediate stored data:** restrict access, execute purge/quarantine/retention procedures per applicable rules; account for downstream copies and backups.
5. **Investigate access and notification obligations:** coordinate with security, privacy, and operations teams; do not assume all data types carry identical legal requirements.
6. **Prevent recurrence:** add allowlist schemas, canary tests, code reviews for loggers touching `@RequestBody`/headers/DTOs/exceptions, and monitor framework/config changes.

**Never repost the real payload** in tickets, chat, or bug descriptions. Use dummy data or protected incident identifiers.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `logger.debug("body={}", rawBody)` | Leaks when DEBUG is on; logs may reach multiple sinks | Never log the body; log metadata/allowlisted fields |
| Calling `toJson(dto)` before the logger call | Serializes even when the level is off; may create copies of secrets | Do not serialize sensitive DTOs for logging |
| Reading `readAllBytes()` in a filter to inspect payload | Consumes stream, spikes heap, breaks controller | Do not read the body for logging; use metadata/fields from business logic |
| Treating `ContentCachingRequestWrapper` as "body is always re-readable" | Cache only holds consumed bytes and is size-limited | Understand the lifecycle; test on your Spring/Servlet stack |
| Truncating to the first 1 KiB and calling it safe | Secrets can sit right at the beginning | Apply allowlisting/structured redaction before size limits |
| Regex-masking `password` then logging the whole JSON | Misses tokens, nested fields, and alternative encodings | Do not log raw; parse and select safe fields |
| Logging entire multipart/file uploads | Captures huge, private, or binary data | Log only approved metadata |
| Subscribing again in WebFlux to log | Double consumption, backpressure/`DataBuffer` errors | Use lifecycle-compliant observation/decorators; never dump the body |
| Treating `Content-Length` as received bytes | Can be -1, wrong, chunked, or transformed | Distinguish declared vs. measured bytes |
| Using the raw URL as the route | Query/path may carry tokens/PII | Use route templates |
| Printing full parse-error exceptions | Message/cause may include payload fragments | Use error codes, request IDs, and controlled metadata |
| Redacting only on the dashboard | Raw body may already sit in stdout/files/collectors | Eliminate the body at the source; test the full pipeline |
| Leaving memory/cache or logging queues unbounded | GC pressure, OOM, backpressure, timeouts | Bound sizes, queues, rates, and retention |
| Enabling TRACE across all of production to debug | Massive volume and exposure surface | Use staging, controlled sampling, and narrow diagnostics |
| Putting the body into MDC/ThreadContext | Every event in that scope may inherit the body | Never place bodies in MDC; clean up context |
| Blindly trusting arbitrary request IDs/headers | Log injection, spoofing, mixed traces | Generate/validate/truncate correlation IDs |

## 17. Practice Exercises and Answers

**Exercise 1 — Body stream.** A Servlet filter calls `request.getInputStream().readAllBytes()` and forwards the original request to a controller for `@RequestBody` deserialization. What is the main risk?

**Answer:** The stream may already be consumed, leaving the controller without the expected bytes; the code also creates an unbounded copy in memory and risks exposing the payload. Never read the stream solely for logging.

**Exercise 2 — 4 KiB threshold.** A system logs only the first 4 KiB of a JSON body. Can we claim passwords/tokens will not leak?

**Answer:** No. Secrets are typically short and can appear within the opening bytes. Size limits only reduce resource usage/volume; the primary control is **not logging the body** or selecting allowlisted fields after safe processing.

**Exercise 3 — Spring wrapper.** `ContentCachingRequestWrapper.getContentAsByteArray()` returns empty in a filter running after the chain. Does that guarantee the request had no body?

**Answer:** No. Downstream might not have read the body, the request may have been rejected early, or the cache may not have captured bytes yet. The wrapper does not read the body upon creation.

**Exercise 4 — Reactive.** In WebFlux, should you independently subscribe to `Flux<DataBuffer>` to log it and let the controller subscribe again?

**Answer:** No. The body is a stream governed by Reactor/Netty contracts; double-subscribing or mishandling buffers can corrupt data or break backpressure. Prefer metadata, or use a lifecycle-compliant decorator if instrumentation is needed.

**Exercise 5 — Structured logging.** Does replacing `logger.debug("body={}", body)` with `logger.atDebug().addKeyValue("body", body).log(...)` make logging the body safe?

**Answer:** No. Structured JSON only changes the event format; the encoder still serializes the `body` field's value. You must remove that field or replace it with metadata/a safe view.

**Exercise 6 — Secret exposure.** If a real refresh token was written to the console and collector, is fixing the code to stop logging it sufficient?

**Answer:** No. You must assess the scope, revoke the token per policy, manage retained copies, and follow incident response procedures; never repost the token during investigation.

## 18. Implementation Checklist

Before enabling request logging in a Java web application, confirm:

1. **Never log raw request bodies** by default in controllers, filters, interceptors, AOP, exception handlers, HTTP clients, gateways, or collectors.
2. Method, route, status, duration, request ID, body size, and event codes are sourced appropriately without leaking query/body secrets.
3. The body stream **is not extra-read or consumed** solely for logging; controllers/handlers continue to work properly.
4. If using Spring `ContentCachingRequestWrapper`, you understand the cache only holds consumed bytes up to a limit and is not an arbitrary body-rereading API.
5. For WebFlux/streaming, consumption, backpressure, `DataBuffer` lifecycle, and memory limits are preserved.
6. Multipart, file uploads, and binary/compressed bodies are governed by separate policies and never blindly converted to `String`.
7. Entire DTOs/records/entities are never serialized into logs, and raw bodies are never placed in MDC, structured fields, or exception messages.
8. Any special diagnostic collection has an approved **allowlist, purpose, limits, expiration, and access control**; downstream redaction is strictly defense in depth.
9. All sinks (console, files, secondary appenders, collectors, alerts, backups) are tested with dummy canary data, including DEBUG/TRACE and error paths.
10. Latency/CPU/heap/GC/log volume/queue metrics are tested, and logging failures are monitored so they cannot disproportionately impact business traffic.
11. An incident response process exists for when sensitive payloads leak into logs, including credential revocation/rotation and retention controls.

**Conclusion:** A request body can be large, untrusted, and highly sensitive. Logging raw bodies risks exposing secrets, consuming streams, inflating costs, and causing operational outages. In Java web applications, the sustainable approach is to **exclude the body from log events**, log only metadata and allowlisted fields, respect the request-processing lifecycle, and verify the entire pipeline through testing and real-world observation.