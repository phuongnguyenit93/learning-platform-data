# Protecting Actuator by Management Port, Path, and Matching Filter Chain

> **Scope:** Spring Boot 3.x, Spring Security 6.x, Java 17+ on the **Servlet stack** (Spring MVC). This article explains how to protect Spring Boot Actuator by **management port**, **exposed paths and endpoint set**, and the **`SecurityFilterChain` that actually handles the request**. The content focuses on application operations, not turning Actuator into a public API. Examples illustrate configurations for two models: **Actuator sharing the application port** and **Actuator on a separate management port**. Both require security testing in their corresponding environments.

## 1. Why Does Actuator Need a Separate Protection Policy?

Spring Boot Actuator provides endpoints for runtime monitoring and management. These endpoints can expose application health, build information, metrics, loggers, configuration, or other operational data. Some endpoints are only needed by monitoring systems, while sensitive endpoints must never be opened publicly.

If an application has these URLs:

~~~text
GET  /api/orders
GET  /actuator/health
GET  /actuator/metrics
GET  /actuator/env
POST /actuator/loggers/com.example
~~~

a user's permission to view orders is **not** permission to view metrics, environment configuration, or change log levels. Using the same login mechanism for everyone without separating policies easily turns "authenticated user" into "operator".

In particular, some endpoints can contain sensitive information, expand the attack surface, or perform state changes. You must therefore clearly decide **what is exposed**, **where requests come from**, and **who is allowed to use them**.

### Three Independent Control Layers

| Layer | Question | Configuration examples |
| --- | --- | --- |
| **Exposure** | Is the endpoint published over HTTP? | `management.endpoints.web.exposure.include` / `exclude`. |
| **Network/port** | Who can connect to the port and network path hosting the endpoint? | `management.server.port`, `management.server.address`, firewall, ingress, ACL, mTLS. |
| **Authentication/authorization** | When a request reaches the endpoint, what identity and permissions does the server check? | `SecurityFilterChain`, `EndpointRequest`, `hasRole("OPS")`. |

**Do not conflate these three layers.** An unexposed HTTP endpoint cannot be accessed via normal HTTP `GET`, yet exposure does not decide who is authorized. Conversely, an exposed endpoint still requires authorization and network protection. Moving Actuator to port 9090 **does not automatically make that port safe** if it is exposed to the Internet.

## 2. Endpoint Groups and Sensitivity Levels

Common endpoints:

| Endpoint ID | Purpose | Protection guidance |
| --- | --- | --- |
| `health` | Overall status, health groups, readiness/liveness if enabled. | Summary status may be opened to load balancer/orchestrator; restrict sensitive details. |
| `info` | Build info, version, or published metadata. | Open only if data has been audited; do not assume harmless by default. |
| `metrics` | Performance/resource utilization metric names and values. | Restrict to monitoring/OPS to avoid leaking runtime information. |
| `prometheus` | Exports metrics in Prometheus format, if the matching Micrometer registry is present. | Intended for trusted scrapers; dedicated network policy/auth. |
| `loggers` | View and potentially adjust log levels depending on HTTP method/capabilities. | Narrow operator privileges, auditing, and change control. |
| `env` | Inspect environment properties and configuration sources. | Sensitive; do not expose indiscriminately by default; sanitization does not replace protection. |
| `configprops` | Bound configuration properties information. | Sensitive; evaluate necessity and sanitization capabilities. |
| `beans`, `mappings`, `conditions` | Application structure, routes, auto-configuration. | Diagnostics only in controlled environments. |
| `threaddump`, `heapdump` | Thread/heap diagnostics; may contain sensitive data. | Restrict tightly; heap dumps can be extremely sensitive. |
| `shutdown` | Requests application shutdown if enabled and exposed. | Never enable in public environments; restrict to privileged operations. |

The endpoint names in the table are **IDs**, not necessarily identical to the full HTTP path if base paths or path mappings have changed. Endpoint behavior also depends on dependencies, Spring Boot version, enabled/exposed state, and application extensions. Do not assume an endpoint exists just because you remember its name.

### Expose as Little as Possible

In standard configuration, Spring Boot by default exposes only a very minimal set of HTTP management endpoints (usually `health`). When adding `metrics`, the deployer must **explicitly enable exposure** and define the accompanying security requirements.

Example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

This snippet only **allows those three endpoints to be reachable over HTTP**. It **does not** grant OPS permissions, lock the port, configure firewalls, or guarantee the `prometheus` endpoint exists.

**Avoid using** `management.endpoints.web.exposure.include: "*"` in production unless every endpoint and appropriate protection layer have been thoroughly evaluated. A new dependency could add a new endpoint that wildcard exposure accidentally publishes.

Note on `exposure.exclude`: excluding can narrow the set of endpoints, but the best policy remains an explicit **`include` allowlist**. Do not expect a denylist to keep pace with endpoints added in the future.

## 3. Management Port and Paths: Understand Before Writing Security Matchers

### 3.1 Default: Actuator Sharing the Application Port

If the application uses:

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,metrics
~~~

then HTTP endpoints (if enabled and exposed) typically live at:

