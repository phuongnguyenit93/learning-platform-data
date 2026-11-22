# Adding Data Masking in Java Logging — Hands-On Project for Protecting Sensitive Information

## 1. Practice Objectives

In a Java system, logs help investigate errors, monitor operations, and trace transactions. However, log lines can accidentally contain **passwords, access tokens, Authorization headers, cookies, emails, phone numbers, addresses, personal identifiers, payment details, or request bodies**. Once sent to files, sidecars, collectors, and centralized storage systems, the scope of people who can access the data is often broader than that of the original application.

**Data masking in logging** is the proactive practice of **hiding, replacing, truncating, or removing** sensitive parts from log records before the data reaches places that do not need to know the original values.

This hands-on exercise focuses on **designing and integrating a safe logging mechanism in Java**: with field-level rules, safe defaults, a standalone runnable Java 17 example, and testing methods at both the application and collection pipeline levels.

After this lesson, you will be able to:

1. Classify data fields that should be dropped, fully masked, partially masked, or allowed in logs.
2. Distinguish between **masking, redaction, tokenization, hashing/HMAC, and encryption**.
3. Avoid anti-patterns such as `log.info("request={}", request)` or `log.error("{}", exception.getMessage())`.
4. Create **a structured log event** that preserves useful operation/correlation/outcome context without leaking data.
5. Write Java 17 code demonstrating **fail-closed behavior when encountering fields not in the allowlist**.
6. Integrate the policy into SLF4J/Logback, HTTP filters, message consumers, MDC, and exception logging.
7. Write tests verifying that **secrets do not appear in files/JSONL/collectors**, even with malicious input.
8. Understand the limitations: masking does not replace authentication, authorization, encryption at rest, audit integrity, or retention policies.

**Most important principle:** if a field is **not needed for logging purposes**, it is best **not to generate/write that field at all**, rather than logging the raw value and hoping a regex at the collector will strip it out.

## 2. Identifying the Problem with Before-and-After Examples

Suppose a profile update API receives the following JSON:

```json
{
  "email": "alice@example.com",
  "phone": "+84901234567",
  "password": "not-for-logs",
  "accessToken": "eyJhbGciOi..."
}
```

**Anti-patterns** in Java:

```java
// Illustrative code to avoid: may invoke toString() on the entire DTO.
log.info("Update profile: {}", request);

// Illustrative code to avoid: puts credentials directly into the log.
log.debug("Authorization header: {}", authorizationHeader);

// Illustrative code to avoid: exception message may contain request/SQL/token.
log.error("Update failed: {}", failure.getMessage());
```

If the DTO has an auto-generated `toString()` covering all fields, the logger can print passwords/tokens. Even if DEBUG is disabled today, a runtime level change tomorrow can expose secrets. `request.toString()` can also change due to code generation, Lombok, or a library update, so it is not a safety boundary.

A better log record:

```json
{
  "event": "profile.update.result",
  "requestId": "req-101",
  "outcome": "SUCCEEDED",
  "email": "[MASKED]",
  "phone": "[MASKED]",
  "authorization": "[REDACTED]",
  "durationMs": 24
}
```

In many cases, **omitting email, phone, and authorization from the log in the first place is even better**:

```json
{
  "event": "profile.update.result",
  "requestId": "req-101",
  "outcome": "SUCCEEDED",
  "durationMs": 24
}
```

These two patterns do not contradict each other: the first illustrates masking to protect a field that the current pipeline still needs to emit; the second applies **data minimization**. Choose the approach that fits your investigation needs and data policy.

### 2.1. Guiding Questions

Before logging a field, ask:

- Is this value truly needed for troubleshooting or reconciliation?
- Can it be replaced with `requestId`, `operationId`, `errorCode`, a data type, or a count?
- Who is authorized to read the logs? Which destinations receive copies?
- Could a partial value (such as the last four digits) still expose an identity?
- Can this data contain **arbitrary client-supplied content**?
- If masking fails, will the log **drop the field** or accidentally write the raw value?
- When the system has multiple log sources, is this policy applied across all paths?

## 3. Classifying Data Before Designing Masking

A suggested policy, **not a default legal classification**:

| Data Type | Examples | Suggested Policy | Notes |
| --- | --- | --- | --- |
| Credentials/secrets | password, bearer token, private key, session cookie, OTP | **DROP** or full `[REDACTED]` | Do not keep token prefix/suffix when not strictly needed |
| Personal data | email, phone, address, name, IP depending on context | **OMIT** or `[MASKED]` | May still be identifiable when multiple fields are combined |
| Payment information | card number, CVV, account number | **Never log raw** | Industry standards may impose additional requirements |
| Trusted technical identifiers | event code, status, operation, duration | **ALLOW** | Validate format and cardinality |
| Correlation/request ID | requestId, traceId, messageId | **Controlled ALLOW** | Do not treat client-supplied IDs as trusted |
| Business ID | orderId, customerId, paymentId | Depends on purpose and sensitivity | IDs can still be personal data |
| Unbounded payload/headers | `requestBody`, `responseBody`, `headers`, `metadata` | **DROP by default** | Nested fields may contain unexpected secrets |
| Exception message | error text from SQL/HTTP/driver | **Restrict or redact** | May contain URLs/tokens/SQL literals |
| Internal file path / host | path, hostname, JDBC URL | System-dependent | May expose topology or credentials |
| Mandatory audit content | Actor, action, target, result | Separate schema, permissions, and retention | Masking does not replace audit integrity |

Do not apply a rule that "every `id` is safe." A customer ID may allow looking up a profile, a trace ID can link multiple actions, and an IP address may be personal data depending on purpose and regulations.

