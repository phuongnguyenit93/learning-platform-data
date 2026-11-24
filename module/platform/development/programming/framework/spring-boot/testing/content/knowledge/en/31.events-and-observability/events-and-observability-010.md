# Health Indicators, Actuator Endpoints, and Access Policies in Spring Boot

**Spring Boot Actuator** helps applications answer operational questions: **is the application healthy**, **what conditions drop health to DOWN**, **is the monitoring endpoint present and exposed**, **who is allowed to access the endpoint**, and **how much detail can callers see**. When writing tests, never conflate these distinct concepts:

- **HealthIndicator** is a **data source** contributing status to `HealthEndpoint`. A health indicator is neither a standalone URL nor a security rule.
- **Actuator endpoint** is an operational observation/control point registered by Boot—such as `health`, `info`, or a custom `@Endpoint(id="snapshot")`. It can be surfaced over HTTP/JMX only when permitted and exposed.
- **Access policy** in Boot 3.5 (`management.endpoint.<id>.access`) determines whether an endpoint/operation is allowed to exist at level `none`, `read-only`, or `unrestricted`; it is **not** a user role.
- **Exposure policy** (`management.endpoints.web.exposure.include/exclude`) determines which endpoints are **routed over HTTP**; enabling exposure does not grant access to everyone.
- **HTTP authorization** is enforced by Spring Security `SecurityFilterChain`—for example, public health while `snapshot` requires role `OPS`.
- **Health detail visibility** (`management.endpoint.health.show-details`/`show-components`/`roles`) controls whether health components/metadata are revealed, which is **separate** from permission to call the URL.
- **Health status mapping** translates `UP`/`DOWN`/`OUT_OF_SERVICE` to HTTP status codes. A `503` on health reflects system status, **not necessarily a security 403/401**.

This lesson belongs to **Events and Observability** in **Spring Boot - testing**, focusing on **“Health indicators, Actuator endpoints, and access policies”**. It covers architecture diagrams, decision tables, common mistakes, security hardening, health groups/liveness/readiness, and a Maven project using **Java 17 + Spring Boot 3.5.0 + Spring Security 6.5 + JUnit Jupiter** with `MockMvc` and demo HTTP Basic to verify **20 test methods**: UP/DOWN indicators, aggregate 200/503, public health redaction, OPS details, 401/403, custom endpoints, unexposed endpoints, `access=none` endpoints, keeping application routes protected, and Spring context conditions.

> **Proof boundary:** `MockMvc` loads real Spring MVC/Actuator/Security inside the application context without **opening a real TCP listener**; this suffices to test mappings, filters, status codes, and JSON within the servlet context. When a separate management port, reverse proxy, TLS, or NetworkPolicy is used, add real HTTP integration/E2E tests.

## 1. Observation Layers: Indicator → Health Endpoint → HTTP → Security

```text
QueueState (simulated dependency state)
         |
         v
QueueHealthIndicator implements HealthIndicator
         |
         +--- health() -> Health.up().withDetail(...)
         |             or Health.down().withDetail(...)
         |
         v
HealthContributorRegistry / HealthEndpoint
         |
         +--- StatusAggregator -> overall UP/DOWN/OUT_OF_SERVICE...
         |
         v
HealthEndpointWebExtension  -- HTTP status mapping
         |
         +--- 200 if UP (default)
         +--- 503 if DOWN/OUT_OF_SERVICE (default)
         |
         v
/actuator/health (HTTP route only when exposed)
         |
         +--- Boot endpoint access: none/read-only/unrestricted
         +--- management.endpoints.web.exposure.include/exclude
         +--- SecurityFilterChain: permitAll or require role
         +--- show-details / show-components / health.roles
         |
         v
Client receives { "status": "UP" } (public)
             or { "status": "UP", "components": {...} } (OPS)
```

**Do not invert causality:** a `HealthIndicator` returning `DOWN` does not mean Spring Security blocked the endpoint. When security allows and the endpoint mapping is active, HTTP health normally returns **503 Service Unavailable** with status `DOWN`. Conversely, a `401`/`403` response happens before the health operation executes and does not prove the system is DOWN.

### 1.1. HealthIndicator Is an Interface, Not a Controller

Spring Boot provides:

```java
public interface HealthIndicator extends HealthContributor {
    Health health();
}
```

This is a simplified signature; real implementations inherit the default `getHealth(boolean)` method. An indicator can return:

```java
return Health.up()
        .withDetail("queueDepth", 0)
        .build();
```

Or:

```java
return Health.down()
        .withDetail("reason", "dependency-offline")
        .build();
```

When registered as a Spring bean named `queueHealthIndicator`, Boot typically derives the contribution name **`queue`** by stripping the `HealthIndicator` suffix. Thus the aggregate JSON structure includes `components.queue` when details/components are authorized. To verify the contributor name properly, assert `components.queue` instead of assuming the Java class name automatically becomes the URL `/actuator/QueueHealthIndicator`.

### 1.2. What About HealthContributor and ReactiveHealthIndicator?

- `HealthContributor` is the abstraction for health contributors; a contributor can be a single indicator or a composite.
- `CompositeHealthContributor` aggregates multiple child contributors, e.g., health across multiple datasources/tenants.
- `ReactiveHealthIndicator` returns a reactive outcome for reactive applications; Spring Boot supplies matching reactive health endpoints/registries.
- If integrating slow APIs, indicators must enforce timeouts and failure policies. Blocking health checks can turn the health endpoint itself into a source of load and outages.

**Health is not a secret exception dump**: never put user tokens, passwords, JDBC connection strings, sensitive internal IPs, or detailed stack traces into `withDetail(...)`, especially when `show-details=always` is configured.

## 2. Three Easily Confused Policy Layers: Access, Exposure, and Authorization

Spring Boot 3.5 separates these properties:

