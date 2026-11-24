# Never Log Passwords, Bearer Tokens, Cookies, or Personal Data

## 1. Log Security Goal in Spring Security Servlet

A Spring MVC application needs logs to track errors, performance, authentication events, authorization decisions, and important changes. However, logs typically pass through many systems: JVM console, container stdout, files, collectors, APMs, SIEMs, dashboards, alerts, tickets, and backups. A single mistakenly logged sensitive value creates multiple copies outside the business database.

Principle: **log only fields that are truly necessary and explicitly permitted. Never log passwords, Bearer tokens, cookies, session IDs, or unnecessary personal data.** Prefer designing events around an allowlist rather than logging entire requests and trying to scrub them with regex.

This lesson applies to Java 17+, Spring Boot 3.x, and Spring Security 6.x on the Servlet stack. After this lesson, you will be able to classify sensitive data, design safe security audit events, prevent leaks through logging frameworks and HTTP middleware, write tests with MockMvc/Logback, and operate the entire pipeline from application to collector.

## 2. Why Are Logs Risky?

Credentials can allow another party to perform actions if stolen. For example, Bearer access tokens generally work purely by possessing a valid token; session cookies can represent an active logged-in session; passwords carry especially high risk due to password reuse.

| Data | Risk |
| --- | --- |
| Password, OTP, recovery code | Can enable account takeover |
| Bearer access/refresh token | Can be replayed within its valid scope/lifetime |
| Authorization: Basic | Base64 is only encoding, not encryption |
| Cookie, Set-Cookie, JSESSIONID | Can enable session hijacking |
| API key, client secret | Unauthorized access to APIs/services |
| Email, phone number, address | Phishing or privacy violation |
| JWT claims, customer ID, route | Can link to individuals or sensitive activity |
| Query, form data, file name | Can contain tokens, search terms, private information |

Logs generally have a wider audience and more storage locations than databases. A token can travel from a terminal into aggregators, screenshots, alerts, or tickets. **Masking data on a dashboard does not delete the original copy from collectors and backups.**

## 3. Leak Sources Go Beyond Application `log.info`

Sensitive data can be recorded at:

- Application loggers printing passwords, bodies, headers, queries, `Principal`, or `Authentication`.
- Spring Security `DEBUG`/`TRACE` or custom authentication event listeners printing full events.
- Servlet request logging filters configured to capture payloads or headers.
- HTTP client wire logging, interceptors, or exception reporting.
- Tomcat, Nginx, Envoy, ingress, and CDN/WAF access logs capturing raw URIs and queries.
- SQL logging with bind parameters containing user data.
- APM, tracing, span attributes, exception events, MDC, and baggage.
- CI test reports, consoles, support tickets, exports, and alerts.

Fixing only controller code is not enough. Every layer that generates or forwards logs must be inspected.

~~~text
HTTP client
    |
    v
CDN / gateway / ingress
    |
    v
Servlet container
    |
    v
Spring Security filters -> Spring MVC controller/service
    |
    +--> application logs
    +--> exception reporter
    +--> APM and traces
    |
    v
log collector -> storage -> dashboard / alert / backup
~~~

At each step, ask: when is data captured, who can view it, where can it be exported, how long is it retained, and how is deletion handled when needed?

## 4. Which Fields Must Never Be Logged?

