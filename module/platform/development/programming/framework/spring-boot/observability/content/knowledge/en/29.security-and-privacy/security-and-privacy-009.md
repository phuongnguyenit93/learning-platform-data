# PII in Spring Boot Application Logs

In the **Security and Privacy** chapter of the **SPRING_BOOT_OBSERVABILITY** module, PII (Personally Identifiable Information) is information that can identify an individual directly or when combined with other data. Logs help investigate errors and understand application behavior, but if too much data is recorded, the log pipeline can become a central store of emails, phone numbers, addresses, account identifiers, tokens, or sensitive request contents.

The goal of secure logging is to retain enough technical context for operations and investigation while minimizing the personal data collected, displayed, stored, and shared. An effective approach starts with data minimization and field allowlists; masking/redaction acts as an additional defense layer when sensitive data cannot be completely avoided. You should never rely on a single regex to sanitize every log message.

In **SPRING_BOOT_OBSERVABILITY**, logs are one signal correlated with metrics and distributed tracing. Trace ID, Span ID, and event name are usually sufficient to find the exact request in the trace backend; raw payloads, credentials, or PII do not need to be copied into every log line. This lesson covers classifying PII, designing structured logging, protecting requests/responses and exceptions, configuring Spring Boot/Logback, governing access/retention, and testing for data leaks.

## 1. What Is PII in the Context of Logging?

PII is data that can identify or link to an individual. The exact scope depends on laws, contracts, industry regulations, and organizational policies. A field that looks harmless on its own can still become PII when combined with other fields.

| Data Category | Examples | Risk When Logged |
| --- | --- | --- |
| Direct identifiers | Full name, email, phone number | Searching and identifying individuals |
| Government identifiers | National ID, passport, tax ID | High risk if leaked or retained too long |
| Address/location | Home address, coordinates, location history | Exposes residence or movement habits |
| Account | Username, customer ID, account number | Links activity to an individual |
| Financial | Card number, bank account, transactions | Fraud and financial loss |
| Authentication data | Password, access token, session cookie | Account takeover |
| Health data | Medical records, diagnoses, lab results | Special-category sensitive data |
| Free-form content | Comments, search terms, request bodies | Can contain any personal information |

Not every identifier is classified identically under every policy. Nevertheless, request ID, user ID, tenant ID, or IP address can still link to users and carry high cardinality. Evaluate both privacy and metric cardinality before putting them into logs/traces/metrics.

### Sensitive Data Lives Beyond the Body

PII and secrets can appear in URL paths and query parameters; HTTP headers such as `Authorization`, `Cookie`, `Referer`, or custom headers; JSON/XML request and response bodies; exception messages and stack contexts; SQL parameters, ORM debug output, and database error details; JMS message properties/payloads; MDC, tracing baggage, and custom span attributes; filenames, object storage paths, and queue names constructed from user data.

Therefore, "do not log the request body" is still insufficient if an access token sits in a header or an email sits in a query string.

## 2. Data Minimization Is the First Line of Defense

The most important rule is to record only fields genuinely required for operations. If a field does not help answer a debugging/monitoring question, do not collect it.

Instead of logging the entire request:

```json
{
  "event": "customer.update",
  "requestBody": {
    "name": "Nguyen Van A",
    "email": "person@example.com",
    "phone": "+84...",
    "address": "...",
    "password": "..."
  }
}
```

Record only the minimal event and outcome:

```json
{
  "event": "customer.update",
  "operation": "update-profile",
  "result": "success",
  "http.route": "/customers/{customerId}",
  "http.status_code": 200,
  "duration_ms": 42
}
```

The second example still supports analyzing routes, outcomes, and latency without copying profiles or passwords into logs. If a specific workflow must be distinguished, use correlation/trace context or an approved internal identifier with access controls.

Before adding a new field, answer three questions:

