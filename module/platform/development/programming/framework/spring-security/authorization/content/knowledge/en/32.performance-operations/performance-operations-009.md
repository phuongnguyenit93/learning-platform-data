# Monitoring Denial Rates and Abnormal Authorization Decision Errors

> Scope: **Spring Security - authorization**, **Performance and Operations** section. This lesson guides monitoring authorization in Spring Boot Servlet/MVC applications: measuring denial rates, distinguishing policy-expected denials from **permission evaluation errors**, configuring alerts, and investigating without weakening access controls. Examples use Java 17, Spring Boot 3.3/3.4, Spring Security 6.x, Micrometer, Prometheus, and JUnit 5.

## 1. Do Not Equate HTTP 403 with Policy Decision Errors

An HTTP request may pass through authentication, CSRF validation, `AuthorizationFilter` (URL access rules), `@PreAuthorize` on a service, and then reach business logic. Not every failure means "broken policy."

| Signal | Meaning | What Must Be Distinguished |
| --- | --- | --- |
| HTTP 401 | Unauthenticated per the application's contract | Missing/expired token, anonymous HTTP Basic; usually **authentication**, not a policy deny outcome |
| HTTP 403 | Request ultimately forbidden | Could be missing permissions **or** CSRF, custom filter/handler, gateway |
| `allow` | Observed policy evaluated and granted | Request may still receive 4xx/5xx in later layers; does not equal HTTP 200 |
| `deny` | Observed policy returned a denial decision | Anonymous callers may get 401; authenticated callers usually get 403 |
| `abstain` | Policy returned no decision (`null` in some APIs) | Neither allow nor deny yet; handling depends on policy chain/framework |
| `error` | Permission evaluator hit an unexpected exception | E.g. SpEL error, DB/remote PDP timeout, misconfiguration; this is a **technical incident**, never silently convert to allow |
| Denied event | `AuthorizationDeniedEvent` emitted by Spring Security | Requires `AuthorizationEventPublisher`; does not cover every 401/403, and multiple events can fire per request |

In the Servlet stack, `ExceptionTranslationFilter` handles `AccessDeniedException`: anonymous users typically route to `AuthenticationEntryPoint`, while authenticated users typically route to `AccessDeniedHandler`. Exact results depend on HTTP Basic, sessions, bearer tokens, exception handlers, and policies. Therefore **HTTP 403 counts are not a direct numerator/denominator for policy deny rates**.

```text
HTTP request
   |
   +--> authentication / CSRF ----> may return early 401 or 403
   |
   v
AuthorizationFilter ----------------> allow / deny / error (URL decision)
   |
   v
Controller --> Method Security -----> allow / deny / error (method decision)
   |
   v
Service / Repository ----------------> success or business error
   |
   v
Final HTTP status
```

One request can trigger **multiple permission evaluations** (URL + method security, `ERROR`/`FORWARD` dispatches, calls across multiple services). To measure "percentage of denied requests," count at the **request boundary** with deduplication; to measure "percentage of denied decisions," count per decision within a single policy scope.

## 2. Designing Metrics with Clear Denominators

Recommended minimum metric set:

| Name | Type / Source | Low-Cardinality Tags | Usage |
| --- | --- | --- | --- |
| `http.server.requests` | Timer, Spring Boot Actuator | method, status, outcome, URI template when available | Track HTTP 401/403/5xx, volume, and latency |
| `security.authorization.decisions` | Custom Counter | `policy`, `result=allow/deny/abstain/error/auth_error` | Count evaluations across **instrumented** policies |
| `security.authorization.denied.events` | Custom Counter | No user tags | Track Spring authorization deny events |
| `security.authorization.latency` | Optional Timer | policy, bounded result | Policy latency, especially when backed by DB/remote PDP |

**The `policy` tag must be bounded**: e.g. `reports.read`, `invoice.approve`, `documents.archive`. Never use username, arbitrary tenant ID, token, email, request UUID, IP, document ID, raw URL, query string, or exception message as Prometheus labels: those explode time series and risk leaking sensitive data.

If in a 5-minute window `documents.archive` records 970 allow, 30 deny, and 2 error:

```text
deny_ratio  = 30 / (970 + 30) = 3%
error_ratio = 2 / (970 + 30 + 2) ≈ 0.20%
```

