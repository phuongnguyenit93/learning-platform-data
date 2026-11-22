# Tokens and Credentials in Java Logging — Protecting Secrets and Privacy

## 1. Why Is This an Important Topic?

In Java Logging, logs help investigate failed logins, denied access permissions, failed database connections, expired tokens, or administrative operations. However, **tokens and credentials** can allow their holder to perform actions on behalf of a user, service, or system. If they are written to logs, permission to *read logs* can inadvertently become permission to *use credentials*.

This article belongs to the **Privacy** group: it is necessary to retain enough operational and audit information **without leaking secrets, session identifiers, or unnecessary personal data**.

Compare two ways of logging:

```text
DON'T:
INFO Login failed: Authorization=Bearer TEST_SECRET_VALUE
ERROR Database connection failed: jdbc:postgresql://db/app?password=TEST_SECRET_VALUE

DO:
WARN event=auth.denied method=Bearer reason=INVALID_CREDENTIAL request_id=req-42
ERROR event=db.connection_failed datasource=orders-db error_type=SQLTransientConnectionException
```

The values in the example are **dummy strings**, not valid credentials. The safe logging approach still indicates the operation type, error, and related request, without placing secrets where others can search or download them.

**Core principle:** design safe log data **before** calling the logger. Masking at the appender/Collector is a second line of defense, not a reason to log secrets at the source.

## 2. Distinguishing Tokens, Credentials, and Identifying Data

A **credential** is proof used for authentication/authorization, such as a password, API key, client secret, or private key. A **token** is typically a system-issued value used to represent a session, identity, access right, or action. A Bearer token is a credential: anyone holding the token may be accepted according to its scope and validity conditions.

| Data | Risk if raw value is logged | Information that can be logged instead |
| --- | --- | --- |
| Password, PIN, OTP | Exposes access rights or one-time codes | `auth_method`, `outcome`, standardized reason |
| API key, OAuth client secret | Application impersonation, unauthorized API calls | Integration name, permitted key alias/version |
| Bearer/access token | Reuse of permissions granted to someone else | `credential_present`, `auth_method`, outcome |
| Refresh token | Requesting a new access token | `refresh_attempt`, result, error category |
| Session ID and `Cookie` | Session hijacking | `session_started`/`session_expired`, request ID |
| `Set-Cookie` response | Exposes privileged cookies | Session creation outcome, without recording cookie value |
| JWT | Exposes claims and allows using a still-valid token | **Allowlisted** claims if strictly necessary |
| OAuth authorization code | Can be exchanged for a token under certain conditions | `flow=AUTHORIZATION_CODE` and outcome |
| PKCE verifier, magic/reset token | Exposes verification/recovery data | Route template, event type, and outcome |
| Private key, signing key, keystore password | Compromises cryptography or service identity | Non-sensitive key ID/alias, rotation event |
| JDBC URI containing password | Exposes DB account | Datasource name, error type, retry count |
| Cloud temporary credentials | Unauthorized access to cloud resources | Approved nominal role/service identity |
| Webhook signing secret | Webhook spoofing | `signature_valid=false` and provider |

**A signed JWT does not mean an encrypted JWT.** With the common JWS format, the Base64URL-encoded header/payload can be read without knowing the signing key. Do not log the full JWT, and do not print the decoded payload just for debugging. Claims such as `sub`, `email`, or `jti` can also be identifying data or linkable to user behavior.

Not every field named "ID" is safe. `client_id` is sometimes a public identifier, whereas `session_id` is usually a secret; `trace_id` can serve correlation while `token` is prohibited. All metadata must also comply with the system's privacy and retention policies.

## 3. Why Can a Single Log Line Spread to So Many Places?

A Java event can travel through the following chain:

```text
HTTP Authorization / Cookie / credentials
                 |
          Java application
                 |
          SLF4J / JUL / Log4j 2
                 |
      Console / File / Async / OTLP
            /              \
       Log shipper      Collector
            \              /
           Central log backend
                  |
          Dashboard / Alert
                  |
       Export / Ticket / Backup
```

A token logged at `log.debug` can be stored in the console, rolling files, agents, search systems, alert emails, screenshots, support tickets, and backups. Deleting it at one source **does not delete downstream copies**. Dashboard read permissions may also be broader than access to a secret manager or service account.

The impact depends on the token type and validity period, including session hijacking, API access, data querying, privilege escalation, or privacy violations. Even an expired token can reveal claims, metadata, or activity patterns. Therefore, the issue is not just "is the token still usable" but also **over-collection and expanding the audience that can read it**.

