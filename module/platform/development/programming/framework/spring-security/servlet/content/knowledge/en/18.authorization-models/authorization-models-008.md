# Authorization Events and Tracking Denied Decisions

> **Scope:** Spring Security **Servlet stack**, Java 17+, Spring Boot 3.x / Spring Security 6.x. This article focuses on **authorization events**: when an `AuthorizationManager` decides to deny a request, how to publish/receive `AuthorizationDeniedEvent`, relate decisions to HTTP 403/401 **without equating** every 403 error to an authorization denial, measure metrics to detect anomalies, and write safe audit logs. Examples illustrate `AuthorizationEventPublisher`, `SpringAuthorizationEventPublisher`, `@EventListener`, a `SecurityFilterChain`, `MockMvc` tests, and a standalone Java 17 example. Do not treat events as an authorization mechanism that replaces authorization policies.

## 1. The Practical Problem: "403" Alone Does Not Explain What Happened

An application can return HTTP 403 for several reasons:

- An **authenticated** user lacks `ROLE_ADMIN` when calling `GET /admin`.
- A user has the right role, yet a **POST has a missing or invalid CSRF token**, so `CsrfFilter` blocks it before endpoint authorization runs.
- A controller, gateway, or custom `AccessDeniedHandler` returns 403 directly.
- `@PreAuthorize` on a service denies access even though HTTP-level authorization let the request proceed.
- An object/tenant/ownership policy inside a business service denies access to a specific record.

On the other hand, **unauthenticated** users may receive 401 or a 302 redirect to the login page rather than 403. Therefore, "counting all 403 status codes" is an **HTTP metric**, not a faithful record of **authorization denial decisions**.

**Lesson question:** how do you observe when Spring Security actually issued a denied **authorization decision**, distinguish it from authentication failures and CSRF failures, and use that signal for debugging, auditing, and alerting without leaking sensitive data?

### Logical Model

~~~text
HTTP request
  |
  v
FilterChainProxy -> matching SecurityFilterChain
  |
  | Authentication filter / SecurityContext
  |   -> establish principal + GrantedAuthority
  |
  | CsrfFilter (when applicable)
  |   -> invalid CSRF? request may get 403 RIGHT HERE
  |
  v
AuthorizationFilter
  |
  | select AuthorizationManager by request matcher
  | -> produce / obtain authorization result
  |
  +-- GRANTED
  |      -> proceed to Servlet/MVC/controller
  |
  +-- DENIED
         |
         +-- AuthorizationEventPublisher
         |      -> AuthorizationDeniedEvent
         |      -> safe listener (audit/metrics/alerts)
         |
         +-- AccessDeniedException
                -> ExceptionTranslationFilter
                -> AccessDeniedHandler / AuthenticationEntryPoint
                -> typically 403 or 401/302 depending on context
~~~

**Event, decision, and HTTP response are three distinct concepts:**

1. **Decision** is the outcome of evaluating privileges at an authorization point.
2. **Event** is a system notification published to observe that decision.
3. **HTTP response** is produced by multiple filters/handlers and can carry a status code that does not reflect that decision alone.

A denial event does not automatically mean "the app sent a 403"; the request could pass through error dispatch, another handler, or another entry point. Conversely, a 403 does not guarantee a denial event occurred.

## 2. Relevant Classes and Interfaces

| Component | Role |
| --- | --- |
| `AuthorizationManager<T>` | Evaluates whether the current `Authentication` satisfies policy for object `T`. |
| `AuthorizationResult` / `AuthorizationDecision` | Carries granted/denied outcome; result APIs vary across Spring Security 6.x releases. |
| `AuthorizationFilter` | Bridges the authorization manager and Servlet requests, optionally publishing events via a configured publisher. |
| `AuthorizationEventPublisher` | Contract for publishing authorization decision notifications. |
| `SpringAuthorizationEventPublisher` | Publisher implementation using Spring's `ApplicationEventPublisher` to emit events. |
| `AuthorizationDeniedEvent<T>` | Event representing a denied authorization decision. |
| `AuthorizationGrantedEvent<T>` | Event representing a granted decision, when a publisher is configured to emit it. |
| `@EventListener` | How a Spring bean registers a handler method for events. |
| `AccessDeniedHandler` | Translates access denial into an HTTP response; does **not** replace an event publisher. |
| `AuthenticationEntryPoint` | Initiates authentication when a request lacks suitable authentication (401/redirect). |
| `AuthenticationFailure...` events | Signals belonging to **authentication**, distinct from authorization denials. |

In newer Spring Security 6.x versions, authorization APIs increasingly adopt the broader `AuthorizationResult`. Older snippets or Javadocs may mention `AuthorizationDecision` or expose getters with different names. **Do not copy an accessor from another version's docs assuming it compiles on every 6.x release.** The practical listener below accepts the event type and increments a counter, avoiding reliance on version-sensitive accessors.

### Responsibilities of AuthorizationManager

Example policy:

~~~java
.requestMatchers("/admin").hasRole("ADMIN")
.requestMatchers("/reports").hasAuthority("REPORT_READ")
~~~

For a user holding `ROLE_USER` without `ROLE_ADMIN`, `GET /admin` will be denied by authorization. `hasRole("ADMIN")` checks `ROLE_ADMIN` under the default prefix convention; `hasAuthority("REPORT_READ")` checks the exact string `REPORT_READ`.