Do not call 32/1002 the denial rate. If the same window had 4,000 HTTP requests and 80 HTTP 403s, the HTTP 403 ratio is `80 / 4000 = 2%`. **These three ratios differ** because their units are policy decisions vs. HTTP requests. Compute deny rates per policy; when evaluation volume is low, a high percentage alone is not enough to conclude there is an incident.

## 3. Collecting HTTP Statuses via Micrometer / Actuator

In a Spring Boot 3.x project using Gradle and the Spring Boot BOM, if dependencies are not yet added:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Sample configuration `src/main/resources/application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: never
```

`/actuator/metrics` aids metric inspection and `/actuator/prometheus` exposes scrape output when the Prometheus registry is on the classpath. **Never assume endpoints are protected automatically**: exposure settings only control publication; you must still restrict the management network, require service-account/TLS authentication, and configure the matching `SecurityFilterChain`. If the app uses `.anyRequest().denyAll()`, add explicit management access rules before scrapers can collect metrics.

HTTP metrics normally carry method, status, outcome, and URI template labels when the framework recognizes the route. For requests blocked early by filters, the URI tag may lack a template or show `UNKNOWN`; verify actual exported series before hardcoding dashboards. Never use raw URLs containing IDs just to gain granularity.

## 4. Java 17+ — Wrapping `AuthorizationManager` to Count Allow/Deny/Error

Standalone example with rule: GET `/api/reports` requires authority `report:read`. We **keep Spring Security's exact policy**, add a decorator recording outcomes, and never alter permissions, return values, or exceptions. Measuring at this boundary captures the exact denominator of `reports.read` evaluations.

Complete file `src/main/java/com/example/securitymonitor/AuthorizationMonitoringApp.java`:

```java
package com.example.securitymonitor;

import java.util.function.Supplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@Import({AuthorizationMonitoringApp.SecurityConfig.class,
         AuthorizationMonitoringApp.ReportController.class})
public class AuthorizationMonitoringApp {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizationMonitoringApp.class, args);
    }

    @RestController
    public static class ReportController {
        @GetMapping("/api/reports")
        public String read() {
            return "reports-ok";
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SecurityConfig {
        @Bean
        SecurityFilterChain web(HttpSecurity http, MeterRegistry registry)
                throws Exception {
            AuthorizationManager<RequestAuthorizationContext> policy =
                AuthorityAuthorizationManager.hasAuthority("report:read");

            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/reports")
                    .access(new CountingAuthorizationManager(
                        "reports.read", policy, registry))
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        }

        @Bean
        AuthorizationEventPublisher authorizationEventPublisher(
                ApplicationEventPublisher springEvents) {
            return new SpringAuthorizationEventPublisher(springEvents);
        }

        @Bean
        DeniedEventMeter deniedEventMeter(MeterRegistry registry) {
            return new DeniedEventMeter(registry);
        }
    }

    // Example for Spring Security 6.x. For newer APIs, check
    // migration from check() to authorize() per the active version.
    static final class CountingAuthorizationManager
            implements AuthorizationManager<RequestAuthorizationContext> {

        private final AuthorizationManager<RequestAuthorizationContext> target;
        private final Counter allowed, denied, abstained, error, authError;

        CountingAuthorizationManager(String policy,
                AuthorizationManager<RequestAuthorizationContext> target,
                MeterRegistry registry) {
            this.target = target;
            allowed = counter(registry, policy, "allow");
            denied = counter(registry, policy, "deny");
            abstained = counter(registry, policy, "abstain");
            error = counter(registry, policy, "error");
            authError = counter(registry, policy, "auth_error");
        }

        private static Counter counter(
                MeterRegistry registry, String policy, String result) {
            return Counter.builder("security.authorization.decisions")
                .tag("policy", policy)
                .tag("result", result)
                .register(registry);
        }

        @Override
        public AuthorizationDecision check(
                Supplier<Authentication> authentication,
                RequestAuthorizationContext context) {
            try {
                AuthorizationDecision decision =
                    target.check(authentication, context);
                if (decision == null) {
                    abstained.increment();
                } else if (decision.isGranted()) {
                    allowed.increment();
                } else {
                    denied.increment();
                }
                return decision;
            } catch (AccessDeniedException rejection) {
                denied.increment();
                throw rejection;
            } catch (AuthenticationException failure) {
                authError.increment();
                throw failure;
            } catch (RuntimeException unexpected) {
                error.increment();
                throw unexpected; // Never turn an error into allow.
            }
        }
    }

    static final class DeniedEventMeter {
        private final Counter events;

        DeniedEventMeter(MeterRegistry registry) {
            events = Counter.builder("security.authorization.denied.events")
                .register(registry);
        }

        @EventListener
        public void onDenied(AuthorizationDeniedEvent<?> event) {
            // Do not put object/authentication or raw exception into tags.
            events.increment();
        }
    }
}
```

