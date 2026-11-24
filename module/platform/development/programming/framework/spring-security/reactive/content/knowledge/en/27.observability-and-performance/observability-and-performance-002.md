# Tracking Authentication Decisions, Authorization Decisions, and Request Correlation IDs in Spring Security WebFlux

This lesson belongs to the **Observability and Performance** group of **Spring Security – reactive**. The goal is to answer three questions when an HTTP request is blocked or accepted: **was there an authentication attempt and what was the outcome**, **which authorization policy was evaluated**, and **which log records belong to the same request**. The focus is on `SecurityWebFilterChain`, `ReactiveAuthenticationManager`, `ReactiveAuthorizationManager`, `ServerWebExchange`, and Reactor `Context`; do not apply Servlet's `SecurityFilterChain`/`OncePerRequestFilter` implementation patterns to WebFlux.

## 1. Distinguishing Three Types of Signals

| Signal | Question to Answer | Appropriate Capture Point |
| --- | --- | --- |
| **Authentication** | Was there an identity verification attempt? Success, failure, or no decision? | `ReactiveAuthenticationManager` or the success/failure handler of the corresponding login mechanism |
| **Authorization** | Which rule was evaluated? `GRANT`, `DENY`, or no decision produced? | `ReactiveAuthorizationManager` attached to `authorizeExchange(...).access(...)`; method security requires separate observation |
| **HTTP Result** | What status code did the client ultimately receive? | `WebFilter` at the request edge, callback when the response is about to commit |
| **Correlation ID** | Which filter, security, and business logs belong to the same processing pass? | An ID generated/normalized at entry; propagated via `ServerWebExchange` and Reactor `Context` |

**Authentication differs from authorization.** An account can authenticate successfully yet be denied access to `/admin` for lacking `ROLE_ADMIN`. A request without an `Authorization` header might not trigger an HTTP Basic authentication **attempt** at all, yet still be rejected by a “must be logged in” policy. Do not log “wrong password” when credentials were simply missing.

**Decision differs from response.** A denial decision usually leads to HTTP 403 when the user is authenticated and HTTP 401 when authentication needs to be initiated (depending on the entry point, security mechanism, and configuration). HTTP 401/403 by itself does not tell you which specific manager made the decision; business errors can also produce 403. You must combine signals under the same `correlation_id`.

In WebFlux, a pipeline can switch execution threads. `ThreadLocal` and thread-bound MDC may be missing or carry data from another request if misused. `ServerWebExchange` holds data for the current HTTP request; Reactor `Context` holds data for the reactive sequence per subscription. `ReactiveSecurityContextHolder` uses Reactor context for Spring Security's SecurityContext, not a Servlet-style request-scoped ThreadLocal.

## 2. Observation Flow Model

```text
HTTP request
  |
  v
Inbound WebFilter: generate correlation_id, put into exchange + Reactor Context
  |
  v
Spring Security WebFilter chain
  |-- AuthenticationWebFilter / HTTP Basic, Bearer, OAuth2 mechanisms...
  |     |-- ReactiveAuthenticationManager -> authn_success / authn_failure (if authentication is attempted)
  |
  |-- AuthorizationWebFilter -> ReactiveAuthorizationManager
  |     |-- GRANT -> continue processing
  |     |-- DENY  -> reject according to policy
  |     '-- no decision / error -> handle per manager contract, do not mislabel as GRANT
  |
  v
Controller / service / method protected by @PreAuthorize (if any)
  |
  v
HTTP response -> log status with the same correlation_id
```

Rules in `authorizeExchange` are evaluated in declaration order; the first matching matcher selects the corresponding policy. Thus an observation wrapper around `/admin` only sees requests that actually pass through that rule. A request failing authentication early may have **no** authorization record; a request hitting a `permitAll()` path also bypasses a custom observation manager written for the remaining paths. “No event seen” must not be inferred as “allowed”.

## 3. Event Conventions and Data to Log

Log structured events with consistent fields for searching and aggregation:

- `timestamp` (UTC/ISO-8601 from the logging system), `service`, `environment`; add `instance` if there are multiple instances.
- `correlation_id` for a request; `trace_id`/`span_id` from distributed tracing if integrated. These are **different** identifiers; do not treat `X-Correlation-ID` as W3C `traceparent`.
- `event` = `authn_success`, `authn_failure`, `authz_decision`, or `http_response`; `mechanism` = `http_basic`/`bearer`/...; `policy` is the stable name of the rule.
- `outcome` = `GRANT`, `DENY`, `ABSTAIN` (when the manager emits no decision); `status` is the final HTTP status.
- `principal` only when necessary and permitted: prefer reduced-sensitivity/pseudonymized internal identifiers; `reason` uses fixed error category codes, not full exception messages.

