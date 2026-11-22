# Log Content Review for Privacy Protection in Java

## 1. Why Review Log Content?

**Log content review** is the process of examining **what information is being recorded**, whether it is genuinely needed for operations/investigation, the sensitivity level of the data, who receives it, and how long it persists. For Java applications, reviewing logs does not stop at `logger.info(...)`: information can also flow through formatters, appenders, MDC/ThreadContext, stdout, files, monitoring systems, collectors, error reports, and storage archives.

A seemingly harmless log call can contain a password in a payload, an access token in an HTTP header, an email in a DTO, personal data in a stack trace, or a query string in a URL. Once it reaches a centralized system, a single log record can be replicated across many places and read by more teams than the original data.

**The goal** is to retain sufficient technical and security evidence without **over-collecting** or turning logs into an ungoverned repository of personal data.

After this lesson, you will be able to:
- Inventory log events and classify fields by purpose, sensitivity, retention, and access permissions.
- Identify where sensitive data leaks from Java code, frameworks, HTTP, exceptions, MDC, and appenders.
- Choose solutions in priority order: **do not log → minimize data → normalize/snapshot → mask or pseudonymize → block/control in the pipeline**.
- Verify protection against **log injection** using allowlists/structured fields, length limits, and encoders.
- Write a Java 17+ example that logs only allowed fields and tests that secrets do not appear.
- Design an automated review workflow in CI, inspect actual data at the collector, and handle incidents when sensitive logs are discovered.

## 2. Which Logs Are Worth Keeping and What Data Should Not Appear?

### 2.1. Start with the Purpose of Each Event

Instead of asking "Can I log this object?", ask:
1. **Why** does the event need to be recorded? Debugging errors, security alerting, measuring latency, auditing, or investigating a transaction?
2. **Who** needs to read it? Developers, on-call engineers, SOC, administrators, or alerting systems?
3. What is the **minimum set of fields** needed to fulfill that purpose?
4. **Which destinations** need the data? Dev console, production files, SIEM, or a separate collector?
5. **How long** does it need to be retained, who has access, and how is it deleted/anonymized?
6. Is there a less sensitive alternative, such as an event code, error bucket, random request ID, or metric?

A diagnostic event typically needs only an error code, action type, outcome, timestamp, and correlation ID. An entire HTTP request/response or user object is rarely the minimal choice.

### 2.2. Practical Classification Table

| Data | Risk or Example | Review Handling |
| --- | --- | --- |
| Password, OTP, PIN, access/refresh token, API key, private key | Can grant access to systems/accounts | **Do not log values**; do not merely mask a few characters if the remainder is still useful for exploitation |
| Session cookie, Authorization header, connection string with credentials | May contain login secrets | Omit or replace with non-sensitive authentication status/type |
| Card number, account number, health information, identity documents | Sensitive personal data or specially protected data | Do not log by default; evaluate purpose/compliance before any exception |
| Email, phone number, address, name, date of birth | Can identify an individual | Restrict/omit; use managed surrogate IDs when genuinely needed |
| IP, user agent, device identifier, coordinates | Can identify or track individuals in context | Store only what serves the purpose; restrict retention and access |
| URL, query string, referrer, HTTP headers | May carry tokens, emails, recovery codes, or payloads | Log route/template, method/status; strip query/headers not on an allowlist |
| Raw body, DTO, entity `toString()` | May include every field, including newly added ones | **Do not log whole objects**; explicitly select allowed fields |
| Stack trace, SQL statement, HTTP client error | May expose paths, input data, parameters, or headers | Keep debugging info, strip sensitive fields; inspect exception cause/message |
| Independently generated `requestId`/`traceId` | Useful for correlating records | Allowed if it embeds no PII and has access/retention limits |
| Event code, outcome, latency bucket, status code | Usually less sensitive | Prefer structured logging with controlled types and enums |

**Pseudonymization is not anonymization**: surrogate identifiers or consistent hashes can still link events together and may remain personal data in context. Do not assume `SHA-256(email)` is "anonymous" if emails can be guessed, dictionary-attacked, or linked across systems.

