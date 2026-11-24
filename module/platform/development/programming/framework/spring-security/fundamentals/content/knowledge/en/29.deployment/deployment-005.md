# Securing Actuator, API Documentation, and Diagnostic Endpoints

## 1. Why are operational endpoints also an attack surface?

In a Spring Boot application, business APIs are not the only endpoints needing protection. A service may also expose **Spring Boot Actuator** for monitoring, **OpenAPI/Swagger UI** for inspecting API contracts, and **internal diagnostic** paths to check state, jobs, configuration, or errors. Developers commonly use these routes in test environments, yet during real deployments they can accidentally pass through ingress, reverse proxies, API gateways, or management ports without proper controls.

The risk is not limited to "outsiders learning which endpoints the app has." Certain paths can reveal bean names, configuration, route mappings, loggers, dependencies, health details, stack traces, metrics, HTTP exchanges, or even allow **modifying operational state**. OpenAPI documentation can expose internal paths and parameters even when the docs themselves do not grant permission to call them. Custom diagnostic endpoints can inadvertently expose cache-reset actions, config changes, arbitrary queries, or log retrieval.

The goal of this **Deployment** lesson in *Spring Security - fundamentals* is to build a multi-layered protection strategy for these three surfaces:

1. **Do not enable or expose what you do not need**: reduce the attack surface before writing a single rule.
2. **Configure HTTP security properly**: minimal health for probes, explicit roles/authorities for management, docs, and diagnostics; never assume defaults remain intact once you define a custom `SecurityFilterChain`.
3. **Restrict network access and operational permissions**: management ports, network policies, ingress, TLS, credentials/SSO, auditing, and least privilege.
4. **Never leak sensitive data**: response bodies, health details, env values, log contents, OpenAPI descriptions, and diagnostics.
5. **Test realistically**: anonymous, other roles, authorized roles, unexposed paths, CSRF, port/path changes, ingress, and production configuration.

**Principle:** "Having authentication" is not enough. An obscure yet public API returning secrets or allowing sensitive actions still poses risk; a separate management port reachable from the Internet through ingress or networking is likewise unsafe.

## 2. Classifying resources by sensitivity

| Category | Typical URLs (config-dependent) | Data / capability | Reasonable exposure level |
| --- | --- | --- | --- |
| Liveness/readiness | `/actuator/health/liveness`, `/actuator/health/readiness` | Health signals for orchestrators | Minimal info only; authorized network/probe callers |
| Overall health | `/actuator/health` | UP/DOWN status, potentially component details | Minimal status may be public; **never** public details |
| Info | `/actuator/info` | Build/app info if configured | OPS only or approved non-sensitive info |
| Metrics/Prometheus | `/actuator/metrics`, `/actuator/prometheus` | Runtime stats, resource names, tags | Monitoring identity/network; never broadly public |
| Env/configprops/beans/mappings | `/actuator/env`, `/actuator/configprops`, `/actuator/beans`, `/actuator/mappings` | Config, bean structure, mappings, metadata | Best kept unexposed in normal production |
| Loggers/logfile/threaddump/heapdump | `/actuator/loggers`, `/actuator/logfile`, `/actuator/threaddump`, `/actuator/heapdump` | Logs, stacks, memory—potentially containing PII/secrets | Disabled by default; controlled access only if truly needed |
| Shutdown or mutating actions | `/actuator/shutdown`, POST to loggers or custom endpoints | Mutates application state | Disabled except under special ops workflows; stricter than GET |
| OpenAPI description | `/v3/api-docs`, `/v3/api-docs.yaml`, `/v3/api-docs/{group}` | Path list, schemas, models, descriptions | Docs group/role or disabled in production |
| Swagger UI | `/swagger-ui.html`, `/swagger-ui/**` | UI to browse and invoke APIs | Docs group/role; never accidentally public |
| Custom diagnostics | `/internal/diagnostics/**`, `/debug/**`, `/admin/**` | State, support actions, internal info | OPS + network restrictions; omit from production if unneeded |

**No "diagnostic" label creates a security boundary by itself.** `/internal`, `/admin`, `/debug`, or long hard-to-guess paths remain ordinary HTTP endpoints until filter chains and networks actually restrict access.

**Do not confuse publishing documentation with authorizing APIs.** Swagger UI is only a client/documentation tool; backend endpoints still need independent authentication, authorization, and object-level checks. Hiding a route from OpenAPI does not block calling that route.

## 3. Three gates deciding whether Actuator is reachable

In Spring Boot 3.5, distinguish three separate concepts before securing Actuator:

1. **Endpoint access/availability**: `management.endpoint.<id>.access`, `management.endpoints.access.default`, and `management.endpoints.access.max-permitted` control whether an endpoint or operation is allowed to exist. Values can be `none`, `read-only`, or `unrestricted` depending on endpoint type. When access is `none`, the endpoint is no longer available in the application context.
2. **Exposure**: `management.endpoints.web.exposure.include` and `exclude` decide which available endpoints are exposed over HTTP. JMX has separate exposure. An endpoint not exposed over HTTP cannot be reopened merely by `permitAll()`.
3. **HTTP authorization**: Spring Security `SecurityFilterChain` decides whether an incoming HTTP request needs anonymous access, authentication, or a specific role. Exposure **does not replace** authorization.

