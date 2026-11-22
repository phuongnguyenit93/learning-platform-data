# Logging Secrets in Java: Anti-Patterns, Prevention, and Testing

## 1. Objectives

**Logging secrets** is a security anti-pattern in which an application inadvertently writes **passwords, access tokens, refresh tokens, session cookies, API keys, private keys, signing keys, connection strings containing passwords, or other sensitive values** into the logging pipeline. This data can be replicated across console/file outputs, container runtimes, log collectors, dashboards, backups, file exports, and support tickets.

This issue belongs to the **Anti-pattern logging** group of Java Core Logging. It is not merely a matter of DEBUG level or log formatting. Someone authorized to read regular logs may not be authorized to read secrets from a vault; if a secret leaks into logs, this authorization boundary is broken.

This lesson targets the following capabilities:

1. Identify direct and indirect leak paths from **SLF4J, Logback, Log4j2, JUL, exceptions, DTO.toString(), Java records, HTTP filters, MDC, and startup configuration**.
2. Distinguish between **secrets, PII, and metadata** to know which data must be excluded and which can be logged for investigation.
3. Design safe logging based on **allowlisted fields**, event names, safe error codes, correlation IDs, and output encoding.
4. Understand why **disabling DEBUG, encrypting logs, or masking data in dashboards** does not eliminate all risks.
5. Run a **standalone Java 17** example using JUL, proving that dummy secret values do not appear in captured logs.
6. Write automated tests and an incident response procedure when real secrets have already been logged.

## 2. Why Are Logs Containing Secrets Dangerous?

An application may retrieve tokens from an authentication system or secrets manager with narrow permissions. However, a centralized logging system typically has a much broader audience: developers, support, SREs, security analysts, CI/CD, collector service accounts, and incident responders.

An event like the following is an anti-pattern:

~~~text
DEBUG outbound request Authorization: Bearer <ACCESS_TOKEN>
INFO  db connected with url=jdbc:postgresql://db.local/shop?user=svc&password=<PASSWORD>
~~~

The bracketed strings are dummy placeholders illustrating where sensitive data sits; they are **not real credentials**.

Consequences may include:

- Log readers using tokens to call APIs or hijack sessions while the token remains valid.
- Partner API keys being exposed and potentially misused.
- Connection strings enabling database access if the credentials are still valid.
- Private keys being used to sign data or decrypt payloads depending on the key's purpose.
- Logs being indexed/backed up for many days, even after the application code has been fixed.
- Users downloading CSVs, attaching logs to tickets, or sending them via chat, creating additional copies outside the vault's access controls.

MITRE classifies inserting sensitive information into logs as **CWE-532**. OWASP recommends not logging passwords, session identifiers, access tokens, encryption keys, connection strings, and many other types of sensitive data directly.

## 3. Classification: How Do Secrets Differ from Personal Data?

| Category | Examples | Recommended Handling |
| --- | --- | --- |
| **Credential** | Password, access token, refresh token, API key, session cookie | Do not log raw values. |
| **Cryptographic secret** | Private key, HMAC key, signing key, encryption key | Do not log values; treat even backups/exports as sensitive assets. |
| **Configuration credential** | JDBC URL with password, DSN, cloud service account JSON | Log only the dependency name and standardized error code. |
| **One-time secret** | OTP, password reset token, magic login link | Do not log; a short lifespan does not eliminate the risk. |
| **PII** | Email, phone number, user ID, address, health information | Minimize, mask/pseudonymize per policy, enforce read permissions. |
| **Business confidential** | Business metrics, contracts, transactions | Classify data and logging purpose before emitting events. |
| **Safe diagnostic** | Event name, status, route template, error code, duration | Usually more useful than raw payloads; still validate input and limit scope. |

Do not assume every user ID is an authentication secret, yet many identifiers can still be **personal data**. Hashing does not automatically render a value harmless either: hashes can be brute-forced if the original value has low entropy or used to correlate activities across multiple occurrences.

A good practice is to **log the event of using a secret** rather than the **secret value itself**:

~~~text
INFO event=secret.accessed workload=orders-service secret_ref=db-primary result=ALLOW
INFO event=secret.rotated secret_ref=payment-provider-key result=SUCCESS
WARN event=secret.access.denied workload=unknown-service reason=POLICY_DENIED
~~~

These are sample events. **secret_ref** is a logical name permitted to be exposed within the log scope, not the key itself. Even secret names or vault paths sometimes need to be controlled according to internal policy.

## 4. Anti-Pattern: Logging Passwords/Tokens Directly

Unsafe Java pattern:

~~~java
// WRONG: illustrative snippet in an application with SLF4J.
log.info("Login username={} password={}", username, password);
log.debug("Outbound Authorization={}", bearerToken);
log.error("Payment API key={}", paymentApiKey);
~~~

**SLF4J placeholders do not automatically mask secrets.** They only format the message and typically avoid some string concatenation work when the level is disabled. When an event is logged, the passed values can still be written to the console, files, or structured encoders.

Alternative pattern:

~~~java
// Illustrative; requestId has been validated at the boundary.
log.info("event=auth.attempt request_id={}", requestId);
log.warn("event=auth.result request_id={} result={} reason={}",
        requestId, "DENIED", "BAD_CREDENTIALS");
~~~

What you need to know is that **an authentication attempt was denied**, not what password or token the user submitted. If you want to analyze the authentication mechanism, log **auth_method=PASSWORD/OAUTH2** using a safe enum.

**Do not log the first/last four characters of an API key by default.** Prefixes/suffixes can reveal the provider, tenant, or assist attacks against structured values. If you genuinely need to identify a key, use an **opaque secret ID** issued by the management system or a separately designed, approved, and protected fingerprint. Do not hash passwords with SHA-256 yourself and log the hash assuming it is no longer sensitive.

## 5. Anti-Pattern: Logging All HTTP Headers

Headers that commonly contain secrets:

- **Authorization** and **Proxy-Authorization**.
- **Cookie**, **Set-Cookie**, session identifiers.
- **X-API-Key** and custom credential headers.
- Headers containing signatures, bearer tokens, one-time codes, or partner secrets.

Unsafe example:

~~~java
// WRONG: illustrative example in a Servlet Filter.
request.getHeaderNames().asIterator().forEachRemaining(name ->
        log.debug("header {}={}", name, request.getHeader(name)));
~~~

If DEBUG is enabled, the snippet above can log raw cookies/tokens. A denylist that only masks the **Authorization** header name is insufficient: a partner might place credentials in a custom header.

**Prefer an allowlist** of fields that genuinely serve operations:

~~~text
event=http.request.received
method=POST
route=/orders
request_id=req-204
content_type=application/json
~~~

Even requestId and seemingly safe fields still require validation and size limits. Do not log raw bodies, entire header maps, or uncontrolled client-supplied values.

### 5.1. Body and Response

Request bodies may contain passwords, OTPs, client_secret, refresh tokens, or personal data. Responses may also contain newly issued tokens after login or password reset links. A filter that automatically logs full requests and responses at DEBUG is a major risk.

**Truncating the body is not equivalent to redaction.** If a secret lies within the first 100 bytes, printing only the first 100 bytes still leaks it. Choose useful metadata such as method, route template, status, payload size, and safe validation error codes instead of the body.

## 6. Anti-Pattern: Logging Raw URLs/Query Strings

Examples of URLs requiring caution:

~~~text
GET /password-reset?token=<ONE_TIME_SECRET>
GET /callback?code=<AUTH_CODE>
GET /download?signature=<SIGNED_VALUE>
~~~

Some libraries or error handlers automatically include the full URL in exception messages. Reverse proxy/gateway access logs may also record query strings even if the Java application does not log them directly.

**Better approach:** use a route template:

~~~text
method=GET route=/password-reset status=400
method=GET route=/download status=200
~~~

Do not treat URL encoding, base64, or JWT encoding as protective encryption. They do not strip credentials of their usability.

For database connections, do not log the full JDBC URL or **DataSource.toString()** unless you know for certain no credentials are inside:

~~~text
WARN event=db.connection.failed datasource=orders-primary error_type=SQLTransientConnectionException
~~~

This is an illustrative event: datasource is a logical name, and error_type is an approved error class, not a raw connection string.

