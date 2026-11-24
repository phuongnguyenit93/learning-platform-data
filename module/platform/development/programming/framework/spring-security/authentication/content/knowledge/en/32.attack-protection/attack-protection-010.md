# Never log passwords, tokens, API keys, or recovery codes

When defending Spring Security authentication systems against attacks, logs are crucial for detecting failed logins, spotting denied access, investigating incidents, and monitoring administrative activity. Yet logs themselves can become a **leaked-credential repository** if application code or infrastructure accidentally writes passwords, access tokens, refresh tokens, API keys, recovery codes, or session cookies.

**Core principle:** *Log the security event and processing outcome, never the secret used to execute that event.* For example, log `security_event=LOGIN_REJECTED`, `outcome=DENIED`, and a server-generated trace ID; never log the `password` field, full `Authorization` or `Cookie` headers, or user-submitted token strings.

This lesson applies to **Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet)**, and is equally relevant to WebFlux, API Gateways, reverse proxies, and observability pipelines. Illustrative examples use synthetic test data only and require no real credentials. The goal is establishing mechanisms that **prevent sensitive data from entering logs at the source**, rather than relying on regex masking after secrets have already entered the pipeline.

## 1. Why can a single log line nullify authentication?

Suppose an API receives:

~~~http
POST /api/auth/login HTTP/1.1
Content-Type: application/json
Authorization: Bearer <ACCESS_TOKEN_TEST_ONLY>

{
  "username": "alice",
  "password": "<PASSWORD_TEST_ONLY>"
}
~~~

A developer might think logging the whole request for debugging will help investigate errors:

~~~java
// WRONG: may log the password or token the user just entered.
log.debug("loginRequest={}", requestBody);
log.debug("authorization={}", httpRequest.getHeader("Authorization"));
~~~

If an attacker gains log-read access, the fallout can include:

- **Password**: retry logins or use in credential stuffing across other services.
- **Bearer access token**: call APIs as the token owner until the token is rejected/expired.
- **Refresh token**: mint new access tokens, potentially extending access far longer.
- **Session cookie/ID**: hijack sessions depending on session policies and secondary defenses.
- **API key**: call integrated services, consume quotas, read/modify data.
- **Recovery codes**: bypass a multi-factor authentication step or seize account recovery.
- **Password reset/magic-link/one-time tokens**: hijack password reset or create sessions while the token stays valid.
- **Private keys, client secrets, connection strings with credentials**: compromise the application/service itself rather than a single user.

Logs are routinely replicated to collectors, dashboards, APMs, traces, alerting systems, backups, or external support teams; deleting a line in a local file **does not guarantee** all copies are gone. That is why sensitive data must be **excluded before writing**.

## 2. Classification: what data must never be logged verbatim?

| Data type | Example locations | Rule |
| --- | --- | --- |
| **Passwords**: current/new/confirm/temporary | JSON/form body, error queries, DTOs, exceptions | **Never log**, even on failed logins; do not call `toString()` on DTOs holding passwords |
| **Password hashes** | DB entities, `UserDetails`, debug responses | Keep out of logs; though not plaintext, still vulnerable to offline attacks |
| **Bearer access tokens, JWTs, ID tokens** | `Authorization` header, cookies, body, queries | Never log raw tokens or sensitive payloads/claims; validator error codes are fine |
| **Refresh tokens, opaque tokens, session IDs** | Cookies, token endpoints, `Set-Cookie` responses | Never log; session IDs are credentials in many schemes |
| **API keys, client secrets** | `X-API-Key`, `Authorization: Basic`, configs, env, HTTP responses | Never log values; manage separately via a secret store |
| **MFA/recovery/backup codes** | Device-change forms, resets, TOTP recovery | Never log either used or unused codes |
| **Password reset tokens, magic-link OTTs** | Query strings `?token=...`, paths, email redirects | Never log URLs containing tokens; log request or consume success/failure events |
| **Private keys, seeds, signing secrets** | PEMs, keystores, JWT issuers, Vault responses | Never log; protect metadata and error paths too |
| **Unnecessary PII** | Emails, phone numbers, IPs, devices | Minimize per investigation needs and privacy rules; enforce access control/retention if needed |
| **Data safe to log when well-designed** | Fixed event types, HTTP status, outcome enums, server request IDs, route templates | Allowed after checking provenance, size, and absence of user-injected secrets |

**Note on "masking":** logging `Authorization: Bearer ****` is less risky than logging the raw token, yet it is best **not to collect the full header** when unnecessary. Truncating to the last 4 characters of an API key/token can still leak useful information in some models; never do that by default. A JWT can also carry sensitive claims in its payload even if the signature is masked.

### Is a "Base64-encoded password" safe?

No. Base64 is merely **encoding**, which anyone can decode. Likewise, three-part JWTs usually carry readable Base64url payloads; `jwt.toString()`/`getClaims()` can expose identities, emails, or sensitive attributes. Never log tokens assuming "it's not immediately human-readable" makes it safe.

### Should you log SHA-256 hashes of tokens for correlation?

Not by default. Unkeyed hashes of short recovery codes, OTPs, or low-entropy API keys can be cracked offline. Even for high-entropy tokens, a stable fingerprint correlates users/sessions across log systems. When correlation is mandatory, prefer a **random event ID**, or design an internal token reference/keyed HMAC with strict access controls and lifecycle policies; assess risk separately instead of turning hashes into a new secret appearing in every log.