| Layer | Example | Question Answered | What It Does Not Mean |
|---|---|---|---|
| Endpoint access | `management.endpoint.snapshot.access=read-only` | Is the endpoint/operation **permitted** in the app? | Does not specify user roles |
| Max access cap | `management.endpoints.access.max-permitted=read-only` | Is there a stricter global ceiling? | Not HTTP Basic/auth tokens |
| Default access | `management.endpoints.access.default=none` | Which non-opted-in endpoints are excluded? | Cannot be re-opened via `permitAll` once excluded |
| Web exposure | `management.endpoints.web.exposure.include=health,snapshot` | Which endpoints get HTTP mappings? | Does not automatically allow anonymous access |
| Web exclude | `management.endpoints.web.exposure.exclude=env` | Which endpoints are stripped from HTTP regardless of include? | Does not automatically disable JMX access |
| Authorization | `EndpointRequest.to("health").permitAll()` | Which callers pass `SecurityFilterChain`? | Does not materialize an `access=none` endpoint |
| Health details | `show-details=when-authorized`, `roles=OPS` | Which callers see indicator details? | Differs from permission to hit the health URL |
| HTTP status | `DOWN -> 503` | How is health status mapped? | Not a 403 security denial |

### 2.1. Disabled Endpoints Differ from Unexposed Endpoints

Given:

```properties
management.endpoints.access.default=none
management.endpoint.health.access=read-only
management.endpoint.snapshot.access=read-only
management.endpoints.web.exposure.include=health,snapshot
```

Only `health` and `snapshot` are opted-in and exposed over HTTP. In Spring Boot 3.5, `access=none` prevents an endpoint from having **any active operations in the application context** under Actuator's mechanism; granting role OPS cannot make it appear over HTTP. Simply adding it to `include` is not enough when access policy disables it.

Conversely, an endpoint can remain active internally/over JMX yet **not be exposed over HTTP**. For example, `info` is absent from `include`, so requesting `GET /actuator/info` with full credentials still finds **no HTTP mapping**, typically resulting in **404** once security permits the request through. To verify the true cause of a 404, check access, exposure, and context paths rather than immediately blaming the URL.

### 2.2. `read-only` vs. `unrestricted`

Boot 3.5:
- `none`: disables the endpoint.
- `read-only`: allows only **read operations**; for `@Endpoint`, these are `@ReadOperation` methods.
- `unrestricted`: allows all operations supported by the endpoint (read/write/delete), though **Spring Security/CSRF/network policies can still block HTTP requests**.
- `management.endpoints.access.max-permitted` enforces an app-wide ceiling and **overrides** default/individual access levels. If capped at `read-only`, even an endpoint explicitly set to `unrestricted` cannot run writes.

**Do not infer “read-only” from ordinary HTTP GET business controllers**. With Actuator annotations, operation types come from `@ReadOperation`, `@WriteOperation`, and `@DeleteOperation` (mapping by convention to HTTP GET, POST, DELETE, while some controller/servlet endpoint types follow separate read criteria). If an endpoint declares no write operation, you cannot meaningfully test “writes blocked” by invoking an undeclared operation.

### 2.3. Web Exposure Does Not Replace Spring Security

By default, only `health` is exposed over HTTP/JMX. Endpoints like `env`, `beans`, `configprops`, `loggers`, `heapdump`, `threaddump`, and `mappings` can expose sensitive metadata or mutation capabilities. **Never set**:

```properties
management.endpoints.web.exposure.include=*
```

on an internet-facing service simply for debugging convenience. When more exposure is needed, use a strict allowlist and verify authentication, roles, firewalls/ingress, TLS, secret sanitization, and auditing. Even default JSON value sanitization does not justify exposing your entire internal app structure publicly.

### 2.4. Custom SecurityFilterChain Causes Boot's Auto-Security to Back Off

When Spring Security is on the classpath and **no** user-defined `SecurityFilterChain` exists, Boot normally protects Actuator endpoints other than health automatically. **However, declaring any custom `SecurityFilterChain` causes that auto-security policy to back off**. At that point, **you are responsible for protecting both Actuator and application routes**.

A real-world mistake:

```java
@Bean
SecurityFilterChain unsafe(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a
            .anyRequest().permitAll());
    return http.build();
}
```

That snippet accidentally **opens every exposed endpoint** alongside business routes. Never put that in production. In the runnable example, we order rules explicitly:
1. `health` public;
2. all other Actuator endpoints require `ROLE_OPS`;
3. non-Actuator application paths require an authenticated user.

Spring Boot provides `EndpointRequest.to("health")` and `EndpointRequest.toAnyEndpoint()` to match **against the real endpoint IDs and management base path**, avoiding fragile hardcoded `/actuator/**` patterns when base paths change. `EndpointRequest.to("health")` also matches health **subpaths**. With multiple `@Order`-annotated `SecurityFilterChain` beans, verify which chain matches first; `securityMatcher` selects the chain, while `requestMatcher` enforces authorization inside it.

## 3. Health Status and HTTP Responses: Two-Layer Testing

Common Health API statuses:

| Status | Reference Meaning | Default HTTP |
|---|---|---|
| `UP` | Contributor or aggregate considered healthy | **200** |
| `DOWN` | Unhealthy | **503** |
| `OUT_OF_SERVICE` | Not ready to serve | **503** |
| `UNKNOWN` | Indeterminate | Typically **200** unless mapped otherwise |

Boot includes `StatusAggregator` and `HttpCodeStatusMapper`. Aggregation takes all contributors and picks the overall status by precedence; by default `DOWN`/`OUT_OF_SERVICE` outrank `UP`. Configuration notes:
- `management.endpoint.health.status.order` customizes precedence for custom statuses.
- `management.endpoint.health.status.http-mapping.*` customizes HTTP status codes.
- When declaring **custom HTTP mappings**, be careful: default mappings for `DOWN` and `OUT_OF_SERVICE` may **no longer apply automatically**; to keep 503, re-declare both alongside your custom status.

