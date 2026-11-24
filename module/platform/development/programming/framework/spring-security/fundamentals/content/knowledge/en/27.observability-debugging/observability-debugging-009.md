# Authentication Events, Authorization Events, and Audit Logs in Spring Security

> **Scope:** Spring Security fundamentals, **Observability and Debugging** group. This lesson explains and practices capturing **authentication events**, **authorization events**, and **audit events/audit trails**, along with structuring safe audit data, verifiability, traceability, and resilience when systems fail. Examples use **Java 17, Spring Boot 3.3.5, Spring Security 6.x, Spring MVC/Servlet, Spring Boot Actuator, and JUnit 5/MockMvc**. Points specific to WebFlux/OAuth2/Resource Server are called out separately rather than assuming every mechanism emits the same events.

## 1. Why Are Security Events and Audit Logs Needed?

When an API returns `401`, `403`, or `200`, the HTTP response communicates **the outcome to the client**, yet does not provide enough evidence to answer:

- Who attempted to log in? Did authentication succeed or fail, and under which mechanism?
- Why was an already logged-in user still denied access?
- Who just granted or revoked an important permission, or modified a security setting?
- Is a burst of failed logins a password mistake, attack traffic, or an identity-store outage?
- What events occurred before and after a sensitive change? Is there trustworthy evidence for an investigation?

Spring Security can publish **Spring application events** on authentication or authorization. Spring Boot Actuator adds an `AuditEvent` and `AuditEventRepository` model. Yet **an in-JVM event is not automatically a durable audit record**: a proper audit trail requires selecting, normalizing, storing, protecting, and monitoring the recording pipeline.

**Key distinctions:**

| Concept | Unit of Information | Used For | Limitations |
| --- | --- | --- | --- |
| Authentication event | Login success/failure attempt, exception type | Tracking logins and identity-provider errors | Does not mean every HTTP request emits an auth event |
| Authorization event | Decision to grant/deny an action | Finding role/scope bugs, counting access denials | Granted events can be too noisy; not every 403 path is an authz denial |
| Audit event | Structured record: actor, action/type, outcome, time, context | Querying security events and business changes | Needs a repository/collector; in-memory is not durable |
| Application/security log | INFO/DEBUG/WARN/ERROR log lines, trace ID | Technical debugging, system investigation | May lack schema, get rotated/deleted, or contain sensitive info |
| Audit trail | Stored, protected, queryable, lifecycle-managed event stream | Investigation, accountability, abuse detection, compliance | Does not form automatically just from `@EventListener` |
| Metric/trace | Rates, latencies, cross-service spans | Alerting, impact sizing, dependency mapping | Does not replace detailed events with actor/action/outcome |

**Sound design:** treat framework events as an **input signal**, transform valuable signals into **filtered, data-minimized audit records**, and for high-assurance evidence choose a durable store rather than relying solely on ordinary text loggers.

## 2. Event Flow in Servlet Spring Security

In a typical Servlet application:

```text
HTTP Request
    |
    v
SecurityFilterChain
    |
    +--> Authentication filter (Basic/form/Bearer...)
    |      |
    |      v
    |   AuthenticationManager / ProviderManager
    |      |
    |      +--> Success -> AuthenticationSuccessEvent
    |      |
    |      +--> Failure -> AbstractAuthenticationFailureEvent
    |                      (subclass per AuthenticationException type)
    |
    +--> AuthorizationFilter / AuthorizationManager
    |      |
    |      +--> Denied  -> AuthorizationDeniedEvent
    |      |
    |      +--> Granted -> usually does not emit granted events by default
    |
    v
Controller / service / method security
    |
    +--> Additional authorization events may come from matching extension points
    |
    v
Spring ApplicationEventPublisher
    |
    +--> @EventListener / custom adapter
    |
    +--> Spring Boot Actuator auditing when configured
    |
    v
AuditEventRepository / storage / observability pipeline
```

This diagram shows the **common event path**, not a guarantee that every authentication flow or every request emits exactly one event. Depending on filters, providers, session reuse, JWT decoders, method security, how `AuthenticationManager` is built, and version differences, event counts and names can vary. Test the application's **real flow**.

### 2.1 One HTTP Request Does Not Equal One Authentication

- With HTTP Basic, the filter can re-authenticate on every request, so success events may fire repeatedly.
- With sessions after form login, subsequent requests may simply restore `SecurityContext` from the session without re-running `AuthenticationManager`.
- With a JWT Resource Server, token decoding and authentication flows emit events differently depending on the `AuthenticationManager`/filter setup.
- With `@WithMockUser` in tests, context is injected directly: that is **not** real login, so do not rely on mocks to prove real authentication events fire.
- With OAuth2 login, inspect the events/handlers of the OIDC/OAuth2 flow itself; do not assume a single `AuthenticationSuccessEvent` fully describes token exchange.

**Operational consequence:** never measure "successful user login sessions" by blindly counting every `AuthenticationSuccessEvent` across all architectures. Explicitly distinguish metrics for "credential verification," "interactive login," "new session," and "authenticated request."

## 3. Authentication Events

### 3.1 Success, Failure, and Event Publisher

Common classes/APIs in Spring Security 6.x:

| Class/API | Role |
| --- | --- |
| `AuthenticationEventPublisher` | Contract for publishing authentication events |
| `DefaultAuthenticationEventPublisher` | Standard publisher translating success and selected auth failures into Spring events |
| `AuthenticationSuccessEvent` | Authentication accepted by a provider |
| `AbstractAuthenticationFailureEvent` | Base class for failed authentication events |
| `AuthenticationFailureBadCredentialsEvent` | Credentials rejected |
| `AuthenticationFailureLockedEvent`, `AuthenticationFailureDisabledEvent` | Account locked/disabled |
| `AuthenticationFailureServiceExceptionEvent` | Error in the service backing authentication |
| `ApplicationEventPublisher` | Internal Spring event bus |
| `@EventListener` | Declares a method that receives events |

Explicit configuration example:

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new DefaultAuthenticationEventPublisher(applicationEvents);
}
```

This is a **configuration fragment** requiring matching imports; the complete Java file in section 7 includes all imports. Many Spring Boot apps already get an event publisher via auto-configuration; declaring a bean explicitly helps demonstrate the activation point. **Do not register multiple redundant publishers** without knowing which bean the framework picks or whether events will be duplicated.

### 3.2 Listening for Events via @EventListener

```java
// Fragment: place inside a @Component.
// Pick only safe fields; never print the entire Authentication.
@EventListener
public void onSuccess(AuthenticationSuccessEvent event) {
    String principal = event.getAuthentication().getName();
    // Write filtered audit event through adapter/repository.
}

@EventListener
public void onFailure(AbstractAuthenticationFailureEvent event) {
    String kind = event.getException().getClass().getSimpleName();
    // Never log raw credentials or event.getAuthentication().toString().
}
```

A listener accepting `AbstractAuthenticationFailureEvent` receives matching subclasses. When distinguishing failure kinds, classify the **exception** (bad credentials, account state, dependency failure) and store only an **internal category**. Avoid storing verbatim exception messages because they may contain usernames, hostnames, or sensitive details.

### 3.3 Exception Mapping Does Not Automatically Capture Every Subclass

`DefaultAuthenticationEventPublisher` maps a set of standard exceptions to corresponding events. Subtle detail: its mapping mechanism uses **exact exception class matching**, so a custom subclass of `BadCredentialsException` is not guaranteed to publish the same default event.

Common groups include:

- `BadCredentialsException` or hidden missing-username errors → credential failure group.
- `LockedException` / `DisabledException` → account state group.
- `AuthenticationServiceException` → authentication infrastructure/service failure group.
- `ProviderNotFoundException` → likely configuration/provider issue.
- Custom application-defined exceptions → check mappings rather than assuming a default event exists.

You can configure `setAdditionalExceptionMappings(Map<...>)` or a default/fallback event for unmapped exceptions. Verify custom event constructors and Spring Security versions carefully, and write tests proving events are not dropped.

### 3.4 Authentication Failure Is Not Authorization Denial

- Logging in with a wrong password is an **authentication failure**; the client typically gets 401 or a protocol-appropriate error page/redirect.
- A logged-in user lacking `ROLE_ADMIN` is an **authorization denial**, typically returning 403.
- A POST missing a CSRF token can return 403 inside the security filter without necessarily invoking `AuthorizationManager`.
- An identity store/IdP outage can emit an authentication service failure; do not lump it together with wrong passwords in metrics or account-lockout policies.
- An administrator changing roles can succeed and needs a separate **business audit event**—it cannot be deduced from authentication/authorization events alone.

**Harmful misclassification:** incrementing failed-login counters during an outage can lock out innocent users en masse; counting every 403 as a missing role conflates CSRF, CORS, and gateway errors; checking only loggers does not guarantee audit persistence.

## 4. Authorization Events

Spring Security 6.x provides `AuthorizationEventPublisher`. `SpringAuthorizationEventPublisher` uses `ApplicationEventPublisher` to emit authorization events; by default, this publisher focuses on **`AuthorizationDeniedEvent`** instead of flooding every grant.

Configuration:

```java
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new SpringAuthorizationEventPublisher(applicationEvents);
}
```

To capture denials:

```java
// Fragment: place inside a @Component with matching imports.
@EventListener
public void onDenied(AuthorizationDeniedEvent<?> event) {
    // Do not log event.getObject().toString() or the whole
    // authentication: the object may contain request/method arguments.
    // Append an outcome=DENIED audit record with filtered data.
}
```

`AuthorizationDeniedEvent` exposes information about the protected object and a `Supplier<Authentication>` per Spring Security 6.3 APIs. That does not mean you should serialize the whole object. For URL authorization, the object may relate to the request; for method security, it may hold the method invocation and sensitive business arguments.

### 4.1 Why Are Granted Events Not Enabled Broadly?

An application serving thousands of requests per second performs huge numbers of "allowed" checks. Emitting and storing every grant can:

- Inflate record counts and storage costs, burying noteworthy denials.
- Repeatedly log the exact same permission check.
- Leak resources, tenants, or method arguments into audits if serializers are too broad.
- Slow down requests if listeners write synchronously.
- Blur "passed one security check" with "business operation actually completed."

For sensitive operations, auditing **the completed business action** (e.g., permission change, account deletion, data export) is usually far more valuable than auditing every time `hasRole` returned true. If granted events are needed, emit them selectively by rule/route/action or raise an explicit business event carrying a clear outcome; measure load and avoid duplicates.

### 4.2 Not Every Denial Shares the Same Source

A 403 response can originate from the CSRF filter, method security, URL authorization, a custom `AccessDeniedHandler`, a reverse proxy, or a gateway. `AuthorizationDeniedEvent` depends on whether **the publisher and that decision point** participated. Never assume "a 403 happened, so an AuthorizationDeniedEvent must have fired."

For critical operations, define a **supplementary audit path** where the decision or transaction actually takes place, and test both positive and negative paths. However, avoid writing two records for "one event" from two un-deduplicated listeners and counting them as two denials.

## 5. How Audit Trails Differ from DEBUG Logs

DEBUG logs are meant for developers: they may include class names, request matchers, timings, stack traces, and change across library versions. An **audit record** should have a stable schema for auditing and querying, sufficient to answer *who – did what – to which resource – when – where – with what outcome – for what reason category – tied to which request*.

Reference schema:

| Audit Field | Example | Rule |
| --- | --- | --- |
| `event_id` | UUID | Unique identifier to prevent duplicate writes |
| `occurred_at` | ISO-8601 UTC | Action timestamp, time-synchronized |
| `recorded_at` | ISO-8601 UTC | Time the audit store received the record |
| `category` | AUTHENTICATION, AUTHORIZATION, ACCOUNT_ADMIN | High-level event category |
| `event_type` | LOGIN_FAILED, ACCESS_DENIED, ROLE_REVOKED | Stable, versioned/schema-governed code |
| `actor_id` | Internal ID / pseudonym | No need to store passwords, full principals, or emails |
| `actor_type` | USER, SERVICE, ANONYMOUS | Distinguishes human users from service accounts |
| `target_type` | REPORT, ACCOUNT, TENANT, API | Avoid storing raw request bodies |
| `target_id` | Allowed internal identifier | Govern tenant/PII exposure |
| `action` | READ, LOGIN, UPDATE_PERMISSION | Requested or performed operation |
| `outcome` | SUCCEEDED, DENIED, FAILED, UNKNOWN | Never treat HTTP status alone as root cause |
| `reason_code` | BAD_CREDENTIALS, MISSING_ROLE, IDENTITY_STORE_DOWN | Filtered internal classification code |
| `request_id`, `trace_id` | Correlation ID | Joins records across system components |
| `service`, `environment`, `instance` | identity-api, prod, pod-03 | Aids investigation and data partitioning |
| `source_ip` | Normalized IP if policy allows | Behind proxies, trust only validated forwarding headers |
| `schema_version` | 1 | Supports schema evolution over time |

Not every system needs every field. **Data minimization principle:** collect only what is needed for accountability, strip passwords, tokens, authorization headers, and raw cookies, and encrypt and restrict access to remaining identifiers.

### 5.1 "Attempted," "Authorized," and "Committed" Events Differ

A role-change example:

```text
POST /admin/accounts/42/roles
  |
  +--> Authentication succeeded       (identity verified)
  |
  +--> Authorization permitted        (allowed to invoke action)
  |
  +--> Business validation            (may fail)
  |
  +--> DB update transaction          (may roll back)
  |
  +--> Commit succeeded               (change is actually durable)
  |
  +--> ROLE_CHANGED audit event       (completed outcome)