```text
Actuator called over HTTP
  |
  +-- Does the endpoint have access != none? -- No --> unavailable
  |
  +-- Is the ID in web.exposure.include
  |   and not in exclude? --------------------- No --> no HTTP handler
  |
  +-- Does the request pass the right SecurityFilterChain?
  |      |
  |      +-- minimal health / probes --> allow valid callers
  |      +-- metrics/info -------------> requires OPS permission
  |      +-- everything else ----------> deny
  |
  +-- Does network / ingress / firewall allow the connection?
         |
         +-- No  --> blocked at the network layer
         +-- Yes --> HTTP security must still check permissions
```

**Important default:** Spring Boot 3.5 exposes only `health` over HTTP/JMX by default; other endpoints do not appear automatically just by adding the starter. When Spring Security is on the classpath **and the app defines no `SecurityFilterChain`**, Boot auto-configures protection for most Actuator endpoints (except health). **Once you define a custom `SecurityFilterChain`, Boot backs off from automatic Actuator security; you must secure those endpoints yourself.** This is a frequent mistake when adding a `permitAll()` rule for a public API and accidentally leaving Actuator unprotected.

**Version warning:** `management.endpoints.access.*` is an API/property available in the Boot 3.5 line. When maintaining older Boot versions or upgrading to Boot 4, check that version's reference documentation; never copy package imports or properties without verifying the version.

## 4. Production deployment pattern: deny expansion by default

A restrictive configuration for production might look like:

```yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,metrics"
  endpoint:
    health:
      access: read-only
      show-details: never
      show-components: never
      probes:
        enabled: true
    info:
      access: read-only
    metrics:
      access: read-only
```

Meaning:

- By default, **unlisted endpoints are disallowed**. Only `health`, `info`, and `metrics` receive `read-only` access, and only those three IDs are exposed over HTTP.
- `max-permitted: read-only` caps access permissions; even if an endpoint is switched to `unrestricted` elsewhere, this cap restricts write operations. Still, do not rely solely on this property to protect production.
- `health.show-details: never` and `show-components: never` hide health indicator details from ordinary callers. Where deeper inspection is needed, use dedicated groups/roles/admin channels and verify actual responses.
- `probes.enabled: true` enables liveness/readiness paths outside Kubernetes auto-detection. On Kubernetes, Spring Boot can enable probes automatically.
- `info` and `metrics` still require authentication/authorization and network restrictions at another layer.

If using YAML `include: "*"`, remember to **quote it** because `*` is special YAML syntax. In production, avoid broad `management.endpoints.web.exposure.include=*` paired with a short `exclude` list, as future endpoints will be exposed by default.

**Environment note:** this illustrative config does not expose `prometheus`. If Prometheus scraping is genuinely needed, add the appropriate registry dependency, add `prometheus` to access and exposure, and protect it with a service account/monitoring network; never assume every pod or Internet client may scrape it.

## 5. Runnable example: Spring Boot 3.5, Actuator, OpenAPI, and diagnostics

The example below uses **Java 17+, Maven, Spring Boot 3.5.16, Spring Security 6.x, Actuator, and springdoc-openapi 2.10.0**. springdoc 2.x fits Boot 3.x; version 2.10.x is compatible with Boot 3.5.x per the project's compatibility matrix. When applying to another system, verify organization-approved versions.

Demo requirements:

- Anonymous users can read `GET /api/public` and `GET /actuator/health` (minimal status only).
- `GET /actuator/metrics` and `/actuator/info` are restricted to `ROLE_OPS`.
- OpenAPI JSON and Swagger UI are restricted to `ROLE_DOCS` or OPS users granted DOCS.
- `GET /internal/diagnostics/ping` is restricted to OPS and returns approved minimal content without reading env/logs/secrets.
- `/actuator/env` and other dangerous endpoints are **not exposed**.
- All remaining routes are denied by default.

Structure:

```text
management-security-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/ManagementSecurityApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/ManagementSecurityTests.java
```

### 5.1. Maven `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>management-security-demo</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>2.10.0</version>
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

This is a standalone Maven project with a **complete `<plugin>...</plugin>` wrapper**. The Actuator starter adds endpoints and HTTP integration; springdoc generates OpenAPI JSON and Swagger UI; Spring Security provides `HttpSecurity`/filter chains; test dependencies provide MockMvc and Spring Security Test.

### 5.2. `src/main/resources/application.yml`

