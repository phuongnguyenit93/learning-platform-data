# Masking Tokens, Passwords, and Personal Data in Logs or Error Messages

In a Spring Boot system integrating via HTTP clients, databases, caches, message brokers, and Spring Integration adapters, sensitive data passes through many layers: requests, headers, connections, message payloads, exceptions, logs, traces, and dead-letter queues. A single `log.error("request failed", exception)` or mis-enabled HTTP wire logging can write tokens or personal data into monitoring systems accessible to far more people and services than the origin system.

This lesson explains how to **keep secrets out of logs from the start**, how to mask or strip data when diagnostic logging is necessary, and how to design safe error messages that still provide enough context to operate integration flows. This is part of **connection security**: TLS encryption and storing passwords in a secret manager only protect certain legs; copies of data in logs, exceptions, and error messages still require independent control.

## 1. Learning Outcomes and Real-World Scenario

After this lesson, you can:

- Classify tokens, passwords, access keys, personal data, and safe diagnostic metadata.
- Spot places where Spring Boot/Spring Integration may accidentally log headers, request/response bodies, or secret-bearing exceptions.
- Design logging around an **allowlist of safe fields**, paired with redaction as a secondary defense layer.
- Return HTTP error messages conforming to a stable contract without leaking credential-bearing URLs, access tokens, input data, or stack traces.
- Control sensitive data in logs across HTTP clients, JDBC/JPA/MongoDB, caches, JMS/Kafka/RabbitMQ, and error channels.
- Test logs, responses, traces, and dead-letter data before releasing.
- Respond to incidents if secrets have already been written to logs or observability systems.

**Scenario:** an API receives a payment request, calls a partner using a bearer token, persists transaction state to a database, and emits an event to a broker. The partner returns `401` with a response body that may echo headers or customer data. If the app logs the raw exception or passes the partner's error content directly to callers, sensitive data spreads across multiple systems even when HTTPS is properly configured.

## 2. Classify Data Before Deciding What to Log

Not all values share the same sensitivity or diagnostic utility.

| Data Category | Examples | Practical Rule |
|---|---|---|
| **Authentication secrets** | Passwords, bearer/access/refresh tokens, API keys, session cookies, OTPs, private keys, credential-bearing connection strings | **Never log** to logs, metrics, traces, HTTP error responses, DLQ metadata, or support notices |
| **Personal data** | Names, emails, phone numbers, addresses, personal IDs, IPs depending on context, financial details | Use only with explicit purpose and access/retention controls; prefer omitting or pseudonymized IDs |
| **Protected business data** | Contract contents, balances, transaction payloads, customer data in messages | Never log full objects; log only operation type and classified status |
| **Relatively safe diagnostic metadata** | Static adapter name, operation type, HTTP status, internal error code, duration, retry count | Safe to log provided it contains no arbitrary user-supplied input |
| **Flow correlation IDs** | System-generated correlation ID, trace ID, random job ID | Safe for linking events; keep free of personal data and never use tokens as IDs |

Examples:

```text
UNSAFE
Authorization: Bearer eyJhbGciOi...
GET /partner/customer?email=example@domain.test&api_key=...
jdbc:postgresql://db.example/app?user=service&password=...
Message failed: CustomerUpdate(email=..., phone=..., accessToken=...)

ACCEPTABLE AFTER REVIEW
event=partner_call_failed
partner=billing
operation=createPayment
httpStatus=401
errorCode=UPSTREAM_AUTH_REJECTED
correlationId=7c8d...             # Application-generated random ID
durationMs=184
retryable=false
```

**"Masking" does not always mean keeping part of a value.** For tokens, passwords, and API keys, the default choice is **complete removal**. Showing the first/last few characters of a token can still help attackers correlate events or exploit short/predictable formats. If you genuinely need to recognize a repeated credential, use a system-managed identifier or a purpose-built keyed fingerprint with separate key and retention controls.

For emails, phone numbers, or customer identifiers, simple partial masking or plain hashing may not anonymize the data. *Pseudonymized* data still requires governance as linkable personal data.

