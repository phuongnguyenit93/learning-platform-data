# Redacting Data in Logs, Traces, and Error Messages

Spring Data Elasticsearch applications routinely handle documents containing customer details, orders, addresses, search queries, internal metadata, and occasionally credentials. Such data can accidentally surface outside Elasticsearch: application logs, exception messages, HTTP client logs, distributed traces, metric tags, dead-letter records, and error messages returned by APIs.

Data redaction/masking is part of security design. The goal is to preserve enough information for operations, troubleshooting, and request tracking while curbing the recording or spread of sensitive data.

A practical principle is to log only what operators need to answer technical questions: which request, which operation, which index, whether it succeeded or failed, which error category occurred, and how long it took. You do not need to log entire documents, query bodies, tokens, passwords, or verbatim exception messages to achieve that.

In this lesson, "redacting data" covers:

- **Redaction:** completely stripping sensitive values from logs/traces/responses.
- **Masking:** replacing part of a value with masking characters, such as `***1234`, when the remainder is still needed operationally.
- **Pseudonymization:** replacing a value with a stable code or HMAC to correlate events without revealing the original value.
- **Minimization:** avoiding collecting fields in the first place when no genuine purpose exists.

Redaction should occur at the boundary where data is emitted and before it enters observability systems. A log filter at the end of a pipeline can help, but should never be your sole line of defense.

## 1. Where Sensitive Data Can Leak

A document-processing flow crosses many components:

```text
HTTP request
    |
    v
Controller / validation
    |
    v
Service / domain logic
    |
    v
Spring Data Elasticsearch
    |
    v
Elasticsearch Java client / HTTP transport
    |
    v
Elasticsearch cluster

Parallel observation points:
  - Application logs
  - Exception messages / stack traces
  - Distributed traces / span attributes
  - Metrics labels
  - Audit events
  - API error responses
  - Reverse proxy / gateway / APM agent logs
```

Example document:

```json
{
  "customer_id": "C-10001",
  "name": "Nguyen Van A",
  "email": "customer@example.com",
  "phone": "+84 901 234 567",
  "address": "12 Example Street",
  "order_id": "O-2026-001",
  "payment_token": "tok_live_secret_value",
  "status": "PAID"
}
```

Values such as `email`, `phone`, `address`, and payment tokens should never appear verbatim in ordinary logs or traces. Even `customer_id` and `order_id` can be considered sensitive under internal policies because they allow correlating an individual's or transaction's activities.

### 1.1. Common leak sources

| Source | Risk |
|---|---|
| `log.info("Document: {}", entity)` | `toString()` may print every entity field. |
| `log.error("Failed: {}", exception.getMessage())` | Message may include queries, indices, URLs, field values, or payloads. |
| `log.error("Request failed", exception)` | Stack trace/cause messages may include input data. |
| HTTP wire logging | May record `Authorization` headers, request bodies, and response bodies. |
| Elasticsearch query logging | Query DSL may contain emails, phone numbers, addresses, or user search terms. |
| Trace span attributes | May capture URLs, query strings, request headers, document IDs, or exception descriptions. |
| MDC/baggage | Context values may automatically propagate onto every log/span. |
| API error responses | Returning raw exception messages or stack traces to clients. |
| Metric labels | Using emails, IDs, or queries as tags causes leaks and extreme cardinality. |
| Debug dumps/dead-letter | Storing full source documents in uncontrolled logs or error stores. |

## 2. Classifying Data Before Logging

Do not decide redaction solely by field name. Evaluate sensitivity and intended usage.

A practical classification:

| Category | Examples | Default Handling |
|---|---|---|
| Authentication secrets | Passwords, API keys, bearer tokens, refresh tokens, private keys, cookies | Never log; absolute redaction. |
| Personal data | Emails, phone numbers, names, addresses, personal identifiers | Never log raw values; mask or pseudonymize only for approved purposes. |
| Transaction data | Payment tokens, accounts, transaction IDs, order contents | Log only classified internal IDs if needed; strip payloads. |
| User content | Search terms, free text, comments, filenames | Do not log by default; may contain personal data or secrets. |
| Technical metadata | Operation, index alias, HTTP status, duration, retry count | Safe to log if free of sensitive data and unnecessary internal topology. |
| Correlation metadata | Trace ID, request ID, job ID | Usually permitted for event correlation, but never embed PII into values. |

For every field, document:

1. Purpose of collection.
2. Who can access logs/traces.
3. Whether raw, masked, or pseudonymous values are needed.
4. Retention period.
5. How data is deleted or handled when no longer needed.

