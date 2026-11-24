# Observing Security with Logs, Metrics, and Traces by Supported Version — Spring Security Servlet

> **Scope:** Operating Spring Security applications running on **Servlet/Spring MVC**, specifically Spring Boot 3.x + Spring Security 6.x + Micrometer/Actuator (Java 17+). This guide explains how to collect and correlate **security logs, metrics, and distributed traces**, how to track authentication/authorization, principles for never leaking credentials or identity data, and requirements for checking **capabilities per exact version**. Complete code examples focus on **stable public APIs**; framework-generated metric/observation names can change between versions and must be verified against a running application.

## 1. Why Is Security Observability Necessary?

An operational security issue can rarely be answered simply by asking "Did HTTP return 401 or 403?". You need to know:

- How many **authentication failures** occurred over a time window? Is there a sudden spike?
- Did failures come from **bad credentials**, expired tokens, invalid JWT keys, CSRF, or **missing authority**?
- A request was authenticated, yet why did it return **403**?
- Did a `SecurityFilterChain` config change suddenly make critical endpoints return **200/302/401/403** differently than before?
- A user sends a request through gateway, backend, and database; which log and trace belong to which request?
- Did authentication filters or IdP/introspection calls gain latency after deploying a new release?
- Are there spikes in header spoofing, repeated login retries, or unauthorized access attempts?
- Is data in logs/metrics/traces accidentally containing passwords, Authorization headers, session cookies, or access tokens?

**Security observability** is the ability to use signals from a running system to understand its security behavior and decisions. It complements testing and auditing; it does **not** by itself replace authentication, authorization, SIEM, WAF, or attack-prevention controls.

The three signal types have different strengths:

| Signal | Questions it answers well | Examples | Limitations |
| --- | --- | --- | --- |
| **Log** | "What event happened?" | `authentication_failed`, `authorization_denied`, timestamp, reason code, request ID | Storage cost, risk of leaking PII/tokens, requires normalized schema |
| **Metric** | "What are the rate, latency, and trend?" | Auth failure count, 401/403 rate, IdP latency and timeouts | Cardinality explosion if user ID/token/dynamic URL becomes a tag |
| **Trace** | "Which components did this request traverse and where was time spent?" | Ingress → filter chain → controller → service → IdP | Sampling may drop traces; traces are not a complete audit log |

**No single system solves everything:** metrics drive alerts, logs drive event investigation, and traces reveal causality and latency. A serious login failure should produce a **structured security event**, a metric counter to detect abnormal spikes, and a correlation ID linking to a trace when present.

## 2. Signal Architecture on Spring Security Servlet

~~~text
[Client / browser]
       |
       v
[Gateway / reverse proxy / IdP integration]
       |
       | verified request ID / trace context
       v
[Servlet container]
       |
       +--> Micrometer HTTP server observation
       |      http.server.requests (depending on config/version)
       |
       v
[FilterChainProxy / SecurityFilterChain]
       |
       +--> Authentication filters / providers
       |      - form login, HTTP Basic, Bearer JWT, OAuth2/OIDC ...
       |      - authentication success/failure events
       |
       +--> AuthorizationFilter / access decisions
       |      - permit / deny, 401 / 403
       |
       +--> CSRF / session / exception handling
       |
       v
[Spring MVC controller]
       |
       v
[Business service / database / outbound HTTP / IdP]
       |
       +--> application observations / network spans
       |
       v
[HTTP response]

LOGS  -> central log pipeline / audit store
METRIC -> MeterRegistry -> Prometheus / monitoring
TRACE  -> ObservationRegistry -> tracer/exporter -> trace backend
~~~

Names like `http.server.requests` are typically **HTTP server instrumentation from Spring Boot/Micrometer**, **not a guarantee that every Spring Security action creates its own metric by default**. Some Spring Security versions integrate Micrometer Observation inside the filter chain; instrumentation depth and names vary across dependencies and releases.

A sound workflow therefore starts with **runtime verification**, not guessing metric names from memory:

1. Identify exact running Spring Boot/Spring Security/Micrometer versions.
2. Confirm Actuator and registry/exporter are installed.
3. Verify whether security instrumentation is supported on that version combination.
4. Send valid and rejected sample requests.
5. Inspect **actual emitted signals** in logs, `/actuator/metrics`, and trace backends.
6. Build dashboards/alerts from **observed, supported metric names and tags**, never hard-coded imagined names.

## 3. By Supported Version: Do Not Mix Three Generations of Tooling

### 3.1. Version Matrix Mindset

| Platform | Integration direction | What to verify before use |
| --- | --- | --- |
| **Spring Boot 2.x / Spring Security 5.x** | Actuator/Micrometer metrics; some systems use Spring Cloud Sleuth for tracing. | Do not copy Boot 3.x Micrometer Tracing or Observation configs verbatim; APIs, dependencies, and observation names differ. |
| **Spring Boot 3.x / Spring Security 6.x** | Micrometer Observation and Micrometer Tracing are the common path; Spring Security offers observability hooks depending on the 6.x release. | Check exact Boot minor version, Spring Security minor, Actuator, registry, tracing bridge, and auto-configuration. |
| **Newer Spring Boot/Security versions or custom stacks** | Rely on release notes, reference documentation, and published features of **the exact deployed combination**. | Never assume every metric/filter observation from an older release keeps the same name/tags/semantics. |

**Do not force an upgrade** merely to get a metric you can gather with application events; equally, do not write dozens of custom filters when you forgot to check built-in framework instrumentation.

In builds managed by the Spring Boot BOM, prefer **Boot-managed Micrometer and Spring Security versions** over pinning arbitrary standalone versions. When overriding versions, test compatibility explicitly.