## 4. Common Leak Vectors in Java

| Source | Risky example | Prevention |
| --- | --- | --- |
| Direct logging | `log.info("token={}", token)` | Never pass tokens to the logging API |
| DTO / record | `log.debug("login={}", loginRequest)` | Do not print objects containing passwords; create a safe view |
| HTTP request headers | Dumping `Authorization`, `Cookie`, `X-API-Key` | Log only approved header names/auth types |
| HTTP response headers | Dumping `Set-Cookie` | Exclude cookie values |
| HTTP body | Login/refresh JSON containing secrets | Do not dump authentication bodies |
| URL/query string | `/reset?token=...`, `?code=...` | Log route templates, not raw URIs/queries |
| Exception | `ex.getMessage()` with URL/header/password | Log error category, type; sanitize the entire cause chain |
| Stack trace | Throwable containing secret messages | Do not automatically print Throwables from untrusted sources |
| MDC / ThreadContext | `MDC.put("access_token", token)` | Put only valid correlation metadata |
| SQL/ORM logging | JDBC bind values, DSN with password | Do not log sensitive bind values |
| HTTP client wire log | DEBUG OAuth request/response | Disable raw wire payloads or strictly control them |
| Reverse proxy/gateway | Access log with full query/headers | Configure privacy independently at each layer |
| Telemetry | Span attributes, baggage containing tokens | Do not place secrets into observability signals |
| CI/CD / startup | Echoing env vars, config, command line | Do not print secrets in build/deploy logs |

In particular, `Authorization: Basic ...` is Base64 of the credentials, **not a form of secret encryption**. It must also be excluded from logs. For a bearer token, the `Authorization` value may be accessible in code, but **must never become a logger parameter**.

URLs are dangerous even without a query string: a path like `/reset/ACTUAL_TOKEN` may contain a recovery code. Thus, simply stripping the query string and logging `request.getRequestURI()` is not necessarily safe.

## 5. Strongest Defense: Allowlist Log Fields

Instead of waiting for an encoder to find keys that "look like secrets," define an **allowlist of fields permitted to be logged** for each event type.

Example authentication event:

| Field | Illustrative value | Policy |
| --- | --- | --- |
| `event` | `auth.denied` | Allowed |
| `auth_method` | `Bearer` | Allowed |
| `credential_present` | `true` | Allowed if needed |
| `outcome` | `DENIED` | Allowed |
| `reason` | `INVALID_CREDENTIAL` | Allowed via enum |
| `request_id` | `req-42` | Allowed if ID is generated safely |
| `route` | `/api/orders/{id}` | Allowed in template form |
| `service` | `account-service` | Allowed |
| `client_id` | `client-demo` | Policy-dependent only |
| `authorization` | Raw Bearer token | **Prohibited** |
| `password` / `otp` | Secret value | **Prohibited** |
| `refresh_token` / `api_key` | Secret value | **Prohibited** |
| `cookie` / `session_id` | Session credential | **Prohibited** |
| `exception_message` | Unclassified text | Do not log by default |

**Allowlist vs. blocklist:** if a developer adds a `sessionProof` field to a DTO, an allowlist will not automatically print it. A blocklist that only knows `password` and `token` can miss new aliases.

Do not use `request.toString()`, `Map.toString()`, or serialize an entire object as a shortcut. Java `record` types automatically generate `toString()` with all components, so a record containing `password` can leak it when logged directly.

### 5.1. Safe Structured Logging

Example JSON log record without secrets:

```json
{
  "event": "auth.denied",
  "service": "account-service",
  "auth_method": "Bearer",
  "credential_present": true,
  "reason": "INVALID_CREDENTIAL",
  "route": "/api/orders/{id}",
  "request_id": "req-42"
}
```

This is an **illustrative schema**; it does not claim to be a mandatory schema of OpenTelemetry or any framework. When switching to a JSON encoder, you must inspect **message, structured fields, MDC, markers, and exceptions**. An encoder that outputs JSON does not automatically strip secrets.

## 6. Standalone Runnable Java 17+ Example

This example uses `java.util.logging` (JUL) from the JDK, requiring no external libraries. It creates a **dummy token used only for testing**, while the log records only the authentication type, a credential-present flag, and the outcome. `CaptureHandler` keeps the output in memory to verify that the dummy token string never appears.

