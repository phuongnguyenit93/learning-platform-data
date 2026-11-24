# Controlling DEBUG, TRACE Logs, and Sensitive Data During Spring Security Incident Investigations

## 1. Objective: Investigating Failures Without Creating Another Leak

When a Spring Security application hits "valid password still fails to log in", unexpected HTTP 401/403 responses, redirect loops, or JWT/LDAP verification errors, many teams' first reflex is switching log levels from `INFO` to `DEBUG` or `TRACE`. That quickly surfaces filter chains, authentication managers, CSRF, and authorization decisions. Yet **logs are a data store**: enabling overly broad logging can write session cookies, Bearer tokens, passwords, OTP codes, API keys, session IDs, emails, URL parameters, and sensitive stack traces into consoles, files, cloud logging, or monitoring platforms.

**This Operations topic requires balancing two goals:**

1. **Observability:** knowing which filters a request traversed, why authentication/authorization failed, and whether sessions/IdPs/DBs had errors.
2. **Data minimization:** recording only **approved** events, outcome codes, and metadata, never raw credentials, tokens, or user-supplied payloads.

Rule of thumb: **DEBUG/TRACE are not safe by default**; follow the priority order **metrics and minimal audit events → structured application logs → logger-specific timeboxed DEBUG → TRACE only in isolated environments after risk review**. Turning on DEBUG is never an excuse to bypass data security policies.

**Scope:** Spring Boot **3.5.x**, Spring Security **6.5.x**, Java **17+**, Servlet apps; parts apply to Spring Security 7 or WebFlux, though class/logger names, verbosity, and filter chains must be verified against the exact version. Includes runnable Maven/Java examples, JUnit + Logback log tests, a plain Java allowlist demo, and an incident runbook.

## 2. Distinguishing Log Levels and Debug Modes

| Level | What to Log | Risk If Applied Too Broadly |
| --- | --- | --- |
| `ERROR` | Service failures needing intervention, uncompletable operations | Stack traces/messages may contain secrets |
| `WARN` | Anomalous events, meaningful authentication rejections | PII, username enumeration, attacker-induced noise |
| `INFO` | Standardized audits, operational state, critical config changes | Excessive volume or over-retention |
| `DEBUG` | Filter paths, config decisions, diagnostic flow details | URLs, internal reasons, identities, or context |
| `TRACE` | Finer library/framework execution steps | Huge log volume; sensitive data depending on logger |

**Log level is not a sensitivity label.** A developer can accidentally log a password at `INFO`, while a framework `TRACE` log might print only a class name. Always evaluate the **actual content** emitted by each logger and version in use.

### 2.1. Four Logging Switches That Are Often Confused

| Switch | Meaning | Recommendation |
| --- | --- | --- |
| `logging.level.org.springframework.security=DEBUG` | Raises level for the entire Spring Security package | Use only in labs or scoped incidents |
| `logging.level.org.springframework.security.web.FilterChainProxy=DEBUG` | Raises level for one filter-chain logger | Preferred narrow scope to trace chains |
| Spring Boot `--debug` / `debug=true` | Enables DEBUG for a **curated set** of Boot loggers, not every logger | Not equivalent to DEBUG on all packages |
| Spring Boot `--trace` / `trace=true` | Enables TRACE for a broader framework logger set | High risk and overhead; isolate to non-prod |
| `@EnableWebSecurity(debug = true)` | Enables Spring Security web filter debug infrastructure | **Never use in production**; can log sensitive request headers/parameters |

Spring Security docs warn that web debug infrastructure may display **request parameters and headers**, so use it only in development. `@EnableWebSecurity(debug=true)` is **different** from setting one specific logger to DEBUG; never treat them as interchangeable.

**Version note:** Spring Boot logging syntax uses properties/YAML, while which logger/class prints what depends on Spring Security, servlet container, and library versions. Always inspect sanitized output in a staging/mock environment before enabling in production.

## 3. Why Authentication Logs Easily Leak Secrets

A login or API request can carry:

~~~http
POST /login HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=REDACTED
Authorization: Bearer REDACTED
Content-Type: application/x-www-form-urlencoded

username=user@example.test&password=REDACTED&_csrf=REDACTED
~~~

This is an **illustrative request with masked data**. Logging requests verbatim duplicates secrets across:

- stdout/console and server log files;
- log shippers, container logs, and Kubernetes log collectors;
- APM/tracing/span attributes and exception trackers;
- proxies, load balancers, and WAF/access logs;
- message brokers, SIEMs, data lakes, and cloud logging;
- tickets, screenshots, support chats, and CSV exports.

A secret can be copied repeatedly even after the app stops printing to console. Log access permissions are typically wider than database or secret-store permissions, so **never turn the logging system into a credential store**.

### 3.1. Never Log Verbatim