**Credentials and tokens to exclude unconditionally by default:** `password`, `passwordConfirmation`, `OTP`, `recovery code`, `MFA secret`, `reset token`, `API key`, `private key`, `access token`, `refresh token`, `client secret`, `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `JSESSIONID`.

**Never serialize whole objects:** `HttpServletRequest`, `HttpHeaders`, `Authentication`, `SecurityContext`, `Jwt`, `OAuth2User`, `UserDetails`, or unreviewed request/response DTOs. A `toString()` call may include password hashes, token claims, emails, authorities, or details. Never assume every implementation hides credentials.

**Personal data may be logged only when genuinely needed and controlled:** email, name, phone number, address, IP, user ID, tenant ID, subject, document ID, search terms, filename, HTTP `Referer`. UUIDs and email hashes can still link back to individuals.

**Exception messages are not safe by default.** Validation exceptions can include rejected values; SQL exceptions include queries; HTTP exceptions include URL queries; custom exceptions can concatenate raw input.

## 5. Code Patterns to Avoid

The code below shows examples of bugs, not patterns to copy:

~~~java
// WRONG: logging user-submitted password.
log.info("user={} password={}", username, submittedPassword);

// WRONG: logging a header containing credentials.
log.debug("Authorization={}",
    request.getHeader("Authorization"));

// WRONG: logging all headers or the entire request.
log.debug("Headers={}", headers);

// WRONG: body may contain secrets or PII.
log.info("Request body={}", body);

// WRONG: uncontrolled Authentication.toString().
log.info("Authentication={}", authentication);

// WRONG: raw URI/query may contain tokens or emails.
log.info("Request={} query={}",
    request.getRequestURI(), request.getQueryString());
~~~

Parameter substitution in logging frameworks helps formatting/performance, **not argument sanitization**. If an argument contains a Bearer token, the log still contains the token.

Regex filters looking for `password` or `Bearer` often miss new fields, custom headers, escaped JSON, URL encoding, Unicode, tokens in paths, or exceptions. Redaction can be a secondary layer, never the primary defense.

## 6. Using an Allowlist Schema for Operational Events

Instead of building events from raw requests, allow only a fixed set of fields:

~~~text
eventCode=AUTHENTICATION_REJECTED
outcomeCode=DENIED
reasonCode=BAD_CREDENTIALS
requestId=generated-by-server
httpStatus=401
routeTemplate=/api/login
durationMs=14
~~~

`eventCode`, `outcomeCode`, and `reasonCode` must be decided by server logic, never copied verbatim from client input. `requestId` should be server-generated or carefully validated per trust boundary; `routeTemplate` is safer than raw URLs in many cases.

Define log messages by an **allowed field set**:

~~~text
ALLOWED:
  eventCode, outcomeCode, reasonCode
  requestId, status, durationMs
  httpMethod, approvedRouteTemplate

DISALLOWED AS RAW VALUES:
  Authorization, Cookie, Set-Cookie
  requestBody, responseBody
  HttpServletRequest, Authentication, Jwt
  raw URL and query string
  uncontrolled exception message
~~~

Not every field in `ALLOWED` is needed on every log line. Log only what serves investigation and avoid increasing sensitivity unnecessarily.

## 7. Standalone Java 17: Formatter Accepting No Secrets

File `SafeEventDemo.java`:

~~~java
public class SafeEventDemo {

    enum EventCode {
        AUTHENTICATION_REJECTED,
        ACTION_ACCEPTED
    }

    enum Outcome {
        DENIED,
        SUCCESS
    }

    static String format(EventCode event, Outcome outcome) {
        return "event=" + event.name()
            + " outcome=" + outcome.name();
    }

    public static void main(String[] args) {
        System.out.println(
            format(
                EventCode.AUTHENTICATION_REJECTED,
                Outcome.DENIED
            )
        );
        System.out.println(
            format(
                EventCode.ACTION_ACCEPTED,
                Outcome.SUCCESS
            )
        );
    }
}
~~~

Run:

~~~bash
javac SafeEventDemo.java
java SafeEventDemo
~~~

Exact stdout:

~~~text
event=AUTHENTICATION_REJECTED outcome=DENIED
event=ACTION_ACCEPTED outcome=SUCCESS
~~~

The method accepts two enums rather than passwords, tokens, or request bodies. This illustrates a safe logging contract; real products should use proper logging frameworks and audit storage rather than treating `System.out` as an audit system.

## 8. Spring Boot 3 Sample: Request ID, Audit Event, and REST Endpoint

This Spring Boot 3.x project uses Java 17+ and the following dependencies in `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Files live in package `demo.safelog`. Running requires the Spring Boot plugin, dependency management, and the project's Gradle wrapper.

### 8.1. Application