### 3.2. How to Inspect Actual Versions

For a Maven project, common commands:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

In the output, look for:
- `spring-boot-actuator` and `spring-boot-actuator-autoconfigure`;
- `spring-security-web`, `spring-security-config`, `spring-security-core`;
- `micrometer-core`, `micrometer-observation`;
- exporters such as `micrometer-registry-prometheus`;
- tracing bridges (e.g., `micrometer-tracing-bridge-otel` or Brave bridge);
- corresponding OpenTelemetry/Zipkin/OTLP exporters.

With Gradle you can run `./gradlew dependencies --configuration runtimeClasspath`. Never infer from a dependency "being on the classpath" that every security filter is automatically instrumented; check **beans/auto-configuration**, actual runtime behavior, and emitted signals.

### 3.3. Which Metric/Observation Names Are Stable?

In the Spring Boot Actuator/Micrometer ecosystem, `http.server.requests` is a common HTTP server metric/observation name in Boot 3.x. **Spring Security observation names** may appear prefixed with `spring.security.*`, such as components related to filter chains and authorization, though **identical names and tags are not guaranteed across every 6.x minor release**.

Do not build production alerts assuming "`spring.security.http.requests` definitely exists in every release" without runtime observation. Instead:
- read the **exact-version** Spring Security documentation under *Observability*;
- verify a Micrometer `ObservationRegistry` is auto-wired into security infrastructure;
- inspect names in `/actuator/metrics` or your monitoring backend;
- write a post-upgrade smoke test to catch disappeared metrics/observations;
- manage dashboards as code tied to release versions.

If a needed built-in metric is absent, add a **custom low-cardinality counter** driven by authentication or policy events. This uses application-defined names and is much easier to govern.

## 4. Security Logs: Record Useful Events, Never Secrets

### 4.1. Structured Logging Model

An audit event needs searchable context, e.g.:

~~~json
{
  "event_type": "authentication",
  "outcome": "failure",
  "reason": "bad_credentials",
  "service": "checkout-api",
  "environment": "prod",
  "request_id": "req-6f9a",
  "trace_id": "trace-example",
  "timestamp": "2026-11-06T11:25:30Z"
}
~~~

This is an **illustrative schema**, not a log captured from a real system. `request_id` and `trace_id` must only be attached from trusted/validated sources; "blindly accepting raw client headers" enables log injection or forged correlation.

Usually helpful fields:

- `event_type`: fixed categories such as `authentication`, `authorization`, `session`, `logout`, `csrf`, `token_validation`.
- `outcome`: `success`, `failure`, `denied`, `error` per explicit schema.
- `reason`: **stable, normalized** reason codes such as `bad_credentials`, `token_expired`, `missing_authority`, `csrf_invalid`.
- `timestamp`, `service`, `deployment`, `request_id`/`trace_id` when available.
- `route_template`: e.g., `/api/orders/{orderId}` instead of paths containing raw IDs.
- `actor_reference`: only when needed and allowed by privacy/audit policy; can use a protected internal ID, HMAC, or a dedicated audit store.

**Never include in regular logs:** usernames/passwords, full Basic headers, Bearer tokens, refresh tokens, session IDs, raw cookies, secret keys, OTPs, authorization codes, private certificate material, full login request bodies, or sensitive raw JWT claims. When account-level investigation is needed, use an access-controlled lookup mechanism with separate retention.

### 4.2. What Should Be Logged at Each Layer?

| Layer | Valuable events | Avoid |
| --- | --- | --- |
| Gateway | Policy-blocked requests, TLS/mTLS peer accepted/rejected, rate limiting | Tokens/cookies or request bodies with credentials |
| Authentication | Success/failure by normalized reason code, provider, or mechanism | Passwords, bearer tokens, emails, or full principal dumps |
| Authorization | Deny decisions, action/resource type, appropriate internal policy ID | Full objects containing business data |
| CSRF | Missing/mismatched tokens by normalized route/method | Raw CSRF tokens |
| Session/logout | Session creation/closure at event/outcome level; permitted audit links | Raw session identifiers in application logs |
| Business service | Actions denied at tenant/object/policy-rule level | Secret values inside entities or request JSON |
| Infrastructure | Certificate expiry, JWKS/IdP unavailability, exporter backlogs | Private keys, client secrets, raw handshake payloads |

Ensure **no duplicate audits** are recorded simply because an HTTP request undergoes `REQUEST` and `ASYNC` servlet dispatches, or because multiple listeners handle the same event. Counting "authentication attempts" is not the same as "unique users": an HTTP Basic client can authenticate repeatedly across multiple requests.

### 4.3. TRACE/DEBUG Log Level Is Not Long-Term Production Observability

Locally, you can temporarily enable:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

`TRACE` can generate massive filter-chain logs. Never leave it enabled indefinitely in production: it increases cost, hurts performance, and risks logging sensitive data depending on requests/components/configs. When debugging a production incident, scope packages narrowly, set a time limit, apply sampling and strict log access controls, then turn it off and confirm no sensitive data remains.

Distinguish:
- **Framework debug logs** help understand filter chain execution;
- **Security audit events** need stable formats/schemas and strict retention policies;
- **Application access logs** record HTTP requests/responses at the web server/gateway layer;
- **Metrics/traces** are not automatic copies of every audit event.

## 5. Metrics: Measuring Rates and Latency Without Cardinality Explosion

### 5.1. Metrics Worth Tracking