**Allowlist first, denylist second.** For critical events, explicitly define which fields are allowed to be logged and how they are represented. A denylist of terms like `password`, `secret`, and `token` is still useful as defense in depth, but it easily misses unfamiliar names such as `auth`, `bearer`, `credentialValue`, `api_key`, `session`, `refresh`, or a nested property.

## 4. Understanding the Differences: Masking, Redaction, Tokenization, HMAC, and Encryption

| Technique | Output Example | Goal | Risks/Limitations |
| --- | --- | --- | --- |
| **Omit/drop** | Do not emit `password` | Minimal data | Cannot search by that value |
| **Full redaction** | `token=[REDACTED]` | Keep a signal that the field existed without logging its value | Still reveals that the field was present |
| **Full masking** | `email=[MASKED]` | Hide the value while keeping the field type | Cannot correlate by email |
| **Partial masking** | `a***@example.com` | Help readers verify part of a value | May leak domain, length, or identity |
| **Tokenization** | `customerRef=tok_...` | Replace the value with a token from a token system | Requires managing a mapping vault or token service/algorithm |
| **Keyed HMAC** | `actorTag=HMAC(key, identifier)` | Pseudonymous correlation without direct exposure | Still linkable; requires key protection and key rotation control |
| **Unkeyed hash** | SHA-256(email) | Produce a digest | Email/phone can be guessed via dictionary attack |
| **Encryption** | Ciphertext decryptable by a key holder | Protect data in storage/transit | Not masking; anyone with the key can recover the raw value |

When the goal is simply to debug an HTTP request, there is no need to add complex HMAC logic if a system-generated `requestId` is sufficient. When you need to correlate the same subject across events without logging the identifier, HMAC can be appropriate with a clear **threat model and access policy**. HMAC does not make data strictly anonymous because linkability still remains.

Do not generate fake-looking values like `****1234` for every kind of data just to make it look "masked." **The last four digits** can sometimes still be sensitive; use partial masking only when there is a business justification, approval, and access control.

## 5. Designing a Masking Pipeline at the Source

Treat the log data path as a pipeline with multiple potential leak points:

```text
HTTP / message / DB / external service
              |
              v
        Business code
              |
        Classify fields
              |
       Drop / Mask / Validate
              |
          Safe log event
              |
         JUL / SLF4J
              |
       Encoder / Appender
              |
      stdout / file / network
              |
    Sidecar / node collector
              |
       Log storage / SIEM
```

**The preferred point is before calling the logger.** Once raw data enters a `LoggingEvent`, a second appender, another logger, or an exception renderer might write it before a downstream filter runs.

You can apply **defense in depth**:

1. **Application boundary:** only build events with allowed fields.
2. **Logging API/builder:** centralize classification, sanitization, masking, and schema.
3. **Encoder/appender:** add redaction during formatting, with tests covering message/arguments/MDC/Throwable.
4. **Collector:** second line of defense to detect secret patterns and route/drop/quarantine by policy.
5. **Storage:** appropriate access control, retention, search, and access auditing.

Do not rely on step 4 as the sole control: the collector may receive data after raw logs have already hit disk, or another pipeline may bypass the collector.

### 5.1. Fail-Closed Strategy

An event containing a field not in the allowlist can be:

- **Dropped (field omitted)** while keeping safe technical fields.
- Replaced with `[REDACTED]` if you still need to know the field existed.
- **Not emitted**, incrementing a metric/health signal if this is an audit log with strict policy requirements.
- Reported as a schema validation error through a **channel that contains no raw input**.

**Do not:** print `originalMessage` for "easier debugging" if the parser/regex fails. That creates a leak path at the exact moment abnormal data is being processed.

What fail-closed means depends on requirements: for best-effort diagnostic logs, dropping the field may be reasonable; for mandatory audit logs, dropping the entire record could violate requirements and require a different safe capture mechanism.

## 6. Standalone Java 17 Example: Allowlist + Field-Level Masking

The following example uses only **JDK 17 and `java.util.logging`**. The policy is centrally defined:

- `event`, `requestId`, `outcome`, `errorCode`: **CODE**, accepts only ASCII alphanumeric characters plus `_`, `-`, `.`, length 1–64.
- `email`, `phone`: **MASK**, replaces the entire value with `[MASKED]`.
- `authorization`, `accessToken`: **REDACT**, keeps no secret characters.
- Fields **not in the allowlist**: **ignored** (fail-closed).
- IDs containing newlines or unusual characters: replaced with `[INVALID]` before logging.
- `Logger` uses a demo stdout handler to inspect the exact output.

The example intentionally supplies sensitive data and an ID with a **forged log-line newline** to prove that the data is not emitted.

