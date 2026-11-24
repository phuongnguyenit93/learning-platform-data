# AuthorizationDeniedEvent and Investigative Data

In Spring Security, a denied request is typically seen as **HTTP 403**, **HTTP 401**, or an `AccessDeniedException`. For system operations, knowing only the HTTP status code is not enough: you need to answer **who** made the request, **which resource or operation** was blocked, **which control layer** made the decision, and **which request/trace** links that event to application logs. `AuthorizationDeniedEvent` is an important hook for collecting evidence of an **authorization denial decision** in Spring Security.

This lesson belongs to the **Events and Auditing** group in the **Spring Security - authorization** module. Examples use **Spring Boot 3.5.x, Spring Security 6.x (Servlet), Java 17+**. The event mechanism can appear in both servlet HTTP authorization and method security; exact API details should be verified against the version in use.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Describe the timing and roles of `AuthorizationDeniedEvent`, `AuthorizationEventPublisher`, and `SpringAuthorizationEventPublisher`.
- Distinguish a **denial decision**, an **exception**, an **HTTP response**, an **authentication failure**, and a **durable audit record**.
- Read key data from `AuthorizationDeniedEvent`; identify which parts must be enriched from the request, SecurityContext, MDC/tracing, or business policy.
- Build a working listener to record HTTP and method denials; correlate `requestId` with observed outcomes.
- Design audit logs that are useful for investigations while avoiding passwords, tokens, cookies, bodies, sensitive parameters, and raw Java objects.
- Test 401/403 cases and distinguish access-rule denials from CSRF, authentication failures, and denials that do not pass through event publishing.

## 2. What Does AuthorizationDeniedEvent Actually Represent?

`AuthorizationDeniedEvent<T>` belongs to the package `org.springframework.security.authorization.event` and is a Spring `ApplicationEvent` indicating that an authorization check returned a **non-granted** result. The event carries information about the check request; it is **not** a complete description of the HTTP call or the full investigative reason.

Conceptual flow:

```text
HTTP request / method invocation
          |
          v
AuthorizationManager checks permissions
          |
          +--> Granted: continue execution
          |      (granted events are NOT published by default)
          |
          +--> Denied: AuthorizationEventPublisher
                     |
                     v
              AuthorizationDeniedEvent
                     |
                     +--> @EventListener -> audit/log/metric
                     |
                     v
              Block call or throw exception
                     |
                     v
              Handle appropriate response (401/403...)
```

The event is published **at the authorization decision**. The HTTP response is formed in a different layer, depending on whether the caller is authenticated and how `AuthenticationEntryPoint` / `AccessDeniedHandler` are configured. Therefore:

- `AuthorizationDeniedEvent` **is not synonymous** with "HTTP 403 was returned". For an anonymous user, a denial can trigger the authentication flow and ultimately return **401** (Basic/Bearer APIs) or **302** to a login page.
- `AuthorizationDeniedEvent` **is not** `AuthenticationFailureEvent`. Wrong passwords or invalid tokens are typically handled during authentication; do not count those failures as missing-permission decisions unless an authorization check was actually denied as well.
- `AuthorizationDeniedEvent` **is not** Spring Boot Actuator's `AuditEvent`. It is an in-process event; if only a console-logging listener exists, there is no guarantee of durable retention, querying, access control, or immutability.
- Not **every HTTP 403** originates from `AuthorizationDeniedEvent`: for example, failed CSRF checks, custom filters, gateway errors, or error codes returned directly by a controller.

## 3. Components and Publishing Conditions

### 3.1. Event Publisher

`AuthorizationEventPublisher` is the interface used by authorization components to publish events. `SpringAuthorizationEventPublisher` integrates with Spring's `ApplicationEventPublisher`; Spring Security's standard setup publishes **denial events** by default and does not publish every grant because the volume can be very large.

Register the publisher bean explicitly:

```java
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new SpringAuthorizationEventPublisher(applicationEvents);
}
```