| Group | Sample metric | Why it matters |
| --- | --- | --- |
| HTTP | Total requests by `uri template`, `method`, `status`, `outcome` | Reveals shifts in 401/403/5xx |
| Authentication | `auth_attempts_total{outcome="success|failure"}` (app-defined name) | Detects credential error/rate spikes |
| Authorization | `authorization_denied_total{resource_type="..."}` (if accurately instrumented) | Tracks access denials |
| IdP/JWKS | Outbound call latency, timeouts, error counts | Detects upstream dependency failures |
| Token | Invalid/expired token rate by fixed reason code | Catches config errors/key rotation issues |
| CSRF | CSRF denial rate by route template/method | Spots broken client integrations or attacks |
| Filter chain | Latency/calls of version-supported observations | Finds hot spots in the security filter pipeline |
| Infrastructure | Exporter failures, dropped spans/logs, registry cardinality | Confirms the observability pipeline is healthy |

**Pick a low-cardinality label set:** `method`, `status`, `outcome`, `provider` from a normalized enum, `route` from templates. Never add `username`, `email`, `session_id`, `token`, `ip`, `trace_id`, or paths containing UUIDs as metric tags.

For example, a single metric with 5 tags having 4 × 8 × 20 × 2 × 3 values creates up to **3,840 time series** even before per-instance/region dimensions. Adding a user ID with millions of values explodes cardinality. Identifying fields belong in **access-controlled logs/traces**, never metric labels.

### 5.2. "Rising 401s" Does Not Automatically Mean an Attack

HTTP 401 can stem from expired tokens, missing tokens, misconfigured API clients, or brute force; 403 can stem from authorization denials, CSRF, or cross-tenant policies. Combine:

- baseline and rate over time;
- route template, mechanism, reason code;
- release/deployment changes;
- aggregated event logs;
- IdP and dependency latency;
- sampled traces to inspect execution paths when needed.

Never page directly on **one** isolated 401. Alerts should evaluate anomalies relative to traffic, rates/ratios, and blast radius.

### 5.3. Metrics Are Not a Complete Audit Trail

Metrics hold totals, histograms, and percentiles—not every individual event. A spike in `authentication_failure_total` triggers alerts, yet does not tell you who, when, and which policy denied access. Security audits may require dedicated retention, integrity, and retrieval workflows compliant with personal-data policies.

## 6. Tracing: Knowing Which Hop Slowed Down a Request

Tracing fits requests traversing multiple hops:

~~~text
ingress/gateway (server or proxy span)
    |
    +--> inventory-api HTTP server span
         |
         +--> Spring Security filter/observation (if supported by version)
         +--> controller / service observation (when instrumented)
         +--> remote IdP introspection HTTP client span
         +--> database query span (if instrumented)
         |
         +--> HTTP 200 / 401 / 403
~~~

A **trace** contains multiple **spans**, each with trace ID/span ID, start/end timestamps, operation name, and attributes/tags. A trace reveals whether a request spent 800 ms at the introspection endpoint or 5 ms in the authorization decision.

### 6.1. Log Correlation and Trace Context

When Spring Boot 3.x is configured with Micrometer Tracing and a matching bridge/exporter, trace/span IDs can be populated into logging MDC per observability configuration. Accepting trace context from HTTP headers across proxies must follow a **trusted proxy policy**; never blindly accept client-sent trace headers to spoof linkage with sensitive requests.

Without a tracer installed, the application can still export HTTP metrics; **do not assume** trace IDs appear in logs just because Actuator is present.

### 6.2. Sampling and Audit Completeness

10% sampling means most HTTP traces are not captured; that works well for performance analysis but **cannot prove every authentication failure was recorded**. Mandatory audit events require a dedicated log/event channel with appropriate durability and retention.

If raising trace sampling during an incident, balance cost, sensitive data exposure, and exporter limits. Never put an `authorization` attribute containing tokens/PII on spans.

### 6.3. Async/Thread Context

In Servlet + Spring MVC `Callable`, Micrometer observation/tracing and `SecurityContext` may use **different context propagation mechanisms**. With `@Async`, `CompletableFuture`, or custom executors, verify whether propagators/`TaskDecorator`/`ContextSnapshot` are configured.

Never assume `MDC.get("traceId")` on thread A automatically appears on thread B. Never treat `InheritableThreadLocal` as a universal fix for thread pools. A **broken trace** does not mean authentication failed; inspect instrumentation and context propagation separately.

## 7. Complete Java 17+ Example: Logging Events and Authentication Metrics

The following code is a **Spring Boot 3.3.5 reference project** for learning. It represents a specific Boot 3.x release, **not claimed to be the latest**. The example uses HTTP Basic on a GET endpoint, one demo user, Actuator, and the Prometheus registry. It demonstrates:
- Spring Security **genuinely authenticating** passwords;
- the framework emitting authentication events via `AuthenticationEventPublisher`;
- a listener recording **low-cardinality metrics** and logging events without credentials;
- HTTP metrics viewable in Actuator, depending on config/version;
- tests observing counters increment after Basic success/failure.

**Important limitations:** There is no full JWT/OIDC code in this project. Spring Security 6.x **automatic** filter metrics/traces apply only if supported and configured in the running version. Do not treat this example as a complete production audit architecture.

### 7.1. Project Structure

~~~text
security-observability-demo/
  pom.xml
  src/
    main/
      java/com/example/securityobs/
        SecurityObsApplication.java
        SecurityConfig.java
        SecurityEventMetrics.java
        DemoController.java
      resources/
        application.yml
    test/
      java/com/example/securityobs/
        SecurityEventMetricsTest.java
~~~

### 7.2. Maven Dependencies

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>security-observability-demo</artifactId>
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
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-registry-prometheus</artifactId>
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
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-maven-plugin</artifactId>
    </plugins>
  </build>
</project>
~~~

