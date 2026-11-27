# Masking Sensitive Data

In the **Logging** chapter of the **SPRING_BOOT_OBSERVABILITY** module, logs are critical evidence for investigating errors, latency, and application behavior. However, logs typically traverse multiple components: the Spring Boot application, SLF4J/Logback, appenders or agents, the OpenTelemetry Collector, and storage backends. If logs contain passwords, access tokens, session cookies, personal data, or payment details, every copy becomes a potential leak point.

**Masking sensitive data** means transforming or removing portions of data that must not appear in logs before they reach anywhere they can be stored or queried. A solid strategy combines preventing emission at the source, structured logging, attribute allowlists, tested filters/redaction, and access/retention controls. You should not rely on a single regex at the end of the pipeline to protect all data.

The **SPRING_BOOT_OBSERVABILITY** module focuses on Micrometer Observation, metrics, logs, and distributed tracing. Therefore, this lesson also covers how to protect data in MDC, trace/span attributes, baggage, and exception logs so correlation remains useful without copying secrets or PII into telemetry.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify secrets, PII, payment data, and internal data that must not be logged.
2. Distinguish masking, redaction, hashing, tokenization, and encryption.
3. Design an allowlist for structured logging instead of logging entire objects/requests.
4. Prevent sensitive data from appearing in messages, arguments, exceptions, MDC, and HTTP/gRPC metadata.
5. Choose the right handling location across the application, logging framework, and telemetry pipeline.
6. Configure testable Logback/SLF4J filters without depending on brittle regexes.
7. Protect logs, traces, and baggage when integrating Micrometer Tracing/OpenTelemetry.
8. Write tests verifying sensitive data does not appear in output.
9. Establish a runbook when sensitive data is discovered in logs.
10. Balance investigability against privacy, cost, and retention policies.

## 2. Why Do Logs Need Protection?

A log record can pull data from many sources:

- Messages written by developers.
- Arguments passed to the logger.
- Objects serialized into JSON.
- Exception messages, causes, and stack traces.
- MDC or logging context such as user, tenant, or request ID.
- HTTP request/response headers and bodies.
- gRPC metadata and message fields.
- Trace/span attributes or baggage copied into logs.
- Data logged directly by third-party libraries.

Even when application code does not intentionally log passwords, exceptions from HTTP clients, ORMs, authentication libraries, or request decoders can still contain URLs, query parameters, headers, or payloads.

| Risk | Impact |
| --- | --- |
| Leaked password, API key, access token, or cookie | Anyone with log read access can replay credentials to access systems. |
| Leaked email, phone number, address, or identifier | Violates privacy, internal policy, or applicable regulations. |
| Leaked sensitive payment data | Expands blast radius and incident-response obligations. |
| Logs containing session IDs or reset tokens | Enables session hijacking or acting on a user's behalf. |
| Data attached to traces/baggage | Telemetry spreads across multiple services and backends. |
| Logging large full payloads | Increases storage/indexing cost and data-exposure risk. |

Logs often have broad access: developers, operators, support, SIEM systems, APM vendors, or anyone with query permissions. Never assume that because logs sit inside an internal system, data can be written freely.

## 3. Classify Data Before Logging

A policy must specify which data may be logged, which must be transformed, and which is prohibited.

| Data category | Examples | Default handling |
| --- | --- | --- |
| Secrets/credentials | Password, API key, bearer token, private key, session cookie | Never log; if accidentally emitted, redact and treat as an incident. |
| Sensitive payment data | Security code, magnetic-stripe data, authentication data | Never log. |
| PII | Email, phone number, address, date of birth, personal identifier | Drop or mask according to purpose and policy. |
| Transaction identifiers | Order ID, payment reference, request ID | Log only when needed; control access, cardinality, and retention. |
| Operational metadata | Service, route template, operation, status, duration | Generally safe to log if it reveals no private data. |
| Public configuration data | Feature flag name, operation type | Safe to log after reviewing content. |

Actual classification must follow your organization's data classification policy and applicable legal/industry requirements. Never assume a value is safe to log simply because it does not look like a password.

### Allowlist-First Design

For structured logs, pick only approved fields:

~~~java
log.atInfo()
        .addKeyValue("operation", "payment.authorize")
        .addKeyValue("outcome", "rejected")
        .addKeyValue("payment.reference", safeReference)
        .log("Payment authorization completed");
~~~

This example does not serialize the entire `PaymentRequest`. Only fields serving a concrete investigation purpose are selected.

Do not use:

