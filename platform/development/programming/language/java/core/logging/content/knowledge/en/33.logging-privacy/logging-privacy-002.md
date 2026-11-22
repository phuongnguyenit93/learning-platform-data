# Secrets in Logs: Protecting Sensitive Data in Java Logging

## 1. Objectives and Context

Logs help with debugging, observing operations, and investigating incidents, but they can also become a **channel for leaking secrets**. A call like `logger.debug("headers={}", headers)` can log an `Authorization` token; an exception can contain a URL with an API key; a JSON encoder can output an entire user object if a developer passes that object into a message. Once written, data can also pass through stdout, files, collectors, dashboards, storage repositories, backups, and alerting systems.

**Secrets in logs** is the problem of preventing values that should remain confidential from entering a logging event, regardless of log level or destination. The primary principle is **not generating or putting sensitive data into a log event in the first place**. Masking/redaction at the appender or collector is only an additional layer of defense, not a substitute for control at the source.

After this lesson, you will be able to:

- Identify passwords, access tokens, API keys, private keys, session cookies, connection strings, and personally identifiable information (PII) that may appear in logs.
- Understand leakage paths in Java: string concatenation, `toString()`, structured logging, exceptions, MDC, HTTP access logging, ORM SQL trace, and asynchronous appenders.
- Write logging using an **allowlist** of safe fields, using event codes and correlation IDs instead of printing secret payloads.
- Distinguish between **not logging**, **redacting**, **masking**, **tokenizing/pseudonymizing**, and **hashing**, along with the limitations of each approach.
- Test with intentional dummy data, verify both application logs and downstream sinks, and respond when a secret has accidentally been logged.

## 2. Types of Data That Should Not Be Logged Verbatim

Not every value that looks like a string carries the same risk. Use a classification based on the actual security requirements of the application.

| Category | Examples | Risk if Logged |
| --- | --- | --- |
| Credentials | Passwords, OTP codes, recovery codes, PINs | Can aid account takeover or authentication bypass |
| Tokens/Sessions | Bearer access tokens, refresh tokens, session IDs, auth cookies | Can be reused if still valid |
| Sensitive keys and certificates | API keys, client secrets, private keys, signing keys, JWT secrets | Can allow unauthorized access or forgery |
| System connections | JDBC URLs with credentials, DSNs containing passwords, service account details | Opens paths to databases or internal services |
| Personal data | Emails, phone numbers, addresses, ID numbers, health or financial data | Privacy risks and data protection policy compliance issues |
| Confidential application data | Unpublished transaction details, private request bodies, document contents | Leakage of business secrets or user information |
| Combinable identifying metadata | IP, user-agent, device ID, precise location, traces tied to an identity | Can correlate user activity across multiple sources |

**Passwords and authentication tokens almost never have a legitimate reason to appear verbatim in application logs.** For personal data, the level of handling depends on the processing purpose, internal policies, and applicable legal obligations; do not assume emails or IPs are "harmless" just because they are commonly used as search fields.

Examples of messages **that should not be created**:

```text
Login failed: username=alice@example.test password=demo-password
Request headers: Authorization=Bearer demo-token-123
Database URL: jdbc:vendor://db.internal/app?user=svc&password=demo-secret
```

All values above are **dummy data used to illustrate what to avoid**, not real values. Even if the token in the example has expired, it should still be excluded from logs by design.

Replace them with messages that have a clear observability purpose:

```text
event=login_denied requestId=req-74 result=DENIED reason=INVALID_CREDENTIALS
event=outbound_http_error service=payments route=/payments/{id} status=401
event=db_connection_failed pool=orders-db causeType=AUTHENTICATION_REJECTED
```

Note that `requestId` should be server-generated or validated for syntax/length; do not log an arbitrary client-controlled header verbatim as a correlation ID.

## 3. Leakage Path Model of a Log Event

```text
Request / message / database / external API
                   |
                   v
       Java objects, maps, exceptions
                   |
          +--------+--------+
          |                 |
  message formatting   MDC/structured fields
          |                 |
          +--------+--------+
                   |
                   v
             Logging API
                   |
          filter / appender / encoder
                   |
                   v
          async queue / buffer
                   |
                   v
        stdout / stderr / file / network
                   |
                   v
        collector / index / dashboard / backup
```

