# Securing Actuator, Health Endpoints, API Docs, and Diagnostics in Spring Security WebFlux

This topic belongs to the **Secure Deployment** group of **Spring Security – reactive**. Beyond business APIs, a WebFlux service typically exposes operational paths: Spring Boot Actuator, health probes, OpenAPI/Swagger UI, and custom diagnostic endpoints. If misconfigured, they can leak topology, configuration, metrics, logs, heap dumps, or allow mutating runtime state. The goal is to design and verify a concrete access policy that stays safe when adding endpoints or promoting to production.

The examples use **Java 17+, Spring Boot 3.3.13, Spring Security 6.3.x, and Spring WebFlux**. In the reactive stack, use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ServerWebExchangeMatcher`; do not use Servlet's `HttpSecurity`, `SecurityFilterChain`, or `OncePerRequestFilter`.

## 1. Endpoint "Exists", "Exposed", and "Authorized" Are Three Separate Things

For an Actuator endpoint to be reachable over HTTP, all of the following conditions must hold:

1. **Endpoint present** on the classpath with initialization conditions met: for example, `prometheus` needs `micrometer-registry-prometheus`, `httpexchanges` needs `HttpExchangeRepository`.
2. **Enabled**: `management.endpoint.<id>.enabled` allows the endpoint to be created. For example, `shutdown` is disabled by default.
3. **Exposed** over HTTP: `management.endpoints.web.exposure.include` selects endpoints published to the web, with `exclude` taking precedence over `include`. In Spring Boot 3.3, only `health` is exposed over HTTP by default.
4. **Authorized**: the security chain has a matching matcher and appropriate authority. In addition, firewalls, ingress, service mesh, and management networks must permit the connection.

Example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
```

This configuration only exposes `health`, `info`, and `metrics` over HTTP if they are available/enabled; it **does not grant access permission**. Conversely, `hasRole("OPS")` cannot create an unexposed endpoint. Do not use `include: "*"` as a "convenience switch," especially before all permissions are audited.

**Auto-configuration pitfall:** When declaring your own `SecurityWebFilterChain`, the application takes responsibility for access policy, including Actuator. Do not assume Boot continues generating and enforcing all default security rules for management endpoints. When using multiple chains, ensure Actuator and all remaining routes actually match an appropriate chain.

## 2. Grouping Surfaces and Access Permissions

| Group | Common Paths | Protection Approach |
| --- | --- | --- |
| Liveness | `GET /actuator/health/liveness` | Probes may call unauthenticated, **only over a trusted network**, returning minimal payload |
| Readiness | `GET /actuator/health/readiness` | Same as liveness; indicates readiness to receive traffic |
| Aggregate health | `GET /actuator/health` | Operator, or public status-only when explicitly justified |
| Status/operational | `/actuator/info`, `/actuator/metrics`, `/actuator` | Authenticated operator/monitoring |
| Configuration and mappings | `/actuator/env`, `/actuator/configprops`, `/actuator/beans`, `/actuator/mappings` | Do not expose unless needed; when needed, strictly restrict roles/network |
| Sensitive debug | `/actuator/heapdump`, `/actuator/threaddump`, `/actuator/logfile`, `/actuator/loggers`, `/actuator/httpexchanges` | Strictly restrict; may contain secrets or allow changing log levels |
| API documentation | `/v3/api-docs`, `/v3/api-docs.yaml`, `/swagger-ui/**` | Authenticated DOCS group, or disabled in production |
| Custom diagnostics | `/internal/diagnostics/**`, `/debug/**` | Operators only, audit logged; consider excluding from production builds |
| Business APIs | `/api/**` | Dedicated policies per business domain |

The URLs in the table are **default** values or examples. They can change via `management.endpoints.web.base-path`, `management.endpoints.web.path-mapping`, management port, context path, springdoc config, or gateway rewrites.

### Health, Liveness, and Readiness

- **Liveness** answers "does this instance need to be restarted?" Failures of external dependencies (database/queue) should not trigger restarting the entire pod.
- **Readiness** answers "is this instance currently ready to accept requests?" During startup, shutdown, or an unavailable phase, readiness can be DOWN while liveness remains UP.
- **Aggregate health** may include dependency statuses. Never turn it into a public endpoint with full components/details by default.

In Kubernetes, Boot can automatically enable health probe groups. Enable explicitly in demo environments with `management.endpoint.health.probes.enabled=true`. Use `management.endpoint.health.show-details=never` and `management.endpoint.health.show-components=never` to omit dependency details from responses. If operators need details, use `when-authorized` with `management.endpoint.health.roles` and **also** check the Spring Security URL policy: permission to see details and permission to call the endpoint are two separate controls.