~~~java
log.info("Payment request: {}", request);
log.debug("Headers: {}", allHeaders);
log.info("User: {}", user);
~~~

Calls like these can trigger `toString()` or serializers holding sensitive fields, even if the author intended `DEBUG`-only logging. Disabling `DEBUG` in production is not a standalone safeguard: log levels can change, and exceptions or other loggers can still emit the same object.

## 4. Distinguishing Masking, Redaction, Hashing, Tokenization, and Encryption

| Technique | How it works | Example | Limitation |
| --- | --- | --- | --- |
| **Masking** | Hides part of a value while keeping part for recognition. | `a***@example.com` | Remaining part can still be PII; unsuitable for secrets. |
| **Redaction** | Removes the value or replaces it with a placeholder. | `Authorization: [REDACTED]` | Loses visibility into original value; must apply on every write path. |
| **Hashing** | One-way transformation into a digest. | Hash of a reference. | Low-entropy values can be guessed; deterministic hashes still link activity. |
| **Tokenization** | Replaces value with a token; mapping protected in another system. | Card reference to token. | Requires a token vault and mapping access controls. |
| **Encryption** | Reversible encoding using a key. | Encrypted field in storage. | Key holders can decrypt; does not replace data minimization. |

### When to Use Which Technique?

- Passwords, access tokens, API keys, and private keys: **never log**. If already in the pipeline, strip the value and consider rotating/revoking the credential.
- Emails or phone numbers: usually redact or mask as required. Only hash when there is a clear linking purpose, proper controls, and dictionary-attack evaluation.
- Payment/card data: never log sensitive data; use a reference/token designed by the payment system to appear in logs.
- System-generated request IDs: safe to log if free of identifying data and governed by proper retention.
- Passwords: never hash and log. Password hashing for authentication storage is a separate workflow; logs are not a place to store verifiers.

Masking does not automatically make data anonymous. A partially masked email can still identify a user when combined with timestamps, tenant, and IP address. Assess re-identification risk across the full context.

## 5. Prefer Prevention at the Source

The most effective control is keeping sensitive data out of log events from the start. This reduces reliance on regexes, appenders, and downstream pipelines.

### Do Not Log Full Requests/Responses

Instead of serializing the request, pick operational facts:

~~~java
log.atInfo()
        .addKeyValue("operation", "order.create")
        .addKeyValue("http.route", "/orders")
        .addKeyValue("http.status_code", 201)
        .addKeyValue("order.item_count", request.items().size())
        .log("Order created");
~~~

Do not log the request body just to see which endpoint a request hit. If you need to investigate failing payloads, build a filtered descriptor with an explicit schema, size cap, and access controls.

### Do Not Log Credentials or Raw Headers

~~~java
// Avoid: header map may contain Authorization and Cookie.
log.debug("Outbound headers: {}", headers);

// Recommended: log only selected safe attributes.
log.debug("Calling inventory service, method={}, route={}",
        "POST", "/inventory/reserve");
~~~

If you need to know the authentication scheme, log only a classified value such as `auth.scheme=bearer`; never log the raw `Authorization` header.

### Do Not Rely on `toString()`

Never log DTOs, entities, or library objects directly without checking their `toString()`, JSON annotations, and custom serializers. Future model changes can add a new field and cause logs to start capturing sensitive data without any change to logging code.

Create a dedicated log view/record containing only permitted fields. Never reuse a request DTO as a log schema.

## 6. Masking in SLF4J and Logback

Spring Boot commonly uses the SLF4J facade with Logback as the default logging backend. You can combine structured logging with a sanitization/filter layer before appenders or before telemetry forwarding.

Example of an application-layer value transformer:

~~~java
public final class SensitiveDataMasker {

    private SensitiveDataMasker() {
    }

    public static String maskEmail(String email) {
        if (email == null || email.isBlank()) {
            return email;
        }

        int at = email.indexOf('@');
        if (at <= 1 || at == email.length() - 1) {
            return "[REDACTED]";
        }

        return email.charAt(0) + "***" + email.substring(at);
    }

    public static String redactSecret(String value) {
        return value == null ? null : "[REDACTED]";
    }
}
~~~

This helper only illustrates masking one field type. It is not a general-purpose filter for arbitrary log text. Never rely on a simple email helper as your sole safeguard because emails vary in format and data can sit inside JSON, exceptions, or headers.

Usage:

~~~java
log.atInfo()
        .addKeyValue("customer.email",
                SensitiveDataMasker.maskEmail(customer.email()))
        .addKeyValue("operation", "profile.lookup")
        .log("Customer profile lookup");