Once authorization components use the configured publisher, you can listen:

```java
@EventListener
public void onDenied(AuthorizationDeniedEvent<?> event) {
    // Select permitted audit fields; do not serialize the raw event.
}
```

**Integration point to verify:** having a publisher bean and a listener is only a necessary condition. The component enforcing authorization must actually send decisions to the publisher. `AuthorizationFilter` supports `setAuthorizationEventPublisher(...)` and the method authorization system has event publishing support. If you substitute custom filters, managers, or legacy mechanisms, test the specific path rather than assuming every denial will emit an event.

In Spring Security 6.x, `AuthorizationDeniedEvent` can be constructed from `AuthorizationResult`; older APIs centered on `AuthorizationDecision` have deprecated versions. New code should use `getAuthorizationResult()` and `isGranted()`, avoiding deprecated APIs when building audits.

### 3.2. Servlet Authorization and Method Authorization

**In HTTP URLs:** `AuthorizationFilter` invokes `AuthorizationManager<HttpServletRequest>` to check rules from `authorizeHttpRequests`. The object in a denial event is typically `HttpServletRequest`. The listener can observe the HTTP method, request URI, and request-time context; however, sensitive data must be stripped before logging.

**In method security:** when `@EnableMethodSecurity` is enabled, interceptors can enforce `@PreAuthorize` / `@PostAuthorize`. A denial may carry a `MethodInvocation` or a method invocation/result object type depending on when the check occurs. For a safe identifier, extract the **class and method name**, avoiding raw `getArguments()` or return objects because they frequently contain business data.

**A single request can have multiple checkpoints:** authorization at the URL, then at the service, and then at the object level. The number of events does not necessarily equal the number of requests, users, or 403 responses. If a request is blocked at the filter before reaching the controller, method security is never invoked.

## 4. Event API: What Data Is Actually Available?

| Data / API | Meaning | Investigative limitation |
| --- | --- | --- |
| `event.getAuthentication()` | `Supplier<Authentication>` associated with the decision; call `.get()` to access `Authentication` when appropriate | May be anonymous; credentials/principal inside the object may be sensitive |
| `event.getObject()` | The object being access-controlled, of type `T` | May be `HttpServletRequest`, `MethodInvocation`, or another object; unsafe to serialize as-is |
| `event.getAuthorizationResult()` | Authorization result; `isGranted()` is `false` for a denied event | Does not necessarily contain a "policy name", missing authority, business reason, or HTTP status |
| `event.getTimestamp()` | Creation time of the Spring `ApplicationEvent` (milliseconds since epoch) | Not the HTTP response completion timestamp, nor the durable write timestamp |
| `event.getSource()` | Inherited source from Spring event | Should not be treated as safe log material; use the typed APIs above |

Most investigative data requires **enrichment** from other sources: server-generated request ID, trace/span ID, route template, application-defined policy name or rule code, the tenant/resource ID checked, policy version, internal actor ID, final HTTP response status, service name, and runtime environment.

**Do not infer a specific root cause** solely from `isGranted() == false`. It could be a missing authority, ownership/tenant rule, resource state, custom policy, or another data condition. If the application wants to record a `reasonCode`, design it in the policy layer under a controlled contract; `AuthorizationDeniedEvent` has no universal `getReason()` property by default.

## 5. Runnable Example: Publishing Events and Logging Denials with a Correlation ID

The example uses HTTP Basic so it can be tested directly with `curl`. There are two policies:

- `GET /api/admin/reports` allows `ROLE_ADMIN` only: denial happens in the **HTTP filter**.
- `GET /api/reports/export` requires authentication at the URL, while the service method requires the `REPORT_EXPORT` authority: denial happens in **method security**.

A servlet filter assigns `X-Request-Id` and puts the same ID into SLF4J MDC. The listener logs only a normalized route/policy label, the demo actor, and the object type name; it does not dump headers, principals, or request bodies.