## 3. Least-Privilege Policy and Matcher Ordering

Suppose there are three types of authenticated users: `USER` (business API), `DOCS` (documentation), and `OPS` (operations). In the example, operators are granted both `OPS` and `DOCS`. Spring Security `hasRole("OPS")` checks for authority `ROLE_OPS`; if the identity system returns different claims/scopes, map them or use `hasAuthority(...)`.

A clear policy:

```text
GET /actuator/health/liveness  -> permitAll
GET /actuator/health/readiness -> permitAll
Remaining Actuator endpoints   -> ROLE_OPS
/v3/api-docs*, /swagger-ui*    -> ROLE_DOCS
/internal/diagnostics/**       -> ROLE_OPS
GET /api/public/ping           -> permitAll
all remaining requests         -> authenticated
```

To protect Actuator, Spring Boot 3.3 provides `org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest`. `EndpointRequest.toAnyEndpoint()` creates a `ServerWebExchangeMatcher` based on Actuator endpoints, including the `/actuator` links page, instead of relying solely on a literal `/actuator/**`. However, the two probes in the example use literal paths so only the exact desired paths are permitted; when changing the base path, update and re-test them.

**Specific matchers must precede broad matchers**; never place `anyExchange()` ahead of rules that need to be enforced. Do not permit all of `/actuator/**` just because Kubernetes needs health. At the same time, `permitAll()` cannot verify that a request originated from kubelet: restricting callers requires appropriate network policies/firewalls/ingress rules.

## 4. Complete Spring Boot WebFlux Example

The example uses HTTP Basic and in-memory accounts **only under the `demo` profile**. Production requires an identity provider, service accounts, TLS/mTLS, or an approved mechanism. For Spring Boot 3.3.x, use springdoc **2.6.x** per the project's compatibility matrix.

### 4.1. Declaring Dependencies

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactive-endpoint-security</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
            <version>2.6.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

### 4.2. Exposure and Health Response

Create `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      show-components: never
    env:
      show-values: never
    configprops:
      show-values: never

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

Do not expose `env`, `configprops`, `loggers`, `mappings`, `heapdump`, `threaddump`, or `shutdown` in the lab. `show-values: never` is a defense-in-depth layer against leaks if exposure settings change later; it does **not** enable those endpoints. `springdoc.*.enabled` determines whether documentation endpoints exist, not who may call them.

### 4.3. Application and Controller

Create `src/main/java/com/example/endpointsecurity/EndpointSecurityApplication.java`:

```java
package com.example.endpointsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class EndpointSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointSecurityApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/api/public/ping")
    Mono<String> publicPing() {
        return Mono.just("pong");
    }

    @GetMapping("/api/hello")
    Mono<String> hello() {
        return Mono.just("hello");
    }

    // Illustrative diagnostic route only; do not read secrets or sensitive state.
    @GetMapping("/internal/diagnostics/ping")
    Mono<String> diagnosticPing() {
        return Mono.just("diagnostic-ok");
    }
}
```

### 4.4. Spring Security Reactive

Create `src/main/java/com/example/endpointsecurity/EndpointSecurityConfig.java`:

```java
package com.example.endpointsecurity;