## 3. Leak points beyond developer log statements

~~~text
Client
  │
  ├─ Browser URL/history/devtools
  │
  ▼
CDN / WAF / Load Balancer / API Gateway / Nginx
  │ ├─ access logs containing path + query
  │ ├─ debug request/response headers
  │ └─ WAF samples/traces
  ▼
Servlet container (Tomcat)
  │ ├─ access logs
  │ └─ exception/error details
  ▼
Spring Security filter chain
  │ ├─ authentication failure/success handlers
  │ └─ security library DEBUG/TRACE
  ▼
Spring MVC Controller / Service
  │ ├─ DTO / exception / validation error logs
  │ ├─ request/response logging filters
  │ └─ DB/HTTP client tracing
  ▼
Logback / SLF4J + MDC / Micrometer / OpenTelemetry
  │ ├─ exporters/collectors/APM
  │ ├─ log aggregators/indexes
  │ └─ alerts, dumps, backups, and support bundles
~~~

No single "master switch" protects this entire pipeline. Inspect **every place that can generate and forward logs**, including:

1. **Backend source**: `log.debug/info/warn/error` calls, `System.out.println`, `printStackTrace()`, class `toString()`, AOP logging, audit events, and HTTP client interceptors.
2. **Web filters**: `CommonsRequestLoggingFilter` or custom filters reading/writing headers, queries, or payloads; avoid enabling carelessly.
3. **Spring MVC**: configuration enabling detailed request printing at DEBUG/TRACE.
4. **Error handlers**: `@ControllerAdvice` serializing full exceptions/DTOs, exposing `rejectedValue` containing passwords.
5. **Database/ORM/drivers**: logging SQL bind parameters, connection URLs with credentials, or bind values.
6. **Reverse proxies/load balancers**: many default access log formats record the raw request line, including query strings.
7. **Traces/APM/metrics**: tagging `authorization`, `request.body`, `session_id`, or `token` turns secrets into widely replicated telemetry.
8. **CI/build/tools**: `curl -v`, pipeline debug output, test reports, crash dumps, environment dumps, troubleshooting attachments.
9. **Frontend/mobile**: console/network debugging, third-party analytics, and client error tracking receiving inputs or URL tokens.
10. **Alerts/chat**: systems forwarding full log lines/stack traces to email, chat, or tickets with broader read access.

**Do not inspect only Controller logs.** An `Authorization` header printed by a proxy or APM is still an incident even if the controller has zero log lines.

## 4. Designing safe security events: log *metadata*, not secrets

A shared log vocabulary stops each developer from concatenating arbitrary strings:

| Event | Suggested minimal metadata | Strictly avoid |
| --- | --- | --- |
| `LOGIN_REJECTED` | time, outcome, audit ID, internal reason **category**, app/module | Attempted password, full `Authentication`, username if unnecessary |
| `LOGIN_ACCEPTED` | time, event, access-controlled internal account ID, audit ID | Session ID, credentials/passwords |
| `JWT_REJECTED` | error category code `SIGNATURE_INVALID`/`EXPIRED`/`AUDIENCE_INVALID` | Raw JWT, JWT claims, `Authorization` header |
| `API_KEY_ROTATED` | **system-issued** key record ID (not raw key), action outcome | Old/new API keys, suspicious secret prefixes |
| `RECOVERY_REQUESTED` | event, generic outcome, rate-limit classification | Recovery code, reset token, "email X does not exist" if unnecessary |
| `MFA_CODE_REJECTED` | generic type, audit ID, outcome | OTP/TOTP/recovery code |
| `ACCESS_DENIED` | policy/route template, HTTP 403, audit ID | URL containing token, full request, sensitive serialized principal/authorities |
| `ACCOUNT_LOCKED` | event, reason category, privacy-safe account reference if policy allows | Wrong password, reset codes, out-of-scope email info |

### 4.1. Using a field allowlist

**Unsafe approach:**

~~~java
// WRONG: request, credentials, or exception may contain secrets.
log.warn("Login failed: {}", request);
log.warn("Authentication details: {}", authentication);
log.warn("Reason: {}", exception.getMessage());
log.warn("Headers: {}", request.getHeaderNames());
log.warn("JWT: {}", jwt);
~~~

In some cases `request.getHeaderNames()` only prints header names, yet logging above is a bad pattern because it harvests unnecessary context; someone else will easily "upgrade" it to dump values too. `exception.getMessage()` is especially dangerous when exceptions embed raw input or HTTP client libraries put credentials into messages. Never call `log.warn("...", exception)` in sensitive auth flows by default without verifying the exception chain carries no secrets.

**Safer approach:**

~~~java
log.warn("security_event={} outcome={} audit_id={}",
        "LOGIN_REJECTED", "DENIED", generatedAuditId);
~~~

However, `generatedAuditId` must be server-generated or strictly validated—never use raw client `X-Request-ID` headers without trusting the source; headers can carry newlines, forged log text, or attacker-injected secrets. And one safe log call **does not guarantee** external filters/proxies are safe too.

### 4.2. Why do enums reduce risk?

If the logger only accepts `SecurityEvent` and `Outcome` (finite enums), developers cannot accidentally pass passwords or raw exceptions. To extend logging, reviewers must change the method signature rather than passing arbitrary `Object` or `Map<String,Object>` payloads.