1. Which operational or security use case does this field serve?
2. Can the goal be met with an aggregate value, category, or less sensitive identifier?
3. Who needs access to the field, how long is it retained, and when can it be deleted/anonymized?

## 3. Distinguishing Masking, Redaction, Hashing, and Tokenization

| Technique | How It Works | When Appropriate | Limitations |
| --- | --- | --- | --- |
| Masking | Hides part of a value | Support display, e.g., masked email | Still identifiable if too many characters remain |
| Redaction | Removes or replaces with a placeholder | Tokens, passwords, card numbers, unneeded content | Original value cannot be recovered |
| Hashing | Produces a one-way digest | Comparing/grouping values if clearly justified | Low-entropy values can be guessed; hashes remain linkable data |
| Tokenization | Replaces value with a reference token | Needs controlled linkage via a vault system | Tokens can still be sensitive; vault requires protection |
| Truncation | Keeps only a non-identifying portion | Format or version diagnostics | Can still leak data |

Do not use masking as an excuse to log every field. For example, a partially masked email can still identify a user. Hashing an email does not automatically make data anonymous; if it is linkable or dictionary-searchable, privacy risks remain.

For passwords, access tokens, refresh tokens, session cookies, and private keys, the right choice is usually not recording them or full redaction—never partial masking.

## 4. Structured Logging and Field Allowlists

Structured logging records events as explicitly named fields. It helps backends filter and query by service, operation, outcome, route template, and trace context.

Safer log event example:

```json
{
  "timestamp": "2026-11-22T10:15:30Z",
  "level": "INFO",
  "service.name": "customer-service",
  "event.name": "customer.profile.updated",
  "http.request.method": "PATCH",
  "http.route": "/customers/{customerId}",
  "http.response.status_code": 200,
  "duration_ms": 42,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

The field set is pre-selected and excludes raw URLs, payloads, `Authorization` headers, or emails. The field names here are examples; your system should align on a consistent schema and semantic conventions.

An allowlist is generally safer than a denylist. A denylist hides only known fields; new payloads or custom headers can slip through. An allowlist emits only approved fields, so new data is excluded from logs by default.

An event schema should specify a stable event name; service/deployment identity; operation or route template; outcome/status and duration; normalized error type when needed; Trace ID/Span ID if present; and business identifiers that have passed privacy/security review.

## 5. Never Log Full HTTP Requests/Responses

Convenient debugging shortcuts like serializing entire request objects, logging bodies, or enabling wire logging can record PII and secrets. In particular, request/response bodies can contain unpredictable data.

Avoid patterns like:

```java
log.info("Request: {}", objectMapper.writeValueAsString(request));
log.debug("Authorization: {}", request.getHeader("Authorization"));
log.info("URL: {}", request.getRequestURL() + "?" + request.getQueryString());
```

Replace them with logs containing selected fields:

```java
log.info(
        "Customer profile update completed: route={}, status={}, durationMs={}",
        "/customers/{customerId}",
        200,
        durationMs);
```

This example uses parameterized logging to avoid unnecessary string construction. In a real system, a structured logger/JSON encoder should emit distinct fields rather than free-form string interpolation.

If payload debugging is necessary in an isolated environment, use synthetic data or a sanitized copy. Never enable production body logging for extended periods to investigate an incident without appropriate filtering, access controls, and retention.

## 6. Protecting HTTP Headers and URLs

| Header | Why Sensitive | Handling |
| --- | --- | --- |
| `Authorization` | Bearer/basic credentials | Redact completely |
| `Cookie` / `Set-Cookie` | Session IDs and auth state | Redact completely |
| `Proxy-Authorization` | Proxy credentials | Redact completely |
| `X-Api-Key` | API key | Redact completely |
| `Referer` | May contain personal queries/paths | Drop or normalize |
| `X-Forwarded-For` | IP address chain | Keep only with clear purpose and policy |
| Custom tenant/user headers | Can identify individuals/organizations | Allowlist or pseudonymize per policy |

URLs must be normalized before logging. Use route templates such as `/customers/{customerId}` and drop query parameters unless there is an allowlist of safe fields. Do not just strip the query string and keep the raw path if path variables contain emails, phone numbers, or account IDs.

If analyzing a query option is necessary, log a normalized category or boolean such as `include_history=true` rather than the raw query string.

## 7. Redaction in Logback

Spring Boot typically uses Logback as the default logging backend when using the logging starter. Encoders/layouts or filters can be used as needed to control output. A durable approach is passing only sanitized fields to the logger; regexes over the full rendered message should be an extra defense layer, never the primary layer.

Example utility for masking emails in a controlled display use case:

```java
final class LogSanitizer {
    private LogSanitizer() {
    }