```

Do not write `ROLE_CHANGED success` the moment `hasRole("ADMIN")` returns true. If the transaction rolls back, the audit record becomes false. For events tied to commits, design `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` for appropriate side effects or use a **transactional outbox** / transaction log when high reliability is required. Note that an `AFTER_COMMIT` listener calling another service can still fail, so never promise that an in-JVM event bus guarantees durable exactly-once delivery.

### 5.2 Collect Meaningful Events, Not Just "Log Everything"

Prioritize auditing:

- Significant authentication successes/failures; MFA changes, password resets, session/token revocations.
- Role grants/revocations, policy changes, service account creation/deletion, IdP/OAuth2 client config edits.
- Data administration actions, sensitive data exports, access to audit-required resources.
- Repeated blocked access attempts or attempts from anomalous sources; failed security changes.
- Credential rotation/revocation events—record only action type and actor, **never secret values**.

There is no need to audit every routine GET request in detail; use metrics/traces for volumetric monitoring and select meaningful events.

## 6. Spring Boot Actuator: AuditEvent and AuditEventRepository

Spring Boot Actuator offers an auditing model with:

| API | Role |
| --- | --- |
| `AuditEvent` | A record with timestamp, principal, type, and data map |
| `AuditEventRepository` | Contract to append/query audit events |
| `InMemoryAuditEventRepository` | Ring buffer in RAM, **for demo/dev only**, unsuitable for production audits |
| `AuditApplicationEvent` | Way to publish a custom audit event into the Spring application context |
| `AbstractAuthenticationAuditListener` | Extension point converting authentication events to audit events |
| `AbstractAuthorizationAuditListener` | Extension point converting authorization-related events to audit events |
| `/actuator/auditevents` | Management endpoint reading audit data when a repository exists and it is intentionally exposed |

When Spring Security is present and Actuator auditing is configured, Spring Boot can translate common security events into audit records (e.g., authentication success/failure, access denied). **These events should not be assumed to cover every business action or every denial in every filter**. If an application adds its own audit listener, it may receive **both Boot-provided events and custom events**; decide record ownership explicitly to avoid double counting.

Example repository for testing:

```java
@Bean
AuditEventRepository auditEventRepository() {
    return new InMemoryAuditEventRepository(1000);
}
```

The **1000-event limit in RAM** prevents unbounded memory growth. Contents vanish on restart and get overwritten/evicted when capacity is exceeded. Thus it must never be treated as durable compliance evidence in production.

### 6.1 The auditevents Endpoint Must Be Protected

Do not expose `/actuator/auditevents` publicly. Records can contain principals, paths, and sensitive metadata. For production use, enforce:

1. Management network isolation (private network, VPN/mTLS, allowlists).
2. Strict authorization restricted to authorized security operators/auditors.
3. Query controls and rate limiting; audit reads/exports of audit logs themselves if policy requires.
4. Retention controls and result-size limits to prevent bulk data exfiltration.
5. Do not treat exposing the endpoint as required for **recording** audits: the repository can capture events even when the HTTP endpoint is not exposed.

In applications with a custom `SecurityFilterChain`, never assume actuator endpoints will automatically be protected the way you want. Configure management security explicitly according to your deployment model.

## 7. Java 17 Project: Publishing, Listening, and Testing Events

The following example runs with Spring Boot 3.3.5 and the bundled Spring Security 6.3.x. It has two demo users `reader` and `admin`, plus endpoints `/public`, `/me`, and `/ops` (ADMIN only). We configure two publishers, three listeners, and an in-memory `AuditEventRepository`. Listeners record only **event type and minimal metadata**—no passwords, Authorization headers, raw `Authentication` objects, or request objects.

The example can produce both **default Actuator audit events** and **custom events**. To keep tests deterministic and prevent mixing types, custom types use an `APP_` prefix. Production systems must design merging/deduplication if both sources feed the same metric.

### 7.1 Directory Structure

```text
security-events-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/securityevents/
    │   └── SecurityEventsApplication.java
    └── test/java/com/example/securityevents/
        └── SecurityEventsApplicationTest.java