The permissible level of data processing also depends on applicable laws, organizational policies, contracts, and specific purposes. This article presents technical controls; do not treat any retention period or field as legally compliant in all systems.

## 3. Common Leak Paths in Java

### 3.1. Logging Whole Objects or Requests

```java
// Example code NOT to use: objects may contain passwords/tokens.
LOG.info("registration={}", registrationRequest);
LOG.debug("headers={}", httpHeaders);
LOG.info("user={}", userEntity);
```

Parameterized logging reduces formatting overhead when the log level is disabled, **not** when the log level is enabled. The `toString()` method of a Java record, Lombok `@ToString`, DTO, or entity can automatically include sensitive fields; fields added later may accidentally appear without anyone touching the log statement.

A safer approach is to explicitly select fields defined in a **logging contract**:

```java
// Illustrative snippet requiring variables/Logger/DTO defined in the application.
LOG.info("event=registration_result requestId={} outcome={}",
         requestId, outcomeCode);
```

Condition: `requestId` must be independently generated/validated, and `outcomeCode` must be a managed enum or code. Do not pass `registrationRequest` or email/password into the message.

### 3.2. Headers, URLs, and Bodies

The following values may contain secrets:
- `Authorization: Bearer ...`, `Cookie`, `Set-Cookie`, `X-API-Key`.
- Query strings `?token=...`, `?email=...`, `?code=...`, and sometimes even path segments.
- Form/JSON bodies, multipart uploads, file contents, and third-party partner responses.
- SQL queries with bind parameters, especially when ORM/driver or datasource logging is enabled at DEBUG/TRACE.

In an HTTP server, log `method`, **route pattern** such as `/users/{id}`, status, latency, and a server-issued correlation ID. Do not log the full URL and try to strip a few parameters with regex; parameter names can change, tokens can appear in paths, and encoding can vary.

Do not enable global request/response logging in production just for temporary troubleshooting. When part of a body is genuinely needed, define an allowed field list, sample size, length limit, enabled duration, approver, and a separate destination.

### 3.3. Exceptions and Stack Traces

```java
// Code to review because the exception message may contain user-supplied values.
LOG.error("failed to process request {}", request, exception);
```

Information in `exception.getMessage()` or a nested cause can contain user input, internal paths, SQL, or URLs with credentials. However, **do not mechanically drop all exceptions**: stack traces are critical for investigating failures.

A balanced approach:
- Log an error code, error type, and a safe correlation ID.
- Decide whether to record the throwable/stack trace based on event type, environment, and sensitivity.
- Ensure custom exceptions do not embed secrets in their messages at creation time.
- Check whether formatters/encoders automatically output the cause chain, suppressed exceptions, and context.
- For errors requiring deep investigation, consider a separate secure diagnostic channel rather than dumping all data into general logs.

### 3.4. MDC/ThreadContext and Structured Logging

SLF4J MDC or Log4j 2 ThreadContext helps attach `requestId`, `traceId`, and `tenantId`. However, when a pattern uses `%X` or a JSON layout outputs the entire context, a field placed into MDC can travel along with **every event** of the request.

Risky example:

```java
// Do not store the Authorization header in MDC.
MDC.put("authorization", authorizationHeader);
```

Instead, add only approved keys/values, with length limits and data validation. Clean up context in a `finally` block or use framework-appropriate scoped APIs to avoid leaking context across requests in thread pools. With executors/virtual threads, ensure context propagation follows your system's actual mechanism; do not assume `ThreadLocal` behaves identically in every scenario.

## 4. Design Principle: Allowlist Instead of Blacklist Only

An **allowlist** predefines the set of fields/events permitted to be logged. Everything else is **excluded from logs by default**. This is generally safer than scanning arbitrary strings with regexes to find data that should not be there.

Example contract for an authentication event:

| Field | Type/Constraint | Log It? | Reason |
| --- | --- | --- | --- |
| `event` | Fixed enum: `auth_decision` | Yes | Event classification |
| `request_id` | Server-issued random ID, restricted characters/length | Yes | Error correlation |
| `outcome` | `SUCCESS`, `DENIED`, `UNKNOWN` | Yes | Diagnostics and security protection |
| `email` | Personal identifier | No by default | Not needed for general auth logs |
| `access_token` | Secret that grants access | **No** | Risk of account/system takeover |
| `raw_client_text` | External, untrusted input | No | Data leakage and log injection |
| `password` | Authentication secret | **No** | No valid reason to log |
| `user_agent`/IP | Potentially user-linkable | Only with purpose and policy | Do not assume non-sensitive |