| Data Type | Examples | Recommended Replacement |
| --- | --- | --- |
| Password / PIN | Login password, current password, PIN | `reasonCategory=BAD_CREDENTIALS` |
| Bearer / OAuth tokens | JWT, opaque access token, refresh token, ID token | `tokenValidation=EXPIRED/INVALID_AUDIENCE` |
| Cookie / session identifiers | `Cookie`, `Set-Cookie`, `JSESSIONID` | `sessionPresent=true`, separate correlation ID |
| MFA / recovery secrets | OTP, TOTP seed, recovery code, magic-link token | `factorType=OTT`, `verificationResult=FAILED` |
| API keys / client secrets | `X-API-Key`, `client_secret` | Classified `clientType=service` |
| CSRF / anti-forgery values | `_csrf`, `X-CSRF-TOKEN`, `XSRF-TOKEN` | `csrfResult=MISSING/INVALID/VALID` |
| Private keys / keystores | PEM, private JWK material, HSM keys | Controlled `keyId`, signing status |
| PII | Full email, phone, address, national ID | Protected internal user reference, buckets/counters |
| Secret-bearing URLs | `/reset?token=...`, `/callback?code=...` | Route template `/reset`, `/callback` |
| `Authentication` objects | `Authentication.toString()`, `getCredentials()`, `getDetails()` | Event type, policy outcome, `principalKnown` boolean |
| HTTP bodies / SQL bind values | Login JSON, `password=...`, query params | Allowlisted route/method/status |

Fields like IP, User-Agent, account ID, device identifier, error message, tenant ID, and exact URL **can also be PII or abused**; never assume they are safe merely because they are not passwords.

The OWASP Logging Cheat Sheet recommends omitting, masking, sanitizing, hashing, or encrypting session identifiers, access tokens, passwords, encryption keys, and sensitive PII. Often **not logging** beats logging and trying to scrub afterward.

### 3.2. Why Regex "Replace password=..." Is Insufficient

Secrets can appear in:

- Differently cased headers: `authorization`, `Proxy-Authorization`, or custom headers.
- Nested JSON, XML, multipart forms, and GraphQL variables.
- Query strings or URL-encoded/double-encoded payloads.
- Exception messages, request wrappers, and debug `toString` output.
- Parameters holding secrets under names other than `password`, e.g., `credential`, `secret`, `otp`, `code`.
- Session/trace attributes from third-party libraries unseen by regexes.

**Prefer building logs from an explicit field allowlist** and **never include request/response bodies in messages**. Output regex masking should be **defense in depth**, never the sole boundary.

## 4. Spring Security Loggers Worth Knowing During Investigations

Spring Security exposes helpful loggers to narrow down issues:

| Logger / Component | Investigation Question | Caution |
| --- | --- | --- |
| `org.springframework.security.web.FilterChainProxy` | Which security filter chain handles the request? | May log request paths |
| `org.springframework.security.web.DefaultSecurityFilterChain` | Which filters were wired at startup? | Does not prove filters run on every request |
| `org.springframework.security.web.access.ExceptionTranslationFilter` | Why was the entry point / AccessDeniedHandler invoked? | Messages/URLs vary by version |
| `org.springframework.security.web.csrf.CsrfFilter` | Missing/bad CSRF or matched elsewhere? | Never log raw CSRF tokens |
| `org.springframework.security.authentication.ProviderManager` | Which authentication provider handled the request? | Never log full `Authentication` |
| `org.springframework.security.web.authentication` | Form login success/failure flows and handlers | May log URL/exception info |
| `org.springframework.security.oauth2.server.resource` | Bearer/JWT validation flow | **Never log raw tokens/JWT claims** |
| `org.springframework.security.saml2` | SAML login validation | XML assertions contain identity/claims |
| `org.springframework.security.ldap` | LDAP/AD binds and user lookups | DNs, endpoints, and usernames can be sensitive |

Logger names and exact message counts **are not a fixed API**. Some loggers print nothing at DEBUG for a given path; do not flip everything to TRACE just because "no log appeared" without checking the filter chain, code path, and environment.

### 4.1. Reading the Startup Filter List

At DEBUG for `DefaultSecurityFilterChain`, Spring Security may output:

~~~text
Will secure any request with [
  SecurityContextHolderFilter,
  CsrfFilter,
  LogoutFilter,
  UsernamePasswordAuthenticationFilter,
  ExceptionTranslationFilter,
  AuthorizationFilter
]
~~~

This is an **abbreviated example** (other filters depend on config). It helps spot missing or misordered filters like `CsrfFilter`, `BasicAuthenticationFilter`, or a custom filter.

Yet **seeing filters in a chain does not prove a request matched that chain** when multiple `SecurityFilterChain`s exist. Cross-check matchers, HTTP methods/route templates, status codes, and integration tests.

### 4.2. How Can DEBUG Help on HTTP 401/403?

Typical situations:

- **401 Unauthorized:** missing valid authentication proof, Bearer token failed validation, wrong HTTP Basic password, or entry point triggered.
- **403 Forbidden:** missing authority/role or CSRF rejected; do not guess from status code alone.
- **302 `/login`:** unauthenticated web request redirected to form login; not inherently an error.
- **Redirect loop:** session cookie not sent, context not persisted, wrong saved request/host/scheme.
- **LDAP/IdP timeout:** service/provider failure; do not turn every failure into `BadCredentialsException`.