### How the Example Works

1. Request with authority `report:read` → `CountingAuthorizationManager` calls the underlying policy, sees `isGranted()==true`, increments `result=allow` by 1, and the API returns `reports-ok`.
2. Authenticated request with only `report:list` → increments `result=deny`, and Spring Security rejects access (403 under HTTP Basic in this example).
3. Anonymous request → HTTP Basic normally returns 401. Whether the policy runs and emits a deny event depends on the filter chain and authentication; **never count 401 as 403**.
4. If a DB/SpEL-backed policy throws `IllegalStateException` → increments `result=error` and rethrows. `AccessDeniedException` is intentionally counted as deny; `AuthenticationException` is separated into `auth_error`. Never assume every evaluation error becomes HTTP 500, as application exception mappings may differ.
5. `DeniedEventMeter` receives `AuthorizationDeniedEvent` from Spring's publisher. **Do not add event metrics to decision metrics**: URL guards, method security, and dispatchers can emit differing events within one request.

The decorator above measures only passes through the GET `/api/reports` rule; `.anyRequest().denyAll()` and other method guards do not automatically get `reports.read`. If using `@PreAuthorize`, enable `@EnableMethodSecurity`, observe the exact enforcement boundary separately, and document which metric includes method-level decisions. Avoid wrapping every policy with one shared `policy="all"` if you want to pinpoint which endpoint is misbehaving.

### 4.1. Testing Counters, Statuses, and Exception Propagation

Create `src/test/java/com/example/securitymonitor/AuthorizationMonitoringTest.java`:

```java
package com.example.securitymonitor;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = AuthorizationMonitoringApp.class)
@AutoConfigureMockMvc
class AuthorizationMonitoringTest {

    @Autowired MockMvc mvc;
    @Autowired MeterRegistry registry;

    private double count(String result) {
        return registry.get("security.authorization.decisions")
            .tags("policy", "reports.read", "result", result)
            .counter().count();
    }

    @Test
    void allowedRequestIncreasesAllowOnly() throws Exception {
        double allowed = count("allow");
        double denied = count("deny");

        mvc.perform(get("/api/reports")
                .with(user("alice").authorities("report:read")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports-ok"));

        assertEquals(allowed + 1, count("allow"));
        assertEquals(denied, count("deny"));
    }

    @Test
    void forbiddenRequestIncreasesDenyOnly() throws Exception {
        double allowed = count("allow");
        double denied = count("deny");

        mvc.perform(get("/api/reports")
                .with(user("bob").authorities("report:list")))
            .andExpect(status().isForbidden());

        assertEquals(allowed, count("allow"));
        assertEquals(denied + 1, count("deny"));
    }

    @Test
    void anonymousRequestUsesAuthenticationEntryPoint()
            throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unexpectedPolicyFailureIsErrorNotDeny() {
        try (SimpleMeterRegistry isolated = new SimpleMeterRegistry()) {
            AuthorizationManager<RequestAuthorizationContext> broken =
                (auth, request) -> {
                    throw new IllegalStateException("policy backend down");
                };

            var monitored = new AuthorizationMonitoringApp
                .CountingAuthorizationManager(
                    "reports.read", broken, isolated);

            var context = new RequestAuthorizationContext(
                new MockHttpServletRequest("GET", "/api/reports"));

            assertThrows(IllegalStateException.class,
                () -> monitored.check(
                    () -> new TestingAuthenticationToken(
                        "alice", "unused", "report:read"),
                    context));

            assertEquals(1.0, isolated
                .get("security.authorization.decisions")
                .tags("policy", "reports.read", "result", "error")
                .counter().count());

            assertEquals(0.0, isolated
                .get("security.authorization.decisions")
                .tags("policy", "reports.read", "result", "deny")
                .counter().count());
        }
    }
}
```