A system may need an account identifier to investigate fraud. In that case, consider a separate internal ID and appropriate access controls rather than automatically logging raw emails on every event. Rules must be approved and tested as part of event design.

**Code organization tip:** define a dedicated event type containing only approved fields, rather than letting arbitrary modules pass entire DTOs to the logger. If arbitrary text must be logged, use structured encoding with proper escaping; to prevent log injection, do not merely call `trim()` or truncate strings while ignoring CR/LF.

## 5. Standalone Java 17+ Example: Allowlist Review and Sensitive Data Testing

This example uses only `java.util.logging` and standard APIs. The simulated input contains a fake email, fake token, and text with newlines. We **do not log those three fields**, construct the message solely from allowed fields, and verify that an invalid ID cannot inject CR/LF into the record.

Create **`LogContentReviewDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogContentReviewDemo {
    record AuthAttempt(String requestId, String email,
                       String accessToken, String rawClientText,
                       String outcome) {}

    static String safeRequestId(String value) {
        return value != null && value.matches("[A-Za-z0-9_-]{1,32}")
                ? value : "invalid";
    }

    static String safeOutcome(String value) {
        return "SUCCESS".equals(value) || "DENIED".equals(value)
                ? value : "UNKNOWN";
    }

    static String safeLine(AuthAttempt attempt) {
        return "event=auth_decision request_id="
                + safeRequestId(attempt.requestId())
                + " outcome=" + safeOutcome(attempt.outcome());
    }

    public static void main(String[] args) {
        AuthAttempt input = new AuthAttempt("req_27",
                "alice@example.invalid", "top-secret",
                "bad\nWARN forged", "DENIED");

        String line = safeLine(input);
        if (!line.equals(
                "event=auth_decision request_id=req_27 outcome=DENIED")
                || line.contains("alice@")
                || line.contains("top-secret")
                || line.contains("\n")) {
            throw new AssertionError("Privacy contract failed");
        }

        AuthAttempt malicious = new AuthAttempt(
                "req_28\nERROR injected",
                input.email(), input.accessToken(),
                input.rawClientText(), "unexpected");

        String checked = safeLine(malicious);
        if (!checked.equals(
                "event=auth_decision request_id=invalid outcome=UNKNOWN")) {
            throw new AssertionError(
                    "Untrusted fields escaped allowlist");
        }

        Logger log = Logger.getAnonymousLogger();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };
        sink.setLevel(Level.ALL);
        log.addHandler(sink);

        try {
            log.info(line);
            System.out.println("review_checks=PASS");
        } finally {
            log.removeHandler(sink);
            sink.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LogContentReviewDemo.java
java LogContentReviewDemo
```

**Expected standard output:**

```text
INFO event=auth_decision request_id=req_27 outcome=DENIED
review_checks=PASS
```

### Why Does This Example Not Leak Data?

1. `safeLine` **never accesses** `email`, `accessToken`, or `rawClientText`. Even better is not passing them into the real logging system in the first place.
2. `requestId` is kept only if it matches the allowlist `[A-Za-z0-9_-]{1,32}`; strings containing `\n` are replaced with `invalid`.
3. `outcome` is normalized to three finite values. The input `unexpected` becomes `UNKNOWN` and is never logged verbatim.
4. Tests assert that the message contains no token/email strings or newlines, and that an event with attack input produces a safe output.
5. An isolated logger/handler is used so the program does not require Logback or JVM-wide root configuration; `finally` detaches and closes the handler.

**This is a policy illustration, not a general-purpose personal data filter.** ID allowlists in real applications must align with how IDs are generated/received. If your `request_id` inherently contains personal data or a user-linkable ID, a valid regex still **does not** guarantee the value is non-sensitive. Use server-generated IDs and verify their intended use.