Save the file as **`SafeLoggingDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SafeLoggingDemo {
    private enum Treatment { CODE, MASK, REDACT }

    private static final Map<String, Treatment> POLICY = Map.of(
            "requestId", Treatment.CODE,
            "outcome", Treatment.CODE,
            "errorCode", Treatment.CODE,
            "email", Treatment.MASK,
            "phone", Treatment.MASK,
            "authorization", Treatment.REDACT,
            "accessToken", Treatment.REDACT
    );

    private static String safeCode(String value) {
        if (value != null
                && value.matches("[A-Za-z0-9_.-]{1,64}")) {
            return value;
        }
        return "[INVALID]";
    }

    private static String safeValue(
            Treatment treatment, String value) {
        return switch (treatment) {
            case CODE -> safeCode(value);
            case MASK -> value == null ? "-" : "[MASKED]";
            case REDACT -> value == null ? "-" : "[REDACTED]";
        };
    }

    private static String safeEvent(
            String event, Map<String, String> input) {
        StringBuilder result = new StringBuilder("event=")
                .append(safeCode(event));

        for (Map.Entry<String, String> field : input.entrySet()) {
            Treatment treatment = POLICY.get(field.getKey());

            // Fields not in the policy will not be logged.
            if (treatment == null) {
                continue;
            }

            result.append(' ')
                    .append(field.getKey())
                    .append('=')
                    .append(safeValue(treatment, field.getValue()));
        }

        return result.toString();
    }

    private static void assertSafe(String line) {
        if (line.contains("alice@example.com")
                || line.contains("Bearer")
                || line.contains("card=4111")
                || line.contains("secret-token")
                || line.contains("\n")
                || line.contains("\r")) {
            throw new AssertionError("Sensitive content leaked");
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.safe-logging");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler stdout = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        logger.addHandler(stdout);
        try {
            Map<String, String> first = new LinkedHashMap<>();
            first.put("requestId", "req-101");
            first.put("outcome", "SUCCEEDED");
            first.put("email", "alice@example.com");
            first.put("phone", "+84901234567");
            first.put("authorization", "Bearer secret-token");
            first.put("rawPayload", "card=4111111111111111");

            String firstLine = safeEvent(
                    "profile.update.result", first);
            assertSafe(firstLine);
            logger.info(firstLine);

            Map<String, String> second = new LinkedHashMap<>();
            second.put("requestId", "req-102\nERROR forged");
            second.put("outcome", "FAILED");
            second.put("errorCode", "PROVIDER_TIMEOUT");
            second.put("accessToken", "secret-token");

            String secondLine = safeEvent(
                    "payment.authorize.result", second);
            assertSafe(secondLine);
            logger.info(secondLine);
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
        }
    }
}
```

Compile and run on **JDK 17 or later**:

```bash
javac SafeLoggingDemo.java
java SafeLoggingDemo
```

**Exact stdout** of the program:

```text
INFO event=profile.update.result requestId=req-101 outcome=SUCCEEDED email=[MASKED] phone=[MASKED] authorization=[REDACTED]
INFO event=payment.authorize.result requestId=[INVALID] outcome=FAILED errorCode=PROVIDER_TIMEOUT accessToken=[REDACTED]
```

No email, phone number, bearer token, raw payload, or `ERROR forged` line appears. If the check in `assertSafe` fails, the program throws `AssertionError` and **is not considered successful**.

### 6.1. Code Walkthrough

1. `POLICY` is **an allowlist of known fields**. A field like `rawPayload` that is not in the policy is ignored completely.
2. `LinkedHashMap` preserves insertion order so stdout has deterministic field ordering.
3. `safeCode` does not try to "fix" dangerous input into a valid-looking ID; it returns `[INVALID]` when the format is invalid.
4. `MASK` and `REDACT` both return a constant value in the demo. This is **full masking**, requiring no regex.
5. The JUL handler disables parent handlers to avoid duplicate output and variable timestamps in the example.
6. `assertSafe` is a **smoke check on specific test payloads**, not a mathematical proof that every future secret will be filtered out. Real testing must use broader datasets.
7. `stdout` is only the demo output target; there is no storage, encryption, rotation, or collector.
8. A string containing a newline in `requestId` is not written verbatim to the log, reducing **log injection** risk.

### 6.2. Important Limitations of the Demo

**Do not use verbatim as a production masking system.**

- Each field requires **responsible data classification**. If `customerEmail` is mistakenly classified as `CODE`, the policy will not automatically recognize it as PII.
- Some legitimate IDs contain Unicode or exceed 64 characters; design realistic validators rather than relaxing rules indiscriminately.
- `[MASKED]` and `[REDACTED]` have the same level of hiding in the example, but the names express two different policy meanings.
- A policy keyed by **field name** does not detect secrets hidden inside an allowed field, such as `errorCode="Bearer xxx"` or a client-controlled `event`. That is why `CODE` only accepts a very narrow grammar; other dynamic values need dedicated policies.
- `assertSafe` runs after constructing a temporary string in memory, so it is not a memory-dump protection mechanism.
- The values of masked fields are still passed into `safeEvent`; a better practice is **not to collect secrets in the first place** when not needed.
- Dropping unknown fields can lose diagnostic information; emit schema-violation metrics/alerts on a safe channel if needed.
- There is no control over `Throwable`, MDC, message templates, custom `toString()`, sidecars, or other appenders. Those paths must be protected separately.

## 7. Scaling the Exercise to a Real Application Design

From the JUL demo, you can expand into components such as:

```text
com.example.logging
  FieldClassification        (sensitivity class, allowed level)
  LogEventSchema             (event name, allowed fields, types)
  SafeLogEventBuilder        (accepts only permitted data)
  MaskingPolicy              (DROP/MASK/REDACT/ALLOW...)
  Sanitizer                  (validate, normalize, escape)
  SafeLogPublisher           (forwards vetted events to logger)
  MaskingPolicyTest          (unit tests)
  LoggingPipelineTest        (integration tests)
```

This is an **architectural suggestion**, not pre-existing files. A smaller application may use fewer classes; the goal is to **centralize rules** rather than having each controller write its own regexes.

The API contract should separate:

- **Raw input:** allowed to exist only in the business processing layer, not yet loggable data.
- **Safe value:** type/result processed according to policy.
- **Safe log event:** object containing the event code, permitted fields, and outcome.
- **Publisher:** emits the structured event as-is without re-attaching raw payloads.

An advanced option is using **type-safe wrappers** instead of a generic `Map<String, String>`, such as `SafeRequestId`, `SanitizedErrorCode`, and `MaskedEmail`. The compiler cannot prove every field is safe, but the API can prevent a developer from accidentally passing an entire DTO into the logger.

## 8. Designing Schemas and Masking by Event Type

A global rule like `fieldName=email => MASK` is helpful but insufficient. Events serve different purposes.