Event codes/labels should be small, stable, and useful for SIEM, e.g., `LOGIN_REJECTED`, `TOKEN_INVALID`, and `RECOVERY_REDEEM_FAILED`. Avoid overly granular reason codes in public responses that let attackers infer whether an account exists.

## 5. Standalone Java 17 example without Spring: safe logging and exact stdout

A minimal example using `java.util.logging` and `enum`s to show events can be investigated without passing secrets to the logger. Standalone file `SafeAuditJava17.java`:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class SafeAuditJava17 {

    enum Event {
        LOGIN_REJECTED, TOKEN_REJECTED, API_KEY_ROTATED
    }

    enum Outcome {
        DENIED, COMPLETED
    }

    private static final Logger AUDIT =
            Logger.getLogger("example.security.audit");

    public static void main(String[] args) {
        AUDIT.setUseParentHandlers(false);
        AUDIT.setLevel(Level.INFO);

        StreamHandler handler = new StreamHandler(System.out,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return formatMessage(record)
                                + System.lineSeparator();
                    }
                });
        handler.setLevel(Level.INFO);
        AUDIT.addHandler(handler);

        // Passwords/tokens/API keys must not enter log parameters.
        // Demo ID is controlled, not taken from HTTP headers.
        audit(Event.LOGIN_REJECTED, Outcome.DENIED, "audit-001");
        audit(Event.TOKEN_REJECTED, Outcome.DENIED, "audit-002");
        audit(Event.API_KEY_ROTATED, Outcome.COMPLETED, "audit-003");

        handler.flush();
        AUDIT.removeHandler(handler);
        handler.close();
    }

    static void audit(Event event, Outcome outcome, String auditId) {
        AUDIT.log(Level.INFO,
                "security_event={0} outcome={1} audit_id={2}",
                new Object[] {
                    event.name(), outcome.name(), auditId
                });
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 SafeAuditJava17.java
java SafeAuditJava17
~~~

**Deterministic stdout**:

~~~text
security_event=LOGIN_REJECTED outcome=DENIED audit_id=audit-001
security_event=TOKEN_REJECTED outcome=DENIED audit_id=audit-002
security_event=API_KEY_ROTATED outcome=COMPLETED audit_id=audit-003
~~~

This snippet neither holds, reads, nor verifies credentials; it **only demonstrates one way to design an event logger**. Never pass raw client-sent `AuditId` values into that method in real systems; always use server-generated/validated IDs.

### Strengths and limitations

Using enums and fixed parameters prevents programmers from directly passing raw passwords into logs. Even so, real deployments still need:

- Clear rules on which fields may be added;
- Validation for strange input in metadata like routes, usernames, user agents, and IPs;
- Securing log channels and access permissions;
- Checking **other** loggers across the application and infrastructure;
- Automated secret-leakage checks using canaries in CI.

One "clean" audit log line does not let you conclude the whole system leaks no secrets if framework debug settings or proxies still record requests.

## 6. Spring Boot 3.5 + Spring Security 6.5: safe authentication failure logging

This sample app uses Spring Security **form login**. When a login is rejected, `AuthenticationFailureHandler` logs **only the event code, outcome, and a server-generated audit ID**. It does not log `request`, `authentication`, `password`, `exception.getMessage()`, or the body.

### 6.1. Gradle dependencies

In a Spring Boot 3.5.x project with the Boot Gradle plugin/BOM and JDK 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Boot's starter logging typically brings SLF4J/Logback; the example and test below rely on Boot 3.x's default logging. If a project swaps the logging backend, log suppression and test capture mechanisms may differ.

### 6.2. application.properties

File `src/main/resources/application.properties`:

~~~properties
# Explicit: prevent Spring MVC from printing request details at DEBUG/TRACE.
spring.mvc.log-request-details=false

# Keep logs at necessary levels. Never enable app-wide HTTP body/header debug logging.
logging.level.org.springframework.web=INFO
logging.level.org.springframework.security=INFO

# Lab user password passed via environment variable/secret store.
# Never commit a real demo.password value to the repository.
demo.password=${DEMO_PASSWORD}
~~~

`spring.mvc.log-request-details=false` is a Spring Boot 3.5 property, defaulting to `false`; setting it explicitly guards against accidentally enabling parameter/header logging. It **does not cover** custom filters, telemetry SDKs, Nginx, or your own logging calls.

**Never use `logging.level.root=OFF` to "solve" secret leaks:** that blinds you to attack signals. Fix the leak source instead of turning off all auditing/security monitoring.

### 6.3. Complete Java file

File `src/main/java/example/safelog/SafeLoggingApplication.java`:

~~~java
package example.safelog;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeLoggingApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeLoggingApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(
            PasswordEncoder encoder,
            @Value("${demo.password}") String rawDemoPassword) {

        // Lab-only account: never commit passwords to source code.
        UserDetails labUser = User.withUsername("lab-user")
                .password(encoder.encode(rawDemoPassword))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(labUser);
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, SafeSecurityAudit audit)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .failureHandler((request, response, exception) -> {
                    // NEVER LOG exception, request, password, or username.
                    audit.record(SecurityEvent.LOGIN_REJECTED,
                            AuditOutcome.DENIED);
                    response.sendRedirect(
                            request.getContextPath() + "/login?error");
                }));

        return http.build();
    }
}

enum SecurityEvent {
    LOGIN_REJECTED,
    TOKEN_REJECTED,
    RECOVERY_REDEEM_FAILED,
    API_KEY_ROTATED
}