Log **reason categories** and **security decision outcomes** rather than `exception.toString()` or raw requests.

## 5. Minimum Logging Policy by Environment

Illustrative policy:

| Environment | Default Level | During Investigation | Conditions |
| --- | --- | --- | --- |
| Unit/Local | INFO, per-class DEBUG | Short-lived DEBUG/TRACE with synthetic data | Never use real secrets |
| CI/Integration | INFO + event categories | Conditional DEBUG on failing tests | Artifacts/logs reviewed and redacted |
| Staging | INFO | Narrow-logger DEBUG with approval/TTL | Prefer synthetic data |
| Production | INFO/WARN/ERROR | **Controlled** DEBUG; TRACE strictly exceptional | Owner, goal, timebox, RBAC, rollback |
| Incident handling | Baseline audits always on | Raise per-logger level for bounded window | Watch leaks, volume, rollback, retention |

**Never** leave `logging.level.root=TRACE` or `logging.level.org.springframework=TRACE` enabled permanently in production. It inflates cost, latency, exposure risk, and noise hiding real signals.

### 5.1. Default `application.properties`

~~~properties
spring.application.name=safe-auth-log-lab
server.port=8080

# Safer baseline for labs and new applications.
logging.level.root=INFO
logging.level.org.springframework.security=INFO
logging.level.demo.audit=INFO

# Do not enable Boot --trace/--debug globally.
debug=false
trace=false
~~~

In production, `INFO` **does not guarantee clean logs automatically**. Application loggers still need allowlists, and third-party framework logs must be reviewed before enabling around real data.

### 5.2. Raising Only One Specific Logger

Create `src/main/resources/application-diagnostics.properties` strictly for the lab:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security.web.access.ExceptionTranslationFilter=DEBUG

# Do not enable TRACE across all of org.springframework.security.
# Do not use @EnableWebSecurity(debug = true).
~~~

Run locally:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=diagnostics
~~~

On Windows PowerShell or shells with different JVM/Maven flag handling, you can also run the built JAR:

~~~bash
java -jar target/safe-auth-log-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=diagnostics
~~~

This profile is **for testing with synthetic data**. In environments holding real data, pick loggers only after reviewing potential output and enforce automatic expiration.

## 6. Application-Layer Logging: Allowlisted Events

Example of a suitable audit record:

~~~json
{
  "event": "AUTH_FAILURE",
  "outcome": "DENIED",
  "reasonCategory": "BAD_CREDENTIALS",
  "authMethod": "HTTP_BASIC",
  "route": "/api/me",
  "correlationId": "opaque-internal-id",
  "timestamp": "2026-11-06T03:00:00Z"
}
~~~

This is an **illustrative schema JSON** with zero usernames, passwords, or tokens.

Never take `reasonCategory` or `authMethod` from client-submitted form values; derive them server-side from verified authentication/authorization results. `route` is the router-matched **path template**, not a raw URL with queries or identifier path segments. Generate `correlationId` server-side or strictly validate format/length across proxies.

### 6.1. Authentication Events Differ from HTTP Logs

Spring Security emits events such as:

- `AuthenticationSuccessEvent` when the manager authenticates successfully.
- `AuthenticationFailureBadCredentialsEvent` for bad credentials.
- `AuthenticationFailureLockedEvent` for locked accounts.
- Other `AbstractAuthenticationFailureEvent` subtypes depending on exception mappings.

**Authentication events are not HTTP request/access logs:** they fire on authentication attempts, not on every GET. For example, HTTP Basic may authenticate on every request, whereas session form login authenticates on submit; do not count events as active users.

A listener can log **event type, outcome, and safe category** without touching `event.getAuthentication().getCredentials()`. If a custom manager is not wired to `AuthenticationEventPublisher`, events may not fire; absence of events does not prove whether a user succeeded or failed.

### 6.2. Authorization and CSRF Events

Lacking `ROLE_ADMIN` when already authenticated is **authorization denied**, not a bad password. A POST missing CSRF is rejected by `CsrfFilter` **before** credentials reach `AuthenticationManager`. Maintain a clear taxonomy:

~~~text
AUTH_SUCCESS
AUTH_FAILURE / BAD_CREDENTIALS
AUTH_FAILURE / ACCOUNT_LOCKED
AUTH_FAILURE / PROVIDER_UNAVAILABLE
AUTHZ_DENIED / MISSING_AUTHORITY
CSRF_DENIED / MISSING_OR_INVALID
SESSION_EXPIRED
BEARER_DENIED / INVALID_SIGNATURE | EXPIRED | BAD_AUDIENCE
CONFIG_CHANGED / LOGGER_LEVEL
~~~

These codes are a **recommended application taxonomy**, not default event types emitted by every Spring Security version. For critical audit events, never rely solely on toggling framework DEBUG levels.

## 7. Runnable Example: Spring Boot 3.5 + Java 17 Logging Only Safe Audits