The checks in this example run synchronously on a single thread. If a real backend is asynchronous, tests must wait for events to reach the sink using a timeout mechanism or flush the appropriate API before asserting the final record.

## 6. Masking, Redaction, and Pseudonymization: How Do They Differ?

| Technique | Conceptual Example | Advantages | Risks/Limitations |
| --- | --- | --- | --- |
| **Do not log** | Log only `auth_failed`, not the token | Minimizes data risk maximally | Requires good event design |
| **Data minimization** | Log error code and request ID, not request body | Retains sufficient info | Must define purpose |
| **Masking** | Partially obscure a value not allowed in full | Supports certain specific use cases | Remaining portion may still be sensitive; easily leaked elsewhere |
| **Redaction** | Replace entire secret with `[REDACTED]` | Provides defense in depth | Must accurately identify secrets/fields |
| **Pseudonymization** | Random identifier with secure mapping | Links events without exposing raw PII | Mapping/linkability still requires protection |
| **Hashing** | Produce a digest for an identifier per policy | Useful for certain matching operations | Guessable identifiers can be probed; hashing is not automatic anonymization |
| **Encryption** | Encrypt payload with separately managed keys | Reduces risk on storage compromise | Anyone holding the key can decrypt; does not solve over-collection |

**Prioritize not logging and selecting the right fields at the source**, followed by redaction at the appender/collector. Filtering only at the end of the pipeline means raw values may already reside in the heap, async queues, console, agent buffers, or another appender.

### Why Is Regex Redaction Not a Sole Shield?

Suppose you only strip strings matching an email pattern:
- Secrets may be URL-encoded, Base64-encoded, JSON-escaped, lack an `@` sign, or use a new format.
- Tokens do not look like emails; JWTs, API keys, and session IDs take many shapes.
- Regexes can produce false negatives (leaks) or false positives (over-redacting), destroying diagnostic data.
- Some regexes are CPU-intensive or vulnerable to catastrophic backtracking on large inputs if poorly designed.

If using pipeline filters, maintain diverse test fixtures and **measure false negatives**; never declare "no PII remains" simply because a regex found nothing.

### Is Hashing User Identifiers Safe?

Do not assume `SHA-256(email)` is anonymous by default: email/phone sets can be brute-forced, and identical digests across logs still correlate activity. When approved correlation is required, use an internal random ID or an appropriate keyed pseudonymization mechanism (e.g., HMAC with a private key and controlled rotation); the HMAC secret must never appear in logs. The system must still manage access, retention, key lifecycle, and re-identification risk.

## 7. Preventing Log Injection with Client-Supplied Data

**Log injection** occurs when untrusted data forges record boundaries or fields. For example, an attacker sends a username containing `\r\nERROR access granted`, and the code concatenates it into a text log. A log viewer may display it as a forged error line, disrupting investigations and alerts.

Beyond CR/LF, hand-assembled text formats can be tricked by tabs, `=` signs, CSV delimiters, quotes, control characters, or improperly escaped JSON structures.

Defense in order:
1. **Do not log raw user input** when unnecessary; in the Section 5 example, `rawClientText` is never passed into `safeLine`.
2. If logging is required, **validate types/constraints** (enums, valid IDs, byte/length limits) and replace invalid values with a safe code.
3. Use a maintained structured JSON encoder/schema, escape strings per format, and cap individual field lengths and total event size. Add only fixed keys rather than letting clients determine key names.
4. Keep logging templates constant, passing parameters rather than concatenating parts of the template from input.
5. Test CR/LF, control characters, quotes, special Unicode, large strings, and nested fields at the **final output sink**.
6. Configure viewers/dashboards to render text as plain text, not execute client-supplied HTML/scripts.

**Parameterized logging does not automatically prevent CRLF injection.** For example, `LOG.warn("bad input={}", untrusted)` is cleaner than template concatenation, but if a plain-text output encoder does not escape newline characters, the log structure can still be broken. Combine schema validation with proper output encoding.

## 8. How to Review Java Code and Logging Configuration

### 8.1. Inspecting Call Sites

