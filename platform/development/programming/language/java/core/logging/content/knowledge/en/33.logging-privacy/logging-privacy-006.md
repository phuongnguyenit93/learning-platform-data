# Redaction in Java Logging: Protecting Private Data When Writing Logs

## 1. What is Redaction and Why is It Necessary?

**Redaction** is the process of **removing, replacing, or obscuring sensitive content before a log record is delivered to any place not authorized to see the original data**. In Java logging, the goal is to ensure the system still has incident-investigation information without putting passwords, access tokens, payment details, personal data, or confidential business content into the console, files, collectors, dashboards, or storage.

An example input might be:

~~~text
event=login_rejected email=alice@example.test authorization=Bearer sample-token
~~~

The record permitted for output under a hypothetical policy:

~~~text
event=login_rejected email=[REDACTED] authorization=[REDACTED]
~~~

Some systems choose **not to log the two sensitive fields** in the first place; that is usually better than capturing them verbatim and redacting afterward, because the raw data never has to travel through the logging pipeline. In cases where you still need to know whether a field was present, you can log a boolean flag or an approved status value instead of the raw value.

Redaction is not simply replacing characters with asterisks. It requires understanding **which fields are sensitive, who is authorized to view them, where values can appear, which layer is responsible for handling them, and how to verify that raw data does not leak into sinks**.

Note that log levels **INFO/WARN/ERROR** do not distinguish between safe and sensitive data. An ERROR log containing an exception message with a password can still leak a secret. When a product scales out to multiple instances, copies of the same event can travel to multiple systems, amplifying the impact of a leak.

## 2. Distinguishing Redaction, Masking, Suppression, Pseudonymization, and Encryption

These techniques are related, but they **do not provide the same protective properties**:

| Technique | How It Works | Example | What to Understand |
| --- | --- | --- | --- |
| **Suppression / omission** | Do not emit the field | Do not log the Authorization header | Preferred if the field is not needed for operations |
| **Full redaction** | Replace the entire content with a fixed marker | email=[REDACTED] | The original value cannot be recovered from the marker itself |
| **Masking** | Hide only part of the value | phone=******1234 | The remaining portion may still identify the user |
| **Pseudonymization** | Replace an identifier with a substitute value | accountRef=acct-token-27 | Events can still be linked; often remains re-identifiable data |
| **Tokenization** | Use a token linked to a value in a separate vault | customerToken=tkn-... | Reversibility depends on the vault and access permissions |
| **Hashing** | Generate a digest from the value | emailHash=... | Small-domain values are vulnerable to dictionary attacks |
| **Keyed HMAC** | Compute a digest using a secret key | subjectRef=HMAC(key, identifier) | Useful for controlled correlation, but the key must be protected |
| **Encryption** | Encrypt data so it can be decrypted by key holders | encryptedPayload=... | Not equivalent to redaction; plaintext can be recovered |

**Hiding a few characters is not necessarily safe enough.** For example, a postal code, date of birth, or the last four digits of a card number can sometimes be combined with other sources to identify someone. For data minimization requirements, it is usually better to **omit the field or use a marker** rather than keeping unnecessary portions.

**Hashing is not anonymous by default.** Emails, phone numbers, or customer IDs can be brute-forced or looked up via dictionary attacks if an unkeyed hash is used. HMAC with a private key reduces some risks, but the derived ID may still be considered personal data depending on context, and still requires retention and access controls. Never put an HMAC key or encryption key in logs.

**Redaction cannot fix a log record that has already been distributed.** If a token has already reached a collector, hiding it from a dashboard view does not mean copies in indexes, archives, exports, and backups have been handled.

## 3. Classify Data Before Writing a Logging Policy

You cannot redact accurately without knowing which category each field belongs to. Define a data classification tied to the source and purpose of the log:

| Data Category | Examples | Typically Appropriate Logging Policy |
| --- | --- | --- |
| Low-sensitivity operational metadata | eventCode, service, module, outcome | Log if useful and standardized |
| Technical correlation IDs | requestId, traceId, jobId | Can be kept when safely issued and governed by an access policy |
| Personal identifiers | email, phone, userId, IP address | Restrict, redact, tokenize, or pseudonymize depending on purpose |
| Free-form user-supplied content | search text, comment, filename, request body | Do not log raw by default; extract only necessary, controlled fields |
| Authentication/session data | password, cookie, Authorization header, access/refresh token | Never log raw values |
| Financial data | PAN, CVV/CVC, account details | Never log raw; follow specialized policies |
| Business secrets | API key, private key, connection password, signed URL | Never log raw values |
| Error/exception data | exception message, SQL statement, stack trace | Check for potential sensitive values before emitting |
| Audit metadata | action type, approved principal reference | Log under a dedicated audit policy with data minimization |

**Do not treat data from a database or dependency as unconditionally trustworthy.** A display name stored by a user in the database is still user-controlled data. An HTTP client exception message can contain a URL with a query token, even if the exception was not constructed directly from the incoming request.

You also need to check fields that commonly leak unintentionally: **DTO/entity `toString()`**, serialized request bodies, ORM SQL parameters, HTTP client debug logs, access logs, security filters, message payloads, and MDC context.

Do not build a "global secret list" and assume everywhere is safe. Beyond fixed values, there are dynamic fields produced by new services or third-party libraries; combine a **schema allowlist** with controls over less trusted sources.

## 4. Prioritize Data Minimization and Allowlists at the Source

The design order should be:

1. **Do not create logs containing unnecessary data.**
2. Include in logs **only approved fields** enforced by a schema or typed API.
3. **Redact/mask** sensitive fields if presence or status information needs to be recorded.
4. Use a **structured encoder** to preserve field boundaries.
5. Add **collector-side filtering/redaction** as an additional defense layer, not as the sole line of defense.
6. Apply **access permissions, retention, auditing, and testing** across all destinations.

Examples to avoid:

~~~java
logger.info("Incoming user={}", userDto);
logger.debug("Request body: {}", requestBody);
logger.error("Authentication failed, token={}", authorizationHeader);
~~~

This is an **integration illustration snippet**, not a complete program. If `userDto.toString()` or `requestBody` contains PII or secrets, a single logger call can emit the entire payload. With a `debug` statement, data may still be computed or prepared before the logger filters the event, and `DEBUG` might be temporarily enabled in production.

Instead, choose low-sensitivity event codes and fields, for example:

~~~java
logger.warn("event={} requestId={} reason={}",
        "login_rejected", validatedRequestId, "invalid_credentials");
~~~

**`validatedRequestId`** in the example must actually be generated or validated before logging; a variable name alone does not make data safe. For fixed-category fields such as `event`/`reason`, use an enum or an allowed set of values, and avoid placing raw user-supplied messages into fields used for alert classification.

## 5. Where in the Pipeline Should Redaction Happen?

~~~text
User input / message / dependency
       |
       v
Java application: validate, select fields, omit/redact at source
       |
       v
SLF4J/JUL/Log4j 2: create event, attach MDC, Throwable
       |
       v
Encoder/Appender: serialize fields and control output
       |
       v
stdout / file / network
       |
       v
Collector: parse, filter, apply additional redaction, route
       |
       v
Storage / SIEM / dashboard / export / archive
~~~

Each location has advantages and limitations:

| Location | Advantages | Limitations |
| --- | --- | --- |
| **Business/service code** | Knows field semantics; can avoid putting secrets in logs altogether | Requires code review discipline; hard to cover third-party libraries |
| **Logging wrapper / structured event API** | Shared policy, testable, consistent schema | Can be bypassed if code calls another logger directly |
| **Encoder / formatter / appender** | Redacts at the output of a shared provider | May lose original structure if everything has already been flattened into a String |
| **Collector / processor** | Adds protection across multiple services; centrally managed | Secrets have already left the application; raw copies may exist in stdout/files/queues |
| **Dashboard / query view** | Restricts displayed data for specific viewer groups | Does not remove secrets from the backend or earlier copies |

Rule of thumb: **redact as close to the source as possible**. If a raw HTTP token is written to the console and only later redacted by a collector, the token can still remain in runtime logs, container logs, temporary files, network buffers, or debug pipelines. A collector is useful for defense in depth, not as a substitute for restricting raw logs in the Java application.