### 2.1. Do not apply a single masking rule to every field

Examples:

- API tokens: strip completely, including prefix/suffix characters.
- Emails: may mask the local part if operators need to recognize the same address within an event.
- Phones: retain only the last few digits if policy allows.
- Document IDs: can use HMAC to correlate events without exposing raw IDs.
- Search text: usually stripped entirely since it can contain arbitrary sensitive text.

Do not assume a value is safe just because it does not look like an email or phone number. Sensitive data can appear inside filenames, URLs, query strings, exception messages, or free-form fields.

## 3. Safe Logging: Log Events, Not Object Dumps

Avoid logging entities directly:

```java
// Unsafe: toString() may include every field.
log.info("Saving product {}", product);
```

Avoid logging request or query bodies:

```java
// Unsafe if request/query contains user data.
log.debug("Elasticsearch query: {}", query);
```

Instead, emit structured events containing only required fields:

```java
log.info(
        "Elasticsearch write completed operation={} index={} documentRef={} outcome={}",
        "index",
        "products",
        safeDocumentReference(product.getId()),
        "success"
);
```

Here `safeDocumentReference` must be a pseudonymization or masking helper defined per application policy. If cross-log document correlation is unnecessary, omitting the ID altogether is even better.

### 3.1. Use placeholders, avoid manual string concatenation

SLF4J parameterized logging avoids building strings unnecessarily when the log level is disabled:

```java
log.info("Bulk indexing finished index={} itemCount={} durationMs={}",
        indexAlias,
        itemCount,
        duration.toMillis());
```

Do not concatenate full objects or payloads:

```java
// Avoid.
log.info("Import request=" + request);
```

Placeholders do not automatically redact data. If an argument is a token or an entity containing PII, its value still gets logged. Select safe arguments before calling the logger.

### 3.2. Log useful operational metadata

Example event for a bulk operation:

```java
log.info(
        "Elasticsearch bulk completed index={} batchId={} itemCount={} successCount={} failureCount={} durationMs={}",
        indexAlias,
        batchId,
        itemCount,
        successCount,
        failureCount,
        duration.toMillis()
);
```

These fields aid operations without logging source documents. If `batchId` could contain user data or sensitive business IDs, generate a random technical ID rather than using a raw business key.

## 4. Designing Masking and Pseudonymization Functions

Masking and pseudonymization serve different needs.

### 4.1. Masking emails

Example simple masking helper:

```java
public final class DataMasker {

    private DataMasker() {
    }

    public static String maskEmail(String email) {
        if (email == null || email.isBlank()) {
            return "[redacted]";
        }

        int at = email.indexOf('@');
        if (at <= 0 || at == email.length() - 1) {
            return "[redacted]";
        }

        String local = email.substring(0, at);
        String domain = email.substring(at + 1);
        String visible = local.substring(0, 1);

        return visible + "***@" + domain;
    }
}
```

For example, `alice@example.com` becomes `a***@example.com`. This still reveals the domain and first character, so use it only if policy permits. When domains themselves are sensitive, full redaction or pseudonymization is safer.

Illustrative helpers should be adapted for Unicode, non-standard addresses, and business rules. Never use masking helpers for email validation.

### 4.2. Masking phone numbers

```java
public static String maskPhone(String phone) {
    if (phone == null || phone.isBlank()) {
        return "[redacted]";
    }

    String digits = phone.replaceAll("\\D", "");
    if (digits.length() < 4) {
        return "[redacted]";
    }

    return "***" + digits.substring(digits.length() - 4);
}
```

For example, a phone number becomes `***4567`. Never log the raw value in another log line within the same workflow.

### 4.3. Pseudonymization with HMAC

When you need to correlate multiple logs for the same customer without logging the raw customer ID, you can use HMAC-SHA-256 with a secret key managed outside source code:

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public final class ReferenceHasher {

    private final byte[] secretKey;

    public ReferenceHasher(byte[] secretKey) {
        this.secretKey = secretKey.clone();
    }

    public String hashReference(String value) {
        if (value == null || value.isBlank()) {
            return "[missing]";
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secretKey, "HmacSHA256"));
            byte[] digest = mac.doFinal(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (Exception ex) {
            throw new IllegalStateException("Could not create reference hash", ex);
        }
    }
}
```

HMAC is safer than an unkeyed hash when inputs are predictable like emails or phone numbers. Unkeyed hashes are vulnerable to dictionary guessing. The secret key must reside in a secret manager or equivalent key store with access controls and rotation procedures.

HMAC remains a pseudonymous identifier, not absolute anonymization. Anyone with access to multiple systems or the key can link events. Avoid sharing the same key across environments unless cross-environment correlation between dev, staging, and production is explicitly required.

## 5. Prevent `toString()` from Leaking Data

A frequent leak source is automatic object logging. Entities using Lombok `@Data`, `@ToString`, or Java records include all fields in `toString()`.

Risky example:

```java
@Data
@Document(indexName = "customers")
public class CustomerDocument {
    @Id
    private String id;
    private String email;
    private String phone;
    private String address;
    private String accessToken;
}
```

`@Data` generates a `toString()` containing every field. If the entity is printed by a logger, debugger, exception, or framework, values can leak.

You can exclude sensitive fields from `toString()`:

```java
@Getter
@Setter
@ToString(onlyExplicitlyIncluded = true)
@Document(indexName = "customers")
public class CustomerDocument {