| Event | Safe Fields to Include | Fields to Drop or Mask |
| --- | --- | --- |
| `auth.login.result` | event, outcome, errorCode, requestId | password, OTP, raw authorization, session |
| `profile.update.result` | requestId, operation, result, duration | full profile payload, email, phone, address |
| `payment.capture.result` | policy-compliant paymentRef, status, errorCode | card number, CVV, token, bank details |
| `http.request.completed` | method, route template, status, duration, requestId | raw URL/query, cookies, body |
| `message.processing.failed` | event ID, message type, attempt, safe errorCode | message body, secret headers |
| `order.create.result` | policy-compliant order ID, outcome, correlation ID | object graph containing customer PII |
| `config.change.result` | authenticated actor, setting name, approved change ID, outcome | secret values, connection strings |
| `job.run.completed` | job name, run ID, counts, duration | full exported records and data snapshots |

For **config changes**, you can log `secretChanged=true` instead of `oldSecret`/`newSecret`. For request debugging, use `route=/api/orders/{id}` rather than a raw path/query containing user data.

**Note on metrics:** masking may change visible values, but **it should not alter the meaning of outcome, duration, or status**. If a policy masks a `reasonCode` while dashboards use `reasonCode` as a label, design a harmless error-code mapping instead of blanket-masking it and losing observability.

## 9. Structured Logging: Mask Before Serializing

In modern Java applications, you typically want to emit JSONL with fields such as:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "INFO",
  "service": "accounts-api",
  "event": "profile.update.result",
  "requestId": "req-101",
  "outcome": "SUCCEEDED",
  "email": "[MASKED]"
}
```

Build `SafeLogEvent` first, then **serialize with a JSON encoder that performs proper escaping**. If you use `log.info("{}", request)` and hope the encoder automatically recognizes nested email/password fields, there is no guarantee it will do so.

**Never concatenate JSON strings manually in production**, even when strings look simple: quotes, backslashes, newlines, control characters, invalid Unicode, or nested objects can break JSON or lead to log injection. Jackson, a logging backend's encoder, or a compatible serializer helps control syntax; **however, a serializer does not automatically know which fields are secrets**.

### 9.1. Structured Logging and Field-Level Redaction

An example pipeline:

```text
SafeLogEvent(
  event = "profile.update.result",
  fields = {
    requestId = "req-101",
    outcome   = "SUCCEEDED",
    email     = MASKED
  }
)
  -> JSON encoder
  -> one JSON object per line
  -> file/stdout
  -> collector parses JSON
  -> storage
```

Rules:

- Only **cataloged field names** are passed to the encoder.
- Text fields have length limits and escaping.
- `durationMs` must remain a number; `status` must remain an integer if specified by the schema.
- Null/unknown fields have a clear contract: omit, `null`, or `UNKNOWN`.
- Do not let clients dictate field names due to **mapping explosion** risk.
- Avoid putting raw objects under `details` or `additionalFields`, as this can bypass the policy.
- Verify output at the actual sink, not just the object before serialization.

## 10. Integrating SLF4J 2 and Logback

SLF4J is a **facade API**, while Logback is a backend. When an application uses SLF4J 2.x, you can emit key-value attributes:

```java
// Integration snippet: log is org.slf4j.Logger from SLF4J 2.x.
// The following variables have already been processed by SafeLogEventBuilder per policy.
log.atInfo()
        .addKeyValue("event", "profile.update.result")
        .addKeyValue("requestId", safeRequestId)
        .addKeyValue("outcome", "SUCCEEDED")
        .addKeyValue("email", maskedEmail)
        .log("Profile update completed");
```

**Mandatory requirement:** `maskedEmail` must be the masked value, **not the raw email**. `addKeyValue` does not mask or redact automatically. The backend/encoder must output key-value pairs in the expected format; a pattern that only prints `%msg` may drop attributes.

With Logback and a compatible JSON encoder, an integration configuration typically looks like:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

This is a **configuration snippet for a project that already has a compatible `logstash-logback-encoder` dependency** in addition to SLF4J/Logback. It **does not enable masking automatically** and cannot run with plain JDK alone. Field names, MDC output, structured arguments, and Throwables depend on the specific encoder and version.

In particular, Logback can receive data into an event through multiple paths:

- `message` or formatted message;
- template arguments;
- structured key-value pairs;
- markers;
- `MDC`;
- `Throwable`/stack trace;
- logger/thread metadata.

A filter that only replaces `formattedMessage` **does not prove** that the remaining paths are masked. If you use encoder-level masking (such as library-supported decorators or field-name filters), verify the exact processing order, version, nested-object support, and scope.

### 10.1. Watch Out for Double Logging

If you emit safe JSON events from Java while another agent also collects unmasked console text, raw data can still leak. Check **every appender and sink**: file, console, rolling archive, HTTP exporter, sidecar stdout, collector debug logs, and error-status loggers.

Masking in one pipeline **does not compensate** for another pipeline logging raw data. If there is a separate audit trail, apply the policy dedicated to that audit trail and verify access permissions and retention.

## 11. HTTP Logging: Handling Headers and Bodies

HTTP middleware is a common leak point because requests can contain `Authorization`, `Cookie`, query parameters, and bodies.

**Do not:**

```java
// Illustrative code to avoid in Servlet/Spring web code.
log.debug("headers={}", request.getHeaderNames());
log.debug("authorization={}",
        request.getHeader("Authorization"));