## 3. Common Leak Paths in Spring Boot Integration

```mermaid
flowchart LR
    A["HTTP request / message"] --> B["Spring Boot service"]
    B --> C["HTTP client / database / cache"]
    B --> D["JMS / Kafka / RabbitMQ"]
    C --> E["Exception / retry handler"]
    D --> E
    B --> F["Application log"]
    E --> F
    E --> G["HTTP error body"]
    E --> H["Error channel / DLQ"]
    F --> I["Log collector / APM"]
    H --> I
```

Data leaks happen in many places beyond an explicit `logger.info(...)`:

1. **Automatic object stringification:** Java records, Lombok `@Data` or `@ToString`, Kotlin data classes, and object mappers can serialize every sensitive field into strings.
2. **HTTP request/response logging:** client interceptors, proxies, gateway access logs, wiretaps, trace filters, or API debug dumps can capture `Authorization`, `Cookie`, query parameters, and bodies.
3. **Exceptions and stack traces:** `Throwable#getMessage()` and `Throwable#toString()` may contain URLs, SQL, payloads, response bodies, or external error text. Logging a full throwable often prints messages across the entire cause chain.
4. **Validation errors:** binding error objects can retain `rejectedValue`, such as a user-entered password.
5. **Messaging errors:** Spring Integration `ErrorMessage` or `MessagingException#getFailedMessage()` holds the failed message, headers, and original payload; dead-letter messages may retain copies too.
6. **Query data:** ORM SQL bind-value logging, MongoDB command logging, cache keys, or deserialization logs can record personal payloads and credentials.
7. **Observability:** span attributes, baggage, metric tags, audit events, and dashboards can capture URLs/queries/bodies/headers or identifying user IDs.
8. **Files and storage:** filenames, paths, or adapter metadata can contain customer names, emails, or secrets in signed URLs.

Because logs are shipped to centralized collectors, backups, and alerting tools, deleting a log line from an application console **does not guarantee** every copy is gone.

## 4. Primary Strategy: Never Emit Sensitive Data in the First Place

Order of defense:

1. **Never create logs containing secrets.** Every log event includes only the fields needed for operations.
2. **Use dedicated DTOs or log events.** Never pass raw requests, responses, messages, entities, or unvetted exceptions to loggers.
3. **Normalize errors.** Map external errors into internal error codes and safe diagnostic fields; never pass raw upstream errors to callers.
4. **Apply redaction at log/export boundaries.** This acts as damage mitigation if an accidental log slips through; it never replaces step 1.
5. **Restrict access and retention.** Enforce across logs, traces, audits, DLQs, and diagnostic stores.

### 4.1. Avoid Logging Entire DTOs

Inappropriate example:

```java
record PaymentRequest(
        String customerEmail,
        String cardToken,
        String authorizationToken,
        long amountInMinorUnits
) {}

log.info("Processing payment: {}", paymentRequest);
```

With Java records, default `toString()` includes all component values. Even if a field carries `@JsonIgnore` or `@JsonProperty(access = WRITE_ONLY)` for JSON control, that **does not** hide the value in a Java record's `toString()` or across logging libraries.

Instead, log only approved fields:

```java
log.info(
    "payment_request_received operation={} amountCurrency={} correlationId={}",
    "createPayment",
    "VND",
    correlationId
);
```

If amounts are needed for failure investigation, evaluate data protection requirements, precision, and log access rights—do not dump every business field into logs simply because "it isn't a password".

### 4.2. Avoid Passing Uncontrolled `Throwable` Instances

```java
// Risky: exception may contain response body, token-bearing URL,
// SQL bind values, or sensitive details in a nested cause.
log.error("Partner request failed", exception);

// Safer once the error category is classified:
log.warn(
    "partner_call_failed partner={} operation={} status={} correlationId={}",
    "billing",
    "createPayment",
    safeHttpStatus,
    correlationId
);
```