~~~text
http://localhost:8080/actuator/health
http://localhost:8080/actuator/info
http://localhost:8080/actuator/metrics
~~~

`management.endpoints.web.base-path` defaults to `/actuator`. It is a **prefix for web endpoints**, not a password or firewall. Changing the prefix to `/hidden-admin-92` is not a security measure: paths can still be discovered or leaked via logs, build info, or proxy configs.

When Actuator **shares the port**, web endpoints share the web server with application routes. Make sure the Actuator matcher is not shadowed by an earlier catch-all `/**` chain or an overly broad `permitAll` rule.

### 3.2 Changing the Management Base Path

Example:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,metrics
~~~

Typical paths on the same port become:

~~~text
/manage/health
/manage/info
/manage/metrics
~~~

**Pay attention:** when **sharing a port**, the management base path is affected by the Servlet context path and web server config; when running on a **separate port**, the management context may have its own base path depending on Boot configuration. Proxies may rewrite prefixes. Therefore, verify the **actual URLs** instead of inferring from a single property.

If you hard-code a security rule `requestMatchers("/actuator/**")` and change base-path to `/manage`, the old rule may stop matching. That is one reason to use `EndpointRequest` when protecting Actuator endpoints.

### 3.3 Separating Ports with management.server.port

Example:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,metrics
~~~

Meaning:

- The application serves API/UI on port `8080`.
- Management endpoints are configured to serve on port `9090`, typically in a **separate management web context** when the two ports differ.
- Actuator health is usually at `http://host:9090/manage/health` and metrics at `http://host:9090/manage/metrics`; verify context path, reverse proxy, and actual runtime behavior.
- **Do not** assume `SecurityFilterChain` beans effective on port `8080` will automatically apply identically on port `9090`. When Boot creates a separate management context, how beans/configurations are visible and auto-configured must be verified by testing **against the management port itself**.

This is an **alternative configuration option** to the shared-port example: do not merge both into one file and claim both models run simultaneously. Test whichever model you actually deploy.

### 3.4 Binding to a Management Interface

In some environments, you can restrict the management server to loopback:

~~~yaml
management:
  server:
    port: 9090
    address: 127.0.0.1
~~~

This configuration makes sense when the management port is **separate from the application port**. Once bound successfully, the service only listens on the loopback of **that specific network namespace/container**. However:

- If the app runs in Docker/Kubernetes, `127.0.0.1` is **inside the container/pod**, so external monitoring may not be able to reach it. Choose a proper network design rather than rushing to bind `0.0.0.0`.
- Binding to a private address is one restriction layer, **not a substitute** for authentication/authorization. Processes sharing the host/network namespace can still connect.
- If using Kubernetes Service/Ingress, configure firewalls, NetworkPolicy, security groups, and ingress rules for real monitoring needs. Never route the management port onto a public ingress unnecessarily.
- Do not assume a separate address setting always takes effect while management shares the main port: many container/Boot setups require a **separate port** to bind a management address distinct from the main server.

## 4. SecurityFilterChain: Selecting the Right Actuator Endpoints

Spring Boot Actuator provides `EndpointRequest` to build `RequestMatcher`s based on **endpoint IDs/endpoint mappings**, rather than just hard-coded URL strings.

Common import on the Servlet stack:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
~~~

Key APIs to remember:

- `EndpointRequest.toAnyEndpoint()`: matcher for web Actuator endpoints in the corresponding context.
- `EndpointRequest.to("health")`: matcher for the `health` endpoint ID.
- `EndpointRequest.to("health", "info")`: selects specific endpoint IDs; only `permitAll` them if truly intended to be public per policy.
- `EndpointRequest.toAnyEndpoint().excluding(...)`: excludes specific endpoint IDs when organizing multiple chains, though you must understand how fallback chains apply.

**Advantage:** changing `management.endpoints.web.base-path` from `/actuator` to `/manage` generally does not require editing matchers built from endpoint IDs. Spring Boot maps endpoint IDs to the active web management configuration.

Also remember: `EndpointRequest` and `SecurityFilterChain` do not make an **unexposed** endpoint accessible. They only identify which requests **correspond to management endpoints** in order to apply security.

### Distinguishing securityMatcher from requestMatchers

An easily confused configuration:

~~~java
http.securityMatcher(EndpointRequest.toAnyEndpoint())
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(EndpointRequest.to("health")).permitAll()
        .anyRequest().hasRole("OPS"));
~~~

- `http.securityMatcher(...)` determines whether **the entire filter chain** handles an Actuator request.
- `authorizeHttpRequests(...requestMatchers(...))` selects **authorization rules** inside the matched filter chain.
- If no chain matches, a request could proceed **unprotected by Spring Security**. Therefore, a **fallback chain** is usually needed for other application requests.
- With multiple chains, `FilterChainProxy` selects the **first matching chain** in configured order. A catch-all chain placed too early can shadow a dedicated Actuator chain.
- With the management server on a **separate port**, the chain must actually be registered in **that management context/port**. Having the right matcher name does nothing if the bean is not loaded in the right context.