Example:

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.fatal=500
```

This is a **policy example**, not placed in the runnable demo. The tests' `DOWN -> 503` expectation relies on **default HTTP mappings**, not custom status codes.

**Never test only JSON status:** When an indicator returns `DOWN`, the body might say `"status":"DOWN"` while a misconfigured HTTP mapping returns 200, tricking load balancers/kubelets into treating it as healthy. Tests should verify **both HTTP status code and body**. Likewise, never assume every HTTP 503 means Health DOWN: reverse proxies or gateways can return 503 before the request reaches Actuator.

## 4. Permission to See Details vs. Permission to Call the URL

The health endpoint can answer anonymous callers if policy allows, while hiding details:

```http
GET /actuator/health HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
```

For callers holding an authorized health role:

```json
{
  "status": "UP",
  "components": {
    "queue": {
      "status": "UP",
      "details": {
        "mode": "ready"
      }
    }
  }
}
```

This is an **abbreviated illustrative shape** (real aggregates may include other contributors like `diskSpace`/`ping`). `Content-Type` headers can vary across content negotiation or Actuator API versions; avoid hardcoding vendor media types unless part of a strict contract.

### 4.1. Configuring show-details and show-components

```properties
management.endpoint.health.show-details=when-authorized
management.endpoint.health.show-components=when-authorized
management.endpoint.health.roles=OPS
```

Valid values for `show-details` and `show-components`:
- `never`: never displayed.
- `when-authorized`: displayed only to authenticated callers holding a matching role.
- `always`: displayed to every caller **permitted to access the endpoint**.

If `roles` is omitted, any authenticated user can qualify as authorized when `when-authorized` is set. Therefore, in apps with multiple user tiers (customer, staff, operator), **specify roles explicitly** so ordinary logged-in users cannot inspect infrastructure topology.

**Two conditions must both hold for OPS to see details:**
1. HTTP security permits the caller to reach `/actuator/health` (`permitAll` in the demo).
2. Health detail authorization sees the caller has `OPS`, matching `management.endpoint.health.roles=OPS`.

With `show-details=always`, unauthenticated callers see dependency structures/metadata whenever health is public. Avoid exposing internal hostnames, queue names, disk paths, or raw connection errors to the public internet.

### 4.2. Public Status with Redacted Components

In the demo:
- Anonymous `GET /actuator/health` gets **200** with `{"status":"UP"}`, no `components`.
- User with role `USER` gets **200**, still no `components`.
- User with role `OPS` gets **200** and sees `components.queue.details.mode`.
- When the queue goes down, anonymous gets **503** with `"status":"DOWN"`, still hiding details.
- OPS gets **503**, with `components.queue.status=DOWN` and permitted `reason/mode` details.

**This separation is critical:** public health status for load balancers/kubelets need not expose internal details. A test asserting only `status().isOk()` does not prove **data isn't leaking**; also assert `jsonPath("$.components").doesNotExist()`.

## 5. Health Groups, Liveness/Readiness, and Management Port

The health endpoint can group indicators by operational purpose. For instance, readiness can depend on DB/queues while liveness must not depend on external services.

### 5.1. Liveness and Readiness Differ

- **Liveness**: is the process still internally healthy enough to keep running? If it fails, the orchestrator may **restart** the pod.
- **Readiness**: is the instance **ready to accept traffic**? If it fails, the orchestrator stops routing traffic temporarily.
- **Startup probe**: protects slow-starting apps from being killed prematurely by liveness checks.

When a database or external API goes DOWN, usually **do not** include it in liveness: mass-restarting pods cannot fix an external dependency and causes cascading failures. Depending on the system, it may affect readiness; account for partial functionality and degraded modes.

On Kubernetes, Boot enables `livenessState` and `readinessState` health indicators, accessible at:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

In **non-Kubernetes** environments, enable explicitly:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

With additional paths enabled, Boot exposes `/livez` and `/readyz` **on the main application server port**, allowing probes to exercise the app's primary connector. **These reference settings are omitted from the runnable demo's properties** to avoid changing the contributor/path set under assertion.

### 5.2. Management Port Separate from Application Port

`management.server.port=9091` opens a separate management web context/port. In that setup:
- `MockMvc` on the main servlet context **does not verify the full HTTP path of a separate management port**.
- `server.port` differs from `management.server.port`; network ingress, TLS, and firewall rules may differ.
- Kubelet probes hitting the separate management port can report healthy even while the **main app port rejects requests**.
- Test with `@SpringBootTest(webEnvironment=RANDOM_PORT)`, resolve the respective ports, and make real HTTP calls to each port alongside security/cookie/mTLS requirements.
- If kubelet must detect failures on the main connector, consider additional paths on the main port per Boot docs.

### 5.3. Creating Custom Health Groups

Example:

```properties
management.endpoint.health.group.queueOnly.include=queue
management.endpoint.health.group.queueOnly.show-details=when-authorized
management.endpoint.health.group.queueOnly.roles=OPS
```

This is a conceptual snippet; group names and contributor names must match the registry, and should be verified against your Spring Boot version/binding. Boot validates group membership by default, so a group referencing a nonexistent indicator can cause **context startup failure**; check `management.endpoint.health.validate-group-membership` when encountering this. Ensure custom groups never leak unintended details, and avoid wiring external DB/queues into liveness groups.

## 6. Runnable Java 17 + Spring Boot 3.5 Project: HealthIndicator, @Endpoint, and Security

The project includes:
1. A `QueueState` simulating a dependency, initially healthy and deterministically toggleable to DOWN.
2. A `QueueHealthIndicator` returning `UP`/`DOWN` with details, under contributor ID `queue`.
3. A custom `@Endpoint(id="snapshot")` with a `@ReadOperation` returning secret-free JSON.
4. A `SecurityFilterChain` keeping health public, requiring `OPS` for all other Actuator endpoints, and requiring authentication on business routes.
5. In-memory demo users strictly for learning; production requires real credential stores/OIDC/mTLS.
6. Actuator properties for access, exposure, and detail visibility.
7. Three test classes: **3 pure unit tests**, **15 MockMvc integration tests**, and **2 access-policy integration tests**—totaling **20 `@Test` methods**.

### 6.1. Directory Tree

```text
actuator-health-security/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/actuatordemo/
    │   │   ├── ActuatorDemoApplication.java
    │   │   ├── QueueState.java
    │   │   ├── QueueHealthIndicator.java
    │   │   ├── OpsSnapshotEndpoint.java
    │   │   ├── ActuatorSecurityConfig.java
    │   │   └── PrivateController.java
    │   └── resources/
    │       └── application.properties
    └── test/java/com/example/actuatordemo/
        ├── QueueHealthIndicatorTest.java
        ├── ActuatorAccessTest.java
        └── ActuatorDisabledTest.java