**Do not log** passwords, Basic Authorization headers, access/refresh tokens, session cookies, full JWTs/sensitive claims, request body contents, queries containing personal data, or stack traces for every invalid credential attempt. Do not put usernames, request IDs, tokens, or URLs with dynamic IDs into **metric labels** as this causes high cardinality and data leaks.

An illustrative log record (random ID just to show relationships, not fixed output):

```text
event=authn_success correlation_id=8fe2... mechanism=http_basic principal=reader
event=authz_decision correlation_id=8fe2... policy=admin_only outcome=DENY
event=http_response correlation_id=8fe2... status=403
```

## 4. Runnable Example: HTTP Basic and Role-Based Authorization

The example uses **Java 17+**, Spring Boot **3.3.13** / Spring Security 6.3.x, Spring WebFlux, and HTTP Basic to make the flow easy to verify. The user data and passwords below are **for learning environments only**. In real systems, use the application's actual identities and policies; do not create sample accounts like this.

Create a Maven project with `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>security-trace</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

Create `src/main/java/com/example/securitytrace/SecurityTraceApplication.java`:

```java
package com.example.securitytrace;

import java.util.Objects;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatusCode;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authorization.AuthenticatedReactiveAuthorizationManager;
import org.springframework.security.authorization.AuthorityReactiveAuthorizationManager;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class SecurityTraceApplication {

    private static final Logger log =
            LoggerFactory.getLogger(SecurityTraceApplication.class);
    private static final String CORRELATION_ID = "correlationId";

    public static void main(String[] args) {
        SpringApplication.run(SecurityTraceApplication.class, args);
    }

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter correlationFilter() {
        return (exchange, chain) -> {
            // Server generates the ID; do not directly trust arbitrary headers sent by the client.
            String id = UUID.randomUUID().toString();
            exchange.getAttributes().put(CORRELATION_ID, id);
            exchange.getResponse().getHeaders().set("X-Correlation-ID", id);

            // Record status when the response is about to commit, even if security blocks it.
            exchange.getResponse().beforeCommit(() -> {
                HttpStatusCode code = exchange.getResponse().getStatusCode();
                log.info("event=http_response correlation_id={} status={}",
                        id, code == null ? 200 : code.value());
                return Mono.empty();
            });

            // contextWrite provides the ID to inner publishers in the filter chain.
            return chain.filter(exchange)
                    .contextWrite(ctx -> ctx.put(CORRELATION_ID, id));
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
                User.withUsername("reader")
                        .password(encoder.encode("reader123"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin123"))
                        .roles("ADMIN")
                        .build()
        );
    }

    @Bean
    ReactiveAuthenticationManager observedAuthenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var delegate = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        delegate.setPasswordEncoder(encoder);

        return submitted -> Mono.deferContextual(context -> {
            String id = context.getOrDefault(CORRELATION_ID, "missing");
            return delegate.authenticate(submitted)
                    .doOnNext(auth -> log.info(
                            "event=authn_success correlation_id={} mechanism=http_basic principal={}",
                            id, auth.getName()))
                    .doOnError(AuthenticationException.class, ex -> log.warn(
                            "event=authn_failure correlation_id={} mechanism=http_basic reason={}",
                            id, ex.getClass().getSimpleName()));
        });
    }

    private static ReactiveAuthorizationManager<AuthorizationContext> observedPolicy(
            String policy,
            ReactiveAuthorizationManager<AuthorizationContext> delegate) {

        return (authentication, context) ->
                delegate.check(authentication, context)
                        .doOnSuccess(decision -> {
                            ServerWebExchange exchange = context.getExchange();
                            String id = Objects.toString(
                                    exchange.getAttribute(CORRELATION_ID), "missing");
                            String outcome = decision == null ? "ABSTAIN"
                                    : decision.isGranted() ? "GRANT" : "DENY";
                            log.info(
                                    "event=authz_decision correlation_id={} policy={} outcome={}",
                                    id, policy, outcome);
                        });
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager observedAuthenticationManager) {

        return http
                // Demo only reads via GET; do not use disable CSRF as a production default.
                .csrf(csrf -> csrf.disable())
                .formLogin(form -> form.disable())
                .httpBasic(basic ->
                        basic.authenticationManager(observedAuthenticationManager))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").access(observedPolicy(
                                "admin_only",
                                AuthorityReactiveAuthorizationManager.hasRole("ADMIN")))
                        .anyExchange().access(observedPolicy(
                                "login_required",
                                AuthenticatedReactiveAuthorizationManager.authenticated())))
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/admin")
    Mono<String> adminEndpoint() {
        return Mono.just("admin");
    }

    @GetMapping("/profile")
    Mono<String> profileEndpoint() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }
}
```

**Why does the code preserve security decisions?**

1. `observedAuthenticationManager` calls `delegate.authenticate(...)` and attaches `doOnNext`/`doOnError` observation operators; it does not return a fake `Authentication` object, swallow `AuthenticationException`, or turn failure into success. A `Mono.empty()` (if the delegate cannot handle the credential type) does not equate to a successful login.
2. `observedPolicy` delegates the exact result from `delegate.check(...)`. `doOnSuccess` receives `null` when the `Mono` completes empty, so the example logs `ABSTAIN` instead of assuming `GRANT`. It does not use `onErrorResume` to convert an exception into an allowed decision.
3. `@Order(Ordered.HIGHEST_PRECEDENCE)` places the correlation ID filter ahead of most other filters, including the security chain; `contextWrite` makes the ID available during asynchronous password verification. `ServerWebExchange` lets the authorization manager retrieve the request's ID. The filter only observes the response and does not alter the status itself.
4. `.pathMatchers("/public").permitAll()` genuinely allows public access; because it does not pass through `observedPolicy`, it only gets the final HTTP log unless the user explicitly sends Basic credentials triggering an authentication attempt. `/admin` requires `ROLE_ADMIN`, while `/profile` requires an authenticated account. `roles("ADMIN")` creates the `ROLE_ADMIN` authority; `hasRole("ADMIN")` automatically prepends the `ROLE_` prefix.

**Limitations of the pattern:** the authentication observation layer applies only to the manager wired to **HTTP Basic** in the example. If using Bearer JWT, OAuth2 Login, sessions, custom authentication filters, or a gateway, you must attach signals to the **mechanism-specific manager/handler**; do not claim the HTTP Basic sample automatically captures all authentication attempts. `@PreAuthorize`/`@PostAuthorize` is method-level authorization and is not included in `authorizeExchange` logs; it needs separate tracking if reactive method security is enabled. Logging `principal=...` on success in the example is for learning only; production should consider pseudonymizing or omitting this field.

## 5. Running and Testing by Scenario

In the directory containing `pom.xml`, using JDK 17+ and Maven 3.6.3+:

```bash
mvn spring-boot:run
```

Open another terminal and test the requests:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u reader:reader123 http://localhost:8080/profile
curl -i -u reader:wrong http://localhost:8080/profile
curl -i -u reader:reader123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
```