Create `SafeCredentialLoggingDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SafeCredentialLoggingDemo {
    private static final class CaptureHandler extends Handler {
        private final StringBuilder output = new StringBuilder();

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            output.append(record.getLevel().getName())
                  .append(" ")
                  .append(record.getMessage())
                  .append("\n");
        }

        @Override public void flush() { }
        @Override public void close() { }

        String content() {
            return output.toString();
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.auth");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        CaptureHandler handler = new CaptureHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            // Synthetic fixture only, not a real token.
            String syntheticToken = "test-only-not-a-real-secret";
            boolean credentialPresent = !syntheticToken.isBlank();

            logger.info("event=auth.attempt method=Bearer "
                    + "credential_present=" + credentialPresent
                    + " request_id=req-42");
            logger.warning("event=auth.denied "
                    + "reason=INVALID_CREDENTIAL request_id=req-42");

            String loggedText = handler.content();
            if (loggedText.contains(syntheticToken)) {
                throw new AssertionError("Secret leaked to log");
            }
            System.out.print(loggedText);
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac --release 17 SafeCredentialLoggingDemo.java
java SafeCredentialLoggingDemo
```

**Exact** stdout:

```text
INFO event=auth.attempt method=Bearer credential_present=true request_id=req-42
WARNING event=auth.denied reason=INVALID_CREDENTIAL request_id=req-42
```

Because `setUseParentHandlers(false)` is set, the parent logger's handler does not produce duplicate output. `CaptureHandler` intentionally omits timestamps and records only the two generated events, making the output deterministic.

**Demo limitations:** `CaptureHandler` is not a production security logging system. It still appends `record.getMessage()` verbatim; if a developer later logs a secret at the source, the handler will still record it. A `contains(...)` check does not catch all encoded/escaped variants of a credential. In a real application, you must test **all** appenders and exporters.

### 6.1. Parameterized Logging Does Not Automatically Mask Secrets

The calls below are **unsafe** even though they use placeholders:

```java
log.debug("Authorization={}", authorizationHeader);
log.info("loginRequest={}", loginRequest);
log.error("Authentication failed", exceptionWithTokenInMessage);
```

This is an **illustrative SLF4J snippet**, not a standalone class. The `{}` placeholder supports formatting via the logger's mechanism, but does not automatically redact data. A DTO's `toString()` or an exception's message/cause can still reveal secrets.

Replace with metadata:

```java
log.warn("event=auth.denied method={} reason={} request_id={}",
        "Bearer", "INVALID_CREDENTIAL", safeRequestId);
```

`safeRequestId` must be a generated/controlled correlation ID, **not a session ID or token**. If you need to log a client/actor, use only an identifier that has passed privacy review.

## 7. Exceptions and Stack Traces Often Contain More Than Expected

In Logback/Log4j 2, `log.error("Request failed", ex)` can output the stack trace, cause chain, and suppressed exceptions. Exception objects may contain URLs, HTTP headers, response bodies, JDBC connection URIs, or tokens in their messages.

Common sources:
- HTTP client reporting a failed request along with a URI containing a token.
- Database driver printing a connection string containing a username/password.
- Failed JWT parsing where the exception repeats the entire input.
- OAuth endpoint error whose response body contains a token/secret.
- Validation error displaying the value of a password/OTP field.

You do not need to eliminate every stack trace at all costs. Instead, **proactively prevent secrets from entering exceptions in the first place**, use safe error codes and exception types in general logs, and only print stack traces after verifying trusted data sources.

Example integrated SLF4J snippet:

```java
log.error("event=auth.provider_failed provider={} error_type={} request_id={}",
        "identity-provider",
        ex.getClass().getSimpleName(),
        safeRequestId);
```

It does not pass `ex` or `ex.getMessage()` to the logger. When a traceback is genuinely needed, evaluate both the cause chain and nested messages; avoid reflexively passing a risky exception as the final argument to a logger.

## 8. Protecting HTTP Headers, URLs, and Bodies

### 8.1. Request Headers and Cookies

Never dump the values of:
- `Authorization`, `Proxy-Authorization`;
- `Cookie`, `Set-Cookie`;
- `X-API-Key`, `X-Auth-Token`, or custom headers containing credentials;
- headers carrying signatures, CSRF/session proofs, or internal protocol secrets.

Header names can vary across SDKs. Therefore, a denylist of a few names is **not enough** to protect a "log all headers" feature. If you only need to know whether a request had an Authorization header, use an approved Boolean flag and do not keep a copy of the header in the event.

### 8.2. Query Strings and Path Segments