```

### 7.2 Maven Dependencies

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-events-demo</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

### 7.3 Spring Boot Application and Listeners

Create `src/main/java/com/example/securityevents/SecurityEventsApplication.java`:

```java
package com.example.securityevents;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityEventsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityEventsApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-456"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new DefaultAuthenticationEventPublisher(applicationEvents);
    }

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new SpringAuthorizationEventPublisher(applicationEvents);
    }

    @Bean
    AuditEventRepository auditEventRepository() {
        // Demo/dev only. Do not use as a compliance audit store in production.
        return new InMemoryAuditEventRepository(1000);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/ops").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public ok";
        }

        @GetMapping("/me")
        String currentUser(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @GetMapping("/ops")
        String operations() {
            return "ops ok";
        }
    }

    @Component
    static class SecurityAuditListeners {
        private final AuditEventRepository repository;

        SecurityAuditListeners(AuditEventRepository repository) {
            this.repository = repository;
        }

        @EventListener
        public void authenticationSucceeded(AuthenticationSuccessEvent event) {
            // Do not store credentials, details, toString(), or principal objects.
            String actor = safeActor(event.getAuthentication());
            repository.add(new AuditEvent(
                actor,
                "APP_AUTH_SUCCESS",
                Map.of("outcome", "SUCCEEDED", "source", "spring-security")
            ));
        }

        @EventListener
        public void authenticationFailed(
                AbstractAuthenticationFailureEvent event) {

            String reason = "OTHER_AUTH_FAILURE";
            if (event.getException() instanceof BadCredentialsException) {
                reason = "BAD_CREDENTIALS";
            } else if (event.getException()
                    instanceof AuthenticationServiceException) {
                reason = "AUTH_SERVICE_FAILURE";
            }

            repository.add(new AuditEvent(
                safeActor(event.getAuthentication()),
                "APP_AUTH_FAILURE",
                Map.of("outcome", "FAILED", "reason", reason)
            ));
        }

        @EventListener
        public void accessDenied(AuthorizationDeniedEvent<?> event) {
            String actor = "unknown";
            try {
                // Supplier may fail to return Authentication if no proper
                // security context exists; never let auditing break the request.
                actor = safeActor(event.getAuthentication().get());
            } catch (RuntimeException ignored) {
                // Store only a generic actor instead of printing request/credentials.
            }

            repository.add(new AuditEvent(
                actor,
                "APP_AUTHZ_DENIED",
                Map.of("outcome", "DENIED", "domain", "http-authorization")
            ));
        }

        private static String safeActor(Authentication authentication) {
            if (authentication == null) {
                return "anonymous";
            }
            String name = authentication.getName();
            return (name == null || name.isBlank()) ? "unknown" : name;
        }
    }
}
```

### 7.4 Why Is This Implementation Meaningful?

1. **Authentication publisher** is declared explicitly; when a `ProviderManager` processes Basic authentication with this publisher, it emits success/failure events.
2. **Authorization publisher** is also declared explicitly. `SpringAuthorizationEventPublisher` emits a denial when `AuthorizationFilter` makes a deny decision; do not confuse that denial with every HTTP 403.
3. **Listeners** receive events via `@EventListener`, rather than calling `System.out.println` or printing full `Authentication` objects. The data map holds only outcomes/categories without passwords or raw tokens.
4. **AuditEventRepository** uses a bounded in-memory implementation for learning convenience. Within the same JVM, JUnit can query it to assert recorded events. No custom API endpoint dumps all audit records to clients.
5. **Actor name** is an example for the demo environment. Production may need internal IDs/pseudonyms, data minimization/retention workflows, or avoid storing account names on every event; avoid logging unbounded attacker-supplied usernames.
6. **AuthorizationDenial source** records only the domain type and never serializes `event.getObject()`, because that object can hold URLs, method arguments, or sensitive business objects.
7. **No separate async executor** is used in the example: default event listeners run synchronously along the publish path, keeping tests simple. Production must weigh latency and durability; a slow repository write or thrown listener exception can impact authentication requests.
8. **Actuator may write standard audit events alongside custom `APP_*` events**. Never sum both kinds and treat that as real login counts. In deployment, choose canonical sources, event types, and deduplication rules.
9. **HTTP status is not controlled by listeners**: URL access is still governed by `authorizeHttpRequests`; auditing only records observed events. An audit failure must never serve as a way to grant access or bypass protection.

### 7.5 Integration Testing with MockMvc and AuditEventRepository

Create `src/test/java/com/example/securityevents/SecurityEventsApplicationTest.java`:

```java
package com.example.securityevents;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityEventsApplicationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AuditEventRepository audit;

    private int count(String actor, String type) {
        return audit.find(actor, null, type).size();
    }

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    void loginSuccessProducesAuditEvent() throws Exception {
        int before = count("admin", "APP_AUTH_SUCCESS");

        mvc.perform(get("/me")
                .with(httpBasic("admin", "admin-demo-456")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello admin"));

        assertThat(count("admin", "APP_AUTH_SUCCESS"))
            .isGreaterThan(before);
    }

    @Test
    void wrongPasswordProducesAuthenticationFailureEvent()
            throws Exception {

        int before = count("admin", "APP_AUTH_FAILURE");

        mvc.perform(get("/ops")
                .with(httpBasic("admin", "wrong")))
            .andExpect(status().isUnauthorized());

        assertThat(count("admin", "APP_AUTH_FAILURE"))
            .isGreaterThan(before);
    }

    @Test
    void deniedAccessProducesAuthorizationAuditEvent()
            throws Exception {

        int before = count("reader", "APP_AUTHZ_DENIED");

        mvc.perform(get("/ops")
                .with(httpBasic("reader", "reader-demo-123")))
            .andExpect(status().isForbidden());

        assertThat(count("reader", "APP_AUTHZ_DENIED"))
            .isGreaterThan(before);
    }

    @Test
    void adminIsAuthorizedToUseOps() throws Exception {
        mvc.perform(get("/ops")
                .with(httpBasic("admin", "admin-demo-456")))
            .andExpect(status().isOk())
            .andExpect(content().string("ops ok"));
    }

    @Test
    void customAuditDataDoesNotContainPassword() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("admin", "admin-demo-456")))
            .andExpect(status().isOk());

        List<AuditEvent> records =
            audit.find("admin", null, "APP_AUTH_SUCCESS");

        assertThat(records).isNotEmpty();
        for (AuditEvent item : records) {
            // Check only custom data fields; do not serialize credentials.
            assertThat(item.getData().toString())
                .doesNotContain("admin-demo-456");
        }
    }

    @Test
    void unauthenticatedRequestCannotReadOps() throws Exception {
        mvc.perform(get("/ops"))
            .andExpect(status().isUnauthorized());
    }
}
```

The suite contains **7 tests**. Event tests measure record counts **before and after a request**, rather than assuming the application-wide count equals 1, because other tests or auto-configuration may write into the dev store too. Custom events are separated from Boot's default audit events by the `APP_` prefix.

**Note when switching to async:** these tests rely on synchronous `@EventListener` and an in-memory repository. If replaced with a message broker, queue, or `@Async`, tests must wait on a bounded timeout condition (or use a test broker) rather than asserting immediately after the response. Never add fixed `Thread.sleep` calls to mask race conditions.

### 7.6 Trying It Out

Install Java 17+ and Maven. From the project directory:

```bash
mvn test
mvn spring-boot:run
```

Send real requests:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/ops
curl -i -u reader:reader-demo-123 http://localhost:8080/ops
curl -i -u admin:admin-demo-456 http://localhost:8080/ops
curl -i -u admin:wrong http://localhost:8080/ops
```