However, the manager does not verify passwords itself. Identity/authorities must come from a trusted authentication mechanism: form login, HTTP Basic, JWT verifier, or a proper custom provider. If a custom provider grants wrong authorities, the event publisher only observes **decisions made on that wrong privilege set**—it cannot fix the privilege-granting bug.

## 3. What Information Does AuthorizationDeniedEvent Carry?

A denied event typically associates with:

- A reference or lazy supplier for the `Authentication` being evaluated.
- The object evaluated by the authorization manager: the request (or related context) in HTTP authorization, or a method invocation when method security is active.
- The denied authorization result.

Because the target object type `T` varies by call site, **never cast every event target to `HttpServletRequest`**. Also avoid calling `event.toString()` or logging raw authentication/event/request objects: they can contain sensitive attributes, query strings, user details, session references, or internal structures.

When auditing, intentionally extract only **permitted** fields (for example, normalized action/route, policy name, principal category, server-generated trace ID), and **never** put raw credentials, cookies, CSRF tokens, `Authorization` headers, or full request bodies into logs.

### A Denial Event Is Not an AccessDeniedException

`AccessDeniedException` represents a failed privilege check in the exception-handling flow. An event may be emitted **before** the exception is translated into HTTP 403; a custom `AccessDeniedHandler` can also handle an exception without emitting a corresponding event.

Both are useful, for different purposes:

~~~text
AuthorizationDeniedEvent: "An authorization decision was denied"
AccessDeniedException:    "Execution flow encountered access denial"
HTTP 403:                 "Response indicating continuation is forbidden"
~~~

**Do not equate them by counting:** a single HTTP request can undergo multiple authorization checks (web + method, forwards/error dispatch, custom managers), producing multiple decision events. When you need a *denied requests* metric, use clear correlation/deduplication rules and policies; never treat the raw total of `AuthorizationDeniedEvent`s as "the number of users who got 403" without understanding the structure.

## 4. How Do You Enable Publishing Authorization Events?

Spring Security provides `AuthorizationEventPublisher`. A typical way in a Spring Boot Servlet app is declaring a publisher bean so Spring Security can publish decisions through Spring's application event system.

Create `src/main/java/com/example/authzaudit/AuthorizationEventsConfig.java`:

~~~java
package com.example.authzaudit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;

@Configuration
public class AuthorizationEventsConfig {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher applicationEvents) {

        return new SpringAuthorizationEventPublisher(applicationEvents);
    }
}
~~~

**Essential points to understand:**

1. `SpringAuthorizationEventPublisher` uses Spring's `ApplicationEventPublisher` to emit the events it is designed to publish.
2. This publisher's default pattern **prioritizes emitting denial events**, rather than turning every granted request into an event. That avoids high event volume when normal web traffic mostly succeeds.
3. Declaring the bean does not alter `hasRole`, `hasAuthority`, or endpoint policies; it changes **observability** of the outcomes.
4. Depending on your version and how you configure custom filters or interceptors, verify that the active authorization component **is actually wired with the publisher**. A custom filter/controller invoking a manager directly will not necessarily pick up this bean automatically. Never assume `@Bean` guarantees monitoring of every decision point system-wide.
5. To verify, send an unauthorized request and confirm the listener receives the event; that proves the pipeline is **truly wired**, better than checking bean names in the context alone.
6. If your project runs on an older Spring Security branch or a newer major version, check the exact packages/constructors/APIs of `spring-security-core`, `spring-security-web`, and `spring-security-config` for your version/BOM. Examples here target compatible Spring Security 6.x models; do not assume identical method names across every release.

### What If You Also Want to Record "Granted" Decisions?

`AuthorizationGrantedEvent` exists to represent granted decisions, yet **simply declaring `SpringAuthorizationEventPublisher` does not emit full granted events by default**. Publishing grants requires customizing the publisher per your version's API and evaluating traffic impact:

- A route like `GET /assets/...` can have millions of success decisions; emitting an event per request creates overhead and high cardinality.
- Compliance audits sometimes require **success** records for sensitive actions. In that case, choose **specific business audit points** rather than flooding events for every URL.
- Sampling may be appropriate for non-mandatory metrics/diagnostics, yet **never** use random sampling in a way that drops legally required audit records.
- Always clarify the data source: `AuthorizationGrantedEvent` may only reflect the manager check, not prove the business operation or DB transaction succeeded.

A custom publisher must preserve exact deny/grant semantics and be load-tested; never turn audit logic into an authorization shortcut.

## 5. Capturing Denied Events with @EventListener

Create `src/main/java/com/example/authzaudit/DeniedEventRecorder.java`:

~~~java
package com.example.authzaudit;

import java.util.concurrent.atomic.LongAdder;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;

@Component
public final class DeniedEventRecorder {

    private final LongAdder deniedDecisions = new LongAdder();

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> ignoredEvent) {
        // Demo: record the count of denied decisions.
        // Do not log Authentication, request, secrets, or the event object.
        deniedDecisions.increment();
    }

    public long count() {
        return deniedDecisions.sum();
    }
}
~~~

**Intentional limitations of this example:**

- `LongAdder` works well for a high-contention counter inside **one JVM**; it is not durable metrics storage and does not aggregate across nodes/pods.
- The method accepts `AuthorizationDeniedEvent<?>` without reading its payload, avoiding accidental logging of sessions/tokens and reducing dependence on version-specific getters.
- When the publisher uses Spring's default synchronous event multicaster, the listener runs on the publishing thread. Never run slow DB queries or HTTP calls inside such a listener.
- If the system moves application events to an async executor, tests cannot assume the counter increments immediately; use proper waiting/eventual-consistency assertions and analyze ordering, retries, and event loss on crash.
- This counter tracks **denied authorization decisions**, not unique users or failed logins; do not use it to auto-lock accounts.