### 5.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>authorization-audit</artifactId>
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

### 5.2. src/main/java/com/example/audit/AuthorizationAuditApplication.java

```java
package com.example.audit;

import java.io.IOException;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.aopalliance.intercept.MethodInvocation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.context.event.EventListener;
import org.springframework.security.access.prepost.PreAuthorize;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizationAuditApplication.class, args);
    }

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher events) {
        return new SpringAuthorizationEventPublisher(events);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password("{noop}reader123")
                        .authorities("ROLE_USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin123")
                        .authorities("ROLE_ADMIN", "REPORT_EXPORT")
                        .build());
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/admin/reports").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class ReportController {

        private final ReportService reportService;

        ReportController(ReportService reportService) {
            this.reportService = reportService;
        }

        @GetMapping("/api/public")
        Map<String, String> publicEndpoint() {
            return Map.of("result", "public");
        }

        @GetMapping("/api/admin/reports")
        Map<String, String> adminReports() {
            return Map.of("result", "admin-only");
        }

        @GetMapping("/api/reports/export")
        Map<String, String> export() {
            return reportService.export();
        }
    }

    @Service
    static class ReportService {

        @PreAuthorize("hasAuthority('REPORT_EXPORT')")
        public Map<String, String> export() {
            return Map.of("result", "export-ready");
        }
    }

    // Filter outside the Spring Security filter chain so correlation
    // applies even when authentication rejects before authorization.
    @Component
    @Order(Ordered.HIGHEST_PRECEDENCE)
    static class CorrelationIdFilter extends OncePerRequestFilter {

        @Override
        protected void doFilterInternal(
                HttpServletRequest request, HttpServletResponse response,
                FilterChain chain) throws ServletException, IOException {
            String requestId = UUID.randomUUID().toString();
            response.setHeader("X-Request-Id", requestId);
            MDC.put("requestId", requestId);
            try {
                chain.doFilter(request, response);
            } finally {
                MDC.remove("requestId");
            }
        }
    }

    @Component
    static class DeniedAuditListener {

        private static final Logger log =
                LoggerFactory.getLogger(DeniedAuditListener.class);

        @EventListener
        public void onDenied(AuthorizationDeniedEvent<?> event) {
            Authentication auth = event.getAuthentication().get();
            String actor = (auth == null
                    || auth instanceof AnonymousAuthenticationToken)
                    ? "anonymous" : auth.getName();

            Object securedObject = event.getObject();
            String layer;
            String resource;

            if (securedObject instanceof HttpServletRequest request) {
                layer = "HTTP";
                // Log a safe route label; avoid logging URIs containing IDs/PII.
                resource = request.getRequestURI()
                        .startsWith("/api/admin/")
                        ? "api.admin" : "api.other";
            } else if (securedObject instanceof MethodInvocation invocation) {
                layer = "METHOD";
                resource = invocation.getMethod().getDeclaringClass()
                        .getSimpleName()
                        + "#" + invocation.getMethod().getName();
            } else {
                layer = "OTHER";
                resource = "secured-object";
            }

            // Learning sample: actor is a controlled demo username.
            // In production, use an internal actor ID or pseudonym.
            log.warn(
                    "event=authorization_denied at={} requestId={} "
                    + "actor={} layer={} resource={} granted={}",
                    Instant.ofEpochMilli(event.getTimestamp()),
                    MDC.get("requestId"),
                    actor,
                    layer,
                    resource,
                    event.getAuthorizationResult().isGranted());
        }
    }
}
```

**Why does this code matter?**