During code review, prioritize searching for these patterns (do not treat a single grep as conclusive):
- `logger.info("{}", request)`, `LOG.debug("dto={}", dto)`, `System.out.println(entity)`.
- `logger.error("...", exception)` where the exception message contains user input.
- Serializing a DTO to JSON and logging the entire string.
- `MDC.put("email", ...)`, `MDC.put("token", ...)`, and ThreadContext entries with unfamiliar fields.
- Logging URLs with queries, headers, HTTP bodies, or SQL binding parameters.
- Entity/record `toString()` methods and auto-generated string annotations.
- Logging in interceptors, filters, middleware, or instrumentation enabled via config rather than appearing explicitly in service code.

A review table for each call site:

| Question | Evidence to Record |
| --- | --- |
| What is the event used for? | Diagnostic/security/audit purpose and consumers |
| Where do the fields originate? | Constant, server-generated ID, DTO, HTTP input, DB, secret store |
| Are any fields outside the allowlist? | Field name, sensitivity level, removal decision |
| Could level/backend log more broadly than intended? | Effective level, appender, MDC, layout |
| Do multiple destinations receive the event? | Console, file, collector, APM/OTel, backup |
| How long is the data retained? | Retention, indexes, archives, exports, tickets |
| Was it tested with canary data? | Search results on the final event/JSON downstream |

You do not need to log real sensitive data to test. Use **fake canaries** shaped like tokens/emails that grant no real access.

### 8.2. Reviewing Logback and Log4j 2 Configuration

For Logback, check:
- `logback.xml`, `logback-test.xml`, and config files selected via framework/launcher.
- Patterns such as `%msg`, `%X{key}`, or `%X` (which outputs the entire MDC).
- File/console/network appenders; `AsyncAppender` only changes the delivery path and does not redact PII.
- Filters, encoders/layouts, environment-specific level configs, and additional appenders brought in by libraries.

For Log4j 2, check:
- `log4j2.xml`/`log4j2-test.xml`, JSON templates, `PatternLayout`, and how context data is output.
- `ThreadContext` and automatically added fields.
- `AsyncLogger`/`AsyncAppender`, filter chains, and appender references.
- Whether custom message serializers, throwables, or layouts emit unwanted fields.

For JUL, check:
- `java.util.logging.config.file`/`LogManager`, `Handler`, `Formatter`, `Filter`.
- `logger.log(Level, ...)` parameters and `LogRecord` throwables/parameters.
- Whether a JUL-to-SLF4J bridge routes logs through another backend.

**A token-stripping filter on a single appender does not guarantee safety if the same event also goes to another appender before the filter runs.** Inspect every destination route.

## 9. Reviewing Logs at Runtime and in the Collector

Code review checks intent; runtime inspection reveals what the system actually produces and stores. Safe testing workflow:

```text
Generate fake canary data in a test environment
      |
      v
Send request / trigger exception / emit test event
      |
      v
Capture at application logger/appender
      |
      v
Capture at stdout/file/agent buffer
      |
      v
Query logs in collector and dashboard
      |
      v
Inspect archive/export/backup and retention
      |
      v
Compare against event contract + privacy rules
```

Commonly overlooked places:
- APM or tracing agents automatically capturing request attributes/exception messages.
- HTTP client wire logs or access logs generated by reverse proxies/container runtimes.
- Retry queues, dead-letter queues, log shipper buffers, or staging indexes.
- CI job artifacts, screenshots, CSV/JSON exports, and ticket attachments.
- Logs from integrated libraries/SDKs or third-party components.
- Development debug consoles and test records using production data.

Do not download production logs containing sensitive data to personal machines for ad-hoc review. Use approved permissions, appropriate secure environments, managed scanning tools, and aggregated/sanitized results.

### Metrics for Review Outcomes

Consider tracking:
- Number of reviewed call sites/event schemas and approval rate.
- Number of non-allowlisted fields, broken down by service/backend/destination.
- Number of secret/PII canary detections slipping through to the collector.
- Test coverage for sensitive events; number of recurring redaction regressions.
- Number of exceptions/stack traces or body dumps needing remediation.
- Status of retention, exports, read permissions, access audits, and remaining copies.

**False confidence warning:** "zero scan hits" is not proof that no sensitive data exists. Scanners can miss encodings, new token formats, compressed payloads, nested fields, or rare events. Combine design reviews, canary testing, supervised scanning, and pipeline checks.