```

No external services, database, Redis, Kafka, or Testcontainers are needed. All data is synthetic demo state. When adapting `HealthIndicator` for production, replace `QueueState` with real health checks bounded by timeouts, caching, and bulkheads.

### 6.2. Maven POM

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>actuator-health-security</artifactId>
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

The Boot 3.5 BOM aligns Spring MVC/Security/Actuator/Mockito/JUnit versions. `spring-security-test` supplies `httpBasic(...)` for `MockMvc`. Use `org.springframework.boot.actuate.*` imports matching Boot 3.5; never copy Boot 4's reorganized package paths into this project.

### 6.3. Main Application

File **`src/main/java/com/example/actuatordemo/ActuatorDemoApplication.java`**:

```java
package com.example.actuatordemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorDemoApplication.class, args);
    }
}
```

All components share this package or subpackages so Spring discovers the HealthIndicator, custom endpoint, security config, and controller. JUnit does not invoke `main`; `@SpringBootTest` initializes the context.

### 6.4. Simulated Dependency State

File **`src/main/java/com/example/actuatordemo/QueueState.java`**:

```java
package com.example.actuatordemo;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class QueueState {

    private final AtomicBoolean available =
            new AtomicBoolean(true);

    public boolean isAvailable() {
        return available.get();
    }

    public void setAvailable(boolean value) {
        available.set(value);
    }
}
```

This is a test-friendly fake state: toggling `available` requires no sleeps or live connections. It is **not a real production health check**. Tests sharing this singleton state assume JUnit's **default sequential execution**; if enabling parallel tests or sharing cached contexts across classes, isolate state or use per-test contexts/unique fixtures to avoid races.

### 6.5. Custom HealthIndicator

File **`src/main/java/com/example/actuatordemo/QueueHealthIndicator.java`**:

```java
package com.example.actuatordemo;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("queueHealthIndicator")
public class QueueHealthIndicator implements HealthIndicator {

    private final QueueState state;

    public QueueHealthIndicator(QueueState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isAvailable()) {
            return Health.up()
                    .withDetail("mode", "ready")
                    .build();
        }
        return Health.down()
                .withDetail("mode", "offline")
                .build();
    }
}
```

Actuator registers this contributor in aggregate health under ID `queue` by bean naming convention. Keep `mode` as a **non-sensitive** simulated value; never expose internal hostnames or credentials in details. For real dependencies, map timeouts/network exceptions to `DOWN` per policy, ensuring no health indicator blocks indefinitely and stalls probes.

### 6.6. Custom Actuator Endpoint with Read Operation

File **`src/main/java/com/example/actuatordemo/OpsSnapshotEndpoint.java`**:

```java
package com.example.actuatordemo;

import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "snapshot")
public class OpsSnapshotEndpoint {

    @ReadOperation
    public Map<String, String> snapshot() {
        return Map.of(
                "kind", "operations",
                "mode", "demo");
    }
}
```

`@Endpoint(id="snapshot")` assigns the endpoint ID, and `@ReadOperation` maps to `GET /actuator/snapshot` when both **access and exposure** permit it. No `@RestController` or `@GetMapping` is needed; Actuator generates mappings from operation annotations. This demo defines only a **read operation** with no `@WriteOperation`. To test write policies properly, add a write operation in a dedicated test fixture, test `access=read-only` vs. `unrestricted`, and handle CSRF/security accordingly.

### 6.7. Spring Security Configuration

File **`src/main/java/com/example/actuatordemo/ActuatorSecurityConfig.java`**:

```java
package com.example.actuatordemo;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                // Health is public, including health subpaths.
                .requestMatchers(
                        EndpointRequest.to("health")).permitAll()

                // Every other Actuator endpoint requires role OPS.
                .requestMatchers(
                        EndpointRequest.toAnyEndpoint()).hasRole("OPS")

                // Do not accidentally leave business endpoints open.
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService demoUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("operator")
                        .password("{noop}ops-password")
                        .roles("OPS")
                        .build(),
                User.withUsername("reader")
                        .password("{noop}reader-password")
                        .roles("USER")
                        .build());
    }
}
```

**Strictly for learning/testing:** hardcoded `{noop}` passwords in source are completely **unsafe for production**. In real deployments, use strong password encoders or OAuth2/OIDC/mTLS, secret managers, and least privilege. Never copy demo credentials into real systems.

Matcher order is critical: health is permitted first, then all remaining Actuator endpoints require `ROLE_OPS`, and other business routes require authentication. Because we define a custom `SecurityFilterChain`, **Boot's actuator security auto-config backs off**; this class is responsible for securing both Actuator and the application.

**Never disable CSRF globally.** The lesson uses only GET/read operations, so default CSRF stays intact. When adding `@WriteOperation` via POST/DELETE called by browser cookies/sessions, verify CSRF tokens. A POST returning 403 might stem from a **missing CSRF token** rather than missing role OPS; test both conditions separately. For machine-only non-browser clients, any CSRF exemption must follow a real threat model rather than convenience.

### 6.8. A Business API to Verify Default Deny

File **`src/main/java/com/example/actuatordemo/PrivateController.java`**:

```java
package com.example.actuatordemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {

    @GetMapping("/api/private/ping")
    public Map<String, String> ping() {
        return Map.of("reply", "pong");
    }
}
```

This endpoint is **not an Actuator endpoint**. Adding a custom `SecurityFilterChain` must not accidentally open `/api/private/ping` to anonymous users; tests verify **401 without credentials** and **200 when logged in as USER**. In production, enforce granular authorization per route/data rather than `authenticated()` alone as in the demo.

### 6.9. Actuator Properties

File **`src/main/resources/application.properties`**:

```properties
# By default, DO NOT grant access to Actuator endpoints.
management.endpoints.access.default=none

# Opt in only the 2 needed endpoints, allowing read operations only.
management.endpoint.health.access=read-only
management.endpoint.snapshot.access=read-only

# Expose over HTTP via strict allowlist. Do not expose info/env/beans.
management.endpoints.web.exposure.include=health,snapshot

# Public sees status only; role OPS sees components and details.
management.endpoint.health.show-details=when-authorized
management.endpoint.health.show-components=when-authorized
management.endpoint.health.roles=OPS