1. `@Bean AuthorizationEventPublisher` connects authorization events to Spring application events. The listener uses `@EventListener` to handle `AuthorizationDeniedEvent<?>`.
2. `@EnableMethodSecurity` enables `@PreAuthorize` checks on service beans. The controller **calls through a Spring-managed bean**, allowing the AOP interceptor to execute; self-invocation on a method in the same object can bypass the proxy.
3. The HTTP policy checks `/api/admin/reports` before the controller is called. `reader` is denied at `AuthorizationFilter`.
4. The URL-level policy for `/api/reports/export` only requires authentication; user `reader` passes the URL check and is then blocked at `ReportService#export` due to missing `REPORT_EXPORT`.
5. The filter generates a server-side ID and writes it to both MDC and the response header so investigators can correlate the same request. `finally` clears the MDC, preventing data leaks into another request when servlet threads are reused.
6. The listener checks the object type before extracting fields; it does not call `securedObject.toString()`, and does not log method arguments or the full `Authentication`. For production systems, extend according to the safe-field allowlist and data-protection rules in section 7.
7. `{noop}` accounts and HTTP Basic are for local demo purposes only. Production deployments must use hashed password storage/an appropriate identity provider, TLS, an appropriate auth mechanism, and a CSRF policy matching the credential model.

### 5.3. Running and Verifying

Place `pom.xml` and the Java file at the exact paths above. With JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Maven compiles and runs the application with Spring dependencies; you cannot just run `javac AuthorizationAuditApplication.java` without supplying the full classpath.

Try the cases:

```bash
# No credentials: HTTP Basic challenges for authentication (typically HTTP 401).
curl -i http://localhost:8080/api/admin/reports

# Authenticated, missing ROLE_ADMIN: HTTP 403, denial at HTTP layer.
curl -i -u reader:reader123 http://localhost:8080/api/admin/reports

# Authenticated, missing REPORT_EXPORT: HTTP 403, denial at method layer.
curl -i -u reader:reader123 http://localhost:8080/api/reports/export

# Sufficient permissions: HTTP 200.
curl -i -u admin:admin123 http://localhost:8080/api/admin/reports
curl -i -u admin:admin123 http://localhost:8080/api/reports/export

# Wrong password: HTTP 401 due to authentication failure.
curl -i -u reader:wrong http://localhost:8080/api/reports/export

# Public endpoint: HTTP 200.
curl -i http://localhost:8080/api/public
```

The two successful responses have exact JSON bodies from the controller:

```json
{"result":"admin-only"}
```

```json
{"result":"export-ready"}
```

Illustrative log (timestamp, requestId, and log prefix vary on each run):

```text
event=authorization_denied at=2026-11-05T10:00:00Z requestId=<server-generated-id> actor=reader layer=HTTP resource=api.admin granted=false
event=authorization_denied at=2026-11-05T10:01:00Z requestId=<server-generated-id> actor=reader layer=METHOD resource=ReportService#export granted=false
```

**This is an illustrative log, not fixed stdout.** With HTTP Basic, `401` usually includes a `WWW-Authenticate` header; the listener does not know the final HTTP status from the event alone. Match `X-Request-Id` from the response with `requestId` in the log.

### 5.4. Automated Testing with MockMvc and Spring ApplicationEvents

File `src/test/java/com/example/audit/AuthorizationAuditApplicationTests.java`:

```java
package com.example.audit;

import jakarta.servlet.http.HttpServletRequest;
import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthorizationAuditApplicationTests {

    @Autowired MockMvc mvc;
    @Autowired ApplicationEvents events;

    @Test
    @WithMockUser(roles = "USER")
    void urlDenialPublishesEvent() throws Exception {
        mvc.perform(get("/api/admin/reports"))
                .andExpect(status().isForbidden());

        assertTrue(events.stream(AuthorizationDeniedEvent.class)
                .anyMatch(event ->
                        event.getObject() instanceof HttpServletRequest));
    }

    @Test
    @WithMockUser(roles = "USER")
    void methodDenialPublishesEvent() throws Exception {
        mvc.perform(get("/api/reports/export"))
                .andExpect(status().isForbidden());

        assertTrue(events.stream(AuthorizationDeniedEvent.class)
                .anyMatch(event ->
                        event.getObject() instanceof MethodInvocation));
    }
}
```

Run:

```bash
mvn test
```

The two tests verify **that events are emitted** at the URL and method layers; they do not depend on log strings or random UUIDs. When expanding, add tests for anonymous, admin, invalid authentication, CSRF, route patterns, and domain-specific policies. If a custom manager/filter does not use the publisher, these tests will catch the missing events.

## 6. Designing Audit Data for Incident Investigation

Do not send the raw event to Elasticsearch, Kafka, or a database table. Transform it into an **audit record with a clear schema** and controlled fields. Example schema:

| Field | Trusted source | Investigative value |
| --- | --- | --- |
| `eventId` | Audit system UUID | Distinguish records, handle duplicate writes |
| `occurredAt` | `event.getTimestamp()` or observation clock | Order the UTC timeline |
| `requestId`, `traceId`, `spanId` | Server-generated middleware/tracing | Link gateway → security → service → DB |
| `service`, `environment`, `instance` | Deployment configuration | Identify pod/service/version |
| `actorId` | Normalized internal identity/subject | Identify principal with controlled access; do not include tokens |
| `authenticationType` | Normalized authentication info | Distinguish anonymous, session, API key, Bearer... |
| `tenantId` | Verified tenant context | Distinguish cross-tenant denials |
| `layer` | HTTP / METHOD / POLICY | Identify blocking layer |
| `resourceType`, `resourceId` | Route template, domain resource metadata | Distinguish endpoint and resource; IDs may need pseudonymization |
| `action` | GET/POST or operation code | Requested action |
| `policyId`, `policyVersion` | Application-managed policy | Explain impact when rules change |
| `decision` | `AuthorizationResult.isGranted()` | `DENY` for this event |
| `reasonCode` | Application-specific authorization logic | Standardized reason like `MISSING_AUTHORITY` or `CROSS_TENANT` when truly known |
| `httpStatus` | Final response observation | Cross-check 401/403/redirect; **not available in the event** |
| `clientIp` | Trusted edge/proxy chain, if permitted to store | Investigate network behavior; do not blindly trust client-supplied `X-Forwarded-For` |

A **normalized** record might look like this; all values are illustrative:

```json
{
  "eventId": "35fc6115-6f39-4702-bcdc-3af94f8d75aa",
  "eventType": "AUTHORIZATION_DENIED",
  "occurredAt": "2026-11-05T10:01:00Z",
  "service": "report-api",
  "environment": "staging",
  "requestId": "c5e6e50f-6f69-4d56-9ab3-8d2d0ea6a14b",
  "traceId": "7b9a2240924d7b4e918acde701682071",
  "actorId": "user-42",
  "tenantId": "tenant-7",
  "layer": "METHOD",
  "resourceType": "REPORT_EXPORT",
  "action": "EXPORT",
  "policyId": "report.export.permission",
  "policyVersion": "2026-11-01",
  "decision": "DENY",
  "reasonCode": "MISSING_AUTHORITY",
  "httpStatus": 403
}
```

**Distinguish data sources:** the runnable Java snippet above logs only a minimal set of fields. The JSON just shown is a **target schema sample**; it is not an out-of-the-box payload of `AuthorizationDeniedEvent`. Fields such as `tenantId`, `reasonCode`, `policyVersion`, and `httpStatus` require separate instrumentation, domain policies, and audit recording paths.

### Notes on Logging Sensitive Information

- **Do not log** `Authorization` headers, Bearer tokens, Basic credentials, session cookies, passwords, OTPs, secrets, full JWT claims, request/response bodies, or method arguments by default.
- **Do not directly serialize** `HttpServletRequest`, `Authentication`, `Principal`, `MethodInvocation`, entity/domain objects, or exception stack traces into audit records. They can contain personal information, credentials, and huge object graphs.
- For URLs containing sensitive IDs, use a `route template` (e.g., `/orders/{id}`) instead of raw `/orders/123456`; IDs needed for investigations must be classified and protected.
- Usernames/IPs can be personal data. Retain only necessary data, pseudonymize where appropriate, and separate read access to security logs from general operators.
- Avoid **log injection**: user-controlled data can contain newlines/control characters. Use structured logging, encode/sanitize strings, and enforce length limits.
- Do not take client-supplied `X-Request-Id` or `X-Forwarded-For` as trusted sources by default. A trusted edge may forward/normalize them; otherwise, generate IDs on the server.
- Define retention periods, read access controls, encryption at rest and in transit, policy-driven deletion, alerts, and auditing of access to the audit store itself.