In production, use Micrometer/OTel metrics and a proper audit sink, defining **metric semantics** and permitted fields clearly upfront.

## 6. A Runnable Spring Boot 3 + Spring Security 6.x Demo

Goal: build an easily reproducible flow:

- `GET /public`: accessible to everyone, normally returns 200.
- `GET /admin`: requires `ROLE_ADMIN`.
- `GET /reports`: requires `REPORT_READ`.
- `POST /reports/submit`: requires `REPORT_WRITE` and (with default web session/CSRF settings) a **valid CSRF token**.
- A `reader` account has only `ROLE_USER` and `REPORT_READ`; an `admin` account has `ROLE_ADMIN`, `REPORT_READ`, and `REPORT_WRITE`.
- `DeniedEventRecorder` increments only when the publisher emits an authorization denial; tests verify this with unauthorized requests.

### Structure

~~~text
src/main/java/com/example/authzaudit/
  AuthzAuditApplication.java
  SecurityConfig.java
  AuthorizationEventsConfig.java
  DeniedEventRecorder.java
  DemoController.java

src/test/java/com/example/authzaudit/
  AuthorizationEventsIntegrationTest.java
~~~

Dependencies:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-test        (scope test)
spring-security-test           (scope test)
~~~

All classes share package `com.example.authzaudit`. No database is needed. The learning usernames and passwords below **must never be used in real environments**.

### 6.1. SecurityConfig.java

~~~java
package com.example.authzaudit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-demo-only"))
                .authorities("ROLE_USER", "REPORT_READ")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-demo-only"))
                .authorities(
                    "ROLE_ADMIN", "REPORT_READ", "REPORT_WRITE")
                .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/reports/submit")
                    .hasAuthority("REPORT_WRITE")
                .requestMatchers("/reports/**").denyAll()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // Default CSRF is enabled for unsafe methods such as POST.
        // Do not disable CSRF just to make a POST test pass.
        return http.build();
    }
}
~~~

**Breakdown:**

1. `reader` has `REPORT_READ`, lacking `REPORT_WRITE` and `ROLE_ADMIN`.
2. `admin` has all three privileges; `hasRole("ADMIN")` expects exact authority `ROLE_ADMIN`.
3. `/reports/submit` is bound to **POST**, not opening GET/DELETE on the same path.
4. `anyRequest().denyAll()` lowers the risk of adding endpoints without rules.
5. `httpBasic` is used for the demo without rendering a form login. For cookie-based browser APIs, session/CSRF configuration may differ; check the real threat model.
6. This is a single `SecurityFilterChain`; if a project defines multiple chains, a higher-`@Order` chain may match requests first and alter how events are emitted.
7. `AuthorizationEventsConfig` supplies the publisher bean, while `DeniedEventRecorder` consumes events; the security config does **not** invoke the recorder directly.

Never fold `AuthorizationEventPublisher` into a custom access-control rule like "if the audit sink fails, grant access". Authorization success/failure must be decided by security policy, not telemetry systems.

### 6.2. DemoController.java

~~~java
package com.example.authzaudit;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin";
    }

    @GetMapping("/reports")
    public String readReport() {
        return "report-read";
    }

    @PostMapping("/reports/submit")
    public String submitReport() {
        // Demo does not mutate a DB: returns response directly.
        return "report-submitted";
    }
}
~~~

**Do not have `@GetMapping("/admin")` check `if (username.equals("admin"))` itself**. Privileges are enforced at the Spring Security HTTP authorization layer; business services may add permission/tenant checks, yet never rely on raw usernames alone.

### 6.3. AuthzAuditApplication.java

~~~java
package com.example.authzaudit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthzAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthzAuditApplication.class, args);
    }
}
~~~

Requires JDK 17+ and compatibly resolved Spring Boot dependencies. To run with the project's Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Example localhost requests with **learning** credentials:

~~~bash
curl -i http://localhost:8080/public

curl -i -u reader:reader-demo-only \
  http://localhost:8080/reports

curl -i -u reader:reader-demo-only \
  http://localhost:8080/admin

curl -i -u admin:admin-demo-only \
  http://localhost:8080/admin
~~~

Logical outcomes in the demo:

| Request | Expected | Reason |
| --- | --- | --- |
| Anonymous GET `/public` | 200, body `public` | `permitAll()`. |
| Reader GET `/reports` | 200, body `report-read` | Holds `REPORT_READ`. |
| Reader GET `/admin` | 403 | Lacks `ROLE_ADMIN`; a denied decision may be published. |
| Admin GET `/admin` | 200, body `admin` | Holds `ROLE_ADMIN`. |
| Anonymous GET `/admin` | Usually 401 with HTTP Basic | Needs authentication; do not treat as equivalent to 403. |

No fixed stdout of `curl -i` is shown because headers, cookies, and challenge headers vary by version/server. `curl -u` places credentials on the command line and in process history; use only fake localhost accounts, never real secrets. Production must use TLS and proper credential management.

### 6.4. What a Listener Must NOT Do

~~~java
// ANTI-PATTERN: never copy into a real system.
@EventListener
public void unsafeLogging(
        AuthorizationDeniedEvent<?> event) {
    System.out.println(event); // may expose sensitive data.
}
~~~

This snippet illustrates a bug, not a standalone Java file. Logging the entire event/request/authentication can leak unintended contents or raise PII risk. In the real demo program, the listener only increments a safe counter.