When there are multiple sinks, you must test **every sink**: console, rolling files, async appenders, collectors, tracing exporters, and third-party error reporting systems may follow different paths.

## 6. Standalone Java 17 Example: Allowlist and Redaction Before Emitting Logs

The following example uses only Java SE 17 to illustrate how to **build a safe log record from input data** without passing a raw map directly to output. The program extracts `event` and `requestId` according to a bounded contract, while `email` and `authorization`, if present, are represented only by a fixed marker.

Create **RedactionDemo.java**:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public class RedactionDemo {
    private static final Set<String> EVENTS =
            Set.of("login_rejected", "payment_failed");
    private static final Pattern REQUEST_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static String safeEvent(String candidate) {
        return EVENTS.contains(candidate) ? candidate : "unknown";
    }

    private static String safeRequestId(String candidate) {
        return candidate != null && REQUEST_ID.matcher(candidate).matches()
                ? candidate : "invalid";
    }

    private static String redactedPresence(
            Map<String, String> input, String key) {
        return input.containsKey(key) ? "[REDACTED]" : "[ABSENT]";
    }

    private static String safeRecord(Map<String, String> input) {
        return "event=" + safeEvent(input.get("event"))
                + " requestId=" + safeRequestId(input.get("requestId"))
                + " email=" + redactedPresence(input, "email")
                + " authorization="
                + redactedPresence(input, "authorization");
    }

    public static void main(String[] args) {
        Map<String, String> received = Map.of(
                "event", "login_rejected",
                "requestId", "req-42",
                "email", "alice@example.test",
                "authorization", "Bearer sample-token");

        String record = safeRecord(received);
        System.out.println(record);
        System.out.println("secretAbsent="
                + (!record.contains("alice@example.test")
                && !record.contains("sample-token")));
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac RedactionDemo.java
java RedactionDemo
~~~

Exact stdout:

~~~text
event=login_rejected requestId=req-42 email=[REDACTED] authorization=[REDACTED]
secretAbsent=true
~~~

Explanation:

1. **`Map.of`** only creates mock data for the demonstration program; it is not equivalent to a request object or logging provider.
2. **`safeEvent`** allows only two fixed event codes; any other value becomes `unknown`.
3. **`safeRequestId`** accepts only alphanumeric characters, underscores, and hyphens, up to 64 characters long. This is an illustrative grammar; a real application needs an appropriate ID contract.
4. **`redactedPresence`** does not read the `email` or `authorization` value; it only checks whether the key exists and emits a marker. This way, raw secrets are never concatenated into the message.
5. **`secretAbsent=true`** checks that the record does not contain the two test values. It **does not prove that all real-world secrets are detected**; the program explicitly selects fields and must be updated when the schema changes.
6. Output uses **`System.out.println`** to demonstrate the principle; in a real application, use a logging framework with structured fields and an explicit redaction schema rather than manually concatenating `key=value` strings.

**Security note:** The record still reveals that the `email` and `authorization` fields were present. If even the presence of a field is sensitive or unnecessary, omit it from the log entirely. Do not replace the marker with the first or last few characters of a token just for debugging convenience.

This example does not attempt to match every PII format with regex. That approach easily misses encodings, nested structures, new secrets, or messages that do not match old patterns. A contract-based **field allowlist** is a more verifiable defense, though other log paths still need monitoring.

## 7. Structured Logging Instead of Manually Concatenating Sensitive Messages

A structured log event typically separates metadata and fields:

~~~json
{
  "timestamp": "2026-11-10T02:41:59Z",
  "level": "WARN",
  "service": "auth-service",
  "event": "login_rejected",
  "requestId": "req-42",
  "reasonCode": "invalid_credentials",
  "email": "[REDACTED]"
}
~~~

This is **illustrative JSON**, not generated automatically from Java SE or a text pattern. To emit JSON, use the standard encoder/serializer of your stack. In text logs, a free-form value containing spaces, newlines, or equals signs can trick parsers; structured fields and proper escaping reduce this risk, though they do not replace redaction.

Rules to follow:

- **Field keys** come from an approved schema, not arbitrary user-generated keys.
- **Event codes** are stable values, not raw exception messages.
- Sensitive fields are **omitted/redacted before serialization**; do not rely on a JSON encoder to guess which fields are passwords.
- Static metadata fields such as `service`/`version`/`environment` can be added at the encoder/collector rather than re-inserted into MDC on every request.
- Use **field presence**, `errorCode`, or `outcome` instead of raw payloads whenever sufficient for investigation.
- If correlation is needed, use an **opaque ID** generated/validated by the application, not `email` or `phone` as the default tracing key.

JSON escaping ensures format validity; **it does not hide data**. A JSON encoder can escape quotes and newlines perfectly while still writing a raw token: the event is syntactically valid yet violates privacy policy.

## 8. SLF4J, MDC, and Logback: Common Data Leak Points

In Java applications using SLF4J/Logback, MDC often holds request/trace context. Keep in mind:

- **`MDC.put("email", rawEmail)`** can cause the email to appear on every log line when an encoder is configured to output the entire MDC.
- **`%X{someKey}`** or a JSON encoder reading MDC only reads the existing value; it **does not automatically redact**.
- When using **`AsyncAppender`**, an event may snapshot context on the producer thread; modifying MDC afterward does not necessarily update an already enqueued event.
- MDC values populated from client-sent HTTP headers must be validated; a `requestId` containing a token or newline can pollute many events.
- When thread pools are reused, failing to clear MDC in a `finally` block can leak context from request A into logs for request B.

Example using a server-validated ID scoped to MDC:

~~~java
import org.slf4j.MDC;

void processRequest(String validatedRequestId, Runnable work) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", validatedRequestId);
        work.run();
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

This is an **integration snippet**, requiring SLF4J and a logger implementation that supports MDC. Validate `validatedRequestId` before calling this method. A library that owns only the `requestId` key should restore **that specific key** instead of calling `MDC.clear()` and wiping out keys owned by the caller or tracer.

**Do not put a raw user object or an entire request body into MDC.** Instead, keep only `traceId`/`requestId`/`jobId` and approved metadata. With async executors, capture, activate, and restore context appropriately; redaction and propagation are two separate responsibilities.

### Redaction in Logback or Appenders: Use as Additional Defense

Logback may support layout/encoder/filter mechanisms depending on version and dependencies. Some systems use converters or regex replacement on messages. However, understand the limitations:

- If a pattern only redacts **`%msg`**, values in **`%X{...}`**, markers, argument fields, throwables, or data added automatically by the encoder may bypass the same rules.
- Text-based regex does not always catch tokens that are split across strings, encoded, differently cased, or nested inside JSON.
- A filter running after an event enters an async queue may operate **later** than the point where raw data was snapshotted.
- When adding a new appender, you must reapply the policy; do not assume an old appender's configuration protects all sinks.

**Placing field-level redaction at the source or structured event builder** is usually clearer than regex replacement over combined messages. You can still use sink-side redaction as an extra guardrail if its coverage is tested.

## 9. Exception Messages, Stack Traces, and Commonly Overlooked Errors

A common call:

~~~java
logger.error("Payment failed for requestId={}", requestId, exception);
~~~

In SLF4J, when a `Throwable` is passed properly, the provider can log the stack trace. However, **`Throwable.getMessage()`** or stack trace details generated by libraries may contain URLs, SQL, query parameters, user input, or sensitive configuration. Redacting only the **`requestId`** parameter does not guarantee the entire event is safe.

You must distinguish:

1. **Exception type / stack location**: valuable for technical investigation and usually safe.
2. **Exception message**: may contain external values or system details; not safe by default.
3. **Nested cause / suppressed exceptions**: may carry additional sensitive content.
4. **Framework error handlers** or HTTP client interceptors may log requests/responses on their own even after application code is fixed.

The practical solution is to avoid putting secrets into exception messages at the source whenever you control them; log safe **`errorCode`/`exceptionType`/`operation`/`correlationId`** fields; configure libraries to avoid dumping payloads; and apply a Throwable filter/formatter policy if genuinely needed. **Do not strip stack traces at all costs**: you can retain error location information in an appropriately protected sink or use a formatter that avoids emitting sensitive messages to general logs.

Example of safe formatting at a boundary, logging only the error type and event code:

~~~java
logger.error("event={} requestId={} exceptionType={}",
        "payment_failed",
        validatedRequestId,
        exception.getClass().getSimpleName());
~~~

This is an **integration snippet**. Omitting the `Throwable` can lose needed stack traces; if stack traces are required, control exception contents and use an appropriate sink rather than always dropping them. Do not sacrifice error handling: redaction does not replace retries, rollbacks, or proper error responses.

## 10. HTTP Headers, Bodies, URLs, and Access Logs

Redaction only in the service logger is not enough when frameworks, reverse proxies, or access logs record HTTP data.

**Authorization/Cookie/Set-Cookie:** Do not log raw values by default. Other token-bearing headers such as `X-Api-Key` need a similar policy. Do not truncate credentials to the last few characters unless specifically required and approved.

**URL/query string:** URLs can contain signed URLs, emails, session IDs, or access tokens. Do not log full query strings unless truly necessary. Log a **route template** such as `/orders/{id}` and status code instead of a full URL containing personal IDs and queries.

**Request/response body:** Bodies can be nested JSON, multipart, binary, or free-form text. Generic regex redaction over serialized bodies is error-prone and expensive. Do not dump bodies by default; if an endpoint genuinely needs diagnostic fields, build a dedicated allowlist and enforce length limits.

**Proxy/ingress access logs:** These sit outside Java code, so inspect infrastructure as well. An application might not log tokens while the ingress still logs query strings; apply a consistent policy across the entire system.

**HTTP client logs:** When `DEBUG` or wire logging is enabled on an HTTP client, headers and bodies may be logged automatically. Review library configurations in staging and production; do not turn on verbose logging during an incident without assessing privacy impact.

## 11. ORM, Databases, Messaging, and Background Jobs

**ORM/SQL:** Hibernate/JDBC debug logs or interceptors may contain SQL with bind parameters, including personal data. If performance diagnostics are needed, prefer query duration, query identifier, template, or statement fingerprint over raw bind values. Do not assume all SQL logs are safe metadata.

**Message brokers:** Kafka/RabbitMQ consumers may log headers, keys, and payloads during retries or dead-lettering. A message ID or `jobId` can be used for correlation; message payloads need their own data policy. An exception thrown during deserialization may include a snippet of the malformed payload.

**Batch jobs:** It is tempting to log every failed record. Instead, log `taskId`, `errorCode`, `attemptNo`, and total failure count; if a record needs investigation, store evidence in a controlled system rather than leaving raw PII in general logs.

**Third-party SDKs:** Payment, auth, email, cloud client, and monitoring agents can emit logs without direct calls from your app. When upgrading dependencies, check logging defaults, especially at `DEBUG`/`TRACE` levels.

**Background retries:** A sensitive value can repeat across multiple attempts, creating multiple copies in the backend. Redacting before emitting the event prevents multiplying exposure by retry count.

## 12. How Does Redaction Relate to Log Forging?

These are two distinct problems:

- **Redaction** aims to reduce exposure of sensitive information.
- **Log forging/injection** aims to prevent untrusted data from being interpreted as log record syntax.

A value with no secrets that contains CR/LF can still forge logs. Conversely, a JSON encoder that escapes CR/LF perfectly can still log a raw password. Therefore, you need **both proper output encoding/framing and redaction**.

The following example is a mock string, not a real secret:

~~~text
requestId=req-42\r\nINFO event=admin_authenticated
~~~

If `requestId` is client-supplied without validation, a line-oriented text formatter can produce a forged line. For technical IDs, validate grammar and length. For free-form text fields, the output encoder must escape according to the target format. Do not use a secret-finding regex as a substitute for delimiter/newline controls.

## 13. Hashing, HMAC, and Tokenization for Correlation

Some use cases require linking logs across multiple operations without storing raw emails or account IDs. Options must be evaluated against privacy policy:

**Random opaque ID:** Issue a random ID for an authenticated business request/session. The ID used in logs does not directly reveal real identity. Store the mapping in a protected system only when genuinely needed.

**Tokenization:** Generate a token and store the mapping under access control. Anyone with vault access can look up the original value, so a token is not harmless data. Manage mapping lifecycle and retention.

**Hash:** Small-domain values such as emails or phone numbers can be inferred via dictionary lookup. Using an unkeyed hash is not recommended for claiming data is anonymized.

**HMAC:** Use a dedicated secret key and standard algorithm to produce a stable matching value within the required scope. Enforce key rotation, key separation by purpose, view restrictions, and expiration rules. Tokens and HMACs can still allow linking a person's activity over time, so evaluate re-identification risk and data protection policies.

**Encryption:** Encrypted data can still be recovered with the key; it protects data at rest/in transit, **not a replacement for redaction**. If reversibility is not needed, do not retain mappings or ciphertext just for debugging.

Do not implement homegrown cryptographic algorithms to obscure IDs in logs. Use standard libraries, manage keys properly, and review with the security team when a use case genuinely requires reversible correlation.

## 14. Privacy and Retention Policies in Production

A record with one field redacted is not necessarily completely safe. Combining several individually harmless fields can re-identify someone. For example, an exact timestamp, IP address, location, and rare route can point to a specific user or action.

Policy design should answer:

- Who is allowed to view general logs, security logs, audit logs, and error records?
- Which fields are visible on standard dashboards, and which are restricted to protected channels?
- How long does data persist on hosts, collectors, backends, archives, backups, and exported reports?
- Is there a mechanism to delete or invalidate copies when data has been logged by mistake?
- When `DEBUG` is enabled in production, what additional fields are emitted?
- Do external vendors or processors receive identifiable data?

**Retention** does not replace redaction: a record kept for only 24 hours can still be viewed or forwarded during that window. **Redaction** also does not replace RBAC/ABAC: records may still contain internal information or correlation IDs requiring authorization.

Where privacy or legal requirements apply, follow your organization's policies and applicable regulations in your operating jurisdiction. Do not claim that a single redaction technique automatically satisfies all standards or data protection laws.

## 15. Unit Tests and Integration Tests for Redaction

An effective test suite must test high-risk fields, not just a single fixed payload.

### 15.1. Unit Tests

- For `email`/`authorization` fields, output values must be the defined marker or the field must be absent.
- For a `requestId` failing regex/length validation, logs use the safe marker; never the raw input.
- For an `eventCode` outside the allowlist, the event must be normalized, never letting users dictate log level or event name.
- Null or missing fields do not throw exceptions and do not emit sensitive strings.
- Raw object `toString()` is not used when building events; verify using a DTO containing canary values.
- Records containing Vietnamese Unicode characters still parse correctly; safe data is not accidentally corrupted.

### 15.2. Integration Tests

- Emit events containing mock passwords/tokens, mock emails, and mock payment data; collect output from **console, file, async queue, collector, and backend** along the actual pipeline.
- Verify raw secrets **do not appear** in any accessible sink; do not check only the UI.
- Test a `Throwable` with a nested cause containing a mock secret; verify policy for stack traces and exception messages.
- Test MDC containing malformed input and reused thread pool contexts; values must not leak to subsequent requests.
- Test with `DEBUG`/`TRACE` temporarily enabled in staging; ensure no raw request bodies, headers, or bind parameters are emitted.
- Test that JSON logs are parsed into valid fields without log forging via newlines or delimiters.
- Test sensitive values appearing in different encodings or key case variations; do not assume a single replacement regex has complete coverage.
- Test when the collector is unavailable, queues are full, or logs branch to multiple destinations; know which buffers might hold raw values.
- Test updated configurations whenever adding a logger, appender, message consumer, or third-party SDK.

You can use **canary secrets** dedicated solely to staging tests to verify the real pipeline. Never send production secrets or real personal data into test logs.

### 15.3. Testing the Java 17 Program in Section 6

The expected record must match:

~~~text
event=login_rejected requestId=req-42 email=[REDACTED] authorization=[REDACTED]
~~~

Tests must assert that the strings **`alice@example.test`** and **`sample-token`** are absent from the output, while the valid `eventCode` and `requestId` remain visible. Replacing `requestId` with a string containing CR/LF must produce **`requestId=invalid`**; this is required by the example's regex.

## 16. Common Mistakes

| Mistake | Why It Is Dangerous | Right Approach |
| --- | --- | --- |
| Only lowering the log level from DEBUG to INFO | INFO/ERROR can still contain secrets | Prevent raw data from entering any log event |
| Relying only on regex to replace known tokens | Secrets have new formats, encodings, or sit in nested JSON | Field allowlist + serializer + multi-source testing |
| Believing parameterized logging redacts data automatically | Placeholders are only a formatting mechanism | Select safe fields before calling the logger |
| Redacting only at the dashboard | Raw data remains in files/indexes/queues/archives | Redact near the source and verify all sinks |
| Showing the first/last four characters of a credential | Retained characters can aid exploitation or matching | Omit or full redaction per policy |
| Hashing emails with unkeyed SHA-256 and calling them anonymous | Vulnerable to dictionary attacks and still linkable | Consider opaque ID/HMAC + policy |
| Logging the full Throwable for every ERROR | Nested messages may contain URLs/queries/secrets | Review exception data and formatters |
| Putting user email into MDC | Leaks across many events and is hard to clean up | Use a validated opaque ID; scope cleanup |
| Using `DTO.toString` in logs | `toString` may expose all sensitive fields | Structured allowlist |
| Building JSON manually | JSON may be malformed or unescaped | Standard JSON encoder/serializer |
| Configuring redaction on only one appender | Other appenders can bypass it | Source policy + verify each output |
| Using tokenization without managing vault/retention | Tokens remain linkable or reversible | Enforce access control and mapping/key management |
| Running only unit tests | Does not prove collectors/agents are not storing secrets | Add end-to-end tests |

## 17. Responding When Sensitive Data Is Found in Logs

When a token or private information appears in production logs, it is a **data-handling incident**, not merely a display bug.

Steps to consider under an incident response process:

1. **Stop further emission:** disable the verbose path or update the logger/encoder and deploy a tested fix.
2. **Determine scope:** data type, service, timestamps, sinks, collectors, indexes, archives, exports, and third parties that may have received it.
3. **Revoke/rotate credentials** if an active token, API key, password, or secret may be usable; restrict access to exposed data.
4. **Control copies:** perform deletion, access restriction, reindexing, or retention enforcement according to system capabilities and requirements; do not claim full deletion if backups/archives remain unhandled.
5. **Preserve investigation evidence** in a protected location; avoid taking screenshots or pasting secrets back into tickets or chat.
6. **Assess notification obligations** with security/legal teams under applicable policies and regulations.
7. **Add regression tests** and verify with canary data across the entire logging pipeline before closing the incident.

Do not treat the issue as resolved simply by "changing the log level" and ignoring already-written data. If a valid token was exposed, changing logging configuration does not invalidate that token.

## 18. Redaction Design Checklist for Java Logging

| Check | Completion Criteria |
| --- | --- |
| Data classification | Secrets, PII, operational metadata, and audit fields are identified |
| Data minimization | Raw headers, bodies, DTOs, or user objects are not logged unnecessarily |
| Field allowlist | Only approved fields are selected in structured events |
| Validation | `requestId`/`eventCode` and technical IDs have explicit grammars |
| Redaction | Sensitive fields are omitted or replaced with markers before log emission |
| Logging API | SLF4J/JUL/providers do not leak via `toString` or `Throwable` |
| MDC | Contains no secrets; has proper scope cleanup and propagation |
| Encoder | JSON/text properly escaped; redaction is distinct from output encoding |
| Collector | Additional filtering layer and parse-error controls in place |
| Sink coverage | Console, file, async, storage, dashboard, and exports are all tested |
| Access & retention | Policies exist for access control, retention, archives, and backups |
| Correlation | Opaque ID/HMAC used if truly needed; hashes are not treated as anonymous |
| QA | Unit + integration + canary secrets in staging |
| Incident process | Process exists for detection, key revocation, deletion/restriction, and notification |

**Remember:** Effective redaction starts by **not putting unnecessary data into logs**. In Java, build events from an allowlist schema, validate IDs, handle `Throwable` and MDC separately, use properly formatted encoders, and test every destination. Replacing raw secrets with markers is only one part; the ultimate goal is to **preserve investigative capability without exposing private information throughout the entire log lifecycle**.