**Syntax check:** `<build>` appears only once in `pom.xml`; `<plugins>` closes with lowercase `</plugins>`. Maven XML is case-sensitive. Always run `mvn validate` before running tests or deploying.

### 7.3. Main Application

**`src/main/java/com/example/securityobs/SecurityObsApplication.java`:**

~~~java
package com.example.securityobs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityObsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityObsApplication.class, args);
    }
}
~~~

### 7.4. Security Configuration

**`src/main/java/com/example/securityobs/SecurityConfig.java`:**

~~~java
package com.example.securityobs;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        // Publish success/failure events from AuthenticationManager.
        return new DefaultAuthenticationEventPublisher(publisher);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/ping").permitAll()
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Do not disable CSRF in an app that only has GET endpoints.
            .build();
    }
}
~~~

**Explanation:**

- `InMemoryUserDetailsManager` is for demo use only. Never use hardcoded accounts in production.
- Spring Security's configured authentication provider invokes `AuthenticationEventPublisher` on matching auth success/failure. Events can be published on every Basic authentication attempt; **not** once per "unique user session".
- When `GET /api/me` receives a wrong Basic header, it typically returns 401. When valid, it returns 200 and emits a success event.
- `SessionCreationPolicy.STATELESS` applies to the Basic demo, avoiding relying on sessions to authenticate subsequent requests. Do not treat stateless as proof no client faces CSRF: browsers may auto-attach Basic credentials. Since the demo only has GETs, keep default CSRF.
- `/actuator/metrics` and `/actuator/prometheus` are protected by Basic in the demo due to `anyRequest().authenticated()`. Production must restrict networks/mTLS/monitoring identities and never expose telemetry endpoints publicly over the Internet.
- `AbstractHttpConfigurer::disable` here **only disables form login** to keep API behavior clear; it **does not** disable CSRF, authentication, or authorization.

### 7.5. Measuring Authentication Events with a Micrometer Counter

**`src/main/java/com/example/securityobs/SecurityEventMetrics.java`:**

~~~java
package com.example.securityobs;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.stereotype.Component;

@Component
public class SecurityEventMetrics {

    private static final Logger log =
        LoggerFactory.getLogger(SecurityEventMetrics.class);

    private final Counter success;
    private final Counter failure;

    public SecurityEventMetrics(MeterRegistry registry) {
        success = Counter.builder("app.security.authentication.attempts")
            .description("Authentication attempts recorded as success")
            .tag("outcome", "success")
            .register(registry);

        failure = Counter.builder("app.security.authentication.attempts")
            .description("Authentication attempts recorded as failure")
            .tag("outcome", "failure")
            .register(registry);
    }

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        success.increment();

        // Do not log username, password, token, or raw Authentication.
        log.info("security_event=authentication outcome=success");
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        failure.increment();

        // Normalize reason by exception type; do not dump message.
        String reason = event.getException()
            .getClass().getSimpleName();

        log.warn(
            "security_event=authentication outcome=failure reason={}",
            reason);
    }
}
~~~

This is an **application-defined metric**:
- named `app.security.authentication.attempts`;
- `outcome` tag with only two values `success`/`failure`;
- no user ID/IP/trace ID to avoid high cardinality;
- minimal event logging containing no credential details.

Micrometer/Prometheus may **reformat metric names** per naming conventions when exporting. Do not rigidly assert "in Prometheus the name definitely has dots identically". Inspect `/actuator/metrics` and `/actuator/prometheus` on the running app.

**Events do not cover all application security.** Authentication events do not automatically report every authorization decision, every 401 from a missing token, every CSRF rejection, or every JWT decoder validation error identically. For those categories, use **matching instrumentation points** (version-supported Spring Security observations, authorization events, exception handlers, gateways, application services). Never add a filter "counting denials" by HTTP status alone and label it authentication failure.

### 7.6. API Controller

**`src/main/java/com/example/securityobs/DemoController.java`:**

~~~java
package com.example.securityobs;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/me")
    public Map<String, String> currentUser(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
~~~

In production, never return extra `Authentication`/`UserDetails` fields or raw principals for "easy debugging"; they can hold password hashes and sensitive attributes.

### 7.7. Actuator and Exporter (Dev Configuration)

**`src/main/resources/application.yml`:**

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 0.1

logging:
  level:
    org.springframework.security: INFO
~~~

This configuration is **only a local example**. In production, Actuator endpoint exposure must pair with authentication, network segmentation, monitoring service identities, TLS, and role-based access. `health` can return varying detail levels; never expose `show-details=always` to the Internet.

`management.tracing.sampling.probability` only takes effect when a matching **tracing implementation/bridge** is installed; by itself, it **does not create a tracer or export spans**. The `pom.xml` in this section only installs Actuator + Prometheus metrics, without a distributed tracing bridge/exporter.

### 7.8. Running and Verifying

From the project directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

Send a public request:

~~~bash
curl -i http://localhost:8080/api/ping
~~~

A typical response body:

~~~json
{"status":"ok"}
~~~

Send valid Basic credentials:

~~~bash
curl -i -u alice:demo-pass http://localhost:8080/api/me
~~~

Expect HTTP 200, JSON user `alice`, an `outcome=success` log event, and an incremented success counter. Send invalid credentials:

~~~bash
curl -i -u alice:wrong-password http://localhost:8080/api/me
~~~

Expect HTTP 401, an authentication failure event per provider exception mapping, and an incremented failure counter. A Basic request sent with no credentials may return 401 yet **not necessarily** emit the same authentication failure event because no username/password attempt occurred—never treat the metric as a count of all 401 statuses.

Inspect protected actuator metrics:

~~~bash
curl -i -u alice:demo-pass \
  http://localhost:8080/actuator/metrics

curl -i -u alice:demo-pass \
  http://localhost:8080/actuator/metrics/app.security.authentication.attempts

curl -i -u alice:demo-pass \
  http://localhost:8080/actuator/prometheus
~~~

Returned output depends on dependencies, registries, security chains, and requests that actually created the meter. If the metric does not exist yet, verify the event listener was invoked and meter naming is right before assuming Micrometer is broken.

HTTP/Basic URLs are only for localhost study; **real credentials must go over HTTPS and never enter shell history or pipeline logs**.

## 8. Testing Event Metrics Without Using Fake Users to Bypass Authentication

**`src/test/java/com/example/securityobs/SecurityEventMetricsTest.java`:**

~~~java
package com.example.securityobs;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityEventMetricsTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MeterRegistry registry;

    @Test
    void successfulBasicIncreasesSuccessCounter() throws Exception {
        double before = count("success");

        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));

        assertTrue(count("success") > before);
    }

    @Test
    void badBasicPasswordIncreasesFailureCounter() throws Exception {
        double before = count("failure");

        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "bad-password")))
            .andExpect(status().isUnauthorized());

        assertTrue(count("failure") > before);
    }

    @Test
    void anonymousPublicRequestIsNotBasicLogin() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    private double count(String outcome) {
        Counter counter = registry
            .find("app.security.authentication.attempts")
            .tag("outcome", outcome)
            .counter();
        return counter == null ? 0.0 : counter.count();
    }
}
~~~