~~~

For secrets, prefer omitting them from the event entirely. If you need to confirm a header existed, log only a boolean or authentication type:

~~~java
log.atDebug()
        .addKeyValue("authorization.present", authorizationHeader != null)
        .log("Outbound authentication metadata prepared");
~~~

### Filters in Logback

A Logback filter or converter can transform output at the logging backend. However, placement matters greatly:

- Filters only decide whether to accept or deny an event; not every filter modifies bodies/arguments.
- Converters typically transform presentation inside a layout; if an OTel appender or file appender reads raw events/structured arguments, layout masking will not protect those paths.
- A `TurboFilter` can block events before output creation, though it does not automatically redact individual fields.
- A custom appender can normalize events into a safe schema prior to export.

If using Logback masking, verify where raw events are read and test every appender. Masking a string in a console layout does not prove the JSON appender, file appender, async appender, or OpenTelemetry appender is also protected.

## 7. Structured Logging and Safe Schemas

Structured logging clarifies which fields are permitted, reducing reliance on regex parsing of message text.

~~~json
{
  "event.name": "payment.authorization",
  "operation": "authorize",
  "outcome": "rejected",
  "payment.reference": "pay_ref_7f31",
  "error.type": "LimitExceededException"
}
~~~

The schema excludes PAN, security codes, bearer tokens, customer emails, and payment payloads. Fields should have stable types and semantics for cross-service querying.

### Using a Safe Event Object

~~~java
public record PaymentLogEvent(
        String operation,
        String outcome,
        String paymentReference,
        String errorType) {
}
~~~

~~~java
PaymentLogEvent event = new PaymentLogEvent(
        "authorize",
        "rejected",
        paymentReference,
        "LimitExceededException");

log.atWarn()
        .addKeyValue("operation", event.operation())
        .addKeyValue("outcome", event.outcome())
        .addKeyValue("payment.reference", event.paymentReference())
        .addKeyValue("error.type", event.errorType())
        .log("Payment authorization rejected");
~~~

`paymentReference` must be an identifier permitted by policy, not a card number or auth token. Do not put the entire exception message into `error.type`; use a stable class/category and a controlled message.

## 8. Exceptions and Stack Traces Can Also Expose Data

Downstream errors can include full URLs, query strings, request bodies, or response bodies. Exceptions can embed input values in their messages. Logging full exceptions helps in many investigations, yet you must assess content and transport paths.

Avoid:

~~~java
log.error("Payment failed for request {}", request, exception);
~~~

A safer approach logs operation, safe reference, error category, and the exception according to policy:

~~~java
log.atError()
        .addKeyValue("operation", "payment.authorize")
        .addKeyValue("payment.reference", safePaymentReference)
        .addKeyValue("error.type", exception.getClass().getSimpleName())
        .log("Payment authorization failed");
~~~

If a stack trace is required, inspect exception causes/messages before forwarding. You can map exceptions at boundaries into stable error types while keeping original exceptions in an access-restricted debug channel if permitted by policy. Do not strip all stack traces indiscriminately because that can erase vital evidence.

Changing only the message does not ensure a `Throwable` isn't attached by another logger overload. Verify actual call signatures and final output.

## 9. MDC, Trace Context, and Baggage

MDC commonly stores correlation fields like request ID, tenant tier, or trace ID so they appear in log patterns. Sensitive data placed here can propagate into vast numbers of log events.

Do not put raw emails or tokens into MDC:

~~~java
MDC.put("user.email", user.email());
MDC.put("authorization", bearerToken);
~~~

Add only necessary, approved fields:

~~~java
MDC.put("request.id", requestId);
MDC.put("tenant.tier", verifiedTenantTier);
try {
    orderService.create(request);
} finally {
    MDC.remove("request.id");
    MDC.remove("tenant.tier");
}
~~~

Use `try`/`finally` to prevent context from leaking into subsequent requests on the same thread. For async/reactive flows, use the corresponding context propagation mechanism; do not assume MDC crosses every executor automatically.

Micrometer Tracing can place trace ID/span ID into MDC. That supports correlation without making all baggage fields safe. Copy only allowlisted baggage fields into logging correlation. Avoid dumping the raw baggage map or full HTTP/gRPC metadata.

## 10. Protecting Traces and OpenTelemetry Attributes

Sensitive data can still leak via trace/span attributes even when log statements are masked. Auto-instrumentation may capture URLs, routes, database statements, exception events, or request attributes.