## 7. Anti-Pattern: Logging Entire DTOs, Maps, or Java Records

An error-prone example:

~~~java
// Illustrative sensitive record type.
record LoginRequest(
        String username,
        String password,
        String accessToken) {
}

// WRONG if LoginRequest contains credentials:
log.debug("request={}", loginRequest);
~~~

A Java record has an **auto-generated toString()** that describes its components. When a logger formats the object, password/accessToken can end up in the message. POJOs with Lombok **@Data/@ToString**, collections, Maps, and nested objects carry similar risks.

Avoid:

~~~java
// WRONG: requests often contain nested sensitive data.
log.info("incomingRequest={}", requestDto);
log.debug("context={}", requestAttributes);
~~~

Replace with an event containing allowlisted fields:

~~~java
// Illustrative: operationId has been validated.
log.info("event=login.request.received operation_id={}", operationId);
~~~

**Annotations used to hide fields during Jackson JSON serialization do not guarantee that Java toString or another logging backend will hide those fields.** If you configure a safe toString for a DTO, treat it as an additional safeguard rather than a reason to log the entire DTO.

Nested maps/objects are very difficult to audit as schemas evolve. Allowlisting the fields permitted to be logged is generally safer than "log everything and use a denylist to remove a few names."

## 8. Anti-Pattern: Exception Messages and Stack Traces

Many Throwables from HTTP/database libraries have messages containing URLs, response bodies, request parameters, or credentials. A seemingly correct snippet:

~~~java
// RISKY if the Throwable contains a secret in its message or cause chain.
catch (RuntimeException ex) {
    log.error("Remote dependency failed", ex);
    throw ex;
}
~~~

When the backend logs a Throwable, the message and cause chain can appear in the stack trace. If sensitive data is present there, it can be exposed. Moreover, logging and rethrowing across multiple layers causes **duplicate stack traces**, increasing the blast radius.

Not all stack traces are dangerous or need to be disabled. The goals are:

1. Do not put secrets into exceptions **where the exception is created**.
2. Avoid passing raw URLs/headers/bodies into exception messages.
3. Use safe **error codes, dependency names, error types, and trace IDs** for debugging.
4. Log Throwables only to destinations with controlled data and access permissions.
5. Use redaction at the encoder/collector as an additional layer.
6. Choose **a single boundary that owns terminal error logging**, avoiding repeated log-and-rethrow.

If the error cause contains a raw token whose safety cannot be guaranteed, you can log:

~~~text
ERROR event=payment.dependency.failed dependency=payment-gateway error_type=SocketTimeoutException request_id=req-17
~~~

instead of the verbatim Throwable message. In production systems, to preserve diagnostic information, fix the source that creates the exception or design safe exceptions/wrappers; do not strip stack traces from all errors merely out of fear of leaks.

## 9. Anti-Pattern: MDC and Structured Logging Carrying Secrets

SLF4J MDC and Log4j2 ThreadContext can be injected into every log event via a pattern or JSON layout.

~~~java
// WRONG: illustrative example in an application using SLF4J.
MDC.put("accessToken", accessToken);
~~~

From this point on, a simple log like "Service started" can contain accessToken if the layout outputs MDC. Do not put passwords, bearer tokens, cookies, or raw request bodies into MDC.

Only put safe, controlled context into MDC:

~~~java
// Illustrative: requires SLF4J, service, and a valid requestId.
try {
    MDC.put("requestId", requestId);
    service.process();
} finally {
    MDC.remove("requestId");
}
~~~

In asynchronous processing, MDC might not propagate across ExecutorService/CompletableFuture/Reactor or might linger on reused threads. You must test context propagation and cleanup using the appropriate framework mechanisms.

**Structured logging can also contain secrets.** A JSON field named token whose value is a raw token is still a vulnerability, even if JSON escaping is flawless.

## 10. Anti-Pattern: Dumping Config or Environment

When startup fails, developers sometimes print the entire configuration:

~~~java
// WRONG when the environment contains secrets.
System.out.println(System.getenv());
System.out.println(System.getProperties());
~~~