There are at least three boundaries that must be protected:

1. **Before creating the log event**: decide which fields are allowed to be emitted, do not serialize entire objects containing secrets; handle messages, exceptions, MDC, and headers.
2. **On the output path**: encoders/appenders/collectors apply additional data-masking policies and size limits; detect errors or leaked data.
3. **After storage**: log viewing permissions, group-based access control, encryption in transit/at rest, retention, querying, exporting, and access auditing.

If you only redact after writing to a file, **the raw file already contains the secret**. If you only redact in the collector, stdout/stderr or queues before the collector may still contain secrets. Therefore, **control at the source is the top priority**.

## 4. Ways Java Accidentally Puts Secrets Into Logs

### 4.1. String Concatenation, Parameterized Logging, and `toString()`

With SLF4J, all of the following statements are dangerous if the objects contain sensitive information:

```java
// Illustrative snippet in an application with logger, request, and credentials.
logger.debug("credentials=" + credentials);
logger.debug("credentials={}", credentials);
logger.info("request={}", request);
logger.trace("requestBody={}", request.getBody());
```

The `{}` placeholder defers **formatting** via SLF4J's mechanism, **it does not make the content inherently safe**. When the event is accepted, the backend may call `toString()` or the object's serializer, causing a leak if the object contains a password, token, or body. String concatenation can also cause `toString()` to run even when the log level is disabled.

Java records auto-generate a `toString()` that may list all components in its default representation. For example, `record Credentials(String username, String password) {}` should not be logged as a whole object. Lombok `@ToString` or IDE-generated `toString` methods carry similar risks if secret fields are not excluded. Even if an object has a masked `toString()`, **do not rely solely** on that masking as a substitute for safe field selection at the call site.

### 4.2. Headers, Cookies, Query Strings, and Request Bodies

Common leakage paths:

- `Authorization: Bearer ...`, `Proxy-Authorization`.
- `Cookie`, `Set-Cookie` carrying session identifiers or authentication information.
- URLs containing tokens in the query string such as `?access_token=...`, `?api_key=...`, or paths with authentication codes.
- HTTP request/response bodies, especially for login, password reset, payment, or integration APIs.
- Multipart payloads, webhook secrets, signed URLs, and callback URLs with sensitive query parameters.

For example, calling `request.getHeader("Authorization")` to make an authentication decision is a valid business operation, but writing the raw header to a logger is a different matter. If HTTP debugging is needed, log the **HTTP method, route template, status, duration, retry count, and a safe request ID**, rather than the full headers/body.

Do not use `request.getRequestURI()` with the full query string as the "route"; a route template like `/orders/{id}` generally reduces the risk of exposing identifiers or tokens in the URL. For outbound HTTP clients, enable wire logging/payload logging only after verifying the exact mechanism for stripping sensitive headers and bodies.

### 4.3. Exceptions and Error Messages

The call:

```java
// Illustrative snippet with SLF4J, where exception is an actual Throwable.
logger.error("Request failed", exception);
```

can log the **exception message, cause chain, and stack trace**. The stack trace itself usually contains only class/file/line information; however, the **message** of the exception or its suppressed/cause exceptions may contain URLs, headers, SQL, request fragments, or user data. For example, an HTTP library might include the full URI in an exception, or application code might construct `IllegalArgumentException("Invalid token: " + token)`.

You cannot say "stack traces are always safe," nor should you strip stack traces from all errors. A practical approach is:
- Do not construct exception messages containing secrets.
- Use standardized errors, error codes, and low-sensitivity metadata.
- When external libraries may produce messages containing secrets, consider handling diagnostics at an appropriate boundary; do not print raw exceptions to public loggers.
- Only log necessary details in controlled locations, in accordance with security procedures and access policies.

### 4.4. MDC, Trace Context, and Structured Fields

MDC is a common place to store per-thread metadata. If you use:

```java
// Integration snippet with SLF4J.
org.slf4j.MDC.put("authorization", authHeader);
org.slf4j.MDC.put("password", password);
```

then an encoder configured to output `%X` or JSON MDC fields can accidentally write both values into **every log event emitted on that thread**, including logs from third-party libraries.