| Request | Expected HTTP | Primary Signal Layer |
| --- | --- | --- |
| `GET /public` | 200 | Public route, no auth event required |
| `GET /ops` without credentials | 401 | Entry point; do not assume a bad-credentials event fires |
| `GET /ops` with `reader` | 403 | Missing role; `AuthorizationDeniedEvent` with publisher configured |
| `GET /ops` with `admin` | 200 | Valid authentication; can emit auth success |
| `GET /ops` with `admin` + wrong password | 401 | Authentication failure; custom audit `APP_AUTH_FAILURE` |

Audit data has no public API in the demo. Tests query `AuditEventRepository` directly to prove those events were recorded. To query operationally, configure a tightly controlled management endpoint rather than exposing a public `GET /all-audit`.

The results in the table are expectations based on the stated source and APIs; to confirm execution on your machine, run `mvn test`. Never use a single HTTP status result as proof that events and the audit trail are durable.

## 8. Adding Audits for Critical Business Actions

Authentication/authorization events do not cover "admin just changed someone else's role." Example publishing a custom audit event for a permission change **after commit**:

```java
// ILLUSTRATIVE FRAGMENT: roleService/accountId/actorId are project-defined.
// Use when a transaction and a suitable durable write path exist.
@Transactional
public void changeRole(long accountId, String role, String actorId) {
    roleRepository.updateRole(accountId, role);
    applicationEvents.publishEvent(
        new RoleChangeRequestedEvent(accountId, actorId, role)
    );
}

// Listener can run only after commit once the transaction truly succeeds.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onRoleChange(RoleChangeRequestedEvent event) {
    auditSink.recordRoleChange(event.accountId(), event.actorId());
}
```