    @Id
    @ToString.Include
    private String id;

    @ToString.Include
    private String status;

    private String email;
    private String phone;
    private String address;
    private String accessToken;
}
```

Another option is `@ToString.Exclude` on sensitive fields. Explicitly allowlisting included fields is easier to govern than an exclude denylist, because newly added fields will not appear automatically in `toString()`.

Even so, do not treat a redacted `toString()` as permission to log entities everywhere. Entities may be serialized or dumped through other mechanisms. Creating dedicated log DTOs/events is cleaner.

## 6. Safe Logging Around `ElasticsearchOperations`

Never log whole entities or queries. Log operation metadata at service boundaries:

```java
public Mono<Product> saveProduct(Product product) {
    long startedAt = System.nanoTime();

    return reactiveOperations.save(product)
            .doOnSuccess(saved -> log.info(
                    "Product indexed index={} operation={} outcome={} durationMs={}",
                    "products",
                    "save",
                    "success",
                    elapsedMillis(startedAt)
            ))
            .doOnError(error -> log.warn(
                    "Product index failed index={} operation={} errorType={} durationMs={}",
                    "products",
                    "save",
                    error.getClass().getSimpleName(),
                    elapsedMillis(startedAt)
            ));
}
```

With `Mono`, `doOnSuccess` can be invoked with `null` when the publisher completes empty; if code needs to distinguish empty vs. valued completion, use an appropriate operator or check the value. The snippet above focuses on metadata and omits exception messages.

With imperative APIs:

```java
public Product saveProduct(Product product) {
    long startedAt = System.nanoTime();
    try {
        Product saved = operations.save(product);
        log.info("Product indexed index={} operation={} outcome={} durationMs={}",
                "products", "save", "success", elapsedMillis(startedAt));
        return saved;
    } catch (RuntimeException ex) {
        log.warn("Product index failed index={} operation={} errorType={} durationMs={}",
                "products", "save", ex.getClass().getSimpleName(), elapsedMillis(startedAt));
        throw ex;
    }
}
```

This illustrates a logging boundary; production services may translate exceptions into domain exceptions higher up. Never log and swallow exceptions when callers need to know the operation failed.

### 6.1. Avoid logging raw Query DSL

A query can hold user data:

```json
{
  "query": {
    "term": {
      "email.keyword": "customer@example.com"
    }
  }
}
```

Instead of logging query JSON, log metadata:

```java
log.debug("Elasticsearch search started index={} queryType={} fieldGroup={}",
        "customers", "term", "customer_lookup");
```

Never log literal values, query strings, or full `NativeQuery` dumps if queries hold sensitive inputs. To reproduce bugs, use synthetic test data or a redacted query copy.

### 6.2. Avoid logging full `BulkResponse` item sources

Bulk responses normally contain status, ID, error type, and reason. Log counts and error categories instead of dumping the full response:

```java
log.warn("Bulk indexing partially failed index={} total={} succeeded={} failed={} errorType={}",
        indexAlias, total, succeeded, failed, errorType);
