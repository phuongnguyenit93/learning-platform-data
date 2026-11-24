# Recording Security Events and Designing Audit Trails in Spring Security Reactive

## 1. Objectives and Scope

After this lesson, you will be able to distinguish operational logs from an audit trail, identify security events that must be recorded, design structured records, and integrate audit writing into a Reactor pipeline without blocking the event loop. The focus is on Spring Boot WebFlux applications using `SecurityWebFilterChain`, `ReactiveAuthenticationManager`, and `ReactiveSecurityContextHolder`.

**Scenario:** an account tries a wrong password, an authenticated user calls an admin API, or an administrator changes an account's roles. All three require forensic evidence: who performed the action, what operation, when, on which target, the outcome, the reason, and a correlation ID. A single `DEBUG` line containing an HTTP status is usually insufficient to answer these questions.

Auditing does not replace authentication, authorization, alerting, or tracing. It must record the decisions/events that occurred; having a log entry does not mean the system prevented an attack.

## 2. How Do Application Logs, Observability, and Audits Differ?

| Data Type | Purpose | Example | Characteristics |
| --- | --- | --- | --- |
| Application log | Error diagnostics, execution tracing | Timeout when calling a service | Can be sampled; log level can change |
| Metrics / tracing | Measure latency, error rate, trace requests | Count of HTTP 403s, trace ID | Usually aggregated, may use sampling |
| Security event | Detect suspicious activity | Multiple failed logins, denied access | Has explicit event name and outcome |
| Audit trail | Accountability for sensitive operations | Who granted ADMIN role to whom, before/after state | Needs completeness, integrity protection, access controls, and retention lifecycle |

An event can serve both monitoring and auditing, but **do not use random sampling for mandatory audit events**. Do not turn every HTTP 200 into a “login succeeded”: with HTTP Basic, credentials are re-authenticated on many requests; with login sessions, refresh tokens, or OAuth2/OIDC, event boundaries differ.

Minimum classification:

1. **Authentication:** successful/failed authentication attempts; account lock, unlock, disable; logout, session/token revocation where applicable. Distinguish `AUTHENTICATION_FAILED` from “no credentials sent”.
2. **Authorization:** access denied due to missing permissions, wrong tenant scope, or policy; changes to permissions/groups/policies; specify accurately whether it occurred at the **HTTP** or **method security** level.
3. **Security-sensitive business actions:** changing recovery email, enabling/disabling MFA, resetting credentials, changing roles, reading/exporting sensitive data, editing policies. Record at the business layer after the true transaction outcome is known, rather than inferring solely from HTTP status.
4. **Control-plane events:** modifying security configuration, rotating keys/certificates, changing log retention policies, deleting audit data under an authorized procedure.

**HTTP 401 and 403:** typically 401 means authentication is required or invalid; 403 means access denied after authentication. However, you cannot rely solely on status to know the cause: CSRF, resource errors, custom entry points, and other handlers can produce the same status. Record at the exact security hook with a classified reason code.

## 3. Data Contract of an Audit Event

Design a versioned schema with stable fields. Example:

| Field | Meaning |
| --- | --- |
| `eventId`, `schemaVersion` | Unique ID for deduplication / evolvable format |
| `occurredAt`, `recordedAt` | When the event occurred and when the system stored it, in UTC |
| `service`, `environment`, `tenantId` | Origin; tenant if the application is multi-tenant |
| `eventType`, `outcome`, `reasonCode` | Action type; SUCCESS/DENIED/FAILURE; controlled reason code |
| `actorId`, `actorType` | Stable identifier of the user/service, or UNKNOWN if unauthenticated |
| `targetType`, `targetId` | Affected target object, separated from actor |
| `httpMethod`, `routeTemplate` | HTTP method and normalized route, avoiding raw queries/paths with secrets |
| `requestId`, `traceId` | Keys linking to traces and operational logs; not used as user identity |
| `authMethod`, `clientContext` | Authentication mechanism; normalized IP/UA only if truly needed and allowed by privacy policy |
| `changeSummary` | Changed fields, **filtered** old/new role names; do not copy sensitive data |