**Expected** HTTP results with the exact configuration above:

| Request | Status | Authentication | Authorization |
| --- | --- | --- | --- |
| `GET /public` without header | 200 | No Basic attempt | `permitAll` rule; bypasses observation wrapper |
| `GET /profile` without header | 401 | No Basic attempt | `login_required` rule denies/challenges for identity |
| `GET /profile` with `reader:reader123` | 200 | `authn_success` | `login_required = GRANT` |
| `GET /profile` with `reader:wrong` | 401 | `authn_failure` | May not reach authorization manager |
| `GET /admin` with `reader:reader123` | 403 | `authn_success` | `admin_only = DENY` |
| `GET /admin` with `admin:admin123` | 200 | `authn_success` | `admin_only = GRANT` |

Every response contains a UUID-formatted `X-Correlation-ID` header. For **each call**, match that header value against `correlation_id` in the authentication log (if attempted), authorization log (if evaluated and logged), and `http_response`. IDs will **differ across calls**; there is no fixed stdout or UUID to copy. You can send multiple concurrent requests to verify logs do not mix request IDs.

Note: `curl -u` sends HTTP Basic, suitable for testing on `localhost`; over real networks, HTTPS is required. Passwords typed on the command line can leak in shell history or process lists. Sample accounts must be removed from real applications. `csrf.disable()` in the example only helps isolate the test flow for read endpoints; in applications with browsers/sessions or state-changing operations, CSRF must be evaluated and configured properly.

## 6. Reactor Context, MDC, and Distributed Tracing

The example demonstrated two ways to access the same identifier:

- Filter: `exchange.getAttributes().put("correlationId", id)`, suitable for components that already have `ServerWebExchange`.
- Reactive chain: `.contextWrite(ctx -> ctx.put("correlationId", id))` at the outer boundary; internally use `Mono.deferContextual(ctx -> ...)`. Context is propagated along the subscription and does not rely on a fixed thread.

Do not assume calling `MDC.put("correlationId", id)` once at the start of a WebFlux request will remain populated in all callbacks after `publishOn`/`subscribeOn`, or always be cleaned up automatically. If your organization uses Logback MDC, you need a context propagation mechanism compatible with your Reactor/Micrometer version and must verify both **propagation** and **cleanup** across thread switches. The example logs `correlation_id` directly in structured logs to avoid depending on MDC.