Environment variables, Java system properties, startup arguments, and dependency configurations may contain API keys, database passwords, signing keys, or auth tokens. CI logs, deploy logs, crash diagnostics, and service startup logs can all become leak vectors.

A better example:

~~~text
INFO event=service.started profile=prod config_version=v42
WARN event=config.invalid component=datasource reason=MISSING_REQUIRED_PROPERTY
~~~

Log the **component and error type**, not the raw value of a secret. Even a property key or secret path should be classified according to the environment.

### 10.1. Library Debug/Trace Logging

Enabling DEBUG/TRACE for Spring Security, HTTP clients, SQL/JDBC drivers, ORMs, OAuth SDKs, or RPC libraries can emit headers, URLs, payloads, or queries with parameters. Do not assume every library is safe when verbose logging is turned on.

Check indirect paths as well:

- Request/response logging filters.
- HTTP wire logging.
- SQL parameter binding logs.
- OAuth token exchange diagnostics.
- Message broker body logs.
- Framework validation/binding errors.
- Third-party SDK exception handlers.

Disabling DEBUG in production is an **exposure-reduction layer**, not a substitute for protecting data at the source.

## 11. Designing Safe Log Events

Instead of passing raw objects/requests to the logger, construct events from an **allowlist**:

~~~text
Request with username/password/token
            |
            v
        Business logic
            |
            v
Safe event:
    event=auth.login.result
    request_id=req-17
    auth_method=PASSWORD
    outcome=DENIED
    reason_code=BAD_CREDENTIALS
            |
            v
Structured encoder + escaping
            |
            v
Appender / collector
            |
            v
Storage with RBAC, retention, audit
~~~

Good fields to consider:

| Field | Benefit | Condition |
| --- | --- | --- |
| **event** | Easy to query and alert on. | Fixed name, not derived from arbitrary input. |
| **request_id / trace_id** | Correlates events. | Validated; do not use a secret as an ID. |
| **outcome** | SUCCESS, DENIED, ERROR. | Based on actual outcome, not guessed in advance. |
| **error_code** | Stable error classification. | Do not use raw exception messages. |
| **dependency** | Pinpoints error source. | Logical name approved for sharing. |
| **duration_ms** | Latency analysis. | Measure duration with a monotonic clock when appropriate. |
| **http.route / status** | HTTP analysis. | Use route template and actual status at the boundary. |

If you need to correlate a key, use a **vault-issued secret ID** or a designed and approved identification mechanism; do not log key prefixes or arbitrary hashes.

### 11.1. Allowlists Are Better Than Denylists Alone

A denylist may remove fields named password/token but miss newer names like client_secret, x-api-key, auth_assertion, credential, signedUrl, or refreshToken. Regex redaction can miss encoded secrets or secrets embedded in unstructured messages.

An allowlist controls which fields are permitted to enter the logs. You can add **redaction at the encoder/collector** to reduce risk from external code paths, but you cannot rely on a regex alone for guarantees.

### 11.2. Encoding and Preventing Log Injection

Untrusted data can contain CR/LF, delimiters, or control characters, causing **log forging** in text layouts. Use a structured JSON encoder and validate IDs; do not concatenate JSON strings manually.

Protecting secrets and preventing log injection are two distinct concerns, both of which must be verified along the path from Java to the backend.

## 12. Standalone Java 17: Verifying That Secrets Do Not Appear in Logs

The example below uses **java.util.logging (JUL)** built into JDK 17. The program creates a LoginAttempt containing a dummy password/token but **does not log the object, exception message, or credential values**. It uses a **CaptureHandler** to store LogRecords, checks security conditions, and only then prints the safe events to stdout.

There is no network, file I/O, or external dependency; this is a **logging simulation**, not a real authentication system.