Only put allowed fields into MDC, such as a safe `request_id`, `operation`, `service`, or trace/span ID per policy. Do not place Bearer tokens, Cookies, or raw PII into MDC. Clean up/restore MDC in a task's `finally` block so information does not leak across requests when a thread pool reuses threads.

Structured logging does not automatically protect data. `logger.atInfo().addKeyValue("payload", request).log("...")` can still cause the encoder to serialize the entire request. **Explicit field selection** is more important than switching from text logs to JSON.

## 5. Standalone Java 17 Example: Logging Only Allowed Data

This example uses `java.util.logging` (JUL) built into the JDK, requiring no Maven or external libraries. An object holds a simulated email, password, and bearer token. Instead of logging the whole object, the program logs only an **event code, a fixed request ID, and a status**. Finally, the program checks whether the captured output contains any of the three sensitive values.

Create `SecretSafeLoggingDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SecretSafeLoggingDemo {
    private record LoginInput(
            String email, String password, String authorization) {}

    private static final class CapturingHandler extends Handler {
        private final StringBuilder output;

        CapturingHandler(StringBuilder output) {
            this.output = output;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            output.append(record.getLevel().getName())
                    .append(" | ")
                    .append(record.getMessage())
                    .append('\n');
        }

        @Override
        public void flush() {
            // No I/O or buffer other than StringBuilder.
        }

        @Override
        public void close() {
            flush();
        }
    }

    public static void main(String[] args) {
        LoginInput input = new LoginInput(
                "alice@example.test",
                "demo-password",
                "Bearer demo-access-token");

        Logger logger = Logger.getLogger("lesson.privacy.secrets");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        StringBuilder captured = new StringBuilder();
        Handler handler = new CapturingHandler(captured);
        logger.addHandler(handler);

        try {
            // Only log approved, non-sensitive fields.
            logger.info("event=login_denied requestId=req-74 result=DENIED");
            logger.warning(
                    "event=auth_failed requestId=req-74 reason=INVALID_CREDENTIALS");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        String output = captured.toString();
        System.out.print(output);
        boolean secretFound =
                output.contains(input.email())
                || output.contains(input.password())
                || output.contains(input.authorization());
        System.out.println("secretFound=" + secretFound);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SecretSafeLoggingDemo.java
java SecretSafeLoggingDemo
```

**Exact stdout** in a fresh JVM, with no external components interfering with the demo logger:

```text
INFO | event=login_denied requestId=req-74 result=DENIED
WARNING | event=auth_failed requestId=req-74 reason=INVALID_CREDENTIALS
secretFound=false
```

Explanation:

1. `LoginInput` intentionally holds three values that must not be emitted; all three are **dummy data**, not real secrets. The program never calls `input.toString()`, never passes `input` to the logger, and never uses any credential value to build a message.
2. `CapturingHandler` records only the level and message of the two emitted records. `logger.setUseParentHandlers(false)` prevents events from propagating to the root handler, avoiding extra timestamped output or routing to destinations irrelevant to the demo.
3. The `secretFound` check runs on the captured text and evaluates to `false`. This is a **property check of this specific example**, not proof that a production application cannot leak data through other paths.
4. The messages use an **event code** and a program-controlled `requestId`, rather than using username/email or a token as a lookup key. The `reason` value is also a fixed error code instead of a message containing user-supplied data.
5. The handler is a single-threaded simulation component, not a full multi-threaded logging setup; using an unsynchronized `StringBuilder` here is intentionally restricted to a single thread.

### 5.1. Takeaways from the Example

An **allowlist when creating logs** is generally easier to audit than a blacklist filter: select only useful and permitted fields from the start. If an event never contained a password or access token, the appender does not need to "rescue" it with regex.

In a project with multiple loggers/backends, place tests at a controlled sink to verify not only the message, but also exceptions, MDC, key-value fields, encoders, and collectors. Checking only the message text **will not detect** secrets placed in another JSON field.

## 6. Safe Logging with SLF4J and Structured Logs

SLF4J is commonly used as a facade with Logback or Log4j 2 underneath. You can build clear messages such as:

```java
// Integration snippet: logger is an SLF4J logger; values are controlled.
logger.info("event=login_denied requestId={} reason={}",
        safeRequestId, "INVALID_CREDENTIALS");
```