This **does not mean eliminating all stack-trace diagnostics**. For controlled exceptions known to carry no sensitive data, stack traces can be logged on appropriate channels. For exceptions from HTTP clients, database drivers, or external sources, never assume exception messages are clean. Log the vetted exception class name, an application-defined error code, and correlation ID; use restricted diagnostic capture when deeper inspection is genuinely required.

## 5. Creating Safe Correlation IDs for Integration Flows

Correlation IDs connect logs across controllers, HTTP clients, databases, retry handlers, and message consumers without printing payloads. Identifiers must be independent of credentials and user data.

Example for a Spring Boot 3.x Servlet app:

```java
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
public class CorrelationIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String correlationId = UUID.randomUUID().toString();
        response.setHeader("X-Correlation-Id", correlationId);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("correlationId", correlationId)) {
            filterChain.doFilter(request, response);
        }
    }
}
```

This is a synchronous Servlet example. With WebFlux, `@Async`, Reactor, or Spring Integration `ExecutorChannel`, thread-bound `MDC` **does not automatically cross every async boundary**. Use the context propagation mechanism matching your framework and version. If accepting an external correlation ID header, validate length, character set, and trustworthiness; you can generate a fresh internal ID and store the link to the external ID in a controlled space.

Never put access tokens, emails, or phone numbers into `MDC` or tracing baggage just to search logs easily: those values get replicated across spans, log appenders, and downstream services.

## 6. Redacting Data in HTTP Clients and Connection Logs

### 6.1. What Must Be Excluded

When using `RestClient`, `RestTemplate`, `WebClient`, Feign, or underlying HTTP libraries, avoid logging:

- Auth headers: `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key`, and partner-specific credential headers.
- Queries containing `token`, `code`, `key`, `password`, signed URLs, presigned URLs, or unvetted raw query strings.
- Request/response bodies holding customer details, card tokens, credentials, upstream error text, or confidential business payloads.
- Raw URIs when userinfo or queries may hold credentials.
- Connection material containing certificates, keys, or client secrets.

Avoid enabling broad HTTP **wire logging** or body logging in environments processing real data. Debug levels on HTTP libraries, custom interceptors, request-response logging filters, and APM agents must all be checked independently: setting the app logger to `INFO` does not necessarily disable logging inside gateways or agents.

### 6.2. Example: Logging Metadata When Upstream Returns an Error

With `RestClient` on Spring Boot 3.x, illustrative code:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Service
public class PaymentGateway {

    private static final Logger log =
            LoggerFactory.getLogger(PaymentGateway.class);

    private final RestClient restClient;