When calling other services with `WebClient`, correlating cross-service logs requires a strategy to propagate IDs/trace context on outbound requests. Prefer **Micrometer Observation + OpenTelemetry/W3C Trace Context** configured across the entire chain; `trace_id` and `span_id` are managed by the tracing system, while `X-Correlation-ID` is a supplementary field when required by business needs. Do not overwrite `traceparent` manually or unconditionally trust a request ID supplied by external callers. If you must accept an inbound correlation ID, constrain its length/characters, re-decide at trust boundaries, and prevent newline characters from forging logs; the safest pattern is **generating a new UUID** at the application edge.

## 7. Verifying Observability and Performance Quality

You should have an integration test suite with `WebTestClient` covering **200, 401, and 403** statuses and the presence of `X-Correlation-ID`, then inspect captured logs in a test appender to prove all related events share the same ID. Specifically test two concurrent requests to detect context leakage. Test public URLs, wrong Basic credentials, regular users accessing admin, admin users accessing admin, and cases where a manager emits `Mono.empty()` or an error to ensure it is never mislogged as `GRANT`.

You can track aggregate metrics, such as `authn_attempts_total{mechanism,outcome}` and `authz_decisions_total{policy,outcome}`, along with authentication/authorization latency via histograms with bounded labels. These are **custom metric names**, not default names automatically exported by Spring Security across all versions. Do not attach `correlation_id`, `principal`, tokens, detailed IPs, or paths with dynamic IDs as tags. If Spring Boot Actuator/Micrometer is enabled, leverage HTTP server observations and add only necessary instruments; limit success logs or use sampling under high traffic, while retaining failure/suspicious signals per security policy.

For incident triage, inspect in order: **response status + correlation ID → was there an authn attempt → authn mechanism and result → authz policy and outcome → business exception/flow → cross-service trace**. If you only see HTTP 401 without an `authn_failure` event, first check whether the request sent credentials; if you only see 403 without `authz_decision`, check method security, application handlers, and instrumentation placement. Enable DEBUG/TRACE on `org.springframework.security` only in controlled environments for diagnostics, not as a long-term audit source, and review what data may appear in logs.

## 8. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `OncePerRequestFilter` or `HttpSecurity` in WebFlux | Hooks into the wrong Servlet layer, fails to observe the reactive security chain | Use `WebFilter`, `ServerHttpSecurity`, `SecurityWebFilterChain` |
| Concluding “login failed” for every HTTP 401 | Mixes up “no credentials sent” with “wrong credentials” | Log authn attempt, authz decision, and HTTP status separately |
| Treating every 403 as “missing ROLE_ADMIN” | Could be method security, CSRF, or business code | Include `policy` + `outcome` at the exact evaluation point |
| Using only `ThreadLocal` MDC across the reactive chain | Missing/wrong request ID when switching threads | Use Reactor `Context` or configured and tested context propagation |
| Swallowing exceptions with `onErrorResume(e -> Mono.just(GRANT))` | Alters security behavior and introduces vulnerabilities | Observation wrappers must preserve the delegate's result/error |
| Logging raw `Authorization` header or JWT | Credential exposure; increases data risk | Log fixed event/error codes; filter sensitive data |
| Using request ID/user/path as metric tags | Time-series cardinality explosion, high cost | Restrict tags to finite mechanism/policy/outcome values |
| Instrumenting only `authorizeExchange` and claiming `@PreAuthorize` coverage | Misses security decisions at the service/method layer | Observe reactive method authorization additionally per application scope |

## 9. Lab Completion Criteria

- **Semantic accuracy:** distinguish `authn`, `authz`, and `http_response` events; never guess authn failure from status alone.
- **Correlation accuracy:** each request has one ID returned to the client and attached to all related records in the reactive chain; no mixing between concurrent requests.
- **Security correctness:** observers never alter decisions, never leak secrets, and never treat `ABSTAIN`/exceptions as `GRANT`.
- **Scope awareness:** when adding OAuth2/JWT and method security, know exactly which instrumentation points the HTTP Basic example does not cover.
- **Performance soundness:** logs are sampled as needed, metrics have bounded cardinality, and lookup tools work by correlation/trace ID.

### Official References

- Spring Security – Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security 6.3 – `AuthenticatedReactiveAuthorizationManager`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authorization/AuthenticatedReactiveAuthorizationManager.html
- Spring Security 6.3 – `ServerHttpSecurity.HttpBasicSpec`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Reactor – Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor – Context Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html