Illustrative record (hypothetical values, not fixed stdout from the runnable example below):

```json
{
  "eventId": "f58ce0fa-6f81-4e0b-a562-cd296c597632",
  "schemaVersion": 1,
  "occurredAt": "2026-11-07T09:00:00Z",
  "service": "security-reactive-api",
  "eventType": "AUTHORIZATION_DENIED",
  "outcome": "DENIED",
  "reasonCode": "MISSING_REQUIRED_ROLE",
  "actorId": "user-42",
  "targetType": "HTTP_ROUTE",
  "targetId": "GET /admin",
  "requestId": "req-7a1e",
  "traceId": "trace-9c2b"
}
```

**Do not include in audits:** passwords, `Authorization` headers, cookie/session IDs, access/refresh tokens, OTPs, private keys, full request/response bodies, URLs with secret query parameters, or stack traces containing sensitive data. Usernames, emails, and IPs can also be personal data: retain only if necessary and enforce read permissions, retention periods, and masking/pseudonymization. Use error codes like `BAD_CREDENTIALS` instead of logging exception messages that may contain internal details.

## 4. Where to Record in the WebFlux Flow

```text
Client
  -> WebFilter generates requestId/sets Reactor Context
  -> SecurityWebFilterChain
       -> HTTP Basic / form / OAuth2 / resource-server authentication
          -> Authentication succeeds or fails -> audit
       -> Authorization (route/method)
          -> Denied -> ServerAccessDeniedHandler / corresponding hook -> audit
       -> Controller -> Business service
          -> Sensitive change succeeds/fails -> business audit
  -> Structured log / queue / transactional outbox / audit store
  -> SIEM, alerting, and role-restricted lookup
```

Key extension points:

- **`ReactiveAuthenticationManager`:** can be wrapped with `flatMap` and `onErrorResume` to observe decisions of the **active authentication mechanism**. `Mono.empty()` may mean “no decision”, not automatically failure. If multiple providers exist, place the hook at the appropriate authentication layer to avoid duplicate or missed events.
- **`ServerAuthenticationSuccessHandler` / `ServerAuthenticationFailureHandler`:** useful when customizing `AuthenticationWebFilter` or form login. When wrapping a handler, still invoke the original handler to preserve redirects, `SecurityContext` saving, HTTP challenges, and login behavior. Do not mechanically assign an HTTP Basic handler to all OAuth2/JWT flows.
- **`ServerAuthenticationEntryPoint`:** triggers the authentication-required response, usually 401; this **does not automatically mean wrong password**.
- **`ServerAccessDeniedHandler`:** handles missing permissions, usually 403. For CSRF, inspect the `csrf` handler separately; for method security, verify that the exception actually passes through the corresponding HTTP handler layer. Do not guarantee every `AccessDeniedException` reaches a single hook.
- **Business layer:** when granting permissions, revoking tokens, or modifying policies, log the event with the target and real transaction outcome instead of merely attaching a `WebFilter` reading HTTP status.

Spring Security documentation about `AuthenticationSuccessEvent` / `DefaultAuthenticationEventPublisher` in the **Servlet** branch does not mean WebFlux automatically emits all those events. You must verify the actual reactive mechanism/provider and attach the appropriate hooks.

### Reactor Context, Threads, and Backpressure

WebFlux can switch execution across multiple threads. Servlet's `ThreadLocal`-based `SecurityContextHolder` is not the standard way to read identity in Reactor; use `ReactiveSecurityContextHolder.getContext()` or `exchange.getPrincipal()` in the Web layer. Put the request ID into `Reactor Context` with `contextWrite` and retrieve it via `Mono.deferContextual`. Traditional MDC is also ThreadLocal-based, so using it requires a proper context bridge—do not assume MDC automatically follows thread switches.

Audit writers return `Mono<Void>` to **compose** into the pipeline via `then` / `flatMap`. Avoid `block()` on the event loop; avoid fire-and-forget `subscribe()` calls inside handlers as that loses error handling, ordering, and lifecycle control. Synchronous file/DB writes or heavy JSON serialization on the event loop can still cause blocking even if the API returns `Mono`; production needs async appenders/drivers or a controlled outbox/queue.