Check these points:

- Do URLs have query parameters containing tokens/emails?
- Do database statements contain literal customer data?
- Do exception events/messages contain sensitive payloads?
- Does baggage propagate to services that should not see that data?
- Do span attributes contain user IDs, account IDs, or identifying data?
- Does the Collector run processors/filters to drop or transform attributes before backend export?

Prefer avoiding creating sensitive attributes at the source. Collector filtering is an extra defense layer, not a replacement for preventing emission in the application. Once data is sent to a Collector, some information has already crossed the network and may be recorded by an agent/proxy before processors filter it.

Micrometer Observation low-cardinality/high-cardinality key-values require the same classification rules. Never attach emails, bearer tokens, or raw payloads to an observation context. High-cardinality does not mean a field is safe to export.

## 11. Masking Headers and Metadata in HTTP/gRPC

HTTP headers and gRPC metadata frequently carry authentication or session data. Never log the full collection.

Keys to drop or handle specially:
- `Authorization`
- `Proxy-Authorization`
- `Cookie` and `Set-Cookie`
- `X-Api-Key` or custom API key headers
- Session, CSRF, and password-reset headers
- Custom headers carrying identity/credentials

Header allowlist example:

~~~java
private static final Set<String> SAFE_HEADERS = Set.of(
        "content-type",
        "accept",
        "user-agent",
        "x-request-id"
);

public static Map<String, String> safeHeaders(
        Map<String, String> headers) {
    Map<String, String> safe = new LinkedHashMap<>();
    headers.forEach((name, value) -> {
        String normalized = name.toLowerCase(Locale.ROOT);
        if (SAFE_HEADERS.contains(normalized)) {
            safe.put(normalized, value);
        }
    });
    return safe;
}
~~~

This is an allowlist example for a simple map; real applications must handle multi-value headers, case insensitivity, and proxy-supplied data. Do not allowlist a header solely because its name looks familiar; inspect its contents and origin.

For gRPC, apply the same principle to `Metadata`. Never serialize entire metadata because it can contain authorization, binary entries, and propagation fields. W3C trace context/baggage should only enter logs per explicit policy; raw baggage is not safe by default.

## 12. Redaction in the Collector and Backend

The Collector can act as a centralized control layer for telemetry arriving from multiple services. Depending on version and distribution, processors can strip/transform attributes or filter logs prior to export.

~~~mermaid
flowchart LR
    App["Spring Boot app"]
    App --> Source["Safe logging at source"]
    Source --> Agent["Agent / Collector receiver"]
    Agent --> Filter["Redaction / allowlist processor"]
    Filter --> Backend["Logs / traces backend"]
    Backend --> Access["RBAC, retention, audit"]
~~~

Do not reuse a generic Collector processor config without verifying version/distribution support. Confirm the processor exists in the binary, applies to logs or traces as intended, and supports nested attributes/body removal at the required depth.

Principles:
- Place filters before exporters to the backend.
- Protect queues, debug exporters, and internal telemetry; they can also hold sensitive data.
- Never enable Collector debug logging in production if it prints raw payloads.
- Audit both the logs pipeline and the traces pipeline.
- Keep an audit trail for policy/processor changes.
- Verify that the filtered stream is the only copy reaching authorized storage.

Redaction at the Collector does not hide data already written earlier to a file appender, container stdout, sidecar, or network proxy. Inventory all telemetry destinations.

## 13. Regex Masking: Use with Limits

Regex can help catch simple patterns in text, but it is not a complete data classifier.

Regex easily fails when:
- Tokens span multiple lines or are URL/base64-encoded.
- JSON contains escaped characters or nested objects.
- `Authorization` headers vary in casing.
- Exception messages contain URLs/query parameters.
- Values appear under unexpected field names.
- PII follows international formats or varying delimiters.

If using regex:
1. Apply it to specific fields rather than scanning entire messages whenever possible.
2. Test valid, invalid, null, Unicode, multiline, and adversarial inputs.
3. Bound input length and avoid regexes prone to catastrophic backtracking CPU spikes.
4. Do not rely on regex to catch every secret.
5. Measure false positives and false negatives.
6. Keep allowlists and source prevention as the primary layer.

Do not mask every card-like digit sequence with a broad regex without understanding false positives; and never let regex substitute for simply not logging that data.

## 14. Testing to Guarantee Sensitive Data Never Leaks into Output

Tests must inspect **actual appender/pipeline output**, not just assert that a masker helper returns a string.