This is **not a standalone program**; it assumes an existing logger and a normalized/application-generated request ID. Do not replace `safeRequestId` with an unvalidated arbitrary header. Do not insert `credentials`, `headers`, or `request` for debugging convenience.

With **SLF4J 2.x**, the fluent API can produce key-value pairs:

```java
// Integration snippet requiring SLF4J 2.x and a backend/encoder supporting structured fields.
logger.atInfo()
      .addKeyValue("event", "login_denied")
      .addKeyValue("request_id", safeRequestId)
      .addKeyValue("result", "DENIED")
      .log("Authentication rejected");
```

For a JSON encoder to output these fields, the backend must be configured accordingly. Even in key-value form, if you call `addKeyValue("authorization", header)`, the token can still be exposed. **Structured logging only changes the data representation**, it does not guarantee that fields are security-compliant.

### 6.1. Schema-Based Event Design and Allowlisting

A safe schema for authentication logs might specify:

| Field Name | Example | Notes |
| --- | --- | --- |
| `event` | `login_denied` | Fixed event name |
| `request_id` | `req-74` | Server-generated/validated, no free-form input |
| `result` | `DENIED` | Fixed result code |
| `reason` | `INVALID_CREDENTIALS` | Does not reveal whether the username exists |
| `latency_ms` | `23` | Non-sensitive metric |
| `service` | `identity-api` | Configuration value containing no secrets |

Do not include `password`, `access_token`, `refresh_token`, `cookie`, `authorization`, or the full `request_body` by default. Even `user_id` can be personal data; omit it if not needed. If an identifier is needed for diagnostics, evaluate pseudonymous IDs, retention, and access controls according to the actual purpose.

JSON encoders must properly escape strings. Constructing JSON manually via string concatenation with user-supplied data can produce malformed JSON or lead to **log injection**: newline/control characters making a log entry look like a separate record. Use a standard encoder, enforce length limits, and normalize any permitted client-controlled fields.

### 6.2. Using Markers and Error Codes Instead of Secrets

Sometimes you want to know whether a request "had an Authorization header or not." Log a boolean or a categorized state instead of the header itself:

```java
// Integration snippet; do not log the Authorization header value.
logger.debug("event=auth_header_check present={}",
        authorizationHeader != null);
```

Even `present=true/false` should only be logged if genuinely useful. For authentication errors, avoid overly detailed messages that could help an attacker distinguish whether an account exists. Both client-facing response policies and log storage policies require separate evaluation.

## 7. Redaction, Masking, and Hashing: Uses and Limitations

| Technique | Meaning | Limitations |
| --- | --- | --- |
| **Do not log** | Exclude fields at the call site/schema | Must control every code path that could log that data |
| **Redaction** | Replace the entire value with `[REDACTED]` or drop the field | If done late, raw data already existed in earlier layers |
| **Masking** | Show only a partial value (e.g., last 4 characters) | The remaining part may still be sensitive or enough to link identity |
| **Pseudonymization/tokenization** | Replace identifiers with managed tokens | Behavior can still be linked, and the mapping table must be protected |
| **Hashing** | Compute a hash digest for comparison | Hashing does not automatically anonymize data; low-entropy inputs can be guessed; unsuitable for logging passwords |
| **Encryption at rest/in transit** | Protect storage and transport | Anyone with decryption/log access can still view raw secrets |

**Redaction at the source** is a good policy for fixed fields. A filter in a Logback encoder/appender or Log4j 2 layout can serve as **defense in depth**, mitigating mistakes from a logger that does not follow the schema. However, typical regex patterns struggle to catch every variant: tokens nested in JSON, URL-encoded strings, Base64, varying header names, multiline data, or custom objects.

Do not treat string filtering on a few keywords (`password=`, `token=`) as proof that all logs are safe. APIs and frameworks can represent secrets in many forms or attach them to fields outside the message.

### 7.1. Risks of Hashing

For example, hashing an email with SHA-256 and logging that value can still allow a viewer to guess emails from a small candidate set and re-hash them for comparison. A hash can become a **stable identifier for linking users** across events. When correlation is needed without exposing identity, consider a keyed mechanism like HMAC with separate key management and a key rotation plan; HMAC output itself is still pseudonymous data requiring retention and access controls.