enum AuditOutcome {
    DENIED, COMPLETED
}

@Component
class SafeSecurityAudit {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeSecurityAudit.class);

    void record(SecurityEvent event, AuditOutcome outcome) {
        // ID is always server-generated; never read client-sent headers.
        String auditId = UUID.randomUUID().toString();
        LOG.warn("security_event={} outcome={} audit_id={}",
                event.name(), outcome.name(), auditId);
    }
}

@RestController
class PrivatePage {
    @GetMapping("/private")
    String privatePage() {
        return "ok";
    }
}
~~~

**How it works:**

1. `InMemoryUserDetailsManager` creates one lab user so Spring does not auto-generate a random startup password and print it to the dev console; the lab password is supplied by the runner and encoded before storage.
2. `formLogin` provides the default login page at `GET /login`, handling `POST /login` and CSRF per default Spring Security config.
3. `AuthenticationFailureHandler` runs on failed login; it logs only `LOGIN_REJECTED`/`DENIED` and a UUID. No `exception` object is passed to the logger.
4. After logging, the handler redirects the browser to `/login?error`. This URL contains a **display status flag**, no credentials or user identifiers.
5. `/private` requires authentication, so unauthenticated requests redirect to the login form.
6. Upon successful login, Spring Security uses a normal session; the example never logs session IDs/cookies.
7. The code is a **local demo**; production must use a real user repository, HTTPS, rate limiting, and account-locking/MFA/session policies rather than keeping mock accounts in RAM.

**Note:** default form login reads `username`/`password` request parameters; Spring Security processes them internally. Because a framework **reads** a password to authenticate does not mean you may **write** the password to a logger. Never enable `CommonsRequestLoggingFilter` capturing full requests just to "see what's in the form".

### 6.4. Running the lab

Set `DEMO_PASSWORD` via a secret mechanism provided by your OS/IDE/secret manager **before** running; never type real values into shell commands recorded in build logs, CI YAML, or chat messages. This password is **lab data** and must not be reused on real accounts.

~~~bash
./gradlew bootRun
~~~

On Windows, use `gradlew.bat bootRun`.

When running properly, open `http://localhost:8080/login` and try user `lab-user` with a **wrong** password. The browser redirects to `/login?error`, and the console prints a line similar to:

~~~text
... WARN ... security_event=LOGIN_REJECTED outcome=DENIED audit_id=<server-generated-uuid>
~~~

This is the **expected log shape**, not fixed stdout: timestamp, logger format, and UUID change every run. The console must not contain the entered password or session/cookie headers. If you try the right lab password supplied via `DEMO_PASSWORD`, login succeeds and `GET /private` returns:

~~~text
ok
~~~

**Do not turn on framework-wide DEBUG/TRACE to capture "proof" and paste secret-filled logs into tickets.** Test under controlled conditions using fake data in test environments, never real credentials.

## 7. Automated testing: using canaries to detect credentials leaking into app logs

A **canary** is a unique synthetic string used strictly in tests, such as `TEST_CANARY_DO_NOT_USE_2026`. Tests submit the canary in password/token/API key/recovery code fields and verify **actual log output** never contains the canary. A canary is **not a real password** and must never serve as a production secret.

Below is a Spring Boot 3.5 + JUnit 5 + MockMvc/Logback test. It captures `ILoggingEvent` from `SafeSecurityAudit`'s own logger; the test verifies that logger does not record the canary. **Limitation:** capturing only the audit class's logger does not prove every proxy/filter/APM is safe. Add pipeline-level integration/canary tests in the next section.

File `src/test/java/example/safelog/SafeSecurityAuditTest.java`:

~~~java
package example.safelog;

import java.util.stream.Collectors;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "demo.password=TEST_ONLY_LAB_PASSWORD")
@AutoConfigureMockMvc
class SafeSecurityAuditTest {

    @Autowired MockMvc mvc;

    @Test
    void rejectedLoginDoesNotPutPasswordInAuditLog()
            throws Exception {

        // Simulates a WRONG password, strictly test canary data.
        String canary = "TEST_CANARY_DO_NOT_USE_2026";

        Logger auditLogger = (Logger) LoggerFactory.getLogger(
                SafeSecurityAudit.class);

        ListAppender<ILoggingEvent> buffer = new ListAppender<>();
        buffer.start();
        auditLogger.addAppender(buffer);

        try {
            mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "lab-user")
                    .param("password", canary))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));

            String messages = buffer.list.stream()
                    .map(ILoggingEvent::getFormattedMessage)
                    .collect(Collectors.joining("\n"));

            assertTrue(messages.contains(
                    "security_event=LOGIN_REJECTED"));
            assertTrue(messages.contains("outcome=DENIED"));
            assertFalse(messages.contains(canary));
            assertFalse(messages.contains("TEST_ONLY_LAB_PASSWORD"));
        }
        finally {
            auditLogger.detachAppender(buffer);
            buffer.stop();
        }
    }
}
~~~

Run:

~~~bash
./gradlew test --tests example.safelog.SafeSecurityAuditTest
~~~

Expected result: the test passes when app and libraries align, the handler performs the redirect, and the logger contains no canary password. **Never conclude "zero credential leaks system-wide" from this test alone.** It does not observe Nginx, container access logs, request filters outside the test context, HTTP client logs, APM exporters, or dashboards.

### 7.1. Full-pipeline canary testing

A stronger integration test should inject *distinct* canary strings into:

- `password` and `currentPassword`/`newPassword`;
- `Authorization: Bearer <canary>`;
- `X-API-Key: <canary>`;
- `Cookie: JSESSIONID=<canary>` and `Set-Cookie` responses in matching flows;
- `recoveryCode`, `otp`, `resetToken` in JSON/forms;
- `?token=<canary>` and canary-containing paths in test environments to catch proxy access-log leaks (then redesign architecture to avoid passing secrets in URLs wherever possible);
- Exception messages, validation `rejectedValue`, and auto-generated request DTO `toString()` outputs;
- Outbound client requests carrying API keys to other services.

After sending requests, collect **all logging sinks** in the test environment: application, container, ingress/proxy/WAF, log collector, APM/traces, metric tags, error tracking, and alert/ticket exports. Scan for exact canaries and common encodings only where permitted; do not assume missing raw strings means no Base64, URL-encoded, or JSON-escaped secret leaked.

A test is meaningful when it confirms **absence across collected sinks**. If you lack read access to APM/proxies, scope the conclusion accurately: "app logger pass", never "system-wide pass".

### 7.2. Intentional negative-control check

In a test environment, temporarily add a flawed filter (never merge to production) that logs `Authorization`, and verify the pipeline test **catches** the canary. This proves the check can actually detect leaks rather than passing simply because no logs were collected. When finished, remove the flawed filter and ensure it never deploys to any real environment.

## 8. Spring Framework and logging settings prone to leaking secrets

### 8.1. Spring MVC request-details logging

Per Spring Framework, request parameter/header details are masked at DEBUG/TRACE by default; enabling `enableLoggingRequestDetails` can expose sensitive data. Spring Boot 3.5 provides:

~~~properties
spring.mvc.log-request-details=false
~~~

Never set this to `true` on systems handling password forms or `Authorization` headers without evaluated controls. Never assume this single property protects custom filters or proxies: it is **one layer** inside Spring MVC.

### 8.2. CommonsRequestLoggingFilter

`CommonsRequestLoggingFilter`/`AbstractRequestLoggingFilter` exposes toggles:

- `setIncludeHeaders(boolean)`;
- `setIncludePayload(boolean)`;
- `setIncludeQueryString(boolean)`;
- `setIncludeClientInfo(boolean)`;
- `setHeaderPredicate(Predicate<String>)`;
- `setMaxPayloadLength(int)`.

A cautious configuration **if the app must have a request logging filter**:

~~~java
CommonsRequestLoggingFilter filter = new CommonsRequestLoggingFilter();
filter.setIncludeHeaders(false);
filter.setIncludePayload(false);
filter.setIncludeQueryString(false);
filter.setIncludeClientInfo(false);
~~~

This snippet requires importing `org.springframework.web.filter.CommonsRequestLoggingFilter` and placing it in appropriate configuration; it is **not a standalone program**. Even with all flags false, the filter can still log the **URI path** (excluding query). If an app embeds reset tokens/API keys in path segments, the URI can still leak them. Therefore it is best **not to use generic request logging** on sensitive endpoints, logging only defined route templates/event codes.

**Never use `setMaxPayloadLength(20)` as a password-masking mechanism.** It merely truncates logged character count without classifying data; the first 20 characters can already expose a secret.

### 8.3. Spring Security DEBUG and Authentication objects

Some Security components emit helpful debug details during troubleshooting, yet no log level should be assumed "guaranteed PII/secret-free" across all versions and custom extensions.

Specifically avoid:

~~~java
// WRONG: credentials/details may leak via serialization/toString.
log.debug("SecurityContext={}", SecurityContextHolder.getContext());
log.debug("Authentication={}", authentication);
log.debug("Request={}", request);
log.debug("Exception={}", exception);
~~~

Even if an implementation attempts to erase/mask credentials after authentication, custom `Authentication`, `AuthenticationDetailsSource`, or exception objects may hold raw data. Log only event codes and vetted metadata.

### 8.4. @ControllerAdvice, Bean Validation, and error reporting

A DTO such as:

~~~java
record LoginRequest(String username, String password) {
}
~~~

Java `record`s auto-generate a `toString()` containing the `password` field; calling `log.info("{}", loginRequest)` can print secrets. That is why sensitive DTOs must never enter logs. To reduce accidental `toString` leaks, you can override `toString()` to return a masked label, yet **never** rely on that override alone because JSON serializers/filters still read raw fields.

When handling `MethodArgumentNotValidException`, `FieldError.getRejectedValue()` can contain passwords/OTPs. Return only allowlisted field names and error codes:

~~~java
// Illustrated inside @ExceptionHandler(MethodArgumentNotValidException.class).
List<String> invalidFields = exception.getBindingResult()
        .getFieldErrors().stream()
        .map(error -> error.getField())
        .distinct()
        .toList();

log.warn("security_event={} invalid_field_count={}",
        "VALIDATION_REJECTED", invalidFields.size());
~~~

Never log or return `exception.getMessage()`, `getRejectedValue()`, the entire `BindingResult`, or the request body. On reset/login endpoints, error responses **must not tell attackers whether a user exists**; return generic messages while recording non-sensitive internal categories in audits.

## 9. Reverse proxies, URLs, and access logs

### 9.1. Query strings are a common leak hotspot

Many proxies write access logs containing the HTTP request line such as:

~~~text
"GET /reset-password?token=<RESET_TOKEN_TEST_ONLY> HTTP/1.1" 200
~~~