```yaml
server:
  port: 8080

management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,metrics"
      discovery:
        enabled: false
  endpoint:
    health:
      access: read-only
      show-details: never
      show-components: never
      probes:
        enabled: true
    info:
      access: read-only
    metrics:
      access: read-only

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

**Why disable Actuator discovery?** The `/actuator` link discovery endpoint typically lists exposed Actuator endpoints. In this demo, `management.endpoints.web.discovery.enabled=false` reduces the link metadata returned. This **does not** replace security for `/actuator/health`, `/actuator/metrics`, or any other route. Access policy still depends on exposure, access, the filter chain, and networking.

**Why enable Swagger in the demo?** To test role-based documentation rules. In a production system that needs no UI, disable both completely via `springdoc.api-docs.enabled=false` and `springdoc.swagger-ui.enabled=false` using profiles/config; still verify the gateway does not route docs on another path.

### 5.3. `src/main/java/demo/ManagementSecurityApplication.java`

```java
package demo;

import java.util.Map;

import io.swagger.v3.oas.annotations.Hidden;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ManagementSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManagementSecurityApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("viewer")
                        .password(encoder.encode("viewer-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("docs")
                        .password(encoder.encode("docs-pass"))
                        .roles("DOCS")
                        .build(),
                User.withUsername("ops")
                        .password(encoder.encode("ops-pass"))
                        .roles("OPS", "DOCS")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        // Minimal health only for probes / anonymous.
                        .requestMatchers(EndpointRequest.to("health"))
                            .permitAll()

                        // Exposed Actuator endpoints
                        // require ROLE_OPS.
                        .requestMatchers(EndpointRequest.toAnyEndpoint())
                            .hasRole("OPS")

                        // Actuator path fallback for discovery/unknown URLs
                        // in the demo; applies even if the endpoint is unexposed.
                        .requestMatchers("/actuator", "/actuator/**")
                            .hasRole("OPS")

                        // OpenAPI JSON, YAML, and Swagger UI assets.
                        .requestMatchers(
                                "/v3/api-docs",
                                "/v3/api-docs/**",
                                "/v3/api-docs.yaml",
                                "/swagger-ui.html",
                                "/swagger-ui/**")
                            .hasRole("DOCS")

                        // Every diagnostic route must be declared explicitly.
                        .requestMatchers("/internal/diagnostics/**")
                            .hasRole("OPS")

                        // Only public business endpoint in the demo.
                        .requestMatchers("/api/public").permitAll()

                        // Prevent new routes from becoming public automatically.
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @RestController
    static class PublicController {
        @GetMapping("/api/public")
        Map<String, String> publicApi() {
            return Map.of("message", "public");
        }
    }

    @Hidden // Hides from OpenAPI only; does NOT replace authorization.
    @RestController
    static class DiagnosticController {
        @GetMapping("/internal/diagnostics/ping")
        Map<String, String> ping(Authentication authentication) {
            return Map.of("state", "ok");
        }
    }
}
```

#### Why does the example use one `SecurityFilterChain`?

For a demo app sharing port 8080, **a single clearly ordered chain** makes the lesson easy to verify:

- `EndpointRequest.to("health")` is a Boot-provided matcher based on the Actuator endpoint rather than just a hardcoded string. It can match health and health subpaths; therefore keep `show-details=never`, limit health groups, and verify actual behavior. If you want only a single exact probe path public, write a dedicated matcher for the approved path/probe and recheck when base path changes.
- `EndpointRequest.toAnyEndpoint()` requires OPS for existing Actuator endpoints. The `/actuator/**` fallback in the demo also blocks anonymous users from probing similar paths, though it does not make an unexposed endpoint suddenly exist.
- Docs and Swagger UI have **separate** matchers. An `ops` user in the demo also has `ROLE_DOCS` because both roles were seeded; `ROLE_OPS` does not imply `ROLE_DOCS` by default.
- `/internal/diagnostics/**` requires OPS; the controller returns one harmless value. Never return environment variables, stack traces, keys, request headers, or user data.
- `anyRequest().denyAll()` ensures new URLs never open automatically.
- Spring Boot backs off from Actuator security auto-configuration when the app defines a custom chain; this bean bears responsibility for securing them.

**Note on `@Hidden`:** this OpenAPI annotation omits diagnostics from generated docs. It only **reduces disclosure via docs**, not access control. Removing `@Hidden` must still leave OPS role and network restrictions protecting the endpoint. Never do the reverse: relying on a path being unlisted to allow anonymous calls.

**Note on the user store:** the three passwords in this guide are for local execution only. Production must never hardcode credentials or use in-memory users for operations; it needs a secret manager/identity provider, TLS, rate limiting, MFA for privileged groups where appropriate, and controlled auditing. Basic Auth must run over HTTPS if ever used outside localhost.

### 5.4. Do not confuse `SecurityFilterChain` with enabling endpoints

Even when OPS is authenticated, `GET /actuator/env` still **has no handler** in the demo because `env` has no access granted and is not in exposure. The expected result for OPS is **404**, not 200. When an anonymous caller hits an unexposed path matched by the fallback security matcher, they may receive 401/403 **before** reaching the conclusion that no HTTP handler exists; to verify an endpoint is truly unexposed, send an OPS-authenticated request or inspect endpoint mappings/config. Do not conclude exposure state from a single anonymous status code.

If you change `management.endpoints.web.base-path`, a hardcoded `/actuator/**` rule misses the new base path; `EndpointRequest` avoids relying on a fixed path for Actuator-registered endpoints. For docs, if you change `springdoc.api-docs.path` or a custom Swagger UI path, update request matchers and tests accordingly.

## 6. Testing with Spring Security Test and MockMvc

Create `src/test/java/demo/ManagementSecurityTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class ManagementSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiIsAvailableAnonymously() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void healthIsPublicButLimited() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").exists())
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void metricsRequiresOps() throws Exception {
        mvc.perform(get("/actuator/metrics"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/actuator/metrics")
                        .with(httpBasic("viewer", "viewer-pass")))
                .andExpect(status().isForbidden());

        mvc.perform(get("/actuator/metrics")
                        .with(httpBasic("ops", "ops-pass")))
                .andExpect(status().isOk());
    }

    @Test
    void unexposedEnvironmentStaysUnavailable() throws Exception {
        mvc.perform(get("/actuator/env")
                        .with(httpBasic("ops", "ops-pass")))
                .andExpect(status().isNotFound());
    }

    @Test
    void openApiRequiresDocsRole() throws Exception {
        mvc.perform(get("/v3/api-docs"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/v3/api-docs")
                        .with(httpBasic("viewer", "viewer-pass")))
                .andExpect(status().isForbidden());

        mvc.perform(get("/v3/api-docs")
                        .with(httpBasic("docs", "docs-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi").exists());
    }

    @Test
    void diagnosticsAreOpsOnly() throws Exception {
        mvc.perform(get("/internal/diagnostics/ping"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/internal/diagnostics/ping")
                        .with(httpBasic("docs", "docs-pass")))
                .andExpect(status().isForbidden());

        mvc.perform(get("/internal/diagnostics/ping")
                        .with(httpBasic("ops", "ops-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("ok"));
    }
}
```

**Checks before treating tests as proof:**

- `@AutoConfigureMockMvc(addFilters=true)` is needed to keep Spring Security filters active; `addFilters=false` invalidates authorization tests.
- `httpBasic(...)` puts credentials on the request and runs through the test application context's provider; **never** use `@WithMockUser` in tests intended to verify passwords.
- 401 = missing/invalid credentials, 403 = authenticated but missing role (in this Basic API setup); form-login apps typically return a 302 redirect instead of 401.
- The `/actuator/env` test uses OPS to confirm 404 **after passing the role check**; testing anonymously gives 401, which does not prove the endpoint is disabled.
- The `/v3/api-docs` test confirms both that OpenAPI JSON is generated and that `USER` cannot access it. Add tests for `/v3/api-docs.yaml` and `/swagger-ui/index.html` when those routes are used in deployment; update tests if paths change.
- If the docs library is absent or incompatible, OpenAPI tests will fail; never "fix" that with `permitAll("/**")`. Check dependencies, base paths, and Spring Security matchers.

### Manual testing

From the directory containing `pom.xml`:

```bash
mvn -q test
mvn -q -DskipTests package
java -jar target/management-security-demo-0.0.1-SNAPSHOT.jar
```

In another terminal:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i -u viewer:viewer-pass http://localhost:8080/actuator/metrics
curl -i -u ops:ops-pass http://localhost:8080/actuator/metrics
curl -i -u ops:ops-pass http://localhost:8080/actuator/env
curl -i http://localhost:8080/v3/api-docs
curl -i -u docs:docs-pass http://localhost:8080/v3/api-docs
curl -i -u docs:docs-pass http://localhost:8080/internal/diagnostics/ping
curl -i -u ops:ops-pass http://localhost:8080/internal/diagnostics/ping
```

Expected statuses in order: **200, 200, 401, 403, 200, 404, 401, 200, 403, 200**. `/actuator/health` returns at least `{"status":"UP"}` when the demo's health indicators are healthy; health values vary at runtime, so automated tests only assert that `status` exists and `components` does not. `/internal/diagnostics/ping` returns only:

```json
{
  "state": "ok"
}
```

When visiting `http://localhost:8080/swagger-ui/index.html` in a browser, HTTP Basic prompts for docs/ops credentials. Swagger UI also loads JSON config, OpenAPI descriptions, and static assets, so protecting only `swagger-ui.html` is insufficient.

**Never claim these commands ran successfully if you have not executed them**; these statuses are expected outcomes for the exact code/config above. If results differ, check Spring Boot/springdoc versions, management exposure, and filter mappings instead of opening routes publicly to make them pass.

## 7. Securing OpenAPI and Swagger UI in real applications

OpenAPI/Swagger UI helps developers, yet introduces surface-discovery risks and can expose sample payloads, schemas, error models, hidden/internal endpoints, role/permission descriptions, or server URLs. Three protection layers are needed:

### 7.1. Both routes and assets are controlled

With springdoc-openapi on Spring MVC, common paths are:

- `/v3/api-docs` and `/v3/api-docs.yaml`: API specification data.
- `/v3/api-docs/{group}`: when using grouped OpenAPI.
- `/swagger-ui.html`: entry path/redirect.
- `/swagger-ui/**`: pages, JS/CSS, and related assets.

If you customize paths via springdoc config or deploy behind a context path/gateway, matchers must cover the **actual post-routing paths**. At minimum, test anonymous users, unauthorized users, and docs-authorized users for **both JSON and UI**. Securing JS/CSS alone does not protect the JSON spec; conversely, blocking the spec while leaving the UI public is not a coherent security design either.

### 7.2. Disable completely when unneeded

In production environments prohibiting online docs, consider:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

This is an **alternative profile/config** replacing the `enabled: true` lines in the demo—do not paste both into conflicting blocks. Once disabled, verify via HTTP tests that docs and UI have no active handlers and that gateways/CDNs do not serve cached copies. Disabling OpenAPI does not stop backend APIs from running; endpoints still require their own security policies.

### 7.3. Swagger UI does not grant backend authorization

Even when Swagger UI is restricted to DOCS, the "Try it out" button sends HTTP requests to the API and must obey the identity/token used on that request. OpenAPI security scheme definitions only document credential types; they do not perform authentication/authorization in place of Spring Security. With OAuth2 in Swagger UI, protect client IDs/secrets and redirect URIs; never embed production tokens, refresh tokens, or secrets in static config, logs, or JSON examples.

**Never use `@Hidden` as a substitute for blocking a route.** The annotation only controls whether the endpoint appears in docs. Any caller who knows the URL can still send direct HTTP requests; Spring Security and service policies govern the outcome.

## 8. Management port, ingress, and network policies

Moving Actuator to a separate management port can help:

```yaml
server:
  port: 8080

management:
  server:
    port: 9001
    address: 127.0.0.1
```

This is a **deployment variant**, not part of the shared-port example in section 5. When the management port differs from the application port, `management.server.address` can restrict the listening interface. `127.0.0.1` works only when a monitoring agent in the same network namespace/host can reach loopback; in containers/Kubernetes, kubelet probes or external monitoring services may **not** be able to reach it. Use bindings and `NetworkPolicy`/firewalls suited to your real architecture instead of blindly copying localhost.

A separate port is **infrastructure separation**, not authorization:

- Block the management port at public load balancers/ingress, security groups, and firewalls.
- Allow only identified monitoring/operations sources.
- Use TLS/mTLS, service identities, or SSO when traffic crosses potentially untrusted networks.
- Never add gateway rules like `/actuator/** -> public`, and never expose paths via alternate hostnames, direct node IPs, or service mesh routes.
- Verify which context/HTTP security chain governs management endpoints on the **separate port**. Testing port 8080 does not prove port 9001 is secure. When using a separate management port or management context, run integration/network tests on that port and inspect all active filters and security beans.
- Consider disabling HTTP management exposure completely if using only JMX or a specialized agent; JMX also requires its own security and network configuration.

**Warning about health on a separate port:** sometimes the management server is healthy while the main connector fails; Kubernetes liveness/readiness probes targeting only the management port can miss main-traffic failures. Spring Boot offers an option to expose health probes on the main server port for better fidelity, e.g., `management.endpoint.health.probes.add-additional-paths=true` (creating `/livez`, `/readyz` per config). When enabled, verify **security and exposure on both ports**.

## 9. Health/liveness/readiness: letting probes work without leaking data

A health endpoint should return enough information for an orchestrator to decide routing/restarts, not enough for outsiders to inspect your environment and architecture.

**Distinguish:**

- **Liveness:** is the process still alive and capable of running? Do not bind every external dependency to liveness, or a shared DB outage can cause the orchestrator to restart all instances simultaneously.
- **Readiness:** should this instance receive traffic right now? May evaluate critical dependencies per application strategy.
- **Overall health:** usually includes more indicators; if public, omit details and component names.

Spring Boot example with probes enabled:

```text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Do not assume health is always **200**: a `DOWN` component can cause the endpoint to return an appropriate HTTP status such as 503. Security test suites should distinguish **reachable without login** from **actual UP/DOWN system health**. If using roles to protect health details, note that `management.endpoint.health.show-details=when-authorized` and `management.endpoint.health.roles` form a policy layer **for health details only**, not a replacement for security filters on other URLs.

When health responses vary by profile or Kubernetes, verify that fields containing URIs, hostnames, dependency names, messages, or stack traces are never exposed to anonymous callers. `show-details=always` is dangerous if the health endpoint is public.

## 10. Metrics and logging: diagnostic values can also be sensitive

Metrics often include application names, routes, status codes, cache names, database pools, and tags. If labels are built from user IDs, tokens, emails, raw URIs, or query strings, metrics can leak data or cause cardinality explosions. Never create tags from unnormalized sensitive data; secure both monitoring endpoints and metric storage backends.

Endpoints requiring special caution:

- `/actuator/env`, `/actuator/configprops`: include sensitive-value sanitization, but **sanitization is not a guarantee** against inferring configuration or leaking metadata. Never enable `show-values=always` in public environments.
- `/actuator/beans`, `/actuator/conditions`, `/actuator/mappings`: aid reconnaissance of architecture, bean names, and URLs.
- `/actuator/logfile`, `/actuator/httpexchanges`: can contain request paths, headers, user info, errors, and operational data. Never log raw `Authorization`, cookies, or private payloads.
- `/actuator/threaddump` and `/actuator/heapdump`: can contain highly sensitive in-memory data like tokens/secrets; control large downloads and artifact storage locations.
- `/actuator/loggers`: can allow changing log levels; overly broad DEBUG/TRACE increases data-leakage risk, system load, and log costs.
- `/actuator/shutdown` and custom mutating endpoints: modify state and should not be enabled merely for convenience testing.

Spring Boot 3.5 lets you limit access to `read-only` and set `max-permitted`, yet you must still verify each endpoint's behavior, network rules, and roles. Dangerous endpoints may be disabled by default; never open them in production for a one-off diagnostic command without a formal process to close them again.

**Practical recommendation:** when deep incident diagnostics are required, use an approved, time-bound, audited break-glass workflow with rollback; never leave a shared `ROLE_ADMIN` permanently open on Internet-facing endpoints.

## 11. Custom diagnostics: designing safer endpoints from the start

If a custom endpoint like `GET /internal/diagnostics/ping` is genuinely required:

1. **Return minimal data only:** aggregated state/latency or status codes containing no hostnames, SQL, stack traces, request headers, secrets, or user IDs.
2. **Never mix reads and writes:** reading state and changing state must use separate endpoints/HTTP methods with fine-grained permissions and auditing. Never create a side-effecting `GET /debug/clear-cache`.
3. **Enforce policy at both HTTP and service layers:** routes require OPS, and service actions validate environment, tenant, or business approvals; background jobs must not bypass invariants.
4. **Rate limits and timeouts:** diagnostic queries can be expensive, exhausting thread/connection pools or stressing databases; apply bounds, pagination, and controlled async jobs where appropriate.
5. **Response formatting:** use allowlisted response DTOs and error handlers that leak no stack traces; avoid returning raw `Exception.toString()` or `System.getenv()`.
6. **Controlled auditing:** log verified actor, action, resource, and outcome without dumping tokens, cookies, or passwords.
7. **Feature flags/environments:** if a route is unnecessary in production, do not register it, or block access per profile with tested config. Merely renaming `/debug` to `/private` does not fix the risk.

### Anti-pattern example: do not copy

```java
@GetMapping("/debug/config")
Map<String, String> debugConfig() {
    return System.getenv(); // Never expose the entire ENV over HTTP!
}
```

This is a **counter-example** to help spot mistakes, not part of the runnable app in section 5. `System.getenv()` can hold database credentials, cloud tokens, and secrets. Do not soften it by "enabling only for `ROLE_USER`"; if configuration status genuinely needs inspection, build a DTO containing only approved fields and require OPS plus a secure network.

## 12. CSRF, CORS, and HTTP methods on management endpoints

**CSRF:** Spring Security protects unsafe HTTP methods by default. If you expose write endpoints such as `loggers`, `shutdown`, or custom POST/PUT/DELETE routes, requests with valid credentials can still fail with **403 due to a missing CSRF token**. Never solve this by calling `csrf.disable()` application-wide just so Postman or curl works. Align credentials and CSRF with the client model: browser cookies and HTTP Basic carry auto-submission risks, whereas Bearer-only APIs have a different threat model. If you truly must exempt a non-browser management client from CSRF, use a tightly scoped matcher, strong authentication, network controls, auditing, and negative tests.

**CORS:** browsers enforce CORS, not backend authentication. Actuator has its own CORS settings such as `management.endpoints.web.cors.allowed-origins`; enable them only for trusted origins and avoid wildcards with credentials. CLI `curl` can still send HTTP requests even when browser CORS blocks JS; therefore CORS is not a firewall.

**HTTP methods:** use GET/HEAD for read-only operations and POST/PUT/DELETE for controlled mutations. `management.endpoints.access.max-permitted=read-only` limits Actuator write operations at the application level, but custom controllers such as `/internal/**` are not automatically governed by it—they need their own rules.

**Response caching:** health, metrics, docs, and diagnostics can change continuously or hold private info. Set `Cache-Control` and configure proxy/CDN caching appropriately; a publicly cached docs/diagnostics response can remain exposed even after security rules are fixed.

## 13. Preserving protection when changing paths or frameworks

Review matchers whenever any of the following change:

- Changing `management.endpoints.web.base-path` from `/actuator` to `/manage`: hardcoded `/actuator/**` rules will miss it; `EndpointRequest` reduces this risk for Actuator endpoints. Test actual URLs after path changes.
- Multiple `SecurityFilterChain` beans: each has `@Order` priority and its own `securityMatcher`. If a management chain matches only Actuator, another chain must still cover business APIs, docs, and diagnostics. **Never let routes fall outside every chain.**
- Using a separate management port: test filter chains, contexts, and ingress on the **management port**, not just the app port.
- Spring MVC → WebFlux: use `SecurityWebFilterChain`, `ServerHttpSecurity`, and reactive Actuator matchers instead of Servlet `HttpSecurity` and the Servlet `EndpointRequest` package. Never plug Servlet filters into Netty WebFlux.
- Using springdoc grouped APIs, custom Swagger UI paths, or API gateway rewrites: update matchers for `/v3/api-docs/**`, YAML, UI assets, redirects, and config URLs. External paths and Servlet-facing paths may differ.
- Spring Boot 3 → Boot 4: auto-configuration packages and dependencies may change; consult version-specific docs instead of copying imports without compiling and testing.

**Common mistake:** defining a chain with `.securityMatcher(EndpointRequest.toAnyEndpoint())` for Actuator without any chain for the rest of the app. Spring Boot docs warn that once a custom chain is declared, default security backs off; never assume the business API remains protected.

## 14. Testing across every layer of defense

### API/role matrix

| Request | Anonymous | ROLE_USER | ROLE_DOCS | ROLE_OPS (also seeded with DOCS) |
| --- | --- | --- | --- | --- |
| `GET /api/public` | 200 | 200 | 200 | 200 |
| `GET /actuator/health` | 200 if health UP | 200 | 200 | 200 |
| `GET /actuator/metrics` | 401 | 403 | 403 | 200 |
| `GET /actuator/env` | 401 via fallback | 403 via fallback | 403 via fallback | 404 unexposed |
| `GET /v3/api-docs` | 401 | 403 | 200 | 200 |
| `GET /internal/diagnostics/ping` | 401 | 403 | 403 | 200 |

This table shows **expectations for the demo config** when health is UP; it is not a universal rule for every Spring Security deployment. Status 401 may be 302 with form login, or 404 instead of 401 if a gateway blocks routes before reaching the app.

### Additional deployment test suite

- **Endpoint inventory:** verify which URLs are actually exposed, not just those listed in documentation.
- **Custom security regression:** add a `SecurityFilterChain` and rerun Actuator tests to verify Boot auto-configuration backoff caused no exposure.
- **Multiple chains/path rewrites:** vary base paths, management ports, context paths, API gateway prefixes, and OpenAPI groups.
- **Management network:** verify port 9001 is unreachable from the public Internet while authorized monitoring agents can connect. Test through ingress and direct pod/node paths where relevant.
- **Secrets:** `env/configprops/heapdump/logfile` must stay unexposed; Swagger specs must contain no secrets or sensitive examples; diagnostics must leak no error stacks.
- **Health details:** public callers see status only; probes work without revealing dependency names; `DOWN`/`OUT_OF_SERVICE` statuses behave properly.
- **Write methods:** missing roles/CSRF or `read-only` access must block logger/shutdown mutations, with auditing on permitted actions.
- **Token/SSO:** if replacing Basic with OAuth2/JWT, test valid tokens, expired tokens, invalid signatures, wrong issuer/audience, missing scopes, and service-account permissions.
- **Monitoring:** scraping succeeds from authorized identities and networks; labels contain no user IDs, tokens, or sensitive queries.

Every test must state its **scope**. `MockMvc` tests filters and handlers inside the Spring test context, not production firewalls, ingress, or TLS. `@WithMockUser` supplies a mock principal and does not test passwords. Use real HTTP clients against real ports for network tests, and Playwright/Selenium across real origins for browser/CORS tests.

## 15. Common deployment mistakes

1. **Exposing all of Actuator:** `management.endpoints.web.exposure.include=*` expands the surface unnecessarily, especially without network policies.
2. **Defining a custom `SecurityFilterChain` while assuming Boot still protects Actuator automatically.** Boot's auto-configuration backoff makes that assumption false.
3. **Securing only `/actuator/**` while forgetting docs, diagnostics, or changed base paths.**
4. **Moving management to a separate port yet still publishing it on public ingress.** A different port is not a firewall.
5. **Treating CORS as authentication.** `curl` bypasses browser CORS, and server-side credential/authorization checks remain mandatory.
6. **Disabling CSRF globally so POSTing to loggers/shutdown returns 200.** Align credentials and CSRF with the client model.
7. **Making health details public:** `show-details=always` can expose dependencies, statuses, and hostnames even on a "health" endpoint.
8. **Using `show-values=always` for env/configprops.** Sanitization is not a license to share all configuration.
9. **Allowing regular users to view metrics, logfiles, or heapdumps.** Observability data can leak metadata, PII, or tokens.
10. **Enabling shutdown or debug write operations just for support convenience.** Use time-bound, audited break-glass workflows.
11. **Protecting Swagger UI while forgetting `/v3/api-docs` or grouped/YAML/config paths.**
12. **Treating `@Hidden` as security.** It does not block HTTP requests.
13. **Writing GET endpoints with side effects** such as `clear-cache` or `toggle-logging`.
14. **Returning raw `System.getenv()`, request headers, or stack traces in diagnostics.**
15. **Storing Basic passwords, JWTs, or cookies in logs, screenshots, support tickets, or OpenAPI examples.**
16. **Testing only anonymous 401 on an unexposed endpoint.** Fallback security can hide that the endpoint still exists; test with OPS to distinguish 404 vs. 200.
17. **Overlooking JMX exposure:** HTTP and JMX are separate channels; locking down HTTP does not lock down JMX.
18. **Running probes only on the management server and forgetting the main listener.** A healthy management port does not guarantee the app serves main traffic.
19. **Leaving request rates or heapdump/logfile sizes unconstrained**, turning diagnostic actions into DoS or OOM risks.
20. **Leaving docs/diagnostics open across all profiles because "only developers know the URL".** URL secrecy is not authorization.
21. **Sharing one OPS role across all apps/tenants** without scoping, MFA, credential rotation, and auditing.
22. **Treating a green local test as proof of production safety.** Verify ingress, TLS, IAM, runtime config, and real networks.

## 16. Pre-release checklist

- [ ] Complete inventory exists for all Actuator, OpenAPI, Swagger UI, and custom diagnostic endpoints.
- [ ] Every Actuator endpoint has minimal access/exposure; prefer allowlists.
- [ ] Health returns only data required for probes, without exposing details or components publicly.
- [ ] Custom `SecurityFilterChain` covers management, docs, and diagnostics, with a fallback rule for all APIs.
- [ ] JSON/YAML/grouped docs, UI, assets, config, and redirect routes all require appropriate permissions or are completely disabled.
- [ ] Management port and ingress/firewall/`NetworkPolicy` allow only authorized sources.
- [ ] OPS/DOCS permissions come from trusted sources with no hardcoded demo credentials in production.
- [ ] Diagnostics return no env vars, tokens, passwords, raw logs, stack traces, or user data.
- [ ] Write operations, CSRF, and access restrictions are verified; no GET endpoints cause side effects.
- [ ] Heapdumps, logfiles, env, loggers, and shutdown are never opened outside approved processes.
- [ ] Tested anonymous, USER, DOCS, OPS, and disabled URLs to avoid a false sense of security.
- [ ] Changing base paths, management ports, or proxy routes preserves authorization; regression tests match real URLs.
- [ ] Metric labels, logging/traces, and artifacts exclude sensitive information.
- [ ] Auditing, credential rotation, emergency revocation, and time-bound break-glass procedures are in place.
- [ ] In staging, tested from both public and operations networks before deployment.

## 17. Practice questions

1. Why does adding `spring-boot-starter-actuator` not automatically expose every Actuator endpoint over HTTP?
2. Distinguish `management.endpoint.<id>.access`, `web.exposure.include`, and `SecurityFilterChain`. Which layer removes the endpoint handler completely?
3. Why is a custom `SecurityFilterChain` with `anyRequest().permitAll()` far more dangerous when Actuator is on the classpath?
4. Why is `GET /actuator/env` returning 401 to anonymous callers insufficient to prove the endpoint is unexposed? What else must you test?
5. When can health be public? Why must you combine `show-details=never`, network/probe rules, and tests?
6. Why does `ROLE_OPS` not automatically include `ROLE_DOCS`? How does OPS access docs in the demo?
7. Is protecting only `/swagger-ui.html` enough? Name the additional OpenAPI paths that must be protected.
8. Does `@Hidden` stop clients from calling `/internal/diagnostics/ping`? Which component actually blocks it?
9. Is management port 9001 inherently safe if public ingress still routes to it from the Internet?
10. Why should liveness checks not depend on every database or external service?
11. For `loggers`/`shutdown`, what risks do CSRF and `read-only` mitigate? Do they replace IAM?
12. When replacing Basic Auth with a JWT Resource Server, how should you test signature/issuer/audience, role/scope mapping, and the gateway?
13. If `management.endpoints.web.base-path` changes to `/manage`, which matchers and tests must be reviewed?
14. A diagnostic endpoint returns full stack traces but requires `ROLE_USER`: what risks remain?
15. Design an access matrix for health, metrics, docs, and diagnostics across four audiences: anonymous, developer, monitoring service account, and operations engineer.

## 18. Official documentation and reference links

- [Spring Boot 3.5 — Actuator Endpoints, Exposure and Security](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Spring Security Integration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Testing Spring MVC with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [springdoc-openapi v2 — Spring Boot 3.x, Getting Started and Compatibility](https://springdoc.org/v2/)
- [springdoc-openapi v2 — Swagger UI and OpenAPI paths](https://springdoc.org/v2/getting-started.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)

**Key takeaway:** protect Actuator and diagnostics starting from **the moment an endpoint is enabled**, not just when writing `hasRole`. Restrict access and exposure, apply Spring Security to the right chains, scrub sensitive data, isolate management networks, cover all Docs/UI paths, and test with real roles and network paths. Deployment safety is the intersection of multiple control layers, never a path named "internal".