## 5. Sample Spring Security Configuration: Public Health, OPS-Only Metrics

This is a complete example of **setting policy when Actuator shares the application port**. The classes use Spring Boot 3.x, Spring Security 6.x on Servlet, Java 17+, and matching dependencies. The demo uses HTTP Basic so status codes are clearly observable.

Desired policy:

1. `health` is allowed for health-check monitoring without **exposing sensitive details** to anonymous callers.
2. `info` and `metrics` are only for users with role `OPS`.
3. Any other exposed Actuator endpoints must require `OPS`; this does not imply they should be exposed.
4. Application requests sit in a separate **fallback chain**.
5. Any state-changing POST is allowed only if policy and other protections (such as CSRF where applicable) permit it.

### 5.1 Maven Dependencies

In a Spring Boot project's `pom.xml` using Boot parent/BOM, minimal dependencies for web + actuator + security + tests:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
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
~~~

This is an **XML snippet**, not a standalone POM. You should normally rely on Spring Boot's dependency management so Spring Security/Actuator module versions stay compatible.

### 5.2 application.yml for the Shared-Port Demo

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: when_authorized
      roles: OPS

app:
  ops:
    username: ${OPS_USERNAME:ops}
    password: ${OPS_PASSWORD}
~~~

Analysis:

- `/manage` is a base path, not "security by obscurity". The concrete metrics URL on the same port is `/manage/metrics`.
- Only expose `health`, `info`, and `metrics`. Do not expose `env`, `beans`, `heapdump`, or `shutdown` just for easy checking.
- `management.endpoint.health.show-details=when_authorized` paired with `management.endpoint.health.roles=OPS` ensures health details appear only when authorized by the configured role. The health path may be public, while the body for unauthorized callers should show only overall status; inspect the exact response in your Boot version.
- `app.ops.username/password` are properties of the **demo application**, **not** standard Actuator/Spring Security properties. The `OPS_PASSWORD` environment variable must be set before startup. Never put real passwords in Git.
- Spring Boot may add different health contributors based on dependencies; `UP`/`DOWN` health status and HTTP status depend on runtime state. Health status tests must account for environment state (if disk/db is unhealthy, it may return `503`).

### 5.3 Main Class

File `src/main/java/com/example/management/ManagementDemoApplication.java`:

~~~java
package com.example.management;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManagementDemoApplication.class, args);
    }
}
~~~

### 5.4 SecurityFilterChain with @Order and EndpointRequest

File `src/main/java/com/example/management/ManagementSecurityConfig.java`:

~~~java
package com.example.management;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ManagementSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("OPS")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Protection model:**

- `@Order(1)` prioritizes the Actuator chain before the fallback chain.
- `EndpointRequest.toAnyEndpoint()` selects Actuator requests present in the matching context.
- `EndpointRequest.to("health")` permits the health endpoint, not all of `/manage/**`.
- `anyRequest().hasRole("OPS")` on the Actuator chain requires `ROLE_OPS` for metrics, info, and any other endpoints matched by the chain.
- `@Order(2)` is the application chain with fallback `anyRequest().authenticated()`; non-management endpoints still require authentication, except `/public/**`. Because the demo does not use form login, the HTTP Basic entry point typically returns `401` when credentials are missing.
- Both chains use Basic **for test illustration only**. Production may use OAuth2/mTLS/service accounts/SSO depending on architecture, ensuring management credentials and privileges stay isolated. HTTP Basic requires HTTPS over real networks.
- Do not declare `csrf.disable()`. The demo GET endpoints do not mutate state; if exposing Actuator operations over POST, evaluate CSRF, authentication, and state-change authorization separately. **Do not disable CSRF app-wide just because a management POST request fails.**

**Why not write `.requestMatchers("/manage/**").permitAll()`?** Because it accidentally opens metrics, env/loggers, or newly added endpoints. Furthermore, it couples policy to a string path; `EndpointRequest` understands Actuator's actual mappings.

### 5.5 UserDetailsService and PasswordEncoder (Demo Only)

File `src/main/java/com/example/management/OpsUserConfig.java`:

~~~java
package com.example.management;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class OpsUserConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            @Value("${app.ops.username}") String username,
            @Value("${app.ops.password}") String password,
            PasswordEncoder encoder) {

        return new InMemoryUserDetailsManager(
            User.withUsername(username)
                .password(encoder.encode(password))
                .roles("OPS")
                .build()
        );
    }
}
~~~

`roles("OPS")` creates the `ROLE_OPS` authority matching `hasRole("OPS")` in the Actuator chain. The password must be loaded securely from an environment variable/secret manager; it is hashed with BCrypt when initializing the demo user. Never commit real passwords. This is **not** how to design a production user store with auditing/rotation/MFA.

**Demo model limitation:** one `UserDetailsService` is visible to both chains. The `ops` user can also pass `authenticated()` in the fallback application chain. If strict isolation between **operator identities** and end-user sessions is required, design separate authentication managers/providers or explicit identity policies per chain rather than a single shared store. Separating ports does not automatically separate identities.

### 5.6 Application Endpoints for Comparison