# Keep management endpoints in the same servlet context/port for MockMvc.
# Do not set management.server.port in this example.
```

In Boot 3.5, `access.default=none` prevents other endpoints from being enabled in-context under Actuator, while `include` controls which endpoints get HTTP routes. This config **intentionally omits `info`**, testing that OPS still gets **404** on `/actuator/info` despite holding a privileged role.

**Granting role OPS does not make health details public:** the health URL is public via SecurityFilterChain `permitAll`, while `components` visibility depends on `show-details`/`show-components` and `health.roles`. This distinction sits at the heart of policy testing.

### 6.10. Pure Unit Tests for HealthIndicator: 3 Methods

File **`src/test/java/com/example/actuatordemo/QueueHealthIndicatorTest.java`**:

```java
package com.example.actuatordemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;

import static org.assertj.core.api.Assertions.assertThat;

class QueueHealthIndicatorTest {

    @Test
    void startsHealthyWithNonSensitiveDetail() {
        QueueState state = new QueueState();
        QueueHealthIndicator indicator =
                new QueueHealthIndicator(state);

        Health health = indicator.health();

        assertThat(health.getStatus()).isEqualTo(Status.UP);
        assertThat(health.getDetails())
                .containsEntry("mode", "ready");
    }

    @Test
    void offlineSignalChangesHealthToDown() {
        QueueState state = new QueueState();
        state.setAvailable(false);

        Health health =
                new QueueHealthIndicator(state).health();

        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
        assertThat(health.getDetails())
                .containsEntry("mode", "offline");
    }