    public PaymentGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    public PaymentReceipt charge(
            PaymentCommand command,
            String correlationId
    ) {
        try {
            return restClient.post()
                    .uri("/payments")
                    .body(command)
                    .retrieve()
                    .body(PaymentReceipt.class);
        } catch (RestClientResponseException ex) {
            log.warn(
                "payment_upstream_rejected operation={} httpStatus={} correlationId={}",
                "charge",
                ex.getStatusCode().value(),
                correlationId
            );

            // Never propagate ex.getResponseBodyAsString(), ex.getMessage(),
            // response headers, or raw URIs to API errors or ordinary logs.
            throw new PaymentGatewayUnavailableException();
        }
    }
}
```

`PaymentCommand`, `PaymentReceipt`, and `PaymentGatewayUnavailableException` are illustrative business types; `RestClient` must have endpoints, timeouts, and credentials configured via the project's bean configuration. The example preserves the **HTTP status code** and correlation ID for operations without logging the partner's response body.

In practice, `4xx` errors may indicate invalid business requests while `5xx` or timeouts may be retryable. Map them to distinct internal error codes; never collapse all statuses into one exception if doing so breaks retry policies. For I/O/timeout failures without an HTTP status, log a classified `failureKind` instead of printing the raw exception.

### 6.3. With HTTP Interceptors or Filters

If an interceptor logs HTTP activity, allowlist fields using **normalized paths**:

```text
method=POST
route=/partners/{partnerId}/payments   # static template, not full URL
partner=billing
status=502
durationMs=215
attempt=2
correlationId=<internal UUID>
```

Never log `request.getURI().toString()` when queries could hold tokens. Never buffer request/response bodies solely for logging: besides data exposure risk, buffering consumes extra memory and can break streaming.

## 7. Safe HTTP Error Messages with `ProblemDetail`

Error messages returned to callers should tell clients how to react without leaking internal exceptions or partner data. With Spring Framework 6/Spring Boot 3.x, use `ProblemDetail` in `@RestControllerAdvice`.

Example:

```java
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class SafeApiErrorHandler {

    @ExceptionHandler(PaymentGatewayUnavailableException.class)
    public ResponseEntity<ProblemDetail> paymentUnavailable(
            PaymentGatewayUnavailableException ex
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_GATEWAY,
                "Unable to complete transaction with dependent service at this time."
        );
        problem.setTitle("Dependent service unavailable");
        problem.setProperty("code", "PAYMENT_PROVIDER_UNAVAILABLE");

        String correlationId = MDC.get("correlationId");
        if (correlationId != null) {
            problem.setProperty("correlationId", correlationId);
        }

        return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(problem);
    }
}
```

Example response:

```json
{
  "type": "about:blank",
  "title": "Dependent service unavailable",
  "status": 502,
  "detail": "Unable to complete transaction with dependent service at this time.",
  "code": "PAYMENT_PROVIDER_UNAVAILABLE",
  "correlationId": "0a63e52c-7f06-49e8-bd32-5916b0ad4391"
}
```

Here `status`, `code`, and `correlationId` assist operations; the response exposes no tokens, upstream error bodies, stack traces, internal hosts, or database settings.

### 7.1. Never Return Raw `exception.getMessage()`

Avoid patterns such as:

```java
// Unsafe:
return ResponseEntity.status(500).body(
        Map.of("error", exception.getMessage())
);

// Unsafe:
return ResponseEntity.status(500).body(exception);

// Unsafe if BindingResult includes rejectedValue (e.g., password):
return ResponseEntity.badRequest().body(bindingResult.getAllErrors());
```

Validation errors should return a code like `VALIDATION_FAILED` and a list of **permitted field names** with fixed messages, e.g., `email: INVALID_FORMAT`. Never echo `rejectedValue` or unvetted input strings into responses or logs.

Exceptions from JDBC, MongoDB, or HTTP clients can include connection strings, URIs, queries, or external server messages. Separate **internal error classification** from the **public error contract** rather than forwarding raw driver messages.

### 7.2. Default Error Settings and Actuator

For Spring Boot 3.x, a conservative baseline is:

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
    include-exception: false

spring:
  mvc:
    log-request-details: false
  codec:
    log-request-details: false

management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never

logging:
  level:
    org.springframework.web: INFO
    reactor.netty.http.client: INFO
```

These properties govern only those respective Spring Boot mechanisms. `server.error.*` does not replace controlling JSON returned by your `@RestControllerAdvice`; `show-values: never` hides config values on those Actuator endpoints, yet **does not protect** data logged by other loggers or libraries. Actuator endpoints still require restricted exposure and authentication/authorization/network protection.

Depending on your Spring Boot version and Servlet vs. WebFlux stack, verify exact property names and logging settings; never assume one YAML block silences every underlying library.

## 8. Redaction When Dynamic Content Must Be Processed

When operational requirements demand logging a subset of dynamic data, enforce clear boundaries:

- **Field allowlist:** serialize only fields explicitly approved as safe, rather than serializing everything and attempting to scrub a few.
- **Structured classification:** process JSON, HTTP headers, query parameters, and message properties as structured field/value pairs. Mask header names case-insensitively; include partner-specific secret header names.
- **Consistent replacement values:** e.g., `[REDACTED]`; avoid keeping token prefixes unless explicitly approved.
- **Size and format bounds:** skip large payloads, binary bodies, file attachments, or schema-less objects.
- **Escaping and normalization:** partner/user-supplied strings can contain newlines, control characters, or fake log lines; prevent raw input from breaking log structure.