## 10. Testing with JUnit and Fake Test Data

### 10.1. Unit Testing the Event Contract

In JUnit 5, you can directly test the safe string builder from Section 5. The following is an integration example **requiring JUnit Jupiter** and does not run standalone with plain JDK:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class LogContentReviewTest {
    @Test
    void neverIncludesPrivateFields() {
        var e = new LogContentReviewDemo.AuthAttempt(
                "req_27", "alice@example.invalid", "top-secret",
                "bad\nWARN forged", "DENIED");

        String line = LogContentReviewDemo.safeLine(e);

        assertEquals(
                "event=auth_decision request_id=req_27 outcome=DENIED",
                line);
        assertFalse(line.contains("alice@"));
        assertFalse(line.contains("top-secret"));
        assertFalse(line.contains("\n"));
    }

    @Test
    void rejectsUntrustedIdentifiers() {
        var e = new LogContentReviewDemo.AuthAttempt(
                "req\nERROR injected", "someone@example.invalid",
                "top-secret", "ignored", "UNKNOWN");

        assertEquals(
                "event=auth_decision request_id=invalid outcome=UNKNOWN",
                LogContentReviewDemo.safeLine(e));
    }
}
```

The record and `safeLine` method in Section 5 have package-private visibility; the test must be in the same package, or you should expose an appropriate public API. This tests the **event contract** and does not yet prove the backend does not add extra fields in the layout.

### 10.2. Integration Testing at the Appender

With Logback or Log4j 2, you can attach an in-memory test appender, emit events, and inspect the final fields:
- Level, message template, MDC map, and exception fields.
- Absence of emails, tokens, cookies, raw bodies, or canary values.
- Valid JSON output with no out-of-schema fields.
- Characters like `\r` and `\n` do not create forged records.
- Debug/trace events automatically enabled during tests do not inadvertently expose data.

If the backend is async, wait on a condition with a timeout (latch/poll) and verify the worker received the event. Do not use `Thread.sleep(100)` to assume logs have flushed. After the test finishes, detach the appender, reset the appropriate scope, and restore MDC/levels in `finally`. Avoid modifying the global root logger in parallel tests.

### 10.3. Recommended Regression Tests

1. When a DTO gains a new field named `passwordHash`, the allowlisted event **remains unchanged**.
2. A URL containing `?token=canary` does not appear verbatim in logs.
3. `Authorization` and `Cookie` headers are never printed.
4. An exception cause containing a fake secret does not leak through the formatter.
5. `MDC` contains no email/token values or unapproved fields.
6. Input `"\nERROR forged"` does not create a separate log line.
7. Production configs with multiple appenders/collectors enforce the same policy.
8. All test archives, backups, and exports are deleted after testing per policy.

## 11. When Is Structured Logging Needed?

Structured logging uses schema-backed key/value pairs, as illustrated by **a valid event**:

```json
{
  "event": "auth_decision",
  "request_id": "req_27",
  "outcome": "DENIED",
  "severity": "WARN"
}
```

Benefits:
- Reviewers can clearly identify which fields appear, their data types, and ownership.
- Easy to enforce policies allowing only fixed keys, length limits, and type validation.
- Easy to parse/test and integrate with collectors without relying on regexes over free-form text.
- Compliant JSON encoders escape CR/LF/quotes inside values, reducing the risk of breaking record boundaries.

However, **structured does not automatically mean secure**. If you log `"authorization": "Bearer ..."` or `"request": entireDto`, sensitive data is still collected. And if JSON is assembled manually via string concatenation, it may not escape properly. Use a reliable encoder/layout, define a schema/allowlist, and test against actual output.

In Java, you can use the SLF4J 2.x fluent API with `addKeyValue` or Log4j 2 structured messages/`JsonTemplateLayout` depending on your backend. The API provides structured fields; the application and output configuration must still decide whether a value should be logged.

## 12. Access Control, Retention, and Log Sharing

Content review must be paired with **delivery path** and **lifecycle** review:

| Storage/Read Location | Control Questions |
| --- | --- |
| Local files | Are owner/group/ACLs restricted? Do rotated files and directories share the same policy? |
| Console/stdout | Who views container/CI logs? Are they copied into shared systems? |
| Collector | Who has permission to search, export, create dashboards, or call APIs? |
| S3/object storage or backups | Are encryption, IAM, retention, replicas, legal holds, and lifecycle rules defined? |
| SIEM/APM | Does it automatically attach HTTP bodies, request metadata, exceptions, or unapproved fields? |
| Tickets/attachments | Who receives them, and can they download and retain them? Is there a valid deletion/redaction mechanism? |

Apply:
- **Need-to-know** and role-based access, combined with access auditing for sensitive logs.
- Retention aligned with specific purposes and obligations; distinguish debug, operational, and security/audit logs.
- Encryption in transit/at rest where appropriate; separate key management.
- Avoid sharing raw logs in public chat/email; use permissioned links or sanitized excerpts.
- Workflows for personal data requests must account for replicas, indexes, exports, and backups; deletion/anonymization policies depend on legal obligations and system capabilities.

Do not prescribe a single "standard" retention day count for all systems: appropriate durations vary by event type, contracts, security requirements, and applicable regulations.

## 13. When Exposed Secrets or PII Are Discovered in Logs

This is a **data incident**, not merely a formatting bug. Response steps depend on severity and organizational processes:

1. **Identify data type, source, and scope**: service, timestamp, level, appender, index, backup, export. Do not propagate raw values in tickets or incident reports.
2. **Stop new occurrences**: fix the call site/schema, disable unnecessary debug logging, or block at an appropriate collection point; do not delete indiscriminately in a way that destroys forensic evidence.
3. If an **active credential** is involved, evaluate **immediate revocation/rotation** per security procedures. Masking old logs alone does not invalidate an exposed token.
4. **Restrict access** to affected logs and check access/export history if supported by the system.
5. **Remediate collected data** per policy and legal requirements: delete/redact indexes, exports, or copies where permitted; account for backups/retention and preservation obligations.
6. Assess notification/reporting obligations with privacy/security/legal teams as needed.
7. Add regression tests, review similar events, and track improvements.

Do not paste raw tokens, customer emails, or exposed data into investigation channels to "prove" the incident. Use identifiers, safe fingerprints, or appropriately redacted excerpts with restricted access.

## 14. A Review Workflow Applicable Within One Sprint

### Step 1 — Inventory

Collect events by module, business domain, and risk level. Pay attention to authentication, payment, profile, upload, request/response, integrations, exceptions, tracing, and third-party library logging.

### Step 2 — Classify Fields

For each event, specify purpose, owner, fields, origin, type, length limit, sensitivity, destination, and retention. Mark passwords, tokens, and other secrets as **strictly prohibited**.

### Step 3 — Design Allowlists and Normalize

Create templates/event schemas, preferring non-sensitive IDs and outcome enums. For user-linkable identifiers, use them only after an appropriate policy is in place. For untrusted text, apply validation, encoding, and size limits.

### Step 4 — Fix Sources, MDC, and Appenders

Remove DTO/header/raw-body dumps. Review throwables. Check all appenders, context providers, async paths, and interceptors. Do not fix just one pattern if another path still records the value.

### Step 5 — Test with Canaries

Generate harmless sample emails/tokens/URLs, run success and failure flows, and test injection and exceptions. Inspect the same event at the appender, stdout/file, collector, and export. Measure false negatives as well.

### Step 6 — Review Permissions and Lifecycle

Check access permissions and backups, retention periods, projects/tenants sharing the collector, and third-party sharing. Ensure unauthorized users cannot read the data.

### Step 7 — Integrate into CI and Operations

Add reviewer checklists, schema tests, controlled scanners, canary alerts, and incident handling guides. Re-verify whenever DTOs, dependencies, layouts, logging levels, or collectors change.

### Final Checklist Template

| Check | Acceptance Criteria |
| --- | --- |
| Is there a purpose for each event? | Clear owner, purpose, and consumers |
| Are prohibited fields present? | No passwords/tokens/session secrets/credentials |
| Is data minimized? | No unnecessary full body/headers/DTO dumps |
| Is there a schema/allowlist? | Keys and data types are approved |
| Is injection prevented? | Untrusted values are validated/escaped per format |
| Are MDC/exceptions checked? | No PII leaks through context or cause chains |
| Are all sinks checked? | File/stdout/agent/collector/export verified |
| Are automated tests present? | Unit + integration tests with canaries, including negative checks |
| Is access controlled? | Need-to-know, access auditing where required |
| Are retention/backups defined? | Duration, lifecycle, and copy handling are clear |
| Is there an incident playbook? | Procedures to revoke secrets, contain, and prevent recurrence |

## 15. Common Mistakes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| "Only DEBUG has PII so production is safe" | DEBUG can be enabled temporarily; INFO/ERROR still carry exceptions/DTOs | Review all levels and runtime overrides |
| Scanning only with an email regex | Tokens and other encodings slip through | Allowlist + canary tests + supplementary scanning |
| Logging whole objects with `@ToString.Exclude` | New fields or other serializers can still be logged | Create dedicated event DTOs with only allowed fields |
| Hashing emails and calling them anonymous | Digests can still be guessed and linked | Assess re-identification risk; use managed IDs/pseudonymization |
| Redacting at the collector is enough | Raw data already passed through queues/agents/files | Remove/minimize at the source |
| Checking only files and ignoring MDC | Layouts may output the entire context | Review MDC/ThreadContext and structured attributes |
| Using placeholders and assuming CRLF safety | Plain-text encoders can still preserve newlines | Structured escaping + validation |
| Logging every exception message | Causes may contain input and secrets | Inspect exception sources, design an error taxonomy |
| Copying raw logs into tickets/chat | Expands who can read them and how long they persist | Safe excerpts or access-controlled links |
| Reviewing only source code without checking the collector | Interceptors, agents, and sidecars can capture extra data | End-to-end integration tests and inventory |
| Dropping audit logs to "ensure privacy" | Loses mandatory security trails | Design minimal audit logs with proper permissions and retention |
| Using production data for testing | Creates new sensitive copies | Use fake canaries and synthetic test data |

## 16. Practice Exercises

1. Run `LogContentReviewDemo`. Explain why the email and token do not appear, and why the request ID containing a newline is replaced with `invalid`.
2. Add a `passwordHash` field to the input record. Keep `safeLine` unchanged and verify the output **does not change**; this demonstrates the benefit of an allowlist.
3. Write JUnit tests for `requestId` values: empty, too long, containing `\r\n`, quotes, arbitrary Unicode, and valid IDs; verify none break the structure.
4. Find five logging call sites in a demo application; classify the event, fields, and data sources, and decide whether to keep, remove, or mask each.
5. Use a test appender to capture Logback `ILoggingEvent`/Log4j events and inspect MDC, throwable, and message; test with a fake canary token.
6. Emit a structured JSON event with a real encoder. Send strings containing newlines and quotes, and verify the JSON parses cleanly without creating forged events.
7. Simulate a request with query `?code=canary` and inspect both HTTP server/proxy access logs and application logs. Reduce logs to route pattern and status.
8. Create a collector checklist: who can read, how long it is retained, and where copies exist in indexes/exports/backups; explain why checking only `application.log` is insufficient.

## 17. Key Takeaways

- **Log content review** means controlling **fields, purpose, sensitivity, delivery paths, readers, and retention** — not just searching source code for the word password.
- Prioritize **not logging** sensitive data or **allowlisting** event fields before relying on pipeline regex masking/redaction.
- Placeholders and structured logging do not automatically guarantee privacy; encoders, schemas, and input data must be controlled.
- Test with canary data and scenarios covering CR/LF, exceptions, MDC, multiple appenders, and async delivery.
- Review files, stdout, collectors, dashboards, exports, and backups. Handle exposed credentials through revocation/rotation and proper incident procedures.
- Keep security/audit logs at the necessary level while enforcing access controls, retention, and safeguards per policy.

### References

- OWASP — *Logging Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — *Log Injection*: https://owasp.org/www-community/attacks/Log_Injection
- OWASP — *Implement Security Logging and Monitoring*: https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/
- Oracle Java 17 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 — `java.util.logging.LogRecord`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html