    @Test
    void recoveredStateReturnsUpAgain() {
        QueueState state = new QueueState();
        QueueHealthIndicator indicator =
                new QueueHealthIndicator(state);

        state.setAvailable(false);
        assertThat(indicator.health().getStatus())
                .isEqualTo(Status.DOWN);

        state.setAvailable(true);
        assertThat(indicator.health().getStatus())
                .isEqualTo(Status.UP);
    }
}
```

These unit tests verify **indicator logic** without a Spring context. They **do not** prove the bean is picked up by the Actuator registry, HTTP mappings, or Spring Security policies. Those belong to the integration tests next.

### 6.11. MockMvc Integration Tests: 15 Methods

File **`src/test/java/com/example/actuatordemo/ActuatorAccessTest.java`**:

```java
package com.example.actuatordemo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ActuatorAccessTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private QueueState queueState;

    @Autowired
    private QueueHealthIndicator queueIndicator;

    @Autowired
    private HealthEndpoint healthEndpoint;

    @BeforeEach
    void restoreQueue() {
        queueState.setAvailable(true);
    }

    @Test
    void indicatorBeanIsRegisteredAndInitiallyUp() {
        assertThat(queueIndicator.health().getStatus())
                .isEqualTo(Status.UP);
    }

    @Test
    void aggregateHealthReflectsOfflineContributor() {
        queueState.setAvailable(false);

        assertThat(healthEndpoint.health().getStatus())
                .isEqualTo(Status.DOWN);
    }

    @Test
    void anonymousMayReadStatusWithoutComponents() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void ordinaryAuthenticatedUserStillCannotSeeDetails()
            throws Exception {

        mvc.perform(get("/actuator/health")
                .with(httpBasic("reader", "reader-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void operatorSeesQueueHealthStatusAndDetails()
            throws Exception {

        mvc.perform(get("/actuator/health")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components.queue.status")
                        .value("UP"))
                .andExpect(jsonPath("$.components.queue.details.mode")
                        .value("ready"));
    }

    @Test
    void anonymousGets503ButNoSensitiveDetailsWhenDown()
            throws Exception {

        queueState.setAvailable(false);

        mvc.perform(get("/actuator/health"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void operatorSeesDownContributorDetailsWith503()
            throws Exception {

        queueState.setAvailable(false);

        mvc.perform(get("/actuator/health")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"))
                .andExpect(jsonPath("$.components.queue.status")
                        .value("DOWN"))
                .andExpect(jsonPath("$.components.queue.details.mode")
                        .value("offline"));
    }

    @Test
    void anonymousCannotReadCustomActuatorEndpoint()
            throws Exception {

        mvc.perform(get("/actuator/snapshot"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void readerWithoutOpsRoleGets403OnSnapshot()
            throws Exception {

        mvc.perform(get("/actuator/snapshot")
                .with(httpBasic("reader", "reader-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void operatorGetsCustomActuatorEndpointJson()
            throws Exception {

        mvc.perform(get("/actuator/snapshot")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.kind")
                        .value("operations"))
                .andExpect(jsonPath("$.mode").value("demo"));
    }

    @Test
    void unexposedInfoStillReturns404ForOperator()
            throws Exception {

        mvc.perform(get("/actuator/info")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isNotFound());
    }

    @Test
    void nonActuatorPrivateApiStillRequiresLogin()
            throws Exception {

        mvc.perform(get("/api/private/ping"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryReaderCanCallAuthenticatedBusinessApi()
            throws Exception {

        mvc.perform(get("/api/private/ping")
                .with(httpBasic("reader", "reader-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reply").value("pong"));
    }

    @Test
    void healthSubpathIsAlsoAllowedForOps()
            throws Exception {

        mvc.perform(get("/actuator/health/queue")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.details.mode")
                        .value("ready"));
    }

    @Test
    void anonymousCannotAccessActuatorDiscoveryLinks()
            throws Exception {

        mvc.perform(get("/actuator"))
                .andExpect(status().isUnauthorized());
    }
}
```

These **15 test methods** verify every layer:

- `HealthIndicator` bean exists and overall health updates to DOWN.
- `/actuator/health` is public, yet anonymous and USER see no `components`.
- OPS sees the `queue` contributor and details; roles are authenticated via **real HTTP Basic headers through MockMvc security filters**.
- When `QueueState` is DOWN, HTTP health returns **503**, not 200, while visibility policy still holds.
- Custom `@Endpoint(id="snapshot")` returns 401 to anonymous, 403 to USER, and 200 + JSON to OPS.
- Unexposed `/actuator/info` still returns 404 to OPS (having the role does not grant a URL).
- Non-Actuator business routes still require authentication; the custom `SecurityFilterChain` does not open the whole system.
- `EndpointRequest.to("health")` matches the `health/queue` subpath; `EndpointRequest.toAnyEndpoint()` covers discovery links at `/actuator`.

They do not test TCP ports or reverse proxies. Thanks to `@BeforeEach`, health is reset to UP before each case so a DOWN test does not pollute subsequent tests. JUnit runs sequentially by default; keep it sequential or isolate singleton state if parallelizing.

### 6.12. Testing `access=none` in a Separate Context: 2 Methods

File **`src/test/java/com/example/actuatordemo/ActuatorDisabledTest.java`**:

```java
package com.example.actuatordemo;

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

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = "management.endpoint.snapshot.access=none")
@AutoConfigureMockMvc
class ActuatorDisabledTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void operatorCannotRecoverDisabledEndpointWithRole()
            throws Exception {

        mvc.perform(get("/actuator/snapshot")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isNotFound());
    }

    @Test
    void healthRemainsAvailableWhenSnapshotIsDisabled()
            throws Exception {

        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
```

`properties = "management.endpoint.snapshot.access=none"` creates a **test context with a property override** for this class; main `application.properties` keeps `snapshot.access=read-only`. Separate Boot context configurations verify the difference:
- With `access=read-only` + exposure + role OPS → snapshot endpoint **200**.
- With `access=none` + `snapshot` still listed in exposure + role OPS → **404**, because the endpoint operation is unavailable; a security role cannot “re-enable” an excluded endpoint.
- Health stays **200** due to its own access/exposure settings.

Do not assume every 404 means `access=none`: 404 can also come from unexposed endpoints, wrong base path, wrong management port, missing controller mapping, or reverse proxies. This test isolates one property variable to prove the cause.

### 6.13. Run Commands and Expected Results

Requires JDK 17+, Maven. From the directory containing `pom.xml`:

```bash
mvn test
```

Run individual classes:

```bash
mvn -Dtest=QueueHealthIndicatorTest test
mvn -Dtest=ActuatorAccessTest test
mvn -Dtest=ActuatorDisabledTest test
```

If using Maven Wrapper: `./mvnw test` (Linux/macOS) or `mvnw.cmd test` (Windows).

**Expected counts**: 3 pure unit + 15 MockMvc integration + 2 disabled-policy integration = **20 JUnit `@Test` methods**. Data is synthetic, requiring no Docker/Internet, with no invariant business stdout to match. All assertions are expected to PASS on Boot 3.5.0 with the security/test setup described above; **this is a source-code expectation, not a claim that Maven ran during authoring**. If your real project differs in dependencies, Boot patches, or security config, run in CI to verify.

## 7. Access Matrix: 200/401/403/404/503 Have Distinct Meanings

| Request / Role | Access/Exposure | Health/Endpoint State | Expected |
|---|---|---|---|
| Anonymous GET `/actuator/health` | health read-only + exposed + permitAll | UP | **200**, `status` only |
| Reader USER GET `/actuator/health` | same as above | UP | **200**, no details |
| Operator OPS GET `/actuator/health` | same as above | UP | **200**, includes queue details |
| Anonymous GET `/actuator/health` | same as above | DOWN | **503**, `status` only |
| Operator OPS GET `/actuator/health` | same as above | DOWN | **503**, queue DOWN/details |
| Anonymous GET `/actuator/snapshot` | snapshot read-only + exposed | available | **401** (HTTP Basic entry point) |
| Reader USER GET `/actuator/snapshot` | same as above | available | **403** (missing OPS role) |
| Operator OPS GET `/actuator/snapshot` | same as above | available | **200**, JSON |
| Operator OPS GET `/actuator/info` | info unexposed | no route | **404** |
| Operator OPS GET `/actuator/snapshot` with `access=none` | snapshot disabled | no route | **404** |
| Anonymous GET `/api/private/ping` | not Actuator | authenticated required | **401** |
| Reader USER GET `/api/private/ping` | not Actuator | authenticated | **200** |

**Distinguish status codes at the right layer:**

- `401 Unauthorized`: lacking valid authentication in **this HTTP Basic demo**. Form login may redirect `302`; do not assume every app returns 401.
- `403 Forbidden`: authenticated yet lacking authorization, or an unsafe request missing CSRF. 403 **does not mean health DOWN**.
- `404 Not Found`: request has no HTTP mapping (such as unexposed or `access=none`), though it can also simply mean a wrong path; some configs hide endpoints before returning 404.
- `503 Service Unavailable`: default mapping for `Health DOWN/OUT_OF_SERVICE`; does not substitute for OPS role checks, and can also originate from a reverse proxy/infra if the request never reached the app.
- `200 OK`: endpoint responded successfully, yet **does not prove all downstream dependencies are healthy** if an indicator omits them, isn't registered, is excluded from the health group, or fails to check real errors.

**Never replace all assertions with `status().isOk()`:** health tests must assert right/wrong details and status codes, security tests must assert exact roles, and endpoint availability tests must verify whether mappings actually exist.

## 8. Pitfalls When Reading Endpoint Access and Exposure

### 8.1. `management.endpoint.health.access=read-only` Is Not `permitAll`

This property only means health's read operation is enabled; it **does not grant public HTTP access**. If Spring Security requires login for health, anonymous callers still get 401/302. Conversely, `permitAll` cannot resurrect an endpoint set to `access=none`.

### 8.2. `management.endpoints.web.exposure.include=health` Does Not Allow Other Endpoints

An operator with a valid token still cannot call `/actuator/env` if `env` is unexposed. If more endpoints must open, update config deliberately and test authorization/sanitization rather than enabling a wildcard. If JMX is enabled, JMX exposure can differ from HTTP; check both technologies per threat model.

### 8.3. Health Details with Overly Broad Roles

Setting `show-details=when-authorized` **without setting `management.endpoint.health.roles`** usually lets every authenticated user see details. In apps with normal end-user logins, that exposes topology and exception details. Restrict to OPS and keep public payloads minimal.

### 8.4. Configuring `show-components=always` with `show-details=never`

You can expose contributor names/statuses while hiding details. Distinguish:
- `show-components` controls **contributor structure**.
- `show-details` controls **metadata inside each contributor**.
To avoid leaking topology, do not set `show-components=always`. The demo sets both to `when-authorized` and asserts anonymous callers **receive no `components`**, while OPS sees both components and details.

### 8.5. Custom Status Mappings Turning DOWN into 200

When configuring HTTP mappings for a custom status, Boot may stop applying defaults for `DOWN`/`OUT_OF_SERVICE`. Re-declare them explicitly if you still expect 503. A test checking only `status=DOWN` without checking HTTP status misses major rollout/probe bugs.

### 8.6. Indicator Misnamed or Not Registered

`QueueHealthIndicator` can pass when manually instantiated via `new` and calling `health()`, yet still not be registered by Spring. Integration tests must check `HealthEndpoint` overall status when state flips and (when authorized) assert `components.queue` appears. If a custom bean is skipped by component scan, Spring's default health remains `UP` and a status-200-only test passes falsely.

### 8.7. Health Checks Causing Load Themselves

A `HealthIndicator` making synchronous external API/DB calls without timeouts can:
- time out kubelet probes even when main app traffic is fine;
- pile extra load onto a failing dependency;
- restart all pods when external dependencies are checked in liveness;
- trigger cascading failures.

Enforce short timeouts and low retries, use cached state/backpressure where appropriate, separate readiness from liveness, and log slow checks without leaking secrets. Boot provides `management.endpoint.health.logging.slow-indicator-threshold` to warn on slow health indicators.

### 8.8. Custom Security Chain Matching Only Actuator, Leaving the Rest Exposed

A security config matching only `EndpointRequest.toAnyEndpoint()` can leave **application routes without Boot's default security** because the custom chain disables Boot's auto-config. With multiple chains, define a **second chain for the app** with proper `@Order`, and test that anonymous business URLs are blocked. The demo avoids this by using **one chain with an `anyRequest().authenticated()` fallback**.

### 8.9. Public Health Does Not Mean Public Secrets

Even when public status shows only UP/DOWN, the path can be abused to probe availability or generate traffic. Apply network rate limiting / load balancer policies, keep internal details out of responses, and monitor for abuse. In internal-only environments, consider exposing health only on a management VLAN/sidecar, while testing on the real port.

## 9. Production Testing: Going Beyond MockMvc

The demo verifies several layers **inside the JVM**. Once infrastructure is added, also test:

| Infrastructure | Risk | Appropriate Test |
|---|---|---|
| Separate `management.server.port` | Security/network config differs from app port | Real HTTP tests on both main and management ports |
| Ingress/reverse proxy | Path rewrites, auth bypass, missing forwarded headers | E2E through a deployment-like proxy |
| Kubernetes readiness/liveness | Wrong probe path/port or wrong group | Integration with probes + deployment manifests |
| TLS/mTLS | Trust/CA/certificates, client authentication | HTTPS integration with test certificates |
| OAuth2/OIDC | JWT roles/scopes differ from mock BASIC users | Security integration with test JWT/auth server |
| Database/Redis/Kafka | Real `HealthContributor` DOWN and readiness | Isolated Testcontainers/environments |
| Parallel tests | Shared singleton `QueueState`/health mocks collide | Per-test state or disable parallel execution |
| Separate management context | `MockMvc` does not mirror child management server | `RANDOM_PORT` + HTTP calls to management port |
| Metrics/observations | Health status doesn't ensure counters/traces work | Separate `MeterRegistry`/`ObservationRegistry` tests |
| Slow dependencies | Health probes time out | Fault injection + time budget/slow-indicator threshold |
| High scale | Probe frequency overloads app | Load tests and rate-limiting policies |

### 9.1. Do Not Use MockMvc Tests as Network ACL Proof

`MockMvc` exercises Spring MVC request handlers and security filters without opening real sockets. `MockMvc GET /actuator/snapshot` returning 403 proves the filter chain **in that context** blocks the user. It **does not prove** firewalls/ingress block the public Internet or that a separate management port is properly restricted. If endpoints must be private-network-only, write dedicated deployment/infrastructure tests.

### 9.2. If the App Uses WebFlux

Reactive apps use `ReactiveHealthIndicator`, `WebTestClient`, and `SecurityWebFilterChain`, with reactive `EndpointRequest` matchers in a different package. Never copy servlet `HttpSecurity`/`MockMvc` examples verbatim into WebFlux. Access/exposure/health detail concepts still apply, yet runtime and security APIs differ.

### 9.3. If Testing the Prometheus Endpoint

`/actuator/prometheus` requires `micrometer-registry-prometheus` on the classpath plus matching **access, exposure, and security**. `MetricsEndpoint` and `prometheus` are not the same ID/operation. A `health` endpoint returning `UP` does not guarantee Prometheus metrics scrape properly; test each endpoint according to its operational role, and never expose scrape endpoints carelessly to the Internet.

## 10. Recommended Test Matrix for Real Services

| Test | Input | Evidence |
|---|---|---|
| Indicator unit UP | Dependency ready | `Health.status=UP`, safe details |
| Indicator unit DOWN | Dependency offline | `Health.status=DOWN` |
| Aggregate health DOWN | Registered contributor offline | Overall `HealthEndpoint.health().getStatus()=DOWN` |
| HTTP public healthy | Anonymous GET `/actuator/health` | 200, status UP, no components/details |
| HTTP public unhealthy | Anonymous GET `/actuator/health` | 503, status DOWN, no leaked details |
| HTTP OPS healthy | Authenticated OPS | 200, `components.queue` and exact details |
| HTTP USER healthy | Authenticated USER | 200, still no components |
| Custom endpoint no auth | Anonymous GET `/actuator/snapshot` | 401/redirect per entry point |
| Custom endpoint wrong role | USER | 403 |
| Custom endpoint right role | OPS | 200, valid JSON |
| Unexposed endpoint | OPS GET `/actuator/info` | 404 |
| `access=none` | OPS GET `/actuator/snapshot` with property override | 404 |
| Non-Actuator app route | Anonymous GET `/api/private/ping` | 401 |
| Health subpath | OPS GET `/actuator/health/queue` | 200, exact status/details |
| Actuator discovery links | Anonymous GET `/actuator` | 401 when blocked by security chain |
| Read-only write operation (if present) | OPS POST actuator write endpoint | Disallowed when `access=read-only`; distinguish CSRF from missing mapping |
| Probes | `/actuator/health/readiness/liveness` or `/readyz` `/livez` | Match group/status/path/port per deployment |
| Management server port | Remote client hitting separate port | Proper security/TLS/network policy |
| Indicator timeout | Slow dependency | Health fails within budget without hanging process |

**Choose assertions by contract:** if policy makes health public, assert 200/503 and absence of details; if policy restricts it to a private subnet, add network ACL tests. With custom statuses, never assume 503—verify `HttpCodeStatusMapper` actually maps them.

## 11. Self-Check Questions

**1. The endpoint has `management.endpoint.snapshot.access=read-only`, yet anonymous callers still get 401. Why?**

Because access defines **whether the operation exists**, not anonymous permission. `SecurityFilterChain` requires role OPS.

**2. OPS gets 404 at `/actuator/info`. Does OPS lack permissions?**

Not necessarily: OPS satisfies Actuator security policy, yet `info` is not in the demo's `management.endpoints.web.exposure.include` and has not opted into access. Check access, exposure, and path instead of tweaking roles blindly.

**3. Anonymous calls to health return 200 without `components`. Is that a bug?**

No. `show-components=when-authorized` and `roles=OPS` intentionally redact details. Kubelets/load balancers typically need only the status.

**4. Operator calls health and gets 503 with `"status":"DOWN"`. Does the operator lack permissions?**

No. The operator passed security; this reflects degraded health status and the `DOWN -> 503` mapping.

**5. Does setting `management.endpoints.web.exposure.include=*` secure endpoints?**

No. It widens HTTP exposure; you still need access policies, Spring Security, firewalls/mTLS, and sanitization checks.

**6. After writing a custom `SecurityFilterChain` for Actuator, does the web app keep Boot's default security chain?**

Boot's security auto-config normally backs off once a custom `SecurityFilterChain` exists. You must configure and test security for the **entire application**, not Actuator alone.

**7. Why isn't unit testing `QueueHealthIndicator.health()` enough?**

It does not prove the bean is registered, statuses aggregate properly, the endpoint is exposed, HTTP status codes map properly, or details are hidden by role.

**8. `DOWN` stopped returning 503 after adding a custom HTTP mapping for `FATAL`. What happened?**

Custom HTTP mappings can drop default `DOWN`/`OUT_OF_SERVICE` mappings. Re-declare mappings you want to preserve and add HTTP regression tests.

**9. If Kubernetes liveness checks the DB, a DB outage restarts every pod. Is that reasonable?**

Usually no. Liveness should reflect unrecoverable internal process state; external dependencies generally belong in readiness or service degradation policies.

**10. Does `@Endpoint(id="snapshot")` automatically create a public URL?**

No. The endpoint must be **permitted by access policy**, **exposed on the web**, and the request must **pass `SecurityFilterChain`**. `@ReadOperation` defines a GET operation, not anonymous access.

## 12. Operations and QA Checklist

- [ ] I distinguish `HealthIndicator`, `HealthEndpoint`, custom endpoints, access, exposure, HTTP authorization, and detail visibility.
- [ ] Spring Boot 3.5 properties use `management.endpoint.<id>.access` / `management.endpoints.access.default` / `max-permitted`.
- [ ] Endpoints default to deny unless opted in; needed endpoints use the tightest access (`read-only` for GET-only).
- [ ] Web exposure uses a minimal allowlist; never expose `*` in production.
- [ ] Tests verify 401 for anonymous and 403 for insufficient roles on sensitive Actuator endpoints.
- [ ] Positive test verifies OPS can read custom read endpoints with secret-free JSON.
- [ ] Custom `SecurityFilterChain` does not open business routes; anonymous 401 test is included.
- [ ] Health URL matches the threat model if public, with anonymous body restricted to status only.
- [ ] `show-details`, `show-components`, and `health.roles` are explicitly configured.
- [ ] Tests prove USER cannot view infrastructure details while OPS can.
- [ ] Tested the same custom `HealthIndicator` in both UP and DOWN states, verifying aggregate status flips.
- [ ] Tested HTTP health returns **200 when UP, 503 when DOWN** per active HTTP mapping.
- [ ] Verified exact component name (e.g., `queue`) and non-sensitive details.
- [ ] Unexposed endpoints are tested with a fully privileged role to distinguish 404 from 401/403.
- [ ] `access=none` endpoints are tested in a context with property overrides.
- [ ] Tests avoid overusing `@MockBean` where real registries/endpoint mappings are under test.
- [ ] For health groups, contributor IDs and group membership are validated.
- [ ] Liveness does not blindly depend on external DBs/APIs; readiness reflects traffic readiness.
- [ ] Separate management port/context has dedicated network/TLS/security tests if distinct from main port.
- [ ] When adding custom status mappings, `DOWN`/`OUT_OF_SERVICE` 503 mappings are preserved explicitly.
- [ ] When adding write operations, both CSRF and authorization are tested rather than assuming any 403 means role failure.
- [ ] Accounted for API/config differences between Servlet MVC and Reactive WebFlux.
- [ ] No secrets, PII, or sensitive hostnames appear in `withDetail(...)` or custom Actuator output.
- [ ] Health endpoints never run unbounded slow dependency checks; timeouts/rate budgets are enforced.
- [ ] Never confused `MockMvc` tests with real HTTP ports, ingress, NetworkPolicy, or mTLS verification.
- [ ] Executed `mvn test` on JDK 17+ against the project's real Spring Boot/Actuator/Security versions.

**Conclusion:** Proper Actuator testing covers **health indicator logic**, **contributor registration**, **HTTP health status mapping**, **endpoint availability**, **Spring Security authorization**, and **detail visibility**. A `200` response does not guarantee safe public exposure; a `503` health response is not a role error; a `404` can come from access or exposure; and defining a custom `SecurityFilterChain` makes you responsible for securing both Actuator and application routes. Use unit tests for indicators, `MockMvc`/`@SpringBootTest` for security/mapping, and real HTTP/deployment tests for management ports and live infrastructure.

### Official Documentation (Spring Boot 3.5)

- [Spring Boot 3.5 — Actuator Endpoints, Access, Exposure, Security, Health](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html)
- [Spring Boot 3.5 — HealthIndicator API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/HealthIndicator.html)
- [Spring Boot 3.5 — HealthEndpoint API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html)
- [Spring Boot 3.5 — EndpointRequest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)
- [Spring Boot 3.5 — Custom Actuator @Endpoint API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html)
- [Spring Boot 3.5 — Spring Security Integration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
