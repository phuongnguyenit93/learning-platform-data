# Redacting Sensitive Data in Logs, Traces, and Error Messages

Logs, distributed traces, and error messages help operations teams understand which requests a Java serverless function received, which services they traversed, and where failures occurred. Yet those same channels can leak access tokens, cookies, connection strings, personal data, message contents, or internal system details. A single log line is often replicated across many destinations—log aggregators, dashboards, alerts, tickets, and analytics systems; a trace may be shared across multiple teams or observability vendors.

Therefore, telemetry security must be designed directly into the application. The goal is to retain enough information to investigate issues and measure reliability while collecting only necessary data, restricting who can view it, and controlling retention. Stripping passwords from a few log statements is not enough if frameworks automatically log headers, exception messages, request bodies, or span attributes.

In the **CLOUD_SERVERLESS** module, learners build Java functions triggered by HTTP, messages, or events and handle access control, state, retries, idempotency, cold starts, scaling, and cost. This lesson focuses on protecting sensitive data across logs, traces, and error responses from functions and the services they call.

## 1. Why can telemetry become a data leak channel?

A single request moving through a serverless system can generate many records:

- API Gateway writes access logs and partial request metadata.
- The runtime logs invocation IDs, durations, memory usage, and exceptions.
- The application emits business logs.
- OpenTelemetry emits spans and events for each dependency.
- HTTP clients or SDKs log requests/responses when debug logging is enabled.
- Queue consumers log message metadata, retry counts, and dead-letter reasons.
- Error handlers return messages to clients.
- Alerting systems copy log snippets or exceptions into emails, chat messages, or tickets.

A sensitive value can be copied into multiple systems that developers never see directly in source code. For example, an HTTP client exception can contain a full URL with query strings; a database error can contain SQL or schema names; a webhook can contain emails and addresses in its payload.

Telemetry typically has broader access permissions than business databases because many engineers need visibility for production support. If sensitive data enters telemetry, the audience able to read that data expands, and its retention period may differ from database policies.

~~~mermaid
flowchart TD
    A[HTTP request / queue message] --> B[Java function]
    B --> C[Application logs]
    B --> D[OpenTelemetry spans]
    B --> E[Exception handler]
    C --> F[Log platform]
    D --> G[Trace backend]
    E --> H[Client error response]
    F --> I[Search / alert / ticket]
    G --> I
    H --> J[Client and support record]
~~~

Logs and traces are data stores that must be protected. Error responses are also public application outputs and must be designed not to reveal internal details.

## 2. Classify data before logging

Before choosing which fields to log, classify data by sensitivity level and intended purpose.

| Data category | Examples | Telemetry handling |
|---|---|---|
| Public | Service name, public API version | Safe to log if needed |
| Operational metadata | Function name, route template, status code, duration, region | Log via allowlist |
| Internal identifiers | Invocation ID, correlation ID, resource ID | Log only when needed; control linkability |
| Personal data | Email, phone number, address, IP, user ID | Avoid logging; if needed, minimize or pseudonymize |
| Authentication data | Passwords, access tokens, refresh tokens, cookies, API keys | Never log |
| Financial/regulated data | Card numbers, account numbers, sensitive records | Never log payloads; log only outcomes and safe reference codes |
| Infrastructure secrets | Connection strings, private keys, SAS/presigned URLs | Never log |
| Business payloads | Order contents, webhook bodies, message bodies | Log minimal metadata only |

Classification must cover user-submitted data, system-generated data, and provider-injected data. A header such as X-Forwarded-For or a field inside an event can contain identifying information even when its field name does not suggest it.

Sensitive data is not limited to passwords. A user ID or tenant ID can correlate a person's activity; a request path can contain an email or order ID; a query string can contain a reset token; a trace ID can link multiple actions; an exception message can include private hostnames or input values. Never assume a field is safe simply because it is not a password.

## 3. Data minimization and allowlists

The most reliable way to prevent sensitive logging is to keep sensitive data out of telemetry from the start. Log only fields with a clear operational purpose.

An allowlist defines permitted fields, for example:

- service name, function name, and deployment version.
- Platform-assigned invocation ID or request ID.
- HTTP method, route template, status code, and duration.
- Stable error codes.
- Event type, schema version, and queue name.
- Region and dependency name.