**Do not log database password hashes** just because they are not plaintext passwords. Password hashes are authentication credentials that must be protected.

### 7.2. Masking Is a Business Decision

Displaying `****1234` of an identifier may help a support desk confirm a transaction, but it may not be appropriate for every data type or policy. Do not blindly apply a "show last 4 characters" rule to JWTs, API keys, session IDs, or personal data. For such tokens, it is usually better **not to log them at all**.

## 8. Common Configuration Leakage Points

### 8.1. Logback, Log4j 2, and Pattern/JSON Encoders

With Logback, patterns like `%msg` output the message; `%ex`/`%throwable` can output exception details; `%X` or `%mdc` outputs MDC. JSON encoders can include key-value fields, arguments, exceptions, or custom attributes depending on configuration. Log4j 2 has corresponding patterns/layouts and context map/ThreadContext features.

Therefore, when reviewing an appender, ask:
- What messages, parameter objects, exceptions, or MDC fields does it receive?
- Which objects does the formatter/encoder call `toString()` or JSON serialization on?
- Is include-all MDC/headers/arguments enabled?
- Is the output forwarded to a secondary appender, fallback, or another collector?
- Does a masking rule cover the message, exception text, and structured fields alike?

Example of an unsafe JSON event:

```json
{
  "event": "login_denied",
  "request_id": "req-74",
  "authorization": "Bearer demo-token",
  "password": "demo-password"
}
```

Replace with:

```json
{
  "event": "login_denied",
  "request_id": "req-74",
  "result": "DENIED",
  "reason": "INVALID_CREDENTIALS"
}
```

These two JSON objects are **schema illustrations only**, not real observability data. The `authorization` or `password` fields should be dropped at event creation; it is not necessary to keep them as `[REDACTED]` if the schema does not require it.

### 8.2. HTTP Logging and Access Logs

Server access logs may log method, path, status, duration, user-agent, or IP by default. When customized to add headers, query strings, or request bodies, the risk increases sharply. Inspect debug/wire logging features of servlet frameworks, HTTP clients, reverse proxies, API gateways, and service meshes; secrets can be logged **outside the Java application**.

Prefer:
- Route templates or endpoint names instead of full URLs containing query strings.
- Status, duration, method, and a safe request ID.
- Not logging `Authorization`, `Cookie`, `Set-Cookie`, and request/response bodies on authentication or payment endpoints.
- Disabling or restricting wire logging; configuring an allowlist of required fields.
- Checking error paths, timeouts, and retries, as libraries may print raw requests on failure.

### 8.3. SQL and ORM Logging

Enabling SQL logging can be helpful for performance investigation, but adding **binding parameter values** can expose emails, tokens, ID numbers, or other sensitive data. Distinguish between:
- An SQL template with placeholders, e.g., `SELECT ... WHERE email = ?`.
- Actual bind values, e.g., the email passed to the query.

Do not log all bind values in production logs without special controls. For database exceptions, connection URLs or driver diagnostics may contain connection credentials; check where exceptions are handled. Do not embed credentials into URIs/connection strings that exceptions might display.

### 8.4. MDC/ThreadContext, Async, and Background Threads

With asynchronous logging, events may be queued in memory, serialized on another thread, or forwarded to a collector. "Redacting at the end of the pipeline" can leave raw data in queues, heap dumps, or diagnostic output. Therefore, avoid putting secrets into events from the start.

Thread pools reuse workers; if one request's MDC is not cleared, the next request may inherit stale metadata. Use `try/finally` or managed scope/context propagation mechanisms to restore state properly. Never store raw credentials in MDC expecting them to disappear automatically when the request ends.

## 9. Testing to Detect Secrets in Logs Before Release

You cannot prove "all logs are always safe" with a single regex. However, you can design a test suite capable of catching leaks early and preventing regressions.

### 9.1. Intentional Dummy Data (Canaries)

Create test credentials **with no real access**:
- Dummy passwords with an identifiable string.
- Dummy tokens with an easily recognizable prefix.
- Dummy emails using an example domain such as `example.test`.
- Dummy header/cookie values.
- Data containing quotes, slashes, newline characters, or Unicode characters to test escaping.