This is a **fragment, not standalone Java code**: `RoleChangeRequestedEvent`, `roleRepository`, `auditSink`, and imports must be provided by the project. `RoleChangeRequestedEvent` is just a sample domain name; publishing before commit allows an `AFTER_COMMIT` listener to record it only after the transaction succeeds.

**Do not confuse AFTER_COMMIT with guaranteed durable storage:** the process can crash after committing the database yet before the audit sink receives the record. When requirements demand "never lose a record," use a **transactional outbox** (writing the business change and outbox record in the same transaction) with a reliable worker pushing events from the outbox to the audit store. Consumers must be idempotent by `event_id` because at-least-once delivery can duplicate messages.

### Three Ways to Write Audits and Their Trade-Offs

| Approach | Pros | Cons |
| --- | --- | --- |
| Synchronous `@EventListener` + DB audit | Simple, direct testing | Increases request latency; audit write errors can impact business logic |
| `@Async`/internal queue + log collector | Reduces request blocking | Crashes/restarts can drop events; ordering and context must be propagated explicitly |
| Transactional outbox + broker/collector | Protects records across commits, retries, replays | Higher design, ops, idempotency, dead-letter, and monitoring effort |

If audit policy states **a transaction is permitted only if audited**, decide what happens when audit storage is unavailable (fail closed, block transactions, or governed degradation) and verify zero data loss. There is no single universal technical answer for every risk tier.

## 9. Protecting Events, PII, and Sensitive Data

### 9.1 What Must Never Be Recorded?

**Never record** passwords, OTPs, PINs, raw Basic `Authorization` headers, access/refresh tokens, session cookies, CSRF tokens, OAuth authorization codes, API keys, client secrets, private keys, token signing keys, entire login request bodies, or stack traces containing sensitive data.

Also avoid serializing whole objects verbatim:

```java
// WRONG: may log credentials/details/claims/business arguments.
log.info("authentication={}", event.getAuthentication());
log.info("denied event={}", deniedEvent);
auditRepository.add(new AuditEvent(
    principal, "ALL_DETAILS", Map.of("request", request.toString())));
```

These are **anti-pattern fragments**—variables are project-defined, not runnable standalone code. `toString()` on a principal, `Authentication`, request, method invocation, or exception can expose far more than intended.

### 9.2 Replace with a Data Allowlist

A sensible record to ship to a collector (illustrative JSON):

```json
{
  "schema_version": 1,
  "event_type": "AUTHORIZATION_DENIED",
  "outcome": "DENIED",
  "actor_type": "USER",
  "actor_id": "user-internal-932",
  "target_type": "REPORT",
  "action": "READ",
  "reason_code": "MISSING_ROLE",
  "request_id": "req-62ad",
  "occurred_at": "2026-01-01T09:00:00Z",
  "service": "reports-api"
}
```

Timestamp, IDs, and values here are **synthetic data** illustrating the schema, not a real record. You do not always have to record a cleartext `actor_id` for every event; consider internal IDs/pseudonyms, decryption/lookup permissions, and data-protection policies.

Core principles:

- **Minimize:** capture only fields genuinely required for auditing; never copy request bodies.
- **Protect:** TLS/mTLS to collectors, encryption at rest, RBAC policies, and audit read/export access too.
- **Separate duties:** the app emitting events should not be able to delete or alter already-written audit records; separate app admin roles from audit administrators.
- **Retain appropriately:** TTLs matching legal and risk requirements; account for deletion/erasure obligations under laws and internal policies.
- **Verify:** schema versions, event IDs, checksums/signatures, or append-only/WORM storage where assurance requires it.
- **Limit volume:** apply burst controls, suppression, and sampling to low-value categories—never sample mandatory audit records.
- **Classify:** separate credential auth failures from IdP/database outages; never fire "attack" alerts on an unclassified error spike.

### 9.3 Correlation IDs and Tracing

Use `request_id` or `trace_id` to join browser/gateway/auth-service/permission-service logs with audit events. IDs should not contain usernames, emails, or tokens. In Spring MVC, logs can use MDC on the request thread, yet async event listeners may run on another thread; **pass correlation context explicitly** in the event envelope instead of assuming `ThreadLocal` is always populated.