Example log representation of a vetted header map:

```java
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public final class HeaderRedactor {
    private HeaderRedactor() {}

    private static final Set<String> SENSITIVE = Set.of(
            "authorization",
            "proxy-authorization",
            "cookie",
            "set-cookie",
            "x-api-key"
    );

    public static Map<String, String> redact(Map<String, String> headers) {
        return headers.entrySet().stream().collect(Collectors.toMap(
                Map.Entry::getKey,
                entry -> SENSITIVE.contains(
                        entry.getKey().toLowerCase(Locale.ROOT)
                ) ? "[REDACTED]" : entry.getValue()
        ));
    }
}
```

**Important limitation:** this helper only demonstrates masking by header name. It is **not** a complete or safe filter for logging arbitrary headers. Other headers can still hold personal data, partner-specific tokens, or log-injection payloads. In production, use an **allowlist of specific loggable header names**, keeping redactors strictly as secondary defense.

### Why Are Generic Regexes Not Enough?

A regex searching for `password=...` typically misses credentials inside:

- Nested JSON, URL-encoded forms, Basic auth, or split bearer tokens.
- Custom-named headers, mixed casing, multi-line tokens, or multi-layer encodings.
- Exception messages and stack traces lacking consistent field labels.
- Personal data in free-form values lacking keywords like `password`.

Pattern filters can still be added at log collectors to reduce blast radius, yet test them on real formats, treat redaction failures as security bugs, and keep **not logging raw payloads** as the primary design.

## 9. Logs in Databases, Caches, and Connection Configurations

Be especially cautious with logging below the data access layer.

| Component | Risk Point | Mitigation |
|---|---|---|
| JDBC/JPA/Hibernate | SQL bind parameters, queries containing PII or passwords; connection URLs | Avoid bind-value logging on real data; never log credential-bearing datasource URLs |
| MongoDB | Command/driver debug logs reflecting sensitive documents or filters | Restrict log levels; monitor latency/status instead of raw commands/payloads |
| Redis/cache | Cache keys/entries holding emails, session IDs, tokens, or PII | Design keys without embedded secrets; never log raw entries/values |
| Connection pool | Connection exceptions, host/user configs, or properties | Log only error category and logical datasource name; keep passwords and DSNs out of loggers |
| Config/secret resolution | Secrets in environment variables, application properties, config dumps | Never dump full configuration at startup; use secret managers and strict Actuator access |

For instance, SQL bind tracing helps debug queries yet directly logs emails, account numbers, or access tokens inside `WHERE`/`INSERT` clauses. For time-boxed troubleshooting, use controlled environments, test data, or observability mechanisms that omit raw parameters.

Never let database passwords leak into HTTP error responses merely because config came from environment variables: driver or pool exceptions can still embed connection details.

## 10. Protecting Messages, Error Channels, and Dead-Letter Queues

In JMS/Kafka/RabbitMQ and Spring Integration flows, processing failures can dump the original message into logs or DLQs. Payloads may contain personal data; headers may hold credentials or authorization metadata.

### 10.1. Risks with `ErrorMessage`

Spring Integration sends exceptions to `errorChannel` wrapped in an `ErrorMessage`. With `MessagingException`, `getFailedMessage()` may reference the failed message including its payload and headers. Therefore:

```java
// Risky: may print payload/headers and exception message.
log.error("Spring Integration error: {}", errorMessage);
log.error("Flow failed", messagingException);
log.error("Failed message: {}", messagingException.getFailedMessage());
```

Instead, an error handler should emit a **controlled summary**:

```java
public void handleIntegrationError(
        String flowName,
        String failureCode,
        String correlationId,
        String destinationAlias
) {
    log.warn(
        "integration_flow_failed flow={} code={} destination={} correlationId={}",
        flowName, failureCode, destinationAlias, correlationId
    );
}
```

`flowName`, `failureCode`, and `destinationAlias` here must be normalized values or come from trusted config catalogs—never pass raw `toString()` of messages/headers as arguments. If error records must be forwarded downstream, construct a dedicated **error envelope** holding message ID, flow ID, error code, timestamp, and a reference to protected storage rather than copying raw exceptions.

