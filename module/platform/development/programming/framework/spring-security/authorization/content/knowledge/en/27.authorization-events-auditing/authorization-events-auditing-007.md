# Masking Personal Data, Tokens, and Sensitive Attributes in Logs

> **Context:** Spring Security – authorization, group **Events and Auditing**. This lesson explains how to design logs for investigating and observing authorization decisions without exposing personal data, credentials, or sensitive attributes. Practical examples use **Java 17, Spring Boot 3.5.6, Spring Security 6.5.x (Servlet/Spring MVC)**, and SLF4J/Logback.

## 1. Why Can Security Logs Become a Vulnerability?

Applications need to answer operational questions such as "Why was this account denied access to a report?" or "Is there a sudden spike in `DENIED` authorization decisions?". If raw requests, `Authentication` objects, or exceptions are written straight to logs, the observability system can inadvertently retain:

- `Authorization: Bearer eyJ...` — an access token that may still be valid; neither JWT headers/payloads nor signatures should appear in logs.
- `Authorization: Basic ...` — a Base64 string containing username/password; Base64 **is not secret encryption**.
- `Cookie`, `Set-Cookie`, `JSESSIONID`, refresh tokens, session IDs, API keys, OAuth authorization codes, passwords, OTPs, and recovery codes.
- Full names, emails, phone numbers, addresses, national/personal IDs, financial/health data, profile contents, or sensitive permission attributes.
- Query strings such as `?token=...`, paths with customer IDs/emails, HTTP bodies, multipart uploads, response bodies, and stack traces carrying input data.
- `Authentication.getCredentials()`, `SecurityContext`, `Principal`, `Jwt`, `OAuth2AuthenticationToken`, full `HttpServletRequest`, or business objects converted to strings via `toString()`.

Logs are routinely copied to container stdout, files, centralized aggregators, APM/traces, dashboards, alerts, tickets, and support tools. A secret that enters logs can persist across many copies, be read by many people, and outlive the request.

**Primary principle:** Collect only the *events needed for investigation* using an allowlisted set of fields right where logs are created. **Do not send sensitive data into the pipeline hoping a downstream filter will scrub everything.** "Masking" is a secondary measure; **data minimization + allowlisting** is the primary defense.

## 2. Distinguishing Protection Techniques

| Technique | Example | When appropriate | Limitations |
|---|---|---|---|
| **Omit (do not log)** | Do not emit `Authorization`, `Cookie`, email, or body fields | Default for secrets and data unnecessary for investigation | Cannot query data intentionally omitted |
| **Redaction** (strip value) | `access_token=[REDACTED]` | Need to know a *field was present* without its value | Must also inspect copies/aliases of the field |
| **Masking** (partial hide) | `m***@example.com` | Only when justified by business need and processing rights | The unmasked portion can still be **personal data**; never use for tokens or passwords |
| **Keyed pseudonymization** | `actor_ref=HMAC(k, stableId)` | Need to correlate events by the same subject without logging raw IDs | May still constitute personal-related data; keys/rotation/linkability must be managed |
| **Plain hash** | `SHA-256(email)` | Should not be used by default for emails/phones | Low-entropy inputs are easily brute-forced via dictionaries |
| **Truncation** | Limit a field to 200 characters | Prevent log injection and oversized logs | Not security: the first 200 characters can still hold an entire token |
| **Encryption at rest** | Encrypted log archive | Protects stored/in-transit data | Does not remove secret exposure to anyone with log read access |

For **passwords, access tokens, refresh tokens, OTPs, session IDs, and private keys**, the practical rule is **never log values**, not even the first/last few characters. If a diagnostic marker is needed, log only a bounded flag like `credential_present=true` when legitimately justified; usually even that flag is unnecessary.

A masked email such as `m***@example.com` can still identify a subject via domain, context, and other logs. Do not treat masked data as automatically "anonymous".

## 3. Determining Which Fields Are Permitted in Authorization Audits

Proposed compact, stable **authorization denial** event schema:

```json
{
  "event_type": "AUTHORIZATION_DENIED",
  "outcome": "DENIED",
  "resource": "REPORT_READ",
  "event_id": "6d1d6d4e-bc78-4759-82c1-4ba3e417f5bf"
}
```

This is an **application-defined illustrative schema**; Spring Security does not generate this JSON itself. Timestamps and service names are typically added by the logging system/collector. `event_id` is a random ID **for a single event**, not a session ID and not a replacement for a trace ID.