```

The first line may only print an `Enumeration` rather than all headers, but using a generic header dumper to log all names/values is risky. The second line definitely puts credentials into the log if DEBUG is enabled.

**Do:** choose an access log schema with validated `method`, `routeTemplate`, `status`, `durationMs`, and `requestId`. For example:

```json
{
  "event": "http.request.completed",
  "method": "POST",
  "route": "/api/orders",
  "status": 201,
  "requestId": "req-101",
  "durationMs": 18
}
```

This is an example event, not the output of a standalone Servlet snippet.

If certain HTTP headers are needed for debugging, use an **allowlist of header names** with per-header policies, and never print `Authorization`, `Cookie`, `Set-Cookie`, custom auth headers, or raw queries. `User-Agent` is still client-supplied data that can contain newlines/long strings and carries fingerprinting concerns; log it only in a bounded/normalized form if permitted.

In Spring Boot, you can use `OncePerRequestFilter` or appropriate instrumentation/filters to measure the request lifecycle, but **pay attention to async requests**: a filter returning does not always mean the response or business transaction has completed. Name events according to the observed boundary.

### 11.1. Never Log Request/Response Bodies by Default

Bodies can contain passwords, customer profiles, payment data, or file uploads. A request may be binary, streaming, very large, or contain dynamic schemas. A generic body dumper is an uncontrollable leak source.

If an investigation requires body inspection, use an approved debugging mechanism with **narrow scope, short duration, explicit authorization, and schema-based masking**, rather than enabling system-wide full-body logging during an incident.

## 12. MDC, TraceContext, and Thread Pool Leakage

SLF4J `MDC` lets you attach context to multiple events within the same scope. However, if you put raw client values into MDC, the encoder may emit them in **every log event**:

```java
// Integration snippet to avoid.
MDC.put("authorization", request.getHeader("Authorization"));
```

A better pattern:

```java
import org.slf4j.MDC;