Example goals:

- Simple app with HTTP Basic and lab account `learner` / `lab-password`.
- `DefaultAuthenticationEventPublisher` auto-configured by Spring Boot in standard setups, supplying success/failure events.
- Listener logs only **constant event names and allowlisted reason codes**, never principals, passwords, tokens, session IDs, full `Authentication`, or exception messages.
- JUnit 5 suite using MockMvc + Logback `ListAppender` verifying **events appear** while **secrets do not leak**.
- Optional `diagnostics` profile raising DEBUG only for two Spring Security loggers in the lab.

HTTP Basic is used to exercise valid/invalid credentials cleanly in tests. **Never send HTTP Basic over unencrypted connections in production**; this localhost HTTP demo is purely educational. For form login, OAuth2, or LDAP, swap the auth mechanism while keeping the exact field-allowlist audit design.

### 7.1. Directory Layout

~~~text
safe-auth-log-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/audit/SafeAuthLogApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── application-diagnostics.properties
    └── test/
        └── java/demo/audit/SafeAuthLogTests.java
~~~

### 7.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>safe-auth-log-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

If using a newer Boot 3.5.x patch, keep the BOM-aligned Spring Security version rather than overriding `spring-security-core` down to a different branch.

### 7.3. Java Source: `SafeAuthLogApplication.java`

~~~java
package demo.audit;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeAuthLogApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeAuthLogApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("lab-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @RestController
    static class LabApi {
        @GetMapping("/health")
        String health() {
            return "ready";
        }

        @GetMapping("/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("user", authentication.getName());
        }
    }

    @Component
    static class SafeSecurityAudit {
        private static final Logger log =
            LoggerFactory.getLogger(SafeSecurityAudit.class);

        @EventListener
        void success(AuthenticationSuccessEvent event) {
            // Log only permitted info; do not record principal.
            log.info("event=AUTH_SUCCESS outcome=SUCCESS");
        }

        @EventListener
        void failure(AbstractAuthenticationFailureEvent event) {
            var error = event.getException();
            String category;

            if (error instanceof BadCredentialsException) {
                category = "BAD_CREDENTIALS";
            } else if (error instanceof LockedException) {
                category = "ACCOUNT_LOCKED";
            } else if (error instanceof AuthenticationServiceException) {
                category = "PROVIDER_ERROR";
            } else {
                category = "OTHER_AUTH_FAILURE";
            }

            // Never call toString/getMessage on Authentication,
            // password, exception, or HTTP request.
            log.warn("event=AUTH_FAILURE outcome=DENIED reason={}",
                category);
        }
    }
}
~~~

**Why is this safer than raw request logging?**

1. `SafeSecurityAudit` writes only **fixed constants** and one `reason` from an in-code category list.
2. The listener never touches `event.getAuthentication().getCredentials()`, `getDetails()`, `getPrincipal()`, or `event.getException().getMessage()`.
3. `BadCredentialsException` maps into a unified category so broadly readable logs never disclose "user does not exist" vs. wrong password.
4. `UserDetailsService` uses BCrypt for the lab without logging password hashes.
5. HTTP Basic still requires real HTTPS outside localhost; this example does not replace rate limiting, session policies, or production monitoring.

Standard Spring Boot setups provide `DefaultAuthenticationEventPublisher` if no custom publisher bean exists. If defining a custom `ProviderManager`, wire the publisher explicitly; otherwise listeners receive no events.

### 7.4. Configuration Files

`src/main/resources/application.properties`:

~~~properties
spring.application.name=safe-auth-log-lab
server.port=8080
logging.level.root=INFO
logging.level.org.springframework.security=INFO
logging.level.demo.audit=INFO
debug=false
trace=false
~~~

`src/main/resources/application-diagnostics.properties`:

~~~properties
# Use locally only with synthetic credentials; never configure in production.
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security.web.access.ExceptionTranslationFilter=DEBUG
~~~

Never enable `@EnableWebSecurity(debug=true)` or `logging.level.org.springframework=TRACE` since output can exceed safe boundaries.

### 7.5. JUnit Test Verifying Passwords, Usernames, and Bearer Tokens Are Not Logged

File `src/test/java/demo/audit/SafeAuthLogTests.java`:

~~~java
package demo.audit;