| Field | Include in logs? | Safe way to obtain |
|---|---|---|
| `event_type`, `outcome` | Yes | Constants defined in code, e.g., `AUTHORIZATION_DENIED` / `DENIED` |
| `resource` or `action` | Yes | Logical name from an enum/allowlist like `REPORT_READ`; **never use raw URLs** |
| `event_id` | Yes | Fresh `UUID.randomUUID()` per event |
| `request_id`/`trace_id` | Yes, if trusted | Server/tracing-generated or validated ID; do not blindly trust client headers |
| `actor_ref` | Only when needed for audits | Controlled surrogate ID or keyed HMAC; see section 8 |
| `http_method` | Yes, when needed | Accept only a bounded set such as GET/POST; do not concatenate unvalidated strings |
| `request_uri`, `query_string` | Do not log verbatim | Map to a logical route name, stripping queries and path identifiers |
| `Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key` | No | Drop the entire field/value |
| `Authentication`, `Principal`, `Jwt`, `SecurityContext` | Do not log as objects | Extract approved fields only; never `toString()` |
| `exception.getMessage()`, stack trace, `request.getParameterMap()` | Not by default | Use fixed error codes and error categories; enable details only under risk assessment and controls |

Example real request:

```http
GET /api/reports/customer-783?email=mai@example.com HTTP/1.1
Authorization: Bearer eyJhbGciOi...
Cookie: SESSION=opaque-secret
```

The log line **must not** copy the URI, query, or headers above. A more useful and safer log line:

```text
security_event=AUTHORIZATION_DENIED outcome=DENIED resource=REPORT_READ event_id=6d1d6d4e-bc78-4759-82c1-4ba3e417f5bf
```

The report ID `customer-783` and email **do not appear**. Yet you still know a report-read permission check was denied.

## 4. Logging Anti-Patterns to Avoid

### 4.1. Calling `toString()` on Data-Bearing Objects

**Wrong:**

```java
log.warn("Denied: request={} authentication={}", request, authentication);
log.debug("JWT claims={}", jwt.getClaims());
log.error("Permission denied for payload={}", command);
```

Because `toString()` or serializers of libraries, models, or proxies can include more fields than expected, including fields added in the future. You cannot declare a log safe merely because it once ran on harmless test data.

**Safer:**

```java
log.warn("security_event={} outcome={} resource={}",
        "AUTHORIZATION_DENIED", "DENIED", "REPORT_READ");
```

The three values above are defined in source code and unaffected by request inputs. In practice, provide a single audit service/helper accepting dedicated enums or records, rather than letting every controller invent its own log format.

### 4.2. Logging Full Headers, Bodies, and URLs

**Wrong:**

```java
log.info("uri={} query={} headers={}",
        request.getRequestURI(),
        request.getQueryString(),
        java.util.Collections.list(request.getHeaderNames()));
```

Even this bad snippet only logs header *names*; changing it to read *values* leaks secrets directly. Even URIs or header names can expose implementation details and sensitive information. Never deploy a filter that logs full requests/responses in production just to debug a 403.

**Safer:** map URLs to fixed resource codes like `REPORT_READ` based on known routes/endpoints. If paths are needed for measurement, use a **route template** such as `/api/reports/{reportId}` once sure the template comes from a trusted router; never use a URI populated with IDs.

### 4.3. Relying Solely on Pipeline-End Regex Masking

For example, a regex matching `Bearer ...` can miss tokens inside JSON bodies, URL encoding, SQL logs, renamed headers, nested objects, exceptions, or new logging formats. Email-masking regexes also fail to protect phone numbers, addresses, health attributes, or PII inside token claims.

Regexes can serve as a **second line of defense** at the sink, but they do not replace source-level allowlisting, log-level control, testing of log producers, and log read-access governance.

### 4.4. Assuming Parameterized Logging Automatically Hides Secrets

SLF4J's `log.info("token={}", token)` only defers formatting/reduces string-building overhead in some cases. It **does not encrypt, mask, or redact**. Likewise, structured JSON logging only ensures valid escaping/schema; it does not decide which fields are sensitive.

## 5. Proper Processing Flow in Spring Security

A good authorization audit sits where **authorization events** are created, then transforms the event into an approved schema:

```text
HTTP request (may contain tokens, PII, payload)
       |
       v
Spring Security authentication / authorization
       |
       +--> AuthorizationManager decides DENIED
       |
       +--> AuthorizationEventPublisher
       |        |
       |        +--> SpringAuthorizationEventPublisher
       |                 |
       |                 +--> AuthorizationDeniedEvent
       |                            |
       |                            +--> SafeAuditListener
       |                                     |
       |                                     +--> Determine resource from allowlist
       |                                     +--> Generate random event_id
       |                                     +--> Log fixed fields
       |
       +--> Handle HTTP 401 / 403 independently
```

In Spring Security Servlet, register an appropriate `AuthorizationEventPublisher` bean to receive `AuthorizationDeniedEvent`s from publisher-enabled checkpoints. By default, `SpringAuthorizationEventPublisher` focuses on **denied** events; do not assume every successful access emits an audit event. An `AccessDeniedHandler` builds 403 responses; it is not the best place to maintain a unified authorization audit schema.

**Scope warning:** Not every HTTP 403 goes through `AuthorizationEventPublisher` (for instance, CSRF failures or custom filters blocking directly). A single request may have multiple authorization checks and emit multiple events. If audit policy must cover every business command, add corresponding business audit checkpoints.

## 6. Spring Boot 3.5.6 Example: Logging Only Safe Metadata

The demo application uses HTTP Basic to create authenticated users with distinct roles. `{noop}` passwords are for demo purposes only; never use them in production. The listener **intentionally logs no username, token, header, URI, or request body**.

### 6.1. Project Structure

```text
safe-authorization-logs/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/safelogs/
│   ├── SafeLogsApplication.java
│   ├── SecurityConfig.java
│   ├── ReportController.java
│   └── SafeAuthorizationAuditListener.java
└── src/test/java/com/example/safelogs/
    └── SafeAuthorizationAuditTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>safe-authorization-logs</artifactId>
    <version>1.0.0</version>
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
```

`src/main/resources/application.properties`:

```properties
spring.application.name=safe-authorization-logs
logging.level.root=INFO
logging.level.org.springframework.security=INFO
logging.level.org.springframework.web=INFO
spring.mvc.log-request-details=false
```

The settings above reduce risky verbosity from default framework loggers. **This is not a global leak filter**: application loggers, JDBC/ORM, HTTP clients, reverse proxies, tracing, and APM agents each have independent policies. Never set `logging.level.org.springframework.security=TRACE` or enable request-detail/body logging in production just to diagnose a 403.

### 6.2. Main Application

`src/main/java/com/example/safelogs/SafeLogsApplication.java`:

```java
package com.example.safelogs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLogsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeLogsApplication.class, args);
    }
}
```

### 6.3. Authorization and Event Publisher Configuration

`src/main/java/com/example/safelogs/SecurityConfig.java`:

```java
package com.example.safelogs;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher events) {
        return new SpringAuthorizationEventPublisher(events);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/reports/**").hasRole("AUDITOR")
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        var analyst = User.withUsername("analyst")
                .password("{noop}analyst123")
                .roles("ANALYST")
                .build();
        var auditor = User.withUsername("auditor")
                .password("{noop}auditor123")
                .roles("AUDITOR")
                .build();
        return new InMemoryUserDetailsManager(analyst, auditor);
    }
}
```

`hasRole("AUDITOR")` requires the `ROLE_AUDITOR` authority; `roles("AUDITOR")` creates that authority. `analyst` is authenticated but lacks the role, so they receive 403. The `AuthorizationEventPublisher` bean allows authorization to publish events into Spring's event infrastructure; keeping request values out of the logger is the **listener's responsibility**.

### 6.4. Controller

`src/main/java/com/example/safelogs/ReportController.java`:

```java
package com.example.safelogs;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    @GetMapping("/api/reports/{reportId}")
    public Map<String, String> report(@PathVariable String reportId) {
        return Map.of("status", "ready");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile() {
        return Map.of("status", "visible");
    }
}
```

`reportId` may be a customer identifier; the controller accepts it solely to demonstrate that **the path variable exists yet will not enter the audit log**. The security filter rule blocks the call before the method runs when permissions are missing.

### 6.5. Listener Logging Only Constants and Event Codes

`src/main/java/com/example/safelogs/SafeAuthorizationAuditListener.java`:

```java
package com.example.safelogs;

import jakarta.servlet.http.HttpServletRequest;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.stereotype.Component;

@Component
public class SafeAuthorizationAuditListener {
    private static final Logger log =
            LoggerFactory.getLogger(SafeAuthorizationAuditListener.class);

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> event) {
        String resource = resourceCategory(event.getObject());
        String eventId = UUID.randomUUID().toString();

        log.warn("security_event=AUTHORIZATION_DENIED outcome=DENIED " +
                 "resource={} event_id={}", resource, eventId);
    }

    private String resourceCategory(Object securedObject) {
        if (securedObject instanceof HttpServletRequest request) {
            // Read URI only to CLASSIFY in memory; never log the URI.
            String relativePath = request.getRequestURI()
                    .substring(request.getContextPath().length());

            if ("GET".equals(request.getMethod())
                    && relativePath.startsWith("/api/reports/")) {
                return "REPORT_READ";
            }
        }
        return "OTHER_PROTECTED_RESOURCE";
    }
}
```

**Key points when reading this code:**

1. `@EventListener` receives `AuthorizationDeniedEvent<?>`. The value of `event.getObject()` **is not always a Servlet request**: in method security or custom publishers, it can be another object. All non-matching cases receive the fixed label `OTHER_PROTECTED_RESOURCE`.
2. `resourceCategory` inspects the URI **in memory** to classify the resource without outputting the URI, ID, query, or headers. In applications with many routes and context paths, map via official route metadata or domain action enums, and test those mappings thoroughly.
3. The log receives only two application-controlled variables: `resource` from a bounded set and a random `eventId`. No personal data or credentials from the request appear.
4. `eventId` is generated per event; it is **not** an idempotency key and not a session ID. To correlate multiple events for the same request, use a server-generated request/correlation ID with explicit lifecycle management.
5. The handler retains no references to `HttpServletRequest`, `Authentication`, or tokens for background processing. It never calls `toString()` on the event or exception.

Example log (actual UUID differs each run):

```text
security_event=AUTHORIZATION_DENIED outcome=DENIED resource=REPORT_READ event_id=6d1d6d4e-bc78-4759-82c1-4ba3e417f5bf
```

A logging system may prepend timestamp, thread, and logger name before the line above. The goal of the code is that **no** `reportId`, email, Bearer token, or cookie appears in the message produced by the listener.

### 6.6. Starting and Observing

In the directory containing `pom.xml`, with JDK 17+ and Maven 3.9+:

```bash
mvn spring-boot:run
```

In another terminal, test:

```bash
# Analyst lacks ROLE_AUDITOR. HTTP 403 + safe audit log.
curl -i -u analyst:analyst123 \
  'http://localhost:8080/api/reports/customer-783?email=mai%40example.com'

# Auditor has permission. HTTP 200, no denied audit.
curl -i -u auditor:auditor123 \
  'http://localhost:8080/api/reports/customer-783?email=mai%40example.com'

# Unauthenticated. HTTP Basic challenges for authentication: typically 401.
curl -i 'http://localhost:8080/api/reports/customer-783'
```

On Windows PowerShell, use `curl.exe` if `curl` is an alias. Windows shells also handle line continuation differently: you can collapse each command onto one line without Bash's `\` continuation character.

Expected status table:

| Call | HTTP | Log produced by listener |
|---|---|---|
| Analyst lacks permission to read report | **403** | `AUTHORIZATION_DENIED` with `resource=REPORT_READ` |
| Auditor has sufficient permission | **200** | No denied log emitted for a successful check |
| Unauthenticated | Typically **401** with HTTP Basic | Do not assume an exact count of authorization events; depends on the authentication/authorization flow |

Note that the 403 response and the log are **two related but independent flows**. A 403 from another source, such as CSRF, may not emit this event.

## 7. Testing That Secrets and Personal Data Do Not Leak

Tests should verify **a real request going through the filter chain**, then inspect the log output. Unit-testing a masking utility alone does not prove the application avoids logging sensitive data in another layer.

`src/test/java/com/example/safelogs/SafeAuthorizationAuditTest.java`:

```java
package com.example.safelogs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeAuthorizationAuditTest {
    @Autowired
    MockMvc mvc;

    @Test
    void deniedRequestLogsMetadataWithoutSecrets(CapturedOutput output)
            throws Exception {
        String jwtLike = "eyJhbGciOiJIUzI1NiJ9.sample.signature";
        String privateEmail = "mai@example.com";
        String privateReport = "customer-783";
        String privateCookie = "SESSION=secret-session-value";

        mvc.perform(get("/api/reports/" + privateReport)
                .with(user("analyst").roles("ANALYST"))
                .queryParam("email", privateEmail)
                .header("Authorization", "Bearer " + jwtLike)
                .header("Cookie", privateCookie))
            .andExpect(status().isForbidden());

        String logged = output.getAll();
        assertThat(logged)
            .contains("security_event=AUTHORIZATION_DENIED")
            .contains("resource=REPORT_READ")
            .doesNotContain(jwtLike)
            .doesNotContain(privateEmail)
            .doesNotContain(privateReport)
            .doesNotContain(privateCookie)
            .doesNotContain("secret-session-value");
    }

    @Test
    void authorizedUserCanReadWithoutDeniedLog(CapturedOutput output)
            throws Exception {
        mvc.perform(get("/api/reports/customer-783")
                .with(user("auditor").roles("AUDITOR")))
            .andExpect(status().isOk());

        assertThat(output.getAll())
            .doesNotContain("security_event=AUTHORIZATION_DENIED");
    }

    @Test
    void unauthenticatedRequestIsChallenged() throws Exception {
        mvc.perform(get("/api/reports/customer-783"))
            .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
mvn test
```

**Test explanation:**

- `with(user("analyst").roles("ANALYST"))` attaches authentication to MockMvc without sending a demo password; the `Authorization: Bearer ...` header is added as sensitive test data *to verify the listener does not log it*. This setup uses HTTP Basic without OAuth2 Resource Server enabled, so the Bearer header is not the demo's authentication mechanism.
- The denied test confirms 403, the audit marker, the logical resource name, and the **absence** of tokens, emails, path variables, or cookies in captured logs.
- The allowed test confirms 200 and no **denied** marker in the example's successful request.
- `CapturedOutput` captures the test process's console/output. It is **necessary but not sufficient** to declare the entire system leak-free: proxies, ingress, HTTP clients, APM, SQL loggers, sidecars, and external collectors may still capture data outside this scope.
- `doesNotContain(...)` assertions protect only the specific test fixtures. Expand fixtures to cover international emails/IDs, nested JSON, tokens in multiple locations, newline injection, URL encoding, and real log sources.

`@SpringBootTest` + `@AutoConfigureMockMvc` uses the application's security filter chain. Building `MockMvcBuilders.standaloneSetup(...)` without security filters does not verify authorization decisions.

## 8. When Audits Must Correlate by User

Omitting usernames/IDs completely in the demo is a safe choice for teaching the mechanism, but business audits may need to trace actions per account. In that case, **define the purpose, processing authority, and retention period** before adding an identifier.

One option is **keyed pseudonymization** over a **stable internal user ID**:

```text
stableInternalUserId
    |
    +--> HMAC-SHA256(secretKey, "audit:v1:" + stableInternalUserId)
                |
                +--> actor_ref = truncated digest of sufficient length (per policy)
```

- Use a high-entropy secret key managed in a secret manager/KMS; never store the key in source code, committed config, exceptions, or logs.
- Use **HMAC**, not plain `SHA-256(email)` because emails/phone numbers are easily guessed.
- Separate purposes with a domain prefix such as `audit:v1:`; clearly define key versions, rotation lifecycles, and the impact of key rotation on event correlation.
- Consider investigative scenarios requiring reversal of the surrogate back to the original account: only authorized systems/personnel may perform it; maintain a controlled mapping or workflow if truly required.
- A pseudonymized identifier can still be **personal data** under applicable context/regulations. Never label it absolute "anonymization".