### 12.1. SafeSecretLoggingDemo.java

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SafeSecretLoggingDemo {

    private static final Logger LOG =
            Logger.getLogger("demo.security.AuthService");

    record LoginAttempt(
            String requestId,
            String username,
            String password,
            String accessToken) {
    }

    static final class CaptureHandler extends Handler {
        private final List<String> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override
        public void flush() {
            // No I/O needed in the demo.
        }

        @Override
        public void close() {
            // No external resources.
        }

        List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    static String safeRequestId(String raw) {
        if (raw != null && raw.matches("[A-Za-z0-9_-]{1,36}")) {
            return raw;
        }
        return "invalid";
    }

    static void authenticationResult(
            LoginAttempt attempt, boolean authenticated) {
        String requestId = safeRequestId(attempt.requestId());
        LOG.info("event=auth.attempt request_id=" + requestId);
        LOG.info("event=auth.result request_id=" + requestId
                + " outcome="
                + (authenticated ? "SUCCESS" : "DENIED"));
    }

    static void dependencyFailed(
            LoginAttempt attempt, RuntimeException error) {
        // Do not log exception message because it may contain a token.
        LOG.warning("event=auth.dependency_failed request_id="
                + safeRequestId(attempt.requestId())
                + " error_type="
                + error.getClass().getSimpleName());
    }

    public static void main(String[] args) {
        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.ALL);

        Level oldLevel = LOG.getLevel();
        boolean oldParent = LOG.getUseParentHandlers();

        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(capture);

        try {
            LoginAttempt attempt = new LoginAttempt(
                    "req-17",
                    "test-user@example.invalid",
                    "DUMMY_PASSWORD_DO_NOT_LOG",
                    "DUMMY_TOKEN_DO_NOT_LOG");

            authenticationResult(attempt, false);
            dependencyFailed(attempt,
                    new IllegalStateException(
                            "Bearer DUMMY_TOKEN_DO_NOT_LOG"));

            List<String> events = capture.snapshot();
            String rendered = String.join("\n", events);

            for (String forbidden : List.of(
                    attempt.username(),
                    attempt.password(),
                    attempt.accessToken(),
                    "Bearer")) {
                if (rendered.contains(forbidden)) {
                    throw new AssertionError(
                            "Sensitive value appeared in logs");
                }
            }

            if (events.size() != 3) {
                throw new AssertionError(
                        "Unexpected number of log events");
            }

            for (String event : events) {
                System.out.println(event);
            }
            System.out.println(
                    "PASS: no sensitive values in captured events");
        } finally {
            LOG.removeHandler(capture);
            capture.close();
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
        }
    }
}
~~~

### 12.2. Compiling and Running

~~~bash
javac SafeSecretLoggingDemo.java
java SafeSecretLoggingDemo
~~~

**Expected stdout:**

~~~text
INFO event=auth.attempt request_id=req-17
INFO event=auth.result request_id=req-17 outcome=DENIED
WARNING event=auth.dependency_failed request_id=req-17 error_type=IllegalStateException
PASS: no sensitive values in captured events
~~~

### 12.3. Explanation

- LoginAttempt holds a dummy password/accessToken, but the logger only uses the **validated requestId**.
- A Java record has a default toString containing component names and values; do not call log.info on the entire object.
- The test exception has a dummy token in its message. The dependencyFailed method logs only the **exception class**, not the raw message or Throwable.
- CaptureHandler records events that actually reach the JUL Handler and uses level/name/message. The program compares the output against dummy strings and does not print raw secrets when an assertion fails.
- **setUseParentHandlers(false)** prevents events from the demo logger from propagating to the root ConsoleHandler.
- The code runs sequentially on a single thread with no timestamps or randomness in the output, so the result is deterministic.
- **finally** removes the Handler and restores the logger level/parent settings so other code is not affected.

### 12.4. Limitations

The example only tests **JUL CaptureHandler in RAM**. It does not verify logs after passing through a JSON encoder, async queue, file, Logback/Log4j2, or collector; nor does it perform real authentication. Another backend might store additional arguments, MDC, Throwables, or structured attributes that do not appear in the getMessage string.

In production, logging only the exception type may not be enough for debugging. Prioritize **removing secrets at the exception source**, or creating a controlled safe error type/cause, and then logging diagnostics at the appropriate boundary. Do not blindly strip all stack traces.

**Do not use real credentials in tests.** Sentinel values are used solely to ensure log paths do not leak data under known schemas and sinks.

## 13. Testing Against Secret Leaks in Real Projects

A good test suite should check multiple sources:

| Source | Dummy Value | Expectation |
| --- | --- | --- |
| Login DTO | DUMMY_PASSWORD_DO_NOT_LOG | Does not appear in output. |
| Authorization header | DUMMY_TOKEN_DO_NOT_LOG | Does not appear at INFO/DEBUG/TRACE. |
| Custom API-key header | DUMMY_API_KEY_DO_NOT_LOG | Not written via header dumps. |
| Session cookie | DUMMY_COOKIE_DO_NOT_LOG | Does not appear in request/response logs. |
| URL query | DUMMY_RESET_TOKEN_DO_NOT_LOG | Only route template present, no raw URL. |
| Java record.toString() | DUMMY_RECORD_SECRET_DO_NOT_LOG | Entire record is not logged. |
| Exception message | DUMMY_EXCEPTION_SECRET_DO_NOT_LOG | Does not appear in rendered Throwable. |
| MDC/ThreadContext | DUMMY_MDC_SECRET_DO_NOT_LOG | Absent from structured fields. |
| JDBC datasource | DUMMY_DB_PASSWORD_DO_NOT_LOG | Absent from startup/error logs. |
| Library debug | DUMMY_REMOTE_TOKEN_DO_NOT_LOG | Not leaked when verbose test config is enabled. |

Enable DEBUG/TRACE **in an isolated test environment** to test paths that operators might turn on during an incident. A test running only at root INFO can mask dangerous debug statements.

### 13.1. Positive Control Checks

If logging is completely disabled, a "secret does not appear" test can PASS meaninglessly. You must assert that at least one **safe event** was logged, such as auth.result=DENIED. The demo in section 12 checks **events.size() == 3** for that reason.

### 13.2. Inspecting Multiple Parts of an Event

With SLF4J + Logback, an event can store:

- Formatted message.
- Argument array.
- MDC properties.
- ThrowableProxy.
- Markers/key-value pairs.
- Fields from a JSON encoder.

Therefore, testing only **getFormattedMessage()** may not be enough. You should inspect the **actual post-encoder representation** and relevant sinks. For **Log4j2**, test ThreadContext and the corresponding message/Throwable/layout.

### 13.3. Be Careful with Test Failure Messages

Do not include raw credentials in assertion expected/actual messages or CI reports. If a test detects a sentinel, the test failure log should report the **type of leaked data and event location** without repeating the actual value.

### 13.4. Static Analysis and Code Review

Check for dangerous patterns:

~~~text
log.info("password={}", password)
log.debug("headers={}", requestHeaders)
log.info("dto={}", dto)
log.error("request failed: " + exception.getMessage())
MDC.put("accessToken", value)
System.out.println(System.getenv())
~~~

Simple regexes or rules can have false positives/false negatives, especially when data flows through helper methods. Combine **data-flow code review, CI scanning, safe logging APIs, and integration tests**. Do not claim "the scan found no keys" as proof that the system is free of CWE-532.

## 14. Technology-Specific Notes

### 14.1. SLF4J

- The **{}** placeholder does not mask automatically.
- SLF4J 2.x's fluent key-value API can also carry secrets; it only differs in how the event is constructed.
- Logger levels do not guarantee security: DEBUG can be enabled via runtime config.
- If an unexpected provider is used, output differs from expectations; test against the real provider.

### 14.2. Logback

- PatternLayout can print the entire MDC via **%X**.
- A JSON encoder can serialize fields/arguments that do not appear in the formatted message.
- A masking encoder/filter on one appender does not mean all other appenders are protected.
- AsyncAppender can hold data in a queue before the collector reads it.
- Test actual file/console/centralized layouts.

### 14.3. Log4j2

- ThreadContext can also store secrets.
- Message templates, custom layouts, and structured logging do not automatically classify sensitive fields.
- Rewrite/filter/regex replacement can serve as an extra layer, but has limitations.
- If there are multiple AppenderRefs, ensure raw messages do not bypass redaction.

### 14.4. JUL

- **Logger.log(Level, String, Throwable)** passes the Throwable to the Handler/Formatter. If the message/cause contains a secret, the formatter may output it.
- ConsoleHandler typically writes to stderr, so tests that only intercept stdout can miss it.
- FileHandler supports rotation, but data already written to a file/collector does not vanish just because the application closes the Handler.