File `src/main/java/com/example/management/AppController.java`:

~~~java
package com.example.management;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AppController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/app/private")
    public String privateEndpoint() {
        return "private";
    }
}
~~~

`GET /public/ping` is expected to return `pong` without authentication, while `GET /app/private` requires valid credentials. With a stricter policy, you can require a dedicated application role rather than just `authenticated()`.

## 6. Changing base-path or path-mapping Without Exposing Endpoints

Suppose the management base path starts as `/manage`, and you later change it to `/internal/ops`:

~~~yaml
management:
  endpoints:
    web:
      base-path: /internal/ops
      exposure:
        include: health,info,metrics
~~~

Steps to follow:

1. Verify the actual `/internal/ops/health` and `/internal/ops/metrics` URLs at runtime (possibly prefixed by Servlet context path).
2. Because the chain uses `EndpointRequest.toAnyEndpoint()` and `EndpointRequest.to("health")`, the policy continues selecting the **right endpoint IDs** without relying strictly on hard-coded `/manage/**`.
3. Verify the old `/manage/metrics` route is no longer an exposed management endpoint; an accidental request to the old URL may hit the fallback chain, and no sensitive non-Actuator controller should exist under the old name.
4. Check that reverse proxies, monitoring scrape configs, load balancer health checks, and alert rules have updated paths.
5. Directly test both anonymous and OPS after the change; do not test only a successful OPS request and assume anonymous is blocked.

To change only the health path (without changing its ID), Spring Boot supports `management.endpoints.web.path-mapping.<id>`. Example:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        health: status
~~~

In this model, the typical web health path is `/manage/status` instead of `/manage/health`, yet **the ID remains `health`**. `EndpointRequest.to("health")` expresses permissions consistently by endpoint. If using reverse proxy rewrites, verify both the upstream path and external path.

**Note on sub-routes:** health groups can have subpaths like `/manage/health/readiness` when probes are configured. Do not assume a matcher `requestMatchers("/manage/health")` covers every branch; use endpoint-aware matchers or test each required URL.

## 7. Separate Management Port: What Changes for Security?

An `application.yml` variant for deployments with an administrative network segment:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: when_authorized
      roles: OPS

app:
  ops:
    username: ${OPS_USERNAME:ops}
    password: ${OPS_PASSWORD}
~~~

This configuration illustrates the intent to serve the application on `8080` and management only on `127.0.0.1:9090`, if infrastructure supports it. It is not a file to copy verbatim into Kubernetes if Prometheus runs outside the network namespace; production network design must match.

### Two Protection Layers with a Separate Port

**Layer 1 — Network:** only the monitoring/ops network may connect. Options include loopback, internal interfaces, firewalls/security groups, or Kubernetes NetworkPolicy. If traffic must pass through a reverse proxy, allow only trusted proxies to route to the management port; never configure an arbitrary public ingress.

**Layer 2 — Spring Security:** requests reaching the management port must still be authenticated/authorized per policy. `metrics` is only for OPS/monitoring identities; `health` may be internal-public with details hidden.

**Crucial note:** Spring Boot may create a **management child ApplicationContext** when using a different port. To prove policy takes effect on this port, test **the management port itself**, not just MockMvc against the main web application context. If the child context does not pick up the custom `SecurityFilterChain` you expected, configure management security in the appropriate context as supported by your Boot version, and inspect startup/test logs. Never infer from "the config class exists in the app" that port 9090 is protected.

### A Separate Port Is Not a Firewall

TCP port `9090` can be scanned, NATed, ingressed, or exposed by a Service. Changing a port number does not add real security by itself. Inspect effective network configuration (container port mappings, service endpoints, load balancer listeners, host firewalls, cloud security groups, and reverse proxies).

In Docker deployments, container `127.0.0.1` may only be reachable inside the container. If you change it to bind all interfaces so scrapers can reach it, add firewall/network policies and authentication; never drop a protection layer just to make scraping work.

## 8. Management Server Context, Bean Scope, and Auto-Configured Security Defaults

Spring Boot includes auto-configuration for Actuator Security **when Spring Security is on the classpath**. In common setups, if the application **has not declared** any `SecurityFilterChain`, Boot may configure default restrictions for management endpoints. However, once the application declares **any matching custom `SecurityFilterChain` bean**, management security auto-configuration may **back off**. At that point, you **must explicitly** define authorization for Actuator.

### Why Adding an Application Filter Chain Can Introduce Risk

Suppose previously:

~~~text
Spring Boot auto security:
  /actuator/health -> accessible
  other actuator endpoints -> authenticated
~~~

Then you add a `SecurityFilterChain` only for `/api/**` without a chain covering Actuator. Do not assume Boot will keep blocking `/actuator/metrics`. Depending on auto-config conditions, the custom bean can disable default security creation; an exposed management endpoint unmatched by your chain becomes a vulnerability.

**How to prevent this:**