In Java, the right primitive is `javax.crypto.Mac` with `HmacSHA256` and `javax.crypto.spec.SecretKeySpec`. Illustrative usage example (not a standalone program; `keyBytes` must be supplied securely from KMS/secret store):

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuditActorRef {
    private AuditActorRef() {}

    public static String of(String internalUserId, byte[] keyBytes) {
        if (internalUserId == null || internalUserId.isBlank()) {
            throw new IllegalArgumentException("Missing internal user ID");
        }
        if (keyBytes == null || keyBytes.length < 32) {
            throw new IllegalArgumentException("HMAC key must be at least 32 bytes");
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(keyBytes, "HmacSHA256"));
            byte[] digest = mac.doFinal(
                ("audit:v1:" + internalUserId).getBytes(StandardCharsets.UTF_8));
            // 128 bits from HMAC, long enough for this example's audit identifier.
            return HexFormat.of().formatHex(digest, 0, 16);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("Audit pseudonymization unavailable", e);
        }
    }
}
```

Never log `internalUserId` or `keyBytes`, and never pass the raw `Authentication` object across threads. Truncating the HMAC value **shortens its length**, not because truncation makes it "anonymous". Final length depends on subject population, collision budget, and event-linking requirements. Define rotation/rekeying order before changing keys.

## 9. Defense in Depth Beyond the Listener

### 9.1. Logging Frameworks and Detailed Configuration

- **Application:** audit helpers use allowlists and fixed enums/error codes. Never call `log.*("{}", request)` or log raw response/claims maps.
- **Spring MVC & Security:** control `logging.level.*`, avoiding broad `TRACE`/`DEBUG` in production; `spring.mvc.log-request-details=false` governs only part of MVC logging, **not all loggers**.
- **HTTP client/server:** request/response logging in Feign, RestTemplate, WebClient, gateways, and reverse proxies usually has separate settings. Verify hiding of `Authorization`, cookies, bodies, and queries in each place.
- **ORM/SQL:** SQL bind parameters can contain emails, tokens, or payloads even when the SQL text does not. Check Hibernate/JDBC/tracing loggers.
- **Log encoders/appenders:** use structured logs with a stable schema, configure extra filters for secret fields, and escape control characters.
- **APM/traces/error trackers:** spans, baggage, exception breadcrumbs, and crash dumps are also telemetry; never attach PII, credentials, or raw requests to attributes.

Switching a `logger` to JSON **does not automatically strip sensitive fields**. Even when output is masked, a collector may retain the original if redaction happens after ingestion. Redact **as early as possible**.

### 9.2. MDC and Correlation IDs

SLF4J MDC is a thread-contextual map used to enrich logs. You can store a server-generated `requestId`; **never put emails, usernames, JWTs, or session IDs into MDC** because every log on that thread could carry them. In Servlets, clean up MDC in `finally` after the request:

```java
// Illustrative body of a filter/interceptor, not a complete class.
String requestId = java.util.UUID.randomUUID().toString();
org.slf4j.MDC.put("requestId", requestId);
try {
    filterChain.doFilter(request, response);
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

In async execution, virtual threads, thread pools, or reactive contexts, MDC does not automatically preserve context accurately; use framework-supported propagation mechanisms, pass only approved values, and clear when done. Never accept a raw client-supplied `X-Request-ID` and log it without validation/length limits; client-controlled headers can contain newlines, personal data, or attack strings.

### 9.3. Preventing Log Injection and Untrusted Data

If a user-supplied text field cannot be avoided, apply an allowlist, length limits, and normalize/escape `\r`, `\n`, tabs, and control characters for your log format; otherwise, a single value can forge fake log lines. Structured logging helps with escaping, yet still requires schemas and size limits. Never print a partially masked string that still leaves OTPs or secrets in the unmasked slice.

**Never use `trim` or `substring` to "mask" secrets**; truncation only bounds length and does not make sensitive data safe.

## 10. Storage, Access, and Incident Response Procedures

Even after data minimization, security events remain sensitive because they describe activity and permission checkpoints.

1. **Separated read/write permissions:** restrict who can view logs, audit every access, prevent applications from arbitrarily altering history; prefer write-once collections where appropriate.
2. **Clear retention:** retention duration depends on investigative goals and applicable legal/business requirements. Minimize uncontrolled copies (agent buffers, archives, backups, exports).
3. **Protected transit/storage:** TLS for telemetry streams; encryption at rest; separate key management and access control.
4. **Reliability and load:** synchronous listeners add latency; exceptions in listeners can affect requests. Isolate sinks/queues with proper failure policies and backpressure. If durable auditing is mandatory, in-process Spring application events are **not** sufficient proof of successful storage.
5. **Incident where a token leaked into logs:** treat the token as compromised; revoke/rotate according to credential type, restrict log access scope, investigate downstream exports, and remediate data per approved incident procedures. Deleting a line from a dashboard **does not** remove it from all archives.
6. **Periodic checks:** review logging rules, run secret scanners against telemetry in test environments, and query logs with permitted aggregated checks; always avoid turning tests into a place that logs real secrets.

## 11. Before-and-After Analysis Scenarios

**Scenario A: API returns 403**

- Before: `log.warn("Denied {}", request.getRequestURL())` logs paths containing personal IDs and may omit role context.
- After: `event_type=AUTHORIZATION_DENIED resource=REPORT_READ outcome=DENIED`. Permission decisions are investigated by event ID; the client still receives HTTP 403 from Spring Security.

**Scenario B: Expired JWT or missing scope**

- Before: `log.error("JWT error token={}", token)` creates a hijack risk if the token is still usable elsewhere.
- After: log `auth_error_code=INVALID_TOKEN` or `INSUFFICIENT_SCOPE` from a fixed code set, optionally with correlation ID. Never log raw claims, bearer tokens, or free-form exception messages. Properly distinguish **authentication** events from **authorization** events.

**Scenario C: Searching all events for one person**

- Before: logging raw emails or phone numbers on every line.
- After: add `actor_ref` only when needed and backed by clear policy; derive it from internal IDs via keyed HMAC. Avoid using IP/user-agent as an absolute identity because they can change, be shared, or constitute personal data.

**Scenario D: QA discovers secrets in HTTP client debug logs**

- Before: fixing only the authorization listener while leaving full-body wire logging enabled.
- After: disable/fix the actual leak source in the HTTP client, audit downstream stores, add canary tests without real secrets, and lock down production configuration.

## 12. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Logs mask `password` but Bearer tokens still appear | Redaction applied only to the `password` field | Drop auth headers/tokens completely at source; audit with fixed error codes |
| Email regex masks emails, yet PII appears in nested JSON | String scanning lacks schema/escaping awareness | Allowlist fields before serialization; check secondary sinks |
| Hashed emails are still guessable | Unkeyed hash over low-entropy input | Use keyed HMAC over internal IDs when correlation is needed |
| Log has URI without query string but still leaks IDs | Path variables are personal identifiers | Use route templates/logical resource codes |
| JWT payload treated as non-secret | Base64URL payloads decode trivially, and the token may still grant access | Never log any part of a JWT, not even "just claims" |
| Enabling DEBUG/TRACE in production reveals credentials | Other libraries/frameworks log outside your helper | Audit every component's config; block wire/request-body logging |
| One denied event appears twice | Multiple permission checks or different dispatchers | Attach event ID/correlation and source; do not assume 1 event = 1 request |
| Audit logs lack actors so investigations fail | Excessive data minimization relative to requirements | Add controlled `actor_ref` when purpose and access controls are in place |
| Correlation ID contains newlines or untrusted data | Logging client-sent headers verbatim | Generate IDs server-side or validate format/length |
| Tests pass but proxies still log secrets | Only capturing application stdout | Inspect gateways, ingress, APM, queues, collectors, and retention |

## 13. Pre-Release Review Checklist

- [ ] All authorization/audit logs use an **allowlisted schema**, never directly serializing requests, responses, SecurityContext, Principal, or exceptions.
- [ ] No passwords, tokens, cookies, session IDs, keys, OTPs, or OAuth codes in messages, MDC, span attributes, appenders, or exports.
- [ ] No verbatim URLs/queries/path variables or bodies that may contain personal data.
- [ ] `resource/action/outcome` labels come from enums/bounded sets, with tests for unknown routes.
- [ ] If `actor_ref` is present, its purpose, HMAC method, keys, rotation, read permissions, and retention are defined.
- [ ] Tested at least one 403 denied request carrying fake tokens/emails/IDs; verified log matches schema and omits secrets.
- [ ] Tested 200 allowed requests; avoided mistaking absence of denied events for absence of requests.
- [ ] Log levels/field sizes bounded, CRLF injection prevented, MDC cleaned up, and listener failure policy defined.
- [ ] Checked external sources: proxies, clients, SQL, APM, traces, and collectors.
- [ ] Incident response plan exists in case secrets are ever written to logs.

## References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to exclude from logs, masking/sanitization, log-injection defense, and log governance.
- [Spring Security – Authorization Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/events.html): `AuthorizationEventPublisher`, `SpringAuthorizationEventPublisher`, and `AuthorizationDeniedEvent`.
- [Spring Security – Servlet Authorization](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter` and permission decisions.
- [Spring Boot – Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html): logger levels, Logback, output, and Spring Boot configuration.
- [Spring Boot – CapturedOutput/OutputCaptureExtension](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/system/OutputCaptureExtension.html): testing application log output.