// Integration snippet: validatedRequestId has already been checked for format/length.
String previous = MDC.get("requestId");
try {
    if (validatedRequestId == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", validatedRequestId);
    }

    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

This is **not a standalone runnable class**; the variables, `processRequest()`, and SLF4J dependency must be provided by the project.

Principles:

1. Put only **allowlisted context keys** into MDC.
2. Validate/normalize before placing values into MDC; do not trust client-sent `X-Request-ID` verbatim.
3. Use `finally` to restore context, because thread pools reuse threads.
4. With `CompletableFuture`, executors, Reactor/WebFlux, or schedulers, context **does not automatically propagate across all threads**; use framework-appropriate propagation.
5. When copying the MDC map across tasks, do not copy raw headers, tokens, or user profiles into the new context.
6. Avoid putting high-cardinality values like `traceId`, `userId`, or `requestId` into **metric labels**.
7. Trace/correlation IDs help locate logs; they are **not authenticated identities** and do not prove an operation succeeded.

A serious data-leak bug occurs when thread A handles user 1 and forgets to clear MDC; that thread then handles user 2, causing user 2's logs to carry user 1's identifier. Test concurrency and thread reuse, not just single requests.

## 13. Exception Logging: An Often-Overlooked Leak Path

An error from a database, HTTP client, or validation library can contain SQL queries, URLs with tokens, header/body fragments, hostnames, or file paths in `Throwable.getMessage()`.

Risky example:

```java
// Illustrative code not to use unless the message is verified safe.
log.error("External call failed: {}", failure.getMessage());
```

**Do not assume** that `log.error("... ", failure)` is safe by itself: passing a `Throwable` preserves the cause chain for investigation, but **an encoder can print exception messages that contain secrets**. This creates a trade-off:

- **Preserve root cause:** keep technical evidence useful for analysis.
- **Protect sensitive data:** avoid sending raw exception text containing secrets to unauthorized sinks.

A practical policy:

1. In regular events, log `errorCode`, `exceptionType`, `operationId`, `dependency` (allowlisted values), and outcome; avoid raw `failure.getMessage()`.
2. For exceptions that need stack traces, use a protected internal log path with a tested renderer/redaction configuration—never return stack traces in API responses.
3. If you want to log a full `Throwable`, inspect what libraries can put into messages/causes/suppressed exceptions and test the actual encoder.
4. For secret-related errors, you may need a **safe exception wrapper** without secret text, while keeping correlation to a policy-protected investigation system.
5. Catch/unwrap exceptions only according to contract; do not swallow errors or alter retry logic just for log masking.
6. Do not dump exception objects as arbitrary JSON; object graphs can have cyclic references, uncontrolled fields, and sensitive data.

**Masking exceptions with regexes on stack traces is a supplemental defense, not a guarantee.** A stack trace containing data with unusual escaping or encoding can bypass patterns.

## 14. Regex-Based Masking: Where to Use It and Its Limits

Regex can serve as a second line of defense for **free-text legacy logs** when migrating to structured fields is not yet possible.

For example, targeting a string like `Authorization: Bearer ...` in text logs. Even with a well-crafted expression, problems remain:

- Clients can vary **case, spacing, delimiters, percent encoding, Unicode, or newlines**.
- Secrets may appear as different JSON keys, XML attributes, query parameters, URL-encoded values, base64, or nested fields.
- Regexes can accidentally mask benign strings, losing diagnostic information.
- Regexes cannot tell which value belongs to `email` or `password` in a nested object if parsing fails.
- Complex regexes can cause high CPU usage or catastrophic backtracking on malicious input.
- Regexes running at the collector **after raw data has reached disk** cannot erase copies already written there.

A small regex example for **bounded strings with a known format**, just to illustrate the mechanism:

```java
// Integration snippet, NOT a complete security rule.
// Handles only one fixed pattern; does not cover all bearer token variants.
String sanitized = rawLine.replaceAll(
        "(?i)Authorization: Bearer [A-Za-z0-9._~+/-]+",
        "Authorization: Bearer [REDACTED]");
```

This snippet is **illustrative**; `rawLine` must already exist and should not be logged if the regex fails. It does **not** handle all credential syntax, header folding, unusual Unicode, `=` signs, tokens with different patterns, or secrets in other fields. Do not replace source-level allowlisting with this snippet.

If performing deep masking on JSON, **parse the JSON with an allowed schema and field paths** instead of using regex substring replacement on a JSON string. However, parsers can fail on malformed JSON; the fallback must be safe and never print the raw payload.

## 15. Partial Masking: When Is It Acceptable?

Sometimes support teams want to verify "did the phone number the user entered end in the right two digits?" Partial masking may be requested, but its risk must be evaluated.

Example:

```text
phone="[MASKED]"
email="[MASKED]"
cardNumber="[REDACTED]"
```

versus:

```text
phone="********67"
email="a***@example.com"
```

The second pattern reveals more: the phone suffix and the email domain. It can allow identity correlation when combined with timestamps, locations, `requestId`, or other leaked data.

A valid policy should specify:

- Which fields are permitted to be partially masked?
- How many characters remain, their positions, and how short strings are handled?
- Does the format need to be normalized before computing prefix/suffix?
- Could Unicode code points and combining characters cause partial masking to leak or slice incorrectly?
- Who is allowed to view partially masked values, and what is the retention period?
- Should a token or HMAC be used instead for correlation without exposing suffixes?

**Do not apply "keep the last four digits" to passwords, private keys, or access tokens.** Unless there is a specific requirement, full redaction is the safer default.

## 16. Idempotency and Pseudonymization with HMAC

In some scenarios, SREs need to correlate records for **the same entity** without logging the raw identifier. You can consider generating a tag using **HMAC with a securely managed key**.

Conceptual example:

```text
raw identifier
    |
HMAC(secret key, canonical identifier)
    |
short-lived / scoped pseudonym tag
    |
log: actorTag=...
```

Unlike unkeyed SHA-256(email), HMAC resists dictionary attacks if the key is kept secret and sufficiently strong. However, **pseudonymous is not anonymous**: a stable tag still enables behavioral linkage, and anyone with the key or another reference source can infer identity. Therefore, you need:

- Secret/key storage and rotation policy.
- Scoping by purpose/tenant if cross-context linkage must be restricted.
- Retention policy and tag access controls.
- Key-rotation planning: should history remain linkable, or should rotation intentionally break linkage?
- Input canonicalization testing so one person does not get multiple tags due to formatting differences.
- Never logging the raw identifier when tag generation fails.
- Never logging the HMAC key or stack traces containing the secret key.

Add this mechanism only if there is a genuine investigative need and a privacy review has been completed. For many applications, safe `requestId` and `errorCode` values are sufficient.

## 17. Testing Masking: From Unit Tests to End-to-End

A masking test must prove that **sensitive values cannot appear on the evaluated paths**, not merely that the string `"[MASKED]"` is present.

### 17.1. Test Matrix

| Input or Scenario | Expected Outcome |
| --- | --- |
| Full email | No raw address in logs |
| Phone number | No raw phone number remaining |
| Bearer token | No secret token/prefix outside policy |
| Cookie/session | No session ID |
| Password/OTP | Omitted/redacted, no partial value stored |
| Nested `user.credentials.password` | Recognized by field-path policy or object dropped |
| Unknown field | Fail-closed, raw value not printed |
| Null/empty | Handled per schema, no NPE |
| JSON string with quotes/backslashes | Properly escaped by encoder |
| Newline/CR/tab | No forged log lines created |
| Unicode/emoji | Does not corrupt encoding; masking respects code points |
| Base64/URL encoding | Do not rely on simple regexes to guarantee full masking |
| Object `toString()` | Does not accidentally dump sensitive fields |
| Throwable message containing token | No leak through cause/stack trace at sink |
| MDC containing sensitive value | Not exported or already redacted |
| Async/thread pool | No context leak across tasks |
| Multiple appenders | No sink receives raw data |
| Logback JSON encoder | Field names, types, and redaction are correct |
| File rotation | Old archives contain no raw data outside policy |
| Sidecar collector | No raw data logged in collector debug/error logs |
| Remote 429/503 | Retries/buffering do not dump payloads on error |
| Missing masking rule | Raw value never used as fallback |
| Schema update | New fields classified before release |
| High throughput | Masking does not cause log storms, CPU spikes, or unmeasured drops |

### 17.2. Tests for the Java 17 Code in Section 6

The program already includes two test payloads and `assertSafe`:

- `email` must become `[MASKED]`.
- `authorization` and `accessToken` must become `[REDACTED]`.
- `rawPayload` must not be emitted because it is not in the policy.
- A `requestId` containing a newline must become `[INVALID]`.
- No extra `ERROR forged` line may be emitted.

This is a **smoke test**. When turning it into a library, write **JUnit 5 parameterized tests** per sensitivity class, covering various null, Unicode, whitespace, nested data, and malformed syntax cases. Unit tests should verify **the values of `SafeLogEvent`**, independent of whether the logger has INFO enabled.

### 17.3. Verifying After the Encoder and Collector

An integration workflow can include:

1. Create a set of unique **synthetic secrets** used only for testing, such as the marker string `SYNTHETIC_SECRET_ALPHA`.
2. Emit events through the application's actual logging backend/encoder.
3. Collect log files/console output using a test appender or an isolated temporary volume.
4. For JSONL, use a **real JSON parser** to read each line; verify event counts and schema.
5. Search for synthetic secret canaries across **all outputs** and nested fields.
6. Pass the data through a test sidecar/collector and query the test log sink.
7. Verify that the collector does not emit raw values in its status/error/debug logs.
8. Test rotation, restarts, buffer retries, process crashes, and network outages.
9. Verify that historical data in archives and destinations has appropriate retention applied.
10. Evaluate logs from **third-party libraries** if they have independent logging paths.

**Never use real secrets as test data.** When a test detects a leak, saving screenshots or raw logs in a ticket can also widen exposure; record test results and controlled canary tests instead of copying real credentials.

## 18. Risks in Commonly Forgotten Layers

### 18.1. Logging Before Masking

A controller calls `log.debug("request={}", request)` before `SafeLogEventBuilder` runs. Even if the main event is safe, that first debug log still leaks. Review **all log call sites** in critical flows.

### 18.2. Multiple Log Sinks

The console appender has masking, but the file appender or telemetry exporter still stores raw data. The reverse happens too. Test all appenders and paths.

### 18.3. Exception Chains

A wrapper exception that preserves its cause can still retain an exception message containing a URL/token. Do not just mask the wrapper's `getMessage()` and let the encoder print the raw `Caused by` underneath.

### 18.4. Runtime Log Level Changes

DEBUG/TRACE may be off now, but can be enabled during an incident. Masking policies must be **correct at every level**, not just INFO/ERROR.

### 18.5. Request Bodies and Message Payloads

Logging entire DTO objects or Kafka records easily includes fields not in the policy. Emit only the required **metadata and event codes**. Data that fails deserialization should not be dumped raw in catch blocks either.

### 18.6. Collector Parse Errors

A malformed JSON event can cause a collector to log the raw line for debugging. If it contains sensitive data, this creates a **new copy** in collector logs. Configure error logging and invalid-record quarantine safely.

### 18.7. Over-Masking Breaking Observability

If you mask `event`, `outcome`, `errorCode`, or `traceId`, dashboards can lose value. Classify by field and purpose; use standard error codes and valid IDs rather than blanket-replacing all strings.

### 18.8. Log Injection Despite Masking

Masking email/tokens does not prevent a public field from containing `\nERROR forged`. Validate/escape **all client-controllable data**, including correlation IDs and message text.

### 18.9. Information in URLs/Queries

Tokens can appear in `httpClient.get(url)` exceptions, proxy access logs, or raw `request.getRequestURL()`. For HTTP logging, use route template/method/status instead of raw URLs whenever possible.

### 18.10. Diagnostic Events Containing Config Snapshots

A debug log may print all environment/system properties, config files, or connection strings. Usually these should not be logged raw; log the setting name and `changed`/`enabled` state, omitting secret values.

## 19. Performance and Sizing of the Masking Pipeline

Masking has costs:

- Field classification and policy lookup.
- String copying, JSON encoding, and allocations.
- Regex scanning on large messages (if used).
- Nested object traversal, which can spike CPU if depth is unbounded.
- Formatting and escaping long strings.
- Per-event overhead at high throughput.

Recommendations:

1. **Data minimization first:** do not pass large objects into logging only to scan them afterward.
2. Use a **fixed catalog and lookup maps/enums** for common fields.
3. Avoid regexes on large raw payloads; if unavoidable, bound input size and pattern complexity.
4. Enforce limits on field count, string length, and nesting depth.
5. Do not serialize expensive debug data when that log level is disabled.
6. Measure p95/p99 logging latency, CPU/allocation, dropped events, and queue utilization.
7. For required audit logs, design a durable write path independent of sampling.
8. Use load tests to check whether masking causes appender/collector bottlenecks.

With SLF4J:

```java
// Integration snippet: expensiveDebugView() may be CPU-intensive.
if (log.isDebugEnabled()) {
    log.debug("event=debug.summary data={}",
            expensiveDebugView()); // Returns data already permitted for logging.
}
```

A placeholder does not make `expensiveDebugView()` lazy because Java evaluates arguments before calling `debug`. Still, do not return `request.toString()` from this method; return a debug DTO **whose fields are already classified and bounded**.

## 20. Policy When Masking Fails

Masking is code and can fail due to:

- A missing rule for a new field.
- Null or unexpected object types.
- JSON parser failure.
- Regex timeout or excessive CPU usage.
- Serializer encountering invalid Unicode or cyclic objects.
- Missing or mismatched policy configuration version.
- A downstream encoder not following the defined schema.

Choose explicit behavior:

| Case | Recommended Behavior |
| --- | --- |
| New unclassified field | Omit or `[REDACTED]`; alert on schema policy safely |
| Secret field is null | Omit or represent null per schema, no NPE |
| Invalid public identifier | `[INVALID]` or fall back to server-generated ID |
| Serializer error | Never print the raw object as fallback |
| JSON parse error at collector | Quarantine/drop per policy, never dump raw line |
| Masking too slow | Enforce size limits and instrumentation; do not disable masking |
| Audit event cannot be protected | Follow defined fail-closed/fail-safe policy, do not silently drop |
| Test detects a secret | Block release, assess retained logs, and handle as an incident |

If a service cannot produce a **safe audit record** and a sensitive business operation requires auditing, handling must follow business policy (which may mean rejecting the operation). For routine diagnostic logs, dropping a risky field is usually better than sending a secret to a sink.

**Never include raw content in the error message of the masking mechanism itself.** For example, avoid `throw new RuntimeException("mask failed for: " + raw)`; that message could itself be logged.

## 21. Project Rollout Process

A practical rollout plan can follow these steps:

### Phase 1: Identify Scope and Log Paths

- Inventory HTTP access logs, business logs, exception logs, message consumers, scheduled jobs, and third-party libraries.
- Document appenders: console, file, rolling archive, remote/OTLP, sidecar.
- Use **synthetic secret canaries** to detect leak paths in test environments.
- Pick a specific flow such as `profile.update.result` to practice first.

### Phase 2: Establish Policy

- Catalog fields and sensitivity classes.
- Separate `DROP`, `REDACT`, `MASK`, and `ALLOW`.
- Define error code enums and validators.
- Lock in the default for unknown fields: fail-closed.
- Define who approves allowlist expansions.

### Phase 3: Build SafeLogEventBuilder

- Start from the Java 17 demo.
- Move the policy into versioned configuration or Java types.
- Do not accept arbitrary object graphs without a controlled serializer.
- Bound string length, key length, and field count.
- Separate JSON encoding from data-sensitivity decisions.

### Phase 4: Integrate into the Logger

- Configure SLF4J/Logback or Log4j 2 accordingly.
- Emit real structured fields through the encoder.
- Apply field policies to MDC, Throwables, and all appenders.
- Remove legacy raw request/body/header logs.
- Avoid duplicating events across multiple ingest routes.

### Phase 5: Test and Monitor

- Unit tests for each field class and edge case.
- Integration tests for JSONL/console/file outputs.
- Test the collector and retention/rotation.
- Negative tests with canaries and log injection.
- Dashboard metrics for masking policy violations (with no raw values).
- Manual review of a controlled sample of logs.

### Phase 6: Historical Review and Operations

- **New masking does not erase data already written earlier.** If historical leaks are found, follow an incident response process: impact assessment, access control, retention, policy-compliant deletion, and credential rotation when needed.
- Restrict access to sinks that may still hold raw data.
- Update coding standards, code review checklists, and onboarding.
- Add CI guardrails such as synthetic secret tests or well-grounded static analysis.
- Monitor performance, false positives/false negatives, and troubleshooting experience.

## 22. Acceptance Criteria for the Exercise

A complete result should satisfy:

| Criterion | Expected Evidence |
| --- | --- |
| **Clear source policy** | Field list and treatments reviewed |
| **Runs standalone on Java 17** | `javac` and `java` succeed |
| **Masks secrets** | No `Bearer secret-token` in stdout |
| **Masks PII** | No raw email/phone |
| **Fail-closed on unknown fields** | `rawPayload` is not emitted |
| **Blocks basic log injection** | ID containing newline becomes `[INVALID]` |
| **Sufficient event context** | `event`, `requestId`, `outcome`, `errorCode` are intact |
| **No pipeline bypass** | All appenders/collectors verified |
| **Valid JSONL if using JSON** | Parses as objects with correct field types |
| **Throwable and MDC evaluated** | No leaks via exceptions/ThreadLocal |
| **Safe under rotation/retry** | No raw data emitted into archives or failed collector logs |
| **Canary tests present** | No synthetic secrets found at final sink |
| **Policy alerting present** | Schema violations measured without raw values |
| **Data lifecycle managed** | Retention, permissions, and leaked-data response defined |

These criteria are for a controlled exercise/prototype. A real financial, healthcare, or identity system may require deeper threat modeling, auditing, and industry-specific compliance.

## 23. Anti-Patterns to Avoid

### 23.1. Masking at the Collector While Writing Raw Logs to Disk

Data already exists in archives/local volumes and may be backed up before reaching the collector. Mask at the source first; the collector is only a supplemental layer.

### 23.2. Masking Only the Message and Ignoring MDC/Throwable

Those paths can still carry tokens or personal data. Evaluate the entire `LoggingEvent` and all appenders.

### 23.3. Printing Objects/DTOs via `toString()`

Auto-generated `toString()` may include a newly added field after a deployment. Select specific fields instead of serializing entire objects.

### 23.4. Relying Solely on Email Regexes

A secret may not look like an email or may use unusual encoding. Regexes do not replace field classification.

### 23.5. Partial Masking by Default

Keeping domains or suffixes can be enough to re-identify individuals. Default to full masking/dropping when there is no specific need.

### 23.6. Hashing Emails Without a Key and Calling It Anonymous

Emails and phone numbers have relatively small guess spaces and are vulnerable to dictionary attacks. Consider HMAC and a privacy policy when linkage is required.

### 23.7. Logging Raw Data When Masking Throws an Exception

This is fail-open. Design fallbacks so raw data is never passed to the logger.

### 23.8. Allowing Arbitrary Field Names

Clients could create fields like `token123` or thousands of keys, causing mapping explosions and bypassing rules. Field names must be cataloged.

### 23.9. Enabling DEBUG to "See the Entire Request"

This easily leaks passwords, card data, and cookies. Enable a narrow debug mode with vetted data, explicit permissions, and a time limit.

### 23.10. Treating Masking as the Only Solution

Even when properly masked, log data can still contain sensitive metadata and requires RBAC, TLS, retention, encryption, and access auditing.

## 24. Production Readiness Checklist

- [ ] Classify fields by sensitivity, purpose, and usage permissions.
- [ ] Never log secrets, raw payloads, full headers, or DTO `toString()` by default.
- [ ] Enforce an allowlist and fail-closed default for unknown fields.
- [ ] Choose DROP/REDACT/MASK/ALLOW per field and event.
- [ ] Never use plain SHA-256(email) to claim anonymization.
- [ ] Validate/escape IDs and controllable inputs to prevent log injection.
- [ ] Use an appropriate structured JSON encoder when queryability is needed.
- [ ] Check MDC, request/response, message consumers, Throwables, and suppressed causes.
- [ ] Review all appenders, loggers, and collection paths—including collector debug logs.
- [ ] Test the Java 17 example, unit tests, integration tests, and synthetic canaries at the sink.
- [ ] Test with debug level enabled, full async queues, rotation, restarts, and network errors.
- [ ] Bound string size/nesting and measure CPU/GC and memory overhead.
- [ ] Emit metrics for policy violations without raw data.
- [ ] Do not let new masking hide previously written raw data: have a historical remediation plan.
- [ ] Protect logs with appropriate RBAC/TLS/retention and access auditing.
- [ ] Give sensitive audit events dedicated durability/integrity separate from diagnostic logs.
- [ ] Maintain a schema review process when adding fields or changing DTOs/dependencies.

**Conclusion:** **Adding data masking** is an essential part of designing a Java logging strategy. The most solid approach is to **minimize data at the source, allow only classified fields, vet data before creating log events, and verify output at every sink**. The Java 17 demo shows a straightforward pattern: allowlisting, full masking/redaction, validation, and fail-closed behavior. When integrating with SLF4J/Logback/JSONL, you must continue protecting **MDC, Throwables, payloads, collectors, and archives**, because a single unmasked path can undermine the entire policy.