Denylists try to enumerate fields to exclude, such as password, token, and cookie. Denylists easily miss newly added field names, nested payloads, or secrets embedded inside URLs. Therefore, use an allowlist as your primary defense; denylists and secret scanners act as secondary safeguards.

Never log entire objects simply because the logger can serialize them:

~~~java
// Unsafe: object may contain email, tokens, addresses, or payment data.
logger.info("Request received: {}", request);
~~~

Instead, log explicitly selected operational fields:

~~~java
logger.info(
    "order request accepted: requestId={}, route={}, method={}",
    safeRequestId,
    "/orders",
    "POST"
);
~~~

If you need to know the request type, log an enum or schema version instead of the raw body. If you need to reference a record, prefer a random reference ID or dedicated support identifier.

Prefer request IDs generated by a trusted gateway or runtime. If the system accepts a correlation ID from a client, validate its format, bound its length, and replace invalid values with an internal ID; never treat a client-supplied ID as a verified identity.

## 4. Structured logging in Java

Structured logging emits logs as structured fields, typically JSON, rather than concatenating free-form strings. Structure simplifies querying, filtering, and dashboards while creating an explicit checkpoint for which fields may appear.

Example JSON event:

~~~json
{
  "timestamp": "2026-11-17T10:15:30Z",
  "level": "INFO",
  "service": "orders-function",
  "function": "CreateOrder",
  "request_id": "req-7f2c",
  "route": "/orders",
  "method": "POST",
  "status_code": 202,
  "duration_ms": 34,
  "event": "order_request_accepted"
}
~~~

This example contains metadata only. No request body, Authorization header, cookie, email, or customer address is present.

### Using SLF4J with safe fields

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderFunction {
    private static final Logger log =
            LoggerFactory.getLogger(OrderFunction.class);

    public Response handle(Request request) {
        String requestId = safeRequestId(request.requestId());

        log.info(
            "request accepted request_id={} route={} method={}",
            requestId,
            "/orders",
            "POST"
        );

        return process(request);
    }

    private static String safeRequestId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,64}")) {
            return "unavailable";
        }
        return value;
    }
}
~~~

SLF4J placeholders avoid manual string concatenation, but do not automatically redact data. Passing a sensitive object to a placeholder still calls toString() and logs its full contents.

### Preventing log injection

When logging client-controlled values, attackers can inject newlines or control characters to forge log entries and mislead investigations. A standard structured JSON encoder escapes characters per format, yet applications should still bound lengths and strip unnecessary control characters.

~~~java
static String safeSingleLine(String value, int maxLength) {
    if (value == null) {
        return "unavailable";
    }

    String normalized = value
            .replace('\r', ' ')
            .replace('\n', ' ')
            .replace('\t', ' ');

    StringBuilder result = new StringBuilder();
    normalized.codePoints()
            .filter(cp -> !Character.isISOControl(cp))
            .limit(maxLength)
            .forEach(result::appendCodePoint);

    return result.toString();
}
~~~

This helper only sanitizes a short text value. Never use it to turn arbitrary payloads into log-safe data; payloads must be excluded from logs or handled under a dedicated schema.

## 5. Never log headers, query strings, or full URLs

HTTP requests can carry secrets in many places:

- Authorization bearer tokens.
- Cookie and Set-Cookie headers.
- X-Api-Key or custom application headers.
- Query parameters such as token, code, sig, or password.
- Object storage signed URLs.
- URLs containing usernames/passwords or credential query parameters.

A full URL sometimes holds a SAS token, presigned signature, or password-reset token. Consequently, never log request URLs with query strings by default.

Log route templates and methods instead:

~~~text
method=GET
route=/customers/{customerId}/orders
status=200
~~~

Avoid logging raw URLs containing path identifiers or query tokens. If query parameters must be debugged, log only allowlisted parameter names and omit sensitive values. Never log all headers and then try to mask a few with regexes.

Forwarded headers such as X-Forwarded-For, Forwarded, and X-Real-IP can be spoofed by clients if requests bypass trusted proxies or proxies fail to overwrite them. Never treat them as verified identity. If IPs are needed for security telemetry, read them from trusted gateway metadata, normalize along the proxy chain, and apply privacy/retention policies.

## 6. Masking, redaction, and pseudonymization

Three techniques are commonly used:

- **Masking:** replacing part of a value so viewers see only a portion, e.g., ***@example.com.
- **Redaction:** removing the value completely and replacing it with a marker such as [REDACTED].
- **Pseudonymization:** replacing an identifier with a stable surrogate so records can be linked without storing the original identifier directly.