### 10.2. DLQs Are Not Public Information Stores

In some systems, routing failed messages to a DLQ is needed for replay or investigation. However, DLQs often preserve the full original payload—doing so does not automatically count as "redacted".

Distinguish:

- **DLQs needing payloads for retries:** encrypt at rest/in transit where appropriate; enforce strict ACLs, consumers, retention, viewing tools, and deletion policies. Avoid adding stack traces or credentials to DLQ headers.
- **Error telemetry:** emit only IDs, error codes, retry counts, statuses, and approved flow types.
- **Support records or dashboards:** point to controlled message/job IDs; block click-through viewing of raw payloads for unauthorized users.

When publishing to a broker, avoid stuffing an inbound HTTP request's bearer token into message headers to "pass context". Consumers should obtain credentials through their own service identity; correlation IDs are not credentials.

### 10.3. Retries, Idempotency, and Observability

Data masking must not destroy duplicate-handling diagnostics. Use safe `eventId`/`requestId`, normalized event types, `attemptCount`, `failureCode`, and timestamps to track how many times a message retried. Never use full payloads or tokens as deduplication keys. Idempotency keys must be structured with appropriate retention; if they contain personal data, protect them too.

## 11. Tracing, Metrics, and Out-of-Application Logging Layers

Even when every `Logger` call is clean, data can still leak via:

- **APM/tracing:** full URLs, HTTP headers, SQL statements, exception messages, baggage, and custom span attributes.
- **Metrics:** labels like `userId`, `email`, `orderId`, or full URLs both leak data and explode cardinality.
- **Reverse proxies/API gateways:** access logs recording query strings; request logging plugins or WAF audits capturing request bodies.
- **Infrastructure:** container stdout, service meshes, ingress/controllers, audit logs, crash dumps, or support bundles.
- **Notifications:** Slack/email/ticket alerts attaching raw logs with sensitive data.

A span can stay informative using approved attributes such as:

```text
integration.system = "billing"
integration.operation = "charge"
integration.status = "failed"
error.type = "UPSTREAM_TIMEOUT"
http.response.status_code = 504
retry.attempt = 2
```

These are illustrative internal field names, not a guarantee every exporter uses identical standard names. With Micrometer Observation/OpenTelemetry, review active observation conventions and instrumentations, stripping sensitive headers, raw URIs, bodies, and personal data from span attributes. Metric labels must stay bounded from static catalogs.

## 12. Testing Data Masking and Error Contracts

Code inspection alone never proves all sensitive data is scrubbed. Tests must inject **synthetic sensitive markers** and verify actual outputs.

### 12.1. Test Matrix

| Data Path | Synthetic Input to Inject | Outcome to Verify |
|---|---|---|
| HTTP input | Password and token in JSON/headers | Responses and app logs contain zero marker values |
| Outbound HTTP client | `401/500` error with response body holding token/email | Logs contain only error code, status, correlation ID; client response stays clean |
| Validation | Rejected value is a sensitive string | No `rejectedValue`/raw input in bodies or logs |
| JDBC/MongoDB | Error with sensitive data in message | No raw exception/SQL bind/payload in logs |
| Spring Integration | `ErrorMessage` holding a secret-bearing failed message | Error channel handler and logs emit error summaries only |
| Broker DLQ | Failed message with personal data | ACLs, encryption/retention, and DLQ headers match policy; logs never dump payload |
| Traces/metrics | `Authorization` header and URL with `?token=...` | Exporter puts zero values into span attributes or labels |
| Configuration | Secrets and password-bearing datasource URL | Startup logs, `/actuator/env`, `/actuator/configprops` expose no values |

### 12.2. Example Test Ensuring Responses Do Not Leak Tokens

In Spring MVC with `MockMvc`, assert the full response body excludes fixture secret markers:

```java
@Test
void doesNotExposeSecretsInPublicError() throws Exception {
    String marker = "SECRET_TEST_ONLY_9a8f7c";

    mockMvc.perform(post("/payments")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("Authorization", "Bearer " + marker)
                    .content("""
                        {"customerEmail":"test@example.invalid",
                         "cardToken":"SECRET_TEST_ONLY_9a8f7c"}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(not(containsString(marker))))
            .andExpect(content().string(
                    not(containsString("test@example.invalid"))
            ));
}
```

This example assumes a validation branch returning `400`; if your business endpoint uses another status, adjust the fixture and assertions per contract. Helpers like `post`, `status`, `content`, and Hamcrest matchers are static-imported in real tests.

Run similar tests using a log-capturing appender to inspect **actual formatted log lines**, including rendered throwables/causes—not just message templates before encoding. For JSON logs, inspect serialized JSON written to a test stream/collector. For traces, inspect exported spans, not only in-app objects.

### 12.3. Testing Log Injection and Length Limits

Beyond secrets, inject fixtures containing newlines, control characters, and forged log lines:

```text
username = "guest\nERROR authenticated_as_admin=true"
reason   = "\r\nAuthorization: Bearer SECRET_TEST_ONLY_9a8f7c"
```

If an input field truly must be logged, encode/escape it per log format, cap length reasonably, and scrub sensitive data before writing. Never place these values in metric names or span attributes.

## 13. When Secrets Have Already Been Written to Logs

Scrubbing logs in a new release only stops future leaks—it does not invalidate leaked tokens. When evidence shows credentials or personal data entered logs:

1. **Stop the leak source:** disable the offending logging config or deploy restricted field logging; tighten emergency access controls if needed.
2. **Assess scope:** data types, time window, downstream log sinks, indexes, exporters, dashboards, alerts, backups, and support tools that copied them.
3. **Revoke/rotate credentials:** revoke and rotate leaked tokens, passwords, or keys per system procedure; evaluate impact on active clients.
4. **Restrict access and clean copies:** per security policy and legal compliance, purge or shorten retention on reachable copies while preserving necessary forensic evidence.
5. **Prevent recurrence:** add synthetic marker tests, logging policy checks, APM/Actuator audits, and review sibling integration flows.

Never paste the leaked token itself into tickets, chat, incident reports, or support messages. Reference incident IDs and secret-store IDs instead, sharing details strictly through controlled channels.

## 14. Pre-Deployment Checklist

- [ ] Cataloged secrets, PII, and business payloads across every HTTP endpoint, database, cache, broker, and integration adapter.
- [ ] Application logs follow an allowlist; never print raw requests, responses, entities, messages, or untrusted exceptions.
- [ ] Reviewed DTO `toString()`, validation `rejectedValue`, and custom loggers/interceptors.
- [ ] Stripped `Authorization`, cookies, API keys, and custom credential headers from all request/response logging.
- [ ] HTTP error bodies expose stable `code`/correlation ID, never raw exceptions, stack traces, or upstream bodies.
- [ ] Default error settings, Actuator, HTTP debug/wiretap, and data bind logging are locked down.
- [ ] Spring Integration error channels and DLQs omit payloads/credentials from logs and extra error metadata per policy.
- [ ] Reviewed trace/span attributes, baggage, metric labels, gateways, and logging sidecars.
- [ ] Integration tests inject synthetic tokens/passwords/PII and inspect formatted logs, responses, and exported telemetry.
- [ ] Access, retention, encryption, and incident policies exist specifically for logs, traces, DLQs, and backups.
- [ ] Correlation IDs are safely generated/validated and propagate across needed async boundaries.
- [ ] Operational diagnostics remain intact: normalized route/operation, status, error code, latency, retry count, and trace ID.

**Remember:** the most effective way to mask tokens, passwords, and personal data in Spring Boot Integration is **never putting them into logs or error messages in the first place**. Logging allowlisted diagnostic metadata, normalizing errors, governing external telemetry sinks, and testing actual emitted outputs reduce leak risks while preserving full debuggability across HTTP, database, cache, and broker flows.