A user opening a magic link with a query token can expose the token across browser history, proxy access logs, error tracking, referrers, or analytics. Even if the token is single-use, **before consumption** it remains a live credential.

Defenses:

1. Where the protocol permits, carry tokens in request bodies or safe exchange flows rather than keeping them in URLs.
2. If magic links require URL tokens, lock down access logs/queries, referrers, and third-party resources; set `Referrer-Policy: no-referrer` on sensitive pages.
3. Never log full `requestURI + "?" + queryString`, or raw `getRequestURL()`/`getQueryString()`.
4. Never construct a redirect URL carrying a fresh token and then log the `Location` response header.
5. Enforce short TTLs and atomic one-time consumption so tokens cannot be reused after the first visit; yet **single-use does not replace leak prevention**.

### 9.2. Nginx: a queryless/tokenless logging pattern

A **simplified** access log example recording only method, status code, and a fixed route category, without `$request` or `$request_uri`:

~~~nginx
map $uri $safe_route {
    default "other";
    =/login "login";
    =/api/auth/login "auth_login";
    =/reset-password "password_reset";
}

log_format safe_auth '$remote_addr $request_method $safe_route '
                     '$status $request_time';

access_log /var/log/nginx/access.log safe_auth;
~~~

Place `map` in the `http` context and apply `access_log` in the matching context. Here `$uri` is used solely **to pick a static label** from an allowlist and is never printed directly. Variable paths carrying tokens or usernames get logged only as `other`, never raw path strings. This is a **technical illustration**; real Nginx configs must align with routing, reverse proxies, privacy policies, trust boundaries, and organizational audit rules. IPs in logs still require privacy/retention governance.

Never say "Spring request logging is off" and assume Nginx access logs are safe: those are two separate pipelines.

## 10. Micrometer, OpenTelemetry, MDC, and structured logs

Spring Boot has three observability pillars—**logs, metrics, traces**—plus Micrometer Observation integration. A clean log string may still leak tokens via:

- `http.request.header.authorization` tags;
- `request.body`/`response.body`;
- `url.full` span attributes (including queries);
- `session.id`, `api.key`, `jwt`, or `recovery.code` tags;
- arbitrary strings put into baggage/MDC and exported later;
- error-reporting SaaS capturing request/exception stacks in the background.

### 10.1. Never put secrets into MDC

MDC/trace baggage is designed to **propagate context**, not store secrets. Never call:

~~~java
// WRONG: easily leaks into every log line on the same thread.
MDC.put("token", bearerToken);
MDC.put("apiKey", apiKey);
MDC.put("sessionId", sessionId);
~~~

Use only permitted fields like random correlation IDs, route templates, or server-assigned, validated subsystem codes. In web thread pools, clean up MDC properly per request lifecycle (`MDC.remove`/`MDC.clear` as appropriate) to prevent context leaking to another request. In reactive pipelines, `ThreadLocal` has limits; use proper context propagation while still **never** putting credentials into context.

### 10.2. Metrics and cardinality

Avoid `token_value`, `user_input`, or `email` as metric tags. Metrics may be stored/replicated separately and suffer cardinality explosions that exhaust resources. Use finite categories:

~~~text
auth_attempts_total{event="login", outcome="denied", reason="invalid_credentials"}
auth_attempts_total{event="token", outcome="denied", reason="expired"}
~~~

These lines are **illustrative metric examples**, not complete Prometheus/Micrometer configs. Here `reason` is a fixed label from an allowlist, not `exception.getMessage()` or a JWT claim.

### 10.3. Does Logback masking replace not logging secrets?

**No.** Converters/filters/redaction in Logback or collectors should only be *defense in depth*:

- Regexes can miss JSON escaping, Base64/URL encoding, new token formats, nested fields, or multi-line payloads.
- Secrets may already have entered memory buffers, collectors, stdout, or the network before final masking.
- A secret inside another exception/call stack might not match a field named `password`.
- Printing even *part* of a token can still pose a risk depending on the algorithm and threat model.

Prioritize **never logging secrets in app loggers** and **never capturing sensitive bodies/headers** in filters/proxies/tracing; add masking afterward as a secondary safety net.

## 11. Secrets can leak via Java exceptions and third-party libraries

### 11.1. Never expose raw exception messages to logs/APIs by default

In various cases, exceptions from HTTP clients, databases, JSON parsers, or validation can include:

- URLs with `?api_key=...` or `?token=...`;
- database connection strings with username/password;
- rejected body/field values;
- access tokens inside external API error messages;
- objects holding recovery codes via auto-generated `toString()`.

**This does not mean dropping all stack traces:** for exceptions from components verified to carry no secrets, internal channels with proper permissions/retention may log them. However, for **authentication/password reset/token exchange** flows, select allowlisted error codes and inspect all exception/cause messages before emission. Clients must never see stack traces or raw upstream errors.

### 11.2. HTTP clients/outbound integrations

When `RestClient`/`WebClient`/`Feign` or an SDK adds `Authorization`/`X-API-Key` to outbound requests:

- Never enable full wire logging or log outbound request bodies/headers.
- If an interceptor must log, record only **trusted** host/route, method, outcome, timeout category, and correlation ID.
- Never log full request builders or full response bodies from token endpoints.
- If an API provider echoes tokens/secrets in error bodies, map them to categories; never dump `responseBody` into exception logs.

### 11.3. CI and operational support