Notable points:

1. `httpBasic("alice","demo-pass")` actually sends an **Authorization header** to the authentication filter; `@WithMockUser` typically **does not** go through the password provider this way.
2. Tests read counts **before and after** the request, avoiding the assumption that the registry starts at 0 (other tests/contexts may have emitted events).
3. With a standard synchronous listener, the metric increments before MockMvc finishes. If a project configures asynchronous event processing, synchronize tests or use bounded eventual-consistency assertions.
4. Do not treat "every request definitely emits exactly 1 event" as an invariant across versions, as caching, filter chains, and provider behavior can differ; the test verifies expected events occurred.
5. Do not assert a specific Prometheus text line when naming conventions/exporter versions are unpinned; assert against the registry first, and test exporter format in a dedicated integration test.

This test lives inside a Spring Boot application, not a standalone `javac` program. Because Maven builds depend on environment and repositories, this guide does not fabricate `mvn test` stdout. Tests are expected to pass when the project is configured properly.

### If Metric Tests Fail

- Check whether the `AuthenticationEventPublisher` bean is used by `ProviderManager`.
- Check that `AuthenticationSuccessEvent`/`AbstractAuthenticationFailureEvent` types match the provider.
- Check that the `@Component` event listener falls within component scanning.
- Check that HTTP Basic requests hit the chain and the user actually authenticated.
- Check that the test context shares the same `MeterRegistry` and application context.
- Check whether the service uses a custom authentication manager/provider bypassing the event publisher.
- Check whether the failure type is mapped to an event in `DefaultAuthenticationEventPublisher` or needs extra mapping.

## 9. Enabling Tracing When Supported by Dependencies and Collector

To export distributed traces in Spring Boot 3.x, you typically add a **Micrometer Tracing bridge** (e.g., OpenTelemetry bridge) and matching exporter/transport. Add the following dependencies to `<dependencies>` in Maven **only when supported by your running version combination**:

~~~xml
<dependency>
  <groupId>io.micrometer</groupId>
  <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
<dependency>
  <groupId>io.opentelemetry</groupId>
  <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

This is an addition snippet, not a standalone `pom.xml`. Exporter/collector properties, OTLP protocol/endpoint, authentication, and TLS must match your **Boot version**. Never claim simply adding two dependencies automatically sends traces to any backend: you need a reachable collector, exporter config, sampling, and smoke tests.

An illustrative Boot 3.x style config you might use:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

The collector address above is a **local-only example**; never send traces carrying business data over plain public HTTP in production. Use a protected transport, auth/TLS, and policy-driven data retention. Verify `management.otlp.tracing.endpoint` and the OTLP HTTP path on your exact Spring Boot release; other versions or exporters may require different properties.

### Tracing Smoke-Test Procedure

1. Verify tracer/bridge beans are created (not just Actuator).
2. Verify the collector is listening on the configured endpoint/protocol.
3. Send a request to `/api/me` with demo credentials.
4. View the trace in the backend; inspect the HTTP server span and trace ID.
5. Check log correlation in application logs if MDC is configured.
6. Send a request with a wrong password and verify the corresponding trace/status, ensuring **no Basic credentials/tokens appear in span attributes**.
7. Send a request through gateway/downstream to verify context propagation; confirm hops share the same trace.
8. Account for sampling: at 10%, one call without an exported trace **is not enough** to conclude the exporter is broken; in an isolated test environment you can temporarily raise sampling.

**Never use tracing as an audit log:** when sampling and exporter queues drop spans, traces can be missing even though authentication ran. Legal/compliance events need a separate audit channel with isolated access controls and retention.

## 10. Observing Authorization Without "Counting 403 = Missing Permission"

A 403 response can come from:
- `AuthorizationFilter` blocking due to missing authority;
- `CsrfFilter` rejecting a POST with a missing/invalid CSRF token;
- a business service denying resource/tenant access;
- a proxy/WAF returning 403 **before** the request reaches Spring Boot;
- a custom filter or API gateway issuing a policy denial.

Metrics by **HTTP status** are therefore an overview signal, not a root cause. To capture authorization security events, locate the decision point in your exact module and version: Spring Security authorization event publishing, method security events, or application-level audits. **Never assume every authorization denial emits the same default `ApplicationEvent`.**