## 5. Runnable Example: HTTP Basic + Event Auditing and 401/403

This small example uses Java 17, Spring Boot **3.3.13**, WebFlux, and Spring Security 6.3.x with two demo users. The goal is to illustrate hooks, log structure, and Reactor Context; this is not yet an immutable production audit store.

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>reactive-audit-demo</artifactId>
    <version>1.0.0</version>
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

Create `src/main/java/dev/example/audit/AuditDemoApplication.java` (all helper classes reside in the same file and are not declared `public`):

```java
package dev.example.audit;

import java.security.Principal;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class AuditDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuditDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class AuditSecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
                .password(encoder.encode("demo123")).roles("USER").build();
        var root = User.withUsername("root")
                .password(encoder.encode("admin123")).roles("ADMIN").build();
        return new MapReactiveUserDetailsService(alice, root);
    }

    @Bean
    ReactiveAuthenticationManager auditAuthenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder,
            AuditLog audit) {
        var delegate = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        delegate.setPasswordEncoder(encoder);

        return request -> Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(AuditRequestIdFilter.KEY, "unknown");
            return delegate.authenticate(request)
                    .flatMap(authenticated -> audit.write(
                            "AUTHENTICATION", "SUCCESS", authenticated.getName(),
                            "HTTP_BASIC", "CREDENTIALS_ACCEPTED", requestId)
                            .thenReturn(authenticated))
                    .onErrorResume(AuthenticationException.class, failure ->
                            audit.write(
                                    "AUTHENTICATION", "FAILURE", request.getName(),
                                    "HTTP_BASIC", failure.getClass().getSimpleName(), requestId)
                                    .then(Mono.error(failure)));
        });
    }

    @Bean
    SecurityWebFilterChain securityChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager auditAuthenticationManager,
            AuditLog audit) {
        var basicChallenge = new HttpBasicServerAuthenticationEntryPoint();
        var forbidden = new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN);

        return http
                .authorizeExchange(authorize -> authorize
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic.authenticationManager(auditAuthenticationManager))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((exchange, cause) ->
                                audit.write(
                                        "AUTH_REQUIRED", "DENIED", "anonymous",
                                        exchange.getRequest().getPath().value(),
                                        cause.getClass().getSimpleName(),
                                        exchange.getRequest().getId())
                                        .then(basicChallenge.commence(exchange, cause)))
                        .accessDeniedHandler((exchange, cause) ->
                                exchange.getPrincipal()
                                        .map(Principal::getName)
                                        .defaultIfEmpty("anonymous")
                                        .flatMap(actor -> audit.write(
                                                "AUTHORIZATION", "DENIED", actor,
                                                exchange.getRequest().getPath().value(),
                                                cause.getClass().getSimpleName(),
                                                exchange.getRequest().getId()))
                                        .then(forbidden.handle(exchange, cause))))
                .build();
    }
}

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class AuditRequestIdFilter implements WebFilter {
    static final String KEY = "audit.requestId";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String requestId = exchange.getRequest().getId();
        return chain.filter(exchange)
                .contextWrite(context -> context.put(KEY, requestId));
    }
}

@Component
class AuditLog {
    private static final Logger LOG = LoggerFactory.getLogger(AuditLog.class);
    private final ObjectMapper mapper;

    AuditLog(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    Mono<Void> write(String type, String outcome, String actor,
                     String resource, String reason, String requestId) {
        return Mono.fromRunnable(() -> {
            Map<String, String> event = new LinkedHashMap<>();
            event.put("eventId", UUID.randomUUID().toString());
            event.put("occurredAt", Instant.now().toString());
            event.put("type", type);
            event.put("outcome", outcome);
            event.put("actor", actor);
            event.put("resource", resource);
            event.put("reason", reason);
            event.put("requestId", requestId);
            try {
                LOG.info("SECURITY_AUDIT {}", mapper.writeValueAsString(event));
            } catch (JsonProcessingException ex) {
                throw new IllegalStateException("Audit serialization failed", ex);
            }
        }).then();
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
    }

    @GetMapping("/admin")
    Mono<String> admin() {
        return Mono.just("admin ok");
    }
}
```