```

When failed items must be tracked, log pseudonymous IDs, statuses, and error codes. Store original payloads in a separate error store only when justified, encrypted, access-controlled, and bounded by retention.

## 7. Exception Messages from Elasticsearch Can Contain Data

Exceptions can originate across multiple layers:

- Spring Data Elasticsearch.
- Elasticsearch Java API Client.
- HTTP transport.
- Elasticsearch server responses.
- Mapping/conversion layer.
- Validation and domain services.

Error messages can contain index names, document IDs, fields, query fragments, URLs, request parameters, or snippets of input data. Therefore, never assume `exception.getMessage()` is safe to log or return to clients.

Avoid:

```java
catch (Exception ex) {
    log.error("Elasticsearch operation failed: {}", ex.getMessage());
    throw new RuntimeException(ex.getMessage());
}
```

And avoid:

```java
catch (Exception ex) {
    return Mono.error(new ResponseStatusException(
            HttpStatus.INTERNAL_SERVER_ERROR,
            ex.getMessage(),
            ex
    ));
}
```

The second example can propagate internal details straight into HTTP responses or error handling chains.

### 7.1. Log safe error codes

Define internal error codes free of payloads:

```java
public enum SearchErrorCode {
    INDEX_UNAVAILABLE,
    DOCUMENT_INVALID,
    SEARCH_TIMEOUT,
    SEARCH_FAILED
}
```

Map exceptions to error categories:

```java
private SearchErrorCode classify(Throwable error) {
    if (error instanceof org.springframework.dao.DataAccessResourceFailureException) {
        return SearchErrorCode.INDEX_UNAVAILABLE;
    }
    if (error instanceof org.springframework.dao.DataIntegrityViolationException) {
        return SearchErrorCode.DOCUMENT_INVALID;
    }
    return SearchErrorCode.SEARCH_FAILED;
}
```

Real exceptions may be wrapped across several layers and differ by client version. This is a baseline classifier; extend it with the exception classes and error statuses used in your project.

Log the code and exception class:

```java
log.error("Elasticsearch operation failed errorCode={} exceptionType={} traceId={}",
        errorCode,
        error.getClass().getSimpleName(),
        traceId);
```

When stack traces are needed for investigation, direct them only to a restricted-access log sink with scrubbing rules. Avoid automatically dumping raw exceptions across all environments when messages/causes may carry request data.

### 7.2. Distinguishing retryable errors from data errors

Do not decide retries by matching free-text exception messages alone. Classify by status/error type:

| Category | Examples | Handling |
|---|---|---|
| Transient | Timeouts, connection resets, 429, 502/503/504 | Retry with backoff, limits, and idempotency. |
| Data | Mapping parse errors, invalid fields, oversized documents | Do not retry as-is; fix data or dead-letter. |
| Conflict | Version conflict, create conflict | Read current version/state and handle per business logic. |
| Configuration/permission | Missing index, unauthorized, forbidden | Stop or alert; fix configuration/permissions. |
| Unknown | Unclassified exceptions | Log safe error code, correlation ID, and investigate. |

Error classifiers should return stable codes so metrics and alerts never depend on free-form message text.

## 8. Returning Safe Error Messages to APIs

Clients need to know an operation failed and what to do next, yet rarely need stack traces, node names, physical index names, Query DSL, or raw Elasticsearch exceptions.

An error response can contain:

- An appropriate HTTP status.
- A stable error code.
- A generic message free of internal data.
- A correlation ID or trace ID for support lookup.
- Sanitized field validation errors when safe to show.

Example response:

```json
{
  "type": "https://api.example.com/problems/search-failed",
  "title": "Search could not be completed",
  "status": 503,
  "detail": "Please retry later or contact support with the request ID.",
  "code": "SEARCH_UNAVAILABLE",
  "requestId": "req-7f2c1a"
}
```

Never return:

```json
{
  "error": "ElasticsearchException: failed request to node ...",
  "query": "...email customer@example.com...",
  "stackTrace": "..."
}
```

### 8.1. `@RestControllerAdvice` with Spring MVC/WebFlux

Spring Framework supports `ProblemDetail` for HTTP API error responses. You can use an exception handler to return standardized errors:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(SearchUnavailableException.class)
    public ProblemDetail handleSearchUnavailable(
            SearchUnavailableException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Search is temporarily unavailable. Please retry later."
        );
        problem.setTitle("Search unavailable");
        problem.setProperty("code", "SEARCH_UNAVAILABLE");
        return problem;
    }
}
```

The handler never places `exception.getMessage()` into the response. With Spring WebFlux, `@RestControllerAdvice` can also handle exceptions from reactive controllers; handler methods can return `Mono<ProblemDetail>` or reactive response types when async work is needed.

### 8.2. Attaching a request ID to responses

Request IDs should be generated or validated at the gateway/application boundary, then propagated via logging/tracing context. Never accept an arbitrary client header as a trusted ID without validating length and characters.