Redaction suits tokens, passwords, cookies, and secrets. Masking is appropriate only when the remaining portion does not expose identity beyond approved purposes. Pseudonymization is useful when investigating a sequence of events for the same subject without logging real user IDs or emails.

### Hashing is not anonymization

Hashing an email or phone number with SHA-256 does not automatically anonymize it. Attackers can run dictionary attacks over common values and compare hashes. When correlation is needed, use HMAC with a dedicated managed secret key that supports versioning and rotation:

~~~java
String pseudonym = hmacSha256(activeKey, normalizedCustomerId);
~~~

This is pseudocode: activeKey must come from a secret manager or KMS-backed mechanism; never hardcode keys in source or logs. Do not reuse the same key across unrelated purposes. When stable cross-request correlation is unnecessary, generating a random per-request reference ID reduces linkability across activities.

## 7. Building a safe logging wrapper

A practical pattern is providing a logging API that accepts only approved fields rather than letting every handler log arbitrary objects.

~~~java
public record SafeRequestContext(
        String requestId,
        String route,
        String method,
        String functionName,
        String region) {
}

public final class SafeLog {
    private SafeLog() {}

    public static void requestAccepted(
            Logger logger,
            SafeRequestContext context) {

        logger.info(
            "request_accepted request_id={} route={} method={} function={} region={}",
            context.requestId(),
            context.route(),
            context.method(),
            context.functionName(),
            context.region()
        );
    }

    public static void operationFailed(
            Logger logger,
            SafeRequestContext context,
            String errorCode,
            String exceptionType) {

        logger.error(
            "operation_failed request_id={} route={} error_code={} exception_type={}",
            context.requestId(),
            context.route(),
            errorCode,
            exceptionType
        );
    }
}
~~~

The key point is that SafeRequestContext holds no request body, token, or customer data. Route should be the router's route template, not an arbitrary raw request path.

A wrapper alone cannot guarantee safety if callers can still pass arbitrary objects to raw loggers. Strengthen enforcement by using dedicated types for approved fields, reviewing logging helpers in code review, prohibiting raw request/response and exception-object logging in production, running static analysis to flag logger calls passing request/headers/payload/token, and scanning log samples for secrets.

## 8. Managing MDC and context in functions

SLF4J/Logback Mapped Diagnostic Context (MDC) attaches a request ID or trace ID to multiple log statements without repeating parameters.

~~~java
import org.slf4j.MDC;

public Response handle(Request request) {
    String requestId = safeRequestId(request.requestId());
    String previousRequestId = MDC.get("request_id");
    String previousFunction = MDC.get("function");
    String previousRoute = MDC.get("route");

    try {
        MDC.put("request_id", requestId);
        MDC.put("function", "CreateOrder");
        MDC.put("route", "/orders");

        return process(request);
    } finally {
        restoreMdc("request_id", previousRequestId);
        restoreMdc("function", previousFunction);
        restoreMdc("route", previousRoute);
    }
}

private static void restoreMdc(String key, String previousValue) {
    if (previousValue == null) {
        MDC.remove(key);
    } else {
        MDC.put(key, previousValue);
    }
}
~~~

In serverless environments, threads can be reused across subsequent invocations. If MDC is not cleared, the previous request's context can leak into the next request's logs. Always clean up keys added by the function inside a finally block, even when the handler throws an exception.

If a framework or runtime executes invocations asynchronously, MDC does not automatically propagate across threads or executors. Use supported context propagation or pass context explicitly into tasks. Never place tokens, emails, or payloads into MDC, as those fields would automatically appear in every log record.

## 9. Exceptions can leak data

Exception messages are often constructed from input data or dependencies. A few examples:

- HTTP client exceptions containing URLs with signed queries.
- SQL exceptions containing statements, schemas, tables, or bind values.
- JSON parser exceptions quoting fragments of payloads.
- Authentication exceptions containing usernames or token fragments.
- Storage SDK exceptions containing object paths or request metadata.
- Validation exceptions echoing client-supplied values.

The following line can expose messages and stack traces:

~~~java
// Do not use in general logs if the exception may contain sensitive data.
logger.error("Request failed", exception);
~~~

In broad-access operational logs, record a stable error code, exception type, and request ID:

~~~java
catch (Exception ex) {
    logger.error(
        "payment_authorization_failed request_id={} error_code={} exception_type={}",
        requestId,
        "PAYMENT_PROVIDER_UNAVAILABLE",
        ex.getClass().getSimpleName()
    );

    throw new ServiceUnavailableException("PAYMENT_PROVIDER_UNAVAILABLE");
}
~~~

Never log ex.getMessage() unless you know for sure it cannot contain secrets or PII. Never serialize whole exceptions to JSON and ship them to a broad log aggregator.

### When stack traces are needed for debugging

Stack traces have diagnostic value, yet can contain sensitive exception messages across cause chains. When deeper diagnostics are needed, route them to a separate diagnostic sink with tighter access controls; redact exception messages, URLs, and provider details; enforce short retention and enable access auditing; never include stack traces in client responses; and never forward raw exceptions into alerts, chat, or tickets.

Do not assume logging only the exception class is always sufficient. Error codes and stack fingerprints should accompany trace IDs, deployment versions, and safe operational metadata.

## 10. Designing safe HTTP error responses

Error responses are public interfaces. They should give clients enough information to handle failures without disclosing stack traces, internal class names, file paths, packages, private hostnames, SQL queries, table names, connection strings, tokens, other users' data, or raw payloads.

Use stable error codes and request/correlation IDs to aid investigation:

~~~json
{
  "type": "https://api.example.com/problems/service-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503,
  "detail": "The request could not be completed. Try again later.",
  "code": "PAYMENT_PROVIDER_UNAVAILABLE",
  "requestId": "req-7f2c"
}
~~~

This is a Problem Details-style example. Detail must be an approved static message, not an exception message. Never place tokens, user IDs, or sensitive data inside the instance or URL fields of a problem response.

### Mapping exceptions to responses

~~~java
public ApiError toApiError(Throwable error, String requestId) {
    if (error instanceof InvalidInputException) {
        return new ApiError(
            400, "INVALID_REQUEST",
            "The request is invalid.", requestId);
    }

    if (error instanceof ServiceUnavailableException) {
        return new ApiError(
            503, "SERVICE_UNAVAILABLE",
            "The service is temporarily unavailable.", requestId);
    }

    return new ApiError(
        500, "INTERNAL_ERROR",
        "An unexpected error occurred.", requestId);
}

public record ApiError(
        int status,
        String code,
        String message,
        String requestId) {
}
~~~

Clients receive error codes and request IDs; operations teams look up logs/traces using the request ID. Never return error.getMessage() verbatim simply because it is the quickest way to surface errors.

### Distinguishing 4xx and 5xx

- 4xx: input error messages may identify which field is invalid if that field is non-sensitive. Never echo raw input.
- 401/403: do not reveal whether an account exists if that creates an enumeration risk.
- 404: do not confirm the existence of private resources when the caller lacks permission.
- 429: may return retry guidance and an appropriate Retry-After header without leaking sensitive internal quotas.
- 5xx: return generic messages and stable error codes; internal details stay in controlled telemetry.

## 11. OpenTelemetry: traces and spans are also sensitive data

Distributed tracing records a request's path across functions, APIs, databases, queues, and external services. A trace typically includes trace IDs, span IDs, parent relationships, timings, statuses, events, and attributes.

Potentially sensitive attributes:

- url.full containing query parameters with tokens or signed URLs.
- HTTP request headers Authorization or Cookie.
- db.statement containing SQL or input values.
- messaging.message.body containing entire event payloads.
- enduser.id, email, or tenant identifiers.
- Exception messages and stack traces.
- Baggage propagated from service to service.

Do not enable capturing all headers, bodies, or SQL statements in production without explicit redaction policies.

### Use route templates instead of full URLs

Record method POST, route /orders/{orderId}, and status code 202. Avoid recording full URLs when query strings may contain secrets. If host is needed, record only allowlisted hostnames; omit userinfo and queries.

### Adding attributes selectively

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;

Span span = Span.current();
span.setAttribute("app.error_code", "ORDER_VALIDATION_FAILED");
span.setAttribute("app.operation", "create_order");
span.setAttribute("http.route", "/orders/{orderId}");
span.setStatus(StatusCode.ERROR);
~~~

Add only approved values. Never add raw customer IDs, emails, tokens, request bodies, or exception messages. Follow semantic conventions matching your OpenTelemetry SDK/instrumentation version.

### Exception recording