    static String maskEmail(String email) {
        if (email == null || email.isBlank()) {
            return "[redacted]";
        }
        int at = email.indexOf('@');
        if (at <= 1) {
            return "[redacted]";
        }
        return email.charAt(0) + "***" + email.substring(at);
    }
}
```

Email masking is only an example and does not prove the email is anonymized. In most log events, it is best not to record email at all. If a business/security use case genuinely needs to correlate user events, use an approved internal subject reference or a tokenization service.

Do not write a sanitizer that handles only a few field names while allowing arbitrary objects to be serialized. Design an allowlist schema before serialization.

### Why Regex Filters Easily Fail

Regexes over rendered log lines can miss JSON nested fields or escape sequences; URL encoding/base64; multiline exception messages; header names with mixed casing; PII in deeper exception causes; and XML, protobuf, or binary-to-text payloads.

If post-serialization redaction is unavoidable, use a format-aware parser and test against data variants. Never assume a single regex understands every structure.

## 8. Exception Messages and Stack Traces

Stack traces are helpful for pinpointing where an error occurred, but exception messages can contain user data or secrets. For example, validation errors may embed raw emails, account numbers, or request parameters directly into the message.

Practices:

- Record normalized exception classes/types.
- Retain stack traces when needed and after evaluating storage/access controls.
- Never put raw exception messages into metric tags or event names.
- Sanitize messages at boundaries if they could contain sensitive data.
- Avoid logging the same exception repeatedly in controller, service, and global handler if doing so adds no new context.
- Never log tokens or request objects inside error handlers.

Example:

```java
catch (PaymentGatewayException ex) {
    log.error(
            "Payment authorization failed: dependency={}, errorType={}",
            "payment-gateway",
            ex.getClass().getSimpleName());
    throw ex;
}
```

If a stack trace is needed, pass the exception as the final argument per your configured logging API after confirming its message/cause contains no PII or secrets. When that cannot be guaranteed, emit a sanitized exception type/event and keep details in a more tightly protected system.

## 9. MDC, Trace ID, and Baggage

MDC is commonly used to attach Trace ID, Span ID, or correlation fields to every log line. This is a helpful way to link logs with distributed traces without logging payloads.

JSON log example:

```json
{
  "message": "Inventory reservation completed",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "service.name": "orders-service"
}
```

Trace ID and Span ID are usually not direct PII, yet they remain identifiers capable of linking activity. Control access permissions, retention, and ID-based queryability. Never use them as metric tags due to high cardinality.

Tracing baggage is key-value context that can propagate across service boundaries. Never put emails, phone numbers, account numbers, access tokens, or sensitive data into baggage. Baggage can be transmitted across multiple services and exporters, expanding the exposure scope beyond expectations.

Propagate only allowlisted keys that are small, have finite values, or have passed privacy review. Trace attributes also require redaction/allowlists; tracing is not a safe storage zone by default.

## 10. SQL, JDBC, and Database Logs

SQL logging can inadvertently record literal values or bind parameters—for instance, queries with emails or account numbers in a `WHERE` clause. ORM debug logging and JDBC proxy tools can print SQL with substituted parameters or parameter values.

Do not enable SQL bind parameter logging in production without evaluating the data. Prefer logging operation/repository names or normalized query fingerprints; database duration and outcome; use DB slow-query tooling with dedicated access permissions and retention; redact sensitive parameters before logging if genuinely needed; and avoid logging connection strings containing usernames/passwords.

Database observability should link query duration with traces/spans and datasource metrics. You do not need to log full SQL parameter values into application logs to know which query is slow.

## 11. JMS and Message Payloads

Message payloads can carry customer, payment, or authentication data. Never log entire JMS messages when a consumer fails. Log a normalized destination, message type, schema version, outcome, and Trace ID if appropriate.

Never turn JMS Message ID, Correlation ID, customer ID, or order ID into metric tags. These identifiers may be logged in secured logs when an approved investigation purpose and retention exist; message bodies require allowlisting/redaction before logging.

If failed messages must be reprocessed, use a DLQ/replay mechanism with access control and auditing. Logs should only keep enough metadata to locate the message in the broker via a controlled procedure, rather than copying sensitive payloads into every sink.

## 12. Protecting the Log Pipeline and Storage

| Layer | Required Controls |
| --- | --- |
| Application | Data minimization, allowlists, redaction |
| Agent/collector | TLS, access credentials, avoid debug payload dumps |
| Transport | Authentication, encryption, bounded buffering |
| Storage | Encryption at rest, tenant isolation, retention |
| Query/UI | RBAC, least privilege, query/export auditing |
| Export/download | Approval, watermarking/auditing if policy requires |
| Deletion | Clear TTL, legal hold, and deletion workflows |
| Backup/archive | Same controls and retention as primary data |

Never send logs containing PII to a SaaS/third-party backend before verifying data residency, processing agreements, access scope, and retention. Generating a log inside a private network does not make it automatically safe once forwarded.

## 13. Retention and Access Permissions

Logs should be retained only for as long as defined for operations, security investigations, and legal requirements. Never set infinite retention simply because storage is cheap.

A policy may tier operational logs, security/audit logs, restricted logs, and archives; each tier needs appropriate retention, access permissions, and deletion workflows. Do not apply a single retention number across all organizations. Determine purpose, data categories, legal/contractual obligations, and deletion procedures. When no valid purpose remains, delete or anonymize per policy; backups/archives must be accounted for as well.

Access permissions should follow least privilege. Developers do not necessarily need read access to all production logs. Use task-based roles, audit searches/exports, and restrict bulk downloads or queries by personal identifiers.

## 14. Testing to Prevent PII Leakage Into Logs

Logging policies must be tested automatically as a security requirement:

1. Build a test request with a synthetic PII marker, e.g., email `pii-test-482@example.invalid`.
2. Send a synthetic `Authorization` header with marker `SECRET_TEST_TOKEN`.
3. Send query strings and bodies containing synthetic sensitive markers.
4. Trigger a validation exception whose message contains the marker.
5. Capture logs using a test appender or output stream.
6. Assert the markers do not appear in log output.
7. Assert required operational fields such as event, route template, outcome, and trace ID remain present.
8. Inspect exception causes, nested fields, and multiline logs.
9. Verify MDC/baggage do not emit sensitive fields into output.
10. Run tests across HTTP, JDBC, and JMS logging paths if the application uses them.

Simple JUnit test example:

```java
@Test
void shouldNotWriteSensitiveMarkersToLogs() {
    String logs = captureLogs(() -> customerController.update(
            requestWithEmail("pii-test-482@example.invalid")));

    assertThat(logs).doesNotContain("pii-test-482@example.invalid");
    assertThat(logs).doesNotContain("SECRET_TEST_TOKEN");
    assertThat(logs).contains("customer.profile.updated");
}
```

This is pseudocode; how capture works depends on your Logback test appender and test framework. Use synthetic data—never real customer data—in test fixtures. Assert both content and schema, because deleting all logs would also pass a "contains no PII" check while destroying operability.

### Auditing Logging Configuration

Review specific logger levels and packages: HTTP client wire logging; Spring Web request/response logging; Hibernate SQL and bind parameter logging; JDBC proxy logging; JMS provider/client debug logging; Security/authentication debug logging; exception handlers and request logging filters.

A temporary `DEBUG` setting can drastically change what data is logged. Procedures for enabling production debug logging require an approver, narrow logger scope, automatic expiration, and output inspection before broad rollout.

## 15. Responding When PII Has Been Logged

If PII is detected in a log sink:

1. Identify the field, event, service, timeframe, and receiving sinks.
2. Stop the source from continuing to emit data via allowlist/redaction or disabling the specific logger per procedure.
3. Restrict access and exports to affected indexes/objects.
4. Identify affected retention tiers, replicas, archives, and backups.
5. Execute deletion/containment according to incident response and legal/privacy policies.
6. Assess whether regulatory or contractual notifications are required.
7. Add regression tests and inspect the pipeline to prevent recurrence.

Never delete audit/security evidence unilaterally before coordinating with the incident owner and retention policies. You must balance containment, evidence preservation obligations, and data-subject rights.

## 16. Scenario Exercise

A team enables `DEBUG` for the HTTP client and Logback for 30 minutes to investigate a payment failure. The log backend begins receiving `Authorization` headers, emails in query strings, and response bodies containing customer addresses. Logs are forwarded to a centralized platform accessible to many developers.

**Questions:**

1. Which PII/secret sources are being logged?
2. Why is adding a regex to mask emails insufficient?
3. How should the logging strategy change so errors can still be investigated?
4. Who needs to be notified/consulted once logs have been forwarded?
5. Which tests are needed to prevent this incident from recurring?

**Analysis Hints:**

- `Authorization` headers are secrets requiring complete redaction; query strings and response bodies contain PII; wire logging can capture far more data than expected.
- Regexes can miss URL encoding, JSON nested fields, multiline exceptions, or other formats. Event field allowlists and disabling body/header logging form the primary defense.
- Retain normalized event, route template, status, duration, error type, Trace ID/Span ID, and dependency name. Use the trace backend for flow inspection and controlled logs for investigation.
- Incident owners, security/privacy teams, data owners, and log platform owners assess scope, access, retention, deletion, and notification obligations per policy.
- Use synthetic PII/token markers in integration tests, checking appender output, nested exceptions, headers, query strings, bodies, MDC, and `DEBUG` logger configs.

### Completion Checklist

| Topic | Can Explain / Verify |
| --- | --- |
| PII | Identify direct data and linkable data |
| Data minimization | Record only fields serving a clear purpose |
| Allowlist | Choose safe log schemas instead of serializing whole objects |
| Masking/redaction | Pick appropriate techniques; secrets must be completely removed |
| HTTP | Do not log raw bodies, auth headers, cookies, or free-form queries |
| Exceptions | Control messages, causes, and stack contexts |
| MDC/baggage | Keep Trace ID useful; never propagate PII |
| JDBC/JMS | Avoid sensitive bind parameters and message payloads |
| Storage/access | Encryption, RBAC, auditing, retention, and deletion |
| Testing | Use synthetic markers to verify PII never appears |
| Incident response | Contain, scope, preserve evidence, and remediate per policy |

**Takeaway:** Logs are a data copy that can be forwarded, indexed, searched, exported, and stored in backups. Start with data minimization and field allowlists; use redaction for secrets and unavoidable data, but never rely on regex as the sole defense. Control headers, URLs, exceptions, SQL, JMS payloads, MDC, and tracing baggage. Protect the log pipeline with encryption, least-privilege access, auditing, and clear retention; test with synthetic PII markers to ensure logs remain useful without exposing personal data.