Example handler attaching a request ID obtained from request context:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.SERVICE_UNAVAILABLE,
        "Search is temporarily unavailable."
);
problem.setProperty("requestId", requestId);
```

Request IDs are strictly correlation identifiers—never emails, phone numbers, customer IDs, or tokens. Clients could send forged IDs to confuse logs if the system does not generate/control IDs at a trusted boundary.

## 9. Traces and Span Attributes

Distributed tracing links a request across gateways, services, Spring Data, the Elasticsearch client, and downstream dependencies. Span attributes are exported to APM backends and often persist longer than application logs.

Useful attributes typically include:

- `db.system` or datastore type.
- Operation name, e.g., `index`, `get`, `search`, `delete`.
- Logical index/alias name if it does not reveal sensitive topology.
- HTTP status or error category.
- Duration, retry count, and batch size.
- Trace ID/span ID managed by the tracing system.

Keep out of spans:

- `Authorization`/`Cookie` headers.
- Document sources or response bodies.
- Literal queries containing user input.
- Full URLs with sensitive query parameters.
- Emails, phone numbers, addresses, or tokens.
- Unscrubbed raw exception messages.

### 9.1. Do not put PII into span names

Span names should be stable and describe the operation:

```text
elasticsearch.search products
elasticsearch.index products
elasticsearch.get products
```

Avoid span names containing IDs or search terms:

```text
search customer@example.com
get customer-C-10001
```

Span names show up in dashboards, alerts, and log correlation. Dynamic names containing user data both leak information and create high cardinality.

### 9.2. Attributes must follow an allowlist

Never attach entire request objects to spans:

```java
// Avoid: the object may serialize into many sensitive attributes.
span.setAttribute("request", request.toString());
```

Instead, record a curated set of approved attribute keys and values:

```java
span.setAttribute("app.operation", "product.search");
span.setAttribute("app.index_alias", "products");
span.setAttribute("app.result_count", resultCount);
span.setAttribute("app.outcome", "success");
```

Never attach customer IDs or search terms simply because the tracing SDK accepts arbitrary attributes.

## 10. MDC, Trace Context, and Reactor Context

In imperative applications, SLF4J's MDC is commonly used to attach `requestId`, `traceId`, or `spanId` to log patterns. In reactive pipelines, execution can switch threads; `ThreadLocal`-backed MDC does not automatically cross every operator/scheduler boundary safely.

Imperative example:

```java
try {
    MDC.put("requestId", requestId);
    service.handle(request);
} finally {
    MDC.remove("requestId");
}
```

Always clear MDC in `finally` so data from a previous request does not linger on a reused thread.

In Reactor, context attaches to the subscriber context:

```java
return repository.findByStatus("ACTIVE")
        .contextWrite(context -> context.put("requestId", requestId));
```

You can read Reactor Context inside an operator:

```java
return Mono.deferContextual(contextView -> {
    String requestId = contextView.getOrDefault("requestId", "unknown");
    log.info("Reactive operation started requestId={} operation={}",
            requestId, "product.search");
    return repository.findBySku("SKU-100");
});
```

This snippet illustrates reading context inside a publisher. To propagate trace/MDC automatically across threads in logs, prefer Micrometer Context Propagation/Tracing matching your Spring Boot and Reactor versions. Avoid copying `ThreadLocal` values manually across threads without proper restoration and cleanup.

### 10.1. Baggage is not a business data store

Distributed tracing baggage can travel across multiple services. Any value placed into baggage can leave the current process and appear in downstream spans/logs.

Put only essential technical values into baggage, never PII or secrets. If tenant correlation is required, use an approved pseudonymous code and restrict propagation scope.

## 11. Redacting Data in URLs and HTTP Headers

HTTP client logs can record URLs, query strings, and headers. Example:

```text
GET /customers/search?email=customer@example.com
Authorization: Bearer eyJhbGciOi...
Cookie: session=...
```

Never enable full wire logging in production without filters and strict governance. Some HTTP clients or logging interceptors record full request/response bodies when `DEBUG`/`TRACE` is turned on.

Principles:

- Never log `Authorization`, `Proxy-Authorization`, `Cookie`, or `Set-Cookie`.
- Never place tokens in URL query parameters.
- Avoid logging query strings holding user data.
- When logging endpoints, log route templates like `/customers/{id}` rather than concrete URLs.
- Never log Elasticsearch request/response bodies by default.
- Never enable `TRACE` for transport/clients in production outside controlled incident debugging with verified output.
- Ensure proxies, gateways, and APM agents apply the exact same redaction policies.

### 11.1. Route templates are safer than concrete URLs

Log:

```text
http.route=/customers/{customerId}
http.request.method=GET
http.response.status_code=200
```

Avoid:

```text
url.full=https://api.example.com/customers/C-10001?email=customer@example.com
```

When identifying routes, rely on framework-provided route templates rather than fragile regex replacement across arbitrary URLs.

## 12. Configuring Log Levels for the Elasticsearch Client

Spring Data Elasticsearch uses the Elasticsearch Java API Client and HTTP transport. Exact logger categories depend on Spring Data, client, and transport versions.

In `application.yml`, you can configure log levels for application packages:

```yaml
logging:
  level:
    root: INFO
    com.example.catalog: INFO
    org.springframework.data.elasticsearch: INFO
    co.elastic.clients: WARN