Run from project root with Gradle Wrapper:

```bash
./gradlew test --tests "com.example.securitymonitor.AuthorizationMonitoringTest"
```

On Windows:

```powershell
.\gradlew.bat test --tests "com.example.securitymonitor.AuthorizationMonitoringTest"
```

**Expected outcome:** 4 green tests when run in a project with compatible dependencies and Spring Boot 3.3/3.4. This is an expectation from the assertions, **not an executed Gradle output**. The fourth test proves `error` increments, `deny` stays 0, and exceptions are not swallowed. You can add tests for `AccessDeniedException`, `AuthenticationException`, and `null` decisions; if policies change, these classifications must hold.

## 5. Prometheus Queries and Alerting

Micrometer typically converts Counter `security.authorization.decisions` to `security_authorization_decisions_total`; HTTP Timer normally exports counts as `http_server_requests_seconds_count`. **Verify exact names on `/actuator/prometheus`** because naming conventions, versions, and backends can vary.

### 5.1. Policy Deny Ratio Over 5 Minutes

```promql
sum by (policy) (
  rate(security_authorization_decisions_total{result="deny"}[5m])
)
/
clamp_min(
  sum by (policy) (
    rate(security_authorization_decisions_total{result=~"allow|deny"}[5m])
  ),
  1e-9
)
```

Measures only instrumented policies. When there is insufficient denominator data, dashboards should display *no data* rather than claiming 0% denials.

### 5.2. Policy Evaluation Errors

```promql
sum by (policy) (
  increase(security_authorization_decisions_total{result="error"}[5m])
)
```

Permission evaluation errors usually deserve higher priority than valid denials because they can disrupt access, surface as HTTP 5xx, or cause mass fail-closed lockouts.

### 5.3. Application-Wide HTTP 403 Ratio

```promql
sum(rate(http_server_requests_seconds_count{status="403"}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)
```

Separate charts for 401, 403, 5xx, total request volume, P95 latency, and denial ratio by `policy`. If 403 rises while `decision deny` stays flat, check CSRF, request matchers, gateways, or paths blocked before reaching the policy. If 5xx and `error` rise together, inspect dependent backends/policy expressions.

### 5.4. Alerts with Traffic and Duration Thresholds

Example query firing when deny >5% **and** more than 100 allow/deny evaluations occur in 5 minutes:

```promql
(
  sum by(policy) (
    rate(security_authorization_decisions_total{result="deny"}[5m])
  )
  /
  clamp_min(
    sum by(policy) (
      rate(security_authorization_decisions_total{result=~"allow|deny"}[5m])
    ),
    1e-9
  )
) > 0.05
and on(policy)
sum by(policy) (
  increase(security_authorization_decisions_total{result=~"allow|deny"}[5m])
) > 100
```

Add `for: 10m` (sustained duration) in the alert rule. The numbers **5% / 100 / 10 minutes are tunable examples only**, not default SLOs. Base thresholds on each policy's baseline, time of day, releases, traffic mix, and sensitivity. An `/admin` endpoint intentionally blocking most users can have a high deny rate completely normally; privileged data writes may require alerting after only a few errors.

Watch for **sudden drops in decision counts** while HTTP volume stays steady: a route may have shifted to another `SecurityFilterChain`, guards may have been bypassed, instrumentation may have stopped running, or collectors may be dropping data.

## 6. Logs, Tracing, and Data Protection During Investigation

Metrics tell *how many* and *when*; logs and traces clarify *why*. You can emit structured events like this (**illustrative** payload; applications populate fields themselves):

```json
{
  "event": "authorization_decision",
  "timestamp": "2026-11-06T07:00:00Z",
  "service": "report-api",
  "environment": "production",
  "trace_id": "trace-created-by-tracing-system",
  "policy": "reports.read",
  "action": "read",
  "route_template": "/api/reports",
  "result": "deny",
  "reason_code": "INSUFFICIENT_AUTHORITY",
  "policy_version": "v3"
}
```

`reason_code` and `policy_version` are application-managed business fields; Spring Security does not emit this schema automatically. Use reason codes from a bounded vocabulary only. Never log access tokens, Authorization headers, cookies, passwords, document contents, queries containing secrets, or stack traces containing secrets. To investigate specific users/resources, store protected identifiers in an access-controlled log system with bounded retention, never in Prometheus labels.