A concrete policy architecture example:

~~~text
GET /api/orders/{id}
    |
    +--> HTTP authentication
    |
    +--> URL authorization
    |      -> authenticated?
    |
    +--> service-level ownership/tenant check
           -> allowed or denied
           -> application audit event reason=object_permission_denied
    |
    +--> response 200 or 403/404 per API contract
~~~

In the application service, where enough context exists to check ownership, emit a **custom audit event** with normalized action and resource type. Never put raw `orderId`, full objects, bearer tokens, or user IDs in metric tags. If detailed investigation is needed, store audit events in a repository with dedicated ACLs.

### Version-Dependent Authorization Metrics

If your Spring Security version provides Micrometer observations for the authorization manager, use the documented integration and inspect the actual tag set. If unsupported, record a custom counter with:
- `decision=allow|deny`;
- `resource_type=order|invoice|...` as a finite enum;
- `policy_id` only if drawn from a finite policy list.

**Never measure full data paths using `request.getRequestURI()`**: e.g., `/api/orders/1234` and `/api/orders/5678` create unbounded per-ID cardinality.

## 11. Sessions, Logout, CSRF, JWT, and Special Events

### 11.1. Session/Logout

In applications with form login/session cookies, observe:
- login success/failure rates;
- session lifecycles, timeouts, and concurrent session limit violations if applicable;
- logout intent and logout completion (if auditing is required);
- session fixation protection operating per policy;
- cookie/configuration errors.

Never log `JSESSIONID` or session identifiers. A logged-out user whose next request authenticates again may be hitting an **SSO session** or a client still sending Basic credentials; inspect the exact authentication mechanism instead of assuming logout failed.

### 11.2. CSRF

A CSRF 403 can stem from a frontend bug sending the wrong token, an expired session, or a cross-site request. HTTP 403 alone does not reveal the cause. Use appropriate logging/events/exception handling to distinguish `MissingCsrfTokenException` and `InvalidCsrfTokenException` where supported; never log raw tokens. Check CSRF policies at both the filter chain and proxy.

### 11.3. JWT Resource Server

Token failures can include:
- invalid signature;
- wrong `issuer`;
- `audience` not matching this backend;
- expired `exp`, not-yet-valid `nbf`;
- JWKS endpoint network errors or out-of-sync key rotation.

Ideal security events use fixed reason codes like `invalid_signature`, `wrong_issuer`, `expired`, `wrong_audience`, `jwks_unavailable`. However, the framework sometimes groups failures under `InvalidBearerTokenException` or other exceptions; **availability of every individual reason code cannot be guaranteed** from the same filter across all versions. Prove instrumentation behavior via tests while keeping sensitive tokens/claims out of events.

### 11.4. Authentication Federation/OIDC

If an external proxy/IdP performs login, the backend may only see tokens/headers/claims forwarded by the proxy. An "auth success" log at the backend may simply mean "assertion accepted", **not that the user just completed MFA**. Distinguish:
- login at the IdP;
- session validation at the proxy;
- token validation at the resource server;
- application authorization.

When correlating logs across hops, use trusted request/trace IDs and normalized audit fields; never trust raw identity headers self-asserted by clients.

## 12. Securing the Observability Pipeline Itself

A security observability system can become a major data leak source if:
- full HTTP headers/cookies are logged;
- metrics export user IDs/IPs/tokens in tags;
- traces carry raw JWTs, passwords, or PII;
- exporter endpoints use unprotected HTTP;
- Prometheus/Actuator dashboards are open to the Internet;
- too many engineers have unneeded read access to sensitive audit records;
- retention is unbounded or backups lack deletion policies;
- logging drops data while alerts quietly report "zero incidents".

### 12.1. Data Checklist

| Item | Metric labels? | Logs/traces? | Guidance |
| --- | --- | --- | --- |
| `outcome`, `method`, `status` | Yes | Yes | Small, stable set |
| Route template `/api/orders/{id}` | Yes, when template is normalized | Yes | Never use raw URIs containing IDs |
| Username/email | No | Only in protected audit store when justified | Needs privacy/retention |
| Client IP | No, or bucketed if truly required | Restricted, policy-compliant | Avoid high cardinality and personal data |
| Trace ID | No | Can log as correlation ID | Not secret by default, but prevent spoofing |
| Session ID/cookie | No | No | Never log verbatim |
| Bearer/refresh token | No | No | Tokens are credentials |
| JWT claims | No | Only allowed fields under control | Never dump full tokens |
| Exception class/reason code | Finite categories only | Yes | Never log raw messages containing credentials |
| Tenant ID | Usually no | Can store in protected audit store | Avoid per-tenant metrics if tenant count is large |

### 12.2. Retention and Access

- Separate **application operational logs** from **security audit stores** by sensitivity/retention.
- Define who may view, search, and export data; log audit-access actions themselves.
- Configure redaction across multiple layers: application, collector, pipeline, storage.
- Periodically test "no Authorization/Cookie/secret leaked" using safe test data.
- Alert on full exporter queues, ingestion errors, and dropped data; **losing telemetry** is itself an operational incident.
- Prevent log injection from client headers: sanitize newlines, lengths, and formats of correlation fields.

### 12.3. Cost and Durability

Metric counters are generally cheap if series counts stay bounded. Traces depend on sampling/exporters; audit logs must verify ingestion and persistence. Never place synchronous network calls to a log server **inside an authentication filter** if it can slow down or block logins. For mandatory audit events, design queues/outboxes/transactions and fail-safe semantics per compliance requirements.

## 13. Dashboards, SLIs, and Alerts

A useful dashboard does not try to show as many charts as possible. It should quickly answer:

1. **Authentication health:** attempts, success/failure ratio, aggregated by mechanism/service/route.
2. **Authorization health:** total denials and 403 rates (separating CSRF vs. permissions via logs/events).
3. **Latency:** p50/p95/p99 of HTTP server requests by route template, IdP/JWKS dependency latency.
4. **Telemetry quality:** exporter errors, dropped spans/logs, scrape failures, sampling config.
5. **Deployments:** annotate releases/versions, filter chain config changes, and key rotation events.

Illustrative PromQL query example (verify Prometheus-normalized metric names at runtime):

~~~promql
sum(rate(app_security_authentication_attempts_total{outcome="failure"}[5m]))
/
clamp_min(
  sum(rate(app_security_authentication_attempts_total[5m])),
  1
)
~~~

**Unit note:** `rate()` measures attempts/second; this computes failure / total ratio. `clamp_min(...,1)` in the example can distort the ratio when total traffic is below 1 attempt/second. Production dashboards should use denominator guards suited to units and thresholds; do not treat this illustrative formula as a production-ready alert.

An easier-to-read option for rolling-window ratios uses `increase(…[10m])` in both numerator and denominator, then handles zero-traffic windows. Check your exporter's meter naming implementation. **Never alert when denominator=0** and conclude an attack happened.

### 13.1. Alerts Need Context

- **Auth failures up:** compare against traffic baseline; inspect types and releases instead of labeling every 401 spike "brute force".
- **403s up after deploy:** check routes/endpoints with changed policies, CSRF, and gateways.
- **JWKS/IdP latency up:** compare dependency health and invalid token rates.
- **Unusual 200 rate on sensitive endpoints:** may signal an authorization regression; verify with synthetic tests/audits.
- **Missing logs/metrics/traces:** likely a broken telemetry pipeline; never interpret silence as "no incidents".

When defining SLIs/SLOs, clearly specify the **denominator**, user journeys, expected 401/403s, synthetic test traffic, and security requirements so valid rejections are not mistaken for service outages.

### 13.2. Dashboards Must Be "Version-Accurate"

When upgrading Spring Security/Micrometer, run a regression checklist:
- do metric names/tags still exist?
- did status/route tag semantics change?
- was default instrumentation enabled or disabled?
- do Actuator endpoints/security policies still hold?
- did trace IDs/log patterns change?
- do demo-user tests still emit events and increment counters?
- are sampling/exporters/collectors still compatible?

An empty dashboard after deploy does not prove traffic dropped to zero; a metric may have been renamed or export broken.

## 14. Runbook for Investigating 401/403 Spikes and Authentication Latency

Suppose 403 rates jump after a deploy:

1. **Pinpoint timing and scope:** deployment version, service, route template, method, and traffic volume.
2. **Identify which layer returned the status:** gateway/WAF, Spring Security filter, controller, or business service.
3. **Check CSRF logic:** a POST missing a token can return 403 before authorization; do not assume every 403 means a missing role.
4. **Check Authentication:** actual principal, token type, issuer/audience/timestamps for JWT, session/Basic for username/password.
5. **Check authorization policy:** URL matchers, method security, tenant/object permissions, and policy version.
6. **Query structured audit logs:** request ID, reason code, timestamp; avoid credential dumps.
7. **Inspect traces if available:** ingress, filters/outbound IdP calls, business spans, and latency; remember sampling.
8. **Diff against previous deploy:** filter chain order, new `SecurityFilterChain`, property mappings, and dependency upgrades.
9. **Check telemetry pipeline:** exporter delays/drops, scrape access, clock skew, and retention.
10. **Recover safely:** roll back or fix policy with tests; never slap `permitAll` on a sensitive endpoint just to make a dashboard green.

If 401s rise without authentication failure events, requests may carry no credentials or be rejected by the entry point **before the provider is called**. That does not prove the listener is broken. Separate the concepts: **HTTP denied outcome** and **authentication attempt failure** are two distinct metrics.

If latency increases in JWT auth:
- check JWKS network/caching/rotation and key ID mismatches;
- check parser/validation overhead and allowed algorithms;
- check thread pools and upstream timeouts;
- check trace sampling/collectors;
- never enable raw JWT logging or drop issuer/audience validation to save latency.

## 15. Observing Without Altering Security Decisions

Instrumentation can cause failures if:
- a listener throws an exception and fails requests;
- a slow synchronous exporter sits on the authentication hot path;
- log formatting serializes full principals and pulls in sensitive data;
- metrics tag by user, steadily leaking memory;
- a custom timing filter forgets `filterChain.doFilter` or writes a response itself;
- trace context propagation mixes identities across thread-pool tasks;
- security endpoint exposure becomes broader than intended.

**Principle:** telemetry must never grant privileges, weaken authentication, or alter security responses. Inside listeners, keep metric/log writes simple and free of slow I/O. For mandatory audits, engineer reliability explicitly rather than "catching exceptions and ignoring" every failure.

If a custom timing filter is truly necessary, it must:
- sit at a proven position on the chain;
- use proper clocks/observations and `finally` to close scopes;
- distinguish `REQUEST`, `ASYNC`, and `ERROR` dispatches to avoid double-counting;
- avoid double registration via both Spring bean filter and `addFilterBefore`;
- never log raw headers/bodies.

**Prefer version-supported built-in instrumentation** over writing manual filters everywhere.

## 16. Compatibility and Telemetry Quality Testing

### 16.1. Unit/Integration Tests