In WebFlux, Reactor Context fits better than Servlet-style `SecurityContextHolder`. Never call `block()` or synchronous JDBC inside a reactive event-loop listener; use reactive clients or an appropriate write channel.

## 10. Reliable Audit Storage in Distributed Systems

### 10.1 Points Where Records Can Be Lost

- Process crashes before the listener runs or before shipping to the collector.
- Listener throws an exception; if synchronous, the request may fail or the event may abort.
- Message broker disconnects or acknowledgments are lost.
- Log collector queues fill up, disks fill, indexes fail, or retention misconfigures.
- An event is delivered multiple times via retries, consumer restarts, or at-least-once semantics.
- Clock skew across instances makes timestamp ordering misleading.
- Gateway drops a request before it reaches Spring Security, so no internal framework event fires.

For trustworthy auditing, measure **events created/received/persisted/failed**, end-to-end latency, queue depth, oldest event age, retries, and dead letters. Alert when the audit pipeline loses write capacity, not only when 401/403 rates spike.

### 10.2 Idempotency and Ordering

A stable `event_id` lets consumers reprocess safely without creating duplicate records. Design unique keys and query models—for example `(tenant_id, event_id)`. Across multiple services, **timestamps do not always determine a strict total order**; aggregate/transaction sequences or causal links may be needed.

Never promise "exactly once" merely because you use Kafka, a database, or an annotation; end-to-end consistency must be proven across business commit, publisher, broker, consumer, and audit store.

### 10.3 Do Not Break Authentication Availability Because of a Bad Listener

Spring's `ApplicationEventPublisher` with the default multicaster can invoke listeners synchronously on the publishing thread. Therefore:

- Listeners must never perform slow queries, untimeouted network writes, or heavy JSON serialization on the login path.
- Listeners must not accidentally throw exceptions that fail logins, unless mandatory audit policy requires fail-closed behavior and it is explicitly designed and tested.
- Never treat `@Async` as a "zero data loss guarantee." You need durable queues/buffers, backpressure, retries, and an error strategy.
- Never swallow audit writer failures silently; metrics and alerts must report which events were impacted.
- Test collector outages, retries, duplicates, backlogs, restarts, and rollbacks.

## 11. Testing Security Events and Audit Trails

A thorough test suite should cover distinct categories:

| Test Group | What to Prove | Technique |
| --- | --- | --- |
| Authentication success | Valid login emits signal and stores expected record | MockMvc/`httpBasic` or real flow; `AuditEventRepository` |
| Authentication failure | Bad credentials emit failure without leaking passwords | Real auth provider + inspect audit fields |
| Account state | Locked/disabled user differs from bad credentials | Test `UserDetailsService`/provider and category |
| Infrastructure failure | IdP/database timeout is not counted as wrong password | Fault injection/test doubles + mappings |
| Authorization denied | Logged-in user missing role is denied and creates denial record | HTTP 403 request + event listener |
| Authorization granted | Authorized admin passes route without record explosion | HTTP 200, check auditing scope |
| CSRF/CORS/gateway | 403 from CSRF, CORS, or upstream is not misattributed | Filter/route integration tests |
| Business audit | Role change writes event after commit; rollback writes no success | Transactional integration test |
| Durability | Broker/DB outage follows defined loss/retry policy | Retry/idempotency/chaos tests |
| Data protection | No unnecessary tokens/passwords/PII stored | Schema assertions + log inspection |
| Access control | Only auditors can read/export audits | Security tests for management endpoints |
| Retention | Events are retained/purged per lifecycle | Repository/pipeline integration |

**Never use `@WithMockUser` to prove authentication events:** the annotation injects a fake `SecurityContext`; to test `ProviderManager` and `DefaultAuthenticationEventPublisher`, use real authentication requests or controlled calls to the provider/manager.

When adding asynchronous auditing, tests must not assert results immediately without synchronization; use test queues/transactions and bounded polling with timeouts. For production pipelines, add tests for record counts after retries, duplicate messages, and partial failures.

## 12. Common Mistakes

### Mistake 1 — Adding `@EventListener` Alone and Treating It as a Durable Audit Trail

In-JVM Spring events do not survive restarts by default. `InMemoryAuditEventRepository` also loses data. **Fix:** distinguish signals from durable persistence, and choose an audit store/collector with retention and monitoring.

### Mistake 2 — Conflating 401 with One Specific Event

Missing credentials, wrong passwords, expired tokens, and broken IdPs can all yield 401 depending on configuration. **Fix:** classify root causes and auth mechanisms; never rely on HTTP status as the sole metric.

### Mistake 3 — Treating Every 403 as an `AuthorizationDeniedEvent`

CSRF and gateways can return 403 without reaching `AuthorizationManager`. **Fix:** test each security path and audit at the true source.

### Mistake 4 — Assuming Every Grant Emits an Event

`SpringAuthorizationEventPublisher` in Spring Security 6.3 focuses on denials; granted events are off by default to avoid high volume. **Fix:** add selective grant auditing only when explicitly required, preferring business outcome events.

### Mistake 5 — Logging Full `Authentication` or Exception Objects

Authentication objects, claims, or exception messages can contain secrets or PII. **Fix:** allowlist fields and reason codes, and restrict log/audit read access.