File `src/main/java/demo/safelog/SafeLogApplication.java`:

~~~java
package demo.safelog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLogApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeLogApplication.class, args);
    }
}
~~~

### 8.2. RequestIdFilter: Server-Generated ID, Cleaning Up MDC

File `src/main/java/demo/safelog/RequestIdFilter.java`:

~~~java
package demo.safelog;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String id = UUID.randomUUID().toString();
        MDC.put("requestId", id);
        response.setHeader("X-Request-ID", id);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

The filter uses a server-generated UUID. Never put a client-sent `X-Request-ID` straight into MDC: a client could supply oversized strings or control characters to perform log injection. Clearing MDC in `finally` prevents IDs from bleeding between requests on reused servlet threads. With `@Async`, `Executor`, or async dispatch, handle propagation explicitly; MDC does not follow every thread automatically.

### 8.3. SafeAuditService: Accepting Only Enums

File `src/main/java/demo/safelog/SafeAuditService.java`:

~~~java
package demo.safelog;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;

@Service
public class SafeAuditService {

    private static final Logger log =
        LoggerFactory.getLogger(SafeAuditService.class);

    public enum EventCode {
        ACTION_ACCEPTED,
        AUTHENTICATION_REJECTED,
        AUTHORIZATION_DENIED
    }

    public enum OutcomeCode {
        SUCCESS,
        DENIED
    }

    public void record(EventCode event, OutcomeCode outcome) {
        log.info(
            "security_event={} outcome={} requestId={}",
            event.name(),
            outcome.name(),
            MDC.get("requestId")
        );
    }
}
~~~

The logger takes no `HttpServletRequest`, body, header, `Authentication`, or `Jwt` parameter. It accepts only predefined event enums and the server-generated request ID. You can switch `key=value` to JSON structured logging, yet the JSON encoder must still adhere to the allowed schema.

### 8.4. SecurityConfig Protecting the Controller

File `src/main/java/demo/safelog/SecurityConfig.java`:

~~~java
package demo.safelog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/health")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/api/actions")
                    .hasRole("OPERATOR")
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

The example configures endpoint authorization while keeping the default security filters provided by `HttpSecurity` for the framework version. The tests use `@WithMockUser` and `csrf()` to verify the controller and safe logging; **they do not test real passwords or JWT verification**. In a real deployment, choose and configure concrete authentication mechanisms (form, Basic, Resource Server, etc.) and matching session/CSRF policies. Never disable authentication or CSRF just to make tests pass.

### 8.5. Controller Without Logging Client-Sent Payloads

File `src/main/java/demo/safelog/ActionController.java`:

~~~java
package demo.safelog;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import demo.safelog.SafeAuditService.EventCode;
import demo.safelog.SafeAuditService.OutcomeCode;

@RestController
@RequestMapping("/api")
public class ActionController {

    private final SafeAuditService audit;