### Unit Test for the Masker

~~~java
class SensitiveDataMaskerTest {

    @Test
    void masksEmailLocalPart() {
        assertEquals(
                "a***@example.com",
                SensitiveDataMasker.maskEmail("alice@example.com"));
    }

    @Test
    void redactsSecretCompletely() {
        assertEquals(
                "[REDACTED]",
                SensitiveDataMasker.redactSecret("top-secret-token"));
    }
}
~~~

### Testing Logger Output

Use a test appender or Spring Boot's `OutputCaptureExtension` to emit events and verify:
- Synthetic secret values never appear.
- Placeholders or masked fields render properly.
- Exception messages/causes do not accidentally emit raw input.
- MDC is cleared after the request.
- Async events do not inherit a prior request's context.
- Both JSON appender and OpenTelemetry appender comply with policy.

Tests should use easily searchable canary strings, such as `CANARY_PASSWORD_91` or `CANARY_TOKEN_72`, never real secrets. Assert both the permitted output and the complete absence of the raw canary string across all captured logs.

### Testing Negative Cases

Test missing/null or mixed-case headers; multi-value headers; unexpected baggage fields; exceptions with URL query parameters; nested and multiline JSON; Unicode and oversized values; encoded inputs or alternate delimiters.

A masker whose unit tests pass can still be bypassed by another appender, `toString()`, an error handler, or an agent. Integration tests should cover real application emission paths.

## 15. Access Control, Retention, and Incident Response

Masking reduces risk, yet does not replace operational log safeguards:

- Apply least-privilege RBAC; developers should not have blanket read access to all production logs by default.
- Segregate tenants/environments and restrict queries by role.
- Set retention aligned with purpose and compliance requirements.
- Encrypt in transit and at rest; manage keys independently from the data.
- Audit exports, queries, downloads, and retention changes.
- Limit data inside alerts/notifications since alerts often forward to email/chat.
- Govern backups, archives, and log shipping; deleting from the primary backend does not delete every downstream copy.

### When a Secret or PII Is Found in Logs

1. Identify the field, time window, service, and every destination that received the data.
2. Stop further emission with a verified source fix/filter.
3. If it is a credential, coordinate rotation/revocation per incident policy.
4. Locate copies in stdout, files, sidecars, Collector queues, backends, backups, and exports.
5. Restrict access and adjust retention following incident procedures; do not prematurely destroy evidence that must be preserved.
6. Coordinate with security/privacy owners to decide on purging, notification, and reporting obligations.
7. Add regression tests and re-audit all logging paths.

Do not paste the exposed secret itself into tickets/chats as an example. Reference the field name, data category, service, and timestamp; keep concrete values inside an approved incident channel only if truly necessary.

## 16. Common Pitfalls

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Masked in console, but secret still in backend | Masking applied only in console layout; OTel/file appender reads raw event. | Test each appender and exporter independently. |
| Token appears in exception | HTTP client or library embeds request headers/URL in message. | Inspect exception message/cause and apply safe error mapping. |
| MDC leaks data to other requests | Context not cleared in `finally` or broken async propagation. | Verify cleanup and executor/reactive lifecycle. |
| PII appears in traces but not logs | Auto-instrumentation captures span attributes or exception events. | Inspect raw spans and Collector trace processors. |
| Regex misses some data | Encoding, nested JSON, unexpected field names, or multiline text. | Add schema allowlists and negative test cases. |
| Fields over-masked | Regex false positives or masking the entire message. | Target specific sensitive fields and use safe attributes. |
| Password still logged despite no direct log call | Object `toString()`/serializer or request dump. | Avoid object serialization; use a dedicated log event schema. |
| Collector redacts, yet sidecar file holds raw data | Filtering occurs after another destination already wrote the log. | Inventory destinations and enforce prevention at source. |
| Hash still links users | Deterministic hash or guessable input. | Evaluate entropy/linkability; consider tokenization or removal. |
| Alerts send PII | Notification template copies message/attributes verbatim. | Apply allowlist/redaction to alert payloads. |

## 17. Runbook: Verifying Masking in Spring Boot