Tokens can appear in `?access_token=...`, `?code=...`, `?signature=...`, password-reset links, or signed URLs. When logging routes, use a **route template** like `/reset/{token}`, not the raw URL. Avoid logging redirect `Location` headers that contain codes/tokens. Reverse proxies and ingress controllers also need their own configuration.

### 8.3. Request Bodies

Login and refresh-token endpoints typically include `password`, `otp`, `client_secret`, or `refresh_token`. Avoid printing raw bodies on validation exceptions. If you need to know which field is missing, log the field name **from an allowlist**, not its value. Do not serialize POJOs/records containing secrets just to inspect JSON.

## 9. Spring Boot 3: Illustrating Request Logging Without Printing Credentials

This is **an integrated class** in a Spring Boot 3 project using Spring MVC, SLF4J, and Jakarta Servlet; it requires framework dependencies. It is not a standalone `javac`-only program.

File `src/main/java/com/example/logging/SafeRequestLogFilter.java`:

```java
package com.example.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public final class SafeRequestLogFilter extends OncePerRequestFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeRequestLogFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        try {
            chain.doFilter(request, response);
        } finally {
            Object mapped = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            String route = mapped instanceof String s
                    ? s : "unmatched";
            LOG.info("event=http.request method={} route={} status={}",
                    request.getMethod(), route, response.getStatus());
        }
    }
}
```

`HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` usually holds the route pattern after the handler has been mapped. If the request is rejected before MVC, use `unmatched` instead of the raw URI/query. The example logs only method, route, and status; it does not touch Authorization, Cookie, principal, body, or raw URL.

**Inspect the entire pipeline:** Spring Security, servlet container access logs, HTTP client interceptors, ingress, and reverse proxies can log requests through other paths. An application filter does **not** automatically protect them. If a route pattern or method does not conform to an internal allowlist, normalize it further according to system policy.

### 9.1. HTTP Client Debugging Must Be Bounded

Enabling DEBUG/TRACE or wire logging on HTTP clients, ORMs, Security SDKs, or OAuth SDKs can produce dumps containing headers and bodies. You should:
1. Use an environment with synthetic credentials when reproducing issues.
2. Target a specific logger package; do not enable TRACE system-wide.
3. Log only method, endpoint template, status, latency, and error category.
4. Check console, files, and Collector before sharing logs.
5. Turn off detailed debugging after investigation.

In particular, token endpoints return JSON containing `access_token`/`refresh_token`: do not log the full response to "check whether a token was issued." Log `issued=true`, the token type, and a TTL bucket if approved.

## 10. MDC, ThreadContext, and Tracing Are Not Secret Stores

SLF4J/Logback's MDC and Log4j 2's ThreadContext are used to attach metadata to logs. They are correlation tools, not places to store tokens.

Do not do this:

```java
MDC.put("access_token", token);
log.info("request started");
```

This is an SLF4J snippet inside a class that already has a logger. If the pattern uses `%X` or a JSON encoder serializes the entire MDC, the token can be multiplied into **every log** emitted from that thread. When a thread pool reuses threads, an uncleaned MDC can also bleed context across requests.

Do this instead:

```java
try {
    MDC.put("request_id", safeRequestId);
    log.info("event=request.started");
} finally {
    MDC.remove("request_id");
}
```

`safeRequestId` must be a non-privileged ID issued/controlled according to policy. With async logging, the framework may snapshot the MDC to carry it across a queue; **do not put a secret into the MDC thinking other workers will not see it**.

With OpenTelemetry, do not place access tokens, cookies, or private keys into **span attributes, resource attributes, or baggage**. Baggage can be propagated to other services. `trace_id` helps correlate logs with traces, but it is not a place to store authentication evidence.

## 11. Masking/Redaction Is a Second Line of Defense

Additional techniques to apply:
- Structured log encoders that build output from allowlisted fields.
- JSON field-based redaction (including nested fields), checking aliases and case sensitivity.
- Dedicated appender filters to strip unwanted patterns.
- Sanitization at the Collector before data enters the backend.
- Periodic secret scanning to detect missed formats.

**Limitations:** a console appender filter does not control a file appender; a Collector filter runs **after the secret has already left the JVM**. A regex matching a single pattern will not cover URLs, JSON-escaped strings, Base64, multiline exceptions, or SDK variations.

Log4j 2 has `%replace` in Pattern Layout. An *illustrative* example of a layer replacing an Authorization header-like string in text:

```xml
<PatternLayout
    pattern="%d %-5p %c - %replace{%msg}{(?i)(authorization:\s*bearer\s+)\S+}{$1[REDACTED]}%n"/>
```

This syntax belongs to **Log4j 2 PatternLayout** and must not be copied verbatim to Logback. This pattern applies only where the layout is attached and matches **only one text format**; it is not a complete production policy. Never intentionally pass a token to the logger just to test whether the regex hides it. For a real system, using allowlists and testing across multiple sinks is far better.

### 11.1. Is Showing Only a Few Characters of a Token Enough?

Do not assume `token_prefix=abc` or `last4=1234` is safe by default. It still exposes part of the secret, which can aid access correlation or guessing attacks on weak credentials. If you need to distinguish keys/tokens, prefer a **separate non-privileged key ID or version** issued by the system and approved for logging; do not take substrings from credentials as identifiers.

## 12. Hashing, Fingerprints, and HMAC

Some systems want to know whether multiple requests used the same credential. **Do not log raw tokens** to perform correlation.

A plain `SHA-256(token)` hash can be brute-forced for low-entropy tokens/OTPs, and a stable hash can become a long-lived tracking identifier. If necessary and approved by security/privacy review, consider **HMAC-SHA-256 using a separate secret key** managed in a secret manager to generate a correlation fingerprint.

Conditions:
- The HMAC key must not be written to logs, source code, or broadly visible environments.
- A fingerprint **is still linkable** and requires its own retention/ACL policy.
- Key rotation affects historical correlation.
- Never use a fingerprint as a credential or pass it to an authentication system.
- Evaluate collision probability if truncating the fingerprint.
- If a request ID or key alias suffices, **do not generate a fingerprint**.

HMAC does not preserve privacy simply by "hashing it and calling it a day." Storing linkable identifiers and audit trails must still have a valid purpose.

## 13. Log Access Control and Retention

Logging designed with data minimization still requires controls:
- **Least privilege:** which roles can search/export logs? Should audit/security logs be separated from application logs?
- **Encryption in transit:** TLS/authentication between appenders, agents, Collectors, and backends.
- **Encryption at rest:** protect storage, snapshots, and backups.
- **Retention:** limit retention duration to match operational/legal purposes; do not keep all logs indefinitely.
- **Access audit:** track who views/downloads/exports logs when the system supports it.
- **Environment separation:** avoid moving test credentials or sensitive production logs into workspaces with broad access.
- **Third-party vendors:** know which log, telemetry, and support providers receive the data.
- **Incident reporting:** avoid copying raw credentials into alerts, tickets, or investigation chats.

Encryption does not make logging raw tokens safe: anyone authorized to view decrypted content can still use the token. You must combine data minimization with access control.

## 14. Testing for Zero Secret Leaks Across Sinks

Use a **synthetic canary token**: an easily recognizable dummy string that has no authentication validity. Create test requests containing the canary in the Authorization header, Cookie, JSON body, URL, simulated exception message, and nested DTO. Then verify:

1. Loggers in code **do not receive** the secret as a parameter.
2. Structured messages, MDC, markers, and exceptions do not contain the secret.
3. Console/stdout and stderr do not emit the canary.
4. Files, rolling archives, and async appenders do not write the canary.
5. OTLP/Collector/backend do not ingest the canary.
6. Pipeline alerts/tickets/webhooks/exports do not attach the canary.
7. There are no duplicate logs across multiple pipelines amplifying an incident.
8. Necessary security events remain intact for investigation.

Example test matrix:

| Case | Expectation |
| --- | --- |
| HTTP Authorization Bearer | Log only method/outcome, no value |
| HTTP Basic | Do not log Base64 credentials |
| Login DTO with password/OTP | Do not log the full DTO |
| OAuth refresh fail | Log reason enum, not the refresh token |
| JWT validation error | Do not log raw JWT string or decoded payload |
| OAuth redirect with `code` | Log route template, not raw URL |
| Exception with secret in message | Do not let risky text pass through Throwable formatter |
| MDC accidentally receives token | Test detects it; not serialized to sink |
| HTTP wire DEBUG | No raw headers/body |
| Structured JSON nested field | Apply allowlist to nested fields as well |
| Synthetic token at collector | No canary in backend |
| Rejected auth request | Event, outcome, request ID, and timestamp present |

Regex/entropy-based secret scanners help catch some issues but have false positives and false negatives. A clean scanner result **is not absolute proof**. You must re-test whenever frameworks are upgraded or when HTTP SDKs, encoders, or collector configs change.