import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class EndpointSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        // Open only GET liveness and readiness, not root health.
                        .pathMatchers(HttpMethod.GET,
                                "/actuator/health/liveness",
                                "/actuator/health/readiness").permitAll()

                        // Reactive matcher covering Actuator endpoints and the links page.
                        .matchers(EndpointRequest.toAnyEndpoint())
                                .hasRole("OPS")

                        // Protect OpenAPI schema, Swagger config, and UI assets together.
                        .pathMatchers(
                                "/v3/api-docs",
                                "/v3/api-docs.yaml",
                                "/v3/api-docs/**",
                                "/swagger-ui.html",
                                "/swagger-ui/**",
                                "/webjars/swagger-ui/**")
                                .hasRole("DOCS")

                        .pathMatchers("/internal/diagnostics/**")
                                .hasRole("OPS")

                        .pathMatchers(HttpMethod.GET, "/api/public/ping")
                                .permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // Keep default CSRF; the demo declares only GET endpoints.
                .build();
    }

    @Bean
    @Profile("demo")
    MapReactiveUserDetailsService demoUsers() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer123"))
                .roles("USER")
                .build();
        UserDetails docs = User.withUsername("docs")
                .password(encoder.encode("docs123"))
                .roles("DOCS")
                .build();
        UserDetails ops = User.withUsername("ops")
                .password(encoder.encode("ops123"))
                .roles("OPS", "DOCS")
                .build();
        return new MapReactiveUserDetailsService(viewer, docs, ops);
    }
}
```

**Key points in the code:**

1. `EndpointRequest` is imported from `...security.reactive`; Servlet has a class with the same name but a different matcher type.
2. Both probes are permitted **before** the all-Actuator matcher. Root health, metrics, info, links, and any newly exposed Actuator endpoint require `ROLE_OPS`.
3. JSON at `/v3/api-docs`, YAML, `/v3/api-docs/swagger-config`, HTML, and Swagger UI JS/CSS must all be protected consistently. If changing `springdoc.api-docs.path` or `springdoc.swagger-ui.path`, update matchers and tests to match the actual URLs.
4. `/internal/diagnostics/**` requires the OPS role. If adding a new route outside this pattern, `anyExchange().authenticated()` still requires login, which is **not** enough if the route needs OPS; expand the policy by route name and function.
5. The example does not disable CSRF globally. GET requests do not mutate state; if adding POST/PUT/DELETE diagnostic endpoints, apply appropriate CSRF protection, authorization, auditing, and abuse controls.
6. HTTP Basic and sample passwords are for local demos only; never store sample credentials in production configuration. With JWT/OIDC, verify the IdP's role/authority mapping rather than assuming tokens contain `ROLE_OPS`.

## 5. Test Run and 200/401/403 Decision Matrix

Use JDK 17+ and Maven in the directory containing `pom.xml`:

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=demo
```

In another terminal (use sample passwords on localhost only):

```bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i -u viewer:viewer123 http://localhost:8080/actuator/metrics
curl -i -u ops:ops123 http://localhost:8080/actuator/metrics

curl -i http://localhost:8080/v3/api-docs
curl -i -u viewer:viewer123 http://localhost:8080/v3/api-docs
curl -i -u docs:docs123 http://localhost:8080/v3/api-docs

curl -i http://localhost:8080/internal/diagnostics/ping
curl -i -u viewer:viewer123 http://localhost:8080/internal/diagnostics/ping
curl -i -u ops:ops123 http://localhost:8080/internal/diagnostics/ping

curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/hello
curl -i -u viewer:viewer123 http://localhost:8080/api/hello
```

Table of **expected status codes** when the service is ready and probes are UP:

| Endpoint | Anonymous | USER | DOCS | OPS + DOCS |
| --- | --- | --- | --- | --- |
| `GET /actuator/health/liveness` | 200 | 200 | 200 | 200 |
| `GET /actuator/health/readiness` | 200 | 200 | 200 | 200 |
| `GET /actuator/health` | 401 | 403 | 403 | 200 |
| `GET /actuator/metrics` | 401 | 403 | 403 | 200 |
| `GET /v3/api-docs` | 401 | 403 | 200 | 200 |
| `GET /swagger-ui.html` | 401 | 403 | Allowed, may return 302 redirect | Allowed, may return 302 |
| `GET /internal/diagnostics/ping` | 401 | 403 | 403 | 200 |
| `GET /api/public/ping` | 200 | 200 | 200 | 200 |
| `GET /api/hello` | 401 | 200 | 200 | 200 |

**401** usually indicates missing authentication; **403** usually indicates authenticated but insufficient authority. `404` can occur because an endpoint is unexposed, disabled, on a different base path, missing a dependency, or routed differently; an HTTP 404 does not prove an authorization policy is safe. Health when DOWN can return `503`; this reflects **service health**, not a security error. Swagger UI may redirect from `/swagger-ui.html` to `/swagger-ui/index.html`; checking only the initial response is insufficient—verify schema and assets actually load for DOCS and are blocked for USER.

Never pass production passwords to curl `-u` on the command line: it risks leaking them in shell history/process listings. Call production APIs over HTTPS with managed authentication mechanisms.

## 6. Regression Testing with `WebTestClient`

To catch accidental exposure after adding dependencies or routes, run integration tests. Create `src/test/java/com/example/endpointsecurity/EndpointSecurityIntegrationTest.java`:

```java
package com.example.endpointsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("demo")
class EndpointSecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void probesAreOpenButMetricsAreNot() {
        client.get().uri("/actuator/health/liveness")
                .exchange().expectStatus().isOk();
        client.get().uri("/actuator/metrics")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void regularUserCannotReadAdminEndpointsOrDocs() {
        client.get().uri("/actuator/metrics")
                .headers(h -> h.setBasicAuth("viewer", "viewer123"))
                .exchange().expectStatus().isForbidden();
        client.get().uri("/v3/api-docs")
                .headers(h -> h.setBasicAuth("viewer", "viewer123"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void docsRoleCannotReadDiagnostics() {
        client.get().uri("/v3/api-docs")
                .headers(h -> h.setBasicAuth("docs", "docs123"))
                .exchange().expectStatus().isOk();
        client.get().uri("/internal/diagnostics/ping")
                .headers(h -> h.setBasicAuth("docs", "docs123"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void operatorCanUseProtectedRoutes() {
        client.get().uri("/actuator/metrics")
                .headers(h -> h.setBasicAuth("ops", "ops123"))
                .exchange().expectStatus().isOk();
        client.get().uri("/internal/diagnostics/ping")
                .headers(h -> h.setBasicAuth("ops", "ops123"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("diagnostic-ok");
    }
}
```

Run `mvn test`. These tests verify policy within a WebFlux runtime; they **do not** prove that network policies, ingress, reverse proxies, or an external management port outside the JVM are configured correctly. When deploying, additionally verify `/actuator` links, `/actuator/info`, `/v3/api-docs.yaml`, `/v3/api-docs/swagger-config`, Swagger UI assets, alternate paths, and custom diagnostics.

## 7. Management Port, Base Path, and Network Boundaries

To isolate Actuator onto a dedicated management port, an alternative configuration is:

```yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: "health,info,metrics"
```

This is a **different deployment option**; do not merge it into the demo file and reuse the old curl commands. When applied, Actuator URLs can become `http://localhost:9090/manage/health`; verify the exact port, context, and proxy routes. Moving to a separate port **does not create a firewall by itself**—apply security groups, network policies, private listeners, firewalls, or ingress restrictions. Do not assume the exact same web security chain applies across a separate management context when the management server runs on its own port: test the real network path directly.

`EndpointRequest` matchers recognize Actuator metadata; literal `/actuator/health/liveness`/`readiness` paths in the example **must be updated** when changing the base path. Likewise, if a gateway rewrites URLs at the network edge, testing must start from the real public and internal addresses matching each role rather than testing only localhost URLs.

When Kubernetes calls health on a separate management port, the management server can still respond while the main web server is not accepting traffic. Spring Boot supports:

```properties
management.endpoint.health.probes.add-additional-paths=true
```

This option exposes liveness and readiness on the main application port at `/livez` and `/readyz`. If used, configure **dedicated permissions** for those two paths and restrict caller sources appropriately. Avoid attaching shared database/queue checks to liveness; readiness should reflect actual ability to serve traffic, preventing cascading failures when a shared dependency degrades.

## 8. Protecting OpenAPI and Swagger UI Properly

Springdoc WebFlux serves multiple resources for the same UI:

- `/v3/api-docs`: OpenAPI JSON; `/v3/api-docs.yaml`: YAML.
- `/v3/api-docs/swagger-config`: Swagger UI configuration.
- `/swagger-ui.html`: UI entry path, typically redirects.
- `/swagger-ui/**` and related static resources such as `/webjars/swagger-ui/**`.

Blocking only `/swagger-ui.html` **does not** stop clients from reading OpenAPI JSON/YAML. Blocking the schema while leaving HTML open can break UI loading or leak partial info. With custom springdoc paths/groups, protect every generated URL and verify via browser/network traces or integration tests. If publishing docs publicly, review schemas for internal endpoints, hosts, server URLs, sample credentials, or sensitive descriptions; public/private API groups only help when filtering is configured accurately.

If the production environment does not need runtime documentation published:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

Reviewed static documentation files can be published through a separate pipeline. Never use "hiding Swagger" as a substitute for protecting business APIs: authorization must be enforced on the HTTP API itself, even without any UI.

## 9. Sensitive Diagnostics and Actuator Endpoints

**Principle:** Expose only what operations require, authorize only the exact principals, and restrict network paths and audit logs. Even `ROLE_OPS` does not mean every operator needs access to every kind of sensitive data.

- `env`, `configprops`: Spring Boot sanitizes potentially sensitive values, yet property names and structures can still disclose infrastructure details. Never set `show-values=always` without special controls.
- `heapdump`, `threaddump`, `logfile`, `httpexchanges`: can leak tokens/secrets from memory heaps, logs, headers, or request payloads. Keep them disabled normally, enabling only under time-boxed, audited procedures.
- `loggers` and `shutdown`: can mutate runtime state; `shutdown` is disabled by default. POST/PUT/DELETE endpoints are also subject to CSRF when the app uses sessions/cookies; for non-browser APIs, decide CSRF based on threat modeling rather than disabling it arbitrarily.
- `/internal/diagnostics/**`: custom routes do not belong to `EndpointRequest`. They must have dedicated matchers tested across subpaths, HTTP methods, multiple security chains, and all URL aliases.
- CPU/memory-intensive or blocking-I/O diagnostic endpoints can cause DoS even when called by authorized users. In WebFlux, never execute blocking operations on the event loop; enforce concurrency limits, timeouts, quotas, and appropriate schedulers if blocking APIs are unavoidable.
- Actuator settings under `management.endpoints.web.exposure` govern HTTP only; JMX has separate exposure and network rules and is not automatically protected by WebFlux security rules.

In audit logs, record useful fields such as authenticated principal, operation type, resource, timestamp, decision, and correlation ID; never log Authorization headers, raw JWTs, passwords, heap dumps, or unnecessary personal data. Metrics should use bounded labels such as endpoint class, policy, and status—never attach tokens, request IDs, or dynamic paths that cause high cardinality.

## 10. Common Mistakes and How to Prevent Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Exposing `*` while only protecting `/api/**` | Operational endpoints may be exposed | Exposure allowlist + `EndpointRequest` with OPS role |
| Permitting `/actuator/**` to allow health | Grants access to all other Actuator endpoints | Permit only specific liveness/readiness paths |
| Blocking UI while forgetting `/v3/api-docs` | Schema can still be downloaded unauthorized | Enforce the same policy across schema, UI config, and HTML/JS/CSS |
| Applying Servlet `HttpSecurity`/`SecurityFilterChain` in WebFlux | Wrong-stack security matcher | Use reactive `ServerHttpSecurity`/`SecurityWebFilterChain` |
| Placing `anyExchange()` before privileged routes | Subsequent matchers are never evaluated | Specific first, broad last |
| Treating any 401/403/404 as "protected" | Masks exposure bugs, missing handlers, or matcher errors | Test authorized 200, denied 403, and anonymous 401; verify bodies |
| `show-details=always` on public health | Leaks dependency statuses/details | `never` or `when-authorized` with appropriate roles |
| Changing management port/path while keeping old config | May expose port or break probes | Test real network paths and matchers; restrict ports via ACLs |
| Enabling loggers/heapdump in production and forgetting to turn off | Data disclosure/runtime mutation | Disabled by default; enable only via audited procedure |
| Using demo Basic accounts in production | Static credentials easily leaked | Activate demo profile locally only; replace with IdP/TLS |

## 11. Deployment Verification Checklist

1. **Inventory:** List enabled and HTTP-exposed endpoints for the actual profile/dependencies, not from another environment's config file.
2. **Probes:** Liveness/readiness return minimal payloads, accurate UP/DOWN statuses, and are reachable from the orchestration network; external networks are restricted if unneeded.
3. **Actuator:** Anonymous and USER cannot view metrics/info/links; operators can view only exposed endpoints; heapdump/loggers/env do not appear unintentionally.
4. **Docs:** JSON, YAML, swagger-config, UI, and static assets share the same policy; DOCS role can access everything, USER cannot.
5. **Diagnostics:** Every HTTP method and alias of diagnostic routes requires the proper role; risky endpoints have auditing, rate limits, and timeouts.
6. **Network & regression:** Test with both `WebTestClient` and real ingress/management ports; re-verify when changing base paths, profiles, identity providers, adding Actuator endpoints, or upgrading Spring Boot.

Acceptance criteria are met when defaults do not inadvertently expose new resources, health probes work without leaking unnecessary details, and operational or documentation endpoints are accessible only to the right principals, from the right networks, backed by repeatable tests.

### References

- Spring Boot 3.3 Actuator – Enabling, Exposing, Security, Health Groups, and Kubernetes Probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 reactive `EndpointRequest`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/reactive/EndpointRequest.html
- Spring Security WebFlux configuration and multiple chains: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security reactive HTTP authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Springdoc OpenAPI v2 – Boot compatibility (Boot 3.3.x uses springdoc 2.6.x): https://springdoc.org/v2/faq.html
- Springdoc v2 – WebFlux API/Swagger UI: https://springdoc.org/v2/modules.html