## 7. Investigating a Denial Incident: Practical Workflow

**Scenario:** a user reports "I was just granted report export permission, but the API still returns 403".

1. **Confirm the trail:** gather UTC timestamp, endpoint, method, request ID/trace ID from the response or telemetry, service, and environment. Avoid asking the user to send credentials/tokens.
2. **Locate the event:** filter `AUTHORIZATION_DENIED` by `requestId` and time. Check whether an event exists, its `layer`, and the resource/policy name. Do not infer from HTTP 403 alone.
3. **Confirm identity:** check actor/tenant in the identity system and the authorities issued for **that request**, not only the current state. Tokens may carry stale claims, or a user cache may not have refreshed yet.
4. **Cross-check rules:** check `hasRole` vs `hasAuthority`, `ROLE_` prefixes, object-level policies, tenant ownership, policy version, rollout time, and related feature flags. A `DENY` result alone does not pinpoint which rule fired.
5. **Identify the blocking layer:** `HTTP` shows the request was blocked before the controller; `METHOD` shows the request entered the application and a method interceptor denied it; `OTHER` requires further classification.
6. **Cross-check outputs:** using the same `requestId`, inspect auth logs, policy-layer audits, gateway, CORS/CSRF, and final status. If it is `401`, check authentication; if 403 with no event, check another component producing 403.
7. **Form an evidence-backed conclusion:** document the verifiable cause, log sources, checked rule/version, when permissions changed, and remediation action. Do not "fix" by broadening permissions before understanding the policy.
8. **Verify after fixing:** reproduce the same type of request in an appropriate environment, inspect status, events/logs/correlation ID, and run regression tests ensuring unintended permissions were not granted.

Example of a valid deduction:

```text
Request A -> 403
Audit: layer=METHOD, resource=ReportService#export, actor=user-42
Policy: REPORT_EXPORT required, effective authorities did not include it
Identity: role change applied after token was issued
=> Evidence of stale claims/authorities in request A;
   check token refresh/re-issue flow and authorization cache.
```

This is an investigative example, **not** a conclusion applicable to every 403 incident. If authority data at request time was not safely recorded, rely on trusted identity/token validation telemetry; do not infer with certainty from current roles.

## 8. Cases That Commonly Cause Confusion

| Observation | Is an AuthorizationDeniedEvent guaranteed? | Where to check |
| --- | --- | --- |
| Anonymous caller invokes a login-required API, returns 401 | May occur when URL authorization makes a denial decision | Authentication entry point, anonymous filter, rules, and publisher |
| Authenticated caller lacks `ROLE_ADMIN`, returns 403 | Usually yes with `AuthorizationFilter` + publisher | Route matcher, authorities, HTTP event |
| `@PreAuthorize` denies a service method | Yes when method interceptor is active and publisher works | `@EnableMethodSecurity`, Spring proxy, method event |
| Wrong Basic password or expired Bearer token | Not a guaranteed `AuthorizationDeniedEvent` | Authentication events, failure handler/token validator |
| POST missing CSRF token, returns 403 | Not necessarily | `CsrfFilter` and CSRF token strategy |
| Controller directly returns `ResponseEntity.status(403)` | Does not automatically emit an authorization event | Controller/business path; needs separate business audit |
| Gateway/WAF/nginx denies before reaching Spring | Spring app never sees the request | Edge/gateway audit and trace |
| Using a custom `AccessDeniedHandler` | The handler changes the response, does not itself ensure events | Check where decisions are made and the publisher |