```

This is an illustrative configuration; actual transport logger packages may differ. Avoid enabling broad `DEBUG`/`TRACE` on client packages in production without knowing precisely what gets emitted.

When troubleshooting:

1. Enable logging only for the targeted package and a short window.
2. Use synthetic/test data whenever possible.
3. Inspect output before shipping to log aggregators.
4. Revert verbose log levels immediately after investigation.
5. Purge or restrict access to logs containing sensitive data if any were emitted.

Do not assume changing `logging.level` provides redaction. Log levels only control verbosity; they do not recognize which fields are PII.

## 13. Logback and Redaction Filters

You can use Logback encoders/layouts or appender filters to standardize log events. However, regex filtering on final formatted strings has limitations:

- Data may be encoded or escaped differently.
- Secrets may appear inside nested JSON or stack traces.
- Regexes can miss newly introduced formats.
- Overly broad regexes can corrupt helpful technical metadata.
- Data may reach another appender before the filter runs.

Prefer keeping sensitive data out of log events from the start. End-of-pipeline filters are a supplemental defense layer.

Example Logback pattern emitting only technical fields:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] trace=%X{traceId} request=%X{requestId} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

This pattern does not generate trace IDs/request IDs itself; values must be populated in the proper context. When logging JSON, use a structured encoder and configure allowlists/redaction aligned with your project's log schema.

Never dump the entire MDC if MDC could contain client-supplied data. Include only controlled keys in the pattern.

## 14. Structured Logging and Log Schemas

Structured logging lets log pipelines parse fields without fragile free-text parsing. Define a consistent event schema:

```json
{
  "timestamp": "2026-11-13T12:00:00Z",
  "level": "INFO",
  "service": "catalog-api",
  "event": "elasticsearch.operation.completed",
  "operation": "search",
  "index_alias": "products",
  "outcome": "success",
  "duration_ms": 24,
  "result_count": 12,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req-7f2c1a"
}
```

There is no document source, literal query, token, or customer email. With a log schema, govern both field names and field values; a field named `request_id` is still unsafe if the application stuffs an email into it.

Useful event names:

- `elasticsearch.operation.started`
- `elasticsearch.operation.completed`
- `elasticsearch.operation.failed`
- `elasticsearch.bulk.partial_failure`
- `elasticsearch.reindex.completed`
- `elasticsearch.alias.cutover.completed`
- `elasticsearch.connection.unavailable`

Stable event names power dashboards and alerts without storing payloads.

## 15. Metrics Are Not a Place for Identifying Data

Metric labels/tags are stored in time-series databases. Putting emails, document IDs, query strings, or request IDs into labels both leaks data and explodes cardinality.

Do not do this:

```java
counterBuilder.tag("customer_email", customer.getEmail());
```

Use low-cardinality labels instead:

```java
counterBuilder
        .tag("operation", "search")
        .tag("outcome", "success")
        .tag("index_group", "catalog")
        .register(registry)
        .increment();