Leak sources outside the backend:

- `curl -v`/`--trace` commands can print `Authorization` headers, cookies, and bodies.
- `gradle --debug`, environment dumps, `env`/`printenv`, and command-line args can expose secrets.
- Browser DevTools screenshots, network captures, and error-tracking attachments.
- Tickets or chats containing "show me the full request" and unscrubbed HAR files.
- Container crash dumps, heap dumps, and remote diagnostic snapshots can hold credentials in RAM.

Use only **test credentials/canaries** for debugging, restrict access, and establish scrubbing procedures before sharing artifacts. A file named `debug.log` is still a log and needs the same protection/retention as any other log.

## 12. If a secret is discovered in logs: incident response

When a real password, API key, token, or recovery code appears in logs, do not just edit the log statement and call it done:

1. **Stop the leak source** or isolate the leaking route/filter without destroying needed forensic evidence.
2. **Classify the secret**: access token, refresh token, session ID, API key, password, recovery code, reset token, private key; determine affected systems and privilege scope.
3. **Revoke/rotate affected secrets**: revoke sessions/refresh tokens, rotate API keys/client secrets, invalidate recovery/reset codes, force password resets where appropriate.
4. **Scope time window and blast radius**: node logs, proxies, collectors, APM, alerts, backups, shared tickets; check who had access and look for abuse signs.
5. **Restrict access to logs and copies** during investigation; coordinate with security/legal per procedure.
6. **Handle copies per retention, legal, and evidence-preservation policies**; never delete recklessly mid-investigation.
7. **Fix at the root**, add canary tests to prevent recurrence; audit logging configs and release pipelines.
8. **Notify and post-mortem**: assign ownership, analyze root cause, update runbooks, and decide breach notifications per applicable regulations.

**Principle:** if an API key appeared in logs readable by multiple people, treat it as a potentially compromised credential; merely "hiding the line on a dashboard" does not make the old API key safe again.

### Response checklist by secret type

| Secret type | Priority action |
| --- | --- |
| Login password | Reset/rotate password per risk, check reuse and anomalous sessions |
| Access token | Revoke if supported or block related session; monitor until expiry |
| Refresh token | Revoke token family/session per OAuth policy |
| Session cookie | Invalidate session server-side; review cookie rotation policy |
| API key/client secret | Rotate and replace across workloads using the key; monitor unusual calls |
| Recovery/backup code | Invalidate exposed codes, issue a new set via a secure authenticated flow |
| Password reset/OTT token | Invalidate/block consumption, reissue via trusted channel |
| Private key/signing key | Evaluate key rotation, trust distribution, and impact on signed certs/tokens |

Exact actions depend on each token type's revocability and issuance architecture. Never claim a live stateless JWT can be revoked instantaneously if the system lacks a denylist, token-versioning, issuer key rotation, or equivalent mechanism.

## 13. Mandatory QA matrix

| ID | Test case | Passing criterion |
| --- | --- | --- |
| S01 | Login with canary password, both success and failure | Password never appears in app logs, proxies, or APM |
| S02 | Canary Bearer access token via `Authorization` | No raw token/JWT in any log |
| S03 | API key via `X-API-Key`/body | Key never leaked, including outbound client debug |
| S04 | Refresh token/opaque token | Not leaked in token endpoint, audit, or response logs |
| S05 | Rejected recovery code or OTP | Logs only `RECOVERY_REDEEM_FAILED`/category code |
| S06 | Test reset token in URL query | Never appears in access logs/traces/referrers |
| S07 | Reset token in URL path | Raw path not logged; logs only route template/category |
| S08 | Session ID in `Cookie` and `Set-Cookie` | Session identifier or cookie-bearing response headers not logged |
| S09 | `LoginRequest.toString()`/DTO record | Never invoked by loggers in real code |
| S10 | Bean Validation failure | `getRejectedValue()` absent from errors/logs |
| S11 | Spring MVC DEBUG/TRACE | `log-request-details` disabled and sensitive requests unlogged |
| S12 | `CommonsRequestLoggingFilter` | Captures no headers/body/query; inspect remaining URI path |
| S13 | Nginx/Gateway access logs | Never writes `$request`/`$request_uri` holding secrets |
| S14 | Security exception with strange input | Raw message/stack with credentials not logged |
| S15 | HTTP client request/response to IdP | No `Authorization`/refresh token in wire logs |
| S16 | MDC/baggage/trace attributes | No tokens, keys, sessions, raw emails/passwords |
| S17 | Metric labels | Finite enums/categories only, no user input/high-cardinality secrets |
| S18 | CI test failure logs/reports | Does not print canary/raw payload when tests fail |
| S19 | Log deleted on one node but copied in collector | Retention, exports, and incident workflow cover all copies |
| S20 | Intentional canary injection into test filter | Detection suite genuinely catches the leak |
| S21 | Audit event after stripping secrets | Retains enough context: event, outcome, time, correlation ID, action |
| S22 | User-controlled request ID with newlines | No log injection, never inserted verbatim |
| S23 | Lowering production log levels | Does not blind suspicious-behavior monitoring |
| S24 | WebFlux/other microservices | Equivalent policy applied; never assume only MVC carries risk |

A single passing run of `SafeSecurityAuditTest` only guarantees **the tested logger**. Completing QA requires inspecting and collecting logs from **actually deployed components**, not merely asserting "this code doesn't call `log.debug`".