Then exercise these paths:
1. Successful and failed authentication.
2. 4xx/5xx errors, exceptions, and nested causes.
3. Timeouts, retries, cancellations, and shutdown.
4. Inbound/outbound HTTP and database errors.
5. Async logging, MDC/context, and fallback appenders.

Search for all canaries in logs captured **across multiple layers**. Check message text, structured fields, stack traces, raw files, console streams, collectors/indexes, and backups if authorized for testing. For offline testing, avoid downloading real sensitive raw logs onto personal laptops.

### 9.2. Assertion-Based Testing

Verify similarly to the Java 17 example:
- Expected safe events are present.
- No dummy password/token/email strings appear.
- No disallowed keys like `authorization` or `cookie` appear in the JSON schema.
- No log injection turns one event into multiple forged lines.
- When an appender uses redaction, test uppercase/lowercase variants, header formats, escaped values, and nested JSON.

Add tests for **unseen code paths**: search for logger calls directly passing request, response, credentials, user entity, headers, claims, or exceptions constructed from sensitive data. Static analysis and code review are important complementary layers; grepping keywords does not replace data-flow evaluation.

### 9.3. Negative Tests and False Confidence

If a test only searches for `password=`, it may miss `"pwd":"..."` or a `secretKey` JSON field. If tests only run with INFO logging, a DEBUG/TRACE path enabled during incident investigation could leak secrets. If you only check application files, proxy or collector access logs might still contain the data.

The test suite should include **changing log level configurations** in the test environment and testing the actual encoder. Do not enable DEBUG/TRACE across all of production or use real secrets just for testing.

## 10. Log Access, Storage, and Lifecycle

Preventing leaks at the call site is necessary but not sufficient; data can also persist in storage and transport:

- **Read permissions:** restrict which users/applications can access files, dashboards, log search, exports, snapshots, and backups based on the principle of least privilege.
- **Transport:** use secure and properly authenticated channels between agents, collectors, and backends.
- **Storage:** encrypt at rest if required by policy; do not treat encryption as a substitute for redaction because authorized users can still read the data.
- **Retention:** retain logs only for the required duration, minimize redundant copies, and enforce deletion according to policy and applicable legal obligations.
- **Environment separation:** do not copy raw production logs containing user data into test/demo environments or share them in public chats/tickets.
- **Alerts and quoted content:** dashboards, notifications, and incident tickets can also re-expose secrets if raw messages are embedded.

Understand that once logs are dispatched to multiple sinks, deleting a local file **does not delete** copies in backends, exports, or backups. Handling policies must cover the data lifecycle across the entire system.

## 11. When a Secret Is Found in Logs

A secret exposure incident must be treated as a security event, not merely a formatting bug:

1. **Stop further generation:** disable the offending log path, roll back debug configuration, or deploy a fix to remove the field at the source. Do not paste more secrets into tickets or diagnostic channels while fixing.
2. **Determine scope:** which secret type, since when, in which sinks/replicas/backups, who has access, and whether it may have been exported or sent in alerts.
3. **Revoke/rotate credentials:** for exposed access tokens, API keys, cookies/sessions, or passwords, perform revocation/rotation/reset per system policy. **Merely masking existing logs does not make an exposed credential safe.**
4. **Control stored data:** restrict access and execute deletion/retention/quarantine per security guidance and applicable governance obligations; pay attention to collectors and backups.
5. **Assess and notify:** coordinate with security/privacy teams, investigate signs of abuse, and fulfill notification obligations if applicable. Do not assume every case has the same legal requirements.
6. **Prevent recurrence:** add canary tests, schema allowlists, and review sites logging raw objects, HTTP headers, exceptions, and MDC; track coverage across backends.

**Do not re-post real tokens when asking for help.** Use field names, timestamps, log locations, and dummy values or permitted fingerprints. For secrets that are still valid, the critical action is revoking/rotating per procedure, not just replacing strings in messages.