```

Good labels are small fixed enums/categories like operation, outcome, error code, region, or service. Never use random IDs, user IDs, emails, trace IDs, or search terms as tags.

Trace IDs fit log/trace correlation, not metric labels, because every request produces a distinct value.

## 16. Audit Logs Differ from Application Logs

Audit logs record security- or business-significant actions, such as:

- Who modified access permissions.
- Who deleted a record.
- When an export was requested.
- Which job executed an alias cutover.
- When an index administration operation occurred.

Audit events need enough detail for traceability while still applying minimization and pseudonymization. Do not repurpose debug application logs as audit logs, because completeness guarantees, retention, and access controls differ.

Example audit event:

```json
{
  "event": "customer.record.deleted",
  "actor_ref": "hmac:4c91...",
  "record_ref": "hmac:8a10...",
  "reason_code": "RETENTION_POLICY",
  "outcome": "success",
  "request_id": "req-7f2c1a",
  "timestamp": "2026-11-13T12:00:00Z"
}
```

Audit logs require appropriate integrity/access controls, clear retention policies, and tamper detection. If identifying data must be retained for an approved workflow, store it in a separately controlled audit system rather than scattering it across all application logs.

## 17. Dead-Letter Queues and Import Errors

When bulk imports fail, operators may need to retain failed items for fixing and replay. However, dead-letter records can contain entire source documents, including PII and secrets.

A minimal error record should contain:

- Import job ID.
- Pseudonymized source record reference.
- Index alias/version.
- Operation type.
- Classified error code/type.
- Timestamp and retry count.
- Reference to a protected payload store if payload retention is genuinely required.

If raw payloads must be retained:

- Store them in a dedicated store encrypted at rest and in transit.
- Restrict read permissions by role.
- Audit all access.
- Enforce short retention with automatic deletion.
- Never copy payloads into application logs or traces.
- Strip secrets before saving if the payload does not need them.

Never stuff sensitive payloads into exception messages just for retry convenience. Retry stores need their own schema and access controls.

## 18. Controlling Stack Traces and Error Messages

Stack traces help developers, yet can contain:

- Server/client exception messages.
- URLs and query parameters.
- Physical index, shard, or node names.
- Snippets of requests/responses.
- Field values inside mapping errors.
- Internal file paths or configuration details.

Never return stack traces to API consumers. In production, avoid automatically exposing exception classes, messages, or nested causes.

One approach separates internal logging from public responses:

```java
try {
    return operations.search(query, Product.class);
} catch (RuntimeException ex) {
    String errorCode = "SEARCH_FAILED";
    log.error("Search failed errorCode={} exceptionType={} requestId={}",
            errorCode,
            ex.getClass().getSimpleName(),
            requestId);

    throw new SearchUnavailableException(errorCode);
}
```

This snippet avoids leaking raw messages/causes into responses. When stack traces are required for debugging, route them to a controlled diagnostic channel with scrubbing rather than emitting them unconditionally into general logs.

Do not catch `Throwable` to hide every failure. Catch appropriate exceptions so fatal JVM errors follow runtime handling.

## 19. Safe Correlation IDs and Trace IDs

Correlation IDs connect logs, traces, and API responses without recording personal data.

Workflow:

1. The gateway or application boundary generates a random request ID.
2. The request ID is stored in the tracing/logging context.
3. Services include the request ID in event logs.
4. Trace IDs are managed by the tracing system.
5. API error responses return approved request IDs/trace IDs.
6. Support staff use those IDs to look up logs under access controls.

Never use emails or customer IDs as correlation IDs. Never accept unbounded header lengths or control characters; validate/normalize client-supplied header values.

### 19.1. Preventing log injection

User input can contain newlines or control characters to forge log entries:

```text
searchTerm = "keyboard\nINFO login succeeded"
```

If logged straight into plain-text logs, one input can fabricate multiple log lines. Structured logging/JSON encoders escape many characters, yet free-text inputs still require validation and sanitization.

Never concatenate raw user input into log lines. When a user-controlled value must be recorded, strip/normalize control characters or use an encoder with proper escaping.

## 20. Access Control, Retention, and Protecting Logs/Traces

Application-side redaction does not replace securing the log storage system.

Operational controls:

- Role-based access control; developers should not hold blanket read access to all production logs by default.
- Encryption in transit and at rest.
- Retention limits aligned with purpose and internal policy.
- Access auditing on logs, traces, and stored payloads.
- Isolation across dev/test/staging/production environments.
- No production PII in test environments without an approved anonymization process.
- Controls on exports/downloads and dashboard sharing.
- Deletion or rotation per retention schedules.
- An incident response procedure if secrets/PII are accidentally logged.

Logs get replicated across stdout, container runtimes, collectors, message queues, object storage, SIEMs, and APM backends. Account for every copy and its retention policy.

## 21. Testing Redaction Policies

Do not test only that a logger method was called. Assert on actual appender/encoder output or unit-test redaction utilities.

Sample masker tests:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class DataMaskerTest {

    @Test
    void masksEmailLocalPart() {
        assertThat(DataMasker.maskEmail("alice@example.com"))
                .isEqualTo("a***@example.com");
    }

    @Test
    void masksPhoneExceptLastFourDigits() {
        assertThat(DataMasker.maskPhone("+84 901 234 567"))
                .isEqualTo("***4567");
    }

    @Test
    void redactsMalformedEmail() {
        assertThat(DataMasker.maskEmail("not-an-email"))
                .isEqualTo("[redacted]");
    }
}
```

Testing log output:

1. Attach a test appender or capture logging backend output.
2. Send requests containing dummy emails, phone numbers, tokens, and search queries.
3. Exercise both success paths and error paths.
4. Assert output contains none of the raw secret/PII values.
5. Assert request IDs and error codes are still present for correlation.
6. Assert stack traces, causes, and nested exceptions leak no sensitive data.
7. Assert metric labels and span attributes contain no IDs or query literals.