import java.util.stream.Collectors;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeAuthLogTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHealthNeedsNoCredentials() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk());
    }

    @Test
    void protectedEndpointWithoutCredentialsIsDenied()
            throws Exception {
        mvc.perform(get("/me")).andExpect(status().isUnauthorized());
    }

    @Test
    void auditLogShowsEventsButNotSecrets() throws Exception {
        Logger logger = (Logger) LoggerFactory.getLogger(
            SafeAuthLogApplication.SafeSecurityAudit.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        String marker = "wrong-password-SECRET-MARKER";
        String bearerMarker = "Bearer DO-NOT-LOG-THIS";

        try {
            mvc.perform(get("/me")
                    .with(httpBasic("learner", "lab-password")))
                .andExpect(status().isOk());

            mvc.perform(get("/me")
                    .with(httpBasic("learner", marker)))
                .andExpect(status().isUnauthorized());

            String recorded = appender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .collect(Collectors.joining("\n"));

            assertTrue(recorded.contains("event=AUTH_SUCCESS"));
            assertTrue(recorded.contains("event=AUTH_FAILURE"));
            assertTrue(recorded.contains("reason=BAD_CREDENTIALS"));

            assertFalse(recorded.contains(marker));
            assertFalse(recorded.contains("lab-password"));
            assertFalse(recorded.contains("learner"));
            assertFalse(recorded.contains(bearerMarker));
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
~~~

**What this test means:**

- Both HTTP Basic requests genuinely trigger the authentication flow rather than bypassing providers with `@WithMockUser`.
- `ListAppender` attaches only to the **`SafeSecurityAudit` logger**. It proves this listener emits no secrets; it **does not prove every other logger, reverse proxy, APM, or production appender is safe**.
- Intentional marker strings catch regressions if a future developer logs `event.getAuthentication()` or exception messages.
- Tests use synthetic lab credentials, no real accounts, and zero outbound Internet HTTP traffic.

Expand with static/dynamic scans of full app log files, ingress integration tests, Logback policies, and pipeline DLP checks before turning on production debugging.

### 7.6. Running the Demo

Inside the project with JDK 17+ and Maven:

~~~bash
mvn test
mvn spring-boot:run
~~~

Expected result with matching dependencies:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is **expected output**, not captured build logs; Maven also prints class names, timings, and startup diagnostics.

Test endpoints locally with curl:

~~~bash
curl -i http://localhost:8080/health
curl -i --user learner:lab-password http://localhost:8080/me
curl -i --user learner:wrong-password http://localhost:8080/me
~~~

Sample success body:

~~~json
{"user":"learner"}
~~~

The listener logs lines carrying:

~~~text
event=AUTH_SUCCESS outcome=SUCCESS
event=AUTH_FAILURE outcome=DENIED reason=BAD_CREDENTIALS
~~~

Spring Boot prepends timestamp, thread, logger, and level to each line. **Never copy raw logs containing HTTP headers/cookies/passwords into documentation.** With curl and Basic auth, passwords on the command line appear in shell history/process listings: use lab credentials only, never production secrets.

### 7.7. Enabling Diagnostics in a Local Lab

Run the local profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=diagnostics
~~~

Watch `FilterChainProxy` at DEBUG. Logs show which request entered which chain; **do not** expect or save raw request bodies. When done checking, turn off the profile and return to the `INFO` baseline.

**Do not conclude from this example's stdout that Spring Security can never leak tokens in other loggers/frameworks:** safe audit listeners must pair with stack-wide controls.

## 8. Plain Java 17: Allowlist Instead of Redacting Request Bodies

This Java program runs **without Spring** to illustrate building logs solely from trusted data. File `SafeAuditLineDemo.java`:

~~~java
public class SafeAuditLineDemo {

    record SafeAuditLine(String event,
                         String outcome,
                         String reason,
                         String requestId) {

        String encode() {
            return "event=" + event
                + " outcome=" + outcome
                + " reason=" + reason
                + " requestId=" + requestId;
        }
    }

    public static void main(String[] args) {
        String rawPassword = "PRIVATE-PASSWORD-DO-NOT-LOG";
        String rawToken = "Bearer PRIVATE-TOKEN-DO-NOT-LOG";

        SafeAuditLine audit = new SafeAuditLine(
            "AUTH_FAILURE", "DENIED", "BAD_CREDENTIALS", "req-42");

        String output = audit.encode();
        System.out.println(output);
        System.out.println("leaked=" +
            (output.contains(rawPassword) || output.contains(rawToken)));
    }
}
~~~

Run:

~~~bash
javac --release 17 SafeAuditLineDemo.java
java SafeAuditLineDemo
~~~

**Exact stdout:**

~~~text
event=AUTH_FAILURE outcome=DENIED reason=BAD_CREDENTIALS requestId=req-42
leaked=false
~~~

Lesson: sensitive values **never enter the audit record**, instead of logging everything and applying regex scrubbing. In real apps, `requestId` is server-generated via UUID/controlled trace context; never accept arbitrary client header strings, preventing log injection and cardinality abuse.

**Example scope:** fields are constants set by code. When constructing audit records from untrusted values, validate/encode and cap lengths so CRLF payloads cannot forge log lines.

## 9. Actuator Loggers: Changing Levels at Runtime Without Config Edits

Spring Boot Actuator exposes `/actuator/loggers` to inspect and (when authorized) adjust log levels at runtime. Example request body:

~~~json
{"configuredLevel": "DEBUG"}
~~~

Posting to a specific logger endpoint (with authentication/authorization and CSRF/network controls) switches it to DEBUG. Reset the configured level with:

~~~json
{"configuredLevel": null}
~~~

**Important:** an HTTP POST altering log config is a **sensitive administrative action**. Never expose `/actuator/loggers/**` anonymously or expose all Actuator endpoints via `include=*` in production.

### 9.1. If Adding Actuator

In Maven, add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

This is a **dependency snippet**, not automatically included in section 7's demo. By default Spring Boot exposes only `health` over HTTP; using `loggers` requires configuring both exposure **and** access/security per policy. Conceptual policy example:

~~~properties
# Configure only on a controlled management interface.
management.endpoints.web.exposure.include=health,loggers

# Never expose management endpoints directly to the Internet.
# Use authn + OPS role, network allowlists, TLS, and auditing.
~~~

If the app defines a custom `SecurityFilterChain`, Boot Security auto-config may no longer protect Actuator endpoints unless explicitly matched. Enforce explicit authorization for management paths, ideally on a separate network/port with role restrictions. With cookie-based management UIs, POSTs changing logger levels still need CSRF protection; never disable CSRF just to make the call succeed.

### 9.2. Runbook for Changing Log Levels

Before enabling:

1. **Ticket/incident ID:** document failure, purpose, approver, service/replica/env.
2. **Data classification:** could this logger print headers, claims, request parameters, or PII?
3. **Scope:** prefer one class/logger or a single staging replica, avoiding root/global changes.
4. **Timebox:** e.g., 10–15 minutes per policy, with a named owner and rollback deadline.
5. **Access:** restrict who can read logs/Actuator and audit logger-level changes.
6. **Dry run:** test with synthetic data to verify log volume and zero secrets.
7. **Activate:** apply narrow DEBUG; watch status codes, latency, throughput, and disk/ingestion.
8. **Collect:** extract only **the minimal excerpt**, scrub secrets, and enforce retention.
9. **Rollback:** set `configuredLevel=null` or `INFO` baseline and verify effective level reverted.
10. **Post-incident:** record RCA, add regression tests, verify no sensitive logs propagated, close ticket.

Timeboxes must be **enforced by process/automation**; Actuator does not revert to `INFO` automatically just because a ticket said "15 minutes". Dynamic settings vanish on restart or get overwritten by config management, so record both desired and effective levels.

### 9.3. When Should You NOT Use Actuator for Debugging?

If endpoint protection and change auditing are not in place, **do not expose `loggers` merely for convenience**. Use controlled deployment-pipeline configuration changes rather than opening a high-privilege production API. Runtime log control is an operational tool—and also an avenue for attackers with admin access to try forcing secret logging.

## 10. Common Leak Locations Outside Spring Security Logs

Even when event listener code is clean, audit:

| Source | Specific Risk | Mitigation |
| --- | --- | --- |
| Servlet/access logs | Raw URIs/queries containing `token`, `code`, email | Log route template with query stripped |
| Reverse proxy/WAF | `Authorization`/`Cookie` or full request capture | Header allowlists, masking, retention |
| APM/tracing | URL queries, baggage, span attrs, errors | Attribute filtering, collector policies |
| HTTP client wire logging | HTTP bodies with passwords/client secrets | Disable wire/body logs, synthetic tests |
| Logback/Log4j patterns | MDC containing user/token/PII | Add only validated MDC fields |
| Hibernate SQL binder TRACE | Emails/password hashes/PII in bind vars | Disable SQL bind TRACE in production |
| OAuth2/OIDC clients | Authorization codes, state, ID tokens, SAML responses | Never log full callbacks/queries/assertions |
| JWT failure exceptions | Raw tokens in error context | Map errors to safe reason categories |
| Session debugging | `JSESSIONID` and session attributes | Log presence/state only |
| CSRF debugging | Raw CSRF tokens in request params | Log missing/invalid category only |
| Exception handlers | Stack traces/request bodies printed automatically | Sanitize causes/responses/logs |
| Actuator `env`/`configprops`/`heapdump` | Secrets and in-memory objects | Never expose carelessly; RBAC/network isolation |
| CI artifacts/support dumps | Tokens/credentials in test logs | Scan/redact and restrict access |

**Special caution:** OpenTelemetry/APM agents and log shippers may capture data **before appender masking runs**, so secure every collection point, not only Logback.

### 10.1. Correlation IDs and MDC

Correlation links related logs without printing session IDs. Best practice:

- Trusted server/edge generates random IDs or uses verified tracing IDs.
- Validate incoming IDs for length, character set, and trust boundary; never trust arbitrary `X-Request-ID` headers from the Internet.
- Log `correlationId` consistently across services with retention/role controls.
- With SLF4J MDC, always clear in `finally` so reused servlet threads never leak into subsequent requests.
- Never put raw principals, emails, or tokens into MDC or trace baggage; propagation spans multiple systems.

Example fragment:

~~~java
String requestId = java.util.UUID.randomUUID().toString();
org.slf4j.MDC.put("requestId", requestId);
try {
    // Continue processing inside filter/service.
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

**This is a code fragment**, not a complete Servlet Filter. In reactive stacks, thread-local MDC does not follow across threads automatically; use Reactor context/tracing integration.

## 11. Log Injection and Untrusted Input

If code logs directly:

~~~java
// ANTI-PATTERN: client-supplied username can contain CRLF.
log.warn("login failed for " + inputUsername);
~~~

A newline-containing string can forge fake log entries, tricking dashboards or parsers. Client-supplied fields also enable log flooding, high-cardinality metrics, and PII leaks.

Prefer:

- Server-inferred fixed categories/enums.
- Structured JSON logs with field-level encoding and size caps.
- No raw usernames in metric labels.
- When an investigation reference is needed, use an authorized internal ID/pseudonym per policy; HMAC pseudonymization still carries privacy risks and requires key management.
- Separate security event logs from framework debug logs with dedicated sinks, retention, and RBAC.
- Never make authn/authz decisions from a log event controllable by clients.

## 12. Incident Playbook: Investigating an "Unexplained 403"

### 12.1. Initial Collection Without Enabling TRACE

Suppose users report `POST /api/profile` returns 403.

1. Record timestamp, service, environment, HTTP method, **route template**, and sanitized correlation ID.
2. Check metrics and audit categories: `CSRF_DENIED`, `AUTHZ_DENIED`, or `AUTH_FAILURE`?
3. Check controller/filter chain matchers; for session auth, check whether session cookie was present (boolean) and CSRF token was valid (boolean) without logging values.
4. Check whether `SecurityContext` held an authenticated principal via a **flag** or approved internal ref; inspect role/authority categories **only if audit policy permits**.
5. For resource servers, check `issuer/audience/expiry/signature` validation categories without dumping the JWT.
6. If signals are still insufficient, enable DEBUG on one specific logger with an owner and timebox.

### 12.2. Escalating Levels Step by Step

Priority order:

~~~text
A. Baseline INFO + standardized audit events
B. DEBUG FilterChainProxy for filters/matchers
C. DEBUG ExceptionTranslationFilter/CsrfFilter when needed
D. DEBUG matching provider in a controlled environment
E. TRACE only after approval, with synthetic traffic/isolation
~~~

Step E is never the default. When real credentials are present, prefer **avoiding TRACE** and reproducing safely or adding category-level instrumentation.

### 12.3. Common Diagnostic Patterns

| Symptom | Signals to Collect | Never Collect |
| --- | --- | --- |
| Login form POST 403 | CSRF result, route, `sessionPresent` | CSRF token / password |
| Login form 302 loop | Session cookie flags, sanitized saved URL, context persistence | Raw `JSESSIONID` |
| OAuth JWT 401 | Reason category, issuer key-set status, clock skew bounds | Raw JWT, `Authorization` header |
| LDAP login failure | Provider availability, bind outcome category | Full DN / LDAP password |
| Admin endpoint 403 | Role/policy decision category, tenant access result | Full `Authentication` object |
| Session lost after login | Session store health, cookie path/domain, fixation event | Session values |
| SSO callback error | IdP state/nonce validation outcome | Authorization code / ID token |
| Flood of bad-password events | Counts bucketed by source/account risk | Password guesses, usernames as metric labels |

### 12.4. After Discovering a Secret Entered Logs

If a secret entered the logging pipeline:

1. **Stop the leak source** (roll back level, fix logger/handler).
2. **Classify data and scope:** which token type, whether still valid, which sinks hold it, and whether exported/downloaded.
3. **Revoke/rotate** credentials, refresh tokens, API keys, or session IDs per exposure severity.
4. **Restrict access** and shut off export paths while preserving forensic evidence per policy (never wipe blindly and break chain-of-custody).
5. **Purge copies** in log storage, backups, CI artifacts, and tickets per retention/redaction procedures and legal rules.
6. **Notify** security/privacy/legal teams and affected data subjects when required by policy or law.
7. **Add regression tests** banning credential fields, harden exporter/proxy guardrails, and review logging configs.
8. **Postmortem:** a log leak is a security incident, not merely "someone left DEBUG on".

## 13. Security QA Checklist for the Logging Pipeline

### 13.1. Log Levels and Configuration

- [ ] Default `INFO`/`WARN`/`ERROR`, no global `TRACE` in production.
- [ ] Spring Security web debug mode restricted strictly to development.
- [ ] Production `DEBUG`, if ever needed, scoped by logger, duration, blast radius, and owner.
- [ ] Logger changes via Actuator/config require authentication, authorization, auditing, and rollback.
- [ ] `/actuator/loggers`, `env`, `heapdump`, and trace endpoints never exposed publicly.
- [ ] Verify baseline/effective levels post-incident, including after restarts/redeploys.
- [ ] Monitor log volume, disk/ingestion rates, and login latency.

### 13.2. Data Minimization

- [ ] Never log raw passwords, PINs, OAuth tokens, refresh tokens, session IDs, Cookie/Set-Cookie, CSRF tokens, OTPs, or recovery codes.
- [ ] Never log raw `Authorization`, `Proxy-Authorization`, `X-API-Key`, or request bodies.
- [ ] Secret-bearing URLs/query strings stripped or replaced with route templates.
- [ ] Event logs emit only allowlisted fields, category enums, and safe correlation IDs.
- [ ] Stack traces/exception messages vetted before emission; never rely purely on regexes.
- [ ] Log fields enforce length/encoding checks against CRLF injection.
- [ ] Sink RBAC, retention limits, and encryption at rest/in transit enforced.
- [ ] Audited proxies, APMs, tracing, SQL bind loggers, CI artifacts, and support exports.

### 13.3. Investigability

- [ ] Clearly separates authentication failures, authorization denials, and CSRF denials.
- [ ] Correlation IDs never reuse session tokens as identifiers.
- [ ] Authentication event counts are never mistaken for active online users.
- [ ] Triage playbooks exist for 401, 403, 302 loops, token/JWK, LDAP, and sessions.
- [ ] Synthetic traffic exists to reproduce and verify DEBUG logs before touching production.
- [ ] Unit/integration tests confirm safe listeners emit zero secrets.
- [ ] Incident response plan exists for secret-in-logs leaks, including re-verification after fixes.

## 14. Common Mistakes and Fixes

| Mistake | Why It Is Dangerous/Wrong | Fix |
| --- | --- | --- |
| Enabling `logging.level.root=TRACE` | Prints every package, heavy PII/overhead | Target one narrow logger briefly |
| Enabling `@EnableWebSecurity(debug=true)` in prod | Can print request headers/parameters | Dev only with synthetic data |
| Assuming `--debug` sets DEBUG app-wide | Boot enables only selected loggers | Configure explicit logger levels |
| Logging `request.getHeader("Authorization")` | Leaks Bearer tokens | Log token validation outcome |
| Logging `Cookie`/`Set-Cookie` | Leaks `JSESSIONID`/sessions | Log `sessionPresent`/flags |
| Logging `Authentication.toString()` | May contain principal/details/credentials | Allowlist safe fields |
| Logging `exception.getMessage()` on all errors | Leaks provider/DB/IdP internals | Map to failure categories |
| Scrubbing only `password=...` | Misses JSON/headers/encoded tokens | Stop body logging, allowlist fields |
| Putting full emails in metric labels | PII leak, high cardinality, cost | Use buckets/aggregates/safe IDs |
| Trusting arbitrary `X-Forwarded-For` IPs | Attackers spoof investigation IPs | Trusted proxy chains |
| Exposing public `POST /actuator/loggers` | Attackers raise levels to harvest secrets | OPS role, network/TLS/CSRF, audit |
| Forgetting to roll back DEBUG post-incident | Sustains leaks and ingestion costs | Timeboxes/runbooks/automation |
| Assuming missing events mean auth didn't run | Custom manager lacks publisher wiring | Verify manager wiring |
| Testing only the app's Logback appender | Proxies/APMs can still leak | Scan end-to-end pipelines |
| Immediately deleting logs on token leak | Can destroy forensic evidence | Preserve/contain per incident policy |

## 15. Self-Check Questions

1. Why is setting `logging.level.org.springframework.security=TRACE` different from raising only `FilterChainProxy`?
2. Does Spring Boot `--debug` set every logger to DEBUG?
3. Why should Spring Security `@EnableWebSecurity(debug=true)` never be used in production?
4. Which headers must never be dumped into logs?
5. Should `JSESSIONID` and `XSRF-TOKEN` be treated as public log info?
6. Why can `Authentication.toString()` leak sensitive data?
7. How does OWASP advise handling session IDs, passwords, and access tokens before logging?
8. Is a regex deleting `password=...` sufficient for JSON or OAuth callbacks?
9. How does 401 differ from 403, and is a CSRF 403 bad credentials?
10. Why distinguish authentication events from authorization denials?
11. What advantages does logging only `reasonCategory` have over exception messages?
12. Why do username metric labels create PII and cardinality risks?
13. What controls does `/actuator/loggers` require?
14. Why must logger-level rollbacks have an explicit owner and deadline?
15. What does a Logback `ListAppender` debug test prove, and what does it not prove?
16. If a token log already reached a cloud collector, what additional copies must be handled?
17. Why should correlation IDs never be taken verbatim from untrusted headers?
18. When enabling TRACE to diagnose a wrong-audience JWT error, do you need to print the raw JWT?

**Conclusion:** DEBUG/TRACE are powerful diagnostic tools that can easily turn logs into a secret vault. The right design pairs **structured audits, field allowlists, `INFO` baselines, timeboxed/approved logger-specific DEBUG, Actuator/collector controls, rollbacks, and leak-prevention tests**. When troubleshooting Spring Security, look for **categorized authn/authz causes**, never raw passwords, tokens, or cookies.

## 16. Official Documentation and Security References

- [Spring Security 6.5 — Servlet Security Architecture and Logging](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Web Application Security namespace debug warning](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/namespace/http.html)
- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot 3.5 — Actuator Loggers](https://docs.spring.io/spring-boot/3.5/reference/actuator/loggers.html)
- [Spring Boot 3.5 — Actuator Endpoint Exposure and Access](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