| Test | Purpose | Expected |
| --- | --- | --- |
| Valid Basic | Authentication success event/counter | Success counter increments, 200 with right user |
| Invalid Basic | Authentication failure event/counter | Failure counter increments, 401 |
| Missing credentials | Entry point behavior | 401 per demo, failure event not required |
| Authorization deny | AccessDeniedHandler/policy event | 403 not misclassified as bad password |
| Invalid CSRF (apps with POST) | CSRF classification | CSRF reason, no token dump |
| HTTP server metric | Actuator/registry | Meter created after request per Boot version |
| Trace smoke test | Tracer/collector | Span reaches backend under proper sampling |
| Redaction | Zero leaks | Logs/spans/metrics exclude demo password/token |
| Version upgrade | Metric/tag/trace names | Regression tests against pinned manifest versions |
| Telemetry outage | Preserve auth availability per policy | Exporter failure reported; service handles gracefully |

### 16.2. Testing Against Credential Leaks

Use a **distinctive marker demo credential** in test environments and verify captured logs/trace samples **never contain** that string. Never test with production credentials. If using a Logback `TestAppender` or in-memory logger, reset it between tests. Inspect both formatted messages and structured arguments. Verify Prometheus exposition has no user-specific label values.

### 16.3. Testing Sampling and Propagation

In isolated test environments, temporarily adjust sampling to verify trace chains; standard tests should reflect production sampling policies. For asynchronous code, verify trace continuity and context cleanup between two different user requests to prevent ID/context cross-contamination.

### 16.4. Do Not Confuse Instrumentation Tests with Authentication Tests

A `@WithMockUser` test can traverse a controller and emit HTTP metrics, yet **does not perform a real password authentication attempt**. To test provider-emitted events, send `httpBasic()` or `formLogin()` through `FilterChainProxy`. To test JWT signature/claim validation, use a real Resource Server decoder or matching test configuration—never mock `Jwt` and claim production signature validation works.

## 17. Practice Exercises

**Exercise 1 — Build an authentication dashboard.** Run the demo and send multiple valid and invalid Basic requests. Inspect `/actuator/metrics/app.security.authentication.attempts` for tags/measurements. Explain why auth event counts differ from unique user counts.

**Exercise 2 — Identify a 401 bypassing the provider.** Send a protected GET **without an Authorization header**. Compare status vs. authentication failure counter. Explain why 401 can occur with zero failure events.

**Exercise 3 — Compare 401 and 403.** Add an endpoint requiring `ROLE_ADMIN` while the demo user only has `ROLE_USER`. Send valid Basic credentials. Verify authentication succeeded yet status is 403; never increment "bad password" metrics.

**Exercise 4 — Metric cardinality.** Estimate the series count if you added a `username` tag across one million users. Redesign to keep only `outcome` and route template.

**Exercise 5 — Trace propagation.** With an OTLP collector running, add an instrumented outbound HTTP call. Verify the shared trace ID across gateway/backend/outbound spans when version and propagation are properly configured. Document sampling and header protection.

**Exercise 6 — Redaction.** Use a recognizable demo credential and verify logs, Prometheus metrics, and trace exporters contain no password, Authorization header, or session cookie. Fix redaction at the right layer if anything leaks.

**Exercise 7 — Version upgrade.** Pin Boot/Security versions in the build and record current metric names/tags. Upgrade one minor release following official guides, re-run smoke tests, and check if dashboards need migration.

**Exercise 8 — Denominator-aware alert.** Write a 10-minute failure-rate formula active only above minimum traffic; explain why a 100% failure rate on a single request is not automatically an incident.

**Exercise 9 — Exporter outage.** In an isolated environment, stop the collector/Prometheus scrape. Observe application availability and exporter failure/drop metrics without disabling authentication due to log/trace outages.

**Exercise 10 — Avoiding duplicate async logs.** With a Spring MVC `Callable` endpoint, distinguish request-start events, async dispatch completion, and a business operation. Write a test proving audits do not fire twice solely because of Servlet `ASYNC` dispatch.

## 18. Per-Version Deployment Checklist

- [ ] Document exact Spring Boot, Spring Security, Micrometer, registry, and tracing bridge versions.
- [ ] Use BOM-aligned dependency versions; test after any override or upgrade.
- [ ] Verify Actuator endpoint exposure and authentication/network restrictions.
- [ ] Confirm Spring Security built-in observations **actually exist** at runtime; never guess metric names.
- [ ] Bind HTTP metrics to route templates and finite method/status/outcome tags.
- [ ] Track authentication success/failure event metrics from trusted sources; separate from all-401/all-403 counts.
- [ ] Ensure audit logs hold sufficient investigation data without leaking credentials or policy-restricted PII.
- [ ] Never use usernames, IPs, tokens, session IDs, or trace IDs as high-cardinality metric tags.
- [ ] Configure appropriate trace sampling/exporters; never treat tracing as a complete audit log.
- [ ] Test correlation ID/trace propagation across gateways and async paths where needed.
- [ ] Alert on telemetry pipeline failures and dropped data.
- [ ] Run synthetic tests for auth success/failure, authorization denials, and CSRF.
- [ ] Run dashboard regression tests on minor/major upgrades.
- [ ] Never leave `TRACE` debugging enabled long-term in production.
- [ ] Restrict security monitoring endpoints to authorized identities and networks.
- [ ] Obtain approval for retention, redaction, audit access controls, and incident playbooks.

**Conclusion:** Security observability in Spring Security Servlet works when **logs answer what happened and why**, **metrics answer rates, ratios, and latency**, and **traces answer causality across hops**. Signals lose value if the system leaks tokens/passwords, explodes cardinality, or silently drops telemetry when exporters fail. Because observability integrations vary across **Spring Boot, Spring Security, and Micrometer versions**, start from real dependencies and runtimes, leverage supported built-in instrumentation, add custom low-cardinality security events where needed, and verify with integration tests and dashboards on every upgrade.