- Declare a dedicated chain with `EndpointRequest.toAnyEndpoint()` when Actuator and app share the servlet context/port.
- Set consistent `@Order` values with a fallback chain protecting application routes.
- When on a separate port, inspect the management child context itself, endpoint request mappings, and loaded chains there.
- Add negative anonymous tests for metrics/info, not just positive OPS tests.
- Re-verify at runtime after upgrading Spring Boot, changing application contexts, adding filter chains, or changing ingress rules.

The Spring Boot documentation on actuator security is authoritative for your **running version**; never assume behavior from an older version holds after an upgrade.

## 9. Testing Shared-Port Actuator with MockMvc

For the shared-port model in section 5, `@SpringBootTest` + `@AutoConfigureMockMvc` runs requests through the Spring Security filters in the ApplicationContext. This verifies matchers/authorization at the Servlet layer **without opening a TCP port**.

File `src/test/java/com/example/management/ActuatorSecurityTest.java`:

~~~java
package com.example.management;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
    "management.endpoints.web.base-path=/manage",
    "management.endpoints.web.exposure.include=health,info,metrics",
    "app.ops.username=ops",
    "app.ops.password=local-only-test-password"
})
@AutoConfigureMockMvc
class ActuatorSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingIsAllowed() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousMetricsIsRejected() throws Exception {
        mvc.perform(get("/manage/metrics"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/manage/metrics")
                .with(httpBasic("ops", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void operatorCanReadMetrics() throws Exception {
        mvc.perform(get("/manage/metrics")
                .with(httpBasic("ops", "local-only-test-password")))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousInfoIsRejected() throws Exception {
        mvc.perform(get("/manage/info"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousPrivateApplicationIsRejected() throws Exception {
        mvc.perform(get("/app/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void healthIsAccessibleIfHealthy() throws Exception {
        mvc.perform(get("/manage/health"))
            .andExpect(status().isOk());
    }
}
~~~

**This test belongs to the same demo project.** `local-only-test-password` is strictly for test context; never use it in real environments. When the app and health contributors are healthy, `GET /manage/health` expects 200. If health status is `DOWN`, Actuator may return `503` per status mapping, so `healthIsAccessibleIfHealthy` must be interpreted according to the tested health state rather than treating 503 as an authentication error.

Key tests:

1. `anonymousMetricsIsRejected` confirms the endpoint is exposed yet not public.
2. `operatorCanReadMetrics` confirms the positive path for OPS.
3. `wrongBasicPasswordIsRejected` goes through the **demo's** real HTTP Basic authentication provider, unlike attaching `@WithMockUser(roles="OPS")`.
4. `anonymousInfoIsRejected` ensures `info` is not left public just because it sounds "non-sensitive".
5. `anonymousPrivateApplicationIsRejected` tests the fallback chain; Actuator policy does not leave the rest of the application open.
6. `healthIsAccessibleIfHealthy` shows overall health can be permitted, without asserting that health details or contributors are public.

Run with the configured Maven project:

~~~bash
mvn test
~~~

Do not fabricate fixed Maven stdout: real output depends on plugins, system health, and other test classes. Do not look only for a green build; verify the tests exercised the **right `FilterChainProxy`**, right endpoint exposure, and right management port.

### Testing the Old Path After Changing base-path

Add a test for `/actuator/metrics` after switching to `/manage` if the system has a reverse proxy or legacy routes. Expectations should not be guessed solely by URL name: without a controller, it is usually 404 after security; if the fallback chain requires login, anonymous callers may get 401 **before reaching MVC**. The goal is to prove the sensitive endpoint **is no longer publicly reachable at the old path**, not to mechanically assert "must be 404".

## 10. Testing a Separate Management Port via HTTP on That Port

When management uses a separate port, **do not test only MockMvc on the main context** and conclude the management context is protected. An integration test can start the application web server and management web server on two random ports and send real HTTP to the **management port**.

Example `@SpringBootTest` test configuration:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.server.port=0",
        "management.endpoints.web.base-path=/manage",
        "management.endpoints.web.exposure.include=health,metrics",
        "app.ops.username=ops",
        "app.ops.password=local-only-test-password"
    }
)
class ManagementPortSecurityTest {
    // Use @LocalManagementPort to get the exact runtime management port.
}
~~~

This snippet only illustrates test class configuration, not a complete test file. With `management.server.port=0`, Spring Boot allocates a random HTTP port specifically for management, and the test can inject `@LocalManagementPort` (from Spring Boot Test). Ensure the security chain is **actually applied in that context**.

### Complete Test Example Using TestRestTemplate

File `src/test/java/com/example/management/ManagementPortSecurityTest.java`:

~~~java
package com.example.management;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.server.port=0",
        "management.endpoints.web.base-path=/manage",
        "management.endpoints.web.exposure.include=health,metrics",
        "app.ops.username=ops",
        "app.ops.password=local-only-test-password"
    }
)
class ManagementPortSecurityTest {

    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate rest;

    @Test
    void anonymousCannotReadMetricsOnManagementPort() {
        String url = "http://localhost:" + managementPort
                + "/manage/metrics";

        ResponseEntity<String> response =
                rest.getForEntity(url, String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void operatorCanReadMetricsOnManagementPort() {
        String url = "http://localhost:" + managementPort
                + "/manage/metrics";

        ResponseEntity<String> response =
                rest.withBasicAuth("ops", "local-only-test-password")
                    .getForEntity(url, String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
    }
}
~~~

**Purpose:** this test does not just inspect beans in the main application context; it **hits the runtime management port directly**. If an anonymous caller reads metrics (HTTP 200), that signals a serious failure of the desired policy; inspect management context wiring and auto-configuration instead of changing the test to expect 200 "to make it pass".

This is a localhost HTTP test inside the test JVM: unencrypted HTTP is only for controlled loopback testing. Production must use HTTPS/mTLS or a suitable trusted transport. If the test runtime uses a different proxy/port or Actuator does not expose `metrics`, a 404 test does not prove auth; verify the endpoint exists via the positive operator test in the same suite.

**Note on `@LocalManagementPort`:** the annotation only makes sense when bootstrapping a web environment with the management server listening on an appropriate port. If a deployment environment does not use a separate management context, adjust the test setup to target the actual port/namespace rather than hard-coding 9090.

## 11. Health and Probes: How to Monitor While Keeping Secrets Safe?

A load balancer or Kubernetes orchestrator typically only needs to know **whether the app is alive/ready for requests**; it does not need bean lists, credentials, SQL diagnostics, or the entire environment.

### Health Details

Common options for `management.endpoint.health.show-details`:

| Value | General meaning |
| --- | --- |
| `never` | Never show health component details to callers. |
| `when_authorized` | Show details conditionally on authorized health access; can pair with `management.endpoint.health.roles`. |
| `always` | Allows details to appear broadly; risky when the health endpoint is public. |

If anonymous callers can access health, usually only expose overall status; test the real response body to avoid leaking database names, internal components, or detailed errors. `when_authorized` with `roles: OPS` is a balanced option when operators need details and anonymous callers only need status.

### Readiness/Liveness for Kubernetes

Probes can be enabled:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

When the corresponding health groups exist, URLs are typically:

~~~text
/manage/health/liveness
/manage/health/readiness
~~~

These paths are **branches of the health endpoint**. If policy allows the entire health endpoint by ID, the corresponding groups may be reachable without authentication; evaluate whether that fits requirements. Some deployments need health paths on the main application port to check the traffic-serving web server itself, because a separate management port might remain healthy even when the application port fails; Spring Boot offers additional configuration options for probes on the application port depending on version. Never treat "management health returns 200" as proof that all application request-serving layers are healthy.

**Kubernetes-specific:** making liveness depend on an external database can trigger mass pod restarts during temporary DB glitches. Design health contributors/groups around readiness/liveness semantics, not only security.

## 12. Prometheus, Metrics, and Service Identity

If `/prometheus` is required, an appropriate Micrometer Prometheus registry must be present alongside Spring Boot Actuator. Example Maven dependency (added to a project that already has starter-actuator):

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Exposure configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

**Exposing Prometheus ≠ Letting everyone on the Internet scrape it.** Typically required:

- NetworkPolicy/firewall for the monitoring network or Prometheus instance.
- Dedicated service identity with **metrics read-only** privileges; Basic auth over HTTPS or mTLS where appropriate. Do not force using the same operator account that can change loggers or shut down the app.
- Avoid labels containing PII, customer IDs, tokens, or high-cardinality values that exhaust memory and leak information.
- Monitor scrape failures after changing ports/paths, proxy rewrites, or authentication.
- Avoid wildcard exposure just because you need the `prometheus` endpoint.

### Separating MONITOR and OPS Permissions

A better model than an all-powerful OPS role:

~~~text
Anonymous / load balancer -> overall health status
MONITOR service identity  -> metrics, prometheus (read-only)
OPS operator identity     -> info, approved diagnostic endpoints
Nobody over HTTP          -> shutdown/heapdump unless explicitly approved
~~~

To implement this in practice, define explicit matchers/authorities and separate policies per HTTP method/endpoint ID. Illustrative DSL snippet inside the Actuator chain:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(EndpointRequest.to("health")).permitAll()
    .requestMatchers(EndpointRequest.to("metrics", "prometheus"))
        .hasAnyRole("MONITOR", "OPS")
    .anyRequest().hasRole("OPS")
)
~~~

This snippet is a **configuration fragment replacing the `authorizeHttpRequests` policy in section 5**, not a standalone Java class. The `prometheus` endpoint exists only when the registry and exposure are configured. If OPS is granted write access to exposed Actuator endpoints, consider a stronger permission model and **restrict exposure** rather than just adding MONITOR. You can split chains by endpoint if different authentication managers, CSRF, or session policies are needed; verify chain selection and actual ordering.

## 13. Actuator Security Is Not Only About Spring Security

### Reverse Proxies and Path Rewriting

A proxy might map:

~~~text
Public /internal-monitor/status
    -> http://127.0.0.1:9090/manage/health
~~~

If a proxy accepts public requests and forwards them to the management port, the effective network boundary has widened. Check:

- Does the proxy require identity, and does it strip user-supplied headers?
- Are source allowlists and TLS between proxy, app, and scraper properly configured?
- Which request paths are allowed to route? Could `/manage/**` accidentally be proxied instead of just health?
- Are `X-Forwarded-*` headers accepted only from trusted proxies? Host/header spoofing can corrupt URLs or policies.
- Does the proxy preserve auth responses/status/headers? Never turn 401/403 into a 200 "health okay".
- Do Actuator startup logs and actual endpoints match external paths?

Do not assume security matchers are evaluated against the external URI seen by the user. Spring Security runs on the **request reaching the backend** after servlet context and path rewriting; test both the proxy and the application.

### TLS and management.ssl

Spring Boot provides SSL settings for server/management server depending on version and topology. Use TLS for credentials/metrics over untrusted networks; HTTPS termination at a reverse proxy must still protect the downstream hop. With mTLS, manage trust stores and certificate lifecycles explicitly rather than simply turning on HTTPS and assuming clients are authenticated.

### Spring Security and Actuator JMX

`management.endpoints.web.exposure.*` controls **web HTTP** exposure, **not** JMX exposure. If the application enables JMX or remote JMX, audit JMX access/transport settings separately. Blocking `/manage/metrics` over HTTP does not imply all management channels are closed.

### Credentials and Secret Rotation

Monitoring/OPS passwords in YAML can be read by anyone with config or log access if misconfigured. Use a secret manager/Kubernetes Secret securely, restrict read permissions, and rotate under control. Review separate production account models: an operator account should not implicitly have access to business endpoints.

## 14. POST Management Operations: Authentication, Authorization, and CSRF

Many developers see Actuator mostly using GET for health/metrics, then disable CSRF across the entire application so one POST management endpoint works. That easily opens vulnerabilities for session/cookie-authenticated business operations.

Separate three questions:

1. **Is the endpoint enabled and exposed?** An endpoint excluded from HTTP exposure has no web endpoint to call.
2. **Does the caller have the right authority?** Never use just `authenticated()` for operations like changing log levels or shutdown.
3. **Does the request carry CSRF risk?** When browser-sent cookies/sessions are used, state-changing requests need CSRF protection per the threat model; HTTP Basic in browsers also raises cached-credential considerations. Never assume "Actuator is machine-to-machine so CSRF cannot happen" if management routes are reachable by browsers.

For state-changing endpoints, consider:
- Do not expose HTTP operations unnecessarily; prefer dedicated operational channels or audited admin tools.
- Use strong operator/service identities, least privilege, mTLS, or private networks.
- Protect CSRF appropriately for the request/credential model rather than disabling it application-wide.
- Maintain change logging/auditing and rollback for operational config changes.
- Test specific HTTP methods (GET/POST) across anonymous, read-only monitor, and operator identities.

### Why Simply Hiding Actuator Endpoints from Menus Has No Security Value

Actuator endpoints are called directly by HTTP clients/monitoring tools without needing a UI. Once a URL is leaked in configs or guessed, requests reach Spring MVC. UI security, CORS, or a "secret" path never replaces `FilterChain` authorization.

## 15. Configuration Mistakes to Avoid

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| Anonymous caller reads metrics | Endpoint exposed yet custom `SecurityFilterChain` does not match, default chain backed off, or management context lacks the expected chain. | Send anonymous request to exact **management port/path**; inspect chain logs and auto-config. |
| After changing base path, metrics become public | Hard-coded matcher `/actuator/**` stops matching `/manage/**`; fallback is too broad. | Use ID-based `EndpointRequest` and re-test after any path change. |
| Health check gets 401 | Actuator chain requires OPS for health too; missing dedicated rule or request hits another chain. | Check `EndpointRequest.to("health")`, chain order, health path, and proxy route. |
| Overall health returns 200 but leaks details | `management.endpoint.health.show-details=always` or custom health body leaks internals. | Test anonymous and OPS responses separately; restrict details. |
| `management.server.port` is set but endpoints remain on old port | Config not loaded, wrong profile, or unexpected context/port. | Inspect effective config/startup logs and test both ports. |
| Management port 9090 open from Internet | Overly broad firewall/ingress/security group or container port mapping. | Test external network path, not just localhost binding in docs. |
| Prometheus returns 404 | Missing Micrometer registry, endpoint not enabled/exposed, or wrong path. | Check dependency, `exposure.include`, base path, and scrape target. |
| Prometheus returns 401 | Scraper lacks credentials/mTLS or auth middleware out of sync. | Provision read-only identity and check status; never open anonymous just to scrape. |
| Metrics called as OPS still returns 403 | Wrong authority prefix or auth manager/role mapper returns different authorities. | Check `ROLE_OPS`, `hasRole("OPS")`, and Authentication. |
| A `/**` chain prevents Actuator chain from running | Wrong `@Order` or catch-all chain registered first. | Inspect first matching chain; add negative tests. |
| Metrics become public after adding custom filter chain | Boot management security auto-config may back off; new chain does not cover management. | Verify Actuator matcher and anonymous endpoint response after changes. |
| MockMvc tests pass yet separate management port is public | Tests hit only main context, skipping management child context. | Write HTTP integration test using `@LocalManagementPort` or test real deployment. |
| Direct request blocked yet succeeds via proxy | Inconsistent rewrites/matchers/forwarded headers or ingress bypass. | Test both external and backend routes together. |
| Changing log level via POST returns 403 | Missing CSRF token, missing authority, or endpoint unexposed. | Identify exact cause; never disable CSRF site-wide. |
| Readiness/liveness endpoints missing | Probes not enabled or missing health groups in test env. | Check `management.endpoint.health.probes.enabled` and health groups. |
| App keeps running while management health returns 503 | A health contributor is DOWN while HTTP server stays alive. | Distinguish readiness/liveness and health status mapping. |

## 16. Pre-Production Actuator Security Checklist

1. **Inventory endpoint IDs** enabled/exposed per profile; keep `web.exposure.include` minimal. Specifically avoid wildcards in production.
2. **Separate ports** if administrative network segmentation is needed, without treating a separate port as authentication. Verify bind addresses and real reachability.
3. **Lock down network routes** with firewalls/security groups/NetworkPolicy/ingress; allow only monitoring/operators to reach sensitive ports.
4. **`SecurityFilterChain`** applies to the right web/management context, in the right `@Order`, with `EndpointRequest.toAnyEndpoint()` unshadowed by other chains.
5. **Limited public health** only when needed; audit details, groups, and status payloads. Info/metrics/prometheus are not public by default.
6. **Separate MONITOR and OPS** per least privilege if the system needs both scrapers and operators; consider READ/WRITE endpoints and separate authentication managers.
7. **Do not disable CSRF globally** just to make a POST management operation work; evaluate the actual credential/session model.
8. **Test anonymous and invalid credentials**, not just OPS reading metrics. Verify status/body and zero data leakage.
9. **Test both ports** when the management port is separate: send HTTP to the real management port, not just MockMvc on the main context.
10. **Test base-path/path-mapping** after changes, including reverse proxies and old URLs; avoid fragile hard-coded matchers.
11. **Protect credentials/TLS**: secret stores, rotation, HTTPS/mTLS, avoid logging passwords or putting PII in metric labels.
12. **Assess JMX** as a separate administrative channel, never inferring safety from HTTP exposure.
13. **Runtime observability**: alert on unusual 401/403/404/503 responses on management paths, without auto-opening endpoints to "fix" monitoring.
14. **Re-test after Boot/Security upgrades** and dependency/management topology changes; endpoint mappings, management contexts, and auto-configurations can change.
15. **Review privileges**: ensure the OPS identity cannot accidentally access all business endpoints just because the fallback chain uses `authenticated()`.

## 17. Practical Scenarios: Choosing the Right Topology

### A. Single Internal Machine, Simple Application

- Keep Actuator on the same port as the API if infrastructure does not require separation.
- Expose `health` and only the monitoring endpoints needed.
- Prioritize an `EndpointRequest` Actuator chain ahead of the fallback chain.
- Health may be public inside the internal network with minimal details; metrics require authentication.

### B. Service Using Prometheus/Kubernetes

- Use a dedicated monitoring network service and avoid putting metrics on a public ingress.
- Enable `prometheus` only with a matching Micrometer registry and scrape target.
- Use a read-only `MONITOR` identity/role and network policies; avoid sensitive metric labels.
- Design health/readiness/liveness around orchestrator semantics, considering whether a separate management port reflects application port health.

### C. Enterprise Production with Operators and SSO

- A separate management port helps network segmentation but must be tested on the management child context.
- Operator authentication should use a managed identity provider and MFA at the appropriate access tier; never use a hard-coded in-memory user as in the demo.
- Restrict sensitive operational endpoints by least privilege and audit log-level changes or side-effecting actions.
- Test ingress/proxies, TLS, account revocation, and credential rotation—not just MockMvc.

### D. Only Health Needed for a Load Balancer

- Do not expose `metrics`, `env`, or `configprops` when unnecessary.
- Consider exposing only health status (and probes if needed); hide internal details.
- Even if health is public, combine network restrictions or response minimization per the threat model.

## 18. Key Takeaways

Protecting Actuator is **a coordinated three-layer problem**:

~~~text
Minimum exposure
   +
Controlled management port / network
   +
SecurityFilterChain selects the right endpoints, enforces the right permissions
   =
Better-protected management surface
~~~

`management.server.port` separates traffic **but does not authenticate**. `management.endpoints.web.base-path` changes the URL **but is not security by obscurity**. `management.endpoints.web.exposure.include` decides **which endpoints can appear over HTTP**, while `EndpointRequest` and `SecurityFilterChain` decide **who is allowed to call them**. If the management server runs on a **separate port**, you must test that port directly to confirm the chain and permissions actually take effect.

**Rule of practice:** *Expose only what must be monitored, allow only authorized systems to connect, and always test anonymous and OPS callers on the exact running port and path.*

## References

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — Monitoring and Management over HTTP: https://docs.spring.io/spring-boot/reference/actuator/monitoring.html
- Spring Security Reference — Servlet Architecture and SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Reference — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