**Absence of an event does not prove a request was allowed**; the request may have been blocked before authorization, a listener may not be registered, the publisher may not be wired, method security may be bypassed, events may be dropped during storage/delivery, or correlation IDs may be missing.

**Presence of an event is also not enough to conclude a security incident:** a burst of denials could be normal permission testing, a misconfigured client, or a permission-probing attack. Look at frequency patterns, actor, tenant, route, trusted network source, policy changes, and other signals.

## 9. Audit Reliability, Performance, and Threat Model

Spring `@EventListener` with the default multicaster typically executes **synchronously** on the publishing thread. A listener that runs slow DB queries, makes HTTP calls to a SIEM, or performs blocking network writes can increase request latency. An unhandled exception thrown by a listener can also affect the request depending on publisher/multicaster configuration.

- Keep handlers lightweight: map required fields, normalize, and hand off to logging/sinks with proper backpressure. If durable storage is required, consider reliable queues, bounded retries, dead-letter queues, and event-loss detection.
- Choose a clear data commitment level: **best-effort logs** differ from retained, evidentiary audits for compliance. Do not claim "every denial is saved" if the system lacks write acknowledgments, error monitoring, and sink-failure policies.
- With async processing, do not assume MDC, SecurityContext, or the servlet request automatically propagate to another thread. Snapshot safe data **before enqueuing**, and propagate tracing context using supported mechanisms.
- Protect the system against denial storms: rate-limit/aggregate/alert on appropriate analytical dimensions; avoid flooding with granted events. If sampling denials to reduce load, explicitly document the impact on audit completeness.
- Do not log full policy evaluation state; rule conditions may contain sensitive data. Only include classified, permitted event codes.
- Synchronize clocks across systems and record both `occurredAt` and ingestion time if analyzing transport/queue lag.

## 10. Testing and Operations Checklist

Before considering denial collection complete, confirm:

- [ ] The publisher is registered and the active HTTP/method paths actually invoke it.
- [ ] `@EventListener` receives events for denials from URLs and `@PreAuthorize`; tests verify the **secured object type**, not only the status code.
- [ ] `permitAll` and authorized requests are not miscounted as denied; granted events are not enabled wholesale.
- [ ] Anonymous, 401, 403, invalid credentials, CSRF, and custom error paths are classified using evidence.
- [ ] Multiple checks within one request do not miscount blocked users or unique requests.
- [ ] Server-generated correlation IDs appear in responses and audits; tracing works across proxies according to trust boundaries.
- [ ] No credentials, sensitive headers, payloads, raw objects, raw dynamic URLs, or unnecessary PII are logged.
- [ ] Roles/authorities/tenants, policy versions, and reason codes come from real sources; do not assign a default cause to every denial.
- [ ] Alert thresholds, retention, read access controls, sink-failure handling, and end-to-end verification exist.
- [ ] Run `mvn test` and perform sample requests in a test environment; inspect both the audit output and the actual HTTP responses.

## 11. Official References

- Spring Security: [Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html) — how to register the publisher, listeners, and why grants are not published by default.
- Spring Security: [AuthorizationDeniedEvent API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/event/AuthorizationDeniedEvent.html) — secured object and event data types.
- Spring Security: [AuthorizationEvent API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/event/AuthorizationEvent.html) — authentication supplier, authorization result, timestamp.
- Spring Security: [Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `@EnableMethodSecurity` and denied events in the method interceptor.
- Spring Security: [AuthorizationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/intercept/AuthorizationFilter.html) — `setAuthorizationEventPublisher`.
- Spring Security: [Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html) — distinguishing failed authentication from authorization denial.

**Remember:** `AuthorizationDeniedEvent` is evidence of an **authorization denial decision**, whereas data sufficient for **investigation** must be safely and verifiably joined with identity/policy, request/trace, and HTTP outcome.