## 14. Common mistakes and fixes

| Mistake | Why it is dangerous | Right approach |
| --- | --- | --- |
| `log.info("request={}", dto)` | Record/Lombok `toString()` can include password/OTP | Log only event codes; avoid `toString` on sensitive DTOs |
| `log.warn("JWT={}", jwt)` | JWT carries claims/tokens that can leak | Log `TOKEN_INVALID` and a reason category |
| `log.debug("headers={}", headers)` | Includes `Authorization`, `Cookie`, `X-API-Key` | Do not log headers; if metadata is needed, pick a vetted allowlist |
| `log.error("{}", exception.getMessage())` | Message may contain URLs/tokens or raw input | Use allowlisted error codes; sanitize exception logging |
| `request.getQueryString()` in access logs | Magic links/reset tokens easily leak into logs | Use route categories, drop queries, avoid URL tokens |
| Setting `spring.mvc.log-request-details=true` | DEBUG/TRACE can print detailed requests | Keep `false`; test all filters/custom code |
| Enabling body logger truncated to 20 bytes | The leading slice can still be a secret | Do not capture sensitive bodies |
| Regex redaction in log collector as sole defense | Misses encodings and logs pre-redaction | Prevent at source and gateway; masking is secondary |
| Using token suffix/fingerprint for correlation by default | Can expose part of secret or act as tracking ID | Use server-side random IDs or vetted HMAC design |
| Returning raw exceptions in error responses | Can leak passwords/SQL/tokens to clients and logs | Return status + generic error code + server audit ID |
| Letting support view raw HAR files | Contains `Cookie`/`Authorization`/request bodies | Scrub/forbid credential uploads; use test canaries |
| Deleting local log and calling it done | Copies stay in collectors, backups, alerts, tickets | Run incident response and rotate/revoke secrets |
| Dropping security event logs to avoid leaks | Blinds attack detection and breaks audit compliance | Keep safe event/outcome logs without secrets |

## 15. Self-check

1. Why must passwords and recovery codes never appear in logs **even after they have been used**?
2. Can a validly signed JWT be logged for debugging? Why or why not?
3. Where in the Client → Nginx → Tomcat → Spring → APM chain can tokens leak even when controllers log nothing?
4. Why is logging raw `exception.getMessage()` sometimes riskier than logging a `LOGIN_REJECTED` code?
5. Why should `LoginRequest` declared as a Java `record` never be logged as a whole object?
6. Does `spring.mvc.log-request-details=false` automatically protect Nginx/custom filters/RestClient?
7. If a proxy strips queries yet still logs raw URI paths containing tokens, what risk remains?
8. What is the difference between "masking tokens with regex" and "never capturing tokens into logs at all"?
9. Does passing `SafeSecurityAuditTest` prove APM/collectors never receive credentials?
10. If a real refresh token is found in logs, is deleting that log entry enough?
11. Should session IDs or API keys be placed in MDC/metric tags for easier tracing?
12. Which fields can be logged to investigate brute force without printing passwords or tokens?

**Guiding answers:** (1) they remain sensitive data usable for replay/follow-on attacks across multiple log copies; (2) no, tokens remain credentials and carry claims; (3) every layer with access/request/trace logging; (4) messages can embed raw input; (5) auto-`toString` can print passwords; (6) no; (7) secrets in paths still leak; (8) preventing at source is stronger and limits spread; (9) no, the test only observes a specific logger; (10) no, rotate/revoke and investigate copies; (11) no; (12) event, outcome, timestamp, error code, server correlation ID, and vetted metadata.

## 16. Acceptance checklist

- [ ] No `password`/`currentPassword`/`newPassword`, TOTP, `recoveryCode`, or reset tokens in app/access/APM logs.
- [ ] No raw `Authorization`/`Cookie`/`Set-Cookie`/`X-API-Key` values in logs.
- [ ] No full or merely "Base64-encoded" JWTs/opaque tokens/session IDs/keys/secrets/hashes written to logs.
- [ ] Controllers/Services/Filters/exception handlers never log DTOs, `Authentication`, `SecurityContext`, or raw requests.
- [ ] Spring MVC `log-request-details=false`; generic request logging filters capture no bodies/headers/queries on sensitive flows.
- [ ] Gateways/proxies never log queries, token-bearing paths, or sensitive request/response headers.
- [ ] MDC, traces, metrics, tags, APM, and error tracking contain no credentials.
- [ ] Audit event allowlist designed with outcomes/codes and server-generated correlation IDs.
- [ ] Log retention, access control, and encryption/tamper protection meet policy.
- [ ] Canary tests verify both app and infrastructure deployments; negative controls catch leaks.
- [ ] Playbooks exist to revoke/rotate credentials, handle log copies, and report incidents.
- [ ] Sufficient failed/accepted logins, access denials, key rotations, and account recoveries remain logged for attack detection.

## 17. References

- [OWASP Logging Cheat Sheet — Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Sensitive Data Exposure / Security Logging Testing](https://owasp.github.io/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management/02-Application_Platform_Configuration)
- [Spring Framework 6.2 — MVC Logging, Sensitive Data](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/logging.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework 6.2 — AbstractRequestLoggingFilter API](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/filter/AbstractRequestLoggingFilter.html)
- [Spring Security 6.5 — Form Login and AuthenticationFailureHandler](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — HTTP Exchanges](https://docs.spring.io/spring-boot/reference/actuator/http-exchanges.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