Include a dedicated canary string in tests, such as `SECRET_CANARY_9f31`, and scan all test logs/traces for it. If it appears anywhere, the redaction policy has a gap.

## 22. Common Mistakes

| Symptom | Possible Cause | Fix |
|---|---|---|
| Logs contain full customer documents | Direct entity logging or `toString()` includes fields. | Log allowlisted event fields; omit sensitive fields from `toString()` and stop dumping entities. |
| Tokens appear in HTTP logs | Wire logging records headers/bodies. | Disable body/header logging or redact `Authorization`/`Cookie` at transport/proxy. |
| Exception messages contain user data | Logging raw `getMessage()` or stack traces. | Log error codes/types and route scrubbed traces to a restricted sink when needed. |
| APIs return stack traces | Handlers expose exception messages/causes to clients. | Return `ProblemDetail` with generic messages and request IDs. |
| Traces contain emails/search terms | Attaching raw requests to span attributes or URLs. | Allowlist attributes and use route templates. |
| MDC leaks across requests in reactive apps | Using `ThreadLocal` without context propagation/cleanup. | Use Reactor Context and Micrometer context propagation. |
| Logs contain forged multi-line entries | Input contained newlines/control characters. | Use structured logging and sanitize user-controlled fields. |
| Metric storage cardinality spikes | Using user/document/request IDs as tags. | Use bounded-cardinality labels like operation/outcome/error code. |
| Masked emails still expose info | Masked only local part while keeping domain/length. | Assess threat model; use full redaction or HMAC if stricter privacy is needed. |
| Hashed IDs are guessed | Using unkeyed hashes on predictable inputs. | Use HMAC with a securely managed secret key. |
| Dead-letter stores keep PII long-term | Saving full payloads with no retention. | Minimize payloads, encrypt, restrict access, and auto-expire. |
| Log redaction regex misses leaks | Filtering only final strings while formats change. | Keep sensitive data out of logs upfront; use schema allowlists and canary tests. |

## 23. Safe Logging, Tracing, and Error Handling Workflow

1. **Classify data:** mark secrets, PII, business identifiers, free text, and technical metadata.
2. **Define purpose:** which operational questions must logs/traces answer?
3. **Select allowlists:** emit only required operation, alias, outcome, duration, count, error code, and correlation IDs.
4. **Choose handling:** strip completely, mask, or HMAC per purpose.
5. **Design exception mapping:** never pass raw exception messages into API responses.
6. **Control client logging:** disable or redact HTTP wire/query/body/header logs.
7. **Manage context:** use technical request IDs/trace IDs; keep PII out of MDC/baggage.
8. **Govern metrics:** never use identifiers or free text as tags.
9. **Protect storage:** enforce access control, encryption, retention, auditing, and deletion.
10. **Test:** capture log/trace/error outputs and scan for canary secrets.
11. **Review changes:** whenever adding entity fields, queries, or tracing instrumentation, re-verify for leaks.

## 24. Key Takeaways

- Logs, traces, exceptions, metric labels, and API responses can all leak sensitive data.
- Favor data minimization and allowlists; never log raw entities, request bodies, or Query DSL.
- Secrets such as passwords, tokens, keys, and cookies must be stripped completely.
- Masking can still reveal information; HMAC pseudonymization correlates events while still requiring key protection.
- Entity/Lombok `toString()` can expose every field; use dedicated log DTOs/events and field allowlists.
- `exception.getMessage()` and stack traces can contain queries, URLs, indices, or input data.
- Return error codes, generic messages, and request IDs; never return stack traces to clients.
- Trace spans should carry only approved technical attributes; keep PII out of span names and baggage.
- `ThreadLocal`-based MDC needs care in reactive pipelines; use Reactor Context/context propagation.
- Never enable full HTTP wire logging in production without reliable redaction.
- Never use emails, document IDs, queries, or trace IDs as metric labels.
- Dead-letter payloads need encryption, access control, auditing, and retention limits.
- Protect log storage with access controls, encryption, retention, and incident response procedures.
- Test actual outputs using canary strings to catch leaks.

Redacting data across logs, traces, and error messages is part of data-flow design, not just logger configuration. Decide upfront which data may appear, build log events from allowlists, keep internal exceptions out of public responses, propagate technical correlation IDs through Reactor Context, and test actual outputs. That gives operators the signals they need to resolve incidents without turning logs and traces into uncontrolled copies of business data.

## References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [OpenTelemetry — Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/)