### Mistake 6 — Forgetting to Configure `AuthenticationEventPublisher`

`ProviderManager` may use a no-op publisher if not wired properly in a given integration setup. **Fix:** inspect publisher beans/injection and test with real credentials to confirm events arrive.

### Mistake 7 — Missing Exception Subclass Mappings

The default publisher uses exact class matching for several exceptions. **Fix:** add explicit mappings or fallback events and test custom exceptions.

### Mistake 8 — Confusing Audit Events with Human Login Counts

HTTP Basic can emit multiple auth successes per request count; sessions can reuse authentication without new events. **Fix:** clearly define metrics and event types for login flows, credential checks, requests, and sessions.

### Mistake 9 — Synchronous Listeners Writing to Slow Downstream Systems

Event listeners can block requests or throw exceptions that break authentication. **Fix:** decouple writes, enforce timeouts, use bounded queues/reliable brokers, and apply a sound error policy without turning fail-open.

### Mistake 10 — Adding `@Async` and Assuming Zero Event Loss

In-memory queues can lose events on crashes. **Fix:** use a transactional outbox or durable queue when auditing is mandatory, and monitor lag/retries/dead letters.

### Mistake 11 — Auditing "Role Changed" Before Commit

The business transaction rolls back while the audit claims success. **Fix:** separate attempted from committed actions; use after-commit hooks or outbox patterns per reliability needs.

### Mistake 12 — Leaving `/actuator/auditevents` Unrestricted

The endpoint can expose identities and sensitive events. **Fix:** never expose publicly; enforce network/RBAC protections, audit queries, and retention.

### Mistake 13 — Ignoring Duplicates and Schema Versions

Replays or retries can produce duplicate records, and structural changes break queries. **Fix:** use `event_id`, idempotency, `schema_version`, and migration tests.

### Mistake 14 — Treating DEBUG/TRACE Logs as the Only Audit Store

Log verbosity can be turned off, internal messages are unstable, and rotation/retention differ from audit requirements. **Fix:** emit stable audit event types to controlled durable storage; keep DEBUG strictly for troubleshooting.

### Mistake 15 — "More Audit Data Equals More Security"

Recording raw requests, tokens, and PII increases blast radius if the audit store is breached. **Fix:** enforce data minimization, encryption, access separation, audit-only schemas, and privacy reviews.

## 13. Checklist for Real-World Projects

1. Clearly define which **authentication events**, **authorization events**, and **business audit events** must be captured—and which must not.
2. Check your Spring Security version, whether `AuthenticationEventPublisher`/`AuthorizationEventPublisher` are registered, and whether all flows pass through the expected publishers.
3. Define a stable schema: event ID, UTC timestamp, actor, target, action, outcome, reason code, correlation ID, schema version.
4. Never copy `Authentication`, requests, tokens, passwords, cookies, or method arguments into audits.
5. For access denials, test URL authorization, method security, CSRF, and gateway rejections; never just count 403s.
6. For authentication failures, separate bad credentials, account state, and identity dependency failures; avoid locking out users during backend outages.
7. For business operations, distinguish attempted, authorized, and committed; mark success only after real commit.
8. Choose storage with appropriate durability, retention, and immutability; **never use `InMemoryAuditEventRepository` as production evidence**.
9. Govern operator/auditor access, encryption, networks, and audit query endpoints; audit reads/exports when required.
10. Harden delivery paths: bounded retries, idempotency, dead-letter handling, dropped-event metrics, and gap detection.
11. Test 200/401/403 paths, event emission, content redaction, failure/restart recovery, and deduplication together.
12. After deployment, reconcile event counts by definition against dashboards/traces, investigate discrepancies, and update runbooks.

## 14. Summary

- Spring Security can emit **authentication success/failure events** and **authorization denied events**, provided appropriate publishers/hooks are configured and real flows are tested.
- `@EventListener` receives signals; it **does not create durable audit logs on its own**. Spring Boot Actuator provides `AuditEventRepository` to store and query audit events.
- `SpringAuthorizationEventPublisher` in Spring Security 6.3 focuses on denials; do not enable every granted event out of habit due to volume and privacy concerns.
- A good audit trail captures **who – did what – to which resource – when – outcome – reason – correlation ID** while minimizing sensitive data.
- "Authorized" differs from "transaction committed"; use after-commit or outbox patterns when audits track critical mutations.
- `InMemoryAuditEventRepository` is a learning/dev tool, not durable enough for production. Production audits need durable storage, access control, retention, deduplication, and loss monitoring.
- Test not only HTTP statuses but also emitted events, actors/outcomes, absence of secrets, error classification, and failure-path recording.

## Official Reference Documentation

- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/events.html
- Spring Security — Authorization Events: https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/events.html
- Spring Security 6.3 API — `SpringAuthorizationEventPublisher`: https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html
- Spring Security 6.3 API — `AuthorizationDeniedEvent`: https://docs.spring.io/spring-security/site/docs/6.3.2/api/org/springframework/security/authorization/event/AuthorizationDeniedEvent.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authorization for HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot — Auditing (Actuator): https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html
- Spring Boot — Audit Events Endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/auditevents.html
- Spring Boot — Actuator Endpoint Security: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html