## 15. When a Credential Is Accidentally Logged: Incident Response

If a token, password, API key, or private key is discovered in logs:

1. **Assess scope**: credential type, timestamp of appearance, log destinations, who has read access, and what copies may exist. Do not paste the raw value into a new ticket.
2. **Containment:** restrict access to the affected logs and **revoke/rotate** the affected credential according to procedure.
3. **Replace usages:** update services/configs/deployments so they no longer depend on the old secret; verify the application still works.
4. **Fix the leak source:** remove sensitive input logging, fix DTO `toString()`/wire logging/exceptions/MDC, and add safe event fields.
5. **Handle stored data:** coordinate with backend administrators to delete/restrict data as feasible under policy and audit preservation requirements; check exports, alerts, and backups.
6. **Investigate abuse:** correlate the secret's validity window with suspicious usage events.
7. **Regression testing:** emit a synthetic canary and verify it is no longer written to any sink.
8. **Evaluate privacy/security obligations** under organizational policy and applicable laws.

Rotation does not erase secrets already captured or accompanying identifying data; deleting a log line does not revoke a still-valid token. Both remediation tracks must happen appropriately.

## 16. Common Misconceptions That Cause Leaks

| Misconception | Reality |
| --- | --- |
| "It's only logged at DEBUG, so secrets won't leak." | DEBUG can be enabled in production or debug environments, and the data is already stored. |
| "SLF4J `{}` parameters automatically mask tokens." | Placeholders are not redaction. |
| "JWTs look encrypted, so they are safe." | Signed JWTs usually have readable payloads; the token is also a bearer credential. |
| "Logging only the last 4 characters is fine." | It can still leak/enable correlation; requires a specific policy. |
| "Masking only the console is enough." | File, async, OTLP, and Collector can be independent paths. |
| "Using JSON logging prevents leaks." | A JSON encoder can still serialize raw tokens, MDC, and Throwables. |
| "Exceptions only print technical stack traces." | Causes/messages can contain URLs, headers, and response bodies. |
| "`SHA-256(token)` is public data." | Weak credentials can be brute-forced, and a fingerprint is still an identifier. |
| "Having TLS means logging passwords is allowed." | TLS protects data in transit, not who can read stored data afterward. |
| "Deleting from the log file is enough." | Copies may exist in backends, exports, alerts, and backups. |
| "Turning off all auth logs is safer." | You still need to record security events **without credentials**. |

## 17. Pre-Deployment Checklist

1. Classify all secrets and secret-bearing fields (passwords, OTPs, tokens, cookies, API keys, private keys, DB URLs).
2. Define a security event schema with **allowlisted fields** and standardized outcomes/reasons.
3. Never pass secrets to loggers, `toString()`, throwables, or MDC.
4. Never log raw Authorization/Cookie headers, authentication bodies, URLs/queries, or signed links.
5. Log endpoints using route templates; use safely issued correlation IDs.
6. Control HTTP client wire logs, security framework DEBUG logs, and ORM bind-value logging.
7. Verify Logback/Log4j 2/JUL, console/file/async/OTLP, Collector, and backend independently.
8. Use sink masking as a secondary layer; test case sensitivity/aliases/encodings/nested fields.
9. Manage read/export permissions, retention, TLS, encryption, and vendor access.
10. Run synthetic canary tests in CI/integration and inspect all outputs.
11. Maintain a runbook for revoking/rotating credentials and handling logs that captured credentials.
12. Retain critical authentication events without retaining the raw credentials.

**In summary:** logs should tell you **how a credential was presented, checked, and accepted or rejected**—never hand the credential itself to the log reader. Designing safe fields at the source is the strongest measure; encoding, redaction, access control, and incident response are supporting layers of defense.

## References

- [OWASP Logging Cheat Sheet – Data to exclude and sanitization](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- [OWASP Secrets Management Cheat Sheet – Rotation, revocation, and logging](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).
- [OWASP DevSecOps Logging and Monitoring](https://owasp.github.io/DevSecOpsGuideline/2-Process/2-7-Operate/2-7-2-Logging-and-Monitoring/).
- [Oracle Java – java.util.logging.Logger](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Logger.html).
- [Oracle Java – java.util.logging.Handler](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Handler.html).
- [Apache Log4j 2 – Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html).
- [Logback – Logging architecture](https://logback.qos.ch/manual/architecture.html).
- [OpenTelemetry – Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).