    public ActionController(SafeAuditService audit) {
        this.audit = audit;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @PostMapping("/actions")
    public ResponseEntity<Map<String, String>> action(
            @RequestBody ActionInput input) {

        // Do not pass input.label or the input object into logs.
        audit.record(EventCode.ACTION_ACCEPTED, OutcomeCode.SUCCESS);

        return ResponseEntity
            .status(HttpStatus.ACCEPTED)
            .body(Map.of("status", "accepted"));
    }

    public record ActionInput(String label) {}
}
~~~

The illustrative endpoint only acknowledges the request, with no database or queue. Do not treat HTTP 202 as a guarantee that work was persisted durably. Real products need validation, object-level permissions, and corresponding business logic.

### 8.6. Logging Pattern with Correlation ID

In `src/main/resources/application.properties`:

~~~properties
logging.level.root=INFO
logging.level.org.springframework.security=INFO
logging.pattern.console=%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level requestId=%X{requestId} %logger{36} - %msg%n
~~~

The pattern defines the message format and `requestId`; **it does not automatically mask secrets if another logger puts credentials into a message**.

## 9. Anti-Leak Testing with MockMvc and ListAppender

The test below puts **synthetic** markers in the request body and a custom header, then captures only the `SafeAuditService` logger. Never use real customer credentials.

File `src/test/java/demo/safelog/SafeLoggingTest.java`:

~~~java
package demo.safelog;

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
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeLoggingTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "test-user", roles = "OPERATOR")
    void loggerDoesNotPrintClientInput() throws Exception {
        Logger logger =
            (Logger) LoggerFactory.getLogger(SafeAuditService.class);

        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        try {
            mvc.perform(post("/api/actions")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"label\":\"SYNTHETIC_BODY_MARKER\"}")
                    .header("X-Debug-Marker", "SYNTHETIC_HEADER_MARKER"))
                .andExpect(status().isAccepted());

            String captured = appender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .collect(Collectors.joining("\n"));

            assertTrue(captured.contains("security_event=ACTION_ACCEPTED"));
            assertFalse(captured.contains("SYNTHETIC_BODY_MARKER"));
            assertFalse(captured.contains("SYNTHETIC_HEADER_MARKER"));
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
~~~

The test uses `SpringBootTest`, `AutoConfigureMockMvc`, Spring Security Test, and Logback `ListAppender`. `@WithMockUser` creates a mock `Authentication`; `csrf()` attaches a token for the MockMvc `POST` request.

**Limitation:** the appender only captures `SafeAuditService`, not Tomcat access logs, proxies, APMs, collectors, or other logging frameworks. Passing this test therefore only verifies the tested logger path—**it does not prove the entire pipeline is free of secrets**.

Run when the project has a Gradle wrapper:

~~~bash
./gradlew test --tests demo.safelog.SafeLoggingTest
~~~

Actual results depend on dependencies, versions, and configuration. If the logging backend is not Logback, use the matching test adapter.

## 10. Authentication, JWT, and Exception Messages

Spring Security `Authentication` can contain principals, credentials, authorities, and details. In Resource Servers, `Jwt` holds claims like `sub`, `email`, `aud`, `scopes`, and custom attributes. **Never log raw `Authentication`/`Jwt` objects**:

~~~java
// DO NOT:
log.info("Authentication={}", authentication);
log.debug("Context={}",
    SecurityContextHolder.getContext());
log.info("Claims={}", jwt.getClaims());
log.warn("Failure={}", exception.getMessage());
~~~

Log safe server-classified event codes and reason codes instead:

~~~text
security_event=AUTHENTICATION_REJECTED
reasonCode=INVALID_CREDENTIALS
outcome=DENIED
requestId=generated-by-server
~~~

An exception message can contain rejected input, SQL queries, paths, or headers. If stack traces are needed, inspect the message origin and restrict access to the error reporting system. Never print exception objects automatically without knowing what data may be attached.

## 11. Frequently Forgotten HTTP Headers, URLs, and Queries

Headers whose values must not be logged: `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, `X-Auth-Token`, `X-CSRF-TOKEN`, `X-XSRF-TOKEN`. `Referer`, `User-Agent`, `X-Forwarded-For`, and tracing baggage can also contain personal data or manipulated input.

Header names are case-insensitive; regexes checking only one casing can miss matches.

Examples of URLs carrying sensitive data:

~~~text
GET /users/alice@example.org
GET /reset?token=synthetic-value
GET /search?q=private-information
~~~

Prefer logging method/status and **route template** instead of raw URLs:

~~~text
method=GET route=/users/{userId} status=200
method=GET route=/reset status=400
method=GET route=/search status=200
~~~

Route templates are only available after MVC resolves a handler; unmatched requests can use an `UNKNOWN` category. Never truncate raw paths arbitrarily and assume PII is gone.

A proxy may log query strings before the request even reaches the JVM. Never put credentials in URLs in client designs.

## 12. Log Injection and Untrusted Input Sources

Custom headers, `User-Agent`, `Referer`, queries, and request bodies can contain newlines or control characters. If logged verbatim, an attacker can forge log entries resembling another event.

Countermeasures:

1. Prefer stable, server-generated event codes.
2. Never log unnecessary raw input.
3. When a client-supplied field must be recorded, enforce length and character-set limits.
4. Use a structured encoder with proper escaping.
5. Never execute shell/SQL commands or render unescaped HTML from logs.
6. Control log volume/cardinality to prevent data flooding.

Structured JSON enforces schema/escaping, yet **does not automatically encrypt or mask tokens** if a token is still passed into a field.

## 13. MDC and Tracing: Put Only Approved Metadata

MDC can propagate across many log lines. Never put `Authorization`, `Cookie`, or emails into MDC:

~~~java
// Better:
MDC.put("requestId", UUID.randomUUID().toString());

// Avoid:
MDC.put("cookie", request.getHeader("Cookie"));
MDC.put("authorization", request.getHeader("Authorization"));
~~~

OpenTelemetry/APMs can capture span attributes, baggage, headers, and exception events. Review their configurations separately. With `@Async`, `Executor`, or async processing, MDC does not automatically follow every thread; propagate only approved `requestId`/metadata via controlled context propagation.

## 14. Do Audits Need to Identify the Actor?

A role-change event may need to know who performed it. However, do not assume you must log emails, full names, or entire JWTs.

Consider internal IDs, `issuer+subject` when allowed by policy, or pseudonymous IDs protected by a separate mapping system. When using HMAC with a secret key to correlate events, manage the key properly and remember that pseudonymous identifiers can still link back to individuals.

**`SHA-256(email)` is not anonymous by itself**: emails are easy to dictionary-attack, and stable hashes still allow activity correlation.

Example of a data-minimized event:

~~~json
{
  "eventCode": "ROLE_CHANGED",
  "outcome": "SUCCESS",
  "requestId": "server-id",
  "actorRef": "approved-internal-reference",
  "targetType": "USER_ACCOUNT"
}
~~~

Security audits may have different RBAC and retention from operational logs, yet neither needs passwords or session cookies.

## 15. Spring Security Authentication Failure Events

Spring Security provides authentication event mechanisms depending on `AuthenticationEventPublisher` and manager configuration. A listener can log failure reasons using fixed codes without serializing the full event or exception.

Conceptual listener snippet:

~~~java
@EventListener
public void onFailure(AbstractAuthenticationFailureEvent ignored) {
    audit.record(
        SafeAuditService.EventCode.AUTHENTICATION_REJECTED,
        SafeAuditService.OutcomeCode.DENIED
    );
}
~~~

This is only an illustrative method placed in a Spring-managed component with matching imports/beans. Do not claim every `HttpFirewall`, Resource Server, or proxy error emits this event type. Test the actual event publisher and never blindly pass `getException().getMessage()` to logs.

## 16. Auditing the Entire Operational Pipeline

| Layer | What to verify |
| --- | --- |
| Frontend/mobile | Do not print tokens or passwords to console or crash reports |
| CDN, WAF, gateway | Request body/header capture, access logs |
| Reverse proxy/ingress | Raw URI/query, `Cookie`, `Authorization` |
| Servlet container | Access logs, request dump filters, error logs |
| Spring Security | `TRACE`/`DEBUG`, authentication events, custom filters |
| Application | Raw DTOs, `Authentication`/`Jwt`, request/response logging |
| HTTP clients | Wire logging, outbound `Authorization`/API keys |
| ORM/JDBC | SQL parameters containing PII |
| APM/Tracing | Span attributes, baggage, error context |
| Collector | Scrubbing/drop rules, exports, and backups |
| Dashboard | Access controls, downloads, sharing, retention |
| CI/Support | Test output, tickets/screenshots, raw diagnostic files |

A useful canary test sends fake markers in body, headers, query, and exceptions, then searches for them in log storage. **Seeing no marker in one test does not prove no form of sensitive data can leak.** Combine source review, collector configuration, and periodic checks.

## 17. Access Controls, Retention, and Incident Response

Logging policy must specify: purpose, allowed fields, authorized viewers, download/export rights, encryption, data destinations, retention period, and deletion procedures. No single retention period fits every organization; choose based on purpose, risk, contracts, and legal obligations.

If a secret is discovered in logs:

1. Stop the source with controlled code/config changes.
2. Identify the secret type, time window, and copies in collectors, dashboards, alerts, and backups.
3. Revoke/rotate/invalidate tokens, API keys, sessions, or credentials based on risk.
4. Restrict access to raw logs and audit view/export history.
5. Purge/delete copies per policy; dashboard masking is insufficient.
6. Assess security and personal-data notification obligations.
7. Monitor for anomalies using approved telemetry.
8. Add automated tests and review rules to prevent recurrence.

Never attach raw logs containing real credentials to general tickets. Share only sanitized excerpts; if evidence must be preserved, use a restricted investigation channel.

## 18. Misconceptions to Avoid

**"Logging at DEBUG is fine."** DEBUG can be turned on temporarily and forgotten; data still reaches storage.

**"JWTs are signed, so they can be logged."** A JWT is still a Bearer credential, and claims are readable.

**"Cookies are just identifiers."** A session ID can grant access to an active session.

**"Regex masking every `Bearer` string is enough."** Secrets can still live in custom headers, queries, bodies, exceptions, or other encodings.

**"Just skip logging the body."** Raw URIs, `Authorization`, `Cookie`, JDBC, and APM can still leak.

**"Hashed emails are no longer personal data."** Hashes can be correlated and dictionary-attacked.

**"ListAppender tests prove production is safe."** They only observe the tested logger, not proxies, containers, or collectors.

**"Structured JSON automatically sanitizes secrets."** JSON formatting does not remove sensitive data if code passes raw values.

**"Audits must record the full principal object."** Audits need minimal purpose-fit fields, never credentials.

## 19. Pre-Merge / Pre-Production Logging Checklist

- [ ] No passwords, OTPs, access/refresh tokens, API keys, or session cookies in log arguments.
- [ ] Never serialize `HttpServletRequest`, `HttpHeaders`, `Authentication`, `Jwt`, or `SecurityContext`.
- [ ] Raw request bodies, queries, paths, and exception messages are excluded from general loggers.
- [ ] Events, outcomes, and reason codes are decided server-side from an allowlist.
- [ ] Request IDs cannot be forged by clients; MDC is cleared in `finally`.
- [ ] No unnecessary secrets/PII in tracing attributes or baggage.
- [ ] Spring Security, HTTP wire, and SQL bind logging configurations have been checked.
- [ ] Gateway and Servlet access logs do not record raw credentials.
- [ ] Regression tests use fake markers across application loggers and pipelines.
- [ ] Audits have documented purpose, RBAC, encryption, retention, and export policies.
- [ ] A revoke/rotate and copy-cleanup runbook exists if a secret is logged by mistake.

## 20. Self-Check and Conclusion

**Question 1.** Why must `Authorization: Bearer` values never be logged?

Because it is a credential that can invoke APIs while valid. Logging it creates extra copies vulnerable to unauthorized access.

**Question 2.** If the application does not log request bodies, is it safe while the proxy logs raw URLs?

No. URLs/queries can carry emails, reset tokens, or private data; both proxy configuration and client design must be fixed.

**Question 3.** To know who changed a role, is logging the email mandatory?

No. You can use an internal ID or approved pseudonymous reference, with audit storage protected by appropriate access controls and retention.

**Question 4.** Why use an allowlist of event codes?

It reduces the chance raw request input reaches loggers, keeps schemas stable, and simplifies testing.

**Question 5.** Why inspect MDC, APM, and collectors too?

Because they can copy metadata, headers, or exception data automatically even when business loggers are safe.

**Conclusion:** In Spring Security Servlet, never log passwords, Bearer tokens, cookies, or unnecessary personal data in application logs, access logs, audits, exceptions, or traces. Record **safe event codes, outcomes, reason codes, route templates, and request IDs**, build allowlists at the source, test with synthetic markers, inspect the entire pipeline, and protect log storage with clear access controls, retention, and incident response.