Some instrumentation libraries automatically record exception events, including exception.message and stack traces. Thus, even if your code never adds exception attributes directly, agents or auto-instrumentation may still capture them.

Audit your OpenTelemetry Java agent, framework instrumentation, and exporter configurations. Disable or restrict capturing exception messages/stack traces if they cannot be safely redacted. For general telemetry, recording only exception.type, app.error_code, and span status may be sufficient.

## 12. Baggage and context propagation

OpenTelemetry Baggage propagates key-value pairs across services alongside trace context. Baggage is handy for propagating attributes such as tenant tier or operation class, yet it travels across the network and can appear in downstream logs/traces.

Never place access tokens, session IDs, cookies, emails, phone numbers, addresses, raw user/tenant identifiers, payloads, or secrets into baggage. Allowlist only small, low-sensitivity values genuinely needed for routing/observability. Never trust baggage sent by external clients; gateways should strip or replace disallowed keys before propagation.

Correlation IDs should also never become data containers. Use random, unpredictable IDs with no business meaning. If mapping an ID back to a user or operation is required, keep that mapping in a separately protected system.

## 13. Metrics: avoid putting identifiers into labels

Metrics are typically retained longer and aggregated broadly. Using user IDs, emails, order IDs, request IDs, or dynamic URLs as labels causes extreme cardinality, drives up cost, and slows queries—while exposing identifying data.

Prefer bounded-cardinality dimensions:

~~~text
function_name=CreateOrder
route=/orders/{orderId}
status_class=2xx
error_code=ORDER_VALIDATION_FAILED
region=ap-southeast-1
~~~

Avoid customer emails, order IDs, request IDs, and dynamic URLs as metric labels. Use histograms for durations, counters for error counts, and gauges for backlog/concurrency. When tenant breakdown is needed, use tier or tenant category rather than exact IDs. When tracing a single request, traces/logs are better suited than metrics.

## 14. Never log entire message or event payloads

Queues and event triggers commonly carry business data. A message may contain emails, shipping addresses, payment references, or webhook bodies. When a consumer fails, logging the full body can repeat sensitive data across every retry.

Instead, log minimal metadata:

~~~json
{
  "event": "message_processing_failed",
  "event_type": "OrderCreated",
  "schema_version": 3,
  "message_ref": "msg-6d12",
  "attempt": 2,
  "error_code": "ORDER_VALIDATION_FAILED",
  "function": "ProcessOrder"
}
~~~

message_ref should be a non-sensitive ID or pseudonymous reference; never use raw payloads as identifiers. If an external message ID might contain PII, replace it with an internal ID.

### For dead-letter queues

DLQs must retain messages for replay or investigation, but DLQ access permissions should be no broader than necessary. Never dump message bodies into logs when routing to a DLQ. Enforce encryption and read access controls on the queue, retention limits, strict peek/dequeue/redrive permissions, masking or tokenization before storage if needed, expiration cleanup of messages and copies, and auditing whenever messages are exported or replayed.

Replays must preserve idempotency keys and avoid duplicate side effects. If a payload is edited for redrive, audit the edit without logging sensitive contents.

## 15. Debugging HTTP clients and SDKs safely

HTTP clients, database drivers, and cloud SDKs often offer debug modes that log requests and responses. Those logs are helpful in development but can expose credentials or body data in production.

- Never enable global wire logging or body logging in production.
- When debugging is required, enable it temporarily with narrow service/route scope and pre-export redaction.
- Never log Authorization, Cookie, API keys, signed URLs, or request bodies.
- Disable automatic library header logging unless an allowlist is configured.
- For SQL, log query fingerprints or operation names instead of statements with bind values.
- Never log response bodies from identity providers or payment providers.

Safe dependency logging example:

~~~java
logger.warn(
    "dependency_call_failed dependency={} operation={} status={} request_id={}",
    "payment-provider",
    "authorize",
    503,
    requestId
);
~~~

When diagnosing errors, include vetted error categories or provider error codes. Avoid logging full response bodies because providers may return token fragments or account details.

## 16. Logging during retries and idempotency flows

Serverless functions may be re-invoked on timeouts, runtime restarts, queue redeliveries, or upstream retries. If every retry logs the full payload, sensitive data multiplies. Without attempt/correlation metadata, distinguishing a retry from a new operation is also harder.

A helpful log event:

~~~json
{
  "event": "operation_retry_scheduled",
  "operation_ref": "op-7a31",
  "attempt": 3,
  "max_attempts": 5,
  "error_code": "DEPENDENCY_TIMEOUT",
  "next_delay_ms": 4000,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

Never log idempotency keys containing customer data or raw message IDs. Use a dedicated internal reference. Preserve correlation/trace context across retries when supported, without misleadingly reusing trace context across independent operations.

If log emission fails before commit, order state writes appropriately. Never rely on payload-bearing logs as the sole business recovery mechanism; durable state must reside in databases, queues, or workflows.

## 17. Controlling log platforms and access permissions

Application-level redaction is the first layer. Telemetry platforms must enforce additional controls:

- Encryption in transit and at rest.
- Role-based access by team, service, and environment.
- Auditing of queries, exports, shared dashboards, and log downloads.
- Field-level masking or access controls where supported.
- Retention tailored to data type and purpose.
- Separation of production logs from sandbox/test logs.
- Restricted permissions for creating alerts containing log snippets.
- Blocking sensitive logs from shipping to unauthorized workspaces or regions.

Logs are often replicated to multiple targets. When changing sinks or exporters, inspect every copy, including archives, SIEMs, data lakes, ticket integrations, and backups.

Do not retain all logs indefinitely. Define retention based on security, legal, operational, and investigative needs. Logs containing personal identifiers should have the shortest necessary retention. Aggregated metrics can safely be kept longer than detailed logs.

## 18. Trace sampling and limiting collected data

Distributed tracing can generate huge span volumes, especially when requests call many dependencies or queue consumers process heavy message traffic. Sampling reduces volume, cost, and collected data exposure.

- **Head sampling:** decides whether to keep a trace at request entry, usually by percentage or simple rules.
- **Tail sampling:** decides after observing the trace, prioritizing error traces or high latency.
- **Attribute filtering:** strips or transforms sensitive attributes before export.
- **Span suppression:** drops overly granular spans that serve no operational purpose.

Sampling is not redaction. If a trace is sampled before filtering, sensitive data may still sit in memory buffers or exporters. Redact/allowlist before export; sampling only adjusts how many traces are kept.

Never base sampling rules on user IDs or emails. To retain error traces, filter by status, error code, service, and duration.

## 19. Testing to detect data leaks

Do not rely solely on source code reviews. Inspect actual telemetry emitted by frameworks, runtimes, SDKs, and auto-instrumentation.

Tests can inject synthetic canary values rather than real secrets:

~~~java
@Test
void doesNotLogAuthorizationOrPayload() {
    String fakeToken = "CANARY_TOKEN_DO_NOT_LOG";
    String fakeEmail = "canary-user@example.invalid";

    invokeFunction(fakeToken, fakeEmail);

    String capturedLogs = testAppender.contents();

    assertFalse(capturedLogs.contains(fakeToken));
    assertFalse(capturedLogs.contains(fakeEmail));
}
~~~

This example requires a test appender matching your logging framework. The goal is to assert that sensitive values never appear in log outputs.

| Test case | Canary data | Expected result |
|---|---|---|
| HTTP Authorization | Synthetic bearer token | Absent from logs and spans |
| Cookie | Synthetic session cookie | Absent from telemetry |
| Query string | Synthetic reset token | Only route template recorded |
| Request body | Synthetic email/address | Full body not serialized |
| Exception message | String containing canary | General error logs exclude message |
| SQL error | Synthetic bind value | SQL containing values not logged |
| Trace baggage | Synthetic PII | Not propagated or exported |
| Queue message | Payload containing canary | Only safe event metadata logged |
| DLQ redrive | Synthetic failed message | Audit logs reference only, no body dump |
| Error response | Synthetic stacktrace/hostname | Client receives only public code and message |
| CRLF injection | CRLF and control characters | No forged log records created |
| MDC reuse | Two consecutive invocations | Previous invocation context absent from next invocation |

Run tests both locally and in a serverless test environment because platform loggers, extensions, and agents can emit fields outside unit-test appenders.

## 20. Incident response when sensitive data has been logged

If tokens, passwords, or PII are discovered in telemetry:

1. Identify the data type, affected log/trace systems, timeframe, and replica scope.
2. Restrict access or pause the leaking exporter/sink if necessary.
3. Revoke/rotate credentials if secrets may have been exposed.
4. Trace where logs were exported, archived, attached to tickets, or sent via alerts.
5. Execute deletion/retention cleanup across every sink and backup.
6. Fix logging, instrumentation, or error handlers at the source.
7. Add canary tests and detection rules to prevent recurrence.
8. Document the incident, impact, and notification decisions per organizational policy.

Never delete logs arbitrarily if they serve as required forensic evidence. Coordinate with security/incident owners to balance evidence preservation with restricting access and purging unauthorized data.

## 21. Common mistakes

| Mistake | Risk | Mitigation |
|---|---|---|
| Logging full requests/responses | Leaks tokens, cookies, and PII | Allowlist fields and log metadata |
| Masking only passwords via regex | Misses secrets in URLs, nested JSON, or exceptions | Avoid logging payloads; apply schema-based redaction and allowlists |
| Logging exceptions directly | Message/cause may include input data | Log error codes, exception types, and isolate full details to restricted sinks |
| Returning stack traces to clients | Exposes packages, paths, SQL, and topology | Generic error responses with request ID |
| Logging full URLs | Queries hold tokens/SAS/presigned signatures | Log route templates and allowlisted hostnames |
| Putting raw user IDs into metrics | Leaks identifiers and causes high cardinality | Use aggregated dimensions |
| Putting PII into baggage | Data spreads across services | Baggage allowlists and gateway sanitization |
| Enabling HTTP/SQL debug in production | Logs bodies, headers, and bind values | Time-bound, narrowly scoped debug with redaction |
| Not clearing MDC | Prior request context leaks into next invocation | Remove keys in finally blocks |
| Assuming structured JSON is automatically safe | Sensitive fields still serialize | Schema allowlists and output testing |
| Redacting only at dashboards | Secrets still sit in storage/indexes | Redact before export and secure sinks |
| Retaining logs indefinitely | Magnifies breach impact and cost | Purpose-driven retention |
| Logging DLQ bodies for easier debugging | Duplicates sensitive payloads | Message references, error codes, and dedicated DLQ access |
| Hashing PII with plain SHA-256 | Vulnerable to dictionary reversal | Managed-key HMAC or random references |

## 22. Production checklist

Before deploying a Java function, confirm:

- **Data inventory:** are PII, secrets, business payloads, and operational metadata identified?
- **Allowlists:** do logs record only purposeful fields without arbitrarily serializing requests, responses, or events?
- **HTTP:** are Authorization, Cookie, query tokens, signed URLs, and forwarded headers excluded from logs?
- **Structured logs:** do JSON encoders escape data, and are text inputs bounded against log injection?
- **Exceptions:** are error codes and exception types logged while exception messages/stacks stay in controlled sinks?
- **Error responses:** are clients shielded from stack traces, SQL, private hostnames, and secrets while receiving request IDs?
- **Traces:** are URL, header, SQL, event body, and exception attributes allowlisted/redacted?
- **Baggage:** are only non-sensitive key-values propagated, with untrusted client baggage stripped?
- **Metrics:** are user IDs, emails, request IDs, and dynamic URLs excluded from labels?
- **Queues/DLQs:** are payload dumps avoided, with access controls, retention, redrive permissions, and auditing enforced?
- **MDC/context:** is context cleared after every invocation and propagated properly across async tasks?
- **Storage:** are logs/traces encrypted, access-restricted, audited, and governed by retention?
- **Testing:** do canary tests cover logs, traces, error responses, CRLF, and retries?
- **Incident response:** are procedures ready to rotate secrets, trace replicas, and execute deletion/retention?
- **Cost:** are sampling, cardinality, log volume, and retention monitored to avoid unnecessary spend?

## 23. Conclusion

Logs, traces, and error messages are part of an application's security surface. They must provide enough context to diagnose failures without becoming duplicates of requests, event payloads, or business records. Classify data, prefer allowlists, adopt structured logging, keep exception messages and stack traces within controlled scopes, and return stable error codes instead of internal details.

In Java serverless systems, pay special attention to automatic telemetry from runtimes and SDKs, thread/MDC reuse, retried messages, and trace context flowing across services. Redaction must happen before data is exported; backend access controls, retention, encryption, and auditing continue protecting stored records. Canary tests and incident procedures catch and contain leaks before they recur.

When telemetry contains only essential data traceable via request IDs, error codes, and safe trace context, teams can still investigate cold starts, dependency failures, retries, and latency without elevating the risk of exposing user data.