### 14.5. Spring Boot

- Check request/response logging filters, Spring Security debug, WebClient/HTTP client wire logging, and JDBC/ORM debug.
- Do not print request bodies, object.toString, environment, or configurations with credentials inside @Service.
- Protect logging management endpoints if enabled (such as Actuator loggers); changing levels can expand what is output.
- Check dev/test/staging/prod profiles and overrides from env/command line.
- Do not treat the framework's masking of certain properties on management endpoints as proof that all logging paths are safe.

## 15. The Log Pipeline and Where Secrets Can Be Replicated

~~~text
Java application
       |
       +-- stdout/stderr or file
       |
       +-- container runtime logs
       |
       +-- log shipper/collector buffers
       |
       +-- centralized log index
       |
       +-- dashboard / saved query
       |
       +-- CSV export / backup / archive
       |
       +-- ticket / chat / local download
~~~

If a secret is logged at the source layer, a collector that redacts data before export **does not automatically erase raw copies in files/stdout**. Masking data in a viewer does not prove that raw APIs/exports are masked. Encryption at rest and TLS protect disk and network, but anyone authorized to query plaintext can still read and copy it.

You should manage:

- **VIEW/QUERY/EXPORT/SHARE** as separate permissions.
- Tenant/environment isolation and least privilege.
- Appropriate retention and backup handling.
- Auditing access/exports of sensitive data.
- Using debug exporters only in secure environments.
- Never sending raw secrets through support tickets or chat.

## 16. When a Secret Has Leaked into Logs: Response Procedure

Do not just fix the code and consider the incident closed. The secret may have already been read and replicated.

### Step 1 — Contain

Identify the credential type, application, version, environment, timestamp, which sinks received the logs, and related access permissions. Record the incident ID and metadata; **do not copy the raw secret into tickets or team announcements**.

### Step 2 — Reduce Current Risk

Evaluate **revoking/rotating** the token, API key, session, or private key per incident policy. For session cookies, sessions may need to be invalidated; for API keys, a new key may need to be issued and workloads updated securely; for private keys, downstream trust/signatures must be evaluated.

Do not assume an expired credential means no one used it during the prior validity window.

### Step 3 — Stop New Emissions

Fix logging at the source, control debug flags/SDKs, add allowlists, and remove raw DTOs and exception messages containing secrets. Test with sentinels on the corresponding code paths.

### Step 4 — Control Copies

Check local files, container logs, collectors, indexes, backups, archives, CSV exports, and ticket/chat attachments. Restrict read access where needed and perform redaction/purging following approved procedures; keep **legal hold, audit integrity, and retention** in mind.

**Do not indiscriminately delete audit trails or evidence** that would impair investigation. Copies that cannot be deleted immediately must be documented with risk-mitigation measures.

### Step 5 — Assess Usage and Prevent Recurrence

Cross-reference log access audits with credential usage audits during the relevant timeframe. Identify affected users/tenants and apply notification/compliance procedures if necessary. Add regression tests and review logging policies in similar libraries.

## 17. Common Mistakes

1. **SLF4J placeholders automatically mask tokens** — false; if the argument is a token, it can still be printed.
2. **Only DEBUG contains secrets** — false; INFO/WARN/ERROR can also leak.
3. **Disabling DEBUG in production is enough** — false; levels can be enabled during incident debugging.
4. **Logging all headers for convenience** — Authorization/Cookie/custom API keys can be exposed.
5. **Truncating the body provides protection** — the secret may sit at the beginning of the body.
6. **URLs are just metadata** — query strings can contain signed URLs/reset tokens.
7. **Java record.toString() is always safe** — it can list all components.
8. **JSON annotations also hide fields in Lombok/toString** — each serializer has its own mechanism.
9. **Exception.getMessage() is always harmless** — it can contain URLs, headers, or SQL parameters.
10. **With MDC, just put the token in for easy searching** — the token can be emitted in every event.
11. **Logback JSON encoder automatically redacts** — structured format does not guarantee security policy.
12. **Regex masking catches every secret** — cannot be guaranteed for new variants.
13. **Hashing a token and logging it is definitely safe** — there may be brute-force or data-correlation risks.
14. **Redacting at the collector means source files are clean** — raw data can exist before the collector.
15. **Encrypted logs mean dashboard readers cannot see them** — the API may decrypt them for readers.
16. **Deleting one log line is enough to handle an incident** — secrets need revocation/rotation and copy handling.
17. **A test not seeing a token when the logger is off means PASS** — there must be a positive control.
18. **Using real secrets for testing** — CI logs/artifacts themselves can become a leak vector.
19. **Not checking the exception cause chain** — a secret can reside in a nested Throwable.
20. **Testing only the console** — files, collectors, and exports may contain different representations.