Cases to watch out for:

- Spring's `AuthorizationDeniedEvent` is helpful for seeing rejections at URL or method boundaries (when the publisher is wired properly). Granted events can be noisy and are typically off by default; **never use denied event counts as the deny-ratio numerator**.
- `@PostFilter` can strip records from results while HTTP remains 200; 401/403 will not capture "count of filtered records." Where business visibility is needed, add metrics at the data/service layer without exposing sensitive IDs.
- If a policy calls a remote PDP/DB, measure latency with a `Timer`/Micrometer Observation around that exact call using low-cardinality keys; never treat HTTP P95 as an accurate proxy for policy P95.
- Event listeners and logging must not perform heavy synchronous I/O on the request thread; use sampling/buffering per observability design, track queue bounds and drop rates, and never let telemetry errors make policies fail-open.

## 7. Runbook for Investigating Denial-Rate Spikes or Evaluation Errors

| Step | Question | Concrete Action |
| --- | --- | --- |
| 1. Verify data | Is the exporter healthy? Are there counter resets or scrape gaps? | Check raw counts, instances, timestamps, request volume |
| 2. Narrow scope | One policy or all policies? Which release? | Group by policy, service, release; compare pre/post deploy |
| 3. Classify | Did 401, 403, deny, or error spike? | Correlate HTTP metrics, policy counters, and security events |
| 4. Check authentication causes | Expired tokens, bad scope/role mapping, CSRF? | Inspect auth provider, gateway, client changes |
| 5. Check authorization causes | Matcher order, new policy, owner/tenant, role hierarchy? | Compare reviewed permission matrix and regression tests |
| 6. Investigate evaluation errors | DB/remote PDP timeout, config/SpEL bug? | Inspect traces, dependency latency, release diff, controlled exceptions |
| 7. Remediate & verify | Fix policy or roll back config? | Never loosen permissions blindly to drop 403s; re-test and re-measure |

**Scenario A:** pre-deploy `reports.read` had 12,000 allows and 120 denies/hour (~0.99%); post-deploy it shows 9,000 allows and 3,000 denies/hour (25%), steady HTTP traffic, error=0. Check matcher rules, authority mappings, and post-deploy policy changes. Do not jump straight to assuming probing attacks.

**Scenario B:** after a front-end release, HTTP 403 jumps sharply on POST while the policy `deny` counter stays flat. POST requests may be blocked by the CSRF filter **before authorization**. Tweaking permissions will not fix CSRF token errors.

**Scenario C:** `error` climbs alongside 5xx and high P95 latency; policy logs show `DEPENDENCY_TIMEOUT`. Inspect DB/remote PDP health, timeouts/circuit breakers, recent releases, and fail-closed behavior. Never turn dependency errors into allow decisions.

## 8. Common Mistakes and Acceptance Checklist

Mistakes to avoid:

1. Counting 403s alone and calling them "authorization denies": lacks the denominator and may include CSRF.
2. Computing `denied_events / http_requests` as "decision deny rate": mismatched units; multiple events can occur per request.
3. Failing to separate `deny` from `error`: technical outages get misread as users lacking permissions.
4. Logging or tagging user IDs, tokens, or raw URLs with IDs: explodes cardinality and leaks data.
5. Alerting on percentages with only 1–2 requests: noisy; require minimum sample counts and sustained duration.
6. Counting at too many layers and summing them together: double-counts URL/method/dispatcher checks.
7. Catching exceptions and returning `true`: fail-open risk. Preserve exception/deny semantics alongside error telemetry.
8. Skipping instrumentation tests: routes keep working while metrics silently vanish after a security config refactor.
9. Exposing Actuator for scraping without proper network restrictions and authentication.

Pre-production checklist: confirm critical policies are instrumented; metrics have bounded `policy`/`result` tags and defined denominators; dashboards separate 401/403/5xx/traffic/deny/error/latency; alerts are tuned against baselines; runbooks have owners; logs/traces protect sensitive data; tests prove allow/deny/error instrumentation never alters authorization decisions; verify scraper access and cardinality costs post-deploy.

## References

- [Spring Security — Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