## 7. MockMvc: Proving Events Come from Authorization Denials

Create `src/test/java/com/example/authzaudit/AuthorizationEventsIntegrationTest.java`:

~~~java
package com.example.authzaudit;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationEventsIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired DeniedEventRecorder denied;

    @Test
    void publicRequestSucceedsWithoutAuthentication()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void deniedHttpAuthorizationPublishesDeniedEvent()
            throws Exception {
        long before = denied.count();

        mvc.perform(get("/admin")
                    .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());

        assertTrue(denied.count() > before);
    }

    @Test
    void authorizedAdminRequestIsAllowed() throws Exception {
        mvc.perform(get("/admin")
                    .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void missingWriteAuthorityDeniesEvenWithValidCsrf()
            throws Exception {
        long before = denied.count();

        mvc.perform(post("/reports/submit")
                    .with(csrf())
                    .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());

        assertTrue(denied.count() > before);
    }

    @Test
    void validWriteAuthorityWithCsrfSucceeds()
            throws Exception {
        mvc.perform(post("/reports/submit")
                    .with(csrf())
                    .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-submitted"));
    }

    @Test
    void missingCsrfReturns403ButProvesNothingAboutTheRule()
            throws Exception {
        // Admin has REPORT_WRITE, yet CsrfFilter may block
        // before reaching AuthorizationFilter.
        mvc.perform(post("/reports/submit")
                    .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Detailed explanation:**

- `deniedHttpAuthorizationPublishesDeniedEvent` tests the **publisher → event listener** pipeline for an HTTP-layer denied decision, not just the HTTP status.
- `denied.count() > before` rather than strictly `before + 1` is used because the number of authorization checks can vary with error dispatch, method security, or additional configuration. Never bake "one request always equals one event" into assumptions.
- `missingWriteAuthority...` sends `.with(csrf())` to pass the CSRF layer, ensuring the denial reflects **missing REPORT_WRITE**.
- `missingCsrf...` intentionally does **not** assert the denied event count: 403 may occur **before authorization**. This teaches distinguishing CSRF rejections from authorization denials.
- `validWriteAuthority...` verifies path + method + authority and valid CSRF token together.
- If a project uses an async application event multicaster, the counter may increment asynchronously; use Awaitility or an appropriate wait strategy in tests. The example assumes Spring's default synchronous event publishing.
- Tests share the counter bean in the application context. Because each test compares `before` and `after` within itself, they do not rely on starting from 0. For parallel test execution or concurrent traffic, isolate fixtures/counters to avoid interference.

Run:

~~~bash
./mvnw test
~~~

**Do not claim guaranteed execution across every Boot/Security release.** APIs, dependencies, and how Spring Security integrates the publisher must be verified against your actual project version. With multiple filter chains or custom `AuthorizationManager`s, add tests targeting **the exact decision point** of interest.

### Denial Outcomes in Application Events Differ from HTTP 403 Logs

Reader's `GET /admin` test produces:

~~~text
Authentication: reader, authorities=[ROLE_USER, REPORT_READ]
Authorization rule: hasRole("ADMIN")
Authorization result: DENIED
AuthorizationDeniedEvent: published
HTTP response: 403
~~~

Yet the same 403 status from a POST missing CSRF follows a different path:

~~~text
Authentication: may not even be evaluated at that filter stage
CsrfFilter: missing/invalid token
AuthorizationFilter: not necessarily reached
AuthorizationDeniedEvent: cannot be inferred from status 403
HTTP response: 403
~~~

**Never lump both paths into one metric labeled "user lacked role"**. That generates false alerts and misleads operators.

## 8. Auditing: What Is "Enough Information Without Leaking Data"?

A useful audit record describes **what was denied**, **in what context**, **how it was handled**, and remains traceable without leaking secrets. Suggested fields:

| Field | Example | Safety rule |
| --- | --- | --- |
| `event_type` | `authorization.denied` | Stable event name. |
| `timestamp` | ISO 8601 UTC | Use synchronized clocks; do not assume clocks across nodes are identical. |
| `service` / `environment` | `orders-api / prod` | Low-cardinality labels. |
| `rule_id` | `admin.read` | Server-defined identifier, not raw expressions with inputs. |
| `action` | `read_admin_dashboard` | Stable business-aligned semantic name. |
| `route_template` | `/admin` or `/orders/{id}` | Do **not** log raw path IDs/tokens unnecessarily. |
| `http_method` | `GET` | Normalized verb. |
| `principal_ref` | Internal pseudonymous ID | Only when required for audit, with access/retention controls; never as a metric label. |
| `tenant_ref` | Pseudonymous tenant ID | Only when needed and sourced from trusted server state. |
| `correlation_id` | Gateway/server-issued random ID | Never blindly trust arbitrary client inputs; restrict format/length. |
| `decision` | `denied` | Record the source/mechanism of the decision. |
| `response_status` | `403` | **Optional field from the HTTP response layer**; never infer from the event alone. |
| `policy_version` | `acp-v3` | Helpful when rules evolve across releases. |

A method-security denial event may have no HTTP route; do not invent a fake path. When you need to trace "who, which operation, which object", audit at **the meaningful business boundary** after resolving resource/tenant, and emit redacted records. A URL list cannot replace that context.

### Data That Must NOT Enter Audits or Metrics

- Raw `Authorization` headers, Basic credentials, Bearer JWTs, refresh tokens, API keys.
- `JSESSIONID`, CSRF tokens, remember-me cookies, or full `Cookie` headers.
- Passwords/passcodes, login form inputs.
- Full request bodies, customer profile JSONs, uploaded files, query strings with sensitive values.
- Uncontrolled `Authentication.toString()` or `event.toString()`.
- Full IP + user-agent + account ID in metric labels (causes massive cardinality and privacy risks).

For security audits that require actor attribution, protect `principal_ref` with access controls, encryption in transit/at rest, retention limits, and compliance policies; minimization does not mean "delete every trace of identity". Balance investigative value with data minimization and organizational rules.

## 9. Metrics, Alerting, and Tracing: Counting the Right Quantity

A pipeline can be structured like this:

~~~text
AuthorizationDeniedEvent
   |
   v
Lightweight event listener, redaction and safe context enrichment
   |
   +--> Micrometer counter / OTel metric
   |      security_authorization_denied_total
   |      tags: service, policy_category, http_method, outcome
   |
   +--> Audit queue / append-only storage
   |      with retention, access control, and retry mechanism
   |
   +--> Trace/span event
          linked via safe correlation ID
          (when a request trace is active)
   |
   v
Alert engine:
   - Denial rate spikes by endpoint category
   - Unusual denial volume after a deployment
   - Critical policy denying in bulk
~~~

Notes:

- Decision **counters** do not equal unique HTTP requests. If a dashboard wants the 403 request rate, track an HTTP server/response-layer metric or aggregate by correlation ID.
- Use **low-cardinality tags**: service name, policy category, method, outcome. Never put user ID, raw URL, order ID, token, or error message into tags.
- Set thresholds on denial **rates** relative to valid traffic, by endpoint category and baseline; an admin-only endpoint naturally has a different denial rate than a public one.
- Distinguish spikes from **privilege probing attacks** vs. **bad policy deployments** using release timestamps, specific routes, anonymized user/scope groups, and system regions.
- Audit logs may require retaining all critical events; metrics and traces are typically observational with separate retention/sampling.
- When using a queue, define unavailable-queue behavior: authorization policies **must never fail open** just because auditing failed. Fail-closed options for *special compliance-gated actions* must be designed intentionally rather than breaking every request on telemetry lag.

### Optional Micrometer Integration Example

If the project configures Micrometer `MeterRegistry` via Spring Boot Actuator, you can use a simple listener instead of an in-memory counter:

~~~java
package com.example.authzaudit;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;

public final class DeniedMetricsListener {

    private final MeterRegistry registry;

    public DeniedMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> ignored) {
        registry.counter("security.authorization.denied",
                "decision", "denied")
                .increment();
    }
}
~~~

This is an **optional class** and is not managed by Spring unless registered as a bean (e.g., via `@Bean` in `@Configuration`); it is not needed to run the Section 6 demo. The project must have the appropriate Micrometer dependency, such as `spring-boot-starter-actuator` and a registry exporter. Never add labels containing accounts or raw paths. Metric publishers and HTTP server metrics are separate channels; do not assume the metric name in this snippet is mandatory across all backends.

## 10. When You Need Structured 403 Responses: AccessDeniedHandler

Frontend APIs often expect JSON instead of HTML error pages. `AccessDeniedHandler` can convert access denials into `application/problem+json` or a standard JSON envelope. **However, AccessDeniedHandler is not an event publisher**: it shapes the HTTP response when an exception reaches it, and does not guarantee every 403 came from an `AuthorizationDeniedEvent`.

Example configuration snippet to return status 403 **without** writing sensitive details into the body:

~~~java
import jakarta.servlet.http.HttpServletResponse;

// Inside HttpSecurity configuration:
http.exceptionHandling(ex -> ex
    .accessDeniedHandler((request, response, denied) -> {
        response.sendError(HttpServletResponse.SC_FORBIDDEN);
    }));
~~~

This is a **snippet** to place inside a `SecurityFilterChain` in a Boot app. It does not handle errors occurring before the security chain, nor does it replace authorization checks. In real JSON APIs, check `response.isCommitted()` and never echo exception messages, role names, or tenant IDs directly to clients.

When to use what?

- Events for auditing/metrics at **the decision point**.
- `AccessDeniedHandler` for shaping the **HTTP error contract**.
- `AuthenticationEntryPoint` for handling **unauthenticated** callers.
- Service-level auditing for recording controlled business context.

Never emit duplicate audit events from both the publisher and handler and count them twice as separate denials without a deduplication key/semantics.

## 11. Method Security and Authorization Events

Beyond HTTP request matching, Spring Security supports method security, typically via `@EnableMethodSecurity` and annotations like `@PreAuthorize`. An authorization denial at a method interceptor can emit a corresponding event when components are wired with an appropriate publisher.

Logical illustration:

~~~java
@PreAuthorize("hasAuthority('REPORT_EXPORT')")
public byte[] exportReport(String reportId) {
    return reportStore.export(reportId);
}
~~~

This is an **illustrative snippet**; it does not compile standalone because `reportStore` and surrounding beans are omitted. Real applications need method-security beans, service/transaction layers, and resource-level authorization. Key points:

- HTTP-level `GET /reports/export/{id}` might satisfy `REPORT_READ` while the method requires `REPORT_EXPORT`, so denial occurs at the method layer.
- Conversely, if the HTTP rule blocks the request before reaching the controller, the method is never invoked.
- When both are enabled, authorization decisions and event counts **no longer have a one-to-one relationship** with requests.
- Events tied to `MethodInvocation` do not necessarily carry an `HttpServletRequest`; listeners must check the object type before extracting context.
- Never dump full method arguments into audit logs—they may contain PII, raw payloads, or secrets.

**You do not need method security enabled just to count HTTP-rule denials** in the Section 6 demo; `authorizeHttpRequests` suffices. When adding method security in production, distinguish `source=web` and `source=method` reliably rather than guessing from class names.

## 12. Distinguishing Failure Types to Avoid False Alarms

| Scenario | Primary component | Typical HTTP status | Can you infer AuthorizationDeniedEvent? |
| --- | --- | --- | --- |
| Logged-in user lacks authority for GET `/admin` | `AuthorizationFilter` / `AuthorizationManager` | 403 | **Yes**, when the event publisher is wired properly. |
| Anonymous calls protected URL | Authorization + entry point | 401 or 302 redirect | Do not count unauthenticated attempts as authorization-denied events. |
| Wrong username/password | Authentication provider/filter | 401 or login failure redirect | **No**. Use authentication failure events. |
| POST missing CSRF | `CsrfFilter` | 403 | **No**, not from status 403 alone. |
| Controller returns `ResponseEntity.status(403)` directly | Controller | 403 | **No**, unless backed by an authorization manager decision. |
| `@PreAuthorize` lacks privilege | Method security interceptor | Usually 403 over HTTP | Depends on method authorization event publisher setup. |
| Route does not exist | MVC/router | 404, sometimes denied by policy first | Do not infer from status alone. |
| External proxy/gateway rejects before Spring | Gateway/firewall/WAF | 403 or other | Do not expect internal Spring application events. |
| Business service denies ownership via custom exception | Service | 403 or other | Does not emit events automatically unless integrated with the authorization mechanism. |

Important in multi-tier systems: a request can be **blocked by a gateway before reaching the service**. Measuring only Spring Security events misses those rejections. To investigate 403s end-to-end, correlate gateway access logs, service HTTP metrics, Spring authorization events, and business audits using a proper correlation ID.

### Diagnosing Why GET /admin Returned 403

1. Verify the request reached the intended service, `SecurityFilterChain`, and matcher.
2. Verify authentication succeeded and the actual user/authorities came from a trusted source.
3. Verify `hasRole("ADMIN")` is checking `ROLE_ADMIN` under the default prefix rather than plain `ADMIN`.
4. Verify the `AuthorizationEventPublisher` bean is configured and denied requests actually trigger the listener.
5. If no event fires despite a 403 status, check `CsrfFilter`, custom filters, proxies, and controller/service layers.
6. If multiple events fire for one request, check error/forward dispatches, web+method security, async dispatch, and duplicate listener/decorator registration.
7. Never "fix" missing logs by switching to `permitAll`; that alters security policy instead of instrumentation.

## 13. Relationship to AuthenticationFailure Events

Spring Security also publishes events when authentication fails, such as subclasses of `AbstractAuthenticationFailureEvent` via `AuthenticationEventPublisher` when configured.

Keep the two categories separate:

~~~text
Client sends wrong password:
   -> AuthenticationProvider rejects credentials
   -> authentication failure event (if publisher configured)
   -> typically no authenticated principal is created

Client logs in validly, then accesses /admin:
   -> Authentication succeeds
   -> AuthorizationManager sees missing ROLE_ADMIN
   -> authorization denial event (if publisher configured)
   -> HTTP 403 commonly returned
~~~

Never merge everything into `security_failures_total` without `stage=authentication|authorization|csrf`. Investigating credential stuffing is completely different from investigating privilege probing or a broken role-mapping migration.

**Privacy protection:** login errors should prevent user enumeration; authorization errors should avoid disclosing "you are missing exact `ROLE_ADMIN`". Return minimal messages to clients, while internal audits may record policy codes under strict access control.

## 14. Reliability and Performance of the Event Pipeline

### ApplicationEventPublisher Is Not a Durable Message Queue

An in-process `ApplicationEventPublisher` lets beans receive events, yet does not provide:

- Durable persistence across crashes.
- Exactly-once delivery guarantees.
- Backpressure, retries, or dead-letter queues.
- Cross-pod/cross-instance synchronization.
- Retention rules or tamper-evident log storage.

For mandatory long-term audit evidence, build an audit sink meeting requirements—such as an append-only store, signed events, or a transactional outbox when tied to business state. Also test behavior when the sink fails.

### Listeners Must Not Slow Down Requests

A synchronously invoked listener can increase latency or throw exceptions that disrupt authorization flow. Best practices:

- Keep listeners minimal; never send emails or make synchronous HTTP calls per event.
- Push redacted data onto a bounded internal queue.
- If the queue fills up, enforce an explicit **telemetry** policy: count dropped/lagged events and alert without turning denials into grants.
- Never run slow DB queries just to "look up extra user names" on the authorization path.
- Ensure thread safety; never turn a shared mutable map into a race condition.
- Rate-limit log verbosity during denial-flood attacks so disk/CPU are not exhausted.

### Deduplication and Tracing

When you need a "denied requests" ratio, use request/span IDs from tracing infrastructure and define aggregation rules: a single request may trigger **multiple** deny events, or a method-security denial may pass through an error handler. Never deduplicate by `event.hashCode()` or principal name, as neither guarantees unique request identity.

With async dispatch or async application events, trace context may not propagate automatically; configure proper context propagation. Never pass raw `SecurityContext` or credentials inside queue/audit payloads.

### When Is Sampling Appropriate?

- High-volume metrics or granted events: sampling/bucketing can be reasonable.
- Denial events needed for security investigations: define clear retention and loss budgets.
- Legally/policy-mandated audit events: if full retention is required, **never randomly sample them away**.

A solid pattern is **low-cardinality metrics + redacted audit events + application logs with correlation IDs**, rather than dumping entire request objects.

## 15. Standalone Java 17: Simulating Denial Event Publishing

To grasp "decision" vs. "event" without Spring libraries, create `AuthorizationDecisionDemo.java`. This is a **Java SE model**, not the real `AuthorizationManager` or `SpringAuthorizationEventPublisher` classes.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public final class AuthorizationDecisionDemo {

    record Attempt(
        String method, String route, String requiredAuthority) {}

    private static final List<String> deniedEvents = new ArrayList<>();

    static boolean authorize(Attempt attempt, Set<String> authorities) {
        boolean granted = authorities.contains(
                attempt.requiredAuthority());

        if (!granted) {
            deniedEvents.add(attempt.method() + " " + attempt.route());
        }

        return granted;
    }

    static void check(Attempt attempt, Set<String> authorities) {
        System.out.println(
            attempt.method() + " " + attempt.route()
            + " -> " + (authorize(attempt, authorities)
                        ? "ALLOW" : "DENY"));
    }

    public static void main(String[] args) {
        Set<String> reader = Set.of("ROLE_USER", "REPORT_READ");

        check(new Attempt("GET", "/reports", "REPORT_READ"), reader);
        check(new Attempt("GET", "/admin", "ROLE_ADMIN"), reader);
        check(new Attempt(
            "POST", "/reports/submit", "REPORT_WRITE"), reader);

        System.out.println("denialEvents=" + deniedEvents.size());
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac AuthorizationDecisionDemo.java
java AuthorizationDecisionDemo
~~~

**Exact** stdout:

~~~text
GET /reports -> ALLOW
GET /admin -> DENY
POST /reports/submit -> DENY
denialEvents=2
~~~

Takeaways:

- Each attempt's **decision** depends on actual authorities.
- An **event** is recorded only when the decision is denied.
- An allowed attempt does not increment the denied counter.
- This program does not handle HTTP 401/403, password verification, or CSRF. Seeing `POST` in the output is merely the attempt's label, not proof an HTTP request passed `CsrfFilter`.

To extend it, add an `UNKNOWN` / `ABSTAIN` result to the model and define explicitly when events fire. In real Spring Security, null/abstain decisions and `AuthorizationResult` semantics depend on version/manager; **never assume every null decision means denied** without checking composition rules.

## 16. Common Mistakes

### 16.1. Treating Every 403 as an Authorization-Denied Event

HTTP 403 can come from CSRF, gateways, or controllers. A metric reading `http.server.requests{status=403}` does not equal `AuthorizationDeniedEvent`. Match the data source and scope carefully.

### 16.2. Logging Raw Events or Authentication Objects

~~~java
// ANTI-PATTERN: risks exposing PII/credentials.
logger.warn("Denied: {}", event);
~~~

This snippet illustrates a bug; it requires `logger` and `event` from a real class to compile. Never log `event.getAuthentication()` or raw `HttpServletRequest`; design a safe audit schema instead.

### 16.3. Enabling Granted Events for All Requests and Querying the DB

If a listener runs a DB query on every allowed request, high traffic can bottleneck the system. Prefer low-overhead instrumentation and targeted audits, avoiding heavy I/O on synchronous event paths.

### 16.4. Having a Listener Grant Privileges When a User Lacks a Role

~~~java
// ANTI-PATTERN: never "fix" a denied event by elevating privileges.
// The event reports that authorization was denied, not to grant new rights.
grantRoleToCurrentUser("ADMIN");
~~~

This is pseudocode illustrating a critical mistake. If role mapping is wrong, fix the authority source and test policies—never mutate the security context inside an audit callback.

### 16.5. Failing to Distinguish Web and Method Events

A controller passing URL policy while a service `@PreAuthorize` denies access is a different scenario. If a listener unconditionally casts the event target to `HttpServletRequest`, it can throw an exception on method-security events. Read only fields guaranteed by contract/type.

### 16.6. Putting userId or Raw URLs into Metric Labels

A metric with a distinct label value per account/order/token causes cardinality explosion, increases cost, and leaks information. Tags like `policy_category`, `service`, `method`, and `decision` work much better.

### 16.7. Treating Synchronous Events Like Guaranteed Message Queues

Spring application events do not guarantee replay after a crash. Use a durable audit sink when required for investigations or compliance, with runbooks for queue/DB outages.

### 16.8. Alerting on Every Denial Without Baselines

Internet bots probing `/admin` raise denials; deploying a bad rule also raises denials. Without total traffic, endpoint category, deployment markers, and baselines, alerts become noisy and cause alert fatigue.

### 16.9. Turning Denials into HTTP 200 to Lower Error Rates

Changing status codes does not fix authorization logic and can leak data. Return the proper status, explain non-sensitive error codes to the frontend, and monitor internally.

### 16.10. Testing Only @EventListener Without Running FilterChainProxy

A unit test calling `onDenied` directly only proves the counter increments—**not** that `AuthorizationFilter` has the publisher wired. Write an integration test sending real unauthorized requests through `MockMvc`.

## 17. QA Matrix and Edge-Case Tests

| Case | HTTP / outcome | Event meaning |
| --- | --- | --- |
| Reader GET `/reports` | 200 | Granted decision; default publisher does not need to emit a granted event. |
| Reader GET `/admin` | 403 | HTTP policy denial; with publisher wired, listener receives event. |
| Admin GET `/admin` | 200 | Not a denied decision. |
| Reader POST `/reports/submit` + valid CSRF | 403 | Missing `REPORT_WRITE`; trackable authorization denial. |
| Admin POST `/reports/submit` + valid CSRF | 200 | Holds `REPORT_WRITE`; controller executes. |
| Admin POST `/reports/submit` missing CSRF | 403 | CSRF failure; **do not** infer a denied event. |
| Anonymous GET `/admin` | Usually 401 with HTTP Basic | Entry point; do not count as "logged in but lacked role". |
| Wrong HTTP Basic password | Usually 401 | Authentication failure, distinct from authorization denial. |
| Controller returns `ResponseEntity` 403 directly | 403 | Does not automatically emit an authorization event. |
| Custom `AuthorizationManager` | Depends on policy | Verify the publisher is attached/invoked. |
| Method-level `@PreAuthorize` denial | Usually 403 at HTTP endpoint | Can emit a dedicated event when method interceptor is configured. |
| Gateway WAF blocks before reaching app | Depends on gateway | Spring app never sees the request or emits an event. |
| Multiple chains / forward / error dispatch | Depends on chain/dispatch | May emit extra events; test deduplication rules. |
| Listener exception / queue unavailable | Must never turn denied into grant | Monitor and handle audit failures per designed policy. |

### Pre-Production Checklist

- [ ] Defined that the tracked signal is authorization denials, not every 403 status.
- [ ] Identified all policy enforcement points: HTTP authorization, method security, and business/resource policies.
- [ ] Configured a version-appropriate `AuthorizationEventPublisher` bean and verified wiring to active managers/filters.
- [ ] Added a `MockMvc` test proving an authenticated request lacking authority emits a denied event.
- [ ] Tested CSRF separately; never attribute token-missing 403s to authorization denials.
- [ ] Separated authentication failures (401/302), authorization denials (403), and gateway rejections.
- [ ] Confirmed listeners have no authorization side effects, never elevate privileges, and handle exceptions safely.
- [ ] Ensured zero logging of raw events/authentications/requests or secrets in cookies/headers/queries/bodies.
- [ ] Defined audit schema with action, route template, policy ID, correlation ID, and proper retention.
- [ ] Configured metrics with low-cardinality labels, rates/baselines, and proper grouping.
- [ ] Defined policies for async event processing, event loss, retries, backpressure, and queue outages.
- [ ] Implemented deduplication/trace correlation when a request goes through multiple decisions.
- [ ] Verified publisher behavior and method signatures when upgrading Spring Security 6.x or major versions.
- [ ] If durable auditing is required, avoided treating `ApplicationEventPublisher` as an exactly-once store.
- [ ] Tested across multiple security chains, proxies, sessions/CSRF, and method-level policies if used.

## 18. Self-Check

**Q1. If a request returns 403, is an `AuthorizationDeniedEvent` guaranteed to exist?** No. It could be blocked by CSRF, a gateway, or a controller without passing through the authorization manager/event publisher.

**Q2. Does `AuthorizationDeniedEvent` itself cause the request to be denied?** No. The authorization manager/policy decides; the event is for observability. HTTP handling is performed by filters, exception translation, and handlers.

**Q3. What does configuring a `SpringAuthorizationEventPublisher` bean solve?** It bridges compatible authorization components to Spring's `ApplicationEventPublisher`, allowing listeners to observe denials.

**Q4. Why accept `AuthorizationDeniedEvent<?>` instead of assuming the target is `HttpServletRequest`?** Events can come from HTTP or method security with different object types; the generic source is not guaranteed to be a request.

**Q5. Do you need to track every granted request by default?** No. Denials are usually higher priority for security, while granted events need careful design to avoid load and audit cost.

**Q6. Both a missing-role user and a missing-CSRF POST return 403. How do you test the difference?** Let the POST pass `csrf()` validly and test missing role, vs. intentionally omitting the CSRF token. Do not assert status codes alone.

**Q7. Should the entire `Authentication` object be written to audit logs?** No. Extract permitted fields into a redacted schema; never log raw passwords, tokens, sessions, or cookies.

**Q8. Does one denial event correspond to exactly one HTTP request?** Not guaranteed. Multiple authorization checks, forwarding/error dispatches, or method security can occur.

**Q9. Is `LongAdder` inside a listener sufficient for production auditing?** No. It counts inside a single JVM with no retention, replay, distribution, or investigative context.

**Q10. If the audit queue is temporarily down, may requests that should be denied be allowed?** No. Telemetry must never bypass authorization. Handle reliability according to security policy.

**Q11. Why should metric labels never contain user IDs?** They create extreme cardinality, raise costs, and risk leaking data; use stable low-cardinality tags and keep controlled actor IDs in audit logs when needed.

**Q12. Does a unit test invoking the listener directly prove events are published?** No. Only a real HTTP test through `FilterChainProxy` with the publisher bean verifies end-to-end integration.

**Summary:** **AuthorizationManager decides → AuthorizationEventPublisher records → `AuthorizationDeniedEvent` is handled by a listener → ExceptionTranslationFilter/handler builds the response**. Observing *denied decisions* is not the same as counting *all 403 responses*. Good observability knows the **source of denial**, has **real integration tests**, **leaks no secrets**, **never slows authorization**, and maintains **semantically sound audits, metrics, and alerts**.