## 12. Common Mistakes and Fixes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Logging raw `request`, `headers`, or `credentials` | `toString`/serializer may print tokens/passwords/cookies | Select safe fields using an allowlist |
| Assuming disabled `logger.debug` prevents value creation | String concatenation, `toJson`, or accessors may still run at the call site | Avoid putting secrets in logs; use guards/lazy evaluation for cost reduction, not as a security control |
| Using `{}` and assuming tokens are masked | Parameterized logging formats values; it does not strip secrets | Do not pass tokens/passwords as arguments |
| Logging raw exceptions | Message/cause may contain URIs, SQL, headers, or input | Control where exceptions are created and how errors are logged |
| Putting Authorization headers into MDC | Encoders output MDC on every log on that thread | Only use permitted metadata; clean up via scope |
| Keeping INFO off but enabling TRACE during incidents | Trace paths may expose previously hidden data | Test all log levels that can be enabled |
| Relying solely on regex at the collector | Raw logs already passed through streams/queues/files; regex easily misses cases | Remove secrets at the source; use sink redaction as an extra layer |
| Hashing emails/tokens and assuming anonymity | Easy to correlate or guess low-entropy inputs | Minimize identifiers; use policy-governed pseudonymization if needed |
| Logging entire request bodies for debugging | May contain credentials, personal documents, or payments | Log only route/status/duration and safe fields |
| Enabling SQL bind logging broadly | Query values may contain private data | Log SQL templates/metrics; control parameter logging |
| Checking only a single log file | Console/collector/backup copies may still leak | Test and govern the entire pipeline |
| Thinking deleting logs removes token risk | Secrets may have been copied/exported earlier | Revoke/rotate and investigate access |

## 13. Knowledge Check Exercises

**Question 1.** Is the following line safe?

```java
logger.info("Login failed: {}", credentials);
```

**It cannot be considered safe.** `credentials` may be rendered by `toString()` or a serializer containing a password. Replace it with an event code, a safe request ID, and a fixed reason code. The statement above is an **integration snippet**, not a standalone Java class.

**Question 2.** An application masks `Authorization` on console logs, but still has a raw JSON appender. Can we conclude the token is not leaked?

**No.** Each appender/encoder can output different fields. If the raw event contains the token, the JSON appender can still write it. Strip the field at the source and test all sinks.

**Question 3.** Does hashing an email with SHA-256 and logging the hash turn the email into anonymous data?

**Not necessarily.** Emails can often be guessed from candidate lists and correlated across logs; hashing is not an absolute anonymization mechanism. Evaluate the need, linkability, access controls, retention, and keyed approaches if appropriate.

**Question 4.** An HTTP error includes a URL with a query token. If you log `logger.error("failed", exception)`, can the token appear?

**Yes, it can.** The exception message/cause formatted by the backend may contain the URL. Handle errors with safe codes/metadata and avoid constructing exception messages that contain secrets.

**Question 5.** When a real token has appeared in logs and been seen by someone who should not have access, is fixing the code and deleting one line enough?

**No.** The token may still be valid or may have been copied. Revoke/rotate it per policy, control storage locations, investigate scope, and add tests.

## 14. Production Readiness Checklist for Logging

1. Loggers receive only fields **genuinely needed for diagnostics/operations**; credentials, tokens, and private keys never enter messages, args, or structured fields.
2. Raw headers, URL queries, request/response bodies, or SQL bind values containing sensitive data are not logged.
3. Exceptions and error messages do not accidentally contain tokens, URLs with secrets, account data, or payloads.
4. `toString()` on records/entities, JSON serializers, Lombok-generated methods, and raw object logging have been reviewed.
5. MDC/ThreadContext contains only permitted metadata; tasks clean up in `finally`; no cross-thread leakage.
6. Logback/Log4j 2/JUL appenders/encoders and downstream collectors have been checked, including fallbacks, error logs, and JSON fields.
7. If additional redaction/masking is used, it has been tested across varied formats and its limitations are understood.
8. Tested with dummy canaries at INFO/DEBUG/TRACE, exception paths, HTTP paths, and async/collector under realistic configuration.
9. Log access permissions, transport security, retention, exports, and backups meet security/privacy policies.
10. An incident response procedure exists for secrets in logs, including containment, revocation/rotation, and recurrence prevention.

**Conclusion:** Protecting secrets in Java logging starts **before calling the logger**: create events containing only permitted data, and avoid logging raw objects, headers, tokens, passwords, sensitive exception messages, and uncontrolled MDC. Redaction at encoders/collectors, access control, retention, and canary testing are complementary layers of defense. A useful log should help explain an incident without **becoming a copy of secrets or personal data**.