1. **Inventory data:** list secrets, PII, payment data, identifiers, and internal fields per policy.
2. **Map logging paths:** SLF4J/Logback appenders, stdout, files, agents, OTel bridge, Collector, and backends.
3. **Locate data entry points:** request/response logging, object serialization, exception mapping, MDC, baggage, and instrumentation.
4. **Design allowlist schema:** enumerate allowed fields, types, owners, and purposes.
5. **Prevent at the source:** replace raw objects/headers/bodies with safe event fields.
6. **Add supplementary redaction:** filters/appenders/Collector for data that cannot be fully eliminated at source.
7. **Test canary values:** inject recognizable fake values and inspect all output destinations.
8. **Test failures and async:** exception chains, thread pools, Reactor, HTTP/gRPC metadata, and shutdown.
9. **Measure cost:** verify redaction introduces no CPU spikes, excessive log volume, or regex backtracking.
10. **Verify backend:** search for both raw and masked canary values; the raw value must not exist in any test index/destination.
11. **Audit access and retention:** verify RBAC, auditing, backups, and log shipping.
12. **Record evidence:** policy version, test results, owners, and review date.

## 18. Self-Check Exercises

### Exercise 1 — Is Console Masking Enough?

An application masks `Authorization` in a Logback console pattern, yet still runs a JSON file appender and an OpenTelemetry appender. Can you conclude the secret is protected?

**Answer:** No. Console layout affects presentation only for that appender. Other appenders can read raw events/arguments. You must test every destination or normalize into a safe event schema before fan-out.

### Exercise 2 — Hashing Emails Before Logging

A team SHA-256 hashes emails before logging them to correlate requests from the same user. Is this completely safe?

**Answer:** No. Emails have low entropy and are vulnerable to dictionary attacks; deterministic hashes also allow cross-activity linking. Assess purpose, access controls, and linkability; consider tokenization or a reference issued by a trusted system.

### Exercise 3 — Exception Containing a Token

Logs do not emit the `Authorization` header directly, yet an HTTP client exception contains a URL with an `access_token` query parameter. Where must you fix it?

**Answer:** Control URLs/credentials at the source, avoid placing secrets in query strings when the protocol supports safer headers, and sanitize exception messages/causes before logging/exporting. Do not rely solely on header filtering.

### Exercise 4 — Leaked MDC

One request puts a user identifier into MDC, and the next request on the same thread sees the stale value. What is the cause and fix?

**Answer:** MDC was not cleared when the prior request finished. Set and remove the field inside `try`/`finally` or use an appropriate request/context scope mechanism; also audit async propagation.

### Exercise 5 — Collector Redaction

The Collector strips `customer.email` before backend export. Does this guarantee container log files contain no emails?

**Answer:** No. Files/stdout can be written before telemetry ever reaches the Collector. Prevent emission at the source and verify every destination receiving data.

### Exercise 6 — Baggage as Log Fields

An application copies all baggage into MDC for easier debugging. What is the risk?

**Answer:** Inbound baggage can be caller-controlled, contain PII/secrets, or carry high-cardinality values. Copy only allowlisted, verified, purposeful fields; never log the entire baggage map.

## 19. Implementation Checklist

- [ ] A data classification policy exists for secrets, PII, payment data, and identifiers.
- [ ] Log statements prioritize allowlisted fields and safe event objects.
- [ ] Unreviewed requests/responses, entities, or objects are never serialized directly.
- [ ] Passwords, access tokens, API keys, cookies, private keys, and security codes are never logged.
- [ ] Emails/phones/PII are dropped or masked per policy; re-identification risk is assessed.
- [ ] Hashing/tokenization is used only with valid purpose, sufficient entropy, and access policy.
- [ ] Exception messages, causes, and stack traces are reviewed before export.
- [ ] MDC contains only permitted correlation fields and is cleaned up properly across its lifecycle.
- [ ] Baggage, trace/span attributes, and HTTP/gRPC metadata have dedicated allowlists.
- [ ] Every appender, agent, and Collector pipeline is verified; console masking alone is insufficient.
- [ ] Collector redaction is a supplementary defense, never the sole safeguard.
- [ ] Regexes have adversarial tests, input bounds, and do not replace schema allowlists.
- [ ] Integration tests use canary strings to confirm raw values never appear in output.
- [ ] RBAC, retention, encryption, audit, and backup policies have been reviewed.
- [ ] An incident runbook and credential rotation/revocation procedure exist for leaks.
- [ ] Alert/notification templates do not copy sensitive data.

**Remember:** Effective log protection begins by **not writing sensitive data**. Use schema allowlists and safe event fields at the source, reinforce with masking/redaction in the logging pipeline and Collector, and test every destination including files, stdout, traces, and backends. Masking, hashing, or encryption does not automatically render data anonymous or safe; policies must account for linkability, access control, retention, and the entire telemetry path.