**Mechanism:** `AuditRequestIdFilter` puts the request's ID into Reactor Context. `auditAuthenticationManager` wraps the actual username/password authentication manager; when `onNext` emits an authenticated `Authentication`, it emits a `SUCCESS` event; when the manager emits `AuthenticationException`, it records `FAILURE` and re-propagates the error. `AUTH_REQUIRED` reflects an authentication challenge when identity is missing; `AUTHORIZATION DENIED` records cases where a principal exists but lacks permissions. Both default response delegates still run to preserve the Basic challenge and HTTP 403.

The example keeps CSRF defaults and only exposes GET endpoints, adding no state-changing endpoints. The two passwords in source code are **for learning only**; real applications use identity stores, secret management, and HTTPS. Because HTTP Basic authenticates per request, the same user may generate multiple `AUTHENTICATION SUCCESS` events—do not interpret every one as a new login session.

### 5.2. Testing the Scenarios

Run in the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

In another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u alice:demo123 http://localhost:8080/me
curl -i -u alice:demo123 http://localhost:8080/admin
curl -i -u root:admin123 http://localhost:8080/admin
```

| Request | Expected HTTP | Expected Audit |
| --- | --- | --- |
| GET `/public`, no credentials | 200, body `public` | No authn/denial event needed |
| GET `/admin`, no credentials | 401, with Basic challenge | `AUTH_REQUIRED / DENIED` |
| GET `/me`, wrong password | 401 | `AUTHENTICATION / FAILURE`; Basic handler may issue challenge without going through `AUTH_REQUIRED` hook |
| GET `/me`, valid alice | 200, body `alice` | `AUTHENTICATION / SUCCESS` |
| GET `/admin`, valid alice | 403 | `AUTHENTICATION / SUCCESS` and `AUTHORIZATION / DENIED` |
| GET `/admin`, valid root | 200, body `admin ok` | `AUTHENTICATION / SUCCESS` |

The console will show lines starting with `SECURITY_AUDIT` and a JSON payload with `eventId`, `occurredAt`, `type`, `outcome`, `actor`, `resource`, `reason`, and `requestId`; timestamps/IDs change on every run so no fake fixed stdout is provided. If using custom clients/headers or multiple security chains, verify the actual filter/handler path with integration tests.

### 5.3. Intentional Limitations of the Demo

- `AuditLog` only writes to a logger: **it does not yet guarantee durable storage, tamper resistance, or zero log loss**; synchronous console appenders can add latency on the event loop. Production uses pipelines with buffering/backpressure, bounded queues, controlled retries, and a proper audit store.
- The handler's `resource` currently uses the raw request path. Production should use a **route template** or strip IDs/secrets from paths, never append query strings, and populate `tenantId` and `actorId` from trusted sources.
- The `ReactiveAuthenticationManager` hook here covers **HTTP Basic** assigned to this manager. Adding form login, OAuth2/OIDC, or JWT requires identifying the corresponding pipeline; having one manager bean does not prove every mechanism is logged.
- The example has no role-change actions; auditing **business state changes** must be added at the corresponding service/transaction. Do not infer from HTTP 200 that a change was committed.
- `getRequest().getId()` is an internal request ID. When OpenTelemetry/Micrometer tracing is present, also link real trace/span IDs; do not blindly trust client-supplied correlation headers.

## 6. From Console Logs to a Trustworthy Audit Trail

### 6.1. Choosing Success Semantics and Preserving Data

**Record at the decision boundary:** authentication accepted, authorization denied, data change committed; avoid recording “SUCCESS” before a transaction succeeds. On rollback, emit a `FAILED`/`ROLLED_BACK` event or use a clear business model.

**Error policy:** for ordinary diagnostic logs, business operations may continue if logging drops; for mandatory auditable actions, organizations may require blocking completion unless audit persistence is guaranteed. Fail-open/fail-closed decisions must be approved based on risk level. The demo chains `Mono` sequentially, so a logging error can fail the flow; however, **there is no atomic transaction guarantee** between business work and a log file.

**Transactional outbox** when business and audit work must share a transaction: within the same business DB transaction, persist both the change and an outbox event; a separate worker pushes via a broker to the audit store, retrying idempotently using `eventId`. In reactive systems, use appropriate reactive DB/transaction APIs and confirm exactly-once policies by design; brokers are typically more practical with at-least-once + deduplication.

### 6.2. Protecting Integrity, Privacy, and Queryability

- **Append-only:** application accounts only have insert permission, never UPDATE/DELETE on audits; separate admin accounts, and enable immutable storage / WORM if required by regulation or risk. Hashes or signatures only help when keys, permissions, and custody chains are also protected; hashing alone does not stop someone with permissions to alter all data.
- **Clocks and identifiers:** normalize UTC timestamps, maintain clock sync, store both event time and ingest time when queued; use unique IDs and `schemaVersion`. Separate actor, target, and tenant so subjects are never confused.
- **Permissions and security:** only authorized teams may view logs; encrypt in transit/at rest, monitor audit store access, restrict exports, mask sensitive data, and prevent log injection via a JSON serializer; never log credentials or raw tokens.
- **Retention and disposal:** set retention per business/legal requirements, with legal hold if applicable; keeping data longer is not automatically better. Delete/anonymize per policy while retaining appropriate evidence of admin operations.
- **Search:** index on `occurredAt`, `eventType`, `actorId`, `targetId`, `tenantId`, and `requestId`; support pagination, mandatory tenant filtering, query limits, and checks against information leakage through query APIs.

### 6.3. Performance, Reliability, and Alerting

Monitor: audit events/sec by type, write latency (p95/p99), queue size, dropped records, serializer/sink errors, retries, event-to-ingest lag, and storage usage. Alert on anomalous failure streaks, spikes in denied access, sensitive privilege grants, and an audit sink stopping ingestion; tune thresholds to avoid false positives.

Mandatory audit events are normally prioritized over debug logs. If applying sampling to regular logs, ensure the audit pipeline is not dropped by sampling or rate limits. Reduce cost with compact schemas, controlled reason codes, time/tenant partitioning, and sensible archiving.

## 7. QA Checklist and Common Mistakes

**Minimum test scenarios:** test 401 on missing credentials; 401 on wrong password; 200 on valid password; 403 on missing role; 200 on valid role; CSRF/method security if enabled; audit for admin operations and rollbacks; behavior when the sink fails; recovery after retry and `eventId` deduplication; test usernames containing newlines/Unicode characters to confirm safe JSON output.

Verify each event is written only once at the **defined boundary**, has a unique `eventId`, UTC timestamp, valid type/outcome/reason, and accurate correlation ID and actor/target. Ensure no passwords, tokens, cookies, or secrets appear in logs, and under-privileged accounts cannot query others' audits.

Common mistakes:

1. Calling `SecurityContextHolder.getContext()` from an arbitrary thread in WebFlux and getting a `null` user; use `ReactiveSecurityContextHolder` or the exchange principal.
2. Calling `block()` / `subscribe()` inside reactive handlers; causes blocking or lost error signals. Compose `Mono` instead.
3. Recording `AUTHENTICATION_SUCCESS` for every 200; HTTP status does not prove a new authentication or committed business operation.
4. Logging only `exception.getMessage()`; can leak data, is hard to query, and varies across versions. Use a controlled `reasonCode`.
5. Configuring only a **Servlet** event publisher and assuming WebFlux is covered; test the exact reactive hooks in use.
6. Writing audits before a transaction commits when business logic rolls back, or firing-and-forgetting so records are lost; use appropriate transactions/outbox.
7. Trusting client-sent `X-Forwarded-For`/`X-Request-Id` without configuring trusted proxies; enables origin spoofing.
8. Equating plain console text logs with an immutable audit store; you need access control, durability, integrity, retention, and completeness monitoring.

## 8. References

- Spring Security — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Enable Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — ServerHttpSecurity API: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — AuthenticationWebFilter API: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