## 18. Pre-Release Review Checklist

- [ ] Event name, purpose, severity, and field allowlist are clear.
- [ ] No passwords, API keys, tokens, cookies, key material, or OTPs in messages/attributes/MDC.
- [ ] No raw headers/body/URL/query logged unless specially classified and protected.
- [ ] No entire DTOs, Java records, maps, or nested objects containing credentials logged.
- [ ] Exception messages/cause chains from libraries have been evaluated.
- [ ] Configuration dumps and library DEBUG/TRACE are controlled.
- [ ] Structured encoder and escaping are tested with CR/LF, Unicode, and long inputs.
- [ ] Tests use dummy sentinel secrets, have positive controls, and check all relevant levels.
- [ ] Tests verify JSON formatted output, MDC, arguments, Throwables, and critical sinks.
- [ ] No real credentials are used and no secrets are placed in test failure reports.
- [ ] Log storage has RBAC/ABAC, TLS, retention, auditing, and separate export permissions.
- [ ] If a leak has occurred, there is a procedure for revocation/rotation, copy management, and post-incident review.

## 19. Self-Study Exercises

1. Run **SafeSecretLoggingDemo.java** and explain why LoginAttempt holds a token while the logs contain no token.
2. Predict the risk if **LOG.info(attempt.toString())** is added to the demo program; explain Java record toString.
3. Extend safeRequestId to allow only the req- prefix and valid characters, then test CR/LF input.
4. Design a safe event for an OAuth provider call failure where the exception message contains an access token.
5. A filter logs all HTTP headers at DEBUG: build an allowlist of permitted metadata.
6. Create an integration test for a Logback JSON encoder, checking formatted message, MDC, structured arguments, and Throwable.
7. A password reset URL has a token in the query string: design an alternative route-template log.
8. A real API key was logged in production: draft a runbook for revocation/rotation, backup handling, auditing, and notification.
9. Explain why dashboard masking does not protect raw exports/APIs.
10. Design a test that enables DEBUG/TRACE in an isolated environment while still proving no sentinel secret is leaked.

## 20. Conclusion

**Logging secrets is a logging design flaw, not merely a choice of format or log level.** Secrets can enter logs directly or indirectly through headers, URLs, DTO.toString, Java records, exceptions, MDC, config dumps, and third-party libraries. Once an event is emitted, it can be copied to many places with broader read permissions than the original secret.

The priority measure is **not logging secrets at the source**, using **safe events and allowlisted fields**, testing with **dummy sentinel values** at log levels that may be enabled, and governing read/transport/retention permissions. Redaction, TLS, encryption, and RBAC are supporting layers rather than substitutes for data minimization.

When a real secret has appeared in logs, treat it as a potential credential-exposure incident: **contain, revoke/rotate according to risk, handle copies, check audits, and add regression tests**.

### Official References

- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- MITRE CWE-532 — Insertion of Sensitive Information into Log File: https://cwe.mitre.org/data/definitions/532.html
- OWASP DevSecOps — Logging and Monitoring: https://owasp.github.io/DevSecOpsGuideline/2-Process/2-7-Operate/2-7-2-Logging-and-Monitoring/
- Oracle Java 17 Record Classes: https://docs.oracle.com/en/java/javase/17/language/records.html
- Oracle Java 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- SLF4J Manual: https://www.slf4j.org/manual.html
- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Logback Manual: https://logback.qos.ch/manual/index.html
- OpenTelemetry Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/